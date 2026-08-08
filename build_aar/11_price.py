

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 패널 — 월말 스냅샷 · 익영업일 체결 · 보유기간별 forward return · 폐지 처리     ║
# ║                                                                                          ║
# ║  가격 원천은 10_universe 의 marcap 로더가 이미 만들어 두었다(연도 parquet 11개).           ║
# ║  이 모듈은 그것을 백테스트가 먹을 수 있는 형태로 바꾸기만 한다 — 네트워크 접근 없음.       ║
# ║                                                                                          ║
# ║  · 체결가  = 신호 산출일의 **익영업일 종가** (§1-1 익영업일 앵커). 당일 종가는 미래누수.   ║
# ║  · 수익률  = 수정종가 비율. **Marcap 비율 금지**(주식수 변동이 섞여 상방 편의, §7-F1).     ║
# ║  · 폐지    = 승계(합병 등)면 결측, 전손이면 -100%. 일괄 처리는 양방향 모두 편향이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_price_panel(monthly: "pd.DataFrame", months: "pd.DatetimeIndex",
                      max_hold: int = 3) -> "pd.DataFrame":
    """월말 패널 + 1~max_hold 개월 forward return.

    ★ forward return 은 '정확히 k개월 뒤'와만 짝지어야 한다. 거래가 끊겨 중간 달이
      패널에서 빠지면 shift(-k) 가 몇 달 뒤 가격을 끌어와 k개월 수익으로 둔갑시킨다
      (수익 과대계상). 인접성 검사로 봉인한다."""
    m = monthly[monthly["month"].isin(months)].copy()
    m = m.sort_values(["code", "month"], kind="stable").reset_index(drop=True)

    # 체결가 = 익영업일 종가. 다음 거래일이 너무 멀면(거래정지·상폐 직전) 그 가격으로
    # 체결했다고 가정할 수 없으므로 당월 말 수정종가로 폴백한다.
    gap = (m["next_date"] - m["signal_date"]).dt.days
    m["exec_px"] = m["next_close"].where(gap.notna() & (gap <= 10))
    m["exec_px"] = m["exec_px"].fillna(m["adj_close"])

    g = m.groupby("code", observed=True)
    mnum = m["month"].dt.year * 12 + m["month"].dt.month
    for k in range(1, max_hold + 1):
        nxt_px = g["exec_px"].shift(-k)
        nxt_mn = g["month"].shift(-k)
        adjacent = ((nxt_mn.dt.year * 12 + nxt_mn.dt.month) - mnum) == k
        m[f"fwd_ret{k}"] = (nxt_px / m["exec_px"].where(m["exec_px"] > 0) - 1.0).where(adjacent)
    m["fwd_ret"] = m["fwd_ret1"]

    n_gap = int((g["month"].shift(-1).notna() & m["fwd_ret1"].isna()).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 아래 apply_delisting_returns 가 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", m)
    return downcast(m)


def apply_delisting_returns(panel: "pd.DataFrame", sec: "pd.DataFrame",
                            max_hold: int = 3) -> "pd.DataFrame":
    """상장폐지 월의 forward return 을 '승계 vs 전손'으로 갈라 채운다 (§2.5).

    ★ 무조건 결측 → 손실 누락(상방 편향).  무조건 -100% → 피흡수합병 주주까지 전손
      (하방 편향).  둘 다 틀리므로 폐지 사유로 분기한다.
        · SUCCEED (합병·주식교환·지주회사 전환) : 주주는 대가를 받았다 → 결측(사건 제외)
        · WIPEOUT (상장폐지기준 해당 등)        : -100%
    """
    if panel is None or panel.empty or sec is None or sec.empty:
        return panel
    kind = classify_delisting(
        sec.rename(columns={"delist_reason": "reason", "delist_to": "to_symbol"})
           [["code", "delisting_date", "reason", "to_symbol"]].dropna(subset=["delisting_date"]))
    dl = dict(zip(as_str_series(sec["code"]), as_ts_series(sec["delisting_date"])))
    p = panel.copy()
    codes = as_str_series(p["code"])
    dser = codes.map(dl)
    kser = codes.map(kind)
    n_wipe = n_succ = 0
    for k in range(1, max_hold + 1):
        col = f"fwd_ret{k}"
        if col not in p.columns:
            continue
        horizon_end = p["month"] + pd.offsets.MonthEnd(k)
        within = dser.notna() & (dser > p["month"]) & (dser <= horizon_end)
        wipe = within & (kser == "WIPEOUT") & p[col].isna()
        succ = within & (kser != "WIPEOUT")
        p.loc[wipe, col] = -1.0
        p.loc[succ & p[col].isna(), col] = np.nan       # 승계는 사건 제외(결측 유지)
        if k == 1:
            n_wipe, n_succ = int(wipe.sum()), int(succ.sum())
    p["fwd_ret"] = p["fwd_ret1"]
    LOG.info(f"상장폐지 수익률 처리 — 전손(-100%) {n_wipe:,}건 · "
             f"승계(합병 등, 사건 제외) {n_succ:,}건. "
             f"일괄 처리하지 않는 이유: 전자만 하면 상방 편향, 후자만 하면 하방 편향입니다.")
    return p


def benchmark_series(months: "pd.DatetimeIndex", daily: "pd.DataFrame",
                     uni_month: "pd.DataFrame", panel: "pd.DataFrame"
                     ) -> Tuple[Dict[str, "pd.Series"], "pd.Series"]:
    """벤치마크 4종 + 일별 시장수익(이벤트 스터디의 시장조정용).

    §8: KOSPI, KOSDAQ, **동일가중 유니버스**, 그리고 **'단순 리포트 건수 증가' 나이브 신호**.
    마지막이 진짜 비교 대상이다 — §6.3 통제의 가치를 보여주는 유일한 벤치마크이기 때문이다.
    (나이브 신호는 32_signal 에서 만들어 백테스트로 돌리므로 여기서는 앞 3종만 만든다)

    ★ 지수 데이터를 못 받아도 동일가중 유니버스는 항상 있으므로 비교가 끊기지 않는다.
    """
    out: Dict[str, "pd.Series"] = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, (months[0] - pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d"),
                                   months[-1].strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        out[name] = d.groupby("month")["close"].last().pct_change().reindex(months)
    if not out:
        LOG.info("지수(KOSPI/KOSDAQ) 시계열을 받지 못했습니다 — 동일가중 유니버스 벤치마크로 "
                 "비교합니다(§8 의 핵심 벤치마크는 원래 동일가중 유니버스입니다).")

    # 동일가중 유니버스 — 이 전략의 1차 비교 대상 (§11 ACCEPT 조건이 이것 대비 +3%p)
    if panel is not None and len(panel):
        ew = (panel.dropna(subset=["fwd_ret"])
                   .groupby("month", observed=True)["fwd_ret"].mean().reindex(months))
        out["동일가중유니버스"] = ew

    daily_mkt = pd.Series(dtype="float64")
    if daily is not None and len(daily):
        dd = daily.dropna(subset=["ret"])
        daily_mkt = dd.groupby("date")["ret"].mean()
    return out, daily_mkt
