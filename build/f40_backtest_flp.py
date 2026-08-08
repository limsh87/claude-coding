# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  주간 백테스트 엔진 + 비용 모델 (§8)                                                   ║
# ║                                                                                          ║
# ║  · 주 1회 리밸런싱. 체결 = 신호 산출일의 '다음 거래일 시가'. 당일 종가 체결 금지.           ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(C2).                        ║
# ║    ★ 이 전략의 표적 집단이 곧 상폐 위험 집단이므로 여기가 성과의 진위를 가른다.             ║
# ║  · 청산: f_cr_pctl ≥ 0.5 회복(재취약) / 방화벽·거부권 위반 / 26주 상한.                     ║
# ║    보유 중 '유니버스 밴드 이탈'은 청산 사유가 아니다(C13).                                  ║
# ║  · 사이징 상수는 헤더에 못박혀 있고, R12 가 그 근거를 사후 검증한다(§12-2).                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5           # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10              # 제곱근 충격 계수 (소형주 가중이 여기서 나온다)
PERIODS_PER_YEAR = 52.0


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float, k: float = SLIPPAGE_K) -> float:
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(k * math.sqrt(part))


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """동일가중 → 종목당 상한 + ADV 참여율 상한 → 잔여를 자유 종목에 재배분.
    ★ 신호강도 비례 사이징을 쓰지 않는다. 이 전략의 신호는 순위정보이지 기대수익 크기가 아니다."""
    n = len(sub)
    if n == 0:
        return sub.assign(weight=[])
    w = np.full(n, 1.0 / n)
    adv = pd.to_numeric(sub.get("adv20"), errors="coerce").to_numpy(dtype=float)
    cap_adv = np.where(np.isfinite(adv) & (adv > 0),
                       POS_ADV_PARTICIPATION * adv / max(ACCOUNT_KRW, 1.0), POS_MAX_WEIGHT)
    cap = np.minimum(np.full(n, POS_MAX_WEIGHT), np.maximum(cap_adv, POS_MIN_WEIGHT))
    for _ in range(6):
        over = w > cap
        if not over.any():
            break
        rem = float(np.sum(w[over] - cap[over]))
        w[over] = cap[over]
        free = ~over & (w < cap)
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem + w[free]) if pool > 1e-12 else (rem / free.sum())
        w = np.minimum(w, cap)
    s = w.sum()
    if s > 1.0 + 1e-9:
        w = w / s
    return sub.assign(weight=w)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.head(0)
    # 동점 처리: 신호 동률이면 유동성이 큰 쪽 → 그래도 같으면 종목코드 순.
    # ★ 과거 세션 교훈: 동점을 암묵적 행순서로 깨면 같은 입력이 다른 포트폴리오를 낳는다
    #   (C8 결정성 위반). 마지막 키까지 명시해 완전히 결정적으로 만든다.
    keys, asc = [signal_col, "adv20", "code"], [False, False, True]
    keys = [k for k in keys if k in df.columns]
    asc = asc[:len(keys)]
    d = df.sort_values(keys, ascending=asc, kind="mergesort")
    return d.head(n)


