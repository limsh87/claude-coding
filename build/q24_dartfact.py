

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q3  DART 하드팩트 ΔNONFIN + 배제 플래그 (§6.1)  —  LLM 호출 없음                       ║
# ║                                                                                          ║
# ║  추출 원칙(엄격): 완료형 동사 + 날짜 + 숫자가 모두 있는 사실만 추출한다.                    ║
# ║  전망·계획·의지·기대·예정은 전부 제외한다. 추출기는 좋다/나쁘다를 판단하지 않는다.          ║
# ║                                                                                          ║
# ║  ★ 설계 핵심: '구조화 엔드포인트로 얻을 수 있는 것을 본문 파싱으로 얻으려 하지 않는다'.     ║
# ║    연구개발비/매출액·설비투자·자본잠식률은 이미 받아둔 재무제표로 계산된다. CB/BW 발행,     ║
# ║    최대주주 변경, 단일판매·공급계약은 공시목록(list.json) 한 번의 스윕으로 잡힌다.          ║
# ║    본문(document.xml)이 정말로 필요한 것은 주석에만 있는 4가지뿐이다:                       ║
# ║      특허 등록건수 · 연구개발 인력 · 특수관계자 거래비중 · 우발부채/소송/감사의견 강조사항   ║
# ║    이 구분을 흐리면 호출량이 10배가 되고 콜드빌드가 몇 주가 된다.                           ║
# ║                                                                                          ║
# ║  ★ 구형 공시는 스캔 PDF 비중이 높아 기계판독이 불가능하다(§0.4). 실패율을 반드시 측정하고   ║
# ║    '섹션 없음' / '판독 불가' / 'API 무응답' 을 구분해서 보고한다 — 셋은 원인이 다르다.      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 원문 XML 을 드라이브에 통째로 보관할지. 사업보고서 하나가 수 MB 이고 1만 건이면 수십 GB 라
# 기본은 False 다. 우리가 캐시하는 것은 '추출된 사실 테이블'이며 그것이 공용 인덱스에 남는다.
DART_STORE_RAW_DOCS = False

DOC_API = "document.xml"

# 미래형/의지 표현 — 하나라도 걸리면 그 문장은 사실이 아니다(§6.1)
_FORWARD_RE = re.compile(
    r"예정|계획|전망|기대|목표|추진\s*(?:할|중|예정)|예상|가능성|모색|검토\s*중|"
    r"할\s*것|하고자|하려|추정|예측|목표로")
# 완료형 동사
_DONE_RE = re.compile(
    r"하였|했[다으]|되었|됐[다으]|완료|체결|취득|등록(?:되|하|을|된|함)|선정(?:되|하|된|됨)|"
    r"납품|수주|출원(?:하|되|됨)|승인(?:받|되)|인수(?:하|함)|설립(?:하|됨)")
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DATE_RE = re.compile(r"(?:19|20)\d{2}\s*[.\-/년]\s*(?:\d{1,2})\s*[.\-/월]?|(?:19|20)\d{2}\s*년")


def is_completed_fact(sent: str) -> bool:
    """§6.1 — 완료형 동사 + 날짜 + 숫자가 모두 있고, 미래형 표현이 없어야 사실로 인정한다."""
    if not sent or len(sent) > 800:
        return False
    if _FORWARD_RE.search(sent):
        return False
    return bool(_DONE_RE.search(sent) and _NUM_RE.search(sent) and _DATE_RE.search(sent))


# ── 공시목록 스윕 (거래소공시·외부감사 포함) ────────────────────────────────────────────────
QVF_DISCLOSURE_PATTERNS = {
    # 긍정 하드팩트
    "supply_contract":  r"단일판매[·ㆍ・]?\s*공급계약|공급계약\s*체결|수주",
    # 배제 플래그
    "cb_issue":         r"전환사채",
    "bw_issue":         r"신주인수권부사채",
    "major_holder_chg": r"최대주주\s*(?:변경|변동)",
    "audit_report":     r"감사보고서|감사의견",
    "lawsuit_filed":    r"소송\s*(?:등의?\s*)?(?:제기|판결)",
    "capital_impair":   r"자본잠식",
}
QVF_DISCLOSURE_TYPES = ("A", "B", "F", "I")   # 정기 · 주요사항 · 외부감사 · 거래소공시


