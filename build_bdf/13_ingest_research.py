

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 수집 — 한경컨센서스 + 네이버금융리서치                            ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : 작성자(애널리스트)·적정가격·투자의견을 리스트에서    ║
# ║      바로 준다. 1요청에 최대 수백 행 → 애널리스트 원장의 1순위 소스.                       ║
# ║      단, 종목코드가 컬럼에 없다. 제목의 "종목명(005930)" 에서 뽑아야 한다.                 ║
# ║    · 네이버금융리서치 : 종목코드를 td[0] a.stock_item href 에 확실히 준다.                 ║
# ║      애널리스트명은 리스트에 없다(PDF/상세에 있음). 커버리지 폭이 넓다.                    ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자가 명시적으로 수집을 지시했으므로     ║
# ║    수행하되, 초당 요청을 보수적으로 제한하고(RATE_LIMIT_QPS) 이 사실을 로그에 명시한다.     ║
# ║  ⚠ PDF 원문은 증권사 저작물이다. 로컬 캐시/분석 용도로만 쓰고 재배포하지 말 것.             ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다. (공개 스크래퍼들의 컬럼 인덱스가 서로 모순되기 때문)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
HK_PDF = HK_BASE + "/analysis/downpdf?report_idx={idx}"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = [
    "report_uid", "source", "src_report_id", "pub_date", "category",
    "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
    "analyst_raw", "target_price", "opinion", "pdf_url", "pdf_uid", "detail_url",
    "views", "event_date", "knowledge_date",
]

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


_REPEAT_RE = re.compile(r"^(.{4,}?)(?:\s*\1)+$")


def _dedup_repeat(s: str) -> str:
    """제목이 'ABCABC' / 'ABC ABC' 처럼 반복되어 나오는 알려진 버그를 되돌린다.

    ★ 호출부가 td.get_text(" ") 로 셀을 뽑기 때문에 반복 사이에 공백이 낀다.
      '구분자 없는 정확 반복' 만 보던 옛 구현은 그걸 못 잡았고, 그 결과 stock_name 과
      dedup_key 가 함께 오염됐다. 정규식 폭주를 막으려 최소 단위 길이를 4로 둔다."""
    s = _clean_cell(s)
    if len(s) < 8:
        return s
    m = _REPEAT_RE.match(s)
    if m:
        return _clean_cell(m.group(1))
    n = len(s)
    for k in (2, 3):
        if n % k == 0 and s[: n // k] * k == s:
            return s[: n // k]
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 목표주가 리비전 팩터가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    if v <= 0 or v > 5e7:
        return None
    return v


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
    """★ 네이버 리스트의 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    → 두 자리 연도는 여기서 4자리로 확정한 뒤에만 하위로 넘긴다.
    """
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        # 백테스트 대상은 2000년대. 두 자리 연도는 2000+yy 로 확정한다.
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        try:
            return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
        except Exception:
            return None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6})\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return m.group(1) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


