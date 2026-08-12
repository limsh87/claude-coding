# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  사전등록 상수 (SPEC) + 동결 장치                                                          ║
# ║                                                                                          ║
# ║  명세서 §8 금지사항은 "그러지 않겠다"는 약속이 아니라 구조여야 한다.                        ║
# ║   · SPEC 은 SpecLock 으로 감싼다 → 실행 중 대입하면 즉시 예외                              ║
# ║   · 민감도 격자는 팩터당 4개로 상한이 걸려 있다 → 5개째를 등록하면 예외                     ║
# ║   · OOS 구간은 OOSSeal 이 잠그고, Step 7 에서만 열린다 → 조기 열람이 예외로 잡힌다          ║
# ║   · 문서 SHA256 을 run_log 에 남긴다 (선행 문서 규약)                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


class SpecViolation(Exception):
    """사전등록 위반. 코드를 고치기 전에 명세 개정(버전 상향)을 먼저 하라는 뜻."""


class SpecLock(dict):
    """한 번 정해진 값은 실행 중 바뀌지 않는다."""

    def __init__(self, name: str, d: dict):
        super().__init__(d)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_frozen", True)

    def __setitem__(self, k, v):
        if getattr(self, "_frozen", False):
            raise SpecViolation(
                f"[{self._name}] 사전등록 상수 '{k}' 를 실행 중에 바꾸려 했습니다. "
                f"명세서 §8-3(1차 결과를 본 뒤 재조정 금지) 위반입니다. "
                f"정말 바꿔야 한다면 코드가 아니라 명세서 버전을 올리고 그 이력을 남기세요.")
        super().__setitem__(k, v)

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# ── §1 유니버스 ─────────────────────────────────────────────────────────────────────────────
SPEC_UNIV = SpecLock("UNIVERSE", dict(
    min_amount_krw=GATE_MIN_AMOUNT,      # 거래대금 ≥ 1억원
    min_listing_days=GATE_MIN_LIST_DAYS,  # 상장 ≥ 180일
    main_n=UNIV_MAIN_N,                   # 시총 하위 250 (주)
    aux_n=UNIV_AUX_N,                     # 시총 하위 500 (보조)
    weighting="EW",                       # 동일가중
))

# ── §4 공통 규약 ────────────────────────────────────────────────────────────────────────────
SPEC_N_VALUES   = (30, 50, 80)     # 랭킹형·이벤트형 N. 주 명세는 50
SPEC_N_PRIMARY  = 50
SPEC_UNCOV_MODES = ("neutral", "exclude")   # 미커버 처리 2방식 — 둘 다 산출
#   neutral : 선별 대상에서 빼지 않는다 — 랭킹형은 중앙값 점수, 필터형은 통과(유지)
#   exclude : 미커버 종목을 후보에서 제외한다
SPEC_PIT_LAG_BDAYS = 1                   # 공시 접수일 + 1영업일부터 사용 가능

# ── §3 Phase 0 통과 기준 ────────────────────────────────────────────────────────────────────
SPEC_COV = SpecLock("PHASE0", dict(pass_median=80, hold_median=40))

# ── §6.1 표본 분할 ──────────────────────────────────────────────────────────────────────────
SPEC_IS_FRACTION = 0.60           # 탐색구간(IS) = 앞 60%
SPEC_WF_TRAIN_M  = 36             # walk-forward 학습 36개월
SPEC_WF_TEST_M   = 12             # 검정 12개월, 12개월 롤

# ── §6.2 시행 횟수 (다중검정 통제) ──────────────────────────────────────────────────────────
#   4팩터 × (주명세 1 + 민감도 4) × N값 3개 × 미커버처리 2방식 = 120
#   ★ DSR 계산 시 팩터별이 아니라 반드시 이 전체값을 쓴다(§6.2).
SPEC_TRIALS_TOTAL = 4 * 5 * 3 * 2

