# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  데이터 조립 — 캐시에서 꺼내 쓰고, 없는 것만 만든다                                        ║
# ║                                                                                          ║
# ║  순서가 곧 정책이다:  LAKE(캐시) → VAULT(드라이브 테이블) → 네트워크(구멍만)              ║
# ║  COLLECT_POLICY="NEVER" 면 세 번째 단계가 아예 실행되지 않는다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

RUNLOG: Dict[str, Any] = {}


def _net_allowed() -> bool:
    if RUN_MODE == "CACHED" or COLLECT_POLICY == "NEVER":
        return False
    return True


# ── SMOKE 합성데이터 ────────────────────────────────────────────────────────────────────────
def synth_dataset(n_codes: int = 900, years: int = 8) -> Dict[str, pd.DataFrame]:
    """실데이터 없이 Step 0~9 전 계산경로를 증명하기 위한 합성 패널.

    ★ 신호가 '있는' 데이터를 만들지 않는다. F2/F4 이벤트는 수익률과 독립으로 뿌린다.
      스모크에서 팩터가 통과하면 그건 하네스 버그지 알파가 아니다 —
      그래서 스모크의 기대 결과는 '전 팩터 G1~G7 미달' 이다.
    """
    rng = np.random.default_rng(SEED)
    end = pd.Timestamp("2026-07-31")
    dates = pd.bdate_range(end - pd.DateOffset(years=years), end)
    codes = [f"{i:06d}" for i in rng.choice(np.arange(1000, 999999), n_codes, replace=False)]
    codes = [c[:-1] + "0" for c in codes]
    codes = sorted(set(codes))
    n_codes = len(codes)

    drift = rng.normal(0.0002, 0.0004, n_codes)
    vol = rng.uniform(0.018, 0.055, n_codes)
    r = rng.standard_normal((len(dates), n_codes)) * vol + drift
    px = 1000.0 * np.exp(np.cumsum(r, axis=0)) * rng.uniform(0.5, 20, n_codes)
    shares = rng.lognormal(16.5, 1.1, n_codes)
    turn = np.exp(rng.normal(-5.6, 1.0, (len(dates), n_codes)))
    vol_sh = np.maximum(shares * turn, 1.0)

    D = pd.DataFrame({
        "code": np.tile(codes, len(dates)),
        "date": np.repeat(dates.values, n_codes),
        "close": px.ravel(), "open": (px * (1 + rng.normal(0, 0.004, px.shape))).ravel(),
        "high": (px * 1.01).ravel(), "low": (px * 0.99).ravel(),
        "volume": vol_sh.ravel(),
        "amount": (px * vol_sh).ravel(),
        "shares": np.tile(shares, len(dates)),
    })
    D["market_cap"] = D["close"] * D["shares"]

    lst = pd.to_datetime(rng.choice(pd.bdate_range("2005-01-01", "2024-01-01"), n_codes))
    dele = pd.Series(pd.NaT, index=range(n_codes))
    kill = rng.random(n_codes) < 0.11                      # 폐지 이력 ~11%
    dele[kill] = pd.to_datetime(rng.choice(pd.bdate_range(dates[0], dates[-1]), int(kill.sum())))
    names = []
    for i, c in enumerate(codes):
        t = rng.random()
        names.append(f"합성{i:03d}스팩" if t < 0.04 else
                     f"합성{i:03d}리츠" if t < 0.06 else f"합성{i:03d}")
    SEC = pd.DataFrame({"code": codes, "name": names,
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes, p=[0.25, 0.75]),
                        "listing_date": lst, "delisting_date": dele.values,
                        "corp_code": [f"{i:08d}" for i in range(n_codes)],
                        "industry": rng.choice([f"업종{i}" for i in range(18)], n_codes)})

    yrs = list(range(dates[0].year - 1, dates[-1].year + 1))
    FIN = pd.DataFrame([
        {"code": c, "bsns_year": y,
         "knowledge_date": pd.Timestamp(year=y + 1, month=3, day=25),
         "revenue": float(rng.lognormal(24, 1.3)),
         "equity": float(rng.lognormal(23.5, 1.4)) * (1 if rng.random() > 0.07 else -1),
         "capital": float(rng.lognormal(22.8, 1.0))}
        for c in codes for y in yrs])

    def _ev(rate, cols):
        k = max(1, int(n_codes * len(dates) / 250 * rate))
        idx = rng.integers(0, n_codes, k)
        dt = pd.to_datetime(rng.choice(dates, k))
        d = pd.DataFrame({"code": [codes[i] for i in idx], "rcept_dt": dt})
        for cname, fn in cols.items():
            d[cname] = fn(k, rng)
        return d

    CAP = _ev(0.09, {"event": lambda k, g: g.choice(["E1_CB", "E1_BW", "E2_3RD", "E3_OWNER"], k),
                     "is_private": lambda k, g: g.random(k) < 0.75,
                     "refix": lambda k, g: g.random(k) < 0.6,
                     "conv_price": lambda k, g: g.uniform(500, 20000, k)})
    INS = _ev(0.05, {"reason": lambda k, g: g.choice(["장내매수", "장내매도", "스톡옵션", "상속"], k,
                                                     p=[0.42, 0.33, 0.15, 0.10]),
                     "net_amount": lambda k, g: g.lognormal(18, 1.5, k),
                     "role": lambda k, g: g.choice(["대표이사", "등기임원", "최대주주", "특수관계인"], k)})
    INS["net_amount"] *= np.where(INS["reason"] == "장내매수", 1, -1)
    CON = _ev(0.04, {"contract_amt": lambda k, g: g.lognormal(23, 1.6, k),
                     "counterparty": lambda k, g: g.choice(["공공기관", "대기업집단", "일반"], k),
                     "is_cancel": lambda k, g: g.random(k) < 0.07})
    return {"price": D, "sec": SEC, "fin": FIN, "cap_events": CAP,
            "insider": INS, "contracts": CON}


