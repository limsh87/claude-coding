

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 — KRX 미호출. FDR / 네이버금융 / yfinance 3중화.                                ║
# ║                                                                                          ║
# ║  ★ 두 종류의 가격을 **분리해서** 쓴다. 섞으면 조용히 틀린다.                                 ║
# ║      close_adj   (수정주가)  → 수익률·IC·백테스트.  분할/배당이 소급 반영된 값.             ║
# ║      close_unadj (실제주가)  → 시가총액·목표주가 환산. 그날 실제로 체결된 값.               ║
# ║    수정주가로 2016년 시가총액을 계산하면 이후 액면분할한 종목의 과거 시총이 배수만큼         ║
# ║    줄어들어 '하위 1000' 선정이 통째로 틀어진다. 이게 흔한 조용한 버그다.                     ║
# ║                                                                                          ║
# ║  ★ 캐시 재사용: 이전 전략(TCD v2)이 만들어 둔 공용 테이블 krx_ohlcv_daily 를 **씨앗으로**    ║
# ║    읽는다. 단, 그 테이블은 소스별로 수정/무수정이 섞여 있으므로(yfinance 행은 무수정)        ║
# ║    src 로 갈라서 각각 제 자리에 넣는다. 그대로 합치면 분할 종목에서 점프가 생긴다.           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_PX_ADJ_TABLE = "price_daily_adj"          # 공용 — 다른 전략도 그대로 재사용 가능
SCG_PX_UNADJ_TABLE = "price_daily_unadj"      # 공용
SCG_PX_COLS = ["code", "date", "close_adj", "volume", "amount", "src"]
SCG_UNADJ_COLS = ["code", "date", "close_unadj", "adj_factor", "src"]
#  이 소스들은 수정주가를 준다. yfinance 는 auto_adjust=False 로 부르면 무수정이다.
_SCG_ADJ_SRC = ("fdr", "naver", "pykrx")


def _scg_px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """★ 폐기된 경로다 — 절대 되살리지 마라.

    fdr.DataReader 는 **어떤 타임아웃도 받지 않는다**. 내부적으로
    pandas.read_csv(<http url>) → urllib.request.urlopen(timeout 인자 없음)
    으로 내려가고, 그건 socket 기본값(=None, 무한대기)이다. 게다가 호출부가
    `except Exception: d = None` 으로 감싸고 있어서 멈춰도 예외도 로그도 없다 —
    우리가 실제로 겪은 '조용한 정체'의 정확한 형태다.

    한국 종목은 _scg_px_naver 가 같은 데이터를 덮고, 그쪽은 http_get(전체 마감 있음)
    을 쓴다. 그래서 이 경로는 항상 None 을 돌려주고 사다리에서 빠진다.
    """
    return None



