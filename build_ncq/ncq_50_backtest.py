

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 6 — 12개월 오버랩 코호트 백테스트 · 벤치마크 · 성과지표                              ║
# ║                                                                                          ║
# ║  입력 : SIG(신호) · pxm(월말 패널) · sec · Universe · months                                ║
# ║  출력 : BT{returns, holdings, cohorts, label}                                              ║
# ║  실패 : 신호가 없는 달은 예외가 아니라 '현금 보유'다. 강제 편입하지 않는다(명세 §10).       ║
# ║                                                                                          ║
# ║  ── 구조 (명세 §10) ────────────────────────────────────────────────────────────────────  ║
# ║   · 매월 1/H 코호트를 신규 편입하고 H개월 뒤 청산하는 **오버랩 포트폴리오**                 ║
# ║   · 코호트 내 동일가중. 신호 없는 코호트 슬롯은 현금(수익 0) — 억지로 채우지 않는다         ║
# ║   · 체결 = 월말 신호 → **다음 영업일 시가**(pxm.exec_px). 당일 종가 체결은 미래누수다       ║
# ║   · 상장폐지: 폐지 직전가 -50% 적용 후 현금화. 누락 처리 금지(= 생존자편향)                 ║
# ║   · 거래정지: 정지 직전가로 마킹(수익 0), 재개 시 실가 반영                                 ║
# ║   · 종목당 상한: 편입 시점 20일 ADV 의 10% (3일 내 청산 가능 규모). 초과분은 현금           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시, 총부담 기준). 비용의 '비대칭'을 만들기 위해 쓴다.
NCQ_TAX_SCHEDULE = [("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
                    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015)]
NCQ_COMMISSION = 0.00015          # 편도 수수료 0.015%


def ncq_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = NCQ_TAX_SCHEDULE[0][1]
    for d, r in NCQ_TAX_SCHEDULE:
        if t is not None and t >= as_ts(d):
            rate = r
    return rate


def ncq_split_cost(cost_roundtrip: float, entry_dt, exit_dt) -> Tuple[float, float]:
    """왕복 비용을 진입/청산으로 쪼갠다.

    ★ 왕복 총액은 사용자가 지정한 값(민감도 축)을 **정확히** 지킨다. 다만 매도 쪽에만 붙는
      증권거래세 때문에 실제 부담은 비대칭이므로, 세율만큼을 청산 쪽에 얹고 나머지 슬리피지를
      균등 분배한다. 이렇게 하면 '왕복 1.8%' 라는 계약을 지키면서 세율 이력도 반영된다.
    """
    tax = ncq_sell_tax(exit_dt)
    rest = float(cost_roundtrip) - 2 * NCQ_COMMISSION - tax
    slip = max(0.0, rest / 2.0)
    entry = NCQ_COMMISSION + slip
    exit_ = NCQ_COMMISSION + slip + tax
    if rest < 0:                       # 지정 왕복비용이 세금+수수료보다 작으면 균등 분배로 낮춘다
        entry = exit_ = max(0.0, float(cost_roundtrip) / 2.0)
    return entry, exit_


def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    """월별 수익률 시계열의 성과 지표. 값이 정의되지 않으면 NaN 으로 둔다(0으로 채우지 않음)."""
    if R is None or len(R) == 0 or "ret" not in R.columns:
        return {}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / 12.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = float(r.std(ddof=1) * math.sqrt(12)) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = float(dn.std(ddof=1) * math.sqrt(12)) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, t = hac_tstat(r, lags=12)
    return {
        "월수": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC12)": t, "최장언더워터(월)": int(mx),
        "평균종목수": float(pd.to_numeric(R.get("n"), errors="coerce").mean())
        if "n" in R.columns else np.nan,
        "월평균비용": float(pd.to_numeric(R.get("cost"), errors="coerce").mean())
        if "cost" in R.columns else np.nan,
        "월평균현금비중": float(pd.to_numeric(R.get("cash"), errors="coerce").mean())
        if "cash" in R.columns else np.nan,
    }