# ── 로더 ────────────────────────────────────────────────────────────────────────────────────
def load_sec_master() -> pd.DataFrame:
    d = LAKE.load("sec_master")
    if d is None:
        d = VAULT.get_table("sec_master", scope="shared")
    if d is None and _net_allowed():
        d = fetch_sec_master_github()
    if d is None or not len(d):
        raise StageFailure(
            "종목마스터(상장일·폐지일)를 어디에서도 찾지 못했습니다. 상장일이 없으면 "
            "'상장 ≥ 180일' 게이트를, 폐지일이 없으면 생존자편향 제거를 할 수 없습니다.")
    d = d.copy()
    d["code"] = d["code"].map(to_code6)
    d = d.dropna(subset=["code"])
    for c in ("listing_date", "delisting_date"):
        d[c] = as_ts_series(d[c]) if c in d.columns else pd.NaT
    for c in ("name", "market", "industry", "corp_code"):
        if c not in d.columns:
            d[c] = ""
    #   같은 종목이 여러 캐시에 있으면 정보가 많은 행을 남긴다(폐지일이 있는 쪽 우선).
    d["_rich"] = d[["listing_date", "delisting_date"]].notna().sum(axis=1) + \
                 (d["name"].astype(str).str.len() > 0).astype(int)
    d = d.sort_values("_rich").drop_duplicates("code", keep="last").drop(columns=["_rich"])
    n_del = int(d["delisting_date"].notna().sum())
    LOG.ok(f"종목마스터 {len(d):,}종목 (폐지 이력 {n_del:,}종목 = {100*n_del/max(len(d),1):.1f}%) "
           f"— 폐지 종목이 0이면 생존자편향입니다.")
    if n_del == 0:
        LOG.warn("폐지 종목이 하나도 없습니다 — 생존자편향이 확실합니다. "
                 "폐지 목록을 담은 캐시를 찾거나 FDR delisting 을 수집하세요.")
    return d


