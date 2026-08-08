

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  실패하면 어디서 실패했는지, 무엇이 몇 행 들어가고 나왔는지가 자동으로 출력된다              ║
# ║  (PIPE.stage 안에서만 연산이 돈다). 그것이 사용자가 요구한 '에러 국소화' 다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def scg_offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f       # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML     # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{base64.b64encode(b).decode()}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def scg_collect(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    warm_start = (as_ts(BACKTEST_START) - pd.DateOffset(years=HISTORY_WARMUP_YEARS)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 스파인 (KRX 미호출)", "L1", budget_s=1800):
        years = list(range(as_ts(warm_start).year, as_ts(BACKTEST_END).year + 1))
        #  ① 1순위: 일별 전종목시세 스파인. '그날 행이 있다 = 그날 상장돼 있었다'.
        M = scg_fetch_marcap(years)
        listing = scg_fetch_listing()
        delist = scg_fetch_delisting()
        corpcode = scg_fetch_dart_corpcode()
        if len(M):
            #  ② 스파인이 있으면 그것으로 마스터를 만들고, 상장/폐지목록으로 이름·업종만 보강한다
            sec = scg_master_from_marcap(M)
            if len(listing):
                add = listing[["code", "industry"]].drop_duplicates("code")
                sec = sec.drop(columns=["industry"]).merge(add, on="code", how="left")
                sec["industry"] = sec["industry"].fillna("")
            if len(delist):
                dl = delist[["code", "delisting_date"]].dropna().drop_duplicates("code")
                sec = sec.merge(dl.rename(columns={"delisting_date": "_dl2"}),
                                on="code", how="left")
                #  두 근거가 다르면 **이른 쪽**을 쓴다(늦게 빼면 없는 종목을 들고 있게 된다)
                sec["delisting_date"] = sec[["delisting_date", "_dl2"]].min(axis=1)
                sec = sec.drop(columns=["_dl2"])
            if len(corpcode):
                cc = corpcode.dropna(subset=["code"]).drop_duplicates("code")
                sec = sec.drop(columns=["corp_code"]).merge(
                    cc[["code", "corp_code"]], on="code", how="left")
            n0 = len(sec)
            is_common = sec["code"].str.len().eq(6) & sec["code"].str[5].eq("0")
            bad = sec["name"].astype(str).str.contains(_SCG_NONEQUITY_NAME, na=False)
            sec = sec[is_common & ~bad].copy()
            LOG.info(f"marcap 스파인 기준 종목 마스터 {n0:,} → 보통주 {len(sec):,}건 "
                     f"(우선주 {int((~is_common).sum()):,} · 스팩/ETF/리츠 {int(bad.sum()):,} 제외) · "
                     f"폐지 이력 {int(sec['delisting_date'].notna().sum()):,}건")
        else:
            LOG.warn("marcap 스파인이 없어 상장/폐지목록 기반 경로로 폴백합니다 "
                     "(정확도가 낮고 폐지목록 누락분만큼 생존자편향이 남습니다).")
            sec = scg_build_security_master(listing, delist, corpcode)
        ctx["sec"] = sec
        ctx["marcap"] = M

    with PIPE.stage("L1.PX", "가격 (FDR/네이버) · 벤치마크", "L1", budget_s=3600):
        codes = ctx["sec"]["code"].dropna().astype(str).tolist()
        px = scg_fetch_prices(codes, warm_start, BACKTEST_END)
        bench = scg_fetch_benchmark(warm_start, BACKTEST_END)
        #  거래일 캘린더는 marcap 스파인이 있으면 그것이 가장 정확하다(전종목 관측일 집합)
        M = ctx.get("marcap")
        cal = scg_build_calendar(
            M[["code", "date"]].rename(columns={"date": "date"}) if M is not None and len(M) else px,
            bench)
        sec = scg_first_trade_dates(ctx["sec"], px)
        sec = scg_infer_delisting_from_prices(sec, px, cal.values.astype("datetime64[ns]"))
        ctx.update(px=px, bench=bench, calendar=cal, sec=sec)
        ctx["signal_dates"] = scg_signal_dates(cal, SIGNAL_FREQ)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장", "L1", budget_s=7200, critical=False):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
                 "로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(warm_start, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(warm_start, BACKTEST_END)
                frames.append(naver_enrich_detail(nv))
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                     f"— 이전 전략이 모아둔 것을 그대로 씁니다")
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
        VAULT.flush("shared")
        ctx.update(reports=rep, analysts=A, links=L)

    with PIPE.stage("L1.DART", "DART 실적 실측치 · 주식총수 · 접수일", "L1",
                    budget_s=7200, critical=False):
        covered = (sorted(set(ctx["links"]["stock_code"].dropna().astype(str)))
                   if len(ctx.get("links", [])) else [])
        years = list(range(as_ts(warm_start).year - 1, as_ts(BACKTEST_END).year + 1))
        scg_report_dart_plan(len(ctx["sec"]), len(years), max(len(covered), 1))
        dis = scg_fetch_periodic_disclosures(warm_start, BACKTEST_END)
        ctx["annual_rcept"] = scg_annual_report_dates(dis)
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        multi = scg_fetch_multi_accounts(corps, years)
        tidy = scg_tidy_multi(multi)
        M = ctx.get("marcap")
        if M is not None and len(M):
            #  ★ marcap 이 그날의 상장주식수를 이미 준다 → stockTotqySttus 회사×연도 호출
            #    (약 12,000회 = 하루치 예산의 절반)이 통째로 불필요해진다.
            #    회계연도말 기준 주식수를 그 연도의 EPS 분모로 쓴다.
            m = M[["code", "date", "shares"]].dropna()
            m = m.assign(bsns_year=m["date"].dt.year)
            shares = (m.sort_values("date").groupby(["code", "bsns_year"], observed=True)
                       .agg(shares=("shares", "last"), _d=("date", "last")).reset_index())
            #  실적 발표 전에는 알 수 없으므로 knowledge_date 는 사업보고서 접수일로 둔다
            shares["knowledge_date"] = pd.to_datetime(
                shares["bsns_year"].astype(int).astype(str) + "-12-31") + pd.Timedelta(days=90)
            shares["src"] = "marcap"
            shares = shares[["code", "bsns_year", "shares", "knowledge_date", "src"]]
            LOG.ok(f"주식총수 {len(shares):,}행 (marcap 관측) — DART stockTotqySttus 호출 "
                   f"약 {len(corps)*len(years):,}회를 절약했습니다")
        else:
            shares_raw = scg_fetch_shares(ctx["sec"][["corp_code", "code"]], years,
                                          priority_codes=covered)
            shares = scg_shares_panel(shares_raw, tidy, ctx["sec"][["corp_code", "code"]])
        ctx.update(tidy_multi=tidy, shares=shares, disclosures=dis)
        if SCG_QUOTA is not None:
            SCG_QUOTA.report()

    with PIPE.stage("L1.UNADJ", "무수정 주가 · 분할보정계수", "L1", budget_s=3600,
                    critical=False):
        M = ctx.get("marcap")
        if M is not None and len(M):
            #  marcap 이 무수정 종가를 이미 준다 → yfinance 2,800종목 수집이 통째로 불필요하다.
            #  수정주가(FDR)와 나란히 놓아 adj_factor = 수정/무수정 을 그날의 두 관측값에서 얻는다.
            u = M[["code", "date", "close_unadj"]].dropna()
            j = u.merge(ctx["px"][["code", "date", "close_adj"]], on=["code", "date"], how="inner")
            j["adj_factor"] = j["close_adj"] / j["close_unadj"].replace(0, np.nan)
            j["src"] = "marcap+fdr"
            ctx["px_unadj"] = j[["code", "date", "close_unadj", "adj_factor", "src"]]
            moved = float((j["adj_factor"].sub(1).abs() > 0.01).mean()) if len(j) else np.nan
            LOG.ok(f"무수정 주가 {len(u):,}행 (marcap) · 수정/무수정 대조 {len(j):,}행 중 "
                   f"1% 초과 괴리 {100*moved:.1f}% (액면분할·유상증자 구간) — "
                   f"yfinance 수집을 건너뜁니다")
            if len(j) and not np.isfinite(moved):
                LOG.warn("분할보정계수를 계산하지 못했습니다 — 목표주가 환산이 원 단위로 남습니다.")
        else:
            ctx["px_unadj"] = scg_fetch_unadjusted(
                ctx["sec"]["code"].dropna().astype(str).tolist(), warm_start, BACKTEST_END,
                px_adj=ctx["px"])
    return ctx


