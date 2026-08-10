

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
#  ★★ '해지·철회·취소·기각' 을 '체결·발행·제기' 와 구분해야 한다 ★★
#    공시 제목은 "단일판매·공급계약 해지", "전환사채 발행결정 철회", "소송 제기 취하" 처럼
#    반대 사건도 같은 어간을 쓴다. 구분하지 않으면 공급계약 '해지'가 긍정 하드팩트로,
#    CB 발행 '철회'가 배제 사유로 계상된다 — 두 방향 모두 신호를 뒤집는다.
_DIS_NEG = r"(?!.*(해지|철회|취소|취하|기각|각하|무효|불성립|해제))"
QVF_DISCLOSURE_PATTERNS = {
    # 긍정 하드팩트
    "supply_contract":  _DIS_NEG + r".*(단일판매[·ㆍ・]?\s*공급계약|공급계약\s*체결|수주)",
    # 배제 플래그
    "cb_issue":         _DIS_NEG + r".*전환사채",
    "bw_issue":         _DIS_NEG + r".*신주인수권부사채",
    "major_holder_chg": _DIS_NEG + r".*최대주주\s*(?:변경|변동)",
    "audit_report":     r"감사보고서|감사의견",
    "lawsuit_filed":    _DIS_NEG + r".*소송\s*(?:등의?\s*)?(?:제기|판결)",
    "capital_impair":   r"자본잠식",
}
# 반대 사건도 별도로 세어 표에 남긴다(무시하는 것과 '없었다'는 다르다).
QVF_DISCLOSURE_REVERSALS = r"(해지|철회|취소|취하|기각|각하|무효|불성립|해제)"
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
    _rev = int(D["report_nm"].str.contains(QVF_DISCLOSURE_REVERSALS, regex=True, na=False).sum())
    LOG.ok(f"QVF 공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={v:,}" for k, v in counts.items() if v))
    if _rev:
        LOG.info(f"  그중 '해지·철회·취소·기각' 류 {_rev:,}건은 어떤 이벤트로도 태그하지 "
                 f"않았습니다 — 공급계약 '해지'를 긍정 하드팩트로, CB 발행 '철회'를 배제 "
                 f"사유로 세면 신호가 정반대로 뒤집힙니다.")
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