# ── §6.3 판정 게이트 ────────────────────────────────────────────────────────────────────────
SPEC_GATE = SpecLock("GATES", dict(
    g1_random_pct=0.95,          # B4 무작위 분포 상위 5% 밖
    g2_excess_cagr=0.030,        # B2 대비 순수익 초과 CAGR ≥ +3.0%p (AUM 1억)
    g2_aum_krw=100_000_000,
    g3_drop_best_years=2,        # 최고 2개 연도 제외 후에도 초과수익 > 0
    g4_oos_ratio=0.50,           # OOS 초과수익 ≥ IS 의 50%
    g5_dsr_min=0.0, g5_pbo_max=0.5,
    g6_quintile_monotone=True,   # 랭킹형 한정
    g7_placebo_shift_bdays=-60,  # P1: 신호일 −60영업일 시프트
))
SPEC_B4_SIMS = 1000              # §2 B4: 무작위 N종목 1,000회 시뮬

# ── §5 비용 모형 ────────────────────────────────────────────────────────────────────────────
#   증권거래세: 연도별 실제 세율표. 하드코딩 금지 → 테이블로 관리하고 근거를 함께 남긴다.
#   (매도 시에만 부과. 코스피는 농특세 0.15% 포함 실효세율, 코스닥은 거래세만)
SPEC_TAX_TABLE = [
    # (시행 시작연도, KOSPI 매도 실효율, KOSDAQ 매도 실효율, 근거)
    (2016, 0.00300, 0.00300, "증권거래세법 — 유가증권 0.15%+농특세 0.15%, 코스닥 0.30%"),
    (2019, 0.00300, 0.00250, "2019.06 인하 — 유가증권 0.10%+농특세 0.15%, 코스닥 0.25%"),
    (2021, 0.00230, 0.00230, "2021.01 인하 — 유가증권 0.08%+농특세 0.15%, 코스닥 0.23%"),
    (2023, 0.00200, 0.00200, "2023.01 인하 — 유가증권 0.05%+농특세 0.15%, 코스닥 0.20%"),
    (2024, 0.00180, 0.00180, "2024.01 인하 — 유가증권 0.03%+농특세 0.15%, 코스닥 0.18%"),
    (2025, 0.00150, 0.00150, "2025.01 인하 — 유가증권 0.00%+농특세 0.15%, 코스닥 0.15%"),
]
SPEC_COST = SpecLock("COST", dict(
    commission_roundtrip=0.0003,     # 위탁수수료 왕복 0.03%
    spread_fallback_bp={             # 종목별 실측 미가용 시 시총분위별 보수 고정값(편도 bp)
        1: 90.0, 2: 70.0, 3: 55.0, 4: 40.0, 5: 30.0},
    spread_fallback_basis="마이크로캡 호가단위/가격 기반 보수 추정 — 실측 대체 시 로그에 명시",
    impact_coef=0.10,                # 시장충격 = coef × sqrt(주문금액 / ADV)
    slippage_bp=15.0,                # 체결가정: 리밸일 종가 대비 불리한 방향 고정 슬리피지
))
SPEC_AUM_LADDER = (10_000_000, 100_000_000, 300_000_000, 1_000_000_000)   # §5 용량 시뮬

# ── §4 팩터별 신호 상수 ─────────────────────────────────────────────────────────────────────
SPEC_F1 = SpecLock("F1", dict(
    horizon_m=12,                    # 제거 유효기간 12개월
    e1_private_only=True,            # E1: CB/BW 발행결정 — 사모 한정
    e4_refix_drop=-0.20,             # E4: 현재가 ≤ 최초 전환가 × (1−0.20)
))
SPEC_F2 = SpecLock("F2", dict(
    lookback_m=6,                    # 직전 6개월 순매수 > 0
    rank_var="net_buy_over_mktcap",  # 랭킹 변수: 순매수금액 / 시가총액
    reasons_include=("장내매수",),
    reasons_exclude=("주식매수선택권", "스톡옵션", "상속", "증여", "담보", "무상증자",
                     "주식배당", "장외매수", "신주인수권", "전환", "합병", "대여", "반환"),
))
SPEC_F3 = SpecLock("F3", dict(
    illiq_window_d=60,               # ILLIQ = mean(|r|/거래대금) over 60일
    delta_lag_d=120,                 # ΔILLIQ = log ILLIQ(t) − log ILLIQ(t−120일)
    redundancy_rho=0.50,             # |ρ| > 0.5 → F3 기각
))
SPEC_F4 = SpecLock("F4", dict(
    ratio_threshold=0.20,            # 계약금액 / 직전연도 매출액 ≥ 0.20
    horizon_m=12,                    # 신호 유효기간 12개월, 복수 계약 합산
    track_cancel=True,               # 정정·해지 추적 — 누락하면 명백한 미래참조
))

