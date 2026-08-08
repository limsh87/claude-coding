#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  TCD v3 — 전략 3 · CORE-D + EMP-LITE   [TCD_V3_CORE_D_EMP_LITE]
#  DART 직원현황 기반 「한계임금」 전환 코어
#  백테스트 구간: 2016-08-01 ~ 2026-07-31 (10년)
#
#  ── 이 파일 하나로 끝납니다 ───────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v3_core_d_emp_lite.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정(C1·C2·C13·C15·원칙1~7)
#     [1] 합성데이터 엔드투엔드 스모크 (실데이터 쓰기 전 '계산경로' 증명)
#     [2] 실경로 리허설 (네트워크만 가짜로 두고 '수집함수'를 실물 실행)
#     [3] CANARY K1~K9  ← 여기서 막히면 몇 시간을 아낍니다
#     [4] 데이터 수집 (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [5] 원장 무결성 감사 (보고서 ↔ 애널리스트 ↔ 종목 다중소스 연결)
#     [6] PIT 유니버스 + 감쇠 감사 → L1 센서 → EMP 커버리지 감사(§6)
#     [7] TP 조립(clip×clip) → 거부권 → Signal → 백테스트
#     [8] 성과 검증표 (자체측정 벤치마크 대비)
#     [9] 강건성 R0·R1·R2-N⭐·R3·R5·R7·R8·R10
#    [10] 해석표 · 진단카드 · 데이터흐름 지도 · 런타임 감사 → 산출물 다운로드
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
#
#   ▣ 이 전략이 재는 것 ─────────────────────────────────────────────────────────────────────
#
#     한계임금 = Δ(연간급여총액) / Δ(직원수)
#     임금프리미엄 = 한계임금 / 전기 1인평균급여액
#
#       wage_premium < 1  →  저임금 대량채용. 정책보조금 유인 채용 의심
#       wage_premium > 1  →  기존보다 비싼 사람을 뽑음. 진짜 역량 확충
#
#     정책 오염 필터가 별도 패치가 아니라 **산식 자체에 내장**되어 있다는 것이 핵심 가치다.
#
#   ▣ 이 파일의 존재 이유 (R2-N) ────────────────────────────────────────────────────────────
#
#     국민연금 사업장 데이터(월 해상도)로 정밀화할 수 있으나 사업자번호 퍼지매칭에 6시간+.
#     **그 투자를 하기 전에, DART 직원현황(연 1회)만으로 이 신호가 나이브 지표를 이기는지**
#     부터 판정한다. 판정 결과(r2n_verdict)가 이 파일의 핵심 산출물이다.
#     유리하게 해석하지 않는다. C ≈ max(A,B) 면 그대로 "무기여"라고 쓴다.
#
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  ①  사용자 설정 — 여기만 채우면 됩니다  (아래는 손대지 않아도 됩니다)
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 한글로 로그에 남깁니다. 조용히 실패하지 않습니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다(RUN_MODE="CACHED").
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  ★ 이 전략의 필수 입력 ──────────────────────────────────────────
#
#    발급 경로 : https://opendart.fss.or.kr
#                → 회원가입 → 상단 [인증키 신청/관리] → [API 인증키 신청] → 즉시 발급(무료)
#    형식      : 40자리 소문자+숫자 (예: "a1b2c3d4e5f6...")
#    한도      : 1일 20,000건. 이 코드가 잔여량을 추적하고 자동 스로틀합니다.
#
#    ▶ 없으면: 재무(CORE-D)·직원현황(EMP-LITE)이 전부 결측 → 이 전략은 성립하지 않습니다.
#      (그래도 크래시 없이 끝까지 돌면서 "무엇이 없어서 무엇이 죽었는지"를 표로 보여줍니다)
DART_API_KEY = ""

# ── ② KRX 데이터 마켓플레이스  (2025-12 인증방식 변경 대응) ─────────────────────────────────
#
#    가입 경로 : https://data.krx.co.kr → 우측 상단 [회원가입] (무료)
#                가입 시 쓴 **아이디와 비밀번호**를 그대로 아래에 넣으세요.
#
#    ▶ 비워두셔도 됩니다. 이 코드의 가격 수집은 4중 폴백 체인입니다:
#         pykrx → FinanceDataReader → 네이버 금융 차트 → yfinance
#      KRX 마켓플레이스는 '검증·보강' 경로이며, 비우면 그 단계만 건너뜁니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서
#      1회만 하고 호출을 직렬화해 스스로 충돌하지 않지만, '바깥' 세션까지 막을 수는 없습니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""
#    (선택) KRX Open API 인증키. 엔드포인트별 '이용신청'이 따로 필요하고 승인에 하루 정도
#           걸립니다 — 키만 넣는다고 즉시 되지 않습니다. 없으면 위 체인이 대신합니다.
KRX_OPENAPI_KEY = ""

# ── ③ 공공데이터포털  (선택 — R10 정책반증 캘린더 보강용) ───────────────────────────────────
#    발급: https://www.data.go.kr → 로그인 → API 상세 → [활용신청]
#          → 마이페이지 > 데이터활용 > Open API > 인증키
#    ★ 반드시 "일반 인증키(Decoding)" 를 넣으세요. Encoding 키(%2B, %3D 포함)를 넣으면
#      이중 인코딩으로 SERVICE_KEY_IS_NOT_REGISTERED 가 납니다(코드가 감지해 경고합니다).
DATA_GO_KR_KEY = ""
CUSTOMS_API_KEY = ""          # 이 전략은 쓰지 않습니다 (코어 호환용 자리)

# ── ④ 구글드라이브 캐시  ★★★ 절대 1원칙 ★★★ ───────────────────────────────────────────────
#
#    이 코드는 기존 캐시·인덱스를 **절대 삭제하거나 덮어쓰지 않습니다.**
#    약속이 아니라 구조로 보장합니다:
#      1. 인덱스의 진실은 append-only JSONL 저널입니다. 기존 줄을 다시 쓰지 않습니다.
#      2. index.parquet 은 저널의 파생물일 뿐이며, 재생성 전 항상 타임스탬프 백업을 뜹니다.
#         백업에 실패하면 컴팩션 자체를 건너뜁니다(저널이 원천이므로 유실 없음).
#      3. 컬럼은 합집합으로만 확장합니다. 다른 전략이 쓰던 컬럼을 떨어뜨리지 않습니다.
#      4. blob 은 내용해시 경로에 씁니다. 같은 내용은 재기록조차 하지 않습니다.
#      5. 이미 드라이브에 있던 리포트는 이동·개명 없이 **경로만 등록**합니다(adopt-by-reference).
#      6. 삭제 API 자체가 없습니다. 손상 파일조차 지우지 않고 `.corrupt` 로 격리만 합니다.
#
#    GDRIVE_ROOT      : 캐시 최상위 루트
#    GDRIVE_SHARED_NS : 공용 인덱스 — 다른 전략도 그대로 재사용 (가격·재무·직원·보고서 원장)
#    GDRIVE_PRIVATE_NS: 전용 인덱스 — 이 전략 고유 (피처패널·스코어·백테스트·판정문)
#    ▸ 기본값은 Colab 기준입니다. JupyterLab(로컬)에서는 구글드라이브 '데스크톱' 동기화
#      폴더를 자동으로 찾습니다 — Windows 의 드라이브 문자(G:/내 드라이브 …), macOS 의
#      ~/Library/CloudStorage/GoogleDrive-<계정>/My Drive 를 모두 훑습니다.
#      자동탐지가 실패하면 홈 폴더로 폴백하며 그 사실을 경고로 남깁니다. 그때는 아래 한 줄을
#      실제 경로로 바꾸세요.  예)  GDRIVE_ROOT = r"G:/내 드라이브/tcd_cache"
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"
GDRIVE_PRIVATE_NS = "tcd_v3_core_d_emp"

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요.
#      재귀 스캔해서 **등록만** 합니다. 파일을 옮기거나 지우지 않습니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽입니다.
#      None 이면 Path.home()/tcd_cache 를 씁니다. /content 를 하드코딩하지 않습니다.
LOCAL_CACHE_ROOT  = None

# ── ⑤ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑥ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12      # 네트워크 병렬(스레드). 차단이 잦으면 8로 낮추세요.
N_WORKERS_CPU  = 0       # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {       # 소스별 초당 요청 상한 — 차단 방지. 낮출수록 안전/느림.
    "dart":      8.0,    # OpenDART 공식 권고 상한 근방
    "hankyung":  2.5,
    "naver":     3.0,
    "krx":       2.0,
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0     # 초과가 예상되면 청크 처리로 자동 전환

# ── ⑥-b DART 호출 예산  ★ 4시간 계약(§12-6)을 지키는 유일한 장치입니다 ─────────────────────
#
#    DART 재무는 2층 구조입니다.
#      Tier-1  fnlttMultiAcnt     : 1회 호출로 100사 — 매출·영업이익·순이익·자산·부채·자본
#                                   전 종목 10년치가 2,000여 회(≈5분)로 끝납니다. 항상 받습니다.
#      Tier-2  fnlttSinglAcntAll  : 1회 호출로 1사×1기간 — 재고·매출채권·영업CF·CAPEX 까지
#                                   전 계정. **호출 수가 기업×연도×분기로 곱해집니다.**
#                                   3,981사 × 13년 × 4분기 = 207,012회 = DART 일일한도 기준 11일.
#
#    그래서 Tier-2 는 반드시 상한을 겁니다. 상한 안에서 '투자 가능한 종목의 최근 연도'부터
#    채우므로, 첫 실행에서도 백테스트는 끝까지 돌아가고 재실행할 때마다 커버리지가 올라갑니다.
#    ★ 하루 예산은 19,000 이고 **모든 단계가 이 하나를 나눠 씁니다.**
#      Tier-1 배치 ≈2,100 + CANARY ≈600 은 고정비이고, Tier-2 는 잡당 OFS→CFS 로 최대 2회를
#      던지므로 실제 호출은 상한의 2배까지 갑니다. 계약 §12-6 이 이 합을 검사합니다.
#
#    ▶ 기본값을 0 으로 둔 이유 — 직원현황(알파)이 아직 0행이기 때문입니다.
#      재무는 이미 공용 캐시에 146만 행이 있고 Tier-1 이 유니버스·규모버킷·R3 를 받쳐 줍니다.
#      반면 한계임금은 empSttus 없이는 계산 자체가 불가능합니다. 그래서 알파가 찰 때까지
#      하루 예산을 직원현황에 몰아줍니다. **EMP 커버리지가 충분해지면 6000 정도로 올리세요**
#      (그때 §12-6 이 합계를 다시 검사해 줍니다).
DART_FS_MAX_CALLS   = 0        # 0 = Tier-2 생략(Tier-1 주요계정으로 대체). 실측 5건/초.
                               # None 으로 두면 상한 없음 = 며칠짜리 콜드빌드(4시간 계약 밖).
DART_FS_FREQ        = "annual"  # "annual" = 사업보고서(FY)만 → 호출 1/4. 첫 실행 권장.
                                # "quarterly" = 분기까지. TTM 정밀도는 오르지만 4배 비쌉니다.
DART_FS_UNIVERSE_ONLY = True   # True = U-MID 투자가능 대역에 한 번이라도 든 종목만 Tier-2 수집.
                               # 애초에 담을 수 없는 종목의 전체 재무제표는 백테스트에 안 쓰입니다.
DART_FS_WARMUP_Y      = 3      # 백테스트 시작연도보다 몇 년 더 과거까지 받을지(TTM·전년대비용)

# ── ⑦ 애널리스트 리포트 (한경컨센서스 · 네이버 리서치) ──────────────────────────────────────
#    이 전략에서의 용도: U(반영도)축의 컨센서스 보강 + 다중소스 원장연결 감사.
#    드라이브에 이미 캐시가 있으면 그것을 최우선으로 재사용합니다.
RESEARCH_COLLECT       = True     # False = 드라이브 캐시에 있는 것만 사용(신규 수집 안 함)
RESEARCH_SOURCES       = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF  = False    # v3 기본 False — PDF 는 용량·시간이 크고 U축 기여가 제한적
RESEARCH_PDF_MAX_PER_MONTH = 0    # 0 = 무제한
RESEARCH_TARGET_PER_YEAR   = 30000
#   ▸ ★ 네이버 '상세 보강'(리포트 1건당 1요청)은 이 파이프라인에서 가장 비싼 단계입니다.
#     실측 45,000건 대상 → 20,000건만 해도 1시간 44분(2.99건/초). §10 수집 총예산이 95분인데
#     보조축 하나가 그 배를 먹습니다. 게다가 실측 수율이 '목표주가 0건 추가 확보'였습니다.
#     0 = 생략(권장) · 10 = 10분만 · None 은 쓰지 마세요.
RESEARCH_ENRICH_MAX_MIN    = 0

# ── ⑧ 포지션 / 사이징  (드로다운 한가운데서 정하지 않도록 상수로 못박음) ────────────────────
PORTFOLIO_TOP_PCT       = 0.05
PORTFOLIO_MAX_NAMES     = 25
PORTFOLIO_MIN_NAMES     = 5
POS_MAX_WEIGHT          = 0.12
POS_MIN_WEIGHT          = 0.02
POS_ADV_PARTICIPATION   = 0.10
HOLD_MAX_MONTHS         = 24
ACCOUNT_KRW             = 30_000_000
MIN_ADV_KRW             = 300_000_000     # V6 유동성 하한: 20일 평균거래대금

# ── ⑨ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전 출력물을 예행연습 (수십 초). 네트워크·키 불필요.
#              백테스트·성과·강건성·해석표가 전부 나옵니다. ★ 처음엔 이걸로 한 번 돌리세요.
#    "FULL"  : 스모크 → 리허설 → CANARY → 실데이터 수집 → 백테스트 → 강건성 (기본값)
#    "CACHED": 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트
RUN_MODE = "FULL"

SEED = 20260807                 # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True    # §12 킬 기준 위반 시 즉시 중단하고 그대로 보고 (끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   ⚙️  ②  전략 파라미터 — 스펙 §4·§7·§8 을 코드로 못박은 값들
#          바꾸면 스펙 위반이 되는 값에는 ★ 를 붙였습니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── C15: 한계임금 분모 안정성 (스펙 §4) ─────────────────────────────────────────────────────
C15_MIN_ABS_DN      = 5          # ★ (a) |Δ직원수| 최소 절대 하한
C15_MIN_REL_DN      = 0.03       # ★ (a) |Δ직원수| 최소 상대 하한 (직원수_{t-1} 대비)
C15_PREMIUM_LO      = 0.0        # ★ (b) 임금프리미엄 클리핑 하한
C15_PREMIUM_HI      = 5.0        # ★ (b) 임금프리미엄 클리핑 상한 (초과는 오류로 보고 NaN)
C15_MIN_OBS_PER_YR  = 200        # ★ (c) 연도별 유효관측치 하한 — 미달이면 TP_N1 비활성화
C15_MNA_UP          = 1.00       # ★ (d) Δ직원수 +100% 초과 = M&A·분할 의심 → 결측
C15_MNA_DN          = -0.50      # ★ (d) Δ직원수 -50% 미만 = 분할·매각 의심 → 결측

# ── §6 커버리지 판정: 연도별 유효관측치가 이 값 미만인 앞구간은 백테스트 창에서 제외 ─────────
COVERAGE_MIN_OBS_START = 400
COVERAGE_AUTO_TRIM     = True    # True = 판정에 따라 시작월을 자동 상향하고 리포트에 명시

# ── §8 셀 정규화 ────────────────────────────────────────────────────────────────────────────
CELL_KEYS_V3   = ["month", "ind_mid", "size_bucket"]   # ★ 3단계 규모버킷
CELL_MIN_N_V3  = 8               # ★ 셀 표본 하한. 미달이면 규모버킷 없는 상위 셀로 폴백
SIZE_BUCKET_N  = 3               # ★ 규모버킷 3단계

# ── ⑧-b 비교 유니버스 (스몰캡 팔) ───────────────────────────────────────────────────────────
#    같은 신호·같은 규칙을 **규모 대역만 바꿔** 한 번 더 돌려 나란히 출력합니다.
#    한계임금 신호가 중형주 고유인지, 소형주에서 더 강한지를 한 실행에서 판정하기 위함입니다.
#    ▸ 유동성 하한(MIN_ADV_KRW)은 **낮추지 않습니다.** 낮추면 실제로 체결할 수 없는 종목이
#      섞여 성과가 부풀려지고, 그 순간 비교의 의미가 사라집니다.
RUN_SMALLCAP_ARM = True          # False = 메인(U-MID)만 실행
SMALL_RANK_LO, SMALL_RANK_HI = 1401, 2400   # 거래대금 랭크 하위 1,000 구간

# ── §8 증거층(E) 구성 ───────────────────────────────────────────────────────────────────────
TP_CORE_D = ["TP_I1", "TP_I2", "TP_I4", "TP_P1", "TP_P2"]   # CORE-D 기본 골격
TP_EMP    = ["TP_N1", "TP_N2", "TP_N3"]                     # EMP-LITE (이 전략의 차별점)
TP_ALL    = TP_CORE_D[:3] + TP_EMP + TP_CORE_D[3:]          # 스펙 §8 표 순서

#   최소 관측 TP 수 — 관측된 TP 가 1개뿐인 종목이 그 하나로 E 상위를 차지하는 것을 막는다.
#   스펙에 명시된 규칙은 아니므로 R5 절제검사에서 이 경계값의 민감도를 반드시 함께 출력한다.
MIN_TP_OBSERVED = 3

# ── §7 V8 거부권 (정책오염 직접관측) ────────────────────────────────────────────────────────
V8_EMP_TOP_Q   = 0.80            # ★ nl_emp 상위 20%
V8_TAX_DROP    = -0.03           # ★ Δ실효세율 < -3%p

# ── §5 empSttus 수집 범위 ───────────────────────────────────────────────────────────────────
EMP_YEARS_BACK = 2               # 백테스트 시작연도보다 몇 년 더 과거까지 받을지(차분에 필요)
EMP_MAX_CORPS  = 0               # 0 = 제한 없음. 테스트 시 300 등으로 줄이면 빨라집니다.
#   ▸ empSttus 도 |기업| × |연도| 로 곱해집니다(3,981사 × 13년 = 51,753 > 일일한도 19,000).
#     한계임금은 이 전략의 알파 원천이라 DART 일일예산을 **Tier-2 재무보다 먼저** 여기에 씁니다.
#     상한에 걸리면 '담길 확률이 높은 종목 × 최근 연도'부터 채우고 재실행 시 이어받습니다.
EMP_MAX_CALLS  = 14_000          # 실측 8건/초 → ≈30분. None = 상한 없음(4시간 계약 밖).
EMP_UNIVERSE_ONLY = True         # True = U-MID 대역을 한 번이라도 경험한 종목만 수집.
                                 # 셀 정규화도 U-MID 패널 안에서만 하므로 제외분은 안 쓰입니다.
#   ▸ ★ 직원현황은 이 전략의 **유일한 알파 원천**입니다(TP_N1·N2·N3).
#     재무 캐시가 아무리 많아도 이게 비면 '전략 3' 이 아니라 다른 전략이 됩니다.
#     True = 알파가 비어 있으면 수집을 시작하기 전에 멈춥니다(2시간 낭비 방지).
#     CORE-D 5개 TP 만으로 축소 실행해 보고 싶을 때만 False 로 두세요.
REQUIRE_EMP_ALPHA = True
#   ▸ 직원현황 전용 예산 하한. 다른 단계가 아무리 많이 써도 이만큼은 EMP 몫으로 남깁니다.
#     이것이 없으면 Tier-2 재무가 일일 한도를 먼저 다 써버려 알파가 영원히 안 모입니다
#     (실제로 3회 실행 내내 dart_employees_ext 가 0행이었던 이유입니다).
EMP_RESERVED_CALLS = 14_000

# ── §2 CANARY 임계값 ────────────────────────────────────────────────────────────────────────
CANARY_SAMPLE_N     = 200        # 표본 종목수 (K3·K4·K7·K8·K9)
CANARY_K1_MIN_ROWS  = 100_000    # K1 PASS 조건
CANARY_K3_MIN_COV   = 0.85       # K3 필수계정 커버리지
CANARY_K7_MIN_RATE  = 0.80       # K7 empSttus 응답 성공률
CANARY_K8_MIN_RATE  = 0.70       # K8 연간급여총액 기재율
CANARY_K9_MAX_BAD   = 0.05       # K9 단위 불일치(10배+) 허용 비율

# ── §11 강건성 예산 (초) — 초과하면 그 검사만 건너뛰고 사유를 남깁니다 ──────────────────────
ROBUST_BUDGET_S = {"R0": 240, "R1": 360, "R2N": 300, "R3": 120,
                   "R5": 420, "R7": 60, "R8": 60, "R10": 300}

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID    = "TCD_V3_CORE_D_EMP_LITE"
STRATEGY_NAME  = "CORE-D + EMP-LITE (DART 직원현황 기반 한계임금 전환 코어)"
BUILD_VERSION  = "v3.20260808.0407"
ACTIVE_PACKS   = ["CORE_D", "EMP_LITE"]        # 진단 출력용 라벨 (레지스트리 없음 — 경량화)


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
        # ★ yfinance 는 실패 종목마다 ERROR 한 줄을 직접 찍는다. 한국 폐지종목은 .KS/.KQ 양쪽이
        #   모두 없으므로 종목당 2줄 — 1,800종목이면 3,600줄이 진단 로그를 덮어버린다.
        #   실패 사실은 fetch_prices 의 시도 원장(price_fetch_attempts)에 이미 남으므로
        #   여기서는 라이브러리 자체 출력만 CRITICAL 로 올려 침묵시킨다(예외는 그대로 전파).
        for _n in ("yfinance", "yfinance.data", "yfinance.utils", "peewee", "urllib3"):
            logging.getLogger(_n).setLevel(logging.CRITICAL)
        try:
            yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), "py-yfinance"))
        except Exception:
            pass
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
# ║  L0-E  캐시 루트 해석 + 런타임 예산 추적  (스펙 §3 · §10)                                  ║
# ║                                                                                          ║
# ║  스펙 §3: "Colab: drive.mount, 실패시 /content/tcd_cache.                                 ║
# ║            JupyterLab: Path.home()/tcd_cache. /content 하드코딩 금지."                     ║
# ║  → 코어의 _mount_drive() 는 LOCAL_CACHE_ROOT 를 그대로 돌려주므로 None 이면 죽는다.        ║
# ║    v3 는 그 앞단에서 '환경별 기본값'을 먼저 확정한다.                                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def resolve_local_cache_root() -> str:
    """LOCAL_CACHE_ROOT 가 비어 있을 때 환경에 맞는 기본 경로를 만든다.

    ★ /content 를 하드코딩하지 않는다. Colab 이 아닌 곳에서 /content 를 쓰면 권한 오류가
      나거나(리눅스 루트 직하), 최악의 경우 컨테이너 종료와 함께 캐시가 통째로 사라진다.
    """
    v = globals().get("LOCAL_CACHE_ROOT")
    if isinstance(v, str) and v.strip():
        return os.path.abspath(os.path.expanduser(v.strip()))
    if ENV.get("colab"):
        return "/content/tcd_cache"
    try:
        from pathlib import Path as _P
        return str(_P.home() / "tcd_cache")
    except Exception:
        return os.path.abspath("./tcd_cache")


def mount_cache_v3() -> Tuple[str, str]:
    """(루트경로, 상태). 어느 환경에서도 절대 None 을 돌려주지 않는다.

    우선순위
      Colab      : drive.mount → GDRIVE_ROOT           (실패 시 로컬 폴백)
      Jupyter/CLI: 이미 동기화된 드라이브 경로가 있으면 그것 → 없으면 홈 아래 로컬
    """
    local = resolve_local_cache_root()
    if ENV.get("colab"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                LOG.info("구글드라이브 마운트를 시도합니다. 브라우저에서 권한을 승인해 주세요.")
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                os.makedirs(GDRIVE_ROOT, exist_ok=True)
                return GDRIVE_ROOT, "COLAB_DRIVE"
            LOG.warn("드라이브가 마운트되지 않았습니다 — 로컬 캐시로 폴백합니다. "
                     "이번 실행의 수집물은 세션 종료 시 사라질 수 있습니다.")
            return local, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                                  # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return local, "COLAB_MOUNT_ERROR→LOCAL"

    # JupyterLab / CLI — 드라이브 데스크톱이 동기화해 둔 경로가 있으면 그것을 우선한다.
    for c in _gdrive_desktop_candidates():
        if c and os.path.isdir(c):
            os.makedirs(c, exist_ok=True)
            return c, "LOCAL_SYNCED_DRIVE"
    # 캐시 폴더는 없지만 드라이브 자체는 붙어 있는 경우 → 거기에 만들어 준다.
    #   ★ 이것이 없으면 첫 실행에서 조용히 홈 폴더로 폴백해, 수집물이 드라이브에
    #     한 줄도 남지 않는다(사용자 절대1원칙 위반). 부모가 실재할 때만 만든다.
    for c in _gdrive_desktop_candidates():
        par = os.path.dirname(c.rstrip("/\\"))
        if par and os.path.isdir(par):
            try:
                os.makedirs(c, exist_ok=True)
                LOG.ok(f"구글드라이브(데스크톱 동기화) 안에 캐시 폴더를 새로 만들었습니다: {c}")
                return c, "LOCAL_SYNCED_DRIVE"
            except Exception:
                continue
    os.makedirs(local, exist_ok=True)
    # ★ '못 찾았다'만 말하면 사용자는 무엇을 고쳐야 할지 모른다. 실제로 뒤진 경로를 보여준다.
    tried = _gdrive_desktop_candidates()
    LOG.warn(f"구글드라이브 경로를 찾지 못해 로컬({local})에 저장합니다.\n"
             f"     뒤져본 경로 {len(tried)}개 중 앞부분: {tried[:6]}\n"
             f"     드라이브에 남기려면 상단 GDRIVE_ROOT 를 실제 경로로 바꾸세요. 확인 방법:\n"
             f"       · Windows 탐색기에서 구글 드라이브를 열고 주소창 경로를 복사\n"
             f"         예)  GDRIVE_ROOT = r\"G:/내 드라이브/tcd_cache\"\n"
             f"       · macOS  ~/Library/CloudStorage/GoogleDrive-<계정>/My Drive/tcd_cache\n"
             f"     ※ 로컬에 저장해도 백테스트는 정상 동작합니다. 다음 실행에서 드라이브 경로를 "
             f"지정하면 이 폴더를 GDRIVE_ADOPT_DIRS 에 넣어 그대로 흡수할 수 있습니다 "
             f"(파일 이동·삭제 없음).")
    return local, "LOCAL"


def _win_drivefs_roots() -> List[str]:
    """구글드라이브(데스크톱)가 **스스로 기록해 둔** 마운트 지점을 읽는다.

    ① 레지스트리 DefaultMountPoint — 정책(HKLM\\Policies) > 시스템 > 사용자 순.
       드라이브 문자일 수도, '%USERPROFILE%\\GFS' 같은 확장 경로일 수도 있다.
    ② %LOCALAPPDATA%\\Google\\DriveFS\\root_preference_sqlite.db
       media.last_mount_point = 실제로 마운트했던 지점,
       roots.last_seen_absolute_path = 미러링 폴더(문자 스캔으로는 절대 못 찾는 경로).
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
                for q, colname in (("SELECT last_mount_point FROM media", 0),
                                   ("SELECT last_seen_absolute_path FROM roots", 0)):
                    try:
                        for row in con.execute(q):
                            p = str(row[colname] or "").strip()
                            if p:
                                out.append(p + ":\\" if len(p.rstrip(":")) == 1 else p)
                    except Exception:
                        continue
            finally:
                con.close()
    except Exception:
        pass
    # 루트 아래의 '내 드라이브' 계열 하위폴더도 후보에 넣는다(폴더 마운트 대응).
    kids = ("My Drive", "내 드라이브", "Shared drives", "공유 드라이브")
    return out + [os.path.join(r, k) for r in list(out) for k in kids]


def _gdrive_desktop_candidates() -> List[str]:
    """구글드라이브 '데스크톱' 동기화 폴더 후보. 환경마다 이름이 다르다.

    Windows 는 드라이브 문자(G:, H: …)로 붙고 한국어 계정은 '내 드라이브'다.
    macOS 는 최신 버전이 ~/Library/CloudStorage/GoogleDrive-<메일>/My Drive 로 바뀌었다.
    이 목록을 갖고 있지 않으면 JupyterLab 사용자는 매번 홈 폴더로 폴백한다.
    """
    out: List[str] = [GDRIVE_ROOT] if GDRIVE_ROOT else []
    leaf = os.path.basename(str(GDRIVE_ROOT).rstrip("/\\")) or "tcd_cache"
    home = os.path.expanduser("~")
    roots: List[str] = []
    if platform.system() == "Windows":
        # ★ 드라이브 문자를 훑는 것만으로는 못 찾는다. 구글 드라이브는 (a) 드라이브 문자
        #   (b) **임의의 빈 폴더** (c) 미러링 모드의 로컬 폴더 중 하나로 붙을 수 있고,
        #   (b)(c)는 어떤 문자 스캔으로도 발견되지 않는다. 실제로 사용자 환경에서 못 찾았다.
        #   → 드라이브 자신이 기록해 둔 설정을 먼저 읽는다. 추측보다 조회가 정확하다.
        roots += _win_drivefs_roots()
        letters = "DEFGHIJKLMNOPQRSTUVWXYZ"     # 기본은 G: 지만 사용자가 바꿀 수 있다
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()      # type: ignore[attr-defined]
            live = "".join(L for L in letters if mask >> (ord(L) - ord("A")) & 1)
            letters = live or letters          # 비트마스크는 '힌트'다. 실패해도 스캔은 한다.
        except Exception:
            pass
        for L in letters:
            roots += [f"{L}:/내 드라이브", f"{L}:/My Drive", f"{L}:/공유 드라이브"]
        roots += [os.path.join(home, n) for n in
                  ("My Drive", "내 드라이브", "Google Drive", "GoogleDrive")]
    roots += [os.path.join(home, "Google Drive", "My Drive"),
              os.path.join(home, "Google Drive", "MyDrive"),
              os.path.join(home, "GoogleDrive", "MyDrive"),
              os.path.join(home, "내 드라이브")]
    cs = os.path.join(home, "Library", "CloudStorage")
    try:
        for d in sorted(os.listdir(cs)):
            if d.startswith("GoogleDrive"):
                roots += [os.path.join(cs, d, "My Drive"), os.path.join(cs, d, "내 드라이브")]
    except Exception:
        pass
    out += [os.path.join(r, leaf) for r in roots]
    seen, uniq = set(), []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


# ── 런타임 예산 추적 (§10) ──────────────────────────────────────────────────────────────────
RUNTIME_ROWS: List[dict] = []
_RUNTIME_BUDGET_MIN = {
    "L0.준비": 3, "CANARY": 25, "수집": 95, "L1.센서+커버리지": 5,
    "L2+L3.백테스트": 2, "R-SUITE": 26,
}
WALL_CLOCK_LIMIT_H = 4.0        # §12-6 — 초과하면 구조 재점검 경고를 띄운다


def runtime_mark(phase: str, seconds: float, note: str = ""):
    RUNTIME_ROWS.append({"phase": phase, "seconds": float(seconds),
                         "minutes": float(seconds) / 60.0,
                         "budget_min": _RUNTIME_BUDGET_MIN.get(phase, np.nan), "note": note})


def report_runtime_v3(t0: float) -> pd.DataFrame:
    total_s = time.time() - t0
    rows = []
    for r in RUNTIME_ROWS:
        b = r["budget_min"]
        verdict = "-" if not np.isfinite(b) else ("초과" if r["minutes"] > b * 1.5 else "예산내")
        rows.append([r["phase"], f"{r['minutes']:.1f}",
                     "-" if not np.isfinite(b) else f"{b:.0f}", verdict, _trunc(r["note"], 40)])
    rows.append(["── 합계", f"{total_s/60:.1f}", "153", "", ""])
    LOG.table(rows, ["단계", "실측(분)", "예산(분)", "판정", "비고"],
              ["l", "r", "r", "c", "l"], title="런타임 감사 (§10)")
    if total_s > WALL_CLOCK_LIMIT_H * 3600:
        LOG.warn(f"총 wall-clock {total_s/3600:.1f}시간 — §12-6 킬 기준(4시간)을 넘었습니다. "
                 f"파라미터가 아니라 구조를 재점검하세요(수집 범위·캐시 적중률).")
    return pd.DataFrame(RUNTIME_ROWS)


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
                   "corp_code", "industry", "sector_src", "src",
                   # 폐지 사유 — 백테스트가 청산가를 정할 때 쓴다. 흡수합병·완전자회사화·
                   # 스팩해산을 -100% 로 처리하면 없는 손실을 매년 지어낸다(41_backtest).
                   "delist_reason", "to_code"]

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
                # ★ 컬럼 목록을 자르지 않는다. [:6] 으로 자른 로그가 delisting CSV 의
                #   DelistingDate(7번째)를 가려, '상장일을 폐지일로 읽고 있다'는 오진을
                #   유발했다. 진단 출력이 진단을 방해하면 없느니만 못하다.
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} "
                          f"({len(df):,}행 · 컬럼 {list(df.columns)})")
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
    # ★ dl_c 폴백 목록에 "listingdate" 가 들어 있다. 업스트림이 DelistingDate 컬럼명을
    #   바꾸는 순간 상장일이 폐지일로 읽히고, 모든 종목이 상장 첫날 폐지된 것으로 처리되어
    #   유니버스가 통째로 비워진다 — 예외가 아니라 '그럴듯한 숫자'로 실패한다. 방어한다.
    if dl_c and str(dl_c).strip().lower().replace("_", "") == "listingdate":
        LOG.error("폐지목록에 폐지일 컬럼이 없어 상장일 컬럼을 쓸 뻔했습니다 — "
                  f"상장일을 폐지일로 읽으면 전 종목이 즉시 폐지 처리됩니다. "
                  f"폐지일 없이 진행합니다. 원본 컬럼: {list(d.columns)}")
        dl_c = None
    lst_c = next((col[k] for k in ("listingdate", "listing_date", "listdate") if k in col), None)
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        # 폐지 종목의 상장일 — 상장 전 달에 유니버스로 새는 것(C13)과 시즈닝 면제를 막는다.
        "listing_date": as_ts_series(d[lst_c]) if lst_c else pd.NaT,
        # 폐지 '사유'. 흡수합병·완전자회사화·스팩해산은 -100% 가 아니다(41_backtest 가 소비).
        "delist_reason": (d[col["reason"]].astype(str).str.strip() if "reason" in col else ""),
        "to_code": (d[col["tosymbol"]].map(to_code6) if "tosymbol" in col else None),
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str).str.strip() if "secugroup" in col
                      else d[col["kind"]].astype(str).str.strip() if "kind" in col else ""),
    })
    # ★ 탈락분의 정체를 반드시 증권종류로 분류한다.
    #   업스트림 원본(4,172행)을 직접 확인한 결과, to_code6 이 떨어뜨리는 1,536행은
    #   전부 신주인수권증서(857)·수익증권(521)·신주인수권증권(158)이고 **주권은 0건**이다.
    #   그런데 예전 코드는 이를 "코드형식 불일치 → 생존자편향이 그만큼 남습니다"로 경고했다.
    #   주식 전략의 유니버스가 아닌 파생·펀드 상품이 빠진 것을 편향으로 보고하면,
    #   ① 멀쩡한 결과를 의심하게 만들고 ② 진짜 편향 경고까지 같이 무시하게 만든다.
    #   → '정책적 제외'와 '진짜 유실'을 분리해서 세고, 주권이 유실될 때만 경고한다.
    _EQUITY_SG = ("주권", "외국주권", "주식예탁증권")
    sg = t["secugroup"].fillna("")
    is_equity = sg.isin(_EQUITY_SG) if sg.str.len().gt(0).any() else pd.Series(True, index=t.index)
    bad = t["code"].isna()
    n_badcode = int(bad.sum())
    n_lost_equity = int((bad & is_equity).sum())
    n_nonequity = int((~bad & ~is_equity).sum())
    if sg.str.len().gt(0).any() and n_badcode:
        LOG.info(f"  코드 정규화 탈락 {n_badcode:,}건의 증권종류: "
                 f"{dict(sg[bad].value_counts().head(5))} → 이 중 주권계열 {n_lost_equity:,}건")
    # ★ 비주권(수익증권·리츠·투자회사 등)은 여기서 **버리지 않는다.**
    #   폐지 기록을 지우면 그 종목이 유니버스에서 영원히 살아있는 것으로 보인다 — 제거하려던
    #   생존자편향을 오히려 만드는 방향이다. 담을 수 없는 종목은 U-MID 의 유동성·규모 조건이
    #   이미 걸러내므로, 여기서는 '분류해서 보고'만 하고 기록은 보존한다.
    t = t.dropna(subset=["code"])
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_nodate = int(t["delisting_date"].isna().sum())

    LOG.ok(f"상장폐지 목록 {len(t):,}건 (주권계열 {int(t['secugroup'].isin(_EQUITY_SG).sum()):,} · "
           f"비주권 {n_nonequity:,}) — 생존자편향 제거 입력 확보")
    if n_raw - len(t):
        LOG.info(f"  폐지목록 정규화: 원본 {n_raw:,} → {len(t):,} "
                 f"(증권종류상 코드체계가 다른 {n_badcode:,}건 제외 · 동일코드 중복 {n_dupe:,} 병합) · "
                 f"폐지일 결측 {n_nodate:,}건은 상장기간 추정에서 제외됩니다.")
    # ★ 경고는 '주권이 유실됐을 때'만 띄운다. 비주권 제외는 편향이 아니라 유니버스 정의다.
    if n_lost_equity:
        LOG.warn(f"폐지목록에서 **주권** {n_lost_equity:,}건이 코드 정규화에 실패했습니다 — "
                 f"이만큼은 실제로 생존자편향으로 남습니다. "
                 f"원본 코드 예시: {raw_codes[codes.isna() & is_equity].head(5).tolist()}")
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
                                   "listing_date", "delist_reason", "to_code"]).copy()
        # ★ 예전엔 여기서 listing_date 를 pd.NaT 로 못박았다. 그런데 폐지목록 원본에는
        #   ListingDate 가 4,172건 **전부** 들어 있다. 버리면 두 가지가 동시에 깨진다:
        #     ① Universe.at 는 listing_date 결측을 '태초부터 상장'으로 읽는다 →
        #        2016년 이후 상장했다가 폐지된 292종목이 상장 전 달의 유니버스에 낀다(C13 위반).
        #     ② 250일 시즈닝 게이트는 listing_date 가 있을 때만 걸린다 → 결측인 종목만
        #        면제된다. 그 면제 대상이 하필 '나중에 폐지된 종목'이라, 어느 종목이 게이트를
        #        건너뛰는지가 **그 종목의 미래로 결정**된다. 실거래로는 재현 불가능한 유니버스다.
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
        delist_reason=("delist_reason", _first_str),
        to_code=("to_code", _first_str),
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
    # ★ 이름은 FDR 이지만 6자리 KRX 코드는 FinanceDataReader 내부에서 NaverDailyReader 로
    #   라우팅된다(fchart.stock.naver.com). 즉 KRX 가 아니라 네이버다. 그런데 예전엔
    #   krx 버킷(2.0 qps)의 토큰을 먹었다. RateLimiter 는 소스당 전역 단일 간격이라
    #   12스레드가 0.5초 슬롯 하나를 나눠 쓰게 되고, 실효 동시성이 1로 떨어진다.
    #   실측: 1,833건 × 0.5초 = 916.5초 ≈ 관측 916.7초 — 수집 시간의 100%가 이 대기였다.
    if fdr is None:
        return None
    try:
        limiter("naver").wait()
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


# 코드 → 야후 접미사 힌트. fetch_prices 가 상장정보(sec)로 채워 넣는다.
# 비어 있으면 종전대로 .KS → .KQ 양쪽을 시도한다(동작은 같고, 채워지면 호출이 절반이 된다).
YF_SUFFIX_HINT: Dict[str, str] = {}


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    hint = YF_SUFFIX_HINT.get(code)
    sufs = ((hint, ".KQ" if hint == ".KS" else ".KS") if hint else (".KS", ".KQ"))
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


def fetch_prices(codes: Sequence[str], start: str, end: str,
                 sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
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

    # ── 전 구간 재수집을 막는 두 가지 하한 ──────────────────────────────────────────────
    #   ① 상장일 — 그 이전 봉은 존재하지 않는다.
    #   ② 워터마크 — 전 구간을 요청했는데도 더 이전이 안 온 지점. 소스에 없다는 뜻이다.
    listing_of: Dict[str, pd.Timestamp] = {}
    delist_of: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        try:
            _s = sec.dropna(subset=["code"]).drop_duplicates("code")
            _cd = _s["code"].astype(str)
            if "listing_date" in _s.columns:
                listing_of = dict(zip(_cd, as_ts_series(_s["listing_date"])))
            if "delisting_date" in _s.columns:
                delist_of = dict(zip(_cd, as_ts_series(_s["delisting_date"])))
        except Exception:
            listing_of, delist_of = {}, {}
    watermark: Dict[str, pd.Timestamp] = {}
    _wm = VAULT.get_table("price_earliest_available", scope="shared")
    if _wm is not None and len(_wm):
        try:
            watermark = dict(zip(_wm["code"].astype(str), as_ts_series(_wm["earliest"])))
        except Exception:
            watermark = {}

    todo, n_back, n_fwd, n_skip, n_done = [], 0, 0, 0, 0
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
        #
        #   ★★ 다만 '요청 시작일'을 그대로 기준으로 삼으면 안 된다. 2021년에 상장한 종목은
        #   2015년 봉이 **존재할 수 없으므로** 조건이 영원히 참이고, 매 실행 전 구간을 다시
        #   받는다. 실측: 캐시 3,517종목 중 1,487종목(42%)이 매번 재수집 대상이 되어
        #   가격 단계 992초 중 916초를 이미 갖고 있는 데이터를 다시 받는 데 썼다.
        #   → 상장일과 '이 종목에서 실제로 받아진 최소일' 워터마크로 하한을 올린다.
        want = start_ts
        _ld = listing_of.get(c)
        if _ld is not None and pd.notna(_ld):
            want = max(want, as_ts(_ld))
        _wm = watermark.get(c)
        if _wm is not None and pd.notna(_wm):
            want = max(want, _wm)          # 이미 '더 이전은 없다'가 확인된 지점
        # ★ 증분(앞으로) 방향에도 종료 조건이 필요하다.
        #   폐지 종목의 mx 는 '마지막 거래일'이라 mx < end_ts - 5d 가 **영원히 참**이다.
        #   그래서 매 실행 존재하지도 않는 구간(mx+1 ~ 오늘)을 4개 소스에 물었고,
        #   637종목이 100% 실패하며 640초를 태웠다 — 그것도 매번.
        #   음성캐시는 'mx is None' 가지에서만 조회되므로 이 population 을 못 본다.
        #   → 폐지일이 있으면 그 이후는 애초에 요청하지 않는다. 사실이지 기억이 아니다.
        _dd = delist_of.get(c)
        _closed = (_dd is not None and pd.notna(_dd)
                   and mx >= as_ts(_dd) - pd.Timedelta(days=5))
        if mn is not None and mn > want + pd.Timedelta(days=10):
            todo.append((c, start))
            n_back += 1
        elif _closed:
            n_done += 1                      # 폐지까지 이미 다 받음 — 더 받을 것이 없다
        elif mx < end_ts - pd.Timedelta(days=5) and not _recently_failed(
                c, mx + pd.Timedelta(days=1)):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
            n_fwd += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목을 처음부터 다시 받습니다 "
                 f"(캐시 최소일이 요청 시작일보다 늦음 = 앞 구간 결손).")
    if n_done:
        LOG.info(f"폐지일까지 이미 확보된 {n_done:,}종목은 증분 요청을 보내지 않습니다 "
                 f"(폐지 이후 구간은 존재하지 않습니다 — 예전엔 이걸 매 실행 4개 소스에 "
                 f"물어 전량 실패하며 시간을 태웠습니다).")
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
        failed, wm_rows = [], []
        for (c, st), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
                # ★ 전 구간(start)을 요청했는데 이만큼만 왔다면 그 이전은 소스에 없다.
                #   이 워터마크가 없으면 2021년 상장 종목은 2015년 봉이 영영 안 오므로
                #   '앞 구간 결손'으로 판정되어 **매 실행 전 구간을 다시 받는다.**
                if as_ts(st) <= start_ts + pd.Timedelta(days=1):
                    _mn = as_ts_series(d["date"]).min()
                    if pd.notna(_mn):
                        wm_rows.append({"code": c, "earliest": _mn, "checked_at": _today})
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
        if wm_rows:
            _wprev = VAULT.get_table("price_earliest_available", scope="shared")
            _wall = pd.concat([_wprev, pd.DataFrame(wm_rows)], ignore_index=True) \
                if _wprev is not None and len(_wprev) else pd.DataFrame(wm_rows)
            _wall = (_wall.sort_values("checked_at")
                          .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_earliest_available", _wall, scope="shared", domain="price",
                            source="fetch_prices: 소스가 보유한 최초 관측일 워터마크")
            LOG.info(f"최초 관측일 워터마크 {len(wm_rows):,}종목 기록 — 다음 실행부터 이 종목들의 "
                     f"전 구간 재수집을 건너뜁니다(상장 이전 구간은 존재하지 않습니다).")
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
    # ★★ 공용 캐시 보존 (절대 1원칙) ★★
    #   반환값은 이번 백테스트 창(+400일 워밍업)으로 자르는 게 맞지만, **그 잘린 프레임을
    #   공용 테이블에 그대로 써버리면** 창 밖의 과거가 활성 parquet 에서 영구히 사라진다.
    #   put_table 은 백업을 남기지만 get_table 은 활성 파일만 읽으므로, 다른 전략(또는 더 이른
    #   시작일로 도는 다음 실행)이 보기에 캐시가 통째로 파괴된 것과 같다.
    #   → 저장은 '기존 캐시 ∪ 신규'로 하고, 반환만 창으로 자른다.
    win = (px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)
    px_out = px[win]

    if new_frames:
        to_store = px
        if cached is not None and len(cached):
            outside = cached[~((cached["date"] >= as_ts(start) - pd.Timedelta(days=400)) &
                               (cached["date"] <= end_ts))]
            if len(outside):
                to_store = (pd.concat([outside.reindex(columns=px.columns), px],
                                      ignore_index=True)
                              .sort_values(["code", "date"])
                              .drop_duplicates(["code", "date"], keep="last")
                              .reset_index(drop=True))
                LOG.info(f"공용 가격 캐시 보존 — 이번 창 밖의 과거 {len(outside):,}행을 "
                         f"합쳐서 저장합니다(잘라내지 않습니다).")
        VAULT.put_table("krx_ohlcv_daily", to_store, scope="shared", domain="price",
                        source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common()))
    px = px_out
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if any(src_used.get(k, 0) for k in ("naver", "yfinance", "fdr")):
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
        cached = cached.copy()                      # 공용 캐시 객체를 제자리에서 고치지 않는다
        cached["date"] = as_ts_series(cached["date"])
        lo, hi = cached["date"].min(), cached["date"].max()
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용 "
                 f"({lo:%Y-%m} ~ {hi:%Y-%m} · {cached['code'].nunique():,}종목)")
        # ★ 이 캐시는 증분 갱신 경로가 없다(있으면 통째로 재사용). 다른 전략이 더 짧은 구간으로
        #   만들어 둔 캐시를 물려받으면 요청 구간의 뒷부분 d3 가 조용히 전부 결측이 된다.
        #   조용히 두지 않고 '어디까지 덮는지'를 명시한다.
        need_lo, need_hi = as_ts(start), as_ts(end)
        if pd.notna(lo) and pd.notna(hi) and (lo > need_lo + pd.Timedelta(days=45) or
                                              hi < need_hi - pd.Timedelta(days=45)):
            LOG.warn(f"수급 캐시가 요청 구간({need_lo:%Y-%m}~{need_hi:%Y-%m})을 다 덮지 못합니다 "
                     f"— 덮이지 않는 달의 d3 는 결측이 되고 U 는 d1 단독으로 계산됩니다. "
                     f"(이 캐시는 증분 갱신 경로가 없어 전체를 다시 받아야 넓어집니다. "
                     f"공용 캐시를 지우지 않는 것이 원칙이므로 자동 삭제하지 않습니다)")
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
        self.today = self._kst_day()
        self.n = 0
        self.exhausted = False
        self._lk = threading.RLock()
        self._reserved: Dict[str, int] = {}
        self._dirty = 0
        self._warned_reserve = False
        self._load()

    @staticmethod
    def _kst_day() -> str:
        """DART 한도의 리셋 경계는 00:00 KST 다. 로컬 날짜를 쓰면 UTC 컨테이너에서
        하루에 두 번 틀린다: 15~24 UTC 는 이미 리셋된 한도를 소진으로 착각해 9시간을
        헛차단하고, 그 뒤에는 남아 있다고 믿고 쏘다가 status 020 을 맞는다."""
        try:
            from zoneinfo import ZoneInfo
            return _dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        except Exception:
            return (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date().isoformat()

    def _roll_if_new_day(self):
        """긴 실행이 자정을 넘으면 한도도 리셋된다. take() 안에서 값싸게 확인한다."""
        d = self._kst_day()
        if d != self.today:
            LOG.info(f"KST 자정 경과 — DART 일일 한도가 초기화됐습니다 "
                     f"({self.today} → {d}, 직전 사용 {self.n:,}건).")
            self._save()
            self.today, self.n, self.exhausted = d, 0, False
            DART_HALT["reason"] = DART_HALT["detail"] = None

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

    def refund(self, k: int = 1, purpose: Optional[str] = None):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)
            # ★ 예약분도 함께 되돌린다. take(2) 후 refund(1) 이 정상 경로이므로,
            #   되돌리지 않으면 예약이 잡당 2 씩 깎여 14,000 예약이 7,000건만 보호한다.
            if purpose in self._reserved:
                self._reserved[purpose] += k
            self._dirty += k

    # ── 예약(reservation) ─────────────────────────────────────────────────────────────
    #  ★ 이 전략의 알파는 직원현황 하나뿐인데, 실행 3회 내내 dart_employees_ext 가 0행이었다.
    #    원인은 단순하다 — Tier-2 전체재무제표가 일일 한도를 먼저 다 써버렸다. 단계 순서를
    #    바꿔도 예산은 '날짜별 누적 카운터'라 어제 태운 것이 오늘까지 따라온다.
    #    → 특정 용도(purpose)에 호출 수를 **예약**해 두고, 예약분은 그 용도만 인출한다.
    #      일반 소비자는 (한도 − 예약잔량) 까지만 쓸 수 있다.
    def reserve(self, purpose: str, k: int):
        with self._lk:
            self._reserved[purpose] = max(0, int(k))

    def _reserved_for_others(self, purpose: Optional[str]) -> int:
        return sum(v for p, v in self._reserved.items() if p != purpose)

    def left(self, purpose: Optional[str] = None) -> int:
        """purpose 가 지금 쓸 수 있는 호출 수. 남의 예약분은 빼고 센다."""
        with self._lk:
            return max(0, DART_DAILY_LIMIT - self.n - self._reserved_for_others(purpose))

    def take(self, k: int = 1, purpose: Optional[str] = None) -> bool:
        with self._lk:
            self._roll_if_new_day()
            room = DART_DAILY_LIMIT - self._reserved_for_others(purpose)
            if self.n + k > room:
                # 예약 때문에 막힌 것인지, 한도 자체가 끝난 것인지 구별해서 알린다.
                if self.n + k > DART_DAILY_LIMIT:
                    if not self.exhausted:
                        self.exhausted = True
                        LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                                 f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, "
                                 f"내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                elif not self._warned_reserve:
                    self._warned_reserve = True
                    LOG.info(f"남은 호출은 다른 용도로 예약되어 있습니다 "
                             f"(예약 {self._reserved}). 이 단계는 여기서 멈춥니다 — "
                             f"예약분은 알파 원천(직원현황) 몫입니다.")
                if purpose in self._reserved:
                    self._reserved[purpose] = max(0, self._reserved[purpose] - k)
                return False
            self.n += k
            if purpose in self._reserved:
                self._reserved[purpose] = max(0, self._reserved[purpose] - k)
            self._dirty += k
            # ★ n % 500 은 refund 가 임의 값으로 감산하는 순간 영원히 안 맞을 수 있다.
            #   '마지막 저장 이후 변동량'으로 세면 어떤 감산 패턴에서도 반드시 저장된다.
            if self._dirty >= 200:
                self._dirty = 0
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★ '지금 못 받는다' 와 '원래 없다' 를 구별하는 단일 진실
#
#  dart_api() 는 세 가지 전혀 다른 사건을 모두 None 으로 뭉갠다:
#    ① 예산 게이트가 호출을 거부   ② 네트워크 실패   ③ API 가 '데이터 없음'(013) 응답
#  호출자는 ①②를 ③으로 읽는다. 실제로 이것 때문에 실행이 죽었다 —
#  일일 한도가 소진된 상태로 시작한 실행에서 CANARY 가 K8 을 '급여총액 미기재'로 판정하고
#  §12-2 킬 기준을 발동시켰다. 데이터는 멀쩡히 있었고 오늘 호출권이 없었을 뿐이다.
#  게다가 그 판정의 처방은 '백테스트 시작일 상향' — 일시적 조건으로 전략을 영구 훼손한다.
#
#  → 사유를 여기에 기록하고, 자원 조건으로 실패한 검사는 FAIL 이 아니라 SKIP 이어야 한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
DART_HALT: Dict[str, Optional[str]] = {"reason": None, "detail": None}


def dart_note_halt(reason: str, detail: str = ""):
    if DART_HALT["reason"] is None:
        DART_HALT["reason"], DART_HALT["detail"] = reason, detail


def dart_halt_reason(purpose: Optional[str] = None) -> Optional[str]:
    """지금 DART 를 쓸 수 없는 이유. None 이면 정상 — 즉 '응답 0건'은 진짜 데이터 부재다.

    purpose 를 주면 그 용도의 **예약분까지 고려**해서 판정한다. 예약이 남아 있으면
    전체 잔량이 0 이어도 그 용도는 계속 진행할 수 있다."""
    if not DART_API_KEY:
        return "DART_API_KEY 미입력"
    if DBUDGET is not None:
        if DBUDGET.left(purpose) <= 0 or DBUDGET.n >= DART_DAILY_LIMIT:
            return f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})"
        if purpose is None and DBUDGET.exhausted:
            return f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})"
    return DART_HALT["reason"]


def dart_budget_left(purpose: Optional[str] = None) -> int:
    return DBUDGET.left(purpose) if DBUDGET else DART_DAILY_LIMIT


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2, no_data_ok: bool = False,
             purpose: Optional[str] = None) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries, purpose=purpose):
        dart_note_halt(f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})",
                       "내일 재실행하면 정확히 이 지점부터 이어받습니다.")
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    # ★ try/finally 가 없으면 http_json 에서 예외가 새는 순간 tries 만큼이 영구 소실된다.
    #   EMP 경로는 상위에서 예외를 삼키므로 이 누수가 **완전히 조용하다**.
    try:
        js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                       referer="https://opendart.fss.or.kr/",
                       on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    finally:
        if DBUDGET is not None:
            DBUDGET.refund(max(0, tries - max(1, attempts["n"])), purpose=purpose)
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            dart_note_halt(f"DART 서버가 한도 초과 응답(status={st})",
                           "내일 재실행하면 이어받습니다.")
            LOG.warn(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            dart_note_halt(f"DART 인증 오류(status={st} · {DART_STATUS_MSG.get(st, '?')})",
                           "DART_API_KEY 를 확인하세요. 데이터 부재가 아닙니다.")
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st == "800":
            dart_note_halt("DART 시스템 점검 중(status=800)", "점검 종료 후 재실행하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        # ★ 013("조회된 데이터 없음")은 통신 실패가 아니라 **정상 응답**이다. 그런데 None 으로
        #   뭉개면 호출자가 '실패'와 구별할 수 없다. 서킷브레이커를 둔 호출자에게 이건 치명적이다
        #   — 그 해에 사업보고서를 안 낸 회사가 몇 곳만 연속돼도 브레이커가 터져 남은 수집을
        #   통째로 포기한다. 원하는 호출자만 opt-in 으로 빈 응답을 받아 구별할 수 있게 한다.
        if st == "013" and no_data_ok:
            return {"status": "013", "list": []}
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
    # ★ 예산·인증이 이미 막혔으면 남은 잡을 즉시 포기한다. 계속 돌면 OFS/CFS 두 번씩
    #   헛호출하며 큐 전체(최대 12,000건)를 소진하고, 로그만 실패로 채운다.
    if dart_halt_reason():
        return None
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        if dart_halt_reason():
            return None
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
        if dart_halt_reason():          # 예산·인증이 막히면 남은 배치를 즉시 포기
            return None
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
                          max_calls: Optional[int] = None,
                          freq: Optional[str] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다.

    ★ max_calls (2026-08 추가 — 이번 실행에서 던질 호출 수의 하드 상한)
      이 함수의 잡 수는 |기업| × |연도| × |보고서| 로 **곱셈으로 폭발**한다.
      3,981사 × 13년 × 4분기 = 207,012건 = 11일치. 호출자가 상한을 주지 않으면
      tqdm 이 11시간짜리 ETA 를 띄운 채 그대로 돌아간다 — 4시간 예산 계약이 있는
      호출자에게 이것은 계약 위반이다. 상한을 받으면 **우선순위 순으로 잘라서** 그만큼만
      던지고, 무엇을 남겼는지 로그로 밝힌다. None 이면 종전과 동일(무제한 콜드빌드).

    ★ freq  ("annual" | "quarterly") — 전역 DART_STATEMENT_FREQ 를 호출자가 덮어쓴다.
      연간만 받으면 잡 수가 정확히 1/4 이 된다.
    """
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

    reprts = ([REPRT_CODES["FY"]] if (freq or DART_STATEMENT_FREQ) == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    # 연도 내림차순 → 기업 우선순위 → 사업보고서(FY) 우선. FY 를 먼저 받아야 연간 축(직원현황·
    # 한계임금)과 짝이 맞는 회계 데이터가 먼저 완성된다.
    _rorder = {REPRT_CODES["FY"]: 0, REPRT_CODES["Q3"]: 1,
               REPRT_CODES["H1"]: 2, REPRT_CODES["Q1"]: 3}
    reprts = sorted(reprts, key=lambda r: _rorder.get(r, 9))
    jobs = [(c, y, r) for y in sorted(years, reverse=True) for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    total_needed = len(jobs)
    left_today = max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0))
    cap = total_needed
    if max_calls is not None:
        cap = max(0, min(cap, int(max_calls), left_today))
    if jobs:
        LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 (오늘 가용 호출 {left_today:,}건)")
        if cap < total_needed:
            jobs = jobs[:cap]
            LOG.warn(
                f"이번 실행에서는 상한 {cap:,}건만 받습니다 "
                f"(전체 {total_needed:,}건 = 약 {math.ceil(total_needed / max(DART_DAILY_LIMIT,1))}일치). "
                f"미수집분은 Tier-1 주요계정(fnlttMultiAcnt)으로 대체되며, "
                f"재실행하면 정확히 이 지점부터 이어받습니다. "
                f"상한은 DART_FS_MAX_CALLS 로 조절합니다.")
        elif total_needed > DART_DAILY_LIMIT:
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


# ★ 모듈 스코프여야 한다. 예전엔 fetch_dart_disclosures 안의 지역변수였는데
#   _disclosure_done_months 가 이를 참조해 NameError 가 잠복해 있었다. 예산이 남아 있는
#   첫 실행에서 L1.DART 가 통째로 죽는다(critical=False 라 조용한 WARN 으로).
DISCLOSURE_TYPES = ("A", "B")     # A=정기공시(사업/반기/분기보고서), B=주요사항보고
DISCLOSURE_LEDGER = "dart_disclosure_months"


def _disclosure_done_months(cached: Optional[pd.DataFrame]) -> set:
    """완결이 **증명된** 달만 돌려준다.

    기존 캐시에는 이 원장이 없다. 그렇다고 '캐시에 행이 있으니 완결'로 간주하면
    이미 뚫려 있는 구멍을 그대로 물려받는다. 그래서 레거시 캐시는 (달 × 유형)당
    1회짜리 값싼 탐침으로 total_count 를 받아 실제 보유 행수와 대조해 검증한다.
    120개월이면 240회 — 전체 재수집(수천 회)에 비하면 무시할 수 있는 비용이고,
    이 한 번으로 과거 실행이 남긴 조용한 결손이 드러난다.
    """
    led = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    if led is not None and len(led) and "month" in led.columns:
        d = led[led.get("complete", False).astype(bool)] if "complete" in led.columns else led
        return set(d["month"].astype(str))
    if cached is None or not len(cached):
        return set()

    have = cached["rcept_dt"].dt.to_period("M").astype(str).value_counts().to_dict()
    if not have or not DART_API_KEY or RUN_MODE == "CACHED" or dart_halt_reason():
        # 검증할 수 없으면 재수집 대상으로 둔다 — 조용히 '완결'로 승격시키지 않는다.
        return set()

    LOG.info(f"공시목록 캐시 {len(have)}개월의 완결성을 검증합니다 "
             f"(달당 {len(DISCLOSURE_TYPES)}회 탐침 — 과거 실행이 페이지 중간에 끊겼는지 확인).")

    def _probe(mk):
        p = pd.Period(mk, freq="M")
        total = 0
        for ty in DISCLOSURE_TYPES:
            js = dart_api("list.json", {
                "bgn_de": p.start_time.strftime("%Y%m%d"), "end_de": p.end_time.strftime("%Y%m%d"),
                "pblntf_ty": ty, "page_no": 1, "page_count": 1, "last_reprt_at": "N"},
                no_data_ok=True)
            if js is None:
                return mk, None                       # 검증 실패 → 완결로 승격하지 않는다
            total += int(js.get("total_count", 0) or 0)
        return mk, total

    res = pmap_io(_probe, sorted(have), workers=min(N_WORKERS_IO, 8), desc="공시 캐시 완결성 검증")
    ok, holed, unknown = set(), [], 0
    for r in res:
        if not r:
            unknown += 1
            continue
        mk, total = r
        if total is None:
            unknown += 1
        elif have.get(mk, 0) >= total:
            ok.add(mk)
        else:
            holed.append((mk, have.get(mk, 0), total))
    if holed:
        LOG.warn(f"과거 실행이 남긴 공시목록 결손 {len(holed)}개월을 찾았습니다 — "
                 f"예: {[f'{m}: {h}/{t}행' for m, h, t in holed[:3]]}. "
                 f"이 달들을 다시 받습니다. (그대로 뒀다면 유상증자·전환사채·자기주식 공시가 "
                 f"'애초에 없었던 것'으로 백테스트에 들어갔습니다)")
    if unknown:
        LOG.info(f"  {unknown}개월은 검증하지 못해 재수집 대상으로 둡니다(안전한 방향).")
    _save_disclosure_ledger(ok)
    return ok


def _save_disclosure_ledger(complete_months) -> None:
    prev = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    rows = set()
    if prev is not None and len(prev) and "month" in prev.columns:
        keep = prev[prev["complete"].astype(bool)] if "complete" in prev.columns else prev
        rows |= set(keep["month"].astype(str))
    rows |= {str(m) for m in complete_months}
    if not rows:
        return
    VAULT.put_table(DISCLOSURE_LEDGER,
                    pd.DataFrame({"month": sorted(rows), "complete": True}),
                    scope="shared", domain="dart",
                    source="공시목록 완결성 원장 — 페이지를 끝까지 훑은 달만 기록")


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ '그 달에 행이 하나라도 있다' ≠ '그 달을 다 받았다'
    #
    #  예전에는 have_months 를 캐시 행의 rcept_dt 에서 유도했다. 그래서 12페이지짜리 달을
    #  3페이지에서 예산·네트워크로 놓쳐도, 1~2페이지가 저장되는 순간 그 달은 영원히
    #  '보유'로 표시되고 나머지 페이지는 **두 번 다시 시도되지 않았다.**
    #  잃어버리는 것이 유상증자·전환사채·자기주식 공시라서, 하류(V3 희석 거부권·PACK-C)는
    #  '이벤트 없음'이라는 **정상적인 값**을 읽는다 — 경고도 FAIL 도 뜨지 않고, 재실행할수록
    #  그 거짓이 굳는다. 일시적 장애를 영구적 음성 관측으로 세탁하는 최악의 형태다.
    #  → 완결 여부를 별도 원장에 명시적으로 기록하고, 그 원장만 신뢰한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    done_months = _disclosure_done_months(cached)
    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in done_months]
    if RUN_MODE == "CACHED":
        todo = []
    elif todo and cached is not None and len(cached):
        LOG.info(f"공시목록 미완결 {len(todo)}개월을 다시 받습니다 "
                 f"(완결 확인 {len(done_months)}개월). 페이지 중간에 끊긴 달은 "
                 f"'보유'로 세지 않습니다 — 그렇게 세면 빠진 공시가 영구히 없는 것이 됩니다.")

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)

    def _one(m):
        """(월, 행들, 완결여부). 한 페이지라도 못 받으면 그 달은 미완결이다."""
        rows, complete = [], True
        for ty in DISCLOSURE_TYPES:
            page, walked = 1, False
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"}, no_data_ok=True)
                if js is None:                       # 예산·네트워크·인증 → 이 달은 미완결
                    complete = False
                    break
                lst = js.get("list")
                if not isinstance(lst, list) or not lst:
                    walked = True                    # 정상 빈 응답 = 이 유형은 여기서 끝
                    break
                rows.extend(lst)
                if page >= int(js.get("total_page", 1) or 1):
                    walked = True
                    break
                page += 1
            else:
                complete = False                     # 100페이지 상한 = 다 못 훑었다
            if not walked and complete is not False:
                complete = False
        return str(m), rows, complete

    new, ok_months, bad_months = [], [], []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if not r:
                continue
            mkey, rows, complete = r
            new.extend(rows)
            (ok_months if complete else bad_months).append(mkey)
        if bad_months:
            LOG.warn(f"공시목록 {len(bad_months)}개월이 미완결로 남았습니다 "
                     f"(예: {bad_months[:3]}). 받은 부분은 저장하되 **완결로 표시하지 않으므로** "
                     f"다음 실행에서 그 달부터 다시 받습니다. "
                     + (f"사유: {dart_halt_reason()}" if dart_halt_reason() else ""))

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
    # 원장 갱신은 저장 뒤에. 완결로 표시한 달은 실제로 저장된 달이어야 한다.
    if ok_months:
        _save_disclosure_ledger(ok_months)
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  상장폐지 '유형' 분류 — 청산가를 -100% 로 둘지 직전가로 둘지 가른다
#
#  ★ 왜 필요한가. 예전엔 모든 폐지를 -100% 로 처리했다. 그런데 폐지목록 원본의 Reason 을
#    실측해 보면 2016년 이후 폐지된 주권 561건 중
#      · 피흡수합병 60 · 스팩소멸합병 53 · 지주회사 완전자회사화 29 · 타법인 완전자회사 편입 14
#        → 합병 대가로 인수기업 주식을 받는다. 0% 도 아니고 보통 프리미엄이 붙는다.
#      · 스팩 예심청구서 미제출·해산 ~110  → 예치금이 공모가 + 이자로 반환된다(사실상 원금).
#    즉 **절반 이상이 전액손실이 아닌데 전액손실로 계상**되고 있었다.
#    U-MID 대역의 연 폐지율(~4.9%)과 25종목 포트폴리오로 환산하면 연 -2%p 안팎의
#    '있지도 않은 손실'이다. 게다가 이것은 보수적인 방향이 아니라 **틀린** 방향이다.
#
#  ★ 그렇다고 프리미엄을 지어내지 않는다. 합병·해산 건은 **직전 관측가로 청산**한다.
#    한국 시장의 합병 스프레드는 좁아 직전가가 편향 없는 추정치이고, 실제 프리미엄보다
#    낮으므로 여전히 보수적이다. 부실 폐지(감사의견 거절·자본잠식·부도)는 종전대로
#    정리매매가가 없으면 -100% 다.
# ══════════════════════════════════════════════════════════════════════════════════════════
DELIST_TRANSFER_PAT = (
    r"흡수합병|피흡수|합병으로|완전자회사|지주회사|주식교환|주식의\s*포괄적|"
    r"신청에\s*의한\s*상장폐지|상장폐지\s*신청|자진|공개매수|이전상장|재상장|시장이전")
DELIST_SPAC_PAT = (
    # 스팩 특유의 사유들. '청구서'와 '신청서'가 혼용되고, '존속기간 만료'는 스팩의
    # 3년 존속기간이 끝나 예치금을 반환하고 해산하는 경우다(부실이 아니다).
    r"스팩|기업인수목적|예비심사\s*(청구서|신청서)\s*미제출|합병상장예비심사신청서\s*미제출|"
    r"해산\s*사유|존속기간\s*만료")
DELIST_DISTRESS_PAT = (
    # ★ '자본잠식' 을 그대로 쓰면 실제 표기인 '자본전액잠식'(전액이 사이에 낀다)을 놓친다.
    #   계약 C2c 가 이 누락을 잡아냈다 — 사유 문자열은 KRX 표기 그대로 검증해야 한다.
    r"감사의견|의견거절|부적정|자본\S*잠식|부도|파산|회생|영업정지|계속기업|"
    r"상장폐지\s*기준에\s*해당|횡령|배임|사업보고서\s*미제출|주식\S*분산\s*미달|"
    r"매출액\s*미달|시가총액\s*미달|거래량\s*미달")


def classify_delisting(reason: Any) -> str:
    """'transfer'(합병·자진) | 'spac'(스팩 해산) | 'distress'(부실) | 'unknown'"""
    s = str(reason or "").strip()
    if not s:
        return "unknown"
    # 부실을 먼저 본다. '스팩소멸합병'처럼 두 패턴이 겹칠 때 관대한 쪽으로 새지 않게
    # 하려는 것이 아니라, 반대로 부실 신호가 있으면 무조건 부실로 보내기 위함이다.
    if re.search(DELIST_DISTRESS_PAT, s):
        return "distress"
    if re.search(DELIST_TRANSFER_PAT, s):
        return "transfer"
    if re.search(DELIST_SPAC_PAT, s):
        return "spac"
    return "unknown"


# 직전가 청산으로 볼 유형. 'unknown' 은 포함하지 않는다 — 모르면 보수적으로 -100%.
DELIST_NOT_WIPEOUT = ("transfer", "spac")


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

    def delist_kind_map(self) -> Dict[str, str]:
        """종목 → 폐지 유형. 청산가를 -100% 로 둘지 직전가로 둘지 가른다."""
        if "delist_reason" not in self.sec.columns:
            return {}
        return {r.code: classify_delisting(getattr(r, "delist_reason", ""))
                for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        # ★ 이 목록에 없는 단계는 표에서 조용히 사라진다(오류도 경고도 없이).
        #   새 게이트를 추가했다면 반드시 여기에도 넣을 것.
        order = ["전체상장", "PIT유니버스", "가격보유", "U-MID대역", "유동성필터", "거부권통과",
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
# ║  CANARY  K1~K9  (스펙 §2 · 예산 25분)                                                     ║
# ║                                                                                          ║
# ║  목적은 '수집을 시작해도 되는가'를 25분 안에 판정하는 것이다.                               ║
# ║  95분짜리 수집을 다 돌린 뒤 급여총액 기재율이 12% 였다는 걸 아는 것보다,                    ║
# ║  200종목 표본으로 20분 만에 아는 편이 압도적으로 싸다.                                      ║
# ║                                                                                          ║
# ║  ★ 판정은 실측값과 함께 남긴다. "PASS" 만 찍고 숫자를 숨기지 않는다.                        ║
# ║  ★ K5(상장폐지 목록) 실패는 즉시 중단이다. 생존자편향이 확정되기 때문이다(§12-1).           ║
# ║  ★ K8(급여총액 기재율) 실패도 중단이다. 임금프리미엄 자체가 계산 불가이므로                 ║
# ║    이 전략의 존재 이유가 사라진다(§12-2).                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY_RESULTS: List[dict] = []


def _k(kid: str, name: str, passed: Optional[bool], measured: str, criterion: str,
       action: str = "", fatal: bool = False):
    CANARY_RESULTS.append({"id": kid, "name": name, "passed": passed, "measured": measured,
                           "criterion": criterion, "action": action, "fatal": fatal})
    tag = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
    fn = LOG.ok if passed else (LOG.info if passed is None else LOG.warn)
    fn(f"[{kid}] {name} — {tag} · 실측 {measured} (기준 {criterion})" +
       (f" → {action}" if action else ""))


def _num_series(s) -> pd.Series:
    """DART 금액 문자열 → 숫자. 콤마·공백·유니코드 마이너스·'-'(무기재) 처리."""
    t = (pd.Series(s).astype(str)
         .str.replace(",", "", regex=False)
         .str.replace("−", "-", regex=False)
         .str.strip())
    t = t.where(~t.isin(["", "-", "--", "nan", "None", "N/A", "해당사항없음"]))
    return pd.to_numeric(t.str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")


# ── K1 / K2 : DART 재무 일괄(배치) 경로 ─────────────────────────────────────────────────────
def _canary_bulk(corps: Sequence[str], n_universe: int) -> Tuple[Optional[bool], Optional[bool]]:
    """K1: 2016Q1 배치 응답의 실측 행수를 전 유니버스로 외삽. K2: 최초 제공 사업연도 탐침.

    ※ '재무정보 일괄다운로드'는 웹 화면이고 API 가 아니다. 코드가 실제로 타는 배치 경로는
      fnlttMultiAcnt(100사/호출)이므로, 그 경로의 실측 처리량으로 판정한다.
      외삽값임을 표에 명시한다 — 실측처럼 위장하지 않는다.
    """
    if not DART_API_KEY:
        _k("K1", "DART 재무 배치(2016Q1)", None, "키 없음", f">{CANARY_K1_MIN_ROWS:,}행",
           "DART_API_KEY 미입력 — 재무 기반 TP 전부 비활성")
        _k("K2", "배치 최초 제공 사업연도", None, "키 없음", "≤2016", "")
        return None, None

    batch = [str(c) for c in corps[:DART_MULTI_BATCH]]
    rows_per_corp, ok_batch = 0.0, False
    js = dart_api("fnlttMultiAcnt.json", {"corp_code": ",".join(batch), "bsns_year": "2016",
                                          "reprt_code": REPRT_CODES["Q1"]})
    if js and isinstance(js.get("list"), list) and js["list"]:
        d = pd.DataFrame(js["list"])
        n_corp = d["corp_code"].nunique() if "corp_code" in d.columns else max(len(batch), 1)
        rows_per_corp = len(d) / max(n_corp, 1)
        ok_batch = True
    est = int(rows_per_corp * max(n_universe, 1) * 4)          # 4개 분기 보고서 기준
    k1 = ok_batch and est > CANARY_K1_MIN_ROWS
    _k("K1", "DART 재무 배치(2016Q1)", k1,
       f"{rows_per_corp:.1f}행/사 → 전체 외삽 {est:,}행", f">{CANARY_K1_MIN_ROWS:,}행",
       "" if k1 else "Fallback: fnlttSinglAcntAll 단건 경로로 자동 전환(코드에 이미 배선됨)")

    # K2 — 뒤로 탐침해 실제 최초 제공 연도를 찾는다.
    first_year = None
    for y in (2015, 2016, 2017, 2018):
        j = dart_api("fnlttMultiAcnt.json", {"corp_code": ",".join(batch[:50]),
                                             "bsns_year": str(y), "reprt_code": REPRT_CODES["FY"]})
        if j and isinstance(j.get("list"), list) and j["list"]:
            first_year = y
            break
    k2 = first_year is not None and first_year <= 2016
    # ★ first_year 가 None 이면 '탐침이 아무것도 못 받았다'는 뜻이지 '2016년 데이터가 없다'가
    #   아니다. 예전엔 그대로 문자열에 끼워 "시작일을 None년 이후로 상향" 이라는 실행 불가능한
    #   지시가 찍혔다 — 처방이 원인 진단과 어긋나면 사용자는 엉뚱한 곳을 고친다.
    _k("K2", "배치 최초 제공 사업연도", k2, str(first_year or "미확인"), "≤2016",
       "" if k2 else (f"백테스트 시작일을 {first_year}년 이후로 상향해야 합니다" if first_year
                      else "2015~2018 탐침이 모두 빈 응답 — 키·한도·네트워크를 먼저 확인하세요. "
                           "이 결과만으로 시작연도를 바꾸지 마세요."))
    return k1, k2


# ── K3 : 필수 계정 커버리지 ─────────────────────────────────────────────────────────────────
CANARY_REQUIRED_ACCOUNTS = ["revenue", "inventory", "receivable", "cfo", "capex", "tax_expense"]


def _canary_accounts(corps: Sequence[str], year: int) -> Optional[bool]:
    if not DART_API_KEY:
        _k("K3", "필수계정 커버리지", None, "키 없음", f"≥{CANARY_K3_MIN_COV:.0%}", "")
        return None
    jobs = [(c, year, REPRT_CODES["FY"]) for c in corps]
    res = [d for d in pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 8),
                              desc="CANARY K3 계정") if d is not None and len(d)]
    if not res:
        _k("K3", "필수계정 커버리지", False, "응답 0건", f"≥{CANARY_K3_MIN_COV:.0%}",
           "재무 기반 TP 전부 비활성 위험 — 키·한도를 확인하세요")
        return False
    W = tidy_financials(pd.concat(res, ignore_index=True))
    n = W["corp_code"].nunique() if len(W) else 0
    cov, weak = {}, []
    for a in CANARY_REQUIRED_ACCOUNTS:
        c = float(W.loc[W[a].notna(), "corp_code"].nunique()) / max(n, 1) if a in W.columns else 0.0
        cov[a] = c
        if c < CANARY_K3_MIN_COV:
            weak.append(a)
    globals()["CANARY_WEAK_ACCOUNTS"] = weak
    ok = not weak
    _k("K3", "필수계정 커버리지", ok,
       " · ".join(f"{a}={cov[a]:.0%}" for a in CANARY_REQUIRED_ACCOUNTS),
       f"전 계정 ≥{CANARY_K3_MIN_COV:.0%}",
       "" if ok else (f"미달 계정 {weak} 을 쓰는 센서는 결측으로 두고 진행합니다(0 채움 금지). "
                      f"※ 재고·매출채권은 금융·지주·순수서비스 기업에 **원래 없는** 계정이라 "
                      f"표본에 그런 업종이 섞이면 80% 안팎이 정상입니다 — 수집 실패와 구분하려면 "
                      f"§6 커버리지표의 업종별 분포를 함께 보세요."))
    return ok


# ── K4 : 가격 10년 ──────────────────────────────────────────────────────────────────────────
def _canary_price(codes: Sequence[str], sec: Optional[pd.DataFrame] = None) -> bool:
    """탐침 구간(2016 상반기) 가격 확보율.

    ★ 분모를 반드시 '그 구간에 실제로 상장돼 있던 종목'으로 좁힌다.
      이 전략의 CANARY 표본은 생존자편향을 없애려고 폐지종목을 대역 비중대로 섞어 뽑는다.
      2016 이후 상장했거나 2016 이전에 이미 폐지된 종목은 2016 상반기 시세가 **없는 게 정상**이다.
      그것을 실패로 세면, 편향을 제대로 제거할수록 K4 가 FAIL 로 기울어 임계값을 낮추라는
      압력이 생긴다 — 정확히 스펙이 금지하는 방향이다(§2 "임계값을 낮춰 통과시키지 말 것").
    """
    P0, P1 = as_ts("2016-01-01"), as_ts("2016-06-30")
    codes = [str(c) for c in codes]
    elig, n_off = codes, 0
    if sec is not None and len(sec):
        s = sec.drop_duplicates("code").copy()
        s.index = pd.Index(s["code"].astype(str))
        nat = pd.Series(pd.NaT, index=s.index)
        ld = as_ts_series(s["listing_date"]) if "listing_date" in s.columns else nat
        dd = as_ts_series(s["delisting_date"]) if "delisting_date" in s.columns else nat
        live = ((ld.isna() | (ld <= P1)) & (dd.isna() | (dd >= P0)))
        live = pd.Series(np.asarray(live), index=s.index)  # as_ts_series 가 인덱스를 갈아끼워도 안전
        elig = [c for c in codes if bool(live.get(c, True))]
        n_off = len(codes) - len(elig)
    if not elig:
        elig, n_off = codes, 0

    # ★ 판정 기준을 '폐지 예정 여부'로 쪼갠다.
    #   존속 종목의 시세 결손은 진짜 결손이다 — 그 종목은 실제로 담겨서 수익률을 만든다.
    #   반면 이미 폐지된 종목의 시세 결손은 백테스트 엔진이 -100%(정리매매가 없으면)로
    #   처리하므로 **보수적 방향**이며, 이를 실패로 세면 편향을 제대로 제거할수록
    #   K4 가 FAIL 로 기울어 임계값을 낮추라는 압력이 생긴다(§2 가 금지하는 방향).
    #   → 존속에 엄격한 기준(≥95%)을 걸고, 폐지분은 정보성으로 따로 보고한다.
    dead: set = set()
    if sec is not None and len(sec) and "delisting_date" in sec.columns:
        dead = set(sec.loc[sec["delisting_date"].notna(), "code"].astype(str))

    chain_used = Counter()
    def _one(c):
        for nm, fn in PRICE_CHAIN:
            try:
                d = fn(c, "2016-01-01", "2016-06-30")
            except Exception:
                d = None
            if d is not None and len(d):
                return nm
        return None
    res = pmap_io(_one, elig, workers=min(N_WORKERS_IO, 8), desc="CANARY K4 가격")
    live_n = live_ok = dead_n = dead_ok = 0
    for c, r in zip(elig, res):
        if r:
            chain_used[r] += 1
        if c in dead:
            dead_n += 1
            dead_ok += 1 if r else 0
        else:
            live_n += 1
            live_ok += 1 if r else 0
    rate_live = live_ok / max(live_n, 1)
    rate_dead = dead_ok / max(dead_n, 1)
    ok = (live_n == 0) or (rate_live >= 0.95)
    _k("K4", "10년 가격 확보", ok,
       f"존속 {live_ok}/{live_n} ({rate_live:.0%})" +
       (f" · 폐지 {dead_ok}/{dead_n} ({rate_dead:.0%}, 미확보분은 -100% 처리)" if dead_n else "") +
       (f" · 구간 미상장 {n_off}종목 분모 제외" if n_off else "") + " · " +
       (", ".join(f"{k}×{v}" for k, v in chain_used.most_common()) or "경로 없음"),
       "존속 종목 ≥95%",
       "" if ok else "존속 종목의 시세가 비어 있습니다 — 체인(pykrx→FDR→네이버→yfinance)과 "
                     "네트워크·차단을 확인하세요. 폐지 종목 결손은 여기 포함되지 않습니다.")
    return ok


# ── K5 : 상장폐지 목록  ★ 실패 시 즉시 중단 ─────────────────────────────────────────────────
def _canary_delisting(sec: pd.DataFrame) -> bool:
    n = int(sec["delisting_date"].notna().sum()) if "delisting_date" in sec.columns else 0
    ok = n >= 50
    _k("K5", "상장폐지 목록 확보", ok, f"폐지일 보유 {n:,}종목", "≥50종목",
       "" if ok else "★ 생존자편향이 확정됩니다 — 중단합니다(§12-1)", fatal=True)
    return ok


# ── K7 / K8 / K9 : empSttus ─────────────────────────────────────────────────────────────────
def _canary_emp(corps: Sequence[str], year: int) -> Tuple[Optional[bool], Optional[bool], Optional[bool]]:
    if not DART_API_KEY:
        for kid, nm, crit in (("K7", "empSttus 응답", f"≥{CANARY_K7_MIN_RATE:.0%}"),
                              ("K8", "연간급여총액 기재율", f"≥{CANARY_K8_MIN_RATE:.0%}"),
                              ("K9", "단위 정합성", f"불일치<{CANARY_K9_MAX_BAD:.0%}")):
            _k(kid, nm, None, "키 없음", crit, "DART_API_KEY 미입력")
        return None, None, None

    rows = [r for r in pmap_io(lambda c: _emp_one_raw(c, year), list(corps),
                               workers=min(N_WORKERS_IO, 12), desc="CANARY K7~K9 직원현황")
            if r is not None]
    n_try = len(corps)
    n_ok = len(rows)
    rate7 = n_ok / max(n_try, 1)
    k7 = rate7 >= CANARY_K7_MIN_RATE
    _k("K7", "empSttus 응답", k7, f"{n_ok}/{n_try} ({rate7:.0%})", f"≥{CANARY_K7_MIN_RATE:.0%}",
       "" if k7 else "실제 최초 가용연도를 찾아 백테스트 시작일을 상향하세요")

    if not rows:
        _k("K8", "연간급여총액 기재율", False, "표본 0건", f"≥{CANARY_K8_MIN_RATE:.0%}",
           "★ 임금프리미엄 계산 불가 — 중단(§12-2)", fatal=True)
        _k("K9", "단위 정합성", None, "표본 0건", f"불일치<{CANARY_K9_MAX_BAD:.0%}", "")
        return k7, False, None

    D = pd.DataFrame(rows)
    n_pay = int(D["payroll_total"].notna().sum())
    rate8 = n_pay / max(len(D), 1)
    k8 = rate8 >= CANARY_K8_MIN_RATE
    _k("K8", "연간급여총액 기재율", k8, f"{n_pay}/{len(D)} ({rate8:.0%})",
       f"≥{CANARY_K8_MIN_RATE:.0%}",
       "" if k8 else "★ 미달 — 임금프리미엄 TP 를 비활성화하고 CORE-D 로 축소 실행합니다",
       fatal=False)

    # K9 — jan_salary_am × sm ≈ fyer_salary_totamt 인가 (단위 혼재 탐지)
    m = D.dropna(subset=["payroll_total", "avg_salary", "employees"])
    m = m[(m["employees"] > 0) & (m["avg_salary"] > 0)]
    if len(m) < 10:
        _k("K9", "단위 정합성", None, f"검증가능 표본 {len(m)}건", f"불일치<{CANARY_K9_MAX_BAD:.0%}",
           "표본 부족 — 본수집에서 재판정합니다")
        return k7, k8, None
    ratio = (m["payroll_total"] / (m["avg_salary"] * m["employees"])).replace([np.inf, -np.inf], np.nan)
    bad = float(((ratio > 10) | (ratio < 0.1)).mean())
    k9 = bad < CANARY_K9_MAX_BAD
    _k("K9", "단위 정합성 (jan×sm≈tot)", k9,
       f"중앙비 {ratio.median():.2f} · 10배이상 불일치 {bad:.1%} (n={len(m)})",
       f"불일치<{CANARY_K9_MAX_BAD:.0%}",
       "" if k9 else "단위(원/천원/백만원) 혼재 — 정규화에서 배수 역추정을 적용합니다")
    return k7, k8, k9


def canary_sample(sec: pd.DataFrame, monthly: pd.DataFrame, n: int = None) -> List[str]:
    """CANARY 표본 추출 — U-MID 대역에서, **폐지 종목 비율까지 유니버스와 맞춰서** 뽑는다.

    ★ 전 구간 거래대금 중앙값으로 한 줄 세우면 표본이 조용히 생존자 쪽으로 쏠린다.
      일찍 폐지된 종목은 관측 개월 수가 적어 중앙값 순위가 낮게 잡히고, 그 결과 K3/K7/K8 이
      '오래 살아남은 회사의 공시 충실도'를 재게 된다 — 실제 수집률보다 낙관적인 수치가 나오고,
      그걸 근거로 수집을 시작한다. 캐너리의 목적과 정반대다.
    → ① 월별 랭크로 U-MID 대역에 한 번이라도 들어온 종목을 후보로 삼고
      ② 그 후보 안에서 폐지/존속 비율을 그대로 유지해 균등 간격 추출한다.
    """
    n = CANARY_SAMPLE_N if n is None else n
    if monthly is None or monthly.empty or "adv20" not in monthly.columns:
        return sec["code"].astype(str).tolist()[:n]
    pm = monthly[["code", "month", "adv20"]].copy()
    pm["rk"] = pm.groupby("month", observed=True)["adv20"].rank(ascending=False, method="first")
    band = pm[pm["rk"].between(UMID_RANK_LO, UMID_RANK_HI) & (pm["adv20"] >= MIN_ADV_KRW)]
    cand = band["code"].value_counts()               # 대역에 머문 개월 수 순
    codes = [str(c) for c in cand.index]
    if not codes:
        LOG.warn("U-MID 대역 후보가 없어 거래대금 상위 순으로 캐너리 표본을 뽑습니다.")
        codes = (monthly.groupby("code", observed=True)["adv20"].median()
                 .sort_values(ascending=False).index.astype(str).tolist())
    dead = set(sec.loc[sec["delisting_date"].notna(), "code"].astype(str))
    d_list = [c for c in codes if c in dead]
    l_list = [c for c in codes if c not in dead]
    share = len(d_list) / max(len(codes), 1)
    n_d = min(len(d_list), int(round(n * share)))
    n_l = min(len(l_list), n - n_d)

    def _stride(xs, k):
        if k <= 0 or not xs:
            return []
        step = max(1, len(xs) // k)
        return xs[::step][:k]

    pick = _stride(d_list, n_d) + _stride(l_list, n_l)
    LOG.info(f"CANARY 표본 {len(pick)}종목 — U-MID 대역 후보 {len(codes):,}개 중 "
             f"폐지 {n_d}·존속 {n_l} (대역 내 폐지비율 {share:.1%}을 그대로 반영해 "
             f"생존자 쏠림을 제거)")
    return pick


DART_DEPENDENT_KS = ("K1", "K2", "K3", "K7", "K8", "K9")


def canary_resource_flip() -> bool:
    """DART 가 자원 조건으로 멈춘 상태라면, 이미 기록된 DART 검사 FAIL 을 SKIP 으로 되돌린다.

    ★ 예산은 CANARY 도중에도 바닥난다(시작 시점엔 남아 있었던 경우). 그때 기록된 FAIL 은
      '자원 없음'을 '데이터 없음'으로 오판한 결과다. 되돌린 사실 자체를 로그로 남겨
      은폐가 아니라 정정임을 밝힌다. 되돌렸으면 True.
    """
    why = dart_halt_reason()
    if not why:
        return False
    flipped = [r["id"] for r in CANARY_RESULTS
               if r["id"] in DART_DEPENDENT_KS and r["passed"] is False]
    for r in CANARY_RESULTS:
        if r["id"] in DART_DEPENDENT_KS and r["passed"] is False:
            r["passed"], r["fatal"] = None, False
            r["measured"] = f"{r['measured']}  ← 측정 중 {why}"
            r["action"] = "자원 조건으로 판정 보류. 데이터 부재가 아닙니다."
    if flipped:
        LOG.warn(f"수집 도중 DART 가 중단됐습니다 — {why}. "
                 f"{flipped} 의 FAIL 을 **판정 보류(SKIP)** 로 되돌립니다. "
                 f"호출권이 없어 못 받은 것을 '데이터가 없다'로 판정하면 안 됩니다.")
    return True


def run_canary(sec: pd.DataFrame, sample_codes: Sequence[str]) -> dict:
    """CANARY 전체 실행. 반환 dict 는 하류가 '무엇을 끄고 갈지' 정하는 데 쓴다."""
    LOG.banner("③ CANARY K1~K9", "수집을 시작해도 되는지 25분 안에 판정합니다 (스펙 §2)")
    CANARY_RESULTS.clear()
    t0 = time.time()

    s = sec[sec["code"].isin(list(sample_codes))].copy()
    if s.empty:
        s = sec.head(CANARY_SAMPLE_N).copy()
    corps = [c for c in s["corp_code"].dropna().astype(str).unique().tolist()][:CANARY_SAMPLE_N]
    codes = s["code"].astype(str).tolist()[:CANARY_SAMPLE_N]
    n_uni = int(sec["corp_code"].notna().sum())
    probe_year = min(as_ts(BACKTEST_END).year - 1, _dt.date.today().year - 1)

    LOG.info(f"표본 {len(codes)}종목 / corp_code {len(corps)}개 · 직원현황 탐침연도 {probe_year}")

    # ★ DART 를 지금 쓸 수 없는 상태라면, DART 의존 검사는 FAIL 이 아니라 SKIP 이다.
    #   '오늘 호출권이 없다'는 것과 '그 데이터가 세상에 없다'는 것은 전혀 다른 사건이고,
    #   후자의 처방(백테스트 시작연도 상향·전략 축소)을 전자에 적용하면 일시적 조건 때문에
    #   전략이 영구히 훼손된다. 실제로 이것 때문에 실행이 §12-2 킬 기준으로 죽었다.
    halt = dart_halt_reason()
    if halt:
        LOG.warn(f"DART 를 지금 쓸 수 없습니다 — {halt}. "
                 f"K1·K2·K3·K7·K8·K9 는 **판정 보류(SKIP)** 로 두고 진행합니다. "
                 f"이 상태에서의 '응답 0건'은 데이터 부재의 증거가 아니므로 킬 기준을 걸지 않습니다.")
        for kid, nm, crit in (("K1", "DART 재무 배치(2016Q1)", f">{CANARY_K1_MIN_ROWS:,}행"),
                              ("K2", "배치 최초 제공 사업연도", "≤2016"),
                              ("K3", "필수계정 커버리지", f"≥{CANARY_K3_MIN_COV:.0%}"),
                              ("K7", "empSttus 응답", f"≥{CANARY_K7_MIN_RATE:.0%}"),
                              ("K8", "연간급여총액 기재율", f"≥{CANARY_K8_MIN_RATE:.0%}"),
                              ("K9", "단위 정합성", f"불일치<{CANARY_K9_MAX_BAD:.0%}")):
            _k(kid, nm, None, f"측정 불가 — {halt}", crit,
               "자원 조건입니다. 데이터 부재가 아니므로 시작연도·전략을 바꾸지 마세요.")
        k1 = k2 = k3 = k7 = k8 = k9 = None
    else:
        k1, k2 = _canary_bulk(corps, n_uni)
        k3 = _canary_accounts(corps, probe_year)
        k7, k8, k9 = _canary_emp(corps, probe_year)
    k4 = _canary_price(codes, sec)
    k5 = _canary_delisting(sec)

    if canary_resource_flip():
        k1 = k2 = k3 = k7 = k8 = k9 = None

    LOG.table([[r["id"], _trunc(r["name"], 26),
                "PASS" if r["passed"] else ("SKIP" if r["passed"] is None else "FAIL"),
                _trunc(r["measured"], 46), _trunc(r["criterion"], 18),
                _trunc(r["action"], 34)] for r in CANARY_RESULTS],
              ["ID", "확인 항목", "판정", "실측", "기준", "FAIL 시 조치"],
              ["c", "l", "c", "l", "l", "l"], title="CANARY 실측표 (§2)", maxw=48)

    runtime_mark("CANARY", time.time() - t0)
    verdict = {"K1": k1, "K2": k2, "K3": k3, "K4": k4, "K5": k5, "K7": k7, "K8": k8, "K9": k9,
               "wage_premium_ok": (k8 is not False),
               "weak_accounts": globals().get("CANARY_WEAK_ACCOUNTS", [])}

    fatal = [r for r in CANARY_RESULTS if r["fatal"] and r["passed"] is False]
    if fatal and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(
            "CANARY 치명 실패: " + ", ".join(f"{r['id']}({r['name']})" for r in fatal) +
            " — §12 킬 기준입니다. 임계값을 낮춰 통과시키지 마십시오.")
    if k8 is False:
        LOG.warn("K8 미달 — 임금프리미엄(TP_N1)을 비활성화하고 CORE-D + TP_N2/N3 로 진행합니다. "
                 "이 사실은 최종 리포트에 그대로 명시됩니다.")
    return verdict


def canary_report_md() -> str:
    lines = ["# CANARY 실측 리포트 (TCD v3 · 전략3)", "",
             f"- 생성: {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
             f"- 백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
             "| ID | 항목 | 판정 | 실측 | 기준 | 조치 |", "|---|---|---|---|---|---|"]
    for r in CANARY_RESULTS:
        tag = "PASS" if r["passed"] else ("SKIP" if r["passed"] is None else "**FAIL**")
        lines.append(f"| {r['id']} | {r['name']} | {tag} | {r['measured']} | "
                     f"{r['criterion']} | {r['action'] or '-'} |")
    return "\n".join(lines) + "\n"

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  EMP-LITE — DART 직원현황(empSttus) 확장 수집 + C15 한계임금                         ║
# ║                                                                                          ║
# ║  코어(v2)의 fetch_dart_employees 는 sm 과 급여총액만 남기고 jan_salary_am·rgllbr_co 를     ║
# ║  버린다. 이 전략은 그 두 필드가 없으면 성립하지 않으므로 확장판을 따로 둔다.                 ║
# ║  → 공용 인덱스 테이블명도 다르다: dart_employees_ext (다른 전략도 그대로 재사용 가능)       ║
# ║                                                                                          ║
# ║  ★ 설계상 가장 중요한 결정: EMP 센서는 **연도 프레임에서 계산한다.**                        ║
# ║    월 패널에 먼저 붙인 뒤 diff(12) 를 하면, 제출일(rcept_dt)이 해마다 며칠씩 밀리는         ║
# ║    구조 때문에 "12개월 전 행"이 같은 사업연도를 가리키는 달이 생긴다 → 차분이 0 이 되고     ║
# ║    Δ직원수=0 이 되어 C15(a) 가 그 관측을 통째로 버린다. 조용히, 로그 없이.                  ║
# ║    연도 프레임에서 계산하면 Δ는 언제나 정확히 1개 사업연도 간격이고,                        ║
# ║    PIT 안전성은 merge_asof(knowledge_date=rcept_dt) 가 그대로 보장한다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EMP_EXT_COLS = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "employees",
                "regular", "payroll_total", "avg_salary", "n_rows", "unit_fix",
                "pay_fix", "src_flag"]

_TOTAL_TOKENS = {"합계", "계", "소계", "총계", "합 계", "전체", "총 계", "합계(계)", "-"}

# 서킷브레이커 — 연속 실패가 이 수를 넘으면 남은 호출을 즉시 포기한다(§3).
EMP_CIRCUIT_MAX = 15

# 예산 예약 라벨. 이 이름으로 예약된 호출은 직원현황만 인출할 수 있다.
EMP_PURPOSE = "emp"

# 이번 실행에서 직원현황 수집이 잘렸는가. §6 커버리지 판정이 '미수집'을 'DART 결측'으로
# 오독하지 않게 하는 근거. dropped>0 이면 자동 창 단축(COVERAGE_AUTO_TRIM)을 걸지 않는다.
EMP_TRUNCATED: Dict[str, Any] = {"dropped": 0, "why": ""}
_EMP_CB = {"consec": 0, "tripped": False, "lock": threading.Lock()}

# 미제출(013) 원장 — 답이 존재하지 않는 (회사, 연도). 다음 실행에서 다시 묻지 않는다.
_EMP_NODATA: List[dict] = []
EMP_NODATA_TABLE = "dart_emp_nodata"


def _emp_cb_ok() -> bool:
    # ★ 예산이 이미 바닥났으면 한 건도 시도하지 않는다. 예전엔 예산 거부(None)를 '실패'로
    #   세어 서킷브레이커가 15건 만에 터질 때까지 헛돌았고, 각 호출마다 0.05~0.15초를
    #   자고 있었다 — 14,000건이면 12스레드로도 2분을 아무 일 없이 태운다.
    if dart_halt_reason(EMP_PURPOSE):
        return False
    with _EMP_CB["lock"]:
        return not _EMP_CB["tripped"]


def _emp_cb_mark(success: bool):
    with _EMP_CB["lock"]:
        if success:
            _EMP_CB["consec"] = 0
        else:
            _EMP_CB["consec"] += 1
            if _EMP_CB["consec"] >= EMP_CIRCUIT_MAX and not _EMP_CB["tripped"]:
                _EMP_CB["tripped"] = True
                # ★ 사유를 추측하지 않는다. 예산 소진·인증 오류는 이미 기록돼 있으므로
                #   "대개 …입니다" 같은 짐작 대신 실제 사유를 그대로 말한다. 짐작이 틀리면
                #   사용자는 멀쩡한 키를 의심하거나 IP 차단을 걱정하며 시간을 버린다.
                why = dart_halt_reason(EMP_PURPOSE)
                LOG.warn(f"직원현황 수집 중단 — 연속 {EMP_CIRCUIT_MAX}건 실패. "
                         f"남은 호출을 포기하고 여기까지 받은 것을 저장합니다. "
                         + (f"사유: {why}. 내일 재실행하면 이어받습니다."
                            if why else
                            "예산·인증에는 이상이 없습니다 — 네트워크 또는 DART 서버 상태를 "
                            "확인하세요(이 경우는 데이터 부재가 아닙니다)."))


def _emp_pick_rows(d: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """부문×성별 분해 행만 남긴다. 소계/합계 행과 섞으면 인원이 두 배로 계산된다.

    다만 '분해 행이 아예 없고 합계 행 하나만 제출한 회사'가 실재한다. 그 경우까지
    버리면 중소형주가 통째로 사라지므로, 분해 행이 없을 때만 합계 행을 쓴다.
    어느 경로를 탔는지는 src_flag 로 남겨 하류에서 감사할 수 있게 한다.
    """
    def _is_total(colname):
        if colname not in d.columns:
            return pd.Series(False, index=d.index)
        v = d[colname].astype(str).str.strip()
        return v.isin(_TOTAL_TOKENS)

    tot_b, tot_s = _is_total("fo_bbm"), _is_total("sexdstn")
    detail = d[~tot_b & ~tot_s]
    if len(detail):
        return detail, "detail"
    # 부문만 합계이고 성별은 분해된 경우 (또는 그 반대)
    half = d[~(tot_b & tot_s)]
    if len(half):
        return half, "half"
    return d, "total_only"


def _norm_money(v: float, kind: str) -> Tuple[float, int]:
    """단위(원/천원/백만원) 혼재 보정. (보정값, 적용배수) 를 돌려준다.

    한국 상장사 1인 평균급여의 현실 범위는 대략 1,500만 ~ 3억원이다.
    이 범위를 크게 벗어나면 단위가 원이 아니라는 뜻이므로 1000 배수로 스냅한다.
    범위 안으로 못 들어오면 보정하지 않고 그대로 둔다 — 억지로 맞추면 조용한 오염이 된다.
    """
    if not np.isfinite(v) or v <= 0:
        return (np.nan, 1)
    lo, hi = (5e6, 5e8) if kind == "avg" else (0.0, np.inf)
    if kind != "avg":
        return (v, 1)
    for mult in (1, 1_000, 1_000_000):
        if lo <= v * mult <= hi:
            return (v * mult, mult)
    return (v, 1)


def _emp_one_raw(corp: str, year: int) -> Optional[dict]:
    """empSttus 단건 → 정규화된 연 1행. 실패는 None (예외를 위로 던지지 않는다)."""
    if not _emp_cb_ok():
        return None
    try:
        time.sleep(0.05 + random.random() * 0.10)          # §5 — 0.05~0.15s 지연
        js = dart_api("empSttus.json", {"corp_code": str(corp), "bsns_year": str(int(year)),
                                        "reprt_code": REPRT_CODES["FY"]}, no_data_ok=True,
                      purpose=EMP_PURPOSE)
    except Exception:
        _emp_cb_mark(False)
        return None
    # ★ '그 해에 사업보고서를 안 낸 회사'(status 013)는 **정상 응답**이지 실패가 아니다.
    #   실패로 세면 서킷브레이커가 정상 데이터만으로 터진다: 잡 격자가 corp × year 라
    #   신규상장사·폐지사는 초기/말기 연도가 통째로 013 이고, 12개 스레드가 공유하는
    #   연속실패 카운터는 그런 회사 몇 곳이면 15에 도달한다. 그러면 아직 받지 않은
    #   수천 건을 전부 포기하고, 로그에는 '차단당한 것 같다'는 오해를 남긴다.
    if isinstance(js, dict) and str(js.get("status", "")) == "013":
        _emp_cb_mark(True)
        # ★ '그 해에 제출하지 않았다'는 **영구적 사실**이다. 그런데 흔적을 남기지 않아
        #   매 실행 다시 물었다. 유니버스가 생존자편향 없이 구성돼 있어 폐지 이후·상장 이전
        #   연도가 격자의 40% 가까이 되고, 그게 연도 내림차순 큐의 앞쪽에 몰린다.
        #   → 답이 있을 수 없는 질문에 매일 한도의 대부분을 쓰고 있었다. 기록해 둔다.
        with _EMP_CB["lock"]:
            _EMP_NODATA.append({"corp_code": str(corp), "bsns_year": int(year)})
        return None
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        _emp_cb_mark(False)
        return None
    _emp_cb_mark(True)

    d = pd.DataFrame(js["list"])
    sel, flag = _emp_pick_rows(d)
    if sel.empty:
        return None

    sm = _num_series(sel.get("sm", pd.Series(dtype=object)))
    reg = _num_series(sel.get("rgllbr_co", pd.Series(dtype=object)))
    cnt = _num_series(sel.get("cnttk_co", pd.Series(dtype=object)))
    tot = _num_series(sel.get("fyer_salary_totamt", pd.Series(dtype=object)))
    jan = _num_series(sel.get("jan_salary_am", pd.Series(dtype=object)))

    emp = float(sm.sum(skipna=True)) if sm.notna().any() else np.nan
    if not np.isfinite(emp) or emp <= 0:
        # sm 이 비면 정규직+계약직으로 복원한다 (일부 제출본이 sm 을 비워 둔다)
        alt = float(reg.fillna(0).sum() + cnt.fillna(0).sum())
        emp = alt if alt > 0 else np.nan
    regular = float(reg.sum(skipna=True)) if reg.notna().any() else np.nan
    payroll = float(tot.sum(skipna=True)) if tot.notna().any() else np.nan

    # ★ jan_salary_am(1인 평균급여)은 절대 합산하지 않는다. 인원 가중평균이 유일하게 옳다.
    if jan.notna().any() and sm.notna().any():
        w = sm.where(sm > 0)
        num = (jan * w).sum(skipna=True)
        den = w.where(jan.notna()).sum(skipna=True)
        avg = float(num / den) if den and den > 0 else float(jan.mean(skipna=True))
    elif jan.notna().any():
        avg = float(jan.mean(skipna=True))
    else:
        avg = np.nan

    avg, unit_fix = _norm_money(avg, "avg")

    # ── 급여총액 단위 보정 ──────────────────────────────────────────────────────────────
    #   tot ≈ avg × emp 가 성립해야 한다. 다만 **먼저 '고칠 필요가 있는가'를 묻는다.**
    #
    #   ★ 가장 가까운 1000 배수를 무조건 고르면 멀쩡한 값을 망친다: 1인평균급여가 그 회사를
    #     대표하지 못하는 제출본(예: 임원만 기재)에서는 expect 가 실제보다 수십 배 작아지고,
    #     그러면 '÷1000' 이 오히려 오차를 줄이는 것처럼 보여 **정확한 급여총액이 1000분의 1로
    #     조용히 축소된다.** 한계임금은 이 값의 차분이므로 그대로 신호가 뒤집힌다.
    #   → 원값이 이미 10배 이내면 손대지 않는다. 명백히 틀렸을 때만, 그것도 배수 보정이
    #     3배 이내로 들어맞을 때만 고친다. 둘 다 아니면 폐기한다(0 채움 금지).
    pay_fix = 1
    if np.isfinite(payroll) and np.isfinite(avg) and np.isfinite(emp) and emp > 0 and avg > 0:
        expect = avg * emp
        err0 = abs(math.log10(max(payroll, 1e-9) / expect))
        if err0 > 1.0:                                     # 10배 넘게 어긋난 경우에만 개입
            best, best_err = None, np.inf
            for m2 in (1_000, 1_000_000, 0.001, 0.000001):
                err = abs(math.log10(max(payroll * m2, 1e-9) / expect))
                if err < best_err:
                    best, best_err = m2, err
            if best_err <= 0.5:                            # 보정 후 3배 이내로 맞을 때만 채택
                payroll, pay_fix = payroll * best, best
            else:
                payroll = np.nan                           # §5 — 불일치 10배+ 폐기

    rn = str(sel["rcept_no"].iloc[0]) if "rcept_no" in sel.columns and len(sel) else ""
    kd = _knowledge_from_rcept(rn, REPRT_CODES["FY"], int(year))
    return {"corp_code": str(corp), "bsns_year": int(year), "rcept_no": rn,
            "rcept_dt": kd, "employees": emp, "regular": regular,
            "payroll_total": payroll, "avg_salary": avg, "n_rows": int(len(sel)),
            "unit_fix": int(unit_fix), "pay_fix": float(pay_fix), "src_flag": flag}


def fetch_emp_status(corp_codes: Sequence[str], years: Sequence[int],
                     priority: Optional[Sequence[str]] = None,
                     max_calls: Optional[int] = None) -> pd.DataFrame:
    """empSttus 증분 수집. 공용 캐시(dart_employees_ext)를 먼저 소진하고 부족분만 호출한다.

    ★ 잡 수는 |기업| × |연도| 로 곱해진다(3,981사 × 13년 = 51,753 > 일일한도 19,000).
      max_calls 로 이번 실행분을 잘라내고, priority 순서로 '담길 확률이 높은 종목'부터 채운다.
      한계임금은 이 전략의 알파 원천이므로 Tier-2 재무보다 **먼저** 예산을 배정한다.
    """
    cached = VAULT.get_table("dart_employees_ext", scope="shared")
    done = set()
    if cached is not None and len(cached):
        try:
            done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
            LOG.ok(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용 ({len(done):,} 조합) — "
                   f"이만큼은 API 를 다시 부르지 않습니다")
        except Exception:
            done = set()
    nod = VAULT.get_table(EMP_NODATA_TABLE, scope="shared")
    if nod is not None and len(nod):
        try:
            skip = set(zip(nod["corp_code"].astype(str), nod["bsns_year"].astype(int)))
            done |= skip
            LOG.info(f"미제출 원장에서 {len(skip):,} (사×연) 을 제외합니다 — "
                     f"그 해 사업보고서를 내지 않은 조합이라 다시 물어도 답이 없습니다.")
        except Exception:
            pass
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 직원현황 신규 수집을 건너뜁니다. "
                 "캐시에 있는 것만으로 진행하며, 없으면 EMP-LITE 전 센서가 결측입니다.")
        return _emp_finalize(cached, [])

    corps = [str(c) for c in dict.fromkeys(corp_codes) if str(c) and str(c) != "nan"]
    if EMP_MAX_CORPS and EMP_MAX_CORPS > 0:
        corps = corps[:EMP_MAX_CORPS]
    # 담길 확률이 높은 종목 먼저 — 예산에 걸려 잘려도 '쓸 수 있는' 한계임금이 먼저 완성된다.
    _ord = {str(c): i for i, c in enumerate(priority or [])}
    corps = sorted(corps, key=lambda c: (_ord.get(c, 10 ** 9), c))
    # 최근 연도 우선. 차분에 t-1 이 필요하므로 연도는 내림차순으로 촘촘히 채운다.
    jobs = [(c, y) for y in sorted(years, reverse=True) for c in corps if (c, int(y)) not in done]
    if RUN_MODE == "CACHED":
        if jobs:
            LOG.info(f"RUN_MODE='CACHED' — 신규 수집 대상 {len(jobs):,}건을 건너뜁니다.")
        jobs = []

    got: List[dict] = []
    if jobs:
        total_needed = len(jobs)
        if max_calls is not None:
            left = dart_budget_left(EMP_PURPOSE)
            cap = max(0, min(total_needed, int(max_calls), left))
            if cap < total_needed:
                # ★ 절단 사실을 기록해 둔다. §6 커버리지 판정이 이 표를 'DART 의 보유량'으로
                #   오독해 백테스트 창을 영구히 잘라내는 것을 막기 위한 유일한 근거다.
                EMP_TRUNCATED.update({
                    "dropped": total_needed - cap,
                    "why": (f"오늘 남은 DART 호출 {left:,}건" if left < int(max_calls)
                            else f"상한 EMP_MAX_CALLS={int(max_calls):,}")})
                jobs = jobs[:cap]
                LOG.warn(f"직원현황 {total_needed:,}건 중 이번 실행은 {cap:,}건만 받습니다 "
                         f"(오늘 남은 DART 호출 {left:,}건 · 상한 EMP_MAX_CALLS={max_calls:,}). "
                         f"우선순위 상위 종목·최근 연도부터 채웠으며, 재실행하면 이어받습니다. "
                         f"※ 미수집분이 있으므로 §6 커버리지 기반 자동 창 단축은 비활성화됩니다.")
        LOG.info(f"직원현황 신규 수집 {len(jobs):,}건 "
                 f"({len(corps):,}사 × {len(years)}년, 캐시 적중 {len(done):,}) — "
                 f"약 {len(jobs)/max(RATE_LIMIT_QPS.get('dart',8.0),1)/60:.0f}분 예상")
        _EMP_CB.update({"consec": 0, "tripped": False})
        # ══════════════════════════════════════════════════════════════════════════════════
        #  ★ 청크 체크포인트 — 예산은 200건마다 영속되는데 **데이터는 맨 끝에 한 번**이었다.
        #    비대칭이 치명적이다: 28분째에 죽으면 드라이브에는 '14,000건 썼음'만 남고
        #    dart_employees_ext 는 0행 그대로다. 다음 실행은 예산이 없다며 정당하게 거부한다.
        #    → 세션 종료·OOM·Ctrl+C 어디서 끊겨도 **받은 만큼은 반드시 남는다.**
        #    Vault 는 append-only 저널이라 증분 저장이 싸고 안전하다.
        # ══════════════════════════════════════════════════════════════════════════════════
        got, done_n = [], 0
        for i in range(0, len(jobs), EMP_CHECKPOINT_EVERY):
            chunk = jobs[i:i + EMP_CHECKPOINT_EVERY]
            res = pmap_io(lambda j: _emp_one_raw(j[0], j[1]), chunk,
                          workers=min(N_WORKERS_IO, 12),
                          desc=f"DART 직원현황({i//EMP_CHECKPOINT_EVERY + 1}/"
                               f"{math.ceil(len(jobs)/EMP_CHECKPOINT_EVERY)})")
            got.extend(r for r in res if r)
            done_n += len(chunk)
            _emp_checkpoint(cached, got)
            if not _emp_cb_ok():          # 예산 소진·브레이커 → 남은 청크는 의미 없다
                if done_n < len(jobs):
                    EMP_TRUNCATED.update({
                        "dropped": len(jobs) - done_n,
                        "why": dart_halt_reason(EMP_PURPOSE) or "수집 중단(서킷브레이커)"})
                    LOG.warn(f"직원현황 수집을 {done_n:,}/{len(jobs):,}건에서 멈춥니다 — "
                             f"{EMP_TRUNCATED['why']}. 여기까지는 드라이브에 저장됐습니다. "
                             f"※ 미수집분이 있으므로 §6 자동 창 단축은 비활성화됩니다.")
                break
        LOG.info(f"직원현황 신규 확보 {len(got):,}/{len(jobs):,}건")
    return _emp_finalize(cached, got)


EMP_CHECKPOINT_EVERY = 1_000


def _emp_checkpoint(cached: Optional[pd.DataFrame], got: List[dict]) -> None:
    """지금까지 받은 것을 공용 인덱스에 즉시 반영한다(실패해도 수집은 계속)."""
    try:
        if got:
            E = pd.concat([f for f in (cached, pd.DataFrame(got)) if f is not None and len(f)],
                          ignore_index=True)
            E["corp_code"] = E["corp_code"].astype(str)
            E = E.drop_duplicates(["corp_code", "bsns_year"], keep="last")
            VAULT.put_table("dart_employees_ext", E, scope="shared", domain="dart",
                            source="opendart empSttus 확장 (증분 체크포인트)")
        if _EMP_NODATA:
            prev = VAULT.get_table(EMP_NODATA_TABLE, scope="shared")
            N = pd.concat([f for f in (prev, pd.DataFrame(_EMP_NODATA))
                           if f is not None and len(f)], ignore_index=True)
            N["corp_code"] = N["corp_code"].astype(str)
            VAULT.put_table(EMP_NODATA_TABLE, N.drop_duplicates(["corp_code", "bsns_year"]),
                            scope="shared", domain="dart",
                            source="empSttus 미제출(013) 원장 — 재요청 방지")
    except Exception as e:                                          # noqa
        LOG.debug(f"직원현황 체크포인트 실패({type(e).__name__}) — 수집은 계속합니다.")


def _emp_finalize(cached: Optional[pd.DataFrame], got: List[dict]) -> pd.DataFrame:
    frames = []
    if cached is not None and len(cached):
        frames.append(cached)
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        LOG.warn("직원현황 데이터가 전혀 없습니다 — EMP-LITE 3개 TP 가 모두 결측이 됩니다.")
        return pd.DataFrame(columns=EMP_EXT_COLS)
    E = pd.concat(frames, ignore_index=True)
    for c in EMP_EXT_COLS:
        if c not in E.columns:
            E[c] = np.nan
    E["corp_code"] = E["corp_code"].astype(str)
    E["bsns_year"] = pd.to_numeric(E["bsns_year"], errors="coerce").astype("Int64")
    E = E.dropna(subset=["bsns_year"])
    E["bsns_year"] = E["bsns_year"].astype(int)
    E = E.drop_duplicates(["corp_code", "bsns_year"], keep="last").reset_index(drop=True)
    E["rcept_dt"] = as_ts_series(E["rcept_dt"])
    # rcept_dt 가 없으면 법정 제출기한(사업보고서 90일)으로 보수적 추정 — '늦게 알았다' 방향
    miss = E["rcept_dt"].isna()
    if miss.any():
        E.loc[miss, "rcept_dt"] = [
            _knowledge_from_rcept("", REPRT_CODES["FY"], int(y)) for y in E.loc[miss, "bsns_year"]]
    if got:
        VAULT.put_table("dart_employees_ext", E, scope="shared", domain="dart",
                        source="opendart empSttus (v3 확장: jan_salary_am·rgllbr_co 포함)")
    PIPE.io("OUT", "DRIVE", "dart_employees_ext", E, source="opendart empSttus")
    LOG.ok(f"직원현황 총 {len(E):,}행 · {E['corp_code'].nunique():,}사 · "
           f"{E['bsns_year'].min()}~{E['bsns_year'].max()}년 "
           f"(급여총액 기재 {E['payroll_total'].notna().mean():.0%})")
    # 단위 정규화가 얼마나 개입했는지 드러낸다 — 조용한 보정은 조용한 오염과 구별되지 않는다.
    rows = []
    if "unit_fix" in E.columns:
        for m, n in E["unit_fix"].value_counts().sort_index().items():
            rows.append([f"1인평균급여 ×{int(m):,}", f"{int(n):,}",
                         "원 단위 그대로" if int(m) == 1 else "천원/백만원 기재로 판단해 환산"])
    if "pay_fix" in E.columns:
        for m, n in E["pay_fix"].value_counts().sort_index().items():
            rows.append([f"급여총액 ×{float(m):g}", f"{int(n):,}",
                         "손대지 않음" if float(m) == 1.0 else "10배 초과 불일치 → 배수 보정"])
    n_drop = int(E["payroll_total"].isna().sum())
    rows.append(["급여총액 결측/폐기", f"{n_drop:,}", "무기재이거나 10배+ 불일치로 폐기(0 채움 안 함)"])
    if "src_flag" in E.columns:
        for f, n in E["src_flag"].value_counts().items():
            rows.append([f"행 선택 경로: {f}", f"{int(n):,}",
                         {"detail": "부문×성별 분해행 사용(정상)",
                          "half": "한쪽만 합계 — 부분 분해",
                          "total_only": "합계행만 제출 — 이중계상 위험 없음"}.get(str(f), "")])
    LOG.table(rows, ["단위·행선택 정규화", "건수", "의미"], ["l", "r", "l"],
              title="직원현황 정규화 감사 (K9 단위 정합성의 실측 결과)")
    return E


# ── C15 : 한계임금 분모 안정성 (스펙 §4 신설 계약) ──────────────────────────────────────────
C15_STATS: Dict[str, Any] = {}


def build_emp_sensors(E: pd.DataFrame) -> pd.DataFrame:
    """연도 프레임에서 EMP-LITE 센서를 만든다. C15 (a)(b)(d) 를 여기서 강제한다.

    출력 컬럼(연 1행/사):
      nl_emp      Δlog(직원수)
      nl_dn       Δ(직원수)
      nl_marginal Δ(연간급여총액) / Δ(직원수)          ← C15 조건부
      nl_premium  nl_marginal / 전기 1인평균급여액       ← ★ 이 전략의 핵심
      nl_regular  Δ(정규직 비중)
      emp_ok      C15 전 조건 통과 여부 (커버리지 감사용)
    """
    if E is None or E.empty:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "knowledge_date"])
    D = E.sort_values(["corp_code", "bsns_year"]).copy()
    g = D.groupby("corp_code", observed=True)

    # ★ 연도가 비연속이면(예: 2018 → 2020) 차분이 2년치가 되어 '1년간 변화'라는 전제가 깨진다.
    #   그런 관측은 계산하지 않는다. 채워 넣지도 않는다(C15: forward-fill 금지).
    D["year_gap"] = g["bsns_year"].diff()
    contiguous = D["year_gap"] == 1

    emp_prev = g["employees"].shift(1)
    pay_prev = g["payroll_total"].shift(1)
    avg_prev = g["avg_salary"].shift(1)
    reg_ratio = safe_div(D["regular"], D["employees"])
    D["regular_ratio"] = reg_ratio.where((reg_ratio >= 0) & (reg_ratio <= 1.001))

    D["emp_prev"] = emp_prev.where(contiguous)
    D["dn"] = (D["employees"] - emp_prev).where(contiguous)
    D["d_pay"] = (D["payroll_total"] - pay_prev).where(contiguous)
    D["nl_emp"] = np.log(D["employees"].where(D["employees"] > 0)) - \
                  np.log(D["emp_prev"].where(D["emp_prev"] > 0))
    D["nl_dn"] = D["dn"]
    D["nl_regular"] = (D["regular_ratio"] - g["regular_ratio"].shift(1)).where(contiguous) \
        if "regular_ratio" in D.columns else np.nan

    # (a) |Δ직원수| >= max(5, 직원수_{t-1} × 3%) 일 때만 계산
    thresh = np.maximum(C15_MIN_ABS_DN, D["emp_prev"].fillna(0) * C15_MIN_REL_DN)
    gate_a = D["dn"].abs() >= thresh

    # (d) Δ직원수 급변 (>+100% / <-50%) = M&A·분할 의심 → 결측
    rel = safe_div(D["dn"], D["emp_prev"])
    gate_d = (rel <= C15_MNA_UP) & (rel >= C15_MNA_DN)

    ok = gate_a.fillna(False) & gate_d.fillna(False) & contiguous.fillna(False)
    D["nl_marginal"] = safe_div(D["d_pay"], D["dn"]).where(ok)

    # (b) 임금프리미엄 [0, 5] 클리핑. 초과는 '오류'로 보고 NaN — 절대 clip 으로 뭉개지 않는다.
    prem_raw = safe_div(D["nl_marginal"], avg_prev.where(avg_prev > 0))
    in_range = prem_raw.between(C15_PREMIUM_LO, C15_PREMIUM_HI)
    n_out = int((prem_raw.notna() & ~in_range).sum())
    D["nl_premium"] = prem_raw.where(in_range)
    D["emp_ok"] = (D["nl_premium"].notna()).astype(int)

    C15_STATS.update({
        "n_rows": int(len(D)),
        "n_contiguous": int(contiguous.sum()),
        "n_gate_a_fail": int((~gate_a.fillna(False) & contiguous.fillna(False)).sum()),
        "n_gate_d_fail": int((~gate_d.fillna(False) & contiguous.fillna(False)).sum()),
        "n_premium_out_of_range": n_out,
        "n_valid": int(D["nl_premium"].notna().sum()),
    })
    LOG.table([["전체 (사×연) 관측", f"{C15_STATS['n_rows']:,}"],
               ["연도 연속(Δ=1년)", f"{C15_STATS['n_contiguous']:,}"],
               ["(a) |Δ인원| 임계 미달 → 결측", f"{C15_STATS['n_gate_a_fail']:,}"],
               ["(d) M&A·분할 의심 → 결측", f"{C15_STATS['n_gate_d_fail']:,}"],
               ["(b) 프리미엄 [0,5] 이탈 → 결측", f"{C15_STATS['n_premium_out_of_range']:,}"],
               ["★ 최종 유효 임금프리미엄", f"{C15_STATS['n_valid']:,}"]],
              ["C15 게이트", "건수"], ["l", "r"],
              title="C15 한계임금 분모 안정성 (0 채움·forward-fill 금지)")

    # knowledge_date = 사업보고서 접수일. 이것이 PIT 의 전부다.
    D["knowledge_date"] = as_ts_series(D["rcept_dt"])
    D["period_end"] = as_ts_series(D["bsns_year"].astype(int).astype(str) + "-12-31")
    # ★ d_pay·avg_prev 를 함께 내보내는 이유: R5 절제검사가 C15 분모 임계값을 바꿔가며
    #   한계임금을 '재계산'해야 하는데, 원재료가 패널에 없으면 그 절제는 아예 불가능하다.
    D["avg_prev"] = avg_prev
    keep = ["corp_code", "bsns_year", "period_end", "knowledge_date", "employees", "emp_prev",
            "regular_ratio", "payroll_total", "avg_salary", "avg_prev", "dn", "d_pay",
            "nl_emp", "nl_dn", "nl_marginal", "nl_premium", "nl_regular", "emp_ok", "src_flag"]
    out = D[[c for c in keep if c in D.columns]].copy()
    return out


def test_c15(df: pd.DataFrame) -> Tuple[bool, str]:
    """스펙 §4 의 test_c15 를 그대로 코드로 옮긴 자가검정."""
    if df is None or df.empty or "dn" not in df.columns:
        return True, "표본 없음 — 검정 생략"
    d = df.dropna(subset=["emp_prev"])
    if d.empty:
        return True, "표본 없음 — 검정 생략"
    ok = d["dn"].abs() >= np.maximum(C15_MIN_ABS_DN, d["emp_prev"] * C15_MIN_REL_DN)
    leak = int(d.loc[~ok, "nl_marginal"].notna().sum())
    if leak:
        return False, f"C15(a) 위반 — 임계 미달인데 한계임금이 계산된 행 {leak:,}건"
    p = d["nl_premium"].dropna()
    if len(p) and not p.between(C15_PREMIUM_LO, C15_PREMIUM_HI).all():
        return False, (f"C15(b) 위반 — 임금프리미엄이 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}] 밖: "
                       f"min={p.min():.2f} max={p.max():.2f}")
    return True, f"통과 (유효 프리미엄 {len(p):,}건 · 전부 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}])"


# ── §6 커버리지 감사 (필수 출력) ────────────────────────────────────────────────────────────
def emp_coverage_audit(S: pd.DataFrame, umid_n: Dict[int, int],
                       umid_corps: Optional[Dict[int, set]] = None) -> pd.DataFrame:
    """연도별: U-MID 대상 / empSttus 성공 / 급여총액 기재 / C15 통과 / 유효 관측치.

    ★ 분자와 분모는 반드시 같은 모집단이어야 한다. umid_corps 를 주면 그 해 U-MID 였던
      기업으로 분자를 제한한다. 주지 않으면 전 상장사 기준이며, 그 사실을 표 제목에 밝힌다.
    반환 DataFrame 은 emp_coverage.csv 로 저장되고, 시작연도 판정의 근거가 된다.
    """
    rows = []
    if S is None or S.empty:
        LOG.warn("직원현황 패널이 비어 커버리지 감사를 출력할 수 없습니다.")
        return pd.DataFrame(columns=["year", "u_mid", "emp_ok", "pay_ok", "c15_ok", "valid"])
    scoped = umid_corps is not None and len(umid_corps) > 0
    for y in sorted(S["bsns_year"].dropna().astype(int).unique()):
        sub = S[S["bsns_year"] == y]
        if scoped:
            # 사업연도 y 의 공시는 y+1 년에 알려지므로, 그 해 U-MID 였던 기업 기준으로 센다.
            #   ★ 교집합이 비면 그 해엔 U-MID 종목이 아예 없다는 뜻이다(대개 백테스트 창 밖).
            #     그때 필터를 건너뛰면 분자만 전 상장사로 튀어 분모(0)와 어긋난다 → 0 으로 센다.
            keep = umid_corps.get(int(y), set()) | umid_corps.get(int(y) + 1, set())
            sub = sub[sub["corp_code"].astype(str).isin(keep)] if keep else sub.iloc[0:0]
        # ★ 분모도 분자와 **같은 집합**에서 센다. 분모를 '그 해 U-MID', 분자를 'y 또는 y+1 에
        #   U-MID' 로 두면 (사업연도 y 의 공시는 y+1 에 알려지므로 분자는 y+1 을 포함해야 한다)
        #   표가 자기모순에 빠진다 — 분모 0 인데 분자 84 같은 행이 나온다.
        denom = len(keep) if scoped else int(umid_n.get(int(y), 0))
        rows.append({
            "year": int(y),
            "u_mid": int(denom),
            "emp_ok": int(sub["employees"].notna().sum()),
            "pay_ok": int(sub["payroll_total"].notna().sum()),
            "c15_ok": int(sub["nl_marginal"].notna().sum()),
            "valid": int(sub["nl_premium"].notna().sum()),
        })
    C = pd.DataFrame(rows)
    LOG.table([[str(r.year), f"{r.u_mid:,}", f"{r.emp_ok:,}", f"{r.pay_ok:,}",
                f"{r.c15_ok:,}", f"{r.valid:,}",
                "구간밖" if (scoped and r.u_mid == 0) else
                ("부족" if r.valid < C15_MIN_OBS_PER_YR else
                 ("경계" if r.valid < COVERAGE_MIN_OBS_START else "충분"))]
               for r in C.itertuples(index=False)],
              ["사업연도", "U-MID 대상", "empSttus 성공", "급여총액 기재", "C15 통과",
               "유효 관측치", "판정"],
              ["c", "r", "r", "r", "r", "r", "c"],
              title="EMP 커버리지 감사 (§6 — 필수 출력) · 분자 모집단 = " +
                    ("U-MID 기업" if scoped else "전 상장사(분모와 불일치, 참고용)"))
    if not scoped:
        LOG.warn("커버리지 분자를 U-MID 로 제한하지 못했습니다(corp_code 매핑 부재). "
                 "비율이 과대평가될 수 있으므로 시작연도 판정을 보수적으로 읽으세요.")
    return C


def coverage_verdict(C: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], str]:
    """§6 판정: 앞구간의 유효 관측치가 부족하면 백테스트 시작월을 상향한다.

    ★ 시작연도 y 의 관측은 그 해 사업보고서(다음해 3~4월 접수)부터 신호가 되므로,
      창을 자를 때도 '사업연도 y' 가 아니라 '실제로 알 수 있게 된 시점'을 기준으로 자른다.
    """
    if C is None or C.empty:
        return None, "커버리지 표가 비어 판정을 유보합니다."

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ 이 판정의 전제: 커버리지 표가 'DART 가 실제로 보유한 양'을 잰다는 것.
    #    예산에 걸려 잘린 실행에서는 그 전제가 깨진다. 수집 잡은 연도 내림차순이라
    #    jobs[:cap] 은 **항상 오래된 연도부터** 버린다 → 커버리지는 최근이 두껍고 과거가
    #    얇은 모양이 되고, 그건 DART 의 사실이 아니라 우리 지갑의 사실이다.
    #    그 모양을 그대로 읽어 COVERAGE_AUTO_TRIM 이 창을 자르면, **일시적 예산 부족이
    #    10년 백테스트를 영구히 단축**시키고 그 단축이 §6 데이터 근거로 리포트에 박힌다.
    #  → 절단이 있었으면 자동 트림을 걸지 않는다. 자를지 말지는 완전 수집 후에 판단한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    trunc = EMP_TRUNCATED.get("dropped", 0)
    if trunc:
        return None, (
            f"이번 실행에서 직원현황 수집이 {trunc:,}건 잘렸습니다"
            f"({EMP_TRUNCATED.get('why', '호출 상한')}). 수집은 최근 연도부터 채우므로 "
            f"아래 표의 과거 연도 부족분은 **DART 의 결측이 아니라 이번 실행의 미수집**입니다. "
            f"이 표를 근거로 백테스트 창을 자르면 일시적 예산 부족이 10년 구간을 영구히 "
            f"단축시킵니다 — 자동 트림을 걸지 않습니다. 재실행으로 수집을 완성한 뒤 재판정하세요.")

    good = C[C["valid"] >= COVERAGE_MIN_OBS_START]
    if good.empty:
        worst = int(C["valid"].max()) if len(C) else 0
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 미만입니다 "
                      f"(최대 {worst:,}건). 창을 자르지 않고 전 구간을 쓰되, "
                      f"EMP 신호의 검정력이 낮다는 사실을 결론에 명시합니다.")
    y0 = int(good["year"].min())
    thin = C[C["year"] < y0]
    if thin.empty:
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 이상입니다 "
                      f"— 백테스트 창을 그대로 사용합니다.")
    start = as_ts(f"{y0 + 1}-04-01")          # 사업연도 y0 는 y0+1 년 3~4월에 공시된다
    msg = (f"{int(thin['year'].min())}~{int(thin['year'].max())}년 유효 관측치가 "
           f"{COVERAGE_MIN_OBS_START}건 미만(" +
           ", ".join(f"{int(r.year)}:{int(r.valid)}" for r in thin.itertuples(index=False)) +
           f") → EMP 신호 유효 시작 {start:%Y-%m}. ")
    if COVERAGE_AUTO_TRIM:
        msg += "COVERAGE_AUTO_TRIM=True 이므로 EMP TP 를 이 시점 이전에는 결측으로 둡니다."
    else:
        msg += "COVERAGE_AUTO_TRIM=False 이므로 자르지 않고 그대로 진행합니다."
    return (start if COVERAGE_AUTO_TRIM else None), msg

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  정책 캘린더 (R10 정책반증의 입력)                                                         ║
# ║                                                                                          ║
# ║  모든 대체데이터는 정책에 오염된다. 다만 정책 시행일은 공개되어 있고 정확하다               ║
# ║  → 이 오염만은 자연실험 설계가 가능하다. 이벤트 ±6개월을 빼고도 알파가 남는지 본다.         ║
# ║                                                                                          ║
# ║  ★ 고용 관련 제도를 빠짐없이 넣는 것이 이 전략에서 특히 중요하다. TP_N1(한계임금)은         ║
# ║    설계상 보조금 채용을 걸러내지만, '걸러진다'는 주장 자체를 R10 이 반증해야 한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

POLICY_COLS_V3 = ["policy_id", "name", "start", "end", "kind", "req_type", "req_value", "url"]

POLICY_EVENTS_V3 = [
    # ── 고용 보조금·장려금 (TP_N1 의 직접 오염원) ──────────────────────────────────────────
    {"policy_id": "YOUTH_TOMORROW_2016", "name": "청년내일채움공제 시행", "start": "2016-07-01",
     "end": "2021-12-31", "kind": "고용장려금", "req_type": "연령·근속", "req_value": "만15~34세"},
    {"policy_id": "PUBLIC_REGULAR_2017", "name": "공공부문 비정규직 정규직 전환 지침",
     "start": "2017-07-20", "end": None, "kind": "고용규제", "req_type": "고용형태", "req_value": "비정규직"},
    {"policy_id": "MINWAGE_2018", "name": "최저임금 16.4% 인상", "start": "2018-01-01",
     "end": None, "kind": "임금규제", "req_type": "임금", "req_value": "7,530원"},
    {"policy_id": "JOB_STABILITY_FUND", "name": "일자리안정자금 시행", "start": "2018-01-01",
     "end": "2022-12-31", "kind": "고용장려금", "req_type": "규모", "req_value": "30인 미만"},
    {"policy_id": "EMP_INCREASE_TAXCREDIT", "name": "고용증대 세액공제 도입", "start": "2018-01-01",
     "end": "2022-12-31", "kind": "세액공제", "req_type": "고용증가", "req_value": "상시근로자 증가"},
    {"policy_id": "DURUNURI_EXPAND", "name": "두루누리 사회보험료 지원 확대", "start": "2018-01-01",
     "end": None, "kind": "고용장려금", "req_type": "규모·임금", "req_value": "10인 미만"},
    {"policy_id": "YOUTH_ADDL_HIRE_2018", "name": "청년추가고용장려금", "start": "2018-03-15",
     "end": "2021-12-31", "kind": "고용장려금", "req_type": "청년 신규채용", "req_value": "1인당 연 900만원"},
    {"policy_id": "WORKWEEK_52_L", "name": "주52시간제 (300인 이상)", "start": "2018-07-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "300인 이상"},
    {"policy_id": "MINWAGE_2019", "name": "최저임금 10.9% 인상", "start": "2019-01-01",
     "end": None, "kind": "임금규제", "req_type": "임금", "req_value": "8,350원"},
    {"policy_id": "WORKWEEK_52_M", "name": "주52시간제 (50~299인)", "start": "2020-01-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "50~299인"},
    {"policy_id": "COVID_EMP_RETAIN", "name": "코로나 고용유지지원금 특례 확대", "start": "2020-03-01",
     "end": "2022-06-30", "kind": "고용장려금", "req_type": "휴업·휴직", "req_value": "인건비 최대 90%"},
    {"policy_id": "WORKWEEK_52_S", "name": "주52시간제 (5~49인)", "start": "2021-07-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "5~49인"},
    {"policy_id": "YOUTH_LEAP_2022", "name": "청년일자리도약장려금", "start": "2022-01-01",
     "end": None, "kind": "고용장려금", "req_type": "청년 신규채용", "req_value": "1인당 연 960만원"},
    {"policy_id": "SERIOUS_ACCIDENT_ACT", "name": "중대재해처벌법 시행", "start": "2022-01-27",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "50인 이상"},
    {"policy_id": "INTEGRATED_EMP_TAXCREDIT", "name": "통합고용세액공제 전환", "start": "2023-01-01",
     "end": None, "kind": "세액공제", "req_type": "고용증가", "req_value": "상시근로자 증가"},
    {"policy_id": "SERIOUS_ACCIDENT_SMALL", "name": "중대재해처벌법 (50인 미만) 확대",
     "start": "2024-01-27", "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "5~49인"},

    # ── 자본배분 (TP_P1/TP_P2 의 레짐 의존성) ──────────────────────────────────────────────
    {"policy_id": "VALUEUP_2024", "name": "기업 밸류업 프로그램 발표", "start": "2024-02-26",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "VALUEUP_INDEX_2024", "name": "코리아 밸류업 지수 발표", "start": "2024-09-24",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "DIV_SEPARATE_TAX", "name": "배당소득 분리과세 논의/시행", "start": "2025-01-01",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "TREASURY_CANCEL_REFORM", "name": "자사주 소각 관련 제도 변경", "start": "2025-01-01",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},

    # ── 시장 전체 레짐 (신호-수익 관계 자체를 흔드는 국면) ─────────────────────────────────
    {"policy_id": "COVID_CRASH", "name": "코로나 급락/급반등", "start": "2020-02-20",
     "end": "2020-09-30", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
    {"policy_id": "SHORT_BAN_2020", "name": "공매도 전면금지(1차)", "start": "2020-03-16",
     "end": "2021-05-02", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
    {"policy_id": "SHORT_BAN_2023", "name": "공매도 전면금지(2차)", "start": "2023-11-06",
     "end": "2025-03-31", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
]

# R10 이 제외 대상으로 삼는 종류 — '고용' 관련만 뺀다. 시장레짐까지 빼면 표본이 남지 않는다.
R10_KINDS = ("고용장려금", "세액공제", "고용규제", "임금규제")


def build_policy_calendar_v3() -> pd.DataFrame:
    C = pd.DataFrame(POLICY_EVENTS_V3, columns=POLICY_COLS_V3)
    C["start"] = as_ts_series(C["start"])
    C["end"] = as_ts_series(C["end"]).fillna(as_ts(BACKTEST_END))
    C = C.dropna(subset=["start"]).drop_duplicates("policy_id").reset_index(drop=True)
    LOG.ok(f"정책 캘린더 {len(C)}건 등록 "
           f"(고용 관련 {int(C['kind'].isin(R10_KINDS).sum())}건 · R10 제외 대상)")
    PIPE.io("OUT", "MEM", "policy_calendar", C)
    return C


def policy_mask(cal: pd.DataFrame, months: pd.DatetimeIndex,
                kinds: Sequence[str] = R10_KINDS, halo_months: int = 6) -> pd.Series:
    """정책 이벤트 시행일·종료일 ±halo 개월 마스크 (True = 정책 구간)."""
    m = pd.Series(False, index=months)
    sel = cal[cal["kind"].isin(list(kinds))]
    for r in sel.itertuples(index=False):
        lo = r.start - pd.DateOffset(months=halo_months)
        hi = r.start + pd.DateOffset(months=halo_months)
        m |= (months >= lo) & (months <= hi)
        if pd.notna(r.end) and r.end < as_ts(BACKTEST_END):
            m |= (months >= r.end - pd.DateOffset(months=halo_months)) & \
                 (months <= r.end + pd.DateOffset(months=halo_months))
    return m


def report_policy_v3(cal: pd.DataFrame, months: pd.DatetimeIndex):
    LOG.table([[r.policy_id, _trunc(r.name, 30), str(r.start)[:10],
                str(r.end)[:10] if pd.notna(r.end) else "-", r.kind,
                _trunc(f"{r.req_type}:{r.req_value}", 22)]
               for r in cal.itertuples(index=False)],
              ["ID", "제도명", "시행", "종료", "종류", "요건"],
              ["l", "l", "l", "l", "c", "l"], title="정책 캘린더 (R10 입력)", maxw=34)
    m = policy_mask(cal, months)
    LOG.info(f"고용정책 ±6개월 구간: 전체 {len(months)}개월 중 {int(m.sum())}개월 "
             f"({100*m.mean():.0f}%) — R10 은 이 구간을 빼고 재검정합니다.")
    if m.mean() > 0.75:
        LOG.warn("정책 구간이 전체의 75%를 넘습니다. R10 잔여 표본이 얇아 검정력이 낮습니다. "
                 "이 한계를 결론 해석에 반드시 반영하세요.")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1  패널 조립 + CORE-D / EMP-LITE 센서 (스펙 §7)                                          ║
# ║                                                                                          ║
# ║  원칙 1 — PIT 조인은 merge_asof 단일 패스. 종목 루프 금지.                                  ║
# ║  원칙 3 — 셀 정규화는 rank(pct=True) + transform. groupby.apply 금지.                      ║
# ║  원칙 6 — 한계임금 분모가 불안정하면 결측. 0 채움 금지.                                     ║
# ║                                                                                          ║
# ║  ※ 이 파일에는 '원시값'만 만든다. 부호를 뒤집어 '좋을수록 큼'으로 맞추는 것까지가 여기 일이고,║
# ║    z 변환·클리핑·곱은 전부 40_score 에서 한 번만 일어난다. 두 곳에서 하면 반드시 어긋난다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 셀 (스펙 §8: date × ind_mid × size_bucket, 3단계 규모버킷) ──────────────────────────────
#   규모를 셀에 넣는 이유: 정부 지원제도 요건 대부분이 기업 규모에 연동되므로,
#   같은 규모대 안에서 상대비교하면 정책효과가 셀 내 공통충격으로 흡수된다 — 비용 0의 오염 제거.
#   버킷 경계는 한국 정책 설계(중소기업기본법 상시근로자수)를 그대로 따른다.
SIZE_BUCKETS_V3 = [(0, 300, "중소(<300)"), (300, 1000, "중견(300-999)"),
                   (1000, 10 ** 9, "대기업(1000+)")]


def size_bucket_v3(n_emp: float) -> str:
    if n_emp is None or not np.isfinite(n_emp) or n_emp <= 0:
        return "미상"
    for lo, hi, lab in SIZE_BUCKETS_V3:
        if lo <= n_emp < hi:
            return lab
    return SIZE_BUCKETS_V3[-1][2]


def build_cells_v3(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """cell = month|ind_mid|size_bucket, 폴백 사다리 = month|ind_mid|ALL → month|ALL|ALL.

    ★ 직원수가 없으면 규모를 매출 3분위로 대신한다. '미상' 한 덩어리로 두면 그 셀 안에서
      대기업과 소형주가 같은 분포에 섞여 규모효과가 신호로 둔갑한다.
    """
    ind = sec.dropna(subset=["code"]).set_index("code")["industry"].astype(str).to_dict()
    p = P.copy()
    p["ind_mid"] = p["code"].map(ind).fillna("미분류").astype(str).replace("", "미분류")
    p["ind_l1"] = p["ind_mid"].str.slice(0, 4).replace("", "미분류")

    # 벡터화(pd.cut). 14만 행 파이썬 루프를 돌 이유가 없다 — 원칙 3 의 취지가 여기에도 적용된다.
    emp = col(p, "employees")
    p["size_bucket"] = pd.cut(emp, bins=[b[0] for b in SIZE_BUCKETS_V3] + [np.inf],
                              labels=[b[2] for b in SIZE_BUCKETS_V3],
                              right=False).astype(object)
    p["size_bucket"] = p["size_bucket"].where(emp > 0).fillna("미상")
    unknown = p["size_bucket"].eq("미상")
    if unknown.any():
        rev = col(p, "revenue_ttm")
        # 월 단위 3분위 — 벡터화(qcut 를 그룹마다 부르지 않는다)
        r = rev.groupby(p["month"], observed=True).rank(pct=True)
        lab = pd.Series("미상", index=p.index, dtype=object)
        lab = lab.mask(unknown & (r < 1 / 3), "매출3분위-하")
        lab = lab.mask(unknown & (r >= 1 / 3) & (r < 2 / 3), "매출3분위-중")
        lab = lab.mask(unknown & (r >= 2 / 3), "매출3분위-상")
        p["size_bucket"] = p["size_bucket"].mask(unknown, lab)

    ym = p["month"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["ind_mid"] + "|" + p["size_bucket"]
    p["cell_l2"] = ym + "|" + p["ind_mid"] + "|ALL"
    p["cell_l3"] = ym + "|ALL|ALL"

    n_small = int((p.groupby("cell", observed=True)["code"].transform("size") < CELL_MIN_N_V3).sum())
    LOG.info(f"셀 구성 — 1단계 {p['cell'].nunique():,}개 / 2단계 {p['cell_l2'].nunique():,}개 "
             f"· 표본 {CELL_MIN_N_V3}개 미만 셀에 속한 {n_small:,}행은 조회 시 상위 셀로 폴백")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    return p


# ── 기본 격자 + PIT 결합 (C1 단일 패스) ─────────────────────────────────────────────────────
def build_base_panel_v3(uni: "Universe", months: pd.DatetimeIndex,
                        price_m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for m in months:
        codes = uni.at(m)
        uni.audit_row("PIT유니버스", m, codes)
        rows.append(pd.DataFrame({"code": codes, "month": m}))
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["code", "month"])
    P = P.merge(price_m, on=["code", "month"], how="left")
    for m in months:
        uni.audit_row("가격보유", m, P.loc[(P["month"] == m) & P["close"].notna(), "code"].tolist())
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {len(months)}개월) · "
           f"{mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel", P)
    return P


def attach_pit_sources(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """스펙 §4 C1 의 build_pit_panel — 등록된 모든 PIT 소스를 merge_asof 단일 패스로 붙인다.

    ★ 결합 후에 결측 컬럼을 채운다. 먼저 만들어 두면 merge_asof 가 접미사를 붙여
      실제 값이 <컬럼>_r 로 흘러가고, 하류는 전부 NaN 인 원래 컬럼을 읽는다.
    """
    c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
              .set_index("code")["corp_code"].astype(str).to_dict())
    P = P.copy()
    P["corp_code"] = P["code"].map(c2c)
    n_map = int(P["corp_code"].notna().sum())
    LOG.info(f"code→corp_code 매핑 {n_map:,}/{len(P):,}행 ({100*n_map/max(len(P),1):.1f}%) — "
             f"미매핑 행은 버리지 않고 결측으로 보존합니다(C2 생존자편향 방지)")

    # ★★ 두 번 이상 as-of 결합할 때의 두 가지 함정 — 둘 다 조용히 값을 날린다 ★★
    #  ① asof_join 은 언제나 'knowledge_date' 를 결과에 붙인다. 두 번째 호출에서 이름이
    #     충돌해 오른쪽 값이 'knowledge_date_r' 로 들어가고, 하류는 첫 소스의 날짜를
    #     두 번째 소스의 날짜인 줄 알고 읽는다.
    #  ② 재무(tidy)와 직원현황은 'bsns_year' 를 둘 다 갖는다. 마찬가지로 _r 접미사가 붙는다.
    #  → 소스별로 가져올 컬럼을 **명시**하고, 날짜는 소스별 이름으로 즉시 개명한다.
    EMP_JOIN_COLS = ["corp_code", "knowledge_date", "bsns_year", "employees", "emp_prev",
                     "regular_ratio", "payroll_total", "avg_salary", "avg_prev", "dn", "d_pay",
                     "nl_emp", "nl_dn", "nl_marginal", "nl_premium", "nl_regular", "src_flag"]
    for name, tag, want in (("dart_financials", "fin", list(FUNDAMENTAL_COLS)),
                            ("emp_sensors", "emp", EMP_JOIN_COLS)):
        if not PIT.has(name):
            continue
        avail = set(PIT._t[name].columns)
        cols = [c for c in dict.fromkeys(["corp_code", "knowledge_date"] + want) if c in avail]
        before = P.shape[1]
        P = PIT.asof_join(P, name, by="corp_code", left_time="month", cols=cols)
        for src_col in ("knowledge_date", "knowledge_date_r"):
            if src_col in P.columns:
                P = P.rename(columns={src_col: f"kd_{tag}"})
                break
        if f"kd_{tag}" in P.columns:
            bad = int((P[f"kd_{tag}"].notna() & (P[f"kd_{tag}"] > P["month"])).sum())
            if bad:
                raise RuntimeError(f"[C1 위반] '{name}' 결합에서 미래 정보 {bad:,}행 유입. "
                                   f"merge_asof 방향(backward)을 확인하세요.")
        LOG.debug(f"PIT as-of 결합 '{name}' — 컬럼 {before}→{P.shape[1]} "
                  f"(요청 {len(cols)}개, 지식일 → kd_{tag})")
    # 두 번째 결합에서 접미사가 붙은 잔재가 남았으면 명시적으로 버린다(조용히 두면 오독한다)
    stray = [c for c in P.columns if c.endswith("_r") and c[:-2] in P.columns]
    if stray:
        LOG.debug(f"as-of 결합 잔재 컬럼 제거: {stray[:6]}")
        P = P.drop(columns=stray)

    for c in FUNDAMENTAL_COLS:
        if c not in P.columns:
            P[c] = np.nan
    for c in ("employees", "emp_prev", "regular_ratio", "payroll_total", "avg_salary", "dn",
              "nl_emp", "nl_dn", "nl_marginal", "nl_premium", "nl_regular", "bsns_year"):
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_financials"):
        LOG.warn("DART 재무가 없어 CORE-D 5개 TP 가 전부 결측입니다. 실행은 계속되지만 "
                 "증거층이 EMP-LITE 3개 TP 뿐입니다 — DART_API_KEY 를 넣으면 살아납니다.")
    if not PIT.has("emp_sensors"):
        LOG.warn("직원현황이 없어 EMP-LITE 3개 TP 가 전부 결측입니다. "
                 "이 전략의 차별점이 사라지므로 사실상 CORE-D 단독 실행이 됩니다.")
    return P


# ── CORE-D 센서 (스펙 §7) ───────────────────────────────────────────────────────────────────
def core_d_sensors(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """전부 벡터화. 종목 루프 없음. 부호는 '클수록 좋다'로 통일한다."""
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)

    # i_sales — 매출 TTM 의 전년동월 대비 로그변화
    P["i_sales"] = g("revenue_ttm").transform(lambda s: dlog(s, 12))

    # i_dio / i_dso / i_turn — 회전일수는 '줄어드는 것'이 좋으므로 부호를 뒤집는다
    P["i_dio"] = safe_div(col(P, "inventory"), col(P, "cogs_ttm")) * 365.0
    P["i_dso"] = safe_div(col(P, "receivable"), col(P, "revenue_ttm")) * 365.0
    P["turn_days"] = P["i_dio"] + P["i_dso"]
    P["i_turn"] = -g("turn_days").diff(12)

    # i_accr — Sloan 발생액. 순이익이 음수인 구간에서도 안전(분모가 평균총자산이므로)
    avg_assets = (col(P, "assets") + g("assets").shift(12)) / 2.0
    P["accruals"] = safe_div(col(P, "net_income_ttm") - col(P, "cfo_ttm"), avg_assets)
    P["i_accr"] = -g("accruals").diff(12)

    # i_capex — 유형자산취득 / 직전 3년 평균.  1.0 이면 평년 수준, 2.0 이면 두 배 투자.
    #   ★ 분모는 '직전' 3년이어야 한다. 현재를 포함하면 자기 자신으로 나누는 꼴이 되어
    #     대규모 투자를 한 해에 오히려 비율이 1 로 눌린다.
    #   창은 정확히 '직전 3년'이다: shift(12) 로 현재 12개월을 밀어낸 뒤 36개월 평균을 낸다.
    #   min_periods 를 36 으로 두면 4년치 이력이 쌓이는 2019년까지 i_capex 가 통째로 결측이 되어
    #   백테스트 앞 3년이 CORE-D 한 축을 잃는다 → 12 로 두어 짧은 이력에서도 산출한다.
    capex_abs = col(P, "capex_ttm").abs()
    P["_capex_abs"] = capex_abs
    base3 = (g("_capex_abs")
             .transform(lambda s: s.shift(12).rolling(36, min_periods=12).mean()))
    P["i_capex"] = safe_div(capex_abs, base3)

    # i_ic / i_roic — 투하자본과 그 수익률
    nwc = (col(P, "receivable").fillna(0) + col(P, "inventory").fillna(0)
           - col(P, "payable").fillna(0))
    P["IC"] = nwc + col(P, "ppe").fillna(0) + col(P, "intangible").fillna(0)
    P["i_ic"] = g("IC").transform(lambda s: dlog(s, 12))
    #   NOPAT: 실효세율이 관측되면 그걸 쓰고, 아니면 22% 가정. 셀 내 상대값이라 수준은 무해.
    eff = safe_div(col(P, "tax_expense_ttm"), col(P, "pretax_income_ttm"))
    eff = eff.where((eff >= 0) & (eff <= 0.6))
    P["nopat"] = col(P, "op_income_ttm") * (1.0 - eff.fillna(0.22))
    avg_ic = (P["IC"] + g("IC").shift(12)) / 2.0
    P["ROIC"] = safe_div(P["nopat"], avg_ic)
    P["i_roic"] = g("ROIC").diff(12)

    # p_payout / p_invest — 자본배분
    payout = col(P, "dividend_paid_ttm").abs().fillna(0) + col(P, "treasury_buy_ttm").abs().fillna(0)
    P["payout_ratio"] = safe_div(payout, col(P, "cfo_ttm"))
    P["p_payout"] = g("payout_ratio").diff(12)
    invest = col(P, "capex_ttm").abs().fillna(0) + col(P, "rnd_ttm").abs().fillna(0)
    P["invest_ratio"] = safe_div(invest, col(P, "revenue_ttm"))
    P["p_invest"] = g("invest_ratio").diff(12)

    # p_cancel — 자사주 취득공시 대비 12M 내 실제 소각 실행률 (한국 특수성: 취득≠소각)
    P = _attach_treasury(P, ctx)

    # 실효세율 (V8 입력). 세전이익 ≤ 0 이면 판정 유보 → NaN (V8=1 로 떨어진다)
    P["eff_tax"] = safe_div(col(P, "tax_expense_ttm"),
                            col(P, "pretax_income_ttm").where(col(P, "pretax_income_ttm") > 0))
    P["eff_tax"] = P["eff_tax"].where((P["eff_tax"] >= -0.5) & (P["eff_tax"] <= 1.0))
    P["d_eff_tax"] = g("eff_tax").diff(12)

    P["equity_impaired"] = (col(P, "equity") <= 0)
    P = P.drop(columns=["_capex_abs"], errors="ignore")
    return P


def _attach_treasury(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """자사주 취득/소각 공시 건수를 12개월 롤링으로 실어 p_cancel·acq_size 를 만든다."""
    P["treasury_acq_n"] = 0.0
    P["treasury_canc_n"] = 0.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns and "event" in dis.columns:
        d = dis[dis["event"].isin(["treasury_acq", "treasury_canc"])].copy()
        if len(d) and "corp_code" in d.columns:
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            cnt = (d.groupby(["corp_code", "month", "event"]).size()
                     .unstack("event").reset_index())
            for c in ("treasury_acq", "treasury_canc"):
                if c not in cnt.columns:
                    cnt[c] = 0.0
            cnt["corp_code"] = cnt["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(cnt[["corp_code", "month", "treasury_acq", "treasury_canc"]],
                        on=["corp_code", "month"], how="left")
            P["treasury_acq"] = P["treasury_acq"].fillna(0.0)
            P["treasury_canc"] = P["treasury_canc"].fillna(0.0)
            P = P.sort_values(["code", "month"])
            P["treasury_acq_n"] = (P.groupby("code", observed=True)["treasury_acq"]
                                    .transform(lambda s: s.rolling(12, min_periods=1).sum()))
            P["treasury_canc_n"] = (P.groupby("code", observed=True)["treasury_canc"]
                                     .transform(lambda s: s.rolling(12, min_periods=1).sum()))
    # 취득이 0 인데 소각도 0 이면 '실행률'은 정의되지 않는다 → NaN. 1.0 도 0.0 도 거짓이다.
    P["p_cancel"] = safe_div(P["treasury_canc_n"],
                             P["treasury_acq_n"].where(P["treasury_acq_n"] > 0)).clip(0, 2)
    P["acq_size"] = safe_div(col(P, "treasury_buy_ttm").abs(), col(P, "assets"))
    return P


# ── EMP-LITE 파생 (연도 프레임 센서는 이미 붙어 있고, 여기선 패널 결합이 필요한 것만) ───────
def emp_lite_sensors(P: pd.DataFrame, emp_start: Optional[pd.Timestamp]) -> pd.DataFrame:
    """nl_vapp(1인당 부가가치 변화)만 패널에서 만든다. 나머지는 build_emp_sensors 산출물.

    부가가치 = 영업이익 + 인건비 + 감가상각.  분자는 별도(OFS) 기준으로 통일해야 하는데
    (empSttus 가 별도 기준에 가깝다) 코어의 재무 수집이 OFS 를 우선 시도하므로 정합한다.
    이 가정은 리포트에 명시한다 — 연결 비중이 큰 지주회사에서는 오차가 커진다.
    """
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)
    va = (col(P, "op_income_ttm").fillna(0) + col(P, "payroll_total").fillna(0)
          + col(P, "dep_ttm").abs().fillna(0))
    # 세 항목이 전부 결측이면 0 이 아니라 결측이다 (0 채움 금지)
    any_obs = (col(P, "op_income_ttm").notna() | col(P, "payroll_total").notna()
               | col(P, "dep_ttm").notna())
    P["value_added"] = va.where(any_obs)
    P["va_per_emp"] = safe_div(P["value_added"], col(P, "employees"))

    # ★★ 구성이 바뀐 채로 차분하면 '경제'가 아니라 '공시 완비도'를 잰다 ★★
    #   3항목을 각각 fillna(0) 하므로, 급여총액이 작년엔 결측이고 올해는 기재된 회사는
    #   부가가치가 실제로 늘지 않았는데도 nl_vapp 가 급등한다. 한국 중형주에서 인건비는
    #   부가가치의 지배적 항이고 payroll_total 은 설계상(단위 불일치 폐기·무기재) 상당수가
    #   결측이므로 이 인공 점프는 드물지 않다. TP_N2 는 그걸 '희석 없는 확장'으로 읽는다.
    #   → t 와 t-12 의 **관측 패턴이 동일할 때만** 차분한다. 수준(value_added)은 건드리지 않는다.
    comp = (col(P, "op_income_ttm").notna().astype(int) * 4
            + col(P, "payroll_total").notna().astype(int) * 2
            + col(P, "dep_ttm").notna().astype(int))
    P["_va_comp"] = comp
    same_comp = comp == g("_va_comp").shift(12)
    raw_vapp = g("va_per_emp").diff(12)
    P["nl_vapp"] = raw_vapp.where(same_comp.fillna(False))
    n_drop = int((raw_vapp.notna() & ~same_comp.fillna(False)).sum())
    if n_drop:
        LOG.info(f"nl_vapp — 부가가치 3항목(영업이익·인건비·감가상각)의 관측 구성이 전년과 "
                 f"달라진 {n_drop:,}행을 결측 처리했습니다. 그대로 두면 '공시가 새로 생긴 것'이 "
                 f"'생산성이 좋아진 것'으로 계산됩니다.")
    P = P.drop(columns=["_va_comp"], errors="ignore")

    if emp_start is not None:
        pre = P["month"] < as_ts(emp_start)
        n = int(pre.sum())
        for c in ("nl_emp", "nl_premium", "nl_vapp", "nl_regular", "nl_marginal"):
            if c in P.columns:
                P.loc[pre, c] = np.nan
        LOG.warn(f"§6 커버리지 판정에 따라 {as_ts(emp_start):%Y-%m} 이전 {n:,}행의 EMP 센서를 "
                 f"결측 처리했습니다. 이 구간은 CORE-D 5개 TP 만으로 평가됩니다.")
    return P


# ── U-MID 유니버스 (스펙 §4 C2/C13 의 build_universe_panel) ─────────────────────────────────
UMID_RANK_LO, UMID_RANK_HI = 251, 1400


def universe_band(name: str) -> Tuple[int, int, float]:
    """(랭크 하한, 랭크 상한, 거래대금 하한). 비교용 대역을 한 곳에서 정의한다."""
    if name == "SMALL":
        # 시총(대리: 거래대금) 하위 1,000 — U-MID 아래 구간. 유동성 하한은 그대로 두어야
        # '못 담는 종목으로 만든 성과'가 되지 않는다. 하한을 낮추면 체결 불가능한 종목이
        # 섞여 성과가 부풀려진다 — 비교의 의미가 사라진다.
        return SMALL_RANK_LO, SMALL_RANK_HI, MIN_ADV_KRW
    return UMID_RANK_LO, UMID_RANK_HI, MIN_ADV_KRW


def apply_umid(P: pd.DataFrame, uni: "Universe", band: str = "UMID") -> pd.DataFrame:
    """u_mid = 규모랭크 [251,1400] & adtv20 ≥ 3억 & 상장 250거래일 경과.

    ★ 규모 대리변수에 관한 정직한 고지: 스펙은 시가총액 랭크를 쓰지만, 이 파이프라인이
      확보하는 소스(pykrx 스냅샷·FDR·네이버)에는 과거 시점의 시가총액이 일관되게 없다.
      상장주식수 시계열을 PIT 로 복원하지 못한 채 현재 주식수를 쓰면 그 자체가 미래누수다.
      그래서 **20일 평균거래대금 랭크**를 규모 대리로 쓴다. 한국 시장에서 시총과 거래대금
      순위 상관은 높지만 동일하지 않다 — 이 치환은 결과 해석에 반드시 함께 읽어야 한다.
      (상장 250거래일 시즈닝은 Universe 가 이미 강제하므로 여기서 중복 적용하지 않는다)
    """
    lo, hi, adv_min = universe_band(band)
    P = P.copy()
    adv = col(P, "adv20")
    rank = adv.groupby(P["month"], observed=True).rank(ascending=False, method="first")
    P["size_rank"] = rank
    P["u_mid"] = (rank.between(lo, hi) & (adv >= adv_min)).fillna(False)
    for m, g in P.groupby("month", observed=True):
        uni.audit_row("U-MID대역", m, g.loc[g["u_mid"], "code"].tolist())
    keep = int(P["u_mid"].sum())
    LOG.info(f"{band} 유니버스: {keep:,}/{len(P):,}행 "
             f"(월평균 {keep/max(P['month'].nunique(),1):,.0f}종목) — "
             f"규모랭크 [{lo},{hi}] ∩ 거래대금 ≥{adv_min/1e8:.0f}억. "
             f"규모 대리는 20일 평균거래대금 랭크입니다(시총 PIT 복원 불가에 따른 치환).")
    if keep == 0:
        LOG.warn("U-MID 에 남는 행이 없습니다 — 가격 수집이 실패했거나 유동성 하한이 너무 높습니다. "
                 "u_mid 필터를 적용하지 않고 전 종목으로 진행합니다(조용히 빈 결과를 내지 않기 위함).")
        P["u_mid"] = True
    return P


def umid_by_year(P: pd.DataFrame) -> Dict[int, int]:
    """§6 커버리지 감사의 분모 — 연도별 U-MID 종목 수(연중 한 번이라도 U-MID 였던 종목)."""
    if P.empty or "u_mid" not in P.columns:
        return {}
    sub = P.loc[P["u_mid"], ["code", "month"]].copy()
    sub["year"] = sub["month"].dt.year
    return sub.groupby("year")["code"].nunique().to_dict()


def umid_corps_by_year(P: pd.DataFrame) -> Dict[int, set]:
    """연도별 U-MID 기업의 corp_code 집합 — §6 표의 **분자**를 분모와 같은 모집단으로 맞춘다.

    ★ 이걸 안 하면 분자는 전 상장사에서 세고 분모는 U-MID 에서 세게 되어,
      'U-MID 대상 1,102 / empSttus 성공 2,400' 처럼 비율이 100%를 넘는 표가 나온다.
      그 표를 근거로 시작연도를 판정하므로(§6), 커버리지를 과대평가한 채 창을 앞당기게 된다.
    """
    if P.empty or "u_mid" not in P.columns or "corp_code" not in P.columns:
        return {}
    sub = P.loc[P["u_mid"] & P["corp_code"].notna(), ["corp_code", "month"]].copy()
    sub["year"] = sub["month"].dt.year
    return {int(y): set(g["corp_code"].astype(str))
            for y, g in sub.groupby("year", observed=True)}


# ── U축: 반영도 (스펙 §8 — U = mean(z(d1), z(d3))) ─────────────────────────────────────────
def axis_U_v3(P: pd.DataFrame, flows: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Δlog P = Δlog E + Δlog M 분해.  d1 = -Δlog M  (120거래일 ≈ 6개월)

    목표 상태: ΔlogE > 0 AND ΔlogM <= 0
      → 시장이 이익 증가는 인정했으나 자본화를 거부 = '일회성으로 분류함' = 노리는 미스프라이싱

    ⚠ 한계: 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하다. E 는 후행 12M 순이익 대리를
      쓴다. 초기 구간일수록 오차가 크다. 숨기지 않고 리포트에 명시한다.
    """
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)
    P["E_proxy"] = col(P, "net_income_ttm")
    P["dlog_E"] = g("E_proxy").transform(lambda s: dlog(s, 6))
    P["dlog_P"] = g("close").transform(lambda s: dlog(s, 6))
    P["dlog_M"] = P["dlog_P"] - P["dlog_E"]
    P["d1"] = -P["dlog_M"]
    P["D_state"] = np.select(
        [(P["dlog_E"] > 0) & (P["dlog_M"] <= 0),
         (P["dlog_E"] > 0) & (P["dlog_M"] > 0),
         (P["dlog_E"] <= 0) & (P["dlog_M"] > 0)],
        ["목표상태(진입)", "리레이팅중(관망)", "기대선행(배제)"], default="개선없음(배제)")

    # d3: 120일 기관+외국인 누적순매수 (부호 반전 — 아직 안 들어온 쪽이 좋다)
    P["d3"] = np.nan
    if flows is not None and len(flows):
        # ★ 인덱스를 즉시 리셋한다. 아래 컬럼 대입들은 '라벨 정렬'로 동작하는데, flows 는
        #   불리언 필터·concat·부분 갱신을 거쳐 구멍 난 인덱스로 들어오는 것이 정상이다.
        #   라벨과 위치가 어긋난 채로 대입하면 다른 종목·다른 날짜의 값이 그 행에 실린다.
        f = flows.copy().reset_index(drop=True)
        f["date"] = as_ts_series(f["date"])
        inst = pd.to_numeric(f["inst_net"], errors="coerce") if "inst_net" in f.columns else 0.0
        fore = pd.to_numeric(f["foreign_net"], errors="coerce") if "foreign_net" in f.columns else 0.0
        f["net"] = pd.Series(inst).fillna(0) + pd.Series(fore).fillna(0)
        f = f.sort_values(["code", "date"])
        f["cum120"] = (f.groupby("code", observed=True)["net"]
                        .transform(lambda s: s.rolling(120, min_periods=40).sum()))
        # ★★ 미래누수 지점 ★★ 절대로 as_ts_series(<ndarray>) 를 컬럼에 대입하지 말 것.
        #   as_ts_series 는 ndarray 를 받으면 0..N-1 짜리 **새 인덱스**를 단 Series 를 돌려준다.
        #   그런데 `f["month"] = <Series>` 는 **라벨 정렬** 대입이다. 값은 위치 기준으로 계산돼
        #   있는데 배치는 라벨 기준으로 일어나므로, 바로 위 sort_values 가 순서를 바꾼 순간
        #   위치 p 의 행이 라벨 p 짜리 다른 행의 달을 받는다. 프레임이 종목-major 라
        #   2026년 A종목 행이 2016년 B종목의 달을 받는 일이 일상적으로 생기고,
        #   groupby(code, month).last() 가 그 미래 누적수급을 과거 달에 실어 보낸다
        #   → d3 → U → Signal. 전 종목 선정 랭킹이 최대 수년치 미래 정보로 오염된다.
        #   date 는 이미 Series 이므로 그대로 더하면 인덱스가 구조적으로 어긋날 수 없다.
        f["month"] = f["date"] + pd.offsets.MonthEnd(0)
        fm = f.groupby(["code", "month"], observed=True)["cum120"].last().reset_index()
        P = P.merge(fm, on=["code", "month"], how="left")
        adv = col(P, "adv20").replace(0, np.nan)
        P["d3"] = -safe_div(P["cum120"], adv * 250.0)

    z1 = cell_z(P, "d1")
    z3 = cell_z(P, "d3")
    Z = pd.DataFrame({"z_d1": z1, "z_d3": z3}, index=P.index)
    P["U_raw"] = nanmean_cols(Z, ["z_d1", "z_d3"])
    P["U_axes_used"] = Z.notna().sum(axis=1)
    P["U"] = cell_rank(P, P["U_raw"])
    LOG.info(f"U축 가용성 — d1:{int(z1.notna().sum()):,}행 · d3:{int(z3.notna().sum()):,}행 "
             f"(평균 가용 축 {P['U_axes_used'].mean():.2f}개). "
             f"U 는 스펙 §8 대로 d1·d3 만으로 구성합니다.")
    if int(z3.notna().sum()) == 0:
        LOG.warn("기관·외국인 수급(d3)이 전무합니다 — U 가 d1 단독이 됩니다. "
                 "pykrx 수급 수집 실패 여부를 위 수집 로그에서 확인하세요.")
    return P

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  셀 정규화 → TP(clip×clip) → 거부권 → Signal   (스펙 §8)                              ║
# ║                                                                                          ║
# ║  원칙 2 ── 트레이드오프 쌍은 clip(z,0) × clip(z,0). z×z 금지.                              ║
# ║    z×z 를 쓰면 '개선도 대가회피도 셀 하위'인 최악의 종목이 음×음=양 으로 최고점을 받는다.   ║
# ║    실측하면 이 사분면이 정의역의 약 4분의 1이다. 부호 버그 한 줄이 전략을 정확히 뒤집는다.  ║
# ║                                                                                          ║
# ║  원칙 3 ── 셀 정규화는 rank(pct=True) + transform. groupby.apply 금지(수십 배 느리다).     ║
# ║                                                                                          ║
# ║  ★ 본선과 강건성 비교팔은 **반드시 같은 함수(score_arm)** 를 통과한다.                      ║
# ║    비교팔이 다른 경로로 점수를 만들면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'  ║
# ║    를 재게 된다. 아무것도 빼지 않은 널-절제가 ΔSharpe +2.08 로 나온 전례가 있다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _clean_num(P: pd.DataFrame, name_or_series) -> pd.Series:
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(name_or_series, errors="coerce")
    # ±inf 를 먼저 NaN 으로. rank 는 inf 를 최대값으로 취급해 셀 순위를 통째로 왜곡한다.
    return v.replace([np.inf, -np.inf], np.nan).astype("float64")


def _rank_in(v: pd.Series, cells: pd.Series, min_n: int) -> Tuple[pd.Series, pd.Series]:
    """(셀 내 백분위, 셀 내 유효관측수). 표본 부족 셀은 호출자가 상위 셀로 폴백한다.

    ★ transform("size") 가 아니라 count 를 쓴다. size 는 NaN 행까지 세므로,
      30행짜리 셀에 그 센서 관측이 3개뿐이어도 '표본 충분'으로 통과해 3점짜리 순위가
      다른 셀의 30점짜리 순위와 나란히 곱해진다.
    """
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    return g.rank(pct=True, method="average"), g.transform("count")


def cell_rank(P: pd.DataFrame, name_or_series, min_n: int = None) -> pd.Series:
    """셀 내 백분위 [0,1] + 폴백 사다리 (month|ind_mid|size → month|ind_mid|ALL → month|ALL|ALL).

    폴백이 필요한 이유: 셀에 종목이 30개 있어도 '그 센서를 관측한' 종목은 5개뿐일 수 있다.
    셀 크기만 보고 판단하면 그 센서는 전부 NaN 이 되고, 아무 신호도 못 내면서
    로그에는 아무것도 남지 않는다 — 가장 나쁜 조용한 실패다.
    """
    min_n = CELL_MIN_N_V3 if min_n is None else min_n
    v = _clean_num(P, name_or_series)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    for lvl in ("cell", "cell_l2", "cell_l3"):
        if lvl not in P.columns:
            continue
        need = out.isna() & v.notna()
        if not need.any():
            break
        r, n = _rank_in(v, P[lvl], min_n)
        out = out.where(~need, r.where(n >= min_n))
    return out.astype("float32")


def cell_z(P: pd.DataFrame, name_or_series, min_n: int = None) -> pd.Series:
    """셀 내 z-score (winsorize ±2σ → z). U축 합성에만 쓴다 — TP 는 랭크 기반이다."""
    min_n = CELL_MIN_N_V3 if min_n is None else min_n
    v = _clean_num(P, name_or_series)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    for lvl in ("cell", "cell_l2", "cell_l3"):
        if lvl not in P.columns:
            continue
        need = out.isna() & v.notna()
        if not need.any():
            break
        grp = P[lvl].astype(object).fillna("__NA__").to_numpy()
        g = v.groupby(grp, observed=True, dropna=False)
        cnt, mu0, sd0 = g.transform("count"), g.transform("mean"), g.transform("std", ddof=0)
        w = v.clip(lower=mu0 - 2.0 * sd0, upper=mu0 + 2.0 * sd0)
        gw = w.groupby(grp, observed=True, dropna=False)
        mu, sd = gw.transform("mean"), gw.transform("std", ddof=0)
        z = (w - mu) / sd.where(sd > 0)
        z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)
        out = out.where(~need, z.where(cnt >= min_n))
    return out.astype("float32")


def tp(P: pd.DataFrame, a, b) -> pd.Series:
    """★ 스펙 §8 그대로:  za = rank(a)-0.5, zb = rank(b)-0.5,  TP = max(za,0) × max(zb,0)

    · 결과는 항상 [0, 0.25]. 음수가 나올 수 없으므로 '최악이 최고점'이 구조적으로 불가능하다.
    · 한쪽이 결측이면 결과도 결측. 0 으로 채우면 '대가를 치르지 않았다'는 거짓 주장이 된다.
    """
    za = cell_rank(P, a) - 0.5
    zb = cell_rank(P, b) - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    return pd.Series(out, index=P.index).where(za.notna() & zb.notna()).astype("float32")


# ── TP 정의표 (스펙 §8) ─────────────────────────────────────────────────────────────────────
TP_DEFS = [
    ("TP_I1", "i_capex",  "i_roic",    "확장하는데 수익성 유지"),
    ("TP_I2", "i_sales",  "i_turn",    "매출↑ × 회전유지"),
    ("TP_N1", "nl_emp",   "nl_premium", "★고부가 인력 확충 (이 전략의 핵심 신호)"),
    ("TP_N2", "nl_emp",   "nl_vapp",   "희석 없는 확장"),
    ("TP_N3", "nl_emp",   "nl_regular", "정규직으로 늘림 = 확신의 증거"),
    ("TP_I4", "i_sales",  "i_accr",    "매출↑ × 발생액유지"),
    ("TP_P1", "p_payout", "p_invest",  "환원↑ × 투자↑ = 잉여현금창출력"),
    ("TP_P2", "acq_size", "p_cancel",  "취득규모 × 소각실행 = 진정성"),
]


def build_tps(P: pd.DataFrame) -> pd.DataFrame:
    P = P.copy()
    rows = []
    for name, a, b, desc in TP_DEFS:
        P[name] = tp(P, a, b)
        cov = float(P[name].notna().mean()) if len(P) else 0.0
        pos = float((P[name] > 0).mean()) if len(P) else 0.0
        rows.append([name, f"{a} × {b}", _trunc(desc, 30), f"{cov*100:.1f}%", f"{pos*100:.1f}%"])
    LOG.table(rows, ["TP", "구성 (개선 × 대가회피)", "의미", "관측 커버리지", "양(>0) 비율"],
              ["l", "l", "l", "r", "r"], title="트레이드오프 쌍 (clip×clip · 음수 불가)")
    dead = [n for n, *_ in TP_DEFS if P[n].notna().sum() == 0]
    if dead:
        LOG.warn(f"관측이 한 건도 없는 TP: {dead} — 해당 원천 데이터가 비었습니다. "
                 f"E 는 나머지 TP 의 결측 제외 평균으로 계산되며, 이 사실은 리포트에 남습니다.")
    return P


# ── 거부권 V ∈ {0,1} — 연속화·가중치화·상쇄 금지 ────────────────────────────────────────────
VETO_DEFS_V3 = [
    ("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출 > 1.5", "제외"),
    ("V2", "순이익>0 인데 영업CF < 0.5×순이익 3분기 연속", "제외"),
    ("V3", "90일 내 대규모 희석성 조달(유증/CB/BW/감자)", "제외"),
    ("V5", "자본잠식 · 관리종목 · 감사의견 비적정", "제외"),
    ("V6", "유동성 하한 미달 또는 거래정지", "제외"),
    ("V8", "인원 급증(상위20%) + 유효세율 급락(<-3%p)", "제외"),
]
VETO_COLS_V3 = [v[0] for v in VETO_DEFS_V3]


def apply_vetoes_v3(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)
    n = len(P)

    # V1 — 밀어내기
    d_rev = g("revenue_ttm").diff(12)
    push = safe_div(g("inventory").diff(12).fillna(0) + g("receivable").diff(12).fillna(0), d_rev)
    P["v1_metric"] = push
    P["V1"] = np.where((d_rev > 0) & (push > 1.5), 0.0, 1.0)

    # V2 — 이익-현금 괴리 3분기 연속. 분기 프레임에서 만든 플래그를 as-of 로 실어 왔다.
    #      (월 패널에서 rolling(9) 로 세면 같은 분기값이 1~4개월 반복돼 발동이 밀린다)
    v2q = col(P, "v2_bad_3q")
    P["V2"] = np.where(v2q.fillna(0.0) >= 1.0, 0.0, 1.0)

    # V3 — 희석성 조달
    P["V3"] = 1.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns and "event" in dis.columns:
        d = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue", "capital_reduce"])].copy()
        if len(d):
            # ★★ 90일 창은 '패널 행 3개'가 아니라 '달력 3개월'이어야 한다 ★★
            #   이 패널은 U-MID 대역으로 이미 잘려 있어 종목별 행이 월 연속이 아니다.
            #   rolling(3) 을 쓰면 (a) 유동성이 출렁여 중간 달이 빠진 종목에서 창이 실제
            #   6~9개월로 늘어나 멀쩡한 종목을 계속 제외하고, (b) 공시가 난 달에 패널 행이
            #   없으면 그 이벤트는 아예 사라져 거부권이 발동조차 하지 않는다.
            #   → 이벤트 날짜에서 직접 창을 펼쳐 패널 행 유무와 무관하게 만든다.
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            ev = d[["corp_code", "month"]].dropna().drop_duplicates()
            ev["corp_code"] = ev["corp_code"].astype(str)
            win = pd.concat([ev.assign(month=ev["month"] + pd.offsets.MonthEnd(k))
                             for k in range(3)], ignore_index=True)   # 공시 당월 + 2개월
            win = win.drop_duplicates()
            win["dilution_win"] = 1.0
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(win, on=["corp_code", "month"], how="left")
            P["V3"] = np.where(P["dilution_win"].fillna(0.0) > 0, 0.0, 1.0)
            P = P.drop(columns=["dilution_win"], errors="ignore")

    # V5 — 자본잠식/관리종목
    P["V5"] = np.where(col(P, "equity").le(0).fillna(False), 0.0, 1.0)
    adm = ctx.get("administrative")
    if adm is not None and len(adm) and "code" in adm.columns:
        P["V5"] = np.where(P["code"].isin(set(adm["code"].dropna())), 0.0, P["V5"])

    # V6 — 유동성
    P["V6"] = np.where((col(P, "adv20").fillna(0) >= MIN_ADV_KRW) &
                       (col(P, "close").fillna(0) > 0), 1.0, 0.0)

    # V8 — 정책 유인 채용 의심 (인원 급증 + 유효세율 급락). 세전이익≤0 이면 eff_tax 가 NaN 이라
    #      자동으로 '판정 유보(V8=1)'가 된다 — 스펙 §7 그대로.
    P["V8"] = 1.0
    if "nl_emp" in P.columns and "d_eff_tax" in P.columns:
        thr = P.groupby("month", observed=True)["nl_emp"].transform(
            lambda s: s.quantile(V8_EMP_TOP_Q))
        hi = (col(P, "nl_emp") > thr).fillna(False)
        drop = (col(P, "d_eff_tax") < V8_TAX_DROP).fillna(False)
        P["V8"] = np.where(hi & drop, 0.0, 1.0)

    for c in VETO_COLS_V3:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(1.0)
        uniq = set(np.unique(P[c].dropna().to_numpy()))
        if not uniq <= {0.0, 1.0}:
            raise ValueError(f"[거부권 위반] {c} 가 이진이 아닙니다: {sorted(uniq)[:5]}. "
                             f"거부권은 절대 연속화하지 않습니다 — 어떤 센서 점수도 "
                             f"밀어내기 정황을 상쇄할 수 없어야 합니다.")
    P["VETO"] = P[VETO_COLS_V3].prod(axis=1)
    fired = {c: int((P[c] == 0).sum()) for c in VETO_COLS_V3}
    LOG.table([[c, d, act, f"{fired[c]:,}", f"{100*fired[c]/max(n,1):.2f}%"]
               for (c, d, act) in VETO_DEFS_V3],
              ["ID", "조건", "조치", "발동 행수", "비율"], ["c", "l", "c", "r", "r"],
              title="거부권 발동 현황 (V∈{0,1} · 곱 · 상쇄 불가)")
    LOG.info(f"거부권 전체 통과 {int((P['VETO']==1).sum()):,}/{n:,}행 "
             f"({100*(P['VETO']==1).mean():.1f}%)")
    return P


# ── 스코어 조립 — 본선·비교팔이 공유하는 유일한 경로 ────────────────────────────────────────
def score_arm(P: pd.DataFrame, tp_cols: Sequence[str], min_tp: int = None,
              use_u: bool = True, use_veto: bool = True) -> Dict[str, pd.Series]:
    """주어진 TP 집합 하나로 E → Signal → Signal_rank 를 만든다.

    Signal = rank_pct(E) × rank_pct(U) × ∏V        (스펙 §8)

    min_tp: 관측된 TP 가 이보다 적으면 제외(FLOOR). 스펙에 없는 우리 쪽 안전장치이므로
            R5 절제검사에서 이 경계값의 민감도를 반드시 함께 출력한다.
    """
    tp_cols = [c for c in tp_cols if c in P.columns]
    min_tp = MIN_TP_OBSERVED if min_tp is None else min_tp
    if not tp_cols:
        raise RuntimeError("증거층(TP) 컬럼이 하나도 없습니다. 위 수집 로그에서 "
                           "어떤 원천이 비었는지 확인하세요.")
    T = P[tp_cols].astype("float64")
    n_obs = T.notna().sum(axis=1)
    E_raw = T.mean(axis=1, skipna=True)                       # 결측 제외 동일가중 (C7)
    E = cell_rank(P, E_raw)
    FLOOR = (n_obs >= min(min_tp, len(tp_cols))).astype(float)
    U = (P["U"].fillna(0.0) if use_u and "U" in P.columns else pd.Series(1.0, index=P.index))
    V = (P["VETO"].fillna(0.0) if use_veto and "VETO" in P.columns
         else pd.Series(1.0, index=P.index))
    Signal = E.fillna(0.0) * U * V * FLOOR
    rank = Signal.groupby(P["month"], observed=True).rank(pct=True, method="average")
    return {"E_raw": E_raw, "E": E, "FLOOR": FLOOR, "Signal": Signal,
            "Signal_rank": rank, "n_tp": n_obs}


def assemble_score_v3(P: pd.DataFrame, tp_cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
    tp_cols = list(tp_cols) if tp_cols else [c for c, *_ in TP_DEFS if c in P.columns]
    live = [c for c in tp_cols if P[c].notna().sum() > 0]
    if len(live) < len(tp_cols):
        LOG.warn(f"관측 0 인 TP {sorted(set(tp_cols)-set(live))} 를 증거층에서 제외합니다. "
                 f"제외하지 않으면 최소 TP 수 조건이 전 종목을 탈락시킵니다.")
    S = score_arm(P, live)
    for k, v in S.items():
        P[k] = v
    globals()["ACTIVE_TP_COLS"] = live

    ret = float(P["FLOOR"].mean()) if len(P) else 0.0
    LOG.table([[c, f"{float(P[c].notna().mean())*100:.1f}%",
                f"{float(P.loc[P[c].notna(), c].mean()):.4f}" if P[c].notna().any() else "-"]
               for c in live],
              ["증거층 TP", "관측 커버리지", "평균값"], ["l", "r", "r"],
              title=f"증거층 E 구성 — {len(live)}개 TP 동일가중 (결측 제외 평균)")
    LOG.info(f"최소 TP 조건(≥{MIN_TP_OBSERVED}개 관측) 통과 {int(P['FLOOR'].sum()):,}/{len(P):,}행 "
             f"({ret*100:.1f}%) · 관측 TP 중앙값 {float(P['n_tp'].median()):.0f}개")
    if ret < 0.03:
        LOG.warn(f"통과율 {ret*100:.1f}% 는 매우 낮습니다. MIN_TP_OBSERVED 를 낮추기 전에 "
                 f"위 TP 커버리지 표에서 '어떤 원천이 비었는지'를 먼저 확인하세요 — "
                 f"임계값을 낮추면 원인이 아니라 증상만 가려집니다.")
    PIPE.io("OUT", "MEM", "scored_panel", P)
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델                                                             ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 '다음 거래일 시가'. 당일 종가 체결 금지(미래누수).   ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(누락 = 생존자편향).         ║
# ║  · 롱온리 (공매도 불가) — 음의 신호는 청산 게이트로만 쓴다.                                 ║
# ║  · 청산 규칙이 진입 논리와 같은 언어를 쓴다: Δlog M 이 Δlog E 수준까지 확장 완료 시 청산.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5          # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10             # 제곱근 충격 계수

# 보유 중 패널에서 사라진 종목을 '폐지 진행'으로 볼 최대 대기 기간.
#   KRX 는 매매거래정지 → 개선기간 → 정리매매 → 상장폐지 경로가 흔히 3~24개월이다.
#   거래가 정지되면 그 달부터 패널에 행이 생기지 않으므로, 폐지일이 '다음 달 안'일 때만
#   -100% 를 물리면 이 경로가 통째로 0% 청산으로 빠져나간다(생존자편향).
DELIST_VANISH_HORIZON_M = 24


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격. 참여율이 높을수록 급격히 비싸진다 — 소형주 가중이 여기서 나온다."""
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(SLIPPAGE_K * math.sqrt(part))


def exit_gate(dm, de) -> bool:
    """청산 판단: '진입 시의 목표상태'를 벗어났는가.

    진입 조건(axis_D)은 ΔlogE > 0 AND 시장이 아직 자본화를 안 함(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다. 알파 소진(원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다. 논거 무효

    ★ 예전엔 `dm >= de and de > 0` 이었다. 앞 조건이 참이면 뒤 조건도 거의 항상 참이라
      보이지만, 실제로 걸러지는 건 'de <= 0' 인 전 구간 — 즉 논거가 깨진 종목을 청산하는
      경로가 통째로 닫혀 있었다. 그 종목들은 보유상한(24개월)까지 자리를 차지했다.
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 종목 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '데이터프레임에 먼저 나온 행'을 고른다. 패널은
      ["code","month"] 로 정렬되어 있으므로 그건 곧 '종목코드가 작은 순'이다. 동점이 드물면
      무해하지만, 실측상 월 보유종목의 상당수가 동점 구간에서 결정됐고 행 순서를 섞으면
      포트폴리오가 통째로 바뀌었다 — 즉 보유종목이 데이터가 아니라 정렬의 함수였다.
      그래서 ① 1차 키는 signal_col, ② 2차 키는 랭크 이전의 원 Signal(정보량이 더 많다),
      ③ 최후에만 code 로 깬다. 이러면 동점 처리가 결정적이면서 '왜 그 종목인가'가 설명된다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "code") if c in df.columns and c != signal_col]
    asc = [False] + [False if c == "Signal" else True for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중(§8.5).
    비중 상한은 코드 상수로 이미 못박혀 있다 — 드로다운 한가운데서 정하지 않는다."""
    s = sub["Signal_rank"].fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    lo, hi = float(np.min(s)), float(np.max(s))
    if spread < 1e-6 or (hi - lo) < 1e-12:
        w = np.full(len(s), 1.0 / len(s))
    else:
        # ★ 예전엔 raw = clip(s - median, 0, None) + 1e-9 였다. 그러면 **선정된 종목의 정확히
        #   절반**(중앙값 이하)이 raw=1e-9 로 깔려 비중이 사실상 0 이 된다 — 25종목을 골랐다고
        #   로그에 찍으면서 실제로는 12~13종목만 보유하는 셈이고, '평균종목수' 지표가 실효
        #   보유수의 2배 넘게 부풀려진다. 분산 효과도 그만큼 과대평가된다.
        #   선정집합 내부 순위로 바꾸면 모든 선정 종목이 양(+)의 비중을 갖고,
        #   집중도는 conc 하나로만 조절된다(문서화된 의도 그대로).
        r = pd.Series(s).rank(method="average").to_numpy(dtype=float)   # 1..n
        conc = min(2.0, 0.5 + spread * 8.0)          # 격차 클수록 집중
        w = (r / r.sum()) ** conc
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    # 종목별 상한 = min(정책 상한, 유동성 상한). 유동성 상한은 20일 평균거래대금의 X%.
    adv = sub["adv20"].fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                       POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))

    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다(합이 1보다 작아지면 전부 커진다).
    #   상한에 걸린 종목은 고정하고 나머지에만 잔여 비중을 재배분하는 water-filling 으로 강제한다.
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
    if w.sum() > 1.0 + 1e-9:                 # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    return sub.assign(weight=w)


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                 sec: pd.DataFrame, signal_col: str = "Signal_rank",
                 top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                 label: str = "TCD") -> dict:
    mkt = sec.set_index("code")["market"].astype(str).to_dict()
    delist = uni.delisting_map()
    # 폐지 '유형' — 흡수합병·스팩해산은 -100% 가 아니다. 없으면 전부 -100%(종전 동작).
    dkind = uni.delist_kind_map() if hasattr(uni, "delist_kind_map") else {}
    hold: Dict[str, dict] = {}
    rows, trades, holdings_log = [], [], []
    prev_w: Dict[str, float] = {}
    # 폐지 손실을 이미 반영한 종목 — 같은 종목에 -100% 를 두 번 물리지 않기 위한 장부
    delist_realized: set = set()
    vanished_delisted = vanished_other = vanished_transfer = 0
    # 종목별 '패널에 마지막으로 등장한 달'. 사라진 종목이 나중에 돌아오는지(유동성 회복 등)를
    # 판별해야 '거래정지→폐지'와 '일시적 유니버스 이탈'을 가를 수 있다.
    _pm = P[P["month"].isin(months)] if len(P) else P
    last_seen = (_pm.groupby("code", observed=True)["month"].max().to_dict()
                 if len(_pm) else {})

    for i, m in enumerate(months):
        sub = P[(P["month"] == m)].copy()
        if sub.empty:
            rows.append({"month": m, "ret": 0.0, "n": 0, "turnover": 0.0, "cost": 0.0})
            continue
        elig = sub[(sub["VETO"] == 1) & (sub["FLOOR"] == 1) & sub[signal_col].notna() &
                   sub["exec_px"].notna()]
        # ★ 감쇠 감사는 '누적 교집합'으로 기록한다. 게이트별 독립 집계를 깔때기처럼 보여주면
        #   잔존율이 100%를 넘는 무의미한 숫자가 나온다(게이트가 서로 포함관계가 아니므로).
        g_liq = sub[sub["V6"] == 1]
        g_veto = g_liq[g_liq["VETO"] == 1]
        g_floor = g_veto[g_veto["FLOOR"] == 1]
        uni.audit_row("유동성필터", m, g_liq["code"].tolist())
        uni.audit_row("거부권통과", m, g_veto["code"].tolist())
        uni.audit_row("하한선통과", m, g_floor["code"].tolist())

        # 종목별 조회를 dict 로 미리 만든다. sub[sub.code==c] 를 종목마다 돌리면
        # 백테스트가 강건성 스위트에서 10여 회 재실행될 때 그 비용이 그대로 곱해진다.
        need_cols = [c for c in ("adv20", "fwd_ret", "VETO", "dlog_M", "dlog_E", signal_col)
                     if c in sub.columns]
        rec: Dict[str, dict] = {}
        for _c, *_v in sub[["code"] + need_cols].itertuples(index=False, name=None):
            rec[_c] = dict(zip(need_cols, _v))

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, k, signal_col)
        uni.audit_row("최종선정", m, pick["code"].tolist())

        # 청산 게이트: Δlog M 이 Δlog E 수준까지 확장 완료 / 보유상한 / 거부권
        keep = []
        vanished_loss = 0.0
        for c, h in list(hold.items()):
            r0 = rec.get(c)
            if r0 is None:
                # ★★ 패널에서 사라진 보유 종목 (C2 생존자편향의 마지막 구멍) ★★
                #   예전엔 그냥 continue 였다. 그러면 '거래정지 → 몇 달 뒤 상장폐지' 경로가
                #   손실 0%로 조용히 청산된다. 거래가 끊긴 종목은 월 패널에 행이 생기지 않으므로
                #   아래 fwd_ret 기반 -100% 규칙이 **한 번도 발동하지 못한다.**
                #   실제로는 정리매매가 없으면 -100% 다. 사라진 이유를 갈라서 처리한다:
                #     · 폐지가 임박/진행 중  → -100% (이미 반영한 종목은 제외)
                #     · 그 외(유니버스 이탈) → 직전가로 청산, 그 달 수익 0% (로그로 드러냄)
                #   ★ 창을 '다음 달까지'로 잡으면 안 된다. 거래가 정지되면 그 달부터 패널에
                #     행이 없어지는데, 실제 폐지일은 3~24개월 뒤다. 그래서 '이 달 이후 패널에
                #     다시 나타나지 않는가(=영구 이탈)' + '폐지일이 그 안에 있는가'로 판정한다.
                dl = delist.get(c)
                w_prev = prev_w.get(c, 0.0)
                never_back = m > last_seen.get(c, m)
                terminal = (dl is not None and pd.notna(dl) and never_back
                            and dl <= m + pd.DateOffset(months=DELIST_VANISH_HORIZON_M))
                if w_prev > 0 and terminal and c not in delist_realized:
                    # ★ 폐지 유형에 따라 청산가가 다르다. 흡수합병·완전자회사화·스팩해산은
                    #   전액손실이 아니다(대가로 인수기업 주식 또는 예치금을 받는다).
                    #   그런 건을 -100% 로 계상하면 없는 손실을 매년 지어낸다.
                    #   모르는 사유('unknown')는 보수적으로 -100% 를 유지한다.
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        vanished_transfer += 1      # 직전가 청산 = 그 달 수익 0%
                    else:
                        vanished_loss += w_prev * -1.0
                        vanished_delisted += 1
                    delist_realized.add(c)
                elif w_prev > 0:
                    vanished_other += 1
                continue
            dm, de = r0.get("dlog_M"), r0.get("dlog_E")
            exited = False
            if r0.get("VETO", 1) == 0:
                exited = True                                    # 거부권 발동 시 즉시 강제청산
            elif h["months"] >= HOLD_MAX_MONTHS:
                exited = True
            elif exit_gate(dm, de):
                exited = True                        # 목표상태 이탈 (재분류 완료 또는 논거 무효)
            if not exited:
                keep.append(c)
        target = pd.concat([pick, sub[sub["code"].isin(keep) & ~sub["code"].isin(pick["code"])]],
                           ignore_index=True) if len(keep) else pick
        if len(target) > PORTFOLIO_MAX_NAMES:
            target = _top_n(target, PORTFOLIO_MAX_NAMES, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}
        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in set(w_new) | set(prev_w))

        cost = 0.0
        if apply_costs:
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                c_bps = COMMISSION_BPS / 1e4
                sl = slippage(notional, adv)
                tx = sell_tax(m, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (c_bps + sl + tx)

        # 다음 달 수익
        ret = 0.0
        for c, w in w_new.items():
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                # ★ 상장폐지: 정리매매 최종가가 있으면 그것을 쓴다. 없을 때만 유형을 본다.
                #   부실·사유불명 → -100%(C2 원칙7). 합병·스팩해산 → 직전가 청산(0%).
                if not np.isfinite(fr):
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        fr = 0.0
                        vanished_transfer += 1
                    else:
                        fr = -1.0
                delist_realized.add(c)      # 이 종목의 폐지 손익은 여기서 확정 — 재차감 금지
            if not np.isfinite(fr):
                fr = 0.0
            ret += w * fr
            _s = _r.get(signal_col)
            holdings_log.append({"month": m, "code": c, "weight": w, "ret": fr,
                                 "signal": float(_s) if _s is not None and pd.notna(_s) else np.nan})
        ret += vanished_loss                 # 패널에서 사라진 폐지 종목의 -100% 를 이달에 반영
        ret_net = ret - cost
        rows.append({"month": m, "ret": ret_net, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost})
        for c in list(hold):
            if c in w_new:
                hold[c]["months"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"months": 0})
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    H = pd.DataFrame(holdings_log)
    if vanished_delisted or vanished_other or vanished_transfer:
        LOG.info(f"[{label}] 보유 중 청산된 종목 — 부실·사유불명 폐지 {vanished_delisted}건은 "
                 f"-100%, 합병·완전자회사화·스팩해산 {vanished_transfer}건은 직전가 청산(0%), "
                 f"그 외 유니버스 이탈 {vanished_other}건도 직전가 청산. "
                 f"조용히 사라지게 두지 않습니다(C2).")
        if not dkind:
            LOG.warn(f"[{label}] 폐지 사유 정보가 없어 **모든** 폐지를 -100% 로 계상했습니다. "
                     f"실측상 폐지의 절반가량(흡수합병·스팩해산)은 전액손실이 아니므로 "
                     f"성과가 과소평가됩니다 — 종목마스터에 delist_reason 이 실렸는지 확인하세요.")
    return {"returns": R, "holdings": H, "label": label,
            "vanished_delisted": vanished_delisted, "vanished_other": vanished_other}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
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
    uw, mx, cur = 0, 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1), "평균종목수": float(R["n"].mean()),
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """★ 이 전략은 IR 이 아니라 우측 꼬리에 의존한다. 상위 종목 제외 시 성과가 사라지는지
    반드시 측정하고 리포트에 명시한다(§10.2)."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {}
    base = float(contrib.sum())
    for q, lab in ((0.05, "상위5%"), (0.10, "상위10%"), (0.01, "상위1%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후 총기여"] = base - float(contrib.iloc[:k].sum())
    out["총기여"] = base
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                # ★ 끝을 2개월 늘린다. 아래 shift(-1) 때문에 마지막 달이 NaN 이 되면
                #   비교표의 dropna 에서 그 달이 조용히 빠진다.
                d = fdr.DataReader(sym, months[0] - pd.offsets.MonthEnd(2),
                                   months[-1] + pd.offsets.MonthEnd(2))
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        # ★★ 위상 정렬 ★★ 전략 수익률은 '월 m 행 = 월 m+1 에 실현된 수익'(fwd_ret) 규약이다.
        #   지수를 pct_change() 그대로 두면 한 달 어긋난 채로 차분되어, 시장요인이 상쇄되기는
        #   커녕 두 배로 들어간다. 초과수익의 t통계량이 절반 수준으로 눌린다.
        s = d.groupby("month")["close"].last().pct_change().shift(-1)
        out[name] = s.reindex(months)
    return out

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트  R0 · R1 · R2-N⭐ · R3 · R5 · R7 · R8 · R10   (스펙 §11)                ║
# ║                                                                                          ║
# ║  ★ 모든 비교팔은 score_arm() 이라는 **하나의 경로**만 통과한다.                             ║
# ║    비교팔이 다른 계산을 타면 Δ가 '무엇을 뺐는가'가 아니라 '어떻게 계산했는가'를 잰다.        ║
# ║  ★ 결과를 유리하게 해석하지 않는다. C ≈ max(A,B) 면 "무기여"라고 그대로 쓴다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_V3: List[dict] = []


def _rec(rid: str, name: str, passed: Optional[bool], detail: str, numbers: str = ""):
    ROBUST_V3.append({"id": rid, "name": name, "passed": passed,
                      "detail": detail, "numbers": numbers})
    tag = "PASS" if passed else ("N/A" if passed is None else "FAIL")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.warn))(
        f"[{rid}] {name} — {tag} · {detail}")


def _stat(bt: dict, key: str) -> float:
    try:
        return float(perf_stats(bt["returns"]).get(key, np.nan))
    except Exception:
        return np.nan


def _ret_series(bt: dict, months: pd.DatetimeIndex) -> pd.Series:
    R = bt["returns"]
    return pd.Series(R["ret"].to_numpy(dtype=float),
                     index=pd.DatetimeIndex(R["month"])).reindex(months).fillna(0.0)


def _diff_t(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """두 수익률 시계열 차이의 HAC 평균·t통계량. 월별 쌍대비교라 표본상관을 자동 상쇄한다."""
    d = (a - b).dropna().to_numpy(dtype=float)
    return hac_tstat(d)


def _budget_ok(rid: str, t0: float) -> bool:
    lim = ROBUST_BUDGET_S.get(rid)
    return not (lim and (time.time() - t0) > lim)


ALPHA_FLOOR = 0.20      # 이 아래의 Sharpe 는 '알파가 있다'고 말하지 않는다


def _no_alpha_to_test(base: float) -> bool:
    """기준선에 애초에 알파가 없으면 '살아남았다/유지됐다'는 판정은 무의미하다.

    ★ 이걸 막지 않으면 R3·R7·R10 이 전부 조용히 PASS 를 찍는다. 기준 Sharpe 가 -0.05 인데
      직교화 후 0.04 가 나오면 `orth > 0` 이 참이라 '알파 잔존'이라고 출력되는 식이다.
      아무 알파도 없는 전략이 강건성 검사를 3개나 통과한 것처럼 보이는 것 —
      스펙 §11 이 금지하는 '유리한 해석'의 가장 전형적인 형태다.
      그래서 이 경우는 PASS 도 FAIL 도 아닌 **판정 유보(N/A)** 로 돌려보낸다.
    """
    return (not np.isfinite(base)) or base <= ALPHA_FLOOR


# ── R0 : 자체측정 벤치마크 (하드코딩 금지 — 이 문서가 직접 잰다) ────────────────────────────
def R0_benchmark(P: pd.DataFrame, bt: dict, months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """유니버스 동일가중 = 이 전략이 반드시 이겨야 하는 최소 기준선.

    ★ 지수(KOSPI/KOSDAQ)가 아니라 '우리가 실제로 고를 수 있었던 종목의 동일가중'이다.
      지수와 비교하면 유니버스 선택(중형주 편중)의 효과가 알파로 둔갑한다.
    """
    t0 = time.time()
    elig = P[(col(P, "V6") == 1) & col(P, "fwd_ret").notna()]
    if elig.empty:
        _rec("R0", "자체측정 벤치마크(유니버스 동일가중)", None, "유효 표본 없음")
        return {}
    ew = elig.groupby("month", observed=True)["fwd_ret"].mean().reindex(months).fillna(0.0)
    bench = {"유니버스 동일가중": ew}
    try:
        for k, v in benchmark_returns(months).items():
            if v is not None and v.notna().any():
                bench[k] = v.reindex(months)
    except Exception as e:                                       # noqa
        LOG.debug(f"지수 벤치마크 수집 실패({type(e).__name__}) — 자체측정만 사용합니다.")

    bR = pd.DataFrame({"month": months, "ret": ew.to_numpy(), "n": 0,
                       "turnover": 0.0, "cost": 0.0})
    bs = perf_stats(bR)
    ss = perf_stats(bt["returns"])
    cal_s, cal_b = ss.get("Calmar", np.nan), bs.get("Calmar", np.nan)
    ok = np.isfinite(cal_s) and np.isfinite(cal_b) and cal_s > cal_b
    _rec("R0", "자체측정 벤치마크(유니버스 동일가중) 대비", bool(ok),
         "Calmar 상회" if ok else "Calmar 미달 — 스펙 §11 기준상 폐기 대상",
         f"전략 Calmar {cal_s:.2f} / 벤치 {cal_b:.2f} · "
         f"CAGR {ss.get('CAGR', np.nan):.2%} vs {bs.get('CAGR', np.nan):.2%} · "
         f"MDD {ss.get('MDD', np.nan):.1%} vs {bs.get('MDD', np.nan):.1%}")
    runtime_mark("R0", time.time() - t0)
    return bench


# ── R1 : 누수 자가검정 (이중 대조군) ────────────────────────────────────────────────────────
def R1_leakage(P: pd.DataFrame, months: pd.DatetimeIndex, run_fn: Callable) -> None:
    """하네스가 '누수를 감지할 수 있는 상태인가'를 먼저 증명한다.

    두 개의 **고의 오염 대조군**을 넣는다:
      ① 미래수익 직접주입 — 신호를 fwd_ret 의 랭크로 바꾼다. 완벽한 예지력.
      ② 신호 6개월 앞당김 — 미래의 신호를 현재에 쓴다(스펙의 '-120일 앞당김').

    ★ 판정은 ①만으로 한다. 이유를 분명히 해 둔다:
      ①은 '하네스가 누수를 감지할 수 있는가'를 재는 **인과적으로 옳은** 검정이다.
      미래 수익을 신호에 그대로 넣었는데도 성과가 안 오르면 체결·정렬·결합 어딘가가
      끊어진 것이고, 그러면 본선 결과 전체가 무효다.
      ②는 성격이 다르다. 신호를 앞당겨 개선되려면 **신호에 실제 예측력이 있어야** 한다.
      알파가 0인 신호는 앞당겨도 0이므로, ②의 미개선은 하네스 결함이 아니라
      '신호에 지속성이 없다'는 별개의 사실이다. 둘을 한 판정에 묶으면 서로 다른 두
      사건을 구별할 수 없게 된다 — 그래서 ②는 참고 지표로 따로 보고한다.
    """
    t0 = time.time()
    base = _stat(run_fn(P, label="R1_base"), "Sharpe")

    A = P.copy()
    A["Signal_rank"] = (col(A, "fwd_ret").groupby(A["month"], observed=True)
                        .rank(pct=True, method="average"))
    A["FLOOR"] = 1.0
    s_inject = _stat(run_fn(A, label="R1_inject"), "Sharpe")

    B = P.sort_values(["code", "month"]).copy()
    B["Signal_rank"] = B.groupby("code", observed=True)["Signal_rank"].shift(-6)
    s_ahead = _stat(run_fn(B, label="R1_ahead"), "Sharpe")

    d1 = s_inject - base
    d2 = s_ahead - base
    ok = np.isfinite(d1) and d1 > 0.5
    note = ("하네스가 누수에 민감 — 본선 결과를 신뢰할 수 있음" if ok else
            "★ 미래수익을 주입해도 성과가 오르지 않음 — 하네스 결함입니다. "
            "전 결과를 무효로 다루고 체결·정렬·결합 경로를 먼저 고치세요")
    if ok:
        note += ("; 신호 앞당김도 개선(지속성 있음)" if np.isfinite(d2) and d2 > 0.1 else
                 "; 다만 신호 앞당김은 개선되지 않음 — 하네스가 아니라 "
                 "'신호의 예측 지속성이 약하다'는 별개의 신호로 읽으세요")
    _rec("R1", "누수 자가검정 (대조군 ①주입 판정 / ②앞당김 참고)", bool(ok), note,
         f"기준 Sharpe {base:.2f} · ①미래수익주입 {s_inject:.2f}(Δ{d1:+.2f}, 판정근거) · "
         f"②신호6M앞당김 {s_ahead:.2f}(Δ{d2:+.2f}, 참고)")
    runtime_mark("R1", time.time() - t0)


# ── R2-N : 한계임금 킬게이트 ⭐⭐ (이 문서의 존재 이유) ──────────────────────────────────────
R2N_VERDICT: Dict[str, Any] = {}


def R2N_kill_gate(P: pd.DataFrame, run_fn: Callable) -> None:
    """스펙 §11.1.

      A. clip(z(nl_emp),0)     단독          ← 나이브
      B. clip(z(nl_premium),0) 단독
      C. TP_N1 = clip × clip                 ← 트레이드오프
      D. 전체 E (8개 TP)   vs   CORE-D 단독 (5개 TP)

    ★ A·B·C 는 **동일한 행 집합**에서 비교한다. nl_emp 만 있고 nl_premium 이 없는 행을
      A 에만 허용하면 A 의 유니버스가 넓어져 비교가 성립하지 않는다.
      (실제로 이 통제를 빠뜨리면 나이브 팔이 표본 수 덕분에 이기는 일이 생긴다)
    """
    t0 = time.time()
    have_emp = ("nl_emp" in P.columns and "nl_premium" in P.columns
                and P["nl_emp"].notna().any() and P["nl_premium"].notna().any())
    if not have_emp:
        _rec("R2-N", "한계임금 킬게이트", None,
             "nl_emp 또는 nl_premium 관측이 없어 검정 불가 — "
             "K7/K8 실측표와 EMP 커버리지 감사를 확인하세요")
        R2N_VERDICT.update({"verdict": "검정불가", "reason": "EMP 관측 부재"})
        return

    # ── 공통 행 집합: 두 센서가 모두 관측된 행만 ───────────────────────────────────────────
    common = P["nl_emp"].notna() & P["nl_premium"].notna()
    n_common = int(common.sum())
    Q = P.copy()
    Q["ARM_A"] = np.maximum(cell_rank(Q, "nl_emp") - 0.5, 0.0)
    Q["ARM_B"] = np.maximum(cell_rank(Q, "nl_premium") - 0.5, 0.0)
    Q["ARM_C"] = Q["TP_N1"] if "TP_N1" in Q.columns else tp(Q, "nl_emp", "nl_premium")
    for c in ("ARM_A", "ARM_B", "ARM_C"):
        Q[c] = pd.to_numeric(Q[c], errors="coerce").where(common)

    arms = {}
    for lab, cols in (("A. nl_emp 단독(나이브)", ["ARM_A"]),
                      ("B. nl_premium 단독", ["ARM_B"]),
                      ("C. TP_N1 = clip×clip", ["ARM_C"])):
        S = score_arm(Q, cols, min_tp=1)
        Z = Q.copy()
        for k, v in S.items():
            Z[k] = v
        arms[lab] = run_fn(Z, label=f"R2N_{lab[:1]}")

    months = pd.DatetimeIndex(sorted(P["month"].unique()))
    rs = {k: _ret_series(v, months) for k, v in arms.items()}
    sh = {k: _stat(v, "Sharpe") for k, v in arms.items()}
    cg = {k: _stat(v, "CAGR") for k, v in arms.items()}
    ca = {k: _stat(v, "Calmar") for k, v in arms.items()}

    kA, kB, kC = list(arms)
    best_naive = kA if (sh.get(kA, -9) >= sh.get(kB, -9)) else kB
    mu, tstat = _diff_t(rs[kC], rs[best_naive])
    sig = np.isfinite(tstat) and tstat > 1.65

    # ── D: 전체 E vs CORE-D 단독 (같은 min_tp, 전 패널) ────────────────────────────────────
    live_all = [c for c in TP_ALL if c in P.columns and P[c].notna().any()]
    live_core = [c for c in TP_CORE_D if c in P.columns and P[c].notna().any()]
    dD = dC = None
    if live_core:
        for lab, cols in (("D. 전체 E (8TP)", live_all), ("CORE-D 단독 (5TP)", live_core)):
            S = score_arm(P, cols)
            Z = P.copy()
            for k, v in S.items():
                Z[k] = v
            arms[lab] = run_fn(Z, label=f"R2N_{lab[:1]}")
            rs[lab] = _ret_series(arms[lab], months)
            sh[lab] = _stat(arms[lab], "Sharpe")
            cg[lab] = _stat(arms[lab], "CAGR")
            ca[lab] = _stat(arms[lab], "Calmar")
        dD, dC = "D. 전체 E (8TP)", "CORE-D 단독 (5TP)"

    LOG.table([[k, f"{cg.get(k, np.nan):.2%}", f"{sh.get(k, np.nan):.2f}",
                f"{ca.get(k, np.nan):.2f}", f"{_stat(arms[k],'MDD'):.1%}",
                f"{_stat(arms[k],'평균종목수'):.0f}"] for k in arms],
              ["비교팔", "CAGR", "Sharpe", "Calmar", "MDD", "평균종목"],
              ["l", "r", "r", "r", "r", "r"],
              title=f"R2-N 한계임금 킬게이트 (A·B·C 는 공통 {n_common:,}행에서 비교)")

    # ── 판정 (유리하게 해석하지 않는다) ───────────────────────────────────────────────────
    if sig:
        verdict = "PASS"
        msg = ("한계임금 트레이드오프 신호가 나이브 지표를 유의하게 이겼습니다. "
               "→ 국민연금 월 해상도 데이터로 정밀화할 가치가 있다는 근거를 확보했습니다.")
    else:
        verdict = "무기여"
        msg = ("C ≈ max(A,B) — 트레이드오프 논리가 기여하지 않습니다. 연 1회 해상도의 한계로 "
               "보입니다. → NPS 정밀화 투자의 근거가 이 실험에서는 확보되지 않았습니다.")
    emp_contrib = None
    if dD and np.isfinite(sh.get(dD, np.nan)) and np.isfinite(sh.get(dC, np.nan)):
        emp_contrib = sh[dD] - sh[dC]
        if emp_contrib <= 0:
            msg += (f" 또한 전체 E(8TP)가 CORE-D 단독(5TP)을 넘지 못했습니다"
                    f"(ΔSharpe {emp_contrib:+.2f}) → EMP 신호 전체가 무기여이므로 "
                    f"TP_N1~N3 를 제외한 CORE-D 6TP 축소안을 병행 제시합니다.")

    _rec("R2-N", "한계임금 킬게이트 ⭐⭐", bool(sig), msg,
         f"C-{best_naive[:1]} 월평균차 {mu:+.4%} · HAC t={tstat:.2f} "
         f"(유의 기준 t>1.65) · 공통표본 {n_common:,}행" +
         (f" · D-CORE ΔSharpe {emp_contrib:+.2f}" if emp_contrib is not None else ""))

    R2N_VERDICT.update({
        "verdict": verdict, "t_stat": float(tstat) if np.isfinite(tstat) else None,
        "mean_diff": float(mu) if np.isfinite(mu) else None,
        "best_naive": best_naive, "n_common": n_common,
        "sharpe": {k: (float(v) if np.isfinite(v) else None) for k, v in sh.items()},
        "cagr": {k: (float(v) if np.isfinite(v) else None) for k, v in cg.items()},
        "emp_contribution_sharpe": (float(emp_contrib) if emp_contrib is not None else None),
        "message": msg})
    runtime_mark("R2N", time.time() - t0)

    if (not sig) and STOP_ON_KILL_CRITERIA:
        LOG.warn("§12-4 킬 기준: R2-N 무기여. 중단하지 않고 끝까지 돌려 축소안까지 보여주지만, "
                 "이 결과를 '거의 유의함' 따위로 포장하지 않습니다.")


def r2n_verdict_md() -> str:
    v = R2N_VERDICT
    if not v:
        return "# R2-N 판정\n\n검정이 실행되지 않았습니다.\n"
    # ★ f-string 안에 같은 따옴표를 다시 쓰지 않는다(3.12 미만에서 SyntaxError).
    #   서식은 전부 밖에서 문자열로 만들어 두고, f-string 은 그 변수만 끼워 넣는다.
    md = v.get("mean_diff")
    ts = v.get("t_stat")
    s_md = "-" if md is None else format(md, "+.4%")
    s_ts = "-" if ts is None else format(ts, ".2f")
    L = ["# R2-N 판정 — 한계임금 킬게이트 (TCD v3 · 전략3)", "",
         f"**판정: {v.get('verdict')}**", "", v.get("message", ""), "",
         "## 실측", "", "| 비교팔 | CAGR | Sharpe |", "|---|---|---|"]
    for k, s in (v.get("sharpe") or {}).items():
        c = (v.get("cagr") or {}).get(k)
        s_c = "-" if c is None else format(c, ".2%")
        s_s = "-" if s is None else format(s, ".2f")
        L.append(f"| {k} | {s_c} | {s_s} |")
    L += ["", f"- 공통 표본: {v.get('n_common', 0):,}행",
          f"- 최강 나이브: {v.get('best_naive')}",
          f"- C − 나이브 월평균차: {s_md}",
          f"- HAC t통계량: {s_ts} (유의 기준 1.65)",
          "", "## 해석 규약", "",
          "판정을 유리하게 재해석하지 않는다. `C ≈ max(A,B)` 이면 트레이드오프 논리가",
          "이 해상도에서 무기여라는 뜻이며, 그것이 이 문서의 정직한 산출물이다.", ""]
    return "\n".join(L)


# ── R3 : 퀄리티 직교화 ──────────────────────────────────────────────────────────────────────
def R3_orthogonal(P: pd.DataFrame, run_fn: Callable) -> None:
    """E 를 규모·수익성·모멘텀·발생액에 회귀시키고 잔차로 다시 돌린다.

    '트레이드오프'라는 게 사실 그냥 퀄리티 팩터의 다른 이름이라면, 직교화 후 알파가 사라진다.
    """
    t0 = time.time()
    Q = P.sort_values(["code", "month"]).copy()
    Q["f_size"] = np.log(col(Q, "assets").where(col(Q, "assets") > 0))
    Q["f_prof"] = safe_div(col(Q, "net_income_ttm"), col(Q, "assets"))
    Q["f_mom"] = gby(Q, "close").transform(lambda s: dlog(s, 12))
    Q["f_accr"] = col(Q, "accruals")
    facs = ["f_size", "f_prof", "f_mom", "f_accr"]
    y = col(Q, "E_raw")
    if y.notna().sum() < 100:
        _rec("R3", "퀄리티 직교화", None, "E_raw 표본 부족")
        return

    resid = pd.Series(np.nan, index=Q.index, dtype="float64")
    for m, idx in Q.groupby("month", observed=True).indices.items():
        idx = np.asarray(idx)
        yy = y.to_numpy()[idx]
        XX = np.column_stack([np.ones(len(idx))] + [Q[f].to_numpy()[idx] for f in facs])
        ok = np.isfinite(yy) & np.isfinite(XX).all(axis=1)
        if ok.sum() < 20:
            continue
        try:
            beta, *_ = np.linalg.lstsq(XX[ok], yy[ok], rcond=None)
        except np.linalg.LinAlgError:
            continue
        r = np.full(len(idx), np.nan)
        r[ok] = yy[ok] - XX[ok] @ beta
        resid[idx] = r

    Z = Q.copy()
    Z["E"] = cell_rank(Z, resid)
    Z["Signal"] = Z["E"].fillna(0) * Z["U"].fillna(0) * Z["VETO"].fillna(0) * Z["FLOOR"].fillna(0)
    Z["Signal_rank"] = Z["Signal"].groupby(Z["month"], observed=True).rank(pct=True, method="average")
    base = _stat(run_fn(P, label="R3_base"), "Sharpe")
    orth = _stat(run_fn(Z, label="R3_orth"), "Sharpe")
    nums = (f"원본 Sharpe {base:.2f} → 잔차 {orth:.2f} · "
            f"통제변수 규모·수익성·모멘텀·발생액")
    if _no_alpha_to_test(base):
        _rec("R3", "퀄리티 직교화", None,
             f"원본 구간에 직교화로 검정할 알파가 없습니다(Sharpe {base:.2f} ≤ {ALPHA_FLOOR}). "
             f"'잔존'이라고 쓰지 않습니다 — 남을 것이 없었습니다.", nums)
        runtime_mark("R3", time.time() - t0)
        return
    keep = orth / base
    ok = np.isfinite(orth) and orth > 0 and keep >= 0.5
    _rec("R3", "퀄리티 직교화", bool(ok),
         "직교화 후에도 알파 잔존" if ok else
         "직교화하면 알파가 사라짐 — 트레이드오프가 아니라 퀄리티 팩터의 재포장일 수 있음",
         nums + f" · 잔존율 {keep:.0%}")
    runtime_mark("R3", time.time() - t0)


# ── R5 : 절제 (TP별 · 경계 · 분모임계) ─────────────────────────────────────────────────────
def R5_ablation(P: pd.DataFrame, run_fn: Callable) -> None:
    t0 = time.time()
    live = [c for c in TP_ALL if c in P.columns and P[c].notna().any()]
    base_bt = run_fn(P, label="R5_base")
    base = _stat(base_bt, "Sharpe")
    rows = [["(기준) 전체", f"{base:.2f}", "0.00", f"{len(live)}개 TP"]]

    # ① TP 하나씩 제거
    for c in live:
        cols = [x for x in live if x != c]
        if not cols:
            continue
        S = score_arm(P, cols)
        Z = P.copy()
        for k, v in S.items():
            Z[k] = v
        s = _stat(run_fn(Z, label=f"R5_-{c}"), "Sharpe")
        rows.append([f"− {c}", f"{s:.2f}", f"{s-base:+.2f}", "TP 제거"])
        if not _budget_ok("R5", t0):
            rows.append(["(예산 초과로 이후 절제 생략)", "-", "-", ""])
            break

    # ② 경계: 최소 TP 관측 수
    if _budget_ok("R5", t0):
        for k in (2, 4):
            S = score_arm(P, live, min_tp=k)
            Z = P.copy()
            for kk, v in S.items():
                Z[kk] = v
            s = _stat(run_fn(Z, label=f"R5_mintp{k}"), "Sharpe")
            rows.append([f"MIN_TP_OBSERVED={k}", f"{s:.2f}", f"{s-base:+.2f}",
                         f"기본값 {MIN_TP_OBSERVED}"])

    # ③ C15 분모 임계값 — 한계임금을 실제로 재계산해서 본다
    if _budget_ok("R5", t0) and {"dn", "emp_prev", "d_pay", "avg_prev"} <= set(P.columns):
        for thr in (0.02, 0.05):
            Z = P.copy()
            gate = col(Z, "dn").abs() >= np.maximum(C15_MIN_ABS_DN, col(Z, "emp_prev") * thr)
            rel = safe_div(col(Z, "dn"), col(Z, "emp_prev"))
            gate &= (rel <= C15_MNA_UP) & (rel >= C15_MNA_DN)
            mw = safe_div(col(Z, "d_pay"), col(Z, "dn")).where(gate.fillna(False))
            prem = safe_div(mw, col(Z, "avg_prev").where(col(Z, "avg_prev") > 0))
            Z["nl_premium"] = prem.where(prem.between(C15_PREMIUM_LO, C15_PREMIUM_HI))
            Z["TP_N1"] = tp(Z, "nl_emp", "nl_premium")
            S = score_arm(Z, live)
            for kk, v in S.items():
                Z[kk] = v
            s = _stat(run_fn(Z, label=f"R5_c15_{thr}"), "Sharpe")
            rows.append([f"C15 분모임계 {thr:.0%}", f"{s:.2f}", f"{s-base:+.2f}",
                         f"기본값 {C15_MIN_REL_DN:.0%}"])

    LOG.table(rows, ["절제 조건", "Sharpe", "Δ", "비고"], ["l", "r", "r", "l"],
              title="R5 절제 검사 (TP별 · 경계 · 분모임계)")
    deltas = [float(r[2]) for r in rows[1:] if r[2] not in ("-",)]
    spread = (max(deltas) - min(deltas)) if deltas else np.nan
    ok = np.isfinite(spread) and spread < 1.5
    _rec("R5", "절제 안정성", bool(ok),
         "단일 TP·단일 임계값에 성과가 종속되지 않음" if ok else
         "특정 절제에서 성과가 급변 — 결과가 한 요소에 종속되어 있습니다(재설계 검토)",
         f"ΔSharpe 폭 {spread:.2f} (기준 <1.5) · 절제 {len(rows)-1}종")
    runtime_mark("R5", time.time() - t0)


# ── R7 : 레짐 (밸류업 이전/이후) ────────────────────────────────────────────────────────────
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    t0 = time.time()
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    cut = as_ts("2024-02-26")
    pre, post = R[R["month"] < cut], R[R["month"] >= cut]
    rows = []
    for lab, sub in (("전체", R), ("밸류업 이전 (~2024-02)", pre), ("밸류업 이후 (2024-03~)", post)):
        if len(sub) < 6:
            rows.append([lab, f"{len(sub)}", "표본부족", "", "", ""])
            continue
        s = perf_stats(sub.reset_index(drop=True))
        rows.append([lab, f"{len(sub)}", f"{s.get('CAGR', np.nan):.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('MDD', np.nan):.1%}",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
    LOG.table(rows, ["레짐", "월수", "CAGR", "Sharpe", "MDD", "t(HAC)"],
              ["l", "r", "r", "r", "r", "r"],
              title="R7 레짐 분할 — TP_P1/P2 는 최근 2년만 현 레짐입니다")
    pre_s = perf_stats(pre.reset_index(drop=True)).get("Sharpe", np.nan) if len(pre) >= 6 else np.nan
    full_s = perf_stats(R.reset_index(drop=True)).get("Sharpe", np.nan)
    nums = (f"이전 Sharpe {pre_s:.2f} / 전체 {full_s:.2f} · "
            f"이전 {len(pre)}개월 / 이후 {len(post)}개월")
    if _no_alpha_to_test(full_s):
        _rec("R7", "레짐 (밸류업 이전 알파)", None,
             f"전체 구간 알파 자체가 없어(Sharpe {full_s:.2f} ≤ {ALPHA_FLOOR}) "
             f"레짐 귀속을 논할 단계가 아닙니다.", nums)
        runtime_mark("R7", time.time() - t0)
        return
    ok = np.isfinite(pre_s) and pre_s > ALPHA_FLOOR
    _rec("R7", "레짐 (밸류업 이전 알파)", bool(ok),
         "밸류업 이전 구간에서도 알파가 존재 — 구조적 알파로 볼 근거가 있음" if ok else
         "★ 밸류업 이전 알파가 사실상 0 — 이건 구조적 알파가 아니라 정책 베팅입니다. "
         "TP_P1/P2 는 10년 중 최근 2년만 현 레짐임을 결론에 명시하세요",
         nums)
    runtime_mark("R7", time.time() - t0)


# ── R8 : 하위기간 ───────────────────────────────────────────────────────────────────────────
def R8_subperiod(bt: dict) -> None:
    t0 = time.time()
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    R["year"] = R["month"].dt.year
    rows, pos = [], 0
    yrs = sorted(R["year"].unique())
    for y in yrs:
        sub = R[R["year"] == y]
        r = sub["ret"].fillna(0)
        tot = float((1 + r).prod() - 1)
        pos += 1 if tot > 0 else 0
        rows.append([str(y), f"{len(sub)}", f"{tot:+.2%}", f"{float(r.mean()):+.2%}",
                     f"{float((r>0).mean()):.0%}", f"{float(sub['n'].mean()):.0f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목"],
              ["c", "r", "r", "r", "r", "r"], title="R8 하위기간 (연도별)")
    ratio = pos / max(len(yrs), 1)
    ok = ratio >= 0.6
    _rec("R8", "하위기간 일관성", bool(ok),
         "대부분의 연도에서 양(+)" if ok else "특정 연도에 성과가 몰려 있음 — 일관성 부족",
         f"{pos}/{len(yrs)}개 연도 양수 ({ratio:.0%})")
    runtime_mark("R8", time.time() - t0)


# ── R10 : 정책반증 (고용장려금 캘린더 ±6M 제외) ─────────────────────────────────────────────
def R10_policy_falsify(P: pd.DataFrame, cal: pd.DataFrame, months: pd.DatetimeIndex,
                       run_fn: Callable) -> None:
    t0 = time.time()
    m = policy_mask(cal, months)
    clean = pd.DatetimeIndex(months[~m.to_numpy()])
    if len(clean) < 18:
        _rec("R10", "정책반증 (고용정책 ±6M 제외)", None,
             f"정책 제외 후 남은 표본이 {len(clean)}개월뿐이라 검정력이 없습니다. "
             f"제외 대상 정책이 10년을 거의 덮고 있다는 사실 자체를 결론에 명시하세요.")
        runtime_mark("R10", time.time() - t0)
        return
    base = _stat(run_fn(P, label="R10_base", months_override=months), "Sharpe")
    off = _stat(run_fn(P, label="R10_clean", months_override=clean), "Sharpe")
    nums = (f"전체 {len(months)}개월 Sharpe {base:.2f} → "
            f"정책제외 {len(clean)}개월 {off:.2f}")
    if _no_alpha_to_test(base):
        _rec("R10", "정책반증 (고용정책 ±6M 제외)", None,
             f"전체 구간에 반증할 알파가 없습니다(Sharpe {base:.2f} ≤ {ALPHA_FLOOR}). "
             f"'정책 구간을 빼도 유지됐다'고 쓰지 않습니다 — 유지될 것이 없었습니다.", nums)
        runtime_mark("R10", time.time() - t0)
        return
    keep = off / base
    ok = np.isfinite(off) and off > 0 and keep >= 0.5
    _rec("R10", "정책반증 (고용정책 ±6M 제외)", bool(ok),
         "정책 구간을 빼도 알파가 유지됨 — 보조금 유인 채용의 부산물이 아님" if ok else
         "★ 정책 구간을 빼면 알파가 사라짐 — 스펙 §12-5 상 TP_N1 폐기 대상입니다",
         nums + f" (잔존 {keep:.0%})")
    runtime_mark("R10", time.time() - t0)


def report_robustness_v3():
    rows = [[r["id"], _trunc(r["name"], 26),
             "PASS" if r["passed"] else ("N/A" if r["passed"] is None else "FAIL"),
             _trunc(r["numbers"] or "", 52), _trunc(r["detail"], 46)] for r in ROBUST_V3]
    LOG.table(rows, ["ID", "검사", "판정", "실측", "해석"],
              ["c", "l", "c", "l", "l"], title="강건성 검사 종합 (§11)", maxw=54)
    n_fail = sum(1 for r in ROBUST_V3 if r["passed"] is False)
    n_pass = sum(1 for r in ROBUST_V3 if r["passed"] is True)
    n_na = sum(1 for r in ROBUST_V3 if r["passed"] is None)
    LOG.info(f"강건성 종합 — 통과 {n_pass} · 실패 {n_fail} · 판정불가 {n_na}")
    kills = [r for r in ROBUST_V3 if r["passed"] is False and r["id"] in ("R0", "R1", "R2-N", "R10")]
    if kills:
        LOG.warn("★ 킬 기준에 해당하는 실패: " + ", ".join(r["id"] for r in kills) +
                 " — 스펙 §12 는 파라미터 조정으로 통과시키는 것을 금지합니다. "
                 "실패는 실패대로 보고하는 것이 이 문서의 산출물입니다.")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증 · 해석표 · 진단카드 · 원장 연결 지도                                        ║
# ║                                                                                          ║
# ║  "어디서 에러가 났고, 데이터 입출력이 어디서 일어났고, 애널리스트 보고서와 식별된            ║
# ║   애널리스트가 제대로 연결됐고, 다중소스 원장 연결이 확실한지"를 한눈에 보여주는 층.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance_v3(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    R = bt["returns"]
    s = perf_stats(R)
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다(수익률 시계열이 비었습니다).")
        return
    order = ["월수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "월평균", "t통계량(HAC)", "최장언더워터(월)", "누적수익", "평균종목수",
             "월평균회전율", "월평균비용"]
    pct = {"CAGR", "연변동성", "MDD", "승률", "월평균", "누적수익", "월평균회전율", "월평균비용"}
    rows = []
    for k in order:
        v = s.get(k)
        if v is None:
            continue
        rows.append([k, f"{v:.2%}" if k in pct and np.isfinite(v) else
                     (f"{v:,.2f}" if isinstance(v, float) else f"{v:,}")])
    LOG.table(rows, ["지표", "값"], ["l", "r"],
              title=f"성과 검증 {label or STRATEGY_ID} (비용: 수수료+세금+제곱근충격 반영)")

    # 벤치마크 비교 — ★ 하드코딩된 과거 수치를 인용하지 않는다. 전부 이 실행에서 재측정한다.
    if bench:
        brows = []
        r = pd.Series(R["ret"].to_numpy(dtype=float), index=pd.DatetimeIndex(R["month"]))
        for name, bs in bench.items():
            b = pd.Series(bs).reindex(r.index)
            both = pd.concat([r, b], axis=1).dropna()
            if len(both) < 6:
                continue
            bstat = perf_stats(pd.DataFrame({"month": both.index, "ret": both.iloc[:, 1].to_numpy(),
                                             "n": 0, "turnover": 0.0, "cost": 0.0}))
            ex = both.iloc[:, 0] - both.iloc[:, 1]
            mu, t = hac_tstat(ex.to_numpy())
            brows.append([name, f"{bstat.get('CAGR', np.nan):.2%}",
                          f"{bstat.get('MDD', np.nan):.1%}",
                          f"{bstat.get('Calmar', np.nan):.2f}",
                          f"{(s.get('CAGR', np.nan) - bstat.get('CAGR', np.nan)):+.2%}",
                          f"{mu*12:+.2%}", f"{t:.2f}"])
        if brows:
            LOG.table(brows, ["벤치마크", "벤치 CAGR", "벤치 MDD", "벤치 Calmar",
                              "CAGR 차", "연환산 초과", "t(HAC)"],
                      ["l", "r", "r", "r", "r", "r", "r"],
                      title="벤치마크 대비 (이 실행에서 직접 재측정 — 인용 없음)")

    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:.4f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측꼬리 기여도 — 상위 종목을 빼면 성과가 남는가")
        base, top5 = rt.get("총기여", 0.0), rt.get("상위5% 기여", 0.0)
        if base and abs(top5) > abs(base) * 0.8:
            LOG.warn(f"총기여의 {100*top5/base:.0f}%가 상위 5% 종목에서 나옵니다. "
                     f"이 전략은 우측 꼬리 의존적입니다 — 표본 밖에서 재현되지 않을 위험이 "
                     f"IR 이 시사하는 것보다 훨씬 큽니다. 숨기지 않고 명시합니다.")


INTERP_D_STATE_V3 = [
    ("목표상태(진입)", "이익은 늘었는데 시장이 자본화를 거부 — 노리는 미스프라이싱"),
    ("리레이팅중(관망)", "이익도 늘고 멀티플도 확장 중 — 이미 반영이 진행됨"),
    ("기대선행(배제)", "이익은 그대로인데 멀티플만 확장 — 기대만 앞선 상태"),
    ("개선없음(배제)", "이익도 멀티플도 개선 없음"),
]

INTERP_TP_V3 = [
    ("TP_I1", "확장하면서 수익성을 지킴 — 투하자본 효율이 계단 상승", "설비만 늘고 ROIC 하락"),
    ("TP_I2", "매출이 느는데 운전자본 회전이 안 나빠짐 — 밀어내기가 아님", "매출↑ + 재고/채권 급증"),
    ("TP_N1", "★비싼 사람을 뽑으며 인원 확충 — 진짜 역량 확충", "저임금 대량채용(보조금 유인 의심)"),
    ("TP_N2", "인원이 느는데 1인당 부가가치가 안 희석됨", "인원만 늘고 생산성 희석"),
    ("TP_N3", "정규직으로 늘림 — 되돌릴 수 없는 확신의 증거", "계약직 위주 확대"),
    ("TP_I4", "매출이 느는데 발생액이 안 늘어남 — 이익의 질 유지", "매출↑ + 발생액 급증"),
    ("TP_P1", "환원과 투자를 동시에 늘림 — 진짜 잉여현금 창출력", "성장 포기하고 환원만"),
    ("TP_P2", "자사주를 사서 실제로 소각까지 감 — 진정성", "취득만 하고 물량 재활용"),
]


def report_interpretation_v3(P: pd.DataFrame):
    if "D_state" in P.columns:
        cnt = P["D_state"].value_counts()
        tot = int(cnt.sum()) or 1
        LOG.table([[k, d, f"{int(cnt.get(k,0)):,}", f"{100*int(cnt.get(k,0))/tot:.1f}%"]
                   for k, d in INTERP_D_STATE_V3],
                  ["U축 상태", "의미", "행수", "비율"], ["l", "l", "r", "r"],
                  title="반영도(U) 상태 분포 — Δlog P = Δlog E + Δlog M 분해")

    rows = []
    for tid, good, bad in INTERP_TP_V3:
        if tid not in P.columns:
            continue
        v = P[tid]
        rows.append([tid, _trunc(good, 40), _trunc(bad, 30),
                     f"{float(v.notna().mean())*100:.1f}%",
                     f"{float((v > 0).mean())*100:.1f}%"])
    LOG.table(rows, ["TP", "높으면 (해석)", "낮으면/0 (해석)", "관측률", "양(>0)"],
              ["l", "l", "l", "r", "r"], title="트레이드오프 해석표", maxw=44)

    if "nl_premium" in P.columns and P["nl_premium"].notna().any():
        q = P["nl_premium"].dropna()
        below = float((q < 1.0).mean())
        LOG.table([["관측 수", f"{len(q):,}"],
                   ["중앙값", f"{q.median():.2f}"],
                   ["평균", f"{q.mean():.2f}"],
                   ["< 1.0 비율 (저임금 채용 의심)", f"{below:.1%}"],
                   ["> 1.0 비율 (역량 확충)", f"{1-below:.1%}"],
                   ["상위 10% 경계", f"{q.quantile(0.9):.2f}"]],
                  ["임금프리미엄", "값"], ["l", "r"],
                  title="임금프리미엄 분포 — 정책오염 필터가 산식에 내장되어 있다")


def diagnostic_card_v3(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    """최근 월 상위 종목이 '왜' 뽑혔는지 TP 단위로 분해해 보여준다."""
    if P.empty or "Signal_rank" not in P.columns:
        return
    m = P["month"].max()
    sub = P[(P["month"] == m) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    sub = sub.sort_values("Signal_rank", ascending=False).head(top_n)
    if sub.empty:
        LOG.info("최근 월에 선정 조건을 통과한 종목이 없어 진단 카드를 생략합니다.")
        return
    nm = sec.drop_duplicates("code").set_index("code")["name"].to_dict()
    live = [c for c, *_ in TP_DEFS if c in P.columns]
    LOG.banner(f"종목 진단 카드 — {as_ts(m):%Y-%m} 상위 {len(sub)}종목",
               "각 종목이 어떤 트레이드오프로 뽑혔는지 분해합니다")
    for r in sub.itertuples(index=False):
        d = r._asdict()
        vals = [(c, d.get(c)) for c in live]
        got = [(c, v) for c, v in vals if v is not None and pd.notna(v)]
        got.sort(key=lambda x: -float(x[1]))
        LOG.table([[c, f"{float(v):.4f}",
                    next((g for t, g, _b in INTERP_TP_V3 if t == c), "")[:38]] for c, v in got]
                  + [["— 없음(결측)", ", ".join(c for c, v in vals
                                                if v is None or pd.isna(v)) or "-", ""]],
                  ["TP", "값", "해석"], ["l", "r", "l"],
                  title=f"{nm.get(d.get('code'), '')}({d.get('code')}) · "
                        f"Signal_rank {float(d.get('Signal_rank', np.nan)):.3f} · "
                        f"E {float(d.get('E', np.nan)):.3f} · U {float(d.get('U', np.nan)):.3f} · "
                        f"{d.get('D_state', '')}", maxw=40)
        emp_bits = []
        for k, lab, fmt in (("employees", "직원수", ",.0f"), ("nl_emp", "Δlog인원", "+.3f"),
                            ("nl_premium", "임금프리미엄", ".2f"),
                            ("nl_regular", "Δ정규직비중", "+.3f"),
                            ("i_capex", "CapEx/3년평균", ".2f"),
                            ("eff_tax", "실효세율", ".1%")):
            v = d.get(k)
            if v is not None and pd.notna(v):
                emp_bits.append(f"{lab} {format(float(v), fmt)}")
        if emp_bits:
            LOG.info("   " + " · ".join(emp_bits))


def report_ledger_v3(ctx: dict):
    """다중소스 원장 연결 감사 — '무엇과 무엇이 어떤 키로 연결되었는가'를 표로 못박는다."""
    sec = ctx.get("sec", pd.DataFrame())
    rep = ctx.get("reports", pd.DataFrame())
    A = ctx.get("analysts", pd.DataFrame())
    L = ctx.get("links", pd.DataFrame())
    emp = ctx.get("emp_raw", pd.DataFrame())
    fin = ctx.get("fin", pd.DataFrame())

    def _n(df, c=None):
        if df is None or len(df) == 0:
            return 0
        return int(df[c].notna().sum()) if c and c in df.columns else int(len(df))

    def _nuniq(df, c):
        """컬럼이 없거나 비어도 감사표가 죽지 않게 한다 — 감사표는 실패했을 때 가장 필요하다."""
        if df is None or len(df) == 0 or c not in df.columns:
            return "0사"
        return f"{df[c].nunique():,}사"

    rows = [
        ["종목마스터 ← FDR·KIND·pykrx·폐지목록", "code", f"{_n(sec):,}",
         f"corp_code 연결 {_n(sec,'corp_code'):,} ({100*_n(sec,'corp_code')/max(_n(sec),1):.0f}%)",
         "DART 재무·직원현황의 유일한 조인키"],
        ["DART 재무 ← corp_code", "corp_code",
         f"{_n(fin):,}", _nuniq(fin, "corp_code"),
         "knowledge_date = 접수일자(rcept_no 앞 8자리)"],
        ["DART 직원현황 ← corp_code", "corp_code",
         f"{_n(emp):,}", _nuniq(emp, "corp_code"),
         "knowledge_date = 사업보고서 접수일"],
        ["리포트 원장 ← 한경컨센서스·네이버", "report_id", f"{_n(rep):,}",
         f"종목코드 연결 {_n(rep,'code'):,} ({100*_n(rep,'code')/max(_n(rep),1):.0f}%)",
         "제목 정규식 + 네이버 stock_item href"],
        ["애널리스트 원장 ← 리포트", "analyst_id", f"{_n(A):,}",
         f"보고서-애널 링크 {_n(L):,}건", "증권사 사명 정규화 후 (이름,증권사) 동일성"],
    ]
    LOG.table(rows, ["원장 / 소스", "조인키", "행수", "연결 실적", "비고"],
              ["l", "c", "r", "l", "l"], title="다중소스 원장 연결 감사", maxw=44)

    if _n(rep) and _n(A):
        try:
            audit_linkage(rep, A, L)
        except Exception as e:                                    # noqa
            LOG.warn(f"애널리스트 원장 상세 감사 실패({type(e).__name__}) — 요약만 출력했습니다.")
    elif RESEARCH_COLLECT:
        LOG.info("애널리스트 리포트가 수집되지 않았습니다. U축은 d1·d3 만으로 구성되며 "
                 "(스펙 §8 이 요구하는 구성이 바로 그것이므로) 전략 자체는 온전합니다. "
                 "원장은 공용 인덱스 재활용·감사 목적으로만 사용합니다.")


def report_dataflow_map_v3():
    LOG.banner("데이터 흐름 지도", "어느 소스가 어느 단계에서 무엇을 만드는지")
    _safe_print("""
  ┌───────────────────────── L0 준비 ─────────────────────────────────────────────────────┐
  │  환경감지(Colab/Jupyter) → 구글드라이브 마운트 → VAULT(공용 _shared / 전용 tcd_v3_*)   │
  │  계약검정 C1·C2·C13·C15 · 원칙1~7  →  합성 스모크  →  실경로 리허설                    │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │
  ┌───────────────────────── L1 수집 ─────────────────────────────────────────────────────┐
  │  FDR/KIND/pykrx/DART corpCode ─→ 종목마스터(code·corp_code·상장일·폐지일·업종)         │
  │  pykrx→FDR→네이버→yfinance(+KRX 마켓플레이스 세션) ─→ 일별 가격 ─→ 월 패널(exec_px)    │
  │  DART fnlttMultiAcnt(배치) + fnlttSinglAcntAll(단건) ─→ 재무 TTM (knowledge=접수일)    │
  │  DART empSttus(확장: sm·급여총액·1인평균·정규직) ───→ 연도 프레임 EMP 센서 + C15       │
  │  DART list.json 스윕 ───→ 자사주 취득/소각·유증·CB/BW  (V3·p_cancel)                   │
  │  한경컨센서스 + 네이버리서치 ─→ 리포트 원장 ─→ 애널리스트 원장(엔티티 해소)             │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │  merge_asof(knowledge_date ≤ month) 단일 패스
  ┌───────────────────────── L1 센서 ─────────────────────────────────────────────────────┐
  │  CORE-D : i_sales i_turn i_accr i_capex i_ic i_roic p_payout p_invest p_cancel        │
  │  EMP-LITE: nl_emp nl_dn nl_marginal nl_premium★ nl_vapp nl_regular   (C15 게이트)      │
  │  U축    : d1 = -ΔlogM(120거래일) · d3 = -기관외국인 120일 누적순매수                   │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │  셀 = month × ind_mid × size_bucket(3단계)
  ┌───────────────────────── L2 스코어 ───────────────────────────────────────────────────┐
  │  TP = max(rank-0.5, 0) × max(rank-0.5, 0)        ← 음수 불가 (부호 버그 구조적 차단)   │
  │  E = mean(8 TP) · U = mean(z(d1), z(d3))                                              │
  │  Signal = rank(E) × rank(U) × V1·V2·V3·V5·V6·V8                                       │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │
  ┌──────────── L3 백테스트 ────────────┐   ┌──────────── L5 강건성 ─────────────────────┐
  │ 월 1회 · 다음 거래일 시가 체결       │   │ R0 자체벤치 · R1 누수 · R2-N★ · R3 직교화  │
  │ 비용(수수료+세금+제곱근충격)         │   │ R5 절제 · R7 레짐 · R8 하위기간 · R10 정책 │
  │ 상폐 -100% · 24개월 상한 · 청산게이트│   └────────────────────────────────────────────┘
  └─────────────────────────────────────┘
""")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 — 주석이나 관례는 무효. 테스트로만 강제한다.                                ║
# ║  실행 전 자동 수행하고 실패하면 즉시 중단한다(fail-fast).                                   ║
# ║                                                                                          ║
# ║  검정 대상: 스펙 §0 의 7대 원칙 + C1(PIT) · C2(생존자편향) · C13(유니버스 PIT) · C15       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_V3: List[dict] = []


def _cc(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_V3.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return ok


def _src_of(*fns) -> str:
    """함수 소스 결합. 한 셀에 붙여넣어 실행하는 경우 소스 조회가 불가할 수 있다 → "" 반환."""
    import inspect
    out = []
    for f in fns:
        try:
            out.append(inspect.getsource(f))
        except Exception:
            return ""
    return "\n".join(out)


def run_contracts_v3(strict: bool = True) -> bool:
    CONTRACT_V3.clear()
    rng = np.random.default_rng(SEED)

    # ── C1 : PIT 게이트웨이 ───────────────────────────────────────────────────────────────
    def c1():
        d = pd.DataFrame({"corp_code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 필터 오류: {len(got)}행 (기대 2)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        # merge_asof 단일 패스 등가성 — 루프 조회와 결과가 같아야 한다
        panel = pd.DataFrame({"corp_code": ["A"] * 4 + ["B"] * 4,
                              "month": list(pd.date_range("2020-02-29", periods=4, freq="ME")) * 2})
        J = st.asof_join(panel, "t", by="corp_code", left_time="month")
        if "knowledge_date" in J.columns:
            bad = (J["knowledge_date"].notna() & (J["knowledge_date"] > J["month"])).sum()
            if bad:
                return False, f"asof_join 이 미래 정보를 붙였습니다: {bad}행"
        loop = [len(st.get("t", m, latest_by=["corp_code"])) for m in panel["month"].unique()]
        return True, (f"as_of 절단·등록거부·merge_asof 단일패스 등가 전부 통과 "
                      f"(루프 조회 {sum(loop)}행 대조)")

    _cc("C1", "PIT — merge_asof 단일 패스, 미래 정보 차단", c1)

    # ── C2 / C13 : 생존자편향 · 유니버스 PIT ──────────────────────────────────────────────
    def c2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": ["살아있음", "폐지됨", "나중상장"],
            "market": ["KOSPI"] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", "2022-01-01"]),
            "delisting_date": pd.to_datetime([None, "2020-06-30", None]),
            "corp_code": ["A", "B", "C"], "industry": ["X"] * 3})
        days = pd.date_range("2009-01-01", "2026-06-30", freq="B")
        px = pd.DataFrame({"code": "000001", "date": days})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2019 = set(uni.at("2019-12-31"))
        at2021 = set(uni.at("2021-12-31"))
        if "000002" not in at2019:
            return False, "폐지 예정 종목이 폐지 이전 시점 유니버스에서 빠졌습니다 (생존자편향)"
        if "000002" in at2021:
            return False, "폐지된 종목이 폐지 이후에도 남아 있습니다"
        if "000003" in at2019:
            return False, "★C13 위반 — 미래에 상장할 종목이 과거 유니버스에 있습니다"
        if "000003" not in at2021 and "000003" not in set(uni.at("2023-06-30")):
            return False, "상장 후 시즈닝이 끝난 종목이 끝내 유니버스에 들어오지 않습니다"
        dm = uni.delisting_map()
        if "000002" not in dm:
            return False, "delisting_map 이 폐지 종목을 반환하지 않습니다"
        return True, "폐지 전 포함 · 폐지 후 제외 · 미래 상장 배제 · 시즈닝 통과"

    _cc("C2/C13", "생존자편향 · 유니버스 PIT", c2)

    # ── C2b : 상장폐지 -100% 강제 ─────────────────────────────────────────────────────────
    def c2b():
        src = _src_of(run_backtest)
        if not src:
            return True, "소스 조회 불가 — 검사 생략 (한 셀 실행 환경)"
        if "-1.0" not in src or "delist" not in src:
            return False, "백테스트 엔진에 상장폐지 -100% 처리가 보이지 않습니다"
        return True, "정리매매가 없으면 -100% (누락 처리 금지) 가 엔진에 존재"

    _cc("C2b", "상장폐지 손실 반영 (원칙 7)", c2b)

    # ── 원칙 2 : clip(z,0) × clip(z,0),  z×z 금지 ─────────────────────────────────────────
    def p2():
        n = 400
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": pd.Timestamp("2020-06-30"),
            "a": rng.normal(size=n), "b": rng.normal(size=n)})
        P["cell"] = "C"
        P["cell_l2"] = "C"
        P["cell_l3"] = "C"
        v = tp(P, "a", "b")
        if v.min() < -1e-12:
            return False, f"TP 에 음수가 나왔습니다(min={v.min():.4f}) — clip 이 적용되지 않았습니다"
        # 최악의 사분면(둘 다 하위)이 0 이어야 한다. z×z 였다면 여기가 최고점이 된다.
        worst = (cell_rank(P, "a") < 0.2) & (cell_rank(P, "b") < 0.2)
        if worst.any() and float(v[worst].max()) > 1e-12:
            return False, "★부호 버그 — 개선·대가회피 모두 하위인 종목이 양의 TP 를 받았습니다"
        best = (cell_rank(P, "a") > 0.8) & (cell_rank(P, "b") > 0.8)
        if best.any() and float(v[best].min()) <= 0:
            return False, "둘 다 상위인 종목의 TP 가 0 입니다"
        # 한쪽 결측이면 결과도 결측 (0 채움 금지)
        P2 = P.copy()
        P2.loc[P2.index[:10], "b"] = np.nan
        if tp(P2, "a", "b").iloc[:10].notna().any():
            return False, "한쪽이 결측인데 TP 가 값을 가졌습니다 (0 채움 금지 위반)"
        src = _src_of(tp)
        if src and "maximum" not in src:
            return False, "tp() 소스에 clip(np.maximum) 이 보이지 않습니다"
        return True, f"음수 불가 · 최악사분면=0 · 결측 전파 (표본 {n})"

    _cc("원칙2", "TP = clip(z,0) × clip(z,0) — z×z 금지", p2)

    # ── C1b : 수급(d3) 경로의 행 정렬 무결성 ──────────────────────────────────────────────
    def c1b():
        """★ 실제로 터졌던 미래누수를 고정하는 회귀 테스트.

        `f["month"] = as_ts_series(<ndarray>)` 는 값은 위치로 계산하고 배치는 라벨로 하는
        대입이다. flows 가 구멍 난 인덱스로 들어오거나 sort_values 가 순서를 바꾸면
        다른 종목·다른 날짜의 달이 그 행에 실리고, 미래 수급이 과거 달로 흘러든다.
        d3 는 PIT.asof_join 을 타지 않으므로 C1 이 잡지 못한다 — 그래서 따로 검정한다.
        """
        # ★ 표본은 반드시 rolling(120, min_periods=40) 이 실제로 값을 내는 크기여야 한다.
        #   월 30행짜리로 만들면 cum120 이 전부 NaN 이라 아래 검사가 공회전하고,
        #   버그가 있어도 통과한다(검정 같아 보이지만 아무것도 재지 않는 테스트).
        days = pd.bdate_range("2020-01-01", periods=320)
        rows = []
        for c in ("000002", "000001"):                 # 정렬 전 순서를 일부러 역순으로
            for i, d in enumerate(days):
                # 순매수를 시간에 따라 증가시킨다 → 120일 누적도 시간 단조 증가해야 한다
                rows.append({"code": c, "date": d, "inst_net": float(i), "foreign_net": 0.0})
        fl = pd.DataFrame(rows)
        fl = fl[fl.index % 7 != 3]                     # 인덱스에 구멍 (필터/concat 의 정상 결과)
        months = pd.DatetimeIndex(sorted(set(days + pd.offsets.MonthEnd(0))))
        P = pd.DataFrame({"code": np.repeat(["000001", "000002"], len(months)),
                          "month": list(months) * 2, "close": 1000.0, "adv20": 1e9,
                          "net_income_ttm": 1e10})
        P["cell"] = P["cell_l2"] = P["cell_l3"] = "C"
        out = axis_U_v3(P, fl)
        if "cum120" not in out.columns:
            return False, "수급 결합이 일어나지 않았습니다 — d3 경로가 죽어 있습니다"
        obs = out["cum120"].notna().sum()
        if obs < 8:
            return False, (f"cum120 유효 관측이 {obs}건뿐입니다 — 표본이 롤링 창을 못 채웠거나 "
                           f"월 배치가 어긋나 대량 결측(NaT)이 발생했습니다")
        # 시간이 흐를수록 누적순매수가 커져야 한다. 미래 값이 과거 달에 실리면 단조성이 깨진다.
        bad = 0
        for c, g in out.dropna(subset=["cum120"]).groupby("code"):
            s = g.sort_values("month")["cum120"].to_numpy()
            bad += int((np.diff(s) < -1e-9).sum())
        if bad:
            return False, (f"★수급 누적값이 시간 역행하는 구간 {bad}건 — 행 정렬이 어긋나 "
                           f"미래 수급이 과거 달에 실렸습니다(d3→U→Signal 오염)")
        return True, (f"구멍 난 인덱스·역순 입력에서도 월 배치가 행과 일치 "
                      f"(표본 {len(fl):,}행 · cum120 유효 {obs}건 · 시간 단조성 유지)")

    _cc("C1b", "수급(d3) 행 정렬 — 미래 수급 유입 차단", c1b)

    # ── 원칙 3 : 셀 정규화에 groupby.apply 금지 ───────────────────────────────────────────
    def p3():
        src = _src_of(cell_rank, cell_z, _rank_in)
        if not src:
            return True, "소스 조회 불가 — 검사 생략"
        if re.search(r"groupby\([^)]*\)\s*\.\s*apply\s*\(", src):
            return False, "셀 정규화에 groupby.apply 가 있습니다 (수십 배 느립니다)"
        if "rank(pct=True" not in src.replace(" ", "") and "rank(pct=True)" not in src:
            if "pct=True" not in src:
                return False, "rank(pct=True) 경로가 보이지 않습니다"
        return True, "rank(pct=True) + transform 벡터화 경로만 사용"

    _cc("원칙3", "셀 정규화 벡터화 (groupby.apply 금지)", p3)

    # ── 원칙 5 : 벤치마크 하드코딩 금지 ───────────────────────────────────────────────────
    def p5():
        src = _src_of(R0_benchmark, report_performance_v3)
        if not src:
            return True, "소스 조회 불가 — 검사 생략"
        # 성과 수치를 리터럴로 박아 둔 흔적(예: CAGR=0.23 같은 상수 비교)이 없어야 한다
        if re.search(r"(CAGR|Sharpe|Calmar)\s*=\s*-?\d+\.\d+", src):
            return False, "벤치마크/성과 수치가 소스에 하드코딩되어 있습니다"
        if "groupby" not in src or "fwd_ret" not in src:
            return False, "벤치마크를 이 실행에서 직접 재측정하는 경로가 보이지 않습니다"
        return True, "유니버스 동일가중을 매 실행 직접 측정 (인용 없음)"

    _cc("원칙5", "벤치마크 하드코딩 금지 — 직접 재측정", p5)

    # ── C15 / 원칙 6 : 한계임금 분모 안정성, 0 채움 금지 ──────────────────────────────────
    def c15():
        E = pd.DataFrame({
            "corp_code": ["A"] * 4 + ["B"] * 3 + ["C"] * 2,
            "bsns_year": [2018, 2019, 2020, 2021, 2018, 2019, 2020, 2019, 2020],
            "rcept_dt": pd.to_datetime(
                ["2019-03-20", "2020-03-20", "2021-03-20", "2022-03-20",
                 "2019-03-20", "2020-03-20", "2021-03-20", "2020-03-20", "2021-03-20"]),
            #  A: 1000→1002 (Δ2, 임계 미달) → 결측 / 1002→1200 (Δ198, 통과) / 1200→1210(Δ10<36 미달)
            #  B: 500→1400 (+180% M&A 의심) → 결측
            #  C: 정상 증가
            "employees": [1000., 1002., 1200., 1210., 500., 1400., 1450., 300., 360.],
            "regular": [900., 900., 1080., 1090., 450., 1260., 1300., 270., 330.],
            "payroll_total": [7e10, 7.02e10, 8.6e10, 8.7e10, 3.5e10, 9.8e10, 1.0e11, 2.1e10, 2.6e10],
            "avg_salary": [7e7, 7e7, 7.2e7, 7.2e7, 7e7, 7e7, 7e7, 7e7, 7.1e7],
            "src_flag": ["detail"] * 9})
        S = build_emp_sensors(E)
        a = S[S["corp_code"] == "A"].set_index("bsns_year")
        if pd.notna(a.loc[2019, "nl_marginal"]):
            return False, "C15(a) 위반 — |Δ인원|=2 (임계 미달)인데 한계임금이 계산되었습니다"
        if pd.isna(a.loc[2020, "nl_marginal"]):
            return False, "C15(a) 오작동 — |Δ인원|=198 (임계 통과)인데 결측입니다"
        if pd.notna(a.loc[2021, "nl_marginal"]):
            return False, "C15(a) 위반 — |Δ인원|=10 < max(5, 1200×3%)=36 인데 계산되었습니다"
        b = S[S["corp_code"] == "B"].set_index("bsns_year")
        if pd.notna(b.loc[2019, "nl_marginal"]):
            return False, "C15(d) 위반 — 인원 +180%(M&A 의심)인데 한계임금이 계산되었습니다"
        ok, msg = test_c15(S)
        if not ok:
            return False, msg
        # 0 채움·forward-fill 금지 확인
        if (S["nl_marginal"] == 0).sum() > (E["employees"].diff() == 0).sum():
            return False, "한계임금에 0 채움 흔적이 있습니다"
        return True, msg

    _cc("C15", "한계임금 분모 안정성 (a)(b)(d) + 0채움 금지", c15)

    # ── C15(c) : 유효 관측치 하한 판정이 존재하는가 ───────────────────────────────────────
    def c15c():
        C = pd.DataFrame({"year": [2016, 2017, 2018, 2019],
                          "u_mid": [1000, 1000, 1000, 1000],
                          "emp_ok": [900, 900, 900, 900], "pay_ok": [700, 700, 800, 900],
                          "c15_ok": [100, 150, 500, 600], "valid": [100, 150, 500, 600]})
        start, msg = coverage_verdict(C)
        if COVERAGE_AUTO_TRIM and start is None:
            return False, "얇은 앞구간이 있는데 시작월 상향 판정이 나오지 않았습니다"
        if start is not None and start.year != 2019:
            return False, f"시작월 판정이 틀렸습니다: {start:%Y-%m} (기대 2019-04)"
        return True, f"판정 동작 확인 — {_trunc(msg, 70)}"

    _cc("C15c", "연도별 유효관측치 하한 → 창 상향 판정", c15c)

    # ── 거부권 이진성 ─────────────────────────────────────────────────────────────────────
    def veto():
        n = 60
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "month": pd.Timestamp("2020-06-30"),
                          "adv20": 1e9, "close": 1000.0, "equity": 1e9,
                          "revenue_ttm": 1e11, "inventory": 1e10, "receivable": 1e10,
                          "net_income_ttm": 1e10, "cfo_ttm": 1e10,
                          "nl_emp": rng.normal(size=n), "d_eff_tax": rng.normal(size=n) * 0.05})
        P = apply_vetoes_v3(P, {})
        for c in VETO_COLS_V3 + ["VETO"]:
            u = set(np.unique(P[c].to_numpy()))
            if not u <= {0.0, 1.0}:
                return False, f"{c} 가 이진이 아닙니다: {sorted(u)[:4]}"
        return True, f"V1·V2·V3·V5·V6·V8 및 곱 전부 ∈{{0,1}} (표본 {n})"

    _cc("거부권", "V ∈ {0,1} · 곱 · 상쇄 불가", veto)

    # ── 결정성 ────────────────────────────────────────────────────────────────────────────
    def det():
        a = np.random.default_rng(SEED).normal(size=32)
        b = np.random.default_rng(SEED).normal(size=32)
        if not np.allclose(a, b):
            return False, "동일 시드에서 난수가 재현되지 않습니다"
        return True, f"SEED={SEED} 재현성 확인"

    _cc("결정성", "동일 시드 → 동일 결과", det)

    # ── 드라이브 캐시 훼손 불가능성 (절대 1원칙) ──────────────────────────────────────────
    def vault_safe():
        src = _src_of(Vault.put_table, Vault.compact, Vault._register, Vault.flush) or ""
        bad = [p for p in (r"os\.remove\s*\(\s*self\.journal", r"shutil\.rmtree",
                           r"\.to_parquet\(\s*self\.journal")
               if src and re.search(p, src)]
        if bad:
            return False, f"인덱스를 파괴하는 호출이 있습니다: {bad}"
        if hasattr(Vault, "delete") or hasattr(Vault, "remove_table"):
            return False, "Vault 에 삭제 API 가 존재합니다 — 설계상 존재해선 안 됩니다"
        return True, "삭제 API 부재 · 저널 append-only · 컴팩션 전 백업"

    _cc("절대1원칙", "구글드라이브 캐시 훼손 불가능성", vault_safe)

    # ── §12-6 : 수집 호출량 상한 (4시간 계약) ─────────────────────────────────────────────
    def budget_bounded():
        """★ 실제로 터졌던 사고를 고정하는 회귀 테스트.

        Tier-2 재무(fnlttSinglAcntAll)와 직원현황(empSttus)은 잡 수가 |기업|×|연도|(×|분기|)
        로 **곱해진다**. 상한이 없으면 3,981사 × 13년 × 4분기 = 207,012 호출 = 11일치가
        조용히 큐에 올라간다 — tqdm ETA 로 드러났을 때는 이미 돌고 있다.
        이 계약은 (a) 두 단계 모두 상한을 갖고 (b) 그 상한이 DART 일일한도 안에 들고
        (c) 수집 함수가 상한 인자를 실제로 받는지를 강제한다.
        """
        caps = {"EMP_MAX_CALLS": EMP_MAX_CALLS, "DART_FS_MAX_CALLS": DART_FS_MAX_CALLS}
        missing = [k for k, v in caps.items() if v is None]
        if missing:
            return False, f"{missing} 에 상한이 없습니다 — 콜드빌드가 4시간 계약을 벗어납니다"
        import inspect as _ins
        for fn, arg in ((fetch_dart_financials, "max_calls"), (fetch_emp_status, "max_calls")):
            if arg not in _ins.signature(fn).parameters:
                return False, f"{fn.__name__} 이 {arg} 인자를 받지 않습니다"
        # ★ Tier-2 는 잡당 OFS→CFS 로 최대 2회를 던진다. '잡 수'가 아니라 '호출 수'로 센다.
        plan = int(EMP_MAX_CALLS) + int(DART_FS_MAX_CALLS) * 2 + 2100 + 600
        if max(int(EMP_MAX_CALLS), int(DART_FS_MAX_CALLS)) > DART_DAILY_LIMIT:
            return False, f"단일 단계 상한이 일일한도({DART_DAILY_LIMIT:,})를 넘습니다"
        # 예전엔 plan 을 계산해 성공 메시지에 찍기만 하고 **한도와 비교하지 않았다.**
        # 그래서 26,000건 계획이 "일일한도 19,000 안" 이라는 문구와 함께 PASS 했다.
        if plan > DART_DAILY_LIMIT:
            return False, (f"계획 호출 {plan:,}건이 일일한도 {DART_DAILY_LIMIT:,}건을 넘습니다 "
                           f"(EMP {EMP_MAX_CALLS:,} + Tier-2 {DART_FS_MAX_CALLS:,}×2 + "
                           f"배치·캐너리 ≈2,700). 한 실행이 한도를 넘게 계획하면 "
                           f"뒤쪽 단계는 반드시 굶습니다 — 상한을 낮추세요")
        # 5~8건/초 실측 기준 상한 소진에 걸리는 최악 시간이 4시간 안이어야 한다.
        worst_h = (int(EMP_MAX_CALLS) / 8.0 + int(DART_FS_MAX_CALLS) / 5.0) / 3600.0
        if worst_h > WALL_CLOCK_LIMIT_H * 0.6:
            return False, (f"상한 소진 예상 {worst_h:.1f}h 가 수집 몫(4h×0.6)을 넘습니다 — "
                           f"EMP_MAX_CALLS/DART_FS_MAX_CALLS 를 낮추세요")
        return True, (f"계획 {plan:,}건 (EMP {EMP_MAX_CALLS:,} + Tier-2 {DART_FS_MAX_CALLS:,}×2 "
                      f"+ 배치·캐너리) ≈{worst_h*60:.0f}분 · 일일한도 {DART_DAILY_LIMIT:,} 안")

    _cc("§12-6", "수집 호출량 상한 — 4시간 계약", budget_bounded)

    # ── §12-R : 자원 부족을 데이터 부재로 판정 금지 ───────────────────────────────────────
    def resource_vs_data():
        """★ 실제로 실행을 죽인 사고를 고정하는 회귀 테스트.

        DART 일일 한도가 이미 소진된 상태로 시작한 실행에서, 모든 호출이 예산 게이트에
        막혀 None 을 돌려줬다. CANARY 는 그것을 '데이터 없음'으로 읽어 K8 을 FAIL 시키고
        §12-2 킬 기준을 발동해 실행을 중단했다 — 데이터는 멀쩡히 있었다.
        더 나쁜 건 처방이었다: '백테스트 시작연도를 상향하라'. 오늘 호출권이 없다는
        일시적 사실로 10년 백테스트 구간을 영구히 잘라낼 뻔했다.

        이 계약은 (a) 자원 사유가 조회 가능하고 (b) 그 상태에서 CANARY 의 DART 검사가
        FAIL 이 아니라 SKIP 이 되며 (c) 킬 기준이 발동하지 않음을 강제한다.
        """
        for fn in ("dart_halt_reason", "dart_note_halt", "dart_budget_left"):
            if not callable(globals().get(fn)):
                return False, f"{fn}() 이 없습니다 — 자원 사유를 구별할 방법이 없습니다"
        saved = dict(DART_HALT)
        saved_results = list(CANARY_RESULTS)
        try:
            # 사고 당시와 똑같은 상태를 만든다: K8 이 치명 FAIL 로 기록된 채 예산이 소진됨.
            CANARY_RESULTS.clear()
            _k("K8", "연간급여총액 기재율", False, "표본 0건", "≥70%",
               "★ 임금프리미엄 계산 불가 — 중단(§12-2)", fatal=True)
            _k("K7", "empSttus 응답", False, "0/191 (0%)", "≥80%", "")
            _k("K5", "상장폐지 목록 확보", False, "폐지일 보유 0종목", "≥50종목", "", fatal=True)
            dart_note_halt("테스트: 일일 한도 소진", "회귀 검정")
            if not dart_halt_reason():
                return False, "halt 를 기록했는데 dart_halt_reason() 이 None 입니다"
            if not canary_resource_flip():
                return False, "자원 사유가 있는데 canary_resource_flip() 이 되돌리지 않았습니다"
            k8 = next(r for r in CANARY_RESULTS if r["id"] == "K8")
            k7 = next(r for r in CANARY_RESULTS if r["id"] == "K7")
            k5 = next(r for r in CANARY_RESULTS if r["id"] == "K5")
            if k8["passed"] is not None or k8["fatal"]:
                return False, "K8 이 여전히 치명 FAIL 입니다 — 실행이 또 킬 기준으로 죽습니다"
            if k7["passed"] is not None:
                return False, "K7 이 여전히 FAIL 입니다 (SKIP 이어야 함)"
            # K5(상장폐지 목록)는 DART 와 무관하므로 절대 완화되면 안 된다.
            if k5["passed"] is not False or not k5["fatal"]:
                return False, "K5(생존자편향)까지 완화됐습니다 — DART 무관 검사는 건드리면 안 됩니다"
            fatal_left = [r["id"] for r in CANARY_RESULTS if r["fatal"] and r["passed"] is False]
            return True, (f"K7·K8 → SKIP 전환 · K5 는 치명 FAIL 유지 "
                          f"(잔여 치명 {fatal_left}) · 킬 기준 오발동 차단")
        finally:
            DART_HALT.update(saved)
            CANARY_RESULTS.clear()
            CANARY_RESULTS.extend(saved_results)

    _cc("§12-R", "자원 부족 ≠ 데이터 부재 (킬 기준 오발동 방지)", resource_vs_data)

    # ── C2c : 폐지 유형별 청산가 ──────────────────────────────────────────────────────────
    def delist_kinds():
        """흡수합병·스팩해산을 -100% 로 계상하지 않는다. 단, 모르면 -100% 를 유지한다.

        ★ 실측 근거(폐지목록 원본 Reason, 2016년 이후 폐지 주권 561건):
          피흡수합병 60 · 스팩소멸합병 53 · 완전자회사화 43 → 인수기업 주식을 받는다.
          스팩 예심 미제출·해산·존속기간만료 ~130 → 예치금이 공모가+이자로 반환된다.
          이 308건(55%)을 전액손실로 계상하면 매년 -2%p 안팎의 없는 손실을 지어낸다.
          이것은 '보수적'이 아니라 그냥 틀린 것이다. 반대로 사유를 모르면(unknown)
          반드시 -100% 를 유지해야 한다 — 그쪽이 진짜 보수다(원칙7).
        """
        cases = {
            "피흡수합병": "transfer", "피흡수합병(스팩소멸합병)": "transfer",
            "지주회사(최대주주등)의 완전자회사화 등": "transfer", "타법인의 완전자회사로 편입": "transfer",
            "신청에 의한 상장폐지": "transfer",
            "상장예비심사 청구서 미제출로 관리종목 지정 후 1개월 이내 동 사유 미해소": "spac",
            "해산 사유 발생": "spac", "존속기간 만료": "spac",
            "감사의견 거절(감사범위 제한)": "distress",
            "기업의 계속성 및 경영의 투명성 등을 종합적으로 고려하여 상장폐지기준에 해당한다고 결정": "distress",
            "자본전액잠식": "distress", "최종부도": "distress",
            "": "unknown", "사유 미상": "unknown",
        }
        wrong = [(k, classify_delisting(k), v) for k, v in cases.items()
                 if classify_delisting(k) != v]
        if wrong:
            return False, f"폐지 사유 분류 오류: {wrong[:3]}"
        # 모르면 전액손실이어야 한다 — 관대한 쪽으로 새면 성과가 부풀려진다.
        if "unknown" in DELIST_NOT_WIPEOUT:
            return False, "'unknown' 이 직전가 청산으로 분류돼 있습니다 — 모르면 -100% 여야 합니다"
        src = _src_of(run_backtest) or ""
        if src and "DELIST_NOT_WIPEOUT" not in src:
            return False, "백테스트 엔진이 폐지 유형을 쓰지 않습니다 — 전부 -100% 로 계상됩니다"
        if src and "-1.0" not in src:
            return False, "백테스트 엔진에서 -100% 경로가 사라졌습니다(원칙7 위반)"
        return True, (f"합병·완전자회사화·스팩해산 → 직전가 청산 · "
                      f"부실·사유불명 → -100% 유지 (표본 {len(cases)}건 전부 일치)")

    _cc("C2c", "폐지 유형별 청산가 (합병을 전액손실로 계상 금지)", delist_kinds)

    # ── §12-A : 알파 원천 보호 ────────────────────────────────────────────────────────────
    def alpha_guard():
        """★ 실행 3회 내내 dart_employees_ext 가 0행이었던 사고를 고정한다.

        원인은 둘이었다.
          ① 사전점검이 세 테이블을 **합산**해 total>0 이면 진행했다. 재무 146만 행이 있고
             직원현황이 0행인 상태를 '캐시 충분'으로 읽어, 27분(잠재 2시간)을 태운 뒤에야
             "EMP-LITE 3개 TP 가 모두 결측"을 선언했다. 테이블은 대체재가 아니다.
          ② Tier-2 재무가 일일 한도를 먼저 다 써버려 EMP 몫이 남지 않았다. 단계 순서를
             바꿔도 예산은 날짜별 누적이라 어제 태운 것이 오늘까지 따라온다.
        이 계약은 (a) 예약 API 가 존재하고 실제로 남의 인출을 막으며 (b) 예약분은 해당
        용도가 인출할 수 있고 (c) 사전점검이 알파 테이블을 개별로 본다는 것을 강제한다.
        """
        for fn in ("reserve", "left", "take"):
            if not callable(getattr(DartBudget, fn, None)):
                return False, f"DartBudget.{fn}() 이 없습니다 — 알파 예산을 지킬 수단이 없습니다"
        b = DartBudget.__new__(DartBudget)          # _load(파일 I/O) 를 타지 않게 직접 구성
        b.today, b.n, b.exhausted = "T", 0, False
        b._lk = threading.RLock()
        b._reserved, b._dirty, b._warned_reserve = {}, 0, False
        b.reserve("emp", 100)
        room = DART_DAILY_LIMIT - 100
        if b.left(None) != room:
            return False, f"예약 후 일반 잔량이 {b.left(None):,} (기대 {room:,})"
        if b.left("emp") != DART_DAILY_LIMIT:
            return False, "예약 당사자가 자기 예약분을 못 봅니다"
        # 일반 소비자가 예약분까지 먹어치우지 못해야 한다.
        if b.take(room, purpose=None) is not True:
            return False, "일반 소비자가 정당한 잔량조차 인출하지 못합니다"
        if b.take(1, purpose=None) is not False:
            return False, "★ 일반 소비자가 예약분을 인출했습니다 — 알파가 또 굶습니다"
        if b.take(1, purpose="emp") is not True:
            return False, "★ 예약 당사자가 자기 예약분을 인출하지 못합니다"
        # 사전점검이 알파 테이블을 개별 판정하는가 (합산 판정이면 사고가 재현된다)
        src = _src_of(preflight_dart_v3) or ""
        if src:
            if "dart_employees_ext" not in src:
                return False, "사전점검이 알파 테이블을 개별로 보지 않습니다"
            if "sum(have.values())" in src and "dead_alpha" not in src:
                return False, "사전점검이 여전히 합산으로만 판정합니다"
        if not REQUIRE_EMP_ALPHA:
            return True, "예약 동작 확인 · REQUIRE_EMP_ALPHA=False (알파 없이도 진행하도록 설정됨)"
        return True, (f"예약 {EMP_RESERVED_CALLS:,}건은 EMP 만 인출 가능 · "
                      f"알파 부재 시 수집 전 중단")

    _cc("§12-A", "알파 원천(직원현황) 예산 보호 · 부재 시 사전 중단", alpha_guard)

    # ── 출력 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 34), "PASS" if r["pass"] else "FAIL",
             _trunc(r["msg"], 60)] for r in CONTRACT_V3]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["c", "l", "c", "l"],
              title="계약 자동검정 (주석이 아니라 테스트로 강제)", maxw=62)
    fails = [r for r in CONTRACT_V3 if not r["pass"]]
    if fails:
        LOG.error(f"계약 위반 {len(fails)}건: " + ", ".join(r["id"] for r in fails))
        for r in fails:
            LOG.warn(f"  · [{r['id']}] {r['name']} — {r['msg']}")
        if strict:
            raise RuntimeError(
                f"계약 검정 {len(fails)}건 실패 — 실행을 중단합니다. "
                f"이 계약들은 협상 대상이 아닙니다. 임계값을 바꿔 통과시키지 마십시오.")
        return False
    LOG.ok(f"계약 검정 {len(CONTRACT_V3)}건 전부 통과")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  실경로 리허설 (REHEARSAL) — 수집 함수를 '진짜로' 실행해 본다                        ║
# ║                                                                                          ║
# ║  왜 이 계층이 생겼는가:                                                                    ║
# ║    합성 스모크(§80)는 make_synthetic() 이 만든 완성 패널을 곧바로 주입한다. 즉               ║
# ║    build_security_master · fetch_prices · tidy_financials · hankyung_collect 같은          ║
# ║    실제 수집·정제 함수는 단 한 줄도 실행되지 않는다.                                        ║
# ║    실제로 이 공백 때문에 계약 17건 + 스모크를 전부 통과한 빌드가 실행 2분 만에               ║
# ║    build_security_master 의 중복 컬럼 한 줄로 죽었다.                                      ║
# ║                                                                                          ║
# ║  그래서 여기서는 네트워크 계층만 가짜로 바꾸고(HTTP·pykrx·FDR), 그 위의 수집·정제           ║
# ║  로직은 실물 그대로 돌린다. 각 함수에 대해 네 가지를 먹인다:                                 ║
# ║    ① 정상 응답  ② 빈 응답  ③ 깨진 응답  ④ 기대 컬럼이 빠진 응답                            ║
# ║  전부 '예외 없이' 통과해야 하고, 정상 응답에서는 실제로 값이 나와야 한다.                    ║
# ║                                                                                          ║
# ║  수 초면 끝나고 네트워크·키가 필요 없다. 실수집 전에 반드시 통과해야 한다.                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []

# 전략별 추가 리허설 훅. 시그니처: fn(G: dict, sec: pd.DataFrame, corps: List[str],
# months: pd.DatetimeIndex) -> None.  가짜 네트워크가 이미 물려 있는 안쪽에서 호출된다.
# 코어만 빌드하면 빈 리스트라 동작이 바뀌지 않는다(순수 추가).
REHEARSAL_HOOKS: List[Callable] = []


def _rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    """리허설 1건 실행. 예외는 실패, 정상응답 0행도 (기대했다면) 실패."""
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        REHEARSAL_RESULTS.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0,
            "err": "" if ok else "정상 응답을 줬는데 결과가 0행입니다(파싱 실패 가능성)",
            "note": note})
        return out
    except Exception as e:                                          # noqa
        REHEARSAL_RESULTS.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0,
            "err": f"{type(e).__name__}: {str(e)[:200]}", "note": note,
            "tb": traceback.format_exc()})
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────────────────────
def _fx_fdr_listing_csv(n: int = 40) -> bytes:
    # FDR GitHub 캐시 실제 스키마 (ChagesRatio 오타는 업스트림 그대로)
    rows = ["，Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"
            .replace("，", "")]
    for i in range(n):
        code = f"{i+1:06d}"
        rows.append(f"{i},{code},KR7{code}003,합성{i+1:03d},"
                    f"{'KOSPI' if i%2 else 'KOSDAQ'},,10000,0.5,1000000000,100000,"
                    f"{'STK' if i%2 else 'KSQ'}")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_fdr_delisting_csv(n: int = 30) -> bytes:
    rows = ["Symbol,Name,Market,SecuGroup,Kind,DelistingDate,ToSymbol,ToName,Reason"]
    for i in range(n):
        # 앞 20건은 정상 6자리, 뒤 10건은 비표준 코드(ETF/ELW/스팩 등) — 탈락 집계 검증용
        code = f"{900000+i:06d}" if i < 20 else f"KR{i:08d}"
        rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,"
                    f"{2017+(i%8)}-0{1+(i%9)}-15,,,상장폐지")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_kind_html(n: int = 30) -> bytes:
    # KIND 는 HTML 표이고 종목코드가 '정수'로 와서 앞자리 0 이 날아간다
    head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
            "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
    body = "".join(
        f"<tr><td>합성{i+1:03d}</td><td>{i+1}</td><td>화학</td><td>제품</td>"
        f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td><td>서울</td></tr>"
        for i in range(n))
    return (head + body + "</table>").encode("euc-kr")


def _fx_dart_fnltt(corp: str, year: int) -> dict:
    def row(sj, aid, anm, amt):
        return {"rcept_no": f"{year}0331000001", "reprt_code": "11011", "bsns_year": str(year),
                "corp_code": corp, "sj_div": sj, "sj_nm": sj, "account_id": aid,
                "account_nm": anm, "thstrm_amount": amt, "frmtrm_amount": amt, "ord": "1"}
    return {"status": "000", "message": "정상", "list": [
        row("IS", "ifrs-full_Revenue", "매출액", "1,234,567,000,000"),
        row("IS", "ifrs-full_CostOfSales", "매출원가", "900,000,000,000"),
        row("IS", "dart_OperatingIncomeLoss", "영업이익", "120,000,000,000"),
        row("IS", "ifrs-full_ProfitLoss", "당기순이익", "90,000,000,000"),
        row("IS", "-표준계정코드 미사용-", "경상연구개발비", "30,000,000,000"),
        row("IS", "ifrs-full_IncomeTaxExpense", "법인세비용", "20,000,000,000"),
        row("IS", "ifrs-full_ProfitLossBeforeTax", "법인세비용차감전순이익", "110,000,000,000"),
        row("IS", "dart_SellingGeneralAdministrativeExpenses", "판매비와관리비", "200,000,000,000"),
        row("BS", "ifrs-full_Inventories", "재고자산", "150,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권", "180,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentPayables", "매입채무및기타채무", "120,000,000,000"),
        row("BS", "ifrs-full_Assets", "자산총계", "3,000,000,000,000"),
        row("BS", "ifrs-full_Liabilities", "부채총계", "1,200,000,000,000"),
        row("BS", "ifrs-full_Equity", "자본총계", "1,800,000,000,000"),
        row("BS", "ifrs-full_PropertyPlantAndEquipment", "유형자산", "800,000,000,000"),
        row("BS", "ifrs-full_IntangibleAssetsOtherThanGoodwill", "무형자산", "100,000,000,000"),
        row("BS", "dart_ContractLiabilities", "계약부채", "50,000,000,000"),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "140,000,000,000"),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득", "-60,000,000,000"),
        row("CF", "dart_DepreciationAndAmortisationExpense", "감가상각비와상각비", "50,000,000,000"),
        row("CF", "ifrs-full_DividendsPaid", "배당금지급", "-15,000,000,000"),
        row("CF", "dart_PaymentsToAcquireOrRedeemEntitysShares", "자기주식의 취득", "-8,000,000,000"),
        row("CF", "ifrs-full_ProceedsFromBorrowings", "차입금의 증가", "40,000,000,000"),
    ]}


def _fx_dart_emp(corp: str, year: int) -> dict:
    # 사업부문 × 성별로 쪼개진 실제 스키마 + '합계' 소계 행(이중계상 방지 검증)
    def r(bbm, sex, sm, tot):
        return {"rcept_no": f"{year}0331000001", "corp_code": corp, "fo_bbm": bbm,
                "sexdstn": sex, "sm": sm, "fyer_salary_totamt": tot,
                "jan_salary_am": "70,000,000"}
    return {"status": "000", "list": [
        r("반도체", "남", "1,200", "96,000,000,000"),
        r("반도체", "여", "300", "21,000,000,000"),
        r("디스플레이", "남", "500", "40,000,000,000"),
        r("디스플레이", "여", "100", "7,000,000,000"),
        r("합계", "합계", "2,100", "164,000,000,000"),
    ]}


def _fx_dart_list(bgn: str) -> dict:
    y = bgn[:4]
    return {"status": "000", "page_no": 1, "total_page": 1, "list": [
        {"corp_code": "C0000001", "corp_name": "합성001", "stock_code": "000001",
         "rcept_no": f"{y}0410000001", "rcept_dt": f"{y}0410",
         "report_nm": "주요사항보고서(자기주식취득결정)", "flr_nm": "합성001", "corp_cls": "Y"},
        {"corp_code": "C0000002", "corp_name": "합성002", "stock_code": "000002",
         "rcept_no": f"{y}0412000002", "rcept_dt": f"{y}0412",
         "report_nm": "주요사항보고서(유상증자결정)", "flr_nm": "합성002", "corp_cls": "Y"},
        {"corp_code": "C0000003", "corp_name": "합성003", "stock_code": "000003",
         "rcept_no": f"{y}0415000003", "rcept_dt": f"{y}0415",
         "report_nm": "사업보고서 (2023.12)", "flr_nm": "합성003", "corp_cls": "Y"},
    ]}


def _fx_hankyung_html(n: int = 12) -> str:
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
    return f"<div id='contents'><div class='table_style01'><table>{hdr}{''.join(rows)}</table></div></div>"


def _fx_naver_research_html(n: int = 12) -> str:
    hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
           "<th>작성일</th><th>조회수</th></tr>")
    rows = []
    for i in range(n):
        rows.append(
            "<tr>"
            f"<td style='padding-left:10'><a class='stock_item' href='/item/main.naver?code={i+1:06d}' "
            f"title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
            f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>실적 개선 전망</a></td>"
            f"<td>{'KB증권' if i%2 else '신한금융투자'}</td>"
            f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
            f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
            f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
    nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
           "<a href='/research/company_list.naver?&amp;page=3'>맨뒤</a></td></tr></table>")
    return (f"<div id='contentarea_left'><div class='box_type_m'>"
            f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")


def _fx_nps_json(page: int) -> dict:
    items = [{"wkplNm": f"합성{i+1:03d}", "bzowrRgstNo": f"{1000000000+i}",
              "jnngpCnt": str(100 + i * 7), "crrmmNtcAmt": str((100 + i * 7) * 300000),
              "nwAcqzrCnt": "5", "lssJnngpCnt": "3", "wkplRoadNmDtlAddr": "서울시 강남구",
              "ldongAddrMgplDgCd": "11", "vldtVlKrnNm": "제조업", "seq": str(i)}
             for i in range(40)]
    return {"response": {"header": {"resultCode": "00"},
                         "body": {"totalCount": 40, "pageNo": page, "numOfRows": 1000,
                                  "items": {"item": items if page == 1 else []}}}}


def _fx_g2b_json() -> dict:
    items = [{"bizno": f"{1000000000+i}", "bidwinnrNm": f"합성{i+1:03d}",
              "sucsfbidAmt": str(1_000_000_000 + i * 1_000_000),
              "presmptPrce": str(1_200_000_000 + i * 1_000_000),
              "sucsfbidRate": str(85 + (i % 10)), "dminsttNm": "조달청",
              "prdctClsfcNo": f"{4000+i}"} for i in range(25)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_customs_json() -> dict:
    items = [{"expDlr": str(1_000_000 + i * 1000), "expWgt": str(500_000 + i * 500),
              "statCd": ["US", "DE", "VN", "CN"][i % 4]} for i in range(8)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_pdf() -> bytes:
    return b"%PDF-1.4\n% synthetic fixture\n%%EOF\n"


# ── 라우팅 ──────────────────────────────────────────────────────────────────────────────────
class _FixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크. mode 로 정상/빈/깨짐/컬럼누락을 전환한다."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: Counter = Counter()

    def _m(self, kind: str):
        self.hits[kind] += 1

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u = str(url)
        p = params or {}
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return b"\x00\x01garbage" if as_bytes else "<html><body>오류</body></html>"

        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                self._m("fdr_delisting")
                return _fx_fdr_delisting_csv()
            self._m("fdr_listing")
            if self.mode == "missingcol":
                return b"\xef\xbb\xbf,Foo,Bar\n0,1,2\n"
            return _fx_fdr_listing_csv()
        if "kind.krx.co.kr" in u:
            self._m("kind")
            return _fx_kind_html()
        if "corpCode.xml" in u:
            self._m("dart_corpcode")
            buf = io.BytesIO()
            xml = "<result>" + "".join(
                f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
                f"<stock_code>{i+1:06d}</stock_code><modify_date>20240101</modify_date></list>"
                for i in range(40)) + "</result>"
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml", xml.encode("utf-8"))
            return buf.getvalue()
        if "document.xml" in u:
            self._m("dart_document")
            buf = io.BytesIO()
            body = ("<?xml version='1.0' encoding='euc-kr'?><DOCUMENT>"
                    "II. 사업의 내용 당사는 반도체 소재를 제조합니다. " * 30 +
                    "위험요인 환율 변동 위험이 존재합니다. " * 30 +
                    "우발부채 계류 중인 소송은 없습니다. " * 20 + "</DOCUMENT>")
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("doc.xml", body.encode("euc-kr"))
            return buf.getvalue()
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                self._m("hk_pdf")
                return _fx_pdf()
            self._m("hankyung")
            page = int(p.get("now_page", 1) or 1)
            return _fx_hankyung_html() if page == 1 else "<td class='no_data'>데이터가 없습니다</td>"
        if "finance.naver.com/research" in u:
            self._m("naver_research")
            page = int(p.get("page", 1) or 1)
            if page <= 2:
                return _fx_naver_research_html()
            return "<div id='contentarea_left'><table class='type_1'></table></div>"
        if "finance.naver.com/item/main" in u:
            self._m("naver_item")
            return ('<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>')
        if "stock.pstatic.net" in u:
            self._m("naver_pdf")
            return _fx_pdf()
        if "siseJson" in u:
            self._m("naver_chart")
            rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
            d = as_ts("2016-05-02")
            for i in range(2600):
                d2 = d + pd.Timedelta(days=i)
                if d2.weekday() >= 5:
                    continue
                rows.append(f"['{d2:%Y%m%d}',10000,10100,9900,10050,120000,5.0]")
            return "[" + ",".join(rows) + "]"
        self._m("other")
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "opendart" in u and "fnlttSinglAcntAll" in u:
            self._m("dart_fnltt")
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return _fx_dart_fnltt(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "empSttus" in u:
            self._m("dart_emp")
            return _fx_dart_emp(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "list.json" in u:
            self._m("dart_list")
            return _fx_dart_list(str(p.get("bgn_de", "20200101")))
        if "NpsBplcInfoInqireService" in u:
            self._m("nps")
            return _fx_nps_json(int(p.get("pageNo", 1) or 1))
        if "ScsbidInfoService" in u:
            self._m("g2b")
            return _fx_g2b_json() if int(p.get("pageNo", 1) or 1) == 1 else {"response": {"body": {"items": []}}}
        if "nitemtrade" in u:
            self._m("customs")
            return _fx_customs_json()
        if "stockSecurity/researches" in u:
            self._m("naver_api")
            return []                       # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        self._m("other_json")
        return None


def run_rehearsal(strict: bool = True) -> bool:
    """실제 수집·정제 함수를 픽스처로 전부 실행한다. 네트워크·키 불필요."""
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다")
    REHEARSAL_RESULTS.clear()
    G = globals()
    saved = {k: G.get(k) for k in ("http_get", "http_json", "http_post",
                                   "fdr", "pykrx_stock", "yf", "DART_API_KEY",
                                   "DATA_GO_KR_KEY", "CUSTOMS_API_KEY", "RUN_MODE",
                                   "RESEARCH_DOWNLOAD_PDF", "UNIVERSE_SNAPSHOT_FREQ")}
    tmp = tempfile.mkdtemp(prefix="tcd_rehearsal_")
    saved_vault, saved_budget = G.get("VAULT"), G.get("DBUDGET")
    months = month_range("2016-08-01", "2026-07-31")

    try:
        # 네트워크·외부 라이브러리 차단 + 키 주입 (키가 있어야 해당 분기가 실행된다)
        net = _FixtureNet("ok")
        G["http_get"] = net.get
        G["http_json"] = net.json
        G["http_post"] = lambda *a, **k: ""
        G["fdr"] = None
        G["pykrx_stock"] = None            # 스냅샷 경로는 '없을 때' 폴백을 검증
        G["yf"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["DATA_GO_KR_KEY"] = "REHEARSAL"
        G["CUSTOMS_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["VAULT"] = Vault(tmp, "REHEARSAL")
        G["DBUDGET"] = DartBudget()

        # ── ① 유니버스 ────────────────────────────────────────────────────────────────────
        snaps = _rh("fetch_pykrx_snapshots(pykrx 없음→폴백)",
                    lambda: fetch_pykrx_snapshots(months), expect_rows=False,
                    note="pykrx 미설치 상황에서 죽지 않고 빈 결과를 돌려줘야 한다")
        _rh("fetch_fdr_listing", fetch_fdr_listing)
        _rh("fetch_fdr_delisting", fetch_fdr_delisting)
        _rh("fetch_kind_listing", fetch_kind_listing)
        _rh("fetch_dart_corpcode", fetch_dart_corpcode)
        sec = _rh("build_security_master ★이번 크래시 지점",
                  lambda: build_security_master(snaps if snaps is not None else pd.DataFrame(
                      columns=["snap_date", "code", "market"])),
                  note="중복 컬럼 → groupby.agg 폭발이 여기서 났다")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{i+1:06d}" for i in range(40)],
                                "name": [f"합성{i+1:03d}" for i in range(40)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(40)],
                                "listing_date": as_ts("2010-01-01"),
                                "delisting_date": pd.NaT, "sector_src": "fx", "src": "fx"})

        # ── ② 가격 ────────────────────────────────────────────────────────────────────────
        codes = sec["code"].dropna().tolist()[:12]
        px = _rh("fetch_prices(네이버 차트 폴백)",
                 lambda: fetch_prices(codes, "2016-05-01", "2026-07-31"),
                 note="FDR/pykrx 없이 네이버 경로만으로 동작해야 한다")
        if px is not None and len(px):
            _rh("build_price_panel", lambda: build_price_panel(px, months))
        _rh("fetch_investor_flows(pykrx 없음)",
            lambda: fetch_investor_flows(codes, "2016-08-01", "2026-07-31"), expect_rows=False)

        # ── ③ DART ────────────────────────────────────────────────────────────────────────
        corps = sec["corp_code"].dropna().astype(str).tolist()[:6]
        years = [2019, 2020, 2021]
        fs = _rh("fetch_dart_financials", lambda: fetch_dart_financials(corps, years))
        if fs is not None and len(fs):
            _rh("tidy_financials", lambda: tidy_financials(fs))
        _rh("fetch_dart_employees", lambda: fetch_dart_employees(corps, years),
            note="사업부문×성별 분해 + '합계' 소계행 이중계상 방지")
        dis = _rh("fetch_dart_disclosures",
                  lambda: fetch_dart_disclosures("2019-01-01", "2019-06-30"))

        # ── ④ 리서치 원장 ─────────────────────────────────────────────────────────────────
        hk = _rh("hankyung_collect", lambda: hankyung_collect("2024-01-01", "2024-12-31"))
        nv = _rh("naver_collect", lambda: naver_collect("2024-01-01", "2024-12-31",
                                                        cats=("company",)))
        if nv is not None and len(nv):
            _rh("naver_enrich_detail", lambda: naver_enrich_detail(nv, limit=5),
                expect_rows=False)
        frames = [x for x in (hk, nv) if x is not None and len(x)]
        rep = _rh("build_report_master(다중소스 병합)",
                  lambda: build_report_master(frames, sec)) if frames else None
        if rep is not None and len(rep):
            rep2 = _rh("download_pdfs", lambda: download_pdfs(rep, cap_per_month=3))
            A_L = _rh("build_analyst_ledger",
                      lambda: build_analyst_ledger(rep2 if rep2 is not None else rep),
                      expect_rows=False)
            if A_L is not None:
                A, L = A_L
                _rh("audit_linkage", lambda: (audit_linkage(rep, A, L) or [1]),
                    expect_rows=False)
                _rh("build_consensus_panel", lambda: build_consensus_panel(L, months),
                    expect_rows=False)

        # ── ⑤ 팩 전용 수집 ────────────────────────────────────────────────────────────────
        if "fetch_nps_workplaces" in G:
            N = _rh("fetch_nps_workplaces", lambda: fetch_nps_workplaces(months[:3]))
            if N is not None and len(N):
                M = _rh("resolve_nps_to_corp",
                        lambda: resolve_nps_to_corp(N, sec, pd.DataFrame())[0])
                if M is not None and len(M):
                    _rh("build_nps_panel", lambda: build_nps_panel(N, M, pd.DataFrame(), months),
                        expect_rows=False)
        if "fetch_procurement" in G:
            _rh("fetch_procurement", lambda: fetch_procurement(months[:2]))
        if "fetch_customs_trade" in G:
            _rh("fetch_customs_trade",
                lambda: fetch_customs_trade(months[:2], ["3901000000", "3902000000"]))
        if "fetch_dart_documents" in G and dis is not None and len(dis):
            T = _rh("fetch_dart_documents", lambda: fetch_dart_documents(dis, sec, max_docs=5),
                    expect_rows=False)
            if T is not None and len(T):
                _rh("build_text_similarity", lambda: build_text_similarity(T),
                    expect_rows=False)

        # ── ⑤-b 전략별 추가 리허설 (가짜 네트워크가 물려 있는 상태에서 실행) ──────────────
        for _hook in list(REHEARSAL_HOOKS):
            try:
                _hook(G, sec, corps, months)
            except Exception as _e:                                  # noqa
                REHEARSAL_RESULTS.append({
                    "name": f"[훅] {getattr(_hook, '__name__', 'hook')}", "ok": False,
                    "rows": -1, "sec": 0.0, "err": f"{type(_e).__name__}: {_e}",
                    "note": "", "tb": traceback.format_exc()})

        # ── ⑥ 이상 응답 내성 (빈/깨짐/컬럼누락) ───────────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = _FixtureNet(mode)
            G["http_get"], G["http_json"] = bad.get, bad.json
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"tcd_rh_{mode}_"), "REHEARSAL")
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing),
                              ("fetch_dart_corpcode", fetch_dart_corpcode)):
                _rh(f"[{label}] {fname}", fn, expect_rows=False,
                    note="예외 없이 빈 결과를 돌려줘야 한다")
            _rh(f"[{label}] fetch_dart_financials",
                lambda: fetch_dart_financials(corps, [2020]), expect_rows=False)
            _rh(f"[{label}] hankyung_collect",
                lambda: hankyung_collect("2024-01-01", "2024-03-31"), expect_rows=False)
            _rh(f"[{label}] build_report_master(빈 입력)",
                lambda: build_report_master([], sec), expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"], G["DBUDGET"] = saved_vault, saved_budget
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in REHEARSAL_RESULTS if r["ok"])
    LOG.table([[r["name"], "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 62)]
               for r in REHEARSAL_RESULTS],
              ["실경로 함수", "판정", "결과", "소요", "비고"],
              ["l", "c", "r", "r", "l"], maxw=64)
    fails = [r for r in REHEARSAL_RESULTS if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(REHEARSAL_RESULTS)}건 실패")
        for r in fails[:4]:
            LOG.banner(f"✘ 리허설 실패: {r['name']}", r["err"])
            for ln in str(r.get("tb", "")).rstrip().split("\n")[-10:]:
                _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"이 검사는 '수집 함수가 진짜 데이터 모양에서 도는지'를 보는 것이라, "
                f"여기서 막는 것이 몇 시간 뒤 L1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(REHEARSAL_RESULTS)}건 통과 — "
           f"수집·정제 함수가 실제 데이터 모양에서 정상 동작합니다.")
    return True

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  합성 스모크 — 실데이터를 쓰기 전에 '계산경로'를 증명한다                                   ║
# ║                                                                                          ║
# ║  네트워크·키 없이 수십 초 안에 센서 → TP → 스코어 → 백테스트 → 성과 → 강건성까지            ║
# ║  전 출력물을 예행연습한다. 여기서 죽으면 수집을 시작하지 않는다.                             ║
# ║                                                                                          ║
# ║  ★ 스모크(계산경로)와 리허설(수집경로)은 서로 다른 것을 본다. 둘 다 필요하다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def make_synthetic_v3(n_codes: int = 320, n_months: int = 60, seed: int = None) -> dict:
    # ★ n_codes 기본값이 320 인 이유: U-MID 대역이 규모랭크 [251,1400] 이라 250종목 이하로는
    #   대역에 아무도 남지 않아 apply_umid 의 '폴백 경로'만 검증된다. 320이면 정상 경로와
    #   폴백 경로를 모두 태울 수 있다(스모크의 목적은 실행 경로 증명이다).
    rng = np.random.default_rng(SEED if seed is None else seed)
    end = as_ts(BACKTEST_END)
    months = pd.date_range(end - pd.DateOffset(months=n_months - 1), end, freq="ME")
    start = months[0] - pd.DateOffset(months=18)
    codes = [f"9{i:05d}" for i in range(n_codes)]
    corps = [f"S{i:07d}" for i in range(n_codes)]
    inds = ["반도체", "화학", "바이오", "기계", "소프트웨어", "유통", "건설"]

    sec = pd.DataFrame({
        "code": codes, "name": [f"합성{i:03d}" for i in range(n_codes)],
        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
        "listing_date": start - pd.Timedelta(days=1200),
        "delisting_date": pd.NaT,
        "corp_code": corps,
        "industry": [inds[i % len(inds)] for i in range(n_codes)]})
    # 생존자편향 경로를 반드시 태운다 — 일부 종목은 구간 중간에 상장폐지된다
    dead_idx = rng.choice(n_codes, max(3, n_codes // 25), replace=False)
    sec.loc[dead_idx, "delisting_date"] = [
        months[int(rng.integers(n_months // 3, n_months - 2))] for _ in dead_idx]

    # ── 일별 가격 (GBM) ───────────────────────────────────────────────────────────────────
    days = pd.bdate_range(start, end)
    T = len(days)
    drift = rng.normal(0.0004, 0.0006, n_codes)[:, None]
    # ★ 공통 시장 요인을 반드시 넣는다. 종목 수익이 서로 독립이면 동일가중 벤치마크의
    #   변동성이 1/√N 로 사라져 MDD 가 0 에 수렴하고 Calmar 가 수십으로 뛴다.
    #   그러면 R0(벤치마크 대비)가 합성 단계에서 구조적으로 항상 FAIL 이 되어,
    #   '검사가 도는지'조차 확인할 수 없는 무의미한 대조군이 된다. 실제 시장은 베타가 있다.
    mkt = rng.normal(0.0002, 0.011, size=(1, T))
    beta = rng.uniform(0.6, 1.4, n_codes)[:, None]
    shock = beta * mkt + rng.normal(0, 0.016, size=(n_codes, T))
    lp = np.log(rng.uniform(3000, 90000, n_codes))[:, None] + np.cumsum(drift + shock, axis=1)
    close = np.exp(lp)
    px = pd.DataFrame({
        "code": np.repeat(codes, T), "date": np.tile(days.values, n_codes),
        "close": close.ravel()})
    px["open"] = px["close"] * (1 + rng.normal(0, 0.004, len(px)))
    px["high"] = np.maximum(px["open"], px["close"]) * 1.01
    px["low"] = np.minimum(px["open"], px["close"]) * 0.99
    px["volume"] = rng.integers(3_000, 900_000, len(px))
    px["amount"] = px["volume"] * px["close"]
    px["src"] = "synthetic"
    px["date"] = as_ts_series(px["date"])
    # 폐지 종목은 폐지일 이후 거래가 없다
    dmap = sec.dropna(subset=["delisting_date"]).set_index("code")["delisting_date"].to_dict()
    if dmap:
        dd = px["code"].map(dmap)
        px = px[dd.isna() | (px["date"] <= dd)]

    # ── 분기 재무 (knowledge_date = 기말 + 45/90일) ───────────────────────────────────────
    qs = pd.date_range(start - pd.DateOffset(months=15), end, freq="QE")
    rows = []
    for i, cc in enumerate(corps):
        rev = rng.uniform(5e10, 9e11)
        growth = rng.normal(0.02, 0.04)
        for k, q in enumerate(qs):
            rev = max(rev * (1 + growth + rng.normal(0, 0.03)), 1e9)
            cogs = rev * rng.uniform(0.55, 0.85)
            op = rev - cogs - rev * rng.uniform(0.05, 0.18)
            ni = op * rng.uniform(0.5, 0.95)
            pretax = op * rng.uniform(0.8, 1.1)
            rows.append({
                "corp_code": cc, "period_end": q,
                "knowledge_date": q + pd.Timedelta(days=90 if q.month == 12 else 45),
                "revenue_ttm": rev * 4, "cogs_ttm": cogs * 4, "op_income_ttm": op * 4,
                "net_income_ttm": ni * 4, "cfo_ttm": ni * 4 * rng.uniform(0.6, 1.6),
                "pretax_income_ttm": pretax * 4,
                "tax_expense_ttm": pretax * 4 * rng.uniform(0.10, 0.28),
                "capex_ttm": -rev * 4 * rng.uniform(0.02, 0.14),
                "dep_ttm": rev * 4 * rng.uniform(0.02, 0.07),
                "rnd_ttm": rev * 4 * rng.uniform(0.005, 0.06),
                "dividend_paid_ttm": -ni * 4 * rng.uniform(0.0, 0.35),
                "treasury_buy_ttm": -ni * 4 * rng.uniform(0.0, 0.20),
                "inventory": rev * rng.uniform(0.15, 0.55),
                "receivable": rev * rng.uniform(0.15, 0.50),
                "payable": rev * rng.uniform(0.10, 0.40),
                "assets": rev * 4 * rng.uniform(0.8, 2.2),
                "liabilities": rev * 4 * rng.uniform(0.3, 1.2),
                "equity": rev * 4 * rng.uniform(0.4, 1.2),
                "ppe": rev * 4 * rng.uniform(0.2, 0.9),
                "intangible": rev * 4 * rng.uniform(0.02, 0.2),
                "contract_liab": rev * rng.uniform(0.0, 0.1),
                "v2_bad_3q": float(rng.random() < 0.05)})
    fin = pit_frame(pd.DataFrame(rows), "period_end", "knowledge_date", source="synthetic")

    # ── 연간 직원현황 ─────────────────────────────────────────────────────────────────────
    yrs = list(range(int(start.year) - 1, int(end.year) + 1))
    erows = []
    for cc in corps:
        emp = float(rng.integers(80, 4000))
        avg = float(rng.uniform(4.0e7, 1.1e8))
        for y in yrs:
            emp = max(20.0, emp * (1 + rng.normal(0.05, 0.14)))
            avg = avg * (1 + rng.normal(0.03, 0.05))
            miss_pay = rng.random() < 0.18          # 급여총액 무기재 케이스도 태운다
            erows.append({"corp_code": cc, "bsns_year": y,
                          "rcept_dt": as_ts(f"{y+1}-03-20"),
                          "employees": round(emp),
                          "regular": round(emp * rng.uniform(0.55, 0.98)),
                          "payroll_total": (np.nan if miss_pay
                                            else emp * avg * rng.uniform(0.9, 1.1)),
                          "avg_salary": avg, "src_flag": "detail"})
    emp_raw = pd.DataFrame(erows)

    # ── 공시 (자사주·유증) ────────────────────────────────────────────────────────────────
    drows = []
    for cc in rng.choice(corps, size=max(20, n_codes // 2), replace=False):
        for _ in range(int(rng.integers(1, 5))):
            d = months[int(rng.integers(0, n_months))]
            drows.append({"corp_code": cc, "rcept_no": f"{d:%Y%m%d}000001",
                          "rcept_dt": d, "report_nm": "주요사항보고서",
                          "event": rng.choice(["treasury_acq", "treasury_canc",
                                               "rights_issue", "cb_issue"])})
    dis = pit_frame(pd.DataFrame(drows), "rcept_dt", "rcept_dt", source="synthetic")

    # ── 수급 ──────────────────────────────────────────────────────────────────────────────
    fl = px[["code", "date"]].copy()
    fl["inst_net"] = rng.normal(0, 4e8, len(fl))
    fl["foreign_net"] = rng.normal(0, 4e8, len(fl))

    return {"sec": sec, "px": px, "fin": fin, "emp_raw": emp_raw,
            "disclosures": dis, "flows": fl, "months": months}


def run_selftest_v3(full_chain: bool = False) -> bool:
    """★ 프로덕션 함수를 그대로 호출한다. 스모크가 자기 사본을 돌리면 아무것도 증명하지 못한다.

    예전 구조는 build_features_v3 의 호출 순서를 스모크가 손으로 베껴 두는 방식이었다.
    그러면 프로덕션 쪽만 고쳤을 때 스모크는 여전히 통과하고, 2시간 반짜리 FULL 실행이
    수집을 다 끝낸 뒤 L1.PANEL 한 줄에서 죽는다. 실제로 그런 전례가 있다.
    → 합성 ctx 를 만들어 build_features_v3 → score_and_backtest_v3 → persist_outputs_v3 을
      **실물로** 통과시킨다.

    VAULT 는 임시 디렉터리로 바꿔 끼운다. 합성 피처·스코어가 사용자의 전용 인덱스에
    기록되면 그것이야말로 캐시 오염이다(절대 1원칙).
    """
    LOG.banner("① 합성데이터 엔드투엔드 스모크",
               "네트워크·키 없이 프로덕션 함수를 실물 호출해 계산경로를 증명합니다")
    t0 = time.time()
    G = globals()
    saved_vault = G.get("VAULT")
    saved_runtime = list(RUNTIME_ROWS)      # 합성 실행의 소요시간이 §10 예산표에 섞이지 않게
    tmp = tempfile.mkdtemp(prefix="tcd_v3_smoke_")
    try:
        G["VAULT"] = Vault(tmp, "SMOKE")
        S = make_synthetic_v3()
        months = S["months"]
        PIT._t.clear(); PIT._meta.clear()

        ES = build_emp_sensors(S["emp_raw"])
        PIT.register("dart_financials", S["fin"], key_cols=["corp_code"])
        PIT.register("emp_sensors",
                     pit_frame(ES, "period_end", "knowledge_date", source="synthetic"),
                     key_cols=["corp_code"])

        ctx: Dict[str, Any] = {
            "sec": S["sec"],
            "snapshots": pd.DataFrame(columns=["snap_date", "code", "market"]),
            "panel": build_price_panel(S["px"], months),
            "flows": S["flows"], "disclosures": S["disclosures"],
            "emp_raw": S["emp_raw"], "emp_sensors": ES, "fin": S["fin"],
        }

        # ── 프로덕션 경로 실물 호출 ────────────────────────────────────────────────────
        P, uni, ctx = build_features_v3(ctx, months)
        if P.empty:
            LOG.error("U-MID 필터 후 패널이 비었습니다 — apply_umid 폴백이 동작하지 않았습니다.")
            return False
        P, bt, _run = score_and_backtest_v3(P, ctx, months, uni)

        R = bt["returns"]
        if R.empty or not np.isfinite(R["ret"].fillna(0)).all():
            LOG.error("스모크 백테스트가 유효한 수익률 시계열을 만들지 못했습니다.")
            return False

        # 미래누수 자가검정 — 소스별 지식일이 모두 관측월 이하여야 한다
        bad = 0
        for kd in ("kd_fin", "kd_emp"):
            if kd in P.columns:
                bad += int((P[kd].notna() & (P[kd] > P["month"])).sum())
        if bad:
            LOG.error(f"★스모크에서 미래정보 유입 {bad:,}행 감지 — merge_asof 방향을 확인하세요.")
            return False

        LOG.ok(f"스모크 통과 — 패널 {len(P):,}행 × {P.shape[1]}열 · 백테스트 {len(R)}개월 · "
               f"평균 보유 {R['n'].mean():.1f}종목 · {time.time()-t0:.1f}초")

        if full_chain:
            bench = R0_benchmark(P, bt, months)
            report_performance_v3(bt, bench, label="SMOKE(합성)")
            uni.report_attrition()
            uni.attrition = []
            cal = build_policy_calendar_v3()
            report_policy_v3(cal, months)
            ctx["policy"] = cal
            try:
                R1_leakage(P, months, _run)
                R2N_kill_gate(P, _run)
                R3_orthogonal(P, _run)
                R5_ablation(P, _run)
                R7_regime(bt, bench)
                R8_subperiod(bt)
                R10_policy_falsify(P, cal, months, _run)
            except KillCriteria as e:
                LOG.warn(f"스모크 강건성에서 킬 기준 발동(합성데이터이므로 정상일 수 있음): {e}")
            report_robustness_v3()
            report_interpretation_v3(P)
            diagnostic_card_v3(P, bt, ctx["sec"])
            report_ledger_v3(ctx)
            # 산출물 경로까지 실물로 태운다 — FULL 2시간 뒤 저장부에서 죽는 것을 막는다
            outs = persist_outputs_v3(P, bt, ctx, bench, t0)
            LOG.ok(f"산출물 경로 검증 완료 — {len(outs)}개 파일 생성(임시 디렉터리, 곧 삭제됨): "
                   + ", ".join(os.path.basename(p) for p in outs[:6]))
        return True
    finally:
        G["VAULT"] = saved_vault
        if RUN_MODE != "SMOKE":                 # SMOKE 모드에선 이 표가 유일한 런타임 기록이다
            RUNTIME_ROWS[:] = saved_runtime
        shutil.rmtree(tmp, ignore_errors=True)

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  각 단계는 PIPE.stage 안에서만 돈다. 실패하면 자동으로 다음이 출력된다:                     ║
# ║    실패 지점(스테이지·계층·경과) / 직전 입출력 스냅샷 / 한글 진단 힌트 / 트레이스백          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _rehearsal_hook_v3(G: dict, sec: pd.DataFrame, corps: Sequence[str],
                       months: pd.DatetimeIndex) -> None:
    """v3 전용 수집·계산 함수를 리허설에 태운다 (가짜 네트워크가 물려 있는 안쪽)."""
    _rh("fetch_emp_status(v3 확장)",
        lambda: fetch_emp_status(list(corps)[:3], [2019, 2020]), expect_rows=False,
        note="empSttus 확장 파서 — 소계행 제거·단위 역추정 포함")
    _rh("build_emp_sensors + C15",
        lambda: build_emp_sensors(pd.DataFrame({
            "corp_code": ["Z1"] * 3, "bsns_year": [2018, 2019, 2020],
            "rcept_dt": pd.to_datetime(["2019-03-20", "2020-03-20", "2021-03-20"]),
            "employees": [500.0, 600.0, 610.0], "regular": [450.0, 540.0, 550.0],
            "payroll_total": [3.5e10, 4.4e10, 4.5e10],
            "avg_salary": [7e7, 7.1e7, 7.2e7], "src_flag": ["detail"] * 3})),
        note="연도 프레임 센서 + C15 게이트")


REHEARSAL_HOOKS.append(_rehearsal_hook_v3)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Tier-2 전체재무제표 수집 범위 — 4시간 계약(§12-6)을 지키는 지점
#
#  이 함수가 없으면 잡 수는 |상장·폐지 전 종목| × |연도| × |보고서| 로 곱해진다.
#  3,981사 × 13년 × 4분기 = 207,012회. DART 일일한도 19,000 기준 11일이다.
#  좁히는 근거는 두 가지뿐이고, 둘 다 결과를 바꾸지 않는다:
#    ① 한 번도 U-MID 대역(투자가능)에 들지 못한 종목의 전체재무제표는 어떤 달에도
#       포트폴리오에 들어갈 수 없다 → 스코어에 쓰이지 않는다.
#    ② 백테스트 시작연도 −DART_FS_WARMUP_Y 이전 회계연도는 TTM·전년대비에도 안 쓰인다.
#  ①의 U-MID 판정은 **가격패널만으로** 내려진다(20일 평균거래대금 랭크) — 재무를 보지
#  않으므로 순환참조가 없고, 미래 재무를 미리 들여다보는 일도 없다.
# ══════════════════════════════════════════════════════════════════════════════════════════
def dart_fs_scope_v3(ctx: dict, all_corps: Sequence[str], quiet: bool = False
                     ) -> Tuple[List[str], List[int], List[str]]:
    """(수집대상 corp_code, 연도, 우선순위 corp_code) 를 돌려준다.

    quiet=True 면 로그를 찍지 않는다 — 직원현황 단계가 우선순위만 빌려 쓸 때 쓴다."""
    y0 = as_ts(BACKTEST_START).year - int(DART_FS_WARMUP_Y)
    years = list(range(y0, as_ts(BACKTEST_END).year + 1))
    corps = [str(c) for c in all_corps]
    prio: List[str] = []
    try:
        pm = ctx["panel"]["monthly"]
        adv = col(pm, "adv20")
        rank = adv.groupby(pm["month"], observed=True).rank(ascending=False, method="first")
        in_band = rank.between(UMID_RANK_LO, UMID_RANK_HI) & (adv >= MIN_ADV_KRW)
        # 우선순위: 'U-MID 대역에 머문 달 수'가 많은 종목부터. 유동성 1등이 아니라
        # **실제로 담길 확률이 높은 종목**부터 채우는 것이 백테스트 커버리지에 직결된다.
        months_in = (pm.loc[in_band.fillna(False), "code"].value_counts())
        c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
               .set_index("code")["corp_code"].astype(str).to_dict())
        prio = [c2c[c] for c in months_in.index if c in c2c]
        if DART_FS_UNIVERSE_ONLY and prio:
            keep = set(prio)
            dropped = len(corps) - len([c for c in corps if c in keep])
            corps = [c for c in corps if c in keep]
            if not quiet:
                LOG.info(f"Tier-2 수집대상을 U-MID 대역 경험 종목 {len(corps):,}사로 좁힙니다 "
                         f"(제외 {dropped:,}사 — 전 기간 한 번도 투자가능 대역에 들지 못해 "
                         f"어떤 달에도 편입될 수 없는 종목입니다).")
    except Exception as e:                                          # noqa
        if not quiet:
            LOG.warn(f"U-MID 기반 Tier-2 범위 축소 실패({type(e).__name__}) — 전 종목으로 진행합니다.")
    n_reprt = 1 if DART_FS_FREQ == "annual" else 4
    est = len(corps) * len(years) * n_reprt
    cap = est if DART_FS_MAX_CALLS is None else min(est, int(DART_FS_MAX_CALLS))
    if not quiet:
        LOG.info(f"Tier-2 전체재무제표 계획: {len(corps):,}사 × {len(years)}년 × "
                 f"{n_reprt}보고서 = 최대 {est:,}건 → 이번 실행 상한 {cap:,}건 "
                 f"(≈{cap/5/60:.0f}분). 나머지는 Tier-1 주요계정으로 대체하고 재실행 시 이어받습니다.")
    if DART_FS_MAX_CALLS == 0:
        if not quiet:
            LOG.warn("DART_FS_MAX_CALLS=0 — Tier-2 를 건너뜁니다. 재고·매출채권·영업CF 가 결측이므로 "
                 "TP_I1/TP_I2(회계품질) 가 비활성화됩니다.")
        return [], years, prio
    return corps, years, prio


def offer_download_v3(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f                 # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
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


def downcast_floats(P: pd.DataFrame) -> pd.DataFrame:
    """float64 → float32 만. object→category 변환은 하지 않는다.

    ★ 코어의 downcast() 는 저카디널리티 object 를 category 로 바꾼다. 그러면 강건성 팔에서
      P.copy() 후 merge 할 때 category vs object dtype 불일치로 매칭이 0건이 되거나
      dtype 오류가 난다. 스코어링 패널은 여러 번 복제·재계산되므로 이 위험을 피한다.
    """
    for c in P.columns:
        if P[c].dtype.kind == "f":
            P[c] = pd.to_numeric(P[c], downcast="float")
    return P


def _flush_on_abort_v3():
    """중단 경로에서도 원장과 진단표를 반드시 남긴다.

    ★ 예전엔 DBUDGET.close() 와 report_http() 가 정상 종료 경로에만 있었다. 그래서
      ① 중단된 실행이 오늘 쓴 DART 호출이 파일에 기록되지 않아 다음 실행이 없는 예산을
         있다고 믿고 또 실패하고,
      ② '이번 실행에서 DART 요청을 한 건도 못 보냈다'를 보여줄 유일한 표(HTTP 감사)가
         하필 그게 가장 필요한 순간에 출력되지 않았다.
      중단은 진단 정보가 가장 필요한 순간이다. 그때 정보를 끊으면 안 된다.
    """
    try:
        if DBUDGET:
            DBUDGET.close()
    except Exception:
        pass
    try:
        report_http()
    except Exception:
        pass
    why = None
    try:
        why = dart_halt_reason()
    except Exception:
        pass
    if why:
        LOG.warn(f"참고 — 이번 실행의 DART 상태: {why}. "
                 f"위 표에서 dart 요청 수가 0 이면 '데이터가 없어서'가 아니라 "
                 f"'요청을 못 보내서'입니다. 한도는 매일 자정(KST)에 초기화됩니다.")
    try:
        VAULT.flush()
    except Exception:
        pass


def _enrich_research_bounded(nv: pd.DataFrame, sec: Optional[pd.DataFrame]) -> pd.DataFrame:
    """네이버 상세 보강을 시간 상한 안에서, 담을 수 있는 종목부터 수행한다."""
    if nv is None or nv.empty or not RESEARCH_ENRICH_MAX_MIN:
        if nv is not None and len(nv) and not RESEARCH_ENRICH_MAX_MIN:
            LOG.info("RESEARCH_ENRICH_MAX_MIN=0 — 상세 보강을 생략합니다. "
                     "목표주가는 한경 경로에서만 채워집니다(실측 수율이 0 이었던 단계입니다).")
        return nv if nv is not None else pd.DataFrame()
    obs = float(RATE_LIMIT_QPS.get("naver", 3.0)) or 3.0
    cap = max(0, int(RESEARCH_ENRICH_MAX_MIN * 60 * obs))
    if "code" in nv.columns and sec is not None and len(sec):
        try:
            # 담을 수 있는 종목(=거래대금이 있는 종목)을 앞으로 당긴다. 정렬만 바꾸므로
            # 상한에 걸려 잘려도 남는 것이 '쓸모 있는 쪽'이 된다.
            live = set(sec.loc[sec["delisting_date"].isna(), "code"].astype(str)) \
                if "delisting_date" in sec.columns else set(sec["code"].astype(str))
            key = (~nv["code"].astype(str).isin(live)).astype(int)
            nv = nv.assign(_pri=key).sort_values(
                ["_pri"] + (["date"] if "date" in nv.columns else []),
                ascending=[True] + ([False] if "date" in nv.columns else [])
            ).drop(columns=["_pri"]).reset_index(drop=True)
        except Exception:
            pass
    LOG.info(f"네이버 상세 보강 상한 {cap:,}건 (≈{RESEARCH_ENRICH_MAX_MIN}분 · "
             f"실측 {obs:.1f}건/초). 상장 종목·최신순으로 채웁니다. "
             f"이 단계는 U축 d1 보조이며 알파(한계임금)와 무관합니다.")
    return naver_enrich_detail(nv, limit=cap)


def announce_budget_v3():
    """수집을 시작하기 전에 '이번 실행이 몇 분짜리인지'를 먼저 못박아 보여준다.

    ★ 이 표가 없으면 곱셈으로 폭발한 잡 수가 tqdm ETA 로만 드러난다 — 이미 돌기 시작한
      뒤다. 4시간 계약(§12-6)은 사후 판정이 아니라 **사전 상한**이어야 한다.
    """
    fs_cap, emp_cap = DART_FS_MAX_CALLS, EMP_MAX_CALLS
    used = DBUDGET.n if DBUDGET else 0
    left = max(0, DART_DAILY_LIMIT - used)
    _n = lambda v: "무제한" if v is None else f"{int(v):,}"
    _m = lambda v, qps: "며칠" if v is None else f"{int(v)/qps/60:.0f}"
    rows = [
        ["L1.UNI  종목마스터·스냅샷", "-", "10", "pykrx/FDR/KIND"],
        ["L1.PX   일봉·거래대금", "-", "40", "실패종목 30일 음성캐시 → 재실행은 대폭 단축"],
        ["L1.EMP  직원현황(empSttus)", _n(emp_cap), _m(emp_cap, 8.0),
         "① 알파 원천 — 예산을 먼저 배정 · EMP_MAX_CALLS"],
        ["L1.DART Tier-1 주요계정(배치)", "≈2,100", "5", "100사/호출 — 전 종목 전 연도"],
        ["L1.DART Tier-2 전체재무제표", _n(fs_cap), _m(fs_cap, 5.0),
         f"② 남는 예산으로 · {DART_FS_FREQ} · DART_FS_MAX_CALLS"],
        ["L2~R    피처·백테스트·강건성", "-", "35", "네트워크 없음"],
    ]
    LOG.table(rows, ["단계", "DART 호출 상한", "예상(분)", "비고"], ["l", "r", "r", "l"],
              title="이번 실행의 수집 예산 (§10 · 총 예산 153분 / 킬 기준 4시간)")
    plan = sum(int(v) for v in (emp_cap, fs_cap) if v is not None) + 2100
    LOG.info(f"DART 일일 한도 {DART_DAILY_LIMIT:,} · 오늘 사용 {used:,} · 잔여 {left:,} → "
             f"이번 실행 계획 {plan:,}건. 한도에 닿으면 그 지점에서 깨끗이 멈추고 "
             f"수집분을 드라이브에 저장합니다. 재실행하면 이어받습니다.")
    if fs_cap is None or emp_cap is None:
        LOG.warn("호출 상한이 None 인 단계가 있습니다 — 콜드빌드는 며칠이 걸리며 §12-6 의 "
                 "4시간 계약 밖입니다. 4시간 안에 끝내려면 숫자를 넣으세요 "
                 "(권장: EMP_MAX_CALLS=14000, DART_FS_MAX_CALLS=12000).")
    if plan > left and left > 0:
        LOG.warn(f"계획 호출({plan:,})이 오늘 잔여 한도({left:,})를 넘습니다 — 우선순위 상위부터 "
                 f"채우고 한도에서 멈춥니다. 커버리지는 재실행할 때마다 올라갑니다.")
    return preflight_dart_v3()


def preflight_dart_v3() -> str:
    """이번 실행에서 DART 로 무엇을 할 수 있는지 **수집 시작 전에** 확정한다.

    ★ 왜 필요한가. 직전 실행은 0.35초 시점에 이미 '잔여 0'을 알고 있었는데도 그대로
      진행해, 16분 30초짜리 가격 수집을 끝낸 뒤 CANARY 에서 죽었다. 사용자는 17분을
      쓰고 아무 산출물도 받지 못했다. 알 수 있었던 사실로 나중에 죽는 것은 설계 결함이다.

    반환 "LIVE"(정상 수집) / "CACHE_ONLY"(캐시로 진행) / "BLOCKED"(진행 불가)
    """
    halt = dart_halt_reason()
    if not halt:
        return "LIVE"

    # ★★ 테이블은 서로 대체재가 아니다. ★★
    #   이 전략의 알파는 오직 한계임금(dart_employees_ext)이고, 재무 두 테이블은 **보조**다.
    #   예전 판정은 셋을 합산해 total>0 이면 진행했다. 그래서 재무 146만 행이 있고
    #   직원현황이 0행인 상태를 '캐시 충분'으로 읽고 27분을 태운 뒤, 정작 EMP 단계에서
    #   "3개 TP 가 모두 결측"을 선언했다. 알파가 없는 백테스트는 돌릴 이유가 없다.
    #   → 알파 필수(critical)와 보조(support)를 분리해 판정한다.
    CRITICAL = {"dart_employees_ext": "한계임금 — 이 전략의 유일한 알파 원천 (TP_N1·N2·N3)"}
    SUPPORT = {"dart_fnltt_raw": "전체재무제표 — TP_I1/I2/I4",
               "dart_multi_raw": "주요계정 — 유니버스·규모버킷·R3"}
    have = {}
    for t in list(CRITICAL) + list(SUPPORT):
        try:
            d = VAULT.get_table(t, scope="shared")
            have[t] = 0 if d is None else len(d)
        except Exception:
            have[t] = 0

    LOG.table([[t, "★알파" if t in CRITICAL else "보조", f"{have[t]:,}행",
                "사용 가능" if have[t] else "비어 있음",
                _trunc({**CRITICAL, **SUPPORT}[t], 44)]
               for t in list(CRITICAL) + list(SUPPORT)],
              ["공용 캐시 테이블", "역할", "보유", "이번 실행", "이 테이블이 없으면"],
              ["l", "c", "r", "c", "l"],
              title=f"DART 사전점검 — 지금 신규 수집 불가: {halt}")

    dead_alpha = [t for t in CRITICAL if not have[t]]
    if dead_alpha:
        LOG.error(
            f"★ 알파 원천이 비어 있습니다 — {dead_alpha} · {halt}\n"
            f"  재무 캐시가 {sum(have[t] for t in SUPPORT):,}행 있어도 **이 전략은 성립하지 않습니다.**\n"
            f"  한계임금 = Δ급여총액 / Δ직원수 이고, 그 입력이 empSttus 하나뿐입니다.\n"
            f"  이대로 진행하면 TP_N1·N2·N3 가 전부 결측이고, 남는 것은 CORE-D 5개 TP 뿐이라\n"
            f"  '전략 3' 이 아니라 '이름만 같은 다른 전략'의 백테스트가 나옵니다.\n"
            f"  그래서 가격·리포트 수집(실측 2시간)에 들어가기 전에 **지금** 멈춥니다.\n"
            f"\n"
            f"  선택지\n"
            f"    ① 한도 회복 후 재실행 — DART 한도는 매일 자정(KST)에 초기화됩니다.\n"
            f"       다음 실행은 EMP 에 예산을 **먼저** 배정하므로 한 번에 {EMP_MAX_CALLS:,}건까지 채웁니다.\n"
            f"    ② EMP 만 먼저 채우기 — DART_FS_MAX_CALLS=0 으로 두면 Tier-2 가 예산을 쓰지 않아\n"
            f"       직원현황이 최대 속도로 완성됩니다(권장).\n"
            f"    ③ CORE-D 단독으로 돌려보려면 REQUIRE_EMP_ALPHA=False 로 두세요.\n"
            f"       EMP-LITE 없는 축소판임이 모든 산출물에 명시됩니다.")
        if REQUIRE_EMP_ALPHA:
            raise KillCriteria(
                f"알파 원천(dart_employees_ext) 부재 · {halt} — 위 ①~③ 중 하나를 고른 뒤 재실행하세요. "
                f"2시간을 쓰고 '3개 TP 전부 결측'을 보는 대신 지금 멈춥니다.")
        LOG.warn("REQUIRE_EMP_ALPHA=False — EMP 없는 CORE-D 축소판으로 진행합니다.")
        return "CACHE_ONLY"

    if sum(have.values()) > 0:
        LOG.warn(
            f"DART 신규 수집은 못 하지만 알파 원천이 캐시에 {have['dart_employees_ext']:,}행 있어 "
            f"**캐시만으로 진행**합니다.\n"
            f"     · 캐시에 없는 (회사×연도)는 결측으로 남습니다 — 0 으로 채우지 않습니다.\n"
            f"     · CANARY 의 DART 항목은 판정 보류(SKIP)로 처리되며 킬 기준을 걸지 않습니다.\n"
            f"     · 내일(또는 한도 회복 후) 재실행하면 정확히 이 지점부터 이어받습니다.")
        return "CACHE_ONLY"

    LOG.error(
        f"DART 를 쓸 수 없고 공용 캐시도 비어 있습니다 — {halt}\n"
        f"  이 상태로 계속하면 가격 수집에만 15~40분을 쓰고 결국 재무·직원현황이 전부 비어\n"
        f"  백테스트가 성립하지 않습니다. 그래서 **지금** 멈춥니다.\n"
        f"\n"
        f"  선택지\n"
        f"    ① 한도 회복 후 재실행 — DART 한도는 매일 자정(KST)에 초기화됩니다.\n"
        f"       지금까지 받은 것은 전부 캐시에 있으므로 이어받습니다.\n"
        f"    ② 가격·유니버스만 먼저 채우기 — DART_FS_MAX_CALLS=0, EMP_MAX_CALLS=0 으로 두고\n"
        f"       실행하면 이 점검을 통과하고 가격 캐시를 미리 완성해 둘 수 있습니다.\n"
        f"    ③ RUN_MODE='CACHED' — 신규 수집 없이 캐시만으로 재현합니다.\n"
        f"    ④ 키가 문제라면 상단 DART_API_KEY 를 확인하세요 "
        f"(https://opendart.fss.or.kr → 인증키 신청/관리).")
    if (DART_FS_MAX_CALLS or 0) == 0 and (EMP_MAX_CALLS or 0) == 0:
        LOG.warn("DART 상한이 둘 다 0 이므로 애초에 DART 를 쓰지 않는 실행입니다 — 계속합니다.")
        return "CACHE_ONLY"
    raise KillCriteria(
        f"DART 사전점검 실패 — {halt} · 공용 캐시도 비어 있습니다. "
        f"위 선택지 중 하나를 고른 뒤 재실행하세요. "
        f"(17분을 쓰고 죽는 대신 지금 멈춥니다)")


# ── L1 수집 ─────────────────────────────────────────────────────────────────────────────────
def collect_all_v3(months: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}
    t_ing = time.time()
    ctx["dart_mode"] = announce_budget_v3()

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금 (다중소스 폴백 체인)", "L1", budget_s=2400):
        KRX.login()
        LOG.info(f"KRX 마켓플레이스 세션: {getattr(KRX, 'status', '미시도')}")
        # 야후 접미사를 미리 알려준다 — 모르면 종목당 .KS/.KQ 를 둘 다 때려 호출이 2배가 된다.
        try:
            _mk = ctx["sec"].dropna(subset=["code"]).drop_duplicates("code")
            _s = _mk["market"].astype(str).str.upper()
            YF_SUFFIX_HINT.update(dict(zip(
                _mk["code"].astype(str),
                np.where(_s.str.contains("KOSDAQ|KSQ|코스닥"), ".KQ", ".KS"))))
        except Exception:
            pass
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END, sec=ctx["sec"])
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L0.CANARY", "CANARY K1~K9", "L0", budget_s=2100):
        ctx["canary"] = run_canary(ctx["sec"],
                                   canary_sample(ctx["sec"], ctx["panel"]["monthly"]))

    with PIPE.stage("L1.FLOW", "기관·외국인 수급 (U축 d3)", "L1", budget_s=1200, critical=False):
        ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(), BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.EMP", "DART 직원현황(확장) · C15 한계임금", "L1",
                    budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        # ★ 상한을 '아직 제출되지 않은 회계연도' 앞에서 끊는다.
        #   사업보고서는 다음 해 3~4월에 나오므로 FY(올해)는 존재할 수 없다. 그런데 잡은
        #   연도 내림차순이라 그 없는 연도가 **큐 맨 앞**에 온다 — 3,366건(상한의 24%)을
        #   확실히 빈 응답에 먼저 태우고 나서야 쓸 수 있는 연도에 도달했다.
        _y_max = min(as_ts(BACKTEST_END).year, _dt.date.today().year) - 1
        eyears = list(range(as_ts(BACKTEST_START).year - EMP_YEARS_BACK, _y_max + 1))
        LOG.info(f"직원현황 대상 회계연도 {eyears[0]}~{eyears[-1]} "
                 f"(FY{_y_max + 1} 이후는 아직 제출 전이라 제외 — 없는 연도를 먼저 묻지 않습니다)")
        # ★ 한계임금이 이 전략의 알파 원천이므로 DART 일일예산을 **여기에 먼저** 배정한다.
        #   (Tier-2 전체재무제표는 남는 예산으로 채우고, 부족분은 Tier-1 주요계정이 받친다)
        emp_corps, _, emp_prio = dart_fs_scope_v3(ctx, corps, quiet=True)
        if not (EMP_UNIVERSE_ONLY and emp_corps):
            emp_corps = corps          # 축소 실패 또는 사용자가 끈 경우 → 전 종목
        else:
            LOG.info(f"직원현황 수집대상 {len(emp_corps):,}사 "
                     f"(전체 {len(corps):,}사 중 U-MID 대역을 한 번이라도 경험한 종목). "
                     f"셀 정규화도 U-MID 패널 안에서만 이뤄지므로 제외분은 스코어에 쓰이지 않습니다.")
        E = fetch_emp_status(emp_corps, eyears, priority=emp_prio, max_calls=EMP_MAX_CALLS)
        ctx["emp_raw"] = E
        S = build_emp_sensors(E)
        ctx["emp_sensors"] = S
        ok, msg = test_c15(S)
        (LOG.ok if ok else LOG.error)(f"C15 자가검정 — {msg}")
        if not ok and STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"C15 계약 위반: {msg}")
        if len(S):
            PIT.register("emp_sensors",
                         pit_frame(S, "period_end", "knowledge_date", source="dart"),
                         key_cols=["corp_code"])
            VAULT.put_table("emp_sensors_annual", S, scope="shared", domain="dart",
                            source="v3 EMP-LITE 연도 센서 (C15 적용) — 타 전략 재사용 가능")

    with PIPE.stage("L1.DART", "DART 재무 · 공시목록", "L1", budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        # ── Tier-1(배치): 전 종목 · 전 연도. 100사/호출이므로 싸다. 항상 전부 받는다.
        multi = fetch_dart_multi_accounts(corps, years)
        # ── Tier-2(단건): 기업×연도×보고서로 곱해진다 → 반드시 범위를 좁히고 상한을 건다.
        fs_corps, fs_years, prio = dart_fs_scope_v3(ctx, corps)
        fs = fetch_dart_financials(fs_corps, fs_years, priority=prio,
                                   max_calls=DART_FS_MAX_CALLS, freq=DART_FS_FREQ)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        dis = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["fin"], ctx["disclosures"] = fin, dis
        # ★ 빈 경로의 tidy_financials 는 PIT 컬럼조차 없는 3열짜리 프레임을 돌려준다.
        #   그대로 register 하면 KeyError 로 죽으므로 컬럼 존재를 먼저 확인한다.
        if len(fin) and all(c in fin.columns for c in PIT_COLS):
            PIT.register("dart_financials", fin, key_cols=["corp_code"])
        else:
            LOG.warn("DART 재무가 비어 PIT 등록을 건너뜁니다 — CORE-D TP 는 전부 결측이 됩니다.")

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장 구축", "L1",
                    budget_s=3600, critical=False):
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        # ★ 캐시를 읽어 놓고도 전 구간을 다시 긁고 있었다. "재수집하지 않습니다" 로그는
        #   재수집이 **끝난 뒤에** 찍혔다(13분 낭비 × 매 실행). 가격·공시는 이미 증분인데
        #   리포트만 전량 재수집이었다 → 캐시 최신일 이후만 받는다.
        r_start = BACKTEST_START
        if cached is not None and len(cached) and "date" in cached.columns:
            try:
                _mx = as_ts_series(cached["date"]).max()
                if pd.notna(_mx):
                    # 7일 겹쳐 받는다 — 경계일에 늦게 올라온 리포트를 놓치지 않기 위함.
                    r_start = max(as_ts(BACKTEST_START),
                                  _mx - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
                    if r_start != BACKTEST_START:
                        LOG.info(f"보고서 증분 수집 — 캐시 최신 {_mx:%Y-%m-%d} 이후만 받습니다 "
                                 f"({r_start} ~). 전 구간 재수집이면 실측 13분이 매번 듭니다.")
            except Exception:
                pass
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                     "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                     "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
            if "hankyung" in RESEARCH_SOURCES:
                _hk = hankyung_collect(r_start, BACKTEST_END)
                if not len(_hk) and r_start == BACKTEST_START:
                    # ★ 전 구간을 요청했는데 0건이면 소스 장애다. 예전엔 LOG.ok 로 찍혀
                    #   초록 체크마크 뒤에 숨었다. 한경은 analyst_raw 의 **유일한** 원천이라
                    #   0건이면 애널리스트 원장 전체가 빈다.
                    LOG.error("한경컨센서스 0건 — 전 구간을 요청했는데 한 건도 받지 못했습니다. "
                              "위 'HTTP 수집 감사' 표에서 hankyung 의 403/404 건수를 확인하세요. "
                              "403 이면 차단(잠시 뒤 재시도), 404 면 엔드포인트 변경입니다. "
                              "이 소스가 비면 애널리스트 원장·목표주가가 통째로 비어 "
                              "다중소스 원장연결 감사가 무의미해집니다.")
                frames.append(_hk)
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(r_start, BACKTEST_END)
                # ★ 상세 보강은 리포트 1건당 1회 요청이라 **이 전략에서 가장 비싼 단계**다.
                #   실측: 45,000건 대상 → 20,000건만 해도 ETA 1시간 44분(2.99 it/s).
                #   §10 의 수집 총예산이 95분인데 한 보조축 보강이 그 배를 먹는다.
                #   게다가 리허설·실행 모두 '목표주가 0건 추가 확보' 였다 — 수율이 0 이다.
                #   → 시간 상한을 걸고, 그 안에서 **U-MID 대역 종목부터** 보강한다.
                #     (담을 수 없는 종목의 목표주가는 스코어에 쓰이지 않는다)
                nv = _enrich_research_bounded(nv, ctx.get("sec"))
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.ok(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                   f"(신규는 {r_start} 이후만 받았습니다)")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"]) if frames else pd.DataFrame()
        if len(rep):
            if RESEARCH_DOWNLOAD_PDF:
                rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
                if "pdf_target" in rep.columns:
                    fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                    if fill.any():
                        rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                        LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
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
        else:
            ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
            LOG.info("리포트 원장이 비었습니다 — U 는 스펙 §8 대로 d1·d3 로만 구성되므로 "
                     "전략 자체는 온전합니다(원장은 감사·공용재활용 목적).")

    runtime_mark("수집", time.time() - t_ing)
    return ctx


# ── L1 피처 ─────────────────────────────────────────────────────────────────────────────────
def build_features_v3(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe", dict]:
    t_l1 = time.time()
    with PIPE.stage("L1.PANEL", "피처 패널 조립 (L1 센서)", "L1", budget_s=1800):
        uni = Universe(ctx["sec"],
                       ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel_v3(uni, months, ctx["panel"]["monthly"])
        P = attach_pit_sources(P, ctx["sec"])
        P = apply_umid(P, uni)
        P = build_cells_v3(P, ctx["sec"])
        P = core_d_sensors(P, ctx)

        # §6 커버리지 감사 → 판정 → EMP 유효 시작월
        C = emp_coverage_audit(ctx.get("emp_sensors", pd.DataFrame()),
                               umid_by_year(P), umid_corps_by_year(P))
        emp_start, verdict = coverage_verdict(C)
        LOG.info(f"§6 판정 — {verdict}")
        ctx["emp_coverage"], ctx["emp_coverage_verdict"] = C, verdict

        P = emp_lite_sensors(P, emp_start)
        P = axis_U_v3(P, ctx.get("flows"))

        # ★ 대역 밖은 여기서 제외한다. TP 랭크가 '고를 수 있었던 종목' 안에서 매겨져야 한다.
        #   (센서 계산은 전 종목으로 끝낸 뒤에 자른다 — 먼저 자르면 12개월 차분이 깨진다)
        #   ★ 자르기 **직전** 패널을 보관한다. 스몰캡 비교 팔이 같은 센서 위에서 대역만
        #     바꿔 다시 자르기 위함이다. 센서를 다시 계산하지 않으므로 두 팔의 차이는
        #     오직 '규모 대역' 하나뿐임이 구조적으로 보장된다.
        ctx["panel_full"] = P.copy()
        before = len(P)
        P = P[P["u_mid"]].reset_index(drop=True)
        LOG.info(f"U-MID 유니버스로 스코어링 패널 확정 — {before:,} → {len(P):,}행")
        P = downcast_floats(P)
        LOG.ok(f"피처 패널 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 panel")
    runtime_mark("L1.센서+커버리지", time.time() - t_l1)
    return P, uni, ctx


def score_and_backtest_v3(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex,
                          uni: "Universe") -> Tuple[pd.DataFrame, dict, Callable]:
    t_l2 = time.time()
    with PIPE.stage("L2.SCORE", "TP 조립 · 거부권 · Signal", "L2", budget_s=300):
        P = build_tps(P)
        P = apply_vetoes_v3(P, ctx)
        P = assemble_score_v3(P)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        P[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "n_tp") if c in P.columns]],
                        scope="private", domain="scores", source="L2")

    def _run(pp, label="run", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else months,
                            uni, ctx["sec"], apply_costs=apply_costs, label=label)

    with PIPE.stage("L3.BT", "백테스트", "L3", budget_s=300):
        bt = _run(P, label=STRATEGY_ID)
    runtime_mark("L2+L3.백테스트", time.time() - t_l2)
    return P, bt, _run


def run_smallcap_arm_v3(ctx: dict, months: pd.DatetimeIndex, uni: "Universe",
                        bench: Dict[str, pd.Series]) -> Optional[dict]:
    """같은 신호·같은 규칙을 **규모 대역만 바꿔** 다시 돌린다.

    ★ 왜 같은 실행 안에서 도는가. 두 팔이 같은 수집물·같은 센서·같은 시드를 쓰므로
      성과 차이의 원인이 '규모 대역' 하나로 특정된다. 따로 실행하면 수집 시점이 달라
      무엇 때문에 달라졌는지 말할 수 없게 된다.
    ★ TP·셀·랭크는 **대역 안에서 다시** 매긴다. 중형주 랭크를 소형주에 그대로 쓰면
      소형주가 전부 하위권으로 몰려 아무것도 못 고른다.
    """
    if not RUN_SMALLCAP_ARM:
        return None
    PF = ctx.get("panel_full")
    if PF is None or PF.empty:
        LOG.warn("스몰캡 팔 — 전체 패널이 없어 건너뜁니다.")
        return None
    with PIPE.stage("L3.SMALL", f"스몰캡 비교 팔 (랭크 [{SMALL_RANK_LO},{SMALL_RANK_HI}])",
                    "L3", budget_s=600, critical=False):
        S = apply_umid(PF.copy(), uni, band="SMALL")
        S = S[S["u_mid"]].reset_index(drop=True)
        if S.empty or S["month"].nunique() < 24:
            LOG.warn(f"스몰캡 대역에 남는 행이 부족합니다({len(S):,}행 · "
                     f"{S['month'].nunique() if len(S) else 0}개월) — 비교 팔을 건너뜁니다. "
                     f"거래대금 하한 {MIN_ADV_KRW/1e8:.0f}억을 하위 대역이 못 넘기는 것이 "
                     f"보통이며, 이 사실 자체가 '소형주는 담기 어렵다'는 결과입니다.")
            return None
        S = downcast_floats(S)
        S = build_tps(S)
        S = apply_vetoes_v3(S, ctx)
        S = assemble_score_v3(S)
        bt_s = run_backtest(S, months, uni, ctx["sec"], apply_costs=True,
                            label=f"{STRATEGY_ID}__SMALLCAP")
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}_smallcap",
                        S[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "n_tp") if c in S.columns]],
                        scope="private", domain="scores", source="L3 스몰캡 팔")
        return {"panel": S, "bt": bt_s}


def report_arm_comparison_v3(bt_main: dict, arm: Optional[dict],
                             bench: Dict[str, pd.Series]) -> None:
    """메인(U-MID) vs 스몰캡 성과를 나란히 출력한다. 유리하게 해석하지 않는다."""
    if not arm:
        return
    rows = []
    for name, b, lo, hi in ((f"메인 U-MID", bt_main, UMID_RANK_LO, UMID_RANK_HI),
                            ("스몰캡", arm["bt"], SMALL_RANK_LO, SMALL_RANK_HI)):
        R = b.get("returns")
        if R is None or R.empty:
            continue
        st = perf_stats(R)
        _f = lambda k, fmt: (format(st[k], fmt) if k in st and np.isfinite(st.get(k, np.nan))
                             else "-")
        rows.append([name, f"[{lo},{hi}]", _f("CAGR", ".2%"), _f("Sharpe", ".2f"),
                     _f("MDD", ".1%"), _f("승률", ".0%"), _f("t통계량(HAC)", ".2f"),
                     _f("평균종목수", ".1f"), f"{len(R)}개월"])
    if not rows:
        return
    LOG.table(rows, ["팔", "규모랭크", "CAGR", "Sharpe", "MDD", "승률", "t(HAC)",
                     "평균종목", "관측"],
              ["l", "c", "r", "r", "r", "r", "r", "r", "r"],
              title="규모 대역 비교 — 같은 신호·같은 규칙, 대역만 다름")
    LOG.info("두 팔은 동일한 수집물·센서·시드를 씁니다. 따라서 차이의 원인은 규모 대역 하나로 "
             "특정됩니다. 다만 스몰캡은 거래비용·시장충격이 실제로 더 크므로, 이 표의 "
             "스몰캡 우위는 비용 가정이 낙관적일 때 과대평가됩니다(R8 비용민감도를 함께 보세요).")


# ── 산출물 ──────────────────────────────────────────────────────────────────────────────────
def persist_outputs_v3(P: pd.DataFrame, bt: dict, ctx: dict, bench: Dict[str, pd.Series],
                       t_all: float) -> List[str]:
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []

    def _w(fname: str, fn: Callable[[str], None]):
        p = os.path.join(outdir, fname)
        try:
            fn(p)
            outs.append(p)
        except Exception as e:                                    # noqa
            LOG.warn(f"산출물 저장 실패 {fname} ({type(e).__name__}: {e})")

    _w(f"canary_report_{stamp}.md", lambda p: atomic_write_text(p, canary_report_md()))
    _w(f"r2n_verdict_{stamp}.md", lambda p: atomic_write_text(p, r2n_verdict_md()))
    C = ctx.get("emp_coverage")
    if C is not None and len(C):
        _w(f"emp_coverage_{stamp}.csv",
           lambda p: C.to_csv(p, index=False, encoding="utf-8-sig"))
    cal = ctx.get("policy")
    if cal is not None and len(cal):
        _w(f"r10_policy_calendar_{stamp}.csv",
           lambda p: cal.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"returns_{stamp}.csv",
       lambda p: bt["returns"].to_csv(p, index=False, encoding="utf-8-sig"))
    if len(bt.get("holdings", pd.DataFrame())):
        _w(f"holdings_{stamp}.csv",
           lambda p: bt["holdings"].to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"panel_{stamp}.parquet", lambda p: atomic_write_parquet(P, p))

    full = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "window": [BACKTEST_START, BACKTEST_END],
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "performance": {k: (float(v) if isinstance(v, (int, float, np.floating)) and
                            np.isfinite(v) else None)
                        for k, v in (perf_stats(bt["returns"]) or {}).items()},
        "right_tail": {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v))
                       for k, v in (right_tail_contribution(bt) or {}).items()},
        "benchmarks": {},
        "canary": CANARY_RESULTS,
        "contracts": CONTRACT_V3,
        "robustness": ROBUST_V3,
        "r2n": R2N_VERDICT,
        "c15": C15_STATS,
        "coverage_verdict": ctx.get("emp_coverage_verdict", ""),
        "active_tp": globals().get("ACTIVE_TP_COLS", []),
        "runtime_minutes": (time.time() - t_all) / 60.0,
    }
    for name, s in (bench or {}).items():
        try:
            bs = perf_stats(pd.DataFrame({"month": s.index, "ret": s.to_numpy(dtype=float),
                                          "n": 0, "turnover": 0.0, "cost": 0.0}))
            full["benchmarks"][name] = {k: (float(v) if isinstance(v, (int, float, np.floating))
                                            and np.isfinite(v) else None)
                                        for k, v in bs.items()}
        except Exception:
            continue
    _w(f"backtest_full_{stamp}.json",
       lambda p: atomic_write_text(p, json.dumps(full, ensure_ascii=False, indent=2, default=str)))
    RT = report_runtime_v3(t_all)
    _w(f"runtime_{stamp}.csv", lambda p: RT.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"log_{stamp}.txt", lambda p: atomic_write_text(p, "\n".join(LOG.buffer)))

    VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                    domain="backtest", source=STRATEGY_ID)
    VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
    if DBUDGET:
        DBUDGET.close()
    VAULT.report()
    return outs


# ── main ────────────────────────────────────────────────────────────────────────────────────
def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["DART 키", "입력됨" if DART_API_KEY else "없음 (핵심 입력 — 넣으면 살아납니다)"],
               ["KRX 마켓플레이스", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW)
                else "없음 (가격은 pykrx→FDR→네이버→yfinance 체인으로 대체)"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    if pykrx_stock is None:
        LOG.warn(
            "pykrx 를 쓸 수 없습니다 — 결과에 실제로 영향이 갑니다. 두 가지가 죽습니다:\n"
            "     ① 기관·외국인 수급 → U축 d3 가 전 기간 결측 (U 는 d1 하나로만 구성됩니다)\n"
            "     ② 특정일 상장목록 스냅샷 → PIT 유니버스가 KIND·FDR 경로에만 의존합니다\n"
            "   가격 자체는 FDR→네이버→yfinance 로 대체되지만 3~4배 느립니다. "
            f"현재 파이썬 {ENV['python']} 에 설치 가능한 휠이 없으면 3.11~3.12 환경을 권합니다.")

    t_l0 = time.time()
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root, mode = mount_cache_v3()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        # 중복 경로를 미리 제거한다(ADOPT_DIRS[0] 이 ROOT 와 같으면 같은 트리를 두 번 훑는다)
        # ★ 헤더의 ADOPT 경로는 Colab 기준(/content/...)이라 JupyterLab 에서는 하나도 안 맞는다.
        #   실제로 붙어 있는 캐시 루트의 형제 폴더(research/reports/consensus)도 함께 훑어
        #   '드라이브에 이미 모아둔 리포트'를 어느 환경에서든 등록만 하고 재사용한다.
        _sib = os.path.dirname(VAULT.root)
        adopt = list(dict.fromkeys(os.path.abspath(os.path.expanduser(d)) for d in (
            list(GDRIVE_ADOPT_DIRS) + [VAULT.root] +
            [os.path.join(_sib, n) for n in ("research", "reports", "consensus", "tcd_cache")]
        ) if d))
        adopt = [d for d in adopt if os.path.isdir(d)]
        VAULT.adopt_scan(adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET
        # ★ 알파 몫을 먼저 떼어 둔다. 이것이 없어서 Tier-2 재무가 일일 한도를 먼저 다 쓰고
        #   직원현황이 3회 실행 내내 0행이었다. 예약분은 EMP 만 인출할 수 있다.
        if EMP_RESERVED_CALLS:
            DBUDGET.reserve(EMP_PURPOSE, int(EMP_RESERVED_CALLS))
            LOG.info(f"DART 예산 예약 — 직원현황(알파) {int(EMP_RESERVED_CALLS):,}건. "
                     f"다른 단계는 나머지({DBUDGET.left(None):,}건)만 씁니다.")

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 (C1·C2·C13·C15 · 원칙1~7)", "L0", budget_s=180):
        run_contracts_v3(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest_v3(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=900):
        run_rehearsal(strict=True)
    runtime_mark("L0.준비", time.time() - t_l0)

    months = month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_flow(); report_runtime_v3(t_all)
        report_dataflow_map_v3()
        return {"mode": "SMOKE"}

    ctx = collect_all_v3(months)

    with PIPE.stage("L1.AUDIT", "다중소스 원장 연결 감사", "L1", budget_s=180, critical=False):
        report_ledger_v3(ctx)

    P, uni, ctx = build_features_v3(ctx, months)
    P, bt, _run = score_and_backtest_v3(P, ctx, months, uni)
    arm = run_smallcap_arm_v3(ctx, months, uni, {})

    with PIPE.stage("L2.POLICY", "정책 캘린더", "L2", budget_s=60, critical=False):
        cal = build_policy_calendar_v3()
        report_policy_v3(cal, months)
        ctx["policy"] = cal

    bench: Dict[str, pd.Series] = {}
    with PIPE.stage("L6.PERF", "성과 검증 (자체측정 벤치마크 대비)", "L6", budget_s=300):
        bench = R0_benchmark(P, bt, months)
        report_performance_v3(bt, bench)
        report_arm_comparison_v3(bt, arm, bench)
        # ★ 감쇠 감사는 강건성 재실행(백테스트 10여 회)이 섞이기 전에 뽑는다.
        uni.report_attrition()
        uni.attrition = []

    t_rob = time.time()
    with PIPE.stage("L5.ROBUST", "강건성 검사", "L5", budget_s=3 * 3600, critical=False):
        try:
            R1_leakage(P, months, _run)
            R2N_kill_gate(P, _run)
            R3_orthogonal(P, _run)
            R5_ablation(P, _run)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R10_policy_falsify(P, ctx.get("policy", build_policy_calendar_v3()), months, _run)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness_v3()
    runtime_mark("R-SUITE", time.time() - t_rob)

    with PIPE.stage("L6.REPORT", "해석표 · 진단 카드", "L6", budget_s=300, critical=False):
        report_interpretation_v3(P)
        diagnostic_card_v3(P, bt, ctx["sec"])

    outs: List[str] = []
    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = persist_outputs_v3(P, bt, ctx, bench, t_all)
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    report_dataflow_map_v3()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시 — ① 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 U축 d1 의 E 는 "
             "후행 12M 순이익 대리를 씁니다. ② U-MID 의 규모 랭크는 시가총액이 아니라 20일 "
             "평균거래대금 랭크입니다(시총 PIT 복원 불가에 따른 치환). ③ empSttus 는 별도 기준에 "
             "가까우므로 1인당 부가가치의 분자도 별도(OFS) 우선으로 맞췄으나, 연결 비중이 큰 "
             "지주회사에서는 오차가 큽니다. 숨기지 않고 여기에 명시합니다.")
    offer_download_v3(outs)
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_V3, "r2n": R2N_VERDICT}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§12 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        _flush_on_abort_v3()
        try:
            report_robustness_v3()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        _flush_on_abort_v3()
        PIPE.report_stages(); PIPE.report_flow()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 정확히 이 지점부터 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
