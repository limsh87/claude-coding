

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 메타데이터 수집 — 한경컨센서스 + 네이버금융리서치                  ║
# ║                                                                                          ║
# ║  ★ 이 전략은 리포트의 **내용을 전혀 읽지 않는다.** 필요한 것은 (analyst, ticker, date)      ║
# ║    메타데이터뿐이다. 목표주가·투자의견도 신호에 쓰지 않는다(§0 — 검열 내성).                 ║
# ║    목표주가는 오직 H5 선행성 검정의 '컨센서스 개정 대리변수'로만 쓴다.                      ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : **작성자(애널리스트)를 리스트에서 바로 준다.**       ║
# ║      이 전략의 생명줄. 단, 종목코드가 없어 제목의 "종목명(005930)" 에서 뽑아야 한다.        ║
# ║    · 네이버금융리서치 : 종목코드를 확실히 준다. 커버리지가 넓다. 작성자는 리스트에 없다.    ║
# ║                                                                                          ║
# ║  ★ N(a,t) 은 '그 달 발간한 **총** 리포트 수'다(§6.1). 그래서 기업분석뿐 아니라              ║
# ║    산업분석까지 받아야 한다. 산업리포트를 많이 쓴 애널리스트는 개별 종목 share 가 낮아지는  ║
# ║    것이 맞다 — 주의 예산은 하나이기 때문이다. 이걸 빼면 분모가 과소집계된다.                ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자의 명시적 지시에 따라 수집하되        ║
# ║    보수적 속도로 제한하고 그 사실을 로그에 명시한다. 수집된 메타데이터는 로컬 분석          ║
# ║    용도로만 사용할 것.                                                                    ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다.                                                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = ["report_uid", "source", "src_report_id", "pub_date", "category",
               "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
               "analyst_raw", "target_price", "opinion", "detail_url",
               "event_date", "knowledge_date"]

# 한경 report_type — 기업(CO)과 산업(IN)을 모두 받아야 N(a,t) 분모가 정확해진다.
HK_TYPES = [("business", "CO", "기업"), ("business", "IN", "산업")]
# 네이버 카테고리 — 동일 취지
NV_CATS = {"company": "company_list.naver", "industry": "industry_list.naver"}

_OPINION_MAP = {
    "매수": "BUY", "buy": "BUY", "strongbuy": "BUY", "적극매수": "BUY", "outperform": "BUY",
    "비중확대": "BUY", "overweight": "BUY", "trading buy": "BUY", "tradingbuy": "BUY",
    "중립": "HOLD", "hold": "HOLD", "neutral": "HOLD", "marketperform": "HOLD",
    "시장수익률": "HOLD", "보유": "HOLD", "비중유지": "HOLD",
    "매도": "SELL", "sell": "SELL", "underperform": "SELL", "비중축소": "SELL",
    "underweight": "SELL", "reduce": "SELL",
}
_NULL_TOKENS = {"", "-", "--", "0", "n/a", "na", "없음", "투자의견없음", "nr", "not rated", "제시안함"}


