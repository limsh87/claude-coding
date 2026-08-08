# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  각 단계는 PIPE.stage 안에서만 돈다. 실패하면 자동으로 다음이 출력된다:                     ║
# ║    실패 지점(스테이지·계층·경과) / 직전 입출력 스냅샷 / 한글 진단 힌트 / 트레이스백          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _rehearsal_hook_v3(G: dict, sec: pd.DataFrame, corps: Sequence[str],
                       months: pd.DatetimeIndex) -> None:
    """v3 전용 수집·계산 함수를 리허설에 태운다 (가짜 네트워크가 물려 있는 안쪽)."""
    _rh("fetch_emp_status(v3 확장)",
        lambda: fetch_emp_status(list(corps)[:3], [2019, 2020]), expect_rows=False,
        note="empSttus 확장 파서 — 소계행 제거·단위 역추정 포함")
    _rh("build_emp_sensors + C15",
        lambda: build_emp_sensors(pd.DataFrame({
            "corp_code": ["Z1"] * 3, "bsns_year": [2018, 2019, 2020],
            "rcept_dt": pd.to_datetime(["2019-03-20", "2020-03-20", "2021-03-20"]),
            "employees": [500.0, 600.0, 610.0], "regular": [450.0, 540.0, 550.0],
            "payroll_total": [3.5e10, 4.4e10, 4.5e10],
            "avg_salary": [7e7, 7.1e7, 7.2e7], "src_flag": ["detail"] * 3})),
        note="연도 프레임 센서 + C15 게이트")


REHEARSAL_HOOKS.append(_rehearsal_hook_v3)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Tier-2 전체재무제표 수집 범위 — 4시간 계약(§12-6)을 지키는 지점
#
#  이 함수가 없으면 잡 수는 |상장·폐지 전 종목| × |연도| × |보고서| 로 곱해진다.
#  3,981사 × 13년 × 4분기 = 207,012회. DART 일일한도 19,000 기준 11일이다.
#  좁히는 근거는 두 가지뿐이고, 둘 다 결과를 바꾸지 않는다:
#    ① 한 번도 U-MID 대역(투자가능)에 들지 못한 종목의 전체재무제표는 어떤 달에도
#       포트폴리오에 들어갈 수 없다 → 스코어에 쓰이지 않는다.
#    ② 백테스트 시작연도 −DART_FS_WARMUP_Y 이전 회계연도는 TTM·전년대비에도 안 쓰인다.
#  ①의 U-MID 판정은 **가격패널만으로** 내려진다(20일 평균거래대금 랭크) — 재무를 보지
#  않으므로 순환참조가 없고, 미래 재무를 미리 들여다보는 일도 없다.
# ══════════════════════════════════════════════════════════════════════════════════════════
def dart_fs_scope_v3(ctx: dict, all_corps: Sequence[str], quiet: bool = False
                     ) -> Tuple[List[str], List[int], List[str]]:
    """(수집대상 corp_code, 연도, 우선순위 corp_code) 를 돌려준다.

    quiet=True 면 로그를 찍지 않는다 — 직원현황 단계가 우선순위만 빌려 쓸 때 쓴다."""
    y0 = as_ts(BACKTEST_START).year - int(DART_FS_WARMUP_Y)
    years = list(range(y0, as_ts(BACKTEST_END).year + 1))
    corps = [str(c) for c in all_corps]
    prio: List[str] = []
    try:
        pm = ctx["panel"]["monthly"]
        adv = col(pm, "adv20")
        rank = adv.groupby(pm["month"], observed=True).rank(ascending=False, method="first")
        in_band = rank.between(UMID_RANK_LO, UMID_RANK_HI) & (adv >= MIN_ADV_KRW)
        # 우선순위: 'U-MID 대역에 머문 달 수'가 많은 종목부터. 유동성 1등이 아니라
        # **실제로 담길 확률이 높은 종목**부터 채우는 것이 백테스트 커버리지에 직결된다.
        months_in = (pm.loc[in_band.fillna(False), "code"].value_counts())
        c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
               .set_index("code")["corp_code"].astype(str).to_dict())
        prio = [c2c[c] for c in months_in.index if c in c2c]
        if DART_FS_UNIVERSE_ONLY and prio:
            keep = set(prio)
            dropped = len(corps) - len([c for c in corps if c in keep])
            corps = [c for c in corps if c in keep]
            if not quiet:
                LOG.info(f"Tier-2 수집대상을 U-MID 대역 경험 종목 {len(corps):,}사로 좁힙니다 "
                         f"(제외 {dropped:,}사 — 전 기간 한 번도 투자가능 대역에 들지 못해 "
                         f"어떤 달에도 편입될 수 없는 종목입니다).")
    except Exception as e:                                          # noqa
        if not quiet:
            LOG.warn(f"U-MID 기반 Tier-2 범위 축소 실패({type(e).__name__}) — 전 종목으로 진행합니다.")
    n_reprt = 1 if DART_FS_FREQ == "annual" else 4
    est = len(corps) * len(years) * n_reprt
    cap = est if DART_FS_MAX_CALLS is None else min(est, int(DART_FS_MAX_CALLS))
    if not quiet:
        LOG.info(f"Tier-2 전체재무제표 계획: {len(corps):,}사 × {len(years)}년 × "
                 f"{n_reprt}보고서 = 최대 {est:,}건 → 이번 실행 상한 {cap:,}건 "
                 f"(≈{cap/5/60:.0f}분). 나머지는 Tier-1 주요계정으로 대체하고 재실행 시 이어받습니다.")
    if DART_FS_MAX_CALLS == 0:
        if not quiet:
            LOG.warn("DART_FS_MAX_CALLS=0 — Tier-2 를 건너뜁니다. 재고·매출채권·영업CF 가 결측이므로 "
                 "TP_I1/TP_I2(회계품질) 가 비활성화됩니다.")
        return [], years, prio
    return corps, years, prio