def scg_build_tracks(ctx: Dict[str, Any]) -> Dict[str, Dict[str, pd.DataFrame]]:
    """메트릭 트랙별 analyst_forecasts + actuals 를 만든다 (§2.1, §3)."""
    tracks: Dict[str, Dict[str, pd.DataFrame]] = {}
    if "EPS" in FORECAST_METRICS:
        with PIPE.stage("L1.EPS", "EPS 추정치 추출 (PDF → 공용 인덱스)", "L1",
                        budget_s=7200, critical=False):
            fe = build_eps_forecasts(ctx.get("reports", pd.DataFrame()),
                                     ctx.get("links", pd.DataFrame()),
                                     ctx.get("annual_rcept"))
            ae_actuals = scg_build_eps_actuals(ctx.get("tidy_multi", pd.DataFrame()),
                                               ctx.get("shares", pd.DataFrame()),
                                               ctx["sec"][["corp_code", "code"]],
                                               ctx.get("annual_rcept") or {})
            tracks["EPS"] = {"forecasts": fe, "actuals": ae_actuals}
    if "TP" in FORECAST_METRICS:
        with PIPE.stage("L1.TP", "목표주가 트랙", "L1", budget_s=600, critical=False):
            af = None
            if len(ctx.get("px_unadj", [])):
                af = ctx["px_unadj"][["code", "date", "adj_factor"]]
            ft = build_tp_forecasts(ctx.get("links", pd.DataFrame()), af)
            tracks["TP"] = {"forecasts": ft, "actuals": None}
    return tracks


