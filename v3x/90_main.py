# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이션 — 이 파일 하나로 백테스트~강건성~해석표까지 전부 나온다                     ║
# ║                                                                                             ║
# ║  실패 지점 국소화: 모든 연산은 PIPE.stage 안에서만 돈다. 실패하면 자동으로                  ║
# ║  스테이지 ID · 계층 · 경과시간 · 직전 입출력 스냅샷 · 한글 진단힌트가 출력된다.             ║
# ║  런타임 실측은 Stage(...) 가 따로 기록한다(예산 대비 몇 배를 썼는가).                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def _months() -> "pd.DatetimeIndex":
    return pd.date_range(pd.Timestamp(BACKTEST_START) + pd.offsets.MonthEnd(0),
                         pd.Timestamp(BACKTEST_END), freq="ME")


def _make_runner(months, sec):
    """강건성 스위트가 백테스트를 반복 호출할 때 쓰는 러너.

    비용 시나리오(R9)를 위해 cost_override 를 받는다.
    """
    def runner(P: pd.DataFrame, months=months, label: str = "XCB",
               cost_override: "Optional[float]" = None) -> dict:
        global COMMISSION_BPS, SLIPPAGE_FLOOR
        prev = (COMMISSION_BPS, SLIPPAGE_FLOOR)
        if cost_override is not None:
            # 왕복 비용 목표치를 편도 수수료 + 스프레드 하한으로 배분한다.
            COMMISSION_BPS = max(0.1, cost_override * 10000 / 4.0)
            SLIPPAGE_FLOOR = cost_override / 4.0
        try:
            return run_backtest(P, months, sec, entry_col="xcb_uni", label=label, quiet=True)
        finally:
            COMMISSION_BPS, SLIPPAGE_FLOOR = prev
    return runner


