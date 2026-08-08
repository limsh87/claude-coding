
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]) -> None:
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크. 산출물이 많으면 zip 하나로 묶는다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    zp = None
    try:
        import zipfile as _zf
        zp = out_path(f"ARC_BDF_outputs_{now_kst():%Y%m%d_%H%M}.zip")
        with _zf.ZipFile(zp, "w", _zf.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, arcname=os.path.basename(p))
    except Exception as e:                                            # noqa
        LOG.warn(f"산출물 압축 실패({type(e).__name__}) — 개별 파일로 안내합니다.")
        zp = None

    targets = [zp] if zp else paths
    _safe_print("")
    for p in targets:
        _safe_print(f"  산출물: {os.path.abspath(p)}")   # ★ 링크가 안 떠도 경로는 항상 보인다

    if ENV.get("colab"):
        try:
            from google.colab import files as _f       # type: ignore
            for p in targets:
                _f.download(p)
        except Exception:
            pass
    try:
        from IPython.display import display, HTML      # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in targets:
            n = os.path.getsize(p)
            if n > 5 * 1024 * 1024:                    # 5MB 초과분을 노트북에 박으면 .ipynb 가 붓는다
                html.append(f"<div>· {os.path.basename(p)} ({n/1e6:.1f}MB) — "
                            f"<code>{os.path.abspath(p)}</code></div>")
                continue
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({n/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════════════════
def collect_all() -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지' 를 남긴다."""
    ctx: Dict[str, Any] = {}
    warm = (as_ts(BACKTEST_START) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.DGK", "공공데이터 일별 전종목 (시총·상장주식수)", "L1",
                    budget_s=5400, critical=False):
        ctx["dgk"] = fetch_datagokr_panel(warm, BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · 상장/폐지 이력", "L1", budget_s=900):
        snaps = (dgk_listing_snapshots(ctx["dgk"]) if len(ctx.get("dgk", []))
                 else fetch_listing_snapshots(date_range_me(BACKTEST_START, BACKTEST_END)))
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    with PIPE.stage("L1.PX", "가격 · 거래대금", "L1", budget_s=5400):
        codes = ctx["sec"]["code"].tolist()
        px = fetch_prices(codes, warm, BACKTEST_END)
        if len(ctx.get("dgk", [])):
            # 공공데이터 시세를 가격 패널에 합류시킨다(가장 신뢰도 높은 소스)
            g = ctx["dgk"].reindex(columns=PRICE_COLS + ["shares", "marcap"]).copy()
            g["src"] = "datagokr"
            px = concat_nonempty([g.reindex(columns=PRICE_COLS), px], cols=PRICE_COLS)
            px = (px.sort_values(["code", "date"], kind="stable")
                    .drop_duplicates(["code", "date"], keep="first").reset_index(drop=True))
        ctx["px"] = px
        ctx["cal"] = build_trading_calendar(px)

    with PIPE.stage("L1.MCAP", "PIT 시가총액 사다리", "L1", budget_s=1800, critical=False):
        corps = (ctx["sec"]["corp_code"].dropna().astype(str).tolist()
                 if "corp_code" in ctx["sec"].columns else [])
        years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
        shares_pit = fetch_dart_shares(corps, years)
        cur = fetch_current_shares(ctx["sec"])
        mc = build_marketcap_panel(ctx["px"], ctx["sec"], shares_pit, cur)
        if len(ctx.get("dgk", [])):
            # ★ 공공데이터의 시총/주식수는 '그 시점 값' 이므로 T1 보다도 우선한다
            g = ctx["dgk"][["code", "date", "marcap", "shares"]].dropna(subset=["marcap"])
            mc = mc.merge(g.rename(columns={"marcap": "mc_dgk"}), on=["code", "date"],
                          how="left")
            hit = mc["mc_dgk"].notna()
            set_where(mc, hit, "marcap", mc.loc[hit, "mc_dgk"])
            set_where(mc, hit, "mc_tier", "T0")
            mc = mc.drop(columns=[c for c in ("mc_dgk", "shares") if c in mc.columns])
            LOG.ok(f"공공데이터 시총으로 {int(hit.sum()):,}행을 T0(정품 관측)으로 승격 — "
                   f"{100*hit.mean():.1f}%. 이 비율이 높을수록 H4/비교전략이 정확합니다.")
        ctx["mc"] = assign_size_bucket(mc)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=7200, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한하며, "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE not in ("CACHED", "SMOKE") and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                nv = naver_enrich_detail(nv)
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.ok(f"★ 공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 — "
                   f"드라이브에 이미 쌓인 리포트를 그대로 씁니다(재수집 없음).")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep) and RESEARCH_DOWNLOAD_PDF:
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    set_where(rep, fill, "target_price", rep.loc[fill, "pdf_target"])
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared",
                            domain="research", source="hankyung+naver",
                            extra={"note": "리포트 원장 — 전 전략 공용"})
        ctx["rep"] = rep
        A, L = build_analyst_ledger(rep) if len(rep) else (pd.DataFrame(), pd.DataFrame())
        ctx["analysts"], ctx["links"] = A, L
        if len(rep):
            audit_linkage(rep, A, L)
            if len(A):
                VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                                source=STRATEGY_ID)
            if len(L):
                VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                                source=STRATEGY_ID)

    with PIPE.stage("L1.FLOW", "플로우 수집 (거래원 / 투자자별)", "L1",
                    budget_s=int(FLOW_TIME_BUDGET_MIN * 60 * 1.3), critical=False):
        ev_codes = (sorted(set(ctx["rep"]["stock_code"].dropna().map(to_code6).dropna()))
                    if len(ctx.get("rep", [])) else ctx["sec"]["code"].tolist())
        LOG.info(f"플로우 수집 대상 {len(ev_codes):,}종목 (리포트가 존재하는 종목만 — "
                 f"전 종목을 긁으면 요청수가 10배가 되고 차단 위험이 그만큼 커집니다)")
        if RUN_MODE != "SMOKE":
            canary = collect_member_snapshot(ev_codes[:FLOW_CANARY_TICKERS], limit=FLOW_CANARY_TICKERS)
            LOG.info(f"카나리(거래원 {FLOW_CANARY_TICKERS}종목): "
                     f"{'도달 성공' if len(canary) else '도달 실패(전진수집만 영향)'}")
        fr = fetch_foreign_ratio(ev_codes, BACKTEST_START, BACKTEST_END)
        fnet = foreign_net_from_ratio(fr, ctx.get("mc"))
        inv = fetch_investor_flow_paged(ev_codes, BACKTEST_START, BACKTEST_END)
        snap = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
        ctx["bm"] = load_broker_map()
        mem_daily = (member_snapshot_to_daily(snap, ctx["px"], ctx["bm"])
                     if snap is not None and len(snap) else pd.DataFrame())
        ctx["flow"] = build_flow_panel(inv, fnet, mem_daily, ctx["px"])
        ctx["member_days"] = int(pd.Series(snap["trade_date"]).nunique()) if snap is not None and len(snap) else 0
    return ctx


