

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 검사 (§41 + 연구질문 §47)                                                     ║
# ║                                                                                          ║
# ║  ★ 여기서 파라미터를 '최적화'하지 않는다(§41). 공식값은 45/6/20 으로 고정이고,              ║
# ║    민감도 표는 "이 결론이 파라미터 한 칸 옮기면 사라지는가"만 본다.                         ║
# ║    성과가 가장 좋은 조합을 사후에 공식전략으로 승격하는 것은 명시적으로 금지되어 있다.       ║
# ║                                                                                          ║
# ║  검사 순서에도 뜻이 있다:                                                                  ║
# ║    S0 누수민감도 → (하네스가 알파를 감지할 수 있는가? 아니면 아래 전부가 무의미)             ║
# ║    S1 증분기여   → (§47 의 세 질문. 이 전략의 존재 이유)                                    ║
# ║    S2 민감도 → S3 하위기간 → S4 집중도 → S5 레짐 → S6 플라시보 → S7 비용                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_ROBUST: List[Dict[str, Any]] = []


def _rb(test: str, metric: str, value: Any, verdict: str, note: str = ""):
    SCG_ROBUST.append({"test": test, "metric": metric, "value": value,
                       "verdict": verdict, "note": note})


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, (int, float, np.floating)) else str(v)


def _ls_series(sig: pd.DataFrame, acol: str, ret_col: str = "ret_next") -> pd.Series:
    bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, 0.0, ret_col)
    return bt["ls"]


# ── S0. 누수 민감도 ──────────────────────────────────────────────────────────────────────
def S0_leak_sensitivity(sig: pd.DataFrame, ppy: float):
    """고의로 오염된 신호(미래수익률 주입)가 확실히 좋아지는지 본다.

    ★ 이 검사가 먼저인 이유: 오염본조차 성과가 안 나오면, 그건 '알파가 없다'가 아니라
      '하네스가 알파를 못 잡는다'는 뜻이다. 그 상태에서 아래 검사들을 읽으면 전부 오독이다.
      (실제 신호를 1개월 선행시키는 방식만으로는 이 둘을 구분할 수 없어 채택하지 않았다)
    """
    d = sig.dropna(subset=["ret_next", "alpha_ls"]).copy()
    if d.empty:
        _rb("S0 누수민감도", "—", np.nan, "SKIP", "표본 없음")
        return
    clean = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    d["_dirty"] = d.groupby("signal_date", observed=True)["ret_next"].rank(pct=True)
    dirty = scg_perf(_ls_series(d, "_dirty"), ppy)["Sharpe"]
    ok = np.isfinite(dirty) and (not np.isfinite(clean) or dirty > clean + 0.5)
    _rb("S0 누수민감도", "오염본 Sharpe − 실제 Sharpe",
        float(dirty - clean) if np.isfinite(dirty) and np.isfinite(clean) else np.nan,
        "PASS" if ok else "FAIL",
        "오염본이 압도적으로 좋아야 정상. 아니면 하네스가 둔감한 것이므로 "
        "아래 모든 결과를 신뢰할 수 없다.")


