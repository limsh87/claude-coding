
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  신호 구성 — FLOW_raw → 이중 디민 잔차 → 횡단면 통제 잔차   (SPEC §6.2~6.5)         ║
# ║                                                                                          ║
# ║  §6.2  netbuy_share(A,i,d) = (매수 − 매도) / 그날 총거래량                                 ║
# ║        FLOW_raw(A,i,d) = Σ_{k=0..K} netbuy_share(A,i,d+k)        (K=0 또는 2)              ║
# ║        진입 = d+K+1 종가.  ★ 거래원/수급은 장 마감 후 공개되므로 d 종가 진입은 즉시 실패다.║
# ║                                                                                          ║
# ║  §6.3  이중 디민 — 대형 창구는 항상 거래량 점유가 커서 원값은 거의 전부 창구 고정효과다.   ║
# ║        FLOW_resid = FLOW_raw                                                              ║
# ║                     − median_{과거 60일}[ FLOW_raw(A,i,·) ]   창구×종목 베이스라인          ║
# ║                     − median_{과거 60일}[ FLOW_raw(A,·,d) ]   창구 전체 그날 성향           ║
# ║                     + median_{과거 60일}[ FLOW_raw(·,·,·) ]   이중차감 보정                 ║
# ║        중앙값을 쓴다(평균 아님) — 창구 플로우는 꼬리가 두껍다.                              ║
# ║                                                                                          ║
# ║  ★★ 베이스라인의 숨은 미래참조 ★★                                                          ║
# ║     FLOW_raw(d′) 는 d′..d′+K 를 쓴다. 따라서 d′ = d−1, K=2 면 그 값은 d+1 을 포함한다.      ║
# ║     '과거 60일 중앙값' 이라고 쓰고 그냥 shift(1) 하면 미래가 새어 들어온다.                 ║
# ║     → 베이스라인은 반드시 (K+1) 만큼 밀어서 '윈도가 d 이전에 끝난' 값들만 쓴다.             ║
# ║                                                                                          ║
# ║  §6.5  통제 잔차: BDF ~ log(시총) + 직전20일수익률 + 회전율 + 업종더미 (+연도더미)          ║
# ║     ★ 전기간 풀표본으로 적합하면 미래정보가 계수에 들어간다. 매매신호로 쓸 버전은            ║
# ║       '과거 252거래일 이벤트만' 으로 적합해 오늘 이벤트에 적용한다(PIT).                    ║
# ║       풀표본 버전은 이벤트스터디 기술통계용으로만 따로 만들고 그렇게 표기한다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BASELINE_DAYS = 60                 # SPEC §6.6: 고정
CONTROL_TRAIN_DAYS = 252           # PIT 통제회귀 학습창 (1년)
CUT_TRAIN_DAYS = 252               # 상·하위 30% 컷 산정창 (PIT)


def _forward_rolling_sum(s: pd.Series, k: int) -> pd.Series:
    """s[d] + s[d+1] + ... + s[d+k].  결측이 하나라도 있으면 결측(0으로 메우지 않는다)."""
    if k <= 0:
        return s.astype(float)
    rev = s.iloc[::-1]
    out = rev.rolling(k + 1, min_periods=k + 1).sum().iloc[::-1]
    return out


