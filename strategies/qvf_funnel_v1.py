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
#     [0] 환경·의존성·계약(Q1~Q14) 자가검정 → 합성 스모크 → 실경로 리허설
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
#  ▸ 일봉을 받을 '후보' 배수. 후보 = 각 신호일 시총 하위 (U1000_N × 이 값) 의 합집합.
#    전 종목(5,000+)의 일봉을 받는 것은 낭비다 — 시총 스냅샷은 날짜당 1~2호출로 전 종목
#    시총을 주므로 후보를 먼저 확정할 수 있다. 버퍼가 필요한 이유는 유동성·구조제외 게이트가
#    하위 종목을 걸러내 '적격 하위 1000' 이 전체 하위 1000 보다 아래로 내려가기 때문이다.
#    실제로 버퍼가 모자랐는지는 실행 중 실현 랭크로 검증해 표로 보고한다(모자라면 경고).
#    ★ 배수를 크게 잡으면 안전하지만 절감이 사라진다. 실측 감쇠(전체상장 186 → 적격 148,
#      약 20% 탈락)를 근거로 2.0 을 기본으로 둔다. 게이트 탈락률이 50% 를 넘는 시장 국면이면
#      경고가 뜨고, 그때 이 값을 올려 재실행하면 된다.
CANDIDATE_BUFFER_MULT = 2.0

#  ▸ Tier-2(전체 재무제표) 수집 빈도.  "annual" | "quarterly"
#    ★ 이 한 줄이 콜드빌드 기간을 좌우한다. Tier-2 는 회사별 API 라 (회사×연도×보고서)마다
#      1호출이다 — 후보 3,000사 × 15년 × 4분기 = 180,000회 = 하루 2만 한도로 9일이다.
#    ★ Tier-2 가 Tier-1(주요계정 배치, 100사/호출)보다 '더' 주는 것은 매출원가(gp_a)와
#      영업활동현금흐름(PCR·발생액) 둘뿐이다. 나머지 V/Q 지표와 자본잠식 판정은 Tier-1 로 끝난다.
#    ★ 이 둘은 모두 '느리게 변하는 품질 지표'다. Novy-Marx(gp_a) · Sloan(발생액) 원논문도
#      연간 재무로 정의하고, 국내 소형주 분기재무는 비감사라 잡음이 크다. 따라서 연간(FY)이
#      타협이 아니라 오히려 표준 설계다 — 대신 TTM 이 연 1회 갱신된다는 점은 명시한다.
#    → "annual" 이면 콜드빌드가 하루 안에 끝난다. "quarterly" 로 바꾸면 며칠에 걸쳐
#      이어받기로 완성되며, 중간에 끊겨도 캐시는 그대로 남는다(진행률이 로그에 표시됨).
DART_TIER2_FREQ = "annual"

#  ▸ Tier-2 대상 버퍼. 가격용 버퍼(CANDIDATE_BUFFER_MULT)와 '따로' 둔다.
#    가격은 후보를 넉넉히 받아도 호출이 종목당 1회지만, Tier-2 는 (회사 × 연도)마다 1회라
#    버퍼를 키우면 콜드빌드 기간이 그만큼 늘어난다. 게이트 실측 탈락률(전체상장 186 → 적격
#    148, 약 20%)을 덮는 1.25 면 충분하다. 모자라면 해당 종목은 gp_a·PCR·발생액만 결측이
#    되고 나머지 축은 Tier-1 으로 그대로 산출된다(선정에서 사라지지 않는다).
DART_TIER2_BUFFER_MULT = 1.25

#  ▸ Tier-2 소급 연수. 연간(FY) 기준에서 roic_std3y 는 3개 관측(Y, Y-1, Y-2)이면 되므로 2 다.
#    share_growth3y 는 이제 DART 가 아니라 KRX 시총 스냅샷의 상장주식수를 쓰므로 무관하다.
DART_TIER2_LOOKBACK_Y = 2
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
#  ★ §8.1 의 문언은 "비용 = 증권거래세 + 실측 호가스프레드 기반 슬리피지" 다. 수수료와
#    제곱근 시장충격은 명세에 없다. 명세를 넘는 비용을 기본값으로 두면 §10.4 폐기조건 ①
#    ("비용 차감 후 성과")이 사전등록되지 않은 비용 때문에 발동한다 — 하락 드리프트다.
#    그래서 기본(사전등록) 모형은 "spec" 이고, 확장 모형은 §8.4 강건성 축으로만 병기한다.
QVF_COST_MODEL = "spec"             # "spec" = 세금 + 스프레드/2 (§8.1 문언)
#                                     "extended" = spec + 수수료 + 제곱근 충격 (명세 초과)
COMMISSION_BPS = 1.5                # 편도 위탁수수료(개인 온라인 가정), bp — extended 전용
SLIPPAGE_MODE  = "corwin_schultz"   # "corwin_schultz" | "amihud" | "fixed"
SLIPPAGE_FLOOR_BPS = 15.0           # 초소형주 최소 스프레드 가정 하한
SLIPPAGE_CAP_BPS   = 400.0          # 추정 스프레드 상한 (추정치 폭주 방지)
IMPACT_K       = 0.10               # 제곱근 시장충격 계수 — extended 전용
# 체결일에 거래가 없을 때 '그 이후 첫 거래일'까지 기다리는 최대 일수.
#  ★ 예전 15일은 정지 종목이 −60% 로 재개장한 가격을 진입가로 쓰게 만들었다(정지 복권의
#    유리한 쪽만 취하는 비대칭). 짧게 잡아 '리밸런싱 시점에 거래되지 않는 종목은 못 산다'는
#    현실을 그대로 반영하고, 탈락 건수를 감사표에 남긴다.
EXEC_FILL_MAX_LAG_DAYS = 5

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
    "krx":       2.0,   # KRX 웹세션 — 올리면 차단 위험. KRXGate 가 추가로 직렬화한다.
    "fdr":       6.0,   # FinanceDataReader 자체/깃허브 캐시 경로. KRX 버킷과 분리(병목 해소).
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
VAULT_BACKUP_MAX_BYTES = 64 * 1024 * 1024   # 이보다 크면 회차별 백업 복사를 생략(원자적 교체로 보호). 삭제는 하지 않는다.
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
BUILD_VERSION      = "qvf1.20260810.1045"
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

# ★★ import 실패를 조용히 삼키면 안 된다 ★★
#   예전에는 `except Exception: pykrx_stock = None` 이었다. 그러면 '설치는 됐지만 import 가
#   깨진' 상태(파이썬 3.14 + 윈도우에서 실제로 발생)가 '패키지 없음'과 구별되지 않는다.
#   상단 표에는 "pykrx 설치됨"으로 뜨는데 실제로는 None 이라, 시총 스냅샷이 0건이 되고
#   → 후보를 못 좁혀 전 종목 5,398개 일봉을 받는 폭주로 이어졌다. 사용자는 원인을 볼 수
#   없었다. 실패 사유를 반드시 남기고, 능력 표가 '실물 import 결과'를 말하게 한다.
IMPORT_FAILURES: Dict[str, str] = {}


def _opt_import(pkg: str, fn):
    if not OPT.get(pkg):
        return None
    try:
        return fn()
    except BaseException as e:                    # noqa — SystemExit/ImportError 모두 잡는다
        IMPORT_FAILURES[pkg] = f"{type(e).__name__}: {e}"
        return None


def _import_fdr():
    import FinanceDataReader as _m                # type: ignore
    # FDR 은 종목마다 '"000010" invalid symbol or has no data' 를 직접 출력한다.
    # 폐지 종목이 정상적으로 섞인 소형주 백테스트에서 수천 줄이 되어 진짜 경고를 밀어낸다.
    for _n in ("FinanceDataReader", "financedatareader", "requests", "urllib3"):
        logging.getLogger(_n).setLevel(logging.CRITICAL)
        logging.getLogger(_n).propagate = False
    return _m


def _import_pykrx():
    from pykrx import stock as _m                 # type: ignore
    return _m


fdr = _opt_import("FinanceDataReader", _import_fdr)
pykrx_stock = _opt_import("pykrx", _import_pykrx)
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
        # ★ yfinance 는 종목마다 "possibly delisted; no price data found" 를 ERROR 로 뱉는다.
        #   폐지 종목이 정상적으로 섞여 있는 소형주 백테스트에서는 이게 수천 줄로 쏟아져
        #   진짜 경고를 화면 밖으로 밀어낸다. 실패 건수는 우리가 수집 시도 원장으로 이미
        #   집계하므로(원인·재시도 정책 포함) 라이브러리 자체 로그는 끈다 — 정보 손실이 없다.
        for _n in ("yfinance", "yfinance.data", "yfinance.ticker", "peewee", "urllib3"):
            logging.getLogger(_n).setLevel(logging.CRITICAL)
            logging.getLogger(_n).propagate = False
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








CELL_LADDER = ("cell", "cell_l2", "cell_l3")








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




def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)






# ── 벡터화 롤링 OLS (칼만 대체, §3) ─────────────────────────────────────────────────────────




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
                # ★ 대용량 테이블(일봉 패널·DART 원시계정 등)은 백업 전체복사가 드라이브에
                #   파일 크기의 2배 I/O 를 만든다. 몇 행 추가하려고 수백 MB 를 두 번 쓴다.
                #   atomic_write_parquet 이 이미 임시파일→교체라 '쓰다 만 파일'은 생기지
                #   않으므로, 큰 파일은 복사를 건너뛰고 직전 1개만 보존한다.
                _sz = os.path.getsize(path)
                if _sz > VAULT_BACKUP_MAX_BYTES:
                    _prev = os.path.join(self.ns[scope], "index", "_backup", f"{name}.prev.parquet")
                    if not os.path.exists(_prev):
                        shutil.copy2(path, _prev)           # 최초 1회만 안전본을 남긴다
                    LOG.debug(f"{name}: {_sz/1e6:,.0f}MB — 회차별 백업 생략(원자적 교체로 보호). "
                              f"직전 안전본은 _backup/{name}.prev.parquet")
                else:
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


@contextmanager
def _suppress_corrupt_rename():
    """이 블록 안에서는 read_parquet_safe 가 파일을 개명하지 않는다.

    ★ 쓰기루트도 결국 같은 구글드라이브다. 위 독스트링이 진단한 파괴 조건(placeholder /
      동기화 중 부분 파일)은 미러만의 문제가 아니라 쓰기루트에서도 똑같이 성립한다.
      그런데 코어 load_index 는 index.parquet 을 read_parquet_safe 로 읽으므로,
      동기화가 느린 환경에서는 실행마다 index.parquet 을 `.corrupt.<ts>` 로 개명한다.
      저널이 진실의 원천이라 데이터 유실은 없지만 (a) "삭제 없음 / 기존 캐시 훼손 금지"가
      자기 쓰기루트에서 깨지고, (b) .corrupt 파일이 무한히 쌓이며, (c) 멀쩡한 컴팩션
      결과를 매번 버려 저널 전량 재파싱을 하게 된다.
    """
    g = globals()
    orig = g.get("read_parquet_safe")

    def _ro(path, *a, **kw):
        d, st = ro_read_parquet(path)
        if d is None and st not in ("ok", "FileNotFoundError"):
            LOG.info(f"인덱스 parquet 을 아직 읽을 수 없습니다({st}) — 파일은 그대로 두고 "
                     f"저널로 진행합니다: {path}")
        return d

    g["read_parquet_safe"] = _ro
    try:
        yield
    finally:
        if orig is not None:
            g["read_parquet_safe"] = orig


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
        # 이번 실행에서 등록한 행. 코어가 self._idx 를 갱신하지 않으므로 조회 때 얹어준다.
        self._new_rows: Dict[str, List[dict]] = {}
        self._idxlk = threading.RLock()              # read_parquet_safe 치환 구간 보호용

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

    # ★★ 같은 실행에서 저장한 것을 같은 실행에서 반드시 되찾을 수 있어야 한다 ★★
    #   코어 Vault._register 는 _pending 과 _uidset 만 갱신하고 self._idx 는 손대지 않는다.
    #   그리고 코어 load_index 는 force 가 아니면 self._idx 의 캐시본을 그대로 돌려준다.
    #   그래서 "put_blob → flush → get_blob" 이 같은 실행 안에서 None 을 돌려주는 구멍이
    #   있었다. 콜드런 1회차에 방금 내려받은 PDF 가 TONE 입력에서 통째로 빠지고, 2회차부터
    #   갑자기 정상이 되는 형태로 나타난다 — '본문이 짧아 제외'와 구분되지 않는다.
    #   저장↔재호출 연결은 이 전략의 절대 1원칙이므로, 등록분을 인덱스에 반드시 얹는다.
    def _pending_frame(self, scope: str) -> Optional[pd.DataFrame]:
        with self._lk:
            rows = list(self._new_rows.get(scope, ()))
        if not rows:
            return None
        f = pd.DataFrame(rows)
        if "uid" in f.columns:
            f["uid"] = f["uid"].astype(str)
        f["_root"] = self.root
        return f

    def _with_new_rows(self, scope: str, own: pd.DataFrame) -> pd.DataFrame:
        f = self._pending_frame(scope)
        if f is None:
            return own
        o = own.copy()
        if "_root" not in o.columns:
            o["_root"] = self.root
        allc: List[str] = []
        for g in (o, f):
            for c in g.columns:
                if c not in allc:
                    allc.append(c)
        out = pd.concat([o.reindex(columns=allc), f.reindex(columns=allc)], ignore_index=True)
        if "uid" in out.columns:
            out["uid"] = out["uid"].astype(str)
            # 저널을 이미 다시 읽었다면 같은 uid 가 양쪽에 있다 — 먼저 온 쪽(저널)을 남긴다.
            out = out.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)
        return out

    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        if force:
            # ★ force=True 가 오히려 복구를 막던 버그: 파생 캐시를 같이 비우지 않으면
            #   스테일 인덱스로 만들어진 빈 uid→경로 사전이 그대로 남아 get_blob 이
            #   영구히 None 을 돌려준다.
            with self._lk:
                self._merged.pop(scope, None)
                self._uidpath.pop(scope, None)
                self._mirror_idx.pop(scope, None)
        with self._idxlk:
            with _suppress_corrupt_rename():
                own = super().load_index(scope, force=force)
        own = self._with_new_rows(scope, own)
        if self._own_only:
            with self._lk:
                self._uidset[scope] = set(own["uid"].astype(str).tolist()) if len(own) else set()
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
                if sc != scope:
                    LOG.warn(f"  ※ 요청 스코프는 '{scope}' 인데 '{sc}' 스코프의 동명 테이블을 "
                             f"채택했습니다: {name} — 이름이 겹치는 전략이 있는지 확인하세요.")
                    self.table_src[name] = f"{mr}#{sc}"
                # ★★ 승격은 '드라이브에 파일이 실재하지 않을 때만' ★★
                #   super().get_table 은 파일이 있어도 max_age_days 를 넘기면 None 을 준다.
                #   그 None 을 '드라이브에 없음'으로 읽으면, 로컬 미러(복사·동기화로 mtime 만
                #   최신이고 내용은 과거)가 드라이브의 최신본을 덮어쓴다. dart_corpcode 처럼
                #   전 파이프라인의 종목 연결 축이 3분의 1로 줄어드는 사고가 실제로 난다.
                _own_p = os.path.join(self.table_dir(scope), f"{name}.parquet")
                if self.promote_tables and not os.path.exists(_own_p):
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
        with self._lk:
            self._new_rows.setdefault(scope, []).append(dict(rec))
        self._merged.pop(scope, None)
        self._uidpath.pop(scope, None)

    def flush(self, scope: Optional[str] = None):
        """코어와 달리 append 가 성공한 뒤에 pending 을 비운다.

        ★ 코어는 `rows, self._pending[sc] = self._pending[sc], []` 로 먼저 비우고 append 한다.
          드라이브 용량 초과·네트워크 끊김으로 append 가 던지면 그 행들은 영구 소실되고,
          blob 파일은 이미 쓰여 있으므로 '인덱스 없는 고아 blob' 이 남는다. 삭제 API 가
          없으므로 영구히 남고, 그 세션 내내 has() 는 True 라 재수집도 되지 않는다.
        """
        scopes = [scope] if scope else ["shared", "private"]
        for sc in scopes:
            with self._lk:
                rows = list(self._pending.get(sc, ()))
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)     # 실패하면 여기서 예외 — pending 은 그대로
            with self._lk:
                del self._pending[sc][:len(rows)]
            self.stats[f"journal_append:{sc}"] += len(rows)
            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,
              source: str = "", event_date=None, knowledge_date=None,
              scope: str = "shared", extra: Optional[dict] = None,
              size: Optional[int] = None) -> Optional[str]:
        """size 를 알고 있으면 getsize() 를 생략한다 — 드라이브 FUSE 왕복 1회/파일 절감.

        ★ uid 는 코어와 동일한 sha1_str("adopt", domain, subtype, abspath, size) 여야 한다.
          계약 Q7 이 '코어 경로와 size 지정 경로의 uid 가 같은가'를 회귀로 고정한다.
        """
        if size is None:
            return super().adopt(abs_path, domain, subtype, key, source=source,
                                 event_date=event_date, knowledge_date=knowledge_date,
                                 scope=scope, extra=extra)
        sz = int(size)
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
    # ★★ 이름으로 프루닝하면 사용자의 폴더를 먹는다 ★★
    #   예전에는 {"blob","table","index","_backup","_locks","reports"} 를 '이름'으로 잘랐다.
    #   그러면 트리 어디에 있든 그 이름이면 하위 전체가 사라진다 — GDRIVE_ADOPT_DIRS 기본값에
    #   `reports` 가 있는데 `research/reports/`, `archive/reports/` 는 리포트를 모아둔
    #   폴더에서 극히 흔한 이름이다. 실측으로 8개 중 7개가 통째로 누락됐고, 누락 사실은
    #   어디에도 남지 않았다. 그래서 '이름'이 아니라 '구조'로 판정한다.
    _HEX2_RE = re.compile(r"^[0-9a-f]{2}$")
    _HASH_FANOUT_MIN = 32          # 2자리 16진수 하위폴더가 이만큼이면 내용해시 샤드 트리
    _MANAGED_NS_CHILD = {"index", "blob", "table", "_backup", "_locks"}
    _SKIP_DIRNAMES = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules",
                      ".cache", ".Trash", "$RECYCLE.BIN", "System Volume Information"}

    def _is_cache_ns(self, path: str) -> bool:
        """`<X>/_shared/blob` 처럼 '캐시 네임스페이스 바로 아래의 관리 폴더'인가.

        이름만 보는 것이 아니라 부모가 캐시 네임스페이스인지까지 본다. 사용자의
        `research/reports`, `archive/table` 은 여기에 걸리지 않는다.
        """
        parts = [p for p in os.path.normpath(str(path)).replace("\\", "/").split("/") if p]
        for i in range(len(parts) - 1):
            if parts[i] in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS) and \
                    parts[i + 1] in self._MANAGED_NS_CHILD:
                return True
        return False

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

        # ── 디렉터리 체크포인트 ──────────────────────────────────────────────────────────
        #  ★ 예전 체크포인트는 mtime 만 저장하고, 무변경이어도 scandir 는 그대로 했다.
        #    아끼는 것이 파일 stat 뿐이라 '디렉터리 열거 절감률 0.0%' 였고, FUSE 왕복이
        #    비용의 전부인 드라이브에서는 이어받기가 회차당 +332 → +47 → +7 로 감쇠해
        #    사실상 수렴하지 않았다. 이제 '완주한 디렉터리의 하위폴더 목록'까지 저장해서,
        #    mtime 이 같으면 scandir 자체를 생략하고 저장된 하위폴더로 바로 내려간다.
        #  ★ 그리고 상한으로 중도 탈출한 디렉터리는 체크포인트에 넣지 않는다. 예전에는
        #    scandir '전에' 기록해서, 상한에 걸려 10건만 읽은 디렉터리의 나머지 40건이
        #    (트리가 바뀌지 않는 한) 영구히 등록되지 않았다.
        ckpt: Dict[str, Tuple[float, List[str]]] = {}
        cdf = self.get_table("qvf_adopt_scan_state", scope="private")
        if cdf is not None and len(cdf):
            try:
                _mt = pd.to_numeric(cdf["mtime"], errors="coerce").fillna(-1.0)
                _sd = (cdf["subdirs"].astype(str) if "subdirs" in cdf.columns
                       else pd.Series(["[]"] * len(cdf)))
                for _p, _m, _s in zip(cdf["dirpath"].astype(str), _mt, _sd):
                    try:
                        kids = json.loads(_s) if _s and _s != "nan" else []
                    except Exception:
                        kids = []
                    ckpt[_p] = (float(_m), list(kids) if isinstance(kids, list) else [])
            except Exception:
                ckpt = {}
            LOG.info(f"이전 스캔 체크포인트 {len(ckpt):,}개 디렉터리 — 변경되지 않은 폴더는 "
                     f"열거(scandir) 자체를 생략하고 저장된 하위폴더로 바로 내려갑니다.")

        t0 = time.time()
        found: List[dict] = []
        new_ckpt: Dict[str, Tuple[float, List[str]]] = dict(ckpt)
        n_files = n_dirs = n_skipped_dirs = n_ckpt_hit = 0
        skipped_samples: List[str] = []
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
                prev = ckpt.get(cur)
                if prev is not None and abs(prev[0] - st_m) < 1e-6:
                    # 무변경 + 이전에 '완주' 한 디렉터리 → 열거를 통째로 생략한다.
                    n_ckpt_hit += 1
                    stack.extend(prev[1])
                    continue
                completed = True
                subdirs: List[str] = []
                hex2 = 0
                try:
                    with os.scandir(cur) as it:
                        for ent in it:
                            try:
                                if ent.is_dir(follow_symlinks=False):
                                    nm = ent.name
                                    if nm.startswith(".") or nm in self._SKIP_DIRNAMES:
                                        n_skipped_dirs += 1
                                        continue
                                    if self._is_cache_ns(ent.path):
                                        n_skipped_dirs += 1
                                        if len(skipped_samples) < 6:
                                            skipped_samples.append(ent.path)
                                        continue
                                    if self._HEX2_RE.match(nm):
                                        hex2 += 1
                                        if hex2 >= self._HASH_FANOUT_MIN:
                                            # 내용해시 샤드 트리(최대 65,536 디렉터리). 여기는
                                            # 남의 캐시 blob 이지 사용자의 리포트가 아니다.
                                            n_skipped_dirs += 1
                                            if len(skipped_samples) < 6:
                                                skipped_samples.append(ent.path)
                                            continue
                                    if _same_place_key(ent.path) in managed:
                                        n_skipped_dirs += 1
                                        continue
                                    subdirs.append(ent.path)
                                    stack.append(ent.path)
                                    continue
                                # ★ 예산 검사가 디렉터리 경계에만 있으면 예산이 상한이 아니다.
                                #   파일 1만 개짜리 디렉터리 하나가 예산을 통째로 넘긴다.
                                if (n_files & 0x3FF) == 0 and time.time() - t0 > max_seconds:
                                    completed = False
                                    stopped = f"시간 예산 {max_seconds:.0f}초 초과"
                                    break
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
                                    completed = False
                                    break
                            except Exception:
                                continue
                except Exception as e:                              # noqa
                    completed = False
                    LOG.warn(f"  디렉터리 열람 실패({type(e).__name__}) — 이 하위 트리는 "
                             f"이번 실행에서 등록되지 않습니다: {cur}")
                if completed:
                    # 완주한 디렉터리만 체크포인트에 남긴다(중도 탈출분은 다음 실행에서 재시도).
                    new_ckpt[cur] = (st_m, subdirs)

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
                # scandir 에서 이미 크기를 알고 있다 — getsize() 를 또 부르면 드라이브 FUSE
                # 왕복이 파일마다 한 번씩 더 붙는다(리포트 3만 건이면 2.6~6.4분).
                self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                           subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                           event_date=ed, knowledge_date=ed, scope="shared",
                           extra={"dir": r.dir},
                           size=(int(r.bytes) if int(r.bytes) >= 0 else None))
            self.flush("shared")
            LOG.ok(f"기존 리포트 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
                   f"(파일은 원위치 그대로, 이동·삭제 없음) — "
                   f"디렉터리 {n_dirs:,}개 · {dur:.1f}초")

        # ★ 프루닝은 '조용히' 하면 안 된다. 사용자가 자기 리포트가 왜 안 잡혔는지 알 수 있어야
        #   한다. 예전에는 n_skipped_dirs 를 증가만 시키고 출력하는 곳이 한 군데도 없었다.
        LOG.table([["걸은 디렉터리", f"{n_dirs:,}"],
                   ["체크포인트 적중(열거 생략)", f"{n_ckpt_hit:,}"],
                   ["프루닝한 하위폴더", f"{n_skipped_dirs:,}"],
                   ["프루닝 예시", _trunc(" / ".join(skipped_samples), 90) if skipped_samples else "—"],
                   ["새로 찾은 파일", f"{len(found):,}"],
                   ["소요", f"{dur:.1f}초"],
                   ["중단 사유", stopped or "—"]],
                  ["항목", "값"], ["l", "l"],
                  title="기존 리포트 폴더 스캔 요약 — 프루닝 건수를 숨기면 누락을 알 수 없다")
        if stopped:
            LOG.warn(f"스캔을 중단했습니다: {stopped}. 완주한 디렉터리만 체크포인트에 저장했으므로 "
                     f"다음 실행에서 남은 폴더부터 이어받습니다(중도 탈출한 폴더는 다시 읽습니다). "
                     f"상한을 늘리려면 ADOPT_SCAN_MAX_FILES / ADOPT_SCAN_MAX_SECONDS 를 조정하세요.")
        try:
            self.put_table("qvf_adopt_scan_state",
                           pd.DataFrame({"dirpath": list(new_ckpt.keys()),
                                         "mtime": [v[0] for v in new_ckpt.values()],
                                         "subdirs": [json.dumps(v[1], ensure_ascii=False)
                                                     for v in new_ckpt.values()]}),
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

    def _reload_other(self):
        """저널을 다시 읽어 '남이 오늘 쓴 양'만 갱신한다(hist/observed 는 건드리지 않는다).

        020 을 기록하기 직전에 부른다. 형제 프로세스의 소비가 안 보이면 내 눈에 보이는
        누적이 실제보다 작고, 그 작은 값이 그날의 실측 한도로 저널에 영구히 박힌다.
        """
        rows: List[dict] = []
        for p in [self._path()] + self._mirror_paths():
            rows.extend(read_jsonl(p))
        seen, tot = set(), 0
        for r in rows:
            if r.get("event") != "use" or str(r.get("date")) != self.today:
                continue
            eid = r.get("evt_id") or (r.get("host"), r.get("pid"), r.get("ts"), r.get("n"))
            if eid in seen:
                continue
            seen.add(eid)
            try:
                tot += max(0, int(r.get("n", 0)))
            except Exception:
                pass
        # 내 몫(self.n)은 이미 저널에 flush 되어 tot 에 포함되므로 빼서 이중계상을 막는다.
        with self._lk:
            self.n_other = max(0, tot - int(self.n))

    def _load(self):
        rows: List[dict] = []
        for p in [self._path()] + self._mirror_paths():
            rows.extend(read_jsonl(p))
        # ★★ 미러의 저널 사본을 중복 합산하면 안 된다 ★★
        #   로컬 미러가 드라이브 캐시의 복사본이면(= CACHE_MIRROR_ROOTS 의 정상 용도) 같은
        #   소비 이벤트가 '미러 수 + 1' 배로 세어진다. 실측으로 500건 사용이 1,000~1,500건
        #   으로 잡혔고, take() 의 안전정지가 실제 사용량의 절반 지점에서 걸려 DART 수집이
        #   조기 중단됐다. 그런데 그 스테이지는 critical=False 라 실패로 잡히지도 않는다.
        #   → evt_id 로 dedup 한다. 미러를 '읽는' 것 자체는 타당하다(다른 기기의 소비를
        #     봐야 하므로). 중복만 걷어낸다.
        seen_evt = set()
        uniq: List[dict] = []
        for r in rows:
            eid = r.get("evt_id")
            if eid:
                if eid in seen_evt:
                    continue
                seen_evt.add(eid)
            else:
                # 구버전 저널(evt_id 없음)은 자연키로 대체한다.
                nk = (r.get("date"), r.get("key_fp"), r.get("host"), r.get("pid"),
                      r.get("ts"), r.get("event"), r.get("n"), r.get("limit"))
                if nk in seen_evt:
                    continue
                seen_evt.add(nk)
            uniq.append(r)
        if len(uniq) != len(rows):
            LOG.debug(f"DART 쿼터 저널 중복 {len(rows) - len(uniq):,}행 제거(미러 사본)")
        rows = uniq
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
        self._seq = getattr(self, "_seq", 0) + 1
        _ts = _dt.datetime.now().isoformat(timespec="microseconds")
        rec = {"date": self.today, "key_fp": self.key_fp, "pid": os.getpid(),
               "host": platform.node(), "ts": _ts,
               # 미러 사본 중복 합산을 막는 고유 id. 없으면 dedup 자체가 불가능하다.
               "evt_id": sha1_str("dartquota", platform.node(), os.getpid(), _ts, self._seq),
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
        # ★ used_today = self.n + self.n_other 인데 n_other 는 __init__ 의 _load() 에서
        #   딱 한 번만 읽었다. 이 프로세스가 시작한 뒤 형제 프로세스(TCD·두 번째 QVF 실행)가
        #   같은 키를 쓴 몫이 안 보이므로, 020 이 왔을 때 내 눈에 보이는 누적은 실제보다
        #   훨씬 작다. 그 작은 값이 '그날의 실측 한도'로 저널에 영구 기록되고, 이후 모든
        #   실행이 그 근처(및 ×2 안전정지)에서 멈춘다 — 한 번 오염되면 매일 재현된다.
        #   기록 직전에 저널을 다시 읽어 형제 소비분을 반영한다.
        self._flush()
        try:
            self._reload_other()
        except Exception as e:
            LOG.debug(f"저널 재조회 실패({type(e).__name__}) — 프로세스 내 집계로만 기록합니다.")
        self.observed_limit = int(self.used_today)
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

    def remaining_calls(self) -> Optional[int]:
        """오늘 더 쓸 수 있는 호출 수의 '숫자'. 모르면 None (문자열판 remaining_str 과 짝).

        수집부는 이 값으로 작업 목록을 잘라낸다 — 한도를 코드에 고정하지 않고, 그렇다고
        전부 던져 놓고 예외를 기다리지도 않기 위해서다. 후자가 실제로 하루치를 통째로
        태우고도 아무 회사도 완성시키지 못한 원인이었다.

        ★ 실측 상한이 아직 없으면 None 이 아니라 헤더 힌트 기준 잔여를 준다. None 을 주면
          호출부가 '무제한'으로 오해해 예전 동작으로 되돌아간다.
        """
        with self._lk:
            used = int(self.used_today)
        if self.observed_limit is not None:          # 오늘 020 을 이미 봤다 = 확정적으로 소진
            return max(0, int(self.observed_limit) - used)
        # ★ 과거 실측치는 '그날 그 지점에서 막혔다'는 하한 증거일 뿐 상한이 아니다.
        #   (키를 다른 프로세스와 나눠 썼으면 그날치가 낮게 찍힌다 — 실제로 사용자 키는
        #    14,047 에서 막혔지만 OpenDART 공표 한도는 20,000 이다.)
        #   이걸 상한으로 쓰면 매일 6,000 호출을 스스로 버리게 된다. 계획은 둘 중 큰 값으로
        #   잡고, 진짜 중단은 오늘 020 이 실제로 올 때 한다 = "실시간으로 체크해서 그만큼 쓴다".
        cap = max(int(self.hist_limit or 0), int(DART_DAILY_LIMIT_HINT))
        return max(0, cap - used)

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


def _krx_recent_bizday() -> str:
    d = _dt.date.today() - _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d.strftime("%Y%m%d")


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
        # ★★ 로그인 성공을 '실패 단어가 없더라' 로 판정하면 안 된다 ★★
        #   예전 판정은 응답 앞 600자에 (실패|오류|error|fail) 가 없으면 성공으로 봤다.
        #   그러면 (a) 엔드포인트가 바뀌어 엉뚱한 200 응답이 와도 '성공', (b) 네트워크
        #   실패·차단·캡차로 txt=None 이면 전부 'ID/PW 를 확인하세요' 가 된다.
        #   사용자가 자격증명을 정확히 넣고도 틀렸다는 말을 듣는 이유가 정확히 (b) 다.
        #   → 성공은 '실제 인증이 필요한 호출이 되는가' 로만 증명하고, 실패는 사유를 나눈다.
        reasons = []
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                reasons.append("네트워크/차단: 로그인 엔드포인트가 응답하지 않음")
                continue
            body_s = str(txt)
            if re.search(r"CD011|중복\s*로그인", body_s):
                reasons.append("중복 로그인(CD011): 같은 계정이 다른 곳에 로그인되어 있음")
                LOG.warn("KRX 중복 로그인(CD011) — 같은 계정이 브라우저나 다른 노트북에서 이미 "
                         "로그인되어 있습니다. 두 곳을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if re.search(r"(비밀번호|아이디).{0,20}(불일치|틀|확인)|존재하지\s*않는\s*(회원|아이디)",
                         body_s[:1500]):
                reasons.append("자격증명 불일치: KRX 가 ID/PW 오류로 응답함")
                continue
            # 여기까지 왔으면 '아마 성공' 이다. 말이 아니라 기능으로 확인한다.
            self.session_ok = True
            probe = self.json_data("dbms/MDC/STAT/standard/MDCSTAT01501",
                                   mktId="ALL", trdDd=_krx_recent_bizday())
            if isinstance(probe, dict) and probe.get("OutBlock_1"):
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공 (인증 호출로 확인).")
                return True
            self.session_ok = False
            reasons.append("로그인 응답은 정상이나 인증 호출이 데이터를 주지 않음 "
                           "(세션 미형성 또는 bld 변경)")
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스를 사용하지 못했습니다 — 사유: "
                 + " / ".join(dict.fromkeys(reasons)) + "\n"
                 "  ※ 이 단계는 '검증·보강' 이며 백테스트에 필수가 아닙니다. 상장/폐지 목록과 "
                 "시총은 로그인 불필요 경로(FDR·KIND·pykrx)로 이미 확보됩니다.\n"
                 "  ※ 자격증명이 맞는데도 위 사유가 '네트워크/차단' 이면 ID/PW 문제가 아닙니다.")
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
        # ★ 예전엔 pykrx 를 12스레드에서 '직접' 불렀다. KRXGate 가 존재하는 이유가 정확히
        #   이것을 막기 위해서다(10_ingest_universe:46-54): 동시 호출이 각자 재로그인을 하고
        #   KRX 가 skipDup 으로 앞 세션을 죽여, 진 쪽은 JSON 대신 로그인 HTML 을 받는다.
        #   그러면 이 종목은 실패로 떨어져 fdr → naver(×4) → yfinance 까지 전부 타므로
        #   종목당 요청이 4~8배가 된다. 55분의 상당 부분이 이 되먹임이었다.
        #   KRXG.call 은 락으로 직렬화하고 세션을 미리 갱신한다(자체 스로틀 포함이라
        #   limiter("krx") 는 이중 대기가 되어 뺀다).
        d = KRXG.call(pykrx_stock.get_market_ohlcv,
                      start.replace("-", ""), end.replace("-", ""), code)
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
        # ★ FDR 은 KRX 웹세션이 아니라 자체 엔드포인트/깃허브 캐시를 쓴다. 그런데 "krx" 버킷을
        #   같이 쓰고 있어서, pykrx 와 FDR 이 초당 2건을 '나눠' 먹었다. 종목 3,300개가 두
        #   경로를 다 타면 6,600슬롯 ÷ 2/s ≈ 55분 — 사용자가 본 그 숫자다. 버킷을 분리한다.
        limiter("fdr").wait()
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


# 종목 → 시장(KOSPI/KOSDAQ). 종목 마스터에서 채운다. 비어 있으면 예전처럼 둘 다 시도한다.
CODE_MARKET: Dict[str, str] = {}
CODE_LISTED: Dict[str, pd.Timestamp] = {}     # 종목 → 상장일
CODE_DELISTED: Dict[str, pd.Timestamp] = {}   # 종목 → 폐지일


def set_code_dates(sec: pd.DataFrame):
    """상장일·폐지일 표. '캐시가 완결인가'를 판정하는 1순위 증거다.

    ★ 왜 필요한가: 캐시 최소일이 요청 시작일보다 늦을 때, 그것이 '결손'인지 '그 종목의
      실제 최초 거래일'인지 구분해야 한다. 예전에는 별도 원장(price_fetch_attempts)에만
      의존했는데, 그 원장은 구버전에서 실패만 기록했고 다른 PC/전략의 캐시를 물려받으면
      아예 비어 있다. 실측: 캐시 696만행·3,497종목이 있는데 원장에 없다는 이유로 3,492종목을
      '처음부터 다시' 받았다. 상장일은 이미 종목 마스터에 있다 — 그걸 쓰는 게 맞다.
    """
    lo, ld = CODE_LISTED, CODE_DELISTED
    lo.clear(); ld.clear()
    cols = {c.lower(): c for c in sec.columns}
    c_list = cols.get("listing_date") or cols.get("listed_date") or cols.get("list_date")
    c_del = cols.get("delisting_date") or cols.get("delist_date")
    codes = sec["code"].astype(str)
    if c_list:
        for c, v in zip(codes, as_ts_series(sec[c_list])):
            if pd.notna(v):
                lo[c] = v
    if c_del:
        for c, v in zip(codes, as_ts_series(sec[c_del])):
            if pd.notna(v):
                ld[c] = v
    LOG.debug(f"상장일 {len(lo):,}종목 · 폐지일 {len(ld):,}종목 확보 — 캐시 완결성 판정에 사용")


def set_code_market(sec: pd.DataFrame):
    """yfinance 접미사를 '추측'하지 않기 위한 시장 구분표.

    ★ 예전에는 모든 종목에 .KS 와 .KQ 를 둘 다 시도했다. 시장 구분은 종목 마스터에 이미
      있는데도 그랬다. 그 결과 (a) 호출이 정확히 2배가 되고 (b) 실패하는 쪽이 항상 하나씩
      생겨 로그가 'possibly delisted' 로 도배되어 진짜 오류가 묻힌다.
    """
    if sec is None or not len(sec) or "market" not in sec.columns:
        return
    m = {}
    for c, mk in zip(sec["code"].astype(str), sec["market"].astype(str)):
        u = mk.upper()
        if "KOSDAQ" in u:
            m[c] = ".KQ"
        elif "KOSPI" in u or "STK" in u:
            m[c] = ".KS"
    CODE_MARKET.update(m)
    LOG.debug(f"yfinance 접미사 확정 {len(m):,}종목 (추측 대신 시장 구분 사용)")


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    known = CODE_MARKET.get(str(code))
    sufs = (known,) if known else (".KS", ".KQ")
    for suf in sufs:
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
    # ★ 예전엔 _today = as_ts(end) 였다 — end 는 BACKTEST_END(설정 상수)지 '오늘'이 아니다.
    #   그래서 attempted_at 이 항상 같은 값이라 (_today - at).days 가 늘 0 이었고,
    #   "30일 뒤 자동 재시도합니다"는 영원히 오지 않았다. 일시적 네트워크 장애 한 번으로
    #   종목이 유니버스에서 영구 제외되는데 INFO 한 줄로만 흘렀다.
    _today = pd.Timestamp.today().normalize()
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

    todo, n_back, n_fwd, n_skip, n_ipo = [], 0, 0, 0, 0
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, start_ts):
                n_skip += 1
                continue
            todo.append((c, start))
            continue
        # ★ 과거 방향 백필을 함께 본다. 앞선 실행이 최근 구간만 캐시했다면
        #   max 만 보고 판단하면 앞 구간을 영원히 못 받는다.
        if mn is not None and mn > start_ts + pd.Timedelta(days=10):
            # ★★ 여기서 무조건 재수집하면 '무한 재수집 루프'가 된다 ★★
            #   2019년 상장 종목의 캐시 최소일은 당연히 2019년이다. 그건 '결손'이 아니라
            #   그 종목의 실제 최초 거래일이다. 그런데 요청 시작일(2015)과만 비교하면
            #   매 실행 전 구간을 다시 받고, 상장 전 데이터는 존재하지 않으므로 캐시
            #   최소일이 움직이지 않아, 다음 실행도 똑같이 다시 받는다 — 영원히.
            #   실측: 이 조건 하나로 1,974종목이 매 실행 재수집되어 55분을 썼다.
            #   → 이미 이 시작일(또는 그 이전)로 요청해 본 적이 있으면 mn 이 곧 그 종목의
            #     확정된 최초 거래일이다. 다시 물어도 답은 같다.
            #   ★ 증거는 세 가지다. 강한 순서대로 본다.
            #     ① 상장일: 캐시 최소일이 상장일 근처면 그건 결손이 아니라 완결이다. 가장 강하다.
            #     ② 폐지일: 요청 시작일 이전에 이미 폐지된 종목은 받을 데이터 자체가 없다.
            #     ③ 시도 원장: 위 둘을 모르는 종목의 마지막 수단.
            #   예전에는 ③만 봤다. 그런데 원장은 구버전에서 실패만 기록했고 다른 PC/전략의
            #   캐시를 물려받으면 비어 있다 — 실측으로 캐시 3,497종목 중 3,492종목이
            #   '원장에 없다'는 이유만으로 전량 재수집됐다. 상장일은 이미 손에 있었다.
            _L = CODE_LISTED.get(c)
            _D = CODE_DELISTED.get(c)
            _p = attempts.get(c)
            _asked = _p.get("frm") if _p else None
            if _L is not None and pd.notna(_L) and mn <= as_ts(_L) + pd.Timedelta(days=10):
                n_ipo += 1                      # ① 상장일 = 캐시 최소일 → 완결
            elif _D is not None and pd.notna(_D) and as_ts(_D) <= start_ts:
                n_ipo += 1                      # ② 요청 구간 전에 폐지 → 받을 것이 없음
            elif _asked is not None and pd.notna(_asked) and _asked <= start_ts + pd.Timedelta(days=10):
                n_ipo += 1                      # ③ 같은 시작일로 이미 물어봤다
            else:
                todo.append((c, start))
                n_back += 1
        elif mx < end_ts - pd.Timedelta(days=5):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
            n_fwd += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목을 처음부터 다시 받습니다 "
                 f"(요청 시작일 이전으로 물어본 적이 없는 종목만).")
    if n_ipo:
        LOG.info(f"캐시 최소일이 요청 시작일보다 늦지만 이미 확인된 {n_ipo:,}종목은 재수집하지 "
                 f"않습니다 (상장이 그 이후 = 결손이 아님). 이 판정이 없으면 매 실행 전 구간을 "
                 f"다시 받고도 캐시가 그대로라 영원히 반복합니다.")
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
        failed, asked = [], []
        for (c, st), d in zip(todo, res):
            # ★ 성공/실패와 무관하게 '무엇을 언제 어느 시작일로 물어봤는지'를 남긴다.
            #   성공분을 안 남기면 위의 무한 재수집 판정이 근거를 잃는다.
            asked.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
        if asked:
            _prev = _att if _att is not None and len(_att) else None
            _all = pd.concat([_prev, pd.DataFrame(asked)], ignore_index=True) \
                if _prev is not None else pd.DataFrame(asked)
            # 같은 종목은 '가장 이른 시작일로 물어본 기록'을 남긴다(그게 확정 근거다).
            _all = (_all.sort_values(["code", "requested_from", "attempted_at"])
                        .drop_duplicates("code", keep="first").reset_index(drop=True))
            try:
                VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                                source="fetch_prices:asked_ledger")
            except Exception as e:                                   # noqa
                LOG.warn(f"수집 시도 원장 저장 실패({type(e).__name__}) — 다음 실행이 같은 "
                         f"구간을 다시 받을 수 있습니다.")
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # 실패분은 위 asked 원장에 이미 포함되어 있다(중복 저장하지 않는다).

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


