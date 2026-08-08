

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단 카드 (§37~§40, §46~§47)                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _p(v: Any, nd: int = 2, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    try:
        return f"{100*float(v):+.{nd}f}%" if pct else f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


def scg_report_performance(res: Dict[str, Any], label: str = ""):
    """§37 — 네 전략 나란히. 동일 유니버스·동일 리밸런스."""
    P = res.get("performance")
    if P is None or P.empty:
        LOG.warn("성과표를 만들 표본이 없습니다.")
        return
    rows = []
    for _, r in P.iterrows():
        rows.append([r["strategy"], f"{int(r['n_signals']):,}", f"{int(r['n_unique_stocks']):,}",
                     _p(r["annualized_return"], 1, True), _p(r["CAGR"], 1, True),
                     _p(r["volatility"], 1, True), _p(r["Sharpe"]),
                     _p(r["MDD"], 1, True), _p(r["hit_rate"], 1, True),
                     _p(r["turnover"], 2), _p(r["average_holdings"], 0),
                     _p(r.get("excess_vs_bench"), 1, True)])
    LOG.table(rows, ["전략", "신호수", "고유종목", "연율", "CAGR", "변동성", "Sharpe",
                     "MDD", "적중률", "회전율", "평균보유", "벤치대비"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              title=f"§37 전략별 성과 — 최상위 버킷 롱온리 · 거래비용 {BT_COST_BPS:.0f}bp 반영"
                    + (f"  [{label}]" if label else ""))
    rows = [[r["strategy"], _p(r["LS_annual"], 1, True), _p(r["LS_Sharpe"])]
            for _, r in P.iterrows()]
    LOG.table(rows, ["전략", "롱숏 연율", "롱숏 Sharpe"], ["l", "r", "r"],
              title="롱숏(최상위−최하위) — 시장방향을 제거한 순수 신호력")


def scg_report_buckets(res: Dict[str, Any]):
    """§39 단조성 — D1~D10 이 계단으로 올라가는가."""
    per = res.get("per_strategy", {})
    if not per:
        return
    names = list(per)
    ref = per[names[0]]["bt"]["summary"]
    if ref is None or ref.empty:
        return
    buckets = list(ref["bucket"])
    rows = []
    for b in buckets:
        cells = [f"D{int(b)}"]
        for n in names:
            s = per[n]["bt"]["summary"]
            v = s.loc[s["bucket"] == b, "mean_ret"]
            cells.append(_p(float(v.iloc[0]) if len(v) else np.nan, 2, True))
        rows.append(cells)
    LOG.table(rows, ["버킷"] + names, ["c"] + ["r"] * len(names),
              title=f"§39 십분위 평균 기간수익률 (D{int(max(buckets))} = 알파 최상위) — "
                    f"계단이 우상향해야 신호에 정보가 있다는 뜻입니다")

    mono = res.get("monotonicity")
    if mono is not None and not mono.empty:
        rows = [[r["strategy"], f"{int(r['n_buckets'])}", _p(r["spearman"], 3),
                 _p(r["top_minus_bottom"], 2, True),
                 "✔ 단조" if (np.isfinite(r["spearman"]) and r["spearman"] >= 0.6) else
                 ("△ 약함" if (np.isfinite(r["spearman"]) and r["spearman"] > 0) else "✘ 없음")]
                for _, r in mono.iterrows()]
        LOG.table(rows, ["전략", "버킷수", "Spearman(버킷,수익)", "최상−최하", "판정"],
                  ["l", "r", "r", "r", "c"],
                  title="§39 단조성 — Spearman 이 높을수록 '점수가 높을수록 수익도 높다'가 성립")


def scg_report_ic(res: Dict[str, Any]):
    """§40 — 20/60/120 거래일 forward IC."""
    IC = res.get("ic")
    if IC is None or IC.empty:
        LOG.warn("IC 를 계산할 표본이 없습니다.")
        return
    rows = []
    for _, r in IC.iterrows():
        rows.append([r["strategy"], f"{int(r['horizon_td'])}d", f"{int(r['n_dates'])}",
                     _p(r["mean_ic"], 4), _p(r["median_ic"], 4), _p(r["ic_std"], 4),
                     _p(r["ic_ir"], 3), _p(r["positive_ic_ratio"], 2),
                     _p(r["t_stat"], 2)])
    LOG.table(rows, ["전략", "지평", "시점수", "평균IC", "중앙IC", "IC표준편차",
                     "IC_IR", "양(+)비율", "t"],
              ["l", "c", "r", "r", "r", "r", "r", "r", "r"],
              title="§40 Forward IC — 세 지평의 부호가 같아야 신호가 일관됩니다 (§47 질문6)")
    #  지평 간 부호 일관성
    for s, g in IC.groupby("strategy"):
        sg = np.sign(g["mean_ic"].to_numpy())
        if len(sg) >= 2 and not (np.all(sg >= 0) or np.all(sg <= 0)):
            LOG.warn(f"{s}: 지평별 IC 부호가 엇갈립니다 {dict(zip(g['horizon_td'], g['mean_ic'].round(4)))} "
                     f"— 단기 반전/장기 지속이 섞였을 수 있습니다. 그대로 보고합니다.")


def scg_report_interpretation(sig: pd.DataFrame, res: Dict[str, Any]):
    """§46 경제적 의미 + §47 연구질문에 대한 답을 한 화면에 모은다."""
    LOG.banner("해석표 — §46 경제적 의미 · §47 연구질문",
               "숫자를 유리하게 읽지 않는다. NO 는 NO 라고 쓴다.")
    ok = sig["status"].eq(STATUS_OK) if "status" in sig.columns else pd.Series(True, index=sig.index)
    d = sig[ok]
    if d.empty:
        LOG.warn("유효 신호가 없어 해석표를 만들 수 없습니다.")
        return

    pos_ls = float((d["scg_ls"] > 0).mean()) if "scg_ls" in d.columns else np.nan
    pos_ac = float((d["scg_accel_20d"] > 0).mean()) if "scg_accel_20d" in d.columns else np.nan
    corr = (float(d["scg_ls"].corr(d["base_revision_20d"], method="spearman"))
            if {"scg_ls", "base_revision_20d"} <= set(d.columns) else np.nan)
    corr0 = (float(d["scg_ls"].corr(d["scg0"], method="spearman"))
             if {"scg_ls", "scg0"} <= set(d.columns) else np.nan)
    LOG.table([
        ["SCG_LS > 0 인 관측 비중", _p(pos_ls, 1, True).replace("+", ""),
         "정보력 높은 애널리스트 집단이 일반 컨센서스보다 높은 전망을 낸 종목의 비중"],
        ["SCG_ACCEL > 0 비중", _p(pos_ac, 1, True).replace("+", ""),
         "그 격차가 최근 더 빠르게 벌어지는 종목의 비중"],
        ["corr(SCG_LS, BASE_REV)", _p(corr, 3),
         "낮을수록 단순 리비전과 다른 정보를 담고 있다는 뜻"],
        ["corr(SCG_LS, SCG_0)", _p(corr0, 3),
         "1.0 에 가까우면 Leadership 이 사실상 아무것도 바꾸지 않은 것"],
        ["평균 애널리스트 수", _p(float(d["analyst_count"].mean()), 1),
         "얇으면 컨센서스 자체가 노이즈"],
    ], ["지표", "값", "읽는 법"], ["l", "r", "l"],
        title="§46 — 전략이 노리는 현상: 정보발생 → 고정보력 analyst 선행 → Smart Consensus 선행 "
              "→ 일반 Consensus 지연 → 가격 반영")

    P = res.get("performance")
    if P is not None and not P.empty:
        g = P.set_index("strategy")
        def sh(n):
            return float(g.loc[n, "Sharpe"]) if n in g.index else np.nan
        q = [("질문1  SCG_0 > BASE_REV ?", sh("SCG_0"), sh("BASE_REV"),
              "Smart Consensus 자체가 의미 있는가"),
             ("질문2  SCG_LS > SCG_0 ?", sh("SCG_LS"), sh("SCG_0"),
              "Leadership 에 독립적 추가 알파가 있는가"),
             ("질문3  SCG_LSA > SCG_LS ?", sh("SCG_LSA"), sh("SCG_LS"),
              "Gap 변화속도에 추가 알파가 있는가")]
        rows = [[name, _p(b), _p(a), _p(a - b) if np.isfinite(a) and np.isfinite(b) else "—",
                 ("YES" if (np.isfinite(a) and np.isfinite(b) and a > b) else "NO"), why]
                for name, a, b, why in q]
        LOG.table(rows, ["연구질문", "기준", "신규", "차이", "답", "의미"],
                  ["l", "r", "r", "r", "c", "l"],
                  title="§47 연구질문 — 롱온리 Sharpe 기준. NO 면 그 구성요소는 제거를 권고합니다")
        no = [r[0].split()[0] for r in rows if r[4] == "NO"]
        if no:
            LOG.warn(f"{', '.join(no)} 이 NO 입니다. 명세 §38 에 따라 명확히 보고합니다: "
                     f"해당 구성요소는 이 표본에서 추가 알파를 보이지 않았습니다. "
                     f"파라미터를 바꿔 YES 로 만들지 마십시오 — 그것이 과적합입니다.")


def scg_diagnostic_card(sig: pd.DataFrame, res: Dict[str, Any], scores: pd.DataFrame,
                        metric: str, universe: str):
    """실행 한 번의 요약 카드 — 무엇을 봤고 무엇을 못 봤는지."""
    ok = sig["status"].eq(STATUS_OK) if "status" in sig.columns else pd.Series(True, index=sig.index)
    d = sig[ok]
    n_an = int(scores["analyst_id"].nunique()) if scores is not None and len(scores) else 0
    with_acc = int((scores.groupby("analyst_id")["acc_n"].max() > 0).sum()) \
        if scores is not None and len(scores) else 0
    with_lead = int((scores.groupby("analyst_id")["lead_n"].max() > 0).sum()) \
        if scores is not None and len(scores) else 0
    LOG.table([
        ["메트릭 트랙", metric], ["유니버스", universe],
        ["신호 시점", f"{d['signal_date'].nunique() if len(d) else 0}개"],
        ["유효 신호", f"{len(d):,}행"],
        ["고유 종목", f"{d['stock_id'].nunique() if len(d) else 0:,}"],
        ["회계기간 수", f"{d['fiscal_period'].nunique() if len(d) else 0}"],
        ["애널리스트", f"{n_an:,}명"],
        ["  ├ Accuracy 이력 보유", f"{with_acc:,}명 ({100*with_acc/max(n_an,1):.0f}%)"],
        ["  └ Leadership 이력 보유", f"{with_lead:,}명 ({100*with_lead/max(n_an,1):.0f}%)"],
        ["이력 없어 중립(0) 처리", f"{n_an-max(with_acc,with_lead):,}명 — 탈락 아님(§32)"],
    ], ["항목", "값"], ["l", "r"],
        title=f"진단 카드 — {metric} / {universe}")
