

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
#
#   ★★ 호출 격자 설계 (예전 설계의 낭비를 명시적으로 뒤집는다) ★★
#     (구) 전 법인 × 전 연도 데카르트 곱 = 3,500 × 12 ≈ 42,000 건을 만들어 놓고
#          "12,000 건에서 자른다"로 대응했다. 두 가지가 동시에 틀렸다:
#            ① 격자 자체가 낭비였다. 2018년에 상장폐지된 법인에게 2019~2026 사업보고서를
#               묻는 호출은 100% 헛수고다(응답은 '조회된 데이터 없음'). 반대로 2022년
#               신규상장 법인에게 2015~2020 을 묻는 것도 마찬가지다.
#            ② 잘라내는 상한이 실제 잔량과 무관했다.
#     (신) 격자를 먼저 줄이고, 상한은 없앤다. 줄이는 근거는 셋 다 무손실이다:
#            A. 상장 구간 제한 : 각 법인의 [상장연도-1, 폐지연도] 범위 밖은 애초에 존재하지 않는다.
#            B. 공시 가능 시점 : bsns_year Y 의 사업보고서는 Y+1년 봄에나 접수된다. 백테스트
#               종료일까지 접수될 수 없는 연도는 PIT 상 쓸 수도 없으므로 요청하지 않는다.
#            C. 소형주 사전선별 : 이 전략의 유니버스는 시총 하위 N 이다. '현재/최종 주식수 ×
#               그 시점 종가'로 만든 거친 시총이 컷오프의 NCQ_DART_MCAP_MARGIN 배 안에
#               **한 번도** 들어온 적 없는 법인은 정밀 주식수를 받아도 유니버스에 못 들어온다.
#               ※ 주식수를 전혀 모르는 종목은 배제 근거가 없으므로 **항상 후보로 남긴다**
#                 (근거 없음을 배제 사유로 쓰는 순간 그게 생존자편향이다).
#     이 셋을 적용하면 통상 42,000 → 12,000~16,000 수준으로 떨어진다. 그리고 남은 것도
#     '상한'이 아니라 '서버가 020 을 줄 때까지'로 소진한다(L0-D DartKeyPool).
DART_SHARES_URL = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
NCQ_DART_SHARES_MAX_CALLS = 0            # 0 = 상한 없음(서버 020 까지). >0 이면 사용자 지정 상한


def _ncq_dart_shares_one(job: Tuple[str, int, str]) -> Optional[List[dict]]:
    corp, year, rc = job
    js = dart_json(DART_SHARES_URL, {"corp_code": corp, "bsns_year": str(year),
                                     "reprt_code": rc}, source="dart", tries=2)
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
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


def ncq_crude_mcap(sec: pd.DataFrame, px_daily: pd.DataFrame, listing_now: pd.DataFrame,
                   months: pd.DatetimeIndex) -> pd.DataFrame:
    """호출 0건으로 만드는 '거친 시가총액' [code, month, mcap_crude].

    분모는 이미 손에 있는 상수 주식수다: 생존 종목은 FDR 상장목록의 현재 주식수,
    폐지 종목은 폐지원장의 상장주식수. 증자·감자는 반영되지 않는다.
    → **유니버스 판정에는 절대 쓰지 않는다.** 오직 "이 법인에게 DART 정밀 주식수를
      물어볼 가치가 있는가"를 가르는 사전선별용이다. 그래서 여유배수를 크게 잡는다.
    """
    out_cols = ["code", "month", "mcap_crude"]
    if px_daily is None or len(px_daily) == 0:
        return pd.DataFrame(columns=out_cols)
    sh: Dict[str, float] = {}
    if listing_now is not None and len(listing_now) and "shares" in listing_now.columns:
        for c, v in zip(listing_now["code"].astype(str),
                        pd.to_numeric(listing_now["shares"], errors="coerce")):
            if v and v > 0:
                sh[c] = float(v)
    if sec is not None and len(sec) and "shares_master" in sec.columns:
        for c, v in zip(sec["code"].astype(str),
                        pd.to_numeric(sec["shares_master"], errors="coerce")):
            if v and v > 0:
                sh.setdefault(c, float(v))
    if not sh:
        return pd.DataFrame(columns=out_cols)
    p = px_daily[["code", "date", "close"]].dropna(subset=["date", "close"]).copy()
    p["month"] = as_ts_series(p["date"]) + pd.offsets.MonthEnd(0)
    p = p[p["month"].isin(months)]
    if not len(p):
        return pd.DataFrame(columns=out_cols)
    m = (p.sort_values("date").groupby(["code", "month"], observed=True)
           .tail(1)[["code", "month", "close"]])
    m["code"] = m["code"].astype(str)
    m["mcap_crude"] = m["close"].astype(float) * m["code"].map(sh)
    return m.dropna(subset=["mcap_crude"])[out_cols].reset_index(drop=True)


