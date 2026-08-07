

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  R-SUITE  강건성 (§9)                                                                      ║
# ║                                                                                          ║
# ║  순서대로. 앞 단계 실패 시 판정을 KILL 로 기록한다.                                        ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§11). 나쁜 결과는 그 자체로 정보다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: List[dict] = []
ABLATION_RETURNS: "OrderedDict[str, pd.Series]" = OrderedDict()


def _rec(rid: str, name: str, verdict: str, detail: str, metric: str = "",
         kill: bool = False):
    ROBUST.append({"id": rid, "name": name, "verdict": verdict, "metric": metric,
                   "detail": detail, "kill": kill})
    icon = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "INFO": "·", "SKIP": "→"}.get(verdict, "?")
    (LOG.error if verdict == "FAIL" else LOG.warn if verdict == "WARN" else LOG.ok)(
        f"{icon} [{rid}] {name} — {verdict}  {metric}")
    if detail:
        LOG.info(f"    {detail}")


def _cagr(bt) -> float:
    return float(perf_stats(bt["returns"]).get("CAGR", np.nan))


def _calmar(bt) -> float:
    return float(perf_stats(bt["returns"]).get("Calmar", np.nan))


def _sharpe(bt) -> float:
    return float(perf_stats(bt["returns"]).get("Sharpe", np.nan))


def _holdings_set(bt) -> Dict[pd.Timestamp, set]:
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    return {m: set(g["code"]) for m, g in H.groupby("month")}


