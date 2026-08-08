
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-B  이벤트 스터디 — 군별 평균 CAR 곡선  (SPEC §8)                                      ║
# ║                                                                                          ║
# ║  네 개의 군을 반드시 함께 그린다. 하나만 보면 아무것도 판정할 수 없다:                     ║
# ║    ① 확증군    매수성 리포트 + 자사(계열) 창구 순매수 상위 30%                             ║
# ║    ② 페이드군  매수성 리포트 + 자사(계열) 창구 순매도 하위 30%                             ║
# ║    ③ 무플로우 대조군   매수성 리포트인데 플로우가 중간 40%                                 ║
# ║    ④ 무리포트 대조군   ★ H5 의 핵심. 리포트가 없는 날의 동일 창구 플로우 상위 30%          ║
# ║       — 이게 확증군만큼 좋으면 이건 '리포트 전략' 이 아니라 그냥 '플로우 전략' 이다.        ║
# ║                                                                                          ║
# ║  ★ 벤치마크 모형: market-adjusted (동일가중 유니버스 수익 차감).                           ║
# ║    market-model(베타 추정)은 추정창이 이벤트 직전이라 추정오차가 CAR 에 그대로 실린다.     ║
# ║    size-matched 는 시총이 T2~T4 로 강등될 수 있는 이번 설계에서 매칭 자체가 불안정하다.    ║
# ║    → 가장 단순하고 가정이 적은 것을 쓰고, 그 선택을 산출물에 명시한다.                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CAR_HORIZON = 60          # d+1 ~ d+60
CAR_PRE = 5               # 사전 구간(-5) 도 함께 그려 '이벤트 전에 이미 오르고 있었나' 를 본다


def _ret_matrix(px: pd.DataFrame, cal: pd.DatetimeIndex) -> Tuple[np.ndarray, Dict[str, int]]:
    close, cidx = _price_matrix(px, cal)
    with np.errstate(all="ignore"):
        r = np.full_like(close, np.nan)
        r[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    return r, cidx


def compute_car(events: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                horizon: int = CAR_HORIZON, pre: int = CAR_PRE) -> Dict[str, np.ndarray]:
    """이벤트 집합 → 평균 초과 CAR 곡선 + 표준오차 + 표본수.

    이벤트 t=0 은 리포트 발간일. 수익률은 시장(동일가중 유니버스) 차감 후 누적한다."""
    out = {"tau": np.arange(-pre, horizon + 1), "car": np.full(pre + horizon + 1, np.nan),
           "se": np.full(pre + horizon + 1, np.nan), "n": np.zeros(pre + horizon + 1, int)}
    if events is None or len(events) == 0 or not len(cal):
        return out
    R, cidx = _ret_matrix(px, cal)
    mkt = np.nanmean(R, axis=0)
    mkt = np.where(np.isfinite(mkt), mkt, 0.0)
    AR = R - mkt[None, :]

    day_pos = {d: i for i, d in enumerate(cal)}
    rows = []
    for code, dt_ in zip(events["code"], events["date"]):
        ci = cidx.get(code)
        di = day_pos.get(pd.Timestamp(dt_))
        if ci is None or di is None:
            continue
        lo, hi = di - pre, di + horizon
        if lo < 0 or hi >= AR.shape[1]:
            continue
        rows.append(AR[ci, lo:hi + 1])
    if not rows:
        return out
    M = np.vstack(rows)
    M = np.where(np.isfinite(M), M, 0.0)
    C = np.cumsum(M, axis=1)
    out["car"] = np.nanmean(C, axis=0)
    n = np.sum(np.isfinite(C), axis=0)
    out["n"] = n
    with np.errstate(all="ignore"):
        out["se"] = np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.maximum(n, 1))
    return out


def split_groups(S: pd.DataFrame, sig_col: str, ctrl: Optional[pd.DataFrame] = None
                 ) -> Dict[str, pd.DataFrame]:
    """SPEC §8 의 4개 군으로 나눈다. 컷은 PIT 분위(미래참조 차단)."""
    g: Dict[str, pd.DataFrame] = {}
    if S is None or len(S) == 0 or sig_col not in S.columns:
        return g
    d = S[S[sig_col].notna()].copy()
    hi = pit_quantile_cut(d, sig_col, 1.0 - PORT_LONG_PCT)
    lo = pit_quantile_cut(d, sig_col, PORT_FADE_PCT)
    d["_hi"], d["_lo"] = hi.to_numpy(), lo.to_numpy()
    ok = d["_hi"].notna() & d["_lo"].notna()
    d = d[ok]
    g["확증군(리포트+순매수상위30%)"] = d[d[sig_col] >= d["_hi"]]
    g["페이드군(리포트+순매도하위30%)"] = d[d[sig_col] <= d["_lo"]]
    g["무플로우대조군(리포트+중간40%)"] = d[(d[sig_col] > d["_lo"]) & (d[sig_col] < d["_hi"])]
    if ctrl is not None and len(ctrl):
        g["무리포트대조군(플로우만 상위30%)"] = ctrl
    return g