def ncq_plan_dart_share_jobs(sec: pd.DataFrame, px_daily: pd.DataFrame,
                             listing_now: pd.DataFrame, months: pd.DatetimeIndex,
                             cached_keys: Optional[set] = None,
                             bottom_n: int = None, margin: float = None,
                             reprt_codes: Optional[Sequence[str]] = None
                             ) -> Tuple[List[Tuple[str, int, str]], List[list]]:
    """DART 주식총수 호출 격자를 무손실로 줄인다. 반환: (jobs, 깔때기표 rows)

    A 상장구간 · B 공시가능시점 · C 소형주 사전선별 — 근거는 함수 위 주석 참조.
    정렬은 '중간에 끊겨도 쓸모 있는 것부터'가 되도록 (최근 연도 → 작은 시총) 순이다.
    """
    bottom_n = int(bottom_n if bottom_n is not None else NCQ_UNIVERSE_BOTTOM_N)
    margin = float(margin if margin is not None else NCQ_DART_MCAP_MARGIN)
    rcs = [str(r) for r in (reprt_codes or NCQ_DART_REPRT_CODES or ["11011"])]
    cached_keys = cached_keys or set()
    as_of = as_ts(BACKTEST_END) or months.max()
    y0, y1 = int(months.min().year) - 1, int(months.max().year)

    # ── B. bsns_year Y 사업보고서는 Y+1년 3~4월 접수. 그 이후를 알 수 없으면 요청 자체가 무의미
    years_all = [y for y in range(y0, y1 + 1)
                 if (as_ts(f"{y + 1}-03-31") or as_of) <= as_of]
    if not years_all:
        years_all = [y0]

    s = sec.dropna(subset=["corp_code"]).copy() if (sec is not None and len(sec)) else pd.DataFrame()
    if not len(s) or "corp_code" not in s.columns:
        return [], []
    s["code"] = s["code"].astype(str)
    s["corp_code"] = s["corp_code"].astype(str)
    n_full = len(s) * len(range(y0, y1 + 1)) * len(rcs)

    # ── A. 상장 구간: [상장연도-1, 폐지연도]. 밖은 존재하지 않는 보고서다.
    ld = as_ts_series(s["listing_date"]) if "listing_date" in s.columns else pd.Series(pd.NaT, index=s.index)
    dd = as_ts_series(s["delisting_date"]) if "delisting_date" in s.columns else pd.Series(pd.NaT, index=s.index)
    s["_ylo"] = ld.dt.year.fillna(y0).astype(int) - 1
    s["_yhi"] = dd.dt.year.fillna(y1 + 5).astype(int)

    # ── C. 소형주 사전선별
    crude = ncq_crude_mcap(s, px_daily, listing_now, months)
    keep_codes: Optional[set] = None
    n_known = n_small = 0
    if len(crude):
        c = crude.copy()
        c["_rk"] = c.groupby("month")["mcap_crude"].rank(method="first")
        # 그 달의 'bottom_n 번째로 작은 시총' = 컷오프. 종목 수가 N 미만인 달은 전부 포함된다.
        cut = c[c["_rk"] <= bottom_n].groupby("month")["mcap_crude"].max().rename("cut")
        j = c.merge(cut, left_on="month", right_index=True, how="left")
        ever_small = j.loc[j["mcap_crude"] <= j["cut"] * margin, "code"].astype(str).unique()
        known = set(c["code"].astype(str))
        n_known, n_small = len(known), len(ever_small)
        # 주식수를 몰라 거친 시총조차 못 만든 종목은 배제 근거가 없다 → 전부 남긴다.
        keep_codes = set(ever_small) | (set(s["code"]) - known)

    prio: Dict[str, float] = crude.groupby("code")["mcap_crude"].min().to_dict() if len(crude) else {}
    rows: List[tuple] = []
    n_pre_cache = 0
    n_keep_corp = 0
    for code, corp, ylo, yhi in zip(s["code"], s["corp_code"], s["_ylo"], s["_yhi"]):
        if keep_codes is not None and code not in keep_codes:
            continue
        n_keep_corp += 1
        pk = float(prio.get(code, 0.0))
        for y in years_all:
            if y < ylo or y > yhi:
                continue
            for rc in rcs:
                n_pre_cache += 1
                if (corp, int(y), str(rc)) in cached_keys:
                    continue
                rows.append((-y, pk, corp, int(y), str(rc)))
    rows.sort(key=lambda t: (t[0], t[1]))                        # 최근 연도 → 작은 시총 순
    jobs = [(c, y, r) for (_a, _b, c, y, r) in rows]

    n_B = len(s) * len(years_all) * len(rcs)
    n_C = n_keep_corp * len(years_all) * len(rcs)
    funnel = [
        ["① 전 법인 × 전 연도 (예전 격자)", f"{n_full:,}", "이 방식이 4만 건을 만들었다"],
        ["② 공시 가능 연도만 (B)", f"{n_B:,}", f"-{max(0, n_full - n_B):,}"],
        ["③ 소형주 후보만 (C)", f"{n_C:,}", f"-{max(0, n_B - n_C):,}"],
        ["④ 상장·폐지 구간 안만 (A)", f"{n_pre_cache:,}", f"-{max(0, n_C - n_pre_cache):,}"],
        ["⑤ 캐시 차감 후 실제 호출", f"{len(jobs):,}",
         f"전체 대비 {100 * (1 - len(jobs) / max(n_full, 1)):.0f}% 절감"],
    ]
    LOG.table(funnel, ["DART 주식총수 호출 격자", "건수", "비고"], ["l", "r", "l"],
              title="호출량 절감 깔때기 (상한으로 자르는 대신 격자를 줄인다)")
    if len(crude):
        LOG.info(f"소형주 사전선별: 거친시총 산출 {n_known:,}종목 중 컷오프×{margin:g} 안에 "
                 f"한 번이라도 들어온 {n_small:,}종목 + 주식수 미상 "
                 f"{len(s) - n_known:,}종목(배제 근거 없음 → 전부 유지)")
    manifest_put("dart_share_plan", {"grid_full": int(n_full), "grid_planned": int(len(jobs)),
                                     "reprt_codes": rcs, "margin": margin})
    return jobs, funnel


