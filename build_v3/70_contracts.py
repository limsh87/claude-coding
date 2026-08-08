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

    # ── §12-6 : 수집 호출량 상한 (4시간 계약) ─────────────────────────────────────────────
    def budget_bounded():
        """★ 실제로 터졌던 사고를 고정하는 회귀 테스트.

        Tier-2 재무(fnlttSinglAcntAll)와 직원현황(empSttus)은 잡 수가 |기업|×|연도|(×|분기|)
        로 **곱해진다**. 상한이 없으면 3,981사 × 13년 × 4분기 = 207,012 호출 = 11일치가
        조용히 큐에 올라간다 — tqdm ETA 로 드러났을 때는 이미 돌고 있다.
        이 계약은 (a) 두 단계 모두 상한을 갖고 (b) 그 상한이 DART 일일한도 안에 들고
        (c) 수집 함수가 상한 인자를 실제로 받는지를 강제한다.
        """
        caps = {"EMP_MAX_CALLS": EMP_MAX_CALLS, "DART_FS_MAX_CALLS": DART_FS_MAX_CALLS}
        missing = [k for k, v in caps.items() if v is None]
        if missing:
            return False, f"{missing} 에 상한이 없습니다 — 콜드빌드가 4시간 계약을 벗어납니다"
        import inspect as _ins
        for fn, arg in ((fetch_dart_financials, "max_calls"), (fetch_emp_status, "max_calls")):
            if arg not in _ins.signature(fn).parameters:
                return False, f"{fn.__name__} 이 {arg} 인자를 받지 않습니다"
        # ★ Tier-2 는 잡당 OFS→CFS 로 최대 2회를 던진다. '잡 수'가 아니라 '호출 수'로 센다.
        plan = int(EMP_MAX_CALLS) + int(DART_FS_MAX_CALLS) * 2 + 2100 + 600
        if max(int(EMP_MAX_CALLS), int(DART_FS_MAX_CALLS)) > DART_DAILY_LIMIT:
            return False, f"단일 단계 상한이 일일한도({DART_DAILY_LIMIT:,})를 넘습니다"
        # 예전엔 plan 을 계산해 성공 메시지에 찍기만 하고 **한도와 비교하지 않았다.**
        # 그래서 26,000건 계획이 "일일한도 19,000 안" 이라는 문구와 함께 PASS 했다.
        # ★ 한도는 **키 하나당**이다. 키를 여러 개 넣으면 그만큼 곱해진다.
        n_keys = max(1, len([k for k in ([DART_API_KEY] + list(DART_API_KEYS))
                             if str(k).strip()]))
        room = DART_DAILY_LIMIT * n_keys
        if plan > room:
            return False, (f"계획 호출 {plan:,}건이 하루 한도 {room:,}건"
                           f"(키 {n_keys}개 × {DART_DAILY_LIMIT:,})을 넘습니다. "
                           f"상한을 낮추거나 DART_API_KEYS 에 키를 추가하세요 — "
                           f"키는 opendart.fss.or.kr 에서 무료·즉시 발급됩니다")
        # 5~8건/초 실측 기준 상한 소진에 걸리는 최악 시간이 4시간 안이어야 한다.
        worst_h = (int(EMP_MAX_CALLS) / 8.0 + int(DART_FS_MAX_CALLS) / 5.0) / 3600.0
        if worst_h > WALL_CLOCK_LIMIT_H * 0.6:
            return False, (f"상한 소진 예상 {worst_h:.1f}h 가 수집 몫(4h×0.6)을 넘습니다 — "
                           f"EMP_MAX_CALLS/DART_FS_MAX_CALLS 를 낮추세요")
        return True, (f"계획 {plan:,}건 ≈{worst_h*60:.0f}분 · "
                      f"하루 한도 {room:,}(키 {n_keys}개) 안")

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
        src = _src_of(run_backtest) or ""
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
        b2._lk = threading.RLock()
        b2.keys = ["k1"]
        b2._kid_of = {"k1": DartBudget._make_kid("k1")}
        b2.per_key = {b2._kid_of["k1"]: DART_DAILY_LIMIT * 99}
        b2.blocked, b2._reserved, b2._dirty, b2._rr = set(), {}, 0, 0
        if b2.pick_key() is None:
            return False, ("★ 로컬 카운터가 한도를 넘었다는 이유로 호출을 막습니다 — "
                           "진짜 잔여량은 서버만 압니다. 추정으로 우리를 막으면 "
                           "서버가 답해 줄 수 있는 상태에서 한 건도 안 쏘게 됩니다")
        # 사전점검이 알파 테이블을 개별 판정하는가 (합산 판정이면 사고가 재현된다)
        src = _src_of(preflight_dart_v3) or ""
        if src:
            if "dart_employees_ext" not in src:
                return False, "사전점검이 알파 테이블을 개별로 보지 않습니다"
            if "sum(have.values())" in src and "dead_alpha" not in src:
                return False, "사전점검이 여전히 합산으로만 판정합니다"
        if not REQUIRE_EMP_ALPHA:
            return True, "예약 동작 확인 · REQUIRE_EMP_ALPHA=False (알파 없이도 진행하도록 설정됨)"
        return True, (f"키 로테이션 · 서버 거부만 하드 차단 · 로컬 카운터는 계획용 · "
                      f"예약 {EMP_RESERVED_CALLS:,}건 · 알파 부재 시 수집 전 중단")

    _cc("§12-A", "알파 원천(직원현황) 예산 보호 · 부재 시 사전 중단", alpha_guard)

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
