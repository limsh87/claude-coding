
# ────────────────────────────────────────────────────────────────────────────────────────
#  L3  백테스트 엔진 (분기 리밸런싱) + 비용 모델 (§7.2 / §8.1)
#  ★ 연율화 계수는 4 다(분기). 12 로 쓰면 성과가 통째로 3배로 부풀려진다.
#  · 분기 1회 리밸런싱(3/1, 6/1, 9/1, 12/1). 체결 = 리밸일 이후 첫 거래일 시가.
# ────────────────────────────────────────────────────────────────────────────────────────

PERIODS_PER_YEAR = 4          # 분기 리밸런싱

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
ARC_TAX_SCHEDULE = [
    ("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
]

def arc_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = ARC_TAX_SCHEDULE[0][1]
    for d, r in ARC_TAX_SCHEDULE:
        if t is not None and t >= as_ts(d):
            rate = r
    return rate

def arc_slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격 + 초소형주 최소 스프레드 하한.

    ★ §8.1 이 경고한 대로 초소형주는 스프레드가 알파를 통째로 잠식할 수 있다.
      제곱근 모형만 쓰면 참여율이 낮을 때 비용이 0 에 수렴하는데, 실제로는 호가 스프레드
      절반은 무조건 낸다. 그래서 하한(ARC_MIN_SPREAD_BPS/2)을 강제한다.
    """
    floor = (ARC_MIN_SPREAD_BPS / 2.0) / 1e4
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return max(floor, 0.02)
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(max(floor, ARC_SLIPPAGE_K * math.sqrt(part)))

def _bt_weights(sub: pd.DataFrame, weighting: str) -> np.ndarray:
    """동일가중(기준) 또는 역변동성 가중(병행 산출). 유동성 상한을 water-filling 으로 강제."""
    n = len(sub)
    if n == 0:
        return np.zeros(0)
    if weighting == "invvol" and "vol_q" in sub.columns:
        v = pd.to_numeric(sub["vol_q"], errors="coerce").to_numpy(dtype=float)
        v = np.where(np.isfinite(v) & (v > 1e-6), v, np.nanmedian(v[np.isfinite(v)])
                     if np.isfinite(v).any() else 1.0)
        w = 1.0 / v
        w = w / w.sum() if w.sum() > 0 else np.full(n, 1.0 / n)
    else:
        w = np.full(n, 1.0 / n)

    adv = pd.to_numeric(sub.get("adtv60", pd.Series(np.nan, index=sub.index)),
                        errors="coerce").fillna(0).to_numpy(dtype=float)
    cap = np.where(adv > 0, (adv * ARC_ADV_PARTICIPATION) / max(ARC_ACCOUNT_KRW, 1), 1.0)
    cap = np.clip(cap, 1.0 / (4.0 * n), 1.0)
    # ★ clip 후 재정규화하면 상한이 도로 뚫린다. water-filling 으로 강제한다.
    free = np.ones(n, dtype=bool)
    for _ in range(24):
        over = free & (w > cap)
        if not over.any():
            break
        w[over] = cap[over]
        free &= ~over
        rem = 1.0 - w[~free].sum()
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem) if pool > 1e-12 else (rem / free.sum())
    if w.sum() > 1.0 + 1e-9:
        w = w / w.sum()
    return w

def _bt_pick(elig: pd.DataFrame, k: int, signal_col: str) -> pd.DataFrame:
    """상위 k 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep='first') 는 동점 시 '먼저 나온 행'을 고르는데, 패널은 code 정렬이라
      그건 곧 '종목코드가 작은 순'이다. 보유종목이 데이터가 아니라 정렬의 함수가 된다.
    """
    if not len(elig):
        return elig.iloc[0:0]
    keys = [signal_col] + [c for c in ("FINAL_SCORE", "code")
                           if c in elig.columns and c != signal_col]
    asc = [False] + [False if c == "FINAL_SCORE" else True for c in keys[1:]]
    return elig.sort_values(keys, ascending=asc, kind="mergesort").head(int(k))

def run_backtest(P: pd.DataFrame, rebals: pd.DatetimeIndex, uni, sec: pd.DataFrame,
                 signal_col: str = "FINAL_RANK", apply_costs: bool = True,
                 label: str = "ARC", top_n: Optional[int] = None,
                 weighting: str = None, bottom: bool = False) -> dict:
    """분기 리밸런싱 롱온리 백테스트.

    bottom=True 면 하위 랭크를 담는다(§7.3 부정 신호 검증 전용 — 실제 숏이 아니라
    '하위 그룹의 수익률'을 측정하기 위한 롱 포트폴리오다).
    """
    k_target = int(top_n or ARC_TOP_N_DEFAULT)
    wmode = weighting or ARC_WEIGHTING
    delist = uni.delisting_map() if uni is not None else {}
    rows, holdings = [], []
    prev_w: Dict[str, float] = {}
    n_impute_tot, w_impute_tot, n_adv_miss = 0, 0.0, 0

    need = [c for c in ("code", "asof", "adtv60", "fwd_ret_1q", signal_col, "FINAL_SCORE",
                        "vol_q", "EXCLUDE") if c in P.columns]
    B = P[need].copy() if need else P.copy()

    for t in rebals:
        t = as_ts(t)
        sub = B[B["asof"] == t]
        # ★ 측정 가능한 분기인가. 마지막 리밸일은 다음 리밸일이 없어 전 종목 fwd_ret 이 결측인데,
        #   예전에는 그 분기를 '수익률 0' 으로 성과 시계열에 넣었다. 그러면 CAGR 분모의 연수가
        #   9.75년 대신 10년이 되고, 변동성이 희석되고, 승률 분모가 부풀려진다.
        #   measurable=False 로 표시해 perf_stats 에서 제외한다. 청산 비용만 따로 계상한다.
        measurable = bool(len(sub)) and bool(
            pd.to_numeric(sub["fwd_ret_1q"], errors="coerce").notna().any())
        if sub.empty or not measurable:
            liq_cost = 0.0
            if apply_costs and prev_w:
                liq_cost = sum(abs(v) for v in prev_w.values()) * (
                    ARC_COMMISSION_BPS / 1e4 + arc_sell_tax(t))
            rows.append({"asof": t, "ret": -liq_cost, "ret_gross": 0.0, "n": 0,
                         "turnover": float(sum(abs(v) for v in prev_w.values())),
                         "cost": liq_cost, "n_elig": 0, "n_imputed": 0, "w_imputed": 0.0,
                         "measurable": False})
            prev_w = {}
            continue
        #   (상세 근거는 커밋 로그 참조)
        elig = sub[sub[signal_col].notna()]
        n_elig = len(elig)
        if uni is not None:
            uni.audit_row("신호보유", t, elig["code"].tolist())
        if n_elig == 0:
            rows.append({"asof": t, "ret": 0.0, "ret_gross": 0.0, "n": 0,
                         "turnover": 0.0, "cost": 0.0, "n_elig": 0,
                         "n_imputed": 0, "w_imputed": 0.0, "measurable": True})
            prev_w = {}
            continue

        if bottom:
            pick = elig.sort_values([signal_col, "code"], ascending=[True, True],
                                    kind="mergesort").head(min(k_target, n_elig))
        else:
            pick = _bt_pick(elig, min(k_target, n_elig), signal_col)
        if uni is not None:
            uni.audit_row("최종선정", t, pick["code"].tolist())

        w = _bt_weights(pick, wmode)
        w_new = dict(zip(pick["code"].astype(str), w))
        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0))
                   for c in set(w_new) | set(prev_w))

        cost = 0.0
        if apply_costs:
            #   (상세 근거는 커밋 로그 참조)
            advmap = dict(zip(sub["code"].astype(str),
                              pd.to_numeric(sub.get("adtv60", pd.Series(np.nan, index=sub.index)),
                                            errors="coerce").fillna(0.0)))
            _miss_adv = [c for c in (set(w_new) | set(prev_w)) if advmap.get(c, 0.0) <= 0]
            if _miss_adv:
                n_adv_miss += len(_miss_adv)
            tax = arc_sell_tax(t)
            comm = ARC_COMMISSION_BPS / 1e4
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                notional = abs(dw) * ARC_ACCOUNT_KRW
                sl = arc_slippage(notional, float(advmap.get(c, 0.0)))
                cost += abs(dw) * (comm + sl + (tax if dw < 0 else 0.0))

        ret = 0.0
        fw = dict(zip(pick["code"].astype(str),
                      pd.to_numeric(pick["fwd_ret_1q"], errors="coerce")))
        sig = dict(zip(pick["code"].astype(str),
                       pd.to_numeric(pick[signal_col], errors="coerce")))
        # 측정 불가 종목의 대치값 = 그 분기 유니버스 전체의 중앙값 수익률.
        # 0 으로 채우면 '현금 보유'라는 없는 가정을 넣게 되고, 버리면 표본이 선택된다.
        uni_r = pd.to_numeric(sub["fwd_ret_1q"], errors="coerce")
        fallback = float(uni_r.median()) if uni_r.notna().any() else 0.0
        n_imputed, w_imputed = 0, 0.0
        for c, ww in w_new.items():
            fr = fw.get(c, np.nan)
            dl = delist.get(c)
            # ★ §3.4 2중 방어: 패널이 폐지를 놓쳤어도 여기서 잡는다. 예전에는 위쪽 elig 가
            #   fwd_ret 결측 행을 이미 지워 이 분기가 도달 불가능한 죽은 코드였다.
            if (not np.isfinite(fr)) and dl is not None and pd.notna(dl) and dl > t:
                fr = -1.0
            if not np.isfinite(fr):
                fr = fallback
                n_imputed += 1
                w_imputed += float(ww)
            ret += ww * float(fr)
            holdings.append({"asof": t, "code": c, "weight": float(ww), "ret": float(fr),
                             "signal": float(sig.get(c, np.nan))})
        if n_imputed:
            n_impute_tot += n_imputed
            w_impute_tot += w_imputed
        # ★ ret 는 -1 아래로 내려갈 수 없다. Σw≤1 · fwd≥-1 이므로 gross 는 ≥-1 이지만
        #   비용을 빼면 -1 을 밑돌 수 있고, 그러면 cumprod 가 부호를 뒤집어 파산한 경로가
        #   양의 자본곡선으로 되살아난다(MDD -112% 같은 정의상 불가능한 값이 표에 찍힌다).
        ret = float(max(ret, -1.0))
        rows.append({"asof": t, "ret": max(ret - cost, -1.0), "ret_gross": ret,
                     "n": len(w_new),
                     "turnover": turn, "cost": cost, "n_elig": n_elig,
                     "n_imputed": n_imputed, "w_imputed": w_imputed, "measurable": True})
        prev_w = w_new

    if n_adv_miss:
        LOG.info(f"[{label}] 거래대금(ADTV)을 못 찾은 매매 {n_adv_miss:,}건은 슬리피지 "
                 f"보수 폴백(2%)을 적용했습니다.")
    if n_impute_tot:
        LOG.warn(f"[{label}] 전방수익률 측정 불가 {n_impute_tot:,}건(누적 비중 "
                 f"{w_impute_tot:.2f})을 해당 분기 유니버스 중앙값으로 대치했습니다. "
                 f"거래정지 후 재개 또는 가격 결측 구간입니다 — 폐지 종목은 위 §3.4 경로로 "
                 f"이미 청산 처리되었습니다.")

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
        R["equity_gross"] = (1.0 + R["ret_gross"].fillna(0)).cumprod()
    H = pd.DataFrame(holdings)
    return {"returns": R, "holdings": H, "label": label,
            "eligible": R[["asof", "n_elig"]] if len(R) else pd.DataFrame()}

# ── 성과 지표 (분기 기준) ───────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0, gross: bool = False) -> dict:
    """분기 수익률 시계열 → 성과 지표. ★ 연율화 계수는 4 (분기 4개 = 1년)."""
    if R is None or len(R) == 0:
        return {}
    key = "ret_gross" if (gross and "ret_gross" in R.columns) else "ret"
    # ★ 측정 불가 분기(마지막 리밸일 등)는 성과 통계에서 뺀다. 수익률 0 으로 끼워 넣으면
    #   연수·변동성·승률 분모가 전부 조용히 왜곡된다.
    Rm = R[R["measurable"].astype(bool)] if "measurable" in R.columns else R
    if len(Rm) == 0:
        Rm = R
    r = pd.to_numeric(Rm[key], errors="coerce").fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / float(PERIODS_PER_YEAR)
    # ★ 자본곡선이 0 이하를 '통과'하면 그 경로는 파산이다. 예전에는 최종값(eq[-1])만 봤는데,
    #   1+r<0 이 두 번 나오면 cumprod 가 부호를 두 번 뒤집어 파산 경로가 양의 자본으로
    #   되살아나고 CAGR·MDD·Calmar 가 전부 유한값으로 인쇄됐다(MDD -112% 같은 값).
    ruined = bool(np.any(eq <= 0))
    if ruined:
        cagr = -1.0
    else:
        cagr = (eq[-1] ** (1.0 / years) - 1.0) if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if n > 1 else np.nan
    # ★ Sortino 의 하방편차는 '목표(=rf) 대비' 제곱평균이지, '음수 수익률들의 자기 평균 대비
    #   표본표준편차'가 아니다. 후자는 손실이 비슷한 크기로 반복될수록 0 에 수렴해
    #   손실의 '크기'가 아니라 '균일함'을 보상한다 — 실측에서 정의값 3.88 이 393 으로 나왔다.
    rf_q = rf / float(PERIODS_PER_YEAR)
    _dn = np.minimum(r - rf_q, 0.0)
    dvol = float(np.sqrt((_dn ** 2).mean()) * math.sqrt(PERIODS_PER_YEAR)) if n else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(max(dd.min(), -1.0)) if n else np.nan     # -100% 아래는 정의상 불가
    if ruined:
        mdd = -1.0
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    # ★ 평균 통계도 측정 가능한 분기(Rm)에서만 낸다. 측정 불가 분기는 n=0 ·
    #   turnover=전량청산 으로 기록되므로 원본 R 을 쓰면 평균종목수·평균회전율이 어긋난다.
    return {
        "기간수(분기)": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "분기평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(분기)": int(mx),
        "평균종목수": float(Rm["n"].mean()) if "n" in Rm.columns else np.nan,
        "평균회전율": float(Rm["turnover"].mean()) if "turnover" in Rm.columns else np.nan,
        "평균비용": float(Rm["cost"].mean()) if "cost" in Rm.columns else np.nan,
        "평균편입가능": float(Rm["n_elig"].mean()) if "n_elig" in Rm.columns else np.nan,
    }

def bt_ic(P: pd.DataFrame, signal_col: str = "FINAL_RANK") -> Tuple[float, float, int]:
    """신호의 기간별 Spearman IC / IC-IR."""
    if P is None or P.empty or signal_col not in P.columns or "fwd_ret_1q" not in P.columns:
        return (np.nan, np.nan, 0)
    return info_coef(P[signal_col], P["fwd_ret_1q"], P["asof"].astype(str))

def attach_volatility(P: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """역변동성 가중용 분기 변동성(직전 60거래일 일간수익률 표준편차, 연율화)."""
    P = P.copy()
    if px_daily is None or px_daily.empty:
        P["vol_q"] = np.nan
        return P
    d = px_daily[["code", "date", "close"]].dropna().copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    d["r1"] = d.groupby("code", observed=True)["close"].pct_change()
    d["vol"] = (d.groupby("code", observed=True)["r1"]
                 .transform(lambda s: s.rolling(60, min_periods=20).std()) * math.sqrt(252))
    # ★ 리밸일마다 일봉 전체를 필터링하지 않는다(메모리 스파이크). merge_asof 한 번으로 끝낸다.
    right = (d[["code", "date", "vol"]].dropna(subset=["date", "code"])
             .sort_values("date", kind="stable"))
    right["code"] = right["code"].astype(str)
    left = P[["code", "asof"]].copy()
    left["code"] = left["code"].astype(str)
    left["asof"] = as_ts_series(left["asof"])
    left = left.dropna(subset=["asof"]).sort_values("asof", kind="stable")
    try:
        V = pd.merge_asof(left, right, left_on="asof", right_on="date", by="code",
                          direction="backward", allow_exact_matches=False)
        V = (V.dropna(subset=["vol"])[["code", "asof", "vol"]]
              .rename(columns={"vol": "vol_q"})
              .drop_duplicates(["code", "asof"], keep="last"))
        P = P.merge(V, on=["code", "asof"], how="left")
    except Exception as e:                                       # noqa
        LOG.warn(f"변동성 as-of 결합 실패({type(e).__name__}) — 역변동성 가중을 건너뜁니다.")
        P["vol_q"] = np.nan
    if "vol_q" not in P.columns:
        P["vol_q"] = np.nan
    return P

def benchmark_returns(rebals: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """벤치마크 분기 수익률. FDR 이 없으면 빈 dict — 그 사실을 로그로 남긴다."""
    out: Dict[str, pd.Series] = {}
    if fdr is None or len(rebals) == 0:
        LOG.info("FinanceDataReader 가 없어 지수 벤치마크를 건너뜁니다 (절대수익 기준으로 보고).")
        return out
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            d = fdr.DataReader(sym, as_ts(rebals[0]) - pd.DateOffset(months=4),
                               as_ts(rebals[-1]) + pd.DateOffset(months=4))
        except Exception:
            d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d = d.dropna(subset=["date", "close"]).sort_values("date")
        vals = []
        for i, t in enumerate(rebals):
            t = as_ts(t)
            nxt = as_ts(rebals[i + 1]) if i + 1 < len(rebals) else None
            a = d[d["date"] >= t].head(1)
            b = d[d["date"] >= nxt].head(1) if nxt is not None else pd.DataFrame()
            if len(a) and len(b):
                vals.append(float(b["close"].iloc[0]) / float(a["close"].iloc[0]) - 1.0)
            else:
                vals.append(np.nan)
        out[name] = pd.Series(vals, index=pd.DatetimeIndex(rebals))
    if out:
        LOG.ok(f"벤치마크 확보: {', '.join(out)} (분기 수익률)")
    return out

def equal_weight_universe_return(P: pd.DataFrame) -> pd.Series:
    """U-1000 동일가중 수익률 — 초과수익 계산의 1순위 벤치마크.

    ★ 지수(KOSPI/KOSDAQ)는 시총가중이라 대형주가 지배한다. 우리 유니버스는 소형주 하위 1000
      이므로, 지수 대비 초과수익은 '소형주 프리미엄'을 알파로 착각하게 만든다.
      같은 유니버스의 동일가중 수익률과 비교해야 신호의 순기여가 드러난다.
    """
    if P is None or P.empty or "fwd_ret_1q" not in P.columns:
        return pd.Series(dtype=float)
    g = P.dropna(subset=["fwd_ret_1q"]).groupby("asof", observed=True)["fwd_ret_1q"].mean()
    return g.sort_index()
