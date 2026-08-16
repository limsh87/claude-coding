# -*- coding: utf-8 -*-
"""§3.1 팩터 정의의 벡터화 구현.

속도 규율: 시점 루프를 쓰지 않는다.
  · IEG(12M 로그차분)·TREND(60M 롤링 OLS)·CYCLE 은 셀×월 행렬 위의 cumsum 으로 계산한다.
  · 횡단면 회귀(DIV, 잔차화)는 시점별 루프 대신 **정규방정식의 groupby 합**으로 일괄 해를 구한다.
    시점 T개·회귀변수 k개면 bincount 를 k(k+1)/2 + k 번만 돌리고 (T,k,k) 를 한 번에 푼다.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .spec import CXD, RULES


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  횡단면 유틸 — 전부 groupby 벡터 연산
# ═══════════════════════════════════════════════════════════════════════════════════════════
def xsec_winsorize(df: pd.DataFrame, col: str, by: str,
                   q: Tuple[float, float] = None) -> pd.Series:
    """시점별 분위 절단. 명세서 §3.1 winsorize (0.01, 0.99)."""
    lo, hi = q or RULES["winsor"]
    g = df.groupby(by, observed=True)[col]
    return df[col].clip(lower=g.transform(lambda s: s.quantile(lo)),
                        upper=g.transform(lambda s: s.quantile(hi)))


def xsec_z(df: pd.DataFrame, col: str, by: str, min_obs: int = 5) -> pd.Series:
    """시점별 z-score. 표본이 min_obs 미만이거나 분산이 0이면 결측(0 대입 금지)."""
    g = df.groupby(by, observed=True)[col]
    mu, sd, n = g.transform("mean"), g.transform("std"), g.transform("count")
    z = (df[col] - mu) / sd.replace(0.0, np.nan)
    return z.where((n >= min_obs) & np.isfinite(z))


def xsec_rank_pct(df: pd.DataFrame, col: str, by: str) -> pd.Series:
    """시점별 백분위 순위 (§3.1 정규화: winsorize → percentile rank)."""
    return df.groupby(by, observed=True)[col].rank(pct=True, method="average")


def batched_xsec_resid(df: pd.DataFrame, ycol: str, xcols: Sequence[str], by: str,
                       min_obs: int = 10) -> pd.Series:
    """시점별 횡단면 OLS 잔차 — 루프 없이 일괄 계산.

    각 시점 t 에 대해  y = a + Σ b_j x_j + e  를 적합하고 e 를 돌려준다.
    y 또는 x 에 결측이 있는 행은 적합에서 빠지고 잔차도 결측이다(0 대입 금지).
    관측이 min_obs 미만인 시점은 통째로 결측 — 표본이 없는데 회귀하지 않는다.
    """
    xcols = list(xcols)
    codes, _ = pd.factorize(df[by], sort=True)
    G = int(codes.max()) + 1 if len(codes) else 0
    if G == 0:
        return pd.Series(np.nan, index=df.index, dtype=float)

    y = pd.to_numeric(df[ycol], errors="coerce").to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(df))] +
                        [pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
                         for c in xcols])
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    k = X.shape[1]

    cnt = np.bincount(codes[ok], minlength=G)
    # 정규방정식 성분을 groupby 합으로 모은다 (bincount = 가장 빠른 groupby-sum)
    XtX = np.zeros((G, k, k), dtype=float)
    Xty = np.zeros((G, k), dtype=float)
    cg, Xg, yg = codes[ok], X[ok], y[ok]
    for a in range(k):
        Xty[:, a] = np.bincount(cg, weights=Xg[:, a] * yg, minlength=G)
        for b in range(a, k):
            s = np.bincount(cg, weights=Xg[:, a] * Xg[:, b], minlength=G)
            XtX[:, a, b] = s
            XtX[:, b, a] = s

    good = cnt >= max(min_obs, k + 1)
    beta = np.full((G, k), np.nan, dtype=float)
    if good.any():
        # pinv 는 특이행렬(완전공선)에서도 최소노름 해를 주므로 시점 하나 때문에 죽지 않는다
        beta[good] = np.einsum("gij,gj->gi", np.linalg.pinv(XtX[good]), Xty[good])

    fit = np.einsum("nk,nk->n", X, beta[codes])
    out = np.full(len(df), np.nan, dtype=float)
    out[ok] = y[ok] - fit[ok]
    return pd.Series(out, index=df.index, dtype=float)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  월별 행렬 위의 롤링 연산 — cumsum 기반, 셀 전체를 한 번에
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _roll_sum(A: np.ndarray, w: int) -> np.ndarray:
    """축=1 방향 폭 w 롤링 합. 창이 다 차지 않은 앞부분은 NaN."""
    C = np.concatenate([np.zeros((A.shape[0], 1)), np.nancumsum(A, axis=1)], axis=1)
    S = C[:, w:] - C[:, :-w]
    out = np.full(A.shape, np.nan, dtype=float)
    out[:, w - 1:] = S
    return out


def exp_matrix(exp_df: pd.DataFrame, cell_col: str = "cell", month_col: str = "month",
               val_col: str = "exp_usd") -> Tuple[np.ndarray, pd.Index, pd.DatetimeIndex]:
    """셀×월 수출액 행렬. **달력 연속성**을 강제한다.

    pivot 만 하면 전 셀이 결측인 달의 컬럼이 통째로 사라지고, 그러면 12M·60M 창이
    달력상 떨어진 구간을 이어붙여 IEG·TREND 가 조용히 왜곡된다.
    """
    m = pd.to_datetime(exp_df[month_col]).dt.to_period("M").dt.to_timestamp("M")
    W = (pd.DataFrame({"cell": exp_df[cell_col].astype(str), "month": m,
                       "v": pd.to_numeric(exp_df[val_col], errors="coerce")})
         .groupby(["cell", "month"], observed=True, as_index=False)["v"].sum()
         .pivot(index="cell", columns="month", values="v"))
    full = pd.date_range(W.columns.min(), W.columns.max(), freq="ME")
    W = W.reindex(columns=full)
    return W.to_numpy(dtype=float), W.index, full


def compute_ieg(E: np.ndarray) -> np.ndarray:
    """§3.1 [2] IEG = log(Σ EXP 최근 12M) − log(Σ EXP 그 이전 12M).

    통관 결측월은 '수출 0'이므로 합산에서 0으로 다루되, 12M 합이 0 이하인 셀-시점은
    로그가 정의되지 않으므로 결측이다.
    """
    A = np.where(np.isfinite(E), E, 0.0)
    S12 = _roll_sum(A, 12)
    prev = np.full_like(S12, np.nan)
    prev[:, 12:] = S12[:, :-12]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(np.where(S12 > 0, S12, np.nan)) - np.log(np.where(prev > 0, prev, np.nan))
    return out


def compute_trend_cycle(E: np.ndarray, window: int = None,
                        min_periods: int = None) -> Tuple[np.ndarray, np.ndarray]:
    """§3.1 [3] TREND(연율화 OLS 기울기) 와 CYCLE.

    y = log(월별 수출액). 수출이 0/결측인 달은 로그가 없으므로 창에서 제외하고,
    유효 관측이 min_periods 미만인 창은 결측이다. 결측을 0으로 밀지 않는다 —
    0으로 밀면 '수출이 끊긴 달'이 '수출액 1달러'로 둔갑해 기울기가 음으로 조작된다.
    """
    window = int(window or CXD["TREND_MONTHS"])
    min_periods = int(min_periods or max(24, window // 2))
    n, T = E.shape
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log(np.where(np.isfinite(E) & (E > 0), E, np.nan))
    m = np.isfinite(y)
    yf = np.where(m, y, 0.0)
    x = np.tile(np.arange(T, dtype=float), (n, 1))
    xm = np.where(m, x, 0.0)

    Sn = _roll_sum(m.astype(float), window)
    Sx = _roll_sum(xm, window)
    Sy = _roll_sum(yf, window)
    Sxx = _roll_sum(xm * xm, window)
    Sxy = _roll_sum(xm * yf, window)

    with np.errstate(divide="ignore", invalid="ignore"):
        den = Sxx - (Sx * Sx) / Sn
        slope = (Sxy - (Sx * Sy) / Sn) / np.where(np.abs(den) > 1e-12, den, np.nan)
        xbar, ybar = Sx / Sn, Sy / Sn

    bad = ~np.isfinite(Sn) | (Sn < min_periods)
    slope = np.where(bad, np.nan, slope)

    # CYCLE = mean(log 수출액, 최근 12M) − 60M 추세의 그 시점 적합값
    S12n = _roll_sum(m.astype(float), 12)
    S12y = _roll_sum(yf, 12)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean12 = S12y / np.where(S12n > 0, S12n, np.nan)
    mean12 = np.where(S12n >= 6, mean12, np.nan)
    x_end = np.tile(np.arange(T, dtype=float), (n, 1))
    fitted = ybar + slope * (x_end - xbar)
    cycle = mean12 - fitted
    return slope * 12.0, cycle          # 기울기는 월 단위 → 연율화


def build_cell_panel(exp_df: pd.DataFrame) -> pd.DataFrame:
    """셀×월 → IEG / TREND / CYCLE 롱 패널 + PIT 스탬프.

    §3.1 [2] PIT: 참조월말 + 45일. 최소 1회의 정정 사이클을 통과한 값만 쓴다(R-06).
    """
    E, cells, months = exp_matrix(exp_df)
    ieg = compute_ieg(E)
    trend, cycle = compute_trend_cycle(E)
    n, T = E.shape
    P = pd.DataFrame({
        "cell": np.repeat(cells.to_numpy(), T),
        "month": np.tile(months.to_numpy(), n),
        "exp_usd": E.reshape(-1),
        "IEG": ieg.reshape(-1),
        "TREND": trend.reshape(-1),
        "CYCLE": cycle.reshape(-1),
    })
    P["knowledge_date"] = (pd.to_datetime(P["month"])
                           + pd.Timedelta(days=int(CXD["CUSTOMS_PIT_DAYS"])))
    return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  기업 축
# ═══════════════════════════════════════════════════════════════════════════════════════════
def compute_fgr(rev: pd.DataFrame, lookback_q: int = None,
                collapse_floor: float = None) -> pd.DataFrame:
    """§3.1 [4] 매출 성장 + 붕괴 배제.

    rev: code, qend, rev_ttm, knowledge_date (PIT = rcept_dt + 1 거래일)
    FGR   = (REV_ttm(t) − REV_ttm(t−LQ)) / |REV_ttm(t−LQ)|
    붕괴배제: REV_ttm(t−LQ) / max(REV_ttm, t−2·LQ .. t−LQ) < floor → 결측
    """
    LQ = int(lookback_q or CXD["FGR_LOOKBACK_Q"])
    floor = float(collapse_floor if collapse_floor is not None else CXD["COLLAPSE_FLOOR"])
    R = rev.sort_values(["code", "qend"]).copy()
    g = R.groupby("code", observed=True)["rev_ttm"]
    base = g.shift(LQ)
    with np.errstate(divide="ignore", invalid="ignore"):
        R["FGR"] = (R["rev_ttm"] - base) / base.abs().replace(0.0, np.nan)
    # 기저 구간 t−2LQ..t−LQ 의 최대치 = 붕괴 판정 기준
    peak = g.shift(LQ).groupby(R["code"], observed=True).transform(
        lambda s: s.rolling(LQ + 1, min_periods=2).max())
    with np.errstate(divide="ignore", invalid="ignore"):
        R["collapse_ratio"] = base / peak.replace(0.0, np.nan)
    R.loc[R["collapse_ratio"] < floor, "FGR"] = np.nan
    return R


def asof_attach(left: pd.DataFrame, right: pd.DataFrame, left_time: str,
                right_time: str, by: Optional[str], cols: Sequence[str],
                suffix: str = "") -> pd.DataFrame:
    """PIT 결합 — merge_asof(backward). 리밸일 시점에 '이미 알려진' 최신 관측만 붙는다."""
    L = left.sort_values(left_time).copy()
    R = right.dropna(subset=[right_time]).sort_values(right_time).copy()
    L[left_time] = pd.to_datetime(L[left_time])
    R[right_time] = pd.to_datetime(R[right_time])
    keep = [right_time] + ([by] if by else []) + list(cols)
    R = R[[c for c in dict.fromkeys(keep) if c in R.columns]]
    out = pd.merge_asof(L, R, left_on=left_time, right_on=right_time,
                        by=by, direction="backward", suffixes=("", suffix))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §3.1 [5][6][7] 최종 신호
# ═══════════════════════════════════════════════════════════════════════════════════════════
def build_signal(panel: pd.DataFrame, arm, by: str = "rebal") -> pd.DataFrame:
    """C1 패널 → arm 별 CXD 신호.

    panel 필수 컬럼: rebal, code, cell, FGR, IEG, TREND, P_RS, P_EG, RET_12M, mktcap
    반환: 위 + DIV, DIV_z, IEG_z, CXD_raw, CXD, CXD_rank
    """
    P = panel.copy()

    # ── 구조적 쇠퇴 셀 처리 (§3.1 [3] / arm D) ──────────────────────────────────────────
    P["cell_active"] = P["TREND"] >= RULES["trend_active_min"]
    if not arm.include_declining:
        P.loc[~P["cell_active"].fillna(False), ["IEG", "FGR"]] = np.nan

    # ── [5] 통관 벤치마크 대비 초과 성장 ────────────────────────────────────────────────
    #   차분(β=1 가정)이 아니라 횡단면 회귀 잔차. β 는 시점별 풀링 회귀 1개 계수 = 자유도 0.
    P["DIV"] = batched_xsec_resid(P, "FGR", [RULES["div_x"]], by=by)
    P["DIV_w"] = xsec_winsorize(P, "DIV", by)
    P["DIV_z"] = xsec_z(P, "DIV_w", by)

    P["IEG_w"] = xsec_winsorize(P, "IEG", by)
    P["IEG_z"] = xsec_z(P, "IEG_w", by)

    # ── [6] 최종 신호 ───────────────────────────────────────────────────────────────────
    if arm.signal == "product":
        P["CXD_raw"] = P["DIV_z"] * (-P["IEG_z"])
    elif arm.signal == "div":
        P["CXD_raw"] = P["DIV_z"]
    elif arm.signal == "negieg":
        P["CXD_raw"] = -P["IEG_z"]
    else:
        raise ValueError(f"알 수 없는 arm.signal: {arm.signal}")

    P["LOG_MKTCAP"] = np.log(pd.to_numeric(P["mktcap"], errors="coerce")
                             .where(lambda s: s > 0))
    have = [c for c in RULES["resid_x"] if c in P.columns and P[c].notna().any()]
    P["CXD"] = batched_xsec_resid(P, "CXD_raw", have, by=by) if have else P["CXD_raw"]
    P["_resid_x_used"] = ",".join(have)

    # ── 정규화: winsorize → percentile rank ─────────────────────────────────────────────
    P["CXD_w"] = xsec_winsorize(P, "CXD", by)
    P["CXD_rank"] = xsec_rank_pct(P, "CXD_w", by)   # 높을수록 매수 (§3.1 [7] 사전 확정)
    return P
