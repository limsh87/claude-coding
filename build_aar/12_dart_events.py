

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 실적발표월 · 월별 공시건수  (§6.3 통제회귀의 두 입력만 받는다)                ║
# ║                                                                                          ║
# ║  ★ 이 전략은 재무제표를 받지 않는다. 필요한 것은 딱 두 가지뿐이다:                          ║
# ║      ① EarningsMonth(i,t)     — 그 달에 i의 정기보고서 접수가 있었는가                     ║
# ║      ② DisclosureCount(i,t)   — 그 달에 i의 공시가 몇 건이었는가                           ║
# ║    둘 다 **시장 전체를 날짜로 훑는** list.json 스윕으로 얻는다. 회사별 호출이 아니다.       ║
# ║                                                                                          ║
# ║  호출량 산정 (왜 한도가 문제되지 않는가):                                                   ║
# ║    120개월 × 공시유형 2종(A정기·B주요사항) × 시장 2종(유가·코스닥) = 480 스윕              ║
# ║    스윕당 평균 2~4페이지 → **총 1,000~2,000 호출**. 일일 한도의 5~10%.                     ║
# ║    게다가 한 번 받으면 공용 인덱스에 영구 저장되어 다른 전략도 그대로 재사용한다.           ║
# ║    (이전 세대가 한도를 태운 건 회사×분기 재무제표를 단건으로 받았기 때문이지,               ║
# ║     DART 자체가 부족해서가 아니다.)                                                        ║
# ║                                                                                          ║
# ║  ★ 키가 없어도 파이프라인은 돌아간다. 법정 제출기한 기반 달력 폴백이 있고,                  ║
# ║    그 사실을 통제회귀 진단표에 명시한다(조용히 넘어가지 않는다).                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}
# 정기보고서 = 실적발표. 이것이 EarningsMonth 의 정의다.
PERIODIC_PAT = re.compile(r"(사업보고서|반기보고서|분기보고서)")
DISCLOSURE_TYPES = ("A", "B")        # A=정기공시, B=주요사항보고(유증·M&A·자사주 등 강제발간 유발)
CORP_CLASSES = ("Y", "K")            # Y=유가증권, K=코스닥