# ── 헤더 기반 테이블 파서 (컬럼 인덱스 불신 원칙) ────────────────────────────────────────────
def _table_headers(table) -> List[str]:
    hdr = []
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            hdr = [_clean_cell(th.get_text()) for th in ths]
            break
    return hdr


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    if headers and len(headers) == len(tds):
        return {headers[i]: tds[i] for i in range(len(tds))}
    return {}


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
    if table is None:
        return []
    if soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃 감지: {len(headers)}컬럼 {headers}")
        if headers and not any("적정" in h or "목표" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 적정가격 컬럼이 없습니다. "
                     f"skinType 파라미터가 무시된 것 같습니다(통합 탭 6컬럼 레이아웃). "
                     f"목표주가·투자의견은 이 카테고리에서 수집되지 않습니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        # report_idx 는 어느 열에 있든 앵커에서 찾는다 (인덱스 의존 제거)
        ridx, pdf = None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                pdf = HK_PDF.format(idx=ridx)
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

        if headers and len(headers) == len(texts):
            pass                                     # 헤더 매핑 성공 — 그대로 사용
        else:
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c not in (op or "",)]
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
            "pdf_url": pdf, "detail_url": pdf, "views": None,
        })
    return out


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다."""
    rows: List[dict] = []
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    jobs = []
    for skin in skins:
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            jobs.append((skin, sd, ed))

    def _sweep(job):
        skin, sd, ed = job
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        fail_streak = 0
        cut_pages: List[int] = []
        for page in range(1, max_pages + 1):
            params = {
                "skinType": skin, "sdate": sd.strftime("%Y-%m-%d"), "edate": ed.strftime("%Y-%m-%d"),
                "now_page": page, "pagenum": page_size, "order_type": "",
                "report_type": "CO" if skin == "business" else "",
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            batch = _hk_parse(html, skin) if html else None
            # ★ 여기서 곧바로 break 하면 일시적 5xx/타임아웃 한 번에 그 해 남은 페이지가
            #   통째로 사라진다(전체의 10%). 3회 연속 실패일 때만 중단하고, 잘린 지점을 남긴다.
            if not html or not batch:
                fail_streak += 1
                cut_pages.append(page)
                if fail_streak >= 3:
                    LOG.error(f"한경 {skin} {sd:%Y} 구간이 page {page} 에서 3회 연속 실패로 "
                              f"잘렸습니다 (지금까지 {len(got):,}건). 재실행하면 캐시 위에 "
                              f"이어서 채웁니다.")
                    break
                continue
            fail_streak = 0
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            for b in fresh:
                seen_ids.add(b["src_report_id"])
            got.extend(fresh)
            # ★ 조기 종료 조건을 느슨하게 잡으면 데이터가 조용히 잘려나간다.
            #   파싱 실패나 일시적 짧은 페이지 하나로 그 해 전체 수집이 끊길 수 있으므로,
            #   '새 항목 0건'이 2회 연속일 때만 멈춘다.
            if len(fresh) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
            if page == max_pages:
                LOG.warn(f"한경 {skin} {sd:%Y} 구간이 최대 페이지({max_pages})에 도달했습니다 — "
                         f"데이터가 잘렸을 수 있습니다. max_pages 를 늘리거나 구간을 분기 단위로 "
                         f"쪼개세요. (지금까지 {len(got):,}건)")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스")
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows, columns=[c for c in REPORT_COLS if c in (rows[0].keys() if rows else [])]) \
        if rows else pd.DataFrame(columns=REPORT_COLS)
    if rows:
        d = pd.DataFrame(rows)
    LOG.ok(f"한경컨센서스 {len(d):,}건 "
           f"(작성자 보유 {int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} / "
           f"목표주가 보유 {int(d['target_price'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
NV_CATS = {
    "company": ("company_list.naver", "company_read.naver"),
    "industry": ("industry_list.naver", "industry_read.naver"),
    "market": ("market_info_list.naver", "market_info_read.naver"),
    "invest": ("invest_list.naver", "invest_read.naver"),
    "economy": ("economy_list.naver", "economy_read.naver"),
    "debenture": ("debenture_list.naver", "debenture_read.naver"),
}
_NV_PDF_RE = re.compile(r"/stock-research/(\w+)/(\d+)/(\d{8})_(\w+)_(\d+)\.pdf")


def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = soup.select_one("#contentarea_left div.box_type_m table.type_1") or \
        soup.select_one("table.type_1") or soup.select_one("table")
    if table is None:
        return []
    headers = _table_headers(table)
    _, read_page = NV_CATS.get(cat, ("", "company_read.naver"))
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid, detail, title = None, None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid = m.group(1)
                detail = urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        # ★ 클래스명 하나(a.stock_item)에 의존하면 네이버가 클래스를 바꾸는 순간
        #   code 와 stock_name 이 동시에 죽고, 네이버 기여가 통째로 0 이 된다.
        #   href 에 code= 가 있는 링크면 모두 후보로 본다. 코드 판정은 to_code6 에 위임해
        #   2024 개편 영숫자 티커(예: 09701K)도 받아들인다.
        a_item = tr.select_one("a.stock_item[href]") or tr.select_one('a[href*="code="]')
        if a_item is not None:
            mm = re.search(r"code=([0-9A-Za-z]{6})", a_item["href"])
            code = to_code6(mm.group(1)) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        pdf = None
        for a in tr.find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                pdf = a["href"] if a["href"].startswith("http") else urljoin(NV_BASE, a["href"])
                break

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)
        vw = _pick(rm, "조회")

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None,
            "pdf_url": pdf, "detail_url": detail,
            "views": _clean_cell(vw).replace(",", "") or None,
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


def _nv_any_date(v: Any) -> Optional[str]:
    """네이버 JSON 의 날짜는 형식이 제각각이다. 전부 YYYY-MM-DD 로 정규화한다.

    ★ 이걸 건너뛰면 pd.to_datetime 자동추론이 '23.05.12' 를 2012-05-23 으로 읽고
      (연·일 뒤바뀜) 예외 없이 통과한다 — 리포트 원장의 시간축 전체가 어긋난다.
      epoch(ms) 를 그대로 넘기면 1970-01-01 이 된다."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10}", s):                       # epoch 초
        return _dt.datetime.utcfromtimestamp(int(s)).strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{13}", s):                       # epoch 밀리초
        return _dt.datetime.utcfromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{8}", s):                        # YYYYMMDD
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    kd = parse_kr_date(s)                                # YY.MM.DD 뒤바뀜 방어
    if kd:
        return kd
    try:
        t = pd.Timestamp(s[:19])
        if pd.notna(t) and 1990 <= t.year <= 2100:
            return t.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 60000) -> pd.DataFrame:
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
                "pub_date": _nv_any_date(it.get("createDate") or it.get("date") or
                                         it.get("writeDate") or it.get("regDate")),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                "detail_url": None, "views": it.get("readCount"),
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    if len(d):
        d = d[d["src_report_id"].astype(str).str.len() > 0]
    return d


