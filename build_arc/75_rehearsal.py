

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  실경로 리허설 — 수집 함수를 '진짜로' 실행해 본다                                    ║
# ║                                                                                          ║
# ║  합성 스모크(80)는 완성된 패널을 주입한다. 즉 build_security_master · fetch_prices ·        ║
# ║  fetch_arc_documents · hankyung_collect 같은 실제 수집·정제 함수는 한 줄도 실행되지 않는다. ║
# ║  실제로 계약 검정 + 스모크를 전부 통과한 빌드가 실행 2분 만에 수집부 한 줄 때문에 죽은      ║
# ║  전례가 있어 이 계층이 생겼다.                                                              ║
# ║                                                                                          ║
# ║  여기서는 네트워크 계층만 가짜로 바꾸고(HTTP·pykrx·FDR), 그 위 수집·정제 로직은 실물 실행.   ║
# ║  각 함수에 네 가지를 먹인다: ① 정상 ② 빈 응답 ③ 깨진 응답 ④ 기대 컬럼 누락                  ║
# ║  전부 '예외 없이' 통과해야 하고, 정상 응답에서는 실제로 값이 나와야 한다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []


def _arh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        REHEARSAL_RESULTS.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0,
            "err": "" if ok else "정상 응답인데 결과가 0행입니다(파싱 실패 가능성)", "note": note})
        return out
    except Exception as e:                                        # noqa
        REHEARSAL_RESULTS.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0,
            "err": f"{type(e).__name__}: {str(e)[:200]}", "note": note,
            "tb": traceback.format_exc()})
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────────────────────
def _afx_fdr_listing(n: int = 40) -> bytes:
    rows = ["Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"]
    for i in range(n):
        code = f"{(i+1)*10:06d}"          # 실제 보통주처럼 끝자리 0
        rows.append(f"{code},KR7{code}003,합성{i+1:03d},{'KOSPI' if i%2 else 'KOSDAQ'},,"
                    f"10000,0.5,1000000000,100000,{'STK' if i%2 else 'KSQ'}")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _afx_fdr_delisting(n: int = 30) -> bytes:
    rows = ["Symbol,Name,Market,SecuGroup,Kind,DelistingDate,ToSymbol,ToName,Reason"]
    for i in range(n):
        code = f"{900000+i:06d}" if i < 20 else f"KR{i:08d}"
        rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,{2017+(i%8)}-0{1+(i%9)}-15,,,상장폐지")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _afx_kind(n: int = 30) -> bytes:
    head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
            "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
    body = "".join(f"<tr><td>합성{i+1:03d}</td><td>{i+1}</td><td>화학</td><td>제품</td>"
                   f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td>"
                   f"<td>서울</td></tr>" for i in range(n))
    return (head + body + "</table>").encode("euc-kr")


def _afx_corpcode(n: int = 40) -> bytes:
    buf = io.BytesIO()
    xml = "<result>" + "".join(
        f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
        f"<stock_code>{(i+1)*10:06d}</stock_code><modify_date>20240101</modify_date></list>"
        for i in range(n)) + "</result>"
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buf.getvalue()


def _afx_fnltt(corp: str, year: int) -> dict:
    def row(sj, aid, anm, amt):
        return {"rcept_no": f"{year+1}0331000001", "reprt_code": "11011",
                "bsns_year": str(year), "corp_code": corp, "sj_div": sj, "sj_nm": sj,
                "account_id": aid, "account_nm": anm, "thstrm_amount": amt,
                "frmtrm_amount": amt, "ord": "1"}
    return {"status": "000", "message": "정상", "list": [
        row("IS", "ifrs-full_Revenue", "매출액", "1,234,567,000,000"),
        row("IS", "ifrs-full_CostOfSales", "매출원가", "900,000,000,000"),
        row("IS", "dart_OperatingIncomeLoss", "영업이익", "120,000,000,000"),
        row("IS", "ifrs-full_ProfitLoss", "당기순이익", "90,000,000,000"),
        row("IS", "-표준계정코드 미사용-", "경상연구개발비", "30,000,000,000"),
        row("BS", "ifrs-full_Inventories", "재고자산", "150,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권",
            "180,000,000,000"),
        row("BS", "ifrs-full_Assets", "자산총계", "3,000,000,000,000"),
        row("BS", "ifrs-full_Liabilities", "부채총계", "1,200,000,000,000"),
        row("BS", "ifrs-full_Equity", "자본총계", "1,800,000,000,000"),
        row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "300,000,000,000"),
        row("BS", "ifrs-full_PropertyPlantAndEquipment", "유형자산", "800,000,000,000"),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름",
            "140,000,000,000"),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득",
            "-60,000,000,000"),
    ]}


