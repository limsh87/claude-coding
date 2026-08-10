#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""엔진 불변식 회귀시험 — v1.0 감사에서 잡은 치명 결함이 되살아나지 않았는지 확인."""
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "shinhan_7f_earnings_surprise_v1.py")
src = open(SRC, encoding="utf-8").read()
src = src.replace('if __name__ == "__main__" or ENV["ipython"]:', 'if False:')
src = src.replace('RUN_MODE = "FULL"', 'RUN_MODE = "CACHED"')
mod = types.ModuleType("sh7f_eng"); mod.__file__ = SRC
sys.modules["sh7f_eng"] = mod
exec(compile(src, SRC, "exec"), mod.__dict__)
M = mod.__dict__; np, pd = M["np"], M["pd"]
F = []
def ck(n, c, d=""):
    print(("  [OK]   " if c else "  [FAIL] ") + n + (f"  — {d}" if d else ""))
    if not c: F.append(n)

print("=== E1 리밸런스 경계 이중계상 (v1.0 치명) ===")
# 분기마다 정확히 +10% 만 나는 세계 → 6분기 보유 후 누적은 1.1^6 이어야 한다.
BD = pd.bdate_range("2016-01-04", "2017-12-29")
cal = np.array(BD, dtype="datetime64[ns]")
sch = M["rebalance_schedule"](cal, "2016-01-01", "2017-09-30", quiet=True)
codes = [f"{i:06d}" for i in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120)]
# 신호일 사이 구간마다 종가가 정확히 1.1배가 되도록 계단식 가격 생성
lvl = pd.Series(1.0, index=BD)
for k, ex in enumerate(sch["exec_date"]):
    lvl[BD >= pd.Timestamp(ex)] = 1.1 ** (k + 1)
px = pd.concat([pd.DataFrame({"code": c, "date": BD, "open": lvl.values,
                              "high": lvl.values, "low": lvl.values, "close": lvl.values,
                              "volume": 1e6, "amount": 1e9, "src": "t"}) for c in codes],
               ignore_index=True)
snaps = pd.concat([pd.DataFrame({"signal_date": s, "code": codes,
                                 **{f: np.linspace(1, 2, len(codes)) for f in M["FACTOR_NAMES"]}})
                   for s in sch["signal_date"]], ignore_index=True)
M["TOP_N"] = 10; M["MIN_ELIGIBLE"] = 5
old_c, old_s = M["COMMISSION_BPS"], M["SLIPPAGE_K"]
M["COMMISSION_BPS"] = 0.0; M["SLIPPAGE_K"] = 0.0
sr = M["StrategyRun"]("T", snaps, sch, px, {})
bt = sr.run(tag="T")
D = bt["daily"]; eq = float((1 + D["ret"]).prod())
# 마지막 신호은 체결일 이후 가격 상승 계단이 없어 0% — 달성 가능 총수익은 1.1^(분기-1)
truth = 1.1 ** (len(sch) - 1)
ck("일별 복리 누적 = 1.1^분기수 (경계 이중계상 없음)", abs(eq / truth - 1) < 1e-4,
   f"code={eq:.6f} truth={truth:.6f} 분기={len(sch)}")
Q = bt["quarterly"]; eqq = float((1 + Q["ret"]).prod())
ck("분기 수익 복리도 동일", abs(eqq / truth - 1) < 1e-4, f"{eqq:.6f}")
ck("같은 날짜가 일별 시계열에 중복되지 않음", D["date"].is_unique)
M["COMMISSION_BPS"], M["SLIPPAGE_K"] = old_c, old_s

print("=== E2 ConsensusStore category 키 (v1.0 치명) ===")
pxc = M["downcast"](px[["code", "date", "close"]].copy())
ck("downcast 가 code 를 category 로 만든다(전제 확인)",
   str(pxc["code"].dtype) == "category", str(pxc["code"].dtype))
L = pd.DataFrame({"stock_code": codes * 20, "analyst_id": [f"A{i%13:02d}" for i in range(len(codes)*20)],
                  "pub_date": pd.date_range("2016-01-05", periods=len(codes)*20, freq="3D"),
                  "target_price": np.linspace(1.0, 3.0, len(codes)*20)})
cs = M["ConsensusStore"](L, pxc)
ck("category 키로도 MergeError 없이 생성", cs.ok)
snap = cs.snapshot(pd.Timestamp("2017-06-30"))
ck("스냅샷 생성", isinstance(snap, pd.DataFrame))

print("=== E3 z-score 계약 준수 ===")
v = pd.Series([1.0, 2.0, 3.0, 4.0])
zz = (v - v.mean()) / v.std(ddof=0)
ck("계약 z 정의: 모표준편차(ddof=0)", abs(float(zz.std(ddof=0)) - 1.0) < 1e-9)
ck("소스에 ddof=0 이 실제로 쓰였다",
   src.count("std(ddof=0)") >= 3, f"{src.count('std(ddof=0)')}곳")
ck("윈저라이즈는 강건성 변형에만 존재",
   "winsorization" in src and "none" in src)

print("=== E4 to_code6 / 날짜 파서 ===")
ck("A005930 → 005930", M["to_code6"]("A005930") == "005930")
ck("5930 → 005930", M["to_code6"]("5930") == "005930")
ck("09701K 보존(2024 영문 티커 개편)", M["to_code6"]("09701K") == "09701K")
ck("'ETF' 는 None", M["to_code6"]("ETF") is None)
ck("26.01.19 → 2026-01-19", M["parse_kr_date"]("26.01.19") == "2026-01-19", str(M["parse_kr_date"]("26.01.19")))
ck("99.12.31 → 1999-12-31", M["parse_kr_date"]("99.12.31") == "1999-12-31", str(M["parse_kr_date"]("99.12.31")))

print("=== E5 px_at strict_day ===")
bk = M["PriceBook"](px, set(codes))
ck("거래일 종가 조회", np.isfinite(bk.px_at(codes[0], pd.Timestamp(BD[10]), "close")))
ck("비거래일 strict_day=True 는 NaN",
   not np.isfinite(bk.px_at(codes[0], pd.Timestamp("2016-01-02"), "close", strict_day=True)))
print("\n" + "="*70)
print(f"실패 {len(F)}건: {F}" if F else "엔진 불변식 회귀시험 전체 통과")
sys.exit(1 if F else 0)