def fetch_disclosures_qvf(start: str, end: str) -> pd.DataFrame:
    """월 단위 시장 전체 공시목록 스윕. 공용 코어의 dart_disclosures 와 '별도 테이블'을 쓴다.

    ★ 같은 테이블을 쓰면 안 되는 이유: 코어는 A·B 만 훑는데, 그 캐시에 이미 있는 달을
      QVF 가 '완료'로 보면 거래소공시(I)·외부감사(F)를 영원히 못 받는다. 캐시 키가
      '어떤 유형까지 훑었는가' 를 담고 있지 않으므로 테이블 자체를 분리한다.
    """
    cols = ["corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm", "event", "pblntf_ty"]
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 공시목록 스윕 불가. ΔNONFIN 의 공급계약 항목과 "
                 "CB/BW·최대주주변경 배제플래그가 전부 결측이 됩니다.")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_disclosures_qvf", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have = set(cached["rcept_dt"].dropna().dt.to_period("M").astype(str))
        LOG.info(f"캐시에서 QVF 공시목록 {len(cached):,}행 · {len(have)}개월 재사용")

    months = pd.period_range(as_ts(start) - pd.DateOffset(months=6), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have]
    if RUN_MODE == "CACHED":
        todo = []

    breaker = {"fail": 0}

    def _one(m):
        rows = []
        for ty in QVF_DISCLOSURE_TYPES:
            page, empty = 1, 0
            while page <= 100:
                if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                    return rows
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100, "last_reprt_at": "N"})
                if not js or not isinstance(js.get("list"), list) or not js["list"]:
                    empty += 1
                    breaker["fail"] += 1 if not js else 0
                    break
                breaker["fail"] = 0
                for r in js["list"]:
                    r["pblntf_ty"] = ty
                rows.extend(js["list"])
                if page >= int(js.get("total_page", 1) or 1):
                    break
                page += 1
        return rows

    new = []
    if todo:
        LOG.info(f"QVF 공시목록 스윕 {len(todo)}개월 × 유형 {len(QVF_DISCLOSURE_TYPES)} "
                 f"(남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        for chunk in pmap_io(_one, todo, workers=min(N_WORKERS_IO, 6), desc="DART 공시목록(QVF)"):
            if chunk:
                new.extend(chunk)
        if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
            LOG.warn(f"서킷 브레이커 발동 — 연속 실패 {CIRCUIT_BREAKER_FAILS}회. 공시목록 스윕을 "
                     f"중단하고 받은 만큼만 사용합니다.")

    frames = [cached] if cached is not None and len(cached) else []
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "pblntf_ty") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=cols)
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in QVF_DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures_qvf", D, scope="shared", domain="dart",
                        source="opendart list.json A/B/F/I")
    # §4 — 접수일 다음 거래일부터 사용 가능
    D["knowledge_date"] = next_trading_day_series(D["rcept_dt"])
    D = pit_frame(D, "rcept_dt", "knowledge_date", source="dart")
    counts = {k: int((D["event"] == k).sum()) for k in QVF_DISCLOSURE_PATTERNS}
    LOG.ok(f"QVF 공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={v:,}" for k, v in counts.items() if v))
    PIPE.io("OUT", "DRIVE", "dart_disclosures_qvf", D, source="opendart list.json")
    return downcast_q(D)


