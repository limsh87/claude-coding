

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 리포트 원장은 백테스트 시작보다 **42개월 앞서** 있어야 한다:
#   12개월 룩백(base) + 24개월 확장창 버인 + 여유 6개월.
# 이걸 빼면 신호 개시가 1년 이상 밀려 백테스트 앞부분이 통째로 빈다.
RESEARCH_LEAD_M = 42
OUTPUTS: Dict[str, str] = {}


def _months() -> "pd.DatetimeIndex":
    return month_range(BACKTEST_START, BACKTEST_END)


def collect_all(months: "pd.DatetimeIndex") -> dict:
    ctx: Dict[str, Any] = {}
    res_start = (as_ts(BACKTEST_START) - pd.DateOffset(months=RESEARCH_LEAD_M)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.MKT", "시장 데이터 (marcap 연도 parquet)", "L1", budget_s=1800):
        y0 = as_ts(res_start).year
        y1 = as_ts(BACKTEST_END).year
        md = build_market_data(y0, y1)
        ctx.update(daily=md["daily"], monthly=md["monthly"], sec=md["sec"])
        LOG.info(f"※ 종목당 HTTP 수천 건 대신 **연도 parquet {y1-y0+1}개**로 전 종목·전 기간을 "
                 f"받았습니다. 두 번째 실행부터는 HTTP 캐시 적중으로 네트워크 0회입니다.")

    with PIPE.stage("L1.UNI", "PIT 유니버스 · 시가총액", "L1", budget_s=600):
        ctx["uni_all"] = build_pit_universe(ctx["monthly"], months)
        ctx["panel"] = build_price_panel(ctx["monthly"], months, max_hold=max(GRID_HOLD))
        ctx["panel"] = apply_delisting_returns(ctx["panel"], ctx["sec"], max_hold=max(GRID_HOLD))
        ctx["universe"] = Universe(ctx["uni_all"], ctx["sec"])
        for m in months:
            ctx["universe"].audit_row("PIT유니버스", m,
                                      ctx["uni_all"].loc[ctx["uni_all"]["month"] == m, "code"])
            ctx["universe"].audit_row("시즈닝통과", m, ctx["universe"].at(m))

    with PIPE.stage("L1.DART", "실적발표월 · 공시건수 (통제변수)", "L1",
                    budget_s=2400, critical=False):
        fetch_dart_corpcode()
        dis = fetch_dart_disclosures(res_start, BACKTEST_END)
        codes = sorted(set(as_str_series(ctx["uni_all"]["code"])))
        ctrl, meta = build_control_panel(
            pd.DatetimeIndex(sorted(set(months) | set(
                month_range(res_start, BACKTEST_END)))), dis, codes)
        ctx["ctrl"], ctx["ctrl_meta"] = ctrl, meta
        LOG.table([[k, str(v)] for k, v in meta.items()], ["통제변수 메타", "값"], ["l", "l"],
                  title="§6.3 통제변수 출처 (실측인지 달력 대리인지 숨기지 않습니다)")
        if DART_API_KEY:
            quota("DART", key=DART_API_KEY).report()

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장", "L1",
                    budget_s=5400, critical=False):
        raw = collect_reports(res_start, BACKTEST_END)
        rep = build_report_master(raw, ctx["sec"])
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    return ctx


