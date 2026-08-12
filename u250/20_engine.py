# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §5 비용 모형 + 백테스트 엔진                                                             ║
# ║                                                                                          ║
# ║  "순수익 없이는 어떤 판정도 하지 않는다."                                                  ║
# ║  그래서 총수익 경로는 B1 하나뿐이고, 나머지 전 산출물은 비용을 통과해야만 나온다.           ║
# ║                                                                                          ║
# ║  스프레드는 종목별 실측을 우선한다 — Corwin-Schultz(2012) 고저가 추정량을 일별 OHLC 로     ║
# ║  계산하고, 추정이 불가한 구간에만 시총분위별 보수 고정값으로 폴백한다.                      ║
# ║  (마이크로캡에서 스프레드를 상수로 두면 소형일수록 비용이 과소계상돼 결론이 뒤집힌다)       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def tax_rate(year: int, market: str) -> float:
    """연도별 증권거래세 실효율 (매도 시). 하드코딩이 아니라 테이블 조회다(§5)."""
    row = SPEC_TAX_TABLE[0]
    for r in SPEC_TAX_TABLE:
        if year >= r[0]:
            row = r
    return row[2] if str(market).upper().startswith("KOSDAQ") else row[1]


def corwin_schultz_spread(daily: pd.DataFrame) -> pd.DataFrame:
    """일별 고저가로 종목별 유효 스프레드(편도, 비율)를 추정한다.

    음수 추정치는 0 이 아니라 결측으로 둔다 — 0 으로 밀면 '비용 없는 종목'이 생기고
    그 종목이 정확히 마이크로캡이라 결론을 오염시킨다.
    """
    if not {"high", "low"} <= set(daily.columns):
        LOG.warn("고가·저가가 없어 Corwin-Schultz 스프레드 실측을 건너뜁니다 → "
                 "전 구간 시총분위 폴백값을 사용합니다(§5 '값과 근거를 로그에 명시').")
        return pd.DataFrame(columns=["code", "date", "spread_cs"])
    d = daily[["code", "date", "high", "low"]].copy()
    d["code"] = d["code"].astype(str)
    d = d[(d["high"] > 0) & (d["low"] > 0)].sort_values(["code", "date"])
    g = d.groupby("code", observed=True)
    h1, l1 = g["high"].shift(-1), g["low"].shift(-1)
    beta = np.log(d["high"] / d["low"]) ** 2 + np.log(h1 / l1) ** 2
    h2 = np.maximum(d["high"], h1)
    l2 = np.minimum(d["low"], l1)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    d["spread_cs"] = np.where(np.isfinite(s) & (s > 0) & (s < 0.25), s, np.nan)
    #   2일 추정치는 잡음이 크다 → 60세션 중앙값으로 눌러 쓴다(리밸 시점 조회용).
    d["spread_cs"] = d.groupby("code", observed=True)["spread_cs"].transform(
        lambda s: s.rolling(60, min_periods=20).median())
    out = d[["code", "date", "spread_cs"]].reset_index(drop=True)
    ok = int(out["spread_cs"].notna().sum())
    LOG.ok(f"Corwin-Schultz 스프레드 실측 {ok:,}셀 "
           f"(중앙값 편도 {100*out['spread_cs'].median():.3f}% ) — "
           f"결측 셀은 시총분위 폴백값을 씁니다.")
    return out


@dataclass
class CostModel:
    """§5 비용 모형. AUM 을 받아 종목별 왕복 비용률을 만든다."""
    spread_map: Optional[pd.DataFrame] = None      # (code, rebal) → 편도 스프레드
    market_map: Optional[pd.Series] = None         # code → KOSPI/KOSDAQ
    cap_quintile: Optional[pd.DataFrame] = None    # (code, rebal) → 1(소)~5(대)
    adv: Optional[pd.DataFrame] = None             # (code, rebal) → 20일 평균거래대금
    fallback_used: int = 0
    measured_used: int = 0

    def one_way(self, rebal: pd.Timestamp, codes: pd.Index, notional: np.ndarray) -> np.ndarray:
        """편도 비용률 (세금 제외). notional = 이 리밸에서 그 종목에 실제로 넣고 빼는 금액."""
        sp = self._spread(rebal, codes)
        adv = self._adv(rebal, codes)
        impact = SPEC_COST["impact_coef"] * np.sqrt(np.maximum(notional, 0.0) / np.maximum(adv, 1.0))
        return (sp / 2.0
                + SPEC_COST["commission_roundtrip"] / 2.0
                + SPEC_COST["slippage_bp"] / 1e4
                + impact)

    def sell_tax(self, rebal: pd.Timestamp, codes: pd.Index) -> np.ndarray:
        mk = (self.market_map.reindex(codes).fillna("KOSDAQ").to_numpy()
              if self.market_map is not None else np.array(["KOSDAQ"] * len(codes)))
        y = int(pd.Timestamp(rebal).year)
        return np.array([tax_rate(y, m) for m in mk])

    def _spread(self, rebal, codes) -> np.ndarray:
        base = np.full(len(codes), np.nan)
        if self.spread_map is not None:
            s = self.spread_map.get(rebal)
            if s is not None:
                base = s.reindex(codes).to_numpy(dtype=float)
        miss = ~np.isfinite(base)
        if miss.any():
            q = np.full(len(codes), 1)
            if self.cap_quintile is not None:
                qq = self.cap_quintile.get(rebal)
                if qq is not None:
                    q = qq.reindex(codes).fillna(1).astype(int).to_numpy()
            fb = np.array([SPEC_COST["spread_fallback_bp"].get(int(x), 90.0) / 1e4 for x in q])
            base = np.where(miss, fb, base)
            self.fallback_used += int(miss.sum())
        self.measured_used += int((~miss).sum())
        return base

    def _adv(self, rebal, codes) -> np.ndarray:
        if self.adv is None:
            return np.full(len(codes), 1e9)
        a = self.adv.get(rebal)
        if a is None:
            return np.full(len(codes), 1e9)
        return a.reindex(codes).fillna(1e7).to_numpy(dtype=float)

    def report(self):
        tot = self.measured_used + self.fallback_used
        if tot:
            LOG.info(f"스프레드 출처 — 실측(Corwin-Schultz) {100*self.measured_used/tot:.1f}% · "
                     f"시총분위 폴백 {100*self.fallback_used/tot:.1f}% "
                     f"(폴백 근거: {SPEC_COST['spread_fallback_basis']})")