# ── 사업보고서 본문 (주석에만 있는 항목) ────────────────────────────────────────────────────
_SECTIONS = {
    "ip":        r"(지식재산권|산업재산권|특허|공업소유권)",
    "rnd":       r"(연구개발\s*(?:활동|조직|인력|실적)|기술개발\s*조직)",
    "related":   r"(특수관계자|특수관계인)\s*(?:와의)?\s*(?:거래|매출|매입)",
    "contingent": r"(우발부채|지급보증|약정사항|담보제공)",
    "lawsuit":   r"(소송|계류중인\s*소송|법적\s*분쟁)",
    "audit":     r"(강조사항|특기사항|감사의견|핵심감사사항)",
    "holder":    r"(최대주주\s*(?:에?\s*관한\s*사항|현황)|주주에\s*관한\s*사항)",
}
_SECTION_RE = {k: re.compile(v) for k, v in _SECTIONS.items()}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def _xml_to_text(raw: bytes) -> Tuple[str, str]:
    """DART document.xml (ZIP) → 평문. (텍스트, 상태) 를 돌려준다.

    상태: ok / not_zip / empty_zip / decode_fail / no_text(스캔본 추정)
    ★ '스캔본'과 '섹션 없음'을 구분하는 유일한 방법이 여기다. 태그를 걷어낸 뒤 남는 글자가
      거의 없으면 그 파일은 이미지이며, 정규식을 아무리 고쳐도 절대 읽히지 않는다.
    """
    if not raw or len(raw) < 64:
        return "", "empty"
    if raw[:2] != b"PK":
        head = raw[:300].decode("utf-8", "ignore")
        if "status" in head:
            return "", "api_error"
        return "", "not_zip"
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in zf.namelist() if n.lower().endswith((".xml", ".html", ".htm"))]
        if not names:
            return "", "empty_zip"
        blob = b"".join(zf.read(n) for n in names[:6])
    except Exception:
        return "", "empty_zip"
    txt = ""
    for enc in ("utf-8", "euc-kr", "cp949", "utf-16"):
        try:
            t = blob.decode(enc)
        except Exception:
            continue
        if len(_HANGUL.findall(t[:8000])) > 20:
            txt = t
            break
        if not txt:
            txt = t
    if not txt:
        return "", "decode_fail"
    txt = _TAG_RE.sub(" ", txt)
    txt = _WS_RE.sub(" ", txt)
    han = len(_HANGUL.findall(txt))
    if han < 500:
        # 태그를 걷어냈는데 한글이 거의 없다 = 본문이 이미지(스캔본)
        return txt, "no_text_scan"
    return txt, "ok"


def _section(text: str, key: str, span: int = 6000) -> str:
    m = _SECTION_RE[key].search(text)
    if not m:
        return ""
    return text[m.start(): m.start() + span]


def _count_patents(sect: str) -> Optional[float]:
    if not sect:
        return None
    m = re.search(r"특허\D{0,12}?([\d,]{1,6})\s*건", sect)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            pass
    n = len(re.findall(r"특허\s*(?:권|등록|제?\s*\d{2,})", sect))
    return float(n) if n else None


def _rnd_headcount(sect: str) -> Optional[float]:
    if not sect:
        return None
    for pat in (r"연구\s*(?:개발)?\s*인력\D{0,12}?([\d,]{1,6})\s*명",
                r"연구소\D{0,20}?([\d,]{1,6})\s*명",
                r"(?:연구원|연구개발\s*인원)\D{0,10}?([\d,]{1,6})\s*명"):
        m = re.search(pat, sect)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _ratio_pct(sect: str, pats: Sequence[str]) -> Optional[float]:
    for p in pats:
        m = re.search(p, sect)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                return v / 100.0 if v > 1.5 else v
            except Exception:
                continue
    return None


def _amount_krw(sect: str, pats: Sequence[str]) -> Optional[float]:
    """'12,345백만원' / '1,234억원' 같은 표기를 원 단위로 환산한다."""
    for p in pats:
        for m in re.finditer(p, sect):
            try:
                v = float(m.group(1).replace(",", ""))
            except Exception:
                continue
            tail = sect[m.end(): m.end() + 8]
            if "억" in m.group(0) or "억" in tail:
                v *= 1e8
            elif "백만" in m.group(0) or "백만" in tail:
                v *= 1e6
            elif "천원" in m.group(0) or "천원" in tail:
                v *= 1e3
            return v
    return None


