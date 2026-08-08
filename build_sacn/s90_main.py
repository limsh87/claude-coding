

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — SPEC §12 실행 순서                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

#  사전등록 주 구성 (SPEC §7). 결과를 본 뒤 바꾸지 않는다.
#    12개 격자 중 '기본값'을 사전에 못박아 둔다: 1개월 신호 · 월간 리밸런싱 · 비가중 링크.
#    최종 신호는 직교화 잔차(§6.3)이며, 원신호 버전을 항상 병기한다.
PRIMARY_CONFIG = {"window": "1M", "rebal": "M", "weight": "unweighted"}
PRIMARY_SIGNAL = "sacn_resid"


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in dict.fromkeys(paths) if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f          # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드: {os.path.basename(p)}")
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
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: <code>{p}</code></div>")
                continue
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{base64.b64encode(b).decode()}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.2f}MB)</a>")
        display(HTML("".join(html) + "</div>"))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물: {p}")


def _cfg_id(w: str, rb: str, wt: str) -> str:
    return f"{w}|{rb}|{wt}"


def collect_all(months: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}

    with PIPE.stage("L1.UNI", "종목 마스터 (상장·폐지 이력 포함)", "L1", budget_s=900):
        KRX.login()
        snaps = fetch_pykrx_snapshots(months)
        if snaps is None or len(snaps) == 0:
            # pykrx 가 없으면 위 경로는 통째로 건너뛴다(설계상 정상). 다만 그러면
            # 생존자편향을 교차검증할 PIT 스냅샷이 사라지므로, KRX 벌크로 복원한다.
            snaps = krx_listing_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "일별 가격 · 거래대금", "L1", budget_s=2400):
        start = (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d")
        # ★ 받아야 하는 것만 받는다. 우선주·ETF·ETN·ELW·스팩·KONEX 와 구간 밖 종목은
        #   §5 에서 어차피 전부 제외되므로 가격을 요청할 이유가 없다. 실측에서 이 부류가
        #   '전 소스 실패 1,901종목'의 큰 덩어리였다 — 받지 못할 것을 받으려다 4개 소스를
        #   전부 헛돌린 것이다. (상장폐지 종목은 반드시 남긴다 — 생존자편향)
        px_codes, px_audit = price_target_codes(ctx["sec"])
        LOG.table(px_audit.values.tolist(), list(px_audit.columns), ["l", "r"],
                  title="가격 수집 대상 축소 (§5 에서 탈락이 확정된 종목은 요청하지 않음)")
        px = fetch_prices(px_codes, start, BACKTEST_END, sec=ctx["sec"])
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L1.META", "시가총액 · BM · 제외플래그 · 업종", "L1", budget_s=1800):
        ctx["mcap"] = fetch_mktcap_monthly(months, panel=ctx["panel"]["monthly"])
        fund = fetch_fundamental_monthly(months)
        ctx["nonequity"] = fetch_nonequity_tickers(months)
        ctx["flags"] = build_exclusion_flags(ctx["sec"], ctx["nonequity"])
        ctx["sector"] = build_sector_map(ctx["sec"])
        ctx["fund"] = attach_bm_fallback(fund, ctx["mcap"], ctx["sec"], months)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=7200, critical=False):
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
                nv = naver_enrich_detail(nv)
                nv = naver_attach_analyst(nv)         # ★ 버려지던 바이라인 회수
                frames.append(nv)
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
            rep = apply_publication_lag(rep)          # §0.1 익영업일 보수화
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
    return ctx


