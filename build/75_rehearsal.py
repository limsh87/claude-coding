

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  실경로 리허설 (REHEARSAL) — 수집 함수를 '진짜로' 실행해 본다                        ║
# ║                                                                                          ║
# ║  왜 이 계층이 생겼는가:                                                                    ║
# ║    합성 스모크(§80)는 make_synthetic() 이 만든 완성 패널을 곧바로 주입한다. 즉               ║
# ║    build_security_master · fetch_prices · tidy_financials · hankyung_collect 같은          ║
# ║    실제 수집·정제 함수는 단 한 줄도 실행되지 않는다.                                        ║
# ║    실제로 이 공백 때문에 계약 17건 + 스모크를 전부 통과한 빌드가 실행 2분 만에               ║
# ║    build_security_master 의 중복 컬럼 한 줄로 죽었다.                                      ║
# ║                                                                                          ║
# ║  그래서 여기서는 네트워크 계층만 가짜로 바꾸고(HTTP·pykrx·FDR), 그 위의 수집·정제           ║
# ║  로직은 실물 그대로 돌린다. 각 함수에 대해 네 가지를 먹인다:                                 ║
# ║    ① 정상 응답  ② 빈 응답  ③ 깨진 응답  ④ 기대 컬럼이 빠진 응답                            ║
# ║  전부 '예외 없이' 통과해야 하고, 정상 응답에서는 실제로 값이 나와야 한다.                    ║
# ║                                                                                          ║
# ║  수 초면 끝나고 네트워크·키가 필요 없다. 실수집 전에 반드시 통과해야 한다.                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []

# 전략별 추가 리허설 훅. 시그니처: fn(G: dict, sec: pd.DataFrame, corps: List[str],
# months: pd.DatetimeIndex) -> None.  가짜 네트워크가 이미 물려 있는 안쪽에서 호출된다.
# 코어만 빌드하면 빈 리스트라 동작이 바뀌지 않는다(순수 추가).
REHEARSAL_HOOKS: List[Callable] = []


def _rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    """리허설 1건 실행. 예외는 실패, 정상응답 0행도 (기대했다면) 실패."""
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        REHEARSAL_RESULTS.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0,
            "err": "" if ok else "정상 응답을 줬는데 결과가 0행입니다(파싱 실패 가능성)",
            "note": note})
        return out
    except Exception as e:                                          # noqa
        REHEARSAL_RESULTS.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0,
            "err": f"{type(e).__name__}: {str(e)[:200]}", "note": note,
            "tb": traceback.format_exc()})
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────────────────────
def _fx_fdr_listing_csv(n: int = 40) -> bytes:
    # FDR GitHub 캐시 실제 스키마 (ChagesRatio 오타는 업스트림 그대로)
    rows = ["，Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"
            .replace("，", "")]
    for i in range(n):
        code = f"{i+1:06d}"
        rows.append(f"{i},{code},KR7{code}003,합성{i+1:03d},"
                    f"{'KOSPI' if i%2 else 'KOSDAQ'},,10000,0.5,1000000000,100000,"
                    f"{'STK' if i%2 else 'KSQ'}")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_fdr_delisting_csv(n: int = 30) -> bytes:
    rows = ["Symbol,Name,Market,SecuGroup,Kind,DelistingDate,ToSymbol,ToName,Reason"]
    for i in range(n):
        # 앞 20건은 정상 6자리, 뒤 10건은 비표준 코드(ETF/ELW/스팩 등) — 탈락 집계 검증용
        code = f"{900000+i:06d}" if i < 20 else f"KR{i:08d}"
        rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,"
                    f"{2017+(i%8)}-0{1+(i%9)}-15,,,상장폐지")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_kind_html(n: int = 30) -> bytes:
    # KIND 는 HTML 표이고 종목코드가 '정수'로 와서 앞자리 0 이 날아간다
    head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
            "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
    body = "".join(
        f"<tr><td>합성{i+1:03d}</td><td>{i+1}</td><td>화학</td><td>제품</td>"
        f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td><td>서울</td></tr>"
        for i in range(n))
    return (head + body + "</table>").encode("euc-kr")


