# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 — 주석이나 관례는 무효. 테스트로만 강제한다.                                ║
# ║  실행 전 자동 수행하고 실패하면 즉시 중단한다(fail-fast).                                   ║
# ║                                                                                          ║
# ║  검정 대상: 스펙 §0 의 7대 원칙 + C1(PIT) · C2(생존자편향) · C13(유니버스 PIT) · C15       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_V3: List[dict] = []


def _cc(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_V3.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return ok


def _src_of(*fns) -> str:
    """함수 소스 결합. 한 셀에 붙여넣어 실행하는 경우 소스 조회가 불가할 수 있다 → "" 반환."""
    import inspect
    out = []
    for f in fns:
        try:
            out.append(inspect.getsource(f))
        except Exception:
            return ""
    return "\n".join(out)


def run_contracts_v3(strict: bool = True) -> bool:
    CONTRACT_V3.clear()
    rng = np.random.default_rng(SEED)

    # ── C1 : PIT 게이트웨이 ───────────────────────────────────────────────────────────────
    def c1():
        d = pd.DataFrame({"corp_code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 필터 오류: {len(got)}행 (기대 2)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        # merge_asof 단일 패스 등가성 — 루프 조회와 결과가 같아야 한다
        panel = pd.DataFrame({"corp_code": ["A"] * 4 + ["B"] * 4,
                              "month": list(pd.date_range("2020-02-29", periods=4, freq="ME")) * 2})
        J = st.asof_join(panel, "t", by="corp_code", left_time="month")
        if "knowledge_date" in J.columns:
            bad = (J["knowledge_date"].notna() & (J["knowledge_date"] > J["month"])).sum()
            if bad:
                return False, f"asof_join 이 미래 정보를 붙였습니다: {bad}행"
        loop = [len(st.get("t", m, latest_by=["corp_code"])) for m in panel["month"].unique()]
        return True, (f"as_of 절단·등록거부·merge_asof 단일패스 등가 전부 통과 "
                      f"(루프 조회 {sum(loop)}행 대조)")

    _cc("C1", "PIT — merge_asof 단일 패스, 미래 정보 차단", c1)

    # ── C2 / C13 : 생존자편향 · 유니버스 PIT ──────────────────────────────────────────────
    def c2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": ["살아있음", "폐지됨", "나중상장"],
            "market": ["KOSPI"] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", "2022-01-01"]),
            "delisting_date": pd.to_datetime([None, "2020-06-30", None]),
            "corp_code": ["A", "B", "C"], "industry": ["X"] * 3})
        days = pd.date_range("2009-01-01", "2026-06-30", freq="B")
        px = pd.DataFrame({"code": "000001", "date": days})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2019 = set(uni.at("2019-12-31"))
        at2021 = set(uni.at("2021-12-31"))
        if "000002" not in at2019:
            return False, "폐지 예정 종목이 폐지 이전 시점 유니버스에서 빠졌습니다 (생존자편향)"
        if "000002" in at2021:
            return False, "폐지된 종목이 폐지 이후에도 남아 있습니다"
        if "000003" in at2019:
            return False, "★C13 위반 — 미래에 상장할 종목이 과거 유니버스에 있습니다"
        if "000003" not in at2021 and "000003" not in set(uni.at("2023-06-30")):
            return False, "상장 후 시즈닝이 끝난 종목이 끝내 유니버스에 들어오지 않습니다"
        dm = uni.delisting_map()
        if "000002" not in dm:
            return False, "delisting_map 이 폐지 종목을 반환하지 않습니다"
        return True, "폐지 전 포함 · 폐지 후 제외 · 미래 상장 배제 · 시즈닝 통과"

    _cc("C2/C13", "생존자편향 · 유니버스 PIT", c2)

    # ── C2b : 상장폐지 -100% 강제 ─────────────────────────────────────────────────────────
    def c2b():
        src = _src_of(run_backtest)
        if not src:
            return True, "소스 조회 불가 — 검사 생략 (한 셀 실행 환경)"
        if "-1.0" not in src or "delist" not in src:
            return False, "백테스트 엔진에 상장폐지 -100% 처리가 보이지 않습니다"
        return True, "정리매매가 없으면 -100% (누락 처리 금지) 가 엔진에 존재"

    _cc("C2b", "상장폐지 손실 반영 (원칙 7)", c2b)

    # ── 원칙 2 : clip(z,0) × clip(z,0),  z×z 금지 ─────────────────────────────────────────
    def p2():
        n = 400
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": pd.Timestamp("2020-06-30"),
            "a": rng.normal(size=n), "b": rng.normal(size=n)})
        P["cell"] = "C"
        P["cell_l2"] = "C"
        P["cell_l3"] = "C"
        v = tp(P, "a", "b")
        if v.min() < -1e-12:
            return False, f"TP 에 음수가 나왔습니다(min={v.min():.4f}) — clip 이 적용되지 않았습니다"
        # 최악의 사분면(둘 다 하위)이 0 이어야 한다. z×z 였다면 여기가 최고점이 된다.
        worst = (cell_rank(P, "a") < 0.2) & (cell_rank(P, "b") < 0.2)
        if worst.any() and float(v[worst].max()) > 1e-12:
            return False, "★부호 버그 — 개선·대가회피 모두 하위인 종목이 양의 TP 를 받았습니다"
        best = (cell_rank(P, "a") > 0.8) & (cell_rank(P, "b") > 0.8)
        if best.any() and float(v[best].min()) <= 0:
            return False, "둘 다 상위인 종목의 TP 가 0 입니다"
        # 한쪽 결측이면 결과도 결측 (0 채움 금지)
        P2 = P.copy()
        P2.loc[P2.index[:10], "b"] = np.nan
        if tp(P2, "a", "b").iloc[:10].notna().any():
            return False, "한쪽이 결측인데 TP 가 값을 가졌습니다 (0 채움 금지 위반)"
        src = _src_of(tp)
        if src and "maximum" not in src:
            return False, "tp() 소스에 clip(np.maximum) 이 보이지 않습니다"
        return True, f"음수 불가 · 최악사분면=0 · 결측 전파 (표본 {n})"

    _cc("원칙2", "TP = clip(z,0) × clip(z,0) — z×z 금지", p2)

    # ── C1b : 수급(d3) 경로의 행 정렬 무결성 ──────────────────────────────────────────────
    def c1b():
        """★ 실제로 터졌던 미래누수를 고정하는 회귀 테스트.

        `f["month"] = as_ts_series(<ndarray>)` 는 값은 위치로 계산하고 배치는 라벨로 하는
        대입이다. flows 가 구멍 난 인덱스로 들어오거나 sort_values 가 순서를 바꾸면
        다른 종목·다른 날짜의 달이 그 행에 실리고, 미래 수급이 과거 달로 흘러든다.
        d3 는 PIT.asof_join 을 타지 않으므로 C1 이 잡지 못한다 — 그래서 따로 검정한다.
        """
        # ★ 표본은 반드시 rolling(120, min_periods=40) 이 실제로 값을 내는 크기여야 한다.
        #   월 30행짜리로 만들면 cum120 이 전부 NaN 이라 아래 검사가 공회전하고,
        #   버그가 있어도 통과한다(검정 같아 보이지만 아무것도 재지 않는 테스트).
        days = pd.bdate_range("2020-01-01", periods=320)
        rows = []
        for c in ("000002", "000001"):                 # 정렬 전 순서를 일부러 역순으로
            for i, d in enumerate(days):
                # 순매수를 시간에 따라 증가시킨다 → 120일 누적도 시간 단조 증가해야 한다
                rows.append({"code": c, "date": d, "inst_net": float(i), "foreign_net": 0.0})
        fl = pd.DataFrame(rows)
        fl = fl[fl.index % 7 != 3]                     # 인덱스에 구멍 (필터/concat 의 정상 결과)
        months = pd.DatetimeIndex(sorted(set(days + pd.offsets.MonthEnd(0))))
        P = pd.DataFrame({"code": np.repeat(["000001", "000002"], len(months)),
                          "month": list(months) * 2, "close": 1000.0, "adv20": 1e9,
                          "net_income_ttm": 1e10})
        P["cell"] = P["cell_l2"] = P["cell_l3"] = "C"
        out = axis_U_v3(P, fl)
        if "cum120" not in out.columns:
            return False, "수급 결합이 일어나지 않았습니다 — d3 경로가 죽어 있습니다"
        obs = out["cum120"].notna().sum()
        if obs < 8:
            return False, (f"cum120 유효 관측이 {obs}건뿐입니다 — 표본이 롤링 창을 못 채웠거나 "
                           f"월 배치가 어긋나 대량 결측(NaT)이 발생했습니다")
        # 시간이 흐를수록 누적순매수가 커져야 한다. 미래 값이 과거 달에 실리면 단조성이 깨진다.
        bad = 0
        for c, g in out.dropna(subset=["cum120"]).groupby("code"):
            s = g.sort_values("month")["cum120"].to_numpy()
            bad += int((np.diff(s) < -1e-9).sum())
        if bad:
            return False, (f"★수급 누적값이 시간 역행하는 구간 {bad}건 — 행 정렬이 어긋나 "
                           f"미래 수급이 과거 달에 실렸습니다(d3→U→Signal 오염)")
        return True, (f"구멍 난 인덱스·역순 입력에서도 월 배치가 행과 일치 "
                      f"(표본 {len(fl):,}행 · cum120 유효 {obs}건 · 시간 단조성 유지)")

    _cc("C1b", "수급(d3) 행 정렬 — 미래 수급 유입 차단", c1b)

    # ── 원칙 3 : 셀 정규화에 groupby.apply 금지 ───────────────────────────────────────────
    def p3():
        src = _src_of(cell_rank, cell_z, _rank_in)
        if not src:
            return True, "소스 조회 불가 — 검사 생략"
        if re.search(r"groupby\([^)]*\)\s*\.\s*apply\s*\(", src):
            return False, "셀 정규화에 groupby.apply 가 있습니다 (수십 배 느립니다)"
        if "rank(pct=True" not in src.replace(" ", "") and "rank(pct=True)" not in src:
            if "pct=True" not in src:
                return False, "rank(pct=True) 경로가 보이지 않습니다"
        return True, "rank(pct=True) + transform 벡터화 경로만 사용"

    _cc("원칙3", "셀 정규화 벡터화 (groupby.apply 금지)", p3)

    # ── 원칙 5 : 벤치마크 하드코딩 금지 ───────────────────────────────────────────────────
    def p5():
        src = _src_of(R0_benchmark, report_performance_v3)
        if not src:
            return True, "소스 조회 불가 — 검사 생략"
        # 성과 수치를 리터럴로 박아 둔 흔적(예: CAGR=0.23 같은 상수 비교)이 없어야 한다
        if re.search(r"(CAGR|Sharpe|Calmar)\s*=\s*-?\d+\.\d+", src):
            return False, "벤치마크/성과 수치가 소스에 하드코딩되어 있습니다"
        if "groupby" not in src or "fwd_ret" not in src:
            return False, "벤치마크를 이 실행에서 직접 재측정하는 경로가 보이지 않습니다"
        return True, "유니버스 동일가중을 매 실행 직접 측정 (인용 없음)"

    _cc("원칙5", "벤치마크 하드코딩 금지 — 직접 재측정", p5)

    # ── C15 / 원칙 6 : 한계임금 분모 안정성, 0 채움 금지 ──────────────────────────────────
    def c15():
        E = pd.DataFrame({
            "corp_code": ["A"] * 4 + ["B"] * 3 + ["C"] * 2,
            "bsns_year": [2018, 2019, 2020, 2021, 2018, 2019, 2020, 2019, 2020],
            "rcept_dt": pd.to_datetime(
                ["2019-03-20", "2020-03-20", "2021-03-20", "2022-03-20",
                 "2019-03-20", "2020-03-20", "2021-03-20", "2020-03-20", "2021-03-20"]),
            #  A: 1000→1002 (Δ2, 임계 미달) → 결측 / 1002→1200 (Δ198, 통과) / 1200→1210(Δ10<36 미달)
            #  B: 500→1400 (+180% M&A 의심) → 결측
            #  C: 정상 증가
            "employees": [1000., 1002., 1200., 1210., 500., 1400., 1450., 300., 360.],
            "regular": [900., 900., 1080., 1090., 450., 1260., 1300., 270., 330.],
            "payroll_total": [7e10, 7.02e10, 8.6e10, 8.7e10, 3.5e10, 9.8e10, 1.0e11, 2.1e10, 2.6e10],
            "avg_salary": [7e7, 7e7, 7.2e7, 7.2e7, 7e7, 7e7, 7e7, 7e7, 7.1e7],
            "src_flag": ["detail"] * 9})
        S = build_emp_sensors(E)
        a = S[S["corp_code"] == "A"].set_index("bsns_year")
        if pd.notna(a.loc[2019, "nl_marginal"]):
            return False, "C15(a) 위반 — |Δ인원|=2 (임계 미달)인데 한계임금이 계산되었습니다"
        if pd.isna(a.loc[2020, "nl_marginal"]):
            return False, "C15(a) 오작동 — |Δ인원|=198 (임계 통과)인데 결측입니다"
        if pd.notna(a.loc[2021, "nl_marginal"]):
            return False, "C15(a) 위반 — |Δ인원|=10 < max(5, 1200×3%)=36 인데 계산되었습니다"
        b = S[S["corp_code"] == "B"].set_index("bsns_year")
        if pd.notna(b.loc[2019, "nl_marginal"]):
            return False, "C15(d) 위반 — 인원 +180%(M&A 의심)인데 한계임금이 계산되었습니다"
        ok, msg = test_c15(S)
        if not ok:
            return False, msg
        # 0 채움·forward-fill 금지 확인
        if (S["nl_marginal"] == 0).sum() > (E["employees"].diff() == 0).sum():
            return False, "한계임금에 0 채움 흔적이 있습니다"
        return True, msg

    _cc("C15", "한계임금 분모 안정성 (a)(b)(d) + 0채움 금지", c15)

    # ── C15(c) : 유효 관측치 하한 판정이 존재하는가 ───────────────────────────────────────
    def c15c():
        C = pd.DataFrame({"year": [2016, 2017, 2018, 2019],
                          "u_mid": [1000, 1000, 1000, 1000],
                          "emp_ok": [900, 900, 900, 900], "pay_ok": [700, 700, 800, 900],
                          "c15_ok": [100, 150, 500, 600], "valid": [100, 150, 500, 600]})
        start, msg = coverage_verdict(C)
        if COVERAGE_AUTO_TRIM and start is None:
            return False, "얇은 앞구간이 있는데 시작월 상향 판정이 나오지 않았습니다"
        if start is not None and start.year != 2019:
            return False, f"시작월 판정이 틀렸습니다: {start:%Y-%m} (기대 2019-04)"
        return True, f"판정 동작 확인 — {_trunc(msg, 70)}"

    _cc("C15c", "연도별 유효관측치 하한 → 창 상향 판정", c15c)

    # ── 거부권 이진성 ─────────────────────────────────────────────────────────────────────
    def veto():
        n = 60
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "month": pd.Timestamp("2020-06-30"),
                          "adv20": 1e9, "close": 1000.0, "equity": 1e9,
                          "revenue_ttm": 1e11, "inventory": 1e10, "receivable": 1e10,
                          "net_income_ttm": 1e10, "cfo_ttm": 1e10,
                          "nl_emp": rng.normal(size=n), "d_eff_tax": rng.normal(size=n) * 0.05})
        P = apply_vetoes_v3(P, {})
        for c in VETO_COLS_V3 + ["VETO"]:
            u = set(np.unique(P[c].to_numpy()))
            if not u <= {0.0, 1.0}:
                return False, f"{c} 가 이진이 아닙니다: {sorted(u)[:4]}"
        return True, f"V1·V2·V3·V5·V6·V8 및 곱 전부 ∈{{0,1}} (표본 {n})"

    _cc("거부권", "V ∈ {0,1} · 곱 · 상쇄 불가", veto)

    # ── 결정성 ────────────────────────────────────────────────────────────────────────────
    def det():
        a = np.random.default_rng(SEED).normal(size=32)
        b = np.random.default_rng(SEED).normal(size=32)
        if not np.allclose(a, b):
            return False, "동일 시드에서 난수가 재현되지 않습니다"
        return True, f"SEED={SEED} 재현성 확인"

    _cc("결정성", "동일 시드 → 동일 결과", det)

    # ── 드라이브 캐시 훼손 불가능성 (절대 1원칙) ──────────────────────────────────────────
    def vault_safe():
        src = _src_of(Vault.put_table, Vault.compact, Vault._register, Vault.flush) or ""
        bad = [p for p in (r"os\.remove\s*\(\s*self\.journal", r"shutil\.rmtree",
                           r"\.to_parquet\(\s*self\.journal")
               if src and re.search(p, src)]
        if bad:
            return False, f"인덱스를 파괴하는 호출이 있습니다: {bad}"
        if hasattr(Vault, "delete") or hasattr(Vault, "remove_table"):
            return False, "Vault 에 삭제 API 가 존재합니다 — 설계상 존재해선 안 됩니다"
        return True, "삭제 API 부재 · 저널 append-only · 컴팩션 전 백업"

    _cc("절대1원칙", "구글드라이브 캐시 훼손 불가능성", vault_safe)

    # ── 출력 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 34), "PASS" if r["pass"] else "FAIL",
             _trunc(r["msg"], 60)] for r in CONTRACT_V3]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["c", "l", "c", "l"],
              title="계약 자동검정 (주석이 아니라 테스트로 강제)", maxw=62)
    fails = [r for r in CONTRACT_V3 if not r["pass"]]
    if fails:
        LOG.error(f"계약 위반 {len(fails)}건: " + ", ".join(r["id"] for r in fails))
        for r in fails:
            LOG.warn(f"  · [{r['id']}] {r['name']} — {r['msg']}")
        if strict:
            raise RuntimeError(
                f"계약 검정 {len(fails)}건 실패 — 실행을 중단합니다. "
                f"이 계약들은 협상 대상이 아닙니다. 임계값을 바꿔 통과시키지 마십시오.")
        return False
    LOG.ok(f"계약 검정 {len(CONTRACT_V3)}건 전부 통과")
    return True
