

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 3·4·5 — PDF 본문 수집 · 동결 렉시콘 스코어링 · 횡단면 상대비교                       ║
# ║                                                                                          ║
# ║  입력 : EV(이벤트) · REP(원장) · UNI · pxm                                                 ║
# ║  출력 : TXT(섹션 분할 본문) · SCORE(문서 점수) · SIG(신호 패널)                             ║
# ║  실패 : 스캔 PDF/추출 실패는 예외가 아니라 '결손율'이다. 반드시 수치로 노출한다.            ║
# ║                                                                                          ║
# ║  ★ 왜 LLM 임베딩을 1차 스코어러로 쓰지 않는가(명세 §9.1)                                    ║
# ║    사전학습 모델은 2016년 리포트를 채점할 때 이미 2024년까지를 학습한 상태다. 어떤 소형주가 ║
# ║    결국 대박이 났는지를 모델이 '알고' 있을 수 있다 — 미묘하지만 실질적인 룩어헤드다.        ║
# ║    그래서 1차 스코어러는 **수익률을 보기 전에 동결한 룰 기반 렉시콘**이다.                  ║
# ║                                                                                          ║
# ║  ⚠⚠ 렉시콘을 백테스트 수익률을 확인한 뒤에 수정하면 이 전략의 모든 결과가 무효다(§12 R5).   ║
# ║     수정이 필요하면 버전을 올리고(v2) 사전등록을 새로 써야 한다. 해시가 매니페스트에 남는다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 렉시콘 v1.0 (동결 대상) ─────────────────────────────────────────────────────────────────
NCQ_LEXICON: Dict[str, Any] = {
    "version": "v1.0",
    "frozen_at": "2026-08-08",
    "note": "수익률 확인 전에 동결. 수정 시 버전 증가 + 사전등록 재작성 필수(명세 §9.2).",
    "section_weight": {"TITLE": 3.0, "HEADLINE": 2.0, "BODY": 1.0},
    "negation_window": 30,
    "negation_markers": ["아니", "못하", "없", "어렵", "힘들"],
    "groups": {
        "A": {"weight": 3.0, "label": "구조적 전환", "terms": [
            "사업구조 전환", "사업구조전환", "사업 재편", "사업재편", "체질 개선", "체질개선",
            "턴어라운드", "흑자전환", "흑자 전환", "퀀텀점프", "퀀텀 점프",
            "신규 사업 진출", "신규사업 진출", "신사업 진출", "주력 제품 교체",
            "포트폴리오 전환", "밸류체인 진입", "밸류체인 편입", "수직계열화"]},
        "B": {"weight": 2.5, "label": "캐파·양산", "terms": [
            "증설", "신규 라인", "신규라인", "양산 개시", "양산개시", "첫 양산", "본격 양산",
            "캐파 확대", "캐파확대", "가동률 상승", "공장 준공", "설비 투자", "설비투자",
            "생산능력", "생산 능력", "라인 증설", "증설 투자"]},
        "C": {"weight": 2.0, "label": "수요·고객", "terms": [
            "신규 수주", "신규수주", "대형 수주", "대형수주", "수주 잔고", "수주잔고",
            "장기공급계약", "장기 공급 계약", "고객사 다변화", "신규 고객사", "신규 고객",
            "1차 벤더", "1차벤더", "레퍼런스 확보", "전방시장 확대", "전방 시장 확대",
            "국산화", "수입 대체", "수입대체", "진입장벽", "진입 장벽"]},
        "D": {"weight": 2.0, "label": "인증·승인", "terms": [
            "인증 획득", "인증획득", "품질 승인", "품질승인", "벤더 등록", "벤더등록",
            "특허 등록", "특허등록", "규제 통과", "승인 완료", "승인완료", "임상 진입",
            "임상 개시", "허가 획득"]},
        "H": {"weight": -1.0, "label": "헤지·불확실성", "terms": [
            "기대", "전망", "가능성", "예상", "할 것으로 보인다", "될 것으로 보인다",
            "추정", "관측", "여겨진다", "지켜볼 필요", "검토 중", "검토중",
            "계획 중", "계획중", "논의 중", "논의중", "협의 중", "협의중"]},
        "N": {"weight": -2.5, "label": "부정", "terms": [
            "지연", "차질", "부진", "둔화", "감소", "하향", "우려", "리스크",
            "불확실", "악화", "적자 전환", "적자전환"]},
    },
}

NCQ_PREREG: Dict[str, Any] = {
    "version": "v1.0",
    "frozen_at": "2026-08-08",
    "strategy": "ARC-NCQ v1.0 — New Coverage × Qualitative Shift",
    "primary_hypothesis": (
        "시총 하위 N 소형주에서 발생한 신규 애널리스트 커버리지 이벤트 중, "
        "동월 이벤트 풀 내 텍스트 z-score 상위 tercile 종목군이 "
        "동일 유니버스 동일가중(Bottom-N EW) 대비 12개월 초과수익을 낸다."),
    "hypotheses": [
        {"id": "P1", "text": "De novo 신규커버리지 × z상위tercile 포트폴리오가 Bottom-N EW 대비 초과수익",
         "stat": "월별 초과수익 평균, Newey-West t (lag=12)", "direction": ">0"},
        {"id": "P2", "text": "텍스트 z점수의 단조성: 상위 tercile − 하위 tercile 스프레드",
         "stat": "롱숏 스프레드 HAC t", "direction": ">0"},
        {"id": "P3", "text": "ORGANIC_ONLY 서브그룹에서도 P1 유지",
         "stat": "서브그룹 초과수익 HAC t", "direction": ">0"},
        {"id": "P4", "text": "텍스트 점수가 신규커버리지 이벤트 단독 대비 증분 정보 제공",
         "stat": "전체 이벤트 EW 대비 z상위 tercile 스프레드 HAC t", "direction": ">0"},
    ],
    "multiple_testing": "BH-FDR (alpha=0.10) applied to P1~P4",
    "adoption_criteria": [
        "P1 과 P3 가 BH-FDR 통과",
        "왕복 거래비용 3.0% 시나리오에서도 초과수익 > 0",
        "Placebo(z 하위 tercile) 대비 스프레드 > 0",
    ],
    "parameters": {
        "universe_bottom_n": None, "min_adv_krw": None, "lookback_months": None,
        "burnin_months": None, "hold_months": None, "tercile": None,
        "cost_roundtrip": None, "max_new_per_month": None,
    },
    "sensitivity_plan": "기본 1조합 + 각 축 단독 변동 8조합 = 9조합만 실행. DSR 시행횟수에 9 반영.",
    "kill_criteria": [
        "커버리지 완결성 진단에서 유효 윈도우 < 5년이면 백테스트 중단",
        "하네스 누수 민감도(N11) 실패 시 전 결과 무효",
    ],
}

