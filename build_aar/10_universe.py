

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  marcap 로더 · PIT 유니버스 · PIT 시가총액 · 수정주가   (KRX 인증 완전 배제)         ║
# ║                                                                                          ║
# ║  ★★ 이 모듈이 이 프로젝트에서 가장 큰 시간 절약을 만든다. ★★                              ║
# ║                                                                                          ║
# ║  종전: 종목당 HTTP 1회 × 3,500종목 × 폴백체인 = 수천~수만 요청, 완전 캐시 상태에서도       ║
# ║        판단에만 13~15분.                                                                  ║
# ║  현재: **연도당 parquet 1개 × 11개 = 총 11회 다운로드로 전 종목·전 기간(1995~2026).**      ║
# ║        그마저 HTTP 캐시에 남아 두 번째 실행부터는 네트워크 0회다.                          ║
# ║                                                                                          ║
# ║  소스: FinanceData/marcap (raw.githubusercontent, 인증 불필요)                             ║
# ║    Date, Code, Name, Market, Dept, Close, ChangesRatio, Marcap, Stocks, Amount, Volume    ║
# ║                                                                                          ║
# ║  이 한 소스가 동시에 해결하는 것:                                                          ║
# ║   · PIT 유니버스   — 날짜별 단면이라 그날 실제 거래된 종목만 들어 있다                     ║
# ║   · 생존자편향     — 폐지 종목이 폐지일까지 존재하다 사라진다. **구조적으로 제거됨**       ║
# ║   · PIT 시가총액   — Marcap 컬럼이 이미 PIT 값 (Marcap == Close × Stocks, 오차 0 검증)     ║
# ║   · 상장주식수     — Stocks. 별도 시계열 재구성이 불필요                                   ║
# ║   · 실거래대금     — Amount (KRX 실측). close×volume 근사가 필요 없다                     ║
# ║   · 수정주가       — ChangesRatio 가 KRX 공식 수정등락률                                   ║
# ║                                                                                          ║
# ║  ⚠ Close 는 **무수정 원주가**다. 삼성전자 2018-05-04 50:1 분할일의 raw pct_change 는       ║
# ║    -98.04% 이고 ChangesRatio 는 -2.08% 다. 수익률에 Close 비율이나 Marcap 비율을           ║
# ║    쓰면 안 된다(§7-F1). Marcap 비율에는 주식수 변동이 섞여 유상증자일에 +1.75%/일의        ║
# ║    상방 편의가 생긴다. Marcap 은 **랭킹 전용**이다.                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MARCAP_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet"
MARCAP_COLS = ["Date", "Code", "Name", "Market", "Dept", "Close", "ChangesRatio",
               "Marcap", "Stocks", "Amount", "Volume"]
FDR_LIST_URL = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                "refs/heads/master/data/{kind}/{date}.csv")

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "industry", "sector", "delist_reason", "delist_to", "src"]
CA_TOL = 2e-3          # ChangesRatio 는 소수 2자리 반올림 → 이보다 작은 차이는 반올림 잡음
CA_MAX_GAP_D = 7       # 연 경계·장기 거래정지 구간은 코퍼레이트액션 판정에서 제외


