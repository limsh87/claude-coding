# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-A  강제 재고(신용융자잔고) · 소유권 이전(투자자유형별 순매수) · 시가총액 · 감시목록  ║
# ║                                                                                          ║
# ║  이 전략의 데이터 등급이 여기서 결정된다(§5.2 / F1 카나리).                                ║
# ║    PRIMARY_DAILY    종목별 '일별' 신용거래융자 잔고        → 완전체                        ║
# ║    FALLBACK_A_WEEKLY 주간 관측 + forward-fill(★보간 금지)  → 해상도 손실                   ║
# ║    FALLBACK_B_PROXY 개인 순매수 252일 누적 / 시가총액      → 사실상 다른 전략              ║
# ║  조용히 강등되지 않는다. 등급은 전역 CREDIT_GRADE 에 남고 리포트 첫 줄에 인쇄된다.          ║
# ║                                                                                          ║
# ║  PIT: 신용잔고·수급의 knowledge_date = 거래일 + 1영업일 (당일 잔고는 익일 공표).           ║
# ║       이 하루를 흘리면 일 단위 타이밍 전략인 이 전략의 성과가 크게 부풀려진다(§4.1).        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CREDIT_GRADE = "UNKNOWN"          # PRIMARY_DAILY / FALLBACK_A_WEEKLY / FALLBACK_B_PROXY / NONE
CREDIT_SOURCE_NOTE = ""
FLOW_GRADE = "UNKNOWN"            # FULL / APPROX(개인=근사) / PARTIAL / NONE
FLOW_APPROX = False               # 개인이 -(기관+외국인) 근사인가 (퇴화 판정의 근거)
WATCH_GRADE = "UNKNOWN"           # OK / PARTIAL / NONE
CANARY: "OrderedDict[str, dict]" = OrderedDict()


def canary(cid: str, name: str, passed: Optional[bool], measured: str, action: str = ""):
    """카나리 결과는 '측정값'과 '그래서 무엇을 하는가'를 함께 남긴다. 추측 금지(§2)."""
    CANARY[cid] = {"id": cid, "name": name, "pass": passed, "measured": measured,
                   "action": action}
    icon = "✔" if passed else ("✘" if passed is False else "→")
    (LOG.ok if passed else (LOG.error if passed is False else LOG.info))(
        f"[CANARY {cid}] {icon} {name} — {measured}" + (f" · 조치: {action}" if action else ""))


def _trading_calendar(px: pd.DataFrame) -> np.ndarray:
    if px is None or len(px) == 0:
        return np.array([], dtype="datetime64[ns]")
    return np.sort(pd.unique(as_ts_series(px["date"]).values))


