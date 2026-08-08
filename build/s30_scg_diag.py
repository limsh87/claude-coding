

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  진단 (§34) + 원장 연결 감사                                                              ║
# ║                                                                                          ║
# ║  사용자 요구: "보고서와 식별된 애널리스트가 제대로 연결되었는지, 다중소스 원장연결은        ║
# ║  확실한지 한눈에". 그래서 원장을 4단 사슬로 보고, 각 고리의 잔존율을 연도·소스별로 낸다:    ║
# ║      리포트  →  애널리스트  →  종목코드  →  EPS 추정치                                     ║
# ║  어느 고리에서 끊기는지 모르면 "데이터가 없다"와 "코드가 연결을 못 했다"를 구분할 수 없다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


def scg_analyst_count_distribution(sig: pd.DataFrame) -> pd.DataFrame:
    """§34.1 analyst_count_distribution — 시점별 커버리지 분포.

    이 표가 급락하는 구간이 있으면 그 구간의 성과는 신뢰할 수 없다.
    (표본이 얇아지면 십분위 자체가 노이즈가 된다)
    """
    if sig is None or sig.empty or "analyst_count" not in sig.columns:
        return pd.DataFrame(columns=["signal_date", "count", "mean", "median",
                                     "p10", "p25", "p75", "p90"])
    d = sig[sig["status"].eq(STATUS_OK)] if "status" in sig.columns else sig
    g = d.groupby("signal_date", observed=True)["analyst_count"]
    D = pd.DataFrame({
        "count": g.size(), "mean": g.mean(), "median": g.median(),
        "p10": g.quantile(0.10), "p25": g.quantile(0.25),
        "p75": g.quantile(0.75), "p90": g.quantile(0.90),
    }).reset_index()
    return D


def scg_shrinkage_diagnostics(scores: pd.DataFrame) -> pd.DataFrame:
    """§34.2 shrinkage_diagnostics — 표본이 적은 애널리스트가 과대평가되지 않는지.

    ★ 읽는 법: acc_n 이 작은데 acc_star 가 크면 수축이 작동하지 않은 것이다.
      λ = n/(n+6) 이므로 n=1 이면 λ=0.14, n=6 이면 0.50, n=30 이면 0.83 이어야 한다.
      아래 표의 '이론 λ' 와 '실측 λ' 가 어긋나면 계산이 틀린 것이다.
    """
    cols = ["analyst_id", "acc_n", "lead_n", "acc_raw", "acc_star",
            "lead_raw", "lead_star", "quality_score_ls"]
    if scores is None or scores.empty:
        return pd.DataFrame(columns=cols)
    #  마지막 signal date 의 단면 = 가장 많은 이력이 쌓인 시점
    last = scores["signal_date"].max()
    S = scores[scores["signal_date"].eq(last)].copy()
    return S[[c for c in cols if c in S.columns]].sort_values(
        "acc_n", ascending=False).reset_index(drop=True)