def build_signals(ctx: dict, months: "pd.DatetimeIndex") -> dict:
    L, A, sec = ctx.get("links"), ctx.get("analysts"), ctx["sec"]
    mode = ctx.get("phase0", {}).get("mode", "ANALYST")

    with PIPE.stage("L2.ATTN", "주의 패널 → 축소추정 → 통제회귀 → VAS", "L2", budget_s=2100):
        # 지문에 sec(섹터·폐지일)와 uni_all(지수이벤트·상장여부)까지 넣는다.
        # 빠뜨리면 그 입력만 바뀐 재실행이 낡은 VAS 를 그대로 재사용한다.
        fp = fingerprint_of("vas", mode, LOOKBACK_M, MIN_REPORTS_MON, MIN_LOOKBACK_N,
                            CTRL_MIN_TRAIN_M, BACKTEST_START, BACKTEST_END, "v4",
                            frames=[L, ctx.get("ctrl"), sec, ctx.get("uni_all")])

        def _mk():
            P = build_attention_panel(L, months, sec, unit_mode=mode)
            if P.empty:
                return P
            P = attach_controls(P, ctx.get("ctrl"), ctx["uni_all"])
            V, sd, rd = compute_vas(P, months)
            ctx["shrink_diag"], ctx["reg_diag"] = sd, rd
            return V

        V = VAULT.memo_table("attention_panel", fp, _mk, scope="private", domain="features",
                             note="주의패널+VAS")
        for c in ("month",):
            if c in V.columns:
                V[c] = as_ts_series(V[c])
        ctx["vas"] = V
        if len(V):
            VAULT.put_table(f"attention_panel_{STRATEGY_ID}", V, scope="private",
                            domain="features", source="L2")

    with PIPE.stage("L2.DROPS", "커버리지 철회 인과분해", "L2", budget_s=900):
        fp = fingerprint_of("drops", W_SIG, D_VER, LAM_MIN, COVER_WINDOW_M,
                            NEG_W_VDROP, NEG_W_HEXIT, "v4",
                            frames=[L, A, sec, ctx.get("uni_all")])

        def _mkd():
            d = classify_coverage_drops(L, A, months, sec, ctx["uni_all"])
            ctx["_drops_all"] = d
            return d["signal"]

        drops = VAULT.memo_table("drop_events", fp, _mkd, scope="private", domain="features",
                                 note="철회 분류")
        for c in ("month", "last_report_month", "event_date", "knowledge_date"):
            if c in drops.columns:
                drops[c] = as_ts_series(drops[c])
        ctx["drops"] = drops
        if len(drops):
            VAULT.put_table(f"coverage_exit_{STRATEGY_ID}", drops, scope="private",
                            domain="features", source="L2")
        ctx["aar_neg"] = build_aar_neg(drops, L, months)

    with PIPE.stage("L2.SIG", "AAR_pos 가중 3종 · 신호 조립", "L2", budget_s=600):
        ctx["pos_by_w"] = {w: build_aar_pos(ctx["vas"], w) for w in GRID_WEIGHTS}
        ctx["naive"] = build_naive_signal(L, months, ctx["uni_all"])
    return ctx


