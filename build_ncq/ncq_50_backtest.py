

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


def ncq_gap_return_matrix(pxm: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """거래정지 구간의 '갭 수익'을 재개월에 계상하기 위한 행렬 (월 × 종목).

    ★ 왜 필요한가 — 조용히 사라지던 손실
      build_price_panel 은 월 연속성이 끊기면 fwd_ret 을 NaN 으로 만든다(건너뛴 달의 수익을
      한 달 수익으로 계상하지 않기 위함). 그런데 백테스트는 NaN 을 '정지 마킹 = 0%' 로 처리한다.
      두 방어가 겹치면 **정지 직전 → 재개 사이의 갭 수익이 어느 쪽에도 계상되지 않는다.**
      7개월 정지 후 -80% 로 재개한 종목의 -80% 가 통째로 증발하고 코호트 수익이 과대계상된다.
      폐지원장에 없는 '정지→재개' 종목이라 -50% 해어컷 경로도 타지 않는다.

    ★ 모델링 원칙: **정지된 주식은 팔 수 없다.** 그래서 정지 구간은 0% 로 두되, 재개 시점에
      exec_px(재개) / exec_px(정지직전) - 1 을 한 번에 계상한다. 보유기간이 정지 중에 끝나면
      청산이 재개월로 이연된다(현실과 같다).

    반환: 재개월(month) × 종목(code) 행렬. 값은 갭 수익. 갭이 없으면 NaN.
    """
    empty = pd.DataFrame(index=months)
    if pxm is None or pxm.empty or "exec_px" not in pxm.columns:
        return empty
    p = (pxm.dropna(subset=["code", "month", "exec_px"])
            .drop_duplicates(["code", "month"], keep="last")
            .sort_values(["code", "month"]))
    if p.empty:
        return empty
    mi = (as_ts_series(p["month"]).dt.year * 12 + as_ts_series(p["month"]).dt.month)
    p = p.assign(_mi=mi.to_numpy())
    g = p.groupby("code", observed=True)
    prev_px = g["exec_px"].shift(1)
    prev_mi = g["_mi"].shift(1)
    gap_m = p["_mi"] - prev_mi
    is_gap = gap_m.notna() & (gap_m > 1) & prev_px.notna() & (prev_px > 0)
    if not bool(is_gap.any()):
        return empty
    r = pd.DataFrame({
        "month": as_ts_series(p.loc[is_gap, "month"]),
        "code": p.loc[is_gap, "code"].astype(str),
        "gap_ret": (pd.to_numeric(p.loc[is_gap, "exec_px"], errors="coerce") /
                    pd.to_numeric(prev_px[is_gap], errors="coerce") - 1.0),
        "gap_months": gap_m[is_gap].astype(float),
    }).dropna(subset=["gap_ret"])
    if r.empty:
        return empty
    GM = r.drop_duplicates(["month", "code"], keep="last").pivot(
        index="month", columns="code", values="gap_ret").reindex(months)
    LOG.info(f"거래정지 갭 {len(r):,}건을 재개월 수익으로 계상합니다 "
             f"(평균 {r['gap_months'].mean():.1f}개월 정지 · 평균 갭수익 "
             f"{100*r['gap_ret'].mean():+.1f}%). 계상하지 않으면 정지 중 손실이 증발합니다.")
    return GM


def ncq_effective_return_matrix(pxm: pd.DataFrame, months: pd.DatetimeIndex,
                                delist_map: Optional[dict] = None
                                ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """전략과 벤치마크가 **똑같이** 쓰는 실효 수익률 행렬을 한 번만 만든다.

    ★ 왜 공유해야 하는가 — 비대칭이 곧 가짜 알파다
      예전에는 전략만 상장폐지 -50% 와 정지 마킹 0% 를 짊어지고, 주 벤치마크(Bottom-N EW)는
      `mean(skipna=True)` 로 그 종목들을 **평균에서 조용히 빼** 버렸다. 그러면 벤치마크는
      생존자편향이 걸린 채 위로 뜨고, 전략은 아래로 눌린다. 부호가 어느 쪽으로 틀리든
      "같은 규약으로 비교했다"는 주장이 성립하지 않는다. 한 행렬을 공유해 원천 차단한다.

    적용 순서:
      ① 거래정지 갭 수익을 재개월에 곱셈으로 합성 (ncq_gap_return_matrix)
      ② 상장폐지: 폐지일을 포함하는 **선도 수익 창**의 달에 -50%, 그 이후는 0 (명세 §10)
         (fwd_ret(m) 은 exec_px(m)→exec_px(m+1) 구간이므로 폐지월의 한 달 **전** 인덱스다)
      ③ 나머지 결측은 소비자가 0(정지 마킹)으로 채운다 — 여기서 채우지 않는다.

    반환: (E 실효수익행렬, AM 거래대금행렬)
    """
    RM, AM = _ncq_ret_matrix(pxm, months)
    if RM.empty:
        return RM, AM
    E = RM.copy()

    GM = ncq_gap_return_matrix(pxm, months)
    if not GM.empty:
        GM = GM.reindex(index=E.index, columns=E.columns)
        m = GM.notna()
        if bool(m.to_numpy().any()):
            E = E.where(~m, (1.0 + GM.fillna(0.0)) * (1.0 + E.fillna(0.0)) - 1.0)

    n_del = 0
    if delist_map:
        pos = {mm: i for i, mm in enumerate(months)}
        cols = set(map(str, E.columns))
        for code, dd in delist_map.items():
            c = str(code)
            if c not in cols or dd is None or pd.isna(dd):
                continue
            d = as_ts(dd)
            # 폐지일이 속한 달의 한 달 전 인덱스 = 그 폐지를 포함하는 선도수익 창
            hit = None
            for mm, i in pos.items():
                if mm >= d:
                    hit = i - 1
                    break
            if hit is None or hit < 0:
                continue
            E.iloc[hit, E.columns.get_loc(c)] = NCQ_DELIST_HAIRCUT
            if hit + 1 < len(months):
                E.iloc[hit + 1:, E.columns.get_loc(c)] = 0.0
            n_del += 1
    if n_del:
        LOG.info(f"상장폐지 {n_del:,}종목에 폐지 직전가 {100*NCQ_DELIST_HAIRCUT:+.0f}% 후 현금화를 "
                 f"적용했습니다 — **전략과 벤치마크 양쪽에 동일하게** 반영됩니다(생존자편향 차단).")
    return E, AM


def run_overlap_backtest(SIG: pd.DataFrame, pxm: pd.DataFrame, sec: pd.DataFrame,
                         uni_obj: Optional["Universe"], months: pd.DatetimeIndex,
                         hold_months: Optional[int] = None, sel_col: str = "selected",
                         cost_roundtrip: Optional[float] = None, adv_cap: bool = True,
                         label: str = "NCQ") -> dict:
    """오버랩 코호트 백테스트 — **시간축 순차 포트폴리오 시뮬레이터**.

    수익률 인덱싱 규약: 월 t 의 수익률은 'exec_px(t) → exec_px(t+1)' 사이의 실현분이다
    (pxm.fwd_ret 과 동일). 월말 신호 → 익영업일 시가 진입이므로, 월 t 에 편입한 코호트는
    월 t 의 수익률부터 받는다. 이 규약을 벤치마크·플라시보에도 **동일하게** 적용한다.

    ★★ 왜 코호트별 루프가 아니라 시간축 루프인가 — 두 가지 회계 오류를 원천 차단한다
      ① 진입 가중치를 고정한 채 매달 dot(w, r) 을 더하면 '비용 0짜리 월간 리밸런싱'이
         공짜로 섞인다(변동성 하베스팅). 손계산: H=2, A[+100%,-50%], B[-50%,+100%] 를
         25%/25% 로 담으면 진짜 buy&hold 는 0.00% 인데 고정가중은 +26.6% 가 나온다.
      ② 코호트를 독립적으로 굴린 뒤 손익을 더하면, 그 손익이 '초기 자본 대비' 비율인데
         equity 는 '현재 NAV 대비' 수익률로 복리시킨다. NAV 가 움직이는 순간 어긋난다.
      → NAV 를 하나 들고 시간 순으로 진행하며 (진입 → 수익반영 → 청산) 순서를 지킨다.
        매월 NAV 의 1/H 를 새 코호트에 배분하고, 신호가 없으면 그 슬롯은 현금으로 남는다.

    ★ 거래정지 종목은 팔 수 없다. 보유기간이 끝나도 첫 거래 가능 시점까지 청산이 이연된다.
    ★ 패널 마지막 달은 fwd_ret 이 정의되지 않으므로 청산하지 않고 시가평가로 남긴다.
      (거기서 전 코호트에 청산비용을 물리면 결정론적 가짜 손실이 표본에 들어간다)
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

    delist = {}
    if uni_obj is not None:
        try:
            delist = uni_obj.delisting_map()
        except Exception:
            delist = {}
    # ★ 벤치마크와 **동일한** 실효 수익률 행렬을 쓴다(폐지·정지 처리 비대칭 차단).
    RM, AM = ncq_effective_return_matrix(pxm, months, delist)
    if RM.empty:
        LOG.warn("수익률 행렬이 비어 백테스트를 수행할 수 없습니다(가격 패널 확인).")
        return empty

    S = SIG[SIG[sel_col].fillna(False).astype(bool)].copy()
    S = S[S["month"].isin(months)]
    if S.empty:
        LOG.warn(f"[{label}] 선정된 이벤트가 없어 전 구간 현금 보유가 됩니다.")
        return empty
    by_month = {as_ts(mm): gg for mm, gg in S.groupby("month", observed=True)}

    n_m = len(months)
    slot_frac = 1.0 / float(H)
    cols = set(map(str, RM.columns))
    # ★ 현금을 명시적 상태로 든다. nav = cash + Σ(포지션 시가) 라는 항등식이 '구조적으로'
    #   성립해야 한다. 비용을 NAV 에서만 빼면 포지션 시가 합이 NAV 를 넘어(=암묵적 레버리지)
    #   가중치 합 > 1 이 되고, 그만큼 성과가 부풀려진다. N6 계약검정이 이걸 잡는다.
    cash = 1.0
    nav = 1.0
    port_ret = np.zeros(n_m); port_cost = np.zeros(n_m)
    invested = np.zeros(n_m); n_names = np.zeros(n_m); turnover = np.zeros(n_m)
    holdings: List[dict] = []; cohorts: List[dict] = []
    open_pos: List[dict] = []
    n_defer = n_open_at_end = n_cohort = 0
    adv_bind_n = adv_bind_d = 0

    for t, m_t in enumerate(months):
        r_row = RM.loc[m_t]
        adv_row = AM.loc[m_t] if (not AM.empty and m_t in AM.index) else None
        nav_open = cash + float(sum(float(np.sum(p["val"] * p["alive"])) for p in open_pos))
        nav = nav_open

        # ── ① 진입 (이번 달 신호로 만든 새 코호트) ────────────────────────────────────────
        g = by_month.get(as_ts(m_t))
        if g is not None and len(g):
            names = [c for c in g["code"].astype(str).tolist() if c in cols]
            if names:
                k = len(names)
                # NAV 의 1/H 를 배분(초기자본이 아니라). 현금이 모자라면 있는 만큼만 — 차입 없음.
                slot = min(nav_open * slot_frac, max(cash, 0.0))
                if slot <= 0:
                    slot = 0.0
                v_each = slot / k if k else 0.0
                v = np.full(k, v_each)
                if adv_cap and adv_row is not None:
                    adv = pd.to_numeric(adv_row.reindex(names), errors="coerce").to_numpy()
                    cap_krw = adv * NCQ_ADV_PARTICIPATION
                    # 상한은 '금액' 기준이므로 가정 계좌규모로 NAV 배수를 환산해 비교한다
                    cap_v = np.where(np.isfinite(cap_krw) & (cap_krw > 0),
                                     cap_krw / max(NCQ_ACCOUNT_KRW, 1.0), 0.0)
                    v = np.minimum(v, cap_v)
                    adv_bind_n += int(np.sum(v < v_each - 1e-15)); adv_bind_d += k
                v = np.where(np.isfinite(v) & (v > 0), v, 0.0)
                if v.sum() > 0:
                    e_cost, x_cost = ncq_split_cost(
                        cost, m_t, months[min(t + H, n_m - 1)])
                    # 총 지출 = 매수대금 + 수수료 = slot. 즉 실제로 사는 금액은 slot/(1+e_cost).
                    # 이렇게 해야 현금에서 나간 돈과 포지션 시가가 정확히 맞는다.
                    v = v / (1.0 + e_cost)
                    outlay = float(v.sum()) * (1.0 + e_cost)
                    port_cost[t] += float(v.sum()) * e_cost
                    cash -= outlay
                    turnover[t] += float(v.sum()) / max(nav_open, 1e-12)
                    open_pos.append({
                        "cohort": m_t, "names": names, "val": v.copy(), "v0": v.copy(),
                        "alive": np.ones(k, dtype=bool), "h": 0, "x_cost": x_cost,
                        "val_final": np.full(k, np.nan),
                        "n_held": np.zeros(k, dtype=int),
                        "exit_i": np.full(k, np.nan),
                        "z": {c: float(x) for c, x in zip(g["code"].astype(str),
                                                          pd.to_numeric(g.get("z"),
                                                                        errors="coerce"))},
                    })
                    n_cohort += 1

        # ── ② 수익 반영 (이번 달에 진입한 코호트도 이 달 수익부터 받는다) ────────────────
        pnl = 0.0
        for pos in open_pos:
            nm, al = pos["names"], pos["alive"]
            r = pd.to_numeric(r_row.reindex(nm), errors="coerce").to_numpy(dtype=float)
            fin = np.isfinite(r)
            r = np.where(fin & al, r, 0.0)          # 정지·결측은 직전가 마킹(0%)
            pos["n_held"] += (fin & al).astype(int)
            val_before = pos["val"] * al
            pnl += float(np.dot(val_before, r))
            invested[t] += float(val_before.sum())
            n_names[t] += float(np.sum(al & (val_before > 0)))
            for j, cd in enumerate(nm):
                if al[j]:
                    holdings.append({"month": m_t, "code": cd,
                                     "weight": float(val_before[j] / max(nav_open, 1e-12)),
                                     "ret": float(r[j]), "cohort": pos["cohort"],
                                     "z": float(pos["z"].get(cd, np.nan))})
            pos["val"] = np.where(al, pos["val"] * (1.0 + r), pos["val"])
            pos["_fin"] = fin

        # ── ③ 청산 (보유기간 만료 + 거래 가능). 정지 중이면 이연 ─────────────────────────
        sold_cost = 0.0
        for pos in open_pos:
            al, fin = pos["alive"], pos.get("_fin", np.ones(len(pos["names"]), dtype=bool))
            due = al & (pos["h"] >= H - 1)
            sell = due & fin
            if t == n_m - 1:
                n_open_at_end += int(np.sum(al & ~sell))
                for j in np.where(al & ~sell)[0]:
                    pos["exit_i"][j] = t
                    pos["val_final"][j] = float(pos["val"][j])   # 시가평가로 마감된 값
                pos["alive"] = al & sell            # 마지막 달: 시가평가로 마감(비용 미부과)
                al = pos["alive"]
            if bool((due & ~fin).any()):
                n_defer += int((due & ~fin).sum())
            if bool(sell.any()):
                sv = float(np.sum(pos["val"][sell]))
                sold_cost += sv * pos["x_cost"]
                cash += sv * (1.0 - pos["x_cost"])      # 매도대금에서 비용을 뺀 실수령액
                turnover[t] += sv / max(nav_open, 1e-12)
                for j in np.where(sell)[0]:
                    pos["exit_i"][j] = t
                    pos["val_final"][j] = float(pos["val"][j])   # 청산 시점 시가(비용 차감 전)
                pos["alive"] = pos["alive"] & ~sell
            pos["h"] += 1
        port_cost[t] += sold_cost

        # ── ④ NAV 재계산 (= 현금 + 포지션 시가) · 월 수익률 = ΔNAV / 월초 NAV ─────────────
        nav = cash + float(sum(float(np.sum(p["val"] * p["alive"])) for p in open_pos))
        port_cost[t] = port_cost[t] / max(nav_open, 1e-12)
        port_ret[t] = (nav - nav_open) / max(nav_open, 1e-12) + port_cost[t]
        invested[t] = invested[t] / max(nav_open, 1e-12)

        # 완전히 청산된 코호트는 원장에 확정하고 목록에서 제거
        still: List[dict] = []
        for pos in open_pos:
            pos["val"] = np.where(pos["alive"], pos["val"], 0.0)
            if bool(pos["alive"].any()) and t < n_m - 1:
                still.append(pos)
            else:
                for j, cd in enumerate(pos["names"]):
                    v0 = float(pos["v0"][j])
                    ei = pos["exit_i"][j]
                    # ★ 청산 시점의 시가로 계산한다. NAV 계산용으로 0 으로 만든 val 을 쓰면
                    #   전 종목의 ret_h 가 -100% 로 찍힌다(N12 가 잡아낸 실수).
                    vf = pos["val_final"][j]
                    vf = float(vf) if np.isfinite(vf) else float(pos["val"][j])
                    cohorts.append({
                        "cohort": pos["cohort"], "code": cd, "entry_month": pos["cohort"],
                        "exit_month": months[int(ei)] if np.isfinite(ei) else months[t],
                        "ret_h": float(vf / v0 - 1.0) if v0 > 0 else np.nan,
                        "n_months": int(pos["n_held"][j]), "weight": v0,
                        "z": float(pos["z"].get(cd, np.nan))})
        open_pos = still

    R = pd.DataFrame({"month": months, "ret_gross": port_ret, "cost": port_cost,
                      "n": n_names, "turnover": turnover,
                      "cash": np.clip(1.0 - invested, 0.0, 1.0)})
    R["ret"] = R["ret_gross"] - R["cost"]
    R["equity"] = (1.0 + R["ret"].fillna(0.0)).cumprod()
    H_df = pd.DataFrame(holdings) if holdings else pd.DataFrame(
        columns=["month", "code", "weight", "ret", "cohort", "z"])
    C_df = pd.DataFrame(cohorts) if cohorts else pd.DataFrame(
        columns=["cohort", "code", "entry_month", "exit_month", "ret_h", "n_months"])

    _bind = (adv_bind_n / adv_bind_d) if adv_bind_d else float("nan")
    manifest_put(f"adv_cap_binding_frac[{label}]",
                 None if not np.isfinite(_bind) else round(_bind, 4))
    if adv_cap and adv_bind_d and adv_bind_n == 0:
        LOG.warn(f"[{label}] ADV 참여율 상한이 **한 번도 발동하지 않았습니다** — 이 실행에는 "
                 f"용량 제약이 사실상 없습니다(가정 계좌 {NCQ_ACCOUNT_KRW/1e8:.0f}억이 "
                 f"ADV 하한 {NCQ_MIN_ADV/1e8:.1f}억 대비 작기 때문). §12 R4 를 실제로 검정하려면 "
                 f"NCQ_ACCOUNT_KRW 를 키우세요(예: 50억). 지금 상태의 'ADV 제약 적용본'과 "
                 f"'미적용본'은 동일한 결과입니다.")
    if n_defer:
        LOG.info(f"[{label}] 거래정지로 청산이 이연된 (종목×달) {n_defer:,}건 — "
                 f"정지된 주식은 팔 수 없으므로 첫 거래 가능 시점까지 보유가 연장됩니다.")
    if n_open_at_end:
        LOG.info(f"[{label}] 패널 종료 시점에 {n_open_at_end:,}개 포지션이 열려 있어 "
                 f"청산비용 없이 시가평가로 마감했습니다(마지막 달 가짜 손실 방지).")
    ramp = int((R["cash"] > 0.5).head(max(H - 1, 0)).sum()) if len(R) else 0
    LOG.info(f"[{label}] 백테스트 완료 — 코호트 {n_cohort}개 · "
             f"연인원 {len(H_df):,} · 평균 현금비중 {100*R['cash'].mean():.0f}% · "
             f"누적 {100*(R['equity'].iloc[-1]-1):+.1f}%"
             + (f" · 램프업 {ramp}개월(코호트 미충전 — 현금비중 50%↑)" if ramp else ""))
    return {"returns": R, "holdings": H_df, "cohorts": C_df, "label": label}


# ── 벤치마크 ────────────────────────────────────────────────────────────────────────────────
def bench_universe_ew(UNI: pd.DataFrame, pxm: pd.DataFrame, months: pd.DatetimeIndex,
                      uni_obj: Optional["Universe"] = None,
                      gate: str = "liq_pass", name: str = "Bottom-N EW") -> pd.Series:
    """주 벤치마크 — 동일 유니버스 동일가중(Bottom-N EW).

    ★ 이것이 진짜 비교 대상이다. KOSDAQ 지수와 비교하면 '소형주 프리미엄'을 알파로 착각한다.
      같은 유니버스, 같은 유동성 필터, **같은 실효 수익률 행렬**로 담았을 때와 비교해야
      신호의 순수 기여가 드러난다.

    ★★ 과거 버그: `mean(skipna=True)` 로 결측을 평균에서 빼면, 상장폐지·거래정지 종목이
       벤치마크에서만 조용히 사라져 벤치마크에 생존자편향이 생긴다(전략은 -50%/0% 를 짊어짐).
       그 비대칭은 그대로 가짜 알파(또는 가짜 부진)가 된다. 이제 전략과 **같은 행렬**을 쓰고
       결측은 양쪽 모두 0(정지 마킹)으로 채운다.
    """
    if UNI is None or UNI.empty or pxm is None or pxm.empty:
        return pd.Series(np.nan, index=months, name=name)
    gate = gate if gate in UNI.columns else "liq_pass"
    delist = {}
    if uni_obj is not None:
        try:
            delist = uni_obj.delisting_map()
        except Exception:
            delist = {}
    E, _ = ncq_effective_return_matrix(pxm, months, delist)
    if E.empty:
        return pd.Series(np.nan, index=months, name=name)
    u = UNI[UNI[gate].fillna(False).astype(bool)][["month", "code"]].copy()
    u["code"] = u["code"].astype(str)
    vals, cnts = [], []
    cols = set(map(str, E.columns))
    for m in months:
        names = [c for c in u.loc[u["month"] == m, "code"].tolist() if c in cols]
        if not names:
            vals.append(np.nan); cnts.append(0); continue
        r = pd.to_numeric(E.loc[m].reindex(names), errors="coerce").to_numpy(dtype=float)
        r = np.where(np.isfinite(r), r, 0.0)      # 전략과 동일한 '정지 마킹' 규약
        vals.append(float(r.mean())); cnts.append(len(names))
    s = pd.Series(vals, index=months, name=name)
    LOG.info(f"벤치마크({name}) 구성 — 월평균 {np.mean(cnts):,.0f}종목 동일가중 · "
             f"전략과 동일한 실효 수익률 행렬 사용(폐지 -50%·정지 0% 동일 적용)")
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
        # ★★ 인덱싱 규약을 전략과 맞춘다. 전략·주벤치의 fwd_ret(m) 은 exec_px(m)→exec_px(m+1),
        #    즉 '월 m 라벨 = 달력 m+1 수익'이다. 반면 pct_change() 는 close(m-1)→close(m),
        #    즉 '월 m 라벨 = 달력 m 수익'이라 **한 달 어긋난다.** shift(-1) 로 맞추지 않으면
        #    2020-02 라벨에서 전략의 3월(코로나 폭락)과 지수의 2월을 빼는 일이 벌어지고,
        #    지수 대비 초과·HAC t 가 통째로 다른 달끼리 뺀 값이 된다.
        s = d.groupby("month")["close"].last().pct_change().shift(-1).reindex(months)
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
