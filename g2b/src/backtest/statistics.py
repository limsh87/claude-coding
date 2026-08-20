# -*- coding: utf-8 -*-
"""성과·검정 통계.   §60 · §61 · §62 · §78"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def newey_west_t(x, lags: Optional[int] = None) -> Tuple[float, float, float]:
    """(mean, se_nw, t). 자기상관·이분산에 강건한 표준오차."""
    a = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(a)
    if n < 6:
        return (float(a.mean()) if n else np.nan, np.nan, np.nan)
    mu = float(a.mean())
    e = a - mu
    L = int(lags if lags is not None else max(1, int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))))
    s = float(e @ e) / n
    for k in range(1, min(L, n - 1) + 1):
        s += 2.0 * (1.0 - k / (L + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    se = float(np.sqrt(max(s, 0.0) / n))
    return mu, se, (mu / se if se > 0 else np.nan)


def t_to_p(t: float, dof: int = 200) -> float:
    if t is None or not np.isfinite(t):
        return np.nan
    from scipy import stats
    return float(2 * (1 - stats.t.cdf(abs(t), dof)))


def perf_table(ret, freq: int = 12, label: str = "") -> pd.DataFrame:
    """§60 필수 성과표."""
    r = pd.Series(ret).dropna().astype(float)
    if not len(r):
        return pd.DataFrame([{"전략": label, "관측월": 0}])
    cum = float((1 + r).prod())
    yrs = len(r) / freq
    cagr = (cum ** (1 / yrs) - 1) if (yrs > 0 and cum > 0) else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(freq))
    curve = (1 + r).cumprod()
    mdd = float((curve / curve.cummax() - 1).min())
    mu, se, t = newey_west_t(r.to_numpy())
    return pd.DataFrame([{
        "전략": label, "관측월": len(r), "CAGR": cagr, "연환산수익": float(r.mean() * freq),
        "변동성": vol, "Sharpe": (float(r.mean() * freq) / vol) if vol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if (mdd < 0 and pd.notna(cagr)) else np.nan,
        "적중률": float((r > 0).mean()), "월평균": mu, "NW_SE": se, "NW_t": t,
        "p(NW)": t_to_p(t, max(len(r) - 1, 5)),
        "CI95_low": (mu - 1.96 * se) if pd.notna(se) else np.nan,
        "CI95_high": (mu + 1.96 * se) if pd.notna(se) else np.nan}])


def information_coefficient(F: pd.DataFrame, score_col: str, ret_col: str,
                            month_col: str = "month", min_n: int = 10
                            ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§61 — 월별 Spearman IC 와 그 시계열 검정. (요약, 월별 시계열)."""
    d = F[[month_col, score_col, ret_col]].dropna()
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    rk = d.groupby(month_col, observed=True)[[score_col, ret_col]].rank()
    rk[month_col] = d[month_col].to_numpy()
    n = rk.groupby(month_col, observed=True)[score_col].transform("count")
    rk = rk[n >= min_n]
    if not len(rk):
        return pd.DataFrame(), pd.DataFrame()
    # 순위 상관 = 순위변수의 피어슨 상관 (그룹 루프 없이 벡터화)
    # 순위 상관 = 순위변수의 피어슨 상관. groupby.apply 를 피하고 완전 벡터화한다
    # (pandas 버전마다 include_groups 시그니처가 달라 apply 는 이식성이 나쁘다).
    a = rk[score_col].to_numpy(dtype=float)
    b = rk[ret_col].to_numpy(dtype=float)
    key = rk[month_col]
    df = pd.DataFrame({"m": key.to_numpy(), "a": a, "b": b,
                       "ab": a * b, "a2": a * a, "b2": b * b})
    G = df.groupby("m", observed=True).agg(n=("a", "size"), sa=("a", "sum"), sb=("b", "sum"),
                                            sab=("ab", "sum"), sa2=("a2", "sum"),
                                            sb2=("b2", "sum")).reset_index()
    cov = G["sab"] - G["sa"] * G["sb"] / G["n"]
    va = G["sa2"] - G["sa"] ** 2 / G["n"]
    vb = G["sb2"] - G["sb"] ** 2 / G["n"]
    den = np.sqrt(va.clip(lower=0) * vb.clip(lower=0))
    ic = pd.DataFrame({month_col: G["m"],
                       "IC": np.where((G["n"] > 2) & (den > 0), cov / den.replace(0, np.nan),
                                      np.nan)})
    v = ic["IC"].dropna().to_numpy()
    mu, se, t = newey_west_t(v)
    summ = pd.DataFrame([{"팩터": score_col, "월수": len(v), "평균IC": mu, "IC_SE": se, "IC_t": t,
                          "p(IC)": t_to_p(t, max(len(v) - 1, 5)),
                          "IC>0 비율": float((v > 0).mean()) if len(v) else np.nan,
                          "IR": (float(np.mean(v) / np.std(v, ddof=1))
                                 if len(v) > 1 and np.std(v, ddof=1) > 0 else np.nan)}])
    return summ, ic


