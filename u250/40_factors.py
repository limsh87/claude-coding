# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §4 팩터 명세 F1~F4 — 각각 독립 실행. 결합 백테스트는 이 명세 범위 밖(§8-1).               ║
# ║                                                                                          ║
# ║  공통 규약                                                                                ║
# ║   · PIT   : 모든 신호는 공시 접수일 + 1영업일부터 사용 가능. 정정 전 원본을 쓴다.           ║
# ║   · 룩어헤드 금지 : 전 기간으로 학습한 정규화 파라미터를 쓰지 않는다.                      ║
# ║   · 미커버 : neutral(랭킹=중앙값 / 필터=통과) 와 exclude(후보에서 제외) 두 방식 모두 산출.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

@dataclass
class FactorSignal:
    factor: str
    variant: str
    obs: pd.DataFrame        # (code, rebal) — 소스가 값을 낼 수 있었던 셀
    sig: pd.DataFrame        # (code, rebal, score) — 실제로 신호가 켜진 셀
    kind: str                # filter | rank | event
    note: str = ""

    def selector(self, univ_by_t: Dict[pd.Timestamp, List[str]], n: Optional[int],
                 uncov: str) -> Callable[[pd.Timestamp], List[str]]:
        cov_by_t = {t: set(g["code"]) for t, g in self.obs.groupby("rebal", observed=True)} \
            if len(self.obs) else {}
        sig_by_t = {t: g for t, g in self.sig.groupby("rebal", observed=True)} if len(self.sig) else {}

        if self.kind == "filter":
            def sel(t):
                cand = list(univ_by_t.get(t, []))
                flagged = set(sig_by_t.get(t, pd.DataFrame(columns=["code"]))["code"])
                out = [c for c in cand if c not in flagged]
                if uncov == "exclude":
                    cov = cov_by_t.get(t, set())
                    out = [c for c in out if c in cov]
                return out
            return sel

        def sel(t):
            cand = list(univ_by_t.get(t, []))
            if not cand:
                return []
            s = sig_by_t.get(t)
            score = pd.Series(np.nan, index=pd.Index(cand, name="code"))
            if s is not None and len(s):
                v = s.set_index("code")["score"]
                score.update(v.reindex(score.index).dropna())
            cov = cov_by_t.get(t, set())
            if uncov == "exclude":
                score = score[[c in cov for c in score.index]]
            else:
                #   중립 = 중앙값 부여. 이 시점 횡단면 중앙값만 쓴다(전 기간 통계 금지).
                med = score.median()
                score = score.fillna(med if np.isfinite(med) else 0.0)
            score = score.dropna()
            if not len(score):
                return []
            if self.kind == "event":
                #   이벤트형: 신호 발생 종목만. N 이 주어지면 점수 상위 N 으로 자른다.
                fired = set(s["code"]) if (s is not None and len(s)) else set()
                score = score[[c in fired for c in score.index]]
                if not len(score):
                    return []
            k = min(int(n or len(score)), len(score))
            return list(score.sort_values(ascending=False).head(k).index)
        return sel


def _ensure_cols(d: pd.DataFrame, cols: Dict[str, Any]) -> pd.DataFrame:
    """원천마다 있는 컬럼이 다르다. 없는 것은 결측으로 세워 둔다 — 추측값으로 채우지 않는다."""
    d = d.copy()
    for c, v in cols.items():
        if c not in d.columns:
            d[c] = v
    return d


def _pit_usable(dt: pd.Series) -> pd.Series:
    """공시 접수일 + 1영업일 (§4 공통규약)."""
    return as_ts_series(dt) + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS)


def _source_span(ev: pd.DataFrame, col: str = "rcept_dt") -> Tuple[pd.Timestamp, pd.Timestamp]:
    if ev is None or not len(ev):
        return pd.NaT, pd.NaT
    s = as_ts_series(ev[col]).dropna()
    return (s.min(), s.max()) if len(s) else (pd.NaT, pd.NaT)


