

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 실행 순서와 산출물                                                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _reband(P: pd.DataFrame, mode: str, lo: float, hi: float) -> pd.DataFrame:
    """유니버스 밴드만 갈아끼운다. L1 재빌드가 필요 없다 — 랭크는 이미 패널에 있다(§3)."""
    Q = P.copy()
    adtv = col(Q, "adv20")
    seasoned = col(Q, "days_listed") >= UNIVERSE_SEASON_DAYS
    live = Q["listed"].astype(bool) if "listed" in Q.columns else pd.Series(True, index=Q.index)
    if mode == "pct":
        band = col(Q, "mcap_pct").between(lo, hi)
    elif mode == "bottom":
        # 매 시점 '시총 하위 lo개'. 월마다 상장 종목수가 다르므로 상수 랭크로 자를 수 없다.
        # mcap_rank 는 1 = 최대시총이므로 그 달의 최대 랭크에서 lo 개를 거꾸로 센다.
        r = col(Q, "mcap_rank")
        mx = r.groupby(Q["month"], observed=True).transform("max")
        band = (r > (mx - float(lo))) & r.notna()
    else:
        band = col(Q, "mcap_rank").between(lo, hi)
    Q["u_mid_alt"] = (band.fillna(False) & live & adtv.ge(UNIVERSE_MIN_ADTV).fillna(False)
                      & seasoned.fillna(False))
    return Q


def make_runner(months: pd.DatetimeIndex, sec: pd.DataFrame, stage: str = "M3") -> Callable:
    """L2 + L3 를 한 번 도는 클로저. 강건성 스위트가 이걸 반복 호출한다.

    ★ L1 은 절대 다시 만들지 않는다(§3). 그래서 절제 1회가 수십 초다.
    """
    def runner(P: pd.DataFrame, label: str = "run", signal: str = "Signal_rank",
               floor=True, veto: bool = True, drop_tp: Sequence[str] = (),
               drop_axis: Sequence[str] = (), tp_mode: str = "clip",
               floor_pct: float = BREADTH_FLOOR_PCT, uni: Optional[tuple] = None,
               costs: bool = True, naive_axes: Optional[Sequence[str]] = None,
               use_research: Optional[bool] = None) -> dict:
        Q = P
        entry = "u_mid"
        if uni is not None:
            Q = _reband(Q, *uni)
            entry = "u_mid_alt"
        need_full = (signal == "Signal_rank") or (floor is True)
        if need_full:
            S = assemble_score(Q, stage=stage, tp_mode=tp_mode, drop_tp=drop_tp,
                               drop_axis=drop_axis, floor_pct=floor_pct,
                               use_research=use_research, quiet=True)
        else:
            S = apply_vetoes(Q.copy(), stage=stage, quiet=True)
            S["FLOOR"] = np.int8(1)
            if "Signal" not in S.columns:
                S["Signal"] = 1.0
            if "E" not in S.columns:
                S["E"] = np.nan

        # ── 신호 교체 ───────────────────────────────────────────────────────────────
        if signal == "equal":
            S["Signal"] = 1.0
            S["Signal_rank"] = 1.0
        elif signal == "naive_improve":
            ax = list(naive_axes or [])
            cells = cell_series(S, CELL_KEYS)
            fb = list(CELL_KEYS[:-1])
            parts = [cell_rank(S, col(S, a), CELL_KEYS, fb, tag=f"naive:{a}")
                     for a in ax if a in S.columns]
            if not parts:
                raise RuntimeError("나이브 팔의 축이 하나도 없습니다.")
            base = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
            S["_naive_E"] = base
            er = cell_rank(S, base, ["ym"], ["ym"], min_n=20, tag="naive:E")
            ur = S["U_rank"] if "U_rank" in S.columns else pd.Series(1.0, index=S.index)
            S["Signal"] = (er.astype("float64") * ur.astype("float64")
                           * S["VETO"].astype("float64")).astype("float32")
            S["Signal_rank"] = (S["Signal"].groupby(S["month"], observed=True)
                                .rank(pct=True, method="average").astype("float32"))
        elif signal != "Signal_rank":
            if signal not in S.columns:
                raise RuntimeError(f"신호 컬럼 '{signal}' 이 패널에 없습니다.")
            S["Signal"] = pd.to_numeric(S[signal], errors="coerce").astype("float32")
            S["Signal_rank"] = (S["Signal"].groupby(S["month"], observed=True)
                                .rank(pct=True, method="average").astype("float32"))

        # ── 게이트 교체 ─────────────────────────────────────────────────────────────
        if not veto:
            S["VETO"] = np.int8(1)
        if floor is False:
            S["FLOOR"] = np.int8(1)
        elif floor == "naive":
            # ★ 나이브 팔은 **자기 증거로** 하한선을 만든다. 본선 FLOOR 를 물려주면
            #   나이브 팔조차 TP 로 선별된 종목만 보게 되어 비교 자체가 성립하지 않는다.
            #   축 개수도 맞춘다 — 하한선은 축수에 지수적이다.
            ax = list(naive_axes or [])
            n_groups = max(1, len([g for g, (m, need) in FLOOR_GROUPS.items()
                                   if _stage_ok(need, stage)]))
            chunks = [ax[i::n_groups] for i in range(n_groups)]
            ok = pd.Series(True, index=S.index)
            fb = list(CELL_KEYS[:-1])
            for ch in chunks:
                ch = [c for c in ch if c in S.columns]
                if not ch:
                    continue
                gv = pd.concat([col(S, c) for c in ch], axis=1).mean(axis=1, skipna=True)
                ok &= (cell_rank(S, gv, CELL_KEYS, fb, tag="naive:floor") >= floor_pct).fillna(False)
            S["FLOOR"] = ok.astype("int8")

        # 동일가중 기준선은 '유니버스 전체를 그냥 담는다'는 뜻이므로 종목수 상한을 풀어야 한다.
        # 25종목으로 자르면 그건 동일가중 벤치마크가 아니라 또 하나의 선정 규칙이 된다.
        eq = (signal == "equal")
        bt = run_backtest(S, months, sec, signal_col="Signal_rank",
                          top_pct=(1.0 if eq else PORTFOLIO_TOP_PCT),
                          max_names=(10_000 if eq else PORTFOLIO_MAX_NAMES),
                          apply_costs=costs, label=label, entry_col=entry, quiet=True)
        bt["scored"] = S if label.startswith("MAIN") else None
        return bt
    return runner


