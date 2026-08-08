# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 수집 — 한경컨센서스 + 네이버리서치  (전면 재작성)                 ║
# ║                                                                                          ║
# ║  ■ 실측(사용자 실행 로그)에서 무슨 일이 있었나                                             ║
# ║      한경컨센서스 0건            ← 고신뢰(link_conf 0.98) 애널리스트 소스가 통째로 증발     ║
# ║      네이버 JSON 실패 → HTML     ← 2,350페이지 16분                                        ║
# ║      네이버 상세 5,733/20,000    ← 38분에 29%. 상한만 채우는 데 2.2시간, 전량은 5시간       ║
# ║      PDF 대상 64,190건           ← 그 뒤로 몇 시간 + 수십 GB                                ║
# ║                                                                                          ║
# ║  ■ 재작성 원칙                                                                            ║
# ║   ① 한경을 살리는 것이 최대 레버리지다.                                                    ║
# ║      한경은 '리스트 한 장에 작성자·목표주가·투자의견'이 다 온다. 네이버는 작성자를          ║
# ║      상세페이지에 숨겨 둔다. 즉 한경 1페이지 = 네이버 상세 80건과 같은 값을 한 번에 준다.   ║
# ║      한경이 죽으면 그 부담이 전부 네이버 상세로 넘어가고, 그게 5시간짜리 병목이 된다.      ║
# ║      → 엔드포인트를 하나로 믿지 않는다. 후보를 실측으로 두드려 살아 있는 것을 찾는다.      ║
# ║      → 그래도 0건이면 '왜' 0건인지(도달 여부·응답크기·표 유무)를 반드시 진단해 남긴다.     ║
# ║        조용한 0건은 데이터 부재가 아니라 코드 실패인데, 로그만 봐서는 구분이 안 된다.      ║
# ║                                                                                          ║
# ║   ② 상세 보강은 '한 번만' 한다 — 영구 캐시로 만든다.                                       ║
# ║      nid 는 불변이다. 한 번 받은 상세는 공용 인덱스에 남기면 이 전략도, 다른 전략도,       ║
# ║      다음 세션도 다시 받지 않는다. 5시간짜리 작업이 두 번째 실행부터 0초가 된다.           ║
# ║                                                                                          ║
# ║   ③ 상한을 걸 때 '최신순'으로 자르지 않는다.  ★ 조용한 치명 결함이었다.                    ║
# ║      최신 20,000건만 받으면 2024~2026 만 채워지고 2016~2019 는 텅 빈다. 링크 행렬이         ║
# ║      비면 백테스트 앞 절반이 신호 없이 지나가는데, 어디에도 에러가 안 뜬다.                ║
# ║      → 월 단위 라운드로빈으로 고르게 뽑는다. 잘리더라도 시간축 전체가 균일하게 남는다.     ║
# ║                                                                                          ║
# ║   ④ PDF 는 기본 끈다.  네이버 바이라인 회수만으로 애널리스트 식별이 되므로, 6.4만 건의     ║
# ║      PDF 는 대부분 이미 아는 사실을 다시 확인하는 비용이다. 필요한 사람만 켜면 된다.       ║
# ║                                                                                          ║
# ║   ⑤ 받은 것은 예외 없이 저장한다(절대원칙). 소스별 원본 리스트까지 공용 인덱스에 남겨      ║
# ║      중간에 끊겨도, 세션이 바뀌어도 그 지점부터 이어간다.                                  ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자가 명시적으로 수집을 지시했으므로     ║
# ║    수행하되, 초당 요청을 보수적으로 제한하고 이 사실을 로그에 명시한다.                    ║
# ║  ⚠ PDF 원문은 증권사 저작물이다. 로컬 캐시/분석 용도로만 쓰고 재배포하지 말 것.             ║
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


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABCABC' 처럼 2~3회 반복되어 나오는 알려진 버그를 되돌린다."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0:
            unit = s[: n // k]
            if unit * k == s:
                return unit
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



# ── 한경컨센서스 : 엔드포인트 자동탐색 ──────────────────────────────────────────────────────
#   ★ 실측에서 0건이 나온 지점이다. 한경은 화면 개편 때 경로와 파라미터 이름을 함께 바꾼다.
#     하나를 하드코딩하고 죽는 대신, 후보 조합을 짧은 구간으로 두드려 보고 살아 있는 것을
#     고른다. 성공 조합은 전용 인덱스에 저장해 다음 실행에서 곧장 재사용한다(세션 무관).
HK_ENDPOINTS = [
    # (설명, URL, 파라미터 빌더)
    ("legacy/analysis.list", HK_BASE + "/apps.analysis/analysis.list",
     lambda sd, ed, pg, ps: {"sdate": sd, "edate": ed, "now_page": pg, "pagenum": ps,
                             "report_type": "CO", "order_type": "", "search_text": "",
                             "search_value": "", "business_code": ""}),
    ("analysis/list?skinType", HK_LIST,
     lambda sd, ed, pg, ps: {"skinType": "business", "sdate": sd, "edate": ed,
                             "now_page": pg, "pagenum": ps, "report_type": "CO",
                             "order_type": "", "search_text": "", "search_value": "",
                             "business_code": ""}),
    ("analysis/list(plain)", HK_LIST,
     lambda sd, ed, pg, ps: {"sdate": sd, "edate": ed, "now_page": pg, "pagenum": ps}),
    ("apps.analysis(plain)", HK_BASE + "/apps.analysis/analysis.list",
     lambda sd, ed, pg, ps: {"sdate": sd, "edate": ed, "now_page": pg, "pagenum": ps}),
]
_HK_CHOSEN: Optional[int] = None


def _hk_request(ep_idx: int, sd: str, ed: str, page: int, page_size: int) -> Optional[str]:
    _desc, url, mk = HK_ENDPOINTS[ep_idx]
    return http_get(url, source="hankyung", params=mk(sd, ed, page, page_size),
                    tries=3, referer=HK_BASE + "/", timeout=30)


def hankyung_probe(end: str) -> Optional[int]:
    """살아 있는 엔드포인트 조합을 찾는다. 못 찾으면 '왜' 못 찾았는지를 표로 남긴다.

    조용한 0건이 가장 위험하다. 데이터가 정말 없는 것과 코드가 틀린 것을 구분하지 못하면
    사용자는 몇 시간을 기다린 뒤에야 소스 하나가 통째로 빠진 결과를 받게 된다.
    """
    global _HK_CHOSEN
    if _HK_CHOSEN is not None:
        return _HK_CHOSEN
    saved = cache_recall("hankyung_endpoint", scope="private")
    if saved is not None and len(saved):
        try:
            i = int(saved["ep_idx"].iloc[-1])
            if 0 <= i < len(HK_ENDPOINTS):
                # 저장된 조합을 그대로 신뢰하지 않고 1회 확인한다(사이트가 또 바뀌었을 수 있다)
                ed = as_ts(end)
                sd = (ed - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
                if _hk_parse(_hk_request(i, sd, ed.strftime("%Y-%m-%d"), 1, 20) or "", "probe"):
                    _HK_CHOSEN = i
                    LOG.ok(f"한경 엔드포인트 캐시 적중 — {HK_ENDPOINTS[i][0]}")
                    return i
        except Exception:
            pass
    ed = as_ts(end)
    sd = (ed - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
    rows_out, best = [], None
    for i, (desc, url, _mk) in enumerate(HK_ENDPOINTS):
        html = _hk_request(i, sd, ed.strftime("%Y-%m-%d"), 1, 20)
        if html is None:
            rows_out.append([desc, "도달실패", "-", "-", "네트워크/차단/404"])
            continue
        n_bytes = len(html)
        has_idx = "report_idx" in html
        parsed = _hk_parse(html, "probe")
        rows_out.append([desc, "200", f"{n_bytes:,}B",
                         f"{len(parsed)}건", "OK" if parsed else
                         ("표는 있으나 파싱 0" if has_idx else "리포트 링크 없음")])
        if parsed and best is None:
            best = i
    LOG.table(rows_out, ["엔드포인트 후보", "응답", "크기", "파싱", "판정"],
              ["l", "l", "r", "r", "l"], title="한경컨센서스 엔드포인트 탐색")
    if best is None:
        LOG.error(
            "한경컨센서스에서 리포트를 한 건도 파싱하지 못했습니다. 위 표가 원인을 가립니다:\n"
            "  · 전부 '도달실패'  → 네트워크 차단(사내망/프록시) 또는 IP 차단입니다.\n"
            "  · 200 인데 파싱 0  → 사이트 레이아웃이 바뀌었습니다. 이 경우 네이버 단독으로\n"
            "    진행하며, 애널리스트 식별은 네이버 상세 바이라인에만 의존하게 됩니다\n"
            "    (Phase 0 게이트가 그 확보율을 판정하므로 결과가 조용히 왜곡되지는 않습니다).")
        return None
    _HK_CHOSEN = best
    persist("hankyung_endpoint", pd.DataFrame([{"ep_idx": best, "desc": HK_ENDPOINTS[best][0],
                                                "checked": as_ts(_dt.date.today())}]),
            scope="private", domain="research", source="endpoint probe")
    LOG.ok(f"한경컨센서스 엔드포인트 확정 — {HK_ENDPOINTS[best][0]}")
    return best


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다.

    ★ 캐시 우선: 이미 받은 연도는 다시 받지 않는다(공용 인덱스, 세션 무관).
    """
    prev = cache_recall("research_raw_hankyung", scope="shared")
    have_years: set = set()
    if prev is not None and len(prev):
        pdt = as_ts_series(prev["pub_date"])
        # '연도가 통째로 있다'고 보려면 그 해의 월이 충분히 채워져 있어야 한다.
        # 한 달치만 있는 해를 '완료'로 보면 나머지 11개월을 영원히 못 받는다.
        cov = pdt.dt.to_period("M").astype(str).groupby(pdt.dt.year).nunique() \
            if len(pdt.dropna()) else pd.Series(dtype=int)
        this_y = as_ts(end).year
        for y, n_m in cov.items():
            need = 12 if int(y) < this_y else max(1, as_ts(end).month)
            if int(n_m) >= need:
                have_years.add(int(y))
        LOG.info(f"공용 캐시에서 한경 {len(prev):,}건 재사용 — "
                 f"완결 연도 {sorted(have_years)} 는 재수집하지 않습니다.")

    ep = hankyung_probe(end)
    years = [y for y in range(as_ts(start).year, as_ts(end).year + 1) if y not in have_years]
    if ep is None or not years:
        out = prev if prev is not None else pd.DataFrame(columns=REPORT_COLS)
        if ep is not None and not years:
            LOG.ok("한경컨센서스 — 모든 연도가 캐시에 있습니다(신규 요청 0건).")
        return out

    jobs = [(y, max(as_ts(f"{y}-01-01"), as_ts(start)), min(as_ts(f"{y}-12-31"), as_ts(end)))
            for y in years]

    def _sweep(job):
        _y, sd, ed = job
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            html = _hk_request(ep, sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d"),
                               page, page_size)
            if not html:
                break
            batch = _hk_parse(html, "business")
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            for b in fresh:
                seen_ids.add(b["src_report_id"])
            got.extend(fresh)
            # 조기 종료를 느슨하게 잡으면 데이터가 조용히 잘려나간다 — 2회 연속 0건일 때만 멈춘다.
            if len(fresh) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
            if page == max_pages:
                LOG.warn(f"한경 {sd:%Y} 구간이 최대 페이지({max_pages})에 도달했습니다 — "
                         f"데이터가 잘렸을 수 있습니다. (지금까지 {len(got):,}건)")
        return got

    res = pmap_io(_sweep, jobs, workers=_resolve_workers("hankyung", hard_cap=6),
                  desc="한경컨센서스")
    rows: List[dict] = [r for chunk in res if chunk for r in chunk]
    fresh_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPORT_COLS)
    if len(fresh_df):
        note_new_data("research_raw_hankyung", len(fresh_df), "shared", "research", "hankyung")
    merged = pd.concat([x for x in (prev, fresh_df) if x is not None and len(x)],
                       ignore_index=True) if (prev is not None or len(fresh_df)) else fresh_df
    if len(merged):
        merged = merged.drop_duplicates(
            subset=[c for c in ("source", "src_report_id") if c in merged.columns], keep="last")
        # ★ 절대원칙: 새로 받은 즉시 공용 인덱스에 저장한다 (다음 세션이 그대로 재사용)
        if len(fresh_df):
            persist("research_raw_hankyung", merged, scope="shared", domain="research",
                    source=f"hankyung:{HK_ENDPOINTS[ep][0]}")
    d = merged
    LOG.ok(f"한경컨센서스 {len(d):,}건 (신규 {len(fresh_df):,}) "
           f"(작성자 보유 {int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} / "
           f"목표주가 보유 {int(d['target_price'].notna().sum()) if len(d) and 'target_price' in d else 0:,})")
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
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=(\d{6})", a_item["href"])
            code = mm.group(1) if mm else None
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



NV_API_CANDIDATES = [
    "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}",
    "https://m.stock.naver.com/api/research/{cat}",
    "https://api.stock.naver.com/research/{cat}",
]
NV_DETAIL_TPL = "https://finance.naver.com/research/{page}?nid={nid}&page=1"
NV_DETAIL_COLS = ["src_report_id", "detail_url", "target_price", "opinion",
                  "_detail_src", "fetched_at"]


def _nv_detail_url(cat: str, nid: Any, existing: Any = None) -> Optional[str]:
    """상세 URL. 리스트가 준 게 있으면 그걸, 없으면 nid 로 만든다.

    ★ JSON API 경로에는 detail_url 이 없다. 예전 구현은 그래서 JSON 으로 받은 건에 대해
      상세 보강을 통째로 건너뛰었다 — 바이라인(=애널리스트)이 사라지는 조용한 경로였다.
    """
    if existing:
        return str(existing)
    nid = str(nid or "").strip()
    if not nid.isdigit():
        return None
    page = NV_CATS.get(cat, ("", "company_read.naver"))[1]
    return NV_DETAIL_TPL.format(page=page, nid=nid)


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 60000) -> pd.DataFrame:
    """신형 JSON API. 되면 HTML 페이징보다 훨씬 빠르고 구조가 안정적이다.

    ★ 후보 URL 을 순서대로 시도한다. 실측에서 v2 경로가 죽어 HTML 폴백으로 떨어졌는데,
      폴백 자체는 정상 동작이라 로그만 봐서는 '왜 느린지'를 알 수 없었다 — 이제 표로 남는다.
    """
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    for tpl in NV_API_CANDIDATES:
        rows, index, url = [], 0, tpl.format(cat=cat)
        while index < hard_cap:
            js = http_json(url, source="naver", tries=2, headers=hdr,
                           params={"index": index, "size": page_size, "page": index // page_size + 1,
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
                nid = str(it.get("id") or it.get("nid") or it.get("researchId") or "")
                rows.append({
                    "source": "naver", "category": cat, "src_report_id": nid,
                    "pub_date": parse_kr_date(it.get("createDate") or it.get("date")
                                              or it.get("writeDate")),
                    "title": _dedup_repeat(str(it.get("title") or "")),
                    "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                    "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                    "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                    "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                    "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                    "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                    "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                    "detail_url": _nv_detail_url(cat, nid), "views": it.get("readCount"),
                })
            if len(items) < page_size:
                break
            index += len(items)
        d = pd.DataFrame(rows)
        if len(d):
            d = d[d["src_report_id"].astype(str).str.len() > 0]
        if len(d) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(d):,}건  ({url})")
            return d
    return pd.DataFrame()


def _nv_missing_ranges(prev: Optional[pd.DataFrame], cat: str,
                       start: str, end: str) -> List[Tuple[str, str]]:
    """캐시에 없는 '달'만 골라 연속 구간으로 묶는다. 재실행에서 새 달만 받는다.

    ★ 네이버 HTML 리스트는 writeFromDate/writeToDate 를 지원하므로 구간 요청이 가능하다.
      페이지 번호 기반 증분은 새 글이 앞에 끼면 전부 밀려서 못 쓴다 — 날짜 축이 정답이다.
    """
    months = [str(p) for p in pd.period_range(as_ts(start), as_ts(end), freq="M")]
    have: set = set()
    if prev is not None and len(prev):
        sub = prev[prev.get("category", pd.Series("", index=prev.index)).astype(str) == cat] \
            if "category" in prev.columns else prev
        if len(sub):
            have = set(as_ts_series(sub["pub_date"]).dt.to_period("M").astype(str).dropna())
    miss = [m for m in months if m not in have]
    if not miss:
        return []
    out, run_lo, prev_m = [], miss[0], miss[0]
    for m in miss[1:]:
        if (pd.Period(m, "M") - pd.Period(prev_m, "M")).n == 1:
            prev_m = m
            continue
        out.append((run_lo, prev_m))
        run_lo = prev_m = m
    out.append((run_lo, prev_m))
    return [(pd.Period(a, "M").start_time.strftime("%Y-%m-%d"),
             pd.Period(b, "M").end_time.strftime("%Y-%m-%d")) for a, b in out]


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1500) -> pd.DataFrame:
    """네이버 리서치 리스트. 캐시에 없는 달만 받는다(공용 인덱스, 세션 무관)."""
    prev = cache_recall("research_raw_naver", scope="shared")
    if prev is not None and len(prev):
        LOG.info(f"공용 캐시에서 네이버 리스트 {len(prev):,}건 재사용 — 빠진 달만 받습니다.")
    frames: List[pd.DataFrame] = []
    for cat in cats:
        gaps = _nv_missing_ranges(prev, cat, start, end)
        if not gaps:
            LOG.ok(f"네이버 '{cat}' — 캐시가 구간 전체를 덮습니다(신규 요청 0건).")
            continue
        n_mon = sum((pd.Period(b[:7], "M") - pd.Period(a[:7], "M")).n + 1 for a, b in gaps)
        LOG.info(f"네이버 '{cat}' 미보유 {n_mon}개월 / {len(gaps)}구간")
        for (gs, ge) in gaps:
            # ① JSON API 우선
            try:
                dj = naver_collect_json(cat, gs, ge)
            except Exception:
                dj = pd.DataFrame()
            if len(dj) > 50:
                frames.append(dj)
                continue
            # ② HTML 리스트 폴백
            list_page, _ = NV_CATS[cat]
            base = urljoin(NV_BASE, list_page)
            q = {"searchType": "writeDate", "writeFromDate": gs, "writeToDate": ge, "page": 1}
            probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr", params=q)
            if not probe:
                LOG.warn(f"네이버 '{cat}' {gs}~{ge} 리스트 접근 실패 — 이 구간을 건너뜁니다.")
                continue
            last = min(_nv_last_page(probe), max_pages)

            def _pg(p: int, _b=base, _gs=gs, _ge=ge, _c=cat, _first=probe):
                # ★ 파라미터 dict 를 기본인자로 공유하면 안 된다. 기본인자는 함수당 한 번만
                #   평가되므로 모든 스레드가 같은 dict 를 쓰게 되고, _q["page"]=p 가 서로를
                #   덮어써 엉뚱한 페이지를 중복으로 받거나 어떤 페이지를 통째로 빠뜨린다.
                #   (예외도 안 나고 건수만 조용히 달라진다 — 매 실행 결과가 미묘하게 바뀐다)
                if p == 1:
                    return _nv_parse_list(_first, _c)
                q_ = {"searchType": "writeDate", "writeFromDate": _gs,
                      "writeToDate": _ge, "page": p}
                h = http_get(_b, source="naver", referer=NV_BASE, force_enc="euc-kr",
                             tries=3, params=q_)
                return _nv_parse_list(h, _c) if h else []

            res = pmap_io(_pg, list(range(1, last + 1)),
                          workers=_resolve_workers("naver", hard_cap=10),
                          desc=f"네이버 {cat} {gs[:7]}~{ge[:7]}")
            rows = [r for chunk in res if chunk for r in chunk]
            if rows:
                frames.append(pd.DataFrame(rows))

    fresh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(fresh):
        # 리스트에 detail_url 이 없는 건(JSON 경로)은 nid 로 만들어 둔다 — 상세 보강의 전제
        if "detail_url" not in fresh.columns:
            fresh["detail_url"] = None
        fresh["detail_url"] = [
            _nv_detail_url(c, n, u) for c, n, u in
            zip(fresh.get("category", pd.Series("company", index=fresh.index)),
                fresh.get("src_report_id", pd.Series("", index=fresh.index)),
                fresh["detail_url"])]
        note_new_data("research_raw_naver", len(fresh), "shared", "research", "naver")
    d = pd.concat([x for x in (prev, fresh) if x is not None and len(x)], ignore_index=True) \
        if (prev is not None or len(fresh)) else pd.DataFrame(columns=REPORT_COLS)
    if len(d):
        d = d.drop_duplicates(subset=[c for c in ("source", "src_report_id") if c in d.columns],
                              keep="last").reset_index(drop=True)
        if len(fresh):
            persist("research_raw_naver", d, scope="shared", domain="research", source="naver")
    LOG.ok(f"네이버 리서치 {len(d):,}건 (신규 {len(fresh):,}) "
           f"(종목코드 보유 {int(d['stock_code'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def _nv_stratified(need: pd.DataFrame, limit: int) -> pd.DataFrame:
    """월별 라운드로빈으로 limit 건을 고른다.

    ★ 이 함수가 없던 것이 조용한 치명 결함이었다. 예전 구현은 최신순 head(limit) 였다.
      45,000건 중 최신 20,000건만 받으면 2023~2026 만 채워지고 2016~2022 는 0건이 된다.
      링크 행렬은 '연결 3개 미만이면 결측'이므로 앞 6~7년의 신호가 통째로 사라지는데,
      어디에서도 예외가 나지 않는다. 백테스트는 그냥 짧아진 표본으로 조용히 끝난다.
      → 달마다 한 건씩 돌아가며 뽑으면, 잘리더라도 시간축 전체가 균일하게 남는다.
    """
    if limit <= 0 or len(need) <= limit:
        return need           # limit<=0 은 '무제한' — head(0) 로 전멸시키지 않는다
    n = need.copy()
    n["_m"] = as_ts_series(n["pub_date"]).dt.to_period("M").astype(str)
    n["_rk"] = n.groupby("_m").cumcount()
    n = n.sort_values(["_rk", "_m"]).head(limit).drop(columns=["_m", "_rk"])
    return n


def naver_enrich_detail(df: pd.DataFrame, limit: int = 0) -> pd.DataFrame:
    """네이버 상세 보강 — 애널리스트 바이라인(1순위)과 목표주가(부수)를 회수한다.

    ■ 재작성 요지
      · 영구 캐시   : nid 는 불변이므로 한 번 받으면 끝이다. 공용 인덱스에 남겨 다음
                      세션·다른 전략이 절대 다시 받지 않게 한다(절대원칙). 5시간 → 0초.
      · 균등 표본   : 상한에 걸리면 월 라운드로빈으로 자른다 (위 _nv_stratified 참조).
      · 처리량      : 전용 버킷(naver_detail)과 그에 맞는 워커 수. 실측 2.5it/s 는 워커가
                      아니라 QPS 버킷이 만든 상한이었다.
      · 이어받기    : 청크마다 캐시에 반영하므로 중간에 끊겨도 그 지점부터 이어간다.
    """
    if df is None or df.empty:
        return df
    # 0 = 무제한. int(limit or MAX) 만 쓰면 MAX 가 0 일 때 limit 이 0 이 되어
    # _nv_stratified 가 head(0) 로 전부 날려버린다 — '무제한'이 '전멸'이 되는 반전.
    limit = int(limit) if limit else int(NAVER_DETAIL_MAX)
    if limit <= 0:
        limit = 10 ** 9
    cache = cache_recall("naver_research_detail", scope="shared")
    known: Dict[str, dict] = {}
    if cache is not None and len(cache):
        cache = cache.drop_duplicates("src_report_id", keep="last")
        known = {str(r.src_report_id): {"target_price": r.target_price, "opinion": r.opinion,
                                        "_detail_src": r._detail_src}
                 for r in cache.itertuples(index=False)}
        LOG.info(f"공용 캐시에서 네이버 상세 {len(known):,}건 재사용 — 다시 받지 않습니다.")

    is_nv = df["source"].astype(str).eq("naver") if "source" in df.columns else pd.Series(True, index=df.index)
    cat_ok = df["category"].astype(str).eq("company") if "category" in df.columns else pd.Series(True, index=df.index)
    has_url = df["detail_url"].notna() if "detail_url" in df.columns else pd.Series(False, index=df.index)
    # ★ 결측 id 를 astype(str) 하면 전부 "nan" 이 되어 서로 같은 키가 된다.
    #   그 상태로 merge 하면 서로 다른 리포트에 같은 애널리스트·목표주가가 붙는다
    #   (원장 오염 → 링크 행렬 오염 → 신호 오염). 아예 대상에서 빼는 것이 유일한 안전책이다.
    rid = (df["src_report_id"].astype(str).str.strip()
           if "src_report_id" in df.columns else pd.Series("", index=df.index))
    rid_ok = rid.str.len().gt(0) & ~rid.str.lower().isin(("nan", "none", "<na>"))
    # 이미 아는 건 제외. '작성자를 모르는 것'이 최우선이고 목표주가는 부수적이다.
    no_analyst = (df["analyst_raw"].astype(str).str.strip().eq("")
                  if "analyst_raw" in df.columns else pd.Series(True, index=df.index))
    unseen = ~rid.isin(set(known))
    need = df[is_nv & cat_ok & has_url & unseen & no_analyst & rid_ok].copy()

    if need.empty:
        LOG.ok("네이버 상세 — 신규 조회 대상 0건 (전부 캐시 보유).")
    else:
        n_all = len(need)
        need = _nv_stratified(need, limit)
        if len(need) < n_all:
            LOG.warn(f"네이버 상세 대상 {n_all:,}건 중 {len(need):,}건만 이번에 조회합니다 "
                     f"(NAVER_DETAIL_MAX). ★ 최신순이 아니라 월별 균등 추출이므로 "
                     f"백테스트 앞 구간이 비지 않습니다. 나머지는 다음 실행에서 이어받습니다.")
        jobs = list(zip(need["src_report_id"].astype(str), need["detail_url"].astype(str)))

        def _one(job):
            rid_, u = job
            h = http_get(u, source="naver_detail", referer=NV_BASE, force_enc="euc-kr", tries=2)
            if not h:
                return None
            s = soup_of(h)
            if s is None:
                return None
            box = s.select_one("div.view_info_1") or s
            tp = box.select_one("em.money strong") or box.select_one("em.money")
            op = box.select_one("em.coment")
            src = s.select_one("th.view_sbj p.source")
            return {"src_report_id": rid_, "detail_url": u,
                    "target_price": parse_target_price(tp.get_text() if tp else None),
                    "opinion": parse_opinion(op.get_text() if op else None),
                    "_detail_src": _clean_cell(src.get_text(" ")) if src is not None else "",
                    "fetched_at": as_ts(_dt.date.today())}

        CH = 2500
        acc: List[dict] = []
        w = _resolve_workers("naver_detail", hard_cap=16)
        for k0 in range(0, len(jobs), CH):
            part = jobs[k0:k0 + CH]
            res = pmap_io(_one, part, workers=w,
                          desc=f"네이버 상세 {k0 // CH + 1}/{(len(jobs) - 1) // CH + 1}")
            acc.extend([r for r in res if r])
            # ★ 청크마다 즉시 영속화 — 여기서 끊겨도 다음 실행이 이어받는다
            if acc:
                snap = pd.DataFrame(acc)
                full = pd.concat([x for x in (cache, snap) if x is not None and len(x)],
                                 ignore_index=True).drop_duplicates("src_report_id", keep="last")
                note_new_data("naver_research_detail", len(snap), "shared", "research", "naver")
                persist("naver_research_detail", full.reindex(columns=NV_DETAIL_COLS),
                        scope="shared", domain="research", source="naver detail")
            del res
        for r in acc:
            known[str(r["src_report_id"])] = r
        LOG.ok(f"네이버 상세 신규 {len(acc):,}건 — "
               f"바이라인 {sum(1 for r in acc if r.get('_detail_src')):,}건 / "
               f"목표주가 {sum(1 for r in acc if r.get('target_price') is not None):,}건")

    if not known:
        return df
    # ── 병합: detail_url 이 아니라 src_report_id 로 붙인다 ────────────────────────────────
    #   detail_url 은 page 파라미터 때문에 같은 리포트가 서로 다른 문자열이 될 수 있다.
    #   그 상태로 merge 하면 붙지 않거나(결측) 중복 증식한다. nid 는 유일하고 불변이다.
    kd = pd.DataFrame([{"src_report_id": k, **{c: v.get(c) for c in
                                               ("target_price", "opinion", "_detail_src")}}
                       for k, v in known.items()])
    n_before = len(df)
    df = df.copy()
    df["src_report_id"] = rid.where(rid_ok, other=pd.NA)     # 결측 id 는 아예 안 붙게 만든다
    kd["src_report_id"] = kd["src_report_id"].astype(str).str.strip()
    out = df.merge(kd, on="src_report_id", how="left", suffixes=("", "_d"))
    if len(out) != n_before:
        LOG.warn(f"상세 병합에서 행수가 {n_before:,}→{len(out):,} 로 변했습니다 — "
                 f"중복 src_report_id 로 인한 증식입니다. 원장 기준으로 접습니다.")
        out = out.drop_duplicates("report_uid" if "report_uid" in out.columns
                                  else "src_report_id", keep="first")
    for c in ("target_price", "opinion"):
        if f"{c}_d" in out.columns:
            out[c] = out[c].where(out[c].notna(), out[f"{c}_d"])
            out = out.drop(columns=[f"{c}_d"])
    if "_detail_src_d" in out.columns:
        base = out["_detail_src"] if "_detail_src" in out.columns else pd.Series("", index=out.index)
        out["_detail_src"] = base.where(base.astype(str).str.len() > 0, out["_detail_src_d"])
        out = out.drop(columns=["_detail_src_d"])
    got_src = int(out["_detail_src"].astype(str).str.len().gt(0).sum()) if "_detail_src" in out.columns else 0
    LOG.ok(f"네이버 상세 반영 — 바이라인 보유 {got_src:,}건 / 목표주가 보유 "
           f"{int(out['target_price'].notna().sum()) if 'target_price' in out.columns else 0:,}건")
    return out

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
    """PDF 원문에서 애널리스트명을 추출한다. 기본 비활성 — 켤 때만 돈다.

    ■ 왜 기본 비활성인가 (실측 근거)
      실행 로그에서 대상이 64,190건이었다. 평균 300KB 로 잡아도 19GB, 시간은 몇 시간이다.
      그런데 그 비용으로 얻는 것은 '애널리스트 이름'뿐이고, 같은 정보를 한경 리스트가
      공짜로 주고 네이버 상세 바이라인이 회수해 준다. 즉 대부분은 이미 아는 사실을
      비싸게 다시 확인하는 작업이다.
      → 켜더라도 '아직 작성자를 모르는 리포트'만 받는다. 그게 PDF 가 유일하게 답인 경우다.

    ■ 켜는 경우의 안전장치
      · 디스크 여유를 먼저 본다. 남은 공간의 절반을 넘길 것 같으면 그만큼만 받는다.
      · 청크마다 flush 하므로 상주 메모리가 작업 수와 무관하게 평평하다(약 600MB).
      · 내용해시 경로라 같은 PDF 를 두 번 저장하지 않는다(절대원칙: 저장·재호출 가능).
    """
    for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
        if c not in df.columns:
            df[c] = "" if c == "pdf_uid" else None
    if df.empty or not RESEARCH_DOWNLOAD_PDF:
        if not df.empty:
            LOG.info("PDF 원문 수집 비활성(RESEARCH_DOWNLOAD_PDF=False) — 애널리스트 식별은 "
                     "한경 리스트 작성자와 네이버 상세 바이라인으로 수행합니다. "
                     "Phase 0 게이트가 그 확보율을 판정하므로 결과가 조용히 왜곡되지 않습니다.")
        return df
    if fitz is None and pdfplumber is None:
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 원문 추출을 건너뜁니다.")
        return df

    work = df[df["pdf_url"].notna()].copy()
    # ★ 이미 작성자를 아는 리포트는 받지 않는다 — PDF 가 유일한 답인 건만 남긴다
    if "analyst_raw" in work.columns:
        unknown = work["analyst_raw"].astype(str).str.strip().eq("")
        if "_detail_src" in work.columns:
            unknown &= work["_detail_src"].astype(str).str.strip().eq("")
        n0 = len(work)
        work = work[unknown]
        LOG.info(f"PDF 대상 축소 {n0:,} → {len(work):,}건 "
                 f"(작성자를 이미 아는 리포트는 제외)")
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
    n_cached = sum(1 for k in work["report_uid"] if k in known)

    # 디스크 방어 — 실측에서 free_gb 가 nan 이라 이 점검이 무력했다(윈도우 statvfs 부재)
    free = free_gb_safe(getattr(VAULT, "root", "."))
    n_new = max(0, len(work) - n_cached)
    est_gb = n_new * 0.3 / 1024.0
    if math.isfinite(free) and est_gb > free * 0.5 and n_new:
        allow = max(0, int((free * 0.5) / (0.3 / 1024.0)))
        LOG.warn(f"PDF 예상 용량 {est_gb:.1f}GB > 여유 {free:.1f}GB 의 절반 — "
                 f"{allow:,}건으로 제한합니다. 나머지는 다음 실행에서 이어받습니다.")
        work = work.head(n_cached + allow)
    LOG.info(f"PDF 대상 {len(work):,}건 (드라이브 캐시 보유 {n_cached:,}건 / "
             f"신규 {max(0, len(work) - n_cached):,}건, 여유 {free:.1f}GB)")

    def _one(rec):
        uid, url = rec
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
            if data:
                return (uid, known[uid], data)
            # 인덱스에는 있는데 실제 파일이 없으면(드라이브 동기화 누락 등) 재수집으로 폴백한다.
        raw = http_get(url, source="hankyung" if "hankyung" in str(url) else "naver",
                       as_bytes=True, tries=2,
                       referer=HK_BASE + "/" if "hankyung" in str(url) else NV_BASE)
        if not raw or raw[:5] != b"%PDF-":
            return (uid, "", b"")          # 로그인/에러 HTML 이 200 으로 오는 케이스 방어
        return (uid, "", raw)

    jobs = list(zip(work["report_uid"].astype(str), work["pdf_url"].astype(str)))
    PDF_CHUNK = 2000
    rows, ok = [], 0
    # pymupdf 는 페이지마다 'Could not get FontBBox' 를 C 레벨에서 stderr 로 뱉는다.
    # 6만 건이면 수십만 줄이고, 주피터 IOPub 한도를 터뜨려 출력이 정지한다 → 통째로 봉인.
    n_chunk = (len(jobs) - 1) // PDF_CHUNK + 1
    for k0 in range(0, len(jobs), PDF_CHUNK):
        chunk = jobs[k0:k0 + PDF_CHUNK]
        # ★ 봉인 범위를 '수다를 떠는 구간'으로만 좁힌다. VAULT.flush 까지 감싸면 저장 실패
        #   경고가 화면에서 사라진다 — 캐시가 안 남는 사고를 눈으로 못 보게 되는 셈이다.
        with quiet_fds():
            res = pmap_io(_one, chunk, workers=min(N_WORKERS_IO, 10), desc="", quiet=True)
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
        LOG.info(f"PDF {k0 // PDF_CHUNK + 1}/{n_chunk} 청크 완료 — 누적 확보 {ok:,}건")
    VAULT.flush("shared")
    LOG.ok(f"PDF 확보 {ok:,}/{len(jobs):,}건 — 공용 인덱스에 저장(내용해시 중복제거 적용)")
    if not rows:
        return df
    ext = pd.DataFrame(rows)
    note_new_data("research_pdf_fields", len(ext), "shared", "research", "pdf")
    persist("research_pdf_fields", ext, scope="shared", domain="research", source="pdf extract")
    for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
        if c in df.columns:
            df = df.drop(columns=[c])
    df = df.merge(ext, on="report_uid", how="left")
    return df
