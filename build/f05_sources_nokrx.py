# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-0  KRX 비의존 데이터 스파인 (KRX 차단 대응)                                        ║
# ║                                                                                          ║
# ║  전제: data.krx.co.kr / kind.krx.co.kr 접근이 차단될 수 있다(계정·IP 단위).                 ║
# ║  그때도 ① PIT 유니버스 ② 생존자편향 제거 ③ 소유권 이전 관측이 성립해야 한다.                 ║
# ║                                                                                          ║
# ║  ── 대체 경로 사다리 ───────────────────────────────────────────────────────────────────  ║
# ║   유니버스/상장폐지 : FDR GitHub 캐시(비KRX 호스트) → DART corpCode → 네이버 시세목록       ║
# ║                       → ★가격이력 기반 상장/폐지 창 재구성 (거래가 있었다는 사실 자체가     ║
# ║                         상장의 증거다. 어떤 명부에도 의존하지 않는다)                       ║
# ║   상장주식수(시총)  : ★DART 주식총수현황(stockTotqySttus) — 분기별·접수일 기준이라 PIT 완전 ║
# ║                       → 없으면 거래대금 20일합 대리 분모                                    ║
# ║   투자자 수급       : pykrx(가능할 때) → ★네이버 종목별 투자자 매매동향 JSON → 네이버 HTML  ║
# ║   신용융자잔고      : KRX 독점 데이터. 차단 시 수동 CSV → 프록시(Fallback B)로만 가능하며    ║
# ║                       그 사실을 등급으로 못박아 리포트 첫 줄에 인쇄한다(§11-3).             ║
# ║                                                                                          ║
# ║  ★ 차단 상태에서 KRX 를 계속 두드리는 것은 상황을 악화시킨다. 1회 프로브 후 전 경로를        ║
# ║    끄고, 그 사실과 영향을 로그에 남긴다.                                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_KRX_STATE = {"probed": False, "allowed": None, "reason": ""}


def next_bday(s) -> pd.Series:
    """거래일 +1영업일. 공표 지연을 '달력 하루'가 아니라 '영업일 하루'로 계산한다."""
    return as_ts_series(s) + pd.tseries.offsets.BDay(1)


def krx_allowed() -> bool:
    """KRX 계열(data.krx.co.kr / pykrx / KIND) 사용 가능 여부. 프로브는 실행당 1회."""
    if KRX_MODE.upper() == "OFF":
        if not _KRX_STATE["probed"]:
            _KRX_STATE.update(probed=True, allowed=False, reason="KRX_MODE='OFF' (사용자 설정)")
            LOG.warn("KRX 경로가 설정으로 꺼져 있습니다 — 비KRX 스파인으로 전량 진행합니다. "
                     "차단이 풀리면 KRX_MODE='AUTO' 로 되돌리세요.")
        return False
    if KRX_MODE.upper() == "ON":
        return True
    if _KRX_STATE["probed"]:
        return bool(_KRX_STATE["allowed"])
    ok, why = _krx_probe()
    _KRX_STATE.update(probed=True, allowed=ok, reason=why)
    (LOG.ok if ok else LOG.warn)(
        f"KRX 접근 프로브: {'가능' if ok else '차단/불가'} — {why}"
        + ("" if ok else " → 이번 실행은 비KRX 경로만 씁니다(재시도하지 않습니다)."))
    return ok


