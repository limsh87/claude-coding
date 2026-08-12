# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §9 실행 순서 — Step 0 ~ Step 9                                                           ║
# ║  각 Step 완료 시 중간 산출물을 저장하고, 다음 Step 은 이전 결과를 보지 않은 상태에서        ║
# ║  명세대로만 실행한다.                                                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

AMENDMENTS: List[str] = []
FWD_GLOBAL: Optional[pd.DataFrame] = None


def _prep_dirs():
    global CACHE_DIR, LOG_DIR, OUTPUT_DIR
    base = os.path.expanduser(BASE_DIR)
    if not _can_write(base):
        base = os.path.abspath("./u250_factor_test")
        LOG.warn(f"BASE_DIR({BASE_DIR}) 에 쓸 수 없어 {base} 로 대체합니다 "
                 f"(윈도우 경로를 다른 OS 에서 실행한 경우 정상입니다).")
    CACHE_DIR = CACHE_DIR or os.path.join(base, "cache")
    LOG_DIR = LOG_DIR or os.path.join(base, "logs")
    OUTPUT_DIR = OUTPUT_DIR or os.path.join(base, "outputs")
    for p in (base, CACHE_DIR, LOG_DIR, OUTPUT_DIR):
        os.makedirs(p, exist_ok=True)
    LOG.info(f"산출물 루트 {base}")


def _can_write(p: str) -> bool:
    try:
        os.makedirs(p, exist_ok=True)
        t = os.path.join(p, ".wtest")
        open(t, "w").close()
        os.remove(t)
        return True
    except Exception:
        return False


def _load_all() -> dict:
    """캐시에서 전부 꺼낸다. 하나라도 없으면 그 사실을 남기고 SMOKE 합성으로 대체한다."""
    if RUN_MODE == "SMOKE":
        LOG.warn("RUN_MODE=SMOKE — 합성데이터로 계산경로만 증명합니다. "
                 "이 결과는 알파 판정이 아닙니다(신호를 수익률과 독립으로 뿌렸으므로 "
                 "전 팩터 G1~G7 미달이 정상입니다).")
        return synth_dataset()
    try:
        px = load_price()
        sec = load_sec_master()
        fin = load_financials()
    except StageFailure as e:
        LOG.error(str(e))
        LOG.warn("실데이터를 조립하지 못해 SMOKE 합성으로 전환합니다 — "
                 "산출물 구조는 동일하나 수치는 무의미합니다.")
        RUNLOG["fallback_to_synth"] = str(e)
        return synth_dataset()
    return {"price": px, "sec": sec, "fin": fin, "cap_events": None,
            "insider": None, "contracts": None}


