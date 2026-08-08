

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-U  PIT 유니버스 (SPEC §5)                                                             ║
# ║                                                                                          ║
# ║  매월말 스냅샷. 이후 어떤 단계에서도 미래 스냅샷을 참조하지 않는다.                          ║
# ║   시장   : KOSPI + KOSDAQ (KONEX 제외)                                                    ║
# ║   제외   : 스팩 · 우선주 · ETF/ETN/리츠 (지주회사 중복상장분은 유지)                        ║
# ║   하한   : 주가 1,000원 · 시총 500억 · 20영업일 평균거래대금 3억                            ║
# ║   포함   : ★ 상장폐지 종목 — 그 시점에 살아 있었으면 반드시 포함한다 (생존편향 제거)         ║
# ║                                                                                          ║
# ║  각 스냅샷은 features/universe/universe_YYYYMM.parquet 로 저장한다.                        ║
# ║  게이트마다 잔존 종목수를 기록해 '어디서 표본이 붕괴하는지'를 표로 출력한다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

UNI_GATES = ["① 상장중(PIT)", "② 시장/증권 종류", "③ 가격 보유", "④ 주가 하한",
             "⑤ 시총 하한", "⑥ 유동성 하한", "⑦ 최종 유니버스"]

# ★ exec_px(익영업일 시가)·fwd_ret(차월 수익률)은 '그 월말에 알 수 없는' 값이다.
#   유니버스 패널에서 쓰이지도 않으면서 universe_YYYYMM.parquet 안에 들어가면,
#   PIT 스냅샷이라는 이름의 파일에 미래 정보가 담긴 채로 남는다 — 장전된 총이다. 아예 빼둔다.
UNIVERSE_COLS = ["code", "month", "market", "close_m", "adv20", "mktcap", "shares",
                 "mcap_approx", "sector", "bm", "in_universe"]


