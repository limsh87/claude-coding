

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-B  백테스트 엔진 (SPEC §7 · §8)                                                       ║
# ║                                                                                          ║
# ║   · 5분위 정렬. 주 포트폴리오 = Q5 롱온리 동일가중 (한국 공매도 제약 반영)                  ║
# ║   · 참고 산출 = Q5−Q1 롱숏 스프레드 (알파 존재 검증용, 실행가능성과 무관하게 보고)          ║
# ║   · 보유 하한 20종목. 미달이면 그 리밸런싱은 현금 — 조용히 넘어가지 않고 로그에 남긴다.      ║
# ║   · 진입은 신호일의 익영업일 (신호 패널에서 이미 앵커됨). 겹치면 실패로 간주.               ║
# ║   · 상장폐지는 -100% 일괄이 아니라 정리매매 최종가 기준 (§0.3)                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 연도별 증권거래세 (SPEC §7.1 — 단일 세율 적용 금지) ─────────────────────────────────────
#   출처: 기획재정부 증권거래세법 시행령 개정 연혁
#     https://www.moef.go.kr  ·  https://www.law.go.kr/법령/증권거래세법시행령
#   유가증권시장 = 증권거래세 + 농어촌특별세 0.15%, 코스닥 = 증권거래세.
#   2019-06-03 · 2021-01-01 · 2023-01-01 · 2024-01-01 · 2025-01-01 에 각각 인하됐다.
SELL_TAX_SCHEDULE = [
    ("1900-01-01", {"KOSPI": 0.00300, "KOSDAQ": 0.00300, "OTHER": 0.00300}),
    ("2019-06-03", {"KOSPI": 0.00250, "KOSDAQ": 0.00250, "OTHER": 0.00250}),
    ("2021-01-01", {"KOSPI": 0.00230, "KOSDAQ": 0.00230, "OTHER": 0.00230}),
    ("2023-01-01", {"KOSPI": 0.00200, "KOSDAQ": 0.00200, "OTHER": 0.00200}),
    ("2024-01-01", {"KOSPI": 0.00180, "KOSDAQ": 0.00180, "OTHER": 0.00180}),
    ("2025-01-01", {"KOSPI": 0.00150, "KOSDAQ": 0.00150, "OTHER": 0.00150}),
]
_TAX_DATES = [as_ts(d) for d, _ in SELL_TAX_SCHEDULE]

SIZE_LARGE_KRW = 1_000_000_000_000       # 1조 이상 = large
SIZE_MID_KRW = 300_000_000_000           # 3천억 이상 = mid, 미만 = small


def sell_tax_rate(t, market: str) -> float:
    i = int(np.searchsorted(np.array([np.datetime64(x) for x in _TAX_DATES]),
                            np.datetime64(as_ts(t)), side="right")) - 1
    i = max(0, i)
    tbl = SELL_TAX_SCHEDULE[i][1]
    return float(tbl.get(str(market).upper(), tbl["OTHER"]))


def size_class(mktcap: float) -> str:
    if not np.isfinite(mktcap):
        return "small"
    if mktcap >= SIZE_LARGE_KRW:
        return "large"
    if mktcap >= SIZE_MID_KRW:
        return "mid"
    return "small"


def tax_schedule_table():
    rows = []
    for d, tbl in SELL_TAX_SCHEDULE:
        rows.append([d if d != "1900-01-01" else "~2019-06-02",
                     f"{tbl['KOSPI']*100:.3f}%", f"{tbl['KOSDAQ']*100:.3f}%"])
    LOG.table(rows, ["적용 시작일", "유가증권(매도)", "코스닥(매도)"], ["l", "r", "r"],
              title="증권거래세 연도별 테이블 (§7.1) — 출처: 증권거래세법 시행령 개정 연혁")


PERIODS_PER_YEAR = {"M": 12.0, "W": 52.0}