# ═══ 시가총액 (신용잔고율의 분모) ═══════════════════════════════════════════════════════════
def fetch_shares_outstanding(months: pd.DatetimeIndex, sec: Optional[pd.DataFrame] = None,
                             dart_shares: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """상장주식수 월말 스냅샷. 일별 시총 = 일별 종가 × (과거 스냅샷 상장주식수 forward-fill).

    ★ 종목별로 2,500번 부르지 않는다. '날짜별 전종목' 1콜이면 끝나므로 120콜로 10년이 덮인다.
      (종목 루프로 짜면 같은 결과에 수십 배의 시간과 차단 위험을 지불한다)
    ★ 현재 상장주식수를 과거에 적용하면 액면분할·유상증자가 소급되어 시총이 조용히 틀어진다.
    """
    cols = ["snap_date", "code", "shares", "mcap_snap"]
    # ★ 1순위는 DART 주식총수현황이다. 접수일 기준이라 PIT 가 구조적으로 보장되고
    #   KRX 차단과 무관하게 동작한다. KRX 스냅샷은 '보강'이지 전제가 아니다.
    dart_panel = shares_panel_from_dart(dart_shares, sec) if dart_shares is not None else \
        pd.DataFrame(columns=cols)
    if len(dart_panel):
        LOG.ok(f"DART 주식총수 기반 상장주식수 {len(dart_panel):,}행 "
               f"({dart_panel['code'].nunique():,}종목) — KRX 없이 시총 분모 확보")
    cached = VAULT.get_table("krx_shares_outstanding_monthly", scope="shared")
    have = set()
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        frames.append(cached[cols])
        LOG.info(f"공용 캐시에서 상장주식수 스냅샷 {len(have)}개 시점 재사용")

    todo = [m for m in months if m.strftime("%Y-%m-%d") not in have]
    if not krx_allowed():
        todo = []
    if RUN_MODE == "CACHED" or pykrx_stock is None:
        if todo:
            LOG.warn("상장주식수 스냅샷 신규 수집 불가(CACHED 모드 또는 pykrx 없음) — "
                     "시가총액은 캐시분으로만 구성됩니다.")
        todo = []
    if todo and not KRXG.warmup():
        LOG.warn("KRX 세션 없음 — 상장주식수 스냅샷을 건너뜁니다. "
                 "신용잔고율의 분모가 없으면 f_cr 은 '거래대금 20일합' 대리 분모로 폴백합니다.")
        todo = []

    new = []
    if todo:
        bad = 0
        for m in tqdm(todo, desc="상장주식수 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
            d = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd)
            if d is None or len(d) == 0:
                bad += 1
                if bad >= 5:
                    LOG.warn("상장주식수 스냅샷이 연속 5회 비었습니다 — 세션 만료로 판단하고 중단합니다.")
                    break
                continue
            bad = 0
            d = d.reset_index()
            code_c = next((c for c in d.columns if str(c) in ("티커", "종목코드", "ticker")), d.columns[0])
            sh_c = next((c for c in d.columns if "상장주식수" in str(c)), None)
            mc_c = next((c for c in d.columns if "시가총액" in str(c)), None)
            if sh_c is None and mc_c is None:
                continue
            new.append(pd.DataFrame({
                "snap_date": m, "code": d[code_c].map(to_code6),
                "shares": pd.to_numeric(d[sh_c], errors="coerce") if sh_c else np.nan,
                "mcap_snap": pd.to_numeric(d[mc_c], errors="coerce") if mc_c else np.nan,
            }))
        if new:
            frames.append(pd.concat(new, ignore_index=True))

    if len(dart_panel):
        frames.append(dart_panel.reindex(columns=cols))
    if not frames:
        LOG.warn("상장주식수를 한 건도 확보하지 못했습니다 — 시가총액은 '거래대금 20일합' "
                 "대리 분모로 대체됩니다(스케일만 다르고 f_cr 백분위는 성립). "
                 "DART_API_KEY 를 넣으면 PIT 정확한 분모가 생깁니다.")
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True).dropna(subset=["code", "snap_date"])
    S = S.drop_duplicates(["snap_date", "code"], keep="last")[cols]
    if new:
        out = S.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_shares_outstanding_monthly", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "상장주식수 월말 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_shares_outstanding_monthly", S, source="pykrx")
    return S


# ═══ 투자자유형별 일별 순매수 (개인 / 기관 / 외국인) ════════════════════════════════════════
FLOW_COLS = ["code", "date", "retail_net", "inst_net", "foreign_net"]
FLOW_TABLE_COLS = FLOW_COLS + ["src"]


