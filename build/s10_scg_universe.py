

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  PIT 유니버스 — KRX 를 한 번도 호출하지 않고 생존자편향을 제거한다                    ║
# ║                                                                                          ║
# ║  ★ KRX 금지는 '안 쓰기로 했다'가 아니라 '코드 경로가 없다'로 구현한다.                       ║
# ║    이 파일에는 data.krx.co.kr / kind.krx.co.kr / pykrx 호출이 한 줄도 없다.                 ║
# ║    RATE_LIMIT_QPS["krx"] = 0.0 이라 실수로 부르면 즉시 막힌다.                              ║
# ║                                                                                          ║
# ║  유니버스가 PIT 인 근거 (생존자편향 제거의 3중 방어):                                       ║
# ║    ① 상장일  — FDR GitHub 캐시(listing/krx) + 최초 체결일                                  ║
# ║    ② 폐지일  — FDR GitHub 캐시(listing/delisting). KRX 없이 유일한 공개 경로.               ║
# ║    ③ 관측기반 폐지 추정 — 시장은 계속 거래되는데 이 종목만 시계열이 끊기면 폐지다.           ║
# ║       ②가 놓친 종목을 ③이 줍는다. 두 경로가 겹치는 정도를 매 실행 표로 낸다.                 ║
# ║                                                                                          ║
# ║    시점 t 의 유니버스 = listing_date <= t < delisting_date                                 ║
# ║    → 지금 없어진 회사도 그 시절엔 들어 있다. 그것이 생존자편향 제거의 정의다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_SEC_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                "corp_code", "industry", "src", "delist_src"]

_SCG_FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                  "refs/heads/master/data/{kind}/{date}.csv")

#  보통주가 아닌 종목(우선주·신주인수권 등)은 6번째 자리가 '0' 이 아니다. 시점 불변 규칙이라
#  미래정보가 섞이지 않는다. ETF/ETN/스팩은 이름/구분으로 추가 배제한다.
_SCG_NONEQUITY_NAME = re.compile(
    r"스팩|기업인수목적|제\d+호|리츠|ETN|ETF|상장지수|인프라투融|맥쿼리인프라|"
    r"신주인수권|워런트|WR\b", re.I)


def _scg_lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def _scg_fdr_cache_csv(kind: str, back_days: int = 21) -> Optional[pd.DataFrame]:
    """FinanceDataReader 의 GitHub 캐시를 직접 읽는다 (KRX 인증과 무관).

    ★ FDR 라이브러리 자체(fdr.StockListing)는 최신 영업일 확인차 data.krx.co.kr 를
      찌르므로 이 전략에서는 절대 쓰지 않는다. CSV 만 직접 가져온다.
    ★ index_col=0 을 무조건 주면 안 된다: delisting CSV 는 인덱스 컬럼이 없어서
      첫 실컬럼(Symbol=종목코드)이 인덱스로 먹히고 폐지종목이 통째로 사라진다 = 생존자편향.
    """
    ck = f"fdr_cache_{kind.replace('/', '_')}"
    cached = VAULT.get_table(ck, scope="shared", max_age_days=7)
    if cached is not None and len(cached):
        LOG.debug(f"FDR 캐시 테이블 재사용: {ck} ({len(cached):,}행)")
        return cached
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        raw = http_get(_SCG_FDR_CACHE.format(kind=kind, date=d.isoformat()),
                       source="fdr", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} ({len(df):,}행)")
                VAULT.put_table(ck, df, scope="shared", domain="universe",
                                source=f"fdr_github_cache/{kind}")
                return df
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
#  ★ 1순위 PIT 스파인 — FinanceData/marcap (일별 전종목시세)
#
#  이것이 이 전략의 유니버스·시가총액 문제를 통째로 해결한다.
#    · 연도별 parquet 하나에 그날 상장돼 있던 **모든** 종목의 행이 들어 있다.
#      → "그날 행이 있다 = 그날 상장돼 있었다". 생존자편향이 정의상 불가능하다.
#      → 폐지 종목도 마지막 거래일까지 그대로 들어 있다.
#    · Close 는 **무수정** 종가, Stocks 는 그날의 상장주식수, Marcap 은 그 둘의 곱이다.
#      → PIT 시가총액을 DART 주식총수 없이 바로 얻는다 (호출 12,000회 절약).
#    · 거래일 캘린더도 여기서 나온다 (KRX 휴장일 API 불필요).
#
#  접근 경로는 raw.githubusercontent.com 이다 — data.krx.co.kr 을 거치지 않는다.
#  (원 데이터의 출처는 KRX 공시자료이며, 이 코드베이스가 이미 fdr_krx_data_cache 에
#   대해 취하고 있는 것과 같은 태도다. 접근이 아니라 계보를 문제 삼는 금지였다면
#   MARCAP_ENABLED=False 로 끄면 아래의 상장/폐지목록 경로로 자동 폴백한다)
#
#  ⚠ FinanceData/marcap 패키지의 marcap_data() 헬퍼는 마지막에 Volume>0 으로 거르는데,
#    그러면 거래정지 종목이 통째로 사라진다. 우리는 parquet 을 직접 읽어 그 필터를 피한다.
# ══════════════════════════════════════════════════════════════════════════════════════

MARCAP_ENABLED = True
_MARCAP_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet"

#  ★ parquet 에서 **읽을 컬럼만** 지정한다. 이게 이 파일에서 가장 중요한 한 줄이다.
#    전체 18컬럼을 읽으면 1년치가 274MB 이고 그중 222MB 가 쓰지도 않는 object 컬럼
#    (Name 48.7 · Dept 42.9 · Code 33.9 · Market 33.6 · MarketId 32.3 · ChangeCode 31.2 MB)이다.
#    16년을 concat 하면 4.4GB, pd.concat 피크는 그 두 배 — 실제로 여기서 30분 정체가 났다.
_MARCAP_READ = ["Date", "Code", "Name", "Close", "ChangesRatio", "Amount",
                "Marcap", "Stocks", "Market"]
