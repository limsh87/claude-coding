

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0  명세 전수조사 (§3.1 ~ §10.4)  —  계약 Q1~Q14 와 무엇이 다른가                          ║
# ║                                                                                          ║
# ║  계약은 '원칙'을 지킨다: PIT 강제 · 생존자편향 · 결정성 · 비용 단조성.                       ║
# ║  그런데 원칙이 전부 지켜져도 '숫자가 명세와 다를' 수 있다.                                   ║
# ║    실제로 계약·스모크·리허설을 전부 통과한 상태에서 §5.3 이 지정한 Q축 5개 지표 중           ║
# ║    3개가 z 를 하나도 만들지 않고 있었다(관측률 100% 인데 z 산출 0행). 어느 계약도            ║
# ║    "지정된 지표가 실제로 산출되는가" 를 보고 있지 않았기 때문이다.                           ║
# ║                                                                                          ║
# ║  그래서 조항 단위로 따로 검정한다. 조항마다                                                 ║
# ║    ① 정답을 아는 합성 입력을 만들고  ② 실제 함수를 돌리고  ③ 숫자로 PASS/FAIL 판정          ║
# ║                                                                                          ║
# ║  ★ 검정을 쓸 때의 규칙: "이 검정이 실패하는 입력을 만들 수 있는가" 를 먼저 확인할 것.        ║
# ║    검정력 0 인 검정은 통과해도 아무것도 보장하지 않는다 — 계약 8개가 그 상태로 ✔ 였다.      ║
# ║    아래 검정들이 '검정력 확인' 소검정을 함께 두는 이유다.                                    ║
# ║                                                                                          ║
# ║  ★ 이 층은 파이프라인을 오염시키면 안 된다. 전역을 만지는 검정이 있으므로(U1000_N,           ║
# ║    EXPERIMENTS, 거래일 캘린더 …) 실행 전후로 스냅샷을 떠서 복원하고, 복원 여부 자체를        ║
# ║    마지막에 검정한다. 검증층이 본 실행의 입력을 바꾸면 그건 검증이 아니라 사고다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SPEC_CASES: List[Tuple[str, str, Callable]] = []


def spec_clause(cid: str, title: str):
    def deco(fn):
        SPEC_CASES.append((cid, title, fn))
        return fn
    return deco


class SpecChk:
    """한 조항 안의 소검정 모음. 통과/실패 모두 '숫자'를 남긴다."""

    def __init__(self):
        self.rows: List[Tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, evidence: str = ""):
        self.rows.append((name, bool(ok), evidence))
        return bool(ok)

    def eq(self, name: str, got, want, tol: float = 0.0):
        try:
            ok = abs(float(got) - float(want)) <= tol
            ev = f"실측 {got!r} · 기대 {want!r}" + (f" (허용 {tol})" if tol else "")
        except (TypeError, ValueError):
            ok = got == want
            ev = f"실측 {got!r} · 기대 {want!r}"
        return self.add(name, ok, ev)

    @property
    def passed(self) -> bool:
        return all(ok for _n, ok, _e in self.rows)


# ── 합성 입력 헬퍼 ──────────────────────────────────────────────────────────────────────────
def _sa_grid(n_codes: int, rebals: Sequence[str], **cols) -> pd.DataFrame:
    """(code × rebal) 격자. 값은 스칼라 또는 길이 n_codes 시퀀스."""
    codes = [f"{i:06d}" for i in range(1, n_codes + 1)]
    rows = []
    for t in rebals:
        for i, c in enumerate(codes):
            r = {"code": c, "rebal": pd.Timestamp(t),
                 "signal_date": pd.Timestamp(t) - pd.Timedelta(days=1),
                 "exec_date": pd.Timestamp(t) + pd.Timedelta(days=1)}
            for k, v in cols.items():
                r[k] = v[i] if isinstance(v, (list, tuple)) else v
            rows.append(r)
    return pd.DataFrame(rows)


def _sa_cells(P: pd.DataFrame) -> pd.DataFrame:
    """build_sector_cells 와 같은 규약의 셀 컬럼."""
    d = P.copy()
    if "sector" not in d.columns:
        d["sector"] = "테스트섹터"
    ym = as_ts_series(d["rebal"]).dt.strftime("%Y%m")
    d["cell"] = ym + "|" + d["sector"].astype(str)
    d["cell_l2"] = ym + "|" + d["sector"].astype(str).str.slice(0, 4)
    d["cell_l3"] = ym + "|ALL"
    return d


def _sa_prices(codes: Sequence[str], dates, amount=1e9, close=1000.0,
               skip: Optional[Dict[str, set]] = None) -> pd.DataFrame:
    """일봉 패널. skip[code] 의 인덱스는 행 자체를 만들지 않는다(소스 누락 재현)."""
    rows = []
    for c in codes:
        for i, d in enumerate(dates):
            if skip and c in skip and i in skip[c]:
                continue
            am = amount[c] if isinstance(amount, dict) else amount
            rows.append({"code": c, "date": pd.Timestamp(d), "open": close,
                         "high": close * 1.01, "low": close * 0.99, "close": close,
                         "amount": am, "volume": am / max(close, 1)})
    return pd.DataFrame(rows)


def _sa_bdays(start: str, n: int):
    return list(pd.bdate_range(start, periods=n))


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §3  유니버스
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§3.1", "U-1000 = PIT 시총 '하위' N · 해석 A/B 가 실제로 다른 모집단인가")
def _sc31():
    k = SpecChk()
    k.eq("U1000_N", U1000_N, 1000)
    n = 300
    G0 = _sa_grid(n, ["2020-03-01"], mktcap=[float(i) * 1e8 for i in range(1, n + 1)],
                  adtv=5e8, equity=1e9, excl_struct="", sector="X")
    k.eq("적격 300종목 전부 선정(N<1000)", len(select_u1000(G0)), 300)

    old_n, old_b = U1000_N, U1000_RANK_BEFORE_FILTER
    try:
        globals()["U1000_N"] = 50
        got = sorted(int(c) for c in select_u1000(G0)["code"])
        k.eq("N=50 선정 수", len(got), 50)
        k.add("선정 = 시총 최소 50종목", got == list(range(1, 51)),
              f"선정 코드 min={got[0]} max={got[-1]} (기대 1..50)")
        # 해석 A(게이트→하위N) vs B(하위N→게이트): 하위 40 의 유동성을 죽이면 갈린다
        Gb = G0.copy()
        Gb.loc[Gb["code"].isin([f"{i:06d}" for i in range(1, 41)]), "adtv"] = 1e6
        globals()["U1000_RANK_BEFORE_FILTER"] = False
        nA = len(select_u1000(Gb))
        globals()["U1000_RANK_BEFORE_FILTER"] = True
        nB = len(select_u1000(Gb))
    finally:
        globals()["U1000_N"], globals()["U1000_RANK_BEFORE_FILTER"] = old_n, old_b
    k.eq("해석 A(기본): 게이트 통과분에서 하위 50", nA, 50)
    k.eq("해석 B: 하위 50 을 먼저 뽑고 게이트", nB, 10)
    k.add("기본값은 해석 A", U1000_RANK_BEFORE_FILTER is False,
          f"U1000_RANK_BEFORE_FILTER={U1000_RANK_BEFORE_FILTER}")
    return k


@spec_clause("§3.2", "유동성 게이트 — 직전 60거래일 평균 거래대금 ≥ 1억원")
def _sc32():
    k = SpecChk()
    k.eq("ADTV_WINDOW_DAYS", ADTV_WINDOW_DAYS, 60)
    k.eq("MIN_ADTV_KRW", MIN_ADTV_KRW, 100_000_000)

    G0 = _sa_grid(3, ["2020-03-01"], mktcap=1e9,
                  adtv=[99_999_999.0, 100_000_000.0, 100_000_001.0],
                  equity=1e9, excl_struct="", sector="X")
    sel = set(select_u1000(G0)["code"])
    k.add("adtv = 99,999,999 → 탈락", "000001" not in sel, f"선정={sorted(sel)}")
    k.add("adtv = 100,000,000 → 통과", "000002" in sel, f"선정={sorted(sel)}")

    # '그 종목이 가진 60개 행'이 아니라 '시장 60거래일' 인가.
    #   A: 60일 전부 거래(2억) → 2억 · B: 3일에 1일만 행 존재(3억) → 3억×20/60 = 1억
    days = _sa_bdays("2020-01-01", 80)
    px = pd.concat([_sa_prices(["000001"], days, amount=2e8),
                    _sa_prices(["000002"], days, amount=3e8,
                               skip={"000002": {i for i in range(80) if i % 3 != 0}})],
                   ignore_index=True)
    cal = pd.DataFrame([{"rebal": pd.Timestamp("2020-04-01"),
                         "signal_date": days[79], "exec_date": days[79]}])
    A = build_adtv_panel(cal, px, window=60)
    a = dict(zip(A["code"].astype(str), pd.to_numeric(A["adtv"])))
    k.eq("전일 거래 종목 ADTV", a.get("000001", float("nan")), 2e8, tol=1e3)
    gb = a.get("000002", float("nan"))
    k.add("결측일이 있는 종목은 시장격자 기준(0 채움)으로 희석된다", abs(gb - 1.0e8) <= 6e6,
          f"실측 {gb:,.0f} · 시장격자 기대 ≈100,000,000 · "
          f"'자기 행 60개' 해석이면 300,000,000 (3배 과대)")

    days2 = _sa_bdays("2020-01-01", 40)
    cal2 = pd.DataFrame([{"rebal": pd.Timestamp("2020-03-01"),
                          "signal_date": days2[39], "exec_date": days2[39]}])
    k.eq("거래일 40일뿐이면 ADTV 산출 없음(min_periods=60)",
         len(build_adtv_panel(cal2, _sa_prices(["000009"], days2, amount=5e8), window=60)), 0)
    return k