class SACNUniverse:
    """SPEC §5 유니버스. 게이트별 감쇠를 기록하고 월별 스냅샷을 영속화한다."""

    def __init__(self):
        self.attrition: List[dict] = []
        self.panel: Optional[pd.DataFrame] = None
        self.saved_months: List[str] = []
        self.mcap_partial_months: List[tuple] = []   # 커버리지 부족으로 결측을 통과시킨 달
        self.mcap_skipped_months: List[Any] = []     # 시총이 통째로 없어 하한을 못 건 달

    def _mark(self, month, gate: str, n: int):
        self.attrition.append({"month": as_ts(month), "gate": gate, "n": int(n)})

    def build(self, uni: "Universe", months: pd.DatetimeIndex, price_m: pd.DataFrame,
              mcap: pd.DataFrame, flags: pd.DataFrame, sector: pd.DataFrame,
              fund: pd.DataFrame, persist: bool = True) -> pd.DataFrame:
        # 룩업을 미리 만들어 월 루프 안에서 재구성하지 않는다 (120개월 × 2,500종목).
        pm = price_m.copy()
        pm["code"] = pm["code"].astype(str)
        pm["month"] = as_ts_series(pm["month"])
        pm = pm.set_index(["code", "month"])

        mc = mcap.copy() if mcap is not None and len(mcap) else pd.DataFrame(
            columns=["code", "month", "mktcap", "shares", "mktcap_is_approx"])
        if len(mc):
            mc["code"] = mc["code"].astype(str)
            mc["month"] = as_ts_series(mc["month"])
            if "mktcap_is_approx" not in mc.columns:
                mc["mktcap_is_approx"] = False
            mc = mc.drop_duplicates(["code", "month"]).set_index(["code", "month"])

        fd = fund.copy() if fund is not None and len(fund) else pd.DataFrame(
            columns=["code", "month", "bm"])
        if len(fd):
            fd["code"] = fd["code"].astype(str)
            fd["month"] = as_ts_series(fd["month"])
            fd = fd.drop_duplicates(["code", "month"]).set_index(["code", "month"])

        excl = set(flags.loc[flags["excluded"], "code"].astype(str)) if flags is not None and len(flags) else set()
        mkt = (flags.set_index("code")["market"].astype(str).to_dict()
               if flags is not None and len(flags) and "market" in flags.columns else {})
        smap = (sector.set_index("code")["sector"].to_dict()
                if sector is not None and len(sector) else {})

        rows = []
        for m in tqdm(months, desc="PIT 유니버스", disable=not VERBOSE):
            m = as_ts(m)
            codes = [str(c) for c in uni.at(m)]                      # ① 상장중 (폐지종목 포함 판정)
            self._mark(m, UNI_GATES[0], len(codes))

            codes2 = [c for c in codes
                      if c not in excl
                      and str(mkt.get(c, "")).upper() in ("KOSPI", "KOSDAQ", "")]
            self._mark(m, UNI_GATES[1], len(codes2))                 # ② 시장/증권 종류

            idx = pd.MultiIndex.from_product([codes2, [m]], names=["code", "month"])
            g = pd.DataFrame(index=idx)
            for c in ("close", "adv20"):
                g[c] = pm[c].reindex(idx) if c in pm.columns else np.nan
            g["mktcap"] = mc["mktcap"].reindex(idx) if "mktcap" in getattr(mc, "columns", []) else np.nan
            g["mcap_approx"] = (mc["mktcap_is_approx"].reindex(idx).fillna(False).astype(bool)
                                if "mktcap_is_approx" in getattr(mc, "columns", [])
                                else pd.Series(False, index=idx))
            g["shares"] = mc["shares"].reindex(idx) if "shares" in getattr(mc, "columns", []) else np.nan
            g["bm"] = fd["bm"].reindex(idx) if "bm" in getattr(fd, "columns", []) else np.nan
            g = g.reset_index()

            g = g[g["close"].notna() & (g["close"] > 0)]
            self._mark(m, UNI_GATES[2], len(g))                      # ③ 가격 보유

            g = g[g["close"] >= UNI_MIN_PRICE_KRW]
            self._mark(m, UNI_GATES[3], len(g))                      # ④ 주가 하한

            # ⑤ 시총 하한 — 커버리지에 따라 두 갈래로 간다.
            #   · 커버리지가 충분하면 '값이 있고 하한 이상'만 통과시킨다. 결측을 통과시키면
            #     시총 미상 소형주가 그대로 들어와, 하한을 둔 의미가 사라진다(성과 과대 방향).
            #   · 커버리지가 부족하면 하한을 적용하지 않는다. 데이터 부재를 '탈락'으로 처리하면
            #     그 달 유니버스가 0이 되고, 그건 필터가 아니라 버그다.
            #   ★ 근사 시총(mktcap_is_approx)도 하한 판정에 쓴다. 근사라고 통과시키면
            #     소형주가 무조건 들어오고, 근사라고 전부 빼면 실측 소스가 전멸한 실행에서
            #     유니버스가 통째로 비어 버린다 — 둘 다 하한을 둔 목적에 반한다.
            #     근사 오차는 대칭 잡음이고, 하한을 '적용하는' 쪽이 보수적이다.
            #     근사 비중은 시총 출처 감사표와 OPEN_QUESTIONS 에 그대로 남는다.
            cov = float(g["mktcap"].notna().mean()) if len(g) else 0.0
            ap = float(g["mcap_approx"].mean()) if len(g) and "mcap_approx" in g.columns else 0.0
            # ★ 근사 시총이 지배적인 달에는 '값 없으면 탈락' 규칙을 쓰면 안 된다.
            #   근사는 현재 상장주식수를 과거에 곱한 값이라 ⓐ 미래참조이고
            #   ⓑ 상장폐지 종목은 현재 상장목록에 없어 값 자체가 생기지 않는다.
            #   그 상태로 엄격 규칙을 걸면 폐지종목이 전부 탈락해 생존자편향이 되살아난다.
            #   → 근사 지배 구간에서는 하한을 느슨하게(결측 통과) 두고 그 사실을 기록한다.
            if cov >= MCAP_GATE_MIN_COVERAGE and ap < 0.5:
                g = g[g["mktcap"].notna() & (g["mktcap"] >= UNI_MIN_MKTCAP_KRW)]
            elif g["mktcap"].notna().any():
                g = g[g["mktcap"].isna() | (g["mktcap"] >= UNI_MIN_MKTCAP_KRW)]
                self.mcap_partial_months.append((m, cov, ap))
            else:
                self.mcap_skipped_months.append(m)
            self._mark(m, UNI_GATES[4], len(g))

            g = g[g["adv20"].isna() | (g["adv20"] >= UNI_MIN_ADV_KRW)]
            self._mark(m, UNI_GATES[5], len(g))                      # ⑥ 유동성 하한

            g["market"] = g["code"].map(lambda c: mkt.get(c, ""))
            g["sector"] = g["code"].map(lambda c: smap.get(c, "미분류"))
            g = g.rename(columns={"close": "close_m"})
            g["in_universe"] = True
            self._mark(m, UNI_GATES[6], len(g))                      # ⑦ 최종
            rows.append(g)

            if persist and len(g):
                self._persist_snapshot(m, g)

        P = (pd.concat(rows, ignore_index=True) if rows
             else pd.DataFrame(columns=UNIVERSE_COLS))
        P = P.reindex(columns=[c for c in UNIVERSE_COLS if c in P.columns or c in
                               ("code", "month")] + [c for c in P.columns if c not in UNIVERSE_COLS])
        P["code"] = P["code"].astype(str)
        P["month"] = as_ts_series(P["month"])
        # ★ 시총 하한이 실제로 몇 달에 걸렸는지 밝힌다. "하한 500억을 적용했다"는 말이
        #   절반의 달에만 참이면, 그건 적용한 게 아니라 적용했다고 믿는 것이다.
        n_ok = len(months) - len(self.mcap_partial_months) - len(self.mcap_skipped_months)
        if self.mcap_partial_months or self.mcap_skipped_months:
            LOG.warn(
                f"§5 시총 하한 적용 실태 — 정상 적용 {n_ok}개월 / "
                f"커버리지 부족(결측 통과) {len(self.mcap_partial_months)}개월 / "
                f"시총 전무(하한 미적용) {len(self.mcap_skipped_months)}개월. "
                f"미적용 구간에는 시총 미상 소형주가 포함되어 있으며, 이는 성과를 "
                f"과대평가하는 방향입니다. 결과 해석에 반드시 반영하세요. "
                f"(근사 시총이 지배적인 달은 폐지종목이 통째로 탈락하는 생존자편향을 피하려고 "
                f"일부러 하한을 느슨하게 둡니다 — 둘 중 생존자편향이 더 큰 왜곡입니다)")
            open_question(
                "MCAP_GATE_PARTIAL", "§5 시총 하한이 전 구간에 걸리지 않음",
                f"시총 데이터 커버리지가 {MCAP_GATE_MIN_COVERAGE:.0%} 미만인 달이 "
                f"{len(self.mcap_partial_months) + len(self.mcap_skipped_months)}개월 있어 "
                f"해당 월에는 500억 하한을 온전히 적용하지 못했습니다.",
                "데이터 부재를 '탈락'으로 처리하면 그 달 유니버스가 0이 되어 백테스트가 "
                "끊기므로, 하한 미적용 + 명시 보고를 택했습니다(가장 보수적인 '전부 제외'는 "
                "표본을 없애 검정 자체를 불가능하게 만듭니다).",
                "해당 월 성과는 상향 편의를 가질 수 있습니다.")
        else:
            LOG.ok(f"§5 시총 하한을 전 {len(months)}개월에 온전히 적용했습니다.")
        dup = int(P.duplicated(["code", "month"]).sum()) if len(P) else 0
        if dup:
            raise RuntimeError(f"유니버스 패널에 (code, month) 중복 {dup:,}행이 있습니다. "
                               f"하류 merge 가 행을 복제해 같은 종목이 두 번 편입됩니다.")
        self.panel = P
        PIPE.io("OUT", "MEM", "sacn_universe_panel", P)
        return P

    def _persist_snapshot(self, m: pd.Timestamp, g: pd.DataFrame):
        try:
            d = os.path.join(VAULT.ns["private"], "features", "universe")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"universe_{m:%Y%m}.parquet")
            if not os.path.exists(p):          # 이미 있으면 덮어쓰지 않는다
                atomic_write_parquet(g, p)
                self.saved_months.append(f"{m:%Y%m}")
        except Exception as e:                 # noqa
            LOG.debug(f"유니버스 스냅샷 저장 실패({type(e).__name__}) {m:%Y-%m}")

    # ── 감사 ─────────────────────────────────────────────────────────────────────────
    def report(self):
        if not self.attrition:
            LOG.warn("유니버스 감쇠 기록이 없습니다.")
            return
        A = pd.DataFrame(self.attrition)
        piv = A.groupby("gate")["n"].agg(["mean", "min", "max"]).reindex(UNI_GATES).dropna(how="all")
        rows, prev = [], None
        for gate, r in piv.iterrows():
            keep = "—" if prev in (None, 0) else f"{100 * r['mean'] / prev:.1f}%"
            rows.append([gate, f"{r['mean']:.0f}", f"{int(r['min'])}", f"{int(r['max'])}", keep])
            prev = r["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§5) — 어느 게이트에서 표본이 붕괴하는지")
        fin = piv.loc[UNI_GATES[6], "mean"] if UNI_GATES[6] in piv.index else 0
        need = N_QUANTILES * PORT_MIN_NAMES
        if fin < need:
            LOG.error(f"최종 유니버스 월평균 {fin:.0f}종목 → Q{N_QUANTILES} 분위당 "
                      f"{fin/N_QUANTILES:.0f}종목으로 보유하한 {PORT_MIN_NAMES}종목에 미달합니다. "
                      f"이대로면 대부분의 리밸런싱이 현금 처리되어 성과가 0 으로 나옵니다 "
                      f"(전략 실패가 아니라 표본 부족). 유니버스가 최소 {need}종목은 되어야 합니다.")
            PIPE.note("WARN: 유니버스 표본 부족 — 분위 백테스트 실행 불가 수준")
        elif fin < 200:
            LOG.warn(f"최종 유니버스 월평균 {fin:.0f}종목 — 분위당 {fin/N_QUANTILES:.0f}종목뿐입니다. "
                     f"통계적 판단력이 약합니다.")
        if self.saved_months:
            LOG.ok(f"월별 유니버스 스냅샷 {len(self.saved_months)}개 저장 "
                   f"→ {GDRIVE_PRIVATE_NS}/features/universe/universe_YYYYMM.parquet")

    def delisting_returns(self, uni: "Universe", months: pd.DatetimeIndex,
                          px_daily: pd.DataFrame, default_ret: float = DELIST_DEFAULT_RET
                          ) -> pd.DataFrame:
        """SPEC §0.3 — 폐지 종목의 최종 수익률.

        -100% 가 아니라 '정리매매 최종가' 기준이다. 일별 가격의 마지막 관측이 정리매매
        최종가에 해당하므로, 폐지 직전월 종가 → 최종 관측가 수익률을 쓴다.
        최종가를 확인할 수 없으면 default_ret(-70%)를 쓰고, 그 가정의 민감도를 별도 보고한다.
        """
        dmap = uni.delisting_map() if hasattr(uni, "delisting_map") else {}
        if not dmap:
            return pd.DataFrame(columns=["code", "month", "delist_date", "delist_ret", "source"])
        px = px_daily[["code", "date", "close"]].copy()
        px["code"] = px["code"].astype(str)
        px["date"] = as_ts_series(px["date"])
        px = px.dropna(subset=["close"]).sort_values(["code", "date"])
        last = px.groupby("code", observed=True).tail(1).set_index("code")
        # 종목별로 한 번만 그룹핑한다. 폐지 종목 1,500개 × 600만행 전수 스캔은
        # 스테이지 예산(900초)을 그대로 잡아먹는다.
        by_code = {c: g for c, g in px.groupby("code", observed=True)}
        rows = []
        mset = set(as_ts(m) for m in months)
        for code, dd in dmap.items():
            d = as_ts(dd)
            if d is None:
                continue
            m_prev = (d - pd.offsets.MonthEnd(1)) + pd.offsets.MonthEnd(0)
            if m_prev not in mset:
                continue
            gsub = by_code.get(str(code))
            base = gsub[gsub["date"] <= m_prev]["close"] if gsub is not None else None
            p0 = float(base.iloc[-1]) if base is not None and len(base) else np.nan
            p1 = last["close"].get(str(code), np.nan)
            t1 = last["date"].get(str(code), pd.NaT)
            if np.isfinite(p0) and np.isfinite(p1) and p0 > 0 and pd.notna(t1) and t1 > m_prev:
                r, src = float(p1 / p0 - 1.0), "정리매매 최종가"
            else:
                r, src = float(default_ret), "확인불가 → 보수적 기본값"
            rows.append({"code": str(code), "month": m_prev, "delist_date": d,
                         "delist_ret": max(-1.0, min(r, 5.0)), "source": src})
        out = pd.DataFrame(rows)
        if len(out):
            n_ok = int((out["source"] == "정리매매 최종가").sum())
            LOG.table([["정리매매 최종가 확인", f"{n_ok:,}"],
                       ["확인불가 → 기본값 적용", f"{len(out) - n_ok:,}"],
                       ["기본값", f"{default_ret:.0%}"],
                       ["평균 폐지수익률", f"{out['delist_ret'].mean():.1%}"]],
                      ["항목", "값"], ["l", "r"],
                      title="상장폐지 처리 (§0.3) — -100% 일괄 적용 금지")
            if len(out) - n_ok:
                open_question("OQ-02", "상장폐지 최종가",
                              f"{len(out) - n_ok}건은 정리매매 최종가를 확인할 수 없다.",
                              f"보수적 기본값 {default_ret:.0%} 적용.",
                              "delisting_sensitivity.md 에 -100%/-70%/-50%/-30% 민감도 병기.")
        return out


