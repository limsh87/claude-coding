

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-H  계약 자동검정 Q1~Q12 — 협상 불가 규칙을 코드가 스스로 증명한다                       ║
# ║                                                                                          ║
# ║  주석은 지켜지지 않아도 아무 일이 없지만, 여기의 검정은 실패하면 실행이 멈춘다.             ║
# ║  일부 계약은 '소스 검사'다 — 최적화 루틴이 없다는 것은 실행으로 증명할 수 없고              ║
# ║  코드에 그것이 존재하지 않음을 확인하는 방법밖에 없다.                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

import inspect as _inspect

CONTRACTS: List[dict] = []


def _contract(cid: str, name: str, critical: bool = True):
    def deco(fn):
        CONTRACTS.append({"id": cid, "name": name, "fn": fn, "critical": critical})
        return fn
    return deco


class ContractViolation(Exception):
    pass


@_contract("Q1", "PIT 게이트 — PIT 컬럼 없는 테이블은 등록 자체가 거부된다")
def _q1():
    st = PITStore()
    bad = pd.DataFrame({"code": ["000660"], "x": [1.0]})
    try:
        st.register("bad", bad)
    except KeyError:
        pass
    else:
        raise ContractViolation("PIT 컬럼이 없는 테이블이 등록되었습니다 — C1 게이트가 열려 있습니다.")
    ok = pit_frame(pd.DataFrame({"code": ["000660"], "x": [1.0]}),
                   "2020-01-01", "2020-02-15")
    st.register("ok", ok)
    got = st.get("ok", "2020-01-31")
    if len(got) != 0:
        raise ContractViolation("knowledge_date 이후 시점의 행이 조회되었습니다 — 미래누수입니다.")
    if len(st.get("ok", "2020-02-20")) != 1:
        raise ContractViolation("knowledge_date 이후에도 행이 보이지 않습니다.")
    return "PIT 등록 거부 + as_of 절단 정상"


@_contract("Q2", "시점 규약 — 신호일 < 체결일, 공시는 접수일+1거래일")
def _q2():
    days = pd.bdate_range("2020-01-01", "2020-06-30")
    px = pd.DataFrame({"code": "000660", "date": days, "open": 1.0, "high": 1.0,
                       "low": 1.0, "close": 1.0, "volume": 1.0, "amount": 1.0})
    set_trading_days(px)
    cal = qvf_rebal_calendar(px, "2020-01-01", "2020-06-30")
    if not (cal["signal_date"] < cal["exec_date"]).all():
        raise ContractViolation("signal_date >= exec_date 인 리밸런싱이 있습니다.")
    d0 = as_ts("2020-03-10")
    d1 = next_trading_day(d0)
    if not (d1 > d0):
        raise ContractViolation("next_trading_day 가 날짜를 미래로 밀지 않습니다 (§4 위반).")
    s = next_trading_day_series(pd.Series([d0, as_ts("2020-03-13")]))
    if not (as_ts_series(s) > pd.Series([d0, as_ts("2020-03-13")])).all():
        raise ContractViolation("next_trading_day_series 가 §4 규약을 만족하지 않습니다.")
    return f"리밸 {len(cal)}시점 · 접수일+1거래일 이동 확인"


