

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-S  SACN 신호 (SPEC §6.2) + 직교화 (SPEC §6.3)                                         ║
# ║                                                                                          ║
# ║      SACN_i(t) = Σ_j w_ij(t)·r_j(t-1) / Σ_j w_ij(t)                                       ║
# ║                                                                                          ║
# ║  희소행렬 곱 한 번이면 전 종목이 동시에 계산된다:                                          ║
# ║      num = W @ (r ⊙ mask),  den = W @ mask,  SACN = num / den                             ║
# ║  mask 는 '그 시점 유니버스에 속한 연결기업만 쓴다'는 §6.2 규칙을 그대로 구현한 것이다.       ║
# ║  종목별 루프로 짜면 같은 결과에 수백 배가 든다.                                             ║
# ║                                                                                          ║
# ║  직교화(필수): SACN 을 그대로 쓰면 업종/사이즈/반전의 재포장일 수 있다.                     ║
# ║      SACN_i = α + β1·log(MktCap) + β2·r_i(t-1) + β3·SectorRet(t-1) + β4·BM_i + ε_i         ║
# ║  최종 신호는 잔차 ε. 원신호 버전과 직교화 버전을 둘 다 산출해 병기한다.                     ║
# ║  직교화 후 신호가 소멸하면 그것이 결론이다 — 되살리려 하지 않는다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

WINDOW_DAYS = {"1W": 7, "1M": 31}          # 캘린더 기준 룩백 (거래일 수가 아니라 달력일)


class PriceGrid:
    """일별 종가/시가 와이드 격자. 모든 시점 연산의 공용 기반."""

    def __init__(self, px_daily: pd.DataFrame):
        d = px_daily[["code", "date", "close", "open"]].copy()
        d["code"] = d["code"].astype(str)
        d["date"] = as_ts_series(d["date"])
        d = d.dropna(subset=["date", "code"]).drop_duplicates(["code", "date"], keep="last")
        self.close = d.pivot(index="date", columns="code", values="close").astype("float32")
        self.open = d.pivot(index="date", columns="code", values="open").astype("float32") \
            .reindex_like(self.close)
        self.close = self.close.sort_index()
        self.open = self.open.reindex(index=self.close.index, columns=self.close.columns)
        self.dates = self.close.index.to_numpy("datetime64[ns]")
        self.codes = list(self.close.columns)
        self.cpos = {c: i for i, c in enumerate(self.codes)}
        LOG.info(f"가격 격자 {self.close.shape[0]:,}일 × {self.close.shape[1]:,}종목 "
                 f"({self.close.memory_usage(deep=True).sum()/1e6:.0f}MB)")

    def pos_at_or_before(self, t) -> int:
        """t 이하 마지막 거래일의 인덱스. 없으면 -1."""
        return int(np.searchsorted(self.dates, np.datetime64(as_ts(t)), side="right")) - 1

    def pos_after(self, t) -> int:
        """t 초과 첫 거래일의 인덱스(= 익영업일). 없으면 -1."""
        i = int(np.searchsorted(self.dates, np.datetime64(as_ts(t)), side="right"))
        return i if i < len(self.dates) else -1

    def prior_return(self, t, window: str) -> np.ndarray:
        """t 시점까지의 직전 window 수익률 (종가 기준). 전 종목 벡터."""
        i1 = self.pos_at_or_before(t)
        if i1 < 0:
            return np.full(len(self.codes), np.nan, dtype="float32")
        t0 = as_ts(t) - pd.Timedelta(days=WINDOW_DAYS.get(window, 31))
        i0 = self.pos_at_or_before(t0)
        if i0 < 0 or i0 >= i1:
            return np.full(len(self.codes), np.nan, dtype="float32")
        c1 = self.close.iloc[i1].to_numpy("float32")
        c0 = self.close.iloc[i0].to_numpy("float32")
        with np.errstate(all="ignore"):
            r = np.where((c0 > 0) & np.isfinite(c0) & np.isfinite(c1), c1 / c0 - 1.0, np.nan)
        return r.astype("float32")

    def exec_price(self, t) -> Tuple[np.ndarray, Optional[pd.Timestamp]]:
        """익영업일 시가 (없으면 그날 종가). SPEC 아키텍처 불변 규칙: 진입은 익영업일."""
        i = self.pos_after(t)
        if i < 0:
            return np.full(len(self.codes), np.nan, dtype="float32"), None
        o = self.open.iloc[i].to_numpy("float32")
        c = self.close.iloc[i].to_numpy("float32")
        px = np.where(np.isfinite(o) & (o > 0), o, c)
        return px.astype("float32"), as_ts(self.close.index[i])


