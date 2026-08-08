# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-B  일별 센서(§6) → 주간 패널 → 국면 판정(§7.1) → TP 조립(§7.2) → 방화벽(§7.3)      ║
# ║                                                                                          ║
# ║  원칙 (§1):                                                                               ║
# ║   · 모든 롤링은 groupby(code)[col].transform(...) — 종목 루프 금지                         ║
# ║   · 신용잔고/수급은 '거래일 +1영업일' 지연을 반영한 뒤에만 센서에 들어간다                  ║
# ║   · TP 는 clip(z,0)*clip(z,0). z*z 금지 (양쪽 음수가 최고점을 받는 부호 버그)               ║
# ║   · 셀 정규화는 rank(pct=True)+transform. groupby.apply 금지                               ║
# ║   · 거부권/방화벽은 이진·곱·상쇄 불가                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SENSOR_COLS = ["f_dd", "f_dd_spd", "f_cr", "f_cr_pctl", "f_cr_chg", "f_cr_chg_slow",
               "f_retail", "f_inst", "f_ret_ex", "f_vol", "f_turn"]
TP_COLS = ["TP_F1", "TP_F2", "TP_F3", "TP_F4"]


def week_grid(start: str, end: str, px: pd.DataFrame) -> pd.DatetimeIndex:
    """주간 신호일 = 실제 거래일에 정렬된 주 1회 격자(§8).
    달력상의 금요일이 휴장이면 그 주의 마지막 거래일을 쓴다."""
    cal = pd.DatetimeIndex(np.sort(pd.unique(as_ts_series(px["date"]).values))) \
        if px is not None and len(px) else pd.DatetimeIndex([])
    weeks = pd.date_range(as_ts(start), as_ts(end), freq=REBAL_DAY)
    if not len(cal):
        return weeks
    out = []
    for w in weeks:
        pos = int(np.searchsorted(cal.values, np.datetime64(w), side="right")) - 1
        if pos >= 0 and (w - cal[pos]).days <= 6:
            out.append(cal[pos])
    return pd.DatetimeIndex(sorted(set(out)))


