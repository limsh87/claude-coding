

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — §10 실행 순서                                                            ║
# ║   [1] Phase 0 게이트 → [2] U-1000 PIT → [3] DART 수집 → [4] 정규화 → [5] D1                ║
# ║   [6] D2 → [7] D3·배제 → [8] 층 상관 진단 → [9] 리포트·TONE → [10] ΔTONE·직교화·IC          ║
# ║   [11] 인과순서 → [12] FINAL 합성 → [13] 어블레이션 11 → [14] BH-FDR·강건성 → [15] 보고     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f          # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML         # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def arc_collect(rebals: pd.DatetimeIndex) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))

    with PIPE.stage("L1.UNI", "종목 마스터 (상장·폐지 3중 확보)", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(month_range(BACKTEST_START, BACKTEST_END))
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 유동성 · PIT 시가총액", "L1", budget_s=2400):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        ctx["liq"] = build_liquidity_panel(px, rebals)
        ctx["exec"] = build_exec_prices(px, rebals)
        ctx["snap_mc"] = fetch_market_cap_snapshots(rebals)

    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시 · 주식총수 · 감사의견", "L1",
                    budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        prio: List[str] = []
        try:
            adv = (ctx["liq"].groupby("code", observed=True)["adtv60"].median()
                   .sort_values(ascending=False))
            c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
                            .set_index("code")["corp_code"].astype(str).to_dict())
            prio = [c2c[c] for c in adv.index if c in c2c]
        except Exception:
            prio = []
        multi = fetch_dart_multi_accounts(corps, years)
        fs = fetch_dart_financials(corps, years, priority=prio)
        ctx["fin"] = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["emp"] = fetch_dart_employees(corps, years)
        ctx["dis"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["shares"] = fetch_dart_shares(corps, years)
        ctx["audit"] = fetch_dart_audit(corps, years)
        if DBUDGET is not None:
            DBUDGET.report()

    with PIPE.stage("L1.DOC", "DART 정기보고서 원문 수집 + 정규화 (D1 입력)", "L1",
                    budget_s=3600, critical=False):
        n_before = 0
        try:
            n_before = int(ctx["dis"]["report_nm"].astype(str)
                           .str.contains("사업보고서|반기보고서|분기보고서", na=False).sum())
        except Exception:
            pass
        ctx["doc_attempted"] = n_before
        _T = fetch_arc_documents(ctx.get("dis"), ctx["sec"])
        arc_norm_sample_report(_T, n=5)                     # §10-[4] 육안 검증
        ctx["doc_pairs"] = arc_doc_pairs(_T)
        # ★ 게이트·D3 는 매니페스트(토큰 제외)만 있으면 된다. tf/bigram 을 통째로 들고
        #   다니면 문서 수에 비례해 상주량이 폭발하므로 여기서 떨어뜨린다.
        #   D1 은 build_d1_streaming 이 연도 샤드에서 다시 읽는다.
        _keep = [c for c in ARC_DOC_COLS if c not in ("tf", "bigram")]
        ctx["doc_tokens_full"] = _T if len(_T) < 60_000 else None
        ctx["doc_tokens"] = _T[_keep].copy() if len(_T) else _T
        _mb = mem_mb(_T)
        del _T
        gc.collect()
        LOG.info(f"문서 토큰 원본 {_mb:.0f}MB → 매니페스트만 보관 "
                 f"({mem_mb(ctx['doc_tokens']):.0f}MB). D1 은 연도 샤드에서 스트리밍합니다.")

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 · 본문", "L1",
                    budget_s=5400, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
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
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 보강")
            rep = tag_sponsored_reports(rep)
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
            VAULT.put_table(f"report_master_{STRATEGY_ID}", rep, scope="private",
                            domain="research", source="strategy view")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
        ctx["report_text"] = build_report_text_store(rep) if len(rep) else pd.DataFrame()
    return ctx


def arc_build_signals(ctx: dict, rebals: pd.DatetimeIndex, gate: dict):
    """L2 — 유니버스 → 패널 → 축 B(D1·D2·D3·배제) → 축 A(TONE·직교화) → FINAL."""
    with PIPE.stage("L2.UNI", "U-1000 PIT 유니버스 + 분기 패널", "L2", budget_s=900):
        px_monthly = (ctx["px"].assign(month=as_ts_series(ctx["px"]["date"]) +
                                       pd.offsets.MonthEnd(0))
                      .groupby(["code", "month"], observed=True)
                      .tail(1)[["code", "month", "close"]])
        mc = build_mktcap_panel(rebals, px_monthly, ctx.get("snap_mc"), ctx.get("shares"),
                                ctx["sec"])
        base = Universe(ctx["sec"], ctx.get("snapshots",
                                            pd.DataFrame(columns=["snap_date", "code", "market"])),
                        ctx["px"])
        uni = ArcUniverse(base, ctx["sec"], classify_excluded(ctx["sec"]))
        U = uni.build(rebals, mc, ctx["liq"][["code", "asof", "adtv60"]]
                      if len(ctx.get("liq", [])) else pd.DataFrame())
        P = build_arc_panel(uni, rebals, U, ctx.get("liq"), ctx.get("exec"), ctx["sec"])
        ctx["panel_base"] = P

    with PIPE.stage("L2.D1", "D1 텍스트 변화량", "L2", budget_s=1800, critical=False,
                    skip_if=(not gate.get("d1", True)),
                    skip_reason="Phase 0 GATE_4/5 실패 — D1 비활성화"):
        struct = build_struct_flags(ctx.get("dis"))
        # ★ 연도 2개씩만 올리는 스트리밍 경로. 전 구간 토큰을 한 번에 들면 수 GB 가 된다.
        d1 = build_d1_streaming(struct, T_manifest=ctx.get("doc_tokens"))
        P = attach_d1(P, d1)
    if not gate.get("d1", True):
        P = attach_d1(P, None)

    with PIPE.stage("L2.D2", "D2 재무제표 이상현상", "L2", budget_s=600, critical=False):
        P = attach_d2(P, build_d2_panel(ctx.get("fin"), ctx.get("shares"))
                      if gate.get("d2", True) else None)
        report_d2_coverage(P)

    with PIPE.stage("L2.D3", "D3 하드팩트 + 배제 플래그", "L2", budget_s=900, critical=False):
        _Td = ctx.get("doc_tokens_full")     # tf 가 있어야 텍스트 기반 이벤트를 볼 수 있다
        hard = extract_hardfacts(_Td, ctx.get("fin"), ctx.get("emp"), ctx.get("dis"))
        excl = build_exclusion_flags(ctx.get("fin"), ctx.get("dis"), ctx.get("audit"), _Td)
        if _Td is None:
            LOG.warn("문서 수가 많아 토큰 원본을 메모리에 유지하지 않았습니다 — D3 의 "
                     "텍스트 기반 이벤트(특허·정부과제·종속기업·해외거점·신규사업)는 이번 "
                     "실행에서 결측입니다. 재무·직원·수시공시 기반 이벤트는 정상 산출됩니다.")
        P = attach_d3(P, hard, excl)
        report_d3_sector(P)
        report_exclusion(P)

    with PIPE.stage("L2.FIN", "재무 결합 (직교화 통제변수용)", "L2", budget_s=300,
                    critical=False):
        if ctx.get("fin") is not None and len(ctx["fin"]):
            PIT.register("arc_fin", arc_kd_lag(ctx["fin"]), key_cols=["corp_code"])
            P = PIT.asof_join(P, "arc_fin", by="corp_code", left_time="asof",
                              cols=["corp_code", "knowledge_date", "net_income_ttm", "assets"],
                              suffix="_fin")

    with PIPE.stage("L2.A", "축 A — TONE 분류 · ΔTONE · 직교화", "L2", budget_s=5400,
                    critical=False, skip_if=(not gate.get("axis_a", True)),
                    skip_reason="Phase 0 GATE_1/2/3 실패 — DART-ONLY 폴백"):
        train = build_tone_training(ctx.get("report_text"), ctx.get("px"), ctx["sec"])
        tone_rep = score_tone_reports(ctx.get("report_text"), train, rebals)
        tone_q = aggregate_tone(tone_rep, rebals)
        rev = build_revision_panel(ctx.get("links"), rebals)
        P = attach_axis_a(P, tone_q, rev)
        ctx["tone_q"], ctx["rev"] = tone_q, rev
    if not gate.get("axis_a", True):
        P = attach_axis_a(P, None, None)

    with PIPE.stage("L2.VOL", "역변동성 가중용 변동성", "L2", budget_s=300, critical=False):
        P = attach_volatility(P, ctx.get("px"))

    with PIPE.stage("L2.SCORE", "FINAL_SCORE 합성", "L2", budget_s=300):
        axes = ["A"] if gate.get("axis_a", True) else []
        if gate.get("d1", True):
            axes.append("D1")
        if gate.get("d2", True):
            axes.append("D2")
        axes.append("D3")
        Q = assemble_final(P, use_axes=tuple(axes), use_excl=True)
        ctx["use_axes"] = tuple(axes)
        report_score_summary(Q)
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", downcast(P.copy()), scope="private",
                        domain="features", source="L2 panel")
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        Q[[c for c in ("code", "asof", "q", "DART_SCORE", "AXIS_A_Z",
                                       "FINAL_SCORE", "FINAL_RANK", "EXCLUDE")
                           if c in Q.columns]],
                        scope="private", domain="scores", source="L2")
    return Q, uni


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"ARC-TXT v2.0 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · "
               f"빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"],
               ["형태소 분석", "konlpy 사용 가능" if KONLPY_AVAILABLE else
                              ("soynlp" if soynlp_tok is not None else "규칙기반 폴백")],
               ["TONE 분류기", f"{ARC_TONE_MODEL} " +
                              ("(sklearn)" if sk_tfidf is not None else "(numpy NB 폴백)")]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "캐시 연결 (로컬 + 구글드라이브 양쪽 탐색)", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 3:
                LOG.warn("여유 공간이 3GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan([os.path.expanduser(p) for p in CACHE_SEARCH_DIRS])
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 A1~A19", "L0", budget_s=300):
        run_contract_tests(strict=STOP_ON_CONTRACT_FAIL)

    with PIPE.stage("L0.SMOKE", "합성 엔드투엔드 스모크", "L0",
                    budget_s=(3600 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설", "L0", budget_s=900):
        run_rehearsal(strict=True)

    rebals = rebal_dates(BACKTEST_START, BACKTEST_END)
    LOG.info(f"리밸런싱 시점 {len(rebals)}개 ({rebals[0]:%Y-%m-%d} ~ {rebals[-1]:%Y-%m-%d})")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = arc_collect(rebals)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (보고서↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    # ── 게이트를 위해 기본 패널을 먼저 만든다 (유니버스 코드 집합이 필요) ────────────────
    with PIPE.stage("L1.PRE", "게이트용 예비 유니버스", "L1", budget_s=600, critical=False):
        try:
            px_monthly = (ctx["px"].assign(month=as_ts_series(ctx["px"]["date"]) +
                                           pd.offsets.MonthEnd(0))
                          .groupby(["code", "month"], observed=True)
                          .tail(1)[["code", "month", "close"]])
            mc0 = build_mktcap_panel(rebals, px_monthly, ctx.get("snap_mc"),
                                     ctx.get("shares"), ctx["sec"])
            b0 = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
                columns=["snap_date", "code", "market"])), ctx["px"])
            u0 = ArcUniverse(b0, ctx["sec"], classify_excluded(ctx["sec"]))
            U0 = u0.build(rebals, mc0, ctx["liq"][["code", "asof", "adtv60"]])
            ctx["panel_base"] = U0
        except Exception as e:                                    # noqa
            LOG.warn(f"예비 유니버스 생성 실패({type(e).__name__}) — 게이트는 전 종목 기준으로 "
                     f"계산됩니다.")

    with PIPE.stage("L1.GATE", "Phase 0 게이트 6종", "L1", budget_s=300, critical=False):
        gate = run_phase0_gates(ctx, rebals)
        ctx["gate"] = gate

    P, uni = arc_build_signals(ctx, rebals, gate)

    def _run(pp, label="ARC", apply_costs=True, top_n=None, weighting=None, bottom=False):
        return run_backtest(pp, rebals, uni, ctx["sec"], apply_costs=apply_costs,
                            label=label, top_n=top_n, weighting=weighting, bottom=bottom)

    with PIPE.stage("L3.BT", "백테스트 (분기 리밸런싱)", "L3", budget_s=600):
        bt = _run(P, label=STRATEGY_ID)
        bt_iv = _run(P, label=f"{STRATEGY_ID}_invvol", weighting="invvol")

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300, critical=False):
        bench = benchmark_returns(rebals)
        ubench = equal_weight_universe_return(P)
        report_performance(bt, bench, label="동일가중(기준)", uni_bench=ubench)
        report_performance(bt_iv, bench, label="역변동성 가중(병행)", uni_bench=ubench)
        uni.report_attrition()

    with PIPE.stage("L6.DIAG", "층 상관 · D1 부호 · 축 A IC", "L6", budget_s=300,
                    critical=False):
        report_correlation_matrix(P)
        ctx["d1_sign"] = report_d1_sign_check(P)
        ctx["axis_a_ic"] = report_axis_a_ic(P)

    with PIPE.stage("L5.ABL", "어블레이션 11종 + BH-FDR", "L5", budget_s=2 * 3600,
                    critical=False):
        run_ablations(P, rebals, uni, ctx["sec"], _run)
        report_f4_vs_f1()
        ctx["fdr"] = apply_bh_fdr()

    with PIPE.stage("L5.ROBUST", "강건성 R1~R11", "L5", budget_s=2 * 3600, critical=False):
        run_robustness_suite(P, bt, rebals, uni, ctx["sec"], _run,
                             rep=ctx.get("reports"), doc=ctx.get("doc_tokens"),
                             px_daily=ctx.get("px"))

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드 · 폐기 판정", "L6", budget_s=300,
                    critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])
        ctx["kill"] = report_kill_criteria(ctx)
        report_gate_table()
        report_final_deliverables(ctx)

    with PIPE.stage("L0.PERSIST", "산출물 저장 (전용 인덱스) + 다운로드", "L0",
                    budget_s=600, critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        rp = os.path.join(outdir, f"returns_{stamp}.csv")
        bt["returns"].to_csv(rp, index=False, encoding="utf-8-sig")
        outs.append(rp)
        if len(bt.get("holdings", pd.DataFrame())):
            hp = os.path.join(outdir, f"holdings_{stamp}.csv")
            bt["holdings"].to_csv(hp, index=False, encoding="utf-8-sig")
            outs.append(hp)
        if ABLATION_RESULTS:
            ap = os.path.join(outdir, f"ablation_{stamp}.csv")
            pd.DataFrame([{"id": k, "name": v["name"], "ok": v["ok"],
                           **{f"net_{kk}": vv for kk, vv in (v.get("net") or {}).items()},
                           "ic": v.get("ic"), "icir": v.get("icir"), "p": v.get("p")}
                          for k, v in ABLATION_RESULTS.items()]).to_csv(
                ap, index=False, encoding="utf-8-sig")
            outs.append(ap)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)
        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.report(); DBUDGET.close()
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
    LOG.info("[방법론적 한계 — 숨기지 않는다] ① EPS 컨센서스 시계열은 과거 복원이 불가능하여 "
             "PIT 실적 변화율을 대리변수로 씁니다. ② 관리종목·거래정지 지정 이력은 공개 API 로 "
             "복원 불가하여 배제 플래그와 유동성 하한으로 근사합니다. ③ 특수관계자·우발부채·"
             "소송 금액 판정은 정규화 이전 원문 재파싱이 선행되어야 하며 현재 결측입니다. "
             "④ Lazy Prices 는 미국 10-K 결과이며 한국 재현은 이 백테스트의 검증 대상입니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx,
            "ablation": ABLATION_RESULTS, "robust": ROBUST_RESULTS, "gate": GATE_RESULTS}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 계약 위반/폐기 기준으로 중단", "파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
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
        except Exception:
            pass