def rebalance_dates(months: pd.DatetimeIndex, grid: PriceGrid, freq: str) -> List[pd.Timestamp]:
    """리밸런싱 시점. 'M'=월말, 'W'=주말(각 주의 마지막 거래일)."""
    if freq == "M":
        out = []
        for m in months:
            i = grid.pos_at_or_before(m)
            if i >= 0:
                out.append(as_ts(grid.close.index[i]))
        return sorted(set(out))
    idx = pd.DatetimeIndex(grid.close.index)
    lo, hi = as_ts(months[0]), as_ts(months[-1])
    idx = idx[(idx >= lo - pd.DateOffset(months=1)) & (idx <= hi)]
    if not len(idx):
        return []
    s = pd.Series(idx, index=idx)
    wk = s.groupby([idx.isocalendar().year, idx.isocalendar().week]).max()
    return sorted(as_ts(x) for x in wk.to_numpy())


def compute_sacn(LM: LinkMatrices, grid: PriceGrid, uni_panel: pd.DataFrame,
                 rebals: Sequence[pd.Timestamp], window: str,
                 min_links: int = MIN_LINKS_REQUIRED) -> pd.DataFrame:
    """SPEC §6.2 원신호. 반환: code, date, sacn_raw, n_link_used, own_ret

    연결기업 j 는 '해당 시점 유니버스에 속한 종목' 만 쓴다. 유니버스 밖 종목은
    분자·분모 양쪽에서 동시에 빠져야 한다 — 분자에서만 빼면 신호가 0 쪽으로 눌린다.
    """
    if _sp is None or not LM.W:
        return pd.DataFrame(columns=["code", "date", "sacn_raw", "n_link_used", "own_ret"])

    lcodes = LM.codes
    lpos = {c: i for i, c in enumerate(lcodes)}
    # 링크행렬 좌표계 ↔ 가격격자 좌표계 대응
    g2l = np.full(len(lcodes), -1, dtype=np.int64)
    for c, i in lpos.items():
        j = grid.cpos.get(c, -1)
        g2l[i] = j

    uni = uni_panel[["code", "month"]].copy()
    uni["code"] = uni["code"].astype(str)
    uni["month"] = as_ts_series(uni["month"])
    uni_by_month: Dict[pd.Timestamp, set] = {
        as_ts(m): set(g["code"]) for m, g in uni.groupby("month")}

    link_months = sorted(LM.W.keys())
    lm_arr = np.array([np.datetime64(m) for m in link_months])

    rows = []
    for t in rebals:
        t = as_ts(t)
        # PIT: t 시점에 '이미 만들어져 있던' 가장 최근 월말 링크 행렬만 쓴다
        k = int(np.searchsorted(lm_arr, np.datetime64(t), side="right")) - 1
        if k < 0:
            continue
        m_link = link_months[k]
        W = LM.W.get(m_link)
        if W is None or W.nnz == 0:
            continue
        # 유니버스도 t 이하 최근 월말 스냅샷 기준
        m_uni = (t + pd.offsets.MonthEnd(0)) if t == (t + pd.offsets.MonthEnd(0)) \
            else (t - pd.offsets.MonthEnd(1))
        if m_uni not in uni_by_month:
            cand = [m for m in uni_by_month if m <= t]
            if not cand:
                continue
            m_uni = max(cand)
        alive = uni_by_month[m_uni]

        r_grid = grid.prior_return(t, window)
        r = np.full(len(lcodes), np.nan, dtype="float64")
        ok = g2l >= 0
        r[ok] = r_grid[g2l[ok]]

        mask = np.array([1.0 if c in alive else 0.0 for c in lcodes])
        mask *= np.isfinite(r).astype(float)
        if mask.sum() < min_links + 1:
            continue
        rr = np.where(np.isfinite(r), r, 0.0) * mask

        num = W @ rr
        den = W @ mask
        B = (W > 0).astype(np.float32)
        nlink = B @ mask                      # 실제로 쓰인 연결기업 수

        with np.errstate(all="ignore"):
            sig = np.where((den > 0) & (nlink >= min_links), num / den, np.nan)

        sel = np.isfinite(sig)
        if not sel.any():
            continue
        rows.append(pd.DataFrame({
            "code": [lcodes[i] for i in np.where(sel)[0]],
            "date": t,
            "sacn_raw": sig[sel].astype("float32"),
            "n_link_used": nlink[sel].astype("float32"),
            "own_ret": r[sel].astype("float32"),
        }))
    if not rows:
        LOG.warn(f"SACN 신호가 한 시점도 만들어지지 않았습니다 (window={window}). "
                 f"링크 부족 또는 유니버스 불일치를 확인하세요.")
        return pd.DataFrame(columns=["code", "date", "sacn_raw", "n_link_used", "own_ret"])
    S = pd.concat(rows, ignore_index=True)
    cov = S.groupby("date")["code"].size()
    LOG.ok(f"SACN 원신호 [{window}] {len(S):,}행 · {S['date'].nunique()}시점 · "
           f"시점당 평균 {cov.mean():.0f}종목 (최소 연결 {min_links}개 요건 적용)")
    return S