def _rolling_rank_pct(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    """자기 이력 백분위. pandas>=2.1 의 Rolling.rank 를 쓰고, 없으면 z→정규근사로 폴백한다.
    (파이썬 apply 로 돌리면 600만 행에서 수 분이 아니라 수십 분이 걸린다)"""
    try:
        return s.rolling(window, min_periods=min_periods).rank(pct=True)
    except (AttributeError, TypeError):
        m = s.rolling(window, min_periods=min_periods).mean()
        sd = s.rolling(window, min_periods=min_periods).std()
        z = (s - m) / sd.replace(0, np.nan)
        from math import erf, sqrt
        return z.map(lambda v: np.nan if not np.isfinite(v) else 0.5 * (1 + erf(v / sqrt(2))))


def _chunk_codes(codes: Sequence[str], n: int) -> List[List[str]]:
    codes = list(codes)
    n = max(1, int(n))
    return [codes[i:i + n] for i in range(0, len(codes), n)]


def build_flp_panel(px: pd.DataFrame, credit: pd.DataFrame, flows: pd.DataFrame,
                    shares: pd.DataFrame, weeks: pd.DatetimeIndex,
                    uni: "Universe") -> pd.DataFrame:
    """일별 센서를 청크 단위로 계산하고 주간 격자에만 남긴다(RAM 방어).

    반환: (code, date=신호일, 센서들, exec_px, fwd_ret, adv20, mcap)
    """
    if px is None or not len(px):
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)

    # ★ 결합키 dtype 정규화. downcast() 를 지난 가격 패널의 code 는 category 인데
    #   신용잔고/수급/주식수 프레임의 code 는 object 다. merge_asof(by="code") 는 dtype 이
    #   다르면 MergeError 로 죽는다 — 몇 시간짜리 수집이 끝난 직후 L2 에서 터진다.
    #   (합성 스모크는 downcast 를 타지 않아 이 경로를 못 본다)
    _as_code = lambda d: d.assign(code=d["code"].astype(str))
    px = _as_code(px.copy())
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    for c in ("close", "open", "amount", "volume"):
        if c not in px.columns:
            px[c] = np.nan

    cr = credit.copy() if credit is not None and len(credit) else pd.DataFrame(columns=CREDIT_COLS)
    if len(cr):
        cr = _as_code(cr)
        cr["date"] = as_ts_series(cr["date"])
        cr = cr.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    fl = flows.copy() if flows is not None and len(flows) else pd.DataFrame(columns=FLOW_COLS)
    if len(fl):
        fl = _as_code(fl)
        fl["date"] = as_ts_series(fl["date"])
        fl = fl.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    sh = shares.copy() if shares is not None and len(shares) else pd.DataFrame(
        columns=["snap_date", "code", "shares", "mcap_snap"])
    if len(sh):
        sh = _as_code(sh)
        sh["snap_date"] = as_ts_series(sh["snap_date"])
        # ★ 상장주식수 스냅샷도 PIT: 스냅샷일 +1영업일 이후에만 알 수 있다.
        sh["knowledge_date"] = next_bday(sh["snap_date"])
        sh = sh.dropna(subset=["code", "knowledge_date"]).sort_values("knowledge_date")

    # 주간 격자 × 유니버스 (C13 — 매 시점의 당시 값으로 멤버십 판정)
    grid_rows = []
    for w in weeks:
        codes = uni.at(w)
        uni.audit_row("PIT유니버스", w, codes)
        grid_rows.append(pd.DataFrame({"code": codes, "week": w}))
    G = pd.concat(grid_rows, ignore_index=True) if grid_rows else pd.DataFrame(columns=["code", "week"])
    if len(G):
        G["code"] = G["code"].astype(str)
    if G.empty:
        LOG.error("주간 격자가 비었습니다 — 유니버스가 전 구간에서 0종목입니다.")
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)

    all_codes = sorted(set(G["code"]) & set(px["code"]))
    LOG.info(f"일별 센서 계산: {len(all_codes):,}종목 × {len(weeks):,}주 "
             f"(청크 {DAILY_CHUNK_CODES}종목 단위 — 메모리 상한 방어)")
    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        LOG.warn("신용잔고가 프록시이므로 f_cr_chg 는 '비율'이 아니라 '자기 스케일 정규화 차분'을 "
                 "씁니다. 프록시는 부호가 바뀌는 양이라 비율이 0 근처에서 발산하기 때문입니다 "
                 "— 임계값(PH_CR_CHG_B)의 의미가 등급에 따라 달라진다는 점을 인지하세요.")

    # ★ 청크마다 isin() 으로 전체 일봉을 훑으면 (청크수 × 전체행) 스캔이 된다.
    #   2,500종목·650만행이면 7회 × 650만 = 4,500만 비교. 코드로 정렬해 두고 위치로 잘라내면
    #   같은 결과를 한 번의 정렬 비용으로 얻는다. 신용/수급/주식수도 동일하게 처리한다.
    def _slicer(df: pd.DataFrame):
        if df is None or not len(df):
            return None
        d0 = df.sort_values(["code"], kind="stable").reset_index(drop=True)
        codes_arr = d0["code"].to_numpy()
        return d0, codes_arr

    _px_s = _slicer(px)
    _cr_s = _slicer(cr)
    _fl_s = _slicer(fl)
    _sh_s = _slicer(sh)

    def _take(sl, chunk_codes):
        if sl is None:
            return None
        d0, arr = sl
        lo = np.searchsorted(arr, chunk_codes[0], side="left")
        hi = np.searchsorted(arr, chunk_codes[-1], side="right")
        sub = d0.iloc[lo:hi]
        # 청크 경계가 정확히 맞지 않는 경우(코드 정렬 순서가 다른 프레임)만 보정
        if len(sub) and (sub["code"].iloc[0] < chunk_codes[0] or
                         sub["code"].iloc[-1] > chunk_codes[-1]):
            sub = sub[sub["code"].isin(set(chunk_codes))]
        return sub

    out_parts = []
    for chunk in tqdm(_chunk_codes(all_codes, DAILY_CHUNK_CODES), desc="L1 센서", ncols=88,
                      leave=False):
        cs = set(chunk)
        _pxc = _take(_px_s, chunk)
        d = (_pxc[_pxc["code"].isin(cs)] if _pxc is not None else px.head(0)).copy()
        if d.empty:
            continue
        # ── 원시 입력 결합 ────────────────────────────────────────────────────────────
        #   중복 (code,date) 가 하나라도 있으면 merge 가 패널 행을 복제해 수익률이 부풀려진다
        c0 = _take(_cr_s, chunk)
        if c0 is not None and len(c0):
            c0 = (c0[c0["code"].isin(cs)][["code", "date", "credit_bal"]]
                  .drop_duplicates(["code", "date"], keep="last"))
            d = d.merge(c0, on=["code", "date"], how="left")
            # 주간 관측이면 그 사이는 forward-fill (★선형보간 금지 — 미래정보 누출)
            d["credit_bal"] = d.groupby("code", observed=True)["credit_bal"].ffill()
        if "credit_bal" not in d.columns:
            d["credit_bal"] = np.nan

        f0 = _take(_fl_s, chunk)
        if f0 is not None and len(f0):
            f0 = (f0[f0["code"].isin(cs)][["code", "date", "retail_net", "inst_net",
                                           "foreign_net"]]
                  .drop_duplicates(["code", "date"], keep="last"))
            d = d.merge(f0, on=["code", "date"], how="left")
        for c in ("retail_net", "inst_net", "foreign_net"):
            if c not in d.columns:
                d[c] = np.nan

        s0 = _take(_sh_s, chunk)
        if s0 is not None and len(s0):
            s0 = (s0[s0["code"].isin(cs)][["code", "knowledge_date", "shares"]]
                  .drop_duplicates(["code", "knowledge_date"], keep="last")
                  .sort_values("knowledge_date"))
            d = d.sort_values("date")
            d = pd.merge_asof(d, s0, left_on="date", right_on="knowledge_date", by="code",
                              direction="backward")
        if "shares" not in d.columns:
            d["shares"] = np.nan
        d = d.sort_values(["code", "date"])

        g = lambda c: d.groupby("code", observed=True)[c]

        # ── PIT 지연 (§4.1): 잔고·수급은 '거래일 +1영업일' 공표 → 거래일 기준 1행 시프트 ──
        for c in ("credit_bal", "retail_net", "inst_net", "foreign_net"):
            d[c] = g(c).shift(1)

        # ── 가격 상태 ────────────────────────────────────────────────────────────────
        d["p252max"] = g("close").transform(lambda s: s.rolling(252, min_periods=120).max())
        d["f_dd"] = d["close"] / d["p252max"] - 1.0
        d["f_dd_spd"] = d["f_dd"] - g("f_dd").shift(60)
        d["ret1d"] = g("close").pct_change()
        d["adv20"] = g("amount").transform(lambda s: s.rolling(20, min_periods=10).mean())
        d["adv60"] = g("amount").transform(lambda s: s.rolling(60, min_periods=30).mean())

        # ── 시가총액 (분모) ──────────────────────────────────────────────────────────
        d["mcap"] = d["close"] * d["shares"]
        # 상장주식수를 못 구한 종목은 '20일 거래대금 합'을 대리 분모로 쓴다(스케일만 다름).
        proxy_den = d["adv20"] * 20.0
        d["mcap_den"] = d["mcap"].where(d["mcap"] > 0, proxy_den)

        # ── 강제 재고 (핵심) ─────────────────────────────────────────────────────────
        d["f_cr"] = safe_div(d["credit_bal"], d["mcap_den"])
        d["f_cr_pctl"] = g("f_cr").transform(
            lambda s: _rolling_rank_pct(s, 252, 120))
        # 변화율은 '비율'이 기본이지만, 프록시(Fallback B)는 부호가 바뀌는 양이라
        # 비율이 0 근처에서 발산·부호역전한다 → 그 경우에만 자기 스케일로 정규화한 '차분'을 쓴다.
        if CREDIT_GRADE == "FALLBACK_B_PROXY":
            scale = g("f_cr").transform(lambda s: s.abs().rolling(252, min_periods=60).mean())
            d["f_cr_chg"] = safe_div(d["f_cr"] - g("f_cr").shift(20), scale)
            d["f_cr_chg_slow"] = safe_div(d["f_cr"] - g("f_cr").shift(60), scale)
        else:
            d["f_cr_chg"] = safe_div(d["f_cr"], g("f_cr").shift(20)) - 1.0
            d["f_cr_chg_slow"] = safe_div(d["f_cr"], g("f_cr").shift(60)) - 1.0

        # ── 소유권 이전 ──────────────────────────────────────────────────────────────
        r20 = g("retail_net").transform(lambda s: s.rolling(20, min_periods=10).sum())
        r60 = g("retail_net").transform(lambda s: s.rolling(60, min_periods=30).sum())
        i20 = (g("inst_net").transform(lambda s: s.rolling(20, min_periods=10).sum()) +
               g("foreign_net").transform(lambda s: s.rolling(20, min_periods=10).sum()))
        d["f_retail"] = safe_div(r20, d["mcap_den"])
        d["f_inst"] = safe_div(i20, d["mcap_den"])
        d["f_ret_ex"] = -safe_div(r60, d["mcap_den"])

        # ── 안정화 ───────────────────────────────────────────────────────────────────
        d["f_vol"] = -g("ret1d").transform(lambda s: s.rolling(20, min_periods=10).std())
        d["f_turn"] = safe_div(d["adv20"], d["adv60"])

        # ── 체결가: 신호 산출일의 '다음 거래일 시가' (§8) ─────────────────────────────
        d["next_open"] = g("open").shift(-1)
        d["next_date"] = g("date").shift(-1)
        gap = (d["next_date"] - d["date"]).dt.days
        d["exec_px"] = d["next_open"].where(gap.notna() & (gap <= 10)).fillna(d["close"])

        keep = ["code", "date", "close", "exec_px", "adv20", "mcap", "mcap_den",
                "credit_bal", "shares"] + SENSOR_COLS
        d = d[[c for c in keep if c in d.columns]]

        # ── 주간 격자로 축약 (as-of backward: 신호일 이전 최신 관측) ───────────────────
        gg = G[G["code"].isin(cs)].sort_values("week")
        if gg.empty:
            continue
        d = d.sort_values("date")
        m = pd.merge_asof(gg, d, left_on="week", right_on="date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=7))
        out_parts.append(m)

    if not out_parts:
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)
    P = pd.concat(out_parts, ignore_index=True)
    P = P.rename(columns={"week": "wk"}).sort_values(["code", "wk"])
    P["signal_date"] = P["date"]

    # ── 다음 주 수익률 (체결가 → 체결가). 주 연속성이 끊기면 결측(수익 과대계상 방지) ──
    nxt_px = P.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_wk = P.groupby("code", observed=True)["wk"].shift(-1)
    adjacent = ((nxt_wk - P["wk"]).dt.days.between(1, 10))
    P["fwd_ret"] = (nxt_px / P["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_wk.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"주 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 구간 수익을 1주 수익으로 계상하지 않기 위함). "
                 f"상장폐지는 백테스트 엔진이 -100% 로 별도 처리합니다.")
    # ★ 신호일이 격자일보다 며칠 앞선 행 = 최근 거래가 없었다는 뜻(거래정지 진입 구간).
    #   보유 연속성을 위해 행 자체는 남기되, '그 가격으로 신규 진입'은 막아야 한다
    #   (이미 존재하지 않는 가격에 새로 사는 셈이 된다).
    P["stale_days"] = (P["wk"] - P["signal_date"]).dt.days
    P = P[P["signal_date"].notna()].reset_index(drop=True)
    n_stale = int((P["stale_days"] > 3).sum())
    if n_stale:
        LOG.info(f"신호일이 3일 이상 지연된 행 {n_stale:,}건 — 최근 시세가 없는 구간입니다. "
                 f"보유 연속성 판단에는 쓰되 신규 진입 자격에서는 제외합니다.")
    LOG.ok(f"주간 패널 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB "
           f"({P['code'].nunique():,}종목 × {P['wk'].nunique():,}주)")
    PIPE.io("OUT", "MEM", "flp_weekly_panel", P)
    return P


