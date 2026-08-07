

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델                                                             ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 '다음 거래일 시가'. 당일 종가 체결 금지(미래누수).   ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(누락 = 생존자편향).         ║
# ║  · 롱온리 (공매도 불가) — 음의 신호는 청산 게이트로만 쓴다.                                 ║
# ║  · 청산 규칙이 진입 논리와 같은 언어를 쓴다: Δlog M 이 Δlog E 수준까지 확장 완료 시 청산.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5          # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10             # 제곱근 충격 계수


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격. 참여율이 높을수록 급격히 비싸진다 — 소형주 가중이 여기서 나온다."""
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(SLIPPAGE_K * math.sqrt(part))


def exit_gate(dm, de) -> bool:
    """청산 판단: '진입 시의 목표상태'를 벗어났는가.

    진입 조건(axis_D)은 ΔlogE > 0 AND 시장이 아직 자본화를 안 함(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다. 알파 소진(원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다. 논거 무효

    ★ 예전엔 `dm >= de and de > 0` 이었다. 앞 조건이 참이면 뒤 조건도 거의 항상 참이라
      보이지만, 실제로 걸러지는 건 'de <= 0' 인 전 구간 — 즉 논거가 깨진 종목을 청산하는
      경로가 통째로 닫혀 있었다. 그 종목들은 보유상한(24개월)까지 자리를 차지했다.
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 종목 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '데이터프레임에 먼저 나온 행'을 고른다. 패널은
      ["code","month"] 로 정렬되어 있으므로 그건 곧 '종목코드가 작은 순'이다. 동점이 드물면
      무해하지만, 실측상 월 보유종목의 상당수가 동점 구간에서 결정됐고 행 순서를 섞으면
      포트폴리오가 통째로 바뀌었다 — 즉 보유종목이 데이터가 아니라 정렬의 함수였다.
      그래서 ① 1차 키는 signal_col, ② 2차 키는 랭크 이전의 원 Signal(정보량이 더 많다),
      ③ 최후에만 code 로 깬다. 이러면 동점 처리가 결정적이면서 '왜 그 종목인가'가 설명된다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "code") if c in df.columns and c != signal_col]
    asc = [False] + [False if c == "Signal" else True for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중(§8.5).
    비중 상한은 코드 상수로 이미 못박혀 있다 — 드로다운 한가운데서 정하지 않는다."""
    s = sub["Signal_rank"].fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    if spread < 1e-6:
        w = np.full(len(s), 1.0 / len(s))
    else:
        raw = np.clip(s - med, 0, None) + 1e-9
        conc = min(2.0, 0.5 + spread * 8.0)          # 격차 클수록 집중
        w = raw ** conc
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    # 종목별 상한 = min(정책 상한, 유동성 상한). 유동성 상한은 20일 평균거래대금의 X%.
    adv = sub["adv20"].fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                       POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))

    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다(합이 1보다 작아지면 전부 커진다).
    #   상한에 걸린 종목은 고정하고 나머지에만 잔여 비중을 재배분하는 water-filling 으로 강제한다.
    w = np.clip(w, 0.0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    free = np.ones(len(w), dtype=bool)
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
    if w.sum() > 1.0 + 1e-9:                 # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    return sub.assign(weight=w)


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                 sec: pd.DataFrame, signal_col: str = "Signal_rank",
                 top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                 label: str = "TCD") -> dict:
    mkt = sec.set_index("code")["market"].astype(str).to_dict()
    delist = uni.delisting_map()
    hold: Dict[str, dict] = {}
    rows, trades, holdings_log = [], [], []
    prev_w: Dict[str, float] = {}

    for i, m in enumerate(months):
        sub = P[(P["month"] == m)].copy()
        if sub.empty:
            rows.append({"month": m, "ret": 0.0, "n": 0, "turnover": 0.0, "cost": 0.0})
            continue
        elig = sub[(sub["VETO"] == 1) & (sub["FLOOR"] == 1) & sub[signal_col].notna() &
                   sub["exec_px"].notna()]
        # ★ 감쇠 감사는 '누적 교집합'으로 기록한다. 게이트별 독립 집계를 깔때기처럼 보여주면
        #   잔존율이 100%를 넘는 무의미한 숫자가 나온다(게이트가 서로 포함관계가 아니므로).
        g_liq = sub[sub["V6"] == 1]
        g_veto = g_liq[g_liq["VETO"] == 1]
        g_floor = g_veto[g_veto["FLOOR"] == 1]
        uni.audit_row("유동성필터", m, g_liq["code"].tolist())
        uni.audit_row("거부권통과", m, g_veto["code"].tolist())
        uni.audit_row("하한선통과", m, g_floor["code"].tolist())

        # 종목별 조회를 dict 로 미리 만든다. sub[sub.code==c] 를 종목마다 돌리면
        # 백테스트가 강건성 스위트에서 10여 회 재실행될 때 그 비용이 그대로 곱해진다.
        need_cols = [c for c in ("adv20", "fwd_ret", "VETO", "dlog_M", "dlog_E", signal_col)
                     if c in sub.columns]
        rec: Dict[str, dict] = {}
        for _c, *_v in sub[["code"] + need_cols].itertuples(index=False, name=None):
            rec[_c] = dict(zip(need_cols, _v))

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, k, signal_col)
        uni.audit_row("최종선정", m, pick["code"].tolist())

        # 청산 게이트: Δlog M 이 Δlog E 수준까지 확장 완료 / 보유상한 / 거부권
        keep = []
        for c, h in list(hold.items()):
            r0 = rec.get(c)
            if r0 is None:
                continue
            dm, de = r0.get("dlog_M"), r0.get("dlog_E")
            exited = False
            if r0.get("VETO", 1) == 0:
                exited = True                                    # 거부권 발동 시 즉시 강제청산
            elif h["months"] >= HOLD_MAX_MONTHS:
                exited = True
            elif exit_gate(dm, de):
                exited = True                        # 목표상태 이탈 (재분류 완료 또는 논거 무효)
            if not exited:
                keep.append(c)
        target = pd.concat([pick, sub[sub["code"].isin(keep) & ~sub["code"].isin(pick["code"])]],
                           ignore_index=True) if len(keep) else pick
        if len(target) > PORTFOLIO_MAX_NAMES:
            target = _top_n(target, PORTFOLIO_MAX_NAMES, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}
        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in set(w_new) | set(prev_w))

        cost = 0.0
        if apply_costs:
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                c_bps = COMMISSION_BPS / 1e4
                sl = slippage(notional, adv)
                tx = sell_tax(m, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (c_bps + sl + tx)

        # 다음 달 수익
        ret = 0.0
        for c, w in w_new.items():
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                # ★ 상장폐지: 정리매매 최종가가 없으면 -100%. 누락 처리 금지(C2).
                fr = -1.0 if not np.isfinite(fr) else fr
            if not np.isfinite(fr):
                fr = 0.0
            ret += w * fr
            _s = _r.get(signal_col)
            holdings_log.append({"month": m, "code": c, "weight": w, "ret": fr,
                                 "signal": float(_s) if _s is not None and pd.notna(_s) else np.nan})
        ret_net = ret - cost
        rows.append({"month": m, "ret": ret_net, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost})
        for c in list(hold):
            if c in w_new:
                hold[c]["months"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"months": 0})
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    H = pd.DataFrame(holdings_log)
    return {"returns": R, "holdings": H, "label": label}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
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
    uw, mx, cur = 0, 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1), "평균종목수": float(R["n"].mean()),
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """★ 이 전략은 IR 이 아니라 우측 꼬리에 의존한다. 상위 종목 제외 시 성과가 사라지는지
    반드시 측정하고 리포트에 명시한다(§10.2)."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {}
    base = float(contrib.sum())
    for q, lab in ((0.05, "상위5%"), (0.10, "상위10%"), (0.01, "상위1%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후 총기여"] = base - float(contrib.iloc[:k].sum())
    out["총기여"] = base
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, months[0] - pd.offsets.MonthEnd(2), months[-1])
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        s = d.groupby("month")["close"].last().pct_change()
        out[name] = s.reindex(months)
    return out