def extract_report_facts(text: str) -> dict:
    """사업보고서 본문 → 하드팩트 수치. 판단하지 않고 숫자만 뽑는다."""
    out: Dict[str, Any] = {}
    ip = _section(text, "ip")
    out["patents"] = _count_patents(ip)
    out["sect_ip"] = bool(ip)

    rnd = _section(text, "rnd")
    out["rnd_headcount"] = _rnd_headcount(rnd)
    out["sect_rnd"] = bool(rnd)
    # 정부 R&D 과제: 완료형 사실 문장만 인정
    gov = 0
    for s in _SENT_SPLIT.split(rnd)[:400]:
        if re.search(r"(국책|정부|국가)\s*(과제|연구개발사업|R&D)", s) and is_completed_fact(s):
            gov += 1
    out["gov_rnd_facts"] = float(gov)

    rel = _section(text, "related")
    out["sect_related"] = bool(rel)
    out["related_sales_ratio"] = _ratio_pct(
        rel, [r"매출\D{0,20}?([\d,.]+)\s*%", r"비중\D{0,10}?([\d,.]+)\s*%"])
    out["related_purchase_ratio"] = _ratio_pct(
        rel, [r"매입\D{0,20}?([\d,.]+)\s*%"])

    cg = _section(text, "contingent")
    out["sect_contingent"] = bool(cg)
    out["contingent_amt"] = _amount_krw(
        cg, [r"지급보증\D{0,24}?([\d,]{3,})", r"우발부채\D{0,24}?([\d,]{3,})"])

    ls = _section(text, "lawsuit")
    out["sect_lawsuit"] = bool(ls)
    out["lawsuit_amt"] = _amount_krw(
        ls, [r"소송\s*가?액\D{0,24}?([\d,]{3,})", r"청구\s*금액\D{0,24}?([\d,]{3,})"])
    out["lawsuit_new"] = float(sum(1 for s in _SENT_SPLIT.split(ls)[:300]
                                   if re.search(r"소송.{0,20}제기", s) and is_completed_fact(s)))

    au = _section(text, "audit")
    out["sect_audit"] = bool(au)
    out["audit_emphasis"] = float(bool(
        re.search(r"(강조사항|특기사항|계속기업|핵심감사사항)", au) and
        not re.search(r"해당사항\s*없|없습니다", au[:400])))

    hd = _section(text, "holder")
    out["sect_holder"] = bool(hd)
    out["major_holder_pct"] = _ratio_pct(
        hd, [r"최대주주\D{0,40}?([\d,.]+)\s*%", r"소유\s*비율\D{0,10}?([\d,.]+)\s*%"])
    return out