def perf_stats(R: pd.DataFrame, ppy: float = 12.0, rf: float = 0.0) -> dict:
    """성과 지표. 리밸런싱 주기(ppy)에 따라 연율화 계수가 달라진다.

    Sharpe 는 교과서 정의(평균/표준편차 × √ppy)를 쓴다. 기하수익/변동성 정의와 섞으면
    다른 표와 비교가 불가능해지므로 한 가지로 고정한다.
    """
    if R is None or not len(R):
        return {}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy(float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / ppy
    cagr = float(eq[-1] ** (1.0 / years) - 1.0) if years > 0 and eq[-1] > 0 else float("nan")
    vol = float(np.std(r, ddof=1) * math.sqrt(ppy)) if n > 1 else float("nan")
    dn = r[r < 0]
    dvol = float(np.std(dn, ddof=1) * math.sqrt(ppy)) if len(dn) > 1 else float("nan")
    dd = eq / np.maximum.accumulate(eq) - 1.0
    mdd = float(dd.min()) if n else float("nan")
    mu, tstat = hac_tstat(r)
    uw, best = 0, 0
    for x in dd:
        uw = uw + 1 if x < 0 else 0
        best = max(best, uw)
    out = {
        "기간수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(ppy)) if n > 1 and np.std(r, ddof=1) > 0 else float("nan"),
        "Sortino": float(np.mean(r) * ppy / dvol) if dvol and dvol > 0 else float("nan"),
        "MDD": mdd, "Calmar": float(cagr / abs(mdd)) if mdd and mdd < 0 else float("nan"),
        "승률": float((r > 0).mean()), "기간평균수익": float(np.mean(r)),
        "t통계량(HAC)": float(tstat), "최장언더워터(기간)": int(best),
        "누적수익": float(eq[-1] - 1.0),
    }
    if "n" in R.columns:
        out["평균종목수"] = float(pd.to_numeric(R["n"], errors="coerce").mean())
    if "turnover" in R.columns:
        out["평균회전율"] = float(pd.to_numeric(R["turnover"], errors="coerce").mean())
    if "cost" in R.columns:
        out["평균비용"] = float(pd.to_numeric(R["cost"], errors="coerce").mean())
    return out


def _assign_quantiles(g: pd.DataFrame, col: str, q: int) -> pd.Series:
    """동점 처리를 결정적으로: 신호 내림차순 → code 오름차순으로 순위를 확정한 뒤 분할."""
    d = g[[col, "code"]].copy()
    d["_r"] = d[col].rank(method="first", ascending=True)
    n = int(d["_r"].notna().sum())
    if n < q:
        return pd.Series(np.nan, index=g.index)
    lab = np.ceil(d["_r"] / (n / q))
    return pd.Series(np.clip(lab, 1, q), index=g.index)


def run_quantile_backtest(P: pd.DataFrame, signal_col: str, rebal: str,
                          delist: Optional[pd.DataFrame] = None,
                          cost_mult: float = 1.0, label: str = "SACN",
                          q: int = N_QUANTILES, min_names: int = PORT_MIN_NAMES,
                          long_only: bool = True) -> dict:
    """분위 백테스트. 반환 dict: returns / holdings / spread / label / meta"""
    empty = {"returns": pd.DataFrame(columns=["date", "ret", "ret_gross", "n", "turnover",
                                              "cost", "equity"]),
             "holdings": pd.DataFrame(), "spread": pd.DataFrame(), "label": label,
             "meta": {"cash_periods": 0, "ppy": PERIODS_PER_YEAR.get(rebal, 12.0)}}
    if P is None or not len(P) or signal_col not in P.columns:
        return empty

    d = P[P[signal_col].notna() & P["exec_px"].notna()].copy()
    if not len(d):
        return empty
    d["code"] = d["code"].astype(str)
    d["date"] = as_ts_series(d["date"])
    # 신호 패널은 메모리 절약을 위해 float32 다. 여기서 float64 로 올려 두지 않으면
    # 아래 폐지수익률(float64) 주입이 pandas 3.x 에서 dtype 상향 오류로 죽는다.
    for c in ("fwd_ret", "exec_px", signal_col):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")

    # 폐지 수익률 주입 (§0.3) — fwd_ret 이 결측인데 그 구간에 폐지된 종목
    if delist is not None and len(delist):
        dl = delist.copy()
        dl["code"] = dl["code"].astype(str)
        dl["month"] = as_ts_series(dl["month"])
        d["_m"] = d["date"] + pd.offsets.MonthEnd(0)
        d = d.merge(dl.rename(columns={"month": "_m"})[["code", "_m", "delist_ret"]],
                    on=["code", "_m"], how="left")
        inj = d["fwd_ret"].isna() & d["delist_ret"].notna()
        d.loc[inj, "fwd_ret"] = d.loc[inj, "delist_ret"]
        d = d.drop(columns=["_m", "delist_ret"], errors="ignore")

    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    if not len(d):
        return empty

    if "mktcap" not in d.columns:
        d["mktcap"] = np.nan
    if "market" not in d.columns:
        d["market"] = "OTHER"
    d["_size"] = d["mktcap"].map(size_class)

    dates = sorted(d["date"].unique())
    prev_w: Dict[str, float] = {}
    rows, holds, spreads = [], [], []
    cash_periods, cash_dates = 0, []

    for t in dates:
        t = as_ts(t)
        g = d[d["date"] == t]
        top = g[g["qtile"] == q]
        bot = g[g["qtile"] == 1]

        if len(top) < min_names:
            cash_periods += 1
            cash_dates.append(t)
            # 전량 청산 비용은 실제로 발생한다 — 현금 처리라고 0으로 두지 않는다
            cost = 0.0
            for c, w in prev_w.items():
                mk = g.loc[g["code"] == c, "market"]
                sz = g.loc[g["code"] == c, "_size"]
                cost += abs(w) * (COST_COMMISSION_BP / 1e4
                                  + COST_SLIPPAGE_BP.get(sz.iat[0] if len(sz) else "small", 35.0) / 1e4
                                  + sell_tax_rate(t, mk.iat[0] if len(mk) else "OTHER"))
            cost *= cost_mult
            rows.append({"date": t, "ret": -cost, "ret_gross": 0.0, "n": 0,
                         "turnover": float(sum(abs(v) for v in prev_w.values())), "cost": cost})
            prev_w = {}
            continue

        w = 1.0 / len(top)
        w = min(w, POS_MAX_WEIGHT)
        wmap = {c: w for c in top["code"]}
        # 상한 때문에 남은 비중은 현금으로 둔다 (억지로 종목을 늘리지 않는다)
        fr = pd.to_numeric(top["fwd_ret"], errors="coerce").fillna(0.0).to_numpy(float)
        ret_gross = float(np.sum(fr * w))

        cost, turn = 0.0, 0.0
        allc = set(wmap) | set(prev_w)
        smap = dict(zip(g["code"], g["_size"]))
        mmap = dict(zip(g["code"], g["market"]))
        for c in allc:
            dw = wmap.get(c, 0.0) - prev_w.get(c, 0.0)
            if abs(dw) < 1e-12:
                continue
            turn += abs(dw)
            slip = COST_SLIPPAGE_BP.get(smap.get(c, "small"), 35.0) / 1e4
            tax = sell_tax_rate(t, mmap.get(c, "OTHER")) if dw < 0 else 0.0
            cost += abs(dw) * (COST_COMMISSION_BP / 1e4 + slip + tax)
        cost *= cost_mult

        rows.append({"date": t, "ret": ret_gross - cost, "ret_gross": ret_gross,
                     "n": int(len(top)), "turnover": turn, "cost": cost})
        h = top[["code", "date", signal_col, "fwd_ret"]].copy()
        h["weight"] = w
        holds.append(h)

        if len(bot) >= min_names:
            rb = float(pd.to_numeric(bot["fwd_ret"], errors="coerce").fillna(0.0).mean())
            spreads.append({"date": t, "q5": ret_gross, "q1": rb, "spread": ret_gross - rb,
                            "n5": len(top), "n1": len(bot)})
        prev_w = wmap

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"]).cumprod()
    H = pd.concat(holds, ignore_index=True) if holds else pd.DataFrame()
    S = pd.DataFrame(spreads)
    if cash_periods:
        LOG.warn(f"[{label}] 보유 하한({min_names}종목) 미달로 {cash_periods}개 기간을 "
                 f"현금 보유 처리했습니다. 예: "
                 f"{', '.join(f'{x:%Y-%m-%d}' for x in cash_dates[:5])}"
                 f"{' …' if len(cash_dates) > 5 else ''}")
    n_per = max(1, len(dates))
    cash_ratio = cash_periods / n_per
    if cash_ratio > 0.5:
        LOG.error(f"[{label}] 전체 {n_per}기간 중 {cash_periods}기간({cash_ratio:.0%})이 현금입니다. "
                  f"유니버스가 작아 Q{q} 분위 종목수가 보유하한 {min_names}종목에 미달합니다. "
                  f"이 결과는 '전략의 성과'가 아니라 '표본 부족'입니다 — 판정에 쓰면 안 됩니다.")
    return {"returns": R, "holdings": H, "spread": S, "label": label,
            "meta": {"cash_periods": cash_periods, "n_periods": n_per,
                     "cash_ratio": cash_ratio, "ppy": PERIODS_PER_YEAR.get(rebal, 12.0),
                     "rebal": rebal, "signal_col": signal_col, "cost_mult": cost_mult}}


def quantile_profile(P: pd.DataFrame, signal_col: str, q: int = N_QUANTILES) -> pd.DataFrame:
    """분위별 평균 전향수익 — 신호가 단조인지 보는 가장 정직한 표."""
    if P is None or not len(P) or signal_col not in P.columns:
        return pd.DataFrame()
    d = P[P[signal_col].notna() & P["fwd_ret"].notna()].copy()
    if not len(d):
        return pd.DataFrame()
    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    per = d.groupby(["date", "qtile"])["fwd_ret"].mean().reset_index()
    out = per.groupby("qtile")["fwd_ret"].agg(["mean", "std", "size"]).reset_index()
    out.columns = ["분위", "평균수익", "표준편차", "기간수"]
    return out


# ── 벤치마크 ────────────────────────────────────────────────────────────────────────────────
def equal_weight_universe(grid: "PriceGrid", uni_panel: pd.DataFrame,
                          rebals: Sequence[pd.Timestamp]) -> pd.Series:
    """★ SPEC §8 이 말하는 '진짜 비교 기준'.

    시총가중 지수 대비 초과는 사이즈 팩터일 뿐이다. 같은 유니버스를 동일가중으로 들었을 때
    대비 초과가 나야 신호에 의미가 있다.

    ★ 신호 패널(연결 3개 이상인 종목)이 아니라 '유니버스 전체'로 계산한다.
      신호가 잡힌 종목만으로 벤치마크를 만들면, 커버리지가 두터운 종목만 모인 집단과
      비교하게 되어 초과수익이 구조적으로 과소평가된다. 비교 기준을 유리하게 만들지도,
      불리하게 만들지도 않는 유일한 방법은 유니버스 정의 그대로 쓰는 것이다.
    """
    if uni_panel is None or not len(uni_panel) or not len(rebals):
        return pd.Series(dtype=float)
    U = uni_panel[["code", "month"]].copy()
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])
    by_month = {as_ts(m): set(g["code"]) for m, g in U.groupby("month")}
    months_sorted = sorted(by_month)
    ex = {as_ts(t): grid.exec_price(t) for t in rebals}
    out = {}
    rb = [as_ts(t) for t in rebals]
    for i, t in enumerate(rb[:-1]):
        cand = [m for m in months_sorted if m <= t]
        if not cand:
            continue
        alive = by_month[max(cand)]
        p0, d0 = ex[t]
        p1, d1 = ex[rb[i + 1]]
        if d0 is None or d1 is None:
            continue
        gi = np.array([grid.cpos.get(c, -1) for c in alive])
        gi = gi[gi >= 0]
        if not len(gi):
            continue
        with np.errstate(all="ignore"):
            r = np.where((p0[gi] > 0) & np.isfinite(p0[gi]) & np.isfinite(p1[gi]),
                         p1[gi] / p0[gi] - 1.0, np.nan)
        if np.isfinite(r).sum() >= 5:
            out[t] = float(np.nanmean(r))
    s = pd.Series(out).sort_index()
    s.name = "동일가중 유니버스"
    return s