@_contract("Q3", "생존자편향 — 폐지 종목이 유니버스에 있고 −100% 가 적용된다")
def _q3():
    days = pd.bdate_range("2020-01-01", "2021-06-30")
    rows = []
    for c, stop in (("000001", None), ("000002", as_ts("2020-08-15"))):
        dd = days if stop is None else days[days <= stop]
        rows.append(pd.DataFrame({"code": c, "date": dd, "open": 100.0, "high": 101.0,
                                  "low": 99.0, "close": 100.0, "volume": 1e5, "amount": 1e7}))
    px = pd.concat(rows, ignore_index=True)
    set_trading_days(px)
    cal = qvf_rebal_calendar(px, "2020-01-01", "2021-06-30")
    sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["A", "B"],
                        "market": ["KOSPI", "KOSDAQ"],
                        "listing_date": [as_ts("2010-01-01")] * 2,
                        "delisting_date": [pd.NaT, as_ts("2020-08-20")],
                        "industry": ["기계", "기계"], "corp_code": ["C1", "C2"], "src": "t"})
    uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    at = uni.at(as_ts("2020-06-01"))
    if "000002" not in at:
        raise ContractViolation("폐지 예정 종목이 폐지 전 시점의 유니버스에서 빠졌습니다 — 생존자편향.")
    if "000002" in uni.at(as_ts("2020-12-01")):
        raise ContractViolation("폐지 이후 시점에 폐지 종목이 유니버스에 남아 있습니다.")
    ep = build_exec_prices(cal, px)
    fwd = build_forward_returns(ep, cal, {"000002": as_ts("2020-08-20")}, px)
    row = fwd[(fwd["code"] == "000002") & (fwd["rebal"] == as_ts("2020-06-01"))]
    if row.empty or not np.isclose(float(row["fwd_ret"].iloc[0]), -1.0, atol=1e-9):
        raise ContractViolation(
            "보유 중 상장폐지에 −100% 가 적용되지 않았습니다 (§3.4 위반). "
            "가격 시계열이 폐지 직전에 끊겼을 때 마지막 정상가를 청산가로 쓰면 "
            "'상장폐지 = 무손실'이 되어 생존자편향이 그대로 재유입됩니다.")
    # 정리매매가 실제로 관측된 경우에는 그 가격을 써야 한다(무조건 −100% 도 틀렸다).
    px2 = px.copy()
    tail = px2["code"] == "000002"
    px2.loc[tail & (px2["date"] >= as_ts("2020-08-10")), ["close", "open"]] = 12.0
    extra = pd.DataFrame({"code": "000002",
                          "date": pd.bdate_range("2020-08-17", "2020-08-19"),
                          "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
                          "volume": 1e4, "amount": 1e5})
    px2 = pd.concat([px2, extra], ignore_index=True)
    fwd2 = build_forward_returns(build_exec_prices(cal, px2), cal,
                                 {"000002": as_ts("2020-08-20")}, px2)
    r2 = fwd2[(fwd2["code"] == "000002") & (fwd2["rebal"] == as_ts("2020-06-01"))]
    if r2.empty or float(r2["fwd_ret"].iloc[0]) <= -0.999:
        raise ContractViolation("정리매매 체결가가 관측되었는데도 −100% 로 처리했습니다 "
                                "(§3.4 는 '실제 체결가 반영'을 먼저 요구합니다).")
    return (f"폐지 전 포함 · 폐지 후 제외 · 데이터 끊김 → −100% · "
            f"정리매매 관측 → 실가 반영({float(r2['fwd_ret'].iloc[0]):+.1%})")


@_contract("Q4", "부호 처리 — 음수 분모가 최우량이 아니라 최하위로 배정된다")
def _q4():
    n = 40
    P = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
    })
    P["cell"] = "202003|기계"
    P["cell_l2"] = P["cell"]
    P["cell_l3"] = "202003|ALL"
    # 앞 5개는 EBIT 음수(= 분모 부적격), 나머지는 양수이며 비율이 클수록(=비쌀수록) 나쁨
    ebit = pd.Series([-1.0] * 5 + list(np.linspace(1.0, 5.0, n - 5)))
    cap = pd.Series([100.0] * n)
    raw = safe_div(cap, ebit)
    valid = ebit > 0
    z = z_lower_is_better(P, raw, valid, "테스트")
    bad_z = float(z.iloc[:5].mean())
    good_z = float(z.iloc[5:].max())
    if not (bad_z <= z.iloc[5:].min() + 1e-6):
        raise ContractViolation(
            f"음수 EBIT 종목의 z({bad_z:.3f})가 최하위가 아닙니다 — 적자기업이 최우량으로 "
            f"오분류되는 §5.2 위반입니다.")
    if not np.isfinite(good_z):
        raise ContractViolation("정상 관측의 z 가 산출되지 않았습니다.")
    return f"음수분모 z={bad_z:+.2f} ≤ 정상 최소 z={float(z.iloc[5:].min()):+.2f}"