def _ncq_ret_matrix(pxm: pd.DataFrame, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(월 × 종목) 수익률 행렬과 ADV 행렬. 종목별 루프를 없애기 위한 벡터화 준비."""
    if pxm is None or pxm.empty:
        return (pd.DataFrame(index=months), pd.DataFrame(index=months))
    p = pxm.drop_duplicates(["code", "month"], keep="last")
    RM = p.pivot(index="month", columns="code", values="fwd_ret").reindex(months)
    AM = (p.pivot(index="month", columns="code", values="adv20").reindex(months)
          if "adv20" in p.columns else pd.DataFrame(index=months))
    return RM, AM


def run_overlap_backtest(SIG: pd.DataFrame, pxm: pd.DataFrame, sec: pd.DataFrame,
                         uni_obj: Optional["Universe"], months: pd.DatetimeIndex,
                         hold_months: Optional[int] = None, sel_col: str = "selected",
                         cost_roundtrip: Optional[float] = None, adv_cap: bool = True,
                         label: str = "NCQ") -> dict:
    """오버랩 코호트 백테스트.

    수익률 인덱싱 규약: 월 t 의 수익률은 'exec_px(t) → exec_px(t+1)' 사이의 실현분이다
    (pxm.fwd_ret 과 동일). 월말 신호 → 익영업일 시가 진입이므로, 월 t 에 편입한 코호트는
    월 t 의 수익률부터 받는다. 이 규약을 벤치마크·플라시보에도 **동일하게** 적용한다.
    """
    H = int(hold_months or NCQ_HOLD_MONTHS)
    cost = float(cost_roundtrip if cost_roundtrip is not None else NCQ_COST_ROUNDTRIP)
    empty = {"returns": pd.DataFrame(columns=["month", "ret", "ret_gross", "n", "turnover",
                                              "cost", "cash", "equity"]),
             "holdings": pd.DataFrame(columns=["month", "code", "weight", "ret", "cohort", "z"]),
             "cohorts": pd.DataFrame(columns=["cohort", "code", "entry_month", "exit_month",
                                              "ret_h", "n_months"]),
             "label": label}
    if SIG is None or SIG.empty or sel_col not in SIG.columns:
        return empty

    RM, AM = _ncq_ret_matrix(pxm, months)
    if RM.empty:
        LOG.warn("수익률 행렬이 비어 백테스트를 수행할 수 없습니다(가격 패널 확인).")
        return empty
    mon_pos = {m: i for i, m in enumerate(months)}
    delist = {}
    if uni_obj is not None:
        try:
            delist = uni_obj.delisting_map()
        except Exception:
            delist = {}

    S = SIG[SIG[sel_col].fillna(False).astype(bool)].copy()
    S = S[S["month"].isin(months)]
    if S.empty:
        LOG.warn(f"[{label}] 선정된 이벤트가 없어 전 구간 현금 보유가 됩니다.")
        return empty

    n_m = len(months)
    port_ret = np.zeros(n_m)
    port_cost = np.zeros(n_m)
    invested = np.zeros(n_m)         # 실제 투자된 비중(나머지는 현금)
    n_names = np.zeros(n_m)
    turnover = np.zeros(n_m)
    holdings: List[dict] = []
    cohorts: List[dict] = []
    slot_w = 1.0 / float(H)          # 코호트 슬롯당 자본 배분 (신호 없으면 현금)

    for c_month, g in S.groupby("month", observed=True):
        c0 = mon_pos.get(c_month)
        if c0 is None:
            continue
        names = [c for c in g["code"].astype(str).tolist() if c in RM.columns]
        if not names:
            continue
        zs = dict(zip(g["code"].astype(str), pd.to_numeric(g.get("z"), errors="coerce")))
        k = len(names)
        w_each = slot_w / k

        # ── 종목당 상한 = 편입 시점 20일 ADV × 참여율. 초과분은 현금으로 남긴다(§10, R4) ──
        if adv_cap and not AM.empty and c_month in AM.index:
            adv = pd.to_numeric(AM.loc[c_month].reindex(names), errors="coerce").to_numpy()
            cap_krw = adv * NCQ_ADV_PARTICIPATION
            cap_w = np.where(np.isfinite(cap_krw) & (cap_krw > 0),
                             cap_krw / max(NCQ_ACCOUNT_KRW, 1.0), 0.0)
            w = np.minimum(np.full(k, w_each), cap_w)
        else:
            w = np.full(k, w_each)
        w = np.where(np.isfinite(w), w, 0.0)
        if w.sum() <= 0:
            continue

        e_cost, x_cost = ncq_split_cost(cost, c_month, months[min(c0 + H, n_m - 1)])
        port_cost[c0] += float(w.sum()) * e_cost
        turnover[c0] += float(w.sum())

        alive = np.ones(k, dtype=bool)
        haircut_done = np.zeros(k, dtype=bool)
        cum = np.ones(k)
        n_held = np.zeros(k, dtype=int)
        for h in range(H):
            t = c0 + h
            if t >= n_m:
                break
            m_t = months[t]
            row = RM.loc[m_t].reindex(names)
            r = pd.to_numeric(row, errors="coerce").to_numpy(dtype=float)
            for j, cd in enumerate(names):
                if not alive[j]:
                    r[j] = 0.0
                    continue
                dl = delist.get(cd)
                if dl is not None and pd.notna(dl) and as_ts(dl) <= m_t + pd.offsets.MonthEnd(0):
                    # 상장폐지: 폐지 직전가 -50% 적용 후 현금화 (명세 §10)
                    if not haircut_done[j]:
                        r[j] = NCQ_DELIST_HAIRCUT
                        haircut_done[j] = True
                    else:
                        r[j] = 0.0
                    alive[j] = False
                elif not np.isfinite(r[j]):
                    # 거래정지·데이터 결손 → 정지 직전가로 마킹(수익 0). 재개 시 실가가 들어온다.
                    r[j] = 0.0
                else:
                    n_held[j] += 1
            port_ret[t] += float(np.dot(w, r))
            invested[t] += float(w.sum())
            n_names[t] += float(np.sum(w > 0))
            cum = cum * (1.0 + r)
            for j, cd in enumerate(names):
                holdings.append({"month": m_t, "code": cd, "weight": float(w[j]),
                                 "ret": float(r[j]), "cohort": c_month,
                                 "z": float(zs.get(cd, np.nan))})
            if h == H - 1 or t == n_m - 1:
                port_cost[t] += float(w.sum()) * x_cost
                turnover[t] += float(w.sum())
        ex_i = min(c0 + H, n_m - 1)
        for j, cd in enumerate(names):
            cohorts.append({"cohort": c_month, "code": cd, "entry_month": c_month,
                            "exit_month": months[ex_i], "ret_h": float(cum[j] - 1.0),
                            "n_months": int(n_held[j]), "weight": float(w[j]),
                            "z": float(zs.get(cd, np.nan))})

    R = pd.DataFrame({"month": months, "ret_gross": port_ret, "cost": port_cost,
                      "n": n_names, "turnover": turnover,
                      "cash": np.clip(1.0 - invested, 0.0, 1.0)})
    R["ret"] = R["ret_gross"] - R["cost"]
    R["equity"] = (1.0 + R["ret"].fillna(0.0)).cumprod()
    H_df = pd.DataFrame(holdings) if holdings else pd.DataFrame(
        columns=["month", "code", "weight", "ret", "cohort", "z"])
    C_df = pd.DataFrame(cohorts) if cohorts else pd.DataFrame(
        columns=["cohort", "code", "entry_month", "exit_month", "ret_h", "n_months"])
    LOG.info(f"[{label}] 백테스트 완료 — 코호트 {C_df['cohort'].nunique() if len(C_df) else 0}개 · "
             f"연인원 {len(H_df):,} · 평균 현금비중 {100*R['cash'].mean():.0f}% · "
             f"누적 {100*(R['equity'].iloc[-1]-1):+.1f}%")
    return {"returns": R, "holdings": H_df, "cohorts": C_df, "label": label}


# ── 벤치마크 ────────────────────────────────────────────────────────────────────────────────
def bench_universe_ew(UNI: pd.DataFrame, pxm: pd.DataFrame,
                      months: pd.DatetimeIndex) -> pd.Series:
    """주 벤치마크 — 동일 유니버스 동일가중(Bottom-N EW).

    ★ 이것이 진짜 비교 대상이다. KOSDAQ 지수와 비교하면 '소형주 프리미엄'을 알파로 착각한다.
      같은 유니버스, 같은 유동성 필터, 같은 체결 규약에서 동일가중으로 담았을 때와 비교해야
      신호의 순수 기여가 드러난다.
    """
    if UNI is None or UNI.empty or pxm is None or pxm.empty:
        return pd.Series(np.nan, index=months, name="Bottom-N EW")
    u = UNI[UNI["liq_pass"].fillna(False).astype(bool)][["month", "code"]]
    j = u.merge(pxm[["month", "code", "fwd_ret"]], on=["month", "code"], how="left")
    s = j.groupby("month", observed=True)["fwd_ret"].mean().reindex(months)
    s.name = "Bottom-N EW"
    n = j.groupby("month", observed=True)["code"].size().reindex(months)
    LOG.info(f"주 벤치마크(Bottom-N EW) 구성 — 월평균 {float(n.mean() or 0):,.0f}종목 동일가중")
    return s


def bench_event_ew(SIG: pd.DataFrame, pxm: pd.DataFrame, months: pd.DatetimeIndex,
                   uni_obj=None, sec=None) -> dict:
    """전체 신규커버리지 이벤트를 텍스트 점수와 무관하게 전부 담은 팔 (P4 의 대조군)."""
    if SIG is None or SIG.empty:
        return {"returns": pd.DataFrame(columns=["month", "ret", "equity"]), "label": "이벤트 EW"}
    S = SIG.copy()
    S["_all"] = True
    return run_overlap_backtest(S, pxm, sec, uni_obj, months, sel_col="_all",
                                label="이벤트 EW(텍스트 미사용)")


def bench_index(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """보조 벤치마크 — KOSPI / KOSDAQ. 실패해도 조용히 빈 dict(전략은 주 벤치마크로 판정)."""
    out: Dict[str, pd.Series] = {}
    if fdr is None:
        LOG.info("FinanceDataReader 가 없어 지수 벤치마크를 건너뜁니다 "
                 "(주 벤치마크는 Bottom-N EW 이므로 판정에는 영향 없음).")
        return out
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            d = fdr.DataReader(sym, (months[0] - pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d"),
                               months[-1].strftime("%Y-%m-%d"))
        except Exception as e:                                   # noqa
            LOG.debug(f"지수 {name} 조회 실패: {type(e).__name__}")
            continue
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        s = d.groupby("month")["close"].last().pct_change().reindex(months)
        s.name = name
        out[name] = s
    if out:
        LOG.ok(f"지수 벤치마크 확보: {', '.join(out)}")
    return out


def excess_series(BT: dict, bench: pd.Series) -> pd.Series:
    """전략 − 벤치마크 월별 초과수익. **month 인덱스로 정렬 후 교집합만** 사용한다.

    ★ 위치 기반 뺄셈(np 배열끼리)은 두 시계열의 시작월이 다르면 조용히 어긋난다.
      한 달만 밀려도 t 통계량이 완전히 달라진다 — 반드시 인덱스로 맞춘다.
    """
    if not BT or "returns" not in BT or BT["returns"] is None or len(BT["returns"]) == 0:
        return pd.Series(dtype=float)
    R = BT["returns"].set_index("month")["ret"]
    if bench is None or len(bench) == 0:
        return R
    b = pd.Series(bench).copy()
    b.index = as_ts_series(pd.Series(b.index))
    idx = R.index.intersection(b.index)
    if len(idx) == 0:
        return pd.Series(dtype=float)
    return (R.reindex(idx).fillna(0.0) - b.reindex(idx).fillna(0.0)).sort_index()


def right_tail_contribution(BT: dict) -> dict:
    """우측 꼬리 의존도 — 상위 소수 종목을 빼면 성과가 사라지는가(명세 §11.3-7)."""
    H = BT.get("holdings") if BT else None
    if H is None or len(H) == 0:
        return {}
    contrib = (pd.to_numeric(H["weight"], errors="coerce") *
               pd.to_numeric(H["ret"], errors="coerce"))
    s = contrib.groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(s)
    if n == 0:
        return {}
    base = float(s.sum())
    out = {"총기여": base, "종목수": n}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 기여"] = float(s.iloc[:k].sum())
        out[f"{lab} 제외 후"] = base - float(s.iloc[:k].sum())
    out["기여 상위5"] = ", ".join(f"{c}({v:+.3f})" for c, v in s.head(5).items())
    out["기여 하위5"] = ", ".join(f"{c}({v:+.3f})" for c, v in s.tail(5).items())
    return out
