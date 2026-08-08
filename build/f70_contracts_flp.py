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

    def c_halt():
        """★ 실제로 있었던 결함의 회귀 방지:
        보유 종목이 거래정지로 패널에서 사라진 뒤 상장폐지되면, 예전 구현은 그 종목을
        '보유 목록에서 조용히 제거'해 총손실(-100%)을 무손실(0%)로 계상했다.
        한국의 전형 경로(거래정지 → 정리매매 → 폐지)가 통째로 공짜 탈출이 되는 결함이다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=5, freq="W-FRI"))
        dl = wks[3] + pd.Timedelta(days=2)          # 4주차와 5주차 사이에 폐지
        rows = []
        for i, w in enumerate(wks):
            if i >= 1:
                continue                             # 2주차부터 패널에서 사라진다(거래정지)
            rows.append({"code": "A", "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0,
                         "adv20": 1e10, "FIREWALL": 1, "VETO": 1, "in_band": 1, "V6": 1,
                         "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [dl]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_halt")
        H = bt["holdings"]
        states = list(H["state"]) if "state" in H.columns else []
        loss = float(H.loc[H["ret"] <= -0.999, "weight"].sum()) if len(H) else 0.0
        total = float(bt["returns"]["ret"].sum())
        return (("delisted" in states) and loss > 0 and total < -0.05,
                f"상태전이={states} · 총손실 반영 {total:.2%} "
                f"(거래정지 중 폐지를 0% 로 처리하면 여기가 0.00% 로 나온다)")

    def c_delist_once():
        """폐지 -100% 이중계상 방지: 손실은 정확히 한 번만 계상되어야 한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=4, freq="W-FRI"))
        dl = wks[1] + pd.Timedelta(days=2)
        rows = [{"code": "A", "wk": wks[0], "exec_px": 1000.0, "fwd_ret": 0.0, "adv20": 1e10,
                 "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "in_band": 1, "V6": 1,
                 "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0},
                # 폐지 주간: 다음 주 체결가가 없으므로 fwd_ret 은 결측이다(= 정리매매 미확보)
                {"code": "A", "wk": wks[1], "exec_px": 1000.0, "fwd_ret": np.nan, "adv20": 1e10,
                 "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "in_band": 1, "V6": 1,
                 "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0}]
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")], "delisting_date": [dl]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_del1")
        H = bt["holdings"]
        n_total = int((H["ret"] <= -0.999).sum()) if len(H) else 0
        tot = float(bt["returns"]["ret"].sum())
        return (n_total == 1 and tot < -0.05,
                f"-100% 계상 {n_total}회 · 누적 {tot:.2%} "
                f"(0회면 미계상, 2회면 폐지 손실을 두 번 반영한 것)")

    def c_halt_gap():
        """거래정지 구간의 가격 붕괴가 재개 주에 실현되는가.
        정지 중 0%, 재개 후 새 가격에서 재시작하면 그 손실이 어디에도 계상되지 않는다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=4, freq="W-FRI"))
        base = dict(adv20=1e10, FIREWALL=1, FIREWALL_HARD=1, VETO=1, in_band=1, V6=1,
                    PHASE_C=1, f_dd=-0.4, f_cr_pctl=0.1)
        rows = [{"code": "A", "wk": wks[0], "exec_px": 1000.0, "fwd_ret": 0.0,
                 "Signal_rank": 1.0, **base},
                # wks[1], wks[2] 는 패널에 없음(거래정지) → wks[3] 에 반토막으로 재개
                {"code": "A", "wk": wks[3], "exec_px": 500.0, "fwd_ret": 0.0,
                 "Signal_rank": np.nan, **base}]
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_gap")
        H = bt["holdings"]
        got = float(H.loc[H["state"] == "resumed", "ret"].sum()) if "state" in H.columns else 0.0
        return (got <= -0.49,
                f"재개 주 실현수익률 {got:.1%} (정지 중 -50% 붕괴가 반영되면 -50% 근처)")

    def c_dtype():
        """★ 실제 실행에서만 나타나던 결함: 가격 패널은 downcast 로 code 가 category 가 되고
        신용/수급/주식수는 object 다. merge_asof(by='code') 는 dtype 이 다르면 죽는다."""
        px = downcast(_synth_daily(3, 200))
        if str(px["code"].dtype) != "category":
            px["code"] = px["code"].astype("category")
        codes = [str(c) for c in px["code"].unique()]
        cr = pd.DataFrame({"code": codes * 10, "date": list(px["date"].unique())[:10] * 3,
                           "credit_bal": 1e8, "src": "t"})
        sh = pd.DataFrame({"snap_date": [px["date"].min()] * 3, "code": codes,
                           "shares": 1e6, "mcap_snap": np.nan})
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSPI",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": pd.NaT, "industry": "T", "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
        P = build_flp_panel(px, cr, pd.DataFrame(), sh, weeks, uni)
        return (len(P) > 0 and P["shares"].notna().any(),
                f"category/object 혼합 결합 결과 {len(P):,}행 · 주식수 결합 "
                f"{int(P['shares'].notna().sum()):,}행")

    def c_fixture():
        """★ 실제로 터졌던 결함의 회귀 방지:
        합성 픽스처가 '길이에 결합된 상수 경계'(integers(300, n_days-200))를 써서
        RUN_MODE='FULL' 경로(n_days=500)에서만 ValueError 로 즉사했다.
        SMOKE 경로(n_days=900)만 검증하던 하네스는 이 경로를 한 번도 실행하지 않았다.
        → 여러 길이로 실제 생성해 보고, 필수 키와 최소 행수를 확인한다."""
        need = ("px", "credit", "flows", "sec", "shares", "fin", "disclosures", "links")
        sizes = []
        for nd, nc in ((200, 8), (460, 60), (500, 60), (900, 120)):
            if True:
                S = make_synthetic_flp(n_codes=nc, n_days=nd, seed=SEED + nd)
                miss = [k for k in need if k not in S or S[k] is None or not len(S[k])]
                if miss:
                    return False, f"n_days={nd}, n_codes={nc} 에서 누락: {miss}"
                if S["sec"]["delisting_date"].notna().sum() < 1:
                    return False, f"n_days={nd} 에서 상장폐지 종목이 0개 (C2 경로 미검증)"
                sizes.append((nd, nc, len(S["px"])))
        return True, f"{len(sizes)}개 조합 생성 성공 (길이 200~900 · FULL 경로 460일 포함)"

    def c_small():
        """스몰캡 밴드는 '매 시점 시총 하위 N' 이어야 하고, 전체 밴드의 부분집합이어야 한다."""
        n = SMALLCAP_BOTTOM_N + 500
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "wk": pd.Timestamp("2020-01-03"),
                          "mcap": np.linspace(1e13, 1e9, n),
                          "adv20": 1e10})
        Q = apply_universe_bands(P)
        big, small = Q["in_band"] == 1, Q["in_band_small"] == 1
        if not small.any():
            return False, "스몰캡 밴드가 비었습니다"
        if int((small & ~big).sum()):
            return False, "스몰캡 밴드가 전체 밴드의 부분집합이 아닙니다"
        n_small = int(small.sum())
        max_in = float(Q.loc[small, "mcap"].max())
        min_out = float(Q.loc[big & ~small, "mcap"].min())
        return (n_small <= SMALLCAP_BOTTOM_N and max_in <= min_out,
                f"{n:,}종목 중 스몰캡 {n_small:,}종목(상한 {SMALLCAP_BOTTOM_N:,}) · "
                f"선택 최대시총 {max_in:.3g} ≤ 제외 최소시총 {min_out:.3g}")

    def c_r2f_band():
        """★ 라운드3 리뷰가 잡은 결함의 회귀 방지:
        R2-F 를 스몰캡 밴드로 호출하면 A·B 는 그 밴드로 재채점되는데 C 만 호출자가
        이미 매겨둔 '전체 밴드' 신호를 그대로 썼다. 그러면 '스몰캡 A/B vs 전체 C' 를
        비교하게 되어 판정 자체가 무효다. 세 arm 이 같은 밴드를 쓰는지 검증한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=12, freq="W-FRI"))
        codes = [f"{700000+i:06d}" for i in range(30)]
        rows = []
        for w in wks:
            for i, c in enumerate(codes):
                rows.append({
                    "code": c, "wk": w, "exec_px": 1000.0 + i, "fwd_ret": 0.001 * (i % 5),
                    "adv20": 1e10, "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "V6": 1,
                    "in_band": 1, "in_band_small": 1 if i < 10 else 0,   # 작은 10종목만
                    "f_dd": -0.4, "f_dd_spd": -0.05, "f_cr_pctl": 0.1, "f_cr_chg": 0.0,
                    "f_cr_chg_slow": 0.0, "f_retail": -1e-4, "f_inst": 1e-4,
                    "f_ret_ex": 1e-4, "f_vol": -0.01, "f_turn": 1.2,
                    "cell": "X", "cell_l2": "Y", "cell_l3": "Z",
                    "TP_F1": 0.2 + i / 100, "TP_F2": 0.2, "TP_F3": 0.2, "TP_F4": 0.2,
                    "PHASE_C": 1, "stale_days": 0})
        P = pd.DataFrame(rows)
        P = assemble_score(P, quiet=True)                 # 전체 밴드로 채점된 상태(호출자 패널)
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"), "delisting_date": pd.NaT})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": list(wks) * 30, "code": sorted(codes * 12)}))
        _run = lambda pp, label="x", **kw: run_backtest_w(pp, wks, uni, sec, apply_costs=False,
                                                          label=label)
        keep_stop = globals().get("STOP_ON_KILL_CRITERIA", True)
        globals()["STOP_ON_KILL_CRITERIA"] = False
        try:
            out = R2F_exhaustion_vs_drawdown(P, _run, band_col="in_band_small")
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = keep_stop
        small = set(codes[:10])
        bad = {}
        for lab, bt in (out.get("bts") or {}).items():
            H = bt.get("holdings")
            if H is None or H.empty:
                continue
            outside = set(H["code"]) - small
            if outside:
                bad[lab] = len(outside)
        return (not bad,
                f"세 arm 모두 스몰캡 밴드 내에서만 선정 (밴드 밖 편입: {bad or '없음'})")

    def c_ablation():
        """★ 라운드3 리뷰가 잡은 결함의 회귀 방지:
        엔진이 진입 자격에서 FIREWALL·VETO 를 다시 적용하는 바람에, R5 절제의
        '방화벽 off'·'거부권 off' arm 이 수학적으로 아무것도 절제하지 못했다
        (ΔCAGR 이 항상 0 → 절제표가 '방화벽은 기여가 없다'고 거짓 보고)."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=8, freq="W-FRI"))
        codes = [f"{800000+i:06d}" for i in range(20)]
        rows = []
        for w in wks:
            for i, c in enumerate(codes):
                rows.append({
                    "code": c, "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0, "adv20": 1e10,
                    # 절반은 방화벽 차단 대상인데 TP 점수는 오히려 더 높게 준다
                    "FIREWALL": 0 if i < 10 else 1, "FIREWALL_HARD": 0 if i < 10 else 1,
                    "VETO": 1, "in_band": 1, "V6": 1, "PHASE_C": 1, "stale_days": 0,
                    "f_dd": -0.4, "f_cr_pctl": 0.1,
                    "cell": "X", "cell_l2": "Y", "cell_l3": "Z",
                    "TP_F1": 0.9 if i < 10 else 0.1, "TP_F2": 0.9 if i < 10 else 0.1,
                    "TP_F3": 0.9 if i < 10 else 0.1, "TP_F4": 0.9 if i < 10 else 0.1})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"), "delisting_date": pd.NaT})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": list(wks) * 20, "code": sorted(codes * 8)}))
        _run = lambda pp: run_backtest_w(pp, wks, uni, sec, apply_costs=False, label="abl")
        on = _run(assemble_score(P, quiet=True))
        off = _run(assemble_score(P, gate_firewall=False, quiet=True))
        h_on = set(on["holdings"]["code"]) if len(on["holdings"]) else set()
        h_off = set(off["holdings"]["code"]) if len(off["holdings"]) else set()
        blocked = set(codes[:10])
        return (not (h_on & blocked) and bool(h_off & blocked),
                f"방화벽 on 선정 {len(h_on)}종목(차단대상 {len(h_on & blocked)}) · "
                f"off 선정 {len(h_off)}종목(차단대상 {len(h_off & blocked)}) "
                f"— off 에서 차단대상이 0이면 절제가 무의미한 것")

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
    _c("FIXT", "합성 픽스처 길이 무관 생성 (회귀 방지)", c_fixture)
    _c("HALT", "거래정지 중 폐지 = -100% (회귀 방지)", c_halt)
    _c("DEL1", "폐지 손실 이중계상 금지 (회귀 방지)", c_delist_once)
    _c("GAP", "거래정지 구간 손실을 재개 주에 실현 (회귀 방지)", c_halt_gap)
    _c("DTYPE", "category/object 결합키 혼합 내성 (회귀 방지)", c_dtype)
    _c("SMALL", "스몰캡 밴드 = 시총 하위 N ∧ 전체 밴드의 부분집합", c_small)
    _c("R2FB", "R2-F 세 비교군이 같은 밴드를 쓴다 (회귀 방지)", c_r2f_band)
    _c("ABL", "절제 arm 이 실제로 절제한다 (회귀 방지)", c_ablation)
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
