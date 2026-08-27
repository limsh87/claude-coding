# -*- coding: utf-8 -*-
"""메커니즘 검정.   §29 · §39 · §46 · §54 · §63 · §64 · §80 · §81 · §82 · §84

이 파일이 답해야 하는 질문
  §80 정부수요↑ → EligibleTAM↑ → 낙찰확률↑ → 계약금액↑ → 향후 매출↑
      각 화살표마다 effect size · t · N · lag 를 낸다.
  §63 Demand only / Win only / Alignment 의 증분성
  §64 단계별(PLAN/PRESPEC/BID/AWARD/CONTRACT) 정보가치 — 사후선택 금지
  §84 가장 중요한 비교: 복잡한 Demand Graph 가 단순 '낙찰금액/시총'보다 나은가
  §46 §47 계약 → DART 매출 인식 지연 — rolling estimation 아니면 MECHANISM_VALIDATION_ONLY
  §82 각 이벤트의 [-20,+60] 거래일 CAR
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from backtest.statistics import newey_west_t, perf_table, information_coefficient, t_to_p, bh_fdr
from backtest.portfolio import build_portfolio, benchmark_returns
from features.g2b_dwa import xsec_pct, factor_family
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _panel_regression(d: pd.DataFrame, y: str, x: str, month_col: str = "month",
                      min_n: int = 20) -> dict:
    """월별 횡단면 회귀 계수의 시계열 평균 + NW t (Fama-MacBeth 형)."""
    d = d[[month_col, x, y]].dropna()
    if len(d) < min_n * 3:
        return {"beta": np.nan, "t": np.nan, "N": len(d), "months": 0}
    betas = []
    for m, g in d.groupby(month_col, observed=True):
        if len(g) < min_n:
            continue
        xv = pd.to_numeric(g[x], errors="coerce").to_numpy(float)
        yv = pd.to_numeric(g[y], errors="coerce").to_numpy(float)
        sx = np.nanstd(xv)
        if not np.isfinite(sx) or sx <= 0:
            continue
        xz = (xv - np.nanmean(xv)) / sx
        A = np.column_stack([np.ones(len(g)), np.nan_to_num(xz)])
        try:
            b, *_ = np.linalg.lstsq(A, yv, rcond=None)
            betas.append(b[1])
        except Exception:                                      # noqa: BLE001
            continue
    if not betas:
        return {"beta": np.nan, "t": np.nan, "N": len(d), "months": 0}
    mu, se, t = newey_west_t(np.array(betas))
    return {"beta": mu, "t": t, "N": len(d), "months": len(betas)}


def causal_chain(F: pd.DataFrame, firm_col: str = "stock_code",
                 month_col: str = "month") -> pd.DataFrame:
    """§80 — 인과 사슬 각 화살표의 효과크기·t·N·lag."""
    d = F.sort_values([firm_col, month_col], kind="stable").copy()
    g = d.groupby(firm_col, sort=False, observed=True)
    # 미래 자기변수(수주·계약)는 '메커니즘 검정'이지 신호가 아니다 — 팩터에 절대 넣지 않는다.
    for h in (3, 6, 12):
        d[f"fwd_award_{h}m"] = g["award_amt_12m"].shift(-h)
        if "contract_amt_12m" in d.columns:
            d[f"fwd_contract_{h}m"] = g["contract_amt_12m"].shift(-h)
    rows = []
    links = [
        ("① 정부수요↑ → EligibleTAM↑", "eligible_demand_flow_12m", "D1_DS_YOY", 0),
        ("② EligibleTAM↑ → 향후 낙찰↑(3M)", "fwd_award_3m", "D1_DS_YOY", 3),
        ("② EligibleTAM↑ → 향후 낙찰↑(6M)", "fwd_award_6m", "D1_DS_YOY", 6),
        ("② EligibleTAM↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "D1_DS_YOY", 12),
        ("③ 파이프라인↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "D2_PIPELINE_YOY", 12),
        ("④ 낙찰↑ → 계약↑(6M)", "fwd_contract_6m", "win_accel_log", 6),
        ("⑤ 정합(DWA)↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "G2B_DWA", 12),
    ]
    for name, y, x, lag in links:
        if y not in d.columns or x not in d.columns:
            rows.append({"연결": name, "설명변수": x, "피설명": y, "lag(M)": lag,
                         "효과크기": np.nan, "t": np.nan, "N": 0, "월수": 0, "비고": "변수 없음"})
            continue
        dd = d.copy()
        dd[y] = np.log1p(pd.to_numeric(dd[y], errors="coerce").clip(lower=0))
        r = _panel_regression(dd, y, x, month_col)
        rows.append({"연결": name, "설명변수": x, "피설명": y, "lag(M)": lag,
                     "효과크기": r["beta"], "t": r["t"], "N": r["N"], "월수": r["months"],
                     "비고": ""})
    return pd.DataFrame(rows)


def revenue_lag_analysis(F: pd.DataFrame, sales: pd.DataFrame, firm_col: str = "stock_code",
                         month_col: str = "month",
                         quarters: Sequence[int] = (1, 2, 3, 4, 6, 8)) -> pd.DataFrame:
    """§46 §47 — G2B 계약 → DART 매출 인식 지연.

    ★ §47 이 결과로 signal weighting 을 바꾸려면 rolling historical estimation 만 허용된다.
      그렇지 않으면 MECHANISM_VALIDATION_ONLY 로 둔다. 이 함수는 후자다.
    """
    if sales is None or not len(sales) or "contract_amt_12m" not in F.columns:
        return pd.DataFrame([{"상태": "NOT_IDENTIFIABLE",
                              "사유": "PIT 매출 또는 계약금액이 없어 매출인식 지연을 볼 수 없습니다"}])
    s = sales.copy()
    s["month"] = pd.to_datetime(s["filing_ts"]) + pd.offsets.MonthEnd(0)
    s = s.sort_values([firm_col, "month"], kind="stable")
    s["rev_yoy"] = s.groupby(firm_col, observed=True)["revenue"].pct_change(4)
    rows = []
    for k in quarters:
        sk = s.copy()
        sk[month_col] = sk["month"] - pd.DateOffset(months=3 * k)
        sk[month_col] = sk[month_col] + pd.offsets.MonthEnd(0)
        j = F[[firm_col, month_col, "contract_amt_12m", "mcap"]].merge(
            sk[[firm_col, month_col, "rev_yoy"]], on=[firm_col, month_col], how="inner").dropna()
        if len(j) < 60:
            rows.append({"lag(분기)": k, "표본": len(j), "효과크기": np.nan, "t": np.nan,
                         "비고": "표본부족"})
            continue
        j["x"] = np.log1p(j["contract_amt_12m"].clip(lower=0) / j["mcap"].replace(0, np.nan))
        r = _panel_regression(j, "rev_yoy", "x", month_col, min_n=10)
        rows.append({"lag(분기)": k, "표본": r["N"], "효과크기": r["beta"], "t": r["t"],
                     "비고": "MECHANISM_VALIDATION_ONLY (§47)"})
    return pd.DataFrame(rows)


def decomposition(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§63 — Demand only / Win only / Alignment 의 증분성."""
    specs = [("Demand only (D1)", "D1_DS_YOY"), ("Win only (W)", "W_PRIMARY"),
             ("Demand-Win Alignment", "G2B_DWA")]
    rows = []
    for name, col in specs:
        if col not in F.columns:
            continue
        pf = build_portfolio(F, col, ret_col)
        if not len(pf["returns"]):
            rows.append({"구성": name, "팩터": col, "관측월": 0})
            continue
        bm = benchmark_returns(F, ret_col)
        R = pf["returns"].set_index(month_col)
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        ic, _ = information_coefficient(F, col, ret_col, month_col)
        rows.append({"구성": name, "팩터": col, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "평균IC": float(ic["평균IC"].iloc[0]) if len(ic) else np.nan,
                     "IC_t": float(ic["IC_t"].iloc[0]) if len(ic) else np.nan})
    return pd.DataFrame(rows)