def quantile_returns(F: pd.DataFrame, score_col: str, ret_col: str, q: int = 5,
                     month_col: str = "month", weight: str = "equal",
                     min_n: int = 20) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§55 분위 포트폴리오 월수익 + monotonicity 표."""
    cols = [month_col, "stock_code", score_col, ret_col]
    d = F[[c for c in cols if c in F.columns]].dropna().copy()
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    n = d.groupby(month_col, observed=True)[score_col].transform("count")
    d = d[n >= max(min_n, q * 2)]
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    d["q"] = (d.groupby(month_col, observed=True)[score_col]
              .transform(lambda s: pd.qcut(s.rank(method="first"), q, labels=False,
                                           duplicates="drop") + 1))
    d = d.dropna(subset=["q"])
    if weight == "equal":
        d["w"] = 1.0
    else:
        d["w"] = d.groupby([month_col, "q"], observed=True)[score_col].rank(method="average")
    d["w"] = d["w"] / d.groupby([month_col, "q"], observed=True)["w"].transform("sum")
    QR = (d.assign(_wr=d["w"] * d[ret_col])
          .groupby([month_col, "q"], as_index=False, observed=True)
          .agg(ret=("_wr", "sum"), n=(ret_col, "size")))
    piv = QR.pivot(index=month_col, columns="q", values="ret")
    piv.columns = [f"Q{int(c)}" for c in piv.columns]
    piv = piv.join(d.groupby(month_col, observed=True)[ret_col].mean().rename("Universe"))
    hi = f"Q{q}"
    if hi in piv.columns:
        piv[f"{hi}-Universe"] = piv[hi] - piv["Universe"]
        if "Q1" in piv.columns:
            piv[f"{hi}-Q1"] = piv[hi] - piv["Q1"]
    tab = pd.concat([perf_table(piv[c], label=c) for c in piv.columns], ignore_index=True)
    return piv, tab


def fama_macbeth(F: pd.DataFrame, y: str, xs: Sequence[str], month_col: str = "month",
                 sector_col: Optional[str] = "sector", min_n: int = 30) -> pd.DataFrame:
    """§62 — 월별 횡단면 회귀 계수의 시계열 평균과 NW t."""
    xs = [c for c in xs if c in F.columns]
    if not xs or y not in F.columns:
        return pd.DataFrame()
    use = [month_col, y] + xs + ([sector_col] if sector_col and sector_col in F.columns else [])
    d = F[use].dropna(subset=[y] + xs)
    coefs: List[dict] = []
    for mth, g in d.groupby(month_col, observed=True):
        if len(g) < min_n:
            continue
        X, names = [np.ones((len(g), 1))], ["const"]
        for c in xs:
            v = pd.to_numeric(g[c], errors="coerce").to_numpy(dtype=float)
            sd = np.nanstd(v)
            v = (v - np.nanmean(v)) / (sd + 1e-12)
            X.append(np.nan_to_num(v).reshape(-1, 1))
            names.append(c)
        if sector_col and sector_col in g.columns:
            sec = pd.Categorical(g[sector_col].astype(str))
            if len(sec.categories) > 1:
                D = np.zeros((len(g), len(sec.categories) - 1))
                for j in range(1, len(sec.categories)):
                    D[:, j - 1] = (sec.codes == j).astype(float)
                X.append(D)
                names += [f"sec_{i}" for i in range(D.shape[1])]
        try:
            beta, *_ = np.linalg.lstsq(np.hstack(X), g[y].to_numpy(dtype=float), rcond=None)
        except Exception:                                      # noqa: BLE001
            continue
        coefs.append({"month": mth, **{n: b for n, b in zip(names, beta)
                                       if not n.startswith("sec_")}})
    if not coefs:
        return pd.DataFrame()
    C = pd.DataFrame(coefs)
    rows = []
    for c in [x for x in C.columns if x != "month"]:
        mu, se, t = newey_west_t(C[c].to_numpy())
        rows.append({"변수": c, "월수": int(C[c].notna().sum()), "평균계수": mu,
                     "NW_SE": se, "NW_t": t, "p": t_to_p(t, max(len(C) - 1, 5))})
    return pd.DataFrame(rows)


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> pd.DataFrame:
    """§78 — Benjamini-Hochberg. 최고 t 하나만 보고 '성공' 판정하지 않기 위함."""
    p = np.asarray(list(pvals), dtype=float)
    ok = np.isfinite(p)
    m = int(ok.sum())
    crit = np.full(len(p), np.nan)
    rej = np.zeros(len(p), dtype=bool)
    if m:
        order = np.argsort(np.where(ok, p, np.inf))
        ranks = np.arange(1, len(p) + 1)
        crit_sorted = q * ranks / m
        below = p[order][:m] <= crit_sorted[:m]
        kmax = (np.where(below)[0].max() + 1) if below.any() else 0
        rej[order[:kmax]] = True
        crit[order] = crit_sorted
    return pd.DataFrame({"p": p, "BH_임계값": crit, "기각(FDR)": rej})
