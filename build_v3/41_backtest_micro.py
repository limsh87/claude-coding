

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 (§10)                                                                  ║
# ║                                                                                          ║
# ║  체결   : 신호 산출일의 '다음 거래일 시가'. 당일 종가 체결은 미래누수다.                    ║
# ║  비용   : 왕복 수수료+세금+슬리피지(거래대금 참여율, 소형주 가중)                          ║
# ║  리밸런싱: 월 1회                                                                          ║
# ║  청산   : 거부권 발동 / 방화벽 이탈 / 보유 24개월 상한 / 신호 밴드 이탈                    ║
# ║  비중   : 20일 평균거래대금의 일정 비율로 상한 (소액계좌에서도 실행 가능한지 검증)          ║
# ║  상장폐지: 정리매매 최종가, 없으면 -100% (C2 — 누락 처리 금지)                              ║
# ║                                                                                          ║
# ║  ★ 월 루프(120회)는 돌지만 종목 루프는 돌지 않는다. 월 내부는 전부 벡터 연산이다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def sell_tax_rate(dt) -> float:
    """증권거래세(코스닥/코스피 장내 매도). 구간별 인하를 반영한다.
    하드코딩된 '기억'이 아니라 시행일 기준 표이며, 틀리면 R9 비용 시나리오가 흡수한다."""
    d = as_ts(dt)
    if d is None:
        return 0.0023
    y = (d.year, d.month)
    if y < (2019, 6):
        return 0.0030
    if y < (2021, 1):
        return 0.0025
    if y < (2023, 1):
        return 0.0023
    if y < (2024, 1):
        return 0.0020
    if y < (2025, 1):
        return 0.0018
    return 0.0015


SLIPPAGE_K = 0.05          # 제곱근 충격계수
SLIPPAGE_BASE = 0.0015     # 호가 스프레드 절반 (소형주 기준)


def slippage_bps(trade_krw: float, adv_krw: float, participation: float = 0.0) -> float:
    """거래대금 참여율에 대한 제곱근 충격모형:  impact ≈ base + K·√(참여율).

    ★ participation(시나리오의 참여율 '상한')을 충격식에 곱하면 안 된다.
      한때 `base + K·√(part/P)·P` 였는데 이는 `base + K·√part·√P` 와 같아서,
      상한을 넉넉히 준 낙관 시나리오(P=0.20)가 빡빡한 비관 시나리오(P=0.05)보다
      슬리피지가 커지는 역전이 발생했다 — 비용 시나리오의 의미가 뒤집힌다.
      상한은 '얼마나 살 수 있는가'(사이징)에만 쓰고, 충격은 실제 참여율만의 함수다.
    """
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.0300                      # 거래대금을 모르면 3% 로 보수적으로 계상
    part = min(max(float(trade_krw) / float(adv_krw), 0.0), 1.0)
    return SLIPPAGE_BASE + SLIPPAGE_K * math.sqrt(part)


def _cap_weights(w: pd.Series, cap: pd.Series, max_iter: int = 8) -> pd.Series:
    """상한을 지키면서 재분배한다. 남는 몫은 현금으로 둔다.

    ★ `w = min(w, cap); w = w / w.sum()` 는 상한을 무효화한다.
      상한이 전 종목에 걸리면 정규화가 정확히 원래 비중을 복원해 버리기 때문이다
      (5종목 각 0.12 → 합 0.60 → 정규화 → 각 0.20). 소형주 용량 제약을 보겠다는
      R9 의 참여율 상한이 아무 일도 하지 않게 된다.
    → 상한을 건 뒤 '여유가 있는 종목에만' 재분배하고, 그래도 남으면 현금으로 남긴다.
    """
    w = w.astype("float64").copy()
    cap = cap.astype("float64").reindex(w.index).fillna(0.0)
    w = np.minimum(w, cap)
    for _ in range(max_iter):
        s = float(w.sum())
        if s >= 1.0 - 1e-9:
            break
        room = (cap - w).clip(lower=0.0)
        tot = float(room.sum())
        if tot <= 1e-12:
            break                          # 전 종목이 상한 → 나머지는 현금
        w = w + room * min(1.0, (1.0 - s) / tot)
    return w.clip(lower=0.0)