def fetch_annual_report_facts(targets: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """targets: corp_code · bsns_year · rcept_no · rcept_dt (사업보고서 접수건)
    반환: (사실 테이블, 파싱 통계)

    ★ 파싱 결과를 항상 한 행 남긴다. 실패도 행이다 — 실패를 남기지 않으면 재실행마다
      같은 스캔본을 영원히 다시 받고, dart_parse_rate 도 정직하게 계산할 수 없다.
    """
    FACT_COLS = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "parse_status",
                 "patents", "rnd_headcount", "gov_rnd_facts", "related_sales_ratio",
                 "related_purchase_ratio", "contingent_amt", "lawsuit_amt", "lawsuit_new",
                 "audit_emphasis", "major_holder_pct",
                 "sect_ip", "sect_rnd", "sect_related", "sect_contingent", "sect_lawsuit",
                 "sect_audit", "sect_holder"]
    if targets is None or targets.empty or not DART_API_KEY:
        if not DART_API_KEY:
            LOG.warn("DART_API_KEY 미입력 — 사업보고서 본문 파싱을 건너뜁니다. "
                     "ΔNONFIN 의 특허·연구인력 항목과 특수관계자·우발부채·소송·감사의견 "
                     "배제플래그가 결측이 됩니다(0 으로 채우지 않음).")
        return pd.DataFrame(columns=FACT_COLS), {}

    cached = VAULT.get_table("dart_report_facts", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(cached["rcept_no"].astype(str))
        LOG.info(f"캐시에서 사업보고서 사실 {len(cached):,}건 재사용 "
                 f"(재파싱하지 않습니다 — 스캔본 실패도 기억합니다)")

    todo = targets[~targets["rcept_no"].astype(str).isin(done)].copy()
    if RUN_MODE == "CACHED":
        todo = todo.iloc[0:0]
    stats: Counter = Counter()
    rows: List[dict] = []

    if len(todo):
        LOG.info(f"사업보고서 본문 신규 파싱 대상 {len(todo):,}건 "
                 f"(남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        breaker = {"fail": 0}

        def _one(rec):
            corp, yr, rno, rdt = rec
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                return None
            if DQUOTA is not None and not DQUOTA.take(1):
                return None
            raw = http_get("https://opendart.fss.or.kr/api/" + DOC_API, source="dart",
                           params={"crtfc_key": DART_API_KEY, "rcept_no": str(rno)},
                           as_bytes=True, tries=2, referer="https://opendart.fss.or.kr/")
            if not raw:
                breaker["fail"] += 1
                return {"corp_code": corp, "bsns_year": yr, "rcept_no": rno,
                        "rcept_dt": rdt, "parse_status": "api_empty"}
            breaker["fail"] = 0
            text, status = _xml_to_text(raw)
            if status == "api_error" and DQUOTA is not None:
                try:
                    if re.search(r'"020"', raw[:300].decode("utf-8", "ignore")):
                        DQUOTA.exhausted = True
                except Exception:
                    pass
            base = {"corp_code": corp, "bsns_year": yr, "rcept_no": rno,
                    "rcept_dt": rdt, "parse_status": status}
            if status != "ok":
                return base
            if DART_STORE_RAW_DOCS:
                VAULT.put_blob("dart", "document_xml", str(rno), raw, "zip",
                               source="opendart document.xml", scope="shared",
                               event_date=rdt, knowledge_date=rdt)
            f = extract_report_facts(text)
            del text, raw
            base.update(f)
            return base

        jobs = list(zip(todo["corp_code"].astype(str), todo["bsns_year"].astype(int),
                        todo["rcept_no"].astype(str), todo["rcept_dt"]))
        CHUNK = 500          # 본문은 수 MB 다. 청크로 끊어 상주 메모리를 평평하게 유지한다.
        for k0 in range(0, len(jobs), CHUNK):
            part = jobs[k0:k0 + CHUNK]
            res = pmap_io(_one, part, workers=min(N_WORKERS_IO, 8),
                          desc=f"사업보고서 본문 {k0//CHUNK+1}/{(len(jobs)-1)//CHUNK+1}")
            rows.extend([r for r in res if r])
            del res
            gc.collect()
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"서킷 브레이커 발동(연속 실패 {CIRCUIT_BREAKER_FAILS}회) — 본문 파싱 중단.")
                break
            if DQUOTA is not None and DQUOTA.exhausted:
                LOG.warn("DART 호출 한도 도달 — 본문 파싱을 여기서 멈춥니다. "
                         "받은 만큼 저장하고 다음 실행에서 이어받습니다.")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=FACT_COLS), {}
    F = pd.concat(frames, ignore_index=True)
    for c in FACT_COLS:
        if c not in F.columns:
            F[c] = np.nan
    F = F.drop_duplicates("rcept_no", keep="last")
    if rows:
        VAULT.put_table("dart_report_facts", F, scope="shared", domain="dart",
                        source="opendart document.xml + 규칙기반 추출")
    for s in F["parse_status"].astype(str):
        stats[s] += 1
    PIPE.io("OUT", "DRIVE", "dart_report_facts", F, source="opendart document.xml")
    return downcast_q(F), dict(stats)


