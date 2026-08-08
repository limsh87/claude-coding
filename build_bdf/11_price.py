
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · ★PIT 시가총액 (KRX 없이)                                         ║
# ║                                                                                          ║
# ║  가격 폴백 사슬 (앞이 실패하면 자동으로 다음으로 — 전부 로그에 남는다):                    ║
# ║    ① FinanceDataReader      가장 넓은 커버리지, 상장폐지 종목도 상당수 조회됨              ║
# ║    ② 네이버금융 siseJson    api.finance.naver.com — 대량·고속·안정. EUC-KR 아님(JSON)      ║
# ║    ③ 네이버금융 sise_day    ②가 막힐 때의 HTML 폴백 (EUC-KR)                               ║
# ║    ④ yfinance               최후 폴백. 005930.KS / 0xxxxx.KQ                               ║
# ║                                                                                          ║
# ║  ★ 시가총액(PIT)이 이 모듈에서 가장 어려운 부분이다. KRX 를 못 쓰면 '과거 시점의 시총'을    ║
# ║    직접 주는 무료 소스가 사실상 없다. 그래서 4단 사다리로 만들고, 어느 단을 썼는지를        ║
# ║    (code, date) 마다 기록해 감사표로 출력한다. 조용히 틀린 시총을 쓰는 것이 최악이다.       ║
# ║      T1  DART 주식총수(stockTotqySttus) × 종가   ← 유일한 '정품' PIT 경로. DART 키 필요     ║
# ║      T2  현재 상장주식수 × 종가 ÷ 액면분할 보정  ← 자본변동 역산. 근사이지만 랭크는 견고    ║
# ║      T3  현재 시가총액 × (종가/현재종가)          ← T2 의 축약형                            ║
# ║      T4  20일 평균 거래대금 백분위                ← 시총이 아예 없을 때의 '사이즈 대용치'   ║
# ║                                                                                          ║
# ║    ※ 이 전략에서 시총은 전부 '랭크/버킷'으로만 쓰인다(§6.5 통제, H4 사이즈, 슬리피지 구간,  ║
# ║      비교전략의 하위 1000). 레벨로 쓰지 않으므로 T2~T4 로 강등돼도 결론이 뒤집히지 않는다.  ║
# ║      다만 T2~T4 는 '오늘의 주식수'를 과거에 투영하므로 미래정보가 섞인다 → 그 사실을        ║
# ║      감사표에 명시하고, T1 커버리지 비율을 반드시 보고한다.                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]

_NAVER_SISE_JSON = "https://api.finance.naver.com/siseJson.naver"
_NAVER_SISE_DAY = "https://finance.naver.com/item/sise_day.naver"


# ── ① FinanceDataReader ─────────────────────────────────────────────────────────────────────
def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    lc = {str(c).strip().lower(): c for c in d.columns}
    dt_c = lc.get("date") or lc.get("index") or d.columns[0]
    if "close" not in lc:
        return None
    vol = pd.to_numeric(d[lc["volume"]], errors="coerce") if "volume" in lc else np.nan
    close = pd.to_numeric(d[lc["close"]], errors="coerce")
    return pd.DataFrame({
        "code": code, "date": as_ts_series(d[dt_c]),
        "open": pd.to_numeric(d[lc["open"]], errors="coerce") if "open" in lc else close,
        "high": pd.to_numeric(d[lc["high"]], errors="coerce") if "high" in lc else close,
        "low": pd.to_numeric(d[lc["low"]], errors="coerce") if "low" in lc else close,
        "close": close, "volume": vol,
        "amount": pd.to_numeric(d[lc["amount"]], errors="coerce") if "amount" in lc
                  else close * vol,
        "src": "fdr"})


