

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  합성데이터 엔드투엔드 스모크 테스트                                                 ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 계산경로 전체(피처→스코어→백테스트→강건성→리포트)를      ║
# ║  합성데이터로 통과시킨다. 목적은 성과 측정이 아니라 '배관 검증'이다.                        ║
# ║                                                                                          ║
# ║  왜 필요한가: 실수집은 수 시간~수 일이 걸린다. 그걸 다 받은 뒤에 조립부에서 터지면          ║
# ║  그 시간이 통째로 날아간다. 수 초짜리 스모크가 그 위험을 없앤다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def make_synthetic(n_codes: int = 160, n_months: int = 60, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    months = pd.date_range(as_ts(BACKTEST_END) - pd.DateOffset(months=n_months - 1),
                           as_ts(BACKTEST_END), freq="ME")
    codes = [f"{i+1:06d}" for i in range(n_codes)]
    inds = rng.choice(["화학", "전자부품", "건설", "기계", "소프트웨어"], n_codes)

    # 상장/폐지 — 일부는 기간 중 상장, 일부는 폐지 (생존자편향 검증용)
    listing = [months[0] - pd.DateOffset(years=int(rng.integers(2, 12))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
        listing[i] = months[int(rng.integers(6, n_months - 6))]
    delist = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        delist[i] = months[int(rng.integers(10, n_months - 2))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": inds,
                        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)],
                        "src": "synthetic"})

    # ── 진짜 알파를 심는다: quality[i] 가 높으면 미래수익이 높다 ────────────────────────────
    quality = rng.normal(size=n_codes)

    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1] + pd.Timedelta(days=5))
    px_rows = []
    for i, c in enumerate(codes):
        drift = 0.0006 + 0.0012 * quality[i]
        r = rng.normal(drift, 0.022, len(days))
        p = 10000 * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.5, 0.8, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": p * (1 + rng.normal(0, 0.003, len(days))),
            "high": p * 1.01, "low": p * 0.99, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    for i, c in enumerate(codes):
        if pd.notna(delist[i]):
            px = px[~((px["code"] == c) & (px["date"] > delist[i]))]
        px = px[~((px["code"] == c) & (px["date"] < listing[i]))]

    # ── 재무: quality 와 상관되게 만들되 노이즈를 크게 준다 ────────────────────────────────
    fin_rows, emp_rows = [], []
    for i, c in enumerate(codes):
        base_rev = rng.lognormal(25, 1.0)
        for m in pd.date_range(months[0] - pd.DateOffset(months=15), months[-1], freq="QE"):
            gr = 1 + 0.02 * quality[i] + rng.normal(0, 0.05)
            rev = base_rev * gr
            base_rev = rev
            fin_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "period_end": m,
                "knowledge_date": m + pd.Timedelta(days=45),
                "revenue_ttm": rev, "cogs_ttm": rev * (0.72 - 0.02 * quality[i]),
                "op_income_ttm": rev * (0.08 + 0.02 * quality[i]),
                "net_income_ttm": rev * (0.06 + 0.015 * quality[i]),
                "cfo_ttm": rev * (0.09 + 0.02 * quality[i]),
                "capex_ttm": rev * 0.05, "rnd_ttm": rev * (0.02 + 0.01 * max(quality[i], 0)),
                "dep_ttm": rev * 0.04,
                "dividend_paid_ttm": rev * (0.01 + 0.008 * max(quality[i], 0)),
                "treasury_buy_ttm": rev * (0.005 * max(quality[i], 0)),
                "inventory": rev * (0.15 - 0.01 * quality[i]),
                "receivable": rev * (0.18 - 0.01 * quality[i]),
                "payable": rev * 0.12, "assets": rev * 1.4, "liabilities": rev * 0.6,
                "equity": rev * 0.8, "ppe": rev * 0.5, "intangible": rev * 0.1,
                "contract_liab": rev * (0.03 + 0.01 * quality[i]),
                "tax_expense": rev * 0.015, "pretax_income": rev * 0.07,
                "sgna_ttm": rev * 0.15,
            })
        for y in range(months[0].year - 1, months[-1].year + 1):
            emp_rows.append({"corp_code": sec["corp_code"].iloc[i], "bsns_year": y,
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90),
                             "employees": float(max(12, rng.lognormal(5.2, 1.0) *
                                                    (1 + 0.05 * quality[i]))),
                             "payroll": float(rng.lognormal(22, 0.8))})
    fin = pd.DataFrame(fin_rows)
    fin = pit_frame(fin, "period_end", "knowledge_date", source="synthetic")
    emp = pd.DataFrame(emp_rows)
    emp = pit_frame(emp, "period_end", "knowledge_date", source="synthetic")

    # ── 공시 ───────────────────────────────────────────────────────────────────────────────
    dis_rows = []
    for i, c in enumerate(codes):
        for m in months[::4]:
            if rng.random() < 0.10 + 0.10 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m)[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식취득결정)",
                                 "event": "treasury_acq"})
            if rng.random() < 0.05 + 0.08 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m, "x")[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식소각결정)",
                                 "event": "treasury_canc"})
            if rng.random() < 0.05:
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m, "y")[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(유상증자결정)",
                                 "event": "rights_issue"})
    dis = pd.DataFrame(dis_rows)
    dis = pit_frame(dis, "rcept_dt", "rcept_dt", source="synthetic")

    # ── 애널리스트 리포트 원장 (링크까지 합성) ─────────────────────────────────────────────
    brokers = MAJOR_BROKERS[:10] + MINOR_BROKERS[:12]
    analysts = [(b, f"애널{j:02d}") for b in brokers for j in range(3)]
    rep_rows, link_rows = [], []
    for m in months:
        for _ in range(int(rng.integers(120, 260))):
            i = int(rng.integers(0, n_codes))
            b, nm = analysts[int(rng.integers(0, len(analysts)))]
            bid, bname = normalize_broker(b)
            tp = float(np.exp(rng.normal(9.6, 0.5)) * (1 + 0.15 * quality[i]))
            uid = sha1_str("syn", codes[i], m, nm, rng.integers(1e9))
            d = m - pd.Timedelta(days=int(rng.integers(0, 28)))
            rep_rows.append({"report_uid": uid, "source": "synthetic",
                             "src_report_id": uid[:10], "pub_date": d, "category": "company",
                             "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                             "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                             "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                             "opinion": "BUY", "pdf_url": None, "detail_url": None,
                             "event_date": d, "knowledge_date": d})
            link_rows.append({"report_uid": uid, "name": nm, "broker_id": bid,
                              "broker_name": bname, "role": "lead", "link_method": "list_field",
                              "link_conf": 0.98, "pub_date": d, "stock_code": codes[i],
                              "target_price": tp, "opinion": "BUY",
                              "name_norm": nm,
                              "analyst_id": sha1_str("analyst", bid, nm)[:14]})
    rep = pd.DataFrame(rep_rows)
    L = pd.DataFrame(link_rows)

    # ── 국민연금 패널 ──────────────────────────────────────────────────────────────────────
    nps_rows = []
    for i, c in enumerate(codes):
        base = max(15, int(rng.lognormal(5.0, 1.0)))
        wage = rng.lognormal(15.0, 0.25)
        for m in months:
            base = max(5, int(base * (1 + 0.004 * quality[i] + rng.normal(0, 0.02))))
            wage *= (1 + 0.002 + 0.001 * quality[i] + rng.normal(0, 0.004))
            nps_rows.append({"code": c, "month": m,
                             "nps_members": float(base),
                             "nps_amt": float(base * wage * 0.09),
                             "nps_acq": float(max(0, rng.poisson(3))),
                             "nps_loss": float(max(0, rng.poisson(max(1, 3 - quality[i])))),
                             "n_wkpl": float(max(1, int(rng.integers(1, 6)))),
                             "knowledge_date": m + pd.offsets.MonthEnd(2)})
    nps = pd.DataFrame(nps_rows)
    nps = pit_frame(nps, "month", "knowledge_date", source="synthetic")

    # ── 공시 텍스트 유사도 (PACK-D) ────────────────────────────────────────────────────────
    tx_rows = []
    for i, c in enumerate(codes):
        for y in range(months[0].year, months[-1].year + 1):
            d0 = as_ts(f"{y}-03-31")
            tx_rows.append({"corp_code": sec["corp_code"].iloc[i], "rcept_dt": d0,
                            "sim_risk": float(np.clip(0.9 + 0.03 * quality[i] +
                                                      rng.normal(0, 0.05), 0, 1)),
                            "sim_all": float(np.clip(0.9 + 0.02 * quality[i] +
                                                     rng.normal(0, 0.04), 0, 1))})
    txt = pit_frame(pd.DataFrame(tx_rows), "rcept_dt", "rcept_dt", source="synthetic")

    # ── 관세 통관 + HS 매핑 (PACK-X) ───────────────────────────────────────────────────────
    n_hs = max(60, n_codes // 2)              # 셀 내 z-score 가 성립할 만큼은 덮어야 한다
    hs_list = [f"{3900+i:04d}000000" for i in range(n_hs)]
    hs_map = pd.DataFrame({"code": [codes[i] for i in range(n_hs)],
                           "hs": hs_list, "weight": 1.0,
                           "valid_from": months[0], "valid_to": months[-1]})
    cu_rows = []
    for j, hs in enumerate(hs_list):
        # θ_X(수출매출/연결매출)가 0.3~0.9 가 되도록 매출 규모에 맞춰 스케일링한다.
        rev0 = float(np.exp(25.0))
        base_usd = rev0 * rng.uniform(0.3, 0.9) / 1300.0
        unit_px0 = rng.lognormal(1.0, 0.2)          # ※ 지역변수 px 는 일봉 DataFrame 이므로 금지
        q = base_usd / unit_px0
        for m in months:
            q *= (1 + 0.004 * quality[j] + rng.normal(0, 0.04))
            unit_px = unit_px0 * (1 + 0.03 * quality[j] + rng.normal(0, 0.02))
            for grp in ("선진_미국", "선진_EU", "아세안", "중화권"):
                w = q * rng.uniform(0.15, 0.35)
                cu_rows.append({"ym": m.strftime("%Y%m"), "hs": hs, "grp": grp,
                                "exp_wgt": float(w), "exp_usd": float(w * unit_px)})
    customs = pd.DataFrame(cu_rows)

    # ── 조달 낙찰 (PACK-P) ────────────────────────────────────────────────────────────────
    g_rows = []
    for i in range(0, n_codes, 3):
        for m in months:
            if rng.random() > 0.55:
                continue
            plan = rng.lognormal(19, 0.8)
            rate = float(np.clip(85 + 4 * quality[i] + rng.normal(0, 3), 60, 110))
            g_rows.append({"ym": m.strftime("%Y%m"), "biz_no": f"{1000000000+i}",
                           "corp_nm": f"합성{i+1:03d}", "award_amt": plan * rate / 100.0,
                           "plan_price": plan, "rate": rate,
                           "org": rng.choice(["조달청", "국방부", "한전", "지자체", "철도공단"]),
                           "item_cls": f"{rng.integers(1000,9999)}"})
    procure = pd.DataFrame(g_rows)

    return {"sec": sec, "px": px, "fin": fin, "emp": emp, "dis": dis,
            "reports": rep, "links": L, "nps": nps, "months": months,
            "text_sim": txt, "customs": customs, "hs_map": hs_map, "procure": procure,
            "flows": pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"]),
            "snapshots": pd.DataFrame(columns=["snap_date", "code", "market"])}


def run_selftest(full_chain: bool = False) -> bool:
    """full_chain=True 면 성과검증·강건성(R1~R11)·해석표·진단카드까지 전부 합성데이터로 돌린다.
    RUN_MODE='SMOKE' 의 목적이 바로 이것 — 실데이터 없이 최종 출력물의 모양을 전부 확인한다."""
    LOG.banner("① 합성데이터 엔드투엔드 스모크 테스트",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수 초)"
               + (" · full_chain: 강건성·해석표까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    S = make_synthetic()
    LOG.info(f"합성 데이터: 종목 {S['sec'].shape[0]} · 월 {len(S['months'])} · "
             f"일봉 {len(S['px']):,} · 재무 {len(S['fin']):,} · 리포트 {len(S['reports']):,}")

    PIT.register("dart_financials", S["fin"], key_cols=["corp_code"])
    PIT.register("dart_employees", S["emp"], key_cols=["corp_code"])

    panel = build_price_panel(S["px"], S["months"])
    uni = Universe(S["sec"], S["snapshots"], panel["daily"])
    P = build_base_panel(uni, S["months"], panel["monthly"])
    P = attach_fundamentals(P, S["sec"])
    P = build_cells(P, S["sec"])
    P = axis_B(P); P = axis_C(P)
    P = axis_B_tp(P); P = axis_C_tp(P)
    cons = build_consensus_panel(S["links"], S["months"])
    P = axis_D(P, panel["daily"], S["flows"], cons)
    P = axis_D_U(P)

    ctx = {"disclosures": S["dis"], "nps_panel": S["nps"], "sec": S["sec"],
           "text_sim": S["text_sim"], "customs": S["customs"], "hs_map": S["hs_map"],
           "procurement": S["procure"], "administrative": None}
    for p in active_packs():
        P = p["features"](P, ctx)
    P = apply_vetoes(P, ctx)
    P = assemble_score(P)

    def _run(pp, label="smoke", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else S["months"],
                            uni, S["sec"], apply_costs=apply_costs, label=label)

    bt = _run(P)
    st = perf_stats(bt["returns"])
    dur = time.time() - t0
    ok = (len(P) > 0 and len(bt["returns"]) == len(S["months"]) and
          bool(st) and np.isfinite(st.get("CAGR", np.nan)))
    LOG.table([["패널 행수", f"{len(P):,}"],
               ["활성 팩", ", ".join(p["id"] for p in active_packs()) or "없음"],
               ["백테스트 월수", f"{len(bt['returns'])}"],
               ["평균 보유종목", f"{st.get('평균종목수', float('nan')):.1f}"],
               ["합성 CAGR", f"{st.get('CAGR', float('nan'))*100:+.2f}%"],
               ["합성 Sharpe", f"{st.get('Sharpe', float('nan')):.3f}"],
               ["소요시간", f"{dur:.2f}초"]],
              ["항목", "값"], ["l", "r"], title="스모크 결과 (성과 수치는 의미 없음 — 배관 검증용)")
    if ok:
        LOG.ok(f"스모크 통과 ({dur:.2f}초) — 피처→스코어→백테스트 경로가 정상 동작합니다. "
               f"이제 실데이터를 수집해도 조립부에서 시간을 날릴 위험이 없습니다.")
    else:
        LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
        return False
    if not full_chain:
        return True

    # ── 여기서부터는 '최종 출력물 전체'를 합성데이터로 예행연습한다 ────────────────────────
    LOG.warn("아래 성과·강건성 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 아니라 "
             "'출력물이 제대로 나오는지'를 보여주는 예행연습입니다. 절대 해석하지 마세요.")
    bench = {}
    with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
        report_performance(bt, bench, label=f"{STRATEGY_NAME} (합성 예행연습)")
        uni.report_attrition()
    with PIPE.stage("SMOKE.POLICY", "[합성] 정책 캘린더", "L2", budget_s=60, critical=False):
        cal = build_policy_calendar()
        report_policy(cal, S["months"], [p["id"] for p in active_packs()])
    with PIPE.stage("SMOKE.ROBUST", "[합성] 강건성 R1~R11", "L5", budget_s=1800, critical=False):
        keep_kill = STOP_ON_KILL_CRITERIA
        globals()["STOP_ON_KILL_CRITERIA"] = False   # 예행연습에서는 킬로 멈추지 않는다
        try:
            R1_leakage(P, S["months"], uni, S["sec"], _run)
            R2_tp_vs_naive(P, _run)
            R3_orthogonal(P, bt, S["months"])
            R4_placebo(P, n_iter=200)
            R10_policy_falsify(P, cal, S["months"], _run)
            R5_ablation(P, _run)
            R11_pack_corr(P)
            R6_pbo_dsr(bt)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, _run)
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = keep_kill
        report_robustness()
    with PIPE.stage("SMOKE.REPORT", "[합성] 해석표 · 진단 카드", "L6", budget_s=120, critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, S["sec"])
    LOG.ok("full_chain 예행연습 완료 — 백테스트·성과검증·강건성·해석표·진단카드가 모두 "
           "정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 동일한 출력이 실데이터로 나옵니다.")
    ROBUST_RESULTS.clear()
    return True