#  슬림 스파인 스키마. 9M행 기준 약 270MB (원본 4.4GB 대비 1/16).
SPINE_COLS = ["code", "date", "close_unadj", "ret_adj", "amount", "marketcap", "shares"]
SPINE_TABLE = "marcap_spine_{y}"        # 공용 인덱스 — 다른 전략도 그대로 재사용


def _scg_slim_marcap(d: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """원본 연도 프레임 → (슬림 스파인, 종목메타). 원본은 즉시 버린다.

    ★ 메타를 DataFrame.attrs 에 실어 보내지 않는다. attrs 에 DataFrame 을 넣으면
      pd.concat 이 attrs 동일성 검사에서 DataFrame == DataFrame 를 평가하다 ValueError 로
      죽고, parquet 저장도 TypeError 가 난다. (실제로 두 곳 다 터졌다)
    """
    cm = {str(c).strip().lower(): c for c in d.columns}
    need = ("code", "date", "close", "marcap", "stocks")
    if not all(k in cm for k in need):
        return pd.DataFrame(columns=SPINE_COLS), pd.DataFrame(columns=["code", "name", "market"])
    out = pd.DataFrame({
        "code": d[cm["code"]].astype(str).str.zfill(6),
        "date": pd.to_datetime(d[cm["date"]], errors="coerce").astype("datetime64[ns]"),
        "close_unadj": pd.to_numeric(d[cm["close"]], errors="coerce").astype("float32"),
        #  ★ ChangesRatio 는 KRX 기준가 기반 등락률이라 액면분할·유무상증자가 이미 보정돼 있다.
        #    (삼성전자 2018-05-04 분할일: 종가 pct_change 는 -98.04% 인데 ChangesRatio 는 -2.08%)
        #    → 이 한 컬럼으로 수정주가 계열을 만들 수 있어 종목별 가격 재수집이 통째로 불필요해진다.
        #    단 현금배당은 반영되지 않는다(가격수익률이지 총수익률이 아니다). 명시해 둔다.
        "ret_adj": (pd.to_numeric(d[cm["changesratio"]], errors="coerce").astype("float32") / 100.0
                    if "changesratio" in cm else np.float32(np.nan)),
        "amount": (pd.to_numeric(d[cm["amount"]], errors="coerce").astype("float32")
                   if "amount" in cm else np.float32(np.nan)),
        "marketcap": pd.to_numeric(d[cm["marcap"]], errors="coerce").astype("float64"),
        "shares": pd.to_numeric(d[cm["stocks"]], errors="coerce").astype("float64"),
    })
    #  종목명/시장은 마스터를 만들 때만 필요하므로 (code → 값) 한 줄짜리 사전으로 따로 뺀다.
    #  이것만 빼도 연도당 115MB(Name 48.7 + Market 33.6 + MarketId 32.3)가 사라진다.
    meta = pd.DataFrame({
        "code": out["code"],
        "name": d[cm["name"]].astype(str) if "name" in cm else "",
        "market": d[cm["market"]].astype(str) if "market" in cm else "KRX",
    }).drop_duplicates("code", keep="last").reset_index(drop=True)
    return out.dropna(subset=["code", "date"]).reset_index(drop=True), meta


def scg_fetch_spine(years: Sequence[int]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """★ 이 전략의 단일 데이터 스파인 — 일별 전종목시세.

    여기서 나오는 것: 거래일 캘린더 · PIT 유니버스 · 수정주가(수익률) · 무수정 종가 ·
    PIT 시가총액 · 상장주식수 · 거래대금. 전부 한 소스에서 나오므로 종목별 가격 재수집이
    **한 건도** 필요 없다(이전 구조는 여기서 2,800회를 더 긁었다).

    ★ 접근 경로는 raw.githubusercontent.com 이다 — data.krx.co.kr 을 거치지 않는다.
      (원 데이터 계보는 KRX 공시자료다. 계보 자체가 금지 대상이라면 MARCAP_ENABLED=False
       로 끄면 상장/폐지목록 + 종목별 가격수집 경로로 자동 폴백한다)

    ★ 메모리: 연도별로 받아 **즉시 슬림화**하고 원본을 버린다. 원본을 다 모으면 4.4GB 이고
      그게 이전 실행이 30분간 멈춘 이유다. 슬림 스파인은 9M행에 약 270MB 다.
    """
    empty = (pd.DataFrame(columns=SPINE_COLS), pd.DataFrame(columns=["code", "name", "market"]))
    if not MARCAP_ENABLED:
        return empty
    this_year = _dt.datetime.now(_dt.timezone.utc).year
    ys = sorted({int(x) for x in years})
    frames, metas, got, miss = [], [], [], []
    LOG.info(f"일별 전종목시세 스파인 {ys[0]}~{ys[-1]} ({len(ys)}개 연도) 준비 — "
             f"연도별로 받아 즉시 슬림화합니다(원본을 모으지 않습니다)")
    for k, y in enumerate(ys, 1):
        tbl = SPINE_TABLE.format(y=y)
        #  과거 연도 파일은 사실상 불변 → 영구 캐시. 올해 파일만 매일 갱신된다.
        d = VAULT.get_table(tbl, scope="shared", max_age_days=(1.0 if y >= this_year else None))
        if d is not None and len(d):
            LOG.debug(f"  [{k}/{len(ys)}] {y} 캐시 재사용 {len(d):,}행")
        else:
            if RUN_MODE == "CACHED":
                miss.append(y)
                continue
            t0 = time.time()
            raw = http_get(_MARCAP_URL.format(y=y), source="fdr", as_bytes=True,
                           tries=3, timeout=240)
            if not raw or len(raw) < 10_000:
                miss.append(y)
                LOG.warn(f"  [{k}/{len(ys)}] {y} 다운로드 실패 — 그 해는 유니버스에서 빠집니다")
                continue
            try:
                #  ★ columns= 로 필요한 컬럼만 읽는다. 읽고 나서 버리면 이미 메모리를 먹은 뒤다.
                rawdf = pd.read_parquet(io.BytesIO(raw), columns=_MARCAP_READ)
            except Exception:
                try:
                    rawdf = pd.read_parquet(io.BytesIO(raw))
                except Exception as e:
                    LOG.warn(f"  [{k}/{len(ys)}] {y} parquet 파싱 실패({type(e).__name__})")
                    miss.append(y)
                    continue
            d, meta = _scg_slim_marcap(rawdf)
            del rawdf, raw
            if not len(d):
                miss.append(y)
                continue
            VAULT.put_table(tbl, d, scope="shared", domain="universe",
                            source="FinanceData/marcap (github)")
            if meta is not None and len(meta):
                VAULT.put_table(f"marcap_meta_{y}", meta, scope="shared", domain="universe",
                                source="FinanceData/marcap (github)")
            got.append(y)
            LOG.info(f"  [{k}/{len(ys)}] {y} 수집 {len(d):,}행 · {mem_mb(d):.0f}MB · "
                     f"{time.time()-t0:.1f}s")
        m = VAULT.get_table(f"marcap_meta_{y}", scope="shared")
        if m is not None and len(m):
            metas.append(m)
        frames.append(d.reindex(columns=SPINE_COLS))
    if got:
        VAULT.flush("shared")
    if not frames:
        LOG.warn("스파인을 확보하지 못했습니다 — 상장/폐지목록 + 종목별 가격수집 경로로 폴백합니다.")
        return empty

    for f in frames:
        f.attrs.clear()                      # concat 의 attrs 동일성 검사를 원천 차단
    S = pd.concat(frames, ignore_index=True, copy=False)
    del frames
    S["date"] = S["date"].astype("datetime64[ns]")
    #  code 를 category 로 접으면 9M행 object(500MB) → int16 코드(18MB) 가 된다
    S["code"] = S["code"].astype("category")
    META = (pd.concat(metas, ignore_index=True).drop_duplicates("code", keep="last")
            if metas else pd.DataFrame(columns=["code", "name", "market"]))
    LOG.ok(f"스파인 {len(S):,}행 · {S['code'].nunique():,}종목 × {S['date'].nunique():,}거래일 · "
           f"{mem_mb(S):.0f}MB (신규 {len(got)}개 연도 · 캐시 {len(ys)-len(got)-len(miss)}개"
           + (f" · 누락 {miss}" if miss else "") + ")")
    PIPE.io("IN", "DRIVE", "marcap_spine", S, source="FinanceData/marcap")
    return S, META


def scg_spine_close_adj(S: pd.DataFrame) -> pd.DataFrame:
    """수정주가 계열을 스파인에서 직접 만든다 — 종목별 HTTP 0회.

    close_adj = 1000 × Π(1 + ret_adj).  절대 수준은 의미가 없고 비율만 쓰이므로
    기준값 1000 이면 충분하다(수익률·IC·백테스트가 전부 비율 연산이다).
    ★ ret_adj 는 KRX 기준가 기반이라 액면분할·증자가 이미 보정돼 있다. 대신 현금배당은
      빠져 있다 — 가격수익률이며, 한국 주식 백테스트의 통상적 관행이다.
    """
    if S is None or S.empty:
        return S
    S = S.sort_values(["code", "date"], kind="mergesort")
    r = S["ret_adj"].to_numpy("float64")
    #  첫 관측일의 등락률은 전일 기준가가 없어 의미가 없다 → 0 으로 두고 1.0 에서 출발한다.
    first = ~S["code"].duplicated().to_numpy()
    r = np.where(first | ~np.isfinite(r), 0.0, r)
    #  ±60% 를 넘는 일간 등락률은 한국 시장에 존재하지 않는다(상하한 ±30%).
    #  데이터 오류가 누적수익률을 통째로 날리는 것을 막는다.
    bad = np.abs(r) > 0.6
    if bad.any():
        LOG.info(f"일간 등락률 이상치 {int(bad.sum()):,}건을 0 으로 대체했습니다 "
                 f"(한국 시장 상하한 ±30% 초과 — 데이터 오류로 봅니다)")
        r = np.where(bad, 0.0, r)
    S = S.copy()
    S["close_adj"] = (1000.0 * pd.Series(1.0 + r, index=S.index)
                      .groupby(S["code"], observed=True).cumprod()).astype("float32")
    return S


def scg_spine_calendar(S: pd.DataFrame) -> pd.DatetimeIndex:
    """거래일 캘린더 — 전종목시세에 행이 있는 날이 곧 거래일이다(KRX 휴장일 API 불필요)."""
    if S is None or S.empty:
        return pd.DatetimeIndex([])
    cal = pd.DatetimeIndex(sorted(pd.unique(S["date"]))).normalize()
    LOG.ok(f"거래일 캘린더 {len(cal):,}일 ({cal.min().date()} ~ {cal.max().date()})")
    return cal


def scg_spine_master(S: pd.DataFrame, META: pd.DataFrame) -> pd.DataFrame:
    """종목 마스터 — 최초/최종 거래일. 폐지목록이 없어도 성립한다."""
    if S is None or S.empty:
        return pd.DataFrame(columns=SCG_SEC_COLS)
    g = S.groupby("code", observed=True)["date"]
    t = pd.DataFrame({"first_seen": g.min(), "last_seen": g.max()}).reset_index()
    t["code"] = t["code"].astype(str)
    end = pd.Timestamp(S["date"].max())
    #  마지막 거래일이 데이터 끝에서 30일 이상 앞서면 그때 사라진 종목이다
    gone = (end - t["last_seen"]).dt.days > 30
    t["delisting_date"] = pd.to_datetime(np.where(gone, t["last_seen"] + pd.Timedelta(days=1),
                                                  pd.NaT))
    if META is not None and len(META):
        t = t.merge(META.assign(code=META["code"].astype(str)), on="code", how="left")
    for c, v in (("name", ""), ("market", "KRX")):
        if c not in t.columns:
            t[c] = v
        t[c] = t[c].fillna(v)
    t["listing_date"] = t["first_seen"]
    t["corp_code"] = np.nan
    t["industry"] = ""
    t["src"] = "marcap"
    t["delist_src"] = np.where(gone, "marcap_last_seen", "")
    return t.reindex(columns=SCG_SEC_COLS)


def scg_spine_universe(S: pd.DataFrame, signal_dates, sec: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """★ 생존자편향이 정의상 불가능한 유니버스: '그날 시세표에 행이 있었는가'.

    상장일·폐지일을 추정할 필요가 없다. 그날의 시세표가 곧 그날의 유니버스다.
    """
    if S is None or S.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id"])
    sd = pd.DatetimeIndex(signal_dates)
    U = S.loc[S["date"].isin(sd), ["date", "code"]].rename(
        columns={"date": "signal_date", "code": "stock_id"})
    U["stock_id"] = U["stock_id"].astype(str)
    U = U.drop_duplicates()
    if sec is not None and len(sec):
        keep = set(sec["code"].astype(str))
        n0 = U["stock_id"].nunique()
        U = U[U["stock_id"].isin(keep)]
        LOG.debug(f"보통주 필터: {n0:,} → {U['stock_id'].nunique():,}종목")
    per = U.groupby("signal_date").size()
    LOG.ok(f"PIT 유니버스 {len(U):,}행 · 시점당 평균 {per.mean():.0f}종목 "
           f"(최소 {per.min():,} · 최대 {per.max():,}) — 폐지 종목이 그 시절엔 포함됩니다")
    return U.reset_index(drop=True)


def scg_spine_marketcap(S: pd.DataFrame, signal_dates) -> pd.DataFrame:
    """PIT 시가총액 — 그날 관측된 Marcap 을 그대로 쓴다(정의상 PIT 이다)."""
    cols = ["signal_date", "stock_id", "close_unadj", "shares", "marketcap", "mcap_src"]
    if S is None or S.empty:
        return pd.DataFrame(columns=cols)
    sd = pd.DatetimeIndex(signal_dates)
    d = S.loc[S["date"].isin(sd), ["date", "code", "close_unadj", "shares", "marketcap"]]
    out = d.rename(columns={"date": "signal_date", "code": "stock_id"}).copy()
    out["stock_id"] = out["stock_id"].astype(str)
    out["mcap_src"] = "marcap"
    out = out.dropna(subset=["marketcap"])
    LOG.ok(f"PIT 시가총액 {len(out):,}행 — DART 주식총수 호출 없이 확보")
    return out.reindex(columns=cols).reset_index(drop=True)


def scg_spine_adv(S: pd.DataFrame, signal_dates) -> pd.DataFrame:
    """20거래일 평균 거래대금 — 용량 진단용(하드게이트 아님). 스파인에서 바로 만든다."""
    cols = ["signal_date", "stock_id", "adv20"]
    if S is None or S.empty or "amount" not in S.columns:
        return pd.DataFrame(columns=cols)
    d = S[["code", "date", "amount"]].sort_values(["code", "date"], kind="mergesort")
    d["adv20"] = (d.groupby("code", observed=True)["amount"]
                   .transform(lambda s: s.rolling(20, min_periods=5).mean()))
    sd = pd.DatetimeIndex(signal_dates)
    out = d.loc[d["date"].isin(sd) & d["adv20"].notna(), ["date", "code", "adv20"]]
    out = out.rename(columns={"date": "signal_date", "code": "stock_id"})
    out["stock_id"] = out["stock_id"].astype(str)
    return out.reindex(columns=cols).reset_index(drop=True)


def scg_spine_prices(S: pd.DataFrame) -> pd.DataFrame:
    """백테스트가 쓰는 (code, date, close_adj) 패널. 스파인의 뷰일 뿐 새 수집이 아니다."""
    if S is None or S.empty or "close_adj" not in S.columns:
        return pd.DataFrame(columns=["code", "date", "close_adj", "amount", "src"])
    out = S[["code", "date", "close_adj", "amount"]].copy()
    out["code"] = out["code"].astype(str)
    out["src"] = "marcap"
    return out


def scg_fetch_listing() -> pd.DataFrame:
    """현재 상장 종목. 이것만으로는 생존자편향이 남으므로 반드시 폐지목록과 합쳐야 한다."""
    d = _scg_fdr_cache_csv("listing/krx")
    if d is None or not len(d):
        LOG.warn("상장목록을 확보하지 못했습니다 (FDR GitHub 캐시 실패). "
                 "DART corpCode 와 가격 관측만으로 유니버스를 구성합니다 — 정확도가 떨어집니다.")
        return pd.DataFrame(columns=SCG_SEC_COLS)
    col = _scg_lower_map(d)
    code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
    name_c = col.get("name") or col.get("korean name") or col.get("isu_nm")
    if not code_c or not name_c:
        LOG.warn(f"상장목록 컬럼 인식 실패: {list(d.columns)[:12]}")
        return pd.DataFrame(columns=SCG_SEC_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[name_c].astype(str).str.strip(),
        "market": (d[col["market"]].astype(str) if "market" in col
                   else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
        "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
        "industry": (d[col["sector"]].astype(str) if "sector" in col
                     else d[col["industry"]].astype(str) if "industry" in col else ""),
    })
    t["delisting_date"] = pd.NaT
    t["corp_code"] = np.nan
    t["src"] = "fdr_listing"
    t["delist_src"] = ""
    t = t.dropna(subset=["code"]).drop_duplicates("code")
    LOG.ok(f"상장목록 {len(t):,}건 (KRX 미호출 경로)")
    return t[SCG_SEC_COLS]


def scg_fetch_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. KRX 없이 이 GitHub 캐시가 사실상 유일한 공개 경로다."""
    d = _scg_fdr_cache_csv("listing/delisting")
    empty = pd.DataFrame(columns=["code", "name", "delisting_date", "market", "secugroup"])
    if d is None or not len(d):
        LOG.warn("상장폐지 목록을 확보하지 못했습니다 — 생존자편향 제거가 '관측기반 추정'에만 "
                 "의존하게 됩니다. 결과 해석 시 반드시 감안하세요.")
        return empty
    col = _scg_lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        LOG.warn(f"폐지목록에서 종목코드 컬럼을 찾지 못했습니다: {list(d.columns)[:12]}")
        return empty
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date",
                                  "listingdate") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c
    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    t = pd.DataFrame({
        "code": codes, "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    }).dropna(subset=["code"])
    #  재상장/재폐지가 있으면 '가장 늦은 폐지일'을 남긴다(가장 이른 것을 남기면 재상장
    #  구간이 통째로 유니버스에서 빠져 표본이 줄어든다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    #  ★ 탈락분을 '코드 형식 오류'로 뭉뚱그리면 오경보가 난다. 폐지목록에는 ELW·신주인수권
    #    (8자리, 예: 722011J7)이 대량으로 섞여 있고 그건 보통주가 아니므로 빼는 게 맞다.
    #    진짜 문제는 '6자리인데 파싱 실패한' 건이다. 둘을 갈라서 보고한다.
    failed = raw_codes[codes.isna()]
    n_bad = int(codes.isna().sum())
    n_nonequity = int(failed.str.len().ne(6).sum())
    n_real = n_bad - n_nonequity
    LOG.ok(f"상장폐지 목록 {len(t):,}건 (원본 {n_raw:,} · 보통주 아님 {n_nonequity:,} "
           f"[ELW·신주인수권 등, 제외가 정상] · 코드형식 실패 {n_real:,})")
    if n_real > n_raw * 0.02:
        LOG.warn(f"6자리인데 파싱에 실패한 폐지종목이 {n_real:,}건입니다 — 그만큼 생존자편향이 "
                 f"남습니다. 예시: {failed[failed.str.len().eq(6)].head(5).tolist()}")
    return t


def scg_fetch_dart_corpcode() -> pd.DataFrame:
    """DART corpCode.xml — corp_code ↔ stock_code 매핑 (KRX 아님, 금융감독원)."""
    cols = ["corp_code", "corp_name", "code", "modify_date"]
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.debug(f"DART corpCode 캐시 재사용 ({len(cached):,}건)")
        return cached.reindex(columns=cols)
    if not DART_API_KEY:
        LOG.info("DART_API_KEY 가 없어 corp_code 매핑을 건너뜁니다 → 실적 실측치(A)가 없어 "
                 "ACC* 는 전부 0 으로 수축됩니다(애널리스트는 유지).")
        return pd.DataFrame(columns=cols)
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3,
                   referer="https://opendart.fss.or.kr/")
    if not raw or len(raw) < 1000:
        LOG.warn("corpCode.xml 을 받지 못했습니다. DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=cols)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read(z.namelist()[0])
    except Exception as e:
        LOG.warn(f"corpCode.xml 압축 해제 실패({type(e).__name__}) — 응답이 ZIP 이 아닙니다 "
                 f"(대개 인증키 오류 시 XML 에러문서가 옵니다).")
        return pd.DataFrame(columns=cols)
    rows = re.findall(
        rb"<list>\s*<corp_code>(.*?)</corp_code>\s*<corp_name>(.*?)</corp_name>\s*"
        rb"<stock_code>(.*?)</stock_code>\s*<modify_date>(.*?)</modify_date>", xml, re.S)
    if not rows:
        return pd.DataFrame(columns=cols)
    t = pd.DataFrame({
        "corp_code": [r[0].decode("utf-8", "ignore").strip() for r in rows],
        "corp_name": [r[1].decode("utf-8", "ignore").strip() for r in rows],
        "code": [to_code6(r[2].decode("utf-8", "ignore").strip()) for r in rows],
        "modify_date": [r[3].decode("utf-8", "ignore").strip() for r in rows],
    })
    VAULT.put_table("dart_corpcode", t, scope="shared", domain="dart", source="opendart corpCode")
    LOG.ok(f"DART corpCode {len(t):,}건 (상장 {int(t['code'].notna().sum()):,}건)")
    return t


def scg_build_security_master(listing: pd.DataFrame, delisting: pd.DataFrame,
                              corpcode: pd.DataFrame) -> pd.DataFrame:
    """상장 + 폐지 + corp_code 를 합쳐 종목 마스터를 만든다.

    ★ 폐지 종목을 '행으로 존재하게' 만드는 것이 이 함수의 존재 이유다.
      상장목록만 쓰면 오늘 살아있는 회사만 남고, 그 순간 백테스트는 전부 거짓말이 된다.
    """
    frames = []
    if listing is not None and len(listing):
        frames.append(listing.reindex(columns=SCG_SEC_COLS))
    if delisting is not None and len(delisting):
        d = pd.DataFrame({
            "code": delisting["code"], "name": delisting["name"],
            "market": delisting.get("market", "KRX"),
            "listing_date": pd.NaT, "delisting_date": delisting["delisting_date"],
            "corp_code": np.nan, "industry": "",
            "src": "fdr_delisting", "delist_src": "fdr_delisting"})
        frames.append(d.reindex(columns=SCG_SEC_COLS))
    if not frames:
        raise RuntimeError(
            "종목 마스터를 만들 수 없습니다: 상장목록·폐지목록을 모두 확보하지 못했습니다. "
            "KRX 를 쓰지 않는 설계이므로 raw.githubusercontent.com 접근이 필수입니다 — "
            "네트워크(프록시/방화벽)를 확인하세요.")

    A = pd.concat(frames, ignore_index=True)
    A = A[A["code"].notna()].copy()
    A["code"] = A["code"].astype(str)
    agg = A.groupby("code", as_index=False).agg(
        name=("name", lambda s: max((str(x) for x in s if str(x) not in ("", "nan")),
                                    key=len, default="")),
        market=("market", "first"),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "max"),
        industry=("industry", "first"),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
        delist_src=("delist_src", lambda s: "|".join(sorted({x for x in map(str, s) if x}))))
    agg["corp_code"] = np.nan

    if corpcode is not None and len(corpcode):
        cc = corpcode.dropna(subset=["code"]).drop_duplicates("code")
        agg = agg.drop(columns=["corp_code"]).merge(
            cc[["code", "corp_code"]], on="code", how="left")

    #  ── 보통주만 남긴다 (시점 불변 규칙이라 미래정보가 아니다) ────────────────────────
    n0 = len(agg)
    is_common = agg["code"].str.len().eq(6) & agg["code"].str[5].eq("0")
    bad_name = agg["name"].astype(str).str.contains(_SCG_NONEQUITY_NAME, na=False)
    agg = agg[is_common & ~bad_name].copy()
    LOG.info(f"종목 마스터 {n0:,} → 보통주 {len(agg):,}건 "
             f"(우선주 등 {int((~is_common).sum()):,} · 스팩/ETF/리츠 {int(bad_name.sum()):,} 제외)")

    n_del = int(agg["delisting_date"].notna().sum())
    LOG.ok(f"종목 마스터 {len(agg):,}건 · 상장폐지 이력 보유 {n_del:,}건 "
           f"({100*n_del/max(len(agg),1):.1f}%)")
    if n_del < 300:
        LOG.warn(f"폐지 종목이 {n_del:,}건뿐입니다. 10년 구간이면 통상 1,000건 이상입니다 — "
                 f"생존자편향이 완전히 제거되지 않았을 수 있습니다. 그대로 보고합니다.")
    return agg.reindex(columns=SCG_SEC_COLS)


def scg_infer_delisting_from_prices(sec: pd.DataFrame, px: pd.DataFrame,
                                    cal: np.ndarray, gap_days: int = 200) -> pd.DataFrame:
    """③ 관측기반 폐지 추정 — 시장은 계속 도는데 이 종목만 시계열이 끊겼다면 폐지다.

    ★ 폐지목록이 놓친 종목을 여기서 줍는다. 이것을 안 하면 그 종목들은
      '데이터 끝까지 살아 있었던 것'처럼 처리되어 생존자편향이 남는다.
    ★ 반대 방향의 사고도 막아야 한다: 데이터 **수집 실패**를 폐지로 오인하면
      멀쩡한 종목이 유니버스에서 사라진다. 그래서 마지막 거래일이 '전체 데이터의 끝'에서
      gap_days 이상 떨어져 있을 때만 폐지로 본다.
    """
    if px is None or px.empty or sec is None or sec.empty:
        return sec
    last = px.groupby("code", observed=True)["date"].max()
    if last.empty:
        return sec
    data_end = pd.Timestamp(last.max())
    S = sec.copy()
    S["_last_px"] = S["code"].map(last)
    need = S["delisting_date"].isna() & S["_last_px"].notna() & \
        ((data_end - S["_last_px"]).dt.days > gap_days)
    n = int(need.sum())
    if n:
        #  마지막 체결 다음 거래일을 폐지일로 본다(그날부터 유니버스에서 빠진다)
        nd = _scg_shift_td(S.loc[need, "_last_px"], 1, cal)
        S.loc[need, "delisting_date"] = pd.to_datetime(nd)
        S.loc[need, "delisting_date"] = S.loc[need, "delisting_date"].fillna(
            S.loc[need, "_last_px"] + pd.Timedelta(days=1))
        S.loc[need, "delist_src"] = (S.loc[need, "delist_src"].astype(str)
                                     .str.strip("|") + "|inferred_price_stop").str.strip("|")
        LOG.info(f"관측기반 폐지 추정 {n:,}건 — 폐지목록에 없지만 가격 시계열이 "
                 f"{gap_days}일 이상 먼저 끊긴 종목입니다(생존자편향 제거의 3중 방어 ③).")
    both = int((sec["delisting_date"].notna() &
                sec["code"].isin(S.loc[need, "code"])).sum())
    LOG.debug(f"폐지 근거 교차: 목록기반 {int(sec['delisting_date'].notna().sum()):,} · "
              f"관측기반 추가 {n:,} · 중복 {both:,}")
    return S.drop(columns=["_last_px"])


def scg_first_trade_dates(sec: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """상장일이 비어 있으면 최초 체결일로 보수적으로 채운다.

    ★ '보수적' 의 방향이 중요하다. 최초 체결일은 실제 상장일보다 같거나 늦으므로,
      이걸로 채우면 유니버스 편입이 늦어질지언정 빨라지지 않는다 → 미래누수 없음.
    """
    if px is None or px.empty:
        return sec
    first = px.groupby("code", observed=True)["date"].min()
    S = sec.copy()
    need = S["listing_date"].isna()
    S.loc[need, "listing_date"] = S.loc[need, "code"].map(first)
    S["listing_date"] = as_ts_series(S["listing_date"])
    LOG.debug(f"상장일 보강 {int(need.sum()):,}건 (최초 체결일 기준 — 보수적 방향)")
    return S


def scg_universe_at(sec: pd.DataFrame, dates) -> pd.DataFrame:
    """시점별 유니버스 멤버십. 이 함수 하나가 생존자편향 제거의 최종 판정자다.

        회원 조건:  listing_date <= t  AND  (delisting_date 없음 OR delisting_date > t)
    """
    d = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(dates))).dropna().unique()))
    S = sec.dropna(subset=["code"]).copy()
    S["listing_date"] = as_ts_series(S["listing_date"])
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    #  상장일이 끝내 결측이면 '언제부터 있었는지 모른다' → 보수적으로 데이터 시작부터 포함하지
    #  않는다면 표본이 준다. 반대로 무조건 포함하면 상장 전 데이터를 쓰게 된다.
    #  가격이 있는 날부터만 수익률이 계산되므로, 여기서는 포함하고 하류에서 가격으로 걸러진다.
    #  센티넬은 datetime64[ns] 범위(1677~2262) 안이어야 한다. 2999 를 쓰면 OverflowError 다.
    ls = S["listing_date"].fillna(pd.Timestamp("1900-01-01")).values.astype("datetime64[ns]")
    de = S["delisting_date"].fillna(pd.Timestamp("2200-01-01")).values.astype("datetime64[ns]")
    dv = d.values.astype("datetime64[ns]")
    mask = (ls[:, None] <= dv[None, :]) & (de[:, None] > dv[None, :])
    ii, jj = np.nonzero(mask)
    return pd.DataFrame({"signal_date": dv[jj], "stock_id": S["code"].values[ii]})


def scg_build_calendar(px: pd.DataFrame, bench: Optional[pd.DataFrame] = None
                       ) -> pd.DatetimeIndex:
    """거래일 캘린더 — KRX 휴장일 API 없이 '실제로 거래가 일어난 날'의 합집합으로 만든다.

    ★ Leadership 의 20일은 calendar day 가 아니라 trading day 다(§4). 이 캘린더가 틀리면
      t20 이 통째로 어긋나 Leadership 이 조용히 다른 것을 측정한다.
    ★ 한 종목만 거래된 날을 거래일로 세면 오류에 취약하므로, 그날 거래된 종목 수가
      중앙값의 20% 이상인 날만 채택한다.
    """
    cands = []
    if bench is not None and len(bench):
        cands.append(pd.DatetimeIndex(as_ts_series(bench["date"]).dropna().unique()))
    if px is not None and len(px):
        cnt = px.groupby("date", observed=True)["code"].size()
        if len(cnt):
            thr = max(1.0, float(cnt.median()) * 0.2)
            cands.append(pd.DatetimeIndex(cnt[cnt >= thr].index))
    if not cands:
        LOG.warn("거래일 캘린더 원천이 없어 영업일(월~금)로 대체합니다 — 공휴일이 포함되어 "
                 "t20 이 며칠 어긋날 수 있습니다.")
        return pd.bdate_range(as_ts(BACKTEST_START) - pd.DateOffset(years=HISTORY_WARMUP_YEARS + 1),
                              as_ts(BACKTEST_END) + pd.DateOffset(years=1))
    cal = cands[0]
    for c in cands[1:]:
        cal = cal.union(c)
    cal = pd.DatetimeIndex(sorted(set(cal))).normalize().drop_duplicates()
    LOG.ok(f"거래일 캘린더 {len(cal):,}일 ({cal.min().date()} ~ {cal.max().date()}) — "
           f"KRX 휴장일 API 없이 실거래 관측으로 구성")
    return cal


def scg_signal_dates(cal: pd.DatetimeIndex, freq: str = "M") -> pd.DatetimeIndex:
    """신호 시점 그리드 — 각 기간의 **마지막 거래일**. 달력 말일이 아니다."""
    if not len(cal):
        return pd.DatetimeIndex([])
    s = pd.Series(cal, index=cal)
    period = "W" if str(freq).upper().startswith("W") else "M"
    g = s.groupby(s.index.to_period(period)).max()
    sd = pd.DatetimeIndex(g.values)
    lo, hi = as_ts(BACKTEST_START), as_ts(BACKTEST_END)
    sd = sd[(sd >= lo) & (sd <= hi)]
    LOG.ok(f"신호 시점 {len(sd)}개 ({period} 그리드 · {sd.min().date()} ~ {sd.max().date()})")
    return sd


# ══════════════════════════════════════════════════════════════════════════════════════
#  PIT 시가총액 — 하위 1000 비교 유니버스 (§ 사용자 요구)
# ══════════════════════════════════════════════════════════════════════════════════════

def scg_build_marketcap(px_unadj: pd.DataFrame, shares: pd.DataFrame,
                        signal_dates: pd.DatetimeIndex, cal: np.ndarray) -> pd.DataFrame:
    """PIT 시가총액 = 그 시점의 **실제 주가(무수정)** × 그 시점까지 공시된 **주식총수**.

    ★ 왜 무수정 주가인가: 수정주가는 과거를 현재 기준으로 다시 쓴 값이다.
      2016년 시가총액을 2026년 기준 수정주가로 계산하면 액면분할한 종목의 과거 시총이
      분할 배수만큼 축소되어 '하위 1000' 선정이 통째로 틀어진다.
    ★ 왜 PIT 주식총수인가: 오늘의 주식수를 과거에 곱하면 그 사이의 증자·감자가
      전부 미래정보로 새어 들어간다. DART 접수일(rcept_dt) 이후에만 반영한다.
    ★ 주식총수를 못 구한 종목은 버리지 않는다. mcap 이 NaN 이면 하위1000 선정에서만
      빠지고 전체(ALL) 유니버스에는 그대로 남는다 — 표본 보존이 우선이다(§49).
    """
    cols = ["signal_date", "stock_id", "close_unadj", "shares", "marketcap", "mcap_src"]
    if px_unadj is None or px_unadj.empty:
        LOG.warn("무수정 주가가 없어 PIT 시가총액을 만들 수 없습니다 → 하위1000 비교 유니버스 비활성.")
        return pd.DataFrame(columns=cols)

    M, codes, didx = _scg_price_matrix(px_unadj, np.asarray(cal, dtype="datetime64[ns]"),
                                       value_col="close_unadj")
    if M.size == 0:
        return pd.DataFrame(columns=cols)
    U = scg_universe_at_frame(signal_dates, codes)
    ci = U["stock_id"].map(codes).to_numpy("int64")
    pos = np.searchsorted(didx, U["signal_date"].values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = pos >= 0
    U["close_unadj"] = np.where(ok, M[np.clip(pos, 0, len(didx) - 1), ci], np.nan)
    U = U[U["close_unadj"].notna()]
    if U.empty:
        return pd.DataFrame(columns=cols)

    if shares is None or shares.empty:
        LOG.warn("주식총수(DART)를 확보하지 못해 시가총액을 만들 수 없습니다 → "
                 "하위1000 비교 유니버스는 '거래대금 하위'로 대체됩니다.")
        U["shares"] = np.nan
        U["marketcap"] = np.nan
        U["mcap_src"] = "none"
        return U.reindex(columns=cols)

    sh = shares[["code", "knowledge_date", "shares"]].dropna().copy()
    sh["knowledge_date"] = _scg_ns(sh["knowledge_date"])
    sh = sh.dropna(subset=["knowledge_date"]).sort_values("knowledge_date")
    #  ★ merge_asof backward = '그 시점까지 공시된 최신 주식수'. 미래 공시는 구조적으로 안 붙는다.
    U["signal_date"] = _scg_ns(U["signal_date"])
    U = U.sort_values("signal_date")
    J = pd.merge_asof(U, sh.rename(columns={"knowledge_date": "signal_date"}),
                      on="signal_date", left_by="stock_id", right_by="code",
                      direction="backward")
    J["marketcap"] = J["close_unadj"] * J["shares"]
    J["mcap_src"] = np.where(J["shares"].notna(), "dart_shares", "none")
    cov = float(J["marketcap"].notna().mean())
    LOG.ok(f"PIT 시가총액 {len(J):,}행 · 커버리지 {100*cov:.1f}% "
           f"(무수정주가 × DART 주식총수, 접수일 기준 asof)")
    if cov < 0.5:
        LOG.warn(f"시가총액 커버리지가 {100*cov:.0f}% 입니다 — 하위1000 선정이 부분표본에서만 "
                 f"이뤄집니다. 커버리지 밖 종목은 ALL 유니버스에는 그대로 남습니다.")
    return J.reindex(columns=cols)


def scg_universe_at_frame(signal_dates: pd.DatetimeIndex, codes: Dict[str, int]) -> pd.DataFrame:
    """(시점 × 가격보유종목) 격자. 시가총액 계산의 뼈대."""
    cs = list(codes)
    sd = pd.DatetimeIndex(signal_dates)
    return pd.DataFrame({
        "signal_date": np.repeat(sd.values.astype("datetime64[ns]"), len(cs)),
        "stock_id": np.tile(np.array(cs, dtype=object), len(sd)),
    })


def scg_small_universe(mcap: pd.DataFrame, n: int, fallback_adv: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """시점별 시가총액 **하위 n 종목**. 기존 전략 대비 비교용 압축 유니버스."""
    cols = ["signal_date", "stock_id"]
    if mcap is not None and len(mcap) and mcap["marketcap"].notna().any():
        d = mcap.dropna(subset=["marketcap"]).copy()
        d["_r"] = d.groupby("signal_date", observed=True)["marketcap"].rank(
            method="first", ascending=True)
        out = d[d["_r"] <= n][cols]
        per = out.groupby("signal_date").size()
        LOG.ok(f"하위{n:,} 유니버스: 시점당 평균 {per.mean():.0f}종목 "
               f"(최소 {per.min():.0f} · 최대 {per.max():.0f})")
        return out.reset_index(drop=True)
    if fallback_adv is not None and len(fallback_adv):
        LOG.warn(f"시가총액이 없어 '거래대금 하위 {n:,}' 로 대체합니다 — 규모 프록시이며 "
                 f"시가총액과 완전히 같지 않습니다. 해석 시 감안하세요.")
        d = fallback_adv.dropna(subset=["adv20"]).copy()
        d["_r"] = d.groupby("signal_date", observed=True)["adv20"].rank(
            method="first", ascending=True)
        return d[d["_r"] <= n][cols].reset_index(drop=True)
    LOG.warn("하위1000 비교 유니버스를 만들 수 없습니다 (시가총액·거래대금 모두 없음).")
    return pd.DataFrame(columns=cols)