def build_panel_xcb(months, sec, px_m, px_d, mcap, cx, mapping,
                    fin, emp, dis, reports) -> "pd.DataFrame":
    """L1 — 원시 센서만. 정규화는 여기서 하지 않는다(전부 L2)."""
    P = build_base_panel(months, px_m, px_d, sec, mcap)
    P["ym"] = as_ts_series(P["month"]).astype("datetime64[ns]")
    # ★ 가격패널은 20일 평균거래대금을 'adv20' 으로 낸다. 거부권 V6 와 규모버킷은 'adtv20' 을
    #   읽는다. 이름이 어긋나면 예외 없이 **V6 가 영원히 발동하지 않고** 규모버킷이 NA 로
    #   무너진다(합성데이터가 두 이름을 다 갖고 있으면 스모크는 통과한다 — 실제로 그랬다).
    if "adtv20" not in P.columns and "adv20" in P.columns:
        P["adtv20"] = pd.to_numeric(P["adv20"], errors="coerce")
    elif "adv20" not in P.columns and "adtv20" in P.columns:
        P["adv20"] = pd.to_numeric(P["adtv20"], errors="coerce")

    # ── A축: HS 격자에서 산출 → 매핑표로 종목 격자로 이동
    a_hs = customs_a_sensors(cx)
    PIPE.io("OUT", "MEM", "A축 HS센서", a_hs)
    a_corp = map_hs_to_corp(a_hs, mapping, months)
    PIPE.io("OUT", "MEM", "A축 종목센서", a_corp)
    if len(a_corp):
        P = P.merge(a_corp, on=["code", "ym"], how="left")
    else:
        for c in ("a1", "a2", "a3", "a4", "a5", "x_wgt", "x_usd", "a2_beta",
                  "hs_main", "hs_n"):
            P[c] = np.nan

    # ── cv_dest (V10 커모디티 판정)
    cvd = customs_cv_dest(cx)
    if len(cvd) and "hs_main" in P.columns:
        P = P.merge(cvd[["hs", "cv_dest"]].rename(columns={"hs": "hs_main"}),
                    on="hs_main", how="left")
    else:
        P["cv_dest"] = np.nan

    # ── B·C축: 분기 프레임에서 산출한 뒤 PIT 로 붙인다 (merge_asof 단일 패스)
    b = b_sensors(fin)
    c = c_sensors(fin, emp)
    th = derive_theta_x(fin, mapping, cx)
    sub = build_subsidy_signal(fin)
    imp = build_capital_impairment(fin)
    # ★ 재무 '원값' 통과 소스. b/c 센서는 파생값만 내보내므로, D축(eps_ttm)과 거부권이
    #   필요로 하는 원계정(net_income_ttm 등)이 패널에 아예 없게 된다.
    #   그러면 d1(이 시스템에서 가장 중요한 단일 지표)이 통째로 결측이 되는데 예외는 안 난다.
    _raw_cols = [c_ for c_ in ("net_income_ttm", "revenue_ttm", "cfo_ttm", "assets",
                               "equity", "shares_out") if c_ in fin.columns]
    fund = (fin[["code", "knowledge_date"] + _raw_cols].copy() if _raw_cols else None)
    srcs = {"b": b, "c": c, "theta": th, "subsidy": sub, "impair": imp, "fund": fund}
    P = build_pit_panel(P, {k: v for k, v in srcs.items() if v is not None and len(v)},
                        by="code", left_time="month")
    viol = assert_c1(P, strict=False)
    if viol:
        LOG.error(f"C1(PIT) 위반 {len(viol)}건 — 결과를 신뢰할 수 없습니다: {viol[:3]}")

    # ── c6: 계약공시 12개월 누계 (월 격자 이벤트)
    con = fetch_supply_contracts(dis)
    c6 = c6_contract_ratio(con, months)
    if len(c6):
        P = P.merge(c6, on=["code", "ym"], how="left")
        rev = pd.to_numeric(P.get("rev_ttm"), errors="coerce")
        P["c6"] = safe_div(pd.to_numeric(P["contract_12m"], errors="coerce"), rev)
        # 매출을 못 구하면 금액 그대로 쓰되 셀 내 랭크가 되므로 스케일은 문제되지 않는다.
        P["c6"] = P["c6"].where(rev > 0, pd.to_numeric(P["contract_12m"], errors="coerce"))
    else:
        P["c6"] = np.nan

    # ── D축
    fin_m = P[["code", "ym"]].copy()
    ni = (pd.to_numeric(P["net_income_ttm"], errors="coerce")
          if "net_income_ttm" in P.columns else pd.Series(np.nan, index=P.index))
    sh = safe_div(pd.to_numeric(P.get("mcap"), errors="coerce"),
                  pd.to_numeric(P.get("close"), errors="coerce").replace(0, np.nan))
    fin_m["eps_ttm"] = safe_div(ni, sh)
    _cov_eps = float(fin_m["eps_ttm"].notna().mean()) if len(fin_m) else 0.0
    if _cov_eps < 0.05:
        LOG.warn(f"eps_ttm 커버리지가 {_cov_eps*100:.1f}% 입니다 — d1(ΔlogE/ΔlogM 재분류 갭)이 "
                 f"사실상 죽습니다. d1 은 이 시스템에서 가장 중요한 단일 지표이므로 "
                 f"net_income_ttm(재무) 과 mcap(시총) 확보 상태를 먼저 확인하세요.")
    cov = build_coverage_panel(reports, months)
    flows = None
    _codes = sorted(P.loc[P.get("xcb_uni", True), "code"].astype(str).unique()) \
        if "xcb_uni" in P.columns else sorted(P["code"].astype(str).unique())
    if krx_mode() != "off":
        try:
            fl = fetch_investor_flows(_codes, BACKTEST_START, BACKTEST_END)
            if fl is not None and len(fl):
                flows = fl.rename(columns={"month": "ym"}) if "month" in fl.columns else fl
        except Exception as e:                                          # noqa
            LOG.warn(f"KRX 수급 수집 실패({type(e).__name__}) — 네이버 폴백을 시도합니다.")
    if flows is None or not len(flows):
        try:
            flows = flows_naver(_codes, months)
        except Exception as e:                                          # noqa
            LOG.warn(f"네이버 수급 폴백 실패({type(e).__name__}) — d3 비활성화(0 채움 금지).")
            flows = None
    d = d_sensors(P[["code", "ym", "close"]], fin_m, flows, cov)
    P = P.merge(d.drop(columns=["close"], errors="ignore"), on=["code", "ym"], how="left")
    if len(cov):
        P = P.merge(cov, on=["code", "ym"], how="left")

    # ── 거부권 입력
    dil = build_dilution_flags(dis, months)
    if len(dil):
        P = P.merge(dil, on=["code", "ym"], how="left")
    wf = build_watch_flags(dis, months, sec)
    if len(wf):
        P = P.merge(wf, on=["code", "ym"], how="left")
    P["watch_flag"] = np.maximum(pd.to_numeric(P.get("watch_flag"), errors="coerce").fillna(0),
                                 pd.to_numeric(P.get("impaired"), errors="coerce").fillna(0))
    P["theta_x_chg"] = pd.to_numeric(P.get("theta_x"), errors="coerce") - \
        pd.to_numeric(P.get("theta_x"), errors="coerce").groupby(
            P["code"], observed=True).shift(12)
    P["map_gate_fail"] = pd.to_numeric(P.get("map_gate_fail"), errors="coerce").fillna(0.0)

    # ── 유니버스 플래그: 매핑된 종목 ∧ 상장 ∧ 시즈닝 (§5.1 — 매핑이 곧 유니버스)
    mapped = set(mapping["code"].astype(str)) if mapping is not None and len(mapping) else set()
    P["xcb_uni"] = (P["code"].astype(str).isin(mapped)
                    & P.get("listed", True)
                    & (pd.to_numeric(P.get("days_listed"), errors="coerce")
                       >= UNIVERSE_SEASON_DAYS))
    LOG.ok(f"L1 패널 {len(P):,}행 · {P['code'].nunique():,}종목 · {mem_mb(P):.0f}MB · "
           f"유니버스 {int(P['xcb_uni'].sum()):,} 종목월")
    return downcast(P)