def _flow_from_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None or not krx_allowed():
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_trading_value_by_date(
            as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d = d.rename(columns={d.columns[0]: "date"})

    def pick(*keys):
        for k in keys:
            c = next((c for c in d.columns if k in str(c)), None)
            if c is not None:
                return pd.to_numeric(d[c], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    out = pd.DataFrame({
        "code": code, "date": as_ts_series(d["date"]),
        "retail_net": pick("개인"),
        "inst_net": pick("기관합계", "기관"),
        "foreign_net": pick("외국인합계", "외국인"),
        "src": "pykrx",
    })
    return out if out[["retail_net", "inst_net", "foreign_net"]].notna().any().any() else None


def _flow_one(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """수급 취득 사다리. 어느 경로로 받았는지 src 에 남겨 감사표에 노출한다.
    ★ KRX 가 막혀도 '소유권 이전' 관측이 끊기지 않게 하는 것이 이 사다리의 존재 이유다."""
    for fn in (_flow_from_pykrx, naver_trend_flows, naver_frgn_flows):
        try:
            r = fn(code, start, end)
        except Exception:
            r = None
        if r is not None and len(r):
            return r.reindex(columns=FLOW_COLS + ["src"])
    return None


def fetch_investor_flows_daily(codes: Sequence[str], start: str, end: str,
                               sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """종목별 일별 투자자유형 순매수(금액). 이 전략의 '소유권 이전' 관측치.

    F2 카나리가 여기서 판정된다. 실패하면 §11-2 킬 기준(소유권 이전 관측 불가)이다.
    knowledge_date = 거래일 + 1영업일 (T+1 공표).
    """
    global FLOW_GRADE
    codes = sorted({c for c in map(to_code6, codes) if c})
    cached = VAULT.get_table("krx_investor_flows_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        for c in FLOW_TABLE_COLS:
            if c not in cached.columns:
                cached[c] = np.nan
        have_max = cached.groupby("code")["date"].max().to_dict()
        frames.append(cached[FLOW_TABLE_COLS])
        LOG.info(f"공용 캐시에서 일별 수급 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    # ★ 가격과 똑같은 낭비가 여기서 훨씬 비싸게 일어난다(종목당 최대 9페이지).
    #   폐지·거래정지 종목은 마지막 관측일이 영원히 종료일보다 이르므로, 커버리지 판정 없이
    #   '최대일 < 종료일-7일' 만 보면 매 실행 전량 재수집된다. 가격과 같은 판정기를 쓴다.
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        have_min = cached.groupby("code")["date"].min().to_dict()
    listing, delist = {}, {}
    if sec is not None and len(sec) and "code" in sec.columns:
        _s = sec.dropna(subset=["code"]).drop_duplicates("code")
        if "listing_date" in _s.columns:
            listing = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["listing_date"]))
                       if pd.notna(d)}
        if "delisting_date" in _s.columns:
            delist = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["delisting_date"]))
                      if pd.notna(d)}
    _today = as_ts(_dt.date.today())
    eff_end = min(as_ts(end), _today)
    attempts: Dict[str, dict] = {}
    _fa = VAULT.get_table("flow_fetch_attempts", scope="shared")
    if _fa is not None and len(_fa):
        _fa = _fa.copy()
        for _c in ("attempted_at", "requested_from", "got_min", "got_max"):
            if _c not in _fa.columns:
                _fa[_c] = pd.NaT
            _fa[_c] = as_ts_series(_fa[_c])
        _fa = _fa.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from,
                                  "gmin": r.got_min, "gmax": r.got_max}
                    for r in _fa.itertuples(index=False)}
    todo, reasons = ([], Counter())
    if RUN_MODE != "CACHED":
        todo, reasons = plan_price_fetch(codes, as_ts(start), eff_end, have_min, have_max,
                                         listing, delist, attempts, _today,
                                         retry_fail_days=30, retry_stale_days=21,
                                         tol_back=14, tol_fwd=7)
    if reasons:
        LOG.table([[k, f"{v:,}"] for k, v in reasons.most_common()] +
                  [["── 실제 수집 대상", f"{len(todo):,}"]],
                  ["판정 사유", "종목수"], ["l", "r"],
                  title=f"수급 수집 판정 — 대상 {len(codes):,}종목 중 {len(todo):,}종목만 받습니다")
    if todo:
        LOG.info(f"일별 수급 {len(todo):,}종목 수집 (캐시 미보유/증분분만)")
        fails = {"n": 0}

        def _one(job):
            c, s = job
            r = _flow_one(c, s, end)
            if r is None:
                fails["n"] += 1
            return r

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="일별 수급")
        got = [d for d in res if d is not None and len(d)]
        if got:
            frames.append(pd.concat(got, ignore_index=True).reindex(columns=FLOW_TABLE_COLS))
        # ★ 시도 원장: 받아도 커버리지가 안 늘면 다음 실행이 같은 요청을 반복하지 않는다
        _att_rows = []
        for (c, st), d in zip(todo, res):
            _dd = as_ts_series(d["date"]) if (d is not None and len(d)) else pd.Series(dtype="datetime64[ns]")
            _gmin = min([x for x in (have_min.get(c), (_dd.min() if len(_dd) else pd.NaT))
                         if pd.notna(x)] or [pd.NaT])
            _gmax = max([x for x in (have_max.get(c), (_dd.max() if len(_dd) else pd.NaT))
                         if pd.notna(x)] or [pd.NaT])
            _att_rows.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today,
                              "got_min": _gmin, "got_max": _gmax})
        if _att_rows:
            _prev = _fa if (_fa is not None and len(_fa)) else None
            _all = pd.concat([_prev, pd.DataFrame(_att_rows)], ignore_index=True) \
                if _prev is not None else pd.DataFrame(_att_rows)
            _all = (_all.sort_values("attempted_at").drop_duplicates("code", keep="last")
                        .reset_index(drop=True))
            VAULT.put_table("flow_fetch_attempts", _all, scope="shared", domain="flow",
                            source="fetch_investor_flows_daily:coverage_ledger")
        if fails["n"] > len(todo) * 0.7:
            LOG.warn(f"수급 수집 실패율 {100*fails['n']/max(len(todo),1):.0f}% — KRX 세션/차단을 의심하세요.")

    if not frames:
        FLOW_GRADE = "NONE"
        LOG.error("투자자유형별 순매수를 한 건도 확보하지 못했습니다. "
                  "이 전략의 핵심인 '소유권 이전'을 관측할 수 없습니다(§11-2 킬 기준).")
        return pd.DataFrame(columns=FLOW_COLS)

    F = pd.concat(frames, ignore_index=True)
    F["date"] = as_ts_series(F["date"])
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"]))
    has_retail = float(F["retail_net"].notna().mean())
    approx = float(F.get("src", pd.Series("", index=F.index)).astype(str)
                    .str.contains("근사").mean())
    globals()["FLOW_APPROX"] = bool(approx >= 0.5)
    FLOW_GRADE = ("FULL" if (has_retail > 0.5 and approx < 0.5)
                  else ("APPROX" if has_retail > 0.5 else ("PARTIAL" if len(F) else "NONE")))
    if FLOW_GRADE == "APPROX":
        LOG.warn(f"수급의 {approx:.0%} 가 '개인 = -(기관+외국인)' 근사입니다(네이버 경로). "
                 f"기타법인이 빠져 있으므로 f_retail·f_ret_ex 에 계통오차가 있습니다 — "
                 f"숨기지 않고 등급으로 표기합니다.")
    src_tab = (F.get("src", pd.Series(dtype=str)).astype(str).value_counts()
               if "src" in F.columns else pd.Series(dtype=int))
    if len(src_tab):
        LOG.table([[k, f"{v:,}"] for k, v in src_tab.items()], ["수급 소스", "행수"], ["l", "r"],
                  title="수급 취득 경로 원장 (KRX 차단 시 네이버로 자동 전환)")
    if FLOW_GRADE == "PARTIAL":
        LOG.warn("수급에 '개인' 분해가 없습니다 — f_ret_ex(개인 이탈)가 결측이 되고 "
                 "TP_F2 의 절반이 죽습니다. 0으로 채우지 않습니다.")
    VAULT.put_table("krx_investor_flows_daily", F, scope="shared", domain="flow",
                    source="pykrx trading_value_by_date",
                    extra={"note": "종목별 일별 개인/기관/외국인 순매수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_investor_flows_daily", F, source="pykrx")
    return downcast(F)


# ═══ 신용융자잔고 ═══════════════════════════════════════════════════════════════════════════
CREDIT_COLS = ["code", "date", "credit_bal", "src"]

# KRX 정보데이터시스템 bld 후보군. 화면 개편으로 ID가 바뀌므로 '하나를 믿지 않고' 프로브한다.
# (KRX_CREDIT_BLD 를 직접 지정하면 그것만 쓴다)
KRX_CREDIT_BLD_CANDIDATES = [
    "dbms/MDC/STAT/srt/MDCSTAT04601",
    "dbms/MDC/STAT/srt/MDCSTAT04701",
    "dbms/MDC/STAT/srt/MDCSTAT04801",
    "dbms/MDC/STAT/standard/MDCSTAT04601",
    "dbms/MDC/STAT/srt/MDCSTAT05001",
]
_CREDIT_VALUE_KEYS = ("융자잔고", "신용잔고", "잔고금액", "LOAN_BAL", "CRDT")


def _parse_krx_credit_json(js: Any, dt: pd.Timestamp) -> Optional[pd.DataFrame]:
    """KRX getJsonData 응답 → (code, date, credit_bal). 컬럼명이 개편마다 바뀌므로
    '코드처럼 생긴 컬럼' + '잔고처럼 생긴 컬럼'을 내용으로 찾는다."""
    if not isinstance(js, dict):
        return None
    block = None
    for k, v in js.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            block = v
            break
    if not block:
        return None
    d = pd.DataFrame(block)
    code_c = next((c for c in d.columns
                   if d[c].astype(str).str.fullmatch(r"\d{6}").mean() > 0.7), None)
    if code_c is None:
        code_c = next((c for c in d.columns if str(c).upper() in ("ISU_SRT_CD", "ISU_CD")), None)
    if code_c is None:
        return None
    val_c = None
    for c in d.columns:
        cu = str(c).upper()
        if any(k.upper() in cu for k in _CREDIT_VALUE_KEYS):
            val_c = c
            break
    if val_c is None:                      # 마지막 수단: 숫자 규모가 가장 큰 수치 컬럼
        num = {}
        for c in d.columns:
            v = pd.to_numeric(d[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if v.notna().mean() > 0.7:
                num[c] = float(v.abs().median() or 0)
        if not num:
            return None
        val_c = max(num, key=num.get)
    out = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "date": dt,
        "credit_bal": pd.to_numeric(d[val_c].astype(str).str.replace(",", "", regex=False),
                                    errors="coerce"),
        "src": "krx_marketplace",
    }).dropna(subset=["code", "credit_bal"])
    return out if len(out) > 50 else None


def _probe_credit_bld(probe_date: pd.Timestamp) -> Optional[str]:
    """어떤 bld 가 살아 있는지 실제로 한 번 때려서 확인한다. 결과는 로그에 남는다."""
    cands = [KRX_CREDIT_BLD] if KRX_CREDIT_BLD else KRX_CREDIT_BLD_CANDIDATES
    for bld in cands:
        js = KRX.json_data(bld, trdDd=probe_date.strftime("%Y%m%d"), mktId="ALL",
                           strtDd=probe_date.strftime("%Y%m%d"), endDd=probe_date.strftime("%Y%m%d"))
        got = _parse_krx_credit_json(js, probe_date)
        if got is not None:
            LOG.ok(f"KRX 신용잔고 bld 확인: {bld} (표본 {len(got):,}종목)")
            return bld
    return None


def _load_manual_credit() -> pd.DataFrame:
    """사용자가 KRX 웹에서 직접 받아 드라이브에 넣어둔 CSV/XLSX 를 흡수한다.
    ★ 원본 파일은 읽기만 하고 옮기거나 지우지 않는다(절대 1원칙)."""
    rows = []
    seen = set()
    for d in CREDIT_MANUAL_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".csv", ".xlsx", ".xls")):
                    continue
                p = os.path.join(root, fn)
                if p in seen:
                    continue
                seen.add(p)
                try:
                    if fn.lower().endswith(".csv"):
                        try:
                            t = pd.read_csv(p, encoding="utf-8-sig")
                        except Exception:
                            t = pd.read_csv(p, encoding="cp949")
                    else:
                        t = pd.read_excel(p)
                except Exception as e:                                  # noqa
                    LOG.warn(f"수동 신용잔고 파일 파싱 실패({type(e).__name__}): {fn}")
                    continue
                cmap = {str(c).strip(): c for c in t.columns}
                code_c = next((cmap[k] for k in cmap if k in ("종목코드", "단축코드", "code", "티커")), None)
                date_c = next((cmap[k] for k in cmap if k in ("일자", "날짜", "date", "기준일")), None)
                val_c = next((cmap[k] for k in cmap
                              if any(x in k for x in ("융자잔고", "신용잔고", "잔고금액"))), None)
                if not (code_c and date_c and val_c):
                    LOG.warn(f"수동 신용잔고 파일의 컬럼을 인식하지 못했습니다: {fn} → {list(t.columns)[:8]}")
                    continue
                rows.append(pd.DataFrame({
                    "code": t[code_c].map(to_code6),
                    "date": as_ts_series(t[date_c]),
                    "credit_bal": pd.to_numeric(
                        t[val_c].astype(str).str.replace(",", "", regex=False), errors="coerce"),
                    "src": "manual_csv"}))
                VAULT.adopt(p, domain="credit", subtype="manual_csv", key=fn,
                            source="user manual download", scope="shared")
    if not rows:
        return pd.DataFrame(columns=CREDIT_COLS)
    M = pd.concat(rows, ignore_index=True).dropna(subset=["code", "date", "credit_bal"])
    LOG.ok(f"수동 신용잔고 파일에서 {len(M):,}행 흡수 ({M['code'].nunique():,}종목, "
           f"{M['date'].min():%Y-%m-%d}~{M['date'].max():%Y-%m-%d})")
    return M


