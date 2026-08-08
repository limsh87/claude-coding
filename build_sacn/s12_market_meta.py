

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-M  시장 메타 — 시가총액 / BM / 제외플래그 / 업종 / 개인비중                            ║
# ║                                                                                          ║
# ║  재사용 코어(가격 조각)에는 이것들이 통째로 없다. 확인된 공백을 여기서 메운다:               ║
# ║    · 시가총액·상장주식수      → §5 유니버스 하한, §6.3 log(MktCap), 소형주 비교아암          ║
# ║    · BM(장부/시가)            → §6.3 직교화 4번째 항                                       ║
# ║    · 관리종목/스팩/우선주/ETF → §5 제외 규칙 (코어에 필터가 하나도 없었다)                   ║
# ║    · 업종                     → §6.3 SectorRet, H2 교차업종 전용 검정                       ║
# ║    · 개인 거래비중            → H3 조건부 예측                                              ║
# ║                                                                                          ║
# ║  ★ 호출량 설계: 전부 '날짜 1개 = 전종목 1호출' 스냅샷 API 다.                               ║
# ║    시총 120호출 + 펀더멘털 120호출 + ETF/ETN 목록 120호출 ≈ 360호출로 10년치가 끝난다.      ║
# ║    종목별 루프(2,500회)로 짜면 같은 데이터에 20배를 쓴다 — 그렇게 하지 않는다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ★ 리허설(가짜 네트워크) 중에는 캐시에 절대 쓰지 않는다.
#   이 플래그가 없으면 리허설이 만들어낸 합성 시총/PBR 이 공용 인덱스에 저장되고,
#   이후 실수집이 "그 달은 이미 있다"며 영원히 건너뛴다. 사용자의 기존 캐시를 훼손하는
#   경로이므로(절대 1원칙 위반) 구조로 막는다.
_REHEARSAL = False


def _cache_writable() -> bool:
    return not _REHEARSAL


MKTCAP_COLS = ["code", "month", "mktcap", "shares", "close_m", "amount_m"]
FUND_COLS = ["code", "month", "bps", "per", "pbr", "eps", "div_yield", "bm"]

_PREF_TAIL = set("5679KLMNkl")          # 우선주 관용 말자리 (구형 5/7/9, 신형 K/L/M)
_SPAC_PAT = re.compile(r"스팩|기업인수목적")
_REIT_PAT = re.compile(r"리츠|위탁관리부동산|기업구조조정부동산")
_ETF_PAT = re.compile(r"KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE |PLUS |RISE |KOSEF|"
                      r"TIMEFOLIO|파워|마이티|네비게이터|ETN|레버리지|인버스", re.I)


def is_preferred(code: str, name: str = "") -> bool:
    """우선주 판정. 코드 말자리(구형 5/7/9, 신형 K/L/M)와 종목명 '우/우B/2우B' 를 함께 본다."""
    c = str(code or "")
    if len(c) == 6 and c[-1] in _PREF_TAIL and c[-1] != "0":
        return True
    n = str(name or "").strip()
    return bool(re.search(r"(\d?우[BC]?)$|우선주$", n))