def orthogonalize(S: pd.DataFrame, uni_panel: pd.DataFrame, grid: PriceGrid,
                  window: str) -> pd.DataFrame:
    """SPEC §6.3 — 매 시점 횡단면 회귀의 잔차를 최종 신호로 쓴다.

        SACN_i = α + β1·log(MktCap_i) + β2·r_i(t-1) + β3·SectorRet(t-1) + β4·BM_i + ε_i

    설계 판단: 어떤 회귀항이 통째로 결측인 시점에는 그 항만 빼고 회귀한다.
    (그 시점을 통째로 버리면 표본이 붕괴하고, 결측을 0으로 채우면 계수가 오염된다)
    빠진 항은 시점별로 기록해 산출물에 남긴다.
    """
    if S is None or not len(S):
        return S
    U = uni_panel[["code", "month", "mktcap", "bm", "sector"]].copy()
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])

    d = S.copy()
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    # 주간 리밸런싱은 월말 이전 시점이 있으므로, 그 시점에 '알 수 있던' 직전 월말 속성을 쓴다
    d["month_attr"] = np.where(as_ts_series(d["date"]) >= d["month"],
                               d["month"], d["month"] - pd.offsets.MonthEnd(1))
    d["month_attr"] = as_ts_series(d["month_attr"])
    d = d.merge(U.rename(columns={"month": "month_attr"}), on=["code", "month_attr"], how="left")

    # 업종 수익률: 같은 시점, 같은 업종의 자기수익률 평균 (자기 자신 제외 = leave-one-out)
    grp = d.groupby(["date", "sector"], observed=True)["own_ret"]
    ssum, scnt = grp.transform("sum"), grp.transform("count")
    d["sector_ret"] = np.where(scnt > 1, (ssum - d["own_ret"].fillna(0)) / (scnt - 1), np.nan)

    d["logmc"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").clip(lower=1e8))
    d["bm_w"] = pd.to_numeric(d["bm"], errors="coerce")

    terms = [("logmc", "log(MktCap)"), ("own_ret", "r_i(t-1)"),
             ("sector_ret", "SectorRet(t-1)"), ("bm_w", "BM")]
    out, dropped = [], Counter()
    for t, g in d.groupby("date", observed=True):
        g = g.copy()
        y = pd.to_numeric(g["sacn_raw"], errors="coerce").to_numpy(float)
        use = []
        for c, label in terms:
            v = pd.to_numeric(g[c], errors="coerce")
            if v.notna().sum() >= max(10, 0.5 * len(g)):
                use.append((c, label, v))
            else:
                dropped[label] += 1
        if not use or len(g) < 12:
            g["sacn_resid"] = np.nan
            out.append(g)
            continue
        X = np.column_stack([np.ones(len(g))] + [
            np.where(np.isfinite(v.to_numpy(float)),
                     v.to_numpy(float), np.nanmedian(v.to_numpy(float))) for _, _, v in use])
        # 스케일 차가 큰 설계행렬은 정규방정식을 불안정하게 만든다 → 표준화 후 회귀
        mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0)
        sd = np.where(sd > 1e-12, sd, 1.0)
        Xs = np.column_stack([np.ones(len(g)), (X[:, 1:] - mu) / sd])
        keep = np.isfinite(y)
        if keep.sum() < 12:
            g["sacn_resid"] = np.nan
            out.append(g)
            continue
        try:
            beta, *_ = np.linalg.lstsq(Xs[keep], y[keep], rcond=None)
            resid = np.full(len(g), np.nan)
            resid[keep] = y[keep] - Xs[keep] @ beta
        except Exception:
            resid = np.full(len(g), np.nan)
        g["sacn_resid"] = resid
        out.append(g)

    R = pd.concat(out, ignore_index=True)
    n_ok = int(R["sacn_resid"].notna().sum())
    LOG.ok(f"직교화 [{window}] 완료 — 잔차 산출 {n_ok:,}/{len(R):,}행 "
           f"({100*n_ok/max(len(R),1):.1f}%)")
    if dropped:
        LOG.table([[k, f"{v}"] for k, v in dropped.most_common()],
                  ["결측으로 제외된 회귀항", "시점 수"], ["l", "r"],
                  title="§6.3 직교화 — 시점별로 빠진 항 (통째 결측인 항만 제외)")
        open_question("OQ-04", "직교화 회귀항 결측",
                      f"일부 시점에서 회귀항이 통째로 결측이다: {dict(dropped)}",
                      "해당 시점에서 그 항만 제외하고 회귀했다(시점 자체를 버리거나 0으로 채우지 않음).",
                      "직교화 강도가 시점별로 균일하지 않다. 원신호 버전을 반드시 병기해 비교한다.")
    try:
        c = R[["sacn_raw", "sacn_resid"]].corr().iloc[0, 1]
        LOG.info(f"원신호 vs 직교화 신호 상관 = {c:.3f} "
                 f"({'대부분 사이즈/업종/반전으로 설명됨' if abs(c) < 0.5 else '고유 정보가 상당 부분 남음'})")
    except Exception:
        pass
    return R.drop(columns=["month_attr"], errors="ignore")


