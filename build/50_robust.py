

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트 R1~R11 (§11)                                                            ║
# ║                                                                                          ║
# ║  순서대로 실행. 앞 단계 실패 시 진행 금지.                                                  ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§16.3). 나쁜 결과는 그 자체로 정보다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: "OrderedDict[str, dict]" = OrderedDict()


def _record(rid: str, name: str, passed: Optional[bool], detail: str,
            kill: bool = False, metrics: Optional[dict] = None):
    # ★ numpy bool 주의: np.False_ is False → False 다. `is False` 로 분기하면 킬 게이트가
    #   조용히 발동하지 않는다. 여기서 파이썬 bool 로 강제 변환한다.
    passed = None if passed is None else bool(passed)
    ROBUST_RESULTS[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                           "kill": kill, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[passed]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → {icon} · {detail}")
    if passed is False and kill and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name} — {detail}")


def _sharpe(R: pd.DataFrame) -> float:
    s = perf_stats(R)
    return float(s.get("Sharpe", np.nan)) if s else np.nan


# ── R1. 누수 민감도 자가검정 (C9) — 이 검정 통과 전 모든 백테스트 결과는 무효 ────────────────
def R1_leakage(P: pd.DataFrame, months, uni, sec, run_fn) -> None:
    """파이프라인이 누수를 '탐지할 수 있는지' 먼저 증명한다 (C9).

    두 부분으로 나눈다. 한쪽만으로는 결론이 나지 않기 때문이다:

      R1a 하네스 민감도 (판정의 기준)
          미래수익을 직접 신호로 심은 '고의 오염본'을 만든다. 이건 정의상 완벽한 누수다.
          이때도 성과가 뚜렷이 좋아지지 않으면 하네스가 신호에 반응하지 못하는 것 =
          체결·정렬·수익계산 어딘가가 고장난 것이다. 이 경우 전략 결과는 전부 무효다.

      R1b 실제 신호 선행 (참고)
          실제 신호를 1개월 앞당겨 본다. 개선되면 정상. 개선되지 않는 경우는 두 가지인데
          ① 하네스 둔감 ② 애초에 신호에 알파가 거의 없음 — 구분이 안 된다.
          그래서 R1b 는 판정에 쓰지 않고 참고로만 기록한다. (R1a 가 ①을 이미 배제한다)
    """
    base = run_fn(P, label="R1_base")
    s0 = _sharpe(base["returns"])

    # R1a: 미래수익을 신호에 주입 (고의 누수)
    Oracle = P.copy()
    ora = Oracle.groupby("month", observed=True)["fwd_ret"].rank(pct=True)
    Oracle["Signal_rank"] = ora.where(ora.notna(), Oracle["Signal_rank"])
    oracle_bt = run_fn(Oracle, label="R1_oracle")
    s_ora = _sharpe(oracle_bt["returns"])

    # 포지션이 아예 잡히지 않으면 '하네스 둔감'이 아니라 '게이트가 전부 막았다'는 뜻이다.
    # 두 원인은 처방이 완전히 다르므로 구분해서 보고한다.
    n_pos = float(base["returns"]["n"].mean()) if len(base["returns"]) else 0.0
    n_pos_ora = float(oracle_bt["returns"]["n"].mean()) if len(oracle_bt["returns"]) else 0.0
    if n_pos_ora < 0.5:
        _record("R1", "누수 민감도 자가검정 (C9)", None,
                f"평균 보유종목이 {n_pos_ora:.2f}개로 포지션이 사실상 잡히지 않아 판정할 수 없습니다. "
                f"하네스 문제가 아니라 게이트 문제입니다 — 위 '유니버스 감쇠 감사'에서 "
                f"거부권/하한선 중 어디서 표본이 0이 되는지 먼저 확인하세요.",
                kill=False, metrics={"n_pos": n_pos, "n_pos_oracle": n_pos_ora})
        LOG.error("R1 판정불가 — 포지션이 0입니다. 강건성 결과 전체가 무의미하므로 "
                  "게이트(특히 하한선)를 먼저 진단해야 합니다.")
        return
    sensitive = np.isfinite(s_ora) and np.isfinite(s0) and (s_ora - s0) > 0.5

    # R1b: 실제 신호 1개월 선행
    Q = P.sort_values(["code", "month"]).copy()
    for c in ("Signal_rank", "Signal", "E", "U"):
        if c in Q.columns:
            Q[c] = Q.groupby("code", observed=True)[c].shift(-1)
    s1 = _sharpe(run_fn(Q, label="R1_leaked")["returns"])

    _record("R1", "누수 민감도 자가검정 (C9)", sensitive,
            f"[R1a 하네스 민감도] 정상 Sharpe {s0:.3f} → 미래수익 주입 오염본 {s_ora:.3f} "
            f"(Δ={s_ora-s0:+.3f}). "
            + ("하네스가 누수에 뚜렷이 반응함 = 정상. 이제 실제 결과를 신뢰할 근거가 생겼습니다."
               if sensitive else
               "★ 완벽한 누수를 넣어도 성과가 개선되지 않습니다 → 하네스가 신호에 반응하지 못합니다. "
               "체결 정렬(익일 시가)·수익 계산·유니버스 결합 중 하나가 고장난 것이며, "
               "§15-1에 따라 이 상태의 백테스트 결과는 전부 무효입니다.")
            + f"  [R1b 참고] 실제 신호 1개월 선행 시 {s1:.3f} (Δ={s1-s0:+.3f})"
            + ("" if (s1 - s0) > 0.15 else
               " — 개선되지 않았으나, R1a 가 통과했다면 이는 '신호 자체의 알파가 약하다'는 뜻이지 "
               "누수 탐지 실패가 아닙니다." if sensitive else ""),
            kill=False,
            metrics={"sharpe_base": s0, "sharpe_oracle": s_ora, "sharpe_shifted": s1})
    if not sensitive:
        LOG.error("R1a 실패 — §15-1: 하네스가 누수에 둔감하므로 이후 모든 결과가 무효입니다. "
                  "전략을 손대기 전에 백테스트 엔진부터 고쳐야 합니다.")


