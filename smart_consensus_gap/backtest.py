# -*- coding: utf-8 -*-
"""Stage 6 — 백테스트 (§12, §13, §17).

체결 규칙(§12):
  · 시그널 = 리밸런싱일 종가까지 공개된 자료.
  · 공식 체결 = **다음 거래일 시가**. 시가가 없으면 다음 가용 종가로 체결하고 플래그를 남긴다.
  · 당일 종가 체결(SAME_DAY_CLOSE)은 참고용 진단이며 공식 성과로 쓰지 않는다.

상장폐지(§12):
  · 사라진 종목을 과거 포트폴리오에서 지우지 않는다. 마지막 가용 가격(또는 정리매매 수익률)
    으로 청산해 현금으로 남긴다. 그 사실은 플래그와 현금비중으로 드러난다.

거래비용(§13):
  · turnover = 0.5 * Σ|w_new − w_old_post_return|,  cost = turnover × 35bp.
  · gross / net 을 모두 출력한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import EXEC_NEXT_OPEN, EXEC_SAME_CLOSE, SCGConfig
from .pit_engine import MarketPanel, TradingCalendar
from .portfolio import cost_of, turnover
from .util import LOG

TRADING_DAYS_PER_YEAR = 252.0


@dataclass
class BacktestResult:
    daily: "pd.DataFrame"                    # date, ret_gross, ret_net, nav_gross, nav_net, cash_w, n_holdings
    rebalances: "pd.DataFrame"               # exec_date, turnover, cost, n_holdings, flags
    flags: Dict[str, int] = field(default_factory=dict)
    strategy: str = ""
    variant_id: str = "BASE"
    mode: str = ""
    execution: str = EXEC_NEXT_OPEN

    @property
    def ok(self) -> bool:
        return self.daily is not None and len(self.daily) > 1


def _price_matrices(panel: MarketPanel) -> Tuple[np.ndarray, np.ndarray]:
    """(수정종가, 수정시가). 수정시가는 MarketPanel 이 이미 배당·분할 정합을 맞춰 둔 값이며,
    맞출 수 없었던 경우 NaN 이다 → 백테스트가 종가 체결로 낮추고 플래그를 센다(§12)."""
    return panel.adj_close, panel.open_px


def run_backtest(holdings: "pd.DataFrame", panel: MarketPanel, cal: TradingCalendar,
                 cfg: SCGConfig, strategy: str, mode: str,
                 execution: Optional[str] = None) -> BacktestResult:
    execution = execution or cfg.execution
    flags: Dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        flags[k] = flags.get(k, 0) + n

    empty = pd.DataFrame(columns=["date", "ret_gross", "ret_net", "nav_gross", "nav_net",
                                  "cash_weight", "n_holdings"])
    if holdings is None or not len(holdings):
        return BacktestResult(empty, pd.DataFrame(), {"NO_HOLDINGS": 1}, strategy,
                              cfg.variant_id, mode, execution)

    h = holdings.dropna(subset=["exec_date"]).copy()
    if not len(h):
        return BacktestResult(empty, pd.DataFrame(), {"NO_EXEC_DATE": 1}, strategy,
                              cfg.variant_id, mode, execution)

    close, open_ = _price_matrices(panel)
    days = pd.DatetimeIndex(cal.days)
    n_days = len(days)
    pos_of = panel.code_pos

    #  체결일 → {code: target_weight}
    targets: Dict[pd.Timestamp, Dict[str, float]] = {}
    for d, g in h.groupby("exec_date", observed=True):
        d = pd.Timestamp(d)
        if execution == EXEC_SAME_CLOSE:
            d = pd.Timestamp(g["asof"].iloc[0])
        targets[d] = {str(c): float(w) for c, w in zip(g["company_code"], g["weight"])
                      if np.isfinite(w) and w > 0}
    exec_days = sorted(targets)
    if not exec_days:
        return BacktestResult(empty, pd.DataFrame(), {"NO_EXEC_DAYS": 1}, strategy,
                              cfg.variant_id, mode, execution)

    start_i = int(np.searchsorted(days.values, np.datetime64(exec_days[0]), side="left"))
    if start_i >= n_days:
        return BacktestResult(empty, pd.DataFrame(), {"EXEC_AFTER_CALENDAR_END": 1}, strategy,
                              cfg.variant_id, mode, execution)

    weights: Dict[str, float] = {}
    nav_g, nav_n = 1.0, 1.0
    rows: List[Dict[str, Any]] = []
    reb_rows: List[Dict[str, Any]] = []
    exec_set = {pd.Timestamp(d) for d in exec_days}

    for i in range(start_i, n_days):
        d = days[i]
        prev = i - 1
        is_exec = d in exec_set

        # ── 1) 기존 보유의 오늘 수익 (체결 전 구간) ────────────────────────────────
        codes = list(weights)
        r_leg1 = 0.0
        if codes and prev >= 0:
            j = np.array([pos_of.get(c, -1) for c in codes], dtype=np.int64)
            w = np.array([weights[c] for c in codes], dtype=float)
            p0 = np.where(j >= 0, close[prev, np.maximum(j, 0)], np.nan)
            if is_exec and execution == EXEC_NEXT_OPEN:
                p1 = np.where(j >= 0, open_[i, np.maximum(j, 0)], np.nan)
                miss = ~np.isfinite(p1) & np.isfinite(np.where(j >= 0, close[i, np.maximum(j, 0)], np.nan))
                if miss.any():
                    bump("EXEC_OPEN_MISSING_USED_CLOSE", int(miss.sum()))
                    p1 = np.where(miss, close[i, np.maximum(j, 0)], p1)
            else:
                p1 = np.where(j >= 0, close[i, np.maximum(j, 0)], np.nan)

            ri = np.full(len(codes), np.nan)
            live = np.isfinite(p0) & np.isfinite(p1) & (p0 > 0)
            ri[live] = p1[live] / p0[live] - 1.0
            dead = ~live
            if dead.any():
                bump("DELIST_EXIT_AT_LAST_PRICE", int(dead.sum()))
                ri[dead] = 0.0                   # 마지막 가용 가격으로 청산 → 현금화
            r_leg1 = float(np.dot(w, ri))
            # 비중 드리프트 (사라진 종목은 현금으로 빠진다)
            gw = w * (1.0 + ri)
            new_w: Dict[str, float] = {}
            denom = 1.0 + r_leg1
            for k, c in enumerate(codes):
                if dead[k]:
                    continue
                new_w[c] = gw[k] / denom if denom > 0 else 0.0
            weights = new_w

        # ── 2) 체결 ────────────────────────────────────────────────────────────────
        cost = 0.0
        turn = np.nan
        if is_exec:
            tgt = targets[pd.Timestamp(d)]
            live_tgt = {}
            j = {c: pos_of.get(c, -1) for c in tgt}
            for c, wv in tgt.items():
                jj = j[c]
                px = close[i, jj] if jj >= 0 else np.nan
                if np.isfinite(px) and px > 0:
                    live_tgt[c] = wv
                else:
                    bump("TARGET_NO_PRICE_AT_EXEC")
            s = sum(live_tgt.values())
            if s > 0:
                live_tgt = {c: v / s for c, v in live_tgt.items()}
            turn = turnover(live_tgt, weights)
            cost = cost_of(turn, cfg.transaction_cost_bps)
            reb_rows.append({"exec_date": d, "turnover": turn, "cost": cost,
                             "n_holdings": len(live_tgt),
                             "n_target": len(tgt), "strategy": strategy,
                             "variant_id": cfg.variant_id})
            weights = live_tgt

        # ── 3) 체결 후 구간 수익 ──────────────────────────────────────────────────
        r_leg2 = 0.0
        if is_exec and execution == EXEC_NEXT_OPEN and weights:
            codes2 = list(weights)
            j2 = np.array([pos_of.get(c, -1) for c in codes2], dtype=np.int64)
            w2 = np.array([weights[c] for c in codes2], dtype=float)
            po = np.where(j2 >= 0, open_[i, np.maximum(j2, 0)], np.nan)
            pc = np.where(j2 >= 0, close[i, np.maximum(j2, 0)], np.nan)
            po = np.where(np.isfinite(po), po, pc)
            ri2 = np.full(len(codes2), np.nan)
            ok = np.isfinite(po) & np.isfinite(pc) & (po > 0)
            ri2[ok] = pc[ok] / po[ok] - 1.0
            ri2 = np.nan_to_num(ri2, nan=0.0)
            r_leg2 = float(np.dot(w2, ri2))
            gw = w2 * (1.0 + ri2)
            tot = gw.sum()
            if tot > 0:
                weights = {c: float(v / tot) for c, v in zip(codes2, gw)}

        r_gross = (1.0 + r_leg1) * (1.0 + r_leg2) - 1.0
        r_net = (1.0 + r_gross) * (1.0 - cost) - 1.0
        nav_g *= (1.0 + r_gross)
        nav_n *= (1.0 + r_net)
        cash_w = max(0.0, 1.0 - float(sum(weights.values()))) if weights else 1.0
        rows.append({"date": d, "ret_gross": r_gross, "ret_net": r_net,
                     "nav_gross": nav_g, "nav_net": nav_n,
                     "cash_weight": cash_w, "n_holdings": len(weights),
                     "turnover": turn, "cost": cost})

    daily = pd.DataFrame(rows)
    return BacktestResult(daily, pd.DataFrame(reb_rows), flags, strategy, cfg.variant_id,
                          mode, execution)


# ════════════════════════════════════════════════════════════════════════════════════════
#  벤치마크
# ════════════════════════════════════════════════════════════════════════════════════════
def benchmark_daily(bench: Optional["pd.DataFrame"], panel: MarketPanel, cal: TradingCalendar,
                    universe_by_date: Optional[Dict[Any, List[str]]], benchmark_id: str
                    ) -> Tuple["pd.DataFrame", str]:
    """실제 지수가 있으면 그것을, 없으면 PIT 유니버스 시총가중 대용을 쓴다(플래그 명시)."""
    if bench is not None and len(bench):
        b = bench[bench["benchmark_id"].astype(str) == benchmark_id]
        if not len(b):
            b = bench
        b = b.sort_values("date").drop_duplicates("date", keep="last")
        s = b.set_index("date")["close"].astype(float)
        r = s.pct_change()
        return pd.DataFrame({"date": s.index, "bench_ret": r.to_numpy()}).dropna(), "INDEX_SERIES"

    if not universe_by_date:
        return pd.DataFrame(columns=["date", "bench_ret"]), "UNAVAILABLE"

    days = pd.DatetimeIndex(cal.days)
    snap_dates = sorted(pd.Timestamp(d) for d in universe_by_date)
    rows = []
    cur: List[str] = []
    for i in range(1, len(days)):
        d = days[i]
        while snap_dates and d >= snap_dates[0]:
            cur = universe_by_date[snap_dates.pop(0)]
        if not cur:
            continue
        j = np.array([panel.code_pos.get(c, -1) for c in cur], dtype=np.int64)
        j = j[j >= 0]
        if not len(j):
            continue
        p0 = panel.adj_close[i - 1, j]
        p1 = panel.adj_close[i, j]
        mc = panel.market_cap[i - 1, j]
        ok = np.isfinite(p0) & np.isfinite(p1) & (p0 > 0) & np.isfinite(mc) & (mc > 0)
        if ok.sum() < 5:
            continue
        w = mc[ok] / mc[ok].sum()
        rows.append({"date": d, "bench_ret": float(np.dot(w, p1[ok] / p0[ok] - 1.0))})
    return pd.DataFrame(rows), "PROXY_UNIVERSE_CAPWEIGHT"


# ════════════════════════════════════════════════════════════════════════════════════════
#  성과 지표 (§17)
# ════════════════════════════════════════════════════════════════════════════════════════
def _ann_factor(n_days: int, span_days: float) -> float:
    return TRADING_DAYS_PER_YEAR


def max_drawdown(nav: np.ndarray) -> float:
    if len(nav) == 0:
        return float("nan")
    peak = np.maximum.accumulate(nav)
    dd = nav / np.where(peak > 0, peak, np.nan) - 1.0
    return float(np.nanmin(dd))


def performance_metrics(ret: "pd.Series", bench: Optional["pd.Series"] = None,
                        turnover_series: Optional["pd.Series"] = None,
                        label: str = "") -> Dict[str, Any]:
    r = pd.Series(ret).dropna().astype(float)
    if len(r) < 2:
        return {"label": label, "n_days": int(len(r))}
    nav = (1.0 + r).cumprod().to_numpy()
    years = len(r) / TRADING_DAYS_PER_YEAR
    total = float(nav[-1] - 1.0)
    cagr = float(nav[-1] ** (1.0 / years) - 1.0) if years > 0 and nav[-1] > 0 else float("nan")
    vol = float(r.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
    downside = r[r < 0]
    dvol = float(downside.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(downside) > 1 else np.nan
    mdd = max_drawdown(nav)
    m = r.resample("ME").apply(lambda s: (1 + s).prod() - 1) if isinstance(r.index, pd.DatetimeIndex) \
        else pd.Series(dtype=float)
    out = {
        "label": label, "n_days": int(len(r)), "years": round(years, 3),
        "total_return": total, "CAGR": cagr, "ann_vol": vol,
        "Sharpe": float(cagr / vol) if (np.isfinite(vol) and vol > 0) else np.nan,
        "Sortino": float(cagr / dvol) if (np.isfinite(dvol) and dvol > 0) else np.nan,
        "MDD": mdd,
        "Calmar": float(cagr / abs(mdd)) if (np.isfinite(mdd) and mdd < 0) else np.nan,
        "hit_ratio_monthly": float((m > 0).mean()) if len(m) else np.nan,
        "hit_ratio_daily": float((r > 0).mean()),
        "best_month": float(m.max()) if len(m) else np.nan,
        "worst_month": float(m.min()) if len(m) else np.nan,
    }
    if turnover_series is not None and len(turnover_series.dropna()):
        ts = turnover_series.dropna().astype(float)
        out["turnover_per_rebalance"] = float(ts.mean())
        out["turnover_annual"] = float(ts.mean() * (len(ts) / max(years, 1e-9)))
    if bench is not None:
        b = pd.Series(bench).dropna().astype(float)
        idx = r.index.intersection(b.index)
        if len(idx) > 10:
            ex = r.loc[idx] - b.loc[idx]
            bnav = (1.0 + b.loc[idx]).cumprod().to_numpy()
            byears = len(idx) / TRADING_DAYS_PER_YEAR
            bcagr = float(bnav[-1] ** (1.0 / byears) - 1.0) if bnav[-1] > 0 else np.nan
            pnav = (1.0 + r.loc[idx]).cumprod().to_numpy()
            pcagr = float(pnav[-1] ** (1.0 / byears) - 1.0) if pnav[-1] > 0 else np.nan
            te = float(ex.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
            out.update({
                "benchmark_CAGR": bcagr,
                "excess_CAGR": pcagr - bcagr if np.isfinite(pcagr) and np.isfinite(bcagr) else np.nan,
                "tracking_error": te,
                "information_ratio": float((pcagr - bcagr) / te)
                if (np.isfinite(te) and te > 0 and np.isfinite(pcagr) and np.isfinite(bcagr)) else np.nan,
                "excess_hit_ratio_monthly": float(
                    (ex.resample("ME").apply(lambda s: (1 + s).prod() - 1) > 0).mean())
                if isinstance(ex.index, pd.DatetimeIndex) else np.nan,
            })
    return out


def yearly_returns(ret: "pd.Series", bench: Optional["pd.Series"] = None) -> "pd.DataFrame":
    r = pd.Series(ret).dropna().astype(float)
    if not len(r):
        return pd.DataFrame(columns=["year", "portfolio", "benchmark", "excess"])
    y = r.resample("YE").apply(lambda s: (1 + s).prod() - 1)
    out = pd.DataFrame({"year": y.index.year, "portfolio": y.to_numpy()})
    if bench is not None and len(bench):
        b = pd.Series(bench).dropna().astype(float).resample("YE").apply(lambda s: (1 + s).prod() - 1)
        out["benchmark"] = b.reindex(y.index).to_numpy()
        out["excess"] = out["portfolio"] - out["benchmark"]
    return out


def monthly_returns(ret: "pd.Series", bench: Optional["pd.Series"] = None) -> "pd.DataFrame":
    r = pd.Series(ret).dropna().astype(float)
    if not len(r):
        return pd.DataFrame(columns=["month", "portfolio", "benchmark", "excess"])
    m = r.resample("ME").apply(lambda s: (1 + s).prod() - 1)
    out = pd.DataFrame({"month": m.index.strftime("%Y-%m"), "portfolio": m.to_numpy()})
    if bench is not None and len(bench):
        b = pd.Series(bench).dropna().astype(float).resample("ME").apply(lambda s: (1 + s).prod() - 1)
        out["benchmark"] = b.reindex(m.index).to_numpy()
        out["excess"] = out["portfolio"] - out["benchmark"]
    return out


def rolling_windows(ret: "pd.Series") -> "pd.DataFrame":
    r = pd.Series(ret).dropna().astype(float)
    if len(r) < 260:
        return pd.DataFrame(columns=["date", "rolling_12m_return", "rolling_36m_cagr"])
    lr = np.log1p(r)
    w12 = int(TRADING_DAYS_PER_YEAR)
    w36 = int(TRADING_DAYS_PER_YEAR * 3)
    roll12 = np.expm1(lr.rolling(w12).sum())
    roll36 = np.expm1(lr.rolling(w36).sum() / 3.0)
    return pd.DataFrame({"date": r.index, "rolling_12m_return": roll12.to_numpy(),
                         "rolling_36m_cagr": roll36.to_numpy()}).dropna(how="all",
                                                                        subset=["rolling_12m_return",
                                                                                "rolling_36m_cagr"])


def to_series(daily: "pd.DataFrame", col: str) -> "pd.Series":
    if daily is None or not len(daily) or col not in daily.columns:
        return pd.Series(dtype=float)
    return pd.Series(daily[col].to_numpy(dtype=float),
                     index=pd.DatetimeIndex(daily["date"]), name=col)


__all__ = ["run_backtest", "BacktestResult", "benchmark_daily", "performance_metrics",
           "yearly_returns", "monthly_returns", "rolling_windows", "max_drawdown", "to_series",
           "TRADING_DAYS_PER_YEAR"]
