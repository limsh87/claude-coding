

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6-R  성과검증 · 강건성 · 해석표 · 산출물 (SPEC §10)                                      ║
# ║                                                                                          ║
# ║  결과 미화 금지 (SPEC §0.5): "유망하다" / "추가 튜닝하면" 같은 표현을 쓰지 않는다.           ║
# ║  성과가 나쁘면 나쁜 대로, §11 기준으로만 판정해 출력한다.                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

OUTPUTS: List[str] = []

_METRIC_ORDER = ["기간수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                 "승률", "기간평균수익", "t통계량(HAC)", "최장언더워터(기간)", "누적수익",
                 "평균종목수", "평균회전율", "평균비용"]
_PCT = {"CAGR", "연변동성", "MDD", "승률", "기간평균수익", "누적수익", "평균회전율", "평균비용"}


def _fmt_metric(k: str, v: Any) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if k in _PCT:
        return f"{v:+.2%}" if k not in ("승률", "연변동성", "평균회전율", "평균비용") else f"{v:.2%}"
    if k in ("기간수", "최장언더워터(기간)"):
        return f"{int(v):,}"
    if k == "평균종목수":
        return f"{v:.1f}"
    return f"{v:+.3f}"


def outdir() -> str:
    d = os.path.join(VAULT.ns["private"], "outputs")
    os.makedirs(d, exist_ok=True)
    return d


def write_text(name: str, text: str) -> str:
    p = os.path.join(outdir(), name)
    atomic_write_text(p, text)
    OUTPUTS.append(p)
    return p


def write_df(name: str, df: pd.DataFrame) -> Optional[str]:
    if df is None:
        return None
    p = os.path.join(outdir(), name)
    try:
        if name.endswith(".parquet"):
            atomic_write_parquet(df, p)
        else:
            df.to_csv(p, index=False, encoding="utf-8-sig")
        OUTPUTS.append(p)
        return p
    except Exception as e:                                    # noqa
        LOG.warn(f"산출물 저장 실패({type(e).__name__}): {name}")
        return None


def report_performance(bt: dict, bench: Dict[str, pd.Series], title: str = "") -> dict:
    """성과 검증표."""
    R = bt.get("returns", pd.DataFrame())
    ppy = bt.get("meta", {}).get("ppy", 12.0)
    if R is None or not len(R):
        LOG.warn(f"[{title or bt.get('label')}] 수익 계열이 비어 성과표를 만들 수 없습니다.")
        return {}
    st = perf_stats(R, ppy=ppy)
    LOG.banner(f"성과 검증 — {title or bt.get('label')}",
               f"{as_ts(R['date'].min()):%Y-%m-%d} ~ {as_ts(R['date'].max()):%Y-%m-%d} · "
               f"{len(R)}기간 · 연 {ppy:.0f}회 리밸런싱")
    LOG.table([[k, _fmt_metric(k, st.get(k))] for k in _METRIC_ORDER if k in st],
              ["지표", "값"], ["l", "r"])
    rows = benchmark_table(bt, bench, ppy)
    if rows:
        LOG.table(rows, ["벤치마크", "벤치 연수익", "전략 연수익", "초과(연)", "초과 t(HAC)",
                         "§11 +3%p"], ["l", "r", "r", "r", "r", "c"],
                  title="벤치마크 대비 — ★동일가중 유니버스가 진짜 비교 기준이다 "
                        "(시총가중 지수 대비 초과는 사이즈 팩터일 뿐)")
    # 연도별
    if len(R):
        y = R.copy()
        y["연도"] = as_ts_series(y["date"]).dt.year
        ag = y.groupby("연도").agg(기간수=("ret", "size"), 수익=("ret", lambda s: (1 + s).prod() - 1),
                                   승률=("ret", lambda s: (s > 0).mean()),
                                   평균종목=("n", "mean"), 회전율=("turnover", "mean"))
        LOG.table([[str(i), f"{int(r['기간수'])}", f"{r['수익']:+.2%}", f"{r['승률']:.0%}",
                    f"{r['평균종목']:.0f}", f"{r['회전율']:.1%}"] for i, r in ag.iterrows()],
                  ["연도", "기간수", "수익", "승률", "평균종목수", "회전율"],
                  ["c", "r", "r", "r", "r", "r"], title="연도별 성과")
    return st