def _reset_run_state() -> None:
    """같은 커널에서 두 번째로 실행할 때 지난 실행의 기록이 섞이지 않게 초기화한다.

    ★ 노트북은 한 커널에서 셀을 여러 번 돌린다. 전역 로그가 누적되면 강건성 표에 같은 검사가
      두 번 찍히고, 감쇠표의 첫 행(=분모)이 지난 실행 값이라 잔존율이 통째로 틀어진다.
    """
    for _lst in (ROBUST_LOG, KILL_LOG, CANARY_LOG, CONTRACT_LOG,
                 ATTRITION_LOG, OUTPUT_FILES, RUNTIME_LOG):
        try:
            _lst.clear()
        except Exception:                                               # noqa
            pass
    try:
        _SRC_CACHE.clear()
        CELL_FALLBACK_STATS.clear()
    except Exception:                                                   # noqa
        pass


def main_xcb() -> int:
    t_start = time.time()
    _reset_run_state()
    LOG.banner(f"{STRATEGY_NAME}  ·  {BUILD_VERSION}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · RUN_MODE={RUN_MODE} · STAGE={STAGE}")

    # ── [0] 환경 · 금고 · 외부캐시 · 계약 ────────────────────────────────────────────────
    global VAULT
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300), \
            Stage("L0.vault", 3.0):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        VAULT.report()
        foreign_init()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300), \
            Stage("L0.contracts", 2.0):
        contracts_xcb()

    with PIPE.stage("L0.SMOKE", "합성 스모크", "L0", budget_s=1800), \
            Stage("L0.smoke", 3.0):
        ok = smoke_xcb()
        if not ok:
            LOG.error("스모크 실패 — 실데이터로 진행하지 않습니다. 위 진단을 먼저 해결하세요.")
            PIPE.report_stages()
            return 2

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        return 0

    months = _months()
    canary = None
    with PIPE.stage("L1.CANARY", "CANARY 실측", "L1", budget_s=1800, critical=False), \
            Stage("CANARY", STAGE_BUDGET_MIN["CANARY"]):
        canary = run_canary()

    # ── [1] 유니버스 · 가격 ───────────────────────────────────────────────────────────────
    with PIPE.stage("L1.UNIVERSE", "PIT 유니버스 · 상장/폐지 (KRX 비의존)", "L1",
                    budget_s=1800), Stage("M0.universe", 15.0):
        # ★ KRX 는 '있으면 검증에 쓰는 보조'일 뿐 의존 대상이 아니다.
        #   계정이 차단되어 있어도 여기서 멈추지 않는다 — 마스터는 FDR/KIND 로 완성된다.
        mode = krx_mode()
        snaps = pd.DataFrame(columns=["snap_date", "code", "market"])
        if mode != "off":
            try:
                KRX.login()
                snaps = fetch_pykrx_snapshots(months)
            except Exception as e:                                      # noqa
                LOG.warn(f"KRX 경로 실패({type(e).__name__}) — 무시하고 비의존 경로로 진행합니다.")
        else:
            LOG.info("KRX_ENABLED=False — KRX 를 아예 호출하지 않습니다. "
                     "생존자편향 제거와 PIT 유니버스는 KRX 없이 구성됩니다.")
        sec = (build_security_master(snaps) if len(snaps)
               else build_security_master_nokrx())
        attrition("전체 상장(생존+폐지)", sec["code"].nunique(), "C2 상장폐지 포함")
        surv = audit_survivorship(sec, months, phase="pre")

    with PIPE.stage("L1.PRICE", "가격 · 시가총액", "L1", budget_s=2400), \
            Stage("M0.price", 25.0):
        codes = sorted(sec["code"].astype(str).unique())
        px_d = fetch_prices(codes, BACKTEST_START, BACKTEST_END)
        pxp = build_price_panel(px_d, months)
        px_m = pxp["monthly"] if isinstance(pxp, dict) else pxp
        mcap = None
        if krx_mode() != "off":
            try:
                mcap = fetch_pit_marketcap(months, px_m, sec)
            except Exception as e:                                      # noqa
                LOG.warn(f"KRX 시총 경로 실패({type(e).__name__}) — 근사 경로로 넘어갑니다.")
        if mcap is None or not len(mcap):
            mcap = mcap_nokrx(months, px_m, sec)
        # ★ 폐지일이 없는 폐지종목의 폐지일을 '마지막 거래일'로 복원한다.
        #   가격을 받은 뒤에만 가능하므로 여기서 한다. C2 의 마지막 구멍을 막는 단계다.
        sec = infer_delisting_from_prices(sec, px_d, months)
        audit_survivorship(sec, months)

    # ── [2] 큐레이션 · 통관 ───────────────────────────────────────────────────────────────
    with PIPE.stage("L1.CURATE", "HS 유니버스 큐레이션", "L1", budget_s=1500), \
            Stage("CURATION", 20.0):
        conc, _st = fetch_hs_ksic_concordance()
        # 큐레이션은 통관 원장을 필요로 하고, 통관 수집은 HS 목록을 필요로 한다.
        # 순환을 끊기 위해 1차로 '연계표가 지목한 章의 대표 HS' 만 넓게 받아 본다.
        seed_hs = sorted({str(h).zfill(2)[:2] for h in conc["hs"].astype(str)})
        cx0 = ingest_customs(seed_hs, BACKTEST_START.replace("-", "")[:6],
                             BACKTEST_END.replace("-", "")[:6], key=DATA_GO_KR_KEY)
        hs_uni = curate_hs_universe(cx0, sec, conc)
        adopted = hs_uni[hs_uni["adopted"] == 1]["hs"].astype(str).tolist()
        attrition("과점 HS 매핑 대상", len(adopted), f"HS {len(hs_uni)}개 중 채택")

    with PIPE.stage("L1.CUSTOMS", "관세청 통관 수집", "L1", budget_s=2400), \
            Stage("M0.customs", 20.0):
        cx = ingest_customs(adopted or seed_hs, BACKTEST_START.replace("-", "")[:6],
                            BACKTEST_END.replace("-", "")[:6], key=DATA_GO_KR_KEY)
        if cx is None or not len(cx):
            LOG.error("통관 데이터를 확보하지 못했습니다 — A축이 없으면 이 전략은 성립하지 않습니다.")
            PIPE.report_stages()
            return 3

    # ── [3] DART · 리서치 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시", "L1", budget_s=3000), \
            Stage("M0.dart", 30.0):
        corpmap = fetch_dart_corpcode()
        code_of = dict(zip(corpmap["corp_code"].astype(str), corpmap["code"].astype(str))) \
            if corpmap is not None and len(corpmap) else {}
        years = list(range(pd.Timestamp(BACKTEST_START).year - 1,
                           pd.Timestamp(BACKTEST_END).year + 1))
        raw = fetch_dart_bulk(years, list(REPRT_CODES.values()))
        dis = fetch_dart_disclosures(BACKTEST_START.replace("-", ""),
                                     BACKTEST_END.replace("-", ""))
        kmap = build_knowledge_map(dis)
        fin = tidy_financials(raw, kmap)
        emp = fetch_dart_employees(sorted(code_of), years, code_of) \
            if STAGE in ("M2", "ALL") else None

    reports = pd.DataFrame(columns=REPORT_COLS)
    analysts = pd.DataFrame()
    with PIPE.stage("L1.RESEARCH", "리서치 원장(캐시 우선)", "L1",
                    budget_s=1800, critical=False), Stage("M2.research", 15.0):
        if FOREIGN is not None:
            reports = foreign_reports(FOREIGN)
            analysts = foreign_analysts(FOREIGN)
        if RESEARCH_COLLECT and RUN_MODE == "FULL" and len(reports) < 5000:
            try:
                fresh = fetch_research_all(BACKTEST_START, BACKTEST_END)
                if fresh is not None and len(fresh):
                    reports = merge_report_ledger(reports, fresh)
            except Exception as e:                                      # noqa
                LOG.warn(f"리서치 신규 수집 실패({type(e).__name__}) — 캐시분만 사용합니다.")

    # ── [4] 매핑 게이트 ──────────────────────────────────────────────────────────────────
    with PIPE.stage("L2.MAP", "매핑표 + 4중 게이트", "L2", budget_s=1200), \
            Stage("CURATION.gates", 15.0):
        mapping = build_mapping_table(hs_uni, sec, conc, seg=None)
        attrition("매핑표 생성", mapping["code"].nunique() if len(mapping) else 0)
        a_hs0 = customs_a_sensors(cx)
        b0 = b_sensors(fin)
        fin_g = fin.merge(b0[["code", "period_end", "b1"]], on=["code", "period_end"],
                          how="left") if len(b0) else fin
        mapping, gates = apply_mapping_gates(mapping, cx, fin_g, None, a_hs0)
        attrition("매핑 게이트 통과", mapping["code"].nunique() if len(mapping) else 0,
                  f"게이트3 p={gates.get('gate3', {}).get('p', float('nan')):.4f}")

    # ── [5] L1 → L2 → L3 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L2.PANEL", "L1 피처 패널", "L2", budget_s=1800), \
            Stage("M0.panel", 20.0):
        P = build_panel_xcb(months, sec, px_m, px_d, mcap, cx, mapping,
                            fin, emp, dis, reports)
        attrition("유니버스(매핑∧상장∧시즈닝)",
                  int(P.loc[P["xcb_uni"], "code"].nunique()))

    with PIPE.stage("L3.SCORE", "스코어 조립", "L3", budget_s=900), Stage("M0.score", 10.0):
        P = score_panel(P, stage=STAGE)
        P["VETO"] = P["veto_pass"]
        P["FLOOR"] = P["breadth_ok"]
        P["dlog_M"] = P.get("dlogM")
        P["dlog_E"] = P.get("dlogE")
        attrition("거부권 통과", int(P.loc[P["xcb_uni"] & (P["veto_pass"] > 0),
                                          "code"].nunique()))
        attrition("하한선 통과", int(P.loc[P["xcb_uni"] & (P["veto_pass"] > 0)
                                        & (P["breadth_ok"] > 0), "code"].nunique()))
        attrition("최종 신호 보유", int(P.loc[P["Signal"].notna(), "code"].nunique()))

    runner = _make_runner(months, sec)
    with PIPE.stage("L3.BT", "백테스트", "L3", budget_s=900), Stage("M0.backtest", 10.0):
        bt = runner(P, label="XCB")
        bench = benchmark_returns(months)

    # ── [6] 성과 · 원장 · 해석 ───────────────────────────────────────────────────────────
    with PIPE.stage("L4.PERF", "성과 검증", "L4", budget_s=300), Stage("REPORT.perf", 3.0):
        report_performance_xcb(bt, bench)
        report_ledger_integrity(reports, analysts, build_coverage_panel(reports, months))
        report_interpretation_xcb(P, bt)

    # ── [7] 강건성 ───────────────────────────────────────────────────────────────────────
    abl = None
    with PIPE.stage("L4.ROBUST", "강건성 R0~R10", "L4", budget_s=3000, critical=False), \
            Stage("R-SUITE", 30.0):
        RX0_benchmark(bt, bench, months)
        RX1_leakage(P, months, sec, runner, bt)
        RX2_tp_vs_naive(P, months, sec, runner, bt)
        RX3_orthogonal(P, bt)
        RX4_placebo(gates.get("gate3", {}))
        RX10_policy(P, months, sec, runner, bt)

        def _rescore(**kw):
            Q = score_panel(P, stage=STAGE, **kw)
            Q["VETO"] = Q["veto_pass"]
            Q["FLOOR"] = Q["breadth_ok"]
            Q["dlog_M"] = Q.get("dlogM")
            Q["dlog_E"] = Q.get("dlogE")
            return Q

        abl = RX5_ablation(P, months, sec, runner, bt, _rescore)
        RX6_pbo(abl)
        RX7_regime(bt, bench)
        RX9_capacity(P, months, sec, runner, bt)
        report_robustness_xcb()

    # ── [8] 산출물 · 감사 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L5.OUT", "산출물 · 감사", "L5", budget_s=600, critical=False):
        attr = report_attrition()
        cards = diagnostic_cards_xcb(P, bt, sec)
        save_outputs_xcb(P, bt, abl, attr, cards, canary, gates)
        try:
            VAULT.put_table("l1_panel_xcb", P, scope="private", source=STRATEGY_ID)
            VAULT.put_table("backtest_returns_xcb", bt["returns"], scope="private",
                            source=STRATEGY_ID)
            VAULT.flush()
        except Exception as e:                                          # noqa
            LOG.warn(f"전용 인덱스 저장 실패({type(e).__name__})")
        universe_sources_audit(sec, px_m, mcap, None)
        report_cell_fallback()
        report_http()
        PIPE.report_stages()
        report_dataflow_xcb()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)

    mins = (time.time() - t_start) / 60.0
    LOG.banner("완료", f"총 {mins:.1f}분 (하드 제약 {WALL_CLOCK_BUDGET_MIN:.0f}분)")
    if mins > WALL_CLOCK_BUDGET_MIN:
        LOG.warn(f"[킬 기준 11] 총 wall-clock 이 {mins:.0f}분으로 예산을 초과했습니다. "
                 f"검사를 줄이지 말고 구조를 고치세요.")
    if KILL_LOG:
        LOG.error(f"★ 킬 기준 {len(KILL_LOG)}건 발동 — 결과를 그대로 보고합니다. "
                  f"파라미터를 조정해 통과시키지 마세요.")
    return 0


def _entrypoint() -> int:
    try:
        return main_xcb()
    except KillCriteria as e:
        LOG.error(f"킬 기준으로 중단: {e}")
        return 4
    except StageFailure as e:
        LOG.error(f"스테이지 실패로 중단: {e}")
        return 5


# ★ 노트북에 통째로 붙여넣어도 __name__ 은 "__main__" 이므로 그대로 실행된다(원셀 실행).
#   다만 노트북에서 SystemExit 를 던지면 셀이 빨간 트레이스백으로 끝나 '실패한 것처럼' 보인다.
#   대화형 환경에서는 종료코드를 변수로만 남기고 조용히 끝낸다.
if __name__ == "__main__":
    XCB_EXIT_CODE = _entrypoint()
    if ENV.get("ipython"):
        if XCB_EXIT_CODE:
            LOG.warn(f"종료코드 {XCB_EXIT_CODE} — 위 진단을 확인하세요. "
                     f"(노트북이라 예외를 던지지 않고 XCB_EXIT_CODE 변수로만 남깁니다)")
    else:
        raise SystemExit(XCB_EXIT_CODE)