def _afx_emp(corp: str, year: int) -> dict:
    def r(bbm, sex, sm, tot):
        return {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "fo_bbm": bbm,
                "sexdstn": sex, "sm": sm, "fyer_salary_totamt": tot,
                "jan_salary_am": "70,000,000"}
    return {"status": "000", "list": [
        r("반도체", "남", "1,200", "96,000,000,000"), r("반도체", "여", "300", "21,000,000,000"),
        r("합계", "합계", "1,500", "117,000,000,000")]}


def _afx_shares(corp: str, year: int) -> dict:
    return {"status": "000", "list": [
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "보통주",
         "isu_stock_totqy": "10,000,000", "now_to_isu_stock_totqy": "10,000,000",
         "tesstk_co": "100,000", "istc_totqy": "10,000,000"},
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "우선주",
         "isu_stock_totqy": "1,000,000", "now_to_isu_stock_totqy": "1,000,000",
         "tesstk_co": "0", "istc_totqy": "1,000,000"},
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "합계",
         "isu_stock_totqy": "11,000,000", "now_to_isu_stock_totqy": "11,000,000",
         "tesstk_co": "100,000", "istc_totqy": "11,000,000"}]}


def _afx_audit(corp: str, year: int) -> dict:
    emph = "계속기업으로서의 존속능력에 대한 불확실성" if int(year) % 3 == 0 else ""
    return {"status": "000", "list": [
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "bsns_year": str(year),
         "adtor": "합성회계법인", "adt_opinion": "적정", "emphs_matter": emph,
         "core_adt_matter": "수익인식"}]}


def _afx_dart_list(bgn: str, ty: str) -> dict:
    y = int(bgn[:4])
    m = int(bgn[4:6])
    items = []
    if ty == "A" and m == 3:
        for i in range(1, 4):
            items.append({"corp_code": f"C{i:07d}", "corp_name": f"합성{i:03d}",
                          "stock_code": f"{i:06d}", "rcept_no": f"{y}0320{i:06d}",
                          "rcept_dt": f"{y}0320",
                          "report_nm": f"사업보고서 ({y-1}.12)", "flr_nm": f"합성{i:03d}",
                          "corp_cls": "Y"})
    if ty == "B" and m == 7:
        items.append({"corp_code": "C0000001", "corp_name": "합성001", "stock_code": "000001",
                      "rcept_no": f"{y}0710000001", "rcept_dt": f"{y}0710",
                      "report_nm": "주요사항보고서(전환사채발행결정)", "flr_nm": "합성001",
                      "corp_cls": "Y"})
        items.append({"corp_code": "C0000002", "corp_name": "합성002", "stock_code": "000002",
                      "rcept_no": f"{y}0711000002", "rcept_dt": f"{y}0711",
                      "report_nm": "단일판매ㆍ공급계약체결", "flr_nm": "합성002",
                      "corp_cls": "Y"})
    return {"status": "000" if items else "013", "page_no": 1, "total_page": 1, "list": items}