def report_quantile_profile(P: pd.DataFrame, signal_col: str, title: str = ""):
    Q = quantile_profile(P, signal_col)
    if not len(Q):
        return
    ppy = 12.0
    LOG.table([[f"Q{int(r['분위'])}", f"{r['평균수익']:+.3%}", f"{r['표준편차']:.3%}",
                f"{int(r['기간수'])}"] for _, r in Q.iterrows()],
              ["분위", "기간평균 전향수익", "표준편차", "기간수"], ["c", "r", "r", "r"],
              title=f"분위별 프로파일 — {title} (단조성이 없으면 신호가 아니라 잡음이다)")
    lo, hi = Q["평균수익"].iloc[0], Q["평균수익"].iloc[-1]
    mono = bool(Q["평균수익"].is_monotonic_increasing)
    LOG.info(f"  Q1 {lo:+.3%} → Q5 {hi:+.3%} · 단조증가 {'예' if mono else '아니오'}")


def report_robustness(rob: dict, title: str = ""):
    """강건성 검사표 — 블록 부트스트랩 / PBO / DSR / 워크포워드."""
    LOG.banner(f"강건성 검사 — {title}", "SPEC §9 통계 검증 게이트")
    bs = rob.get("bootstrap", {})
    if bs.get("ok"):
        LOG.table([["블록 길이", f"{bs['block']} 기간"],
                   ["반복", f"{bs['n_boot']:,}회"],
                   ["CAGR 95% 신뢰구간", f"{bs['cagr_lo']:+.2%} ~ {bs['cagr_hi']:+.2%} "
                                          f"(중앙 {bs['cagr_med']:+.2%})"],
                   ["Sharpe 95% 신뢰구간", f"{bs['sharpe_lo']:+.2f} ~ {bs['sharpe_hi']:+.2f} "
                                            f"(중앙 {bs['sharpe_med']:+.2f})"],
                   ["P(CAGR ≤ 0)", f"{bs['p_cagr_le0']:.1%}"],
                   ["P(Sharpe ≤ 0)", f"{bs['p_sharpe_le0']:.1%}"]],
                  ["항목", "값"], ["l", "r"], title="① 블록 부트스트랩 (§9.1)")
    else:
        LOG.warn("① 블록 부트스트랩: 표본 부족으로 수행 불가")

    pb = rob.get("pbo", {})
    if pb.get("ok"):
        LOG.table([["구성 수", f"{pb['n_config']}"], ["블록 수 S", f"{pb.get('S','-')}"],
                   ["조합 수", f"{pb['n_combo']:,}"],
                   ["PBO", f"{pb['pbo']:.3f}"],
                   ["§11 기준", "✔ PBO < 0.5" if pb["pbo"] < 0.5 else "✘ PBO ≥ 0.5 → KILL"]],
                  ["항목", "값"], ["l", "r"], title="② PBO — CSCV (§9.2)")
    else:
        LOG.warn(f"② PBO: {pb.get('note', '수행 불가')}")

    ds = rob.get("dsr", {})
    if ds.get("ok"):
        LOG.table([["시도 횟수 (사전등록 구성 수)", f"{ds['n_trials']}"],
                   ["Sharpe (연율)", f"{ds['sr_annual']:+.3f}"],
                   ["기대 최대 Sharpe (기간단위)", f"{ds['sr0']:+.4f}"],
                   ["왜도 / 첨도", f"{ds['skew']:+.2f} / {ds['kurt']:.2f}"],
                   ["DSR", f"{ds['dsr']:.4f}"],
                   ["§11 기준 (DSR>0)", "✔" if ds["dsr"] > 0 else "✘"],
                   ["통용 기준 (DSR>0.95)", "✔" if ds["dsr"] > 0.95 else "✘ — 시도횟수 보정 후 유의하지 않음"]],
                  ["항목", "값"], ["l", "r"], title="③ Deflated Sharpe Ratio (§9.3)")
    else:
        LOG.warn("③ DSR: 표본 부족으로 수행 불가")

    wf = rob.get("wf", {})
    if wf.get("ok"):
        LOG.table([[f["검증구간"], f["선택 구성"], f"{f['학습 Sharpe']:+.2f}",
                    f"{f['검증 Sharpe']:+.2f}", f"{f['검증 수익']:+.2%}"] for f in wf["folds"]],
                  ["검증구간", "학습기 최고 구성", "학습 Sharpe", "검증 Sharpe", "검증 수익"],
                  ["l", "l", "r", "r", "r"], title="④ 워크포워드 5년 학습 / 1년 검증 (§9.4)")
        LOG.info(f"  OOS 종합: Sharpe {wf['oos_sharpe']:+.2f} · CAGR {wf['oos_cagr']:+.2%} · "
                 f"선택된 구성 종류 {wf['n_distinct']}개/{wf['n_fold']}폴드 "
                 f"({'구성 선택이 불안정하다' if wf['n_distinct'] > wf['n_fold']/2 else '구성 선택이 비교적 안정적이다'})")
    else:
        LOG.warn(f"④ 워크포워드: {wf.get('note', '수행 불가')}")


