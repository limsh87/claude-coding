# -*- coding: utf-8 -*-
"""Phase 1/2 — 신호 진단(수익률 불요) 과 백테스트(수익률 필요, 잠금 통과 필수).

OPS-C5: gross / net 을 분리 저장한다. **gross 만 보고하지 않는다.**
모든 수익률 조회는 spec.LOCK 을 통과한다 — 잠금이 닫혀 있으면 예외로 중단되고 시도 횟수가 센다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .spec import LOCK, KILL5_MARGIN_CAGR, BH_FDR_Q

PPY = 4.0   # 분기 리밸런싱

# 증권거래세 — 연도별 실효세율(매도분). 하드코딩이 아니라 근거를 붙인 표로 관리한다.
TAX_TABLE = [
    (2016, 0.00300, "유가증권 0.15%+농특세 0.15% / 코스닥 0.30%"),
    (2019, 0.00275, "2019.06 인하"),
    (2021, 0.00230, "2021.01 인하"),
    (2023, 0.00200, "2023.01 인하"),
    (2024, 0.00180, "2024.01 인하"),
    (2025, 0.00150, "2025.01 인하"),
]
COST = dict(commission_roundtrip=0.0003, spread_oneway_bp=55.0,
            slippage_bp=15.0, impact_bp=12.0)


def tax_rate(ts: pd.Timestamp) -> float:
    y = pd.Timestamp(ts).year
    r = TAX_TABLE[0][1]
    for yr, v, _ in TAX_TABLE:
        if y >= yr:
            r = v
    return r


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  Phase 1 — 미래수익률을 보지 않는 신호 진단
# ═══════════════════════════════════════════════════════════════════════════════════════════
def signal_diagnostics(panel: pd.DataFrame, by: str = "rebal",
                       sig: str = "CXD_rank") -> pd.DataFrame:
    """커버리지·분포·회전율. 수익률 접근 0회."""
    P = panel.copy()
    g = P.groupby(by, observed=True)
    rows = pd.DataFrame({
        "C1종목수": g["code"].count(),
        "신호보유": g[sig].apply(lambda s: s.notna().sum()),
        "커버리지": g[sig].apply(lambda s: s.notna().mean()),
        "셀매핑률": g["cell"].apply(lambda s: s.notna().mean()),
        "활성셀비율": g["cell_active"].apply(lambda s: pd.Series(s).fillna(False).mean()),
    })
    # 상위 N 구성의 분기 간 회전율 (수익률 아님)
    P = P.dropna(subset=[sig])
    prev, turns = None, {}
    for t, gg in P.groupby(by, observed=True):
        cur = set(gg.nlargest(50, sig)["code"])
        turns[t] = np.nan if prev is None else 1.0 - len(cur & prev) / max(1, len(cur))
        prev = cur
    rows["상위50회전율"] = pd.Series(turns)
    return rows.reset_index()


def rank_ic(panel: pd.DataFrame, by: str = "rebal", sig: str = "CXD_rank",
            ret: str = "fwd_ret_q") -> pd.DataFrame:
    """랭크 IC — 미래수익률을 쓰므로 잠금을 통과해야 한다."""
    LOCK.require(f"rank_ic({sig})")
    d = panel.dropna(subset=[sig, ret])
    ic = d.groupby(by, observed=True).apply(
        lambda g: g[sig].corr(g[ret], method="spearman") if len(g) >= 10 else np.nan)
    ic = ic.replace([np.inf, -np.inf], np.nan).dropna()
    n = len(ic)
    mu, sd = float(ic.mean()), float(ic.std(ddof=1)) if n > 1 else np.nan
    t = mu / (sd / np.sqrt(n)) if (n > 1 and sd and sd > 0) else np.nan
    from scipy import stats
    p = float(2 * stats.t.sf(abs(t), n - 1)) if np.isfinite(t) else np.nan
    return pd.DataFrame([dict(시점수=n, 평균IC=mu, IC표준편차=sd, IC_t=t, IC_p=p,
                              IR=(mu / sd if sd else np.nan),
                              양의비율=float((ic > 0).mean()))]), ic


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  Phase 2 — 백테스트
# ═══════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class BTResult:
    name: str
    gross: pd.Series
    net: pd.Series
    turnover: pd.Series
    n_holdings: pd.Series

    def stats(self, which: str = "net") -> dict:
        r = (self.net if which == "net" else self.gross).dropna()
        if len(r) < 4:
            return dict(cagr=np.nan, vol=np.nan, sharpe=np.nan, mdd=np.nan, hit=np.nan, n=len(r))
        eq = (1 + r).cumprod()
        yrs = len(r) / PPY
        cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else np.nan
        vol = float(r.std(ddof=1) * np.sqrt(PPY))
        mdd = float((eq / eq.cummax() - 1).min())
        return dict(cagr=cagr, vol=vol, sharpe=(cagr / vol if vol else np.nan), mdd=mdd,
                    hit=float((r > 0).mean()), n=len(r))


def _one_way_cost() -> float:
    return (COST["spread_oneway_bp"] + COST["slippage_bp"] + COST["impact_bp"]) / 1e4 \
        + COST["commission_roundtrip"] / 2.0


def backtest(panel: pd.DataFrame, name: str, top_n: int = 50, by: str = "rebal",
             sig: Optional[str] = "CXD_rank", ret: str = "fwd_ret_q",
             universe_mask: Optional[str] = None) -> BTResult:
    """동일가중 상위 N 분기 리밸런싱. sig=None 이면 유니버스 전체 동일가중(베이스라인)."""
    LOCK.require(f"backtest({name})")
    P = panel.copy()
    if universe_mask:
        P = P[P[universe_mask].fillna(False)]
    gross, net, turn, nh = {}, {}, {}, {}
    prev: set = set()
    ow = _one_way_cost()
    for t, g in P.groupby(by, observed=True):
        g = g.dropna(subset=[ret])
        if sig:
            g = g.dropna(subset=[sig])
            sel = g.nlargest(top_n, sig)
        else:
            sel = g
        if not len(sel):
            continue
        cur = set(sel["code"])
        r = float(sel[ret].mean())
        to = 1.0 if not prev else 1.0 - len(cur & prev) / max(1, len(cur))
        c = to * (2 * ow) + to * tax_rate(t)      # 매수+매도 편도비용 + 매도분 거래세
        gross[t], net[t], turn[t], nh[t] = r, r - c, to, len(sel)
        prev = cur
    idx = pd.DatetimeIndex(sorted(gross))
    return BTResult(name, pd.Series(gross).reindex(idx), pd.Series(net).reindex(idx),
                    pd.Series(turn).reindex(idx), pd.Series(nh).reindex(idx))


def quintile_profile(panel: pd.DataFrame, by: str = "rebal", sig: str = "CXD_rank",
                     ret: str = "fwd_ret_q") -> pd.DataFrame:
    """5분위 단조성 — 랭킹형 팩터의 기본 진단."""
    LOCK.require("quintile_profile")
    P = panel.dropna(subset=[sig, ret]).copy()
    P["q"] = P.groupby(by, observed=True)[sig].transform(
        lambda s: pd.qcut(s, 5, labels=[1, 2, 3, 4, 5], duplicates="drop"))
    out = (P.groupby("q", observed=True)[ret]
           .agg(평균수익="mean", 표준편차="std", 관측수="count").reset_index())
    return out


def bh_fdr(pvals: Dict[str, float], q: float = BH_FDR_Q) -> pd.DataFrame:
    """Benjamini-Hochberg. family = U250-F1 전체 팩터군(q=0.10). arm 은 시행수에 포함된다."""
    s = pd.Series(pvals).dropna().sort_values()
    m = len(s)
    if not m:
        return pd.DataFrame(columns=["대상", "p", "임계", "기각"])
    crit = pd.Series(np.arange(1, m + 1) / m * q, index=s.index)
    passed = s <= crit
    kmax = np.where(passed.to_numpy())[0].max() + 1 if passed.any() else 0
    rej = pd.Series(False, index=s.index)
    if kmax:
        rej.iloc[:kmax] = True
    return pd.DataFrame(dict(대상=s.index, p=s.to_numpy(), 임계=crit.to_numpy(),
                             기각=rej.to_numpy()))


def kill5_check(a: BTResult, b: BTResult, base: BTResult,
                margin: float = KILL5_MARGIN_CAGR) -> dict:
    """KILL-5 — arm A 가 arm B 를 사전 마진 초과로 이기지 못하면 폐기.

    비교는 **순수익(net)** 기준이며 베이스라인 대비 초과분으로 잰다.
    유리하게 해석하지 않는다.
    """
    xa = a.stats("net")["cagr"] - base.stats("net")["cagr"]
    xb = b.stats("net")["cagr"] - base.stats("net")["cagr"]
    gap = xa - xb
    return dict(arm_A_excess=xa, arm_B_excess=xb, gap=gap, margin=margin,
                passed=bool(np.isfinite(gap) and gap > margin))