_FS_DIV: Dict[str, str] = {}          # corp_code → 그 회사에서 실제로 먹히는 fs_div
_FS_DIV_LK = threading.Lock()


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    # ★ 예전엔 (회사, 연도, 보고서)마다 OFS 를 먼저 치고 비면 CFS 를 또 쳤다. 소형주는
    #   연결재무제표만 내는 곳이 많고 폐지사는 대부분 연도에 제출 자체가 없어서, 빈 조합마다
    #   호출이 2배가 됐다 — 작업 15만건이 실호출 21만~25만건이 되는 경로다.
    #   fs_div 는 회사 속성이지 연도 속성이 아니므로 회사당 한 번만 알아내고 재사용한다.
    with _FS_DIV_LK:
        known = _FS_DIV.get(corp)
    order = (known,) if known else ("OFS", "CFS")
    js, used = None, None
    for div in order:
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": reprt, "fs_div": div})
        if js and isinstance(js.get("list"), list) and js["list"]:
            used = div
            break
    if used and not known:
        with _FS_DIV_LK:
            _FS_DIV[corp] = used
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        # ★ '데이터 없음'도 결과다. 빈손을 캐시하지 않으면 done 집합에 영영 안 들어가서
        #   매 실행 같은 조합을 다시 묻는다 — "재실행하면 이 지점부터 이어받습니다"가
        #   거짓이 되는 지점이고, 하루치 한도가 통째로 '같은 부재를 재발견'하는 데 쓰였다.
        #   센티넬 1행을 남겨 다음 실행이 건너뛰게 한다(값은 전부 결측이라 집계에 무해).
        return pd.DataFrame([{**{c: None for c in _FS_KEEP}, "corp_code": corp,
                              "bsns_year": int(year), "reprt_code": reprt,
                              "fs_div": "NONE", "account_id": "_EMPTY_"}])[_FS_KEEP]
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
                          priority: Optional[Sequence[str]] = None,
                          only_years: Optional[Dict[str, set]] = None,
                          reprt_codes: Optional[Sequence[str]] = None) -> pd.DataFrame:
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

    reprts = list(reprt_codes) if reprt_codes else (
        [REPRT_CODES["FY"]] if DART_STATEMENT_FREQ == "annual"
        else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    # ★ only_years 가 있으면 '그 회사가 실제로 후보였던 기간(+소급)'만 요청한다. 예전에는
    #   (회사 전체) × (전 기간 연도)의 데카르트 곱이라 2,980사 × 15년 × 4보고서 = 178,800회,
    #   회사별 API 로 9일짜리 작업이었다. 2018~2021 에만 하위권이던 회사의 2012년 재무는
    #   어느 리밸런싱 시점에서도 읽히지 않는다.
    jobs = [(c, y, r) for y in sorted(years, reverse=True) for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done
            and (only_years is None or int(y) in only_years.get(str(c), ()))]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        total_needed = len(jobs)
        # ★★ 예전에는 jobs 전체를 그대로 pmap_io 에 넘기고 '한도에 걸리면 예외가 나겠지'에
        #    맡겼다. 그 결과 하루치 호출을 통째로 태우고도 아무 회사도 완성되지 않았다
        #    (실측: 사용자 키가 14,117회 소진). 요구사항은 "남은 호출량을 실시간으로 체크해서
        #    그만큼만 쓰라"이므로, 던지기 전에 살아 있는 잔여 예산으로 잘라낸다.
        _left = DBUDGET.remaining_calls() if DBUDGET is not None else None
        if _left is not None and _left <= 0:
            LOG.warn(f"DART 잔여 호출이 0 입니다 — Tier-2(전체 재무제표) 신규 수집을 건너뜁니다. "
                     f"Tier-1(주요계정)만으로 V축·자본잠식 판정은 동작합니다. "
                     f"내일 재실행하면 정확히 이 지점부터 이어받습니다.")
            jobs = []
        elif _left is not None and total_needed > _left:
            LOG.warn(f"필요 호출({total_needed:,})이 오늘 잔여({_left:,})를 넘습니다 — "
                     f"잔여만큼인 {_left:,}건만 받고 나머지는 다음 실행으로 넘깁니다. "
                     f"약 {math.ceil(total_needed / max(_left, 1))}일에 걸쳐 콜드빌드가 완성됩니다. "
                     f"(우선순위 정렬이 되어 있어 '투자 가능한 종목의 최근 데이터'부터 채워집니다)")
            jobs = jobs[:_left]
        else:
            LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 (오늘 잔여 "
                     f"{_left if _left is not None else '미상':,}건 이내)"
                     if _left is not None else f"DART 재무 신규 수집 대상 {total_needed:,}건")
    if jobs:
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
    # ★ '데이터 없음' 센티넬(_fs_one)은 재요청을 막으려고 캐시에만 남기는 행이다. 여기서
    #   걸러내지 않으면 '전체 재무제표가 있다'고 오인해 Tier-1(주요계정) 폴백을 막아버린다.
    if full is not None and len(full) and "account_id" in full.columns:
        full = full[full["account_id"].astype(str) != "_EMPTY_"]
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


def research_covered_years(cached: Optional[pd.DataFrame], source: str) -> set:
    """캐시에 이미 충분히 담긴 '지난 연도'들. 그 해는 다시 훑지 않는다.

    ★ 예전에는 두 수집기 모두 캐시를 아예 보지 않고 매 실행 10년 전체를 다시 훑었다.
      한경만 연 375페이지 × 11년 ÷ 2.0qps ≈ 34분, 네이버 상세보강까지 합치면 약 3시간이
      '이미 가진 것을 다시 받는 데' 쓰였다.
    ★ 올해는 항상 다시 훑는다 — 새 리포트가 계속 올라오기 때문이다. 지난 연도는 확정이다.
    """
    if cached is None or not len(cached) or "pub_date" not in cached.columns:
        return set()
    d = cached
    if "source" in d.columns:
        d = d[d["source"].astype(str).str.contains(source, na=False)]
    if not len(d):
        return set()
    y = as_ts_series(d["pub_date"]).dt.year.dropna()
    if not len(y):
        return set()
    this_year = pd.Timestamp.today().year
    cnt = y.value_counts()
    # 그 해에 리포트가 극소수면 수집이 중간에 끊긴 것으로 보고 다시 훑는다.
    return {int(k) for k, v in cnt.items() if int(k) < this_year and int(v) >= 100}


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400,
                     skip_years: Optional[set] = None) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다."""
    rows: List[dict] = []
    years = [y for y in range(as_ts(start).year, as_ts(end).year + 1)
             if not (skip_years and y in skip_years)]
    if skip_years:
        LOG.info(f"한경: 캐시에 확정된 {len(skip_years)}개 연도는 건너뜁니다 "
                 f"(재수집 {len(years)}개 연도만 — 연도당 약 375페이지).")
    if not years:
        return pd.DataFrame()
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
                  max_pages: int = 1500, skip_years: Optional[set] = None) -> pd.DataFrame:
    # ★ 네이버는 날짜 구간 하나로 훑으므로 '연도 건너뛰기' 대신 시작일을 앞으로 당긴다.
    #   캐시가 확정한 연도가 start 부터 연속으로 이어지는 만큼만 잘라낸다(중간 구멍은 다시 받는다).
    if skip_years:
        y0, y1 = as_ts(start).year, as_ts(end).year
        y = y0
        while y <= y1 and y in skip_years:
            y += 1
        if y > y0:
            start = max(as_ts(start), as_ts(f"{y}-01-01")).strftime("%Y-%m-%d")
            LOG.info(f"네이버: 캐시 확정 구간을 건너뛰고 {start} 부터 수집합니다 "
                     f"({y - y0}개 연도 절약).")
            if as_ts(start) > as_ts(end):
                return pd.DataFrame()
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
                        codes: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다.

    ★ 이 함수 하나가 매 실행 2시간 13분을 썼다(20,000건 ÷ 2.5qps). 원인 두 가지:
      ① 상세를 열어봤는데 목표주가가 없던 건은 다음 실행에도 target_price 가 결측이라
         '아직 안 해봤다'와 구분되지 않아 영원히 다시 열었다 → detail_tried 로 표시한다.
      ② 소비처는 build_tp_revision 뿐이고 그건 U-1000 패널에만 붙는다. 후보 밖 종목의
         목표주가는 어디에도 쓰이지 않는데 다 받고 있었다 → codes 로 좁힌다.
    """
    if df.empty:
        return df
    if "detail_tried" not in df.columns:
        df = df.assign(detail_tried=False)
    df["detail_tried"] = df["detail_tried"].fillna(False).astype(bool)
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna()) &
              (~df["detail_tried"])].copy()
    if codes is not None and "stock_code" in need.columns:
        _cs = {str(c) for c in codes}
        n0 = len(need)
        need = need[need["stock_code"].astype(str).isin(_cs)]
        if n0:
            LOG.info(f"네이버 상세 보강 대상을 U-1000 후보로 축소: {n0:,} → {len(need):,}건 "
                     f"(후보 밖 종목의 목표주가는 어느 패널에도 붙지 않습니다)")
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
    # ★ 시도했다는 사실 자체를 남긴다. 목표주가를 못 찾은 건도 '해봤다'로 표시해야
    #   다음 실행이 같은 URL 을 다시 열지 않는다(이게 2시간의 절반이었다).
    df.loc[df["detail_url"].isin(need["detail_url"]), "detail_tried"] = True
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
    # ★ 이미 받아서 blob 에 넣고 원장에 pdf_uid 를 남긴 건은 다시 열지 않는다. blob 캐시가
    #   HTTP 는 막아줬지만 예전에는 pdf_uid 가 병합에서 증발해(14_entity:agg 누락) 매 실행
    #   전 코퍼스를 드라이브에서 다시 읽고 pdf_text() 로 다시 파싱했다 — 최대 30만회.
    _done_pdf = (df["pdf_uid"].astype(str).str.len() > 0) if "pdf_uid" in df.columns \
        else pd.Series(False, index=df.index)
    work = df[df["pdf_url"].notna() & ~_done_pdf].copy()
    if int(_done_pdf.sum()):
        LOG.info(f"PDF {int(_done_pdf.sum()):,}건은 이미 원장에 pdf_uid 가 있어 건너뜁니다 "
                 f"(신규 대상 {len(work):,}건).")
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
        # ★★ 이 4개가 빠져 있어서 PDF 캐시가 '쓰고도 못 읽는' 상태였다 ★★
        #   download_pdfs 는 pdf_uid/pdf_analysts/pdf_emails/pdf_target 를 돌려주고
        #   원장에 저장까지 된다. 그런데 다음 실행에서 원장을 다시 읽어 이 agg 를 통과시키면
        #   여기 없는 컬럼은 통째로 사라진다 → download_pdfs 가 pdf_uid 를 못 봐서
        #   전 코퍼스(최대 30만건)를 매번 다시 내려받고 다시 파싱했다. blob 캐시가 HTTP 는
        #   막아줬지만 드라이브 blob 읽기 + pdf_text() 파싱 30만회는 그대로 났다.
        **({k: (k, _pick_str) for k in ("pdf_uid", "pdf_analysts", "pdf_emails")
            if k in d.columns}),
        **({"pdf_target": ("pdf_target", "max")} if "pdf_target" in d.columns else {}),
        # 상세페이지 조회 여부도 같은 이유로 반드시 살아남아야 한다 — 떨어지면 목표주가를
        # 못 찾은 건을 매 실행 다시 연다(네이버 상세 2시간의 원인).
        **({"detail_tried": ("detail_tried", "max")} if "detail_tried" in d.columns else {}),
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
# ★★ 이름 규칙은 실존 소형주를 영구 삭제할 수 있다 — 경계를 반드시 붙인다 ★★
#   예전 `우(?:B|C)?$` 는 '연우'·'미래에셋대우' 처럼 '…우' 로 끝나는 보통주를 전부 우선주로
#   판정했고, `파워|마이다스|FOCUS|TREX` 는 접미 경계가 없어 '파워로직스'·'파워넷' 을
#   ETF 로 판정했다. 셋 다 정확히 §3.1 이 겨냥하는 하위 1000 구간 종목이다. 시점불변
#   삭제라 전 리밸런싱·전 실험에서 동일하게 빠지는 재현 가능한 편향이 된다.
#   → 우선주 이름 규칙은 '숫자+우' / '우B' / '우선주' 처럼 우선주에서만 나타나는 형태로
#     좁히고, 단독 '…우' 는 코드 6번째 자리 규칙에만 맡긴다(그쪽이 정확하다).
_PREF_NAME_RE = re.compile(r"\d+우(?:B|C)?$|[가-힣A-Za-z]우(?:B|C)$|우선주")
_SPAC_RE = re.compile(r"스팩|기업인수목적")
_REIT_RE = re.compile(r"리츠|위탁관리부동산투자|기업구조조정부동산투자|부동산투자회사")
# ETF/ETN 브랜드 접두는 뒤에 공백/숫자/영문 경계를 요구한다. '파워'·'마이다스'·'FOCUS'·
# 'TREX' 는 실존 사업회사 이름의 접두이기도 하므로 목록에서 뺀다(§3.3 에 없는 확장이기도 하다).
_FUND_RE = re.compile(r"^(KODEX|TIGER|KBSTAR|ARIRANG|KINDEX|HANARO|KOSEF|SOL|ACE|PLUS|RISE|"
                      r"미래에셋TIGER)(?=[\s\d]|$)|ETN$|ETF$|레버리지$|인버스$|선물\s*ETN")

# 구조적 제외로 걸러진 종목을 사후 검증할 수 있도록 명단을 남긴다(개수만 찍으면 확인 불가).
EXCLUSION_AUDIT: Dict[str, str] = {}


def is_preferred(code: str, name: str = "") -> bool:
    c = str(code or "")
    if len(c) == 6 and c[5] not in ("0",):
        # 신형 영숫자 코드는 6번째가 0/K/L/M/N 이고 0 만 보통주다. 구형은 0 이 보통주.
        return True
    # ★ 코드가 보통주(6번째='0')로 확정된 종목은 이름 규칙을 적용하지 않는다.
    #   코드 규칙이 이름 규칙보다 정확하며, 이름 규칙의 오탐은 전부 이 경로에서 나왔다.
    if len(c) == 6 and c[5] == "0":
        return bool(re.search(r"우선주$", str(name or "")))
    return bool(_PREF_NAME_RE.search(str(name or "")))


def classify_exclusion(code: str, name: str) -> str:
    """이름·코드만으로 판별 가능한 구조적 제외 사유. 없으면 빈 문자열."""
    nm = str(name or "").strip()
    why = ""
    if is_preferred(code, nm):
        why = "우선주"
    elif _SPAC_RE.search(nm):
        why = "스팩"
    elif _REIT_RE.search(nm):
        why = "리츠"
    elif _FUND_RE.search(nm):
        why = "ETF/ETN"
    if why:
        EXCLUSION_AUDIT[f"{code} {nm}"] = why
    return why


# ── 거래일 캘린더 / 리밸런싱 격자 ────────────────────────────────────────────────────────────
def fetch_trading_calendar(start: str, end: str) -> np.ndarray:
    """거래일 격자를 '지수 1종목' 으로 만든다. 전 종목 일봉이 필요 없다.

    ★★ 왜 필요한가 ★★
      예전 순서는 [전 종목 일봉 수집] → [거래일 확정] → [리밸 캘린더] → [시총 스냅샷] 이었다.
      즉 '하위 1000 종목이 누구인지' 를 알기도 전에 5,000종목이 넘는 일봉을 전부 받았다.
      시총 스냅샷은 날짜당 1~2호출로 전 종목 시총을 주므로, 순서만 뒤집으면 후보를
      먼저 확정하고 그 종목만 받을 수 있다. 그 순서 반전을 막고 있던 것이 이 순환 의존
      (캘린더 ← 일봉) 이었고, 지수 하나면 끊어진다.
    """
    lo = (as_ts(start) - pd.DateOffset(months=18)).strftime("%Y-%m-%d")
    hi = as_ts(end).strftime("%Y-%m-%d")
    for nm, fn in (("pykrx-index", lambda: (pykrx_stock.get_index_ohlcv(
                        lo.replace("-", ""), hi.replace("-", ""), "1001")
                        if pykrx_stock is not None else None)),
                   ("fdr-KS11", lambda: (fdr.DataReader("KS11", lo, hi)
                                         if fdr is not None else None))):
        try:
            d = fn()
        except Exception as e:                                      # noqa
            LOG.debug(f"거래일 격자 {nm} 실패({type(e).__name__})")
            continue
        if d is None or not len(d):
            continue
        idx = pd.DatetimeIndex(pd.to_datetime(d.index)).normalize()
        idx = idx[(idx >= as_ts(lo)) & (idx <= as_ts(hi))]
        if len(idx) > 200:
            LOG.ok(f"거래일 격자 {len(idx):,}일 확보 ({nm}, 호출 1회) — "
                   f"전 종목 일봉 없이 캘린더를 만든다")
            return np.sort(pd.unique(idx.values))
    LOG.warn("지수로 거래일 격자를 만들지 못했습니다 — 영업일(Mon-Fri) 격자로 폴백합니다. "
             "공휴일이 거래일로 잡히면 signal/exec 이 하루씩 어긋날 수 있으니 로그를 확인하세요.")
    return np.sort(pd.bdate_range(lo, hi).values)


def select_universe_candidates(caps: pd.DataFrame, signal_dates: Sequence[Any],
                               n_target: int = U1000_N,
                               buffer_mult: float = CANDIDATE_BUFFER_MULT) -> Tuple[List[str], dict]:
    """일봉을 받을 '후보' 종목만 고른다 = 각 신호일 시총 하위 K 의 합집합.

    ★ K = n_target × buffer_mult. 버퍼가 필요한 이유: §3.2/§3.3 게이트(유동성·구조제외·
      자본잠식)가 하위 종목을 걸러내므로, 적격 하위 1000 은 전체 하위 1000 보다 아래로
      더 내려간다. 버퍼가 모자랐는지는 build_u1000 이 실현 랭크로 검증해 보고한다.
    """
    if caps is None or not len(caps):
        return [], {"reason": "시총 스냅샷 없음"}
    c = caps.copy()
    c["snap_date"] = as_ts_series(c["snap_date"])
    c["mktcap"] = pd.to_numeric(c["mktcap"], errors="coerce")
    c = c.dropna(subset=["code", "snap_date", "mktcap"])
    c = c[c["mktcap"] > 0]
    k = int(max(n_target, round(n_target * float(buffer_mult))))
    want = {as_ts(d) for d in signal_dates}
    picked: set = set()
    per_date = []
    for d, g in c.groupby("snap_date", observed=True):
        if as_ts(d) not in want:
            continue
        gg = g.nsmallest(min(k, len(g)), "mktcap")
        picked.update(gg["code"].astype(str).tolist())
        per_date.append(len(g))
    info = {"K": k, "n_dates": len(per_date), "n_candidates": len(picked),
            "n_listed_avg": float(np.mean(per_date)) if per_date else float("nan")}
    return sorted(picked), info


def qvf_trading_days(px_daily: pd.DataFrame) -> np.ndarray:
    """전 종목 일봉에서 유도한 실제 거래일 배열. 공휴일 테이블을 따로 두지 않는다
    (테이블을 두면 그 테이블이 틀렸을 때 조용히 하루씩 밀린다)."""
    if px_daily is None or not len(px_daily):
        return np.array([], dtype="datetime64[ns]")
    d = as_ts_series(px_daily["date"]).dropna()
    return np.sort(pd.unique(d.values))


def qvf_rebal_calendar_from_days(start: str, end: str, shift_days: int = 0) -> pd.DataFrame:
    """이미 확정된 QVF_TRADING_DAYS 로 캘린더를 만든다(일봉 패널 없이)."""
    return qvf_rebal_calendar(pd.DataFrame({"date": pd.Series(QVF_TRADING_DAYS)}),
                              start, end, shift_days=shift_days)


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

    # ★★ rolling(60) 은 '시장 60거래일'이 아니라 '그 종목이 가진 60개 행' 이다 ★★
    #   거래정지·소스 누락으로 행이 빠지면 창이 조용히 늘어나고, 분모에서 무거래일이 빠져
    #   유동성이 과대평가된다. 과대 배수는 정확히 60/실거래일수다 — 20일만 거래된 종목은
    #   ADTV 가 3배로 잡혀 §3.2 의 1억 게이트를 통과한다. 즉 §3.3 이 빼라는 바로 그
    #   거래정지·초박형 종목이 U-1000 에 들어오고, 백테스트는 실제로 살 수 없는 종목을 산다.
    #   pykrx 는 정지일을 amount=0 행으로 주지만 naver/yfinance 폴백은 행 자체를 생략하므로
    #   §3.2 의 의미가 소스별로 달라진다.
    #   → 시장 거래일 격자에 reindex 하고 무거래일 거래대금을 0 으로 채운 뒤 rolling 한다.
    _tds = pd.DatetimeIndex(sorted(pd.unique(px["date"])), name="date")
    _amt = (px.pivot_table(index="date", columns="code", values="amount", aggfunc="last")
              .reindex(_tds))
    _amt.columns.name = "code"
    # 첫 상장 전 구간까지 0 으로 채우면 신규 상장주의 ADTV 가 부당하게 낮아진다.
    # 각 종목의 '최초 관측일 이후'만 0 으로 채운다(그 이전은 결측 유지).
    _seen = _amt.notna().cumsum() > 0
    _amt = _amt.where(~(_seen & _amt.isna()), 0.0)
    _adtv = _amt.rolling(int(window), min_periods=int(window)).mean()
    _adtv = _adtv.stack(dropna=True).rename("adtv").reset_index()
    _adtv.columns = ["date", "code", "adtv"]
    _adtv["code"] = _adtv["code"].astype(str)
    px["code"] = px["code"].astype(str)
    px = px.merge(_adtv, on=["date", "code"], how="left")
    _n_tight = int(px["adtv"].isna().sum())
    LOG.debug(f"ADTV: 시장 거래일 격자 {len(_tds):,}일 · min_periods={window} "
              f"(자기 행이 아니라 시장 거래일 기준) · 창 미충족 결측 {_n_tight:,}행")

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
        # ★ 개수만 찍으면 사후 검증이 불가능하다. 이름 규칙의 오탐(실존 소형주가 ETF/우선주로
        #   판정되는 사고)은 명단을 봐야만 잡힌다. 사유별 표본을 반드시 남긴다.
        _samp = defaultdict(list)
        for k, v in struct.items():
            if v and len(_samp[v]) < 12:
                _samp[v].append(f"{k} {names.get(k, '')}".strip())
        LOG.table([[k, f"{by[k]:,}", _trunc(", ".join(_samp[k]), 78)] for k in by],
                  ["제외 사유", "건수", "표본(최대 12)"], ["l", "r", "l"], maxw=80,
                  title="구조적 제외 명단 (§3.3) — 이름 규칙의 오탐은 명단을 봐야만 잡힌다")

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
            "대안해석": int(alt["elig"].sum()) if len(alt) else 0,
            # §3.1 문언이 두 가지로 읽히는 지점이라 두 모집단의 규모·성격 차이를 남긴다.
            "채택_시총중앙": float(g.loc[g["in_u1000"], "mktcap"].median())
                              if int(g["in_u1000"].sum()) else np.nan,
            "채택_시총상한": float(g.loc[g["in_u1000"], "mktcap"].max())
                              if int(g["in_u1000"].sum()) else np.nan,
            "대안_시총중앙": float(alt.loc[alt["elig"], "mktcap"].median())
                              if len(alt) and int(alt["elig"].sum()) else np.nan,
            "대안_시총상한": float(alt.loc[alt["elig"], "mktcap"].max())
                              if len(alt) and int(alt["elig"].sum()) else np.nan,
            "겹침": (len(set(g.loc[g["in_u1000"], "code"]) &
                         set(alt.loc[alt["elig"], "code"])) /
                     max(1, int(g["in_u1000"].sum()))) if len(alt) else np.nan})

    # ★ 후보 버퍼가 실제로 충분했는지 검증한다. 후보를 K 로 잘랐는데 적격 하위 1000 이
    #   K 밖까지 내려가야 했다면, 그만큼의 종목이 '데이터가 없어서' 빠진 것이지
    #   '규칙에 걸려서' 빠진 것이 아니다. 그건 조용한 유니버스 손실이다.
    _K = int(max(U1000_N, round(U1000_N * float(CANDIDATE_BUFFER_MULT))))
    _bind = []
    for t, g in d.groupby("rebal", observed=True):
        gm = g[g["mktcap"].notna()]
        if not len(gm) or not int(g["in_u1000"].sum()):
            continue
        r_all = gm["mktcap"].rank(method="first", ascending=True)
        r_sel = r_all[g.loc[gm.index, "in_u1000"].to_numpy()]
        if len(r_sel) and float(r_sel.max()) >= _K * 0.95:
            _bind.append((t, int(r_sel.max()), int(g["in_u1000"].sum())))
    if _bind:
        LOG.warn(f"후보 버퍼(K={_K:,})가 빠듯한 분기 {len(_bind)}회 — "
                 + ", ".join(f"{as_ts(t):%Y-%m}:최대랭크 {r:,}" for t, r, _n in _bind[:6])
                 + (" …" if len(_bind) > 6 else "")
                 + ". CANDIDATE_BUFFER_MULT 를 올려 다시 실행하면 그만큼 종목이 더 들어옵니다. "
                   "지금 결과는 '데이터가 없어 빠진 종목'이 있을 수 있다는 뜻입니다.")
    else:
        LOG.debug(f"후보 버퍼 K={_K:,} 충분 — 전 분기에서 적격 하위 {U1000_N:,} 가 K 안에 들어옴")

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
             f"(적격 평균 {Aud['적격'].mean():,.0f} / 전체상장 평균 {Aud['전체상장'].mean():,.0f})")
    # ★★ §3.1 '하위 1000종목' 은 문언상 두 가지로 읽힌다 ★★
    #   (A) 채택: §3.2/§3.3 게이트를 통과한 종목 안에서 하위 1000
    #   (B) 대안: 전 종목에서 하위 1000 을 먼저 뽑고 그 안에서 게이트
    #   둘은 모집단 자체가 다르다 — (A)가 더 크고 유동성 좋은 종목을 포함하므로 비용이
    #   낮아지고, 1차필터 선택률이 낮아져 Score1 의 분산·알파가 기계적으로 커진다.
    #   즉 §10.2 의 "1차필터 기여 = 알파 창출" 주장이 이 해석 하나에 직접 의존한다.
    #   개수 한 줄만 찍고 넘어가면 안 되므로 규모·성격 차이를 표로 남긴다.
    _fmt_eok = lambda v: "—" if not np.isfinite(v) else f"{v/1e8:,.0f}억"
    LOG.table([
        ["종목수", f"{Aud['U1000'].mean():,.0f}", f"{Aud['대안해석'].mean():,.0f}"],
        ["시총 중앙값", _fmt_eok(Aud['채택_시총중앙'].mean()), _fmt_eok(Aud['대안_시총중앙'].mean())],
        ["시총 상한", _fmt_eok(Aud['채택_시총상한'].mean()), _fmt_eok(Aud['대안_시총상한'].mean())],
        ["채택 대비 겹침률", "100.0%", f"{100*Aud['겹침'].mean():.1f}%"],
    ], ["항목", "채택: 게이트 → 하위1000", "대안: 하위1000 → 게이트"], ["l", "r", "r"],
        title="§3.1 '하위 1000' 해석 비교 (전 분기 평균) — 명세 문언이 두 갈래로 읽히는 지점")
    globals()["U1000_INTERP_AUDIT"] = {
        "n_adopted": float(Aud["U1000"].mean()), "n_alt": float(Aud["대안해석"].mean()),
        "cap_med_adopted": float(Aud["채택_시총중앙"].mean()),
        "cap_med_alt": float(Aud["대안_시총중앙"].mean()),
        "cap_max_adopted": float(Aud["채택_시총상한"].mean()),
        "cap_max_alt": float(Aud["대안_시총상한"].mean()),
        "overlap": float(Aud["겹침"].mean())}
    if np.isfinite(Aud["겹침"].mean()) and Aud["겹침"].mean() < 0.90:
        LOG.warn(f"두 해석의 겹침률이 {100*Aud['겹침'].mean():.1f}% 입니다 — 사실상 다른 "
                 f"모집단입니다. 결과를 '하위 1000 전략'이라고 부를 때 어느 해석인지 반드시 "
                 f"명시하고, 전체 재실행으로 비교하려면 U1000_RANK_BEFORE_FILTER=True 로 "
                 f"두고 한 번 더 돌리십시오(§8.4 축으로 자동 병행하지는 않습니다 — 유니버스가 "
                 f"바뀌면 패널 전체를 다시 만들어야 해서 실행시간이 두 배가 됩니다).")
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