NCQ_LEXICON_SHA = ""
NCQ_PREREG_SHA = ""
NCQ_PDF_ENGINE = "auto"          # "auto" | "fitz" | "pdfplumber"

TXT_COLS = ["report_uid", "code", "pub_date", "sec_title", "sec_headline", "sec_body",
            "n_chars", "n_pages", "extract_ok", "extract_method"]
SCORE_COLS = ["report_uid", "code", "month", "doc_raw", "doc_score", "n_chars", "title_only",
              "g_A", "g_B", "g_C", "g_D", "g_H", "g_N"]
SIG_COLS = ["month", "code", "event_score", "z", "pooled", "pool_n", "rank_pct",
            "selected", "placebo", "sponsor_group", "event_type", "exec_px", "adv20", "fwd_ret"]


def _ncq_canon_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def freeze_configs(outdir: str) -> Tuple[dict, str, dict, str]:
    """렉시콘·사전등록을 JSON 으로 동결하고 SHA256 을 기록한다.

    ★ 이미 파일이 있으면 **그 파일을 정본으로 삼는다.** 코드 안의 딕셔너리로 덮어쓰지 않는다.
      한 번 동결한 뒤 코드를 수정해도 과거 실행의 정의가 바뀌지 않아야 재현성이 성립한다.
      내용이 다르면 경고를 띄우고 파일 쪽을 쓴다(사용자가 의도적으로 v2 를 만든 경우 대비).
    """
    global NCQ_LEXICON, NCQ_PREREG, NCQ_LEXICON_SHA, NCQ_PREREG_SHA
    os.makedirs(outdir, exist_ok=True)
    # 사전등록에 현재 파라미터를 박아 넣는다(무엇을 사전등록했는지 나중에 다툴 여지를 없앤다).
    prereg = json.loads(_ncq_canon_json(NCQ_PREREG))
    prereg["parameters"] = {
        "universe_bottom_n": NCQ_UNIVERSE_BOTTOM_N, "min_adv_krw": NCQ_MIN_ADV,
        "lookback_months": NCQ_LOOKBACK_M, "burnin_months": NCQ_BURNIN_M,
        "hold_months": NCQ_HOLD_MONTHS, "tercile": round(float(NCQ_TERCILE), 6),
        "cost_roundtrip": NCQ_COST_ROUNDTRIP, "max_new_per_month": NCQ_MAX_NEW_PER_MONTH,
        "backtest_window": [BACKTEST_START, BACKTEST_END], "seed": SEED,
    }

    pairs = [("lexicon_v1.json", NCQ_LEXICON, "렉시콘"), ("prereg_v1.json", prereg, "사전등록")]
    loaded: Dict[str, Any] = {}
    for fn, obj, label in pairs:
        path = os.path.join(outdir, fn)
        if os.path.exists(path):
            try:
                on_disk = json.loads(open(path, encoding="utf-8").read())
                if _ncq_canon_json(on_disk) != _ncq_canon_json(obj):
                    LOG.warn(f"{label} 파일이 코드 안의 정의와 다릅니다 — **파일 쪽을 정본으로 "
                             f"사용합니다**({fn}). 동결 원칙상 이미 고정된 정의가 우선합니다. "
                             f"의도한 변경이면 버전을 올려 새 파일로 만드세요.")
                loaded[fn] = on_disk
                continue
            except Exception as e:                                # noqa
                LOG.warn(f"{label} 파일을 읽지 못해({type(e).__name__}) 코드 정의로 새로 씁니다.")
        atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))
        loaded[fn] = obj
        LOG.ok(f"{label} 동결: {path}")

    NCQ_LEXICON = loaded["lexicon_v1.json"]
    NCQ_PREREG = loaded["prereg_v1.json"]
    NCQ_LEXICON_SHA = hashlib.sha256(_ncq_canon_json(NCQ_LEXICON).encode()).hexdigest()
    NCQ_PREREG_SHA = hashlib.sha256(_ncq_canon_json(NCQ_PREREG).encode()).hexdigest()
    _ncq_compile_lexicon()
    manifest_put("lexicon_version", NCQ_LEXICON.get("version"))
    manifest_put("lexicon_sha256", NCQ_LEXICON_SHA)
    manifest_put("prereg_version", NCQ_PREREG.get("version"))
    manifest_put("prereg_sha256", NCQ_PREREG_SHA)
    LOG.table([["렉시콘", NCQ_LEXICON.get("version", "?"), NCQ_LEXICON_SHA[:16] + "…",
                f"{sum(len(g['terms']) for g in NCQ_LEXICON['groups'].values())}개 어휘"],
               ["사전등록", NCQ_PREREG.get("version", "?"), NCQ_PREREG_SHA[:16] + "…",
                f"{len(NCQ_PREREG.get('hypotheses', []))}개 가설"]],
              ["구성", "버전", "SHA256", "규모"], ["l", "c", "l", "l"],
              title="동결 설정 (백테스트 수익률을 보기 전에 고정됨 — 사후 수정 시 전 결과 무효)")
    return NCQ_LEXICON, NCQ_LEXICON_SHA, NCQ_PREREG, NCQ_PREREG_SHA


# ── 렉시콘 컴파일 (그룹당 정규식 1개 — 어휘당 스캔은 너무 느리다) ────────────────────────────
_NCQ_GRP_RE: Dict[str, Any] = {}
_NCQ_NEG_RE = None


