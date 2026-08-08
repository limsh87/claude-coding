

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  체결 · 비용 · 성과   (§8.3 · §8.4)                                                    ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱. 체결 = 신호 산출일 **다음 거래일 시가**. 당일 종가 체결 금지(미래누수). ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(= 생존자편향).              ║
# ║  · 롱온리. 음의 신호는 청산 게이트로만 쓴다.                                                ║
# ║  · ★ C13(c): 보유 중 밴드 이탈은 청산 사유가 아니다. u_mid 는 **진입 필터 전용**이다.       ║
# ║      졸업(시총이 커져 밴드를 벗어남)은 성공 신호이므로 그걸 이유로 팔면 안 된다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TAX_SCHEDULE = [                       # 증권거래세(매도). 농특세 포함 총부담 기준.
    ("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
]
COMMISSION_BPS = 1.5                   # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10                      # 제곱근 충격 계수
SLIPPAGE_FLOOR = 0.0015                # 호가스프레드 하한. 소액이라고 비용이 0 이 되지는 않는다


def sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격 + 스프레드 하한.

    ★ 하한이 없으면 소액계좌(3천만원) 가정에서 참여율이 1e-4 수준이 되어 슬리피지가 사실상
      0 이 된다. 그러면 R9(용량) 검사가 '비용이 없으니 성과가 그대로'라는 무의미한 답을 낸다.
      실제로는 소형주 호가스프레드만으로도 왕복 30~100bp 가 든다.
    """
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(max(SLIPPAGE_FLOOR, SLIPPAGE_K * math.sqrt(part)))


def exit_gate(dm, de) -> bool:
    """§8.3 청산: 'ΔlogM 이 ΔlogE 수준까지 확장 완료' 또는 논거 무효.

    진입 논리는 ΔlogE > 0 이고 시장이 아직 자본화하지 않음(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다 (알파 소진 — 원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다 (논거 무효)
    ★ v2 는 `dm >= de and de > 0` 이었다. 뒤 조건이 'de<=0' 인 전 구간을 닫아버려
      논거가 깨진 종목을 청산하는 경로가 통째로 막혀 있었다(24개월 상한까지 자리를 차지).
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '먼저 나온 행'을 고른다. 패널이 code 로 정렬돼
      있으면 그건 '종목코드가 작은 순'이다. 동점이 많으면 보유종목이 데이터가 아니라
      정렬의 함수가 된다(v2 실측: 월 보유의 70%가 동점 1.0). 정렬키를 명시해 결정성을 준다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "E", "code") if c in df.columns and c != signal_col]
    asc = [False] + [True if c == "code" else False for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중."""
    s = col(sub, "Signal_rank").fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    if spread < 1e-6:
        w = np.full(len(s), 1.0 / len(s))
    else:
        raw = np.clip(s - med, 0, None) + 1e-9
        w = raw ** min(2.0, 0.5 + spread * 8.0)
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    adv = col(sub, "adv20").fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1), POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))
    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다. 상한에 걸린 종목은 고정하고
    #   나머지에만 잔여를 재배분하는 water-filling 으로 강제한다.
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
    if w.sum() > 1.0 + 1e-9:                     # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    return sub.assign(weight=w)


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, sec: pd.DataFrame,
                 signal_col: str = "Signal_rank", top_pct: float = PORTFOLIO_TOP_PCT,
                 apply_costs: bool = True, label: str = "CORE-D",
                 entry_col: str = "u_mid", quiet: bool = True,
                 max_names: int = PORTFOLIO_MAX_NAMES,
                 min_names: int = PORTFOLIO_MIN_NAMES) -> dict:
    delist = {}
    if "delisting_date" in sec.columns:
        dd = as_ts_series(sec["delisting_date"])
        delist = {c: d for c, d in zip(sec["code"].astype(str), dd) if pd.notna(d)}

    need = [c for c in ("adv20", "fwd_ret", "VETO", "FLOOR", "dlog_M", "dlog_E", "exec_px",
                        entry_col, "Signal", "E", signal_col) if c in P.columns]
    Pm = {m: g for m, g in P[["code", "month"] + need].groupby("month", observed=True)}

    hold: Dict[str, int] = {}
    rows, holdings_log, gates = [], [], []
    prev_w: Dict[str, float] = {}
    charged: set = set()          # 폐지 -100% 를 이미 계상한 종목 (이중 계상 방지)
    n_unresolved, w_unresolved = 0, 0.0   # 결과 미관측 보유 — 0% 로 계상한 건수·가중치
    n_noselect = 0                # 후보 ≤ k 라 '상위 N%'가 '전부'가 된 달

    for m in months:
        sub = Pm.get(m)
        if sub is None or sub.empty:
            # ★ prev_w 를 비우면 그 달에 보유 종목이 **비용 없이 증발**하고, 그 사이에 폐지된
            #   종목의 -100% 도 영원히 계상되지 않는다(생존자편향 재유입).
            #   패널에 그 달 행이 없는 건 데이터 공백이지 청산이 아니다 — 보유를 이월한다.
            rows.append({"month": m, "ret": 0.0, "ret_gross": 0.0, "n": 0,
                         "turnover": 0.0, "cost": 0.0, "invested": 0.0, "empty": 1})
            continue
        sub = sub.copy()
        rec = {c: dict(zip(sub["code"], sub[c])) for c in need if c in sub.columns}

        # ── 진입 후보: 유니버스 밴드 ∧ 거부권 ∧ 하한선 ─────────────────────────────────
        band = sub[entry_col].astype(bool) if entry_col in sub.columns else pd.Series(True, index=sub.index)
        # 폐지일이 지난 종목은 진입 후보에서도 무조건 제외한다 (유니버스 플래그와 무관하게).
        # ★ 파이썬 람다로 쓰면 종목수×개월수 만큼 호출된다. 강건성 스위트가 백테스트를
        #   40회 가까이 재실행하므로 그 비용이 그대로 곱해진다 — dict map 으로 벡터화한다.
        gone = as_ts_series(sub["code"].map(delist)).le(m).fillna(False)
        elig = sub[band & ~gone & (sub["VETO"] == 1) & (sub["FLOOR"] == 1)
                   & sub[signal_col].notna() & sub["exec_px"].notna()]
        gates.append({"month": m, "패널": len(sub), "U_MID": int(band.sum()),
                      "거부권통과": int((band & (sub["VETO"] == 1)).sum()),
                      "하한선통과": int((band & (sub["VETO"] == 1) & (sub["FLOOR"] == 1)).sum()),
                      "체결가보유": len(elig)})

        k = int(max(min_names, min(max_names, round(len(elig) * top_pct))))
        # ★ 후보가 k 이하면 '상위 top_pct%' 선택이 곧 '전부 선택'이 된다 — 신호가
        #   포트폴리오에 아무 영향을 주지 못하는 상태다(R1a 가 Δ0.000 으로 잡아낸 것).
        #   조용히 지나가면 '신호로 고른 결과'로 오독되므로 달 수를 센다.
        if len(elig) and len(elig) <= k:
            n_noselect += 1
        pick = _top_n(elig, k, signal_col) if len(elig) else elig

        # ── 청산 게이트 ───────────────────────────────────────────────────────────────
        #   ★ 여기서 u_mid 를 보지 않는다. C13(c) — 밴드 이탈(=졸업)은 청산 사유가 아니다.
        keep = []
        for c in list(hold):
            # ★ C2 강제: 폐지일이 지난 종목은 어떤 경로로도 보유되지 않는다.
            #   실데이터에서는 폐지 후 가격이 없어 자연히 빠지지만, 그건 '우연히 안전한' 것이지
            #   보장이 아니다. 가격 소스가 폐지 후 값을 하나라도 주면(정리매매 잔재·데이터 오류)
            #   그 종목이 계속 보유되어 이미 -100% 를 계상한 포지션이 되살아난다.
            _dl = delist.get(c)
            if _dl is not None and pd.notna(_dl) and _dl <= m:
                continue
            if c not in rec.get("exec_px", {}):
                continue                                   # 패널에서 사라짐(폐지) → 아래서 -100%
            if rec.get("VETO", {}).get(c, 1) == 0:
                continue                                   # 거부권 발동 → 즉시 강제청산
            if hold[c] >= HOLD_MAX_MONTHS:
                continue
            if exit_gate(rec.get("dlog_M", {}).get(c), rec.get("dlog_E", {}).get(c)):
                continue
            keep.append(c)

        picked = set(pick["code"]) if len(pick) else set()
        carry = sub[sub["code"].isin([c for c in keep if c not in picked])]
        target = pd.concat([pick, carry], ignore_index=True) if len(carry) else pick
        if len(target) > max_names:
            target = _top_n(target, max_names, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])
        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}

        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in set(w_new) | set(prev_w))
        cost = 0.0
        if apply_costs:
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                a = rec.get("adv20", {}).get(c)
                adv = float(a) if a is not None and pd.notna(a) else 0.0
                cost += abs(dw) * (COMMISSION_BPS / 1e4
                                   + slippage(abs(dw) * ACCOUNT_KRW, adv)
                                   + (sell_tax(m) if dw < 0 else 0.0))

        ret = 0.0
        for c, w in w_new.items():
            f = rec.get("fwd_ret", {}).get(c)
            fr = float(f) if f is not None and pd.notna(f) else np.nan
            dl = delist.get(c)
            if (dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1)
                    and c not in charged):
                # ★ 상장폐지: 정리매매 최종가가 없으면 -100%. 누락 처리 금지(C2).
                if not np.isfinite(fr):
                    fr = -1.0
                    charged.add(c)          # 같은 폐지를 두 번 계상하지 않는다
            if not np.isfinite(fr):
                # ★ 결과를 관측하지 못한 보유(거래정지·가격결손·마지막 달).
                #   0% 는 '아무 일도 없었다'는 적극적 주장이라 **성과를 부풀리는 방향**이다.
                #   여기서 임의로 -100% 를 때리면 반대로 과도하다 → 0 으로 두되 **세어서 보고**한다.
                fr = 0.0
                n_unresolved += 1
                w_unresolved += float(w)
            ret += w * fr
            holdings_log.append({"month": m, "code": c, "weight": w, "ret": fr,
                                 "signal": rec.get(signal_col, {}).get(c, np.nan)})
        # 폐지로 패널에서 사라진 보유 종목도 손실을 계상한다(빠뜨리면 생존자편향)
        for c, w in prev_w.items():
            if c in w_new or c in rec.get("exec_px", {}):
                continue
            dl = delist.get(c)
            # ★★ 이중 계상 방지 ★★ 위 루프와 달리 하한(m < dl)이 없어서, 직전 달에 이미
            #   -100% 를 맞은 종목이 이번 달에 **또** -100% 를 맞았다.
            #   (마지막 거래가 m-1 월, 폐지일이 m 월인 한국의 전형적 관리→정지→상폐 경로에서
            #    항상 발생한다) 12% 비중이면 -12% 가 아니라 -24% 가 계상된다.
            #   실측 누적 -18.2% 는 이런 사건 두 건만으로 만들어질 수 있는 크기다.
            if (dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1)
                    and c not in charged):
                ret += w * (-1.0)
                charged.add(c)
                holdings_log.append({"month": m, "code": c, "weight": w, "ret": -1.0,
                                     "signal": np.nan})

        # invested = 실제 투자 비중. 종목별 상한(POS_MAX_WEIGHT)에 걸려 남은 잔여는 현금이다.
        #   1종목만 잡히면 12% 만 투자되고 88% 가 무이자 현금이라, CAGR·변동성·MDD 가
        #   전부 1/8 로 압축된다. 그 사실을 숫자로 남겨야 성과표를 옳게 읽을 수 있다.
        rows.append({"month": m, "ret": ret - cost, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost,
                     "invested": float(sum(w_new.values())), "empty": 0})
        hold = {c: (hold.get(c, 0) + 1) for c in w_new}
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    G = pd.DataFrame(gates)
    if not quiet and len(G):
        LOG.table([[g, f"{G[g].mean():,.0f}", f"{G[g].min():,.0f}", f"{G[g].max():,.0f}",
                    ("" if i == 0 else f"{100*G[g].mean()/max(G[G.columns[1]].mean(),1e-9):.0f}%")]
                   for i, g in enumerate([c for c in G.columns if c != "month"])],
                  ["게이트", "월평균", "최소", "최대", "U-MID 대비"], ["l", "r", "r", "r", "r"],
                  title="선정 깔때기 — 어느 게이트에서 후보가 사라지는지")
    # ── 성과표를 읽는 데 필요한 '노출' 진단 ────────────────────────────────────────────
    #   종목당 상한 때문에 소수 종목만 잡히면 대부분이 현금이다. 그 상태의 CAGR·변동성·MDD 는
    #   전략의 것이 아니라 '전략 × 노출비중'의 것이다. 비교 가능한 형태로 함께 남긴다.
    inv = pd.to_numeric(R.get("invested", pd.Series(1.0, index=R.index)),
                        errors="coerce").fillna(0.0)
    n_empty = int((pd.to_numeric(R.get("n", 0), errors="coerce").fillna(0) <= 0).sum())
    diag = {"n_months": int(len(R)), "n_empty": n_empty,
            "mean_invested": float(inv.mean()),
            "mean_invested_active": float(inv[inv > 0].mean()) if (inv > 0).any() else 0.0,
            "n_unresolved": int(n_unresolved), "w_unresolved": float(w_unresolved),
            "n_delist_charged": int(len(charged)), "n_noselect": int(n_noselect)}
    # 투자자본 기준 수익률 — 현금 희석을 걷어낸 계열. 해석용이며 실제 성과가 아니다.
    R["ret_invested"] = np.where(inv > 1e-9, R["ret"] / inv.where(inv > 1e-9), np.nan)
    if not quiet:
        LOG.table([
            ["관측 개월", f"{diag['n_months']}"],
            ["포지션 없던 달", f"{n_empty} ({100*n_empty/max(len(R),1):.0f}%)"],
            ["평균 투자비중(전체)", f"{diag['mean_invested']*100:.1f}%"],
            ["평균 투자비중(보유월)", f"{diag['mean_invested_active']*100:.1f}%"],
            ["폐지 -100% 계상", f"{diag['n_delist_charged']}종목 (중복 계상 없음)"],
            ["결과 미관측 보유", f"{n_unresolved}건 · 누적가중 {w_unresolved:.2f} "
                                 f"(0% 로 계상 — 성과를 부풀리는 방향)"],
            ["신호가 선택을 못 한 달", f"{n_noselect}/{len(R)} "
                                       f"(후보 ≤ 최소보유수 → '상위 N%'가 곧 '전부')"],
        ], ["노출·계상 진단", "실측"], title=f"백테스트 노출 진단 · {label}")
        if n_noselect > 0.5 * max(len(R), 1):
            LOG.error(
                f"{n_noselect}/{len(R)}개월에서 후보가 최소보유수 이하라 **신호가 종목 선택에 "
                f"관여하지 못했습니다.**\n"
                f"    이 성과는 '신호로 고른 결과'가 아니라 '거부권·하한선을 통과한 잔여물'입니다.\n"
                f"    R1a(미래주입)가 Δ0 으로 나오는 것도 같은 이유입니다 — 엔진 고장이 아닙니다.")
        if diag["mean_invested_active"] < 0.5 and (inv > 0).any():
            LOG.warn(
                f"보유월 평균 투자비중이 {diag['mean_invested_active']*100:.0f}% 입니다 — "
                f"나머지는 무이자 현금입니다.\n"
                f"    이 상태의 CAGR·연변동성·MDD 는 전부 그 비중만큼 압축된 값이라 "
                f"전략의 성과로 읽으면 안 됩니다(Sharpe 는 비중에 불변, 다만 빈 달 0% 로 "
                f"√(보유월/전체월) 만큼 축소됩니다).\n"
                f"    → 'ret_invested' 계열(투자자본 기준)을 함께 보세요.")
    return {"returns": R, "holdings": pd.DataFrame(holdings_log), "gates": G,
            "label": label, "exposure": diag}


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §8.4  성과 지표
# ═══════════════════════════════════════════════════════════════════════════════════════════
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    r = col(R, "ret").fillna(0).to_numpy(dtype=float)
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
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균수익": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1),
        "평균보유종목수": float(R["n"].mean()) if "n" in R else np.nan,
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """§8.4 — 이 전략은 IR 이 아니라 우측 꼬리에 의존한다.

    ★ 상위 소수를 제외했을 때 성과가 사라지는지 반드시 측정한다. 측정 단위는 '종목'이다:
      기여도 = Σ(비중 × 수익) 을 종목별로 합산한 뒤 상위 k 를 빼고 월수익을 재구성한다.
      (월 단위로 빼면 '좋았던 달을 뺀다'가 되어 전혀 다른 질문이 된다)
    """
    H = bt.get("holdings")
    R = bt.get("returns")
    if H is None or H.empty or R is None or R.empty:
        return {}
    H = H.copy()
    H["contrib"] = pd.to_numeric(H["weight"], errors="coerce") * pd.to_numeric(H["ret"], errors="coerce")
    by_code = H.groupby("code")["contrib"].sum().sort_values(ascending=False)
    n = len(by_code)
    if n == 0:
        return {}
    out = {"기여 상위5종목": ", ".join(f"{c}({v:+.2f})" for c, v in by_code.head(5).items()),
           "보유 종목수(누적)": n}
    base = perf_stats(R)
    out["원본 CAGR"] = base.get("CAGR")
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        excl = set(by_code.index[:k])
        h2 = H[~H["code"].isin(excl)]
        r2 = h2.groupby("month")["contrib"].sum().reindex(R["month"]).fillna(0.0)
        cost = pd.to_numeric(R["cost"], errors="coerce").fillna(0).to_numpy()
        R2 = pd.DataFrame({"month": R["month"], "ret": r2.to_numpy() - cost,
                           "n": R["n"], "turnover": R["turnover"], "cost": R["cost"]})
        s2 = perf_stats(R2)
        out[f"{lab} 제외 종목수"] = k
        out[f"{lab} 제외 CAGR"] = s2.get("CAGR")
        out[f"{lab} 제외 Sharpe"] = s2.get("Sharpe")
    return out


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
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
    return out
