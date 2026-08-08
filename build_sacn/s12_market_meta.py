# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-M  시장 메타 — 시가총액 / BM / 제외플래그 / 업종 / 개인비중  (전면 재작성)             ║
# ║                                                                                          ║
# ║  ■ 실측에서 무슨 일이 있었나                                                              ║
# ║      "pykrx 없음 — 시가총액 스냅샷을 건너뜁니다"  (파이썬 3.14 에서 설치 실패)             ║
# ║      "pykrx 없음 — PBR 스냅샷 불가"                                                       ║
# ║    라이브러리 하나가 없다는 이유로 아래가 전부 죽었다:                                     ║
# ║      ⓐ §5 시총 하한 500억      ⓑ §6.3 직교화의 log(MktCap)                                ║
# ║      ⓒ 시총하위 1000 비교아암  ⓓ §6.3 직교화의 BM  (BM 표가 1행으로 붕괴)                 ║
# ║                                                                                          ║
# ║  ■ 재작성 원칙 — 단일 라이브러리 의존을 없앤다                                             ║
# ║    pykrx 는 결국 data.krx.co.kr 을 부르는 얇은 껍데기다. 그 호출을 우리가 직접 하면        ║
# ║    (s10b krx_all_price / krx_all_perpbr) pykrx 유무와 무관해진다.                          ║
# ║    소스 체인:  pykrx → KRX MDC 벌크 → 근사(현재 상장주식수 × 과거 종가)                    ║
# ║    각 행에 출처(src)를 남겨, 근사분이 얼마나 섞였는지 감사표에서 보이게 한다.               ║
# ║    ★ 근사는 '조용히' 쓰지 않는다. 비중을 표로 찍고 OPEN_QUESTIONS 에 기록한다.             ║
# ║                                                                                          ║
# ║  ★ 호출량: 신호에 쓰이는 것은 전부 '날짜 1개 = 전종목 1호출' 이다.                         ║
# ║    시총 120 + 펀더멘털 120 ≈ 240호출로 10년이 끝난다(종목축 루프면 20배).                  ║
# ║    예외 둘은 기본 비활성이며 신호에 쓰이지 않는다:                                         ║
# ║      · fetch_retail_share  — 종목축(H3 보조축).  COLLECT_RETAIL_SHARE=False 가 기본        ║
# ║      · attach_bm_fallback  — DART 배치(100사/호출). PBR 스냅샷이 빈 곳만 보강              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MKTCAP_COLS = ["code", "month", "mktcap", "shares", "close_m", "amount_m", "src"]
FUND_COLS = ["code", "month", "bps", "per", "pbr", "eps", "div_yield", "bm", "src"]