def main() -> dict:
    t_all = time.time()
    global VAULT, DQ, GDRIVE_ROOT, ADOPT_DIRS_RESOLVED
    # ★ 가장 먼저 서드파티 수다를 끈다. 주피터는 초당 메시지 수가 제한돼 있어서,
    #   yfinance/pymupdf 가 뱉는 수천 줄이 IOPub 한도를 넘기면 출력이 통째로 멈춘다.
    #   사용자는 그걸 '멈춤'으로 읽고 커널을 죽인다 — 몇 시간이 그렇게 날아간다.
    silence_thirdparty()
    LOG.banner(f"ARC-SACN — {STRATEGY_NAME}",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(폴백)")],
               ["시드", str(SEED)], ["사전등록 구성 수", f"{N_PREREG_CONFIGS}개 (확장 금지)"],
               ["주 구성", f"{PRIMARY_CONFIG['window']} 신호 · "
                           f"{PRIMARY_CONFIG['rebal']} 리밸 · {PRIMARY_CONFIG['weight']} 링크"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.ROOT", "프로젝트 루트 결정 · 캐시 연결", "L0", budget_s=300):
        root, mode, adopts = resolve_project_root()
        GDRIVE_ROOT = root
        globals()["GDRIVE_ROOT"] = root
        ADOPT_DIRS_RESOLVED = adopts
        globals()["ADOPT_DIRS_RESOLVED"] = adopts
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.table([["캐시 루트", VAULT.root], ["결정 방식", mode],
                   ["공용 인덱스", f"{GDRIVE_SHARED_NS}  (다른 전략과 공유·재사용)"],
                   ["전용 인덱스", f"{GDRIVE_PRIVATE_NS}  (이 전략 고유)"],
                   ["기존 캐시 스캔 대상", f"{len(adopts)}개 경로" +
                    (f"  ({adopts[0]})" if adopts else "")],
                   ["여유 공간", f"{free_gb_safe(VAULT.root):.1f} GB"]],
                  ["항목", "값"], ["l", "l"], title="구글드라이브 캐시")
        if mode.endswith("_CREATED") and not mode.startswith(("LOCAL", "FALLBACK")):
            LOG.warn(f"캐시 루트를 새로 만들었습니다({mode}) — 기존 캐시를 물려받지 "
                     f"못했다는 뜻입니다. 경로 오타이거나 드라이브가 아직 동기화되지 "
                     f"않았을 수 있습니다. 이대로 진행하면 전부 재수집합니다.")
        if mode.startswith(("LOCAL", "FALLBACK")):
            LOG.warn(
                "구글드라이브를 찾지 못해 로컬 경로를 씁니다. 기존 드라이브 캐시를 한 건도 "
                "재사용하지 못하는 상태이며, 이번 실행의 수집물도 드라이브가 아니라 이 PC 에만 "
                "남습니다.\n"
                "  → 해결: 코드 상단 GDRIVE_ROOT 에 드라이브 폴더 경로를 그대로 붙여넣으세요.\n"
                "     윈도우 예:  GDRIVE_ROOT = r\"G:\\내 드라이브\\tcd_cache\"\n"
                "     코랩 예:    GDRIVE_ROOT = \"/content/drive/MyDrive/tcd_cache\"\n"
                "     (탐색기 주소창에 보이는 경로를 그대로 복사하면 됩니다)")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(adopts)
        DQ = DartQuota(DART_API_KEY, scope="shared")
        globals()["DQ"] = DQ
        DQ.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 K1~K21", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        if not run_selftest(full=True):
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설", "L0", budget_s=300, critical=False):
        run_rehearsal(strict=False)

    months = sacn_month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 계산경로를 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (리포트 ↔ 애널 ↔ 종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    with PIPE.stage("L1.PHASE0", "PHASE 0 데이터 실현가능성 게이트", "L1", budget_s=600):
        ph = phase0_gate(ctx.get("reports", pd.DataFrame()), ctx.get("links", pd.DataFrame()),
                         t_all)
        ctx["phase0"] = ph
        write_phase0_md(ph)
        if ph.get("need_ipw"):
            ctx["ipw"] = missingness_sensitivity(ctx.get("reports", pd.DataFrame()),
                                                 ctx.get("links", pd.DataFrame()), ctx["mcap"])
        ctx["ledger"] = build_link_ledger(ctx.get("reports", pd.DataFrame()),
                                          ctx.get("links", pd.DataFrame()),
                                          ctx["sec"], unit=ph["unit"])
    if RUN_MODE == "PHASE0":
        LOG.banner("PHASE 0 완료 — 승인 대기", "SPEC §12-1: 여기서 보고 후 중단합니다.")
        write_open_questions_md()
        PIPE.report_stages()
        offer_download(OUTPUTS)
        return {"mode": "PHASE0", "phase0": ph, "outputs": OUTPUTS}
    if ctx["ledger"] is None or not len(ctx["ledger"]):
        raise RuntimeError("링크 원장이 비어 있어 전략을 구성할 수 없습니다. "
                           "PHASE0_DATA_FEASIBILITY.md 를 확인하세요.")

    with PIPE.stage("L2.UNIVERSE", "PIT 유니버스 120개월", "L2", budget_s=900):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
            columns=["snap_date", "code", "market"])), ctx["panel"]["daily"])
        SU = SACNUniverse()
        U = SU.build(uni, months, ctx["panel"]["monthly"], ctx["mcap"], ctx["flags"],
                     ctx["sector"], ctx["fund"])
        SU.report()
        ctx["uni_panel"], ctx["SU"] = U, SU
        ctx["delist"] = SU.delisting_returns(uni, months, ctx["panel"]["daily"])
        if not len(U):
            raise RuntimeError("PIT 유니버스가 비었습니다 — 게이트 감쇠표에서 붕괴 지점을 확인하세요.")

    with PIPE.stage("L2.LINK", "링크 행렬 (3가지 가중) + 애널리스트 스킬", "L2", budget_s=2400):
        codes = sorted(U["code"].astype(str).unique())
        ctx["skill"] = build_analyst_skill(ctx["ledger"], ctx["panel"]["monthly"],
                                           months, ctx["sector"])
        LMs = {wt: build_link_matrices(ctx["ledger"], months, codes, wt, skill=ctx["skill"])
               for wt in PREREG_LINK_WEIGHTS}
        ctx["LMs"] = LMs
        ctx["LM_xsec"] = mask_cross_sector(LMs["unweighted"], ctx["sector"])

    with PIPE.stage("L2.SIGNAL", f"신호 {N_PREREG_CONFIGS}개 구성", "L2", budget_s=1800):
        grid = PriceGrid(ctx["panel"]["daily"])
        ctx["grid"] = grid
        panels: Dict[str, pd.DataFrame] = {}
        for wt in PREREG_LINK_WEIGHTS:
            for w in PREREG_SIGNAL_WINDOWS:
                for rb in PREREG_REBALANCES:
                    cid = _cfg_id(w, rb, wt)
                    P = build_signal_panel(LMs[wt], grid, U, months, w, rb)
                    if P is None or not len(P):
                        LOG.warn(f"구성 {cid}: 신호 패널이 비었습니다 — 건너뜁니다.")
                        continue
                    panels[cid] = attach_attrs(P, U, grid)
        ctx["panels"] = panels
        if not panels:
            raise RuntimeError("어떤 구성에서도 신호가 만들어지지 않았습니다.")
        LOG.ok(f"신호 패널 {len(panels)}/{N_PREREG_CONFIGS}개 구성 생성")
        _pid = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"],
                       PRIMARY_CONFIG["weight"])
        if _pid in panels:
            VAULT.put_table(f"signal_panel_primary_{STRATEGY_ID}", panels[_pid],
                            scope="private", domain="features", source=f"SACN {_pid}")

    pid = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], PRIMARY_CONFIG["weight"])
    if pid not in ctx["panels"]:
        pid = sorted(ctx["panels"])[0]
        LOG.warn(f"사전등록 주 구성을 만들 수 없어 {pid} 로 대체합니다 (그 사실을 산출물에 남깁니다).")
        open_question("OQ-06", "주 구성 대체",
                      f"사전등록 주 구성을 생성할 수 없었다.", f"{pid} 로 대체.",
                      "주 구성 결과 해석 시 이 대체를 감안해야 한다.")
    ctx["primary_id"] = pid
    P0 = ctx["panels"][pid]
    ppy = PERIODS_PER_YEAR.get(PRIMARY_CONFIG["rebal"], 12.0)

    with PIPE.stage("L3.BT", f"백테스트 {len(ctx['panels'])}구성 × 2아암", "L3", budget_s=1800):
        arms = {"전체 유니버스": P0}
        if COMPARE_SMALLCAP_ARM:
            arms["시총하위1000"] = smallcap_subset(P0, SMALLCAP_ARM_N)
        ctx["arm_bt"] = {}
        for an, Pa in arms.items():
            ctx["arm_bt"][an] = run_quantile_backtest(
                Pa, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"], delist=ctx["delist"],
                cost_mult=COST_SCENARIOS["base"], label=an)
        # 12개 구성 전체 (PBO/DSR/WF 의 입력)
        allbt: Dict[str, dict] = {}
        for cid, Pc in ctx["panels"].items():
            rb = cid.split("|")[1]
            allbt[cid] = run_quantile_backtest(Pc, PRIMARY_SIGNAL, rb, delist=ctx["delist"],
                                               cost_mult=1.0, label=cid)
        ctx["allbt"] = allbt

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300):
        bench = index_benchmarks(ctx["arm_bt"]["전체 유니버스"]["returns"]["date"].tolist())
        bench["동일가중 유니버스"] = equal_weight_universe(
            ctx["grid"], U, rebalance_dates(months, ctx["grid"], PRIMARY_CONFIG["rebal"]))
        ctx["bench"] = bench
        tax_schedule_table()
        for an, bt in ctx["arm_bt"].items():
            report_performance(bt, bench, title=f"{an} · {pid} · {PRIMARY_SIGNAL}")
            report_quantile_profile(ctx["panels"][pid] if an == "전체 유니버스"
                                    else smallcap_subset(P0, SMALLCAP_ARM_N),
                                    PRIMARY_SIGNAL, title=an)
        report_arm_comparison(ctx["arm_bt"], ppy)
        # 원신호 vs 직교화 병기 (§6.3)
        bt_raw = run_quantile_backtest(P0, "sacn_raw", PRIMARY_CONFIG["rebal"],
                                       delist=ctx["delist"], label="원신호")
        ctx["bt_raw"] = bt_raw
        report_arm_comparison({"직교화(주)": ctx["arm_bt"]["전체 유니버스"], "원신호": bt_raw}, ppy)

    # ★ rob 을 스테이지 밖에서 먼저 채워둔다. L5.STATS 는 critical=False 라 실패해도
    #   진행되는데, 그때 ctx["rob"] 이 없으면 하류가 KeyError 로 조용히 죽고
    #   '수 시간 수집 후 산출물 0개'가 된다.
    ctx["rob"] = {"bootstrap": {}, "pbo": {}, "dsr": {}, "wf": {}}
    with PIPE.stage("L5.STATS", "통계 검증 게이트 (§9)", "L5", budget_s=1500, critical=False):
        base = ctx["arm_bt"]["전체 유니버스"]
        r = base["returns"]["ret"].to_numpy(float) if len(base["returns"]) else np.array([])
        # ★ 주간·월간 구성을 한 행렬에 섞으면 안 된다. 날짜 격자가 달라 dropna(how="any")
        #   후 교집합(월말∩주말)만 남고, 그 한 행 안에서 '1주 수익'과 '1개월 수익'이
        #   나란히 비교된다. PBO 는 실력이 아니라 리밸런싱 주기를 고르게 되고,
        #   워크포워드는 표본 부족으로 아예 실행되지 않는다.
        mats: Dict[str, pd.DataFrame] = {}
        for cid, bt in ctx["allbt"].items():
            R = bt.get("returns")
            if R is None or not len(R):
                continue
            mats.setdefault(cid.split("|")[1], {})[cid] = \
                R.set_index(as_ts_series(R["date"]))["ret"]
        mats = {rb: pd.DataFrame(c).sort_index() for rb, c in mats.items()}
        M = mats.get(PRIMARY_CONFIG["rebal"], pd.DataFrame())
        # DSR 의 시도 횟수는 12(사전등록 전체)로 유지하되, 시도 간 Sharpe 분산이
        # 있으면 그것을 쓴다 (귀무 하 표집분산보다 정확하고 덜 관대하다).
        srv = None
        if len(M.columns) > 2:
            _s = (M.mean() / M.std(ddof=1)).replace([np.inf, -np.inf], np.nan).dropna()
            srv = float(_s.var(ddof=1)) if len(_s) > 2 else None
        rob = {"bootstrap": block_bootstrap(r, ppy=ppy),
               "pbo": cscv_pbo(M, S=8),
               "pbo_by_rebal": {rb: cscv_pbo(m, S=8) for rb, m in mats.items()},
               "dsr": deflated_sharpe(r, n_trials=N_PREREG_CONFIGS, ppy=ppy, sr_variance=srv),
               "wf": walk_forward(M, ppy=ppy)}
        ctx["rob"] = rob
        LOG.info(f"통계 검증 행렬: 리밸런싱 주기별 분리 — "
                 f"{', '.join(f'{k}:{v.shape[1]}구성×{v.shape[0]}기간' for k, v in mats.items())} "
                 f"(주 구성 주기 '{PRIMARY_CONFIG['rebal']}' 기준으로 §11 판정)")
        report_robustness(rob, title=f"{pid} · 전체 유니버스")

    with PIPE.stage("L5.HYP", "사전등록 가설 H1~H4 (§3)", "L5", budget_s=900, critical=False):
        sp_full = test_H1(P0, PRIMARY_SIGNAL, ppy)
        Px = build_signal_panel(ctx["LM_xsec"], ctx["grid"], U, months,
                                PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"])
        if Px is not None and len(Px):
            Px = attach_attrs(Px, U, ctx["grid"])
            sp_x = spread_series(Px, PRIMARY_SIGNAL)
        else:
            sp_x = pd.Series(dtype=float)
        test_H2(sp_full, sp_x, ppy)
        # ★ 수집은 L1 에서 끝났어야 한다. 여기(critical=False 스테이지) 에서 네트워크를
        #   때리면, 그 한 번의 실패로 이미 계산된 H1·H2 결과와 ctx["hyp_table"] 까지
        #   통째로 버려진다. 예외가 나도 가설검정은 계속되도록 감싼다.
        try:
            ctx["retail"] = fetch_retail_share(
                sorted(U["code"].astype(str).unique()), BACKTEST_START, BACKTEST_END) \
                if RUN_MODE == "FULL" else pd.DataFrame()
        except Exception as e:                                    # noqa
            LOG.warn(f"개인 거래비중 수집 실패({type(e).__name__}) — H3 는 소형주·저커버리지 "
                     f"축으로만 판정합니다. 나머지 가설검정은 그대로 진행합니다.")
            ctx["retail"] = pd.DataFrame()
        T3 = test_H3(P0, PRIMARY_SIGNAL, ppy, ctx.get("retail"))
        cid_f = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], "freq")
        cid_s = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], "highskill")
        test_H4(sp_full,
                spread_series(ctx["panels"][cid_f], PRIMARY_SIGNAL) if cid_f in ctx["panels"]
                else pd.Series(dtype=float),
                ppy,
                spread_series(ctx["panels"][cid_s], PRIMARY_SIGNAL) if cid_s in ctx["panels"]
                else None)
        F = finalize_hypotheses(q=0.10)
        ctx["hyp_table"], ctx["mech_table"] = F, T3

    with PIPE.stage("L5.SENS", "비용 · 폐지 민감도", "L5", budget_s=600, critical=False):
        scen = {name: run_quantile_backtest(P0, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"],
                                            delist=ctx["delist"], cost_mult=mult,
                                            label=f"cost:{name}")
                for name, mult in COST_SCENARIOS.items()}
        ctx["cost_scen"] = scen
        ctx["cost_table"] = report_cost_sensitivity(scen, ppy)
        drows = []
        for g in DELIST_SENSITIVITY_GRID:
            dl = ctx["delist"].copy()
            if len(dl):
                m = dl["source"] != "정리매매 최종가"
                dl.loc[m, "delist_ret"] = g
            b = run_quantile_backtest(P0, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"],
                                      delist=dl, label=f"delist:{g}")
            st = perf_stats(b["returns"], ppy=ppy)
            drows.append([f"{g:.0%}", _fmt_metric("CAGR", st.get("CAGR")),
                          _fmt_metric("Sharpe", st.get("Sharpe")),
                          _fmt_metric("MDD", st.get("MDD")),
                          f"{int((dl['source'] != '정리매매 최종가').sum()) if len(dl) else 0}"])
        ctx["delist_table"] = drows
        report_delist_sensitivity(drows)

    with PIPE.stage("L6.INTERP", "해석표", "L6", budget_s=300, critical=False):
        report_interpretation(P0, PRIMARY_SIGNAL, ctx["LMs"][PRIMARY_CONFIG["weight"]],
                              ctx["arm_bt"]["전체 유니버스"], ctx["sec"])

    with PIPE.stage("L6.VERDICT", "§11 기계적 판정", "L6", budget_s=300, critical=False):
        v = final_verdict(ctx["arm_bt"]["전체 유니버스"], ctx["bench"].get("동일가중 유니버스"),
                          ctx["rob"].get("pbo", {}), ctx["rob"].get("dsr", {}), ppy)
        ctx["verdict"] = v
    ctx.setdefault("verdict", {"verdict": "NOT_EVALUABLE", "why": "판정 단계 실패",
                               "criteria": [], "excess_ew": float("nan"),
                               "pbo": float("nan"), "dsr": float("nan")})

    # 산출물은 판정과 분리한다. 판정이 실패해도 몇 시간짜리 수집 결과는 반드시 남겨야 한다.
    with PIPE.stage("L6.OUTPUT", "산출물 생성 (§10)", "L6", budget_s=600, critical=False):
        write_outputs(ctx, ppy, t_all)

    PIPE.report_stages()
    PIPE.report_flow(limit=120)
    PIT.report()
    report_http()
    if DQ:
        DQ.report()
        DQ.close()
    PIPE.report_runtime()
    VAULT.flush()
    VAULT.compact("shared")
    VAULT.compact("private")
    VAULT.report()
    # ★ 절대원칙 점검 — 이번 실행이 새로 받은 것이 전부 드라이브에 남았는지 기계적으로 확인
    report_cache_ledger()
    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물 {len(OUTPUTS)}개 · 캐시 {VAULT.root}")
    offer_download(OUTPUTS)
    return {"ctx": ctx, "verdict": ctx.get("verdict"), "outputs": OUTPUTS}


