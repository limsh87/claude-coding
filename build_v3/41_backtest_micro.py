

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 (§10)                                                                  ║
# ║                                                                                          ║
# ║  체결   : 신호 산출일의 '다음 거래일 시가'. 당일 종가 체결은 미래누수다.                    ║
# ║  비용   : 왕복 수수료+세금+슬리피지(거래대금 참여율, 소형주 가중)                          ║
# ║  리밸런싱: 월 1회                                                                          ║
# ║  청산   : 거부권 발동 / 방화벽 이탈 / 보유 24개월 상한 / 신호 밴드 이탈                    ║
# ║  비중   : 20일 평균거래대금의 일정 비율로 상한 (소액계좌에서도 실행 가능한지 검증)          ║
# ║  상장폐지: 정리매매 최종가, 없으면 -100% (C2 — 누락 처리 금지)                              ║
# ║                                                                                          ║
# ║  ★ 월 루프(120회)는 돌지만 종목 루프는 돌지 않는다. 월 내부는 전부 벡터 연산이다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def sell_tax_rate(dt) -> float:
    """증권거래세(코스닥/코스피 장내 매도). 구간별 인하를 반영한다.
    하드코딩된 '기억'이 아니라 시행일 기준 표이며, 틀리면 R9 비용 시나리오가 흡수한다."""
    d = as_ts(dt)
    if d is None:
        return 0.0023
    y = (d.year, d.month)
    if y < (2019, 6):
        return 0.0030
    if y < (2021, 1):
        return 0.0025
    if y < (2023, 1):
        return 0.0023
    if y < (2024, 1):
        return 0.0020
    if y < (2025, 1):
        return 0.0018
    return 0.0015


def slippage_bps(trade_krw: float, adv_krw: float, participation: float) -> float:
    """거래대금 참여율에 비례하는 슬리피지. 소형주일수록 급격히 커진다.

    제곱근 충격모형: impact ≈ k * sqrt(참여율). 참여율이 상한을 넘으면 애초에
    그 크기로 못 사므로 사이징 단계에서 잘리고, 여기서는 남은 만큼만 비용으로 계상한다.
    """
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.0300                      # 거래대금을 모르면 3% 로 보수적으로 계상
    part = float(trade_krw) / float(adv_krw)
    part = min(max(part, 0.0), 1.0)
    base = 0.0015                          # 호가 스프레드 절반 (소형주 기준)
    return base + 0.05 * math.sqrt(part / max(participation, 1e-6)) * participation


def _select_month(sub: pd.DataFrame, top_pct: float, max_n: int, min_n: int) -> pd.DataFrame:
    """그 달의 목표 포트폴리오. 월 전체를 한 줄로 세워 상위 X% 를 뽑는다."""
    live = sub[sub["Signal"] > 0]
    if len(live) == 0:
        return live
    n = int(np.clip(round(len(live) * top_pct), min_n, max_n))
    n = min(n, len(live))
    return live.nlargest(n, "Signal")