def report_cost_sensitivity(scen: Dict[str, dict], ppy: float) -> pd.DataFrame:
    rows = []
    for name, bt in scen.items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        st = perf_stats(R, ppy=ppy)
        rows.append([name, _fmt_metric("CAGR", st.get("CAGR")),
                     _fmt_metric("Sharpe", st.get("Sharpe")),
                     _fmt_metric("MDD", st.get("MDD")),
                     f"{st.get('평균비용', float('nan')):.3%}",
                     f"{st.get('평균회전율', float('nan')):.1%}"])
    if rows:
        LOG.table(rows, ["비용 시나리오", "CAGR", "Sharpe", "MDD", "기간평균 비용", "회전율"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="비용 민감도 (§7.1) — 0 / 기본 / 2배 보수")
    return pd.DataFrame(rows, columns=["시나리오", "CAGR", "Sharpe", "MDD", "평균비용", "회전율"])


def report_delist_sensitivity(rows: List[list]) -> None:
    if rows:
        LOG.table(rows, ["폐지 수익률 가정", "CAGR", "Sharpe", "MDD", "영향 종목수"],
                  ["l", "r", "r", "r", "r"],
                  title="상장폐지 처리 민감도 (§0.3) — -100% 일괄 적용은 과도한 가정이다")


def report_arm_comparison(arms: Dict[str, dict], ppy: float):
    """전체 유니버스 아암 vs 시총 하위 1000 아암 — 사용자 요청 비교표."""
    rows = []
    for name, bt in arms.items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        st = perf_stats(R, ppy=bt.get("meta", {}).get("ppy", ppy))
        rows.append([name, _fmt_metric("CAGR", st.get("CAGR")),
                     _fmt_metric("Sharpe", st.get("Sharpe")),
                     _fmt_metric("MDD", st.get("MDD")),
                     _fmt_metric("Calmar", st.get("Calmar")),
                     _fmt_metric("승률", st.get("승률")),
                     f"{st.get('평균종목수', float('nan')):.0f}",
                     _fmt_metric("t통계량(HAC)", st.get("t통계량(HAC)"))])
    if rows:
        LOG.table(rows, ["아암", "CAGR", "Sharpe", "MDD", "Calmar", "승률", "평균종목수", "t(HAC)"],
                  ["l", "r", "r", "r", "r", "r", "r", "r"],
                  title="★ 아암 비교 — 전체 유니버스 vs 시가총액 하위 1,000종목")
        LOG.info("H3(소형주에서 더 강하다)가 참이라면 하위1000 아암이 전체 아암보다 강해야 한다. "
                 "그렇지 않다면 메커니즘 주장과 배치된다.")


def report_interpretation(P: pd.DataFrame, signal_col: str, LM: LinkMatrices,
                          bt: dict, sec: pd.DataFrame, top_n: int = 8):
    """기타 해석표 — 신호가 실제로 무엇을 집고 있는지 종목 단위로 보여준다."""
    LOG.banner("해석표", "신호 구성 · 링크 구조 · 최근 시점 상위 종목")
    S = LM.summary()
    if len(S):
        LOG.table([["평균 활동 애널리스트", f"{S['n_analyst'].mean():.0f}"],
                   ["평균 연결보유 종목", f"{S['n_covered'].mean():.0f}"],
                   ["평균 링크쌍", f"{S['n_pair'].mean():,.0f}"],
                   ["종목당 연결 수 (중위)", f"{S['median_links'].median():.0f}"],
                   ["링크 룩백", f"{LINK_LOOKBACK_M}개월 (고정)"],
                   ["최소 연결 요건", f"{MIN_LINKS_REQUIRED}개 미만은 신호 결측"]],
                  ["링크 구조", "값"], ["l", "r"])
    if P is None or not len(P):
        return
    last = as_ts(P["date"].max())
    g = P[(P["date"] == last) & P[signal_col].notna()].copy()
    if not len(g):
        return
    nm = sec.set_index("code")["name"].to_dict() if "name" in sec.columns else {}
    g = g.nlargest(top_n, signal_col)
    LOG.table([[r["code"], _trunc(nm.get(r["code"], ""), 16), f"{r[signal_col]:+.4f}",
                f"{r.get('sacn_raw', float('nan')):+.4f}",
                f"{int(r.get('n_link_used', 0))}",
                f"{r.get('own_ret', float('nan')):+.2%}",
                f"{r.get('mktcap', float('nan'))/1e8:,.0f}억" if np.isfinite(r.get("mktcap", np.nan)) else "—",
                _trunc(str(r.get("sector", "")), 14)] for _, r in g.iterrows()],
              ["종목", "종목명", "최종신호", "원신호", "연결수", "자기수익(t-1)", "시총", "업종"],
              ["l", "l", "r", "r", "r", "r", "r", "l"],
              title=f"최근 리밸런싱({last:%Y-%m-%d}) 상위 {top_n}종목")
    H = bt.get("holdings", pd.DataFrame())
    if len(H) and "fwd_ret" in H.columns:
        con = (H.assign(c=H["weight"] * H["fwd_ret"].fillna(0))
               .groupby("code")["c"].sum().sort_values(ascending=False))
        tot = float(con.sum())
        LOG.table([[c, _trunc(nm.get(c, ""), 16), f"{v:+.3%}",
                    f"{100*v/tot:+.1f}%" if abs(tot) > 1e-12 else "—"]
                   for c, v in list(con.head(5).items()) + list(con.tail(5).items())],
                  ["종목", "종목명", "누적 기여", "총기여 대비"], ["l", "l", "r", "r"],
                  title="기여 상위·하위 5종목 (우측꼬리 의존도 점검)")
        top5 = con.head(max(1, int(len(con) * 0.05)))
        LOG.info(f"  상위 5% 종목({len(top5)}개) 기여 {float(top5.sum()):+.2%} / 총 {tot:+.2%} — "
                 f"제외 시 {tot - float(top5.sum()):+.2%}")


# ── 산출물 파일 (§10) ───────────────────────────────────────────────────────────────────────
def _md_table(df: pd.DataFrame, maxrow: int = 200) -> str:
    if df is None or not len(df):
        return "_(데이터 없음)_\n"
    d = df.head(maxrow)
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    body = "\n".join("| " + " | ".join(
        ("" if v is None else (f"{v:.4f}" if isinstance(v, float) and np.isfinite(v) else str(v)))
        for v in r) + " |" for r in d.itertuples(index=False))
    return "\n".join([head, sep, body]) + "\n"


def _fallback_banner() -> str:
    if PHASE0.get("unit") == "broker_sector_team":
        return ("> ## ⚠ 폴백 전환 고지\n"
                "> Phase 0 확보율이 40% 미만이어서 **링크 단위를 애널리스트에서 "
                "`broker × sector_team` 으로 격하**했습니다.\n"
                "> 이 문서의 모든 결과는 **폴백 구성의 결과**이며, 애널리스트 단위 결과가 아닙니다.\n"
                "> 교차업종 전용 버전이 주 버전(primary)입니다.\n\n")
    return ""


def write_phase0_md(ph: dict) -> str:
    t = ["# PHASE 0 — 데이터 실현가능성 게이트", "", f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M}",
         f"빌드: {BUILD_VERSION}", "", "## 판정", "",
         f"- **표본 확보율: {ph.get('rate', float('nan')):.1%}** (표본 {ph.get('n', 0):,}건)",
         f"- 전체 확보율: {ph.get('overall_rate', float('nan')):.1%}",
         f"- 게이트: ≥70% 정상 / 40~70% IPW 필수 / <40% 폴백",
         f"- **링크 단위: `{ph.get('unit')}`**", f"- 판정: {ph.get('verdict')}",
         f"- 경과: {ph.get('elapsed_min', 0):.1f}분 (타임박스 {PHASE0_TIMEBOX_MIN/60:.0f}시간)", ""]
    det = ph.get("detail", {}) or {}
    for key, title in (("by_source", "소스별 확보율"), ("by_year", "연도별 확보율")):
        d = det.get(key)
        if d is not None and len(d):
            t += [f"## {title}", "", _md_table(d), ""]
    t += ["## 확보 경로", "",
          "1. 한경컨센서스 리스트 '작성자' 컬럼 (신뢰도 0.98)",
          "2. 네이버 상세페이지 바이라인 — 기존 구현이 수집해 놓고 버리던 컬럼을 회수",
          "3. PDF 본문 헤더 정규식 (신뢰도 0.80)", "",
          "## 한계", "",
          "- 두 소스 모두 발간 **시각**을 제공하지 않는다 → 전 건을 장중 발간으로 간주하고 "
          "knowledge_date = 발간일 + 1영업일로 보수화했다.",
          "- `analyst_id = sha1(broker_id, name)` 이므로 이직 시 다른 식별자가 된다. "
          "이는 SPEC §4.2 의 요구와 일치한다(같은 하우스에서 동시에 본다는 사실이 링크의 핵심).", ""]
    return write_text("PHASE0_DATA_FEASIBILITY.md", "\n".join(t))


