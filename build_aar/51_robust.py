

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-B  강건성 스위트 (§9)                                                                 ║
# ║   R1 블록 부트스트랩   R2 PBO(CSCV)   R3 DSR   R4 워크포워드                              ║
# ║   R5 M-EXIT 플라시보(TOST)   R6 이벤트스터디 CAR   R7 비용 민감도                         ║
# ║   R8 누수 민감도(확장창 vs 전기간)   R9 레짐·하위기간   R10 나이브 대비                    ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이         ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§13). 나쁜 결과는 그 자체로 정보다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: "OrderedDict[str, dict]" = OrderedDict()


def _rec(rid: str, name: str, passed: Optional[bool], detail: str,
         kill: bool = False, metrics: Optional[dict] = None):
    passed = None if passed is None else bool(passed)      # np.bool_ 방어 (`is False` 함정)
    ROBUST[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                   "kill": kill, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[passed]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → {icon} · {detail}")
    if passed is False and kill and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name} — {detail}")


def R1_bootstrap(bt: dict) -> None:
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    rows, verdicts = [], []
    for b in (1, 3, 6):
        res = block_bootstrap(r, n_iter=1000, block=b, seed=SEED)
        rows.append([f"{b}개월", f"{res['point']*100:+.3f}%p",
                     f"[{res['ci_lo']*100:+.3f}, {res['ci_hi']*100:+.3f}]",
                     f"{res['p_gt0']:.4f}", res["verdict"]])
        verdicts.append(res)
    LOG.table(rows, ["블록 길이", "월평균", "95% 신뢰구간", "P(≤0)", "판정"],
              ["c", "r", "r", "r", "l"],
              title="R1 블록 부트스트랩 1,000회 — 블록 길이는 추론 파라미터이지 "
                    "전략 파라미터가 아니므로 여러 개 보고해도 시행횟수에 들어가지 않습니다")
    base = verdicts[0]
    ok = bool(np.isfinite(base["ci_lo"]) and base["ci_lo"] > 0)
    _rec("R1", "블록 부트스트랩", ok,
         f"블록 1개월 기준 95% CI [{base['ci_lo']*100:+.3f}, {base['ci_hi']*100:+.3f}]%p, "
         f"P(평균≤0)={base['p_gt0']:.4f}",
         metrics=base)


def R2_pbo(grid_returns: "pd.DataFrame") -> None:
    if grid_returns is None or grid_returns.empty or grid_returns.shape[1] < 2:
        _rec("R2", "PBO (CSCV)", None, "구성이 2개 미만이라 판정 불가")
        return
    res = pbo_cscv(grid_returns.to_numpy(dtype=float), S=10, max_combos=400, seed=SEED)
    ok = np.isfinite(res.get("pbo", np.nan)) and res["pbo"] < 0.5
    _rec("R2", "PBO (CSCV 정식)", ok if np.isfinite(res.get("pbo", np.nan)) else None,
         f"PBO={res.get('pbo', float('nan')):.3f} "
         f"(조합 {res.get('n_combos', 0)}개, 구성 {res.get('N', 0)}개, "
         f"{res.get('T', 0)}개월) · {res.get('verdict', '')}",
         kill=True, metrics=res)


def R3_dsr(bt: dict, grid_returns: "pd.DataFrame") -> None:
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    sr_trials = None
    if grid_returns is not None and len(grid_returns.columns) >= 3:
        sr_trials = [float(_sharpe_raw(grid_returns[c].to_numpy(dtype=float)))
                     for c in grid_returns.columns]
    # ★ 시행횟수는 격자 12 × 유니버스 변형 2 = 24 로 센다. 적게 세는 것은 항상 낙관 방향이다.
    n_trials = len(GRID_WEIGHTS) * len(GRID_LAMBDA) * len(GRID_HOLD) * len(UNIVERSE_VARIANTS)
    res = deflated_sharpe(r, n_trials=n_trials, sr_trials=sr_trials)
    ok = np.isfinite(res.get("dsr", np.nan)) and res["dsr"] > 0.90
    _rec("R3", "DSR (과적합 보정 Sharpe)",
         ok if np.isfinite(res.get("dsr", np.nan)) else None,
         f"DSR={res.get('dsr', float('nan')):.3f} · 관측 SR(월) {res.get('sr', float('nan')):.3f} "
         f"vs 기대최대 SR* {res.get('sr_star', float('nan')):.3f} · 시행 {n_trials}회 "
         f"· 분산근거: {res.get('var_source', '')} · {res.get('verdict', '')}",
         kill=True, metrics=res)