def run_universe(ctx: dict, months: "pd.DatetimeIndex", variant: str) -> dict:
    """한 유니버스 변형에 대해 격자 12개 백테스트 + 성과 + 검정 + 강건성."""
    LOG.banner(f"유니버스 변형: {variant}",
               "PIT 전체 상장 유니버스" if variant == "FULL"
               else f"시가총액 하위 {SMALLCAP_N:,} 압축 (기존 전략 대비 비교용)")
    uni = apply_universe_variant(ctx["uni_all"], variant)
    # ★ 상장 시즈닝을 **실제로 적용**한다. Universe.at() 이 계산만 하고 아무도 쓰지 않으면
    #   감사표에는 게이트가 찍히는데 포트폴리오는 상장 1개월차 신규상장주를 담는다.
    #   신규상장 직후는 수익률 분포가 완전히 다르므로 그대로 두면 신호가 아니라 IPO 효과를 잰다.
    seasoned = {(c, m) for m in months for c in ctx["universe"].at(m)}
    n0 = len(uni)
    uni = uni[[(c, m) in seasoned for c, m in zip(as_str_series(uni["code"]), uni["month"])]]
    if n0 != len(uni):
        LOG.info(f"[{variant}] 상장 시즈닝(상장일+1년) 적용 — {n0:,} → {len(uni):,} 월행 "
                 f"(신규상장 직후 구간 제외).")
    key = set(zip(as_str_series(uni["code"]), uni["month"]))
    panel = ctx["panel"][[(c, m) in key for c, m in
                          zip(as_str_series(ctx["panel"]["code"]), ctx["panel"]["month"])]].copy()

    sig_by_w: Dict[str, "pd.DataFrame"] = {}
    grid_stats, grid_ret = [], {}
    for g in signal_grid():
        S = assemble_signal(ctx["pos_by_w"][g["weight"]], ctx["aar_neg"], uni, lam=g["lam"])
        if g["lam"] == GRID_LAMBDA[-1] and g["hold"] == GRID_HOLD[0]:
            sig_by_w[g["weight"]] = S
        if S.empty:
            continue
        bt = run_backtest(S, panel, months, ctx["sec"], hold=g["hold"], cost_mult=1.0,
                          label=g["label"], uni_obj=(ctx["universe"] if g["label"].endswith("1M")
                                                     and g["weight"] == GRID_WEIGHTS[0] else None))
        st = perf_stats(bt["returns"])
        grid_stats.append({**g, "stats": st, "bt": bt, "S": S})
        grid_ret[g["label"]] = bt["returns"].set_index("month")["ret"]
    if not grid_stats:
        LOG.error(f"[{variant}] 어떤 구성에서도 백테스트를 만들지 못했습니다.")
        return {}
    report_grid(grid_stats)
    GR = pd.DataFrame(grid_ret).reindex(months).fillna(0.0)

    # 헤드라인 구성: 사전등록상 기본값 = 비가중 · λ=1.0 · 1개월 (최고 성과를 고르지 않는다)
    head = next((g for g in grid_stats
                 if g["weight"] == "uw" and g["lam"] == 1.0 and g["hold"] == 1), grid_stats[0])
    LOG.info(f"헤드라인 구성 = {head['label']} — **사전에 정한 기본 구성**입니다. "
             f"격자 12개 중 최고 성과를 골라 보고하지 않습니다(그것이 곧 사후선택입니다).")
    bt = head["bt"]
    S = head["S"]

    bench, daily_mkt = benchmark_series(months, ctx["daily"], uni, panel)
    report_performance(bt, bench, title=f"{STRATEGY_NAME} [{variant}]")
    if variant == "FULL":
        ctx["universe"].report_attrition()

    # 나이브 벤치마크 백테스트 (§8 — 통제의 가치를 보여주는 진짜 비교 대상)
    nv = ctx["naive"]
    nv = nv[[(c, m) in key for c, m in zip(as_str_series(nv["code"]), nv["month"])]] if len(nv) else nv
    bt_naive = run_backtest(nv, panel, months, ctx["sec"], hold=1, label="naive") \
        if len(nv) else {"returns": pd.DataFrame()}

    # ★ 비필수 스테이지가 실패해도 아래 return 이 살아 있어야 한다. 스테이지 안에서만
    #   대입되는 변수를 그대로 반환하면 UnboundLocalError 로 그 유니버스 전체가 날아간다.
    hyp: "pd.DataFrame" = pd.DataFrame()
    with PIPE.stage(f"L5.HYPO.{variant}", f"가설 검정 H1~H5 [{variant}]", "L5",
                    budget_s=900, critical=False):
        HYPO.clear()
        test_H1(S, panel, months)
        test_H2(sig_by_w, panel, months)
        test_H3(ctx["drops"], panel, months)
        test_H4(S, panel, uni, months)
        rev = build_consensus_revision(ctx.get("links"), months)
        test_H5(ctx["vas"], rev, months)
        hyp = finalize_hypotheses()

    with PIPE.stage(f"L5.ROBUST.{variant}", f"강건성 검사 [{variant}]", "L5",
                    budget_s=1500, critical=False):
        ROBUST.clear()
        try:
            R1_bootstrap(bt)
            R2_pbo(GR)
            R3_dsr(bt, GR)
            R4_walkforward(GR, months)
            R5_mexit_placebo(ctx["drops"], panel, months)
            ctx[f"car_{variant}"] = R6_event_study(ctx["drops"], ctx["daily"], daily_mkt)
            R7_cost_sensitivity(
                lambda cost_mult=1.0, label="": run_backtest(
                    S, panel, months, ctx["sec"], hold=head["hold"],
                    cost_mult=cost_mult, label=label), COST_SCENARIOS)
            R8_leakage(ctx["vas"], None,
                       lambda vas_col="VAS", label="": run_backtest(
                           assemble_signal(build_aar_pos(
                               ctx["vas"].assign(VAS=ctx["vas"][vas_col]), head["weight"]),
                               ctx["aar_neg"], uni, lam=head["lam"]),
                           panel, months, ctx["sec"], hold=head["hold"], label=label))
            R9_regime(bt, bench)
            R10_vs_naive(bt, bt_naive)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    report_interpretation(S, ctx["vas"], ctx["drops"])
    return {"variant": variant, "bt": bt, "stats": perf_stats(bt["returns"]), "bench": bench,
            "grid": grid_stats, "grid_returns": GR, "signal": S, "hyp": hyp,
            "robust": dict(ROBUST), "hypo": dict(HYPO), "naive": bt_naive}


