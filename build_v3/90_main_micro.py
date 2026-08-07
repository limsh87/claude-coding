

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN — 실행 흐름                                                                         ║
# ║                                                                                          ║
# ║  [0] 환경·캐시 → 계약검정 → 합성 스모크   (실데이터 이전에 계산경로를 먼저 증명)           ║
# ║  [1] CANARY K1~K6                          (소표본 실측. FAIL 은 조치와 함께 표로)         ║
# ║  [2] 수집   (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)                          ║
# ║  [3] 패널   (PIT 유니버스 → 시총 → 재무/센서 → 셀 → 방화벽 입력)                            ║
# ║  [4] 스코어·백테스트 A/B/C/D → 성과검증                                                    ║
# ║  [5] 강건성 R0 · R2-M · R3 · R5-M · R9                                                     ║
# ║  [6] 해석표 · 진단카드 · 원장감사 · 런타임 감사 · 산출물                                    ║
# ║                                                                                          ║
# ║  모든 연산은 PIPE.stage 안에서만 돈다 → 실패하면 '어디서·무엇이·왜' 가 자동 출력된다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

OUT_DIR = "tcd_v3_micro_fw_out"


def offer_download(paths: Sequence[str]):
    ok = [p for p in paths if p and os.path.exists(p)]
    if not ok:
        return
    LOG.banner("산출물", "아래 경로에 저장되었습니다")
    LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:,.1f} KB", p] for p in ok],
              ["파일", "크기", "경로"], ["l", "r", "l"], maxw=64)
    if ENV.get("colab"):
        try:
            from google.colab import files as _f                       # type: ignore
            for p in ok:
                try:
                    _f.download(p)
                except Exception:
                    pass
        except Exception:
            LOG.info("Colab 다운로드 위젯을 쓸 수 없습니다 — 위 경로에서 직접 받으세요.")