def _fdr_recent_csv(kind: str, back_days: int = 21) -> Optional["pd.DataFrame"]:
    """fdr_krx_data_cache 의 최신 CSV. delisting/desc 는 롤링이 아니라 매일 전량 갱신된다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        raw = http_get(FDR_LIST_URL.format(kind=kind, date=d.isoformat()), source="github",
                       as_bytes=True, tries=1, timeout=30, params={"_d": d.isoformat()})
        if not raw or len(raw) < 500:
            continue
        head = raw[:60].lstrip()
        if head.startswith(b"404") or head.startswith(b"<"):
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR 캐시 적중: {kind} @ {d.isoformat()} ({len(df):,}행)")
                return df
        except Exception:
            continue
    return None


# ── marcap 로더 ─────────────────────────────────────────────────────────────────────────────
def load_marcap(y0: int, y1: int) -> "pd.DataFrame":
    """연도별 parquet 을 **연속으로** 적재한다.

    ★ 연도 결손을 허용하면 안 된다. 2016 과 2018 을 이어붙이면 2018-01-02 의 pct_change 가
      2016-12-29 종가와 비교되어 존재하지 않는 코퍼레이트액션 계수가 만들어진다
      (실측: 삼성전자에 f=0.707 이라는 유령 계수 발생). 그래서 KillCriteria 로 세운다."""
    frames = []
    for y in range(y0, y1 + 1):
        b = http_get(MARCAP_URL.format(y=y), source="github", as_bytes=True, tries=3,
                     timeout=180, params={"_y": str(y)}, cache_ttl_days=(0.0 if y < _dt.date.today().year else 2.0))
        if b is None or len(b) < 1000:
            raise KillCriteria(
                f"marcap-{y}.parquet 을 받지 못했습니다. 연도 결손은 허용하지 않습니다 — "
                f"불연속 구간을 이어붙이면 가짜 코퍼레이트액션이 생겨 수익률이 조용히 "
                f"왜곡됩니다(§7-F2). 네트워크에서 raw.githubusercontent.com 접근을 확인하세요.")
        try:
            d = pd.read_parquet(io.BytesIO(b), columns=MARCAP_COLS)
        except Exception:
            d = pd.read_parquet(io.BytesIO(b))
            d = d[[c for c in MARCAP_COLS if c in d.columns]]
        frames.append(d)
        LOG.debug(f"  marcap-{y}: {len(d):,}행")
    m = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    m["Date"] = as_ts_series(m["Date"])
    m["Code"] = as_str_series(m["Code"]).str.zfill(6)
    for c in ("Market", "Dept", "Name"):
        if c in m.columns:
            m[c] = as_str_series(m[c])
    # ★ Marcap 은 조 단위라 float32 로 낮추면 유효자릿수가 깨진다. float64 유지.
    for c in ("Close", "ChangesRatio", "Marcap", "Stocks", "Amount", "Volume"):
        if c in m.columns:
            m[c] = pd.to_numeric(m[c], errors="coerce").astype("float64")
    m = m.dropna(subset=["Date", "Code", "Close"])
    m = m.sort_values(["Code", "Date"], kind="stable").reset_index(drop=True)

    lag_d = (pd.Timestamp.today().normalize() - m["Date"].max()).days
    if lag_d > 5:
        LOG.warn(f"marcap 최종 데이터일이 {lag_d}일 뒤처집니다({m['Date'].max():%Y-%m-%d}) — "
                 f"저장소 유지보수자 측 지연입니다. 과거분 parquet 은 확정 커밋이라 "
                 f"백테스트 재현성에는 영향이 없고, 위험은 최근 구간에 국한됩니다.")
    if lag_d > 25:
        LOG.error(f"marcap 신선도 위반({lag_d}일). 최근 구간 결과를 신뢰하지 마십시오.")
    LOG.ok(f"marcap 적재 {len(m):,}행 · {m['Code'].nunique():,}종목 · "
           f"{m['Date'].min():%Y-%m-%d}~{m['Date'].max():%Y-%m-%d} · {mem_mb(m):.0f}MB")
    PIPE.io("IN", "HTTP", "marcap", m, source="FinanceData/marcap")
    return m


def add_adjusted_close(m: "pd.DataFrame") -> "pd.DataFrame":
    """ChangesRatio 로 역수정 종가를 복원한다.

      f_t       = (1 + ChangesRatio_t/100) / (Close_t / Close_{t-1})     조정계수
      adj_t     = Close_t / Π_{u > t} f_u                                 역수정(back-adjust)

    ★ 방향 주의: **나눈다.** 곱하면 삼성전자 2016-01-04 이 24,101 대신 42,609,078 이 된다.
    ★ 3중 가드가 전부 필요하다: 이전값 존재 · 날짜 간격 ≤7일 · |f-1| > 반올림 잡음.
      하나라도 빠지면 연 경계나 반올림이 유령 계수를 만든다.
    """
    m = m.sort_values(["Code", "Date"], kind="stable").reset_index(drop=True)
    g = m.groupby("Code", observed=True, sort=False)
    prev = g["Close"].shift(1)
    gap_d = (m["Date"] - g["Date"].shift(1)).dt.days

    p = m["Close"] / prev.where(prev > 0)
    q = 1.0 + m["ChangesRatio"] / 100.0
    f = q / p.where(p > 0)
    ok = (prev.notna() & (prev > 0) & m["ChangesRatio"].notna()
          & gap_d.notna() & (gap_d <= CA_MAX_GAP_D)
          & f.notna() & ((f - 1.0).abs() > CA_TOL) & (f > 0.01) & (f < 100.0))
    m["_f"] = np.where(ok.to_numpy(), f.to_numpy(), 1.0)

    rev = m.iloc[::-1]
    revcum = rev.groupby("Code", observed=True, sort=False)["_f"].cumprod()
    m["_revcum"] = revcum.reindex(m.index)
    fwd = m["_revcum"] / m["_f"]                    # u > t 구간만 (자기 자신 제외)
    m["adj_close"] = m["Close"] / fwd.where(fwd > 0)
    m["ca_flag"] = ok.to_numpy()
    n_ca = int(ok.sum())
    LOG.info(f"코퍼레이트액션 감지 {n_ca:,}건 / {len(m):,} 종목일 "
             f"({100*n_ca/max(len(m),1):.3f}%) — 통상 0.05% 수준이면 정상입니다.")

    # 검산: 알려진 사례로 방향과 크기를 확인한다(로그에 남긴다).
    try:
        s = m[(m["Code"] == "005930")]
        if len(s):
            first = s.iloc[0]
            LOG.info(f"  역수정 검산 삼성전자 {first['Date']:%Y-%m-%d}: "
                     f"원종가 {first['Close']:,.0f} → 역수정 {first['adj_close']:,.1f} "
                     f"(2018년 50:1 분할 반영. 2016-01-04 기준 이론값 ≈ 24,100)")
    except Exception:
        pass
    return m.drop(columns=["_f", "_revcum"])


def _is_common_stock(code: "pd.Series", name: "pd.Series", dept: "pd.Series") -> "pd.Series":
    """보통주만 남긴다.

    ★ 우선주 판정은 **종목코드 끝자리** 로 한다. 이름의 '우' 포함으로 판정하면
      '대우', '우리' 가 오탐된다(실측 오탐 172 vs 정탐 118)."""
    c = as_str_series(code)
    ok = c.str.len().eq(6) & c.str[-1].eq("0")
    ok &= ~as_str_series(name).str.contains("스팩", na=False)
    ok &= ~as_str_series(dept).str.contains("SPAC", na=False, case=False)
    return ok


def fetch_delisting_master() -> "pd.DataFrame":
    """전체 상장폐지 이력 마스터 (1956~). 폐지 수익률의 '승계 vs 전손' 판정에 필수.

    ★ 무조건 결측 처리 → 손실 누락(상방 편향). 무조건 -100% → 피흡수합병 주주까지
      전손 처리(하방 편향). Reason/ToSymbol 로 반드시 분기한다(§2.5)."""
    cols = ["code", "name", "delisting_date", "listing_date", "market",
            "secugroup", "reason", "to_symbol"]
    d = _fdr_recent_csv("listing/delisting")
    if d is None or d.empty:
        LOG.error("상장폐지 마스터를 받지 못했습니다. marcap 단면이 생존자편향을 이미 제거하므로 "
                  "유니버스는 정확하지만, 폐지 종목의 최종 수익률을 '승계'와 '전손'으로 "
                  "가를 수 없어 보수적으로 전부 결측 처리합니다.")
        return pd.DataFrame(columns=cols)
    lm = {str(c).strip().lower(): c for c in d.columns}
    gc_ = lambda *ks: next((lm[k] for k in ks if k in lm), None)
    code_c = gc_("symbol", "code", "isu_srt_cd")
    if not code_c:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "code": as_str_series(d[code_c]).map(to_code6),
        "name": as_str_series(d[gc_("name") or code_c]),
        "delisting_date": as_ts_series(d[gc_("delistingdate", "delisting_date")]) if gc_("delistingdate", "delisting_date") else pd.NaT,
        "listing_date": as_ts_series(d[gc_("listingdate", "listing_date")]) if gc_("listingdate", "listing_date") else pd.NaT,
        "market": as_str_series(d[gc_("market")]).str.upper() if gc_("market") else "",
        "secugroup": as_str_series(d[gc_("secugroup", "kind")]) if gc_("secugroup", "kind") else "",
        "reason": as_str_series(d[gc_("reason")]) if gc_("reason") else "",
        "to_symbol": as_str_series(d[gc_("tosymbol")]).map(to_code6) if gc_("tosymbol") else None,
    }).dropna(subset=["code"])
    out = out.sort_values("delisting_date").drop_duplicates("code", keep="last")
    LOG.ok(f"상장폐지 마스터 {len(out):,}건 (폐지일 보유 {int(out['delisting_date'].notna().sum()):,} · "
           f"승계종목 지정 {int(out['to_symbol'].notna().sum()):,})")
    VAULT.put_table("krx_delisting_master", out, scope="shared", domain="universe",
                    source="fdr_krx_data_cache listing/delisting")
    return out


SUCCEED_PAT = re.compile(r"(합병|포괄적\s*주식교환|주식의\s*포괄적|지주회사|완전자회사)")


def classify_delisting(dl: "pd.DataFrame") -> Dict[str, str]:
    """code → 'SUCCEED' | 'WIPEOUT' | 'UNKNOWN'."""
    if dl is None or dl.empty:
        return {}
    out: Dict[str, str] = {}
    for r in dl.itertuples(index=False):
        if isinstance(getattr(r, "to_symbol", None), str) and r.to_symbol:
            out[r.code] = "SUCCEED"
        elif SUCCEED_PAT.search(str(getattr(r, "reason", "") or "")):
            out[r.code] = "SUCCEED"
        else:
            out[r.code] = "WIPEOUT"
    return out


def fetch_listing_desc() -> "pd.DataFrame":
    """상장일·업종 마스터. KIND 를 완전히 대체한다(커버리지 100% 실측)."""
    d = _fdr_recent_csv("listing/desc")
    if d is None or d.empty:
        LOG.info("listing/desc 를 받지 못했습니다 — 상장일은 marcap 최초 관측일로 대체합니다"
                 "(그 경우 시즈닝이 보수적으로 늦어질 뿐 미래누수는 없습니다).")
        return pd.DataFrame(columns=["code", "listing_date", "sector", "industry"])
    lm = {str(c).strip().lower(): c for c in d.columns}
    gc_ = lambda *ks: next((lm[k] for k in ks if k in lm), None)
    code_c = gc_("code", "symbol")
    if not code_c:
        return pd.DataFrame(columns=["code", "listing_date", "sector", "industry"])
    out = pd.DataFrame({
        "code": as_str_series(d[code_c]).map(to_code6),
        "listing_date": as_ts_series(d[gc_("listingdate")]) if gc_("listingdate") else pd.NaT,
        "sector": as_str_series(d[gc_("sector")]) if gc_("sector") else "",
        "industry": as_str_series(d[gc_("industry")]) if gc_("industry") else "",
    }).dropna(subset=["code"]).drop_duplicates("code")
    LOG.ok(f"상장정보(desc) {len(out):,}건 (상장일 {int(out['listing_date'].notna().sum()):,})")
    return out


# ── 통합 빌더 (메모 캐시) ───────────────────────────────────────────────────────────────────
def build_market_data(y0: int, y1: int) -> Dict[str, "pd.DataFrame"]:
    """marcap → (월말 단면, 일별 수익률, 종목 마스터). 무거운 파싱은 최초 1회뿐이다.

    반환:
      monthly : code, month, date, adj_close, marcap, stocks, amount, adv20, market, dept
      daily   : code, date, ret (ChangesRatio/100 = KRX 공식 수정등락률)
      sec     : 종목 마스터 (상장일/폐지일/업종/폐지사유)
    """
    fp = fingerprint_of("marketdata", y0, y1, "v3", BACKTEST_START, BACKTEST_END)

    def _build() -> "pd.DataFrame":
        m = load_marcap(y0, y1)
        m = add_adjusted_close(m)
        return m

    # 원본 전체를 메모에 담으면 수백 MB 라 오히려 느리다. 파생 3종만 각각 메모한다.
    m: Optional["pd.DataFrame"] = None

    def _need_raw():
        nonlocal m
        if m is None:
            m = _build()
        return m

    def _mk_daily() -> "pd.DataFrame":
        mm = _need_raw()
        d = pd.DataFrame({
            "code": mm["Code"], "date": mm["Date"],
            "ret": (mm["ChangesRatio"] / 100.0).astype("float32"),
            "adj_close": mm["adj_close"].astype("float64"),
            "amount": mm["Amount"].astype("float64"),
        })
        # 정리매매·오류틱 방어: ±60% 초과 일간 수익은 결측 처리(가격제한은 ±30%)
        d.loc[d["ret"].abs() > 0.60, "ret"] = np.nan
        return d

    def _mk_monthly() -> "pd.DataFrame":
        mm = _need_raw()
        x = mm[["Code", "Date", "adj_close", "Close", "Marcap", "Stocks", "Amount",
                "Volume", "Market", "Dept", "Name"]].copy()
        x = x.sort_values(["Code", "Date"], kind="stable")
        x["adv20"] = (x.groupby("Code", observed=True)["Amount"]
                       .transform(lambda s: s.rolling(20, min_periods=10).mean()))
        x["ym"] = x["Date"].values.astype("datetime64[M]")
        last = x.groupby(["Code", "ym"], observed=True).tail(1).copy()
        last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)
        # 익영업일 종가 = 체결가 (§7 — 신호 산출일 익영업일 앵커)
        nx = x[["Code", "Date", "adj_close"]].copy()
        nx["next_close"] = nx.groupby("Code", observed=True)["adj_close"].shift(-1)
        nx["next_date"] = nx.groupby("Code", observed=True)["Date"].shift(-1)
        last = last.merge(nx[["Code", "Date", "next_close", "next_date"]],
                          on=["Code", "Date"], how="left")
        out = last.rename(columns={"Code": "code", "Date": "signal_date", "Marcap": "marcap",
                                   "Stocks": "stocks", "Amount": "amount", "Volume": "volume",
                                   "Market": "market", "Dept": "dept", "Name": "name"})
        return out[["code", "month", "signal_date", "adj_close", "Close", "next_close",
                    "next_date", "marcap", "stocks", "amount", "volume", "adv20",
                    "market", "dept", "name"]]

    daily = VAULT.memo_table("marcap_daily", fingerprint_of(fp, "daily"), _mk_daily,
                             scope="shared", domain="price", note="일별 수정수익률")
    monthly = VAULT.memo_table("marcap_monthly", fingerprint_of(fp, "monthly"), _mk_monthly,
                               scope="shared", domain="price", note="월말 단면")
    for df, c in ((daily, "date"), (monthly, "month")):
        if df is not None and len(df):
            df[c] = as_ts_series(df[c])
    if "signal_date" in monthly.columns:
        monthly["signal_date"] = as_ts_series(monthly["signal_date"])
        monthly["next_date"] = as_ts_series(monthly["next_date"])
    daily["code"] = as_str_series(daily["code"])
    monthly["code"] = as_str_series(monthly["code"])

    # ── 종목 마스터 ────────────────────────────────────────────────────────────────────
    def _mk_sec() -> "pd.DataFrame":
        obs = monthly.groupby("code", observed=True).agg(
            name=("name", "last"), market=("market", "last"), dept=("dept", "last"),
            first_obs=("month", "min"), last_obs=("month", "max"))
        obs = obs.reset_index()
        desc = fetch_listing_desc()
        dl = fetch_delisting_master()
        s = obs.merge(desc, on="code", how="left")
        s = s.merge(dl[["code", "delisting_date", "reason", "to_symbol", "secugroup"]],
                    on="code", how="left")
        s["listing_date_src"] = np.where(s["listing_date"].notna(), "desc", "marcap최초관측")
        s["listing_date"] = s["listing_date"].fillna(s["first_obs"])
        # 폐지일이 명단에 없는데 관측이 끊긴 종목 → 마지막 관측월 말일을 폐지로 추정
        last_all = monthly["month"].max()
        gone = s["delisting_date"].isna() & (s["last_obs"] < last_all - pd.offsets.MonthEnd(2))
        s.loc[gone, "delisting_date"] = s.loc[gone, "last_obs"] + pd.offsets.MonthEnd(1)
        s.loc[gone, "reason"] = s.loc[gone, "reason"].fillna("관측중단(추정)")
        s["industry"] = as_str_series(s.get("industry", "")).replace("", "미분류")
        # ★ Series.replace("", other_series) 는 pandas 가 거부한다(스칼라→Series 치환 불가).
        #   where 로 조건 치환해야 한다.
        _sec = as_str_series(s.get("sector", ""))
        s["sector"] = _sec.where(_sec.str.strip() != "", s["industry"]).replace("", "미분류")
        s["delist_reason"] = as_str_series(s.get("reason", ""))
        s["delist_to"] = s.get("to_symbol")
        s["src"] = "marcap+desc+delisting"
        return s

    sec = VAULT.memo_table("security_master_aar", fingerprint_of(fp, "sec"), _mk_sec,
                           scope="shared", domain="universe", note="종목 마스터")
    for c in ("listing_date", "delisting_date", "first_obs", "last_obs"):
        if c in sec.columns:
            sec[c] = as_ts_series(sec[c])
    sec["code"] = as_str_series(sec["code"])

    n_del = int(sec["delisting_date"].notna().sum())
    LOG.table([["일별 관측", f"{len(daily):,}"],
               ["월말 단면", f"{len(monthly):,}"],
               ["고유 종목", f"{len(sec):,}"],
               ["폐지 이력 보유", f"{n_del:,} ({100*n_del/max(len(sec),1):.1f}%)"],
               ["시총 보유 월행", f"{int(monthly['marcap'].notna().sum()):,}"],
               ["실거래대금 보유", f"{int(monthly['amount'].notna().sum()):,}"]],
              ["항목", "값"], ["l", "r"], title="marcap 기반 시장 데이터 (KRX 인증 없이)")
    if n_del < 1000:
        LOG.warn(f"폐지 이력이 {n_del:,}건으로 예상(≈4,000)보다 적습니다. "
                 f"★ 이 전략은 특히 위험합니다 — 커버리지 철회 신호가 폐지 직전 종목에 "
                 f"집중되므로 폐지 종목이 빠지면 H3(음의 신호)가 통째로 사라집니다.")
    m = None
    gc.collect()
    return {"daily": daily, "monthly": monthly, "sec": sec}


# ── PIT 유니버스 ────────────────────────────────────────────────────────────────────────────
def build_pit_universe(monthly: "pd.DataFrame", months: "pd.DatetimeIndex") -> "pd.DataFrame":
    """월별 PIT 유니버스 + 재랭킹.

    ★ marcap 의 Rank 컬럼을 그대로 쓰면 안 된다. KONEX·우선주·신주인수권이 섞여 있어
      '시총 하위 1000' 이 우선주와 KONEX 로 오염된다(실측: 2016-08-31 최하위 Rank 가 KONEX).
      반드시 필터한 뒤 **재랭킹**한다."""
    u = monthly[monthly["month"].isin(months)].copy()
    n0 = len(u)
    u = u[as_str_series(u["market"]).str.upper().isin(["KOSPI", "KOSDAQ"])]
    n1 = len(u)
    u = u[_is_common_stock(u["code"], u["name"], u["dept"])]
    n2 = len(u)
    u = u[pd.to_numeric(u["marcap"], errors="coerce") > 0]
    n3 = len(u)
    u["size_rank"] = (u.groupby("month", observed=True)["marcap"]
                       .rank(method="first", ascending=True))
    u["size_pct"] = (u.groupby("month", observed=True)["marcap"]
                      .rank(pct=True, ascending=True).astype("float32"))
    u["n_month"] = u.groupby("month", observed=True)["code"].transform("size")
    LOG.table([["월행 원본", f"{n0:,}", ""],
               ["KOSPI/KOSDAQ (KONEX 제외)", f"{n1:,}", f"{100*n1/max(n0,1):.1f}%"],
               ["보통주 (우선주·스팩 제외)", f"{n2:,}", f"{100*n2/max(n1,1):.1f}%"],
               ["시총 > 0", f"{n3:,}", f"{100*n3/max(n2,1):.1f}%"],
               ["월평균 종목수", f"{u.groupby('month')['code'].size().mean():,.0f}", ""]],
              ["필터 단계", "잔존 월행", "직전 대비"], ["l", "r", "r"],
              title="PIT 유니버스 필터 체인 (필터 후 재랭킹 — marcap 의 Rank 는 쓰지 않음)")
    PIPE.io("OUT", "MEM", "pit_universe", u)
    return u


def apply_universe_variant(uni: "pd.DataFrame", variant: str) -> "pd.DataFrame":
    """FULL = PIT 전체 / SMALL1000 = 시총 하위 SMALLCAP_N (오름차순 rank ≤ N)."""
    if variant == "SMALL1000":
        out = uni[uni["size_rank"] <= SMALLCAP_N].copy()
        sz = out.groupby("month", observed=True)["code"].size()
        LOG.info(f"[SMALL1000] 시총 하위 {SMALLCAP_N:,} 압축 — 월별 종목수 "
                 f"min {int(sz.min()):,} / median {int(sz.median()):,} / max {int(sz.max()):,}")
        return out
    return uni.copy()


# ── PIT 저장소 ──────────────────────────────────────────────────────────────────────────────
class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, "pd.DataFrame"] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: "pd.DataFrame", key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[PIT 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        self._t[name] = d.reset_index(drop=True)
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def names(self) -> List[str]:
        return sorted(self._t)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> "pd.DataFrame":
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        d = self._t[name]
        if d.empty:
            return d
        pos = int(np.searchsorted(d["knowledge_date"].values,
                                  np.datetime64(as_ts(as_of)), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def report(self):
        rows = [[n, f"{m['rows']:,}", str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                 ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n, 0):,}"]
                for n, m in self._meta.items()]
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()

LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    """월별 유니버스 조회 + 감쇠 감사.

    marcap 단면이 이미 '그날 실제 거래된 종목'이므로 상장/폐지 판정은 관측 자체가 근거다.
    상장일 시즈닝만 추가로 적용한다."""

    def __init__(self, uni_month: "pd.DataFrame", sec: "pd.DataFrame"):
        self.attrition: List[dict] = []
        self._by_month: Dict["pd.Timestamp", List[str]] = {}
        for m, g in uni_month.groupby("month", observed=True):
            self._by_month[as_ts(m)] = sorted(as_str_series(g["code"]).tolist())
        s = sec.drop_duplicates("code")
        self._listing = dict(zip(as_str_series(s["code"]), as_ts_series(s["listing_date"])))
        self._delist = {c: d for c, d in zip(as_str_series(s["code"]),
                                             as_ts_series(s["delisting_date"])) if pd.notna(d)}
        # ★ 시즈닝 앵커는 '상장일'이다. 패널 시작일을 앵커로 잡으면 기존 상장사 전부가
        #   백테스트 첫 1년 동안 유니버스에서 사라진다 — 에러도 경고도 없이.
        self._seasoned = {c: (ld + pd.Timedelta(days=365)) if pd.notna(ld) else pd.NaT
                          for c, ld in self._listing.items()}

    def at(self, t) -> List[str]:
        t = as_ts(t)
        base = self._by_month.get(t, [])
        return [c for c in base
                if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]

    def delisting_map(self) -> Dict[str, "pd.Timestamp"]:
        return dict(self._delist)

    def audit_row(self, stage: str, t, codes):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["PIT유니버스", "시즈닝통과", "유동성필터", "신호보유(U)", "Q5선정",
                 "배제후최종"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max"])
        rows, prev = [], None
        for s in order:
            if s not in piv.index:
                continue
            r = piv.loc[s]
            keep = "" if prev is None else f"{100*r['mean']/max(prev,1e-9):.1f}%"
            rows.append([s, f"{r['mean']:,.0f}", f"{r['min']:,.0f}", f"{r['max']:,.0f}", keep])
            prev = r["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < PORT_MIN_NAMES:
            LOG.warn(f"최종 보유가 월평균 {rows[-1][1]}종목으로 하한({PORT_MIN_NAMES})에 미달합니다. "
                     f"임계값을 손대기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")