def offer_download_v3(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f                 # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
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


def downcast_floats(P: pd.DataFrame) -> pd.DataFrame:
    """float64 → float32 만. object→category 변환은 하지 않는다.

    ★ 코어의 downcast() 는 저카디널리티 object 를 category 로 바꾼다. 그러면 강건성 팔에서
      P.copy() 후 merge 할 때 category vs object dtype 불일치로 매칭이 0건이 되거나
      dtype 오류가 난다. 스코어링 패널은 여러 번 복제·재계산되므로 이 위험을 피한다.
    """
    for c in P.columns:
        if P[c].dtype.kind == "f":
            P[c] = pd.to_numeric(P[c], downcast="float")
    return P


def announce_budget_v3():
    """수집을 시작하기 전에 '이번 실행이 몇 분짜리인지'를 먼저 못박아 보여준다.

    ★ 이 표가 없으면 곱셈으로 폭발한 잡 수가 tqdm ETA 로만 드러난다 — 이미 돌기 시작한
      뒤다. 4시간 계약(§12-6)은 사후 판정이 아니라 **사전 상한**이어야 한다.
    """
    fs_cap, emp_cap = DART_FS_MAX_CALLS, EMP_MAX_CALLS
    used = DBUDGET.n if DBUDGET else 0
    left = max(0, DART_DAILY_LIMIT - used)
    _n = lambda v: "무제한" if v is None else f"{int(v):,}"
    _m = lambda v, qps: "며칠" if v is None else f"{int(v)/qps/60:.0f}"
    rows = [
        ["L1.UNI  종목마스터·스냅샷", "-", "10", "pykrx/FDR/KIND"],
        ["L1.PX   일봉·거래대금", "-", "40", "실패종목 30일 음성캐시 → 재실행은 대폭 단축"],
        ["L1.EMP  직원현황(empSttus)", _n(emp_cap), _m(emp_cap, 8.0),
         "① 알파 원천 — 예산을 먼저 배정 · EMP_MAX_CALLS"],
        ["L1.DART Tier-1 주요계정(배치)", "≈2,100", "5", "100사/호출 — 전 종목 전 연도"],
        ["L1.DART Tier-2 전체재무제표", _n(fs_cap), _m(fs_cap, 5.0),
         f"② 남는 예산으로 · {DART_FS_FREQ} · DART_FS_MAX_CALLS"],
        ["L2~R    피처·백테스트·강건성", "-", "35", "네트워크 없음"],
    ]
    LOG.table(rows, ["단계", "DART 호출 상한", "예상(분)", "비고"], ["l", "r", "r", "l"],
              title="이번 실행의 수집 예산 (§10 · 총 예산 153분 / 킬 기준 4시간)")
    plan = sum(int(v) for v in (emp_cap, fs_cap) if v is not None) + 2100
    LOG.info(f"DART 일일 한도 {DART_DAILY_LIMIT:,} · 오늘 사용 {used:,} · 잔여 {left:,} → "
             f"이번 실행 계획 {plan:,}건. 한도에 닿으면 그 지점에서 깨끗이 멈추고 "
             f"수집분을 드라이브에 저장합니다. 재실행하면 이어받습니다.")
    if fs_cap is None or emp_cap is None:
        LOG.warn("호출 상한이 None 인 단계가 있습니다 — 콜드빌드는 며칠이 걸리며 §12-6 의 "
                 "4시간 계약 밖입니다. 4시간 안에 끝내려면 숫자를 넣으세요 "
                 "(권장: EMP_MAX_CALLS=14000, DART_FS_MAX_CALLS=12000).")
    if plan > left:
        LOG.warn(f"계획 호출({plan:,})이 오늘 잔여 한도({left:,})를 넘습니다 — 우선순위 상위부터 "
                 f"채우고 한도에서 멈춥니다. 커버리지는 재실행할 때마다 올라갑니다.")


# ── L1 수집 ─────────────────────────────────────────────────────────────────────────────────
def collect_all_v3(months: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}
    t_ing = time.time()
    announce_budget_v3()

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금 (다중소스 폴백 체인)", "L1", budget_s=2400):
        KRX.login()
        LOG.info(f"KRX 마켓플레이스 세션: {getattr(KRX, 'status', '미시도')}")
        # 야후 접미사를 미리 알려준다 — 모르면 종목당 .KS/.KQ 를 둘 다 때려 호출이 2배가 된다.
        try:
            _mk = ctx["sec"].dropna(subset=["code"]).drop_duplicates("code")
            _s = _mk["market"].astype(str).str.upper()
            YF_SUFFIX_HINT.update(dict(zip(
                _mk["code"].astype(str),
                np.where(_s.str.contains("KOSDAQ|KSQ|코스닥"), ".KQ", ".KS"))))
        except Exception:
            pass
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L0.CANARY", "CANARY K1~K9", "L0", budget_s=2100):
        ctx["canary"] = run_canary(ctx["sec"],
                                   canary_sample(ctx["sec"], ctx["panel"]["monthly"]))

    with PIPE.stage("L1.FLOW", "기관·외국인 수급 (U축 d3)", "L1", budget_s=1200, critical=False):
        ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(), BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.EMP", "DART 직원현황(확장) · C15 한계임금", "L1",
                    budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        eyears = list(range(as_ts(BACKTEST_START).year - EMP_YEARS_BACK,
                            as_ts(BACKTEST_END).year + 1))
        # ★ 한계임금이 이 전략의 알파 원천이므로 DART 일일예산을 **여기에 먼저** 배정한다.
        #   (Tier-2 전체재무제표는 남는 예산으로 채우고, 부족분은 Tier-1 주요계정이 받친다)
        emp_corps, _, emp_prio = dart_fs_scope_v3(ctx, corps, quiet=True)
        if not (EMP_UNIVERSE_ONLY and emp_corps):
            emp_corps = corps          # 축소 실패 또는 사용자가 끈 경우 → 전 종목
        else:
            LOG.info(f"직원현황 수집대상 {len(emp_corps):,}사 "
                     f"(전체 {len(corps):,}사 중 U-MID 대역을 한 번이라도 경험한 종목). "
                     f"셀 정규화도 U-MID 패널 안에서만 이뤄지므로 제외분은 스코어에 쓰이지 않습니다.")
        E = fetch_emp_status(emp_corps, eyears, priority=emp_prio, max_calls=EMP_MAX_CALLS)
        ctx["emp_raw"] = E
        S = build_emp_sensors(E)
        ctx["emp_sensors"] = S
        ok, msg = test_c15(S)
        (LOG.ok if ok else LOG.error)(f"C15 자가검정 — {msg}")
        if not ok and STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"C15 계약 위반: {msg}")
        if len(S):
            PIT.register("emp_sensors",
                         pit_frame(S, "period_end", "knowledge_date", source="dart"),
                         key_cols=["corp_code"])
            VAULT.put_table("emp_sensors_annual", S, scope="shared", domain="dart",
                            source="v3 EMP-LITE 연도 센서 (C15 적용) — 타 전략 재사용 가능")

    with PIPE.stage("L1.DART", "DART 재무 · 공시목록", "L1", budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        # ── Tier-1(배치): 전 종목 · 전 연도. 100사/호출이므로 싸다. 항상 전부 받는다.
        multi = fetch_dart_multi_accounts(corps, years)
        # ── Tier-2(단건): 기업×연도×보고서로 곱해진다 → 반드시 범위를 좁히고 상한을 건다.
        fs_corps, fs_years, prio = dart_fs_scope_v3(ctx, corps)
        fs = fetch_dart_financials(fs_corps, fs_years, priority=prio,
                                   max_calls=DART_FS_MAX_CALLS, freq=DART_FS_FREQ)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        dis = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["fin"], ctx["disclosures"] = fin, dis
        # ★ 빈 경로의 tidy_financials 는 PIT 컬럼조차 없는 3열짜리 프레임을 돌려준다.
        #   그대로 register 하면 KeyError 로 죽으므로 컬럼 존재를 먼저 확인한다.
        if len(fin) and all(c in fin.columns for c in PIT_COLS):
            PIT.register("dart_financials", fin, key_cols=["corp_code"])
        else:
            LOG.warn("DART 재무가 비어 PIT 등록을 건너뜁니다 — CORE-D TP 는 전부 결측이 됩니다.")

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장 구축", "L1",
                    budget_s=3600, critical=False):
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                     "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                     "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                frames.append(naver_enrich_detail(naver_collect(BACKTEST_START, BACKTEST_END)))
        if cached is not None and len(cached):
            LOG.ok(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 — 재수집하지 않습니다")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"]) if frames else pd.DataFrame()
        if len(rep):
            if RESEARCH_DOWNLOAD_PDF:
                rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
                if "pdf_target" in rep.columns:
                    fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                    if fill.any():
                        rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                        LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
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
        else:
            ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
            LOG.info("리포트 원장이 비었습니다 — U 는 스펙 §8 대로 d1·d3 로만 구성되므로 "
                     "전략 자체는 온전합니다(원장은 감사·공용재활용 목적).")

    runtime_mark("수집", time.time() - t_ing)
    return ctx


