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


def build_cells_v3(P: pd.DataFrame, sec: pd.DataFrame, tag: str = "") -> pd.DataFrame:
    """cell = month|ind_mid|size_bucket. 폴백 사다리 4단.

      1단 month|ind_mid|size_bucket   ← 산업·규모 둘 다 중립화
      2단 month|ind_mid|ALL           ← 규모만 접는다 (큰 산업에서만 성립)
      3단 month|ind_l1|ALL            ← 산업을 묶는다 (★ 새로 생긴 계단)
      4단 month|ALL|ALL               ← 전체 시장

    ★★ 왜 3단이 새로 필요한가 — 실측된 사고 ★★
      v2 는 2단을 거친 산업(industry_l1)으로 내렸는데(build/20_pit.py:363), v3 포팅에서
      ind_l1 을 계산해 놓고도 2단에 ind_mid 를 그대로 넣어 **1단과 2단이 같이 무너졌다.**
      스코어링 패널 135,953행 ÷ 120개월 = 월 1,133행인데 업종이 154개라
      (월 × 업종) 셀이 평균 7.4행 — CELL_MIN_N_V3=8 에 못 미친다.
      결과: 전 행이 곧바로 '전체 시장' 으로 떨어져 **산업·규모 중립화가 한 번도 일어나지
      않았는데** 로그와 리포트는 여전히 '셀 = month × ind_mid × size_bucket' 이라고 말했다.

    ★ ind_l1 을 만드는 방법. 업종명 앞 N글자를 자르는 방식은 '반도체와관련장비'와
      '반도체소재'를 여전히 다른 문자열로 남긴다 — 자른다고 줄어든다는 보장이 없다.
      그래서 접두 병합 뒤에 **빈도 기반으로 한 번 더 접는다**: 그 그룹이 월평균
      CELL_MIN_N_V3 행을 못 채우면 '기타'로 합친다. 이러면 3단이 반드시 유효해진다.
      결과 카디널리티와 셀당 행수를 아래에서 로그로 찍어 검증 가능하게 남긴다.

    ★ 직원수가 없으면 규모를 매출 3분위로 대신한다. '미상' 한 덩어리로 두면 그 셀 안에서
      대기업과 소형주가 같은 분포에 섞여 규모효과가 신호로 둔갑한다.
    """
    ind = sec.dropna(subset=["code"]).set_index("code")["industry"].astype(str).to_dict()
    p = P.copy()
    p["ind_mid"] = p["code"].map(ind).fillna("미분류").astype(str).replace("", "미분류")
    # 1차 접기: 업종명 앞 2글자(금융/화학/전기/운수/도매/반도 …). 한국 업종명은 앞머리가 대분류다.
    _l1 = p["ind_mid"].str.slice(0, 2).replace("", "미분류")
    # 2차 접기: 그래도 표본이 안 나오는 그룹은 '기타'로 합친다 — 계단이 있어도 못 밟으면 없는 것과 같다.
    _n_months = max(1, int(p["month"].nunique()))
    _need = CELL_MIN_N_V3 * _n_months
    _cnt = _l1.map(_l1.value_counts())
    p["ind_l1"] = _l1.where(_cnt >= _need, "기타")

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
    p["cell_l3"] = ym + "|" + p["ind_l1"] + "|ALL"
    p["cell_l4"] = ym + "|ALL|ALL"

    # ★ 사다리가 실제로 밟히는지를 숫자로 남긴다. 예전 로그는 셀 **개수**만 찍었는데,
    #   정작 중요한 것은 '셀당 몇 행이냐'다 — 그게 임계치를 넘어야 그 계단이 존재한다.
    #   이 표가 없어서 '1단계 45,128개'라는 숫자가 붕괴 신호인 줄 아무도 몰랐다.
    rows = []
    for lvl, desc in ((c, d) for c, d in zip(CELL_LADDER_V3,
                                             ("month|업종|규모", "month|업종|ALL",
                                              "month|업종군|ALL", "month|ALL|ALL"))):
        cnt = p.groupby(lvl, observed=True)["code"].transform("count")
        rows.append([desc, f"{p[lvl].nunique():,}", f"{cnt.median():.1f}",
                     f"{100 * (cnt >= CELL_MIN_N_V3).mean():.0f}%"])
    LOG.table(rows, ["폴백 단계", "셀 수", "셀당 행(중앙값)", f"표본≥{CELL_MIN_N_V3} 비율"],
              ["l", "r", "r", "r"],
              title=f"셀 사다리 {tag}— {len(p):,}행 · 업종 {p['ind_mid'].nunique():,}개 → "
                    f"업종군 {p['ind_l1'].nunique():,}개")
    _usable = [d for (d, _n, _m, r) in rows if float(str(r).rstrip('%')) >= 50.0]
    if len(_usable) <= 1:
        LOG.warn(f"셀 사다리에서 실제로 쓸 수 있는 계단이 {len(_usable)}개뿐입니다 "
                 f"— 산업·규모 중립화가 사실상 전체시장 랭크로 퇴화합니다. "
                 f"모집단({len(p):,}행 / {p['month'].nunique():,}개월)이 너무 얇거나 "
                 f"업종 카디널리티가 과도합니다.")
    for c in CELL_LADDER_V3:
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
    # ★ 구성항목을 각각 fillna(0) 한 뒤 더하면, 계정이 **하나도 없는** 회사의 IC 가
    #   결측이 아니라 정확히 0.0 이 된다. 그러면 avg_ic=0 → safe_div 가 정의역 밖으로
    #   밀어내 ROIC 가 조용히 NaN 이 되고, '왜 0% 인지' 는 어디에도 안 남는다.
    #   → 하나라도 관측된 행에서만 합성한다(원칙 6 · 이 파일 머리말의 '0 채움 금지').
    #     관측된 항목만 더하는 것은 여전히 필요하다 — 매입채무만 없는 회사를 통째로
    #     버릴 이유는 없기 때문이다. 다만 **전부 없는 행은 결측으로 남긴다.**
    _ic_parts = ["receivable", "inventory", "payable", "ppe", "intangible"]
    _ic_obs = pd.concat([col(P, c).notna() for c in _ic_parts], axis=1).any(axis=1)
    nwc = (col(P, "receivable").fillna(0) + col(P, "inventory").fillna(0)
           - col(P, "payable").fillna(0))
    P["IC"] = (nwc + col(P, "ppe").fillna(0) + col(P, "intangible").fillna(0)).where(_ic_obs)
    P["i_ic"] = g("IC").transform(lambda s: dlog(s, 12))
    #   NOPAT: 실효세율이 관측되면 그걸 쓰고, 아니면 22% 가정. 셀 내 상대값이라 수준은 무해.
    eff = safe_div(col(P, "tax_expense_ttm"), col(P, "pretax_income_ttm"))
    eff = eff.where((eff >= 0) & (eff <= 0.6))
    P["nopat"] = col(P, "op_income_ttm") * (1.0 - eff.fillna(0.22))
    avg_ic = (P["IC"] + g("IC").shift(12)) / 2.0
    P["ROIC"] = safe_div(P["nopat"], avg_ic)
    P["i_roic"] = g("ROIC").diff(12)

    # p_payout / p_invest — 자본배분
    # ★ 같은 함정이 여기 두 번 더 있었다. capex_ttm·rnd_ttm 이 **통째로 없는** 실행에서
    #   invest 가 0.0 이 되고, revenue_ttm 은 살아 있으니 invest_ratio 가
    #   '전 종목 정확히 0' 인 **관측된 것처럼 보이는 무의미 센서**가 됐다.
    #   결측이면 결측인 게 낫다 — 가짜 관측은 MIN_TP_OBSERVED 게이트까지 속인다.
    _payout_obs = col(P, "dividend_paid_ttm").notna() | col(P, "treasury_buy_ttm").notna()
    payout = (col(P, "dividend_paid_ttm").abs().fillna(0)
              + col(P, "treasury_buy_ttm").abs().fillna(0)).where(_payout_obs)
    P["payout_ratio"] = safe_div(payout, col(P, "cfo_ttm"))
    P["p_payout"] = g("payout_ratio").diff(12)
    _invest_obs = col(P, "capex_ttm").notna() | col(P, "rnd_ttm").notna()
    invest = (col(P, "capex_ttm").abs().fillna(0)
              + col(P, "rnd_ttm").abs().fillna(0)).where(_invest_obs)
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
        # ★ 이 폴백은 **본선(UMID)에서만** 정당하다. 비교 대역(SMALL 등)에서 전 행을 True 로
        #   깔면 '스몰캡 팔'이 조용히 전 종목 팔로 둔갑해, 두 팔이 같은 모집단을 돌면서
        #   '대역 차이'라는 이름의 결과를 보고하게 된다 — 결론을 만들어내는 실패다.
        #   호출자(run_smallcap_arm_v3)의 빈-대역 가드는 이 폴백 때문에 영원히 발동하지 않았다.
        if band == "UMID":
            LOG.warn("U-MID 에 남는 행이 없습니다 — 가격 수집이 실패했거나 유동성 하한이 너무 높습니다. "
                     "u_mid 필터를 적용하지 않고 전 종목으로 진행합니다"
                     "(본선이 조용히 빈 결과를 내지 않기 위함).")
            P["u_mid"] = True
        else:
            LOG.warn(f"{band} 대역에 남는 행이 0 입니다 — 이 대역은 **비어 있는 것이 결과**이므로 "
                     f"전 종목으로 되돌리지 않습니다. 비교 팔은 건너뜁니다. "
                     f"(유동성 하한 {adv_min/1e8:.0f}억을 하위 대역이 못 넘긴다는 사실 자체가 "
                     f"'소형주는 담기 어렵다'는 발견입니다 — 하한을 낮춰 만들어내지 않습니다)")
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
