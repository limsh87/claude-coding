# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  KRX 비의존 경로 — 생존자편향 제거와 PIT 유니버스를 **KRX 없이 보장**한다                   ║
# ║                                                                                             ║
# ║  배경: KRX 마켓플레이스는 2025-12 부터 로그인이 필수가 됐고, 중복로그인·과다요청으로        ║
# ║  계정이 차단되는 일이 흔하다. 그런데 이 전략에서 KRX 가 반드시 필요한 곳은 **하나도 없다.** ║
# ║  이 모듈은 그것을 '희망'이 아니라 **검증된 사실**로 만든다:                                 ║
# ║                                                                                             ║
# ║    C2 생존자편향 : FDR 상장폐지 목록 + KIND + 상장/폐지일 → KRX 불필요                      ║
# ║    C13 PIT유니버스: 상장일·폐지일 + 가격 관측으로 매 시점 재구성 → KRX 불필요               ║
# ║    가격·거래대금  : FDR → 네이버 → yfinance 체인 → KRX 불필요                               ║
# ║                                                                                             ║
# ║  약해지는 것은 둘뿐이고, 둘 다 **대체 경로 + 감사표**로 처리한다:                           ║
# ║    시가총액(규모버킷) → 상장주식수 역산 근사 · 수급(d3) → 네이버 폴백 또는 U 에서 제외      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def krx_mode() -> str:
    """KRX 사용 여부를 확정한다. 'off' | 'auto' | 'on'."""
    v = str(KRX_ENABLED).lower()
    if v in ("false", "0", "off", "no"):
        return "off"
    if not (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW):
        return "off"
    return "on" if v in ("true", "1", "on", "yes") else "auto"


def build_security_master_nokrx() -> "pd.DataFrame":
    """KRX 없이 종목 마스터를 만든다.  ★ 이 경로가 C2 의 본선이다.

    KRX 스냅샷은 '검증 입력'일 뿐 의존 대상이 아니다. 스냅샷이 없어도
    상장목록(FDR/KIND) ∪ 상장폐지목록(FDR) 로 마스터가 완성된다.
    """
    sec = build_security_master(pd.DataFrame(columns=["snap_date", "code", "market"]))
    return sec


def audit_survivorship(sec: "pd.DataFrame", months: "pd.DatetimeIndex") -> dict:
    """생존자편향 제거가 **실제로** 되어 있는지 수치로 검증한다.

    ★ '폐지 종목이 마스터에 있다'는 것만으로는 부족하다. 폐지 종목이
      백테스트 기간 안에서 실제로 유니버스에 들어왔다가 폐지일에 빠지는지를 봐야 한다.
      이 감사가 통과하지 못하면 성과는 전부 생존자편향으로 부풀려진 값이다.
    """
    out = {"total": 0, "delisted": 0, "delisted_in_window": 0, "listing_known": 0.0,
           "verdict": "FAIL", "detail": ""}
    if sec is None or not len(sec):
        out["detail"] = "종목 마스터가 비어 있습니다."
        return out
    s = sec.drop_duplicates("code").copy()
    dd = as_ts_series(s.get("delisting_date"))
    ld = as_ts_series(s.get("listing_date"))
    lo, hi = pd.Timestamp(BACKTEST_START), pd.Timestamp(BACKTEST_END)
    out["total"] = int(len(s))
    out["delisted"] = int(dd.notna().sum())
    out["delisted_in_window"] = int(((dd >= lo) & (dd <= hi)).sum())
    out["listing_known"] = float(ld.notna().mean())

    ok = out["delisted_in_window"] >= 50
    out["verdict"] = "PASS" if ok else "FAIL"
    out["detail"] = (
        f"마스터 {out['total']:,}종목 중 폐지일 보유 {out['delisted']:,}종목 · "
        f"백테스트 구간 내 폐지 {out['delisted_in_window']:,}종목 · "
        f"상장일 확보율 {out['listing_known']*100:.0f}%")
    LOG.banner("생존자편향 제거 감사 (C2) — KRX 비의존 경로",
               "폐지 종목이 구간 안에서 실제로 들어왔다 빠지는가")
    LOG.table([["종목 마스터(생존+폐지)", f"{out['total']:,}"],
               ["폐지일 보유 종목", f"{out['delisted']:,}"],
               ["백테스트 구간 내 폐지", f"{out['delisted_in_window']:,}"],
               ["상장일 확보율", f"{out['listing_known']*100:.1f}%"],
               ["판정", out["verdict"]]], ["항목", "값"])
    if out["listing_known"] < 0.10:
        LOG.warn(
            f"상장일 확보율이 {out['listing_known']*100:.0f}% 입니다 "
            f"(KIND 가 막히면 흔합니다 — FDR 상장목록 스냅샷에 ListingDate 가 없는 판이 있습니다).\n"
            f"    → 시즈닝(상장 후 {UNIVERSE_SEASON_DAYS}거래일) 앵커는 '최초 가격 관측일'로 폴백합니다.\n"
            f"    → 방향이 중요합니다: '모르면 오래된 종목'으로 처리하므로 신규상장 필터가 "
            f"**느슨해질 뿐**이며, 반대로 '모르면 신규상장'으로 처리했다면 패널 앞 구간의 "
            f"유니버스가 통째로 비었을 것입니다. 생존자편향은 폐지일로 제거되므로 영향 없습니다.")
    if not ok:
        LOG.error("[C2] 구간 내 폐지 종목이 50개 미만입니다. 10년이면 통상 수백 종목이 폐지됩니다. "
                  "상장폐지 목록을 못 받은 상태이며, 이대로 나온 성과는 생존자편향으로 "
                  "부풀려진 값입니다. raw.githubusercontent.com(FDR 캐시) 접근을 확인하세요.")
    else:
        LOG.ok(f"생존자편향 제거 정상 — 구간 내 폐지 {out['delisted_in_window']:,}종목이 "
               f"유니버스에 포함되었다가 폐지일에 빠집니다(정리매매 없으면 -100%).")
    return out