def _select_month(sub: pd.DataFrame, top_pct: float, max_n: int, min_n: int) -> pd.DataFrame:
    """그 달의 목표 포트폴리오. 월 전체를 한 줄로 세워 상위 X% 를 뽑는다."""
    live = sub[sub["Signal"] > 0]
    if len(live) == 0:
        return live
    n = int(np.clip(round(len(live) * top_pct), min_n, max_n))
    n = min(n, len(live))
    return live.nlargest(n, "Signal")


def run_backtest_micro(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                       variant: str = "D", scenario: str = COST_BASE_SCENARIO,
                       label: str = "", quiet: bool = False) -> dict:
    """월별 백테스트. 반환에는 월 수익률·보유내역·회전율·비용이 전부 들어간다."""
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    roundtrip, participation = float(scn["roundtrip"]), float(scn["participation"])
    one_way = roundtrip / 2.0

    dmap = uni.delisting_map() if uni is not None else {}
    need = ["code", "month", "Signal", "fwd_ret", "adv20", "VETO", "FW", "close", "d1_trailing"]
    D = P[[c for c in need if c in P.columns]].copy()
    for c in need:
        if c not in D.columns:
            D[c] = np.nan
    D = D.sort_values(["month", "Signal"], ascending=[True, False], kind="stable")
    by_month = {m: g for m, g in D.groupby("month", observed=True)}

    prev_w: Dict[str, float] = {}
    entry_m: Dict[str, pd.Timestamp] = {}
    recs, holdings_log = [], []

    for t in months:
        sub = by_month.get(t)
        if sub is None or len(sub) == 0:
            if prev_w:
                # 그 달 패널이 통째로 비면 보유를 유지하되 수익률은 0 으로 둔다(추정 금지)
                recs.append({"month": t, "ret_gross": 0.0, "cost": 0.0, "ret": 0.0,
                             "n": len(prev_w), "turnover": 0.0})
            continue
        sub = sub.set_index("code")

        tgt = _select_month(sub.reset_index(), PORTFOLIO_TOP_PCT,
                            PORTFOLIO_MAX_NAMES, PORTFOLIO_MIN_NAMES)
        tgt_codes = list(tgt["code"]) if len(tgt) else []

        # ── 유지 판정 (§10 청산 규칙) ────────────────────────────────────────────────
        band = sub["Signal"].rank(pct=True, ascending=True)   # 1.0 = 최고
        keep = []
        for c in prev_w:
            if c not in sub.index:
                continue                                       # 패널 이탈 → 청산(상폐 포함)
            # ★ 결측은 '유지'가 아니라 '청산'이다.
            #   `float(x or 0) == 0` 은 NaN 에서 무너진다: NaN 은 truthy 라 `or` 를 통과하고
            #   float(NaN)==0 은 False 라 청산 분기가 발동하지 않는다. 그 결과 거부권 데이터가
            #   결측인 종목은 '영원히 보유'된다 — 살 수는 없는데(신호 쪽은 fillna(0)) 팔지도
            #   못하는 좀비 포지션이 생긴다.
            if not float(pd.to_numeric(sub.at[c, "VETO"], errors="coerce") or 0.0) == 1.0:
                continue                                       # 거부권 발동/결측 → 즉시 청산
            if not float(pd.to_numeric(sub.at[c, "FW"], errors="coerce") or 0.0) == 1.0:
                continue                                       # 방화벽 이탈/결측 → 청산
            held = (t.year - entry_m[c].year) * 12 + (t.month - entry_m[c].month)
            if held >= HOLD_MAX_MONTHS:
                continue                                       # 보유 상한
            # 청산 게이트(§10): ΔlogM 이 ΔlogE 수준까지 확장 = 논거가 가격에 반영 완료
            d1 = sub.at[c, "d1_trailing"] if "d1_trailing" in sub.columns else np.nan
            if pd.notna(d1) and float(d1) >= 0.0:
                continue
            # ★ 위 FW/VETO 와 같은 이유로 여기서도 결측은 '청산'이다.
            #   `float(nan) < 0.90` 은 False 라, 신호가 사라진 종목이 청산 분기를 그대로
            #   통과해 최대 24개월 동안 보유된다 — 살 수는 없는데 팔지도 못하는 포지션이다.
            _b = pd.to_numeric(pd.Series([band.get(c, np.nan)]), errors="coerce").iloc[0]
            if not (pd.notna(_b) and float(_b) >= (1.0 - 2 * PORTFOLIO_TOP_PCT)):
                continue                                       # 신호 밴드 이탈/결측 → 청산

            keep.append(c)

        # ★ 보유분(keep)을 신규 목표(tgt)보다 무조건 앞세우면 안 된다.
        #   PORTFOLIO_MAX_NAMES=25 이고 유니버스가 500종목만 넘어도 목표 종목수가 25가 되어,
        #   keep 이 25개를 채우는 순간 tgt 가 통째로 잘려 나간다. 전략이 조용히
        #   "한 번 사서 24개월 보유"로 퇴화하고, 그게 A/B/C/D 스프레드를 압착한다.
        #   → 보유·신규를 합쳐 신호 순으로 상위 N 개를 고른다(보유는 위 게이트를 이미 통과했다).
        cand = list(dict.fromkeys(keep + tgt_codes))
        if len(cand) > PORTFOLIO_MAX_NAMES:
            _sc = (pd.to_numeric(sub.reindex(cand)["Signal"], errors="coerce")
                     .fillna(-np.inf).sort_values(ascending=False))
            cand = list(_sc.index[:PORTFOLIO_MAX_NAMES])
        chosen = cand
        if not chosen:
            # 조건을 만족하는 종목이 없으면 현금. 억지로 채우지 않는다.
            if prev_w:
                turn = sum(abs(0.0 - w) for w in prev_w.values())
                cost = turn * one_way
                recs.append({"month": t, "ret_gross": 0.0, "cost": cost, "ret": -cost,
                             "n": 0, "turnover": turn})
                prev_w, entry_m = {}, {}
            continue

        # ── 사이징: 동일가중 → 거래대금 참여율 상한 → 여유분만 재분배(나머지는 현금) ──
        # adv 는 '그 달 전체'에서 만든다. 매도 종목(chosen 밖)도 비용 계산에 필요한데
        # chosen 으로만 만들면 전부 결측이 되어 매도마다 3% 폴백 슬리피지를 문다.
        adv_all = pd.to_numeric(sub["adv20"], errors="coerce")
        w = pd.Series(1.0 / len(chosen), index=chosen, dtype="float64")
        cap_adv = (participation * adv_all.reindex(chosen) / max(ACCOUNT_KRW, 1))
        cap_adv = cap_adv.clip(upper=POS_MAX_WEIGHT).fillna(POS_MIN_WEIGHT)
        w = _cap_weights(w, cap_adv)
        w = w[w >= POS_MIN_WEIGHT * 0.5]
        if float(w.sum()) <= 0:
            continue
        cash_w = max(0.0, 1.0 - float(w.sum()))                # 용량 부족분은 현금(수익률 0)

        # ── 수익률 (상장폐지 -100% 강제) ─────────────────────────────────────────────
        fr = pd.to_numeric(sub.reindex(w.index)["fwd_ret"], errors="coerce")
        nxt = t + pd.offsets.MonthEnd(1)
        nxt_sub = by_month.get(nxt)
        nxt_codes = set(nxt_sub["code"].astype(str)) if nxt_sub is not None else None
        n_forced = 0
        for c in w.index:
            dd = dmap.get(c)
            has_dd = dd is not None and pd.notna(dd) and dd > t
            # ★ 폐지월 창(t < dd <= 다음달)만 보면 안 된다.
            #   한국 소형주의 전형적 경로는 '거래정지 → 수 개월 실질심사 → 상장폐지'다.
            #   정지 시점부터 가격 행이 끊겨 fwd_ret 이 NaN 이 되는데, 폐지일은 몇 달 뒤라
            #   창 조건이 거짓이 되고, fillna(0.0) 이 그 달을 0% 로 기록한다.
            #   = 전액을 잃은 포지션이 '본전'으로 계상된다(생존자편향 재유입, C2 위반).
            # ★ 결측이라는 이유만으로 -100% 를 찍으면 안 된다. 가격 소스가 한 달 비었을 뿐인
            #   2018년의 종목이, 2025년에 폐지 예정이라는 이유로 2018년에 전액손실 처리된다.
            #   → 폐지일이 지났거나, 결측이면서 **다음 달 패널에서도 사라졌을 때**만 확정한다.
            if has_dd and (dd <= nxt or (pd.isna(fr.get(c, np.nan))
                                         and (nxt_codes is None or c not in nxt_codes))):
                fr.at[c] = -1.0
                n_forced += 1
                continue
            # ★ 폐지일을 아예 모르는 종목이 더 위험하다.
            #   FDR 폐지목록은 부분적일 수 있고(코드가 그 사실을 경고한다), 그런 종목은
            #   dmap 에 없어서 위 분기를 전부 비껴간다. 거래가 끊겼는데 폐지일도 없으면
            #   조용히 0% 가 된다 — 커버리지가 나쁠수록 성과가 좋아지는 최악의 편향이다.
            #   → 다음 달 패널에서 사라졌고 수익률도 없으면 '사실상 상장폐지'로 간주한다.
            if (not has_dd) and pd.isna(fr.get(c, np.nan)) and nxt_codes is not None \
                    and c not in nxt_codes:
                fr.at[c] = -1.0
                n_forced += 1
        n_nan = int(fr.isna().sum())
        fr = fr.fillna(0.0)             # 다음 달에도 살아 있는 종목의 일시적 결측만 0 (추정 금지)

        ret_gross = float((w * fr).sum())                      # 현금분은 수익률 0

        # ── 비용: 회전율 × 편도비용 + 슬리피지 + 매도세 ──────────────────────────────
        # ★ 직전 비중은 '목표'가 아니라 '드리프트된 실제' 비중과 비교해야 한다.
        #   지난달 목표를 그대로 두고 비교하면, 종목별 수익률 차이로 이미 벌어진 비중을
        #   되돌리는 거래(리밸런싱의 본질)가 회전율에서 통째로 빠진다.
        allc = set(w.index) | set(prev_w)
        turn = float(sum(abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0))) for c in allc))
        slip = 0.0
        for c in allc:
            dw = abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0)))
            if dw <= 0:
                continue
            a = float(adv_all.get(c, np.nan)) if c in adv_all.index else np.nan
            slip += dw * slippage_bps(dw * ACCOUNT_KRW, a)
        sells = float(sum(max(float(prev_w.get(c, 0.0)) - float(w.get(c, 0.0)), 0.0) for c in allc))
        cost = turn * one_way + slip + sells * sell_tax_rate(t)

        recs.append({"month": t, "ret_gross": ret_gross, "cost": cost,
                     "ret": ret_gross - cost, "n": int(len(w)), "turnover": turn,
                     "cash_w": cash_w, "na_fwd": n_nan, "delist_forced": n_forced})
        for c in w.index:
            holdings_log.append({"month": t, "code": c, "w": float(w[c]),
                                 "signal": float(sub.at[c, "Signal"] or 0.0),
                                 "fwd_ret": float(fr[c])})
        for c in w.index:
            entry_m.setdefault(c, t)
        for c in list(entry_m):
            if c not in w.index:
                entry_m.pop(c, None)
        # 다음 달 비교 기준은 '드리프트된 실제 비중'이다(목표 비중이 아니다).
        drift = w * (1.0 + fr.reindex(w.index).fillna(0.0))
        tot = float(drift.sum()) + cash_w
        prev_w = (drift / tot).to_dict() if tot > 0 else {}

    R = pd.DataFrame(recs)
    if len(R):
        R = R.sort_values("month").reset_index(drop=True)
        # ★ 보유가 없던 달은 recs 에 아예 안 들어간다. 그대로 두면 연율화 분모(개월수)가
        #   줄어 CAGR·Sharpe 가 과대계상된다(현금으로 쉰 기간이 사라진다).
        #   전 구간 격자에 맞춰 채운다 — 쉰 달은 수익률 0 이다.
        full = pd.DataFrame({"month": pd.DatetimeIndex(months)})
        R = full.merge(R, on="month", how="left")
        for c in ("ret_gross", "cost", "ret", "turnover", "n", "cash_w", "na_fwd",
                  "delist_forced"):
            if c in R.columns:
                R[c] = pd.to_numeric(R[c], errors="coerce").fillna(0.0)
        R.loc[R["n"] == 0, "cash_w"] = 1.0
        R["equity"] = (1.0 + R["ret"]).cumprod()
    H = pd.DataFrame(holdings_log)
    out = {"variant": variant, "scenario": scenario, "label": label or variant,
           "returns": R, "holdings": H, "stats": perf_stats(R)}
    if not quiet:
        s = out["stats"]
        LOG.ok(f"[{label or variant}·{scenario}] CAGR {100*s['cagr']:.2f}% · "
               f"MDD {100*s['mdd']:.1f}% · Calmar {s['calmar']:.2f} · "
               f"Sharpe {s['sharpe']:.2f} · 월평균 {s['avg_n']:.0f}종목 · "
               f"회전율 {100*s['turnover']:.0f}%/월 · 상폐확정 {s.get('delist_forced', 0):.0f}건"
               + (f" · 결측0%처리 {s.get('na_zero', 0):.0f}건" if s.get('na_zero', 0) else ""))
    PIPE.io("OUT", "MEM", f"backtest:{label or variant}", R)
    return out


