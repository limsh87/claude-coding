
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L4-A  통계 검증 원시함수  (SPEC §9)                                                      ║
# ║   ① 블록 부트스트랩 (블록 21영업일, 1,000회)                                               ║
# ║   ② PBO (CSCV, Bailey et al. 2016)                                                        ║
# ║   ③ DSR (Deflated Sharpe Ratio, Bailey & López de Prado 2014)                             ║
# ║   ④ 워크포워드 (학습 5년 / 검증 1년 롤링)                                                  ║
# ║   ⑤ BH-FDR (q=0.10)                                                                        ║
# ║   ⑥ 뉴이-웨스트 표준오차                                                                    ║
# ║   ⑦ 플라시보 (이벤트 날짜 ±20~60영업일 이동)                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BLOCK_LEN = 21
N_BOOT = 1000


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r: np.ndarray, n_iter: int = N_BOOT, block: int = BLOCK_LEN,
                    stat: Callable[[np.ndarray], float] = None,
                    seed: int = SEED) -> Dict[str, float]:
    """순환 블록 부트스트랩(circular block bootstrap).

    ★ 이벤트드리븐 일별수익률은 보유구간이 겹쳐 자기상관이 있다. iid 부트스트랩을 쓰면
      신뢰구간이 좁아져 유의성이 과대평가된다. 블록을 통째로 뽑아 상관구조를 보존한다.
      순환(circular)을 쓰는 이유는 표본 끝 구간이 과소표집되는 편향을 없애기 위함이다."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    T = r.size
    out = {"n": T, "obs": np.nan, "p_gt0": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
           "boot_mean": np.nan}
    if T < block * 3:
        return out
    if stat is None:
        def stat(x):                                   # 연율화 샤프
            sd = x.std(ddof=1)
            return float(x.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan
    obs = float(stat(r))
    out["obs"] = obs
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, T, size=(n_iter, nb))
    offs = np.arange(block)
    vals = np.empty(n_iter)
    for i in range(n_iter):
        idx = (starts[i][:, None] + offs[None, :]).ravel()[:T] % T
        vals[i] = stat(r[idx])
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return out
    out["boot_mean"] = float(vals.mean())
    out["ci_lo"], out["ci_hi"] = (float(np.quantile(vals, 0.025)),
                                 float(np.quantile(vals, 0.975)))
    # 귀무가설(참값 0) 하의 분포로 중심이동한 뒤 관측값의 우측꼬리 확률
    centered = vals - vals.mean()
    out["p_gt0"] = float((centered >= obs).mean())
    return out


# ── ② PBO (CSCV) ────────────────────────────────────────────────────────────────────────────
def pbo_cscv(perf: np.ndarray, n_split: int = 8) -> Dict[str, float]:
    """Combinatorially Symmetric Cross-Validation.

    perf: [T, N] — T개 시점 × N개 구성의 수익률 행렬.
    절차 (Bailey, Borwein, López de Prado, Zhu 2016):
      1) 시계열을 S개 균등 블록으로 자른다 (S 는 짝수)
      2) S개 중 S/2 개를 IS 로 고르는 모든 조합 C(S, S/2) 에 대해
      3) IS 에서 최고 성과 구성 n* 를 고르고
      4) OOS 에서 n* 의 상대순위 ω 를 구한 뒤 logit λ = ln(ω/(1-ω))
      5) PBO = P(λ <= 0)  = '선택한 구성이 OOS 중앙값 이하로 떨어질 확률'
    """
    out = {"pbo": np.nan, "n_comb": 0, "median_logit": np.nan, "n_config": 0}
    P = np.asarray(perf, float)
    if P.ndim != 2 or P.shape[1] < 2 or P.shape[0] < n_split * 4:
        return out
    T, N = P.shape
    out["n_config"] = N
    S = n_split if n_split % 2 == 0 else n_split - 1
    bounds = np.linspace(0, T, S + 1).astype(int)
    blocks = [P[bounds[i]:bounds[i + 1]] for i in range(S)]
    blocks = [b for b in blocks if len(b) > 1]
    S = len(blocks)
    if S < 4 or S % 2:
        S = S - (S % 2)
        blocks = blocks[:S]
    if S < 4:
        return out

    def _sr(x: np.ndarray) -> np.ndarray:
        mu = np.nanmean(x, axis=0)
        sd = np.nanstd(x, axis=0, ddof=1)
        return np.where(sd > 0, mu / sd, np.nan)

    logits = []
    for comb in itertools.combinations(range(S), S // 2):
        is_idx = list(comb)
        oos_idx = [i for i in range(S) if i not in comb]
        IS = np.vstack([blocks[i] for i in is_idx])
        OOS = np.vstack([blocks[i] for i in oos_idx])
        sr_is, sr_oos = _sr(IS), _sr(OOS)
        if not np.isfinite(sr_is).any() or not np.isfinite(sr_oos).any():
            continue
        n_star = int(np.nanargmax(sr_is))
        valid = np.isfinite(sr_oos)
        if valid.sum() < 2 or not np.isfinite(sr_oos[n_star]):
            continue
        # 상대순위 ω ∈ (0,1)
        rank = float((sr_oos[valid] < sr_oos[n_star]).sum()) / float(valid.sum())
        w = min(max(rank, 1.0 / (valid.sum() + 1)), 1.0 - 1.0 / (valid.sum() + 1))
        logits.append(math.log(w / (1.0 - w)))
    if not logits:
        return out
    lg = np.asarray(logits)
    out["n_comb"] = len(lg)
    out["median_logit"] = float(np.median(lg))
    out["pbo"] = float((lg <= 0).mean())
    return out


# ── ③ DSR ───────────────────────────────────────────────────────────────────────────────────
def expected_max_sharpe(sr_trials: np.ndarray, n_trials: Optional[int] = None) -> float:
    """E[max SR] = sqrt(V) * ((1-γ)·Z⁻¹(1-1/N) + γ·Z⁻¹(1-1/(N·e)))
       V = '시도들의 SR 분산' (하나만 있으면 정의되지 않으므로 보수적 기본값을 쓴다)"""
    s = np.asarray(sr_trials, float)
    s = s[np.isfinite(s)]
    N = int(n_trials or s.size)
    if N < 2:
        return 0.0
    V = float(np.var(s, ddof=1)) if s.size >= 2 else 0.25 ** 2
    if not np.isfinite(V) or V <= 0:
        V = 0.25 ** 2
    g = 0.5772156649015329                      # 오일러-마스케로니
    e = math.e
    z1 = norm_ppf(1.0 - 1.0 / N)
    z2 = norm_ppf(1.0 - 1.0 / (N * e))
    return math.sqrt(V) * ((1.0 - g) * z1 + g * z2)


def deflated_sharpe(r: np.ndarray, sr_trials: np.ndarray, n_trials: int) -> Dict[str, float]:
    """DSR — 여러 번 시도해서 고른 최고 샤프가 '운' 일 확률을 깎아낸 값.

    DSR = Φ( (SR - SR0) · sqrt(T-1) / sqrt(1 - γ3·SR + (γ4-1)/4·SR²) )
      SR0 = E[max SR] (위 식),  γ3=왜도, γ4=첨도. 모두 '주기당' SR 로 계산한다."""
    out = {"sharpe_period": np.nan, "sharpe_ann": np.nan, "sr0": np.nan,
           "dsr": np.nan, "n_trials": int(n_trials), "skew": np.nan, "kurt": np.nan}
    x = np.asarray(r, float)
    x = x[np.isfinite(x)]
    T = x.size
    if T < 30:
        return out
    sd = x.std(ddof=1)
    if sd <= 0:
        return out
    sr = float(x.mean() / sd)                    # 주기당(일별) 샤프
    m3 = float(((x - x.mean()) ** 3).mean() / sd ** 3)
    m4 = float(((x - x.mean()) ** 4).mean() / sd ** 4)
    sr0 = expected_max_sharpe(sr_trials, n_trials)
    denom = 1.0 - m3 * sr + (m4 - 1.0) / 4.0 * sr ** 2
    out.update(sharpe_period=sr, sharpe_ann=sr * math.sqrt(252), sr0=sr0,
               skew=m3, kurt=m4)
    if denom <= 0:
        return out
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    out["dsr"] = norm_cdf(z)
    return out


# ── ④ 워크포워드 ────────────────────────────────────────────────────────────────────────────
def walk_forward(daily_by_cfg: Dict[str, pd.DataFrame], cal: pd.DatetimeIndex,
                 train_years: int = 5, test_years: int = 1) -> pd.DataFrame:
    """학습 5년으로 최고 구성을 고르고, 이어지는 1년 성과를 기록한다(롤링).

    ★ 이게 '실제로 운용했다면' 에 가장 가까운 검정이다. 전 구간 최고 구성의 전 구간 성과는
      정의상 사후선택(look-ahead)이므로 그 숫자로 판단해선 안 된다."""
    if not daily_by_cfg or not len(cal):
        return pd.DataFrame()
    # ★ 표본 구간이 학습+검증보다 짧으면 검증 창이 하나도 안 잡혀 조용히 '판정불가' 가 된다.
    #   Phase 0 이 PARTIAL(3~10년)로 떨어지면 실제로 일어난다. 창을 표본에 맞춰 줄이고,
    #   줄였다는 사실을 반드시 로그에 남긴다(검정력이 그만큼 낮아지므로).
    span_y = (cal[-1] - cal[0]).days / 365.25
    if span_y < train_years + test_years + 0.5:
        new_train = max(1, int(span_y - test_years - 0.25))
        if new_train < 1:
            LOG.warn(f"워크포워드 불가 — 표본이 {span_y:.1f}년뿐이라 학습/검증 창을 만들 수 "
                     f"없습니다. 이는 '실패' 가 아니라 '검정 불가' 입니다.")
            return pd.DataFrame()
        LOG.warn(f"표본이 {span_y:.1f}년이라 워크포워드 학습창을 {train_years}→{new_train}년으로 "
                 f"줄였습니다. 학습 표본이 짧을수록 구성 선택이 불안정해지므로 "
                 f"검증 성과를 실제 운용 기대치로 읽지 마세요.")
        train_years = new_train
    names = list(daily_by_cfg.keys())
    M = pd.DataFrame({n: daily_by_cfg[n].set_index("date")["ret"].reindex(cal).fillna(0.0)
                      for n in names}, index=cal)
    rows = []
    y0, y1 = cal[0].year, cal[-1].year
    for te in range(y0 + train_years, y1 + 1, test_years):
        tr_lo = pd.Timestamp(f"{te - train_years}-01-01")
        tr_hi = pd.Timestamp(f"{te}-01-01")
        te_hi = pd.Timestamp(f"{te + test_years}-01-01")
        tr = M[(M.index >= tr_lo) & (M.index < tr_hi)]
        te_ = M[(M.index >= tr_hi) & (M.index < te_hi)]
        if len(tr) < 200 or len(te_) < 60:
            continue
        sd = tr.std(ddof=1)
        sr = (tr.mean() / sd.replace(0, np.nan)) * math.sqrt(252)
        if not sr.notna().any():
            continue
        pick = str(sr.idxmax())
        oos = te_[pick]
        rows.append({"검증연도": te, "선택구성": pick,
                     "학습샤프": float(sr.max()),
                     "검증수익": float(np.prod(1 + oos.to_numpy()) - 1),
                     "검증샤프": float(oos.mean() / oos.std(ddof=1) * math.sqrt(252))
                     if oos.std(ddof=1) > 0 else np.nan,
                     "검증일수": len(oos)})
    W = pd.DataFrame(rows)
    if len(W):
        hit = float((W["검증수익"] > 0).mean())
        LOG.table([[r.검증연도, _trunc(r.선택구성, 34), f"{r.학습샤프:.2f}",
                    f"{r.검증수익*100:+.2f}%", f"{r.검증샤프:.2f}"] for r in W.itertuples()],
                  ["검증연도", "학습기간 최고구성", "학습Sharpe", "검증수익", "검증Sharpe"],
                  ["c", "l", "r", "r", "r"],
                  title=f"워크포워드 (학습 {train_years}년 / 검증 {test_years}년 롤링) — "
                        f"양(+) 검증연도 비율 {100*hit:.0f}%")
    return W


# ── ⑤ BH-FDR 래퍼 ───────────────────────────────────────────────────────────────────────────
def bh_fdr_table(items: List[Tuple[str, float, str]], q: float = 0.10) -> pd.DataFrame:
    """items: [(가설ID, p값, 설명)]  → BH 보정 결과표.

    ★ 가설이 5개뿐이고 서로 양의 상관을 가질 수 있다(같은 데이터·같은 신호를 본다).
      BH 는 양의 의존(PRDS) 하에서 유효하므로 그대로 쓰되, 상관 구조가 임의라면
      Benjamini-Yekutieli 가 더 보수적이다 — 두 임계를 모두 표에 표시한다."""
    ids = [i for i, _, _ in items]
    ps = np.array([p for _, p, _ in items], float)
    passed = bh_fdr(ps, q=q)
    m = len(ps)
    cm = float(np.sum(1.0 / np.arange(1, m + 1))) if m else 1.0
    passed_by = bh_fdr(ps * cm, q=q) if m else passed
    order = np.argsort(np.where(np.isfinite(ps), ps, np.inf))
    rank = np.empty(m, int)
    rank[order] = np.arange(1, m + 1)
    return pd.DataFrame({
        "가설": ids, "p값": ps, "순위": rank,
        "BH임계": q * rank / max(m, 1),
        "BH(q=0.10)": np.where(passed, "통과", "기각"),
        "BY(보수)": np.where(passed_by, "통과", "기각"),
        "설명": [d for _, _, d in items]})


# ── ⑦ 플라시보 ──────────────────────────────────────────────────────────────────────────────
def make_placebo_events(E: pd.DataFrame, cal: pd.DatetimeIndex, seed: int = SEED,
                        lo: int = 20, hi: int = 60) -> pd.DataFrame:
    """이벤트 날짜를 ±lo~hi 영업일 무작위 이동시킨 가짜 이벤트.

    ★ 가짜 이벤트에서도 효과가 나오면 파이프라인에 look-ahead 가 있다는 뜻이다 (SPEC §9-7).
      종목·증권사·신호분포는 그대로 두고 '시점만' 흔든다 — 그래야 시점 정렬에서 오는
      누수만 분리해서 볼 수 있다."""
    if E is None or len(E) == 0 or not len(cal):
        return pd.DataFrame()
    rng = np.random.default_rng(seed ^ 0xA11CE)
    day_pos = {d: i for i, d in enumerate(cal)}
    n = len(E)
    shift = rng.integers(lo, hi + 1, size=n) * rng.choice([-1, 1], size=n)
    di = np.array([day_pos.get(pd.Timestamp(d), -1) for d in E["date"]])
    nd = di + shift
    ok = (di >= 0) & (nd >= 0) & (nd < len(cal))
    P = E[ok].copy()
    P["date"] = pd.DatetimeIndex(cal)[nd[ok]]
    P["pub_date"] = P["date"]
    LOG.info(f"플라시보 이벤트 {len(P):,}건 생성 (원본 {n:,}건 · ±{lo}~{hi}영업일 이동). "
             f"여기서 유의한 효과가 나오면 파이프라인에 미래참조가 있다는 뜻입니다.")
    return P