def scg_run_track(ctx: Dict[str, Any], metric: str, fc: pd.DataFrame,
                  actuals: Optional[pd.DataFrame], universe: Optional[pd.DataFrame],
                  uname: str, cfg: SCGConfig = SCG, quiet: bool = False) -> Dict[str, Any]:
    """한 (메트릭 × 유니버스) 조합의 전 과정. §44 의 인터페이스를 그대로 호출한다."""
    cal = ctx["calendar"]
    sd = ctx["signal_dates"]
    out: Dict[str, Any] = {"metric": metric, "universe": uname}
    if fc is None or fc.empty:
        return out

    #  §7~§8 Accuracy · §11~§16 Leadership — 둘 다 PIT 사건만 만든다
    if metric == "TP":
        ae = build_tp_accuracy_events(fc, ctx.get("px", pd.DataFrame()), cal, cfg)
    else:
        ae = build_accuracy_events(fc, actuals, cal, cfg)
    le = build_leadership_events(fc, cal, cfg)
    #  §9~§18 — signal date 마다 PIT 롤링 (전체기간 점수 금지)
    S = build_analyst_scores(sd, ae, le, cfg)
    #  §6, §19~§23
    act = build_active_forecasts(fc, sd, cfg)
    if universe is not None and len(universe):
        n0 = act["stock_id"].nunique()
        act = act.merge(universe.drop_duplicates(), on=["signal_date", "stock_id"], how="inner")
        if not quiet:
            LOG.info(f"[{uname}] 유니버스 적용: {n0:,} → {act['stock_id'].nunique():,}종목")
    sc, W = compute_smart_consensus(act, S, cfg)
    #  §24~§29
    sig = build_scg_signals(sc, cal, cfg)
    #  §5 — FY1(가장 가까운 미발표 회계기간)만 신호로 쓴다. FY2 는 별도 행으로 남는다.
    sig = scg_pick_primary_period(sig, metric)
    sig = scg_forward_returns(sig, ctx.get("px", pd.DataFrame()), cal, IC_HORIZONS_TD,
                              ctx.get("sec"))
    out.update(accuracy_events=ae, leadership_events=le, scores=S,
               active=act, consensus=sc, weights=W, signals=sig)
    return out