def index_benchmarks(dates: Sequence[pd.Timestamp]) -> Dict[str, pd.Series]:
    """KOSPI / KOSDAQ — 리밸런싱 시점 격자에 맞춰 수익률화."""
    out: Dict[str, pd.Series] = {}
    if fdr is None or not len(dates):
        return out
    idx = pd.DatetimeIndex(sorted(as_ts(d) for d in dates))
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            df = fdr.DataReader(sym, (idx[0] - pd.DateOffset(months=2)).strftime("%Y-%m-%d"),
                                idx[-1].strftime("%Y-%m-%d"))
            if df is None or df.empty:
                continue
            c = df["Close"].copy()
            c.index = as_ts_series(pd.Series(df.index)).to_numpy()
            v = c.reindex(c.index.union(idx)).sort_index().ffill().reindex(idx)
            out[name] = v.pct_change()
        except Exception as e:                                   # noqa
            LOG.debug(f"벤치마크 {name} 수집 실패({type(e).__name__})")
    return out


def benchmark_table(bt: dict, bench: Dict[str, pd.Series], ppy: float) -> List[list]:
    R = bt.get("returns")
    if R is None or not len(R):
        return []
    r = R.set_index(as_ts_series(R["date"]))["ret"]
    rows = []
    for name, b in bench.items():
        if b is None or not len(b):
            continue
        j = pd.concat([r.rename("s"), b.rename("b")], axis=1).dropna()
        if len(j) < 6:
            continue
        ex = j["s"] - j["b"]
        _, tt = hac_tstat(ex.to_numpy(float))
        rows.append([name, f"{(1+j['b']).prod() ** (ppy/len(j)) - 1:+.2%}",
                     f"{(1+j['s']).prod() ** (ppy/len(j)) - 1:+.2%}",
                     f"{ex.mean()*ppy:+.2%}", f"{tt:+.2f}",
                     "✔" if ex.mean() * ppy >= 0.03 else "—"])
    return rows