def smallcap_subset(P: pd.DataFrame, n: int = SMALLCAP_ARM_N) -> pd.DataFrame:
    """비교 아암 — 매월 시가총액 하위 n종목으로 압축한 유니버스.

    H3('소형주에서 더 강하다')의 조건부 예측과 직접 맞물리는 비교군이다.
    시총 결측 종목은 순위를 매길 수 없으므로 제외한다(포함하면 순위가 의미를 잃는다).
    """
    if P is None or not len(P):
        return P
    # 신호 패널의 시점 축은 'date'(리밸런싱일)다. 주간 리밸런싱에서는 한 달에 여러 시점이
    # 있으므로 month 로 묶으면 순위가 달 단위로 뭉개진다 — 반드시 시점별로 매긴다.
    key = "date" if "date" in P.columns else "month"
    if "mktcap" not in P.columns:
        LOG.warn("시가총액 컬럼이 없어 소형주 비교아암을 만들 수 없습니다 (전체 아암만 보고).")
        return P.iloc[0:0]
    d = P[P["mktcap"].notna()].copy()
    if not len(d):
        LOG.warn("시가총액이 전부 결측이라 소형주 비교아암을 만들 수 없습니다.")
        return d
    d["_rk"] = d.groupby(key)["mktcap"].rank(method="first", ascending=True)
    out = d[d["_rk"] <= n].drop(columns=["_rk"]).reset_index(drop=True)
    LOG.ok(f"소형주 비교아암: 시점평균 {out.groupby(key).size().mean():.0f}종목 "
           f"(시총 하위 {n:,} 기준) · 전체 아암 시점평균 "
           f"{P.groupby(key).size().mean():.0f}종목")
    return out
