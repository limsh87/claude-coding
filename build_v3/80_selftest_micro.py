

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-T  계약 자동검정 + 합성 스모크                                                        ║
# ║                                                                                          ║
# ║  두 검증은 서로 다른 것을 본다:                                                           ║
# ║   ① 계약검정 — 협상 불가 규칙(C1 PIT · C2 생존자편향 · C13 유니버스PIT · C14 셀 ·          ║
# ║      TP 부호 · 거부권 이진성)이 코드에 실제로 구현돼 있는가                                ║
# ║   ② 합성 스모크 — 네트워크 없이 '계산 경로 전체'가 끝까지 도는가                           ║
# ║      (수집부 한 줄 때문에 2분 만에 죽는 사고를 여기서 먼저 잡는다)                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _c(cid: str, name: str, fn):
    try:
        ok, detail = fn()
    except Exception as e:                                             # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
    CONTRACTS.append({"id": cid, "name": name, "ok": bool(ok), "detail": str(detail)})


def run_contracts() -> bool:
    CONTRACTS.clear()

    # ── C1: PIT — merge_asof 결합이 미래를 절대 보지 않는다 ────────────────────────────
    def c1():
        grid = pd.DataFrame({"corp_code": ["A"] * 4,
                             "month": pd.to_datetime(["2020-01-31", "2020-02-29",
                                                      "2020-03-31", "2020-04-30"])})
        src = pd.DataFrame({"corp_code": ["A", "A"],
                            "knowledge_date": pd.to_datetime(["2020-02-15", "2020-04-10"]),
                            "val": [1.0, 2.0]})
        m = pd.merge_asof(grid.sort_values("month"), src.sort_values("knowledge_date"),
                          left_on="month", right_on="knowledge_date", by="corp_code",
                          direction="backward")
        if pd.notna(m.loc[0, "val"]):
            return False, "1월에 2월 공시값이 보입니다 — 미래누수."
        if not (m["knowledge_date"].dropna() <= m["month"][m["knowledge_date"].notna()]).all():
            return False, "knowledge_date > month 인 행이 존재합니다."
        if float(m.loc[3, "val"]) != 2.0:
            return False, "4월에 4/10 공시가 반영되지 않았습니다."
        return True, "backward as-of 결합이 knowledge_date ≤ month 를 강제함을 확인"

    # ── C2: 상장폐지 종목 포함 + 정리매매 없으면 -100% ────────────────────────────────
    def c2():
        months = pd.date_range("2020-01-31", periods=3, freq="ME")
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["a", "b"],
                            "market": ["KOSPI"] * 2,
                            "listing_date": pd.to_datetime(["2010-01-01"] * 2),
                            "delisting_date": [pd.NaT, pd.Timestamp("2020-02-20")],
                            "industry": ["X", "X"], "corp_code": ["A", "B"], "src": ["t", "t"]})
        px = pd.DataFrame({"code": ["000001"] * 3, "date": months})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at_jan = uni.at(pd.Timestamp("2020-01-31"))
        at_mar = uni.at(pd.Timestamp("2020-03-31"))
        if "000002" not in at_jan:
            return False, "폐지 예정 종목이 폐지 전 유니버스에서 빠졌습니다 — 생존자편향."
        if "000002" in at_mar:
            return False, "폐지일 이후에도 유니버스에 남아 있습니다."
        P = pd.DataFrame({"code": ["000002"], "month": [pd.Timestamp("2020-01-31")],
                          "Signal": [1.0], "fwd_ret": [np.nan], "adv20": [1e9],
                          "VETO": [1.0], "FW": [1], "close": [1000.0], "d1_trailing": [-0.5]})
        bt = run_backtest_micro(P, pd.DatetimeIndex([pd.Timestamp("2020-01-31")]), uni,
                                "D", COST_BASE_SCENARIO, label="C2TEST", quiet=True)
        R = bt["returns"]
        if len(R) == 0:
            return False, "백테스트가 아무 행도 만들지 않았습니다."
        if float(R["ret_gross"].iloc[0]) > -0.99:
            return False, (f"정리매매가 없는 폐지 종목의 수익률이 "
                           f"{float(R['ret_gross'].iloc[0]):.3f} 입니다. -100% 여야 합니다.")
        return True, "폐지 전 포함 · 폐지 후 제외 · 정리매매 없으면 -100% 강제 확인"

    # ── C13: 유니버스는 PIT — 미래 상장 종목이 섞이지 않는다 ──────────────────────────
    def c13():
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["a", "b"],
                            "market": ["KOSPI"] * 2,
                            "listing_date": pd.to_datetime(["2010-01-01", "2023-05-01"]),
                            "delisting_date": [pd.NaT, pd.NaT], "industry": ["X", "X"],
                            "corp_code": ["A", "B"], "src": ["t", "t"]})
        px = pd.DataFrame({"code": ["000001"] * 3,
                           "date": pd.date_range("2020-01-31", periods=3, freq="ME")})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        if "000002" in uni.at(pd.Timestamp("2020-06-30")):
            return False, "2023년 상장 종목이 2020년 유니버스에 있습니다 — 미래누수."
        # 랭크가 시점별로 재산출되는지 (현재 시총을 과거에 적용하지 않는다)
        pm = pd.DataFrame({"code": ["000001", "000002"] * 2,
                           "month": [pd.Timestamp("2020-01-31")] * 2 + [pd.Timestamp("2020-02-29")] * 2,
                           "close": [100.0, 200.0, 300.0, 50.0]})
        snap = pd.DataFrame({"snap_date": pd.to_datetime(["2019-12-31"] * 2),
                             "code": ["000001", "000002"], "shares": [10.0, 10.0],
                             "mcap": [np.nan, np.nan], "src": ["t", "t"]})
        M = build_mcap_panel(pm, snap, sec, pd.DatetimeIndex(sorted(pm["month"].unique())))
        r1 = M[M["month"] == pd.Timestamp("2020-01-31")].set_index("code")["mcap_rank"]
        r2 = M[M["month"] == pd.Timestamp("2020-02-29")].set_index("code")["mcap_rank"]
        if not (r1["000001"] > r1["000002"] and r2["000001"] < r2["000002"]):
            return False, "시총 랭크가 시점별로 재산출되지 않습니다 — 현재 시총의 과거 적용."
        return True, "미래 상장 배제 + 시총 랭크의 시점별 재산출 확인 (C13-a)"

    # ── C14: 셀 키에 size_bucket 이 없다 ──────────────────────────────────────────────
    def c14():
        if "size_bucket" in CELL_MICRO:
            return False, "CELL_MICRO 에 size_bucket 이 들어 있습니다(C14-a 위반)."
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(60)],
                          "month": pd.Timestamp("2020-06-30"),
                          "close": 1000.0})
        sec = pd.DataFrame({"code": P["code"], "industry": ["전자부품 제조업"] * 30 + ["의료기기"] * 30})
        Q = build_cells_micro(P, sec, min_n=20)
        s = str(Q["cell"].iloc[0])
        if "|" not in s or len(s.split("|")) != 2:
            return False, f"셀 키 형식이 (연월|업종) 이 아닙니다: {s}"
        if any("size" in str(c).lower() for c in Q.columns if c.startswith("cell")):
            return False, "셀 컬럼에 규모 정보가 섞였습니다."
        return True, f"셀 키 = (연월|업종) 확인 · 예: {s}"

    # ── TP 부호: clip(z,0)×clip(z,0) — 저-저 사분면이 최고점을 받지 않는다 ────────────
    def tpsign():
        n = 40
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": pd.Timestamp("2020-06-30"),
            "cell": "202006|X", "cell_l2": "202006|X", "cell_l3": "202006|ALL",
            "a": np.linspace(-1, 1, n), "b": np.linspace(-1, 1, n)})
        # 마지막 행: 둘 다 최저(저-저). 첫 행보다 점수가 높으면 부호 버그.
        P.loc[n - 1, ["a", "b"]] = [-5.0, -5.0]
        P.loc[n - 2, ["a", "b"]] = [5.0, 5.0]
        t = tp_micro(P, "a", "b")
        lowlow, highhigh = float(t.iloc[n - 1]), float(t.iloc[n - 2])
        if not (lowlow <= 1e-9):
            return False, (f"저-저 사분면 점수가 {lowlow:.4f} 입니다. 0 이어야 합니다 — "
                           f"z×z 를 쓰면 '양쪽 다 나쁨'이 최고점을 받습니다(원칙 2 위반).")
        if not (highhigh > lowlow):
            return False, "고-고 사분면이 저-저보다 높지 않습니다."
        # 고-저(한쪽만 좋음)는 0 이어야 한다
        P2 = P.copy()
        P2.loc[0, ["a", "b"]] = [5.0, -5.0]
        t2 = tp_micro(P2, "a", "b")
        if float(t2.iloc[0]) > 1e-9:
            return False, "한쪽만 개선된 경우에 점수가 났습니다 — 대가를 치렀는데 보상했습니다."
        return True, f"저-저={lowlow:.3f} · 고-고={highhigh:.3f} · 고-저=0 확인 (clip 곱)"

    # ── 거부권 이진성 (C6) ───────────────────────────────────────────────────────────
    def veto():
        P = pd.DataFrame({"code": ["000001", "000002", "000003"],
                          "month": pd.Timestamp("2020-06-30"), "corp_code": ["A", "B", "C"],
                          "v1_pushout": [1.0, 0.0, 0.0], "v2_bad_3q": [0.0, 1.0, 0.0],
                          "adv20": [1e9, 1e9, 1.0], "is_trading_halted": [0.0, 0.0, 0.0],
                          "shares": [np.nan] * 3})
        Q = apply_vetoes_micro(P, None)
        vals = set(pd.unique(Q[["V1", "V2", "V3", "V6"]].to_numpy().ravel()))
        if not vals <= {0.0, 1.0}:
            return False, f"거부권이 이진이 아닙니다: {sorted(vals)}"
        if float(Q["VETO"].iloc[0]) != 0.0 or float(Q["VETO"].iloc[2]) != 0.0:
            return False, "거부권이 곱으로 적용되지 않았습니다(상쇄 발생)."
        return True, "V1/V2/V3/V6 이진값 · 곱 적용 · 상쇄 불가 확인"

    # ── 선정 랭크가 원점수의 단조함수인가 (월 전체 기준) ──────────────────────────────
    def rankmono():
        n = 50
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "month": pd.Timestamp("2020-06-30"),
                          "E_micro": np.linspace(0, 1, n), "U_micro": 1.0,
                          "FW": 1, "VETO": 1.0, "adv20": 1e9})
        S = assemble_signal(P, "D")
        d = S[["Signal", "Signal_rank"]].dropna()
        rho = float(np.corrcoef(d["Signal"].rank(), d["Signal_rank"].rank())[0, 1])
        if not rho > 0.999:
            return False, f"Signal_rank 가 Signal 의 단조함수가 아닙니다 (ρ={rho:.4f})."
        return True, f"월 전체 백분위 · 단조성 ρ={rho:.4f} 확인"

    # ── 비용 단조성: 비용이 커지면 수익률은 낮아져야 한다 ────────────────────────────
    def costmono():
        months = pd.date_range("2020-01-31", periods=6, freq="ME")
        rows = []
        for m in months:
            for i in range(10):
                rows.append({"code": f"{i:06d}", "month": m, "Signal": 1.0 - i * 0.05,
                             "fwd_ret": 0.01, "adv20": 1e9, "VETO": 1.0, "FW": 1,
                             "close": 1000.0, "d1_trailing": -0.5})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": [f"{i:06d}" for i in range(10)], "name": "x",
                            "market": "KOSPI", "listing_date": pd.Timestamp("2010-01-01"),
                            "delisting_date": pd.NaT, "industry": "X",
                            "corp_code": [f"C{i}" for i in range(10)], "src": "t"})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000000"] * 6, "date": months}))
        a = run_backtest_micro(P, months, uni, "D", "낙관", label="c1", quiet=True)
        b = run_backtest_micro(P, months, uni, "D", "비관", label="c2", quiet=True)
        if not (a["stats"]["cagr"] > b["stats"]["cagr"]):
            return False, (f"비용이 큰 시나리오의 수익률이 더 높습니다 "
                           f"(낙관 {a['stats']['cagr']:.4f} vs 비관 {b['stats']['cagr']:.4f}).")
        return True, (f"낙관 {100*a['stats']['cagr']:.2f}% > 비관 "
                      f"{100*b['stats']['cagr']:.2f}% — 비용 모형 단조성 확인")

    _c("C1", "PIT (미래누수 차단)", c1)
    _c("C2", "생존자편향 제거 · 상폐 -100%", c2)
    _c("C13", "유니버스 PIT · 랭크 시점별 재산출", c13)
    _c("C14", "셀 = (연월, 업종) · size_bucket 금지", c14)
    _c("TP", "TP 부호 (clip 곱, z×z 금지)", tpsign)
    _c("V", "거부권 이진 · 곱 · 상쇄불가", veto)
    _c("RANK", "선정 랭크 정합성", rankmono)
    _c("COST", "비용 모형 단조성", costmono)

    LOG.table([[r["id"], r["name"], "✔ 통과" if r["ok"] else "✘ 실패", _trunc(r["detail"], 66)]
               for r in CONTRACTS], ["ID", "계약", "판정", "상세"], ["c", "l", "c", "l"], maxw=70,
              title="계약 자동검정 — 협상 불가 규칙이 코드에 실제로 있는가")
    bad = [r["id"] for r in CONTRACTS if not r["ok"]]
    if bad:
        LOG.error(f"계약 위반 {len(bad)}건: {bad}")
        if STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"계약 위반으로 중단합니다: {bad}. 위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS)}건 전부 통과.")
    return True