def _clean_cell(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABCABC' 처럼 2~3회 반복되어 나오는 알려진 버그를 되돌린다."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0 and s[: n // k] * k == s:
            return s[: n // k]
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 H5 의 컨센서스 개정 대리변수가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    return v if 0 < v <= 5e7 else None


def parse_opinion(x: Any) -> Optional[str]:
    t = _clean_cell(x)
    if t.lower() in _NULL_TOKENS:
        return None
    k = re.sub(r"[^\w가-힣]", "", t).lower()
    for pat, val in _OPINION_MAP.items():
        if re.sub(r"[^\w가-힣]", "", pat).lower() in k:
            return val
    return t[:20] or None


_YYMMDD = re.compile(r"^\s*(\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*$")


def parse_kr_date(s: Any) -> Optional[str]:
    """★ 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    이 전략은 **월 단위 주의 배분**이 신호이므로 날짜가 어긋나면 신호 자체가 무의미해진다."""
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6}|[0-9]{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return to_code6(m.group(1)) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


def _table_headers(table) -> List[str]:
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            return [_clean_cell(th.get_text()) for th in ths]
    return []


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    return {headers[i]: tds[i] for i in range(len(tds))} if headers and len(headers) == len(tds) else {}


def _pick(rowmap: Dict[str, Any], *names) -> Optional[Any]:
    for n in names:
        for k, v in rowmap.items():
            if n in k:
                return v
    return None


# ── 한경컨센서스 ────────────────────────────────────────────────────────────────────────────
_HK_LAYOUT_LOGGED = set()


def _hk_parse(html: str, category: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = None
    for sel in ("div.table_style01 table", "#contents table", "table"):
        t = soup.select_one(sel)
        if t is not None and t.find("tr") is not None:
            table = t
            break
    if table is None or soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃: {len(headers)}컬럼 {headers}")
        if headers and not any("작성자" in h or "애널" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 작성자 컬럼이 없습니다. skinType 파라미터가 무시된 "
                     f"것 같습니다(통합 탭 레이아웃). ★ 이 전략은 작성자가 생명줄이므로 "
                     f"이 상태면 애널리스트 단위 신호를 만들 수 없습니다 — Phase 0 게이트에서 "
                     f"하우스 단위 폴백으로 자동 격하됩니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        ridx = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                break
        if ridx is None:
            continue

        date_s = _pick(rm, "작성일", "날짜")
        if not date_s:
            date_s = next((t for t in texts if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
        title = _pick(rm, "제목")
        if not title:
            a = tr.find("a", href=re.compile("report_idx"))
            title = _clean_cell(a.get_text(" ")) if a else ""
        title = _dedup_repeat(title)

        tp = _pick(rm, "적정가격", "목표주가", "적정주가")
        op = _pick(rm, "투자의견", "의견")
        an = _pick(rm, "작성자", "애널리스트")
        bk = _pick(rm, "제공출처", "증권사", "출처")

        if not (headers and len(headers) == len(texts)):
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c != (op or "")]
            if bk is None:
                bk = next((c for c in cand if "증권" in c or "투자" in c or "금융" in c), None)
            if an is None:
                an = next((c for c in cand if c != bk and 1 <= len(c) <= 30), None)

        out.append({
            "source": "hankyung", "src_report_id": str(ridx), "category": category,
            "pub_date": parse_kr_date(date_s), "title": title,
            "stock_code": code_from_title(title), "stock_name": name_from_title(title),
            "broker_raw": _clean_cell(bk), "analyst_raw": _clean_cell(an),
            "target_price": parse_target_price(tp), "opinion": parse_opinion(op),
            "detail_url": f"{HK_BASE}/analysis/downpdf?report_idx={ridx}",
        })
    return out


def hankyung_collect(start: str, end: str, page_size: int = 80,
                     max_pages: int = 500) -> "pd.DataFrame":
    """분기 단위로 쪼개서 수집. 한 번에 넓은 구간을 요청하면 서버 페이지 상한에 걸려
    데이터가 조용히 잘린다. 각 페이지는 HTTP 캐시에 남으므로 재실행 시 네트워크 0."""
    rows: List[dict] = []
    qs = pd.period_range(as_ts(start), as_ts(end), freq="Q")
    jobs = [(skin, rt, cat, q) for (skin, rt, cat) in HK_TYPES for q in qs]

    def _sweep(job):
        skin, rtype, cat, q = job
        sd = max(as_ts(q.start_time), as_ts(start))
        ed = min(as_ts(q.end_time), as_ts(end))
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            html = http_get(HK_LIST, source="hankyung", tries=3, referer=HK_BASE + "/", timeout=30,
                            params={"skinType": skin, "sdate": sd.strftime("%Y-%m-%d"),
                                    "edate": ed.strftime("%Y-%m-%d"), "now_page": page,
                                    "pagenum": page_size, "report_type": rtype,
                                    "order_type": "", "search_text": "", "search_value": "",
                                    "business_code": ""})
            if not html:
                break
            batch = _hk_parse(html, f"{cat}")
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            seen_ids.update(b["src_report_id"] for b in fresh)
            got.extend(fresh)
            # ★ 조기 종료를 느슨하게 잡으면 데이터가 조용히 잘려나간다. 일시적 짧은 페이지
            #   하나로 그 분기 전체가 끊길 수 있으므로 '새 항목 0건'이 2회 연속일 때만 멈춘다.
            empty_streak = empty_streak + 1 if not fresh else 0
            if empty_streak >= 2:
                break
            if page == max_pages:
                LOG.warn(f"한경 {cat} {q} 구간이 최대 페이지({max_pages})에 도달 — 데이터가 잘렸을 "
                         f"수 있습니다. 지금까지 {len(got):,}건.")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스",
                  breaker=breaker("hankyung"))
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPORT_COLS)
    n_an = int((as_str_series(d["analyst_raw"]).str.len() > 0).sum()) if len(d) else 0
    LOG.ok(f"한경컨센서스 {len(d):,}건 (작성자 보유 {n_an:,} = "
           f"{100*n_an/max(len(d),1):.1f}%)")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = (soup.select_one("#contentarea_left div.box_type_m table.type_1")
             or soup.select_one("table.type_1") or soup.select_one("table"))
    if table is None:
        return []
    headers = _table_headers(table)
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid = detail = title = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid, detail = m.group(1), urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=([0-9A-Z]{6})", a_item["href"])
            code = to_code6(mm.group(1)) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None, "detail_url": detail,
        })
    return out


def _nv_last_page(html: str) -> int:
    soup = soup_of(html)
    if soup is None:
        return 1
    mx = 1
    for a in soup.select("table.Nnavi a[href]"):
        m = re.search(r"page=(\d+)", a["href"])
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 80000) -> "pd.DataFrame":
    """신형 JSON API. 되면 HTML 페이징보다 훨씬 빠르고 구조가 안정적이다."""
    rows, index = [], 0
    url = NV_API.format(cat=cat)
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    while index < hard_cap:
        js = http_json(url, source="naver", tries=2, headers=hdr,
                       params={"index": index, "size": page_size,
                               "startDate": as_ts(start).strftime("%Y-%m-%d"),
                               "endDate": as_ts(end).strftime("%Y-%m-%d")})
        if not js:
            break
        items = js if isinstance(js, list) else (js.get("researches") or js.get("list") or
                                                 js.get("items") or js.get("content") or [])
        if not isinstance(items, list) or not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({
                "source": "naver", "category": cat,
                "src_report_id": str(it.get("id") or it.get("nid") or it.get("researchId") or ""),
                "pub_date": it.get("createDate") or it.get("date") or it.get("writeDate"),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "detail_url": None,
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    return d[as_str_series(d["src_report_id"]).str.len() > 0] if len(d) else d


def naver_collect(start: str, end: str, max_pages: int = 2000) -> "pd.DataFrame":
    frames = []
    for cat, list_page in NV_CATS.items():
        try:
            dj = naver_collect_json(cat, start, end)
        except Exception:
            dj = pd.DataFrame()
        if len(dj) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(dj):,}건")
            frames.append(dj)
            continue
        base = urljoin(NV_BASE, list_page)
        prm = {"searchType": "writeDate",
               "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
               "writeToDate": as_ts(end).strftime("%Y-%m-%d")}
        probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                         params={**prm, "page": 1})
        if not probe:
            LOG.warn(f"네이버 '{cat}' 리스트 접근 실패 — 건너뜁니다.")
            continue
        last = min(_nv_last_page(probe), max_pages)
        LOG.info(f"네이버 '{cat}' HTML 경로 — 총 {last:,}페이지")

        def _pg(p: int):
            h = probe if p == 1 else http_get(base, source="naver", referer=NV_BASE,
                                              force_enc="euc-kr", tries=3,
                                              params={**prm, "page": p})
            return _nv_parse_list(h, cat) if h else []

        res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO),
                      desc=f"네이버 {cat}", breaker=breaker("naver"))
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def collect_reports(start: str, end: str) -> "pd.DataFrame":
    """캐시 우선 수집. 이미 원장에 있는 구간은 다시 긁지 않는다."""
    frames: List["pd.DataFrame"] = []
    cached = VAULT.get_table("research_report_master", scope="shared")
    have_months: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["pub_date"] = as_ts_series(c["pub_date"])
        c = c.dropna(subset=["pub_date"])
        have_months = set(c["pub_date"].dt.strftime("%Y-%m"))
        frames.append(c)
        LOG.info(f"공용 캐시에서 리포트 원장 {len(c):,}건 / {len(have_months)}개월 재사용")

    want = set(pd.period_range(as_ts(start), as_ts(end), freq="M").astype(str))
    missing = sorted(want - have_months)
    if RUN_MODE == "CACHED" or not RESEARCH_COLLECT:
        if missing:
            LOG.warn(f"신규 수집 비활성 — 미보유 {len(missing)}개월은 결측으로 둡니다.")
        missing = []

    if missing:
        # 연속 구간으로 묶어 요청 수를 줄인다 (페이지 캐시는 어차피 남는다)
        lo, hi = as_ts(missing[0] + "-01"), as_ts(missing[-1] + "-01") + pd.offsets.MonthEnd(0)
        lo = max(lo, as_ts(start))
        hi = min(hi, as_ts(end))
        LOG.info(f"리포트 신규 수집 구간 {lo:%Y-%m} ~ {hi:%Y-%m} ({len(missing)}개월 미보유). "
                 f"※ 한경/네이버는 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 지시에 따라 "
                 f"수집하되 보수적 속도로 제한합니다.")
        if "hankyung" in RESEARCH_SOURCES:
            frames.append(hankyung_collect(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
        if "naver" in RESEARCH_SOURCES:
            frames.append(naver_collect(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.error("리포트를 한 건도 확보하지 못했습니다. 이 전략은 리포트 메타데이터가 "
                  "전부이므로 여기서 막히면 신호를 만들 수 없습니다. "
                  "RUN_MODE='SMOKE' 로 계산경로만 검증하거나, 드라이브 캐시 경로를 확인하세요.")
        return pd.DataFrame(columns=REPORT_COLS)
    cols = sorted(set().union(*[set(f.columns) for f in frames]))
    return pd.concat([f.reindex(columns=cols) for f in frames], ignore_index=True)