def _nv_quality_ok(d: pd.DataFrame, sd, ed) -> Tuple[bool, str]:
    """JSON 응답을 채택할지 '건수' 가 아니라 '커버리지 품질' 로 판정한다.

    ★ 옛 게이트는 len(dj) > 50 이었다. 10년을 요청했는데 최근 수백 건만 돌아와도 통과해서,
      증권사 컬럼을 확실히 주는 유일한 경로인 HTML 폴백이 실행되지 않았다.
      ARC-BDF 는 broker 가 없으면 이벤트 자체가 성립하지 않으므로 여기서 막아야 한다."""
    if d is None or len(d) < 50:
        return False, f"건수 부족({0 if d is None else len(d)})"
    dd = as_ts_series(d["pub_date"])
    if dd.notna().mean() < 0.9:
        return False, f"날짜 파싱률 {100*dd.notna().mean():.0f}%"
    want = set(range(as_ts(sd).year, as_ts(ed).year + 1))
    got = set(dd.dropna().dt.year.unique().tolist())
    if len(want - got) > max(0, len(want) // 3):
        return False, f"연도 커버리지 부족(요청 {len(want)}년 중 {len(got & want)}년)"
    bro = d["broker_raw"].astype(str).str.strip().ne("").mean() if "broker_raw" in d else 0.0
    if bro < 0.5:
        return False, f"증권사 비공백률 {100*bro:.0f}%"
    return True, f"연도 {len(got & want)}/{len(want)} · 증권사 {100*bro:.0f}%"


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1200) -> pd.DataFrame:
    """★ 반드시 연 단위로 쪼개서 수집한다.

    옛 구현은 10년 구간을 한 번에 질의하고 max_pages 로 잘랐다. 네이버 리스트는 작성일
    내림차순이므로 잘린 결과는 '가장 최근 N페이지' 이고, 그러면 이벤트 밀도가 최근 구간에
    몰려 10년 백테스트가 사실상 최근 몇 년 백테스트가 된다 — 조용한 시간축 편향이다.
    (한경 수집기는 원래부터 연 단위로 쪼개고 있었다. 두 소스를 같은 규율로 맞춘다)"""
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    frames: List[pd.DataFrame] = []

    for cat in cats:
        # ① JSON API 를 연 단위로 시도
        js_frames, js_ok_years = [], 0
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            try:
                dj = naver_collect_json(cat, sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d"))
            except Exception:
                dj = pd.DataFrame()
            ok, why = _nv_quality_ok(dj, sd, ed)
            if ok:
                js_frames.append(dj)
                js_ok_years += 1
            else:
                LOG.debug(f"네이버 JSON '{cat}' {y}: 미채택 ({why}) → HTML 폴백 대상")

        need_html_years = [y for y in years]
        if js_ok_years:
            LOG.ok(f"네이버 JSON API '{cat}' — {js_ok_years}/{len(years)}개 연도 채택 "
                   f"({sum(len(x) for x in js_frames):,}건)")
            frames.extend(js_frames)
            covered = set()
            for x in js_frames:
                covered |= set(as_ts_series(x["pub_date"]).dropna().dt.year.unique().tolist())
            need_html_years = [y for y in years if y not in covered]

        if not need_html_years:
            continue

        # ② HTML 리스트 폴백 (연 단위)
        list_page, _ = NV_CATS[cat]
        base = urljoin(NV_BASE, list_page)

        def _year_sweep(y: int):
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            qp = {"searchType": "writeDate",
                  "writeFromDate": sd.strftime("%Y-%m-%d"),
                  "writeToDate": ed.strftime("%Y-%m-%d")}
            probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                             params=dict(qp, page=1), tries=3)
            if not probe:
                LOG.warn(f"네이버 '{cat}' {y} 리스트 접근 실패 — 그 해는 결측으로 남습니다.")
                return []
            last = min(_nv_last_page(probe), max_pages)
            out = _nv_parse_list(probe, cat)
            fail = 0
            for p in range(2, last + 1):
                h = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                             tries=3, params=dict(qp, page=p))
                chunk = _nv_parse_list(h, cat) if h else []
                if not chunk:
                    fail += 1
                    if fail >= 3:
                        LOG.warn(f"네이버 '{cat}' {y} 가 page {p} 에서 잘렸습니다 "
                                 f"(지금까지 {len(out):,}건).")
                        break
                    continue
                fail = 0
                out.extend(chunk)
            if last >= max_pages:
                LOG.warn(f"네이버 '{cat}' {y} 가 최대 페이지({max_pages})에 도달 — "
                         f"그 해 데이터가 잘렸을 수 있습니다.")
            return out

        res = pmap_io(_year_sweep, need_html_years, workers=min(4, N_WORKERS_IO),
                      desc=f"네이버 {cat}(연단위)")
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))

    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)

    # ★ 연도별 건수 표를 강제 출력하고, 특정 연도가 중앙값의 30% 미만이면 경고가 아니라
    #   '시간축 편향' 으로 명시한다. 이 표가 없으면 편향이 조용히 통과한다.
    yy = as_ts_series(d["pub_date"]).dt.year.value_counts().sort_index()
    if len(yy):
        med = float(yy.median())
        LOG.table([[str(int(y)), f"{int(n):,}",
                    "정상" if n >= med * 0.3 else "★부족(시간축 편향 위험)"]
                   for y, n in yy.items()],
                  ["연도", "건수", "판정"], ["c", "r", "l"],
                  title="네이버 리서치 연도별 수집량 — 최근 구간 쏠림 감시")
        thin = [int(y) for y, n in yy.items() if n < med * 0.3]
        if thin:
            LOG.warn(f"연도 {thin} 의 수집량이 중앙값의 30% 미만입니다. 그대로 쓰면 "
                     f"이벤트 밀도가 특정 구간에 쏠려 10년 백테스트가 사실상 그 구간 "
                     f"백테스트가 됩니다. 재실행으로 캐시를 채우거나 해당 연도를 "
                     f"해석에서 제외하세요.")
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