# ── L1 피처 ─────────────────────────────────────────────────────────────────────────────────
def build_features_v3(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe", dict]:
    t_l1 = time.time()
    with PIPE.stage("L1.PANEL", "피처 패널 조립 (L1 센서)", "L1", budget_s=1800):
        uni = Universe(ctx["sec"],
                       ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel_v3(uni, months, ctx["panel"]["monthly"])
        P = attach_pit_sources(P, ctx["sec"])
        P = apply_umid(P, uni)
        P = build_cells_v3(P, ctx["sec"])
        P = core_d_sensors(P, ctx)

        # §6 커버리지 감사 → 판정 → EMP 유효 시작월
        C = emp_coverage_audit(ctx.get("emp_sensors", pd.DataFrame()),
                               umid_by_year(P), umid_corps_by_year(P))
        emp_start, verdict = coverage_verdict(C)
        LOG.info(f"§6 판정 — {verdict}")
        ctx["emp_coverage"], ctx["emp_coverage_verdict"] = C, verdict

        P = emp_lite_sensors(P, emp_start)
        P = axis_U_v3(P, ctx.get("flows"))

        # ★ U-MID 밖은 여기서 제외한다. TP 랭크가 '고를 수 있었던 종목' 안에서 매겨져야 한다.
        #   (센서 계산은 전 종목으로 끝낸 뒤에 자른다 — 먼저 자르면 12개월 차분이 깨진다)
        before = len(P)
        P = P[P["u_mid"]].reset_index(drop=True)
        LOG.info(f"U-MID 유니버스로 스코어링 패널 확정 — {before:,} → {len(P):,}행")
        P = downcast_floats(P)
        LOG.ok(f"피처 패널 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 panel")
    runtime_mark("L1.센서+커버리지", time.time() - t_l1)
    return P, uni, ctx


def score_and_backtest_v3(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex,
                          uni: "Universe") -> Tuple[pd.DataFrame, dict, Callable]:
    t_l2 = time.time()
    with PIPE.stage("L2.SCORE", "TP 조립 · 거부권 · Signal", "L2", budget_s=300):
        P = build_tps(P)
        P = apply_vetoes_v3(P, ctx)
        P = assemble_score_v3(P)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        P[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "n_tp") if c in P.columns]],
                        scope="private", domain="scores", source="L2")

    def _run(pp, label="run", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else months,
                            uni, ctx["sec"], apply_costs=apply_costs, label=label)

    with PIPE.stage("L3.BT", "백테스트", "L3", budget_s=300):
        bt = _run(P, label=STRATEGY_ID)
    runtime_mark("L2+L3.백테스트", time.time() - t_l2)
    return P, bt, _run


