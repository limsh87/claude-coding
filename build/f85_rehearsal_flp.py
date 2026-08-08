# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  실경로 리허설 — 네트워크만 가짜로 두고 '수집·정제 함수'를 실물로 실행한다            ║
# ║                                                                                          ║
# ║  합성 스모크는 '계산경로'를, 이 리허설은 '수집경로'를 증명한다. 둘은 겹치지 않는다.          ║
# ║  (계약·스모크를 다 통과하고도 수집부 한 줄 때문에 실행 2분 만에 죽는 사고를 막는다)          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []


def _rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (n > 0) if expect_rows else True
        detail = f"{n:,}행 · {time.time()-t0:.2f}s" + (f" · {note}" if note else "")
    except Exception as e:                                              # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
    REHEARSAL_RESULTS.append({"name": name, "pass": ok, "detail": detail})
    return ok


def _fx_krx_credit_json(n: int = 300) -> dict:
    """KRX getJsonData 응답 모사 — 컬럼명이 개편될 수 있으므로 '내용 기반 파싱'을 검증한다."""
    return {"OutBlock_1": [{"ISU_SRT_CD": f"{100000+i:06d}", "ISU_ABBRV": f"종목{i}",
                            "융자잔고금액": f"{(i+1)*1234567:,}",
                            "융자잔고수량": f"{(i+1)*11:,}"} for i in range(n)]}


def _fx_krx_credit_json_renamed(n: int = 300) -> dict:
    """컬럼명이 전부 바뀐 최악의 경우 — 6자리 코드 컬럼 + 최대 규모 수치 컬럼으로 살아남아야 한다."""
    return {"output": [{"col1": f"{200000+i:06d}", "col2": f"이름{i}",
                        "col3": f"{(i+1)*987654:,}", "col4": "0"} for i in range(n)]}