def run_all():
    t0 = time.time()
    LOG.banner(STRATEGY_NAME, f"명세 v{SPEC_VERSION} · 사전등록 해시 {spec_sha256()[:16]} · "
                              f"빌드 {BUILD_VERSION}")
    RUNLOG.update(spec_sha256=spec_sha256(), spec_version=SPEC_VERSION, run_mode=RUN_MODE,
                  rebal_freq_list=list(REBAL_FREQ_LIST), collect_policy=COLLECT_POLICY,
                  seed=SEED, started=_dt.datetime.now().isoformat(timespec="seconds"))

    AMENDMENTS.extend([
        "§1 은 리밸런싱을 '기존 구현과 동일 주기 유지'라고만 하고 원본(KR_QUANT_SUITE_V1.py)이 "
        "실행 환경에 없어 주기를 특정할 수 없었다. 주간·월간·분기 셋을 전부 산출하고, "
        "주기를 고를 근거가 없으므로 '셋 전부에서 G1~G7 통과'를 유효 조건으로 삼았다. "
        "하나에서만 통과하는 것은 팩터가 아니라 주기 선택에 기댄 결과로 본다.",
        "위 주기 축이 늘어난 만큼 실제 시행수는 120 × 3 = 360 이다. G5 판정은 사전등록대로 "
        "120 으로 하되, 360 기준 SR−SR₀ 를 비고에 함께 남겼다(§8-3 준수, 다만 다중검정 "
        "통제의 취지상 360 쪽이 실질에 가깝다).",
        "§2 의 B4 정의('U250 내 무작위 N종목 EW')는 매 리밸런싱마다 새로 뽑는지, 뽑은 뒤 "
        "보유하는지를 명시하지 않는다. 코드는 문자 그대로 '매 리밸 새로 추출'로 구현했고 G1 "
        "판정도 그 분포로만 한다. 다만 그 경우 귀무 포트폴리오 회전율이 100%에 가까워져 "
        "비용 차가 선별력과 섞이므로, 팩터의 실현 회전율에 맞춘 귀무분포를 '진단'으로 "
        "함께 산출해 G1 비고란에 남겼다(판정에는 쓰지 않음).",
        "§6.2 의 시행수 계산 120 = 4팩터×5×N3×2 는 F1(필터형)에 N 차원이 없다는 점을 "
        "반영하지 않는다. DSR 은 명세대로 120 을 그대로 썼다(실제보다 큰 시행수는 보수적 "
        "방향이므로 결론을 유리하게 만들지 않는다).",
        "§6.3 G5 의 'DSR > 0' 은 DSR 을 확률로 정의하면 항상 참이라 사실상 비구속 조건이다. "
        "코드는 명세대로 판정하되, 실질 판정에 해당하는 SR > SR₀ 결과를 비고란에 남겼다. "
        "임계 변경은 명세 개정 사항이므로 코드에서 바꾸지 않았다.",
    ])

    # ── Step 0. 캐시 하베스트 (주기와 무관 — 한 번만) ─────────────────────────────────
    _prep_dirs()
    global VAULT
    VAULT = Vault(*_mount_drive())
    LOG.info(f"캐시 볼트 {VAULT.root} [{VAULT.mode}]")
    if RUN_MODE != "SMOKE":
        LAKE.harvest()
    gate_crosscheck()
    if RUN_MODE == "CACHED":
        globals()["COLLECT_POLICY"] = "NEVER"
    verify_dart_endpoints()
    if RUN_MODE == "SCAN":
        scan_report()
        return

    D = _load_all()
    with PIPE.stage("L1.PANEL", "패널 조립 (주기 무관)", "L1", budget_s=1800):
        daily = build_daily_panel(D["price"])
        if PANEL_START:
            daily = daily[daily["date"] >= as_ts(PANEL_START)]
        if PANEL_END:
            daily = daily[daily["date"] <= as_ts(PANEL_END)]
        sec, fin = D["sec"], D["fin"]
        RUNLOG["panel"] = dict(codes=int(daily["code"].nunique()), rows=int(len(daily)),
                               start=str(daily["date"].min().date()),
                               end=str(daily["date"].max().date()))
        #   스프레드 실측과 DART 원천은 리밸 주기와 무관하다 — 세 번 만들 이유가 없다.
        cs = corwin_schultz_spread(daily)
        start, end = daily["date"].min(), daily["date"].max()
        codes = sorted(daily["code"].astype(str).unique())
        src = {
            "F1": D["cap_events"] if D["cap_events"] is not None else load_capital_events(codes, start, end),
            "F2": D["insider"] if D["insider"] is not None else load_insider(codes, start, end),
            "F4": D["contracts"] if D["contracts"] is not None else load_contracts(codes, start, end),
        }

    # ── 주기별 전체 검정 (§1 주기를 특정할 수 없어 셋을 모두 돌린다) ──────────────────
    ALL: Dict[str, dict] = {}
    for freq in REBAL_FREQ_LIST:
        globals()["REBAL_FREQ"] = freq
        globals()["_SUBDIR"] = freq_tag(freq)
        globals()["SEAL"] = OOSSeal()
        LOG.banner(f"리밸런싱 {freq_kr(freq)} ({freq})",
                   f"세금·수수료·스프레드·시장충격·슬리피지를 전부 차감한 순수익으로만 판정합니다 "
                   f"· 산출물 → outputs/{freq_tag(freq)}/")
        ALL[freq] = run_one_frequency(daily, sec, fin, cs, src, codes)

    # ── 통합 스코어카드 ───────────────────────────────────────────────────────────────
    globals()["_SUBDIR"] = ""
    write_md(_out("MASTER_SCORECARD.md"), master_scorecard_multi(ALL, AMENDMENTS))
    RUNLOG["elapsed_s"] = round(time.time() - t0, 1)
    atomic_write_text(os.path.join(LOG_DIR, f"run_log_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"),
                      json.dumps(RUNLOG, ensure_ascii=False, indent=2, default=str))
    VAULT.flush()
    DARTB.close()
    PIPE.report_stages()
    PIPE.report_flow()
    report_http()
    PIPE.report_runtime()
    VAULT.report()
    LOG.banner("완료", f"{OUTPUT_DIR} · {RUNLOG['elapsed_s']}초 · "
                       f"MASTER_SCORECARD.md 를 먼저 보세요")


ROLE_NEED = [
    ("price_daily", "일별 가격·거래대금", True,
     "없으면 아무것도 못 한다. 이전 프로젝트의 OHLCV parquet/csv 폴더를 CACHE_SEARCH_DIRS 에 추가"),
    ("mktcap_daily", "일별 시가총액", False,
     "가격 테이블에 시총·상장주식수가 있으면 불필요"),
    ("sec_master", "종목마스터(상장일·폐지일)", True,
     "폐지일이 없으면 생존자편향. 없으면 깃허브 FDR 캐시에서 자동 보충"),
    ("financials", "재무(매출·자본총계·자본금)", True,
     "자본잠식·재무결측 게이트의 입력. dart_fin 원시 계정표도 가능"),
    ("dart_fin", "DART 원시 계정표", False, "financials 가 없을 때의 대체 입력"),
    ("corp_map", "corp_code ↔ 종목코드", False, "DART 계열 데이터를 종목에 붙이는 데 필요"),
    ("dart_disclosure", "공시목록", False, "F1 자본거래 이벤트의 원천"),
    ("dart_insider", "임원·주요주주 지분공시", False, "F2 의 원천. 없으면 F2 는 Phase 0 보류"),
    ("dart_contract", "단일판매·공급계약", False, "F4 의 원천. 없으면 F4 는 Phase 0 보류"),
]


