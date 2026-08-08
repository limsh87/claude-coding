

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  통계 검증 커널 (§9)                                                                ║
# ║   ① 블록 부트스트랩   ② PBO(CSCV 정식)   ③ DSR(정식)   ④ 워크포워드                       ║
# ║   ⑤ 등가성 검정 TOST  ⑥ 패널 그레인저    ⑦ 이벤트스터디 CAR + 캘린더타임 유의성           ║
# ║                                                                                          ║
# ║  ★ 설계 원칙 — 표본이 부족하면 "판정불가(None)"를 돌려준다. 억지로 숫자를 만들지 않는다.    ║
# ║    p=0.51 을 "거의 유의"로 쓰는 것이 이 프로젝트에서 가장 해로운 행동이다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _sharpe_raw(r: np.ndarray) -> float:
    """기간(월) 단위 Sharpe. 연율화하지 않는다 — DSR 은 원단위 SR 을 쓴다."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return np.nan
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 1e-12 else np.nan


def ann_sharpe(r) -> float:
    s = _sharpe_raw(np.asarray(r, dtype=float))
    return float(s * math.sqrt(12)) if np.isfinite(s) else np.nan


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r, n_iter: int = 1000, block: int = 1, seed: int = SEED,
                    stat: Callable[[np.ndarray], float] = None) -> dict:
    """이동블록 부트스트랩. 월간 수익률의 자기상관을 보존한 채 재표본한다.

    명세는 '블록 21영업일'이라고 쓴다. 월간 시계열에서 21영업일 = 1개월이므로 block=1 이
    명세의 문자 그대로의 해석이고, 그건 사실상 iid 부트스트랩이다. 자기상관이 있으면
    iid 재표본이 신뢰구간을 과소추정하므로 block=3(분기)·6(반기)도 함께 보고한다.
    (블록 길이는 전략 파라미터가 아니라 추론 파라미터다 — 여러 개 보고해도 시행횟수에
     들어가지 않는다. §9-3 DSR 의 시행횟수는 §6.6 격자 12개 그대로다.)
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    stat = stat or (lambda x: float(np.mean(x)))
    if n < 12:
        return {"n": n, "point": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                "p_gt0": np.nan, "block": block, "verdict": "표본 부족(12개월 미만)"}
    rng = np.random.default_rng(seed)
    b = max(1, min(int(block), n))
    n_blocks = int(np.ceil(n / b))
    starts_max = n - b + 1
    out = np.empty(n_iter, dtype=float)
    for i in range(n_iter):
        st = rng.integers(0, starts_max, size=n_blocks)
        idx = (st[:, None] + np.arange(b)[None, :]).ravel()[:n]
        out[i] = stat(r[idx])
    point = stat(r)
    lo, hi = np.percentile(out, [2.5, 97.5])
    return {"n": n, "point": float(point), "ci_lo": float(lo), "ci_hi": float(hi),
            "p_gt0": float((out <= 0).mean()), "block": b, "iters": n_iter,
            "boot_mean": float(out.mean()),
            "verdict": "0 초과 (95% 신뢰구간이 0을 포함하지 않음)" if lo > 0 else
                       "0 미만" if hi < 0 else "0과 구분되지 않음"}