@_contract("Q5", "결측 허용 — 리포트 없는 종목의 z 는 0(중립)이며 관측치 z 를 오염시키지 않는다")
def _q5():
    n = 60
    P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                      "rebal": [as_ts("2020-03-01")] * n,
                      "sector": ["기계"] * n})
    P["cell"] = "202003|기계"
    P["cell_l2"] = P["cell"]
    P["cell_l3"] = "202003|ALL"
    v = np.full(n, np.nan)
    v[:20] = np.linspace(-1.0, 1.0, 20)          # 20개만 관측, 40개는 리포트 없음
    P["dTONE_resid"] = v
    mask = P["dTONE_resid"].notna()
    z = zscore_observed_then_neutral(P, "dTONE_resid", mask)
    if not np.isclose(float(z[~mask].abs().max()), 0.0):
        raise ContractViolation("리포트 없는 종목의 z 가 0(중립)이 아닙니다 (§6.2 위반).")
    obs = z[mask]
    if abs(float(obs.mean())) > 0.15 or abs(float(obs.std(ddof=0)) - 1.0) > 0.25:
        raise ContractViolation(
            f"관측치 z 의 평균 {float(obs.mean()):.3f} / 표준편차 {float(obs.std(ddof=0)):.3f} — "
            f"결측 0 을 z-score '이전'에 주입해 분포가 오염되었습니다 (§6.2 핵심 위반).")
    return f"관측 z 평균 {float(obs.mean()):+.3f} · 표준편차 {float(obs.std(ddof=0)):.3f} · 결측 z=0"


@_contract("Q6", "사전등록 가중치 — 코드 어디에도 가중치 최적화 루틴이 없다")
def _q6():
    if abs(sum(VARIANT_W["VQF"]) - 1.0) > 1e-9 or VARIANT_W["V"] != (1.0, 0.0, 0.0):
        raise ContractViolation("VARIANT_W 가 §5.5 사전등록 값과 다릅니다.")
    if (SCORE2_W_NONFIN, SCORE2_W_TONE) != (2.0, 1.0):
        raise ContractViolation("Score2 가중치가 §6.3 사전등록 값(2:1)과 다릅니다.")
    src = ""
    for fn in (score1, build_u200, apply_filter2, build_final_selection, run_experiment):
        try:
            src += _inspect.getsource(fn)
        except Exception:
            pass
    bad = re.findall(r"\b(minimize|curve_fit|GridSearch|RandomizedSearch|optimize|"
                     r"differential_evolution|fmin|argmax\s*\(\s*sharpe|best_weight)\b", src)
    if bad:
        raise ContractViolation(f"선정 경로에서 최적화 흔적이 발견되었습니다: {sorted(set(bad))}")
    return "가중치 고정 확인 · 선정 경로에 최적화 루틴 없음"