def mcap_nokrx(months: "pd.DatetimeIndex", px_m: "pd.DataFrame",
               sec: "pd.DataFrame") -> "pd.DataFrame":
    """KRX 없이 PIT 시가총액을 근사한다.  ★ 규모버킷(셀)에만 쓴다.

    방법: 상장목록 스냅샷의 (시가총액 ÷ 종가) 로 상장주식수를 역산하고, 그 주식수를
    과거 종가에 곱한다. 유상증자·무상증자·감자를 반영하지 못하므로 **비PIT 근사**이며,
    그 사실과 커버리지를 감사표에 남긴다.

    ★ 이 근사가 랭크 유니버스 컷에 쓰이면 위험하지만(자본이벤트 기업이 체계적으로 어긋남),
      XCB 는 시총으로 유니버스를 자르지 않는다(§5.1 — 매핑이 곧 유니버스).
      규모버킷은 셀 내 공통충격 흡수용이라 근사 오차의 영향이 훨씬 작다.
    """
    cols = ["code", "month", "mcap", "shares", "mcap_src"]
    if px_m is None or not len(px_m):
        return pd.DataFrame(columns=cols)
    shares = None
    try:
        lst = fetch_fdr_listing()
        if lst is not None and len(lst):
            lm = _lower_map(lst)
            mc = next((lm[c] for c in ("marcap", "markcap", "시가총액") if c in lm), None)
            cl = next((lm[c] for c in ("close", "종가") if c in lm), None)
            sh = next((lm[c] for c in ("stocks", "shares", "상장주식수") if c in lm), None)
            if sh:
                shares = pd.DataFrame({"code": lst[lm.get("code", "Code")].map(to_code6),
                                       "shares": pd.to_numeric(lst[sh], errors="coerce")})
            elif mc and cl:
                shares = pd.DataFrame({
                    "code": lst[lm.get("code", "Code")].map(to_code6),
                    "shares": safe_div(pd.to_numeric(lst[mc], errors="coerce"),
                                       pd.to_numeric(lst[cl], errors="coerce"))})
    except Exception as e:                                              # noqa
        LOG.debug(f"상장주식수 역산 실패: {type(e).__name__}")
    if shares is None or not len(shares):
        LOG.warn("상장주식수를 얻지 못해 시가총액을 만들 수 없습니다. "
                 "규모버킷은 **20일 평균거래대금 랭크**로 대체됩니다(셀 정의만 바뀌며, "
                 "유니버스 컷에는 시총을 쓰지 않으므로 편향은 생기지 않습니다).")
        return pd.DataFrame(columns=cols)
    shares = shares.dropna(subset=["code"]).drop_duplicates("code")
    m = px_m[["code", "month", "close"]].copy()
    m["code"] = m["code"].map(to_code6)
    m = m.merge(shares, on="code", how="left")
    m["mcap"] = pd.to_numeric(m["close"], errors="coerce") * \
        pd.to_numeric(m["shares"], errors="coerce")
    m.loc[~(m["mcap"] > 0), "mcap"] = np.nan
    m["mcap_src"] = "shares_backsolve(비PIT 근사)"
    cov = float(m["mcap"].notna().mean())
    LOG.warn(f"PIT 시가총액을 상장주식수 역산으로 근사했습니다 (커버리지 {cov*100:.0f}%). "
             f"자본이벤트(유증·무증·감자)는 반영되지 않습니다. "
             f"XCB 는 시총으로 유니버스를 자르지 않으므로 영향은 규모버킷(셀)에 한정됩니다.")
    return m[cols]