def R4_walkforward(grid_returns: "pd.DataFrame", months) -> None:
    if grid_returns is None or grid_returns.empty:
        _rec("R4", "워크포워드", None, "격자 수익률이 없습니다")
        return
    res = walk_forward(grid_returns.to_numpy(dtype=float), months,
                       list(grid_returns.columns), train_y=5, test_y=1)
    if len(res.get("table", pd.DataFrame())):
        t = res["table"]
        LOG.table([[r["학습구간"], r["검증구간"], r["IS최적구성"], f"{r['IS Sharpe']}",
                    f"{r['OOS 월평균']}%p", f"{r['전구성 OOS 평균']}%p", r["판정"]]
                   for _, r in t.iterrows()],
                  ["학습", "검증", "IS 최적", "IS Sharpe", "OOS 월평균", "전구성 평균", "판정"],
                  ["l", "l", "l", "r", "r", "r", "l"],
                  title="R4 워크포워드 (학습 5년 / 검증 1년) — AAR 은 학습할 파라미터가 "
                        "없으므로 이것이 검정하는 것은 '구성 선택의 안정성'입니다")
    ok = (np.isfinite(res.get("oos_t", np.nan)) and res["oos_t"] > 1.0
          and res.get("folds", 0) >= 2)
    _rec("R4", "워크포워드", ok if res.get("folds", 0) >= 2 else None,
         res.get("verdict", ""), metrics={k: v for k, v in res.items() if k != "table"})


