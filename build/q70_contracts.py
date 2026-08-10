

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-H  계약 자동검정 Q1~Q14 — 협상 불가 규칙을 코드가 스스로 증명한다                       ║
# ║                                                                                          ║
# ║  주석은 지켜지지 않아도 아무 일이 없지만, 여기의 검정은 실패하면 실행이 멈춘다.             ║
# ║  일부 계약은 '소스 검사'다 — 최적화 루틴이 없다는 것은 실행으로 증명할 수 없고              ║
# ║  코드에 그것이 존재하지 않음을 확인하는 방법밖에 없다.                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

import inspect as _inspect

CONTRACTS: List[dict] = []

# 빌더가 심어 둔 소스 조각. 파일이 아니라 셀에서 실행될 때 inspect 대신 이걸 쓴다.
QVF_PINNED_SRC: Dict[str, str] = globals().get("QVF_PINNED_SRC", {})


def pinned_src(name: str, obj=None) -> str:
    """이름으로 소스를 가져온다. 빌드 시점 고정본 우선, 없으면 inspect 폴백.

    ★ 둘 다 실패하면 '' 를 돌려주지 않고 예외를 낸다. 소스를 못 읽었는데 조용히 통과시키면
      '부재 증명' 계약이 아무것도 증명하지 않는 채로 ✔ 를 찍게 된다 — Colab 에서 정확히
      그 상태가 될 뻔했다(거기서는 아예 OSError 로 죽어서 드러났지만).
    """
    s = QVF_PINNED_SRC.get(name)
    live = None
    if obj is not None:
        try:
            live = _inspect.getsource(obj)
        except Exception:
            live = None
    # ★★ 고정본을 무조건 믿으면 안 된다 ★★
    #   QVF_PINNED_SRC 는 '빌드 시점'의 글자다. 사용자가 셀에 붙여넣은 뒤 함수를 고치면
    #   실제로 도는 코드는 바뀌었는데 고정본은 옛 글자를 그대로 들고 있다. 그러면 Q6/Q7/Q12
    #   같은 '부재 증명' 계약이 돌지도 않는 코드를 검정하고 ✔ 를 찍는다 — 계약층 전체가
    #   조용히 무력화되는 경로다. 살아 있는 소스를 읽을 수 있으면 그쪽이 진실이다.
    if s and live is not None:
        if re.sub(r"\s+", " ", s).strip() != re.sub(r"\s+", " ", live).strip():
            raise ContractViolation(
                f"'{name}' 의 실제 소스가 빌드 시점 고정본과 다릅니다 — 파일/셀에서 이 함수를 "
                f"수정하셨습니다. 고정본으로 검정하면 '돌지 않는 코드'를 검정하게 되므로 "
                f"통과시키지 않습니다. tools/build_qvf.py 로 다시 빌드하거나 수정을 되돌리세요.")
        return live
    if s:
        return s
    if live is not None:
        return live
    raise ContractViolation(
        f"소스 조각 '{name}' 을 찾을 수 없습니다. 빌드 시점 고정본(QVF_PINNED_SRC)이 "
        f"비어 있고 inspect 도 실패했습니다 — 파일을 직접 편집했거나 빌더의 SRC_PIN 목록과 "
        f"이름이 어긋났을 수 있습니다. 소스 기반 계약을 검정할 수 없으므로 통과시키지 않습니다.")


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
    # ★ 게이트를 실제로 우회하는 경로는 '빈 프레임'이다. PITStore.register 는 len(df)==0 이면
    #   PIT 컬럼 검사 없이 그냥 등록해 버린다 — 수집기가 빈손으로 돌아오면 PIT 없는 테이블이
    #   '있음'으로 잡힌다. 1행짜리만 시험하던 옛 검정은 이 경로를 한 번도 안 밟았다.
    try:
        st.register("empty", pd.DataFrame(columns=["code", "x"]))
    except KeyError:
        pass
    else:
        if st.has("empty"):
            raise ContractViolation(
                "빈 프레임이 PIT 컬럼 검사 없이 등록되어 'has()=True' 로 보고됩니다 — "
                "수집 실패가 '데이터 있음'으로 둔갑하는 경로입니다.")
    return "PIT 등록 거부 + as_of 절단 + 빈 프레임 우회 차단 확인"