def report_parse_rate(F: pd.DataFrame, stats: dict) -> float:
    """§2.1 dart_parse_rate 를 정직하게 분해 보고한다(게이트 ≥ 0.80)."""
    total = int(sum(stats.values())) if stats else 0
    if not total:
        LOG.warn("DART 본문 파싱 시도 기록이 없습니다 — dart_parse_rate 를 산출할 수 없습니다.")
        return float("nan")
    ok = int(stats.get("ok", 0))
    rate = ok / total
    label = {"ok": "정상 판독", "no_text_scan": "스캔본(이미지) — 기계판독 불가",
             "not_zip": "ZIP 아님(대개 API 오류 응답)", "empty_zip": "ZIP 내 문서 없음",
             "decode_fail": "인코딩 판별 실패", "api_empty": "API 무응답/네트워크 실패",
             "api_error": "API 오류코드 응답", "empty": "빈 응답"}
    LOG.table([[label.get(k, k), f"{v:,}", f"{100*v/total:.1f}%"]
               for k, v in sorted(stats.items(), key=lambda x: -x[1])],
              ["파싱 결과", "건수", "비중"], ["l", "r", "r"],
              title=f"DART 본문 기계판독 성공률 = {100*rate:.1f}%  (§2.1 게이트 기준 80%)")
    if len(F):
        sect = [(c, "섹션 발견율") for c in ("sect_ip", "sect_rnd", "sect_related",
                                             "sect_contingent", "sect_lawsuit",
                                             "sect_audit", "sect_holder")]
        okF = F[F["parse_status"].astype(str) == "ok"]
        if len(okF):
            LOG.table([[c.replace("sect_", ""),
                        f"{100*pd.to_numeric(okF[c], errors='coerce').fillna(0).mean():.1f}%"]
                       for c, _ in sect],
                      ["섹션", "정상판독 문서 내 발견율"], ["l", "r"],
                      title="섹션별 발견율 — '판독 실패'와 '해당 섹션 없음'은 다른 사건이다")
    if rate < 0.80:
        LOG.warn(f"dart_parse_rate {100*rate:.1f}% < 80% (§2.1 게이트 미달). "
                 f"주된 사유는 위 표에 분해되어 있습니다. 스캔본 비중이 높다면 정규식을 고쳐도 "
                 f"개선되지 않습니다 — 해당 컴포넌트(특허·연구인력·특수관계자 등)는 결측 처리되고 "
                 f"ΔNONFIN 은 가용 항목만으로 계산됩니다. 전략 전체는 중단하지 않습니다(§2.2).")
    return rate


# ── ΔNONFIN 조립 ────────────────────────────────────────────────────────────────────────────
NONFIN_ITEMS = ["rnd_headcount_up", "rnd_ratio_up", "patent_up", "capex_up",
                "supply_contract", "gov_rnd"]