@spec_clause("§3.3", "구조적 제외(우선주·스팩·리츠·ETF) · 상장 12개월 미만 · 완전자본잠식")
def _sc33():
    k = SpecChk()
    k.eq("SEASONING_DAYS", SEASONING_DAYS, 250)

    # ★ 코드 6번째가 '0' 이 아니면 코드 규칙만으로 우선주가 된다. 이름 규칙을 검정하려면
    #   반드시 '…0' 코드를 써야 한다 — 아니면 이름 규칙에 검정력이 0 이다.
    for code, name, why in (("005935", "삼성전자우", "우선주"),
                            ("000000", "삼성전자우선주", "우선주"),
                            ("000010", "케이비제20호스팩", "스팩"),
                            ("000020", "이지스밸류리츠", "리츠"),
                            ("000030", "KODEX 200", "ETF/ETN"),
                            ("000040", "TIGER 2차전지", "ETF/ETN"),
                            ("000050", "KODEX 레버리지", "ETF/ETN")):
        got = classify_exclusion(code, name)
        k.add(f"제외되어야: {name}", got == why, f"판정='{got}' (기대 '{why}')")
    # 이름 규칙의 오탐은 실존 소형주를 '시점 불변'으로 지운다 — 전 실험에서 동일하게 빠진다
    for code, name in (("100130", "동국S&C"), ("115960", "연우"), ("047310", "파워로직스"),
                       ("037400", "우리조명"), ("032190", "다우데이타"),
                       ("006800", "미래에셋증권")):
        got = classify_exclusion(code, name)
        k.add(f"제외되면 안 됨: {name}", got == "", f"판정='{got}'")

    days = _sa_bdays("2018-01-01", 800)
    px = _sa_prices(["000010"], days)
    sec = pd.DataFrame([
        {"code": "OLD001", "name": "구상장", "market": "KOSPI", "industry": "X",
         "listing_date": pd.Timestamp("2010-01-01"), "delisting_date": pd.NaT},
        {"code": "NEW001", "name": "신규상장", "market": "KOSDAQ", "industry": "X",
         "listing_date": days[700], "delisting_date": pd.NaT},
        {"code": "MID001", "name": "중간상장", "market": "KOSDAQ", "industry": "X",
         "listing_date": days[100], "delisting_date": pd.NaT},
        {"code": "DEL001", "name": "폐지예정", "market": "KOSDAQ", "industry": "X",
         "listing_date": pd.Timestamp("2010-01-01"), "delisting_date": days[500]}])
    uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    at = set(uni.at(days[600]))
    k.add("패널 이전 상장 종목은 포함", "OLD001" in at, f"at()={sorted(at)}")
    k.add("상장 후 250거래일 미만은 제외", "NEW001" not in at, f"at()={sorted(at)}")
    k.add("상장 후 500거래일은 포함", "MID001" in at, f"at()={sorted(at)}")
    k.add("이미 폐지된 종목은 제외", "DEL001" not in at, f"at()={sorted(at)}")
    k.add("폐지 전 시점에는 폐지예정 종목이 포함(생존자편향 방지)",
          "DEL001" in set(uni.at(days[400])), "at(폐지 100거래일 전)")

    G0 = _sa_grid(3, ["2020-03-01"], mktcap=[1e8, 2e8, 3e8], adtv=5e8,
                  equity=[1e9, 0.0, float("nan")], excl_struct="", sector="X")
    sel = set(select_u1000(G0)["code"])
    k.add("equity > 0 → 포함", "000001" in sel, f"선정={sorted(sel)}")
    k.add("equity = 0 (완전잠식) → 제외", "000002" not in sel, f"선정={sorted(sel)}")
    k.add("equity 결측 → 제외하지 않음(모름 ≠ 잠식)", "000003" in sel, f"선정={sorted(sel)}")
    return k


@spec_clause("§3.3b", "종목코드 정규화 — 없는 티커를 '만들어내지' 않는다 (폐지 오적용 방지)")
def _sc33b():
    """FDR 폐지목록에는 `00341A`(쌍용양회4우B) 같은 구형 우선주 코드가 실재한다.
    숫자만 뽑아 0 으로 채우면 `000341`(쌍용양회 보통주)이 된다 — 우선주의 폐지일이
    보통주에 붙어, 실제로는 상장 중인 종목이 유니버스에서 사라지고 보유분이 −100% 가 된다.
    실측(2026-08-10 FDR 폐지목록 4,173행): 원본≠매핑 285건, 그중 주권 13건."""
    k = SpecChk()
    for raw, want in (("005930", "005930"), (5930, "005930"), ("A005930", "005930"),
                      ("005930.KS", "005930"), (" 005930 ", "005930"), ("09701K", "09701K")):
        k.eq(f"정상 입력 {raw!r}", to_code6(raw), want)
    # 문자가 섞인 코드는 '만들어내지' 말고 실패해야 한다
    for raw in ("00341A", "00246A", "01683B", "00736C", "722011J7", "002991K5",
                "KR7005930003"):
        k.add(f"날조 금지: {raw!r} → None", to_code6(raw) is None, f"실측 {to_code6(raw)!r}")
    return k


@spec_clause("§3.4", "상장폐지 — 정리매매가 관측 시 실가, 아니면 −100% (누락 금지)")
def _sc34():
    k = SpecChk()
    days = _sa_bdays("2020-01-02", 260)
    cal = pd.DataFrame([
        {"rebal": pd.Timestamp("2020-03-01"), "signal_date": days[41], "exec_date": days[42]},
        {"rebal": pd.Timestamp("2020-06-01"), "signal_date": days[104], "exec_date": days[105]},
        {"rebal": pd.Timestamp("2020-09-01"), "signal_date": days[168], "exec_date": days[169]}])
    px = pd.concat([_sa_prices(["A"], days), _sa_prices(["B"], days[:70]),
                    _sa_prices(["C"], days[:60], close=900.0), _sa_prices(["D"], days[:70]),
                    _sa_prices(["E"], days[:50])], ignore_index=True)
    px.loc[(px["code"] == "A") & (px["date"] == days[105]), ["open", "close"]] = 1200.0
    px.loc[(px["code"] == "B") & (px["date"] == days[69]),
           ["open", "close", "high", "low"]] = 300.0
    px.loc[(px["code"] == "D") & (px["date"] == days[69]),
           ["open", "close", "high", "low"]] = 1500.0

    fwd = build_forward_returns(build_exec_prices(cal, px), cal,
                                {"B": days[71], "C": days[71], "D": days[71], "E": days[180]}, px)
    f = fwd.set_index(["code", "rebal"])

    def _r(c):
        try:
            return float(f.loc[(c, pd.Timestamp("2020-03-01")), "fwd_ret"])
        except KeyError:
            return float("nan")

    k.eq("A 정상 보유 수익률", _r("A"), 0.20, tol=1e-5)
    k.eq("B 정리매매가(300/1000−1) 반영", _r("B"), -0.70, tol=1e-5)
    k.eq("C 가격 부재 → −100%", _r("C"), -1.0, tol=1e-9)
    # ⚠ 이 한 줄은 '현재의 보수적 동작'을 사전등록으로 못박은 것이지 명세가 못박은 것이 아니다.
    #   정리매매가를 '손실일 때만' 인정하는 이유: 소스가 폐지 직전에 종목을 드롭하면 마지막
    #   정상가가 청산가로 둔갑해 '상장폐지 = 0% 손실'이 되고, 그게 생존자편향의 재유입이다.
    #   반대 비용도 실재한다 — 합병·공개매수·자진상장폐지 같은 '상향 청산'이 −100% 로 계상된다.
    #   ★ 그쪽을 인정하도록 고치려면 이 소검정을 먼저 고쳐야 한다. 실패하면 회귀가 아니라
    #     의도된 변경이다. 어느 방향이 옳은지는 실데이터에서 각 경우의 건수를 세야 정해진다.
    k.eq("D 마지막 관측가가 '이익' → 현재는 규정대로 −100% (상향청산 미인정 · 열린 쟁점)",
         _r("D"), -1.0, tol=1e-9)
    k.eq("E 정지 후 다음 분기 이후 폐지 → −100% (0% 로 새지 않는다)", _r("E"), -1.0, tol=1e-9)
    k.add("E 는 halt_then_delist 로 별도 계상",
          "halt_then_delist" in {str(v) for c, v in zip(fwd["code"], fwd["exit_kind"]) if c == "E"},
          f"exit_kind(E)={[v for c, v in zip(fwd['code'], fwd['exit_kind']) if c=='E']}")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §4  시점 규약
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§4", "분기 3/1·6/1·9/1·12/1 · 신호=직전 거래일 · 체결=익 거래일 · 공시=접수일+1거래일")
def _sc4():
    k = SpecChk()
    k.eq("REBAL_MONTHS", tuple(REBAL_MONTHS), (3, 6, 9, 12))
    k.eq("REBAL_DAY", REBAL_DAY, 1)

    days = _sa_bdays("2019-01-01", 700)
    px = _sa_prices(["000001"], days)
    cal = qvf_rebal_calendar(px, "2019-01-01", "2021-06-30")
    k.eq("명목 리밸런싱 월", tuple(sorted(set(pd.DatetimeIndex(cal["rebal"]).month))), (3, 6, 9, 12))
    k.add("명목일은 매월 1일", bool((pd.DatetimeIndex(cal["rebal"]).day == 1).all()),
          f"day 집합={sorted(set(pd.DatetimeIndex(cal['rebal']).day))}")
    n_bad = int((as_ts_series(cal["signal_date"]) >= as_ts_series(cal["exec_date"])).sum())
    k.add("signal_date < exec_date (전 시점)", n_bad == 0, f"위반 {n_bad}건")

    td = qvf_trading_days(px)
    ok_e = ok_s = True
    for r in cal.itertuples(index=False):
        i = int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.rebal)), side="left"))
        ok_e &= pd.Timestamp(td[i]) == pd.Timestamp(r.exec_date)
        ok_s &= pd.Timestamp(td[i - 1]) == pd.Timestamp(r.signal_date)
    k.add("exec_date = 명목일 이후(포함) 첫 거래일", ok_e, f"전 {len(cal)}시점 검사")
    k.add("signal_date = exec_date 직전 거래일", ok_s, f"전 {len(cal)}시점 검사")
    n_gap = int((as_ts_series(cal["exec_date"]) != as_ts_series(cal["rebal"])).sum())
    k.add("명목일 ≠ 체결일인 분기가 존재(검정력 확인)", n_gap > 0,
          f"{n_gap}/{len(cal)} 분기에서 명목일이 거래일이 아니다 (3/1 은 삼일절)")

    set_trading_days(px)
    fri = pd.Timestamp("2019-03-01")
    k.add("금요일 접수 → 다음 '거래일'(월요일)",
          pd.Timestamp(next_trading_day(fri)) == pd.Timestamp("2019-03-04"),
          f"{fri.date()} → {pd.Timestamp(next_trading_day(fri)).date()}")
    out = apply_t_plus_1(pd.DataFrame({"knowledge_date": [fri], "event_date": [fri]}), "검정")
    k.add("apply_t_plus_1 은 knowledge_date 만 민다",
          pd.Timestamp(out["knowledge_date"].iloc[0]) > fri
          and pd.Timestamp(out["event_date"].iloc[0]) == fri,
          f"knowledge {pd.Timestamp(out['knowledge_date'].iloc[0]).date()} · "
          f"event {pd.Timestamp(out['event_date'].iloc[0]).date()}")

    cal5 = qvf_rebal_calendar(px, "2019-01-01", "2021-06-30", shift_days=5)
    m = cal.merge(cal5, on="rebal", suffixes=("", "_s"))
    ok5 = all(int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.exec_date_s)), side="left"))
              - int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.exec_date)), side="left")) == 5
              for r in m.itertuples(index=False))
    k.add("shift_days=+5 → 체결일이 정확히 5거래일 뒤", ok5, f"{len(m)}시점 전부 +5거래일")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §5  1차 필터
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§5.2", "V축 — EV/EBIT·PBR·PCR · 섹터중립 · 1% 윈저 · 음수분모는 최하위 강제")
def _sc52():
    k = SpecChk()
    k.eq("WINSOR_PCT", WINSOR_PCT, 0.01)
    k.eq("V축 지표 구성", tuple(_V_METRICS), ("ev_ebit", "pbr", "pcr"))

    P = _sa_cells(_sa_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=200.0, cash=50.0,
                           op_income_ttm=[float(10 + i) for i in range(20)],
                           equity=[float(100 + i) for i in range(20)],
                           cfo_ttm=[float(20 + i) for i in range(20)],
                           liabilities=300.0, sector="X"))
    V = axis_V(P)
    r0 = V.iloc[0]
    k.eq("ev_ebit = (시총+차입−현금)/EBIT", float(r0["ev_ebit"]), (1000 + 200 - 50) / 10.0, tol=1e-5)
    k.eq("pbr = 시총/자기자본", float(r0["pbr"]), 10.0, tol=1e-5)
    k.eq("pcr = 시총/영업CF", float(r0["pcr"]), 50.0, tol=1e-5)
    c = float(pd.Series(V["ev_ebit"]).astype(float).corr(pd.Series(V["zV_ev_ebit"]).astype(float)))
    k.add("EV/EBIT 이 낮을수록 z 가 높다", c < -0.9, f"corr(ev_ebit, z) = {c:+.3f}")

    z = xsec_z_pct(pd.Series([float(i) for i in range(1, 101)] + [1e9]),
                   pd.Series(["c"] * 101), pct=0.01)
    k.add("극단값이 상위 1% 분위로 클립된다",
          abs(float(z.iloc[-1]) - float(z.iloc[:-1].max())) < 1e-3,
          f"1e9 의 z={float(z.iloc[-1]):.4f} · 나머지 최대 z={float(z.iloc[:-1].max()):.4f} "
          f"(클립 안 하면 z≈9.9)")

    P2 = _sa_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=0.0, cash=0.0, equity=1.0,
                  cfo_ttm=1.0, liabilities=0.0,
                  op_income_ttm=[float(i) for i in range(1, 11)] * 2,
                  sector=["S1"] * 10 + ["S2"] * 10)
    P2.loc[P2["sector"] == "S2", "op_income_ttm"] *= 1000.0
    V2 = axis_V(_sa_cells(P2))
    z1 = np.sort(V2[V2["sector"] == "S1"]["zV_ev_ebit"].astype(float).to_numpy())
    z2 = np.sort(V2[V2["sector"] == "S2"]["zV_ev_ebit"].astype(float).to_numpy())
    k.add("섹터 수준이 1000배 달라도 z 분포가 같다(섹터중립)",
          float(np.nanmax(np.abs(z1 - z2))) < 1e-3,
          f"S1 [{np.nanmin(z1):+.3f},{np.nanmax(z1):+.3f}] · S2 [{np.nanmin(z2):+.3f},{np.nanmax(z2):+.3f}]")

    P3 = _sa_cells(_sa_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=0.0, cash=0.0,
                            equity=[float(100 + i) for i in range(18)] + [-50.0, 0.0],
                            cfo_ttm=1.0, liabilities=0.0, op_income_ttm=50.0, sector="X"))
    zp = axis_V(P3)["zV_pbr"].astype(float)
    worst = float(zp.min())
    k.eq("자기자본 음수 → 횡단면 최하위 z", float(zp.iloc[18]), worst, tol=1e-5)
    k.eq("자기자본 정확히 0 → 횡단면 최하위 z", float(zp.iloc[19]), worst, tol=1e-5)
    k.add("강제 최하위가 실제로 '최하위'다(양수 벌점이 아니다)",
          worst <= float(zp.iloc[:18].min()) + 1e-6,
          f"강제값 {worst:+.4f} · 유효 관측 최소 {float(zp.iloc[:18].min()):+.4f}")
    P4 = P3.copy()
    P4["equity"] = [float(100 + i) for i in range(18)] + [np.nan, np.nan]
    z4 = axis_V(P4)["zV_pbr"]
    k.add("자기자본 결측(모름) → 벌점이 아니라 결측",
          bool(pd.isna(z4.iloc[18])) and bool(pd.isna(z4.iloc[19])),
          f"z={z4.iloc[18]!r}, {z4.iloc[19]!r}")
    return k