def shares_from_cap_snapshots(snaps: Optional[pd.DataFrame],
                              sec: pd.DataFrame) -> pd.DataFrame:
    """KRX 시총 스냅샷의 '상장주식수'로 DART 주식총수 테이블과 같은 모양을 만든다.

    왜 이게 대체재가 아니라 상위 호환인가:
      · DART stockTotqySttus 는 (회사 × 연도)마다 1호출이다. 후보 2,000사 × 11년 = 22,000회로
        그것 하나가 하루 한도를 태운다. 반면 상장주식수는 시총 스냅샷 호출에 이미 실려 온다(0원).
      · DART 는 분기 공시 시차가 있지만 스냅샷은 '그 날 실제 주식수'라 정의상 PIT 이다.
      · 스냅샷 격자 = 분기 신호일이므로 share_growth3y 의 shift(12) 가 정확히 3년 전을 가리킨다.

    자기주식(shares_treasury)만은 KRX 가 주지 않으므로 결측으로 둔다 — 유동시총이 자기주식
    미차감 근사가 된다는 뜻이고, 그 사실은 호출부가 로그로 밝힌다.
    """
    cols = ["corp_code", "knowledge_date", "shares_issued", "shares_treasury", "period_end"]
    if snaps is None or not len(snaps) or sec is None or not len(sec):
        return pd.DataFrame(columns=cols)
    m = (sec[["code", "corp_code"]].dropna().astype(str).drop_duplicates("code"))
    S = snaps.copy()
    S["code"] = S["code"].astype(str)
    S = S.merge(m, on="code", how="inner")
    S["knowledge_date"] = as_ts_series(S["snap_date"])
    S = S.dropna(subset=["corp_code", "knowledge_date", "shares"])
    S = S[pd.to_numeric(S["shares"], errors="coerce") > 0]
    if not len(S):
        return pd.DataFrame(columns=cols)
    S["shares_issued"] = pd.to_numeric(S["shares"], errors="coerce")
    S["shares_treasury"] = np.nan          # KRX 미제공 — 0 으로 채우면 자기주식 0 이라 우기는 셈
    S["period_end"] = S["knowledge_date"]
    S = (S.sort_values(["corp_code", "knowledge_date"], kind="stable")
          .drop_duplicates(["corp_code", "knowledge_date"], keep="last"))
    return S[cols].reset_index(drop=True)


def candidate_year_span(snaps: Optional[pd.DataFrame], sec: pd.DataFrame,
                        signal_dates: Sequence[pd.Timestamp], n_target: int,
                        buffer_mult: float, lookback_years: int = 3) -> Dict[str, set]:
    """corp_code → 실제로 재무가 필요한 회계연도 집합.

    ★ 왜 필요한가: 예전에는 (후보 전체) × (전 기간 연도)의 데카르트 곱을 요청했다.
      2,980사 × 15년 × 4보고서 = 178,800회 — 회사별 API 로는 9일이 걸린다. 그런데 어떤
      회사가 2018~2021 에만 시총 하위권이었다면 2012년이나 2026년 재무는 어디에도 쓰이지
      않는다. 그 회사가 '후보였던 기간'과 3년 소급(roic_std3y·share_growth3y·TTM)만 받는다.

    반환: {corp_code: {연도, ...}}
    """
    out: Dict[str, set] = {}
    if snaps is None or not len(snaps) or sec is None or not len(sec):
        return out
    m = sec[["code", "corp_code"]].dropna().astype(str).drop_duplicates("code")
    c2corp = dict(zip(m["code"], m["corp_code"]))
    S = snaps.copy()
    S["code"] = S["code"].astype(str)
    S["snap_date"] = as_ts_series(S["snap_date"])
    S["mktcap"] = pd.to_numeric(S["mktcap"], errors="coerce")
    S = S.dropna(subset=["code", "snap_date", "mktcap"])
    K = int(max(n_target, round(n_target * float(buffer_mult))))
    span: Dict[str, List[int]] = {}
    for d in sorted({as_ts(x) for x in signal_dates}):
        g = S[S["snap_date"] == d]
        if not len(g):
            # 그 날짜 스냅샷이 없으면 가장 가까운 과거 스냅샷을 쓴다(없으면 건너뜀).
            prev = S[S["snap_date"] <= d]
            if not len(prev):
                continue
            d2 = prev["snap_date"].max()
            g = S[S["snap_date"] == d2]
        sel = g.nsmallest(K, "mktcap")["code"]
        y = int(as_ts(d).year)
        for c in sel:
            cc = c2corp.get(str(c))
            if not cc:
                continue
            r = span.get(cc)
            if r is None:
                span[cc] = [y, y]
            else:
                if y < r[0]:
                    r[0] = y
                if y > r[1]:
                    r[1] = y
    for cc, (y0, y1) in span.items():
        out[cc] = set(range(y0 - int(lookback_years), y1 + 1))
    return out


# ── 시가총액 폴백: pykrx 없이도 PIT 시총을 만든다 ──────────────────────────────────────────
NAVER_SUM = "https://finance.naver.com/sise/sise_market_sum.naver"


