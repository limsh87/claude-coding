

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-H  PIT 패널 조립 · U-MID 유니버스(C13) · 셀                                            ║
# ║                                                                                          ║
# ║  §4.2  C1 은 '접근 방식'이 아니라 '출력'에서 검증한다.                                     ║
# ║        pit.get() 루프(1,150만 호출 = 3.2시간) 대신 merge_asof 단일 패스(10초).             ║
# ║        그리고 전 행에 대해 knowledge_date <= asof 를 assert 한다 —                        ║
# ║        전수 검사이므로 게이트웨이 방식보다 오히려 더 강하다.                                ║
# ║                                                                                          ║
# ║  §5    C13 유니버스는 Point-In-Time.                                                      ║
# ║        (a) 시총·유동성 랭크는 매 시점 t 의 당시 값으로 재산출                               ║
# ║        (b) 졸업(graduate out)은 성공 신호다                                                ║
# ║        (c) 보유 중 밴드 이탈은 청산 사유가 아니다                                          ║
# ║        (d) 밴드는 **진입 필터 전용**이다                                                   ║
# ║        → 그래서 패널은 밴드 밖 종목도 계속 들고 간다. u_mid 는 컬럼(플래그)이지             ║
# ║          행 필터가 아니다. 행을 지우면 (c) 를 코드로 만족시킬 방법이 없어진다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_pit_panel(grid: pd.DataFrame, sources: Dict[str, pd.DataFrame],
                    by: str = "code", left_time: str = "month") -> pd.DataFrame:
    """§4.2 — merge_asof 단일 패스. grid: (month, code) 격자.

    각 source 는 knowledge_date 컬럼을 보유해야 한다(pit_frame 통과분).
    direction='backward' 는 knowledge_date <= month 인 마지막 행만 붙이므로 C1 과 동의어다.
    """
    out = grid.copy()
    out["_ord"] = np.arange(len(out))
    # ★ pandas 2.x 는 소스에 따라 datetime64[s]/[us]/[ns] 를 섞어 만든다. merge_asof 는
    #   해상도가 다르면 MergeError 로 죽고(운 좋은 경우), 우리 코드는 그걸 잡아
    #   "결합 건너뜀"으로 넘어가 **그 소스 전체가 조용히 사라진다**(운 나쁜 경우).
    #   양쪽을 [ns] 로 못박아 두 시나리오를 모두 없앤다.
    out[left_time] = as_ts_series(out[left_time]).astype("datetime64[ns]")
    for name, src in sources.items():
        if src is None or len(src) == 0:
            LOG.debug(f"PIT 결합 건너뜀(빈 소스): {name}")
            continue
        if "knowledge_date" not in src.columns or by not in src.columns:
            LOG.warn(f"PIT 결합 건너뜀: '{name}' 에 knowledge_date 또는 '{by}' 가 없습니다.")
            continue
        R = src.copy()
        R["knowledge_date"] = as_ts_series(R["knowledge_date"]).astype("datetime64[ns]")
        R = R.dropna(subset=["knowledge_date", by])
        # ★ by 키 dtype 이 다르면(category vs object) merge_asof 가 조용히 0건 매칭하거나 터진다.
        R[by] = R[by].astype(str)
        drop = [c for c in ("event_date", "_src", "_ord") if c in R.columns]
        R = R.drop(columns=drop).sort_values("knowledge_date", kind="stable")
        R = R.rename(columns={c: c for c in R.columns})
        R[f"knowledge_date_{name}"] = R["knowledge_date"]

        L = out.copy()
        L[by] = L[by].astype(str)
        # ★★ 결합키·시각이 결측인 행을 '떨어뜨리면' 안 된다. 그게 곧 생존자편향 재유입이다.
        mask = L[left_time].notna() & L[by].notna()
        Lm = L[mask].sort_values(left_time, kind="stable")
        if Lm.empty:
            continue
        try:
            M = pd.merge_asof(Lm, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", f"__{name}"))
        except Exception as e:                                   # noqa
            # 조용히 넘어가면 그 소스의 컬럼이 통째로 없어지고, 하류는 그걸 '결측 데이터'로
            # 보고해 운영자를 API 키 쪽으로 오도한다. 원장에 ERR 로 남기고 크게 경고한다.
            LOG.error(f"merge_asof 실패({type(e).__name__}: {e}) — '{name}' 소스가 패널에 "
                      f"결합되지 않았습니다. 이 소스를 쓰는 센서는 전부 결측이 됩니다. "
                      f"대개 by 키 dtype 불일치이거나 시간 컬럼 해상도(datetime64[s] vs [ns]) "
                      f"불일치입니다.")
            PIPE.io("IN", "MEM", f"asof:{name}", None, ok=False, note=f"{type(e).__name__}")
            continue
        new_cols = [c for c in M.columns if c not in out.columns]
        if not new_cols:
            continue
        out = (out.set_index("_ord")
                  .join(M.set_index("_ord")[new_cols], how="left")
                  .reset_index())
        PIPE.io("IN", "MEM", f"asof:{name}", M, source=f"merge_asof backward on {left_time}")
    return out.drop(columns=["_ord"])


def assert_c1(panel: pd.DataFrame, strict: bool = True) -> List[str]:
    """§4.2 — C1 계약을 출력에서 전수 검증한다. 위반이 1행이라도 있으면 미래누수다."""
    bad = []
    asof = as_ts_series(panel["month"])
    for c in [c for c in panel.columns if c.startswith("knowledge_date_")]:
        kd = as_ts_series(panel[c])
        v = kd.notna() & (kd > asof)
        if v.any():
            bad.append(f"{c}: {int(v.sum()):,}행 (최대 +{int((kd[v]-asof[v]).dt.days.max())}일)")
    if bad:
        msg = ("[C1 위반] 아래 소스에서 knowledge_date > asof 인 행이 발견되었습니다 — "
               "이것은 미래누수입니다:\n  " + "\n  ".join(bad))
        if strict:
            raise KillCriteria(msg)
        LOG.error(msg)
    else:
        n = len([c for c in panel.columns if c.startswith("knowledge_date_")])
        LOG.ok(f"C1 전수 검증 통과 — {len(panel):,}행 × {n}개 소스 전부 "
               f"knowledge_date <= asof (merge_asof 단일 패스, 예외 경로 없음)")
    return bad


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §5  U-MID 유니버스 (C13)
# ═══════════════════════════════════════════════════════════════════════════════════════════
class UniverseV3:
    """PIT 유니버스. 밴드는 진입 필터일 뿐이므로 패널 행을 지우지 않는다."""

    def __init__(self, panel: pd.DataFrame, sec: pd.DataFrame, mode: str = UNIVERSE_MODE):
        self.sec = sec
        self.mode_requested = mode
        self.mode = "rank" if mode in ("rank", "auto") else "pct"
        self.attrition = pd.DataFrame()
        self.panel_cols = ["u_mid", "u_micro", "mcap_rank", "mcap_pct", "adv20", "days_listed"]
        self._delist = {}
        if "delisting_date" in sec.columns:
            dd = as_ts_series(sec["delisting_date"])
            self._delist = {c: d for c, d in zip(sec["code"], dd) if pd.notna(d)}

    # ── 벡터화 빌더 (§5.3 — groupby.apply 금지) ──────────────────────────────────────────
    def annotate(self, P: pd.DataFrame, mode: Optional[str] = None) -> pd.DataFrame:
        mode = mode or self.mode
        p = P.copy()
        p["mcap"] = col(p, "mcap")
        p.loc[~(p["mcap"] > 0), "mcap"] = np.nan
        # ★ 랭크는 '그 달에 실제로 상장돼 있던' 종목만으로 매겨야 한다. 폐지 후 행이나
        #   미상장 행이 모집단에 섞이면 251~1400 밴드의 의미가 달마다 달라진다.
        live = p["listed"].astype(bool) if "listed" in p.columns else pd.Series(True, index=p.index)
        mc = p["mcap"].where(live)
        g = mc.groupby(p["month"], observed=True)
        p["mcap_rank"] = g.rank(ascending=False, method="first")
        p["mcap_pct"] = g.rank(ascending=False, pct=True, method="average")
        p["n_ranked"] = g.transform("count")

        adtv = col(p, "adv20")
        seasoned = col(p, "days_listed") >= UNIVERSE_SEASON_DAYS
        liq = adtv >= UNIVERSE_MIN_ADTV
        if mode == "pct":
            band = p["mcap_pct"].between(UNIVERSE_PCT_LO, UNIVERSE_PCT_HI)
            band_micro = p["mcap_pct"] > UNIVERSE_PCT_HI
        else:
            band = p["mcap_rank"].between(UNIVERSE_RANK_LO, UNIVERSE_RANK_HI)
            band_micro = p["mcap_rank"] > UNIVERSE_RANK_HI
        p["in_band"] = band.fillna(False) & live
        p["u_mid"] = p["in_band"] & liq.fillna(False) & seasoned.fillna(False)
        p["u_micro"] = (band_micro.fillna(False) & live & seasoned.fillna(False) &
                        (adtv >= 1e8).fillna(False))
        return p

    # ── §5.4 감쇠 감사 ───────────────────────────────────────────────────────────────────
    def audit_attrition(self, P: pd.DataFrame) -> pd.DataFrame:
        p = P.copy()
        p["year"] = p["month"].dt.year
        live = p["listed"].astype(bool) if "listed" in p.columns else pd.Series(True, index=p.index)
        adtv = col(p, "adv20")
        seasoned = col(p, "days_listed") >= UNIVERSE_SEASON_DAYS
        rows = []
        for y, gg in p.groupby("year"):
            nm = max(gg["month"].nunique(), 1)
            lv = live.loc[gg.index]
            rows.append({
                "year": int(y),
                # 전체상장 = 그 달 패널에 존재하는 모든 행(가격이 관측된 종목)
                # PIT유니버스 = 그중 상장일·폐지일 기준으로 '그 시점에 실제 상장 상태'인 것만
                #   → 두 숫자의 차이가 곧 PIT 필터가 걸러낸 양이다. 같은 값으로 찍으면
                #     이 표가 존재하는 이유(어느 게이트가 표본을 깎는가)가 사라진다.
                "전체상장": len(gg) / nm,
                "PIT유니버스": lv.sum() / nm,
                "시총밴드": (gg["in_band"] & lv).sum() / nm,
                "유동성": (gg["in_band"] & lv & adtv.loc[gg.index].ge(UNIVERSE_MIN_ADTV)).sum() / nm,
                "상장250일": (gg["in_band"] & lv & adtv.loc[gg.index].ge(UNIVERSE_MIN_ADTV)
                              & seasoned.loc[gg.index]).sum() / nm,
                "U_MID": gg["u_mid"].sum() / nm,
                "U_MICRO": gg["u_micro"].sum() / nm,
            })
        A = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
        self.attrition = A
        LOG.table([[int(r.year), f"{r.전체상장:,.0f}", f"{r.PIT유니버스:,.0f}", f"{r.시총밴드:,.0f}",
                    f"{r.유동성:,.0f}", f"{r.상장250일:,.0f}", f"{r.U_MID:,.0f}", f"{r.U_MICRO:,.0f}"]
                   for r in A.itertuples(index=False)],
                  ["년도", "전체상장", "PIT유니버스", "시총밴드", "유동성", "상장250일",
                   "U-MID", "U-MICRO"],
                  ["c", "r", "r", "r", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§5.4) — 어느 게이트에서 표본이 붕괴하는지 눈으로 본다")
        return A

    def verdict_mode(self, A: pd.DataFrame) -> Tuple[str, str]:
        """§5.4 판정: 첫해와 마지막해의 U-MID 종목수가 20% 이상 차이나면 분위로 교체."""
        if A is None or len(A) < 2:
            return self.mode, "표본 부족 — 판정 보류"
        a, b = float(A["U_MID"].iloc[0]), float(A["U_MID"].iloc[-1])
        base = max(a, b, 1.0)
        diff = abs(a - b) / base
        y0, y1 = int(A["year"].iloc[0]), int(A["year"].iloc[-1])
        txt = (f"{y0}년 {a:,.0f}종목 → {y1}년 {b:,.0f}종목 (차이 {100*diff:.1f}%)")
        if diff >= 0.20:
            return "pct", (f"❗ {txt} — 20% 이상 차이. 상장 종목 수가 크게 변해 절대 랭크"
                           f"({UNIVERSE_RANK_LO}~{UNIVERSE_RANK_HI})가 구간의 의미를 바꿉니다. "
                           f"분위({UNIVERSE_PCT_LO:.0%}~{UNIVERSE_PCT_HI:.0%})로 교체합니다.")
        return "rank", f"✔ {txt} — 20% 미만. 절대 랭크를 유지합니다."

    def resolve_mode(self, P: pd.DataFrame) -> pd.DataFrame:
        """감쇠 감사 → 필요 시 분위 모드로 재산출. auto 가 아니면 사용자 지정을 존중한다."""
        P = self.annotate(P, mode=self.mode)
        A = self.audit_attrition(P)
        verdict_mode, why = self.verdict_mode(A)
        LOG.info(f"유니버스 모드 판정: {why}")
        if self.mode_requested == "auto" and verdict_mode != self.mode:
            LOG.warn(f"유니버스 정의를 '{self.mode}' → '{verdict_mode}' 로 교체하고 재측정합니다. "
                     f"※ 이 전환은 전체 표본을 본 뒤의 결정이므로 그 자체가 약한 사후선택입니다. "
                     f"R5 절제에서 두 정의를 모두 측정해 성과가 정의에 좌우되지 않는지 확인하세요.")
            self.mode = verdict_mode
            P = self.annotate(P, mode=self.mode)
            self.audit_attrition(P)
        elif self.mode_requested != "auto":
            LOG.info(f"UNIVERSE_MODE='{self.mode_requested}' 로 고정되어 있어 자동 교체를 하지 않습니다.")
        n = int(P["u_mid"].sum())
        avg = n / max(P["month"].nunique(), 1)
        LOG.ok(f"U-MID 유니버스 확정 (mode={self.mode}) — 월평균 {avg:,.0f}종목 · 총 {n:,} 종목·월")
        if avg < 200:
            LOG.warn(f"U-MID 월평균이 {avg:,.0f}종목으로 200 미만입니다. §11-6 킬 기준입니다 — "
                     f"통계 검정이 불가능한 수준이므로 위 감쇠표에서 어느 게이트가 원인인지 "
                     f"먼저 확인하세요(임계값부터 낮추지 마세요).")
        return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  기본 패널 격자
# ═══════════════════════════════════════════════════════════════════════════════════════════
def build_base_panel(months: pd.DatetimeIndex, px_monthly: pd.DataFrame, px_daily: pd.DataFrame,
                     sec: pd.DataFrame, mcap: pd.DataFrame) -> pd.DataFrame:
    """(month, code) 격자 + 가격/유동성/상장상태/시총. 밴드 밖 종목도 전부 보존한다."""
    P = px_monthly[px_monthly["month"].isin(months)].copy()
    P["month"] = as_ts_series(P["month"])
    P["code"] = P["code"].astype(str)

    # ── 상장 상태 (C2) ───────────────────────────────────────────────────────────────────
    s = sec.drop_duplicates("code").set_index("code")
    ld = as_ts_series(s["listing_date"]).to_dict() if "listing_date" in s.columns else {}
    dd = as_ts_series(s["delisting_date"]).to_dict() if "delisting_date" in s.columns else {}
    P["listing_date"] = P["code"].map(ld)
    P["delisting_date"] = P["code"].map(dd)
    P["listed"] = (~(P["listing_date"].notna() & (P["listing_date"] > P["month"])) &
                   ~(P["delisting_date"].notna() & (P["delisting_date"] <= P["month"])))

    # ── 상장 후 거래일 수 ────────────────────────────────────────────────────────────────
    #   ★ 앵커 주의(v2 의 조용한 유니버스 붕괴 원인): searchsorted 는 '가격패널 시작일 이전에
    #     상장한' 종목을 전부 index 0 으로 보낸다. 거기에 +250 을 더하면 1990년 상장 종목조차
    #     "패널 시작 후 250거래일"에야 시즈닝이 끝난 것으로 계산되어 2017년 중반까지
    #     기존 상장사 전부가 유니버스에서 빠진다. 에러도 로그도 없이.
    #     → 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은 이미 시즈닝 완료.
    #   ★★ 두 번째 함정: **상장일을 모르는 경우** ★★
    #     FDR GitHub 상장목록 CSV 에는 ListingDate 컬럼이 없는 스냅샷이 있다(실측 확인:
    #     컬럼이 Code/ISU_CD/Name/Market/Dept/Close 뿐). KIND 가 막히면 상장일이 전 종목 결측이
    #     되고, 그때 "모르면 신규 상장으로 간주"하면 패널 첫 12개월의 유니버스가 통째로 0 이 된다.
    #     에러도 경고도 없이. → '모른다'와 '최근 상장했다'는 완전히 다르다.
    #     앵커는 (상장일 ∨ 최초 가격 관측일) 이고, 그게 패널 시작 이전이면 시즈닝은 이미 끝났다.
    td = np.sort(pd.unique(as_ts_series(px_daily["date"]).values)) if len(px_daily) else np.array([])
    first_px = (P.groupby("code", observed=True)["month"].transform("min"))
    anchor = P["listing_date"].where(P["listing_date"].notna(), first_px)
    n_known = int(P["listing_date"].notna().sum())
    if len(td):
        t0 = as_ts(td[0])
        panel_start = P["month"].min()
        ai = anchor.to_numpy(dtype="datetime64[ns]")
        mi = P["month"].to_numpy(dtype="datetime64[ns]")
        i_anchor = np.searchsorted(td, ai, side="left")
        i_now = np.searchsorted(td, mi, side="right")
        n_days = (i_now - i_anchor).astype("float64")
        pre = (~np.isnat(ai)) & (ai <= np.datetime64(max(t0, panel_start)))
        n_days = np.where(pre, 1e6, n_days)         # 패널 시작 시점에 이미 있었음 = 시즈닝 완료
        n_days = np.where(np.isnat(ai), 1e6, n_days)   # 앵커 자체를 모르면 '오래된 종목'으로 본다
        P["days_listed"] = n_days
    else:
        P["days_listed"] = 1e6
    if n_known < 0.5 * len(P):
        LOG.warn(f"상장일이 확인된 행이 {100*n_known/max(len(P),1):.0f}% 뿐입니다 "
                 f"(KIND 상장법인목록을 못 받으면 흔합니다). 상장일이 없는 종목은 "
                 f"'최초 가격 관측일'을 앵커로 쓰고, 그것도 패널 시작 이전이면 시즈닝 완료로 "
                 f"간주합니다. → 신규 상장 종목의 시즈닝 필터가 그만큼 느슨해집니다. "
                 f"반대 방향(전 종목을 신규로 간주)이 유니버스를 통째로 비우는 것보다 안전합니다.")

    # ── PIT 시가총액 ─────────────────────────────────────────────────────────────────────
    if mcap is not None and len(mcap):
        m = mcap.copy()
        m["month"] = as_ts_series(m["month"])
        m["code"] = m["code"].astype(str)
        P = P.merge(m[["code", "month", "mcap", "mcap_src"]], on=["code", "month"], how="left")
    else:
        P["mcap"] = np.nan
        P["mcap_src"] = "none"
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) · "
           f"{mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel", P)
    return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §7  셀 — CELL_MID = (date, ind_mid, size_bucket)
