

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


def _cell_ladder_z(P: pd.DataFrame, v: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 폴백 사다리를 적용한 백분위-윈저 z. 표본 부족 셀을 통째로 NaN 으로 만들지 않는다."""
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z_pct(v, P["cell"], min_n=min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in ("cell_l2", "cell_l3"):
        if not z.isna().any():
            break
        if lvl in P.columns:
            z = z.where(z.notna(), xsec_z_pct(v, P[lvl], min_n=min_n))
    return z


def z_lower_is_better(P: pd.DataFrame, raw: pd.Series, valid: pd.Series,
                      name: str = "") -> pd.Series:
    """'낮을수록 우수' 지표를 z-score(높을수록 우수)로 바꾸되, 분모 부적격(valid=False)
    관측치는 셀 최하위로 강제 배정한다 (§5.2 부호 처리 규칙).

    ★ 왜 '버리기'가 아니라 '최하위 배정'인가:
      버리면(NaN) 그 종목은 축 평균에서 빠지고, 다른 축 점수만으로 살아남아 오히려
      상위에 오를 수 있다. 즉 적자기업이 벌점 대신 면제를 받는다. 정반대의 결과다.
    """
    r = pd.to_numeric(raw, errors="coerce").replace([np.inf, -np.inf], np.nan)
    ok = valid.fillna(False).to_numpy(dtype=bool) & r.notna().to_numpy()
    sig = pd.Series(np.where(ok, -r.to_numpy(dtype="float64"), np.nan), index=P.index)
    z = _cell_ladder_z(P, sig)
    # 셀별 최하위 z (윈저라이징 이후 값이므로 이상치로 폭주하지 않는다)
    worst = z.groupby(P["cell"].astype(object).fillna("__NA__").to_numpy(),
                      observed=True).transform("min")
    forced = (~pd.Series(ok, index=P.index)) & r.notna().reindex(P.index).fillna(False)
    # raw 자체가 결측(재무 미보유)인 경우는 '부적격'이 아니라 '모름' 이므로 강제하지 않는다.
    z_out = z.copy()
    n_forced = int(forced.sum())
    if n_forced:
        z_out = z_out.where(~forced, worst)
        # 셀 전체가 부적격이라 worst 도 NaN 이면 -3 으로 바닥을 준다(z 스케일상 하위 0.1%).
        z_out = z_out.where(~(forced & z_out.isna()), -3.0)
    if name:
        LOG.debug(f"  {name}: 유효 {int(ok.sum()):,} · 분모부적격 강제최하위 {n_forced:,} · "
                  f"결측(모름) {int(r.isna().sum()):,}")
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
        S["_n"] = S.groupby("corp_code", observed=True).cumcount()
        prev = S.groupby("corp_code", observed=True)["shares_issued"].shift(12)
        prev_n = S.groupby("corp_code", observed=True)["_n"].shift(12)
        # ★ 12행 전이 '정확히 12분기 전'일 때만 3년 증가율로 인정한다. 결측 분기를 건너뛴 채
        #   shift(12) 를 믿으면 5년 전 주식수를 3년 증가율이라 부르게 된다.
        contiguous = (S["_n"] - prev_n) == 12
        S["share_growth3y"] = (safe_div(S["shares_issued"], prev) - 1.0).where(contiguous)
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
    # ★ 순현금이 시총보다 커서 EV<=0 인 경우는 '분모 오류'가 아니라 실제로 최우량이다.
    #   EV 를 0 으로 클립해 비율 0(=최우량)으로 두되, EBIT 부호 규칙은 그대로 적용한다.
    d["ev_ebit"] = safe_div(ev.clip(lower=0), ebit)
    d["_v_ok_ev"] = ebit.notna() & (ebit > 0)

    d["pbr"] = safe_div(cap, col(d, "equity"))
    d["_v_ok_pbr"] = col(d, "equity").notna() & (col(d, "equity") > 0)

    d["pcr"] = safe_div(cap, col(d, "cfo_ttm"))
    d["_v_ok_pcr"] = col(d, "cfo_ttm").notna() & (col(d, "cfo_ttm") > 0)

    LOG.info("V축 부호 처리 (§5.2) — 분모 ≤ 0 관측치는 해당 지표에서 셀 최하위로 강제 배정:")
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
    # 낮을수록 우수 → 부호 반전 후 z. 분모 부적격 개념이 없는 지표는 valid=notna.
    d["zQ_roic_std3y"] = z_lower_is_better(d, col(d, "roic_std3y"),
                                           col(d, "roic_std3y").notna(), "ROIC 3년 표준편차")
    d["zQ_accruals"] = z_lower_is_better(d, d["accruals"], d["accruals"].notna(), "발생액")
    # 부채비율은 자기자본이 0 이하면 의미가 뒤집힌다(음수 부채비율=최우량). 부적격 처리.
    d["zQ_debt_ratio"] = z_lower_is_better(
        d, d["debt_ratio"], col(d, "equity").notna() & (col(d, "equity") > 0), "부채비율")
    d["zQ_share_growth3y"] = z_lower_is_better(
        d, col(d, "share_growth3y"), col(d, "share_growth3y").notna(), "주식수 3년 증가율")

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
    key = f"qvf_flow_netbuy_w{int(window)}"
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
    return downcast_q(F.reindex(columns=cols))


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
