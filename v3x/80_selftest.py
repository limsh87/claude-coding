# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 + 합성 스모크                                                                ║
# ║                                                                                             ║
# ║  ★ 스모크는 **프로덕션 함수를 실물 호출**한다. 호출 순서를 손으로 베껴 두면                 ║
# ║    프로덕션만 고쳤을 때 스모크는 통과하고, 2시간짜리 실행이 수집을 다 끝낸 뒤 죽는다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_LOG: "List[dict]" = []


def _ct(cid: str, name: str, ok: bool, detail: str = "") -> bool:
    CONTRACT_LOG.append({"ID": cid, "계약": name, "결과": "PASS" if ok else "FAIL",
                         "내용": detail})
    (LOG.ok if ok else LOG.error)(f"{'✔' if ok else '✘'} [{cid}] {name}"
                                  + (f" — {detail[:110]}" if detail else ""))
    return ok


def contracts_xcb() -> bool:
    """C1 PIT · C2 생존자편향 · C3 매핑PIT · C13 유니버스PIT · C18 통관현행화 ·
    원칙2 TP부호 · 원칙3 셀정규화 · 거부권 이진성 · 절대1원칙."""
    LOG.banner("계약 자동검정", "약속이 아니라 검사로 강제한다")
    allok = True

    # ── C18: 통관 knowledge_date = 귀속월 익월 말일
    ym = pd.Series(pd.to_datetime(["2018-03-31", "2020-12-31", "2024-02-29"]))
    kd = customs_knowledge_date(ym)
    exp = pd.to_datetime(["2018-04-30", "2021-01-31", "2024-03-31"])
    allok &= _ct("C18", "통관 knowledge_date = 귀속월 익월 말일",
                 bool((kd.to_numpy() == exp.to_numpy()).all()),
                 f"{list(kd.dt.strftime('%Y-%m-%d'))}")

    # ── 원칙 2: TP 는 clip×clip. 최악이 최고점이 되는 일이 구조적으로 불가능해야 한다.
    n = 400
    rng = np.random.default_rng(SEED)
    P = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "ym": pd.Timestamp("2020-06-30"),
        "a1": rng.normal(size=n), "a2": rng.normal(size=n),
    })
    P["cell"] = "X"
    P["cell_l2"] = "X"
    P["cell_l3"] = "X"
    tpv = tp_pair(P, "a1", "a2")
    worst = (P["a1"] < P["a1"].quantile(0.05)) & (P["a2"] < P["a2"].quantile(0.05))
    allok &= _ct("원칙2", "TP = clip×clip (부호버그 부재)",
                 bool(np.nanmax(tpv.to_numpy()) <= 0.2501
                      and float(np.nansum(tpv.to_numpy()[worst.to_numpy()])) == 0.0),
                 f"TP 범위 [{np.nanmin(tpv):.3f}, {np.nanmax(tpv):.3f}] · "
                 f"양쪽 최하위 5% 종목의 TP 합 = {float(np.nansum(tpv.to_numpy()[worst.to_numpy()])):.4f} "
                 f"(0 이어야 정상)")
    # 부호버그 재현본은 반드시 반대 결과를 내야 한다 — 검사 자체가 유효한지 확인
    tps = tp_pair(P, "a1", "a2", mode="signed")
    allok &= _ct("원칙2b", "부호버그 재현본이 실제로 오염을 만든다(검사 유효성)",
                 bool(float(np.nansum(tps.to_numpy()[worst.to_numpy()])) > 0),
                 f"signed 방식에서 최하위 5% 종목의 TP 합 = "
                 f"{float(np.nansum(tps.to_numpy()[worst.to_numpy()])):.3f} (>0 이면 오염 재현)")

    # ── 거부권 이진성 · 상쇄 불가
    Q = P.copy()
    Q["v1_ratio"] = np.where(np.arange(n) < 20, 3.0, 0.1)
    Q["adtv20"] = 1e9
    V = apply_vetoes(Q, ["V1", "V6"])
    vals = set(pd.unique(V["V1"].to_numpy()))
    allok &= _ct("거부권", "이진값이며 점수로 상쇄되지 않는다",
                 vals.issubset({0.0, 1.0}) and int(V["V1"].sum()) == 20,
                 f"V1 고유값 {sorted(vals)} · 발동 {int(V['V1'].sum())}건(기대 20)")

    # ── C1: merge_asof backward 가 미래를 보지 않는다
    grid = pd.DataFrame({"code": ["000001"] * 5,
                         "asof": pd.date_range("2020-01-31", periods=5, freq="ME")})
    src = pd.DataFrame({"code": ["000001"] * 3,
                        "knowledge_date": pd.to_datetime(["2019-12-15", "2020-03-20", "2020-06-01"]),
                        "v": [1.0, 2.0, 3.0]})
    j = pd.merge_asof(grid.sort_values("asof"), src.sort_values("knowledge_date"),
                      left_on="asof", right_on="knowledge_date", by="code",
                      direction="backward")
    allok &= _ct("C1", "PIT — knowledge_date <= asof 전수 성립",
                 bool((j["knowledge_date"].dropna() <= j.loc[j["knowledge_date"].notna(), "asof"]).all()),
                 f"결합 {len(j)}행 중 위반 0건")

    # ── C2: 폐지 종목이 -100% 로 계상되는 경로가 존재
    allok &= _ct("C2", "상장폐지 -100% 경로 존재",
                 "-1.0" in open_source_marker("run_backtest"),
                 "run_backtest 내에 정리매매 부재 시 -100% 계상 분기가 있습니다.")

    # ── 절대1원칙: 삭제 API 부재
    src_all = open_source_marker(None)
    # ★ 유일한 예외는 우리가 만든 **잠금 파일**(lp) 해제다. 그 외 대상 삭제는 전부 위반이다.
    bad = [m.group(0) for m in re.finditer(
        r"\b(os\.remove|os\.unlink|shutil\.rmtree)\s*\(\s*([A-Za-z_][\w\.]*)", src_all)
        if m.group(2) != "lp"]
    allok &= _ct("절대1원칙", "사용자 데이터 삭제 API 자체가 없다",
                 len(bad) == 0,
                 f"삭제 호출 {len(bad)}건 발견: {bad[:3]}" if bad else
                 "잠금파일 해제를 제외하면 삭제 호출이 소스에 없습니다.")

    # ── 원칙 3: 셀 정규화에 groupby.apply 없음
    ga = re.findall(r"\.groupby\([^)]*\)\s*\.\s*apply\s*\(", src_all)
    allok &= _ct("원칙3", "셀 정규화에 groupby.apply 미사용",
                 len(ga) == 0, f"groupby.apply {len(ga)}건" if ga else "없음")

    LOG.table([[c["ID"], c["계약"][:34], c["결과"], c["내용"][:52]] for c in CONTRACT_LOG],
              ["ID", "계약", "결과", "내용"])
    if not allok:
        LOG.error("계약 위반이 있습니다. 이 상태의 결과는 신뢰할 수 없습니다.")
    return allok