def _ncq_compile_lexicon():
    global _NCQ_GRP_RE, _NCQ_NEG_RE
    _NCQ_GRP_RE = {}
    for g, spec in NCQ_LEXICON["groups"].items():
        terms = sorted({str(t).strip() for t in spec["terms"] if str(t).strip()},
                       key=len, reverse=True)      # 긴 어휘 우선 매칭
        if not terms:
            continue
        # ★ 어휘 안의 공백은 \s* 로 바꾼다. PDF 텍스트는 줄바꿈이 단어 사이에 끼어들어
        #   "신규 수주" 가 "신규\n수주" 로 나오는 일이 매우 흔하다. 공백을 고정으로 두면
        #   그 건들이 통째로 미검출되고, 그 결손은 예외가 아니라 '점수 0'으로 조용히 남는다.
        #   (Python 3.7+ 의 re.escape 는 공백을 이스케이프하지 않으므로 예전 방식은 무동작이었다)
        pat = "|".join(r"\s*".join(re.escape(part) for part in t.split()) for t in terms)
        _NCQ_GRP_RE[g] = re.compile(pat)
    marks = NCQ_LEXICON.get("negation_markers", [])
    _NCQ_NEG_RE = re.compile("|".join(re.escape(m) for m in marks)) if marks else None


_ncq_compile_lexicon()


# ── PDF 섹션 추출 ───────────────────────────────────────────────────────────────────────────
_NCQ_COMPLIANCE_RE = re.compile(
    r"(Compliance\s*Notice|본\s*자료는|본\s*조사분석자료는|투자등급\s*및|투자의견\s*및\s*목표주가|"
    r"이해\s*관계\s*고지|이해관계|당사는\s*동\s*자료를|고지사항|Disclaimer|법적\s*고지)")
_NCQ_NUMLINE_RE = re.compile(r"[\d.,%\-+()/\s]")


def ncq_pdf_engine() -> str:
    """추출 엔진 선택. 명세 §8.2 는 pdfplumber 우선이지만 실측 10배 차이라 기본은 자동이다.

    두 엔진의 섹션 분할 결과는 동일한 규칙(첫 페이지 상위 40%)을 쓰므로 점수 분포가 달라지지
    않는다. 어떤 엔진이 쓰였는지는 TXT.extract_method 와 결손율 표에 그대로 남는다.
    """
    e = str(NCQ_PDF_ENGINE).lower()
    if e == "fitz":
        return "fitz" if fitz is not None else ("pdfplumber" if pdfplumber is not None else "")
    if e == "pdfplumber":
        return "pdfplumber" if pdfplumber is not None else ("fitz" if fitz is not None else "")
    if fitz is not None:
        return "fitz"
    if pdfplumber is not None:
        return "pdfplumber"
    return ""


def ncq_clean_text(pages: List[str]) -> str:
    """노이즈 제거 (명세 §8.3): 컴플라이언스 블록 절단 · 숫자 라인 제거 · 반복 헤더/푸터 제거."""
    if not pages:
        return ""
    # ① 반복 헤더/푸터 — 같은 줄이 페이지 수의 70% 이상 나오면 제거
    n_pg = len(pages)
    line_pages: Counter = Counter()
    per_page_lines = []
    for p in pages:
        ls = [ln.strip() for ln in str(p).split("\n")]
        per_page_lines.append(ls)
        for ln in set(ls):
            if len(ln) >= 4:
                line_pages[ln] += 1
    repeated = {ln for ln, c in line_pages.items() if n_pg >= 3 and c >= 0.7 * n_pg}

    out_lines: List[str] = []
    for ls in per_page_lines:
        for ln in ls:
            if not ln or ln in repeated:
                continue
            # ② 표·숫자 라인 — 숫자·기호 비중 60% 초과
            if len(ln) >= 6:
                nsym = len(_NCQ_NUMLINE_RE.findall(ln))
                if nsym / max(len(ln), 1) > 0.60:
                    continue
            out_lines.append(ln)
    txt = "\n".join(out_lines)
    # ③ 컴플라이언스 고지 이후 전체 절단
    m = _NCQ_COMPLIANCE_RE.search(txt)
    if m and m.start() > 200:
        txt = txt[:m.start()]
    return txt


def ncq_pdf_sections(data: bytes, max_pages: int = 0) -> dict:
    """PDF → {headline, body, n_pages, method, ok}.

    HEADLINE = 첫 페이지 상위 40% 영역(투자포인트·요약이 몰려 있는 블록). BODY = 나머지.
    ★ 텍스트 레이어가 비면(스캔 PDF) OCR 을 시도하지 않는다 — 예산을 파괴한다(명세 §8.2-3).
      대신 결손으로 기록한다.
    """
    res = {"headline": "", "body": "", "n_pages": 0, "method": "", "ok": False}
    if not data or data[:5] != b"%PDF-":
        return res
    eng = ncq_pdf_engine()
    cap = int(max_pages or globals().get("NCQ_PDF_MAX_PAGES", 0) or 0)
    head_parts: List[str] = []
    body_pages: List[str] = []

    if eng == "fitz" and fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                n = doc.page_count
                last = min(cap, n) if cap else n
                res["n_pages"] = n
                for i in range(last):
                    pg = doc[i]
                    if i == 0:
                        h = float(pg.rect.height) or 1.0
                        blocks = pg.get_text("blocks") or []
                        top, rest = [], []
                        for b in blocks:
                            try:
                                y0, t = float(b[1]), str(b[4])
                            except Exception:
                                continue
                            (top if y0 < 0.40 * h else rest).append(t)
                        head_parts.append("\n".join(top))
                        body_pages.append("\n".join(rest))
                    else:
                        body_pages.append(pg.get_text())
            res["method"] = "fitz"
        except Exception:
            eng = "pdfplumber" if pdfplumber is not None else ""

    if not res["method"] and eng == "pdfplumber" and pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                n = len(pdf.pages)
                last = min(cap, n) if cap else n
                res["n_pages"] = n
                for i in range(last):
                    pg = pdf.pages[i]
                    if i == 0:
                        h = float(pg.height) or 1.0
                        try:
                            top = pg.crop((0, 0, pg.width, 0.40 * h)).extract_text() or ""
                            rest = pg.crop((0, 0.40 * h, pg.width, h)).extract_text() or ""
                        except Exception:
                            top, rest = "", (pg.extract_text() or "")
                        head_parts.append(top)
                        body_pages.append(rest)
                    else:
                        body_pages.append(pg.extract_text() or "")
            res["method"] = "pdfplumber"
        except Exception:
            return res

    if not res["method"]:
        return res
    head = ncq_clean_text(head_parts)
    body = ncq_clean_text(body_pages)
    res["headline"], res["body"] = head, body
    res["ok"] = (len(head) + len(body)) >= 200        # 스캔 PDF 는 여기서 걸러진다
    return res