# ── R2. TP vs 나이브 ⭐ 킬 게이트 — 이 시스템의 존재 이유를 검정한다 ─────────────────────────
def R2_tp_vs_naive(P: pd.DataFrame, run_fn) -> None:
    """TP = z(개선) × z(대가회피) 가 z(개선) 단독보다 낫지 않다면,
    트레이드오프 논리 전체가 불필요한 복잡도다. 정면으로 검정하고 있는 그대로 보고한다."""
    # ★ 두 팔의 '축 개수'를 맞춘다. 하한선은 "보유한 축이 모두 50th 이상"이라 축이 많을수록
    #   기하급수적으로 좁아진다(축 k개면 대략 0.5^k). TP 팔에 원시 TP 13개, 나이브 팔에
    #   원지표 7개를 넣으면 유니버스 폭이 1.68% 대 7.13% 로 벌어져서, 신호 품질이 아니라
    #   유니버스 폭 차이를 재게 된다. TP 쪽의 올바른 '축'은 팩 단위 집계인 E_* 컬럼이고,
    #   그게 본선이 실제로 쓰는 구성이기도 하다 — 검정 대상과 운용 대상이 일치해야 한다.
    tp_cols = [p["E_col"] for p in active_packs() if p["E_col"] in P.columns] + \
              [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    if not tp_cols:                       # E_* 가 없으면 원시 TP 로 폴백
        for p in active_packs():
            tp_cols += [c for c in p["tp_cols"] if c in P.columns]
        tp_cols += [c for c in ("TP_B1", "TP_B2", "TP_C1", "TP_C2") if c in P.columns]
    # 나이브 = '개선 항목 단독' (곱의 첫 인자에 해당하는 원지표들)
    naive_cols = [c for c in ("n1", "p1", "x1", "q1", "dlog_rev", "dlog_IC", "dlog_emp")
                  if c in P.columns]
    if not tp_cols or not naive_cols:
        _record("R2", "TP vs 나이브", None, "비교할 컬럼이 부족합니다.")
        return

    # ── 각 팔은 '자기 증거'로 하한선까지 다시 만든다 ──────────────────────────────────────
    #   ★ 예전엔 두 팔이 본선의 FLOOR 컬럼을 그대로 물려받았다. 그런데 FLOOR 는 전부 TP 에서
    #     파생된 값이라, '나이브 팔'조차 TP 로 선별된 종목만 보게 된다. 실측하면 FLOOR 하나가
    #     종목 선정의 92.4% 를 끝내 버려서, TP 팔과 '균등난수 팔'의 보유종목 자카드 유사도가
    #     0.73 이었다. 무엇과도 구별하지 못하는 게이트는 킬 게이트가 아니다.
    #     각 팔이 자기 증거로 하한선을 만들면 자카드가 0.64 → 0.14 로 떨어지고 비교가 성립한다.
    def _arm(cols: Sequence[str], label: str):
        A = P.copy()
        Z = pd.DataFrame({c: xsec_z_l(A, c) for c in cols}, index=A.index)
        A["E_raw"] = nanmean_cols(Z, list(cols))
        A["E"] = xsec_rank_pct_l(A, A["E_raw"])
        A["FLOOR"] = compute_floor(A, cols)
        A["Signal"] = A["E"].fillna(0) * A["U"].fillna(0) * A["VETO"].fillna(0) * A["FLOOR"]
        A["Signal_rank"] = (A.groupby("month", observed=True)["Signal"]
                             .rank(pct=True, method="average"))
        return A, run_fn(A, label=label)

    Q, tp_bt = _arm(tp_cols, "R2_TP")
    N, nv_bt = _arm(naive_cols, "R2_naive")

    f_tp, f_nv = float(Q["FLOOR"].mean()), float(N["FLOOR"].mean())
    LOG.info(f"R2 각 팔의 하한선 잔존율 — TP {f_tp*100:.2f}% · 나이브 {f_nv*100:.2f}% "
             f"(두 팔이 각자의 증거로 하한선을 만듭니다)")
    if not (0.5 <= f_nv / max(f_tp, 1e-9) <= 2.0):
        LOG.warn(f"두 팔의 유니버스 폭이 {f_nv/max(f_tp,1e-9):.2f}배로 벌어졌습니다. "
                 f"이 비교는 신호 품질이 아니라 유니버스 폭 차이를 재고 있을 수 있습니다 — "
                 f"아래 판정을 그만큼 할인해서 읽으십시오.")

    a, b = tp_bt["returns"]["ret"].fillna(0).to_numpy(), nv_bt["returns"]["ret"].fillna(0).to_numpy()
    k = min(len(a), len(b))
    diff = a[:k] - b[:k]
    mu, t = hac_tstat(diff)
    s_tp, s_nv = _sharpe(tp_bt["returns"]), _sharpe(nv_bt["returns"])
    better = np.isfinite(t) and t > 1.0 and s_tp > s_nv
    _record("R2", "TP vs 나이브 (킬 게이트)", better,
            f"TP Sharpe {s_tp:.3f} vs 나이브 {s_nv:.3f} · 월수익 차이 평균 {mu*100:+.3f}%p, "
            f"HAC t={t:.2f}. " + ("트레이드오프 논리가 나이브를 유의하게 이깁니다." if better else
                                  "★ TP 가 '개선 항목 단독'을 이기지 못했습니다. "
                                  "§15-2에 따라 트레이드오프 패러다임의 근거가 소멸합니다. "
                                  "유리하게 해석하지 않고 그대로 보고합니다."),
            kill=True, metrics={"sharpe_tp": s_tp, "sharpe_naive": s_nv, "t_diff": t})

    # ── R2b 하니스 자체 검정: TP 가 '무정보 균등난수'는 이겨야 한다 ────────────────────────
    #   이건 전략이 아니라 '비교 장치'를 검정한다. 만약 난수 팔이 TP 와 비슷한 성과를 내면
    #   위 R2 판정은 신호가 아니라 선별 게이트가 만든 것이고, 그 순간 R2 는 아무것도 판정하지
    #   못한다. 실제로 하한선을 공유하던 시절엔 난수 팔이 TP 팔과 자카드 0.73 이었다.
    Z = P.copy()
    Z["_noise"] = np.random.default_rng(SEED).random(len(Z))
    Z["E"] = xsec_rank_pct_l(Z, Z["_noise"])
    Z["FLOOR"] = compute_floor(Z, tp_cols)          # 유니버스 폭은 TP 팔과 동일하게 맞춘다
    Z["Signal"] = Z["E"].fillna(0) * Z["U"].fillna(0) * Z["VETO"].fillna(0) * Z["FLOOR"]
    Z["Signal_rank"] = Z.groupby("month", observed=True)["Signal"].rank(pct=True, method="average")
    s_rd = _sharpe(run_fn(Z, label="R2_noise")["returns"])
    _record("R2b", "TP vs 무정보 난수 (하니스 검정)", bool(s_tp > s_rd),
            f"TP Sharpe {s_tp:.3f} vs 균등난수 {s_rd:.3f}. " +
            ("비교 장치가 신호와 무신호를 구별합니다 — R2 판정을 신뢰할 수 있습니다."
             if s_tp > s_rd else
             "★ TP 가 무정보 난수조차 이기지 못했습니다. 이 경우 위 R2 판정은 신호가 아니라 "
             "선별 게이트(하한선·거부권)가 만든 것입니다. R2 결과를 그대로 믿지 마십시오."),
            metrics={"sharpe_tp": s_tp, "sharpe_random": s_rd})


# ── R3. 퀄리티 팩터 직교화 ─────────────────────────────────────────────────────────────────
def R3_orthogonal(P: pd.DataFrame, bt: dict, months) -> None:
    """표준 퀄리티/수익성/모멘텀에 회귀한 뒤 알파가 남는가. 안 남으면 재포장에 불과하다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        _record("R3", "퀄리티 팩터 직교화", None, "보유 이력이 없어 판정 불가")
        return
    Q = P.copy()
    Q["f_prof"] = safe_div(col(Q, "op_income_ttm"), col(Q, "assets"))
    Q["f_qual"] = safe_div(col(Q, "equity"), col(Q, "assets"))
    Q["f_mom"] = Q.groupby("code", observed=True)["close"].transform(lambda s: s.pct_change(12))
    Q["f_size"] = np.log(Q["adv20"].where(Q["adv20"] > 0))
    Q["f_val"] = safe_div(col(Q, "net_income_ttm"), Q["close"])
    facs = ["f_prof", "f_qual", "f_mom", "f_size", "f_val"]

    fac_ret = []
    for m in months:
        sub = Q[Q["month"] == m]
        if len(sub) < 30:
            continue
        row = {"month": m}
        for f in facs:
            z = xsec_z(sub[f], sub["cell"])
            r = sub["fwd_ret"]
            ok = z.notna() & r.notna()
            row[f] = float(np.average(r[ok], weights=np.clip(z[ok] - z[ok].min() + 1e-9, 0, None))
                           - r[ok].mean()) if ok.sum() > 10 else np.nan
        fac_ret.append(row)
    F = pd.DataFrame(fac_ret).set_index("month") if fac_ret else pd.DataFrame()
    R = bt["returns"].set_index("month")["ret"]
    if F.empty:
        _record("R3", "퀄리티 팩터 직교화", None, "팩터 수익률을 만들 표본이 부족합니다.")
        return
    J = F.join(R.rename("y"), how="inner").dropna()
    if len(J) < 24:
        _record("R3", "퀄리티 팩터 직교화", None, f"공통 표본 {len(J)}개월로 부족합니다.")
        return
    X = np.column_stack([np.ones(len(J))] + [J[f].to_numpy() for f in facs])
    y = J["y"].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    alpha_m, t = hac_tstat(resid + beta[0])
    passed = np.isfinite(t) and t > 1.5 and alpha_m > 0
    _record("R3", "퀄리티 팩터 직교화", passed,
            f"직교화 후 월알파 {alpha_m*100:+.3f}%p (연 {((1+alpha_m)**12-1)*100:+.1f}%), "
            f"HAC t={t:.2f}, 표본 {len(J)}개월. "
            + ("표준 팩터로 설명되지 않는 알파가 남습니다." if passed else
               "★ 직교화 후 알파가 사라집니다 — 기존 퀄리티 팩터의 재포장일 가능성이 큽니다(§15-3)."),
            kill=True, metrics={"alpha_m": alpha_m, "t": t})


# ── R4. 플라시보 매핑 ───────────────────────────────────────────────────────────────────────
def R4_placebo(P: pd.DataFrame, n_iter: int = 1000) -> None:
    """무작위로 종목-신호를 섞었을 때의 귀무분포. 실제가 상위 5% 밖이면 매핑이 무작위와 구분 안 됨."""
    sub = P[P["Signal_rank"].notna() & P["fwd_ret"].notna()]
    if len(sub) < 500:
        _record("R4", "플라시보 매핑", None, "표본 부족")
        return
    real = []
    for m, g in sub.groupby("month", observed=True):
        if len(g) < 20:
            continue
        k = max(1, int(len(g) * PORTFOLIO_TOP_PCT))
        real.append(g.nlargest(k, "Signal_rank")["fwd_ret"].mean() - g["fwd_ret"].mean())
    real_mu = float(np.nanmean(real)) if real else np.nan

    rng = np.random.default_rng(SEED)
    null = np.empty(n_iter)
    groups = [g for _, g in sub.groupby("month", observed=True) if len(g) >= 20]
    for i in range(n_iter):
        acc = []
        for g in groups:
            k = max(1, int(len(g) * PORTFOLIO_TOP_PCT))
            idx = rng.choice(len(g), size=k, replace=False)
            acc.append(g["fwd_ret"].to_numpy()[idx].mean() - g["fwd_ret"].mean())
        null[i] = np.nanmean(acc)
    p = float((null >= real_mu).mean())
    passed = np.isfinite(real_mu) and p < 0.05
    _record("R4", f"플라시보 (무작위 선택 귀무분포 {n_iter:,}회)", passed,
            f"실제 초과 {real_mu*100:+.3f}%p/월 vs 귀무 평균 {null.mean()*100:+.3f}%p "
            f"(p={p:.4f}). " + ("무작위와 구분됩니다." if passed else
                                "★ 무작위 선택과 통계적으로 구분되지 않습니다(§15-5)."),
            kill=False, metrics={"p": p, "real": real_mu})


# ── R10. 정책 반증 검정 ⭐ 전 팩 필수 ───────────────────────────────────────────────────────
def R10_policy_falsify(P: pd.DataFrame, cal: pd.DataFrame, months, run_fn) -> None:
    """정책 이벤트 ±6개월 구간을 전부 제외하고 백테스트. 알파가 유지돼야 통과."""
    packs = [p["id"] for p in active_packs()]
    mask = policy_windows(cal, packs, months, halo_months=6)
    clean_months = months[~mask.to_numpy()]
    if len(clean_months) < 24:
        _record("R10", "정책 반증 검정", None,
                f"정책구간 제외 후 {len(clean_months)}개월밖에 남지 않아 검정력이 없습니다. "
                f"이 자체가 '이 팩의 관측구간이 정책에 광범위하게 덮여 있다'는 사실을 뜻합니다.")
        return
    full = run_fn(P, label="R10_full")
    Q = P[P["month"].isin(clean_months)].copy()
    clean = run_fn(Q, label="R10_clean", months_override=clean_months)
    s_full, s_clean = _sharpe(full["returns"]), _sharpe(clean["returns"])
    mu_f = full["returns"]["ret"].mean()
    mu_c = clean["returns"]["ret"].mean()
    _, t_c = hac_tstat(clean["returns"]["ret"].fillna(0).to_numpy())
    kept = np.isfinite(s_clean) and s_clean > 0 and mu_c > 0 and (
        not np.isfinite(s_full) or s_clean >= 0.5 * s_full)

    # 검정 A: 정책 시행일 근처 신호 발화율 스파이크
    fire = P.groupby("month", observed=True)["Signal_rank"].apply(
        lambda s: float((s > 0.95).mean()) if len(s) else np.nan).reindex(months)
    in_w, out_w = fire[mask.to_numpy()].mean(), fire[~mask.to_numpy()].mean()

    _record("R10", "정책 반증 검정 (검정 C: 이벤트 ±6M 제외)", kept,
            f"전체 Sharpe {s_full:.3f}({len(months)}개월) → 정책구간 제외 {s_clean:.3f}"
            f"({len(clean_months)}개월, 월평균 {mu_c*100:+.3f}%p, HAC t={t_c:.2f}). "
            f"[검정A] 신호 발화율 정책구간 {in_w:.3f} vs 비정책구간 {out_w:.3f}. "
            + ("정책 이벤트를 빼도 알파가 유지됩니다." if kept else
               "★ 정책 이벤트 구간을 제외하면 알파가 사라집니다 → 해당 센서팩 폐기 대상(§15-4). "
               "이것은 수요가 아니라 제도를 관측한 것입니다."),
            kill=False, metrics={"s_full": s_full, "s_clean": s_clean, "fire_in": in_w, "fire_out": out_w})
    if not kept:
        for p in active_packs():
            disable_pack(p["id"], "R10 정책 반증 검정 미통과 — 자동 비활성화")


# ── R5. 절제 (ablation) ─────────────────────────────────────────────────────────────────────
def R5_ablation(P: pd.DataFrame, run_fn) -> None:
    """팩별·TP별로 하나씩 빼고 돌려 기여를 귀속한다. L2 만 건드리므로 몇 분이면 끝난다."""
    packs = active_packs()
    all_e = [p["E_col"] for p in packs if p["E_col"] in P.columns] + \
            [c for c in ("E_AXB", "E_AXC") if c in P.columns]

    # ★ 기준선도 절제팔과 똑같이 score_from_axes 를 통과시킨다.
    #   예전엔 기준선은 본선 컬럼을 그대로 쓰고 절제팔만 별도 식으로 점수를 다시 만들었다.
    #   그러면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를 잰다. 실제로
    #   아무것도 빼지 않은 널-절제의 ΔSharpe 가 +2.08 로 나왔다(0.000 이어야 한다).
    def _score_arm(cols: Sequence[str], label: str):
        A = P.copy()
        S = score_from_axes(A, cols)
        for k in ("E_raw", "E", "FLOOR", "Signal", "pack_profile", "Signal_rank"):
            A[k] = S[k]
        return _sharpe(run_fn(A, label=label)["returns"])

    s0 = _score_arm(all_e, "R5_base")
    rows = [["(전체)", f"{s0:.3f}", "—", "—"]]
    for drop in all_e:
        rest = [c for c in all_e if c != drop]
        if len(rest) < MIN_FLOOR_AXES:
            # 남은 축이 하한선 최소개수보다 적으면 FLOOR 가 전원 탈락한다 — 절제가 아니라
            # 유니버스 전멸이므로 Δ를 기여도로 읽으면 안 된다. 건너뛰되 표에 남긴다.
            rows.append([f"− {drop}", "—", "—",
                         f"측정 불가 (잔여 축 {len(rest)}개 < 하한선 최소 {MIN_FLOOR_AXES}개)"])
            continue
        s = _score_arm(rest, f"R5_no_{drop}")
        rows.append([f"− {drop}", f"{s:.3f}", f"{s - s0:+.3f}",
                     "기여함" if s < s0 - 0.03 else ("무기여" if s > s0 + 0.03 else "중립")])
    LOG.table(rows, ["절제 대상", "Sharpe", "Δ", "판정"], ["l", "r", "r", "l"],
              title="R5 절제 검사 — 어느 축이 실제로 기여하는가")
    _record("R5", "팩별·축별 절제", True, f"기준 Sharpe {s0:.3f} 대비 축별 기여 귀속 완료")


# ── R6. PBO / DSR ───────────────────────────────────────────────────────────────────────────
def _dsr(sharpe: float, n: int, skew: float, kurt: float, n_trials: int) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado)."""
    if not np.isfinite(sharpe) or n < 12:
        return np.nan
    try:
        from scipy.stats import norm
        e = 0.5772156649
        sr0 = math.sqrt(2 * math.log(max(n_trials, 2))) * (1 - e) + e * math.sqrt(
            2 * math.log(max(n_trials, 2) * math.e))
        sr0 = sr0 * (1.0 / math.sqrt(n))
        denom = math.sqrt(max(1e-12, 1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe ** 2))
        return float(norm.cdf((sharpe - sr0) * math.sqrt(n - 1) / denom))
    except Exception:
        return np.nan


def R6_pbo_dsr(bt: dict, n_trials: int = 12) -> None:
    from scipy import stats as _st
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    n = len(r)
    if n < 24:
        _record("R6", "PBO / DSR", None, "표본 부족")
        return
    sr_m = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    dsr = _dsr(sr_m, n, float(_st.skew(r)), float(_st.kurtosis(r, fisher=False)), n_trials)

    # PBO (CSCV, 축약형): 시계열을 S 조각으로 나눠 IS/OOS 순위 역전 빈도
    S = 8
    if n >= S * 6:
        idx = np.array_split(np.arange(n), S)
        losses = 0
        combos = 0
        for i in range(S):
            oos = idx[i]
            iss = np.concatenate([idx[j] for j in range(S) if j != i])
            if len(oos) < 3 or len(iss) < 6:
                continue
            combos += 1
            m_is, m_oos = r[iss].mean(), r[oos].mean()
            if m_is > 0 and m_oos <= 0:
                losses += 1
        pbo = losses / combos if combos else np.nan
    else:
        pbo = np.nan
    passed = (np.isfinite(dsr) and dsr > 0.90) and (not np.isfinite(pbo) or pbo < 0.5)
    _record("R6", "PBO / DSR", passed,
            f"DSR={dsr:.3f} (>0.90 권장, 시행횟수 {n_trials} 가정) · PBO={pbo:.3f} (<0.5 권장). "
            + ("과적합 위험 낮음." if passed else "과적합 위험이 낮지 않습니다 — 파라미터 수를 줄이세요."),
            metrics={"dsr": dsr, "pbo": pbo})


# ── R7. 레짐 분할 ───────────────────────────────────────────────────────────────────────────
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    R = bt["returns"].set_index("month")["ret"]
    rows = []
    ks = bench.get("KOSPI")
    if ks is not None:
        up = ks.reindex(R.index) > 0
        for lab, m in (("강세(코스피↑)", up), ("약세(코스피↓)", ~up)):
            x = R[m.fillna(False)]
            if len(x) >= 6:
                rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                             f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    # 전·후반 구간 (PACK-C 밸류업 레짐 판정의 근거)
    half = len(R) // 2
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        if len(x) >= 6:
            rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                         f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    pre24 = R[R.index < as_ts("2024-01-01")]
    post24 = R[R.index >= as_ts("2024-01-01")]
    LOG.table(rows, ["레짐", "월수", "월평균", "연변동성", "승률"], ["l", "r", "r", "r", "r"],
              title="R7 레짐 분할")
    verdict = ""
    if len(pre24) >= 12 and len(post24) >= 6:
        verdict = (f"2024년 이전 월평균 {pre24.mean()*100:+.3f}%p / 이후 {post24.mean()*100:+.3f}%p. ")
        if "C" in ACTIVE_PACKS:
            if pre24.mean() <= 0:
                verdict += ("★ 밸류업(2024~) 이전 구간에서 알파가 0 이하입니다 → "
                            "이것은 구조적 알파가 아니라 정책 베팅입니다(§6.1 레짐 경고).")
            else:
                verdict += "밸류업 이전 구간에서도 알파가 양(+)이므로 정책 베팅으로만 보기는 어렵습니다."
    _record("R7", "레짐 분할", True, verdict or "레짐별 성과 공개 완료")


# ── R8. 하위기간 안정성 ─────────────────────────────────────────────────────────────────────
def R8_subperiod(bt: dict) -> None:
    R = bt["returns"].copy()
    R["year"] = R["month"].dt.year
    rows = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        rows.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%", f"{g['ret'].mean()*100:+.3f}%p",
                     f"{(g['ret']>0).mean()*100:.0f}%", f"{g['n'].mean():.1f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수"],
              ["c", "r", "r", "r", "r", "r"], title="R8 연도별 분해")
    yrs = [float(r[2].rstrip("%")) for r in rows]
    pos = sum(1 for v in yrs if v > 0)
    _record("R8", "하위기간 안정성", True,
            f"{pos}/{len(yrs)}개 연도 양(+). 최악 {min(yrs):+.1f}% / 최고 {max(yrs):+.1f}%")


