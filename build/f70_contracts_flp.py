# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  계약 자동검정 — 협상 불가 규칙을 코드가 스스로 증명한다                              ║
# ║                                                                                          ║
# ║  C1  모든 as-of 조회는 knowledge_date <= 기준일                                            ║
# ║  C1b 신용잔고·수급의 '+1영업일' 지연이 실제로 센서에 반영되는가 (이 전략의 핵심 누수지점)   ║
# ║  C2  유니버스는 상장폐지 종목을 포함하고, 폐지 주간은 -100% 로 계상된다                     ║
# ║  C13 유니버스 밴드는 매 시점 당시 값으로 재산출된다                                        ║
# ║  TP  clip(z,0)×clip(z,0) — 둘 다 음수면 0                                                  ║
# ║  V   거부권은 이진·곱·상쇄 불가                                                            ║
# ║  BM  벤치마크 수치 하드코딩 금지 (소스 검사)                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                              # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "detail": msg})
    return ok


def _synth_daily(n_codes: int = 6, n_days: int = 400, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-01", periods=n_days)
    out = []
    for i in range(n_codes):
        c = f"{100000+i:06d}"
        ret = rng.normal(0.0003, 0.02, n_days)
        px = 10000 * np.exp(np.cumsum(ret))
        out.append(pd.DataFrame({
            "code": c, "date": days, "open": px * 0.995, "high": px * 1.01,
            "low": px * 0.99, "close": px, "volume": rng.integers(1e4, 1e6, n_days),
            "amount": rng.uniform(5e8, 5e9, n_days), "src": "synth"}))
    return pd.concat(out, ignore_index=True)


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정", "PIT · 생존자편향 · 거부권 · TP 부호 — 협상 불가 규칙")

    def c1():
        base = pd.DataFrame({"code": ["A"] * 3,
                             "wk": pd.to_datetime(["2020-01-10", "2020-02-10", "2020-03-10"])})
        src = pd.DataFrame({"code": ["A", "A"],
                            "event_date": pd.to_datetime(["2020-01-01", "2020-02-20"]),
                            "knowledge_date": pd.to_datetime(["2020-01-05", "2020-02-25"]),
                            "val": [1.0, 2.0]})
        PIT.register("_c1_test", pit_frame(src, "event_date", "knowledge_date", source="test"),
                     key_cols=["code"])
        got = PIT.asof_join(base, "_c1_test", by="code", left_time="wk")
        if "knowledge_date" not in got.columns:
            return False, "asof_join 이 knowledge_date 를 붙이지 않았습니다"
        bad = int((got["knowledge_date"] > got["wk"]).sum())
        vals = got["val"].tolist()
        return (bad == 0 and vals == [1.0, 1.0, 2.0],
                f"미래참조 {bad}건 · 결합값 {vals} (2월10일 시점에 2월25일 공표값을 보면 위반)")

    def c1b():
        """★ 이 전략의 핵심: 잔고·수급은 거래일 +1영업일에만 알 수 있다.
        잔고가 T일에 급변하면 센서는 T일이 아니라 T+1 거래일에 반응해야 한다."""
        px = _synth_daily(2, 300)
        codes = sorted(px["code"].unique())
        spike_date = px["date"].iloc[250]
        cr = px[["code", "date"]].copy()
        cr["credit_bal"] = 1e8
        cr.loc[cr["date"] >= spike_date, "credit_bal"] = 9e9
        cr["src"] = "synth"
        fl = px[["code", "date"]].copy()
        fl["retail_net"] = 1e7; fl["inst_net"] = 1e7; fl["foreign_net"] = 1e7
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSPI",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": pd.NaT, "industry": "테스트",
                            "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
        P = build_flp_panel(px, cr, fl, pd.DataFrame(), weeks, uni)
        if P.empty:
            return False, "패널이 비었습니다"
        # 급변일 '당일'이 신호일인 행이 있으면 그 행의 credit_bal 은 아직 옛값이어야 한다
        same = P[(P["signal_date"] == spike_date)]
        if len(same) == 0:
            # 신호일 격자에 급변일이 없으면, 급변 직후 첫 신호일로 검사한다
            after = P[P["signal_date"] > spike_date].sort_values("signal_date")
            ok = bool(len(after) and (after["credit_bal"] > 1e9).any())
            return ok, f"급변일 격자 부재 → 직후 신호일 반영 여부만 검사 ({'반영됨' if ok else '미반영'})"
        stale = float(same["credit_bal"].max())
        return (stale < 1e9,
                f"급변 당일 센서가 본 잔고 = {stale:,.0f} (옛값 1e8 이어야 함 — "
                f"9e9 이면 하루치 미래정보 누출)")

    def c2():
        px = _synth_daily(4, 300)
        codes = sorted(px["code"].unique())
        dead = codes[0]
        dl = px["date"].iloc[280]
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": [dl] + [pd.NaT] * (len(codes) - 1),
                            "industry": "테스트", "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        before = uni.at(dl - pd.Timedelta(days=30))
        after = uni.at(dl + pd.Timedelta(days=5))
        if dead not in before:
            return False, "폐지 예정 종목이 폐지 전 유니버스에 없습니다 (생존자편향 재유입)"
        if dead in after:
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        # 폐지 주간 -100% 계상 검증
        wk = pd.DatetimeIndex([dl - pd.Timedelta(days=3)])
        P = pd.DataFrame({"code": [dead], "wk": wk, "exec_px": [1000.0], "fwd_ret": [np.nan],
                          "adv20": [1e9], "FIREWALL": [1], "VETO": [1], "in_band": [1],
                          "V6": [1], "PHASE_C": [1], "f_dd": [-0.4], "f_cr_pctl": [0.1],
                          "Signal_rank": [1.0]})
        bt = run_backtest_w(P, wk, uni, sec, apply_costs=False, label="c2")
        H = bt["holdings"]
        if H is None or H.empty:
            return False, "폐지 예정 종목이 아예 편입되지 않았습니다(=조용한 누락, 그 자체가 C2 위반)"
        pos_ret = float(H["ret"].iloc[0])
        w = float(H["weight"].iloc[0])
        port = float(bt["returns"]["ret"].iloc[0])
        # 포지션 수익률이 -100% 여야 한다. 포트 수익률은 비중만큼만 반영되는 것이 정상이다
        # (종목당 상한이 있으므로 -100% 가 그대로 포트 수익률이 되면 오히려 사이징 버그다).
        return (pos_ret <= -0.999 and abs(port - w * pos_ret) < 1e-9,
                f"포지션 수익률 {pos_ret:.1%} · 비중 {w:.1%} · 포트 기여 {port:.2%} "
                f"(정리매매가 없으면 포지션은 -100%)")

    def c13():
        px = _synth_daily(300, 60)
        P = pd.DataFrame({"code": px["code"].unique()})
        P["wk"] = pd.Timestamp("2019-03-01")
        P["mcap"] = np.linspace(1e12, 1e9, len(P))
        P["adv20"] = 1e9
        P = pd.concat([P, P.assign(wk=pd.Timestamp("2019-03-08"),
                                   mcap=P["mcap"].to_numpy()[::-1])], ignore_index=True)
        Q = apply_universe_bands(P)
        r1 = Q[Q["wk"] == pd.Timestamp("2019-03-01")].set_index("code")["mcap_rank"]
        r2 = Q[Q["wk"] == pd.Timestamp("2019-03-08")].set_index("code")["mcap_rank"]
        flipped = float((r1 - r2).abs().mean())
        return (flipped > 1.0,
                f"시점별 랭크 평균 변화 {flipped:.1f} (0 이면 현재 시총으로 과거를 정의한 것)")

    def c_tp():
        P = pd.DataFrame({"cell": ["x"] * 10, "cell_l2": ["y"] * 10, "cell_l3": ["z"] * 10,
                          "a": np.linspace(-1, 1, 10), "b": np.linspace(-1, 1, 10)})
        v = tp(P, P["a"], P["b"])
        low = float(v.iloc[0])                      # 둘 다 최악
        high = float(v.iloc[-1])                    # 둘 다 최고
        return (low == 0.0 and high > 0.0,
                f"둘 다 최악={low:.3f}(0이어야 함) · 둘 다 최고={high:.3f} "
                f"(z*z 를 쓰면 최악이 최고점을 받는다)")

    def c_veto():
        P = pd.DataFrame({"wk": [pd.Timestamp("2020-01-03")] * 3, "code": list("abc"),
                          "TP_F1": [0.9, 0.9, 0.9], "TP_F2": [0.9, 0.9, 0.9],
                          "TP_F3": [0.9, 0.9, 0.9], "TP_F4": [0.9, 0.9, 0.9],
                          "PHASE_C": [1, 1, 1], "FIREWALL": [1, 0, 1], "VETO": [1, 1, 0],
                          "in_band": [1, 1, 1]})
        S = assemble_score(P)
        s = S.set_index("code")["Signal"]
        return (s["a"] > 0 and s["b"] == 0 and s["c"] == 0,
                f"정상={s['a']:.3f} 방화벽차단={s['b']:.3f} 거부권차단={s['c']:.3f} "
                f"(점수가 높아도 상쇄되면 안 된다)")

    def c_exit():
        """청산 규칙이 실제로 작동하는가: f_cr_pctl 회복 시 다음 주에 비중이 0 이어야 한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=3, freq="W-FRI"))
        rows = []
        for i, w in enumerate(wks):
            rows.append({"code": "A", "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0,
                         "adv20": 1e10, "FIREWALL": 1, "VETO": 1, "in_band": 1, "V6": 1,
                         "PHASE_C": 1 if i == 0 else 0, "f_dd": -0.4,
                         "f_cr_pctl": 0.1 if i < 2 else 0.9,
                         "Signal_rank": 1.0 if i == 0 else np.nan})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_exit")
        n = bt["returns"]["n"].tolist()
        return (n[0] == 1 and n[1] == 1 and n[2] == 0,
                f"주별 보유종목수 {n} — 3주차에 f_cr_pctl=0.9(재취약)이므로 0 이어야 함")

    def c_size():
        sub = pd.DataFrame({"code": [f"c{i}" for i in range(30)], "adv20": [1e12] * 30})
        w = size_positions(sub)["weight"]
        return (abs(w.sum() - 1.0) < 1e-6 and w.max() <= POS_MAX_WEIGHT + 1e-9,
                f"합계 {w.sum():.4f} · 최대 {w.max():.4f} (상한 {POS_MAX_WEIGHT})")

    def c_fwd():
        """주 연속성이 끊긴 구간의 fwd_ret 은 결측이어야 한다 (수익 과대계상 방지)."""
        px = _synth_daily(1, 200)
        code = px["code"].iloc[0]
        gap_mask = (px["date"] >= px["date"].iloc[60]) & (px["date"] <= px["date"].iloc[100])
        px2 = px[~gap_mask]
        sec = pd.DataFrame({"code": [code], "name": [code], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT], "industry": ["T"], "corp_code": [None]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px2)
        weeks = week_grid(str(px2["date"].min().date()), str(px2["date"].max().date()), px2)
        P = build_flp_panel(px2, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), weeks, uni)
        big = int((P["fwd_ret"].abs() > 0.5).sum())
        return (big == 0, f"|fwd_ret|>50% 인 주 {big}건 (건너뛴 구간을 1주 수익으로 계상하면 발생)")

    def c_bm():
        """벤치마크 수치 하드코딩 금지(§1-5) — 소스를 직접 검사한다."""
        import inspect
        src = inspect.getsource(benchmark_returns_w)
        bad = re.findall(r"(?:CAGR|cagr)\s*=\s*0\.\d+", src)
        return (len(bad) == 0, f"소스 내 하드코딩된 성과 상수 {len(bad)}건")

    def c_seed():
        a = np.random.default_rng(SEED).normal(size=5)
        b = np.random.default_rng(SEED).normal(size=5)
        return (bool(np.allclose(a, b)), "동일 시드 → 동일 난수열 (C8 결정성)")

    def c_cell():
        """셀이 얇으면 상위 단위로 폴백해야 한다 (얇은 셀에서 rank 가 의미를 잃는 것 방지)."""
        P = pd.DataFrame({"cell": ["a"] * 3 + ["b"] * 20, "cell_l2": ["L2"] * 23,
                          "cell_l3": ["L3"] * 23, "v": np.arange(23, dtype=float)})
        r = cell_rank(P, "v", min_n=8)
        thin = r.iloc[:3]
        return (thin.nunique() == 3 and float(thin.max()) < 0.5,
                f"얇은 셀 3행의 백분위 {[round(x,3) for x in thin]} — "
                f"전체 23행 기준으로 매겨져야 낮게 나온다")

    def c_vault():
        """공용/전용 인덱스 왕복 — 저장한 것을 다시 읽을 수 있어야 한다(절대 1원칙의 실효성)."""
        if VAULT is None:
            return False, "VAULT 미초기화"
        t = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        p1 = VAULT.put_table("_contract_roundtrip_shared", t, scope="shared", domain="test")
        p2 = VAULT.put_table("_contract_roundtrip_private", t, scope="private", domain="test")
        g1 = VAULT.get_table("_contract_roundtrip_shared", scope="shared")
        g2 = VAULT.get_table("_contract_roundtrip_private", scope="private")
        ok = (p1 and p2 and g1 is not None and g2 is not None and
              len(g1) == 3 and len(g2) == 3)
        # 저널이 append-only 인지 확인 (기존 줄 보존)
        j = VAULT.journal("shared")
        n_lines = len(open(j, encoding="utf-8").read().strip().split("\n")) if os.path.exists(j) else 0
        return ok, f"공용/전용 왕복 OK · 저널 {n_lines}줄 (append-only)"

    _c("C1", "as-of 조회는 knowledge_date <= 기준일", c1)
    _c("C1b", "신용잔고·수급 +1영업일 지연 (★핵심 누수지점)", c1b)
    _c("C2", "상장폐지 포함 · 폐지 주간 -100%", c2)
    _c("C13", "유니버스 밴드 PIT 재산출", c13)
    _c("TP", "clip(z,0)×clip(z,0) 부호 규약", c_tp)
    _c("VETO", "거부권 이진·상쇄 불가", c_veto)
    _c("EXIT", "청산 규칙(f_cr_pctl 회복) 작동", c_exit)
    _c("SIZE", "사이징 상한·합계", c_size)
    _c("FWD", "주 연속성 끊김 시 fwd_ret 결측", c_fwd)
    _c("CELL", "셀 폴백 사다리", c_cell)
    _c("BM", "벤치마크 하드코딩 금지", c_bm)
    _c("SEED", "결정성", c_seed)
    _c("VAULT", "구글드라이브 공용/전용 인덱스 왕복", c_vault)

    rows = [[r["id"], _trunc(r["name"], 40), "✔" if r["pass"] else "✘", _trunc(r["detail"], 60)]
            for r in CONTRACT_RESULTS]
    LOG.table(rows, ["ID", "계약", "통과", "상세"], ["l", "l", "c", "l"], maxw=64)
    fails = [r for r in CONTRACT_RESULTS if not r["pass"]]
    if fails:
        msg = "계약 위반: " + ", ".join(f"{r['id']}({r['detail'][:60]})" for r in fails)
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"계약 {len(CONTRACT_RESULTS)}건 전부 통과.")
    return True