@spec_clause("§5.3", "Q축 — gp/a · ROIC 3년 표준편차 · 발생액 · 부채비율 · 주식수 3년 증가율")
def _sc53():
    k = SpecChk()
    k.eq("Q축 지표 구성", tuple(_Q_METRICS),
         ("gp_a", "roic_std3y", "accruals", "debt_ratio", "share_growth3y"))

    P = _sa_cells(_sa_grid(20, ["2020-03-01"], assets=1000.0,
                           gross_profit_ttm=[float(100 + i) for i in range(20)],
                           net_income_ttm=[float(50 + i) for i in range(20)], cfo_ttm=30.0,
                           liabilities=[float(200 + 10 * i) for i in range(20)], equity=400.0,
                           roic_std3y=[0.01 * (i + 1) for i in range(20)],
                           share_growth3y=[0.02 * (i + 1) for i in range(20)],
                           revenue_ttm=np.nan, cogs_ttm=np.nan, sector="X"))
    Q = axis_Q(P)
    r0 = Q.iloc[0]
    k.eq("gp_a = 매출총이익TTM / 자산", float(r0["gp_a"]), 0.1, tol=1e-8)
    k.eq("accruals = (순이익TTM − 영업CF) / 자산", float(r0["accruals"]), 0.02, tol=1e-8)
    k.eq("debt_ratio = 부채총계 / 자기자본", float(r0["debt_ratio"]), 0.5, tol=1e-8)

    # ★★ 이 다섯 줄이 §5.3 의 핵심이다 ★★
    #   '지정된 지표가 존재하는가' 가 아니라 '실제로 z 를 만드는가' 를 본다. 예전에는
    #   발생액·ROIC 표준편차·주식수 증가율 셋이 관측률 100% 에서도 z 산출 0행이었다.
    for label, raw, zc, want_pos in (("gp_a(높을수록 우수)", "gp_a", "zQ_gp_a", True),
                                     ("발생액(낮을수록 우수)", "accruals", "zQ_accruals", False),
                                     ("부채비율(낮을수록 우수)", "debt_ratio", "zQ_debt_ratio", False),
                                     ("ROIC 표준편차(낮을수록 우수)", "roic_std3y", "zQ_roic_std3y", False),
                                     ("주식수 3년 증가율(낮을수록 우수)", "share_growth3y",
                                      "zQ_share_growth3y", False)):
        n_z = int(Q[zc].notna().sum())
        c = float(pd.Series(Q[raw]).astype(float).corr(pd.Series(Q[zc]).astype(float)))
        ok = (n_z == len(Q)) and ((c > 0.9) if want_pos else (c < -0.9))
        k.add(f"방향·산출 — {label}", ok,
              f"raw 관측 {int(Q[raw].notna().sum())}행 → z 산출 {n_z}행 · corr(raw,z) = {c:+.3f}")
    k.eq("Z_Q 행당 가용 지표 수 = 5",
         float(Q[[f"zQ_{m}" for m in _Q_METRICS]].notna().sum(axis=1).mean()), 5.0, tol=1e-9)

    P2 = P.copy()
    P2["gross_profit_ttm"] = np.nan
    P2["revenue_ttm"], P2["cogs_ttm"] = 500.0, 300.0
    k.eq("gp 결측 → (매출−매출원가)/자산 폴백", float(axis_Q(P2)["gp_a"].iloc[0]), 0.2, tol=1e-8)

    kd = pd.date_range("2015-03-31", periods=16, freq="QE")
    shares = pd.DataFrame({"corp_code": ["C1"] * 16, "knowledge_date": kd,
                           "shares_issued": [1e6 * (1.05 ** i) for i in range(16)],
                           "shares_treasury": 0.0})
    fin = pd.DataFrame({"corp_code": ["C1"] * 16, "knowledge_date": kd, "period_end": kd,
                        "equity": 1e9, "liabilities": 1e9, "assets": 2e9, "cash": 1e8,
                        "op_income_ttm": 1e8, "op_income_q": 2.5e7, "pretax_income_ttm": 1e8,
                        "tax_expense_ttm": 2.2e7, "net_income_ttm": 8e7, "cfo_ttm": 9e7,
                        "gross_profit_ttm": 3e8, "revenue_ttm": 1e9, "cogs_ttm": 7e8,
                        "capital_stock": 5e8})
    sg = build_quarterly_fundamentals(fin, shares).dropna(subset=["share_growth3y"])
    k.add("주식수 3년 증가율 산출됨", len(sg) > 0, f"{len(sg)}행")
    if len(sg):
        k.eq("증가율 = 12분기 전 대비 (1.05^12 − 1)", float(sg["share_growth3y"].iloc[0]),
             1.05 ** 12 - 1.0, tol=1e-4)
    n2 = int(build_quarterly_fundamentals(
        fin, shares.drop(index=[4, 5, 6, 7]).reset_index(drop=True))["share_growth3y"].notna().sum())
    k.add("결측 분기가 있으면 '12행 전'을 3년으로 부르지 않는다", n2 < len(sg),
          f"완전 시계열 {len(sg)}건 → 4분기 결측 시 {n2}건")
    return k


