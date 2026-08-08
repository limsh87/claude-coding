# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트 (§10) — 순서대로. 앞 단계 실패 시 진행 금지.                             ║
# ║                                                                                          ║
# ║   R2-F ⭐⭐ 소진조건 vs 단순 낙폭과대   (이 전략의 존재 이유. 다른 무엇보다 먼저 본다)      ║
# ║   R0     자체측정 벤치마크 대비        (수치 하드코딩 금지 — 여기서 직접 재측정)           ║
# ║   R1     누수 자가검정                (미래수익 주입 + 신호 -1주 시프트, 둘 다 개선해야)   ║
# ║   R12 ⭐ 꼬리 동시손실                (위험 프리미엄의 대가를 사전에 측정하고 상한 확정)   ║
# ║   R3     팩터 직교화                  (시장·규모·가치·모멘텀·저변동성 잔차 알파)           ║
# ║   R5     절제                        (무엇이 실제로 기여하는가)                            ║
# ║   R7     레짐 분할 / R9 회전율·비용 시나리오                                               ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 만져 좋아 보이게 만들지 않는다(§11).    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: List[dict] = []


def _record(rid: str, name: str, passed: Optional[bool], detail: str,
            kill: bool = False, numbers: Optional[dict] = None):
    ROBUST_RESULTS.append({"id": rid, "name": name, "pass": passed, "detail": detail,
                           "kill": kill, "numbers": numbers or {}})
    icon = "✔" if passed else ("✘" if passed is False else "→")
    (LOG.ok if passed else (LOG.error if passed is False else LOG.info))(
        f"[{rid}] {icon} {name} — {detail}")
    if kill and passed is False and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name}: {detail}")


def _stat(bt: dict) -> dict:
    return perf_stats_w(bt.get("returns", pd.DataFrame()))


def _series(bt: dict) -> pd.Series:
    R = bt.get("returns")
    if R is None or not len(R):
        return pd.Series(dtype=float)
    return pd.Series(R["ret"].to_numpy(dtype=float), index=pd.DatetimeIndex(R["wk"]))