@_contract("Q2", "시점 규약 — 신호일 < 체결일, 공시는 접수일+1거래일")
def _q2():
    # ★ set_trading_days 는 전역 QVF_TRADING_DAYS 를 덮어쓴다(q21:48). 계약이 끝나도 합성
    #   2020년 영업일 격자가 남으므로, 뒤에 오는 스테이지가 그 격자로 next_trading_day 를
    #   계산하면 2020-01-01 이전 날짜가 전부 2020-01-01 로 접힌다 — DART knowledge_date 가
    #   통째로 조작되는 셈이다. 지금은 L1.CAL 이 나중에 덮어써서 우연히 무해할 뿐이다.
    #   계약은 자기가 만진 전역을 반드시 원복해야 한다.
    _SAVED_TD = globals().get("QVF_TRADING_DAYS")
    try:
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
    finally:
        globals()["QVF_TRADING_DAYS"] = _SAVED_TD


@_contract("Q3", "생존자편향 — 폐지 종목이 유니버스에 있고 −100% 가 적용된다")
def _q3():
    # ★ set_trading_days 는 전역 QVF_TRADING_DAYS 를 덮어쓴다(q21:48). 계약이 끝나도 합성
    #   2020년 영업일 격자가 남으므로, 뒤에 오는 스테이지가 그 격자로 next_trading_day 를
    #   계산하면 2020-01-01 이전 날짜가 전부 2020-01-01 로 접힌다 — DART knowledge_date 가
    #   통째로 조작되는 셈이다. 지금은 L1.CAL 이 나중에 덮어써서 우연히 무해할 뿐이다.
    #   계약은 자기가 만진 전역을 반드시 원복해야 한다.
    _SAVED_TD = globals().get("QVF_TRADING_DAYS")
    try:
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
    finally:
        globals()["QVF_TRADING_DAYS"] = _SAVED_TD


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
    # ★ 예전엔 VQF 의 '합이 1'과 V 만 봤다. VQ 는 아예 검사하지 않았고, VQF 도 (0.1,0.1,0.8)
    #   처럼 완전히 다른 값이 합만 맞으면 통과했다 — 계약 이름이 '사전등록 가중치'인데
    #   정작 사전등록 값을 검정하지 않았다. 세 변형 전부를 리터럴로 못박는다.
    _PRE = {"V": (1.0, 0.0, 0.0), "VQ": (0.5, 0.5, 0.0), "VQF": (0.4, 0.4, 0.2)}
    for _k, _w in _PRE.items():
        _got = tuple(float(x) for x in VARIANT_W.get(_k, ()))
        if len(_got) != 3 or max(abs(a - b) for a, b in zip(_got, _w)) > 1e-9:
            raise ContractViolation(
                f"VARIANT_W['{_k}'] 이 §5.5 사전등록 값과 다릅니다: {_got} ≠ {_w}")
    if (SCORE2_W_NONFIN, SCORE2_W_TONE) != (2.0, 1.0):
        raise ContractViolation("Score2 가중치가 §6.3 사전등록 값(2:1)과 다릅니다.")
    src = ""
    for nm, fn in (("score1", score1), ("build_u200", build_u200),
                   ("apply_filter2", apply_filter2),
                   ("build_final_selection", build_final_selection),
                   ("run_experiment", run_experiment)):
        src += pinned_src(nm, fn) + "\n"
    bad = re.findall(r"\b(minimize|curve_fit|GridSearch|RandomizedSearch|optimize|"
                     r"differential_evolution|fmin|argmax\s*\(\s*sharpe|best_weight)\b", src)
    if bad:
        raise ContractViolation(f"선정 경로에서 최적화 흔적이 발견되었습니다: {sorted(set(bad))}")
    return "가중치 고정 확인 · 선정 경로에 최적화 루틴 없음"