def fetch_sec_master_github() -> Optional[pd.DataFrame]:
    """깃허브 FDR 캐시(로그인 불필요)에서 상장/폐지 목록만 받는다. 구멍 메우기 전용."""
    out = []
    today = _dt.date.today()
    for kind, dcol in (("listing/krx", None), ("listing/delisting", "DelistingDate")):
        got = None
        for i in range(20):
            day = today - _dt.timedelta(days=i)
            if day.weekday() >= 5:
                continue
            url = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                   f"refs/heads/master/data/{kind}/{day.isoformat()}.csv")
            raw = http_get(url, source="github", as_bytes=True, tries=1, timeout=25)
            if raw and len(raw) > 200 and not raw[:15].lstrip().startswith(b"404"):
                try:
                    got = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", dtype=str)
                    break
                except Exception:
                    continue
        if got is None:
            LOG.warn(f"깃허브 FDR 캐시 {kind} 를 받지 못했습니다.")
            continue
        ren = {c: canon_col(c) for c in got.columns if canon_col(c)}
        got = got.rename(columns=ren)
        if dcol and "delisting_date" not in got.columns:
            for c in got.columns:
                if "delist" in str(c).lower():
                    got = got.rename(columns={c: "delisting_date"})
                    break
        out.append(got)
    if not out:
        return None
    d = pd.concat(out, ignore_index=True)
    VAULT.put_table("sec_master", d, scope="shared", domain="universe", source="fdr_github_cache")
    return d


def load_price() -> pd.DataFrame:
    d = LAKE.load("price_daily", required=["code", "date", "close"])
    mc = LAKE.load("mktcap_daily")
    if d is None:
        d = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if d is None:
        raise StageFailure(
            "일별 가격 캐시를 찾지 못했습니다. CACHE_SEARCH_DIRS 에 이전 프로젝트의 "
            "가격 parquet/csv 가 있는 폴더를 추가하세요. (신규 수집은 수 시간 걸립니다)")
    if mc is not None and ("market_cap" not in d.columns or d["market_cap"].isna().all()):
        keep = [c for c in ("code", "date", "market_cap", "shares") if c in mc.columns]
        mc = mc[keep].copy()
        mc["code"] = mc["code"].map(to_code6)
        mc["date"] = as_ts_series(mc["date"])
        d = d.merge(mc.drop_duplicates(["code", "date"]), on=["code", "date"], how="left")
        LOG.ok(f"별도 시총 캐시 {len(mc):,}행을 가격 패널에 결합했습니다.")
    return d


def load_financials() -> pd.DataFrame:
    """(code, knowledge_date, revenue, equity, capital) 롱패널. knowledge_date = 접수일자."""
    d = LAKE.load("financials")
    if d is not None and {"revenue"} <= set(d.columns):
        f = d.copy()
    else:
        raw = LAKE.load("dart_fin")
        if raw is None:
            raw = VAULT.get_table("dart_fnltt_raw", scope="shared")
        if raw is None:
            LOG.warn("재무 캐시를 찾지 못했습니다 — 자본잠식·재무결측 게이트가 무력화됩니다.")
            return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
        f = tidy_dart_accounts(raw)
    for c in ("revenue", "equity", "capital"):
        if c not in f.columns:
            f[c] = np.nan
        f[c] = pd.to_numeric(f[c], errors="coerce")
    if "knowledge_date" not in f.columns:
        if "rcept_no" in f.columns:
            f["knowledge_date"] = pd.to_datetime(
                f["rcept_no"].astype(str).str.replace(r"\D", "", regex=True).str[:8],
                format="%Y%m%d", errors="coerce")
        elif "bsns_year" in f.columns:
            #   접수일자를 모르면 법정 제출기한(사업보고서 90일)으로 보수 추정한다.
            f["knowledge_date"] = pd.to_datetime(
                pd.to_numeric(f["bsns_year"], errors="coerce").astype("Int64").astype(str) + "-12-31",
                errors="coerce") + pd.Timedelta(days=90)
            LOG.warn("재무 캐시에 접수일자가 없어 결산일+90일로 보수 추정했습니다 — "
                     "PIT 가 그만큼 느슨해집니다(미래참조 방향이 아니라 지연 방향).")
    if "code" not in f.columns:
        f = map_corp_to_code(f)
    f = f.dropna(subset=["code", "knowledge_date"])
    f = (f.sort_values(["code", "knowledge_date"])
           .drop_duplicates(["code", "knowledge_date"], keep="last"))
    LOG.ok(f"재무 패널 {len(f):,}행 · {f['code'].nunique():,}종목 "
           f"(자본총계 유효 {int(f['equity'].notna().sum()):,}행)")
    return f[["code", "knowledge_date", "revenue", "equity", "capital"]]


