# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  합성데이터 엔드투엔드 스모크                                                        ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 '계산경로'를 증명한다.                                    ║
# ║  합성데이터에는 국면 C 가 실제로 발생하도록 강제매도-소진 사이클을 심어 둔다.                ║
# ║  (신호가 한 건도 발화하지 않는 합성으로는 백테스트·강건성 경로를 검증할 수 없다)             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _ri(rng, lo: float, hi: float, floor: int = 0) -> int:
    """경계가 뒤집혀도 죽지 않는 정수 난수.

    ★ 이 함수가 존재하는 이유(실제 사고): 픽스처가 `rng.integers(300, n_days - 200)` 처럼
      '길이에 결합된 경계'를 쓰고 있었다. n_days=900 인 SMOKE 경로에서는 통과하지만
      n_days=500 인 FULL 경로에서는 low==high 가 되어 ValueError 로 즉사한다.
      경계를 계산하는 모든 지점을 이 한 곳으로 모아, 길이가 얼마든 항상 유효 구간을 만든다."""
    lo_i, hi_i = int(lo), int(hi)
    lo_i = max(int(floor), lo_i)
    if hi_i <= lo_i:
        hi_i = lo_i + 1
    return int(rng.integers(lo_i, hi_i))


def make_synthetic_flp(n_codes: int = 120, n_days: int = 900, seed: int = SEED) -> dict:
    """합성 데이터. n_days 가 짧아도(최소 200) 전 구간이 성립해야 한다 — 경계는 전부 비율로."""
    n_days = max(200, int(n_days))
    n_codes = max(8, int(n_codes))
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-02", periods=n_days)
    codes = [f"{900001+i:06d}" for i in range(n_codes)]

    px_rows, cr_rows, fl_rows = [], [], []
    for i, c in enumerate(codes):
        drift = rng.normal(0.0002, 0.0004)
        vol = rng.uniform(0.015, 0.035)
        ret = rng.normal(drift, vol, n_days)
        # 강제매도 사이클: 종목마다 다른 시점에 급락 → 신용잔고 급감 → 개인 이탈 → 기관 유입
        # 급락 시작 시점은 '비율'로 잡는다(길이에 결합된 상수 금지)
        t0 = _ri(rng, n_days * 0.35, n_days * 0.75, floor=60)
        ret[t0:t0 + 40] -= rng.uniform(0.004, 0.012)
        px = 20000 * np.exp(np.cumsum(ret))
        amount = rng.uniform(3e8, 4e9, n_days) * (1 + 0.5 * np.sin(np.arange(n_days) / 40))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": px * (1 + rng.normal(0, 0.002, n_days)),
            "high": px * 1.01, "low": px * 0.99, "close": px,
            "volume": (amount / px).astype(np.int64), "amount": amount, "src": "synth"}))

        base_cr = px * rng.uniform(200, 800)                    # 신용잔고 = 가격에 연동
        cr = base_cr.copy()
        cr[t0:t0 + 60] *= np.linspace(1.0, 0.25, min(60, n_days - t0))   # 반대매매로 급감
        cr[t0 + 60:] *= 0.25
        cr_rows.append(pd.DataFrame({"code": c, "date": days, "credit_bal": cr, "src": "synth"}))

        retail = rng.normal(0, 3e8, n_days)
        inst = rng.normal(0, 2e8, n_days)
        retail[t0:t0 + 70] -= 8e8                                # 개인 이탈(항복)
        inst[t0 + 40:t0 + 110] += 6e8                            # 기관 인수
        fl_rows.append(pd.DataFrame({"code": c, "date": days, "retail_net": retail,
                                     "inst_net": inst, "foreign_net": inst * 0.5}))

    px = pd.concat(px_rows, ignore_index=True)
    credit = pd.concat(cr_rows, ignore_index=True)
    flows = pd.concat(fl_rows, ignore_index=True)

    # 상장폐지 종목을 반드시 섞는다 (C2 경로를 스모크에서도 태운다)
    dead = codes[:max(3, n_codes // 20)]
    delist_dates = {c: days[_ri(rng, n_days * 0.65, n_days - 2, floor=10)] for c in dead}
    sec = pd.DataFrame({
        "code": codes, "name": [f"합성{i:03d}" for i in range(n_codes)],
        "market": ["KOSPI" if i % 3 == 0 else "KOSDAQ" for i in range(n_codes)],
        "listing_date": pd.Timestamp("2015-01-02"),
        "delisting_date": [delist_dates.get(c, pd.NaT) for c in codes],
        "industry": [f"IND{i%7:02d}" for i in range(n_codes)],
        "corp_code": [f"{i:08d}" for i in range(n_codes)]})

    months = pd.date_range(days[0], days[-1], freq="ME")
    shares = pd.concat([pd.DataFrame({"snap_date": m, "code": codes,
                                      "shares": rng.uniform(5e6, 5e7, n_codes),
                                      "mcap_snap": np.nan}) for m in months],
                       ignore_index=True)

    # DART 재무 (방화벽 입력) — 일부 종목은 자본잠식/영업CF 적자로 만든다
    fin_rows = []
    for i, c in enumerate(codes):
        for q, d in enumerate(pd.date_range(days[0], days[-1], freq="QE")):
            eq = rng.uniform(5e10, 5e11) * (-1 if i % 25 == 0 else 1)
            fin_rows.append({"corp_code": f"{i:08d}", "period_end": d,
                             "knowledge_date": d + pd.Timedelta(days=45),
                             "equity": eq, "assets": abs(eq) * 2,
                             "liabilities": abs(eq) * 0.8,
                             "cfo_ttm": rng.normal(1e10, 3e10),
                             "op_income_ttm": rng.normal(1e10, 2e10),
                             "net_income_ttm": rng.normal(8e9, 2e10),
                             "revenue_ttm": rng.uniform(1e11, 1e12)})
    fin = pd.DataFrame(fin_rows)

    dis = pd.DataFrame({
        "corp_code": [f"{i:08d}" for i in range(0, n_codes, 9)],
        "rcept_dt": [days[_ri(rng, n_days * 0.2, n_days - 1, floor=5)]
                     for _ in range(0, n_codes, 9)],
        "report_nm": "유상증자결정", "event": "rights_issue"})

    links = pd.DataFrame({
        "stock_code": [codes[_ri(rng, 0, n_codes)] for _ in range(600)],
        "pub_date": [days[_ri(rng, n_days * 0.1, n_days - 1, floor=2)] for _ in range(600)],
        "analyst_id": [f"an{_ri(rng, 0, 40):03d}" for _ in range(600)],
        "target_price": rng.uniform(10000, 60000, 600),
        "broker_name": "합성증권"})

    return {"px": px, "credit": credit, "flows": flows, "sec": sec, "shares": shares,
            "fin": fin, "disclosures": dis, "links": links}


def run_selftest(full_chain: bool = False) -> bool:
    """계산경로 전체(수집 제외)를 합성으로 태운다. 실패하면 실데이터 수집을 시작하지 않는다."""
    t0 = time.time()
    S = make_synthetic_flp(n_codes=(120 if full_chain else 60),
                           n_days=(900 if full_chain else 460))
    px, sec = S["px"], S["sec"]
    # ★ 합성 재무를 전역 PIT 에 올린다. 이 등록은 반드시 끝에서 되돌린다(아래 finally) —
    #   남겨두면 실데이터 실행에서 PIT.has("dart_financials") 가 True 가 되어
    #   "DART 재무가 없어 방화벽이 비활성" 경고가 사라지고, 결측인 채로 조용히 진행된다.
    PIT.register("dart_financials",
                 pit_frame(S["fin"], "period_end", "knowledge_date", source="synth"),
                 key_cols=["corp_code"])
    uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
    P = build_flp_panel(px, S["credit"], S["flows"], S["shares"], weeks, uni)
    if P.empty:
        LOG.error("스모크: 주간 패널이 비었습니다.")
        PIT.drop("dart_financials")
        return False
    P = apply_universe_bands(P)
    P = build_cells_flp(P, sec)
    P = classify_phase(P)
    P = attach_fundamentals_flp(P, sec)
    P = apply_firewall(P, pd.DataFrame(columns=["code", "flag", "from_date", "to_date", "src"]),
                       {"disclosures": S["disclosures"]})
    ctx = {"disclosures": S["disclosures"],
           "research_panel": build_research_panel(S["links"], P, weeks)}
    P = apply_vetoes(P, ctx)
    P = build_tps(P)
    P = assemble_score(P)

    n_c = int(P["PHASE_C"].sum())
    n_sig = int((P["Signal"] > 0).sum())
    if n_sig == 0:
        LOG.error(f"스모크: 신호가 한 건도 발화하지 않았습니다 (국면C {n_c}행). "
                  f"게이트 중 하나가 항상 0 이면 실데이터에서도 영구 무발화입니다.")
        PIT.drop("dart_financials")
        return False

    def _run(pp, label="smoke", apply_costs=True, slip_k=SLIPPAGE_K, audit=False):
        return run_backtest_w(pp, weeks, uni, sec, apply_costs=apply_costs,
                              slip_k=slip_k, label=label, audit=audit)

    bt = _run(P, label="SMOKE", audit=True)      # 대표 실행만 감쇠 원장을 기록
    abl_df, dist_df = pd.DataFrame(), pd.DataFrame()
    s = perf_stats_w(bt["returns"])
    if not s or not np.isfinite(s.get("CAGR", np.nan)):
        LOG.error("스모크: 성과 지표를 계산하지 못했습니다.")
        PIT.drop("dart_financials")
        return False

    if full_chain:
        # 스모크에서는 '전 검사 경로'를 반드시 한 번씩 태운다. 킬로 중단되면 뒤쪽 검사가
        # 한 번도 실행되지 않은 채 실데이터로 넘어가고, 그 함수의 버그는 3시간 뒤에 터진다.
        _stop_keep = globals().get("STOP_ON_KILL_CRITERIA", True)
        _grade_keep = (CREDIT_GRADE, FLOW_GRADE, WATCH_GRADE)
        globals()["STOP_ON_KILL_CRITERIA"] = False
        globals()["CREDIT_GRADE"] = "SYNTHETIC(합성 스모크)"
        globals()["FLOW_GRADE"] = "SYNTHETIC"
        globals()["WATCH_GRADE"] = "SYNTHETIC"
        bench = benchmark_returns_w(weeks, P)
        report_grade_banner()
        report_performance(bt, bench, label="(합성 스모크)")
        # 합성데이터의 킬 판정은 '합성이 그렇게 생겼다'는 뜻일 뿐이므로 여기서는 흡수한다.
        # (실데이터 실행에서는 절대 흡수하지 않는다 — main() 참조)
        try:
            R2F_exhaustion_vs_drawdown(P, _run)
            R0_benchmark(bt, bench)
            R1_leakage(P, _run, s)
            R12_tail_correlation(bt, bench, P)
            R3_orthogonal(bt, P)
            abl_df = R5_ablation(P, _run, s)
            R7_regime(bt, bench)
            R9_capacity(P, _run)
            dist_df = check_phase_sample(P)
        except KillCriteria as e:
            LOG.warn(f"합성데이터에서 킬 판정 — 합성이므로 무시하고 계속합니다: {e}")
        report_robustness()
        # 스몰캡 비교 경로도 스모크에서 한 번 태운다(실데이터에서 처음 도는 코드를 없앤다)
        if RUN_SMALLCAP_COMPARE and "in_band_small" in P.columns:
            runs = OrderedDict()
            runs["전체 유니버스"] = {"bt": bt, "stat": s}
            PS = assemble_score(slim_panel(P), band_col="in_band_small", quiet=True)
            bs = _run(PS, label="SMOKE_small")
            runs[f"스몰캡(하위 {SMALLCAP_BOTTOM_N})"] = {"bt": bs,
                                                         "stat": perf_stats_w(bs["returns"])}
            report_universe_compare(runs, bench)
        uni.report_attrition()
        report_interpretation(P)
        diagnostic_card(P, bt, sec)
        report_dataflow_map()
        # 산출물 저장 경로까지 태운다 — 3시간 뒤 마지막 스테이지에서 처음 터지는 것을 막는다
        try:
            outs = persist_outputs(P, bt, {"verdict": "합성 스모크", "A": {}, "B": {}, "C": {}},
                                   {"synthetic": True}, abl_df, dist_df, uni)
            LOG.ok(f"산출물 저장 경로 검증 완료 — {len(outs)}건 (합성)")
        except Exception as e:                                          # noqa
            LOG.error(f"산출물 저장 경로에서 실패: {type(e).__name__}: {e}")
            return False
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = _stop_keep
            globals()["CREDIT_GRADE"], globals()["FLOW_GRADE"], globals()["WATCH_GRADE"] = _grade_keep
        LOG.info("※ 위 숫자는 전부 '합성데이터'입니다. 실데이터 결과가 아닙니다.")

    PIT.drop("dart_financials")          # ★ 합성 등록 원복 (실데이터 실행 오염 방지)
    LOG.ok(f"스모크 통과 — 국면C {n_c:,}행 · 발화 {n_sig:,}행 · "
           f"CAGR(합성) {s.get('CAGR', float('nan')):.2%} · {time.time()-t0:.1f}s")
    return True