@_contract("Q7", "캐시 무결성 — 삭제 API 부재 · 로컬 미러는 쓰기 경로에 등장하지 않는다")
def _q7():
    # ★ 예전엔 이름 5개짜리 블랙리스트였다 — evict/prune/expire/trim/clear/unlink 로 이름만
    #   바꾸면 그대로 통과한다. 상속 계층(MRO) 전체를 훑어 '지우는 뜻'의 공개 메서드를 금지한다.
    _DEL = re.compile(r"(^|_)(del|delete|remov|purge|drop|rm|evict|prune|expire|trim|clear|unlink|wipe)")
    for _cls in (Vault, QVFVault):
        for _k in dir(_cls):
            if _k.startswith("__") or not callable(getattr(_cls, _k, None)):
                continue
            if _DEL.search(_k.lower()):
                raise ContractViolation(
                    f"{_cls.__name__} 에 삭제 성격의 API '{_k}' 가 있습니다 — 절대 1원칙 위반. "
                    f"(이름만 바꾼 삭제도 삭제입니다)")
    for nm, fn in (("Vault.put_table", Vault.put_table), ("Vault.put_blob", Vault.put_blob),
                   ("Vault.flush", Vault.flush), ("Vault.compact", Vault.compact)):
        s = pinned_src(nm, fn)
        if "mirror" in s.lower():
            raise ContractViolation(f"쓰기 함수 {nm} 가 미러 경로를 참조합니다 — "
                                    f"로컬 미러는 구조적으로 읽기 전용이어야 합니다.")
    s = pinned_src("QVFVault", QVFVault)
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
    # ★★ 예전에는 정규난수를 소수 2자리로 반올림해 '동점이 생기기를 기대'했다. SEED
    #   20260810 에서 실측하면 동점 6쌍이 생기긴 하지만 20위(0.295)와 21위(0.255) 사이를
    #   가로지르는 동점이 없어, 선정 집합이 점수만으로 유일하게 결정된다 — 즉 tie-break 를
    #   통째로 없애도 이 계약은 통과했다. 검정력이 0이었고, 그 사실이 무관한 상수(SEED)에
    #   달려 있었다. 커트라인 위에 동점을 '설계해서' 만든다.
    n = 50
    rng = np.random.default_rng(SEED)
    zv = np.round(rng.normal(size=n), 2)
    # 19~23위가 될 5종목의 점수를 완전히 같게 만들어 커트라인(20위)을 동점이 가로지르게 한다.
    order = np.argsort(-zv)
    tie_at = order[18:23]
    zv[tie_at] = float(zv[order[19]])
    base = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
        "Z_V": zv,
        "Z_Q": zv,                                   # VQ = 0.5·V + 0.5·Q → 동점이 그대로 유지
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
    # ★ 검정이 실제로 '동점 구간'을 통과했는지 확인한다. 동점이 커트라인을 가로지르지 않으면
    #   위 비교는 tie-break 가 없어도 성립하므로 계약이 아무것도 보장하지 못한다.
    _sel = set(base.loc[base.index[tie_at], "code"]) & sa
    if not (0 < len(_sel) < len(tie_at)):
        raise ContractViolation(
            f"동점 {len(tie_at)}종목이 커트라인을 가로지르지 않아 이 검정에 검정력이 없습니다 "
            f"(선정된 동점 {len(_sel)}종목). 테스트 픽스처를 고치세요.")
    return f"행 순서 무관 · 선정 {len(sa)}종목 동일 · 커트라인 동점 {len(tie_at)}종목 통과"


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
    # ★★ 예전 Q10 은 제목이 "비용 차감 후 수익은 항상 차감 전 이하다"인데 정작 백테스트를
    #   돌리지도, 두 값을 비교하지도 않았다. 소스에 "ret_gross"/"gross - cost" 라는 글자가
    #   있는지만 봤다 — 주석 안에 있어도 통과하고, 변수명을 g/c 로 줄이면 멀쩡한 코드가
    #   실패한다. 게다가 IMPACT_K 검사는 기본 설정(QVF_COST_MODEL="spec", §8.1 문언)에서
    #   '있으면 안 되는' 확장 비용을 강제하고 있었다. 실제로 돌려서 부등식을 확인한다.
    _n = 12
    _cal = pd.DataFrame({"rebal": pd.date_range("2020-03-01", periods=4, freq="QS")})
    _cal["signal_date"] = _cal["rebal"] - pd.Timedelta(days=1)
    _cal["exec_date"] = _cal["rebal"] + pd.Timedelta(days=1)
    _rng = np.random.default_rng(SEED)
    _rows = []
    for t in _cal["rebal"]:
        for i in range(_n):
            _rows.append({"code": f"{i:06d}", "rebal": t, "sel": True,
                          "mktcap": 3e10, "adtv": 5e8, "cs_spread": 0.004})
    _P = pd.DataFrame(_rows)
    _fwd = _P[["code", "rebal"]].copy()
    _fwd["fwd_ret"] = _rng.normal(0.01, 0.05, len(_fwd))
    _fwd["exit_kind"] = "normal"
    _kw = dict(P=_P, cal=_cal, sel_col="sel", fwd=_fwd, label="Q10", delist={})
    _R = run_qbacktest(apply_costs=True, **_kw)["returns"]
    _R0 = run_qbacktest(apply_costs=False, **_kw)["returns"]
    for _c in ("ret", "ret_gross", "cost"):
        if _c not in _R.columns:
            raise ContractViolation(f"백테스트 결과에 '{_c}' 이 없습니다 — 비용 전/후를 "
                                    f"분리해 산출하지 않습니다 (§8.1 위반).")
    if bool((_R["ret"] > _R["ret_gross"] + 1e-12).any()):
        raise ContractViolation(
            f"비용 차감 후 수익이 차감 전보다 큰 분기가 "
            f"{int((_R['ret'] > _R['ret_gross'] + 1e-12).sum())}개 있습니다 — "
            f"비용이 음수이거나 부호가 뒤집혔습니다 (§8.1 위반).")
    if bool((_R["cost"] < -1e-12).any()):
        raise ContractViolation("음수 비용이 산출되었습니다 — 거래가 수익을 만들고 있습니다.")
    if float(_R["cost"].sum()) <= 0:
        raise ContractViolation("매매가 있었는데 비용이 0 입니다 — 비용 모델이 적용되지 "
                                "않고 있습니다(회전율 > 0 인 분기가 존재).")
    if float(_R0["cost"].abs().sum()) > 1e-12:
        raise ContractViolation("apply_costs=False 인데 비용이 발생했습니다 — "
                                "비용 스위치가 동작하지 않습니다.")
    # 거래세는 '이력'이어야 한다 — 단일 세율이면 10년 중 어느 시점을 골라도 값이 같다.
    if len(QVF_TAX_SCHEDULE) < 5:
        raise ContractViolation("증권거래세를 단일 세율로 처리하고 있습니다 — 10년간 여섯 번 바뀌었습니다.")
    if abs(qvf_sell_tax(as_ts("2017-06-01")) - qvf_sell_tax(as_ts("2024-06-01"))) < 1e-9:
        raise ContractViolation("거래세 이력표가 시점에 따라 다른 세율을 주지 않습니다 — "
                                "표만 있고 적용되지 않고 있습니다.")
    return (f"실제 백테스트로 net ≤ gross 확인 · 거래세 {len(QVF_TAX_SCHEDULE)}단계가 "
            f"시점별로 다르게 적용됨 (cost_model={QVF_COST_MODEL})")


