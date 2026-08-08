

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
        months = pd.date_range("2020-01-31", periods=3, freq=pd.offsets.MonthEnd())
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
        H = bt["holdings"]
        if H is None or len(H) == 0:
            return False, "백테스트가 보유내역을 만들지 않았습니다."
        # ★ 포트폴리오 수익률이 아니라 '그 종목의' 수익률이 -100% 여야 한다.
        #   포트폴리오 수익률은 비중(용량 상한·현금)에 좌우되므로 C2 의 판정 대상이 아니다.
        pos = float(H["fwd_ret"].iloc[0])
        if pos > -0.999:
            return False, (f"정리매매가 없는 폐지 종목의 종목수익률이 {pos:.3f} 입니다. "
                           f"-100% 여야 합니다.")
        return True, (f"폐지 전 포함 · 폐지 후 제외 · 정리매매 없으면 종목수익률 "
                      f"{pos:.0%} 강제 확인")

    # ── C13: 유니버스는 PIT — 미래 상장 종목이 섞이지 않는다 ──────────────────────────
    def c13():
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["a", "b"],
                            "market": ["KOSPI"] * 2,
                            "listing_date": pd.to_datetime(["2010-01-01", "2023-05-01"]),
                            "delisting_date": [pd.NaT, pd.NaT], "industry": ["X", "X"],
                            "corp_code": ["A", "B"], "src": ["t", "t"]})
        px = pd.DataFrame({"code": ["000001"] * 3,
                           "date": pd.date_range("2020-01-31", periods=3, freq=pd.offsets.MonthEnd())})
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
        months = pd.date_range("2020-01-31", periods=6, freq=pd.offsets.MonthEnd())
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

    # ── 시장조치 상태 복원: 해제가 먼저 관측돼도 이후 지정이 살아야 한다 ──────────────
    def watchstate():
        ev = pd.DataFrame({
            "code": ["000001"] * 3,
            "rcept_dt": pd.to_datetime(["2017-03-15", "2018-06-20", "2019-02-10"]),
            "action": ["watch_off", "watch_on", "watch_off"]})
        S = _step_state(ev, "watch_on", "watch_off", "code")
        m = dict(zip(S["knowledge_date"], S["state"]))
        if int(m[pd.Timestamp("2018-06-20")]) != 1:
            return False, ("이력 시작 전 지정 때문에 이후의 진짜 '관리종목 지정'이 0 으로 "
                           "읽힙니다 — 누적합 방식의 고질적 버그입니다.")
        if int(m[pd.Timestamp("2019-02-10")]) != 0:
            return False, "해제 이벤트가 상태를 끄지 못했습니다."
        return True, "해제 선행 이력에서도 이후 지정이 정상 복원됨 (최근 이벤트 기준)"

    # ── 단발 사건(감사의견 비적정)의 만료가 나중 사건을 끄면 안 된다 ────────────────────
    def oneshot():
        ev = pd.DataFrame({"code": ["000001"] * 2,
                           "rcept_dt": pd.to_datetime(["2019-03-20", "2020-03-25"]),
                           "action": ["audit_bad", "audit_bad"]})
        S = _one_shot_state(ev, "audit_bad", "code", valid_days=400)
        S = S.sort_values("knowledge_date")
        probe = pd.Timestamp("2020-06-30")
        st = S[S["knowledge_date"] <= probe]["state"].iloc[-1]
        if int(st) != 1:
            return False, ("2020-03 비적정 이후인데 2019 건의 만료행이 상태를 꺼 버렸습니다 "
                           "(만료는 누적 최댓값이어야 합니다).")
        return True, "연속 단발 사건에서 나중 사건이 앞 사건의 만료에 지워지지 않음"

    # ── ★ 그 반대 방향이 더 위험하다: 미래 사건이 과거 상태를 켜면 안 된다(C1) ──────────
    def oneshot_pit():
        """2017년 사건 + 2024년 사건 → 2019년의 상태는 반드시 0.

        예전 구현은 만료행을 '종목별 마지막 만료' 하나로 접었다. 그러면 2017-03 부터
        2025-03 까지 97개월이 통째로 켜진다 — 2019년 패널이 '감사의견 비적정'이라고
        말하는 근거가 5년 뒤에야 존재할 공시다. 방향도 나쁘다(나중에 망할 기업을 미리
        배제 → 성과 과대). 위 oneshot 검정만으로는 이 실패를 절대 잡지 못한다.
        """
        ev = pd.DataFrame({"code": ["000001"] * 2,
                           "rcept_dt": pd.to_datetime(["2017-03-20", "2024-03-20"]),
                           "action": ["audit_bad", "audit_bad"]})
        S = _one_shot_state(ev, "audit_bad", "code", valid_days=400).sort_values("knowledge_date")
        probe = pd.Timestamp("2019-06-30")
        prior = S[S["knowledge_date"] <= probe]
        st = int(prior["state"].iloc[-1]) if len(prior) else 0
        if st != 0:
            return False, ("2019-06 시점의 상태가 1 입니다 — 2024년 공시가 과거를 켰습니다. "
                           "미래누수(C1) 입니다.")
        after = S[S["knowledge_date"] <= pd.Timestamp("2024-06-30")]
        if not len(after) or int(after["state"].iloc[-1]) != 1:
            return False, "2024-03 사건 직후 상태가 1 이 아닙니다(만료 처리가 과했습니다)."
        return True, "7년 간격 단발 사건: 2019-06=0 · 2024-06=1 — 미래가 과거를 바꾸지 않음"

    # ── DART 전기 비교치 파싱 · 분기금액 누적여부 자동판정 ──────────────────────────────
    def comparatives():
        """이 전략의 증거층 전체가 여기에 걸려 있다.

        ① 분기 손익금액이 '3개월 단독'인데 누적으로 오인하면 차분이 음수·양수를 오가며
           TTM 이 무의미해진다(반대로 오인하면 매출이 계단식으로 튄다). 둘 다 에러 없이
           값만 틀린다 → 데이터로 판정하는지 검정한다.
        ② 연 1회만 공시하는 기업(U-MICRO 에 흔하다)의 전기 비교치가 비면 i_sales 가
           통째로 결측이 되고 C14-c 로 증거층이 죽는다 → 사업보고서 단독 이력으로 검정한다.
        """
        FY, Q1, H1, Q3 = (REPRT_CODES["FY"], REPRT_CODES["Q1"],
                          REPRT_CODES["H1"], REPRT_CODES["Q3"])

        def _row(cc, y, rc, cum, pcum, th, fr):
            return {"corp_code": cc, "bsns_year": y, "reprt_code": rc, "fs_div": "CFS",
                    "sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액",
                    "thstrm_amount": f"{th:,.0f}",
                    "thstrm_add_amount": ("" if cum is None else f"{cum:,.0f}"),
                    "frmtrm_amount": f"{fr:,.0f}",
                    "frmtrm_q_amount": "", "bfefrmtrm_amount": "",
                    "frmtrm_add_amount": ("" if pcum is None else f"{pcum:,.0f}"),
                    "rcept_no": f"{y}0515000001"}

        rows = []
        for y in (2022, 2023, 2024):
            ann, prev = 1000.0 * (1.10 ** (y - 2022)), 1000.0 * (1.10 ** (y - 2023))
            # 분기 제출 기업: 당기금액=3개월 단독, 당기누적=YTD (실제 DART 형식)
            for q, rc in ((1, Q1), (2, H1), (3, Q3)):
                rows.append(_row("00000001", y, rc, ann * q / 4, prev * q / 4,
                                 ann / 4, prev / 4))
            rows.append(_row("00000001", y, FY, None, None, ann, prev))
            # 연 1회 제출 기업: 사업보고서만
            rows.append(_row("00000002", y, FY, None, None, ann, prev))
        W = tidy_financials(pd.DataFrame(rows))
        if W is None or not len(W):
            return False, "tidy_financials 가 빈 프레임을 돌려주었습니다."
        Q = add_micro_sensors_quarterly(W)
        exp = float(np.log(1.10))
        out = []
        for cc, label in (("00000001", "분기제출"), ("00000002", "연1회제출")):
            r = Q[(Q["corp_code"] == cc) & (Q["reprt_code"] == FY) & (Q["bsns_year"] == 2024)]
            if not len(r):
                return False, f"{label} 기업의 2024 사업보고서 행이 없습니다."
            v = float(pd.to_numeric(r["i_sales"], errors="coerce").iloc[0])
            if not np.isfinite(v):
                return False, (f"{label} 기업의 i_sales 가 결측입니다 — 전기 비교치가 "
                               f"파싱되지 않았습니다(연 1회 제출 기업이 죽는 경로).")
            if abs(v - exp) > 0.02:
                return False, (f"{label} 기업의 i_sales={v:.4f} 이 기대값 {exp:.4f}(=log1.10)과 "
                               f"다릅니다. 누적/3개월 오인 또는 lag4 가 여러 해를 건너뛴 결과입니다.")
            out.append(f"{label} {v:.4f}")
        # 3개월 단독 → 누적 복원이 맞으면 FY 의 TTM 이 연간과 같아야 한다
        r1 = Q[(Q["corp_code"] == "00000001") & (Q["reprt_code"] == FY) &
               (Q["bsns_year"] == 2024)]
        ttm = float(pd.to_numeric(r1["revenue_ttm"], errors="coerce").iloc[0])
        ann24 = 1000.0 * (1.10 ** 2)
        if not np.isfinite(ttm) or abs(ttm - ann24) > ann24 * 0.02:
            return False, (f"3개월 단독 공시의 누적 복원이 틀렸습니다 — TTM {ttm:,.0f} vs "
                           f"연간 {ann24:,.0f}.")
        return True, f"i_sales({' · '.join(out)}) = log1.10 · 3개월→TTM 복원 일치"

    # ── 거래정지→수개월 뒤 상장폐지 경로도 -100% 여야 한다 ─────────────────────────────
    def delist_gap():
        months = pd.date_range("2019-04-30", periods=2, freq=pd.offsets.MonthEnd())
        sec = pd.DataFrame({"code": ["000002"], "name": ["b"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2010-01-01")],
                            "delisting_date": [pd.Timestamp("2020-03-15")],
                            "industry": ["X"], "corp_code": ["B"], "src": ["t"]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000002"] * 2, "date": months}))
        P = pd.DataFrame({"code": ["000002"], "month": [months[0]], "Signal": [1.0],
                          "fwd_ret": [np.nan], "adv20": [1e9], "VETO": [1.0], "FW": [1],
                          "close": [1000.0], "d1_trailing": [-0.5]})
        bt = run_backtest_micro(P, pd.DatetimeIndex([months[0]]), uni, "D",
                                COST_BASE_SCENARIO, label="DGAP", quiet=True)
        H = bt["holdings"]
        r = float(H["fwd_ret"].iloc[0]) if H is not None and len(H) else 0.0
        if r > -0.999:
            return False, (f"거래정지 후 수개월 뒤 상장폐지되는 종목의 종목수익률이 {r:.3f} "
                           f"입니다. 폐지월 창만 보면 이 경로가 0% 로 계상되어 생존자편향이 "
                           f"재유입됩니다.")
        return True, "거래 중단 시점에 종목수익률 -100% 확정 (폐지일이 몇 달 뒤여도 동일)"

    # ── 적자기업이 많은 셀에서 밸류 랭크가 통째로 무효화되면 안 된다 ────────────────────
    def valuecell():
        n = 30
        # 30종목 중 22개가 적자(E/P 음수). 싼 흑자기업(0번)과 비싼 적자기업(29번)을 비교한다.
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)], "month": pd.Timestamp("2020-06-30"),
            "cell": "202006|X", "cell_l2": "202006|X", "cell_l3": "202006|ALL",
            "bp": np.linspace(3.0, 0.3, n),
            "ep": [0.30 - 0.02 * i if i < 8 else -0.05 - 0.01 * i for i in range(n)]})
        vr = value_rank_micro(P)
        if vr.isna().all():
            return False, ("셀에 적자기업이 많다는 이유로 밸류 랭크가 전원 NaN 이 되었습니다. "
                           "그러면 방화벽의 딥밸류 조항이 흑자기업까지 전원 배제합니다.")
        if not (float(vr.iloc[0]) < float(vr.iloc[n - 1])):
            return False, "저PBR·흑자 기업이 고PBR·적자 기업보다 싸게 평가되지 않았습니다."
        return True, (f"적자 {n-8}/{n} 인 셀에서도 밸류 랭크 유효 "
                      f"(최저 {float(vr.min()):.2f} · 최고 {float(vr.max()):.2f})")

    # ── R2-M 구성 분리: B(증거층만)에는 방화벽·거부권이 남아 있으면 안 된다 ─────────────
    def variantsep():
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(10)],
                          "month": pd.Timestamp("2020-06-30"),
                          "E_micro": np.linspace(0, 1, 10), "U_micro": 1.0,
                          "FW": [0] * 5 + [1] * 5, "VETO": [0.0] * 5 + [1.0] * 5,
                          "adv20": 1e9})
        B = assemble_signal(P, "B")
        if not (B["FW"] == 1).all() or not (B["VETO"] == 1.0).all():
            return False, ("B 구성에 방화벽/거부권 컬럼이 남아 백테스트의 보유 판정에서 "
                           "강제 청산을 일으킵니다 — 정의상 B 가 아니라 C 가 됩니다.")
        D = assemble_signal(P, "D")
        if int(D["FW"].sum()) != 5:
            return False, "D 구성에서 방화벽이 중립화되었습니다."
        return True, "B 는 방화벽·거부권 중립화 · D 는 유지 — 구성 간 분리 확인"

    # ── §10 런타임 예산: 예산을 넘길 것을 알면서 시작하면 안 된다 ──────────────────────
    def budget_guard():
        """실제 사고 재현: 전 종목 단건 수집은 187,920회 = 약 10일. 그걸 시작했었다."""
        corps = [f"{i:08d}" for i in range(3915)]
        years = list(range(2015, 2027))
        plan = plan_dart_collection(corps, years, budget_min=DART_BUDGET_MIN)
        if plan["need_single"] <= plan["cap"]:
            return False, ("전 종목 단건 수집이 예산 안이라고 판정됐습니다 — 견적식이 잘못됐습니다.")
        if plan["need_batch"] > plan["need_single"] / 10:
            return False, "배치 경로가 단건 대비 충분히 싸지 않습니다(배치 산식 오류)."
        if MAX_WALLCLOCK_MIN > 240:
            return False, f"MAX_WALLCLOCK_MIN={MAX_WALLCLOCK_MIN} — 계약 상한(240분)을 넘겼습니다."
        return True, (f"단건 {plan['need_single']:,}회는 예산 {plan['cap']:,}회의 "
                      f"{plan['need_single']/max(plan['cap'],1):.0f}배 → 시작하지 않고 "
                      f"배치({plan['need_batch']:,}회)로 내려감 · 상한 {MAX_WALLCLOCK_MIN}분")

    # ── KRX 차단 페이지를 데이터로 착각하지 않는다 ────────────────────────────────────
    def krx_block_detect():
        html = ('<html><head><title>에러페이지 - 한국거래소 | Data Marketplace</title></head>'
                '<body><div class="ip-block-page"><h1>KRX Data Marketplace</h1>'
                '<h2>KDM 이용 제한 안내</h2><p>자동화 수단을 통한 비정상 대량 조회가 '
                '감지되어 해당 IP의 접속이 일시적으로 제한되었습니다.</p></div></body></html>')
        before = dict(KRX_BLOCK)
        try:
            KRX_BLOCK["blocked"], KRX_BLOCK["until"], KRX_BLOCK["logged"] = False, 0.0, True
            if not _check_krx_block("krx", html):
                return False, ("KRX 차단 안내 페이지를 데이터로 취급했습니다. 차단은 200 OK 로 "
                               "오므로, 못 잡으면 계속 요청해 제한이 연장됩니다.")
            if not krx_blocked():
                return False, "차단을 감지했는데 이후 요청이 막히지 않았습니다."
            if _check_krx_block("naver", html):
                return False, "KRX 가 아닌 소스의 응답까지 차단으로 오인했습니다."
            return True, "차단 페이지 감지 → 이번 실행 KRX 전면 중단 + 마커 저장 확인"
        finally:
            KRX_BLOCK.update(before)

    _c("BUDGET", "런타임 예산 강제 (§10)", budget_guard)
    _c("KRXBLK", "KRX 차단 페이지 감지", krx_block_detect)
    _c("C1", "PIT (미래누수 차단)", c1)
    _c("C2", "생존자편향 제거 · 상폐 -100%", c2)
    _c("C13", "유니버스 PIT · 랭크 시점별 재산출", c13)
    _c("C14", "셀 = (연월, 업종) · size_bucket 금지", c14)
    _c("TP", "TP 부호 (clip 곱, z×z 금지)", tpsign)
    _c("V", "거부권 이진 · 곱 · 상쇄불가", veto)
    _c("RANK", "선정 랭크 정합성", rankmono)
    _c("COST", "비용 모형 단조성", costmono)
    _c("WATCH", "관리종목 상태 복원 (해제 선행)", watchstate)
    _c("AUDIT", "단발 사건 만료 누적 최댓값", oneshot)
    _c("APIT", "단발 사건 미래→과거 누수 금지", oneshot_pit)
    _c("COMPAR", "DART 전기 비교치 · 누적 자동판정", comparatives)
    # ── 폐지일을 아예 모르는 종목의 거래중단도 -100% 여야 한다 ──────────────────────────
    def delist_nomap():
        months = pd.date_range("2019-04-30", periods=2, freq=pd.offsets.MonthEnd())
        sec = pd.DataFrame({"code": ["000003", "000004"], "name": ["c", "d"],
                            "market": ["KOSDAQ"] * 2,
                            "listing_date": [pd.Timestamp("2010-01-01")] * 2,
                            "delisting_date": [pd.NaT, pd.NaT],   # ★ 둘 다 폐지목록에 없다
                            "industry": ["X", "X"], "corp_code": ["C", "D"], "src": ["t", "t"]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000004"] * 2, "date": months}))
        # 000003 은 1개월차까지만 패널에 있고(수익률 결측) 2개월차에 사라진다 = 거래 중단.
        # 000004 는 계속 살아 있어 '패널 자체의 공백'과 구분된다(그 경우엔 0% 가 맞다).
        P = pd.DataFrame({
            "code": ["000003", "000004", "000004"],
            "month": [months[0], months[0], months[1]],
            "Signal": [1.0, 0.9, 0.9], "fwd_ret": [np.nan, 0.0, 0.0],
            "adv20": [1e9] * 3, "VETO": [1.0] * 3, "FW": [1] * 3,
            "close": [1000.0] * 3, "d1_trailing": [-0.5] * 3})
        bt = run_backtest_micro(P, pd.DatetimeIndex(months), uni, "D",
                                COST_BASE_SCENARIO, label="DNOMAP", quiet=True)
        H = bt["holdings"]
        if H is None or len(H) == 0:
            return False, "백테스트가 보유내역을 만들지 않았습니다."
        h0 = H[(H["month"] == months[0]) & (H["code"] == "000003")]
        r = float(h0["fwd_ret"].iloc[0]) if len(h0) else 0.0
        if r > -0.999:
            return False, (f"폐지목록에 없는 종목이 거래를 멈췄는데 종목수익률이 {r:.3f} 입니다. "
                           f"0% 로 계상하면 폐지목록 커버리지가 나쁠수록 성과가 좋아집니다.")
        return True, "폐지일 미상 + 다음 달 패널 이탈 → 종목수익률 -100% 확정"

    _c("DLGAP", "정지→지연 상장폐지 -100%", delist_gap)
    _c("DLNOM", "폐지일 미상 종목의 거래중단 -100%", delist_nomap)
    _c("VALUE", "적자 다수 셀의 밸류 랭크 생존", valuecell)
    _c("VSEP", "R2-M 구성 분리 (B ≠ C)", variantsep)

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
            ("current_assets", "BS", "ifrs-full_CurrentAssets", "유동자산"),
            ("current_liab", "BS", "ifrs-full_CurrentLiabilities", "유동부채"),
            ("equity", "BS", "ifrs-full_Equity", "자본총계"),
            ("capital_stock", "BS", "ifrs-full_IssuedCapital", "자본금"),
            ("cfo", "CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름")]
    _FLOW_SJ = {"IS", "CIS", "CF"}
    rc_codes = list(REPRT_CODES.values())
    _FY = REPRT_CODES["FY"]
    fs_rows = []
    y0, y1 = int(months[0].year) - 1, int(months[-1].year)

    def _vals_at(base_rev, grow, c, y, qi):
        """qi=1..4 시점의 (누적 손익, 기말 잔액). qi=4 는 연간."""
        rev_y = base_rev * ((1 + grow) ** (y - y0))
        cum = rev_y * qi / 4.0
        return rev_y, {
            "revenue": cum, "cogs": cum * (0.72 - (0.03 if c in good else 0.0)),
            "op_income": cum * 0.08, "net_income": cum * 0.055,
            "interest_expense": cum * 0.010, "tax_expense": cum * 0.012,
            "inventory": rev_y * (0.14 - (0.02 if c in good else 0.0)),
            "receivable": rev_y * (0.17 - (0.02 if c in good else 0.0)),
            "assets": rev_y * 1.4, "current_assets": rev_y * (0.62 - (0.05 if c in good else 0)),
            "current_liab": rev_y * 0.41, "equity": rev_y * 0.65,
            "capital_stock": rev_y * 0.12,
            "cfo": cum * (0.070 if c in good else 0.035)}

    def _fmt(x) -> str:
        return f"{x:,.0f}"

    for i, c in enumerate(codes):
        base_rev = float(rng.integers(20_000, 300_000)) * 1e6
        grow = 0.05 + (0.14 if c in good else 0.0) + rng.normal(0, 0.03)
        # ★ 5곳 중 1곳은 '연 1회만 공시'하는 기업으로 만든다. U-MICRO 에 흔한 형태이고,
        #   lag4 달력 게이트(shift(4)가 4년 전을 집는 사고)를 스모크가 실제로 밟게 하려면
        #   합성 데이터에도 반드시 존재해야 한다. 전 기업이 4분기를 다 내면 그 버그는
        #   합성에서 영원히 드러나지 않는다 — 실데이터에서만 조용히 터진다.
        annual_only = (i % 5 == 0)
        my_rcs = [_FY] if annual_only else rc_codes
        for y in range(y0, y1 + 1):
            for qi, rc in enumerate(rc_codes, start=1):
                if rc not in my_rcs:
                    continue
                _, cur = _vals_at(base_rev, grow, c, y, qi)
                _, cur_prev_q = _vals_at(base_rev, grow, c, y, qi - 1) if qi > 1 else (0, None)
                _, pv_same = _vals_at(base_rev, grow, c, y - 1, qi)
                _, pv_yend = _vals_at(base_rev, grow, c, y - 1, 4)
                mm, dd_ = REPRT_PERIOD_END[rc]
                rcpt = (pd.Timestamp(year=y, month=mm, day=dd_)
                        + pd.Timedelta(days=REPRT_DEADLINE_DAYS[rc])).strftime("%Y%m%d")
                for key, sj, aid, anm in accs:
                    flow = sj in _FLOW_SJ
                    if not flow:
                        # 재무상태표: 당기말 잔액 / 전기말 잔액 (★전년 동분기말이 아니다)
                        th, th_add = cur[key], ""
                        fr, fr_add = pv_yend[key], ""
                    elif rc == _FY:
                        # 사업보고서: 당기금액 = 연간. 누적 컬럼이 없다(실제 DART 와 동일).
                        th, th_add = cur[key], ""
                        fr, fr_add = pv_yend[key], ""
                    else:
                        # 분기·반기: 당기금액 = 3개월 단독, 당기누적금액 = YTD (실제 DART 와 동일)
                        th = cur[key] - (cur_prev_q[key] if cur_prev_q else 0.0)
                        th_add = cur[key]
                        fr = pv_same[key] - (_vals_at(base_rev, grow, c, y - 1, qi - 1)[1][key]
                                             if qi > 1 else 0.0)
                        fr_add = pv_same[key]
                    fs_rows.append({"corp_code": f"{i+1:08d}", "bsns_year": str(y),
                                    "reprt_code": rc, "rcept_no": rcpt + "000001",
                                    "fs_div": "CFS", "sj_div": sj, "account_id": aid,
                                    "account_nm": anm,
                                    "thstrm_amount": _fmt(th),
                                    "thstrm_add_amount": _fmt(th_add) if th_add != "" else "",
                                    "frmtrm_amount": _fmt(fr),
                                    "frmtrm_q_amount": "",
                                    "frmtrm_add_amount": _fmt(fr_add) if fr_add != "" else "",
                                    "bfefrmtrm_amount": ""})
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
            _br = ["미래에셋증권", "NH투자증권", "한국투자증권", "키움증권",
                   "합성증권"][int(rng.integers(0, 5))]
            rep_rows.append({
                "source": ["hankyung", "naver"][int(rng.integers(0, 2))],
                "src_report_id": f"S{i:05d}{int(rng.integers(0, 9999)):04d}",
                "pub_date": t, "category": "company",
                "title": f"합성{i+1:03d}({codes[i]}) 실적 리뷰",
                "stock_code": codes[i], "stock_name": f"합성{i+1:03d}",
                "broker_raw": _br, "analyst_raw": f"애널{int(rng.integers(1, 30)):02d}",
                "target_price": float(rng.integers(3000, 20000)), "opinion": "매수",
                "pdf_url": "", "detail_url": "", "views": 0,
                "event_date": t, "knowledge_date": t})
    # ★ 실데이터와 같은 정제·엔티티 경로를 통과시킨다. 그래야 '리포트↔애널리스트↔종목'
    #   원장 무결성 감사표가 스모크에서도 실제로 렌더링되어 형식을 확인할 수 있다.
    rep = pd.DataFrame(rep_rows)

    return {"sec": sec, "px": px, "snap": snap, "fs": fs, "actions": actions,
            "dis": dis, "rep": rep, "analysts": pd.DataFrame(), "links": pd.DataFrame(),
            "synthetic": True}