@_contract("Q7", "캐시 무결성 — 삭제 API 부재 · 로컬 미러는 쓰기 경로에 등장하지 않는다")
def _q7():
    for nm in ("delete", "remove", "drop_table", "purge", "rmtree"):
        if hasattr(Vault, nm) or hasattr(QVFVault, nm):
            raise ContractViolation(f"Vault 에 삭제 API '{nm}' 가 존재합니다 — 절대 1원칙 위반.")
    for fn in (Vault.put_table, Vault.put_blob, Vault.flush, Vault.compact):
        s = _inspect.getsource(fn)
        if "mirror" in s.lower():
            raise ContractViolation(f"쓰기 함수 {fn.__name__} 가 미러 경로를 참조합니다 — "
                                    f"로컬 미러는 구조적으로 읽기 전용이어야 합니다.")
    s = _inspect.getsource(QVFVault)
    if re.search(r"os\.(remove|unlink|rmdir)|shutil\.rmtree", s):
        raise ContractViolation("QVFVault 에 파일 삭제 호출이 있습니다 — 절대 1원칙 위반.")

    # ★ 소스 grep 만으로는 '상속받은 쓰기 코드가 미러 경로를 만들 수 있는가'를 못 본다.
    #   실제로 미러에 쓰려고 시도시켜 보고, 막히는지 확인한다.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        wroot, mroot = os.path.join(td, "w"), os.path.join(td, "m")
        os.makedirs(os.path.join(mroot, GDRIVE_SHARED_NS, "table"), exist_ok=True)
        v = QVFVault(wroot, "TEST", [mroot])
        blocked = False
        try:
            v._wpath(os.path.join(mroot, GDRIVE_SHARED_NS, "table", "x.parquet"))
        except PermissionError:
            blocked = True
        if not blocked:
            raise ContractViolation("미러 경로가 쓰기 경로 검증을 통과했습니다 — "
                                    "로컬 미러가 읽기 전용이라는 보장이 구조적이지 않습니다.")
        # 미러의 손상 파일을 읽어도 원본을 개명하지 않아야 한다.
        bad = os.path.join(mroot, GDRIVE_SHARED_NS, "table", "broken.parquet")
        open(bad, "wb").write(b"")                       # 0바이트 = 드라이브 동기화 미완 상황
        v.get_table("broken", scope="shared")
        if not os.path.exists(bad):
            raise ContractViolation("미러의 파일이 사라졌습니다 — 읽기가 파일을 파괴했습니다.")
        if [f for f in os.listdir(os.path.dirname(bad)) if ".corrupt" in f]:
            raise ContractViolation("미러 파일이 .corrupt 로 개명되었습니다 — "
                                    "read_parquet_safe 가 미러에 도달했습니다(절대 1원칙 위반).")
    return "삭제 API 없음 · 미러 쓰기 차단 확인 · 미러 손상파일 읽어도 원본 보존"


@_contract("Q8", "결정성 — 같은 입력에 같은 선정 (동점 처리가 행 순서에 의존하지 않는다)")
def _q8():
    n = 50
    rng = np.random.default_rng(SEED)
    base = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
        "Z_V": np.round(rng.normal(size=n), 2),      # 반올림으로 동점을 일부러 만든다
        "Z_Q": np.round(rng.normal(size=n), 2),
        "Z_F": np.nan, "mktcap": rng.lognormal(23, 1, n),
    })
    a = build_u200(base, variants=("VQ",), n=20)
    b = build_u200(base.sample(frac=1.0, random_state=7).reset_index(drop=True),
                   variants=("VQ",), n=20)
    sa = set(a.loc[a["u200_VQ"], "code"])
    sb = set(b.loc[b["u200_VQ"], "code"])
    if sa != sb:
        raise ContractViolation(
            f"행 순서를 섞었더니 선정이 달라졌습니다({len(sa ^ sb)}종목 차이) — "
            f"포트폴리오가 데이터가 아니라 정렬의 함수입니다.")
    return f"행 순서 무관 · 선정 {len(sa)}종목 동일"


@_contract("Q9", "분기 연율화 — √4 를 쓴다 (√12 를 쓰면 변동성이 1.7배 과대계상된다)")
def _q9():
    if abs(Q_PER_YEAR - 4.0) > 1e-9:
        raise ContractViolation("Q_PER_YEAR 가 4 가 아닙니다.")
    r = np.array([0.05, -0.03, 0.04, 0.01] * 10)
    R = pd.DataFrame({"rebal": pd.date_range("2016-03-01", periods=len(r), freq="QS"),
                      "ret": r, "n": 30, "turnover": 0.5, "cost": 0.0})
    s = qperf_stats(R)
    exp_vol = float(np.std(r, ddof=1) * math.sqrt(4))
    if abs(s["연변동성"] - exp_vol) > 1e-9:
        raise ContractViolation(f"연변동성 {s['연변동성']:.4f} != √4 기준 {exp_vol:.4f}")
    exp_cagr = float(np.prod(1 + r) ** (1 / (len(r) / 4.0)) - 1)
    if abs(s["CAGR"] - exp_cagr) > 1e-9:
        raise ContractViolation("CAGR 의 연수 환산이 분기 기준이 아닙니다.")
    return f"연변동성 √4 · CAGR 연수 = 분기수/4 확인"