@_contract("Q11", "결측을 0 으로 채우지 않는다 — z-score 는 표본 부족 시 NaN 을 유지한다")
def _q11():
    v = pd.Series([1.0, 2.0, np.nan, 4.0, np.inf, -np.inf])
    cells = pd.Series(["A"] * 6)
    z = xsec_z_pct(v, cells, min_n=3)
    if z.isna().sum() < 3:
        raise ContractViolation("±inf 와 NaN 이 결측으로 유지되지 않았습니다.")
    # ★ 위 검정은 '한쪽 방향'이라 z 를 전부 NaN 으로 만드는 회귀도 통과한다(결측이 3개 이상이면
    #   되니까). 그러면 z-score 무결성을 지킨다는 계약이 정작 축이 통째로 죽은 상태를 승인한다.
    #   유효값이 실제로 살아 있고 표준화가 됐는지도 같이 본다.
    _ok = z[v.notna() & np.isfinite(v)]
    if _ok.isna().any():
        raise ContractViolation("정상 관측치의 z 까지 NaN 이 되었습니다 — 표준화가 죽었습니다.")
    if abs(float(_ok.mean())) > 1e-6 or abs(float(_ok.std(ddof=0)) - 1.0) > 1e-6:
        raise ContractViolation(
            f"관측치 z 가 표준화되지 않았습니다(평균 {float(_ok.mean()):+.3g} · "
            f"표준편차 {float(_ok.std(ddof=0)):.3g}).")
    z2 = xsec_z_pct(pd.Series([1.0, 2.0]), pd.Series(["A", "A"]), min_n=8)
    if not z2.isna().all():
        raise ContractViolation("표본 부족 셀의 z 가 NaN 이 아닙니다 — 0 으로 채우면 그 종목이 "
                                "'평균적인 종목'으로 둔갑합니다.")
    return "±inf → NaN · 표본부족 셀 → NaN 유지"


