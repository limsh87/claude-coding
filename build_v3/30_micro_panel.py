

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
]

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
           + [f"interest_expense{s}" for s in ("_q", "_ttm")]
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

    g = d.groupby("corp_code", observed=True)

    def lag4(name: str) -> pd.Series:
        return g[name].shift(4) if name in d.columns else pd.Series(np.nan, index=d.index)

    rev = col(d, "revenue_ttm")
    cogs = col(d, "cogs_ttm")
    inv = col(d, "inventory")
    rec = col(d, "receivable")
    ni = col(d, "net_income_ttm")
    cfo = col(d, "cfo_ttm")
    ast = col(d, "assets")
    opi = col(d, "op_income_ttm")
    inte = col(d, "interest_expense_ttm")
    eq = col(d, "equity")
    cap = col(d, "capital_stock")

    # ── §8 원시 센서 (정규화 금지 — 셀 정규화는 L2 에서 한 번만) ─────────────────────────
    d["i_sales"] = np.log(rev.where(rev > 0)) - np.log(lag4("revenue_ttm").where(lambda s: s > 0))
    # 재고회전일수 · 매출채권회전일수. 분모가 0/음수면 무한대가 되므로 결측 처리한다.
    d["i_dio"] = safe_div(inv, cogs.where(cogs > 0)) * 365.0
    d["i_dso"] = safe_div(rec, rev.where(rev > 0)) * 365.0
    d["_cyc"] = d["i_dio"] + d["i_dso"]
    d["i_turn"] = -(d["_cyc"] - g["_cyc"].shift(4))

    # Sloan 발생액. 순이익이 음수인 구간에서도 안전하다(비율이 아니라 자산 대비 수준).
    avg_ast = (ast + lag4("assets")) / 2.0
    d["_accr"] = safe_div(ni - cfo, avg_ast.where(avg_ast > 0))
    d["i_accr"] = -(d["_accr"] - g["_accr"].shift(4))

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
    d_rev = rev - lag4("revenue_ttm")
    d_wc = (inv - lag4("inventory")) + (rec - lag4("receivable"))
    ratio = safe_div(d_wc, d_rev.where(d_rev > 0))
    d["v1_pushout"] = ((d_rev > 0) & (ratio > V1_PUSH_RATIO)).astype("float32")
    d.loc[d_rev.isna() | d_wc.isna(), "v1_pushout"] = np.nan

    #   V2 는 코어 tidy_financials 가 v2_bad_3q 로 이미 만든다(3분기 연속 이익-현금 괴리).
    if "v2_bad_3q" not in d.columns:
        d["v2_bad_3q"] = np.nan

    d = d.drop(columns=[c for c in ("_cyc", "_accr") if c in d.columns])
    n_ok = int(d["i_sales"].notna().sum())
    LOG.ok(f"L1 센서 계산 {len(d):,}분기행 · i_sales 유효 {n_ok:,}행 "
           f"({100*n_ok/max(len(d),1):.0f}%) — 분기 프레임에서 lag4 로 산출")
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

    med_fine = float(cand_fine.groupby(cand_fine).transform("size").median()) if len(p) else 0.0
    if med_fine < min_n:
        med_coarse = float(cand_coarse.groupby(cand_coarse).transform("size").median()) if len(p) else 0.0
        LOG.warn(f"C14-b 발동 — 셀당 중앙값 종목수 {med_fine:.0f} < {min_n}. "
                 f"산업분류를 한 단계 상위로 올립니다(상위 기준 중앙값 {med_coarse:.0f}).")
        p["cell"] = cand_coarse
        p["cell_l2"] = ym + "|ALL"
    else:
        p["cell"] = cand_fine
        p["cell_l2"] = cand_coarse
    p["cell_l3"] = ym + "|ALL"

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백: 1차 {n_small:,}행(상위 업종) / 2차 {int(still.sum()):,}행(전체). "
                 f"C14-b 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 1단계 {p['cell'].nunique():,}개 · 중앙값 "
              f"{float(p.groupby('cell', observed=True)['code'].transform('size').median()):.0f}종목")
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
    use_pctl = med_abs < 50
    if use_pctl:
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