def credit_grade_of(C: pd.DataFrame, min_codes: int = 100) -> Tuple[str, float]:
    """등급은 '자칭'이 아니라 관측 간격의 실측 중앙값으로 판정한다.
    (수집 부작용 없이 단독 검증이 가능하도록 순수함수로 분리 — 리허설에서 그대로 호출한다)"""
    if C is None or not len(C) or C["code"].nunique() < min_codes:
        return "NONE", np.nan
    gap = C.sort_values("date").groupby("code")["date"].diff().dt.days.dropna()
    med = float(gap.median()) if len(gap) else 99.0
    return ("PRIMARY_DAILY" if med <= 2.0 else "FALLBACK_A_WEEKLY"), med


def fetch_credit_balance(px: pd.DataFrame, flows: pd.DataFrame,
                         start: str, end: str) -> pd.DataFrame:
    """§5.2 — 신용융자잔고. 등급을 정직하게 확정하고 전역 CREDIT_GRADE 에 남긴다."""
    global CREDIT_GRADE, CREDIT_SOURCE_NOTE
    cal = _trading_calendar(px)
    frames = []

    cached = VAULT.get_table("krx_credit_balance_daily", scope="shared")
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        if "src" not in cached.columns:
            cached["src"] = "cache"
        frames.append(cached.dropna(subset=["code", "date"])[CREDIT_COLS])
        LOG.info(f"공용 캐시에서 신용잔고 {len(cached):,}행 재사용")

    manual = _load_manual_credit()
    if len(manual):
        frames.append(manual[CREDIT_COLS])

    # ── Primary: KRX 마켓플레이스 일자별 전종목 조회 ──────────────────────────────────────
    new_rows = []
    if not krx_allowed():
        LOG.warn("KRX 가 차단/비활성이라 신용융자잔고 '직접 수집'은 불가능합니다. "
                 "이 데이터는 KRX 정보데이터시스템 독점이라 대체 공개 소스가 없습니다. "
                 "→ ① 드라이브 캐시 ② 수동 CSV ③ 프록시(Fallback B) 순으로 진행합니다.")
    if RUN_MODE != "CACHED" and len(cal) and krx_allowed():
        have_dates = set()
        if frames:
            hd = pd.concat(frames, ignore_index=True)["date"]
            have_dates = set(pd.to_datetime(hd).dt.strftime("%Y%m%d"))
        want = [pd.Timestamp(d) for d in cal
                if as_ts(start) <= pd.Timestamp(d) <= as_ts(end)]
        todo = [d for d in want if d.strftime("%Y%m%d") not in have_dates]
        if todo and KRX.session_ok:
            bld = _probe_credit_bld(todo[max(0, len(todo) - 1)])
            if bld:
                # 일별 전량이 예산을 넘으면 주간으로 낮춘다 — 조용히가 아니라 명시적으로.
                budget = 2600
                grid = todo
                if len(todo) > budget:
                    grid = [d for d in todo if d.weekday() == 4] or todo[::5]
                    LOG.warn(f"신용잔고 수집 대상 {len(todo):,}일이 호출예산({budget})을 초과합니다 → "
                             f"주간(금요일) 격자 {len(grid):,}일로 낮춥니다. "
                             f"이는 Fallback A(주간 해상도)와 동등합니다.")
                fail = 0
                for d in tqdm(grid, desc="KRX 신용잔고", ncols=88, leave=False):
                    js = KRX.json_data(bld, trdDd=d.strftime("%Y%m%d"), mktId="ALL",
                                       strtDd=d.strftime("%Y%m%d"), endDd=d.strftime("%Y%m%d"))
                    got = _parse_krx_credit_json(js, d)
                    if got is None:
                        fail += 1
                        if fail >= 15:
                            LOG.warn("신용잔고 조회가 연속 15회 실패 — 세션 만료/차단으로 판단하고 중단합니다. "
                                     "받은 분량은 그대로 캐시에 남습니다(재실행 시 이어받음).")
                            break
                        continue
                    fail = 0
                    new_rows.append(got)
            else:
                LOG.warn("KRX 신용잔고 bld 후보를 모두 시도했으나 유효 응답이 없습니다. "
                         "화면 개편으로 ID가 바뀌었을 수 있습니다 → KRX_CREDIT_BLD 에 직접 지정하거나, "
                         "CSV를 내려받아 CREDIT_MANUAL_DIRS 에 넣어 주세요.")
        elif todo and not KRX.session_ok:
            LOG.warn("KRX 마켓플레이스 세션이 없어 신용잔고 직접 수집을 시도하지 않습니다 "
                     "(상단 ①에 ID/PW 입력). 폴백 경로로 진행합니다.")
    if new_rows:
        frames.append(pd.concat(new_rows, ignore_index=True)[CREDIT_COLS])

    C = (pd.concat(frames, ignore_index=True) if frames
         else pd.DataFrame(columns=CREDIT_COLS))
    if len(C):
        C["date"] = as_ts_series(C["date"])
        C = (C.dropna(subset=["code", "date", "credit_bal"])
               .drop_duplicates(["code", "date"], keep="last")
               .sort_values(["code", "date"]))

    # ── 등급 판정 ────────────────────────────────────────────────────────────────────────
    grade, med_gap = credit_grade_of(C)
    if grade != "NONE":
        CREDIT_GRADE = grade
        if CREDIT_GRADE == "FALLBACK_A_WEEKLY" and not CREDIT_ALLOW_FALLBACK_A:
            LOG.warn("주간 해상도 신용잔고만 확보됐지만 CREDIT_ALLOW_FALLBACK_A=False 입니다 — "
                     "그래도 프록시(B)보다는 우월하므로 A로 진행하되 이 사실을 남깁니다.")
        CREDIT_SOURCE_NOTE = (f"관측간격 중앙값 {med_gap:.1f}일 · {C['code'].nunique():,}종목 · "
                              f"{len(C):,}행 · 소스={'/'.join(sorted(set(C['src'].astype(str))))[:40]}")
        if new_rows:
            VAULT.put_table("krx_credit_balance_daily", C, scope="shared", domain="credit",
                            source="KRX marketplace / manual",
                            extra={"note": "종목별 신용융자잔고 — 전 전략 공용"})
            PIPE.io("OUT", "DRIVE", "krx_credit_balance_daily", C, source="KRX")
    else:
        # ── Fallback B: 프록시 ───────────────────────────────────────────────────────────
        if not CREDIT_ALLOW_FALLBACK_B:
            CREDIT_GRADE = "NONE"
            CREDIT_SOURCE_NOTE = "신용잔고 직접 관측 실패 · Fallback B 비허용 설정"
            LOG.error("신용잔고를 확보하지 못했고 CREDIT_ALLOW_FALLBACK_B=False 입니다 → "
                      "이 전략의 핵심 축이 없는 상태로는 진행하지 않습니다.")
            return pd.DataFrame(columns=CREDIT_COLS)
        if flows is None or not len(flows) or flows["retail_net"].notna().sum() == 0:
            CREDIT_GRADE = "NONE"
            CREDIT_SOURCE_NOTE = "신용잔고·개인수급 모두 부재"
            LOG.error("신용잔고도, 프록시의 재료인 개인 순매수도 없습니다. f_cr 계열 전부 결측입니다.")
            return pd.DataFrame(columns=CREDIT_COLS)
        CREDIT_GRADE = "FALLBACK_B_PROXY"
        if FLOW_APPROX:
            LOG.error("★★ 이중 퇴화 경고: 신용잔고가 프록시(개인 순매수 누적)인데 그 '개인'조차 "
                      "-(기관+외국인) 근사입니다. 그러면 f_cr · f_ret_ex · f_inst 가 사실상 "
                      "같은 시계열(기관+외국인 순매수)의 변형이 되고, TP_F2(개인이탈×기관유입)는 "
                      "자기 자신과의 곱으로 퇴화합니다 — 신호처럼 보이지만 아무 정보가 없습니다. "
                      "해당 TP 를 산식에서 제외하고 그 사실을 리포트에 남깁니다.")
        LOG.warn("★ 신용잔고를 직접 얻는 방법(권장, 5분): data.krx.co.kr 접속 → [통계] → "
                 "[시장정보] → '신용거래융자 잔고' 화면에서 기간을 지정해 CSV/XLSX 를 내려받아 "
                 f"{CREDIT_MANUAL_DIRS[0]} 폴더에 넣어두세요. 다음 실행에서 자동 인식되어 "
                 "PRIMARY 등급으로 승격되고, 공용 인덱스에 정규화 적재됩니다. "
                 "(파일에 '일자'·'종목코드'·'융자잔고금액' 컬럼만 있으면 됩니다)")
        f = flows.sort_values(["code", "date"]).copy()
        f["credit_bal"] = (f.groupby("code", observed=True)["retail_net"]
                            .transform(lambda s: s.rolling(252, min_periods=60).sum()))
        C = f.loc[f["credit_bal"].notna(), ["code", "date", "credit_bal"]].copy()
        C["src"] = "proxy_retail_cum252"
        CREDIT_SOURCE_NOTE = ("개인 순매수 252일 누적 (신용잔고 직접 관측 불가) — "
                              "대체재가 아니라 열등재입니다")
        LOG.error("★ 신용잔고를 Fallback B(프록시)로 대체합니다. §11-3에 따라 이 사실을 "
                  "리포트 첫 줄에 명시하고, R2-F 결과의 신뢰도를 하향 표기합니다. "
                  "숨기지 않습니다.")

    LOG.ok(f"신용잔고 등급 = {CREDIT_GRADE} · {CREDIT_SOURCE_NOTE}")
    return downcast(C) if len(C) else C