def run_backtest_micro(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                       variant: str = "D", scenario: str = COST_BASE_SCENARIO,
                       label: str = "", quiet: bool = False) -> dict:
    """월별 백테스트. 반환에는 월 수익률·보유내역·회전율·비용이 전부 들어간다."""
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    roundtrip, participation = float(scn["roundtrip"]), float(scn["participation"])
    one_way = roundtrip / 2.0

    dmap = uni.delisting_map() if uni is not None else {}
    need = ["code", "month", "Signal", "fwd_ret", "adv20", "VETO", "FW", "close", "d1_trailing"]
    D = P[[c for c in need if c in P.columns]].copy()
    for c in need:
        if c not in D.columns:
            D[c] = np.nan
    D = D.sort_values(["month", "Signal"], ascending=[True, False], kind="stable")
    by_month = {m: g for m, g in D.groupby("month", observed=True)}

    prev_w: Dict[str, float] = {}
    entry_m: Dict[str, pd.Timestamp] = {}
    recs, holdings_log = [], []

    for t in months:
        sub = by_month.get(t)
        if sub is None or len(sub) == 0:
            if prev_w:
                # 그 달 패널이 통째로 비면 보유를 유지하되 수익률은 0 으로 둔다(추정 금지)
                recs.append({"month": t, "ret_gross": 0.0, "cost": 0.0, "ret": 0.0,
                             "n": len(prev_w), "turnover": 0.0})
            continue
        sub = sub.set_index("code")

        tgt = _select_month(sub.reset_index(), PORTFOLIO_TOP_PCT,
                            PORTFOLIO_MAX_NAMES, PORTFOLIO_MIN_NAMES)
        tgt_codes = list(tgt["code"]) if len(tgt) else []

        # ── 유지 판정 (§10 청산 규칙) ────────────────────────────────────────────────
        band = sub["Signal"].rank(pct=True, ascending=True)   # 1.0 = 최고
        keep = []
        for c in prev_w:
            if c not in sub.index:
                continue                                       # 패널 이탈 → 청산(상폐 포함)
            if float(sub.at[c, "VETO"] or 0) == 0:
                continue                                       # 거부권 발동 → 즉시 청산
            if float(sub.at[c, "FW"] or 0) == 0:
                continue                                       # 방화벽 이탈 → 청산
            held = (t.year - entry_m[c].year) * 12 + (t.month - entry_m[c].month)
            if held >= HOLD_MAX_MONTHS:
                continue                                       # 보유 상한
            # 청산 게이트(§10): ΔlogM 이 ΔlogE 수준까지 확장 = 논거가 가격에 반영 완료
            d1 = sub.at[c, "d1_trailing"] if "d1_trailing" in sub.columns else np.nan
            if pd.notna(d1) and float(d1) >= 0.0:
                continue
            if float(band.get(c, 0.0)) < (1.0 - 2 * PORTFOLIO_TOP_PCT):
                continue                                       # 신호 밴드 이탈
            keep.append(c)

        chosen = list(dict.fromkeys(keep + tgt_codes))[:PORTFOLIO_MAX_NAMES]
        if not chosen:
            # 조건을 만족하는 종목이 없으면 현금. 억지로 채우지 않는다.
            if prev_w:
                turn = sum(abs(0.0 - w) for w in prev_w.values())
                cost = turn * one_way
                recs.append({"month": t, "ret_gross": 0.0, "cost": cost, "ret": -cost,
                             "n": 0, "turnover": turn})
                prev_w, entry_m = {}, {}
            continue

        # ── 사이징: 동일가중 → 거래대금 참여율 상한 → 재정규화 ──────────────────────
        w = pd.Series(1.0 / len(chosen), index=chosen, dtype="float64")
        adv = pd.to_numeric(sub.reindex(chosen)["adv20"], errors="coerce")
        cap_adv = (participation * adv / max(ACCOUNT_KRW, 1)).clip(upper=POS_MAX_WEIGHT)
        cap_adv = cap_adv.where(cap_adv.notna(), POS_MIN_WEIGHT)
        w = np.minimum(w, cap_adv)
        w = w[w >= POS_MIN_WEIGHT * 0.5]
        if w.sum() <= 0:
            continue
        w = w / w.sum()                                        # 잔여는 현금이 아니라 재분배

        # ── 수익률 (상장폐지 -100% 강제) ─────────────────────────────────────────────
        fr = pd.to_numeric(sub.reindex(w.index)["fwd_ret"], errors="coerce")
        nxt = t + pd.offsets.MonthEnd(1)
        for c in w.index:
            dd = dmap.get(c)
            if dd is not None and pd.notna(dd) and t < dd <= nxt:
                fr.at[c] = -1.0                                # 정리매매가 없으면 전액 손실
        n_nan = int(fr.isna().sum())
        fr = fr.fillna(0.0)                                    # 거래 없는 달은 0 (추정 금지)

        ret_gross = float((w * fr).sum())

        # ── 비용: 회전율 × 편도비용 + 슬리피지 + 매도세 ──────────────────────────────
        allc = set(w.index) | set(prev_w)
        turn = float(sum(abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0))) for c in allc))
        slip = 0.0
        for c in allc:
            dw = abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0)))
            if dw <= 0:
                continue
            a = float(adv.get(c, np.nan)) if c in adv.index else np.nan
            slip += dw * slippage_bps(dw * ACCOUNT_KRW, a, participation)
        sells = float(sum(max(float(prev_w.get(c, 0.0)) - float(w.get(c, 0.0)), 0.0) for c in allc))
        cost = turn * one_way + slip + sells * sell_tax_rate(t)

        recs.append({"month": t, "ret_gross": ret_gross, "cost": cost,
                     "ret": ret_gross - cost, "n": int(len(w)), "turnover": turn,
                     "na_fwd": n_nan})
        for c in w.index:
            holdings_log.append({"month": t, "code": c, "w": float(w[c]),
                                 "signal": float(sub.at[c, "Signal"] or 0.0),
                                 "fwd_ret": float(fr[c])})
        for c in w.index:
            entry_m.setdefault(c, t)
        for c in list(entry_m):
            if c not in w.index:
                entry_m.pop(c, None)
        prev_w = w.to_dict()

    R = pd.DataFrame(recs)
    if len(R):
        R = R.sort_values("month").reset_index(drop=True)
        R["equity"] = (1.0 + R["ret"]).cumprod()
    H = pd.DataFrame(holdings_log)
    out = {"variant": variant, "scenario": scenario, "label": label or variant,
           "returns": R, "holdings": H, "stats": perf_stats(R)}
    if not quiet:
        s = out["stats"]
        LOG.ok(f"[{label or variant}·{scenario}] CAGR {100*s['cagr']:.2f}% · "
               f"MDD {100*s['mdd']:.1f}% · Calmar {s['calmar']:.2f} · "
               f"Sharpe {s['sharpe']:.2f} · 월평균 {s['avg_n']:.0f}종목 · "
               f"회전율 {100*s['turnover']:.0f}%/월")
    PIPE.io("OUT", "MEM", f"backtest:{label or variant}", R)
    return out