# ★ 실제 사업보고서는 섹션당 수천~수만 자다. 픽스처가 너무 짧으면 fetch_arc_documents 의
#   '본문 최소 길이' 와 섹션 최소 길이 필터에 걸려 0행이 되고, 리허설이 실제 경로를 검증하지
#   못한다(초기 빌드에서 실제로 이 함정에 걸렸다). 문단을 반복해 현실적인 분량을 만든다.
_AFX_SECTIONS = [
    ("I. 회사의 개요",
     "당사는 {year}년 12월 31일 현재 제{gi}기 사업연도를 마감하였습니다. "
     "합성전자 주식회사는 {year}년 3월 20일에 본 보고서를 제출하였습니다. "
     "자본금은 {a} 백만원이며 발행주식총수는 {b} 주입니다. "
     "본점 소재지는 충청북도 청주시이며 지점은 {f} 개를 운영하고 있습니다. "),
    ("II. 사업의 내용",
     "당사는 반도체 소재를 제조하여 국내외에 판매하고 있습니다. {biz} "
     "주요 원재료 매입액은 {c} 백만원이며 생산능력은 연간 {d} 톤입니다. "
     "당사는 {year}년 중 유형자산 {e} 백만원을 취득하였습니다. "
     "{year}년 {mm}월 특허 {f} 건을 등록하였습니다. "
     "주요 매출처는 국내 대형 반도체 제조사이며 수출 비중은 {f} 퍼센트입니다. "
     "생산 공정은 정제, 배합, 포장의 세 단계로 구성되어 있습니다. "),
    ("III. 재무에 관한 사항",
     "당기 매출액은 {c} 백만원이며 영업이익은 {a} 백만원입니다. "
     "<table><tr><td>매출액</td><td>{c}</td></tr><tr><td>영업이익</td><td>{a}</td></tr></table> "
     "부채비율은 안정적인 수준을 유지하고 있습니다. "),
    ("VII. 이사의 경영진단 및 분석의견",
     "{mda} 당기 매출은 {c} 백만원으로 전기 대비 증가하였습니다. "
     "원가율은 전기 대비 소폭 상승하였으며 판매관리비는 통제 범위 내에서 관리되고 있습니다. "
     "향후 자금 조달 계획과 유동성 관리 방안을 지속적으로 점검하고 있습니다. "
     "부문별 실적은 소재 부문이 전체 매출의 대부분을 차지하고 있습니다. "),
    ("VIII. 임원 및 직원 등에 관한 사항",
     "직원 수는 {g} 명이며 연간 급여총액은 {a} 백만원입니다. "
     "{year}년 중 연구개발 인력 {f} 명을 신규 채용하였습니다. "
     "임원은 사내이사 {f} 명과 사외이사 {f} 명으로 구성되어 있습니다. "
     "평균 근속연수는 {f} 년이며 이직률은 안정적으로 관리되고 있습니다. "),
    ("IX. 계열회사 등에 관한 사항",
     "당사의 계열회사는 총 {f} 개사입니다. 지배구조는 안정적으로 유지되고 있습니다. "
     "{year}년 중 종속기업 지분을 {d} 백만원에 취득하였습니다. "
     "최대주주 및 특수관계인의 지분율은 {f} 퍼센트입니다. "),
    ("X. 대주주 등과의 거래내용",
     "특수관계자와의 매출 거래는 {d} 백만원이며 매입 거래는 {e} 백만원입니다. "
     "거래 조건은 제3자와의 거래와 동일한 기준을 적용하고 있습니다. "),
    ("XI. 그 밖에 투자자 보호를 위하여 필요한 사항",
     "제재현황: 해당사항 없습니다. "
     "우발부채 등: 계류 중인 소송사건은 {f} 건이며 소송가액은 {d} 백만원입니다. "
     "지급보증 잔액은 {e} 백만원입니다. "
     "사업위험: 환율 변동과 원자재 가격 상승 위험이 존재합니다. {risk} "
     "투자위험요소: 전방 산업 경기 변동에 따라 실적이 영향을 받을 수 있습니다. "),
]


def _afx_doc_body(y: int, newer: bool) -> str:
    fmt = dict(
        year=y, gi=y - 1990, mm=(y % 12) + 1,
        a=f"{1000+y:,}", b=f"{10_000_000+y*13:,}", c=f"{1_234_567+y*31:,}",
        d=f"{98_765+y*7:,}", e=f"{45_678+y*11:,}", f=(y % 9) + 1, g=f"{450+y%50:,}",
        biz=("이차전지 부품 사업을 신규로 개시하였으며 관련 매출이 발생하였습니다."
             if newer else "주력 제품은 실리콘 웨이퍼용 소재입니다."),
        mda=("영업환경 악화로 수익성이 하락하였으며 원가 절감 계획을 시행하고 있습니다."
             if newer else "안정적인 수요를 바탕으로 견조한 실적을 유지하였습니다."),
        risk=("경쟁사 진입으로 가격 경쟁이 심화되고 있습니다." if newer else
              "주요 고객사와의 장기 공급 계약으로 위험을 완화하고 있습니다."))
    out = ["<?xml version='1.0' encoding='euc-kr'?><DOCUMENT><TITLE>사업보고서</TITLE>"]
    for head, para in _AFX_SECTIONS:
        out.append(head)
        out.append((para.format(**fmt) + "\n") * 6)      # 섹션당 현실적 분량 확보
    out.append("</DOCUMENT>")
    return "\n".join(out)