def build_nonfin_panel(G: pd.DataFrame, facts: pd.DataFrame, dis: pd.DataFrame,
                       fq: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """ΔNONFIN(f,q) = 항목별 증분 이벤트 개수의 합 (동일가중, 바이너리 태그).

    ★ 전분기(전년) 값이 없으면 '증가'로 세지 않는다. 결측을 0 으로 보고 차분하면
      데이터가 처음 생긴 시점이 전부 '급증'으로 잡혀, 커버리지가 곧 신호가 된다.
    """
    d = G.copy()
    for c in NONFIN_ITEMS + ["dNONFIN"]:
        d[c] = np.nan

    # ① 재무 기반 (추가 호출 없음): 연구개발비/매출액 비율 상승 · 설비투자(유형자산 취득) 증가
    if fq is not None and len(fq):
        Q = fq[["corp_code", "knowledge_date"]].copy()
        Q["rnd_ratio"] = safe_div(col(fq, "rnd_ttm"), col(fq, "revenue_ttm"))
        Q["capex_v"] = col(fq, "capex_ttm").abs()
        Q["knowledge_date"] = as_ts_series(Q["knowledge_date"])
        Q = (Q.dropna(subset=["corp_code", "knowledge_date"])
              .sort_values(["corp_code", "knowledge_date"], kind="stable"))
        g = Q.groupby("corp_code", observed=True)
        for src, dst in (("rnd_ratio", "rnd_ratio_up"), ("capex_v", "capex_up")):
            prev = g[src].shift(1)
            Q[dst] = ((Q[src] > prev) & Q[src].notna() & prev.notna()).astype(float)
            Q[dst] = Q[dst].where(Q[src].notna() & prev.notna())
        d = _asof_attach(d, Q[["corp_code", "knowledge_date", "rnd_ratio_up", "capex_up"]],
                         sec, ["rnd_ratio_up", "capex_up"])

    # ② 사업보고서 본문 기반 (연 1회): 특허 등록 증가 · 연구개발 인력 순증 · 정부 R&D 과제
    if facts is not None and len(facts):
        A = facts[facts["parse_status"].astype(str) == "ok"].copy()
        if len(A):
            A["knowledge_date"] = next_trading_day_series(A["rcept_dt"])
            A = (A.dropna(subset=["corp_code", "knowledge_date"])
                  .sort_values(["corp_code", "knowledge_date"], kind="stable"))
            ga = A.groupby("corp_code", observed=True)
            for src, dst in (("patents", "patent_up"), ("rnd_headcount", "rnd_headcount_up")):
                cur = pd.to_numeric(A[src], errors="coerce")
                prev = ga[src].shift(1)
                prev = pd.to_numeric(prev, errors="coerce")
                A[dst] = ((cur > prev) & cur.notna() & prev.notna()).astype(float)
                A[dst] = A[dst].where(cur.notna() & prev.notna())
            A["gov_rnd"] = (pd.to_numeric(A["gov_rnd_facts"], errors="coerce").fillna(0) > 0).astype(float)
            # ★ 배제플래그의 '전분기 대비 상승' 은 연 1회 관측인 원 프레임에서 차분해야 한다.
            #   as-of 로 패널에 퍼뜨린 뒤 diff 하면 같은 값이 4분기 반복되어 3번은 0, 1번만
            #   진짜 변화가 되고, 그 1번이 어느 분기에 떨어지는지가 접수일에 좌우된다.
            for src in ("related_sales_ratio", "related_purchase_ratio", "contingent_amt"):
                A[f"{src}_prev"] = ga[src].shift(1)
            keep = ["corp_code", "knowledge_date", "patent_up", "rnd_headcount_up", "gov_rnd",
                    "related_sales_ratio", "related_purchase_ratio", "contingent_amt",
                    "related_sales_ratio_prev", "related_purchase_ratio_prev",
                    "contingent_amt_prev",
                    "lawsuit_amt", "lawsuit_new", "audit_emphasis", "major_holder_pct"]
            d = _asof_attach(d, A[keep], sec, [c for c in keep if c not in
                                               ("corp_code", "knowledge_date")])

    # ③ 공시목록 기반: 단일판매·공급계약 체결 (분기 내 발생 여부)
    if dis is not None and len(dis):
        d = _attach_disclosure_events(d, dis, sec)
    else:
        d["supply_contract"] = np.nan

    have = [c for c in NONFIN_ITEMS if c in d.columns]
    n_ok = d[have].notna().sum(axis=1)
    d["dNONFIN"] = d[have].astype("float64").sum(axis=1, skipna=True).where(n_ok > 0)
    d["dNONFIN_n_items"] = n_ok

    LOG.table([[c, f"{int(d[c].notna().sum()):,}",
                f"{100*d[c].notna().mean():.1f}%",
                f"{float(pd.to_numeric(d[c], errors='coerce').mean()):.3f}"
                if d[c].notna().any() else "—"] for c in have],
              ["ΔNONFIN 항목", "관측", "커버리지", "발생률"], ["l", "r", "r", "r"],
              title="ΔNONFIN 구성 항목별 커버리지 (결측은 0 으로 채우지 않고 합계에서 제외)")
    LOG.ok(f"ΔNONFIN 산출 {int(d['dNONFIN'].notna().sum()):,}행 "
           f"(평균 가용 항목 {n_ok.mean():.2f}/{len(have)}개)")
    return d


def _asof_attach(base: pd.DataFrame, R: pd.DataFrame, sec: pd.DataFrame,
                 value_cols: Sequence[str]) -> pd.DataFrame:
    """corp_code 기준 as-of 결합. 결합키 결측 행은 반드시 보존한다(생존자편향 방지)."""
    d = base.copy()
    if "corp_code" not in d.columns:
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict()) \
            if "corp_code" in sec.columns else {}
        d["corp_code"] = d["code"].map(c2c)
    RR = R.copy()
    RR["knowledge_date"] = as_ts_series(RR["knowledge_date"])
    RR = (RR.dropna(subset=["corp_code", "knowledge_date"])
            .sort_values("knowledge_date", kind="stable"))
    RR["corp_code"] = RR["corp_code"].astype(str)
    RR = RR.drop_duplicates(["corp_code", "knowledge_date"], keep="last")
    d["_ord"] = np.arange(len(d))
    m = d["corp_code"].notna() & d["signal_date"].notna()
    if not m.any():
        for c in value_cols:
            if c not in d.columns:
                d[c] = np.nan
        return d.drop(columns=["_ord"])
    L = d[m].copy()
    L["corp_code"] = L["corp_code"].astype(str)
    L = L.sort_values("signal_date", kind="stable")
    M = pd.merge_asof(L, RR, left_on="signal_date", right_on="knowledge_date",
                      by="corp_code", direction="backward", suffixes=("", "_r"))
    add = [c for c in value_cols if c in M.columns]
    out = d.set_index("_ord")
    for c in add:
        if c in out.columns:
            out = out.drop(columns=[c])
    out = out.join(M.set_index("_ord")[add], how="left").sort_index().reset_index(drop=True)
    return out