def _write_cache_evidence() -> None:
    """절대원칙 증빙 — 매니페스트와 원장. 다른 산출물과 독립적으로, 먼저 쓴다."""
    try:
        man = cache_manifest()
        write_text("cache_manifest.json",
                   json.dumps(man, ensure_ascii=False, indent=2, default=str))
        led, _viol = cache_audit()
        write_df("cache_ledger.csv", led)
        if man.get("datasets"):
            LOG.table([[d["scope"], d["name"], f"{d['rows']:,}"]
                       for d in sorted(man["datasets"], key=lambda x: -x["rows"])[:20]],
                      ["인덱스", "데이터셋", "행수"], ["l", "l", "r"],
                      title="드라이브 캐시 매니페스트 (cache_manifest.json — 다음 세션 재호출용)")
    except Exception as e:                                        # noqa
        LOG.error(f"캐시 증빙 산출 실패({type(e).__name__}: {e}) — "
                  f"드라이브에 무엇이 남았는지 파일로 증명할 수 없습니다.")


def _emergency_flush() -> None:
    """중단·예외 시에도 인덱스를 반드시 커밋한다. 안 하면 이번 실행의 저장분을 잃는다."""
    V = globals().get("VAULT")
    if V is None:
        return
    try:
        V.flush()
        LOG.ok(f"인덱스 커밋 완료 — 여기까지 받은 데이터는 {V.root} 에서 재호출 가능합니다.")
    except Exception as e:                                        # noqa
        _safe_print(f"[경고] 인덱스 커밋 실패({type(e).__name__}) — 다음 실행에서 "
                    f"일부 데이터를 다시 받게 됩니다.")


