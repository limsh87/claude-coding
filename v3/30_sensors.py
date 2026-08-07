

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1  원시 센서  (§3 · §6)                                                                  ║
# ║                                                                                          ║
# ║  ★ 이 블록에는 윈저·z·랭크·셀·TP·거부권이 **하나도** 들어가면 안 된다.                     ║
# ║    그 경계가 v3 의 핵심이다. 정규화가 L1 에 있으면 절제 1회에 L1 재빌드(30분+)가 걸린다.   ║
# ║    전부 L2 에 있으므로 파라미터 실험 1회가 수십 초다.                                      ║
# ║                                                                                          ║
# ║  출력은 parquet 로 영속화되고 L2(score)는 그 parquet 만 읽는다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _mi(P: pd.DataFrame) -> pd.Series:
    """월 인덱스(정수). diff 의 '몇 달 전'을 행 위치가 아니라 달력으로 세기 위해 쓴다."""
    m = as_ts_series(P["month"])
    return (m.dt.year * 12 + m.dt.month).astype("int64")


def _lag_ok(P: pd.DataFrame, n: int) -> pd.Series:
    """n개월 전 행이 실제로 존재하고 정확히 n개월 전인가.

    ★ 이걸 안 하면 거래정지·상장폐지 직전처럼 달이 비는 구간에서 shift(n) 이 몇 달 더 과거를
      끌어와 'n개월 변화'로 둔갑한다. 예외는 안 나고 값만 조용히 틀린다. 전 diff 에 강제한다.
    """
    prev = P.groupby("code", observed=True)["_mi"].shift(n)
    return (P["_mi"] - prev) == n


def gdiff(P: pd.DataFrame, s, n: int = 12) -> pd.Series:
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    v = v.replace([np.inf, -np.inf], np.nan)
    d = v - v.groupby(P["code"], observed=True).shift(n)
    return d.where(_lag_ok(P, n))


def gdlog(P: pd.DataFrame, s, n: int = 12) -> pd.Series:
    """Δlog. 음수/0 은 결측 — log 의 정의역 밖을 0 으로 메우는 것이 이 프로젝트 최빈 버그였다."""
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    v = v.replace([np.inf, -np.inf], np.nan)
    lv = np.log(v.where(v > 0))
    d = lv - lv.groupby(P["code"], observed=True).shift(n)
    return d.where(_lag_ok(P, n))