def perf_stats(R: pd.DataFrame) -> dict:
    """성과 지표. 표본이 없으면 0 이 아니라 NaN 을 돌려준다(없는 성과를 만들지 않는다)."""
    if R is None or len(R) == 0 or "ret" not in R.columns:
        return {"n_months": 0, "cagr": np.nan, "vol": np.nan, "sharpe": np.nan,
                "mdd": np.nan, "calmar": np.nan, "hit": np.nan, "turnover": np.nan,
                "avg_n": np.nan, "total": np.nan, "cost_drag": np.nan, "cash": np.nan,
                "delist_forced": np.nan, "na_zero": np.nan}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy()
    n = len(r)
    # ★ 자본 기준선 1.0 을 앞에 붙인다.
    #   cumprod 만 쓰면 eq[0] = 1+r[0] 이고 peak[0] = eq[0] 이라 '첫 달의 하락'이
    #   정의상 드로다운 0 이 된다. r=[-0.30, ...] 이 MDD 0% 로 보고되고, Calmar 가
    #   NaN 또는 무한대가 되어 킬 게이트 판정이 통째로 뒤집힌다.
    eq = np.concatenate(([1.0], np.cumprod(1.0 + r)))
    total = float(eq[-1] - 1.0)
    yrs = n / 12.0
    cagr = float(eq[-1] ** (1.0 / yrs) - 1.0) if yrs > 0 and eq[-1] > 0 else -1.0
    vol = float(np.std(r, ddof=1) * math.sqrt(12)) if n > 1 else np.nan
    sharpe = float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(12)) if n > 1 and np.std(r, ddof=1) > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    mdd = float(np.min(eq / peak - 1.0)) if n else np.nan
    # 드로다운이 정확히 0 이면 Calmar 는 정의되지 않는다. 수익이 양수면 +inf 가 맞지만
    # 비교에 쓰이므로 매우 큰 유한값으로 두고, 손실이면 0 으로 둔다.
    if mdd is None or not np.isfinite(mdd) or mdd >= 0:
        calmar = (999.0 if (np.isfinite(cagr) and cagr > 0) else 0.0) if n else np.nan
    else:
        calmar = float(cagr / abs(mdd))
    # ★ R.get("x") 는 컬럼이 없으면 None 을 돌려주고, pd.to_numeric(None) 은 Series 가 아니라
    #   numpy 스칼라가 된다 → .fillna() 에서 AttributeError. col() 은 없는 컬럼도 NaN Series 로
    #   돌려주므로 이 경로가 원천 차단된다.
    def _m(name: str, how: str = "mean") -> float:
        s = col(R, name)
        s = pd.to_numeric(s, errors="coerce").fillna(0.0)
        return float(getattr(s, how)()) if len(s) else 0.0

    return {"n_months": n, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd,
            "calmar": calmar, "hit": float((r > 0).mean()), "total": total,
            "turnover": _m("turnover"), "avg_n": _m("n"), "cost_drag": _m("cost", "sum"),
            "cash": _m("cash_w"), "delist_forced": _m("delist_forced", "sum"),
            "na_zero": _m("na_fwd", "sum")}