def _diff_tstat(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """두 전략 수익률 차이의 평균과 HAC t. '유의하게 이긴다'를 눈대중하지 않는다."""
    idx = a.index.intersection(b.index)
    if len(idx) < 20:
        return (np.nan, np.nan)
    d = (a.reindex(idx).fillna(0) - b.reindex(idx).fillna(0)).to_numpy(dtype=float)
    mu, t = hac_tstat(d)
    return float(np.mean(d)), float(t)


# ═══ R2-F — 이 전략의 존재 이유 (§10.1) ═════════════════════════════════════════════════════
def R2F_exhaustion_vs_drawdown(P: pd.DataFrame, run_fn: Callable) -> dict:
    """A 낙폭과대 단독 / B 소진조건 단독(낙폭 무시) / C FLP 전체.
    동일 유니버스·동일 비용·동일 기간. 다른 것은 조건뿐이다."""
    base = P.copy()

    # A: 낙폭 하위 분위 매수 — 신용·수급 조건 없음, 방화벽/밴드만 공통 적용
    A = base.copy()
    A["E_rank"] = A.groupby("wk", observed=True)["f_dd"].rank(pct=True, ascending=True)
    A["Signal"] = (A["E_rank"].fillna(0.0) * (A["f_dd"] < PH_DD_ENTER).astype(int) *
                   A["FIREWALL"] * A["in_band"])
    A["Signal"] = A["Signal"].where(A["E_rank"] <= 0.20, 0.0)     # 하위 20% 분위만
    A["Signal_rank"] = A["Signal"].where(A["Signal"] > 0)

    # B: 소진 조건 단독 (낙폭 조건 제거)
    B = classify_phase(base, use_dd=False)
    B = assemble_score(B, use_tps=["TP_F2", "TP_F4"])

    # C: 전체
    C = base

    bts = {}
    for lab, pp in (("A_낙폭과대단독", A), ("B_소진단독", B), ("C_FLP전체", C)):
        bts[lab] = run_fn(pp, label=lab)
    sA, sB, sC = (_stat(bts["A_낙폭과대단독"]), _stat(bts["B_소진단독"]), _stat(bts["C_FLP전체"]))
    rows = []
    for lab, s in (("A 낙폭과대 단독", sA), ("B 소진조건 단독", sB), ("C FLP 전체", sC)):
        rows.append([lab, f"{s.get('CAGR', float('nan')):.2%}", f"{s.get('MDD', float('nan')):.2%}",
                     f"{s.get('Sharpe', float('nan')):.2f}", f"{s.get('Calmar', float('nan')):.2f}",
                     f"{s.get('승률', float('nan')):.1%}", f"{s.get('평균종목수', float('nan')):.1f}"])
    LOG.table(rows, ["비교군", "CAGR", "MDD", "Sharpe", "Calmar", "승률", "평균종목수"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="R2-F ⭐ 소진 조건이 실제로 기여하는가 (§10.1) — 다른 어떤 지표보다 먼저 본다")

    dCA, tCA = _diff_tstat(_series(bts["C_FLP전체"]), _series(bts["A_낙폭과대단독"]))
    dCB, tCB = _diff_tstat(_series(bts["C_FLP전체"]), _series(bts["B_소진단독"]))
    cagr_gap = (sC.get("CAGR", np.nan) - sA.get("CAGR", np.nan))

    # 판정은 '경제적 크기'와 '통계적 유의성'을 따로 본다.
    #  · 둘 다 충족 → PASS
    #  · 크기는 있으나 유의하지 않음 → 판정보류(더 많은 증거 필요). 킬하지 않는다 —
    #    노이즈를 근거로 전략을 죽이는 것도, 살리는 것도 똑같이 부정직하다.
    #  · 크기 자체가 없음(≤2%p) → §11-4 킬. 낙폭과대의 재포장이다.
    verdict, passed, kill = "", None, False
    if not np.isfinite(cagr_gap):
        verdict = "표본 부족으로 판정 불가 — 데이터 등급을 먼저 올려야 한다"
        passed = None
    elif cagr_gap > 0.02 and (np.isfinite(tCA) and tCA >= 1.5):
        verdict = (f"PASS — C가 A를 CAGR {cagr_gap:+.2%}p, 주간초과수익 t={tCA:.2f} 로 상회. "
                   f"소진 판정이 실제로 기여한다")
        passed = True
    elif cagr_gap > 0.02:
        verdict = (f"판정보류 — C가 A보다 CAGR {cagr_gap:+.2%}p 높지만 t={tCA:.2f} 로 "
                   f"유의하지 않다(기준 1.5). 크기는 있으나 증거가 얇다: 표본 구간·데이터 등급을 "
                   f"올린 뒤 재측정할 것. 유의성 없이 PASS 로 읽지 말 것")
        passed = None
    elif cagr_gap < -0.02:
        verdict = (f"C < A ({cagr_gap:+.2%}p) — 소진 조건이 좋은 기회를 죽이고 있다. "
                   f"임계 재검토 후 재측정 대상(§10.1)")
        passed = False
    else:
        verdict = (f"★ C ≈ A (CAGR 차이 {cagr_gap:+.2%}p, t={tCA:.2f}) — 이건 새 전략이 아니라 "
                   f"낙폭과대의 재포장이다. §11-4 킬 기준")
        passed, kill = False, True
    if np.isfinite(dCB) and abs(sC.get("CAGR", 0) - sB.get("CAGR", 0)) < 0.02 and \
            sB.get("CAGR", -9) > sA.get("CAGR", -9):
        verdict += " · B>A 이면서 C≈B → 낙폭 조건 불필요. 더 단순한 B를 최종안으로 검토할 것"

    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        verdict += ("  ⚠ 단, 신용잔고가 프록시(Fallback B)이므로 이 판정의 신뢰도는 "
                    "구조적으로 하향입니다 — '소진'이 아니라 '개인 누적순매수'를 본 결과입니다")
    _record("R2-F", "소진 조건 vs 단순 낙폭과대 ⭐⭐", passed, verdict, kill=kill,
            numbers={"CAGR_A": sA.get("CAGR"), "CAGR_B": sB.get("CAGR"), "CAGR_C": sC.get("CAGR"),
                     "t_C_minus_A": tCA, "t_C_minus_B": tCB})
    return {"A": sA, "B": sB, "C": sC, "t_CA": tCA, "verdict": verdict, "bts": bts}


# ═══ R0 — 자체측정 벤치마크 대비 ════════════════════════════════════════════════════════════
def R0_benchmark(bt: dict, bench: Dict[str, pd.Series]) -> None:
    s = _stat(bt)
    rows = [["FLP 전략", f"{s.get('CAGR', np.nan):.2%}", f"{s.get('MDD', np.nan):.2%}",
             f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('Calmar', np.nan):.2f}"]]
    best_calmar = -9e9
    for name, sr in bench.items():
        if sr is None or not len(sr.dropna()):
            continue
        b = perf_stats_w(pd.DataFrame({"wk": sr.index, "ret": sr.fillna(0).to_numpy()}))
        rows.append([name, f"{b.get('CAGR', np.nan):.2%}", f"{b.get('MDD', np.nan):.2%}",
                     f"{b.get('Sharpe', np.nan):.2f}", f"{b.get('Calmar', np.nan):.2f}"])
        if np.isfinite(b.get("Calmar", np.nan)):
            best_calmar = max(best_calmar, b["Calmar"])
    LOG.table(rows, ["대상", "CAGR", "MDD", "Sharpe", "Calmar"], ["l", "r", "r", "r", "r"],
              title="R0 자체측정 벤치마크 (★ 수치 하드코딩 금지 — 이 실행에서 직접 측정한 값)")
    if best_calmar <= -9e8:
        _record("R0", "벤치마크 대비", None, "벤치마크를 측정하지 못해 판정 보류 (수치를 임의로 채우지 않음)")
        return
    ok = np.isfinite(s.get("Calmar", np.nan)) and s["Calmar"] > best_calmar
    _record("R0", "벤치마크 대비 (Calmar)", bool(ok),
            f"전략 Calmar {s.get('Calmar', np.nan):.2f} vs 최고 벤치마크 {best_calmar:.2f}",
            numbers={"calmar": s.get("Calmar"), "bench_best": best_calmar})


# ═══ R1 — 누수 자가검정 ═════════════════════════════════════════════════════════════════════
def R1_leakage(P: pd.DataFrame, run_fn: Callable, base_stat: dict) -> None:
    """두 개의 '고의 오염본'이 뚜렷하게 좋아져야 한다. 안 좋아지면 하네스가 고장난 것이고,
    그 경우 이 실행의 모든 결과는 무효다(§11-5)."""
    base_c = base_stat.get("CAGR", np.nan)

    # (a) 미래 수익률 직접 주입
    Pa = P.copy()
    Pa["Signal"] = Pa["fwd_ret"].groupby(Pa["wk"]).rank(pct=True).fillna(0) * \
        Pa["in_band"] * Pa["FIREWALL"]
    Pa["Signal_rank"] = Pa["Signal"].where(Pa["Signal"] > 0)
    sa = _stat(run_fn(Pa, label="R1a_미래수익주입"))

    # (b) 신호를 1주 앞당김(=미래를 5영업일 미리 봄)
    Pb = P.sort_values(["code", "wk"]).copy()
    Pb["Signal"] = Pb.groupby("code", observed=True)["Signal"].shift(-1).fillna(0.0)
    Pb["Signal_rank"] = Pb["Signal"].where(Pb["Signal"] > 0)
    sb = _stat(run_fn(Pb, label="R1b_신호5영업일선행"))

    LOG.table([["기준(정상)", f"{base_c:.2%}", f"{base_stat.get('Sharpe', np.nan):.2f}"],
               ["(a) 미래수익 주입", f"{sa.get('CAGR', np.nan):.2%}", f"{sa.get('Sharpe', np.nan):.2f}"],
               ["(b) 신호 -5영업일", f"{sb.get('CAGR', np.nan):.2%}", f"{sb.get('Sharpe', np.nan):.2f}"]],
              ["시나리오", "CAGR", "Sharpe"], ["l", "r", "r"],
              title="R1 누수 자가검정 — 고의로 미래를 넣으면 반드시 좋아져야 한다")
    ok_a = np.isfinite(sa.get("CAGR", np.nan)) and np.isfinite(base_c) and \
        sa["CAGR"] > base_c + 0.10
    ok_b = np.isfinite(sb.get("CAGR", np.nan)) and np.isfinite(base_c) and sb["CAGR"] > base_c
    passed = bool(ok_a and ok_b)
    detail = (f"미래수익 주입 CAGR {sa.get('CAGR', np.nan):.2%} vs 기준 {base_c:.2%} "
              f"({'개선' if ok_a else '개선 없음 ← 하네스 고장'}) · "
              f"신호 선행 {sb.get('CAGR', np.nan):.2%} ({'개선' if ok_b else '개선 없음'})")
    _record("R1", "누수 자가검정", passed, detail, kill=(not ok_a),
            numbers={"base": base_c, "inject": sa.get("CAGR"), "shift": sb.get("CAGR")})


# ═══ R12 — 꼬리 동시손실 (이 전략 고유, 필수) ════════════════════════════════════════════════
CRISIS_WINDOWS = [("2018Q4 긴축", "2018-10-01", "2018-12-31"),
                  ("2020Q1 코로나", "2020-02-01", "2020-04-30"),
                  ("2022 긴축", "2022-01-01", "2022-10-31"),
                  ("2024-08 급락", "2024-07-15", "2024-08-15")]


def R12_tail_correlation(bt: dict, bench: Dict[str, pd.Series], P: pd.DataFrame) -> dict:
    """위기 국면에 전 포지션이 동시에 손실난다 — 그 크기를 사전에 측정하고 상한을 확정한다."""
    r = _series(bt)
    if not len(r):
        _record("R12", "꼬리 동시손실", None, "수익률 시계열이 비어 판정 불가")
        return {}
    mkt = None
    for k in ("KOSPI", "유니버스 동일가중", "KOSDAQ"):
        if k in bench and bench[k] is not None and len(bench[k].dropna()) > 20:
            mkt = bench[k].reindex(r.index)
            break
    out = {}
    rows = []
    if mkt is not None:
        q05 = mkt.quantile(0.05)
        tail = r[mkt <= q05]
        calm = r[mkt > mkt.quantile(0.25)]
        out["tail_mean"] = float(tail.mean()) if len(tail) else np.nan
        out["tail_worst"] = float(tail.min()) if len(tail) else np.nan
        out["calm_mean"] = float(calm.mean()) if len(calm) else np.nan
        rows.append(["시장 하위5% 주간", f"{len(tail)}주", f"{out['tail_mean']:+.2%}",
                     f"{out['tail_worst']:+.2%}"])
        rows.append(["평시(상위75%)", f"{len(calm)}주", f"{out['calm_mean']:+.2%}", "-"])

    # 보유 종목 간 상관: 위기 vs 평시
    H = bt.get("holdings")
    corr_crisis = corr_calm = np.nan
    if H is not None and len(H):
        piv = H.pivot_table(index="wk", columns="code", values="ret", aggfunc="mean")
        if mkt is not None and piv.shape[1] >= 3:
            mk = mkt.reindex(piv.index)
            def _mean_corr(sub):
                if len(sub) < 5 or sub.shape[1] < 3:
                    return np.nan
                c = sub.corr(min_periods=3).to_numpy(dtype=float)
                iu = np.triu_indices_from(c, k=1)
                v = c[iu]
                v = v[np.isfinite(v)]
                return float(v.mean()) if len(v) else np.nan
            corr_crisis = _mean_corr(piv[mk <= mk.quantile(0.05)])
            corr_calm = _mean_corr(piv[mk > mk.quantile(0.25)])
            rows.append(["보유종목 평균상관", "위기", f"{corr_crisis:.2f}", f"평시 {corr_calm:.2f}"])
    out["corr_crisis"], out["corr_calm"] = corr_crisis, corr_calm

    for name, s, e in CRISIS_WINDOWS:
        sub = r[(r.index >= as_ts(s)) & (r.index <= as_ts(e))]
        if len(sub):
            cum = float((1 + sub).prod() - 1)
            rows.append([f"위기구간 {name}", f"{len(sub)}주", f"{cum:+.2%}", ""])
            out[f"crisis_{name}"] = cum
    LOG.table(rows, ["구간", "표본", "성과/상관", "비고"], ["l", "r", "r", "l"],
              title="R12 ⭐ 꼬리 동시손실 — 위험 프리미엄의 대가를 사전에 측정한다")

    s = _stat(bt)
    mdd = s.get("MDD", np.nan)
    worst_crisis = min([v for k, v in out.items() if k.startswith("crisis_")] or [np.nan])
    # 종목당 상한 권고: 위기구간 손실이 MDD 예산(-35%)을 넘으면 비례 축소
    MDD_BUDGET = -0.35
    rec_cap = POS_MAX_WEIGHT
    if np.isfinite(mdd) and mdd < MDD_BUDGET:
        rec_cap = round(max(0.03, POS_MAX_WEIGHT * abs(MDD_BUDGET / mdd)), 3)
    verdict = (f"MDD {mdd:.2%} · 위기구간 최악 {worst_crisis:+.2%} · "
               f"보유종목 상관 위기 {corr_crisis:.2f} vs 평시 {corr_calm:.2f} → "
               f"종목당 비중 상한 현재 {POS_MAX_WEIGHT:.0%}"
               + (f", 권고 {rec_cap:.1%} (MDD 예산 {MDD_BUDGET:.0%} 초과)"
                  if rec_cap != POS_MAX_WEIGHT else " 유지 (MDD 예산 내)"))
    if np.isfinite(corr_crisis) and np.isfinite(corr_calm) and corr_crisis > corr_calm + 0.1:
        verdict += " · 꼬리에서 상관 상승은 이 전략의 예상된 성질이다(§0-1)"
    out["recommended_pos_max"] = rec_cap
    _record("R12", "꼬리 동시손실 ⭐", (np.isfinite(mdd) and mdd >= MDD_BUDGET), verdict,
            numbers=out)
    return out


# ═══ R3 — 팩터 직교화 ═══════════════════════════════════════════════════════════════════════
def _factor_returns(P: pd.DataFrame) -> pd.DataFrame:
    """패널에서 직접 주간 팩터 수익률을 만든다(외부 팩터 라이브러리 의존 없음).
    각 팩터 = 유니버스 내 상위 20% - 하위 20% 동일가중 다음주 수익률."""
    d = P[(P.get("in_band", 1) == 1)].copy()
    if "fwd_ret" not in d.columns or d.empty:
        return pd.DataFrame()
    d["mom"] = d["f_dd"]                    # 252일 고점 대비 낙폭 = 모멘텀의 부호 있는 대리
    if "size_est" not in d.columns:
        d = build_size_estimate(d)
    d["size"] = -d["size_est"]                # 소형주일수록 큰 값 (밴드·셀과 동일 척도)
    d["value"] = safe_div(col(d, "equity"), d["mcap"])            # 장부/시가 (B/M)
    d["lowvol"] = d["f_vol"]                # f_vol = -표준편차 → 클수록 저변동
    facs = {}
    for f in ("mom", "size", "value", "lowvol"):
        if f not in d.columns or not d[f].notna().any():
            continue
        q = d.groupby("wk", observed=True)[f].rank(pct=True)
        hi = d[q >= 0.8].groupby("wk", observed=True)["fwd_ret"].mean()
        lo = d[q <= 0.2].groupby("wk", observed=True)["fwd_ret"].mean()
        facs[f] = (hi - lo)
    mkt = d.groupby("wk", observed=True)["fwd_ret"].mean()
    facs["mkt"] = mkt
    return pd.DataFrame(facs)


def R3_orthogonal(bt: dict, P: pd.DataFrame) -> None:
    r = _series(bt)
    F = _factor_returns(P)
    if F.empty or not len(r):
        _record("R3", "팩터 직교화", None, "팩터 구성 실패 — 판정 보류")
        return
    idx = r.index.intersection(F.index)
    if len(idx) < 30:
        _record("R3", "팩터 직교화", None, f"공통 표본 {len(idx)}주로 부족 — 판정 보류")
        return
    y = r.reindex(idx).fillna(0).to_numpy(dtype=float)
    X = F.reindex(idx).fillna(0.0)
    Xv = np.column_stack([np.ones(len(idx)), X.to_numpy(dtype=float)])
    try:
        beta, *_ = np.linalg.lstsq(Xv, y, rcond=None)
        resid = y - Xv @ beta
    except Exception:
        _record("R3", "팩터 직교화", None, "회귀 실패 — 판정 보류")
        return
    alpha_w = float(beta[0])
    alpha_ann = (1 + alpha_w) ** PERIODS_PER_YEAR - 1
    _mu, t = hac_tstat(resid + alpha_w)
    names = ["절편(알파)"] + list(X.columns)
    LOG.table([[n, f"{b:+.5f}"] for n, b in zip(names, beta)], ["항", "계수(주간)"], ["l", "r"],
              title="R3 팩터 직교화 — 시장·모멘텀·규모·가치·저변동성 통제 후 남는 것")
    ok = (alpha_ann > 0.02) and (abs(t) >= 1.5)
    _record("R3", "팩터 직교화 후 알파 잔존", bool(ok),
            f"연환산 알파 {alpha_ann:+.2%}, HAC t={t:.2f}" +
            ("" if ok else " → 기존 팩터의 재포장일 가능성(§11-6)"),
            kill=False, numbers={"alpha_ann": alpha_ann, "t": t})


# ═══ R5 — 절제 ══════════════════════════════════════════════════════════════════════════════
def R5_ablation(P: pd.DataFrame, run_fn: Callable, base_stat: dict) -> pd.DataFrame:
    arms = []

    def _arm(label: str, pp: pd.DataFrame):
        s = _stat(run_fn(pp, label=label))
        arms.append({"arm": label, "CAGR": s.get("CAGR"), "MDD": s.get("MDD"),
                     "Sharpe": s.get("Sharpe"), "Calmar": s.get("Calmar"),
                     "평균종목수": s.get("평균종목수"),
                     "ΔCAGR": (s.get("CAGR", np.nan) - base_stat.get("CAGR", np.nan))})

    # 1) TP 4개 각각 제거
    for c in TP_COLS:
        rest = [x for x in TP_COLS if x != c]
        _arm(f"TP제거:{c}", assemble_score(P, use_tps=rest))
    # 2) f_cr_pctl 임계
    for th in (0.10, 0.20, 0.30):
        _arm(f"cr_pctl<{th:.2f}", assemble_score(classify_phase(P, cr_enter=th)))
    # 3) f_dd 임계
    for th in (-0.20, -0.30, -0.40):
        _arm(f"dd<{th:+.2f}", assemble_score(classify_phase(P, dd_enter=th)))
    # 4) 국면 C 게이트 on/off
    _arm("국면C게이트 off", assemble_score(P, gate_phase=False))
    # 5) 방화벽 off / 거부권 off
    _arm("방화벽 off", assemble_score(P, gate_firewall=False))
    _arm("거부권 off", assemble_score(P, gate_veto=False))
    # 6) TP 방식: clip vs rank×rank
    _arm("TP=rank×rank(clip없음)", assemble_score(build_tps(P, method="raw")))

    A = pd.DataFrame(arms)
    if len(A):
        rows = [[r["arm"], f"{r['CAGR']:.2%}" if pd.notna(r["CAGR"]) else "-",
                 f"{r['MDD']:.2%}" if pd.notna(r["MDD"]) else "-",
                 f"{r['Sharpe']:.2f}" if pd.notna(r["Sharpe"]) else "-",
                 f"{r['ΔCAGR']:+.2%}" if pd.notna(r["ΔCAGR"]) else "-",
                 f"{r['평균종목수']:.1f}" if pd.notna(r["평균종목수"]) else "-"]
                for r in arms]
        rows.insert(0, ["기준(전체)", f"{base_stat.get('CAGR', np.nan):.2%}",
                        f"{base_stat.get('MDD', np.nan):.2%}",
                        f"{base_stat.get('Sharpe', np.nan):.2f}", "0.00%",
                        f"{base_stat.get('평균종목수', np.nan):.1f}"])
        LOG.table(rows, ["절제 arm", "CAGR", "MDD", "Sharpe", "ΔCAGR", "평균종목수"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="R5 절제 — 무엇이 실제로 기여하는가 (ΔCAGR<0 이면 그 요소가 기여한 것)")
    _record("R5", "절제 검사", None,
            f"{len(arms)}개 arm 측정 — 기여 귀속표는 위 표 및 r5_ablation.csv 참조")
    return A


# ═══ R7 — 레짐 분할 ═════════════════════════════════════════════════════════════════════════
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    r = _series(bt)
    if not len(r):
        _record("R7", "레짐 분할", None, "표본 없음")
        return
    rows = []
    for y, g in r.groupby(r.index.year):
        b = bench.get("KOSPI")
        bench_y = float((1 + b.reindex(g.index).fillna(0)).prod() - 1) if b is not None else np.nan
        rows.append([str(y), f"{len(g)}주", f"{float((1+g).prod()-1):+.2%}",
                     f"{bench_y:+.2%}" if np.isfinite(bench_y) else "-"])
    LOG.table(rows, ["연도", "주수", "전략", "KOSPI"], ["c", "r", "r", "r"],
              title="R7 레짐 분할 — 특정 구간 의존성을 숨기지 않는다")
    yr = [float((1 + g).prod() - 1) for _y, g in r.groupby(r.index.year)]
    pos = sum(1 for v in yr if v > 0)
    _record("R7", "레짐 분할", None,
            f"{len(yr)}개 연도 중 {pos}개 연도 플러스 · 최악 {min(yr):+.2%} / 최고 {max(yr):+.2%}")


# ═══ R9 — 회전율·비용 3시나리오 ═════════════════════════════════════════════════════════════
def R9_capacity(P: pd.DataFrame, run_fn: Callable) -> None:
    rows = []
    res = {}
    for lab, k in (("낙관(k=0.05)", 0.05), ("기본(k=0.10)", SLIPPAGE_K),
                   ("비관(k=0.25)", 0.25), ("최악(k=0.40)", 0.40)):
        s = _stat(run_fn(P, label=f"R9_{lab}", slip_k=k))
        res[lab] = s
        rows.append([lab, f"{s.get('CAGR', np.nan):.2%}", f"{s.get('MDD', np.nan):.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}",
                     f"{s.get('주평균비용', np.nan)*1e4:.1f}bp",
                     f"{s.get('주평균회전율', np.nan):.2f}"])
    LOG.table(rows, ["시나리오", "CAGR", "MDD", "Sharpe", "주평균비용", "주평균회전율"],
              ["l", "r", "r", "r", "r", "r"],
              title="R9 회전율·비용 시나리오 — 소액계좌에서 실제로 실행 가능한가")
    pess = res.get("비관(k=0.25)", {}).get("CAGR", np.nan)
    ok = np.isfinite(pess) and pess > 0.0
    _record("R9", "비용 비관 시나리오", bool(ok),
            f"비관 시나리오 CAGR {pess:.2%}" + ("" if ok else " → 실행 불가 판정(§11-7)"),
            numbers={"pessimistic_cagr": pess})


# ═══ 국면 C 표본 충분성 (§11-8) ═════════════════════════════════════════════════════════════
def check_phase_sample(P: pd.DataFrame) -> pd.DataFrame:
    if "phase" not in P.columns:
        return pd.DataFrame()
    d = P.copy()
    d["year"] = d["wk"].dt.year
    dist = (d.groupby(["year", "phase"], observed=True)["code"].nunique()
             .unstack("phase").fillna(0).astype(int))
    for c in ("A", "B", "C"):
        if c not in dist.columns:
            dist[c] = 0
    LOG.table([[str(y)] + [f"{int(dist.loc[y, c]):,}" for c in ("A", "B", "C")]
               for y in dist.index],
              ["연도", "국면A(물타기)", "국면B(반대매매중)", "국면C(소진·진입)"],
              ["c", "r", "r", "r"],
              title="국면 분포 — 국면 C 진입 후보가 연평균 몇 종목인가 (§11-8)")
    mean_c = float(dist["C"].mean()) if len(dist) else 0.0
    _record("SAMPLE", "국면 C 표본 충분성", bool(mean_c >= 30),
            f"연평균 국면C 종목수 {mean_c:.1f}개" +
            ("" if mean_c >= 30 else " → 30개 미만. 임계 완화 후 재측정 대상(§11-8). "
                                     "단, 완화는 사람이 결정한다 — 코드가 몰래 바꾸지 않는다"))
    return dist.reset_index()


def report_robustness():
    LOG.banner("강건성 스위트 종합", "킬 기준(⭐)은 §11. 나쁜 결과를 좋게 보이도록 조정하지 않는다")
    rows = []
    for r in ROBUST_RESULTS:
        icon = "✔ PASS" if r["pass"] else ("✘ FAIL" if r["pass"] is False else "→ 정보")
        rows.append([r["id"], _trunc(r["name"], 34), icon, _trunc(r["detail"], 74)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=78)
    fails = [r for r in ROBUST_RESULTS if r["pass"] is False]
    if fails:
        LOG.warn(f"실패 {len(fails)}건: " + ", ".join(r["id"] for r in fails))