@spec_clause("§5.4", "F축 — 외국인·기관 60일 순매수를 '유동주식 시가총액'으로 정규화")
def _sc54():
    k = SpecChk()
    k.eq("FLOW_WINDOW_DAYS", FLOW_WINDOW_DAYS, 60)
    P = _sa_cells(_sa_grid(20, ["2020-03-01"], close=1000.0,
                           shares_issued=[1e6] * 10 + [1e7] * 10, shares_treasury=0.0,
                           mktcap=1e9, sector="X"))
    flows = pd.DataFrame({"code": P["code"], "rebal": P["rebal"], "foreign_net": 1e7,
                          "inst_net": 1e7, "flow_src": "t"})
    F = axis_F(P, flows)
    k.eq("float_cap = (발행주식수 − 자기주식) × 종가", float(F["float_cap"].iloc[0]), 1e9, tol=1.0)
    k.eq("flow_f = 외국인순매수 / 유동시총", float(F["flow_f"].iloc[0]), 0.01, tol=1e-11)
    k.add("같은 금액이라도 유동시총이 작으면 z 가 높다(절대금액 랭킹이 아니다)",
          float(F["Z_F"].iloc[0]) > float(F["Z_F"].iloc[-1]),
          f"유동시총 10억 z={float(F['Z_F'].iloc[0]):+.3f} · "
          f"100억 z={float(F['Z_F'].iloc[-1]):+.3f}")
    P2 = P.copy()
    P2["shares_treasury"] = [2e5] * 10 + [0.0] * 10
    k.eq("자기주식 20% 차감 → 유동시총 8억", float(axis_F(P2, flows)["float_cap"].iloc[0]),
         8e8, tol=1.0)
    F3 = axis_F(P, pd.DataFrame(columns=["code", "rebal", "foreign_net", "inst_net", "flow_src"]))
    k.add("수급 관측이 없으면 Z_F 는 0 이 아니라 결측", bool(F3["Z_F"].isna().all()),
          f"Z_F 결측 {int(F3['Z_F'].isna().sum())}/{len(F3)}행")

    nz = pd.DataFrame({"code": P["code"], "rebal": P["rebal"],
                       "foreign_net": [0.0] * 10 + [1e7] * 10, "inst_net": 0.0, "flow_src": "t"})
    nz.attrs["flow_window"] = int(FLOW_WINDOW_DAYS)
    axis_F(P, nz)
    pre = float(FLOW_NONZERO_RATIO_PREREG)
    f120 = flows.copy()
    f120.attrs["flow_window"] = 120
    axis_F(P, f120)
    k.eq("사전등록 창의 비영 비율", pre, 0.5, tol=1e-6)
    k.add("120일 창 재호출이 사전등록 값을 덮지 않는다",
          abs(float(FLOW_NONZERO_RATIO_PREREG) - pre) < 1e-9,
          f"재호출 전 {pre:.3f} → 후 {float(FLOW_NONZERO_RATIO_PREREG):.3f} "
          f"(현재 창 값 {FLOW_NONZERO_BY_WINDOW.get(120)})")
    return k


@spec_clause("§5.5", "Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F · 사전등록 가중치 · U-200")
def _sc55():
    k = SpecChk()
    k.eq("U200_N", U200_N, 200)
    k.eq("변형 목록", tuple(VARIANTS), ("V", "VQ", "VQF"))
    k.eq("w(V)", tuple(VARIANT_W["V"]), (1.0, 0.0, 0.0))
    k.eq("w(VQ)", tuple(VARIANT_W["VQ"]), (0.5, 0.5, 0.0))
    k.eq("w(VQF)", tuple(VARIANT_W["VQF"]), (0.4, 0.4, 0.2))

    P = _sa_grid(5, ["2020-03-01"], Z_V=[1.0, 2.0, 3.0, 4.0, 5.0], Z_Q=[5.0, 4.0, 3.0, 2.0, 1.0],
                 Z_F=[0.0, 1.0, 0.0, 1.0, 0.0], sector="X")
    for v, (wv, wq, wf) in VARIANT_W.items():
        s = score1(P, v).astype(float).to_numpy()
        want = (wv * P["Z_V"].to_numpy() + wq * P["Z_Q"].to_numpy()
                + wf * P["Z_F"].to_numpy()) / (wv + wq + wf)
        err = float(np.nanmax(np.abs(s - want)))
        k.add(f"Score1[{v}] 산식 일치", err < 1e-5, f"최대 오차 {err:.2e} · 실측 {np.round(s,4).tolist()}")
    P2 = P.copy()
    P2.loc[0, "Z_F"] = np.nan
    k.eq("Z_F 결측 행은 가용 축으로 재정규화(0 채움 아님)",
         float(score1(P2, "VQF").astype(float).iloc[0]), (0.4 * 1.0 + 0.4 * 5.0) / 0.8, tol=1e-5)

    n = 500
    d = build_u200(_sa_grid(n, ["2020-03-01"], Z_V=[float(i) for i in range(n)], Z_Q=0.0,
                            Z_F=0.0, mktcap=1e9, sector="X"), variants=("V",), n=200)
    sel = d[d["u200_V"]]
    k.eq("u200 선정 수", int(len(sel)), 200)
    k.add("선정 = Score1 상위 200", int(sel["Z_V"].min()) == n - 200,
          f"선정 Z_V 최소 {float(sel['Z_V'].min()):.0f} (기대 {n-200})")

    m = 20
    P4 = _sa_grid(m, ["2020-03-01"], Z_V=[1.0] * m, Z_Q=0.0, Z_F=0.0,
                  mktcap=[float(m - i) for i in range(m)], sector="X")
    a = set(build_u200(P4, variants=("V",), n=10).query("u200_V")["code"])
    b = set(build_u200(P4.sample(frac=1.0, random_state=7).reset_index(drop=True),
                       variants=("V",), n=10).query("u200_V")["code"])
    k.add("전원 동점 · 커트라인이 동점을 가로질러도 선정이 같다", a == b,
          f"원순서 {sorted(a)[:4]}… / 섞은 순서 {sorted(b)[:4]}…")
    return k


@spec_clause("§5.6", "필수 보고 — 변형 간 중복률 · 특성 · 리포트 커버리지 · 회전율")
def _sc56():
    k = SpecChk()
    n = 60
    P = build_u200(_sa_grid(n, ["2020-03-01", "2020-06-01"],
                            Z_V=[float(i) for i in range(n)],
                            Z_Q=[float(n - i) for i in range(n)],
                            Z_F=[float((i * 7) % n) for i in range(n)],
                            mktcap=[1e8 * (i + 1) for i in range(n)], adtv=5e8,
                            n_reports=[1 if i % 2 == 0 else 0 for i in range(n)], sector="X"),
                   variants=VARIANTS, n=20)
    res = report_variant_comparison(P, VARIANTS, rep_cov=P[["code", "rebal", "n_reports"]])
    for key in ("overlap", "coverage", "turnover", "sets"):
        k.add(f"보고 항목 '{key}' 산출", key in res and bool(res[key]), f"{key} → {type(res.get(key))}")
    t0 = sorted(res["sets"]["V"])[0]
    a, b = set(res["sets"]["V"][t0]), set(res["sets"]["VQ"][t0])
    k.eq("V∩VQ 중복률 = 교집합/합집합", res["overlap"]["V~VQ"], len(a & b) / len(a | b), tol=0.05)
    k.add("중복률이 [0,1] 범위", all(0.0 <= v <= 1.0 for v in res["overlap"].values()),
          f"overlap={ {kk: round(vv,3) for kk, vv in res['overlap'].items()} }")
    k.add("커버리지가 [0,1] 범위", all(0.0 <= v <= 1.0 for v in res["coverage"].values()),
          f"coverage={ {kk: round(vv,3) for kk, vv in res['coverage'].items()} }")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §6  2차 필터
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§6.1", "배제 플래그 6종 — 임계값 · 근거 없으면 배제하지 않음")
def _sc61():
    k = SpecChk()
    k.eq("RELATED_PARTY_TOPQ", RELATED_PARTY_TOPQ, 0.20)
    k.eq("CONTINGENT_EQ_PP", CONTINGENT_EQ_PP, 0.05)
    k.eq("LAWSUIT_EQ_2ND", LAWSUIT_EQ_2ND, 0.05)
    k.eq("배제 플래그 개수", len(EXCL_FLAGS), 6)

    n = 20
    BASE = dict(equity=1000.0, related_sales_ratio=np.nan, related_sales_ratio_prev=np.nan,
                related_purchase_ratio=np.nan, related_purchase_ratio_prev=np.nan,
                contingent_amt=np.nan, contingent_amt_prev=np.nan, lawsuit_amt=np.nan,
                lawsuit_new=np.nan, lawsuit_filed=np.nan, audit_emphasis=np.nan,
                major_holder_chg=np.nan, cb_issue=np.nan, bw_issue=np.nan, sector="X")
    k.eq("근거가 전부 결측이면 배제 0건",
         int(build_exclusion_flags(_sa_grid(n, ["2020-03-01"], **BASE))["EXCLUDED"].sum()), 0)

    P2 = _sa_grid(n, ["2020-03-01"], **BASE)
    P2["related_sales_ratio_prev"] = 0.10
    P2["related_sales_ratio"] = [0.10 + 0.01 * i for i in range(n)]
    P2["contingent_amt_prev"] = 0.0
    P2["contingent_amt"] = [0.0] * (n - 2) + [50.0, 49.0]        # 5.0%p / 4.9%p
    P2["lawsuit_new"] = [0.0] * (n - 3) + [1.0, 1.0, 0.0]
    P2["lawsuit_amt"] = [0.0] * (n - 3) + [60.0, 40.0, 600.0]    # 6%신규 / 4%신규 / 60%비신규
    P2["audit_emphasis"] = [0.0] * (n - 1) + [1.0]
    P2["major_holder_chg"] = [0.0] * (n - 1) + [1.0]
    P2["cb_issue"] = [0.0] * (n - 1) + [1.0]
    P2["bw_issue"] = 0.0
    E = build_exclusion_flags(P2)

    n_rel = int(E["x_related_up"].sum())
    k.add("① 특수관계자 상승폭 상위 20% ≈ 4/20 종목", 3 <= n_rel <= 5,
          f"발동 {n_rel}건 (상위 20% = 4건 기대)")
    k.add("② 우발부채 5.0%p → 발동 / 4.9%p → 미발동",
          float(E["x_contingent"].iloc[n - 2]) == 1.0 and float(E["x_contingent"].iloc[n - 1]) == 0.0,
          f"5.0%p={E['x_contingent'].iloc[n-2]} · 4.9%p={E['x_contingent'].iloc[n-1]}")
    k.add("③ 신규소송 6% 발동 / 4% 미발동 / 60%(신규 아님) 미발동",
          float(E["x_lawsuit"].iloc[n - 3]) == 1.0 and float(E["x_lawsuit"].iloc[n - 2]) == 0.0
          and float(E["x_lawsuit"].iloc[n - 1]) == 0.0,
          f"{[float(E['x_lawsuit'].iloc[i]) for i in (n-3, n-2, n-1)]}")
    k.eq("④ 감사의견 강조사항 발동", int(E["x_audit"].sum()), 1)
    k.eq("⑤ 최대주주 변경 발동", int(E["x_holder_chg"].sum()), 1)
    k.eq("⑥ CB/BW 발행 발동", int(E["x_cbbw"].sum()), 1)
    k.add("EXCLUDED = 6종 OR",
          bool((E["EXCLUDED"] == (E[EXCL_FLAGS].sum(axis=1) > 0).astype(int)).all()),
          f"배제 {int(E['EXCLUDED'].sum())}/{n}행")
    return k