# ── 유니버스 밴드 (C13) ─────────────────────────────────────────────────────────────────────
def build_size_estimate(P: pd.DataFrame) -> pd.DataFrame:
    """규모 척도를 '하나'로 만든다.

    시총(≈1e11)과 거래대금(≈1e9)은 스케일이 100배 다르다. 둘을 한 컬럼에 coalesce 해서
    랭크하면 '상위 250 제외'가 사실상 '주식수 데이터를 가진 250종목 제외'가 되고,
    셀의 규모 축과 R3 의 규모 팩터도 똑같이 오염된다.
    → 주별로 둘 다 관측된 종목에서 mcap/adv20 의 중앙 배율을 구해 거래대금을 시총 스케일로
      보정한 뒤, 전 종목을 '한 랭크'에서 비교한다. 보정 계수를 못 구하면 전역 중앙값을 쓴다.
    """
    P = P.copy()
    mcap = pd.to_numeric(P.get("mcap"), errors="coerce")
    adv = pd.to_numeric(P.get("adv20"), errors="coerce")
    both = mcap.notna() & (mcap > 0) & adv.notna() & (adv > 0)
    est = mcap.where(mcap > 0)
    if both.any():
        ratio = (mcap[both] / adv[both])
        k_wk = ratio.groupby(P.loc[both, "wk"]).median()
        k = P["wk"].map(k_wk)
        k = k.fillna(float(ratio.median()))
    else:
        k = pd.Series(20.0, index=P.index)      # 관측이 없으면 보수적 상수 (스케일만 맞춘다)
    P["size_est"] = est.where(est.notna(), adv * k)
    P["size_basis"] = np.where(mcap.notna() & (mcap > 0), "mcap", "adv20×보정")
    n_proxy = int((P["size_basis"] == "adv20×보정").sum())
    if n_proxy:
        LOG.info(f"규모 척도 — 시총 {len(P)-n_proxy:,}행 / 거래대금×보정 {n_proxy:,}행. "
                 f"주별 중앙 배율로 스케일을 맞춰 '한 랭크'에서 비교합니다 "
                 f"(척도가 다른 두 값을 섞어 랭크하지 않습니다).")
    return P


