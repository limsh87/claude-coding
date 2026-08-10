

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — §11 실행 순서 [1]~[15]                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f              # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML             # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                        f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def build_momentum(cal: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """12-1 모멘텀 (직전 1개월 제외 12개월 수익률) — ΔTONE 직교화 설명변수."""
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values("date", kind="stable")
    R = px.rename(columns={"date": "px_date"})
    out = []
    for r in cal.itertuples(index=False):
        sd = as_ts(r.signal_date)
        anchors = {"p1": sd - pd.DateOffset(months=1), "p12": sd - pd.DateOffset(months=12)}
        L = pd.DataFrame({"code": sorted(px["code"].unique())})
        vals = {}
        for k, dt in anchors.items():
            LL = L.assign(t=dt).sort_values("t", kind="stable")
            M = pd.merge_asof(LL, R, left_on="t", right_on="px_date", by="code",
                              direction="backward", tolerance=pd.Timedelta(days=20))
            vals[k] = M.set_index("code")["close"]
        m = (vals["p1"] / vals["p12"] - 1.0).rename("mom12_1").reset_index()
        m["rebal"] = r.rebal
        out.append(m)
    if not out:
        return pd.DataFrame(columns=["code", "rebal", "mom12_1"])
    return downcast_q(pd.concat(out, ignore_index=True))


def collect_core(cal_hint: Optional[pd.DataFrame] = None) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    months = month_range(as_ts(BACKTEST_START) - pd.DateOffset(months=18), BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스 입력", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    with PIPE.stage("L1.PX", "가격 · 거래대금 (폴백 체인)", "L1", budget_s=2400):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        set_trading_days(px)

    with PIPE.stage("L1.CAL", "분기 리밸런싱 캘린더 (§4)", "L1", budget_s=60):
        ctx["cal"] = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.CAP", "PIT 시가총액 스냅샷", "L1", budget_s=900, critical=False):
        ctx["snaps_cap"] = fetch_krx_cap_snapshots(list(as_ts_series(ctx["cal"]["signal_date"])))

    with PIPE.stage("L1.DART", "DART 재무 · 주식총수", "L1", budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 4, as_ts(BACKTEST_END).year + 1))
        multi = fetch_dart_multi_accounts(corps, years)
        fs = fetch_dart_financials(corps, years)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["fin"] = apply_t_plus_1(fin, "재무제표")
        ctx["shares"] = fetch_dart_share_counts(corps, years)
        if len(ctx["fin"]):
            PIT.register("dart_financials", ctx["fin"], key_cols=["corp_code"])

    with PIPE.stage("L1.DIS", "DART 공시목록 스윕 (A·B·F·I)", "L1", budget_s=2400, critical=False):
        ctx["dis"] = fetch_disclosures_qvf(BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.FLOW", "외국인·기관 순매수 (§5.4)", "L1", budget_s=1800, critical=False):
        ctx["flows"] = fetch_flow_netbuy(ctx["cal"], ctx["px"], window=FLOW_WINDOW_DAYS)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=5400, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
                 "로컬 캐시/분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                frames.append(naver_enrich_detail(nv))
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep):
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    ctx.setdefault("reports", pd.DataFrame())
    ctx.setdefault("links", pd.DataFrame())
    ctx.setdefault("analysts", pd.DataFrame())
    return ctx


def build_panel_pass1(ctx: dict, cal: pd.DataFrame, flows: pd.DataFrame) -> Tuple[pd.DataFrame, Any]:
    """[2]~[5] — 유니버스 · V/Q/F 축 · 1차필터까지. DART 본문 사실은 아직 필요하지 않다."""
    uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                   ctx["px"])
    cap = build_cap_panel(cal, ctx["px"], ctx.get("snaps_cap", pd.DataFrame()),
                          ctx.get("shares", pd.DataFrame()), ctx["sec"])
    adtv = build_adtv_panel(cal, ctx["px"])
    G = build_universe_grid(uni, cal, cap, adtv, ctx["sec"])
    fq = build_quarterly_fundamentals(ctx.get("fin", pd.DataFrame()), ctx.get("shares", pd.DataFrame()))
    ctx["fq"] = fq
    G = attach_fundamentals_q(G, fq, ctx["sec"])
    U = select_u1000(G)
    U = build_sector_cells(U)
    U = axis_V(U)
    U = axis_Q(U)
    U = axis_F(U, flows)
    U = build_u200(U, variants=VARIANTS, n=U200_N)
    return downcast_q(U), uni


