

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델 (§7, §8)                                                    ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 **익영업일 종가** (당일 종가 체결은 미래누수)        ║
# ║  · Q5 롱온리 **동일가중**, 종목당 상한 5%, 보유 하한 20종목(미달 시 현금 + 로그)           ║
# ║  · 보유기간 3개월은 **중첩 트랜치**로 구현한다: 매월 자본의 1/3 을 새로 넣고 3개월 보유.    ║
# ║    (특정 리밸런싱 월을 고르면 그 선택 자체가 자유 파라미터가 되어 사전등록을 위반한다)      ║
# ║  · 상장폐지: 승계면 사건 제외, 전손이면 -100%. 누락 처리 금지(누락 = 생존자편향).           ║
# ║  · 비용: 수수료 + 규모별 슬리피지 + **연도별 증권거래세 테이블**. 0/기본/2배 3종 보고.      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def sell_tax(dt, market: str) -> float:
    """매도 시 증권거래세. **단일 세율 금지** — 2016~2026 사이에 0.30%→0.15% 로 5번 바뀐다."""
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def size_bucket_of(marcap: float) -> str:
    """슬리피지 규모 구간. 시총 기준(조원): 대형 ≥1조 / 중형 ≥2천억 / 소형 그 외."""
    if marcap is None or not np.isfinite(marcap) or marcap <= 0:
        return "small"
    if marcap >= 1e12:
        return "large"
    if marcap >= 2e11:
        return "mid"
    return "small"


def trade_cost(side: str, month, market: str, marcap: float, mult: float = 1.0) -> float:
    """편도 거래비용(비율). side='buy'|'sell'."""
    c = COMMISSION_BPS / 1e4
    s = SLIPPAGE_BPS.get(size_bucket_of(marcap), SLIPPAGE_BPS["small"]) / 1e4
    tx = sell_tax(month, market) if side == "sell" else 0.0
    return (c + s + tx) * float(mult)


