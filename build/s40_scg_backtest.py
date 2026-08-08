

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 · 성과검증 (§36~§40)                                                        ║
# ║                                                                                          ║
# ║  ★ 이 전략의 백테스트는 '포트폴리오 최적화'가 아니라 '알파의 존재 증명'이다.                 ║
# ║    그래서 threshold 를 튜닝하지 않는다(§36). 십분위로 자르고 단조성을 본다.                 ║
# ║    네 전략(BASE_REV / SCG_0 / SCG_LS / SCG_LSA)은 같은 유니버스·같은 리밸런스로 돈다(§37).  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


def scg_forward_returns(signals: pd.DataFrame, px: pd.DataFrame, cal,
                        horizons_td: Sequence[int], sec: Optional[pd.DataFrame] = None,
                        delist_mode: str = "last_price") -> pd.DataFrame:
    """signal date 기준 전방수익률. 리밸런스용 `ret_next` 와 IC 용 `fwd_ret_{h}` 를 만든다.

    ★ 생존자편향 방어의 마지막 관문이 여기다. 폐지 종목의 수익률을 '결측'으로 두면
      그 종목은 조용히 표본에서 빠지고, 남은 것은 살아남은 종목뿐이다.
      그래서 폐지된 종목은 반드시 값을 갖는다:
        delist_mode="last_price" : 마지막 체결가까지의 실현손익 (정리매매에서 판 것과 같음)
        delist_mode="minus100"   : -100% (정리매매 자체가 없었다고 보는 보수적 가정)
      진입 후 단 한 번도 체결이 없었으면 두 모드 모두 -100% 다.
    """
    out = signals.copy()
    calv = _scg_trading_calendar(cal)
    M, codes, didx = _scg_price_matrix(px, calv)
    hs = sorted({int(h) for h in horizons_td})
    cols = [f"fwd_ret_{h}" for h in hs] + ["ret_next", "n_delisted_used"]
    if M.size == 0 or not codes:
        for c in cols:
            out[c] = np.nan
        LOG.warn("가격 행렬이 비어 전방수익률을 계산할 수 없습니다 — 백테스트는 건너뜁니다.")
        return out

    ci = out["stock_id"].map(codes)
    known = ci.notna()
    ci_v = ci.fillna(0).to_numpy("int64")
    sd = out["signal_date"].values.astype("datetime64[ns]")
    #  signal date 이하의 마지막 거래일에 체결된 가격으로 진입한다(그 날 알 수 있는 값).
    p0i = np.searchsorted(didx, sd, side="right") - 1
    valid0 = known.to_numpy() & (p0i >= 0)
    base = np.where(valid0, M[np.clip(p0i, 0, len(didx) - 1), ci_v], np.nan)

    #  종목별 마지막 체결 위치 (폐지 처리의 근거)
    has = ~np.isnan(M)
    lastpos = np.where(has.any(axis=0), has.shape[0] - 1 - has[::-1].argmax(axis=0), -1)
    last_px = np.where(lastpos >= 0, M[np.clip(lastpos, 0, len(didx) - 1),
                                       np.arange(M.shape[1])], np.nan)

    n_delist = np.zeros(len(out), dtype="int32")

    def _ret_at(pos: np.ndarray) -> np.ndarray:
        pos_c = np.clip(pos, 0, len(didx) - 1)
        inrange = valid0 & (pos >= 0)
        px_h = np.where(inrange, M[pos_c, ci_v], np.nan)
        #  지평 시점에 가격이 없다 = 그 사이에 폐지되었거나 캘린더를 넘어섰다.
        gone = inrange & np.isnan(px_h) & (lastpos[ci_v] >= 0) & (lastpos[ci_v] >= p0i)
        beyond = pos >= len(didx)          # 데이터 끝을 넘어선 것은 '폐지'가 아니다
        if delist_mode == "minus100":
            px_g = np.zeros_like(px_h)
        else:
            px_g = last_px[ci_v]
        px_h = np.where(gone & ~beyond, px_g, px_h)
        r = np.where(np.isfinite(base) & (base > 0), px_h / base - 1.0, np.nan)
        #  진입 후 한 번도 체결이 없었으면 팔 기회 자체가 없었다 → -100%
        r = np.where(gone & ~beyond & ~np.isfinite(r), -1.0, r)
        return np.clip(r, -1.0, None), (gone & ~beyond)

    for h in hs:
        r, g = _ret_at(p0i + h)
        out[f"fwd_ret_{h}"] = r
        n_delist += g.astype("int32")

    #  리밸런스 수익률은 '다음 signal date 까지' — 고정 21거래일이 아니다.
    #  (월말 그리드에서 21일로 고정하면 달마다 며칠씩 겹치거나 비어 복리가 어긋난다)
    sdu = pd.DatetimeIndex(sorted(pd.unique(out["signal_date"])))
    nxt = pd.Series(list(sdu[1:]) + [pd.NaT], index=sdu)
    nd = out["signal_date"].map(nxt).values.astype("datetime64[ns]")
    p1i = np.where(pd.isna(nd), -1, np.searchsorted(didx, nd, side="right") - 1)
    r, g = _ret_at(p1i)
    out["ret_next"] = np.where(pd.isna(nd), np.nan, r)
    out["n_delisted_used"] = n_delist + g.astype("int32")

    nd_tot = int((out["n_delisted_used"] > 0).sum())
    if nd_tot:
        LOG.info(f"폐지·거래종료 구간을 포함해 수익률을 산출한 신호 {nd_tot:,}건 "
                 f"(모드={delist_mode}). 이 건들을 결측으로 버리면 생존자편향이 생깁니다.")
    return out