def _fx_dart_fnltt(corp: str, year: int) -> dict:
    def row(sj, aid, anm, amt):
        return {"rcept_no": f"{year}0331000001", "reprt_code": "11011", "bsns_year": str(year),
                "corp_code": corp, "sj_div": sj, "sj_nm": sj, "account_id": aid,
                "account_nm": anm, "thstrm_amount": amt, "frmtrm_amount": amt, "ord": "1"}
    return {"status": "000", "message": "정상", "list": [
        row("IS", "ifrs-full_Revenue", "매출액", "1,234,567,000,000"),
        row("IS", "ifrs-full_CostOfSales", "매출원가", "900,000,000,000"),
        row("IS", "dart_OperatingIncomeLoss", "영업이익", "120,000,000,000"),
        row("IS", "ifrs-full_ProfitLoss", "당기순이익", "90,000,000,000"),
        row("IS", "-표준계정코드 미사용-", "경상연구개발비", "30,000,000,000"),
        row("IS", "ifrs-full_IncomeTaxExpense", "법인세비용", "20,000,000,000"),
        row("IS", "ifrs-full_ProfitLossBeforeTax", "법인세비용차감전순이익", "110,000,000,000"),
        row("IS", "dart_SellingGeneralAdministrativeExpenses", "판매비와관리비", "200,000,000,000"),
        row("BS", "ifrs-full_Inventories", "재고자산", "150,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권", "180,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentPayables", "매입채무및기타채무", "120,000,000,000"),
        row("BS", "ifrs-full_Assets", "자산총계", "3,000,000,000,000"),
        row("BS", "ifrs-full_Liabilities", "부채총계", "1,200,000,000,000"),
        row("BS", "ifrs-full_Equity", "자본총계", "1,800,000,000,000"),
        row("BS", "ifrs-full_PropertyPlantAndEquipment", "유형자산", "800,000,000,000"),
        row("BS", "ifrs-full_IntangibleAssetsOtherThanGoodwill", "무형자산", "100,000,000,000"),
        row("BS", "dart_ContractLiabilities", "계약부채", "50,000,000,000"),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "140,000,000,000"),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득", "-60,000,000,000"),
        row("CF", "dart_DepreciationAndAmortisationExpense", "감가상각비와상각비", "50,000,000,000"),
        row("CF", "ifrs-full_DividendsPaid", "배당금지급", "-15,000,000,000"),
        row("CF", "dart_PaymentsToAcquireOrRedeemEntitysShares", "자기주식의 취득", "-8,000,000,000"),
        row("CF", "ifrs-full_ProceedsFromBorrowings", "차입금의 증가", "40,000,000,000"),
    ]}


def _fx_dart_emp(corp: str, year: int) -> dict:
    # 사업부문 × 성별로 쪼개진 실제 스키마 + '합계' 소계 행(이중계상 방지 검증)
    def r(bbm, sex, sm, tot):
        return {"rcept_no": f"{year}0331000001", "corp_code": corp, "fo_bbm": bbm,
                "sexdstn": sex, "sm": sm, "fyer_salary_totamt": tot,
                "jan_salary_am": "70,000,000"}
    return {"status": "000", "list": [
        r("반도체", "남", "1,200", "96,000,000,000"),
        r("반도체", "여", "300", "21,000,000,000"),
        r("디스플레이", "남", "500", "40,000,000,000"),
        r("디스플레이", "여", "100", "7,000,000,000"),
        r("합계", "합계", "2,100", "164,000,000,000"),
    ]}


def _fx_dart_list(bgn: str) -> dict:
    y = bgn[:4]
    return {"status": "000", "page_no": 1, "total_page": 1, "list": [
        {"corp_code": "C0000001", "corp_name": "합성001", "stock_code": "000001",
         "rcept_no": f"{y}0410000001", "rcept_dt": f"{y}0410",
         "report_nm": "주요사항보고서(자기주식취득결정)", "flr_nm": "합성001", "corp_cls": "Y"},
        {"corp_code": "C0000002", "corp_name": "합성002", "stock_code": "000002",
         "rcept_no": f"{y}0412000002", "rcept_dt": f"{y}0412",
         "report_nm": "주요사항보고서(유상증자결정)", "flr_nm": "합성002", "corp_cls": "Y"},
        {"corp_code": "C0000003", "corp_name": "합성003", "stock_code": "000003",
         "rcept_no": f"{y}0415000003", "rcept_dt": f"{y}0415",
         "report_nm": "사업보고서 (2023.12)", "flr_nm": "합성003", "corp_cls": "Y"},
    ]}