# ── §4 민감도 격자 (팩터당 총 4개. 초과 금지 — 등록기가 강제한다) ───────────────────────────
SENS_MAX_PER_FACTOR = 4


class SensitivityGrid:
    """민감도 축 등록기. 팩터당 4개를 넘기면 예외 — §8-2 를 구조로 막는다."""

    def __init__(self):
        self._g: Dict[str, List[dict]] = {}

    def add(self, factor: str, key: str, desc: str, **override):
        g = self._g.setdefault(factor, [])
        if any(x["key"] == key for x in g):
            return
        if len(g) >= SENS_MAX_PER_FACTOR:
            raise SpecViolation(
                f"[{factor}] 민감도 격자가 {SENS_MAX_PER_FACTOR}개를 넘었습니다 "
                f"(추가 시도: {key}). 명세서 §8-2 위반 — 격자를 늘리려면 명세를 개정하세요.")
        g.append(dict(key=key, desc=desc, override=override))

    def get(self, factor: str) -> List[dict]:
        return list(self._g.get(factor, []))

    def all_variants(self, factor: str) -> List[dict]:
        """주 명세(primary) 1개 + 민감도 4개 = 5개."""
        return [dict(key="primary", desc="주 명세", override={})] + self.get(factor)


SENS = SensitivityGrid()

# F1 — 유효기간 6/24개월(2) + E1 사모+공모 확대(1) + E4 임계 −30%(1)
SENS.add("F1", "horizon_6m",  "유효기간 6개월",            horizon_m=6)
SENS.add("F1", "horizon_24m", "유효기간 24개월",           horizon_m=24)
SENS.add("F1", "e1_all",      "E1 사모+공모 전체로 확대",  e1_private_only=False)
SENS.add("F1", "e4_m30",      "E4 임계 −30%",              e4_refix_drop=-0.30)
# F2 — 룩백 3/12개월(2) + 대표이사·최대주주 본인 한정(1) + 랭킹변수 ADV 기준(1)
SENS.add("F2", "lookback_3m",  "룩백 3개월",               lookback_m=3)
SENS.add("F2", "lookback_12m", "룩백 12개월",              lookback_m=12)
SENS.add("F2", "ceo_only",     "대표이사·최대주주 본인 한정", ceo_only=True)
SENS.add("F2", "rank_by_adv",  "랭킹변수 = 순매수금액/일평균거래대금",
         rank_var="net_buy_over_adv")
# F3 — 윈도 30d/120d(2) + 수준(level) 대조군(1, 반증용) + 거래대금 변화율 단순판(1)
SENS.add("F3", "win_30d",   "ILLIQ 윈도 30일",            illiq_window_d=30)
SENS.add("F3", "win_120d",  "ILLIQ 윈도 120일",           illiq_window_d=120)
SENS.add("F3", "level",     "수준(level) 기반 대조군 — 반증용", use_level=True)
SENS.add("F3", "amt_only",  "거래대금 변화율만(수익률 미포함)", amount_only=True)
# F4 — 임계 0.10/0.35(2) + 유효기간 6개월(1) + 계약상대 공공·대기업 한정(1)
SENS.add("F4", "thr_010",    "임계 0.10",                 ratio_threshold=0.10)
SENS.add("F4", "thr_035",    "임계 0.35",                 ratio_threshold=0.35)
SENS.add("F4", "horizon_6m", "유효기간 6개월",            horizon_m=6)
SENS.add("F4", "public_big", "계약상대 공공기관·대기업집단 한정", counterparty_major=True)

