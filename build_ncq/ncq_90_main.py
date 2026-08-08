

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — Phase 0~6 실행 순서와 산출물                                             ║
# ║                                                                                          ║
# ║  모든 단계는 PIPE.stage(...) 안에서 돈다. 실패하면 자동으로 출력되는 것:                    ║
# ║    실패 지점(스테이지ID·계층·경과) / 직전 입출력 스냅샷(행수·PIT컬럼) / 한글 진단 힌트 /    ║
# ║    트레이스백 마지막 12줄.  → "어디서 터졌고 무슨 데이터가 어디로 흘렀는가"가 한 화면에.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def ncq_outdir() -> str:
    d = os.path.join(VAULT.ns["private"], "outputs", STRATEGY_ID)
    os.makedirs(d, exist_ok=True)
    return d


def ncq_configdir() -> str:
    d = os.path.join(VAULT.ns["private"], "config")
    os.makedirs(d, exist_ok=True)
    return d


def ncq_phase0(months: pd.DatetimeIndex) -> dict:
    """Phase 0 — 종목마스터 · 가격 · PIT 상장주식수 · 시가총액 · 유니버스."""
    ctx: Dict[str, Any] = {}
    with PhaseBudget("P0", NCQ_PHASE_BUDGET_S["P0"]) as B:

        with PIPE.stage("P0.SEC", "종목 마스터 (다중소스 · 생존자편향 제거)", "L1", budget_s=900):
            snaps = fetch_pykrx_snapshots(months) if ncq_krx_enabled() else \
                pd.DataFrame(columns=["snap_date", "code", "market"])
            sec = build_security_master(snaps)
            dead = ncq_fdr_delisting_full()
            listing_now = ncq_fdr_listing_full()
            ctx.update(sec=sec, snapshots=snaps, dead=dead, listing_now=listing_now)

        with PIPE.stage("P0.PX", "가격 · 거래대금 (KRX-free 폴백 체인)", "L1", budget_s=1500):
            if ncq_krx_enabled():
                KRX.login()
            px = fetch_prices(ctx["sec"]["code"].tolist(),
                              (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                              BACKTEST_END)
            ctx["px"] = px
            ctx["panel"] = build_price_panel(px, months)
            ctx["pxm"] = ctx["panel"]["monthly"]

        with PIPE.stage("P0.SURV", "상장·폐지 구간 보강 (생존자편향 4중 방어)", "L1", budget_s=180):
            ctx["sec"] = ncq_enrich_security_master(ctx["sec"], ctx["panel"]["daily"], ctx["dead"])
            VAULT.put_table("security_master_ncq", ctx["sec"], scope="shared", domain="universe",
                            source="fdr+dart+price_intervals")
            ctx["uni_obj"] = Universe(ctx["sec"], ctx["snapshots"], ctx["panel"]["daily"])

        with PIPE.stage("P0.SHARES", "PIT 상장주식수 (DART 접수일자 기준)", "L1",
                        budget_s=1200, critical=False):
            corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist() \
                if "corp_code" in ctx["sec"].columns else []
            years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
            ds = fetch_dart_shares(corps, years) if corps else pd.DataFrame()
            ctx["shares_hist"] = ncq_build_shares_history(ctx["sec"], ds, ctx["listing_now"])

        with PIPE.stage("P0.MCAP", "PIT 시가총액", "L1", budget_s=900):
            ctx["mcap"] = build_marketcap_panel(ctx["sec"]["code"].tolist(), months,
                                                ctx["panel"]["daily"], ctx["sec"],
                                                ctx.get("shares_hist"))

        with PIPE.stage("P0.UNI", f"PIT 유니버스 (시총 하위 {NCQ_UNIVERSE_BOTTOM_N})", "L1",
                        budget_s=300):
            ctx["UNI"] = build_ncq_universe(months, ctx["pxm"], ctx["mcap"],
                                            ctx["uni_obj"], ctx["sec"])
            VAULT.put_table(f"universe_{STRATEGY_ID}", ctx["UNI"], scope="private",
                            domain="universe", source="build_ncq_universe")
        B.check()
    return ctx


def ncq_phase1(ctx: dict, months: pd.DatetimeIndex) -> dict:
    """Phase 1 — 리포트 인덱스 · 원장 · 애널리스트 연결 · 완결성 진단."""
    with PIPE.stage("P1.INDEX", "리포트 인덱스 전수 수집 (최신→과거 역순)", "L1",
                    budget_s=NCQ_PHASE_BUDGET_S["P1"] + 600):
        ctx["REP"] = collect_report_index(months, ctx["sec"])

    with PIPE.stage("P1.LEDGER", "애널리스트 원장 · 보고서↔애널리스트 연결", "L1",
                    budget_s=300, critical=False):
        A, L = build_analyst_ledger(ctx["REP"])
        ctx["analysts"], ctx["links"] = A, L
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        audit_linkage(ctx["REP"], A, L)

    with PIPE.stage("P1.DIAG", "커버리지 완결성 진단 (백테스트보다 먼저)", "L1", budget_s=120):
        diag, valid_start = coverage_completeness(ctx["REP"], months)
        ctx["diag"], ctx["valid_start"] = diag, valid_start
    return ctx


def ncq_phase2to5(ctx: dict, months_eff: pd.DatetimeIndex) -> dict:
    with PIPE.stage("P2.EVENT", "신규 커버리지 판정 (H1 de novo / H2 broker-new)", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P2"] + 300):
        ctx["EV"] = build_coverage_events(ctx["REP"], ctx["UNI"], months_eff,
                                          ctx["valid_start"], links=ctx.get("links"))
        ctx["event_audit"] = audit_events(ctx["EV"], ctx["REP"])

    with PIPE.stage("P3.TEXT", "이벤트 한정 PDF 본문 수집·섹션 추출", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P3"] + 600, critical=False):
        ctx["TXT"] = collect_event_texts(ctx["EV"], ctx["REP"])

    with PIPE.stage("P4.SCORE", "동결 렉시콘 텍스트 스코어링", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P4"] + 300):
        ctx["SCORE"] = score_texts(ctx["TXT"])

    with PIPE.stage("P5.SIGNAL", "횡단면 z → 상위 tercile 편입", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P5"] + 120):
        ctx["SIG"] = build_signal_panel(ctx["SCORE"], ctx["EV"], ctx["UNI"],
                                        ctx["pxm"], months_eff)
    return ctx


def ncq_make_runners(ctx: dict, months_eff: pd.DatetimeIndex):
    """강건성·민감도가 쓰는 두 콜백을 만든다.

    · run_fn(SIG, ...)      → 백테스트만 다시 (보유기간·비용 축)
    · build_sig_fn(top_pct, min_adv) → 신호를 다시 (tercile·유동성 축)
      ★ 유동성 축은 유니버스의 liq_pass 만 바뀌므로 이벤트 판정을 통째로 다시 하지 않는다.
        (다시 하면 민감도 9조합에 수십 분이 든다)
    """
    UNI, SCORE, EV, pxm, sec, uni_obj = (ctx["UNI"], ctx["SCORE"], ctx["EV"], ctx["pxm"],
                                         ctx["sec"], ctx["uni_obj"])

    def run_fn(SIG, hold_months=None, cost_roundtrip=None, sel_col="selected",
               adv_cap=True, label="NCQ", months_override=None):
        return run_overlap_backtest(SIG, pxm, sec, uni_obj,
                                    months_override if months_override is not None else months_eff,
                                    hold_months=hold_months, sel_col=sel_col,
                                    cost_roundtrip=cost_roundtrip, adv_cap=adv_cap, label=label)

    def build_sig_fn(top_pct=None, min_adv=None):
        U, E = UNI, EV
        if min_adv is not None and abs(float(min_adv) - float(NCQ_MIN_ADV)) > 1e-6:
            U = UNI.copy()
            U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= float(min_adv))
            ok = set(zip(U.loc[U["liq_pass"], "month"].to_numpy(),
                         U.loc[U["liq_pass"], "code"].astype(str)))
            keep = [(m, c) in ok for m, c in zip(EV["month"].to_numpy(), EV["code"].astype(str))]
            E = EV[pd.Series(keep, index=EV.index)]
        return build_signal_panel(SCORE, E, U, pxm, months_eff, top_pct=top_pct)

    return run_fn, build_sig_fn


def offer_download_fallback(paths):
    """리포트 모듈의 offer_download 가 없을 때만 쓰는 최소 폴백."""
    for p in paths or []:
        if p and os.path.exists(p):
            _safe_print(f"⬇  산출물 경로: {p}")


def main() -> dict:
    t_all = time.time()
    global VAULT
    LOG.banner(f"{STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 실행모드 {RUN_MODE} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("JupyterLab/IPython" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 (리서치 {N_WORKERS_RESEARCH} 상한) / "
                        f"CPU {N_CPU} " + ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가→폴백)")],
               ["KRX 경로", "활성" if ncq_krx_enabled() else "비활성 — KRX-free 경로로 진행"],
               ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    # ── L0 캐시 · 소스 배선 · 동결 ────────────────────────────────────────────────────────
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root = resolve_gdrive_root()
        VAULT = Vault(root, MANIFEST.get("gdrive_root_mode", "AUTO"))
        globals()["VAULT"] = VAULT
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(ncq_adopt_dirs())

    with PIPE.stage("L0.SRC", "데이터 소스 배선 (KRX 차단 대응)", "L0", budget_s=60):
        ncq_configure_sources()

    with PIPE.stage("L0.FREEZE", "렉시콘·사전등록 동결 (백테스트 실행 전)", "L0", budget_s=60):
        freeze_configs(ncq_configdir())

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 N1~N11", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(1800 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    # ★ 스모크는 '계산경로'를, 리허설은 '수집경로'를 증명한다. 둘은 겹치지 않는다.
    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=900):
        run_rehearsal(strict=True)

    with PIPE.stage("L0.CANARY", "네트워크 카나리 C1~C7", "L0", budget_s=600):
        ctx_canary = run_canaries(strict=True)

    months = month_range(BACKTEST_START, BACKTEST_END)
    ctx = ncq_phase0(months)
    ctx["canary"] = ctx_canary
    ctx = ncq_phase1(ctx, months)

    # ── 유효 윈도우 판정 (명세 §15-2 — 5년 미만이면 중단하고 보고) ────────────────────────
    yrs = float(MANIFEST.get("valid_backtest_years", 0.0) or 0.0)
    burn_end = (as_ts(ctx["valid_start"]) +
                pd.DateOffset(months=max(NCQ_LOOKBACK_M, NCQ_BURNIN_M))) + pd.offsets.MonthEnd(0)
    months_eff = months[months >= burn_end]
    manifest_put("months_effective", [str(months_eff[0].date()), str(months_eff[-1].date())]
                 if len(months_eff) else [])
    if yrs < NCQ_MIN_VALID_YEARS and NCQ_STOP_IF_SHORT_WINDOW:
        LOG.banner("⛔ 중단 — 유효 백테스트 윈도우 부족",
                   f"유효 {yrs:.1f}년 < 최소 {NCQ_MIN_VALID_YEARS:.0f}년 (명세 §15-2)")
        _safe_print("  아카이브 결손 구간을 그대로 쓰면 '가짜 신규 커버리지'가 대량 발생해\n"
                    "  백테스트 결과 전체가 무효가 됩니다. 다음 중 하나를 선택하세요:\n"
                    "    ① 구글드라이브에 과거 리포트를 더 확보한 뒤 재실행 (권장)\n"
                    "    ② NCQ_STOP_IF_SHORT_WINDOW=False 로 두고 '검정력 부족'을 감수하고 진행\n"
                    "    ③ IR협의회 단독 + 짧은 윈도우로 전략을 재설계\n")
        try:
            report_coverage_diagnostics(ctx["diag"], ctx["REP"], None)
            outs = [write_manifest(ncq_outdir(), ctx), write_coverage_html(ncq_outdir(), ctx)]
        except Exception:
            outs = []
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        PIPE.report_stages(); PhaseBudget.report()
        offer_download([p for p in outs if p])
        return {"stopped": "short_window", "years": yrs, "ctx": ctx}
    if len(months_eff) < 24:
        raise RuntimeError(f"유효 월수가 {len(months_eff)}개월뿐이라 백테스트가 무의미합니다. "
                           f"완결성 진단(유효 시작 {ctx['valid_start']:%Y-%m})을 먼저 확인하세요.")
    LOG.ok(f"유효 백테스트 구간 확정: {months_eff[0]:%Y-%m} ~ {months_eff[-1]:%Y-%m} "
           f"({len(months_eff)}개월) — burn-in {max(NCQ_LOOKBACK_M, NCQ_BURNIN_M)}개월 반영")

    ctx = ncq_phase2to5(ctx, months_eff)
    run_fn, build_sig_fn = ncq_make_runners(ctx, months_eff)

    # ── Phase 6 백테스트 ──────────────────────────────────────────────────────────────────
    with PhaseBudget("P6", NCQ_PHASE_BUDGET_S["P6"]) as B6:
        with PIPE.stage("P6.BT", "12개월 오버랩 코호트 백테스트", "L3", budget_s=600):
            ctx["BT"] = run_fn(ctx["SIG"], label="ARC-NCQ 전략")
            ctx["BT_placebo"] = run_fn(ctx["SIG"], sel_col="placebo", label="Placebo(z 하위)")
            ctx["BT_eventew"] = run_fn(ctx["SIG"].assign(_all=True), sel_col="_all",
                                       label="이벤트 EW(텍스트 미사용)")
            ctx["BT_nocap"] = run_fn(ctx["SIG"], adv_cap=False, label="ADV 제약 미적용")

        with PIPE.stage("P6.BENCH", "벤치마크 구성", "L3", budget_s=300, critical=False):
            bench_ew = bench_universe_ew(ctx["UNI"], ctx["pxm"], months_eff)
            benches: Dict[str, pd.Series] = {"Bottom-N EW(주)": bench_ew}
            benches.update(bench_index(months_eff))
            benches["Placebo(z 하위)"] = ctx["BT_placebo"]["returns"].set_index("month")["ret"]
            benches["이벤트 EW"] = ctx["BT_eventew"]["returns"].set_index("month")["ret"]
            ctx["bench_ew"], ctx["benches"] = bench_ew, benches

        with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=180, critical=False):
            report_performance(ctx["BT"], benches, label="ARC-NCQ")
            ctx["uni_obj"].report_attrition()
        B6.check()

    # ── 강건성 · 사전등록 검정 · 민감도 ───────────────────────────────────────────────────
    with PIPE.stage("L5.PREREG", "사전등록 가설 P1~P4 (BH-FDR)", "L5", budget_s=1200,
                    critical=False):
        # ★ 채택 기준 미충족(킬 게이트)은 '결론'이지 '사고'가 아니다. 여기서 예외로 실행을
        #   끊어버리면 진단·해석·리포트가 통째로 사라져서, 왜 미채택인지 볼 수단이 없어진다.
        #   그래서 킬 사유를 기록만 하고 리포트까지 끝낸 뒤 마지막에 다시 크게 알린다.
        #   (파라미터를 바꿔 통과시키지 않는다는 원칙은 그대로다 — 결과는 미채택으로 남는다)
        try:
            ctx["prereg"] = run_prereg_tests(ctx["SIG"], ctx["BT"], bench_ew, ctx["pxm"],
                                             ctx["sec"], ctx["uni_obj"], months_eff, run_fn)
        except KillCriteria as e:
            ctx["kill"] = str(e)
            ctx["prereg"] = globals().get("NCQ_PREREG_RESULT") or {}
            LOG.error(f"킬 기준 발동 — {e}")
            LOG.warn("킬 기준이 발동했지만 진단·리포트는 끝까지 생성합니다. "
                     "'왜 미채택인지'를 볼 수 없으면 판단 자체가 불가능하기 때문입니다.")
            manifest_note(f"KILL: {e}")
        except Exception as e:                                    # noqa
            LOG.error(f"사전등록 검정 실패({type(e).__name__}: {e}) — 이후 판정은 보류합니다.")
            ctx["prereg"] = {}

    with PIPE.stage("L5.SENS", "민감도 9조합 (81조합 전부 금지 — 명세 §15-5)", "L5",
                    budget_s=1800, critical=False):
        ctx["sens"] = run_sensitivity(ctx, months_eff, build_sig_fn, run_fn)

    with PIPE.stage("L5.STAT", "통계 검정 스위트 (부트스트랩·순열·WF·PBO·DSR·Holm)", "L5",
                    budget_s=1800, critical=False):
        n_trials = int(len(ctx["sens"])) if isinstance(ctx.get("sens"), pd.DataFrame) and \
            len(ctx["sens"]) else 9
        ctx["stats"] = run_stat_suite(ctx["BT"], bench_ew, ctx["SIG"], months_eff, run_fn,
                                      n_trials=n_trials)
        report_robustness()
        try:
            report_structural_risks(ctx)
        except Exception as e:                                    # noqa
            LOG.warn(f"구조적 리스크 표 생성 실패({type(e).__name__})")

    # ── 리포트 · 산출물 ───────────────────────────────────────────────────────────────────
    with PIPE.stage("L6.REPORT", "진단 9종 · 해석표 · 흐름지도", "L6", budget_s=300,
                    critical=False):
        report_headline(ctx)
        report_coverage_diagnostics(ctx["diag"], ctx["REP"], ctx["EV"])
        report_diagnostics(ctx["SIG"], ctx["EV"], ctx["BT"], ctx["UNI"], ctx["sec"], benches)
        report_interpretation(ctx["SIG"], ctx["EV"], ctx["SCORE"])
        report_dataflow_map()

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outdir = ncq_outdir()
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs: List[str] = []
        try:
            bt_path = os.path.join(outdir, f"backtest_results_{stamp}.parquet")
            atomic_write_parquet(ctx["BT"]["returns"], bt_path); outs.append(bt_path)
            ev_path = os.path.join(outdir, f"event_log_{stamp}.parquet")
            atomic_write_parquet(ctx["EV"], ev_path); outs.append(ev_path)
            hd_path = os.path.join(outdir, f"holdings_{stamp}.csv")
            ctx["BT"]["holdings"].to_csv(hd_path, index=False, encoding="utf-8-sig")
            outs.append(hd_path)
        except Exception as e:                                    # noqa
            LOG.warn(f"산출물 일부 저장 실패({type(e).__name__})")
        try:
            outs.append(write_coverage_html(outdir, ctx))
            outs.append(write_html_report(outdir, ctx))
            outs.append(write_manifest(outdir, ctx))
        except Exception as e:                                    # noqa
            LOG.warn(f"리포트 생성 실패({type(e).__name__}: {e})")
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer)); outs.append(lp)

        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", ctx["BT"]["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.put_table(f"cohorts_{STRATEGY_ID}", ctx["BT"]["cohorts"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        VAULT.report()
        ctx["outputs"] = [p for p in outs if p and os.path.exists(p)]

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    ncq_report_sources()
    PhaseBudget.report()
    PIPE.report_runtime()

    if ctx.get("kill"):
        LOG.banner("⛔ 사전등록 채택 기준 미충족 — 이 전략은 '미채택'입니다",
                   "파라미터를 조정해 통과시키지 마십시오. 미채택도 결론입니다.")
        _safe_print(f"  {ctx['kill']}\n"
                    "  다음 단계는 '기준을 낮추는 것'이 아니라 ① 커버리지 완결성을 더 확보하거나\n"
                    "  ② 표본(이벤트 수)을 늘리거나 ③ 이 전략을 위성 배분 후보에서 제외하는 것입니다.")

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다: {ncq_outdir()}")
    LOG.info("한계 명시 — ① 아카이브 결손이 곧 가짜 신규 커버리지다(§12 R1). 완결성 진단이 "
             "유일한 방어선이며 통과 실패 시 결과 전체가 무효입니다. "
             "② 렉시콘은 연구자 편향을 담고 있으며, 수익률 확인 후 수정하면 전 결과가 무효입니다.")
    offer_download(ctx.get("outputs", []))
    return {"ctx": ctx, "backtest": ctx.get("BT"), "signal": ctx.get("SIG"),
            "robust": NCQ_ROBUST, "prereg": ctx.get("prereg"), "sens": ctx.get("sens")}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        try:
            report_robustness()
            PhaseBudget.report()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
        try:
            ncq_report_sources(); PhaseBudget.report()
        except Exception:
            pass
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 _done.jsonl 로 정확히 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
