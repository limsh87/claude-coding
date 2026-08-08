

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0  자체검증 — §35 TEST 1~9 + 합성데이터 엔드투엔드 스모크                                ║
# ║                                                                                          ║
# ║  ★ 실데이터를 한 줄도 건드리기 전에 여기를 통과해야 한다.                                   ║
# ║    수집이 오래 걸리는 파이프라인에서 계산경로 버그를 4시간 뒤에 발견하는 것만큼               ║
# ║    비싼 것이 없다. 합성데이터는 정답을 알고 있으므로 계산경로를 '증명'할 수 있다.            ║
# ║                                                                                          ║
# ║  ★ 그리고 §48 의 완료조건은 "코드가 돌았다"가 아니라 "아래가 전부 PASS 다" 이다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_TESTS: List[Dict[str, Any]] = []


def _t(tid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, f"{type(e).__name__}: {e}"
    SCG_TESTS.append({"id": tid, "name": name, "ok": bool(ok), "msg": str(msg)})


def _synth_forecasts(rows) -> pd.DataFrame:
    f = pd.DataFrame(rows, columns=["stock_id", "analyst_id", "report_date",
                                    "fiscal_period", "forecast_value"])
    f["broker_id"] = "B"
    f["forecast_metric"] = "EPS"
    f["report_id"] = [f"r{i}" for i in range(len(f))]
    f["report_date"] = as_ts_series(f["report_date"])
    return f


def _synth_calendar() -> pd.DatetimeIndex:
    return pd.bdate_range("2012-01-01", "2028-12-31")


def scg_run_tests(strict: bool = True) -> bool:
    """§35 TEST 1~9. 합성데이터라 정답을 알고 있으므로 '통과/실패'가 명확하다."""
    SCG_TESTS.clear()
    CAL = _synth_calendar()
    NOSC = pd.DataFrame(columns=["signal_date", "analyst_id", "acc_star", "lead_star"])

    # ── TEST 1 — 모든 전망이 같으면 Smart == Equal, SCG == 0 ─────────────────────────
    def t1():
        f = _synth_forecasts([("A", f"an{j}", d, "2020-12", 100.0)
                              for j in range(4) for d in ("2019-03-01", "2019-06-01")])
        sd = pd.DatetimeIndex(["2019-07-31", "2019-08-30"])
        sc, _ = compute_smart_consensus(build_active_forecasts(f, sd), NOSC)
        sg = build_scg_signals(sc, CAL)
        a = np.allclose(sc["smart_consensus_ls"], sc["consensus_equal_weight"])
        b = np.allclose(sg["scg_ls"].dropna(), 0.0) and np.allclose(sg["scg0"].dropna(), 0.0)
        return (a and b), "전망이 모두 같을 때 Smart==Equal 이고 SCG==0"

    # ── TEST 2 — 이력 없는 애널리스트는 중립(0), multiplier=1, 탈락 없음 ──────────────
    def t2():
        f = _synth_forecasts([("A", "x", "2020-03-01", "2020-12", 10.0),
                              ("A", "y", "2020-03-01", "2020-12", 12.0)])
        sd = pd.DatetimeIndex(["2020-03-31"])
        S = build_analyst_scores(sd, pd.DataFrame(), pd.DataFrame())
        _, w = compute_smart_consensus(build_active_forecasts(f, sd), S)
        ok = (len(S) == 0 and np.allclose(w["acc_star"], 0) and np.allclose(w["lead_star"], 0)
              and np.allclose(w["quality_multiplier_ls"], 1.0)
              and np.allclose(w["quality_multiplier_scg0"], 1.0) and len(w) == 2)
        return ok, "이력이 없어도 애널리스트 2명 전원 유지 · Q=0 · multiplier=1"

    # ── TEST 3 — 정확했던 애널리스트가 더 큰 가중치 ──────────────────────────────────
    def t3():
        rows, acts = [], []
        for k in range(10):
            y = 2013 + k
            fp, ad = f"{y}-12", as_ts(f"{y+1}-03-15")
            rd = ad - pd.Timedelta(days=60)
            rows += [("A", "good", rd, fp, 100.0), ("A", "bad", rd, fp, 60.0),
                     ("A", "mid", rd, fp, 100.0)]
            acts.append(("A", fp, "EPS", 100.0, ad))
        ae = build_accuracy_events(_synth_forecasts(rows), pd.DataFrame(
            acts, columns=["stock_id", "fiscal_period", "forecast_metric",
                           "actual_value", "actual_announcement_date"]))
        sd = pd.DatetimeIndex(["2024-01-31"])
        S = build_analyst_scores(sd, ae, pd.DataFrame())
        fw = _synth_forecasts([("A", "good", "2024-01-20", "2025-12", 10.0),
                               ("A", "bad", "2024-01-20", "2025-12", 10.0)])
        _, w = compute_smart_consensus(build_active_forecasts(fw, sd), S)
        ww = w.set_index("analyst_id")["weight_ls"]
        si = S.set_index("analyst_id")
        ok = (si.loc["good", "acc_star"] > si.loc["bad", "acc_star"]
              and si.loc["bad", "acc_star"] < 0 and ww["good"] > ww["bad"])
        return ok, (f"ACC* good={si.loc['good','acc_star']:+.3f} bad={si.loc['bad','acc_star']:+.3f} "
                    f"→ weight {ww['good']:.3f} > {ww['bad']:.3f}")

    # ── TEST 4 — 선행한 애널리스트의 LEAD* 가 더 큼 ──────────────────────────────────
    def t4():
        rows = []
        for k in range(12):
            t0 = as_ts("2018-01-05") + pd.DateOffset(months=3 * k)
            t20 = CAL[CAL.searchsorted(t0) + 20]
            rows += [("S", "lead", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "lead", t0, "2030-12", 120.0),
                     ("S", "p1", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "p2", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "p1", t20, "2030-12", 130.0), ("S", "p2", t20, "2030-12", 130.0),
                     ("S2", "flat", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S2", "flat", t0, "2030-12", 120.0),
                     ("S2", "q1", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S2", "q2", t0 - pd.Timedelta(days=5), "2030-12", 100.0)]
        le = build_leadership_events(_synth_forecasts(rows), CAL)
        if le.empty:
            return False, "Leadership 이벤트가 하나도 생성되지 않음"
        S = build_analyst_scores(pd.DatetimeIndex(["2021-06-30"]), pd.DataFrame(), le)
        si = S.set_index("analyst_id")
        ok = ("lead" in si.index and "flat" in si.index
              and si.loc["lead", "lead_star"] > si.loc["flat", "lead_star"]
              and si.loc["lead", "lead_star"] > 0)
        return ok, (f"LEAD* lead={si.loc['lead','lead_star']:+.4f} "
                    f"flat={si.loc['flat','lead_star']:+.4f} (이벤트 {len(le):,}건)")

    # ── TEST 5 — 최근 전망일수록 큰 가중치 (반감기 45일) ─────────────────────────────
    def t5():
        T = as_ts("2020-06-30")
        f = _synth_forecasts([("A", "d0", T, "2020-12", 10.0),
                              ("A", "d45", T - pd.Timedelta(days=45), "2020-12", 10.0),
                              ("A", "d90", T - pd.Timedelta(days=90), "2020-12", 10.0)])
        _, w = compute_smart_consensus(build_active_forecasts(f, pd.DatetimeIndex([T])), NOSC)
        ws = w.set_index("analyst_id")["weight_ls"]
        ok = (ws["d0"] > ws["d45"] > ws["d90"]
              and abs(ws["d45"] / ws["d0"] - 0.5) < 1e-9
              and abs(ws["d90"] / ws["d0"] - 0.25) < 1e-9)
        return ok, f"0일 {ws['d0']:.4f} > 45일 {ws['d45']:.4f} > 90일 {ws['d90']:.4f} (정확히 반감)"

    # ── TEST 6 — 미래누수 차단 ───────────────────────────────────────────────────────
    def t6():
        ad = as_ts("2020-03-15")
        rows = [("A", "x", ad - pd.Timedelta(days=30), "2019-12", 90.0),
                ("A", "y", ad - pd.Timedelta(days=30), "2019-12", 110.0)]
        ae = build_accuracy_events(_synth_forecasts(rows), pd.DataFrame(
            [("A", "2019-12", "EPS", 100.0, ad)],
            columns=["stock_id", "fiscal_period", "forecast_metric",
                     "actual_value", "actual_announcement_date"]))
        before = build_analyst_scores(pd.DatetimeIndex([ad]), ae, pd.DataFrame())
        after = build_analyst_scores(pd.DatetimeIndex([ad + pd.Timedelta(days=1)]), ae, pd.DataFrame())
        n_b = 0 if before.empty else int(before["acc_n"].max())
        n_a = 0 if after.empty else int(after["acc_n"].max())
        return (n_b == 0 and n_a == 1), f"발표 당일 사건수={n_b} (0이어야 함) · 익일={n_a} (1이어야 함)"

    # ── TEST 7 — leave-one-out: peer 에 자기 자신이 절대 없어야 함 ───────────────────
    def t7():
        rows = []
        for k in range(6):
            t0 = as_ts("2019-02-01") + pd.DateOffset(months=4 * k)
            t20 = CAL[CAL.searchsorted(t0) + 20]
            rows += [("S", "a", t0 - pd.Timedelta(days=3), "2031-12", 100.0),
                     ("S", "a", t0, "2031-12", 130.0),
                     ("S", "b", t0 - pd.Timedelta(days=3), "2031-12", 90.0),
                     ("S", "c", t0 - pd.Timedelta(days=3), "2031-12", 110.0),
                     ("S", "b", t20, "2031-12", 120.0)]
        f = _synth_forecasts(rows)
        le = build_leadership_events(f, CAL)
        if le.empty:
            return False, "이벤트 없음"
        if le["self_in_peer_t0"].any() or le["self_in_peer_t20"].any():
            return False, "peer 집합에 이벤트 소유자가 포함됨 — leave-one-out 위반"
        #  O(n²) 참조구현과 정면 대조
        v = _scg_validity(f.copy(), SCG)
        bad = 0
        for r in le.itertuples(index=False):
            for tcol, ccol, ncol in (("event_date", "peer_consensus_t0", "peer_count_t0"),
                                     ("outcome_date", "peer_consensus_t20", "peer_count_t20")):
                t = getattr(r, tcol)
                m = ((v["valid_start"] <= t) & (v["valid_end"] >= t)
                     & v["stock_id"].eq(r.stock_id) & v["fiscal_period"].eq(r.fiscal_period)
                     & v["forecast_metric"].eq(r.forecast_metric)
                     & v["analyst_id"].ne(r.analyst_id))
                s = v.loc[m, "forecast_value"]
                if len(s) != getattr(r, ncol) or abs(float(s.mean()) - getattr(r, ccol)) > 1e-9:
                    bad += 1
        return bad == 0, f"참조구현(O(n²)) 대조 {2*len(le):,}건 중 불일치 {bad}건"

    # ── TEST 8 — 1인 1표 ─────────────────────────────────────────────────────────────
    def t8():
        f = _synth_forecasts([("A", "x", "2020-01-10", "2020-12", 1.0),
                              ("A", "x", "2020-02-10", "2020-12", 2.0),
                              ("A", "x", "2020-03-10", "2020-12", 3.0),
                              ("A", "x", "2020-03-10", "2021-12", 9.0),
                              ("A", "y", "2020-03-01", "2020-12", 5.0)])
        a = build_active_forecasts(f, pd.DatetimeIndex(["2020-03-31"]))
        dup = a.groupby(["signal_date", "stock_id", "analyst_id", "fiscal_period",
                         "forecast_metric"]).size()
        latest = float(a.loc[(a.analyst_id == "x") & (a.fiscal_period == "2020-12"),
                             "forecast_value"].iloc[0])
        c = compute_equal_consensus(a)
        sep = c["fiscal_period"].nunique() == 2
        return (int(dup.max()) == 1 and latest == 3.0 and sep), \
            f"활성 전망 최대 {int(dup.max())}건 · 최신값 채택 {latest} · 회계기간 분리 {sep}"

    # ── TEST 9 — 표본 보존 (§35-9) ───────────────────────────────────────────────────
    def t9():
        rows = []
        for i in range(60):
            rows += [(f"K{i:03d}", "a", "2020-03-01", "2020-12", 100.0 + i),
                     (f"K{i:03d}", "b", "2020-03-01", "2020-12", 101.0 + i)]
        rows += [("SOLO", "a", "2020-03-01", "2020-12", 5.0),
                 ("NEG", "a", "2020-03-01", "2020-12", -50.0),
                 ("NEG", "b", "2020-03-01", "2020-12", -30.0),
                 ("ZERO", "a", "2020-03-01", "2020-12", 0.001),
                 ("ZERO", "b", "2020-03-01", "2020-12", -0.001)]
        sd = pd.DatetimeIndex(["2020-03-31"])
        act = build_active_forecasts(_synth_forecasts(rows), sd)
        sc, _ = compute_smart_consensus(act, NOSC)
        sg = build_scg_signals(sc, CAL)
        u_eq = set(sg.loc[sg["consensus_equal_weight"].notna() &
                          sg["status"].eq(STATUS_OK), "stock_id"])
        u_0 = set(sg.loc[sg["scg0"].notna(), "stock_id"])
        u_ls = set(sg.loc[sg["scg_ls"].notna(), "stock_id"])
        finite = bool(np.isfinite(sg["scg_ls"].dropna()).all())
        keeps = {"NEG", "ZERO"} <= set(sg["stock_id"])
        solo = sg.loc[sg["stock_id"].eq("SOLO"), "status"].iloc[0] == STATUS_INSUFFICIENT
        return (u_eq == u_0 == u_ls and finite and keeps and solo), \
            (f"유니버스 equal={len(u_eq)} scg0={len(u_0)} scg_ls={len(u_ls)} (동일해야 함) · "
             f"음수/0근처 EPS 종목 유지 · 1인 종목은 INSUFFICIENT")

    # ── 추가 — 미래 report_date 즉시 오류 (§32) ──────────────────────────────────────
    def t10():
        try:
            build_active_forecasts(_synth_forecasts([("A", "a", "2035-01-01", "2020-12", 1.0)]),
                                   pd.DatetimeIndex(["2020-03-31"]))
        except ValueError:
            return True, "미래 발간일 전망을 ValueError 로 즉시 거부"
        return False, "미래 발간일을 통과시켰습니다 — §32 위반"

    # ── 추가 — 파라미터가 실제로 산식을 바꾸는가 (배선 검정) ────────────────────────
    def t11():
        T = as_ts("2020-06-30")
        f = _synth_forecasts([("A", "x", T - pd.Timedelta(days=45), "2020-12", 10.0),
                              ("A", "y", T, "2020-12", 20.0)])
        a = build_active_forecasts(f, pd.DatetimeIndex([T]))
        _, w1 = compute_smart_consensus(a, NOSC, SCG)
        _, w2 = compute_smart_consensus(a, NOSC, replace(SCG, FORECAST_HALFLIFE_DAYS=90.0))
        r1 = float(w1.set_index("analyst_id")["weight_ls"]["x"])
        r2 = float(w2.set_index("analyst_id")["weight_ls"]["x"])
        return (abs(r1 - 0.5) < 1e-9 and abs(r2 - 2 ** -0.5) < 1e-9), \
            f"half-life 45→{r1:.4f}, 90→{r2:.4f} (설정이 실제로 산식에 연결되어 있음)"

    _t("TEST1", "Equal forecast invariance (§35-1)", t1)
    _t("TEST2", "Neutral analyst shrinkage (§35-2)", t2)
    _t("TEST3", "Accuracy reward (§35-3)", t3)
    _t("TEST4", "Leadership reward (§35-4)", t4)
    _t("TEST5", "Recency weighting (§35-5)", t5)
    _t("TEST6", "No future leakage (§35-6)", t6)
    _t("TEST7", "Leave-one-out (§35-7)", t7)
    _t("TEST8", "No analyst duplication (§35-8)", t8)
    _t("TEST9", "Sample preservation (§35-9)", t9)
    _t("EXTRA1", "미래 report_date 즉시 오류 (§32)", t10)
    _t("EXTRA2", "config 배선 검정 (파라미터가 산식에 연결됨)", t11)

    rows = [[t["id"], t["name"], "PASS" if t["ok"] else "FAIL", _trunc(t["msg"], 60)]
            for t in SCG_TESTS]
    LOG.table(rows, ["ID", "검사", "결과", "근거"], ["l", "l", "c", "l"],
              title="§35 자체검증 — 합성데이터라 정답을 알고 있으므로 통과/실패가 명확합니다")
    n_fail = sum(1 for t in SCG_TESTS if not t["ok"])
    if n_fail:
        msg = ("자체검증 실패 " + str(n_fail) + "건: " +
               ", ".join(t["id"] for t in SCG_TESTS if not t["ok"]) +
               " — 실데이터 수집을 시작하지 않습니다. 산식이 명세와 어긋나 있습니다.")
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"자체검증 {len(SCG_TESTS)}건 전부 통과 — 계산경로가 명세 §35 를 만족합니다")
    return True


def scg_smoke(n_stocks: int = 90, n_months: int = 48) -> Dict[str, Any]:
    """합성데이터 엔드투엔드 — 수집부를 제외한 전 출력물을 예행연습한다.

    ★ 알파가 '있는' 데이터를 일부러 만든다: 정확한 애널리스트의 전망이 미래수익률과
      약하게 연동되도록 한다. 그래야 백테스트·IC·단조성 표가 의미 있는 숫자로 나오고,
      표가 전부 0 이면 '데이터가 없어서'가 아니라 '경로가 끊겨서'임을 알 수 있다.
    """
    rng = np.random.default_rng(SEED)
    cal = _synth_calendar()
    cal = cal[(cal >= as_ts("2015-01-01")) & (cal <= as_ts("2026-12-31"))]
    sd = pd.DatetimeIndex(pd.Series(cal, index=cal).groupby(
        pd.Series(cal, index=cal).index.to_period("M")).max().values)[-n_months:]
    codes = [f"S{i:04d}" for i in range(n_stocks)]
    analysts = [f"AN{j:03d}" for j in range(40)]
    skill = {a: float(rng.normal(0, 1)) for a in analysts}     # 잠재 실력

    # 종목별 '진짜' EPS 경로
    truth = {c: float(rng.uniform(200, 5000)) for c in codes}
    rows, acts, prices = [], [], []
    for c in codes:
        base = truth[c]
        p0 = base * rng.uniform(8, 20)
        for y in range(2015, 2027):
            a_val = base * (1 + 0.10 * rng.normal())
            acts.append((c, f"{y}-12", "EPS", a_val, as_ts(f"{y+1}-03-20")))
            for a in rng.choice(analysts, size=int(rng.integers(2, 9)), replace=False):
                for m in (3, 6, 9, 12):
                    err = rng.normal(0, 0.18) / (1.0 + 0.9 * max(skill[a], 0))
                    rows.append((c, a, as_ts(f"{y}-{m:02d}-10"), f"{y}-12", a_val * (1 + err)))
        # 가격: 스마트 컨센서스가 앞서가는 종목이 이후 오르도록 약한 신호를 심는다
        r = rng.normal(0.004, 0.06, len(cal)) + 0.02 * np.tanh(skill.get(analysts[0], 0))
        px = p0 * np.exp(np.cumsum(r * 0.2))
        prices.append(pd.DataFrame({"code": c, "date": cal, "close_adj": px,
                                    "volume": 10000.0, "amount": px * 10000.0, "src": "synth"}))
    f = _synth_forecasts(rows)
    A = pd.DataFrame(acts, columns=["stock_id", "fiscal_period", "forecast_metric",
                                    "actual_value", "actual_announcement_date"])
    px = pd.concat(prices, ignore_index=True)

    ae = build_accuracy_events(f, A)
    le = build_leadership_events(f, cal)
    S = build_analyst_scores(sd, ae, le)
    act = build_active_forecasts(f, sd)
    sc, w = compute_smart_consensus(act, S)
    sig = build_scg_signals(sc, cal)
    sig = scg_forward_returns(sig, px, cal, IC_HORIZONS_TD)
    res = scg_run_all_strategies(sig, SCG, None, label="SMOKE")
    return {"signals": sig, "scores": S, "weights": w, "res": res,
            "accuracy_events": ae, "leadership_events": le, "prices": px, "calendar": cal}