MAX_EXCLUDE_FRAC = 0.30      # 안전밸브: 어떤 주에도 유니버스의 30% 넘게 잘라내지 않는다


def apply_universe_bands(P: pd.DataFrame) -> pd.DataFrame:
    """상위 250 대형주 제외 + 유동성 하한. 매 시점의 당시 값으로 재산출한다.
    ★ 보유 중 밴드 이탈은 청산 사유가 아니다(§4.3) — 진입 자격에만 쓴다.

    ★ 안전밸브: 그 주의 유니버스가 250종목보다 작으면 '상위 250 제외'가 유니버스를 통째로
      지운다(신호 영구 무발화). 이 경우 제외 컷을 그 주 종목수의 30% 로 낮추고, 조용히가
      아니라 로그로 알린다. 실데이터(2,000+종목)에서는 절대 발동하지 않는다."""
    P = P.copy()
    P = build_size_estimate(P)
    P["mcap_rank"] = (P.groupby("wk", observed=True)["size_est"]
                       .rank(ascending=False, method="first"))
    P["size_pct"] = P.groupby("wk", observed=True)["size_est"].rank(pct=True, ascending=False)
    n_wk = P.groupby("wk", observed=True)["code"].transform("size")
    cut = np.minimum(MCAP_RANK_EXCLUDE_TOP, np.floor(n_wk * MAX_EXCLUDE_FRAC))
    binding = int((cut < MCAP_RANK_EXCLUDE_TOP).sum())
    if binding:
        LOG.warn(f"유니버스가 작아 '상위 {MCAP_RANK_EXCLUDE_TOP} 제외' 규칙이 "
                 f"{binding:,}행에서 유니버스를 과도하게 삭제합니다 → 해당 주는 "
                 f"상위 {MAX_EXCLUDE_FRAC:.0%} 제외로 낮춥니다(안전밸브). "
                 f"실데이터 전 종목 실행에서는 발동하지 않아야 정상입니다.")
    P["mcap_cut"] = cut
    P["V6"] = (P["adv20"] >= MIN_ADV_KRW).fillna(False).astype(int)
    P["in_band"] = ((P["mcap_rank"] > cut) & (P["V6"] == 1)).fillna(False).astype(int)

    # ── 비교군: 스몰캡 밴드 (매 시점 시총 하위 N) ─────────────────────────────────────
    #   '작은 쪽에서 N번째까지'를 매 시점 다시 센다. 현재 시총으로 과거를 정의하지 않는다(C13).
    small_rank = (P.groupby("wk", observed=True)["size_est"]
                   .rank(ascending=True, method="first"))
    P["small_rank"] = small_rank
    P["in_band_small"] = ((small_rank <= SMALLCAP_BOTTOM_N) & (P["V6"] == 1) &
                          (P["mcap_rank"] > cut)).fillna(False).astype(int)
    return P