@dataclass
class BTResult:
    name: str
    nav: pd.Series                # 순수익 NAV
    nav_gross: pd.Series
    ret: pd.Series                # 리밸 구간 순수익률
    ret_gross: pd.Series
    turnover: pd.Series
    cost: pd.Series
    n_holdings: pd.Series
    weights: Dict[pd.Timestamp, pd.Series] = field(default_factory=dict)

    def stats(self, periods_per_year: float) -> dict:
        r = self.ret.dropna()
        if not len(r):
            return dict(cagr=np.nan, vol=np.nan, mdd=np.nan, sharpe=np.nan,
                        turnover=np.nan, cost=np.nan, n=0)
        yrs = len(r) / periods_per_year
        cagr = (self.nav.iloc[-1]) ** (1 / max(yrs, 1e-9)) - 1 if self.nav.iloc[-1] > 0 else -1.0
        vol = r.std(ddof=1) * np.sqrt(periods_per_year)
        dd = self.nav / self.nav.cummax() - 1
        return dict(cagr=float(cagr), vol=float(vol), mdd=float(dd.min()),
                    sharpe=float(cagr / vol) if vol > 0 else np.nan,
                    turnover=float(self.turnover.mean() * periods_per_year),
                    cost=float(self.cost.sum()), n=int(len(r)),
                    final_nav=float(self.nav.iloc[-1]))

    def yearly(self) -> pd.Series:
        r = self.ret.dropna()
        if not len(r):
            return pd.Series(dtype=float)
        return r.groupby(r.index.year).apply(lambda x: float((1 + x).prod() - 1))


class Engine:
    """동일가중(EW) 리밸런싱 백테스터. 선택 함수만 갈아끼우면 B1~B4·F1~F4 가 전부 나온다."""

    def __init__(self, rebals: pd.DatetimeIndex, fwd: pd.DataFrame, cost: CostModel,
                 delist: Optional[pd.DataFrame] = None):
        self.rebals = rebals
        self.fwd = fwd                 # index=rebal, columns=code, 값=구간 총수익률
        self.cost = cost
        self.delist = delist           # index=rebal, columns=code, True=이 구간에 폐지
        self.ppy = 52.0 if not REBAL_FREQ.upper().startswith("M") else 12.0

    def run(self, select: Callable[[pd.Timestamp], Sequence[str]], name: str,
            aum0: float = 100_000_000, dynamic_aum: bool = False,
            keep_weights: bool = False) -> BTResult:
        nav, nav_g = 1.0, 1.0
        prev_w = pd.Series(dtype=float)
        navs, navs_g, rets, rets_g, tos, costs, ns = [], [], [], [], [], [], []
        wkeep: Dict[pd.Timestamp, pd.Series] = {}
        idx = []
        for t in self.rebals:
            if t not in self.fwd.index:
                continue
            sel = [c for c in select(t) if c]
            if not sel:
                #   빈 포트폴리오 = 현금. 0% 로 기록하되 그 사실이 보이도록 종목수 0 을 남긴다.
                idx.append(t); navs.append(nav); navs_g.append(nav_g)
                rets.append(0.0); rets_g.append(0.0); tos.append(0.0); costs.append(0.0); ns.append(0)
                prev_w = pd.Series(dtype=float)
                continue
            w = pd.Series(1.0 / len(sel), index=pd.Index(sel, name="code"))
            allc = prev_w.index.union(w.index)
            dw = (w.reindex(allc).fillna(0.0) - prev_w.reindex(allc).fillna(0.0))
            aum = (aum0 * nav) if dynamic_aum else aum0
            notional = np.abs(dw.to_numpy()) * aum
            ow = self.cost.one_way(t, allc, notional)
            tax = self.cost.sell_tax(t, allc)
            buy = np.maximum(dw.to_numpy(), 0.0)
            sell = np.maximum(-dw.to_numpy(), 0.0)
            c = float((buy * ow).sum() + (sell * (ow + tax)).sum())

            r = self.fwd.loc[t].reindex(w.index)
            if self.delist is not None and t in self.delist.index:
                dl = self.delist.loc[t].reindex(w.index).fillna(False).astype(bool)
                r = r.where(~dl, -1.0)                 # 정리매매가 없으면 −100% (누락 금지)
            #   수익률이 결측인 종목은 '그 구간 현금'이 아니라 '보유 불가'다.
            #   결측을 0 으로 채우면 폐지·거래정지가 무위험 자산이 된다 → 명시적으로 제외하고
            #   남은 종목으로 비중을 재정규화한다(그 사실은 n_holdings 로 드러난다).
            ok = r.notna()
            rp = float(r[ok].mean()) if ok.any() else 0.0
            nav_g *= (1 + rp)
            nav *= (1 + rp) * (1 - c)
            #   다음 리밸의 시작 비중 = 수익률로 드리프트된 비중
            drift = (w[ok] * (1 + r[ok]))
            prev_w = drift / drift.sum() if drift.sum() > 0 else pd.Series(dtype=float)
            idx.append(t); navs.append(nav); navs_g.append(nav_g)
            rets.append((1 + rp) * (1 - c) - 1); rets_g.append(rp)
            tos.append(float(np.abs(dw).sum() / 2.0)); costs.append(c); ns.append(int(ok.sum()))
            if keep_weights:
                wkeep[t] = w
        I = pd.DatetimeIndex(idx)
        return BTResult(name, pd.Series(navs, index=I), pd.Series(navs_g, index=I),
                        pd.Series(rets, index=I), pd.Series(rets_g, index=I),
                        pd.Series(tos, index=I), pd.Series(costs, index=I),
                        pd.Series(ns, index=I), wkeep)