def dart_api(endpoint: str, params: dict, tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계한다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다.
    → 캐시 적중이면 네트워크에 안 나가므로 예산을 아예 쓰지 않는다."""
    if not DART_API_KEY:
        return None
    q = quota("DART", key=DART_API_KEY)
    if q.exhausted:
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY

    # 캐시 우선 — 예산을 쓰기 전에 확인한다
    cached = None
    if VAULT is not None and CACHE_EVERYTHING:
        cached = VAULT.get_http(DART_BASE + endpoint, p, "dart",
                                ttl_days=_cache_ttl_for(params, "dart"))
    if cached is not None:
        try:
            js = json.loads(cached.decode("utf-8", "replace"))
        except Exception:
            js = None
        if isinstance(js, dict):
            with _HTTP_LK:
                HTTP_STATS["dart:CACHE"] += 1
            return js if str(js.get("status", "000")) == "000" else None

    if not q.take(tries):
        return None
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    q.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            q.mark_exhausted(f"status={st} ({DART_STATUS_MSG.get(st, '?')})")
        elif st in ("010", "011", "012", "901"):
            q.mark_blocked(f"status={st} ({DART_STATUS_MSG.get(st, '?')}) — DART_API_KEY 확인 필요")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def fetch_dart_corpcode() -> "pd.DataFrame":
    """corp_code ↔ 종목코드. 호출 1건. 공용 캐시라 다른 전략도 그대로 쓴다."""
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용 (호출 0건)")
        return cached
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    q = quota("DART", key=DART_API_KEY)
    if not q.take(1):
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=2)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 와 네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        if code in ("020", "021"):
            q.mark_exhausted(f"status={code}")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    txt = _decode(xml, None, "corpcode")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code"))})
    d = pd.DataFrame(rows)
    if len(d):
        VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건) — 호출 1건")
    return d


def fetch_dart_disclosures(start: str, end: str) -> "pd.DataFrame":
    """월 단위 시장 전체 공시목록 스윕. 미수집 월만 받고 공용 인덱스에 누적한다."""
    cols = ["code", "corp_code", "rcept_no", "rcept_dt", "report_nm", "is_periodic",
            "event_date", "knowledge_date"]
    cached = VAULT.get_table("dart_disclosures_slim", scope="shared")
    have_months: set = set()
    frames: List["pd.DataFrame"] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.strftime("%Y-%m"))
        frames.append(cached)
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}건 / {len(have_months)}개월 재사용 (호출 0건)")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED" or not DART_API_KEY:
        if todo and not DART_API_KEY:
            LOG.warn(f"DART_API_KEY 미입력 — 공시 {len(todo)}개월을 수집하지 않습니다. "
                     f"§6.3 통제회귀는 EarningsMonth 를 법정 제출기한 달력으로 대체하고 "
                     f"DisclosureCount 는 제외합니다. 그 사실이 통제 진단표에 표시됩니다.")
        todo = []

    if todo:
        q = quota("DART", key=DART_API_KEY)
        est = len(todo) * len(DISCLOSURE_TYPES) * len(CORP_CLASSES) * 3
        LOG.info(f"DART 공시 스윕 {len(todo)}개월 × 유형 {len(DISCLOSURE_TYPES)} × 시장 "
                 f"{len(CORP_CLASSES)} — 예상 호출 약 {est:,}건. {q.status_line()}")

        def _one(m):
            rows = []
            for ty in DISCLOSURE_TYPES:
                for cc in CORP_CLASSES:
                    page = 1
                    while page <= 100:
                        js = dart_api("list.json", {
                            "bgn_de": m.start_time.strftime("%Y%m%d"),
                            "end_de": m.end_time.strftime("%Y%m%d"),
                            "pblntf_ty": ty, "corp_cls": cc,
                            "page_no": page, "page_count": 100, "last_reprt_at": "N"})
                        if not js or not isinstance(js.get("list"), list) or not js["list"]:
                            break
                        rows.extend(js["list"])
                        if page >= int(js.get("total_page", 1) or 1):
                            break
                        page += 1
            return rows

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 6), desc="DART 공시 스윕")
        new = [r for chunk in res if chunk for r in chunk]
        if new:
            d = pd.DataFrame(new)
            keep = [c for c in ("corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm")
                    if c in d.columns]
            d = d[keep].copy()
            d["code"] = d["stock_code"].map(to_code6) if "stock_code" in d.columns else None
            d["rcept_dt"] = as_ts_series(d["rcept_dt"])
            d["report_nm"] = as_str_series(d["report_nm"])
            d["is_periodic"] = d["report_nm"].str.contains(PERIODIC_PAT, na=False)
            frames.append(d)
            LOG.ok(f"공시 신규 {len(d):,}건 (정기보고서 {int(d['is_periodic'].sum()):,}건). "
                   f"{quota('DART', key=DART_API_KEY).status_line()}")

    if not frames:
        return pd.DataFrame(columns=cols)
    D = pd.concat(frames, ignore_index=True)
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"]).drop_duplicates("rcept_no", keep="last")
    if "is_periodic" not in D.columns:
        D["is_periodic"] = as_str_series(D.get("report_nm", "")).str.contains(PERIODIC_PAT, na=False)
    if "code" not in D.columns:
        D["code"] = None
    D["code"] = D["code"].map(to_code6)
    if len(frames) > 1 or (cached is None or not len(cached)):
        VAULT.put_table("dart_disclosures_slim",
                        D[["code", "corp_code", "rcept_no", "rcept_dt", "report_nm", "is_periodic"]],
                        scope="shared", domain="dart", source="opendart list.json (slim sweep)")
    # 접수일 = 공개일 (PIT)
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")
    LOG.ok(f"공시목록 총 {len(D):,}건 · 종목코드 보유 {int(D['code'].notna().sum()):,}건 · "
           f"정기보고서 {int(D['is_periodic'].sum()):,}건")
    PIPE.io("OUT", "DRIVE", "dart_disclosures_slim", D, source="opendart")
    return D


# ── 통제변수 패널 ───────────────────────────────────────────────────────────────────────────
#   법정 제출기한 (자본시장법 §159·§160) — DART 키가 없을 때의 달력 폴백.
#   12월 결산 법인 기준: Q1→5월, 반기→8월, Q3→11월, 사업보고서→3월.
#   출처: 자본시장과 금융투자업에 관한 법률 시행령 제168조 (분기 45일 / 사업 90일)
EARNINGS_MONTHS_FALLBACK = (3, 5, 8, 11)


def build_control_panel(months: "pd.DatetimeIndex", disclosures: "pd.DataFrame",
                        codes: Sequence[str]) -> Tuple["pd.DataFrame", dict]:
    """종목×월 통제변수 패널 (EarningsMonth, DisclosureCount).

    반환 (패널, 메타). 메타에는 각 통제변수가 '실측'인지 '달력 폴백'인지가 들어가고,
    그것이 통제 진단표에 그대로 출력된다 — 통제가 약해진 것을 조용히 넘기지 않는다."""
    meta = {"earnings_source": "달력 폴백(법정 제출기한)", "disclosure_source": "없음",
            "n_periodic": 0, "n_disclosure": 0}
    idx = pd.MultiIndex.from_product([sorted(set(codes)), list(months)], names=["code", "month"])
    P = pd.DataFrame(index=idx).reset_index()
    P["earnings_month"] = 0.0
    P["disclosure_n"] = np.nan

    if disclosures is not None and len(disclosures) and disclosures["code"].notna().any():
        d = disclosures.dropna(subset=["code"]).copy()
        d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
        d["code"] = as_str_series(d["code"])
        cnt = (d.groupby(["code", "month"], observed=True)
                .agg(disclosure_n=("rcept_no", "nunique"),
                     earn=("is_periodic", "max")).reset_index())
        P = P.merge(cnt, on=["code", "month"], how="left")
        P["earnings_month"] = pd.to_numeric(P["earn"], errors="coerce").fillna(0.0)
        P["disclosure_n"] = pd.to_numeric(P["disclosure_n"], errors="coerce").fillna(0.0)
        P = P.drop(columns=["earn"])
        meta.update(earnings_source="DART 정기보고서 접수일(실측)",
                    disclosure_source="DART 공시 스윕(실측, 유형 A+B)",
                    n_periodic=int(cnt["earn"].sum()), n_disclosure=int(cnt["disclosure_n"].sum()))
    else:
        P["earnings_month"] = P["month"].dt.month.isin(EARNINGS_MONTHS_FALLBACK).astype(float)
        LOG.warn("실적발표월을 **법정 제출기한 달력**으로 대체합니다(3·5·8·11월). "
                 "12월 결산이 아닌 법인에서는 부정확하며, 그만큼 §6.3 통제가 약해집니다. "
                 "DART_API_KEY 를 넣으면 실측 접수일로 자동 대체됩니다.")
    P["disclosure_n"] = P["disclosure_n"].fillna(0.0)
    P["log_disclosure"] = np.log1p(P["disclosure_n"])
    return downcast(P), meta