# ── 셀 (§7.2) ───────────────────────────────────────────────────────────────────────────────
def build_cells_flp(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """셀 = (주, 산업중분류, 규모버킷). 규모는 시총 5분위(PIT)."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict() if len(sec) else {}
    P = P.copy()
    P["industry"] = P["code"].map(ind).fillna("미분류").astype(str)
    P["ind_mid"] = P["industry"].str.slice(0, 4).replace("", "미분류")
    base = P["size_est"] if "size_est" in P.columns else \
        build_size_estimate(P)["size_est"]
    P["size_bucket"] = (base.groupby(P["wk"]).rank(pct=True)
                        .mul(5).clip(0, 4.999).fillna(-1).astype(int).astype(str))
    ws = P["wk"].dt.strftime("%Y%m%d")
    P["cell"] = ws + "|" + P["ind_mid"] + "|" + P["size_bucket"]
    P["cell_l2"] = ws + "|" + P["ind_mid"] + "|ALL"
    P["cell_l3"] = ws + "|ALL|ALL"
    return P


def cell_rank(P: pd.DataFrame, col_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 백분위. 표본이 얇은 셀은 상위 단위로 폴백한다(사다리). groupby.apply 금지."""
    s = P[col_or_series] if isinstance(col_or_series, str) else col_or_series
    s = pd.to_numeric(s, errors="coerce")
    fine = s.groupby(P["cell"], observed=True).rank(pct=True)
    mid = s.groupby(P["cell_l2"], observed=True).rank(pct=True)
    coarse = s.groupby(P["cell_l3"], observed=True).rank(pct=True)
    n1 = s.notna().groupby(P["cell"], observed=True).transform("sum")
    n2 = s.notna().groupby(P["cell_l2"], observed=True).transform("sum")
    out = fine.where(n1 >= min_n, mid.where(n2 >= min_n, coarse))
    return out


def tp(P: pd.DataFrame, a, b) -> pd.Series:
    """★ 음수 절단 후 곱. 한쪽이라도 셀 중앙 미만이면 정확히 0.
    za*zb 를 쓰면 '둘 다 최악'인 종목이 최고점을 받는다 — 이 전략에서 그건 국면 B 매수다."""
    za = cell_rank(P, a) - 0.5
    zb = cell_rank(P, b) - 0.5
    return (za.clip(lower=0.0) * zb.clip(lower=0.0)).astype(float)


# ── 국면 상태기계 (§7.1) ────────────────────────────────────────────────────────────────────
def classify_phase(P: pd.DataFrame, dd_enter: float = PH_DD_ENTER,
                   cr_enter: float = PH_CR_PCTL_ENTER, use_dd: bool = True,
                   use_credit: bool = True) -> pd.DataFrame:
    """A=물타기(진입금지) / B=반대매매 진행(칼날낙하, 진입금지) / C=소진(진입구간).
    ★ 핵심은 '얼마나 빠졌는가'가 아니라 '강제 재고가 남았는가'다.

    파라미터를 노출하는 이유는 R5(절제)·R2-F(비교군)에서 같은 코드로 조건만 바꿔
    재측정하기 위해서다. 별도 구현을 두면 비교 자체가 오염된다."""
    P = P.copy()
    ret_ex_r = cell_rank(P, "f_ret_ex")
    vol_r = cell_rank(P, "f_vol")
    P["ret_ex_rank"] = ret_ex_r
    P["inst_rank"] = cell_rank(P, "f_inst")

    A = ((P["f_dd"] < dd_enter) & (P["f_cr_pctl"] > 0.50) & (P["f_retail"] > 0))
    B = ((P["f_cr_chg"] < PH_CR_CHG_B) & (P["f_retail"] < 0) & (P["f_dd_spd"] < PH_DD_SPD_B))
    C = ((ret_ex_r >= PH_RET_EX_Q) & (P["f_inst"] > 0) & (vol_r >= 0.50))
    if use_credit:
        C = C & (P["f_cr_pctl"] < cr_enter)
    if use_dd:
        C = C & (P["f_dd"] < dd_enter)

    A = A.fillna(False); B = B.fillna(False); C = C.fillna(False)
    C = C & ~B                       # 반대매매가 진행 중이면 소진 판정을 덮어쓴다
    P["PHASE_A"] = A.astype(int)
    P["PHASE_B"] = B.astype(int)
    P["PHASE_C"] = C.astype(int)
    P["phase"] = np.where(C, "C", np.where(B, "B", np.where(A, "A", "-")))
    return P


# ── 재무 결합 (방화벽 입력) ─────────────────────────────────────────────────────────────────
FLP_FUND_COLS = ["equity", "assets", "liabilities", "cfo_ttm", "op_income_ttm",
                 "net_income_ttm", "revenue_ttm"]


def attach_fundamentals_flp(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """DART 재무를 신호일 기준 as-of 로 결합. 결합키(corp_code) 결측 행을 버리지 않는다(C2)."""
    P = P.copy()
    c2c = (sec.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str).to_dict()
           if len(sec) and "corp_code" in sec.columns else {})
    P["corp_code"] = P["code"].map(c2c)
    if PIT.has("dart_financials"):
        P = PIT.asof_join(P, "dart_financials", by="corp_code", left_time="wk")
    for c in FLP_FUND_COLS:
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_financials"):
        LOG.warn("DART 재무가 없어 방화벽의 자본잠식·영업CF·이자보상 조항이 비활성화됩니다. "
                 "이 전략의 단일 실패모드가 '진짜 죽어가는 회사 매수'이므로 "
                 "DART_API_KEY 입력을 강력히 권합니다.")
    return P


# ── 방화벽 · 거부권 (§7.3) ──────────────────────────────────────────────────────────────────
FIREWALL_CLAUSES = ["자본잠식", "관리종목", "거래정지", "영업CF적자+이자보상<1", "유동성"]
FIREWALL_STATUS: Dict[str, str] = {}          # 조항 → 활성/비활성 사유 (등급 카드에 인쇄)


def apply_firewall(P: pd.DataFrame, watch: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """진짜로 소멸 중인 기업을 거른다. 이진·곱·상쇄 불가(§1-7).
    데이터가 없어 판정할 수 없는 조항은 '통과'로 두되, 감사표에 비활성으로 남긴다."""
    P = P.copy()
    n = len(P)
    audit = []

    ok = pd.Series(True, index=P.index)

    # ① 자본잠식
    if P["equity"].notna().any():
        c = ~(P["equity"] <= 0).fillna(False)
        audit.append(("자본잠식", "활성", int((~c).sum())))
        ok &= c
    else:
        audit.append(("자본잠식", "비활성(재무 없음)", 0))

    # ②③ 관리종목 · 거래정지 (스냅샷만 있으면 '현재 이후'로만 적용 — 과거 오염 금지)
    P["is_watchlist"] = 0
    P["is_trading_halted"] = 0
    if watch is not None and len(watch):
        w = watch.dropna(subset=["code"]).copy()
        w["from_date"] = as_ts_series(w["from_date"])
        for flag, colname in (("admin", "is_watchlist"), ("alert", "is_watchlist"),
                              ("halt", "is_trading_halted")):
            sub = w[w["flag"] == flag]
            if not len(sub):
                continue
            m = sub.groupby("code")["from_date"].min().to_dict()
            frm = P["code"].map(m)
            P[colname] = np.where(frm.notna() & (P["wk"] >= frm), 1, P[colname])
        audit.append(("관리종목", "활성", int((P["is_watchlist"] == 1).sum())))
        audit.append(("거래정지", "활성", int((P["is_trading_halted"] == 1).sum())))
        ok &= (P["is_watchlist"] == 0) & (P["is_trading_halted"] == 0)
    else:
        audit.append(("관리종목", f"비활성(K6 {WATCH_GRADE})", 0))
        audit.append(("거래정지", f"비활성(K6 {WATCH_GRADE})", 0))

    # ④ 영업CF 적자 지속 ∧ 이자보상배율 < 1
    #    ※ 이자비용 계정은 DART 정형 매핑에 없어 '부채×5%' 대리를 쓴다. 대리임을 명시한다.
    if P["cfo_ttm"].notna().any() and P["op_income_ttm"].notna().any():
        icov = safe_div(P["op_income_ttm"], P["liabilities"].abs() * 0.05)
        bad = ((P["cfo_ttm"] < 0) & (icov < 1.0)).fillna(False)
        audit.append(("영업CF적자+이자보상<1(대리)", "활성", int(bad.sum())))
        ok &= ~bad
    else:
        audit.append(("영업CF적자+이자보상<1", "비활성(재무 없음)", 0))

    # ★ 여기까지가 '기업 소멸' 방어 = 보유 중에도 즉시 청산해야 하는 하드 조항이다.
    P["FIREWALL_HARD"] = ok.astype(int)

    # ⑤ 유동성 — 이건 유니버스 밴드의 일부다. 진입 자격에는 쓰되,
    #    보유 중 유동성이 말랐다는 이유로 강제청산하지 않는다(§4.3 "밴드 이탈은 청산 사유가 아니다").
    liq = (P["adv20"] >= MIN_ADV_KRW).fillna(False)
    audit.append(("유동성(ADV20) ※진입자격 전용", "활성", int((~liq).sum())))
    ok &= liq

    P["FIREWALL"] = ok.astype(int)
    FIREWALL_STATUS.clear()
    FIREWALL_STATUS.update({a: b for a, b, _c in audit})
    n_off = sum(1 for _a, b, _c in audit if b.startswith("비활성"))
    if n_off:
        LOG.warn(f"방화벽 {n_off}개 조항이 비활성입니다. 이 전략의 단일 실패모드는 "
                 f"'진짜 죽어가는 회사를 사는 것'이고 방화벽이 유일한 방어입니다 — "
                 f"DART_API_KEY 입력이 성과보다 먼저입니다.")
    LOG.table([[a, b, f"{c:,}"] for a, b, c in audit],
              ["방화벽 조항", "상태", "차단 행수"], ["l", "l", "r"],
              title=f"방화벽 감사 — 전체 {n:,}행 중 통과 {int(P['FIREWALL'].sum()):,}행 "
                    f"({100*P['FIREWALL'].mean():.1f}%)")
    return P


def apply_vetoes(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """V1 희석성 조달 / V2 담보 급증 / V3 이익-현금 괴리 / V_RS 애널리스트 하향.
    거부권은 이진이며 서로 상쇄되지 않는다."""
    P = P.copy()
    P["V1"] = 1; P["V2"] = 1; P["V3"] = 1; P["V_RS"] = 1

    # V1 — 90일 내 유상증자/CB/BW 결정: 강제매도 재고가 '새로' 생성된다
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns:
        d = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue"])].copy()
        if len(d):
            d["rcept_dt"] = as_ts_series(d["rcept_dt"])
            d = d.dropna(subset=["corp_code", "rcept_dt"]).sort_values("rcept_dt")
            d["corp_code"] = d["corp_code"].astype(str)
            L = P[["corp_code", "wk"]].copy()
            L["_ord"] = np.arange(len(L))
            Lv = L.dropna(subset=["corp_code"]).sort_values("wk")
            if len(Lv):
                m = pd.merge_asof(Lv, d[["corp_code", "rcept_dt"]].rename(
                    columns={"rcept_dt": "last_dilute"}),
                    left_on="wk", right_on="last_dilute", by="corp_code", direction="backward")
                gapd = (m["wk"] - m["last_dilute"]).dt.days
                hit = pd.Series(False, index=P.index)
                hit.iloc[m["_ord"].to_numpy()] = (gapd <= 90).fillna(False).to_numpy()
                P["V1"] = (~hit).astype(int)
                LOG.info(f"V1(90일 내 희석성 조달) 발동 {int((P['V1']==0).sum()):,}행")

    # V2 — 최대주주 담보비율 급증: 공개 정형 데이터가 없다. 대리 없이 '비활성'으로 남긴다.
    #      (억지 대리를 넣으면 거부권이 아니라 노이즈가 된다)
    # V3 — 순이익>0 인데 영업CF < 0.5×순이익 (3분기 연속 성격 → TTM 단면으로 근사)
    if P["net_income_ttm"].notna().any() and P["cfo_ttm"].notna().any():
        bad = ((P["net_income_ttm"] > 0) &
               (P["cfo_ttm"] < 0.5 * P["net_income_ttm"])).fillna(False)
        P["V3"] = (~bad).astype(int)
        LOG.info(f"V3(이익-현금 괴리) 발동 {int((P['V3']==0).sum()):,}행")

    # V_RS — 애널리스트 목표주가 하향이 지배적이면 '소진'이 아니라 펀더멘털 악화다
    rs = ctx.get("research_panel")
    if rs is not None and len(rs) and {"code", "wk"}.issubset(rs.columns):
        P = P.merge(rs, on=["code", "wk"], how="left")
    if {"rs_cov_90d", "rs_tp_up_ratio"}.issubset(P.columns):
        bad = ((col(P, "rs_cov_90d").fillna(0) >= 3) &
               (col(P, "rs_tp_up_ratio") <= 0.15)).fillna(False)
        P["V_RS"] = (~bad).astype(int)
        LOG.info(f"V_RS(애널리스트 목표주가 하향 지배) 발동 {int((P['V_RS']==0).sum()):,}행 "
                 f"— 커버리지 3인 이상 & 상향비율 15% 이하")
    for c in ("rs_cov_90d", "rs_tp_up_ratio", "rs_tp_gap"):
        if c not in P.columns:
            P[c] = np.nan
    P["VETO"] = (P["V1"] * P["V2"] * P["V3"] * P["V_RS"]).astype(int)
    return P


# ── 스코어 조립 (§7.2) ──────────────────────────────────────────────────────────────────────
def build_tps(P: pd.DataFrame, method: str = "clip") -> pd.DataFrame:
    """TP 4종. method='raw' 는 R5-7(절제)에서 rank_pct×rank_pct 와 비교하기 위한 것이며
    운영 기본값이 아니다 — clip 을 빼면 '둘 다 최악'이 최고점을 받는다."""
    P = P.copy()
    if method == "clip":
        P["TP_F1"] = tp(P, -P["f_dd"], -P["f_cr_pctl"])
        P["TP_F2"] = tp(P, P["f_ret_ex"], P["f_inst"])
        P["TP_F3"] = tp(P, -P["f_dd"], P["f_vol"])
        P["TP_F4"] = tp(P, -P["f_cr_chg_slow"], P["f_turn"])
    else:
        r = lambda s: cell_rank(P, s)
        P["TP_F1"] = r(-P["f_dd"]) * r(-P["f_cr_pctl"])
        P["TP_F2"] = r(P["f_ret_ex"]) * r(P["f_inst"])
        P["TP_F3"] = r(-P["f_dd"]) * r(P["f_vol"])
        P["TP_F4"] = r(-P["f_cr_chg_slow"]) * r(P["f_turn"])
    return P


def assemble_score(P: pd.DataFrame, use_tps: Optional[Sequence[str]] = None,
                   gate_phase: bool = True, gate_firewall: bool = True,
                   gate_veto: bool = True, band_col: str = "in_band",
                   quiet: bool = False) -> pd.DataFrame:
    P = P.copy()
    if not all(c in P.columns for c in TP_COLS):
        P = build_tps(P)
    cols = list(use_tps) if use_tps else TP_COLS
    P["E"] = nanmean_cols(P, cols)
    P["E_rank"] = P.groupby("wk", observed=True)["E"].rank(pct=True)
    gate = P[band_col].astype(float) if band_col in P.columns else P["in_band"].astype(float)
    if gate_phase:
        gate = gate * P["PHASE_C"]
    if gate_firewall:
        gate = gate * P["FIREWALL"]
    if gate_veto:
        gate = gate * P["VETO"]
    P["Signal"] = P["E_rank"].fillna(0.0) * gate
    P["Signal_rank"] = P["Signal"].where(P["Signal"] > 0)
    if not quiet:
        n_live = int((P["Signal"] > 0).sum())
        LOG.ok(f"신호 산출[{band_col}] — 발화 {n_live:,}행 / 전체 {len(P):,}행 "
               f"(국면C {int(P['PHASE_C'].sum()):,} × 방화벽 {int(P['FIREWALL'].sum()):,} × "
               f"거부권통과 {int(P['VETO'].sum()):,} × 밴드 "
               f"{int(P[band_col].sum()) if band_col in P.columns else 0:,})")
    return P


# ── 강건성·비교군용 경량 패널 ───────────────────────────────────────────────────────────
SLIM_COLS = (["code", "wk", "signal_date", "exec_px", "fwd_ret", "adv20", "mcap", "size_est",
              "E", "E_rank", "Signal", "Signal_rank",
              "cell", "cell_l2", "cell_l3", "phase", "PHASE_A", "PHASE_B", "PHASE_C",
              "FIREWALL", "FIREWALL_HARD", "VETO", "V1", "V3", "V_RS", "in_band",
              "in_band_small", "V6", "stale_days", "mcap_rank", "small_rank", "equity"]
             + SENSOR_COLS + TP_COLS)


def slim_panel(P: pd.DataFrame) -> pd.DataFrame:
    """강건성 스위트는 같은 패널을 20여 회 복사한다. 40열 전체를 복사하면 그 자체가
    수 GB·수십 초의 낭비다 — 백테스트와 재점수화에 실제로 필요한 열만 남긴다."""
    cols = [c for c in dict.fromkeys(SLIM_COLS) if c in P.columns]
    out = P[cols].copy()
    return out