def scg_report_shrinkage(scores: pd.DataFrame, cfg: SCGConfig = SCG):
    """수축이 실제로 작동했는지 n 구간별로 검증해 표로 낸다."""
    if scores is None or scores.empty:
        LOG.warn("애널리스트 점수가 비어 수축 진단을 건너뜁니다.")
        return
    last = scores["signal_date"].max()
    S = scores[scores["signal_date"].eq(last)]
    bins = [(0, 0), (1, 2), (3, 5), (6, 9), (10, 19), (20, 49), (50, 10 ** 9)]
    rows = []
    for lo, hi in bins:
        g = S[(S["acc_n"] >= lo) & (S["acc_n"] <= hi)]
        if not len(g):
            continue
        n_mid = float(g["acc_n"].mean())
        rows.append([f"{lo}~{hi if hi < 10**9 else '∞'}", f"{len(g):,}",
                     f"{n_mid:.1f}", f"{n_mid/(n_mid+cfg.K_ACC):.3f}",
                     f"{g['acc_lambda'].mean():.3f}",
                     f"{g['acc_raw'].mean():+.3f}", f"{g['acc_star'].mean():+.3f}",
                     f"{g['acc_star'].abs().max():.3f}"])
    LOG.table(rows, ["acc_n 구간", "애널 수", "평균 n", "이론 λ", "실측 λ",
                     "ACC_raw 평균", "ACC* 평균", "|ACC*| 최대"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title=f"§34.2 수축 진단 ({pd.Timestamp(last).date()} 단면) — "
                    f"이론 λ 와 실측 λ 가 일치해야 하고, n 이 작을수록 ACC* 가 0 에 붙어야 합니다")
    z = S[S["acc_n"].eq(0) & S["lead_n"].eq(0)]
    if len(z):
        LOG.info(f"이력이 전혀 없는 애널리스트 {len(z):,}명 — 전원 유지되며 Q=0, multiplier=1.0 "
                 f"입니다(§32). 탈락시키지 않는 것이 이 전략의 설계입니다.")


def scg_weight_concentration(weights: pd.DataFrame) -> pd.DataFrame:
    """§34.3 weight_concentration — 한 명이 Smart Consensus 를 좌우하고 있지 않은가.

    Effective N = 1 / Σ p_j²   (p_j = w_j / Σw)
    ★ 진단용이지 하드게이트가 아니다(§34.3). 값이 나쁘다고 종목을 빼지 않는다.
    """
    cols = ["signal_date", "stock_id", "fiscal_period", "forecast_metric",
            "max_weight_share", "top2_weight_share", "effective_analyst_n", "n_analysts"]
    if weights is None or weights.empty:
        return pd.DataFrame(columns=cols)
    W = weights[["signal_date"] + GROUP_KEY + ["weight_ls"]].copy()
    tot = W.groupby(["signal_date"] + GROUP_KEY, observed=True)["weight_ls"].transform("sum")
    W["p"] = W["weight_ls"] / tot.where(tot > 0)
    W["p2"] = W["p"] ** 2
    g = W.groupby(["signal_date"] + GROUP_KEY, observed=True)
    D = g.agg(max_weight_share=("p", "max"), _sp2=("p2", "sum"),
              n_analysts=("p", "size")).reset_index()
    top2 = (W.sort_values("p", ascending=False)
             .groupby(["signal_date"] + GROUP_KEY, observed=True)["p"]
             .apply(lambda s: float(s.head(2).sum())).rename("top2_weight_share").reset_index())
    D = D.merge(top2, on=["signal_date"] + GROUP_KEY, how="left")
    D["effective_analyst_n"] = 1.0 / D["_sp2"].where(D["_sp2"] > 0)
    return D[cols]


def scg_report_weight_concentration(conc: pd.DataFrame):
    if conc is None or conc.empty:
        return
    q = conc[["max_weight_share", "top2_weight_share", "effective_analyst_n", "n_analysts"]]
    rows = [[k, f"{q[k].mean():.3f}", f"{q[k].quantile(.5):.3f}",
             f"{q[k].quantile(.9):.3f}", f"{q[k].max():.3f}"] for k in q.columns]
    LOG.table(rows, ["지표", "평균", "중앙", "p90", "최대"], ["l", "r", "r", "r", "r"],
              title="§34.3 가중치 집중도 — Effective N 이 실제 애널리스트 수에 가까울수록 "
                    "'한 명이 컨센서스를 좌우'하지 않는다는 뜻 (진단용 · 게이트 아님)")
    #  가중치 상한이 2.0/0.5 = 4배로 묶여 있으므로 집중도는 구조적으로 제한된다.
    bad = conc[conc["max_weight_share"] > 0.8]
    if len(bad):
        LOG.info(f"한 애널리스트가 80% 초과 비중을 갖는 (종목·시점) {len(bad):,}건 — "
                 f"대부분 애널리스트가 2명뿐인 종목입니다(구조적, 가중치 문제 아님).")


def scg_audit_forecast_ledger(reports: pd.DataFrame, links: pd.DataFrame,
                              forecasts: pd.DataFrame, actuals: pd.DataFrame):
    """★ 원장 4단 사슬 감사 — 리포트 → 애널리스트 → 종목 → EPS 추정치.

    어느 고리가 끊겼는지 연도별로 드러낸다. "EPS 커버리지가 낮다"는 결론을 내리기 전에
    그게 (a) 리포트를 못 받은 건지 (b) 애널을 못 붙인 건지 (c) 종목코드가 없는 건지
    (d) PDF 에서 숫자를 못 뽑은 건지 반드시 구분되어야 한다.
    """
    LOG.banner("원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목 ↔ EPS 추정치",
               "연결이 끊긴 고리를 연도별로 노출한다. 숫자가 낮으면 낮은 대로 보고한다.")
    if reports is None or reports.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다. "
                 "드라이브 캐시(research_report_master)와 RESEARCH_COLLECT 를 확인하세요.")
        return

    r = reports.copy()
    r["year"] = as_ts_series(r["pub_date"]).dt.year
    linked = set(links["report_uid"].astype(str)) if links is not None and len(links) else set()
    with_eps = set()
    if forecasts is not None and len(forecasts) and "report_id" in forecasts.columns:
        e = forecasts[forecasts["forecast_metric"].astype(str).eq("EPS")]
        with_eps = set(e["report_id"].astype(str))
    with_tp = set()
    if forecasts is not None and len(forecasts) and "report_id" in forecasts.columns:
        t = forecasts[forecasts["forecast_metric"].astype(str).eq("TP")]
        with_tp = set(t["report_id"].astype(str))

    ruid = r["report_uid"].astype(str)
    r["c_analyst"] = ruid.isin(linked)
    r["c_code"] = r["stock_code"].notna()
    r["c_eps"] = ruid.isin(with_eps)
    r["c_tp"] = ruid.isin(with_tp)
    r["c_chain"] = r["c_analyst"] & r["c_code"] & r["c_eps"]

    rows = []
    for y, g in r.groupby("year", observed=True):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{100*g['c_analyst'].mean():.1f}%", f"{100*g['c_code'].mean():.1f}%",
                     f"{100*g['c_tp'].mean():.1f}%", f"{100*g['c_eps'].mean():.1f}%",
                     f"{int(g['c_chain'].sum()):,}", f"{100*g['c_chain'].mean():.1f}%"])
    LOG.table(rows, ["연도", "리포트", "①애널연결", "②종목코드", "③목표주가", "④EPS추정",
                     "4단 완결", "완결률"],
              ["c", "r", "r", "r", "r", "r", "r", "r"],
              title="원장 4단 사슬 잔존율 — ④가 낮고 ①②③이 높으면 'PDF에서 숫자를 못 뽑은 것' 입니다")

    if "source" in r.columns:
        s = r.groupby("source", observed=True).agg(
            n=("report_uid", "size"), a=("c_analyst", "mean"), c=("c_code", "mean"),
            tp=("c_tp", "mean"), e=("c_eps", "mean")).reset_index()
        LOG.table([[x["source"], f"{int(x['n']):,}", f"{100*x['a']:.1f}%", f"{100*x['c']:.1f}%",
                    f"{100*x['tp']:.1f}%", f"{100*x['e']:.1f}%"] for _, x in s.iterrows()],
                  ["소스 조합", "건수", "애널연결률", "종목코드율", "목표주가율", "EPS추정율"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="다중소스 원장연결 — 'hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건. "
                        "한경은 작성자를, 네이버는 종목코드를 채운다(둘을 합쳐야 원장이 완성됨)")

    if forecasts is not None and len(forecasts):
        f = forecasts.copy()
        f["year"] = as_ts_series(f["report_date"]).dt.year
        rows = []
        for (mt, y), g in f.groupby(["forecast_metric", "year"], observed=True):
            rows.append([str(mt), int(y), f"{len(g):,}", f"{g['analyst_id'].nunique():,}",
                         f"{g['stock_id'].nunique():,}", f"{g['fiscal_period'].nunique()}"])
        LOG.table(rows[:60], ["메트릭", "연도", "전망 건수", "애널리스트", "종목", "회계기간"],
                  ["l", "c", "r", "r", "r", "r"],
                  title="analyst_forecasts 적재 현황 (§2.1 표준 스키마)")

    if actuals is not None and len(actuals):
        a = actuals.copy()
        a["year"] = as_ts_series(a["actual_announcement_date"]).dt.year
        cov = (a.groupby(["forecast_metric", "year"], observed=True)
                .agg(n=("actual_value", "size"), stocks=("stock_id", "nunique")).reset_index())
        LOG.table([[str(x["forecast_metric"]), int(x["year"]), f"{int(x['n']):,}",
                    f"{int(x['stocks']):,}"] for _, x in cov.iterrows()][:40],
                  ["메트릭", "발표연도", "실적 건수", "종목"], ["l", "c", "r", "r"],
                  title="실적 실측치(Accuracy 의 A) 적재 현황 — 없으면 ACC* 는 전부 0 으로 수축됩니다")
    else:
        LOG.warn("실적 실측치가 없습니다 → ACC* 전원 0. 애널리스트는 탈락하지 않지만 "
                 "SCG_0 는 사실상 'Recency 가중 컨센서스 갭'이 됩니다. DART_API_KEY 를 확인하세요.")


def scg_report_universe_attrition(stages: Sequence[Tuple[str, int, str]]):
    """유니버스 감쇠 감사 — 어느 게이트에서 표본이 줄었는지 (§35 TEST 9 의 근거표).

    stages: [(단계명, 종목수, 설명), ...]
    """
    if not stages:
        return
    base = max(1, stages[0][1])
    prev = stages[0][1]
    rows = []
    for name, n, why in stages:
        rows.append([name, f"{n:,}", f"{100*n/base:.1f}%",
                     f"{n-prev:+,}" if n != prev else "—", why])
        prev = n
    LOG.table(rows, ["단계", "종목수", "잔존율", "증감", "근거"],
              ["l", "r", "r", "r", "l"],
              title="유니버스 감쇠 — §31 이 금지한 하드게이트가 몰래 들어오면 여기서 표본이 꺾입니다")
