

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-I  합성데이터 엔드투엔드 스모크 + 실경로 리허설                                        ║
# ║                                                                                          ║
# ║  두 검증은 서로 다른 것을 본다:                                                            ║
# ║   · 스모크  : 네트워크 없이 '계산경로'(피처→스코어→선정→백테스트→리포트)를 증명한다.        ║
# ║   · 리허설 : 네트워크만 가짜로 두고 '수집·정제 함수'를 실물 실행한다.                       ║
# ║  스모크만 믿으면 수집부 한 줄 때문에 수 시간짜리 실행이 2분 만에 죽는다. 반대도 마찬가지다. ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def make_synthetic(n_codes: int = 200, n_quarters: int = 28, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    end = as_ts(BACKTEST_END)
    q_end = [as_ts(f"{y}-{m:02d}-01") for y in range(end.year - 9, end.year + 1)
             for m in REBAL_MONTHS]
    q_end = [d for d in q_end if d <= end][-n_quarters:]
    start = q_end[0] - pd.DateOffset(months=15)
    days = pd.bdate_range(start, end)

    codes = [f"{i:05d}0" for i in range(1, n_codes + 1)]
    sectors = rng.choice(["화학", "전자부품", "건설", "기계", "소프트웨어", "제약"], n_codes)
    quality = rng.normal(size=n_codes)                       # 진짜 알파를 심는다

    listing = [days[0] - pd.DateOffset(years=int(rng.integers(2, 12))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 14), replace=False):
        listing[i] = days[int(rng.integers(60, len(days) - 300))]
    delist: List[Any] = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(2, n_codes // 12), replace=False):
        delist[i] = days[int(rng.integers(300, len(days) - 30))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": sectors,
                        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)], "src": "synthetic"})

    px_rows = []
    for i, c in enumerate(codes):
        drift = 0.0004 + 0.0009 * quality[i]
        r = rng.normal(drift, 0.026, len(days))
        p = np.exp(np.cumsum(r)) * float(rng.lognormal(8.6, 0.6))
        vol = rng.lognormal(10.5, 1.0, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days,
            "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * (1 + np.abs(rng.normal(0, 0.012, len(days)))),
            "low": p * (1 - np.abs(rng.normal(0, 0.012, len(days)))),
            "close": p, "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    keep = pd.Series(True, index=px.index)
    for i, c in enumerate(codes):
        m = px["code"] == c
        keep &= ~(m & (px["date"] < listing[i]))
        if pd.notna(delist[i]):
            keep &= ~(m & (px["date"] > delist[i]))
    px = px[keep].reset_index(drop=True)

    fin_rows, sh_rows = [], []
    for i, c in enumerate(codes):
        rev = float(rng.lognormal(24.5, 1.0))
        sh = float(rng.lognormal(16.0, 0.6))
        for q in pd.date_range(start, end, freq="QE"):
            rev *= (1 + 0.015 * quality[i] + rng.normal(0, 0.05))
            sh *= (1 + max(0.0, rng.normal(0.004 - 0.004 * quality[i], 0.01)))
            eq = rev * (0.7 + 0.1 * quality[i])
            fin_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "period_end": q,
                "knowledge_date": q + pd.Timedelta(days=46),
                "revenue_ttm": rev, "cogs_ttm": rev * (0.74 - 0.03 * quality[i]),
                "gross_profit_ttm": rev * (0.26 + 0.03 * quality[i]),
                "op_income_ttm": rev * (0.06 + 0.025 * quality[i]),
                "op_income_q": rev * 0.25 * (0.06 + 0.025 * quality[i]),
                "net_income_ttm": rev * (0.04 + 0.02 * quality[i]),
                "cfo_ttm": rev * (0.07 + 0.025 * quality[i]),
                "capex_ttm": rev * 0.05 * (1 + 0.2 * rng.normal()),
                "rnd_ttm": rev * max(0.005, 0.02 + 0.012 * quality[i]),
                "tax_expense_ttm": rev * 0.012, "pretax_income_ttm": rev * 0.055,
                "assets": rev * 1.5, "liabilities": rev * (0.8 - 0.1 * quality[i]),
                "equity": eq, "capital_stock": eq * 0.4, "cash": rev * 0.12,
                "st_debt": rev * 0.15, "lt_debt": rev * 0.2, "bonds": 0.0, "lease_liab": 0.0,
            })
            sh_rows.append({"corp_code": sec["corp_code"].iloc[i],
                            "bsns_year": int(q.year), "reprt_code": REPRT_CODES["FY"],
                            "shares_issued": sh, "shares_treasury": sh * 0.01,
                            "period_end": q, "knowledge_date": q + pd.Timedelta(days=46)})
    fin = pit_frame(pd.DataFrame(fin_rows), "period_end", "knowledge_date", source="synthetic")
    shares = pit_frame(pd.DataFrame(sh_rows), "period_end", "knowledge_date", source="synthetic")

    cap_rows = []
    for i, c in enumerate(codes):
        for q in q_end:
            cap_rows.append({"code": c, "snap_date": q - pd.Timedelta(days=3),
                             "mktcap": float(rng.lognormal(24.0, 1.2)),
                             "shares": float(rng.lognormal(16.0, 0.6))})
    snaps = pd.DataFrame(cap_rows)

    dis_rows, fact_rows = [], []
    for i, c in enumerate(codes):
        for q in q_end:
            if rng.random() < 0.10 + 0.12 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i], "stock_code": c,
                                 "rcept_no": sha1_str(c, q)[:14],
                                 "rcept_dt": q - pd.Timedelta(days=20),
                                 "report_nm": "단일판매ㆍ공급계약체결", "event": "supply_contract",
                                 "pblntf_ty": "I"})
            if rng.random() < 0.05 + 0.06 * max(-quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i], "stock_code": c,
                                 "rcept_no": sha1_str(c, q, "cb")[:14],
                                 "rcept_dt": q - pd.Timedelta(days=25),
                                 "report_nm": "전환사채권발행결정", "event": "cb_issue",
                                 "pblntf_ty": "B"})
        for y in sorted({d.year for d in q_end}):
            fact_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "bsns_year": y,
                "rcept_no": sha1_str(c, y, "ar")[:14],
                "rcept_dt": as_ts(f"{y}-03-25"), "parse_status": "ok",
                "patents": float(max(0, 10 + 4 * quality[i] + rng.normal(0, 2))),
                "rnd_headcount": float(max(1, 30 + 12 * quality[i] + rng.normal(0, 5))),
                "gov_rnd_facts": float(rng.random() < 0.15 + 0.12 * max(quality[i], 0)),
                "related_sales_ratio": float(np.clip(0.12 - 0.05 * quality[i] + rng.normal(0, 0.06), 0, 0.9)),
                "related_purchase_ratio": float(np.clip(0.08 + rng.normal(0, 0.04), 0, 0.9)),
                "contingent_amt": float(max(0.0, rng.lognormal(20, 1.2))),
                "lawsuit_amt": float(max(0.0, rng.lognormal(18, 1.5))) if rng.random() < 0.2 else 0.0,
                "lawsuit_new": float(rng.random() < 0.08),
                "audit_emphasis": float(rng.random() < 0.06 + 0.05 * max(-quality[i], 0)),
                "major_holder_pct": float(np.clip(0.35 + 0.08 * quality[i] + rng.normal(0, 0.12), 0.02, 0.8)),
                "sect_ip": True, "sect_rnd": True, "sect_related": True, "sect_contingent": True,
                "sect_lawsuit": True, "sect_audit": True, "sect_holder": True})
    dis = pd.DataFrame(dis_rows)
    dis["knowledge_date"] = as_ts_series(dis["rcept_dt"]) + pd.Timedelta(days=1)
    dis = pit_frame(dis, "rcept_dt", "knowledge_date", source="synthetic")
    facts = pd.DataFrame(fact_rows)

    flow_rows = []
    for i, c in enumerate(codes):
        for q in q_end:
            if rng.random() < 0.55:                            # 45% 는 비영 관측이 없다(현실 반영)
                continue
            flow_rows.append({"code": c, "rebal": q,
                              "foreign_net": float(rng.normal(0, 1) * 1e8 * (1 + quality[i])),
                              "inst_net": float(rng.normal(0, 1) * 1e8),
                              "flow_src": "synthetic"})
    flows = pd.DataFrame(flow_rows)

    brokers = MAJOR_BROKERS[:8] + MINOR_BROKERS[:8]
    rep_rows, link_rows, txt_rows, tone_rows = [], [], [], []
    for q in q_end:
        for _ in range(int(rng.integers(60, 140))):
            i = int(rng.integers(0, n_codes))
            b = brokers[int(rng.integers(0, len(brokers)))]
            bid, bname = normalize_broker(b)
            nm = f"애널{int(rng.integers(0, 24)):02d}"
            d = q - pd.Timedelta(days=int(rng.integers(5, 80)))
            uid = sha1_str("syn", codes[i], d, nm)
            tp = float(np.exp(rng.normal(9.6, 0.5)) * (1 + 0.15 * quality[i]))
            rep_rows.append({"report_uid": uid, "source": "synthetic", "src_report_id": uid[:10],
                             "pub_date": d, "category": "company",
                             "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                             "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                             "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                             "opinion": "BUY", "pdf_url": None, "detail_url": None,
                             "event_date": d, "knowledge_date": d})
            link_rows.append({"report_uid": uid, "name": nm, "broker_id": bid,
                              "broker_name": bname, "role": "lead", "link_method": "list_field",
                              "link_conf": 0.98, "pub_date": d, "stock_code": codes[i],
                              "target_price": tp, "opinion": "BUY", "name_norm": nm,
                              "analyst_id": sha1_str("analyst", bid, nm)[:14]})
            txt_rows.append({"report_uid": uid, "pub_date": d, "broker_id": bid,
                             "stock_code": codes[i], "text": "합성 본문", "n_sent": 20,
                             "is_irc": float(rng.random() < 0.05)})
            tone_rows.append({"report_uid": uid, "pub_date": d, "stock_code": codes[i],
                              "tone": float(np.clip(0.15 * quality[i] + rng.normal(0, 0.3), -1, 1)),
                              "n_sent": 20, "model_epoch": as_ts(f"{d.year}-01-01")})
    rep = pd.DataFrame(rep_rows)
    links = pd.DataFrame(link_rows)
    rtext = pd.DataFrame(txt_rows)
    tone = pd.DataFrame(tone_rows)

    return {"sec": sec, "px": px, "fin": fin, "shares": shares, "snaps": snaps,
            "dis": dis, "facts": facts, "flows": flows, "reports": rep, "links": links,
            "rtext": rtext, "tone": tone, "quality": quality}


