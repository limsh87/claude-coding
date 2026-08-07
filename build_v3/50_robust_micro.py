

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 (§11)                                                                         ║
# ║                                                                                          ║
# ║   R0   자체 측정 벤치마크 대비 ⭐   — 하드코딩된 기준선을 쓰지 않는다(원칙 5)              ║
# ║   R2-M 거부권 알파 가설 검정 ⭐⭐   — 이 전략의 존재 이유. A/B/C/D 4방 비교                ║
# ║   R3   퀄리티 팩터 직교화           — 알파가 남는가, 아니면 재포장인가                     ║
# ║   R5-M 절제 (조항·TP·거부권)        — 어느 부품이 실제로 일하는가                          ║
# ║   R9   회전율·비용 시나리오         — 비관 시나리오에서도 남는가                           ║
# ║                                                                                          ║
# ║  ★ 유리하게 해석하지 않는다. A 가 벤치마크와 거의 같게 나오면 그대로 보고한다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: List[dict] = []
_KILL_ARMED = True     # 합성 스모크 구간에서만 False. 실데이터에서는 항상 True.


def _rec(rid: str, name: str, passed: Optional[bool], detail: str, kill: bool = False):
    ROBUST.append({"id": rid, "name": name, "passed": passed, "detail": detail, "kill": kill})
    icon = "—" if passed is None else ("✔" if passed else "✘")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.error))(
        f"[{rid}] {icon} {name} — {detail}")
    if kill and passed is False and STOP_ON_KILL_CRITERIA and _KILL_ARMED:
        raise KillCriteria(f"[{rid}] {name}: {detail}")


def _calmar(bt: dict) -> float:
    v = (bt or {}).get("stats", {}).get("calmar", np.nan)
    return float(v) if v is not None and np.isfinite(v) else -np.inf


def _fmt(bt: dict) -> str:
    s = (bt or {}).get("stats", {})
    def g(k):
        v = s.get(k, np.nan)
        return v if v is not None and np.isfinite(v) else np.nan
    return (f"CAGR {100*g('cagr'):.1f}% · MDD {100*g('mdd'):.1f}% · "
            f"Calmar {g('calmar'):.2f} · Sharpe {g('sharpe'):.2f}")


# ── R0 ──────────────────────────────────────────────────────────────────────────────────────
def R0_benchmark(bts: Dict[str, dict], bench_ew: dict, bench_idx: Dict[str, dict]):
    """MICRO-FW(D)가 (a) 유니버스 동일가중, (b) 방화벽 단독(A) 을 Calmar 로 상회하는가."""
    d, a = bts.get("D"), bts.get("A")
    c_d, c_a, c_b = _calmar(d), _calmar(a), _calmar(bench_ew)
    rows = [["MICRO-FW (D)", _fmt(d)], ["방화벽 단독 (A)", _fmt(a)],
            ["유니버스 동일가중", _fmt(bench_ew)]]
    for k, v in (bench_idx or {}).items():
        rows.append([f"참고: {k} 지수", _fmt(v)])
    LOG.table(rows, ["구성", "성과"], ["l", "l"],
              title="R0 — 자체 측정 벤치마크 (수치를 인용하지 않고 같은 데이터로 직접 잰다)")

    ok_a = c_d > c_b
    _rec("R0a", "유니버스 동일가중 대비 (Calmar)", bool(ok_a),
         f"D {c_d:.2f} vs 동일가중 {c_b:.2f} — "
         f"{'상회' if ok_a else '미달. 유니버스 자체의 수익을 재현한 것에 불과합니다'}")
    ok_b = c_d > c_a
    _rec("R0b", "방화벽 단독(A) 대비 (Calmar) ⭐", bool(ok_b),
         f"D {c_d:.2f} vs A {c_a:.2f} — "
         f"{'증거층이 방화벽 위에 값을 더합니다' if ok_b else '증거층이 방화벽에 아무것도 더하지 못합니다(§12-3 폐기 기준)'}",
         kill=True)