# ── ② PBO — Combinatorially Symmetric Cross-Validation (정식) ───────────────────────────────
def pbo_cscv(M, S: int = 10, max_combos: int = 400, seed: int = SEED) -> dict:
    """Bailey·Borwein·López de Prado·Zhu (2017) CSCV.

    M : (T × N) 행렬. 열 = 전략 구성(여기서는 §6.6 격자 12개), 행 = 월별 수익률.

    절차: 시계열을 S 개 인접 조각으로 나누고, S/2 개를 골라 IS(학습), 나머지를 OOS 로 둔다.
          IS 최적 구성 n* 의 OOS 상대순위 ω 를 구하고 로짓 λ=ln(ω/(1-ω)) 를 모은다.
          PBO = P(λ ≤ 0) = "IS 1등이 OOS 중앙값 아래로 떨어질 확률".

    ★ 기존 축약형(한 조각씩 빼는 leave-one-out)은 CSCV 가 아니다. 조합의 대칭성이
      깨져서 PBO 가 체계적으로 과소추정된다 — 과적합을 놓치는 방향이라 더 위험하다.
    """
    M = np.asarray(M, dtype=float)
    if M.ndim != 2:
        return {"pbo": np.nan, "verdict": "입력이 2차원 행렬이 아닙니다"}
    T, N = M.shape
    if N < 2 or T < 2 * S:
        return {"pbo": np.nan, "n_combos": 0, "N": N, "T": T,
                "verdict": f"표본 부족 (구성 {N}개, {T}개월 < 필요 {2*S}개월)"}
    # 결측 열 제거
    good = np.isfinite(M).all(axis=0)
    if good.sum() < 2:
        good = np.isfinite(M).mean(axis=0) > 0.9
        M = np.where(np.isfinite(M), M, 0.0)
    M = M[:, good]
    N = M.shape[1]
    if N < 2:
        return {"pbo": np.nan, "n_combos": 0, "verdict": "유효 구성이 2개 미만입니다"}

    S = int(S) - (int(S) % 2)                       # 짝수로
    S = max(4, min(S, T // 2))
    parts = np.array_split(np.arange(T), S)
    half = S // 2
    combos = list(itertools.combinations(range(S), half))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:                    # 조합 폭발 방지 — 균등 표집
        pick = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in sorted(pick)]

    lams, ranks = [], []
    for cb in combos:
        is_idx = np.concatenate([parts[i] for i in cb])
        oos_idx = np.concatenate([parts[i] for i in range(S) if i not in cb])
        if len(is_idx) < 4 or len(oos_idx) < 4:
            continue
        sr_is = np.array([_sharpe_raw(M[is_idx, j]) for j in range(N)])
        sr_oos = np.array([_sharpe_raw(M[oos_idx, j]) for j in range(N)])
        if not np.isfinite(sr_is).any() or not np.isfinite(sr_oos).any():
            continue
        nstar = int(np.nanargmax(sr_is))
        valid = np.isfinite(sr_oos)
        if valid.sum() < 2 or not valid[nstar]:
            continue
        # OOS 상대순위 ω ∈ (0,1). 순위 1등 = 1.0 근처
        order = np.argsort(np.argsort(np.where(valid, sr_oos, -np.inf)))
        w = (order[nstar] + 1) / (valid.sum() + 1)
        w = min(max(w, 1e-6), 1 - 1e-6)
        ranks.append(w)
        lams.append(math.log(w / (1 - w)))
    if not lams:
        return {"pbo": np.nan, "n_combos": 0, "verdict": "유효 조합이 없습니다"}
    lam = np.array(lams)
    pbo = float((lam <= 0).mean())
    return {"pbo": pbo, "n_combos": len(lam), "S": S, "N": N, "T": T,
            "median_oos_rank": float(np.median(ranks)),
            "verdict": ("과적합 위험 낮음 (PBO<0.5)" if pbo < 0.5 else
                        "★ 과적합 위험 높음 — IS 최적 구성이 OOS 에서 절반 이상 중앙값 아래")}


# ── ③ DSR — Deflated Sharpe Ratio (정식) ───────────────────────────────────────────────────
def deflated_sharpe(r, n_trials: int, sr_trials: Optional[Sequence[float]] = None) -> dict:
    """Bailey & López de Prado (2014).

    SR*  = sqrt(Var(SR_trials)) · [ (1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ]
    DSR  = Φ[ (SR̂ - SR*)·√(T-1) / √(1 - γ₃·SR̂ + (γ₄-1)/4·SR̂²) ]
    (γ = 오일러-마스케로니 0.5772, γ₃ = 왜도, γ₄ = 첨도(비초과))

    ★ SR̂ 과 SR* 는 **같은 단위(기간당)** 여야 한다. 연율화한 Sharpe 를 넣으면 DSR 이
      1.0 으로 붙어버려 아무것도 판정하지 못한다 — 기존 구현의 실패 모드가 이것이었다.
    ★ Var(SR_trials) 는 시행된 구성들의 Sharpe 분산이다. 주지 않으면 이론적 근사
      Var ≈ (1+SR̂²/2)/T 를 쓰되, 그 사실을 판정문에 명시한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    T = len(r)
    if T < 12:
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan,
                "verdict": "표본 부족(12개월 미만)"}
    try:
        from scipy import stats as _st
        Phi, Phi_inv = _st.norm.cdf, _st.norm.ppf
        skew = float(_st.skew(r, bias=False))
        kurt = float(_st.kurtosis(r, fisher=False, bias=False))
    except Exception:
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan, "verdict": "scipy 없음"}

    sr = _sharpe_raw(r)
    if not np.isfinite(sr):
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan, "verdict": "Sharpe 산출 불가"}

    N = max(2, int(n_trials))
    used_empirical = False
    if sr_trials is not None:
        v = np.asarray([x for x in sr_trials if np.isfinite(x)], dtype=float)
        if len(v) >= 3:
            var_sr = float(v.var(ddof=1))
            used_empirical = True
        else:
            var_sr = (1.0 + 0.5 * sr ** 2) / T
    else:
        var_sr = (1.0 + 0.5 * sr ** 2) / T
    var_sr = max(var_sr, 1e-12)

    g = 0.5772156649015329
    sr_star = math.sqrt(var_sr) * ((1 - g) * Phi_inv(1 - 1.0 / N) +
                                   g * Phi_inv(1 - 1.0 / (N * math.e)))
    denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2
    if denom <= 0:
        return {"dsr": np.nan, "sr": sr, "sr_star": sr_star,
                "verdict": "분모 비양수(극단 왜도/첨도) — 판정 불가"}
    z = (sr - sr_star) * math.sqrt(T - 1) / math.sqrt(denom)
    dsr = float(Phi(z))
    return {"dsr": dsr, "sr": float(sr), "sr_star": float(sr_star), "T": T,
            "n_trials": N, "skew": skew, "kurt": kurt,
            "var_source": "시행 구성들의 실측 분산" if used_empirical else "이론 근사(1+SR²/2)/T",
            "verdict": ("과적합 보정 후에도 유의 (DSR>0.95)" if dsr > 0.95 else
                        "보정 후 한계적 (0.90<DSR≤0.95)" if dsr > 0.90 else
                        "★ 과적합 보정 후 유의하지 않음")}


# ── ④ 워크포워드 (학습 5년 / 검증 1년 롤링) ─────────────────────────────────────────────────
def walk_forward(M, months, labels: Sequence[str], train_y: int = 5, test_y: int = 1) -> dict:
    """AAR 은 학습할 파라미터가 없다(전부 사전등록 고정). 그래서 워크포워드가 검정하는 것은
    '최적화'가 아니라 **구성 선택의 안정성**이다:

      학습창에서 가장 좋았던 구성을 그대로 다음 1년에 쓴다 → 그 OOS 성과가
      (a) 전체 구성 평균보다 좋은가  (b) 0보다 큰가

    (a)가 성립하지 않으면 "어느 구성이 좋은지는 과거로부터 알 수 없다"는 뜻이고,
    그건 12개 구성 중 좋은 것을 골라 보고하는 행위가 전부 사후선택이라는 증거다.
    """
    M = np.asarray(M, dtype=float)
    T, N = M.shape
    idx = pd.DatetimeIndex(months)
    rows = []
    tr, te = train_y * 12, test_y * 12
    if T < tr + te:
        return {"folds": 0, "verdict": f"표본 부족 ({T}개월 < 학습{tr}+검증{te})",
                "oos_mean": np.nan, "oos_t": np.nan, "table": pd.DataFrame()}
    picked_oos: List[float] = []
    avg_oos: List[float] = []
    for s in range(0, T - tr - te + 1, te):
        a, b, c = s, s + tr, min(s + tr + te, T)
        sr_is = np.array([_sharpe_raw(M[a:b, j]) for j in range(N)])
        if not np.isfinite(sr_is).any():
            continue
        j = int(np.nanargmax(sr_is))
        oos = M[b:c, j]
        allo = np.nanmean(M[b:c, :], axis=1)
        picked_oos.extend(oos[np.isfinite(oos)].tolist())
        avg_oos.extend(allo[np.isfinite(allo)].tolist())
        rows.append({
            "학습구간": f"{idx[a]:%Y-%m}~{idx[b-1]:%Y-%m}",
            "검증구간": f"{idx[b]:%Y-%m}~{idx[c-1]:%Y-%m}",
            "IS최적구성": labels[j] if j < len(labels) else str(j),
            "IS Sharpe": round(float(sr_is[j]) * math.sqrt(12), 3),
            "OOS 월평균": round(float(np.nanmean(oos)) * 100, 3),
            "전구성 OOS 평균": round(float(np.nanmean(allo)) * 100, 3),
            "판정": "선택이 유효" if np.nanmean(oos) > np.nanmean(allo) else "선택이 무효",
        })
    if not rows:
        return {"folds": 0, "verdict": "유효 폴드 없음", "oos_mean": np.nan,
                "oos_t": np.nan, "table": pd.DataFrame()}
    p = np.array(picked_oos)
    a = np.array(avg_oos)
    k = min(len(p), len(a))
    mu, t = hac_tstat(p[:k] - a[:k])
    mu_abs, t_abs = hac_tstat(p)
    wins = sum(1 for r in rows if r["판정"] == "선택이 유효")
    return {"folds": len(rows), "table": pd.DataFrame(rows),
            "oos_mean": float(np.nanmean(p)), "oos_t": t_abs,
            "excess_mean": mu, "excess_t": t, "wins": wins,
            "verdict": (f"{wins}/{len(rows)} 폴드에서 IS 최적 구성이 전구성 평균을 이겼습니다. "
                        f"OOS 월평균 {np.nanmean(p)*100:+.3f}%p (HAC t={t_abs:.2f}), "
                        f"선택 초과분 {mu*100:+.3f}%p (t={t:.2f}).")}


# ── ⑤ 등가성 검정 TOST — "효과 없음"을 주장하는 유일하게 정당한 방법 ────────────────────────
def tost_equivalence(x, bound: float, alpha: float = 0.05) -> dict:
    """귀무가설 채택은 증거가 아니다. "M-EXIT 는 예측력이 없다"를 주장하려면
    **효과가 실질적으로 무시 가능한 범위 안에 있다**를 적극적으로 보여야 한다.

    TOST: H01: θ ≤ -Δ,  H02: θ ≥ +Δ 를 각각 단측 검정해 둘 다 기각하면 '등가' 판정.
    Δ(bound)는 사전에 정한다 — 여기서는 V-DROP 효과의 절반. 즉 "M-EXIT 효과가
    V-DROP 의 절반에도 못 미친다"를 보인다. 사후에 Δ 를 조정하면 검정이 무의미해진다.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12 or not np.isfinite(bound) or bound <= 0:
        return {"equivalent": None, "n": n, "bound": bound,
                "verdict": "표본 부족 또는 등가범위 미정 — 판정 불가"}
    mu, t_hac = hac_tstat(x)
    se = abs(mu / t_hac) if (np.isfinite(t_hac) and abs(t_hac) > 1e-12) else (x.std(ddof=1) / math.sqrt(n))
    if not np.isfinite(se) or se <= 0:
        return {"equivalent": None, "n": n, "bound": bound, "verdict": "표준오차 산출 불가"}
    try:
        from scipy import stats as _st
        crit = float(_st.t.ppf(1 - alpha, n - 1))
        p_lo = float(_st.t.sf((mu + bound) / se, n - 1))       # H01: θ ≤ -Δ 기각용
        p_hi = float(_st.t.sf((bound - mu) / se, n - 1))       # H02: θ ≥ +Δ 기각용
    except Exception:
        crit, p_lo, p_hi = 1.65, np.nan, np.nan
    t1 = (mu + bound) / se
    t2 = (bound - mu) / se
    eq = bool(t1 > crit and t2 > crit)
    return {"equivalent": eq, "n": n, "mean": float(mu), "se": float(se), "bound": float(bound),
            "t_lower": float(t1), "t_upper": float(t2), "p": float(max(p_lo, p_hi)),
            "ci_lo": float(mu - crit * se), "ci_hi": float(mu + crit * se),
            "verdict": (f"등가 확인 — 효과가 ±{bound*100:.3f}%p 범위 안에 있습니다(무시 가능)."
                        if eq else
                        f"등가를 보이지 못했습니다 — 신뢰구간 [{mu-crit*se:+.4f}, {mu+crit*se:+.4f}] 이 "
                        f"±{bound:.4f} 를 벗어납니다. 표본이 작아서일 수도 있으므로 "
                        f"'효과가 있다'는 뜻은 아닙니다.")}


# ── ⑥ 패널 그레인저 인과 (H5 선행성) ────────────────────────────────────────────────────────
def panel_granger(df: "pd.DataFrame", cause: str, effect: str, entity: str = "code",
                  time: str = "month", lags: int = 3) -> dict:
    """개체 고정효과 패널에서 cause → effect 선행성을 F검정한다.

      effect(i,t) = Σ_{k=1..L} β_k·cause(i,t-k) + Σ_{k=1..L} γ_k·effect(i,t-k) + α_i + δ_t + ε
      H0: β_1=…=β_L=0

    ★ Nickell bias: 개체 FE + 시차종속변수 조합은 O(1/T) 편의를 갖는다. 여기서는
      T≈120개월이라 편의가 1% 미만이고, 우리가 보는 것은 β 의 크기가 아니라 **유의성과
      방향성 비교**이므로 실질적 영향이 없다. (양방향에 동일한 편의가 걸리므로 비교는 특히
      안전하다.) 표본이 짧아지면 그 사실을 판정문에 명시한다.
    """
    need = [c for c in (entity, time, cause, effect) if c not in df.columns]
    if need:
        return {"F": np.nan, "p": np.nan, "verdict": f"컬럼 없음 {need} — 판정 불가"}
    d = df[[entity, time, cause, effect]].copy()
    d[time] = as_ts_series(d[time])
    d = d.dropna(subset=[entity, time]).sort_values([entity, time])
    g = d.groupby(entity, observed=True)
    cols = []
    for k in range(1, lags + 1):
        d[f"_c{k}"] = g[cause].shift(k)
        d[f"_e{k}"] = g[effect].shift(k)
        cols += [f"_c{k}", f"_e{k}"]
    d = d.dropna(subset=[effect] + cols)
    if len(d) < 200:
        return {"F": np.nan, "p": np.nan, "n": len(d),
                "verdict": f"유효 관측 {len(d):,}행으로 부족합니다 — 판정 불가"}

    y = d[effect].to_numpy(dtype=float)
    ent_c, ent_k = factorize_codes(d[entity])
    tim_c, tim_k = factorize_codes(d[time])
    Xc = d[[f"_c{k}" for k in range(1, lags + 1)]].to_numpy(dtype=float)
    Xe = d[[f"_e{k}" for k in range(1, lags + 1)]].to_numpy(dtype=float)

    # 제한모형(원인 시차 제외) / 비제한모형 각각 FE 흡수 후 RSS 비교
    r_r, _, _, _ = absorb_fe(y, Xe, [ent_c, tim_c], [ent_k, tim_k])
    r_u, beta_u, keep_u, info = absorb_fe(y, np.column_stack([Xe, Xc]), [ent_c, tim_c],
                                          [ent_k, tim_k])
    rss_r = float(r_r @ r_r)
    rss_u = float(r_u @ r_u)
    q = int(np.sum(keep_u[-lags:])) if keep_u.size >= lags else lags
    n = len(y)
    dof = n - ent_k - tim_k - int(keep_u.sum()) - 1
    if q <= 0 or dof <= 10 or rss_u <= 0:
        return {"F": np.nan, "p": np.nan, "n": n, "verdict": "자유도 부족 — 판정 불가"}
    F = ((rss_r - rss_u) / q) / (rss_u / dof)
    try:
        from scipy import stats as _st
        p = float(_st.f.sf(max(F, 0.0), q, dof))
    except Exception:
        p = np.nan
    return {"F": float(F), "p": p, "n": n, "q": q, "dof": dof, "lags": lags,
            "converged": info.get("converged", True),
            "verdict": (f"{cause} → {effect} 선행성 F({q},{dof})={F:.2f}, p={p:.4g}")}


# ── ⑦ 이벤트 스터디 CAR + 캘린더타임 유의성 ─────────────────────────────────────────────────
def event_study_car(events: "pd.DataFrame", px_daily: "pd.DataFrame", bench_daily: "pd.Series",
                    horizon: int = 120, group_col: str = "exit_type") -> "pd.DataFrame":
    """군별 시장조정 CAR 곡선 (t+1 ~ t+H 영업일).

    ★ 시장모형(베타 추정) 대신 **시장조정**(초과수익 = 개별 - 시장)을 쓴다. 이유:
      철회 이벤트는 소형·저유동성 종목에 몰리는데, 그런 종목의 베타 추정치는
      비동시거래(non-synchronous trading) 때문에 심하게 편의되어 있다. 잘못 추정한 베타로
      조정하면 CAR 이 베타 오차를 보여줄 뿐이다. 시장조정은 편의가 없고 해석이 명확하다.

    ★ 겹치는 이벤트 창의 횡단면 상관 때문에 CAR 의 단순 t검정은 **표준오차를 크게
      과소추정한다.** 그래서 유의성 판정은 이 함수가 아니라 calendar_time_alpha() 로 한다.
      여기서는 곡선(설명용)과 평균만 낸다.
    """
    cols = ["group", "h", "mean_car", "median_car", "n", "se_naive"]
    if events is None or events.empty or px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    px = px_daily[["code", "date", "close"]].dropna().copy()
    px["date"] = as_ts_series(px["date"])
    px = px.sort_values(["code", "date"])
    px["ret"] = px.groupby("code", observed=True)["close"].pct_change()

    bm = pd.Series(bench_daily).copy()
    bm.index = as_ts_series(pd.Series(bm.index))
    dates = np.sort(px["date"].unique())
    dpos = {d: i for i, d in enumerate(dates)}
    px["_di"] = px["date"].map(dpos)
    px["_ex"] = px["ret"] - px["date"].map(bm).astype("float64")

    ex_by_code: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for c, g in px.dropna(subset=["_ex"]).groupby("code", observed=True):
        ex_by_code[str(c)] = (g["_di"].to_numpy(dtype=np.int64), g["_ex"].to_numpy(dtype=float))

    ev = events.copy()
    ev["event_date"] = as_ts_series(ev["event_date"] if "event_date" in ev.columns else ev["month"])
    rows = []
    for grp, gg in ev.groupby(group_col, observed=True):
        mat = np.full((len(gg), horizon), np.nan)
        for i, r in enumerate(gg.itertuples(index=False)):
            code = str(getattr(r, "code", ""))
            arr = ex_by_code.get(code)
            if arr is None:
                continue
            di, ex = arr
            t0 = int(np.searchsorted(dates, np.datetime64(getattr(r, "event_date")), side="right"))
            lo = int(np.searchsorted(di, t0, side="left"))
            seg = ex[lo:lo + horizon]
            if len(seg):
                mat[i, :len(seg)] = seg
        car = np.nancumsum(np.where(np.isfinite(mat), mat, 0.0), axis=1)
        valid = np.isfinite(mat).any(axis=1)
        car = car[valid]
        if not len(car):
            continue
        for h in range(horizon):
            v = car[:, h]
            v = v[np.isfinite(v)]
            if not len(v):
                continue
            rows.append({"group": str(grp), "h": h + 1, "mean_car": float(v.mean()),
                         "median_car": float(np.median(v)), "n": int(len(v)),
                         "se_naive": float(v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 1 else np.nan})
    return pd.DataFrame(rows, columns=cols)


def calendar_time_alpha(events: "pd.DataFrame", fwd: "pd.DataFrame", months,
                        hold_m: int = 6, group_col: str = "exit_type") -> "pd.DataFrame":
    """캘린더타임 포트폴리오 — 겹치는 이벤트 창의 횡단면 상관을 구조적으로 제거한다.

    매월, '최근 hold_m 개월 안에 이벤트가 있었던' 종목을 동일가중으로 담은 포트폴리오의
    시장초과수익 시계열을 만들고 그 평균을 HAC t 로 검정한다. 이벤트가 아무리 겹쳐도
    각 달의 관측은 하나뿐이므로 표준오차가 정직하다 (Fama 1998, Mitchell & Stafford 2000).
    """
    out_cols = ["group", "n_months", "mean_excess_m", "t_hac", "p", "ann_excess", "avg_names"]
    if events is None or events.empty or fwd is None or fwd.empty:
        return pd.DataFrame(columns=out_cols)
    ev = events.copy()
    ev["month"] = as_ts_series(ev["month"])
    F = fwd[["code", "month", "fwd_ret"]].dropna().copy()
    F["month"] = as_ts_series(F["month"])
    mkt = F.groupby("month", observed=True)["fwd_ret"].mean().rename("mkt")
    F = F.merge(mkt, on="month", how="left")
    F["ex"] = F["fwd_ret"] - F["mkt"]
    rows = []
    for grp, gg in ev.groupby(group_col, observed=True):
        series, counts = [], []
        for m in months:
            lo = add_months(m, -(hold_m - 1))
            names = set(gg.loc[(gg["month"] >= lo) & (gg["month"] <= m), "code"].astype(str))
            if not names:
                series.append(np.nan)
                counts.append(0)
                continue
            sub = F[(F["month"] == m) & (F["code"].astype(str).isin(names))]
            series.append(float(sub["ex"].mean()) if len(sub) else np.nan)
            counts.append(int(len(sub)))
        s = np.asarray(series, dtype=float)
        ok = s[np.isfinite(s)]
        if len(ok) < 12:
            rows.append({"group": str(grp), "n_months": int(len(ok)), "mean_excess_m": np.nan,
                         "t_hac": np.nan, "p": np.nan, "ann_excess": np.nan,
                         "avg_names": float(np.mean(counts)) if counts else 0.0})
            continue
        mu, t = hac_tstat(ok)
        rows.append({"group": str(grp), "n_months": int(len(ok)), "mean_excess_m": float(mu),
                     "t_hac": float(t), "p": t_to_p(t, dof=len(ok) - 1),
                     "ann_excess": float((1 + mu) ** 12 - 1),
                     "avg_names": float(np.mean([c for c in counts if c > 0]) if any(counts) else 0.0)})
    return pd.DataFrame(rows, columns=out_cols)