@_contract("Q10", "비용 — 비용 차감 후 수익은 항상 차감 전 이하다")
def _q10():
    src = _inspect.getsource(run_qbacktest) + _inspect.getsource(qvf_sell_tax)
    if "ret_gross" not in src or "gross - cost" not in src:
        raise ContractViolation("백테스트가 비용 전/후를 분리해 산출하지 않습니다 (§8.1 위반).")
    for pat, nm in ((r"QVF_TAX_SCHEDULE", "거래세 이력"),
                    (r"cs_spread|SLIPPAGE_FLOOR_BPS", "실측 스프레드"),
                    (r"IMPACT_K", "시장충격")):
        if not re.search(pat, src):
            raise ContractViolation(f"비용 모델에 {nm} 이 반영되지 않았습니다.")
    if len(QVF_TAX_SCHEDULE) < 5:
        raise ContractViolation("증권거래세를 단일 세율로 처리하고 있습니다 — 10년간 여섯 번 바뀌었습니다.")
    return f"비용 전/후 분리 · 거래세 {len(QVF_TAX_SCHEDULE)}단계 · 스프레드+충격 반영"


@_contract("Q11", "결측을 0 으로 채우지 않는다 — z-score 는 표본 부족 시 NaN 을 유지한다")
def _q11():
    v = pd.Series([1.0, 2.0, np.nan, 4.0, np.inf, -np.inf])
    cells = pd.Series(["A"] * 6)
    z = xsec_z_pct(v, cells, min_n=3)
    if z.isna().sum() < 3:
        raise ContractViolation("±inf 와 NaN 이 결측으로 유지되지 않았습니다.")
    z2 = xsec_z_pct(pd.Series([1.0, 2.0]), pd.Series(["A", "A"]), min_n=8)
    if not z2.isna().all():
        raise ContractViolation("표본 부족 셀의 z 가 NaN 이 아닙니다 — 0 으로 채우면 그 종목이 "
                                "'평균적인 종목'으로 둔갑합니다.")
    return "±inf → NaN · 표본부족 셀 → NaN 유지"


@_contract("Q12", "DART 호출 한도 — 고정 상수가 아니라 실측으로 확정된다")
def _q12():
    s = _inspect.getsource(DartQuota)
    if "limit_observed" not in s:
        raise ContractViolation("DartQuota 가 실측 한도를 기록하지 않습니다.")
    if not re.search(r"def\s+take", s) or re.search(r"self\.n\s*\+\s*k\s*>\s*DART_DAILY_LIMIT", s):
        raise ContractViolation("take() 가 하드코딩된 DART_DAILY_LIMIT 로 소비를 막고 있습니다 — "
                                "남은 호출량을 실시간으로 쓰라는 요구사항 위반입니다.")
    if 'ns["shared"]' not in s:
        raise ContractViolation("DartQuota 저널이 공용 스코프가 아닙니다 — 전략 간 사용량이 "
                                "합산되지 않아 한도를 넘깁니다.")
    if "_confirm_exhaustion" not in s:
        raise ContractViolation("020(일일한도)과 021(요청오류)을 구분하지 않습니다 — "
                                "021 을 한도로 기록하면 거짓 상한이 공용 저널을 오염시킵니다.")
    # ★ 조립본에서 '실효' 상수를 확인한다. 공용 코어(12_ingest_dart_fin)가 헤더보다 뒤에서
    #   DART_DAILY_LIMIT = 19_000 으로 되돌려 놓기 때문에, 선언만 보면 통과하고 실제로는
    #   사용자가 거부한 값이 살아 있다. 계약은 선언이 아니라 실효값을 봐야 한다.
    if int(DART_DAILY_LIMIT) != int(DART_DAILY_LIMIT_HINT):
        raise ContractViolation(
            f"실효 DART_DAILY_LIMIT 이 {DART_DAILY_LIMIT:,} 로 헤더 값 "
            f"{DART_DAILY_LIMIT_HINT:,} 과 다릅니다 — 조립 순서상 뒤에 오는 하드코딩이 "
            f"헤더를 이기고 있습니다. DartQuota 생성 시 되찾아오는지 확인하세요.")
    return f"실측 기반 · 공용 저널 합산 · 020/021 구분 · 실효 한도 {DART_DAILY_LIMIT:,}"


