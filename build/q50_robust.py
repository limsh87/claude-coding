

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  실험 매트릭스 · 다중검정 보정 · 강건성 (§8.2, §8.3, §8.4)                              ║
# ║                                                                                          ║
# ║  주 실험 3개(V/VQ/VQF full) + 보조 어블레이션 4개(X1~X4) 를 '하나의 검정 패밀리'로 묶어      ║
# ║  BH-FDR(q=0.10) 보정한다. 개별 실험의 유의성을 보정 없이 주장하지 않는다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: List[dict] = []
EXPERIMENTS: "OrderedDict[str, dict]" = OrderedDict()


def _pval_from_t(t: float, n: int) -> float:
    """★ 단측(우측) p값. 검정 가설은 '알파 > 0' 이다.

    양측 p를 쓰면 t = −4 (강하게 '음의' 알파) 인 실험이 p ≈ 0.0001 로 나와 BH-FDR 를
    통과하고 표에 '✔ 유의' 로 찍힌다. 손실이 유의하다는 뜻인데 읽는 사람은 정반대로 읽는다.
    단측이면 같은 실험의 p ≈ 0.9999 로 정확히 기각된다.
    """
    if t is None or not np.isfinite(t) or n < 3:
        return float("nan")
    try:
        from scipy import stats as _st                       # type: ignore
        return float(1.0 - _st.t.cdf(t, df=max(1, n - 1)))
    except Exception:
        return float(1.0 - 0.5 * (1.0 + math.erf(t / math.sqrt(2.0))))


def run_experiment(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str,
                   u200_n: int = U200_N, final_n: int = FINAL_N, second_n: int = SECOND_N,
                   use_tone: bool = True, use_nonfin: bool = True,
                   use_exclusion: bool = True, use_rule3a: bool = True,
                   stage: str = "full", scheme: str = "equal",
                   label: str = "", quiet: bool = True) -> dict:
    """한 실험(변형 × 구성)을 끝까지 돌린다. 패널 재계산 없이 선정 단계만 다시 돈다.

    ★ 실험 7개 + 민감도 수십 개를 매번 데이터 수집부터 돌리면 4시간 예산(§0.5)을 넘긴다.
      비싼 것(수집·피처)은 한 번만 하고, 싼 것(스코어·선정·체결)만 반복한다.
    """
    keep_level = LOG.min
    if quiet:
        LOG.min = LOG.LEVELS["WARN"]
    try:
        d = build_u200(P, variants=(variant,), n=u200_n)
        if stage != "x1":
            d = apply_filter2(d, variant, n=second_n, use_tone=use_tone,
                              use_nonfin=use_nonfin, use_exclusion=use_exclusion)
        d["_sel"] = build_final_selection(d, variant, n_final=final_n,
                                          use_rule3a=use_rule3a, stage=stage)
        bt = run_qbacktest(d, cal, "_sel", fwd, scheme=scheme, apply_costs=True,
                           label=label or f"{variant}-{stage}")
        bt["panel"] = d
    finally:
        LOG.min = keep_level
    return bt


def summarize_experiment(name: str, bt: dict, P: Optional[pd.DataFrame] = None,
                         variant: str = "", fwd: Optional[pd.DataFrame] = None,
                         desc: str = "") -> dict:
    R = bt["returns"]
    net = qperf_stats(R, "ret")
    gro = qperf_stats(R, "ret_gross")
    ic = icir = np.nan
    n_ic = 0
    if P is not None and fwd is not None and variant:
        sc = f"score2_{variant}" if f"score2_{variant}" in P.columns else f"score1_{variant}"
        pool = f"u200_{variant}" if f"u200_{variant}" in P.columns else None
        ic, icir, n_ic = rank_ic(P, sc, fwd, pool_col=pool)
    rec = {"name": name, "desc": desc, "net": net, "gross": gro,
           "IC": ic, "ICIR": icir, "n_ic": n_ic,
           # ★ §9-C2 는 '차이의 유의성'을 요구한다. 차이를 검정하려면 두 실험의 분기수익률
           #   시계열이 필요하므로 여기서 보관한다(요약 통계만으로는 만들 수 없다).
           "R": (R[["rebal", "ret"]].copy() if R is not None and len(R) else None),
           "t": net.get("t통계량(HAC)", np.nan), "n": net.get("분기수", 0)}
    rec["p"] = _pval_from_t(rec["t"], int(rec["n"] or 0))
    EXPERIMENTS[name] = rec
    return rec