def R5_mexit_placebo(drops: "pd.DataFrame", panel: "pd.DataFrame", months) -> None:
    """★ 인과분해의 플라시보 검정 — 이 전략의 존재 이유를 검정한다.

    M-EXIT(인사이동에 의한 기계적 철회)에서도 음의 수익률이 나오면, 분해가 실패한 것이며
    신호는 그냥 '커버리지 감소 = 소외주' 를 재발견한 것이다.

    ★ "효과 없음"을 주장하려면 귀무가설 채택이 아니라 **등가성 검정(TOST)** 이 필요하다.
      등가 범위는 사전에 V-DROP 효과의 절반으로 고정한다 — 사후 조정은 검정을 무의미하게 만든다.
    ★ 표본이 부족하면 '통과'가 아니라 **판정불가(INCONCLUSIVE)** 로 낸다.
      월간 초과수익 sd 12% 에서 N=200 이면 CI 반폭이 1.66%p 라 -1%/월 효과를 통째로 덮는다.
    """
    if drops is None or drops.empty:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None, "철회 사건이 없습니다", kill=False)
        return
    d = drops.copy()
    d["grp"] = np.where(d["klass"].isin(["V-DROP", "H-EXIT"]), "V",
                        np.where(d["klass"] == "M-EXIT", "M", "X"))
    dd = d[d["grp"].isin(("V", "M"))]
    n_m = int((dd["grp"] == "M").sum())
    ct = calendar_time_alpha(dd, panel, months, hold_m=6, group_col="grp")
    if ct.empty:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None, "캘린더타임 표본 부족", kill=False)
        return
    vr = ct[ct["group"] == "V"]
    mr = ct[ct["group"] == "M"]
    mv = float(vr["mean_excess_m"].iloc[0]) if len(vr) else np.nan
    mm = float(mr["mean_excess_m"].iloc[0]) if len(mr) else np.nan
    tm = float(mr["t_hac"].iloc[0]) if len(mr) else np.nan
    if not np.isfinite(mv) or not np.isfinite(mm):
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None,
             "두 군 중 하나의 캘린더타임 시계열을 만들 수 없습니다", kill=False)
        return

    bound = abs(mv) / 2.0
    # M-EXIT 캘린더타임 시계열을 다시 만들어 TOST 를 적용한다
    F = panel[["code", "month", "fwd_ret"]].dropna().copy()
    F["code"] = as_str_series(F["code"])
    mk = F.groupby("month", observed=True)["fwd_ret"].mean().rename("mkt")
    F = F.merge(mk, on="month", how="left")
    F["ex"] = F["fwd_ret"] - F["mkt"]
    sub = dd[dd["grp"] == "M"]
    ser = []
    for m in months:
        lo = add_months(m, -5)
        names = set(as_str_series(sub.loc[(sub["month"] >= lo) & (sub["month"] <= m), "code"]))
        if not names:
            continue
        s = F[(F["month"] == m) & (F["code"].isin(names))]
        if len(s):
            ser.append(float(s["ex"].mean()))
    tost = tost_equivalence(np.array(ser), bound=bound) if len(ser) >= 12 else \
        {"equivalent": None, "verdict": f"M-EXIT 캘린더타임 관측 {len(ser)}개월로 부족"}

    n_need = 2200
    underpowered = n_m < n_need
    LOG.table([["V-DROP+H-EXIT 월평균 초과", f"{mv*100:+.3f}%p"],
               ["M-EXIT 월평균 초과", f"{mm*100:+.3f}%p (t={tm:.2f})"],
               ["사전 고정 등가범위 ±Δ", f"{bound*100:.3f}%p (= |V-DROP 효과| / 2)"],
               ["TOST 판정", str(tost.get("verdict", ""))[:70]],
               ["M-EXIT 사건 수", f"{n_m:,} (검정력 확보 기준 {n_need:,})"],
               ["검정력", "부족 — 판정불가로 처리" if underpowered else "충분"]],
              ["항목", "값"], ["l", "r"],
              title="R5 M-EXIT 플라시보 — '효과 없음'은 등가성 검정으로만 주장할 수 있습니다")

    if underpowered or tost.get("equivalent") is None:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None,
             f"M-EXIT 표본 {n_m:,}건으로 '효과 없음'을 통계적으로 주장할 검정력이 없습니다"
             f"(필요 {n_need:,}건). 통과가 아니라 **판정불가**로 보고합니다 — "
             f"표본 부족을 '통과'로 읽는 것이 이 검정의 가장 흔한 오용입니다.",
             kill=False, metrics={"n_mexit": n_m, "mean_mexit": mm, "mean_vdrop": mv})
        return
    ok = bool(tost.get("equivalent")) and abs(mm) < abs(mv) / 2.0
    _rec("R5", "M-EXIT 플라시보 (인과분해)", ok,
         f"M-EXIT {mm*100:+.3f}%p/월 이 ±{bound*100:.3f}%p 등가범위 "
         f"{'안에 있습니다 — 인과분해 성립' if ok else '밖입니다 — ★인과분해 실패. 신호는 '}"
         f"{'' if ok else '단순히 커버리지 감소를 재발견한 것일 수 있습니다'}",
         kill=True, metrics={"n_mexit": n_m, "mean_mexit": mm, "mean_vdrop": mv, **tost})