def _afx_document(rcept_no: str) -> bytes:
    """전년/당년 두 해치. 당년본은 (a) 숫자·날짜만 바뀐 섹션과 (b) 서술이 바뀐 섹션을 나눈다."""
    y = int(str(rcept_no)[:4]) if str(rcept_no)[:4].isdigit() else 2020
    newer = (y % 2 == 0)
    body = _afx_doc_body(y, newer)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # ★ 본보고서 + 감사보고서 + 첨부 3개 엔트리. 첫 엔트리만 읽으면 내용이 소실되는 회귀를 잡는다.
        z.writestr("00_main.xml", body.encode("euc-kr"))
        z.writestr("01_audit.xml", ("<?xml version='1.0' encoding='euc-kr'?><DOC>"
                                    "감사의견 적정. 강조사항 없음.</DOC>").encode("euc-kr"))
        z.writestr("02_fs.xml", ("<?xml version='1.0' encoding='euc-kr'?><DOC>"
                                 "<table><tr><td>자산</td><td>1,000</td></tr></table>"
                                 "</DOC>").encode("euc-kr"))
    return buf.getvalue()


def _afx_hankyung(n: int = 12) -> str:
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
    return (f"<div id='contents'><div class='table_style01'><table>{hdr}"
            f"{''.join(rows)}</table></div></div>")