def scg_pick_primary_period(sig: pd.DataFrame, metric: str) -> pd.DataFrame:
    """§5 — 종목당 신호 1개가 되도록 '가장 가까운 미도래 회계기간'만 남긴다.

    ★ 회계기간을 섞지 않는다(§45.2). 섞는 대신 **고른다**.
      2026-03 시점에 2026-12 와 2027-12 전망이 둘 다 있으면 2026-12(FY1)를 쓴다.
      FY2 행을 지우지는 않고 primary 플래그만 세운다 — 진단에서 대조하기 위해서다.
    """
    if sig is None or sig.empty:
        return sig
    d = sig.copy()
    if metric == "TP":
        d["is_primary"] = True
        return d
    fpe = pd.to_datetime(d["fiscal_period"].astype(str) + "-01", errors="coerce") \
        + pd.offsets.MonthEnd(0)
    d["_fpe"] = fpe
    fut = d["_fpe"] >= d["signal_date"]
    d["_rank"] = np.where(fut, (d["_fpe"] - d["signal_date"]).dt.days, 10 ** 9)
    idx = d[d["status"].eq(STATUS_OK)].groupby(["signal_date", "stock_id"],
                                               observed=True)["_rank"].idxmin()
    d["is_primary"] = False
    d.loc[idx.dropna().astype(int), "is_primary"] = True
    n = int(d["is_primary"].sum())
    LOG.debug(f"FY1 선택: {len(d):,}행 중 {n:,}행을 신호로 사용 (나머지는 FY2+ 로 진단에만 사용)")
    return d.drop(columns=["_fpe", "_rank"])


def scg_persist(track: Dict[str, Any], outdir: str, tag: str) -> List[str]:
    """§33 필수 중간 출력 + §34 진단 파일. 전용 인덱스와 로컬 파일 양쪽에 남긴다."""
    outs: List[str] = []
    os.makedirs(outdir, exist_ok=True)

    def _w(df: Optional[pd.DataFrame], name: str, as_csv: bool = False):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{tag}.{'csv' if as_csv else 'parquet'}")
        try:
            if as_csv:
                df.to_csv(p, index=False, encoding="utf-8-sig")
            else:
                atomic_write_parquet(df, p)
            outs.append(p)
        except Exception as e:
            LOG.debug(f"{name} 저장 실패: {type(e).__name__}")
        VAULT.put_table(f"{name}_{tag}", df, scope="private", domain="scg", source=STRATEGY_ID)

    sig = track.get("signals")
    _w(track.get("scores"), "analyst_score_history")
    _w(track.get("weights"), "analyst_forecast_weights")
    _w(sig, "smart_consensus_daily")
    _w(scg_analyst_count_distribution(sig), "analyst_count_distribution", as_csv=True)
    _w(scg_shrinkage_diagnostics(track.get("scores")), "shrinkage_diagnostics", as_csv=True)
    _w(scg_weight_concentration(track.get("weights")), "weight_concentration", as_csv=True)
    res = track.get("res") or {}
    _w(res.get("performance"), "performance_summary", as_csv=True)
    _w(res.get("ic"), "ic_summary", as_csv=True)
    _w(res.get("monotonicity"), "monotonicity", as_csv=True)
    VAULT.flush("private")
    return outs