def _assemble_panel(S: dict, cal: pd.DataFrame, flows: pd.DataFrame) -> Tuple[pd.DataFrame, Any]:
    """합성/실데이터 공통 조립 경로. 스모크와 본 실행이 같은 코드를 타야 검증에 의미가 있다."""
    uni = Universe(S["sec"], pd.DataFrame(columns=["snap_date", "code", "market"]), S["px"])
    cap = build_cap_panel(cal, S["px"], S["snaps"], S["shares"], S["sec"])
    adtv = build_adtv_panel(cal, S["px"])
    G = build_universe_grid(uni, cal, cap, adtv, S["sec"])
    fq = build_quarterly_fundamentals(S["fin"], S["shares"])
    G = attach_fundamentals_q(G, fq, S["sec"])
    U = select_u1000(G)
    U = build_sector_cells(U)
    U = axis_V(U)
    U = axis_Q(U)
    U = axis_F(U, flows)
    U = build_nonfin_panel(U, S["facts"], S["dis"], fq, S["sec"])
    tp = build_tp_revision(S["links"], U, cal)
    U = U.merge(tp[["code", "rebal", "tp_revision"]], on=["code", "rebal"], how="left")
    tpanel = build_tone_panel(S["tone"], U, cal, exclude_irc=IRC_EXCLUDE, T=S.get("rtext"))
    U = U.merge(tpanel[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                on=["code", "rebal"], how="left")
    U["mom12_1"] = np.nan
    U = orthogonalize_tone(U)
    U = build_exclusion_flags(U)
    U = apply_filter3a(U)
    return downcast_q(U), uni


def run_selftest(full_chain: bool = False) -> bool:
    LOG.banner("① 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수십 초)"
               + (" · full_chain: 실험·강건성·보고서까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    keep = LOG.min
    try:
        S = make_synthetic()
        LOG.info(f"합성 데이터: 종목 {len(S['sec'])} · 일봉 {len(S['px']):,} · "
                 f"재무 {len(S['fin']):,} · 리포트 {len(S['reports']):,} · 수급 {len(S['flows']):,}")
        set_trading_days(S["px"])
        cal = qvf_rebal_calendar(S["px"], BACKTEST_START, BACKTEST_END)
        P, uni = _assemble_panel(S, cal, S["flows"])
        # ★ 합성 유니버스는 200종목뿐이라 U200_N(=200) 을 그대로 쓰면 U-200 이 곧 U-1000 이
        #   되어 3변형이 항상 동일해진다(중복률 1.000). 그러면 §5.6/§9-C3 경로가 실제로
        #   검증되지 않는다. 유니버스 크기에 비례해 줄여 '진짜 부분집합'으로 만든다.
        _u_avg = float(P.groupby("rebal", observed=True).size().mean())
        _n200 = int(max(20, min(U200_N, round(_u_avg * 0.35))))
        P = build_u200(P, variants=VARIANTS, n=_n200)
        set_delist_map(uni.delisting_map())
        ep = build_exec_prices(cal, S["px"])
        fwd = build_forward_returns(ep, cal, uni.delisting_map(), S["px"])

        cmp_res = report_variant_comparison(P, VARIANTS, rep_cov=P[["code", "rebal", "n_reports"]])
        for v in VARIANTS:
            P = apply_filter2(P, v)
        verify_missing_tolerance(P, "VQ")
        P["_sel"] = build_final_selection(P, "VQ", stage="full")
        bt = run_qbacktest(P, cal, "_sel", fwd, label="SMOKE")
        st = qperf_stats(bt["returns"])
        dur = time.time() - t0
        ok = (len(P) > 0 and len(bt["returns"]) > 0 and bool(st) and
              np.isfinite(st.get("CAGR", np.nan)))
        LOG.table([["패널 행수", f"{len(P):,}"],
                   ["U-1000 평균", f"{P.groupby('rebal', observed=True).size().mean():,.0f}"],
                   ["백테스트 분기수", f"{len(bt['returns'])}"],
                   ["평균 보유종목", f"{st.get('평균종목수', float('nan')):.1f}"],
                   ["합성 CAGR(비용후)", f"{st.get('CAGR', float('nan'))*100:+.2f}%"],
                   ["합성 Sharpe", f"{st.get('Sharpe', float('nan')):.3f}"],
                   ["소요시간", f"{dur:.2f}초"]],
                  ["항목", "값"], ["l", "r"],
                  title="스모크 결과 (성과 수치는 의미 없음 — 배관 검증용)")
        if not ok:
            LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
            return False
        LOG.ok(f"스모크 통과 ({dur:.2f}초) — 유니버스→축→필터→백테스트 경로 정상")
        if not full_chain:
            return True

        LOG.warn("아래 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 아니라 "
                 "'출력물이 제대로 나오는지'를 보여주는 예행연습입니다. 해석하지 마세요.")
        names = []
        for v in VARIANTS:
            b = run_experiment(P, cal, fwd, v, u200_n=_n200, label=f"{v}-full")
            summarize_experiment(f"{v}-full", b, b["panel"], v, fwd, "1차→2차→3-A")
            names.append(f"{v}-full")
        abl = [("X1", dict(stage="x1"), "1차만"),
               ("X2", dict(use_tone=False, use_nonfin=False), "배제플래그만"),
               ("X3", dict(use_tone=False), "ΔNONFIN만"),
               ("X4", dict(use_rule3a=False), "3-A 없음")]
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, "VQ", u200_n=_n200, label=nm, **kw)
            summarize_experiment(nm, b, b["panel"], "VQ", fwd, desc)
            names.append(nm)
        report_experiment_table([f"{v}-full" for v in VARIANTS], "주 실험 (합성 예행연습)")
        report_experiment_table([n for n, _k, _d in abl], "보조 어블레이션 (합성 예행연습)")
        fdr = report_bh_fdr(names)
        R_subperiod(bt, "SMOKE")
        R_size_quartile(bt, P, "SMOKE")
        report_robustness()
        report_phase0(0.95, 0.60, 0.85, 0.35, 120)
        report_flow_verdict(cmp_res, fdr_pass=fdr)
        report_preregistration_kill([f"{v}-full" for v in VARIANTS], "VQ-full", "X1")
        report_final_holdings(P, "VQ", "_sel", S["sec"], top_n=12)
        LOG.ok("full_chain 예행연습 완료 — 백테스트·성과검증·강건성·판정표가 모두 정상 출력됩니다.")
        return True
    finally:
        LOG.min = keep
        EXPERIMENTS.clear()
        ROBUST_RESULTS.clear()
        PHASE0.clear()


# ── 실경로 리허설 ───────────────────────────────────────────────────────────────────────────
def run_rehearsal(strict: bool = True) -> bool:
    """네트워크만 가짜로 두고 실제 수집·정제 함수를 실행한다.

    ★ 스모크는 합성 '결과물'을 직접 만들어 넣으므로 수집 함수의 코드는 한 줄도 실행하지
      않는다. 실제로 죽는 곳은 대개 거기다(응답 구조 변경, 빈 응답, 컬럼명 오타…).
    """
    LOG.banner("② 실경로 리허설", "네트워크만 가짜로 두고 수집·정제 함수를 실물 실행한다")
    orig_get, orig_post, orig_json = http_get, http_post, http_json
    calls: Counter = Counter()

    def fake_get(url, source="generic", **kw):
        calls[source] += 1
        if kw.get("as_bytes"):
            return b""                        # ZIP/PDF 경로: 빈 바이트 → 실패 분기 검증
        return ""                              # HTML/JSON 경로: 빈 문자열

    def fake_post(url, source="generic", **kw):
        calls[f"{source}:POST"] += 1
        return ""

    def fake_json(url, source="generic", **kw):
        calls[f"{source}:JSON"] += 1
        return None

    checks: List[Tuple[str, str]] = []
    # ★ 키가 비어 있으면 수집 함수 대부분이 첫 줄에서 early-return 해 버려 정작 검증하려던
    #   본문 경로가 한 줄도 실행되지 않는다. 가짜 키를 주입해 '응답이 비었을 때'의 분기를
    #   실제로 태운다. 네트워크는 이미 가짜이므로 외부로 나가는 요청은 없다.
    _keep_key = DART_API_KEY
    globals()["DART_API_KEY"] = _keep_key or "REHEARSAL_FAKE_KEY_0000000000000000000000"
    globals()["http_get"] = fake_get
    globals()["http_post"] = fake_post
    globals()["http_json"] = fake_json
    try:
        cases = [
            ("공시목록 스윕", lambda: fetch_disclosures_qvf("2024-01-01", "2024-03-31")),
            ("DART 주식총수", lambda: fetch_dart_share_counts(["00126380"], [2024])),
            ("사업보고서 본문", lambda: fetch_annual_report_facts(pd.DataFrame(
                {"corp_code": ["00126380"], "bsns_year": [2024],
                 "rcept_no": ["20240101000001"], "rcept_dt": [as_ts("2024-03-25")]}))),
            ("시총 스냅샷", lambda: fetch_krx_cap_snapshots([as_ts("2024-03-01")])),
            ("XML→텍스트 판별", lambda: _xml_to_text(b"not a zip at all")),
            ("완료형 사실 판정", lambda: (
                is_completed_fact("2024년 3월 15일 특허 3건을 등록하였다."),
                is_completed_fact("2025년까지 특허 10건을 등록할 예정이다."))),
            ("정형문구 제거", lambda: strip_boilerplate(
                "본 자료는 투자 참고용입니다. 홍길동 연구원 hong@sec.co.kr 실적이 개선되었다.")),
        ]
        for nm, fn in cases:
            try:
                r = fn()
                n = len(r) if hasattr(r, "__len__") else 1
                checks.append((nm, f"✔ 정상 반환 (크기 {n})"))
            except Exception as e:                            # noqa
                checks.append((nm, f"✘ {type(e).__name__}: {str(e)[:60]}"))
        # 완료형 사실 판정의 의미론을 확인 (빈 응답에도 죽지 않는 것과는 별개 문제다)
        if not (is_completed_fact("2024년 3월 15일 특허 3건을 등록하였다.") and
                not is_completed_fact("2025년까지 특허 10건을 등록할 예정이다.")):
            checks.append(("완료형/미래형 구분", "✘ §6.1 추출 원칙 위반"))
        else:
            checks.append(("완료형/미래형 구분", "✔ 미래형 문장 제외 확인"))
        s = strip_boilerplate("본 자료는 투자 참고용입니다. 홍길동 연구원 hong@sec.co.kr 실적이 개선되었다.")
        checks.append(("면책·서명 제거", "✔ 제거됨" if ("연구원" not in s and "@" not in s)
                       else "✘ 잔존 — 증권사 지문 누출 위험"))
    finally:
        globals()["http_get"] = orig_get
        globals()["http_post"] = orig_post
        globals()["http_json"] = orig_json
        globals()["DART_API_KEY"] = _keep_key

    LOG.table([[nm, res] for nm, res in checks], ["수집·정제 함수", "결과"], ["l", "l"], maxw=64)
    bad = [nm for nm, r in checks if r.startswith("✘")]
    if bad:
        msg = f"리허설 실패: {bad} — 실데이터 수집을 시작하면 같은 지점에서 죽습니다."
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"리허설 통과 — 빈 응답·비정상 응답에도 수집부가 죽지 않고 폴백합니다 "
           f"(가짜 호출 {sum(calls.values())}건)")
    return True
