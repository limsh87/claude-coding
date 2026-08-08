

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-0  KRX-free 다중소스 계층 — PIT 유니버스 · 생존자편향 제거 · PIT 상장주식수            ║
# ║                                                                                          ║
# ║  ⚠ 배경: KRX(data.krx.co.kr / pykrx / kind.krx.co.kr)가 차단된 환경을 **정상 경로**로       ║
# ║    간주한다. KRX 는 '있으면 검증에 쓰는 보조'일 뿐, 어떤 결과도 KRX 에 의존하지 않는다.     ║
# ║                                                                                          ║
# ║  입력 : 없음(네트워크) / px_daily(일봉)                                                    ║
# ║  출력 : ① 상장·폐지 원장(생존자편향)  ② PIT 상장주식수 이력  ③ 소스 가용성 감사표          ║
# ║  실패 : 모든 함수는 예외 대신 빈 DataFrame 을 돌려주고, 무엇이 없는지 감사표에 남긴다.      ║
# ║                                                                                          ║
# ║  ── 생존자편향 4중 방어 ────────────────────────────────────────────────────────────────  ║
# ║   D1 FDR GitHub 폐지원장   raw.githubusercontent.com 정적 CSV. 1956년부터 전 폐지 종목의   ║
# ║                            상장일·폐지일·폐지사유·상장주식수. **KRX 서버를 거치지 않음**   ║
# ║   D2 가격 구간 실측        일봉의 첫/마지막 거래일로 상장·폐지 구간을 데이터에서 복원.      ║
# ║                            명단에 없는 종목도 잡는다(명단 결손의 최후 방어선)              ║
# ║   D3 DART 존재성           corpCode ↔ 종목코드. 이름·사명변경 보강                         ║
# ║   D4 KRX 월말 스냅샷       NCQ_USE_KRX=True 일 때만. 검증·보강 용도(합집합, 절대 교집합 아님)║
# ║                                                                                          ║
# ║  ── PIT 시가총액 = PIT 상장주식수 × 그 시점 수정종가 ──────────────────────────────────    ║
# ║   S1 DART 주식총수현황(stockTotqySttus) — 접수일자 기준 진짜 PIT. 증자·분할·감자 반영       ║
# ║   S2 폐지원장의 ListingShares — 폐지 종목의 상장주식수(그 종목 생애 상수로 사용)            ║
# ║   S3 현재 상장목록의 Stocks — 최신 값. 과거 적용 시 근사(증자 미반영)이며 그 사실을 표기    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

NCQ_SOURCE_STATUS: "OrderedDict[str, dict]" = OrderedDict()


def ncq_src(name: str, ok: bool, n: int = -1, note: str = "", krx: bool = False):
    NCQ_SOURCE_STATUS[name] = {"name": name, "ok": bool(ok), "n": int(n), "note": note, "krx": krx}


def ncq_krx_enabled() -> bool:
    """KRX 계열 경로를 쓸지. 기본은 False(차단 이력). 자격증명 없이 True 여도 켜지 않는다."""
    if not bool(globals().get("NCQ_USE_KRX", False)):
        return False
    if not (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW) and not KRX_OPENAPI_KEY:
        return False
    return True