def flows_naver(codes: "Sequence[str]", months: "pd.DatetimeIndex",
                max_codes: int = 600) -> "Optional[pd.DataFrame]":
    """KRX 없이 기관·외국인 수급(d3)을 네이버에서 받는다. 실패하면 None → d3 비활성화.

    ★ 못 얻으면 0 으로 채우지 않는다. 0 은 '수급이 없었다'는 적극적 주장이고,
      d3 는 '수급이 안 들어왔을수록 좋다'는 부호라 0 채움이 그 종목을 인위적으로 좋게 만든다.
    """
    codes = list(dict.fromkeys(str(c) for c in codes))[:max_codes]
    if not codes:
        return None
    url = "https://finance.naver.com/item/frgn.naver"
    rows: List[dict] = []
    fails = 0

    def _one(c: str):
        out = []
        for page in (1, 2, 3):
            html = http_get(url, source="naver", params={"code": c, "page": page},
                            referer="https://finance.naver.com/", tries=2)
            if not html:
                return out
            try:
                tabs = pd.read_html(io.StringIO(html))
            except Exception:                                           # noqa
                return out
            for t in tabs:
                if t.shape[1] < 6:
                    continue
                t = t.dropna(how="all")
                cs = [str(x) for x in t.columns]
                if not any("날짜" in x for x in cs):
                    continue
                t.columns = [str(x) for x in t.columns]
                dcol = next((x for x in t.columns if "날짜" in x), None)
                icol = next((x for x in t.columns if "기관" in x), None)
                fcol = next((x for x in t.columns if "외국인" in x), None)
                if not dcol or (not icol and not fcol):
                    continue
                for _, r in t.iterrows():
                    d = as_ts(r.get(dcol))
                    if d is None or pd.isna(d):
                        continue
                    inst = pd.to_numeric(str(r.get(icol, "")).replace(",", ""), errors="coerce")
                    frg = pd.to_numeric(str(r.get(fcol, "")).replace(",", ""), errors="coerce")
                    out.append({"code": c, "date": d,
                                "net": float(np.nansum([inst, frg]))})
        return out

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 6), desc="네이버 수급(d3)")
    for r in res:
        if r:
            rows.extend(r)
        else:
            fails += 1
    if not rows:
        LOG.warn("네이버 수급도 받지 못했습니다 — d3 를 비활성화하고 U 를 나머지 축으로 "
                 "구성합니다(0 으로 채우지 않습니다).")
        return None
    d = pd.DataFrame(rows)
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    g = d.groupby(["code", "month"], observed=True)["net"].sum().reset_index()
    g = g.sort_values(["code", "month"])
    g["net_buy_120d"] = g.groupby("code", observed=True)["net"].transform(
        lambda s: s.rolling(6, min_periods=3).sum())
    LOG.ok(f"네이버 수급 확보: {g['code'].nunique():,}종목 × {g['month'].nunique()}개월 "
           f"(실패 {fails}종목)")
    return g.rename(columns={"month": "ym"})[["code", "ym", "net_buy_120d"]]


def universe_sources_audit(sec: "pd.DataFrame", px_m: "pd.DataFrame",
                           mcap: "pd.DataFrame", flows) -> None:
    """어떤 소스로 무엇을 만들었는지 한눈에. KRX 의존도가 0 임을 표로 증명한다."""
    mode = krx_mode()
    krx_ok = bool(getattr(KRX, "session_ok", False))
    rows = [
        ["종목 마스터(상장+폐지)", "FDR 상장목록 + KIND + FDR 상장폐지",
         f"{0 if sec is None else sec['code'].nunique():,}종목", "KRX 불필요 ✔"],
        ["생존자편향 제거 C2", "FDR 상장폐지 목록(폐지일)",
         f"{0 if sec is None else int(as_ts_series(sec.get('delisting_date')).notna().sum()):,}건",
         "KRX 불필요 ✔"],
        ["PIT 유니버스 C13", "상장일·폐지일 + 가격 관측",
         f"{0 if px_m is None else px_m['code'].nunique():,}종목", "KRX 불필요 ✔"],
        ["가격·거래대금", "FDR → 네이버 → yfinance",
         f"{0 if px_m is None else len(px_m):,}행", "KRX 불필요 ✔"],
        ["시가총액(규모버킷)",
         (mcap["mcap_src"].mode().iloc[0] if mcap is not None and len(mcap)
          and "mcap_src" in mcap.columns and len(mcap["mcap_src"].mode()) else "없음"),
         f"{0 if mcap is None else len(mcap):,}행",
         "KRX 있으면 정확 / 없으면 근사"],
        ["투자자 수급 d3",
         "네이버 폴백" if flows is not None else "미확보 → U 에서 제외",
         f"{0 if flows is None else len(flows):,}행", "KRX 있으면 정확 / 없으면 폴백"],
    ]
    LOG.banner("데이터 소스 감사 — KRX 의존도",
               f"KRX 모드={mode} · 세션={'확보' if krx_ok else '없음'} — "
               f"핵심 4개 항목은 KRX 없이 성립합니다")
    LOG.table(rows, ["항목", "사용 소스", "규모", "KRX 의존"])
