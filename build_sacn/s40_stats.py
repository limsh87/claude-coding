

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-S  통계 검증 게이트 (SPEC §9)                                                         ║
# ║                                                                                          ║
# ║   ① 블록 부트스트랩 (1,000회) → CAGR·Sharpe 신뢰구간                                       ║
# ║   ② PBO — CSCV 방식, 12개 구성 대상                                                        ║
# ║   ③ DSR — 시도 횟수 12로 명시                                                              ║
# ║   ④ 워크포워드 — 학습 5년 / 검증 1년 롤링 (구성 선택이 개입할 때만 의미가 있다)              ║
# ║   ⑤ BH-FDR (q=0.10) — H1~H4 전체                                                          ║
# ║   ⑥ 뉴이-웨스트 표준오차 (lag = 리밸런싱 주기 × 1.5)                                        ║
# ║                                                                                          ║
# ║  ①②③④ 는 기존 코드베이스에 아예 없었다. 여기서 새로 만든다.                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

try:
    from scipy import stats as _sps
except Exception:                                            # pragma: no cover
    _sps = None


def _norm_cdf(x: float) -> float:
    if _sps is not None:
        return float(_sps.norm.cdf(x))
    return float(0.5 * (1.0 + math.erf(x / math.sqrt(2.0))))