def write_hypothesis_md(F: pd.DataFrame, rob: dict) -> str:
    t = [_fallback_banner(), "# 가설 검정 보고서 (H1~H4)", "",
         f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M} · 빌드 {BUILD_VERSION}", "",
         "사전등록된 가설과 기각조건만으로 판정한다. 백테스트 결과를 본 뒤 기준을 바꾸지 않는다.", ""]
    _LBL = {True: "통과", False: "기각", None: "판정불가"}
    for k in ("H1", "H2", "H3", "H4"):
        h = HYP.get(k)
        if not h:
            continue
        mark = {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[h.get("final")]
        stat = f"{h['stat']:+.3f}" if np.isfinite(h.get("stat", np.nan)) else "—"
        pv = f"{h['p']:.4f}" if np.isfinite(h.get("p", np.nan)) else "—"
        t += [f"## {k}. {h['name']} — **{mark}**", "",
              f"- 사전등록 기준 판정: {_LBL[h.get('pass')]}",
              f"- 통계량: {stat} · p = {pv} · BH-FDR 유의: "
              f"{'예' if h.get('fdr_sig') else '아니오'}",
              f"- 상세: {h['detail']}", ""]
    t += ["## 다중검정 보정 (BH-FDR, q=0.10)", "", _md_table(F), ""]
    for key, title in (("bootstrap", "블록 부트스트랩"), ("pbo", "PBO (CSCV)"),
                       ("dsr", "Deflated Sharpe Ratio")):
        d = rob.get(key, {})
        if d:
            t += [f"## {title}", "", _md_table(pd.DataFrame([
                {"항목": k2, "값": (f"{v:.4f}" if isinstance(v, float) else str(v))}
                for k2, v in d.items() if not isinstance(v, (list, dict, pd.DataFrame))])), ""]
    return write_text("hypothesis_test_report.md", "\n".join(t))


def write_mechanism_md(T: pd.DataFrame, arms: Dict[str, dict], ppy: float) -> str:
    t = [_fallback_banner(), "# 메커니즘 검정 (H3 조건부 예측)", "",
         "제한된 주의와 느린 정보 전파가 메커니즘이라면, 소형주·저커버리지·고개인비중에서 "
         "효과가 **더 강해야** 한다. 반대로 나오면 알파가 아니라 데이터마이닝이다.", "",
         _md_table(T), "", "## 아암 비교 (전체 유니버스 vs 시총 하위 1,000)", ""]
    rows = []
    for name, bt in arms.items():
        R = bt.get("returns", pd.DataFrame())
        if len(R):
            st = perf_stats(R, ppy=bt.get("meta", {}).get("ppy", ppy))
            rows.append({"아암": name, "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe"),
                         "MDD": st.get("MDD"), "t(HAC)": st.get("t통계량(HAC)"),
                         "평균종목수": st.get("평균종목수")})
    t += [_md_table(pd.DataFrame(rows)), ""]
    return write_text("mechanism_tests.md", "\n".join(t))