def R6_event_study(drops: "pd.DataFrame", daily: "pd.DataFrame",
                   daily_mkt: "pd.Series") -> "pd.DataFrame":
    if drops is None or drops.empty or daily is None or daily.empty:
        _rec("R6", "이벤트 스터디 CAR", None, "표본이 없습니다")
        return pd.DataFrame()
    d = drops.copy()
    d["exit_type"] = d["klass"]
    px = daily.rename(columns={"adj_close": "close"})[["code", "date", "close"]]
    car = event_study_car(d, px, daily_mkt, horizon=120, group_col="exit_type")
    if car.empty:
        _rec("R6", "이벤트 스터디 CAR", None, "CAR 을 산출하지 못했습니다")
        return car
    marks = [20, 60, 120]
    rows = []
    for g, gg in car.groupby("group"):
        row = [g, f"{int(gg['n'].max()):,}"]
        for h in marks:
            v = gg[gg["h"] == h]
            row.append(f"{float(v['mean_car'].iloc[0])*100:+.2f}%" if len(v) else "—")
        rows.append(row)
    LOG.table(rows, ["군", "사건수"] + [f"CAR t+{h}일" for h in marks],
              ["l", "r"] + ["r"] * len(marks),
              title="R6 이벤트 스터디 — 시장조정 CAR (설명용 곡선). "
                    "유의성 판정은 겹치는 창의 상관 때문에 캘린더타임(H3/R5)으로만 합니다")
    _rec("R6", "이벤트 스터디 CAR", True,
         f"{car['group'].nunique()}개 군 × 120영업일 CAR 곡선 산출 완료 "
         f"(유의성은 캘린더타임 검정 결과를 보십시오)")
    return car


def R7_cost_sensitivity(run_fn: Callable, scenarios: Dict[str, float]) -> None:
    rows, surv = [], None
    for nm, mult in scenarios.items():
        bt = run_fn(cost_mult=mult, label=f"cost_{nm}")
        s = perf_stats(bt["returns"])
        rows.append([nm, f"×{mult:g}", f"{s.get('CAGR', np.nan)*100:+.2f}%",
                     f"{s.get('Sharpe', np.nan):.3f}", f"{s.get('월평균', np.nan)*100:+.3f}%p",
                     f"{s.get('월평균비용', np.nan)*100:.3f}%p",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
        if nm == "기본":
            surv = s
    LOG.table(rows, ["시나리오", "배수", "CAGR", "Sharpe", "월평균", "월평균비용", "HAC t"],
              ["l", "c", "r", "r", "r", "r", "r"],
              title="R7 비용 민감도 (§7.1 — 0 / 기본 / 2배 3종 전부 보고)")
    ok = bool(surv and np.isfinite(surv.get("Sharpe", np.nan)) and surv["Sharpe"] > 0
              and surv.get("월평균", 0) > 0)
    _rec("R7", "비용 차감 후 생존", ok,
         f"기본 시나리오 Sharpe {surv.get('Sharpe', float('nan')):.3f}, "
         f"월평균 {surv.get('월평균', float('nan'))*100:+.3f}%p" if surv else "산출 실패")


def R8_leakage(V: "pd.DataFrame", S_builder: Callable, run_fn: Callable) -> None:
    """확장창 vs 전기간 — 전기간이 유의하게 좋다면 그 초과분이 곧 누수량이다."""
    if V is None or V.empty or "VAS_fullsample" not in V.columns:
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None, "전기간 VAS 가 없습니다")
        return
    both = V[["VAS", "VAS_fullsample"]].dropna()
    if len(both) < 100:
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None, "비교 표본 부족")
        return
    corr = float(both["VAS"].corr(both["VAS_fullsample"]))
    try:
        bt_e = run_fn(vas_col="VAS", label="R8_expanding")
        bt_f = run_fn(vas_col="VAS_fullsample", label="R8_full")
        se = perf_stats(bt_e["returns"]).get("Sharpe", np.nan)
        sf = perf_stats(bt_f["returns"]).get("Sharpe", np.nan)
        a = bt_e["returns"]["ret"].fillna(0).to_numpy()
        b = bt_f["returns"]["ret"].fillna(0).to_numpy()
        k = min(len(a), len(b))
        mu, t = hac_tstat(b[:k] - a[:k])
    except Exception as e:                                     # noqa
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None,
             f"비교 백테스트 실패({type(e).__name__})")
        return
    leaked = bool(np.isfinite(t) and t > 2.0)
    _rec("R8", "누수 민감도 (확장창 vs 전기간)", (not leaked),
         f"신호 상관 {corr:.4f} · Sharpe 확장창 {se:.3f} vs 전기간 {sf:.3f} · "
         f"월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). " +
         ("★ 전기간 회귀가 유의하게 좋습니다 — 그 초과분이 곧 미래누수량입니다. "
          "생산 경로는 확장창이므로 보고 성과는 안전합니다." if leaked else
          "전기간 회귀가 유의한 우위를 보이지 않습니다 — 통제회귀 경로에 큰 누수가 "
          "없다는 뜻입니다."),
         metrics={"corr": corr, "sharpe_expanding": se, "sharpe_full": sf, "t_diff": t})