def _persist(ctx: dict, results: Dict[str, dict], verdict: str) -> List[str]:
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []

    def _save(name: str, df: "pd.DataFrame"):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{stamp}.csv")
        try:
            df.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
        except Exception as e:                                    # noqa
            LOG.warn(f"{name} 저장 실패({type(e).__name__})")

    for v, r in results.items():
        _save(f"returns_{v}", r["bt"]["returns"])
        _save(f"holdings_{v}", r["bt"].get("holdings", pd.DataFrame()))
        _save(f"metrics_all_configs_{v}",
              pd.DataFrame([{**{k: g[k] for k in ("label", "weight", "lam", "hold")},
                             **g["stats"]} for g in r["grid"]]))
        if len(r.get("hyp", pd.DataFrame())):
            _save(f"hypothesis_{v}", r["hyp"])
        VAULT.put_table(f"backtest_returns_{v}_{STRATEGY_ID}", r["bt"]["returns"],
                        scope="private", domain="backtest", source=STRATEGY_ID)
        if len(ctx.get(f"car_{v}", pd.DataFrame())):
            _save(f"event_study_car_{v}", ctx[f"car_{v}"])
    _save("coverage_exit_classification", ctx.get("drops", pd.DataFrame()))
    if len(ctx.get("vas", pd.DataFrame())):
        _save("attention_panel_sample", ctx["vas"].head(200000))

    summary = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "run_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "backtest": [BACKTEST_START, BACKTEST_END],
        "run_mode": RUN_MODE, "verdict": verdict,
        "phase0": ctx.get("phase0", {}),
        "control_meta": ctx.get("ctrl_meta", {}),
        "variants": {v: {"stats": {k: (float(x) if isinstance(x, (int, float, np.floating))
                                       and np.isfinite(x) else None)
                                   for k, x in r["stats"].items()},
                         "hypotheses": {k: {"pass": h.get("pass"), "fdr_pass": h.get("fdr_pass"),
                                            "p": (float(h["p"]) if np.isfinite(h["p"]) else None)}
                                        for k, h in r["hypo"].items()},
                         "robust": {k: {"pass": x["pass"], "kill": x["kill"]}
                                    for k, x in r["robust"].items()}}
                     for v, r in results.items()},
    }
    sp = os.path.join(outdir, f"run_summary_{stamp}.json")
    atomic_write_text(sp, json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    outs.append(sp)
    lp = os.path.join(outdir, f"log_{stamp}.txt")
    atomic_write_text(lp, "\n".join(LOG.buffer))
    outs.append(lp)
    return outs


def main() -> dict:
    t_all = time.time()
    global VAULT
    LOG.banner(f"ARC-AAR — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START}~{BACKTEST_END} · 유니버스 "
               f"{'/'.join(UNIVERSE_VARIANTS)} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬 / pandas / numpy", f"{ENV['python']} / {pd.__version__} / {np.__version__}"],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["KRX", "비활성 (계정 차단 — marcap 이 전 기능을 대체)"],
               ["전면 캐시", f"HTTP {'ON' if HTTP_CACHE_ENABLED else 'OFF'} · "
                             f"메모 {'ON' if MEMO_ENABLED else 'OFF'}"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        fg = free_gb(VAULT.root)
        if np.isfinite(fg):
            LOG.info(f"여유 공간 {fg:.1f} GB")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise KillCriteria(
                "스모크 테스트 실패 — 하네스가 심어둔 신호를 탐지하지 못했습니다. "
                "이 상태로 실데이터를 돌리면 '알파 없음'이 전략 탓인지 배관 탓인지 "
                "구분할 수 없으므로 수집을 시작하지 않습니다.")

    months = _months()
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 계산 경로를 검증했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.PHASE0", "Phase 0 데이터 실현가능성 게이트", "L1", budget_s=300):
        ctx["phase0"] = phase0_gate(ctx.get("reports"), ctx.get("links")) \
            if PHASE0_ENABLED else {"mode": "ANALYST", "rate": np.nan, "note": "게이트 비활성"}
        if PHASE0_HALT_ON_FAIL and ctx["phase0"].get("mode") == "HOUSE":
            raise KillCriteria("Phase 0 게이트 — 애널리스트 식별률이 40% 미만입니다. "
                               "§12-1 에 따라 보고 후 중단합니다(PHASE0_HALT_ON_FAIL=False 로 "
                               "두면 하우스 단위 폴백으로 자동 진행합니다).")

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    ctx = build_signals(ctx, months)

    results: Dict[str, dict] = {}
    for variant in UNIVERSE_VARIANTS:
        with PIPE.stage(f"L3.BT.{variant}", f"백테스트·검정 [{variant}]", "L3", budget_s=2400,
                        critical=False):
            r = run_universe(ctx, months, variant)
            if r:
                results[variant] = r

    if not results:
        raise RuntimeError("어떤 유니버스에서도 결과를 만들지 못했습니다. "
                           "위 FLOW 원장에서 어느 단계가 0행을 냈는지 확인하세요.")

    with PIPE.stage("L6.REPORT", "비교표 · 해석 · 최종판정", "L6", budget_s=300, critical=False):
        report_universe_compare(results)
        main_hyp = results.get("FULL", next(iter(results.values()))).get("hyp", pd.DataFrame())
        HYPO.clear()
        HYPO.update(results.get("FULL", next(iter(results.values()))).get("hypo", {}))
        ROBUST.clear()
        ROBUST.update(results.get("FULL", next(iter(results.values()))).get("robust", {}))
        verdict = final_verdict(results, main_hyp)
        ctx["verdict"] = verdict

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = _persist(ctx, results, ctx.get("verdict", "INCONCLUSIVE"))
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        for q in QUOTA.values():
            q.close()
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
    LOG.info("한계 명시 — ① 컨센서스 EPS 는 역사적 복원이 불가능해 목표주가 리비전으로 "
             "대체했습니다(H5 는 그 대리변수 대비 선행성입니다). ② 금융투자협회 전문인력 "
             "조회는 접근 불가라 인사이동 판정은 '동일 애널이 다른 종목은 계속 커버하는가' "
             "프록시로 대체했습니다. ③ 산업분류는 현재 시점 분류를 씁니다. "
             "④ 이 전략은 선행 문헌이 존재하는 아이디어의 한국시장 조작화이지 "
             "새로운 학술적 발견이 아닙니다.")
    offer_download(ctx.get("outputs", []))
    return {"ctx": ctx, "results": results}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
        try:
            report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 캐시에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