def _scg_px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 금융 차트 API. 로그인 불필요, 폐지 직전까지의 시계열도 대체로 남아 있다."""
    url = ("https://api.finance.naver.com/siseJson.naver?symbol=%s&requestType=1"
           "&startTime=%s&endTime=%s&timeframe=day"
           % (code, as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d")))
    txt = http_get(url, source="naver", tries=2, referer="https://finance.naver.com/")
    if not txt or "[" not in txt:
        return None
    try:
        rows = json.loads(re.sub(r"'", '"', txt.strip()))
    except Exception:
        return None
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    hdr = [str(x).strip() for x in rows[0]]
    body = [r for r in rows[1:] if isinstance(r, list) and len(r) >= 5]
    if not body:
        return None
    d = pd.DataFrame(body, columns=hdr[:len(body[0])])
    cmap = {c: str(c).strip().lower() for c in d.columns}
    d = d.rename(columns=cmap)
    dc = next((c for c in d.columns if c in ("날짜", "date")), None)
    cc = next((c for c in d.columns if c in ("종가", "close")), None)
    vc = next((c for c in d.columns if c in ("거래량", "volume")), None)
    if dc is None or cc is None:
        return None
    out = pd.DataFrame({
        "code": code,
        "date": pd.to_datetime(d[dc].astype(str), format="%Y%m%d", errors="coerce"),
        "close_adj": pd.to_numeric(d[cc], errors="coerce"),
        "volume": pd.to_numeric(d[vc], errors="coerce") if vc else np.nan})
    out["amount"] = out["close_adj"] * out["volume"]
    out["src"] = "naver"
    return out.dropna(subset=["date", "close_adj"])


def _scg_yf_symbols(code: str) -> List[str]:
    return [f"{code}.KS", f"{code}.KQ"]


def scg_fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """수정주가 일별 패널. 캐시 우선 → 부족분만 신규 → 드라이브 재적재.

    ★ 이 함수의 성능이 곧 백테스트 소요시간이다. 이미 받은 종목은 절대 다시 받지 않는다.
      (종목별 마지막 관측일을 보고 '연장이 필요한 종목'만 고른다)
    """
    want = [str(c) for c in pd.unique(pd.Series(list(codes))) if c and str(c) != "nan"]
    lo, hi = as_ts(start), as_ts(end)

    frames = []
    cached = VAULT.get_table(SCG_PX_ADJ_TABLE, scope="shared")
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        frames.append(cached.reindex(columns=SCG_PX_COLS))
        LOG.info(f"공용 캐시에서 수정주가 {len(cached):,}행 재사용")
    #  ★ 이전 전략(TCD v2)이 남긴 공용 테이블도 그대로 재활용한다 — 단, 수정주가 소스만.
    legacy = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if legacy is not None and len(legacy) and "close" in legacy.columns:
        lg = legacy.copy()
        lg["src"] = (lg["src"].astype(str) if "src" in lg.columns
                     else pd.Series("unknown", index=lg.index))
        keep = lg["src"].isin(_SCG_ADJ_SRC)
        n_drop = int((~keep).sum())
        lg = lg[keep]
        if len(lg):
            lg = pd.DataFrame({"code": lg["code"].astype(str), "date": as_ts_series(lg["date"]),
                               "close_adj": pd.to_numeric(lg["close"], errors="coerce"),
                               "volume": pd.to_numeric(lg.get("volume"), errors="coerce"),
                               "amount": pd.to_numeric(lg.get("amount"), errors="coerce"),
                               "src": lg["src"]})
            frames.append(lg.dropna(subset=["date", "close_adj"]))
            LOG.info(f"이전 전략 캐시(krx_ohlcv_daily)에서 {len(lg):,}행 재활용 "
                     f"(수정주가 소스만 · 무수정 소스 {n_drop:,}행 제외 — 섞으면 분할 종목에 점프가 생깁니다)")

    have = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCG_PX_COLS)
    if len(have):
        have = have.dropna(subset=["code", "date"]).drop_duplicates(["code", "date"], keep="last")
    last = have.groupby("code")["date"].max() if len(have) else pd.Series(dtype="datetime64[ns]")

    if RUN_MODE == "CACHED":
        LOG.info("RUN_MODE='CACHED' — 신규 가격 수집을 건너뜁니다.")
        return have[have["date"].between(lo, hi)].reset_index(drop=True)

    todo = [c for c in want if (c not in last.index) or (last[c] < hi - pd.Timedelta(days=7))]
    LOG.info(f"수정주가: 전체 {len(want):,}종목 중 신규/연장 필요 {len(todo):,}종목 "
             f"(캐시 충분 {len(want)-len(todo):,}종목)")
    if not todo:
        return have[have["date"].between(lo, hi)].reset_index(drop=True)

    def _one(code: str) -> Optional[pd.DataFrame]:
        s = last[code] + pd.Timedelta(days=1) if code in last.index else lo
        s = max(s, lo)
        if s > hi:
            return None
        ss, ee = s.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")
        for fn in (_scg_px_naver,):          # _scg_px_fdr 은 무한대기 위험으로 제외
            try:
                d = fn(code, ss, ee)
            except Exception:
                d = None
            if d is not None and len(d):
                return d
        return None

    got: List[pd.DataFrame] = []
    CH = 1500
    for k0 in range(0, len(todo), CH):
        part = todo[k0:k0 + CH]
        res = pmap_io(_one, part, workers=N_WORKERS_IO,
                      desc=f"가격 수집 {k0//CH+1}/{(len(todo)-1)//CH+1}")
        got += [d for d in res if d is not None and len(d)]
        del res
        if got:
            add = pd.concat(got, ignore_index=True)
            have = pd.concat([have, add], ignore_index=True).drop_duplicates(
                ["code", "date"], keep="last")
            VAULT.put_table(SCG_PX_ADJ_TABLE, have, scope="shared", domain="price",
                            source="fdr/naver (KRX 미호출)")
            VAULT.flush("shared")
            got = []
    #  ★ set(have["code"]) 를 컴프리헨션 조건 안에 두면 파이썬이 알아서 밖으로 빼주지
    #    않는다 — todo 원소마다 have 전체(콜드스타트면 수백만 행)로 set 을 새로 만든다.
    #    9.1M행에서 실측 0.58초/회 × 2,800회 = 27분. 로그 한 줄 없이 조용히 걸린다 —
    #    이전에 겪은 30분 무출력 정체와 같은 종류의 사고다. 한 번만 만든다.
    have_codes = set(have["code"].unique()) if len(have) else set()
    n_fail = sum(1 for c in todo if c not in have_codes)
    if n_fail:
        LOG.info(f"가격을 끝내 못 받은 종목 {n_fail:,}개 — 폐지 직후이거나 소스에 없는 종목입니다. "
                 f"유니버스에는 남지만 수익률이 없어 백테스트 표본에서 자연히 빠집니다.")
    out = have[have["date"].between(lo, hi)].reset_index(drop=True)
    LOG.ok(f"수정주가 패널 {len(out):,}행 · {out['code'].nunique():,}종목")
    PIPE.io("OUT", "DRIVE", SCG_PX_ADJ_TABLE, out, source="fdr/naver")
    return out


def scg_fetch_unadjusted(codes: Sequence[str], start: str, end: str,
                         px_adj: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """무수정 종가 — yfinance(auto_adjust=False)를 **배치**로 받는다.

    ★ 시가총액 전용이다. 커버리지가 낮아도 전체 유니버스에는 영향을 주지 않는다
      (하위1000 비교 유니버스 선정에서만 쓰인다).
    ★ 배치 다운로드가 핵심: 종목별 단건이면 2,800회지만 50개씩 묶으면 56회다.
    """
    if yf is None:
        LOG.info("yfinance 가 없어 무수정 주가를 건너뜁니다 → 시가총액은 만들 수 없고 "
                 "하위1000 비교는 거래대금 하위로 대체됩니다.")
        return pd.DataFrame(columns=SCG_UNADJ_COLS)
    want = [str(c) for c in pd.unique(pd.Series(list(codes))) if c and str(c) != "nan"]
    cached = VAULT.get_table(SCG_PX_UNADJ_TABLE, scope="shared")
    have = pd.DataFrame(columns=SCG_UNADJ_COLS)
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        have = cached.reindex(columns=SCG_UNADJ_COLS)
        LOG.info(f"공용 캐시에서 무수정 주가 {len(have):,}행 재사용")
    if RUN_MODE == "CACHED":
        return have

    lo, hi = as_ts(start), as_ts(end)
    last = have.groupby("code")["date"].max() if len(have) else pd.Series(dtype="datetime64[ns]")
    todo = [c for c in want if (c not in last.index) or (last[c] < hi - pd.Timedelta(days=30))]
    if not todo:
        return have
    LOG.info(f"무수정 주가(시가총액용): {len(todo):,}종목 배치 수집 "
             f"({(len(todo)-1)//50+1}회 호출 — 종목별 단건이면 {len(todo):,}회입니다)")

    #  상장 시장을 몰라 .KS/.KQ 를 둘 다 시도해야 한다 → 두 접미사를 한 배치에 넣는다
    got: List[pd.DataFrame] = []
    B = 50
    syms = [s for c in todo for s in _scg_yf_symbols(c)]
    for k0 in range(0, len(syms), B):
        batch = syms[k0:k0 + B]
        try:
            limiter("yfinance").wait()
            d = yf.download(tickers=" ".join(batch), start=lo.strftime("%Y-%m-%d"),
                            end=(hi + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                            auto_adjust=False, group_by="ticker", progress=False,
                            threads=True, actions=False)
        except Exception as e:
            LOG.debug(f"yfinance 배치 실패({type(e).__name__}) — 건너뜁니다")
            continue
        if d is None or not len(d):
            continue
        for sym in batch:
            try:
                sub = d[sym] if isinstance(d.columns, pd.MultiIndex) else d
            except Exception:
                continue
            if sub is None or not len(sub) or "Close" not in sub.columns:
                continue
            s = sub.dropna(subset=["Close"])
            if not len(s):
                continue
            adj = s["Adj Close"] if "Adj Close" in s.columns else s["Close"]
            got.append(pd.DataFrame({
                "code": sym.split(".")[0], "date": as_ts_series(s.index),
                "close_unadj": pd.to_numeric(s["Close"], errors="coerce").values,
                "adj_factor": (pd.to_numeric(adj, errors="coerce").values /
                               pd.to_numeric(s["Close"], errors="coerce").values),
                "src": "yfinance"}))
        if got and (k0 // B) % 10 == 9:
            have = pd.concat([have] + got, ignore_index=True).drop_duplicates(
                ["code", "date"], keep="last")
            VAULT.put_table(SCG_PX_UNADJ_TABLE, have, scope="shared", domain="price",
                            source="yfinance auto_adjust=False")
            VAULT.flush("shared")
            got = []
    if got:
        have = pd.concat([have] + got, ignore_index=True).drop_duplicates(
            ["code", "date"], keep="last")
        VAULT.put_table(SCG_PX_UNADJ_TABLE, have, scope="shared", domain="price",
                        source="yfinance auto_adjust=False")
        VAULT.flush("shared")
    have = have.dropna(subset=["code", "date", "close_unadj"])
    LOG.ok(f"무수정 주가 {len(have):,}행 · {have['code'].nunique():,}종목 "
           f"(유니버스 대비 {100*have['code'].nunique()/max(len(want),1):.0f}%)")

    #  ── 수정/무수정이 실제로 다른지 검증한다. 같다면 둘 중 하나가 잘못된 것이다. ──────
    if px_adj is not None and len(px_adj) and len(have):
        j = have.merge(px_adj[["code", "date", "close_adj"]], on=["code", "date"], how="inner")
        if len(j) > 100:
            r = (j["close_adj"] / j["close_unadj"]).replace([np.inf, -np.inf], np.nan).dropna()
            diff = float((r.sub(1).abs() > 0.01).mean())
            LOG.info(f"수정/무수정 대조 {len(j):,}행: 1% 초과 괴리 {100*diff:.1f}% "
                     f"(분할·유상증자 등 자본변동이 있었던 구간). 괴리가 0% 라면 두 계열이 "
                     f"같은 것이므로 시가총액이 수정주가 기준이 되어 과거 시총이 왜곡됩니다.")
    return have.reindex(columns=SCG_UNADJ_COLS)


#  fdr.DataReader("KS11") 이 내부에서 읽는 바로 그 파일. 우리가 직접 마감을 걸고 받는다.
_KS11_YEAR_CSV = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                  "refs/heads/master/data/index/year_ks11/{y}.csv")


def scg_fetch_benchmark(start: str, end: str) -> pd.DataFrame:
    """KOSPI 지수 — 벤치마크 + 거래일 캘린더의 1순위 원천."""
    cached = VAULT.get_table("benchmark_ks11_daily", scope="shared", max_age_days=3)
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        return cached
    #  ★ fdr.DataReader("KS11") 을 쓰지 않는다. 그건 내부에서 연도별 GitHub CSV 를
    #    pandas.read_csv(<url>) 로 읽는데, 그 경로에는 타임아웃이 없다(urlopen 기본값
    #    =무한대기). 같은 파일을 우리가 직접, 전체 마감을 걸고 받는다. 결과는 동일하고
    #    최악의 경우에도 연당 60s×2회로 끝난다.
    frames = []
    for y in range(as_ts(start).year, as_ts(end).year + 1):
        b = http_get_stream(_KS11_YEAR_CSV.format(y=y), source="fdr",
                            deadline_s=60.0, tries=2, desc=f"ks11-{y}.csv")
        if not b:
            continue
        try:
            frames.append(pd.read_csv(io.BytesIO(b)))
        except Exception:
            continue
    d = pd.concat(frames, ignore_index=True) if frames else None
    if (d is None or not len(d)) and yf is not None:
        try:
            limiter("yfinance").wait()
            d = yf.download("^KS11", start=start, end=end, progress=False, auto_adjust=True)
        except Exception:
            d = None
    if d is None or not len(d):
        LOG.warn("벤치마크(KOSPI)를 받지 못했습니다 — 레짐 분할과 초과수익 계산을 건너뜁니다.")
        return pd.DataFrame(columns=["date", "close"])
    d = d.reset_index()
    d.columns = [str(c[0]) if isinstance(c, tuple) else str(c) for c in d.columns]
    dc = next((c for c in d.columns if c.lower() in ("date", "index")), d.columns[0])
    cc = next((c for c in d.columns if c.lower() == "close"), None)
    if cc is None:
        return pd.DataFrame(columns=["date", "close"])
    out = pd.DataFrame({"date": as_ts_series(d[dc]),
                        "close": pd.to_numeric(d[cc], errors="coerce")}).dropna()
    VAULT.put_table("benchmark_ks11_daily", out, scope="shared", domain="price", source="fdr KS11")
    LOG.ok(f"벤치마크(KOSPI) {len(out):,}일")
    return out


def scg_benchmark_returns(bench: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.Series:
    """신호 시점 그리드에 맞춘 벤치마크 기간수익률."""
    if bench is None or bench.empty or not len(signal_dates):
        return pd.Series(dtype="float64")
    b = bench.dropna().sort_values("date")
    idx = b["date"].values.astype("datetime64[ns]")
    pos = np.searchsorted(idx, pd.DatetimeIndex(signal_dates).values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = pos >= 0
    v = np.where(ok, b["close"].to_numpy("float64")[np.clip(pos, 0, len(b) - 1)], np.nan)
    s = pd.Series(v, index=pd.DatetimeIndex(signal_dates))
    return s.pct_change().shift(-1).dropna()      # t → t+1 구간 수익률 (신호와 같은 정렬)


def scg_adv_panel(px: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """20일 평균거래대금 — 용량 진단과 시가총액 폴백에 쓴다(하드게이트 아님)."""
    if px is None or px.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id", "adv20"])
    p = px[["code", "date", "amount"]].dropna(subset=["code", "date"]).sort_values(["code", "date"])
    p["adv20"] = p.groupby("code", observed=True)["amount"].transform(
        lambda s: s.rolling(20, min_periods=5).mean())
    p = p.dropna(subset=["adv20"])
    if p.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id", "adv20"])
    #  종목별 루프로 merge_asof 를 2,800번 도는 대신 by= 로 한 번에 끝낸다
    #  (2,800회 × 120시점이면 파이썬 오버헤드만 수십 초, by= 는 1초 미만)
    codes = pd.Index(pd.unique(p["code"]))
    grid = pd.DataFrame({
        "signal_date": np.repeat(pd.DatetimeIndex(signal_dates).values.astype("datetime64[ns]"),
                                 len(codes)),
        "stock_id": np.tile(codes.to_numpy(dtype=object), len(signal_dates)),
    }).sort_values("signal_date")
    right = p[["code", "date", "adv20"]].rename(columns={"date": "signal_date"})
    right["signal_date"] = _scg_ns(right["signal_date"])
    right = right.sort_values("signal_date")
    j = pd.merge_asof(grid, right, on="signal_date", left_by="stock_id", right_by="code",
                      direction="backward", tolerance=pd.Timedelta(days=30))
    return j.dropna(subset=["adv20"])[["signal_date", "stock_id", "adv20"]].reset_index(drop=True)