def _attach_disclosure_events(d: pd.DataFrame, dis: pd.DataFrame,
                              sec: pd.DataFrame) -> pd.DataFrame:
    """리밸런싱 직전 1분기 구간에 발생한 공시 이벤트를 바이너리로 붙인다.

    ★ as-of 결합이 아니라 '구간 집계'다. 공급계약이나 CB 발행은 '가장 최근 값'이 아니라
      '지난 분기에 있었는가'가 의미 있는 정보이기 때문이다.
    ★ 구간의 오른쪽 끝은 signal_date(포함)이며, knowledge_date 기준이므로 §4 규약이 지켜진다.
    """
    D = dis.copy()
    D["knowledge_date"] = as_ts_series(D["knowledge_date"])
    D = D.dropna(subset=["knowledge_date"])
    # 종목코드 확보: stock_code 우선, 없으면 corp_code → code 매핑
    if "stock_code" in D.columns:
        D["code"] = D["stock_code"].map(to_code6)
    else:
        D["code"] = None
    if "corp_code" in D.columns and len(sec) and "corp_code" in sec.columns:
        cc2code = (sec.dropna(subset=["corp_code"]).drop_duplicates("corp_code")
                      .set_index(sec.dropna(subset=["corp_code"])
                                 .drop_duplicates("corp_code")["corp_code"].astype(str))["code"]
                      .to_dict())
        need = D["code"].isna()
        if need.any():
            D.loc[need, "code"] = D.loc[need, "corp_code"].astype(str).map(cc2code)
    D = D.dropna(subset=["code"])
    if D.empty:
        d["supply_contract"] = np.nan
        return d

    ev_cols = {"supply_contract": "supply_contract", "cb_issue": "cb_issue",
               "bw_issue": "bw_issue", "major_holder_chg": "major_holder_chg",
               "lawsuit_filed": "lawsuit_filed", "capital_impair": "capital_impair_dis"}
    for c in ev_cols.values():
        d[c] = 0.0

    reb = sorted(pd.unique(as_ts_series(d["rebal"])))
    sig_by_rebal = (d.groupby("rebal", observed=True)["signal_date"].first().to_dict())
    prev_by_rebal: Dict[Any, pd.Timestamp] = {}
    for i, t in enumerate(reb):
        prev_by_rebal[t] = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))

    idx = {(c, as_ts(t)): None for c, t in zip(d["code"], d["rebal"])}
    for t in reb:
        lo = prev_by_rebal[t]
        hi = as_ts(sig_by_rebal.get(t))
        if hi is None:
            continue
        w = D[(D["knowledge_date"] > lo) & (D["knowledge_date"] <= hi)]
        if w.empty:
            continue
        rows_t = d["rebal"] == t
        for ev, cname in ev_cols.items():
            hits = set(w.loc[w["event"] == ev, "code"])
            if hits:
                d.loc[rows_t & d["code"].isin(hits), cname] = 1.0
    LOG.debug("공시 이벤트 구간 결합 완료 — " +
              ", ".join(f"{c}={int(d[c].sum()):,}" for c in ev_cols.values()))
    return d