@_contract("Q13", "§10.4 폐기조건 — 충족 시 실제로 멈춘다(보고만 하고 지나가지 않는다)")
def _q13():
    """'미달 시 행동'을 표에 적어 놓고 아무것도 하지 않으면 그 표는 거짓말이 된다.

    예전에는 폐기 판정을 낸 직후 그 폐기된 전략의 실전 편입 종목표를 그대로 출력했다.
    여기서는 폐기가 확실히 성립하는 가짜 EXPERIMENTS 를 심고 KillCriteria 가 실제로
    올라오는지, 그리고 STOP_ON_KILL_CRITERIA=False 면 올라오지 않는지 둘 다 본다.
    """
    keep_exp = dict(EXPERIMENTS)
    keep_stop = STOP_ON_KILL_CRITERIA
    try:
        EXPERIMENTS.clear()
        # 세 변형 전부 비용 차감 후 CAGR < 0 → 조건 ① 확실히 충족
        for nm in ("V-full", "VQ-full", "VQF-full", "X1"):
            EXPERIMENTS[nm] = {"name": nm, "desc": "", "R": None, "t": 0.0, "p": 0.9, "n": 8,
                               "net": {"CAGR": -0.05, "Sharpe": 0.10, "MDD": -0.30},
                               "gross": {}}
        keep_level = LOG.min
        LOG.min = 99                                   # 계약 표에 잡음을 남기지 않는다
        try:
            globals()["STOP_ON_KILL_CRITERIA"] = True
            raised = False
            try:
                report_preregistration_kill(["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
            except KillCriteria:
                raised = True
            if not raised:
                raise ContractViolation(
                    "§10.4 폐기 조건이 충족됐는데 KillCriteria 가 올라오지 않았습니다 — "
                    "폐기 판정 후에도 최종 편입 종목표가 출력됩니다.")
            globals()["STOP_ON_KILL_CRITERIA"] = False
            out = report_preregistration_kill(["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
            if not out.get("all_alpha_dead"):
                raise ContractViolation("폐기 조건 ①(전 변형 알파 소멸)이 감지되지 않았습니다.")
        finally:
            LOG.min = keep_level
    finally:
        globals()["STOP_ON_KILL_CRITERIA"] = keep_stop
        EXPERIMENTS.clear()
        EXPERIMENTS.update(keep_exp)
    return "충족 시 중단 · STOP 끄면 보고만"


@_contract("Q14", "adopt(size=) 가 코어 경로와 같은 uid 를 만든다 — 캐시 중복등록 방지")
def _q14():
    """scandir 이 이미 알고 있는 크기를 넘겨 FUSE 왕복을 아끼되, uid 는 반드시 동일해야 한다.

    uid 가 달라지면 같은 파일이 인덱스에 두 번 들어가고, 재실행마다 계속 늘어난다.
    """
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        fp = os.path.join(td, "sample_report_2020-01-02.pdf")
        with open(fp, "wb") as f:
            f.write(b"x" * 1234)
        sz = os.path.getsize(fp)
        u_core = sha1_str("adopt", "research", "report_pdf", os.path.abspath(fp), sz)
        v = QVFVault(os.path.join(td, "cache"), mode="local", mirrors=[])
        u_fast = v.adopt(fp, domain="research", subtype="report_pdf", key="sample",
                         scope="shared", size=sz)
        if u_fast != u_core:
            raise ContractViolation(
                f"size 지정 경로의 uid 가 코어와 다릅니다: {u_fast} vs {u_core} — "
                f"같은 파일이 인덱스에 중복 등록됩니다.")
        if not v.has("shared", u_core):
            raise ContractViolation("adopt 직후 has() 가 False 입니다 — 중복 수집이 발생합니다.")
        # ★★ 같은 실행에서 저장한 것을 같은 실행에서 되찾을 수 있어야 한다(절대 1원칙) ★★
        #   put_blob 은 uid 가 아니라 '파일 경로'를 돌려주므로 인덱스에서 uid 를 찾는다.
        #   저널 flush 이전(=등록만 된 상태)과 이후 둘 다 성립해야 한다. 예전에는 코어가
        #   self._idx 캐시를 갱신하지 않아 둘 다 None 이었고, 콜드런 1회차에 방금 받은
        #   PDF 가 TONE 입력에서 통째로 빠졌다 — '본문이 짧아 제외'와 구분되지 않는 형태로.
        for k, payload, flush_first in (("k_preflush", b"before-flush", False),
                                        ("k_postflush", b"after-flush", True)):
            v.put_blob("test", "unit", k, payload, "bin", scope="shared", source="contract")
            if flush_first:
                v.flush("shared")
            idx = v.load_index("shared")
            hit = idx[idx["key"].astype(str) == k]
            if hit.empty:
                raise ContractViolation(
                    f"put_blob 직후 인덱스에서 '{k}' 를 찾을 수 없습니다 — 인덱스 캐시가 "
                    f"등록분을 반영하지 않고 있습니다(절대 1원칙 위반).")
            got = v.get_blob(str(hit["uid"].iloc[0]), "shared")
            if got != payload:
                raise ContractViolation(
                    f"같은 실행에서 저장한 blob('{k}')을 get_blob 이 되찾지 못했습니다 "
                    f"(flush {'후' if flush_first else '전'}). 콜드런 1회차에 방금 받은 "
                    f"자료가 통째로 빠지는 경로입니다.")
        # force=True 가 오히려 파생 캐시를 굳혀 복구를 막던 경로도 함께 고정한다.
        idx = v.load_index("shared", force=True)
        hit = idx[idx["key"].astype(str) == "k_postflush"]
        if hit.empty or v.get_blob(str(hit["uid"].iloc[0]), "shared") != b"after-flush":
            raise ContractViolation(
                "load_index(force=True) 이후 get_blob 이 실패합니다 — force 가 _uidpath 를 "
                "무효화하지 않아 스테일 사전이 영구히 남는 경로입니다.")
    return "uid 동일 · 저장↔재호출 (flush 전/후/force) 전부 성립"


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정 Q1~Q14", "협상 불가 규칙 — 실패하면 실데이터 수집을 시작하지 않습니다")
    rows, ok_all = [], True
    for c in CONTRACTS:
        t0 = time.time()
        try:
            msg = c["fn"]()
            rows.append([c["id"], _trunc(c["name"], 46), "✔ 통과", f"{time.time()-t0:.2f}s",
                         _trunc(str(msg or ""), 40)])
        except Exception as e:                                # noqa
            ok_all = ok_all and not c["critical"]
            rows.append([c["id"], _trunc(c["name"], 46), "✘ 실패", f"{time.time()-t0:.2f}s",
                         _trunc(f"{type(e).__name__}: {e}", 40)])
            LOG.error(f"[{c['id']}] {c['name']} — {type(e).__name__}: {e}")
    LOG.table(rows, ["ID", "계약", "판정", "소요", "비고"], ["c", "l", "c", "r", "l"], maxw=48)
    if not ok_all:
        msg = ("계약 검정에 실패했습니다. 이 규칙들은 결과의 유효성을 결정하므로 "
               "우회하지 말고 원인을 고치십시오.")
        if strict:
            raise ContractViolation(msg)
        LOG.error(msg)
    else:
        LOG.ok("계약 Q1~Q14 전부 통과 — PIT·생존자편향·부호처리·결측허용·비용·폐기조건·캐시 무결성 확인")
    return ok_all
