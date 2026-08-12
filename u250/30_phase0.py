# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §3 Phase 0 — 커버리지 진단 (선행 필수, 게이트)                                           ║
# ║                                                                                          ║
# ║  팩터 백테스트 전에 반드시 먼저 실행한다. 커버리지가 미달이면 백테스트 없이 보류한다.       ║
# ║                                                                                          ║
# ║  ★ 이 절의 진짜 목적은 '데이터가 있냐'가 아니다. 커버 자체가 알파인 경우를 분리하는 것이다. ║
# ║    그래서 커버 종목만 담은 B_cov 를 따로 돌리고, 팩터 성과를 B2 와 B_cov 양쪽에 견준다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

@dataclass
class Coverage:
    factor: str
    cov_stock: float
    cov_stock_rebal: float
    cov_universe_rebal: pd.Series      # 리밸 시점별 U250 내 관측 종목수
    cov_trend: pd.Series               # 연도별 중앙값
    signal_rate: float
    median_cov: float
    verdict: str                       # PASS | PARTIAL | HOLD
    covered_codes: Dict[pd.Timestamp, set] = field(default_factory=dict)
    bias: Optional[pd.DataFrame] = None

    @property
    def proceed(self) -> bool:
        return self.verdict in ("PASS", "PARTIAL")


def coverage_diag(factor: str, obs: pd.DataFrame, sig: pd.DataFrame,
                  univ: pd.DataFrame, rebals: pd.DatetimeIndex,
                  all_codes: Sequence[str]) -> Coverage:
    """obs = (code, rebal) 관측 셀, sig = 그 중 실제 신호가 켜진 셀."""
    u = univ[univ["u250"]]
    u_by_t = {t: set(g["code"]) for t, g in u.groupby("rebal", observed=True)}
    obs_by_t = ({t: set(g["code"]) for t, g in obs.groupby("rebal", observed=True)}
                if len(obs) else {})
    cov_ts = pd.Series({t: len(u_by_t.get(t, set()) & obs_by_t.get(t, set())) for t in rebals},
                       dtype=float).sort_index()
    covered = {t: (u_by_t.get(t, set()) & obs_by_t.get(t, set())) for t in rebals}

    n_all = max(len(set(all_codes)), 1)
    cov_stock = len(set(obs["code"])) / n_all if len(obs) else 0.0
    cells = sum(len(v) for v in u_by_t.values())
    cov_cell = (cov_ts.sum() / cells) if cells else 0.0
    trend = cov_ts.groupby(cov_ts.index.year).median()
    srate = (len(sig) / max(len(obs), 1)) if len(obs) else 0.0
    med = float(cov_ts.median()) if len(cov_ts) else 0.0

    if med >= SPEC_COV["pass_median"]:
        verdict = "PASS"
    elif med >= SPEC_COV["hold_median"]:
        verdict = "PARTIAL"
    else:
        verdict = "HOLD"

    LOG.table(
        [["cov_stock", f"{cov_stock:.1%}", "전 기간 중 1회 이상 관측된 종목 비율"],
         ["cov_stock_rebal", f"{cov_cell:.1%}", "(종목×리밸) 셀 중 관측 비율 — U250 기준"],
         ["cov_universe_rebal 중앙값", f"{med:.0f}종목",
          f"기준: ≥{SPEC_COV['pass_median']} 정상 / {SPEC_COV['hold_median']}~"
          f"{SPEC_COV['pass_median']} 부분 / <{SPEC_COV['hold_median']} 보류"],
         ["signal_rate", f"{srate:.1%}", "관측된 것 중 실제로 신호가 발생한 셀 비율"],
         ["판정", verdict, {"PASS": "정상 진행", "PARTIAL": "부분 커버 팩터로 표기하고 진행",
                            "HOLD": "★백테스트 보류 (§6.4 조기 중단)"}[verdict]]],
        ["지표", "값", "정의 / 기준"], ["l", "r", "l"],
        title=f"[{factor}] Phase 0 커버리지 진단")
    if len(trend) > 1:
        LOG.table([[str(y), f"{v:.0f}"] for y, v in trend.items()],
                  ["연도", "U250 내 관측 종목수(중앙값)"], ["c", "r"],
                  title=f"[{factor}] cov_trend — 초기 연도 결측 급증 여부")
    return Coverage(factor, cov_stock, cov_cell, cov_ts, trend, srate, med, verdict, covered)