# ═══════════════════════════════════════════════════════════════════════════════════════════
CELL_KEYS = ["ym", "ind_mid", "size_bucket"]
CELL_FALLBACK = ["ym", "ind_mid"]
CELL_FALLBACK2 = ["ym"]


def build_cells(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """셀 = (연월, 산업중분류, 규모 3단계).

    규모를 넣는 이유: 같은 산업이라도 대형/소형은 성장률 분포 자체가 다르다. 셀에 넣으면
    그 차이가 공통충격으로 흡수되어 비용 0 으로 제거된다.
    ★ 규모 버킷은 그 달의 시총 3분위다. 전 기간 고정 경계를 쓰면 인플레이션·시장 전체 상승이
      그대로 버킷 이동으로 나타나 셀 정의가 시간에 따라 흘러간다.
    """
    p = P.copy()
    ind = sec.drop_duplicates("code").set_index("code")["industry"].astype(str).to_dict() \
        if "industry" in sec.columns else {}
    raw = p["code"].map(ind).fillna("미분류").astype(str)
    # 산업 중분류: KRX/KIND 업종명은 자유 텍스트라 앞 토큰만 취해 과분할을 막는다.
    p["ind_mid"] = raw.str.replace(r"\s+", "", regex=True).str.slice(0, 6).replace("", "미분류")
    p["ym"] = p["month"].dt.strftime("%Y%m")

    mc = col(p, "mcap")
    q = mc.groupby(p["month"], observed=True).rank(pct=True, method="average")
    p["size_bucket"] = np.select([q <= 1 / 3, q <= 2 / 3, q > 2 / 3],
                                 ["S", "M", "L"], default="NA")
    n_cell = p.groupby(CELL_KEYS, observed=True)["code"].transform("size")
    n_ind = int(p["ind_mid"].nunique())
    LOG.info(f"셀 구성: {p.groupby(CELL_KEYS, observed=True).ngroups:,}개 "
             f"(중앙 크기 {int(n_cell.median()):,}종목 · 산업 {n_ind}종) · 폴백 사다리 "
             f"{'>'.join(['+'.join(CELL_KEYS), '+'.join(CELL_FALLBACK), '+'.join(CELL_FALLBACK2)])}")
    unclassified = float((p["ind_mid"] == "미분류").mean())
    if n_ind <= 2 or unclassified > 0.5:
        LOG.warn(f"산업 분류가 사실상 없습니다 (고유 {n_ind}종 · 미분류 {100*unclassified:.0f}%). "
                 f"KIND 상장법인목록을 못 받으면 이렇게 됩니다 — FDR GitHub 상장목록 CSV 에는 "
                 f"업종 컬럼이 없는 스냅샷이 있습니다. 이 상태에서는 '셀 내 정규화'가 "
                 f"'규모버킷 내 정규화'로 퇴화합니다. 예외는 안 나지만 산업 공통충격이 "
                 f"제거되지 않아 경기민감 업종이 통째로 상·하위를 차지할 수 있습니다. "
                 f"kind.krx.co.kr 접근을 확인하세요.")
        PIPE.note("WARN: 산업 분류 부재 — 셀 정규화 퇴화")
    return p


def cell_ladder(P: pd.DataFrame, keys: Sequence[str] = CELL_KEYS) -> List[pd.Series]:
    """폴백 사다리: (연월×산업×규모) → (연월×산업) → (연월). 표본이 부족하면 위로 올라간다."""
    fbs = [list(keys[:-1]) or list(keys), CELL_FALLBACK2]
    seen, out = set(), []
    for k in fbs:
        t = tuple(k)
        if t == tuple(keys) or t in seen:
            continue
        seen.add(t)
        out.append(cell_series(P, k))
    return out


def cell_series(P: pd.DataFrame, keys: Sequence[str]) -> pd.Series:
    """셀 키 결합 문자열. category dtype 을 그대로 groupby 하면 observed=False 에서
    카티션 폭발이 나므로 항상 문자열로 만든 뒤 넘긴다."""
    s = None
    for k in keys:
        c = P[k].astype(str) if k in P.columns else pd.Series("NA", index=P.index)
        s = c if s is None else (s + "\x1f" + c)
    return s if s is not None else pd.Series("ALL", index=P.index)