def _section(text: str, key: str, span: int = 6000,
             probe: Optional[Sequence[str]] = None, max_tries: int = 10) -> str:
    """앵커 섹션을 잘라낸다. ★ '문서 전체의 첫 매치'를 쓰면 안 된다.

    ★★ 이 함수가 조용히 실패하면 §6.1 배제플래그 6종 중 4종과 §7.2 3-A 6개 중 4개가
       '한 번도 발동하지 않는다' ★★
      DART 사업보고서는 맨 앞에 목차가 있고, 앵커 정규식(`감사의견`, `주주에 관한 사항`,
      `특수관계자…거래` 등)은 목차 항목에 그대로 걸린다. 그러면 창 6,000자가 목차와
      회사의 개요를 덮고 실제 섹션에는 닿지 못한다. 파이프라인은 정상 종료하고 진단표에는
      "섹션 발견율 100%" 가 찍히는데, 값은 전부 None 이다. 그리고 '근거 결측이면 배제하지
      않는다' 규칙과 결합해 필터층이 통째로 무력화된다. 더 나쁜 것은 어블레이션이
      "3-A 는 기여가 없다"로 읽히지 "3-A 가 실행되지 않았다"로 읽히지 않는다는 점이다.
    → 앵커의 모든 매치를 돌면서 '목표 숫자·문구가 실제로 잡히는 창'을 채택한다.
    """
    hits = [m.start() for m in _SECTION_RE[key].finditer(text)]
    if not hits:
        return ""
    hits = hits[:max_tries]
    if probe:
        for st in hits:
            w = text[st: st + span]
            if any(re.search(p, w) for p in probe):
                return w
    # 목표를 못 찾았거나 probe 가 없으면: 목차로 추정되는 선두 매치를 피해 마지막 매치를 쓴다.
    #  (목차는 문서 앞부분에 몰려 있고, 실제 본문 섹션은 뒤에 온다)
    st = hits[-1] if len(hits) > 1 else hits[0]
    return text[st: st + span]


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
    """'%' 로 적힌 비율을 소수로 돌려준다.

    ★★ 예전 코드는 `v / 100.0 if v > 1.5 else v` 였다 ★★
      즉 "0.8 %" 를 0.8(=80%)로, "1.5 %" 를 1.5(=150%)로 읽었다. 실무에서 특수관계자
      매출 비중이 1.5% 이하인 종목은 드물지 않다(로그정규 중앙값 4% 가정 시 약 22%).
      그 종목들이 전부 100배로 부풀려져 §7.2 `r_related(>30%)` 에 무조건 걸렸고,
      §6.1 `x_related_up` 의 '상승폭 상위 20%' 임계는 5배 이동해 올바른 플래그 집합과의
      일치율이 5% 수준이었다 — 이 플래그는 특수관계자 위험이 아니라 '비중이 1.5% 미만인가'
      를 세고 있었다. 1.5 라는 컷 자체가 명세에 없는 임의값이다.
    → 패턴이 '%' 기호를 실제로 소비했으면 무조건 /100 한다. 여기 오는 패턴은 전부 그렇다.
    """
    for p in pats:
        m = re.search(p, sect)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
            except Exception:
                continue
            if not np.isfinite(v) or v < 0 or v > 100.0:
                continue                      # 표에서 엉뚱한 숫자를 물었다 — 다음 패턴으로
            return v / 100.0
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
    ip = _section(text, "ip", probe=[r"특허\D{0,12}?[\d,]{1,6}\s*건",
                                     r"특허\s*(?:권|등록|제?\s*\d{2,})"])
    out["patents"] = _count_patents(ip)
    out["sect_ip"] = bool(ip)

    rnd = _section(text, "rnd", probe=[r"연구\s*(?:개발)?\s*인력\D{0,12}?[\d,]{1,6}\s*명",
                                       r"(?:연구원|연구개발\s*인원)\D{0,10}?[\d,]{1,6}\s*명"])
    out["rnd_headcount"] = _rnd_headcount(rnd)
    out["sect_rnd"] = bool(rnd)
    # 정부 R&D 과제: 완료형 사실 문장만 인정
    gov = 0
    for s in _SENT_SPLIT.split(rnd)[:400]:
        if re.search(r"(국책|정부|국가)\s*(과제|연구개발사업|R&D)", s) and is_completed_fact(s):
            gov += 1
    out["gov_rnd_facts"] = float(gov)

    _rel_pats = [r"매출\D{0,20}?([\d,.]+)\s*%", r"비중\D{0,10}?([\d,.]+)\s*%"]
    _relp_pats = [r"매입\D{0,20}?([\d,.]+)\s*%"]
    rel = _section(text, "related", probe=_rel_pats + _relp_pats)
    out["sect_related"] = bool(rel)
    out["related_sales_ratio"] = _ratio_pct(rel, _rel_pats)
    out["related_purchase_ratio"] = _ratio_pct(rel, _relp_pats)

    _cg_pats = [r"지급보증\D{0,24}?([\d,]{3,})", r"우발부채\D{0,24}?([\d,]{3,})"]
    cg = _section(text, "contingent", probe=_cg_pats)
    out["sect_contingent"] = bool(cg)
    out["contingent_amt"] = _amount_krw(cg, _cg_pats)

    _ls_pats = [r"소송\s*가?액\D{0,24}?([\d,]{3,})", r"청구\s*금액\D{0,24}?([\d,]{3,})"]
    ls = _section(text, "lawsuit", probe=_ls_pats + [r"소송.{0,20}제기"])
    out["sect_lawsuit"] = bool(ls)
    out["lawsuit_amt"] = _amount_krw(ls, _ls_pats)
    out["lawsuit_new"] = float(sum(1 for s in _SENT_SPLIT.split(ls)[:300]
                                   if re.search(r"소송.{0,20}제기", s) and is_completed_fact(s)))

    # ★ 핵심감사사항(KAM)은 2018년 이후 상장사 감사보고서의 '필수 기재사항'이지 강조사항이
    #   아니다. 탐지어에 넣으면 정상 기업이 전부 발동한다. §6.1/§7.2 가 요구하는 것은
    #   '강조사항·특기사항'과 '계속기업 불확실성' 이다.
    _au_pats = [r"강조\s*사항", r"특기\s*사항", r"계속기업.{0,20}(불확실|의문|중요한)"]
    au = _section(text, "audit", probe=_au_pats)
    out["sect_audit"] = bool(au)
    _au_hit = next((m for m in (re.search(p, au) for p in _au_pats) if m), None)
    if _au_hit is None:
        out["audit_emphasis"] = 0.0
    else:
        # 부정 판정은 '그 문구 주변'에서 본다. 앵커 기준 고정 400자 창은 문서 레이아웃의
        # 우연에 판정이 좌우된다(목차 유무만으로 결과가 뒤집혔다).
        _near = au[max(0, _au_hit.start() - 120): _au_hit.start() + 300]
        out["audit_emphasis"] = float(not re.search(r"해당\s*사항\s*(?:이)?\s*없|"
                                                    r"기재할\s*사항\s*없|없습니다", _near))

    _hd_pats = [r"최대주주\D{0,40}?([\d,.]+)\s*%", r"소유\s*비율\D{0,10}?([\d,.]+)\s*%"]
    hd = _section(text, "holder", probe=_hd_pats)
    out["sect_holder"] = bool(hd)
    out["major_holder_pct"] = _ratio_pct(hd, _hd_pats)
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
            # ★★ '섹션 발견율' 만 보면 안 된다 ★★
            #   그 표는 "단어가 문서 어딘가에 있었다"를 재는 것이지 "그 섹션을 읽었다"를
            #   재는 것이 아니다. 앵커가 목차에 걸리면 발견율은 100% 인데 값은 전부 None 이고,
            #   그 상태로 §6.1 배제플래그 4종과 §7.2 3-A 4개가 한 번도 발동하지 않는다.
            #   → 필드별 '값 추출 성공률' 을 나란히 싣는다. 이 값이 0 에 가까우면 파서가
            #     죽은 것이지 데이터가 없는 것이 아니다.
            _valcol = {"ip": "patents", "rnd": "rnd_headcount", "related": "related_sales_ratio",
                       "contingent": "contingent_amt", "lawsuit": "lawsuit_amt",
                       "audit": "audit_emphasis", "holder": "major_holder_pct"}
            rows, worst = [], []
            for c, _ in sect:
                nm = c.replace("sect_", "")
                s_rate = 100 * pd.to_numeric(okF[c], errors="coerce").fillna(0).mean()
                vc = _valcol.get(nm)
                if vc and vc in okF.columns:
                    v_rate = 100 * okF[vc].notna().mean()
                    vtxt = f"{v_rate:.1f}%"
                    if s_rate >= 50.0 and v_rate < 5.0:
                        worst.append(nm)
                else:
                    vtxt = "—"
                rows.append([nm, f"{s_rate:.1f}%", vtxt])
            LOG.table(rows, ["섹션", "앵커 발견율", "값 추출 성공률"], ["l", "r", "r"],
                      title="섹션별 발견율 vs 값 추출률 — 앵커만 잡히고 값이 안 나오면 "
                            "목차에 걸린 것이다(필터층이 통째로 무력화된다)")
            if worst:
                LOG.warn(f"앵커는 잡히는데 값이 거의 안 나오는 섹션: {', '.join(worst)}. "
                         f"이 섹션에 의존하는 §6.1 배제플래그·§7.2 3-A 는 사실상 발동하지 "
                         f"않습니다 — 어블레이션의 '기여 없음'을 '규칙이 무의미하다'로 읽지 "
                         f"마십시오. 파서가 실행되지 않은 것입니다.")
    if rate < 0.80:
        LOG.warn(f"dart_parse_rate {100*rate:.1f}% < 80% (§2.1 게이트 미달). "
                 f"주된 사유는 위 표에 분해되어 있습니다. 스캔본 비중이 높다면 정규식을 고쳐도 "
                 f"개선되지 않습니다 — 해당 컴포넌트(특허·연구인력·특수관계자 등)는 결측 처리되고 "
                 f"ΔNONFIN 은 가용 항목만으로 계산됩니다. 전략 전체는 중단하지 않습니다(§2.2).")
    return rate