def _obs_cells(codes_seen: Sequence[str], rebals: pd.DatetimeIndex,
               span: Tuple[pd.Timestamp, pd.Timestamp],
               univ_by_t: Dict[pd.Timestamp, List[str]]) -> pd.DataFrame:
    """소스가 '값을 낼 수 있었던' 셀. 종목이 소스 원장에 있고, 시점이 소스 구간 안일 때."""
    lo, hi = span
    seen = set(codes_seen)
    rows = []
    for t in rebals:
        if pd.notna(lo) and (t < lo or t > hi + pd.Timedelta(days=400)):
            continue
        for c in univ_by_t.get(t, []):
            if c in seen:
                rows.append((c, t))
    return pd.DataFrame(rows, columns=["code", "rebal"])


# ── F1. 자본거래·지배구조 이벤트 (하방 제거, 필터형) ────────────────────────────────────────
def build_F1(ev: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t, daily: pd.DataFrame,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F1), **ov}
    if ev is None or not len(ev):
        return FactorSignal("F1", variant, pd.DataFrame(columns=["code", "rebal"]),
                            pd.DataFrame(columns=["code", "rebal", "score"]), "filter",
                            "원천 없음")
    e = _ensure_cols(ev, {"is_private": np.nan, "refix": np.nan, "conv_price": np.nan,
                          "event": ""})
    e["usable"] = _pit_usable(e["rcept_dt"])
    hz = pd.Timedelta(days=int(round(p["horizon_m"] * 30.44)))

    keep = pd.Series(False, index=e.index)
    is_cbbw = e["event"].isin(["E1_CB", "E1_BW"])
    if p["e1_private_only"]:
        #   사모 구분이 결측이면 '사모로 간주'하지 않는다 — 추측 금지. 대신 그 사실을 남긴다.
        keep |= is_cbbw & (e["is_private"] == True)                             # noqa: E712
        n_unknown = int((is_cbbw & e["is_private"].isna()).sum())
        if n_unknown:
            LOG.info(f"[F1/{variant}] 사모 여부 미상인 CB/BW {n_unknown:,}건은 E1 에서 제외했습니다 "
                     f"(추측으로 사모 처리하지 않음).")
    else:
        keep |= is_cbbw
    keep |= e["event"] == "E2_3RD"
    keep |= e["event"] == "E3_OWNER"
    E = e[keep].copy()

    # E4 — 리픽싱 + 현재가가 최초 전환가 대비 임계 이하 (희석 예약 상태)
    e4 = e[is_cbbw & (e["refix"] == True) & e["conv_price"].notna()].copy()      # noqa: E712
    rows = []
    _pv = daily[daily["date"].isin(rebals)][["code", "date", "close"]].copy()
    _pv["code"] = _pv["code"].astype(str)
    px = _pv.pivot_table(index="date", columns="code", values="close", aggfunc="last")
    px.columns = px.columns.astype(str)
    for _, r in e4.iterrows():
        c = r["code"]
        if c not in px.columns:
            continue
        win = px.index[(px.index >= r["usable"]) & (px.index <= r["usable"] + hz)]
        if not len(win):
            continue
        cur = px.loc[win, c]
        hit = cur[cur <= float(r["conv_price"]) * (1.0 + p["e4_refix_drop"])]
        for t in hit.index:
            rows.append((c, t))
    e4_cells = pd.DataFrame(rows, columns=["code", "rebal"]).drop_duplicates()

    # 유효기간 안의 셀로 전개
    out = []
    for t in rebals:
        w = E[(E["usable"] <= t) & (E["usable"] > t - hz)]
        for c in set(w["code"]):
            out.append((c, t))
    sig = pd.DataFrame(out, columns=["code", "rebal"]).drop_duplicates()
    if len(e4_cells):
        sig = pd.concat([sig, e4_cells], ignore_index=True).drop_duplicates()
    sig["score"] = 1.0
    obs = _obs_cells(set(ev["code"]), rebals, _source_span(ev), univ_by_t)
    return FactorSignal("F1", variant, obs, sig, "filter",
                        f"E4 셀 {len(e4_cells):,} · 유효기간 {p['horizon_m']}M")