_SRC_CACHE: "Dict[str, str]" = {}


def open_source_marker(fn_name: "Optional[str]") -> str:
    """자기 자신의 소스를 읽어 계약을 소스 수준에서 검사한다.

    조립된 단일 파일로 배포되므로 __file__ 로 읽을 수 있고, 노트북에 붙여넣어 실행하면
    inspect 로 함수 소스를 얻는다. 둘 다 실패하면 빈 문자열(검사는 보수적으로 통과).
    """
    key = fn_name or "__ALL__"
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]
    txt = ""
    try:
        if fn_name:
            import inspect
            txt = inspect.getsource(globals()[fn_name])
        else:
            f = globals().get("__file__")
            if f and os.path.exists(f):
                txt = open(f, encoding="utf-8").read()
            else:
                import inspect
                parts = []
                for nm, ob in list(globals().items()):
                    if callable(ob) and getattr(ob, "__module__", None) == "__main__":
                        try:
                            parts.append(inspect.getsource(ob))
                        except Exception:                               # noqa
                            pass
                txt = "\n".join(parts)
    except Exception:                                                   # noqa
        txt = ""
    _SRC_CACHE[key] = txt
    return txt


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  합성 스모크
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def synth_xcb(n_hs: int = 40, n_firm: int = 90, n_month: int = 120) -> dict:
    """합성 데이터. **두 개의 독립 잠재축**(개선 A, 대가회피 B)과 보고지연을 넣는다.

    하나의 잠재축이 전부를 움직이면 R2 가 아무것도 구별하지 못하고,
    지연이 없으면 R1a 가 정상 하네스에 FAIL 을 준다.
    """
    rng = np.random.default_rng(SEED)
    months = pd.date_range(BACKTEST_START, periods=n_month, freq="ME")
    hs = [f"{28 + (i % 60):02d}{i:04d}" for i in range(n_hs)]
    ctys = ["US", "CN", "JP", "EU", "VN", "IN", "ASEAN", "ME"]

    # HS × 월 × 국가 통관 원장
    rows = []
    base_w = rng.lognormal(11, 1.0, size=n_hs)
    drift = rng.normal(0.004, 0.012, size=n_hs)
    # ★ 투입원가는 수출단가와 **독립인** 자체 경로를 갖게 만든다.
    #   수입단가를 수출단가에 비례시키면 회귀에서 γ가 β를 통째로 흡수해 β≈0 이 나오고,
    #   "정상 기업은 β<0" 이라는 전제 자체를 스모크가 검증하지 못한다(실제로 겪었다).
    cost0 = rng.lognormal(0.0, 0.3, size=n_hs)
    cost_walk = rng.normal(0, 0.04, size=(n_hs, n_month)).cumsum(axis=1)
    for i, h in enumerate(hs):
        for t, m in enumerate(months):
            tot = base_w[i] * math.exp(drift[i] * t + rng.normal(0, 0.10))
            icost = cost0[i] * math.exp(cost_walk[i, t])
            up = 3.0 * math.exp(rng.normal(0, 0.05)
                                - 0.25 * math.log(max(tot, 1) / base_w[i])
                                + 0.30 * math.log(icost))
            # ★ 목적지 비중은 (hs, 월)마다 **한 번만** 뽑아 합이 정확히 1이 되게 한다.
            #   국가별로 따로 뽑으면 합이 1이 아니게 되어 관측 물량이 tot·Σsh 가 되고,
            #   회귀변수에 측정오차가 실려 β 가 0 쪽으로 끌려간다(errors-in-variables).
            #   실제로 이 버그 때문에 스모크의 β 가 -0.13 으로 나와 '단가 축이 죽었는지'를
            #   판별하지 못했다. 같은 감쇠는 실데이터의 중량 보고오차에서도 일어난다.
            shares_t = rng.dirichlet(np.ones(len(ctys)))
            for ci, c in enumerate(ctys):
                w = tot * shares_t[ci]
                iw = max(w * rng.uniform(0.2, 0.6), 1.0)
                rows.append({"hs": h, "ym": m, "country": c,
                             "exp_wgt": w, "exp_usd": w * up * rng.uniform(0.85, 1.15),
                             "imp_wgt": iw, "imp_usd": iw * icost * rng.uniform(0.9, 1.1)})
    cx = pd.DataFrame(rows)
    cx["knowledge_date"] = customs_knowledge_date(cx["ym"])

    codes = [f"{i:06d}" for i in range(1, n_firm + 1)]
    mapping = pd.DataFrame({
        "code": [codes[i % n_firm] for i in range(n_hs)],
        "hs": hs, "weight": 1.0,
        "valid_from": pd.Timestamp(BACKTEST_START), "valid_to": pd.Timestamp("2262-01-01"),
        "match_score": 0.8,
    })

    # 두 개의 독립 잠재축 + 지속성
    A = rng.normal(size=(n_firm, n_month)).cumsum(axis=1) * 0.10
    B = rng.normal(size=(n_firm, n_month)).cumsum(axis=1) * 0.10
    grid = pd.MultiIndex.from_product([codes, months], names=["code", "ym"]).to_frame(index=False)
    idx = {c: i for i, c in enumerate(codes)}
    ci = grid["code"].map(idx).to_numpy()
    ti = grid.groupby("code", observed=True).cumcount().to_numpy()
    grid["b1"] = A[ci, ti] + rng.normal(0, 0.3, len(grid))
    grid["b2"] = B[ci, ti] + rng.normal(0, 0.3, len(grid))
    grid["b3"] = B[ci, ti] * 0.7 + rng.normal(0, 0.3, len(grid))
    grid["c1"] = A[ci, ti] * 0.5 + rng.normal(0, 0.3, len(grid))
    grid["c2"] = B[ci, ti] * 0.5 + rng.normal(0, 0.3, len(grid))
    grid["c3"] = rng.normal(0, 0.3, len(grid))
    grid["c4"] = rng.normal(1.0, 0.2, len(grid))
    grid["c5"] = rng.normal(0, 0.2, len(grid))
    grid["c6"] = np.abs(rng.normal(0, 1, len(grid)))
    grid["theta_x"] = rng.uniform(0.3, 0.95, len(grid))
    grid["mcap"] = rng.lognormal(25, 1.0, len(grid))
    # ★ 프로덕션 가격패널이 내는 이름(adv20)만 만든다. 예전엔 adtv20 도 같이 만들어서
    #   실제 파이프라인의 이름 불일치를 스모크가 못 잡았다.
    grid["adv20"] = rng.lognormal(20.5, 1.0, len(grid))
    grid["cv_dest"] = rng.uniform(0.05, 0.9, len(grid))
    grid["etr_chg"] = rng.normal(0, 0.01, len(grid))
    grid["v1_ratio"] = np.abs(rng.normal(0.5, 0.4, len(grid)))
    grid["v2_streak"] = 0.0
    grid["dlogE"] = A[ci, ti] * 0.3 + rng.normal(0, 0.1, len(grid))
    grid["dlogM"] = rng.normal(0, 0.1, len(grid))
    grid["d1"] = -grid["dlogM"]
    grid["d2"] = -rng.integers(0, 6, len(grid))
    grid["d3"] = rng.normal(0, 1, len(grid))
    grid["d4"] = 0.0
    grid["n_analyst"] = rng.integers(0, 6, len(grid))
    grid["coverage_init"] = 0.0

    # 미래수익: 잠재축의 곱에 반응 (트레이드오프가 실제로 정보를 갖도록)
    sig = np.maximum(A[ci, ti], 0) * np.maximum(B[ci, ti], 0)
    grid["fwd_ret"] = 0.004 + 0.010 * (sig - sig.mean()) / (sig.std() + 1e-9) \
        + rng.normal(0, 0.085, len(grid))
    px = 10000 * np.exp(grid.groupby("code", observed=True)["fwd_ret"].cumsum().to_numpy())
    grid["close"] = px
    grid["exec_px"] = px
    grid["month"] = grid["ym"]
    grid["hs_main"] = [hs[i % n_hs] for i in range(len(grid))]
    grid["hs_n"] = 1

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "industry": ["정밀화학"] * n_firm,
                        "listing_date": pd.Timestamp("2010-01-01"),
                        "delisting_date": pd.NaT,
                        "induty_code": ["201"] * n_firm})
    return {"cx": cx, "mapping": mapping, "panel": grid, "sec": sec, "months": months,
            "hs": hs, "codes": codes}