def collect_all(months: pd.DatetimeIndex, caps: Dict[str, bool]) -> dict:
    """수집. 캐시 우선 · 부족분만 신규 · 공용 인덱스에 재적재."""
    ctx: Dict[str, Any] = {}

    with PIPE.stage("L1.SEC", "종목 마스터 (상장·폐지·업종)", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        sec = build_security_master(snaps)
        cc = fetch_dart_corpcode()
        if len(cc):
            m = cc.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["corp_code"]
            sec["corp_code"] = sec["corp_code"].where(sec["corp_code"].notna(),
                                                      sec["code"].map(m))
        ctx["sec"] = sec
        VAULT.put_table("security_master", sec, scope="shared", domain="universe",
                        source="fdr+kind+dart")
        VAULT.flush()

    with PIPE.stage("L1.PX", "가격·거래대금 (다중소스 폴백)", "L1", budget_s=2400):
        codes = ctx["sec"]["code"].dropna().astype(str).tolist()
        px = fetch_prices(codes, BACKTEST_START, BACKTEST_END)
        ctx["px_daily"] = px
        ctx["panel"] = build_price_panel(px, months)
        VAULT.flush()

    with PIPE.stage("L1.MCAP", "시가총액·상장주식수", "L1", budget_s=1200):
        snap_m = fetch_mcap_snapshots(months, ctx["sec"])
        ctx["mcap_snap"] = snap_m
        ctx["mcap"] = build_mcap_panel(ctx["panel"]["monthly"], snap_m, ctx["sec"], months)
        VAULT.flush()

    with PIPE.stage("L1.DART", "DART 재무 → 분기 센서", "L1", budget_s=3600, critical=False):
        ccs = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        yrs = sorted({int(m.year) for m in months} | {int(months[0].year) - 1})
        fs = fetch_dart_financials(ccs, yrs)
        W = tidy_financials(fs) if len(fs) else pd.DataFrame()
        Q = add_micro_sensors_quarterly(W) if len(W) else pd.DataFrame()
        ctx["fin_q"] = Q
        if len(Q):
            PIT.register("dart_micro", Q, key_cols=["corp_code"])
            VAULT.put_table(f"micro_sensors_q_{STRATEGY_ID}", Q, scope="private",
                            domain="feature", source="dart tidy + micro sensors")
        VAULT.flush()

    with PIPE.stage("L1.ACT", "관리종목·감사의견·거래정지", "L1", budget_s=1200, critical=False):
        ctx["actions"] = fetch_market_actions(BACKTEST_START, BACKTEST_END)
        VAULT.flush()

    with PIPE.stage("L1.DIS", "공시목록 (희석성 조달 V3)", "L1", budget_s=1800, critical=False):
        ctx["dis"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        VAULT.flush()

    # ★ PIPE.stage(skip_if=...) 는 '표시'만 건너뛸 뿐 with 블록의 본문은 그대로 실행된다
    #   (@contextmanager 는 본문을 건너뛸 수 없다). 부작용이 있는 단계는 반드시 밖에서
    #   진짜 if 로 막아야 한다 — 안 그러면 RESEARCH_USE=False 인데도 수집이 돌아간다.
    ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
    if RESEARCH_USE:
        _collect_research(ctx)
    else:
        LOG.info("RESEARCH_USE=False — 애널리스트 리포트 수집·사용을 전면 건너뜁니다.")
    return ctx


def _collect_research(ctx: dict):
    """애널리스트 리포트 원장. 드라이브 캐시를 최우선으로 재사용한다.

    ★ 별도 함수로 뺀 이유: PIPE.stage(skip_if=...) 는 '표시'만 건너뛸 뿐 with 블록의
      본문은 그대로 실행된다(@contextmanager 는 본문을 건너뛸 수 없다). 부작용이 있는
      단계는 반드시 호출 자체를 if 로 막아야 한다.
    """
    with PIPE.stage("L1.RSRCH", "애널리스트 리포트 (한경·네이버 + 드라이브 캐시)", "L1",
                    budget_s=2400, critical=False):
        frames = []
        cached = VAULT.get_table("research_report_master", scope="shared")
        if cached is not None and len(cached):
            LOG.ok(f"드라이브 공용 인덱스에서 리포트 원장 {len(cached):,}건 재사용 "
                   f"(이미 모아두신 캐시를 최우선으로 씁니다)")
            frames.append(cached)
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                frames.append(naver_enrich_detail(nv))
        rep = build_report_master(frames, ctx["sec"])
        if len(rep) and RESEARCH_DOWNLOAD_PDF:
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
        A, L = build_analyst_ledger(rep) if len(rep) else (pd.DataFrame(), pd.DataFrame())
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared",
                            domain="research", source="hankyung+naver")
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
        VAULT.flush()


def build_panel(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe", dict]:
    tables: Dict[str, Any] = {}
    with PIPE.stage("L1.PANEL", "패널 조립 (유니버스 → 시총 → 재무 → 셀)", "L1", budget_s=1200):
        # 상장일 결측 보강이 Universe 생성보다 반드시 먼저다 — 유니버스 멤버십의 입력이다.
        ctx["sec"] = infer_listing_dates(ctx["sec"], ctx.get("px_daily"))
        uni = Universe(ctx["sec"],
                       ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel_micro(uni, months, ctx["panel"]["monthly"])
        P = P.merge(ctx["mcap"], on=["code", "month"], how="left")
        P = attach_fundamentals_micro(P, ctx["sec"])
        P = attach_valuation(P)
        P = attach_reflection(P)
        P, attrition = apply_umicro_gates(P, uni)
        tables["attrition"] = attrition
        P = build_cells_micro(P, ctx["sec"], min_n=MICRO_MIN_CELL_N)

    with PIPE.stage("L1.FLAGS", "방화벽 입력 (관리종목·감사의견·거래정지)", "L1",
                    budget_s=600, critical=False):
        P, active = build_watchlist_panel(P, ctx.get("actions"), ctx["sec"])
        P = derive_halt_from_price(ctx.get("px_daily"), P)
        tables["fw_active"] = active

    # (skip_if 은 본문을 건너뛰지 못하므로 진짜 if 로 막는다 — 위 _collect_research 주석 참조)
    if RESEARCH_USE and len(ctx.get("links", [])):
        with PIPE.stage("L1.REV", "애널리스트 목표주가 리비전 (U층 보조)", "L1",
                        budget_s=300, critical=False):
            C = build_consensus_panel(ctx["links"], months)
            if len(C):
                P = P.merge(C[["code", "month", "d2_raw"]].rename(columns={"d2_raw": "u_revision"}),
                            on=["code", "month"], how="left")
                P["u_revision_rank"] = cell_rank_micro(P, "u_revision")
                LOG.ok(f"목표주가 리비전 결합 {int(P['u_revision'].notna().sum()):,}행")
    else:
        LOG.info("애널리스트 연결이 없어 U층 보조신호(목표주가 리비전)를 사용하지 않습니다. "
                 "E층은 리포트에 의존하지 않으므로 백테스트는 정상 진행됩니다.")

    # ★ V3(희석성 조달)의 주식수 12개월 증가율은 U-MICRO 부분집합이 아니라 '전체 패널'에서
    #   계산해야 한다. 12개월 전에 유니버스 밖이었던 종목은 부분집합에서 전 값을 못 찾아
    #   증가율이 통째로 결측이 되고, 백스톱이 무력화된다.
    tables["dis"] = ctx.get("dis")
    if "shares" in P.columns:
        _S = P[["code", "month", "shares"]].copy()
        _S["month"] = (as_ts_series(_S["month"]) + pd.DateOffset(months=12)) + pd.offsets.MonthEnd(0)
        _S = _S.rename(columns={"shares": "shares_p12"})
        P = P.merge(_S, on=["code", "month"], how="left")

    P["FW"] = 0
    P["VETO"] = 0.0
    return P, uni, tables


def score_and_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                       tables: dict) -> Tuple[pd.DataFrame, Dict[str, dict], dict, dict]:
    with PIPE.stage("L2.SCORE", "센서 가용성 → TP → 방화벽 → 거부권", "L2", budget_s=600):
        M = P[P["u_micro"].astype(bool)].copy() if "u_micro" in P.columns else P.copy()
        if len(M) < 150:
            raise KillCriteria(
                f"U-MICRO 유효 종목월이 {len(M):,}건뿐입니다(§12-6: 유효종목 150 미만). "
                f"통계 검정이 불가능하므로 중단합니다. 위 감쇠 감사표에서 어느 게이트가 "
                f"표본을 깎았는지 먼저 확인하세요.")
        active_tp, avail = sensor_availability(M)
        tables["availability"] = avail
        M = build_evidence(M, active_tp)
        fw, fwt = s1_firewall(M, tables.get("fw_active", {}))
        M["FW"] = fw
        tables["firewall"] = fwt
        M = apply_vetoes_micro(M, tables.get("dis"))
        PIPE.io("OUT", "MEM", "scored_panel", M)

    with PIPE.stage("L3.BT", "백테스트 A/B/C/D + 벤치마크", "L3", budget_s=900):
        bts: Dict[str, dict] = {}
        for v in ("A", "B", "C", "D"):
            S = assemble_signal(M, v)
            bts[v] = run_backtest_micro(S, months, uni, v, COST_BASE_SCENARIO, label=v)
            if v == "D":
                M = S          # 최종안(D)의 신호를 패널에 남긴다 — 해석표·진단카드가 이걸 읽는다
        bench_ew = benchmark_universe_ew(M, months, COST_BASE_SCENARIO, uni=uni)
        bench_idx = benchmark_index(months)
        LOG.ok(f"유니버스 동일가중 기준선 — {_fmt(bench_ew)}")
    return M, bts, bench_ew, bench_idx


def main() -> dict:
    """어떤 종료 경로(킬 기준·스테이지 실패·Ctrl-C)에서도 인덱스 저널은 남긴다."""
    try:
        return _main_inner()
    finally:
        # ★ _register() 는 메모리(_pending)에만 쌓이고 flush() 에서만 저널에 기록된다.
        #   실행 끝(L6.OUT)에만 flush 하면, 킬 기준처럼 '예상된 중단'에서 그 실행이
        #   수집한 모든 등록이 통째로 버려진다 — 파일은 드라이브에 남았는데 인덱스에는
        #   없는 상태가 되어 다음 실행이 같은 것을 다시 받는다.
        try:
            if VAULT is not None:
                VAULT.flush()
        except Exception:
            pass


def _main_inner() -> dict:
    t_start = time.time()
    LOG.banner(f"TCD v3 · {STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · 모드 {RUN_MODE}")
    months = month_range(BACKTEST_START, BACKTEST_END)
    outputs: List[str] = []
    os.makedirs(OUT_DIR, exist_ok=True)

    # ── [0] 환경 · 캐시 ──────────────────────────────────────────────────────────────
    global VAULT
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        LOG.ok(f"캐시 루트: {root}  (모드 {mode})")
        LOG.info(f"공용 인덱스 = {GDRIVE_SHARED_NS} (전 전략 공유) · "
                 f"전용 인덱스 = {GDRIVE_PRIVATE_NS} (이 전략)")
        try:
            VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        except Exception as e:                                         # noqa
            LOG.warn(f"기존 캐시 스캔 실패({type(e).__name__}) — 기존 파일은 그대로 있습니다.")
        VAULT.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=180):
        run_contracts()

    # ── [1] 합성 스모크 — 출력물 전체를 예행연습한다 ────────────────────────────────
    global _KILL_ARMED
    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        sctx = synth_context(months)
        sm = _run_pipeline_from_ctx(sctx, months, smoke=True)
        LOG.ok(f"계산 경로 통과 — 합성 CAGR {100*sm['bts']['D']['stats']['cagr']:.2f}% "
               f"(값 자체는 의미 없습니다. 경로가 끝까지 돈다는 증명입니다)")
        _KILL_ARMED = False          # 합성 데이터의 판정으로 실행을 죽이지 않는다
        try:
            _report_everything(sm, sctx, months, smoke=True)
        finally:
            _KILL_ARMED = True
        LOG.ok("스모크 통과 — 성과·강건성·해석표까지 전 출력물이 정상 생성됩니다.")

    # ★ 합성 데이터가 실행 후반으로 새지 않게 격리한다.
    #   PIT 저장소는 전역이라, 실데이터 수집이 부분 실패하면 스모크가 등록한 합성 재무가
    #   그대로 남아 '실데이터 백테스트'에 섞인다. 에러 없이 결과만 틀리는 최악의 사고다.
    _reset_state()

    if RUN_MODE == "SMOKE":
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
        LOG.ok("SMOKE 모드 완료. RUN_MODE='FULL' 로 바꾸면 실데이터로 실행합니다.")
        return {"mode": "SMOKE"}

    # ── [2] CANARY ──────────────────────────────────────────────────────────────────
    with PIPE.stage("L0.CANARY", "CANARY K1~K6", "L0", budget_s=900):
        with PIPE.stage("L0.CANARY.SEC", "종목 마스터 선취득", "L0", budget_s=600):
            snaps0 = fetch_pykrx_snapshots(months)
            sec0 = build_security_master(snaps0)
            cc0 = fetch_dart_corpcode()
            if len(cc0):
                m0 = cc0.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["corp_code"]
                sec0["corp_code"] = sec0["corp_code"].where(sec0["corp_code"].notna(),
                                                            sec0["code"].map(m0))
        caps = run_canary(sec0, months)
        p = write_canary_report(os.path.join(OUT_DIR, "canary_report.md"))
        if p:
            outputs.append(p)

    # ── [3~6] 실데이터 ──────────────────────────────────────────────────────────────
    ctx = collect_all(months, caps)
    res = _run_pipeline_from_ctx(ctx, months, smoke=False)
    P, bts, bench_ew = res["P"], res["bts"], res["bench_ew"]
    tables = res["tables"]
    abl, r9, verdict = _report_everything(res, ctx, months, smoke=False)

    # ── 산출물 ──────────────────────────────────────────────────────────────────────
    with PIPE.stage("L6.OUT", "산출물 저장 (전용 인덱스 + 로컬)", "L6", budget_s=300,
                    critical=False):
        outputs += _write_outputs(P, bts, bench_ew, tables, abl, r9, verdict)
        VAULT.put_table(f"panel_micro_{STRATEGY_ID}", downcast(P), scope="private",
                        domain="feature", source="micro-fw panel")
        for k, bt in bts.items():
            if len(bt.get("returns", [])):
                VAULT.put_table(f"backtest_{k}_{STRATEGY_ID}", bt["returns"], scope="private",
                                domain="backtest", source=f"variant {k}")
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        VAULT.report()

    PIPE.report_stages()
    PIPE.report_flow(limit=120)
    PIPE.report_runtime()
    report_http()
    KRXG.report()
    LOG.banner("완료", f"총 소요 {(time.time()-t_start)/60:.1f}분")
    offer_download(outputs)
    return {"P": P, "bts": bts, "outputs": outputs}


def _reset_state():
    """스모크(합성) → 실행(실데이터) 사이의 전역 상태 격리.

    PIT 저장소·강건성 결과·유니버스 캐시는 전역이다. 격리하지 않으면 실데이터 수집이
    부분 실패했을 때 합성 데이터가 그대로 남아 결과에 섞인다 — 에러 없이 값만 틀린다.
    """
    try:
        PIT._t.clear(); PIT._meta.clear(); PIT.access_log.clear()
    except Exception:
        pass
    ROBUST.clear()
    LOG.debug("전역 상태 초기화 완료 (PIT 저장소 · 강건성 결과) — 합성 데이터 격리")


def _report_everything(res: dict, ctx: dict, months: pd.DatetimeIndex, smoke: bool):
    """성과검증 → 강건성 → 해석표. 스모크와 실행이 '같은 출력 경로'를 탄다."""
    P, bts = res["P"], res["bts"]
    bench_ew, bench_idx, tables = res["bench_ew"], res["bench_idx"], res["tables"]
    tag = "(합성 예행연습)" if smoke else ""
    # ★ 아래 강건성 스테이지는 스모크에서 critical=False 다. 거기서 예외가 나면 스테이지가
    #   삼키고 통과하는데, 그 뒤 return 이 미할당 지역변수를 참조해 UnboundLocalError 로
    #   실행 전체를 죽인다 — 원인과 전혀 다른 곳에서 죽는 최악의 형태다. 먼저 초기화한다.
    abl, r9, verdict = None, None, ""

    with PIPE.stage(f"L6.PERF{'.S' if smoke else ''}", f"성과 검증 {tag}", "L6", budget_s=180):
        report_performance(bts, bench_ew, bench_idx)
        report_yearly(bts, bench_ew)
        report_subperiod(bts.get("D"))
        right_tail_contribution(bts.get("D"))

    with PIPE.stage(f"L5.ROBUST{'.S' if smoke else ''}",
                    f"강건성 R0·R2-M·R3·R5-M·R9 {tag}", "L5", budget_s=1800,
                    critical=not smoke):
        if smoke:
            LOG.info("합성 데이터이므로 판정은 '출력 형식 확인'용입니다 — "
                     "킬 기준을 발동시키지 않습니다(실데이터에서는 발동합니다).")
        R0_benchmark(bts, bench_ew, bench_idx)
        verdict = R2M_fourway(bts, bench_ew)
        R3_orthogonal(P, bts.get("D"), bench_ew)
        abl = R5M_ablation(P, months, res["uni"], tables.get("fw_active", {}), bts.get("D"))
        r9 = R9_cost(P, months, res["uni"])
        report_robustness()

    with PIPE.stage(f"L6.REPORT{'.S' if smoke else ''}",
                    f"해석표 · 진단카드 · 원장감사 {tag}", "L6", budget_s=300, critical=False):
        report_interpretation(P, tables.get("firewall"))
        diagnostic_card(P, bts.get("D"), ctx["sec"])
        report_ledger_integrity(ctx.get("reports"), ctx.get("analysts"), ctx.get("links"), P)
        report_dataflow_map()
    return abl, r9, verdict


def _run_pipeline_from_ctx(ctx: dict, months: pd.DatetimeIndex, smoke: bool) -> dict:
    """수집 결과(ctx)를 받아 패널→스코어→백테스트까지. 합성/실데이터가 같은 경로를 탄다."""
    if ctx.get("synthetic"):
        # 합성 ctx 는 원시 형태이므로 실데이터와 같은 정제 경로를 통과시킨다.
        # ★ 복사본을 만들면 여기서 채운 reports/analysts/links 가 호출자의 ctx 에 반영되지
        #   않아, 원장 무결성 감사표가 '리포트 없음'으로 렌더링된다. 원본을 그대로 채운다.
        ctx["px_daily"] = ctx["px"]
        ctx["panel"] = build_price_panel(ctx["px"], months)
        ctx["snapshots"] = ctx["snap"][["snap_date", "code"]].assign(market="KOSDAQ")
        ctx["snapshots"]["snap_date"] = as_ts_series(ctx["snapshots"]["snap_date"])
        ctx["mcap"] = build_mcap_panel(ctx["panel"]["monthly"], ctx["snap"], ctx["sec"], months)
        W = tidy_financials(ctx["fs"])
        Q = add_micro_sensors_quarterly(W)
        PIT.register("dart_micro", Q, key_cols=["corp_code"])
        ctx["fin_q"] = Q
        # 리포트 원장·애널리스트 원장도 실경로와 동일하게 조립한다(원장 감사표 예행연습).
        try:
            _rep = build_report_master([ctx.get("rep")], ctx["sec"])
            _A, _L = build_analyst_ledger(_rep) if len(_rep) else (pd.DataFrame(), pd.DataFrame())
            ctx["reports"], ctx["analysts"], ctx["links"] = _rep, _A, _L
        except Exception as e:                                         # noqa
            LOG.warn(f"합성 리포트 원장 조립 실패({type(e).__name__}) — 원장 감사표는 건너뜁니다.")
    P, uni, tables = build_panel(ctx, months)
    M, bts, bench_ew, bench_idx = score_and_backtest(P, months, uni, tables)
    return {"P": M, "uni": uni, "bts": bts, "bench_ew": bench_ew,
            "bench_idx": bench_idx, "tables": tables}


def _write_outputs(P, bts, bench_ew, tables, abl, r9, verdict) -> List[str]:
    made = []

    def _csv(df, name):
        if df is None or not len(df):
            return
        p = os.path.join(OUT_DIR, name)
        try:
            df.to_csv(p, index=False, encoding="utf-8-sig")
            made.append(p)
        except Exception as e:                                         # noqa
            LOG.warn(f"{name} 저장 실패({type(e).__name__})")

    _csv(tables.get("attrition"), "attrition_micro.csv")
    _csv(abl, "r5m_ablation.csv")
    _csv(r9, "r9_cost_scenarios.csv")
    _csv(tables.get("firewall"), "firewall_clauses.csv")
    _csv(tables.get("availability"), "sensor_availability.csv")

    try:
        p = os.path.join(OUT_DIR, "panel_micro.parquet")
        atomic_write_parquet(downcast(P), p)
        made.append(p)
    except Exception as e:                                             # noqa
        LOG.warn(f"패널 parquet 저장 실패({type(e).__name__})")

    try:
        js = {k: {"stats": {kk: (None if vv is None or (isinstance(vv, float) and not np.isfinite(vv))
                                 else float(vv)) for kk, vv in bt["stats"].items()},
                  "desc": VARIANTS[k]["desc"] if k in VARIANTS else bt.get("label", "")}
              for k, bt in bts.items()}
        js["BENCH_EW"] = {"stats": {kk: (None if vv is None or (isinstance(vv, float) and not np.isfinite(vv))
                                         else float(vv)) for kk, vv in bench_ew["stats"].items()},
                          "desc": "유니버스 동일가중 (자체 측정)"}
        p = os.path.join(OUT_DIR, "backtest_ABCD.json")
        atomic_write_text(p, json.dumps(js, ensure_ascii=False, indent=2))
        made.append(p)
    except Exception as e:                                             # noqa
        LOG.warn(f"backtest_ABCD.json 저장 실패({type(e).__name__})")

    try:
        p = os.path.join(OUT_DIR, "r2m_verdict.md")
        atomic_write_text(p, "# R2-M 판정 — 방화벽 알파 가설\n\n" + verdict + "\n")
        made.append(p)
    except Exception:
        pass

    try:
        rt = pd.DataFrame([{"stage": r.sid, "name": r.name, "layer": r.layer,
                            "status": r.status, "seconds": round(r.dur, 2),
                            "rows_in": r.rows_in, "rows_out": r.rows_out}
                           for r in PIPE.stages.values()])
        _csv(rt, "runtime.csv")
    except Exception:
        pass
    return made


if __name__ == "__main__":
    try:
        main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§12 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_robustness()
    except StageFailure as e:
        LOG.error(str(e))
        PIPE.report_stages()
        PIPE.report_flow(limit=60)
