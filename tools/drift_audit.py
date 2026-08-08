#!/usr/bin/env python3
"""하향 드리프트 감사 — 알파=0 널 테스트.

문제의식: 서로 다른 알파 아이디어를 10여 개 시험했는데 하나같이 성과가 안 나온다면,
아이디어가 아니라 **모든 아이디어가 공유하는 하네스**를 의심해야 한다.

방법: build/41_backtest.py 의 실제 함수를 **복제·수정 없이 그대로 exec** 해서 돌린다.
신호는 미래수익과 통계적으로 독립인 난수 → 참 알파는 정확히 0이다.
따라서 '적격 유니버스 동일가중 수익'과 백테스트 결과의 차이는 전부 엔진이 만든 인공 손익이다.

    python3 tools/drift_audit.py
"""
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

# ── 엔진 원본 로드 (헤더 상수도 소스에서 직접 읽는다 — 하드코딩하면 감사가 거짓말이 된다) ──
_HDR = (BUILD / "00_header.py").read_text()
G: dict = {"np": np, "pd": pd, "math": math, "Dict": dict}
for _name in ("PORTFOLIO_TOP_PCT", "PORTFOLIO_MAX_NAMES", "PORTFOLIO_MIN_NAMES",
              "POS_MAX_WEIGHT", "POS_MIN_WEIGHT", "POS_ADV_PARTICIPATION",
              "HOLD_MAX_MONTHS", "ACCOUNT_KRW", "MIN_ADV_KRW"):
    _m = re.search(rf"^{_name}\s*=\s*([0-9_.]+)", _HDR, re.M)
    if _m is None:
        raise RuntimeError(f"00_header.py 에서 {_name} 를 찾지 못했습니다.")
    _raw = _m.group(1).replace("_", "")
    G[_name] = float(_raw) if "." in _raw else int(_raw)

G["as_ts"] = lambda x: pd.Timestamp(x)


def _hac_tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 12:
        return (np.nan, np.nan)
    mu, n = x.mean(), len(x)
    e = x - mu
    L = max(0, min(int(np.floor(4 * (n / 100.0) ** (2 / 9.0))), n - 2))
    var = float(e @ e) / n
    for l in range(1, L + 1):
        var += 2 * (1 - l / (L + 1.0)) * float(e[l:] @ e[:-l]) / n
    return (float(mu), float(mu / math.sqrt(max(var, 1e-18) / n)))


G["hac_tstat"] = _hac_tstat
exec(compile((BUILD / "41_backtest.py").read_text(), "41_backtest.py", "exec"), G)

run_backtest, perf_stats = G["run_backtest"], G["perf_stats"]
size_positions, slippage = G["size_positions"], G["slippage"]


class _FakeUni:
    def __init__(self, delist=None):
        self._d = delist or {}

    def delisting_map(self):
        return self._d

    def audit_row(self, *a, **k):
        pass


def _ar1(rng, n_m, n_c, rho, sd=1.0):
    x = np.zeros((n_m, n_c))
    x[0] = rng.normal(0, sd, n_c)
    for t in range(1, n_m):
        x[t] = rho * x[t - 1] + rng.normal(0, sd * np.sqrt(1 - rho ** 2), n_c)
    return x


