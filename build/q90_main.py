

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
    if not len(cal) or not len(R):
        return pd.DataFrame(columns=["code", "rebal", "mom12_1"])
    # ★ 예전엔 리밸 시점마다 merge_asof 를 2회 돌렸다 — 40시점 × 2 = 800만행 패널을 80번
    #   훑는다. 게다가 sorted(px["code"].unique()) 를 루프 안에서 매번 다시 계산했다.
    #   패널 재구축이 4회(기준 + 시프트 3회) 있으므로 320 패스가 된다.
    #   (종목 × 앵커시점) 을 한 프레임으로 쌓아 merge_asof 를 '단 2회'로 줄인다. 결과 동일.
    codes = pd.DataFrame({"code": sorted(px["code"].unique())})
    anchors = []
    for r in cal.itertuples(index=False):
        sd = as_ts(r.signal_date)
        anchors.append({"rebal": r.rebal, "p1": sd - pd.DateOffset(months=1),
                        "p12": sd - pd.DateOffset(months=12)})
    A = pd.DataFrame(anchors)
    grid = codes.merge(A, how="cross")
    vals = {}
    for k in ("p1", "p12"):
        LL = grid[["code", "rebal", k]].rename(columns={k: "t"}).sort_values("t", kind="stable")
        M = pd.merge_asof(LL, R, left_on="t", right_on="px_date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=20))
        vals[k] = M.set_index(["code", "rebal"])["close"]
    m = (vals["p1"] / vals["p12"] - 1.0).rename("mom12_1").reset_index()
    return downcast_q(m[["code", "rebal", "mom12_1"]])


def collect_core(cal_hint: Optional[pd.DataFrame] = None) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    months = month_range(as_ts(BACKTEST_START) - pd.DateOffset(months=18), BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스 입력", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    # ★★ 수집 순서를 뒤집었다: [캘린더] → [전종목 시총] → [후보 확정] → [후보만 일봉] ★★
    #   예전에는 전 종목(5,398) 일봉을 먼저 받고 나서야 하위 1000 을 골랐다. 실측 55분.
    #   시총 스냅샷은 날짜당 1~2호출로 전 종목 시총을 주므로 순서만 바꾸면 된다.
    with PIPE.stage("L1.CAL", "거래일 격자 · 분기 리밸런싱 캘린더 (§4)", "L1", budget_s=120):
        globals()["QVF_TRADING_DAYS"] = fetch_trading_calendar(BACKTEST_START, BACKTEST_END)
        ctx["cal"] = qvf_rebal_calendar_from_days(BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.CAP", "PIT 시가총액 스냅샷 (전 종목 · 날짜당 1~2호출)", "L1",
                    budget_s=900, critical=False):
        KRX.login()
        ctx["snaps_cap"] = fetch_krx_cap_snapshots(list(as_ts_series(ctx["cal"]["signal_date"])))

    with PIPE.stage("L1.PX", "가격 · 거래대금 (U-1000 후보만)", "L1", budget_s=2400):
        cand, cinfo = select_universe_candidates(ctx.get("snaps_cap"),
                                                 list(as_ts_series(ctx["cal"]["signal_date"])))
        all_codes = ctx["sec"]["code"].astype(str).tolist()
        if cand:
            ctx["candidates"] = cand
            LOG.table([["전 상장·폐지 종목", f"{len(all_codes):,}"],
                       ["신호일 평균 상장 종목", f"{cinfo.get('n_listed_avg', float('nan')):,.0f}"],
                       [f"후보 기준 K (하위 {U1000_N:,} × {CANDIDATE_BUFFER_MULT})",
                        f"{cinfo.get('K', 0):,}"],
                       ["일봉 수집 대상(후보 합집합)", f"{len(cand):,}"],
                       ["절감", f"{100*(1-len(cand)/max(1,len(all_codes))):.0f}%"],
                       ["절감의 출처", "백테스트 창 밖 폐지분 + 시총 상위 제외"]],
                      ["항목", "종목수"], ["l", "r"],
                      title="일봉 수집 대상 축소 — 시총 하위 후보만 받는다(§3.1)")
        else:
            cand = all_codes
            LOG.warn("시총 스냅샷이 없어 후보를 좁히지 못했습니다 — 전 종목 일봉을 받습니다. "
                     "(스냅샷 실패 사유를 먼저 확인하세요. 이 경로는 매우 느립니다)")
        set_code_market(ctx["sec"])
        px = fetch_prices(cand,
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        # 지수 격자에 없던 실거래일이 있으면 보강한다(지수 휴장·데이터 결손 대비).
        set_trading_days(px)
        ctx["cal"] = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.DART", "DART 재무 · 주식총수", "L1", budget_s=3600, critical=False):
        # ★★ 호출량 폭발의 진원지였다 ★★
        #   예전에는 전 상장사(폐지 포함 ~5,000)를 그대로 넘겼다. Tier-2(fnlttSinglAcntAll)는
        #   회사×연도×보고서마다 1회이므로 5,000 × 11 × 4 ≈ 220,000회 — 하루 한도가 2만이든
        #   4만이든 애초에 끝날 수 없는 설계였다. 실측으로 사용자 키가 하루 14,117회를 태웠다.
        #   가격에 적용한 '후보 먼저' 원칙을 여기에도 적용한다. 시총 하위 1000 전략이므로
        #   U-1000 후보 합집합 밖의 회사는 어느 분기에도 편입될 수 없다 = 재무가 필요 없다.
        _sec = ctx["sec"]
        _cand = set(ctx.get("candidates") or [])
        if _cand:
            _m = _sec[_sec["code"].astype(str).isin(_cand)]
            corps = _m["corp_code"].dropna().astype(str).unique().tolist()
            _all_n = _sec["corp_code"].dropna().nunique()
            LOG.table([["전 상장사 corp_code", f"{_all_n:,}"],
                       ["U-1000 후보로 축소", f"{len(corps):,}"],
                       ["절감", f"{100*(1-len(corps)/max(1,_all_n)):.0f}%"],
                       ["Tier-1 예상 호출", f"약 {math.ceil(len(corps)/100)*len(range(as_ts(BACKTEST_START).year-4, as_ts(BACKTEST_END).year+1))*(1 if DART_STATEMENT_FREQ=='annual' else 4):,}회 (100사 배치)"]],
                      headers=["DART 수집 범위", "값"],
                      title="DART 호출 범위 — 시총 하위 1000 전략이므로 후보 밖 회사는 받지 않는다")
        else:
            corps = _sec["corp_code"].dropna().astype(str).unique().tolist()
            LOG.warn(f"U-1000 후보를 못 만들어 전 상장사 {len(corps):,}개로 DART 를 받습니다 — "
                     f"호출량이 수만 회로 늘어납니다. 시총 스냅샷 단계를 먼저 확인하세요.")
        years = list(range(as_ts(BACKTEST_START).year - 4, as_ts(BACKTEST_END).year + 1))
        # ★★ priority 를 한 번도 넘기지 않고 있었다 ★★
        #   fetch_dart_financials 는 "끊겼을 때 남아 있는 것이 투자 가능한 종목의 최근
        #   데이터가 되도록" priority 순으로 받게 설계돼 있는데(12_ingest:248), 호출부가
        #   인자를 안 줘서 order={} → 정렬이 corp_code 알파벳순으로 붕괴했다. 그래서
        #   14,117 호출을 태우고도 확보된 회사가 시총 하위와 무관해 fin_cov 가 바닥이었고,
        #   §2.2 게이트가 매일 KillCriteria 로 죽였다. 호출 절감은 0이지만 '쓸모없는
        #   부분빌드'를 '쓸모있는 부분빌드'로 바꾸는 가장 값싼 한 줄이다.
        _prio = corps
        _sn = ctx.get("snaps_cap")
        if _sn is not None and len(_sn):
            _mc = (_sn.groupby("code", observed=True)["mktcap"].mean()
                     .rename("mc").reset_index())
            _mc["code"] = _mc["code"].astype(str)
            _pm = _m.merge(_mc, on="code", how="left").sort_values("mc", kind="stable")
            _prio = _pm["corp_code"].dropna().astype(str).drop_duplicates().tolist()
            LOG.info(f"DART 수집 우선순위: 시총 낮은 순 {len(_prio):,}사 — 한도로 끊겨도 "
                     f"U-1000 편입 가능성이 높은 종목부터 완성됩니다.")
        multi = fetch_dart_multi_accounts(corps, years)
        fs = fetch_dart_financials(corps, years, priority=_prio)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["fin"] = apply_t_plus_1(fin, "재무제표")
        # ★ 주식총수는 DART 로 받지 않는다. (corp × year) 마다 1호출이라 후보 2,000사 × 11년
        #   = 22,000회 — 그것 하나로 하루 한도를 태운다. 그런데 KRX 시총 스냅샷이 '상장주식수'를
        #   같은 호출에 이미 담아 준다(q21:288). 게다가 일별이라 DART 분기치보다 촘촘하고,
        #   '그 날 실제 주식수'라 정의상 PIT 이다. Q축 share_growth3y 는 이걸 쓰는 편이 낫다.
        #   DART 는 '자기주식(유동시총 보정)'에만 필요하므로, 다른 수집을 끝내고 호출이
        #   남을 때만 받는다 — 남으면 정밀도가 올라가고, 없어도 전략은 돌아간다.
        _left = DBUDGET.remaining_calls() if DBUDGET is not None else 0
        _need = len(corps) * len(years)
        if _left and _left >= _need:
            ctx["shares"] = fetch_dart_share_counts(corps, years)
        else:
            ctx["shares"] = shares_from_cap_snapshots(ctx.get("snaps_cap"), _sec)
            LOG.info(f"자기주식(DART 주식총수) 수집은 건너뜁니다 — 필요 {_need:,}회 / 잔여 "
                     f"{_left:,}회. 상장주식수는 KRX 시총 스냅샷에서 이미 확보되어 있어 "
                     f"Q축 주식수증가율({len(ctx['shares']):,}행)과 시총 계산은 그대로 동작하고, "
                     f"유동시총만 자기주식 미차감 근사가 됩니다.")
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
            # ★ 예전엔 수집기가 캐시를 아예 안 보고 매 실행 10년을 다시 훑었다(약 3시간).
            #   캐시가 확정한 지난 연도를 넘겨 그 해는 건너뛰게 한다. 올해는 항상 다시 훑는다.
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(
                    BACKTEST_START, BACKTEST_END,
                    skip_years=research_covered_years(cached, "hankyung")))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END,
                                   skip_years=research_covered_years(cached, "naver"))
                # 상세 보강은 U-1000 후보로만. 소비처(build_tp_revision)가 U-1000 패널에만
                # 붙으므로 후보 밖 종목의 목표주가는 어디에도 쓰이지 않는다.
                frames.append(naver_enrich_detail(nv, codes=ctx.get("candidates")))
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
        # ★ 캐시 루트·미러를 스캔 대상에 넣지 않는다. 그 안의 파일은 이미 인덱스에 있고,
        #   blob 은 내용해시 2단이라 드라이브 FUSE 에서 열거만 수 시간이다(실제로 여기서 멈췄다).
        #   외부에 모아둔 리포트 폴더만 스캔한다. 상대경로는 드라이브 루트 기준으로 푼다.
        _base = os.path.dirname(VAULT.root)
        adopt_dirs = [d if os.path.isabs(d) else os.path.join(_base, d)
                      for d in GDRIVE_ADOPT_DIRS]
        VAULT.adopt_scan(adopt_dirs)
        DQUOTA = DartQuota(VAULT)
        globals()["DQUOTA"] = DQUOTA
        globals()["DBUDGET"] = DQUOTA       # 공용 코어(dart_api)가 참조하는 이름에 주입
        DQUOTA.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 Q1~Q14", "L0", budget_s=180):
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
        # ★ §8.2 문언대로. X1~X3 에 3-A 가 섞이면 §10.2 의 귀속("1차=알파 / 배제·3-A=좌측꼬리")
        #   분해가 성립하지 않고, §8.3 BH-FDR 패밀리에 이질적 선정이 섞인다.
        #   X3 = "1차 + ΔNONFIN만" 이므로 배제플래그도 꺼야 한다.
        abl = [("X1", dict(stage="x1", use_rule3a=False),
                "1차만 — 깔때기 자체의 기여"),
               ("X2", dict(use_tone=False, use_nonfin=False, use_rule3a=False),
                "1차+배제플래그만 — 위험배제 효과"),
               ("X3", dict(use_tone=False, use_exclusion=False, use_rule3a=False),
                "1차+ΔNONFIN만 — 애널리스트 축 기여"),
               ("X4", dict(use_rule3a=False), "1차+2차, 3-A 없음 — 3-A 기여")]
        abl_names = []
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, best_v, label=nm, quiet=True, **kw)
            summarize_experiment(nm, b, b["panel"], best_v, fwd, desc)
            abl_names.append(nm)
        report_experiment_table(abl_names, f"보조 어블레이션 (§8.2) — 최우수 변형 {best_v} 기준")

    with PIPE.stage("L5.FDR", "[13] BH-FDR 다중검정 보정", "L5", budget_s=120, critical=False):
        # §9-C2 는 'VQF 자신의 알파'가 아니라 'VQF − VQ 차이'의 유의성을 요구한다.
        # 차이검정을 같은 패밀리에 넣어야 다중검정 보정이 정직하다.
        _c2 = paired_diff_test("VQF-full", "VQ-full")
        ctx["c2_diff"] = _c2
        ctx["fdr"] = report_bh_fdr(main_names + abl_names, extra_tests=[_c2])

    with PIPE.stage("L5.ROBUST", "[13] 강건성 검사 (§8.4)", "L5", budget_s=4 * 3600, critical=False):
        bt_best = ctx.get(f"bt_{best_v}")
        R_subperiod(bt_best, best)
        R_size_quartile(bt_best, P, best)
        R_param_sensitivity(P, cal, fwd, best_v)
        R_weight_scheme(P, cal, fwd, best_v)

        def _rebuild_shift(sh: int, variant: str):
            cal2 = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END, shift_days=sh)
            # 수급 캐시가 '옮긴 신호일'로 다시 계산되도록 시프트를 알린다. 이게 없으면
            # 캐시 키가 같아 옮기지 않은 값을 재사용하고 F축 강건성 검정이 무효가 된다.
            globals()["QVF_REBAL_SHIFT_DAYS"] = int(sh)
            try:
                fl2 = fetch_flow_netbuy(cal2, ctx["px"], window=FLOW_WINDOW_DAYS)
                P2, uni2 = build_panel_pass1(ctx, cal2, fl2)
                P2 = build_panel_pass2(P2, ctx, cal2)
                ep2 = build_exec_prices(cal2, ctx["px"])
                fwd2 = build_forward_returns(ep2, cal2, uni2.delisting_map(), ctx["px"])
                b = run_experiment(P2, cal2, fwd2, variant, label=f"shift{sh}", quiet=True)
            finally:
                globals()["QVF_REBAL_SHIFT_DAYS"] = 0
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
        report_cell_ladder()
        report_discretion_ledger()
        # ★ 폐기 판정은 마지막에 둔다. STOP_ON_KILL_CRITERIA=True 면 여기서 KillCriteria 를
        #   던져 '폐기된 전략의 최종 편입 종목표'가 출력되는 것을 막는다(§10.4 의 이행).
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
