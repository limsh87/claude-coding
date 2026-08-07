

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-G  공용축 B(회계품질) · C(자원투입) · D(반영도)  — 전 팩 공유, 필수                    ║
# ║                                                                                          ║
# ║  B·C 는 '확인'이 아니라 '사전확률'로 쓴다. K분기 연속 정렬 같은 대기조건을 넣지 않는다.     ║
# ║  가장 느린 축에 전체를 묶으면 선행성을 잃기 때문이다(§1.4).                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_base_panel(uni: "Universe", months: pd.DatetimeIndex,
                     price_m: pd.DataFrame) -> pd.DataFrame:
    """(code, month) 기본 격자. 여기에 모든 축이 as-of 로 붙는다."""
    rows = []
    for m in months:
        codes = uni.at(m)
        uni.audit_row("PIT유니버스", m, codes)
        rows.append(pd.DataFrame({"code": codes, "month": m}))
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["code", "month"])
    P = P.merge(price_m, on=["code", "month"], how="left")
    for m in months:
        sub = P[(P["month"] == m) & P["close"].notna()]
        uni.audit_row("가격보유", m, sub["code"].tolist())
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {len(months)}개월) "
           f"— 메모리 {mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel", P)
    return P


def attach_fundamentals(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """재무·직원 데이터를 PIT as-of 로 결합. 여기가 미래누수의 최대 위험지점이다."""
    c2c = sec.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str).to_dict()
    P = P.copy()
    P["corp_code"] = P["code"].map(c2c)
    if PIT.has("dart_financials"):
        P = PIT.asof_join(P, "dart_financials", by="corp_code", left_time="month")
    if PIT.has("dart_employees"):
        P = PIT.asof_join(P, "dart_employees", by="corp_code", left_time="month",
                          cols=["corp_code", "knowledge_date", "employees", "payroll"],
                          suffix="_emp")
    # ★ 결합 '이후에' 채운다. 먼저 만들어 두면 merge_asof 가 접미사를 붙여 실제 값을 흘려버린다.
    #
    #   왜 전 계정을 계약적으로 보장하는가 ─────────────────────────────────────────────────
    #   DART 키가 없거나(상단 안내가 "아무것도 안 채워도 실행된다"고 약속한다) 재무 수집이
    #   부분 실패하면 asof_join 이 아예 일어나지 않아 revenue_ttm·assets 같은 컬럼이
    #   존재하지 않게 된다. 피처 계산부는 col() 로 결측 컬럼을 막아 두었지만
    #   groupby(...)[c] 는 KeyError 로 죽고, 그 위치(L1.PANEL)는 critical 스테이지라
    #   실행 전체가 중단된다. 특히 손익·현금흐름 계정은 tidy_financials 가 항상 만들지만
    #   재무상태표 계정(assets·contract_liab 등)은 그 계정이 매칭됐을 때만 생기므로,
    #   "DART 는 응답했는데 BS 계정만 정규식이 안 맞은" 경우엔 패널이 멀쩡한 채로 죽는다.
    #   여기서 전부 NaN 으로 채워 두면 B/C축이 통째로 결측이 될 뿐 실행은 끝까지 간다.
    for c in FUNDAMENTAL_COLS:
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_financials"):
        LOG.warn("DART 재무가 없어 B축(회계품질)·C축(자원투입)과 PACK-C 가 전부 결측입니다. "
                 "실행은 계속되지만 증거층이 얇아집니다 — DART_API_KEY 를 넣으면 살아납니다.")
    return P