def benchmark_universe_ew(P: pd.DataFrame, months: pd.DatetimeIndex,
                          scenario: str = COST_BASE_SCENARIO,
                          mask_col: Optional[str] = None,
                          uni: Optional["Universe"] = None) -> dict:
    """R0(a) 자체 측정 벤치마크 — U-MICRO 유니버스 동일가중.

    ★ 벤치마크 수치를 하드코딩하지 않는다(원칙 5). 같은 데이터·같은 비용모형으로 직접 잰다.
    동일가중도 매월 리밸런싱하므로 회전율이 있고, 그 비용을 똑같이 물린다.

    ★ 상장폐지를 전략과 '똑같이' 처리해야 한다. ─────────────────────────────────────
      fwd_ret 이 NaN 인 행을 그냥 버리면 거래가 끊긴 종목(=대부분 상장폐지)이 벤치마크에서
      조용히 사라져, 살아남은 종목만의 수익률이 기준선이 된다. 그러면 전략이 아무리
      좋아도 이길 수 없는 '생존자 벤치마크'와 싸우게 되고, R0/R2-M 판정이 통째로 왜곡된다.
    """
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    one_way = float(scn["roundtrip"]) / 2.0
    sub = P
    if mask_col and mask_col in P.columns:
        sub = P[P[mask_col].astype(bool)]
    sub = sub[["code", "month", "fwd_ret"]].copy()
    # 폐지 예정 종목의 끊긴 달은 -100% 로 확정한 뒤에 결측을 버린다(순서가 중요하다).
    if uni is not None:
        dmap = uni.delisting_map()
        if dmap:
            dd = sub["code"].map(dmap)
            kill = sub["fwd_ret"].isna() & dd.notna() & (as_ts_series(dd) > sub["month"])
            n_kill = int(kill.sum())
            if n_kill:
                sub.loc[kill, "fwd_ret"] = -1.0
                LOG.debug(f"벤치마크(동일가중)에서 상장폐지 {n_kill:,}종목월을 -100% 로 확정했습니다 "
                          f"(전략과 동일한 처리 — 생존자 벤치마크 방지).")
    # ★ 전략은 '폐지목록에 없는데 다음 달 사라진' 종목도 -100% 로 확정한다(FDR 폐지목록의
    #   공백을 메우는 규칙). 벤치마크가 그 규칙을 안 쓰면 벤치마크만 그 손실을 면제받아
    #   '부분 생존자 벤치마크'가 된다 — R0a·R2-M① 이 그 격차만큼 전략에 불리해진다.
    #   여기서 같은 규칙을 적용해 비교 기준을 대칭으로 맞춘다.
    if len(sub):
        _ms = sorted(pd.unique(sub["month"]))
        _pos = {m: i for i, m in enumerate(_ms)}
        _inv = {i: m for m, i in _pos.items()}
        _have = set(zip(sub["code"].astype(str), sub["month"]))
        _nm = sub["month"].map(_pos).add(1).map(_inv)
        _gone = pd.Series([(c, m) not in _have for c, m in zip(sub["code"].astype(str), _nm)],
                          index=sub.index)
        kill2 = sub["fwd_ret"].isna() & _nm.notna() & _gone
        n2 = int(kill2.sum())
        if n2:
            sub.loc[kill2, "fwd_ret"] = -1.0
            LOG.debug(f"벤치마크에서 '폐지일 미상이나 다음 달 소멸' {n2:,}종목월도 -100% 로 "
                      f"확정했습니다 (전략과 동일 규칙).")
    sub = sub[sub["fwd_ret"].notna()]
    if len(sub) == 0:
        return {"label": "유니버스 동일가중", "returns": pd.DataFrame(), "stats": perf_stats(None)}
    g = sub.groupby("month", observed=True)
    m = g["fwd_ret"].mean()
    cnt = g["code"].size()

    # ★ 회전율을 상수로 가정하지 않는다. 실제 편입/이탈로 계산한다.
    #   상수 20% 를 쓰면 벤치마크 비용이 데이터와 무관해지고, 전략만 슬리피지·거래세를
    #   물고 벤치마크는 안 무는 비대칭이 생겨 R0/R2-M 판정이 기울어진다.
    members = {mm: set(gg["code"]) for mm, gg in sub.groupby("month", observed=True)}
    idx = sorted(members)
    turn_v, sells_v = [], []
    prev: set = set()
    for mm in idx:
        cur = members[mm]
        nc, np_ = max(len(cur), 1), max(len(prev), 1)
        if not prev:
            turn_v.append(1.0); sells_v.append(0.0)
        else:
            # 동일가중 기준 Σ|w_t − w_{t−1}|
            allc = cur | prev
            t_ = sum(abs((1.0 / nc if c in cur else 0.0) - (1.0 / np_ if c in prev else 0.0))
                     for c in allc)
            s_ = sum(max((1.0 / np_ if c in prev else 0.0) - (1.0 / nc if c in cur else 0.0), 0.0)
                     for c in allc)
            turn_v.append(float(t_)); sells_v.append(float(s_))
        prev = cur
    T = pd.Series(turn_v, index=pd.DatetimeIndex(idx))
    S = pd.Series(sells_v, index=pd.DatetimeIndex(idx))

    R = pd.DataFrame({"month": m.index, "ret_gross": m.to_numpy(), "n": cnt.to_numpy()})
    R["turnover"] = T.reindex(R["month"]).to_numpy()
    _sells = S.reindex(R["month"]).to_numpy()
    # 전략과 동일한 비용 구성: 편도수수료 + 호가스프레드 + 매도 시 증권거래세
    R["cost"] = (R["turnover"] * one_way + R["turnover"] * SLIPPAGE_BASE
                 + _sells * np.array([sell_tax_rate(x) for x in R["month"]]))
    R["ret"] = R["ret_gross"] - R["cost"]
    R = (pd.DataFrame({"month": pd.DatetimeIndex(months)})
         .merge(R, on="month", how="left"))
    for c in ("ret_gross", "cost", "ret", "turnover", "n"):
        R[c] = pd.to_numeric(R[c], errors="coerce").fillna(0.0)
    R["equity"] = (1.0 + R["ret"]).cumprod()
    return {"label": "유니버스 동일가중", "variant": "BENCH", "scenario": scenario,
            "returns": R, "holdings": pd.DataFrame(), "stats": perf_stats(R)}


def benchmark_index(months: pd.DatetimeIndex) -> Dict[str, dict]:
    """참고용 지수 벤치마크(코스닥/코스피). 없으면 조용히 건너뛴다 — 필수가 아니다."""
    out: Dict[str, dict] = {}
    if fdr is None or RUN_MODE == "SMOKE":
        return out
    for name, sym in (("KOSDAQ", "KQ11"), ("KOSPI", "KS11")):
        try:
            d = fdr.DataReader(sym, str(months[0].date()), str(months[-1].date()))
        except Exception:
            continue
        if d is None or len(d) == 0 or "Close" not in d.columns:
            continue
        s = (d["Close"].resample(pd.offsets.MonthEnd()).last()
             if hasattr(d["Close"], "resample") else None)
        if s is None or len(s) < 3:
            continue
        r = s.pct_change().dropna()
        R = pd.DataFrame({"month": as_ts_series(pd.Series(r.index)) + pd.offsets.MonthEnd(0),
                          "ret": r.to_numpy()})
        R = R[R["month"].isin(months)].reset_index(drop=True)
        if len(R) < 3:
            continue
        R["equity"] = (1.0 + R["ret"]).cumprod()
        out[name] = {"label": name, "returns": R, "stats": perf_stats(R)}
    return out