def make_panel(seed=7, n_c=700, n_m=120, mkt_mu=0.005, rho_sig=0.95, rho_de=0.90,
               floor_rate=0.06, delist_n=0):
    """참 알파 0 인 합성 패널.

    rho_sig=1.0 에 가까울수록 '천천히 변하는 펀더멘털 신호', 0 에 가까울수록 잡음 신호.
    수익률은 신호와 **완전히 독립**하게 생성한다 — 알파를 0으로 못박기 위함이다.
    """
    rng = np.random.default_rng(seed)
    months = pd.date_range("2016-08-31", periods=n_m, freq="ME")
    codes = [f"{i:06d}" for i in range(n_c)]
    f = rng.normal(mkt_mu, 0.055, n_m)
    beta = rng.normal(1.0, 0.3, n_c)
    R = beta[None, :] * f[:, None] + rng.normal(0, 0.11, (n_m, n_c))

    P = pd.DataFrame({"code": np.tile(codes, n_m),
                      "month": np.repeat(months, n_c),
                      "fwd_ret": R.ravel()})
    S = _ar1(rng, n_m, n_c, rho_sig).ravel()
    P["Signal_rank"] = pd.Series(S).groupby(P["month"].values).rank(pct=True).values
    P["Signal"] = P["Signal_rank"]
    P["adv20"] = np.tile(np.exp(rng.normal(np.log(2e9), 1.1, n_c)), n_m)   # 중앙값 20억원
    P["exec_px"] = 10000.0
    P["VETO"] = 1.0
    P["V6"] = 1.0
    fl = _ar1(rng, n_m, n_c, 0.95)
    P["FLOOR"] = (fl.ravel() > np.quantile(fl, 1 - floor_rate)).astype(float)
    P["dlog_E"] = 0.02 + 0.15 * _ar1(rng, n_m, n_c, rho_de).ravel()
    P["dlog_M"] = 0.00 + 0.20 * _ar1(rng, n_m, n_c, rho_de).ravel()

    delist = {}
    for c in rng.choice(codes, delist_n, replace=False):
        d = months[rng.integers(13, n_m - 1)]
        delist[c] = d
        P.loc[(P["code"] == c) & (P["month"] >= d), "fwd_ret"] = np.nan
    return P, months, delist


def _bench(P, months):
    """정답값: 적격(거부권·하한선 통과) 유니버스 동일가중. 알파 0 이면 여기에 붙어야 한다."""
    e = P[(P["VETO"] == 1) & (P["FLOOR"] == 1)]
    return e.groupby("month")["fwd_ret"].mean().reindex(months).fillna(0)


def ann(x):
    return (1 + x) ** 12 - 1


def run(P, months, delist, **kw):
    sec = pd.DataFrame({"code": sorted(P["code"].unique()), "market": "KOSPI"})
    bt = run_backtest(P, months, _FakeUni(delist), sec, **kw)
    R, H = bt["returns"], bt["holdings"]
    st = perf_stats(R)
    b = _bench(P, months)
    inv = H.groupby("month")["weight"].sum().reindex(months).fillna(0) if len(H) else pd.Series([np.nan])
    return {"월순": R["ret"].mean(), "월비용": R["cost"].mean(), "벤치": b.mean(),
            "드리프트연": ann(R["ret"].mean()) - ann(b.mean()),
            "n": R["n"].mean(), "투자비중": float(inv.mean()),
            "회전율": R["turnover"].mean(),
            "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe")}