def _fx_hankyung_html(n: int = 12) -> str:
    hdr = ("<tr>" + "".join(f"<th>{h}</th>" for h in
           ["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
            "기업정보", "차트", "첨부"]) + "</tr>")
    rows = []
    for i in range(n):
        idx = 500000 + i
        rows.append(
            "<tr>"
            f"<td>2024-0{1+(i%9)}-15</td>"
            f"<td class='text_l'><a href='/analysis/downpdf?report_idx={idx}'>"
            f"합성{i+1:03d}({i+1:06d}) 실적 개선 전망</a></td>"
            f"<td class='text_r'>{(i+5)*10000:,}</td><td>Buy</td>"
            f"<td>애널{i%7:02d}</td><td>{'미래에셋대우' if i%2 else '하나금융투자'}</td>"
            f"<td>-</td><td>-</td>"
            f"<td><a href='/analysis/downpdf?report_idx={idx}'>PDF</a></td></tr>")
    return f"<div id='contents'><div class='table_style01'><table>{hdr}{''.join(rows)}</table></div></div>"


def _fx_naver_research_html(n: int = 12) -> str:
    hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
           "<th>작성일</th><th>조회수</th></tr>")
    rows = []
    for i in range(n):
        rows.append(
            "<tr>"
            f"<td style='padding-left:10'><a class='stock_item' href='/item/main.naver?code={i+1:06d}' "
            f"title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
            f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>실적 개선 전망</a></td>"
            f"<td>{'KB증권' if i%2 else '신한금융투자'}</td>"
            f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
            f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
            f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
    nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
           "<a href='/research/company_list.naver?&amp;page=3'>맨뒤</a></td></tr></table>")
    return (f"<div id='contentarea_left'><div class='box_type_m'>"
            f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")


def _fx_nps_json(page: int) -> dict:
    items = [{"wkplNm": f"합성{i+1:03d}", "bzowrRgstNo": f"{1000000000+i}",
              "jnngpCnt": str(100 + i * 7), "crrmmNtcAmt": str((100 + i * 7) * 300000),
              "nwAcqzrCnt": "5", "lssJnngpCnt": "3", "wkplRoadNmDtlAddr": "서울시 강남구",
              "ldongAddrMgplDgCd": "11", "vldtVlKrnNm": "제조업", "seq": str(i)}
             for i in range(40)]
    return {"response": {"header": {"resultCode": "00"},
                         "body": {"totalCount": 40, "pageNo": page, "numOfRows": 1000,
                                  "items": {"item": items if page == 1 else []}}}}


def _fx_g2b_json() -> dict:
    items = [{"bizno": f"{1000000000+i}", "bidwinnrNm": f"합성{i+1:03d}",
              "sucsfbidAmt": str(1_000_000_000 + i * 1_000_000),
              "presmptPrce": str(1_200_000_000 + i * 1_000_000),
              "sucsfbidRate": str(85 + (i % 10)), "dminsttNm": "조달청",
              "prdctClsfcNo": f"{4000+i}"} for i in range(25)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_customs_json() -> dict:
    items = [{"expDlr": str(1_000_000 + i * 1000), "expWgt": str(500_000 + i * 500),
              "statCd": ["US", "DE", "VN", "CN"][i % 4]} for i in range(8)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_pdf() -> bytes:
    return b"%PDF-1.4\n% synthetic fixture\n%%EOF\n"


# ── 라우팅 ──────────────────────────────────────────────────────────────────────────────────
class _FixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크. mode 로 정상/빈/깨짐/컬럼누락을 전환한다."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: Counter = Counter()

    def _m(self, kind: str):
        self.hits[kind] += 1

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u = str(url)
        p = params or {}
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return b"\x00\x01garbage" if as_bytes else "<html><body>오류</body></html>"

        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                self._m("fdr_delisting")
                return _fx_fdr_delisting_csv()
            self._m("fdr_listing")
            if self.mode == "missingcol":
                return b"\xef\xbb\xbf,Foo,Bar\n0,1,2\n"
            return _fx_fdr_listing_csv()
        if "kind.krx.co.kr" in u:
            self._m("kind")
            return _fx_kind_html()
        if "corpCode.xml" in u:
            self._m("dart_corpcode")
            buf = io.BytesIO()
            xml = "<result>" + "".join(
                f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
                f"<stock_code>{i+1:06d}</stock_code><modify_date>20240101</modify_date></list>"
                for i in range(40)) + "</result>"
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml", xml.encode("utf-8"))
            return buf.getvalue()
        if "document.xml" in u:
            self._m("dart_document")
            buf = io.BytesIO()
            body = ("<?xml version='1.0' encoding='euc-kr'?><DOCUMENT>"
                    "II. 사업의 내용 당사는 반도체 소재를 제조합니다. " * 30 +
                    "위험요인 환율 변동 위험이 존재합니다. " * 30 +
                    "우발부채 계류 중인 소송은 없습니다. " * 20 + "</DOCUMENT>")
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("doc.xml", body.encode("euc-kr"))
            return buf.getvalue()
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                self._m("hk_pdf")
                return _fx_pdf()
            self._m("hankyung")
            page = int(p.get("now_page", 1) or 1)
            return _fx_hankyung_html() if page == 1 else "<td class='no_data'>데이터가 없습니다</td>"
        if "finance.naver.com/research" in u:
            self._m("naver_research")
            page = int(p.get("page", 1) or 1)
            if page <= 2:
                return _fx_naver_research_html()
            return "<div id='contentarea_left'><table class='type_1'></table></div>"
        if "finance.naver.com/item/main" in u:
            self._m("naver_item")
            return ('<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>')
        if "stock.pstatic.net" in u:
            self._m("naver_pdf")
            return _fx_pdf()
        if "siseJson" in u:
            self._m("naver_chart")
            rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
            d = as_ts("2016-05-02")
            for i in range(2600):
                d2 = d + pd.Timedelta(days=i)
                if d2.weekday() >= 5:
                    continue
                rows.append(f"['{d2:%Y%m%d}',10000,10100,9900,10050,120000,5.0]")
            return "[" + ",".join(rows) + "]"
        self._m("other")
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "opendart" in u and "fnlttSinglAcntAll" in u:
            self._m("dart_fnltt")
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return _fx_dart_fnltt(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "empSttus" in u:
            self._m("dart_emp")
            return _fx_dart_emp(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "list.json" in u:
            self._m("dart_list")
            return _fx_dart_list(str(p.get("bgn_de", "20200101")))
        if "NpsBplcInfoInqireService" in u:
            self._m("nps")
            return _fx_nps_json(int(p.get("pageNo", 1) or 1))
        if "ScsbidInfoService" in u:
            self._m("g2b")
            return _fx_g2b_json() if int(p.get("pageNo", 1) or 1) == 1 else {"response": {"body": {"items": []}}}
        if "nitemtrade" in u:
            self._m("customs")
            return _fx_customs_json()
        if "stockSecurity/researches" in u:
            self._m("naver_api")
            return []                       # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        self._m("other_json")
        return None


def run_rehearsal(strict: bool = True) -> bool:
    """실제 수집·정제 함수를 픽스처로 전부 실행한다. 네트워크·키 불필요."""
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다")
    REHEARSAL_RESULTS.clear()
    G = globals()
    saved = {k: G.get(k) for k in ("http_get", "http_json", "http_post",
                                   "fdr", "pykrx_stock", "yf", "DART_API_KEY",
                                   "DATA_GO_KR_KEY", "CUSTOMS_API_KEY", "RUN_MODE",
                                   "RESEARCH_DOWNLOAD_PDF", "UNIVERSE_SNAPSHOT_FREQ")}
    tmp = tempfile.mkdtemp(prefix="tcd_rehearsal_")
    saved_vault, saved_budget = G.get("VAULT"), G.get("DBUDGET")
    months = month_range("2016-08-01", "2026-07-31")

    try:
        # 네트워크·외부 라이브러리 차단 + 키 주입 (키가 있어야 해당 분기가 실행된다)
        net = _FixtureNet("ok")
        G["http_get"] = net.get
        G["http_json"] = net.json
        G["http_post"] = lambda *a, **k: ""
        G["fdr"] = None
        G["pykrx_stock"] = None            # 스냅샷 경로는 '없을 때' 폴백을 검증
        G["yf"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["DATA_GO_KR_KEY"] = "REHEARSAL"
        G["CUSTOMS_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["VAULT"] = Vault(tmp, "REHEARSAL")
        G["DBUDGET"] = DartBudget()

        # ── ① 유니버스 ────────────────────────────────────────────────────────────────────
        snaps = _rh("fetch_pykrx_snapshots(pykrx 없음→폴백)",
                    lambda: fetch_pykrx_snapshots(months), expect_rows=False,
                    note="pykrx 미설치 상황에서 죽지 않고 빈 결과를 돌려줘야 한다")
        _rh("fetch_fdr_listing", fetch_fdr_listing)
        _rh("fetch_fdr_delisting", fetch_fdr_delisting)
        _rh("fetch_kind_listing", fetch_kind_listing)
        _rh("fetch_dart_corpcode", fetch_dart_corpcode)
        sec = _rh("build_security_master ★이번 크래시 지점",
                  lambda: build_security_master(snaps if snaps is not None else pd.DataFrame(
                      columns=["snap_date", "code", "market"])),
                  note="중복 컬럼 → groupby.agg 폭발이 여기서 났다")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{i+1:06d}" for i in range(40)],
                                "name": [f"합성{i+1:03d}" for i in range(40)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(40)],
                                "listing_date": as_ts("2010-01-01"),
                                "delisting_date": pd.NaT, "sector_src": "fx", "src": "fx"})

        # ── ② 가격 ────────────────────────────────────────────────────────────────────────
        codes = sec["code"].dropna().tolist()[:12]
        px = _rh("fetch_prices(네이버 차트 폴백)",
                 lambda: fetch_prices(codes, "2016-05-01", "2026-07-31"),
                 note="FDR/pykrx 없이 네이버 경로만으로 동작해야 한다")
        if px is not None and len(px):
            _rh("build_price_panel", lambda: build_price_panel(px, months))
        _rh("fetch_investor_flows(pykrx 없음)",
            lambda: fetch_investor_flows(codes, "2016-08-01", "2026-07-31"), expect_rows=False)

        # ── ③ DART ────────────────────────────────────────────────────────────────────────
        corps = sec["corp_code"].dropna().astype(str).tolist()[:6]
        years = [2019, 2020, 2021]
        fs = _rh("fetch_dart_financials", lambda: fetch_dart_financials(corps, years))
        if fs is not None and len(fs):
            _rh("tidy_financials", lambda: tidy_financials(fs))
        _rh("fetch_dart_employees", lambda: fetch_dart_employees(corps, years),
            note="사업부문×성별 분해 + '합계' 소계행 이중계상 방지")
        dis = _rh("fetch_dart_disclosures",
                  lambda: fetch_dart_disclosures("2019-01-01", "2019-06-30"))

        # ── ④ 리서치 원장 ─────────────────────────────────────────────────────────────────
        hk = _rh("hankyung_collect", lambda: hankyung_collect("2024-01-01", "2024-12-31"))
        nv = _rh("naver_collect", lambda: naver_collect("2024-01-01", "2024-12-31",
                                                        cats=("company",)))
        if nv is not None and len(nv):
            _rh("naver_enrich_detail", lambda: naver_enrich_detail(nv, limit=5),
                expect_rows=False)
        frames = [x for x in (hk, nv) if x is not None and len(x)]
        rep = _rh("build_report_master(다중소스 병합)",
                  lambda: build_report_master(frames, sec)) if frames else None
        if rep is not None and len(rep):
            rep2 = _rh("download_pdfs", lambda: download_pdfs(rep, cap_per_month=3))
            A_L = _rh("build_analyst_ledger",
                      lambda: build_analyst_ledger(rep2 if rep2 is not None else rep),
                      expect_rows=False)
            if A_L is not None:
                A, L = A_L
                _rh("audit_linkage", lambda: (audit_linkage(rep, A, L) or [1]),
                    expect_rows=False)
                _rh("build_consensus_panel", lambda: build_consensus_panel(L, months),
                    expect_rows=False)

        # ── ⑤ 팩 전용 수집 ────────────────────────────────────────────────────────────────
        if "fetch_nps_workplaces" in G:
            N = _rh("fetch_nps_workplaces", lambda: fetch_nps_workplaces(months[:3]))
            if N is not None and len(N):
                M = _rh("resolve_nps_to_corp",
                        lambda: resolve_nps_to_corp(N, sec, pd.DataFrame())[0])
                if M is not None and len(M):
                    _rh("build_nps_panel", lambda: build_nps_panel(N, M, pd.DataFrame(), months),
                        expect_rows=False)
        if "fetch_procurement" in G:
            _rh("fetch_procurement", lambda: fetch_procurement(months[:2]))
        if "fetch_customs_trade" in G:
            _rh("fetch_customs_trade",
                lambda: fetch_customs_trade(months[:2], ["3901000000", "3902000000"]))
        if "fetch_dart_documents" in G and dis is not None and len(dis):
            T = _rh("fetch_dart_documents", lambda: fetch_dart_documents(dis, sec, max_docs=5),
                    expect_rows=False)
            if T is not None and len(T):
                _rh("build_text_similarity", lambda: build_text_similarity(T),
                    expect_rows=False)

        # ── ⑤-b 전략별 추가 리허설 (가짜 네트워크가 물려 있는 상태에서 실행) ──────────────
        for _hook in list(REHEARSAL_HOOKS):
            try:
                _hook(G, sec, corps, months)
            except Exception as _e:                                  # noqa
                REHEARSAL_RESULTS.append({
                    "name": f"[훅] {getattr(_hook, '__name__', 'hook')}", "ok": False,
                    "rows": -1, "sec": 0.0, "err": f"{type(_e).__name__}: {_e}",
                    "note": "", "tb": traceback.format_exc()})

        # ── ⑥ 이상 응답 내성 (빈/깨짐/컬럼누락) ───────────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = _FixtureNet(mode)
            G["http_get"], G["http_json"] = bad.get, bad.json
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"tcd_rh_{mode}_"), "REHEARSAL")
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing),
                              ("fetch_dart_corpcode", fetch_dart_corpcode)):
                _rh(f"[{label}] {fname}", fn, expect_rows=False,
                    note="예외 없이 빈 결과를 돌려줘야 한다")
            _rh(f"[{label}] fetch_dart_financials",
                lambda: fetch_dart_financials(corps, [2020]), expect_rows=False)
            _rh(f"[{label}] hankyung_collect",
                lambda: hankyung_collect("2024-01-01", "2024-03-31"), expect_rows=False)
            _rh(f"[{label}] build_report_master(빈 입력)",
                lambda: build_report_master([], sec), expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"], G["DBUDGET"] = saved_vault, saved_budget
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in REHEARSAL_RESULTS if r["ok"])
    LOG.table([[r["name"], "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 62)]
               for r in REHEARSAL_RESULTS],
              ["실경로 함수", "판정", "결과", "소요", "비고"],
              ["l", "c", "r", "r", "l"], maxw=64)
    fails = [r for r in REHEARSAL_RESULTS if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(REHEARSAL_RESULTS)}건 실패")
        for r in fails[:4]:
            LOG.banner(f"✘ 리허설 실패: {r['name']}", r["err"])
            for ln in str(r.get("tb", "")).rstrip().split("\n")[-10:]:
                _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"이 검사는 '수집 함수가 진짜 데이터 모양에서 도는지'를 보는 것이라, "
                f"여기서 막는 것이 몇 시간 뒤 L1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(REHEARSAL_RESULTS)}건 통과 — "
           f"수집·정제 함수가 실제 데이터 모양에서 정상 동작합니다.")
    return True
