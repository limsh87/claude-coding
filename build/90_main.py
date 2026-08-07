

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f       # type: ignore
            for p in paths:
                print(f"⬇  다운로드 시작: {os.path.basename(p)}")
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
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 링크 대신 경로로 안내: "
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
            print(f"⬇  산출물 경로: {p}")


def collect_all(months: pd.DatetimeIndex) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스", "L1", budget_s=600):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금", "L1", budget_s=1200):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L1.FLOW", "기관·외국인 수급 (D축 d3)", "L1", budget_s=900, critical=False):
        ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(), BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시", "L1", budget_s=1800, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        fs = fetch_dart_financials(corps, years)
        fin = tidy_financials(fs)
        emp = fetch_dart_employees(corps, years)
        dis = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["fin"], ctx["emp"], ctx["disclosures"] = fin, emp, dis
        if len(fin):
            PIT.register("dart_financials", fin, key_cols=["corp_code"])
        if len(emp):
            PIT.register("dart_employees", emp, key_cols=["corp_code"])

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=3600, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되, 보수적 속도로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                nv = naver_enrich_detail(nv)
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep):
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            # ★ PDF 에서 추출한 목표주가를 원장에 실제로 반영한다.
            #   (추출만 하고 쓰지 않으면 네이버 단독 건의 목표주가가 영원히 결측으로 남는다)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건을 추가로 채웠습니다 "
                           f"(리스트에 목표주가가 없는 네이버 단독 건 보강).")
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

    for p in active_packs():
        if p.get("ingest"):
            with PIPE.stage(f"L1.PACK.{p['id']}", f"팩 {p['id']} 전용 수집", "L1",
                            budget_s=1800, critical=False):
                p["ingest"](ctx, months)
    return ctx


def build_features(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe"]:
    with PIPE.stage("L1.PANEL", "피처 패널 조립 (L1)", "L1", budget_s=1800):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel(uni, months, ctx["panel"]["monthly"])
        P = attach_fundamentals(P, ctx["sec"])
        P = build_cells(P, ctx["sec"])
        P = axis_B(P); P = axis_C(P)
        P = axis_B_tp(P); P = axis_C_tp(P)
        cons = build_consensus_panel(ctx.get("links", pd.DataFrame()), months)
        ctx["consensus"] = cons
        P = axis_D(P, ctx["panel"]["daily"], ctx.get("flows"), cons)
        P = axis_D_U(P)
        for p in active_packs():
            P = p["features"](P, ctx)
        P = downcast(P)
        LOG.ok(f"피처 패널 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        # L1/L2 분리(§3): 피처는 parquet 으로 영속화하고, 스코어부는 이 parquet 만 읽는다
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 panel")
    return P, uni


def score_and_backtest(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex,
                       uni: "Universe") -> Tuple[pd.DataFrame, dict, Callable]:
    with PIPE.stage("L2.SCORE", "거부권 + 스코어 조립 (L2)", "L2", budget_s=120):
        P = apply_vetoes(P, ctx)
        P = assemble_score(P)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        P[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR") if c in P.columns]],
                        scope="private", domain="scores", source="L2")

    def _run(pp, label="run", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else months,
                            uni, ctx["sec"], apply_costs=apply_costs, label=label)

    with PIPE.stage("L3.BT", "백테스트 (L3)", "L3", budget_s=180):
        bt = _run(P, label=STRATEGY_ID)
    return P, bt, _run


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v2 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"활성 팩: {', '.join(ACTIVE_PACKS) or '없음'} · 백테스트 {BACKTEST_START}~{BACKTEST_END} · "
               f"빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 C1~C12", "L0", budget_s=120):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(1800 if RUN_MODE == "SMOKE" else 300)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    months = month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물(백테스트·성과·강건성·해석표)을 "
               "예행연습했습니다. 실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=120, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    P, uni = build_features(ctx, months)

    with PIPE.stage("L2.POLICY", "정책 캘린더 (C12)", "L2", budget_s=60):
        cal = build_policy_calendar()
        report_policy(cal, months, [p["id"] for p in active_packs()])
        ctx["policy"] = cal

    P, bt, _run = score_and_backtest(P, ctx, months, uni)

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=120):
        bench = benchmark_returns(months)
        report_performance(bt, bench)
        uni.report_attrition()

    with PIPE.stage("L5.ROBUST", "강건성 검사 R1~R11", "L5", budget_s=4 * 3600, critical=False):
        try:
            R1_leakage(P, months, uni, ctx["sec"], _run)
            R2_tp_vs_naive(P, _run)
            R3_orthogonal(P, bt, months)
            R4_placebo(P, n_iter=1000)
            R10_policy_falsify(P, ctx["policy"], months, _run)
            R5_ablation(P, _run)
            R11_pack_corr(P)
            R6_pbo_dsr(bt)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, _run)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단 카드", "L6", budget_s=120, critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=300, critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        rp = os.path.join(outdir, f"returns_{stamp}.csv")
        bt["returns"].to_csv(rp, index=False, encoding="utf-8-sig"); outs.append(rp)
        if len(bt.get("holdings", pd.DataFrame())):
            hp = os.path.join(outdir, f"holdings_{stamp}.csv")
            bt["holdings"].to_csv(hp, index=False, encoding="utf-8-sig"); outs.append(hp)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer)); outs.append(lp)
        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.close()
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
    LOG.info("한계 명시(§16.2): 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 "
             "D축 d1 의 E 는 후행 12M 이익 대리변수를 씁니다. 초기 구간일수록 이 대리의 "
             "오차가 큽니다. 이 한계를 숨기지 않고 여기에 명시합니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_RESULTS}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§15 — 파라미터를 조정해 통과시키지 마십시오")
        print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
        try:
            report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