def build_forward_returns(daily: pd.DataFrame, rebals: pd.DatetimeIndex,
                          sec: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """리밸 구간 수익률 행렬. 체결가 = 신호일 다음 거래일 시가(없으면 종가).

    ★ 폐지 구간은 −100%. 가격이 사라졌다고 수익률을 결측 처리하면 그게 생존자편향이다.
    """
    d = daily.sort_values(["code", "date"]).copy()
    g = d.groupby("code", observed=True)
    d["next_open"] = g["open"].shift(-1) if "open" in d.columns else np.nan
    d["next_date"] = g["date"].shift(-1)
    gap = (d["next_date"] - d["date"]).dt.days
    d["exec_px"] = d["next_open"].where(gap.notna() & (gap <= 10) & (d["next_open"] > 0))
    d["exec_px"] = d["exec_px"].fillna(d["close"])
    snap = d[d["date"].isin(rebals)][["code", "date", "exec_px"]].copy()
    snap["code"] = snap["code"].astype(str)
    M = snap.pivot_table(index="date", columns="code", values="exec_px", aggfunc="last")
    M.columns = M.columns.astype(str)
    M = M.reindex(rebals)
    FWD = M.shift(-1) / M - 1.0

    # 폐지 처리 — 폐지일이 구간 안에 들어오면 그 구간을 −100% 로 못박는다
    DEL = pd.DataFrame(False, index=FWD.index, columns=FWD.columns)
    if sec is not None and "delisting_date" in sec.columns:
        dl = sec.dropna(subset=["delisting_date"]).set_index("code")["delisting_date"]
        dl = dl[dl.index.isin(FWD.columns)]
        starts = FWD.index
        ends = list(FWD.index[1:]) + [FWD.index[-1] + pd.Timedelta(days=400)]
        for c, dt in dl.items():
            j = np.searchsorted(np.array(starts), np.datetime64(dt), side="right") - 1
            if 0 <= j < len(starts) and dt <= ends[j]:
                DEL.iloc[j, DEL.columns.get_loc(c)] = True
    #   마지막 시점은 전방 수익률이 없다. 남겨 두면 '수익 0% 인데 비용은 낸 구간'이 하나
    #   생겨 전 전략의 CAGR 이 똑같이 조금씩 깎인다. 아예 구간에서 뺀다.
    if len(FWD) and FWD.iloc[-1].isna().all():
        FWD, DEL = FWD.iloc[:-1], DEL.iloc[:-1]
    n_del = int(DEL.to_numpy().sum())
    LOG.ok(f"구간 수익률 행렬 {FWD.shape[0]:,}시점 × {FWD.shape[1]:,}종목 · "
           f"폐지로 −100% 처리된 (종목×구간) {n_del:,}건")
    if n_del == 0 and sec is not None and "delisting_date" in sec.columns:
        LOG.warn("폐지 처리 건수가 0입니다 — 폐지일이 패널 구간과 겹치지 않거나 매핑이 어긋난 "
                 "것일 수 있습니다. 생존자편향이 남아 있는지 확인하세요.")
    return FWD, DEL