# ═══ 관리종목 · 거래정지 (방화벽 입력, K6) ═══════════════════════════════════════════════════
def fetch_watchlist_halt(sec: pd.DataFrame) -> pd.DataFrame:
    """관리종목·투자주의환기·거래정지 이력. 이력(지정/해제일)이 이상적이지만 공개 경로는
    대개 '현재 상태' 스냅샷이다. 스냅샷만 얻으면 PIT 로 쓸 수 없으므로,
    ★ 과거 구간에는 적용하지 않고 '현재 시점 이후'로만 제한한다(미래정보 차단).
    """
    global WATCH_GRADE
    cols = ["code", "flag", "from_date", "to_date", "observed_at", "src"]
    cached = VAULT.get_table("krx_watchlist_events", scope="shared")
    if cached is not None and len(cached):
        WATCH_GRADE = "OK"
        if "observed_at" not in cached.columns:
            cached["observed_at"] = pd.NaT
        cached["from_date"] = as_ts_series(cached["from_date"])
        cached["to_date"] = as_ts_series(cached["to_date"])
        cached["observed_at"] = as_ts_series(cached["observed_at"])
        LOG.info(f"공용 캐시에서 관리종목/거래정지 이력 {len(cached):,}행 재사용 "
                 f"(관측시점 최소 {str(cached['observed_at'].min())[:10]})")
        return cached.reindex(columns=cols)

    rows = []
    if RUN_MODE != "CACHED":
        # KIND 공시 기반: 관리종목 지정/해제, 매매거래정지/해제는 '공시'로 남는다.
        for flag, url in (
            ("admin", "https://kind.krx.co.kr/investwarn/adminissue.do?method=searchAdminIssueMain"),
            ("halt", "https://kind.krx.co.kr/investwarn/tradinghaltissue.do?method=searchTradingHaltIssueMain"),
            ("alert", "https://kind.krx.co.kr/investwarn/investattentigender.do?method=searchInvestAttentiMain"),
        ):
            html = http_get(url, source="kind", tries=2,
                            referer="https://kind.krx.co.kr/investwarn/adminissue.do")
            if not html:
                continue
            try:
                tabs = pd.read_html(io.StringIO(html))
            except Exception:
                tabs = []
            if not tabs:
                continue
            t = max(tabs, key=len)
            cmap = {str(c).strip(): c for c in t.columns}
            code_c = next((cmap[k] for k in cmap if "종목코드" in k or "코드" == k), None)
            name_c = next((cmap[k] for k in cmap if "회사명" in k or "종목명" in k), None)
            date_c = next((cmap[k] for k in cmap if "지정일" in k or "일자" in k or "정지일" in k), None)
            if code_c is None and name_c is not None and sec is not None and len(sec):
                n2c = {str(n).strip(): c for c, n in zip(sec["code"], sec["name"]) if isinstance(n, str)}
                codes = t[name_c].astype(str).str.strip().map(n2c)
            elif code_c is not None:
                codes = t[code_c].map(to_code6)
            else:
                continue
            rows.append(pd.DataFrame({
                "code": codes,
                "flag": flag,
                "from_date": as_ts_series(t[date_c]) if date_c else pd.NaT,
                "to_date": pd.NaT,
                "observed_at": pd.Timestamp.today().normalize(),
                "src": "kind"}).dropna(subset=["code"]))

    if not rows:
        WATCH_GRADE = "NONE"
        LOG.warn("관리종목·거래정지 이력을 확보하지 못했습니다(K6 FAIL) → 방화벽의 해당 조항만 "
                 "비활성화하고 그 사실을 방화벽 감사표에 남깁니다. "
                 "다른 조항(자본잠식·영업CF·유동성)은 그대로 작동합니다.")
        return pd.DataFrame(columns=cols)

    W = pd.concat(rows, ignore_index=True).drop_duplicates(["code", "flag", "from_date"])
    # ★ 이 목록은 '현재 지정 중'인 종목만 담긴 스냅샷이다. 지정일이 2019년이어도,
    #   2026년에 관측했다는 사실 자체가 "2026년까지 해제되지 않았다"는 미래정보다.
    #   과거로 소급 적용하면 '끝내 회복하지 못한 종목'만 골라 차단하게 되어 성과가 부풀려진다.
    #   → 적용 시작일 = max(지정일, 관측일). 즉 과거 구간에는 적용하지 않는다.
    #   실행할 때마다 스냅샷이 누적되므로, 앞으로의 구간에서는 진짜 PIT 이력이 쌓인다.
    W["observed_at"] = as_ts_series(W["observed_at"]).fillna(pd.Timestamp.today().normalize())
    W["from_date"] = as_ts_series(W["from_date"])
    W["from_date"] = W[["from_date", "observed_at"]].max(axis=1)
    W["from_date"] = W["from_date"].fillna(W["observed_at"])
    WATCH_GRADE = "SNAPSHOT_FORWARD_ONLY"
    LOG.warn("관리종목/거래정지는 '현재 지정 중' 스냅샷이라 과거 구간에 소급 적용하지 않습니다"
             "(소급하면 '끝내 회복 못한 종목만 차단'하는 미래정보가 됩니다). "
             "따라서 백테스트 구간에서 이 방화벽 조항은 사실상 비활성이며, "
             "그 사실을 방화벽 감사표와 등급 카드에 그대로 남깁니다.")
    VAULT.put_table("krx_watchlist_events", W, scope="shared", domain="universe",
                    source="KIND", extra={"note": "관리종목/거래정지/투자주의 — 전 전략 공용"})
    LOG.ok(f"관리종목·거래정지 {len(W):,}행 ({W['code'].nunique():,}종목)")
    return W.reindex(columns=cols)