def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int],
                      max_calls: int = NCQ_DART_SHARES_MAX_CALLS,
                      jobs: Optional[List[Tuple[str, int, str]]] = None) -> pd.DataFrame:
    """DART 주식총수현황으로 PIT 상장주식수 이력을 만든다(KRX 무관).

    ★ knowledge_date = 접수일자(rcept_no 앞 8자리). 결산일이 아니다. 결산일을 쓰면
      아직 공시되지 않은 주식수를 그 시점에 알았다고 주장하는 것이라 명백한 미래누수다.
    ★ 호출량: ① 공용 캐시 재활용 ② 격자 축소(ncq_plan_dart_share_jobs) ③ 중요도 정렬
      ④ **실시간 잔량 소진**(상한 없음 — 서버가 020 을 줄 때까지). max_calls>0 을 명시한
      경우에만 사용자 지정 상한으로 자른다.
    """
    cols = ["corp_code", "shares", "knowledge_date", "bsns_year", "reprt_code"]
    pool = dart_pool()
    if not pool.configured():
        ncq_src("DART주식총수", False, 0, "DART 키 미입력 — 시가총액이 근사 경로로 낮아집니다")
        LOG.warn("DART 인증키가 없어 PIT 상장주식수를 만들 수 없습니다. 시가총액은 "
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

    if jobs is None:      # 계획이 없으면(구 호출부·테스트) 최소한의 격자만 만든다
        rcs = [str(r) for r in (NCQ_DART_REPRT_CODES or ["11011"])]
        jobs = [(str(c), int(y), rc) for y in sorted(years, reverse=True)
                for c in corp_codes for rc in rcs if (str(c), int(y), rc) not in have]
    else:
        jobs = [j for j in jobs if (str(j[0]), int(j[1]), str(j[2])) not in have]
    if RUN_MODE == "CACHED":
        jobs = []
    if max_calls and len(jobs) > max_calls:
        LOG.warn(f"사용자 지정 상한 NCQ_DART_SHARES_MAX_CALLS={max_calls:,} 로 자릅니다 "
                 f"(대상 {len(jobs):,}건). 0 으로 두면 실시간 잔량만큼 끝까지 씁니다.")
        jobs = jobs[:max_calls]

    new_rows: List[dict] = []
    if jobs:
        dart_plan_note(len(jobs), "DART 주식총수현황 (PIT 상장주식수 — 시가총액의 분모)")
        CH = 500
        n_ch = (len(jobs) - 1) // CH + 1
        for k0 in range(0, len(jobs), CH):
            # ★ 멈춤 판단은 오직 서버의 020(→ 모든 키 소진). 우리 추정 잔량으로 멈추지 않는다.
            if pool.exhausted:
                LOG.warn(f"잔여 {len(jobs) - k0:,}건은 오늘 받지 못했습니다 — 받은 만큼 저장합니다. "
                         f"재실행하면 정확히 이 지점부터 이어받습니다.")
                break
            chunk = jobs[k0:k0 + CH]
            res = pmap_io(_ncq_dart_shares_one, chunk, workers=min(N_WORKERS_IO, 8),
                          desc=f"DART 주식수 {k0 // CH + 1}/{n_ch}")
            for r in res:
                if r:
                    new_rows.extend(r)
        pool.save()
        pool.report("DART 호출량 — 주식총수 수집 후")
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
    S = ncq_split_adjust_shares(S)
    mix = Counter(S["shares_src"])
    LOG.table([[k, f"{v:,}", {"dart_pit": "진짜 PIT (접수일자 기준) · 액면분할 보정 적용",
                              "delist_registry": "폐지원장 상장주식수(생애 상수)",
                              "approx_const_shares": "현재 주식수(증자 미반영 근사)"}.get(k, "")]
               for k, v in mix.most_common()],
              ["주식수 소스", "행수", "성질"], ["l", "r", "l"],
              title="PIT 상장주식수 소스 구성 — 시가총액의 분모")
    return S


def ncq_split_adjust_shares(S: pd.DataFrame) -> pd.DataFrame:
    """상장주식수를 **수정주가와 같은 단위**로 맞춘다 (shares_eff).

    ★★ 이게 없으면 시가총액이 액면분할 배수만큼 틀린다 — 조용히, 그리고 계통적으로.
      우리가 곱하는 종가는 전 소스가 **수정주가**다(네이버 siseJson · FDR · pykrx 모두).
      반면 DART 주식총수현황이 주는 주식수는 **그 시점의 실제(미수정) 주식수**다.
      1:5 액면분할한 종목의 2018년을 보자.
        실제:   50,000원 × 100만주 = 500억   (참 시총)
        계산:   10,000원(수정) × 100만주(PIT) = 100억   ← 1/5 로 축소
      이 종목은 '시총 하위 1000' 에 부당 편입되고, 분할은 대개 주가 강세 뒤에 일어나므로
      **사후 성과가 좋은 종목이 계통적으로 소형주 풀에 섞인다.** 정확히 우리가 피해야 할 편향.
      역설적으로 '현재 주식수 × 과거 수정종가'(approx) 는 분할에 대해서는 정확하다.

    보정 방법: 주식수 시계열의 연속 비율에서 **분할로 보이는 것만** 골라 소급 반영한다.
      · 비율이 1.8배 이상이면서 정수배에 가까우면 분할(반대는 병합)로 본다.
      · 유상증자·자사주 소각 같은 '실제 자본 변동'은 수정주가가 반영하지 않으므로 건드리지 않는다.
        (분할만 걸러내는 이유가 이것이다 — 둘을 같이 처리하면 반대 방향으로 또 틀린다)
      · 판정이 애매하면 보정하지 않는다. 잘못된 보정이 미보정보다 위험하다.
    """
    if S is None or S.empty:
        return S
    out = S.copy()
    out["shares_eff"] = pd.to_numeric(out["shares"], errors="coerce")
    dart = out["shares_src"].astype(str) == "dart_pit"
    if not bool(dart.any()):
        return out

    n_split = 0
    n_code = 0
    for code, g in out[dart].groupby("code", observed=True):
        g = g.sort_values("knowledge_date")
        v = pd.to_numeric(g["shares"], errors="coerce").to_numpy(dtype=float)
        if len(v) < 2 or not np.all(np.isfinite(v)) or np.any(v <= 0):
            continue
        ratios = v[1:] / v[:-1]
        split_k = np.ones(len(ratios))
        for i, r in enumerate(ratios):
            k = None
            if r >= 1.8:
                k = round(float(r))
                if k < 2 or abs(r - k) > 0.05 * k:
                    k = None
            elif 0 < r <= (1.0 / 1.8):
                inv = round(1.0 / float(r))
                if inv < 2 or abs((1.0 / r) - inv) > 0.05 * inv:
                    k = None
                else:
                    k = 1.0 / inv
            if k is not None:
                split_k[i] = float(k)
                n_split += 1
        if np.allclose(split_k, 1.0):
            continue
        # 관측 i 이후에 일어난 분할들의 누적 배수를 소급 적용 → 오늘의 단위로 환산
        cum_after = np.ones(len(v))
        for i in range(len(v) - 1):
            cum_after[i] = float(np.prod(split_k[i:]))
        out.loc[g.index, "shares_eff"] = v * cum_after
        n_code += 1
    if n_split:
        LOG.ok(f"액면분할/병합 {n_split:,}건({n_code:,}종목)을 상장주식수에 소급 반영했습니다 — "
               f"수정주가와 단위를 맞춰야 시가총액이 배수만큼 틀리지 않습니다.")
        manifest_put("split_adjusted_codes", int(n_code))
    return out


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