def build_flow_raw(F: pd.DataFrame, k: int) -> pd.DataFrame:
    """(actor, code, date) → FLOW_raw. 모든 날에 대해 계산한다(이벤트 없는 날 = 대조군 재료)."""
    if F is None or len(F) == 0:
        return pd.DataFrame(columns=["actor", "code", "date", "flow_raw"])
    d = F[["actor", "code", "date", "netbuy_share"]].dropna(subset=["actor", "code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["actor", "code", "date"], kind="stable")
    d["flow_raw"] = (d.groupby(["actor", "code"], observed=True)["netbuy_share"]
                      .transform(lambda s: _forward_rolling_sum(s, k)))
    return d[["actor", "code", "date", "flow_raw"]]


def residualize_flow(R: pd.DataFrame, k: int, baseline: int = BASELINE_DAYS) -> pd.DataFrame:
    """SPEC §6.3 이중 디민. 미래참조를 막기 위해 베이스라인을 (k+1) 만큼 민다."""
    if R is None or len(R) == 0:
        return R
    d = R.sort_values(["actor", "code", "date"], kind="stable").copy()
    lag = k + 1                                   # ★ 윈도가 d 이전에 끝난 값만 베이스라인에 쓴다

    # ── ① 창구×종목 베이스라인 ────────────────────────────────────────────────────────────
    g = d.groupby(["actor", "code"], observed=True)["flow_raw"]
    d["b_ai"] = g.transform(
        lambda s: s.shift(lag).rolling(baseline, min_periods=baseline).median())
    d["b_n"] = g.transform(lambda s: s.shift(lag).rolling(baseline, min_periods=1).count())

    # ── ② 창구 전체 그날 성향 ─────────────────────────────────────────────────────────────
    day_actor = (d.groupby(["actor", "date"], observed=True)["flow_raw"].median()
                  .rename("x").reset_index().sort_values(["actor", "date"], kind="stable"))
    day_actor["b_a"] = (day_actor.groupby("actor", observed=True)["x"]
                        .transform(lambda s: s.shift(lag)
                                   .rolling(baseline, min_periods=max(10, baseline // 3)).median()))
    d = d.merge(day_actor[["actor", "date", "b_a"]], on=["actor", "date"], how="left")

    # ── ③ 전체 베이스라인 (이중차감 보정) ─────────────────────────────────────────────────
    day_all = (d.groupby("date", observed=True)["flow_raw"].median()
                .rename("x").reset_index().sort_values("date", kind="stable"))
    day_all["b_g"] = (day_all["x"].shift(lag)
                      .rolling(baseline, min_periods=max(10, baseline // 3)).median())
    d = d.merge(day_all[["date", "b_g"]], on="date", how="left")

    d["flow_resid"] = d["flow_raw"] - d["b_ai"] - d["b_a"] + d["b_g"]
    # SPEC §6.3: 60영업일 베이스라인이 부족한 (A,i) 페어는 결측 처리
    set_where(d, d["b_ai"].isna(), "flow_resid", np.nan)

    n_ok = int(d["flow_resid"].notna().sum())
    LOG.info(f"이중 디민(k={k}) — 잔차 유효 {n_ok:,}/{len(d):,}행 "
             f"({100*n_ok/max(len(d),1):.1f}%). 베이스라인 부족분은 0 이 아니라 결측입니다. "
             f"베이스라인은 이벤트 윈도와 겹치지 않도록 {lag}일 밀어서 계산했습니다(미래참조 차단).")
    return d[["actor", "code", "date", "flow_raw", "flow_resid", "b_ai", "b_a", "b_g"]]


def attach_signal(E: pd.DataFrame, RES: pd.DataFrame) -> pd.DataFrame:
    """이벤트에 그 날 그 행위자의 FLOW 를 붙인다."""
    if E is None or len(E) == 0:
        return E
    e = E.copy()
    e["date"] = as_ts_series(e["pub_date"])
    m = RES.rename(columns={"date": "date"})
    out = e.merge(m, on=["actor", "code", "date"], how="left")
    n_hit = int(out["flow_raw"].notna().sum())
    LOG.info(f"이벤트 {len(out):,}건 중 플로우 관측 {n_hit:,}건 "
             f"({100*n_hit/max(len(out),1):.1f}%) — 미관측은 결측으로 두고 편입 대상에서 제외됩니다.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  §6.5 횡단면 통제 회귀
# ══════════════════════════════════════════════════════════════════════════════════════════
def _design_matrix(df: pd.DataFrame, with_year: bool) -> Tuple[np.ndarray, List[str]]:
    cols, names = [], []
    lm = np.log(df["marcap"].clip(lower=1.0).to_numpy(float))
    lm = np.where(np.isfinite(lm), lm, np.nanmedian(lm[np.isfinite(lm)]) if np.isfinite(lm).any() else 0.0)
    cols.append(lm); names.append("log_mktcap")
    for c in ("ret20", "turnover"):
        v = pd.to_numeric(df.get(c), errors="coerce").to_numpy(float)
        med = np.nanmedian(v) if np.isfinite(v).any() else 0.0
        cols.append(np.where(np.isfinite(v), v, med)); names.append(c)
    ind = df.get("industry", pd.Series("미분류", index=df.index)).astype(str)
    for lv in sorted(ind.unique())[1:]:                     # 첫 수준은 기준 범주(더미 함정 회피)
        cols.append((ind == lv).to_numpy(float)); names.append(f"ind:{lv}")
    if with_year:
        yr = as_ts_series(df["date"]).dt.year.astype("Int64").astype(str)
        for lv in sorted(yr.unique())[1:]:
            cols.append((yr == lv).to_numpy(float)); names.append(f"yr:{lv}")
    X = np.column_stack(cols + [np.ones(len(df))])
    return X, names + ["const"]


def control_residual(S: pd.DataFrame, signal_col: str, pit: bool = True,
                     train_days: int = CONTROL_TRAIN_DAYS) -> pd.Series:
    """SPEC §6.5. pit=True 면 '과거 이벤트만' 으로 적합해 오늘 이벤트에 적용한다.

    ★ pit=False (풀표본 적합) 는 계수에 미래정보가 들어가므로 매매신호로 쓰면 안 된다.
      이벤트스터디의 기술통계 목적으로만 쓰고, 산출물에 그렇게 표기한다."""
    if S is None or len(S) == 0 or signal_col not in S.columns:
        return pd.Series(dtype=float)
    d = S.copy()
    d["date"] = as_ts_series(d["date"])
    y_all = pd.to_numeric(d[signal_col], errors="coerce")
    out = pd.Series(np.nan, index=d.index, dtype=float)

    if not pit:
        ok = y_all.notna()
        if ok.sum() < 50:
            return out
        X, _ = _design_matrix(d[ok], with_year=True)
        b = ols_beta(X, y_all[ok].to_numpy(float))
        out.loc[ok] = y_all[ok].to_numpy(float) - X @ b
        return out

    # ── PIT: 날짜 오름차순으로 훑으며 '과거 train_days 이벤트' 로 적합 ────────────────────
    d = d.sort_values("date", kind="stable")
    dates = d["date"].to_numpy(DT64)
    uniq = np.unique(dates[~pd.isna(dates)])
    if len(uniq) == 0:
        return out
    # 월 단위로 계수를 갱신한다(매일 재적합은 3,000회 회귀 = 낭비이고 결과 차이가 미미하다)
    月 = pd.DatetimeIndex(uniq).to_period("M").unique()
    y_np = y_all.reindex(d.index).to_numpy(float)
    idx_by_month = {p: np.where(pd.DatetimeIndex(dates).to_period("M") == p)[0] for p in 月}
    beta = None
    trained_at = None
    for p in 月:
        tgt = idx_by_month[p]
        if len(tgt) == 0:
            continue
        t0 = pd.Timestamp(p.start_time)
        train = np.where((pd.DatetimeIndex(dates) < t0) &
                         (pd.DatetimeIndex(dates) >= t0 - pd.Timedelta(days=int(train_days * 1.45))))[0]
        train = train[np.isfinite(y_np[train])]
        if len(train) >= 100:
            sub = d.iloc[train]
            Xtr, _ = _design_matrix(sub, with_year=False)
            beta = ols_beta(Xtr, y_np[train])
            trained_at = sub
        if beta is None or trained_at is None:
            continue
        # 적용 시점의 설계행렬은 학습 때와 '같은 열 구성' 이어야 한다 → 학습표본에 맞춰 재구성
        sub_t = d.iloc[tgt].copy()
        sub_t["industry"] = sub_t["industry"].where(
            sub_t["industry"].isin(trained_at["industry"].unique()),
            sorted(trained_at["industry"].unique())[0])
        Xte, _ = _design_matrix(pd.concat([trained_at.head(0), sub_t]), with_year=False)
        if Xte.shape[1] != len(beta):
            continue
        pred = Xte @ beta
        vals = y_np[tgt] - pred
        out.iloc[tgt] = np.where(np.isfinite(y_np[tgt]), vals, np.nan)
    n = int(out.notna().sum())
    LOG.info(f"통제회귀 잔차({'PIT' if pit else '풀표본'}) — {n:,}건 산출 "
             f"({'과거 1년 이벤트로만 적합' if pit else '★풀표본 적합: 매매신호로 사용 금지'})")
    return out


def pit_quantile_cut(S: pd.DataFrame, col: str, q: float,
                     train_days: int = CUT_TRAIN_DAYS) -> pd.Series:
    """상·하위 컷을 '전체 표본 분위' 로 잡으면 그 자체가 미래참조다.
    과거 train_days 이벤트의 분위로 오늘 이벤트를 자른다."""
    d = S[["date", col]].copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values("date", kind="stable")
    v = pd.to_numeric(d[col], errors="coerce")
    out = pd.Series(np.nan, index=d.index, dtype=float)
    di = pd.DatetimeIndex(d["date"])
    for p in di.to_period("M").unique():
        tgt = np.where(di.to_period("M") == p)[0]
        t0 = pd.Timestamp(p.start_time)
        tr = np.where((di < t0) & (di >= t0 - pd.Timedelta(days=int(train_days * 1.45))))[0]
        vals = v.to_numpy(float)[tr]
        vals = vals[np.isfinite(vals)]
        if len(vals) < 50:
            continue
        out.iloc[tgt] = float(np.quantile(vals, q))
    return out.reindex(S.index)