@_contract("Q12", "DART 호출 한도 — 고정 상수가 아니라 실측으로 확정된다")
def _q12():
    s = pinned_src("DartQuota", DartQuota)
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
    #
    #   ★★ 단, '헤더값과 같아야 한다'로 검정하면 안 된다 ★★
    #   DartQuota 는 과거 실측 한도를 DART_DAILY_LIMIT 에 되돌려 넣는다(q06:938). 그게 바로
    #   "남은 호출량을 실시간으로 체크해서 그만큼 쓰라"는 요구사항의 구현이다. 그런데 옛 검정은
    #   실효값 != 헤더값이면 무조건 위반으로 봤다 — 실측이 성공할수록 계약이 깨지는 구조였고,
    #   실제로 사용자의 실행이 시작 4초 만에 여기서 멈췄다(실측 14,047 vs 헤더 20,000).
    #   그래서 '무엇과 같은가'가 아니라 '어디서 온 값인가'를 검정한다:
    #     허용 = 헤더 힌트 | 저널에서 실측된 값(과거/오늘)
    #     위반 = 그 어느 쪽도 아닌 값 = 코드에 박힌 상수가 이긴 경우
    _eff, _hint = int(DART_DAILY_LIMIT), int(DART_DAILY_LIMIT_HINT)
    _measured = {int(v) for v in (getattr(DQUOTA, "hist_limit", None),
                                  getattr(DQUOTA, "observed_limit", None)) if v}
    if _eff != _hint and _eff not in _measured:
        raise ContractViolation(
            f"실효 DART_DAILY_LIMIT 이 {_eff:,} 인데 헤더 힌트({_hint:,})도 아니고 "
            f"저널 실측치{sorted(_measured) or '(없음)'}도 아닙니다 — 조립 순서상 뒤에 오는 "
            f"하드코딩이 헤더를 이기고 있습니다. DartQuota 생성 시 되찾아오는지 확인하세요.")
    _src = "실측" if _eff in _measured else "헤더 힌트(실측 기록 없음)"
    return f"공용 저널 합산 · 020/021 구분 · 실효 한도 {_eff:,} ({_src})"


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