def write_open_questions_md() -> str:
    t = ["# OPEN QUESTIONS — 판단 보류 항목", "",
         "SPEC §0: 애매한 지점은 임의 판단하지 않고 여기 기록한 뒤 가장 보수적인 선택을 한다.", ""]
    if not OPEN_QUESTIONS:
        t += ["_(이번 실행에서 기록된 항목 없음)_", ""]
    for q in OPEN_QUESTIONS:
        t += [f"## {q['id']} — {q['topic']}", "", f"- **문제**: {q['issue']}",
              f"- **선택**: {q['choice']}"]
        if q.get("impact"):
            t += [f"- **영향**: {q['impact']}"]
        t += [""]
    return write_text("OPEN_QUESTIONS.md", "\n".join(t))


def write_verdict_md(v: dict, arms: Dict[str, dict], ppy: float) -> str:
    t = [_fallback_banner(), f"# FINAL VERDICT — {v['verdict']}", "",
         f"{v['why']}", "", f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M} · 빌드 {BUILD_VERSION}",
         f"백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
         "## §11 판정 조건 (사전 확정, 사후 변경 없음)", ""]
    t += ["| 조건 | 충족 |", "| --- | --- |"]
    for n, ok in v["criteria"]:
        t += [f"| {n} | {'✔' if ok else '✘'} |"]
    def _num(key, fmt):
        x = v.get(key, float("nan"))
        return format(x, fmt) if isinstance(x, (int, float)) and np.isfinite(x) else "—"

    t += ["",
          f"- 동일가중 유니버스 대비 초과(연): {_num('excess_ew', '+.2%')}",
          f"- PBO: {_num('pbo', '.3f')}",
          f"- DSR: {_num('dsr', '.3f')}", "",
          "## 판정 규칙", "",
          "- **ACCEPT**: H1·H2·H3 전부 통과 + PBO<0.5 + DSR>0 + 동일가중 대비 연 +3%p 이상",
          "- **CONDITIONAL**: H1·H2 통과 + H3 실패 → 실전 배분 금지, 페이퍼 트레이딩만",
          "- **KILL**: H1 실패 · 또는 H2 실패(업종 모멘텀 재포장) · 또는 PBO ≥ 0.5", ""]
    return write_text("FINAL_VERDICT.md", "\n".join(t))