def ncq_configure_sources() -> None:
    """KRX 차단 상황에 맞게 전역 수집 경로를 재배선한다. main 초반에 1회 호출.

    ★ 이게 없으면 pykrx 가 설치된 환경에서 종목마다 KRX 로 먼저 붙었다가 타임아웃으로 실패한다.
      2,600종목 × 타임아웃이면 그것만으로 수십 분을 버리고, 차단을 더 악화시킨다.
    """
    G = globals()
    if ncq_krx_enabled():
        LOG.info("KRX 경로 활성 — 월말 스냅샷을 '검증·보강'으로만 사용합니다(의존하지 않음).")
        return
    # ① pykrx 자체를 끈다 (KRXGate.warmup / 가격 체인 / 스냅샷이 전부 이 핸들을 본다)
    if G.get("pykrx_stock") is not None:
        G["pykrx_stock"] = None
    # ② 가격 폴백 체인에서 KRX 계열을 제거하고 네이버를 1순위로
    try:
        G["PRICE_CHAIN"] = [("naver", _px_naver), ("fdr", _px_fdr), ("yfinance", _px_yf)]
    except Exception:
        pass
    # ③ 유니버스 스냅샷 비활성
    G["UNIVERSE_SNAPSHOT_FREQ"] = "off"
    LOG.warn("KRX 경로 비활성 (NCQ_USE_KRX=False 또는 자격증명 없음) — "
             "네이버 차트 → FDR → yfinance 순으로 가격을 받고, 상장·폐지와 상장주식수는 "
             "FDR GitHub 정적 캐시 + DART + 가격구간 실측으로 구성합니다. "
             "이 경로만으로 PIT 유니버스와 생존자편향 제거가 완결됩니다.")
    manifest_put("krx_enabled", False)


# ── D1. FDR GitHub 폐지원장 (풍부한 컬럼 버전) ──────────────────────────────────────────────
NCQ_DELIST_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "reason", "industry", "shares_listing", "secugroup"]


def ncq_fdr_delisting_full() -> pd.DataFrame:
    """폐지 종목 원장. build/10 의 fetch_fdr_delisting 보다 많은 컬럼을 살린다.

    실측 컬럼: Symbol, Name, Market, SecuGroup, Kind, ListingDate, DelistingDate, Reason,
              ArrantEnforceDate, ArrantEndDate, Industry, ParValue, ListingShares, ToSymbol, ToName
    ★ ListingDate 가 여기에만 있다. 현재 상장목록 CSV 에는 상장일 컬럼이 없어서, KIND 가 막히면
      '현재 상장 종목의 상장일'은 가격 구간 실측(D2)으로 복원해야 한다.
    """
    d = _fdr_cache_csv("listing/delisting")
    if d is None or len(d) == 0:
        ncq_src("FDR폐지원장", False, 0, "정적 CSV 수신 실패 — 생존자편향 제거가 약해집니다")
        LOG.warn("폐지 종목 원장을 받지 못했습니다. 생존자편향 제거는 '가격 구간 실측'에만 "
                 "의존하게 됩니다(약화). raw.githubusercontent.com 접근을 확인하세요.")
        return pd.DataFrame(columns=NCQ_DELIST_COLS)
    col = {str(c).strip().lower(): c for c in d.columns}

    def g(*names, default=None):
        for n in names:
            if n in col:
                return d[col[n]]
        return pd.Series([default] * len(d))

    t = pd.DataFrame({
        "code": g("symbol", "code", "isu_cd", "isu_srt_cd").map(to_code6),
        "name": g("name", "isu_nm", default="").astype(str).str.strip(),
        "market": g("market", default="").astype(str),
        "listing_date": as_ts_series(g("listingdate", "listing_date")),
        "delisting_date": as_ts_series(g("delistingdate", "delisting_date", "dedate")),
        "reason": g("reason", default="").astype(str),
        "industry": g("industry", "sector", default="").astype(str),
        "shares_listing": pd.to_numeric(g("listingshares", "stocks", "listing_shares"),
                                        errors="coerce"),
        "secugroup": g("secugroup", "kind", default="").astype(str),
    })
    n_raw = len(t)
    t = t.dropna(subset=["code"])
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (이른 쪽을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 줄어든다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    # 주권(보통주)이 아닌 것은 여기서 표시만 하고 버리지 않는다 — 제외는 유니버스 단계에서.
    n_ok = int(t["delisting_date"].notna().sum())
    LOG.ok(f"[D1] 폐지 종목 원장 {len(t):,}건 (원본 {n_raw:,} → 코드정규화·중복제거 후 {len(t):,}) · "
           f"폐지일 보유 {n_ok:,}건 · 상장일 보유 "
           f"{int(t['listing_date'].notna().sum()):,}건 — KRX 무관 정적 경로")
    ncq_src("FDR폐지원장", True, len(t), "생존자편향 1차 방어 · 상장일/폐지일/폐지사유/상장주식수")
    return t


def ncq_fdr_listing_full() -> pd.DataFrame:
    """현재 상장목록(종가·시가총액·상장주식수 포함). 상장일 컬럼은 없다."""
    d = _fdr_cache_csv("listing/krx")
    if d is None or len(d) == 0:
        ncq_src("FDR상장목록", False, 0, "정적 CSV 수신 실패")
        return pd.DataFrame(columns=["code", "name", "market", "close", "marcap", "shares"])
    col = {str(c).strip().lower(): c for c in d.columns}
    code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
    if not code_c:
        ncq_src("FDR상장목록", False, 0, f"종목코드 컬럼 없음: {list(d.columns)[:8]}")
        return pd.DataFrame(columns=["code", "name", "market", "close", "marcap", "shares"])
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[col["name"]].astype(str).str.strip() if "name" in col else "",
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "close": pd.to_numeric(d[col["close"]], errors="coerce") if "close" in col else np.nan,
        "marcap": pd.to_numeric(d[col["marcap"]], errors="coerce") if "marcap" in col else np.nan,
        "shares": pd.to_numeric(d[col["stocks"]], errors="coerce") if "stocks" in col else np.nan,
    }).dropna(subset=["code"]).drop_duplicates("code")
    need = t["shares"].isna() & t["marcap"].notna() & (t["close"] > 0)
    if need.any():
        t.loc[need, "shares"] = t.loc[need, "marcap"] / t.loc[need, "close"]
    LOG.ok(f"[S3] 현재 상장목록 {len(t):,}건 (상장주식수 보유 {int(t['shares'].notna().sum()):,}건)")
    ncq_src("FDR상장목록", True, len(t), "현재 시점 상장주식수 — 과거 적용 시 근사")
    return t