_NV_SRC_LINE = re.compile(r"([가-힣A-Za-z0-9\.\&\s]{2,25}?(?:증권|금융투자|투자증권))")


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다."""
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    if len(need) > limit:
        # ★ 최신순 상위 N 을 취하면 목표주가 보유율이 최근 1~2년에만 몰린다.
        #   그러면 '+3% 상향' 이벤트 밀도가 시간에 따라 왜곡되어 백테스트 성과가
        #   구간에 의존하게 된다. 연도별로 균등 배분해서 뽑는다.
        need["_y"] = as_ts_series(need["pub_date"]).dt.year
        n_y = max(1, need["_y"].nunique())
        per = max(50, limit // n_y)
        LOG.warn(f"네이버 상세 보강 대상 {len(need):,}건 중 {limit:,}건만 조회합니다 — "
                 f"연도별 최대 {per:,}건씩 균등 배분합니다(최근 구간 쏠림 방지).")
        need = (need.sort_values(["_y", "pub_date"], ascending=[True, False], kind="stable")
                    .groupby("_y", group_keys=False, observed=True).head(per).head(limit)
                    .drop(columns=["_y"]))

    def _one(u: str):
        h = http_get(u, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=2)
        if not h:
            return None
        s = soup_of(h)
        if s is None:
            return None
        box = s.select_one("div.view_info_1") or s
        tp = box.select_one("em.money strong") or box.select_one("em.money")
        op = box.select_one("em.coment")
        an = ""
        src = s.select_one("th.view_sbj p.source")
        if src is not None:
            an = _clean_cell(src.get_text(" "))
        return {"detail_url": u,
                "target_price": parse_target_price(tp.get_text() if tp else None),
                "opinion": parse_opinion(op.get_text() if op else None),
                "_detail_src": an}

    res = pmap_io(_one, need["detail_url"].tolist(), workers=min(8, N_WORKERS_IO),
                  desc="네이버 상세(목표주가)")
    got = pd.DataFrame([r for r in res if r])
    if got.empty:
        return df
    # ★ detail_url 이 유일하지 않으면 merge 가 행을 증식시킨다(리포트가 복제됨).
    #   원장 건수가 조용히 불어나 커버리지·리비전 통계가 전부 틀어진다.
    got = got.drop_duplicates("detail_url", keep="last")
    n_before = len(df)
    df = df.merge(got, on="detail_url", how="left", suffixes=("", "_d"))
    if len(df) != n_before:
        LOG.warn(f"상세 보강 머지에서 행수가 {n_before:,}→{len(df):,} 로 변했습니다 — "
                 f"중복 detail_url 로 인한 증식입니다.")
        df = df.drop_duplicates("report_uid", keep="first")
    for c in ("target_price", "opinion"):
        if f"{c}_d" in df.columns:
            df[c] = df[c].where(df[c].notna(), df[f"{c}_d"])
            df = df.drop(columns=[f"{c}_d"])

    # ★ 상세페이지 th.view_sbj p.source 는 애널리스트가 아니라 '증권사 | 작성일' 라인이다.
    #   지금까지 수집만 하고 버렸다. ARC-BDF 는 broker 가 없으면 이벤트가 성립하지 않으므로
    #   증권사 결측을 복구할 가장 값싼 경로로 배선한다.
    if "_detail_src" in df.columns:
        cand = df["_detail_src"].astype(str).map(
            lambda t: (_NV_SRC_LINE.search(t).group(1).strip() if _NV_SRC_LINE.search(t) else ""))
        blank = df.get("broker_raw", pd.Series("", index=df.index)).astype(str).str.strip().eq("")
        fill = blank & cand.astype(str).str.strip().ne("")
        if fill.any():
            if "broker_raw" not in df.columns:
                df["broker_raw"] = ""
            df.loc[fill, "broker_raw"] = cand[fill]
            LOG.ok(f"상세페이지 출처 라인에서 증권사 {int(fill.sum()):,}건 복구 "
                   f"(ARC-BDF 는 broker 가 없으면 이벤트 자체가 성립하지 않습니다)")
        df = df.drop(columns=["_detail_src"])

    LOG.ok(f"네이버 상세 보강 — 목표주가 {int(got['target_price'].notna().sum()):,}건 추가 확보")
    return df


# ── PDF 원문 ────────────────────────────────────────────────────────────────────────────────
_ANALYST_LINE = re.compile(
    r"([가-힣]{2,4})\s*(?:연구원|애널리스트|수석|책임|선임)?\s*"
    r"(?:\(?\s*(?:02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}\s*\)?)?\s*"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TP_PAT = re.compile(r"(?:목표\s*주가|목표주가|적정\s*주가|적정주가|TP)\s*[:：(]?\s*"
                     r"(?:원\)?\s*)?([0-9][0-9,]{2,9})")


def pdf_text(data: bytes, max_pages: int = 3) -> str:
    """1페이지 헤더/푸터에 애널리스트명·이메일·목표주가가 몰려 있다. 앞 3장이면 충분하다."""
    if not data or data[:5] != b"%PDF-":
        return ""
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count)))
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
        except Exception:
            pass
    return ""


def pdf_extract_fields(text: str) -> dict:
    out = {"pdf_analysts": "", "pdf_emails": "", "pdf_target": None}
    if not text:
        return out
    pairs = _ANALYST_LINE.findall(text[:6000])
    names = [p[0] for p in pairs]
    mails = [p[1] for p in pairs] or _EMAIL.findall(text[:6000])
    if not names:
        # 이메일 로컬파트에서 역추적 실패 시, '연구원/애널리스트' 앞 한글 이름만이라도
        names = re.findall(r"([가-힣]{2,4})\s*(?:연구원|애널리스트)", text[:6000])
    out["pdf_analysts"] = ",".join(dict.fromkeys(names))[:120]
    out["pdf_emails"] = ",".join(dict.fromkeys(mails))[:200]
    m = _TP_PAT.search(text[:8000])
    if m:
        out["pdf_target"] = parse_target_price(m.group(1))
    return out


def download_pdfs(df: pd.DataFrame, cap_per_month: int = 0) -> pd.DataFrame:
    """PDF 를 공용 인덱스에 저장(내용해시 경로 → 중복 저장 없음)하고 본문 필드를 추출한다."""
    if df.empty or not RESEARCH_DOWNLOAD_PDF:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None if c != "pdf_uid" else ""
        return df
    if fitz is None and pdfplumber is None:
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 원문 추출을 건너뜁니다. "
                 "한경 리스트의 작성자/목표주가만으로도 애널리스트 연결은 동작합니다.")
    work = df[df["pdf_url"].notna()].copy()
    if cap_per_month and len(work):
        work["_m"] = as_ts_series(work["pub_date"]).dt.to_period("M")
        work = work.groupby("_m", observed=True).head(cap_per_month).drop(columns=["_m"])
    if work.empty:
        return df

    idx = VAULT.load_index("shared")
    known = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        # iterrows 는 30만 행에서 13초를 쓴다. zip 은 같은 결과를 0.2초에 만든다.
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
    LOG.info(f"PDF 대상 {len(work):,}건 (드라이브 캐시 보유 {sum(1 for k in work['report_uid'] if k in known):,}건)")

    def _one(rec):
        uid, url = rec
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
            if data:
                return (uid, known[uid], data)
            # 인덱스에는 있는데 실제 파일이 없으면(드라이브 동기화 누락 등) 재수집으로 폴백한다.
            # 여기서 포기하면 그 보고서는 영구히 비어 있는 채로 남는다.
        raw = http_get(url, source="hankyung" if "hankyung" in str(url) else "naver",
                       as_bytes=True, tries=2, referer=HK_BASE + "/" if "hankyung" in str(url) else NV_BASE)
        if not raw or raw[:5] != b"%PDF-":
            return (uid, "", b"")          # 로그인/에러 HTML 이 200 으로 오는 케이스 방어
        return (uid, "", raw)

    jobs = list(zip(work["report_uid"].astype(str), work["pdf_url"].astype(str)))

    # ★ 청크로 끊어 받는다. pmap_io 는 결과 리스트를 통째로 들고 있으므로, 한 번에 던지면
    #   내려받은 PDF 본문 전부가 동시에 RAM 에 남는다. 목표치인 연 3만건 × 10년 = 30만건에
    #   평균 300KB 를 곱하면 90GB 다. 캐시가 차 있어도 마찬가지다 — 캐시 경로도 blob 바이트를
    #   그대로 반환하기 때문에 오히려 더 빨리 쌓인다. 청크 단위로 소비하고 버리면 상주량이
    #   작업 수와 무관하게 평평해진다(약 600MB). 청크마다 flush 하므로 중간에 끊겨도 이어받는다.
    PDF_CHUNK = 2000
    rows = []
    ok = 0
    for k0 in range(0, len(jobs), PDF_CHUNK):
        chunk = jobs[k0:k0 + PDF_CHUNK]
        res = pmap_io(_one, chunk, workers=min(N_WORKERS_IO, 10),
                      desc=f"리포트 PDF {k0//PDF_CHUNK + 1}/{(len(jobs)-1)//PDF_CHUNK + 1}")
        for r in res:
            if not r:
                continue
            uid, existing_blob_uid, data = r
            if not data:
                continue
            ok += 1
            blob_uid = existing_blob_uid
            if not blob_uid:
                p = VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                                   source="report_pdf", scope="shared")
                blob_uid = sha1_str("research", "report_pdf", uid, sha1_bytes(data)) if p else ""
            f = pdf_extract_fields(pdf_text(data))
            rows.append({"report_uid": uid, "pdf_uid": blob_uid, **f})
        del res
        VAULT.flush("shared")
    VAULT.flush("shared")
    LOG.ok(f"PDF 확보 {ok:,}/{len(jobs):,}건 — 공용 인덱스에 저장(내용해시 중복제거 적용)")
    if not rows:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None
        return df
    ext = pd.DataFrame(rows)
    df = df.merge(ext, on="report_uid", how="left")
    PIPE.io("OUT", "DRIVE", "research:pdf", ext, source="hankyung/naver pdf")
    return df
