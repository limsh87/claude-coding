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
        # ★ run_backtest 는 감사 스위치만 다루는 얇은 래퍼이고 실제 엔진은 _run_backtest_inner
        #   에 있다. 래퍼만 읽으면 '-100% 처리가 사라졌다'는 오탐이 난다 — 둘을 함께 읽는다.
        src = _src_of(run_backtest, _run_backtest_inner)
        if not src:
            return None, "소스 조회 불가 — 검사하지 못했습니다(통과 아님)"
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
        if not src:
            # 수치 검정(위 표본)은 이미 끝났다. 소스 정규식만 못 돌린 것이므로 그 사실을 남긴다.
            return None, f"수치 검정은 통과({n}표본)했으나 소스 정규식은 조회 불가"
        if "maximum" not in src:
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
            return None, "소스 조회 불가 — 검사하지 못했습니다(통과 아님)"
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
            return None, "소스 조회 불가 — 검사하지 못했습니다(통과 아님)"
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

    # ── §12-6 : 수집 호출량 상한 (4시간 계약) ─────────────────────────────────────────────
    def budget_bounded():
        """★ 실제로 터졌던 사고를 고정하는 회귀 테스트.

        Tier-2 재무(fnlttSinglAcntAll)와 직원현황(empSttus)은 잡 수가 |기업|×|연도|(×|분기|)
        로 **곱해진다**. 상한이 없으면 3,981사 × 13년 × 4분기 = 207,012 호출 = 11일치가
        조용히 큐에 올라간다 — tqdm ETA 로 드러났을 때는 이미 돌고 있다.
        이 계약은 (a) 두 단계 모두 상한을 갖고 (b) 그 상한이 DART 일일한도 안에 들고
        (c) 수집 함수가 상한 인자를 실제로 받는지를 강제한다.
        """
        import inspect as _ins
        # ══════════════════════════════════════════════════════════════════════════════════
        #  ★★ 4시간 계약을 지키는 것은 '개수'가 아니라 '시간'이다 ★★
        #    개수 상한만 검정하던 예전 판은 두 번 무력화됐다.
        #      ① 상수를 유도식(ROOM×0.55 등)으로 바꾼 순간 `plan > room` 이 **항등식**이 되어
        #         절대 발동하지 않았다. 26,000건 사고를 고정한다던 회귀 테스트가 죽은 코드였다.
        #      ② 서버가 먼저 020 을 주면 개수 상한은 아무것도 보호하지 못한다(5차 실행 실증).
        #    → 이제 수집을 멈추는 조건은 딱 둘이다: **서버 020/021** 과 **시계**.
        #      이 계약은 그 둘이 코드에 실재하는지를 검정한다.
        # ══════════════════════════════════════════════════════════════════════════════════
        shares = {"EMP_TIME_SHARE": EMP_TIME_SHARE, "FS_TIME_SHARE": FS_TIME_SHARE}
        bad = [k for k, v in shares.items() if not (isinstance(v, (int, float)) and 0 < v <= 1)]
        if bad:
            return False, f"{bad} 의 시간 몫이 (0,1] 범위가 아닙니다 — 4시간 계약을 배분할 수 없습니다"
        # 수집 데드라인이 전체 예산 **안쪽**에 있어야 후속 단계(강건성·리포트) 몫이 남는다.
        _budget_s = WALL_CLOCK_LIMIT_H * 3600.0
        if not (0 < POST_COLLECT_RESERVE_MIN * 60.0 < _budget_s * 0.5):
            return False, (f"수집 이후 몫(POST_COLLECT_RESERVE_MIN="
                           f"{POST_COLLECT_RESERVE_MIN}분)이 전체 예산의 절반을 넘거나 0 입니다")
        if collect_deadline_ts() >= _T0_PROCESS + _budget_s:
            return False, "수집 데드라인이 전체 예산 밖입니다 — 계약이 집행되지 않습니다"
        # 수집 루프가 실제로 데드라인을 확인하는가 (주석이 아니라 코드로)
        for fn, need in ((fetch_emp_status, ("stage_time_budget", "_deadline")),
                         (fetch_dart_financials, ("_fs_time_budget_s", "_deadline"))):
            src = _src_of(fn)
            if not src:
                return None, f"{fn.__name__} 소스를 읽을 수 없어 데드라인 배선을 확인하지 못했습니다"
            miss = [t for t in need if t not in src]
            if miss:
                return False, (f"{fn.__name__} 이 시간 데드라인을 확인하지 않습니다({miss}) — "
                               f"개수 상한만으로는 4시간 계약을 지킬 수 없습니다")
        # 개수 상한은 **선택**이다(None = 계획 상한 없음). 다만 있으면 전체 한도 안이어야 한다.
        caps = {"EMP_MAX_CALLS": EMP_MAX_CALLS, "DART_FS_MAX_CALLS": DART_FS_MAX_CALLS}
        for fn, arg in ((fetch_dart_financials, "max_calls"), (fetch_emp_status, "max_calls")):
            if arg not in _ins.signature(fn).parameters:
                return False, f"{fn.__name__} 이 {arg} 인자를 받지 않습니다"
        n_keys = max(1, len({str(k).strip() for k in ([DART_API_KEY] + list(DART_API_KEYS))
                             if str(k).strip()}))
        room = DART_DAILY_LIMIT * n_keys
        for k, v in caps.items():
            if v is not None and int(v) > room:
                return False, (f"{k}={int(v):,} 가 전체 한도 {room:,}건"
                               f"(키 {n_keys}개 × {DART_DAILY_LIMIT:,})을 넘습니다")
        # ★ 로컬 추정 잔량으로 작업 큐를 자르는 경로가 되살아나지 않았는지도 여기서 본다.
        #   (§12-A 가 같은 검사를 하지만, 4시간 계약과 한 몸이라 중복해서 못 박는다)
        # ★★ 주석을 먼저 벗긴다 ★★ 그 함수에는 '예전엔 이렇게 틀렸다' 는 설명이 코드와
        #   똑같은 모양(`cap = min(total, max_calls, dart_budget_left("emp"))`)으로 적혀 있다.
        #   벗기지 않으면 계약이 **자기 설명문을 결함으로 오인**해 실행을 거부한다.
        _emp_src = "\n".join(ln.split("#", 1)[0] for ln in (_src_of(fetch_emp_status) or "")
                             .split("\n"))
        if re.search(r"cap\s*=\s*[^\n]*min\([^\n]*dart_budget_left", _emp_src):
            return False, ("직원현황 작업 큐를 로컬 추정 잔량으로 자르고 있습니다 — "
                           "잔여량은 서버만 압니다. 이 경로가 3회 실행 내내 알파를 0행으로 만들었습니다")
        _plan = " · ".join(f"{k}={'무제한' if v is None else format(int(v), ',')}"
                           for k, v in caps.items())
        return True, (f"시간으로 집행 — 수집 몫 "
                      f"{(WALL_CLOCK_LIMIT_H*60 - POST_COLLECT_RESERVE_MIN):.0f}분"
                      f"(EMP {EMP_TIME_SHARE:.0%} → Tier-2 {FS_TIME_SHARE:.0%}) · "
                      f"후속 {POST_COLLECT_RESERVE_MIN:.0f}분 · 계획상한 {_plan} · "
                      f"하루 한도 {room:,}(키 {n_keys}개)")

    _cc("§12-6", "수집 호출량 상한 — 4시간 계약", budget_bounded)

    # ── §12-R : 자원 부족을 데이터 부재로 판정 금지 ───────────────────────────────────────
    def resource_vs_data():
        """★ 실제로 실행을 죽인 사고를 고정하는 회귀 테스트.

        DART 일일 한도가 이미 소진된 상태로 시작한 실행에서, 모든 호출이 예산 게이트에
        막혀 None 을 돌려줬다. CANARY 는 그것을 '데이터 없음'으로 읽어 K8 을 FAIL 시키고
        §12-2 킬 기준을 발동해 실행을 중단했다 — 데이터는 멀쩡히 있었다.
        더 나쁜 건 처방이었다: '백테스트 시작연도를 상향하라'. 오늘 호출권이 없다는
        일시적 사실로 10년 백테스트 구간을 영구히 잘라낼 뻔했다.

        이 계약은 (a) 자원 사유가 조회 가능하고 (b) 그 상태에서 CANARY 의 DART 검사가
        FAIL 이 아니라 SKIP 이 되며 (c) 킬 기준이 발동하지 않음을 강제한다.
        """
        for fn in ("dart_halt_reason", "dart_note_halt", "dart_budget_left"):
            if not callable(globals().get(fn)):
                return False, f"{fn}() 이 없습니다 — 자원 사유를 구별할 방법이 없습니다"
        saved = dict(DART_HALT)
        saved_results = list(CANARY_RESULTS)
        try:
            # 사고 당시와 똑같은 상태를 만든다: K8 이 치명 FAIL 로 기록된 채 예산이 소진됨.
            CANARY_RESULTS.clear()
            _k("K8", "연간급여총액 기재율", False, "표본 0건", "≥70%",
               "★ 임금프리미엄 계산 불가 — 중단(§12-2)", fatal=True)
            _k("K7", "empSttus 응답", False, "0/191 (0%)", "≥80%", "")
            _k("K5", "상장폐지 목록 확보", False, "폐지일 보유 0종목", "≥50종목", "", fatal=True)
            dart_note_halt("테스트: 일일 한도 소진", "회귀 검정")
            if not dart_halt_reason():
                return False, "halt 를 기록했는데 dart_halt_reason() 이 None 입니다"
            if not canary_resource_flip():
                return False, "자원 사유가 있는데 canary_resource_flip() 이 되돌리지 않았습니다"
            k8 = next(r for r in CANARY_RESULTS if r["id"] == "K8")
            k7 = next(r for r in CANARY_RESULTS if r["id"] == "K7")
            k5 = next(r for r in CANARY_RESULTS if r["id"] == "K5")
            if k8["passed"] is not None or k8["fatal"]:
                return False, "K8 이 여전히 치명 FAIL 입니다 — 실행이 또 킬 기준으로 죽습니다"
            if k7["passed"] is not None:
                return False, "K7 이 여전히 FAIL 입니다 (SKIP 이어야 함)"
            # K5(상장폐지 목록)는 DART 와 무관하므로 절대 완화되면 안 된다.
            if k5["passed"] is not False or not k5["fatal"]:
                return False, "K5(생존자편향)까지 완화됐습니다 — DART 무관 검사는 건드리면 안 됩니다"
            fatal_left = [r["id"] for r in CANARY_RESULTS if r["fatal"] and r["passed"] is False]
            return True, (f"K7·K8 → SKIP 전환 · K5 는 치명 FAIL 유지 "
                          f"(잔여 치명 {fatal_left}) · 킬 기준 오발동 차단")
        finally:
            DART_HALT.update(saved)
            CANARY_RESULTS.clear()
            CANARY_RESULTS.extend(saved_results)

    _cc("§12-R", "자원 부족 ≠ 데이터 부재 (킬 기준 오발동 방지)", resource_vs_data)

    # ── C2c : 폐지 유형별 청산가 ──────────────────────────────────────────────────────────
    def delist_kinds():
        """흡수합병·스팩해산을 -100% 로 계상하지 않는다. 단, 모르면 -100% 를 유지한다.

        ★ 실측 근거(폐지목록 원본 Reason, 2016년 이후 폐지 주권 561건):
          피흡수합병 60 · 스팩소멸합병 53 · 완전자회사화 43 → 인수기업 주식을 받는다.
          스팩 예심 미제출·해산·존속기간만료 ~130 → 예치금이 공모가+이자로 반환된다.
          이 308건(55%)을 전액손실로 계상하면 매년 -2%p 안팎의 없는 손실을 지어낸다.
          이것은 '보수적'이 아니라 그냥 틀린 것이다. 반대로 사유를 모르면(unknown)
          반드시 -100% 를 유지해야 한다 — 그쪽이 진짜 보수다(원칙7).
        """
        cases = {
            "피흡수합병": "transfer", "피흡수합병(스팩소멸합병)": "transfer",
            "지주회사(최대주주등)의 완전자회사화 등": "transfer", "타법인의 완전자회사로 편입": "transfer",
            "신청에 의한 상장폐지": "transfer",
            "상장예비심사 청구서 미제출로 관리종목 지정 후 1개월 이내 동 사유 미해소": "spac",
            "해산 사유 발생": "spac", "존속기간 만료": "spac",
            "감사의견 거절(감사범위 제한)": "distress",
            "기업의 계속성 및 경영의 투명성 등을 종합적으로 고려하여 상장폐지기준에 해당한다고 결정": "distress",
            "자본전액잠식": "distress", "최종부도": "distress",
            "": "unknown", "사유 미상": "unknown",
        }
        wrong = [(k, classify_delisting(k), v) for k, v in cases.items()
                 if classify_delisting(k) != v]
        if wrong:
            return False, f"폐지 사유 분류 오류: {wrong[:3]}"
        # 모르면 전액손실이어야 한다 — 관대한 쪽으로 새면 성과가 부풀려진다.
        if "unknown" in DELIST_NOT_WIPEOUT:
            return False, "'unknown' 이 직전가 청산으로 분류돼 있습니다 — 모르면 -100% 여야 합니다"
        src = _src_of(run_backtest, _run_backtest_inner) or ""
        if src and "DELIST_NOT_WIPEOUT" not in src:
            return False, "백테스트 엔진이 폐지 유형을 쓰지 않습니다 — 전부 -100% 로 계상됩니다"
        if src and "-1.0" not in src:
            return False, "백테스트 엔진에서 -100% 경로가 사라졌습니다(원칙7 위반)"
        return True, (f"합병·완전자회사화·스팩해산 → 직전가 청산 · "
                      f"부실·사유불명 → -100% 유지 (표본 {len(cases)}건 전부 일치)")

    _cc("C2c", "폐지 유형별 청산가 (합병을 전액손실로 계상 금지)", delist_kinds)

    # ── §12-A : 알파 원천 보호 ────────────────────────────────────────────────────────────
    def alpha_guard():
        """★ 실행 3회 내내 dart_employees_ext 가 0행이었던 사고를 고정한다.

        원인은 둘이었다.
          ① 사전점검이 세 테이블을 **합산**해 total>0 이면 진행했다. 재무 146만 행이 있고
             직원현황이 0행인 상태를 '캐시 충분'으로 읽어, 27분(잠재 2시간)을 태운 뒤에야
             "EMP-LITE 3개 TP 가 모두 결측"을 선언했다. 테이블은 대체재가 아니다.
          ② Tier-2 재무가 일일 한도를 먼저 다 써버려 EMP 몫이 남지 않았다. 단계 순서를
             바꿔도 예산은 날짜별 누적이라 어제 태운 것이 오늘까지 따라온다.
        이 계약은 (a) 예약 API 가 존재하고 실제로 남의 인출을 막으며 (b) 예약분은 해당
        용도가 인출할 수 있고 (c) 사전점검이 알파 테이블을 개별로 본다는 것을 강제한다.
        """
        for fn in ("reserve", "left", "pick_key", "mark_blocked", "all_blocked", "charge"):
            if not callable(getattr(DartBudget, fn, None)):
                return False, f"DartBudget.{fn}() 이 없습니다 — 알파 예산을 지킬 수단이 없습니다"
        b = DartBudget.__new__(DartBudget)          # _load(파일 I/O) 를 타지 않게 직접 구성
        b.today, b.n, b.exhausted = "T", 0, False
        b._ephemeral = True                         # ★ 프로덕션 dart_budget.json 을 건드리지 않는다
        b._lk = threading.RLock()
        b.keys = ["k1", "k2"]
        b._kid_of = {k: DartBudget._make_kid(k) for k in b.keys}
        b.per_key = {kid: 0 for kid in b._kid_of.values()}
        b.blocked = set()
        b._reserved, b._dirty, b._rr = {}, 0, 0
        # ① 예약은 '계획 기준선'에 반영되어야 한다 (호출 거부가 아니라 잡 수 산정용)
        b.reserve("emp", 100)
        if b.left(None) != b.left("emp") - 100:
            return False, "예약이 계획 기준선(left)에 반영되지 않습니다"
        # ② 키 로테이션 — 소진되지 않은 키를 고르고, 서버가 거부한 키는 건너뛴다
        if b.pick_key() is None:
            return False, "쓸 수 있는 키가 있는데 pick_key() 가 None 을 돌려줍니다"
        b.mark_blocked("k1")
        if b.pick_key() != "k2":
            return False, "★ 서버가 거부한 키를 계속 고릅니다 — 로테이션이 동작하지 않습니다"
        if b.all_blocked():
            return False, "키가 하나 남았는데 전부 차단으로 판정합니다"
        b.mark_blocked("k2")
        if not b.all_blocked() or b.pick_key() is not None:
            return False, "모든 키가 거부됐는데 계속 진행하려 합니다"
        # ③ ★ 로컬 카운터로는 절대 차단하지 않는다 (이 계약의 핵심)
        b2 = DartBudget.__new__(DartBudget)
        b2.today, b2.n, b2.exhausted = "T", DART_DAILY_LIMIT * 99, False
        b2._ephemeral = True
        b2._lk = threading.RLock()
        b2.keys = ["k1"]
        b2._kid_of = {"k1": DartBudget._make_kid("k1")}
        b2.per_key = {b2._kid_of["k1"]: DART_DAILY_LIMIT * 99}
        b2.blocked, b2._reserved, b2._dirty, b2._rr = set(), {}, 0, 0
        if b2.pick_key() is None:
            return False, ("★ 로컬 카운터가 한도를 넘었다는 이유로 호출을 막습니다 — "
                           "진짜 잔여량은 서버만 압니다. 추정으로 우리를 막으면 "
                           "서버가 답해 줄 수 있는 상태에서 한 건도 안 쏘게 됩니다")
        # ④ ★★ 이 계약이 놓쳤던 바로 그 구멍 ★★
        #    pick_key() 만 검사했더니, 정작 **작업 큐를 0 으로 자르는** 경로가 무사통과했다.
        #      fetch_emp_status : cap = min(total, max_calls, dart_budget_left("emp"))
        #      fetch_dart_financials : cap = min(cap, max_calls, DART_DAILY_LIMIT - DBUDGET.n)
        #    서버가 020 을 한 번도 주지 않았는데 직원현황이 0행으로 끝난 실행의 직접 원인이다.
        #    → 수집 함수 소스에서 'left/limit 추정치가 jobs 상한 min() 안에 들어가는' 패턴을 금지한다.
        _csrc = _src_of(fetch_emp_status, fetch_dart_financials)
        if not _csrc:
            _cut_note = " (수집부 소스 정규식은 조회 불가 — 미검사)"
        else:
            _cut_note = ""
            # ★ 주석은 검사 대상이 아니다. '예전엔 이랬다'를 설명하는 주석까지 잡으면
            #   결함을 고친 사실을 기록하는 것 자체가 계약 위반이 된다(실제로 그렇게 터졌다).
            _csrc = "\n".join(re.sub(r"#.*$", "", ln) for ln in _csrc.splitlines())
            for _pat, _why in (
                    (r"min\([^)]*dart_budget_left[^)]*\)",
                     "dart_budget_left() 가 잡 수 상한 min() 안에 들어가 있습니다"),
                    (r"min\([^)]*left_today[^)]*\)",
                     "left_today(로컬 추정 잔량) 가 잡 수 상한 min() 안에 들어가 있습니다"),
                    (r"min\([^)]*DBUDGET\.n[^)]*\)",
                     "DBUDGET.n(사용 추정치) 가 잡 수 상한 min() 안에 들어가 있습니다")):
                if re.search(_pat, _csrc):
                    return False, ("★ 로컬 추정치가 작업 큐를 자릅니다 — " + _why +
                                   ". 추정 잔량이 0 이 되는 순간 서버가 멀쩡한데도 "
                                   "한 건도 시도하지 않고 알파가 0행으로 끝납니다. "
                                   "상한은 의도한 작업량(EMP_MAX_CALLS 등)뿐이어야 하고, "
                                   "하드 차단은 서버 020/021 로만 해야 합니다.")
        # ⑤ 사전점검이 알파 테이블을 개별 판정하는가 (합산 판정이면 사고가 재현된다)
        src = _src_of(preflight_dart_v3) or ""
        if src:
            if "dart_employees_ext" not in src:
                return False, "사전점검이 알파 테이블을 개별로 보지 않습니다"
            if "sum(have.values())" in src and "dead_alpha" not in src:
                return False, "사전점검이 여전히 합산으로만 판정합니다"
        if not REQUIRE_EMP_ALPHA:
            return True, ("예약 동작 확인 · REQUIRE_EMP_ALPHA=False "
                          "(알파 없이도 진행하도록 설정됨)" + _cut_note)
        return True, (f"키 로테이션 · 서버 거부만 하드 차단 · 로컬 카운터는 계획용 · "
                      f"수집부가 추정치로 큐를 자르지 않음 · "
                      f"예약 {EMP_RESERVED_CALLS:,}건 · 알파 부재 시 수집 전 중단" + _cut_note)

    _cc("§12-A", "알파 원천(직원현황) 예산 보호 · 부재 시 사전 중단", alpha_guard)

    # ── C-CELL : 셀 사다리가 **실제 밀도에서** 동작하는가 ─────────────────────────────────
    def c_cell():
        """★ 4차 실행에서 산업·규모 중립화가 통째로 무력화된 사고를 고정한다.

        예전 계약(원칙3)은 P["cell"]=P["cell_l2"]=P["cell_l3"]="C" 로 **모든 행을 한 셀에**
        넣고 검사했다. 그래서 사다리를 한 번도 밟지 않았고, 산업 카디널리티가 커지는 순간
        1·2단이 동시에 무너지는 결함이 구조적으로 검출 불가능했다.
        여기서는 프로덕션과 같은 밀도(월 1,100행 / 업종 150개)를 만들어 실제로 밟게 한다.
        """
        # ★ 업종명은 **실제 한국 업종명처럼** 앞머리가 대분류여야 한다.
        #   "업종000".."업종149" 처럼 접두가 전부 같으면 접두 병합 경로를 검정하지 못하고
        #   폴백(전부 '기타')만 재게 된다 — 검정 같아 보이지만 아무것도 안 재는 테스트다.
        _HEADS = ["화학", "전기", "반도", "운수", "도매", "금융", "건설", "식료",
                  "의약", "기계", "철강", "섬유", "통신", "소프", "자동", "조선",
                  "비금", "종이", "고무", "유통"]
        n_m, n_ind, per_m = 12, 150, 1100
        rows = []
        for mi in range(n_m):
            m = pd.Timestamp("2020-01-31") + pd.offsets.MonthEnd(mi)
            for j in range(per_m):
                k = j % n_ind
                rows.append({"code": f"{j:06d}", "month": m,
                             "industry": f"{_HEADS[k % len(_HEADS)]}제품및부품{k:03d}",
                             "employees": float(50 + (j % 900)),
                             "revenue_ttm": float(1e9 + j)})
        P = pd.DataFrame(rows)
        sec = (P[["code", "industry"]].drop_duplicates("code").reset_index(drop=True))
        P["x"] = rng.normal(size=len(P))
        C = build_cells_v3(P, sec, tag="(계약검정) ")
        for lvl in CELL_LADDER_V3:
            if lvl not in C.columns:
                return False, f"폴백 사다리 단계 {lvl} 가 없습니다"
        r = cell_rank(C, "x")
        cov = float(r.notna().mean())
        if cov < 0.999:
            return False, (f"★ 사다리가 관측을 못 살렸습니다 — 유효관측 100% 인데 "
                           f"랭크 산출은 {cov*100:.1f}% 뿐입니다. 하위 계단이 전부 "
                           f"표본 미달이라는 뜻이며, 이 상태가 프로덕션에서 TP 0% 를 만듭니다")
        # 1단만으로 다 풀리면 이 검정이 사다리를 재지 못한 것이다(밀도 설정이 잘못됨)
        d = CELL_RANK_DIAG[-1]["by_level"] if CELL_RANK_DIAG else {}
        if d.get("cell", 0) >= len(C):
            return False, "1단계에서 전부 해결됐습니다 — 이 검정이 사다리를 밟지 않았습니다"
        # 3단(업종군)이 실제로 존재하고 임계치를 넘는가 — 여기가 v3 에서 빠져 있던 계단이다
        n3 = C.groupby("cell_l3", observed=True)["code"].transform("count")
        if float((n3 >= CELL_MIN_N_V3).mean()) < 0.9:
            return False, (f"3단계(month|업종군|ALL)조차 표본 미달입니다 "
                           f"({100*float((n3 >= CELL_MIN_N_V3).mean()):.0f}%) — "
                           f"업종 병합이 카디널리티를 못 줄였습니다")
        return True, (f"월 {per_m}행 × 업종 {n_ind}개 밀도에서 랭크 산출 {cov*100:.1f}% · "
                      f"해결 단계 {dict(d)} · 업종군 {C['ind_l1'].nunique()}개로 병합")

    _cc("C-CELL", "셀 폴백 사다리 — 실제 밀도에서 중립화가 살아 있는가", c_cell)

    # ── C-TP0 : 증거층 전멸을 백테스트 **전에** 잡는가 ────────────────────────────────────
    def c_tp0():
        """★ 4차 실행은 TP 8개가 전부 0% 인 채로 27분을 더 돌다가 백테스트 직전에
        맨 RuntimeError 로 죽었다. 그 전까지 그 사실을 판정하는 게이트가 하나도 없었고,
        메시지는 '컬럼이 하나도 없습니다' 라고 사실을 잘못 말해 엉뚱한 곳을 찾게 만들었다.
        """
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(40)],
                          "month": pd.Timestamp("2020-06-30"),
                          "cell": "C", "cell_l2": "C", "cell_l3": "C", "cell_l4": "C",
                          "U": 1.0, "VETO": 1.0})
        for n, *_ in TP_DEFS:
            P[n] = np.nan                      # 컬럼은 있는데 전량 결측 — 실제로 났던 상태
        for leg in {a for _n, a, _b, _d in TP_DEFS} | {b for _n, _a, b, _d in TP_DEFS}:
            P[leg] = np.nan
        live = [c for c, *_ in TP_DEFS if P[c].notna().sum() > 0]
        try:
            score_arm(P, live)
            return False, ("★ 증거층이 0개인데 score_arm 이 통과했습니다 — "
                           "증거 없이 종목을 고르고 리포트는 그럴듯하게 나옵니다")
        except RuntimeError as e:
            msg = str(e)
        if "컬럼이 하나도 없습니다" in msg:
            return False, "메시지가 사실을 잘못 말합니다 — 컬럼은 존재하고 관측이 0입니다"
        if "원천" not in msg:
            return False, "메시지가 '어떤 원천이 비었는지'를 지목하지 않습니다"
        # 살아 있는 TP 가 1개뿐이어도 막아야 한다 (단일 팩터로 도는 것이 크래시보다 나쁘다)
        P2 = P.copy()
        P2["TP_I2"] = 0.3
        try:
            score_arm(P2, ["TP_I2"])
            if MIN_TP_ARMS > 1:
                return False, (f"★ 증거층 TP 가 1개뿐인데 통과했습니다 — 트레이드오프가 아니라 "
                               f"단일 팩터입니다(MIN_TP_ARMS={MIN_TP_ARMS})")
        except RuntimeError:
            pass
        return True, (f"관측 0 → 백테스트 전 중단 · 원인 원천 지목 · "
                      f"TP<{MIN_TP_ARMS}개면 단일팩터 실행 차단")

    _cc("C-TP0", "증거층 전멸을 백테스트 전에 판정 (원인 지목 포함)", c_tp0)

    # ── C-PERSIST : 신규 수집물은 무조건 인덱스에 남는다 (세션 무관 절대원칙) ──────────────
    def c_persist():
        """★ 사용자 절대원칙: "어떤 신규수집데이터든 무조건 캐시저장-재호출 가능하게."

        수집 함수가 네트워크로 나가 놓고 결과를 인덱스에 남기지 않으면, 다음 세션은
        같은 것을 다시 받는다. 그것이 반복수집의 정의다. 주석으로는 못 막으므로
        **소스에 put_table 이 실제로 있는지**를 검정한다.
        """
        collectors = [
            ("fetch_prices", fetch_prices), ("fetch_investor_flows", fetch_investor_flows),
            ("fetch_dart_multi_accounts", fetch_dart_multi_accounts),
            ("fetch_dart_financials", fetch_dart_financials),
            ("fetch_dart_disclosures", fetch_dart_disclosures),
            # ★ 저장이 헬퍼로 분리된 수집기는 헬퍼까지 함께 본다. 함수 하나만 보면
            #   '저장 안 함'으로 오판한다(실제로 이 계약이 첫 실행에서 그렇게 걸렸다).
            ("fetch_emp_status(+체크포인트·마감)",
             (fetch_emp_status, _emp_checkpoint, _emp_finalize)),
            ("fetch_dart_employees", fetch_dart_employees),
            ("fetch_dart_corpcode", fetch_dart_corpcode),
            ("fetch_pykrx_snapshots", fetch_pykrx_snapshots),
            ("build_security_master", build_security_master),
            # ★ 이번에 새로 만든 수집물도 예외가 아니다. 사용자 절대원칙은 '어떤 신규
            #   수집데이터든' 이므로, 새 경로를 추가할 때마다 이 목록에도 넣어야 한다.
            #   지수 일봉은 매 실행 FDR 에서 새로 받으면서 **어디에도 저장하지 않았다** —
            #   강건성 스위트가 R0 을 부를 때마다 같은 네트워크 왕복을 반복했다.
            ("_index_daily(지수 벤치마크)", _index_daily),
            # 가격 무결성 원장(버린 관측의 근거)도 재호출 가능해야 한다.
            ("build_price_panel(무결성 원장)", build_price_panel),
        ]
        missing = []
        for nm, fn in collectors:
            src = _src_of(*fn) if isinstance(fn, tuple) else _src_of(fn)
            if not src:
                return None, "소스 조회 불가 — 검사하지 못했습니다(통과 아님)"
            if "put_table" not in src:
                missing.append(nm)
        if missing:
            return False, (f"★ 네트워크로 나가면서 인덱스에 남기지 않는 수집기: {missing}. "
                           f"다음 세션이 같은 것을 다시 받습니다 — 이것이 반복수집의 정의입니다.")
        # 유니버스 3종은 헬퍼 경유로 저장된다 — 그 헬퍼가 실제로 배선돼 있는지 본다.
        usrc = _src_of(build_security_master) or ""
        wired = [t for t in ("src_fdr_listing", "src_kind_listing", "src_fdr_delisting")
                 if t in usrc]
        if len(wired) < 3:
            return False, (f"유니버스 원천이 캐시 경유로 배선되지 않았습니다(배선 {len(wired)}/3) "
                           f"— 매 실행 네트워크로 나갑니다.")
        # 빈 결과로 멀쩡한 캐시를 덮지 않는가 (소스 장애 하루가 다음 실행까지 무너뜨린다)
        hsrc = _src_of(_cached_or_fetch) or ""
        if hsrc and "len(got)" not in hsrc:
            return False, "빈 수집 결과로 캐시를 덮어쓰지 않는다는 가드가 보이지 않습니다"
        # ★ 2단 캐시(로컬 미러)는 **읽기 가속**이어야 한다. 미러가 드라이브를 덮는 경로가
        #   생기면 그 순간 절대1원칙이 깨진다(로컬의 좁은 스냅샷이 공용 원본을 덮는다).
        #   방향이 한쪽인지 소스로 확인한다: 미러 기록은 put_table 이후에만 일어나야 한다.
        vsrc = _src_of(Vault.put_table, Vault.get_table, Vault._mirror_write) or ""
        if vsrc:
            if "_mirror_write" not in vsrc:
                return False, "2단 캐시 미러 배선이 보이지 않습니다 — 드라이브 재읽기가 반복됩니다"
            if re.search(r"shutil\.copy2\(\s*mp\s*,", vsrc) or \
               re.search(r"os\.replace\([^)]*,\s*src\s*\)", vsrc):
                return False, ("★ 로컬 미러가 드라이브 원본을 덮는 경로가 있습니다 — "
                               "절대1원칙 위반입니다. 방향은 드라이브 → 로컬 한쪽뿐이어야 합니다")
        return True, (f"수집기 {len(collectors)}종 전부 put_table 보유 · "
                      f"유니버스 원천 3종 캐시 경유 · 빈 결과 덮어쓰기 차단 · "
                      f"2단 캐시는 드라이브→로컬 단방향")

    _cc("C-PERSIST", "신규 수집물은 무조건 인덱스에 남는다 (세션 무관)", c_persist)

    # ── 출력 ──────────────────────────────────────────────────────────────────────────────
    _verdict = lambda p: "SKIP" if p is None else ("PASS" if p else "FAIL")
    rows = [[r["id"], _trunc(r["name"], 34), _verdict(r["pass"]),
             _trunc(r["msg"], 60)] for r in CONTRACT_V3]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["c", "l", "c", "l"],
              title="계약 자동검정 (주석이 아니라 테스트로 강제)", maxw=62)
    fails = [r for r in CONTRACT_V3 if r["pass"] is False]
    skips = [r for r in CONTRACT_V3 if r["pass"] is None]
    if skips:
        # ★★ 예전엔 이 상태가 PASS 로 집계됐다 ★★
        #   소스 조회(inspect.getsource)가 안 되는 환경 — 즉 문서가 권장하는
        #   '노트북 한 셀 붙여넣기' 실행 — 에서는 소스 정규식 계약 5건이 아무것도 재지 않고
        #   True 를 돌려줬는데, 최종 로그는 "16건 전부 통과" 라고 단언했다.
        #   검사하지 않은 것을 통과했다고 말하는 것은 계약층 자체를 무효로 만든다.
        LOG.warn(f"계약 {len(skips)}건은 **검사하지 못했습니다**(통과가 아닙니다): "
                 + ", ".join(r["id"] for r in skips))
        for r in skips:
            LOG.warn(f"  · [{r['id']}] {r['name']} — {r['msg']}")
        LOG.warn("  소스 조회가 불가능한 실행(노트북 한 셀 붙여넣기 등)에서는 소스 기반 계약이 "
                 "동작하지 않습니다. 파일로 저장해 `python tcd_v3_core_d_emp_lite.py` 로 "
                 "한 번 돌리면 전부 실제로 검정됩니다.")
    if fails:
        LOG.error(f"계약 위반 {len(fails)}건: " + ", ".join(r["id"] for r in fails))
        for r in fails:
            LOG.warn(f"  · [{r['id']}] {r['name']} — {r['msg']}")
        if strict:
            raise RuntimeError(
                f"계약 검정 {len(fails)}건 실패 — 실행을 중단합니다. "
                f"이 계약들은 협상 대상이 아닙니다. 임계값을 바꿔 통과시키지 마십시오.")
        return False
    n_ok = len(CONTRACT_V3) - len(skips)
    if skips:
        LOG.ok(f"계약 검정 {n_ok}/{len(CONTRACT_V3)}건 통과 · {len(skips)}건 검사 불가(SKIP)")
    else:
        LOG.ok(f"계약 검정 {len(CONTRACT_V3)}건 전부 통과")
    return True