def groll_mean(P: pd.DataFrame, s, n: int, min_periods: Optional[int] = None) -> pd.Series:
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    return (v.groupby(P["code"], observed=True)
             .transform(lambda x: x.rolling(n, min_periods=min_periods or max(2, n // 2)).mean()))


SENSOR_STAGE = {
    # 센서 → 필요한 최소 단계(§2). 단계별로 어떤 TP 가 살아나는지가 여기서 결정된다.
    "M0": ["i_sales", "i_dio", "i_dso", "i_turn", "i_accr", "i_gpm",
           "v1_push", "v2_bad", "v5_impair"],
    "M1": ["i_capex", "i_ic", "i_roic", "p_payout", "p_invest", "p_cancel", "b4_defrev", "v3_dilute"],
    "M2": ["i_emp", "i_vapp"],
    "M3": ["d1", "d3", "dlog_M", "dlog_E"],
}
SENSOR_ALL = [s for v in SENSOR_STAGE.values() for s in v]


def build_sensors(P: pd.DataFrame, stage: str = "ALL") -> pd.DataFrame:
    """§6 원시 센서. 정규화 없음. 단계별로 필요한 것만 계산한다."""
    p = P.sort_values(["code", "month"], kind="mergesort").reset_index(drop=True)
    p["_mi"] = _mi(p)
    want = STAGE_ORDER[:STAGE_ORDER.index(stage) + 1] if stage in STAGE_ORDER else STAGE_ORDER

    # ── §6.1 재무 센서 (M0) ──────────────────────────────────────────────────────────────
    rev = col(p, "revenue_ttm")
    cogs = col(p, "cogs_ttm")
    p["i_sales"] = gdlog(p, rev, 12)
    p["i_dio"] = safe_div(col(p, "inventory"), cogs) * 365.0
    p["i_dso"] = safe_div(col(p, "receivable"), rev) * 365.0
    # i_turn 은 '회전이 나빠지지 않았다'를 양수로 만드는 부호다: -Δ(DIO+DSO)
    p["i_turn"] = -gdiff(p, p["i_dio"] + p["i_dso"], 12)
    # Sloan accruals. ★ 순이익이 음수인 구간에서 영업CF/순이익 비율을 쓰면 안 된다(부호 뒤집힘).
    #   발생액 형태로만 쓴다: (순이익 - 영업CF) / 평균총자산
    avg_assets = (col(p, "assets") + col(p, "assets").groupby(p["code"], observed=True).shift(12)
                  .where(_lag_ok(p, 12))) / 2.0
    avg_assets = avg_assets.where(avg_assets > 0, col(p, "assets").where(col(p, "assets") > 0))
    p["_accr_lvl"] = safe_div(col(p, "net_income_ttm") - col(p, "cfo_ttm"), avg_assets)
    p["i_accr"] = -gdiff(p, p["_accr_lvl"], 12)
    p["_gpm"] = safe_div(col(p, "gross_profit_ttm"), rev)
    # 매출총이익이 없는 회사는 매출-매출원가로 복원한다(계정 미매칭이 흔하다)
    p["_gpm"] = p["_gpm"].where(p["_gpm"].notna(), safe_div(rev - cogs, rev))
    p["i_gpm"] = gdiff(p, p["_gpm"], 12)

    # 거부권 원재료 (L1 이므로 판정은 하지 않고 값만 만든다)
    d_rev = gdiff(p, rev, 12)
    d_inv = gdiff(p, col(p, "inventory"), 12)
    d_rec = gdiff(p, col(p, "receivable"), 12)
    p["v1_push"] = safe_div(d_inv + d_rec, d_rev).where(d_rev > 0)     # V1 밀어내기 비율
    p["v2_bad"] = col(p, "v2_bad_3q")                                   # 분기프레임에서 이미 계산됨
    eq = col(p, "equity")
    cap_stock = col(p, "assets") - col(p, "liabilities")
    p["v5_impair"] = ((eq <= 0) | (cap_stock <= 0)).astype("float32")   # 자본잠식

    # ── §6.2 자본·자원 센서 (M1) ────────────────────────────────────────────────────────
    if "M1" in want:
        capex = col(p, "capex_ttm").abs()          # 현금흐름표에서 음수로 오는 경우가 흔하다
        base3 = groll_mean(p, capex, 36, min_periods=24)
        base3 = base3.groupby(p["code"], observed=True).shift(12).where(_lag_ok(p, 12))
        p["i_capex"] = safe_div(capex, base3)
        nwc = col(p, "cur_assets") - col(p, "cur_liab")
        ic = nwc + col(p, "ppe") + col(p, "intangible")
        p["_ic"] = ic.where(ic > 0)
        p["i_ic"] = gdlog(p, p["_ic"], 12)
        tax_rate = safe_div(col(p, "tax_expense_ttm"), col(p, "pretax_income_ttm")).clip(0.0, 0.5)
        tax_rate = tax_rate.fillna(0.22)                                 # 한국 실효법인세 근사
        nopat = col(p, "op_income_ttm") * (1.0 - tax_rate)
        avg_ic = (p["_ic"] + p["_ic"].groupby(p["code"], observed=True).shift(12)
                  .where(_lag_ok(p, 12))) / 2.0
        avg_ic = avg_ic.where(avg_ic > 0, p["_ic"])
        p["_roic"] = safe_div(nopat, avg_ic)
        p["i_roic"] = gdiff(p, p["_roic"], 12)
        p["_payout"] = safe_div(col(p, "dividend_paid_ttm").abs() +
                                col(p, "treasury_buy_ttm").abs(), col(p, "cfo_ttm"))
        p["_payout"] = p["_payout"].where(col(p, "cfo_ttm") > 0)        # 영업CF 음수면 무의미
        p["p_payout"] = gdiff(p, p["_payout"], 12)
        p["_invest"] = safe_div(capex + col(p, "rnd_ttm").abs(), rev)
        p["p_invest"] = gdiff(p, p["_invest"], 12)
        p["b4_defrev"] = safe_div(gdiff(p, col(p, "contract_liab"), 12), rev)
        if "p_cancel" not in p.columns:
            p["p_cancel"] = np.nan
        if "treasury_acq_amt" not in p.columns:
            p["treasury_acq_amt"] = np.nan
        if "v3_dilute" not in p.columns:
            p["v3_dilute"] = 0.0

    # ── §6.3 인적 센서 (M2) ─────────────────────────────────────────────────────────────
    if "M2" in want:
        emp = col(p, "employees")
        p["i_emp"] = gdlog(p, emp, 12)
        va = col(p, "op_income_ttm") + col(p, "payroll") + col(p, "dep_ttm").abs()
        p["_vapp"] = safe_div(va, emp.where(emp > 0))
        p["i_vapp"] = gdiff(p, p["_vapp"], 12)

    # ── §6.4 반영도 센서 (M3) ───────────────────────────────────────────────────────────
    if "M3" in want:
        # ΔlogP = ΔlogE + ΔlogM  →  ΔlogM = ΔlogP - ΔlogE.  d1 = -ΔlogM
        # 윈도우 120거래일 ≈ 6개월. 월 패널이므로 6개월 차분으로 등가 구현한다.
        W = 6
        p["dlog_P"] = gdlog(p, "close", W)
        # E = trailing 12M 이익. 적자 기업은 배수가 정의되지 않으므로 결측이다 —
        # 0 이나 대체 계정으로 채우면 횡단면 안에서 서로 다른 정의가 섞인다.
        p["dlog_E"] = gdlog(p, col(p, "net_income_ttm"), W)
        p["dlog_M"] = p["dlog_P"] - p["dlog_E"]
        p["d1"] = -p["dlog_M"]
        if "flow_120d" in p.columns:
            p["d3"] = -safe_div(col(p, "flow_120d"), col(p, "mcap"))
        else:
            p["d3"] = np.nan

    # ── R3(퀄리티 직교화)용 표준 팩터. 원시값이므로 L1 에 둔다 ───────────────────────────
    p["q_roa"] = safe_div(col(p, "net_income_ttm"), col(p, "assets"))
    p["q_gpa"] = safe_div(col(p, "gross_profit_ttm").where(col(p, "gross_profit_ttm").notna(),
                                                           rev - cogs), col(p, "assets"))
    p["q_size"] = np.log(col(p, "mcap").where(col(p, "mcap") > 0))
    p["q_bm"] = safe_div(eq, col(p, "mcap"))
    mom12 = gdlog(p, "close", 12)
    mom1 = gdlog(p, "close", 1)
    p["q_mom"] = mom12 - mom1                       # 12-1 모멘텀 (직전 1개월 반전 제거)
    p["q_vol"] = (col(p, "ret_m")
                  .groupby(p["code"], observed=True)
                  .transform(lambda s: s.rolling(12, min_periods=8).std()))

    drop = [c for c in p.columns if c.startswith("_") and c not in ("_mi",)]
    p = p.drop(columns=drop)
    made = [s for s in SENSOR_ALL if s in p.columns]
    cov = [[s, f"{int(p[s].notna().sum()):,}", f"{100*p[s].notna().mean():.1f}%"] for s in made]
    LOG.table(cov, ["센서", "유효관측", "커버리지"], ["l", "r", "r"],
              title=f"L1 센서 커버리지 (단계 {stage}) — 0% 인 센서를 쓰는 TP 는 전부 결측이 됩니다")
    PIPE.io("OUT", "MEM", "L1_sensors", p)
    return downcast(p)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  공시 파생 센서 — p_cancel · treasury_acq_amt · v3_dilute
# ═══════════════════════════════════════════════════════════════════════════════════════════
def build_disclosure_sensors(P: pd.DataFrame, dis: pd.DataFrame,
                             months: pd.DatetimeIndex) -> pd.DataFrame:
    """자사주 취득/소각, 희석성 조달.

    ★★ p_cancel 의 PIT 재정의 ★★
      §6.2 원문은 "자사주 취득공시 대비 12M 내 실제 소각 실행률" 이다. 이 정의를 시점 t 에서
      그대로 계산하면 t 이후 12개월의 소각을 봐야 한다 — **정의상 미래를 본다.**
      그대로 구현하면 R1 누수검정이 잡아내지도 못한다(누수가 아니라 정의가 미래를 포함하므로
      knowledge_date 를 앞당겨도 개선이 안 나온다). 조용히, 그리고 크게 틀린다.

      → t 시점에 **이미 판정이 끝난 취득공시만** 본다:
         t-24M ~ t-12M 사이의 취득공시 각각에 대해, 그 공시 후 12개월 안에 소각공시가
         있었는가. 이건 전부 t 이전 정보다. 창을 24개월로 두는 이유는 표본 확보다.
      이 재정의는 '신호가 1년 늦다'는 대가를 치르지만, 진정성(취득 후 실제 소각)이라는
      의미는 그대로 보존된다. 대가를 치르는 쪽이 미래를 보는 쪽보다 항상 낫다.
    """
    p = P.copy()
    for c in ("p_cancel", "treasury_acq_amt", "v3_dilute"):
        if c not in p.columns:
            p[c] = np.nan if c != "v3_dilute" else 0.0
    if dis is None or dis.empty or "stock_code" not in dis.columns:
        LOG.warn("공시목록이 없어 p_cancel · TP_P2 · V3 를 만들 수 없습니다 (결측 처리).")
        return p

    d = dis.dropna(subset=["stock_code"]).copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt"])
    acq = d[d["event"].isin(["treasury_acq", "treasury_trust"])][["stock_code", "rcept_dt"]]
    can = d[d["event"] == "treasury_canc"][["stock_code", "rcept_dt"]]

    # ── p_cancel: 이미 판정이 끝난 취득건의 소각 실행률 ─────────────────────────────────
    if len(acq):
        a = acq.rename(columns={"rcept_dt": "acq_dt"}).sort_values("acq_dt")
        if len(can):
            c = can.rename(columns={"rcept_dt": "can_dt"}).sort_values("can_dt")
            # 각 취득공시에 대해 '그 이후 첫 소각공시'
            m = pd.merge_asof(a, c, left_on="acq_dt", right_on="can_dt", by="stock_code",
                              direction="forward")
            m["executed"] = ((m["can_dt"] - m["acq_dt"]).dt.days.between(0, 365)).astype(float)
        else:
            m = a.copy()
            m["executed"] = 0.0
        m["verdict_dt"] = m["acq_dt"] + pd.Timedelta(days=365)     # 판정이 끝나는 시점
        rows = []
        for t in months:
            lo, hi = t - pd.Timedelta(days=730), t
            w = m[(m["verdict_dt"] > lo) & (m["verdict_dt"] <= hi)]
            if w.empty:
                continue
            g = w.groupby("stock_code")["executed"].agg(["mean", "size"]).reset_index()
            g["month"] = t
            rows.append(g)
        if rows:
            C = pd.concat(rows, ignore_index=True).rename(
                columns={"stock_code": "code", "mean": "_pc", "size": "_pn"})
            C["code"] = C["code"].astype(str)
            p = p.merge(C[["code", "month", "_pc", "_pn"]], on=["code", "month"], how="left")
            p["p_cancel"] = p["_pc"]
            # TP_P2 의 '취득 규모' 축: 판정 창 안의 취득 건수(규모의 대리).
            # 금액은 공시목록에 없고 본문 파싱이 필요하므로 건수로 대체하고 그 사실을 남긴다.
            p["treasury_acq_amt"] = p["_pn"]
            p = p.drop(columns=["_pc", "_pn"])
            LOG.ok(f"p_cancel(소각 실행률) {int(p['p_cancel'].notna().sum()):,}행 — "
                   f"PIT 재정의 적용(판정이 끝난 취득건만). 원문 정의는 12개월 미래를 봅니다.")
            LOG.info("※ TP_P2 의 '취득 규모' 축은 금액이 아니라 판정창 내 취득공시 건수입니다. "
                     "공시목록에 금액이 없어 본문 파싱이 필요하기 때문입니다 — 해석 시 감안하세요.")

    # ── V3: 90일 내 대규모 희석성 조달 ──────────────────────────────────────────────────
    dil = d[d["event"].isin(["rights_issue", "cb_issue", "bw_issue"])][["stock_code", "rcept_dt"]]
    if len(dil):
        dil = dil.rename(columns={"stock_code": "code", "rcept_dt": "dt"})
        dil["code"] = dil["code"].astype(str)
        rows = []
        for t in months:
            w = dil[(dil["dt"] > t - pd.Timedelta(days=90)) & (dil["dt"] <= t)]
            if w.empty:
                continue
            g = w.groupby("code").size().reset_index(name="n")
            g["month"] = t
            rows.append(g)
        if rows:
            V = pd.concat(rows, ignore_index=True)
            p = p.merge(V, on=["code", "month"], how="left")
            p["v3_dilute"] = (p["n"].fillna(0) > 0).astype("float32")
            p = p.drop(columns=["n"])
            LOG.ok(f"V3(90일 내 희석성 조달) 발동 후보 {int(p['v3_dilute'].sum()):,}행")

    # ── V5 보강: 비적정 감사의견 ────────────────────────────────────────────────────────
    #   공시목록의 '감사보고서' 제목만으로는 의견을 알 수 없다. 자본잠식(v5_impair)으로만
    #   판정하고, 감사의견 축은 데이터가 없음을 명시한다. 있는 척하지 않는다.
    return p


def attach_investor_flows(P: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """d3 입력: 120거래일 기관+외국인 누적순매수 (일별 → 월말 스냅샷)."""
    p = P.copy()
    if flows is None or flows.empty:
        p["flow_120d"] = np.nan
        LOG.warn("수급 데이터가 없어 d3 는 결측 처리됩니다. U 는 가용 축 평균으로 계산되며 "
                 "0 으로 채우지 않습니다(§8.1).")
        return p
    f = flows.copy()
    f["date"] = as_ts_series(f["date"])
    f = f.dropna(subset=["date", "code"]).sort_values(["code", "date"])
    f["net"] = (pd.to_numeric(f.get("inst_net"), errors="coerce").fillna(0) +
                pd.to_numeric(f.get("foreign_net"), errors="coerce").fillna(0))
    # ★ 창이 실제로 120일 채워졌을 때만 값을 낸다. 상장 직후·거래정지 구간에서 3일짜리 합을
    #   120일 누적으로 부르면 그 종목만 체계적으로 작아져 d3 랭크가 왜곡된다.
    f["flow_120d"] = (f.groupby("code", observed=True)["net"]
                       .transform(lambda s: rolling_sum_min_valid(s, 120, 90)))
    f["month"] = f["date"] + pd.offsets.MonthEnd(0)
    mo = (f.sort_values("date").groupby(["code", "month"], observed=True)["flow_120d"]
           .last().reset_index())
    mo["code"] = mo["code"].astype(str)
    p = p.merge(mo, on=["code", "month"], how="left")
    LOG.ok(f"d3 수급 결합 {int(p['flow_120d'].notna().sum()):,}행 "
           f"({100*p['flow_120d'].notna().mean():.1f}%)")
    return p