def run_backtest_w(P: pd.DataFrame, weeks: pd.DatetimeIndex, uni: "Universe",
                   sec: pd.DataFrame, signal_col: str = "Signal_rank",
                   top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                   slip_k: float = SLIPPAGE_K, label: str = "FLP",
                   exit_cr: float = EXIT_CR_PCTL,
                   hold_max: int = HOLD_MAX_WEEKS, audit: bool = False) -> dict:
    """audit=True 는 '대표 실행' 하나에만 준다.

    ★ 감쇠 원장(uni.attrition)은 append-only 라, 강건성 arm 20여 회와 스몰캡 비교까지
      전부 기록하면 §10.4 감쇠표가 '여러 전략의 평균'이 되어 아무 것도 뜻하지 않게 된다.
    """
    mkt = (sec.set_index("code")["market"].astype(str).to_dict()
           if sec is not None and len(sec) and "market" in sec.columns else {})
    delist = uni.delisting_map() if uni is not None else {}
    hold: Dict[str, dict] = {}
    prev_w: Dict[str, float] = {}
    rows, holdings_log = [], []
    n_frozen_events = n_forced_delist = n_stale_writeoff = 0

    need = [c for c in ("adv20", "fwd_ret", "FIREWALL", "FIREWALL_HARD", "VETO", "f_cr_pctl",
                        "PHASE_C", "exec_px", signal_col) if c in P.columns]
    Pw = {w: g for w, g in P.groupby("wk", observed=True)} if len(P) else {}

    for i, w in enumerate(weeks):
        # 다음 리밸런스 시점 — 상장폐지 귀속 창을 '고정 7일'이 아니라 실제 보유구간으로 잡는다
        w_next = weeks[i + 1] if i + 1 < len(weeks) else w + pd.Timedelta(days=7)
        sub = Pw.get(w)
        rec: Dict[str, dict] = {}
        if sub is not None and len(sub):
            for _c, *_v in sub[["code"] + need].itertuples(index=False, name=None):
                rec[_c] = dict(zip(need, _v))

        # ── ① 패널에서 사라진 보유분 = 거래정지/폐지. 조용히 0% 로 털어내지 않는다. ──────
        #   한국의 전형 경로는 거래정지 → 정리매매 → 상장폐지다. 그 사이 종목은 패널에서
        #   사라지므로, 예전 구현처럼 '보유 목록에서 pop' 하면 총손실이 무손실로 둔갑한다.
        #   → 팔 수 없는 동안은 비중을 그대로 들고 있고(수익 0), 폐지가 확정되면 -100%.
        frozen: Dict[str, float] = {}
        forced: List[Tuple[str, float, float]] = []
        gap_ret: Dict[str, float] = {}
        for c, wt in list(prev_w.items()):
            if c in rec:
                # ★ 거래재개: 정지 구간의 가격 변화를 이번 주에 실현한다.
                #   정지 중 0% 로 두고 재개 후 새 가격에서 다시 시작하면, 정지 기간에
                #   무너진 가격이 어디에도 계상되지 않는다(이 전략에서 가장 흔한 손실 경로다).
                h0 = hold.get(c)
                if h0 and h0.get("frozen", 0) > 0:
                    last_px = h0.get("last_exec")
                    now_px = (rec[c] or {}).get("exec_px")
                    if (last_px and now_px and np.isfinite(float(last_px))
                            and np.isfinite(float(now_px)) and float(last_px) > 0):
                        gap_ret[c] = float(now_px) / float(last_px) - 1.0
                    h0["frozen"] = 0                 # 재개했으므로 동결 카운터 리셋
                if h0 is not None:
                    _px = (rec[c] or {}).get("exec_px")
                    if _px is not None and pd.notna(_px):
                        h0["last_exec"] = float(_px)
                continue
            dl = delist.get(c)
            h = hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
            if dl is not None and pd.notna(dl) and dl <= w_next:
                forced.append((c, wt, -1.0))          # 정리매매가 없으면 -100% (C2)
                hold.pop(c, None)
                n_forced_delist += 1
            elif h["frozen"] >= hold_max:
                # 26주 넘게 시세가 없고 폐지일도 확인되지 않는다 → 보수적으로 총손실 처리.
                # (낙관적으로 0% 처리하면 이 전략의 성과가 구조적으로 부풀려진다)
                forced.append((c, wt, -1.0))
                hold.pop(c, None)
                n_stale_writeoff += 1
            else:
                h["frozen"] += 1
                frozen[c] = wt
                n_frozen_events += 1

        if sub is None or sub.empty:
            ret_forced = sum(wt * r for _c, wt, r in forced)
            for c, wt, r in forced:
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": r,
                                     "signal": np.nan, "state": "delisted"})
            for c, wt in frozen.items():
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": 0.0,
                                     "signal": np.nan, "state": "halted"})
            rows.append({"wk": w, "ret": ret_forced, "ret_gross": ret_forced,
                         "n": len(frozen), "turnover": 0.0, "cost": 0.0,
                         "invested": float(sum(frozen.values()))})
            prev_w = dict(frozen)
            continue

        # ★ 진입 자격은 '신호' 하나로만 판단한다.
        #   assemble_score 가 이미 방화벽·거부권·밴드를 Signal 에 곱해 넣었으므로
        #   (게이트에 걸리면 Signal 이 정확히 0), 엔진이 같은 게이트를 다시 적용하면
        #   R5 절제의 "방화벽 off"·"거부권 off" arm 이 수학적으로 무의미해진다
        #   (게이트를 빼고 채점해도 엔진이 도로 걸러내므로 ΔCAGR 이 항상 0 → 절제표가
        #    "방화벽은 기여가 없다"고 거짓 보고한다). 청산 쪽 FIREWALL_HARD 는 그대로다.
        fresh_px = (sub["stale_days"] <= 3) if "stale_days" in sub.columns else True
        elig = sub[sub[signal_col].notna() & (sub[signal_col] > 0) &
                   sub["exec_px"].notna() & fresh_px]
        if uni is not None and audit:
            uni.audit_row("유동성필터", w, sub[sub["V6"] == 1]["code"].tolist())
            uni.audit_row("낙폭조건", w, sub[(sub["V6"] == 1) &
                                             (sub["f_dd"] < PH_DD_ENTER)]["code"].tolist())
            uni.audit_row("국면C", w, sub[(sub["V6"] == 1) & (sub["PHASE_C"] == 1)]["code"].tolist())
            uni.audit_row("방화벽통과", w, sub[(sub["V6"] == 1) & (sub["PHASE_C"] == 1) &
                                               (sub["FIREWALL"] == 1)]["code"].tolist())
            uni.audit_row("거부권통과", w, elig["code"].tolist())

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, min(k, len(elig)), signal_col)
        if uni is not None and audit:
            uni.audit_row("최종선정", w, pick["code"].tolist())

        # ── ② 청산 판정 (진입 논리와 같은 언어로) ──────────────────────────────────────
        keep = []
        for c, h in list(hold.items()):
            if c in frozen:
                continue                       # 팔 수 없는 종목은 청산 판단 대상이 아니다
            r0 = rec.get(c)
            if r0 is None:
                continue
            exited = False
            fw_hard = r0.get("FIREWALL_HARD", r0.get("FIREWALL", 1))
            if fw_hard == 0 or r0.get("VETO", 1) == 0:
                exited = True                  # 기업 소멸 방어·거부권은 즉시 강제청산
            elif h["weeks"] >= hold_max:
                exited = True                  # 6개월 상한
            else:
                crp = r0.get("f_cr_pctl")
                if crp is not None and pd.notna(crp) and float(crp) >= exit_cr:
                    exited = True              # 신규 신용 유입 = 다시 취약해짐
            if not exited:
                keep.append(c)

        exited = {c for c in hold if c not in keep and c not in frozen}
        if exited:
            # 청산 사유가 발생한 종목을 같은 주에 다시 사면 보유상한·청산규칙이 무의미해진다
            pick = pick[~pick["code"].isin(exited)]
        extra = sub[sub["code"].isin(keep) & ~sub["code"].isin(set(pick["code"]))]
        target = pd.concat([pick, extra], ignore_index=True) if len(extra) else pick
        room = max(0, PORTFOLIO_MAX_NAMES - len(frozen))
        if len(target) > room:
            held = target[target["code"].isin(keep)].head(room)
            fresh = _top_n(target[~target["code"].isin(keep)],
                           max(0, room - len(held)), signal_col)
            target = pd.concat([held, fresh], ignore_index=True)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        # 정지 종목이 물고 있는 비중만큼 신규 가용 자본이 줄어든다 (팔 수 없으므로)
        w_frozen = float(sum(frozen.values()))
        avail = max(0.0, 1.0 - w_frozen)
        w_new = dict(frozen)
        if len(target):
            for c, wt in zip(target["code"], target["weight"]):
                w_new[c] = float(wt) * avail

        traded = (set(w_new) | set(prev_w)) - {c for c, _wt, _r in forced}
        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0)) for c in traded)

        cost = 0.0
        if apply_costs:
            for c in traded:
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                tx = sell_tax(w, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (COMMISSION_BPS / 1e4 + slippage(notional, adv, slip_k) + tx)

        ret = sum(wt * r for _c, wt, r in forced)
        for c, wt, r in forced:
            holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": r,
                                 "signal": np.nan, "state": "delisted"})
        dead_now: List[str] = []
        for c, wt in w_new.items():
            if c in frozen:
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": 0.0,
                                     "signal": np.nan, "state": "halted"})
                continue
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            state = "held"
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and w < dl <= w_next:
                # ★ 상장폐지 주간: 정리매매 최종가가 없으면 -100%. 누락 처리 금지(C2).
                fr = -1.0 if not np.isfinite(fr) else fr
                state = "delisted"
                dead_now.append(c)             # 여기서 손실을 확정했으므로 다음 주에 또 세지 않는다
            if not np.isfinite(fr):
                fr = 0.0
            g = gap_ret.pop(c, 0.0)            # 거래정지 구간의 가격 변화(재개 주에 실현)
            if g:
                state = "resumed"
            ret += wt * (fr + g)
            holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": fr + g,
                                 "signal": _r.get(signal_col), "state": state})
            h = hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
            _px = _r.get("exec_px")
            if _px is not None and pd.notna(_px):
                h["last_exec"] = float(_px)
        rows.append({"wk": w, "ret": ret - cost, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost,
                     "invested": float(sum(w_new.values()))})

        for c in dead_now:                     # 폐지 확정분은 포지션을 여기서 종료한다
            w_new.pop(c, None)
            hold.pop(c, None)
            n_forced_delist += 1
        for c in list(hold):
            if c in w_new:
                hold[c]["weeks"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
        prev_w = w_new

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    if n_forced_delist or n_stale_writeoff or n_frozen_events:
        LOG.info(f"[{label}] 보유 중 사고 처리 — 거래정지 보유주 {n_frozen_events:,}건 · "
                 f"폐지확정 -100% {n_forced_delist:,}건 · "
                 f"장기 시세부재 보수적 상각 {n_stale_writeoff:,}건 "
                 f"(0% 로 조용히 털지 않습니다 — C2)")
    return {"returns": R, "holdings": pd.DataFrame(holdings_log), "label": label,
            "incidents": {"frozen": n_frozen_events, "delisted": n_forced_delist,
                          "stale_writeoff": n_stale_writeoff}}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats_w(R: pd.DataFrame, rf: float = 0.0) -> dict:
    if R is None or not len(R):
        return {}
    r = R["ret"].fillna(0).to_numpy(dtype=float)
    n = len(r)
    eq = np.cumprod(1 + r)
    years = n / PERIODS_PER_YEAR
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if len(dn) > 1 else np.nan
    # ★ 최고점 후보에 초기자본 1.0 을 포함한다. 빼면 시작부터 내리 하락한 구간의
    #   낙폭이 '1주차 종가 대비'로 측정되어 MDD 가 과소평가된다.
    eq_full = np.concatenate([[1.0], eq])
    peak = np.maximum.accumulate(eq_full)
    dd = (eq_full / peak - 1)[1:]
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    _mu, tstat = hac_tstat(r)
    return {
        "주수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "주평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(주)": int(mx),
        "누적수익": float(eq[-1] - 1),
        "평균종목수": float(R["n"].mean()) if "n" in R else np.nan,
        "평균투자비중": float(R["invested"].mean()) if "invested" in R else np.nan,
        "주평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "주평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """이 전략은 우측 꼬리 의존적이다. 상위 종목 제외 시 성과가 사라지는지 매번 측정한다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {"총기여": float(contrib.sum())}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후"] = float(contrib.sum() - contrib.iloc[:k].sum())
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.3f})" for c, v in contrib.head(5).items())
    return out


def benchmark_returns_w(weeks: pd.DatetimeIndex, P: Optional[pd.DataFrame] = None
                        ) -> Dict[str, pd.Series]:
    """★ 벤치마크 수치를 하드코딩하지 않는다(§1-5). 여기서 직접 재측정한다.
    KOSPI·KOSDAQ 지수 + '유니버스 동일가중'(이 전략의 진짜 대조군)."""
    out: Dict[str, pd.Series] = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None and len(weeks):
            try:
                limiter("krx").wait()
                d = fdr.DataReader(sym, (weeks[0] - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
                                   weeks[-1].strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        s = d.set_index("date")["close"].sort_index()
        s = s.reindex(s.index.union(weeks)).ffill().reindex(weeks)
        # ★ 전략 수익률은 [w, w+1] 구간의 '선행' 수익률이다. 지수를 후행 pct_change 로 두면
        #   한 주가 어긋나 R12(꼬리 동시손실)가 '지난주 급락'으로 위기주를 고르게 된다.
        out[name] = s.pct_change().shift(-1)
    if P is not None and len(P) and "fwd_ret" in P.columns:
        eqw = (P[P["in_band"] == 1].groupby("wk", observed=True)["fwd_ret"].mean()
               if "in_band" in P.columns else P.groupby("wk", observed=True)["fwd_ret"].mean())
        out["유니버스 동일가중"] = eqw.reindex(weeks)
    idx_missing = [n for n in ("KOSPI", "KOSDAQ") if n not in out]
    if idx_missing:
        # ★ '유니버스 동일가중'이 항상 채워지므로 out 이 비는 일은 없다 → 지수 결측을
        #   따로 경고하지 않으면 R0·R7·R12 가 조용히 '자기 유니버스와만' 비교하게 된다.
        LOG.warn(f"지수 벤치마크 {idx_missing} 를 받지 못했습니다 — R0/R7/R12 는 "
                 f"'유니버스 동일가중'만으로 판정합니다. 전략을 자기 유니버스와 비교하는 것은 "
                 f"시장 대비 성과가 아니므로 해석에 반드시 반영하세요(수치를 임의로 채우지 않습니다).")
    return out