def scan_report():
    """RUN_MODE='SCAN' — 캐시 발굴 결과만 보고 끝낸다. 전체 실행 전 경로 점검용."""
    rows = []
    for role, label, required, hint in ROLE_NEED:
        items = [i for i in LAKE.items if i.role == role]
        n = len(items)
        rows.append([label, role, f"{n:,}" if n else "—",
                     f"{sum(max(i.rows, 0) for i in items):,}" if n else "—",
                     ("✔ 있음" if n else ("✘ 없음(필수)" if required else "— 없음(선택)")),
                     "" if n else hint])
    LOG.table(rows, ["데이터", "역할키", "파일", "행수(추정)", "상태", "없을 때"],
              ["l", "l", "r", "r", "c", "l"], title="★ 역할별 캐시 확보 현황")
    miss = [r[0] for r in rows if r[4].startswith("✘")]
    if miss:
        LOG.warn(f"필수 데이터 미확보: {', '.join(miss)} — 이대로 FULL 을 돌리면 합성데이터로 "
                 f"폴백하거나 신규 수집(수 시간)에 들어갑니다. 경로를 먼저 잡으세요.")
        if LAKE.rejected:
            LOG.info("판별 실패한 파일 예시 — 컬럼명이 별칭표에 없으면 여기 뜹니다 "
                     "(ALIAS 에 이름을 추가하면 즉시 인식됩니다):")
            for pth, cols in LAKE.rejected[:12]:
                LOG.info(f"    {os.path.basename(pth)} → {cols}")
    else:
        LOG.ok("필수 데이터가 전부 캐시에 있습니다. RUN_MODE 를 'CACHED' 로 두면 "
               "네트워크 없이 전체 검정이 돕니다.")
    if LAKE.roots_used:
        LOG.table([[k, p] for p, k in LAKE.roots_used], ["출처", "스캔 루트"], ["l", "l"],
                  title="스캔한 경로")
    write_xlsx(_out("cache_scan_report.xlsx"), {
        "역할별_현황": pd.DataFrame(rows, columns=["데이터", "역할키", "파일", "행수", "상태", "없을때"]),
        "채택_파일": pd.DataFrame([{"역할": i.role, "출처": i.origin, "점수": i.score,
                                  "행수": i.rows, "경로": i.path, "테이블": i.sub}
                                 for i in LAKE.items]),
        "판별실패_예시": pd.DataFrame([{"파일": p, "컬럼": ", ".join(map(str, c))}
                                    for p, c in LAKE.rejected[:500]]),
    })