# ── B축: 회계 품질 ──────────────────────────────────────────────────────────────────────────
def axis_B(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)

    rev = col(P, "revenue_ttm")
    cogs = col(P, "cogs_ttm")
    P["gpm"] = safe_div(rev - cogs, rev) if rev is not None and cogs is not None else np.nan
    # b1: GPM 추세 기울기 (12개월 창의 선형 기울기 — 4분기 추세의 월간 등가물)
    P["b1"] = g("gpm").transform(lambda s: s.rolling(12, min_periods=6)
                                 .apply(lambda w: np.polyfit(np.arange(len(w)), w, 1)[0]
                                        if np.isfinite(w).all() else np.nan, raw=True))
    P["DIO"] = safe_div(col(P, "inventory"), col(P, "cogs_ttm")) * 365.0
    P["DSO"] = safe_div(col(P, "receivable"), col(P, "revenue_ttm")) * 365.0
    P["turn_days"] = P["DIO"] + P["DSO"]
    P["d_turn"] = g("turn_days").diff(12)
    P["dlog_rev"] = g("revenue_ttm").transform(lambda s: dlog(s, 12))

    # accruals (Sloan) — 순이익이 음수인 구간에서 CF/NI 비율을 쓰지 말 것(§7.1)
    avg_assets = (col(P, "assets") + g("assets").shift(12)) / 2.0
    P["accruals"] = safe_div(col(P, "net_income_ttm") - col(P, "cfo_ttm"), avg_assets)
    P["d_accruals"] = g("accruals").diff(12)
    P["b4"] = safe_div(g("contract_liab").diff(12), col(P, "revenue_ttm"))
    return P


def axis_B_tp(P: pd.DataFrame) -> pd.DataFrame:
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_B1"] = tp_product(z("dlog_rev"), -z("d_turn"))      # 매출↑ 인데 회전 유지
    P["TP_B2"] = tp_product(z("dlog_rev"), -z("d_accruals"))  # 매출↑ 인데 발생액 유지
    P["E_AXB"] = nanmean_cols(P, ["TP_B1", "TP_B2"]) * 0.5 + \
        nanmean_cols(pd.DataFrame({"a": z("b1"), "b": z("b4")}), ["a", "b"]) * 0.5
    return P


# ── C축: 자원 투입 ──────────────────────────────────────────────────────────────────────────
def axis_C(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)
    nwc = (col(P, "receivable").fillna(0) + col(P, "inventory").fillna(0) -
           col(P, "payable").fillna(0)) if "receivable" in P.columns else np.nan
    P["IC"] = nwc + col(P, "ppe").fillna(0) + col(P, "intangible").fillna(0)
    P["dlog_IC"] = g("IC").transform(lambda s: dlog(s, 12))
    nopat = col(P, "op_income_ttm") * 0.78                      # 법인세 22% 가정(셀 내 상대값이라 수준은 무해)
    avg_ic = (P["IC"] + g("IC").shift(12)) / 2.0
    P["ROIC"] = safe_div(nopat, avg_ic)
    P["d_ROIC"] = g("ROIC").diff(12)
    P["value_added"] = (col(P, "op_income_ttm").fillna(0) + col(P, "payroll").fillna(0) +
                        col(P, "dep_ttm").fillna(0))
    P["va_per_emp"] = safe_div(P["value_added"], col(P, "employees"))
    P["d_va_per_emp"] = g("va_per_emp").diff(12)
    P["dlog_emp"] = g("employees").transform(lambda s: dlog(s, 12))
    P["c3"] = safe_div(col(P, "capex_ttm").abs(), col(P, "dep_ttm").abs())
    P["debt_ratio"] = safe_div(col(P, "liabilities"), col(P, "equity"))
    P["d_debt_ratio"] = g("debt_ratio").diff(12)
    return P


def axis_C_tp(P: pd.DataFrame) -> pd.DataFrame:
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_C1"] = tp_product(z("dlog_IC"), z("d_ROIC"))            # 확장하는데 수익성 유지
    P["TP_C2"] = tp_product(z("dlog_emp"), z("d_va_per_emp"))     # 인원↑ 인데 생산성 유지
    P["E_AXC"] = nanmean_cols(P, ["TP_C1", "TP_C2"]) * 0.5 + \
        nanmean_cols(pd.DataFrame({"a": z("c3")}), ["a"]) * 0.5
    return P