# ═══════════════════════════════════════════════════════════════════════════════════════════
def collect_all(months: pd.DatetimeIndex, stage: str) -> dict:
    """L1 수집. 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))

    with PIPE.stage("M0.UNI", "종목 마스터 (다중소스)", "M0", budget_s=600), Stage("M0.universe", 8):
        snaps = fetch_pykrx_snapshots(months)
        sec = cached_table(
            "security_master", [len(snaps), months.min(), months.max(), len(months)],
            lambda: build_security_master(snaps), scope="shared", domain="universe",
            source="fdr+kind+delisting+corpcode",
            note="종목 마스터(상장일·폐지일·corp_code) — 전 전략 공용",
            date_cols=("listing_date", "delisting_date"))
        ctx["sec"], ctx["snapshots"] = sec, snaps
        ctx["code_of_corp"] = (sec.dropna(subset=["corp_code"])
                                  .assign(corp_code=lambda d: d["corp_code"].astype(str))
                                  .set_index("corp_code")["code"].to_dict())

    with PIPE.stage("M0.PX", "가격 · 거래대금", "M0", budget_s=1500), Stage("M0.price", 20):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END, sec=ctx["sec"])
        ctx["px"] = px
        ctx["pp"] = build_price_panel(px, months)

    with PIPE.stage("M0.MCAP", "PIT 시가총액 (C13)", "M0", budget_s=900), Stage("M0.mcap", 8):
        ctx["mcap"] = fetch_pit_marketcap(months, ctx["pp"]["monthly"], ctx["sec"])

    with PIPE.stage("M0.DART", "DART 재무 (벌크 → 폴백)", "M0", budget_s=1800), Stage("M0.dart", 15):
        dis = fetch_dart_disclosures(
            (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"), BACKTEST_END)
        ctx["disclosures"] = dis
        kmap = cached_table("dart_knowledge_map", [dis],
                            lambda: build_knowledge_map(dis), scope="shared", domain="dart",
                            source="build_knowledge_map",
                            note="rcept_no → 접수일자 원장 — 전 전략 공용",
                            date_cols=("knowledge_date",))
        reprts = [REPRT_CODES[k] for k in ("Q1", "H1", "Q3", "FY")]
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        # 유동성 상위 종목의 corp_code 를 우선순위로 넘긴다 — 일일 한도로 끊겨도
        # '투자 가능한 종목의 최근 데이터'가 먼저 완성되게 하기 위함이다.
        prio: List[str] = []
        try:
            adv = (ctx["pp"]["monthly"].groupby("code", observed=True)["adv20"]
                   .median().sort_values(ascending=False))
            c2c = (ctx["sec"].dropna(subset=["corp_code"])
                   .assign(corp_code=lambda d: d["corp_code"].astype(str))
                   .set_index("code")["corp_code"].to_dict())
            prio = [c2c[c] for c in adv.index if c in c2c]
        except Exception:
            prio = []

        # ── §4.1 3단 티어. 정보량 순으로 쌓고, 상위 티어가 없는 조합만 하위가 메운다 ──
        #   Tier1 벌크            : 전 계정 · 1회 다운로드 (최선)
        #   Tier3 fnlttSinglAcntAll: 전 계정 · 단건(며칠 소요, 이어받기)
        #   Tier2 fnlttMultiAcnt  : 주요계정 6개 · 배치(즉시) — '바닥'을 싸게 깐다
        # ── 투자 가능 종목(= 유동성 하한을 한 번이라도 넘은 곳)의 corp_code 집합 ──
        #   이게 없으면 영원히 살 수 없는 종목의 재무제표까지 받느라 하루 쿼터를 태운다.
        inv_scope: set = set()
        try:
            _pm = ctx["pp"]["monthly"]
            _liq = (_pm.groupby("code", observed=True)["adv20"].max()
                    >= UNIVERSE_MIN_ADTV * 0.5)
            _ok_codes = set(_liq[_liq].index.astype(str))
            _c2c = (ctx["sec"].dropna(subset=["corp_code"])
                    .assign(corp_code=lambda d: d["corp_code"].astype(str))
                    .set_index("code")["corp_code"].to_dict())
            inv_scope = {_c2c[c] for c in _ok_codes if c in _c2c}
            LOG.table([["가격 패널 종목", f"{_pm['code'].nunique():,}"],
                       [f"유동성 하한 절반({UNIVERSE_MIN_ADTV*0.5:,.0f}원) 초과 이력",
                        f"{len(_ok_codes):,}"],
                       ["corp_code 매칭", f"{len(inv_scope):,}"],
                       ["→ 전체재무제표 대상", f"{len(inv_scope):,}사 × {len(years)}년"]],
                      ["수집 범위 산정", "종목수"], ["l", "r"],
                      title="DART 전체재무제표 수집 범위 — 살 수 없는 종목은 받지 않습니다 "
                            "(밴드는 진입 필터이므로 유동성 하한을 한 번도 못 넘으면 매수 불가)")
        except Exception as e:                                   # noqa
            LOG.warn(f"투자 가능 종목 판정 실패({type(e).__name__}) — 전 종목을 대상으로 "
                     f"진행합니다(호출량이 늘어납니다).")

        t_bulk = fetch_dart_bulk(years, reprts) if "bulk" not in DISABLED else pd.DataFrame()
        t_multi = fetch_dart_multi(corps, years, reprts)
        t_full = pd.DataFrame()
        if not nonempty(t_bulk):
            _gf = WALL.gate("DART 단건 전계정(Fallback B)", reserve_min=WALL_RESERVE_MIN + 20.0)
            if _gf:
                LOG.warn(_gf + "  → 이번 실행은 주요계정(Tier2)만으로 진행합니다. "
                               "재고·매출채권·영업CF 의존 TP 는 축소 보고됩니다.")
            else:
                LOG.warn("벌크가 비어 Fallback B(fnlttSinglAcntAll)를 가동합니다. 주요계정만으로는 "
                         "재고·매출채권·영업CF가 없어 TP_I2/TP_I4/TP_I1 이 죽기 때문입니다 — "
                         "이 경로 없이 나온 성과는 '코어가 빠진 전략'의 성과입니다.")
                t_full = fetch_dart_full(corps, years, priority=prio,
                                         scope=inv_scope or None)
        raw = merge_financial_tiers(t_bulk, t_full, t_multi)
        # ★ 실측 2.5분. 입력(원시 재무 + 접수일자 원장)이 그대로면 결과도 그대로다.
        #   전략과 무관한 중간 결과이므로 공용 인덱스에 둔다 — 다른 전략이 그대로 쓴다.
        ctx["fin"] = cached_table(
            "financials_tidy", [raw, kmap, DART_FS_FREQ, DART_MIN_YEAR,
                                sorted(ACCOUNT_MAP.keys())],
            lambda: tidy_financials(raw, kmap, ctx.get("code_of_corp")),
            scope="shared", domain="dart", source="tidy_financials",
            note="정제 재무(누적→분기·TTM 복원 완료) — 전 전략 공용",
            date_cols=("period_end", "knowledge_date"))
        ctx["weak_tp"] = report_account_coverage()

    if _stage_ok("M2", stage):
        _g = WALL.gate("DART 직원현황(TP_I3)")
        with PIPE.stage("M2.EMP", "DART 직원현황", "M2", budget_s=2400, critical=False,
                        skip_if=bool(_g), skip_reason=_g), \
                Stage("M2.employees", 42):
            if _g:
                ctx["emp"] = pd.DataFrame()
            elif "TP_I3" in DISABLED:
                LOG.warn("CANARY K7 실패로 TP_I3 가 비활성화되어 직원현황 수집을 건너뜁니다.")
                ctx["emp"] = pd.DataFrame()
            else:
                corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
                ctx["emp"] = fetch_dart_employees(corps, years, ctx.get("code_of_corp", {}))
    else:
        ctx["emp"] = pd.DataFrame()

    if _stage_ok("M3", stage):
        ctx["flows"] = pd.DataFrame()
        _g = WALL.gate("기관·외국인 수급(d3)")
        with PIPE.stage("M3.FLOW", "기관·외국인 수급 (d3)", "M3", budget_s=900, critical=False,
                        skip_if=bool(_g), skip_reason=_g), \
                Stage("M3.flows", 12):
            if _g:
                pass
            elif "d3" in DISABLED:
                LOG.warn("CANARY K6 실패로 d3 를 비활성화합니다 — U 는 d1 단독으로 구성됩니다.")
            else:
                ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(),
                                                    BACKTEST_START, BACKTEST_END)

        # ★ 리서치는 '수집'만 선택이고 '드라이브 캐시 사용'은 언제나 한다.
        #   예산이 소진돼도 이미 받아둔 리포트로 원장·컨센서스는 그대로 만든다.
        with PIPE.stage("M3.RESEARCH", "애널리스트 리포트 · 원장", "M3", budget_s=3600,
                        critical=False), Stage("M3.research", 25):
            ctx.update(collect_research(months, ctx["sec"]))
    else:
        ctx["flows"] = pd.DataFrame()
        ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
        ctx["consensus"] = pd.DataFrame()
    return ctx


def collect_research(months: pd.DatetimeIndex, sec: pd.DataFrame) -> dict:
    """한경컨센서스 · 네이버금융리서치.  드라이브 캐시 우선 → 부족분만 신규 → 재적재."""
    LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
             "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
             "로컬 분석 용도로만 사용하세요(재배포 금지).")
    cached = VAULT.get_table("research_report_master", scope="shared")
    frames = []
    _g = WALL.gate("리포트 신규 크롤(한경·네이버)")
    if _g:
        LOG.warn(_g + "  → 드라이브 캐시에 이미 있는 리포트만으로 원장을 구성합니다.")

    # ── 증분 크롤: 캐시가 이미 덮고 있는 기간을 다시 긁지 않는다 ──────────────────────
    #   실측 실패: 캐시 70,440건을 갖고도 company 1,500페이지 + industry 850페이지를
    #   전부 다시 긁어 15분을 썼다. 새로 얻은 리포트는 **0건**이었다(고유 70,440 그대로).
    #   리스트는 발행일 역순이므로, 캐시의 마지막 발행일 며칠 전부터만 받으면 충분하다.
    crawl_from = BACKTEST_START
    src_from: Dict[str, str] = {}
    if RESEARCH_INCREMENTAL and nonempty(cached) and "pub_date" in cached.columns:
        cd = cached.copy()
        cd["pub_date"] = as_ts_series(cd["pub_date"])
        for src in RESEARCH_SOURCES:
            sub = cd[cd["source"].astype(str).str.contains(src, case=False, na=False)] \
                if "source" in cd.columns else cd
            mx = sub["pub_date"].max() if nonempty(sub) else pd.NaT
            if pd.notna(mx):
                f = max(as_ts(BACKTEST_START),
                        mx - pd.Timedelta(days=RESEARCH_OVERLAP_DAYS))
                src_from[src] = min(f, as_ts(BACKTEST_END)).strftime("%Y-%m-%d")
        if src_from:
            LOG.table([[k, f"{v} ~ {BACKTEST_END}",
                        f"캐시 최종발행일 −{RESEARCH_OVERLAP_DAYS}일"] for k, v in src_from.items()],
                      ["소스", "이번에 크롤할 구간", "근거"], ["l", "l", "l"],
                      title=f"증분 크롤 — 캐시 {len(cached):,}건이 덮는 기간은 다시 긁지 않습니다 "
                            f"(RESEARCH_INCREMENTAL=False 로 전 구간 재크롤)")

    if RUN_MODE != "CACHED" and RESEARCH_COLLECT and not _g:
        if "hankyung" in RESEARCH_SOURCES:
            hk = hankyung_collect(src_from.get("hankyung", crawl_from), BACKTEST_END)
            if not nonempty(hk):
                LOG.warn("한경컨센서스에서 0건을 받았습니다. 한경은 사양상 1순위 소스이고 "
                         "리스트에 작성자·목표주가가 이미 들어 있어 PDF 없이도 원장이 서는 "
                         "유일한 경로입니다 — 0건이면 애널리스트 연결의 질이 네이버 단독으로 "
                         "떨어집니다. 사이트 구조 변경 또는 차단을 의심하세요.")
            frames.append(hk)
        if "naver" in RESEARCH_SOURCES:
            nv = naver_collect(src_from.get("naver", crawl_from), BACKTEST_END)
            frames.append(naver_enrich_detail(nv))
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                 f"(드라이브에 이미 있는 리포트를 다시 받지 않습니다)")
        frames.append(cached)
    rep = build_report_master(frames, sec)
    if len(rep):
        rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
        if "pdf_target" in rep.columns:
            fill = rep["target_price"].isna() & rep["pdf_target"].notna()
            if fill.any():
                rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
        # ★ 공용(다른 전략 재사용) + 전용(이 전략 시점) 양쪽에 저장한다
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
    audit_linkage(rep, A, L)
    cons = cached_table("consensus_panel", [L, months.min(), months.max(), len(months)],
                        lambda: build_consensus_panel(L, months), scope="shared",
                        domain="research", source="build_consensus_panel",
                        note="애널리스트 컨센서스 월 패널 — 전 전략 공용",
                        date_cols=("month",))
    return {"reports": rep, "analysts": A, "links": L, "consensus": cons}


def build_L1(ctx: dict, months: pd.DatetimeIndex, stage: str) -> Tuple[pd.DataFrame, "UniverseV3"]:
    with PIPE.stage("L1.PANEL", "L1 피처 패널 (정규화 없음)", "L1", budget_s=900), \
            Stage("L1.panel", 12):
        P = cached_table(
            "base_panel", [ctx["pp"]["monthly"], ctx["sec"], ctx.get("mcap"),
                           months.min(), months.max(), len(months),
                           UNIVERSE_SEASON_DAYS],
            lambda: build_base_panel(months, ctx["pp"]["monthly"], ctx["pp"]["daily"],
                                     ctx["sec"], ctx.get("mcap")),
            scope="shared", domain="universe", source="build_base_panel",
            note="PIT 기본 패널(시총랭크·상장경과·유동성) — 전 전략 공용",
            date_cols=("month", "signal_date", "next_date"))
        sources = {}
        if len(ctx.get("fin", [])):
            sources["fin"] = ctx["fin"]
        if len(ctx.get("emp", [])):
            sources["emp"] = ctx["emp"][["code", "employees", "payroll", "knowledge_date"]]
        P = build_pit_panel(P, sources)
        assert_c1(P, strict=True)               # ★ 출력 전수 검증 (§4.2)

        uni = UniverseV3(P, ctx["sec"], mode=UNIVERSE_MODE)
        P = uni.resolve_mode(P)
        P = build_cells(P, ctx["sec"])
        P = attach_investor_flows(P, ctx.get("flows"))
        P = build_sensors(P, stage=stage)
        P = build_disclosure_sensors(P, ctx.get("disclosures"), months)
        cons = ctx.get("consensus")
        if cons is not None and len(cons):
            c = cons.rename(columns={"code": "code"}).copy()
            c["month"] = as_ts_series(c["month"])
            c["code"] = c["code"].astype(str)
            P = P.merge(c[["code", "month", "d2_raw", "d4_raw", "n_analyst"]],
                        on=["code", "month"], how="left")
            LOG.ok(f"리서치 축 결합 — d2 {int(P['d2_raw'].notna().sum()):,}행 · "
                   f"d4 {int(P['d4_raw'].notna().sum()):,}행 "
                   f"(USE_RESEARCH_AXIS={USE_RESEARCH_AXIS})")
        for c in ("d2_raw", "d4_raw"):
            if c not in P.columns:
                P[c] = np.nan
        P = downcast(P)
        report_dead_signals(P, stage=stage)      # 백테스트 전에 '무엇이 죽었는지'를 못박는다
        LOG.ok(f"L1 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        # §3 구현 강제: L1 은 parquet 로 영속화하고 L2 는 이 parquet 만 읽는다
        VAULT.put_table(f"l1_panel_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 sensors (정규화 없음)")
    return P, uni


def main() -> dict:
    t0 = time.time()
    WALL.start()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 · {STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 단계 {STAGE} · 모드 {RUN_MODE} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               # ★ fork 불가(Windows/macOS spawn) 환경에서 pmap_cpu 는 스레드가 아니라
               #   **순차 실행**으로 폴백한다. "15 스레드"라고 찍으면 사용자가 병렬이 도는 줄
               #   알고 병목을 엉뚱한 곳에서 찾게 된다. 실제 동작을 그대로 적는다.
               ["병렬", f"IO {N_WORKERS_IO} 스레드 · 연산 " +
                        (f"{N_CPU} 프로세스(fork)" if CAN_FORK else
                         "순차(fork 불가 — 이 파이프라인의 연산부는 이미 벡터화되어 있어 "
                         "영향이 크지 않습니다)")],
               ["시드", str(SEED)],
               ["DART 키", "입력됨" if DART_API_KEY else "❗ 미입력 — 재무 센서 전부 결측"],
               ["KRX 계정", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW)
                else "미입력 — PIT 시총이 근사로 대체됩니다(C13 약화)"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    report_stage_matrix()

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300), Stage("L0.vault", 3):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"공용 인덱스 {GDRIVE_SHARED_NS} (전 전략 재사용) · "
                 f"전용 인덱스 {GDRIVE_PRIVATE_NS} (이 전략) — "
                 f"기존 기록은 append-only 저널이라 훼손 불가입니다.")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간 2GB 미만 — RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        # 설정된 경로 + 플랫폼별 자동 탐지. 손으로 경로를 고치지 않아도 이미 모아둔
        # 리포트를 찾아낸다(읽기 전용 등록 — 이동·삭제 없음).
        adopt = list(dict.fromkeys(list(GDRIVE_ADOPT_DIRS) + discover_drive_dirs(VAULT.root)))
        LOG.info(f"기존 캐시 스캔 대상 {len(adopt)}곳 (설정 {len(GDRIVE_ADOPT_DIRS)} + 자동탐지 "
                 f"{len(adopt) - len(GDRIVE_ADOPT_DIRS)})")
        VAULT.adopt_scan(adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300), Stage("L0.contracts", 2):
        # ★ 반환값을 반드시 확인한다. strict=True 가 내부에서 raise 하는 것에만 의존하면,
        #   리팩터링으로 그 경로가 끊겼을 때(실제로 한 번 그랬다 — 요약/raise 블록이 다른
        #   함수 안으로 딸려 들어가 함수가 None 을 반환했다) 계약이 전부 실패해도 조용히
        #   통과한다. None 은 falsy 이므로 이 검사가 그 유형까지 함께 막는다.
        if not run_contract_tests(strict=True):
            raise RuntimeError("계약 자동검정이 통과를 보고하지 않았습니다 — "
                               "실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.SMOKE", "합성 스모크", "L0", budget_s=1800), Stage("L0.smoke", 3):
        run_smoke(full=(RUN_MODE == "SMOKE"))

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        report_dataflow_map()
        return {"mode": "SMOKE"}

    months = month_range(BACKTEST_START, BACKTEST_END)
    stage = STAGE if STAGE in STAGE_ORDER else "M3"

    # ★ 스테이지 밖에서 초기화한다. 안에서만 대입하면 CANARY 가 예외로 죽었을 때
    #   L0.PERSIST 의 참조가 UnboundLocalError 를 내고, 그러면 '왜 죽었는지'를 담은
    #   산출물 저장 자체가 실패해 진단 정보를 잃는다.
    ctx_canary = pd.DataFrame()
    with PIPE.stage("CANARY", "CANARY K1~K7", "L0", budget_s=1500, critical=False), \
            Stage("CANARY", 20):
        # ★ critical=False. §1 의 설계는 "FAIL 항목에 의존하는 단계를 큐에서 제거하고 진행"
        #   이다. CANARY 가 전체 실행을 죽이면 그 설계와 정면으로 어긋난다.
        #   진짜 중단 사유(K5 상장폐지 미확보)는 KillCriteria 로 별도 전파된다.
        probe_codes, probe_corps = [], []
        try:
            probe_sec = fetch_fdr_listing()
            if nonempty(probe_sec):
                probe_codes = probe_sec["code"].dropna().astype(str).tolist()[:200]
        except Exception as e:                                   # noqa
            LOG.warn(f"CANARY 표본 종목 확보 실패({type(e).__name__}) — 기본 표본으로 진행합니다.")
        try:
            cc = fetch_dart_corpcode()
            if nonempty(cc):
                probe_corps = cc.dropna(subset=["code"])["corp_code"].astype(str).tolist()[:200]
        except Exception as e:                                   # noqa
            LOG.warn(f"CANARY corp_code 확보 실패({type(e).__name__}) — K7 은 건너뜁니다.")
        ctx_canary = run_canary(probe_codes, probe_corps)

    ctx = collect_all(months, stage)
    P, uni = build_L1(ctx, months, stage)
    runner = make_runner(months, ctx["sec"], stage=stage)

    # ── §2 단계별 백테스트 — M0 에서 이미 결과가 나온다 ──────────────────────────────
    results = {}
    bench = benchmark_returns(months)   # (내부에서 소스별 캐시를 씁니다)
    for st in STAGE_ORDER:
        if not _stage_ok(st, stage):
            break
        with PIPE.stage(f"{st}.BT", f"백테스트 ({st})", "L3", budget_s=600), Stage(f"{st}.backtest",
                                                                                  STAGE_BUDGET_MIN.get(st)):
            r = make_runner(months, ctx["sec"], stage=st)
            bt = r(P, label=f"MAIN:{st}")
            results[st] = bt
            LOG.rule(f"{st} 백테스트 결과")
            report_performance(bt, bench if st == stage else {}, title=f"성과 검증 ({st})")

    # ── 대조군: 시총 하위 N 유니버스 (같은 신호·같은 비용·같은 유동성 하한) ──────────
    #   U-MID 가 정말 최적 구간인지, 아니면 그냥 소형주 프리미엄인지 가르는 실험이다.
    bt_small = None
    if SMALLCAP_COMPARE:
        with PIPE.stage("L3.SMALL", f"비교 백테스트 (시총 하위 {SMALLCAP_BOTTOM_N:,})", "L3",
                        budget_s=600, critical=False), Stage("L3.smallcap", 6):
            bt_small = runner(P, label=f"SMALLCAP:bottom{SMALLCAP_BOTTOM_N}",
                              uni=("bottom", SMALLCAP_BOTTOM_N, 0))
            LOG.rule(f"스몰캡 비교 백테스트 (시총 하위 {SMALLCAP_BOTTOM_N:,})")
            report_performance(bt_small, bench,
                               title=f"성과 검증 (대조군 · 시총 하위 {SMALLCAP_BOTTOM_N:,})")
            report_universe_compare(results[stage], bt_small)

    bt = results[stage]
    S = bt.get("scored")
    if S is None:
        S = assemble_score(P, stage=stage, quiet=False)

    with PIPE.stage("L6.PERF", "성과 검증 (최종)", "L6", budget_s=180), Stage("L6.perf", 3):
        report_performance(bt, bench, title="성과 검증 (최종)")
        uni.audit_attrition(P)
        report_cell_fallback()

    with PIPE.stage("R.SUITE", "강건성 R0~R10", "L5", budget_s=4 * 3600, critical=False), \
            Stage("R-SUITE", 45):
        try:
            R0_baseline(P, months, ctx["sec"], runner)
            R1_leakage(P, months, ctx["sec"], runner, bt)
            R2_tp_vs_naive(P, months, ctx["sec"], runner, bt)
            R3_orthogonal(S, bt, months)
            R5_ablation(P, months, ctx["sec"], runner, bt)
            R6_pbo()
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, months, ctx["sec"], runner, bt)
            R10_policy(P, months, ctx["sec"], runner, bt)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드", "L6", budget_s=180, critical=False), \
            Stage("L6.report", 3):
        report_interpretation(S, bt)
        card = diagnostic_card(S, bt, ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False), Stage("L0.persist", 5):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []

        def _w(name, df):
            if df is None or not len(df):
                return
            p = os.path.join(outdir, f"{name}_{stamp}.csv")
            df.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)

        _w("returns", bt["returns"])
        _w("holdings", bt["holdings"])
        _w("canary", ctx_canary)
        _w("attrition", uni.attrition)
        _w("runtime", pd.DataFrame(RUNTIME_LOG))
        _w("robustness", pd.DataFrame(ROBUST))
        for st, b in results.items():
            _w(f"backtest_{st}", b["returns"])
        if card:
            p = os.path.join(outdir, f"card_sample_{stamp}.txt")
            atomic_write_text(p, card)
            outs.append(p)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)

        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        S[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "u_mid") if c in S.columns]],
                        scope="private", domain="scores", source="L2")
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        if DBUDGET:
            DBUDGET.report()
            DBUDGET.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    report_http()
    report_dataflow_map()
    WALL.report()
    report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
    LOG.banner("완료", f"총 소요 {(time.time()-t0)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시: ① 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 d1 의 E 는 "
             "후행 12M 이익 대리변수입니다. ② p_cancel 은 미래를 보지 않도록 재정의되어 "
             "원문 정의보다 1년 늦습니다. ③ V5 는 자본잠식만 판정합니다(감사의견 소스 없음). "
             "④ PIT 시총이 근사인 구간에서는 자본이벤트 기업의 밴드 편입이 틀어집니다. "
             "숨기지 않고 여기에 명시합니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "scored": S, "backtest": bt, "stages": results,
            "ctx": ctx, "robust": ROBUST, "canary": ctx_canary}


RESULT: Optional[dict] = None


def _entry():
    global RESULT
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        try:
            report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        report_dataflow_map()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 정확히 이 지점부터 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass


# ★ 노트북(Colab/JupyterLab)에서는 셀 실행이 곧 실행이고, CLI 에서는 __main__ 일 때만 돈다.
#   `import` 로 불러가는 경우에는 자동 실행되지 않는다(TCD_NO_AUTORUN=1 로도 끌 수 있다).
if os.environ.get("TCD_NO_AUTORUN", "") not in ("1", "true", "True"):
    if __name__ == "__main__" or ENV.get("ipython"):
        _entry()