def _norm_ppf(p: float) -> float:
    p = float(min(max(p, 1e-12), 1 - 1e-12))
    if _sps is not None:
        return float(_sps.norm.ppf(p))
    # Acklam 근사 (scipy 없을 때도 DSR 을 포기하지 않는다)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r: np.ndarray, ppy: float = 12.0, n_boot: int = 1000,
                    block: Optional[int] = None, seed: int = SEED) -> dict:
    """순환 블록 부트스트랩. 자기상관을 보존한 채 CAGR·Sharpe 신뢰구간을 구한다.

    SPEC §9.1 은 '블록 길이 21영업일'이라고 쓰여 있다. 그런데 월간 수익률 계열에서
    21영업일은 곧 1기간이고, 블록 길이 1 은 자기상관을 전혀 보존하지 못해
    부트스트랩이 단순 i.i.d. 재표집으로 퇴화한다.
    → 21영업일을 기간 단위로 환산하되 최소 3기간을 강제한다(더 넓은 = 더 보수적인 구간).
      실제 사용한 블록 길이를 항상 함께 보고한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 12:
        return {"n": n, "ok": False}
    dpp = 21.0 if ppy <= 13 else (5.0 if ppy <= 60 else 1.0)
    if block is None:
        block = max(3, int(round(21.0 / dpp)))
    block = int(min(max(1, block), max(1, n // 3)))
    rng = np.random.default_rng(seed)
    nblk = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, nblk))
    offs = np.arange(block)
    cagrs = np.empty(n_boot)
    sharps = np.empty(n_boot)
    for i in range(n_boot):
        idx = ((starts[i][:, None] + offs[None, :]) % n).ravel()[:n]
        x = r[idx]
        eq = float(np.prod(1.0 + x))
        cagrs[i] = eq ** (ppy / n) - 1.0 if eq > 0 else -1.0
        sd = np.std(x, ddof=1)
        sharps[i] = (np.mean(x) / sd * math.sqrt(ppy)) if sd > 0 else np.nan
    qs = [2.5, 50, 97.5]
    cg = np.nanpercentile(cagrs, qs)
    sh = np.nanpercentile(sharps, qs)
    return {"ok": True, "n": n, "block": block, "n_boot": n_boot,
            "cagr_lo": float(cg[0]), "cagr_med": float(cg[1]), "cagr_hi": float(cg[2]),
            "sharpe_lo": float(sh[0]), "sharpe_med": float(sh[1]), "sharpe_hi": float(sh[2]),
            "p_cagr_le0": float(np.mean(cagrs <= 0)),
            "p_sharpe_le0": float(np.nanmean(sharps <= 0))}


# ── ② PBO (CSCV) ────────────────────────────────────────────────────────────────────────────
def cscv_pbo(M: pd.DataFrame, S: int = 8) -> dict:
    """Combinatorially Symmetric Cross-Validation (Bailey et al. 2016).

    M: 행=기간, 열=구성(12개). 값=기간수익률.
    S 개 연속 블록으로 나누고 C(S, S/2) 조합 전부에 대해
      IS 최고 구성의 OOS 순위 → 로짓 λ → PBO = P(λ ≤ 0).
    기존 코드베이스의 R6 은 leave-one-out 8폴드 약식이었다. 여기서는 정식 조합형을 쓴다.
    """
    out = {"ok": False, "pbo": float("nan"), "n_combo": 0, "n_config": int(M.shape[1] if M is not None else 0)}
    if M is None or M.shape[1] < 2:
        return out
    D = M.dropna(how="any")
    T, N = D.shape
    if T < S * 4:
        # 표본이 짧으면 블록을 '더 크게' 만들어야 한다. 이전 식은 T 가 줄수록 S 를 키워
        # 블록 길이를 2로 붕괴시켰다(= 블록 구조 소멸).
        S = max(4, 2 * (T // 8))
        if S < 4 or T < S * 2:
            out["note"] = f"기간 {T} 이 부족해 CSCV 를 수행할 수 없습니다 (필요 ≥ {4*4})."
            return out
    if S % 2:
        S -= 1
    blocks = np.array_split(np.arange(T), S)
    from itertools import combinations
    half = S // 2
    lams, n_lt0 = [], 0
    X = D.to_numpy(float)
    for comb in combinations(range(S), half):
        is_idx = np.concatenate([blocks[b] for b in comb])
        oos_idx = np.concatenate([blocks[b] for b in range(S) if b not in comb])
        if len(is_idx) < 4 or len(oos_idx) < 4:
            continue
        def _sr(a):
            sd = np.std(a, axis=0, ddof=1)
            return np.where(sd > 0, np.mean(a, axis=0) / np.where(sd > 0, sd, 1.0), -np.inf)
        sr_is = _sr(X[is_idx])
        sr_oos = _sr(X[oos_idx])
        n_star = int(np.argmax(sr_is))
        # OOS 순위 (1=최악 … N=최고)
        rank = float(pd.Series(sr_oos).rank(method="average").iloc[n_star])
        w = rank / (N + 1.0)
        w = min(max(w, 1e-6), 1 - 1e-6)
        lam = math.log(w / (1 - w))
        lams.append(lam)
        if lam <= 0:
            n_lt0 += 1
    if not lams:
        out["note"] = "유효 조합이 없습니다."
        return out
    out.update(ok=True, pbo=float(n_lt0 / len(lams)), n_combo=len(lams), S=S,
               lambda_med=float(np.median(lams)), n_config=N, T=T)
    return out


# ── ③ Deflated Sharpe Ratio ─────────────────────────────────────────────────────────────────
def deflated_sharpe(r: np.ndarray, n_trials: int = 12, ppy: float = 12.0,
                    sr_variance: Optional[float] = None) -> dict:
    """Bailey & López de Prado. 시도 횟수를 명시적으로 차감한 Sharpe 유의도.

    반환 dsr 은 '진짜 SR>0 일 확률'이다. SPEC §11 은 DSR > 0 을 요구하지만
    그건 사실상 항상 참이므로, 통용 기준인 0.95 도 함께 표시한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 12:
        return {"ok": False, "n": n}
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return {"ok": False, "n": n}
    sr = float(np.mean(r) / sd)                       # 기간단위 SR (비연율)
    m3 = float(np.mean(((r - r.mean()) / sd) ** 3))
    m4 = float(np.mean(((r - r.mean()) / sd) ** 4))
    e = 0.5772156649015329
    N = max(2, int(n_trials))
    if sr_variance is None or not np.isfinite(sr_variance) or sr_variance <= 0:
        sr_variance = 1.0 / max(1, n - 1)             # SR 추정치의 분산 근사
    sd_sr = math.sqrt(sr_variance)
    sr0 = sd_sr * ((1 - e) * _norm_ppf(1 - 1.0 / N) + e * _norm_ppf(1 - 1.0 / (N * math.e)))
    denom = math.sqrt(max(1e-12, 1.0 - m3 * sr + (m4 - 1.0) / 4.0 * sr * sr))
    z = (sr - sr0) * math.sqrt(max(1, n - 1)) / denom
    return {"ok": True, "n": n, "sr_period": sr, "sr_annual": sr * math.sqrt(ppy),
            "sr0": sr0, "dsr": _norm_cdf(z), "z": z, "n_trials": N,
            "skew": m3, "kurt": m4}