def write_outputs(ctx: dict, ppy: float, t_all: float):
    """SPEC §10 산출물 일체.

    ★ 캐시 증빙(cache_manifest.json / cache_ledger.csv)을 '맨 먼저' 쓴다.
      맨 뒤에 두면, 그 앞 어딘가의 KeyError 하나로 절대원칙 증빙이 통째로 사라지면서
      report_cache_ledger() 는 여전히 '통과'를 출력한다 — 증빙 없는 초록불이 된다.
    """
    _write_cache_evidence()
    rows = []
    for cid, bt in ctx["allbt"].items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        w, rb, wt = cid.split("|")
        st = perf_stats(R, ppy=PERIODS_PER_YEAR.get(rb, 12.0))
        rows.append({"config": cid, "signal_window": w, "rebalance": rb, "link_weight": wt,
                     "is_primary": cid == ctx["primary_id"],
                     **{k: st.get(k) for k in _METRIC_ORDER if k in st}})
    MC = pd.DataFrame(rows)
    write_df("metrics_all_configs.csv", MC)
    if len(MC):
        LOG.table([[r["config"] + (" ★" if r["is_primary"] else ""),
                    _fmt_metric("CAGR", r.get("CAGR")), _fmt_metric("Sharpe", r.get("Sharpe")),
                    _fmt_metric("MDD", r.get("MDD")),
                    _fmt_metric("t통계량(HAC)", r.get("t통계량(HAC)"))]
                   for _, r in MC.iterrows()],
                  ["구성 (신호|리밸|가중)", "CAGR", "Sharpe", "MDD", "t(HAC)"],
                  ["l", "r", "r", "r", "r"],
                  title=f"사전등록 {N_PREREG_CONFIGS}개 구성 전체 성과 (★=사전등록 주 구성)")

    eq = []
    for cid, bt in ctx["allbt"].items():
        R = bt.get("returns", pd.DataFrame())
        if len(R):
            e = R[["date", "ret", "equity"]].copy()
            e["config"] = cid
            eq.append(e)
    write_df("equity_curves.parquet", pd.concat(eq, ignore_index=True) if eq else pd.DataFrame())
    H = ctx["arm_bt"]["전체 유니버스"].get("holdings", pd.DataFrame())
    write_df("trade_log.parquet", H)

    write_hypothesis_md(ctx.get("hyp_table", pd.DataFrame()), ctx["rob"])
    write_mechanism_md(ctx.get("mech_table", pd.DataFrame()), ctx["arm_bt"], ppy)
    write_text("cost_sensitivity.md", "# 비용 민감도 (§7.1)\n\n"
               "증권거래세는 2019년 이후 여러 차례 인하됐다. 단일 세율을 쓰지 않고 "
               "연도별 실제 세율 테이블을 적용했다.\n\n"
               + _md_table(ctx.get("cost_table", pd.DataFrame())) + "\n\n## 연도별 세율\n\n"
               + _md_table(pd.DataFrame([{"적용시작": d, "유가증권": f"{t['KOSPI']:.3%}",
                                          "코스닥": f"{t['KOSDAQ']:.3%}"}
                                         for d, t in SELL_TAX_SCHEDULE])))
    write_text("delisting_sensitivity.md", "# 상장폐지 처리 민감도 (§0.3)\n\n"
               "폐지 종목의 최종 수익률은 -100% 일괄이 아니라 정리매매 최종가 기준으로 "
               "처리했다. 최종가를 확인할 수 없는 건에만 보수적 기본값을 적용하고, "
               "그 가정의 민감도를 아래에 병기한다.\n\n"
               + _md_table(pd.DataFrame(ctx.get("delist_table", []),
                                        columns=["가정", "CAGR", "Sharpe", "MDD", "영향 종목수"])))
    write_open_questions_md()
    write_verdict_md(ctx["verdict"], ctx["arm_bt"], ppy)

    summary = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "run_mode": RUN_MODE, "started": _dt.datetime.now().isoformat(timespec="seconds"),
        "elapsed_min": round((time.time() - t_all) / 60.0, 2),
        "backtest": {"start": BACKTEST_START, "end": BACKTEST_END,
                     "months": int(len(sacn_month_range(BACKTEST_START, BACKTEST_END)))},
        "phase0": {k: (v if isinstance(v, (int, float, str, bool)) else str(type(v)))
                   for k, v in (ctx.get("phase0") or {}).items() if k != "detail"},
        "primary_config": ctx.get("primary_id"), "primary_signal": PRIMARY_SIGNAL,
        "n_configs_built": len(ctx.get("panels", {})), "n_configs_preregistered": N_PREREG_CONFIGS,
        "universe_months": int(ctx["uni_panel"]["month"].nunique()) if len(ctx.get("uni_panel", [])) else 0,
        "universe_avg_names": float(ctx["uni_panel"].groupby("month").size().mean())
        if len(ctx.get("uni_panel", [])) else 0.0,
        "link_ledger_rows": int(len(ctx.get("ledger", []))),
        "analyst_keys": int(ctx["ledger"]["analyst_key"].nunique()) if len(ctx.get("ledger", [])) else 0,
        "verdict": (ctx.get("verdict") or {}).get("verdict"),
        "hypotheses": {k: {"pass": h.get("pass"), "final": h.get("final"),
                           "stat": h.get("stat"), "p": h.get("p")} for k, h in HYP.items()},
        "robustness": {k: {kk: vv for kk, vv in (v or {}).items()
                           if isinstance(vv, (int, float, str, bool))}
                       for k, v in ctx.get("rob", {}).items()},
        "dart_quota": {"used": DQ.used if DQ else 0, "remaining": DQ.remaining() if DQ else 0,
                       "limit": DQ.limit if DQ else 0,
                       "limit_observed": DQ.limit_is_observed() if DQ else False},
        "cache_root": VAULT.root, "shared_ns": GDRIVE_SHARED_NS, "private_ns": GDRIVE_PRIVATE_NS,
        "open_questions": len(OPEN_QUESTIONS),
    }
    write_text("run_summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    write_text(f"run_log_{_dt.datetime.now():%Y%m%d_%H%M%S}.txt", "\n".join(LOG.buffer))
    for cid, bt in ctx["allbt"].items():
        if len(bt.get("returns", [])):
            persist(f"backtest_returns_{STRATEGY_ID}_{cid.replace('|', '_')}", bt["returns"],
                    scope="private", domain="backtest", source=cid)
    _write_cache_evidence()          # 백테스트 저장분까지 반영해 한 번 더 갱신
    LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:.1f}KB"] for p in OUTPUTS
               if os.path.exists(p)], ["산출물", "크기"], ["l", "r"],
              title=f"산출물 (§10) → {os.path.join(GDRIVE_PRIVATE_NS, 'outputs')}")


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except StageFailure as e:
        LOG.banner("실행 중단", "위 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow(limit=60)
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 캐시에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        _emergency_flush()
    except Exception as e:                                        # noqa
        # ★ StageFailure/KeyboardInterrupt 외의 예외(스테이지 밖에서 난 RuntimeError 등)가
        #   여기까지 오면, 예전엔 맨 트레이스백만 남기고 죽어 이번 실행이 디스크에 쓴
        #   parquet 이 저널에 등록되지 않은 채 남았다 — 다음 세션이 못 찾는다.
        LOG.banner("실행 중단", f"{type(e).__name__}: {str(e)[:200]}")
        _safe_print(traceback.format_exc()[-3000:])
        try:
            PIPE.report_stages()
        except Exception:
            pass
        _emergency_flush()
        try:
            if VAULT:
                VAULT.flush()
            if DQ:
                DQ.close()
        except Exception:
            pass
