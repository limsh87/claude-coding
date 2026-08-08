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
        # ★★ C18 지연을 반드시 통과시킨다 ★★
        #   센서는 '귀속월' 격자에서 산출되지만, 그 달 실적은 **익월 중순에야 공표**된다.
        #   귀속월에 직결하면 2018-03 통관을 2018-04-02 시가에 매수하는 셈이 되어
        #   2주 앞을 보는 미래누수가 된다. assert_c1 은 knowledge_date 컬럼이 없는 소스는
        #   검사조차 못 하므로 조용히 통과한다 — 그래서 반드시 PIT 결합으로 보낸다.
        a_pit = a_corp.copy()
        a_pit["knowledge_date"] = customs_knowledge_date(a_pit["ym"])
        a_pit = a_pit.drop(columns=["ym"])
        P = build_pit_panel(P, {"axisA": a_pit}, by="code", left_time="month")
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
            # ★ 모양 변환은 normalize_flows_monthly 한 곳에서만 한다.
            #   여기서 리네임으로 때우면 소스마다 다른 스키마가 그대로 패널까지 흘러간다.
            flows = normalize_flows_monthly(
                fetch_investor_flows(_codes, BACKTEST_START, BACKTEST_END))
        except Exception as e:                                          # noqa
            LOG.warn(f"KRX 수급 수집 실패({type(e).__name__}) — 네이버 폴백을 시도합니다.")
    if flows is None or not len(flows):
        try:
            flows = normalize_flows_monthly(flows_naver(_codes, months))
        except Exception as e:                                          # noqa
            LOG.warn(f"네이버 수급 폴백 실패({type(e).__name__}) — d3 비활성화(0 채움 금지).")
            flows = None
    _dcols = ["code", "ym", "close"] + (["mcap"] if "mcap" in P.columns else [])
    d = d_sensors(P[_dcols], fin_m, flows, cov)
    P = P.merge(d.drop(columns=["close"], errors="ignore"), on=["code", "ym"], how="left")
    if len(cov):
        P = P.merge(cov, on=["code", "ym"], how="left")
        # ★ 커버리지 패널에는 '리포트가 하나라도 있는' 종목월만 행이 생긴다.
        #   그래서 무커버리지 종목은 n_analyst 가 결측이 되는데, 사양상 d2 = -(커버리지 수) 이고
        #   **무커버리지일수록 좋다**. 결측으로 두면 이 전략이 노리는 바로 그 집단이
        #   D축에서 통째로 빠진다(정확히 반대 방향의 실수).
        #   원장이 비어 있지 않다면 '리포트 없음'은 관측된 0 이므로 0 으로 채운다.
        P["n_analyst"] = pd.to_numeric(P.get("n_analyst"), errors="coerce").fillna(0.0)
        P["coverage_init"] = pd.to_numeric(P.get("coverage_init"), errors="coerce").fillna(0.0)
        P["d2"] = -P["n_analyst"]
        P["d4"] = P["coverage_init"]

    # ── 거부권 입력
    dil = build_dilution_flags(dis, months)
    if len(dil):
        P = P.merge(dil, on=["code", "ym"], how="left")
    wf = build_watch_flags(dis, months, sec)
    if len(wf):
        P = P.merge(wf, on=["code", "ym"], how="left")
    # ★ P.get(없는컬럼) 은 None 을 돌려주고 pd.to_numeric(None) 은 **스칼라**가 된다.
    #   .fillna() 를 부르는 순간 AttributeError 로 L2.PANEL 이 통째로 죽는다.
    #   '해당 공시를 하나도 못 찾은 경우'가 문서상 정상 경로이므로 반드시 방어한다.
    def _pcol(name: str) -> pd.Series:
        if name in P.columns:
            return pd.to_numeric(P[name], errors="coerce")
        return pd.Series(np.nan, index=P.index, dtype="float64")

    P["watch_flag"] = np.maximum(_pcol("watch_flag").fillna(0), _pcol("impaired").fillna(0))
    _th = _pcol("theta_x")
    P["theta_x_chg"] = _th - _th.groupby(P["code"], observed=True).shift(12)
    # 매핑 게이트 실패 플래그는 매핑표에서 종목 단위로 들어온다(없으면 0 = 통과).
    if "map_gate_fail" not in P.columns:
        gf = (mapping[["code", "map_gate_fail"]].drop_duplicates("code")
              if mapping is not None and "map_gate_fail" in getattr(mapping, "columns", [])
              else None)
        if gf is not None and len(gf):
            P = P.merge(gf, on="code", how="left")
    P["map_gate_fail"] = _pcol("map_gate_fail").fillna(0.0)
    for _v in ("dilution_90d", "subsidy_ratio_chg", "oversea_rev_chg"):
        if _v not in P.columns:
            P[_v] = np.nan

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
        # ★ 같은 커널에서 두 번째 실행 시 지난 실행의 상장/폐지 스냅샷을 재사용하지 않는다.
        reset_once()
        CELL_FALLBACK_STATS.clear()
        HTTP_STATS.clear()
        PIPE.stages.clear()
        PIPE.flow.clear()
        PIPE.failed.clear()
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
        # ★ KSIC 업종코드는 큐레이션(HS→상장사)의 유일한 연결고리다. 반드시 여기서 확보한다.
        #   종목 마스터는 자유텍스트 업종명만 주고 KSIC 코드는 주지 않는다.
        corpmap = fetch_dart_corpcode()
        # ★★ 여기가 사고 지점이었다 ★★
        #   fetch_dart_corpcode() 는 **DART 등록 법인 전체**(비상장 포함 약 118,675건)를 준다.
        #   이걸 그대로 넘기면 직원현황이 118,675 × 12년 = 1,424,100 잡이 되어 48시간이 걸리고
        #   DART 일일 한도(20,000)를 한참 넘겨 키가 막힌다.
        #   → 종목 마스터에 실재하는 **상장사**로만 좁힌다(약 4천건).
        code_of = {}
        if corpmap is not None and len(corpmap):
            _live = set(sec["code"].astype(str))
            _cm = corpmap.copy()
            _cm["code"] = _cm["code"].map(to_code6)
            _cm = _cm[_cm["code"].notna() & _cm["code"].isin(_live)]
            code_of = dict(zip(_cm["corp_code"].astype(str), _cm["code"].astype(str)))
            LOG.info(f"DART 법인 {len(corpmap):,}건 중 **상장사 {len(code_of):,}건**으로 좁혔습니다 "
                     f"(비상장 제외 — 이 전략은 상장사만 다룹니다).")
        if code_of:
            ind = fetch_dart_industry(sorted(code_of), code_of)
            if len(ind):
                sec = sec.merge(ind[["code", "induty_code"]].drop_duplicates("code"),
                                on="code", how="left")
        if "induty_code" not in sec.columns:
            sec["induty_code"] = ""
        _cov_ksic = float((sec["induty_code"].astype(str).str.len() > 0).mean())
        if _cov_ksic < 0.30:
            LOG.error(f"KSIC 업종코드 확보율 {_cov_ksic*100:.0f}% — HS↔상장사 매핑이 사실상 "
                      f"불가능합니다. 채택 HS 가 0개가 되어 유니버스가 비게 됩니다. "
                      f"DART_API_KEY 를 먼저 확인하세요.")

    with PIPE.stage("L1.PRICE", "가격 · 시가총액", "L1", budget_s=2400), \
            Stage("M0.price", 25.0):
        codes = sorted(sec["code"].astype(str).unique())
        # ★ sec 를 넘겨야 상장일(재수집 루프 차단)과 폐지표시(yfinance 회피)가 반영된다.
        px_d = fetch_prices(codes, BACKTEST_START, BACKTEST_END, sec=sec)
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

    with PIPE.stage("L1.CUSTOMS", "관세청 통관 (큐레이션 수집분 재사용)", "L1", budget_s=2400), \
            Stage("M0.customs", 20.0):
        # ★ 章 단위 조회는 그 아래 6자리 코드를 **전부** 포함한다. 채택 HS 는 그 부분집합이므로
        #   다시 받을 이유가 없다. 예전엔 여기서 610콜을 통째로 재실행해 매 실행 6분을 버렸다.
        cx = cx0
        if adopted and cx0 is not None and len(cx0):
            _pref = tuple(sorted(set(str(h) for h in adopted)))
            _hs = cx0["hs"].astype(str)
            cx = cx0[_hs.str.startswith(_pref)].copy()
            LOG.ok(f"큐레이션 수집분에서 채택 HS 만 추림: {len(cx0):,}행 → {len(cx):,}행 "
                   f"(HS {cx['hs'].nunique():,}개 · 신규 호출 0회)")
        if cx is None or not len(cx):
            LOG.warn("채택 HS 로 걸러낸 통관이 비어 큐레이션 수집분 전체를 사용합니다.")
            cx = cx0
        if cx is None or not len(cx):
            LOG.error("통관 데이터를 확보하지 못했습니다 — A축이 없으면 이 전략은 성립하지 않습니다.")
            PIPE.report_stages()
            return 3

    # ── [3] DART · 리서치 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시", "L1", budget_s=3000), \
            Stage("M0.dart", 30.0):
        years = list(range(pd.Timestamp(BACKTEST_START).year - 1,
                           pd.Timestamp(BACKTEST_END).year + 1))
        raw = fetch_dart_bulk(years, list(REPRT_CODES.values()))
        # ★ 벌크는 공개 API 가 아니라 웹 다운로드라 사이트 구조가 바뀌면 통째로 실패한다.
        #   실측에서 48분기가 전부 실패했는데, 코어는 "폴백으로 전환합니다" 라고 **로그만 찍고**
        #   실제로는 아무것도 호출하지 않았다 → fin 이 빈 채로 B·C축이 조용히 죽는다.
        #   여기서 실제로 폴백을 태운다. 배치 API(100사/호출)라 상장사 전체라도 저렴하다.
        if (raw is None or not len(raw)) and code_of:
            _corp = sorted(code_of)
            _n_call = max(1, math.ceil(len(_corp) / max(DART_MULTI_BATCH, 1))) * \
                len(years) * len(REPRT_CODES)
            LOG.warn(f"벌크 재무가 비었습니다 — Fallback A(fnlttMultiAcnt)를 **실제로** 실행합니다. "
                     f"상장사 {len(_corp):,}개 × {len(years)}년 × {len(REPRT_CODES)}보고서 "
                     f"→ 배치 약 {_n_call:,}회(1회당 {DART_MULTI_BATCH}사).")
            guard_dart_jobs(_n_call, "재무 폴백(fnlttMultiAcnt) 배치",
                            "재무는 상장사 전체가 필요하지만 **배치 API** 라 호출 수는 1/100 입니다.")
            raw = fetch_dart_multi(_corp, years, list(REPRT_CODES.values()))
            if raw is not None and len(raw):
                LOG.warn("주요계정만 확보했습니다 — 재고·매출채권·영업CF·유형자산취득이 없어 "
                         "b2(회전)·b3(발생액)·c1(투자)이 죽습니다. TP_B1·TP_B2·TP_C1 이 그만큼 "
                         "약해지므로 해석표의 유효관측 수를 반드시 확인하세요.")
            else:
                LOG.error("재무를 한 건도 확보하지 못했습니다 — B·C축이 전멸합니다. "
                          "DART_API_KEY 와 opendart 접근을 확인하세요.")
        dis = fetch_dart_disclosures(BACKTEST_START.replace("-", ""),
                                     BACKTEST_END.replace("-", ""))
        kmap = build_knowledge_map(dis)
        # ★★ code_of 를 반드시 넘긴다 ★★
        #   벌크는 stock_code 로, API(fnlttMultiAcnt)는 corp_code 로 온다.
        #   이 인자를 빠뜨리면 corp_code→종목코드 복원 분기가 죽고 dropna(subset=["code"])가
        #   전 행을 지운다. 실측: 1,249,787행 → **6행**. B·C축·θ_X·d1 이 통째로 사망했다.
        fin = tidy_financials(raw, kmap, code_of)
        # ★ 직원현황(c3·c4)은 **매핑이 끝난 뒤** 그 종목들만 받는다.
        #   여기서 받으면 대상이 확정되지 않아 전 상장사 × 12년이 되고, 그중 대부분은
        #   유니버스에 들어오지도 못해 통째로 버려진다. L2.PANEL 직전으로 옮겼다.
        emp = None

    reports = pd.DataFrame(columns=REPORT_COLS)
    analysts = pd.DataFrame()
    with PIPE.stage("L1.RESEARCH", "리서치 원장(캐시 우선)", "L1",
                    budget_s=1800, critical=False), Stage("M2.research", 15.0):
        if FOREIGN is not None:
            reports = foreign_reports(FOREIGN)
            analysts = foreign_analysts(FOREIGN)
        # ★ 색인 복원 원장은 파일명에 6자리 코드가 없는 건이 많다. 마스터가 준비된
        #   지금 종목명으로 붙인다(이 단계 전에는 sec 가 없어 불가능하다).
        reports = resolve_report_codes(reports, sec)
        if RESEARCH_COLLECT and RUN_MODE == "FULL" and len(reports) < 5000:
            try:
                frames = [reports] if len(reports) else []
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
                if "naver" in RESEARCH_SOURCES:
                    frames.append(naver_collect(BACKTEST_START, BACKTEST_END))
                frames = [f for f in frames if f is not None and len(f)]
                if frames:
                    reports = build_report_master(frames, sec)
            except Exception as e:                                      # noqa
                LOG.warn(f"리서치 신규 수집 실패({type(e).__name__}) — 캐시분만 사용합니다.")
        if len(reports):
            try:
                analysts, _link = build_analyst_ledger(reports)
                audit_linkage(reports, analysts, _link)
            except Exception as e:                                      # noqa
                LOG.warn(f"애널리스트 원장 구축 실패({type(e).__name__}) — d2 정밀도가 낮아집니다.")

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
        # ★ 직원현황은 **매핑된 종목만**. 명세 §5.1 의 요지가 '유니버스를 좁혀 비용을 지불한다'인데
        #   전 상장사를 받으면 그 설계가 무의미해진다.
        if STAGE in ("M2", "ALL") and mapping is not None and len(mapping):
            _mapped = set(mapping["code"].astype(str))
            _emp_corp = sorted(cc for cc, cd in code_of.items() if cd in _mapped)
            _emp_years = [y for y in years if y >= pd.Timestamp(BACKTEST_START).year - 1]
            LOG.info(f"직원현황 수집 대상: 매핑된 {len(_mapped):,}종목 중 corp_code 확보 "
                     f"{len(_emp_corp):,}건 × {len(_emp_years)}년 = "
                     f"{len(_emp_corp) * len(_emp_years):,}잡")
            guard_dart_jobs(len(_emp_corp) * len(_emp_years), "직원현황(empSttus) 수집",
                            "직원현황은 **매핑된 종목만** 필요합니다(TP_C2 의 c3·c4).")
            emp = fetch_dart_employees(_emp_corp, _emp_years, code_of)
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
        # ★ 성과표를 읽기 **전에** 그 표를 믿어도 되는지 먼저 판정한다.
        audit_signal_integrity(P, bt)
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
