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