# ── D2. 가격 구간 실측 ──────────────────────────────────────────────────────────────────────
def ncq_listing_intervals_from_prices(px_daily: pd.DataFrame, panel_start, panel_end
                                      ) -> pd.DataFrame:
    """일봉의 첫/마지막 거래일로 상장·폐지 구간을 복원한다.

    ★ 이것이 명단 결손의 최후 방어선이다. 폐지원장에 없는 종목도, 상장일 컬럼이 없는 종목도
      '언제부터 언제까지 실제로 거래됐는가'는 가격 데이터가 알고 있다.
    ★ 주의: 데이터 수집 시작일에 붙어 있는 first_trade 는 '상장일'이 아니라 '수집 시작일'이다.
      이걸 상장일로 쓰면 기존 상장사 전부가 신규 상장으로 둔갑해 시즈닝에 걸린다(유니버스 붕괴).
      → 수집 시작일 + 10영업일 이내면 상장일 미상(NaT)으로 둔다.
    ★ 마지막 거래일이 패널 종료보다 한참 이르면 폐지로 본다. 단, 거래정지 후 재개도 있으므로
      임계를 넉넉히(90일) 잡고, 폐지원장에 있는 종목은 원장 날짜를 우선한다.
    """
    cols = ["code", "first_trade", "last_trade", "n_days"]
    if px_daily is None or len(px_daily) == 0:
        return pd.DataFrame(columns=cols)
    p = px_daily[["code", "date"]].dropna()
    g = p.groupby("code", observed=True)["date"]
    T = pd.DataFrame({"first_trade": g.min(), "last_trade": g.max(),
                      "n_days": g.size()}).reset_index()
    ps, pe = as_ts(panel_start), as_ts(panel_end)
    edge = ps + pd.Timedelta(days=21)
    T["listing_date_est"] = T["first_trade"].where(T["first_trade"] > edge)
    T["delisting_date_est"] = (T["last_trade"] + pd.offsets.MonthEnd(1)).where(
        T["last_trade"] < pe - pd.Timedelta(days=90))
    n_l = int(T["listing_date_est"].notna().sum())
    n_d = int(T["delisting_date_est"].notna().sum())
    LOG.ok(f"[D2] 가격 구간 실측 {len(T):,}종목 — 신규상장 추정 {n_l:,}건 · 폐지 추정 {n_d:,}건")
    ncq_src("가격구간실측", True, len(T), "명단 결손의 최후 방어선(상장·폐지 구간을 데이터에서 복원)")
    return T