# ── S1. 증분 기여 (§38, §47) ─────────────────────────────────────────────────────────────
def S1_incremental(sig: pd.DataFrame, ppy: float):
    """§47 의 세 질문에 직접 답한다. 유리하게 해석하지 않는다."""
    series = {}
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol in sig.columns:
            series[name] = _ls_series(sig, acol)
    pairs = [("SCG_0", "BASE_REV", "질문1  Smart Consensus 자체가 단순 리비전을 이기는가"),
             ("SCG_LS", "SCG_0", "질문2  Leadership 에 독립적 추가 알파가 있는가"),
             ("SCG_LSA", "SCG_LS", "질문3  Gap 변화속도에 추가 알파가 있는가")]
    rows = []
    for new, old, q in pairs:
        if new not in series or old not in series:
            rows.append([q, "—", "—", "—", "—", "판정불가(표본없음)"])
            continue
        a, b = series[new].align(series[old], join="inner")
        if len(a) < 6:
            rows.append([q, "—", "—", "—", "—", "판정불가(기간부족)"])
            continue
        sa, sb = scg_perf(a, ppy)["Sharpe"], scg_perf(b, ppy)["Sharpe"]
        diff = a - b
        sd = diff.std(ddof=1)
        t = float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd and sd > 0 else np.nan
        better = np.isfinite(sa) and np.isfinite(sb) and sa > sb
        verdict = ("YES" if better and np.isfinite(t) and abs(t) >= 1.64 else
                   ("약YES" if better else "NO"))
        rows.append([q, _fmt(sb, 2), _fmt(sa, 2), _fmt(sa - sb, 2), _fmt(t, 2), verdict])
        _rb("S1 증분기여", f"{new} vs {old}", float(sa - sb) if np.isfinite(sa - sb) else np.nan,
            verdict, q)
    LOG.table(rows, ["연구질문", "기준 Sharpe", "신규 Sharpe", "차이", "t(차이)", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="§38·§47 증분 기여 — NO 가 나오면 그 구성요소는 불필요한 복잡도입니다. "
                    "제거를 권고하는 것이 정직한 결론입니다")


# ── S2. 파라미터 민감도 (§41) ────────────────────────────────────────────────────────────
def S2_sensitivity(rebuild: Callable[[SCGConfig], Optional[pd.DataFrame]], ppy: float):
    """공식값 45/6/20 을 중심으로 한 칸씩 옮겨 본다. 최적값을 채택하지 않는다."""
    grid = [("Forecast half-life", "FORECAST_HALFLIFE_DAYS", [30.0, 45.0, 60.0]),
            ("Shrinkage K", "K_ACC", [4.0, 6.0, 10.0]),
            ("Leadership horizon", "LEAD_FORWARD_TRADING_DAYS", [10, 20, 40])]
    rows = []
    for label, field, vals in grid:
        for v in vals:
            kw = {field: v}
            if field == "K_ACC":
                kw["K_LEAD"] = v          # 두 수축계수는 같이 움직이는 것이 §42 의 의도
            try:
                s = rebuild(replace(SCG, **kw))
            except Exception as e:
                rows.append([label, str(v), "—", "—", "—", f"실패: {type(e).__name__}"])
                continue
            if s is None or s.empty:
                rows.append([label, str(v), "—", "—", "—", "표본없음"])
                continue
            ls = scg_perf(_ls_series(s, "alpha_ls"), ppy)
            ic = scg_ic(s, "alpha_ls", [20])
            rows.append([label, str(v), _fmt(ls["annualized_return"]), _fmt(ls["Sharpe"], 2),
                         _fmt(float(ic["mean_ic"].iloc[0]) if len(ic) else np.nan),
                         "★ 공식값" if v in (45.0, 6.0, 20) else ""])
    LOG.table(rows, ["파라미터", "값", "LS 연율", "LS Sharpe", "IC(20d)", "비고"],
              ["l", "r", "r", "r", "r", "l"],
              title="§41 민감도 — 공식 V1 은 45/6/20 고정입니다. 이 표에서 가장 좋은 조합을 "
                    "사후에 채택하지 않습니다(그것이 과적합의 정의입니다)")
    fin = [r for r in rows if r[3] not in ("—",)]
    if len(fin) >= 3:
        sh = [float(r[3]) for r in fin]
        _rb("S2 민감도", "Sharpe 범위(max-min)", float(max(sh) - min(sh)),
            "PASS" if (max(sh) - min(sh)) < 1.0 else "주의",
            "파라미터 한 칸에 Sharpe 가 크게 흔들리면 결론이 파라미터에 얹혀 있는 것")


# ── S3. 하위기간 / 연도별 (§47 질문4) ────────────────────────────────────────────────────
def S3_subperiod(sig: pd.DataFrame, ppy: float):
    rows = []
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        ls = _ls_series(sig, acol)
        if ls.empty:
            continue
        y = ls.groupby(pd.DatetimeIndex(ls.index).year).apply(lambda s: float((1 + s).prod() - 1))
        pos = float((y > 0).mean())
        #  최고 성과 연도 하나를 빼면 알파가 사라지는가
        drop1 = y.drop(y.idxmax()) if len(y) > 1 else y
        rows.append([name, f"{len(y)}", f"{100*y.mean():.1f}%", f"{100*pos:.0f}%",
                     f"{y.idxmax()} ({100*y.max():.0f}%)",
                     f"{100*drop1.mean():.1f}%",
                     "의존" if (y.mean() > 0 and drop1.mean() <= 0) else "분산"])
        _rb("S3 하위기간", f"{name} 양(+)연도 비율", pos,
            "PASS" if pos >= 0.6 else "주의", "특정 1~2년 의존 여부")
    LOG.table(rows, ["전략", "연수", "연평균", "양(+)연도", "최고연도", "최고연도 제외 평균", "판정"],
              ["l", "r", "r", "r", "l", "r", "c"],
              title="§47 질문4 — 고성과가 특정 1~2년에만 의존하는가 (LS 기준)")

    #  연도 × 전략 히트맵 표
    yr = {}
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol in sig.columns:
            ls = _ls_series(sig, acol)
            if len(ls):
                yr[name] = ls.groupby(pd.DatetimeIndex(ls.index).year).apply(
                    lambda s: float((1 + s).prod() - 1))
    if yr:
        Y = pd.DataFrame(yr)
        LOG.table([[str(i)] + [f"{100*Y.loc[i, c]:+.1f}%" if c in Y.columns and
                               np.isfinite(Y.loc[i, c]) else "—" for c in Y.columns]
                   for i in Y.index],
                  ["연도"] + list(Y.columns), ["c"] + ["r"] * len(Y.columns),
                  title="연도별 롱숏 수익률 — 네 전략 나란히 (§37 동일 유니버스·동일 리밸런스)")


# ── S4. 종목 집중도 ──────────────────────────────────────────────────────────────────────
def S4_concentration(sig: pd.DataFrame, ppy: float):
    """상위 소수 종목이 성과를 다 만들고 있는가. 그렇다면 재현성이 낮다."""
    d = sig.dropna(subset=["alpha_ls", "ret_next"]).copy()
    if d.empty:
        return
    top = d[d.groupby("signal_date", observed=True)["alpha_ls"].rank(pct=True, ascending=False) <= 0.10]
    if top.empty:
        return
    contrib = top.groupby("stock_id", observed=True)["ret_next"].sum().sort_values(ascending=False)
    tot = float(contrib.sum())
    if abs(tot) < 1e-12:
        return
    n5 = max(1, int(0.05 * len(contrib)))
    share = float(contrib.head(n5).sum() / tot)
    ex = d[~d["stock_id"].isin(contrib.head(n5).index)]
    base = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    exs = scg_perf(_ls_series(ex, "alpha_ls"), ppy)["Sharpe"] if len(ex) else np.nan
    LOG.table([["상위 5% 종목의 기여 비중", f"{100*share:.1f}%"],
               ["전체 Sharpe", _fmt(base, 2)],
               ["상위 5% 종목 제외 Sharpe", _fmt(exs, 2)],
               ["보유 고유종목 수", f"{contrib.shape[0]:,}"]],
              ["항목", "값"], ["l", "r"],
              title="종목 집중도 — 상위 5% 를 빼면 알파가 사라지는가 (우측꼬리 의존성)")
    _rb("S4 집중도", "상위5% 기여비중", share,
        "PASS" if share < 0.5 else "주의", "0.5 초과면 소수 종목 의존")


# ── S5. 레짐 ─────────────────────────────────────────────────────────────────────────────
def S5_regime(sig: pd.DataFrame, bench: Optional[pd.Series], ppy: float):
    if bench is None or not len(bench):
        LOG.info("벤치마크가 없어 레짐 분할을 건너뜁니다.")
        return
    rows = []
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        ls = _ls_series(sig, acol)
        a, b = ls.align(bench, join="inner")
        if len(a) < 8:
            continue
        up, dn = a[b > 0], a[b <= 0]
        rows.append([name, f"{len(up)}", f"{100*up.mean()*ppy:+.1f}%",
                     f"{len(dn)}", f"{100*dn.mean()*ppy:+.1f}%",
                     "양방향" if (up.mean() > 0 and dn.mean() > 0) else
                     ("상승장 편중" if up.mean() > 0 else "하락장 편중")])
    LOG.table(rows, ["전략", "상승 기간수", "상승장 연율", "하락 기간수", "하락장 연율", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="레짐 분할 — 한쪽 장에서만 작동하면 그것은 알파가 아니라 베타 노출입니다")


# ── S6. 플라시보 ─────────────────────────────────────────────────────────────────────────
def S6_placebo(sig: pd.DataFrame, ppy: float, n_iter: int = 500):
    """알파를 시점 안에서 무작위 섞어 귀무분포를 만든다. 실제 Sharpe 의 p-value."""
    d = sig.dropna(subset=["alpha_ls", "ret_next"])
    if d.empty:
        return
    real = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    dates, arrs = [], []
    for T, g in d.groupby("signal_date", observed=True, sort=True):
        if len(g) >= max(10, N_BUCKETS):
            dates.append(T)
            arrs.append(g["ret_next"].to_numpy("float64"))
    if len(arrs) < 8:
        return
    null = np.empty(n_iter)
    for it in range(n_iter):
        per = []
        for r in arrs:
            m = len(r)
            k = max(1, m // N_BUCKETS)
            p = RNG.permutation(m)
            per.append(float(r[p[-k:]].mean() - r[p[:k]].mean()))
        s = pd.Series(per)
        sd = s.std(ddof=1)
        null[it] = float(s.mean() * ppy / (sd * np.sqrt(ppy))) if sd and sd > 0 else 0.0
    p = float((null >= real).mean()) if np.isfinite(real) else np.nan
    LOG.table([["실제 LS Sharpe", _fmt(real, 2)],
               ["귀무분포 평균", _fmt(float(null.mean()), 2)],
               ["귀무분포 95분위", _fmt(float(np.quantile(null, 0.95)), 2)],
               ["p-value (단측)", _fmt(p, 3)],
               ["반복 횟수", f"{n_iter:,}"]],
              ["항목", "값"], ["l", "r"],
              title="플라시보 — 알파를 시점 내에서 섞었을 때의 귀무분포 대비 위치")
    _rb("S6 플라시보", "p-value", p, "PASS" if (np.isfinite(p) and p < 0.05) else "주의",
        "0.05 이상이면 무작위와 구분되지 않음")


# ── S7. 비용 민감도 / 용량 ───────────────────────────────────────────────────────────────
def S7_cost(sig: pd.DataFrame, ppy: float):
    rows = []
    for bps in (0.0, 15.0, 30.0, 60.0, 100.0):
        cells = [f"{bps:.0f}bp"]
        for name, acol in STRATEGY_ALPHA_COLS.items():
            if acol not in sig.columns:
                continue
            bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, bps)
            cells.append(_fmt(scg_perf(bt["long"], ppy)["Sharpe"], 2))
        rows.append(cells)
    names = [n for n, c in STRATEGY_ALPHA_COLS.items() if c in sig.columns]
    LOG.table(rows, ["편도 비용"] + names, ["l"] + ["r"] * len(names),
              title="거래비용 민감도 (롱온리 최상위 버킷 Sharpe) — 한국 소형주 왕복 60bp 가정이 기본")


def scg_report_robustness():
    if not SCG_ROBUST:
        return
    rows = [[r["test"], r["metric"], _fmt(r["value"]), r["verdict"], _trunc(r["note"], 46)]
            for r in SCG_ROBUST]
    LOG.table(rows, ["검사", "지표", "값", "판정", "설명"], ["l", "l", "r", "c", "l"],
              title="강건성 요약 — FAIL/주의 항목을 '파라미터를 바꿔 통과시키는' 것은 금지입니다")


def scg_run_robustness(sig: pd.DataFrame, bench: Optional[pd.Series],
                       rebuild: Optional[Callable[[SCGConfig], Optional[pd.DataFrame]]],
                       ppy: float, do_sensitivity: bool = True):
    SCG_ROBUST.clear()
    for fn, args, name in (
            (S0_leak_sensitivity, (sig, ppy), "S0 누수민감도"),
            (S1_incremental, (sig, ppy), "S1 증분기여"),
            (S3_subperiod, (sig, ppy), "S3 하위기간"),
            (S4_concentration, (sig, ppy), "S4 집중도"),
            (S5_regime, (sig, bench, ppy), "S5 레짐"),
            (S6_placebo, (sig, ppy), "S6 플라시보"),
            (S7_cost, (sig, ppy), "S7 비용")):
        try:
            fn(*args)
        except Exception as e:                       # 한 검사의 실패가 나머지를 죽이지 않게
            LOG.warn(f"{name} 실패: {type(e).__name__}: {e}")
            _rb(name, "—", np.nan, "ERROR", f"{type(e).__name__}: {e}")
    if do_sensitivity and rebuild is not None:
        try:
            S2_sensitivity(rebuild, ppy)
        except Exception as e:
            LOG.warn(f"S2 민감도 실패: {type(e).__name__}: {e}")
    scg_report_robustness()