def stage_information_value(F_by_stage: Dict[str, pd.DataFrame], ret_col: str,
                            score_col: str = "G2B_DWA") -> pd.DataFrame:
    """§64 — PLAN/PRESPEC/BID/AWARD/CONTRACT 각각의 정보가치.

    ★ 이 5개 중 성과가 가장 좋은 것을 골라 PRIMARY 라 부르지 않는다. 해석용이다.
    """
    rows = []
    for st, F in F_by_stage.items():
        if F is None or not len(F) or score_col not in F.columns:
            rows.append({"단계": st, "관측월": 0, "비고": "데이터 없음"})
            continue
        pf = build_portfolio(F, score_col, ret_col)
        if not len(pf["returns"]):
            rows.append({"단계": st, "관측월": 0, "비고": "표본부족"})
            continue
        bm = benchmark_returns(F, ret_col)
        R = pf["returns"].set_index("month")
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        rows.append({"단계": st, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "비고": "해석용 — PRIMARY 사후선택 금지(§64)"})
    return pd.DataFrame(rows)


def nested_comparison(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§84 §99 — 이 연구의 최종 판정표.

    '복잡한 Demand Graph 가 단순 낙찰금액/시총보다 실제로 나은가?'
    복잡성이 단순모델을 이기지 못하면 단순모델을 채택한다.
    """
    fam = factor_family(F)
    rows = []
    for name, col in fam.items():
        if col not in F.columns or F[col].notna().sum() < 100:
            rows.append({"모델": name, "팩터": col, "관측월": 0, "비고": "산출 불가"})
            continue
        pf = build_portfolio(F, col, ret_col)
        bm = benchmark_returns(F, ret_col)
        if not len(pf["returns"]):
            rows.append({"모델": name, "팩터": col, "관측월": 0, "비고": "표본부족"})
            continue
        R = pf["returns"].set_index(month_col)
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        ic, _ = information_coefficient(F, col, ret_col, month_col)
        rows.append({"모델": name, "팩터": col, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "p": float(t["p(NW)"]), "Sharpe": float(t["Sharpe"]),
                     "MDD": float(t["MDD"]),
                     "평균IC": float(ic["평균IC"].iloc[0]) if len(ic) else np.nan,
                     "복잡도": {"1_Award_Amount_only": "단순", "2_Award_over_MCap": "단순",
                              "3_Demand_Shift_only": "중간", "4_Win_Acceleration_only": "중간",
                              "5_Demand_Win_Alignment": "복합"}.get(name, "")})
    T = pd.DataFrame(rows)
    if len(T) and "순초과(연,%)" in T.columns:
        simple = T[T["복잡도"] == "단순"]["순초과(연,%)"].max()
        full = T[T["복잡도"] == "복합"]["순초과(연,%)"].max()
        if pd.notna(simple) and pd.notna(full):
            T.attrs["verdict"] = ("FULL_WINS" if full > simple + 0.5 else "SIMPLE_ADOPTED")
            LOG.info(f"§99 판정: 단순 최고 {simple:.2f}%p vs 복합 {full:.2f}%p → "
                     f"{T.attrs['verdict']}")
    return T


def bucket_2x2(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§29 — Demand High/Low × Win High/Low. 핵심 가설상 D_high·W_high 가 가장 좋아야 한다."""
    d = F.dropna(subset=["P_D", "P_W", ret_col]).copy()
    if not len(d):
        return pd.DataFrame()
    d["bucket"] = np.where((d["P_D"] >= .5) & (d["P_W"] >= .5), "D_high_W_high",
                    np.where((d["P_D"] >= .5) & (d["P_W"] < .5), "D_high_W_low",
                      np.where((d["P_D"] < .5) & (d["P_W"] >= .5), "D_low_W_high", "D_low_W_low")))
    bm = benchmark_returns(d, ret_col)
    rows = []
    for b, g in d.groupby("bucket", observed=True):
        r = g.groupby(month_col, observed=True)[ret_col].mean()
        ex = (r - bm.reindex(r.index)).dropna()
        t = perf_table(ex).iloc[0]
        rows.append({"버킷": b, "평균 종목수": float(g.groupby(month_col).size().mean()),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "관측월": int(t["관측월"])})
    T = pd.DataFrame(rows).sort_values("순초과(연,%)", ascending=False).reset_index(drop=True)
    T["비고"] = np.where(T["버킷"] == "D_high_W_high",
                       "가설상 최상위여야 함 — 메커니즘 확인용이며 파라미터 탐색 도구가 아니다(§29)", "")
    return T


def secondary_family_fdr(F: pd.DataFrame, ret_col: str, candidates: Sequence[str],
                         month_col: str = "month", q: float = 0.10) -> pd.DataFrame:
    """§78 — Secondary family 에 BH/FDR 적용. 최고 t 하나만 보고 성공이라 하지 않는다."""
    rows = []
    for c in candidates:
        if c not in F.columns or F[c].notna().sum() < 100:
            continue
        ic, _ = information_coefficient(F, c, ret_col, month_col)
        if not len(ic):
            continue
        t = float(ic["IC_t"].iloc[0])
        rows.append({"팩터": c, "평균IC": float(ic["평균IC"].iloc[0]), "IC_t": t,
                     "월수": int(ic["월수"].iloc[0]), "p": t_to_p(t, max(int(ic["월수"].iloc[0]) - 1, 5))})
    if not rows:
        return pd.DataFrame()
    T = pd.DataFrame(rows)
    bh = bh_fdr(T["p"].tolist(), q=q)
    T["BH_임계값"] = bh["BH_임계값"].to_numpy()
    T["FDR 기각"] = bh["기각(FDR)"].to_numpy()
    return T.sort_values("p").reset_index(drop=True)


def event_study(events: pd.DataFrame, market_daily: Optional[pd.DataFrame], firm_col: str = "stock_code",
                window: Tuple[int, int] = (-20, 60)) -> pd.DataFrame:
    """§54 §82 — 단계별 [-20,+60] 거래일 CAR.

    일별 가격이 없으면 NOT_IDENTIFIABLE 로 두고 월별 근사로 대체하지 않는다
    (월 단위로 [-20,+60] 을 흉내내면 그건 event study 가 아니다).
    """
    if market_daily is None or not len(market_daily):
        return pd.DataFrame([{"상태": "NOT_IDENTIFIABLE",
                              "사유": "일별 수익률 패널이 없어 [-20,+60] CAR 을 계산할 수 없습니다(§82). "
                                    "공용 인덱스에 krx_ohlcv_daily 가 있으면 자동으로 계산됩니다."}])
    md = market_daily[[firm_col, "date", "ret"]].dropna().sort_values([firm_col, "date"])
    md["_i"] = md.groupby(firm_col, observed=True).cumcount()
    idx = md.set_index([firm_col, "date"])["_i"]
    rows = []
    for st, g in events[events[firm_col].notna()].groupby("stage", observed=True):
        ev = g[[firm_col, "available_at"]].dropna().copy()
        ev["date"] = pd.to_datetime(ev["available_at"]).dt.normalize()
        j = ev.join(idx, on=[firm_col, "date"], how="inner")
        if not len(j):
            continue
        car = []
        for off in range(window[0], window[1] + 1):
            t = md.merge(j.assign(_t=j["_i"] + off)[[firm_col, "_t"]],
                         left_on=[firm_col, "_i"], right_on=[firm_col, "_t"], how="inner")
            if len(t):
                car.append({"stage": st, "day": off, "mean_ret": float(t["ret"].mean()),
                            "n": len(t)})
        if car:
            C = pd.DataFrame(car).sort_values("day")
            C["CAR"] = C["mean_ret"].cumsum()
            rows.append(C)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        [{"상태": "NO_MATCH", "사유": "이벤트 일자와 거래일이 매칭되지 않았습니다"}])