def coverage_bias(cov: Coverage, univ: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """커버 종목 vs 미커버 종목의 시총·거래대금·업종 분포 비교 (§3 추가 필수 진단)."""
    u = univ[univ["u250"]].copy()
    u["covered"] = [c in cov.covered_codes.get(t, set())
                    for t, c in zip(u["rebal"], u["code"])]
    if u["covered"].nunique() < 2:
        LOG.warn(f"[{cov.factor}] 커버/미커버 한쪽이 비어 선택편향 비교를 할 수 없습니다.")
        return pd.DataFrame()
    ind = sec.drop_duplicates("code").set_index("code").get("industry")
    u["industry"] = u["code"].map(ind) if ind is not None else ""
    rows = []
    for col, label in (("market_cap", "시가총액"), ("adv20", "20일 중앙 거래대금")):
        if col not in u.columns:
            continue
        a = u.loc[u["covered"], col].dropna()
        b = u.loc[~u["covered"], col].dropna()
        if not len(a) or not len(b):
            continue
        rows.append([label, f"{a.median():,.0f}", f"{b.median():,.0f}",
                     f"{a.median()/max(b.median(),1):.2f}x"])
    top = (u[u["covered"]]["industry"].value_counts(normalize=True).head(3))
    rows.append(["상위 업종(커버)", ", ".join(f"{k} {v:.0%}" for k, v in top.items()), "", ""])
    LOG.table(rows, ["항목", "커버 종목", "미커버 종목", "배수"], ["l", "r", "r", "r"],
              title=f"[{cov.factor}] 커버리지 선택편향 진단 — 커버 자체가 알파인가")
    out = u.groupby(["rebal", "covered"], observed=True).agg(
        n=("code", "size"), mktcap_med=("market_cap", "median"),
        adv_med=("adv20", "median")).reset_index()
    cov.bias = out
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §2 베이스라인 B1~B4                                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def run_baselines(eng: Engine, univ: pd.DataFrame, elig: pd.DataFrame,
                  window: str = "IS") -> Dict[str, BTResult]:
    u_by_t = {t: list(g["code"]) for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}
    e_by_t = {t: list(g["code"]) for t, g in elig[elig["eligible"]].groupby("rebal", observed=True)}
    reb = _window_rebals(eng.rebals, window)
    e2 = Engine(reb, eng.fwd, eng.cost, eng.delist)
    out = {}
    out["B1"] = e2.run(lambda t: u_by_t.get(t, []), "B1 U250 EW 총수익")
    out["B2"] = e2.run(lambda t: u_by_t.get(t, []), "B2 U250 EW 순수익")
    out["B3"] = e2.run(lambda t: e_by_t.get(t, []), "B3 적격 전종목 EW 순수익")
    #   B1 은 '총수익'이므로 NAV 를 총수익 계열로 바꿔 끼운다 (엔진은 둘 다 계산해 둔다)
    b1 = out["B1"]
    out["B1"] = BTResult(b1.name, b1.nav_gross, b1.nav_gross, b1.ret_gross, b1.ret_gross,
                         b1.turnover, pd.Series(0.0, index=b1.cost.index), b1.n_holdings)
    return out


def _window_rebals(rebals: pd.DatetimeIndex, window: str) -> pd.DatetimeIndex:
    m = SEAL.mask(rebals, window)
    return pd.DatetimeIndex(pd.Series(list(rebals))[m.to_numpy()].tolist())


def random_null(eng: Engine, univ: pd.DataFrame, n: int, sims: int = SPEC_B4_SIMS,
                window: str = "IS", aum: float = 100_000_000,
                match_turnover: Optional[float] = None) -> Dict[str, Any]:
    """B4 — U250 내 무작위 n종목 EW 를 sims 회. 팩터 선별력의 귀무분포.

    ★ 팩터로 뽑은 성과는 반드시 이 분포 안에서 위치를 본다. 절대 CAGR 은 판정에 쓰지 않는다.
    match_turnover 를 주면 '직전 보유를 그만큼 유지하는' 회전율 정합 귀무분포도 함께 만든다
    (무작위는 회전율이 100%에 가까워 비용 차가 스프레드에 섞이기 때문 — 보조 진단용).
    """
    reb = _window_rebals(eng.rebals, window)
    codes = list(eng.fwd.columns)
    cidx = {c: i for i, c in enumerate(codes)}
    u_by_t = {t: np.array([cidx[c] for c in g["code"] if c in cidx], dtype=np.int64)
              for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}
    rng = np.random.default_rng(SEED)
    W = np.zeros((sims, len(codes)), dtype=np.float32)
    nav = np.ones(sims, dtype=np.float64)
    navs = []
    used = 0
    for t in reb:
        if t not in eng.fwd.index:
            continue
        av = u_by_t.get(t)
        if av is None or len(av) == 0:
            continue
        r_all = eng.fwd.loc[t].to_numpy(dtype=np.float64)
        if eng.delist is not None and t in eng.delist.index:
            dl = eng.delist.loc[t].to_numpy(dtype=bool)
            r_all = np.where(dl, -1.0, r_all)
        av = av[np.isfinite(r_all[av])]
        if len(av) < n:
            continue
        # sims × n 무복원 추출 — 난수 정렬의 앞 n개
        rnd = rng.random((sims, len(av)))
        if match_turnover is not None and used > 0:
            #   회전율 정합 — 직전 보유 중 (1−회전율) 만큼은 유지하고 나머지만 새로 뽑는다.
            #   유지분과 신규분이 겹치지 않도록 각각의 난수 키에 벌점을 준다.
            keep = int(round(n * min(1.0, max(0.0, 1.0 - float(match_turnover)))))
            held = W[:, av] > 0
            fresh = np.where(held, 2.0, rnd)
            new_i = av[np.argpartition(fresh, max(n - keep, 1) - 1, axis=1)[:, :max(n - keep, 0)]]
            if keep > 0:
                keep_i = av[np.argpartition(np.where(held, rnd, 2.0), keep - 1, axis=1)[:, :keep]]
                pick = np.concatenate([keep_i, new_i], axis=1)
            else:
                pick = new_i
        else:
            pick = av[np.argpartition(rnd, n - 1, axis=1)[:, :n]]
        #   put_along_axis 로 '1 을 세팅'한 뒤 행 정규화한다. 중복 인덱스가 섞여도
        #   (회전율 정합 경로에서 발생 가능) 고유 종목에 대한 정확한 동일가중이 된다.
        Wn = np.zeros_like(W)
        np.put_along_axis(Wn, pick, np.float32(1.0), axis=1)
        _s = Wn.sum(axis=1, keepdims=True)
        Wn = np.divide(Wn, np.where(_s > 0, _s, 1.0), dtype=np.float32)
        dW = Wn - W
        notional = np.abs(dW).astype(np.float64) * aum
        ow = _cost_matrix(eng.cost, t, codes, notional)
        tax = eng.cost.sell_tax(t, pd.Index(codes))[None, :]
        buy = np.maximum(dW, 0.0).astype(np.float64)
        sell = np.maximum(-dW, 0.0).astype(np.float64)
        c = (buy * ow).sum(axis=1) + (sell * (ow + tax)).sum(axis=1)
        #   수익률은 '실제로 보유한 고유 종목의 동일가중 평균' = Wn·r 이다.
        #   pick 평균으로 계산하면 중복분이 두 번 세어진다.
        r = (Wn.astype(np.float64) * np.nan_to_num(r_all, nan=0.0)[None, :]).sum(axis=1)
        nav *= (1.0 + r) * (1.0 - c)
        drift = Wn * (1.0 + np.nan_to_num(r_all, nan=0.0)[None, :]).astype(np.float32)
        s = drift.sum(axis=1, keepdims=True)
        W = np.divide(drift, np.where(s > 0, s, 1.0), dtype=np.float32)
        navs.append(nav.copy())
        used += 1
    if not navs:
        return dict(n=n, sims=0, cagr=np.array([]), p95=np.nan, median=np.nan)
    ppy = eng.ppy
    yrs = used / ppy
    final = navs[-1]
    cagr = np.where(final > 0, np.power(np.maximum(final, 1e-12), 1.0 / max(yrs, 1e-9)) - 1, -1.0)
    LOG.ok(f"B4 무작위 귀무분포 (N={n}, {sims:,}회, {used}시점) — "
           f"CAGR 중앙 {np.median(cagr):.2%} · 상위5% 경계 {np.quantile(cagr, 0.95):.2%} · "
           f"상위1% {np.quantile(cagr, 0.99):.2%}"
           + ("  [회전율 정합]" if match_turnover is not None else ""))
    return dict(n=n, sims=sims, cagr=cagr, p95=float(np.quantile(cagr, 0.95)),
                median=float(np.median(cagr)), periods=used,
                matched=match_turnover is not None)


def _cost_matrix(cm: CostModel, t, codes: Sequence[str], notional: np.ndarray) -> np.ndarray:
    idx = pd.Index(codes)
    sp = cm._spread(t, idx)[None, :]
    adv = cm._adv(t, idx)[None, :]
    impact = SPEC_COST["impact_coef"] * np.sqrt(np.maximum(notional, 0.0) / np.maximum(adv, 1.0))
    return sp / 2.0 + SPEC_COST["commission_roundtrip"] / 2.0 + SPEC_COST["slippage_bp"] / 1e4 + impact