FACTOR_META = {
    "F1": dict(name="자본거래·지배구조 이벤트", kind="filter",  dirn="하방 제거",
               hyp="H1: 이벤트 발생 종목을 제거하면 순수익 CAGR 이 B2 를 유의하게 초과하고 "
                   "좌측 꼬리(하위 5% 종목수익, MDD)가 개선된다."),
    "F2": dict(name="내부자 순매수", kind="rank", dirn="상방",
               hyp="H2: 임원·주요주주의 자기자금 장내매수 종목은 이후 12개월 순수익이 "
                   "B2 및 B4 상위 5% 를 초과한다."),
    "F3": dict(name="유동성 개선(Investor Recognition)", kind="rank", dirn="상방",
               hyp="H3: Amihud 비유동성의 개선(변화율) 상위 종목은 이후 순수익이 B2 를 초과한다. "
                   "수준(level)이 아니라 변화율이 유효할 것."),
    "F4": dict(name="수주·공급계약", kind="event", dirn="상방",
               hyp="H4: 직전 매출액 대비 20% 이상 신규 공급계약 공시 종목은 이후 12개월 "
                   "순수익이 B2 및 B4 상위 5% 를 초과한다."),
}


# ── §6.1 OOS 봉인 ───────────────────────────────────────────────────────────────────────────
class OOSSeal:
    """봉인구간(뒤 40%)은 Step 7 이전에 열 수 없다.

    '보지 않겠다'는 의지가 아니라 잠금이어야 한다. IS 단계의 모든 수익률 조회는
    이 봉인을 통과하며, 열리기 전에 OOS 날짜를 요청하면 예외로 중단된다.
    """

    def __init__(self):
        self.boundary: Optional[pd.Timestamp] = None
        self.opened = False
        self.open_reason = ""
        self.blocked = 0

    def set_boundary(self, dates: Sequence) -> pd.Timestamp:
        d = pd.DatetimeIndex(sorted(pd.to_datetime(pd.Series(list(dates))).dropna().unique()))
        if len(d) == 0:
            raise SpecViolation("봉인 경계를 정할 리밸런싱 시점이 없습니다.")
        i = max(0, int(np.floor(len(d) * SPEC_IS_FRACTION)) - 1)
        self.boundary = d[i]
        LOG.info(f"표본 분할 — 탐색구간(IS) {d[0]:%Y-%m-%d} ~ {self.boundary:%Y-%m-%d} "
                 f"({i+1}/{len(d)} 시점, {SPEC_IS_FRACTION:.0%}) · "
                 f"봉인구간(OOS) {d[min(i+1, len(d)-1)]:%Y-%m-%d} ~ {d[-1]:%Y-%m-%d} → 🔒 잠금")
        return self.boundary

    def open(self, reason: str):
        self.opened = True
        self.open_reason = reason
        LOG.warn(f"🔓 OOS 봉인 해제 — {reason} (이 시점 이전의 조기 열람 시도: {self.blocked}건)")

    def mask(self, dates, want: str) -> "pd.Series":
        """want='IS'|'OOS'|'ALL'. 봉인 전 OOS/ALL 요청은 예외."""
        s = pd.to_datetime(pd.Series(list(dates)).reset_index(drop=True))
        if self.boundary is None:
            return pd.Series(True, index=s.index)
        if want == "IS":
            return s <= self.boundary
        if not self.opened:
            self.blocked += 1
            raise SpecViolation(
                f"봉인구간(OOS) 접근이 차단되었습니다 (요청: {want}). "
                f"명세서 §8-6(OOS 구간 조기 열람 금지) — Step 7 에서만 열립니다.")
        return pd.Series(True, index=s.index) if want == "ALL" else (s > self.boundary)


SEAL = OOSSeal()


def spec_sha256() -> str:
    """사전등록 상수 전체의 해시. run_log 에 남겨 사후 변조를 확인할 수 있게 한다."""
    payload = json.dumps({
        "spec_version": SPEC_VERSION,
        "univ": dict(SPEC_UNIV), "cov": dict(SPEC_COV), "gate": dict(SPEC_GATE),
        "cost": dict(SPEC_COST), "tax": SPEC_TAX_TABLE, "aum": list(SPEC_AUM_LADDER),
        "f1": dict(SPEC_F1), "f2": dict(SPEC_F2), "f3": dict(SPEC_F3), "f4": dict(SPEC_F4),
        "n_values": list(SPEC_N_VALUES), "trials": SPEC_TRIALS_TOTAL,
        "sens": {f: [x["key"] for x in SENS.get(f)] for f in FACTOR_META},
        "is_fraction": SPEC_IS_FRACTION, "b4_sims": SPEC_B4_SIMS, "seed": SEED,
    }, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
