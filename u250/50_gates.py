# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §6.3 판정 게이트 G1~G7 + §6.2 다중검정(DSR/PBO)                                          ║
# ║                                                                                          ║
# ║  전부 통과해야 '유효'다. 하나라도 실패하면 실패로 기록하고, 통과시키기 위해 명세를          ║
# ║  고치지 않는다(§7 MASTER_SCORECARD 필수 포함 사항).                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

from math import erf, sqrt as _sqrt


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / _sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """역정규 (Acklam 근사). scipy 의존을 피한다 — 이 코드는 어디서든 돌아야 한다."""
    p = min(max(float(p), 1e-12), 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = _sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = _sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe(ret: pd.Series, n_trials: int, ppy: float) -> dict:
    """Bailey & López de Prado (2014). 시행수는 반드시 §6.2 의 전체값(120)을 쓴다."""
    r = pd.Series(ret).dropna().to_numpy(dtype=float)
    T = len(r)
    if T < 12 or r.std(ddof=1) == 0:
        return dict(sr=np.nan, sr0=np.nan, dsr=np.nan, excess=np.nan, T=T)
    sr = float(r.mean() / r.std(ddof=1))                       # 주기 단위 SR
    g3 = float(pd.Series(r).skew())
    g4 = float(pd.Series(r).kurt() + 3.0)
    #   시행 N개 중 최대 SR 의 기대값 (귀무: 진짜 SR=0)
    euler = 0.5772156649
    e1 = _norm_ppf(1 - 1.0 / n_trials)
    e2 = _norm_ppf(1 - 1.0 / (n_trials * math.e))
    var_sr = 1.0 / _sqrt(max(T - 1, 1))                        # 귀무 하에서의 SR 표준편차 근사
    sr0 = var_sr * ((1 - euler) * e1 + euler * e2)
    denom = _sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    z = (sr - sr0) * _sqrt(max(T - 1, 1)) / denom
    return dict(sr=sr * _sqrt(ppy), sr0=sr0 * _sqrt(ppy), dsr=_norm_cdf(z),
                excess=float(sr - sr0), T=T)


def pbo_cscv(R: pd.DataFrame, n_blocks: int = 16) -> dict:
    """CSCV — 변형(variant) 들 사이에서 IS 최우수가 OOS 중앙 아래로 떨어질 확률.

    R: index=시점, columns=변형. 팩터 하나의 격자 전체(5×3×2=30)를 넣는다.
    """
    R = R.dropna(how="all").fillna(0.0)
    T, K = R.shape
    if K < 2 or T < n_blocks * 3:
        return dict(pbo=np.nan, n_comb=0, K=K, T=T)
    n_blocks = int(n_blocks) - (int(n_blocks) % 2)
    edges = np.array_split(np.arange(T), n_blocks)
    X = R.to_numpy(dtype=float)
    bs = np.array([X[e].sum(axis=0) for e in edges])            # (B, K)
    bq = np.array([(X[e] ** 2).sum(axis=0) for e in edges])
    bn = np.array([len(e) for e in edges], dtype=float)

    from itertools import combinations
    idx = list(range(n_blocks))
    combos = list(combinations(idx, n_blocks // 2))
    if len(combos) > 20000:
        rng = np.random.default_rng(SEED)
        combos = [combos[i] for i in rng.choice(len(combos), 20000, replace=False)]

    def _sharpe(sel):
        s, q, n = bs[list(sel)].sum(0), bq[list(sel)].sum(0), bn[list(sel)].sum()
        mu = s / n
        var = np.maximum(q / n - mu ** 2, 1e-18)
        return mu / np.sqrt(var)

    logits = []
    for cmb in combos:
        oos = tuple(i for i in idx if i not in cmb)
        s_is, s_oos = _sharpe(cmb), _sharpe(oos)
        best = int(np.argmax(s_is))
        rank = float((s_oos <= s_oos[best]).sum()) / K          # 상대 순위 (1=최고)
        w = min(max(rank, 1.0 / (K + 1)), 1 - 1.0 / (K + 1))
        logits.append(math.log(w / (1 - w)))
    lg = np.array(logits)
    return dict(pbo=float((lg <= 0).mean()), n_comb=len(combos), K=K, T=T,
                logit_median=float(np.median(lg)))


# ── 게이트 판정 ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    gate: str
    passed: Optional[bool]
    value: str
    criterion: str
    note: str = ""


def excess_cagr(res: BTResult, base: BTResult, ppy: float) -> float:
    return res.stats(ppy)["cagr"] - base.stats(ppy)["cagr"]


def yearly_excess(res: BTResult, base: BTResult) -> pd.Series:
    a, b = res.yearly(), base.yearly()
    return (a - b.reindex(a.index)).dropna()


def gate_G1(res: BTResult, null: dict, ppy: float) -> GateResult:
    if null is None or not len(null.get("cagr", [])):
        return GateResult("G1", None, "—", "B4 무작위 분포 상위 5% 밖", "귀무분포 없음")
    c = res.stats(ppy)["cagr"]
    pct = float((null["cagr"] < c).mean())
    return GateResult("G1", bool(c > null["p95"]), f"{c:.2%} (분위 {pct:.1%})",
                      f"> B4 p95 = {null['p95']:.2%}")


def gate_G2(res: BTResult, b2: BTResult, ppy: float) -> GateResult:
    x = excess_cagr(res, b2, ppy)
    return GateResult("G2", bool(x >= SPEC_GATE["g2_excess_cagr"]), f"{x:+.2%}p",
                      f"≥ +{SPEC_GATE['g2_excess_cagr']:.1%}p (AUM 1억)")


def gate_G3(res: BTResult, b2: BTResult) -> GateResult:
    ye = yearly_excess(res, b2)
    if not len(ye):
        return GateResult("G3", None, "—", "연도별 초과 중앙값>0 & 최고2년 제외 후 >0")
    med = float(ye.median())
    k = SPEC_GATE["g3_drop_best_years"]
    trimmed = ye.sort_values(ascending=False).iloc[k:] if len(ye) > k else pd.Series(dtype=float)
    tm = float(trimmed.mean()) if len(trimmed) else np.nan
    ok = bool(med > 0 and np.isfinite(tm) and tm > 0)
    return GateResult("G3", ok, f"중앙 {med:+.2%}p · 최고{k}년제외 평균 {tm:+.2%}p",
                      "중앙값>0 이고 최고 2년 제외 후에도 >0")


def gate_G4(is_x: float, oos_x: float) -> GateResult:
    if not np.isfinite(oos_x) or not np.isfinite(is_x):
        return GateResult("G4", None, "—", f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}",
                          "OOS 미개봉")
    if is_x <= 0:
        return GateResult("G4", False, f"IS {is_x:+.2%}p", "IS 초과수익이 없어 판정 불가 → 실패")
    return GateResult("G4", bool(oos_x >= is_x * SPEC_GATE["g4_oos_ratio"]),
                      f"IS {is_x:+.2%}p → OOS {oos_x:+.2%}p ({oos_x/is_x:.0%})",
                      f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}")


def gate_G5(dsr: dict, pbo: dict) -> GateResult:
    d, p = dsr.get("dsr", np.nan), pbo.get("pbo", np.nan)
    if not np.isfinite(d) or not np.isfinite(p):
        return GateResult("G5", None, "—", "DSR>0 · PBO<0.5", "표본 부족")
    ok = bool(d > SPEC_GATE["g5_dsr_min"] and p < SPEC_GATE["g5_pbo_max"])
    strict = bool(dsr.get("excess", -1) > 0 and p < SPEC_GATE["g5_pbo_max"])
    return GateResult("G5", ok, f"DSR {d:.3f} · PBO {p:.3f} · SR−SR₀ {dsr.get('excess', np.nan):+.4f}",
                      f"DSR > {SPEC_GATE['g5_dsr_min']} · PBO < {SPEC_GATE['g5_pbo_max']}",
                      f"엄격판정(SR>SR₀ 기준) = {'통과' if strict else '실패'}")


def gate_G6(quint: Dict[int, BTResult], kind: str, ppy: float) -> GateResult:
    if kind == "filter":
        return GateResult("G6", None, "—", "5분위 단조 감소 (랭킹형 한정)", "필터형 — 해당 없음")
    if not quint or len(quint) < 5:
        return GateResult("G6", None, "—", "5분위 단조 감소", "분위 구성 실패")
    c = [quint[q].stats(ppy)["cagr"] for q in sorted(quint, reverse=True)]   # Q5→Q1
    mono = all(c[i] >= c[i + 1] for i in range(len(c) - 1))
    return GateResult("G6", bool(mono), " → ".join(f"{x:.1%}" for x in c),
                      "상위→하위 단조 감소")


def gate_G7(p1: float, p2: float, p3: float, base_x: float) -> GateResult:
    """P1·P2 는 초과수익이 소멸해야 하고, P3 는 유지되어야 한다."""
    tol = max(0.3 * abs(base_x), 0.005)
    r1 = np.isfinite(p1) and abs(p1) < tol
    r2 = np.isfinite(p2) and abs(p2) < tol
    r3 = np.isfinite(p3) and p3 > 0
    ok = bool(r1 and r2 and r3)
    return GateResult("G7", ok,
                      f"P1 {p1:+.2%}p{'✓' if r1 else '✗'} · P2 {p2:+.2%}p{'✓' if r2 else '✗'} · "
                      f"P3 {p3:+.2%}p{'✓' if r3 else '✗'}",
                      f"P1·P2 소멸(|초과|<{tol:.2%}p) & P3 유지(>0)")


# ── 플라시보 생성기 ─────────────────────────────────────────────────────────────────────────
def placebo_shift(fs: FactorSignal, rebals: pd.DatetimeIndex) -> FactorSignal:
    """P1 — 신호 발생일을 −60영업일 시프트. 진짜 신호라면 초과수익이 사라져야 한다."""
    if not len(fs.sig):
        return fs
    s = fs.sig.copy()
    shifted = pd.to_datetime(s["rebal"]) + pd.tseries.offsets.BDay(SPEC_GATE["g7_placebo_shift_bdays"])
    grid = pd.DatetimeIndex(rebals)
    pos = grid.searchsorted(shifted.to_numpy(), side="left")
    pos = np.clip(pos, 0, len(grid) - 1)
    s["rebal"] = grid[pos]
    return FactorSignal(fs.factor, fs.variant + "|P1", fs.obs, s.drop_duplicates(["code", "rebal"]),
                        fs.kind, "P1 −60영업일 시프트")


def placebo_shuffle(fs: FactorSignal, univ_by_t: Dict[pd.Timestamp, List[str]]) -> FactorSignal:
    """P2 — 신호 라벨을 종목 간 무작위 셔플. 발생 빈도(시점별 신호 종목수)는 보존한다."""
    if not len(fs.sig):
        return fs
    rng = np.random.default_rng(SEED + 7)
    rows = []
    for t, g in fs.sig.groupby("rebal", observed=True):
        pool = list(univ_by_t.get(t, []))
        if not pool:
            continue
        k = min(len(g), len(pool))
        pick = rng.choice(len(pool), k, replace=False)
        sc = g["score"].to_numpy()[:k]
        for j, i in enumerate(pick):
            rows.append((pool[i], t, float(sc[j])))
    s = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    return FactorSignal(fs.factor, fs.variant + "|P2", fs.obs, s, fs.kind, "P2 라벨 셔플")


def placebo_matched(fs: FactorSignal, univ: pd.DataFrame, sec: pd.DataFrame) -> FactorSignal:
    """P3 — 신호 종목과 시총·업종·거래대금이 매칭된 대조군. 이 대조군 대비로도 이겨야 한다."""
    if not len(fs.sig):
        return fs
    ind = sec.drop_duplicates("code").set_index("code").get("industry")
    U = univ[univ["u250"]][["rebal", "code", "market_cap", "adv20"]].copy()
    U["industry"] = U["code"].map(ind) if ind is not None else ""
    rng = np.random.default_rng(SEED + 13)
    rows = []
    for t, g in fs.sig.groupby("rebal", observed=True):
        pool = U[U["rebal"] == t]
        if not len(pool):
            continue
        tgt = pool[pool["code"].isin(set(g["code"]))]
        cand = pool[~pool["code"].isin(set(g["code"]))]
        if not len(tgt) or not len(cand):
            continue
        for _, r in tgt.iterrows():
            c2 = cand[cand["industry"] == r["industry"]] if r["industry"] else cand
            if not len(c2):
                c2 = cand
            #   시총·거래대금 로그거리 최소 종목을 짝지운다 (동률은 난수로)
            d = (np.log1p(c2["market_cap"]) - np.log1p(r["market_cap"])).abs() + \
                (np.log1p(c2["adv20"]) - np.log1p(r["adv20"])).abs()
            d = d + rng.random(len(d)) * 1e-6
            rows.append((c2.loc[d.idxmin(), "code"], t, 1.0))
    s = pd.DataFrame(rows, columns=["code", "rebal", "score"]).drop_duplicates(["code", "rebal"])
    return FactorSignal(fs.factor, fs.variant + "|P3", fs.obs, s, fs.kind, "P3 매칭 대조군")