# ── 산출물 ──────────────────────────────────────────────────────────────────────────────────
def persist_outputs_v3(P: pd.DataFrame, bt: dict, ctx: dict, bench: Dict[str, pd.Series],
                       t_all: float) -> List[str]:
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []

    def _w(fname: str, fn: Callable[[str], None]):
        p = os.path.join(outdir, fname)
        try:
            fn(p)
            outs.append(p)
        except Exception as e:                                    # noqa
            LOG.warn(f"산출물 저장 실패 {fname} ({type(e).__name__}: {e})")

    _w(f"canary_report_{stamp}.md", lambda p: atomic_write_text(p, canary_report_md()))
    _w(f"r2n_verdict_{stamp}.md", lambda p: atomic_write_text(p, r2n_verdict_md()))
    C = ctx.get("emp_coverage")
    if C is not None and len(C):
        _w(f"emp_coverage_{stamp}.csv",
           lambda p: C.to_csv(p, index=False, encoding="utf-8-sig"))
    cal = ctx.get("policy")
    if cal is not None and len(cal):
        _w(f"r10_policy_calendar_{stamp}.csv",
           lambda p: cal.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"returns_{stamp}.csv",
       lambda p: bt["returns"].to_csv(p, index=False, encoding="utf-8-sig"))
    if len(bt.get("holdings", pd.DataFrame())):
        _w(f"holdings_{stamp}.csv",
           lambda p: bt["holdings"].to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"panel_{stamp}.parquet", lambda p: atomic_write_parquet(P, p))

    full = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "window": [BACKTEST_START, BACKTEST_END],
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "performance": {k: (float(v) if isinstance(v, (int, float, np.floating)) and
                            np.isfinite(v) else None)
                        for k, v in (perf_stats(bt["returns"]) or {}).items()},
        "right_tail": {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v))
                       for k, v in (right_tail_contribution(bt) or {}).items()},
        "benchmarks": {},
        "canary": CANARY_RESULTS,
        "contracts": CONTRACT_V3,
        "robustness": ROBUST_V3,
        "r2n": R2N_VERDICT,
        "c15": C15_STATS,
        "coverage_verdict": ctx.get("emp_coverage_verdict", ""),
        "active_tp": globals().get("ACTIVE_TP_COLS", []),
        "runtime_minutes": (time.time() - t_all) / 60.0,
    }
    for name, s in (bench or {}).items():
        try:
            bs = perf_stats(pd.DataFrame({"month": s.index, "ret": s.to_numpy(dtype=float),
                                          "n": 0, "turnover": 0.0, "cost": 0.0}))
            full["benchmarks"][name] = {k: (float(v) if isinstance(v, (int, float, np.floating))
                                            and np.isfinite(v) else None)
                                        for k, v in bs.items()}
        except Exception:
            continue
    _w(f"backtest_full_{stamp}.json",
       lambda p: atomic_write_text(p, json.dumps(full, ensure_ascii=False, indent=2, default=str)))
    RT = report_runtime_v3(t_all)
    _w(f"runtime_{stamp}.csv", lambda p: RT.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"log_{stamp}.txt", lambda p: atomic_write_text(p, "\n".join(LOG.buffer)))

    VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                    domain="backtest", source=STRATEGY_ID)
    VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
    if DBUDGET:
        DBUDGET.close()
    VAULT.report()
    return outs


