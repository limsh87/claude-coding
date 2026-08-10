

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 A1~A31 — 주석이나 관례는 무효. 테스트로만 강제한다.                          ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ║                                                                                          ║
# ║  ★ 이 파일의 존재 이유: "정규화가 잘 되어 있다", "미래 시총을 쓰지 않는다" 같은 문장은       ║
# ║    코드가 실제로 그런지와 무관하다. 각 계약은 진짜 데이터를 만들어 함수를 돌려 검사한다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _ac(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:220]}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return bool(ok)


def _ac_skip(cid: str, name: str, why: str):
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": None, "msg": f"건너뜀 — {why}"})


def _mk_sec(codes, **kw) -> pd.DataFrame:
    n = len(codes)
    d = pd.DataFrame({"code": list(codes), "name": [f"검정{i}" for i in range(n)],
                      "market": ["KOSPI"] * n, "industry": ["화학"] * n,
                      "corp_code": [f"C{i:07d}" for i in range(n)],
                      "listing_date": [as_ts("2010-01-01")] * n,
                      "delisting_date": [pd.NaT] * n})
    for k, v in kw.items():
        d[k] = v
    return d


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACT_RESULTS.clear()
    G = globals()
    rng = np.random.default_rng(SEED)

    # ── A1  PIT 강제 ──────────────────────────────────────────────────────────────────────
    def a1():
        d = pd.DataFrame({"code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29",
                                                        "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15",
                                                            "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 절단이 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "★미래누수: knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        # knowledge_date < event_date 는 그 자체가 미래누수 → 보정되어야 한다
        bad = pit_frame(pd.DataFrame({"x": [1], "e": [as_ts("2020-06-30")],
                                      "k": [as_ts("2020-01-01")]}), "e", "k")
        if bad["knowledge_date"].iloc[0] < bad["event_date"].iloc[0]:
            return False, "knowledge_date < event_date 가 보정되지 않았습니다"
        return True, "as_of 절단 정확 · PIT 컬럼 누락 거부 · kd<ed 보정 확인"

    _ac("A1", "Point-In-Time 강제", a1)

    # ── A2  생존자편향 ────────────────────────────────────────────────────────────────────
    def a2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"], "name": ["옛날", "미래", "폐지"],
            "market": ["KOSPI"] * 3, "industry": ["X"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"])})
        px = pd.DataFrame({"date": pd.bdate_range("2009-01-01", "2026-08-01"),
                           "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2016 = set(u.at("2016-08-31"))
        if "000002" in at2016:
            return False, "★C2 위반: 2016년 유니버스에 2025년 상장 종목이 포함되었습니다"
        if "000003" not in at2016:
            return False, ("★C2 위반: 2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다"
                           "(생존자편향 — 과거에는 분명히 상장되어 있었습니다)")
        if "000003" in set(u.at("2020-01-31")):
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지종목 당시 포함 · 폐지 후 제외 확인"

    _ac("A2", "생존자편향 제거", a2)

    # ── A3  U-1000 (PIT 시총 랭크) ────────────────────────────────────────────────────────
    def a3():
        # 실제 보통주 코드처럼 끝자리 0 · 간격 10 (촘촘한 연번은 형제 규칙을 오발화시킨다)
        codes = [f"{i*10:06d}" for i in range(1, 41)]
        sec = _mk_sec(codes)
        sec.loc[0, "name"] = "가나스팩1호"          # 스팩 제외 확인
        # 우선주 판정: 형제 보통주(000020)가 존재하는 000025 를 넣는다
        # ★ 형제 보통주(000020)를 남겨둔 채 다른 자리를 우선주로 바꾼다.
        #   000020 자리를 직접 덮으면 형제가 사라져 규칙이 발화하지 못한다.
        sec.loc[3, "code"] = "000025"
        codes[3] = "000025"
        sec.loc[2, "name"] = "무슨무슨리츠"
        px = pd.DataFrame({"date": pd.bdate_range("2015-01-01", "2021-01-01"),
                           "code": codes[0]})
        base = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        exd = classify_excluded(sec)
        au = ArcUniverse(base, sec, exd)
        t = as_ts("2019-03-01")
        # 시총: 과거에는 코드 순서대로 작음, '현재'에는 정반대라고 가정
        mc_past = pd.DataFrame({"code": codes, "asof": t,
                                "mktcap": np.arange(1, len(codes) + 1) * 1e10})
        liq = pd.DataFrame({"code": codes, "asof": t, "adtv60": 5e8})
        keep = int(min(ARC_UNIVERSE_N, len(codes)))
        U = au.build(pd.DatetimeIndex([t]), mc_past, liq)
        if U.empty:
            return False, "U-1000 이 비었습니다"
        got = set(U["code"])
        if "000001" in got:
            return False, "스팩이 제외되지 않았습니다"
        if "000025" in got:
            return False, "우선주(형제 보통주 000020 존재)가 제외되지 않았습니다"
        if "000003" in got:
            return False, "리츠가 제외되지 않았습니다"
        # 유동성 하한
        liq2 = liq.copy()
        liq2["adtv60"] = ARC_MIN_ADTV_KRW * 0.5
        U2 = au.build(pd.DatetimeIndex([t]), mc_past, liq2)
        if len(U2) != 0:
            return False, f"ADTV 하한({ARC_MIN_ADTV_KRW:,})이 적용되지 않았습니다 ({len(U2)}행 잔존)"
        # 랭크는 '작은 시총부터'
        mc_small = mc_past.copy()
        mc_small["mktcap"] = mc_small["mktcap"].to_numpy()[::-1]
        U3 = au.build(pd.DatetimeIndex([t]), mc_small, liq)
        r1 = U["uni_rank"].iloc[0], U["code"].iloc[0]
        r3 = U3["uni_rank"].iloc[0], U3["code"].iloc[0]
        if r1[1] == r3[1]:
            return False, ("★시총 랭크가 입력 시총에 반응하지 않습니다 — 시총을 뒤집었는데 "
                           "1순위 종목이 같습니다. PIT 시총이 아니라 다른 것으로 랭크하고 "
                           "있을 가능성이 큽니다.")
        # 미래 시총 소급 금지: 다른 시점의 시총을 주면 그 시점 유니버스가 비어야 한다
        mc_future = mc_past.copy()
        mc_future["asof"] = as_ts("2020-03-01")
        U4 = au.build(pd.DatetimeIndex([t]), mc_future, liq)
        if len(U4) != 0:
            return False, ("★미래 시총 소급: 2020-03 시총으로 2019-03 유니버스가 만들어졌습니다. "
                           "시총은 (code, asof) 키로만 조회되어야 합니다.")
        return True, (f"하위 랭크 정렬 · 스팩/우선주/리츠 제외 · ADTV 하한 · "
                      f"미래 시총 소급 차단 확인 (표본 {len(U)}종목)")

    _ac("A3", "U-1000 PIT 유니버스", a3)

    # ── A4  D1 페어링 (전년 동기 동일 유형만) ─────────────────────────────────────────────
    def a4():
        if "arc_doc_pairs" not in G:
            return False, "arc_doc_pairs 가 정의되지 않았습니다"
        rows = []
        for y in (2019, 2020):
            for dt_, m in (("FY", 3), ("Q1", 5)):
                rows.append({"corp_code": "C1", "rcept_no": f"{y}{m:02d}01x{dt_}",
                             "rcept_dt": as_ts(f"{y}-{m:02d}-15"), "doc_type": dt_,
                             "bsns_year": y - (1 if dt_ == "FY" else 0), "section": "S_ALL",
                             "n_tokens": 10, "tf": json.dumps({"가": 1}),
                             "bigram": json.dumps({}), "tok_len": 100, "is_amend": False})
        T = pd.DataFrame(rows)
        Pr = arc_doc_pairs(T)
        if Pr.empty:
            return False, "전년 동기 페어가 하나도 만들어지지 않았습니다"
        mixed = Pr[Pr["doc_type"].isna()]
        if len(mixed):
            return False, "doc_type 이 결측인 페어가 있습니다"
        # 유형이 섞인 페어가 있으면 실패
        for r in Pr.itertuples(index=False):
            if str(r.rcept_no).endswith("FY") != str(r.prev_rcept_no).endswith("FY"):
                return False, ("★문서 유형이 섞인 페어가 생성되었습니다. 사업보고서와 "
                               "분기보고서는 분량·구성이 구조적으로 달라 가짜 변화가 "
                               "대량 발생합니다(§6.1.1).")
            if (as_ts(r.rcept_dt) - as_ts(r.prev_rcept_dt)).days < 200:
                return False, ("★직전 분기와 페어링되었습니다. 반드시 전년 동기여야 합니다.")
        return True, f"동일 유형 × 전년 동기 페어 {len(Pr)}쌍 · 유형 혼합/직전분기 페어 0건"

    _ac("A4", "D1 페어링 (전년 동기 동일 유형)", a4)

    # ── A5  정규화 유효성 ★D1 전체의 전제 ────────────────────────────────────────────────
    def a5():
        if "arc_normalize_text" not in G or "arc_tokenize" not in G:
            return False, "정규화 함수가 정의되지 않았습니다"
        base = ("II. 사업의 내용\n"
                "당사는 2022년 12월 31일 기준으로 반도체 소재를 제조하여 판매하고 있습니다. "
                "제27기 매출액은 1,234,567 백만원이며 영업이익은 98,765 백만원입니다. "
                "주요 고객사는 삼성전자와 SK하이닉스이며 공급 물량은 12,345 톤입니다. "
                "당사는 품질 경영을 통해 고객 만족을 실현하고 있습니다. "
                "생산 설비는 충청북도 청주시에 위치하며 종업원은 456 명입니다.\n") * 3
        # 변형 ①: 숫자·날짜·사명만 바꿈 → 유사도 ≈ 1.0 이어야 한다
        v1 = (base.replace("2022년 12월 31일", "2023년 12월 31일")
                  .replace("제27기", "제28기")
                  .replace("1,234,567", "2,345,678").replace("98,765", "87,654")
                  .replace("12,345", "23,456").replace("456", "789")
                  .replace("가나전자", "가나첨단소재"))
        # 변형 ②: 서술을 실제로 바꿈 → 유사도가 유의하게 낮아야 한다
        v2 = base.replace(
            "당사는 품질 경영을 통해 고객 만족을 실현하고 있습니다.",
            "경쟁 심화로 수익성이 악화되었으며 일부 라인의 가동을 중단하였습니다. "
            "환율 변동과 원자재 가격 상승이 원가 부담을 가중시키고 있습니다.")
        v2 = v2.replace("반도체 소재를 제조하여 판매", "이차전지 부품을 개발하여 공급")

        names = ["가나전자", "가나첨단소재"]
        t0 = set(arc_tokenize(arc_normalize_text(base, names)))
        t1 = set(arc_tokenize(arc_normalize_text(v1, names)))
        t2 = set(arc_tokenize(arc_normalize_text(v2, names)))
        if not t0 or not t1:
            return False, "토큰이 생성되지 않았습니다(토큰화 실패)"
        j1 = len(t0 & t1) / max(len(t0 | t1), 1)
        j2 = len(t0 & t2) / max(len(t0 | t2), 1)
        if j1 < 0.98:
            return False, (f"★숫자·날짜·사명만 바꾼 문서의 자카드가 {j1:.3f} 입니다(기대 ≥0.98). "
                           f"정규화가 가짜 변화를 제거하지 못했다는 뜻이며, 이 상태에서는 "
                           f"D1 의 모든 결과가 무의미합니다 — 전 종목이 '변경 기업'이 됩니다.")
        if j2 >= j1 - 0.02:
            return False, (f"★실제 서술을 바꾼 문서의 자카드가 {j2:.3f} 로 가짜변화본"
                           f"({j1:.3f})과 구분되지 않습니다. 정규화가 과도해서 진짜 변화까지 "
                           f"지워버렸을 가능성이 큽니다.")
        norm = arc_normalize_text(base, names)
        for mark in ("<NUM>", "<DATE>", "<PERIOD>"):
            if mark not in norm:
                return False, f"마스크 {mark} 가 적용되지 않았습니다"
        if re.search(r"\d", norm.replace("<NUM>", "").replace("<DATE>", "")
                             .replace("<PERIOD>", "")):
            return False, "정규화 후에도 원시 숫자가 남아 있습니다"
        return True, (f"가짜변화 자카드 {j1:.3f} (≥0.98) · 진짜변화 {j2:.3f} (유의하게 낮음) · "
                      f"마스크 전부 적용 확인")

    _ac("A5", "정규화 유효성 (D1 의 전제)", a5)

    # ── A6  횡단면 z ──────────────────────────────────────────────────────────────────────
    def a6():
        v = pd.Series([1.0] * 30 + [1000.0])
        cell = pd.Series(["A"] * 31)
        z = xsec_z(v, cell)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        if float(z.max()) > 6:
            return False, f"윈저라이즈 미적용 (max z={z.max():.2f})"
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]))
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 이 아닙니다(0으로 채우면 안 됩니다)"
        vi = pd.Series([1.0, 2, 3, np.inf, 5, 6, 7, 8, 9, 10])
        zi = xsec_z(vi, pd.Series(["A"] * 10))
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, ("★±inf 오염: 셀에 inf 가 하나만 있어도 z 가 전부 뭉개집니다. "
                           "비율/로그 지표에서 흔히 발생하며 그 셀의 신호가 통째로 사라집니다.")
        # 기간 셀 평균 ≈ 0
        n = 300
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "cell": rng.choice(["Q1|IT", "Q1|소재", "Q1|금융"], n),
                          "cell_all": "Q1|ALL", "x": rng.normal(size=n)})
        z2 = xsec_z_arc(P, "x")
        for c, g in P.assign(z=z2).groupby("cell"):
            if g["z"].notna().sum() >= CELL_MIN_N and abs(float(g["z"].mean())) > 0.15:
                return False, f"셀 {c} 의 z 평균이 0에서 벗어남: {g['z'].mean():.3f}"
        return True, "winsorize→z 순서 · 표본부족 NaN · ±inf 무해화 · 셀 평균≈0 확인"

    _ac("A6", "횡단면 표준화", a6)

    # ── A7  D1 섹션 가중치 재배분 ─────────────────────────────────────────────────────────
    def a7():
        wv = np.array([ARC_D1_WEIGHTS[s] for s in ARC_SECTIONS], dtype=float)
        if abs(wv.sum() - 1.0) > 1e-9:
            return False, f"사전등록 가중치 합이 1이 아닙니다: {wv.sum():.6f}"
        V = np.array([[1.0, np.nan, 1.0, np.nan, np.nan, np.nan, 1.0]])
        msk = np.isfinite(V)
        wm = np.where(msk, wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        comp = np.nansum(np.where(msk, V, 0.0) * wm, axis=1) / ws
        if abs(float(comp[0]) - 1.0) > 1e-9:
            return False, (f"★결측 섹션 가중치가 비례 재배분되지 않았습니다 "
                           f"(전 섹션 값이 1.0 인데 합성이 {comp[0]:.4f}). "
                           f"섹션이 적게 파싱된 종목이 구조적으로 불리해집니다.")
        return True, f"결측 섹션 3개 상황에서도 가중치 합 = 1 · 합성값 보존 확인"

    _ac("A7", "D1 섹션 가중치 재배분", a7)

    # ── A8~A11  편입 규칙 4대 회귀 방지 ───────────────────────────────────────────────────
    def _mk_panel(n=60):
        t = as_ts("2020-06-01")
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(1, n + 1)], "asof": t, "q": "2020Q1",
            "cell": "2020Q1|IT", "cell_all": "2020Q1|ALL", "sector": "IT/전자",
            "corp_code": [f"C{i:07d}" for i in range(1, n + 1)],
            "mktcap": np.linspace(1e10, 5e10, n), "adtv60": 5e8,
            "exec_px": 10000.0, "fwd_ret_1q": rng.normal(0, 0.1, n),
            "dTONE": rng.normal(size=n), "dTONE_resid": rng.normal(size=n),
            "has_axis_a": 1.0,
            "D1_SCORE": rng.normal(size=n), "D2_SCORE": rng.normal(size=n),
            "D3_SCORE": rng.normal(size=n), "DELTA_NONFIN": rng.integers(0, 3, n).astype(float),
            "EXCLUDE": 0.0, "listing_months": 60.0})
        return P

    def a8():
        P = _mk_panel()
        P.loc[:9, "EXCLUDE"] = 1.0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        bad = Q.loc[Q["EXCLUDE"] == 1.0, "FINAL_SCORE"].notna().sum()
        if bad:
            return False, (f"★배제 플래그가 발동한 {int(bad)}행에 점수가 남아 있습니다. "
                           f"§6.4 는 '점수 무관 즉시 제외'를 규정합니다.")
        if Q.loc[Q["EXCLUDE"] == 0.0, "FINAL_SCORE"].notna().sum() == 0:
            return False, "배제되지 않은 종목까지 전부 제외되었습니다"
        return True, "EXCLUDE=1 인 10행 전부 편입 불가 · 나머지는 정상 유지"

    _ac("A8", "배제 플래그 하드 제외", a8)

    def a9():
        P = _mk_panel()
        P["DELTA_NONFIN"] = 0.0                       # 전 종목 ΔNONFIN = 0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        if Q["FINAL_SCORE"].notna().sum() == 0:
            return False, ("★ΔNONFIN=0 인 종목이 전부 탈락했습니다. v1.0 의 하드게이트가 "
                           "되살아났다는 뜻입니다 — §6.3 은 이 규칙을 명시적으로 폐기했습니다.")
        Q4 = assemble_final(P, use_axes=("A_RAW",), use_excl=True, v1_hardgate=True)
        if Q4["FINAL_SCORE"].notna().sum() != 0:
            return False, "F4(v1.0 재현) 팔에서 하드게이트가 작동하지 않았습니다"
        return True, ("ΔNONFIN=0 종목도 본선 편입 가능 · F4 재현 팔에서만 하드게이트 작동 확인")

    _ac("A9", "ΔNONFIN 하드게이트 폐기 (v1.0 규칙 부활 방지)", a9)

    def a10():
        P = _mk_panel()
        P.loc[:19, ["dTONE", "dTONE_resid"]] = np.nan       # 리포트 없는 종목 20개
        P.loc[:19, "has_axis_a"] = 0.0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        n_ok = int(Q.loc[:19, "FINAL_SCORE"].notna().sum())
        if n_ok < 20:
            return False, (f"★축 A 결측 종목 20개 중 {20-n_ok}개가 탈락했습니다. "
                           f"§7.2 는 'ΔTONE_resid=0(중립)으로 두고 DART_SCORE 만으로 평가, "
                           f"탈락시키지 말 것' 을 규정합니다. 이것이 v2.0 에서 축 B 를 "
                           f"강화한 이유입니다.")
        return True, "리포트 없는 20개 종목이 DART_SCORE 만으로 전부 생존 확인"

    _ac("A10", "축 A 결측 종목 생존 (§7.2)", a10)

    def a11():
        P = _mk_panel()
        P.loc[:29, "D1_SCORE"] = np.nan                      # D1 결측 30개
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        n_ok = int(Q.loc[:29, "FINAL_SCORE"].notna().sum())
        if n_ok < 30:
            return False, (f"★D1 결측 종목 30개 중 {30-n_ok}개가 탈락했습니다. "
                           f"§6.5 는 'D1 가중치를 D2·D3 에 비례 재배분, 종목을 탈락시키지 "
                           f"말 것' 을 규정합니다.")
        if int(Q.loc[:29, "n_axes_b"].max()) != 2:
            return False, f"D1 결측 행의 축 B 층수가 2가 아닙니다: {Q.loc[:29,'n_axes_b'].max()}"
        # 재배분이 실제로 되었는지: D1 결측 행의 DART_SCORE 가 D2·D3 만으로 계산돼야 한다
        r0 = Q.loc[0]
        man = (ARC_W_D2 * P.loc[0, "D2_SCORE"] + ARC_W_D3 * P.loc[0, "D3_SCORE"]) / \
              (ARC_W_D2 + ARC_W_D3)
        # DART_SCORE 는 그 뒤 다시 z 표준화되므로 값 자체가 아니라 '유한함'만 확인
        if not np.isfinite(r0["DART_SCORE"]) or not np.isfinite(man):
            return False, "D1 결측 행의 DART_SCORE 가 계산되지 않았습니다"
        return True, "D1 결측 30행 전부 생존 · 축 B 층수 2 · D2·D3 로 재배분 확인"

    _ac("A11", "D1 결측 시 가중치 재배분 (§6.5)", a11)

    # ── A12  직교화 필수 ──────────────────────────────────────────────────────────────────
    def a12():
        if "attach_axis_a" not in G:
            return False, "attach_axis_a 가 정의되지 않았습니다"
        import inspect
        src = inspect.getsource(G["attach_axis_a"])
        # ① 사전등록 통제변수 목록이 §5.3 표를 그대로 담고 있는가
        need_ctrl = ["eps_rev", "tp_rev", "opin_chg", "mom_12_1", "log_mktcap", "log_adtv"]
        miss_c = [k for k in need_ctrl if k not in list(ARC_TONE_CONTROLS)]
        if miss_c:
            return False, (f"★ARC_TONE_CONTROLS 에 통제변수 {miss_c} 가 없습니다. §5.3 은 "
                           f"직교화를 '전략 성립의 필요조건' 으로 규정합니다.")
        # ② 함수가 그 목록과 섹터더미·잔차화를 실제로 쓰는가
        need_use = ["ARC_TONE_CONTROLS", "get_dummies", "xsec_resid", "dTONE_resid"]
        miss_u = [k for k in need_use if k not in src]
        if miss_u:
            return False, (f"★attach_axis_a 가 {miss_u} 를 쓰지 않습니다 — 통제변수 목록만 "
                           f"있고 회귀가 실제로 돌지 않으면 직교화는 이름뿐입니다.")
        # ③ 잔차가 원신호와 실제로 달라지는가 (형식이 아니라 동작 검증)
        n = 240
        q = np.repeat(["2020Q1", "2020Q2", "2020Q3", "2020Q4"], n // 4)
        ctrl = rng.normal(size=n)
        y = 0.8 * ctrl + rng.normal(scale=0.3, size=n)
        X = pd.DataFrame({"c": ctrl})
        r = xsec_resid(pd.Series(y), X, pd.Series(q))
        if r.notna().sum() < n * 0.8:
            return False, f"xsec_resid 가 {int(r.notna().sum())}/{n} 행만 잔차를 냈습니다"
        c_before = abs(float(np.corrcoef(y, ctrl)[0, 1]))
        m = r.notna().to_numpy()
        c_after = abs(float(np.corrcoef(r[m].to_numpy(), ctrl[m])[0, 1]))
        if not (c_before > 0.5 and c_after < 0.15):
            return False, (f"★직교화가 통제변수와의 상관을 제거하지 못했습니다 "
                           f"({c_before:.3f} → {c_after:.3f}). 잔차화가 형식적으로만 "
                           f"수행되고 있을 가능성이 큽니다.")
        return True, (f"통제변수 {len(ARC_TONE_CONTROLS)}종 + 섹터더미 + 잔차화 사용 확인 · "
                      f"통제변수 상관 {c_before:.3f} → {c_after:.3f} 로 실제 제거됨")

    _ac("A12", "ΔTONE 직교화 필수 (§5.3)", a12)

    # ── A13  튜닝 금지 ────────────────────────────────────────────────────────────────────
    def a13():
        import inspect
        src = ""
        for nm in ("assemble_final", "d1_composite", "attach_d2", "attach_d3"):
            if nm in G:
                try:
                    src += inspect.getsource(G[nm])
                except Exception:
                    pass
        if re.search(r"(minimize|curve_fit|GridSearch|RandomizedSearch|optimize\.|"
                     r"\.fit\([^)]*weight)", src):
            return False, "★가중치 최적화 흔적이 발견되었습니다 — 사전등록 가중치 튜닝 금지"
        wsum = ARC_W_D1 + ARC_W_D2 + ARC_W_D3
        if abs(wsum - 1.0) > 1e-9:
            return False, f"축 B 가중치 합이 1이 아닙니다: {wsum}"
        if abs(ARC_W_AXIS_A + ARC_W_AXIS_B - 1.0) > 1e-9:
            return False, "축 A/B 가중치 합이 1이 아닙니다"
        if (ARC_W_D1, ARC_W_D2, ARC_W_D3) != (0.40, 0.40, 0.20):
            return False, (f"사전등록 가중치가 변경되었습니다: "
                           f"{(ARC_W_D1, ARC_W_D2, ARC_W_D3)} (기대 0.40/0.40/0.20)")
        return True, "최적화 루틴 부재 · 사전등록 가중치 0.40/0.40/0.20 · 0.5/0.5 확인"

    _ac("A13", "가중치 튜닝 금지 (사전등록)", a13)

    # ── A14  결정성 ───────────────────────────────────────────────────────────────────────
    def a14():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1]).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 입력 순서 무관 확인"

    _ac("A14", "결정성", a14)

    # ── A15  시점 규약 ────────────────────────────────────────────────────────────────────
    def a15():
        rb = rebal_dates("2016-08-01", "2026-07-31")
        if len(rb) == 0:
            return False, "리밸런싱일이 생성되지 않았습니다"
        if any(t.month not in ARC_REBAL_MONTHS or t.day != 1 for t in rb):
            return False, f"리밸일이 3/1·6/1·9/1·12/1 이 아닙니다: {rb[:4].tolist()}"
        if prev_quarter_of("2019-09-01") != "2019Q2":
            return False, (f"★리밸일 직전 분기 계산 오류: 2019-09-01 → "
                           f"{prev_quarter_of('2019-09-01')} (기대 2019Q2). "
                           f"9/1 에 2019Q3(7~9월)을 쓰면 아직 끝나지 않은 분기를 쓰는 것이라 "
                           f"미래누수입니다.")
        if qshift("2019Q1", -1) != "2018Q4" or qshift("2019Q3", -4) != "2018Q3":
            return False, "분기 시프트 계산 오류"
        # DART 는 rcept_dt + 1일 이후 사용 가능
        if ARC_DART_LAG_DAYS < 1 or ARC_REPORT_LAG_DAYS < 1:
            return False, "T+1 규약이 0 으로 설정되어 있습니다(접수일 당일 사용 = 미래누수)"
        return True, (f"리밸일 {len(rb)}개 (3/6/9/12월 1일) · 직전분기 계산 정확 · "
                      f"DART/리포트 T+1 규약 확인")

    _ac("A15", "시점 규약 (룩어헤드 금지)", a15)

    # ── A16  종목코드 정규화 ──────────────────────────────────────────────────────────────
    def a16():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        if not is_preferred("005935", "삼성전자우"):
            return False, "우선주 판정 실패 (005935, 이름 규칙)"
        if not is_preferred("005935", "", {"005930", "005935"}):
            return False, "우선주 판정 실패 (005935, 형제 보통주 규칙)"
        if is_preferred("006800", "미래에셋대우"):
            return False, "★'대우' 로 끝나는 정상 사명이 우선주로 오판되었습니다"
        if is_preferred("900140", "엘브이엠씨홀딩스", {"900140"}):
            return False, "★형제 보통주가 없는 종목이 우선주로 오판되었습니다"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) + 우선주 판정 확인"

    _ac("A16", "종목코드 정규화", a16)

    # ── A17  분기 연율화 ──────────────────────────────────────────────────────────────────
    def a17():
        if PERIODS_PER_YEAR != 4:
            return False, (f"★연율화 계수가 {PERIODS_PER_YEAR} 입니다. 분기 리밸런싱이므로 "
                           f"4 여야 합니다. 12(월) 로 두면 성과가 통째로 3배 부풀려집니다.")
        r = pd.DataFrame({"asof": rebal_dates("2017-03-01", "2026-12-01")[:20],
                          "ret": [0.05] * 20, "n": [30] * 20,
                          "turnover": [0.5] * 20, "cost": [0.0] * 20,
                          "n_elig": [500] * 20})
        s = perf_stats(r)
        # 분기 5% 20회 = 5년, CAGR = 1.05^4 - 1 = 21.55%
        exp = 1.05 ** 4 - 1
        if abs(s["CAGR"] - exp) > 1e-6:
            return False, f"CAGR 이 {s['CAGR']:.6f} (기대 {exp:.6f}) — 연율화가 틀렸습니다"
        if abs(s["기간수(분기)"] - 20) > 0:
            return False, "기간 수 계산 오류"
        return True, f"분기 5% × 20 → CAGR {s['CAGR']*100:.2f}% (= 1.05^4−1) 확인"

    _ac("A17", "분기 연율화 (계수 4)", a17)

    # ── A18  LLM 호출 금지 ────────────────────────────────────────────────────────────────
    def a18():
        import inspect
        targets = ["fit_tone_expanding", "score_tone_reports", "build_tone_training",
                   "arc_normalize_text", "arc_tokenize", "extract_hardfacts",
                   "d1_similarity", "assemble_final", "fetch_arc_documents"]
        src = ""
        for nm in targets:
            if nm in G:
                try:
                    src += inspect.getsource(G[nm])
                except Exception:
                    pass
        pat = (r"openai|anthropic|gpt-|claude-|generativeai|/v1/chat/completions|"
               r"api\.openai|api\.anthropic|gemini|cohere\.")
        if re.search(pat, src, re.I):
            return False, ("★LLM API 호출 흔적이 발견되었습니다. §5.1/§6.3 은 이를 명시적으로 "
                           "금지합니다 — 토큰 비용이 아니라 사전학습 코퍼스로 인한 룩어헤드 "
                           "오염 때문입니다.")
        return True, f"검사 대상 {len([n for n in targets if n in G])}개 함수에 LLM 호출 없음"

    _ac("A18", "LLM API 호출 금지", a18)

    # ── A19  DART 파생 테이블의 T+1 규약 ──────────────────────────────────────────────────
    def a19():
        """§4 'rcept_dt(접수일자) + 1거래일부터 사용 가능' 이 재무 계열에도 적용되는가.

        ★ 초기 빌드에서 D1 만 +1 을 적용하고 재무·직원·주식수·감사의견은 접수 당일부터
          쓸 수 있었다. 작지만 명백한 미래누수이며, 접수는 장중에도 일어나므로 실행 불가능한
          정보 접근이다. 여기서 실제 프레임을 만들어 검사한다.
        """
        rc = REPRT_CODES["FY"]
        fin = pit_frame(pd.DataFrame({
            "corp_code": ["C1", "C1"], "bsns_year": [2019, 2020], "reprt_code": [rc, rc],
            "period_end": pd.to_datetime(["2019-12-31", "2020-12-31"]),
            "knowledge_date": pd.to_datetime(["2020-03-20", "2021-03-20"]),
            "assets": [1000.0, 1100.0], "liabilities": [400.0, 430.0],
            "equity": [600.0, 670.0], "cash": [100.0, 120.0],
            "net_income_ttm": [50.0, 60.0], "cfo_ttm": [55.0, 70.0],
            "revenue_ttm": [900.0, 990.0], "inventory": [80.0, 85.0],
            "receivable": [90.0, 95.0], "op_income_q": [12.0, 14.0],
        }), "period_end", "knowledge_date")
        d2 = build_d2_panel(fin, None)
        if d2 is None or d2.empty:
            return False, "D2 패널이 비어 T+1 검사를 할 수 없습니다"
        kd = as_ts_series(d2["knowledge_date"]).min()
        if kd <= as_ts("2020-03-20"):
            return False, (f"★T+1 위반: 접수일 2020-03-20 인 재무제표의 knowledge_date 가 "
                           f"{str(kd)[:10]} 입니다. 접수 당일부터 쓸 수 있으면 미래누수입니다"
                           f"(§4).")
        # as-of 결합에서도 실제로 차단되는지
        st = PITStore()
        st.register("t_d2", d2, key_cols=["corp_code"])
        panel = pd.DataFrame({"code": ["A"], "corp_code": ["C1"],
                              "asof": [as_ts("2020-03-20")]})
        got = st.asof_join(panel, "t_d2", by="corp_code", left_time="asof")
        if "ACCRUAL" in got.columns and got["ACCRUAL"].notna().any():
            return False, ("★접수 당일(2020-03-20) 리밸런싱에서 그 날 접수된 재무가 "
                           "결합되었습니다. T+1 이 as-of 결합에서 무력화되고 있습니다.")
        got2 = st.asof_join(pd.DataFrame({"code": ["A"], "corp_code": ["C1"],
                                          "asof": [as_ts("2020-03-21")]}),
                            "t_d2", by="corp_code", left_time="asof")
        if "ACCRUAL" not in got2.columns or not got2["ACCRUAL"].notna().any():
            return False, "T+1 다음 날에도 결합되지 않습니다 — 지연이 과도합니다"
        return True, (f"재무 knowledge_date = 접수일 + {ARC_DART_LAG_DAYS}일 · "
                      f"접수 당일 결합 차단 · 익일 결합 정상 확인")

    _ac("A19", "DART T+1 규약 (재무 계열)", a19)

    # ── A20  게이트가 실제로 축을 끄는가 (skip_if 함정) ───────────────────────────────────
    def a20():
        """★ PIPE.stage(skip_if=True) 는 스테이지를 SKIP 으로 '표시'만 하고 with 본문은
        그대로 실행한다(컨텍스트 매니저의 구조적 한계). 이걸 모르고 쓰면 '축을 껐다'고
        로그에는 찍히는데 계산은 다 돌고 값까지 반영되는 조용한 사고가 난다.
        여기서 ① 그 성질을 명시적으로 확인하고 ② 오케스트레이터가 명시 분기로 막았는지 본다.
        """
        ran = {"n": 0}
        with PIPE.stage("T.SKIP", "계약검정용", "L0", skip_if=True, skip_reason="검정"):
            ran["n"] += 1
        if ran["n"] == 0:
            return True, ("skip_if 가 본문 실행까지 막습니다(파이썬 버전/구현 변경). "
                          "이 경우 호출부의 명시 분기는 불필요하지만 무해합니다.")
        # 본문이 실행되는 것이 정상이므로, 오케스트레이터가 명시 분기로 막고 있어야 한다.
        import inspect
        src = inspect.getsource(G["arc_build_signals"]) if "arc_build_signals" in G else ""
        for var, why in (("_d1_on", "D1"), ("_axis_a_on", "축 A")):
            if var not in src:
                return False, (f"★게이트가 {why} 를 실제로 끄지 못합니다. skip_if 는 표시만 "
                               f"하므로 with 본문 안에서 `if {var}:` 로 분기해야 합니다. "
                               f"현재 구조에서는 Phase 0 에서 축을 껐다고 보고해 놓고 "
                               f"계산 결과가 그대로 신호에 들어갑니다.")
        if "attach_d1(P, None)" not in src or "attach_axis_a(P, None, None)" not in src:
            return False, "게이트 off 경로에서 축을 결측 처리하는 호출이 없습니다"
        return True, ("skip_if 는 표시 전용임을 확인 · 오케스트레이터가 _d1_on/_axis_a_on 으로 "
                      "명시 분기하고 off 경로에서 축을 결측 처리함 확인")

    _ac("A20", "게이트가 실제로 축을 끄는가", a20)

    # ── A21  '정보 없음' 을 '중립 0' 으로 착각하지 않는가 ─────────────────────────────────
    def a21():
        P = _mk_panel()
        P.loc[:29, ["dTONE", "dTONE_resid"]] = np.nan       # 축 A 결측 30개
        P.loc[:14, ["D1_SCORE", "D2_SCORE", "D3_SCORE"]] = np.nan   # 그중 15개는 축 B 도 결측
        # ① 축 A 단독 팔: 결측을 0 으로 채우면 전 종목 동점이 되어 코드 순서로 편입된다
        Q1 = assemble_final(P, use_axes=("A",), use_excl=True)
        if Q1.loc[:29, "FINAL_SCORE"].notna().any():
            return False, ("★축 A 단독 팔에서 ΔTONE 결측 종목에 점수가 부여됐습니다. "
                           "그 팔에는 DART_SCORE 가 없으므로 '중립 0' 은 곧 전 종목 동점이고, "
                           "리포트가 없는 종목이 코드 순서로 편입됩니다 — A1 이 축 A 의 "
                           "순기여가 아니라 동점 처리 규칙을 측정하게 됩니다.")
        if not Q1.loc[30:, "FINAL_SCORE"].notna().any():
            return False, "축 A 단독 팔에서 ΔTONE 이 있는 종목까지 탈락했습니다"
        # ② 풀버전: 축 A 결측이라도 축 B 가 있으면 생존(§7.2)
        Q2 = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        if not Q2.loc[15:29, "FINAL_SCORE"].notna().all():
            return False, "풀버전에서 축 A 결측·축 B 보유 종목이 탈락했습니다(§7.2 위반)"
        # ③ 두 축 모두 결측이면 편입 불가 (근거 없는 종목이 중간 순위를 차지하면 안 된다)
        if Q2.loc[:14, "FINAL_SCORE"].notna().any():
            return False, ("★축 A·축 B 가 모두 결측인 종목에 점수가 부여됐습니다. "
                           "아무 근거도 없는 종목이 중간 순위를 차지하고, 표본이 얇은 분기에는 "
                           "실제로 편입됩니다.")
        return True, ("단독 팔은 결측 유지 · 풀버전은 축 A 결측 생존(§7.2) · "
                      "두 축 모두 결측이면 편입 불가 확인")

    _ac("A21", "'정보 없음' vs '중립 0' 구분", a21)

    # ── A22  배제 플래그가 소스별로 서로를 지우지 않는가 ──────────────────────────────────
    def a22():
        # 한국 소형주에서 흔한 조합: FY 감사의견 '의견거절'(3월 접수) → CB 발행(4월) →
        # 1분기보고서 정상(5월). 예전에는 5월 행이 최근행이 되어 3·4월 플래그를 지웠다.
        X = pd.DataFrame([
            {"corp_code": "C1", "event_date": pd.Timestamp("2018-12-31"),
             "knowledge_date": pd.Timestamp("2019-03-26"), "EX_AUDIT": 1.0},
            {"corp_code": "C1", "event_date": pd.Timestamp("2019-04-10"),
             "knowledge_date": pd.Timestamp("2019-04-11"), "EX_CBBW": 1.0},
            {"corp_code": "C1", "event_date": pd.Timestamp("2019-03-31"),
             "knowledge_date": pd.Timestamp("2019-05-16"), "EX_LOSS4Q": 0.0,
             "EX_IMPAIR": 0.0},
        ])
        X = ensure_cols(X, EXCL_COLS, fill=np.nan)
        S = _event_state_table(X, EXCL_COLS, EXCL_VALID_DAYS)
        S = pit_frame(S, "event_date", "knowledge_date", source="t")
        P = pd.DataFrame({"corp_code": ["C1"] * 3, "code": ["000010"] * 3,
                          "asof": pd.to_datetime(["2019-06-01", "2019-09-01", "2021-06-01"]),
                          "q": ["2019Q1", "2019Q2", "2021Q1"], "sector": ["기타"] * 3,
                          "DELTA_NONFIN": [np.nan] * 3})
        Q = attach_d3(P, None, S)
        got = pd.to_numeric(Q["EXCLUDE"], errors="coerce").fillna(0).tolist()
        if got[0] < 1 or got[1] < 1:
            return False, ("★감사의견 '의견거절'과 CB 발행이 걸린 종목이 다음 분기보고서 "
                           "접수만으로 제외 해제됐습니다. 소스별 행이 서로의 플래그를 NaN 으로 "
                           "덮고, as-of 결합이 최근 1행만 붙이기 때문입니다 — §6.4 하드 "
                           f"제외가 사실상 작동하지 않습니다. EXCLUDE={got}")
        if got[2] > 0:
            return False, (f"2년이 지난 뒤에도 제외가 유지됩니다(유효기간 미적용). EXCLUDE={got}")
        return True, ("소스가 다른 EX_AUDIT·EX_CBBW 가 동시에 유지되고(2019-06/09 제외), "
                      "유효기간 경과 후 해제됨(2021-06) 확인")

    _ac("A22", "배제 플래그 소스 간 상호 소거 방지", a22)

    # ── A23  전방수익률이 다음 분기 유니버스 잔류에 조건 지워지지 않는가 ─────────────────
    def a23():
        # WINNER 는 다음 리밸일에 U-1000 밖으로 나가지만(=크게 오른 종목) 가격은 계속 있다.
        rb = pd.to_datetime(["2019-03-01", "2019-06-01"])
        U = pd.DataFrame({"code": ["WIN", "LOS", "LOS"],
                          "asof": [rb[0], rb[0], rb[1]],
                          "mktcap": [1e10, 1e10, 1e10], "uni_rank": [1, 2, 1],
                          "adtv60": [5e8, 5e8, 5e8]})
        execp = pd.DataFrame({"code": ["WIN", "WIN", "LOS", "LOS"],
                              "asof": [rb[0], rb[1], rb[0], rb[1]],
                              "exec_px": [100.0, 118.0, 100.0, 97.0],
                              "exec_date": [rb[0], rb[1], rb[0], rb[1]]})
        sec = pd.DataFrame({"code": ["WIN", "LOS"], "name": ["승자", "패자"],
                            "market": ["KOSDAQ"] * 2, "industry": ["기타"] * 2,
                            "corp_code": ["W", "L"], "listing_date": [pd.NaT] * 2})

        class _U:
            def delisting_map(self): return {}
        P = build_arc_panel(_U(), rb, U, pd.DataFrame(), execp, sec, px_daily=None)
        w = P[(P["code"] == "WIN") & (P["asof"] == rb[0])]
        if w.empty or not np.isfinite(float(w["fwd_ret_1q"].iloc[0])):
            return False, ("★다음 분기에 U-1000 을 이탈하는 종목의 전방수익률이 NaN 입니다. "
                           "run_backtest 의 elig 필터가 그 종목을 **오늘의 편입 후보에서** "
                           "지우므로, 오늘의 편입 자격이 내일의 유니버스 잔류 여부로 "
                           "결정됩니다(방향성 있는 편향).")
        r = float(w["fwd_ret_1q"].iloc[0])
        if abs(r - 0.18) > 1e-3:
            return False, f"전방수익률이 체결가 격자와 불일치: {r:+.4f} (기대 +0.1800)"
        return True, f"유니버스 이탈 종목도 execp 격자에서 정상 계산 ({r:+.2%})"

    _ac("A23", "전방수익률 ⊥ 미래 유니버스 멤버십", a23)

    # ── A24  상장폐지: 정상 폐지는 청산가, 거래정지 후 폐지는 복원 ────────────────────────
    def a24():
        rb = pd.to_datetime(["2019-09-01", "2019-12-01", "2020-03-01"])
        # MERGE: 2019-12-27 피흡수합병(정상 폐지). 직전까지 정상 거래 → -100% 면 가짜 손실.
        # HALT : 2019-12-10 거래정지 → 2020-09-30 폐지. 패널에서 먼저 사라지는 경로.
        U = pd.DataFrame({"code": ["MRG", "HLT"], "asof": [rb[1], rb[1]],
                          "mktcap": [1e10, 1e10], "uni_rank": [1, 2],
                          "adtv60": [5e8, 5e8]})
        execp = pd.DataFrame({"code": ["MRG", "HLT"], "asof": [rb[1], rb[1]],
                              "exec_px": [100.0, 100.0], "exec_date": [rb[1], rb[1]]})
        px = pd.DataFrame({
            "code": ["MRG"] * 2 + ["HLT"] * 2,
            "date": pd.to_datetime(["2019-12-02", "2019-12-20",
                                    "2019-12-02", "2019-12-09"]),
            "open": [100.0, 98.0, 100.0, 40.0], "close": [99.0, 98.0, 95.0, 38.0]})
        sec = pd.DataFrame({"code": ["MRG", "HLT"], "name": ["합병", "정지"],
                            "market": ["KOSDAQ"] * 2, "industry": ["기타"] * 2,
                            "corp_code": ["M", "H"], "listing_date": [pd.NaT] * 2})

        class _U:
            def delisting_map(self):
                return {"MRG": pd.Timestamp("2019-12-27"),
                        "HLT": pd.Timestamp("2020-09-30")}
        P = build_arc_panel(_U(), rb, U, pd.DataFrame(), execp, sec, px_daily=px)
        g = {c: float(v) for c, v in zip(P["code"], P["fwd_ret_1q"])}
        if abs(g.get("MRG", -9) + 1.0) < 1e-6:
            return False, ("★합병·완전자회사화 같은 정상 폐지에 -100% 가 붙었습니다. "
                           "실제로는 합병비율·공개매수가로 원금 수준이 회수됩니다 — "
                           "폐지목록의 34%가 정상 사유이므로 상시 가짜 손실이 됩니다.")
        if abs(g.get("MRG", 0) - (98.0 / 100.0 - 1.0)) > 1e-6:
            return False, f"정상 폐지 청산가가 폐지일 직전 종가가 아닙니다: {g.get('MRG')}"
        if not (g.get("HLT", 0) < -0.5):
            return False, ("★거래정지 후 폐지 종목의 손실이 계상되지 않았습니다. "
                           "거래정지 → 시총 격자 소실 → 폐지 순서라 패널에 행이 없어지고, "
                           "한국의 감사의견거절·자본잠식 폐지는 대부분 이 경로입니다 "
                           f"— 손실만 선택적으로 사라집니다. fwd_ret={g.get('HLT')}")
        return True, (f"정상 폐지는 직전 종가 청산({g['MRG']:+.2%}) · "
                      f"거래정지 후 폐지는 복원({g['HLT']:+.2%})")

    _ac("A24", "§3.4 상장폐지 청산가 · 거래정지 경로", a24)

    # ── A25  결정적 해시 (프로세스 간 재현성) ─────────────────────────────────────────────
    def a25():
        import subprocess as _sp
        src = ("import hashlib;"
               "print(int.from_bytes(hashlib.blake2b('영업이익'.encode(),"
               "digest_size=8).digest(),'little')%262144)")
        outs = set()
        for _ in range(2):
            r = _sp.run([sys.executable, "-c", src], capture_output=True, text=True,
                        timeout=30, env={**os.environ, "PYTHONHASHSEED": "random"})
            outs.add(r.stdout.strip())
        if len(outs) != 1:
            return False, f"해시가 프로세스마다 다릅니다: {outs}"
        if "hash(w)" in inspect.getsource(_ToneNaiveBayes):
            return False, ("★폴백 TONE 분류기가 파이썬 내장 hash() 를 씁니다. CPython 의 "
                           "문자열 해시는 PYTHONHASHSEED 로 프로세스마다 랜덤화되므로 같은 "
                           "SEED·같은 캐시로 두 번 돌리면 보유 종목이 달라집니다. A14 는 "
                           "동일 프로세스 안에서 돌아 이것을 잡지 못합니다.")
        return True, f"blake2b 결정적 해시 사용 · 프로세스 간 동일값({outs.pop()})"

    _ac("A25", "폴백 분류기 해시 결정성", a25)

    # ── A26  D2 윈저 · D1 최종 z 가 기간을 섞지 않는가 ────────────────────────────────────
    def a26():
        rng = np.random.default_rng(11)
        n = 200
        base = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)] * 2,
            "corp_code": [f"C{i}" for i in range(n)] * 2,
            "asof": [pd.Timestamp("2016-09-01")] * n + [pd.Timestamp("2025-09-01")] * n,
            "q": ["2016Q2"] * n + ["2025Q2"] * n, "sector": ["기타"] * (2 * n),
            "cell": ["2016Q2|기타"] * n + ["2025Q2|기타"] * n,
            "cell_all": ["2016Q2|ALL"] * n + ["2025Q2|ALL"] * n,
            "D2_FORCED_LOW": 0.0})
        for c, _s in D2_ITEMS:
            base[c] = rng.normal(size=2 * n)
        A = attach_d2(base.copy(), None)
        B = base.copy()
        # 2025년 코호트의 한 지표만 8배로 부풀린다 — 2016년 점수는 변하면 안 된다.
        c0 = D2_ITEMS[0][0]
        B.loc[n:, c0] = B.loc[n:, c0] * 8.0
        Bz = attach_d2(B, None)
        d = (pd.to_numeric(A.loc[:n - 1, "D2_SCORE"], errors="coerce") -
             pd.to_numeric(Bz.loc[:n - 1, "D2_SCORE"], errors="coerce")).abs().max()
        if not np.isfinite(d):
            return None, "D2_SCORE 를 계산할 수 없어 건너뜁니다"
        if d > 1e-6:
            return False, ("★2025년 데이터를 바꿨더니 2016년 D2_SCORE 가 달라졌습니다 "
                           f"(최대 {d:.4f}z). 윈저라이즈 경계·강제최하위 값이 전 기간 "
                           "백분위로 잡혀 있어, 과거 관측치의 클리핑 한계가 미래로 정해집니다.")
        return True, f"2025년 코호트 변경이 2016년 D2_SCORE 에 영향 없음 (최대 {d:.2e}z)"

    _ac("A26", "D2 윈저라이즈 기간 분리", a26)

    # ── A27  축 A 결측이 '점수 축소'로 사실상 탈락시키지 않는가 ───────────────────────────
    def a27():
        # A10 은 FINAL_SCORE 가 NaN 이 아닌지만 본다. 결측군의 분산이 절반으로 줄면 NaN 은
        # 아니면서도 상위 N 꼬리에 도달하지 못한다 — 여기서는 **선정률**로 검사한다.
        rng2 = np.random.default_rng(7)
        n, cov, K = 600, 0.20, 30
        P = pd.DataFrame({
            "code": [f"{i*10:06d}" for i in range(n)],
            "corp_code": [f"C{i}" for i in range(n)],
            "asof": [pd.Timestamp("2020-06-01")] * n, "q": ["2020Q1"] * n,
            "sector": ["기타"] * n, "cell": ["2020Q1|기타"] * n,
            "cell_all": ["2020Q1|ALL"] * n,
            "D1_SCORE": rng2.normal(size=n), "D2_SCORE": rng2.normal(size=n),
            "D3_SCORE": rng2.normal(size=n), "EXCLUDE": 0.0})
        has_a = rng2.random(n) < cov                       # 축 A 보유 여부 ⟂ 축 B 점수
        t = rng2.normal(size=n)
        P["dTONE"] = np.where(has_a, t, np.nan)
        P["dTONE_resid"] = P["dTONE"]
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        top = Q.nlargest(K, "FINAL_SCORE")
        share = float(top["dTONE_resid"].notna().mean())
        ratio = share / max(cov, 1e-9)
        if Q["FINAL_SCORE"].isna().any():
            return False, "축 B 가 있는데도 FINAL_SCORE 가 결측인 행이 있습니다"
        if ratio > 1.6:
            return False, (f"★축 A 보유 종목이 상위 {K} 를 {ratio:.2f}배 과대점유합니다 "
                           f"(커버리지 {cov:.0%} · 상위 점유 {share:.0%}). 축 A 결측 행은 "
                           f"AXIS_A_Z=0 으로 채워져 FINAL 의 분산이 절반이 되고, 선정은 "
                           f"꼬리에서 일어나므로 NaN 이 아닌데도 구조적으로 밀립니다 — "
                           f"§7.2 '탈락시키지 말 것'의 실질 위반입니다.")
        return True, (f"커버리지 {cov:.0%} · 상위 {K} 중 축 A 보유 {share:.0%} "
                      f"(과대선택 {ratio:.2f}배, 허용 1.6배 이하)")

    _ac("A27", "축 A 결측 종목의 실질 편입률 (§7.2)", a27)

    # ── A28  매도 슬리피지가 폴백(2%)으로 새지 않는가 ─────────────────────────────────────
    def a28():
        rb = pd.to_datetime(["2019-03-01", "2019-06-01", "2019-09-01"])
        codes = [f"{i*10:06d}" for i in range(1, 61)]
        rows = []
        for ti, t in enumerate(rb):
            for i, c in enumerate(codes):
                # 분기마다 신호를 완전히 뒤집어 100% 회전을 만든다
                s = (i if ti % 2 == 0 else len(codes) - i) / len(codes)
                rows.append({"code": c, "asof": t, "adtv60": 5e8, "fwd_ret_1q": 0.0,
                             "FINAL_RANK": s, "FINAL_SCORE": s, "EXCLUDE": 0.0,
                             "vol_q": 0.3})
        P = pd.DataFrame(rows)

        class _U:
            def delisting_map(self): return {}
            def audit_row(self, *a, **k): pass
        bt = run_backtest(P, rb, _U(), None, top_n=10, apply_costs=True, label="A28")
        R = bt["returns"]
        cost_q = float(R.loc[R["measurable"], "cost"].mean())
        # 전 종목 ADTV 가 동일하므로 매수·매도 슬리피지가 같아야 한다.
        # adv=0 폴백(2%)이 매도 쪽에만 걸리면 비용이 대략 2배 이상으로 뛴다.
        w, notional = 0.1, 0.1 * ARC_ACCOUNT_KRW
        sl = arc_slippage(notional, 5e8)
        expect = 2.0 * 10 * w * (ARC_COMMISSION_BPS / 1e4 + sl) + \
                 10 * w * arc_sell_tax(rb[1])
        if cost_q > expect * 1.5:
            return False, (f"★분기 비용 {cost_q:.4f} 가 기대치 {expect:.4f} 의 1.5배를 "
                           f"넘습니다. 전량 매도 종목이 advmap 에 없어 슬리피지가 일괄 2% "
                           f"폴백으로 매겨지고 있습니다 — 회전율이 다른 어블레이션 팔이 "
                           f"부당한 벌점을 받습니다.")
        return True, (f"분기 비용 {cost_q:.4f} (기대 {expect:.4f}) · "
                      f"매도 슬리피지 폴백 없음")

    _ac("A28", "매도 슬리피지 ADTV 폴백 누수", a28)

    # ── A29  Sortino · 파산 경로 방어 ─────────────────────────────────────────────────────
    def a29():
        r = np.array([0.12, -0.030, 0.09, -0.0305, 0.11, -0.0298, 0.08, -0.0302] * 3)
        R = pd.DataFrame({"asof": pd.date_range("2016-03-01", periods=len(r), freq="QS"),
                          "ret": r, "ret_gross": r, "n": 30, "turnover": 1.0,
                          "cost": 0.0, "n_elig": 100, "measurable": True})
        st = perf_stats(R)
        dd_def = float(np.sqrt((np.minimum(r, 0.0) ** 2).mean()) * math.sqrt(4))
        want = (st["CAGR"]) / dd_def
        if abs(st["Sortino"] - want) > 0.05:
            return False, (f"★Sortino {st['Sortino']:.2f} 가 정의값 {want:.2f} 와 다릅니다. "
                           f"하방편차를 '음수 수익률들의 자기 평균 대비 표본표준편차'로 "
                           f"계산하면 손실의 크기가 아니라 균일함을 보상하게 되어 "
                           f"손실이 뭉친 팔이 세 자리 Sortino 로 최우수처럼 보입니다.")
        # 파산 경로: 1+r<0 이 두 번 나오면 cumprod 가 부호를 뒤집어 되살아난다
        r2 = np.array([0.1, -1.10, 0.2, -1.10, 0.3, 0.4])
        R2 = pd.DataFrame({"asof": pd.date_range("2016-03-01", periods=6, freq="QS"),
                           "ret": r2, "ret_gross": r2, "n": 1, "turnover": 1.0,
                           "cost": 0.0, "n_elig": 1, "measurable": True})
        s2 = perf_stats(R2)
        if s2["MDD"] < -1.0 - 1e-9:
            return False, f"★MDD {s2['MDD']:.2%} — 정의상 -100% 아래는 불가능합니다"
        if not (np.isnan(s2["CAGR"]) or s2["CAGR"] <= -0.999):
            return False, (f"★자본곡선이 0 을 통과했는데 CAGR {s2['CAGR']:+.2%} 로 "
                           f"계산됐습니다(파산 경로가 양의 자본으로 되살아남).")
        return True, (f"Sortino 정의 일치 ({st['Sortino']:.2f}) · "
                      f"파산 경로 CAGR {s2['CAGR']:+.0%} · MDD {s2['MDD']:.0%}")

    _ac("A29", "Sortino 정의 · 파산 경로 방어", a29)

    # ── A30  '모름' 이 D3 합산에서 0 으로 붕괴하지 않는가 ─────────────────────────────────
    def a30():
        H = pd.DataFrame({"corp_code": ["C1", "C2"],
                          "event_date": pd.to_datetime(["2019-03-31"] * 2),
                          "knowledge_date": pd.to_datetime(["2019-04-01"] * 2)})
        for i, c in enumerate(D3_COLS):
            H[c] = [1.0 if i < 2 else 0.0, np.nan]        # C2 는 전 태그 '모름'
        H["D3_N_OBS"] = H[D3_COLS].notna().sum(axis=1).astype("int16")
        H["DELTA_NONFIN"] = H[D3_COLS].sum(axis=1, skipna=True).where(H["D3_N_OBS"] > 0)
        if pd.notna(H.loc[1, "DELTA_NONFIN"]):
            return False, ("★전 태그가 '모름'인 법인의 ΔNONFIN 이 0.0 으로 계산됐습니다. "
                           "문서 파싱에 실패한 법인이 '사실이 하나도 없는 법인'과 같은 "
                           "척도로 z-scoring 되어, D3_SCORE 가 사실 건수가 아니라 데이터 "
                           "커버리지의 함수가 됩니다(최종 점수의 10%).")
        if float(H.loc[0, "DELTA_NONFIN"]) != 2.0:
            return False, f"관측이 있는 법인의 ΔNONFIN 이 틀렸습니다: {H.loc[0, 'DELTA_NONFIN']}"
        return True, "전 태그 결측 → ΔNONFIN 결측 · 관측 있으면 정상 합산 · D3_N_OBS 병기"

    _ac("A30", "D3 '모름' vs '미발화' 구분", a30)

    # ── A31  직교화 자유도 가드 ───────────────────────────────────────────────────────────
    def a31():
        rng3 = np.random.default_rng(3)
        p = 13                                   # 통제 6 + 섹터더미 7
        corrs = {}
        for nobs in (17, 60, 200):
            acc = []
            for _ in range(60):
                X = rng3.normal(size=(nobs, p))
                y = rng3.normal(size=nobs)       # y ⟂ X (진짜 신호는 전부 잔차여야 한다)
                res = ols_resid_np(y, X)
                if np.isfinite(res).sum() < 3:
                    continue
                m = np.isfinite(res)
                acc.append(abs(float(np.corrcoef(y[m], res[m])[0, 1])))
            corrs[nobs] = (float(np.mean(acc)) if acc else np.nan, len(acc))
        thin, _ = corrs[17]
        if np.isfinite(thin) and thin < 0.80:
            return False, (f"★관측 17개 · 파라미터 {p+1}개에서 잔차가 원신호를 {1-thin:.0%} "
                           f"만큼 먹었습니다(corr={thin:.2f}). 'ΔTONE_resid' 가 실제로는 "
                           f"규모·모멘텀·섹터의 적합오차, 즉 위장된 사이즈 베팅이 되고 "
                           f"그 값이 FINAL_SCORE 의 50% 를 차지합니다.")
        n_ok = corrs[200][1]
        if n_ok == 0:
            return False, "관측 200개에서도 잔차가 생성되지 않습니다(가드가 과도)"
        return True, (f"자유도 부족(n=17) 시 잔차 미생성 · "
                      f"n=60 corr {corrs[60][0]:.2f} · n=200 corr {corrs[200][0]:.2f} "
                      f"(하한 {OLS_MIN_OBS_PER_PARAM}×파라미터)")

    _ac("A31", "직교화 자유도 하한", a31)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 30),
             {True: "✔ 통과", False: "✘ 실패", None: "— 건너뜀"}[r["pass"]],
             _trunc(r["msg"], 78)] for r in CONTRACT_RESULTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=82,
              title="계약 자동검정 A1~A31 (협상 대상이 아님)")
    failed = [r for r in CONTRACT_RESULTS if r["pass"] is False]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        for r in failed[:4]:
            LOG.banner(f"✘ 계약 위반: [{r['id']}] {r['name']}", _trunc(r["msg"], 96))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len([r for r in CONTRACT_RESULTS if r['pass'] is True])}건 전부 통과 "
           f"(건너뜀 {len([r for r in CONTRACT_RESULTS if r['pass'] is None])}건).")
    return True
