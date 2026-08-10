#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""명세 전수조사 — strategies/qvf_funnel_v1.py 의 §3.1~§10.4 를 '실행'으로 검정한다.

읽기로는 잡히지 않는다는 것이 이 전략의 역사다(TONE 사례: CV 0.77 인데 진짜부호 상관 −0.008).
그래서 각 조항마다 ① 정답을 아는 합성 입력을 만들고 ② 조립본의 실제 함수를 돌리고
③ 숫자로 PASS/FAIL 을 판정한다. '이 검정이 실패하는 입력을 만들 수 있는가' 를 먼저 확인했다 —
검정력 0 인 검정은 통과해도 아무것도 보장하지 않는다(계약 8개가 그랬다).

    python3 tools/audit_spec_qvf.py            # 전체
    python3 tools/audit_spec_qvf.py 5 6        # §5·§6 만
"""
from __future__ import annotations

import os
import re
import sys
import types
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "strategies", "qvf_funnel_v1.py")


# ════════════════════════════════════════════════════════════════════════════════════════════
#  조립본 로딩 — main() 을 돌리지 않고 모듈로만 올린다
# ════════════════════════════════════════════════════════════════════════════════════════════
def load_module(path: str = TARGET) -> Dict[str, Any]:
    src = open(path, encoding="utf-8").read()
    src = re.sub(r'^RUN_MODE\s*=\s*"FULL"', 'RUN_MODE = "SMOKE"', src, flags=re.M)
    mod = types.ModuleType("qvfmod")
    sys.modules["qvfmod"] = mod
    g = mod.__dict__
    g["__name__"] = "qvfmod"
    exec(compile(src, os.path.basename(path), "exec"), g)
    g["LOG"].min = 99                                   # 로그 억제(검정 출력만 남긴다)

    class _Vault:                                       # VAULT 스텁 — 디스크를 건드리지 않는다
        root = ""
        def put_table(self, *a, **k): return None
        def get_table(self, *a, **k): return None
        def flush(self, *a, **k): return None
        def compact(self, *a, **k): return None
    g["VAULT"] = _Vault()
    return g


G: Dict[str, Any] = {}
pd = np = None                                          # load 후 채운다


# ════════════════════════════════════════════════════════════════════════════════════════════
#  검정 등록
# ════════════════════════════════════════════════════════════════════════════════════════════
CASES: List[Tuple[str, str, Callable]] = []


def clause(cid: str, title: str):
    def deco(fn):
        CASES.append((cid, title, fn))
        return fn
    return deco


class Chk:
    """한 조항 안의 소검정 모음. ok(...) / fail 은 전부 '숫자'를 남긴다."""

    def __init__(self):
        self.rows: List[Tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, evidence: str):
        self.rows.append((name, bool(ok), evidence))
        return ok

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


# ════════════════════════════════════════════════════════════════════════════════════════════
#  합성 입력 헬퍼
# ════════════════════════════════════════════════════════════════════════════════════════════
def mk_grid(n_codes: int, rebals: List[str], **cols) -> "pd.DataFrame":
    """(code × rebal) 격자. 값은 스칼라 또는 길이 n_codes 리스트."""
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


def add_cells(P: "pd.DataFrame", sector: Optional[List[str]] = None) -> "pd.DataFrame":
    """build_sector_cells 와 같은 규약의 셀 컬럼을 붙인다(섹터 미지정이면 단일 셀)."""
    d = P.copy()
    if "sector" not in d.columns:
        d["sector"] = sector if sector is not None else "테스트섹터"
    ym = as_ts_s(d["rebal"]).dt.strftime("%Y%m")
    d["cell"] = ym + "|" + d["sector"].astype(str)
    d["cell_l2"] = ym + "|" + d["sector"].astype(str).str.slice(0, 4)
    d["cell_l3"] = ym + "|ALL"
    return d


def as_ts_s(s):
    return G["as_ts_series"](s)


def mk_prices(codes: List[str], dates, amount=1e9, close=1000.0,
              high=None, low=None, open_=None, skip: Optional[Dict[str, set]] = None):
    """일봉 패널. skip[code] 에 든 날짜는 행 자체를 만들지 않는다(소스 누락 재현)."""
    rows = []
    for c in codes:
        for i, d in enumerate(dates):
            if skip and c in skip and i in skip[c]:
                continue
            cl = close[c][i] if isinstance(close, dict) else close
            am = amount[c] if isinstance(amount, dict) else amount
            rows.append({"code": c, "date": pd.Timestamp(d),
                         "open": open_ if open_ is not None else cl,
                         "high": high if high is not None else cl * 1.01,
                         "low": low if low is not None else cl * 0.99,
                         "close": cl, "amount": am, "volume": am / max(cl, 1)})
    return pd.DataFrame(rows)


def bdays(start: str, n: int):
    return list(pd.bdate_range(start, periods=n))


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §3  유니버스
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§3.1", "U-1000 = PIT 시총 '하위' N (폐지종목 포함 · 해석 A/B 가 실제로 다른가)")
def c31():
    k = Chk()
    k.eq("U1000_N 상수", G["U1000_N"], 1000)

    n = 300
    # 시총 1..300 (작을수록 하위). 전 종목 적격.
    Gg = mk_grid(n, ["2020-03-01"], mktcap=[float(i) * 1e8 for i in range(1, n + 1)],
                 adtv=5e8, equity=1e9, excl_struct="", sector="X")
    U = G["select_u1000"](Gg)
    picked = set(U["code"])
    want = {f"{i:06d}" for i in range(1, G["U1000_N"] + 1)} & set(Gg["code"])
    k.eq("적격 300종목 전부 선정(N<1000)", len(picked), 300)

    # 하위 절단이 실제로 '작은 쪽' 인가 — N 을 50 으로 낮춰 확인
    old_n = G["U1000_N"]
    try:
        G["U1000_N"] = 50
        U2 = G["select_u1000"](Gg)
        got = sorted(int(c) for c in U2["code"])
        k.eq("N=50 선정 수", len(got), 50)
        k.add("선정 = 시총 최소 50종목", got == list(range(1, 51)),
              f"선정 코드 min={got[0]} max={got[-1]} (기대 1..50)")
    finally:
        G["U1000_N"] = old_n

    # 폐지 종목이 격자에 있으면 U-1000 에 남는가 (select_u1000 은 폐지로 거르지 않는다)
    k.add("폐지 여부는 select_u1000 의 게이트가 아니다",
          "delisting_date" not in G["select_u1000"].__code__.co_names,
          "select_u1000 은 상장/폐지 컬럼을 참조하지 않는다(폐지 반영은 Universe.at 단계)")

    # 해석 A(게이트→하위N) vs B(하위N→게이트) 가 정말 다른 모집단인가
    #   하위 40 종목의 유동성을 죽이면, A 는 41~90 으로 채워 50종목, B 는 10종목이 된다.
    Gb = Gg.copy()
    Gb.loc[Gb["code"].isin([f"{i:06d}" for i in range(1, 41)]), "adtv"] = 1e6
    try:
        G["U1000_N"] = 50
        G["U1000_RANK_BEFORE_FILTER"] = False
        nA = len(G["select_u1000"](Gb))
        G["U1000_RANK_BEFORE_FILTER"] = True
        nB = len(G["select_u1000"](Gb))
    finally:
        G["U1000_RANK_BEFORE_FILTER"] = False
        G["U1000_N"] = old_n
    k.eq("해석 A(기본): 게이트 통과분에서 하위 50", nA, 50)
    k.eq("해석 B: 하위 50 을 먼저 뽑고 게이트", nB, 10)
    k.add("기본값은 해석 A", G["U1000_RANK_BEFORE_FILTER"] is False,
          f"U1000_RANK_BEFORE_FILTER={G['U1000_RANK_BEFORE_FILTER']}")
    return k


@clause("§3.2", "유동성 게이트 — 직전 60거래일 평균 거래대금 ≥ 1억원")
def c32():
    k = Chk()
    k.eq("ADTV_WINDOW_DAYS", G["ADTV_WINDOW_DAYS"], 60)
    k.eq("MIN_ADTV_KRW", G["MIN_ADTV_KRW"], 100_000_000)

    # ── 게이트 경계: 0.999억 탈락 / 1.000억 통과
    Gg = mk_grid(3, ["2020-03-01"], mktcap=1e9,
                 adtv=[99_999_999.0, 100_000_000.0, 100_000_001.0],
                 equity=1e9, excl_struct="", sector="X")
    U = G["select_u1000"](Gg)
    sel = set(U["code"])
    k.add("adtv = 99,999,999 → 탈락", "000001" not in sel, f"선정={sorted(sel)}")
    k.add("adtv = 100,000,000 → 통과", "000002" in sel, f"선정={sorted(sel)}")

    # ── '그 종목이 가진 60개 행'이 아니라 '시장 60거래일' 인가
    #    A: 60일 전부 거래, 금액 2억  → ADTV = 2억
    #    B: 60일 중 20일만 행이 존재, 금액 3억 → 시장격자 기준 ADTV = 3억×20/60 = 1억
    days = bdays("2020-01-01", 80)
    skipB = {"000002": set(i for i in range(80) if i % 3 != 0)}   # 3일에 1일만 거래
    px = pd.concat([
        mk_prices(["000001"], days, amount=2e8, close=1000.0),
        mk_prices(["000002"], days, amount=3e8, close=1000.0, skip=skipB),
    ], ignore_index=True)
    cal = pd.DataFrame([{"rebal": pd.Timestamp("2020-04-01"),
                         "signal_date": days[79], "exec_date": days[79]}])
    A = G["build_adtv_panel"](cal, px, window=60)
    a = dict(zip(A["code"].astype(str), pd.to_numeric(A["adtv"])))
    k.eq("전일 거래 종목 ADTV", a.get("000001", float("nan")), 2e8, tol=1e3)
    got_b = a.get("000002", float("nan"))
    k.add("결측일이 있는 종목은 시장격자 기준(0 채움)으로 희석된다",
          abs(got_b - 1.0e8) <= 6e6,
          f"실측 {got_b:,.0f} · 시장격자 기대 ≈100,000,000 · "
          f"'자기 행 60개' 해석이면 300,000,000 (3배 과대)")

    # ── 창 미충족(60일 미만)은 결측이어야 한다
    days2 = bdays("2020-01-01", 40)
    px2 = mk_prices(["000009"], days2, amount=5e8)
    cal2 = pd.DataFrame([{"rebal": pd.Timestamp("2020-03-01"),
                          "signal_date": days2[39], "exec_date": days2[39]}])
    A2 = G["build_adtv_panel"](cal2, px2, window=60)
    k.eq("거래일 40일뿐이면 ADTV 산출 없음(min_periods=60)", len(A2), 0)
    return k


@clause("§3.3", "구조적 제외(우선주·스팩·리츠·ETF) · 상장 12개월 미만 · 완전자본잠식")
def c33():
    k = Chk()
    k.eq("SEASONING_DAYS", G["SEASONING_DAYS"], 250)
    ce = G["classify_exclusion"]

    # ★ 코드 6번째 자리가 '0' 이 아니면 코드 규칙만으로 우선주 판정이 난다. 이름 규칙을
    #   검정하려면 반드시 '…0' 코드를 써야 한다 — 아니면 이름 규칙에 검정력이 0 이다.
    pos = [("005935", "삼성전자우", "우선주"),          # 코드 규칙 (6번째='5')
           ("000000", "삼성전자우선주", "우선주"),      # 이름 규칙 (코드는 보통주)
           ("000010", "케이비제20호스팩", "스팩"),
           ("000020", "이지스밸류리츠", "리츠"),
           ("000030", "KODEX 200", "ETF/ETN"),
           ("000040", "TIGER 2차전지", "ETF/ETN"),
           ("000050", "KODEX 레버리지", "ETF/ETN")]
    for code, name, why in pos:
        got = ce(code, name)
        k.add(f"제외되어야: {name}", got == why, f"판정='{got}' (기대 '{why}')")

    # 오탐 방지 — 실존 소형주가 이름 규칙으로 영구 삭제되면 시점불변 편향이다
    neg = [("100130", "동국S&C"), ("115960", "연우"), ("047310", "파워로직스"),
           ("037400", "우리조명"), ("032190", "다우데이타"), ("006800", "미래에셋증권")]
    for code, name in neg:
        got = ce(code, name)
        k.add(f"제외되면 안 됨: {name}", got == "", f"판정='{got}'")

    # ── 시즈닝: 상장 250거래일 미만은 유니버스에 없다
    days = bdays("2018-01-01", 800)
    px = mk_prices(["000010"], days, amount=1e9)
    sec = pd.DataFrame([
        {"code": "OLD001", "name": "구상장", "market": "KOSPI", "industry": "X",
         "listing_date": pd.Timestamp("2010-01-01"), "delisting_date": pd.NaT},
        {"code": "NEW001", "name": "신규상장", "market": "KOSDAQ", "industry": "X",
         "listing_date": days[700], "delisting_date": pd.NaT},
        {"code": "MID001", "name": "중간상장", "market": "KOSDAQ", "industry": "X",
         "listing_date": days[100], "delisting_date": pd.NaT},
        {"code": "DEL001", "name": "폐지예정", "market": "KOSDAQ", "industry": "X",
         "listing_date": pd.Timestamp("2010-01-01"), "delisting_date": days[500]},
    ])
    uni = G["Universe"](sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    at = set(uni.at(days[600]))
    k.add("패널 이전 상장 종목은 포함", "OLD001" in at, f"at()={sorted(at)}")
    k.add("상장 후 250거래일 미만(NEW001, 상장 −100일)은 제외", "NEW001" not in at,
          f"at()={sorted(at)}")
    k.add("상장 후 500거래일(MID001)은 포함", "MID001" in at, f"at()={sorted(at)}")
    k.add("이미 폐지된 종목(DEL001)은 제외", "DEL001" not in at, f"at()={sorted(at)}")
    at_before = set(uni.at(days[400]))
    k.add("폐지 전 시점에는 폐지예정 종목이 포함(생존자편향 방지)",
          "DEL001" in at_before, f"at(폐지 100거래일 전)={sorted(at_before)}")

    # ── 완전자본잠식: equity ≤ 0 은 제외, equity 결측은 '모름'이라 제외하지 않는다
    Gg = mk_grid(3, ["2020-03-01"], mktcap=[1e8, 2e8, 3e8], adtv=5e8,
                 equity=[1e9, 0.0, float("nan")], excl_struct="", sector="X")
    U = G["select_u1000"](Gg)
    sel = set(U["code"])
    k.add("equity > 0 → 포함", "000001" in sel, f"선정={sorted(sel)}")
    k.add("equity = 0 (완전잠식) → 제외", "000002" not in sel, f"선정={sorted(sel)}")
    k.add("equity 결측 → 제외하지 않음(모름 ≠ 잠식)", "000003" in sel, f"선정={sorted(sel)}")
    return k


@clause("§3.4", "상장폐지 — 정리매매가 관측 시 실가, 아니면 −100% (누락 금지)")
def c34():
    k = Chk()
    days = bdays("2020-01-02", 260)
    cal = pd.DataFrame([
        {"rebal": pd.Timestamp("2020-03-01"), "signal_date": days[41], "exec_date": days[42]},
        {"rebal": pd.Timestamp("2020-06-01"), "signal_date": days[104], "exec_date": days[105]},
        {"rebal": pd.Timestamp("2020-09-01"), "signal_date": days[168], "exec_date": days[169]},
    ])
    # A: 정상 보유 (1000 → 1200)
    # B: 보유 중 폐지 + 마지막 종가 300(손실) → 정리매매가 인정 → −70%
    # C: 보유 중 폐지 + 가격이 폐지일 훨씬 전에 끊김 → −100%
    # D: 보유 중 폐지 + 마지막 종가 1500(이익) → 규정대로 −100% (보수적)
    # E: 정지 → 다음 분기 이후 폐지 (창 밖) → −100%
    closes = {}
    px_parts = []
    px_parts.append(mk_prices(["A"], days, close=1000.0))
    px_parts.append(mk_prices(["B"], days[:70], close=1000.0))
    px_parts.append(mk_prices(["C"], days[:60], close=900.0))
    px_parts.append(mk_prices(["D"], days[:70], close=1000.0))
    px_parts.append(mk_prices(["E"], days[:50], close=1000.0))
    px = pd.concat(px_parts, ignore_index=True)
    px.loc[(px["code"] == "A") & (px["date"] == days[105]), ["open", "close"]] = 1200.0
    px.loc[(px["code"] == "B") & (px["date"] == days[69]), ["open", "close", "high", "low"]] = 300.0
    px.loc[(px["code"] == "D") & (px["date"] == days[69]), ["open", "close", "high", "low"]] = 1500.0

    ep = G["build_exec_prices"](cal, px)
    delist = {"B": days[71], "C": days[71], "D": days[71], "E": days[180]}
    fwd = G["build_forward_returns"](ep, cal, delist, px)
    f = fwd.set_index(["code", "rebal"])

    def ret(c):
        try:
            return float(f.loc[(c, pd.Timestamp("2020-03-01")), "fwd_ret"])
        except KeyError:
            return float("nan")

    k.eq("A 정상 보유 수익률", ret("A"), 0.20, tol=1e-6)
    k.eq("B 정리매매가(300/1000−1) 반영", ret("B"), -0.70, tol=1e-6)
    k.eq("C 가격 부재 → −100%", ret("C"), -1.0, tol=1e-9)
    k.eq("D 마지막 관측가가 '이익' → 규정대로 −100%", ret("D"), -1.0, tol=1e-9)
    k.eq("E 정지 후 다음 분기 이후 폐지 → −100% (0% 로 새지 않는다)", ret("E"), -1.0, tol=1e-9)

    kinds = dict(zip(fwd["code"], fwd["exit_kind"]))
    k.add("E 는 halt_then_delist 로 별도 계상",
          any(str(v) == "halt_then_delist" for kk, v in
              zip(fwd["code"], fwd["exit_kind"]) if kk == "E"),
          f"exit_kind(E)={[v for kk, v in zip(fwd['code'], fwd['exit_kind']) if kk=='E']}")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §4  시점 규약
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§4", "분기 3/1·6/1·9/1·12/1 · 신호=직전 거래일 · 체결=익 거래일 · 공시=접수일+1거래일")
def c4():
    k = Chk()
    k.eq("REBAL_MONTHS", tuple(G["REBAL_MONTHS"]), (3, 6, 9, 12))
    k.eq("REBAL_DAY", G["REBAL_DAY"], 1)

    days = bdays("2019-01-01", 700)
    px = mk_prices(["000001"], days)
    cal = G["qvf_rebal_calendar"](px, "2019-01-01", "2021-06-30")
    months = sorted(set(pd.DatetimeIndex(cal["rebal"]).month))
    k.eq("명목 리밸런싱 월", tuple(months), (3, 6, 9, 12))
    k.add("명목일은 매월 1일",
          bool((pd.DatetimeIndex(cal["rebal"]).day == 1).all()),
          f"day 집합={sorted(set(pd.DatetimeIndex(cal['rebal']).day))}")
    k.add("signal_date < exec_date (전 시점)",
          bool((as_ts_s(cal["signal_date"]) < as_ts_s(cal["exec_date"])).all()),
          f"위반 {int((as_ts_s(cal['signal_date']) >= as_ts_s(cal['exec_date'])).sum())}건")

    td = G["qvf_trading_days"](px)
    ok_exec, ok_sig = True, True
    for r in cal.itertuples(index=False):
        i = int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.rebal)), side="left"))
        ok_exec &= (pd.Timestamp(td[i]) == pd.Timestamp(r.exec_date))
        ok_sig &= (pd.Timestamp(td[i - 1]) == pd.Timestamp(r.signal_date))
    k.add("exec_date = 명목일 이후(포함) 첫 거래일", ok_exec, f"전 {len(cal)}시점 검사")
    k.add("signal_date = exec_date 직전 거래일", ok_sig, f"전 {len(cal)}시점 검사")

    # 3/1 은 삼일절 — 명목일이 거래일이 아닌 분기가 실제로 존재해야 이 검정에 힘이 있다
    n_gap = int((as_ts_s(cal["exec_date"]) != as_ts_s(cal["rebal"])).sum())
    k.add("명목일 ≠ 체결일인 분기가 존재(검정력 확인)", n_gap > 0,
          f"{n_gap}/{len(cal)} 분기에서 명목일이 거래일이 아니다")

    # ── 공시 = 접수일 + 1거래일
    G["set_trading_days"](px)
    fri = pd.Timestamp("2019-03-01")                     # 금요일
    nxt = G["next_trading_day"](fri)
    k.add("금요일 접수 → 다음 '거래일'(월요일)", pd.Timestamp(nxt) == pd.Timestamp("2019-03-04"),
          f"{fri.date()} → {pd.Timestamp(nxt).date()}")
    df = pd.DataFrame({"knowledge_date": [fri], "event_date": [fri], "x": [1]})
    out = G["apply_t_plus_1"](df, "테스트")
    k.add("apply_t_plus_1 은 knowledge_date 만 민다",
          pd.Timestamp(out["knowledge_date"].iloc[0]) > fri
          and pd.Timestamp(out["event_date"].iloc[0]) == fri,
          f"knowledge {pd.Timestamp(out['knowledge_date'].iloc[0]).date()} · "
          f"event {pd.Timestamp(out['event_date'].iloc[0]).date()}")

    # ── ±5거래일 이동(§8.4) 이 실제로 거래일 기준인가
    cal_p5 = G["qvf_rebal_calendar"](px, "2019-01-01", "2021-06-30", shift_days=5)
    m = cal.merge(cal_p5, on="rebal", suffixes=("", "_s"))
    shifted_ok = True
    for r in m.itertuples(index=False):
        i0 = int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.exec_date)), side="left"))
        i1 = int(np.searchsorted(td, np.datetime64(pd.Timestamp(r.exec_date_s)), side="left"))
        shifted_ok &= (i1 - i0 == 5)
    k.add("shift_days=+5 → 체결일이 정확히 5거래일 뒤", shifted_ok,
          f"{len(m)}시점 전부 +5거래일")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §5  1차 필터
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§5.2", "V축 — EV/EBIT·PBR·PCR · 섹터중립 · 1% 윈저 · 음수분모는 최하위 강제")
def c52():
    k = Chk()
    k.eq("WINSOR_PCT", G["WINSOR_PCT"], 0.01)
    k.eq("V축 지표 구성", tuple(G["_V_METRICS"]), ("ev_ebit", "pbr", "pcr"))

    # ── 산식 검증 (한 행에서 정확한 값)
    P = mk_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=200.0, cash=50.0,
                op_income_ttm=[float(10 + i) for i in range(20)],
                equity=[float(100 + i) for i in range(20)],
                cfo_ttm=[float(20 + i) for i in range(20)], liabilities=300.0, sector="X")
    P = add_cells(P)
    V = G["axis_V"](P)
    r0 = V.iloc[0]
    k.eq("ev_ebit = (시총+차입−현금)/EBIT", float(r0["ev_ebit"]), (1000 + 200 - 50) / 10.0, tol=1e-6)
    k.eq("pbr = 시총/자기자본", float(r0["pbr"]), 1000 / 100.0, tol=1e-6)
    k.eq("pcr = 시총/영업CF", float(r0["pcr"]), 1000 / 20.0, tol=1e-6)

    # ── 방향: 낮을수록 우수 → z 가 높다
    corr = float(pd.Series(V["ev_ebit"]).corr(pd.Series(V["zV_ev_ebit"]).astype(float)))
    k.add("EV/EBIT 이 낮을수록 z 가 높다", corr < -0.9, f"corr(ev_ebit, z) = {corr:+.3f}")

    # ── 1% 윈저라이징이 실제로 걸리는가
    vals = pd.Series([float(i) for i in range(1, 101)] + [1e9])
    cells = pd.Series(["c"] * 101)
    z = G["xsec_z_pct"](vals, cells, pct=0.01)
    zmax_out = float(z.iloc[-1])
    zmax_in = float(z.iloc[:-1].max())
    k.add("극단값이 상위 1% 분위로 클립된다", abs(zmax_out - zmax_in) < 1e-3,
          f"1e9 의 z={zmax_out:.4f} · 나머지 최대 z={zmax_in:.4f} (클립 안 하면 z≈9.9)")

    # ── 섹터중립: 같은 섹터 안에서만 z 를 만든다
    P2 = mk_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=0.0, cash=0.0,
                 equity=1.0, cfo_ttm=1.0, liabilities=0.0,
                 op_income_ttm=[float(i) for i in range(1, 11)] * 2,
                 sector=["S1"] * 10 + ["S2"] * 10)
    P2.loc[P2["sector"] == "S2", "op_income_ttm"] = \
        P2.loc[P2["sector"] == "S2", "op_income_ttm"] * 1000.0
    P2 = add_cells(P2)
    V2 = G["axis_V"](P2)
    z1 = V2[V2["sector"] == "S1"]["zV_ev_ebit"].astype(float).to_numpy()
    z2 = V2[V2["sector"] == "S2"]["zV_ev_ebit"].astype(float).to_numpy()
    k.add("섹터 수준이 1000배 달라도 z 분포가 같다(섹터중립)",
          float(np.nanmax(np.abs(np.sort(z1) - np.sort(z2)))) < 1e-3,
          f"S1 z 범위 [{np.nanmin(z1):+.3f},{np.nanmax(z1):+.3f}] · "
          f"S2 [{np.nanmin(z2):+.3f},{np.nanmax(z2):+.3f}]")

    # ── 부호 처리: 음수/0 분모는 그 시점 횡단면 최하위 z 로 강제, 결측은 '모름'
    P3 = mk_grid(20, ["2020-03-01"], mktcap=1000.0, total_debt=0.0, cash=0.0,
                 equity=[float(100 + i) for i in range(18)] + [-50.0, 0.0],
                 cfo_ttm=1.0, liabilities=0.0, op_income_ttm=50.0, sector="X")
    P3 = add_cells(P3)
    V3 = G["axis_V"](P3)
    zp = V3["zV_pbr"].astype(float)
    worst = float(zp.min())
    k.eq("자기자본 음수 → 횡단면 최하위 z", float(zp.iloc[18]), worst, tol=1e-5)
    k.eq("자기자본 정확히 0 → 횡단면 최하위 z", float(zp.iloc[19]), worst, tol=1e-5)
    k.add("강제 최하위가 실제로 '최하위'다(양수 벌점이 아니다)",
          worst <= float(zp.iloc[:18].min()) + 1e-6,
          f"강제값 {worst:+.4f} · 유효 관측 최소 {float(zp.iloc[:18].min()):+.4f}")

    P4 = P3.copy()
    P4["equity"] = [float(100 + i) for i in range(18)] + [np.nan, np.nan]
    V4 = G["axis_V"](P4)
    k.add("자기자본 결측(모름) → 벌점이 아니라 결측",
          bool(pd.isna(V4["zV_pbr"].iloc[18])) and bool(pd.isna(V4["zV_pbr"].iloc[19])),
          f"z={V4['zV_pbr'].iloc[18]!r}, {V4['zV_pbr'].iloc[19]!r}")
    return k


@clause("§5.3", "Q축 — gp/a · ROIC 3년 표준편차 · 발생액 · 부채비율 · 주식수 3년 증가율")
def c53():
    k = Chk()
    k.eq("Q축 지표 구성",
         tuple(G["_Q_METRICS"]),
         ("gp_a", "roic_std3y", "accruals", "debt_ratio", "share_growth3y"))

    P = mk_grid(20, ["2020-03-01"], assets=1000.0,
                gross_profit_ttm=[float(100 + i) for i in range(20)],
                net_income_ttm=[float(50 + i) for i in range(20)],
                cfo_ttm=30.0, liabilities=[float(200 + 10 * i) for i in range(20)],
                equity=400.0, roic_std3y=[0.01 * (i + 1) for i in range(20)],
                share_growth3y=[0.02 * (i + 1) for i in range(20)],
                revenue_ttm=np.nan, cogs_ttm=np.nan, sector="X")
    P = add_cells(P)
    Q = G["axis_Q"](P)
    r0 = Q.iloc[0]
    k.eq("gp_a = 매출총이익TTM / 자산", float(r0["gp_a"]), 100 / 1000.0, tol=1e-9)
    k.eq("accruals = (순이익TTM − 영업CF) / 자산", float(r0["accruals"]), (50 - 30) / 1000.0, tol=1e-9)
    k.eq("debt_ratio = 부채총계 / 자기자본", float(r0["debt_ratio"]), 200 / 400.0, tol=1e-9)

    for name, raw, zc, want_sign in (
            ("gp_a(높을수록 우수)", "gp_a", "zQ_gp_a", +1),
            ("발생액(낮을수록 우수)", "accruals", "zQ_accruals", -1),
            ("부채비율(낮을수록 우수)", "debt_ratio", "zQ_debt_ratio", -1),
            ("ROIC 표준편차(낮을수록 우수)", "roic_std3y", "zQ_roic_std3y", -1),
            ("주식수 3년 증가율(낮을수록 우수)", "share_growth3y", "zQ_share_growth3y", -1)):
        c = float(pd.Series(Q[raw]).astype(float).corr(pd.Series(Q[zc]).astype(float)))
        k.add(f"방향 — {name}", (c > 0.9) if want_sign > 0 else (c < -0.9),
              f"corr(raw, z) = {c:+.3f}")

    # ── 매출총이익 결측 시 (매출 − 매출원가) 폴백
    P2 = P.copy()
    P2["gross_profit_ttm"] = np.nan
    P2["revenue_ttm"] = 500.0
    P2["cogs_ttm"] = 300.0
    Q2 = G["axis_Q"](P2)
    k.eq("gp 결측 → (매출−매출원가)/자산 폴백", float(Q2["gp_a"].iloc[0]), 200 / 1000.0, tol=1e-9)

    # ── 주식수 3년 증가율: 12분기 전 대비 · 실제 달력 간격 검사
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
    fq = G["build_quarterly_fundamentals"](fin, shares)
    sg = fq.dropna(subset=["share_growth3y"])
    k.add("주식수 3년 증가율 산출됨", len(sg) > 0, f"{len(sg)}행")
    if len(sg):
        got = float(sg["share_growth3y"].iloc[0])
        k.eq("증가율 = 12분기 전 대비 (1.05^12 − 1)", got, 1.05 ** 12 - 1.0, tol=1e-4)

    # 중간 분기가 빠지면 '12행 전'이 3년 전이 아니므로 만들지 않아야 한다
    shares2 = shares.drop(index=[4, 5, 6, 7]).reset_index(drop=True)
    fq2 = G["build_quarterly_fundamentals"](fin, shares2)
    n2 = int(fq2["share_growth3y"].notna().sum())
    k.add("결측 분기가 있으면 '12행 전'을 3년으로 부르지 않는다", n2 < len(sg),
          f"완전 시계열 {len(sg)}건 → 4분기 결측 시 {n2}건")
    return k


@clause("§5.4", "F축 — 외국인·기관 60일 순매수를 '유동주식 시가총액'으로 정규화")
def c54():
    k = Chk()
    k.eq("FLOW_WINDOW_DAYS", G["FLOW_WINDOW_DAYS"], 60)

    # 두 종목의 순매수 금액은 같지만 유동시총이 10배 다르다 → 정규화가 되면 z 가 달라야 한다
    P = add_cells(mk_grid(20, ["2020-03-01"], close=1000.0,
                          shares_issued=[1e6] * 10 + [1e7] * 10,
                          shares_treasury=0.0, mktcap=1e9, sector="X"))
    flows = pd.DataFrame({"code": P["code"], "rebal": P["rebal"],
                          "foreign_net": 1e7, "inst_net": 1e7, "flow_src": "test"})
    F = G["axis_F"](P, flows)
    k.eq("float_cap = (발행주식수 − 자기주식) × 종가", float(F["float_cap"].iloc[0]), 1e6 * 1000.0,
         tol=1.0)
    k.eq("flow_f = 외국인순매수 / 유동시총", float(F["flow_f"].iloc[0]), 1e7 / 1e9, tol=1e-12)
    z_small = float(F["Z_F"].iloc[0])
    z_big = float(F["Z_F"].iloc[-1])
    k.add("같은 금액이라도 유동시총이 작으면 z 가 높다(절대금액 랭킹이 아니다)",
          z_small > z_big, f"유동시총 10억 z={z_small:+.3f} · 100억 z={z_big:+.3f}")

    # 자기주식 차감이 실제로 반영되는가
    P2 = P.copy()
    P2["shares_treasury"] = [2e5] * 10 + [0.0] * 10
    F2 = G["axis_F"](P2, flows)
    k.eq("자기주식 20% 차감 → 유동시총 8억", float(F2["float_cap"].iloc[0]), 8e8, tol=1.0)

    # 수급 결측은 0 이 아니라 결측
    F3 = G["axis_F"](P, pd.DataFrame(columns=["code", "rebal", "foreign_net", "inst_net", "flow_src"]))
    k.add("수급 관측이 없으면 Z_F 는 0 이 아니라 결측",
          bool(F3["Z_F"].isna().all()),
          f"Z_F 결측 {int(F3['Z_F'].isna().sum())}/{len(F3)}행")

    # §9-C4 입력이 '사전등록 창(60일)'로 고정되는가 — 120일 재호출이 덮으면 안 된다
    flows60 = flows.copy()
    flows60.attrs["flow_window"] = 60
    nz = pd.DataFrame({"code": P["code"], "rebal": P["rebal"],
                       "foreign_net": [0.0] * 10 + [1e7] * 10,
                       "inst_net": 0.0, "flow_src": "t"})
    nz.attrs["flow_window"] = 60
    G["axis_F"](P, nz)
    pre = float(G["FLOW_NONZERO_RATIO_PREREG"])
    flows120 = flows.copy()
    flows120.attrs["flow_window"] = 120
    G["axis_F"](P, flows120)
    pre_after = float(G["FLOW_NONZERO_RATIO_PREREG"])
    k.eq("60일 창의 비영 비율", pre, 0.5, tol=1e-6)
    k.add("120일 창 재호출이 사전등록 값을 덮지 않는다", abs(pre_after - pre) < 1e-9,
          f"재호출 전 {pre:.3f} → 후 {pre_after:.3f} "
          f"(현재 창 값 {G['FLOW_NONZERO_BY_WINDOW'].get(120)})")
    return k


@clause("§5.5", "Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F · 사전등록 가중치 · U-200")
def c55():
    k = Chk()
    k.eq("U200_N", G["U200_N"], 200)
    k.eq("변형 목록", tuple(G["VARIANTS"]), ("V", "VQ", "VQF"))
    k.eq("w(V)", tuple(G["VARIANT_W"]["V"]), (1.0, 0.0, 0.0))
    k.eq("w(VQ)", tuple(G["VARIANT_W"]["VQ"]), (0.5, 0.5, 0.0))
    k.eq("w(VQF)", tuple(G["VARIANT_W"]["VQF"]), (0.4, 0.4, 0.2))

    P = mk_grid(5, ["2020-03-01"], Z_V=[1.0, 2.0, 3.0, 4.0, 5.0],
                Z_Q=[5.0, 4.0, 3.0, 2.0, 1.0], Z_F=[0.0, 1.0, 0.0, 1.0, 0.0], sector="X")
    for v, (wv, wq, wf) in G["VARIANT_W"].items():
        s = G["score1"](P, v).astype(float).to_numpy()
        want = wv * P["Z_V"].to_numpy() + wq * P["Z_Q"].to_numpy() + wf * P["Z_F"].to_numpy()
        want = want / (wv + wq + wf)
        k.add(f"Score1[{v}] 산식 일치", float(np.nanmax(np.abs(s - want))) < 1e-5,
              f"최대 오차 {float(np.nanmax(np.abs(s - want))):.2e} · 실측 {np.round(s,4).tolist()}")

    # ── 축 결측 시 0 채움이 아니라 가중치 재정규화
    P2 = P.copy()
    P2.loc[0, "Z_F"] = np.nan
    s = G["score1"](P2, "VQF").astype(float)
    want0 = (0.4 * 1.0 + 0.4 * 5.0) / 0.8
    k.eq("Z_F 결측 행은 가용 축으로 재정규화(0 채움 아님)", float(s.iloc[0]), want0, tol=1e-5)

    # ── U-200 절단이 정확히 상위 n
    n = 500
    P3 = mk_grid(n, ["2020-03-01"], Z_V=[float(i) for i in range(n)], Z_Q=0.0, Z_F=0.0,
                 mktcap=1e9, sector="X")
    d = G["build_u200"](P3, variants=("V",), n=200)
    sel = d[d["u200_V"]]
    k.eq("u200 선정 수", int(len(sel)), 200)
    k.add("선정 = Score1 상위 200",
          int(sel["Z_V"].min()) == n - 200,
          f"선정 Z_V 최소 {float(sel['Z_V'].min()):.0f} (기대 {n-200})")

    # ── 동점 tie-break 이 행 순서에 의존하지 않는가(검정력 확인: 동점이 커트라인을 가로지름)
    m = 20
    P4 = mk_grid(m, ["2020-03-01"], Z_V=[1.0] * m, Z_Q=0.0, Z_F=0.0,
                 mktcap=[float(m - i) for i in range(m)], sector="X")
    a = set(G["build_u200"](P4, variants=("V",), n=10)
            .query("u200_V")["code"])
    P5 = P4.sample(frac=1.0, random_state=7).reset_index(drop=True)
    b = set(G["build_u200"](P5, variants=("V",), n=10).query("u200_V")["code"])
    k.add("전원 동점 · 커트라인이 동점을 가로질러도 선정이 같다", a == b,
          f"원순서 {sorted(a)} / 섞은 순서 {sorted(b)}")
    return k


@clause("§5.6", "필수 보고 — 변형 간 중복률 · 특성 · 리포트 커버리지 · 회전율")
def c56():
    k = Chk()
    n = 60
    P = mk_grid(n, ["2020-03-01", "2020-06-01"],
                Z_V=[float(i) for i in range(n)],
                Z_Q=[float(n - i) for i in range(n)],
                Z_F=[float((i * 7) % n) for i in range(n)],
                mktcap=[1e8 * (i + 1) for i in range(n)], adtv=5e8,
                n_reports=[1 if i % 2 == 0 else 0 for i in range(n)], sector="X")
    P = G["build_u200"](P, variants=("V", "VQ", "VQF"), n=20)
    res = G["report_variant_comparison"](P, ("V", "VQ", "VQF"),
                                         rep_cov=P[["code", "rebal", "n_reports"]])
    for key in ("overlap", "coverage", "turnover", "sets"):
        k.add(f"보고 항목 '{key}' 산출", key in res and bool(res[key]), f"{key} → {type(res.get(key))}")

    # 중복률이 교집합/합집합(Jaccard) 인가 — 손계산과 대조
    sets = res["sets"]
    t0 = sorted(sets["V"])[0]
    a, b = set(sets["V"][t0]), set(sets["VQ"][t0])
    want = len(a & b) / len(a | b)
    k.eq("V∩VQ 중복률 = 교집합/합집합", res["overlap"]["V~VQ"], want, tol=0.05)
    k.add("중복률이 [0,1] 범위",
          all(0.0 <= v <= 1.0 for v in res["overlap"].values()),
          f"overlap={ {kk: round(vv,3) for kk, vv in res['overlap'].items()} }")
    k.add("커버리지가 [0,1] 범위",
          all(0.0 <= v <= 1.0 for v in res["coverage"].values()),
          f"coverage={ {kk: round(vv,3) for kk, vv in res['coverage'].items()} }")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §6  2차 필터
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§6.1", "배제 플래그 6종 — 임계값 · 근거 없으면 배제하지 않음")
def c61():
    k = Chk()
    k.eq("RELATED_PARTY_TOPQ", G["RELATED_PARTY_TOPQ"], 0.20)
    k.eq("CONTINGENT_EQ_PP", G["CONTINGENT_EQ_PP"], 0.05)
    k.eq("LAWSUIT_EQ_2ND", G["LAWSUIT_EQ_2ND"], 0.05)
    k.eq("배제 플래그 개수", len(G["EXCL_FLAGS"]), 6)

    n = 20
    P = mk_grid(n, ["2020-03-01"], equity=1000.0,
                related_sales_ratio=np.nan, related_sales_ratio_prev=np.nan,
                related_purchase_ratio=np.nan, related_purchase_ratio_prev=np.nan,
                contingent_amt=np.nan, contingent_amt_prev=np.nan,
                lawsuit_amt=np.nan, lawsuit_new=np.nan, lawsuit_filed=np.nan,
                audit_emphasis=np.nan, major_holder_chg=np.nan,
                cb_issue=np.nan, bw_issue=np.nan, sector="X")
    E = G["build_exclusion_flags"](P)
    k.eq("근거가 전부 결측이면 배제 0건", int(E["EXCLUDED"].sum()), 0)

    # 각 플래그를 하나씩 정확히 발동시킨다
    P2 = P.copy()
    #  ① 특수관계자 비중 상승 상위 20% — 20종목 중 상승폭 상위 4종목
    P2["related_sales_ratio_prev"] = 0.10
    P2["related_sales_ratio"] = [0.10 + 0.01 * i for i in range(n)]
    #  ② 우발부채 자기자본 대비 +5%p (경계 검정: 정확히 5%p 는 포함)
    P2["contingent_amt_prev"] = 0.0
    P2["contingent_amt"] = [0.0] * (n - 2) + [50.0, 49.0]     # 50/1000 = 5.0%p, 49 = 4.9%p
    #  ③ 신규소송 + 소송가액/자본 > 5%
    P2["lawsuit_new"] = [0.0] * (n - 3) + [1.0, 1.0, 0.0]
    P2["lawsuit_amt"] = [0.0] * (n - 3) + [60.0, 40.0, 600.0]  # 6% / 4% / 60%(신규 아님)
    #  ④~⑥
    P2["audit_emphasis"] = [0.0] * (n - 1) + [1.0]
    P2["major_holder_chg"] = [0.0] * (n - 1) + [1.0]
    P2["cb_issue"] = [0.0] * (n - 1) + [1.0]
    P2["bw_issue"] = 0.0
    E2 = G["build_exclusion_flags"](P2)

    n_rel = int(E2["x_related_up"].sum())
    k.add("① 특수관계자 상승폭 상위 20% ≈ 4/20 종목", 3 <= n_rel <= 5,
          f"발동 {n_rel}건 (상위 20% = 4건 기대)")
    k.add("② 우발부채 5.0%p → 발동 / 4.9%p → 미발동",
          float(E2["x_contingent"].iloc[n - 2]) == 1.0 and float(E2["x_contingent"].iloc[n - 1]) == 0.0,
          f"5.0%p={E2['x_contingent'].iloc[n-2]} · 4.9%p={E2['x_contingent'].iloc[n-1]} · "
          f"총 {int(E2['x_contingent'].sum())}건")
    k.add("③ 신규소송 6% → 발동 / 신규소송 4% → 미발동 / 소송만 60%(신규 아님) → 미발동",
          float(E2["x_lawsuit"].iloc[n - 3]) == 1.0
          and float(E2["x_lawsuit"].iloc[n - 2]) == 0.0
          and float(E2["x_lawsuit"].iloc[n - 1]) == 0.0,
          f"[6%신규, 4%신규, 60%비신규] = "
          f"{[float(E2['x_lawsuit'].iloc[i]) for i in (n-3, n-2, n-1)]}")
    k.eq("④ 감사의견 강조사항 발동", int(E2["x_audit"].sum()), 1)
    k.eq("⑤ 최대주주 변경 발동", int(E2["x_holder_chg"].sum()), 1)
    k.eq("⑥ CB/BW 발행 발동", int(E2["x_cbbw"].sum()), 1)
    k.add("EXCLUDED = 6종 OR",
          bool((E2["EXCLUDED"] == (E2[G["EXCL_FLAGS"]].sum(axis=1) > 0).astype(int)).all()),
          f"배제 {int(E2['EXCLUDED'].sum())}/{n}행")
    return k


@clause("§6.2", "ΔTONE 결측 허용 — 관측치 z 를 만든 '뒤에' 0(중립) 주입")
def c62():
    k = Chk()
    n = 100
    vals = [np.nan] * (n - 12)
    obs = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0]
    P = mk_grid(n, ["2020-03-01"], dTONE_resid=vals + obs, sector="X")
    P = add_cells(P)
    mask = G["col"](P, "dTONE_resid").notna()
    z = G["zscore_observed_then_neutral"](P, "dTONE_resid", mask)
    zo = z[mask.to_numpy()].astype(float)
    k.eq("관측치 z 평균 ≈ 0 (관측치만으로 표준화)", float(zo.mean()), 0.0, tol=1e-4)
    k.eq("관측치 z 표준편차 ≈ 1", float(zo.std(ddof=0)), 1.0, tol=1e-3)
    k.add("비관측치는 정확히 0.0",
          bool((z[~mask.to_numpy()].astype(float) == 0.0).all()),
          f"비관측 {int((~mask).sum())}행 전부 0.0")
    k.add("검정력 확인 — 0 을 먼저 채웠다면 관측치 z 평균이 크게 양수",
          float(zo.mean()) < 0.5,
          f"실측 관측치 z 평균 {float(zo.mean()):+.4f} · "
          f"선(先)0채움이면 ≈ +{(np.mean(obs) - np.mean(vals[:1] * (n-12) + obs)) or 0:.2f} 수준으로 치우침")

    # 리포트 없는 종목이 2차필터에서 실제로 살아남는가
    m = 60
    P2 = mk_grid(m, ["2020-03-01"], sector="X",
                 dNONFIN=[float(i % 7) for i in range(m)],
                 dTONE_resid=[float(i) if i < 20 else np.nan for i in range(m)],
                 n_reports=[1 if i < 20 else 0 for i in range(m)],
                 score1_V=[float(m - i) for i in range(m)], u200_V=True, EXCLUDED=0)
    P2 = add_cells(P2)
    P2 = G["apply_filter2"](P2, "V", n=30)
    res = G["verify_missing_tolerance"](P2, "V")
    rw, ro = res.get("pass_with_report", float("nan")), res.get("pass_without_report", float("nan"))
    k.add("리포트 없는 종목의 통과율이 보유 종목의 절반 이상",
          np.isfinite(ro) and np.isfinite(rw) and ro >= rw * 0.5,
          f"보유 {100*rw:.1f}% · 없음 {100*ro:.1f}%")
    return k


@clause("§6.3", "Score2 = 2.0·z(ΔNONFIN) + 1.0·z(ΔTONE_resid) − 배제(하드) → 60~80종목")
def c63():
    k = Chk()
    k.eq("SCORE2_W_NONFIN", G["SCORE2_W_NONFIN"], 2.0)
    k.eq("SCORE2_W_TONE", G["SCORE2_W_TONE"], 1.0)
    k.eq("가중 비율 2:1", G["SCORE2_W_NONFIN"] / G["SCORE2_W_TONE"], 2.0)
    k.add("SECOND_N 이 명세 범위 60~80", 60 <= G["SECOND_N"] <= 80, f"SECOND_N={G['SECOND_N']}")

    n = 100
    P = mk_grid(n, ["2020-03-01"], sector="X", u200_V=True, EXCLUDED=0,
                dNONFIN=[float(i) for i in range(n)],
                dTONE_resid=[float(n - i) for i in range(n)],
                score1_V=0.0)
    P = add_cells(P)
    d = G["apply_filter2"](P, "V", n=70)
    zN = G["zscore_observed_then_neutral"](P, "dNONFIN", G["col"](P, "dNONFIN").notna())
    zT = G["zscore_observed_then_neutral"](P, "dTONE_resid", G["col"](P, "dTONE_resid").notna())
    want = 2.0 * zN.astype(float) + 1.0 * zT.astype(float)
    err = float(np.nanmax(np.abs(d["score2_V"].astype(float).to_numpy() - want.to_numpy())))
    k.add("Score2 산식 일치", err < 1e-5, f"최대 오차 {err:.2e}")
    k.eq("2차 선정 수 = n", int(d["f2_V"].sum()), 70)

    # 배제는 하드 — 점수가 아무리 높아도 선정되지 않는다
    P2 = P.copy()
    P2["EXCLUDED"] = [1 if i >= n - 10 else 0 for i in range(n)]
    P2["dNONFIN"] = [float(i) for i in range(n)]          # 배제 대상이 최고점
    d2 = G["apply_filter2"](P2, "V", n=70)
    picked = d2[d2["f2_V"]]
    k.add("배제 종목은 최고점이어도 선정되지 않는다",
          int(picked["EXCLUDED"].sum()) == 0,
          f"선정 {len(picked)}종목 중 배제 {int(picked['EXCLUDED'].sum())}건")

    # U-200 밖 종목은 후보가 아니다
    P3 = P.copy()
    P3["u200_V"] = [i < 50 for i in range(n)]
    d3 = G["apply_filter2"](P3, "V", n=70)
    k.eq("U-200 밖은 2차 후보가 아니다", int(d3["f2_V"].sum()), 50)
    return k


@clause("§6.4", "인과 순서 점검 — 보고만 하고 가중치를 자동 조정하지 않는다")
def c64():
    k = Chk()
    before = (G["SCORE2_W_NONFIN"], G["SCORE2_W_TONE"])
    n = 40
    P = mk_grid(n, ["2020-03-01"], sector="X",
                dNONFIN=[float(i) for i in range(n)],
                dTONE=[float(i) + 0.01 for i in range(n)],
                dTONE_resid=[float(i) for i in range(n)], n_reports=1)
    reports = pd.DataFrame({"stock_code": P["code"].head(10).to_numpy(),
                            "pub_date": pd.Timestamp("2020-02-01"),
                            "report_uid": [f"r{i}" for i in range(10)]})
    dis = pd.DataFrame({"code": P["code"].head(10), "rcept_dt": pd.Timestamp("2020-02-10"),
                        "report_nm": "주요사항보고서"})
    try:
        G["check_causal_order"](reports, dis, P)
        ran = True
        err = ""
    except Exception as e:                                    # noqa
        ran, err = False, f"{type(e).__name__}: {e}"
    after = (G["SCORE2_W_NONFIN"], G["SCORE2_W_TONE"])
    k.add("check_causal_order 가 예외 없이 실행", ran, err or "ok")
    k.add("실행 후에도 Score2 가중치가 그대로", before == after, f"{before} → {after}")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §7  3차 필터 · 포트폴리오
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§7.2", "3-A 규칙 6개 — 사전등록 임계값에서 정확히 발동 · 근거 결측은 제외 안 함")
def c72():
    k = Chk()
    k.eq("RULE_LAWSUIT_EQ", G["RULE_LAWSUIT_EQ"], 0.10)
    k.eq("RULE_RELATED_SALES", G["RULE_RELATED_SALES"], 0.30)
    k.eq("RULE_MAJOR_HOLDER", G["RULE_MAJOR_HOLDER"], 0.15)
    k.eq("RULE_OP_LOSS_QUARTERS", G["RULE_OP_LOSS_QUARTERS"], 4)
    k.eq("RULE_IMPAIRMENT", G["RULE_IMPAIRMENT"], 0.30)
    k.eq("3-A 규칙 개수", len(G["RULE_FLAGS"]), 6)

    BASE = dict(sector="X", equity=2000.0, capital_stock=2000.0,   # 자본잠식률 0% (미발동)
                lawsuit_ratio=np.nan, related_sales_ratio=np.nan, major_holder_pct=np.nan,
                audit_emphasis=np.nan, op_loss_4q=np.nan)
    P = mk_grid(3, ["2020-03-01"], **BASE)
    R = G["apply_filter3a"](P)
    k.eq("근거 전부 결측 → 차단 0건", int(R["RULE3A_BLOCK"].sum()), 0)

    # 경계 검정: 임계 '초과'만 발동
    def one(**kw):
        d = mk_grid(1, ["2020-03-01"], **{**BASE, **kw})
        return G["apply_filter3a"](d).iloc[0]

    k.add("소송 10.0% → 미발동 / 10.1% → 발동",
          float(one(lawsuit_ratio=0.10)["r_lawsuit"]) == 0.0
          and float(one(lawsuit_ratio=0.101)["r_lawsuit"]) == 1.0,
          f"0.100→{one(lawsuit_ratio=0.10)['r_lawsuit']} · 0.101→{one(lawsuit_ratio=0.101)['r_lawsuit']}")
    k.add("특수관계자 매출 30.0% → 미발동 / 30.1% → 발동",
          float(one(related_sales_ratio=0.30)["r_related"]) == 0.0
          and float(one(related_sales_ratio=0.301)["r_related"]) == 1.0,
          f"0.300→{one(related_sales_ratio=0.30)['r_related']} · "
          f"0.301→{one(related_sales_ratio=0.301)['r_related']}")
    k.add("최대주주 15.0% → 미발동 / 14.9% → 발동",
          float(one(major_holder_pct=0.15)["r_holder"]) == 0.0
          and float(one(major_holder_pct=0.149)["r_holder"]) == 1.0,
          f"0.150→{one(major_holder_pct=0.15)['r_holder']} · "
          f"0.149→{one(major_holder_pct=0.149)['r_holder']}")
    k.add("최대주주 지분율 결측 → 미발동(모른다고 버리지 않는다)",
          float(one()["r_holder"]) == 0.0, f"결측→{one()['r_holder']}")
    k.add("감사 강조사항 → 발동", float(one(audit_emphasis=1.0)["r_audit"]) == 1.0, "")
    k.add("4분기 연속 영업적자 → 발동", float(one(op_loss_4q=1.0)["r_oploss"]) == 1.0, "")

    # 자본잠식률 = (자본금 − 자기자본) / 자본금
    r = one(equity=1300.0)        # (2000−1300)/2000 = 35% > 30%
    k.eq("자본잠식률 산식", float(r["impair_ratio"]), (2000 - 1300) / 2000.0, tol=1e-9)
    k.add("자본잠식률 35% → 발동", float(r["r_impair"]) == 1.0, f"impair={float(r['impair_ratio']):.3f}")
    r2 = one(equity=1400.0)       # 30.0% — 초과가 아니므로 미발동
    k.add("자본잠식률 정확히 30% → 미발동", float(r2["r_impair"]) == 0.0,
          f"impair={float(r2['impair_ratio']):.3f} · flag={float(r2['r_impair'])}")
    return k


@clause("§7.4", "최종 20~40종목 · 동일가중 기준 · 하한 미달은 억지로 채우지 않는다")
def c74():
    k = Chk()
    k.eq("FINAL_N_MIN", G["FINAL_N_MIN"], 20)
    k.eq("FINAL_N", G["FINAL_N"], 30)
    k.eq("FINAL_N_MAX", G["FINAL_N_MAX"], 40)
    k.add("기본 보유수가 명세 범위", 20 <= G["FINAL_N"] <= 40, f"FINAL_N={G['FINAL_N']}")
    k.eq("가중 방식", tuple(G["WEIGHT_SCHEMES"]), ("equal", "invvol"))

    n = 100
    P = mk_grid(n, ["2020-03-01"], sector="X", f2_V=True, RULE3A_BLOCK=0,
                score2_V=[float(i) for i in range(n)], score1_V=0.0)
    sel = G["build_final_selection"](P, "V", n_final=30)
    k.eq("풀 100 · n_final 30 → 30종목", int(sel.sum()), 30)
    k.add("선정 = Score2 상위 30",
          float(P.loc[sel, "score2_V"].min()) == float(n - 30),
          f"선정 score2 최소 {float(P.loc[sel,'score2_V'].min()):.0f} (기대 {n-30})")

    # 상·하한 클램프
    k.eq("n_final=100 요청 → 40 으로 클램프", int(G["build_final_selection"](P, "V", n_final=100).sum()), 40)
    k.eq("n_final=5 요청 → 20 으로 클램프", int(G["build_final_selection"](P, "V", n_final=5).sum()), 20)

    # 풀이 하한 미만이면 규칙을 되돌려 채우지 않는다
    P2 = P.copy()
    P2["f2_V"] = [i < 7 for i in range(n)]
    sel2 = G["build_final_selection"](P2, "V", n_final=30)
    k.eq("풀 7종목 → 7종목 (억지로 20 을 채우지 않는다)", int(sel2.sum()), 7)

    # 3-A 차단은 하드
    P3 = P.copy()
    P3["RULE3A_BLOCK"] = [1 if i >= n - 40 else 0 for i in range(n)]
    sel3 = G["build_final_selection"](P3, "V", n_final=30)
    k.eq("3-A 차단 종목은 최고점이어도 선정 안 됨", int(P3.loc[sel3, "RULE3A_BLOCK"].sum()), 0)

    # 동일가중
    sub = P.head(25)
    w = G["compute_weights"](sub, "equal")
    k.add("동일가중 = 1/n · 합 1", abs(float(w.sum()) - 1.0) < 1e-12
          and float(w.max() - w.min()) < 1e-15,
          f"n={len(sub)} · w={float(w.iloc[0]):.6f} (기대 {1/25:.6f})")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §8  비용 · 실험 · 다중검정 · 강건성
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§8.1", "비용 = 증권거래세(이력) + 실측 스프레드/2 · 비용 전/후 병기")
def c81():
    k = Chk()
    k.eq("기본 비용모형", str(G["QVF_COST_MODEL"]), "spec")

    for d, want in (("2016-01-01", 0.0030), ("2019-06-02", 0.0030), ("2019-06-03", 0.0025),
                    ("2021-01-01", 0.0023), ("2023-01-01", 0.0020), ("2024-01-01", 0.0018),
                    ("2025-06-01", 0.0015)):
        k.eq(f"거래세 {d}", G["qvf_sell_tax"](d), want, tol=1e-12)

    # ── 비용 산식: |Δw|·(spread/2) + 매도분·tax, 수수료·충격 없음
    days = bdays("2020-01-02", 300)
    cal = pd.DataFrame([
        {"rebal": pd.Timestamp("2020-03-01"), "signal_date": days[41], "exec_date": days[42]},
        {"rebal": pd.Timestamp("2020-06-01"), "signal_date": days[104], "exec_date": days[105]},
    ])
    P = pd.DataFrame([
        {"code": "A", "rebal": pd.Timestamp("2020-03-01"), "sel": True,
         "adtv": 1e10, "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9},
        {"code": "A", "rebal": pd.Timestamp("2020-06-01"), "sel": False,
         "adtv": 1e10, "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9},
        {"code": "B", "rebal": pd.Timestamp("2020-06-01"), "sel": True,
         "adtv": 1e10, "cs_spread": 0.01, "vol_d": 0.02, "mktcap": 1e9},
    ])
    fwd = pd.DataFrame([{"code": "A", "rebal": pd.Timestamp("2020-03-01"), "fwd_ret": 0.10},
                        {"code": "B", "rebal": pd.Timestamp("2020-06-01"), "fwd_ret": 0.0}])
    G["set_delist_map"]({})
    bt = G["run_qbacktest"](P, cal, "sel", fwd, apply_costs=True, label="T", cost_model="spec")
    R = bt["returns"].set_index("rebal")
    # t0: A 를 100% 매수 → 비용 = 1.0 × 0.01/2 = 0.005
    k.eq("t0 매수 비용 = |Δw|·spread/2", float(R.loc[pd.Timestamp("2020-03-01"), "cost"]),
         0.005, tol=1e-9)
    # t1: A 전량 매도(1.0) + B 전량 매수(1.0). 세금은 매도분에만 (2020년 → 0.0023)
    want_t1 = 1.0 * 0.005 + 1.0 * 0.005 + 1.0 * G["qvf_sell_tax"](days[105])
    k.eq("t1 비용 = 매도(스프레드/2 + 세금) + 매수(스프레드/2)",
         float(R.loc[pd.Timestamp("2020-06-01"), "cost"]), want_t1, tol=1e-9)
    k.eq("t0 비용 전 수익", float(R.loc[pd.Timestamp("2020-03-01"), "ret_gross"]), 0.10, tol=1e-9)
    k.eq("t0 비용 후 수익 = 비용 전 − 비용",
         float(R.loc[pd.Timestamp("2020-03-01"), "ret"]), 0.10 - 0.005, tol=1e-9)
    k.add("비용 전/후가 모두 산출된다(병기 강제)",
          {"ret", "ret_gross", "equity", "equity_gross"} <= set(bt["returns"].columns),
          f"컬럼 {sorted(bt['returns'].columns)}")

    # extended 는 수수료+충격이 '추가로' 붙는다 → 항상 더 비싸다
    bt2 = G["run_qbacktest"](P, cal, "sel", fwd, apply_costs=True, label="T",
                             cost_model="extended")
    c_spec = float(bt["returns"]["cost"].sum())
    c_ext = float(bt2["returns"]["cost"].sum())
    k.add("extended 비용 > spec 비용 (명세 초과분은 기본에 없다)", c_ext > c_spec,
          f"spec {c_spec:.6f} · extended {c_ext:.6f} · 차이 {c_ext-c_spec:.6f}")

    # 스프레드 하한/상한
    P3 = P.copy()
    P3["cs_spread"] = 1e-9
    bt3 = G["run_qbacktest"](P3, cal, "sel", fwd, apply_costs=True, label="T", cost_model="spec")
    k.eq("스프레드 하한 15bp 가 적용된다",
         float(bt3["returns"].set_index("rebal").loc[pd.Timestamp("2020-03-01"), "cost"]),
         (G["SLIPPAGE_FLOOR_BPS"] / 1e4) / 2.0, tol=1e-12)

    # 연율화 √4
    k.eq("Q_PER_YEAR", G["Q_PER_YEAR"], 4.0)
    return k


@clause("§8.2", "실험 매트릭스 — 주 실험 3 + X1~X4 · X1 에는 3-A·2차가 없다")
def c82():
    k = Chk()
    n = 120
    P = mk_grid(n, ["2020-03-01"], sector="X",
                Z_V=[float(i) for i in range(n)], Z_Q=0.0, Z_F=0.0,
                dNONFIN=[float((i * 13) % n) for i in range(n)],
                dTONE_resid=np.nan, EXCLUDED=0,
                RULE3A_BLOCK=[1 if i >= n - 10 else 0 for i in range(n)],
                mktcap=1e9, adtv=1e10, cs_spread=0.01, vol_d=0.02, n_reports=0)
    P = add_cells(P)
    P = G["build_u200"](P, variants=("V",), n=100)

    # X1: 1차만 — 3-A 가 걸린 최고점 종목이 그대로 선정되어야 한다
    sel_x1 = G["build_final_selection"](P, "V", n_final=30, use_rule3a=True, stage="x1")
    n_blocked_in_x1 = int(P.loc[sel_x1, "RULE3A_BLOCK"].sum())
    k.add("X1(1차만)에는 3-A 가 적용되지 않는다", n_blocked_in_x1 > 0,
          f"X1 선정 30종목 중 3-A 차단 종목 {n_blocked_in_x1}건 "
          f"(0 이면 X1 이 사실상 '1차+3차' 였다는 뜻)")

    Pf = G["apply_filter2"](P, "V", n=70)
    sel_full = G["build_final_selection"](Pf, "V", n_final=30, use_rule3a=True, stage="full")
    k.eq("full 에는 3-A 가 적용된다", int(Pf.loc[sel_full, "RULE3A_BLOCK"].sum()), 0)

    # X4 = 1차+2차, 3-A 없음
    sel_x4 = G["build_final_selection"](Pf, "V", n_final=30, use_rule3a=False, stage="full")
    k.add("X4(3-A 없음)는 차단 종목을 담을 수 있다",
          int(Pf.loc[sel_x4, "RULE3A_BLOCK"].sum()) > 0,
          f"X4 선정 중 3-A 차단 {int(Pf.loc[sel_x4,'RULE3A_BLOCK'].sum())}건")

    # X2 = 1차 + 배제플래그만 (ΔNONFIN·ΔTONE 없음) → score2 가 전 행 동일
    d_x2 = G["apply_filter2"](P, "V", n=70, use_tone=False, use_nonfin=False, use_exclusion=True)
    k.add("X2 는 Score2 가 상수(배제만 작동)",
          float(d_x2["score2_V"].astype(float).std()) < 1e-9,
          f"score2 표준편차 {float(d_x2['score2_V'].astype(float).std()):.2e}")

    # X3 = 1차 + ΔNONFIN 만 (배제·TONE 없음)
    d_x3 = G["apply_filter2"](P, "V", n=70, use_tone=False, use_nonfin=True, use_exclusion=False)
    k.add("X3 는 ΔNONFIN 만으로 Score2 가 변한다",
          float(d_x3["score2_V"].astype(float).std()) > 0.1,
          f"score2 표준편차 {float(d_x3['score2_V'].astype(float).std()):.4f}")
    return k


@clause("§8.3", "BH-FDR(q=0.10) — 단측 '알파>0' · 주 실험 3 + 어블레이션 4 를 한 패밀리로")
def c83():
    k = Chk()
    k.eq("BH_FDR_Q", G["BH_FDR_Q"], 0.10)

    p_neg = G["_pval_from_t"](-4.0, 40)
    p_pos = G["_pval_from_t"](+4.0, 40)
    k.add("t = −4 (강한 음의 알파) → p 가 1 에 가깝다(단측)", p_neg > 0.99,
          f"p(t=−4) = {p_neg:.6f} · 양측이면 ≈0.0003 으로 '유의' 오판")
    k.add("t = +4 → p 가 0 에 가깝다", p_pos < 0.001, f"p(t=+4) = {p_pos:.6f}")

    # BH 절차 자체 — 손계산과 대조
    #  m=5, q=0.10 → BH 임계 0.02/0.04/0.06/0.08/0.10.
    #  p(3)=0.04 ≤ 0.06 이 성립하는 최대 rank 이므로 상위 3개가 기각된다.
    ps = [0.001, 0.02, 0.04, 0.30, 0.60]
    got = G["bh_fdr"](ps, q=0.10)
    want = [True, True, True, False, False]
    k.add("BH 절차 판정", list(map(bool, got)) == want,
          f"p={ps} → {list(map(bool, got))} (기대 {want})")
    #  검정력 확인 — 임계를 넘는 p 는 반드시 기각되어야 한다
    got2 = G["bh_fdr"]([0.07, 0.30, 0.50, 0.70, 0.90], q=0.10)
    k.add("BH 검정력 확인 — 최소 p 가 임계(0.02)를 넘으면 전부 기각",
          not any(map(bool, got2)), f"p[0]=0.07 → {list(map(bool, got2))}")

    # 패밀리 구성: 주 실험 3 + X1~X4 + 차이검정 = 8
    G["EXPERIMENTS"].clear()
    for nm, t in (("V-full", 2.5), ("VQ-full", 2.2), ("VQF-full", 2.4),
                  ("X1", 1.8), ("X2", 1.2), ("X3", 0.9), ("X4", 2.0)):
        G["EXPERIMENTS"][nm] = {"name": nm, "net": {}, "gross": {}, "R": None,
                                "t": t, "p": G["_pval_from_t"](t, 40), "n": 40}
    extra = {"name": "VQF-full−VQ-full(차이)", "t": 0.4,
             "p": G["_pval_from_t"](0.4, 40), "n": 40}
    res = G["report_bh_fdr"](["V-full", "VQ-full", "VQF-full", "X1", "X2", "X3", "X4"],
                             extra_tests=[extra])
    k.eq("패밀리 크기 = 주3 + 어블4 + 차이1", len(res), 8)
    k.add("차이검정이 같은 패밀리에 들어간다", "VQF-full−VQ-full(차이)" in res,
          f"패밀리={sorted(res)}")

    # ── paired_diff_test 가 '평균'이 아니라 't 통계량'을 돌려주는가 ─────────────────────
    #   hac_tstat 는 (평균, t) 를 준다. 언패킹을 뒤집으면 t 자리에 평균(≈0.05)이 들어가고
    #   p ≈ 0.48 이 되어 §9-C2 는 영영 통과 못 하고 §10.4 ② 는 항상 발동한다.
    m = 40
    idx = pd.date_range("2016-03-01", periods=m, freq="QS")
    rng = np.random.default_rng(11)
    base = rng.normal(0.02, 0.08, m)
    G["EXPERIMENTS"]["AA"] = {"name": "AA", "net": {}, "gross": {},
                              "R": pd.DataFrame({"rebal": idx, "ret": base + 0.05}),
                              "t": np.nan, "p": np.nan, "n": m}
    G["EXPERIMENTS"]["BB"] = {"name": "BB", "net": {}, "gross": {},
                              "R": pd.DataFrame({"rebal": idx, "ret": base}),
                              "t": np.nan, "p": np.nan, "n": m}
    dt = G["paired_diff_test"]("AA", "BB")
    k.eq("차이의 평균 = +0.05", dt["mean"], 0.05, tol=1e-9)
    k.add("t 는 평균이 아니라 평균/HAC표준오차 (차이가 결정적이면 |t| 가 크다)",
          np.isfinite(dt["t"]) and dt["t"] > 5.0 and abs(dt["t"] - dt["mean"]) > 1.0,
          f"t={dt['t']:.3f} · mean={dt['mean']:.5f} · p={dt['p']:.2e} "
          f"(언패킹이 뒤집히면 t=mean=0.05 → p≈0.48)")
    k.add("결정적인 차이는 p 가 0 에 가깝다", dt["p"] < 0.01, f"p={dt['p']:.3e}")
    return k


@clause("§8.4", "강건성 축 — U-200 크기 · 보유종목수 · 수급창 · 리밸 시점 ±5거래일")
def c84():
    k = Chk()
    k.eq("SENS_U200_SIZES", tuple(G["SENS_U200_SIZES"]), (150, 200, 300))
    k.eq("SENS_FINAL_SIZES", tuple(G["SENS_FINAL_SIZES"]), (20, 30, 40))
    k.eq("SENS_FLOW_WINDOWS", tuple(G["SENS_FLOW_WINDOWS"]), (20, 60, 120))
    k.eq("SENS_REBAL_SHIFTS", tuple(G["SENS_REBAL_SHIFTS"]), (-5, 0, 5))
    k.add("기준값이 민감도 축의 가운데에 있다",
          G["U200_N"] in G["SENS_U200_SIZES"] and G["FINAL_N"] in G["SENS_FINAL_SIZES"]
          and G["FLOW_WINDOW_DAYS"] in G["SENS_FLOW_WINDOWS"],
          f"U200={G['U200_N']} · FINAL={G['FINAL_N']} · FLOW={G['FLOW_WINDOW_DAYS']}")
    k.eq("INVVOL_WINDOW_DAYS", G["INVVOL_WINDOW_DAYS"], 120)

    # 민감도 실행이 실제로 다른 결과를 내는가(=축이 살아 있는가)
    n = 400
    days = bdays("2019-01-02", 400)
    px = mk_prices([f"{i:06d}" for i in range(1, 6)], days)
    G["set_trading_days"](px)
    cal = G["qvf_rebal_calendar"](px, "2019-06-01", "2020-06-30")
    reb = [str(t.date()) for t in as_ts_s(cal["rebal"])]
    P = mk_grid(n, reb, sector="X", Z_V=[float(i) for i in range(n)], Z_Q=0.0, Z_F=0.0,
                dNONFIN=[float((i * 7) % n) for i in range(n)], dTONE_resid=np.nan,
                EXCLUDED=0, RULE3A_BLOCK=0, mktcap=1e9, adtv=1e10, cs_spread=0.01, vol_d=0.02)
    P = add_cells(P)
    P = P.drop(columns=["signal_date", "exec_date"]).merge(
        cal[["rebal", "signal_date", "exec_date"]], on="rebal", how="left")
    rng = np.random.default_rng(0)
    fwd = P[["code", "rebal"]].copy()
    fwd["fwd_ret"] = rng.normal(0.01, 0.10, len(fwd))
    G["set_delist_map"]({})
    s = {}
    for n2 in G["SENS_U200_SIZES"]:
        bt = G["run_experiment"](P, cal, fwd, "V", u200_n=n2, label=f"U{n2}")
        s[n2] = G["qperf_stats"](bt["returns"]).get("CAGR", float("nan"))
    k.add("U-200 크기를 바꾸면 성과가 실제로 달라진다(축이 살아 있다)",
          len({round(v, 8) for v in s.values()}) == len(s),
          " · ".join(f"U200={a}: CAGR {b*100:+.2f}%" for a, b in s.items()))
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §9 · §10
# ════════════════════════════════════════════════════════════════════════════════════════════
@clause("§9", "수급 축 채택 C1~C5 — 판정불가를 충족으로 세지 않는다")
def c9():
    k = Chk()
    G["EXPERIMENTS"].clear()
    G["EXPERIMENTS"]["VQ-full"] = {"name": "VQ-full", "net": {"Sharpe": 0.50}, "gross": {},
                                   "R": None, "t": 1.0, "p": 0.2, "n": 40}
    G["EXPERIMENTS"]["VQF-full"] = {"name": "VQF-full", "net": {"Sharpe": 0.80}, "gross": {},
                                    "R": None, "t": 1.5, "p": 0.1, "n": 40}
    G["EXPERIMENTS"]["VQF-full−VQ-full(차이)"] = {"name": "VQF-full−VQ-full(차이)", "net": {},
                                                 "gross": {}, "R": None, "t": 2.0, "p": 0.03,
                                                 "n": 40}
    cmp_res = {"overlap": {"VQ~VQF": 0.60}, "coverage": {"VQ": 0.40, "VQF": 0.45}}
    G["PHASE0_FLOW_OK"] = True
    G["FLOW_NONZERO_RATIO_PREREG"] = 0.40
    fdr = {"VQF-full−VQ-full(차이)": True, "VQF-full": True}
    v = G["report_flow_verdict"](cmp_res, fdr_pass=fdr)
    k.add("전부 충족 시 C1~C5 True", all(v[c] is True for c in ("C1", "C2", "C3", "C4", "C5")),
          f"{ {c: v[c] for c in ('C1','C2','C3','C4','C5')} }")
    k.add("adopt_flow True", v["adopt_flow"] is True, f"adopt_flow={v['adopt_flow']}")

    # C2 는 '차이의 유의성' — VQF 자신의 유의성으로는 통과하지 못한다
    v2 = G["report_flow_verdict"](cmp_res, fdr_pass={"VQF-full": True})
    k.add("차이검정이 패밀리에 없으면 C2 는 '판정 불가'(자기 유의성으로 대체하지 않는다)",
          v2["C2"] is None, f"C2={v2['C2']}")
    k.add("판정 불가가 있으면 채택 권고가 아니다", v2["adopt_flow"] is False,
          f"adopt_flow={v2['adopt_flow']}")

    # C3 중복률 0.85 경계
    v3 = G["report_flow_verdict"]({"overlap": {"VQ~VQF": 0.85}, "coverage": {"VQ": 0.4, "VQF": 0.45}},
                                  fdr_pass=fdr)
    k.add("중복률 0.85 → C3 미충족(< 0.85 여야 한다)", v3["C3"] is False, f"C3={v3['C3']}")

    # C4 사전등록 창 값 사용
    G["FLOW_NONZERO_RATIO_PREREG"] = 0.20
    G["FLOW_NONZERO_RATIO"] = 0.90
    v4 = G["report_flow_verdict"](cmp_res, fdr_pass=fdr)
    k.add("C4 는 사전등록 창(60일)의 값을 쓴다 — 강건성 실행값(0.90)을 읽지 않는다",
          v4["C4"] is False, f"C4={v4['C4']} · 사전등록 0.20 / 전역 폴백 0.90")
    G["FLOW_NONZERO_RATIO_PREREG"] = 0.40

    # C5 커버리지 격차 +10%p 경계
    v5 = G["report_flow_verdict"]({"overlap": {"VQ~VQF": 0.6}, "coverage": {"VQ": 0.40, "VQF": 0.55}},
                                  fdr_pass=fdr)
    k.add("커버리지 격차 +15%p → C5 미충족", v5["C5"] is False, f"C5={v5['C5']}")

    # flow_cov 게이트 미달이면 C1·C2 판정 불가
    G["PHASE0_FLOW_OK"] = False
    v6 = G["report_flow_verdict"](cmp_res, fdr_pass=fdr)
    k.add("flow_cov 미달 → C1·C2 판정 불가",
          v6["C1"] is None and v6["C2"] is None, f"C1={v6['C1']} C2={v6['C2']}")
    G["PHASE0_FLOW_OK"] = True
    return k


@clause("§10.4", "사전등록 폐기조건 ①②③ — 충족 시 실제로 멈춘다")
def c104():
    k = Chk()
    k.add("STOP_ON_KILL_CRITERIA 기본 True", G["STOP_ON_KILL_CRITERIA"] is True,
          f"{G['STOP_ON_KILL_CRITERIA']}")

    def setup(cagrs, mdd_full, mdd_x1, diff_mean, diff_sd, n=40):
        G["EXPERIMENTS"].clear()
        rng = np.random.default_rng(3)
        base = rng.normal(0.02, 0.08, n)
        for nm, c in cagrs.items():
            G["EXPERIMENTS"][nm] = {
                "name": nm, "gross": {}, "R": pd.DataFrame(
                    {"rebal": pd.date_range("2016-03-01", periods=n, freq="QS"),
                     "ret": base}),
                "net": {"CAGR": c, "MDD": mdd_full if nm == "VQ-full" else np.nan,
                        "Sharpe": 0.5},
                "t": 1.0, "p": 0.2, "n": n}
        G["EXPERIMENTS"]["X1"] = {
            "name": "X1", "gross": {},
            "R": pd.DataFrame({"rebal": pd.date_range("2016-03-01", periods=n, freq="QS"),
                               "ret": base - diff_mean + rng.normal(0, diff_sd, n)}),
            "net": {"CAGR": 0.05, "MDD": mdd_x1, "Sharpe": 0.4}, "t": 1.0, "p": 0.2, "n": n}

    # ① 세 변형 모두 비용 후 CAGR ≤ 0
    setup({"V-full": -0.03, "VQ-full": -0.02, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
    G["STOP_ON_KILL_CRITERIA"] = False
    out = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("① 세 변형 모두 음의 CAGR → 폐기조건 충족", out["all_alpha_dead"] is True, f"{out}")

    setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
    out2 = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("① 하나라도 양의 CAGR → 미충족", out2["all_alpha_dead"] is False, f"{out2}")

    # ② 깔때기 기여가 '미미' = 차이의 단측 p ≥ 0.10
    setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.40, -0.50, 0.0005, 0.05)
    out3 = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("② 차이가 0 에 가까우면 '미미'로 판정", out3["funnel_worthless"] is True,
          f"funnel_worthless={out3['funnel_worthless']}")
    setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.40, -0.50, 0.05, 0.01)
    out4 = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("② 차이가 뚜렷하면 미충족(검정력 확인)", out4["funnel_worthless"] is False,
          f"funnel_worthless={out4['funnel_worthless']}")

    # ③ MDD 개선 없음 (MDD 는 음수 — full 이 더 깊으면 개선 실패)
    setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.50, -0.40, 0.05, 0.01)
    out5 = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("③ full MDD(−50%)가 X1(−40%)보다 깊다 → 개선 실패로 판정",
          out5["exclusion_no_mdd_help"] is True, f"{out5['exclusion_no_mdd_help']}")
    setup({"V-full": 0.03, "VQ-full": 0.05, "VQF-full": 0.02}, -0.30, -0.40, 0.05, 0.01)
    out6 = G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    k.add("③ full MDD(−30%)가 X1(−40%)보다 얕다 → 개선 있음",
          out6["exclusion_no_mdd_help"] is False, f"{out6['exclusion_no_mdd_help']}")

    # 실제로 멈추는가
    G["STOP_ON_KILL_CRITERIA"] = True
    setup({"V-full": -0.03, "VQ-full": -0.02, "VQF-full": -0.01}, -0.40, -0.50, 0.05, 0.01)
    halted = False
    try:
        G["report_preregistration_kill"](["V-full", "VQ-full", "VQF-full"], "VQ-full", "X1")
    except G["KillCriteria"]:
        halted = True
    k.add("폐기조건 충족 시 KillCriteria 로 중단(편입 종목표를 출력하지 않는다)", halted,
          f"halted={halted}")
    return k


@clause("§10.1", "임의선택 원장 · §10.2 귀속 · §10.3 산출물 — 보고 함수가 실제로 돈다")
def c101():
    k = Chk()
    keep = G["LOG"].min
    try:
        G["LOG"].min = 99
        for fname in ("report_discretion_ledger", "report_cell_ladder", "report_dataflow_map"):
            try:
                G[fname]()
                ok, err = True, "ok"
            except Exception as e:                                # noqa
                ok, err = False, f"{type(e).__name__}: {e}"
            k.add(f"{fname}() 실행", ok, err)
    finally:
        G["LOG"].min = keep

    # §10.3-9 최종 편입 종목표 — 폐기 판정 전에는 정상 출력되어야 한다
    n = 40
    P = mk_grid(n, ["2020-03-01"], sector="X", mktcap=1e9, adtv=5e8,
                score1_V=[float(i) for i in range(n)], score2_V=[float(i) for i in range(n)],
                dNONFIN=1.0, dTONE_resid=0.5, n_reports=1,
                _sel=[i >= n - 30 for i in range(n)])
    sec = pd.DataFrame({"code": P["code"].unique(), "name": "테스트종목"})
    try:
        out = G["report_final_holdings"](P, "V", "_sel", sec)
        k.eq("최종 편입 종목표 행수", len(out), 30)
    except Exception as e:                                        # noqa
        k.add("최종 편입 종목표 산출", False, f"{type(e).__name__}: {e}")
    return k


@clause("§구조", "정의되지 않은 전역 참조 · 성과지표 키 오타 — 조용히 nan/NameError 가 되는 부류")
def cstruct():
    import builtins
    import dis as _dis

    k = Chk()
    src = open(TARGET, encoding="utf-8").read()
    code = compile(src, "qvf.py", "exec")

    seen: set = set()
    undefined: Dict[str, str] = {}

    def walk(co, where: str):
        if id(co) in seen:
            return
        seen.add(id(co))
        for ins in _dis.get_instructions(co):
            if ins.opname in ("LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"):
                nm = ins.argval
                if not isinstance(nm, str) or nm.startswith("__"):
                    continue
                if nm in G or hasattr(builtins, nm):
                    continue
                undefined.setdefault(nm, where)
        for c in co.co_consts:
            if hasattr(c, "co_code"):
                walk(c, getattr(c, "co_qualname", None) or getattr(c, "co_name", where))

    walk(code, "<module>")
    # 조립본은 조건부 import 로 이름을 만들기도 한다 — 실제 실행 네임스페이스(G)에 없는 것만 남는다.
    k.add("함수 본문에서 참조하는 전역이 모두 정의되어 있다", not undefined,
          "미정의 전역 없음" if not undefined else
          " · ".join(f"{n} (in {w})" for n, w in sorted(undefined.items())[:12]))

    # qperf_stats 의 키는 대문자다. 소문자로 조회하면 조용히 nan 이 찍힌다(크래시하지 않는다).
    stats_keys = set(G["qperf_stats"](pd.DataFrame(
        {"ret": [0.01] * 20, "n": [10] * 20, "turnover": [0.1] * 20, "cost": [0.001] * 20})))
    bad = []
    for mobj in re.finditer(r"(_s\w*|s|stats|perf)\.get\(\s*['\"]([A-Za-z가-힣_]+)['\"]", src):
        key = mobj.group(2)
        if key.lower() in {"cagr", "sharpe", "mdd", "sortino", "calmar"} and key not in stats_keys:
            bad.append(key)
    k.add("성과지표 딕셔너리를 잘못된 키로 조회하지 않는다", not bad,
          f"성과 키 집합에 없는 조회 {sorted(set(bad))}" if bad else
          f"이상 없음 (키 예: {sorted(kk for kk in stats_keys if kk.isascii())[:5]})")
    return k


# ════════════════════════════════════════════════════════════════════════════════════════════
#  실행
# ════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: List[str]) -> int:
    global G, pd, np
    G = load_module()
    pd, np = G["pd"], G["np"]
    globals()["pd"], globals()["np"] = pd, np

    want = [a.lstrip("§") for a in argv[1:]]
    sel = [(cid, t, fn) for cid, t, fn in CASES
           if not want or any(cid.lstrip("§").startswith(w) for w in want)]

    W = 96
    print("=" * W)
    print("QVF-FUNNEL v1.0 — 명세 전수조사 (§3.1 ~ §10.4)")
    print(f"대상: {TARGET}")
    print("=" * W)

    n_pass = n_fail = n_err = 0
    failures: List[str] = []
    for cid, title, fn in sel:
        try:
            k = fn()
            ok = k.passed
        except Exception:                                       # noqa
            n_err += 1
            print(f"\n■ {cid}  {title}\n   ✘ ERROR")
            print("   " + traceback.format_exc().replace("\n", "\n   "))
            failures.append(f"{cid} (ERROR)")
            continue
        mark = "✔ PASS" if ok else "✘ FAIL"
        print(f"\n■ {cid}  {title}   → {mark}")
        for name, sub_ok, ev in k.rows:
            print(f"   {'✔' if sub_ok else '✘'} {name}")
            if ev:
                print(f"       {ev}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1
            failures += [f"{cid} · {name}" for name, s, _e in k.rows if not s]

    print("\n" + "=" * W)
    print(f"조항 {len(sel)}개 — 통과 {n_pass} · 실패 {n_fail} · 오류 {n_err}")
    if failures:
        print("실패 목록:")
        for f in failures:
            print(f"  ✘ {f}")
    print("=" * W)
    return 0 if (n_fail == 0 and n_err == 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