# ── D축: 반영도 (U 산출) — 이 시스템에서 가장 중요한 단일 지표 ───────────────────────────────
def axis_D(P: pd.DataFrame, px_daily: pd.DataFrame, flows: pd.DataFrame,
           cons: pd.DataFrame) -> pd.DataFrame:
    """Δlog P = Δlog E + Δlog M 분해.

    목표 상태: ΔlogE > 0 AND ΔlogM <= 0
      → 시장이 이익 증가는 인정했으나 자본화를 거부 = "일회성으로 분류함" = 노리는 미스프라이싱
    d1 = -Δlog M

    ⚠ 한계 명시(§16.2): 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하다. 따라서 E 는
      후행 12M EPS(=DART TTM 순이익/주식수 대신 시가총액 기준으로 EPS 대리)를 쓴다.
      이 대리변수의 한계를 리포트에 반드시 명시하고 숨기지 않는다.
    """
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)

    # E 대리: TTM 순이익. M 대리: 시가총액/TTM순이익 → 주식수를 모를 때도 비율은 성립한다.
    P["E_proxy"] = col(P, "net_income_ttm")
    P["mktcap_proxy"] = P["close"]                       # 셀 내 상대비교라 주식수 상수배는 무해
    # 120거래일 ≈ 6개월 창
    P["dlog_E"] = g("E_proxy").transform(lambda s: dlog(s, 6))
    P["dlog_P"] = g("close").transform(lambda s: dlog(s, 6))
    P["dlog_M"] = P["dlog_P"] - P["dlog_E"]
    P["d1"] = -P["dlog_M"]
    P["D_state"] = np.select(
        [(P["dlog_E"] > 0) & (P["dlog_M"] <= 0),
         (P["dlog_E"] > 0) & (P["dlog_M"] > 0),
         (P["dlog_E"] <= 0) & (P["dlog_M"] > 0)],
        ["목표상태(진입)", "리레이팅중(관망)", "기대선행(배제)"], default="개선없음(배제)")

    # d3: 120일 기관+외국인 누적순매수 / 시총 (부호 반전 — 아직 안 들어온 게 좋다)
    P["d3"] = np.nan
    if flows is not None and len(flows):
        f = flows.copy()
        f["date"] = as_ts_series(f["date"])
        f["net"] = f.get("inst_net").fillna(0) + f.get("foreign_net").fillna(0)
        f = f.sort_values(["code", "date"])
        f["cum120"] = (f.groupby("code", observed=True)["net"]
                        .transform(lambda s: s.rolling(120, min_periods=40).sum()))
        f["month"] = f["date"].values.astype("datetime64[M]")
        fm = (f.groupby(["code", "month"], observed=True)["cum120"].last().reset_index())
        fm["month"] = as_ts_series(fm["month"]) + pd.offsets.MonthEnd(0)
        P = P.merge(fm, on=["code", "month"], how="left")
        adv = P["adv20"].replace(0, np.nan)
        P["d3"] = -safe_div(P["cum120"], adv * 250.0)     # 시총 대신 연간 거래대금으로 정규화

    # d2/d4: 컨센서스 (애널리스트 원장에서 산출)
    P["d2"] = np.nan
    P["d4"] = np.nan
    if cons is not None and len(cons):
        P = P.merge(cons[["code", "month", "d2_raw", "d4_raw", "n_analyst", "tp_median"]],
                    on=["code", "month"], how="left")
        P["d2"] = P["d2_raw"]
        P["d4"] = P["d4_raw"]
    return P


def axis_D_U(P: pd.DataFrame) -> pd.DataFrame:
    """U = 결측 제외 평균. ★ 결측 축을 0으로 채우지 않는다(§7.3)."""
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    Z = pd.DataFrame({"z_d1": z("d1"), "z_d2": z("d2"), "z_d3": z("d3"), "z_d4": z("d4")})
    avail = Z.notna().sum(axis=1)
    P["U_raw"] = nanmean_cols(Z, list(Z.columns))
    P["U_axes_used"] = avail
    P["U"] = xsec_rank_pct_l(P, P["U_raw"])
    used = {c: int(Z[c].notna().sum()) for c in Z.columns}
    LOG.info("D축 가용성 — " + " · ".join(f"{k}:{v:,}행" for k, v in used.items()) +
             f"  (평균 가용 축 {avail.mean():.2f}개)")
    if used.get("z_d2", 0) == 0 and used.get("z_d4", 0) == 0:
        LOG.warn("컨센서스 기반 d2/d4 가 전무합니다. U 는 d1(+d3)만으로 구성됩니다. "
                 "애널리스트 리포트 수집이 실패했거나 목표주가 추출률이 0인 상태입니다 — "
                 "위 원장 무결성 감사표를 확인하세요.")
    return P