def _month_snap_dates(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    """각 월의 스냅샷 기준일(월말). pykrx 는 휴장일이면 직전 영업일로 알아서 당겨준다."""
    return [as_ts(m) for m in months]


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


def fetch_mktcap_monthly(months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 시가총액·상장주식수 스냅샷. 1개월 = 1호출."""
    cached = VAULT.get_table("krx_mktcap_monthly", scope="shared")
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["month"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"시가총액 월말 스냅샷: 캐시 충족 "
               f"({len(cached) if cached is not None else 0:,}행, 신규 호출 0건)")
        return cached if cached is not None else pd.DataFrame(columns=MKTCAP_COLS)
    if pykrx_stock is None:
        LOG.warn("pykrx 없음 — 시가총액 스냅샷을 건너뜁니다. "
                 "유니버스 시총 하한과 §6.3 log(MktCap) 항이 비활성화됩니다.")
        return cached if cached is not None else pd.DataFrame(columns=MKTCAP_COLS)

    LOG.info(f"시가총액 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails = [], 0
    for m in tqdm(todo, desc="시총 스냅샷", disable=not VERBOSE):
        d = _krx_snapshot("get_market_cap_by_ticker", m.strftime("%Y%m%d"))
        if d is None:
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 시총 수집을 중단하고 "
                         f"여기까지 받은 분량을 저장합니다.")
                break
            continue
        fails = 0
        t = d.reset_index()
        cmap = {c: str(c) for c in t.columns}
        t = t.rename(columns=cmap)
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
            continue
        g = pd.DataFrame({
            "code": t[pick["code"]].map(to_code6),
            "month": m,
            "mktcap": pd.to_numeric(t[pick["mktcap"]], errors="coerce"),
            "shares": pd.to_numeric(t[pick["shares"]], errors="coerce") if "shares" in pick else np.nan,
            "close_m": pd.to_numeric(t[pick["close_m"]], errors="coerce") if "close_m" in pick else np.nan,
            "amount_m": pd.to_numeric(t[pick["amount_m"]], errors="coerce") if "amount_m" in pick else np.nan,
        })
        rows.append(g.dropna(subset=["code"]))
    frames = [f for f in rows if len(f)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=MKTCAP_COLS))
    if not frames:
        return pd.DataFrame(columns=MKTCAP_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if _cache_writable():
        VAULT.put_table("krx_mktcap_monthly", out, scope="shared", domain="price",
                        source="pykrx get_market_cap_by_ticker")
    PIPE.io("OUT", "DRIVE", "krx_mktcap_monthly", out)
    LOG.ok(f"시가총액 스냅샷 {out['month'].nunique()}개월 × {out['code'].nunique():,}종목 = {len(out):,}행")
    return out


def fetch_fundamental_monthly(months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 PBR/BPS/PER/EPS/배당수익률 스냅샷 → BM = 1/PBR. 1개월 = 1호출.

    §6.3 직교화의 BM 은 이 경로가 1순위다. DART 재무제표를 사별로 긁는 것보다
    두 자릿수 배 싸고, 시장가 기준이라 정의도 더 정확하다(장부가/시가).
    """
    cached = VAULT.get_table("krx_fundamental_monthly", scope="shared")
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["month"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"펀더멘털 월말 스냅샷: 캐시 충족 "
               f"({len(cached) if cached is not None else 0:,}행, 신규 호출 0건)")
        return cached if cached is not None else pd.DataFrame(columns=FUND_COLS)
    if pykrx_stock is None:
        LOG.warn("pykrx 없음 — PBR 스냅샷 불가. §6.3 직교화의 BM 항은 DART 폴백 또는 결측 처리됩니다.")
        return cached if cached is not None else pd.DataFrame(columns=FUND_COLS)

    LOG.info(f"펀더멘털(PBR/BPS) 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails = [], 0
    for m in tqdm(todo, desc="펀더멘털 스냅샷", disable=not VERBOSE):
        d = _krx_snapshot("get_market_fundamental_by_ticker", m.strftime("%Y%m%d"))
        if d is None:
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 펀더멘털 수집 중단.")
                break
            continue
        fails = 0
        t = d.reset_index()
        col = {str(c).upper(): c for c in t.columns}
        code_c = None
        for c in t.columns:
            if str(c) in ("티커", "종목코드", "index"):
                code_c = c
                break
        if code_c is None:
            continue

        def _num(key):
            c = col.get(key)
            return pd.to_numeric(t[c], errors="coerce") if c is not None else pd.Series(np.nan, index=t.index)

        g = pd.DataFrame({
            "code": t[code_c].map(to_code6), "month": m,
            "bps": _num("BPS"), "per": _num("PER"), "pbr": _num("PBR"),
            "eps": _num("EPS"), "div_yield": _num("DIV"),
        })
        rows.append(g.dropna(subset=["code"]))
    frames = [f for f in rows if len(f)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=FUND_COLS))
    if not frames:
        return pd.DataFrame(columns=FUND_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    # BM = 장부가/시가 = 1/PBR. PBR<=0 (자본잠식)은 BM 정의가 무너지므로 결측.
    pbr = pd.to_numeric(out["pbr"], errors="coerce")
    out["bm"] = np.where(pbr > 0, 1.0 / pbr.replace(0, np.nan), np.nan)
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if _cache_writable():
        VAULT.put_table("krx_fundamental_monthly", out, scope="shared", domain="price",
                        source="pykrx get_market_fundamental_by_ticker")
    PIPE.io("OUT", "DRIVE", "krx_fundamental_monthly", out)
    ok = int(out["bm"].notna().sum())
    LOG.ok(f"펀더멘털 스냅샷 {len(out):,}행 · BM 산출 가능 {ok:,}행 ({100*ok/max(len(out),1):.1f}%)")
    return out


def fetch_nonequity_tickers(months: pd.DatetimeIndex) -> pd.DataFrame:
    """ETF/ETN/ELW 티커 목록 스냅샷 (§5 제외). 반기 1회면 충분하므로 호출을 더 줄인다."""
    cached = VAULT.get_table("krx_nonequity_tickers", scope="shared")
    grid = sorted({as_ts(m) for m in months if m.month in (6, 12)}) or list(months[:1])
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["snap"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in grid if m.strftime("%Y-%m") not in have]
    if not todo or pykrx_stock is None:
        if cached is not None:
            return cached
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
    if _cache_writable():
        VAULT.put_table("krx_nonequity_tickers", out, scope="shared", domain="universe",
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
    nm = s["name"].astype(str).fillna("")
    ne = set(nonequity["code"].astype(str)) if nonequity is not None and len(nonequity) else set()
    s["is_pref"] = [is_preferred(c, n) for c, n in zip(s["code"], nm)]
    s["is_spac"] = nm.str.contains(_SPAC_PAT, na=False)
    s["is_reit"] = nm.str.contains(_REIT_PAT, na=False)
    s["is_etp"] = s["code"].isin(ne) | nm.str.contains(_ETF_PAT, na=False)
    s["is_konex"] = s["market"].astype(str).str.upper().str.contains("KONEX", na=False)
    s["excluded"] = s[["is_pref", "is_spac", "is_reit", "is_etp", "is_konex"]].any(axis=1)
    out = s[["code", "name", "market", "is_pref", "is_spac", "is_reit", "is_etp",
             "is_konex", "excluded"]].reset_index(drop=True)
    LOG.table([[k, f"{int(out[k].sum()):,}"] for k in
               ("is_pref", "is_spac", "is_reit", "is_etp", "is_konex", "excluded")],
              ["제외 사유", "종목수"], ["l", "r"], title="유니버스 제외 플래그 (§5)")
    LOG.info("관리종목·투자주의환기·거래정지는 시점가변 PIT 공개소스가 없어 제외하지 않습니다. "
             "제외하면 성과가 개선되는 방향이므로 '남기는 쪽'이 보수적입니다 "
             "(OPEN_QUESTIONS.md 에 기록됨).")
    return out


def build_sector_map(sec: pd.DataFrame) -> pd.DataFrame:
    """code → sector. §6.3 SectorRet 과 H2 교차업종 검정의 기준.

    한계: 업종은 현재시점 분류다(PIT 아님). 변경 빈도가 낮아 영향이 제한적이지만
    완전한 PIT 은 아니며, 이 사실을 산출물에 명시한다.
    """
    s = sec[["code", "industry"]].copy()
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
    return s[["code", "sector"]].drop_duplicates("code").reset_index(drop=True)


def fetch_retail_share(codes: Sequence[str], start: str, end: str,
                       max_codes: int = 2600) -> pd.DataFrame:
    """종목별 개인 거래대금 비중 (H3 조건부 예측용).

    종목 1개당 1호출로 전 구간을 받는다(2,500호출, 캐시 후 0). 일자별 루프로 짜면
    같은 데이터에 250배를 쓴다. 실패해도 전략을 죽이지 않고 H3 를 축소 보고한다.
    """
    cols = ["code", "month", "retail_share"]
    cached = VAULT.get_table("krx_retail_share_monthly", scope="shared")
    if cached is not None and len(cached):
        have = set(cached["code"].astype(str))
    else:
        have = set()
    todo = [c for c in dict.fromkeys(codes) if c and c not in have][:max_codes]
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

    got = pmap_io(_one, todo, workers=min(4, N_WORKERS_IO), desc="개인 거래비중")
    frames = [d for d in got if d is not None and len(d)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=cols))
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    if _cache_writable():
        VAULT.put_table("krx_retail_share_monthly", out, scope="shared", domain="flow",
                        source="pykrx get_market_trading_value_by_date(detail=True)")
    LOG.ok(f"개인 거래비중 {out['code'].nunique():,}종목 × {out['month'].nunique()}개월 = {len(out):,}행")
    return out


def attach_bm_fallback(fund: pd.DataFrame, mcap: pd.DataFrame,
                       sec: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX PBR 이 비어 있는 (code, month) 만 DART 자본총계로 보강한다.

    보강 대상 수를 먼저 세고, 그게 DART 잔여 호출량 대비 얼마인지 표로 보여준 뒤 실행한다.
    """
    base = fund.copy() if fund is not None and len(fund) else pd.DataFrame(columns=FUND_COLS)
    if not len(base):
        base = pd.DataFrame(columns=FUND_COLS)
    miss = int(base["bm"].isna().sum()) if "bm" in base.columns else 0
    total = max(len(base), 1)
    LOG.table([["KRX PBR 로 BM 확보", f"{total - miss:,}", f"{100*(total-miss)/total:.1f}%"],
               ["결측 (DART 보강 대상)", f"{miss:,}", f"{100*miss/total:.1f}%"]],
              ["BM 출처", "행수", "비중"], ["l", "r", "r"], title="§6.3 BM 확보 현황")
    if miss == 0 or not DART_API_KEY or DQ is None or DQ.exhausted:
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
    grid = base[["code", "month"]].copy() if len(base) else pd.DataFrame(columns=["code", "month"])
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
    base = base.merge(j[["code", "month", "bm_dart"]], on=["code", "month"], how="left")
    base["bm"] = pd.to_numeric(base["bm"], errors="coerce").astype("float64")
    fill = base["bm"].isna() & base["bm_dart"].notna()
    base.loc[fill, "bm"] = pd.to_numeric(base.loc[fill, "bm_dart"], errors="coerce").astype("float64")
    LOG.ok(f"DART 자본총계로 BM {int(fill.sum()):,}행 보강 (잔여 결측 {int(base['bm'].isna().sum()):,}행)")
    return base.drop(columns=["bm_dart"], errors="ignore")