def _month_snap_dates(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    """각 월의 스냅샷 기준일(월말). 휴장일이면 소스 쪽에서 직전 영업일로 당겨준다."""
    return [as_ts(m) for m in months]


def _have_months(cached: Optional[pd.DataFrame], col: str = "month") -> set:
    if cached is None or not len(cached) or col not in cached.columns:
        return set()
    try:
        return set(as_ts_series(cached[col]).dt.strftime("%Y-%m").dropna())
    except Exception:
        return set()


def _krx_snapshot(fn_name: str, day: str) -> Optional[pd.DataFrame]:
    """pykrx 스냅샷 호출을 KRXG 게이트로 직렬화한다.

    pykrx 는 스레드마다 재로그인하고 KRX 는 중복 로그인 시 이전 세션을 끊는다.
    병렬로 부르면 JSON 대신 로그인 HTML 을 받아 엉뚱한 곳에서 터진다 — 반드시 직렬화.
    """
    if pykrx_stock is None:
        return None
    fn = getattr(pykrx_stock, fn_name, None)
    if fn is None:
        return None
    d = KRXG.call(fn, day, market="ALL")
    if d is None or not hasattr(d, "empty") or d.empty:
        d = KRXG.call(fn, day)
    if d is None or not hasattr(d, "empty") or d.empty:
        return None
    return d


def _mcap_from_pykrx(m: pd.Timestamp) -> Optional[pd.DataFrame]:
    d = _krx_snapshot("get_market_cap_by_ticker", m.strftime("%Y%m%d"))
    if d is None:
        return None
    t = d.reset_index()
    pick = {}
    for c in t.columns:
        s = str(c)
        if s in ("티커", "종목코드", "index"):
            pick["code"] = c
        elif "시가총액" in s:
            pick["mktcap"] = c
        elif "상장주식수" in s:
            pick["shares"] = c
        elif s == "종가":
            pick["close_m"] = c
        elif "거래대금" in s:
            pick["amount_m"] = c
    if "code" not in pick or "mktcap" not in pick:
        return None

    def _n(k):
        return (pd.to_numeric(t[pick[k]], errors="coerce") if k in pick
                else pd.Series(np.nan, index=t.index))
    g = pd.DataFrame({"code": t[pick["code"]].map(to_code6), "month": m,
                      "mktcap": _n("mktcap"), "shares": _n("shares"),
                      "close_m": _n("close_m"), "amount_m": _n("amount_m"), "src": "pykrx"})
    return g.dropna(subset=["code"])


def _mcap_from_krx_bulk(m: pd.Timestamp) -> Optional[pd.DataFrame]:
    d = krx_all_price(m)
    if d is None or not len(d):
        return None
    g = pd.DataFrame({"code": d["code"], "month": m,
                      "mktcap": d.get("mktcap"), "shares": d.get("shares"),
                      "close_m": d.get("close"), "amount_m": d.get("amount"), "src": "krx_bulk"})
    # 시총이 안 오면 상장주식수 × 종가로 만든다 (같은 응답 안의 값이므로 근사가 아니다)
    need = g["mktcap"].isna() & g["shares"].notna() & g["close_m"].notna()
    g.loc[need, "mktcap"] = g.loc[need, "shares"] * g.loc[need, "close_m"]
    return g.dropna(subset=["code"])


def _fdr_shares_snapshot() -> Optional[pd.DataFrame]:
    """FDR 상장목록의 '현재' 상장주식수. 근사 폴백의 원천 (1회 호출, 캐시)."""
    cur = globals().get("_FDR_SHARES")
    if cur is not None:
        return cur if len(cur) else None
    out = pd.DataFrame()
    if fdr is not None:
        for mkt in ("KRX", "KOSPI", "KOSDAQ"):
            try:
                limiter("fdr").wait()
                d = fdr.StockListing(mkt)
            except Exception:
                continue
            if d is None or not len(d):
                continue
            d = d.rename(columns={c: str(c) for c in d.columns})
            code_c = next((c for c in d.columns if c in ("Code", "Symbol", "종목코드")), None)
            sh_c = next((c for c in d.columns if c in ("Stocks", "상장주식수", "ListedShares")), None)
            if code_c is None or sh_c is None:
                continue
            out = pd.DataFrame({"code": d[code_c].map(to_code6),
                                "shares_now": pd.to_numeric(d[sh_c], errors="coerce")})
            out = out.dropna(subset=["code", "shares_now"]).drop_duplicates("code")
            break
    globals()["_FDR_SHARES"] = out
    return out if len(out) else None


def fetch_mktcap_monthly(months: pd.DatetimeIndex,
                         panel: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """월말 시가총액·상장주식수 스냅샷. 1개월 = 1호출. 소스 체인으로 pykrx 부재를 견딘다."""
    cached = cache_recall("krx_mktcap_monthly", scope="shared")
    have = _have_months(cached)
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"시가총액 월말 스냅샷: 캐시 충족 "
               f"({len(cached) if cached is not None else 0:,}행, 신규 호출 0건)")
        return _finalize_mcap(cached, months, panel, wrote=False)

    use_pykrx = pykrx_stock is not None
    use_bulk = krx_bulk_available()
    LOG.table([["pykrx", "사용 가능" if use_pykrx else "미설치 → 건너뜀"],
               ["KRX MDC 벌크", "사용 가능" if use_bulk else "응답 없음"],
               ["근사 폴백", "FDR 현재 상장주식수 × 과거 종가"]],
              ["시총 소스", "상태"], ["l", "l"], title="시가총액 소스 체인")
    if not (use_pykrx or use_bulk):
        LOG.warn("시가총액 실측 소스가 모두 불가 — 근사 폴백으로만 채웁니다. "
                 "§5 시총하한과 시총하위1000 아암은 '근사 기준'임이 산출물에 명시됩니다.")
        return _finalize_mcap(cached, months, panel, wrote=False)

    LOG.info(f"시가총액 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails, partial = [], 0, 0
    for m in tqdm(todo, desc="시총 스냅샷", disable=not VERBOSE, mininterval=TQDM_MININTERVAL):
        g = _mcap_from_pykrx(m) if use_pykrx else None
        if (g is None or not len(g)) and use_bulk:
            g = _mcap_from_krx_bulk(m)
        if g is None or not len(g):
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 시총 수집을 중단하고 "
                         f"여기까지 받은 분량을 저장합니다.")
                break
            continue
        # ★ 부분 응답 방어. 종목수가 이웃 달 대비 급감한 스냅샷은 '진실'이 아니라 '사고'다.
        #   그대로 받아들이면 그 달만 유니버스가 훅 줄고(시총하한을 못 넘김) 백테스트가
        #   조용히 이가 빠진다. 200 종목짜리 응답은 예외를 내지 않으므로 여기서 세야 한다.
        if rows:
            med = float(np.median([len(x) for x in rows[-6:]]))
            if med > 0 and len(g) < 0.5 * med:
                partial += 1
                LOG.warn(f"{m:%Y-%m} 시총 스냅샷이 {len(g):,}종목으로 직전 중앙값 "
                         f"{med:,.0f}종목의 절반 미만입니다 — 부분 응답으로 보고 버립니다.")
                fails += 1
                continue
        fails = 0
        rows.append(g)
    if partial:
        LOG.warn(f"부분 응답으로 버린 달 {partial}개 — 다음 실행에서 자동 재시도합니다 "
                 f"(캐시에 저장되지 않았으므로 '미보유'로 남습니다).")

    # ★ 캐시를 '앞'에 둔다. keep="last" 와 함께 쓰면 신규 수집분이 캐시를 이긴다.
    #   반대로 두면 재수집해도 낡은 값이 살아남아, 정정이 영원히 반영되지 않는다.
    frames = ([cached.reindex(columns=MKTCAP_COLS)] if cached is not None and len(cached) else []) \
        + [f for f in rows if len(f)]
    if not frames:
        return _finalize_mcap(cached, months, panel, wrote=False)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if rows:
        note_new_data("krx_mktcap_monthly", sum(len(f) for f in rows), "shared", "price", "krx")
        persist("krx_mktcap_monthly", out, scope="shared", domain="price",
                source="pykrx/krx_bulk monthly cap snapshot")
    return _finalize_mcap(out, months, panel, wrote=True)


def _finalize_mcap(mc: Optional[pd.DataFrame], months: pd.DatetimeIndex,
                   panel: Optional[pd.DataFrame], wrote: bool) -> pd.DataFrame:
    """실측이 못 채운 (code, month) 를 근사로 메우고, 출처 비중을 표로 남긴다.

    근사 = 현재 상장주식수 × 그 달의 종가.  액면분할·유상증자·자사주소각을 반영하지 못하므로
    과거로 갈수록 오차가 커진다. 그래도 '시총 순위'는 대체로 보존되므로 하위1000 아암의
    구성에는 쓸 만하다 — 단, 절대 수준(§5 의 500억 하한)에는 쓰면 안 된다.
    ★ 그래서 근사분에는 mktcap_is_approx=True 를 세우고, 하한 필터는 실측분에만 적용한다.
    """
    base = mc.copy() if mc is not None and len(mc) else pd.DataFrame(columns=MKTCAP_COLS)
    if "src" not in base.columns:
        base["src"] = "unknown"
    if panel is not None and len(panel):
        sh = _fdr_shares_snapshot()
        if sh is not None and len(sh):
            p = panel[["code", "month", "close"]].dropna().copy()
            p["month"] = as_ts_series(p["month"])
            p = p[p["month"].isin(pd.DatetimeIndex([as_ts(m) for m in months]))]
            p = p.merge(sh, on="code", how="inner")
            p["mktcap"] = p["shares_now"] * p["close"]
            p = p.rename(columns={"shares_now": "shares", "close": "close_m"})
            p["amount_m"] = np.nan
            p["src"] = "approx_fdr_shares"
            if len(base):
                seen = set(zip(base["code"].astype(str),
                               as_ts_series(base["month"]).astype("int64")))
                keep = [(str(c), int(mm.value)) not in seen
                        for c, mm in zip(p["code"], as_ts_series(p["month"]))]
                p = p[pd.Series(keep, index=p.index)]
            if len(p):
                base = pd.concat([base, p.reindex(columns=MKTCAP_COLS)], ignore_index=True)
    if not len(base):
        LOG.error("시가총액을 한 행도 확보하지 못했습니다 — §5 시총하한과 시총하위1000 아암이 "
                  "비활성화됩니다. 결과 해석 시 이 점을 반드시 감안하세요.")
        return pd.DataFrame(columns=MKTCAP_COLS + ["mktcap_is_approx"])
    base["month"] = as_ts_series(base["month"])
    base = base.drop_duplicates(subset=["code", "month"], keep="first").reset_index(drop=True)
    base["mktcap_is_approx"] = base["src"].astype(str).str.startswith("approx")
    n = len(base)
    tab = base["src"].value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/n:.1f}%"] for k, v in tab.items()],
              ["시총 출처", "행수", "비중"], ["l", "r", "r"], title="시가총액 출처 감사")
    n_ap = int(base["mktcap_is_approx"].sum())
    if n_ap:
        LOG.warn(f"시총 {n_ap:,}행({100*n_ap/n:.1f}%)이 근사치입니다(현재 상장주식수 × 과거 종가). "
                 f"근사분도 §5 하한 판정과 시총하위1000 순위에 그대로 씁니다 — 근사라고 "
                 f"통과시키면 소형주가 무조건 들어오고, 근사라고 전부 빼면 실측 소스가 "
                 f"전멸한 실행에서 유니버스가 통째로 비기 때문입니다. 두 선택 모두 하한을 "
                 f"둔 목적에 반합니다. 대신 이 비중을 표와 OPEN_QUESTIONS 에 남깁니다.")
        open_question(
            "MCAP_APPROX", "시가총액 근사 사용",
            f"실측 시총 소스(pykrx / KRX MDC 벌크)를 확보하지 못해 {n_ap:,}행"
            f"({100*n_ap/n:.1f}%)을 '현재 상장주식수 × 과거 종가'로 근사했습니다. "
            f"액면분할·유상증자·자사주소각을 반영하지 못하므로 절대수준이 왜곡될 수 있고, "
            f"상장폐지 종목은 현재 상장목록에 없어 근사조차 불가합니다.",
            "근사값도 §5 하한 판정에 사용합니다. 대안 두 가지가 모두 더 나쁩니다: "
            "근사분을 무조건 통과시키면 하한을 둔 의미가 사라지고(소형주 전량 유입, 성과 "
            "과대), 근사분을 전부 제외하면 실측 소스가 전멸한 실행에서 유니버스가 0이 되어 "
            "검정 자체가 불가능해집니다. 근사 오차는 대칭 잡음이므로 하한을 '적용하는' 쪽이 "
            "체계적 편의가 가장 작습니다.",
            "절대수준 오차만큼 경계 근처 종목의 편입·제외가 뒤바뀔 수 있습니다. "
            "실측 시총 소스(pykrx 또는 KRX 벌크)가 살아나면 자동 해소됩니다.")
    LOG.ok(f"시가총액 {base['month'].nunique()}개월 × {base['code'].nunique():,}종목 = {len(base):,}행"
           + ("" if wrote else " (신규 저장 없음)"))
    return base