def attach_attrs(P: pd.DataFrame, uni_panel: pd.DataFrame,
                 cols: Sequence[str] = ("mktcap", "market", "sector", "bm")) -> pd.DataFrame:
    """유니버스 속성을 신호 패널에 붙인다 — 이미 있는 컬럼은 건드리지 않는다.

    ★ orthogonalize() 가 mktcap/bm/sector 를 이미 병합해 둔다. 그걸 모르고 다시 merge 하면
      pandas 가 mktcap_x / mktcap_y 로 쪼개고 'mktcap' 이라는 이름은 사라진다.
      하류(run_quantile_backtest)는 결측 컬럼을 NaN 으로 관대하게 처리하므로 예외 없이
      전 종목이 'small' 슬리피지로 계산되는 조용한 오류가 된다. 여기서 원천 차단한다.
    """
    if P is None or not len(P):
        return P
    need = [c for c in cols if c not in P.columns]
    if not need:
        return P
    U = uni_panel[["code", "month"] + [c for c in need if c in uni_panel.columns]].copy()
    if U.shape[1] <= 2:
        return P
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])
    U = U.drop_duplicates(["code", "month"])
    d = P.copy()
    d["code"] = d["code"].astype(str)
    # 주간 리밸런싱 시점은 월말이 아니므로 '그 시점에 알 수 있던' 직전 월말 속성을 쓴다
    mm = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    d["_m"] = np.where(as_ts_series(d["date"]) >= mm, mm, mm - pd.offsets.MonthEnd(1))
    d["_m"] = as_ts_series(d["_m"])
    d = d.merge(U.rename(columns={"month": "_m"}), on=["code", "_m"], how="left")
    return d.drop(columns=["_m"], errors="ignore")