def ncq_enrich_security_master(sec: pd.DataFrame, px_daily: pd.DataFrame,
                               dead: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """종목 마스터에 상장일·폐지일·상장주식수를 다중소스로 채운다(생존자편향 제거의 완성).

    우선순위: 폐지원장(D1) > 기존 마스터 값 > 가격 구간 실측(D2)
    ★ 절대 규칙: 어떤 소스로도 근거를 못 찾은 종목을 **버리지 않는다.** 버리는 순간 그게
      생존자편향이다. 근거가 없으면 상장일=가격 첫 거래일, 폐지일=NaT 로 두어 유니버스에 남긴다.
    """
    if sec is None or sec.empty:
        return sec
    s = sec.copy()
    for c in ("listing_date", "delisting_date"):
        if c not in s.columns:
            s[c] = pd.NaT
        s[c] = as_ts_series(s[c])
    if "shares_master" not in s.columns:
        s["shares_master"] = np.nan

    if dead is not None and len(dead):
        d = dead.drop_duplicates("code").set_index("code")
        idx = s["code"].to_numpy()
        for col_src, col_dst in (("listing_date", "listing_date"),
                                 ("delisting_date", "delisting_date"),
                                 ("shares_listing", "shares_master")):
            if col_src not in d.columns:
                continue
            v = d[col_src].reindex(idx)
            v.index = s.index
            if col_dst.endswith("_date"):
                v = as_ts_series(v)
                s[col_dst] = v.where(v.notna(), s[col_dst])
            else:
                s[col_dst] = pd.to_numeric(v, errors="coerce").where(
                    pd.to_numeric(v, errors="coerce").notna(), s[col_dst])

    T = ncq_listing_intervals_from_prices(px_daily, BACKTEST_START, BACKTEST_END)
    if len(T):
        t = T.set_index("code")
        idx = s["code"].to_numpy()
        ld_est = as_ts_series(t["listing_date_est"].reindex(idx)); ld_est.index = s.index
        dd_est = as_ts_series(t["delisting_date_est"].reindex(idx)); dd_est.index = s.index
        first = as_ts_series(t["first_trade"].reindex(idx)); first.index = s.index
        n_fill_l = int((s["listing_date"].isna() & ld_est.notna()).sum())
        n_fill_d = int((s["delisting_date"].isna() & dd_est.notna()).sum())
        s["listing_date"] = s["listing_date"].where(s["listing_date"].notna(), ld_est)
        s["delisting_date"] = s["delisting_date"].where(s["delisting_date"].notna(), dd_est)
        # 그래도 상장일이 없으면 '첫 거래일'로 최소한의 근거를 부여한다(행을 버리지 않기 위함).
        still = s["listing_date"].isna() & first.notna()
        s.loc[still, "listing_date"] = first[still]
        LOG.info(f"[D2] 상장일 {n_fill_l:,}건 · 폐지일 {n_fill_d:,}건을 가격 구간으로 보강, "
                 f"근거 없던 {int(still.sum()):,}종목에 첫 거래일을 상장일로 부여(유니버스 유지).")

    n_no = int(s["listing_date"].isna().sum())
    n_del = int(s["delisting_date"].notna().sum())
    LOG.table([["종목 마스터 전체", f"{len(s):,}"],
               ["상장일 확보", f"{len(s)-n_no:,} ({100*(len(s)-n_no)/max(len(s),1):.0f}%)"],
               ["폐지일 확보", f"{n_del:,} ({100*n_del/max(len(s),1):.0f}%)"],
               ["근거 부족(유지)", f"{n_no:,}"]],
              ["항목", "값"], ["l", "r"],
              title="생존자편향 방어 상태 (근거가 없어도 종목을 버리지 않습니다)")
    if n_del < 500:
        LOG.warn(f"폐지 종목이 {n_del:,}건입니다. 10년 구간이면 통상 1,000건 이상이어야 합니다. "
                 f"생존자편향이 그만큼 남아 있으니 결과 해석 시 반드시 감안하세요.")
        PIPE.note("WARN: 폐지 표본 부족 — 생존자편향 완전 제거 미달")
    manifest_put("survivorship", {"n_codes": int(len(s)), "n_delisted": n_del,
                                  "n_no_listing_date": n_no})
    return s


# ── S1. DART 주식총수현황 = PIT 상장주식수 ──────────────────────────────────────────────────
DART_SHARES_URL = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
NCQ_DART_SHARES_MAX_CALLS = 12000        # 일 20,000 한도 안에서 안전 마진
_NCQ_DART_CALLS = {"n": 0}


def _ncq_dart_shares_one(job: Tuple[str, int, str]) -> Optional[List[dict]]:
    corp, year, rc = job
    js = http_json(DART_SHARES_URL, source="dart", tries=2,
                   params={"crtfc_key": DART_API_KEY, "corp_code": corp,
                           "bsns_year": str(year), "reprt_code": rc})
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st == "020":
        LOG.warn("DART 일일 호출한도(020)에 도달했습니다 — 여기까지 받은 주식수 이력을 저장하고 "
                 "나머지는 근사 경로로 대체합니다. 내일 재실행하면 정확히 이어받습니다.")
        return "LIMIT"                                   # type: ignore[return-value]
    if st != "000":
        return None
    rows = []
    for it in (js.get("list") or []):
        se = str(it.get("se", ""))
        # '합계' 행만 쓴다. 보통주/우선주 행을 모두 더하면 이중계상이 된다.
        if "합계" not in se:
            continue
        v = re.sub(r"[^\d]", "", str(it.get("istc_totqy") or it.get("isu_stock_totqy") or ""))
        if not v:
            continue
        rcept = str(it.get("rcept_no") or "")
        kd = rcept[:8] if len(rcept) >= 8 else f"{year+1}0401"
        rows.append({"corp_code": corp, "shares": float(v),
                     "knowledge_date": kd, "bsns_year": year, "reprt_code": rc})
    return rows or None


def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int],
                      max_calls: int = NCQ_DART_SHARES_MAX_CALLS) -> pd.DataFrame:
    """DART 주식총수현황으로 PIT 상장주식수 이력을 만든다(KRX 무관).

    ★ knowledge_date = 접수일자(rcept_no 앞 8자리). 결산일이 아니다. 결산일을 쓰면
      아직 공시되지 않은 주식수를 그 시점에 알았다고 주장하는 것이라 명백한 미래누수다.
    ★ 호출량이 크므로 ① 공용 캐시 재활용 ② 우선순위 순서 ③ 상한 을 모두 적용한다.
    """
    cols = ["corp_code", "shares", "knowledge_date", "bsns_year", "reprt_code"]
    if not DART_API_KEY:
        ncq_src("DART주식총수", False, 0, "DART_API_KEY 미입력 — 시가총액이 근사 경로로 낮아집니다")
        LOG.warn("DART_API_KEY 가 없어 PIT 상장주식수를 만들 수 없습니다. 시가총액은 "
                 "'현재 주식수 × 과거 종가' 근사가 되며, 증자가 잦은 소형주에서 오차가 큽니다. "
                 "무료·즉시 발급이므로 넣어 두시길 권합니다: https://opendart.fss.or.kr")
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("dart_shares_history", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        have = set(zip(c["corp_code"].astype(str), c["bsns_year"].astype(int),
                       c["reprt_code"].astype(str)))
        frames.append(c)
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(c):,}행 재사용 ({len(have):,} 조합)")

    jobs = [(str(c), int(y), "11011") for y in sorted(years, reverse=True)
            for c in corp_codes if (str(c), int(y), "11011") not in have]
    if RUN_MODE == "CACHED":
        jobs = []
    if len(jobs) > max_calls:
        LOG.warn(f"DART 주식총수 요청 대상이 {len(jobs):,}건이라 상한 {max_calls:,}건으로 자릅니다. "
                 f"최근 연도·우선순위 종목부터 받았으므로, 재실행하면 나머지를 이어받습니다. "
                 f"이번 실행에서 못 받은 구간은 근사 경로로 대체되고 감사표에 표시됩니다.")
        jobs = jobs[:max_calls]

    new_rows: List[dict] = []
    if jobs:
        LOG.info(f"DART 주식총수현황 {len(jobs):,}건 수집 (PIT 상장주식수 — 시가총액의 분모)")
        stop = False
        CH = 500
        for k0 in range(0, len(jobs), CH):
            if stop:
                break
            chunk = jobs[k0:k0 + CH]
            res = pmap_io(_ncq_dart_shares_one, chunk, workers=min(N_WORKERS_IO, 8),
                          desc=f"DART 주식수 {k0//CH+1}/{(len(jobs)-1)//CH+1}")
            for r in res:
                if r == "LIMIT":
                    stop = True
                    continue
                if r:
                    new_rows.extend(r)
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        ncq_src("DART주식총수", False, 0, "수집 실패")
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["corp_code", "bsns_year", "reprt_code"], keep="last")
    if new_rows:
        VAULT.put_table("dart_shares_history", S, scope="shared", domain="universe",
                        source="opendart:stockTotqySttus",
                        extra={"note": "PIT 상장주식수(접수일자 기준) — 전 전략 공용"})
    LOG.ok(f"[S1] DART 주식총수 {len(S):,}행 · {S['corp_code'].nunique():,}개 법인 (진짜 PIT)")
    ncq_src("DART주식총수", True, len(S), "접수일자 기준 PIT 상장주식수 — KRX 무관")
    return S