# ── R2-M : 4방 비교 (이 전략의 존재 이유) ───────────────────────────────────────────────────
def R2M_fourway(bts: Dict[str, dict], bench_ew: dict) -> str:
    c = {k: _calmar(v) for k, v in bts.items()}
    cb = _calmar(bench_ew)
    rows = [[k, VARIANTS[k]["desc"], _fmt(bts.get(k)), f"{c.get(k, float('nan')):.2f}"]
            for k in ("A", "B", "C", "D") if k in bts]
    rows.append(["–", "유니버스 동일가중 (기준선)", _fmt(bench_ew), f"{cb:.2f}"])
    LOG.table(rows, ["구성", "정의", "성과", "Calmar"], ["c", "l", "l", "r"],
              title="R2-M — 4방 비교 (§11.1). 방화벽이 알파인가, 손실회피인가")
    LOG.info(f"비교 조건: A~D 는 포트폴리오 구성(상위 {100*PORTFOLIO_TOP_PCT:.0f}%·최대 "
             f"{PORTFOLIO_MAX_NAMES}종목·동일 사이징·동일 비용)이 전부 같고, 다른 것은 "
             f"'무엇으로 순위를 매기는가' 하나뿐입니다. 종목 수를 다르게 두면 분산효과와 "
             f"신호효과가 섞여 비교 자체가 무의미해지기 때문입니다.")
    LOG.info("단, A(방화벽만)는 통과/탈락이 이진값이라 순위를 매길 것이 없어 "
             "거래대금 순으로 동점을 가릅니다 — 즉 A 에는 유동성 틸트가 들어 있습니다. "
             "A 가 동일가중을 이긴다면 그 일부는 유동성 효과일 수 있다는 뜻이며, "
             "R0a(전체 유니버스 동일가중 대비)가 그 판정의 기준선입니다.")

    verdicts = []
    # ① 방화벽 자체가 알파인가
    gap = c.get("A", -np.inf) - cb
    if gap > 0.15:
        v1 = ("방화벽 자체가 알파입니다. A 가 유니버스 동일가중을 뚜렷하게 상회합니다 "
              f"(Calmar {c.get('A', float('nan')):.2f} vs {cb:.2f}). 가설 지지.")
    elif gap > -0.15:
        v1 = ("★방화벽은 알파가 아니라 손실회피입니다. A 가 유니버스 동일가중과 사실상 같습니다 "
              f"(Calmar {c.get('A', float('nan')):.2f} vs {cb:.2f}). 문서가 예고한 결과이며 "
              "유리하게 해석하지 않고 그대로 보고합니다.")
    else:
        v1 = (f"방화벽이 오히려 해롭습니다 (A {c.get('A', float('nan')):.2f} < 동일가중 {cb:.2f}). "
              "하드필터가 수익 원천을 함께 잘라내고 있습니다.")
    verdicts.append(v1)

    # ② 결합의 근거가 있는가
    best_ab = max(c.get("A", -np.inf), c.get("B", -np.inf))
    if c.get("C", -np.inf) <= best_ab:
        v2 = (f"★C({c.get('C', float('nan')):.2f}) ≤ max(A,B)({best_ab:.2f}) — 결합 근거가 소멸했습니다. "
              f"§12-4 에 따라 더 단순한 쪽"
              f"({'A(방화벽만)' if c.get('A', -np.inf) >= c.get('B', -np.inf) else 'B(증거층만)'})"
              f"을 채택해야 합니다.")
        _rec("R2M-C", "결합 근거 (C > max(A,B)) ⭐", False, v2, kill=True)
    else:
        v2 = f"C({c.get('C', float('nan')):.2f}) > max(A,B)({best_ab:.2f}) — 방화벽과 증거층의 결합에 근거가 있습니다."
        _rec("R2M-C", "결합 근거 (C > max(A,B)) ⭐", True, v2)
    verdicts.append(v2)

    # ③ U 층이 기여하는가
    if c.get("D", -np.inf) <= c.get("C", -np.inf):
        v3 = (f"D({c.get('D', float('nan')):.2f}) ≤ C({c.get('C', float('nan')):.2f}) — U층(가격 모멘텀)이 "
              f"기여하지 않습니다. d1 을 빼고 C 를 최종안으로 삼는 것이 정직합니다.")
        _rec("R2M-D", "U층 기여 (D > C)", False, v3)
    else:
        v3 = f"D({c.get('D', float('nan')):.2f}) > C({c.get('C', float('nan')):.2f}) — U층이 기여합니다."
        _rec("R2M-D", "U층 기여 (D > C)", True, v3)
    verdicts.append(v3)

    LOG.banner("R2-M 판정", "방화벽 알파 가설")
    for i, v in enumerate(verdicts, 1):
        _safe_print(f"  {i}. {v}")
    return "\n".join(f"{i}. {v}" for i, v in enumerate(verdicts, 1))