def report_experiment_table(names: Sequence[str], title: str):
    rows = []
    for nm in names:
        e = EXPERIMENTS.get(nm)
        if not e:
            continue
        n_, g_ = e["net"], e["gross"]
        f = lambda v, p=True: ("—" if v is None or not np.isfinite(v) else
                               (f"{v*100:+.2f}%" if p else f"{v:,.3f}"))
        rows.append([nm,
                     f(g_.get("CAGR")), f(n_.get("CAGR")),
                     f(n_.get("MDD")), f(n_.get("Sharpe"), False), f(n_.get("Sortino"), False),
                     f(e.get("IC"), False), f(e.get("ICIR"), False),
                     f(n_.get("분기평균회전율"), False),
                     f"{n_.get('평균종목수', float('nan')):.1f}",
                     f(n_.get("승률")), f(e.get("t"), False)])
    LOG.table(rows, ["실험", "CAGR(비용전)", "CAGR(비용후)", "MDD", "Sharpe", "Sortino",
                     "IC", "IC-IR", "회전율", "평균종목", "승률", "HAC t"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=16, title=title)
    LOG.info("§8.1 — 비용 전/후를 반드시 병기합니다. 초소형주는 스프레드가 알파를 통째로 "
             "잠식할 수 있으므로 판단 기준은 언제나 '비용 차감 후' 입니다.")


def paired_diff_test(a: str, b: str, label: Optional[str] = None) -> dict:
    """실험 a − b 의 분기수익률 차이에 대한 HAC t 검정. §9-C2 가 요구하는 '차이의 유의성'.

    ★ 예전에는 C2 가 fdr_pass["VQF-full"] 즉 'VQF 자신의 알파가 0보다 큰가'를 읽었다.
      VQF 와 VQ 는 U-200 중복률이 높아(C3 가 0.85 미만을 요구할 정도) 수익률이 강하게
      상관된다 — 두 시계열의 차이는 각각의 수준보다 훨씬 작은 신호다. 자기 유의성으로
      대체하면 C2 통과가 극적으로 쉬워지고, 수급 축 채택 쪽으로 기운다(상향 드리프트).
    """
    nm = label or f"{a}−{b}(차이)"
    ra = (EXPERIMENTS.get(a) or {}).get("R")
    rb = (EXPERIMENTS.get(b) or {}).get("R")
    if ra is None or rb is None or not len(ra) or not len(rb):
        return {"name": nm, "t": np.nan, "p": np.nan, "n": 0, "mean": np.nan}
    m = ra.merge(rb, on="rebal", how="inner", suffixes=("_a", "_b"))
    d = pd.to_numeric(m["ret_a"], errors="coerce") - pd.to_numeric(m["ret_b"], errors="coerce")
    d = d.dropna().to_numpy(dtype=float)
    if len(d) < 4:
        return {"name": nm, "t": np.nan, "p": np.nan, "n": int(len(d)), "mean": np.nan}
    # ★★ hac_tstat 는 (평균, t통계량) 을 돌려준다 — (t, se) 가 아니다 ★★
    #   예전엔 `t, _se = hac_tstat(d)` 라 '평균'을 t 통계량 자리에 받았다. 분기 평균차는
    #   보통 0.0x 수준이므로 p 값이 항상 0.49 근처가 되고, 그 결과
    #     · §10.4 폐기조건 ②(p ≥ 0.10)가 '매 실행' 발동 → FULL 실행이 L6.VERDICT 에서
    #       KillCriteria 로 중단되고 최종 종목표가 나오지 않는다
    #     · §9-C2 가 영원히 통과하지 못해 수급축 채택 판정이 데이터와 무관하게 고정된다
    #     · §8.3 BH-FDR 패밀리에 가짜 p 가 섞여 진짜 가설들의 임계가 낮아진다
    #   실측(분기 +3.0% 차이를 심고 40분기): 보고된 t 0.029 · p 0.4885 인데
    #   실제 HAC t 는 20.49 · p < 1e-15 였다. 벗어나려면 분기 평균차가 +130% 를 넘어야 했다.
    #   다른 호출부 두 곳은 올바르게 풀고 있었고 여기만 틀렸다.
    _mu, t = hac_tstat(d)
    return {"name": nm, "t": float(t), "p": _pval_from_t(float(t), len(d)),
            "n": int(len(d)), "mean": float(_mu)}


def report_bh_fdr(names: Sequence[str], q: float = BH_FDR_Q,
                  extra_tests: Optional[Sequence[dict]] = None) -> dict:
    """§8.3 — 주 실험 3개 + 어블레이션 4개를 하나의 패밀리로 묶어 BH-FDR 보정.

    extra_tests: {"name","t","p","n"} 형태의 추가 검정(예: §9-C2 의 VQF−VQ 차이).
                 같은 패밀리에 넣어야 보정이 정직하다.
    """
    for _e in (extra_tests or ()):
        if _e and np.isfinite(_e.get("p", np.nan)):
            EXPERIMENTS[_e["name"]] = {"name": _e["name"], "desc": "§9-C2 차이검정",
                                       "net": {}, "gross": {}, "R": None,
                                       "t": _e["t"], "p": _e["p"], "n": _e["n"]}
    names = list(names) + [e["name"] for e in (extra_tests or ())
                           if e and np.isfinite(e.get("p", np.nan))]
    fam = [n for n in names if n in EXPERIMENTS and np.isfinite(EXPERIMENTS[n].get("p", np.nan))]
    if not fam:
        LOG.warn("유효한 p값이 없어 BH-FDR 보정을 수행할 수 없습니다.")
        return {}
    ps = [EXPERIMENTS[n]["p"] for n in fam]
    passed = bh_fdr(ps, q=q)
    order = np.argsort(ps)
    m = len(ps)
    rows = []
    for rank_i, idx in enumerate(order, start=1):
        nm = fam[idx]
        thr = q * rank_i / m
        rows.append([nm, f"{EXPERIMENTS[nm]['t']:+.2f}", f"{ps[idx]:.4f}", f"{thr:.4f}",
                     "✔ 유의" if passed[idx] else "✘ 기각"])
    LOG.table(rows, ["실험", "HAC t", "p값", "BH 임계값", f"판정(q={q})"],
              ["l", "r", "r", "r", "c"],
              title=f"BH-FDR 다중검정 보정 (패밀리 {m}개 · q={q}, 단측 '알파>0') — "
                    f"보정 없이 개별 유의성을 주장하지 않는다")
    n_pass = int(passed.sum())
    if n_pass == 0:
        LOG.warn(f"패밀리 {m}개 중 BH-FDR 보정 후 유의한 실험이 하나도 없습니다. "
                 f"이는 '알파가 없다'와 '표본({EXPERIMENTS[fam[0]]['n']}분기)이 짧다'를 "
                 f"구분하지 못하는 상태입니다 — 방법론적 우려로 명시합니다.")
    return {n: bool(p) for n, p in zip(fam, passed)}


# ── §8.4 강건성 ─────────────────────────────────────────────────────────────────────────────
def R_subperiod(bt: dict, label: str = ""):
    R = bt["returns"]
    if len(R) < 8:
        return
    h = len(R) // 2
    a, b = qperf_stats(R.iloc[:h]), qperf_stats(R.iloc[h:])
    rows = []
    for k in ("CAGR", "Sharpe", "MDD", "승률"):
        fa, fb = a.get(k), b.get(k)
        fmt = (lambda v: "—" if v is None or not np.isfinite(v) else
               (f"{v*100:+.2f}%" if k in ("CAGR", "MDD", "승률") else f"{v:.3f}"))
        rows.append([k, fmt(fa), fmt(fb)])
    LOG.table(rows, ["지표", f"전반부({h}분기)", f"후반부({len(R)-h}분기)"], ["l", "r", "r"],
              title=f"[{label}] 서브기간 분할 — 한쪽 구간에서만 나오는 알파인가")
    ROBUST_RESULTS.append({"test": "서브기간", "label": label,
                           "detail": f"전반 CAGR {a.get('CAGR', float('nan')):.3f} / "
                                     f"후반 {b.get('CAGR', float('nan')):.3f}"})


def R_size_quartile(bt: dict, P: pd.DataFrame, label: str = ""):
    """시총 사분위별 성과 분해 — 하위 1000 안에서도 어느 크기 구간이 성과를 냈는가."""
    H = bt.get("holdings")
    if H is None or H.empty or "mktcap" not in P.columns:
        return
    cap = P[["code", "rebal", "mktcap"]].drop_duplicates(["code", "rebal"])
    d = H.merge(cap, on=["code", "rebal"], how="left").dropna(subset=["mktcap"])
    if d.empty:
        return
    d["q"] = d.groupby("rebal", observed=True)["mktcap"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 4, labels=["Q1(최소)", "Q2", "Q3", "Q4(최대)"])
        if s.notna().sum() >= 8 else pd.Series(["—"] * len(s), index=s.index))
    g = d.groupby("q", observed=True).agg(n=("code", "size"), ret=("ret", "mean"),
                                          contrib=("ret", lambda s: float(np.nansum(s))))
    LOG.table([[str(i), f"{int(r.n):,}", f"{r.ret*100:+.2f}%"] for i, r in g.iterrows()],
              ["시총 사분위", "관측", "분기 평균수익"], ["l", "r", "r"],
              title=f"[{label}] 시총 사분위별 성과 분해 (§8.4)")
    ROBUST_RESULTS.append({"test": "시총사분위", "label": label,
                           "detail": " / ".join(f"{i}:{r.ret*100:+.2f}%" for i, r in g.iterrows())})