def perf_stats(R: pd.DataFrame) -> dict:
    """성과 지표. 표본이 없으면 0 이 아니라 NaN 을 돌려준다(없는 성과를 만들지 않는다)."""
    if R is None or len(R) == 0 or "ret" not in R.columns:
        return {"n_months": 0, "cagr": np.nan, "vol": np.nan, "sharpe": np.nan,
                "mdd": np.nan, "calmar": np.nan, "hit": np.nan, "turnover": np.nan,
                "avg_n": np.nan, "total": np.nan, "cost_drag": np.nan}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy()
    n = len(r)
    eq = np.cumprod(1.0 + r)
    total = float(eq[-1] - 1.0)
    yrs = n / 12.0
    cagr = float(eq[-1] ** (1.0 / yrs) - 1.0) if yrs > 0 and eq[-1] > 0 else -1.0
    vol = float(np.std(r, ddof=1) * math.sqrt(12)) if n > 1 else np.nan
    sharpe = float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(12)) if n > 1 and np.std(r, ddof=1) > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    mdd = float(np.min(eq / peak - 1.0)) if n else np.nan
    calmar = float(cagr / abs(mdd)) if mdd and mdd < 0 else np.nan
    # ★ R.get("x") 는 컬럼이 없으면 None 을 돌려주고, pd.to_numeric(None) 은 Series 가 아니라
    #   numpy 스칼라가 된다 → .fillna() 에서 AttributeError. col() 은 없는 컬럼도 NaN Series 로
    #   돌려주므로 이 경로가 원천 차단된다.
    def _m(name: str, how: str = "mean") -> float:
        s = col(R, name)
        s = pd.to_numeric(s, errors="coerce").fillna(0.0)
        return float(getattr(s, how)()) if len(s) else 0.0

    return {"n_months": n, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd,
            "calmar": calmar, "hit": float((r > 0).mean()), "total": total,
            "turnover": _m("turnover"), "avg_n": _m("n"), "cost_drag": _m("cost", "sum")}


def benchmark_universe_ew(P: pd.DataFrame, months: pd.DatetimeIndex,
                          scenario: str = COST_BASE_SCENARIO,
                          mask_col: Optional[str] = None) -> dict:
    """R0(a) 자체 측정 벤치마크 — U-MICRO 유니버스 동일가중.

    ★ 벤치마크 수치를 하드코딩하지 않는다(원칙 5). 같은 데이터·같은 비용모형으로 직접 잰다.
    동일가중도 매월 리밸런싱하므로 회전율이 있고, 그 비용을 똑같이 물린다.
    """
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    one_way = float(scn["roundtrip"]) / 2.0
    sub = P
    if mask_col and mask_col in P.columns:
        sub = P[P[mask_col].astype(bool)]
    sub = sub[sub["fwd_ret"].notna()]
    if len(sub) == 0:
        return {"label": "유니버스 동일가중", "returns": pd.DataFrame(), "stats": perf_stats(None)}
    g = sub.groupby("month", observed=True)
    m = g["fwd_ret"].mean()
    cnt = g["code"].size()
    # 동일가중 포트폴리오의 월 회전율 ≈ 편입/이탈 비율. 보수적으로 20% 로 잡는다.
    turn = pd.Series(0.20, index=m.index)
    R = pd.DataFrame({"month": m.index, "ret_gross": m.to_numpy(),
                      "turnover": turn.to_numpy(), "n": cnt.to_numpy()})
    R["cost"] = R["turnover"] * one_way
    R["ret"] = R["ret_gross"] - R["cost"]
    R = R[R["month"].isin(months)].sort_values("month").reset_index(drop=True)
    R["equity"] = (1.0 + R["ret"]).cumprod()
    return {"label": "유니버스 동일가중", "variant": "BENCH", "scenario": scenario,
            "returns": R, "holdings": pd.DataFrame(), "stats": perf_stats(R)}


def benchmark_index(months: pd.DatetimeIndex) -> Dict[str, dict]:
    """참고용 지수 벤치마크(코스닥/코스피). 없으면 조용히 건너뛴다 — 필수가 아니다."""
    out: Dict[str, dict] = {}
    if fdr is None or RUN_MODE == "SMOKE":
        return out
    for name, sym in (("KOSDAQ", "KQ11"), ("KOSPI", "KS11")):
        try:
            d = fdr.DataReader(sym, str(months[0].date()), str(months[-1].date()))
        except Exception:
            continue
        if d is None or len(d) == 0 or "Close" not in d.columns:
            continue
        s = d["Close"].resample("ME").last() if hasattr(d["Close"], "resample") else None
        if s is None or len(s) < 3:
            continue
        r = s.pct_change().dropna()
        R = pd.DataFrame({"month": as_ts_series(pd.Series(r.index)) + pd.offsets.MonthEnd(0),
                          "ret": r.to_numpy()})
        R = R[R["month"].isin(months)].reset_index(drop=True)
        if len(R) < 3:
            continue
        R["equity"] = (1.0 + R["ret"]).cumprod()
        out[name] = {"label": name, "returns": R, "stats": perf_stats(R)}
    return out