def ncq_build_shares_history(sec: pd.DataFrame, dart_shares: pd.DataFrame,
                             listing_now: pd.DataFrame) -> pd.DataFrame:
    """PIT 상장주식수 이력을 하나의 긴 테이블로 통합한다.

    반환: [code, knowledge_date, shares, shares_src]  — merge_asof(backward) 용
    """
    out: List[pd.DataFrame] = []
    c2corp = {}
    if sec is not None and len(sec) and "corp_code" in sec.columns:
        c2corp = (sec.dropna(subset=["corp_code"])
                     .drop_duplicates("code").set_index("corp_code")["code"].to_dict())

    if dart_shares is not None and len(dart_shares) and c2corp:
        d = dart_shares.copy()
        d["code"] = d["corp_code"].astype(str).map(c2corp)
        d = d.dropna(subset=["code"])
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"])
        d["shares_src"] = "dart_pit"
        out.append(d[["code", "knowledge_date", "shares", "shares_src"]])

    # 폐지 종목: 상장주식수를 생애 상수로 사용(그 종목의 마지막 알려진 값)
    if sec is not None and len(sec) and "shares_master" in sec.columns:
        m = sec.dropna(subset=["shares_master"])[["code", "listing_date", "shares_master"]].copy()
        if len(m):
            m["knowledge_date"] = as_ts_series(m["listing_date"]).fillna(as_ts("1990-01-01"))
            m = m.rename(columns={"shares_master": "shares"})
            m["shares_src"] = "delist_registry"
            out.append(m[["code", "knowledge_date", "shares", "shares_src"]])

    # 현재 상장목록: 아주 이른 시점에 놓아 '최후 폴백'이 되게 한다(근사임을 라벨로 남김)
    if listing_now is not None and len(listing_now):
        n = listing_now.dropna(subset=["shares"])[["code", "shares"]].copy()
        if len(n):
            n["knowledge_date"] = as_ts("1990-01-01")
            n["shares_src"] = "approx_const_shares"
            out.append(n[["code", "knowledge_date", "shares", "shares_src"]])

    if not out:
        return pd.DataFrame(columns=["code", "knowledge_date", "shares", "shares_src"])
    S = pd.concat(out, ignore_index=True)
    S["shares"] = pd.to_numeric(S["shares"], errors="coerce")
    # 시간 해상도를 ns 로 못박는다(merge_asof 의 dtype 일치 요구 — ncq_ns 주석 참조)
    S["knowledge_date"] = pd.to_datetime(S["knowledge_date"], errors="coerce")
    try:
        S["knowledge_date"] = S["knowledge_date"].astype("datetime64[ns]")
    except Exception:
        pass
    S["code"] = S["code"].astype(str)
    S = S[(S["shares"] > 0)].dropna(subset=["code", "knowledge_date"])
    # 같은 (code, knowledge_date) 가 여러 소스에서 오면 PIT 소스를 우선한다.
    pri = {"dart_pit": 0, "delist_registry": 1, "approx_const_shares": 2}
    S["_p"] = S["shares_src"].map(pri).fillna(9)
    S = (S.sort_values(["code", "knowledge_date", "_p"])
           .drop_duplicates(["code", "knowledge_date"], keep="first")
           .drop(columns=["_p"])
           .sort_values("knowledge_date", kind="stable")
           .reset_index(drop=True))
    mix = Counter(S["shares_src"])
    LOG.table([[k, f"{v:,}", {"dart_pit": "진짜 PIT (접수일자 기준)",
                              "delist_registry": "폐지원장 상장주식수(생애 상수)",
                              "approx_const_shares": "현재 주식수(과거 적용 시 근사)"}.get(k, "")]
               for k, v in mix.most_common()],
              ["주식수 소스", "행수", "성질"], ["l", "r", "l"],
              title="PIT 상장주식수 소스 구성 — 시가총액의 분모")
    return S