def main():
    hr = "─" * 92
    print(hr)
    print("하향 드리프트 감사 — 참 알파 = 0 인 신호를 실제 엔진에 넣었을 때 무엇이 나오는가")
    print(hr)

    P, months, dl = make_panel(rho_sig=0.95)
    base = run(P, months, dl)
    B = base["벤치"]
    print(f"\n적격 유니버스 동일가중(정답값)  {B*100:+.3f}%/월  →  {ann(B)*100:+.2f}%/년")
    print(f"엔진이 뱉는 값                  {base['월순']*100:+.3f}%/월  →  CAGR {base['CAGR']*100:+.2f}%"
          f" · Sharpe {base['Sharpe']:+.3f}")
    print(f"인공 드리프트                   {(base['월순']-B)*100:+.3f}%/월  →  "
          f"{base['드리프트연']*100:+.2f}%p/년   ★ 알파가 0인데 이만큼 잃는다")

    print(f"\n{hr}\n[1] 신호 지속성별 — 회전율과 비용 (i.i.d. 신호는 회전율을 과대평가하므로 함께 본다)\n{hr}")
    print(f"{'신호 자기상관':>12} {'회전율/월':>10} {'실효보유':>9} {'월비용':>9} {'연비용':>9} "
          f"{'평균종목':>9} {'투자비중':>9} {'알파0 CAGR':>11}")
    for rho in (0.99, 0.95, 0.90, 0.80, 0.00):
        Px, mx, dx = make_panel(rho_sig=rho, rho_de=min(rho, 0.90))
        r = run(Px, mx, dx)
        lab = f"{rho:.2f}" if rho else "i.i.d."
        print(f"{lab:>12} {r['회전율']:>10.3f} {2/max(r['회전율'],1e-9):>8.1f}월 "
              f"{r['월비용']*100:>8.3f}% {ann(r['월비용'])*100:>8.2f}% {r['n']:>9.2f} "
              f"{r['투자비중']:>8.1%} {r['CAGR']*100:>10.2f}%")

    print(f"\n{hr}\n[2] SLIPPAGE_K 민감도 — 그 외 전부 원본 그대로\n{hr}")
    print(f"{'K':>8} {'월비용':>9} {'연비용':>9} {'드리프트/년':>12}  비고")
    for K, note in ((0.10, "★ 현재 코드값"), (0.05, ""), (0.025, "Almgren 상한권"),
                    (0.015, "Y·σ_daily ≈ 0.6 × 2.5% = 이론값"), (0.0, "슬리피지 0")):
        G["SLIPPAGE_K"] = K
        r = run(P, months, dl)
        print(f"{K:>8.3f} {r['월비용']*100:>8.3f}% {ann(r['월비용'])*100:>8.2f}% "
              f"{r['드리프트연']*100:>11.2f}%  {note}")
    G["SLIPPAGE_K"] = 0.10

    print(f"\n{hr}\n[3] 슬리피지 실측 — ACCOUNT_KRW = {G['ACCOUNT_KRW']:,}원\n{hr}")
    print(f"{'20일 평균거래대금':>20} {'비중':>6} {'주문금액':>13} {'참여율':>10} {'모델':>9} {'현실 추정':>10}")
    for advb, lab in ((3e8, "3억 (V6 하한)"), (1e9, "10억"), (2e9, "20억 (중앙값)"),
                      (1e10, "100억"), (1e11, "1000억 (대형주)")):
        for w in (0.04, 0.12):
            n = w * G["ACCOUNT_KRW"]
            real = 0.015 * math.sqrt(n / advb)      # Y·σ_daily·√참여율, Y=0.6 σ=2.5%
            print(f"{lab:>20} {w:>6.0%} {n:>12,.0f}원 {n/advb:>9.4%} "
                  f"{slippage(n, advb)*1e4:>8.1f}bp {real*1e4:>9.1f}bp")
    print(f"{'거래대금 결측/0':>20} {'—':>6} {'—':>13} {'—':>10} "
          f"{slippage(1e6, 0)*1e4:>8.1f}bp {'—':>10}   ← 무조건 200bp 폴백")

    print(f"\n{hr}\n[4] 현금끌림 — POS_MAX_WEIGHT = {G['POS_MAX_WEIGHT']:.0%} 하에서 보유종목 수별 실투자비중\n{hr}")
    for n in (5, 6, 7, 8, 9, 12, 25):
        sub = pd.DataFrame({"Signal_rank": np.linspace(0.9, 0.5, n), "adv20": np.full(n, 2e9)})
        w = size_positions(sub)["weight"]
        print(f"  보유 {n:2d}종목 → 투자비중 {w.sum():6.1%} (현금 {1-w.sum():5.1%}) · "
              f"비중 분포 {w.min():.1%}~{w.max():.1%}"
              + ("   ← 전 종목이 상한에 붙어 '신호강도 사이징'이 작동하지 않는다"
                 if w.max() - w.min() < 1e-9 else ""))

    print(f"\n{hr}\n[5] R3(⭐킬게이트) 의 비대칭 — 순수익 전략 vs 총수익 팩터\n{hr}")
    r = run(P, months, dl)
    print(f"  50_robust.py:213  y = bt['returns']['ret']      ← 비용 차감 '순'수익")
    print(f"  50_robust.py:207  팩터수익 = sub['fwd_ret']      ← 비용 없는 '총'수익")
    print(f"  → 회귀 절편(=알파)이 월 {r['월비용']*100:.3f}%p 만큼 통째로 눌린다 "
          f"(연 {ann(r['월비용'])*100:.2f}%p).")
    print(f"  → 총수익 기준 월 +{r['월비용']*100:.3f}%p 의 진짜 알파가 있어도 R3 는 알파 0 으로 읽고,")
    print(f"     kill=True + STOP_ON_KILL_CRITERIA=True 이므로 '퀄리티 재포장'으로 판정하고 실행을 중단한다.")
    print()


if __name__ == "__main__":
    main()