def fetch_fundamental_monthly(months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 PBR/BPS/PER/EPS/배당수익률 스냅샷 → BM = 1/PBR. 1개월 = 1호출.

    §6.3 직교화의 BM 은 이 경로가 1순위다. DART 재무제표를 사별로 긁는 것보다
    두 자릿수 배 싸고, 시장가 기준이라 정의도 더 정확하다(장부가/시가).
    """
    cached = cache_recall("krx_fundamental_monthly", scope="shared")
    have = _have_months(cached)
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"펀더멘털 월말 스냅샷: 캐시 충족 "
               f"({len(cached) if cached is not None else 0:,}행, 신규 호출 0건)")
        return _finalize_fund(cached, wrote=False)

    use_pykrx = pykrx_stock is not None
    use_bulk = krx_bulk_available()
    if not (use_pykrx or use_bulk):
        LOG.warn("PBR 실측 소스가 모두 불가 — §6.3 직교화의 BM 항은 DART 자본총계 폴백으로 "
                 "보강하며, 그래도 남는 결측은 회귀에서 제외 처리됩니다(0으로 채우지 않습니다).")
        return _finalize_fund(cached, wrote=False)

    LOG.info(f"펀더멘털(PBR/BPS) 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails = [], 0
    for m in tqdm(todo, desc="펀더멘털 스냅샷", disable=not VERBOSE, mininterval=TQDM_MININTERVAL):
        g = None
        if use_pykrx:
            d = _krx_snapshot("get_market_fundamental_by_ticker", m.strftime("%Y%m%d"))
            if d is not None:
                t = d.reset_index()
                col = {str(c).upper(): c for c in t.columns}
                code_c = next((c for c in t.columns if str(c) in ("티커", "종목코드", "index")), None)
                if code_c is not None:
                    def _num(key, _t=t, _c=col):
                        c = _c.get(key)
                        return (pd.to_numeric(_t[c], errors="coerce") if c is not None
                                else pd.Series(np.nan, index=_t.index))
                    g = pd.DataFrame({"code": t[code_c].map(to_code6), "month": m,
                                      "bps": _num("BPS"), "per": _num("PER"), "pbr": _num("PBR"),
                                      "eps": _num("EPS"), "div_yield": _num("DIV"),
                                      "src": "pykrx"}).dropna(subset=["code"])
        if (g is None or not len(g)) and use_bulk:
            d = krx_all_perpbr(m)
            if d is not None and len(d):
                g = pd.DataFrame({"code": d["code"], "month": m, "bps": d.get("bps"),
                                  "per": d.get("per"), "pbr": d.get("pbr"), "eps": d.get("eps"),
                                  "div_yield": d.get("div_yield"), "src": "krx_bulk"})
        if g is None or not len(g):
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 펀더멘털 수집 중단.")
                break
            continue
        fails = 0
        rows.append(g)

    frames = ([cached.reindex(columns=FUND_COLS)] if cached is not None and len(cached) else []) \
        + [f for f in rows if len(f)]
    if not frames:
        return _finalize_fund(cached, wrote=False)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if rows:
        note_new_data("krx_fundamental_monthly", sum(len(f) for f in rows), "shared",
                      "price", "krx")
        persist("krx_fundamental_monthly", out, scope="shared", domain="price",
                source="pykrx/krx_bulk monthly fundamental snapshot")
    return _finalize_fund(out, wrote=True)


def _finalize_fund(out: Optional[pd.DataFrame], wrote: bool) -> pd.DataFrame:
    if out is None or not len(out):
        return pd.DataFrame(columns=FUND_COLS)
    out = out.copy()
    # BM = 장부가/시가 = 1/PBR. PBR<=0 (자본잠식)은 BM 정의가 무너지므로 결측.
    # ★ df.get("pbr") 은 컬럼이 없으면 None 을 돌려주고 pd.to_numeric(None) 은 터진다.
    #   구버전 스키마 캐시를 물려받는 경로가 실재하므로 반드시 명시 폴백을 둔다.
    pbr = (pd.to_numeric(out["pbr"], errors="coerce") if "pbr" in out.columns
           else pd.Series(np.nan, index=out.index))
    out["bm"] = np.where(pbr > 0, 1.0 / pbr.replace(0, np.nan), np.nan)
    ok = int(out["bm"].notna().sum())
    LOG.ok(f"펀더멘털 스냅샷 {len(out):,}행 · BM 산출 가능 {ok:,}행 "
           f"({100*ok/max(len(out),1):.1f}%)" + ("" if wrote else " (신규 저장 없음)"))
    return out


def fetch_nonequity_tickers(months: pd.DatetimeIndex) -> pd.DataFrame:
    """ETF/ETN/ELW 티커 목록 스냅샷 (§5 제외). 반기 1회면 충분하므로 호출을 더 줄인다.

    pykrx 가 없으면 종목명 패턴(classify_security)이 같은 일을 한다 — 정확도는 조금 낮지만
    '제외 대상을 못 걸러 유니버스가 오염되는' 사고는 나지 않는다.
    """
    cached = cache_recall("krx_nonequity_tickers", scope="shared")
    grid = sorted({as_ts(m) for m in months if m.month in (6, 12)}) or list(months[:1])
    have = _have_months(cached, "snap")
    todo = [m for m in grid if m.strftime("%Y-%m") not in have]
    if not todo or pykrx_stock is None:
        if cached is not None and len(cached):
            return cached
        if pykrx_stock is None:
            LOG.info("pykrx 없음 — ETF/ETN/ELW 목록은 종목명 패턴으로 판정합니다 "
                     "(build_exclusion_flags 의 이름 규칙).")
        return pd.DataFrame(columns=["snap", "code", "kind"])
    rows = []
    for m in todo:
        day = m.strftime("%Y%m%d")
        for kind, fname in (("ETF", "get_etf_ticker_list"), ("ETN", "get_etn_ticker_list"),
                            ("ELW", "get_elw_ticker_list")):
            fn = getattr(pykrx_stock, fname, None)
            if fn is None:
                continue
            lst = KRXG.call(fn, day)
            for c in (lst or []):
                cc = to_code6(c)
                if cc:
                    rows.append({"snap": m, "code": cc, "kind": kind})
    if not rows:
        return cached if cached is not None else pd.DataFrame(columns=["snap", "code", "kind"])
    out = pd.DataFrame(rows)
    if cached is not None and len(cached):
        out = pd.concat([out, cached], ignore_index=True)
    out["snap"] = as_ts_series(out["snap"])
    out = out.drop_duplicates(subset=["snap", "code"], keep="last").reset_index(drop=True)
    note_new_data("krx_nonequity_tickers", len(rows), "shared", "universe", "pykrx")
    persist("krx_nonequity_tickers", out, scope="shared", domain="universe",
            source="pykrx etf/etn/elw ticker list")
    LOG.ok(f"비주식 종목(ETF/ETN/ELW) {out['code'].nunique():,}개 식별")
    return out


def build_exclusion_flags(sec: pd.DataFrame, nonequity: pd.DataFrame) -> pd.DataFrame:
    """종목별 제외 플래그 (§5). 시점 불변 성질(우선주/스팩/ETF)만 여기서 판정한다.

    관리종목·거래정지는 시점 가변이라 공개 PIT 소스가 없다 → OPEN_QUESTIONS 에 기록하고
    '제외하지 않는' 보수적 선택을 한다(제외하면 성과가 좋아지는 방향이므로, 남기는 쪽이 보수적).
    """
    s = sec.copy()
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"])
    nm = s["name"].astype(str).fillna("") if "name" in s.columns else pd.Series("", index=s.index)
    mkt = s["market"].astype(str) if "market" in s.columns else pd.Series("", index=s.index)
    ne = set(nonequity["code"].astype(str)) if nonequity is not None and len(nonequity) else set()
    kind = [classify_security(c, n, m) for c, n, m in zip(s["code"], nm, mkt)]
    s["kind"] = kind
    s["is_pref"] = s["kind"].eq("preferred")
    s["is_spac"] = s["kind"].eq("spac")
    s["is_reit"] = s["kind"].eq("reit")
    s["is_etp"] = s["code"].isin(ne) | s["kind"].isin(("etp", "elw"))
    s["is_konex"] = mkt.str.upper().str.contains("KONEX", na=False)
    s["excluded"] = s[["is_pref", "is_spac", "is_reit", "is_etp", "is_konex"]].any(axis=1)
    out = s[["code", "name", "market", "is_pref", "is_spac", "is_reit", "is_etp",
             "is_konex", "excluded"]].reset_index(drop=True)
    LOG.table([[k, f"{int(out[k].sum()):,}"] for k in
               ("is_pref", "is_spac", "is_reit", "is_etp", "is_konex", "excluded")],
              ["제외 사유", "종목수"], ["l", "r"], title="유니버스 제외 플래그 (§5)")
    LOG.info("관리종목·투자주의환기·거래정지는 시점가변 PIT 공개소스가 없어 제외하지 않습니다. "
             "제외하면 성과가 개선되는 방향이므로 '남기는 쪽'이 보수적입니다 "
             "(OPEN_QUESTIONS.md 에 기록됨).")
    persist(f"exclusion_flags_{STRATEGY_ID}", out, scope="private", domain="universe",
            source="§5 exclusion rules")
    return out


def build_sector_map(sec: pd.DataFrame) -> pd.DataFrame:
    """code → sector. §6.3 SectorRet 과 H2 교차업종 검정의 기준.

    한계: 업종은 현재시점 분류다(PIT 아님). 변경 빈도가 낮아 영향이 제한적이지만
    완전한 PIT 은 아니며, 이 사실을 산출물에 명시한다.
    """
    s = sec[["code", "industry"]].copy() if "industry" in sec.columns else \
        sec[["code"]].assign(industry="")
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"])
    ind = s["industry"].astype(str).replace({"": "미분류", "nan": "미분류", "None": "미분류"})
    ind = ind.fillna("미분류")
    # 세부 업종명이 너무 잘게 쪼개지면 SectorRet 이 자기 자신이 되어버린다.
    # 앞 두 어절로 묶어 셀 크기를 확보한다(최소 표본 확보가 회귀 안정성보다 앞선다).
    s["sector"] = ind.str.replace(r"\s+", " ", regex=True).str.split(" ").str[:2].str.join(" ")
    s.loc[s["sector"].str.len() < 2, "sector"] = "미분류"
    n = s["sector"].nunique()
    small = s.groupby("sector")["code"].size()
    rare = set(small[small < 5].index)
    if rare:
        s.loc[s["sector"].isin(rare), "sector"] = "기타"
    if s["sector"].nunique() < 2:
        LOG.error("업종 분류가 단일 클래스로 붕괴했습니다 (sec['industry'] 가 비었을 가능성). "
                  "H2 교차업종 검정은 '판정불가'로 처리되며, 이를 통과로 오인하면 안 됩니다.")
    LOG.info(f"업종 매핑: {n}개 원분류 → {s['sector'].nunique()}개 사용 분류 "
             f"(5종목 미만 {len(rare)}개는 '기타'로 병합). ※현재시점 분류 — 완전 PIT 아님")
    out = s[["code", "sector"]].drop_duplicates("code").reset_index(drop=True)
    persist(f"sector_map_{STRATEGY_ID}", out, scope="private", domain="universe",
            source="industry → sector")
    return out


def fetch_retail_share(codes: Sequence[str], start: str, end: str,
                       max_codes: int = 0) -> pd.DataFrame:
    """종목별 개인 거래대금 비중 (H3 조건부 예측의 보조 축).

    ★ 기본 비활성이다. 종목당 1호출 × 2,600종목 = KRX 버킷 2 QPS 에서 22분이고,
      H3 는 소형주·저커버리지 축만으로도 판정 가능하다. 있으면 해석표가 풍부해질 뿐이다.
      켜려면 COLLECT_RETAIL_SHARE = True.
    """
    cols = ["code", "month", "retail_share"]
    cached = cache_recall("krx_retail_share_monthly", scope="shared")
    have = set(cached["code"].astype(str)) if cached is not None and len(cached) else set()
    if not COLLECT_RETAIL_SHARE:
        if cached is not None and len(cached):
            LOG.info(f"개인 거래비중 — 캐시 {len(cached):,}행만 사용(신규 수집 off).")
            return cached
        LOG.info("개인 거래비중 수집 비활성(COLLECT_RETAIL_SHARE=False) — "
                 "H3 는 소형주·저커버리지 축으로 판정합니다.")
        return pd.DataFrame(columns=cols)
    cap = int(max_codes or RETAIL_SHARE_MAX_CODES)
    todo = [c for c in dict.fromkeys(codes) if c and c not in have][:cap]
    if not todo or pykrx_stock is None:
        if cached is None or not len(cached):
            LOG.warn("개인 거래비중 데이터 없음 — H3 는 소형주·저커버리지 축으로만 판정합니다.")
            return pd.DataFrame(columns=cols)
        return cached

    LOG.info(f"개인 거래비중 신규 {len(todo):,}종목 (종목당 1호출로 전 구간)")
    s_str, e_str = as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d")
    state = {"fail": 0, "stop": False}

    def _one(code: str):
        if state["stop"]:
            return None
        fn = getattr(pykrx_stock, "get_market_trading_value_by_date", None)
        if fn is None:
            return None
        d = KRXG.call(fn, s_str, e_str, code, detail=True)
        if d is None or not hasattr(d, "empty") or d.empty:
            state["fail"] += 1
            if state["fail"] >= CIRCUIT_BREAKER_FAILS:
                state["stop"] = True
            return None
        state["fail"] = 0
        t = d.reset_index()
        dc = t.columns[0]
        ind_c = [c for c in t.columns if "개인" in str(c)]
        tot_c = [c for c in t.columns if "전체" in str(c) or "합계" in str(c)]
        if not ind_c:
            return None
        g = pd.DataFrame({"date": as_ts_series(t[dc]),
                          "ind": pd.to_numeric(t[ind_c[0]], errors="coerce").abs()})
        if tot_c:
            g["tot"] = pd.to_numeric(t[tot_c[0]], errors="coerce").abs()
        else:
            num = t.select_dtypes("number").abs().sum(axis=1)
            g["tot"] = pd.to_numeric(num, errors="coerce")
        g = g.dropna(subset=["date"])
        g["month"] = g["date"] + pd.offsets.MonthEnd(0)
        a = g.groupby("month", as_index=False)[["ind", "tot"]].sum()
        a["retail_share"] = safe_div(a["ind"], a["tot"])
        a["code"] = code
        return a[cols]

    got = pmap_io(_one, todo, workers=_resolve_workers("krx"), desc="개인 거래비중")
    frames = [d for d in got if d is not None and len(d)]
    n_new = sum(len(f) for f in frames)
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=cols))
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if n_new:
        note_new_data("krx_retail_share_monthly", n_new, "shared", "flow", "pykrx")
        persist("krx_retail_share_monthly", out, scope="shared", domain="flow",
                source="pykrx get_market_trading_value_by_date(detail=True)")
    LOG.ok(f"개인 거래비중 {out['code'].nunique():,}종목 × {out['month'].nunique()}개월 = {len(out):,}행")
    return out


def attach_bm_fallback(fund: pd.DataFrame, mcap: pd.DataFrame,
                       sec: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX PBR 이 비어 있는 (code, month) 만 DART 자본총계로 보강한다.

    보강 대상 수와 DART 잔여 호출량을 표로 보여준 뒤 실행한다.
    ★ 격자는 base(PBR 표)가 아니라 시총 패널이다 — PBR 수집이 통째로 실패한 경우에도
      BM 을 복구할 수 있어야 하고, base 기준이면 그 순간 폴백이 꺼져 버린다.
    """
    base = fund.copy() if fund is not None and len(fund) else pd.DataFrame(columns=FUND_COLS)
    if not len(base):
        base = pd.DataFrame(columns=FUND_COLS)
    # ★ 보강이 필요한 격자는 base 가 아니라 '시총 패널'이다.
    #   base 를 기준으로 삼으면, PBR 수집이 통째로 실패해 base 가 0행일 때
    #   miss = 0 이 되어 "결측 없음"으로 판정하고 DART 를 부르지도 않는다.
    #   BM 이 가장 필요한 순간에 폴백이 정확히 꺼지는 구조였다.
    grid_src = (mcap[["code", "month"]].drop_duplicates()
                if mcap is not None and len(mcap) else
                (base[["code", "month"]].drop_duplicates() if len(base) else
                 pd.DataFrame(columns=["code", "month"])))
    have_bm = 0
    if len(base) and "bm" in base.columns:
        have_bm = int(base["bm"].notna().sum())
    total = max(len(grid_src), 1)
    miss = max(0, len(grid_src) - have_bm)
    LOG.table([["KRX PBR 로 BM 확보", f"{have_bm:,}", f"{100*have_bm/total:.1f}%"],
               ["결측 (DART 보강 대상)", f"{miss:,}", f"{100*miss/total:.1f}%"],
               ["DART 잔여 호출량", f"{DQ.remaining():,}" if DQ else "키 없음", ""]],
              ["BM 출처", "행수", "비중"], ["l", "r", "r"], title="§6.3 BM 확보 현황")
    if not len(base):
        LOG.warn("KRX PBR 스냅샷이 0행입니다 — BM 전량을 DART 자본총계로 시도합니다.")
    if miss == 0 or not len(grid_src) or not DART_API_KEY or DQ is None or DQ.exhausted:
        if miss and not DART_API_KEY:
            LOG.info("DART 키가 없어 BM 결측은 그대로 둡니다. 직교화 회귀는 해당 항을 "
                     "결측 제외로 처리하며, 그 사실이 산출물에 남습니다.")
        return base
    corps = sec["corp_code"].dropna().astype(str).unique().tolist() if "corp_code" in sec.columns else []
    if not corps:
        return base
    years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
    eq = fetch_dart_equity(corps, years)
    if eq is None or not len(eq):
        return base
    c2c = sec.dropna(subset=["corp_code"]).assign(
        corp_code=lambda d: d["corp_code"].astype(str)).set_index("corp_code")["code"].to_dict()
    eq = eq.copy()
    eq["code"] = eq["corp_code"].astype(str).map(c2c)
    eq = eq.dropna(subset=["code", "knowledge_date"])
    if not len(eq):
        return base
    PIT.register("dart_equity", eq, key_cols=["code"])
    grid = grid_src.copy()
    if not len(grid):
        return base
    j = PIT.asof_join(grid.assign(code=grid["code"].astype(str)), "dart_equity",
                      by="code", left_time="month", cols=["equity"])
    mm = mcap[["code", "month", "mktcap"]].copy() if mcap is not None and len(mcap) else None
    if mm is None:
        return base
    mm["code"] = mm["code"].astype(str)
    j["month"] = as_ts_series(j["month"])
    mm["month"] = as_ts_series(mm["month"])
    j = j.merge(mm, on=["code", "month"], how="left")
    j["bm_dart"] = np.where((j.get("equity", pd.Series(np.nan, index=j.index)) > 0) & (j["mktcap"] > 0),
                            safe_div(j.get("equity"), j["mktcap"]), np.nan)
    # base 가 비었거나 격자보다 좁을 수 있으므로 외부조인으로 넓힌다 —
    # 좌측조인이면 DART 가 새로 채울 수 있는 (code, month) 가 통째로 사라진다.
    base = base.merge(j[["code", "month", "bm_dart"]], on=["code", "month"], how="outer")
    for _c in FUND_COLS:
        if _c not in base.columns:
            base[_c] = np.nan
    base["bm"] = pd.to_numeric(base["bm"], errors="coerce").astype("float64")
    fill = base["bm"].isna() & base["bm_dart"].notna()
    base.loc[fill, "bm"] = pd.to_numeric(base.loc[fill, "bm_dart"], errors="coerce").astype("float64")
    LOG.ok(f"DART 자본총계로 BM {int(fill.sum()):,}행 보강 (잔여 결측 {int(base['bm'].isna().sum()):,}행)")
    out = base.drop(columns=["bm_dart"], errors="ignore")
    if int(fill.sum()):
        persist("krx_fundamental_monthly", out.reindex(columns=FUND_COLS), scope="shared",
                domain="price", source="krx + dart equity fallback")
    return out