def _afx_naver_research(n: int = 12) -> str:
    hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
           "<th>작성일</th><th>조회수</th></tr>")
    rows = []
    for i in range(n):
        rows.append(
            "<tr>"
            f"<td><a class='stock_item' href='/item/main.naver?code={i+1:06d}' "
            f"title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
            f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>실적 개선 전망</a></td>"
            f"<td>{'KB증권' if i%2 else '신한금융투자'}</td>"
            f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
            f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
            f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
    nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
           "<a href='/research/company_list.naver?&amp;page=2'>맨뒤</a></td></tr></table>")
    return (f"<div id='contentarea_left'><div class='box_type_m'>"
            f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")


def _afx_pdf() -> bytes:
    return b"%PDF-1.4\n% synthetic fixture\n%%EOF\n"


class _ArcFixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크. mode 로 정상/빈/깨짐/컬럼누락 전환."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: Counter = Counter()

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return b"\x00\x01garbage" if as_bytes else "<html><body>오류</body></html>"
        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                self.hits["fdr_delisting"] += 1
                return _afx_fdr_delisting()
            self.hits["fdr_listing"] += 1
            if self.mode == "missingcol":
                return b"\xef\xbb\xbf,Foo,Bar\n0,1,2\n"
            return _afx_fdr_listing()
        if "kind.krx.co.kr" in u:
            self.hits["kind"] += 1
            return _afx_kind()
        if "corpCode.xml" in u:
            self.hits["corpcode"] += 1
            return _afx_corpcode()
        if "document.xml" in u:
            self.hits["document"] += 1
            return _afx_document(str(p.get("rcept_no", "20200320000001")))
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                self.hits["hk_pdf"] += 1
                return _afx_pdf()
            self.hits["hankyung"] += 1
            return (_afx_hankyung() if int(p.get("now_page", 1) or 1) == 1
                    else "<td class='no_data'>데이터가 없습니다</td>")
        if "finance.naver.com/research" in u:
            self.hits["naver_research"] += 1
            return (_afx_naver_research() if int(p.get("page", 1) or 1) <= 1
                    else "<div id='contentarea_left'><table class='type_1'></table></div>")
        if "finance.naver.com/item/main" in u:
            self.hits["naver_item"] += 1
            return '<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>'
        if "stock.pstatic.net" in u:
            self.hits["naver_pdf"] += 1
            return _afx_pdf()
        if "siseJson" in u:
            self.hits["naver_chart"] += 1
            rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
            d0 = as_ts("2016-05-02")
            for i in range(0, 2600, 1):
                d2 = d0 + pd.Timedelta(days=i)
                if d2.weekday() >= 5:
                    continue
                rows.append(f"['{d2:%Y%m%d}',10000,10100,9900,10050,120000,5.0]")
            return "[" + ",".join(rows) + "]"
        self.hits["other"] += 1
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "fnlttSinglAcntAll" in u:
            self.hits["fnltt"] += 1
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return _afx_fnltt(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "fnlttMultiAcnt" in u:
            self.hits["multi"] += 1
            return {"status": "013"}
        if "empSttus" in u:
            self.hits["emp"] += 1
            return _afx_emp(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "stockTotqySttus" in u:
            self.hits["shares"] += 1
            return _afx_shares(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "accnutAdtorNmNdAdtOpinion" in u:
            self.hits["audit"] += 1
            return _afx_audit(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "list.json" in u:
            self.hits["dart_list"] += 1
            return _afx_dart_list(str(p.get("bgn_de", "20200301")), str(p.get("pblntf_ty", "A")))
        if "stockSecurity/researches" in u:
            self.hits["naver_api"] += 1
            return []                     # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        self.hits["other_json"] += 1
        return None


def run_rehearsal(strict: bool = True) -> bool:
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다")
    REHEARSAL_RESULTS.clear()
    G = globals()
    saved = {k: G.get(k) for k in ("http_get", "http_json", "http_post", "fdr", "pykrx_stock",
                                   "yf", "DART_API_KEY", "RUN_MODE", "RESEARCH_DOWNLOAD_PDF",
                                   "ARC_DOC_MAX")}
    saved_vault, saved_budget = G.get("VAULT"), G.get("DBUDGET")
    tmp = tempfile.mkdtemp(prefix="arc_rehearsal_")
    rebals = rebal_dates("2019-03-01", "2021-12-01")

    try:
        net = _ArcFixtureNet("ok")
        G["http_get"], G["http_json"] = net.get, net.json
        G["http_post"] = lambda *a, **k: ""
        G["fdr"] = None
        G["pykrx_stock"] = None                # 스냅샷 부재 시 폴백 경로 검증
        G["yf"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["ARC_DOC_MAX"] = 40
        G["VAULT"] = Vault(tmp, "REHEARSAL")
        G["DBUDGET"] = DartBudget()

        # ── ① 유니버스 ────────────────────────────────────────────────────────────────────
        snaps = _arh("fetch_pykrx_snapshots (pykrx 없음 → 폴백)",
                     lambda: fetch_pykrx_snapshots(month_range("2019-01-01", "2021-12-31")),
                     expect_rows=False, note="pykrx 미설치에서 죽지 않고 빈 결과여야 한다")
        _arh("fetch_fdr_listing", fetch_fdr_listing)
        _arh("fetch_fdr_delisting", fetch_fdr_delisting)
        _arh("fetch_kind_listing", fetch_kind_listing)
        _arh("fetch_dart_corpcode", fetch_dart_corpcode)
        sec = _arh("build_security_master",
                   lambda: build_security_master(
                       snaps if snaps is not None else
                       pd.DataFrame(columns=["snap_date", "code", "market"])),
                   note="중복 컬럼 → groupby.agg 폭발이 과거 이 지점에서 났다")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{i+1:06d}" for i in range(20)],
                                "name": [f"합성{i+1:03d}" for i in range(20)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(20)],
                                "listing_date": as_ts("2010-01-01"),
                                "delisting_date": pd.NaT})
        _arh("classify_excluded", lambda: classify_excluded(sec), expect_rows=False)

        # ── ② 가격 · 시총 ─────────────────────────────────────────────────────────────────
        codes = sec["code"].dropna().astype(str).tolist()[:8]
        px = _arh("fetch_prices (네이버 차트 폴백)",
                  lambda: fetch_prices(codes, "2018-06-01", "2021-12-31"),
                  note="FDR/pykrx 없이 네이버 경로만으로 동작해야 한다")
        if px is not None and len(px):
            _arh("build_liquidity_panel", lambda: build_liquidity_panel(px, rebals))
            _arh("build_exec_prices", lambda: build_exec_prices(px, rebals))
            _arh("attach_volatility", lambda: attach_volatility(
                pd.DataFrame({"code": codes[:3], "asof": rebals[0]}), px), expect_rows=False)
        _arh("fetch_market_cap_snapshots (pykrx 없음)",
             lambda: fetch_market_cap_snapshots(rebals), expect_rows=False)

        # ── ③ DART ────────────────────────────────────────────────────────────────────────
        corps = sec["corp_code"].dropna().astype(str).tolist()[:4]
        years = [2019, 2020]
        fs = _arh("fetch_dart_financials", lambda: fetch_dart_financials(corps, years))
        fin = None
        if fs is not None and len(fs):
            fin = _arh("tidy_financials", lambda: tidy_financials(fs))
        _arh("fetch_dart_employees", lambda: fetch_dart_employees(corps, years),
             note="사업부문×성별 분해 + '합계' 소계행 이중계상 방지")
        shares = _arh("fetch_dart_shares", lambda: fetch_dart_shares(corps, years),
                      note="보통주/우선주/합계 행 분해 — 합계 행 우선")
        audit = _arh("fetch_dart_audit", lambda: fetch_dart_audit(corps, years))
        dis = _arh("fetch_dart_disclosures",
                   lambda: fetch_dart_disclosures("2020-01-01", "2020-12-31"),
                   note="A(정기공시) + B(주요사항) 두 유형을 모두 훑어야 한다")

        # ── ④ 정기보고서 원문 → 정규화 → 페어링 → 유사도 ─────────────────────────────────
        T = None
        if dis is not None and len(dis):
            T = _arh("fetch_arc_documents (원문+정규화)",
                     lambda: fetch_arc_documents(dis, sec, max_docs=20),
                     note="zip 다중 엔트리 · EUC-KR · 6단계 정규화")
        if T is not None and len(T):
            _arh("arc_norm_sample_report", lambda: (arc_norm_sample_report(T, 2) or [1]),
                 expect_rows=False)
            pairs = _arh("arc_doc_pairs", lambda: arc_doc_pairs(T), expect_rows=False)
            if pairs is not None and len(pairs):
                S = _arh("d1_similarity", lambda: d1_similarity(pairs))
                if S is not None and len(S):
                    _arh("d1_composite",
                         lambda: d1_composite(S, build_struct_flags(dis)), expect_rows=False)
            _arh("arc_doc_load_years", lambda: arc_doc_load_years(arc_doc_years(T)),
                 expect_rows=False)
            _arh("build_d1_streaming (연도 스트리밍)",
                 lambda: build_d1_streaming(build_struct_flags(dis), T_manifest=T),
                 expect_rows=False,
                 note="연도 2개씩만 올려 상주량을 평평하게 유지하는 경로")
        _arh("build_struct_flags", lambda: build_struct_flags(dis), expect_rows=False)

        # ── ⑤ D2 / D3 / 배제 ──────────────────────────────────────────────────────────────
        if fin is not None and len(fin):
            _arh("build_d2_panel", lambda: build_d2_panel(fin, shares), expect_rows=False)
            _arh("build_exclusion_flags",
                 lambda: build_exclusion_flags(fin, dis, audit, T), expect_rows=False)
        _arh("extract_hardfacts",
             lambda: extract_hardfacts(T, fin, None, dis), expect_rows=False)

        # ── ⑥ 리서치 원장 → 본문 → TONE ───────────────────────────────────────────────────
        hk = _arh("hankyung_collect", lambda: hankyung_collect("2024-01-01", "2024-12-31"))
        nv = _arh("naver_collect",
                  lambda: naver_collect("2024-01-01", "2024-12-31", cats=("company",)))
        frames = [x for x in (hk, nv) if x is not None and len(x)]
        rep = _arh("build_report_master", lambda: build_report_master(frames, sec)) \
            if frames else None
        if rep is not None and len(rep):
            rep = _arh("tag_sponsored_reports", lambda: tag_sponsored_reports(rep))
            rep2 = _arh("download_pdfs", lambda: download_pdfs(rep, cap_per_month=3),
                        expect_rows=False)
            AL = _arh("build_analyst_ledger",
                      lambda: build_analyst_ledger(rep2 if rep2 is not None else rep),
                      expect_rows=False)
            if AL is not None:
                A, L = AL
                _arh("audit_linkage", lambda: (audit_linkage(rep, A, L) or [1]),
                     expect_rows=False)
                _arh("build_revision_panel", lambda: build_revision_panel(L, rebals),
                     expect_rows=False)
            rt = _arh("build_report_text_store",
                      lambda: build_report_text_store(rep2 if rep2 is not None else rep),
                      expect_rows=False,
                      note="PDF 픽스처에 텍스트 레이어가 없어 0행이 정상이다")
            _arh("build_tone_training",
                 lambda: build_tone_training(rt if rt is not None else
                                             pd.DataFrame(columns=["report_uid", "code",
                                                                   "pub_date", "text"]),
                                             px if px is not None else pd.DataFrame(), sec),
                 expect_rows=False)

        # ── ⑦ 게이트 ──────────────────────────────────────────────────────────────────────
        _arh("run_phase0_gates",
             lambda: (run_phase0_gates({"reports": rep, "report_text": None,
                                        "doc_tokens": T, "doc_pairs": None, "fin": fin,
                                        "shares": shares, "links": None,
                                        "panel_base": None}, rebals) or {"x": 1}),
             expect_rows=False)

        # ── ⑧ 이상 응답 내성 (빈 / 깨짐 / 컬럼누락) ───────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = _ArcFixtureNet(mode)
            G["http_get"], G["http_json"] = bad.get, bad.json
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"arc_rh_{mode}_"), "REHEARSAL")
            G["DBUDGET"] = DartBudget()
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing),
                              ("fetch_dart_corpcode", fetch_dart_corpcode)):
                _arh(f"[{label}] {fname}", fn, expect_rows=False,
                     note="예외 없이 빈 결과를 돌려줘야 한다")
            _arh(f"[{label}] fetch_dart_financials",
                 lambda: fetch_dart_financials(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_dart_shares",
                 lambda: fetch_dart_shares(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_dart_audit",
                 lambda: fetch_dart_audit(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_arc_documents",
                 lambda: fetch_arc_documents(dis, sec, max_docs=5), expect_rows=False)
            _arh(f"[{label}] hankyung_collect",
                 lambda: hankyung_collect("2024-01-01", "2024-03-31"), expect_rows=False)
            _arh(f"[{label}] build_report_master(빈 입력)",
                 lambda: build_report_master([], sec), expect_rows=False)
            _arh(f"[{label}] arc_doc_pairs(빈 입력)",
                 lambda: arc_doc_pairs(pd.DataFrame(columns=ARC_DOC_COLS)), expect_rows=False)
            _arh(f"[{label}] d1_similarity(빈 입력)",
                 lambda: d1_similarity(pd.DataFrame(columns=ARC_PAIR_COLS)), expect_rows=False)
            _arh(f"[{label}] build_d2_panel(빈 입력)",
                 lambda: build_d2_panel(pd.DataFrame(), None), expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"], G["DBUDGET"] = saved_vault, saved_budget
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in REHEARSAL_RESULTS if r["ok"])
    LOG.table([[_trunc(r["name"], 42), "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 56)]
               for r in REHEARSAL_RESULTS],
              ["실경로 함수", "판정", "결과", "소요", "비고"],
              ["l", "c", "r", "r", "l"], maxw=58)
    fails = [r for r in REHEARSAL_RESULTS if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(REHEARSAL_RESULTS)}건 실패")
        for r in fails[:5]:
            LOG.banner(f"✘ 리허설 실패: {_trunc(r['name'], 60)}", _trunc(r["err"], 92))
            for ln in str(r.get("tb", "")).rstrip().split("\n")[-10:]:
                _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"여기서 막는 것이 몇 시간 뒤 L1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(REHEARSAL_RESULTS)}건 통과 — "
           f"수집·정제 함수가 실제 데이터 모양에서 정상 동작합니다.")
    return True