# ── R3 : 퀄리티 팩터 직교화 ─────────────────────────────────────────────────────────────────
def _factor_returns(P: pd.DataFrame, name: str, colname: str, high_is_long: bool = True
                    ) -> pd.Series:
    """같은 유니버스에서 만든 롱-숏 팩터 월수익률(상위 30% − 하위 30%, 동일가중)."""
    sub = P[P["fwd_ret"].notna() & col(P, colname).notna()]
    if len(sub) < 100:
        return pd.Series(dtype="float64")
    r = sub.groupby("month", observed=True)[colname].rank(pct=True)
    hi = sub[r >= 0.70].groupby("month", observed=True)["fwd_ret"].mean()
    lo = sub[r <= 0.30].groupby("month", observed=True)["fwd_ret"].mean()
    f = (hi - lo) if high_is_long else (lo - hi)
    return f.dropna().rename(name)


def R3_orthogonal(P: pd.DataFrame, bt: dict, bench_ew: Optional[dict] = None):
    """전략 수익률을 퀄리티/밸류/모멘텀 팩터에 회귀해 알파가 남는지 본다.

    남지 않으면 이 전략은 '기존 팩터의 재포장'이다. statsmodels 없이 최소제곱 + HAC t 로 푼다.
    """
    R = (bt or {}).get("returns")
    if R is None or len(R) < 24:
        _rec("R3", "퀄리티 팩터 직교화", None, "표본이 24개월 미만이라 검정하지 않습니다.")
        return
    P = P.copy()
    P["_roa"] = safe_div(col(P, "net_income_ttm"), col(P, "assets").where(col(P, "assets") > 0))
    P["_accq"] = col(P, "i_accr")
    P["_val"] = col(P, "bp")                         # 순자산수익률(B/P) 롱 = 저PBR 롱
    if P["_val"].notna().sum() == 0:
        P["_val"] = -col(P, "pbr")                   # 폴백(구버전 패널 호환)
    facs = [_factor_returns(P, "QMJ_ROA", "_roa"), _factor_returns(P, "ACCR", "_accq"),
            _factor_returns(P, "VALUE", "_val"), _factor_returns(P, "MOM", "d1_trailing")]
    # ★ 유니버스(시장) 팩터를 반드시 넣는다.
    #   위 팩터들은 전부 롱-숏(상위30%−하위30%)이라 구조적으로 시장중립이다. 전략 수익률은
    #   롱온리인데 회귀식에 시장 요인이 없으면, U-MICRO 유니버스 자체의 수익(베타)이 전부
    #   절편으로 들어간다. 그러면 '알파가 남았다'는 판정이 사실은 '소형주에 노출됐다'는
    #   뜻이 되어, R0(동일가중 대비)와 정면으로 모순되는 결론이 나온다.
    if bench_ew is not None and len(bench_ew.get("returns", [])):
        bm = bench_ew["returns"].set_index("month")["ret"].rename("UNIVERSE")
        if len(bm) >= 24:
            facs.append(bm)
    facs = [f for f in facs if len(f) >= 24]
    if not facs:
        _rec("R3", "퀄리티 팩터 직교화", None, "팩터를 구성할 표본이 부족합니다.")
        return
    F = pd.concat(facs, axis=1)
    y = R.set_index("month")["ret"]
    J = F.join(y, how="inner").dropna()
    if len(J) < 24:
        _rec("R3", "퀄리티 팩터 직교화", None, f"교집합 표본 {len(J)}개월로 부족합니다.")
        return
    X = np.column_stack([np.ones(len(J))] + [J[c].to_numpy() for c in F.columns])
    yy = J["ret"].to_numpy()
    try:
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        resid = yy - X @ beta
    except Exception as e:                                             # noqa
        _rec("R3", "퀄리티 팩터 직교화", None, f"회귀 실패({type(e).__name__})")
        return
    alpha_m = float(beta[0])
    t, p = hac_tstat(resid + alpha_m)
    ann = (1 + alpha_m) ** 12 - 1
    rows = [["절편(월 알파)", f"{100*alpha_m:.3f}%", f"연 {100*ann:.2f}%", f"t={t:.2f} p={p:.3f}"]]
    for i, c in enumerate(F.columns):
        rows.append([f"β({c})", f"{beta[i+1]:.3f}", "", ""])
    LOG.table(rows, ["항", "계수", "연율", "유의성"], ["l", "r", "r", "l"],
              title="R3 — 퀄리티/밸류/모멘텀 직교화 후 잔존 알파")
    ok = (ann > 0) and (abs(t) > 1.64)
    has_uni = "UNIVERSE" in list(F.columns)
    _rec("R3", "퀄리티·밸류·모멘텀·유니버스 직교화", bool(ok),
         f"직교화 후 연 알파 {100*ann:.2f}% (t={t:.2f}) · 유니버스 팩터 "
         f"{'포함' if has_uni else '미포함(주의: 소형주 베타가 절편에 섞임)'} — "
         f"{'알파 잔존' if ok else '유의한 알파가 남지 않습니다. 기존 팩터의 재포장일 수 있습니다'}")