# ── main ────────────────────────────────────────────────────────────────────────────────────
def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["DART 키", "입력됨" if DART_API_KEY else "없음 (핵심 입력 — 넣으면 살아납니다)"],
               ["KRX 마켓플레이스", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW)
                else "없음 (가격은 pykrx→FDR→네이버→yfinance 체인으로 대체)"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    if pykrx_stock is None:
        LOG.warn(
            "pykrx 를 쓸 수 없습니다 — 결과에 실제로 영향이 갑니다. 두 가지가 죽습니다:\n"
            "     ① 기관·외국인 수급 → U축 d3 가 전 기간 결측 (U 는 d1 하나로만 구성됩니다)\n"
            "     ② 특정일 상장목록 스냅샷 → PIT 유니버스가 KIND·FDR 경로에만 의존합니다\n"
            "   가격 자체는 FDR→네이버→yfinance 로 대체되지만 3~4배 느립니다. "
            f"현재 파이썬 {ENV['python']} 에 설치 가능한 휠이 없으면 3.11~3.12 환경을 권합니다.")

    t_l0 = time.time()
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root, mode = mount_cache_v3()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        # 중복 경로를 미리 제거한다(ADOPT_DIRS[0] 이 ROOT 와 같으면 같은 트리를 두 번 훑는다)
        # ★ 헤더의 ADOPT 경로는 Colab 기준(/content/...)이라 JupyterLab 에서는 하나도 안 맞는다.
        #   실제로 붙어 있는 캐시 루트의 형제 폴더(research/reports/consensus)도 함께 훑어
        #   '드라이브에 이미 모아둔 리포트'를 어느 환경에서든 등록만 하고 재사용한다.
        _sib = os.path.dirname(VAULT.root)
        adopt = list(dict.fromkeys(os.path.abspath(os.path.expanduser(d)) for d in (
            list(GDRIVE_ADOPT_DIRS) + [VAULT.root] +
            [os.path.join(_sib, n) for n in ("research", "reports", "consensus", "tcd_cache")]
        ) if d))
        adopt = [d for d in adopt if os.path.isdir(d)]
        VAULT.adopt_scan(adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 (C1·C2·C13·C15 · 원칙1~7)", "L0", budget_s=180):
        run_contracts_v3(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest_v3(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=900):
        run_rehearsal(strict=True)
    runtime_mark("L0.준비", time.time() - t_l0)

    months = month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_flow(); report_runtime_v3(t_all)
        report_dataflow_map_v3()
        return {"mode": "SMOKE"}

    ctx = collect_all_v3(months)

    with PIPE.stage("L1.AUDIT", "다중소스 원장 연결 감사", "L1", budget_s=180, critical=False):
        report_ledger_v3(ctx)

    P, uni, ctx = build_features_v3(ctx, months)
    P, bt, _run = score_and_backtest_v3(P, ctx, months, uni)

    with PIPE.stage("L2.POLICY", "정책 캘린더", "L2", budget_s=60, critical=False):
        cal = build_policy_calendar_v3()
        report_policy_v3(cal, months)
        ctx["policy"] = cal

    bench: Dict[str, pd.Series] = {}
    with PIPE.stage("L6.PERF", "성과 검증 (자체측정 벤치마크 대비)", "L6", budget_s=300):
        bench = R0_benchmark(P, bt, months)
        report_performance_v3(bt, bench)
        # ★ 감쇠 감사는 강건성 재실행(백테스트 10여 회)이 섞이기 전에 뽑는다.
        uni.report_attrition()
        uni.attrition = []

    t_rob = time.time()
    with PIPE.stage("L5.ROBUST", "강건성 검사", "L5", budget_s=3 * 3600, critical=False):
        try:
            R1_leakage(P, months, _run)
            R2N_kill_gate(P, _run)
            R3_orthogonal(P, _run)
            R5_ablation(P, _run)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R10_policy_falsify(P, ctx.get("policy", build_policy_calendar_v3()), months, _run)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness_v3()
    runtime_mark("R-SUITE", time.time() - t_rob)

    with PIPE.stage("L6.REPORT", "해석표 · 진단 카드", "L6", budget_s=300, critical=False):
        report_interpretation_v3(P)
        diagnostic_card_v3(P, bt, ctx["sec"])

    outs: List[str] = []
    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = persist_outputs_v3(P, bt, ctx, bench, t_all)
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    report_dataflow_map_v3()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시 — ① 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 U축 d1 의 E 는 "
             "후행 12M 순이익 대리를 씁니다. ② U-MID 의 규모 랭크는 시가총액이 아니라 20일 "
             "평균거래대금 랭크입니다(시총 PIT 복원 불가에 따른 치환). ③ empSttus 는 별도 기준에 "
             "가까우므로 1인당 부가가치의 분자도 별도(OFS) 우선으로 맞췄으나, 연결 비중이 큰 "
             "지주회사에서는 오차가 큽니다. 숨기지 않고 여기에 명시합니다.")
    offer_download_v3(outs)
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_V3, "r2n": R2N_VERDICT}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§12 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        try:
            report_robustness_v3()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 정확히 이 지점부터 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