# ── R9. 회전율·용량 ─────────────────────────────────────────────────────────────────────────
def R9_capacity(P: pd.DataFrame, run_fn) -> None:
    gross = run_fn(P, label="R9_gross", apply_costs=False)
    net = run_fn(P, label="R9_net", apply_costs=True)
    sg, sn = _sharpe(gross["returns"]), _sharpe(net["returns"])
    mg = gross["returns"]["ret"].mean()
    mn = net["returns"]["ret"].mean()
    survives = np.isfinite(sn) and sn > 0 and mn > 0
    _record("R9", "회전율·비용 차감 후 생존", survives,
            f"비용 전 Sharpe {sg:.3f}(월 {mg*100:+.3f}%p) → 비용 후 {sn:.3f}(월 {mn*100:+.3f}%p). "
            f"월평균 회전율 {net['returns']['turnover'].mean():.2f}, "
            f"월평균 비용 {net['returns']['cost'].mean()*100:.3f}%p. "
            + ("비용 차감 후에도 성과가 남습니다." if survives else
               "★ 비용 차감 후 성과가 소멸합니다 — 개인 소액계좌에서 실행 불가(§15-7)."),
            kill=False, metrics={"sharpe_gross": sg, "sharpe_net": sn})


# ── R11. 팩 간 상관 ─────────────────────────────────────────────────────────────────────────
def R11_pack_corr(P: pd.DataFrame) -> None:
    cols = [p["E_col"] for p in active_packs() if p["E_col"] in P.columns] + \
           [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    if len(cols) < 2:
        _record("R11", "팩 간 상관", None, "활성 축이 2개 미만이라 판정 불가")
        return
    C = P[cols].corr(min_periods=200)
    rows = [[c] + [f"{C.loc[c, d]:+.2f}" if pd.notna(C.loc[c, d]) else "—" for d in cols] for c in cols]
    LOG.table(rows, ["축"] + cols, ["l"] + ["r"] * len(cols), title="R11 팩 간 상관행렬")
    hi = [(a, b, C.loc[a, b]) for i, a in enumerate(cols) for b in cols[i+1:]
          if pd.notna(C.loc[a, b]) and abs(C.loc[a, b]) > 0.7]
    _record("R11", "팩 간 상관", len(hi) == 0,
            "중복 축 없음" if not hi else
            "높은 상관: " + ", ".join(f"{a}~{b}={v:+.2f}" for a, b, v in hi) + " → 통합 검토 필요")


def report_robustness():
    LOG.banner("강건성 검사 요약 (R1~R11)", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    order = ["R1", "R2", "R3", "R4", "R10", "R5", "R11", "R6", "R7", "R8", "R9"]
    rows = []
    for rid in order:
        r = ROBUST_RESULTS.get(rid)
        if not r:
            rows.append([rid, "—", "미실행", ""])
            continue
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid + ("⭐" if r["kill"] else ""), _trunc(r["name"], 26), icon,
                     _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)
    fails = [r for r in ROBUST_RESULTS.values() if r["pass"] is False]
    kills = [r for r in fails if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§15 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("모든 강건성 검사 통과.")