def ncq_report_sources():
    """소스 가용성 감사표 — '무엇이 살아 있고 무엇이 죽었는지'를 한 화면에."""
    if not NCQ_SOURCE_STATUS:
        return
    LOG.banner("데이터 소스 가용성 감사",
               "KRX 차단을 정상 상황으로 간주합니다. KRX 항목이 전부 꺼져 있어도 결과는 성립합니다.")
    rows = []
    for s in NCQ_SOURCE_STATUS.values():
        rows.append([s["name"], "KRX" if s["krx"] else "KRX-free",
                     "✔ 가용" if s["ok"] else "✘ 불가",
                     f"{s['n']:,}" if s["n"] >= 0 else "—", _trunc(s["note"], 52)])
    LOG.table(rows, ["소스", "계열", "상태", "건수", "역할 / 비고"], ["l", "c", "c", "r", "l"])
    krxfree_ok = [s for s in NCQ_SOURCE_STATUS.values() if s["ok"] and not s["krx"]]
    if not krxfree_ok:
        LOG.error("KRX-free 소스가 하나도 살아 있지 않습니다. 이 상태에서는 PIT 유니버스를 "
                  "구성할 수 없으므로 결과가 무효입니다. 네트워크에서 "
                  "raw.githubusercontent.com / finance.naver.com / opendart.fss.or.kr "
                  "접근이 가능한지 먼저 확인하세요.")
    manifest_put("source_status", {k: {"ok": v["ok"], "n": v["n"]}
                                   for k, v in NCQ_SOURCE_STATUS.items()})