# ── ② 네이버 siseJson (대량 수집의 주력) ────────────────────────────────────────────────────
def _px_naver_json(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """반환 예: [['날짜','시가','고가','저가','종가','거래량','외국인소진율'], ['20160801',...], ...]

    ★ 응답이 JSON 처럼 보이지만 키가 홑따옴표라 json.loads 가 실패한다. 그래서 정규식으로 판다.
      (여기서 조용히 실패하면 전 종목 가격이 통째로 비고, 원인 추적이 매우 어렵다)"""
    s, e = as_ts(start), as_ts(end)
    if s is None or e is None:
        return None
    txt = http_get(_NAVER_SISE_JSON, source="naver",
                   params={"symbol": code, "requestType": 1,
                           "startTime": s.strftime("%Y%m%d"), "endTime": e.strftime("%Y%m%d"),
                           "timeframe": "day"},
                   referer=f"https://finance.naver.com/item/sise.naver?code={code}", tries=3)
    if not txt or "[" not in txt:
        return None
    rows = re.findall(r"\[([^\[\]]+)\]", txt)
    out = []
    for r in rows:
        parts = [p.strip().strip("'\"") for p in r.split(",")]
        if len(parts) < 6 or not re.fullmatch(r"\d{8}", parts[0]):
            continue           # 헤더행('날짜','시가',...) 은 여기서 걸러진다
        try:
            out.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3]),
                        float(parts[4]), float(parts[5])))
        except Exception:
            continue
    if not out:
        return None
    d = pd.DataFrame(out, columns=["date", "open", "high", "low", "close", "volume"])
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
    d["code"] = code
    d["amount"] = d["close"] * d["volume"]
    d["src"] = "naver_json"
    return d.dropna(subset=["date"])[PRICE_COLS]


# ── ③ 네이버 sise_day HTML 폴백 ─────────────────────────────────────────────────────────────
def _px_naver_html(code: str, start: str, end: str, max_pages: int = 700) -> Optional[pd.DataFrame]:
    s, e = as_ts(start), as_ts(end)
    got: List[pd.DataFrame] = []
    for page in range(1, max_pages + 1):
        html = http_get(_NAVER_SISE_DAY, source="naver", params={"code": code, "page": page},
                        force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/sise.naver?code={code}")
        if not html:
            break
        tabs = safe_read_html(html)
        if not tabs:
            break
        d = max(tabs, key=len).dropna(how="all")
        cols = {str(c).strip(): c for c in d.columns}
        if "날짜" not in cols or "종가" not in cols:
            break
        d = d.dropna(subset=[cols["날짜"]])
        if not len(d):
            break
        t = pd.DataFrame({
            "code": code,
            "date": pd.to_datetime(d[cols["날짜"]].astype(str).str.replace(".", "-", regex=False),
                                   errors="coerce"),
            "open": pd.to_numeric(d[cols.get("시가", cols["종가"])], errors="coerce"),
            "high": pd.to_numeric(d[cols.get("고가", cols["종가"])], errors="coerce"),
            "low": pd.to_numeric(d[cols.get("저가", cols["종가"])], errors="coerce"),
            "close": pd.to_numeric(d[cols["종가"]], errors="coerce"),
            "volume": pd.to_numeric(d[cols.get("거래량", cols["종가"])], errors="coerce"),
        }).dropna(subset=["date", "close"])
        if not len(t):
            break
        got.append(t)
        if t["date"].min() <= s:
            break
    if not got:
        return None
    d = pd.concat(got, ignore_index=True).drop_duplicates("date")
    d = d[(d["date"] >= s) & (d["date"] <= e)]
    d["amount"] = d["close"] * d["volume"]
    d["src"] = "naver_html"
    return d[PRICE_COLS] if len(d) else None


# ── ④ yfinance 최후 폴백 ────────────────────────────────────────────────────────────────────
def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):     # yfinance 0.2.5x 는 항상 MultiIndex 를 준다
            d.columns = [c[0] for c in d.columns]
        d = d.reset_index()
        lc = {str(c).strip().lower(): c for c in d.columns}
        if "close" not in lc:
            continue
        close = pd.to_numeric(d[lc["close"]], errors="coerce")
        vol = pd.to_numeric(d[lc["volume"]], errors="coerce") if "volume" in lc else np.nan
        return pd.DataFrame({
            "code": code, "date": as_ts_series(d[lc.get("date", d.columns[0])]),
            "open": pd.to_numeric(d[lc["open"]], errors="coerce") if "open" in lc else close,
            "high": pd.to_numeric(d[lc["high"]], errors="coerce") if "high" in lc else close,
            "low": pd.to_numeric(d[lc["low"]], errors="coerce") if "low" in lc else close,
            "close": close, "volume": vol, "amount": close * vol, "src": "yfinance"})
    return None


PRICE_CHAIN = [("fdr", _px_fdr), ("naver_json", _px_naver_json),
               ("naver_html", _px_naver_html), ("yfinance", _px_yf)]


def fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """가격 수집. 캐시 우선 → 부족분만 신규 → 드라이브 재적재(공용 인덱스).

    ★ 캐시 병합 규칙: 종목별로 '캐시가 요구 구간을 덮는가'를 판정한다.
      전체를 한 덩어리로 보고 '있다/없다'를 정하면, 캐시가 2020년까지만 있는 상태에서
      2016년 백테스트가 조용히 4년치 결측으로 돌아간다."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    s, e = as_ts(start), as_ts(end)
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=PRICE_COLS)

    cached = VAULT.get_table("price_daily", scope="shared")
    have: Dict[str, Tuple[pd.Timestamp, pd.Timestamp]] = {}
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached["code"] = cached["code"].map(to_code6)
        cached = cached.dropna(subset=["code", "date", "close"])
        if len(cached):
            frames.append(cached)
            g = cached.groupby("code", observed=True)["date"]
            have = {c: (lo, hi) for c, lo, hi in zip(g.min().index, g.min().values, g.max().values)}
            have = {c: (as_ts(lo), as_ts(hi)) for c, (lo, hi) in have.items()}
            LOG.info(f"공용 캐시에서 가격 {len(cached):,}행 / {cached['code'].nunique():,}종목 재사용")

    # 캐시가 요구 구간을 '충분히' 덮으면 재수집하지 않는다(양끝 10영업일 여유 허용)
    pad = pd.Timedelta(days=16)
    todo = [c for c in codes
            if c not in have or have[c][0] > s + pad or have[c][1] < e - pad]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 가격 부족 종목 {len(todo):,}건을 수집하지 않습니다. "
                     f"해당 종목의 이벤트는 수익률 결측으로 자동 제외됩니다(0으로 채우지 않음).")
        todo = []

    fail_reasons: Counter = Counter()
    src_hit: Counter = Counter()

    def _one(code: str) -> Optional[pd.DataFrame]:
        lo = s
        if code in have and have[code][0] <= s + pad:
            lo = max(s, have[code][1] - pd.Timedelta(days=7))   # 뒷부분만 증분 수집
        for name, fn in PRICE_CHAIN:
            try:
                d = fn(code, lo.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))
            except Exception as ex:                                       # noqa
                fail_reasons[f"{name}:{type(ex).__name__}"] += 1
                d = None
            if d is not None and len(d) >= 5:
                src_hit[name] += 1
                d = d.reindex(columns=PRICE_COLS)
                d["code"] = code
                return d
            fail_reasons[f"{name}:empty"] += 1
        return None

    if todo:
        LOG.info(f"가격 신규 수집 {len(todo):,}종목 (폴백 사슬: "
                 f"{' → '.join(n for n, _ in PRICE_CHAIN)})")
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 10), desc="가격 수집")
        frames += [d for d in res if d is not None and len(d)]

    if not frames:
        LOG.warn("가격 데이터를 하나도 확보하지 못했습니다. 네트워크 또는 소스 접근을 확인하세요.")
        return pd.DataFrame(columns=PRICE_COLS)

    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    px = px[(px["close"] > 0)]
    # 같은 (code,date) 가 여러 소스에서 오면 우선순위가 높은 소스를 남긴다
    prio = {n: i for i, (n, _) in enumerate(PRICE_CHAIN)}
    px["_p"] = px["src"].map(lambda x: prio.get(str(x), 99)).fillna(99)
    px = (px.sort_values(["code", "date", "_p"], kind="stable")
            .drop_duplicates(["code", "date"], keep="first")
            .drop(columns=["_p"]).reset_index(drop=True))
    px = px[(px["date"] >= s - pd.Timedelta(days=400)) & (px["date"] <= e)]

    if src_hit:
        LOG.table([[k, f"{v:,}"] for k, v in src_hit.most_common()],
                  ["소스", "성공 종목수"], ["l", "r"], title="가격 소스별 기여")
    if fail_reasons:
        LOG.debug(f"가격 수집 실패 사유 상위: {fail_reasons.most_common(8)}")

    if todo:
        VAULT.put_table("price_daily", px, scope="shared", domain="price",
                        source="fdr+naver+yfinance",
                        extra={"note": "일별 수정주가 OHLCV — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "price_daily", px, source="fdr+naver+yfinance")
    return downcast(px)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  PIT 시가총액 사다리
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """DART 「주식의 총수 현황」 — 비-KRX 환경에서 PIT 시총을 만드는 유일한 정품 경로.

    반환: corp_code, year, quarter, knowledge_date, shares_common
      · knowledge_date = 보고서 접수 가능 시점(보수적으로 기말 + 90일)
        ★ 이걸 기말로 잡으면 look-ahead 다. 사업보고서는 기말 후 90일 이내 제출이므로
          그 이후부터만 '알 수 있었던' 값으로 취급한다."""
    cols = ["corp_code", "year", "quarter", "knowledge_date", "shares_common"]
    if not DART_API_KEY:
        LOG.info("DART_API_KEY 가 없어 PIT 상장주식수를 건너뜁니다 → 시가총액은 "
                 "T2/T3/T4 근사로 자동 강등되며, 그 사실이 감사표에 표시됩니다.")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_stock_totqy", scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(cached):,}행 재사용")
        c = cached.copy()
        c["knowledge_date"] = as_ts_series(c["knowledge_date"])
        return c.reindex(columns=cols)
    if RUN_MODE == "CACHED":
        return pd.DataFrame(columns=cols)

    corps = [str(c).zfill(8) for c in dict.fromkeys(corp_codes) if str(c).strip()
             and str(c).lower() != "nan"]
    #  reprt_code: 11011=사업보고서(연간), 11014=3분기, 11012=반기, 11013=1분기
    jobs = [(c, y, rc) for c in corps for y in years for rc in ("11011",)]
    if not jobs:
        return pd.DataFrame(columns=cols)
    LOG.info(f"DART 주식총수 수집 {len(jobs):,}건 (기업 {len(corps):,} × 연도 {len(years)})")

    _QEND = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

    def _one(job):
        corp, year, rc = job
        js = http_json("https://opendart.fss.or.kr/api/stockTotqySttus.json", source="dart",
                       params={"crtfc_key": DART_API_KEY, "corp_code": corp,
                               "bsns_year": str(year), "reprt_code": rc}, tries=2)
        if not isinstance(js, dict) or js.get("status") != "000":
            return None
        tot = np.nan
        for row in js.get("list", []) or []:
            se = norm_text(row.get("se", ""))
            if "합계" in se or "보통주" in se:
                v = str(row.get("distb_stock_co", row.get("istc_totqy", ""))).replace(",", "")
                v = re.sub(r"[^\d.\-]", "", v)
                try:
                    n = float(v)
                except Exception:
                    continue
                if n > 0 and (np.isnan(tot) or "합계" in se):
                    tot = n
        if not np.isfinite(tot) or tot <= 0:
            return None
        mm, dd = _QEND[rc]
        kd = pd.Timestamp(year=year, month=mm, day=dd) + pd.Timedelta(days=90)
        return {"corp_code": corp, "year": year, "quarter": rc,
                "knowledge_date": kd, "shares_common": tot}

    res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
    rows = [r for r in res if r]
    if not rows:
        LOG.warn("DART 주식총수를 받지 못했습니다 — 시총은 근사 경로로 강등됩니다.")
        return pd.DataFrame(columns=cols)
    d = pd.DataFrame(rows)
    out = d.copy()
    out["knowledge_date"] = out["knowledge_date"].dt.strftime("%Y-%m-%d")
    VAULT.put_table("dart_stock_totqy", out, scope="shared", domain="fundamental",
                    source="dart:stockTotqySttus",
                    extra={"note": "PIT 상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "dart_stock_totqy", d, source="dart")
    LOG.ok(f"DART 주식총수 {len(d):,}행 / {d['corp_code'].nunique():,}사 확보 "
           f"→ PIT 시가총액 T1 경로 가동")
    return d[cols]


def fetch_current_shares(sec: pd.DataFrame) -> pd.DataFrame:
    """현재 상장주식수/시가총액 스냅샷 (T2/T3 사다리의 앵커).
    FDR 상장목록 캐시에 Stocks/Marcap 이 있으면 그걸 쓰고, 없으면 네이버로 소수만 보강한다."""
    out = pd.DataFrame({"code": sec["code"], "shares_now": np.nan, "marcap_now": np.nan})
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol")
        sh_c = col.get("stocks") or col.get("listedshares") or col.get("shares")
        mc_c = col.get("marcap") or col.get("marketcap")
        if code_c and (sh_c or mc_c):
            t = pd.DataFrame({"code": d[code_c].map(to_code6)})
            t["shares_now"] = pd.to_numeric(d[sh_c], errors="coerce") if sh_c else np.nan
            t["marcap_now"] = pd.to_numeric(d[mc_c], errors="coerce") if mc_c else np.nan
            t = t.dropna(subset=["code"]).drop_duplicates("code")
            out = out.drop(columns=["shares_now", "marcap_now"]).merge(t, on="code", how="left")
            n = int(out["shares_now"].notna().sum() + out["marcap_now"].notna().sum())
            LOG.info(f"현재 상장주식수/시총 스냅샷 {n:,}건 확보 (T2/T3 앵커)")
    return out


def build_marketcap_panel(px: pd.DataFrame, sec: pd.DataFrame,
                          shares_pit: pd.DataFrame, cur: pd.DataFrame) -> pd.DataFrame:
    """(code, date) → marcap, size_tier, adv20, turnover.  ★ 어느 사다리를 썼는지 tier 로 기록.

    T1: PIT 주식수(asof, knowledge_date 이하 최신) × 종가       ← 미래정보 없음
    T2: 현재 주식수 × 종가                                       ← 주식수 변동분이 과거로 투영됨
    T3: 현재 시총 × (종가 / 최근 종가)                            ← T2 와 동치이나 주식수 없이 가능
    T4: 시총 없음 → adv20 백분위로 사이즈 대용                    ← 랭크 전용
    """
    if px is None or len(px) == 0:
        return pd.DataFrame(columns=["code", "date", "close", "amount", "adv20",
                                     "marcap", "mc_tier", "turnover"])
    p = px[["code", "date", "close", "volume", "amount"]].copy()
    p["date"] = as_ts_series(p["date"])
    p = p.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"], kind="stable")
    p["amount"] = p["amount"].fillna(p["close"] * p["volume"])
    p["adv20"] = (p.groupby("code", observed=True)["amount"]
                   .transform(lambda s: s.rolling(20, min_periods=5).mean()))

    p["marcap"] = np.nan
    p["mc_tier"] = "T4"

    # ── T1: DART PIT 주식수 asof 조인 ──────────────────────────────────────────────────────
    if shares_pit is not None and len(shares_pit) and "corp_code" in sec.columns:
        c2c = (sec.dropna(subset=["corp_code"])
                  .assign(corp_code=lambda d: d["corp_code"].astype(str).str.zfill(8))
                  .drop_duplicates("code")[["code", "corp_code"]])
        sp = shares_pit.copy()
        sp["knowledge_date"] = as_ts_series(sp["knowledge_date"])
        sp["corp_code"] = sp["corp_code"].astype(str).str.zfill(8)
        sp = (sp.dropna(subset=["knowledge_date", "shares_common"])
                .merge(c2c, on="corp_code", how="inner")
                .sort_values(["code", "knowledge_date"], kind="stable")
                [["code", "knowledge_date", "shares_common"]])
        if len(sp):
            left = p[["code", "date"]].sort_values(["date", "code"], kind="stable")
            right = sp.sort_values(["knowledge_date", "code"], kind="stable")
            j = pd.merge_asof(left, right, left_on="date", right_on="knowledge_date",
                              by="code", direction="backward", allow_exact_matches=True)
            j = j.set_index(left.index)["shares_common"]
            sh = j.reindex(p.index)
            ok = sh.notna() & (sh > 0)
            set_where(p, ok, "marcap", (p["close"] * sh)[ok])
            set_where(p, ok, "mc_tier", "T1")

    # ── T2/T3: 현재 스냅샷 앵커 ────────────────────────────────────────────────────────────
    need = p["marcap"].isna()
    if need.any() and cur is not None and len(cur):
        cm = cur.dropna(subset=["code"]).drop_duplicates("code").set_index("code")
        sh_now = p["code"].map(cm["shares_now"]) if "shares_now" in cm.columns else pd.Series(np.nan, index=p.index)
        ok2 = need & sh_now.notna() & (sh_now > 0)
        set_where(p, ok2, "marcap", (p["close"] * sh_now)[ok2])
        set_where(p, ok2, "mc_tier", "T2")

        need = p["marcap"].isna()
        if need.any() and "marcap_now" in cm.columns:
            last_close = p.groupby("code", observed=True)["close"].transform("last")
            mc_now = p["code"].map(cm["marcap_now"])
            ok3 = need & mc_now.notna() & (mc_now > 0) & last_close.notna() & (last_close > 0)
            set_where(p, ok3, "marcap", (mc_now * p["close"] / last_close)[ok3])
            set_where(p, ok3, "mc_tier", "T3")

    # ── T4: 거래대금 백분위를 사이즈 대용으로 (랭크 전용) ──────────────────────────────────
    still = p["marcap"].isna()
    if still.any():
        # 같은 날 시총을 가진 종목들의 분포에 adv20 백분위를 사상해 '비교 가능한 값'으로 만든다.
        # 시총이 하나도 없는 날은 adv20 자체를 사이즈 축으로 쓴다(랭크만 쓰므로 무해).
        set_where(p, still, "marcap", p["adv20"][still])
        set_where(p, still, "mc_tier", "T4")

    p["turnover"] = safe_div(p["amount"], p["marcap"])

    tier = p["mc_tier"].value_counts()
    tot = max(len(p), 1)
    LOG.table([[t, f"{int(tier.get(t,0)):,}", f"{100*int(tier.get(t,0))/tot:5.1f}%", why]
               for t, why in [("T1", "DART PIT 주식수 × 종가 — 미래정보 없음"),
                              ("T2", "현재 주식수 × 종가 — 주식수 변동이 과거로 투영됨"),
                              ("T3", "현재 시총 × 종가비 — T2 의 축약"),
                              ("T4", "거래대금 백분위 대용 — 랭크 전용")]],
              ["사다리", "행수", "비중", "성질"], ["l", "r", "r", "l"],
              title="PIT 시가총액 사다리 감사 (KRX 미사용 · 시총은 랭크로만 사용)")
    t1 = 100.0 * int(tier.get("T1", 0)) / tot
    if t1 < 50:
        LOG.warn(f"PIT 정품(T1) 시총 비중이 {t1:.0f}% 입니다. 나머지는 '오늘의 주식수'를 과거에 "
                 f"투영한 근사라 미래정보가 일부 섞입니다. 이 전략에서 시총은 랭크·버킷으로만 "
                 f"쓰이므로 결론이 뒤집힐 위험은 낮지만, H4(사이즈 조건부) 해석 시 감안하세요. "
                 f"DART_API_KEY 를 넣으면 T1 비중이 크게 올라갑니다.")
    PIPE.io("OUT", "MEM", "marketcap_panel", p)
    return downcast(p)


def build_trading_calendar(px: pd.DataFrame) -> pd.DatetimeIndex:
    """실제 거래가 관측된 날 = 영업일 달력. 공휴일 테이블을 하드코딩하지 않는다.
    ★ 관측 종목이 적은 날(예: 데이터 소스 장애일)을 영업일로 잘못 잡으면 d+1 진입이
      존재하지 않는 날로 밀려 수익률이 통째로 결측이 된다 → 관측종목수 하한을 건다."""
    if px is None or len(px) == 0:
        return pd.DatetimeIndex([])
    cnt = px.groupby("date", observed=True)["code"].nunique().sort_index()
    if not len(cnt):
        return pd.DatetimeIndex([])
    # ★ 하한을 5로 고정하면 종목이 몇 개뿐인 상황(합성·리허설·소규모 유니버스)에서
    #   달력이 통째로 비고, 그러면 이벤트가 하나도 거래일에 스냅되지 않아 조용히 0건이 된다.
    #   '중앙값의 25%' 라는 상대 기준만 남기고 절대 하한은 표본 규모에 맞춰 낮춘다.
    med = float(cnt.median())
    thr = max(1.0, min(5.0, med * 0.5), med * 0.25)
    cal = pd.DatetimeIndex(cnt[cnt >= thr].index).sort_values()
    dropped = int((cnt < thr).sum())
    if dropped:
        LOG.info(f"거래일 달력: {len(cal):,}일 확정 (관측종목수 {thr:,.0f} 미만인 {dropped}일은 "
                 f"소스 장애로 보고 제외 — 진입일이 존재하지 않는 날로 밀리는 사고 방지)")
    else:
        LOG.info(f"거래일 달력: {len(cal):,}일 확정")
    return cal
