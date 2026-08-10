#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.1 L1 데이터층 회귀시험 — 실제 실패 시나리오를 합성 데이터로 재현해 검증한다.

시험 대상
  T1 다중 루트 marcap 재귀 발견 (v1.0 이 못 본 '다른 루트'를 보는가)
  T2 MarketcapSpine 6단 체인 (marcap 성공 / 전부 실패 → liq_proxy / 전부 없음)
  T3 거래캘린더 부트스트랩 + 리밸런스 + 재정렬 + 신호일 리맵
  T4 price_gap_plan — 상장/폐지 창 기준 커버리지 (v1.0 병목의 정면 검증)
  T5 repair_price_cliffs — 액면분할 방향·정리매매 구분
  T6 build_universes — 시총 0시점에서도 예외 없이 진행
  T7 AttemptLedger — 실패 횟수별 백오프 · 영구제외
  T8 DartBudget — 참고치를 넘어도 020 이 아니면 계속 쓴다
"""
import os
import sys
import types
import shutil
import tempfile
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "shinhan_7f_earnings_surprise_v1.py")
ROOT = tempfile.mkdtemp(prefix="sh7f_t_")
DRIVE_A = os.path.join(ROOT, "driveA", "tcd_cache")     # 비어 있는 로컬 루트 (v1.0 이 고른 쪽)
DRIVE_B = os.path.join(ROOT, "driveB", "tcd_cache")     # marcap 이 있는 드라이브 루트
for base in (DRIVE_A, DRIVE_B):
    for ns in ("_shared", "shinhan_7f"):
        os.makedirs(os.path.join(base, ns, "table"), exist_ok=True)
        os.makedirs(os.path.join(base, ns, "index"), exist_ok=True)

# ── 모듈 로드: main() 자동실행을 막고 함수만 가져온다 ────────────────────────────────────────
src = open(SRC, encoding="utf-8").read()
src = src.replace('if __name__ == "__main__" or ENV["ipython"]:',
                  'if False:')
src = src.replace('RUN_MODE = "FULL"', 'RUN_MODE = "CACHED"')     # 네트워크 0회
src = src.replace('GDRIVE_ROOT_CANDIDATES = [',
                  'GDRIVE_ROOT_CANDIDATES = [%r, %r,' % (DRIVE_A, DRIVE_B))
mod = types.ModuleType("sh7f")
mod.__file__ = SRC
sys.modules["sh7f"] = mod
exec(compile(src, SRC, "exec"), mod.__dict__)
M = mod.__dict__
np, pd = M["np"], M["pd"]

FAILS = []


def check(name, cond, detail=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────────────────────
BDAYS = pd.bdate_range("2015-01-01", "2026-08-31")
CODES = [f"{i:06d}" for i in range(1000, 1000 + 300 * 10, 10)]     # 300 종목, 끝자리 0


def make_marcap_year(y):
    days = BDAYS[BDAYS.year == y]
    rows = []
    for i, c in enumerate(CODES):
        px = 10000.0 + i * 37
        sh = 1e6 * (i + 1)
        rows.append(pd.DataFrame({
            "date": days, "code": c, "name": f"N{c}",
            "market": "KOSPI" if i < 150 else "KOSDAQ",
            "close": px, "open": px, "high": px, "low": px,
            "volume": 1000.0 + i, "amount": (1000.0 + i) * px,
            "marcap": px * sh, "stocks": sh}))
    return pd.concat(rows, ignore_index=True)


print("\n=== T1 다중 루트 marcap 재귀 발견 ===")
# marcap 을 '비어 있지 않은 쪽(B)'의 깊은 하위 폴더에 둔다 — v1.0 은 table 1단만 봤다.
deep = os.path.join(DRIVE_B, "_shared", "table", "marcap", "byyear")
os.makedirs(deep, exist_ok=True)
for y in (2015, 2016, 2017):
    make_marcap_year(y).to_parquet(os.path.join(deep, f"marcap_{y}.parquet"), index=False)
# 쓰기 루트 결정 + 읽기 루트 등록
root, mode, adopts = M["discover_roots"]()
M["VAULT"] = M["Vault"](root, mode)
M["VAULT"].load_index("shared")
M["VAULT"].load_index("private")
check("쓰기 루트는 적재량이 많은 쪽(B)을 고른다", os.path.realpath(root) == os.path.realpath(DRIVE_B),
      f"root={root}")
check("읽기 루트가 2곳 이상 등록된다", len(M["READ_ROOTS"]) >= 2, str(M["READ_ROOTS"]))
ys = M["MARCAP"].years_available()
check("깊은 하위폴더의 marcap 3개 연도를 발견", ys == [2015, 2016, 2017], str(ys))
d2016 = M["MARCAP"].year(2016)
check("marcap 정규화: stocks→shares 매핑", d2016 is not None and "shares" in d2016.columns)

print("\n=== T2 MarketcapSpine 6단 체인 ===")
sig_dates = [pd.Timestamp(x) for x in ("2016-03-31", "2016-06-30", "2016-09-30", "2016-12-30")]
sp = M["MarketcapSpine"]()
panel = sp.build(sig_dates, pxc=None)
check("marcap 경로로 4개 시점 전부 확보", len(sp.per_date) == 4, str(sp.per_date))
check("등급이 PIT_EXACT", len(panel) and set(panel["grade"]) == {"PIT_EXACT"})
check("size_rank 이 채워진다", len(panel) and panel["size_rank"].notna().all())
# marcap 을 못 쓰는 상황 → 거래대금 프록시로 폴백
pxc_fake = pd.concat([
    pd.DataFrame({"code": c, "date": BDAYS[(BDAYS >= "2016-01-01") & (BDAYS <= "2017-01-31")],
                  "open": 1.0, "high": 1.0, "low": 1.0, "close": 100.0 + i,
                  "volume": 10.0, "amount": (100.0 + i) * 10.0, "src": "cache"})
    for i, c in enumerate(CODES)], ignore_index=True)
sp2 = M["MarketcapSpine"]()
M["MCAP_SPINE_SOURCES"].clear()
M["MCAP_SPINE_SOURCES"].extend(["liq_proxy"])
panel2 = sp2.build(sig_dates, pxc=pxc_fake)
check("전 경로 실패 시 거래대금 프록시로 4개 시점 확보", len(sp2.per_date) == 4)
check("프록시 등급 표기가 RANK_ONLY_LIQUIDITY",
      len(panel2) and set(panel2["grade"]) == {"RANK_ONLY_LIQUIDITY"})
check("프록시는 marcap 값을 만들지 않는다(F6/F7 오염 방지)",
      len(panel2) and panel2["marcap"].isna().all())
sp3 = M["MarketcapSpine"]()
panel3 = sp3.build(sig_dates, pxc=None)          # 소스도 데이터도 없음
check("아무것도 못 만들어도 예외 없이 빈 패널 반환", isinstance(panel3, pd.DataFrame))
M["MCAP_SPINE_SOURCES"].clear()
M["MCAP_SPINE_SOURCES"].extend(["marcap", "cache", "krx_bld", "krx_api", "pykrx",
                                "fdr_apx", "liq_proxy"])

print("\n=== T3 캘린더 부트스트랩 · 리밸런스 · 재정렬 ===")
cal0 = M["bootstrap_calendar"](pxc_fake, "2016-01-01", "2017-01-31")
check("캐시 일봉에서 캘린더 확보", len(cal0) > 200, f"{len(cal0)}일")
sch0 = M["rebalance_schedule"](cal0, "2016-01-01", "2016-12-31")
#  (12월 신호는 익거래일이 캘린더 안에 있어야 성립 — 그래서 캘린더는 2017-01 까지)
check("2016년 리밸런스 4분기", len(sch0) == 4, str(list(sch0["yq"])))
check("신호일 < 체결일", bool((sch0["signal_date"] < sch0["exec_date"]).all()))
# 실제 캘린더에서 3월 마지막 영업일이 하루 빠진 상황 → 재정렬 + 리맵
cal1 = np.array([d for d in pd.DatetimeIndex(cal0)
                 if d != pd.Timestamp(sch0.loc[0, "signal_date"])], dtype="datetime64[ns]")
sch1, remap = M["realign_schedule"](sch0, cal1, "2016-01-01", "2016-12-31")
check("재정렬 후에도 4분기 유지", len(sch1) == 4)
check("사라진 신호일이 리맵에 잡힌다", len(remap) == 1, str(remap))
mem = pd.DataFrame({"signal_date": [sch0.loc[0, "signal_date"]] * 3, "code": CODES[:3]})
mem2 = M["remap_signal_dates"](mem, remap)
check("멤버십 신호일이 함께 이동",
      pd.Timestamp(mem2["signal_date"].iloc[0]) == remap[pd.Timestamp(sch0.loc[0, "signal_date"])])

print("\n=== T4 price_gap_plan (v1.0 병목의 정면 검증) ===")
cal_full = np.array(BDAYS, dtype="datetime64[ns]")
sec = pd.DataFrame({
    "code":  ["000010", "000020", "000030", "000040", "701016", "000055"],
    "name":  ["완결주", "2020상장", "2018폐지", "미보유",  "신주인수권", "우선주"],
    "market": ["KOSPI"] * 6,
    "listing_date": [pd.Timestamp("2010-01-04"), pd.Timestamp("2020-01-06"),
                     pd.Timestamp("2010-01-04"), pd.Timestamp("2010-01-04"),
                     pd.Timestamp("2015-01-02"), pd.Timestamp("2010-01-04")],
    "delisting_date": [pd.NaT, pd.NaT, pd.Timestamp("2018-06-29"), pd.NaT, pd.NaT, pd.NaT]})
win = BDAYS[(BDAYS >= "2015-05-01") & (BDAYS <= "2026-07-31")]
have = []
have.append(pd.DataFrame({"code": "000010", "date": win}))                       # 전구간 보유
have.append(pd.DataFrame({"code": "000020",                                      # 상장 후 전부
                          "date": win[win >= "2020-01-06"]}))
have.append(pd.DataFrame({"code": "000030",                                      # 폐지 전 전부
                          "date": win[win <= "2018-06-29"]}))
pxc2 = pd.concat(have, ignore_index=True).assign(close=1000.0, open=1000.0, high=1000.0,
                                                 low=1000.0, volume=1.0, amount=1000.0,
                                                 src="cache")
M["LEDGER"] = M["AttemptLedger"]()
todo, stats = M["price_gap_plan"](sec["code"].tolist(), "2015-05-01", "2026-07-31",
                                 sec, pxc2, cal_full)
tc = {c for c, _, _ in todo}
print("     stats:", stats)
check("전구간 보유 종목은 재조회하지 않는다", "000010" not in tc)
check("★2020 상장 종목에 2016년을 요구하지 않는다(v1.0 병목 원인 ①)", "000020" not in tc)
check("★2018 폐지 종목에 2026년을 요구하지 않는다(v1.0 병목 원인 ②)", "000030" not in tc)
check("정말 없는 종목만 수집 대상", tc == {"000040"}, str(tc))
check("신주인수권(7xxxxx)은 구조적 제외",
      any(k.startswith("구조적제외") for k in stats))
check("우선주도 구조적 제외", stats.get("구조적제외:우선주/ETP/스팩", 0) >= 1)
# v1.0 규칙을 그대로 재현해 대비 확인
v10_todo = []
for c in sec["code"]:
    g = pxc2[pxc2["code"] == c]["date"]
    mn, mx = (g.min(), g.max()) if len(g) else (None, None)
    if mn is None:
        v10_todo.append(c)
    elif mn > pd.Timestamp("2015-05-01") + pd.Timedelta(days=10):
        v10_todo.append(c)
    elif mx < pd.Timestamp("2026-07-31") - pd.Timedelta(days=5):
        v10_todo.append(c)
check("v1.0 규칙이면 상장·폐지 종목까지 매번 재조회했다는 사실 확인",
      set(v10_todo) >= {"000020", "000030"}, f"v1.0 todo={v10_todo} vs v1.1 todo={sorted(tc)}")

print("\n=== T4b 커버리지 계산이 기대구간 안에서만 세는지 ===")
sec2 = pd.DataFrame({
    "code":  ["000060", "000070", "000080"],
    "name":  ["앞7년결손", "구간밖행", "중간공백"],
    "market": ["KOSPI"] * 3,
    "listing_date": [pd.Timestamp("2010-01-04"), pd.Timestamp("2022-01-03"),
                     pd.Timestamp("2010-01-04")],
    "delisting_date": [pd.NaT, pd.NaT, pd.NaT]})
h2 = [
    # 상장 2010 인데 캐시는 최근 3년만 → 앞 7년 결손이 반드시 잡혀야 한다
    pd.DataFrame({"code": "000060", "date": win[win >= "2023-08-01"]}),
    # 상장일이 2022 로 잘못 기록됐고 캐시에는 2015~2026 전체가 있다 → 구간 밖 행이
    # 커버리지를 부풀리지 못해야 한다(부풀면 '충분'으로 오판)
    pd.DataFrame({"code": "000070", "date": win}),
    # 상장 2010, 캐시는 앞뒤 끝은 있고 가운데 6년이 비었다 → 내부공백으로 잡혀야 한다
    pd.DataFrame({"code": "000080",
                  "date": win[(win <= "2016-06-30") | (win >= "2024-01-02")]}),
]
pxc3 = pd.concat(h2, ignore_index=True).assign(close=1000.0, open=1000.0, high=1000.0,
                                               low=1000.0, volume=1.0, amount=1000.0,
                                               src="cache")
M["LEDGER"] = M["AttemptLedger"]()
todo2, stats2 = M["price_gap_plan"](sec2["code"].tolist(), "2015-05-01", "2026-07-31",
                                    sec2, pxc3, cal_full)
t2 = {c for c, _, _ in todo2}
print("     stats:", stats2)
check("★앞 7년 결손을 잡아낸다", "000060" in t2)
check("★구간 밖 행이 커버리지를 부풀리지 않는다(잘못된 상장일)",
      stats2.get("캐시충분", 0) == 1 and "000070" not in t2,
      f"충분={stats2.get('캐시충분', 0)}, todo={sorted(t2)}")
check("★가운데 6년 공백을 잡아낸다", "000080" in t2)
check("결손 종목만 수집 대상", t2 == {"000060", "000080"}, str(sorted(t2)))

print("\n=== T5 repair_price_cliffs ===")
days = BDAYS[(BDAYS >= "2018-01-02") & (BDAYS <= "2018-12-28")]
split_pos = 60
cl = np.r_[np.full(split_pos, 2_650_000.0), np.full(len(days) - split_pos, 53_000.0)]
liq = np.r_[np.full(len(days) - 10, 5000.0), np.array([2000., 900., 400., 200., 100.,
                                                      60., 40., 25., 15., 10.])]
px_t = pd.concat([
    pd.DataFrame({"code": "005930", "date": days, "close": cl, "open": cl, "high": cl,
                  "low": cl, "volume": 100.0, "amount": cl * 100, "src": "marcap"}),
    pd.DataFrame({"code": "111110", "date": days, "close": liq, "open": liq, "high": liq,
                  "low": liq, "volume": 100.0, "amount": liq * 100, "src": "marcap"})],
    ignore_index=True)
out, cnt = M["repair_price_cliffs"](px_t.copy(), {"111110": pd.Timestamp("2018-12-28")})
print("     분류:", cnt)
s = out[out["code"] == "005930"].sort_values("date")
r = s["close"].pct_change().abs().max()
check("액면분할 절벽이 보정되어 하루 |수익|>50% 가 사라진다", r < 0.05, f"max|r|={r:.4f}")
check("보정 방향이 맞다(분할 전 가격이 53,000 수준으로 내려간다)",
      abs(float(s["close"].iloc[0]) - 53000.0) < 1.0, f"first={float(s['close'].iloc[0]):,.0f}")
check("분할 후 가격은 그대로", abs(float(s["close"].iloc[-1]) - 53000.0) < 1.0)
check("정리매매는 보정하지 않고 정리매매로 분류", cnt["정리매매"] >= 1 and cnt["기업행위보정"] == 1)

print("\n=== T5b 절벽 보정 엣지 (분할2회·역분할·근접절벽·첫행·마지막행) ===")
_days = pd.bdate_range("2018-01-02", "2020-12-31")
_n = len(_days)


def _mk(code, cl):
    return pd.DataFrame({"code": code, "date": _days, "close": cl, "open": cl,
                         "high": cl, "low": cl, "volume": 100.0, "amount": cl * 100,
                         "src": "t"})


_cases = {
    # 분할 10:1 후 다시 5:1 (같은 종목 2회)
    "000010": np.r_[np.full(200, 100000.0), np.full(300, 10000.0), np.full(_n - 500, 2000.0)],
    # 첫 행이 절벽 → 직전 가격이 없어 계산 불가. 예외 없이 무시돼야 한다.
    "000020": np.r_[np.full(1, 100000.0), np.full(_n - 1, 5000.0)],
    # 마지막 행이 절벽이고 비율이 단순비(1/10) → 표본이 없어도 기업행위로 인정한다(M3).
    "000030": np.r_[np.full(_n - 1, 10000.0), np.full(1, 1000.0)],
    # 마지막 행 절벽인데 단순비가 아니다(×0.37) → 실제 급락일 수 있으므로 보정 금지.
    "000060": np.r_[np.full(_n - 1, 10000.0), np.full(1, 3700.0)],
    # 18개월 데이터 공백 뒤 -75% → 거래일이 인접하지 않으므로 기업행위로 보지 않는다(C3).
    "000070": np.r_[np.full(200, 10000.0), np.full(_n - 200, 2500.0)],
    # 폐지일 미기록 정리매매(1000→300, 단순비 아님) → 실제 손실을 지워서는 안 된다(C3).
    "000080": np.r_[np.full(300, 1000.0), np.full(_n - 300, 300.0)],
    # 병합(역분할): 가격이 5배로 뛴다.
    "000040": np.r_[np.full(300, 2000.0), np.full(_n - 300, 10000.0)],
    # 절벽 2개가 10거래일 안에 붙어 있다 → 20일 고정창이면 서로를 오염시켜 둘 다 미분류.
    "000050": np.r_[np.full(200, 100000.0), np.full(10, 10000.0), np.full(_n - 210, 1000.0)],
}
_gapdays = pd.DatetimeIndex(list(_days[:200]) + list(_days[200:] + pd.Timedelta(days=550)))
_frames_t = []
for _k, _v in _cases.items():
    _dd = _gapdays if _k == "000070" else _days
    _frames_t.append(pd.DataFrame({"code": _k, "date": _dd, "close": _v, "open": _v,
                                   "high": _v, "low": _v, "volume": 100.0,
                                   "amount": _v * 100, "src": "t"}))
_px = pd.concat(_frames_t, ignore_index=True)
_out, _cnt = M["repair_price_cliffs"](_px.copy(), {})
for _code, _label, _tail in (("000010", "분할 2회 연속", 2000.0),
                             ("000040", "병합(역분할)", 10000.0),
                             ("000050", "근접 절벽 2개", 1000.0)):
    _s = _out[_out["code"] == _code].sort_values("date")
    _r = float(_s["close"].pct_change().abs().max())
    check(f"{_label}: 절벽 제거", _r < 0.05, f"max|r|={_r:.4f}")
    check(f"{_label}: 전 구간이 최종 스케일로 통일",
          abs(float(_s["close"].iloc[0]) - _tail) < 1.0
          and abs(float(_s["close"].iloc[-1]) - _tail) < 1.0,
          f"first={float(_s['close'].iloc[0]):,.0f} last={float(_s['close'].iloc[-1]):,.0f}")
check("첫 행 절벽은 예외 없이 무시", len(_out[_out["code"] == "000020"]) == _n)
check("마지막 행 절벽 + 단순비(1/10) → 기업행위로 보정(M3)",
      abs(float(_out[_out["code"] == "000030"].sort_values("date")["close"].iloc[0])
          - 1000.0) < 1.0,
      f"first={float(_out[_out['code'] == '000030'].sort_values('date')['close'].iloc[0]):,.0f}")
check("★단순비가 아닌 마지막 행 급락은 보정하지 않는다",
      abs(float(_out[_out["code"] == "000060"].sort_values("date")["close"].iloc[0])
          - 10000.0) < 1.0,
      f"first={float(_out[_out['code'] == '000060'].sort_values('date')['close'].iloc[0]):,.0f}")
# ★ C3: 데이터 공백 뒤 급락을 기업행위로 오분류하면 실제 손실이 0% 로 지워진다
_g = _out[_out["code"] == "000070"].sort_values("date")
check("★18개월 공백 뒤 -75% 를 기업행위로 오분류하지 않는다(실손실 보존)",
      abs(float(_g["close"].iloc[0]) - 10000.0) < 1.0,
      f"first={float(_g['close'].iloc[0]):,.0f} (보정되면 2,500 이 된다)")
_h = _out[_out["code"] == "000080"].sort_values("date")
check("★폐지일 미기록 정리매매(-70%)를 지우지 않는다",
      abs(float(_h["close"].iloc[0]) - 1000.0) < 1.0,
      f"first={float(_h['close'].iloc[0]):,.0f} (보정되면 300 이 된다)")

print("\n=== T6 build_universes 무예외 진행 ===")
M["SEC"] = sec
big_sec = pd.DataFrame({"code": CODES, "name": [f"N{c}" for c in CODES],
                        "market": ["KOSPI"] * 150 + ["KOSDAQ"] * 150,
                        "listing_date": pd.Timestamp("2010-01-04"), "delisting_date": pd.NaT})
sch_u = M["rebalance_schedule"](cal0, "2016-01-01", "2016-12-31", quiet=True)
k, cm, meta = M["build_universes"](sch_u, panel, big_sec)
check("정상 스파인이면 4분기 모두 유니버스 구성", meta["n_reconstructed"] == 4, str(meta))
check("K200 은 KOSPI 보통주 상위 200 (150개뿐이면 그만큼)",
      len(k) > 0 and k.groupby("signal_date")["code"].size().max() <= 200)
check("비교 유니버스도 구성", len(cm) > 0)
k0, cm0, meta0 = M["build_universes"](sch_u, pd.DataFrame(columns=M["MCAP_SPINE_COLS"]),
                                      big_sec)
check("★스파인이 완전히 비어도 예외 없이 반환(v1.0 은 RuntimeError)",
      isinstance(k0, pd.DataFrame) and len(meta0["missing"]) == 4, str(meta0["missing"]))

print("\n=== T7 AttemptLedger 백오프 ===")
L = M["AttemptLedger"]()
L.record("999990", False, "2016-01-01")
check("1회 실패 → 7일 백오프로 차단", L.blocked("999990", pd.Timestamp("2016-01-01")))
for _ in range(3):
    L.record("999990", False, "2016-01-01")
check("4회 실패 → 영구 제외", L._map["999990"]["permanent"] is True,
      str(L._map["999990"]["n_fail"]))
L.record("999980", True, "2016-01-01", "naver")
check("성공 시 차단 해제", not L.blocked("999980", pd.Timestamp("2016-01-01")))
check("성공 소스를 기억(다음 실행에 체인 헛돌기 제거)", L.best_src("999980") == "naver")
L2 = M["AttemptLedger"]()
L2.record("999970", False, "2020-01-01")
check("더 이른 구간을 새로 원하면 이전 실패는 근거가 아니다",
      not L2.blocked("999970", pd.Timestamp("2016-01-01")))

print("\n=== T8 DartBudget — 참고치를 넘어도 020 이 아니면 계속 ===")
M["DART_ADVISORY_DAILY"] = 100
M["DART_OFFICIAL_DAILY"] = 100
b = M["DartBudget"]()
b.n = 100
check("참고 잔량 0", b.remaining() == 0)
check("★DART_STOP_ONLY_ON_020=True 면 잔량 0에서도 계속 쓴다", b.take(1) is True)
M["DART_STOP_ONLY_ON_020"] = False
b2 = M["DartBudget"]()
b2.n = 100
check("옵션을 끄면 예전처럼 선제 중단", b2.take(1) is False)
b.preflight(1400, "테스트")

print("\n" + "=" * 78)
if FAILS:
    print(f"실패 {len(FAILS)}건: " + ", ".join(FAILS))
else:
    print("L1 회귀시험 전체 통과")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if FAILS else 0)