def build_signal_panel(LM: LinkMatrices, grid: PriceGrid, uni_panel: pd.DataFrame,
                       months: pd.DatetimeIndex, window: str, rebal: str) -> pd.DataFrame:
    """신호 패널 조립: 원신호 + 직교화 + 익영업일 실행가 + 다음 리밸까지의 전향수익률."""
    rebals = rebalance_dates(months, grid, rebal)
    if not rebals:
        return pd.DataFrame()
    S = compute_sacn(LM, grid, uni_panel, rebals, window)
    if not len(S):
        return S
    S = orthogonalize(S, uni_panel, grid, window)

    # 익영업일 실행가 (SPEC 불변 규칙) + 다음 리밸 실행가까지의 수익률
    ex: Dict[pd.Timestamp, Tuple[np.ndarray, Optional[pd.Timestamp]]] = {}
    for t in rebals:
        ex[as_ts(t)] = grid.exec_price(t)
    frames = []
    for i, t in enumerate(rebals):
        t = as_ts(t)
        px0, d0 = ex[t]
        if d0 is None:
            continue
        nxt = as_ts(rebals[i + 1]) if i + 1 < len(rebals) else None
        px1, d1 = ex[nxt] if nxt is not None else (None, None)
        sub = S[S["date"] == t]
        if not len(sub):
            continue
        gi = np.array([grid.cpos.get(c, -1) for c in sub["code"]])
        p0 = np.where(gi >= 0, px0[np.clip(gi, 0, len(px0) - 1)], np.nan)
        if px1 is not None:
            p1 = np.where(gi >= 0, px1[np.clip(gi, 0, len(px1) - 1)], np.nan)
            with np.errstate(all="ignore"):
                fr = np.where((p0 > 0) & np.isfinite(p0) & np.isfinite(p1), p1 / p0 - 1.0, np.nan)
        else:
            fr = np.full(len(sub), np.nan)
        g = sub.copy()
        g["exec_px"] = p0.astype("float32")
        g["exec_date"] = d0
        g["fwd_ret"] = fr.astype("float32")
        g["next_date"] = d1
        frames.append(g)
    P = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(P):
        # 신호일과 수익 구간이 겹치면 실패로 간주한다 (SPEC §8)
        bad = (as_ts_series(P["exec_date"]) <= as_ts_series(P["date"])).sum()
        if bad:
            raise RuntimeError(f"[누수] 실행일이 신호일보다 이르거나 같은 행이 {bad:,}건 있습니다. "
                               f"익영업일 앵커가 깨졌습니다 — 백테스트를 진행하지 않습니다.")
        LOG.ok(f"신호 패널 [{window}/{rebal}] {len(P):,}행 · {P['date'].nunique()}시점 · "
               f"전향수익 보유 {int(P['fwd_ret'].notna().sum()):,}행")
    return P