# ── F2. 내부자 순매수 (상방, 랭킹형) ────────────────────────────────────────────────────────
def build_F2(ins: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t, univ: pd.DataFrame,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F2), **ov}
    empty = FactorSignal("F2", variant, pd.DataFrame(columns=["code", "rebal"]),
                         pd.DataFrame(columns=["code", "rebal", "score"]), "rank", "원천 없음")
    if ins is None or not len(ins):
        return empty
    d = _ensure_cols(ins, {"reason": "", "net_amount": np.nan, "role": ""})
    d["usable"] = _pit_usable(d["rcept_dt"])
    rs = d["reason"].astype(str)
    #   장내매수만 채택. 스톡옵션·상속·증여·담보·무상증자·장외 등은 명시적으로 제외한다.
    inc = rs.str.contains("|".join(map(re.escape, p["reasons_include"])))
    exc = rs.str.contains("|".join(map(re.escape, p["reasons_exclude"])))
    d = d[~exc]
    if ov.get("ceo_only"):
        d = d[d["role"].astype(str).str.contains("대표이사|최대주주")]
    #   순매수 = 장내매수 − 장내매도. 매도 건은 부호가 이미 음수로 들어온다.
    d["signed"] = pd.to_numeric(d["net_amount"], errors="coerce")
    d.loc[inc & (d["signed"] < 0), "signed"] = d.loc[inc & (d["signed"] < 0), "signed"].abs()
    d = d.dropna(subset=["signed", "usable", "code"])
    if not len(d):
        return empty

    lb = pd.Timedelta(days=int(round(p["lookback_m"] * 30.44)))
    denom_col = "market_cap" if p["rank_var"] == "net_buy_over_mktcap" else "adv20"
    den = univ.set_index(["rebal", "code"])[denom_col] if denom_col in univ.columns else None
    rows = []
    for t in rebals:
        w = d[(d["usable"] <= t) & (d["usable"] > t - lb)]
        if not len(w):
            continue
        net = w.groupby("code", observed=True)["signed"].sum()
        net = net[net > 0]
        if not len(net):
            continue
        if den is not None:
            try:
                dv = den.loc[t].reindex(net.index)
            except KeyError:
                dv = pd.Series(np.nan, index=net.index)
            sc = net / dv.replace(0, np.nan)
        else:
            sc = net
        sc = sc.replace([np.inf, -np.inf], np.nan).dropna()
        for c, v in sc.items():
            rows.append((c, t, float(v)))
    sig = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    obs = _obs_cells(set(ins["code"]), rebals, _source_span(ins), univ_by_t)
    return FactorSignal("F2", variant, obs, sig, "rank",
                        f"룩백 {p['lookback_m']}M · 랭킹변수 {p['rank_var']}")


