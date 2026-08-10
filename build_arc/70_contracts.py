

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 A1~A19 — 주석이나 관례는 무효. 테스트로만 강제한다.                          ║
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

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 30),
             {True: "✔ 통과", False: "✘ 실패", None: "— 건너뜀"}[r["pass"]],
             _trunc(r["msg"], 78)] for r in CONTRACT_RESULTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=82,
              title="계약 자동검정 A1~A19 (협상 대상이 아님)")
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