def run_backtest(S: "pd.DataFrame", panel: "pd.DataFrame", months: "pd.DatetimeIndex",
                 sec: "pd.DataFrame", hold: int = 1, cost_mult: float = 1.0,
                 label: str = "AAR", uni_obj: Optional["Universe"] = None,
                 min_adv: float = MIN_ADV_KRW) -> dict:
    """중첩 트랜치 백테스트. 반환 {returns, holdings, trades, label}."""
    px = panel[["code", "month", "fwd_ret1", "adv20", "marcap", "market", "exec_px"]].copy()
    px["code"] = as_str_series(px["code"])
    px["month"] = as_ts_series(px["month"])
    look = {(c, m): (r, a, mc, mk)
            for c, m, r, a, mc, mk in zip(px["code"], px["month"], px["fwd_ret1"],
                                          px["adv20"], px["marcap"], px["market"])}
    liq = {(c, m): a for c, m, a in zip(px["code"], px["month"], px["adv20"])}

    tranches: "OrderedDict[int, dict]" = OrderedDict()     # entry_month_idx → {codes, weights}
    rows, hold_log, trade_log = [], [], []
    prev_book: Dict[str, float] = {}

    for i, m in enumerate(months):
        # ── 신규 트랜치 선정 ───────────────────────────────────────────────────────────
        sub = S[S["month"] == m]
        if len(sub) and min_adv > 0:
            keep = [c for c in as_str_series(sub["code"])
                    if (liq.get((c, m)) is None or not np.isfinite(liq.get((c, m), np.nan))
                        or liq.get((c, m), 0) >= min_adv)]
            sub = sub[as_str_series(sub["code"]).isin(set(keep))]
        codes, info = select_portfolio(sub, m) if len(sub) else ([], {"cash": True})
        if uni_obj is not None:
            uni_obj.audit_row("신호보유(U)", m, sub["code"].tolist() if len(sub) else [])
            uni_obj.audit_row("Q5선정", m, [""] * int(info.get("n_q5", 0)))
            uni_obj.audit_row("배제후최종", m, codes)
        if codes:
            w = min(POS_MAX_WEIGHT, 1.0 / len(codes))       # 동일가중 + 종목당 상한
            tranches[i] = {"codes": codes, "w": w}
        else:
            tranches[i] = {"codes": [], "w": 0.0}
            if info.get("cash"):
                LOG.debug(f"{m:%Y-%m} 보유 하한({PORT_MIN_NAMES}) 미달 → 현금 "
                          f"(U={info.get('n_U',0)} Q5={info.get('n_q5',0)} "
                          f"배제={info.get('n_excl',0)})")
        for k in [k for k in tranches if k <= i - hold]:
            tranches.pop(k, None)

        # ── 현재 장부 (활성 트랜치 평균) ──────────────────────────────────────────────
        active = [t for k, t in tranches.items() if t["codes"]]
        book: Dict[str, float] = defaultdict(float)
        if active:
            share = 1.0 / hold                              # 트랜치당 자본 비중
            for t in tranches.values():
                if not t["codes"]:
                    continue
                for c in t["codes"]:
                    book[c] += t["w"] * share
        tot = sum(book.values())
        if tot > 1.0 + 1e-9:
            book = {c: v / tot for c, v in book.items()}

        # ── 비용 ──────────────────────────────────────────────────────────────────────
        cost = 0.0
        turn = 0.0
        for c in set(book) | set(prev_book):
            dw = book.get(c, 0.0) - prev_book.get(c, 0.0)
            if abs(dw) < 1e-9:
                continue
            turn += abs(dw)
            rec = look.get((c, m))
            mc = rec[2] if rec else np.nan
            mk = rec[3] if rec else "OTHER"
            cost += abs(dw) * trade_cost("buy" if dw > 0 else "sell", m, mk, mc, cost_mult)
            trade_log.append({"month": m, "code": c, "dw": dw,
                              "side": "buy" if dw > 0 else "sell"})

        # ── 다음 달 수익 ──────────────────────────────────────────────────────────────
        ret = 0.0
        for c, w in book.items():
            rec = look.get((c, m))
            fr = rec[0] if rec else np.nan
            fr = float(fr) if fr is not None and np.isfinite(fr) else 0.0
            ret += w * fr
            hold_log.append({"month": m, "code": c, "weight": w, "ret": fr})
        rows.append({"month": m, "ret": ret - cost, "ret_gross": ret, "n": len(book),
                     "turnover": turn, "cost": cost, "cash": 1.0 - sum(book.values())})
        prev_book = dict(book)

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    return {"returns": R, "holdings": pd.DataFrame(hold_log),
            "trades": pd.DataFrame(trade_log), "label": label}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: "pd.DataFrame", rf: float = 0.0) -> dict:
    r = R["ret"].fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1 + r)
    years = n / 12.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(12) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(12) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for xdd in dd:
        cur = cur + 1 if xdd < -1e-9 else 0
        mx = max(mx, cur)
    mu, t = hac_tstat(r)
    return {
        "월수": n, "누적수익": float(eq[-1] - 1), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(np.mean(r)),
        "t통계량(HAC)": t, "최장언더워터(월)": int(mx),
        "평균종목수": float(R["n"].mean()),
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
        "현금비중": float(R["cash"].mean()) if "cash" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """소수 종목 의존도. 상위 5% 를 빼면 성과가 사라지는지 반드시 측정해 보고한다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    base = float(contrib.sum())
    out = {"총기여": base}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후"] = base - float(contrib.iloc[:k].sum())
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


def bench_stats(R: "pd.DataFrame", bench: Dict[str, "pd.Series"]) -> List[list]:
    rows = []
    S = R.set_index("month")["ret"].fillna(0)
    for name, b in bench.items():
        if b is None or not len(b):
            continue
        bb = pd.Series(b).reindex(S.index).fillna(0)
        ex = S - bb
        _, t = hac_tstat(ex.to_numpy())
        cum_s = float((1 + S).prod() - 1)
        cum_b = float((1 + bb).prod() - 1)
        ann_ex = float((1 + ex.mean()) ** 12 - 1)
        rows.append([name, f"{cum_b*100:+.1f}%", f"{cum_s*100:+.1f}%",
                     f"{(cum_s-cum_b)*100:+.1f}%p", f"{ann_ex*100:+.2f}%p",
                     f"{t:.2f}" if np.isfinite(t) else "—"])
    return rows
