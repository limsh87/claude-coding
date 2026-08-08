
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-A  이벤트 드리븐 백테스트 엔진  (SPEC §7 · §8)                                        ║
# ║                                                                                          ║
# ║  구조: 캘린더타임 포트폴리오 (calendar-time portfolio).                                    ║
# ║    매 영업일 신규 이벤트를 평가해 조건 충족 시 편입, 보유기간 만료 시 청산.                ║
# ║    ★ 이 구조를 쓰는 이유는 단지 명세 때문이 아니다. 이벤트 스터디에서 보유구간이           ║
# ║      겹치면(overlapping) 이벤트별 수익률이 서로 상관되어 t 통계량이 부풀려진다.            ║
# ║      캘린더타임 포트폴리오는 그 상관을 포트폴리오 수익률 하나로 흡수해버리므로              ║
# ║      횡단면 상관에 의한 t 과대추정이 구조적으로 사라진다.                                  ║
# ║                                                                                          ║
# ║  진입 시점 (★ SPEC §0.1 — 위반하면 산출물 전체 무효)                                       ║
# ║    거래원/수급 데이터는 장 마감 후 공개된다. 따라서                                        ║
# ║      k=0   윈도 → 진입 d+1 종가                                                            ║
# ║      k=0..2 윈도 → 진입 d+3 종가                                                           ║
# ║    코드에서 이 오프셋은 (k+1) 로 강제되며, 계약검정 K3 가 이를 실행 시 재확인한다.          ║
# ║                                                                                          ║
# ║  보유는 buy-and-hold 다(진입 시 비중 고정, 이후 가치 드리프트).                             ║
# ║    매일 동일가중으로 되맞추면 실제로는 하지 않는 매매의 회전율·비용이 발생하고,             ║
# ║    그 비용이 성과를 왜곡한다.                                                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
#   출처: 기획재정부 증권거래세법 시행령 개정 이력
#   https://www.moef.go.kr  /  https://law.go.kr/법령/증권거래세법시행령
#   ★ 단일 세율 사용 금지 (SPEC §7.1). 2016→2026 사이에만 5회 인하되었다.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.00300, "KOSDAQ": 0.00300, "OTHER": 0.00300}),
    ("2019-06-03", {"KOSPI": 0.00250, "KOSDAQ": 0.00250, "OTHER": 0.00250}),
    ("2021-01-01", {"KOSPI": 0.00230, "KOSDAQ": 0.00230, "OTHER": 0.00230}),
    ("2023-01-01", {"KOSPI": 0.00200, "KOSDAQ": 0.00200, "OTHER": 0.00200}),
    ("2024-01-01", {"KOSPI": 0.00180, "KOSDAQ": 0.00180, "OTHER": 0.00180}),
    ("2025-01-01", {"KOSPI": 0.00150, "KOSDAQ": 0.00150, "OTHER": 0.00150}),
]
_TAX_DATES = [as_ts(d) for d, _ in TAX_SCHEDULE]