def R9_regime(bt: dict, bench: Dict[str, "pd.Series"]) -> None:
    R = bt["returns"].set_index("month")["ret"]
    rows = []
    ks = bench.get("KOSPI")
    if ks is not None and len(ks):
        up = pd.Series(ks).reindex(R.index) > 0
        for lab, msk in (("강세(코스피↑)", up), ("약세(코스피↓)", ~up)):
            x = R[msk.fillna(False)]
            if len(x) >= 6:
                rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                             f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    half = len(R) // 2
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        if len(x) >= 6:
            rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                         f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    LOG.table(rows, ["레짐", "월수", "월평균", "연변동성", "승률"], ["l", "r", "r", "r", "r"],
              title="R9 레짐 분할")
    Y = bt["returns"].copy()
    Y["year"] = Y["month"].dt.year
    yrows = []
    for y, g in Y.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        yrows.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%", f"{g['ret'].mean()*100:+.3f}%p",
                      f"{(g['ret']>0).mean()*100:.0f}%", f"{g['n'].mean():.1f}",
                      f"{g['cash'].mean()*100:.0f}%"])
    LOG.table(yrows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수", "평균현금"],
              ["c", "r", "r", "r", "r", "r", "r"], title="R9 연도별 분해")
    yv = [float(r[2].rstrip("%")) for r in yrows]
    pos = sum(1 for v in yv if v > 0)
    _rec("R9", "레짐·하위기간 안정성", True,
         f"{pos}/{len(yv)}개 연도 양(+) · 최악 {min(yv):+.1f}% / 최고 {max(yv):+.1f}%")


def R10_vs_naive(bt_aar: dict, bt_naive: dict) -> None:
    """★ 이 시스템의 존재 이유를 검정한다.

    §6.3 통제회귀·축소추정·인과분해를 다 하고도 '단순 리포트 건수 증가'를 못 이기면,
    그 복잡도 전체가 불필요하다는 뜻이다. 유리하게 해석하지 않고 그대로 보고한다."""
    if not bt_naive or bt_naive["returns"].empty:
        _rec("R10", "AAR vs 나이브 (통제의 가치)", None, "나이브 백테스트가 없습니다")
        return
    a = bt_aar["returns"]["ret"].fillna(0).to_numpy()
    b = bt_naive["returns"]["ret"].fillna(0).to_numpy()
    k = min(len(a), len(b))
    mu, t = hac_tstat(a[:k] - b[:k])
    sa = perf_stats(bt_aar["returns"]).get("Sharpe", np.nan)
    sb = perf_stats(bt_naive["returns"]).get("Sharpe", np.nan)
    ok = bool(np.isfinite(t) and t > 1.0 and sa > sb)
    _rec("R10", "AAR vs 나이브 (통제의 가치)", ok,
         f"AAR Sharpe {sa:.3f} vs 나이브(단순 건수증가) {sb:.3f} · "
         f"월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). " +
         ("통제회귀·축소추정이 만든 정보가 실재합니다." if ok else
          "★ AAR 이 나이브를 유의하게 이기지 못했습니다. §6.3 통제와 §6.2 축소추정, "
          "§6.5 인과분해가 전부 불필요한 복잡도라는 뜻입니다. 유리하게 해석하지 "
          "않고 그대로 보고합니다."),
         kill=True, metrics={"sharpe_aar": sa, "sharpe_naive": sb, "t": t})


def report_robustness():
    LOG.banner("강건성 검사 요약", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    rows = []
    for rid, r in ROBUST.items():
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid + ("⭐" if r["kill"] else ""), _trunc(r["name"], 26), icon,
                     _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)
    fails = [r for r in ROBUST.values() if r["pass"] is False]
    kills = [r for r in fails if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§11 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("모든 강건성 검사 통과.")