def build_panel_pass2(P: pd.DataFrame, ctx: dict, cal: pd.DataFrame) -> pd.DataFrame:
    """[6]~[10] — DART 하드팩트 · TONE · 2차필터 입력 · 3-A 규칙."""
    P = build_nonfin_panel(P, ctx.get("facts", pd.DataFrame()), ctx.get("dis", pd.DataFrame()),
                           ctx.get("fq", pd.DataFrame()), ctx["sec"])
    P = attach_major_holder(P, ctx.get("holder", pd.DataFrame()), ctx["sec"])
    mom = build_momentum(cal, ctx["px"])
    P = P.merge(mom, on=["code", "rebal"], how="left")
    tp = build_tp_revision(ctx.get("links", pd.DataFrame()), P, cal)
    P = P.merge(tp[["code", "rebal", "tp_revision"]], on=["code", "rebal"], how="left")
    tpanel = build_tone_panel(ctx.get("tone", pd.DataFrame()), P, cal,
                              exclude_irc=IRC_EXCLUDE, T=ctx.get("rtext"))
    P = P.merge(tpanel[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                on=["code", "rebal"], how="left")
    P = orthogonalize_tone(P)
    P = build_exclusion_flags(P)
    P = apply_filter3a(P)
    return downcast_q(P)


def compute_phase0(P: pd.DataFrame, ctx: dict, parse_rate: float) -> dict:
    fin_cov = float(col(P, "equity").notna().mean()) if len(P) else float("nan")
    obs = P[["foreign_net", "inst_net"]].notna().any(axis=1) if "foreign_net" in P.columns \
        else pd.Series(False, index=P.index)
    flow_cov = float(obs.mean()) if len(P) else float("nan")
    u200_any = pd.Series(False, index=P.index)
    for v in VARIANTS:
        if f"u200_{v}" in P.columns:
            u200_any |= P[f"u200_{v}"].fillna(False).astype(bool)
    sub = P[u200_any]
    rep_cov = float((pd.to_numeric(col(sub, "n_reports"), errors="coerce").fillna(0) > 0).mean()) \
        if len(sub) else float("nan")
    pair = float("nan")
    if len(sub) and "n_reports" in sub.columns:
        s = sub[["code", "rebal", "n_reports"]].copy()
        s["has"] = pd.to_numeric(s["n_reports"], errors="coerce").fillna(0) > 0
        s = s.sort_values(["code", "rebal"], kind="stable")
        prev = s.groupby("code", observed=True)["has"].shift(1)
        pair = float((s["has"] & prev.fillna(False)).groupby(s["rebal"]).sum().mean())
    return report_phase0(fin_cov, flow_cov, parse_rate, rep_cov, pair)


def main() -> dict:
    t_all = time.time()
    global VAULT, DQUOTA, DBUDGET
    LOG.banner(f"QVF-FUNNEL v1.0 — {STRATEGY_NAME}",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "캐시 연결 (드라이브 쓰기 + 로컬 미러 읽기)", "L0", budget_s=600):
        root, mode, mirrors = qvf_resolve_roots()
        VAULT = QVFVault(root, mode, mirrors)
        globals()["VAULT"] = VAULT
        VAULT.report_roots()
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"쓰기 루트 여유 공간 {free:.1f} GB")
            if free < 3:
                LOG.warn("여유 공간이 3GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        adopt_dirs = []
        for d in GDRIVE_ADOPT_DIRS:
            adopt_dirs.append(d if os.path.isabs(d) else os.path.join(os.path.dirname(VAULT.root), d))
        adopt_dirs += [VAULT.root] + list(VAULT.mirrors)
        VAULT.adopt_scan(adopt_dirs)
        DQUOTA = DartQuota(VAULT)
        globals()["DQUOTA"] = DQUOTA
        globals()["DBUDGET"] = DQUOTA       # 공용 코어(dart_api)가 참조하는 이름에 주입
        DQUOTA.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 Q1~Q12", "L0", budget_s=180):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=600):
        run_rehearsal(strict=True)

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_core()
    cal = ctx["cal"]

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (보고서↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    with PIPE.stage("L1.PANEL1", "[2]~[5] 유니버스 · V/Q/F 축 · 1차필터", "L1", budget_s=1800):
        P, uni = build_panel_pass1(ctx, cal, ctx.get("flows", pd.DataFrame()))

    with PIPE.stage("L1.FACTS", "[6] DART 하드팩트 (U-200 합집합 대상)", "L1",
                    budget_s=5400, critical=False):
        u_any = pd.Series(False, index=P.index)
        for v in VARIANTS:
            u_any |= P[f"u200_{v}"].fillna(False).astype(bool)
        need_codes = set(P.loc[u_any, "code"].astype(str))
        LOG.info(f"U-200 3변형 합집합 {len(need_codes):,}종목 — DART 본문·리포트 본문 수집을 "
                 f"이 집합으로 한정합니다(전 종목이면 호출량이 수 배가 됩니다).")
        ctx["need_codes"] = need_codes
        dis = ctx.get("dis", pd.DataFrame())
        targets = pd.DataFrame(columns=["corp_code", "bsns_year", "rcept_no", "rcept_dt"])
        if len(dis):
            c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
                   .set_index("code")["corp_code"].astype(str).to_dict())
            want_corp = {c2c[c] for c in need_codes if c in c2c}
            ar = dis[dis["report_nm"].astype(str).str.contains("사업보고서", na=False)].copy()
            if "corp_code" in ar.columns and want_corp:
                ar = ar[ar["corp_code"].astype(str).isin(want_corp)]
            if len(ar):
                ar["bsns_year"] = as_ts_series(ar["rcept_dt"]).dt.year - 1
                targets = ar[["corp_code", "bsns_year", "rcept_no", "rcept_dt"]].drop_duplicates("rcept_no")
        facts, pstats = fetch_annual_report_facts(targets)
        ctx["facts"] = facts
        ctx["parse_rate"] = report_parse_rate(facts, pstats)
        # 3-A 의 '최대주주 지분율 < 15%' 는 하드 규칙인데 본문 표 레이아웃에 따라 추출 실패가
        # 잦다. 실패한 (회사, 연도) 에만 구조화 엔드포인트로 보강한다(전량 호출은 낭비).
        need_h = pd.DataFrame(columns=["corp_code", "bsns_year"])
        if len(facts):
            miss = facts[pd.to_numeric(facts.get("major_holder_pct"), errors="coerce").isna()]
            if len(miss):
                need_h = miss[["corp_code", "bsns_year"]].dropna().drop_duplicates()
        elif len(targets):
            need_h = targets[["corp_code", "bsns_year"]].dropna().drop_duplicates()
        ctx["holder"] = fetch_major_holder_stake(need_h)

    with PIPE.stage("L1.TONE", "[7] 리포트 본문 · TONE 분류기 (확장윈도우)", "L1",
                    budget_s=5400, critical=False):
        T = build_report_text_table(ctx.get("reports", pd.DataFrame()), ctx.get("need_codes"))
        ctx["rtext"] = T
        verify_boilerplate_leak(T)
        lab = build_car_labels(T, ctx["px"])
        ctx["tone"] = build_tone_scores(T, lab)

    with PIPE.stage("L2.PANEL2", "[8]~[10] 하드팩트 · TONE · 배제 · 3-A", "L2", budget_s=1200):
        P = build_panel_pass2(P, ctx, cal)
        VAULT.put_table(f"l1_panel_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="QVF panel")

    with PIPE.stage("L1.EXEC", "체결가 · 보유수익률", "L1", budget_s=600):
        set_delist_map(uni.delisting_map())
        ep = build_exec_prices(cal, ctx["px"])
        fwd = build_forward_returns(ep, cal, uni.delisting_map(), ctx["px"])
        ctx["fwd"] = fwd

    with PIPE.stage("L6.PHASE0", "[1] Phase 0 게이트 (사후 실측)", "L6", budget_s=120,
                    critical=False):
        g = compute_phase0(P, ctx, ctx.get("parse_rate", float("nan")))
        if g.get("fin_cov", {}).get("pass") is False:
            raise KillCriteria(
                f"fin_cov {100*g['fin_cov']['value']:.1f}% < 90% — §2.2 규정상 1차필터가 "
                f"성립하지 않으므로 전략을 중단합니다. DART 재무 콜드빌드를 완료한 뒤 "
                f"재실행하면 정확히 이 지점부터 이어받습니다.")

    with PIPE.stage("L2.CMP", "[5] 3변형 비교 (중간 보고)", "L2", budget_s=300):
        cmp_res = report_variant_comparison(P, VARIANTS, rep_cov=P[["code", "rebal", "n_reports"]])
        ctx["cmp"] = cmp_res

    with PIPE.stage("L2.F2", "[9] 2차필터 · 결측 허용 검증", "L2", budget_s=600):
        for v in VARIANTS:
            P = apply_filter2(P, v)
        for v in VARIANTS:
            verify_missing_tolerance(P, v)

    with PIPE.stage("L2.CAUSAL", "[8] 인과 순서 점검 (§6.4)", "L2", budget_s=180, critical=False):
        ctx["causal"] = check_causal_order(ctx.get("reports", pd.DataFrame()),
                                           ctx.get("dis", pd.DataFrame()), P)

    with PIPE.stage("L3.MAIN", "[11] 주 실험 3개 백테스트", "L3", budget_s=1800):
        main_names = []
        for v in VARIANTS:
            bt = run_experiment(P, cal, fwd, v, label=f"{v}-full", quiet=True)
            summarize_experiment(f"{v}-full", bt, bt["panel"], v, fwd, "1차→2차(DART+TONE)→3-A")
            main_names.append(f"{v}-full")
            ctx[f"bt_{v}"] = bt
        report_experiment_table(main_names, "주 실험 (§8.2) — 1차필터 3변형 × 전체 파이프라인")

    best = max(main_names,
               key=lambda n: (EXPERIMENTS[n]["net"].get("Sharpe", -1e9)
                              if np.isfinite(EXPERIMENTS[n]["net"].get("Sharpe", np.nan)) else -1e9))
    best_v = best.split("-")[0]
    LOG.ok(f"비용 차감 후 Sharpe 기준 최우수 변형: {best} "
           f"(Sharpe {EXPERIMENTS[best]['net'].get('Sharpe', float('nan')):.3f})")

    with PIPE.stage("L3.ABL", "[12] 보조 어블레이션 X1~X4", "L3", budget_s=1800, critical=False):
        abl = [("X1", dict(stage="x1"), "1차만 — 깔때기 자체의 기여"),
               ("X2", dict(use_tone=False, use_nonfin=False), "1차+배제플래그만 — 위험배제 효과"),
               ("X3", dict(use_tone=False), "1차+ΔNONFIN만 — 애널리스트 축 기여"),
               ("X4", dict(use_rule3a=False), "1차+2차, 3-A 없음 — 3-A 기여")]
        abl_names = []
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, best_v, label=nm, quiet=True, **kw)
            summarize_experiment(nm, b, b["panel"], best_v, fwd, desc)
            abl_names.append(nm)
        report_experiment_table(abl_names, f"보조 어블레이션 (§8.2) — 최우수 변형 {best_v} 기준")

    with PIPE.stage("L5.FDR", "[13] BH-FDR 다중검정 보정", "L5", budget_s=120, critical=False):
        ctx["fdr"] = report_bh_fdr(main_names + abl_names)

    with PIPE.stage("L5.ROBUST", "[13] 강건성 검사 (§8.4)", "L5", budget_s=4 * 3600, critical=False):
        bt_best = ctx.get(f"bt_{best_v}")
        R_subperiod(bt_best, best)
        R_size_quartile(bt_best, P, best)
        R_param_sensitivity(P, cal, fwd, best_v)
        R_weight_scheme(P, cal, fwd, best_v)

        def _rebuild_shift(sh: int, variant: str):
            cal2 = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END, shift_days=sh)
            fl2 = fetch_flow_netbuy(cal2, ctx["px"], window=FLOW_WINDOW_DAYS)
            P2, uni2 = build_panel_pass1(ctx, cal2, fl2)
            P2 = build_panel_pass2(P2, ctx, cal2)
            ep2 = build_exec_prices(cal2, ctx["px"])
            fwd2 = build_forward_returns(ep2, cal2, uni2.delisting_map(), ctx["px"])
            b = run_experiment(P2, cal2, fwd2, variant, label=f"shift{sh}", quiet=True)
            return qperf_stats(b["returns"])
        R_rebal_shift(_rebuild_shift, best_v)

        if "VQF" in VARIANTS:
            def _rebuild_flow(w: int):
                fl2 = fetch_flow_netbuy(cal, ctx["px"], window=w)
                P2 = axis_F(P.drop(columns=[c for c in ("Z_F", "zF_foreign", "zF_inst",
                                                        "flow_f", "flow_i", "float_cap")
                                            if c in P.columns]), fl2)
                b = run_experiment(P2, cal, fwd, "VQF", label=f"flow{w}", quiet=True)
                return qperf_stats(b["returns"])
            R_flow_window(_rebuild_flow)

        def _rebuild_irc(excl: bool, variant: str):
            tp2 = build_tone_panel(ctx.get("tone", pd.DataFrame()), P, cal,
                                   exclude_irc=excl, T=ctx.get("rtext"))
            P2 = P.drop(columns=[c for c in ("tone_q", "n_reports", "dTONE", "dTONE_resid")
                                 if c in P.columns])
            P2 = P2.merge(tp2[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                          on=["code", "rebal"], how="left")
            P2 = orthogonalize_tone(P2)
            b = run_experiment(P2, cal, fwd, variant, label=f"irc{int(excl)}", quiet=True)
            return qperf_stats(b["returns"])
        R_irc_split(_rebuild_irc, best_v)
        report_robustness()

    with PIPE.stage("L6.VERDICT", "[14] 수급 축 판정 · 사전등록 폐기조건", "L6", budget_s=120,
                    critical=False):
        ctx["flow_verdict"] = report_flow_verdict(ctx.get("cmp", {}), fdr_pass=ctx.get("fdr"))
        ctx["kill"] = report_preregistration_kill(main_names, best, "X1")

    with PIPE.stage("L6.REPORT", "[15] 최종 산출물", "L6", budget_s=300, critical=False):
        bench = qvf_benchmarks(cal, ctx["px"])
        if bench:
            R = ctx[f"bt_{best_v}"]["returns"].set_index("rebal")["ret"]
            rows = []
            for nm, b in bench.items():
                bb = b.reindex(R.index).fillna(0)
                ex = R.fillna(0) - bb
                _, t = hac_tstat(ex.to_numpy())
                rows.append([nm, f"{float((1+bb).prod()-1)*100:+.1f}%",
                             f"{float((1+R.fillna(0)).prod()-1)*100:+.1f}%",
                             f"{float(ex.mean())*100:+.3f}%p", f"{t:.2f}"])
            LOG.table(rows, ["벤치마크", "벤치 누적", "전략 누적", "분기평균 초과", "HAC t"],
                      ["l", "r", "r", "r", "r"], title=f"[{best}] 벤치마크 대비")
        P["_sel_best"] = build_final_selection(P, best_v, stage="full")
        ctx["holdings_last"] = report_final_holdings(P, best_v, "_sel_best", ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        for v in VARIANTS:
            b = ctx.get(f"bt_{v}")
            if b is None:
                continue
            p = os.path.join(outdir, f"returns_{v}_{stamp}.csv")
            b["returns"].to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
            VAULT.put_table(f"backtest_returns_{v}", b["returns"], scope="private",
                            domain="backtest", source=STRATEGY_ID)
        h = ctx.get("holdings_last")
        if h is not None and len(h):
            p = os.path.join(outdir, f"holdings_{best_v}_{stamp}.csv")
            h.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
        summ = pd.DataFrame([{"experiment": k, "desc": e.get("desc", ""),
                              **{f"net_{kk}": vv for kk, vv in (e.get("net") or {}).items()},
                              **{f"gross_{kk}": vv for kk, vv in (e.get("gross") or {}).items()},
                              "IC": e.get("IC"), "ICIR": e.get("ICIR"), "p": e.get("p")}
                             for k, e in EXPERIMENTS.items()])
        if len(summ):
            p = os.path.join(outdir, f"experiments_{stamp}.csv")
            summ.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
            VAULT.put_table("qvf_experiment_summary", summ, scope="private",
                            domain="backtest", source=STRATEGY_ID)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        if DQUOTA:
            DQUOTA.close()
            DQUOTA.report()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    PIPE.report_runtime()
    report_dataflow_map()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("§10.1 증거 등급 — 위 표의 모든 수치는 이 백테스트에서 산출된 실측값입니다. "
             "표본은 10년 40분기이며, 그 길이에서 나오는 통계적 불확실성은 방법론적 우려로 "
             "명시합니다. 수치 없는 낙관/비관 주장은 하지 않습니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "ctx": ctx, "experiments": dict(EXPERIMENTS)}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 사전등록 기준으로 중단", "§2.2 / §10.4 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
            if DQUOTA:
                DQUOTA.close()
        except Exception:
            pass