_ACCT_PAT = {
    "revenue": re.compile(r"^(매출액|수익\(매출액\)|영업수익|매출)$"),
    "equity":  re.compile(r"^(자본총계|자본\s*총계)$"),
    "capital": re.compile(r"^(자본금)$"),
}


def tidy_dart_accounts(raw: pd.DataFrame) -> pd.DataFrame:
    """DART 원시 계정 롱테이블 → 종목×기간 와이드. 접수일자를 여기서 확정한다."""
    d = raw.copy()
    if "account_nm" not in d.columns or "amount_fs" not in d.columns:
        return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    d["amount_fs"] = pd.to_numeric(
        d["amount_fs"].astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce")
    frames = []
    for item, pat in _ACCT_PAT.items():
        h = d[d["account_nm"].str.match(pat)]
        if not len(h):
            continue
        keys = [c for c in ("corp_code", "code", "bsns_year", "rcept_no") if c in h.columns]
        frames.append(h.groupby(keys, observed=True)["amount_fs"].max().rename(item).reset_index())
    if not frames:
        return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=[c for c in out.columns if c in f.columns and c in
                               ("corp_code", "code", "bsns_year", "rcept_no")], how="outer")
    return out


def map_corp_to_code(d: pd.DataFrame) -> pd.DataFrame:
    """corp_code → 종목코드. 매핑표가 없으면 그 사실을 남기고 빈 결과를 돌려준다."""
    if "corp_code" not in d.columns:
        d["code"] = np.nan
        return d
    m = LAKE.load("corp_map")
    if m is None:
        m = VAULT.get_table("dart_corp_map", scope="shared")
    if m is None or "code" not in getattr(m, "columns", []):
        LOG.warn("corp_code ↔ 종목코드 매핑표가 없어 DART 데이터를 종목에 붙이지 못했습니다.")
        d["code"] = np.nan
        return d
    m = m[["corp_code", "code"]].dropna().drop_duplicates("corp_code")
    m["code"] = m["code"].map(to_code6)
    d = d.copy()
    d["corp_code"] = d["corp_code"].astype(str).str.zfill(8)
    m["corp_code"] = m["corp_code"].astype(str).str.zfill(8)
    out = d.merge(m, on="corp_code", how="left")
    hit = 100 * out["code"].notna().mean()
    LOG.info(f"corp_code → 종목코드 매핑률 {hit:.1f}% ({int(out['code'].notna().sum()):,}행)")
    return out


def attach_pit_financials(snap: pd.DataFrame, fin: pd.DataFrame) -> pd.DataFrame:
    """PIT 결합 — 리밸 시점에 '이미 공시된' 최신 재무만 붙인다(merge_asof backward)."""
    if fin is None or not len(fin):
        return snap
    f = fin.copy()
    #   공시 접수일 + 1영업일부터 사용 가능 (§4 공통규약 PIT)
    f["usable_from"] = f["knowledge_date"] + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS)
    f = f.dropna(subset=["usable_from"]).sort_values("usable_from")
    s = snap.sort_values("rebal")
    out = pd.merge_asof(s, f[["code", "usable_from", "revenue", "equity", "capital"]],
                        left_on="rebal", right_on="usable_from", by="code", direction="backward")
    n = int(out["equity"].notna().sum())
    LOG.info(f"PIT 재무 결합 — {n:,}/{len(out):,} 셀에 접수일 기준 최신 재무가 붙었습니다 "
             f"({100*n/max(len(out),1):.1f}%).")
    return out
