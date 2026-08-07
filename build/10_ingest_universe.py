

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 유니버스 (C2 생존자편향 제거)                                     ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축:                                                                     ║
# ║    ① pykrx 월말 상장종목 스냅샷 ← ★ 진짜 PIT. "그 날 실제로 상장돼 있던 종목"              ║
# ║    ② FinanceDataReader StockListing('KRX')          — 현재 상장 + 상장일                   ║
# ║    ③ FinanceDataReader StockListing('KRX-DELISTING')— 상장폐지 종목 + 폐지일 ★생존자편향   ║
# ║    ④ KIND 상장법인목록                              — 상장일 보강                          ║
# ║    ⑤ DART corpCode.xml                              — corp_code ↔ 종목코드 연결            ║
# ║                                                                                          ║
# ║  스냅샷은 공용 인덱스에 저장된다 → 다른 전략이 재수집 없이 그대로 쓴다.                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "sector_src", "src"]

# ── 로그인 불필요 경로 ★1순위 ──────────────────────────────────────────────────────────────
#   FinanceDataReader 가 실제로 읽는 GitHub 캐시. KRX 인증 변경의 영향을 받지 않는다.
#   FDR 라이브러리 자체는 최신 영업일을 알아내려고 data.krx.co.kr 을 한 번 찌르는데,
#   그게 로그인 벽에 막히면 CSV 는 멀쩡한데도 ValueError 로 죽는다 → 우리는 CSV 를 직접 읽는다.
FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
             "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 12) -> Optional[pd.DataFrame]:
    """영업일 CSV 만 존재하므로 최근 날짜부터 거꾸로 훑는다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        url = FDR_CACHE.format(kind=kind, date=d.isoformat())
        raw = http_get(url, source="generic", as_bytes=True, tries=1, timeout=20)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), index_col=0, encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str})
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} ({len(df):,}행)")
                return df
        except Exception:
            continue
    return None


def _pykrx_business_day(d: pd.Timestamp) -> str:
    s = d.strftime("%Y%m%d")
    if pykrx_stock is None:
        return s
    try:
        return pykrx_stock.get_nearest_business_day_in_a_week(s, prev=True)
    except Exception:
        try:
            return pykrx_stock.get_nearest_business_day_in_a_week(s)
        except Exception:
            return s


def fetch_pykrx_snapshots(dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """월말별 상장종목 스냅샷. C2의 핵심 — 이게 있으면 생존자편향이 구조적으로 불가능해진다."""
    if pykrx_stock is None:
        LOG.warn("pykrx 미설치 — 월말 상장 스냅샷을 만들 수 없습니다. "
                 "상장일/폐지일 기반 재구성으로 폴백합니다(정확도 소폭 하락).")
        return pd.DataFrame(columns=["snap_date", "code", "market"])

    cached = VAULT.get_table("krx_listing_snapshots", scope="shared")
    have = set()
    if cached is not None and len(cached):
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"공용 캐시에서 상장 스냅샷 {len(have)}개월 재사용")

    todo = [d for d in dates if d.strftime("%Y-%m-%d") not in have]
    new_rows: List[dict] = []
    if todo and RUN_MODE != "CACHED":
        def _one(d: pd.Timestamp):
            bd = _pykrx_business_day(d)
            out = []
            for mkt in ("KOSPI", "KOSDAQ"):
                limiter("krx").wait()
                try:
                    tk = pykrx_stock.get_market_ticker_list(bd, market=mkt)
                except Exception:
                    tk = []
                for t in (tk or []):
                    c = to_code6(t)
                    if c:
                        out.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c, "market": mkt})
            return out

        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="KRX 상장 스냅샷")
        for r in res:
            if r:
                new_rows.extend(r)

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap = snap.dropna(subset=["snap_date", "code"]).drop_duplicates(["snap_date", "code"])
    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                        source="pykrx", extra={"note": "월말 상장종목 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_listing_snapshots", snap, source="pykrx")
    return snap


def fetch_fdr_listing() -> pd.DataFrame:
    # ① 로그인 불필요 GitHub 캐시 직독 (KRX 인증 변경에 영향받지 않음)
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = {str(c).lower(): c for c in d.columns}
        code_c = col.get("code") or col.get("symbol")
        name_c = col.get("name") or col.get("korean name")
        if code_c and name_c:
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str),
                "market": (d[col["market"]].astype(str) if "market" in col
                           else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
                "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
                "industry": (d[col["sector"]].astype(str) if "sector" in col
                             else d[col["industry"]].astype(str) if "industry" in col else ""),
            })
            t["sector_src"], t["src"] = "fdr_cache", "fdr_github_cache"
            r = t.dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"상장목록(로그인 불필요 경로) {len(r):,}건 — KRX 인증 변경의 영향을 받지 않습니다.")
            return r

    # ② 라이브러리 경로 폴백
    if fdr is None:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    out = []
    for key, mk in (("KRX", None), ("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")):
        try:
            limiter("krx").wait()
            d = fdr.StockListing(key)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        d = d.rename(columns={c: str(c) for c in d.columns})
        col = {c.lower(): c for c in d.columns}
        code_c = col.get("code") or col.get("symbol")
        name_c = col.get("name") or col.get("korean name") or col.get("stock name")
        if not code_c or not name_c:
            continue
        t = pd.DataFrame({
            "code": d[code_c].map(to_code6),
            "name": d[name_c].astype(str),
            "market": d[col["market"]].astype(str) if "market" in col else (mk or "KRX"),
            "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
            "industry": d[col["sector"]].astype(str) if "sector" in col else
                        (d[col["industry"]].astype(str) if "industry" in col else ""),
        })
        t["sector_src"] = "fdr"
        t["src"] = f"fdr:{key}"
        out.append(t)
        break                                   # 'KRX' 하나면 충분. 실패했을 때만 시장별로 시도.
    if not out:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    r = pd.concat(out, ignore_index=True).dropna(subset=["code"])
    return r.drop_duplicates("code")


def fetch_fdr_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. 이게 비면 백테스트 결과 전체를 신뢰할 수 없다.
    KRX Open API 에는 상장폐지 엔드포인트가 아예 없다 → GitHub 캐시가 사실상 유일한 공개 경로."""
    d = _fdr_cache_csv("listing/delisting")
    if d is not None and len(d):
        col = {str(c).lower(): c for c in d.columns}
        code_c = col.get("symbol") or col.get("code") or col.get("isu_cd")
        if code_c:
            dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "date", "dedate",
                                          "listingdate") if k in col), None)
            r = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[col.get("name", code_c)].astype(str),
                "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
                "market": d[col["market"]].astype(str) if "market" in col else "KRX",
            }).dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"상장폐지 목록(로그인 불필요 경로) {len(r):,}건 — 생존자편향 제거 입력 확보")
            return r
    if fdr is None:
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    frames = []
    for key in ("KRX-DELISTING", "KRX-DELISTING-KOSPI", "KRX-DELISTING-KOSDAQ"):
        try:
            limiter("krx").wait()
            d = fdr.StockListing(key)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        col = {str(c).lower(): c for c in d.columns}
        code_c = col.get("symbol") or col.get("code")
        if not code_c:
            continue
        dl_c = (col.get("delistingdate") or col.get("delisting_date") or
                col.get("date") or col.get("dedate"))
        frames.append(pd.DataFrame({
            "code": d[code_c].map(to_code6),
            "name": d[col.get("name", code_c)].astype(str),
            "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
            "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        }))
        break
    if not frames:
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    r = pd.concat(frames, ignore_index=True).dropna(subset=["code"])
    return r.drop_duplicates("code")


def fetch_kind_listing() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일 보강. HTML 테이블(엑셀 위장)이라 read_html 로 읽는다."""
    urls = [
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download",
    ]
    for u in urls:
        raw = http_get(u, source="kind", as_bytes=True, tries=2,
                       referer="https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage")
        if not raw:
            continue
        for enc in ("euc-kr", "cp949", "utf-8"):
            try:
                tabs = pd.read_html(io.BytesIO(raw), encoding=enc)
            except Exception:
                continue
            if not tabs:
                continue
            d = max(tabs, key=len)
            col = {str(c).strip(): c for c in d.columns}
            code_c = col.get("종목코드")
            name_c = col.get("회사명")
            if not code_c or not name_c:
                continue
            return pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str),
                "listing_date": as_ts_series(d[col["상장일"]]) if "상장일" in col else pd.NaT,
                "industry": d[col["업종"]].astype(str) if "업종" in col else "",
                "sector_src": "kind", "src": "kind", "market": "",
            }).dropna(subset=["code"]).drop_duplicates("code")
    LOG.warn("KIND 상장법인목록을 받지 못했습니다 — 상장일은 FDR/pykrx 로만 채웁니다.")
    return pd.DataFrame(columns=SEC_MASTER_COLS)


def fetch_dart_corpcode() -> pd.DataFrame:
    """corp_code ↔ 종목코드. DART 의 모든 재무·공시 조회는 corp_code 로만 된다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    # ZIP 엔드포인트는 오류 시에도 zip content-type 을 광고한다 → 매직바이트로 먼저 판별
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        LOG.debug(body)
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                        # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", xml.decode("utf-8", "ignore"), re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code")), "modify_date": g("modify_date")})
    d = pd.DataFrame(rows)
    VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건)")
    return d


def build_security_master(snapshots: pd.DataFrame) -> pd.DataFrame:
    """모든 소스를 합쳐 종목 마스터를 만든다. 충돌은 로그에 남기고 우선순위로 해소."""
    parts = []
    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
        PIPE.io("IN", "HTTP", "fdr:StockListing", lst, source="FinanceDataReader")
    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")

    dead = fetch_fdr_delisting()
    PIPE.io("IN", "HTTP", "fdr:KRX-DELISTING", dead, source="FinanceDataReader",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.copy()
        d2["listing_date"] = pd.NaT
        d2["industry"] = ""
        d2["sector_src"] = "fdr-del"
        d2["src"] = "fdr:delisting"
        parts.append(d2)

    # 스냅샷에만 존재하는 종목(=상장목록에서 이미 사라진 폐지 종목)도 반드시 살린다
    if len(snapshots):
        known = set(pd.concat(parts)["code"]) if parts else set()
        extra = sorted(set(snapshots["code"]) - known)
        if extra:
            parts.append(pd.DataFrame({"code": extra, "name": "", "market": "",
                                       "listing_date": pd.NaT, "industry": "",
                                       "sector_src": "snapshot", "src": "pykrx:snapshot"}))
            LOG.info(f"스냅샷에만 존재하는 종목 {len(extra):,}건 추가 — 상장폐지 명단 누락분입니다. "
                     f"(이걸 빠뜨리면 곧바로 생존자편향)")

    if not parts:
        raise RuntimeError("종목 마스터를 만들 소스가 하나도 없습니다. "
                           "FinanceDataReader/pykrx 설치와 네트워크를 확인하세요.")

    m = pd.concat([p.reindex(columns=SEC_MASTER_COLS + ["delisting_date"]) for p in parts],
                  ignore_index=True)
    m["code"] = m["code"].map(to_code6)
    m = m.dropna(subset=["code"])

    agg = m.groupby("code", as_index=False).agg(
        name=("name", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
        market=("market", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "min"),
        industry=("industry", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
    )

    # 스냅샷으로 상장/폐지일 보정 — 소스 날짜보다 관측이 우선한다
    if len(snapshots):
        g = snapshots.groupby("code")["snap_date"]
        first_seen, last_seen = g.min(), g.max()
        agg = agg.merge(first_seen.rename("snap_first"), left_on="code", right_index=True, how="left")
        agg = agg.merge(last_seen.rename("snap_last"), left_on="code", right_index=True, how="left")
        need = agg["listing_date"].isna() & agg["snap_first"].notna()
        agg.loc[need, "listing_date"] = agg.loc[need, "snap_first"]
        # 마지막 스냅샷 이전에 사라졌으면 폐지로 간주 (폐지 명단에 없어도)
        last_snap = snapshots["snap_date"].max()
        gone = agg["delisting_date"].isna() & agg["snap_last"].notna() & \
            (agg["snap_last"] < last_snap - pd.Timedelta(days=45))
        agg.loc[gone, "delisting_date"] = agg.loc[gone, "snap_last"] + pd.offsets.MonthEnd(1)
        if int(gone.sum()):
            LOG.info(f"스냅샷에서 사라진 {int(gone.sum()):,}종목을 폐지로 추정 처리 "
                     f"(폐지명단 누락 보완 — 생존자편향 2차 방어)")

    cc = fetch_dart_corpcode()
    if len(cc):
        agg = agg.merge(cc[["code", "corp_code", "corp_name"]].dropna(subset=["code"]),
                        on="code", how="left")
        agg["name"] = agg["name"].where(agg["name"].astype(str).str.strip() != "", agg.get("corp_name", ""))
    else:
        agg["corp_code"] = np.nan

    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    agg = agg.drop(columns=[c for c in ("snap_first", "snap_last", "corp_name") if c in agg.columns])
    LOG.ok(f"종목 마스터 {len(agg):,}건 — 상장일 보유 {int(agg['listing_date'].notna().sum()):,} / "
           f"폐지일 보유 {int(agg['delisting_date'].notna().sum()):,}")
    if int(agg["delisting_date"].notna().sum()) < 200:
        LOG.warn("상장폐지 종목이 200건 미만입니다. 10년 구간이라면 통상 1,000건 이상이어야 합니다. "
                 "생존자편향이 남아 있을 수 있으니 결과 해석 시 반드시 감안하세요. (C2 부분 미충족)")
        PIPE.note("WARN: 상장폐지 표본 부족 — C2 생존자편향 완전 제거 미달")
    VAULT.put_table("security_master", agg, scope="shared", domain="universe",
                    source="fdr+kind+pykrx+dart")
    return agg