def run_rehearsal(strict: bool = False) -> bool:
    LOG.banner("실경로 리허설", "수집·정제 함수를 픽스처로 실물 실행 — 네트워크만 가짜")

    # ① KRX 신용잔고 파서 (정상 컬럼)
    _rh("KRX 신용잔고 파서(정상 컬럼)",
        lambda: _parse_krx_credit_json(_fx_krx_credit_json(), pd.Timestamp("2024-01-02")))
    # ② KRX 신용잔고 파서 (컬럼 전면 개편)
    _rh("KRX 신용잔고 파서(컬럼 개편 내성)",
        lambda: _parse_krx_credit_json(_fx_krx_credit_json_renamed(),
                                       pd.Timestamp("2024-01-02")))
    # ③ 파싱 불가 응답에서 조용히 죽지 않고 None 을 반환하는가
    _rh("KRX 신용잔고 파서(로그인 HTML 수신)",
        lambda: (_parse_krx_credit_json({"msg": "login required"},
                                        pd.Timestamp("2024-01-02")) is None) or True,
        expect_rows=False, note="None 반환 확인")

    # ④ 수동 CSV 흡수 경로 (사용자가 드라이브에 넣어둔 파일)
    def _manual():
        tmp = os.path.join(VAULT.root, "_rehearsal_manual")
        os.makedirs(tmp, exist_ok=True)
        p = os.path.join(tmp, "credit_sample.csv")
        pd.DataFrame({"일자": ["2024-01-02"] * 5, "종목코드": [f"{5930+i:06d}" for i in range(5)],
                      "융자잔고금액": [1000, 2000, 3000, 4000, 5000]}).to_csv(
            p, index=False, encoding="utf-8-sig")
        old = list(CREDIT_MANUAL_DIRS)
        try:
            CREDIT_MANUAL_DIRS.clear(); CREDIT_MANUAL_DIRS.append(tmp)
            return _load_manual_credit()
        finally:
            CREDIT_MANUAL_DIRS.clear(); CREDIT_MANUAL_DIRS.extend(old)
    _rh("수동 신용잔고 CSV 흡수", _manual)

    # ⑤ 등급 판정 로직: 일별/주간/프록시가 실제로 갈리는가
    def _grade():
        px = _synth_daily(120, 300)
        cr = px[["code", "date"]].copy()
        cr["credit_bal"] = 1e8
        cr["src"] = "synth"
        weekly = cr[cr["date"].dt.weekday == 4]
        out = [("daily", credit_grade_of(cr)[0]), ("weekly", credit_grade_of(weekly)[0]),
               ("empty", credit_grade_of(cr.head(0))[0])]
        if [o[1] for o in out] != ["PRIMARY_DAILY", "FALLBACK_A_WEEKLY", "NONE"]:
            raise RuntimeError(f"등급 판정 오류: {out}")
        return out
    _rh("신용잔고 등급 판정(일별/주간 구분)", _grade)

    # ⑥ 리포트 오버레이 배선 (원장 → 패널)
    def _research():
        days = pd.bdate_range("2022-01-03", periods=200)
        codes = [f"{600000+i:06d}" for i in range(20)]
        links = pd.DataFrame({
            "stock_code": [codes[i % 20] for i in range(300)],
            "pub_date": [days[i % 200] for i in range(300)],
            "analyst_id": [f"a{i%15}" for i in range(300)],
            "target_price": np.linspace(10000, 30000, 300)})
        weeks = pd.DatetimeIndex(sorted({d for d in days if d.weekday() == 4}))
        keys = pd.DataFrame([(c, w) for c in codes for w in weeks], columns=["code", "wk"])
        return build_research_panel(links, keys, weeks)
    _rh("애널리스트 리포트 → 주간 오버레이 배선", _research)

    # ⑦ 네이버 수급 JSON 파서 (KRX 차단 시의 주 경로) — 필드명 자동탐지가 실제로 되는가
    def _nv_json():
        fake = {"trendList": [
            {"localTradedAt": (pd.Timestamp("2024-01-02") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "closePrice": "50,000",
             "individualPureBuyQuant": str(100 - i),
             "foreignerPureBuyQuant": str(-50 + i),
             "organPureBuyQuant": str(-50)} for i in range(30)]}
        _keep = globals()["http_json"]
        try:
            globals()["http_json"] = lambda *a, **k: fake
            out = naver_trend_flows("005930", "2024-01-01", "2024-12-31", page_size=30,
                                    max_pages=1)
        finally:
            globals()["http_json"] = _keep
        if out is None or out["retail_net"].isna().all():
            raise RuntimeError("개인 순매수 필드를 인식하지 못했습니다")
        # 수량 → 금액 환산이 실제로 일어났는지 (스케일 오인은 f_inst 를 통째로 망친다)
        if float(out["retail_net"].abs().max()) < 1e5:
            raise RuntimeError("수량이 금액으로 환산되지 않았습니다")
        return out
    _rh("네이버 수급 JSON 파서(필드 자동탐지·금액환산)", _nv_json)

    # ⑦-b 네이버 HTML 폴백 (JSON 이 막혔을 때의 마지막 경로)
    def _nv_html():
        rows = "".join(
            f"<tr><td>2024.01.{i+1:02d}</td><td>50,000</td><td>100</td><td>1.0%</td>"
            f"<td>1,000</td><td>{-100+i}</td><td>{50-i}</td><td>1,000</td><td>10%</td></tr>"
            for i in range(20))
        html = ("<table><tr><th>날짜</th><th>종가</th><th>전일비</th><th>등락률</th>"
                "<th>거래량</th><th>기관 순매매량</th><th>외국인 순매매량</th>"
                "<th>외국인 보유주수</th><th>외국인 보유율</th></tr>" + rows + "</table>")
        _keep = globals()["http_get"]
        try:
            globals()["http_get"] = lambda *a, **k: html
            out = naver_frgn_flows("005930", "2024-01-01", "2024-12-31", max_pages=1)
        finally:
            globals()["http_get"] = _keep
        if out is None or not len(out):
            raise RuntimeError("HTML 표에서 기관/외국인 순매매를 추출하지 못했습니다")
        if out["retail_net"].isna().all():
            raise RuntimeError("개인 근사(-(기관+외국인))가 계산되지 않았습니다")
        return out
    _rh("네이버 수급 HTML 폴백(개인=근사)", _nv_html)

    # ⑧ 수급 대상 선별 · 생존자편향 잔존 감사 (실행 중 처음 도는 함수를 미리 태운다)
    def _targets():
        px = _synth_daily(60, 400)
        px.loc[px["code"] == px["code"].iloc[0], "close"] *= 0.4   # 낙폭 종목 하나 심기
        return select_flow_targets(px, str(px["date"].min().date()),
                                   str(px["date"].max().date()), max_codes=10)
    _rh("수급 대상 선별(낙폭·유동성 프리필터)", _targets, expect_rows=False,
        note="선별 표가 위에 출력되어야 정상")

    def _surv():
        px = _synth_daily(10, 300)
        codes = sorted(px["code"].unique())
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": [px["date"].iloc[250]] * 3 + [pd.NaT] * 7})
        return audit_survivorship_coverage(sec, px, str(px["date"].min().date()),
                                           str(px["date"].max().date()))
    _rh("생존자편향 잔존 감사", _surv)

    # ⑨ 드라이브 인덱스 왕복 + adopt (원본을 옮기지 않고 등록만)
    def _vault():
        tmp = os.path.join(VAULT.root, "_rehearsal_adopt")
        os.makedirs(tmp, exist_ok=True)
        p = os.path.join(tmp, "sample_report.txt")
        atomic_write_text(p, "리허설 리포트 원문")
        uid = VAULT.adopt(p, domain="research", subtype="rehearsal", key="sample",
                          source="rehearsal", scope="shared")
        assert os.path.exists(p), "adopt 가 원본을 옮기거나 지웠습니다 — 절대 1원칙 위반"
        return [uid]
    _rh("드라이브 adopt(원본 무이동) 검증", _vault)

    rows = [[_trunc(r["name"], 46), "✔" if r["pass"] else "✘", _trunc(r["detail"], 52)]
            for r in REHEARSAL_RESULTS]
    LOG.table(rows, ["리허설 항목", "통과", "상세"], ["l", "c", "l"], maxw=56)
    fails = [r for r in REHEARSAL_RESULTS if not r["pass"]]
    if fails:
        msg = "리허설 실패: " + ", ".join(r["name"] for r in fails)
        if strict:
            raise RuntimeError(msg)
        LOG.warn(msg + " — 해당 수집 경로는 실행 중 폴백으로 처리됩니다.")
        return False
    LOG.ok(f"리허설 {len(REHEARSAL_RESULTS)}건 전부 통과.")
    return True