# ── 최대주주 지분율: 구조화 엔드포인트 폴백 ─────────────────────────────────────────────────
#  §7.2 의 '최대주주 지분율 < 15% 제외'는 3-A 의 하드 규칙인데, 본문 정규식으로 뽑는 지분율은
#  표 레이아웃에 따라 실패율이 높다. 정기보고서 주요정보에 구조화 엔드포인트가 있으므로
#  '본문 추출이 실패한 (회사, 연도)'에 한해서만 추가 호출한다(전량 호출은 호출량 낭비다).
#  ★ 응답 스키마가 기대와 다르면 조용히 결측을 돌려주고, 어느 경로가 값을 채웠는지 로그에 남긴다.
USE_HYSLR_ENDPOINT = True


def fetch_major_holder_stake(targets: pd.DataFrame) -> pd.DataFrame:
    """targets: corp_code · bsns_year  →  corp_code · knowledge_date · major_holder_pct_api

    최대주주 '및 특수관계인 합계' 기말 지분율을 쓴다.
    ★ 행이 (인별 × 주식종류별)로 쪼개져 오고 '계/합계' 소계 행이 섞여 있다. 둘을 함께 더하면
      이중계상이라 지분율이 100% 를 넘는다(코어가 empSttus 에서 이미 겪은 함정과 같은 형태).
    """
    cols = ["corp_code", "bsns_year", "knowledge_date", "major_holder_pct_api"]
    if not (USE_HYSLR_ENDPOINT and DART_API_KEY) or targets is None or targets.empty:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_major_holder", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"캐시에서 최대주주 지분율 {len(cached):,}건 재사용")
    jobs = [(str(c), int(y)) for c, y in
            zip(targets["corp_code"], targets["bsns_year"])
            if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, y = job
        js = dart_api("hyslrSttus.json", {"corp_code": corp, "bsns_year": str(y),
                                          "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        rate_col = next((c for c in ("trmend_posesn_stock_qota_rt",
                                     "bsis_posesn_stock_qota_rt") if c in d.columns), None)
        if rate_col is None:
            return None
        rt = pd.to_numeric(d[rate_col].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                           errors="coerce")
        knd = d["stock_knd"].astype(str) if "stock_knd" in d.columns else pd.Series([""] * len(d))
        nm = d["nm"].astype(str) if "nm" in d.columns else pd.Series([""] * len(d))
        common = knd.str.contains("보통", na=False) | (knd.str.strip() == "")
        if not common.any():
            common = pd.Series(True, index=d.index)
        sub_rt, sub_nm = rt[common], nm[common]
        tot = sub_nm.str.replace(r"\s+", "", regex=True).str.contains("계|합계|소계", na=False)
        # 합계 행이 있으면 그것만, 없으면 구성원 합. 둘을 더하면 이중계상이다.
        val = float(sub_rt[tot].max()) if tot.any() and sub_rt[tot].notna().any() \
            else float(sub_rt[~tot].sum(skipna=True))
        if not np.isfinite(val) or val <= 0 or val > 100:
            return None
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(y), "rcept_no": rn,
                "major_holder_pct_api": val / 100.0}

    got = []
    if jobs:
        LOG.info(f"최대주주 지분율 구조화 조회 {len(jobs):,}건 (본문 추출 실패분만) — "
                 f"남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'}")
        got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8),
                                  desc="최대주주 지분율") if r]

    frames = [cached] if cached is not None and len(cached) else []
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    H = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"],
                                                             keep="last")
    if "rcept_no" not in H.columns:
        H["rcept_no"] = ""
    H["knowledge_date"] = [dart_knowledge_date(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(H["rcept_no"], H["bsns_year"])]
    if got:
        VAULT.put_table("dart_major_holder", H, scope="shared", domain="dart",
                        source="opendart hyslrSttus")
    LOG.ok(f"최대주주 지분율(구조화) {len(H):,}건 확보 — 3-A '지분율 < 15%' 규칙의 근거 보강")
    return downcast_q(H[cols])


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
            #   ★★ 다만 솔직하게 적어 둔다: 이 항목들의 원천은 '사업보고서 본문'이므로
            #      관측 주기가 연 1회다. 따라서 여기의 shift(1) 은 §6.1 문언의 '전분기 대비'가
            #      아니라 사실상 '전년 대비' 다. 분기보고서 주석에는 이 수치가 없으므로
            #      분기 차분 자체가 데이터상 불가능하다 — 근사이며 동일하지 않다.
            #      (연 1회 관측을 억지로 분기로 쪼개면 없는 변화를 만들어내는 것이 되므로
            #       그쪽이 더 큰 위반이다. 이 사실은 §10.1 임의선택 원장에 실린다.)
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
    # ★★ '합'을 그대로 쓰면 커버리지가 곧 점수가 된다 ★★
    #   결측을 0 으로 채우지 않고 합계에서 빼는 것은 옳지만, 그러면 항목을 6개 다 관측한
    #   종목이 2개만 관측한 종목보다 구조적으로 큰 값을 받는다. 즉 ΔNONFIN 이 '증분 이벤트'가
    #   아니라 '데이터를 얼마나 확보했는가' 를 재게 된다 — 대형·공시 성실 종목 쪽으로 기운다.
    #   → 가용 항목 수로 정규화한 평균(=항목당 발생률)을 쓰고, 원합계는 참고용으로 남긴다.
    #   ※ 항목 수가 1~2개뿐인 관측은 평균의 분산이 크므로 개수를 함께 실어 해석하게 한다.
    _sum = d[have].astype("float64").sum(axis=1, skipna=True)
    d["dNONFIN_raw_sum"] = _sum.where(n_ok > 0)
    d["dNONFIN"] = (_sum / n_ok.replace(0, np.nan)).where(n_ok > 0)
    d["dNONFIN_n_items"] = n_ok
    if int((n_ok > 0).sum()):
        _c = np.corrcoef(n_ok[n_ok > 0].to_numpy(dtype=float),
                         d.loc[n_ok > 0, "dNONFIN_raw_sum"].to_numpy(dtype=float))[0, 1]
        LOG.info(f"ΔNONFIN 정규화: 가용 항목 수로 나눈 평균을 사용합니다. "
                 f"(정규화 전 원합계와 가용 항목 수의 상관 {_c:+.3f} — 이 값이 높을수록 "
                 f"'커버리지가 곧 점수'가 되던 정도가 큽니다)")

    LOG.table([[c, f"{int(d[c].notna().sum()):,}",
                f"{100*d[c].notna().mean():.1f}%",
                f"{float(pd.to_numeric(d[c], errors='coerce').mean()):.3f}"
                if d[c].notna().any() else "—"] for c in have],
              ["ΔNONFIN 항목", "관측", "커버리지", "발생률"], ["l", "r", "r", "r"],
              title="ΔNONFIN 구성 항목별 커버리지 (결측은 0 으로 채우지 않고 합계에서 제외)")
    LOG.ok(f"ΔNONFIN 산출 {int(d['dNONFIN'].notna().sum()):,}행 "
           f"(평균 가용 항목 {n_ok.mean():.2f}/{len(have)}개)")
    return d


def attach_major_holder(P: pd.DataFrame, H: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """구조화 조회 결과로 본문 추출값의 빈칸을 메운다(덮어쓰지 않는다)."""
    if H is None or H.empty:
        return P
    d = _asof_attach(P, H[["corp_code", "knowledge_date", "major_holder_pct_api"]],
                     sec, ["major_holder_pct_api"])
    before = float(col(d, "major_holder_pct").notna().mean())
    d["major_holder_pct"] = col(d, "major_holder_pct").where(
        col(d, "major_holder_pct").notna(), col(d, "major_holder_pct_api"))
    after = float(col(d, "major_holder_pct").notna().mean())
    LOG.ok(f"최대주주 지분율 커버리지 {100*before:.1f}% → {100*after:.1f}% "
           f"(본문 추출 + 구조화 엔드포인트 보강)")
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
    L["signal_date"] = as_ts_series(L["signal_date"])           # 결합키 단위 고정(as_ts 주석)
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
    # ★ 0.0 으로 초기화하면 '스윕을 안 했다'와 '스윕했는데 해당 없음'이 구별되지 않는다.
    #   전자는 근거 부재(배제하면 안 됨), 후자는 근거 있음(배제 판단 가능)이다.
    #   공시 원장이 실제로 덮은 구간에서만 0 을 채우고, 나머지는 결측으로 남긴다.
    _cov_lo = as_ts_series(D["knowledge_date"]).min()
    _cov_hi = as_ts_series(D["knowledge_date"]).max()
    _covered = (as_ts_series(d["signal_date"]) >= _cov_lo) & (as_ts_series(d["signal_date"]) <= _cov_hi)
    for c in ev_cols.values():
        d[c] = np.where(_covered.to_numpy(), 0.0, np.nan)
    if int((~_covered).sum()):
        LOG.info(f"공시 원장이 덮지 못한 {int((~_covered).sum()):,}행은 이벤트를 0 이 아니라 "
                 f"결측으로 둡니다 (근거 없이 '해당 없음'으로 처리하지 않습니다).")

    reb = sorted(pd.unique(as_ts_series(d["rebal"])))
    sig_by_rebal = (d.groupby("rebal", observed=True)["signal_date"].first().to_dict())
    prev_by_rebal: Dict[Any, pd.Timestamp] = {}
    for i, t in enumerate(reb):
        # ★ 왼쪽 끝은 '직전 분기의 signal_date'. 명목 리밸일로 잡으면
        #   (signal_{i-1}, rebal_{i-1}] 구간이 어느 창에도 속하지 않아, 명목일이 거래일인
        #   분기마다 정확히 1거래일의 공시가 사라진다.
        _p = as_ts(sig_by_rebal.get(reb[i - 1])) if i > 0 else None
        if _p is None:
            _p = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        prev_by_rebal[t] = _p

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