def build_noreport_control(RES: pd.DataFrame, E: pd.DataFrame, cal: pd.DatetimeIndex,
                           sig_col: str = "flow_resid", max_n: int = 60000) -> pd.DataFrame:
    """★ H5 의 대조군: '리포트가 없는 날의 동일 창구 플로우'.

    이게 확증군만큼 잘 되면 리포트는 아무 정보도 더하지 않은 것이고, 그렇다면
    이 전략은 '리포트 전략' 이 아니라 그냥 '브로커 플로우 전략' 이다 (SPEC §3 H5).

    표본이 수백만 행이라 전량을 쓰면 이벤트군과 표본수가 극단적으로 달라져 비교가
    왜곡된다 → 결정적 시드로 층화 추출하고 그 사실을 로그에 남긴다."""
    if RES is None or len(RES) == 0:
        return pd.DataFrame()
    ev_keys = set()
    if E is not None and len(E):
        ev_keys = set(zip(E["actor"], E["code"], pd.DatetimeIndex(E["date"])))
    d = RES[RES[sig_col].notna()].copy()
    if not len(d):
        return pd.DataFrame()
    if ev_keys:
        key = list(zip(d["actor"], d["code"], pd.DatetimeIndex(d["date"])))
        mask = np.array([k not in ev_keys for k in key], bool)
        d = d[mask]
    if not len(d):
        return pd.DataFrame()
    hi = pit_quantile_cut(d.assign(date=d["date"]), sig_col, 1.0 - PORT_LONG_PCT)
    d = d.assign(_hi=hi.to_numpy())
    d = d[d["_hi"].notna() & (d[sig_col] >= d["_hi"])]
    if len(d) > max_n:
        rs = np.random.default_rng(SEED)
        idx = rs.choice(len(d), size=max_n, replace=False)
        LOG.info(f"무리포트 대조군 {len(d):,}건 중 {max_n:,}건을 결정적 시드로 추출했습니다 "
                 f"(표본수 격차로 비교가 왜곡되는 것을 방지).")
        d = d.iloc[np.sort(idx)]
    return d


def report_event_study(groups: Dict[str, pd.DataFrame], px: pd.DataFrame,
                       cal: pd.DatetimeIndex) -> pd.DataFrame:
    """군별 CAR 을 계산하고 표로 출력 + parquet 산출물로 저장."""
    recs: List[pd.DataFrame] = []
    rows: List[List[Any]] = []
    for name, g in groups.items():
        if g is None or len(g) == 0:
            rows.append([name, "0", "-", "-", "-", "-", "표본 없음"])
            continue
        car = compute_car(g, px, cal)
        df = pd.DataFrame({"group": name, "tau": car["tau"], "car": car["car"],
                           "se": car["se"], "n": car["n"]})
        recs.append(df)
        def _at(t):
            i = np.where(car["tau"] == t)[0]
            return car["car"][i[0]] if len(i) else np.nan
        c20, c60 = _at(20), _at(60)
        i20 = np.where(car["tau"] == 20)[0]
        t20 = (car["car"][i20[0]] / car["se"][i20[0]]
               if len(i20) and np.isfinite(car["se"][i20[0]]) and car["se"][i20[0]] > 0 else np.nan)
        rows.append([name, f"{len(g):,}", f"{_at(0)*100:+.2f}%", f"{_at(5)*100:+.2f}%",
                     f"{c20*100:+.2f}%", f"{c60*100:+.2f}%", f"t20={t20:+.2f}"])
    LOG.table(rows, ["군", "이벤트수", "CAR(0)", "CAR(+5)", "CAR(+20)", "CAR(+60)", "유의성"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="이벤트 스터디 — 군별 누적초과수익 (시장조정 · 동일가중 유니버스 차감)")
    if not recs:
        return pd.DataFrame()
    out = pd.concat(recs, ignore_index=True)
    p = out_path("event_study_car.parquet")
    try:
        atomic_write_parquet(out, p)
        VAULT.put_table("event_study_car", out, scope="private", domain="result",
                        source=STRATEGY_ID)
    except Exception as e:                                            # noqa
        LOG.warn(f"CAR 저장 실패: {type(e).__name__}")
    return out


def car_ascii(car_df: pd.DataFrame, width: int = 62) -> None:
    """CAR 곡선을 로그에 ASCII 로 그린다 (matplotlib 없이도 형태를 볼 수 있게)."""
    if car_df is None or len(car_df) == 0:
        return
    LOG.rule("CAR 곡선 (가로=거래일 τ, 세로=군)")
    piv = car_df.pivot_table(index="group", columns="tau", values="car", observed=True)
    taus = [t for t in piv.columns if -5 <= t <= 60]
    if not taus:
        return
    vals = piv[taus].to_numpy(float)
    lo, hi = np.nanmin(vals), np.nanmax(vals)
    rng = max(hi - lo, 1e-9)
    marks = "▁▂▃▄▅▆▇█"
    for name in piv.index:
        row = piv.loc[name, taus].to_numpy(float)
        step = max(1, len(taus) // width)
        cells = "".join(
            marks[min(len(marks) - 1, max(0, int((v - lo) / rng * (len(marks) - 1))))]
            if np.isfinite(v) else " " for v in row[::step])
        LOG.info(f"  {_pad(_trunc(str(name), 30), 30)} |{cells}| "
                 f"최종 {row[-1]*100:+.2f}%")
    LOG.info(f"  (세로 스케일: {lo*100:+.2f}% ~ {hi*100:+.2f}%, τ=-5 부터 +60 까지)")