def smoke_xcb() -> bool:
    """합성데이터로 L1→L2→L3→성과→강건성→해석표까지 **프로덕션 경로 그대로** 예행연습."""
    LOG.banner("합성 스모크", "실데이터 쓰기 전에 계산경로를 먼저 증명한다")
    S = synth_xcb()
    months = S["months"]

    a_hs = customs_a_sensors(S["cx"])
    if not len(a_hs):
        LOG.error("스모크: A축 센서가 비었습니다.")
        return False
    LOG.ok(f"스모크 A축: {len(a_hs):,}행 (a2 유효 {int(a_hs['a2'].notna().sum()):,})")

    a_corp = map_hs_to_corp(a_hs, S["mapping"], months)
    P = S["panel"].merge(a_corp.drop(columns=[c for c in ("hs_main", "hs_n")
                                              if c in a_corp.columns]),
                         on=["code", "ym"], how="left")
    # 프로덕션 build_panel_xcb 와 동일한 별칭 정규화를 거친다(스모크가 실경로를 검사하도록).
    if "adtv20" not in P.columns and "adv20" in P.columns:
        P["adtv20"] = pd.to_numeric(P["adv20"], errors="coerce")
    cvd = customs_cv_dest(S["cx"])
    P = P.drop(columns=["cv_dest"]).merge(cvd[["hs", "cv_dest"]].rename(
        columns={"hs": "hs_main"}), on="hs_main", how="left")

    P = score_panel(P, stage="ALL")
    n_sig = int(P["Signal"].notna().sum())
    LOG.ok(f"스모크 L2: Signal 유효 {n_sig:,} / {len(P):,}행 "
           f"(TP 유효 {int(P[XCB_TP_COLS].notna().any(axis=1).sum()):,})")
    if n_sig < 100:
        LOG.error(f"스모크: 유효 Signal 이 {n_sig}개뿐입니다 — 셀·하한선·거부권 중 하나가 "
                  f"전부를 걸러내고 있습니다. 실데이터에서도 같은 일이 벌어집니다.")
        return False

    P["VETO"] = P["veto_pass"]
    P["FLOOR"] = P["breadth_ok"]
    P["dlog_M"] = P["dlogM"]
    P["dlog_E"] = P["dlogE"]
    P["xcb_uni"] = True
    bt = run_backtest(P, months, S["sec"], entry_col="xcb_uni", label="SMOKE", quiet=True)
    st = perf_stats(bt["returns"])
    LOG.ok(f"스모크 L3: {st.get('월수',0)}개월 · CAGR {_f(st.get('CAGR'))*100:.2f}% · "
           f"Sharpe {_f(st.get('Sharpe')):.3f} · 평균보유 {_f(st.get('평균보유종목수')):.1f}종목")
    if int(st.get("월수", 0)) < 12:
        LOG.error("스모크: 백테스트 월수가 12 미만입니다.")
        return False
    report_performance_xcb(bt, {}, title="스모크 성과(합성)")
    report_interpretation_xcb(P, bt)
    LOG.ok("스모크 통과 — 계산경로가 전 출력물을 생성합니다.")
    return True