def sell_tax_rate(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in zip(_TAX_DATES, [r for _, r in TAX_SCHEDULE]):
        if t >= d:
            rate = r
    m = str(market or "").upper()
    if "KOSDAQ" in m or "코스닥" in m:
        return rate["KOSDAQ"]
    if "KOSPI" in m or "유가" in m or "코스피" in m:
        return rate["KOSPI"]
    return rate["OTHER"]


@dataclass
class BTConfig:
    k: int                       # 플로우 윈도 (0 또는 2)
    hold: int                    # 보유 영업일 (10/20/60)
    version: str                 # "raw" | "resid"
    cost_mult: float = 1.0       # 0 / 1 / 2  (SPEC §7.1 비용 3종)
    rf_annual: float = 0.0
    label: str = ""

    @property
    def entry_offset(self) -> int:
        return self.k + 1        # ★ 장 마감 후 공개 → 최소 d+1 (SPEC §0.1)

    def name(self) -> str:
        return self.label or (f"k={self.k}·hold={self.hold}d·{self.version}"
                              f"{'' if self.cost_mult == 1 else f'·비용x{self.cost_mult:g}'}")


def _price_matrix(px: pd.DataFrame, cal: pd.DatetimeIndex) -> Tuple[np.ndarray, Dict[str, int]]:
    """close 행렬 [n_code, n_day]. 결측은 직전값 전진충전(거래정지 구간의 평가가격)."""
    p = px[["code", "date", "close"]].dropna()
    p = p[p["date"].isin(cal)]
    piv = p.pivot_table(index="code", columns="date", values="close", aggfunc="last")
    piv = piv.reindex(columns=cal)
    piv = piv.ffill(axis=1)
    return piv.to_numpy(float), {c: i for i, c in enumerate(piv.index)}


def run_event_backtest(S: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                       uni: "DailyUniverse", cfg: BTConfig,
                       sec: Optional[pd.DataFrame] = None,
                       member_filter: Optional[np.ndarray] = None) -> dict:
    """이벤트 드리븐 백테스트. 반환: 일별수익률 / 보유내역 / 체결로그 / 요약통계."""
    sig_col = "sig_resid" if cfg.version == "resid" else "sig_raw"
    empty = {"daily": pd.DataFrame(columns=["date", "ret", "n", "cash_w", "cost"]),
             "trades": pd.DataFrame(), "cfg": cfg, "stats": {}}
    if S is None or len(S) == 0 or sig_col not in S.columns or not len(cal):
        return empty

    d = S.copy()
    d["date"] = as_ts_series(d["date"])
    d = d[d[sig_col].notna()]
    if member_filter is not None:
        d = d[member_filter[:len(d)]] if len(member_filter) == len(S) else d
    if not len(d):
        return empty

    # ── PIT 상위 30% 컷 (전체 표본 분위를 쓰면 그 자체가 미래참조) ────────────────────────
    cut = pit_quantile_cut(d, sig_col, 1.0 - PORT_LONG_PCT)
    d = d.assign(_cut=cut.to_numpy())
    sel = d[d["_cut"].notna() & (d[sig_col] >= d["_cut"])].copy()
    if not len(sel):
        LOG.warn(f"[{cfg.name()}] 편입 이벤트가 0건입니다 (PIT 컷 산정에 필요한 과거 이벤트 부족).")
        return empty

    close, cidx = _price_matrix(px, cal)
    n_day = len(cal)
    day_pos = {d_: i for i, d_ in enumerate(cal)}

    # 시장구분 / 사이즈 버킷 (비용 산정용)
    mkt = {}
    if sec is not None and len(sec):
        mkt = dict(zip(sec["code"], sec.get("market", pd.Series("", index=sec.index))))
    size_of = dict(zip(zip(sel["code"], sel["date"]), sel.get("size_bucket", "중형")))

    # ── 이벤트를 진입일 인덱스로 변환 ─────────────────────────────────────────────────────
    ent_i, exi_i, rows = [], [], []
    off = cfg.entry_offset
    for r in sel.itertuples(index=False):
        di = day_pos.get(pd.Timestamp(r.date))
        if di is None:
            continue
        e = di + off
        x = e + cfg.hold
        if e >= n_day:
            continue                       # 진입일이 데이터 끝을 넘어감 → 편입 불가
        ci = cidx.get(r.code)
        if ci is None:
            continue
        rows.append((e, min(x, n_day - 1), ci, r.code, float(getattr(r, sig_col)),
                     getattr(r, "broker", ""), getattr(r, "broker_tier", ""),
                     getattr(r, "size_bucket", "중형"), pd.Timestamp(r.date)))
    if not rows:
        return empty
    rows.sort(key=lambda z: (z[0], -z[4]))

    by_entry: Dict[int, List[tuple]] = defaultdict(list)
    for z in rows:
        by_entry[z[0]].append(z)

    # ── 시뮬레이션 ────────────────────────────────────────────────────────────────────────
    nav = 1.0
    cash = 1.0
    pos: List[dict] = []                   # {ci, code, val, exit_i, entry_px, ...}
    rf_daily = (1.0 + cfg.rf_annual) ** (1 / 252.0) - 1.0
    daily = np.zeros(n_day)
    n_hold = np.zeros(n_day, dtype=int)
    cash_w = np.zeros(n_day)
    cost_d = np.zeros(n_day)
    trades: List[dict] = []
    skipped_noprice = 0

    def _slip(bucket: str) -> float:
        return SLIPPAGE_BPS_BY_SIZE.get(str(bucket), 20.0) * 1e-4 * cfg.cost_mult

    def _comm() -> float:
        return COMMISSION_BPS * 1e-4 * cfg.cost_mult

    for t in range(n_day):
        prev_nav = nav
        # ① 보유 포지션 평가 (전일 종가 → 당일 종가)
        if t > 0 and pos:
            for p in pos:
                c0, c1 = close[p["ci"], t - 1], close[p["ci"], t]
                if np.isfinite(c0) and np.isfinite(c1) and c0 > 0:
                    p["val"] *= (c1 / c0)
                elif not np.isfinite(c1):
                    # 가격이 사라짐 = 상장폐지/거래정지 후 소멸. 보수적으로 헤어컷.
                    p["val"] *= (1.0 + DELIST_HAIRCUT)
                    p["exit_i"] = t
                    p["forced"] = True
        cash *= (1.0 + rf_daily)

        # ② 만기·강제 청산
        still: List[dict] = []
        for p in pos:
            if p["exit_i"] <= t:
                fee = _comm() + _slip(p["bucket"]) + sell_tax_rate(cal[t], p["market"]) * cfg.cost_mult
                proceeds = p["val"] * (1.0 - fee)
                cost_d[t] += p["val"] * fee
                cash += proceeds
                trades.append({"code": p["code"], "broker": p["broker"],
                               "broker_tier": p["tier"], "event_date": p["ev"],
                               "entry_date": cal[p["entry_i"]], "exit_date": cal[t],
                               "hold_days": t - p["entry_i"], "signal": p["sig"],
                               "gross_mult": p["val"] / p["cost0"],
                               "pnl": proceeds - p["cost0"],
                               "size_bucket": p["bucket"],
                               "forced": bool(p.get("forced", False))})
            else:
                still.append(p)
        pos = still

        nav = cash + sum(p["val"] for p in pos)

        # ③ 신규 편입 (신호 강도 순 · 동시보유 상한)
        cand = by_entry.get(t, [])
        if cand:
            room = PORT_MAX_NAMES - len(pos)
            held_codes = {p["code"] for p in pos}
            for (e, x, ci, code, sig, brk, tier, bucket, evd) in cand:
                if room <= 0:
                    break
                if code in held_codes:
                    continue               # 같은 종목 중복 편입 금지(종목 단위 상한 5%)
                if not np.isfinite(close[ci, t]) or close[ci, t] <= 0:
                    skipped_noprice += 1
                    continue
                w = min(POS_MAX_WEIGHT, 1.0 / max(PORT_MAX_NAMES, 1))
                alloc = nav * w
                if alloc > cash:
                    alloc = max(0.0, cash * 0.98)
                if alloc <= 1e-9:
                    break
                fee = _comm() + _slip(bucket)
                cost_d[t] += alloc * fee
                cash -= alloc
                pos.append({"ci": ci, "code": code, "val": alloc * (1.0 - fee),
                            "cost0": alloc, "exit_i": x, "entry_i": t, "sig": sig,
                            "broker": brk, "tier": tier, "bucket": bucket, "ev": evd,
                            "market": mkt.get(code, "")})
                held_codes.add(code)
                room -= 1

        nav = cash + sum(p["val"] for p in pos)
        daily[t] = (nav / prev_nav - 1.0) if prev_nav > 0 else 0.0
        n_hold[t] = len(pos)
        cash_w[t] = cash / nav if nav > 0 else 1.0

    R = pd.DataFrame({"date": cal, "ret": daily, "n": n_hold,
                      "cash_w": cash_w, "cost": cost_d})
    T = pd.DataFrame(trades)
    if skipped_noprice:
        LOG.debug(f"[{cfg.name()}] 진입일 가격 미관측으로 {skipped_noprice:,}건 편입 불가")
    out = {"daily": R, "trades": T, "cfg": cfg,
           "stats": perf_stats_daily(R, T, cfg)}
    return out


def perf_stats_daily(R: pd.DataFrame, T: pd.DataFrame, cfg: "BTConfig") -> dict:
    r = R["ret"].fillna(0).to_numpy(float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / 252.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(252) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(252) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min())
    uw = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        uw = max(uw, cur)
    mu, tstat = hac_tstat(r)
    trades_n = len(T)
    win = float((T["pnl"] > 0).mean()) if trades_n else np.nan
    avg_hold = float(T["hold_days"].mean()) if trades_n else np.nan
    # 회전율: 연간 총 매수금액 / 평균 NAV ≈ (거래수 × 평균비중) / 연수
    turn = (trades_n * min(POS_MAX_WEIGHT, 1.0 / PORT_MAX_NAMES) / years) if years > 0 else np.nan
    return {
        "구성": cfg.name(), "거래일": n,
        "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr / vol) if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr / dvol) if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd < 0 else np.nan,
        "누적수익": float(eq[-1] - 1.0),
        "t통계량(NW)": tstat, "일평균": float(r.mean()),
        "최장언더워터(일)": int(uw),
        "이벤트체결수": trades_n, "승률": win, "평균보유일": avg_hold,
        "연회전율": turn, "평균보유종목": float(R["n"].mean()),
        "평균현금비중": float(R["cash_w"].mean()),
        "총비용": float(R["cost"].sum()),
    }


def yearly_returns(R: pd.DataFrame) -> pd.Series:
    if R is None or len(R) == 0:
        return pd.Series(dtype=float)
    d = R.set_index("date")["ret"]
    return d.groupby(d.index.year, observed=True).apply(lambda s: float(np.prod(1 + s.to_numpy()) - 1))


# ══════════════════════════════════════════════════════════════════════════════════════════
#  벤치마크  (SPEC §8: KOSPI / KOSDAQ / 동일가중 유니버스 / ★나이브 = 매수성 리포트 무차별 매수)
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_benchmarks(px: pd.DataFrame, cal: pd.DatetimeIndex, S: pd.DataFrame,
                     uni: "DailyUniverse", sec: pd.DataFrame,
                     cfg: "BTConfig") -> Dict[str, pd.Series]:
    """★ 이 전략의 진짜 비교 대상은 지수가 아니라 '매수성 리포트를 전부 사는' 나이브 전략이다.
    지수를 이겼다는 말은 의미가 없다 — 리포트를 무차별로 사도 이길 수 있기 때문이다."""
    out: Dict[str, pd.Series] = {}

    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        s = _index_series(sym, cal)
        if s is not None:
            out[name] = s

    # 동일가중 유니버스 (그날 PIT 유니버스 전체의 동일가중 일별수익)
    close, cidx = _price_matrix(px, cal)
    with np.errstate(all="ignore"):
        rets = np.diff(close, axis=1) / close[:, :-1]
    ew = np.nanmean(np.where(np.isfinite(rets), rets, np.nan), axis=0)
    ew = np.concatenate([[0.0], np.where(np.isfinite(ew), ew, 0.0)])
    out["동일가중유니버스"] = pd.Series(ew, index=cal)

    # 나이브: 매수성 리포트 전체를 같은 규칙(진입시점·보유기간·비용)으로 무차별 매수
    if S is not None and len(S):
        naive_cfg = BTConfig(k=cfg.k, hold=cfg.hold, version=cfg.version,
                             cost_mult=cfg.cost_mult, rf_annual=cfg.rf_annual,
                             label="나이브(리포트무차별)")
        Sn = S.copy()
        Sn["sig_raw"] = 1.0        # 전건 편입 (신호 무시)
        Sn["sig_resid"] = 1.0
        bt = run_event_backtest(Sn, px, cal, uni, naive_cfg, sec=sec)
        if len(bt["daily"]):
            out["나이브(리포트무차별매수)"] = bt["daily"].set_index("date")["ret"]
            out["_naive_bt"] = bt
    return out


def _index_series(sym: str, cal: pd.DatetimeIndex) -> Optional[pd.Series]:
    if fdr is None:
        return None
    try:
        d = fdr.DataReader(sym, cal[0] - pd.Timedelta(days=10), cal[-1])
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "close" not in d.columns:
        return None
    s = pd.Series(pd.to_numeric(d["close"], errors="coerce").to_numpy(),
                  index=as_ts_series(d[d.columns[0]]))
    s = s[~s.index.duplicated(keep="last")].reindex(cal).ffill()
    return s.pct_change().fillna(0.0)