def fetch_naver_shares() -> pd.DataFrame:
    """네이버 시가총액 페이지에서 전 종목 '상장주식수'를 받는다. 반환: code · shares_now

    ★ 왜 필요한가: 시총을 pykrx 단일 경로에 묶어 둔 것이 설계 오류였다. pykrx import 가
      깨지자(윈도우 인코딩) U-1000 자체를 만들 수 없어 실행이 통째로 멈췄다. 유니버스는
      여러 소스로 서야 한다.
    ★ 비용: 시장 2개 × 약 33페이지 = 약 66요청. 전 종목 주식수를 이 값으로 확보한다.
    ★ 한계: '현재' 주식수다. 과거 시총은 이 주식수를 과거로 이월해 종가와 곱해 근사한다
      (증자·분할이 있었으면 그만큼 오차). 그래서 cap_src 를 'naver_shares_x_close' 로
      남겨 §3 시총 소스 감사표에 그대로 드러나게 한다 — 숨기지 않는다.
    """
    cached = VAULT.get_table("naver_shares_snapshot", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 네이버 상장주식수 {len(cached):,}종목 재사용")
        return cached
    rows: List[dict] = []
    for sosok, mkt in ((0, "KOSPI"), (1, "KOSDAQ")):
        for page in range(1, 45):
            html = http_get(NAVER_SUM, source="naver", force_enc="euc-kr", tries=2,
                            params={"sosok": sosok, "page": page,
                                    "fieldIds": "listed_stock_cnt", "menu": "market_sum"})
            if not html:
                break
            s = soup_of(html)
            if s is None:
                break
            n0 = len(rows)
            for tr in s.select("table.type_2 tr"):
                a = tr.select_one("a.tltle") or tr.select_one("td a[href*='code=']")
                if a is None:
                    continue
                m = re.search(r"code=(\d{6})", a.get("href", ""))
                if not m:
                    continue
                tds = [td.get_text(strip=True).replace(",", "") for td in tr.select("td")]
                sh = next((v for v in reversed(tds) if v.isdigit() and len(v) >= 5), None)
                if sh:
                    rows.append({"code": m.group(1), "shares_now": float(sh), "market": mkt})
            if len(rows) == n0:                 # 더 이상 종목이 없다 = 마지막 페이지
                break
    if not rows:
        LOG.warn("네이버 상장주식수를 받지 못했습니다 (차단 또는 페이지 구조 변경).")
        return pd.DataFrame(columns=["code", "shares_now", "market"])
    S = pd.DataFrame(rows).drop_duplicates("code", keep="first").reset_index(drop=True)
    VAULT.put_table("naver_shares_snapshot", S, scope="shared", domain="universe",
                    source="naver:sise_market_sum")
    PIPE.io("OUT", "DRIVE", "naver_shares_snapshot", S, source="naver")
    LOG.ok(f"네이버 상장주식수 {len(S):,}종목 확보 (요청 약 {len(S)//50 + 2}회) — "
           f"pykrx 없이도 시총 랭크를 만들 수 있습니다.")
    return S


def cap_snapshots_from_prices(px: pd.DataFrame, shares: pd.DataFrame,
                              signal_dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """주식수 × 신호일 직전 종가 = PIT 근사 시가총액. pykrx·KRX 로그인이 모두 죽어도 선다.

    종가는 이미 캐시에 있는 일봉을 그대로 쓰므로 신규 호출이 0 이다.
    """
    cols = ["code", "snap_date", "mktcap", "shares"]
    if px is None or not len(px) or shares is None or not len(shares):
        return pd.DataFrame(columns=cols)
    P = px[["code", "date", "close"]].copy()
    P["code"] = P["code"].astype(str)
    P["date"] = as_ts_series(P["date"])
    P = P.dropna(subset=["code", "date", "close"]).sort_values("date", kind="stable")
    sh = shares.copy()
    sh["code"] = sh["code"].astype(str)
    sh = sh.dropna(subset=["code", "shares_now"]).drop_duplicates("code")
    grid = (pd.DataFrame({"snap_date": sorted({as_ts(d) for d in signal_dates})})
            .merge(sh[["code"]], how="cross").sort_values("snap_date", kind="stable"))
    M = pd.merge_asof(grid, P.rename(columns={"date": "px_date"}),
                      left_on="snap_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=15))
    M = M.dropna(subset=["close"]).merge(sh[["code", "shares_now"]], on="code", how="left")
    M["mktcap"] = pd.to_numeric(M["close"], errors="coerce") * M["shares_now"]
    M["shares"] = M["shares_now"]
    M = M.dropna(subset=["mktcap"])
    LOG.ok(f"시총 폴백 산출 {len(M):,}행 ({M['code'].nunique():,}종목 × "
           f"{M['snap_date'].nunique()}시점) — 주식수 × 종가. 신규 네트워크 호출 0회.")
    LOG.warn("이 경로의 주식수는 '현재' 값을 과거로 이월한 근사입니다 — 증자·분할이 있었던 "
             "종목은 과거 시총이 과대추정됩니다. §3 시총 소스 감사표에서 비중을 확인하세요.")
    return M[cols].reset_index(drop=True)



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


# ★★ 폴백 사다리를 cell_l3(=전 시장)까지 내리면 §5.2/5.3 의 '섹터중립'이 깨진다 ★★
#   cell_l3 는 "ym|ALL" 이라 섹터중립이 아니라 전 시장 z 다. 그런데 폴백은 '지표별 유효
#   관측 수' 기준이라, 커버리지가 낮은 섹터'만' 섹터중립을 잃는다. 실측: PBR 커버리지가
#   15% 인 섹터의 종목이 오직 그 이유로 일괄 −2.5σ 를 맞고, 상위 20 을 커버리지 100% 인
#   섹터가 독점했다. 그건 알파가 아니라 섹터 베팅이며 §5.2 가 명시적으로 금지한 것이다.
#   → 사다리는 cell_l2(같은 대분류 섹터)에서 멈춘다. 거기서도 표본이 모자라면 그 지표는
#     '결측'이며, 축 평균은 남은 지표로 계산된다(결측을 0 으로 채우지 않는 원칙 그대로).
#   ※ 전 시장 폴백을 굳이 쓰려면 "cell_l3" 로 바꾸되, 그 실행은 섹터중립이 아니다.
CELL_LADDER_MAX_LEVEL = "cell_l2"
CELL_LADDER_USAGE: Dict[str, int] = defaultdict(int)


def _cell_ladder_z(P: pd.DataFrame, v: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 폴백 사다리를 적용한 백분위-윈저 z. 표본 부족 셀을 통째로 NaN 으로 만들지 않는다."""
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z_pct(v, P["cell"], min_n=min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    CELL_LADDER_USAGE["cell"] += int(z.notna().sum())
    ladder = ["cell_l2"] if CELL_LADDER_MAX_LEVEL == "cell_l2" else ["cell_l2", "cell_l3"]
    for lvl in ladder:
        if not z.isna().any():
            break
        if lvl in P.columns:
            before = z.notna()
            z = z.where(z.notna(), xsec_z_pct(v, P[lvl], min_n=min_n))
            CELL_LADDER_USAGE[lvl] += int((z.notna() & ~before).sum())
    CELL_LADDER_USAGE["missing"] += int(z.isna().sum() - v.isna().sum()
                                        if z.isna().sum() >= v.isna().sum() else 0)
    return z


def report_cell_ladder():
    """z 가 어느 셀 레벨에서 산출됐는지. 섹터중립이 실제로 유지됐는지 여기서만 확인된다."""
    tot = sum(v for k, v in CELL_LADDER_USAGE.items() if k != "missing")
    if not tot:
        return
    LOG.table([[k, f"{CELL_LADDER_USAGE[k]:,}", f"{100*CELL_LADDER_USAGE[k]/tot:.1f}%"]
               for k in ("cell", "cell_l2", "cell_l3") if CELL_LADDER_USAGE.get(k)]
              + [["표본부족으로 결측", f"{CELL_LADDER_USAGE.get('missing', 0):,}", "—"]],
              ["z 산출 셀 레벨", "관측수", "비중"], ["l", "r", "r"],
              title=f"섹터중립 z 의 셀 레벨 분포 (§5.2/5.3) — 사다리 상한 "
                    f"'{CELL_LADDER_MAX_LEVEL}'. cell_l3(전 시장)은 섹터중립이 아니다")
    if CELL_LADDER_USAGE.get("cell_l3"):
        LOG.warn(f"전 시장 폴백(cell_l3)에서 산출된 z 가 {CELL_LADDER_USAGE['cell_l3']:,}건 "
                 f"있습니다 — 그만큼은 섹터중립이 아니며, 커버리지가 낮은 섹터가 일괄 벌점을 "
                 f"받는 방향입니다(§5.2 위반). CELL_LADDER_MAX_LEVEL='cell_l2' 를 권장합니다.")


def _denom_ok(x: pd.Series) -> pd.Series:
    """분모의 3상태 적격 판정. True=적격 · False=관측했는데 부적격 · <NA>=분모 자체를 모름.

    ★ 2상태(bool)로 두면 '모름'과 '부적격'이 같은 False 가 되어, 재무를 확보하지 못한 종목
      전체가 §5.2 의 최하위 벌점을 맞는다. 반대로 '분모가 정확히 0' 인 관측치는 safe_div 가
      NaN 을 주는 바람에 벌점을 통째로 빠져나갔다(완전자본잠식 기업이 Z_V 상위 7% 에 앉음).
      두 사고가 같은 뿌리에서 나오므로 판정 자체를 3상태로 만든다.
    """
    v = pd.to_numeric(x, errors="coerce")
    return (v > 0).astype("boolean").where(v.notna())


def z_lower_is_better(P: pd.DataFrame, raw: pd.Series, valid: pd.Series,
                      name: str = "") -> pd.Series:
    """'낮을수록 우수' 지표를 z-score(높을수록 우수)로 바꾸되, 분모 부적격(valid=False)
    관측치는 셀 최하위로 강제 배정한다 (§5.2 부호 처리 규칙).

    ★ 왜 '버리기'가 아니라 '최하위 배정'인가:
      버리면(NaN) 그 종목은 축 평균에서 빠지고, 다른 축 점수만으로 살아남아 오히려
      상위에 오를 수 있다. 즉 적자기업이 벌점 대신 면제를 받는다. 정반대의 결과다.
    """
    r = pd.to_numeric(raw, errors="coerce").replace([np.inf, -np.inf], np.nan)
    vb = valid.fillna(False).to_numpy(dtype=bool)
    ok = vb & r.notna().to_numpy()
    sig = pd.Series(np.where(ok, -r.to_numpy(dtype="float64"), np.nan), index=P.index)
    z = _cell_ladder_z(P, sig)

    # ★★ '최하위 강제'는 반드시 '횡단면 최하위' 여야 한다 ★★
    #   예전에는 셀(cell) 내 최소 z 를 벌점으로 줬다. 두 가지가 겹치면 벌점이 상점이 된다:
    #     ① z 는 표본 부족 시 cell_l2 / cell_l3(전 시장) 스케일로 계산되는데, 셀 최소는
    #        그 사실을 모른 채 원래의 작은 셀에서만 min 을 잡는다.
    #     ② 그 작은 셀의 유효 종목이 우연히 전부 '싼' 종목이면 셀 최소가 양수다.
    #   실측으로 적자 8종목이 z=+1.165 를 받아 312종목 중 6위(상위 2%)에 앉았다. 이 파일
    #   헤더가 스스로 경고한 실패("적자기업이 자동으로 최우량이 된다")가 방어 코드 안에서
    #   재현된 것이다. 더구나 U-200 선정은 groupby("rebal") 즉 전 종목 횡단면에서 이뤄지므로,
    #   벌점도 같은 횡단면에서 매겨야 규모가 일관된다(셀 크기에 따라 −2.3 ~ −4.4 로 2배
    #   차이 나던 문제도 함께 사라진다).
    _reb = P["rebal"].to_numpy()
    worst = z.groupby(_reb, observed=True).transform("min")

    # ★★ 분모가 '정확히 0' 인 관측치도 부적격이다 ★★
    #   safe_div 는 |분모| ≤ 1e-12 이면 NaN 을 준다. 예전 조건 `forced = ~ok & r.notna()` 는
    #   r 이 NaN 이라 강제를 건너뛰고 '모름'으로 분류했다. 그 결과 자기자본이 정확히 0 인
    #   기업(=§3.3 이 제외를 요구하는 완전자본잠식)이 Z_V 상위 7% 에 앉았다.
    #   valid=False 는 '분모를 봤고 부적격이더라' 이므로, r 의 결측 여부와 무관하게 강제한다.
    #   반대로 valid 자체가 결측(재무 미보유)인 경우만 '모름'으로 남긴다.
    known = valid.notna().to_numpy()
    forced = pd.Series(known & (~vb), index=P.index)
    z_out = z.copy()
    n_forced = int(forced.sum())
    if n_forced:
        z_out = z_out.where(~forced, worst)
        # 그 시점 횡단면에 유효 관측이 아예 없으면 벌점을 만들 근거가 없다 — 결측으로 둔다
        # (임의 상수를 찍지 않는다. 축 평균에서 빠지되, 그 사실은 아래 로그로 남는다).
        n_nofloor = int((forced & z_out.isna()).sum())
    else:
        n_nofloor = 0
    if name:
        LOG.debug(f"  {name}: 유효 {int(ok.sum()):,} · 분모부적격 강제최하위 {n_forced:,}"
                  f"(그중 횡단면 유효관측 부재로 벌점 불가 {n_nofloor:,}) · "
                  f"분모 자체 미상(모름) {int((~known).sum()):,}")
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
        # ★★ cumcount 로 인접성을 재면 안 된다 ★★
        #   _n 이 cumcount 이므로 `_n − shift(_n, 12)` 는 정의상 항상 정확히 12 다. 즉 예전
        #   가드는 항진명제였고 아무것도 막지 못했다 — 결측 분기를 건너뛴 채 12행 전을 집으면
        #   5년 전 주식수를 '3년 증가율' 이라 부르게 된다. 실제 달력 간격으로 재야 한다.
        prev = S.groupby("corp_code", observed=True)["shares_issued"].shift(12)
        prev_kd = S.groupby("corp_code", observed=True)["knowledge_date"].shift(12)
        gap_d = (as_ts_series(S["knowledge_date"]) - as_ts_series(prev_kd)).dt.days
        # 3년 = 1,095일. 제출 지연·분기 이동을 감안해 ±6개월(±183일)까지만 인정한다.
        contiguous = gap_d.between(1095 - 183, 1095 + 183)
        S["share_growth3y"] = (safe_div(S["shares_issued"], prev) - 1.0).where(contiguous)
        _n_drop = int((prev.notna() & ~contiguous.fillna(False)).sum())
        if _n_drop:
            LOG.debug(f"  주식수 3년 증가율: 12행 전이 실제로 3년 전이 아닌 {_n_drop:,}건 제외 "
                      f"(중간 분기 결측 — 5년 전 값을 '3년 증가율'로 부르지 않는다)")
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
    # ★ EV<=0(순현금이 시총보다 큼)은 '분모 오류'가 아니라 실제로 최우량이다. §5.2 의 부호
    #   규칙은 분모(EBIT)에 대한 것이지 분자에 대한 것이 아니다.
    #   ★ 예전엔 EV 를 0 으로 클립했는데, 그러면 순현금 기업이 전부 비율 0 에 동점으로 묶여
    #     V축 최상위를 뭉텅이로 차지한다(하위 1000 구간에서 드물지 않다). 클립하지 않으면
    #     비율이 음수로 이어져 '순현금이 많을수록 더 좋다'는 연속 순서가 그대로 보존된다.
    #     EBIT>0 이므로 낮을수록 우수라는 단조성도 깨지지 않는다.
    d["ev_ebit"] = safe_div(ev, ebit)
    d["_v_ok_ev"] = _denom_ok(ebit)

    d["pbr"] = safe_div(cap, col(d, "equity"))
    d["_v_ok_pbr"] = _denom_ok(col(d, "equity"))

    d["pcr"] = safe_div(cap, col(d, "cfo_ttm"))
    d["_v_ok_pcr"] = _denom_ok(col(d, "cfo_ttm"))

    LOG.info("V축 부호 처리 (§5.2) — 분모 ≤ 0 관측치는 해당 지표에서 횡단면 최하위로 강제 배정:")
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
    # 낮을수록 우수 → 부호 반전 후 z.
    #  ★ '분모 부적격' 개념이 없는 지표(ROIC 표준편차·발생액·주식수 증가율)는 valid 를 전부
    #    <NA> 로 준다. 예전처럼 notna() 를 주면 '관측이 없다'가 '부적격'으로 읽혀 재무를
    #    확보하지 못한 종목 전체가 최하위 벌점을 맞는다 — 그건 §5.2 가 말하는 부호 처리가
    #    아니라 커버리지에 대한 처벌이다.
    _na = pd.Series(pd.NA, index=d.index, dtype="boolean")
    d["zQ_roic_std3y"] = z_lower_is_better(d, col(d, "roic_std3y"), _na, "ROIC 3년 표준편차")
    d["zQ_accruals"] = z_lower_is_better(d, d["accruals"], _na, "발생액")
    # 부채비율은 자기자본이 0 이하면 의미가 뒤집힌다(음수 부채비율=최우량). 부적격 처리.
    d["zQ_debt_ratio"] = z_lower_is_better(d, d["debt_ratio"], _denom_ok(col(d, "equity")),
                                           "부채비율")
    d["zQ_share_growth3y"] = z_lower_is_better(d, col(d, "share_growth3y"), _na,
                                               "주식수 3년 증가율")

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
    # ★ 캐시 키에 shift_days 가 빠져 있었다. R_rebal_shift(±5거래일) 재구축은 signal_date 만
    #   옮기고 rebal 이름은 그대로 두므로, have 집합이 전부 적중해 '옮기지 않은 신호일로 계산한
    #   수급'을 그대로 재사용했다 — F축에서 강건성 검정이 통째로 무효였다(VQF 가 대표 변형인데도).
    _sh = int(globals().get("QVF_REBAL_SHIFT_DAYS", 0) or 0)
    key = f"qvf_flow_netbuy_w{int(window)}" + (f"_s{_sh:+d}" if _sh else "")
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
    out = downcast_q(F.reindex(columns=cols))
    # 어느 창으로 만든 프레임인지 남긴다 — §9-C4 는 사전등록 창(60일)의 값만 읽어야 한다.
    try:
        out.attrs["flow_window"] = int(window)
    except Exception:
        pass
    return out


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
    # ★ axis_F 는 §8.4 강건성(수급창 20/60/120일 민감도)에서도 재호출된다. 전역 하나만 두면
    #   §9-C4 가 '사전등록된 60일 창'이 아니라 '강건성 마지막 실행(120일)'의 값을 읽는다.
    #   창별로 따로 보관하고, 사전등록 창의 값을 C4 전용으로 고정한다.
    _win = int((getattr(flows, "attrs", {}) or {}).get("flow_window", FLOW_WINDOW_DAYS))
    globals().setdefault("FLOW_NONZERO_BY_WINDOW", {})
    FLOW_NONZERO_BY_WINDOW[_win] = nonzero_ratio
    if _win == int(FLOW_WINDOW_DAYS):
        globals()["FLOW_NONZERO_RATIO_PREREG"] = nonzero_ratio

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
FLOW_NONZERO_RATIO_PREREG: float = float("nan")   # §9-C4 전용 — 사전등록 창(60일)의 값
FLOW_NONZERO_BY_WINDOW: Dict[int, float] = {}



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
#  ★★ '해지·철회·취소·기각' 을 '체결·발행·제기' 와 구분해야 한다 ★★
#    공시 제목은 "단일판매·공급계약 해지", "전환사채 발행결정 철회", "소송 제기 취하" 처럼
#    반대 사건도 같은 어간을 쓴다. 구분하지 않으면 공급계약 '해지'가 긍정 하드팩트로,
#    CB 발행 '철회'가 배제 사유로 계상된다 — 두 방향 모두 신호를 뒤집는다.
_DIS_NEG = r"(?!.*(해지|철회|취소|취하|기각|각하|무효|불성립|해제))"
QVF_DISCLOSURE_PATTERNS = {
    # 긍정 하드팩트
    "supply_contract":  _DIS_NEG + r".*(단일판매[·ㆍ・]?\s*공급계약|공급계약\s*체결|수주)",
    # 배제 플래그
    "cb_issue":         _DIS_NEG + r".*전환사채",
    "bw_issue":         _DIS_NEG + r".*신주인수권부사채",
    "major_holder_chg": _DIS_NEG + r".*최대주주\s*(?:변경|변동)",
    "audit_report":     r"감사보고서|감사의견",
    "lawsuit_filed":    _DIS_NEG + r".*소송\s*(?:등의?\s*)?(?:제기|판결)",
    "capital_impair":   r"자본잠식",
}
# 반대 사건도 별도로 세어 표에 남긴다(무시하는 것과 '없었다'는 다르다).
QVF_DISCLOSURE_REVERSALS = r"(해지|철회|취소|취하|기각|각하|무효|불성립|해제)"
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
    _rev = int(D["report_nm"].str.contains(QVF_DISCLOSURE_REVERSALS, regex=True, na=False).sum())
    LOG.ok(f"QVF 공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={v:,}" for k, v in counts.items() if v))
    if _rev:
        LOG.info(f"  그중 '해지·철회·취소·기각' 류 {_rev:,}건은 어떤 이벤트로도 태그하지 "
                 f"않았습니다 — 공급계약 '해지'를 긍정 하드팩트로, CB 발행 '철회'를 배제 "
                 f"사유로 세면 신호가 정반대로 뒤집힙니다.")
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


def _section(text: str, key: str, span: int = 6000,
             probe: Optional[Sequence[str]] = None, max_tries: int = 10) -> str:
    """앵커 섹션을 잘라낸다. ★ '문서 전체의 첫 매치'를 쓰면 안 된다.

    ★★ 이 함수가 조용히 실패하면 §6.1 배제플래그 6종 중 4종과 §7.2 3-A 6개 중 4개가
       '한 번도 발동하지 않는다' ★★
      DART 사업보고서는 맨 앞에 목차가 있고, 앵커 정규식(`감사의견`, `주주에 관한 사항`,
      `특수관계자…거래` 등)은 목차 항목에 그대로 걸린다. 그러면 창 6,000자가 목차와
      회사의 개요를 덮고 실제 섹션에는 닿지 못한다. 파이프라인은 정상 종료하고 진단표에는
      "섹션 발견율 100%" 가 찍히는데, 값은 전부 None 이다. 그리고 '근거 결측이면 배제하지
      않는다' 규칙과 결합해 필터층이 통째로 무력화된다. 더 나쁜 것은 어블레이션이
      "3-A 는 기여가 없다"로 읽히지 "3-A 가 실행되지 않았다"로 읽히지 않는다는 점이다.
    → 앵커의 모든 매치를 돌면서 '목표 숫자·문구가 실제로 잡히는 창'을 채택한다.
    """
    hits = [m.start() for m in _SECTION_RE[key].finditer(text)]
    if not hits:
        return ""
    hits = hits[:max_tries]
    if probe:
        for st in hits:
            w = text[st: st + span]
            if any(re.search(p, w) for p in probe):
                return w
    # 목표를 못 찾았거나 probe 가 없으면: 목차로 추정되는 선두 매치를 피해 마지막 매치를 쓴다.
    #  (목차는 문서 앞부분에 몰려 있고, 실제 본문 섹션은 뒤에 온다)
    st = hits[-1] if len(hits) > 1 else hits[0]
    return text[st: st + span]


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
    """'%' 로 적힌 비율을 소수로 돌려준다.

    ★★ 예전 코드는 `v / 100.0 if v > 1.5 else v` 였다 ★★
      즉 "0.8 %" 를 0.8(=80%)로, "1.5 %" 를 1.5(=150%)로 읽었다. 실무에서 특수관계자
      매출 비중이 1.5% 이하인 종목은 드물지 않다(로그정규 중앙값 4% 가정 시 약 22%).
      그 종목들이 전부 100배로 부풀려져 §7.2 `r_related(>30%)` 에 무조건 걸렸고,
      §6.1 `x_related_up` 의 '상승폭 상위 20%' 임계는 5배 이동해 올바른 플래그 집합과의
      일치율이 5% 수준이었다 — 이 플래그는 특수관계자 위험이 아니라 '비중이 1.5% 미만인가'
      를 세고 있었다. 1.5 라는 컷 자체가 명세에 없는 임의값이다.
    → 패턴이 '%' 기호를 실제로 소비했으면 무조건 /100 한다. 여기 오는 패턴은 전부 그렇다.
    """
    for p in pats:
        m = re.search(p, sect)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
            except Exception:
                continue
            if not np.isfinite(v) or v < 0 or v > 100.0:
                continue                      # 표에서 엉뚱한 숫자를 물었다 — 다음 패턴으로
            return v / 100.0
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
    ip = _section(text, "ip", probe=[r"특허\D{0,12}?[\d,]{1,6}\s*건",
                                     r"특허\s*(?:권|등록|제?\s*\d{2,})"])
    out["patents"] = _count_patents(ip)
    out["sect_ip"] = bool(ip)

    rnd = _section(text, "rnd", probe=[r"연구\s*(?:개발)?\s*인력\D{0,12}?[\d,]{1,6}\s*명",
                                       r"(?:연구원|연구개발\s*인원)\D{0,10}?[\d,]{1,6}\s*명"])
    out["rnd_headcount"] = _rnd_headcount(rnd)
    out["sect_rnd"] = bool(rnd)
    # 정부 R&D 과제: 완료형 사실 문장만 인정
    gov = 0
    for s in _SENT_SPLIT.split(rnd)[:400]:
        if re.search(r"(국책|정부|국가)\s*(과제|연구개발사업|R&D)", s) and is_completed_fact(s):
            gov += 1
    out["gov_rnd_facts"] = float(gov)

    _rel_pats = [r"매출\D{0,20}?([\d,.]+)\s*%", r"비중\D{0,10}?([\d,.]+)\s*%"]
    _relp_pats = [r"매입\D{0,20}?([\d,.]+)\s*%"]
    rel = _section(text, "related", probe=_rel_pats + _relp_pats)
    out["sect_related"] = bool(rel)
    out["related_sales_ratio"] = _ratio_pct(rel, _rel_pats)
    out["related_purchase_ratio"] = _ratio_pct(rel, _relp_pats)

    _cg_pats = [r"지급보증\D{0,24}?([\d,]{3,})", r"우발부채\D{0,24}?([\d,]{3,})"]
    cg = _section(text, "contingent", probe=_cg_pats)
    out["sect_contingent"] = bool(cg)
    out["contingent_amt"] = _amount_krw(cg, _cg_pats)

    _ls_pats = [r"소송\s*가?액\D{0,24}?([\d,]{3,})", r"청구\s*금액\D{0,24}?([\d,]{3,})"]
    ls = _section(text, "lawsuit", probe=_ls_pats + [r"소송.{0,20}제기"])
    out["sect_lawsuit"] = bool(ls)
    out["lawsuit_amt"] = _amount_krw(ls, _ls_pats)
    out["lawsuit_new"] = float(sum(1 for s in _SENT_SPLIT.split(ls)[:300]
                                   if re.search(r"소송.{0,20}제기", s) and is_completed_fact(s)))

    # ★ 핵심감사사항(KAM)은 2018년 이후 상장사 감사보고서의 '필수 기재사항'이지 강조사항이
    #   아니다. 탐지어에 넣으면 정상 기업이 전부 발동한다. §6.1/§7.2 가 요구하는 것은
    #   '강조사항·특기사항'과 '계속기업 불확실성' 이다.
    _au_pats = [r"강조\s*사항", r"특기\s*사항", r"계속기업.{0,20}(불확실|의문|중요한)"]
    au = _section(text, "audit", probe=_au_pats)
    out["sect_audit"] = bool(au)
    _au_hit = next((m for m in (re.search(p, au) for p in _au_pats) if m), None)
    if _au_hit is None:
        out["audit_emphasis"] = 0.0
    else:
        # 부정 판정은 '그 문구 주변'에서 본다. 앵커 기준 고정 400자 창은 문서 레이아웃의
        # 우연에 판정이 좌우된다(목차 유무만으로 결과가 뒤집혔다).
        _near = au[max(0, _au_hit.start() - 120): _au_hit.start() + 300]
        out["audit_emphasis"] = float(not re.search(r"해당\s*사항\s*(?:이)?\s*없|"
                                                    r"기재할\s*사항\s*없|없습니다", _near))

    _hd_pats = [r"최대주주\D{0,40}?([\d,.]+)\s*%", r"소유\s*비율\D{0,10}?([\d,.]+)\s*%"]
    hd = _section(text, "holder", probe=_hd_pats)
    out["sect_holder"] = bool(hd)
    out["major_holder_pct"] = _ratio_pct(hd, _hd_pats)
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
            # ★★ '섹션 발견율' 만 보면 안 된다 ★★
            #   그 표는 "단어가 문서 어딘가에 있었다"를 재는 것이지 "그 섹션을 읽었다"를
            #   재는 것이 아니다. 앵커가 목차에 걸리면 발견율은 100% 인데 값은 전부 None 이고,
            #   그 상태로 §6.1 배제플래그 4종과 §7.2 3-A 4개가 한 번도 발동하지 않는다.
            #   → 필드별 '값 추출 성공률' 을 나란히 싣는다. 이 값이 0 에 가까우면 파서가
            #     죽은 것이지 데이터가 없는 것이 아니다.
            _valcol = {"ip": "patents", "rnd": "rnd_headcount", "related": "related_sales_ratio",
                       "contingent": "contingent_amt", "lawsuit": "lawsuit_amt",
                       "audit": "audit_emphasis", "holder": "major_holder_pct"}
            rows, worst = [], []
            for c, _ in sect:
                nm = c.replace("sect_", "")
                s_rate = 100 * pd.to_numeric(okF[c], errors="coerce").fillna(0).mean()
                vc = _valcol.get(nm)
                if vc and vc in okF.columns:
                    v_rate = 100 * okF[vc].notna().mean()
                    vtxt = f"{v_rate:.1f}%"
                    if s_rate >= 50.0 and v_rate < 5.0:
                        worst.append(nm)
                else:
                    vtxt = "—"
                rows.append([nm, f"{s_rate:.1f}%", vtxt])
            LOG.table(rows, ["섹션", "앵커 발견율", "값 추출 성공률"], ["l", "r", "r"],
                      title="섹션별 발견율 vs 값 추출률 — 앵커만 잡히고 값이 안 나오면 "
                            "목차에 걸린 것이다(필터층이 통째로 무력화된다)")
            if worst:
                LOG.warn(f"앵커는 잡히는데 값이 거의 안 나오는 섹션: {', '.join(worst)}. "
                         f"이 섹션에 의존하는 §6.1 배제플래그·§7.2 3-A 는 사실상 발동하지 "
                         f"않습니다 — 어블레이션의 '기여 없음'을 '규칙이 무의미하다'로 읽지 "
                         f"마십시오. 파서가 실행되지 않은 것입니다.")
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
            #   ★★ 다만 솔직하게 적어 둔다: 이 항목들의 원천은 '사업보고서 본문'이므로
            #      관측 주기가 연 1회다. 따라서 여기의 shift(1) 은 §6.1 문언의 '전분기 대비'가
            #      아니라 사실상 '전년 대비' 다. 분기보고서 주석에는 이 수치가 없으므로
            #      분기 차분 자체가 데이터상 불가능하다 — 근사이며 동일하지 않다.
            #      (연 1회 관측을 억지로 분기로 쪼개면 없는 변화를 만들어내는 것이 되므로
            #       그쪽이 더 큰 위반이다. 이 사실은 §10.1 임의선택 원장에 실린다.)
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
    # ★★ '합'을 그대로 쓰면 커버리지가 곧 점수가 된다 ★★
    #   결측을 0 으로 채우지 않고 합계에서 빼는 것은 옳지만, 그러면 항목을 6개 다 관측한
    #   종목이 2개만 관측한 종목보다 구조적으로 큰 값을 받는다. 즉 ΔNONFIN 이 '증분 이벤트'가
    #   아니라 '데이터를 얼마나 확보했는가' 를 재게 된다 — 대형·공시 성실 종목 쪽으로 기운다.
    #   → 가용 항목 수로 정규화한 평균(=항목당 발생률)을 쓰고, 원합계는 참고용으로 남긴다.
    #   ※ 항목 수가 1~2개뿐인 관측은 평균의 분산이 크므로 개수를 함께 실어 해석하게 한다.
    _sum = d[have].astype("float64").sum(axis=1, skipna=True)
    d["dNONFIN_raw_sum"] = _sum.where(n_ok > 0)
    d["dNONFIN"] = (_sum / n_ok.replace(0, np.nan)).where(n_ok > 0)
    d["dNONFIN_n_items"] = n_ok
    if int((n_ok > 0).sum()):
        _c = np.corrcoef(n_ok[n_ok > 0].to_numpy(dtype=float),
                         d.loc[n_ok > 0, "dNONFIN_raw_sum"].to_numpy(dtype=float))[0, 1]
        LOG.info(f"ΔNONFIN 정규화: 가용 항목 수로 나눈 평균을 사용합니다. "
                 f"(정규화 전 원합계와 가용 항목 수의 상관 {_c:+.3f} — 이 값이 높을수록 "
                 f"'커버리지가 곧 점수'가 되던 정도가 큽니다)")

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
        # ★ 왼쪽 끝은 '직전 분기의 signal_date'. 명목 리밸일로 잡으면
        #   (signal_{i-1}, rebal_{i-1}] 구간이 어느 창에도 속하지 않아, 명목일이 거래일인
        #   분기마다 정확히 1거래일의 공시가 사라진다.
        _p = as_ts(sig_by_rebal.get(reb[i - 1])) if i > 0 else None
        if _p is None:
            _p = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        prev_by_rebal[t] = _p

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
        # ★ 왼쪽 끝은 '직전 분기의 signal_date' 여야 한다. 명목 리밸일(reb[i-1])로 잡으면
        #   signal_date_{i-1} < rebal_{i-1} 이므로 (signal_{i-1}, rebal_{i-1}] 구간이
        #   어느 창에도 속하지 않는다 — 명목일이 거래일인 분기마다 정확히 1거래일의
        #   공시·리포트·목표주가 수정이 조용히 사라진다.
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        if lo is None:
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
        # ★ 왼쪽 끝은 '직전 분기의 signal_date' 여야 한다. 명목 리밸일(reb[i-1])로 잡으면
        #   signal_date_{i-1} < rebal_{i-1} 이므로 (signal_{i-1}, rebal_{i-1}] 구간이
        #   어느 창에도 속하지 않는다 — 명목일이 거래일인 분기마다 정확히 1거래일의
        #   공시·리포트·목표주가 수정이 조용히 사라진다.
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        if lo is None:
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
    # ★ X1 은 §8.2 정의상 "1차만 (2차·3차 없음)" 이다. 여기에 3-A 를 적용하면 X1 이 사실은
    #   '1차 + 3차' 가 되고, §10.4 의 폐기조건 ②(깔때기 기여)와 ③(배제가 MDD 를 개선하는가)이
    #   둘 다 잘못된 기준선과 비교하게 된다. 특히 ③은 X1 에 이미 배제가 들어가 있으므로
    #   '배제의 기여가 없다'는 결론을 구조적으로 유도한다 — 2층 논리를 부당하게 반증한다.
    if use_rule3a and stage != "x1":
        pool = pool & (col(d, "RULE3A_BLOCK").fillna(0) == 0)

    sel = pd.Series(False, index=d.index)
    short_q: List[Tuple[Any, int]] = []
    for _t, g in d.groupby("rebal", observed=True):
        gg = g[pool.loc[g.index]]
        if gg.empty:
            short_q.append((_t, 0))
            continue
        keys = [c for c in (rank_col, f"score1_{variant}", "code") if c in gg.columns]
        asc = [False] * (len(keys) - 1) + [True]
        k = int(min(max(FINAL_N_MIN, min(n_final, FINAL_N_MAX)), len(gg)))
        # ★ §7.4 는 보유 20~40 종목을 규정한다. 풀이 20 미만이면 그 분기는 규정 미달이며,
        #   조용히 진행하면 '집중 포트폴리오의 우연한 성과'가 규정 준수로 보고된다.
        #   여기서 종목을 억지로 채우면(제외 규칙을 되돌려서) 그게 더 큰 위반이므로,
        #   미달 자체는 허용하되 분기와 종목수를 반드시 표면화한다.
        if k < FINAL_N_MIN:
            short_q.append((_t, k))
        sel.loc[gg.sort_values(keys, ascending=asc, kind="mergesort").head(k).index] = True
    if short_q:
        LOG.warn(f"§7.4 보유 하한({FINAL_N_MIN}종목) 미달 분기 {len(short_q)}회 "
                 f"[{stage}/{variant}] — " +
                 ", ".join(f"{as_ts(t):%Y-%m}:{n}종목" for t, n in short_q[:8]) +
                 (" …" if len(short_q) > 8 else "") +
                 ". 규칙을 되돌려 억지로 채우지 않았습니다. 해당 분기의 성과는 "
                 "'규정 범위 밖의 집중 포트폴리오' 로 해석해야 합니다.")
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
                      direction="forward",
                      tolerance=pd.Timedelta(days=int(EXEC_FILL_MAX_LAG_DAYS)))
    out = M.dropna(subset=["px_exec"])[["code", "rebal", "exec_date", "px_date", "px_exec"]]
    out = out.rename(columns={"px_date": "fill_date"})
    # ★ 체결 지연 분포를 감사표로 남긴다. tolerance 를 길게 잡으면 '정지 후 재개장 가격'을
    #   진입가로 쓰게 되는데(정지 복권의 유리한 쪽만 취함), 그 건수를 숨기면 안 된다.
    lag = (as_ts_series(out["fill_date"]) - as_ts_series(out["exec_date"])).dt.days
    LOG.table([["당일 체결(lag=0)", f"{int((lag == 0).sum()):,}"],
               ["1~2일 지연", f"{int(lag.between(1, 2).sum()):,}"],
               [f"3~{int(EXEC_FILL_MAX_LAG_DAYS)}일 지연", f"{int(lag.between(3, int(EXEC_FILL_MAX_LAG_DAYS)).sum()):,}"],
               [f"체결 불가(>{int(EXEC_FILL_MAX_LAG_DAYS)}일 · 매수 후보에서 탈락)",
                f"{int(len(M) - len(out)):,}"]],
              ["체결 지연", "건수"], ["l", "r"],
              title=f"체결가 확보 상황 (허용 지연 {int(EXEC_FILL_MAX_LAG_DAYS)}일) — "
                    f"지연 체결은 정지 해제가를 진입가로 쓰게 되므로 짧게 제한한다")
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

    n_liq = n_zero = n_halt = 0
    if delist:
        dl = {str(k): as_ts(v) for k, v in dict(delist).items()}
        E["_dl"] = as_ts_series(E["code"].map(dl))
        E["_nxt"] = as_ts_series(E["rebal"].map(nxt_rebal))
        in_window = (E["_dl"].notna() & E["_nxt"].notna() &
                     (E["_dl"] > E["exec_date"]) & (E["_dl"] <= E["_nxt"]))
        # ★★ 창 밖 폐지의 뒷문 ★★
        #   종목이 분기 중간에 거래정지되면 (a) 다음 신호일에 종가가 없어 U-1000 에서
        #   탈락하고, (b) 다음 체결일에도 체결가가 없어 fwd_ret 이 결측("missing")이 되며,
        #   (c) 실제 폐지일은 대개 몇 달 뒤라 위 in_window 를 벗어난다. 세 조건이 겹치면
        #   그 포지션은 어느 분기에서도 −100% 를 받지 못하고 '정확히 0%'로 청산된다.
        #   한국 실질심사 정지가 통상 수개월인 이상 이건 예외가 아니라 표준 경로다.
        #   판정 기준을 "창 안에서 폐지됐는가"가 아니라 "이 포지션이 다시 체결 가능해지지
        #   않았고 결국 폐지되었는가"로 바꾼다.
        stuck = (E["_dl"].notna() & (E["_dl"] > E["exec_date"]) &
                 (E["exit_kind"] == "missing") & (~in_window))
        n_halt = int(stuck.sum())
        resolve = in_window | stuck
        if resolve.any():
            ld = as_ts_series(E.loc[resolve, "code"].map(last_px["last_date"]))
            lc = pd.to_numeric(E.loc[resolve, "code"].map(last_px["last_close"]),
                               errors="coerce")
            # ── 정리매매가로 인정하는 조건 (§3.4) ──────────────────────────────────────
            #  ① 가격 시계열이 폐지 시점까지 실제로 닿아 있을 것 (닿지 않으면 그냥 데이터가
            #     끊긴 것이지 정리매매를 관측한 게 아니다)
            #  ② 그 가격이 진입가 대비 '손실'일 것.
            #  ★ ②가 없으면 치명적이다: 소스가 폐지 직전에 종목을 드롭하면 마지막 정상가가
            #    청산가로 둔갑해 '상장폐지 = 0% 손실'이 된다. 그게 정확히 생존자편향의
            #    재유입이며, 계약 Q3 가 이 경로를 잡아낸다. 애매하면 규정대로 −100% 로
            #    보수적으로 처리한다(성과를 과소평가하는 방향 = 편향 통제상 옳은 방향).
            entry = E.loc[resolve, "px_exec"]
            reach = ld.notna() & (ld >= E.loc[resolve, "_dl"] - pd.Timedelta(days=7))
            liq_ret = lc / entry - 1.0
            captured = reach & liq_ret.notna() & (liq_ret < 0)
            E.loc[resolve, "fwd_ret"] = liq_ret.where(captured, -1.0)
            kind = np.where(captured.to_numpy(), "liquidation", "delist_-100%")
            # 정지 후 창 밖 폐지는 별도 유형으로 남겨 감사표에서 바로 보이게 한다.
            kind = np.where(stuck[resolve].to_numpy() & ~captured.to_numpy(),
                            "halt_then_delist", kind)
            E.loc[resolve, "exit_kind"] = kind
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
    if n_halt:
        LOG.info(f"  그중 {n_halt:,}건은 '거래정지 → 다음 분기 이후 폐지'라 예전 규칙(같은 분기 "
                 f"창 안 폐지만 인정)에서는 0% 로 새던 건이다 — halt_then_delist 로 계상했다.")
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
                  label: str = "QVF", delist: Optional[Dict[str, pd.Timestamp]] = None,
                  cost_model: Optional[str] = None) -> dict:
    """분기 리밸런싱 롱온리 백테스트. 비용 전/후를 동시에 산출한다.

    cost_model: "spec"(기본, §8.1 문언 = 증권거래세 + 스프레드/2) | "extended"(+수수료+충격)
    """
    cost_model = str(cost_model or QVF_COST_MODEL).lower()
    need = ["code", "rebal", sel_col]
    d = P[[c for c in P.columns if c in set(need) | {"adtv", "cs_spread", "vol_d", "market",
                                                     "mktcap", "score1_V", "score1_VQ",
                                                     "score1_VQF"}]].copy()
    # ★★ 유동성/스프레드 조회표는 '선정 종목'이 아니라 패널 전체에서 만들어야 한다 ★★
    #   예전에는 선정 종목만 남긴 프레임에서 dict 를 만들었다. 그러면 이번 분기에 '팔고
    #   나가는' 종목은 ADTV 조회가 100% 실패하고, 폴백 `part=1.0`(참여율 100%) 이 걸려
    #   매도 레그 전체가 IMPACT_K = 1000bp 를 맞았다. 총비용의 9할이 이 한 줄이었고,
    #   세 변형 전부를 비용 차감 후 음의 CAGR 로 밀어 §10.4 폐기조건 ①을 자동 발동시켰다.
    _LQ = P[[c for c in ("code", "rebal", "adtv", "cs_spread") if c in P.columns]].copy()
    _LQ["code"] = _LQ["code"].astype(str)
    _LQ["rebal"] = as_ts_series(_LQ["rebal"])
    _adv_by_t: Dict[Any, Dict[str, float]] = {}
    _spr_by_t: Dict[Any, Dict[str, float]] = {}
    for _t, _g in _LQ.groupby("rebal", observed=True):
        _cd = _g["code"].to_numpy()
        if "adtv" in _g.columns:
            _adv_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["adtv"], errors="coerce")))
        if "cs_spread" in _g.columns:
            _spr_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["cs_spread"], errors="coerce")))
    del _LQ
    # 패널에서 아예 사라진 종목(유니버스 이탈)을 위한 '마지막으로 알던 값' 누적표.
    _known_adv: Dict[str, float] = {}
    _known_spr: Dict[str, float] = {}
    n_adv_fallback = 0
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
        # 이번 분기 조회표를 갱신한다(패널에 있는 종목은 최신값, 없으면 마지막으로 알던 값).
        _cur_adv = _adv_by_t.get(as_ts(t), {})
        _cur_spr = _spr_by_t.get(as_ts(t), {})
        for _c, _v in _cur_adv.items():
            if _v is not None and np.isfinite(_v) and _v > 0:
                _known_adv[_c] = float(_v)
        for _c, _v in _cur_spr.items():
            if _v is not None and np.isfinite(_v) and _v > 0:
                _known_spr[_c] = float(_v)
        _med_adv = float(np.median(list(_cur_adv.values()))) if _cur_adv else np.nan
        if not np.isfinite(_med_adv) or _med_adv <= 0:
            _med_adv = float(ADTV_MIN_KRW)
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
                    # 창 안 폐지만 인정하면 '정지 → 다음 분기 이후 폐지'가 0% 로 샌다.
                    # 체결 불가 + 이후 폐지 확인이면 규정대로 −100%(마지막 분기는 제외).
                    fr = -1.0 if (dl is not None and nx0 is not None and as_ts(dl) > te0) else 0.0
                g0 += w * fr
            c0 = 0.0
            if apply_costs and prev_w:
                tax0 = qvf_sell_tax(te0)
                _fee0 = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0
                for c, w in prev_w.items():
                    sp0 = _known_spr.get(str(c), np.nan)
                    sp0 = (float(sp0) if sp0 is not None and np.isfinite(sp0)
                           else SLIPPAGE_FLOOR_BPS / 1e4)
                    sp0 = float(np.clip(sp0, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                    imp0 = 0.0
                    if cost_model == "extended":
                        adv0 = _cur_adv.get(str(c), _known_adv.get(str(c), np.nan))
                        adv0 = float(adv0) if adv0 is not None and np.isfinite(adv0) and adv0 > 0 else _med_adv
                        imp0 = IMPACT_K * math.sqrt(min(1.0, abs(w) * ACCOUNT_KRW / adv0))
                    c0 += abs(w) * (_fee0 + sp0 / 2.0 + imp0 + tax0)
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
            # ★ 세율 구간 경계가 2019-06-03 인데 2019-06-01 은 토요일이라 그 분기 체결일이
            #   정확히 2019-06-03 이다. 명목일로 조회하면 그 한 분기만 구세율(0.30%)이 적용돼
            #   매도 레그 전체에 20bp 를 과다계상한다. 체결일 기준으로 조회한다.
            tax = qvf_sell_tax(exec_of.get(t, t))
            _fee = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                # 매수·매도 모두 패널 전체 조회표를 쓴다(매도 종목도 값을 갖는다).
                sp = _cur_spr.get(c, _known_spr.get(c, np.nan))
                sp = float(sp) if sp is not None and np.isfinite(sp) else SLIPPAGE_FLOOR_BPS / 1e4
                sp = float(np.clip(sp, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                impact = 0.0
                if cost_model == "extended":
                    adv = _cur_adv.get(c, _known_adv.get(c, np.nan))
                    if adv is None or not np.isfinite(adv) or adv <= 0:
                        # 폴백은 '참여율 100%'(=충격 상수 1000bp) 가 아니라 그 분기 횡단면
                        # 중앙 ADTV 다. 조회 실패를 최악의 유동성으로 등치시키면 안 된다.
                        adv = _med_adv
                        n_adv_fallback += 1
                    part = min(1.0, (abs(dw) * ACCOUNT_KRW) / float(adv))
                    impact = IMPACT_K * math.sqrt(part)
                one_way = _fee + sp / 2.0 + impact
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
                #   ★ 판정 기준은 "이번 보유창 안에서 폐지"가 아니라 "다시 체결 가능해지지
                #     않았고(=fr 결측) 이후 폐지되었다"이다. 정지가 수개월 이어지다 폐지되는
                #     한국 실질심사 경로가 예전 창 조건을 표준적으로 빠져나갔다.
                dl = dlmap.get(str(c))
                if dl is not None and nx is not None and as_ts(dl) > t_exec:
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
    if n_adv_fallback:
        LOG.debug(f"[{label}] ADTV 조회 실패 {n_adv_fallback:,}건 — 그 분기 중앙 ADTV 로 대체")
    return {"returns": R, "holdings": pd.DataFrame(holds), "label": label, "scheme": scheme,
            "cost_model": cost_model,
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
           # ★ §9-C2 는 '차이의 유의성'을 요구한다. 차이를 검정하려면 두 실험의 분기수익률
           #   시계열이 필요하므로 여기서 보관한다(요약 통계만으로는 만들 수 없다).
           "R": (R[["rebal", "ret"]].copy() if R is not None and len(R) else None),
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


def paired_diff_test(a: str, b: str, label: Optional[str] = None) -> dict:
    """실험 a − b 의 분기수익률 차이에 대한 HAC t 검정. §9-C2 가 요구하는 '차이의 유의성'.

    ★ 예전에는 C2 가 fdr_pass["VQF-full"] 즉 'VQF 자신의 알파가 0보다 큰가'를 읽었다.
      VQF 와 VQ 는 U-200 중복률이 높아(C3 가 0.85 미만을 요구할 정도) 수익률이 강하게
      상관된다 — 두 시계열의 차이는 각각의 수준보다 훨씬 작은 신호다. 자기 유의성으로
      대체하면 C2 통과가 극적으로 쉬워지고, 수급 축 채택 쪽으로 기운다(상향 드리프트).
    """
    nm = label or f"{a}−{b}(차이)"
    ra = (EXPERIMENTS.get(a) or {}).get("R")
    rb = (EXPERIMENTS.get(b) or {}).get("R")
    if ra is None or rb is None or not len(ra) or not len(rb):
        return {"name": nm, "t": np.nan, "p": np.nan, "n": 0, "mean": np.nan}
    m = ra.merge(rb, on="rebal", how="inner", suffixes=("_a", "_b"))
    d = pd.to_numeric(m["ret_a"], errors="coerce") - pd.to_numeric(m["ret_b"], errors="coerce")
    d = d.dropna().to_numpy(dtype=float)
    if len(d) < 4:
        return {"name": nm, "t": np.nan, "p": np.nan, "n": int(len(d)), "mean": np.nan}
    t, _se = hac_tstat(d)
    return {"name": nm, "t": float(t), "p": _pval_from_t(float(t), len(d)),
            "n": int(len(d)), "mean": float(np.mean(d))}


def report_bh_fdr(names: Sequence[str], q: float = BH_FDR_Q,
                  extra_tests: Optional[Sequence[dict]] = None) -> dict:
    """§8.3 — 주 실험 3개 + 어블레이션 4개를 하나의 패밀리로 묶어 BH-FDR 보정.

    extra_tests: {"name","t","p","n"} 형태의 추가 검정(예: §9-C2 의 VQF−VQ 차이).
                 같은 패밀리에 넣어야 보정이 정직하다.
    """
    for _e in (extra_tests or ()):
        if _e and np.isfinite(_e.get("p", np.nan)):
            EXPERIMENTS[_e["name"]] = {"name": _e["name"], "desc": "§9-C2 차이검정",
                                       "net": {}, "gross": {}, "R": None,
                                       "t": _e["t"], "p": _e["p"], "n": _e["n"]}
    names = list(names) + [e["name"] for e in (extra_tests or ())
                           if e and np.isfinite(e.get("p", np.nan))]
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

    # C2: 그 '차이'가 BH-FDR 보정 후에도 유의 — VQF 자신의 유의성이 아니다.
    _dkey = f"{exp_vqf}−{exp_vq}(차이)"
    if _flow_ok is False:
        c2, c2_d = None, "flow_cov 게이트 미달 — 판정 불가"
    elif fdr_pass is None:
        c2, c2_d = None, "BH-FDR 결과 없음"
    elif _dkey not in fdr_pass:
        c2, c2_d = None, f"차이검정({_dkey})이 패밀리에 없음 — 판정 불가"
    else:
        _dt_rec = EXPERIMENTS.get(_dkey, {})
        c2 = bool(fdr_pass.get(_dkey, False)) and bool(c1)
        c2_d = (f"차이 HAC t {_dt_rec.get('t', float('nan')):+.2f} · "
                f"BH-FDR {'통과' if fdr_pass.get(_dkey) else '기각'}"
                + ("" if c1 else " · C1 미충족이라 차이 자체가 없음"))

    # C3: U-200 중복률 < 0.85
    ov = (cmp_res or {}).get("overlap", {})
    key = next((k for k in ov if set(k.split("~")) == {"VQ", "VQF"}), None)
    o = ov.get(key, np.nan) if key else np.nan
    c3 = bool(np.isfinite(o) and o < 0.85)
    c3_d = f"VQ∩VQF 중복률 {o:.3f}" if np.isfinite(o) else "산출 불가"

    # C4: 수급 비영 관측 비율 ≥ 30% — 반드시 '사전등록 창(60일)' 의 값이어야 한다.
    #     axis_F 는 §8.4 민감도(20/60/120일)에서도 재호출되며 전역을 덮어쓴다. 그대로 읽으면
    #     C4 가 마지막 실행(120일)의 값을 보게 되고, 창이 길수록 비영 비율이 높아지므로
    #     사전등록 기준보다 통과하기 쉬워진다(상향 드리프트).
    nz = globals().get("FLOW_NONZERO_RATIO_PREREG", float("nan"))
    _nz_src = f"사전등록 {int(FLOW_WINDOW_DAYS)}일 창"
    if not np.isfinite(nz):
        nz = globals().get("FLOW_NONZERO_RATIO", float("nan"))
        _nz_src = "창 미상(폴백)"
    c4 = bool(np.isfinite(nz) and nz >= 0.30)
    c4_d = f"비영 관측 {100*nz:.1f}% ({_nz_src})" if np.isfinite(nz) else "산출 불가"

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
    #   ★ 명세는 "미미"라고만 하고 수치를 주지 않는다. 예전 코드의 0.05 는 순수 임의값이었고,
    #     40분기 표본에서 두 Sharpe 차이의 표준오차(≈0.50)의 0.1배에 불과하다 — 참 기여가
    #     0 이어도 절반의 확률로 통과하는, 사실상 판별력 없는 기준이다.
    #     그래서 '차이의 신뢰구간이 0 을 포함하면 미미'라는 통계적 정의로 대체한다.
    #     비교 가능한 검정을 못 만들면 0.05 를 폴백으로 쓰되 그 사실을 근거란에 적는다.
    s_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("Sharpe", np.nan)
    s_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("Sharpe", np.nan)
    _dt2 = paired_diff_test(best, x1_name, label=f"{best}−{x1_name}(깔때기기여)")
    if np.isfinite(_dt2.get("t", np.nan)):
        # 단측(우측) t 가 임계 미만 = 차이가 0 과 구분되지 않음 = 깔때기 기여 미미
        k2 = bool(_dt2["p"] >= 0.10)
        k2_basis = (f"분기수익률 차이 HAC t {_dt2['t']:+.2f} · p {_dt2['p']:.3f} "
                    f"(n={_dt2['n']}) — p ≥ 0.10 이면 '미미'")
    else:
        k2 = bool(np.isfinite(s_full) and np.isfinite(s_x1) and (s_full - s_x1) < 0.05)
        k2_basis = "차이검정 불가 → Sharpe 차 < 0.05 폴백(임의 임계값임을 명시)"
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
        ["② X1(1차만) 과 최우수 full 의 차이가 미미", k2_basis,
         "❗ 충족(폐기)" if k2 else "✔ 미충족"],
        ["③ 배제 컴포넌트가 MDD 개선에 기여 못함",
         f"MDD {100*m_full:+.1f}% vs X1 {100*m_x1:+.1f}%" if np.isfinite(m_full) and np.isfinite(m_x1) else "산출 불가",
         "❗ 충족(폐기)" if k3 else "✔ 미충족"],
    ], ["폐기 조건", "근거 수치", "판정"], ["l", "l", "c"], maxw=48)

    if any(out.values()):
        LOG.warn("§10.4 폐기 조건이 충족되었습니다. 이 결과를 파라미터 조정으로 되살리려 하지 "
                 "마십시오. 위 수치를 그대로 보고하고 중단하는 것이 사전등록의 이행입니다.")
        # ★ '미달 시 행동'을 표에 적어 놓고 아무것도 하지 않으면 그 표는 거짓말이 된다.
        #   예전에는 폐기 판정을 낸 직후 그 폐기된 전략의 실전 편입 종목표를 그대로 출력했다.
        out["_halted"] = bool(STOP_ON_KILL_CRITERIA)
        if STOP_ON_KILL_CRITERIA:
            _hit = [k for k, v in out.items() if v is True and not k.startswith("_")]
            raise KillCriteria(
                "§10.4 사전등록 폐기 조건 충족: " + ", ".join(_hit) + "\n"
                "  사전등록의 이행은 '여기서 멈추는 것' 입니다. 최종 편입 종목표는 출력하지 "
                "않습니다.\n"
                "  수치만 확인하고 계속 보고 싶다면 STOP_ON_KILL_CRITERIA = False 로 두십시오 "
                "— 단, 그 실행 결과를 '전략이 통과했다'고 읽으면 안 됩니다.")
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


def report_discretion_ledger():
    """★ 명세가 침묵하는 곳에서 코드가 택한 것을 전부 드러낸다.

    §10.1 은 '근거를 찾지 못했으면 근거 없음이라고 명시' 하라고 요구한다. 산식이 정해지지
    않은 지점에서 구현이 한쪽을 택했다면 그것은 '데이터가 말한 것'이 아니라 '우리가 정한 것'
    이며, 어느 방향으로 성과를 미는지까지 밝혀야 읽는 사람이 할인해서 볼 수 있다.

    드리프트 방향:
      상향 = 성과를 실제보다 좋게 보이게 하는 방향 (위험을 덜 걸러냄 / 비용을 덜 매김)
      하향 = 성과를 실제보다 나쁘게 보이게 하는 방향 (보수적)
      중립 = 방향성이 없거나 상쇄
    """
    LOG.banner("임의 선택 원장 (§10.1) — 명세가 정하지 않은 지점에서 코드가 택한 것",
               "'데이터가 말한 것'과 '우리가 정한 것'을 구분한다. 드리프트 방향까지 밝힌다.")
    rows = [
        ["EV 정의 = 시총 + 총차입금 − 현금", "명세는 EV/EBIT 만 지정", "중립",
         "차입금 계정이 전부 결측이면 부채총계로 폴백 → EV 과대추정(=밸류 매력 과소평가)"],
        ["EV<0 을 클립하지 않음", "명세 침묵", "중립",
         "순현금>시총 기업이 연속 순서를 유지. 클립하면 최상위에 동점 덩어리가 생겼다"],
        ["분모 부적격의 강제 바닥 = 그 리밸일 횡단면 최소 z", "§5.2 '최하위 순위로 강제'", "중립",
         "셀 최소를 쓰면 폴백 사다리와 어긋나 벌점이 양수(=상점)가 되고 셀 크기에 따라 "
         "벌점이 2배 차이 났다. 선정이 횡단면 단위이므로 벌점도 횡단면 단위로 맞췄다. "
         "임의 상수(-3 등)는 쓰지 않는다"],
        ["분모 = 0 도 '부적격'(3상태 판정)", "§5.2 '음수 EBIT/분모'", "하향(보수적)",
         "safe_div 가 NaN 을 주는 탓에 분모가 정확히 0 인 기업(완전자본잠식 등)이 벌점을 "
         "빠져나가 Z_V 상위에 앉았다. '모름(재무 미보유)'과는 구분해 벌점을 주지 않는다"],
        ["ROIC 유효세율 결측 시 22% 가정", "명세 침묵", "중립",
         "ROIC 는 3년 표준편차로만 쓰이고 전 기업 동일 가정이라 횡단면 효과는 작다"],
        ["Score1 축 결측 시 가중치 재정규화", "§5.5 는 고정 가중치", "중립~보수",
         "0(셀 평균)으로 채우지 않는다. VQF 를 VQ 에 가깝게 만들어 §9 채택을 어렵게 함(보수적)"],
        ["배제플래그: 근거 결측이면 배제하지 않음", "§6.1 '해당 시 즉시 제외'", "⚠ 상향",
         "근거가 없는 종목이 안 걸러진다. 위 배제플래그 표의 '근거 관측 보유율'과 함께 볼 것"],
        ["3-A: 근거 결측이면 제외하지 않음", "§7.2 임계값만 지정", "⚠ 상향",
         "위와 동일. 반대로 하면 재무 결측이 많은 초소형주가 통째로 사라져 선택편향이 된다"],
        ["유동시총 ≈ (발행주식수 − 자기주식) × 주가", "§5.4 '유동주식 시가총액'", "중립",
         "대주주·우리사주 미차감 → 분모 과대 → F축 정규화 강도 약화(신호 희석)"],
        [f"셀 폴백 사다리 상한 = {CELL_LADDER_MAX_LEVEL}", "§5.2/5.3 '섹터중립'", "중립",
         "전 시장(cell_l3)까지 내리면 커버리지가 낮은 섹터만 섹터중립을 잃고 일괄 벌점을 "
         "받는다(실측 −2.5σ). 대분류 섹터에서 멈추고, 거기서도 표본 부족이면 결측 처리"],
        ["ΔNONFIN = 가용 항목 수로 나눈 평균", "§6.1 '항목별 증분 이벤트'", "중립",
         "원합계를 쓰면 항목을 다 관측한 종목이 구조적으로 큰 값을 받아, ΔNONFIN 이 "
         "'증분'이 아니라 '데이터 확보량'을 재게 된다(대형·공시성실 종목 쪽으로 기움)"],
        ["본문 기반 배제플래그의 차분 = 전년 대비", "§6.1 은 '전분기 대비'", "불명",
         "이 항목들의 원천이 사업보고서 본문이라 관측이 연 1회다. 분기보고서 주석에 수치가 "
         "없어 분기 차분이 데이터상 불가능하다. 억지로 쪼개면 없는 변화를 만들게 된다"],
        ["공시 '해지·철회·취소·기각' 은 태그하지 않음", "명세 침묵", "중립",
         "공급계약 '해지'를 긍정 하드팩트로, CB 발행 '철회'를 배제 사유로 세면 신호가 "
         "정반대로 뒤집힌다. 반대 사건 건수는 별도로 로그에 남긴다"],
        ["TONE 라벨 = 횡단면 중앙값 조정 2일 수익", "§6.2 '2일 CAR'", "중립",
         "시장모형 대신 당일 횡단면 조정. 같은 날 정보만 쓰므로 누수가 없다"],
        ["직교화에서 EPS 컨센서스 수정률 제외", "§6.2 는 포함 요구", "불명",
         "과거 시계열 복원 불가. 목표주가 수정률로 일부 대체 — 잔차에 컨센서스 성분이 남을 수 있음"],
        ["Sharpe = (CAGR − rf) / 연변동성", "명세는 Sharpe 만 지정", "하향(보수적)",
         "기하평균(CAGR)을 쓰므로 산술평균 기준 Sharpe 보다 낮게 나온다"],
        [f"기본 비용모형 = '{QVF_COST_MODEL}' (거래세 + 스프레드/2)", "§8.1 문언 그대로", "중립",
         f"수수료 {COMMISSION_BPS}bp 와 제곱근 충격 K={IMPACT_K} 는 명세에 없으므로 기본에서 "
         f"뺐다. 사전등록 판정(§9·§10.4)은 명세 문언 기준이어야 한다. 확장 모형은 §8.4 "
         f"민감도로 병기한다"],
        ["ADTV 조회 실패 시 그 분기 중앙 ADTV 로 대체", "명세 침묵", "혼합",
         "예전엔 조회 실패를 '참여율 100%'(=충격 1000bp)로 등치시켜 매도 레그 전체가 "
         "18배 과다 비용을 맞았다. 중앙값 대체는 과소·과대 어느 쪽으로도 치우치지 않는다"],
        [f"체결 허용 지연 {EXEC_FILL_MAX_LAG_DAYS}일 초과 시 매수 후보 탈락", "명세 침묵", "혼합",
         "길게 잡으면 정지 종목의 '재개장 −60% 가격'을 진입가로 쓰게 된다(상향). 짧게 잡으면 "
         "리밸일에 정지된 종목이 빠진다(상향). 후자는 현실 제약이고 전자는 공짜 복권이라 "
         "짧은 쪽을 골랐다. 체결 지연 분포는 감사표로 출력한다"],
        [f"스프레드 하한 {SLIPPAGE_FLOOR_BPS:.0f}bp / 상한 {SLIPPAGE_CAP_BPS:.0f}bp",
         "명세 침묵", "혼합",
         "하한은 비용↑(보수적), 상한은 최악 종목의 비용↓(상향). CS 추정치 폭주 방지용"],
        [f"가정 계좌 {ACCOUNT_KRW/1e8:.0f}억 (충격 참여율 계산)", "명세 침묵", "혼합",
         "계좌가 클수록 비용↑. 실제 운용규모와 다르면 비용 추정이 그만큼 어긋난다"],
        [f"U-200 크기 {U200_N} · 2차 {SECOND_N} · 최종 {FINAL_N}", "§5.5/6.3/7.4 범위 지정",
         "중립", "각각 명세 범위(200 / 60~80 / 20~40)의 값. 민감도는 §8.4 에서 별도 검정"],
        ["PIT 관리종목 이력 미적용", "§3.3 은 제외 요구", "⚠ 상향",
         "소급 조회 불가. 현재 명단을 과거에 적용하면 그게 미래누수라 적용하지 않았다. "
         "재무기준(자본잠식·연속적자·감사의견)으로 근사하지만 동일하지 않다. "
         "★ 그 근사는 3-A 안에 있으므로 어블레이션 X1~X3 에는 §3.3 3종 제외가 없다"],
        ["§10.4 ② '미미' = 차이의 단측 p ≥ 0.10", "명세는 '미미'라고만 함", "중립",
         "예전 임계 0.05(Sharpe 차)는 40분기 표본에서 차이 표준오차의 0.1배라 판별력이 "
         "사실상 없었다(참 기여가 0 이어도 절반만 발동). 통계적 정의로 바꿨다"],
        ["U-1000 = 게이트 통과 종목 안에서의 하위 1000", "§3.1 '하위 1000종목'", "⚠ 상향",
         "문언적 해석(전 종목 하위 1000 → 게이트)이면 종목수가 크게 줄고 시총 상한도 낮아진다. "
         "게이트를 먼저 통과시키면 1차필터 선택률이 낮아져 Score1 의 분산이 커진다. "
         "U1000_RANK_BEFORE_FILTER=True 로 대안 해석을 실행해 비교할 수 있다"],
    ]
    LOG.table(rows, ["임의 선택", "명세 조항", "드리프트", "영향 / 근거"],
              ["l", "l", "c", "l"], maxw=54)
    up = [r[0] for r in rows if "상향" in r[2]]
    LOG.warn(f"성과를 좋게 보이게 하는 방향의 선택 {len(up)}건: {', '.join(up)}. "
             f"앞의 셋은 모두 '근거가 없는 종목을 배제하지 않는다'는 같은 원칙에서 나온다 — "
             f"반대로 하면 재무·공시 결측이 많은 초소형주가 통째로 사라져 선택편향이 되므로 "
             f"교환관계이며, 어느 쪽도 공짜가 아니다. 마지막 U-1000 해석은 성격이 다르다: "
             f"명세 문언이 두 가지로 읽히는 지점이며, 대안 해석을 실행해 비교하는 것이 "
             f"유일한 정직한 처리다. 근거 보유율 표와 함께 해석하십시오.")
    LOG.info("§10.2 — 1차필터(가치·퀄리티)의 기여는 알파 창출로, 2차 배제플래그와 3-A 의 "
             "기여는 좌측꼬리 제거(MDD·Sortino)로 해석합니다. 배제 컴포넌트가 CAGR 을 크게 "
             "올렸다면 그것이 우연인지 별도 검증이 필요합니다.")


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




# ==========================================================================================
#  빌드 시점에 고정한 소스 조각 — 계약 Q6/Q7/Q12 의 '부재 증명'용.
#  Colab 처럼 셀에 붙여넣어 실행하면 inspect.getsource 가 OSError 로 죽는다.
#  파일 실행/셀 실행 어디서든 같은 검정이 돌도록 여기에 심어 둔다.
# ==========================================================================================
QVF_PINNED_SRC = {
    'score1': 'def score1(P: pd.DataFrame, variant: str) -> pd.Series:\n    """Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F  (§5.5 사전등록 가중치, 튜닝 금지)\n\n    ★ 결측 축 처리: 가중치는 고정이지만 축 자체가 결측인 행이 있다. 결측을 0(=셀 평균)으로\n      채우면 그 종목이 \'평균적인 종목\'으로 둔갑해 분산이 압축되고, 결측이 많은 초소형주가\n      일제히 중앙으로 몰린다. 대신 \'가용 축에 대해 가중치를 재정규화\'하고, 재정규화가\n      일어난 비율을 반드시 로그로 남긴다(수급 축이 사실상 죽어 있으면 여기서 드러난다).\n    """\n    if variant not in VARIANT_W:\n        raise KeyError(f"알 수 없는 변형: {variant} (가능: {list(VARIANT_W)})")\n    wv, wq, wf = VARIANT_W[variant]\n    parts = [(col(P, "Z_V"), wv), (col(P, "Z_Q"), wq), (col(P, "Z_F"), wf)]\n    parts = [(z, w) for z, w in parts if w > 0]\n    num = pd.Series(0.0, index=P.index)\n    den = pd.Series(0.0, index=P.index)\n    for z, w in parts:\n        ok = z.notna()\n        num = num.add((z.fillna(0.0) * w).where(ok, 0.0), fill_value=0.0)\n        den = den.add(pd.Series(np.where(ok, w, 0.0), index=P.index), fill_value=0.0)\n    s = (num / den.where(den > 0)).astype("float32")\n    full_w = sum(w for _z, w in parts)\n    renorm = float(((den > 0) & (den < full_w - 1e-9)).mean())\n    if renorm > 0.01:\n        LOG.info(f"  [{variant}] 축 결측으로 가중치 재정규화된 행 {100*renorm:.1f}% "\n                 f"(0 으로 채우지 않고 가용 축만으로 계산)")\n    return s',
    'build_u200': 'def build_u200(P: pd.DataFrame, variants: Sequence[str] = VARIANTS,\n               n: int = U200_N) -> pd.DataFrame:\n    """각 변형별 Score1 과 U-200 소속 플래그를 패널에 추가한다.\n\n    반환 패널에 추가되는 컬럼:  score1_<V>  ·  u200_<V> (bool)\n    """\n    d = P.copy()\n    for v in variants:\n        d[f"score1_{v}"] = score1(d, v)\n    for v in variants:\n        sc = f"score1_{v}"\n        flag = pd.Series(False, index=d.index)\n        for _t, g in d.groupby("rebal", observed=True):\n            gg = g[g[sc].notna()]\n            if gg.empty:\n                continue\n            flag.loc[_rank_pick(gg, min(n, len(gg)), sc)] = True\n        d[f"u200_{v}"] = flag\n    rows = []\n    for v in variants:\n        cnt = d.groupby("rebal", observed=True)[f"u200_{v}"].sum()\n        rows.append([v, f"{cnt.mean():,.0f}", f"{cnt.min():,.0f}", f"{cnt.max():,.0f}",\n                     f"{int(d[f\'score1_{v}\'].notna().sum()):,}"])\n    LOG.table(rows, ["변형", "U-200 평균", "최소", "최대", "Score1 산출행"],\n              ["c", "r", "r", "r", "r"],\n              title=f"1차 필터 결과 (§5.5 사전등록 가중치 · 목표 상위 {n}종목)")\n    return d',
    'apply_filter2': 'def apply_filter2(P: pd.DataFrame, variant: str, n: int = SECOND_N,\n                  use_tone: bool = True, use_nonfin: bool = True,\n                  use_exclusion: bool = True) -> pd.DataFrame:\n    """U-200(변형별) → 상위 n 종목. 어블레이션(X2/X3)을 위해 구성요소를 켜고 끌 수 있다."""\n    d = P.copy()\n    inu = col(d, f"u200_{variant}").fillna(0).astype(bool) if f"u200_{variant}" in d.columns \\\n        else pd.Series(True, index=d.index)\n\n    zN = pd.Series(0.0, index=d.index, dtype="float32")\n    if use_nonfin:\n        zN = zscore_observed_then_neutral(d, "dNONFIN", inu & col(d, "dNONFIN").notna())\n    zT = pd.Series(0.0, index=d.index, dtype="float32")\n    if use_tone:\n        zT = zscore_observed_then_neutral(d, "dTONE_resid", inu & col(d, "dTONE_resid").notna())\n\n    d[f"score2_{variant}"] = (SCORE2_W_NONFIN * zN + SCORE2_W_TONE * zT).astype("float32")\n    excl = col(d, "EXCLUDED").fillna(0).astype(bool) if use_exclusion else \\\n        pd.Series(False, index=d.index)\n\n    sel = pd.Series(False, index=d.index)\n    for _t, g in d.groupby("rebal", observed=True):\n        gg = g[inu.loc[g.index] & ~excl.loc[g.index]]\n        if gg.empty:\n            continue\n        keys = [f"score2_{variant}", f"score1_{variant}", "code"]\n        keys = [k for k in keys if k in gg.columns]\n        asc = [False] * (len(keys) - 1) + [True]\n        idx = gg.sort_values(keys, ascending=asc, kind="mergesort").head(min(n, len(gg))).index\n        sel.loc[idx] = True\n    d[f"f2_{variant}"] = sel\n    return d',
    'build_final_selection': 'def build_final_selection(P: pd.DataFrame, variant: str, n_final: int = FINAL_N,\n                          use_rule3a: bool = True, stage: str = "full") -> pd.Series:\n    """최종 편입 종목 플래그.\n\n    stage: "full"(1→2→3A) | "x1"(1차만) | "x4"(1→2, 3A 없음)\n    """\n    d = P\n    if stage == "x1":\n        pool = col(d, f"u200_{variant}").fillna(0).astype(bool)\n        rank_col = f"score1_{variant}"\n    else:\n        pool = col(d, f"f2_{variant}").fillna(0).astype(bool)\n        rank_col = f"score2_{variant}"\n    # ★ X1 은 §8.2 정의상 "1차만 (2차·3차 없음)" 이다. 여기에 3-A 를 적용하면 X1 이 사실은\n    #   \'1차 + 3차\' 가 되고, §10.4 의 폐기조건 ②(깔때기 기여)와 ③(배제가 MDD 를 개선하는가)이\n    #   둘 다 잘못된 기준선과 비교하게 된다. 특히 ③은 X1 에 이미 배제가 들어가 있으므로\n    #   \'배제의 기여가 없다\'는 결론을 구조적으로 유도한다 — 2층 논리를 부당하게 반증한다.\n    if use_rule3a and stage != "x1":\n        pool = pool & (col(d, "RULE3A_BLOCK").fillna(0) == 0)\n\n    sel = pd.Series(False, index=d.index)\n    short_q: List[Tuple[Any, int]] = []\n    for _t, g in d.groupby("rebal", observed=True):\n        gg = g[pool.loc[g.index]]\n        if gg.empty:\n            short_q.append((_t, 0))\n            continue\n        keys = [c for c in (rank_col, f"score1_{variant}", "code") if c in gg.columns]\n        asc = [False] * (len(keys) - 1) + [True]\n        k = int(min(max(FINAL_N_MIN, min(n_final, FINAL_N_MAX)), len(gg)))\n        # ★ §7.4 는 보유 20~40 종목을 규정한다. 풀이 20 미만이면 그 분기는 규정 미달이며,\n        #   조용히 진행하면 \'집중 포트폴리오의 우연한 성과\'가 규정 준수로 보고된다.\n        #   여기서 종목을 억지로 채우면(제외 규칙을 되돌려서) 그게 더 큰 위반이므로,\n        #   미달 자체는 허용하되 분기와 종목수를 반드시 표면화한다.\n        if k < FINAL_N_MIN:\n            short_q.append((_t, k))\n        sel.loc[gg.sort_values(keys, ascending=asc, kind="mergesort").head(k).index] = True\n    if short_q:\n        LOG.warn(f"§7.4 보유 하한({FINAL_N_MIN}종목) 미달 분기 {len(short_q)}회 "\n                 f"[{stage}/{variant}] — " +\n                 ", ".join(f"{as_ts(t):%Y-%m}:{n}종목" for t, n in short_q[:8]) +\n                 (" …" if len(short_q) > 8 else "") +\n                 ". 규칙을 되돌려 억지로 채우지 않았습니다. 해당 분기의 성과는 "\n                 "\'규정 범위 밖의 집중 포트폴리오\' 로 해석해야 합니다.")\n    return sel',
    'run_experiment': 'def run_experiment(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str,\n                   u200_n: int = U200_N, final_n: int = FINAL_N, second_n: int = SECOND_N,\n                   use_tone: bool = True, use_nonfin: bool = True,\n                   use_exclusion: bool = True, use_rule3a: bool = True,\n                   stage: str = "full", scheme: str = "equal",\n                   label: str = "", quiet: bool = True) -> dict:\n    """한 실험(변형 × 구성)을 끝까지 돌린다. 패널 재계산 없이 선정 단계만 다시 돈다.\n\n    ★ 실험 7개 + 민감도 수십 개를 매번 데이터 수집부터 돌리면 4시간 예산(§0.5)을 넘긴다.\n      비싼 것(수집·피처)은 한 번만 하고, 싼 것(스코어·선정·체결)만 반복한다.\n    """\n    keep_level = LOG.min\n    if quiet:\n        LOG.min = LOG.LEVELS["WARN"]\n    try:\n        d = build_u200(P, variants=(variant,), n=u200_n)\n        if stage != "x1":\n            d = apply_filter2(d, variant, n=second_n, use_tone=use_tone,\n                              use_nonfin=use_nonfin, use_exclusion=use_exclusion)\n        d["_sel"] = build_final_selection(d, variant, n_final=final_n,\n                                          use_rule3a=use_rule3a, stage=stage)\n        bt = run_qbacktest(d, cal, "_sel", fwd, scheme=scheme, apply_costs=True,\n                           label=label or f"{variant}-{stage}")\n        bt["panel"] = d\n    finally:\n        LOG.min = keep_level\n    return bt',
    'run_qbacktest': 'def run_qbacktest(P: pd.DataFrame, cal: pd.DataFrame, sel_col: str, fwd: pd.DataFrame,\n                  scheme: str = "equal", apply_costs: bool = True,\n                  label: str = "QVF", delist: Optional[Dict[str, pd.Timestamp]] = None,\n                  cost_model: Optional[str] = None) -> dict:\n    """분기 리밸런싱 롱온리 백테스트. 비용 전/후를 동시에 산출한다.\n\n    cost_model: "spec"(기본, §8.1 문언 = 증권거래세 + 스프레드/2) | "extended"(+수수료+충격)\n    """\n    cost_model = str(cost_model or QVF_COST_MODEL).lower()\n    need = ["code", "rebal", sel_col]\n    d = P[[c for c in P.columns if c in set(need) | {"adtv", "cs_spread", "vol_d", "market",\n                                                     "mktcap", "score1_V", "score1_VQ",\n                                                     "score1_VQF"}]].copy()\n    # ★★ 유동성/스프레드 조회표는 \'선정 종목\'이 아니라 패널 전체에서 만들어야 한다 ★★\n    #   예전에는 선정 종목만 남긴 프레임에서 dict 를 만들었다. 그러면 이번 분기에 \'팔고\n    #   나가는\' 종목은 ADTV 조회가 100% 실패하고, 폴백 `part=1.0`(참여율 100%) 이 걸려\n    #   매도 레그 전체가 IMPACT_K = 1000bp 를 맞았다. 총비용의 9할이 이 한 줄이었고,\n    #   세 변형 전부를 비용 차감 후 음의 CAGR 로 밀어 §10.4 폐기조건 ①을 자동 발동시켰다.\n    _LQ = P[[c for c in ("code", "rebal", "adtv", "cs_spread") if c in P.columns]].copy()\n    _LQ["code"] = _LQ["code"].astype(str)\n    _LQ["rebal"] = as_ts_series(_LQ["rebal"])\n    _adv_by_t: Dict[Any, Dict[str, float]] = {}\n    _spr_by_t: Dict[Any, Dict[str, float]] = {}\n    for _t, _g in _LQ.groupby("rebal", observed=True):\n        _cd = _g["code"].to_numpy()\n        if "adtv" in _g.columns:\n            _adv_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["adtv"], errors="coerce")))\n        if "cs_spread" in _g.columns:\n            _spr_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["cs_spread"], errors="coerce")))\n    del _LQ\n    # 패널에서 아예 사라진 종목(유니버스 이탈)을 위한 \'마지막으로 알던 값\' 누적표.\n    _known_adv: Dict[str, float] = {}\n    _known_spr: Dict[str, float] = {}\n    n_adv_fallback = 0\n    d = d[d[sel_col].fillna(False).astype(bool)]\n    F = fwd.set_index(["code", "rebal"])["fwd_ret"] if len(fwd) else pd.Series(dtype="float64")\n\n    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))\n    # ★ 보유구간은 [체결일, 다음 체결일) 이지 [명목일, 다음 명목일) 이 아니다.\n    #   3/1 은 삼일절이라 결코 거래일이 아니고 6/1·12/1 도 주말에 자주 걸린다. 두 구간의\n    #   차이(1~3일의 이음매)에서 폐지된 종목은 \'창 밖\'으로 판정되어 −100% 대신 0% 가 된다.\n    #   즉 분기마다 며칠씩 생존자편향이 새는 뒷문이 열려 있었다.\n    exec_of = {as_ts(r.rebal): as_ts(r.exec_date) for r in cal.itertuples(index=False)}\n    exec_next = {t: (exec_of.get(reb[i + 1]) if i + 1 < len(reb) else None)\n                 for i, t in enumerate(reb)}\n    dlmap = ({str(k): as_ts(v) for k, v in dict(delist).items()} if delist\n             else dict(QVF_DELIST_MAP))\n    prev_w: Dict[str, float] = {}\n    rows, holds = [], []\n    n_missing, n_forced_delist, n_empty_q = 0, 0, 0\n    for t in reb:\n        # 이번 분기 조회표를 갱신한다(패널에 있는 종목은 최신값, 없으면 마지막으로 알던 값).\n        _cur_adv = _adv_by_t.get(as_ts(t), {})\n        _cur_spr = _spr_by_t.get(as_ts(t), {})\n        for _c, _v in _cur_adv.items():\n            if _v is not None and np.isfinite(_v) and _v > 0:\n                _known_adv[_c] = float(_v)\n        for _c, _v in _cur_spr.items():\n            if _v is not None and np.isfinite(_v) and _v > 0:\n                _known_spr[_c] = float(_v)\n        _med_adv = float(np.median(list(_cur_adv.values()))) if _cur_adv else np.nan\n        if not np.isfinite(_med_adv) or _med_adv <= 0:\n            _med_adv = float(ADTV_MIN_KRW)\n        sub = d[d["rebal"] == t].copy()\n        if sub.empty:\n            # ★ 3-A 통과 종목이 0 인 분기는 설계상 발생할 수 있는 정상 결과다(사전등록).\n            #   그런데 예전 코드는 회전율만 기록하고 비용 0, 수익 0 으로 넘겼다 — 전량 청산을\n            #   공짜로 처리하고, 그 분기 보유분의 실제 수익을 통째로 증발시킨 것이다.\n            turn0 = float(sum(abs(v) for v in prev_w.values()))\n            g0 = 0.0\n            nx0 = exec_next.get(t)\n            te0 = exec_of.get(t, t)\n            for c, w in prev_w.items():\n                fr = F.get((c, t), np.nan) if len(F) else np.nan\n                fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan\n                if not np.isfinite(fr):\n                    dl = dlmap.get(str(c))\n                    # 창 안 폐지만 인정하면 \'정지 → 다음 분기 이후 폐지\'가 0% 로 샌다.\n                    # 체결 불가 + 이후 폐지 확인이면 규정대로 −100%(마지막 분기는 제외).\n                    fr = -1.0 if (dl is not None and nx0 is not None and as_ts(dl) > te0) else 0.0\n                g0 += w * fr\n            c0 = 0.0\n            if apply_costs and prev_w:\n                tax0 = qvf_sell_tax(te0)\n                _fee0 = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0\n                for c, w in prev_w.items():\n                    sp0 = _known_spr.get(str(c), np.nan)\n                    sp0 = (float(sp0) if sp0 is not None and np.isfinite(sp0)\n                           else SLIPPAGE_FLOOR_BPS / 1e4)\n                    sp0 = float(np.clip(sp0, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))\n                    imp0 = 0.0\n                    if cost_model == "extended":\n                        adv0 = _cur_adv.get(str(c), _known_adv.get(str(c), np.nan))\n                        adv0 = float(adv0) if adv0 is not None and np.isfinite(adv0) and adv0 > 0 else _med_adv\n                        imp0 = IMPACT_K * math.sqrt(min(1.0, abs(w) * ACCOUNT_KRW / adv0))\n                    c0 += abs(w) * (_fee0 + sp0 / 2.0 + imp0 + tax0)\n            n_empty_q += 1\n            rows.append({"rebal": t, "ret": g0 - c0, "ret_gross": g0, "n": 0,\n                         "turnover": turn0, "cost": c0})\n            prev_w = {}\n            continue\n        sub["w"] = compute_weights(sub, scheme)\n        w_new = dict(zip(sub["code"].astype(str), sub["w"].astype(float)))\n\n        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0))\n                   for c in set(w_new) | set(prev_w))\n        cost = 0.0\n        if apply_costs:\n            # ★ 세율 구간 경계가 2019-06-03 인데 2019-06-01 은 토요일이라 그 분기 체결일이\n            #   정확히 2019-06-03 이다. 명목일로 조회하면 그 한 분기만 구세율(0.30%)이 적용돼\n            #   매도 레그 전체에 20bp 를 과다계상한다. 체결일 기준으로 조회한다.\n            tax = qvf_sell_tax(exec_of.get(t, t))\n            _fee = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0\n            for c in set(w_new) | set(prev_w):\n                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)\n                if abs(dw) < 1e-9:\n                    continue\n                # 매수·매도 모두 패널 전체 조회표를 쓴다(매도 종목도 값을 갖는다).\n                sp = _cur_spr.get(c, _known_spr.get(c, np.nan))\n                sp = float(sp) if sp is not None and np.isfinite(sp) else SLIPPAGE_FLOOR_BPS / 1e4\n                sp = float(np.clip(sp, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))\n                impact = 0.0\n                if cost_model == "extended":\n                    adv = _cur_adv.get(c, _known_adv.get(c, np.nan))\n                    if adv is None or not np.isfinite(adv) or adv <= 0:\n                        # 폴백은 \'참여율 100%\'(=충격 상수 1000bp) 가 아니라 그 분기 횡단면\n                        # 중앙 ADTV 다. 조회 실패를 최악의 유동성으로 등치시키면 안 된다.\n                        adv = _med_adv\n                        n_adv_fallback += 1\n                    part = min(1.0, (abs(dw) * ACCOUNT_KRW) / float(adv))\n                    impact = IMPACT_K * math.sqrt(part)\n                one_way = _fee + sp / 2.0 + impact\n                cost += abs(dw) * one_way + (abs(dw) * tax if dw < 0 else 0.0)\n\n        gross = 0.0\n        nx = exec_next.get(t)\n        t_exec = exec_of.get(t, t)\n        for c, w in w_new.items():\n            fr = F.get((c, t), np.nan) if len(F) else np.nan\n            fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan\n            if not np.isfinite(fr):\n                # ★ 체결가가 없어 수익률을 못 만든 종목을 일괄 0% 로 두면, 폐지 직전에\n                #   소스에서 사라지는 종목이 전부 \'무손실\'이 된다 — 생존자편향의 뒷문이다.\n                #   ★ 판정 기준은 "이번 보유창 안에서 폐지"가 아니라 "다시 체결 가능해지지\n                #     않았고(=fr 결측) 이후 폐지되었다"이다. 정지가 수개월 이어지다 폐지되는\n                #     한국 실질심사 경로가 예전 창 조건을 표준적으로 빠져나갔다.\n                dl = dlmap.get(str(c))\n                if dl is not None and nx is not None and as_ts(dl) > t_exec:\n                    fr = -1.0\n                    n_forced_delist += 1\n                else:\n                    fr = 0.0                  # 마지막 분기 등 — 임의 가정 금지\n                    n_missing += 1\n            gross += w * fr\n            holds.append({"rebal": t, "code": c, "weight": w, "ret": fr})\n        rows.append({"rebal": t, "ret": gross - cost, "ret_gross": gross, "n": len(w_new),\n                     "turnover": turn, "cost": cost})\n        prev_w = w_new\n\n    R = pd.DataFrame(rows)\n    if len(R):\n        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()\n        R["equity_gross"] = (1.0 + R["ret_gross"].fillna(0)).cumprod()\n    if n_forced_delist or n_missing or n_empty_q:\n        LOG.info(f"[{label}] 체결가 결측 보정 — 보유구간 내 폐지 확인 {n_forced_delist:,}건은 "\n                 f"−100% · 그 외 {n_missing:,}건은 0%(마지막 분기 등) · "\n                 f"선정 0종목 분기 {n_empty_q:,}회(청산비용 부과·보유수익 반영)")\n        if n_missing > max(20, 0.02 * len(holds)):\n            LOG.warn(f"0% 로 처리된 보유가 {n_missing:,}건으로 많습니다. 폐지·거래정지가 "\n                     f"\'무손실\'로 새고 있을 수 있습니다 — 위 \'보유 종료 유형\' 표와 함께 보세요.")\n    if n_adv_fallback:\n        LOG.debug(f"[{label}] ADTV 조회 실패 {n_adv_fallback:,}건 — 그 분기 중앙 ADTV 로 대체")\n    return {"returns": R, "holdings": pd.DataFrame(holds), "label": label, "scheme": scheme,\n            "cost_model": cost_model,\n            "n_forced_delist": n_forced_delist, "n_missing": n_missing}',
    'qvf_sell_tax': 'def qvf_sell_tax(dt) -> float:\n    t = as_ts(dt)\n    rate = QVF_TAX_SCHEDULE[0][1]\n    for d, r in QVF_TAX_SCHEDULE:\n        if t >= as_ts(d):\n            rate = r\n    return float(rate)',
    'Vault.put_table': '    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",\n                  domain: str = "table", source: str = "", extra: Optional[dict] = None) -> Optional[str]:\n        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""\n        if df is None:\n            return None\n        path = os.path.join(self.table_dir(scope), f"{name}.parquet")\n        if os.path.exists(path):\n            bak = os.path.join(self.ns[scope], "index", "_backup",\n                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")\n            try:\n                # ★ 대용량 테이블(일봉 패널·DART 원시계정 등)은 백업 전체복사가 드라이브에\n                #   파일 크기의 2배 I/O 를 만든다. 몇 행 추가하려고 수백 MB 를 두 번 쓴다.\n                #   atomic_write_parquet 이 이미 임시파일→교체라 \'쓰다 만 파일\'은 생기지\n                #   않으므로, 큰 파일은 복사를 건너뛰고 직전 1개만 보존한다.\n                _sz = os.path.getsize(path)\n                if _sz > VAULT_BACKUP_MAX_BYTES:\n                    _prev = os.path.join(self.ns[scope], "index", "_backup", f"{name}.prev.parquet")\n                    if not os.path.exists(_prev):\n                        shutil.copy2(path, _prev)           # 최초 1회만 안전본을 남긴다\n                    LOG.debug(f"{name}: {_sz/1e6:,.0f}MB — 회차별 백업 생략(원자적 교체로 보호). "\n                              f"직전 안전본은 _backup/{name}.prev.parquet")\n                else:\n                    shutil.copy2(path, bak)\n            except Exception as e:                          # noqa\n                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "\n                         f"리비전 파일로 저장합니다: {name}")\n                path = os.path.join(self.table_dir(scope),\n                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")\n        try:\n            atomic_write_parquet(df, path)\n        except Exception as e:                              # noqa\n            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")\n            return None\n        self._register(scope, {\n            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",\n            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,\n            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",\n            "source": source, "adopted": False,\n            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),\n                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),\n        })\n        return path',
    'Vault.put_blob': '    def put_blob(self, domain: str, subtype: str, key: str, data: bytes, fmt: str,\n                 source: str = "", event_date=None, knowledge_date=None,\n                 scope: str = "shared", extra: Optional[dict] = None,\n                 uid: Optional[str] = None) -> Optional[str]:\n        """원본 바이트를 내용해시 경로에 저장하고 인덱스에 등록. 같은 내용이면 재기록하지 않는다."""\n        if not data:\n            return None\n        h = sha1_bytes(data)\n        uid = uid or sha1_str(domain, subtype, key, h)\n        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])\n        fn = f"{h}.{fmt.lstrip(\'.\')}"\n        abspath = os.path.join(sub, fn)\n        rel = os.path.relpath(abspath, self.root)\n        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다\n            try:\n                atomic_write_bytes(abspath, data)\n            except Exception as e:                          # noqa\n                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에만 기록하지 않고 건너뜁니다: {key}")\n                return None\n        else:\n            self.stats["blob_dedup_hit"] += 1\n        self._register(scope, {\n            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),\n            "path": rel, "abs_path": abspath, "fmt": fmt, "bytes": len(data), "sha1": h,\n            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),\n            "source": source, "adopted": False,\n            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),\n        })\n        return abspath',
    'Vault.flush': '    def flush(self, scope: Optional[str] = None):\n        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""\n        scopes = [scope] if scope else ["shared", "private"]\n        for sc in scopes:\n            with self._lk:\n                rows, self._pending[sc] = self._pending[sc], []\n            if not rows:\n                continue\n            with self.lock(f"journal_{sc}"):\n                append_jsonl(self.journal(sc), rows)\n            self.stats[f"journal_append:{sc}"] += len(rows)\n            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")',
    'Vault.compact': '    def compact(self, scope: str):\n        """저널 → index.parquet 재생성. 저널은 남기고, 기존 parquet 은 반드시 백업한 뒤 교체."""\n        self.flush(scope)\n        idx = self.load_index(scope, force=True)\n        p = self.idx_parquet(scope)\n        if os.path.exists(p):\n            bak = os.path.join(self.ns[scope], "index", "_backup",\n                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")\n            try:\n                shutil.copy2(p, bak)\n            except Exception as e:                          # noqa\n                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 안전을 위해 컴팩션을 건너뜁니다. "\n                         f"저널({os.path.basename(self.journal(scope))})에 모든 기록이 남아 있으므로 "\n                         f"데이터 유실은 없습니다.")\n                return\n        try:\n            atomic_write_parquet(idx.astype({c: str for c in idx.columns if idx[c].dtype == object}), p)\n            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")\n        except Exception as e:                              # noqa\n            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")',
    'QVFVault': 'class QVFVault(Vault):\n    """Vault + 다중루트 읽기. 쓰기 경로는 부모 그대로(=self.root 전용)라 미러는 절대 안 건드린다."""\n\n    def __init__(self, root: str, mode: str, mirrors: Optional[Sequence[str]] = None,\n                 promote_tables: bool = True):\n        super().__init__(root, mode)\n        # ★ 미러 중복제거는 생성자에서도 한 번 더 한다. qvf_resolve_roots 만 믿으면, 다른 경로로\n        #   생성자를 부르는 순간(테스트·재구성) 같은 트리를 두 번 읽고 인덱스가 두 배가 된다.\n        #   Colab 의 MyDrive / "My Drive" 처럼 문자열은 다른데 실체가 같은 경우가 실제로 있다.\n        _seen = {_same_place_key(self.root)}\n        _keep: List[str] = []\n        _dupes: List[str] = []\n        for m in (mirrors or []):\n            if not m or not os.path.isdir(m):\n                continue\n            k = _same_place_key(m)\n            if k in _seen:\n                _dupes.append(m)\n                continue\n            _seen.add(k)\n            _keep.append(m)\n        if _dupes:\n            LOG.info(f"쓰기루트와 같은 실체를 가리키는 미러 {len(_dupes)}개를 제외했습니다 "\n                     f"(같은 트리를 두 번 읽지 않습니다): {_trunc(\', \'.join(_dupes[:3]), 60)}")\n        self.mirrors: List[str] = _keep\n        self.promote_tables = bool(promote_tables)\n        self._mirror_idx: Dict[str, pd.DataFrame] = {}\n        self.table_src: Dict[str, str] = {}          # 어느 루트가 이 테이블을 줬는가(감사용)\n        self._own_only = False                       # compact 중 미러 행을 배제하기 위한 스위치\n        self._merged: Dict[str, pd.DataFrame] = {}   # 미러 병합 결과 캐시(더티 시 무효화)\n        self._uidpath: Dict[str, Dict[str, Tuple[str, str, str]]] = {}   # uid → 경로\n        # 이번 실행에서 등록한 행. 코어가 self._idx 를 갱신하지 않으므로 조회 때 얹어준다.\n        self._new_rows: Dict[str, List[dict]] = {}\n        self._idxlk = threading.RLock()              # read_parquet_safe 치환 구간 보호용\n\n    # ── 쓰기 경로 구조적 봉인 ----------------------------------------------------------\n    def _wpath(self, path: str) -> str:\n        """쓰기 대상 경로 검증. 쓰기루트 밖이면 예외. 상속받은 어떤 코드도 미러를 못 쓴다.\n        ★ 주석으로 \'도달하지 않는다\'고 쓰는 것과, 도달하면 터지게 만드는 것은 다르다."""\n        rp = os.path.realpath(path)\n        root = os.path.realpath(self.root)\n        if not (rp == root or rp.startswith(root + os.sep)):\n            raise PermissionError(\n                f"[절대 1원칙 위반 차단] 쓰기루트 밖 경로에 쓰려 했습니다: {path}\\n"\n                f"  쓰기루트: {self.root}\\n"\n                f"  미러는 읽기 전용입니다. 이 예외는 버그를 조용히 넘기지 않기 위한 것입니다.")\n        return path\n\n    def journal(self, scope: str) -> str:\n        return self._wpath(super().journal(scope))\n\n    def idx_parquet(self, scope: str) -> str:\n        return self._wpath(super().idx_parquet(scope))\n\n    def blob_dir(self, scope: str) -> str:\n        return self._wpath(super().blob_dir(scope))\n\n    def table_dir(self, scope: str) -> str:\n        return self._wpath(super().table_dir(scope))\n\n    # ── 미러 인덱스 (읽기 전용) ---------------------------------------------------------\n    def _load_mirror_index(self, scope: str) -> pd.DataFrame:\n        key = scope\n        if key in self._mirror_idx:\n            return self._mirror_idx[key]\n        frames: List[pd.DataFrame] = []\n        for mr in self.mirrors:\n            base = os.path.join(mr, GDRIVE_SHARED_NS if scope == "shared" else GDRIVE_PRIVATE_NS)\n            idx_dir = os.path.join(base, "index")\n            if not os.path.isdir(idx_dir):\n                continue\n            got: List[pd.DataFrame] = []\n            d, _st = ro_read_parquet(os.path.join(idx_dir, "index.parquet"))\n            if d is not None and len(d):\n                got.append(d)\n            elif _st not in ("ok", "FileNotFoundError"):\n                LOG.debug(f"미러 인덱스 읽기 건너뜀({_st}): {idx_dir} — 파일은 그대로 둡니다.")\n            jr = read_jsonl(os.path.join(idx_dir, "index.jsonl"))\n            if jr:\n                got.append(pd.DataFrame(jr))\n            if not got:\n                continue\n            allc: List[str] = []\n            for g in got:\n                for c in g.columns:\n                    if c not in allc:\n                        allc.append(c)\n            g2 = pd.concat([g.reindex(columns=allc) for g in got], ignore_index=True)\n            g2["_root"] = mr\n            frames.append(g2)\n            self.stats[f"mirror_index_read:{os.path.basename(mr)}"] += len(g2)\n        if not frames:\n            out = pd.DataFrame(columns=list(INDEX_COLUMNS) + ["_root"])\n        else:\n            allc = []\n            for f in frames:\n                for c in f.columns:\n                    if c not in allc:\n                        allc.append(c)\n            out = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)\n            if "uid" not in out.columns:\n                out["uid"] = np.nan\n            miss = out["uid"].isna() | out["uid"].astype(str).str.strip().isin(("", "nan", "None"))\n            if miss.any():\n                src = [c for c in ("path", "abs_path", "key", "sha1", "_root") if c in out.columns]\n                out.loc[miss, "uid"] = [\n                    sha1_str("mirror", i, *[str(out.iloc[i].get(c, "")) for c in src])\n                    for i in np.where(miss.to_numpy())[0]]\n            out["uid"] = out["uid"].astype(str)\n            out = out.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)\n        self._mirror_idx[key] = out\n        return out\n\n    # ★★ 같은 실행에서 저장한 것을 같은 실행에서 반드시 되찾을 수 있어야 한다 ★★\n    #   코어 Vault._register 는 _pending 과 _uidset 만 갱신하고 self._idx 는 손대지 않는다.\n    #   그리고 코어 load_index 는 force 가 아니면 self._idx 의 캐시본을 그대로 돌려준다.\n    #   그래서 "put_blob → flush → get_blob" 이 같은 실행 안에서 None 을 돌려주는 구멍이\n    #   있었다. 콜드런 1회차에 방금 내려받은 PDF 가 TONE 입력에서 통째로 빠지고, 2회차부터\n    #   갑자기 정상이 되는 형태로 나타난다 — \'본문이 짧아 제외\'와 구분되지 않는다.\n    #   저장↔재호출 연결은 이 전략의 절대 1원칙이므로, 등록분을 인덱스에 반드시 얹는다.\n    def _pending_frame(self, scope: str) -> Optional[pd.DataFrame]:\n        with self._lk:\n            rows = list(self._new_rows.get(scope, ()))\n        if not rows:\n            return None\n        f = pd.DataFrame(rows)\n        if "uid" in f.columns:\n            f["uid"] = f["uid"].astype(str)\n        f["_root"] = self.root\n        return f\n\n    def _with_new_rows(self, scope: str, own: pd.DataFrame) -> pd.DataFrame:\n        f = self._pending_frame(scope)\n        if f is None:\n            return own\n        o = own.copy()\n        if "_root" not in o.columns:\n            o["_root"] = self.root\n        allc: List[str] = []\n        for g in (o, f):\n            for c in g.columns:\n                if c not in allc:\n                    allc.append(c)\n        out = pd.concat([o.reindex(columns=allc), f.reindex(columns=allc)], ignore_index=True)\n        if "uid" in out.columns:\n            out["uid"] = out["uid"].astype(str)\n            # 저널을 이미 다시 읽었다면 같은 uid 가 양쪽에 있다 — 먼저 온 쪽(저널)을 남긴다.\n            out = out.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)\n        return out\n\n    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:\n        if force:\n            # ★ force=True 가 오히려 복구를 막던 버그: 파생 캐시를 같이 비우지 않으면\n            #   스테일 인덱스로 만들어진 빈 uid→경로 사전이 그대로 남아 get_blob 이\n            #   영구히 None 을 돌려준다.\n            with self._lk:\n                self._merged.pop(scope, None)\n                self._uidpath.pop(scope, None)\n                self._mirror_idx.pop(scope, None)\n        with self._idxlk:\n            with _suppress_corrupt_rename():\n                own = super().load_index(scope, force=force)\n        own = self._with_new_rows(scope, own)\n        if self._own_only:\n            with self._lk:\n                self._uidset[scope] = set(own["uid"].astype(str).tolist()) if len(own) else set()\n            return own\n        if not force:\n            cached = self._merged.get(scope)\n            if cached is not None:\n                return cached\n        mir = self._load_mirror_index(scope)\n        if mir.empty:\n            self._merged[scope] = own\n            return own\n        o = own.copy()\n        if "_root" not in o.columns:\n            o["_root"] = self.root\n        else:\n            o["_root"] = o["_root"].fillna(self.root)\n        allc: List[str] = []\n        for f in (o, mir):\n            for c in f.columns:\n                if c not in allc:\n                    allc.append(c)\n        merged = pd.concat([o.reindex(columns=allc), mir.reindex(columns=allc)], ignore_index=True)\n        # 쓰기루트(own)를 뒤에 두지 않는다 — 같은 uid 면 \'쓰기루트 우선\'이어야 하므로\n        # keep="first" 로 own 이 이긴다.\n        merged = merged.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)\n        with self._lk:\n            self._idx[scope] = merged\n            self._uidset[scope] = set(merged["uid"].astype(str).tolist())\n            self._merged[scope] = merged\n        return merged\n\n    # ── 다중루트 읽기 -------------------------------------------------------------------\n    def get_table(self, name: str, scope: str = "shared",\n                  max_age_days: Optional[float] = None) -> Optional[pd.DataFrame]:\n        d = super().get_table(name, scope=scope, max_age_days=max_age_days)\n        if d is not None:\n            self.table_src[name] = self.root\n            return d\n        for mr in self.mirrors:\n            for sc in (scope, "private" if scope == "shared" else "shared"):\n                ns = GDRIVE_SHARED_NS if sc == "shared" else GDRIVE_PRIVATE_NS\n                p = os.path.join(mr, ns, "table", f"{name}.parquet")\n                if not os.path.exists(p):\n                    continue\n                if max_age_days is not None:\n                    if (time.time() - os.path.getmtime(p)) / 86400.0 > max_age_days:\n                        continue\n                dd, _st = ro_read_parquet(p)\n                if dd is None or not len(dd):\n                    if _st not in ("ok", "FileNotFoundError"):\n                        LOG.debug(f"미러 테이블 읽기 건너뜀({_st}): {p} — 파일은 그대로 둡니다.")\n                    continue\n                self.table_src[name] = mr\n                self.stats[f"mirror_table_hit:{name}"] += 1\n                LOG.info(f"로컬/미러 캐시 적중: {name} ({len(dd):,}행) ← {mr}")\n                PIPE.io("IN", "MIRROR", f"table:{name}", dd, source=mr)\n                if sc != scope:\n                    LOG.warn(f"  ※ 요청 스코프는 \'{scope}\' 인데 \'{sc}\' 스코프의 동명 테이블을 "\n                             f"채택했습니다: {name} — 이름이 겹치는 전략이 있는지 확인하세요.")\n                    self.table_src[name] = f"{mr}#{sc}"\n                # ★★ 승격은 \'드라이브에 파일이 실재하지 않을 때만\' ★★\n                #   super().get_table 은 파일이 있어도 max_age_days 를 넘기면 None 을 준다.\n                #   그 None 을 \'드라이브에 없음\'으로 읽으면, 로컬 미러(복사·동기화로 mtime 만\n                #   최신이고 내용은 과거)가 드라이브의 최신본을 덮어쓴다. dart_corpcode 처럼\n                #   전 파이프라인의 종목 연결 축이 3분의 1로 줄어드는 사고가 실제로 난다.\n                _own_p = os.path.join(self.table_dir(scope), f"{name}.parquet")\n                if self.promote_tables and not os.path.exists(_own_p):\n                    try:\n                        self.put_table(name, dd, scope=scope, domain="table",\n                                       source=f"promoted_from_mirror:{os.path.basename(mr)}")\n                        LOG.ok(f"  → 구글드라이브로 승격 복사 완료 (원본은 그대로 둡니다): {name}")\n                    except Exception as e:                       # noqa\n                        LOG.warn(f"  → 드라이브 승격 실패({type(e).__name__}) — 읽기만 하고 진행합니다.")\n                return dd\n        return None\n\n    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:\n        rows = self.lookup(scope, uid=uid)\n        if rows.empty:\n            return None\n        for _, r in rows.iterrows():\n            base = str(r.get("_root") or self.root)\n            cands = [r.get("abs_path")]\n            rel = str(r.get("path") or "")\n            if rel:\n                cands.append(os.path.join(base, rel))\n                if base != self.root:\n                    cands.append(os.path.join(self.root, rel))\n            for cand in cands:\n                try:\n                    if cand and isinstance(cand, str) and os.path.exists(cand):\n                        return open(cand, "rb").read()\n                except Exception:\n                    continue\n        return None\n\n    # ── O(1) 인덱스 계층 -----------------------------------------------------------------\n    #  ★ 공용 Vault 는 규모를 가정하지 않고 짜여 있다. 30만 행 인덱스 + 수만 건 blob 조회에서는\n    #    그 가정이 그대로 병목이 된다. 세 곳을 상수시간으로 내린다(코어는 손대지 않는다):\n    #      ① has()      : _pending 리스트 선형탐색 → uid 집합 조회. 신규 uid n 건이면 O(n²)→O(n)\n    #      ② load_index : 호출마다 미러 재병합 → 더티 플래그 캐시\n    #      ③ get_blob   : 전 인덱스 불리언 마스크 → uid→경로 사전\n    def _register(self, scope: str, rec: dict):\n        super()._register(scope, rec)\n        with self._lk:\n            self._new_rows.setdefault(scope, []).append(dict(rec))\n        self._merged.pop(scope, None)\n        self._uidpath.pop(scope, None)\n\n    def flush(self, scope: Optional[str] = None):\n        """코어와 달리 append 가 성공한 뒤에 pending 을 비운다.\n\n        ★ 코어는 `rows, self._pending[sc] = self._pending[sc], []` 로 먼저 비우고 append 한다.\n          드라이브 용량 초과·네트워크 끊김으로 append 가 던지면 그 행들은 영구 소실되고,\n          blob 파일은 이미 쓰여 있으므로 \'인덱스 없는 고아 blob\' 이 남는다. 삭제 API 가\n          없으므로 영구히 남고, 그 세션 내내 has() 는 True 라 재수집도 되지 않는다.\n        """\n        scopes = [scope] if scope else ["shared", "private"]\n        for sc in scopes:\n            with self._lk:\n                rows = list(self._pending.get(sc, ()))\n            if not rows:\n                continue\n            with self.lock(f"journal_{sc}"):\n                append_jsonl(self.journal(sc), rows)     # 실패하면 여기서 예외 — pending 은 그대로\n            with self._lk:\n                del self._pending[sc][:len(rows)]\n            self.stats[f"journal_append:{sc}"] += len(rows)\n            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")\n\n    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,\n              source: str = "", event_date=None, knowledge_date=None,\n              scope: str = "shared", extra: Optional[dict] = None,\n              size: Optional[int] = None) -> Optional[str]:\n        """size 를 알고 있으면 getsize() 를 생략한다 — 드라이브 FUSE 왕복 1회/파일 절감.\n\n        ★ uid 는 코어와 동일한 sha1_str("adopt", domain, subtype, abspath, size) 여야 한다.\n          계약 Q7 이 \'코어 경로와 size 지정 경로의 uid 가 같은가\'를 회귀로 고정한다.\n        """\n        if size is None:\n            return super().adopt(abs_path, domain, subtype, key, source=source,\n                                 event_date=event_date, knowledge_date=knowledge_date,\n                                 scope=scope, extra=extra)\n        sz = int(size)\n        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)\n        if self.has(scope, uid):\n            return uid\n        self._register(scope, {\n            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),\n            "path": abs_path, "abs_path": abs_path,\n            "fmt": os.path.splitext(abs_path)[1].lstrip("."),\n            "bytes": sz, "sha1": "", "source": source or "adopted",\n            "event_date": str(as_ts(event_date) or ""),\n            "knowledge_date": str(as_ts(knowledge_date) or ""),\n            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),\n        })\n        self.stats["adopted"] += 1\n        return uid\n\n    def has(self, scope: str, uid: str) -> bool:\n        if scope not in self._uidset:\n            self.load_index(scope)\n        with self._lk:\n            # _register 가 이미 _uidset 에 넣으므로 pending 을 따로 훑을 필요가 없다.\n            return str(uid) in self._uidset.get(scope, set())\n\n    def _uid_path_map(self, scope: str) -> Dict[str, Tuple[str, str, str]]:\n        m = self._uidpath.get(scope)\n        if m is not None:\n            return m\n        idx = self.load_index(scope)\n        m = {}\n        if len(idx):\n            root_col = (idx["_root"].astype(str) if "_root" in idx.columns\n                        else pd.Series([self.root] * len(idx), index=idx.index))\n            for u, ap, rel, rt in zip(idx["uid"].astype(str),\n                                      idx.get("abs_path", pd.Series([""] * len(idx))).astype(str),\n                                      idx.get("path", pd.Series([""] * len(idx))).astype(str),\n                                      root_col):\n                m[u] = (ap, rel, rt if rt and rt != "nan" else self.root)\n        self._uidpath[scope] = m\n        return m\n\n    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:\n        ent = self._uid_path_map(scope).get(str(uid))\n        if ent is None:\n            return None\n        ap, rel, base = ent\n        cands = [ap]\n        if rel and rel not in ("", "nan"):\n            cands.append(os.path.join(base, rel))\n            if base != self.root:\n                cands.append(os.path.join(self.root, rel))\n        for c in cands:\n            try:\n                if c and c not in ("", "nan") and os.path.exists(c):\n                    return open(c, "rb").read()\n            except Exception:\n                continue\n        return None\n\n    # ── 기존 리포트 폴더 흡수 (드라이브 FUSE 안전판) --------------------------------------\n    # ★★ 이름으로 프루닝하면 사용자의 폴더를 먹는다 ★★\n    #   예전에는 {"blob","table","index","_backup","_locks","reports"} 를 \'이름\'으로 잘랐다.\n    #   그러면 트리 어디에 있든 그 이름이면 하위 전체가 사라진다 — GDRIVE_ADOPT_DIRS 기본값에\n    #   `reports` 가 있는데 `research/reports/`, `archive/reports/` 는 리포트를 모아둔\n    #   폴더에서 극히 흔한 이름이다. 실측으로 8개 중 7개가 통째로 누락됐고, 누락 사실은\n    #   어디에도 남지 않았다. 그래서 \'이름\'이 아니라 \'구조\'로 판정한다.\n    _HEX2_RE = re.compile(r"^[0-9a-f]{2}$")\n    _HASH_FANOUT_MIN = 32          # 2자리 16진수 하위폴더가 이만큼이면 내용해시 샤드 트리\n    _MANAGED_NS_CHILD = {"index", "blob", "table", "_backup", "_locks"}\n    _SKIP_DIRNAMES = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules",\n                      ".cache", ".Trash", "$RECYCLE.BIN", "System Volume Information"}\n\n    def _is_cache_ns(self, path: str) -> bool:\n        """`<X>/_shared/blob` 처럼 \'캐시 네임스페이스 바로 아래의 관리 폴더\'인가.\n\n        이름만 보는 것이 아니라 부모가 캐시 네임스페이스인지까지 본다. 사용자의\n        `research/reports`, `archive/table` 은 여기에 걸리지 않는다.\n        """\n        parts = [p for p in os.path.normpath(str(path)).replace("\\\\", "/").split("/") if p]\n        for i in range(len(parts) - 1):\n            if parts[i] in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS) and \\\n                    parts[i + 1] in self._MANAGED_NS_CHILD:\n                return True\n        return False\n\n    def _managed_keys(self) -> set:\n        """쓰기루트·미러의 관리 트리. 여기는 이미 인덱스에 있으므로 절대 걷지 않는다."""\n        out = set()\n        for r in [self.root] + list(self.mirrors):\n            out.add(_same_place_key(r))\n            for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):\n                p = os.path.join(r, ns)\n                if os.path.isdir(p):\n                    out.add(_same_place_key(p))\n        return out\n\n    def adopt_scan(self, dirs: Sequence[str], max_files: int = None,\n                   max_seconds: float = None) -> pd.DataFrame:\n        """기존에 모아둔 리포트를 \'등록만\' 한다. 이동·개명·삭제 없음.\n\n        ★ 사용자의 실제 Colab 실행이 여기서 멈췄다. 원인은 하나가 아니라 넷이 겹친 것이었다:\n          ① 캐시 루트 자신을 스캔했다 → blob 은 내용해시 2단이라 최대 65,536개 디렉터리이고\n             드라이브 FUSE 에서 listdir 한 번이 50~200ms 다. 열거만 1~2시간인데,\n             그 파일들은 \'이미 인덱스에 있는 것\'이라 전부 무의미한 작업이다.\n          ② /content/drive/MyDrive 와 /content/drive/My Drive 를 중복 스캔했다.\n          ③ 파일마다 getsize() 로 FUSE 왕복이 한 번 더 붙었다.\n          ④ 코어의 max_files 상한은 안쪽 for 만 끊고 os.walk 는 계속 돌았다.\n        → 관리 트리 프루닝 + 실체 기준 중복제거 + scandir 1회 stat + \'진짜\' 상한 +\n          디렉터리 mtime 체크포인트(재실행 시 이어받기) + 진행률 출력.\n        """\n        max_files = int(ADOPT_SCAN_MAX_FILES if max_files is None else max_files)\n        max_seconds = float(ADOPT_SCAN_MAX_SECONDS if max_seconds is None else max_seconds)\n        if not ADOPT_SCAN_ENABLED:\n            LOG.info("ADOPT_SCAN_ENABLED=False — 기존 리포트 폴더 스캔을 건너뜁니다 "\n                     "(인덱스에 이미 등록된 자료는 그대로 사용됩니다).")\n            return pd.DataFrame(columns=["abs_path", "kind", "name"])\n\n        managed = self._managed_keys()\n        roots, skipped_missing, skipped_managed = [], [], []\n        seen_keys = set()\n        for d in dirs:\n            if not d:\n                continue\n            e = _expand(d)\n            if not os.path.isdir(e):\n                skipped_missing.append(d)\n                continue\n            k = _same_place_key(e)\n            if k in managed:\n                skipped_managed.append(e)\n                continue\n            if k in seen_keys:\n                continue\n            seen_keys.add(k)\n            roots.append(e)\n\n        if skipped_missing:\n            LOG.info(f"존재하지 않는 스캔 경로 {len(skipped_missing)}개는 건너뜁니다"\n                     f"(로컬 D: 가 없는 환경에서는 정상): "\n                     f"{_trunc(\', \'.join(skipped_missing[:4]), 70)}")\n        if skipped_managed:\n            LOG.info(f"캐시 관리 트리 {len(skipped_managed)}개는 스캔 대상에서 제외합니다 — "\n                     f"이미 인덱스에 있고, blob 은 내용해시 2단 구조라 드라이브에서 열거만 "\n                     f"수 시간이 걸립니다.")\n        if not roots:\n            LOG.info("스캔할 외부 리포트 폴더가 없습니다. (기존 인덱스는 그대로 사용됩니다)")\n            return pd.DataFrame(columns=["abs_path", "kind", "name"])\n\n        # ── 디렉터리 체크포인트 ──────────────────────────────────────────────────────────\n        #  ★ 예전 체크포인트는 mtime 만 저장하고, 무변경이어도 scandir 는 그대로 했다.\n        #    아끼는 것이 파일 stat 뿐이라 \'디렉터리 열거 절감률 0.0%\' 였고, FUSE 왕복이\n        #    비용의 전부인 드라이브에서는 이어받기가 회차당 +332 → +47 → +7 로 감쇠해\n        #    사실상 수렴하지 않았다. 이제 \'완주한 디렉터리의 하위폴더 목록\'까지 저장해서,\n        #    mtime 이 같으면 scandir 자체를 생략하고 저장된 하위폴더로 바로 내려간다.\n        #  ★ 그리고 상한으로 중도 탈출한 디렉터리는 체크포인트에 넣지 않는다. 예전에는\n        #    scandir \'전에\' 기록해서, 상한에 걸려 10건만 읽은 디렉터리의 나머지 40건이\n        #    (트리가 바뀌지 않는 한) 영구히 등록되지 않았다.\n        ckpt: Dict[str, Tuple[float, List[str]]] = {}\n        cdf = self.get_table("qvf_adopt_scan_state", scope="private")\n        if cdf is not None and len(cdf):\n            try:\n                _mt = pd.to_numeric(cdf["mtime"], errors="coerce").fillna(-1.0)\n                _sd = (cdf["subdirs"].astype(str) if "subdirs" in cdf.columns\n                       else pd.Series(["[]"] * len(cdf)))\n                for _p, _m, _s in zip(cdf["dirpath"].astype(str), _mt, _sd):\n                    try:\n                        kids = json.loads(_s) if _s and _s != "nan" else []\n                    except Exception:\n                        kids = []\n                    ckpt[_p] = (float(_m), list(kids) if isinstance(kids, list) else [])\n            except Exception:\n                ckpt = {}\n            LOG.info(f"이전 스캔 체크포인트 {len(ckpt):,}개 디렉터리 — 변경되지 않은 폴더는 "\n                     f"열거(scandir) 자체를 생략하고 저장된 하위폴더로 바로 내려갑니다.")\n\n        t0 = time.time()\n        found: List[dict] = []\n        new_ckpt: Dict[str, Tuple[float, List[str]]] = dict(ckpt)\n        n_files = n_dirs = n_skipped_dirs = n_ckpt_hit = 0\n        skipped_samples: List[str] = []\n        stopped = ""\n\n        for root in roots:\n            if stopped:\n                break\n            LOG.info(f"기존 리포트 폴더 스캔: {root}")\n            stack = [root]\n            while stack:\n                if time.time() - t0 > max_seconds:\n                    stopped = f"시간 예산 {max_seconds:.0f}초 초과"\n                    break\n                if n_files >= max_files:\n                    stopped = f"파일 상한 {max_files:,}건 도달"\n                    break\n                cur = stack.pop()\n                try:\n                    st_m = os.stat(cur).st_mtime\n                except Exception:\n                    continue\n                n_dirs += 1\n                if n_dirs % 200 == 0:\n                    LOG.info(f"  … 디렉터리 {n_dirs:,} · 파일 {n_files:,} · "\n                             f"{time.time()-t0:.0f}초 경과")\n                prev = ckpt.get(cur)\n                if prev is not None and abs(prev[0] - st_m) < 1e-6:\n                    # 무변경 + 이전에 \'완주\' 한 디렉터리 → 열거를 통째로 생략한다.\n                    n_ckpt_hit += 1\n                    stack.extend(prev[1])\n                    continue\n                completed = True\n                subdirs: List[str] = []\n                hex2 = 0\n                try:\n                    with os.scandir(cur) as it:\n                        for ent in it:\n                            try:\n                                if ent.is_dir(follow_symlinks=False):\n                                    nm = ent.name\n                                    if nm.startswith(".") or nm in self._SKIP_DIRNAMES:\n                                        n_skipped_dirs += 1\n                                        continue\n                                    if self._is_cache_ns(ent.path):\n                                        n_skipped_dirs += 1\n                                        if len(skipped_samples) < 6:\n                                            skipped_samples.append(ent.path)\n                                        continue\n                                    if self._HEX2_RE.match(nm):\n                                        hex2 += 1\n                                        if hex2 >= self._HASH_FANOUT_MIN:\n                                            # 내용해시 샤드 트리(최대 65,536 디렉터리). 여기는\n                                            # 남의 캐시 blob 이지 사용자의 리포트가 아니다.\n                                            n_skipped_dirs += 1\n                                            if len(skipped_samples) < 6:\n                                                skipped_samples.append(ent.path)\n                                            continue\n                                    if _same_place_key(ent.path) in managed:\n                                        n_skipped_dirs += 1\n                                        continue\n                                    subdirs.append(ent.path)\n                                    stack.append(ent.path)\n                                    continue\n                                # ★ 예산 검사가 디렉터리 경계에만 있으면 예산이 상한이 아니다.\n                                #   파일 1만 개짜리 디렉터리 하나가 예산을 통째로 넘긴다.\n                                if (n_files & 0x3FF) == 0 and time.time() - t0 > max_seconds:\n                                    completed = False\n                                    stopped = f"시간 예산 {max_seconds:.0f}초 초과"\n                                    break\n                                low = ent.name.lower()\n                                if low.endswith(".pdf"):\n                                    kind = "report_pdf"\n                                elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \\\n                                        any(t in low for t in\n                                            ("report", "consensus", "research", "analyst",\n                                             "hankyung", "naver", "dart", "krx", "price",\n                                             "ohlcv", "universe", "fnltt")):\n                                    kind = "table_like"\n                                else:\n                                    continue\n                                try:\n                                    sz = ent.stat(follow_symlinks=False).st_size\n                                except Exception:\n                                    sz = -1\n                                found.append({"abs_path": ent.path, "kind": kind,\n                                              "name": ent.name, "dir": cur, "bytes": sz})\n                                n_files += 1\n                                if n_files >= max_files:\n                                    completed = False\n                                    break\n                            except Exception:\n                                continue\n                except Exception as e:                              # noqa\n                    completed = False\n                    LOG.warn(f"  디렉터리 열람 실패({type(e).__name__}) — 이 하위 트리는 "\n                             f"이번 실행에서 등록되지 않습니다: {cur}")\n                if completed:\n                    # 완주한 디렉터리만 체크포인트에 남긴다(중도 탈출분은 다음 실행에서 재시도).\n                    new_ckpt[cur] = (st_m, subdirs)\n\n        dur = time.time() - t0\n        if not found:\n            LOG.info(f"새로 등록할 리포트 파일이 없습니다 (디렉터리 {n_dirs:,}개 · {dur:.1f}초"\n                     + (f" · {stopped}" if stopped else "") + "). "\n                     f"이미 인덱스에 있는 자료는 그대로 사용됩니다.")\n        else:\n            df = pd.DataFrame(found)\n            for r in df.itertuples(index=False):\n                m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)\n                ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None\n                # scandir 에서 이미 크기를 알고 있다 — getsize() 를 또 부르면 드라이브 FUSE\n                # 왕복이 파일마다 한 번씩 더 붙는다(리포트 3만 건이면 2.6~6.4분).\n                self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",\n                           subtype=r.kind, key=r.name, source="preexisting_drive_cache",\n                           event_date=ed, knowledge_date=ed, scope="shared",\n                           extra={"dir": r.dir},\n                           size=(int(r.bytes) if int(r.bytes) >= 0 else None))\n            self.flush("shared")\n            LOG.ok(f"기존 리포트 {len(df):,}건을 공용 인덱스에 \'참조 등록\'했습니다 "\n                   f"(파일은 원위치 그대로, 이동·삭제 없음) — "\n                   f"디렉터리 {n_dirs:,}개 · {dur:.1f}초")\n\n        # ★ 프루닝은 \'조용히\' 하면 안 된다. 사용자가 자기 리포트가 왜 안 잡혔는지 알 수 있어야\n        #   한다. 예전에는 n_skipped_dirs 를 증가만 시키고 출력하는 곳이 한 군데도 없었다.\n        LOG.table([["걸은 디렉터리", f"{n_dirs:,}"],\n                   ["체크포인트 적중(열거 생략)", f"{n_ckpt_hit:,}"],\n                   ["프루닝한 하위폴더", f"{n_skipped_dirs:,}"],\n                   ["프루닝 예시", _trunc(" / ".join(skipped_samples), 90) if skipped_samples else "—"],\n                   ["새로 찾은 파일", f"{len(found):,}"],\n                   ["소요", f"{dur:.1f}초"],\n                   ["중단 사유", stopped or "—"]],\n                  ["항목", "값"], ["l", "l"],\n                  title="기존 리포트 폴더 스캔 요약 — 프루닝 건수를 숨기면 누락을 알 수 없다")\n        if stopped:\n            LOG.warn(f"스캔을 중단했습니다: {stopped}. 완주한 디렉터리만 체크포인트에 저장했으므로 "\n                     f"다음 실행에서 남은 폴더부터 이어받습니다(중도 탈출한 폴더는 다시 읽습니다). "\n                     f"상한을 늘리려면 ADOPT_SCAN_MAX_FILES / ADOPT_SCAN_MAX_SECONDS 를 조정하세요.")\n        try:\n            self.put_table("qvf_adopt_scan_state",\n                           pd.DataFrame({"dirpath": list(new_ckpt.keys()),\n                                         "mtime": [v[0] for v in new_ckpt.values()],\n                                         "subdirs": [json.dumps(v[1], ensure_ascii=False)\n                                                     for v in new_ckpt.values()]}),\n                           scope="private", domain="index", source="adopt_scan checkpoint")\n        except Exception as e:                                      # noqa\n            LOG.debug(f"스캔 체크포인트 저장 실패({type(e).__name__}) — 기능에 영향 없음")\n        return pd.DataFrame(found) if found else pd.DataFrame(columns=["abs_path", "kind", "name"])\n\n    def compact(self, scope: str):\n        """★ 미러 행을 드라이브 인덱스에 쓰면 안 된다.\n\n        load_index 는 조회 편의를 위해 미러 행을 합쳐서 돌려주는데, 부모의 compact 는\n        그 결과를 그대로 index.parquet 에 기록한다. 그러면 \'로컬에만 존재하는 파일 경로\'가\n        공용 드라이브 인덱스에 박히고, 다른 기기·다른 전략이 그 경로를 열려다 실패한다.\n        컴팩션 동안만 자기 루트 전용 모드로 내린다.\n        """\n        keep = self._own_only\n        self._own_only = True\n        try:\n            super().compact(scope)\n        finally:\n            self._own_only = keep\n            self._idx.pop(scope, None)      # 합쳐진 조회용 뷰를 다음 조회에서 재구성\n            self._uidset.pop(scope, None)\n            self._merged.pop(scope, None)\n            self._uidpath.pop(scope, None)\n\n    def report_roots(self):\n        rows = [["쓰기 루트 (신규 수집분 저장)", self.root, self.mode]]\n        for m in self.mirrors:\n            rows.append(["읽기 전용 미러", m, "탐색만 — 절대 쓰지 않음"])\n        missing = [m for m in CACHE_MIRROR_ROOTS if not os.path.isdir(_expand(m))]\n        if missing:\n            rows.append(["(없음 — 건너뜀)", _trunc(", ".join(missing), 44),\n                         "이 환경에 없는 경로. 정상입니다"])\n        LOG.table(rows, ["역할", "경로", "비고"], ["l", "l", "l"],\n                  title="캐시 루트 구성 (로컬·드라이브 양쪽 탐색 → 신규는 드라이브에만 기록)")\n        if not self.mirrors:\n            LOG.info("읽기 전용 미러가 없습니다 — 구글드라이브만 탐색합니다. "\n                     "로컬 D: 가 없는 PC나 Colab 에서는 정상이며, 기능에 영향이 없습니다. "\n                     "다른 PC의 로컬 캐시를 함께 쓰려면 CACHE_MIRROR_ROOTS 에 경로를 "\n                     "추가하세요(탐색만 하고 절대 쓰지 않습니다).")',
    'DartQuota': 'class DartQuota:\n    """DartBudget 의 드롭인 대체(take/refund/close/n/exhausted 동일 인터페이스).\n\n    ★ 공용 스코프에 기록하는 이유: 하나의 DART 키를 여러 전략(TCD, QVF …)이 나눠 쓰면\n      전략별 사설 카운터는 서로를 못 본다. 그러면 각자 \'아직 여유 있다\'고 믿으면서\n      합계로는 한도를 넘겨 020 폭풍을 맞는다.\n    """\n\n    FLUSH_EVERY = 200\n    # DART 한도는 한국시간 자정에 리셋된다. 로컬시간을 쓰면 Colab(UTC)에서 9시간 어긋나고,\n    # 구축 시점에 한 번만 계산하면 자정을 넘긴 장시간 실행이 \'어제 한도\'에 계속 묶인다.\n    KST = _dt.timezone(_dt.timedelta(hours=9))\n\n    @staticmethod\n    def _day_key() -> str:\n        return _dt.datetime.now(DartQuota.KST).date().isoformat()\n\n    def __init__(self, vault: "Vault"):\n        self.vault = vault\n        self.today = self._day_key()\n        self.key_fp = sha1_str("dartkey", DART_API_KEY or "")[:12]\n        self.n = 0                     # 이번 프로세스가 쓴 양\n        self.n_other = 0               # 같은 키로 오늘 다른 프로세스/전략이 쓴 양\n        self.observed_limit: Optional[int] = None   # 오늘 실측된 상한\n        self.hist_limit: Optional[int] = None       # 과거 실측 상한(계획용 추정치)\n        self._exhausted = False\n        self._lk = threading.RLock()\n        self._unflushed = 0\n        self._probe_at = 0.0\n        self._load()\n        # 공용 코어(12_ingest_dart_fin)가 모듈 로드 시점에 DART_DAILY_LIMIT 를 19,000 으로\n        # 되돌려 놓는다(조립 순서상 헤더보다 뒤). 사용자가 명시적으로 거부한 값이므로\n        # 실측 소유자인 이 클래스가 되찾아온다. 실측되면 그 값으로 다시 덮인다.\n        globals()["DART_DAILY_LIMIT"] = int(self.hist_limit or DART_DAILY_LIMIT_HINT)\n\n    def _roll_if_needed(self):\n        """자정(KST)을 넘겼으면 카운터를 새 날짜로 되돌린다. 며칠에 걸친 콜드빌드에서\n        \'어제 소진\'을 오늘까지 끌고 가 하루를 통째로 버리는 사고를 막는다."""\n        d = self._day_key()\n        if d == self.today:\n            return\n        self._flush_locked()\n        LOG.ok(f"DART 한도 리셋 감지 (KST {self.today} → {d}) — 카운터를 초기화하고 계속합니다.")\n        self.today = d\n        self.n = 0\n        self.n_other = 0\n        self.observed_limit = None\n        self._exhausted = False\n        self._unflushed = 0\n\n    # -- 저널 ---------------------------------------------------------------------------\n    def _path(self) -> str:\n        return os.path.join(self.vault.ns["shared"], "index", "dart_quota.jsonl")\n\n    def _mirror_paths(self) -> List[str]:\n        out = []\n        for mr in getattr(self.vault, "mirrors", []) or []:\n            p = os.path.join(mr, GDRIVE_SHARED_NS, "index", "dart_quota.jsonl")\n            if os.path.exists(p):\n                out.append(p)\n        return out\n\n    def _reload_other(self):\n        """저널을 다시 읽어 \'남이 오늘 쓴 양\'만 갱신한다(hist/observed 는 건드리지 않는다).\n\n        020 을 기록하기 직전에 부른다. 형제 프로세스의 소비가 안 보이면 내 눈에 보이는\n        누적이 실제보다 작고, 그 작은 값이 그날의 실측 한도로 저널에 영구히 박힌다.\n        """\n        rows: List[dict] = []\n        for p in [self._path()] + self._mirror_paths():\n            rows.extend(read_jsonl(p))\n        seen, tot = set(), 0\n        for r in rows:\n            if r.get("event") != "use" or str(r.get("date")) != self.today:\n                continue\n            eid = r.get("evt_id") or (r.get("host"), r.get("pid"), r.get("ts"), r.get("n"))\n            if eid in seen:\n                continue\n            seen.add(eid)\n            try:\n                tot += max(0, int(r.get("n", 0)))\n            except Exception:\n                pass\n        # 내 몫(self.n)은 이미 저널에 flush 되어 tot 에 포함되므로 빼서 이중계상을 막는다.\n        with self._lk:\n            self.n_other = max(0, tot - int(self.n))\n\n    def _load(self):\n        rows: List[dict] = []\n        for p in [self._path()] + self._mirror_paths():\n            rows.extend(read_jsonl(p))\n        # ★★ 미러의 저널 사본을 중복 합산하면 안 된다 ★★\n        #   로컬 미러가 드라이브 캐시의 복사본이면(= CACHE_MIRROR_ROOTS 의 정상 용도) 같은\n        #   소비 이벤트가 \'미러 수 + 1\' 배로 세어진다. 실측으로 500건 사용이 1,000~1,500건\n        #   으로 잡혔고, take() 의 안전정지가 실제 사용량의 절반 지점에서 걸려 DART 수집이\n        #   조기 중단됐다. 그런데 그 스테이지는 critical=False 라 실패로 잡히지도 않는다.\n        #   → evt_id 로 dedup 한다. 미러를 \'읽는\' 것 자체는 타당하다(다른 기기의 소비를\n        #     봐야 하므로). 중복만 걷어낸다.\n        seen_evt = set()\n        uniq: List[dict] = []\n        for r in rows:\n            eid = r.get("evt_id")\n            if eid:\n                if eid in seen_evt:\n                    continue\n                seen_evt.add(eid)\n            else:\n                # 구버전 저널(evt_id 없음)은 자연키로 대체한다.\n                nk = (r.get("date"), r.get("key_fp"), r.get("host"), r.get("pid"),\n                      r.get("ts"), r.get("event"), r.get("n"), r.get("limit"))\n                if nk in seen_evt:\n                    continue\n                seen_evt.add(nk)\n            uniq.append(r)\n        if len(uniq) != len(rows):\n            LOG.debug(f"DART 쿼터 저널 중복 {len(rows) - len(uniq):,}행 제거(미러 사본)")\n        rows = uniq\n        mine_pid = os.getpid()\n        for r in rows:\n            if str(r.get("key_fp")) != self.key_fp:\n                continue\n            if r.get("event") == "limit_observed":\n                try:\n                    lim = int(r.get("limit", 0))\n                except Exception:\n                    continue\n                if lim > 0:\n                    self.hist_limit = max(self.hist_limit or 0, lim)\n                    if str(r.get("date")) == self.today:\n                        self.observed_limit = lim\n                        self._exhausted = True\n            elif r.get("event") == "use" and str(r.get("date")) == self.today:\n                try:\n                    k = int(r.get("n", 0))\n                except Exception:\n                    k = 0\n                # 같은 pid 의 기록은 재실행 시 \'남이 쓴 양\'으로 다시 세면 안 되지만,\n                # 프로세스가 죽었다 살아난 경우엔 실제로 소비된 양이므로 세는 게 맞다.\n                # 보수적으로(=과다계상 방향) 전부 센다. 과소계상은 020 폭풍을 부른다.\n                self.n_other += max(0, k)\n        if self.n_other:\n            LOG.info(f"오늘 이 DART 키로 이미 사용된 호출 {self.n_other:,}건 "\n                     f"(다른 전략/이전 실행 포함, 공용 저널 기준) — 이어서 진행합니다.")\n        if self.observed_limit:\n            LOG.warn(f"오늘({self.today}) 이 키의 실측 한도 {self.observed_limit:,}건에 이미 "\n                     f"도달한 기록이 있습니다. DART 신규 수집은 건너뛰고 캐시로 진행합니다. "\n                     f"내일 재실행하면 정확히 이 지점부터 이어받습니다.")\n        elif self.hist_limit:\n            LOG.info(f"과거 실측된 일일 한도 {self.hist_limit:,}건을 \'계획용 추정치\'로만 씁니다. "\n                     f"실제 소비는 서버가 020(한도초과)을 줄 때까지 계속합니다 — "\n                     f"추정치 때문에 남은 호출을 놀리지 않습니다.")\n        else:\n            LOG.info("이 키의 일일 한도 실측 기록이 아직 없습니다. OpenDART 는 잔여량 조회 API 를 "\n                     "제공하지 않으므로, 서버가 020 을 줄 때까지 소비하며 그 지점을 한도로 "\n                     "기록합니다(다음 실행부터 계획에 반영됩니다).")\n\n    def _append(self, rec: dict):\n        self._seq = getattr(self, "_seq", 0) + 1\n        _ts = _dt.datetime.now().isoformat(timespec="microseconds")\n        rec = {"date": self.today, "key_fp": self.key_fp, "pid": os.getpid(),\n               "host": platform.node(), "ts": _ts,\n               # 미러 사본 중복 합산을 막는 고유 id. 없으면 dedup 자체가 불가능하다.\n               "evt_id": sha1_str("dartquota", platform.node(), os.getpid(), _ts, self._seq),\n               **rec}\n        try:\n            with self.vault.lock("dart_quota", timeout=15.0):\n                append_jsonl(self._path(), [rec])\n        except Exception:\n            try:\n                append_jsonl(self._path(), [rec])\n            except Exception:\n                pass\n\n    # -- 인터페이스 ---------------------------------------------------------------------\n    @property\n    def used_today(self) -> int:\n        return self.n + self.n_other\n\n    @property\n    def exhausted(self) -> bool:\n        return self._exhausted\n\n    @exhausted.setter\n    def exhausted(self, v: bool):\n        """★ 공용 코어(dart_api)가 status 020/021 을 보면 여기에 True 를 넣는다.\n        그 순간의 누적 사용량이 곧 \'오늘의 실측 한도\'다. 이 setter 가 발견 지점이다."""\n        v = bool(v)\n        if not v:\n            self._exhausted = False\n            return\n        if self._exhausted:\n            return\n        # ★ 공용 코어는 020(일일한도 초과)과 021(조회 가능 회사 수 초과)을 같은 분기에서\n        #   처리하며 둘 다 여기로 True 를 보낸다. 그런데 021 은 \'요청이 잘못됐다\'는 뜻이지\n        #   한도와 아무 상관이 없다. 이를 한도로 기록하면 (a) 남은 호출을 전부 못 쓰고\n        #   (b) 그 거짓 상한이 공용 저널에 박혀 내일 이후 실행과 \'다른 전략\'까지 오염된다.\n        #   → 값싼 확인 호출을 한 번 던져 진짜 020 인지 확증한 뒤에만 기록한다.\n        self._exhausted = True                      # 확인 전까지는 잠정 정지(호출 폭주 방지)\n        if not self._confirm_exhaustion():\n            self._exhausted = False\n            LOG.warn("DART 오류를 받았지만 확인 호출이 성공했습니다 — 일일한도(020)가 아니라 "\n                     "요청 오류(021 등)로 판단하고 수집을 계속합니다. 한도로 기록하지 않습니다.")\n            return\n        # ★ used_today = self.n + self.n_other 인데 n_other 는 __init__ 의 _load() 에서\n        #   딱 한 번만 읽었다. 이 프로세스가 시작한 뒤 형제 프로세스(TCD·두 번째 QVF 실행)가\n        #   같은 키를 쓴 몫이 안 보이므로, 020 이 왔을 때 내 눈에 보이는 누적은 실제보다\n        #   훨씬 작다. 그 작은 값이 \'그날의 실측 한도\'로 저널에 영구 기록되고, 이후 모든\n        #   실행이 그 근처(및 ×2 안전정지)에서 멈춘다 — 한 번 오염되면 매일 재현된다.\n        #   기록 직전에 저널을 다시 읽어 형제 소비분을 반영한다.\n        self._flush()\n        try:\n            self._reload_other()\n        except Exception as e:\n            LOG.debug(f"저널 재조회 실패({type(e).__name__}) — 프로세스 내 집계로만 기록합니다.")\n        self.observed_limit = int(self.used_today)\n        self._append({"event": "limit_observed", "limit": int(self.observed_limit)})\n        globals()["DART_DAILY_LIMIT"] = int(self.observed_limit)\n        LOG.warn(f"DART 일일 한도 실측: {self.observed_limit:,}건에서 020(한도초과)을 확인했습니다. "\n                 f"여기까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 정확히 "\n                 f"이 지점부터 이어받습니다. (한도값을 코드에 고정하지 않고 실측한 값입니다)")\n\n    def _confirm_exhaustion(self) -> bool:\n        """가장 값싼 정상 요청을 한 번 던져 020 이 재현되는지 본다. True = 진짜 한도 소진."""\n        now = time.monotonic()\n        if now - self._probe_at < 30.0:\n            return True                              # 직전에 확인함 — 중복 확인 금지\n        self._probe_at = now\n        if not DART_API_KEY:\n            return True\n        try:\n            d = (_dt.datetime.now(self.KST) - _dt.timedelta(days=3)).strftime("%Y%m%d")\n            js = http_json("https://opendart.fss.or.kr/api/list.json", source="dart", tries=1,\n                           params={"crtfc_key": DART_API_KEY, "bgn_de": d, "end_de": d,\n                                   "page_no": 1, "page_count": 1},\n                           referer="https://opendart.fss.or.kr/")\n        except Exception:\n            return True                              # 확인 불가 → 보수적으로 소진 처리\n        if not isinstance(js, dict):\n            return True\n        st = str(js.get("status", ""))\n        # 000(정상) 또는 013(데이터 없음)이면 키는 살아 있다 = 한도 소진이 아니다.\n        return st not in ("000", "013")\n\n    def take(self, k: int = 1) -> bool:\n        if not DART_API_KEY:\n            return False\n        with self._lk:\n            self._roll_if_needed()\n            if self._exhausted:\n                return False\n            # 과거 실측 상한이 있으면 \'거기서 멈추지 않고\' 계속 쓴다(§요구사항).\n            # 다만 추정치의 2배를 넘어서면 저널이 오염됐을 가능성이 크므로 안전 정지한다.\n            if self.hist_limit and self.used_today > self.hist_limit * 2:\n                LOG.warn(f"누적 사용량({self.used_today:,})이 과거 실측 한도({self.hist_limit:,})의 "\n                         f"2배를 넘었습니다. 저널 오염 가능성이 있어 안전 정지합니다.")\n                self._exhausted = True\n                return False\n            self.n += k\n            self._unflushed += k\n            if self._unflushed >= self.FLUSH_EVERY:\n                self._flush_locked()\n            return True\n\n    def refund(self, k: int = 1):\n        if k <= 0:\n            return\n        with self._lk:\n            self.n = max(0, self.n - k)\n            self._unflushed = max(0, self._unflushed - k)\n\n    def _flush_locked(self):\n        if self._unflushed <= 0:\n            return\n        k, self._unflushed = self._unflushed, 0\n        self._append({"event": "use", "n": int(k)})\n\n    def _flush(self):\n        with self._lk:\n            self._flush_locked()\n\n    def remaining_calls(self) -> Optional[int]:\n        """오늘 더 쓸 수 있는 호출 수의 \'숫자\'. 모르면 None (문자열판 remaining_str 과 짝).\n\n        수집부는 이 값으로 작업 목록을 잘라낸다 — 한도를 코드에 고정하지 않고, 그렇다고\n        전부 던져 놓고 예외를 기다리지도 않기 위해서다. 후자가 실제로 하루치를 통째로\n        태우고도 아무 회사도 완성시키지 못한 원인이었다.\n\n        ★ 실측 상한이 아직 없으면 None 이 아니라 헤더 힌트 기준 잔여를 준다. None 을 주면\n          호출부가 \'무제한\'으로 오해해 예전 동작으로 되돌아간다.\n        """\n        with self._lk:\n            used = int(self.used_today)\n        if self.observed_limit is not None:          # 오늘 020 을 이미 봤다 = 확정적으로 소진\n            return max(0, int(self.observed_limit) - used)\n        # ★ 과거 실측치는 \'그날 그 지점에서 막혔다\'는 하한 증거일 뿐 상한이 아니다.\n        #   (키를 다른 프로세스와 나눠 썼으면 그날치가 낮게 찍힌다 — 실제로 사용자 키는\n        #    14,047 에서 막혔지만 OpenDART 공표 한도는 20,000 이다.)\n        #   이걸 상한으로 쓰면 매일 6,000 호출을 스스로 버리게 된다. 계획은 둘 중 큰 값으로\n        #   잡고, 진짜 중단은 오늘 020 이 실제로 올 때 한다 = "실시간으로 체크해서 그만큼 쓴다".\n        cap = max(int(self.hist_limit or 0), int(DART_DAILY_LIMIT_HINT))\n        return max(0, cap - used)\n\n    def remaining_str(self) -> str:\n        if self.observed_limit is not None:\n            return f"0 (오늘 실측 한도 {self.observed_limit:,} 도달)"\n        if self.hist_limit:\n            return f"약 {max(0, self.hist_limit - self.used_today):,} (과거 실측 {self.hist_limit:,} 기준 추정)"\n        return "미확정 (OpenDART 는 잔여량 API 를 제공하지 않음 — 020 수신 시 확정)"\n\n    def report(self):\n        LOG.table([["오늘 날짜", self.today],\n                   ["키 지문", self.key_fp or "(키 없음)"],\n                   ["이번 실행 사용", f"{self.n:,}"],\n                   ["오늘 누적 사용(공용 저널)", f"{self.used_today:,}"],\n                   ["오늘 실측 한도", f"{self.observed_limit:,}" if self.observed_limit else "미도달"],\n                   ["과거 실측 한도", f"{self.hist_limit:,}" if self.hist_limit else "기록 없음"],\n                   ["남은 호출량", self.remaining_str()]],\n                  ["항목", "값"], ["l", "r"],\n                  title="DART 호출량 (고정 상수가 아니라 실측 — 공용 저널로 전략 간 합산)")\n\n    def close(self):\n        self._flush()',
}

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-H  계약 자동검정 Q1~Q14 — 협상 불가 규칙을 코드가 스스로 증명한다                       ║
# ║                                                                                          ║
# ║  주석은 지켜지지 않아도 아무 일이 없지만, 여기의 검정은 실패하면 실행이 멈춘다.             ║
# ║  일부 계약은 '소스 검사'다 — 최적화 루틴이 없다는 것은 실행으로 증명할 수 없고              ║
# ║  코드에 그것이 존재하지 않음을 확인하는 방법밖에 없다.                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

import inspect as _inspect

CONTRACTS: List[dict] = []

# 빌더가 심어 둔 소스 조각. 파일이 아니라 셀에서 실행될 때 inspect 대신 이걸 쓴다.
QVF_PINNED_SRC: Dict[str, str] = globals().get("QVF_PINNED_SRC", {})


def pinned_src(name: str, obj=None) -> str:
    """이름으로 소스를 가져온다. 빌드 시점 고정본 우선, 없으면 inspect 폴백.

    ★ 둘 다 실패하면 '' 를 돌려주지 않고 예외를 낸다. 소스를 못 읽었는데 조용히 통과시키면
      '부재 증명' 계약이 아무것도 증명하지 않는 채로 ✔ 를 찍게 된다 — Colab 에서 정확히
      그 상태가 될 뻔했다(거기서는 아예 OSError 로 죽어서 드러났지만).
    """
    s = QVF_PINNED_SRC.get(name)
    live = None
    if obj is not None:
        try:
            live = _inspect.getsource(obj)
        except Exception:
            live = None
    # ★★ 고정본을 무조건 믿으면 안 된다 ★★
    #   QVF_PINNED_SRC 는 '빌드 시점'의 글자다. 사용자가 셀에 붙여넣은 뒤 함수를 고치면
    #   실제로 도는 코드는 바뀌었는데 고정본은 옛 글자를 그대로 들고 있다. 그러면 Q6/Q7/Q12
    #   같은 '부재 증명' 계약이 돌지도 않는 코드를 검정하고 ✔ 를 찍는다 — 계약층 전체가
    #   조용히 무력화되는 경로다. 살아 있는 소스를 읽을 수 있으면 그쪽이 진실이다.
    if s and live is not None:
        if re.sub(r"\s+", " ", s).strip() != re.sub(r"\s+", " ", live).strip():
            raise ContractViolation(
                f"'{name}' 의 실제 소스가 빌드 시점 고정본과 다릅니다 — 파일/셀에서 이 함수를 "
                f"수정하셨습니다. 고정본으로 검정하면 '돌지 않는 코드'를 검정하게 되므로 "
                f"통과시키지 않습니다. tools/build_qvf.py 로 다시 빌드하거나 수정을 되돌리세요.")
        return live
    if s:
        return s
    if live is not None:
        return live
    raise ContractViolation(
        f"소스 조각 '{name}' 을 찾을 수 없습니다. 빌드 시점 고정본(QVF_PINNED_SRC)이 "
        f"비어 있고 inspect 도 실패했습니다 — 파일을 직접 편집했거나 빌더의 SRC_PIN 목록과 "
        f"이름이 어긋났을 수 있습니다. 소스 기반 계약을 검정할 수 없으므로 통과시키지 않습니다.")


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
    # ★ 게이트를 실제로 우회하는 경로는 '빈 프레임'이다. PITStore.register 는 len(df)==0 이면
    #   PIT 컬럼 검사 없이 그냥 등록해 버린다 — 수집기가 빈손으로 돌아오면 PIT 없는 테이블이
    #   '있음'으로 잡힌다. 1행짜리만 시험하던 옛 검정은 이 경로를 한 번도 안 밟았다.
    try:
        st.register("empty", pd.DataFrame(columns=["code", "x"]))
    except KeyError:
        pass
    else:
        if st.has("empty"):
            raise ContractViolation(
                "빈 프레임이 PIT 컬럼 검사 없이 등록되어 'has()=True' 로 보고됩니다 — "
                "수집 실패가 '데이터 있음'으로 둔갑하는 경로입니다.")
    return "PIT 등록 거부 + as_of 절단 + 빈 프레임 우회 차단 확인"


@_contract("Q2", "시점 규약 — 신호일 < 체결일, 공시는 접수일+1거래일")
def _q2():
    # ★ set_trading_days 는 전역 QVF_TRADING_DAYS 를 덮어쓴다(q21:48). 계약이 끝나도 합성
    #   2020년 영업일 격자가 남으므로, 뒤에 오는 스테이지가 그 격자로 next_trading_day 를
    #   계산하면 2020-01-01 이전 날짜가 전부 2020-01-01 로 접힌다 — DART knowledge_date 가
    #   통째로 조작되는 셈이다. 지금은 L1.CAL 이 나중에 덮어써서 우연히 무해할 뿐이다.
    #   계약은 자기가 만진 전역을 반드시 원복해야 한다.
    _SAVED_TD = globals().get("QVF_TRADING_DAYS")
    try:
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
    finally:
        globals()["QVF_TRADING_DAYS"] = _SAVED_TD


@_contract("Q3", "생존자편향 — 폐지 종목이 유니버스에 있고 −100% 가 적용된다")
def _q3():
    # ★ set_trading_days 는 전역 QVF_TRADING_DAYS 를 덮어쓴다(q21:48). 계약이 끝나도 합성
    #   2020년 영업일 격자가 남으므로, 뒤에 오는 스테이지가 그 격자로 next_trading_day 를
    #   계산하면 2020-01-01 이전 날짜가 전부 2020-01-01 로 접힌다 — DART knowledge_date 가
    #   통째로 조작되는 셈이다. 지금은 L1.CAL 이 나중에 덮어써서 우연히 무해할 뿐이다.
    #   계약은 자기가 만진 전역을 반드시 원복해야 한다.
    _SAVED_TD = globals().get("QVF_TRADING_DAYS")
    try:
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
    finally:
        globals()["QVF_TRADING_DAYS"] = _SAVED_TD


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
    # ★ 예전엔 VQF 의 '합이 1'과 V 만 봤다. VQ 는 아예 검사하지 않았고, VQF 도 (0.1,0.1,0.8)
    #   처럼 완전히 다른 값이 합만 맞으면 통과했다 — 계약 이름이 '사전등록 가중치'인데
    #   정작 사전등록 값을 검정하지 않았다. 세 변형 전부를 리터럴로 못박는다.
    _PRE = {"V": (1.0, 0.0, 0.0), "VQ": (0.5, 0.5, 0.0), "VQF": (0.4, 0.4, 0.2)}
    for _k, _w in _PRE.items():
        _got = tuple(float(x) for x in VARIANT_W.get(_k, ()))
        if len(_got) != 3 or max(abs(a - b) for a, b in zip(_got, _w)) > 1e-9:
            raise ContractViolation(
                f"VARIANT_W['{_k}'] 이 §5.5 사전등록 값과 다릅니다: {_got} ≠ {_w}")
    if (SCORE2_W_NONFIN, SCORE2_W_TONE) != (2.0, 1.0):
        raise ContractViolation("Score2 가중치가 §6.3 사전등록 값(2:1)과 다릅니다.")
    src = ""
    for nm, fn in (("score1", score1), ("build_u200", build_u200),
                   ("apply_filter2", apply_filter2),
                   ("build_final_selection", build_final_selection),
                   ("run_experiment", run_experiment)):
        src += pinned_src(nm, fn) + "\n"
    bad = re.findall(r"\b(minimize|curve_fit|GridSearch|RandomizedSearch|optimize|"
                     r"differential_evolution|fmin|argmax\s*\(\s*sharpe|best_weight)\b", src)
    if bad:
        raise ContractViolation(f"선정 경로에서 최적화 흔적이 발견되었습니다: {sorted(set(bad))}")
    return "가중치 고정 확인 · 선정 경로에 최적화 루틴 없음"


@_contract("Q7", "캐시 무결성 — 삭제 API 부재 · 로컬 미러는 쓰기 경로에 등장하지 않는다")
def _q7():
    # ★ 예전엔 이름 5개짜리 블랙리스트였다 — evict/prune/expire/trim/clear/unlink 로 이름만
    #   바꾸면 그대로 통과한다. 상속 계층(MRO) 전체를 훑어 '지우는 뜻'의 공개 메서드를 금지한다.
    _DEL = re.compile(r"(^|_)(del|delete|remov|purge|drop|rm|evict|prune|expire|trim|clear|unlink|wipe)")
    for _cls in (Vault, QVFVault):
        for _k in dir(_cls):
            if _k.startswith("__") or not callable(getattr(_cls, _k, None)):
                continue
            if _DEL.search(_k.lower()):
                raise ContractViolation(
                    f"{_cls.__name__} 에 삭제 성격의 API '{_k}' 가 있습니다 — 절대 1원칙 위반. "
                    f"(이름만 바꾼 삭제도 삭제입니다)")
    for nm, fn in (("Vault.put_table", Vault.put_table), ("Vault.put_blob", Vault.put_blob),
                   ("Vault.flush", Vault.flush), ("Vault.compact", Vault.compact)):
        s = pinned_src(nm, fn)
        if "mirror" in s.lower():
            raise ContractViolation(f"쓰기 함수 {nm} 가 미러 경로를 참조합니다 — "
                                    f"로컬 미러는 구조적으로 읽기 전용이어야 합니다.")
    s = pinned_src("QVFVault", QVFVault)
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
    # ★★ 예전에는 정규난수를 소수 2자리로 반올림해 '동점이 생기기를 기대'했다. SEED
    #   20260810 에서 실측하면 동점 6쌍이 생기긴 하지만 20위(0.295)와 21위(0.255) 사이를
    #   가로지르는 동점이 없어, 선정 집합이 점수만으로 유일하게 결정된다 — 즉 tie-break 를
    #   통째로 없애도 이 계약은 통과했다. 검정력이 0이었고, 그 사실이 무관한 상수(SEED)에
    #   달려 있었다. 커트라인 위에 동점을 '설계해서' 만든다.
    n = 50
    rng = np.random.default_rng(SEED)
    zv = np.round(rng.normal(size=n), 2)
    # 19~23위가 될 5종목의 점수를 완전히 같게 만들어 커트라인(20위)을 동점이 가로지르게 한다.
    order = np.argsort(-zv)
    tie_at = order[18:23]
    zv[tie_at] = float(zv[order[19]])
    base = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
        "Z_V": zv,
        "Z_Q": zv,                                   # VQ = 0.5·V + 0.5·Q → 동점이 그대로 유지
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
    # ★ 검정이 실제로 '동점 구간'을 통과했는지 확인한다. 동점이 커트라인을 가로지르지 않으면
    #   위 비교는 tie-break 가 없어도 성립하므로 계약이 아무것도 보장하지 못한다.
    _sel = set(base.loc[base.index[tie_at], "code"]) & sa
    if not (0 < len(_sel) < len(tie_at)):
        raise ContractViolation(
            f"동점 {len(tie_at)}종목이 커트라인을 가로지르지 않아 이 검정에 검정력이 없습니다 "
            f"(선정된 동점 {len(_sel)}종목). 테스트 픽스처를 고치세요.")
    return f"행 순서 무관 · 선정 {len(sa)}종목 동일 · 커트라인 동점 {len(tie_at)}종목 통과"


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
    # ★★ 예전 Q10 은 제목이 "비용 차감 후 수익은 항상 차감 전 이하다"인데 정작 백테스트를
    #   돌리지도, 두 값을 비교하지도 않았다. 소스에 "ret_gross"/"gross - cost" 라는 글자가
    #   있는지만 봤다 — 주석 안에 있어도 통과하고, 변수명을 g/c 로 줄이면 멀쩡한 코드가
    #   실패한다. 게다가 IMPACT_K 검사는 기본 설정(QVF_COST_MODEL="spec", §8.1 문언)에서
    #   '있으면 안 되는' 확장 비용을 강제하고 있었다. 실제로 돌려서 부등식을 확인한다.
    _n = 12
    _cal = pd.DataFrame({"rebal": pd.date_range("2020-03-01", periods=4, freq="QS")})
    _cal["signal_date"] = _cal["rebal"] - pd.Timedelta(days=1)
    _cal["exec_date"] = _cal["rebal"] + pd.Timedelta(days=1)
    _rng = np.random.default_rng(SEED)
    _rows = []
    for t in _cal["rebal"]:
        for i in range(_n):
            _rows.append({"code": f"{i:06d}", "rebal": t, "sel": True,
                          "mktcap": 3e10, "adtv": 5e8, "cs_spread": 0.004})
    _P = pd.DataFrame(_rows)
    _fwd = _P[["code", "rebal"]].copy()
    _fwd["fwd_ret"] = _rng.normal(0.01, 0.05, len(_fwd))
    _fwd["exit_kind"] = "normal"
    _kw = dict(P=_P, cal=_cal, sel_col="sel", fwd=_fwd, label="Q10", delist={})
    _R = run_qbacktest(apply_costs=True, **_kw)["returns"]
    _R0 = run_qbacktest(apply_costs=False, **_kw)["returns"]
    for _c in ("ret", "ret_gross", "cost"):
        if _c not in _R.columns:
            raise ContractViolation(f"백테스트 결과에 '{_c}' 이 없습니다 — 비용 전/후를 "
                                    f"분리해 산출하지 않습니다 (§8.1 위반).")
    if bool((_R["ret"] > _R["ret_gross"] + 1e-12).any()):
        raise ContractViolation(
            f"비용 차감 후 수익이 차감 전보다 큰 분기가 "
            f"{int((_R['ret'] > _R['ret_gross'] + 1e-12).sum())}개 있습니다 — "
            f"비용이 음수이거나 부호가 뒤집혔습니다 (§8.1 위반).")
    if bool((_R["cost"] < -1e-12).any()):
        raise ContractViolation("음수 비용이 산출되었습니다 — 거래가 수익을 만들고 있습니다.")
    if float(_R["cost"].sum()) <= 0:
        raise ContractViolation("매매가 있었는데 비용이 0 입니다 — 비용 모델이 적용되지 "
                                "않고 있습니다(회전율 > 0 인 분기가 존재).")
    if float(_R0["cost"].abs().sum()) > 1e-12:
        raise ContractViolation("apply_costs=False 인데 비용이 발생했습니다 — "
                                "비용 스위치가 동작하지 않습니다.")
    # 거래세는 '이력'이어야 한다 — 단일 세율이면 10년 중 어느 시점을 골라도 값이 같다.
    if len(QVF_TAX_SCHEDULE) < 5:
        raise ContractViolation("증권거래세를 단일 세율로 처리하고 있습니다 — 10년간 여섯 번 바뀌었습니다.")
    if abs(qvf_sell_tax(as_ts("2017-06-01")) - qvf_sell_tax(as_ts("2024-06-01"))) < 1e-9:
        raise ContractViolation("거래세 이력표가 시점에 따라 다른 세율을 주지 않습니다 — "
                                "표만 있고 적용되지 않고 있습니다.")
    return (f"실제 백테스트로 net ≤ gross 확인 · 거래세 {len(QVF_TAX_SCHEDULE)}단계가 "
            f"시점별로 다르게 적용됨 (cost_model={QVF_COST_MODEL})")


@_contract("Q11", "결측을 0 으로 채우지 않는다 — z-score 는 표본 부족 시 NaN 을 유지한다")
def _q11():
    v = pd.Series([1.0, 2.0, np.nan, 4.0, np.inf, -np.inf])
    cells = pd.Series(["A"] * 6)
    z = xsec_z_pct(v, cells, min_n=3)
    if z.isna().sum() < 3:
        raise ContractViolation("±inf 와 NaN 이 결측으로 유지되지 않았습니다.")
    # ★ 위 검정은 '한쪽 방향'이라 z 를 전부 NaN 으로 만드는 회귀도 통과한다(결측이 3개 이상이면
    #   되니까). 그러면 z-score 무결성을 지킨다는 계약이 정작 축이 통째로 죽은 상태를 승인한다.
    #   유효값이 실제로 살아 있고 표준화가 됐는지도 같이 본다.
    _ok = z[v.notna() & np.isfinite(v)]
    if _ok.isna().any():
        raise ContractViolation("정상 관측치의 z 까지 NaN 이 되었습니다 — 표준화가 죽었습니다.")
    if abs(float(_ok.mean())) > 1e-6 or abs(float(_ok.std(ddof=0)) - 1.0) > 1e-6:
        raise ContractViolation(
            f"관측치 z 가 표준화되지 않았습니다(평균 {float(_ok.mean()):+.3g} · "
            f"표준편차 {float(_ok.std(ddof=0)):.3g}).")
    z2 = xsec_z_pct(pd.Series([1.0, 2.0]), pd.Series(["A", "A"]), min_n=8)
    if not z2.isna().all():
        raise ContractViolation("표본 부족 셀의 z 가 NaN 이 아닙니다 — 0 으로 채우면 그 종목이 "
                                "'평균적인 종목'으로 둔갑합니다.")
    return "±inf → NaN · 표본부족 셀 → NaN 유지"


@_contract("Q12", "DART 호출 한도 — 고정 상수가 아니라 실측으로 확정된다")
def _q12():
    s = pinned_src("DartQuota", DartQuota)
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
    #
    #   ★★ 단, '헤더값과 같아야 한다'로 검정하면 안 된다 ★★
    #   DartQuota 는 과거 실측 한도를 DART_DAILY_LIMIT 에 되돌려 넣는다(q06:938). 그게 바로
    #   "남은 호출량을 실시간으로 체크해서 그만큼 쓰라"는 요구사항의 구현이다. 그런데 옛 검정은
    #   실효값 != 헤더값이면 무조건 위반으로 봤다 — 실측이 성공할수록 계약이 깨지는 구조였고,
    #   실제로 사용자의 실행이 시작 4초 만에 여기서 멈췄다(실측 14,047 vs 헤더 20,000).
    #   그래서 '무엇과 같은가'가 아니라 '어디서 온 값인가'를 검정한다:
    #     허용 = 헤더 힌트 | 저널에서 실측된 값(과거/오늘)
    #     위반 = 그 어느 쪽도 아닌 값 = 코드에 박힌 상수가 이긴 경우
    _eff, _hint = int(DART_DAILY_LIMIT), int(DART_DAILY_LIMIT_HINT)
    _measured = {int(v) for v in (getattr(DQUOTA, "hist_limit", None),
                                  getattr(DQUOTA, "observed_limit", None)) if v}
    if _eff != _hint and _eff not in _measured:
        raise ContractViolation(
            f"실효 DART_DAILY_LIMIT 이 {_eff:,} 인데 헤더 힌트({_hint:,})도 아니고 "
            f"저널 실측치{sorted(_measured) or '(없음)'}도 아닙니다 — 조립 순서상 뒤에 오는 "
            f"하드코딩이 헤더를 이기고 있습니다. DartQuota 생성 시 되찾아오는지 확인하세요.")
    _src = "실측" if _eff in _measured else "헤더 힌트(실측 기록 없음)"
    return f"공용 저널 합산 · 020/021 구분 · 실효 한도 {_eff:,} ({_src})"


@_contract("Q13", "§10.4 폐기조건 — 충족 시 실제로 멈춘다(보고만 하고 지나가지 않는다)")
def _q13():
    """'미달 시 행동'을 표에 적어 놓고 아무것도 하지 않으면 그 표는 거짓말이 된다.

    예전에는 폐기 판정을 낸 직후 그 폐기된 전략의 실전 편입 종목표를 그대로 출력했다.
    여기서는 폐기가 확실히 성립하는 가짜 EXPERIMENTS 를 심고 KillCriteria 가 실제로
    올라오는지, 그리고 STOP_ON_KILL_CRITERIA=False 면 올라오지 않는지 둘 다 본다.
    """
    keep_exp = dict(EXPERIMENTS)
    keep_stop = STOP_ON_KILL_CRITERIA
    try:
        EXPERIMENTS.clear()
        # 세 변형 전부 비용 차감 후 CAGR < 0 → 조건 ① 확실히 충족
        for nm in ("V-full", "VQ-full", "VQF-full", "X1"):
            EXPERIMENTS[nm] = {"name": nm, "desc": "", "R": None, "t": 0.0, "p": 0.9, "n": 8,
                               "net": {"CAGR": -0.05, "Sharpe": 0.10, "MDD": -0.30},
                               "gross": {}}
        keep_level = LOG.min
        LOG.min = 99                                   # 계약 표에 잡음을 남기지 않는다
        try:
            globals()["STOP_ON_KILL_CRITERIA"] = True
            raised = False
            try:
                report_preregistration_kill(["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
            except KillCriteria:
                raised = True
            if not raised:
                raise ContractViolation(
                    "§10.4 폐기 조건이 충족됐는데 KillCriteria 가 올라오지 않았습니다 — "
                    "폐기 판정 후에도 최종 편입 종목표가 출력됩니다.")
            globals()["STOP_ON_KILL_CRITERIA"] = False
            out = report_preregistration_kill(["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
            if not out.get("all_alpha_dead"):
                raise ContractViolation("폐기 조건 ①(전 변형 알파 소멸)이 감지되지 않았습니다.")
        finally:
            LOG.min = keep_level
    finally:
        globals()["STOP_ON_KILL_CRITERIA"] = keep_stop
        EXPERIMENTS.clear()
        EXPERIMENTS.update(keep_exp)
    return "충족 시 중단 · STOP 끄면 보고만"


@_contract("Q14", "adopt(size=) 가 코어 경로와 같은 uid 를 만든다 — 캐시 중복등록 방지")
def _q14():
    """scandir 이 이미 알고 있는 크기를 넘겨 FUSE 왕복을 아끼되, uid 는 반드시 동일해야 한다.

    uid 가 달라지면 같은 파일이 인덱스에 두 번 들어가고, 재실행마다 계속 늘어난다.
    """
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        fp = os.path.join(td, "sample_report_2020-01-02.pdf")
        with open(fp, "wb") as f:
            f.write(b"x" * 1234)
        sz = os.path.getsize(fp)
        u_core = sha1_str("adopt", "research", "report_pdf", os.path.abspath(fp), sz)
        v = QVFVault(os.path.join(td, "cache"), mode="local", mirrors=[])
        u_fast = v.adopt(fp, domain="research", subtype="report_pdf", key="sample",
                         scope="shared", size=sz)
        if u_fast != u_core:
            raise ContractViolation(
                f"size 지정 경로의 uid 가 코어와 다릅니다: {u_fast} vs {u_core} — "
                f"같은 파일이 인덱스에 중복 등록됩니다.")
        if not v.has("shared", u_core):
            raise ContractViolation("adopt 직후 has() 가 False 입니다 — 중복 수집이 발생합니다.")
        # ★★ 같은 실행에서 저장한 것을 같은 실행에서 되찾을 수 있어야 한다(절대 1원칙) ★★
        #   put_blob 은 uid 가 아니라 '파일 경로'를 돌려주므로 인덱스에서 uid 를 찾는다.
        #   저널 flush 이전(=등록만 된 상태)과 이후 둘 다 성립해야 한다. 예전에는 코어가
        #   self._idx 캐시를 갱신하지 않아 둘 다 None 이었고, 콜드런 1회차에 방금 받은
        #   PDF 가 TONE 입력에서 통째로 빠졌다 — '본문이 짧아 제외'와 구분되지 않는 형태로.
        for k, payload, flush_first in (("k_preflush", b"before-flush", False),
                                        ("k_postflush", b"after-flush", True)):
            v.put_blob("test", "unit", k, payload, "bin", scope="shared", source="contract")
            if flush_first:
                v.flush("shared")
            idx = v.load_index("shared")
            hit = idx[idx["key"].astype(str) == k]
            if hit.empty:
                raise ContractViolation(
                    f"put_blob 직후 인덱스에서 '{k}' 를 찾을 수 없습니다 — 인덱스 캐시가 "
                    f"등록분을 반영하지 않고 있습니다(절대 1원칙 위반).")
            got = v.get_blob(str(hit["uid"].iloc[0]), "shared")
            if got != payload:
                raise ContractViolation(
                    f"같은 실행에서 저장한 blob('{k}')을 get_blob 이 되찾지 못했습니다 "
                    f"(flush {'후' if flush_first else '전'}). 콜드런 1회차에 방금 받은 "
                    f"자료가 통째로 빠지는 경로입니다.")
        # force=True 가 오히려 파생 캐시를 굳혀 복구를 막던 경로도 함께 고정한다.
        idx = v.load_index("shared", force=True)
        hit = idx[idx["key"].astype(str) == "k_postflush"]
        if hit.empty or v.get_blob(str(hit["uid"].iloc[0]), "shared") != b"after-flush":
            raise ContractViolation(
                "load_index(force=True) 이후 get_blob 이 실패합니다 — force 가 _uidpath 를 "
                "무효화하지 않아 스테일 사전이 영구히 남는 경로입니다.")
    return "uid 동일 · 저장↔재호출 (flush 전/후/force) 전부 성립"


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정 Q1~Q14", "협상 불가 규칙 — 실패하면 실데이터 수집을 시작하지 않습니다")
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
        LOG.ok("계약 Q1~Q14 전부 통과 — PIT·생존자편향·부호처리·결측허용·비용·폐기조건·캐시 무결성 확인")
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
        report_cell_ladder()
        report_discretion_ledger()
        # ★ 스모크의 목적은 '배관이 끝까지 흐르는가' 이지 '전략이 통과하는가' 가 아니다.
        #   합성 난수에는 알파가 없으므로 §10.4 는 발동하는 것이 정상이며, 그 발동으로
        #   스모크가 죽으면 이후 표를 검증하지 못한다. 여기서만 중단을 끈다.
        #   ★ '발동 시 실제로 멈추는가' 는 계약 Q13 이 별도로 검정한다 — 여기서 끄는 것이
        #     §10.4 의 이행을 무력화하지 않는다는 점을 그 계약이 보증한다.
        _keep_stop = STOP_ON_KILL_CRITERIA
        globals()["STOP_ON_KILL_CRITERIA"] = False
        try:
            _kill = report_preregistration_kill([f"{v}-full" for v in VARIANTS], "VQ-full", "X1")
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = _keep_stop
        LOG.info(f"스모크 §10.4 판정(중단은 끈 상태): "
                 f"{ {k: v for k, v in _kill.items() if not k.startswith('_')} }")
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
        # ★ dart_api 는 DBUDGET.take(tries=2) 로 먼저 예산을 잡고, 실제 시도 횟수만큼
        #   on_attempt 로 되돌려 받는다. 가짜 http_json 이 on_attempt 를 안 부르면
        #   시도 0회로 집계돼 환불이 1건 모자라고, '하지도 않은 호출'이 공용 저널에
        #   기록된다(실행당 약 40건). 다른 전략의 잔여량까지 갉아먹는다.
        cb = kw.get("on_attempt")
        if callable(cb):
            for _ in range(int(kw.get("tries", 1) or 1)):
                cb()
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
    if not len(cal) or not len(R):
        return pd.DataFrame(columns=["code", "rebal", "mom12_1"])
    # ★ 예전엔 리밸 시점마다 merge_asof 를 2회 돌렸다 — 40시점 × 2 = 800만행 패널을 80번
    #   훑는다. 게다가 sorted(px["code"].unique()) 를 루프 안에서 매번 다시 계산했다.
    #   패널 재구축이 4회(기준 + 시프트 3회) 있으므로 320 패스가 된다.
    #   (종목 × 앵커시점) 을 한 프레임으로 쌓아 merge_asof 를 '단 2회'로 줄인다. 결과 동일.
    codes = pd.DataFrame({"code": sorted(px["code"].unique())})
    anchors = []
    for r in cal.itertuples(index=False):
        sd = as_ts(r.signal_date)
        anchors.append({"rebal": r.rebal, "p1": sd - pd.DateOffset(months=1),
                        "p12": sd - pd.DateOffset(months=12)})
    A = pd.DataFrame(anchors)
    grid = codes.merge(A, how="cross")
    vals = {}
    for k in ("p1", "p12"):
        LL = grid[["code", "rebal", k]].rename(columns={k: "t"}).sort_values("t", kind="stable")
        M = pd.merge_asof(LL, R, left_on="t", right_on="px_date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=20))
        vals[k] = M.set_index(["code", "rebal"])["close"]
    m = (vals["p1"] / vals["p12"] - 1.0).rename("mom12_1").reset_index()
    return downcast_q(m[["code", "rebal", "mom12_1"]])


def collect_core(cal_hint: Optional[pd.DataFrame] = None) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    months = month_range(as_ts(BACKTEST_START) - pd.DateOffset(months=18), BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스 입력", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    # ★★ 수집 순서를 뒤집었다: [캘린더] → [전종목 시총] → [후보 확정] → [후보만 일봉] ★★
    #   예전에는 전 종목(5,398) 일봉을 먼저 받고 나서야 하위 1000 을 골랐다. 실측 55분.
    #   시총 스냅샷은 날짜당 1~2호출로 전 종목 시총을 주므로 순서만 바꾸면 된다.
    with PIPE.stage("L1.CAL", "거래일 격자 · 분기 리밸런싱 캘린더 (§4)", "L1", budget_s=120):
        globals()["QVF_TRADING_DAYS"] = fetch_trading_calendar(BACKTEST_START, BACKTEST_END)
        ctx["cal"] = qvf_rebal_calendar_from_days(BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.CAP", "PIT 시가총액 스냅샷 (전 종목 · 날짜당 1~2호출)", "L1",
                    budget_s=900, critical=False):
        KRX.login()
        _sd = list(as_ts_series(ctx["cal"]["signal_date"]))
        ctx["snaps_cap"] = fetch_krx_cap_snapshots(_sd)
        # ★★ 시총을 pykrx 단일 경로에 묶어 둔 것이 설계 오류였다 ★★
        #   pykrx import 하나가 깨지자(윈도우 인코딩) U-1000 을 만들 수 없어 실행이 통째로
        #   멈췄다. 유니버스는 여러 소스로 서야 한다는 요구사항을 시총에는 적용하지 않았다.
        #   폴백: 네이버 시가총액 페이지에서 상장주식수(약 66요청) × '이미 캐시에 있는' 종가.
        #   신규 일봉 호출은 0 이다.
        if ctx["snaps_cap"] is None or not len(ctx["snaps_cap"]):
            LOG.warn("KRX/pykrx 경로로 시총을 못 받았습니다 — 네이버 주식수 × 캐시 종가로 "
                     "폴백합니다(신규 일봉 호출 없음).")
            _pxc = VAULT.get_table("krx_ohlcv_daily", scope="shared")
            _sh = fetch_naver_shares()
            if _pxc is not None and len(_pxc) and len(_sh):
                ctx["snaps_cap"] = cap_snapshots_from_prices(_pxc, _sh, _sd)
                if len(ctx["snaps_cap"]):
                    VAULT.put_table("krx_marketcap_snapshots_approx", ctx["snaps_cap"],
                                    scope="shared", domain="universe",
                                    source="naver_shares_x_cached_close")
            elif not len(_sh):
                LOG.warn("네이버 주식수도 받지 못했습니다.")
            else:
                LOG.warn(f"일봉 캐시가 비어 있어 종가를 곱할 수 없습니다 "
                         f"(캐시 {0 if _pxc is None else len(_pxc):,}행).")

    with PIPE.stage("L1.PX", "가격 · 거래대금 (U-1000 후보만)", "L1", budget_s=2400):
        cand, cinfo = select_universe_candidates(ctx.get("snaps_cap"),
                                                 list(as_ts_series(ctx["cal"]["signal_date"])))
        all_codes = ctx["sec"]["code"].astype(str).tolist()
        if cand:
            ctx["candidates"] = cand
            LOG.table([["전 상장·폐지 종목", f"{len(all_codes):,}"],
                       ["신호일 평균 상장 종목", f"{cinfo.get('n_listed_avg', float('nan')):,.0f}"],
                       [f"후보 기준 K (하위 {U1000_N:,} × {CANDIDATE_BUFFER_MULT})",
                        f"{cinfo.get('K', 0):,}"],
                       ["일봉 수집 대상(후보 합집합)", f"{len(cand):,}"],
                       ["절감", f"{100*(1-len(cand)/max(1,len(all_codes))):.0f}%"],
                       ["절감의 출처", "백테스트 창 밖 폐지분 + 시총 상위 제외"]],
                      ["항목", "종목수"], ["l", "r"],
                      title="일봉 수집 대상 축소 — 시총 하위 후보만 받는다(§3.1)")
        else:
            # ★★ 예전에는 여기서 '전 종목 일봉을 받습니다'로 확대했다 ★★
            #   실패는 작업을 좁혀야지 넓히면 안 된다. 실측으로 pykrx import 하나가 깨지자
            #   후보 3,100 → 전 종목 5,398 로 늘고, 각 종목이 폴백 체인을 전부 타면서
            #   수집이 수십 분 폭주했다. 게다가 U-1000 은 '시총 하위 1000'으로 정의되므로
            #   시총이 없으면 유니버스를 만들 수 없다 — 느린 게 아니라 틀린 결과가 나온다.
            _why = []
            if pykrx_stock is None:
                _why.append("pykrx 사용 불가" + (f" ({IMPORT_FAILURES.get('pykrx','미설치')})"
                                                if "pykrx" in IMPORT_FAILURES else " (미설치)"))
            if not getattr(KRX, "session_ok", False):
                _why.append(f"KRX 마켓플레이스 미사용({getattr(KRX, 'status', '?')})")
            raise KillCriteria(
                "PIT 시가총액을 어느 경로로도 확보하지 못했습니다 — U-1000 은 '시총 하위 "
                f"{U1000_N:,}'으로 정의되므로 유니버스를 만들 수 없습니다.\n"
                f"  사유: {' · '.join(_why) or '시총 스냅샷 0건'}\n"
                "  전 종목 일봉을 대신 받는 것은 해결이 아닙니다 — 시총 없이는 어차피 "
                "유니버스가 구성되지 않고, 수집만 수 배로 늘어납니다.\n"
                "  네이버 주식수 × 캐시 종가 폴백도 시도했으나 실패했습니다(주식수 또는 "
                "일봉 캐시 없음).\n"
                "  조치: ① 윈도우에서 pykrx import 가 JSONDecodeError 로 깨지면 인코딩 "
                "문제입니다 — 환경변수 PYTHONUTF8=1 을 설정하고 커널을 재시작하거나 "
                "`pip install -U pykrx` 하십시오. "
                "② 일봉 캐시가 있는 폴더를 CACHE_MIRROR_ROOTS 에 추가하면 네이버 주식수만으로 "
                "시총을 만들 수 있습니다. "
                "③ KRX 마켓플레이스 로그인을 성공시키십시오. "
                "이미 받아둔 일봉 캐시는 그대로 보존되며 재실행 시 이어받습니다.")
        set_code_market(ctx["sec"])
        # 상장일·폐지일을 넘긴다. '캐시 최소일이 요청 시작일보다 늦다'가 결손인지 완결인지를
        # 가르는 1순위 증거이며, 이게 없으면 별도 원장에만 기대다가 캐시 전체를 다시 받는다.
        set_code_dates(ctx["sec"])
        px = fetch_prices(cand,
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        # 지수 격자에 없던 실거래일이 있으면 보강한다(지수 휴장·데이터 결손 대비).
        set_trading_days(px)
        ctx["cal"] = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.DART", "DART 재무 · 주식총수", "L1", budget_s=3600, critical=False):
        # ★★ 호출량 폭발의 진원지였다 ★★
        #   예전에는 전 상장사(폐지 포함 ~5,000)를 그대로 넘겼다. Tier-2(fnlttSinglAcntAll)는
        #   회사×연도×보고서마다 1회이므로 5,000 × 11 × 4 ≈ 220,000회 — 하루 한도가 2만이든
        #   4만이든 애초에 끝날 수 없는 설계였다. 실측으로 사용자 키가 하루 14,117회를 태웠다.
        #   가격에 적용한 '후보 먼저' 원칙을 여기에도 적용한다. 시총 하위 1000 전략이므로
        #   U-1000 후보 합집합 밖의 회사는 어느 분기에도 편입될 수 없다 = 재무가 필요 없다.
        _sec = ctx["sec"]
        _cand = set(ctx.get("candidates") or [])
        if _cand:
            _m = _sec[_sec["code"].astype(str).isin(_cand)]
            corps = _m["corp_code"].dropna().astype(str).unique().tolist()
            _all_n = _sec["corp_code"].dropna().nunique()
            LOG.table([["전 상장사 corp_code", f"{_all_n:,}"],
                       ["U-1000 후보로 축소", f"{len(corps):,}"],
                       ["절감", f"{100*(1-len(corps)/max(1,_all_n)):.0f}%"],
                       ["Tier-1 예상 호출", f"약 {math.ceil(len(corps)/100)*len(range(as_ts(BACKTEST_START).year-4, as_ts(BACKTEST_END).year+1))*(1 if DART_STATEMENT_FREQ=='annual' else 4):,}회 (100사 배치)"]],
                      headers=["DART 수집 범위", "값"],
                      title="DART 호출 범위 — 시총 하위 1000 전략이므로 후보 밖 회사는 받지 않는다")
        else:
            corps = _sec["corp_code"].dropna().astype(str).unique().tolist()
            LOG.warn(f"U-1000 후보를 못 만들어 전 상장사 {len(corps):,}개로 DART 를 받습니다 — "
                     f"호출량이 수만 회로 늘어납니다. 시총 스냅샷 단계를 먼저 확인하세요.")
        # 3년 소급이면 충분하다(roic_std3y · share_growth3y · TTM). 예전 -4 는 2012년을
        # 통째로 받았는데 어느 리밸런싱 시점에서도 읽히지 않는 연도였다.
        years = list(range(as_ts(BACKTEST_START).year - 3, as_ts(BACKTEST_END).year + 1))
        # ★★ priority 를 한 번도 넘기지 않고 있었다 ★★
        #   fetch_dart_financials 는 "끊겼을 때 남아 있는 것이 투자 가능한 종목의 최근
        #   데이터가 되도록" priority 순으로 받게 설계돼 있는데(12_ingest:248), 호출부가
        #   인자를 안 줘서 order={} → 정렬이 corp_code 알파벳순으로 붕괴했다. 그래서
        #   14,117 호출을 태우고도 확보된 회사가 시총 하위와 무관해 fin_cov 가 바닥이었고,
        #   §2.2 게이트가 매일 KillCriteria 로 죽였다. 호출 절감은 0이지만 '쓸모없는
        #   부분빌드'를 '쓸모있는 부분빌드'로 바꾸는 가장 값싼 한 줄이다.
        _prio = corps
        _sn = ctx.get("snaps_cap")
        if _sn is not None and len(_sn):
            _mc = (_sn.groupby("code", observed=True)["mktcap"].mean()
                     .rename("mc").reset_index())
            _mc["code"] = _mc["code"].astype(str)
            _pm = _m.merge(_mc, on="code", how="left").sort_values("mc", kind="stable")
            _prio = _pm["corp_code"].dropna().astype(str).drop_duplicates().tolist()
            LOG.info(f"DART 수집 우선순위: 시총 낮은 순 {len(_prio):,}사 — 한도로 끊겨도 "
                     f"U-1000 편입 가능성이 높은 종목부터 완성됩니다.")
        multi = fetch_dart_multi_accounts(corps, years)   # 100사 배치라 싸다 — 전 범위 유지

        # ★★ Tier-2 를 '수요 기반'으로 좁힌다 ★★
        #   예전: (후보 2,980사) × (15년) × (4보고서) = 178,800회 → 하루 2만이면 9일.
        #   지금: 그 회사가 실제로 시총 하위권이던 기간(+3년 소급) × 연간보고서.
        #   Tier-2 가 Tier-1 보다 더 주는 것은 매출원가(gp_a)와 영업CF(PCR·발생액) 둘뿐이고,
        #   둘 다 원논문(Novy-Marx · Sloan)이 연간으로 정의한다.
        _span = candidate_year_span(ctx.get("snaps_cap"), _sec,
                                    as_ts_series(ctx["cal"]["signal_date"]),
                                    U1000_N, DART_TIER2_BUFFER_MULT,
                                    lookback_years=DART_TIER2_LOOKBACK_Y)
        _rc = ([REPRT_CODES["FY"]] if str(DART_TIER2_FREQ).lower() == "annual"
               else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
        _yrs = sum(len(_span.get(c, ())) for c in corps) or (len(corps) * len(years))
        _naive, _scoped = len(corps) * len(years) * 4, _yrs * len(_rc)
        _lim = DBUDGET.remaining_calls() if DBUDGET is not None else None
        _d = float(_lim or DART_DAILY_LIMIT_HINT)
        LOG.table([["예전 (회사 × 전연도 × 4분기)", f"{_naive:,}", f"{_naive/_d:.1f}일"],
                   [f"대상=U-1000×{DART_TIER2_BUFFER_MULT} · 소급 {DART_TIER2_LOOKBACK_Y}년",
                    f"{_yrs*4:,}", f"{_yrs*4/_d:.1f}일"],
                   [f"+ Tier-2 빈도 = {DART_TIER2_FREQ}", f"{_scoped:,}", f"{_scoped/_d:.1f}일"],
                   ["오늘 잔여 호출", f"{_lim:,}" if _lim is not None else "미확정", ""]],
                  headers=["Tier-2 수집 계획", "필요 호출", "예상"],
                  title="DART Tier-2 — 회사별 API 라 job 수가 곧 콜드빌드 기간이다")
        if _lim and _scoped > _lim:
            LOG.warn(f"그래도 오늘 잔여({_lim:,})를 넘습니다. 시총 낮은 순으로 받으므로 오늘 "
                     f"확보되는 분은 U-1000 편입 가능성이 높은 종목부터입니다. Tier-1(주요계정)은 "
                     f"이미 전량 확보되어 V축·부채비율·자본잠식 판정은 오늘 백테스트가 그대로 "
                     f"돌아가고, gp_a·PCR·발생액만 커버리지가 낮게 시작합니다.")
        fs = fetch_dart_financials(corps, years, priority=_prio,
                                   only_years=_span, reprt_codes=_rc)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["fin"] = apply_t_plus_1(fin, "재무제표")
        # ★ 주식총수는 DART 로 받지 않는다. (corp × year) 마다 1호출이라 후보 2,000사 × 11년
        #   = 22,000회 — 그것 하나로 하루 한도를 태운다. 그런데 KRX 시총 스냅샷이 '상장주식수'를
        #   같은 호출에 이미 담아 준다(q21:288). 게다가 일별이라 DART 분기치보다 촘촘하고,
        #   '그 날 실제 주식수'라 정의상 PIT 이다. Q축 share_growth3y 는 이걸 쓰는 편이 낫다.
        #   DART 는 '자기주식(유동시총 보정)'에만 필요하므로, 다른 수집을 끝내고 호출이
        #   남을 때만 받는다 — 남으면 정밀도가 올라가고, 없어도 전략은 돌아간다.
        _left = DBUDGET.remaining_calls() if DBUDGET is not None else 0
        _need = len(corps) * len(years)
        if _left and _left >= _need:
            ctx["shares"] = fetch_dart_share_counts(corps, years)
        else:
            ctx["shares"] = shares_from_cap_snapshots(ctx.get("snaps_cap"), _sec)
            LOG.info(f"자기주식(DART 주식총수) 수집은 건너뜁니다 — 필요 {_need:,}회 / 잔여 "
                     f"{_left:,}회. 상장주식수는 KRX 시총 스냅샷에서 이미 확보되어 있어 "
                     f"Q축 주식수증가율({len(ctx['shares']):,}행)과 시총 계산은 그대로 동작하고, "
                     f"유동시총만 자기주식 미차감 근사가 됩니다.")
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
            # ★ 예전엔 수집기가 캐시를 아예 안 보고 매 실행 10년을 다시 훑었다(약 3시간).
            #   캐시가 확정한 지난 연도를 넘겨 그 해는 건너뛰게 한다. 올해는 항상 다시 훑는다.
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(
                    BACKTEST_START, BACKTEST_END,
                    skip_years=research_covered_years(cached, "hankyung")))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END,
                                   skip_years=research_covered_years(cached, "naver"))
                # 상세 보강은 U-1000 후보로만. 소비처(build_tp_revision)가 U-1000 패널에만
                # 붙으므로 후보 밖 종목의 목표주가는 어디에도 쓰이지 않는다.
                frames.append(naver_enrich_detail(nv, codes=ctx.get("candidates")))
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
               # ★ '설치됨'이 아니라 '실제로 import 되어 쓸 수 있는가'를 적는다. 예전 표는
               #   설치 여부만 봤고, 파이썬 3.14+윈도우에서 pykrx import 가 깨졌는데도
               #   "pykrx" 라고 표시했다 — 사용자는 원인을 볼 방법이 없었다.
               ["사용 가능 패키지", ", ".join(
                   n for n, o in (("FinanceDataReader", fdr), ("pykrx", pykrx_stock),
                                  ("yfinance", yf), ("pymupdf", fitz),
                                  ("pdfplumber", pdfplumber)) if o is not None) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    if IMPORT_FAILURES:
        LOG.table([[k, v[:88]] for k, v in IMPORT_FAILURES.items()],
                  ["패키지", "import 실패 사유"], ["l", "l"],
                  title="⚠ 설치는 되어 있으나 import 가 실패한 패키지 — 해당 수집 경로가 죽습니다")
        if "pykrx" in IMPORT_FAILURES:
            LOG.warn("pykrx 가 없으면 PIT 시가총액 스냅샷을 받을 수 없고, U-1000 은 시총 랭크로 "
                     "정의되므로 유니버스 자체가 구성되지 않습니다. 위 사유를 먼저 해결하세요 "
                     "(대개 파이썬 버전 호환 문제입니다 — `pip install -U pykrx` 또는 파이썬 "
                     "3.12 환경 사용).")

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

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 Q1~Q14", "L0", budget_s=180):
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
        # ★ §8.2 문언대로. X1~X3 에 3-A 가 섞이면 §10.2 의 귀속("1차=알파 / 배제·3-A=좌측꼬리")
        #   분해가 성립하지 않고, §8.3 BH-FDR 패밀리에 이질적 선정이 섞인다.
        #   X3 = "1차 + ΔNONFIN만" 이므로 배제플래그도 꺼야 한다.
        abl = [("X1", dict(stage="x1", use_rule3a=False),
                "1차만 — 깔때기 자체의 기여"),
               ("X2", dict(use_tone=False, use_nonfin=False, use_rule3a=False),
                "1차+배제플래그만 — 위험배제 효과"),
               ("X3", dict(use_tone=False, use_exclusion=False, use_rule3a=False),
                "1차+ΔNONFIN만 — 애널리스트 축 기여"),
               ("X4", dict(use_rule3a=False), "1차+2차, 3-A 없음 — 3-A 기여")]
        abl_names = []
        # ★ X0 = 스몰캡 벤치마크. U-1000 을 그대로 동일가중으로 담는다(1·2·3차 필터 전부 없음).
        #   깔때기의 초과수익을 '시장'이 아니라 '같은 유니버스의 무선별 보유'와 비교해야
        #   §10.2 귀속이 성립한다. KOSPI 대비 초과는 소형주 프리미엄일 뿐일 수 있다.
        try:
            _P0 = P.copy()
            _P0["u1000_all"] = _P0["in_u1000"].fillna(False).astype(bool) \
                if "in_u1000" in _P0.columns else True
            b0 = run_qbacktest(_P0, cal, "u1000_all", fwd, label="X0",
                               delist=ctx.get("delist_map") or {})
            # ★ EXPERIMENTS / abl_names 에는 넣지 않는다. 그 둘은 §8.3 BH-FDR 다중검정
            #   패밀리를 이룬다 — 벤치마크는 검정 대상 가설이 아니라 비교 기준선이므로
            #   패밀리에 섞으면 보정 대상 수만 부풀려 실제 가설들의 검정력을 깎는다.
            ctx["x0_smallcap"] = b0
            _s0 = qperf_stats(b0["returns"])
            LOG.table([["분기 평균 종목수", f"{float(b0['returns']['n'].mean()):,.0f}"],
                       ["CAGR (비용차감)", f"{_s0.get('cagr', float('nan')):+.2%}"],
                       ["Sharpe", f"{_s0.get('sharpe', float('nan')):.3f}"],
                       ["MDD", f"{_s0.get('mdd', float('nan')):.1%}"]],
                      headers=["X0 스몰캡 벤치마크 (U-1000 무선별 동일가중)", "값"],
                      title="깔때기 비교 기준선 — KOSPI 대비 초과는 소형주 프리미엄일 수 있다")
        except Exception as e:                                   # noqa
            LOG.warn(f"X0 스몰캡 벤치마크 산출 실패({type(e).__name__}) — 비교 기준선 없이 "
                     f"진행합니다. 깔때기 초과수익이 소형주 프리미엄인지 구분되지 않습니다.")
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, best_v, label=nm, quiet=True, **kw)
            summarize_experiment(nm, b, b["panel"], best_v, fwd, desc)
            abl_names.append(nm)
        report_experiment_table(abl_names, f"보조 어블레이션 (§8.2) — 최우수 변형 {best_v} 기준")

    with PIPE.stage("L5.FDR", "[13] BH-FDR 다중검정 보정", "L5", budget_s=120, critical=False):
        # §9-C2 는 'VQF 자신의 알파'가 아니라 'VQF − VQ 차이'의 유의성을 요구한다.
        # 차이검정을 같은 패밀리에 넣어야 다중검정 보정이 정직하다.
        _c2 = paired_diff_test("VQF-full", "VQ-full")
        ctx["c2_diff"] = _c2
        ctx["fdr"] = report_bh_fdr(main_names + abl_names, extra_tests=[_c2])

    with PIPE.stage("L5.ROBUST", "[13] 강건성 검사 (§8.4)", "L5", budget_s=4 * 3600, critical=False):
        bt_best = ctx.get(f"bt_{best_v}")
        R_subperiod(bt_best, best)
        R_size_quartile(bt_best, P, best)
        R_param_sensitivity(P, cal, fwd, best_v)
        R_weight_scheme(P, cal, fwd, best_v)

        def _rebuild_shift(sh: int, variant: str):
            cal2 = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END, shift_days=sh)
            # 수급 캐시가 '옮긴 신호일'로 다시 계산되도록 시프트를 알린다. 이게 없으면
            # 캐시 키가 같아 옮기지 않은 값을 재사용하고 F축 강건성 검정이 무효가 된다.
            globals()["QVF_REBAL_SHIFT_DAYS"] = int(sh)
            try:
                fl2 = fetch_flow_netbuy(cal2, ctx["px"], window=FLOW_WINDOW_DAYS)
                P2, uni2 = build_panel_pass1(ctx, cal2, fl2)
                P2 = build_panel_pass2(P2, ctx, cal2)
                ep2 = build_exec_prices(cal2, ctx["px"])
                fwd2 = build_forward_returns(ep2, cal2, uni2.delisting_map(), ctx["px"])
                b = run_experiment(P2, cal2, fwd2, variant, label=f"shift{sh}", quiet=True)
            finally:
                globals()["QVF_REBAL_SHIFT_DAYS"] = 0
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
        report_cell_ladder()
        report_discretion_ledger()
        # ★ 폐기 판정은 마지막에 둔다. STOP_ON_KILL_CRITERIA=True 면 여기서 KillCriteria 를
        #   던져 '폐기된 전략의 최종 편입 종목표'가 출력되는 것을 막는다(§10.4 의 이행).
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