def main() -> dict:
    t_all = time.time()
    global VAULT, SCG_QUOTA
    LOG.banner(f"SCG-LS / SCG-LSA — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"Smart Consensus Gap + Analyst Leadership/Skill · "
               f"백테스트 {BACKTEST_START}~{BACKTEST_END} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["신호 그리드", SIGNAL_FREQ], ["메트릭 트랙", ", ".join(FORECAST_METRICS)],
               ["유니버스", ", ".join(UNIVERSE_VARIANTS)],
               ["KRX 사용", "아니오 — 호출 코드 경로 자체가 없습니다"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유")
        LOG.info(f"전용 인덱스: {VAULT.ns['private']}   ← 이 전략 고유")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간 2GB 미만 — RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        SCG_QUOTA = ScgDartQuota()
        globals()["SCG_QUOTA"] = SCG_QUOTA
        VAULT.report()

    with PIPE.stage("L0.TESTS", "자체검증 §35 TEST 1~9", "L0", budget_s=300):
        scg_run_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        sm = scg_smoke()
        scg_report_performance(sm["res"], label="SMOKE")
        scg_report_buckets(sm["res"])
        scg_report_ic(sm["res"])
        if sm["signals"].empty:
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")
        LOG.ok("스모크 통과 — 계산경로(피처→점수→백테스트→성과표)가 전부 동작합니다.")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
        return {"mode": "SMOKE", "smoke": sm}

    ctx: Dict[str, Any] = {}
    ctx = scg_collect(ctx)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=300, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    tracks = scg_build_tracks(ctx)

    with PIPE.stage("L1.LEDGER", "원장 4단 사슬 감사 (리포트→애널→종목→추정치)", "L1",
                    budget_s=300, critical=False):
        allf = pd.concat([t["forecasts"] for t in tracks.values()
                          if t.get("forecasts") is not None and len(t["forecasts"])],
                         ignore_index=True) if tracks else pd.DataFrame()
        alla = pd.concat([t["actuals"] for t in tracks.values()
                          if t.get("actuals") is not None and len(t["actuals"])],
                         ignore_index=True) if tracks else pd.DataFrame()
        scg_audit_forecast_ledger(ctx.get("reports", pd.DataFrame()),
                                  ctx.get("links", pd.DataFrame()), allf, alla)

    # ── 유니버스 변형 준비 ────────────────────────────────────────────────────────────
    with PIPE.stage("L2.UNIV", "유니버스 변형 (ALL / 시총 하위1000)", "L2", budget_s=900):
        sd = ctx["signal_dates"]
        calv = ctx["calendar"].values.astype("datetime64[ns]")
        M = ctx.get("marcap")
        if M is not None and len(M):
            base_u = scg_universe_from_marcap(M, sd, ctx["sec"])
            mcap = scg_marketcap_from_marcap(M, sd)
            mcap = mcap[mcap["stock_id"].isin(set(ctx["sec"]["code"].astype(str)))]
        else:
            base_u = scg_universe_at(ctx["sec"], sd)
            mcap = scg_build_marketcap(ctx.get("px_unadj", pd.DataFrame()),
                                       ctx.get("shares", pd.DataFrame()), sd, calv)
        adv = scg_adv_panel(ctx.get("px", pd.DataFrame()), sd)
        small = scg_small_universe(mcap, SMALL_UNIVERSE_N, adv)
        #  하위1000 은 항상 ALL 의 부분집합이어야 한다(다른 종목이 끼면 비교가 성립하지 않음)
        if len(small) and len(base_u):
            small = small.merge(base_u.drop_duplicates(), on=["signal_date", "stock_id"],
                                how="inner")
        universes = {"ALL": base_u, "SMALL1000": small}
        scg_report_universe_attrition([
            ("종목 마스터", int(ctx["sec"]["code"].nunique()), "상장+폐지 합집합"),
            ("PIT 유니버스(ALL)", int(base_u["stock_id"].nunique()) if len(base_u) else 0,
             "listing<=t<delisting"),
            ("시가총액 산출 가능", int(mcap["stock_id"].nunique()) if len(mcap) else 0,
             "무수정주가 × PIT 주식총수"),
            ("하위1000", int(small["stock_id"].nunique()) if len(small) else 0,
             f"시점별 시총 하위 {SMALL_UNIVERSE_N:,}"),
        ])
        ctx["universes"] = universes
        ctx["mcap"] = mcap

    # ── 메트릭 트랙 × 유니버스 실행 ──────────────────────────────────────────────────
    primary = PRIMARY_METRIC
    cov = {}
    results: Dict[str, Dict[str, Any]] = {}
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []
    bench_r = scg_benchmark_returns(ctx.get("bench", pd.DataFrame()), ctx["signal_dates"])
    ppy = 12.0 if SIGNAL_FREQ.upper().startswith("M") else 52.0

    for metric, t in tracks.items():
        fc = t.get("forecasts")
        if fc is None or fc.empty:
            LOG.warn(f"[{metric}] 전망 데이터가 없어 건너뜁니다.")
            continue
        for uname in UNIVERSE_VARIANTS:
            uni = ctx["universes"].get(uname)
            if uname != "ALL" and (uni is None or not len(uni)):
                LOG.warn(f"[{metric}/{uname}] 유니버스가 비어 건너뜁니다.")
                continue
            key = f"{metric}/{uname}"
            with PIPE.stage(f"L2.{metric}.{uname}", f"SCG 산출 {key}", "L2", budget_s=3600,
                            critical=False):
                tr = scg_run_track(ctx, metric, fc, t.get("actuals"), uni, uname)
                sig = tr.get("signals")
                if sig is None or sig.empty:
                    LOG.warn(f"[{key}] 신호가 비었습니다.")
                    continue
                use = sig[sig.get("is_primary", True) & sig["status"].eq(STATUS_OK)]
                tr["signals_primary"] = use
                cov[key] = int(len(use))
                tr["res"] = scg_run_all_strategies(use, SCG, bench_r, label=key)
                results[key] = tr

    if not results:
        raise RuntimeError(
            "어느 트랙에서도 신호를 만들지 못했습니다. 위의 [원장 4단 사슬 감사] 표에서 "
            "어느 고리가 끊겼는지 확인하세요 (리포트 → 애널리스트 → 종목코드 → 추정치).")

    #  ★ EPS 커버리지가 무너졌으면 공식 트랙을 TP 로 승격한다 — 단, 조용히 하지 않는다.
    #  ★ 두 트랙의 '같은 유니버스에서의' 신호 수를 직접 비교한다. 전체 합계로 나누면
    #    SMALL1000 행까지 분모에 들어가 비율이 흐려진다.
    n_eps, n_tp = cov.get("EPS/ALL", 0), cov.get("TP/ALL", 0)
    eps_share = n_eps / max(n_tp, 1) if n_tp else (1.0 if n_eps else 0.0)
    if primary == "EPS" and "TP/ALL" in results and eps_share < PRIMARY_METRIC_MIN_COVERAGE:
        LOG.warn(f"EPS 트랙의 유효 신호가 {n_eps:,}건으로 TP 트랙({n_tp:,}건) 대비 "
                 f"{100*eps_share:.1f}% 에 불과합니다 (임계 {100*PRIMARY_METRIC_MIN_COVERAGE:.0f}%). "
                 f"공식 트랙을 TP 로 승격합니다. EPS 결과도 아래에 그대로 출력하니 "
                 f"반드시 함께 읽으세요 — 조용히 바꾸지 않습니다.")
        primary = "TP"
    if f"{primary}/ALL" not in results:
        primary = list(results)[0].split("/")[0]

    # ── 보고 ─────────────────────────────────────────────────────────────────────────
    for key, tr in results.items():
        metric, uname = key.split("/")
        is_primary = (key == f"{primary}/ALL")
        with PIPE.stage(f"L6.REPORT.{metric}.{uname}", f"성과·해석 {key}", "L6",
                        budget_s=600, critical=False):
            LOG.banner(f"[{key}] {'★ 공식 트랙' if is_primary else '대조 트랙'}",
                       f"메트릭 {metric} · 유니버스 {uname}")
            scg_report_performance(tr["res"], label=key)
            scg_report_buckets(tr["res"])
            scg_report_ic(tr["res"])
            scg_report_shrinkage(tr.get("scores"))
            scg_report_weight_concentration(scg_weight_concentration(tr.get("weights")))
            scg_report_interpretation(tr["signals_primary"], tr["res"])
            scg_diagnostic_card(tr["signals_primary"], tr["res"], tr.get("scores"),
                                metric, uname)
            outs += scg_persist(tr, outdir, f"{metric}_{uname}_{stamp}")

    # ── 강건성 (공식 트랙 + 하위1000 대조) ────────────────────────────────────────────
    for key in [f"{primary}/ALL", f"{primary}/SMALL1000"]:
        if key not in results:
            continue
        tr = results[key]
        with PIPE.stage(f"L5.ROBUST.{key.replace('/', '.')}", f"강건성 {key}", "L5",
                        budget_s=4 * 3600, critical=False):
            LOG.banner(f"강건성 검사 — [{key}]", "§41 민감도는 '확인' 이지 '최적화' 가 아닙니다")
            metric, uname = key.split("/")
            t = tracks[metric]

            def _rebuild(cfg: SCGConfig, _m=metric, _t=t, _u=uname):
                rr = scg_run_track(ctx, _m, _t["forecasts"], _t.get("actuals"),
                                   ctx["universes"].get(_u), _u, cfg, quiet=True)
                s = rr.get("signals")
                if s is None or s.empty:
                    return None
                return s[s.get("is_primary", True) & s["status"].eq(STATUS_OK)]

            scg_run_robustness(tr["signals_primary"], bench_r, _rebuild, ppy,
                               do_sensitivity=(key == f"{primary}/ALL"))

    # ── 유니버스 대조표 ──────────────────────────────────────────────────────────────
    with PIPE.stage("L6.COMPARE", "유니버스·트랙 대조표", "L6", budget_s=300, critical=False):
        rows = []
        for key, tr in results.items():
            P = tr["res"].get("performance")
            if P is None or P.empty:
                continue
            for _, r in P.iterrows():
                rows.append([key, r["strategy"], f"{int(r['n_signals']):,}",
                             _p(r["annualized_return"], 1, True), _p(r["Sharpe"]),
                             _p(r["MDD"], 1, True), _p(r["hit_rate"], 1, True)])
        LOG.table(rows, ["트랙/유니버스", "전략", "신호수", "연율", "Sharpe", "MDD", "적중률"],
                  ["l", "l", "r", "r", "r", "r", "r"],
                  title="★ 전체 대조표 — 메트릭 트랙 × 유니버스 × 전략. "
                        "시총 하위1000 이 전체와 다른 답을 내면 소형주 효과가 섞인 것입니다")

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        try:
            atomic_write_text(lp, "\n".join(LOG.buffer))
            outs.append(lp)
        except Exception:
            pass
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if SCG_QUOTA:
            SCG_QUOTA.close()
            SCG_QUOTA.report()
        VAULT.report()

    PIPE.report_stages(); PIPE.report_flow(); PIT.report(); report_http(); PIPE.report_runtime()
    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시: ① EPS 추정치는 PDF 파싱에 의존하며 추출 실패가 증권사 템플릿별로 "
             "발생합니다(위의 증권사×연도 추출률 표 참조) — 그래서 TP 트랙을 함께 냅니다. "
             "② 시가총액은 무수정주가 × DART 주식총수이며, 주식총수를 못 구한 종목은 "
             "하위1000 선정에서만 빠집니다. ③ 상장폐지 종목은 포함되나 폐지 목록 자체가 "
             "불완전할 수 있어 관측기반 추정으로 보완했습니다.")
    scg_offer_download(outs)
    return {"results": results, "ctx": ctx, "primary": primary, "outputs": outs}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
            if SCG_QUOTA:
                SCG_QUOTA.close()
        except Exception:
            pass