def run_one_frequency(daily, sec, fin, cs, src, codes) -> dict:
    """한 리밸런싱 주기에 대해 Step 1~9 를 명세대로 끝까지."""
    global FWD_GLOBAL
    tag = freq_tag()
    with PIPE.stage(f"L1.{tag}", f"유니버스 ({freq_kr()})", "L1", budget_s=900):
        rebals = rebalance_dates(pd.DatetimeIndex(daily["date"].unique()))
        SEAL.set_boundary(rebals)
        elig = build_eligibility(daily, sec, fin, rebals)
        univ = build_universe(elig)

    with PIPE.stage(f"L2.{tag}", f"비용 모형 · 수익률 행렬 ({freq_kr()})", "L2", budget_s=900):
        FWD, DEL = build_forward_returns(daily, rebals, sec)
        FWD_GLOBAL = FWD
        spread_map = ({t: g.set_index("code")["spread_cs"]
                       for t, g in cs[cs["date"].isin(rebals)].groupby("date", observed=True)}
                      if len(cs) else {})
        adv_map = {t: g.set_index("code")["adv20_mean"]
                   for t, g in univ.groupby("rebal", observed=True)}
        qmap = {}
        for t, g in univ.groupby("rebal", observed=True):
            try:
                q = pd.qcut(g["market_cap"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
                qmap[t] = pd.Series(q.astype(int).values, index=g["code"].astype(str).values)
            except (ValueError, IndexError):
                qmap[t] = pd.Series(1, index=g["code"].astype(str).values)
        cost = CostModel(spread_map=spread_map,
                         market_map=sec.drop_duplicates("code").set_index("code").get("market"),
                         cap_quintile=qmap, adv=adv_map)
        eng = Engine(rebals, FWD, cost, DEL)
        ppy = eng.ppy
        univ_by_t = {t: list(g["code"]) for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}

    # ── Step 1. Phase 0 ───────────────────────────────────────────────────────────────
    with PIPE.stage(f"S1.{tag}", f"Phase 0 커버리지 진단 ({freq_kr()})", "L3", budget_s=1800):
        prim = {
            "F1": build_F1(src["F1"], rebals, univ_by_t, daily, "primary", {}),
            "F2": build_F2(src["F2"], rebals, univ_by_t, univ, "primary", {}),
            "F3": build_F3(daily, rebals, univ_by_t, "primary", {}),
            "F4": build_F4(src["F4"], fin, rebals, univ_by_t, "primary", {}),
        }
        covs = {}
        for f in ("F1", "F2", "F3", "F4"):
            c = coverage_diag(f, prim[f].obs, prim[f].sig, univ, rebals, codes)
            coverage_bias(c, univ, sec)
            covs[f] = c

    # ── Step 2. 베이스라인 ────────────────────────────────────────────────────────────
    with PIPE.stage(f"S2.{tag}", f"베이스라인 B1~B4 ({freq_kr()})", "L3", budget_s=3600):
        base = run_baselines(eng, univ, elig, "IS")
        LOG.table([[k, f"{r.stats(ppy)['cagr']:.2%}", f"{r.stats(ppy)['mdd']:.1%}",
                    f"{r.stats(ppy)['vol']:.1%}", f"{r.stats(ppy)['turnover']:.1f}x",
                    f"{r.stats(ppy)['cost']:.3f}"] for k, r in base.items()],
                  ["베이스라인", "CAGR", "MDD", "변동성", "연회전율", "누적비용"],
                  ["l", "r", "r", "r", "r", "r"],
                  title=f"§2 베이스라인 (IS · {freq_kr()} · B2~B4 는 전부 순수익)")
        nulls = {n: random_null(eng, univ, n, SPEC_B4_SIMS, "IS") for n in SPEC_N_VALUES}
        b_cov = {}
        for f, c in covs.items():
            if c.median_cov <= 0:
                continue
            b_cov[f] = Engine(_window_rebals(rebals, "IS"), FWD, cost, DEL).run(
                lambda t, cc=c: [x for x in univ_by_t.get(t, []) if x in cc.covered_codes.get(t, set())],
                f"B_cov[{f}]")
        baseline_report(base, nulls, ppy)
        phase0_report(covs, b_cov, ppy, base.get("B2"))

    # ── Step 3~6. 팩터 ────────────────────────────────────────────────────────────────
    FR: Dict[str, dict] = {}
    for f in ("F1", "F2", "F3", "F4"):
        with PIPE.stage(f"S{2+int(f[1])}.{tag}.{f}", f"{f} 단독 백테스트 (IS · {freq_kr()})",
                        "L3", budget_s=3600):
            FR[f] = run_factor(f, src, daily, fin, rebals, univ, univ_by_t, sec,
                               eng, base, nulls, covs[f], b_cov.get(f), ppy)

    # ── Step 7. OOS ───────────────────────────────────────────────────────────────────
    with PIPE.stage(f"S7.{tag}", f"OOS 개봉 → G4 ({freq_kr()})", "L3", budget_s=3600):
        ok = [f for f, r in FR.items()
              if r.get("sel_primary") and r.get("gates")
              and all(g.passed is not False for g in r["gates"] if g.gate in ("G1", "G2", "G3"))]
        LOG.info(f"IS 에서 G1·G2·G3 를 하나도 실패하지 않은 팩터: {ok or '없음'}")
        SEAL.open(f"Step 7 — IS 확정 후 개봉 (대상 {ok or '없음'})")
        base_oos = run_baselines(eng, univ, elig, "OOS")
        for f in ok:
            r = FR[f]
            res = Engine(_window_rebals(rebals, "OOS"), FWD, cost, DEL).run(
                r["sel_primary"], f"{f} OOS")
            r["oos"] = res
            r["excess"]["oos"] = excess_cagr(res, base_oos["B2"], ppy)
            r["gates"].append(gate_G4(r["excess"].get("is", np.nan), r["excess"]["oos"]))
        for f in FR:
            if f not in ok:
                FR[f]["gates"].append(GateResult(
                    "G4", None, "—", f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}",
                    "IS 미통과 — OOS 미개봉(§9 Step 7)"))

    # ── Step 8. DSR / PBO ─────────────────────────────────────────────────────────────
    with PIPE.stage(f"S8.{tag}", f"다중검정 DSR/PBO ({freq_kr()})", "L3", budget_s=1200):
        n_adj = SPEC_TRIALS_TOTAL * len(REBAL_FREQ_LIST)
        for f, r in FR.items():
            if r.get("primary") is None:
                r["gates"].append(GateResult("G5", None, "—", "DSR>0 · PBO<0.5", "백테스트 미실행"))
                continue
            d = deflated_sharpe(r["primary"].ret, SPEC_TRIALS_TOTAL, ppy)
            d_adj = deflated_sharpe(r["primary"].ret, n_adj, ppy)
            grid = pd.DataFrame({k: v.ret for k, v in r["grid"].items()}) if r.get("grid") else pd.DataFrame()
            p = pbo_cscv(grid) if len(grid.columns) >= 2 else dict(pbo=np.nan)
            r["dsr"], r["dsr_adj"], r["pbo"] = d, d_adj, p
            g = gate_G5(d, p)
            #   판정은 사전등록대로 시행수 120 으로 한다. 주기 축이 늘어난 만큼의
            #   보정치(360)는 '보이게' 남기되 게이트를 바꾸지 않는다(§8-3).
            g.note += (f" · 주기축 반영 시행수 {n_adj} 기준 SR−SR₀ "
                       f"{d_adj.get('excess', float('nan')):+.4f}")
            r["gates"].append(g)
            LOG.info(f"[{f}] SR {d['sr']:.3f} · SR₀ {d['sr0']:.3f} · DSR {d['dsr']:.3f} · "
                     f"PBO {p.get('pbo', float('nan')):.3f} (격자 {p.get('K', 0)}개)")

    # ── Step 9. 용량 ──────────────────────────────────────────────────────────────────
    with PIPE.stage(f"S9.{tag}", f"용량 시뮬레이션 ({freq_kr()})", "L3", budget_s=3600):
        cap_rows = []
        targets = [("B2 U250 EW", lambda t: univ_by_t.get(t, []))]
        targets += [(f"{f} 주명세", FR[f]["sel_primary"]) for f in FR if FR[f].get("sel_primary")]
        e_is = Engine(_window_rebals(rebals, "IS"), FWD, cost, DEL)
        for name, sel in targets:
            row = {"전략": name}
            for a in SPEC_AUM_LADDER:
                row[str(a)] = e_is.run(sel, name, aum0=a).stats(ppy)["cagr"]
            row["dynamic"] = e_is.run(sel, name, aum0=SPEC_GATE["g2_aum_krw"],
                                      dynamic_aum=True).stats(ppy)["cagr"]
            cap_rows.append(row)
            for f in FR:
                if FR[f].get("sel_primary") is sel:
                    FR[f]["excess"]["dyn"] = row["dynamic"] - cap_rows[0]["dynamic"]
        capacity = pd.DataFrame(cap_rows)
        write_xlsx(_out("capacity_curves.xlsx"), {"AUM별_CAGR": capacity})
        cost.report()

    all_gates = {f: r["gates"] for f, r in FR.items()}
    excess = {f: r["excess"] for f, r in FR.items()}
    rejects = {f: r["reject_reason"] for f, r in FR.items() if r.get("reject_reason")}
    for f, r in FR.items():
        write_md(_out(FACTOR_DIR[f], f"{f}_gate_scorecard.md"),
                 gate_scorecard_md(f, r["gates"], r["head"]))
    write_md(_out("MASTER_SCORECARD.md"),
             master_scorecard(all_gates, excess, covs, capacity, AMENDMENTS, rejects))
    RUNLOG.setdefault("by_freq", {})[freq_tag()] = dict(
        rebals=int(len(rebals)), b2_cagr=float(base["B2"].stats(ppy)["cagr"]),
        b2_turnover=float(base["B2"].stats(ppy)["turnover"]),
        excess={f: excess[f].get("is") for f in excess})
    return dict(gates=all_gates, excess=excess, covs=covs, capacity=capacity,
                rejects=rejects, base=base, ppy=ppy, freq=REBAL_FREQ)


def run_factor(f: str, src: dict, daily, fin, rebals, univ, univ_by_t, sec,
               eng: Engine, base: Dict[str, BTResult], nulls: dict, cov: Coverage,
               bcov: Optional[BTResult], ppy: float) -> dict:
    """팩터 하나를 명세대로 끝까지 — 격자 30종 + 게이트 + 필수 부가 산출."""
    meta = FACTOR_META[f]
    out = dict(gates=[], grid={}, excess={}, head={}, primary=None, sel_primary=None)
    if not cov.proceed:
        LOG.warn(f"[{f}] cov_universe_rebal 중앙값 {cov.median_cov:.0f} < "
                 f"{SPEC_COV['hold_median']} → §6.4 조기 중단. 백테스트를 실행하지 않습니다.")
        out["head"] = {"판정": f"HOLD — 커버리지 중앙값 {cov.median_cov:.0f}종목",
                       "사유": "팩터가 아니라 별도 소형 유니버스로 재정의해야 하므로 본 명세 범위 밖"}
        for g in ("G1", "G2", "G3", "G5", "G6", "G7"):
            out["gates"].append(GateResult(g, None, "—", "—", "Phase 0 보류로 미실행"))
        write_xlsx(_out(FACTOR_DIR[f], f"{f}_results.xlsx"),
                   {"보류": pd.DataFrame([{"팩터": f, "판정": "HOLD",
                                          "cov_universe_rebal_중앙값": cov.median_cov}])})
        return out

    e_is = Engine(_window_rebals(rebals, "IS"), FWD_GLOBAL, eng.cost, eng.delist)
    builders = {
        "F1": lambda v, ov: build_F1(src["F1"], rebals, univ_by_t, daily, v, ov),
        "F2": lambda v, ov: build_F2(src["F2"], rebals, univ_by_t, univ, v, ov),
        "F3": lambda v, ov: build_F3(daily, rebals, univ_by_t, v, ov),
        "F4": lambda v, ov: build_F4(src["F4"], fin, rebals, univ_by_t, v, ov),
    }[f]
    variants = SENS.all_variants(f)
    rows = []
    for var in variants:
        fs = builders(var["key"], var["override"])
        n_list = SPEC_N_VALUES if fs.kind != "filter" else (SPEC_N_PRIMARY,)
        for n in n_list:
            for uc in SPEC_UNCOV_MODES:
                sel = fs.selector(univ_by_t, None if fs.kind == "filter" else n, uc)
                key = f"{var['key']}|N{n}|{uc}"
                res = e_is.run(sel, f"{f} {key}")
                out["grid"][key] = res
                rows.append({**perf_row(key, res, ppy, base["B2"]),
                             "변형": var["desc"], "N": n, "미커버처리": uc,
                             "신호셀": int(len(fs.sig)), "비고": fs.note})
                if var["key"] == "primary" and n == SPEC_N_PRIMARY and uc == "neutral":
                    out["primary"], out["sel_primary"], out["fs_primary"] = res, sel, fs
    if out["primary"] is None:
        out["primary"] = list(out["grid"].values())[0]
        out["sel_primary"] = None
    LOG.table([[r["전략"], f"{r['CAGR']:.2%}", f"{r.get('초과CAGR(vs B2)', float('nan')):+.2%}p",
                f"{r['MDD']:.1%}", f"{r['연회전율']:.1f}x"] for r in rows[:12]],
              ["격자", "CAGR", "vs B2", "MDD", "회전율"], ["l", "r", "r", "r", "r"],
              title=f"[{f}] 민감도 격자 (상위 12행 / 총 {len(rows)}행)")

    prim, fsp = out["primary"], out.get("fs_primary")
    out["excess"]["is"] = excess_cagr(prim, base["B2"], ppy)
    if bcov is not None:
        out["excess"]["bcov"] = excess_cagr(prim, bcov, ppy)

    # ── 게이트 ────────────────────────────────────────────────────────────────────────
    null = nulls.get(SPEC_N_PRIMARY)
    g1 = gate_G1(prim, null, ppy)
    #   ★ 진단(게이트 아님): 무작위 귀무분포는 매 리밸 새로 뽑으므로 회전율이 100%에 가깝고,
    #     그 비용 차가 스프레드에 섞인다. 팩터의 실현 회전율에 맞춘 귀무분포를 함께 만들어
    #     "G1 통과가 선별력 때문인지 회전율 차이 때문인지"를 구분할 수 있게 남긴다.
    #     사전등록된 G1 판정 자체는 명세대로 literal B4 로만 한다(§8-3).
    tv = float(prim.turnover.mean()) if len(prim.turnover) else np.nan
    null_m = (random_null(eng, univ, SPEC_N_PRIMARY, sims=200, window="IS",
                          match_turnover=tv) if np.isfinite(tv) else None)
    if null_m is not None and len(null_m.get("cagr", [])):
        c = prim.stats(ppy)["cagr"]
        g1.note = (f"회전율 정합 귀무분포(진단, 200회, 회전율 {tv:.1%}/리밸) p95 = "
                   f"{null_m['p95']:.2%} → {'초과' if c > null_m['p95'] else '미달'}")
        out["null_matched"] = null_m
    out["gates"].append(g1)
    out["gates"].append(gate_G2(prim, base["B2"], ppy))
    out["gates"].append(gate_G3(prim, base["B2"]))
    quint = {}
    if fsp is not None and fsp.kind != "filter" and len(fsp.sig):
        quint = _quintiles(fsp, univ_by_t, e_is, f)
    out["gates"].append(gate_G6(quint, fsp.kind if fsp else "rank", ppy))
    p1 = p2 = p3 = np.nan
    if fsp is not None and len(fsp.sig):
        n_or_none = None if fsp.kind == "filter" else SPEC_N_PRIMARY
        r1 = e_is.run(placebo_shift(fsp, rebals).selector(univ_by_t, n_or_none, "neutral"), f"{f}|P1")
        r2 = e_is.run(placebo_shuffle(fsp, univ_by_t).selector(univ_by_t, n_or_none, "neutral"), f"{f}|P2")
        pm = placebo_matched(fsp, univ, sec)
        r3 = e_is.run(pm.selector(univ_by_t, n_or_none, "neutral"), f"{f}|P3")
        p1 = excess_cagr(r1, base["B2"], ppy)
        p2 = excess_cagr(r2, base["B2"], ppy)
        p3 = prim.stats(ppy)["cagr"] - r3.stats(ppy)["cagr"]
    out["gates"].append(gate_G7(p1, p2, p3, out["excess"]["is"]))

    # ── §4 F3 중복성 검사 (필수) — 이 검사만으로 팩터가 기각될 수 있다 ────────────────
    if f == "F3" and fsp is not None and len(fsp.sig):
        red = f3_redundancy(daily, fsp.sig, rebals)
        mn_sel = f3_momentum_neutral_selector(fsp, univ_by_t, daily, rebals, SPEC_N_PRIMARY)
        r_mn = e_is.run(mn_sel, "F3 모멘텀중립(이중정렬)")
        x_mn = excess_cagr(r_mn, base["B2"], ppy)
        red["excess_mom_neutral"] = x_mn
        red["reject"] = bool(red["reject"] or x_mn <= 0)
        out["redundancy"] = red
        LOG.info(f"[F3] 모멘텀 통제(이중정렬) 후 초과수익 {x_mn:+.2%}p — "
                 f"{'소멸 → F3 기각' if x_mn <= 0 else '잔존'}")
        if red["reject"]:
            out["reject_reason"] = (
                f"중복성 검사 기각 — |ρ_모멘텀|={abs(red['rho_mom']):.2f}, "
                f"|ρ_반전|={abs(red['rho_rev']):.2f} (기준 {SPEC_F3['redundancy_rho']}), "
                f"모멘텀 통제 후 초과수익 {x_mn:+.2%}p")
            LOG.warn(f"[F3] {out['reject_reason']} → 다른 게이트 결과와 무관하게 무효입니다(§4 F3).")
        sheets_red = pd.DataFrame([red])
    else:
        sheets_red = None
    out["head"] = {"커버리지 판정": f"{cov.verdict} (중앙 {cov.median_cov:.0f}종목)",
                   "주명세 CAGR": f"{prim.stats(ppy)['cagr']:.2%}",
                   "B2 대비 초과": f"{out['excess']['is']:+.2%}p",
                   "B_cov 대비 초과": (f"{out['excess']['bcov']:+.2%}p"
                                       if "bcov" in out["excess"] else "—"),
                   "격자 수": len(out["grid"])}

    if out.get("null_matched") is not None:
        nm = out["null_matched"]["cagr"]
        sheets_null = pd.DataFrame([{"귀무분포": "literal B4 (매 리밸 재추출)",
                                     "중앙 CAGR": float(np.median(null["cagr"])) if null and len(null["cagr"]) else np.nan,
                                     "p95": null["p95"] if null else np.nan},
                                    {"귀무분포": f"회전율 정합 (진단, {tv:.1%}/리밸)",
                                     "중앙 CAGR": float(np.median(nm)), "p95": float(np.quantile(nm, .95))}])
    else:
        sheets_null = None
    sheets = {"격자결과": pd.DataFrame(rows),
              "B4_귀무분포_비교": sheets_null,
              "F3_중복성검사": sheets_red,
              "연도별": yearly_table({"주명세": prim, "B2": base["B2"]}),
              "플라시보": pd.DataFrame([{"P1(−60영업일)": p1, "P2(라벨셔플)": p2,
                                       "P3(매칭대조군 대비)": p3}])}
    if quint:
        sheets["5분위"] = pd.DataFrame([perf_row(f"Q{q}", r, ppy, base["B2"])
                                       for q, r in sorted(quint.items(), reverse=True)])
    sheets.update(_factor_extras(f, src, fsp, univ, univ_by_t, sec, e_is, base, ppy, fin, rebals, daily))
    write_xlsx(_out(FACTOR_DIR[f], f"{f}_results.xlsx"), sheets)
    return out


def _quintiles(fs: FactorSignal, univ_by_t, e_is: Engine, f: str) -> Dict[int, BTResult]:
    """G6 단조성 — 신호 점수 5분위. 상위→하위 단조 감소해야 한다."""
    sig_by_t = {t: g for t, g in fs.sig.groupby("rebal", observed=True)}
    out = {}
    for q in range(1, 6):
        def sel(t, q=q):
            g = sig_by_t.get(t)
            if g is None or len(g) < 10:
                return []
            s = g.set_index("code")["score"].sort_values()
            cand = [c for c in s.index if c in set(univ_by_t.get(t, []))]
            if len(cand) < 10:
                return []
            s = s.reindex(cand).dropna()
            k = len(s)
            lo, hi = int((q - 1) * k / 5), int(q * k / 5)
            return list(s.index[lo:hi])
        out[q] = e_is.run(sel, f"{f} Q{q}")
    return out


def _factor_extras(f, src, fsp, univ, univ_by_t, sec, e_is, base, ppy, fin, rebals, daily) -> dict:
    """§4 팩터별 '필수 부가 산출'."""
    ex = {}
    if f == "F1" and fsp is not None:
        cnt = fsp.sig.groupby("rebal", observed=True)["code"].nunique() if len(fsp.sig) else pd.Series(dtype=int)
        ex["제거종목수_시계열"] = cnt.rename("제거종목수").reset_index()
        # 제거 종목의 실제 사후 수익률 — 음수가 아니면 가설이 틀린 것이다
        rr = []
        for t, g in (fsp.sig.groupby("rebal", observed=True) if len(fsp.sig) else []):
            if t not in FWD_GLOBAL.index:
                continue
            r = FWD_GLOBAL.loc[t].reindex(list(g["code"])).dropna()
            if len(r):
                rr.append({"rebal": t, "제거종목수": len(r), "평균수익": float(r.mean()),
                           "중앙수익": float(r.median()),
                           "U250평균": float(FWD_GLOBAL.loc[t].reindex(univ_by_t.get(t, [])).mean())})
        ex["제거종목_사후수익"] = pd.DataFrame(rr)
        if len(rr):
            m = float(np.nanmean([x["평균수익"] - x["U250평균"] for x in rr]))
            LOG.info(f"[F1] 제거 종목의 사후 초과수익 평균 {m:+.3%}/구간 — "
                     f"{'가설과 정합(음수)' if m < 0 else '★가설과 반대(양수) — H1 이 틀렸다는 증거'}")
            RUNLOG["f1_removed_excess"] = m
        # 폐지 종목 사전 포착률
        dl = sec.dropna(subset=["delisting_date"])[["code", "delisting_date"]]
        dl = dl[dl["code"].isin(set(univ["code"]))]
        hit = 0
        flag = {t: set(g["code"]) for t, g in fsp.sig.groupby("rebal", observed=True)} if len(fsp.sig) else {}
        for _, r in dl.iterrows():
            win = [t for t in rebals if r["delisting_date"] - pd.Timedelta(days=365) <= t <= r["delisting_date"]]
            if any(r["code"] in flag.get(t, set()) for t in win):
                hit += 1
        ex["폐지_사전포착률"] = pd.DataFrame([{"유니버스 내 폐지종목": len(dl), "F1 사전포착": hit,
                                            "포착률": hit / max(len(dl), 1)}])
        LOG.info(f"[F1] 폐지 {len(dl):,}종목 중 사전 포착 {hit:,}종목 "
                 f"({100*hit/max(len(dl),1):.1f}%)")
    if f == "F2" and src.get("F2") is not None and len(src["F2"]):
        d = src["F2"]
        rows = []
        for role in ("대표이사", "등기임원", "최대주주", "특수관계인"):
            sub = d[d["role"].astype(str).str.contains(role)]
            if not len(sub):
                continue
            fs2 = build_F2(sub, rebals, univ_by_t, univ, f"role:{role}", {})
            r = e_is.run(fs2.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), f"F2 {role}")
            rows.append({**perf_row(role, r, ppy, base["B2"]), "건수": len(sub)})
        ex["매수주체별_분해"] = pd.DataFrame(rows)
        LOG.info("[F2] 매수 주체별 분해는 후속 가설 생성용으로만 기록합니다 — "
                 "이 결과를 보고 주 명세를 바꾸지 않습니다(§4 F2).")
    if f == "F4" and src.get("F4") is not None and len(src["F4"]):
        d = src["F4"]
        n_c = int(d["is_cancel"].fillna(False).sum())
        rows = [{"공시건수": len(d), "해지·정정 건수": n_c, "해지율": n_c / max(len(d), 1)}]
        ex["해지_발생률"] = pd.DataFrame(rows)
        fs_no = build_F4(d, fin, rebals, univ_by_t, "no_cancel_tracking", {}, track_cancel=False)
        r_no = e_is.run(fs_no.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), "F4 해지미처리")
        base_c = e_is.run(fsp.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), "F4 해지처리") \
            if fsp is not None else None
        ex["해지처리_유무_비교"] = pd.DataFrame([
            perf_row("해지 처리(주명세)", base_c, ppy, base["B2"]) if base_c else {},
            perf_row("해지 미처리(미래참조)", r_no, ppy, base["B2"])])
        if base_c is not None:
            gap = r_no.stats(ppy)["cagr"] - base_c.stats(ppy)["cagr"]
            LOG.info(f"[F4] 해지 처리를 빼면 CAGR 이 {gap:+.2%}p 달라집니다 — "
                     f"이만큼이 미래참조로 생기는 가짜 수익입니다.")
            RUNLOG["f4_lookahead_gap"] = gap
    return ex


def main():
    try:
        run_all()
    except SpecViolation as e:
        LOG.error(f"사전등록 위반으로 중단합니다 — {e}")
        raise
    except KillCriteria as e:
        LOG.error(f"킬 기준 — {e}")
        raise


if __name__ == "__main__":
    main()