# ── R5-M : 절제 ─────────────────────────────────────────────────────────────────────────────
def R5M_ablation(P: pd.DataFrame, months, uni, active: Dict[str, bool], base_bt: dict):
    """조항·TP·거부권을 하나씩 빼 보고 Calmar 변화를 본다. 변화가 없으면 그 부품은 장식이다."""
    base = _calmar(base_bt)
    rows = []

    def run_with(mod: pd.DataFrame, tag: str) -> float:
        try:
            S = assemble_signal(mod, "D")
            bt = run_backtest_micro(S, months, uni, "D", COST_BASE_SCENARIO,
                                    label=f"ABL:{tag}", quiet=True)
            v = (bt or {}).get("stats", {}).get("calmar", np.nan)
            return float(v) if v is not None and np.isfinite(v) else float("nan")
        except Exception as e:                                         # noqa
            LOG.warn(f"절제 검사 '{tag}' 실행 실패({type(e).__name__}) — 판정불가로 처리합니다.")
            return float("nan")

    def verdict(c: float) -> str:
        # ★ NaN 을 '해로움'으로 분류하면 안 된다. 실행이 실패한 것과 부품이 해로운 것은
        #   완전히 다른 사건인데, `c < base-0.05` 와 `abs(c-base) <= 0.05` 가 둘 다
        #   False 가 되어 자동으로 '해로움'으로 떨어진다(원인과 정반대의 결론).
        if not np.isfinite(c):
            return "판정불가"
        if c < base - 0.05:
            return "기여"
        return "무기여" if abs(c - base) <= 0.05 else "해로움"

    for key, (name, _b, enabled, _n) in firewall_clause_masks(P, active).items():
        if not enabled:
            rows.append([f"방화벽·{name}", "비활성", "-", "원래 꺼져 있음"])
            continue
        m = P.copy()
        fw, _ = s1_firewall(m, active, skip=[key], quiet=True)
        m["FW"] = fw
        c = run_with(m, key)
        rows.append([f"방화벽·{name}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    for tid, a, b in TP_DEFS:
        if tid not in P.columns or col(P, tid).notna().sum() == 0:
            continue
        m = P.copy()
        m[tid] = np.nan
        others = [t for t, _, _ in TP_DEFS if t != tid]
        m["E_micro"] = nanmean_cols(m, others)
        c = run_with(m, tid)
        rows.append([f"증거층·{tid}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    for v in ("V1", "V2", "V3", "V6"):
        if v not in P.columns:
            continue
        m = P.copy()
        m[v] = 1.0
        m["VETO"] = m["V1"] * m["V2"] * m["V3"] * m["V6"]
        c = run_with(m, v)
        rows.append([f"거부권·{v}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    rows.append(["── 원본 (절제 없음)", f"{base:.2f}", "—", ""])
    LOG.table(rows, ["절제 대상", "Calmar", "변화", "판정"], ["l", "r", "r", "c"],
              title="R5-M — 절제 검사. '빼도 그대로'인 부품은 복잡도만 늘리는 장식이다")
    useful = sum(1 for r in rows[:-1] if r[3] == "기여")
    n_bad = sum(1 for r in rows[:-1] if r[3] == "판정불가")
    _rec("R5M", "절제 (조항·TP·거부권)", useful > 0,
         f"기여 {useful}개 / 검사 {len(rows)-1}개"
         + (f" · 판정불가 {n_bad}개(실행 실패)" if n_bad else "")
         + (" · 무기여 부품은 제거를 검토하세요." if useful < len(rows)-1-n_bad else ""))
    return pd.DataFrame(rows, columns=["절제 대상", "Calmar", "변화", "판정"])


# ── R9 : 비용 시나리오 ──────────────────────────────────────────────────────────────────────
def R9_cost(P: pd.DataFrame, months, uni) -> pd.DataFrame:
    rows, out = [], {}
    for scn in COST_SCENARIOS:
        bt = run_backtest_micro(P, months, uni, "D", scn, label=f"COST:{scn}", quiet=True)
        out[scn] = bt
        s = bt["stats"]
        rows.append([scn, f"{100*COST_SCENARIOS[scn]['roundtrip']:.2f}%",
                     f"{100*COST_SCENARIOS[scn]['participation']:.0f}%",
                     f"{100*s['cagr']:.2f}%", f"{100*s['mdd']:.1f}%", f"{s['calmar']:.2f}",
                     f"{100*s['turnover']:.0f}%"])
    LOG.table(rows, ["시나리오", "왕복비용", "참여율상한", "CAGR", "MDD", "Calmar", "회전율/월"],
              ["c", "r", "r", "r", "r", "r", "r"],
              title="R9 — 비용 시나리오 (§11.2). 비관에서 사라지면 소액계좌라도 실행 불가")
    pes = out.get("비관", {}).get("stats", {})
    ok = float(pes.get("cagr", -1)) > 0 and float(pes.get("calmar", 0) or 0) > 0.3
    _rec("R9", "비용 시나리오 (비관) ⭐", bool(ok),
         f"비관 시나리오 CAGR {100*float(pes.get('cagr', float('nan'))):.2f}% · "
         f"Calmar {float(pes.get('calmar', float('nan'))):.2f} — "
         f"{'성과 잔존' if ok else '성과 소멸. 실행 불가이므로 폐기 대상입니다(§12-5)'}",
         kill=True)
    return pd.DataFrame(rows, columns=["시나리오", "왕복비용", "참여율상한", "CAGR", "MDD",
                                       "Calmar", "회전율/월"])


def report_robustness():
    LOG.banner("강건성 검사 요약", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    if not ROBUST:
        LOG.table([], ["ID", "검사", "판정", "상세"], ["c", "l", "c", "l"])
        return
    rows = [[r["id"], r["name"], "—" if r["passed"] is None else ("통과" if r["passed"] else "실패"),
             _trunc(r["detail"], 78)] for r in ROBUST]
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["c", "l", "c", "l"], maxw=80)
    n_fail = sum(1 for r in ROBUST if r["passed"] is False)
    if n_fail:
        LOG.warn(f"강건성 검사 {n_fail}건 실패. 임계를 낮춰 통과시키지 마십시오 — "
                 f"실패는 전략에 대한 정보입니다.")
    else:
        LOG.ok("모든 강건성 검사 통과.")