# ── F3. 유동성 개선 (상방, 랭킹형) ──────────────────────────────────────────────────────────
def build_F3(daily: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F3), **ov}
    w = int(p["illiq_window_d"])
    lag = int(p["delta_lag_d"])
    d = daily.sort_values(["code", "date"]).copy()
    g = d.groupby("code", observed=True)
    if ov.get("amount_only"):
        base = g["amount"].transform(lambda s: s.rolling(w, min_periods=max(10, w // 3)).mean())
        d["ILLIQ"] = 1.0 / np.maximum(base, 1.0)          # 거래대금이 클수록 비유동성 낮음
    else:
        d["_x"] = np.abs(d["ret1d"]) / np.maximum(d["amount"], 1.0)
        d["ILLIQ"] = g["_x"].transform(lambda s: s.rolling(w, min_periods=max(10, w // 3)).mean())
    d["logI"] = np.log(np.maximum(d["ILLIQ"], 1e-30))
    d["dlogI"] = d["logI"] - g["logI"].shift(lag)
    d["score"] = d["logI"] if ov.get("use_level") else -d["dlogI"]
    if ov.get("use_level"):
        d["score"] = -d["logI"]                            # 수준: 비유동성이 낮을수록 높은 점수
    snap = d[d["date"].isin(rebals)][["code", "date", "score", "logI", "dlogI"]].copy()
    snap["code"] = snap["code"].astype(str)
    snap = snap.rename(columns={"date": "rebal"})
    sig = snap.dropna(subset=["score"])[["code", "rebal", "score"]]
    obs = snap.dropna(subset=["logI"])[["code", "rebal"]]
    return FactorSignal("F3", variant, obs, sig, "rank",
                        f"윈도 {w}d · 변화 lag {lag}d" + (" · 수준 대조군" if ov.get("use_level") else ""))


def f3_redundancy(daily: pd.DataFrame, sig: pd.DataFrame, rebals: pd.DatetimeIndex) -> dict:
    """§4 F3 중복성 검사 — 12개월 모멘텀·1개월 반전과의 상관. |ρ|>0.5 면 기각."""
    d = daily.sort_values(["code", "date"]).copy()
    d["code"] = d["code"].astype(str)
    px = d.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    px = px.reindex(pd.DatetimeIndex(sorted(set(px.index) | set(rebals)))).ffill().reindex(rebals)
    per = int(periods_per_year())              # 12개월 모멘텀 = 1년치 구간 수
    mom = px / px.shift(per) - 1.0
    rev = px / px.shift(max(1, per // 12)) - 1.0
    S = sig.pivot_table(index="rebal", columns="code", values="score", aggfunc="last")
    rhos_m, rhos_r = [], []
    for t in S.index:
        if t not in mom.index:
            continue
        a = S.loc[t].dropna()
        for src, box in ((mom, rhos_m), (rev, rhos_r)):
            b = src.loc[t].reindex(a.index).dropna()
            if len(b) >= 20:
                box.append(float(pd.Series(a.reindex(b.index)).corr(b, method="spearman")))
    out = dict(rho_mom=float(np.nanmean(rhos_m)) if rhos_m else np.nan,
               rho_rev=float(np.nanmean(rhos_r)) if rhos_r else np.nan)
    out["reject"] = bool(max(abs(out["rho_mom"] or 0), abs(out["rho_rev"] or 0))
                         > SPEC_F3["redundancy_rho"])
    LOG.table([["12개월 모멘텀", f"{out['rho_mom']:+.3f}"],
               ["1개월 반전", f"{out['rho_rev']:+.3f}"],
               ["기각 기준", f"|ρ| > {SPEC_F3['redundancy_rho']}"],
               ["판정", "★기각" if out["reject"] else "통과"]],
              ["대조 신호", "평균 Spearman ρ"], ["l", "r"],
              title="[F3] 중복성 검사 — EW 리밸런싱 자체가 반전 베팅이므로 필수")
    return out


# ── F4. 수주·공급계약 (상방, 이벤트형) ──────────────────────────────────────────────────────
def build_F4(con: pd.DataFrame, fin: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t,
             variant: str, ov: dict, track_cancel: bool = True) -> FactorSignal:
    p = {**dict(SPEC_F4), **ov}
    empty = FactorSignal("F4", variant, pd.DataFrame(columns=["code", "rebal"]),
                         pd.DataFrame(columns=["code", "rebal", "score"]), "event", "원천 없음")
    if con is None or not len(con):
        return empty
    d = _ensure_cols(con, {"ratio_sales": np.nan, "contract_amt": np.nan,
                           "counterparty": "", "is_cancel": False})
    d["usable"] = _pit_usable(d["rcept_dt"])
    if ov.get("counterparty_major"):
        d = d[d["counterparty"].astype(str).str.contains("공공|국가|지자체|공사|공단|대기업|그룹")]
    #   비율은 공시에 이미 들어 있다(계약금액/직전 매출액). 없으면 재무로 직접 만든다.
    need = d["ratio_sales"].isna() & d["contract_amt"].notna()
    if need.any() and fin is not None and len(fin):
        f = fin.dropna(subset=["revenue"]).sort_values("knowledge_date")
        f = f.assign(usable_from=f["knowledge_date"] + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS))
        tmp = pd.merge_asof(d[need].sort_values("usable"), f[["code", "usable_from", "revenue"]],
                            left_on="usable", right_on="usable_from", by="code", direction="backward")
        d.loc[need, "ratio_sales"] = (tmp["contract_amt"] / tmp["revenue"].replace(0, np.nan)).values
    d["ratio_sales"] = pd.to_numeric(d["ratio_sales"], errors="coerce")
    #   공시가 %로 들어오는 경우(예: 25.0 = 25%)를 스케일 감지로 교정한다.
    if d["ratio_sales"].dropna().median() > 3.0:
        LOG.info("[F4] 매출액대비 비율이 백분율(%)로 보입니다 — 100 으로 나눠 비율로 환산했습니다.")
        d["ratio_sales"] = d["ratio_sales"] / 100.0

    hz = pd.Timedelta(days=int(round(p["horizon_m"] * 30.44)))
    live = d[~d["is_cancel"].fillna(False)] if track_cancel else d
    cancels = d[d["is_cancel"].fillna(False)][["code", "usable"]] if track_cancel else \
        pd.DataFrame(columns=["code", "usable"])
    rows = []
    for t in rebals:
        w = live[(live["usable"] <= t) & (live["usable"] > t - hz)]
        if not len(w):
            continue
        if track_cancel and len(cancels):
            #   해지 공시 시점부터 신호 소멸 — 그 종목의 해당 구간 계약을 통째로 무효화한다.
            cc = cancels[(cancels["usable"] <= t) & (cancels["usable"] > t - hz)]["code"]
            w = w[~w["code"].isin(set(cc))]
        agg = w.groupby("code", observed=True)["ratio_sales"].sum()
        agg = agg[agg >= float(p["ratio_threshold"])]
        for c, v in agg.items():
            rows.append((c, t, float(v)))
    sig = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    obs = _obs_cells(set(con["code"]), rebals, _source_span(con), univ_by_t)
    return FactorSignal("F4", variant, obs, sig, "event",
                        f"임계 {p['ratio_threshold']:.2f} · 유효 {p['horizon_m']}M"
                        + ("" if track_cancel else " · ★해지 미처리(대조용)"))


def f3_momentum_neutral_selector(fs: FactorSignal, univ_by_t, daily: pd.DataFrame,
                                 rebals: pd.DatetimeIndex, n: int):
    """§4 F3 이중정렬 — 모멘텀 5분위 안에서만 F3 상위를 뽑는다.

    이렇게 하면 포트폴리오의 모멘텀 노출이 유니버스와 같아지므로, 남는 초과수익은
    모멘텀이 아니라 F3 고유의 것이다. 여기서 초과수익이 소멸하면 F3 은 기각된다.
    """
    d = daily[["code", "date", "close"]].copy()
    d["code"] = d["code"].astype(str)
    px = d.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    px = px.reindex(pd.DatetimeIndex(sorted(set(px.index) | set(rebals)))).ffill().reindex(rebals)
    per = int(periods_per_year())
    mom = px / px.shift(per) - 1.0
    sig_by_t = {t: g.set_index("code")["score"] for t, g in fs.sig.groupby("rebal", observed=True)}

    def sel(t):
        s = sig_by_t.get(t)
        if s is None or t not in mom.index:
            return []
        cand = [c for c in s.index if c in set(univ_by_t.get(t, []))]
        m = mom.loc[t].reindex(cand).dropna()
        if len(m) < 25:
            return []
        s2 = s.reindex(m.index)
        try:
            q = pd.qcut(m.rank(method="first"), 5, labels=False)
        except (ValueError, IndexError):
            return []
        per_q = max(1, n // 5)
        out = []
        for k in range(5):
            sub = s2[q.to_numpy() == k].sort_values(ascending=False)
            out += list(sub.head(per_q).index)
        return out
    return sel