# ── 합성 데이터 ─────────────────────────────────────────────────────────────────────────────
def synth_context(months: pd.DatetimeIndex, n_codes: int = 140) -> dict:
    """네트워크 없이 전체 계산 경로를 도는 합성 데이터셋.

    실데이터와 '같은 스키마'를 만든다. 스키마가 다르면 스모크는 통과하고 실행은 죽는다.
    """
    rng = np.random.default_rng(SEED)
    codes = [f"{i+1:06d}" for i in range(n_codes)]
    inds = ["전자부품 제조업", "의료기기 제조업", "소프트웨어 개발", "화학물질 제조",
            "기계장비 제조", "식료품 제조"]
    start = pd.Timestamp(months[0]) - pd.DateOffset(months=18)
    end = pd.Timestamp(months[-1]) + pd.offsets.MonthEnd(1)

    # 종목 마스터 — 10% 는 기간 중 상장폐지, 10% 는 기간 중 신규 상장
    ld = [start - pd.Timedelta(days=int(rng.integers(400, 4000))) for _ in codes]
    dd: List[Any] = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        dd[i] = pd.Timestamp(months[int(rng.integers(12, len(months) - 1))])
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        ld[i] = pd.Timestamp(months[int(rng.integers(2, max(3, len(months) // 2)))])
    sec = pd.DataFrame({
        "code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
        "market": ["KOSDAQ"] * n_codes, "listing_date": ld, "delisting_date": dd,
        "industry": [inds[i % len(inds)] for i in range(n_codes)],
        "corp_code": [f"{i+1:08d}" for i in range(n_codes)], "src": ["synth"] * n_codes})

    # 일봉 — 소형주 성격(고변동), 일부 종목에 지속적 드리프트를 심어 신호가 잡히게 한다
    bdays = pd.bdate_range(start, end)
    good = set(rng.choice(codes, size=n_codes // 5, replace=False))
    px_rows = []
    for c, l, d in zip(codes, ld, dd):
        mask = (bdays >= pd.Timestamp(l)) & (bdays <= (pd.Timestamp(d) if pd.notna(d) else end))
        dts = bdays[mask]
        if len(dts) < 60:
            continue
        drift = 0.0009 if c in good else 0.0
        r = rng.normal(drift, 0.030, len(dts))
        close = 3000 * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.0, 0.7, len(dts))
        px_rows.append(pd.DataFrame({
            "code": c, "date": dts, "open": close * (1 + rng.normal(0, 0.004, len(dts))),
            "high": close * 1.02, "low": close * 0.98, "close": close,
            "volume": vol, "amount": vol * close, "src": "synth"}))
    px = pd.concat(px_rows, ignore_index=True) if px_rows else pd.DataFrame(columns=PRICE_COLS)

    # 시총 스냅샷 (분기)
    snaps = []
    for d in _snapshot_grid(months):
        for c in codes:
            snaps.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                          "shares": float(rng.integers(3_000_000, 40_000_000)),
                          "mcap": np.nan, "src": "synth"})
    snap = pd.DataFrame(snaps)

    # DART 원시 계정 (tidy_financials 를 실제로 통과시킨다 — 스키마 검증 목적)
    accs = [("revenue", "IS", "ifrs-full_Revenue", "매출액"),
            ("cogs", "IS", "ifrs-full_CostOfSales", "매출원가"),
            ("op_income", "IS", "dart_OperatingIncomeLoss", "영업이익"),
            ("net_income", "IS", "ifrs-full_ProfitLoss", "당기순이익"),
            ("interest_expense", "IS", "ifrs-full_FinanceCosts", "금융원가"),
            ("tax_expense", "IS", "ifrs-full_IncomeTaxExpense", "법인세비용"),
            ("inventory", "BS", "ifrs-full_Inventories", "재고자산"),
            ("receivable", "BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권"),
            ("assets", "BS", "ifrs-full_Assets", "자산총계"),
            ("equity", "BS", "ifrs-full_Equity", "자본총계"),
            ("capital_stock", "BS", "ifrs-full_IssuedCapital", "자본금"),
            ("cfo", "CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름")]
    rc_codes = list(REPRT_CODES.values())
    fs_rows = []
    y0, y1 = int(months[0].year) - 1, int(months[-1].year)
    for i, c in enumerate(codes):
        base_rev = float(rng.integers(20_000, 300_000)) * 1e6
        grow = 0.05 + (0.14 if c in good else 0.0) + rng.normal(0, 0.03)
        for y in range(y0, y1 + 1):
            rev_y = base_rev * ((1 + grow) ** (y - y0))
            for qi, rc in enumerate(rc_codes, start=1):
                cum = rev_y * qi / 4.0
                vals = {
                    "revenue": cum, "cogs": cum * (0.72 - (0.03 if c in good else 0.0)),
                    "op_income": cum * 0.08, "net_income": cum * 0.055,
                    "interest_expense": cum * 0.010, "tax_expense": cum * 0.012,
                    "inventory": rev_y * (0.14 - (0.02 if c in good else 0.0)),
                    "receivable": rev_y * (0.17 - (0.02 if c in good else 0.0)),
                    "assets": rev_y * 1.4, "equity": rev_y * 0.65,
                    "capital_stock": rev_y * 0.12,
                    "cfo": cum * (0.070 if c in good else 0.035)}
                mm, dd_ = REPRT_PERIOD_END[rc]
                rcpt = (pd.Timestamp(year=y, month=mm, day=dd_)
                        + pd.Timedelta(days=REPRT_DEADLINE_DAYS[rc])).strftime("%Y%m%d")
                for key, sj, aid, anm in accs:
                    fs_rows.append({"corp_code": f"{i+1:08d}", "bsns_year": str(y),
                                    "reprt_code": rc, "rcept_no": rcpt + "000001",
                                    "fs_div": "CFS", "sj_div": sj, "account_id": aid,
                                    "account_nm": anm,
                                    "thstrm_amount": f"{vals[key]:,.0f}"})
    fs = pd.DataFrame(fs_rows)

    # 시장조치 · 공시 · 리포트
    act_rows, dis_rows = [], []
    for i in rng.choice(n_codes, size=max(2, n_codes // 12), replace=False):
        t = pd.Timestamp(months[int(rng.integers(6, len(months) - 6))])
        act_rows.append({"corp_code": f"{i+1:08d}", "rcept_dt": t,
                         "report_nm": "관리종목 지정", "action": "watch_on"})
        act_rows.append({"corp_code": f"{i+1:08d}", "rcept_dt": t + pd.DateOffset(months=8),
                         "report_nm": "관리종목 지정 해제", "action": "watch_off"})
    for i in rng.choice(n_codes, size=max(2, n_codes // 10), replace=False):
        t = pd.Timestamp(months[int(rng.integers(3, len(months) - 3))])
        dis_rows.append({"corp_code": f"{i+1:08d}", "rcept_no": f"S{i:09d}", "rcept_dt": t,
                         "report_nm": "유상증자결정", "event": "rights_issue",
                         "event_date": t, "knowledge_date": t})
    actions = pd.DataFrame(act_rows) if act_rows else pd.DataFrame(
        columns=["corp_code", "rcept_dt", "report_nm", "action"])
    dis = pd.DataFrame(dis_rows) if dis_rows else pd.DataFrame(
        columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event",
                 "event_date", "knowledge_date"])

    rep_rows = []
    for i in rng.choice(n_codes, size=max(4, n_codes // 4), replace=False):
        for _ in range(int(rng.integers(1, 5))):
            t = pd.Timestamp(months[int(rng.integers(0, len(months)))])
            rep_rows.append({"code": codes[i], "corp_name": f"합성{i+1:03d}",
                             "analyst": f"애널{int(rng.integers(1, 30)):02d}",
                             "broker": "합성증권", "target_price": float(rng.integers(3000, 20000)),
                             "opinion": "매수", "event_date": t, "knowledge_date": t,
                             "source": "synth", "title": "합성 리포트"})
    rep = pd.DataFrame(rep_rows)

    return {"sec": sec, "px": px, "snap": snap, "fs": fs, "actions": actions,
            "dis": dis, "rep": rep, "analysts": pd.DataFrame(), "links": pd.DataFrame(),
            "synthetic": True}