def collect_event_texts(EV: pd.DataFrame, REP: pd.DataFrame,
                        extra_text: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Phase 3 — **이벤트로 판정된 (종목, 월) 의 리포트만** PDF 를 받는다.

    ★ 이 한 줄이 이 전략의 비용 구조 전체다. 인덱스는 수만 건이지만 PDF 는 수천 건만 받는다.
    ★ 이미 드라이브 공용 인덱스에 있는 PDF 는 다시 받지 않는다(내용해시 경로 → 중복 저장 없음).
    """
    if EV is None or EV.empty or REP is None or REP.empty:
        return pd.DataFrame(columns=TXT_COLS)
    want: set = set()
    for s in EV["report_uids"].astype(str):
        for u in s.split("|"):
            if u and u != "nan":
                want.add(u)
    R = REP[REP["report_uid"].astype(str).isin(want)].copy()
    if R.empty:
        LOG.warn("이벤트에 연결된 리포트를 원장에서 찾지 못했습니다 — report_uid 연결이 깨졌습니다.")
        return pd.DataFrame(columns=TXT_COLS)
    R["code"] = R["stock_code"].map(to_code6)

    # 이미 추출해 둔 본문(공용 캐시) 재사용 — 티커 앞 2자리 샤드만 골라 읽는다.
    # ★★ 읽자마자 **필요한 report_uid 로 즉시 자른다.** 공용 샤드는 다른 전략이 넣은 본문까지
    #   들어 있고 sec_body 가 건당 10~30KB 다. 캐시가 성숙해 20만 건이 쌓이면 concat 사본만
    #   수 GB 라 P3 시작 직후 커널이 죽고, 그때까지의 P0·P1(최대 165분)이 통째로 날아간다.
    #   정작 필요한 건 이벤트 리포트 수천 건뿐이다.
    cached_txt: List[pd.DataFrame] = []
    _n_scanned = 0
    for pref in sorted({str(c)[:2] for c in R["code"].dropna().astype(str)}):
        d = VAULT.get_table(f"report_text_{pref}", scope="shared")
        if d is None or len(d) == 0:
            continue
        _n_scanned += len(d)
        if "report_uid" in d.columns:
            d = d[d["report_uid"].astype(str).isin(want)]
        if len(d):
            cached_txt.append(d.copy())
        del d
    if _n_scanned:
        LOG.debug(f"본문 샤드 {_n_scanned:,}행을 훑어 이벤트 관련 "
                  f"{sum(len(x) for x in cached_txt):,}행만 적재했습니다(메모리 보호).")
    if extra_text is not None and len(extra_text):
        # 호출자가 이미 확보한 본문(스모크의 합성 텍스트 · 외부에서 추출해 둔 본문)을 우선 사용.
        # 네트워크 없이도 텍스트 경로 전체를 실제로 검증할 수 있게 하는 통로다.
        cached_txt.insert(0, extra_text.reindex(columns=TXT_COLS))
    T_cached = pd.concat(cached_txt, ignore_index=True) if cached_txt else pd.DataFrame(columns=TXT_COLS)
    if len(T_cached):
        T_cached = T_cached.drop_duplicates("report_uid", keep="first")
    # ★ 캐시에 있어도 '본문 확보에 실패한' 건은 재시도 대상으로 남긴다.
    if len(T_cached):
        _bad = T_cached["extract_method"].astype(str).isin(("download_failed", "no_engine")) \
            if "extract_method" in T_cached.columns else pd.Series(False, index=T_cached.index)
        have = set(T_cached.loc[~_bad, "report_uid"].astype(str))
        if int(_bad.sum()):
            LOG.info(f"본문 확보에 실패했던 {int(_bad.sum()):,}건을 재시도 대상으로 되돌립니다.")
    else:
        have = set()
    todo = R[~R["report_uid"].astype(str).isin(have)]
    LOG.info(f"Phase 3 대상 리포트 {len(R):,}건 — 본문 캐시 보유 {len(R)-len(todo):,}건 / "
             f"신규 추출 {len(todo):,}건")

    if len(todo) and RESEARCH_DOWNLOAD_PDF and RUN_MODE != "CACHED":
        if not ncq_pdf_engine():
            LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 본문 추출을 건너뜁니다. "
                     "제목(TITLE)만으로 점수가 계산되며 변별력이 크게 떨어집니다. "
                     "`pip install pymupdf` 를 권합니다.")
        else:
            new = _ncq_download_and_extract(todo)
            if len(new):
                T_cached = pd.concat([T_cached, new], ignore_index=True)
    elif len(todo):
        LOG.info(f"신규 PDF 수집을 하지 않습니다 (RUN_MODE={RUN_MODE}, "
                 f"RESEARCH_DOWNLOAD_PDF={RESEARCH_DOWNLOAD_PDF}).")

    if T_cached.empty:
        T_cached = pd.DataFrame(columns=TXT_COLS)
    T = T_cached[T_cached["report_uid"].astype(str).isin(set(R["report_uid"].astype(str)))].copy()
    # 제목은 원장에서 항상 붙인다(PDF 가 없어도 TITLE 섹션은 살아 있어야 한다)
    tmap = dict(zip(R["report_uid"].astype(str), R["title"].astype(str)))
    cmap = dict(zip(R["report_uid"].astype(str), R["code"]))
    dmap = dict(zip(R["report_uid"].astype(str), R["pub_date"]))
    miss = R[~R["report_uid"].astype(str).isin(set(T["report_uid"].astype(str)))]
    if len(miss):
        add = pd.DataFrame({
            "report_uid": miss["report_uid"].astype(str), "code": miss["code"],
            "pub_date": miss["pub_date"], "sec_title": miss["title"].astype(str),
            "sec_headline": "", "sec_body": "", "n_chars": 0, "n_pages": 0,
            "extract_ok": False, "extract_method": "none"})
        T = pd.concat([T, add], ignore_index=True)
    _tt = T["report_uid"].astype(str).map(tmap)
    T["sec_title"] = _tt.where(_tt.astype(str).str.len() > 0, T.get("sec_title", ""))
    T["code"] = T["report_uid"].astype(str).map(cmap).fillna(T.get("code"))
    T["pub_date"] = as_ts_series(T["report_uid"].astype(str).map(dmap))
    # ★ 신규 추출본이 캐시의 실패 행보다 항상 우선해야 한다. T_cached(불량) 뒤에 new(양호)를
    #   붙였으므로 keep="last". keep="first" 면 재시도로 방금 받아온 본문을 버리고 빈 행을
    #   남겨서, "재시도 대상으로 되돌립니다" 로그가 그 실행에 한해 거짓이 된다.
    #   (드라이브 샤드는 이미 keep="last" 라 캐시에는 좋은 행이 들어가는데 이번 실행만 손해였다)
    T = T.drop_duplicates("report_uid", keep="last")

    n_ok = int(T["extract_ok"].fillna(False).astype(bool).sum())
    fail = 1.0 - n_ok / max(len(T), 1)
    LOG.table([["대상 리포트", f"{len(T):,}"],
               ["본문 추출 성공", f"{n_ok:,} ({100*(1-fail):.1f}%)"],
               ["추출 실패/스캔 PDF", f"{len(T)-n_ok:,} ({100*fail:.1f}%)"],
               ["평균 본문 길이", f"{float(pd.to_numeric(T['n_chars'], errors='coerce').mean() or 0):,.0f}자"]],
              ["항목", "값"], ["l", "r"], title="Phase 3 본문 추출 결손율 (OCR 은 시도하지 않습니다)")
    manifest_put("pdf_extract_fail_rate", round(float(fail), 4))
    if fail > 0.5:
        LOG.warn(f"본문 추출 실패율이 {100*fail:.0f}% 입니다. 제목만으로 채점된 건이 많아 "
                 f"텍스트 점수의 변별력이 떨어집니다 — P4(증분 정보) 검정을 특히 주의해 보세요.")
    PIPE.io("OUT", "MEM", "report_text", T)
    return T[TXT_COLS]


def _ncq_download_and_extract(todo: pd.DataFrame) -> pd.DataFrame:
    """PDF 다운로드 + 섹션 추출. 청크 단위로 소비하고 버려 RAM 상주량을 평평하게 유지한다."""
    idx = VAULT.load_index("shared")
    known: Dict[str, str] = {}
    if idx is not None and len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))

    jobs = list(zip(todo["report_uid"].astype(str), todo["pdf_url"].astype(str),
                    todo["code"].astype(str), todo["pub_date"], todo["title"].astype(str)))
    jobs = [j for j in jobs if j[1] and j[1].lower() not in ("nan", "none")]
    if not jobs:
        return pd.DataFrame(columns=TXT_COLS)

    def _one(job):
        uid, url, code, pdt, title = job
        data = None
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
        if not data:
            src = "hankyung" if "hankyung" in url else ("irs" if "kirs" in url or "irsolution" in url
                                                        else "naver")
            ref = {"hankyung": "https://consensus.hankyung.com/",
                   "naver": "https://finance.naver.com/research/",
                   "irs": "https://www.kirs.or.kr/"}[src]
            raw = http_get(url, source=src, as_bytes=True, tries=2, referer=ref)
            # ★ 로그인/에러 HTML 이 200 으로 오는 케이스 방어 — 매직바이트를 반드시 본다
            data = raw if (raw and raw[:5] == b"%PDF-") else None
            if data:
                VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                               source="report_pdf", scope="shared",
                               event_date=pdt, knowledge_date=pdt)
        if not data:
            return {"report_uid": uid, "code": code, "pub_date": pdt, "sec_title": title,
                    "sec_headline": "", "sec_body": "", "n_chars": 0, "n_pages": 0,
                    "extract_ok": False, "extract_method": "download_failed"}
        s = ncq_pdf_sections(data)
        return {"report_uid": uid, "code": code, "pub_date": pdt, "sec_title": title,
                "sec_headline": s["headline"], "sec_body": s["body"],
                "n_chars": len(title) + len(s["headline"]) + len(s["body"]),
                "n_pages": s["n_pages"], "extract_ok": bool(s["ok"]),
                "extract_method": s["method"] or "no_engine"}

    rows: List[dict] = []
    CH = 400
    with PhaseBudget("P3", NCQ_PHASE_BUDGET_S["P3"]) as B:
        for k0 in range(0, len(jobs), CH):
            # ★ 열화 L2(앞 6페이지 제한)를 **예산 소진 전에** 발동시킨다. 캡에 도달한 뒤
            #   발동하면 그 즉시 루프가 끝나 단 한 건에도 적용되지 않는데, 매니페스트와
            #   리포트에는 "6페이지 제한 적용"이라고 남아 독자를 오도한다.
            if B.frac() > 0.8 and not is_degraded("L2"):
                degrade("L2", "P3 예산 80% 소진 — 남은 PDF 를 앞 6페이지만 추출")
            if not B.check():
                LOG.warn(f"[P3] 예산 소진 — {k0:,}/{len(jobs):,}건까지만 본문을 확보했습니다. "
                         f"나머지는 제목만으로 채점되며 결손율에 반영됩니다.")
                break
            chunk = jobs[k0:k0 + CH]
            res = pmap_io(_one, chunk, workers=min(N_WORKERS_RESEARCH, 4),
                          desc=f"리포트 PDF {k0//CH+1}/{(len(jobs)-1)//CH+1}")
            got = [r for r in res if r]
            rows.extend(got)
            # ★★ 다운로드 실패 행을 공용 캐시에 남기면 '음성 캐싱'이 된다. 다음 실행의
            #   have 집합에 들어가 재시도 대상에서 영구히 빠지고, 그 보고서는 영원히
            #   제목만으로 채점되어 z 하위로 계통적으로 몰린다(조용한 선택 편향).
            #   게다가 scope="shared" 라 다른 전략의 캐시까지 오염시킨다. 저장하지 않는다.
            _keep = [r for r in got if str(r.get("extract_method")) != "download_failed"]
            if _keep:
                _ncq_flush_text_shards(pd.DataFrame(_keep))
            if len(_keep) < len(got):
                LOG.debug(f"다운로드 실패 {len(got)-len(_keep)}건은 캐시에 저장하지 않습니다"
                          f"(다음 실행에서 재시도).")
            VAULT.flush("shared")
            del res, got
    if not rows:
        return pd.DataFrame(columns=TXT_COLS)
    return pd.DataFrame(rows).reindex(columns=TXT_COLS)


def _ncq_flush_text_shards(new: pd.DataFrame):
    """본문을 티커 앞 2자리로 샤딩 저장(단일 거대 parquet 금지 — 기존 규약)."""
    if new is None or new.empty:
        return
    d = new.copy()
    d["_pref"] = d["code"].astype(str).str[:2]
    for pref, g in d.groupby("_pref"):
        if not pref or pref == "na":
            continue
        name = f"report_text_{pref}"
        old = VAULT.get_table(name, scope="shared")
        merged = g.drop(columns=["_pref"])
        if old is not None and len(old):
            cols = list(dict.fromkeys(list(old.columns) + list(merged.columns)))
            merged = pd.concat([old.reindex(columns=cols), merged.reindex(columns=cols)],
                               ignore_index=True).drop_duplicates("report_uid", keep="last")
        VAULT.put_table(name, merged, scope="shared", domain="research",
                        source="ncq pdf sections",
                        extra={"note": "리포트 본문 섹션 — 티커 앞2자리 샤딩 · 전 전략 공용"})


# ── Phase 4 — 스코어링 ──────────────────────────────────────────────────────────────────────
def _ncq_count_group(text: str, rx, neg_window: int) -> int:
    """그룹 어휘 출현 수. 같은 문장 안에서 어휘 뒤 30자 이내에 부정 어미가 오면 무효화한다.

    ★ 문장 경계를 넘어가면 부정이 아니다. 경계를 안 보면 다음 문장의 '없다'가 앞 문장의
      '수주 확대'를 지워버리는 오탐이 대량 발생한다.
    """
    if not text or rx is None:
        return 0
    n = 0
    for m in rx.finditer(text):
        if _NCQ_NEG_RE is not None:
            tail = text[m.end(): m.end() + neg_window]
            cut = re.search(r"[.!?\n]", tail)
            scope = tail[:cut.start()] if cut else tail
            if _NCQ_NEG_RE.search(scope):
                continue                                  # 부정 → 이 출현은 0점
        n += 1
    return n


def score_texts(TXT: pd.DataFrame) -> pd.DataFrame:
    """문서 점수 (명세 §9.3).

        doc_raw   = Σ_g w_g × [3.0·cnt(TITLE) + 2.0·cnt(HEADLINE) + 1.0·cnt(BODY)]
        doc_score = doc_raw / (총 문자수 / 1000)          ← 길이 정규화

    길이 정규화를 빼면 '긴 리포트일수록 고득점'이라는 자명한 편향이 생기고, 대형사 리포트가
    구조적으로 유리해진다. 우리가 재려는 것은 밀도이지 분량이 아니다.
    """
    if TXT is None or TXT.empty:
        return pd.DataFrame(columns=SCORE_COLS)
    sw = NCQ_LEXICON.get("section_weight", {"TITLE": 3.0, "HEADLINE": 2.0, "BODY": 1.0})
    negw = int(NCQ_LEXICON.get("negation_window", 30))
    groups = NCQ_LEXICON["groups"]

    T = TXT.copy()
    for c in ("sec_title", "sec_headline", "sec_body"):
        if c not in T.columns:
            T[c] = ""
        T[c] = T[c].fillna("").astype(str)

    def _row(r):
        raw = 0.0
        counts = {}
        for g, spec in groups.items():
            rx = _NCQ_GRP_RE.get(g)
            ct = _ncq_count_group(r[0], rx, negw)
            ch = _ncq_count_group(r[1], rx, negw)
            cb = _ncq_count_group(r[2], rx, negw)
            counts[g] = ct + ch + cb
            raw += float(spec["weight"]) * (sw["TITLE"] * ct + sw["HEADLINE"] * ch +
                                            sw["BODY"] * cb)
        return raw, counts

    tri = list(zip(T["sec_title"], T["sec_headline"], T["sec_body"]))
    out_raw, out_cnt = [], []
    for r in tqdm(tri, desc="텍스트 스코어링", ncols=88, leave=False):
        a, b = _row(r)
        out_raw.append(a)
        out_cnt.append(b)

    S = pd.DataFrame({"report_uid": T["report_uid"].astype(str), "code": T["code"],
                      "pub_date": as_ts_series(T["pub_date"]), "doc_raw": out_raw})
    for g in groups:
        S[f"g_{g}"] = [c.get(g, 0) for c in out_cnt]
    S["n_chars"] = (T["sec_title"].str.len() + T["sec_headline"].str.len() +
                    T["sec_body"].str.len()).to_numpy()
    # ★★ 길이 정규화의 하한을 1.0(=1,000자)으로 둔다. 이유가 있다.
    #   명세 §9.3 은 doc_raw / (총 문자수/1000) 이라고만 정의하고 하한을 말하지 않는다.
    #   그런데 PDF 추출이 실패해 '제목만' 남은 문서는 총 문자수가 30자 남짓이라 분모가 0.03 이
    #   되고, 제목에 어휘가 하나만 있어도 점수가 30배로 폭발한다. 그러면 상위 tercile 이
    #   '내용이 좋은 리포트'가 아니라 '본문 추출에 실패한 리포트'로 채워진다 — 신호가 아니라
    #   수집 실패를 사는 셈이다. 하한을 1,000자로 두면 짧은 문서가 공짜 배수를 얻지 못한다.
    #   (하한 자체는 구현 결정이므로 그 사실과 값을 여기에 명시하고 매니페스트에도 남긴다)
    denom = (S["n_chars"] / 1000.0).clip(lower=1.0)
    S["doc_score"] = S["doc_raw"] / denom
    S["title_only"] = ((T["sec_headline"].str.len() + T["sec_body"].str.len()).to_numpy() < 100)

    # ★★ 본문을 못 읽은 문서는 **채점하지 않는다**(결측으로 남긴다). 이유가 결정적이다.
    #   감점 그룹 H(기대·전망·예상·추정)와 N(지연·부진·둔화·우려·리스크)은 본문에만 나온다.
    #   제목은 마케팅 문구라 가점 그룹만 맞는다. 그래서 제목만 남은 문서는 감점이 구조적으로
    #   0이고, 본문을 제대로 읽은 문서는 H·N 이 수십 번 잡혀 점수가 음수로 내려간다.
    #   실측: 같은 제목에 대해 제목만 = +22.5점, 본문 확보(중립~긍정 리포트) = -30.5점.
    #   그대로 두면 상위 tercile 이 '좋은 리포트'가 아니라 **PDF 수집에 실패한 리포트**로
    #   채워진다 — 신호가 아니라 수집 실패를 사는 것이다. 길이 정규화 하한으로는 못 막는다.
    #   결측으로 두면 그 이벤트는 텍스트 점수 없음으로 SIG 에서 빠지고, 결손율은 그대로 보고된다.
    _n_to = int(S["title_only"].sum())
    S.loc[S["title_only"], "doc_score"] = np.nan
    S["month"] = S["pub_date"] + pd.offsets.MonthEnd(0)
    S = S.dropna(subset=["code", "month"])
    LOG.ok(f"텍스트 스코어링 {len(S):,}건 중 채점 {int(S['doc_score'].notna().sum()):,}건 — "
           f"doc_score 평균 {S['doc_score'].mean():.3f} / 표준편차 {S['doc_score'].std():.3f} · "
           f"길이 정규화 하한 1,000자")
    manifest_put("score_title_only_share", round(_n_to / max(len(S), 1), 4))
    if _n_to:
        LOG.warn(f"본문을 못 읽은 {_n_to:,}건({100*_n_to/max(len(S),1):.0f}%)은 **채점에서 제외**"
                 f"했습니다. 제목만으로 채점하면 감점 어휘(H·N)가 본문에만 있어 수집 실패 건이 "
                 f"상위 tercile 을 구조적으로 점령합니다. 0점이 아니라 결측으로 둡니다.")
    PIPE.io("OUT", "MEM", "text_scores", S)
    return S.reindex(columns=SCORE_COLS + [])


# ── Phase 5 — 횡단면 상대비교 → 상위 tercile ────────────────────────────────────────────────
def build_signal_panel(SCORE: pd.DataFrame, EV: pd.DataFrame, UNI: pd.DataFrame,
                       pxm: pd.DataFrame, months: pd.DatetimeIndex,
                       top_pct: Optional[float] = None) -> pd.DataFrame:
    """명세 §9.4 — **절대 임계를 쓰지 않는다.** 같은 달 이벤트 풀 안에서만 z-score 로 비교한다.

    · 월 이벤트가 5건 미만이면 z 가 불안정하므로 직전 3개월 롤링 풀로 계산하고 pooled=True 태깅.
    · 편입 = z 상위 tercile.  대조군(Placebo) = z 하위 tercile.
    """
    tp = float(top_pct if top_pct is not None else NCQ_TERCILE)
    if EV is None or EV.empty:
        return pd.DataFrame(columns=SIG_COLS)

    E = EV.copy()
    if SCORE is not None and len(SCORE):
        # 같은 달 복수 리포트면 **최댓값**. 평균이 아니다 — 가장 강한 주장이 정보다(§9.3).
        agg = (SCORE.groupby(["code", "month"], observed=True)["doc_score"]
                    .max().rename("event_score").reset_index())
        E = E.merge(agg, on=["code", "month"], how="left")
    else:
        E["event_score"] = np.nan
    n_noscore = int(E["event_score"].isna().sum())
    if n_noscore:
        LOG.warn(f"이벤트 {n_noscore:,}건에 텍스트 점수가 없습니다(본문 미확보). "
                 f"z 계산에서 제외되며 결손으로 남습니다 — 0점으로 채우지 않습니다.")

    E = E.dropna(subset=["event_score"]).copy()
    if E.empty:
        LOG.error("텍스트 점수가 있는 이벤트가 하나도 없습니다. Phase 3(PDF) 이 전부 실패한 상태입니다.")
        return pd.DataFrame(columns=SIG_COLS)

    E = E.sort_values(["month", "code"]).reset_index(drop=True)
    mi = _ncq_mi(E["month"])
    E["_mi"] = mi
    rows = []
    for m, g in E.groupby("month", observed=True):
        pool = g
        pooled = False
        if len(g) < NCQ_ZPOOL_MIN_N:
            m0 = float(_ncq_mi(pd.Series([m])).iloc[0])
            pool = E[(E["_mi"] <= m0) & (E["_mi"] > m0 - 3)]
            pooled = len(pool) > len(g)
        v = pd.to_numeric(pool["event_score"], errors="coerce")
        mu, sd = float(v.mean()), float(v.std(ddof=0))
        own = pd.to_numeric(g["event_score"], errors="coerce")
        z = (own - mu) / (sd if sd > 0 else np.nan)
        # 표준편차가 0(전원 동일 점수)이면 변별이 불가능하다. 0으로 두고 선정에서 전원 동률 처리.
        z = z.fillna(0.0) if (not np.isfinite(sd) or sd <= 0) else z

        # ★★ 백분위는 **z 를 만든 그 풀** 안에서 매긴다(당월이 아니라).
        #   과거에는 랭크를 당월 안에서만 매겼는데, rank(pct=True) 의 최솟값이 1/n 이라
        #   이벤트가 1~2건인 달은 하위 tercile(placebo)이 **구조적으로 공집합**이 된다.
        #   그러면 그 달 전략 팔은 종목을 담고 placebo 팔은 현금이 되어, P2·채택조건③ 의
        #   '스프레드'에 선별력과 무관한 시장 베타가 그대로 얹힌다. 선별력이 0인 전략도
        #   상승장이면 통과할 수 있다는 뜻이다. 풀 기준 경험분포로 매기면 이벤트가 1건인
        #   달도 그 풀 안에서 상·하위가 정의되어 두 팔이 대칭을 유지한다.
        pv = v.dropna().to_numpy()
        if len(pv) >= 2 and np.nanstd(pv) > 0:
            rp = np.array([float((pv <= x).mean()) if np.isfinite(x) else np.nan
                           for x in own.to_numpy()], dtype=float)
        else:
            rp = np.full(len(g), 0.5)      # 변별 불가 → 어느 tercile 에도 넣지 않는다
        t = g.copy()
        t["z"] = z.to_numpy()
        t["rank_pct"] = rp
        t["pooled"] = pooled
        t["pool_n"] = int(len(pool))
        rows.append(t)
    Z = pd.concat(rows, ignore_index=True) if rows else E
    if "rank_pct" not in Z.columns:
        Z["rank_pct"] = np.nan

    # 상·하위 tercile (풀 기준 경험 백분위)
    Z["selected"] = Z["rank_pct"] >= (1.0 - tp)
    Z["placebo"] = Z["rank_pct"] <= tp
    # 두 팔의 대칭성을 실제로 확인한다 — 비대칭이면 P2 가 베타를 재게 되므로 그대로 보고한다.
    _bal = Z.groupby("month", observed=True).agg(
        s=("selected", "sum"), p=("placebo", "sum")).reset_index()
    _bad = _bal[(_bal["s"] > 0) & (_bal["p"] <= 0)]
    if len(_bad):
        LOG.warn(f"선정군은 있는데 대조군(placebo)이 비는 달이 {len(_bad)}개 있습니다 "
                 f"(예: {', '.join(str(x)[:7] for x in _bad['month'].head(4))}). "
                 f"그 달의 P2 스프레드에는 선별력이 아니라 시장 베타가 섞입니다 — "
                 f"이벤트 수가 너무 적은 구간이니 결과 해석 시 감안하세요.")
        manifest_put("months_placebo_empty", int(len(_bad)))

    # 월 신규 편입 상한 (§10 — 초과 시 z 상위 N 으로 절단)
    if NCQ_MAX_NEW_PER_MONTH and NCQ_MAX_NEW_PER_MONTH > 0:
        sel = Z[Z["selected"]].copy()
        over = sel.groupby("month", observed=True)["code"].size()
        over = over[over > NCQ_MAX_NEW_PER_MONTH]
        if len(over):
            keep_idx = (sel[sel["month"].isin(over.index)]
                        .sort_values(["month", "z", "code"], ascending=[True, False, True])
                        .groupby("month", observed=True).head(NCQ_MAX_NEW_PER_MONTH).index)
            drop_idx = sel[sel["month"].isin(over.index)].index.difference(keep_idx)
            Z.loc[drop_idx, "selected"] = False
            LOG.info(f"월 신규 편입 상한({NCQ_MAX_NEW_PER_MONTH}종목) 적용 — "
                     f"{len(drop_idx):,}건을 z 하위부터 절단했습니다.")

    if pxm is not None and len(pxm):
        # ★ (code, month) 가 유일하지 않으면 merge 가 행을 증식시켜 이벤트가 복제된다.
        _px1 = pxm.drop_duplicates(["code", "month"], keep="last")
        _n0 = len(Z)
        Z = Z.merge(_px1[["code", "month", "exec_px", "fwd_ret", "signal_date"]],
                    on=["code", "month"], how="left")
        if len(Z) != _n0:
            LOG.warn(f"가격 결합에서 행수가 {_n0:,}→{len(Z):,} 로 변했습니다 — 중복 키입니다.")
            Z = Z.drop_duplicates(["month", "code"], keep="first")
    for c in ("exec_px", "fwd_ret"):
        if c not in Z.columns:
            Z[c] = np.nan
    if "adv20" not in Z.columns:
        Z["adv20"] = np.nan

    # (본문 없는 문서는 score_texts 에서 이미 결측 처리되므로, 선정군이 '추출 실패 문서'로
    #  채워지는 경로 자체가 존재하지 않는다. 결손율은 Phase 3 표에 그대로 남는다.)
    n_sel = int(Z["selected"].sum())
    n_pool = int(Z["pooled"].sum())
    LOG.ok(f"신호 패널 {len(Z):,}행 — 편입 {n_sel:,}건(상위 {100*tp:.0f}%) · "
           f"대조군 {int(Z['placebo'].sum()):,}건 · 풀링 사용 {n_pool:,}건")
    if n_pool > 0.3 * len(Z):
        LOG.warn(f"이벤트가 적어 {100*n_pool/max(len(Z),1):.0f}% 의 달에서 3개월 롤링 풀로 z 를 "
                 f"계산했습니다. 동월 횡단면 비교라는 설계 취지가 그만큼 희석됩니다.")
    VAULT.put_table(f"signal_panel_{STRATEGY_ID}", Z, scope="private", domain="signals",
                    source="build_signal_panel", extra={"top_pct": tp})
    PIPE.io("OUT", "MEM", "signal_panel", Z)
    keep = [c for c in SIG_COLS if c in Z.columns]
    extra = [c for c in ("n_reports", "n_brokers", "sources", "broker_ids", "report_uids",
                         "mcap", "signal_date", "is_denovo") if c in Z.columns]
    return Z[keep + extra]