# ── ④ 워크포워드 ────────────────────────────────────────────────────────────────────────────
def walk_forward(M: pd.DataFrame, ppy: float = 12.0, train_years: int = 5,
                 test_years: int = 1) -> dict:
    """학습 5년에서 최고 구성을 고르고, 이어지는 1년 성과를 측정한다 (롤링).

    이 전략은 주 구성이 사전등록되어 있어 파라미터 적합이 없다. 그러나 '12개 구성 중
    사후에 최고를 고르면 얼마나 무너지는가'는 반드시 측정해야 한다 — 그게 이 검정의 목적이다.
    """
    out = {"ok": False, "folds": []}
    if M is None or M.shape[1] < 2:
        return out
    D = M.dropna(how="any")
    T = len(D)
    tr, te = int(train_years * ppy), int(test_years * ppy)
    if T < tr + te:
        out["note"] = f"기간 {T} < 학습 {tr} + 검증 {te} — 워크포워드 불가"
        return out
    idx = D.index
    rows, oos = [], []
    s = 0
    while s + tr + te <= T:
        A, B = D.iloc[s:s + tr], D.iloc[s + tr:s + tr + te]
        sd = A.std(ddof=1).replace(0, np.nan)
        sr = (A.mean() / sd).dropna()
        if not len(sr):
            s += te
            continue
        pick = sr.idxmax()
        rb = B[pick]
        rows.append({"검증구간": f"{as_ts(idx[s+tr]):%Y-%m} ~ {as_ts(idx[s+tr+te-1]):%Y-%m}",
                     "선택 구성": str(pick),
                     "학습 Sharpe": float(sr.max() * math.sqrt(ppy)),
                     "검증 Sharpe": float(rb.mean() / rb.std(ddof=1) * math.sqrt(ppy))
                     if rb.std(ddof=1) > 0 else float("nan"),
                     "검증 수익": float((1 + rb).prod() - 1)})
        oos.extend(rb.tolist())
        s += te
    if not rows:
        return out
    oos = np.asarray(oos, float)
    out.update(ok=True, folds=rows, n_fold=len(rows),
               oos_sharpe=float(np.mean(oos) / np.std(oos, ddof=1) * math.sqrt(ppy))
               if np.std(oos, ddof=1) > 0 else float("nan"),
               oos_cagr=float(np.prod(1 + oos) ** (ppy / len(oos)) - 1) if len(oos) else float("nan"),
               n_distinct=len({r["선택 구성"] for r in rows}))
    return out


# ── ⑥ 뉴이-웨스트 (lag = 리밸런싱 주기 × 1.5) ───────────────────────────────────────────────
def nw_tstat(x: np.ndarray, ppy: float = 12.0) -> Tuple[float, float, int]:
    """SPEC §9.6 규칙대로 lag 을 고정한다. 반환 (평균, t, lag)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 12:
        return float("nan"), float("nan"), 0
    # 괄호 안은 '한 달에 몇 기간인가'. SPEC 의 '리밸런싱 주기 × 1.5' 를 보유기간(≈1개월)
    # 기준으로 읽은 것이다. ppy 를 그대로 1.5배하면 120개월 표본에 lag 18 이 되어
    # Bartlett 창이 표본의 15%를 덮는다 — HAC 로 성립하지 않는다.
    per_month = 1 if ppy <= 13 else (4 if ppy <= 60 else 21)
    lag = max(1, int(round(1.5 * per_month)))
    mu, t = hac_tstat(x, lags=lag)
    return float(mu), float(t), lag


def fdr_table(names: Sequence[str], pvals: Sequence[float], q: float = 0.10) -> pd.DataFrame:
    """BH-FDR. 개별 p 값만으로 판정하지 않는다 (SPEC §3)."""
    p = np.asarray([float(x) if np.isfinite(x) else 1.0 for x in pvals], float)
    rej = bh_fdr(p, q=q)
    order = np.argsort(p)
    crit = np.full(len(p), np.nan)
    m = len(p)
    for rank, i in enumerate(order, start=1):
        crit[i] = q * rank / m
    return pd.DataFrame({"가설": list(names), "p": p, "BH 임계": crit,
                         "기각(유의)": np.asarray(rej, bool)})


def two_sided_p(t: float) -> float:
    if not np.isfinite(t):
        return 1.0
    return float(2.0 * (1.0 - _norm_cdf(abs(t))))