def build_signal_frame(ctx: dict, mode: str, k: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """이벤트 패널 + 플로우 잔차 → 신호 프레임 (원값/잔차 모두)."""
    uni = ctx["uni"]
    E = attach_matched_actor(ctx["events"], mode)
    R = build_flow_raw(ctx["flow"], k=k)
    RES = residualize_flow(R, k=k, baseline=GRID_BASELINE_DAYS)
    S = attach_signal(E, RES)

    mc = ctx.get("mc")
    if mc is not None and len(mc):
        S = S.merge(mc[["code", "date", "marcap", "adv20", "turnover", "size_bucket"]],
                    on=["code", "date"], how="left")
    else:
        for c, v in (("marcap", np.nan), ("adv20", np.nan), ("turnover", np.nan)):
            S[c] = v
        S["size_bucket"] = "중형"
    # 직전 20일 수익률 (통제변수) — 이벤트일 '이전' 구간만 쓴다
    px = ctx["px"]
    cl = px.pivot_table(index="code", columns="date", values="close", aggfunc="last",
                        observed=True).reindex(columns=ctx["cal"]).ffill(axis=1)
    dpos = {d: i for i, d in enumerate(ctx["cal"])}
    cpos = {c: i for i, c in enumerate(cl.index)}
    arr = cl.to_numpy(float)
    r20 = []
    for c, d in zip(S["code"], S["date"]):
        i, j = cpos.get(c), dpos.get(pd.Timestamp(d))
        if i is None or j is None or j < 21:
            r20.append(np.nan)
            continue
        a, b = arr[i, j - 21], arr[i, j - 1]
        r20.append(b / a - 1.0 if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan)
    S["ret20"] = r20
    S = attach_industry(S, ctx["sec"])

    S["sig_raw"] = control_residual(S.assign(_x=S["flow_raw"]), "flow_raw", pit=True)
    S["sig_resid"] = control_residual(S.assign(_x=S["flow_resid"]), "flow_resid", pit=True)
    # 통제회귀가 성립하지 않는 초기 구간은 원신호를 그대로 쓴다(0으로 채우지 않는다)
    set_where(S, S["sig_raw"].isna() & S["flow_raw"].notna(), "sig_raw",
              S.loc[S["sig_raw"].isna() & S["flow_raw"].notna(), "flow_raw"])
    set_where(S, S["sig_resid"].isna() & S["flow_resid"].notna(), "sig_resid",
              S.loc[S["sig_resid"].isna() & S["flow_resid"].notna(), "flow_resid"])
    return S, RES


def run_grid(ctx: dict, mode: str, universe_mask: Optional[pd.DataFrame] = None,
             label: str = "") -> dict:
    """SPEC §6.6 사전등록 12구성 백테스트 (+ 비용 3종)."""
    out: Dict[str, Any] = {"bts": {}, "cost": {}, "S_by_k": {}, "RES_by_k": {}}
    for k, _ in GRID_FLOW_WINDOWS:
        pass
    for (k, kk) in GRID_FLOW_WINDOWS:
        S, RES = build_signal_frame(ctx, mode, k=kk)
        if universe_mask is not None and len(universe_mask):
            S = S.merge(universe_mask, on=["code", "date"], how="left")
            n0 = len(S)
            S = S[S["in_small"].fillna(False)]
            LOG.info(f"[{label}] k={kk} — 유니버스 제한으로 이벤트 {n0:,} → {len(S):,}건")
        out["S_by_k"][kk] = S
        out["RES_by_k"][kk] = RES
        for hold in GRID_HOLD_DAYS:
            for ver in GRID_SIGNAL_VERSIONS:
                cfg = BTConfig(k=kk, hold=hold, version=ver)
                bt = run_event_backtest(S, ctx["px"], ctx["cal"], ctx["uni"], cfg,
                                        sec=ctx["sec"])
                out["bts"][cfg.name()] = bt
    LOG.ok(f"[{label or mode}] 사전등록 12구성 백테스트 완료 "
           f"({len(out['bts'])}개 — SPEC §6.6 격자 확장 없음)")
    return out


def run_full(ctx: dict, mode: str, tag: str, universe_mask=None) -> dict:
    """한 유니버스에 대한 전체 파이프라인: 백테스트 → 이벤트스터디 → 가설 → 강건성 → 판정."""
    LOG.banner(f"[{tag}] 백테스트 · 검증", f"모드={mode}")
    G = run_grid(ctx, mode, universe_mask, label=tag)
    bts = G["bts"]
    if not bts:
        LOG.error(f"[{tag}] 백테스트 결과가 없습니다.")
        return {}

    cal = ctx["cal"]
    valid = {n: b for n, b in bts.items() if (b.get("stats") or {}).get("이벤트체결수", 0) > 0}
    if not valid:
        LOG.error(f"[{tag}] 체결이 발생한 구성이 없습니다.")
        return {}
    best = max(valid, key=lambda n: valid[n]["stats"].get("Sharpe", -9e9)
               if np.isfinite(valid[n]["stats"].get("Sharpe", np.nan)) else -9e9)
    best_cfg = valid[best]["cfg"]

    S_best = G["S_by_k"][best_cfg.k]
    bench = build_benchmarks(ctx["px"], cal, S_best, ctx["uni"], ctx["sec"], best_cfg)
    M = report_performance(bts, bench, cal, title=f"— {tag} ({mode})")
    report_yearly(bts, best, bench, cal)

    # ── 이벤트 스터디 ─────────────────────────────────────────────────────────────────────
    sig_col = "sig_resid" if best_cfg.version == "resid" else "sig_raw"
    nore = build_noreport_control(G["RES_by_k"][best_cfg.k], S_best, cal)
    groups = split_groups(S_best, sig_col, nore)
    car = report_event_study(groups, ctx["px"], cal)
    car_ascii(car)

    # ── 가설 ──────────────────────────────────────────────────────────────────────────────
    res = test_hypotheses(groups, S_best, ctx["px"], cal, ctx["bm"], mode,
                          entry_offset=best_cfg.entry_offset)

    # ── 강건성 ────────────────────────────────────────────────────────────────────────────
    rob: Dict[str, Any] = {}
    r_best = valid[best]["daily"]["ret"].to_numpy(float)
    bb = block_bootstrap(r_best, n_iter=N_BOOT, block=BLOCK_LEN)
    rob["블록부트스트랩(21일,1000회)"] = {
        "value": f"Sharpe {bb['obs']:.2f} [{bb['ci_lo']:.2f}, {bb['ci_hi']:.2f}]",
        "thresh": "CI 하한 > 0", "pass": bool(np.isfinite(bb["ci_lo"]) and bb["ci_lo"] > 0),
        "note": f"p(우측꼬리)={bb['p_gt0']:.3f}", "raw": bb["ci_lo"]}

    P = np.column_stack([b["daily"]["ret"].reindex(range(len(cal))).fillna(0).to_numpy(float)
                         if len(b["daily"]) == len(cal)
                         else np.zeros(len(cal)) for b in valid.values()])
    pb = pbo_cscv(P, n_split=8)
    rob["PBO"] = {"value": f"{pb['pbo']:.3f}", "thresh": "< 0.50",
                  "pass": bool(np.isfinite(pb["pbo"]) and pb["pbo"] < 0.5),
                  "note": f"CSCV {pb['n_comb']}조합 · 구성 {pb['n_config']}개", "raw": pb["pbo"]}

    srs = np.array([v["stats"].get("Sharpe", np.nan) / math.sqrt(252) for v in valid.values()])
    ds = deflated_sharpe(r_best, srs, n_trials=len(bts))
    rob["DSR"] = {"value": f"{ds['dsr']:.3f}", "thresh": "> 0.50",
                  "pass": bool(np.isfinite(ds["dsr"]) and ds["dsr"] > 0.5),
                  "note": f"시도 {ds['n_trials']}회 · E[maxSR]={ds['sr0']:.3f} · "
                          f"왜도 {ds['skew']:+.2f}", "raw": ds["dsr"]}

    W = walk_forward({n: b["daily"] for n, b in valid.items()}, cal)
    wf_ok = bool(len(W) and (W["검증수익"] > 0).mean() >= 0.5)
    rob["워크포워드(5년/1년)"] = {"value": f"{100*(W['검증수익']>0).mean():.0f}% 양(+)"
                                if len(W) else "-", "thresh": "≥ 50%",
                                "pass": wf_ok if len(W) else None,
                                "note": f"검증 {len(W)}개 연도", "raw": len(W)}

    mu_nw, t_nw = hac_tstat(r_best)
    rob["뉴이-웨스트 t"] = {"value": f"{t_nw:+.2f}", "thresh": "> 2.0",
                          "pass": bool(np.isfinite(t_nw) and t_nw > 2.0),
                          "note": "캘린더타임 일별수익 (겹침 상관 흡수)", "raw": t_nw}

    # ── 플라시보 ──────────────────────────────────────────────────────────────────────────
    PL = make_placebo_events(S_best[["code", "date", "actor", "broker", "broker_tier",
                                     "size_bucket"]].copy(), cal)
    placebo_clean = True
    pl_t = np.nan
    if len(PL):
        PR = G["RES_by_k"][best_cfg.k]
        PS = PL.merge(PR, on=["actor", "code", "date"], how="left")
        PS["sig_resid"] = PS["flow_resid"]
        PS["sig_raw"] = PS["flow_raw"]
        pg = split_groups(PS, sig_col)
        ar = _abnormal_returns(pg.get("확증군(리포트+순매수상위30%)"), ctx["px"], cal,
                               H_HORIZON, best_cfg.entry_offset)
        _, pl_t, pl_p, pl_n = _mean_t(ar)
        placebo_clean = not (np.isfinite(pl_t) and abs(pl_t) >= 2.0)
        rob["플라시보(±20~60일 이동)"] = {
            "value": f"t={pl_t:+.2f}", "thresh": "|t| < 2.0",
            "pass": placebo_clean, "raw": pl_t,
            "note": f"n={pl_n:,} · 유의하면 파이프라인에 미래참조가 있다는 뜻"}
    report_robustness(rob)

    # ── 비용 3종 ──────────────────────────────────────────────────────────────────────────
    cost_bts: Dict[str, Dict[str, dict]] = {}
    naive_by_cost: Dict[float, float] = {}
    for lab, mult in COST_SCENARIOS:
        cfg = BTConfig(k=best_cfg.k, hold=best_cfg.hold, version=best_cfg.version,
                       cost_mult=mult)
        cost_bts[lab] = {best: run_event_backtest(S_best, ctx["px"], cal, ctx["uni"], cfg,
                                                  sec=ctx["sec"])}
        nb = build_benchmarks(ctx["px"], cal, S_best, ctx["uni"], ctx["sec"], cfg)
        nbt = nb.get("_naive_bt")
        naive_by_cost[mult] = (nbt["stats"].get("CAGR", np.nan) if nbt else np.nan)
    cost_md = report_costs(cost_bts, naive_by_cost, best)
    survive2x = "**2배 비용 시나리오 생존: 예**" in cost_md

    report_interpretation(res, mode)
    return {"bts": bts, "best": best, "best_cfg": best_cfg, "M": M, "res": res,
            "rob": rob, "cost_md": cost_md, "survive2x": survive2x,
            "placebo_clean": placebo_clean, "car": car, "groups": groups,
            "S": S_best, "bench": bench, "W": W}


# ══════════════════════════════════════════════════════════════════════════════════════════
def main() -> dict:
    t_start = time.time()
    LOG.banner(f"{SPEC_ID} — {STRATEGY_NAME}",
               f"빌드 {BUILD_VERSION} · 구간 {BACKTEST_START} ~ {BACKTEST_END} · 모드 {RUN_MODE}")
    report_compat()

    # [0-a] 구글드라이브 캐시 연결 — ★ 절대 1원칙: 기존 인덱스를 훼손하지 않는다
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시(공용/전용) 연결", "L0", budget_s=600):
        root, dmode = _mount_drive()
        globals()["VAULT"] = Vault(root, dmode)
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {dmode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유(가격·리포트·플로우 원본)")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유(이벤트패널·백테스트 결과)")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"  여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)     # 기존 리포트를 '이동 없이 등록만'
        VAULT.report()

    # [0-b] 계약
    with PIPE.stage("V.CONTRACT", "계약 자동검정 K1~K16", "V0", budget_s=300):
        run_contracts(strict=True)
    # [1] 스모크
    with PIPE.stage("V.SMOKE", "합성 스모크", "V1", budget_s=600):
        run_smoke(strict=True)
    # [2] 리허설
    with PIPE.stage("V.REHEARSAL", "실경로 리허설", "V2", budget_s=300):
        run_rehearsal(strict=True)

    if RUN_MODE == "SMOKE":
        # ★ 여기서 멈추면 '전 출력물 예행연습' 이라는 약속을 못 지킨다.
        #   합성데이터로 ctx 를 만들어 실제와 동일한 경로로 백테스트~최종판정까지 전부 돌린다.
        #   네트워크·키 없이 성과표·강건성표·해석표·비교표·산출물이 모두 나온다.
        ctx = _synthetic_ctx()
        report_dataflow(ctx)
        main_out = run_full(ctx, "MEMBER", tag="합성 · 전체 유니버스")
        small_out = {}
        if COMPARE_SMALLCAP_ENABLE and len(ctx.get("mc", [])):
            mask = smallcap_universe(ctx["mc"], max(50, COMPARE_SMALLCAP_N // 20))
            small_out = run_full(ctx, "MEMBER", tag=f"합성 · {COMPARE_SMALLCAP_LABEL}",
                                 universe_mask=mask)
        _emit_outputs(ctx, main_out, small_out,
                      {"branch": "SMOKE", "sources": [], "notes": []}, "MEMBER", t_start)
        LOG.ok("SMOKE 완료 — 위 표들이 실데이터에서도 그대로 나옵니다. "
               "RUN_MODE='FULL' 로 바꾸면 실데이터로 진행합니다.")
        PIPE.report_stages()
        return {"mode": "SMOKE", "main": main_out, "small": small_out}

    # [3] ★ Phase 0 게이트
    with PIPE.stage("P0.GATE", "Phase 0 데이터 실현가능성 게이트", "P0", budget_s=3600):
        p0 = run_phase0_gate()
    mode = "MEMBER" if p0["branch"] in ("FULL10", "PARTIAL") else "PROXY"
    if RUN_MODE == "PHASE0":
        LOG.ok("PHASE0 모드 — 게이트 결과만 보고하고 종료합니다 (SPEC §12-1).")
        offer_download([out_path(PHASE0_MD), out_path("forward_collect_member_flow.py")])
        PIPE.report_stages()
        return {"phase0": p0}

    # [4] 수집
    ctx = collect_all()
    ctx["mode"] = mode
    report_dataflow(ctx)

    # [5] 매핑 감사 + PIT 유니버스 + 이벤트
    with PIPE.stage("L2.MAP", "증권사↔거래원 매핑 감사", "L2", budget_s=300, critical=False):
        ctx["bm"] = ctx.get("bm") or load_broker_map()
        aud = audit_broker_mapping(ctx["bm"], ctx.get("rep"), ctx.get("flow"))
        ctx["map_audit"] = aud

    with PIPE.stage("L2.UNI", "PIT 유니버스", "L2", budget_s=600):
        ctx["uni"] = DailyUniverse(ctx["sec"], ctx["px"], ctx.get("dgk"), ctx.get("snapshots"))

    with PIPE.stage("L2.EVENT", "매수성 리포트 이벤트 패널", "L2", budget_s=900):
        ctx["events"] = build_event_panel(ctx["rep"], ctx["bm"], ctx["uni"], ctx["cal"])
        ctx["uni"].report_attrition()
        if not len(ctx["events"]):
            raise KillCriteria("매수성 이벤트가 0건입니다 — 리포트 수집/파싱을 먼저 확인하세요.")

    # [6] 본 전략
    main_out = run_full(ctx, mode, tag="전체 유니버스")

    # [7] ★ 비교 전략: 시총 하위 1000
    small_out = {}
    if COMPARE_SMALLCAP_ENABLE and len(ctx.get("mc", [])):
        with PIPE.stage("CMP.SMALL", f"비교전략 — {COMPARE_SMALLCAP_LABEL}", "L3",
                        budget_s=2400, critical=False):
            mask = smallcap_universe(ctx["mc"], COMPARE_SMALLCAP_N)
            small_out = run_full(ctx, mode, tag=COMPARE_SMALLCAP_LABEL, universe_mask=mask)

    # [8] 비교표
    if main_out and small_out:
        a, b = main_out["bts"][main_out["best"]]["stats"], \
               small_out["bts"][small_out["best"]]["stats"]
        rows = []
        for key, fmt in (("CAGR", "{:+.2%}"), ("Sharpe", "{:.2f}"), ("Sortino", "{:.2f}"),
                         ("MDD", "{:.1%}"), ("Calmar", "{:.2f}"), ("t통계량(NW)", "{:+.2f}"),
                         ("이벤트체결수", "{:,.0f}"), ("승률", "{:.0%}"),
                         ("연회전율", "{:.1f}"), ("평균보유종목", "{:.1f}")):
            va, vb = a.get(key, np.nan), b.get(key, np.nan)
            try:
                sa, sb = fmt.format(va), fmt.format(vb)
            except Exception:
                sa, sb = str(va), str(vb)
            rows.append([key, sa, sb,
                         ("소형 우위" if (np.isfinite(va) and np.isfinite(vb) and vb > va)
                          else "전체 우위") if key not in ("MDD",) else
                         ("소형 우위" if (np.isfinite(va) and np.isfinite(vb) and vb > va)
                          else "전체 우위")])
        LOG.table(rows, ["지표", "전체 유니버스", COMPARE_SMALLCAP_LABEL, "비교"],
                  ["l", "r", "r", "c"],
                  title=f"★ 전략 비교 — 전체 유니버스 vs {COMPARE_SMALLCAP_LABEL} "
                        f"(H4 '소형주에서 더 강하다' 의 직접 검정)")
        LOG.info("※ 소형주 우위가 나오더라도 슬리피지가 3.5배(35bp vs 10bp)이므로 "
                 "비용 반영 후 초과가 남는지를 비용 민감도표에서 반드시 확인하세요.")

    # [9] 산출물
    _emit_outputs(ctx, main_out, small_out, p0, mode, t_start)
    return {"ctx": ctx, "main": main_out, "small": small_out, "phase0": p0}


def _synthetic_ctx() -> dict:
    """SMOKE 전용 — 합성데이터로 실데이터와 동일한 구조의 ctx 를 만든다.
    사이즈 버킷·상장폐지·무리포트 대조군까지 실제로 생성해 H4/H5 경로도 실행되게 한다."""
    syn = make_synthetic(n_codes=160, n_days=1800)   # ~7.1년 — 워크포워드 창이 실제로 잡히도록
    cal, px, sec, F, E = syn["cal"], syn["px"], syn["sec"], syn["flow"], syn["events"]
    rng = np.random.default_rng(SEED)
    mc = px[["code", "date", "close", "volume", "amount"]].copy()
    scale = pd.Series(rng.lognormal(0, 1.6, len(syn["codes"])), index=syn["codes"])
    mc["marcap"] = mc["close"] * mc["volume"] * mc["code"].map(scale) * 50
    mc["adv20"] = mc.groupby("code", observed=True)["amount"].transform(
        lambda s: s.rolling(20, min_periods=5).mean())
    mc["turnover"] = safe_div(mc["amount"], mc["marcap"])
    mc["mc_tier"] = "SYN"
    mc = assign_size_bucket(mc)
    bm = load_broker_map()
    ctx = {"cal": build_trading_calendar(px), "px": px, "sec": sec, "flow": F,
           "events": E, "mc": mc, "bm": bm, "rep": pd.DataFrame(),
           "dgk": pd.DataFrame(), "snapshots": pd.DataFrame(),
           "uni": DailyUniverse(sec, px), "mode": "MEMBER", "member_days": 0}
    ctx["events"] = ctx["events"].assign(date=as_ts_series(ctx["events"]["pub_date"]))
    return ctx


def _emit_outputs(ctx: dict, main_out: dict, small_out: dict, p0: dict, mode: str,
                  t_start: float) -> List[str]:
    """산출물 생성 — SMOKE 와 FULL 이 같은 경로를 쓴다(예행연습이 실제와 같아야 한다)."""
    outs: Dict[str, str] = {}
    if main_out:
        outs["FINAL_VERDICT.md"] = final_verdict(
            main_out["res"], main_out["rob"], main_out["cost_md"], mode,
            main_out["survive2x"], main_out["placebo_clean"])
        outs["cost_sensitivity.md"] = main_out["cost_md"]
        outs["mechanism_tests.md"] = report_mechanism(main_out["res"], mode)
        outs["hypothesis_test_report.md"] = _hyp_md(main_out, mode)
        outs["placebo_test.md"] = _placebo_md(main_out)
        outs["broker_member_map_audit.md"] = _map_md(ctx.get("map_audit", {}), ctx["bm"])
        outs["OPEN_QUESTIONS.md"] = _open_questions_md(p0, mode, ctx)
        if small_out:
            outs["smallcap_comparison.md"] = _cmp_md(main_out, small_out)
        try:
            main_out["M"].to_csv(out_path("metrics_all_configs.csv"), index=False,
                                 encoding="utf-8-sig")
            atomic_write_parquet(main_out["M"], out_path("metrics_all_configs.parquet"))
            eq = pd.DataFrame({n: b["daily"].set_index("date")["ret"]
                               for n, b in main_out["bts"].items() if len(b["daily"])})
            atomic_write_parquet(eq.reset_index(), out_path("equity_curves.parquet"))
            tl = main_out["bts"][main_out["best"]]["trades"]
            if len(tl):
                atomic_write_parquet(tl, out_path("trade_log.parquet"))
            write_json(out_path("run_summary.json"), {
                "strategy": "ARC-BDF-PROXY" if mode == "PROXY" else "ARC-BDF",
                "build": BUILD_VERSION, "run_mode": RUN_MODE, "signal_mode": mode,
                "phase0_branch": p0.get("branch"),
                "period": [BACKTEST_START, BACKTEST_END],
                "best_config": main_out["best"],
                "n_events": int(len(ctx.get("events", []))),
                "n_configs": len(main_out["bts"]),
                "verdict": ("KILL" if not main_out["placebo_clean"] else "본문 참조"),
                "elapsed_min": round((time.time() - t_start) / 60.0, 2)})
        except Exception as e:                                        # noqa
            LOG.warn(f"결과 파일 저장 일부 실패: {type(e).__name__}: {e}")
    paths = write_outputs(outs)
    for extra in ("metrics_all_configs.csv", "metrics_all_configs.parquet",
                  "event_study_car.parquet", "equity_curves.parquet",
                  "trade_log.parquet", "run_summary.json",
                  PHASE0_MD, "forward_collect_member_flow.py"):
        q = out_path(extra)
        if os.path.exists(q):
            paths.append(q)

    PIPE.report_stages()
    PIPE.report_runtime()
    report_http()
    try:
        VAULT.flush()
        VAULT.report()
    except Exception:
        pass
    LOG.banner("완료", f"총 {(time.time()-t_start)/60:.1f}분 · 산출물 {len(paths)}개")
    offer_download(paths)
    return paths


def _hyp_md(o: dict, mode: str) -> str:
    L = ["# 가설 검정 보고서 (H1~H5 + BH-FDR + PBO/DSR)", "",
         f"- 모드: **{mode}**  ·  대표구성: `{o['best']}`", "",
         "| ID | 가설 | 효과크기 | t | 표본 | 판정 |", "|---|---|---|---|---|---|"]
    for r in o["res"]["rows"]:
        L.append("| " + " | ".join(str(x) for x in r) + " |")
    L += ["", "## 다중검정 보정 (BH-FDR q=0.10)", "",
          o["res"]["fdr"].to_markdown(index=False) if hasattr(o["res"]["fdr"], "to_markdown")
          else o["res"]["fdr"].to_string(index=False), "",
          "## 강건성", "", "| 검정 | 값 | 기준 | 판정 |", "|---|---|---|---|"]
    for k, v in o["rob"].items():
        if isinstance(v, dict):
            L.append(f"| {k} | {v.get('value','-')} | {v.get('thresh','-')} | "
                     f"{'통과' if v.get('pass') else ('판정불가' if v.get('pass') is None else '실패')} |")
    return "\n".join(L) + "\n"


def _placebo_md(o: dict) -> str:
    v = o["rob"].get("플라시보(±20~60일 이동)", {})
    return "\n".join([
        "# 플라시보 테스트 (look-ahead 검증)", "",
        "이벤트 날짜를 ±20~60영업일 무작위로 이동시킨 '가짜 이벤트' 로 동일 파이프라인을 돌린다.",
        "종목·증권사·신호 분포는 그대로 두고 **시점만** 흔들기 때문에, 여기서 효과가 나온다면",
        "그것은 알파가 아니라 시점 정렬에서 오는 누수다.", "",
        f"- 결과: **{v.get('value','-')}**  (기준 {v.get('thresh','-')})",
        f"- 판정: **{'무효과 — 파이프라인 정상' if v.get('pass') else '★효과 검출 — 파이프라인 결함 의심'}**",
        f"- {v.get('note','')}", "",
        "플라시보에서 유의한 효과가 나오면 SPEC §11 에 따라 **KILL** 이다. 결과 전체를 폐기한다."]) + "\n"


def _map_md(aud: dict, bm) -> str:
    L = ["# 증권사 ↔ 거래원 회원사 매핑 감사 (SPEC §5)", "",
         f"- 리포트 원장 증권사명 비공백률: {100*aud.get('broker_fill_rate', float('nan')):.1f}%",
         f"- 리포트 → 정식명 매핑 성공률: {100*aud.get('report_rate', float('nan')):.1f}%",
         f"- 거래원 창구 → 정식명 매핑 성공률: {100*aud.get('flow_rate', float('nan')):.1f}%",
         f"- SPEC §5 한계(실패율 20%) 충족: **{'예' if aud.get('ok') else '아니오'}**", "",
         "## 사명변경·합병 반영 내역", "", "| 시점 | 내용 |", "|---|---|"]
    for y, c in aud.get("name_changes", []):
        L.append(f"| {y} | {c} |")
    L += ["", "## 미매핑 (버리지 않고 기록)", ""]
    um = list(bm.unmapped.most_common(30)) if hasattr(bm, "unmapped") else []
    if um:
        L += ["| 원문 | 건수 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in um]
    else:
        L.append("없음")
    L += ["", "## 비증권 법인 차단 (오매칭 방지)", "",
          "미래에셋생명 / 한국투자파트너스 / 키움투자자산운용 / IBK기업은행 등은 이름이 비슷해도",
          "증권사가 아니므로 매핑에서 차단한다. 그대로 두면 '자사 창구' 신호에 남의 주문이 섞인다.",
          "", "`config/broker_member_map.csv` 를 직접 수정하면 그 값이 우선 적용된다."]
    return "\n".join(L) + "\n"


def _cmp_md(a: dict, b: dict) -> str:
    sa, sb = a["bts"][a["best"]]["stats"], b["bts"][b["best"]]["stats"]
    L = [f"# 비교: 전체 유니버스 vs {COMPARE_SMALLCAP_LABEL}", "",
         "동일한 파이프라인·동일한 사전등록 격자를, 유니버스만 바꿔 재실행한 결과다.",
         "이것은 H4('저유동성·소형주에서 더 강하다')의 직접 검정이기도 하다.", "",
         "| 지표 | 전체 유니버스 | " + COMPARE_SMALLCAP_LABEL + " |", "|---|---|---|"]
    for k in ("CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "t통계량(NW)",
              "이벤트체결수", "승률", "평균보유일", "연회전율"):
        L.append(f"| {k} | {sa.get(k, float('nan')):.4g} | {sb.get(k, float('nan')):.4g} |")
    L += ["", "## 해석 시 주의", "",
          "- 소형주는 편도 슬리피지가 35bp 로 대형주(10bp)의 3.5배다. 총수익이 높아도",
          "  비용 반영 후 초과가 남는지는 비용 민감도표에서 따로 확인해야 한다.",
          "- 시가총액 하위 1000 은 **매 거래일 횡단면에서 재선정**한다(PIT). 오늘의 시총으로",
          "  과거를 자르면 그 자체가 미래참조이며, 그 경우 소형주 성과가 크게 과대평가된다.",
          "- 시총 사다리가 T2~T4 로 강등된 구간에서는 '하위 1000' 선정에 근사가 섞인다."]
    return "\n".join(L) + "\n"


def _open_questions_md(p0: dict, mode: str, ctx: dict) -> str:
    return "\n".join([
        "# OPEN QUESTIONS", "",
        "명세가 애매해 임의 판단하지 않고 기록해 둔 지점들. 전부 **가장 보수적인 선택**을 했다.", "",
        "## 1. 거래원 이력 부재에 따른 신호 대체 (SPEC §4.3 B-2)",
        f"- Phase 0 판정: **{p0.get('branch')}**, 실행 모드: **{mode}**",
        "- PROXY 에서 '기관/외국인을 단순 합산' 하는 대신 **발행사 계열 정합**(외국계→외국인,",
        "  국내→기관)을 택했다. 브로커 정체성을 조금이라도 보존하는 쪽이 원 가설에 가깝다.",
        "  단순 합산 버전도 계산은 가능하지만 사전등록 격자를 늘리지 않기 위해 넣지 않았다.", "",
        "## 2. §6.3 두 번째 항의 해석",
        "- `median_{과거 60일}[FLOW_raw(B,·,d)]` 을 '그날 창구의 횡단면 중앙값을 시계열로 만든 뒤",
        "  과거 60일 중앙값' 으로 해석했다. 다른 해석(그날 횡단면 중앙값 자체)도 가능하지만,",
        "  그러면 '과거 60일' 이라는 수식어가 무의미해진다.", "",
        "## 3. 상장폐지 종목의 청산 가정",
        f"- 정리매매 가격이 관측되면 그 가격으로 청산한다. 관측 없이 사라지면 {DELIST_HAIRCUT:+.0%}",
        "  를 적용했다. 명세에 규정이 없어 보수적 값을 골랐다.", "",
        "## 4. 통제회귀의 연도더미",
        "- 매매신호용 잔차는 **과거 1년 이벤트만으로 적합**한다(PIT). 이 창 안에서는 연도더미가",
        "  거의 상수라 제외했다. 연도더미를 포함한 풀표본 적합은 미래정보가 섞이므로",
        "  이벤트스터디 기술통계에만 쓰고 매매에는 쓰지 않았다.", "",
        "## 5. 시가총액 사다리",
        "- 공공데이터포털 키가 없으면 시총이 근사(T2~T4)로 강등된다. 이 파이프라인에서 시총은",
        "  랭크·버킷으로만 쓰이므로 동작은 하지만, H4 와 하위1000 비교전략의 정확도가 낮아진다.",
        "  강등 비율은 실행 로그의 '시가총액 사다리 감사' 표에 그대로 출력된다.", "",
        "## 6. robots.txt",
        "- 한경컨센서스·네이버금융은 `Disallow: /` 다. 사용자의 명시적 지시에 따라 수집하되",
        "  보수적 속도로 제한하고 그 사실을 로그와 Phase 0 문서에 명시했다."]) + "\n"


if __name__ == "__main__":
    try:
        _RESULT = main()
    except KillCriteria as e:
        LOG.error(f"KILL 기준 위반으로 중단: {e}")
        PIPE.report_stages()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단 — 여기까지의 캐시는 드라이브에 저장되어 있습니다. "
                 "다시 실행하면 이어서 진행합니다.")
        try:
            VAULT.flush()
        except Exception:
            pass
    except Exception as _e:                                           # noqa
        LOG.error(diagnose(_e, "메인 파이프라인"))
        PIPE.report_stages()
        raise