def R_param_sensitivity(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str):
    """U-200 크기 · 최종 보유종목수 민감도 (§8.4). 패널 재계산 없이 선정만 다시 돈다."""
    rows = []
    for n2 in SENS_U200_SIZES:
        bt = run_experiment(P, cal, fwd, variant, u200_n=n2, label=f"U200={n2}")
        s = qperf_stats(bt["returns"])
        rows.append([f"U-200 = {n2}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}", f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    for nf in SENS_FINAL_SIZES:
        bt = run_experiment(P, cal, fwd, variant, final_n=nf, label=f"N={nf}")
        s = qperf_stats(bt["returns"])
        rows.append([f"최종 보유 = {nf}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}", f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    LOG.table(rows, ["파라미터", "CAGR(비용후)", "Sharpe", "MDD"], ["l", "r", "r", "r"],
              title=f"[{variant}] 파라미터 민감도 — 특정 값에서만 나오는 성과인가")
    ROBUST_RESULTS.append({"test": "파라미터민감도", "label": variant,
                           "detail": f"U200 {SENS_U200_SIZES} · N {SENS_FINAL_SIZES}"})


def R_weight_scheme(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str):
    rows = []
    for sch in WEIGHT_SCHEMES:
        bt = run_experiment(P, cal, fwd, variant, scheme=sch, label=f"{variant}-{sch}")
        s = qperf_stats(bt["returns"])
        rows.append([{"equal": "동일가중(기준)", "invvol": "역변동성"}.get(sch, sch),
                     f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('분기평균회전율', float('nan')):.3f}"])
    LOG.table(rows, ["가중 방식", "CAGR(비용후)", "Sharpe", "MDD", "회전율"],
              ["l", "r", "r", "r", "r"], title=f"[{variant}] 가중 방식 (§7.4 동일가중 기준 + 역변동성 병행)")


def R_rebal_shift(rebuild_fn: Callable, variant: str):
    """리밸런싱 시점 ±5거래일 이동 민감도. 캘린더가 바뀌므로 패널을 다시 만들어야 한다 —
    가장 비싼 강건성 검정이라 최우수 변형에만 적용한다."""
    rows = []
    for sh in SENS_REBAL_SHIFTS:
        try:
            s = rebuild_fn(sh, variant)
        except Exception as e:                                # noqa
            LOG.warn(f"리밸런싱 {sh:+d}거래일 재구성 실패({type(e).__name__}) — 건너뜁니다.")
            continue
        if not s:
            continue
        rows.append([f"{sh:+d} 거래일", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    if rows:
        LOG.table(rows, ["리밸런싱 시점 이동", "CAGR(비용후)", "Sharpe", "MDD"],
                  ["l", "r", "r", "r"],
                  title=f"[{variant}] 리밸런싱 시점 ±5거래일 민감도 (§8.4)")
        ROBUST_RESULTS.append({"test": "리밸시점이동", "label": variant,
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def R_flow_window(rebuild_flow_fn: Callable):
    """VQF 수급 창 길이 민감도 20/60/120일 (§8.4)."""
    rows = []
    for w in SENS_FLOW_WINDOWS:
        try:
            s = rebuild_flow_fn(w)
        except Exception as e:                                # noqa
            LOG.warn(f"수급 창 {w}일 재구성 실패({type(e).__name__}) — 건너뜁니다.")
            continue
        if not s:
            continue
        rows.append([f"{w}일", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('분기평균회전율', float('nan')):.3f}"])
    if rows:
        LOG.table(rows, ["수급 창 길이", "CAGR(비용후)", "Sharpe", "MDD", "회전율"],
                  ["l", "r", "r", "r", "r"],
                  title="[VQF] 수급 창 길이 민감도 (§8.4) — 60일이 특별한 값인가")
        ROBUST_RESULTS.append({"test": "수급창길이", "label": "VQF",
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def R_irc_split(rebuild_irc_fn: Callable, variant: str):
    """한국IR협의회 기업의뢰형 리포트 포함/제외 (§0.4, §8.4)."""
    rows = []
    for excl in (False, True):
        try:
            s = rebuild_irc_fn(excl, variant)
        except Exception as e:                                # noqa
            LOG.warn(f"IR협의회 {'제외' if excl else '포함'} 재구성 실패({type(e).__name__})")
            continue
        if not s:
            continue
        rows.append(["제외" if excl else "포함(기준)",
                     f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    if rows:
        LOG.table(rows, ["기업의뢰형 리포트", "CAGR(비용후)", "Sharpe", "MDD"],
                  ["l", "r", "r", "r"],
                  title=f"[{variant}] 한국IR협의회 기업의뢰형 리포트 포함/제외 (§0.4 별도 태깅 검증)")
        ROBUST_RESULTS.append({"test": "IR협의회분리", "label": variant,
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def report_robustness():
    if not ROBUST_RESULTS:
        LOG.warn("강건성 결과가 비었습니다.")
        return
    LOG.table([[r["test"], r.get("label", ""), _trunc(str(r.get("detail", "")), 60)]
               for r in ROBUST_RESULTS],
              ["검정", "대상", "요약"], ["l", "l", "l"], maxw=62,
              title="강건성 검사 요약 (§8.4)")