def scg_perf(rets: pd.Series, periods_per_year: float, rf: float = 0.0) -> Dict[str, float]:
    """§37 필수 성과 항목. 입력은 기간수익률 시계열(리밸런스 주기 단위)."""
    r = pd.Series(rets).dropna().astype("float64")
    n = len(r)
    if n == 0:
        return {k: np.nan for k in ("annualized_return", "CAGR", "volatility", "Sharpe",
                                    "MDD", "hit_rate", "n_periods")}
    eq = (1.0 + r).cumprod()
    yrs = n / float(periods_per_year)
    total = float(eq.iloc[-1])
    cagr = (total ** (1.0 / yrs) - 1.0) if (yrs > 0 and total > 0) else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else np.nan
    ann = float(r.mean() * periods_per_year)
    dd = eq / eq.cummax() - 1.0
    return {
        "annualized_return": ann,
        "CAGR": cagr,
        "volatility": vol,
        "Sharpe": float((ann - rf) / vol) if (vol and np.isfinite(vol) and vol > 0) else np.nan,
        "MDD": float(dd.min()),
        "hit_rate": float((r > 0).mean()),
        "n_periods": float(n),
    }


def scg_bucket_backtest(sig: pd.DataFrame, alpha_col: str, n_buckets: int,
                        min_n: int, cost_bps: float, ret_col: str = "ret_next"
                        ) -> Dict[str, Any]:
    """§36 — signal date 마다 알파 십분위(표본이 작으면 5분위)로 자르고 동일가중 보유.

    반환: buckets(시점×버킷 수익률), summary(버킷별 요약), long/ls 시계열, 회전율.
    ★ threshold 를 최적화하지 않는다. 자르는 규칙은 '분위수' 하나뿐이다.
    """
    need = {"signal_date", "stock_id", alpha_col, ret_col}
    d = sig[[c for c in sig.columns if c in need]].dropna(subset=["signal_date", "stock_id", alpha_col])
    res: Dict[str, Any] = {"alpha_col": alpha_col, "buckets": pd.DataFrame(),
                           "summary": pd.DataFrame(), "long": pd.Series(dtype="float64"),
                           "ls": pd.Series(dtype="float64"), "turnover": np.nan,
                           "avg_holdings": np.nan, "n_signals": int(len(d)),
                           "n_unique_stocks": int(d["stock_id"].nunique()) if len(d) else 0,
                           "n_buckets_used": n_buckets}
    if d.empty:
        return res

    rows, holds = [], {}
    used_nb = []
    for T, g in d.groupby("signal_date", observed=True, sort=True):
        g = g.dropna(subset=[ret_col])
        m = len(g)
        if m < 5:
            continue
        nb = n_buckets if m >= min_n else 5
        if m < nb:
            continue
        used_nb.append(nb)
        #  동점이 많은 rank 컬럼에서 qcut 은 자주 실패한다 → 순위 기반으로 균등 분할한다.
        r = g[alpha_col].rank(method="first", ascending=True)
        b = np.minimum((r.to_numpy() - 1) // (m / nb), nb - 1).astype("int32")
        g = g.assign(_b=b, _nb=nb)
        for bi, gg in g.groupby("_b", observed=True):
            rows.append({"signal_date": T, "bucket": int(bi), "n_buckets": nb,
                         "ret": float(gg[ret_col].mean()), "n": int(len(gg))})
        top = g.loc[g["_b"] == nb - 1, "stock_id"]
        holds[T] = set(top.astype(str))

    if not rows:
        return res
    B = pd.DataFrame(rows)
    nb_mode = int(pd.Series(used_nb).mode().iloc[0])
    res["n_buckets_used"] = nb_mode

    #  버킷 번호를 항상 1..nb 로 통일해 5분위/10분위가 섞여도 최상/최하가 어긋나지 않게 한다
    B["bucket_label"] = np.where(B["n_buckets"] == nb_mode, B["bucket"] + 1,
                                 np.ceil((B["bucket"] + 1) * nb_mode / B["n_buckets"]).astype(int))
    piv = B.pivot_table(index="signal_date", columns="bucket_label", values="ret", aggfunc="mean")
    res["buckets"] = piv

    lo_b, hi_b = piv.columns.min(), piv.columns.max()
    #  회전율: 최상위 버킷 보유종목의 교체 비율 (0=그대로, 1=전량 교체)
    ks = sorted(holds)
    tos = [len(holds[b] ^ holds[a]) / max(1, len(holds[b] | holds[a]))
           for a, b in zip(ks, ks[1:])]
    res["turnover"] = float(np.mean(tos)) if tos else np.nan
    res["avg_holdings"] = float(np.mean([len(v) for v in holds.values()])) if holds else np.nan

    cost = (cost_bps / 1e4) * (res["turnover"] if np.isfinite(res["turnover"]) else 0.0) * 2.0
    res["long"] = (piv[hi_b] - cost).dropna()
    res["ls"] = (piv[hi_b] - piv[lo_b] - cost).dropna()

    smry = piv.mean().rename("mean_ret").to_frame()
    smry["std"] = piv.std()
    smry["hit"] = (piv > 0).mean()
    smry["n_periods"] = piv.notna().sum()
    res["summary"] = smry.reset_index().rename(columns={"bucket_label": "bucket"})

    #  §39 단조성 — 버킷 번호와 평균수익률의 스피어만 상관
    s = res["summary"].dropna(subset=["mean_ret"])
    if len(s) >= 3:
        res["monotonicity_spearman"] = float(
            pd.Series(s["bucket"]).corr(pd.Series(s["mean_ret"]), method="spearman"))
        res["top_minus_bottom"] = float(s["mean_ret"].iloc[-1] - s["mean_ret"].iloc[0])
    else:
        res["monotonicity_spearman"] = np.nan
        res["top_minus_bottom"] = np.nan
    return res


def scg_ic(sig: pd.DataFrame, alpha_col: str, horizons_td: Sequence[int]) -> pd.DataFrame:
    """§40 — signal date 별 Spearman(alpha, forward return) 과 그 요약통계."""
    rows = []
    for h in sorted({int(x) for x in horizons_td}):
        fc = f"fwd_ret_{h}"
        if fc not in sig.columns:
            continue
        d = sig[["signal_date", alpha_col, fc]].dropna()
        if d.empty:
            continue
        ics = (d.groupby("signal_date", observed=True)
                 .apply(lambda g: g[alpha_col].corr(g[fc], method="spearman")
                        if len(g) >= 5 else np.nan, include_groups=False)
                 .dropna())
        if ics.empty:
            continue
        sd_ = float(ics.std(ddof=1)) if len(ics) > 1 else np.nan
        rows.append({
            "horizon_td": h, "n_dates": int(len(ics)),
            "mean_ic": float(ics.mean()), "median_ic": float(ics.median()),
            "ic_std": sd_,
            "ic_ir": float(ics.mean() / sd_) if (sd_ and np.isfinite(sd_) and sd_ > 0) else np.nan,
            "positive_ic_ratio": float((ics > 0).mean()),
            "t_stat": float(ics.mean() / (sd_ / np.sqrt(len(ics)))) if (sd_ and sd_ > 0) else np.nan,
        })
    return pd.DataFrame(rows)


def scg_run_all_strategies(sig: pd.DataFrame, cfg: SCGConfig = SCG,
                           bench: Optional[pd.Series] = None, label: str = "") -> Dict[str, Any]:
    """§37 — 네 전략을 동일 유니버스·동일 리밸런스로 나란히 돌린다."""
    ppy = 12.0 if SIGNAL_FREQ.upper().startswith("M") else 52.0
    out: Dict[str, Any] = {"label": label, "per_strategy": {}, "ppy": ppy}
    perf_rows, ic_frames, mono_rows = [], [], []

    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, BT_COST_BPS)
        ics = scg_ic(sig, acol, IC_HORIZONS_TD)
        out["per_strategy"][name] = {"bt": bt, "ic": ics}
        p = scg_perf(bt["long"], ppy)
        pls = scg_perf(bt["ls"], ppy)
        row = {"strategy": name, "n_signals": bt["n_signals"],
               "n_unique_stocks": bt["n_unique_stocks"],
               "annualized_return": p["annualized_return"], "CAGR": p["CAGR"],
               "volatility": p["volatility"], "Sharpe": p["Sharpe"], "MDD": p["MDD"],
               "hit_rate": p["hit_rate"], "turnover": bt["turnover"],
               "average_holdings": bt["avg_holdings"],
               "LS_annual": pls["annualized_return"], "LS_Sharpe": pls["Sharpe"]}
        if bench is not None and len(bench):
            al = bt["long"]
            common = al.index.intersection(bench.index)
            row["excess_vs_bench"] = (float((al.loc[common] - bench.loc[common]).mean() * ppy)
                                      if len(common) else np.nan)
        perf_rows.append(row)
        mono_rows.append({"strategy": name, "n_buckets": bt["n_buckets_used"],
                          "spearman": bt.get("monotonicity_spearman"),
                          "top_minus_bottom": bt.get("top_minus_bottom")})
        if len(ics):
            ic_frames.append(ics.assign(strategy=name))

    out["performance"] = pd.DataFrame(perf_rows)
    out["monotonicity"] = pd.DataFrame(mono_rows)
    out["ic"] = pd.concat(ic_frames, ignore_index=True) if ic_frames else pd.DataFrame()
    return out