@spec_clause("§6.2", "ΔTONE 결측 허용 — 관측치 z 를 만든 '뒤에' 0(중립) 주입")
def _sc62():
    k = SpecChk()
    n, obs = 100, [10.0 + i for i in range(12)]
    P = _sa_cells(_sa_grid(n, ["2020-03-01"], dTONE_resid=[np.nan] * (n - 12) + obs, sector="X"))
    mask = col(P, "dTONE_resid").notna()
    z = zscore_observed_then_neutral(P, "dTONE_resid", mask)
    zo = z[mask.to_numpy()].astype(float)
    k.eq("관측치 z 평균 ≈ 0 (관측치만으로 표준화)", float(zo.mean()), 0.0, tol=1e-4)
    k.eq("관측치 z 표준편차 ≈ 1", float(zo.std(ddof=0)), 1.0, tol=1e-3)
    k.add("비관측치는 정확히 0.0", bool((z[~mask.to_numpy()].astype(float) == 0.0).all()),
          f"비관측 {int((~mask).sum())}행 전부 0.0")
    # 검정력 확인 — 0 을 먼저 채우면 관측치 z 가 한쪽으로 쏠린다
    v0 = pd.Series([0.0] * (n - 12) + obs)
    z_wrong = (v0 - v0.mean()) / v0.std(ddof=0)
    k.add("검정력 확인 — 선(先)0채움이면 관측치 z 평균이 크게 양수",
          float(z_wrong[n - 12:].mean()) > 1.0,
          f"올바른 순서 {float(zo.mean()):+.4f} vs 0 먼저 채운 경우 "
          f"{float(z_wrong[n-12:].mean()):+.4f}")

    m = 60
    P2 = _sa_cells(_sa_grid(m, ["2020-03-01"], sector="X",
                            dNONFIN=[float(i % 7) for i in range(m)],
                            dTONE_resid=[float(i) if i < 20 else np.nan for i in range(m)],
                            n_reports=[1 if i < 20 else 0 for i in range(m)],
                            score1_V=[float(m - i) for i in range(m)], u200_V=True, EXCLUDED=0))
    res = verify_missing_tolerance(apply_filter2(P2, "V", n=30), "V")
    rw, ro = res.get("pass_with_report", np.nan), res.get("pass_without_report", np.nan)
    k.add("리포트 없는 종목의 통과율이 보유 종목의 절반 이상",
          np.isfinite(ro) and np.isfinite(rw) and ro >= rw * 0.5,
          f"보유 {100*rw:.1f}% · 없음 {100*ro:.1f}%")
    return k


@spec_clause("§6.3", "Score2 = 2.0·z(ΔNONFIN) + 1.0·z(ΔTONE_resid) − 배제(하드) → 60~80종목")
def _sc63():
    k = SpecChk()
    k.eq("SCORE2_W_NONFIN", SCORE2_W_NONFIN, 2.0)
    k.eq("SCORE2_W_TONE", SCORE2_W_TONE, 1.0)
    k.eq("가중 비율 2:1", SCORE2_W_NONFIN / SCORE2_W_TONE, 2.0)
    k.add("SECOND_N 이 명세 범위 60~80", 60 <= SECOND_N <= 80, f"SECOND_N={SECOND_N}")

    n = 100
    P = _sa_cells(_sa_grid(n, ["2020-03-01"], sector="X", u200_V=True, EXCLUDED=0,
                           dNONFIN=[float(i) for i in range(n)],
                           dTONE_resid=[float(n - i) for i in range(n)], score1_V=0.0))
    d = apply_filter2(P, "V", n=70)
    want = (2.0 * zscore_observed_then_neutral(P, "dNONFIN", col(P, "dNONFIN").notna()).astype(float)
            + 1.0 * zscore_observed_then_neutral(P, "dTONE_resid",
                                                 col(P, "dTONE_resid").notna()).astype(float))
    err = float(np.nanmax(np.abs(d["score2_V"].astype(float).to_numpy() - want.to_numpy())))
    k.add("Score2 산식 일치", err < 1e-5, f"최대 오차 {err:.2e}")
    k.eq("2차 선정 수 = n", int(d["f2_V"].sum()), 70)

    P2 = P.copy()
    P2["EXCLUDED"] = [1 if i >= n - 10 else 0 for i in range(n)]
    picked = apply_filter2(P2, "V", n=70).query("f2_V")
    k.add("배제 종목은 최고점이어도 선정되지 않는다", int(picked["EXCLUDED"].sum()) == 0,
          f"선정 {len(picked)}종목 중 배제 {int(picked['EXCLUDED'].sum())}건")
    P3 = P.copy()
    P3["u200_V"] = [i < 50 for i in range(n)]
    k.eq("U-200 밖은 2차 후보가 아니다", int(apply_filter2(P3, "V", n=70)["f2_V"].sum()), 50)
    return k


@spec_clause("§6.4", "인과 순서 점검 — 보고만 하고 가중치를 자동 조정하지 않는다")
def _sc64():
    k = SpecChk()
    before = (SCORE2_W_NONFIN, SCORE2_W_TONE)
    n = 40
    P = _sa_grid(n, ["2020-03-01"], sector="X", dNONFIN=[float(i) for i in range(n)],
                 dTONE=[float(i) + 0.01 for i in range(n)],
                 dTONE_resid=[float(i) for i in range(n)], n_reports=1)
    rep = pd.DataFrame({"stock_code": P["code"].head(10).to_numpy(),
                        "pub_date": pd.Timestamp("2020-02-01")})
    dis = pd.DataFrame({"code": P["code"].head(10).to_numpy(),
                        "rcept_dt": pd.Timestamp("2020-02-10"), "report_nm": "주요사항보고서"})
    try:
        check_causal_order(rep, dis, P)
        ran, err = True, "ok"
    except Exception as e:                                        # noqa
        ran, err = False, f"{type(e).__name__}: {e}"
    k.add("check_causal_order 가 예외 없이 실행", ran, err)
    k.add("실행 후에도 Score2 가중치가 그대로",
          before == (SCORE2_W_NONFIN, SCORE2_W_TONE),
          f"{before} → {(SCORE2_W_NONFIN, SCORE2_W_TONE)}")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §7  3차 필터 · 포트폴리오
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§7.2", "3-A 규칙 6개 — 사전등록 임계값에서 정확히 발동 · 근거 결측은 제외 안 함")
def _sc72():
    k = SpecChk()
    k.eq("RULE_LAWSUIT_EQ", RULE_LAWSUIT_EQ, 0.10)
    k.eq("RULE_RELATED_SALES", RULE_RELATED_SALES, 0.30)
    k.eq("RULE_MAJOR_HOLDER", RULE_MAJOR_HOLDER, 0.15)
    k.eq("RULE_OP_LOSS_QUARTERS", RULE_OP_LOSS_QUARTERS, 4)
    k.eq("RULE_IMPAIRMENT", RULE_IMPAIRMENT, 0.30)
    k.eq("3-A 규칙 개수", len(RULE_FLAGS), 6)

    BASE = dict(sector="X", equity=2000.0, capital_stock=2000.0, lawsuit_ratio=np.nan,
                related_sales_ratio=np.nan, major_holder_pct=np.nan, audit_emphasis=np.nan,
                op_loss_4q=np.nan)
    k.eq("근거 전부 결측 → 차단 0건",
         int(apply_filter3a(_sa_grid(3, ["2020-03-01"], **BASE))["RULE3A_BLOCK"].sum()), 0)

    def one(**kw):
        return apply_filter3a(_sa_grid(1, ["2020-03-01"], **{**BASE, **kw})).iloc[0]

    k.add("소송 10.0% 미발동 / 10.1% 발동",
          float(one(lawsuit_ratio=0.10)["r_lawsuit"]) == 0.0
          and float(one(lawsuit_ratio=0.101)["r_lawsuit"]) == 1.0, "임계 '초과'만 발동")
    k.add("특수관계자 매출 30.0% 미발동 / 30.1% 발동",
          float(one(related_sales_ratio=0.30)["r_related"]) == 0.0
          and float(one(related_sales_ratio=0.301)["r_related"]) == 1.0, "임계 '초과'만 발동")
    k.add("최대주주 15.0% 미발동 / 14.9% 발동",
          float(one(major_holder_pct=0.15)["r_holder"]) == 0.0
          and float(one(major_holder_pct=0.149)["r_holder"]) == 1.0, "임계 '미만'만 발동")
    k.add("최대주주 지분율 결측 → 미발동(모른다고 버리지 않는다)",
          float(one()["r_holder"]) == 0.0, f"결측→{one()['r_holder']}")
    k.add("감사 강조사항 → 발동", float(one(audit_emphasis=1.0)["r_audit"]) == 1.0)
    k.add("4분기 연속 영업적자 → 발동", float(one(op_loss_4q=1.0)["r_oploss"]) == 1.0)
    r = one(equity=1300.0)
    k.eq("자본잠식률 = (자본금 − 자기자본)/자본금", float(r["impair_ratio"]), 0.35, tol=1e-9)
    k.add("자본잠식률 35% → 발동", float(r["r_impair"]) == 1.0,
          f"impair={float(r['impair_ratio']):.3f}")
    r2 = one(equity=1400.0)
    k.add("자본잠식률 정확히 30% → 미발동", float(r2["r_impair"]) == 0.0,
          f"impair={float(r2['impair_ratio']):.3f} · flag={float(r2['r_impair'])}")
    return k