def _krx_probe() -> Tuple[bool, str]:
    """가벼운 1회 요청으로 차단 여부를 판정한다. 실패해도 재시도하지 않는다."""
    try:
        txt = http_get("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                       source="krx", tries=1, timeout=8)
    except Exception as e:                                            # noqa
        return False, f"요청 예외 {type(e).__name__}"
    if txt is None:
        return False, "응답 없음(차단·타임아웃·DNS 중 하나)"
    t = str(txt)[:400]
    if "Host not in allowlist" in t or "403" in t or "Forbidden" in t:
        return False, "403/차단 응답"
    return True, "응답 수신"


# ── 코어 수집기에 차단 게이트를 씌운다 (원본은 그대로 두고 감싼다) ───────────────────────────
_ORIG_KRXG_WARMUP = KRXG.warmup


def fetch_listing_snapshots_guarded(months: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX 스냅샷은 '보강'일 뿐이므로, 막혀 있으면 조용히 빈 표를 주고 넘어간다.
    유니버스의 진실은 상장일·폐지일(+가격이력 재구성)이지 스냅샷이 아니다."""
    if not krx_allowed():
        LOG.info("KRX 상장 스냅샷을 건너뜁니다(차단/비활성). 유니버스는 FDR·DART·네이버·"
                 "가격이력 재구성으로 구성되며, 이는 정상 경로입니다.")
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    return fetch_pykrx_snapshots(months)


KRXG.warmup = lambda: (krx_allowed() and _ORIG_KRXG_WARMUP())

# 가격 체인 재정렬 — §1-8 그대로 FDR 우선, pykrx 는 KRX 가 열려 있을 때만.
PRICE_CHAIN = [("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf),
               ("pykrx", lambda c, s, e: _px_pykrx(c, s, e) if krx_allowed() else None)]


# ═══ 상장주식수 — DART 주식총수현황 (비KRX · PIT 완전) ═══════════════════════════════════════
def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """DART '주식의 총수 현황'. 접수일(rcept_dt) 기준이라 PIT 가 구조적으로 보장된다.
    KRX 시가총액 스냅샷의 완전한 대체재이며, 오히려 PIT 관점에서는 더 낫다."""
    cols = ["corp_code", "period_end", "knowledge_date", "shares_total"]
    if not DART_API_KEY or not len(corp_codes):
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_shares_total", scope="shared")
    have = set()
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["knowledge_date"] = as_ts_series(cached["knowledge_date"])
        have = set(zip(cached["corp_code"].astype(str),
                       cached["period_end"].astype(str).str.slice(0, 4)))
        frames.append(cached.reindex(columns=cols))
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(cached):,}행 재사용")

    jobs = [(c, y) for c in corp_codes for y in years
            if (str(c), str(y)) not in have]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        LOG.info(f"DART 주식총수현황 {len(jobs):,}건 수집 (연 1회/사 — 사업보고서 기준)")

        def _one(job):
            c, y = job
            js = dart_api("stockTotqySttus.json",
                          {"corp_code": c, "bsns_year": int(y), "reprt_code": "11011"})
            if not js or not isinstance(js.get("list"), list):
                return None
            rows = []
            for r in js["list"]:
                q = str(r.get("istc_totqy", "")).replace(",", "").strip()
                if not q or not q.replace("-", "").isdigit():
                    continue
                rows.append({"corp_code": c, "period_end": f"{y}-12-31",
                             "rcept_no": r.get("rcept_no", ""),
                             "shares_total": float(q)})
            if not rows:
                return None
            d = pd.DataFrame(rows)
            # 같은 연도에 보통주/우선주가 여러 행 → 합계가 아니라 최대값(보통주 총수)을 취한다
            d = d.sort_values("shares_total", ascending=False).head(1)
            return d

        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
        got = [d for d in res if d is not None and len(d)]
        if got:
            n = pd.concat(got, ignore_index=True)
            n["knowledge_date"] = [_knowledge_from_rcept(rn, "11011", int(str(pe)[:4]))
                                   for rn, pe in zip(n.get("rcept_no", ""), n["period_end"])]
            frames.append(n.reindex(columns=cols))

    if not frames:
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True)
    S["period_end"] = S["period_end"].astype(str)
    S = S.dropna(subset=["corp_code", "shares_total"]).drop_duplicates(
        ["corp_code", "period_end"], keep="last")
    VAULT.put_table("dart_shares_total", S, scope="shared", domain="dart",
                    source="opendart stockTotqySttus",
                    extra={"note": "발행주식총수(PIT) — 전 전략 공용. KRX 시총 스냅샷 대체재"})
    PIPE.io("OUT", "DRIVE", "dart_shares_total", S, source="opendart")
    LOG.ok(f"DART 주식총수 {len(S):,}행 ({S['corp_code'].nunique():,}사) — "
           f"KRX 없이 PIT 시가총액 분모를 확보했습니다")
    return S


def shares_panel_from_dart(dart_sh: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """DART 주식총수 → (code, snap_date, shares) 형태로 변환해 기존 경로에 그대로 물린다."""
    if dart_sh is None or not len(dart_sh) or sec is None or not len(sec):
        return pd.DataFrame(columns=["snap_date", "code", "shares", "mcap_snap"])
    c2c = (sec.dropna(subset=["corp_code"])
              .assign(corp_code=lambda d: d["corp_code"].astype(str))
              .set_index("corp_code")["code"].to_dict())
    d = dart_sh.copy()
    d["code"] = d["corp_code"].astype(str).map(c2c)
    d = d.dropna(subset=["code"])
    if not len(d):
        return pd.DataFrame(columns=["snap_date", "code", "shares", "mcap_snap"])
    # snap_date 를 knowledge_date 로 둔다 → 하류에서 +1영업일이 한 번 더 붙어도 미래를 보지 않는다
    return pd.DataFrame({"snap_date": as_ts_series(d["knowledge_date"]), "code": d["code"],
                         "shares": pd.to_numeric(d["shares_total"], errors="coerce"),
                         "mcap_snap": np.nan}).dropna(subset=["snap_date", "shares"])


# ═══ 투자자 수급 — 네이버 (비KRX) ═══════════════════════════════════════════════════════════
_NV_TREND = "https://m.stock.naver.com/api/stock/{code}/trend"
_NV_FRGN = "https://finance.naver.com/item/frgn.naver?code={code}&page={page}"


def _nv_pick_key(keys: Sequence[str], *needles) -> Optional[str]:
    for k in keys:
        kl = str(k).lower()
        if all(n.lower() in kl for n in needles):
            return k
    return None


def _pick_date_col(d: pd.DataFrame) -> Optional[str]:
    """날짜 컬럼을 '이름'이 아니라 '내용'으로 찾는다.

    ★ 이름 추정은 실제로 깨진다: 네이버는 날짜 필드를 localTradedAt 으로 준다 —
      'date' 도 'dt' 도 들어 있지 않다. 이름 규칙에 걸면 조용히 전 종목 수집이 실패한다.
      (이 함수는 리허설이 실제로 잡아낸 결함을 고친 것이다)
    """
    best, best_score = None, 0.0
    for c in d.columns:
        try:
            v = as_ts_series(d[c])
        except Exception:
            continue
        ok = v.notna()
        if not ok.any():
            continue
        sane = ok & (v >= pd.Timestamp("1990-01-01")) & (v <= pd.Timestamp("2100-01-01"))
        score = float(sane.mean())
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.7 else None


def naver_trend_flows(code: str, start: str, end: str, page_size: int = 300,
                      max_pages: int = 12) -> Optional[pd.DataFrame]:
    """네이버 모바일 API 의 종목별 투자자 매매동향(JSON).
    ★ 필드명이 개편될 수 있으므로 이름을 하드코딩하지 않고 '내용으로' 찾는다."""
    rows = []
    for page in range(1, max_pages + 1):
        js = http_json(_NV_TREND.format(code=code), source="naver",
                       params={"pageSize": page_size, "page": page}, tries=2,
                       referer=f"https://m.stock.naver.com/domestic/stock/{code}/trend")
        block = None
        if isinstance(js, dict):
            for v in js.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    block = v
                    break
        elif isinstance(js, list) and js and isinstance(js[0], dict):
            block = js
        if not block:
            break
        rows.extend(block)
        if len(block) < page_size:
            break
    if not rows:
        return None
    d = pd.DataFrame(rows)
    ks = list(d.columns)
    date_k = _pick_date_col(d)
    ind_k = _nv_pick_key(ks, "individ") or _nv_pick_key(ks, "personal")
    frg_k = _nv_pick_key(ks, "foreign")
    org_k = _nv_pick_key(ks, "organ") or _nv_pick_key(ks, "institu")
    close_k = _nv_pick_key(ks, "close") or _nv_pick_key(ks, "price")
    if date_k is None or (ind_k is None and frg_k is None and org_k is None):
        LOG.debug(f"네이버 수급 필드 인식 실패({code}) — 컬럼: {ks[:10]}")
        return None
    num = lambda k: (pd.to_numeric(d[k].astype(str).str.replace(",", "", regex=False),
                                   errors="coerce") if k else pd.Series(np.nan, index=d.index))
    close = num(close_k).replace(0, np.nan)

    # 순매수가 '수량'이면 금액으로 환산한다 — 단위 혼동은 f_inst/f_ret_ex 스케일을 통째로 망친다
    def to_krw(s):
        if s.isna().all():
            return s
        med = float(s.abs().median() or 0)
        return s * close if (med < 1e6 and close.notna().any()) else s

    out = pd.DataFrame({
        "code": code, "date": as_ts_series(d[date_k]),
        "retail_net": to_krw(num(ind_k)), "inst_net": to_krw(num(org_k)),
        "foreign_net": to_krw(num(frg_k)), "src": "naver_trend"})
    out = out.dropna(subset=["date"])
    out = out[(out["date"] >= as_ts(start)) & (out["date"] <= as_ts(end))]
    if out.empty or out[["retail_net", "inst_net", "foreign_net"]].notna().sum().sum() == 0:
        return None
    if ind_k is None:
        # 개인이 없으면 개인 ≈ -(기관+외국인). 기타법인이 빠진 근사임을 명시한다.
        out["retail_net"] = -(out["inst_net"].fillna(0) + out["foreign_net"].fillna(0))
        out["src"] = "naver_trend(개인=근사)"
    return out


def naver_frgn_flows(code: str, start: str, end: str, max_pages: int = 40
                     ) -> Optional[pd.DataFrame]:
    """네이버 금융 '외국인·기관' 표(HTML). JSON 경로가 막혔을 때의 최종 폴백.
    개인은 제공되지 않으므로 -(기관+외국인) 근사이며, 그 사실을 src 에 남긴다."""
    frames = []
    for page in range(1, max_pages + 1):
        html = http_get(_NV_FRGN.format(code=code, page=page), source="naver", tries=2,
                        referer=f"https://finance.naver.com/item/main.naver?code={code}")
        if not html:
            break
        try:
            tabs = pd.read_html(io.StringIO(html))
        except Exception:
            break
        t = None
        for cand in tabs:
            cols = " ".join(str(c) for c in np.ravel(cand.columns))
            if "날짜" in cols and ("기관" in cols or "외국인" in cols):
                t = cand
                break
        if t is None or not len(t):
            break
        t.columns = [" ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)
                     for c in t.columns]
        dcol = next((c for c in t.columns if "날짜" in c), None)
        ccol = next((c for c in t.columns if "종가" in c), None)
        icol = next((c for c in t.columns if "기관" in c), None)
        fcol = next((c for c in t.columns if "외국인" in c and "보유" not in c), None)
        if dcol is None:
            break
        num = lambda c: (pd.to_numeric(t[c].astype(str).str.replace(",", "", regex=False),
                                       errors="coerce") if c else pd.Series(np.nan, index=t.index))
        close = num(ccol)
        part = pd.DataFrame({"code": code, "date": as_ts_series(t[dcol]),
                             "inst_net": num(icol) * close, "foreign_net": num(fcol) * close})
        part = part.dropna(subset=["date"])
        if part.empty:
            break
        frames.append(part)
        if part["date"].min() < as_ts(start):
            break
    if not frames:
        return None
    F = pd.concat(frames, ignore_index=True).drop_duplicates(["code", "date"])
    F = F[(F["date"] >= as_ts(start)) & (F["date"] <= as_ts(end))]
    if F.empty:
        return None
    F["retail_net"] = -(F["inst_net"].fillna(0) + F["foreign_net"].fillna(0))
    F["src"] = "naver_frgn(개인=근사)"
    return F


# ═══ 다중소스 코드 발굴 · 상장/폐지 창 재구성 (KRX 없이 C2·C13 성립) ══════════════════════════
UNIV_SRC_LEDGER: List[dict] = []


def discover_codes_multi(sec: pd.DataFrame) -> pd.DataFrame:
    """종목 코드 발굴을 한 소스에 걸지 않는다. 어느 소스가 몇 개를 기여했는지 원장에 남긴다."""
    parts = []
    if sec is not None and len(sec):
        parts.append(("기존 마스터(FDR/KIND/폐지목록)", set(sec["code"].dropna())))
    # DART corpCode — 상장폐지된 회사도 남아 있으므로 생존자편향 방어에 직접 기여한다
    try:
        cc = fetch_dart_corpcode()
        if cc is not None and len(cc) and "code" in cc.columns:
            parts.append(("DART corpCode", set(cc["code"].dropna().map(to_code6)) - {None}))
    except Exception as e:                                            # noqa
        LOG.debug(f"DART corpCode 발굴 실패: {type(e).__name__}")
    # 네이버 시세 목록(현재 상장분) — 이름·시장 보강용
    try:
        nv = set()
        for mkt, sosok in (("KOSPI", 0), ("KOSDAQ", 1)):
            for page in range(1, 4):
                html = http_get("https://finance.naver.com/sise/sise_market_sum.naver",
                                source="naver", params={"sosok": sosok, "page": page}, tries=1)
                if not html:
                    break
                nv |= {to_code6(m) for m in re.findall(r"code=(\d{6})", html)}
        nv.discard(None)
        if nv:
            parts.append(("네이버 시세목록", nv))
    except Exception as e:                                            # noqa
        LOG.debug(f"네이버 시세목록 발굴 실패: {type(e).__name__}")

    allc: set = set()
    for name, s in parts:
        new = len(s - allc)
        UNIV_SRC_LEDGER.append({"source": name, "codes": len(s), "new": new})
        allc |= s
    LOG.table([[r["source"], f"{r['codes']:,}", f"{r['new']:,}"] for r in UNIV_SRC_LEDGER],
              ["코드 소스", "보유", "신규 기여"], ["l", "r", "r"],
              title=f"다중소스 종목 발굴 — 합집합 {len(allc):,}종목 (KRX 없이 구성)")
    base = sec.copy() if sec is not None and len(sec) else pd.DataFrame(columns=SEC_MASTER_COLS)
    missing = sorted(allc - set(base["code"])) if len(base) else sorted(allc)
    if missing:
        # 새로 발굴한 종목도 corp_code 를 붙여야 DART 방화벽이 그 종목에 작동한다
        cmap, nmap = {}, {}
        try:
            cc = fetch_dart_corpcode()
            if cc is not None and len(cc):
                cc = cc.dropna(subset=["code"]).drop_duplicates("code")
                cmap = dict(zip(cc["code"].map(to_code6), cc["corp_code"].astype(str)))
                nmap = dict(zip(cc["code"].map(to_code6), cc["corp_name"].astype(str)))
        except Exception:
            pass
        add = pd.DataFrame({"code": missing,
                            "name": [nmap.get(c, "") for c in missing],
                            "market": "", "listing_date": pd.NaT,
                            "delisting_date": pd.NaT,
                            "corp_code": [cmap.get(c, np.nan) for c in missing],
                            "industry": "",
                            "sector_src": "multi", "src": "multi_discovery"})
        base = pd.concat([base.reindex(columns=list(dict.fromkeys(SEC_MASTER_COLS))),
                          add.reindex(columns=list(dict.fromkeys(SEC_MASTER_COLS)))],
                         ignore_index=True)
        LOG.info(f"명부에 없던 {len(missing):,}종목을 추가했습니다 — 빠뜨리면 그대로 생존자편향입니다.")
    return base.drop_duplicates("code")


def reconstruct_listing_windows(sec: pd.DataFrame, px: pd.DataFrame,
                                panel_end: str) -> pd.DataFrame:
    """★ KRX 명부 없이도 성립하는 상장/폐지 판정 — '거래가 있었다'는 사실 자체가 증거다.

      · listing_date  결측 → 첫 거래일 (가격 이력의 시작)
      · delisting_date 결측 → 마지막 거래일 이후 60거래일간 거래가 없고, 패널 종료일보다
        충분히 앞서면 그 시점에 상장폐지된 것으로 '추정'한다. 추정분은 provenance 에 남긴다.
      · 추정은 언제나 명부보다 우선순위가 낮다(명부가 있으면 명부를 쓴다).

    이 재구성이 없으면, KRX 가 막힌 순간 폐지 종목이 '데이터 없음'으로 조용히 사라지고
    그것이 곧 생존자편향이다. 그래서 이 함수는 선택이 아니라 필수 경로다.
    """
    if px is None or not len(px):
        return sec
    S = sec.copy()
    S["listing_date"] = as_ts_series(S["listing_date"])
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    g = px.groupby("code")["date"]
    first_t, last_t = g.min(), g.max()
    end_ts = as_ts(panel_end)
    cal = np.sort(pd.unique(as_ts_series(px["date"]).values))
    # 마지막 거래일이 '전체 거래일 기준 60일 이전'이면 더 이상 거래되지 않는 종목으로 본다
    cutoff_idx = max(0, len(cal) - 60)
    cutoff = pd.Timestamp(cal[cutoff_idx]) if len(cal) else end_ts

    S["first_trade"] = S["code"].map(first_t)
    S["last_trade"] = S["code"].map(last_t)
    prov_l, prov_d = [], []
    ld, dd = [], []
    for r in S.itertuples(index=False):
        l0, d0 = r.listing_date, r.delisting_date
        ft, lt = getattr(r, "first_trade", pd.NaT), getattr(r, "last_trade", pd.NaT)
        if pd.notna(l0):
            ld.append(l0); prov_l.append("명부")
        elif pd.notna(ft):
            ld.append(ft); prov_l.append("가격이력 재구성")
        else:
            ld.append(pd.NaT); prov_l.append("없음")
        if pd.notna(d0):
            dd.append(d0); prov_d.append("명부")
        elif pd.notna(lt) and lt < cutoff:
            dd.append(lt + pd.Timedelta(days=1)); prov_d.append("가격이력 재구성(추정)")
        else:
            dd.append(pd.NaT); prov_d.append("상장 중")
    S["listing_date"], S["delisting_date"] = ld, dd
    S["listing_src"], S["delisting_src"] = prov_l, prov_d

    rows = []
    for col, lab in (("listing_src", "상장일"), ("delisting_src", "폐지일")):
        vc = S[col].value_counts()
        for k, v in vc.items():
            rows.append([lab, k, f"{v:,}"])
    LOG.table(rows, ["항목", "근거", "종목수"], ["l", "l", "r"],
              title="상장/폐지일 출처 원장 (C2) — 어떤 근거로 유니버스 멤버십이 정해졌는가")
    n_est = int((S["delisting_src"] == "가격이력 재구성(추정)").sum())
    n_known = int((S["delisting_src"] == "명부").sum())
    LOG.ok(f"폐지 종목 {n_known + n_est:,}개 확보 (명부 {n_known:,} + 가격이력 추정 {n_est:,}) — "
           f"KRX 없이 C2(생존자편향 제거) 성립")
    if n_known + n_est < 100:
        LOG.warn("폐지 종목이 100개 미만입니다. 10년이면 통상 수백 종목이 사라집니다 — "
                 "가격 수집 커버리지가 낮으면 폐지 종목이 '데이터 없음'으로 빠져 "
                 "생존자편향이 남습니다. 이 수치를 반드시 결과 해석에 반영하세요.")
    return S.drop(columns=["first_trade", "last_trade"], errors="ignore")


def audit_survivorship_coverage(sec: pd.DataFrame, px: pd.DataFrame,
                                start: str, end: str) -> pd.DataFrame:
    """★ 생존자편향 '잔존분'을 추정해 표로 낸다. 제거했다고 주장하는 대신 남은 양을 측정한다.

    폐지 종목을 유니버스에 넣어도, 그 종목의 가격이 없으면 백테스트는 그 종목을 애초에
    살 수 없다 → 실제로는 사서 -100% 를 맞았을 사례가 통째로 빠지고 성과가 위로 편향된다.
    (KRX 가 막히면 폐지 직전 구간 가격을 못 받는 일이 잦으므로 특히 중요하다)
    """
    if sec is None or not len(sec):
        return pd.DataFrame()
    S = sec.copy()
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    win = S[(S["delisting_date"] >= as_ts(start)) & (S["delisting_date"] <= as_ts(end))]
    n_win = len(win)
    if n_win == 0:
        LOG.warn("백테스트 구간 내 상장폐지 종목이 0건입니다 — 생존자편향이 그대로 남아 있습니다(C2 미충족).")
        return pd.DataFrame()
    cov = pd.DataFrame()
    if px is not None and len(px):
        last = px.groupby("code")["date"].max()
        w = win.copy()
        w["last_px"] = w["code"].map(last)
        w["gap_days"] = (w["delisting_date"] - w["last_px"]).dt.days
        have = w["last_px"].notna()
        near = have & (w["gap_days"].abs() <= 60)
        rows = [["구간 내 폐지 종목", f"{n_win:,}", "유니버스에 포함되어야 하는 전량"],
                ["가격 이력 보유", f"{int(have.sum()):,}",
                 f"{100*have.mean():.1f}% — 없으면 애초에 매수 자체가 불가"],
                ["폐지 시점 근처(±60일) 가격 보유", f"{int(near.sum()):,}",
                 f"{100*near.mean():.1f}% — 이 종목만 정리매매/-100% 가 정상 반영된다"],
                ["★ 생존자편향 잔존 추정", f"{int((~near).sum()):,}",
                 f"{100*(~near).mean():.1f}% — 이만큼은 '살 수 없어서' 손실이 계상되지 않는다"]]
        LOG.table(rows, ["항목", "종목수", "의미"], ["l", "r", "l"],
                  title="C2 생존자편향 잔존 감사 — 제거를 주장하지 않고 남은 양을 측정한다")
        if float((~near).mean()) > 0.5:
            LOG.warn("폐지 종목의 절반 이상이 폐지 시점 가격을 갖지 못했습니다. "
                     "성과는 그만큼 위로 편향되어 있습니다 — 결과 해석에 반드시 반영하세요. "
                     "(가격 소스가 폐지 종목을 잘 주지 않는 구조적 한계이며 숨기지 않습니다)")
        cov = w[["code", "delisting_date", "last_px", "gap_days"]]
    return cov


def select_flow_targets(px: pd.DataFrame, start: str, end: str,
                        max_codes: int = FLOW_MAX_CODES) -> List[str]:
    """수급을 '전 종목'이 아니라 '이 전략이 실제로 진입할 수 있었던 종목'에만 받는다.

    ★ 이 선별은 반드시 '인과적(causal)'이어야 한다.
      전 구간 중앙 거래대금이나 전 구간 최대 낙폭 같은 '표본 전체 통계'로 고르면,
      나중에 거래대금이 말라 죽은 종목(=상장폐지 예비군)이 통째로 제외된다.
      그건 곧 생존자편향의 재유입이며, 성과를 위로 부풀린다.
      → 각 시점 t 의 '그 시점까지의 정보'(252일 낙폭·252일 평균거래대금)로 후보를 판정하고,
        한 번이라도 후보였던 종목을 수집 대상으로 삼는다. 시점 t 의 신호는 시점 t 에
        이미 존재하던 조건으로만 결정되므로 미래정보가 개입하지 않는다.

    국면 C 는 f_dd < -0.30 을 요구하므로, 그만한 낙폭을 겪은 적이 없는 종목의 수급은
    어차피 신호에 쓰이지 않는다. 전 종목을 받으면 4시간 예산을 수급 하나가 다 쓴다(§9).
    제외된 것이 무엇이고 그 대가가 얼마인지는 표로 남긴다 — 조용한 축소는 하지 않는다.
    """
    if px is None or not len(px):
        return []
    d = px[(px["date"] >= as_ts(start) - pd.Timedelta(days=400)) &
           (px["date"] <= as_ts(end))][["code", "date", "close", "amount"]].copy()
    if d.empty:
        return []
    d = d.sort_values(["code", "date"])
    g = d.groupby("code", observed=True)
    roll_max = g["close"].transform(lambda s: s.rolling(252, min_periods=60).max())
    d["dd"] = d["close"] / roll_max - 1.0
    d["adv252"] = g["amount"].transform(lambda s: s.rolling(252, min_periods=60).mean())

    # 시점별 후보 여부 — 전부 '그 시점까지'의 정보만 쓴다
    cand = (d["dd"] <= FLOW_DD_PREFILTER) & (d["adv252"] >= MIN_ADV_KRW)
    d["cand"] = cand.fillna(False)
    n_all = int(d["code"].nunique())
    ever = d.groupby("code", observed=True)["cand"].any()
    cand_codes = ever[ever].index.astype(str)
    if not len(cand_codes):
        LOG.warn("수급 대상 후보가 0종목입니다 — 낙폭/유동성 프리필터가 너무 강하거나 "
                 "가격 커버리지가 부족합니다. 전 종목으로 진행합니다(느립니다).")
        return []

    sub = d[d["code"].isin(set(cand_codes))]
    weeks_per_code = sub.groupby("code", observed=True)["cand"].sum()
    # 우선순위: '최초 후보 시점의 유동성' — 사후 통계가 아니라 그때의 관측치를 쓴다
    first_hit = (sub[sub["cand"]].sort_values("date")
                 .drop_duplicates("code", keep="first").set_index("code")["adv252"])
    ranked = first_hit.sort_values(ascending=False)
    capped = ranked.head(max_codes) if max_codes and max_codes > 0 else ranked
    kept = set(capped.index.astype(str))

    tot_w = float(weeks_per_code.sum())
    lost_w = float(weeks_per_code[~weeks_per_code.index.isin(kept)].sum())
    rows = [["전체 가격 보유 종목", f"{n_all:,}", ""],
            [f"후보 경험 (252일 낙폭 ≤ {FLOW_DD_PREFILTER:+.0%} ∧ ADV252 ≥ "
             f"{MIN_ADV_KRW/1e8:.0f}억, 시점별 판정)", f"{len(cand_codes):,}",
             f"{100*len(cand_codes)/max(n_all,1):.0f}%"],
            ["수집 대상(상한 적용)", f"{len(kept):,}",
             f"상한 {max_codes or '무제한'} · 제외 {len(ranked)-len(capped):,}"],
            ["★ 상한으로 잃는 후보-일수", f"{lost_w:,.0f}",
             f"전체 후보-일수의 {100*lost_w/max(tot_w,1):.1f}% — 이만큼이 커버리지 손실"]]
    LOG.table(rows, ["단계", "종목수/일수", "비고"], ["l", "r", "l"],
              title="수급 수집 대상 선별 (인과적 판정) — 진입 불가능했던 종목은 받지 않는다(§9)")
    if lost_w > 0:
        LOG.warn(f"상한(FLOW_MAX_CODES={max_codes})으로 후보-일수의 "
                 f"{100*lost_w/max(tot_w,1):.1f}% 가 수급 없이 남습니다. 해당 종목은 f_inst 결측 → "
                 f"국면 C 판정에서 자동 탈락하므로 '성과'가 아니라 '커버리지'의 한계이며, "
                 f"캐시가 누적되는 재실행마다 줄어듭니다. 0으로 만들려면 FLOW_MAX_CODES=0.")
    return sorted(kept)
