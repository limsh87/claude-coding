

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