def _jaccard(a: dict, b: dict) -> float:
    ks = set(a) & set(b)
    if not ks:
        return np.nan
    vals = []
    for k in ks:
        u = a[k] | b[k]
        if u:
            vals.append(len(a[k] & b[k]) / len(u))
    return float(np.mean(vals)) if vals else np.nan


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R0 — S1 기준선 재측정  ⭐ 가장 싸고 가장 결정적
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R0_baseline(P: pd.DataFrame, months, sec, runner) -> dict:
    """§9 R0.

    ★ 정직성 고지: 이 문서에는 "S1_HARD_FIREWALL_ONLY 규칙"의 정의가 없다. 정의 없이
      '재구현'을 주장하면 그 자체가 날조다. 그래서 우리는 **이 하네스 안에서 완전히
      정의된** 세 개의 기준선을 같은 유니버스·같은 비용모델·같은 기간으로 측정하고,
      그중 '방화벽(거부권)만 쓰고 스코어는 쓰지 않는' 팔을 S1 의 가장 자연스러운 해석으로
      지정한다. 해석이라는 사실을 리포트에 명시한다.

    ★ 과거 대화의 "S1 10년 CAGR 17%" 는 오류로 확인되었다. 어디에도 하드코딩하지 않는다.
    """
    out = {}
    # B1: U-MID 동일가중 — "아무것도 하지 않는다"
    b1 = runner(P, label="B1_umid_equal", signal="equal", floor=False, veto=False)
    # B2: 거부권만 (하드 방화벽) + 유동성 상위 — S1 해석
    b2 = runner(P, label="B2_firewall_only", signal="equal", floor=False, veto=True)
    # B3: 단순 퀄리티 (GP/A 상위) — "재포장이 아닌가"의 사전 점검
    b3 = runner(P, label="B3_quality_gpa", signal="q_gpa", floor=False, veto=True)
    for k, bt in (("B1_UMID_동일가중", b1), ("B2_거부권만(S1 해석)", b2), ("B3_퀄리티GPA", b3)):
        out[k] = perf_stats(bt["returns"])
    rows = []
    for k, s in out.items():
        rows.append([k, f"{s.get('CAGR', np.nan):+.2%}", f"{s.get('MDD', np.nan):+.1%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('Calmar', np.nan):.2f}",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
    LOG.table(rows, ["기준선", "CAGR", "MDD", "Sharpe", "Calmar", "t(HAC)"],
              ["l", "r", "r", "r", "r", "r"],
              title="R0 — S1 기준선 재측정 (기억 속 숫자 사용 금지 · 동일 하네스 실측)")
    LOG.info("※ S1_HARD_FIREWALL_ONLY 의 규칙은 이 문서에 정의되어 있지 않습니다. "
             "B2(거부권만 적용, 스코어 미사용)를 가장 자연스러운 해석으로 지정했으며, "
             "이것이 해석이라는 사실을 명시합니다. 이후 문서의 공통 기준선은 B2 의 실측값입니다.")
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R1 — 누수 자가검정 (이중 대조군)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R1_leakage(P: pd.DataFrame, months, sec, runner, base_bt) -> None:
    """§9 R1.

    DART 공시는 결산기준일 대비 45~90일 후행한다. knowledge_date 를 -30일 앞당겨도 여전히
    결산일 이후라 성과가 개선되지 않고, 구현자는 정상 하네스를 '고장났다'고 오판한다.
    대조군 2개를 모두 쓴다:
      (a) 재무 knowledge_date -120일  → 뚜렷한 개선이 나와야 정상
      (b) 미래 3개월 수익률을 신호로 직접 주입 → 극적 개선이 나와야 정상
    (b)에서도 개선이 없으면 백테스트 엔진 자체가 고장난 것이다. 전 결과 무효.
    """
    base = _cagr(base_bt)
    # (b) 먼저 한다 — 가장 결정적이고 가장 싸다.
    P2 = P.copy()
    fwd3 = (P2.sort_values(["code", "month"]).groupby("code", observed=True)["fwd_ret"]
            .transform(lambda s: s.shift(-1).rolling(3, min_periods=1).sum()))
    P2["_oracle"] = fwd3
    bt_b = runner(P2, label="R1b_oracle", signal="_oracle", floor=True, veto=True)
    cb = _cagr(bt_b)
    jb = _jaccard(_holdings_set(base_bt), _holdings_set(bt_b))
    # 하한선이 선정을 지배하면 신호를 바꿔도 보유가 안 변한다 — 그 경우를 분리해서 본다.
    bt_b_nofloor = runner(P2, label="R1b_oracle_nofloor", signal="_oracle", floor=False, veto=True)
    cb2 = _cagr(bt_b_nofloor)
    ok_b = np.isfinite(cb) and np.isfinite(base) and (cb > base + 0.10)
    ok_b2 = np.isfinite(cb2) and np.isfinite(base) and (cb2 > base + 0.10)
    if ok_b or ok_b2:
        _rec("R1b", "미래수익률 직접 주입", "PASS",
             f"신호를 미래 3개월 수익률로 바꾸면 성과가 뛴다 = 신호가 실제로 선정을 움직인다. "
             f"보유종목 자카드 {jb:.2f} (낮을수록 신호가 지배적).",
             f"기준 {base:+.2%} → 오라클 {cb:+.2%} (하한선 해제 시 {cb2:+.2%})")
        if not ok_b and ok_b2:
            _rec("R1b*", "하한선 지배 경고", "WARN",
                 "하한선을 켠 상태에서는 오라클 신호조차 성과를 못 올렸습니다. 하한선이 선정을 "
                 "지배한다는 뜻이고, 그러면 R2·R5 의 신호 비교가 전부 무의미해집니다. "
                 "BREADTH_FLOOR_PCT 를 낮추거나 FLOOR_GROUPS 구성을 재검토하세요.", "")
    else:
        _rec("R1b", "미래수익률 직접 주입", "FAIL",
             "미래 수익률을 신호로 직접 넣었는데도 성과가 개선되지 않습니다. 백테스트 엔진 "
             "자체가 고장난 것입니다(신호→선정→수익 경로가 끊겨 있음). **전 결과 무효**입니다. "
             "§11-3 킬 기준.",
             f"기준 {base:+.2%} → 오라클 {cb:+.2%} / 하한선해제 {cb2:+.2%} · 자카드 {jb:.2f}",
             kill=True)
        return

    # (a) knowledge_date -120일
    kd_cols = [c for c in P.columns if c.startswith("knowledge_date_")]
    if not kd_cols:
        _rec("R1a", "knowledge_date -120일", "SKIP",
             "패널에 knowledge_date_* 컬럼이 없어 오염본을 만들 수 없습니다.", "")
        return
    LOG.info("R1a — 재무 knowledge_date 를 120일 앞당긴 오염본으로 패널을 재조립합니다. "
             "(-30일은 DART 지연보다 작아 아무 변화도 안 나옵니다 — 그래서 -120일입니다)")
    Pa = P.copy()
    # 오염 주입: 재무 as-of 결합을 120일 늦은 시점에서 한 것과 동치가 되도록 month 를 당긴다.
    # 실제 재조립 대신 등가 변환을 쓰는 이유는 L1 재빌드(30분+)를 피하기 위함이다.
    shift_n = 4                                     # 120일 ≈ 4개월
    fin_cols = [c for c in ("i_sales", "i_turn", "i_accr", "i_gpm", "i_capex", "i_roic",
                            "i_ic", "p_payout", "p_invest", "b4_defrev", "i_emp", "i_vapp",
                            "v1_push", "v2_bad") if c in Pa.columns]
    Pa = Pa.sort_values(["code", "month"])
    Pa["_mi"] = _mi(Pa)
    # ★ shift 는 '행'을 옮기지 '달'을 옮기지 않는다. 거래정지·폐지 직전처럼 달이 비면
    #   4행 뒤가 4개월 뒤가 아니다. 그대로 두면 오염 강도가 종목마다 달라져 R1a 의
    #   판정 근거가 흐려진다 — 정확히 4개월 뒤인 행만 오염시킨다.
    ahead_ok = _lag_ok(Pa, -shift_n)
    for c in fin_cols:
        Pa[c] = Pa.groupby("code", observed=True)[c].shift(-shift_n).where(ahead_ok)
    bt_a = runner(Pa, label="R1a_shift120", signal="Signal_rank", floor=True, veto=True)
    ca = _cagr(bt_a)
    if np.isfinite(ca) and np.isfinite(base) and ca > base + 0.02:
        _rec("R1a", "knowledge_date -120일", "PASS",
             "재무를 120일 일찍 알았다고 가정하면 성과가 개선됩니다 = 하네스가 시점에 민감합니다. "
             "즉 정상 경로에서는 미래를 보고 있지 않습니다.",
             f"기준 {base:+.2%} → 오염본 {ca:+.2%} (Δ{ca-base:+.2%}p)")
    else:
        _rec("R1a", "knowledge_date -120일", "WARN",
             "오염본에서 뚜렷한 개선이 나오지 않았습니다. ① 재무 센서의 기여가 원래 작거나 "
             "② 신호가 시점에 둔감하거나 ③ 이미 미래를 보고 있어 더 볼 게 없거나 입니다. "
             "R1b 가 통과했으므로 엔진 고장은 아닙니다. 재무 축의 기여도를 R5 에서 확인하세요.",
             f"기준 {base:+.2%} → 오염본 {ca:+.2%} (Δ{ca-base:+.2%}p)")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R2 — TP vs 나이브  ⭐ 패러다임 근거
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R2_tp_vs_naive(P, months, sec, runner, base_bt) -> None:
    """§9 R2 — TP 가 '개선 항목 단독'보다 유의하게 우수해야 한다.

    ★ 공정성 두 가지를 반드시 맞춘다(v2 는 둘 다 틀려서 판정이 무의미했다):
      ① 두 팔이 **각자의 증거로** 하한선을 만든다. 본선의 FLOOR 를 물려주면 나이브 팔조차
         TP 로 선별된 종목만 보게 되어 자카드 0.73 이 나온다 = 비교가 아니다.
      ② 축 개수를 맞춘다. 하한선은 축수에 지수적이라 6 대 4 면 통과폭이 크게 벌어진다.
    """
    improve_only = ["i_sales", "i_capex", "p_payout", "i_emp"]
    have = [c for c in improve_only if c in P.columns and col(P, c).notna().sum() > 0]
    if not have:
        _rec("R2", "TP vs 나이브", "SKIP", "개선축 센서가 전부 결측입니다.", "")
        return
    bt_tp = runner(P, label="R2_tp", signal="Signal_rank", floor=True, veto=True)
    bt_nv = runner(P, label="R2_naive", signal="naive_improve", floor="naive", veto=True,
                   naive_axes=have)
    s_tp, s_nv = _sharpe(bt_tp), _sharpe(bt_nv)
    c_tp, c_nv = _cagr(bt_tp), _cagr(bt_nv)
    j = _jaccard(_holdings_set(bt_tp), _holdings_set(bt_nv))
    # 유의성: 두 수익률 시계열의 차분에 HAC t
    a = bt_tp["returns"].set_index("month")["ret"]
    b = bt_nv["returns"].set_index("month")["ret"]
    d = (a - b).dropna()
    _, t = hac_tstat(d.to_numpy())

    # R2b 하니스 검정 — TP 가 무정보 난수를 못 이기면 R2 판정 자체를 신뢰하면 안 된다
    rng = np.random.default_rng(SEED)
    Pr = P.copy()
    Pr["_rand"] = rng.random(len(Pr))
    bt_rd = runner(Pr, label="R2b_random", signal="_rand", floor=False, veto=True)
    c_rd = _cagr(bt_rd)

    LOG.table([["TP (본선)", f"{c_tp:+.2%}", f"{s_tp:.2f}"],
               ["나이브 (개선축 단독)", f"{c_nv:+.2%}", f"{s_nv:.2f}"],
               ["무정보 난수 (하니스 검정)", f"{c_rd:+.2%}", f"{_sharpe(bt_rd):.2f}"]],
              ["팔", "CAGR", "Sharpe"], ["l", "r", "r"],
              title="R2 — 트레이드오프 쌍이 '개선 항목 단독'을 이기는가")
    if np.isfinite(c_tp) and np.isfinite(c_rd) and c_tp <= c_rd:
        _rec("R2b", "하니스 검정(TP vs 난수)", "WARN",
             "TP 팔이 무정보 난수 팔을 이기지 못했습니다. 이 상태에서는 R2 판정 자체를 "
             "신뢰하면 안 됩니다 — 신호가 선정을 거의 움직이지 못한다는 뜻입니다.",
             f"TP {c_tp:+.2%} vs 난수 {c_rd:+.2%}")
    if np.isfinite(t) and t > 1.5 and np.isfinite(s_tp) and np.isfinite(s_nv) and s_tp > s_nv:
        _rec("R2", "TP vs 나이브", "PASS",
             f"트레이드오프 쌍이 개선 항목 단독보다 우수합니다. 보유종목 자카드 {j:.2f} "
             f"(높으면 두 팔이 사실상 같은 종목을 본다는 뜻이므로 비교가 약합니다).",
             f"ΔSharpe {s_tp-s_nv:+.2f} · 월수익차 t(HAC) {t:+.2f}")
    else:
        _rec("R2", "TP vs 나이브", "FAIL",
             "TP 가 나이브를 유의하게 이기지 못했습니다. 이 전략의 존재 이유(트레이드오프 논리)의 "
             "근거가 소멸합니다. §11-4 킬 기준입니다 — 파라미터를 조정해 통과시키지 마세요.",
             f"Sharpe TP {s_tp:.2f} vs 나이브 {s_nv:.2f} · t(HAC) {t:+.2f} · 자카드 {j:.2f}",
             kill=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R3 — 퀄리티 팩터 직교화
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R3_orthogonal(P: pd.DataFrame, bt: dict, months) -> None:
    """표준 퀄리티/수익성/모멘텀/규모/가치 팩터로 직교화한 뒤에도 알파가 남는가.

    팩터 수익률은 U-MID 안에서 만든 롱숏 스프레드(상위 30% - 하위 30%, 동일가중)다.
    외부 팩터 데이터를 쓰지 않으므로 어떤 환경에서도 재현된다.
    """
    facs = {"q_gpa": "수익성(GP/A)", "q_roa": "수익성(ROA)", "q_mom": "모멘텀(12-1)",
            "q_size": "규모(logMcap)", "q_bm": "가치(B/M)"}
    use = [f for f in facs if f in P.columns and col(P, f).notna().sum() > 100]
    if not use or bt["returns"].empty:
        _rec("R3", "퀄리티 직교화", "SKIP", "팩터 구성 입력이 부족합니다.", "")
        return
    pool = P[P["u_mid"].astype(bool)] if "u_mid" in P.columns else P
    frets = {}
    for f in use:
        r = (col(pool, f).groupby(pool["month"], observed=True)
             .rank(pct=True, method="average"))
        fw = pool.assign(_r=r, _fr=pd.to_numeric(pool.get("fwd_ret"), errors="coerce"))
        fw = fw.dropna(subset=["_r", "_fr"])
        if fw.empty:
            continue
        hi = fw[fw["_r"] >= 0.7].groupby("month")["_fr"].mean()
        lo = fw[fw["_r"] <= 0.3].groupby("month")["_fr"].mean()
        frets[f] = (hi - lo).reindex(months)
    if not frets:
        _rec("R3", "퀄리티 직교화", "SKIP", "팩터 수익률을 만들지 못했습니다.", "")
        return
    F = pd.DataFrame(frets)
    y = bt["returns"].set_index("month")["ret"].reindex(months)
    D = pd.concat([y.rename("y"), F], axis=1).dropna()
    if len(D) < 24:
        _rec("R3", "퀄리티 직교화", "SKIP", f"공통 관측이 {len(D)}개월로 부족합니다.", "")
        return
    X = np.column_stack([np.ones(len(D))] + [D[c].to_numpy() for c in F.columns])
    beta, *_ = np.linalg.lstsq(X, D["y"].to_numpy(), rcond=None)
    resid = D["y"].to_numpy() - X @ beta
    alpha_m = float(beta[0])
    _, t_a = hac_tstat(resid + alpha_m)
    ann = (1 + alpha_m) ** 12 - 1
    LOG.table([[facs.get(c, c), f"{beta[i+1]:+.3f}"] for i, c in enumerate(F.columns)] +
              [["── 알파(월) ──", f"{alpha_m:+.4f}"], ["알파(연환산)", f"{ann:+.2%}"],
               ["t(HAC)", f"{t_a:+.2f}"]],
              ["팩터", "적재/값"], ["l", "r"],
              title="R3 — 표준 팩터 직교화 후 잔존 알파")
    if np.isfinite(t_a) and t_a > 1.65 and ann > 0:
        _rec("R3", "퀄리티 직교화", "PASS",
             "표준 퀄리티·수익성·모멘텀·규모·가치로 설명되지 않는 알파가 남습니다.",
             f"연환산 알파 {ann:+.2%} · t(HAC) {t_a:+.2f}")
    else:
        _rec("R3", "퀄리티 직교화", "FAIL",
             "표준 팩터로 직교화하면 알파가 사라집니다. 트레이드오프 쌍이 결국 기존 팩터의 "
             "재포장이라는 뜻입니다. §11-5 킬 기준입니다.",
             f"연환산 알파 {ann:+.2%} · t(HAC) {t_a:+.2f}", kill=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R5 — 절제 (기여 귀속) + R6 입력 생성
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R5_ablation(P, months, sec, runner, base_bt) -> pd.DataFrame:
    """§9 R5. L2 만 건드리므로 전부 합쳐 십수 분.

    구성: TP 6개 각각 제거(6) + 유니버스 경계 5 + TP 방식 3 + 하한선 3 = 17개
    ★ 널-절제(아무것도 안 뺀 것)를 반드시 포함하고 Δ가 0 인지 검정한다. v2 는 기준선이
      다른 경로를 타서 널-절제의 ΔSharpe 가 +2.08 이었다(0 이어야 한다).
    """
    cfgs: List[Tuple[str, dict]] = [("널절제(기준)", {})]
    for tid, a, b, need, _ in TP_DEFS:
        cfgs.append((f"−{tid}", {"drop_tp": [tid]}))
    for lo, hi in ((200, 1200), (251, 1400), (300, 1600)):
        cfgs.append((f"랭크{lo}~{hi}", {"uni": ("rank", lo, hi)}))
    for lo, hi in ((0.10, 0.55), (0.15, 0.60)):
        cfgs.append((f"분위{lo:.0%}~{hi:.0%}", {"uni": ("pct", lo, hi)}))
    for mode in ("clip", "rank", "signed"):
        cfgs.append((f"TP방식={mode}", {"tp_mode": mode}))
    for f in (0.40, 0.50, 0.60):
        cfgs.append((f"하한선{f:.0%}", {"floor_pct": f}))

    base_s = _sharpe(base_bt)
    rows = []
    usable: Dict[str, float] = {}
    ABLATION_RETURNS.clear()
    for name, kw in tqdm(cfgs, desc="R5 절제", ncols=88, leave=False):
        try:
            bt = runner(P, label=f"R5:{name}", signal="Signal_rank", floor=True, veto=True, **kw)
        except Exception as e:                                   # noqa
            rows.append([name, "실패", "-", "-", "-", f"{type(e).__name__}"])
            continue
        s = perf_stats(bt["returns"])
        n_hold = float(bt["returns"]["n"].mean()) if len(bt["returns"]) else 0.0
        # ★ 유니버스가 붕괴한 팔은 '성과가 나쁜 구성'이 아니라 **측정 불가**다.
        #   경계를 좁혀 후보가 0~2종목이 되면 Sharpe 는 아무 의미가 없는데, 그걸 범위에
        #   넣으면 '경계 민감도 폭'이 자동으로 커져 정상 전략도 무조건 FAIL 이 된다.
        #   (합성 300종목에서 랭크 300~1600 팔의 유니버스는 정확히 0종목이었다)
        ok = n_hold >= PORTFOLIO_MIN_NAMES
        if ok:
            ABLATION_RETURNS[name] = bt["returns"].set_index("month")["ret"]
            usable[name] = float(s.get("Sharpe", np.nan))
        rows.append([name, f"{s.get('CAGR', np.nan):+.2%}", f"{s.get('Sharpe', np.nan):.2f}",
                     f"{s.get('Sharpe', np.nan) - base_s:+.2f}", f"{n_hold:.1f}",
                     "" if ok else "측정불가(유니버스 붕괴)"])
    LOG.table(rows, ["구성", "CAGR", "Sharpe", "ΔSharpe(본선대비)", "평균종목수", "비고"],
              ["l", "r", "r", "r", "r", "l"], title="R5 — 절제 (기여 귀속)")

    null = next((r for r in rows if r[0] == "널절제(기준)"), None)
    if null and null[3] not in ("-",):
        try:
            dnull = abs(float(str(null[3]).replace("+", "")))
            if dnull > 0.05:
                _rec("R5*", "널절제 정합성", "WARN",
                     "아무것도 빼지 않은 구성의 ΔSharpe 가 0 이 아닙니다. 기준선과 절제팔이 "
                     "서로 다른 경로를 탄다는 뜻이고, 그러면 모든 기여도 숫자를 믿을 수 없습니다.",
                     f"널절제 ΔSharpe {null[3]}")
        except Exception:
            pass

    # 경계 민감도 판정 — §9 R5 는 이 판정을 리포트 첫 페이지에 쓰라고 요구한다
    vals = [v for k, v in usable.items()
            if k.startswith(("랭크", "분위")) and np.isfinite(v)]
    n_dropped = sum(1 for r in rows if r[0].startswith(("랭크", "분위")) and r[-1])
    if n_dropped:
        LOG.warn(f"유니버스 경계 팔 {n_dropped}개가 '측정 불가'(유니버스 붕괴)로 판정에서 "
                 f"제외되었습니다. 조용히 빼지 않고 여기 남깁니다 — 실데이터에서 이 숫자가 "
                 f"크면 밴드 자체가 표본을 감당하지 못한다는 뜻입니다.")
    if len(vals) >= 3:
        rng_ = max(vals) - min(vals)
        if rng_ > max(0.5, 0.5 * abs(base_s if np.isfinite(base_s) else 1.0)):
            _rec("R5-경계", "유니버스 경계 민감도", "FAIL",
                 "유니버스 경계를 흔들었을 때 Sharpe 가 크게 변합니다. 이건 알파가 아니라 "
                 "특정 구간의 우연입니다. (§9 R5 — 이 판정을 리포트 첫 페이지에 씁니다)",
                 f"Sharpe 범위 {min(vals):.2f} ~ {max(vals):.2f} (폭 {rng_:.2f})", kill=True)
        else:
            _rec("R5-경계", "유니버스 경계 민감도", "PASS",
                 "경계를 흔들어도 성과가 급변하지 않습니다.",
                 f"Sharpe 범위 {min(vals):.2f} ~ {max(vals):.2f} (폭 {rng_:.2f})")
    else:
        _rec("R5-경계", "유니버스 경계 민감도", "SKIP",
             f"측정 가능한 경계 팔이 {len(vals)}개뿐이라 민감도를 판정할 수 없습니다. "
             f"경계를 좁히면 유니버스가 붕괴하는 규모라는 뜻입니다 "
             f"(합성 스모크에서는 정상 — 실데이터에서 나오면 표본 자체를 재검토하세요).", "")
    tp_modes = {r[0]: r[2] for r in rows if r[0].startswith("TP방식=")}
    if tp_modes:
        LOG.info(f"§6.5 요구 — TP 방식 비교 결과를 명시합니다: " +
                 " / ".join(f"{k.split('=')[1]} Sharpe {v}" for k, v in tp_modes.items()) +
                 ".  'signed' 는 v2 의 부호버그(z×z)를 재현한 팔입니다. 이것이 clip/rank 보다 "
                 "높게 나온다면 상위 분위가 '급감+악화' 종목으로 오염되었을 때 우연히 좋았다는 "
                 "뜻이므로, 수치가 아니라 의미를 근거로 clip/rank 를 택해야 합니다.")
    return pd.DataFrame(rows, columns=["구성", "CAGR", "Sharpe", "dSharpe", "평균종목수", "비고"])


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R6 — PBO / DSR  (절제 구성 집합 위에서 CSCV · 백테스트 재실행 0회)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R6_pbo(n_split: int = 12, max_comb: int = 20000) -> None:
    """§9 R6 — C7 이 최적화를 금지하므로 파라미터 그리드가 없다.
    → R5 의 절제 구성 집합을 '구성 축'으로 삼아 N_config × T 수익률 행렬 위에서 CSCV.
    """
    if len(ABLATION_RETURNS) < 4:
        _rec("R6", "PBO / DSR", "SKIP", "절제 구성이 4개 미만이라 CSCV 를 할 수 없습니다.", "")
        return
    M = pd.DataFrame(ABLATION_RETURNS).dropna(how="all")
    M = M.dropna(axis=1, how="any")
    if M.shape[1] < 4 or M.shape[0] < 24:
        _rec("R6", "PBO / DSR", "SKIP", f"행렬 {M.shape} 가 너무 작습니다.", "")
        return
    T, N = M.shape
    S = min(n_split, (T // 6) * 2)
    S = S if S % 2 == 0 else S - 1
    if S < 4:
        _rec("R6", "PBO / DSR", "SKIP", f"기간 {T}개월로는 CSCV 분할이 불가능합니다.", "")
        return
    blocks = np.array_split(np.arange(T), S)
    from itertools import combinations
    combos = list(combinations(range(S), S // 2))
    if len(combos) > max_comb:
        rng = np.random.default_rng(SEED)
        combos = [combos[i] for i in rng.choice(len(combos), max_comb, replace=False)]
    X = M.to_numpy(dtype=float)

    def _sr(a):
        s = a.std(ddof=1)
        return a.mean() / s if s > 0 else -np.inf

    lam = []
    for tr in combos:
        tr_idx = np.concatenate([blocks[i] for i in tr])
        te_idx = np.setdiff1d(np.arange(T), tr_idx)
        sr_tr = np.array([_sr(X[tr_idx, j]) for j in range(N)])
        sr_te = np.array([_sr(X[te_idx, j]) for j in range(N)])
        best = int(np.argmax(sr_tr))
        rank = float((sr_te < sr_te[best]).sum()) / max(N - 1, 1)   # 상위일수록 1에 가까움
        w = max(min(rank, 1 - 1e-9), 1e-9)
        lam.append(math.log(w / (1 - w)))
    pbo = float(np.mean(np.array(lam) <= 0))
    LOG.table([["구성 수 (N)", f"{N}"], ["기간 (T개월)", f"{T}"],
               ["CSCV 분할 S", f"{S}"], ["조합 수", f"{len(combos):,}"],
               ["PBO (과최적화 확률)", f"{pbo:.3f}"]],
              ["항목", "값"], ["l", "r"], title="R6 — PBO / CSCV (백테스트 재실행 0회)")
    if pbo <= 0.5:
        _rec("R6", "PBO / DSR", "PASS",
             "학습구간 최우수 구성이 검증구간에서도 중앙값 이상을 유지하는 경우가 더 많습니다. "
             "※ 절제 구성들은 서로 고도로 상관되어 있어 PBO 가 낙관적으로 편향될 수 있습니다 — "
             "이 수치를 단독 근거로 쓰지 마세요.", f"PBO {pbo:.3f}")
    else:
        _rec("R6", "PBO / DSR", "WARN",
             "학습구간 최우수 구성이 검증구간에서 자주 뒤집힙니다. 구성 선택이 표본 내 "
             "우연에 의존한다는 뜻이므로 파라미터를 더 줄이세요.", f"PBO {pbo:.3f}")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R7 · R8 — 레짐 / 연도별
# ═══════════════════════════════════════════════════════════════════════════════════════════
VALUEUP_EVENTS = ["2024-01-24", "2024-02-26", "2024-05-02", "2024-09-24"]


def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    cut = as_ts("2024-01-01")
    segs = [("2024년 이전", R[R["month"] < cut]), ("2024년 이후(밸류업 레짐)", R[R["month"] >= cut])]
    ks = pd.concat([v.rename(k) for k, v in bench.items()], axis=1) if bench else pd.DataFrame()
    rows = []
    for nm, seg in segs:
        if seg.empty:
            continue
        s = perf_stats(seg)
        bmk = ""
        if len(ks):
            b = ks.reindex(seg["month"]).mean(axis=1)
            bmk = f"{((1+b.fillna(0)).prod()**(12/max(len(b),1))-1):+.2%}"
        rows.append([nm, f"{len(seg)}개월", f"{s.get('CAGR', np.nan):+.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('MDD', np.nan):+.1%}", bmk])
    LOG.table(rows, ["레짐", "기간", "CAGR", "Sharpe", "MDD", "시장(연율)"],
              ["l", "c", "r", "r", "r", "r"],
              title="R7 — 레짐 분할 (2024 전후 필수)")
    n_after = int((R["month"] >= cut).sum())
    _rec("R7", "레짐 분할", "INFO",
         f"2024년 이후 표본이 {n_after}개월뿐이라 이 구간 단독의 통계적 검정력은 낮습니다. "
         f"수치는 공개하되 '레짐 의존성 여부'의 결론 근거로 단독 사용하지 마세요. "
         f"TP_P1/TP_P2 의 레짐 의존성은 R10 정책반증으로 별도 판정합니다.", "")


def R8_subperiod(bt: dict) -> None:
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    R["year"] = R["month"].dt.year
    rows = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        rows.append([int(y), f"{len(g)}", f"{cum:+.2%}",
                     f"{float(g['ret'].mean()):+.2%}", f"{float((g['ret'] > 0).mean()):.0%}",
                     f"{float(g['n'].mean()):.1f}", f"{float(g['turnover'].mean()):.2f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수", "회전율"],
              ["c", "r", "r", "r", "r", "r", "r"], title="R8 — 연도별 안정성")
    yr = [float(r[2].rstrip("%")) / 100 for r in rows]
    if yr:
        neg = sum(1 for v in yr if v < 0)
        _rec("R8", "연도별 안정성", "INFO",
             f"손실 연도 {neg}/{len(yr)}년. 최악 {min(yr):+.1%} · 최선 {max(yr):+.1%}. "
             f"소수 연도에 성과가 집중되면 우측꼬리 의존과 결합해 재현성이 낮아집니다.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R9 — 회전율 · 용량
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R9_capacity(P, months, sec, runner, base_bt) -> None:
    """계좌 규모를 키우며 비용 차감 후 성과가 남는지 본다.

    ★ ACCOUNT_KRW=3천만 가정만 보면 참여율이 1e-4 수준이라 슬리피지가 사실상 0 이 되어
      '비용이 없으니 성과가 그대로'라는 무의미한 답이 나온다. 규모를 키워야 검사가 성립한다.
    """
    global ACCOUNT_KRW
    orig = ACCOUNT_KRW
    rows = []
    gross = perf_stats(runner(P, label="R9_nocost", signal="Signal_rank", floor=True,
                              veto=True, costs=False)["returns"])
    rows.append(["비용 미차감", f"{gross.get('CAGR', np.nan):+.2%}",
                 f"{gross.get('Sharpe', np.nan):.2f}", "-", "-"])
    try:
        for amt in (30_000_000, 300_000_000, 3_000_000_000, 30_000_000_000):
            ACCOUNT_KRW = amt
            globals()["ACCOUNT_KRW"] = amt
            bt = runner(P, label=f"R9_{amt}", signal="Signal_rank", floor=True, veto=True)
            s = perf_stats(bt["returns"])
            rows.append([f"{amt/1e8:,.0f}억원", f"{s.get('CAGR', np.nan):+.2%}",
                         f"{s.get('Sharpe', np.nan):.2f}",
                         f"{s.get('월평균비용', np.nan):.4f}",
                         f"{s.get('월평균회전율', np.nan):.2f}"])
    finally:
        ACCOUNT_KRW = orig
        globals()["ACCOUNT_KRW"] = orig
    LOG.table(rows, ["계좌 규모", "CAGR", "Sharpe", "월평균비용", "월평균회전율"],
              ["l", "r", "r", "r", "r"], title="R9 — 회전율 · 용량 (비용 차감 후 성과 잔존)")
    live = [r for r in rows[1:] if r[1] not in ("nan",)]
    try:
        c0 = float(rows[1][1].rstrip("%")) / 100
        _rec("R9", "회전율·용량", "PASS" if c0 > 0 else "FAIL",
             "소액계좌(3천만원)에서 비용 차감 후에도 성과가 남는지가 §11-7 킬 기준입니다. "
             "규모가 커질수록 슬리피지가 성과를 깎는 지점을 위 표에서 확인하세요.",
             f"3천만원 계좌 CAGR {c0:+.2%}", kill=(c0 <= 0))
    except Exception:
        _rec("R9", "회전율·용량", "INFO", "수치 파싱 실패 — 위 표를 직접 확인하세요.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R10 — 정책 반증 (TP_P1 / TP_P2 한정)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R10_policy(P, months, sec, runner, base_bt) -> None:
    """§9 R10 — 밸류업 발표 ±6개월을 제외해도 TP_P1/P2 의 알파가 유지되는가.

    §6.6 경고: 밸류업 프로그램은 2024년 이후다. 10년 중 최근 2년만 현 레짐이다.
    2024년 이전 구간에서 알파가 0 이면 이것은 구조적 알파가 아니라 정책 베팅이다.
    """
    have_p = [t for t, *_ in [(d[0],) for d in TP_DEFS] if t in ("TP_P1", "TP_P2")]
    if not any(t in P.columns or True for t in have_p):
        _rec("R10", "정책 반증", "SKIP", "TP_P1/TP_P2 가 구성되지 않았습니다.", "")
        return
    ev = [as_ts(x) for x in VALUEUP_EVENTS]
    excl = pd.Series(False, index=pd.Index(months, name="month"))
    for e in ev:
        excl |= (pd.Series(months, index=months) >= e - pd.DateOffset(months=6)) & \
                (pd.Series(months, index=months) <= e + pd.DateOffset(months=6))
    keep_months = pd.DatetimeIndex([m for m in months if not bool(excl.get(m, False))])
    pre24 = pd.DatetimeIndex([m for m in months if m < as_ts("2024-01-01")])

    bt_full = runner(P, label="R10_withP", signal="Signal_rank", floor=True, veto=True)
    bt_noP = runner(P, label="R10_noP", signal="Signal_rank", floor=True, veto=True,
                    drop_tp=["TP_P1", "TP_P2"])

    def _sub(bt, idx):
        R = bt["returns"].copy()
        R["month"] = as_ts_series(R["month"])
        return perf_stats(R[R["month"].isin(idx)])

    rows = []
    for lab, idx in (("전체", pd.DatetimeIndex(months)),
                     ("밸류업 ±6M 제외", keep_months),
                     ("2024년 이전만", pre24)):
        a, b = _sub(bt_full, idx), _sub(bt_noP, idx)
        rows.append([lab, f"{len(idx)}개월",
                     f"{a.get('CAGR', np.nan):+.2%}", f"{b.get('CAGR', np.nan):+.2%}",
                     f"{(a.get('CAGR', np.nan) - b.get('CAGR', np.nan)):+.2%}p"])
    LOG.table(rows, ["구간", "기간", "TP_P 포함", "TP_P 제외", "TP_P 기여"],
              ["l", "c", "r", "r", "r"],
              title="R10 — 정책 반증 (밸류업은 2024년 이후 · 그 이전 기여가 0이면 정책 베팅)")
    try:
        pre_contrib = float(rows[2][4].rstrip("p").rstrip("%")) / 100
        if pre_contrib <= 0:
            _rec("R10", "정책 반증", "FAIL",
                 "2024년 이전 구간에서 TP_P1/TP_P2 의 기여가 0 이하입니다. 이건 구조적 알파가 "
                 "아니라 정책 베팅입니다 — 해당 TP 를 폐기하거나 '정책 의존'으로 명시하세요.",
                 f"2024년 이전 TP_P 기여 {pre_contrib:+.2%}p")
        else:
            _rec("R10", "정책 반증", "PASS",
                 "밸류업 레짐 밖에서도 자본배분 TP 의 기여가 양(+)입니다.",
                 f"2024년 이전 TP_P 기여 {pre_contrib:+.2%}p")
    except Exception:
        _rec("R10", "정책 반증", "INFO", "수치 파싱 실패 — 위 표를 직접 확인하세요.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
def report_robustness():
    if not ROBUST:
        return
    LOG.banner("강건성 판정 요약 (§9 · §11 킬 기준)",
               "나쁜 결과는 그대로 보고합니다. 파라미터를 조정해 통과시키지 않습니다.")
    LOG.table([[r["id"], _trunc(r["name"], 26),
                {"PASS": "✔ PASS", "FAIL": "✘ FAIL", "WARN": "⚠ WARN",
                 "INFO": "· INFO", "SKIP": "→ SKIP"}.get(r["verdict"], r["verdict"]),
                _trunc(r["metric"], 40), "⛔ 킬" if r["kill"] else ""]
               for r in ROBUST],
              ["ID", "검사", "판정", "실측", "킬 기준"], ["c", "l", "c", "l", "c"], maxw=42)
    kills = [r for r in ROBUST if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 발동", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
        _safe_print("\n  이 전략은 위 기준에 따라 **폐기 대상**입니다. 결과를 그대로 보고합니다.")
    else:
        LOG.ok("킬 기준에 걸린 항목이 없습니다.")