@spec_clause("§7.4", "최종 20~40종목 · 동일가중 기준 · 하한 미달은 억지로 채우지 않는다")
def _sc74():
    k = SpecChk()
    k.eq("FINAL_N_MIN", FINAL_N_MIN, 20)
    k.eq("FINAL_N", FINAL_N, 30)
    k.eq("FINAL_N_MAX", FINAL_N_MAX, 40)
    k.eq("가중 방식", tuple(WEIGHT_SCHEMES), ("equal", "invvol"))

    n = 100
    P = _sa_grid(n, ["2020-03-01"], sector="X", f2_V=True, RULE3A_BLOCK=0,
                 score2_V=[float(i) for i in range(n)], score1_V=0.0)
    sel = build_final_selection(P, "V", n_final=30)
    k.eq("풀 100 · n_final 30 → 30종목", int(sel.sum()), 30)
    k.add("선정 = Score2 상위 30", float(P.loc[sel, "score2_V"].min()) == float(n - 30),
          f"선정 score2 최소 {float(P.loc[sel,'score2_V'].min()):.0f} (기대 {n-30})")
    k.eq("n_final=100 요청 → 40 으로 클램프", int(build_final_selection(P, "V", n_final=100).sum()), 40)
    k.eq("n_final=5 요청 → 20 으로 클램프", int(build_final_selection(P, "V", n_final=5).sum()), 20)
    P2 = P.copy()
    P2["f2_V"] = [i < 7 for i in range(n)]
    k.eq("풀 7종목 → 7종목 (억지로 20 을 채우지 않는다)",
         int(build_final_selection(P2, "V", n_final=30).sum()), 7)
    P3 = P.copy()
    P3["RULE3A_BLOCK"] = [1 if i >= n - 40 else 0 for i in range(n)]
    k.eq("3-A 차단 종목은 최고점이어도 선정 안 됨",
         int(P3.loc[build_final_selection(P3, "V", n_final=30), "RULE3A_BLOCK"].sum()), 0)
    w = compute_weights(P.head(25), "equal")
    k.add("동일가중 = 1/n · 합 1",
          abs(float(w.sum()) - 1.0) < 1e-12 and float(w.max() - w.min()) < 1e-15,
          f"n=25 · w={float(w.iloc[0]):.6f} (기대 {1/25:.6f})")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §8  비용 · 실험 · 다중검정 · 강건성
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§8.1", "비용 = 증권거래세(이력) + 실측 스프레드/2 · 비용 전/후 병기")
def _sc81():
    k = SpecChk()
    k.eq("기본 비용모형", str(QVF_COST_MODEL), "spec")
    for d, want in (("2016-01-01", 0.0030), ("2019-06-02", 0.0030), ("2019-06-03", 0.0025),
                    ("2021-01-01", 0.0023), ("2023-01-01", 0.0020), ("2024-01-01", 0.0018),
                    ("2025-06-01", 0.0015)):
        k.eq(f"거래세 {d}", qvf_sell_tax(d), want, tol=1e-12)

    days = _sa_bdays("2020-01-02", 300)
    cal = pd.DataFrame([
        {"rebal": pd.Timestamp("2020-03-01"), "signal_date": days[41], "exec_date": days[42]},
        {"rebal": pd.Timestamp("2020-06-01"), "signal_date": days[104], "exec_date": days[105]}])
    P = pd.DataFrame([
        {"code": "A", "rebal": pd.Timestamp("2020-03-01"), "sel": True, "adtv": 1e10,
         "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9},
        {"code": "A", "rebal": pd.Timestamp("2020-06-01"), "sel": False, "adtv": 1e10,
         "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9},
        {"code": "B", "rebal": pd.Timestamp("2020-06-01"), "sel": True, "adtv": 1e10,
         "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9}])
    fwd = pd.DataFrame([{"code": "A", "rebal": pd.Timestamp("2020-03-01"), "fwd_ret": 0.10},
                        {"code": "B", "rebal": pd.Timestamp("2020-06-01"), "fwd_ret": 0.0}])
    bt = run_qbacktest(P, cal, "sel", fwd, apply_costs=True, label="검정",
                       delist={}, cost_model="spec")
    R = bt["returns"].set_index("rebal")
    k.eq("t0 매수 비용 = |Δw|·spread/2", float(R.loc[pd.Timestamp("2020-03-01"), "cost"]),
         0.005, tol=1e-9)
    k.eq("t1 비용 = 매도(스프레드/2 + 세금) + 매수(스프레드/2)",
         float(R.loc[pd.Timestamp("2020-06-01"), "cost"]),
         0.005 + 0.005 + qvf_sell_tax(days[105]), tol=1e-9)
    k.eq("t0 비용 전 수익", float(R.loc[pd.Timestamp("2020-03-01"), "ret_gross"]), 0.10, tol=1e-9)
    k.eq("t0 비용 후 = 비용 전 − 비용", float(R.loc[pd.Timestamp("2020-03-01"), "ret"]),
         0.095, tol=1e-9)
    k.add("비용 전/후가 모두 산출된다(병기 강제)",
          {"ret", "ret_gross", "equity", "equity_gross"} <= set(bt["returns"].columns),
          f"컬럼 {sorted(bt['returns'].columns)}")
    c_ext = float(run_qbacktest(P, cal, "sel", fwd, apply_costs=True, label="검정",
                                delist={}, cost_model="extended")["returns"]["cost"].sum())
    c_spec = float(bt["returns"]["cost"].sum())
    k.add("extended 비용 > spec 비용 (명세 초과분은 기본에 없다)", c_ext > c_spec,
          f"spec {c_spec:.6f} · extended {c_ext:.6f}")
    P3 = P.copy()
    P3["cs_spread"] = 1e-9
    k.eq("스프레드 하한이 적용된다",
         float(run_qbacktest(P3, cal, "sel", fwd, apply_costs=True, label="검정", delist={},
                             cost_model="spec")["returns"].set_index("rebal")
               .loc[pd.Timestamp("2020-03-01"), "cost"]),
         (SLIPPAGE_FLOOR_BPS / 1e4) / 2.0, tol=1e-12)
    k.eq("Q_PER_YEAR (분기 연율화 √4)", Q_PER_YEAR, 4.0)
    return k


@spec_clause("§8.2", "실험 매트릭스 — 주 실험 3 + X1~X4 · X1 에는 3-A·2차가 없다")
def _sc82():
    k = SpecChk()
    n = 120
    P = _sa_cells(_sa_grid(n, ["2020-03-01"], sector="X", Z_V=[float(i) for i in range(n)],
                           Z_Q=0.0, Z_F=0.0, dNONFIN=[float((i * 13) % n) for i in range(n)],
                           dTONE_resid=np.nan, EXCLUDED=0,
                           RULE3A_BLOCK=[1 if i >= n - 10 else 0 for i in range(n)],
                           mktcap=1e9, adtv=1e10, cs_spread=0.01, vol_d=0.02, n_reports=0))
    P = build_u200(P, variants=("V",), n=100)
    sel_x1 = build_final_selection(P, "V", n_final=30, use_rule3a=True, stage="x1")
    n_blk = int(P.loc[sel_x1, "RULE3A_BLOCK"].sum())
    k.add("X1(1차만)에는 3-A 가 적용되지 않는다", n_blk > 0,
          f"X1 선정 30종목 중 3-A 차단 {n_blk}건 (0 이면 X1 이 사실상 '1차+3차')")
    Pf = apply_filter2(P, "V", n=70)
    k.eq("full 에는 3-A 가 적용된다",
         int(Pf.loc[build_final_selection(Pf, "V", n_final=30, use_rule3a=True), "RULE3A_BLOCK"].sum()), 0)
    k.add("X4(3-A 없음)는 차단 종목을 담을 수 있다",
          int(Pf.loc[build_final_selection(Pf, "V", n_final=30, use_rule3a=False),
                     "RULE3A_BLOCK"].sum()) > 0)
    sd2 = float(apply_filter2(P, "V", n=70, use_tone=False, use_nonfin=False,
                              use_exclusion=True)["score2_V"].astype(float).std())
    k.add("X2 는 Score2 가 상수(배제만 작동)", sd2 < 1e-9, f"score2 표준편차 {sd2:.2e}")
    sd3 = float(apply_filter2(P, "V", n=70, use_tone=False, use_nonfin=True,
                              use_exclusion=False)["score2_V"].astype(float).std())
    k.add("X3 는 ΔNONFIN 만으로 Score2 가 변한다", sd3 > 0.1, f"score2 표준편차 {sd3:.4f}")
    return k


@spec_clause("§8.3", "BH-FDR(q=0.10) — 단측 '알파>0' · 차이검정을 같은 패밀리에")
def _sc83():
    k = SpecChk()
    k.eq("BH_FDR_Q", BH_FDR_Q, 0.10)
    p_neg, p_pos = _pval_from_t(-4.0, 40), _pval_from_t(4.0, 40)
    k.add("t = −4 (강한 음의 알파) → p 가 1 에 가깝다(단측)", p_neg > 0.99,
          f"p(t=−4) = {p_neg:.6f} · 양측이면 ≈0.0003 으로 '유의' 오판")
    k.add("t = +4 → p 가 0 에 가깝다", p_pos < 0.001, f"p(t=+4) = {p_pos:.6f}")
    #  m=5, q=0.10 → 임계 0.02/0.04/0.06/0.08/0.10. p(3)=0.04 ≤ 0.06 이 성립하는 최대 rank.
    got = list(map(bool, bh_fdr([0.001, 0.02, 0.04, 0.30, 0.60], q=0.10)))
    k.add("BH 절차 판정", got == [True, True, True, False, False], f"→ {got}")
    got2 = list(map(bool, bh_fdr([0.07, 0.30, 0.50, 0.70, 0.90], q=0.10)))
    k.add("검정력 확인 — 최소 p 가 임계(0.02)를 넘으면 전부 기각", not any(got2), f"→ {got2}")

    EXPERIMENTS.clear()
    for nm, t in (("V-full", 2.5), ("VQ-full", 2.2), ("VQF-full", 2.4), ("X1", 1.8),
                  ("X2", 1.2), ("X3", 0.9), ("X4", 2.0)):
        EXPERIMENTS[nm] = {"name": nm, "net": {}, "gross": {}, "R": None, "t": t,
                           "p": _pval_from_t(t, 40), "n": 40}
    extra = {"name": "VQF-full−VQ-full(차이)", "t": 0.4, "p": _pval_from_t(0.4, 40), "n": 40}
    res = report_bh_fdr(["V-full", "VQ-full", "VQF-full", "X1", "X2", "X3", "X4"],
                        extra_tests=[extra])
    k.eq("패밀리 크기 = 주3 + 어블4 + 차이1", len(res), 8)
    k.add("차이검정이 같은 패밀리에 들어간다", "VQF-full−VQ-full(차이)" in res, f"패밀리={sorted(res)}")

    # ★ hac_tstat 는 (평균, t) 를 준다. 언패킹을 뒤집으면 t 자리에 평균이 들어가
    #   p ≈ 0.48 이 되어 §9-C2 는 영영 통과 못 하고 §10.4 ②는 항상 발동한다.
    m = 40
    idx = pd.date_range("2016-03-01", periods=m, freq="QS")
    base = np.random.default_rng(11).normal(0.02, 0.08, m)
    EXPERIMENTS["AA"] = {"name": "AA", "net": {}, "gross": {}, "t": np.nan, "p": np.nan, "n": m,
                         "R": pd.DataFrame({"rebal": idx, "ret": base + 0.05})}
    EXPERIMENTS["BB"] = {"name": "BB", "net": {}, "gross": {}, "t": np.nan, "p": np.nan, "n": m,
                         "R": pd.DataFrame({"rebal": idx, "ret": base})}
    dt = paired_diff_test("AA", "BB")
    k.eq("차이의 평균 = +0.05", dt["mean"], 0.05, tol=1e-9)
    k.add("t 는 평균이 아니라 평균/HAC표준오차",
          np.isfinite(dt["t"]) and dt["t"] > 5.0 and abs(dt["t"] - dt["mean"]) > 1.0,
          f"t={dt['t']:.3f} · mean={dt['mean']:.5f} · p={dt['p']:.2e} "
          f"(언패킹이 뒤집히면 t=mean=0.05 → p≈0.48)")
    k.add("결정적인 차이는 p 가 0 에 가깝다", dt["p"] < 0.01, f"p={dt['p']:.3e}")
    return k


@spec_clause("§8.4", "강건성 축 — U-200 크기 · 보유종목수 · 수급창 · 리밸 시점 ±5거래일")
def _sc84():
    k = SpecChk()
    k.eq("SENS_U200_SIZES", tuple(SENS_U200_SIZES), (150, 200, 300))
    k.eq("SENS_FINAL_SIZES", tuple(SENS_FINAL_SIZES), (20, 30, 40))
    k.eq("SENS_FLOW_WINDOWS", tuple(SENS_FLOW_WINDOWS), (20, 60, 120))
    k.eq("SENS_REBAL_SHIFTS", tuple(SENS_REBAL_SHIFTS), (-5, 0, 5))
    k.add("기준값이 민감도 축의 가운데에 있다",
          U200_N in SENS_U200_SIZES and FINAL_N in SENS_FINAL_SIZES
          and FLOW_WINDOW_DAYS in SENS_FLOW_WINDOWS,
          f"U200={U200_N} · FINAL={FINAL_N} · FLOW={FLOW_WINDOW_DAYS}")
    k.eq("INVVOL_WINDOW_DAYS", INVVOL_WINDOW_DAYS, 120)

    n = 400
    px = _sa_prices([f"{i:06d}" for i in range(1, 6)], _sa_bdays("2019-01-02", 400))
    set_trading_days(px)
    cal = qvf_rebal_calendar(px, "2019-06-01", "2020-06-30")
    reb = [str(t.date()) for t in as_ts_series(cal["rebal"])]
    P = _sa_cells(_sa_grid(n, reb, sector="X", Z_V=[float(i) for i in range(n)], Z_Q=0.0,
                           Z_F=0.0, dNONFIN=[float((i * 7) % n) for i in range(n)],
                           dTONE_resid=np.nan, EXCLUDED=0, RULE3A_BLOCK=0, mktcap=1e9,
                           adtv=1e10, cs_spread=0.01, vol_d=0.02))
    P = P.drop(columns=["signal_date", "exec_date"]).merge(
        cal[["rebal", "signal_date", "exec_date"]], on="rebal", how="left")
    fwd = P[["code", "rebal"]].copy()
    fwd["fwd_ret"] = np.random.default_rng(0).normal(0.01, 0.10, len(fwd))
    s = {}
    for n2 in SENS_U200_SIZES:
        s[n2] = qperf_stats(run_experiment(P, cal, fwd, "V", u200_n=n2,
                                           label=f"U{n2}")["returns"]).get("CAGR", np.nan)
    k.add("U-200 크기를 바꾸면 성과가 실제로 달라진다(축이 살아 있다)",
          len({round(v, 8) for v in s.values()}) == len(s),
          " · ".join(f"U200={a}: CAGR {b*100:+.2f}%" for a, b in s.items()))
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §9 · §10
# ════════════════════════════════════════════════════════════════════════════════════════════
@spec_clause("§9", "수급 축 채택 C1~C5 — 판정불가를 충족으로 세지 않는다")
def _sc9():
    k = SpecChk()
    EXPERIMENTS.clear()
    EXPERIMENTS["VQ-full"] = {"name": "VQ-full", "net": {"Sharpe": 0.50}, "gross": {},
                              "R": None, "t": 1.0, "p": 0.2, "n": 40}
    EXPERIMENTS["VQF-full"] = {"name": "VQF-full", "net": {"Sharpe": 0.80}, "gross": {},
                               "R": None, "t": 1.5, "p": 0.1, "n": 40}
    EXPERIMENTS["VQF-full−VQ-full(차이)"] = {"name": "VQF-full−VQ-full(차이)", "net": {},
                                             "gross": {}, "R": None, "t": 2.0, "p": 0.03, "n": 40}
    cmp_res = {"overlap": {"VQ~VQF": 0.60}, "coverage": {"VQ": 0.40, "VQF": 0.45}}
    fdr = {"VQF-full−VQ-full(차이)": True, "VQF-full": True}
    globals()["PHASE0_FLOW_OK"] = True
    globals()["FLOW_NONZERO_RATIO_PREREG"] = 0.40
    v = report_flow_verdict(cmp_res, fdr_pass=fdr)
    k.add("전부 충족 시 C1~C5 True", all(v[c] is True for c in ("C1", "C2", "C3", "C4", "C5")),
          f"{ {c: v[c] for c in ('C1','C2','C3','C4','C5')} }")
    k.add("adopt_flow True", v["adopt_flow"] is True)

    v2 = report_flow_verdict(cmp_res, fdr_pass={"VQF-full": True})
    k.add("차이검정이 패밀리에 없으면 C2 는 '판정 불가'(자기 유의성으로 대체하지 않는다)",
          v2["C2"] is None, f"C2={v2['C2']}")
    k.add("판정 불가가 있으면 채택 권고가 아니다", v2["adopt_flow"] is False)
    v3 = report_flow_verdict({"overlap": {"VQ~VQF": 0.85},
                              "coverage": {"VQ": 0.4, "VQF": 0.45}}, fdr_pass=fdr)
    k.add("중복률 0.85 → C3 미충족(< 0.85 여야 한다)", v3["C3"] is False, f"C3={v3['C3']}")
    globals()["FLOW_NONZERO_RATIO_PREREG"] = 0.20
    globals()["FLOW_NONZERO_RATIO"] = 0.90
    k.add("C4 는 사전등록 창의 값을 쓴다 — 강건성 실행값(0.90)을 읽지 않는다",
          report_flow_verdict(cmp_res, fdr_pass=fdr)["C4"] is False,
          "사전등록 0.20 / 전역 폴백 0.90")
    globals()["FLOW_NONZERO_RATIO_PREREG"] = 0.40
    v5 = report_flow_verdict({"overlap": {"VQ~VQF": 0.6},
                              "coverage": {"VQ": 0.40, "VQF": 0.55}}, fdr_pass=fdr)
    k.add("커버리지 격차 +15%p → C5 미충족", v5["C5"] is False, f"C5={v5['C5']}")
    globals()["PHASE0_FLOW_OK"] = False
    v6 = report_flow_verdict(cmp_res, fdr_pass=fdr)
    k.add("flow_cov 미달 → C1·C2 판정 불가", v6["C1"] is None and v6["C2"] is None,
          f"C1={v6['C1']} C2={v6['C2']}")
    return k


@spec_clause("§10.4", "사전등록 폐기조건 ①②③ — 충족 시 실제로 멈춘다")
def _sc104():
    k = SpecChk()
    k.add("STOP_ON_KILL_CRITERIA 기본 True", STOP_ON_KILL_CRITERIA is True)

    def setup(cagrs, mdd_full, mdd_x1, diff_mean, diff_sd, n=40):
        EXPERIMENTS.clear()
        rng = np.random.default_rng(3)
        base = rng.normal(0.02, 0.08, n)
        idx = pd.date_range("2016-03-01", periods=n, freq="QS")
        for nm, c in cagrs.items():
            EXPERIMENTS[nm] = {"name": nm, "gross": {}, "t": 1.0, "p": 0.2, "n": n,
                               "R": pd.DataFrame({"rebal": idx, "ret": base}),
                               "net": {"CAGR": c, "Sharpe": 0.5,
                                       "MDD": mdd_full if nm == "VQ-full" else np.nan}}
        EXPERIMENTS["X1"] = {"name": "X1", "gross": {}, "t": 1.0, "p": 0.2, "n": n,
                             "R": pd.DataFrame({"rebal": idx,
                                                "ret": base - diff_mean + rng.normal(0, diff_sd, n)}),
                             "net": {"CAGR": 0.05, "MDD": mdd_x1, "Sharpe": 0.4}}

    MAIN = ["V-full", "VQ-full", "VQF-full"]
    old_stop = STOP_ON_KILL_CRITERIA
    try:
        globals()["STOP_ON_KILL_CRITERIA"] = False
        setup({"V-full": -0.03, "VQ-full": -0.02, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
        k.add("① 세 변형 모두 음의 CAGR → 충족",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["all_alpha_dead"] is True)
        setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
        k.add("① 하나라도 양의 CAGR → 미충족",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["all_alpha_dead"] is False)
        setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.40, -0.50, 0.0005, 0.05)
        k.add("② 차이가 0 에 가까우면 '미미'로 판정",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["funnel_worthless"] is True)
        setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.40, -0.50, 0.05, 0.01)
        k.add("② 차이가 뚜렷하면 미충족(검정력 확인)",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["funnel_worthless"] is False)
        setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.50, -0.40, 0.05, 0.01)
        k.add("③ full MDD(−50%)가 X1(−40%)보다 깊다 → 개선 실패",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["exclusion_no_mdd_help"] is True)
        setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.30, -0.40, 0.05, 0.01)
        k.add("③ full MDD(−30%)가 X1(−40%)보다 얕다 → 개선 있음",
              report_preregistration_kill(MAIN, "VQ-full", "X1")["exclusion_no_mdd_help"] is False)

        globals()["STOP_ON_KILL_CRITERIA"] = True
        setup({"V-full": -0.03, "VQ-full": -0.02, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
        halted = False
        try:
            report_preregistration_kill(MAIN, "VQ-full", "X1")
        except KillCriteria:
            halted = True
        k.add("폐기조건 충족 시 KillCriteria 로 중단(편입 종목표를 출력하지 않는다)", halted)
    finally:
        globals()["STOP_ON_KILL_CRITERIA"] = old_stop
    return k


@spec_clause("§10.1", "임의선택 원장 · §10.2 귀속 · §10.3 산출물 — 보고 함수가 실제로 돈다")
def _sc101():
    k = SpecChk()
    for fname in ("report_discretion_ledger", "report_cell_ladder", "report_dataflow_map"):
        try:
            globals()[fname]()
            ok, err = True, "ok"
        except Exception as e:                                    # noqa
            ok, err = False, f"{type(e).__name__}: {e}"
        k.add(f"{fname}() 실행", ok, err)
    n = 40
    P = _sa_grid(n, ["2020-03-01"], sector="X", mktcap=1e9, adtv=5e8,
                 score1_V=[float(i) for i in range(n)], score2_V=[float(i) for i in range(n)],
                 dNONFIN=1.0, dTONE_resid=0.5, n_reports=1,
                 _sel=[i >= n - 30 for i in range(n)])
    sec = pd.DataFrame({"code": P["code"].unique(), "name": "검정종목"})
    try:
        k.eq("최종 편입 종목표 행수", len(report_final_holdings(P, "V", "_sel", sec)), 30)
    except Exception as e:                                        # noqa
        k.add("최종 편입 종목표 산출", False, f"{type(e).__name__}: {e}")
    return k


@spec_clause("§구조", "미정의 전역 참조 · 성과지표 키 오타 — 조용히 NameError/nan 이 되는 부류")
def _scstruct():
    """조립기의 '정의 전 참조' 검사는 최상위만 본다. 함수 '본문 안'의 미정의 전역은
    그 분기가 실행될 때만 NameError 가 된다(실제로 ADTV_MIN_KRW 가 그랬다).
    소스 파일이 없어도(원셀 실행) 돌아야 하므로 이미 정의된 코드객체를 직접 걷는다."""
    import builtins as _bi
    import dis as _dis

    k = SpecChk()
    g = globals()
    # ★ 우리 파일에서 컴파일된 코드객체만 본다. globals() 에는 stdlib 클래스(ProcessPoolExecutor
    #   등)도 들어 있어 그 메서드까지 걷으면 남의 모듈 전역이 '미정의'로 잡힌다(오탐).
    own = _scstruct.__code__.co_filename
    seen: set = set()
    undefined: Dict[str, str] = {}
    consts: set = set()

    def walk(co, where: str):
        if id(co) in seen:
            return
        seen.add(id(co))
        for ins in _dis.get_instructions(co):
            if ins.opname in ("LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"):
                nm = ins.argval
                if (isinstance(nm, str) and not nm.startswith("__")
                        and nm not in g and not hasattr(_bi, nm)):
                    undefined.setdefault(nm, where)
        for c in co.co_consts:
            if isinstance(c, str):
                consts.add(c)
            elif hasattr(c, "co_code"):
                walk(c, getattr(c, "co_qualname", None) or getattr(c, "co_name", where))

    for name, obj in list(g.items()):
        code = getattr(obj, "__code__", None)
        if code is not None:
            if code.co_filename == own:
                walk(code, name)
        elif isinstance(obj, type):
            for _mn, _m in list(vars(obj).items()):
                mc = getattr(_m, "__code__", None)
                if mc is not None and mc.co_filename == own:
                    walk(mc, f"{name}.{_mn}")
    k.add("함수 본문에서 참조하는 전역이 모두 정의되어 있다", not undefined,
          "미정의 전역 없음" if not undefined
          else " · ".join(f"{n} (in {w})" for n, w in sorted(undefined.items())[:12]))

    stats_keys = set(qperf_stats(pd.DataFrame({"ret": [0.01] * 20, "n": [10] * 20,
                                               "turnover": [0.1] * 20, "cost": [0.001] * 20})))
    lower = {kk.lower() for kk in stats_keys if kk.isascii()}
    bad = sorted(c for c in consts
                 if c.isascii() and c.lower() in lower and c not in stats_keys)
    k.add("성과지표를 잘못된 키(대소문자)로 조회하지 않는다", not bad,
          f"성과 키 집합에 없는 문자열 상수 {bad}" if bad
          else f"이상 없음 (키: {sorted(kk for kk in stats_keys if kk.isascii())})")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  실행 — 전역 스냅샷/복원으로 파이프라인을 오염시키지 않는다
# ════════════════════════════════════════════════════════════════════════════════════════════
#  검정이 만지는 전역 목록. 여기 빠진 이름이 있으면 검증층이 본 실행의 입력을 바꾼다.
_SPEC_GUARDED = ("U1000_N", "U1000_RANK_BEFORE_FILTER", "QVF_TRADING_DAYS",
                 "FLOW_NONZERO_RATIO", "FLOW_NONZERO_RATIO_PREREG", "FLOW_NONZERO_BY_WINDOW",
                 "PHASE0_FLOW_OK", "QVF_DELIST_MAP", "STOP_ON_KILL_CRITERIA",
                 "QVF_REBAL_SHIFT_DAYS", "SCORE2_W_NONFIN", "SCORE2_W_TONE")


def _spec_snapshot() -> dict:
    import copy as _copy
    snap = {}
    for nm in _SPEC_GUARDED:
        if nm in globals():
            v = globals()[nm]
            try:
                snap[nm] = _copy.deepcopy(v)
            except Exception:                                     # noqa
                snap[nm] = v
    snap["_EXPERIMENTS"] = OrderedDict(EXPERIMENTS)
    snap["_ROBUST"] = list(ROBUST_RESULTS)
    snap["_LADDER"] = dict(CELL_LADDER_USAGE)
    return snap


def _spec_restore(snap: dict) -> List[str]:
    """복원하고, 복원되지 않은 이름을 돌려준다(빈 리스트여야 정상)."""
    for nm in _SPEC_GUARDED:
        if nm in snap:
            globals()[nm] = snap[nm]
    EXPERIMENTS.clear()
    EXPERIMENTS.update(snap.get("_EXPERIMENTS") or {})
    ROBUST_RESULTS[:] = snap.get("_ROBUST") or []
    CELL_LADDER_USAGE.clear()
    CELL_LADDER_USAGE.update(snap.get("_LADDER") or {})
    bad = []
    for nm in _SPEC_GUARDED:
        if nm not in snap:
            continue
        a, b = snap[nm], globals().get(nm)
        try:
            if isinstance(a, np.ndarray):
                same = bool(np.array_equal(a, b))
            elif isinstance(a, float) and isinstance(b, float):
                # NaN == NaN 은 False 다. 사전등록 창 비율 등은 초기값이 nan 이므로
                # 그대로 비교하면 '복원 실패'로 오판한다.
                same = (a == b) or (not np.isfinite(a) and not np.isfinite(b))
            else:
                same = bool(a == b)
        except Exception:                                         # noqa
            same = True
        if not same:
            bad.append(nm)
    return bad


def run_spec_audit(strict: bool = True, only: Optional[Sequence[str]] = None) -> bool:
    """§3.1~§10.4 전수조사. strict 면 실패 시 ContractViolation 을 던진다."""
    LOG.banner("명세 전수조사 (§3.1 ~ §10.4)",
               "조항마다 정답을 아는 합성 입력을 만들어 실제 함수를 돌리고 숫자로 판정한다")
    sel = [(cid, t, fn) for cid, t, fn in SPEC_CASES
           if not only or any(cid.lstrip("§").startswith(str(w).lstrip("§")) for w in only)]
    snap = _spec_snapshot()
    keep = LOG.min
    rows, failures, n_sub, n_sub_bad = [], [], 0, 0
    try:
        LOG.min = LOG.LEVELS["WARN"]        # 검정 중 본문 로그는 억제(판정표만 남긴다)
        for cid, title, fn in sel:
            try:
                chk = fn()
                ok = chk.passed
                n_sub += len(chk.rows)
                bad = [(n, e) for n, o, e in chk.rows if not o]
                n_sub_bad += len(bad)
                detail = ("전 항목 통과" if ok else bad[0][0])
                if not ok:
                    failures += [f"{cid} · {n} — {e}" for n, e in bad]
            except Exception as e:                                # noqa
                ok, detail = False, f"{type(e).__name__}: {e}"
                failures.append(f"{cid} · 실행 오류 — {detail}")
                if VERBOSE:
                    LOG.min = keep
                    LOG.debug(traceback.format_exc())
                    LOG.min = LOG.LEVELS["WARN"]
            rows.append([cid, _trunc(title, 58), "✔" if ok else "✘", _trunc(detail, 40)])
    finally:
        LOG.min = keep
        leaked = _spec_restore(snap)

    LOG.table(rows, ["조항", "내용", "판정", "비고"], ["l", "l", "c", "l"], maxw=60,
              title=f"명세 전수조사 — 조항 {len(sel)}개 · 소검정 {n_sub}개")
    k_ok = sum(1 for r in rows if r[2] == "✔")
    LOG.add_pipe = getattr(LOG, "add_pipe", None)
    if leaked:
        LOG.warn(f"검정층이 전역을 복원하지 못했습니다: {leaked} — 이 값들이 본 실행의 입력을 "
                 f"바꿉니다. 전수조사 자체가 오염원이 되므로 반드시 고쳐야 합니다.")
        failures.append(f"전역 복원 실패: {leaked}")
    if failures:
        LOG.table([[_trunc(f, 110)] for f in failures[:20]], ["실패한 소검정"], ["l"], maxw=112,
                  title=f"실패 상세 (소검정 {n_sub_bad}건)")
        msg = (f"명세 전수조사 실패 — 조항 {len(sel)-k_ok}/{len(sel)}개, 소검정 {n_sub_bad}/{n_sub}개.\n"
               f"  이 층은 '숫자가 명세와 같은가'를 봅니다. 계약(Q1~Q14)이 통과해도 여기서 걸리면\n"
               f"  선정·판정 결과가 명세와 다르다는 뜻이므로 수집을 시작하지 않습니다.")
        if strict:
            raise ContractViolation(msg)
        LOG.warn(msg)
        return False
    LOG.ok(f"명세 전수조사 통과 — 조항 {k_ok}/{len(sel)} · 소검정 {n_sub}개 · "
           f"전역 복원 확인 완료")
    PIPE.note(f"명세 전수조사 {k_ok}조항/{n_sub}소검정 통과")
    return True
