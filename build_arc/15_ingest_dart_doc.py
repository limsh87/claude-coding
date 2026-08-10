
# ────────────────────────────────────────────────────────────────────────────────────────
#  L1-G  DART 정기보고서 원문 수집 + §6.1.3 텍스트 정규화
#  ★ 명세 §6.1.3 의 단계 순서에 함정이 하나 있어 구현에서 바로잡았다:
#  ★ 섹션 분해 순서도 바로잡았다. 명세 [5]는 '표준 목차 헤더 제거'를 지시하는데, 섹션 분해는
# ────────────────────────────────────────────────────────────────────────────────────────

ARC_SECTIONS = ["S_MDA", "S_LEGAL", "S_EXEC", "S_BIZ", "S_RISK", "S_GOV", "S_ALL"]

# 섹션 표제 정규식. 로마숫자/아라비아 목차 번호는 선택적으로만 매칭하고(서식 개정 때 번호가
# 바뀐다), 한글 표제어를 진짜 앵커로 쓴다.
_RN = r"(?:[IVXivx]{1,5}\s*[.\-]\s*|\d{1,2}\s*[.\-]\s*|제?\s*\d{1,2}\s*장\s*)?"
ARC_SECTION_PAT: Dict[str, str] = {
    "S_MDA":   _RN + r"이사의\s*경영\s*진단\s*및\s*분석\s*의견|경영진단\s*및\s*분석의견|"
                     r"MD\s*&\s*A",
    "S_LEGAL": _RN + r"그\s*밖에\s*투자자\s*보호를\s*위하여\s*필요한\s*사항|"
                     r"제재\s*현황|제재등과\s*관련된\s*사항|우발\s*채무\s*등|우발부채\s*등|"
                     r"소송\s*사건|중요한\s*소송|계류\s*중인\s*소송",
    "S_EXEC":  _RN + r"임원\s*및\s*직원\s*등에\s*관한\s*사항|임원\s*및\s*직원의\s*현황|"
                     r"직원\s*등\s*현황",
    "S_BIZ":   _RN + r"사업의\s*내용",
    "S_RISK":  _RN + r"사업\s*위험|투자\s*위험\s*요소|위험\s*요인|주요\s*위험|위험\s*관리",
    "S_GOV":   _RN + r"주주에\s*관한\s*사항|지배\s*구조|계열\s*회사\s*등에\s*관한\s*사항|"
                     r"대주주\s*등과의\s*거래\s*내용|이사회\s*등\s*회사의\s*기관",
}
_ARC_SECTION_RE = {k: re.compile(v) for k, v in ARC_SECTION_PAT.items()}

# ── 정규화 사전 ─────────────────────────────────────────────────────────────────────────────
# [5] 법정 고지문·서식 문구. 전 기업이 동일하게 쓰므로 남겨두면 유사도를 인위적으로 끌어올린다
#     (= 진짜 변화가 희석된다). 반대로 서식 개정 해에는 이 문구들이 일제히 바뀌어 전 종목이
#     '변경'으로 잡힌다. 어느 쪽이든 신호가 아니므로 제거한다.
_DOC_BOILERPLATE = [
    r"본\s*보고서\s*작성\s*기준일\s*현재[^.\n]{0,80}[.\n]",
    r"금융감독원\s*전자공시시스템[^\n]{0,60}",
    r"전자공시시스템\s*dart\.fss\.or\.kr[^\n]{0,60}",
    r"공시서류\s*작성\s*기준[^\n]{0,60}",
    r"※\s*상기\s*내용은[^.\n]{0,120}[.\n]",
    r"자세한\s*사항은\s*본문을\s*참조[^\n]{0,40}",
    r"목\s*차\s*[\r\n]+(?:[^\n]{0,80}[\r\n]+){0,60}?(?=[IVX]{1,4}\s*\.)",
    r"-\s*\d{1,4}\s*-",                        # 페이지 번호
    r"\(단위\s*[:：][^)]{0,30}\)",              # 표 단위 표기 (표는 지웠지만 캡션이 남는다)
    r"주\s*\d{1,2}\s*\)",                      # 주석 번호
]
_DOC_BOILERPLATE_RE = re.compile("|".join(_DOC_BOILERPLATE))

# [3] 날짜/기수. 반드시 숫자 마스킹보다 먼저.
_DOC_DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[년\-/.]\s*(?:0?[1-9]|1[0-2])\s*[월\-/.]\s*(?:0?[1-9]|[12]\d|3[01])\s*일?"
    r"|(?:19|20)\d{2}\s*[년\-/.]\s*(?:0?[1-9]|1[0-2])\s*월?"
    r"|(?:19|20)\d{2}\s*년度?|(?:19|20)\d{2}\s*회계연도|(?:19|20)\d{2}\s*사업연도"
    r"|(?:19|20)\d{2}\s*년")
_DOC_PERIOD_RE = re.compile(r"제\s*\d{1,4}\s*(?:기|분기|반기|사업연도|회계연도)"
                            r"|당\s*[반분]?기|전\s*[반분]?기|당기말|전기말")
# [2] 잔여 숫자 (반각/전각/콤마/소수/백분율/괄호음수)
_DOC_NUM_RE = re.compile(r"[（(]?\s*[△▲▽▼\-−]?\s*[0-9０-９][0-9０-９,，.．]*\s*%?\s*[)）]?")

# 마스크 토큰 보호용 자리표시자. 문서 본문에 등장할 수 없는 제어문자를 쓴다.
_DOC_MASK_PH = {"<NUM>": "\x01N\x02", "<DATE>": "\x01D\x02",
                "<PERIOD>": "\x01P\x02", "<COMPANY>": "\x01C\x02"}

# [1] 표/이미지/스크립트
_DOC_TABLE_RE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_DOC_DROP_TAG_RE = re.compile(r"<(script|style|img|object|embed)\b.*?(</\1>|/?>)", re.I | re.S)
_DOC_TAG_RE = re.compile(r"<[^>]+>")

_DOC_STOPWORDS = set("""
그리고 그러나 또한 및 등 등의 등을 등에 대한 대하여 관한 관하여 위한 위하여 통한 통하여
있습니다 있으며 있는 있음 없습니다 없으며 없음 하고 하며 하는 한다 합니다 됩니다 되었습니다
경우 때문 따라 따른 통해 이상 이하 이내 이후 이전 현재 당사 회사 보고서 기준 관련 각각
바랍니다 참조 해당 다음 아래 상기 하기 기재 내용 사항 부분 전체 일부 주요 기타 이러한 그러한
것으로 것을 것이 하나 여부 정도 수준 상태 경우에는 위해 대해 대해서 그것 이것
""".split())

# ── 토큰화 폴백 사다리 ──────────────────────────────────────────────────────────────────────
_DOC_TAGGER = {"kind": None, "obj": None, "warned": False}

# 규칙기반 폴백용 한국어 조사/어미. 긴 것부터 잘라야 '에서는' 이 '에' 로 잘못 잘리지 않는다.
_KO_SUFFIX = sorted([
    "으로서는", "으로부터", "에서부터", "이라고는", "하였습니다", "되었습니다", "있습니다",
    "습니다", "ㅂ니다", "하였다", "되었다", "이라는", "으로써", "으로서", "에서는", "에게서",
    "라고는", "이라도", "까지도", "부터는", "에게는", "에서도", "으로는", "하는", "되는",
    "이라", "으로", "에서", "에게", "부터", "까지", "보다", "처럼", "만큼", "조차", "마저",
    "이나", "거나", "라도", "이며", "하며", "되며", "하고", "되고", "인데", "한다", "된다",
    "들의", "들을", "들이", "들에", "이다", "였다", "했다",
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "만", "로", "라",
], key=len, reverse=True)
_KO_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}|<[A-Z]+>")

def _doc_load_tagger():
    """konlpy → soynlp → 규칙기반. konlpy 는 JVM 을 띄우다 프로세스를 죽일 수 있어 지연 로딩."""
    if _DOC_TAGGER["kind"] is not None:
        return _DOC_TAGGER
    kind, obj = "rule", None
    if globals().get("KONLPY_AVAILABLE"):
        for name in ("Mecab", "Okt"):
            try:
                from konlpy.tag import Mecab, Okt          # type: ignore  # noqa
                obj = (Mecab() if name == "Mecab" else Okt())
                # 실제로 한 번 돌려봐야 안다 (Mecab 은 사전이 없으면 생성 시점엔 통과하고
                # 첫 호출에서 죽는다)
                _ = obj.pos("테스트 문장입니다")
                kind = f"konlpy.{name}"
                break
            except Exception:
                obj = None
                continue
    if obj is None and globals().get("soynlp_tok") is not None:
        try:
            obj = soynlp_tok()                              # 점수사전 없이도 L-토큰화는 동작
            _ = obj.tokenize("테스트 문장입니다")
            kind = "soynlp"
        except Exception:
            obj = None
    _DOC_TAGGER["kind"], _DOC_TAGGER["obj"] = kind, obj
    if not _DOC_TAGGER["warned"]:
        _DOC_TAGGER["warned"] = True
        if kind.startswith("konlpy"):
            LOG.ok(f"형태소 분석기: {kind} — D1 토큰화 품질 최상")
        elif kind == "soynlp":
            LOG.info("형태소 분석기가 없어 soynlp L-토큰화를 씁니다. "
                     "D1 은 정상 동작하나 조사 분리 정확도가 다소 낮습니다.")
        else:
            LOG.warn("형태소 분석기(konlpy)·soynlp 둘 다 없어 규칙기반 토큰화로 폴백합니다. "
                     "★ 이 경로에서도 D1 은 동작하지만 어미 절단이 거칠어 유사도 분산이 커집니다. "
                     "결과 해석 시 감안하고, 가능하면 `pip install soynlp` 를 권합니다.")
    return _DOC_TAGGER

def _doc_rule_stem(tok: str) -> str:
    """규칙기반 어간 추출. 긴 조사/어미부터 잘라내고 2자 미만은 버린다."""
    if tok.startswith("<") and tok.endswith(">"):
        return tok
    t = tok
    for suf in _KO_SUFFIX:
        if len(t) > len(suf) + 1 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t if len(t) >= 2 else ""

def arc_tokenize(norm_text: str) -> List[str]:
    """§6.1.3 [6]. 명사·동사·형용사 어간만 유지, 조사·어미 제거, 불용어 적용."""
    if not norm_text:
        return []
    tg = _doc_load_tagger()
    kind, obj = tg["kind"], tg["obj"]
    toks: List[str] = []
    if kind.startswith("konlpy") and obj is not None:
        try:
            keep = ("NN", "VV", "VA", "XR", "SL", "Noun", "Verb", "Adjective", "Alpha")
            for w, p in obj.pos(norm_text[:400_000]):
                if str(p).startswith(keep) and len(w) >= 2:
                    toks.append(w)
        except Exception:
            toks = []
    elif kind == "soynlp" and obj is not None:
        try:
            for w in obj.tokenize(norm_text[:400_000]):
                w = _doc_rule_stem(w)
                if w:
                    toks.append(w)
        except Exception:
            toks = []
    if not toks:                                   # 규칙기반 (최종 폴백 — 항상 동작)
        for w in _KO_TOKEN_RE.findall(norm_text):
            w = _doc_rule_stem(w)
            if w:
                toks.append(w)
    # 마스킹 토큰은 대소문자 그대로 보존되어야 한다(<NUM> 등)
    return [t for t in toks if t not in _DOC_STOPWORDS]

# ── 정규화 본체 ─────────────────────────────────────────────────────────────────────────────
def _doc_company_variants(names: Sequence[str]) -> List[str]:
    """사명 변형 전개. '㈜대한전선' / '주식회사 대한전선' / '대한전선(주)' / 'Daehan' 을 모두 잡는다.

    ★ 이걸 안 하면 사명 변경/표기 변경만으로 문서가 '바뀐' 것으로 잡힌다.
      특히 지주회사 전환기 기업은 문서 전체에서 사명이 수백 번 등장하므로 영향이 크다.
    """
    out = set()
    for n in names or []:
        s = re.sub(r"\s+", "", str(n or ""))
        s = re.sub(r"(주식회사|㈜|\(주\)|유한회사|㈜)", "", s)
        if len(s) >= 2:
            out.add(re.escape(s))
            out.add(re.escape(s[:2]) + r"[가-힣A-Za-z]{0,6}" + r"(?:주식회사|㈜|\(주\))")
    return sorted(out, key=len, reverse=True)[:24]      # 정규식 폭발 방지

def arc_normalize_text(raw_html: str, company_names: Sequence[str] = ()) -> str:
    """§6.1.3 [1]~[5]. 섹션 표제어는 **보존**한다(분해에 필요하므로).

    반환은 '정규화된 평문'이며, 여기에는 <NUM>/<DATE>/<PERIOD>/<COMPANY> 마스크가 들어 있다.
    """
    if not raw_html:
        return ""
    t = str(raw_html)

    # [1] 표·이미지·스크립트 제거 → 순수 서술 텍스트만 (숫자 표는 D2 가 담당한다)
    t = _DOC_TABLE_RE.sub(" ", t)
    t = _DOC_DROP_TAG_RE.sub(" ", t)
    t = _DOC_TAG_RE.sub(" ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))

    # [4] 사명 마스킹 — ★ 숫자 마스킹보다 먼저. 사명에 숫자가 섞인 경우(예: 'SK C&C', '3S')
    #     숫자를 먼저 지우면 사명 매칭이 깨진다.
    vs = _doc_company_variants(company_names)
    if vs:
        try:
            t = re.sub("|".join(vs), " <COMPANY> ", t)
        except re.error:
            for v in vs[:8]:
                try:
                    t = re.sub(v, " <COMPANY> ", t)
                except re.error:
                    continue

    # [3] 날짜 → <DATE>, 기수 → <PERIOD>   (★ 반드시 [2] 보다 먼저 — 위 헤더 주석 참조)
    t = _DOC_PERIOD_RE.sub(" <PERIOD> ", t)
    t = _DOC_DATE_RE.sub(" <DATE> ", t)

    # [2] 잔여 숫자 → <NUM>
    t = _DOC_NUM_RE.sub(" <NUM> ", t)

    # [5] 서식·법정 문구 제거 + 공백/특수문자 정규화 (표제어는 남긴다)
    t = _DOC_BOILERPLATE_RE.sub(" ", t)
    t = unicodedata.normalize("NFKC", t)
    # ★ 특수문자 정리에서 마스크 토큰이 훼손되는 사고를 원천 차단한다.
    #   (상세 근거는 커밋 로그 참조)
    for k, ph in _DOC_MASK_PH.items():
        t = t.replace(k, ph)
    t = re.sub(r"[·ㆍ∙•▷▶□■◦○●◇◆＊*※#~^_=+|\\/\[\]{}<>]+", " ", t)
    for k, ph in _DOC_MASK_PH.items():
        t = t.replace(ph, k)
    t = re.sub(r"(?:<NUM>\s*){3,}", "<NUM> ", t)        # 표 잔재로 반복되는 마스크 압축
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()

def arc_split_sections(norm_text: str) -> Dict[str, str]:
    """정규화 텍스트 → {섹션ID: 본문}. S_ALL 은 항상 포함. 실패 섹션은 키 자체를 넣지 않는다.

    ★ 섹션 경계는 '다음 섹션 표제 등장 위치'로 잡는다. 목차 블록이 남아 있으면 표제가
      본문보다 먼저 두 번 나오므로, 같은 표제의 '마지막' 등장을 본문 시작으로 본다
      (목차는 문서 앞머리에 몰려 있다).
    """
    out: Dict[str, str] = {}
    if not norm_text:
        return out
    out["S_ALL"] = norm_text

    hits: List[Tuple[int, str]] = []
    for sid, rx in _ARC_SECTION_RE.items():
        ms = list(rx.finditer(norm_text))
        if not ms:
            continue
        # 목차 회피: 등장이 2회 이상이면 마지막(=본문) 것을 쓴다.
        m = ms[-1] if len(ms) > 1 else ms[0]
        hits.append((m.start(), sid))
    if not hits:
        return out
    hits.sort()
    bounds = [h[0] for h in hits] + [len(norm_text)]
    for i, (pos, sid) in enumerate(hits):
        seg = norm_text[pos:bounds[i + 1]]
        # 표제어 자체는 잘라낸다(모든 문서에 동일하게 있으므로 유사도만 부풀린다)
        seg = re.sub(r"^[^\n]{0,80}\n", "", seg, count=1)
        if len(seg) >= 200:
            out[sid] = seg[:400_000]
    return out

# ── 문서 유형/연도 해석 ─────────────────────────────────────────────────────────────────────
_DOC_PERIOD_IN_NM = re.compile(r"\((\d{4})[.\-/](\d{1,2})\)")
_DOC_AMEND_RE = re.compile(r"\[?\s*(기재정정|첨부정정|첨부추가|정정)\s*\]?")

def _doc_classify(report_nm: str, rcept_dt) -> Optional[Tuple[str, int, bool]]:
    """report_nm → (doc_type, bsns_year, is_amend). 정기보고서가 아니면 None."""
    nm = re.sub(r"\s+", "", str(report_nm or ""))
    is_amend = bool(_DOC_AMEND_RE.search(str(report_nm or "")))
    m = _DOC_PERIOD_IN_NM.search(str(report_nm or ""))
    year = mon = None
    if m:
        year, mon = int(m.group(1)), int(m.group(2))
    t = as_ts(rcept_dt)
    if "사업보고서" in nm:
        dt = "FY"
        if year is None:
            year = (t.year - 1) if t is not None and t.month <= 6 else (t.year if t else None)
    elif "반기보고서" in nm:
        dt = "H1"
        if year is None:
            year = t.year if t is not None else None
    elif "분기보고서" in nm:
        # 3월 결산분(Q1)은 5월경, 9월 결산분(Q3)은 11월경 접수된다.
        if mon in (3, 4):
            dt = "Q1"
        elif mon in (9, 10):
            dt = "Q3"
        elif t is not None and t.month <= 8:
            dt = "Q1"
        else:
            dt = "Q3"
        if year is None:
            year = t.year if t is not None else None
    else:
        return None
    if year is None:
        return None
    return (dt, int(year), is_amend)

# ── 수집 ────────────────────────────────────────────────────────────────────────────────────
ARC_DOC_COLS = ["corp_code", "rcept_no", "rcept_dt", "doc_type", "bsns_year", "section",
                "n_tokens", "tf", "bigram", "tok_len", "is_amend"]
ARC_DOC_TF_TOP = 350          # 섹션당 저장 토큰 수. 코사인/자카드에 충분하고 용량은 억제.
ARC_DOC_BG_TOP = 120

_ARC_DOC_FAIL: "Counter" = Counter()

def _doc_unzip_text(raw: bytes) -> str:
    """DART 원문 zip → 평문. 모든 xml/html 엔트리를 읽는다.

    ★ 첫 엔트리만 읽으면 본문 대부분이 조용히 사라진다. zip 안에는 본보고서 + 감사보고서 +
      첨부 재무제표가 별도 엔트리로 들어 있다.
    ★ DART 원문은 EUC-KR 인 경우가 많다. XML 선언의 encoding 을 읽어야 한다.
    """
    chunks: List[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        for nm in zf.namelist():
            if not nm.lower().endswith((".xml", ".html", ".htm", ".txt")):
                continue
            try:
                b = zf.read(nm)
            except Exception:
                continue
            enc = None
            m_enc = re.search(rb'encoding\s*=\s*["\']([\w\-]+)["\']', b[:400], re.I)
            if m_enc:
                enc = m_enc.group(1).decode("ascii", "ignore")
            chunks.append(_decode(b, enc, "dart_doc"))
            if sum(len(c) for c in chunks) > 6_000_000:
                break
    except Exception:
        chunks = [_decode(raw, None, "dart_doc")]
    return "\n".join(chunks)

def fetch_arc_documents(dis: pd.DataFrame, sec: pd.DataFrame,
                        max_docs: int = None) -> pd.DataFrame:
    """정기보고서 원문 → 섹션별 정규화 토큰 테이블. 공용 인덱스에 원문·토큰 모두 영속화.

    · 원문 zip  : VAULT.put_blob("dart_doc","raw", rcept_no, ...)   scope="shared"
    · 토큰 테이블: VAULT.put_table("dart_doc_norm_{연도}", ...)      scope="shared"
      → 다른 전략(텍스트 기반 무엇이든)이 그대로 재사용할 수 있다.
    """
    max_docs = int(max_docs or ARC_DOC_MAX)
    _ARC_DOC_FAIL.clear()

    # ── 기존 캐시(연도 샤드) 적재 ─────────────────────────────────────────────────────────
    years_hint = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
    have_frames, have_rcept = [], set()
    for y in years_hint:
        d = VAULT.get_table(f"dart_doc_norm_{y}", scope="shared")
        if d is not None and len(d):
            have_frames.append(d.reindex(columns=ARC_DOC_COLS))
            have_rcept |= set(d["rcept_no"].astype(str))
    if have_frames:
        LOG.info(f"공용 캐시에서 정기보고서 토큰 {sum(len(x) for x in have_frames):,}행 재사용 "
                 f"(문서 {len(have_rcept):,}건)")

    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 정기보고서 원문을 받을 수 없습니다. D1 은 캐시분으로만 "
                 "동작하며, 캐시가 없으면 GATE_5 에서 탈락합니다.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    if dis is None or dis.empty:
        LOG.warn("공시목록이 비어 정기보고서를 특정할 수 없습니다.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    # ── 대상 선별 ─────────────────────────────────────────────────────────────────────────
    D = dis.copy()
    D["report_nm"] = D["report_nm"].astype(str)
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D[D["report_nm"].str.contains("사업보고서|반기보고서|분기보고서", na=False)]
    D = D.dropna(subset=["rcept_no", "rcept_dt", "corp_code"])
    if D.empty:
        LOG.warn("공시목록에 정기보고서(A 유형)가 없습니다. fetch_dart_disclosures 가 "
                 "pblntf_ty='A' 를 훑었는지 확인하세요.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    cls = [_doc_classify(nm, dt) for nm, dt in zip(D["report_nm"], D["rcept_dt"])]
    D["doc_type"] = [c[0] if c else None for c in cls]
    D["bsns_year"] = [c[1] if c else None for c in cls]
    D["is_amend"] = [bool(c[2]) if c else False for c in cls]
    D = D.dropna(subset=["doc_type", "bsns_year"])
    D["bsns_year"] = D["bsns_year"].astype(int)

    # §4.1 정정공시 — 시점 t 에서는 t 이전 마지막 제출본을 쓴다. 여기서는 전부 수집해 두고
    # 페어링 단계에서 '해당 시점 최신본'을 고른다(소급 적용 금지).
    todo_df = D[~D["rcept_no"].astype(str).isin(have_rcept)].copy()
    if RUN_MODE == "CACHED":
        todo_df = todo_df.iloc[0:0]
    # 최근 연도부터 — 중단돼도 최신이 남게
    todo_df = todo_df.sort_values("rcept_dt", ascending=False)
    if len(todo_df) > max_docs:
        LOG.warn(f"정기보고서 신규 대상 {len(todo_df):,}건 중 {max_docs:,}건만 이번에 받습니다. "
                 f"나머지는 다음 실행에서 이어받습니다(콜드빌드는 4시간 예산 밖).")
        todo_df = todo_df.head(max_docs)

    if len(todo_df) and DBUDGET is not None:
        LOG.info(f"정기보고서 원문 신규 {len(todo_df):,}건 — 오늘 남은 DART 호출 "
                 f"{DBUDGET.remaining():,}건 (실시간 추적값). 예산이 부족하면 받은 만큼 저장하고 "
                 f"다음 실행에서 정확히 이어받습니다.")

    # corp_code → 사명(자사 + 종속회사 후보) — [4] 마스킹 입력
    nm_map: Dict[str, List[str]] = {}
    try:
        if sec is not None and len(sec) and "corp_code" in sec.columns:
            g = sec.dropna(subset=["corp_code"]).groupby(sec["corp_code"].astype(str))["name"]
            nm_map = {k: [str(x) for x in v.dropna().tolist()][:6] for k, v in g}
    except Exception:
        nm_map = {}

    jobs = list(zip(todo_df["rcept_no"].astype(str), todo_df["corp_code"].astype(str),
                    todo_df["rcept_dt"], todo_df["doc_type"], todo_df["bsns_year"],
                    todo_df["is_amend"]))

    def _one(job):
        rn, corp, rdt, dtype, byear, amend = job
        if DBUDGET is not None and not DBUDGET.take(1):
            return None                                  # 예산 소진 — 조용히 중단
        raw = http_get(DART_BASE + "document.xml", source="dart", as_bytes=True, tries=2,
                       params={"crtfc_key": DART_API_KEY, "rcept_no": rn},
                       referer="https://opendart.fss.or.kr/")
        if not raw or len(raw) < 500:
            _ARC_DOC_FAIL["응답없음/과소"] += 1
            return None
        # ★ ZIP 엔드포인트는 오류일 때도 content-type 을 zip 으로 광고하면서 JSON 본문을 준다.
        if raw[:2] != b"PK":
            body = raw[:200].decode("utf-8", "ignore")
            if "020" in body:
                if DBUDGET is not None:
                    DBUDGET.note_rate_limited()
                _ARC_DOC_FAIL["호출한도"] += 1
            else:
                _ARC_DOC_FAIL["ZIP아님(스캔본/오류)"] += 1
            return None
        VAULT.put_blob("dart_doc", "raw", rn, raw, "zip", source="opendart document.xml",
                       event_date=rdt, knowledge_date=rdt, scope="shared",
                       extra={"corp_code": corp, "doc_type": dtype, "bsns_year": int(byear)})
        txt = _doc_unzip_text(raw)
        del raw
        if not txt or len(txt) < 2000:
            _ARC_DOC_FAIL["본문없음"] += 1
            return None
        norm = arc_normalize_text(txt, nm_map.get(str(corp), []))
        del txt
        secs = arc_split_sections(norm)
        if len(secs) <= 1:
            _ARC_DOC_FAIL["섹션0개"] += 1
        rows = []
        for sid, body in secs.items():
            toks = arc_tokenize(body)
            if len(toks) < ARC_D1_MIN_TOKENS:
                continue
            cnt = Counter(toks)
            bg = Counter(zip(toks[:-1], toks[1:]))
            rows.append({
                "corp_code": str(corp), "rcept_no": rn, "rcept_dt": as_ts(rdt),
                "doc_type": str(dtype), "bsns_year": int(byear), "section": sid,
                "n_tokens": int(len(cnt)), "tok_len": int(len(toks)),
                "tf": json.dumps(dict(cnt.most_common(ARC_DOC_TF_TOP)), ensure_ascii=False),
                "bigram": json.dumps({f"{a}_{b}": v for (a, b), v
                                      in bg.most_common(ARC_DOC_BG_TOP)}, ensure_ascii=False),
                "is_amend": bool(amend)})
        if not rows:
            _ARC_DOC_FAIL["토큰부족"] += 1
            return None
        return rows

    got: List[dict] = []
    CH = 400            # 청크 소비 — 원문 바이트가 동시에 RAM 에 쌓이지 않게
    for k0 in range(0, len(jobs), CH):
        if DBUDGET is not None and DBUDGET.exhausted:
            LOG.warn(f"DART 예산 소진으로 원문 수집을 {k0:,}/{len(jobs):,} 지점에서 중단합니다. "
                     f"여기까지 받은 분량은 드라이브에 저장되어 다음 실행에서 이어받습니다.")
            break
        part = jobs[k0:k0 + CH]
        res = pmap_io(_one, part, workers=min(N_WORKERS_IO, 6),
                      desc=f"정기보고서 원문 {k0//CH + 1}/{(len(jobs)-1)//CH + 1}")
        for r in res:
            if r:
                got.extend(r)
        del res
        VAULT.flush("shared")
        gc.collect()

    frames = have_frames + ([pd.DataFrame(got)] if got else [])
    if not frames:
        LOG.warn("정기보고서 토큰을 한 건도 확보하지 못했습니다 — D1 비활성화 대상입니다.")
        _arc_doc_fail_report(len(jobs))
        return pd.DataFrame(columns=ARC_DOC_COLS)

    T = pd.concat([f.reindex(columns=ARC_DOC_COLS) for f in frames], ignore_index=True)
    T["rcept_dt"] = as_ts_series(T["rcept_dt"])
    T = T.dropna(subset=["rcept_no", "section", "rcept_dt"])
    T = T.drop_duplicates(["rcept_no", "section"], keep="last").reset_index(drop=True)

    # ── 연도 샤드 저장 (신규분이 있는 연도만) ─────────────────────────────────────────────
    if got:
        new_years = sorted({int(r["bsns_year"]) for r in got})
        for y in new_years:
            g = T[T["bsns_year"].astype(int) == y]
            if len(g):
                VAULT.put_table(f"dart_doc_norm_{y}", g, scope="shared", domain="dart_text",
                                source="opendart document.xml + ARC 정규화",
                                extra={"note": "정규화 토큰(전 전략 공용) — <NUM>/<DATE>/"
                                               "<PERIOD>/<COMPANY> 마스킹 적용"})
        VAULT.flush("shared")

    n_doc = T["rcept_no"].nunique()
    LOG.ok(f"정기보고서 토큰 {len(T):,}행 · 문서 {n_doc:,}건 · {T['corp_code'].nunique():,}사 "
           f"(섹션 평균 {len(T)/max(n_doc,1):.1f}개)")
    _arc_doc_fail_report(len(jobs))
    PIPE.io("OUT", "DRIVE", "dart_doc_norm", T, source="opendart document.xml")
    return T

def _arc_doc_fail_report(n_try: int):
    """§0.4 — 기계판독 실패율을 반드시 측정·보고한다(구형 공시는 PDF 스캔본 비중이 높다)."""
    if not _ARC_DOC_FAIL:
        if n_try:
            LOG.ok(f"원문 파싱 실패 0건 / 시도 {n_try:,}건")
        return
    tot = sum(_ARC_DOC_FAIL.values())
    LOG.table([[k, f"{v:,}", f"{100*v/max(n_try,1):.1f}%"]
               for k, v in _ARC_DOC_FAIL.most_common()] +
              [["── 합계 ──", f"{tot:,}", f"{100*tot/max(n_try,1):.1f}%"]],
              ["실패 사유", "건수", "시도 대비"], ["l", "r", "r"],
              title="정기보고서 기계판독 실패 분해 (GATE_5 의 근거)")
    if n_try and tot / max(n_try, 1) > 0.20:
        LOG.warn(f"기계판독 실패율 {100*tot/n_try:.1f}% 가 20% 를 넘습니다. "
                 f"구형 공시의 PDF 스캔본 비중이 높은 구간이면 정상이며, D1 은 그 구간에서 "
                 f"결측 처리됩니다(0으로 채우지 않습니다).")

# ── 페어링 (§6.1.1) ─────────────────────────────────────────────────────────────────────────
ARC_PAIR_COLS = ["corp_code", "doc_type", "bsns_year", "section", "rcept_no", "prev_rcept_no",
                 "rcept_dt", "prev_rcept_dt", "tf", "prev_tf", "bigram", "prev_bigram",
                 "tok_len", "prev_tok_len", "is_amend"]

def arc_doc_pairs(T: pd.DataFrame) -> pd.DataFrame:
    """§6.1.1 '동일 유형 × 전년 동기' 페어링. 직전 분기 비교는 절대 하지 않는다.
    ★ 왜 직전 분기와 비교하면 안 되는가: 사업보고서(연간)와 분기보고서는 분량·구성이
    """
    if T is None or T.empty:
        return pd.DataFrame(columns=ARC_PAIR_COLS)
    d = T.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["corp_code", "doc_type", "bsns_year", "section", "rcept_dt"])
    d["bsns_year"] = pd.to_numeric(d["bsns_year"], errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    d["bsns_year"] = d["bsns_year"].astype(int)
    # ★ 계약 §4.1: 정정공시(is_amend)는 플래그만 기록하고 신호에는 쓰지 않는다.
    #   (상세 근거는 커밋 로그 참조)
    if "is_amend" in d.columns:
        am = d["is_amend"].astype(bool)
        n_am = int(am.sum())
        if n_am:
            # 원본이 존재하는 기수의 정정본만 뺀다. 정정본밖에 없으면 그거라도 써야
            # 그 기수가 통째로 사라지지 않는다(근거 없는 결측 금지).
            key = ["corp_code", "doc_type", "bsns_year", "section"]
            has_orig = d.loc[~am, key].drop_duplicates().assign(_orig=1)
            d = d.merge(has_orig, on=key, how="left")
            drop = am.to_numpy() & (d["_orig"] == 1).to_numpy()
            LOG.info(f"정정공시 {n_am:,}건 중 원본이 있는 {int(drop.sum()):,}건을 페어링에서 "
                     f"제외했습니다(§4.1 — 플래그만 기록, 신호 미사용). "
                     f"원본이 없는 {n_am - int(drop.sum()):,}건은 유지합니다.")
            d = d[~drop].drop(columns=["_orig"])
    # 같은 기수에 같은 종류가 여러 개면 마지막 접수본이 대표
    d = (d.sort_values("rcept_dt", kind="stable")
           .drop_duplicates(["corp_code", "doc_type", "bsns_year", "section"], keep="last"))

    prev = d.copy()
    prev["bsns_year"] = prev["bsns_year"] + 1           # 전년 → 당년 키로 맞춘다
    prev = prev.rename(columns={"rcept_no": "prev_rcept_no", "rcept_dt": "prev_rcept_dt",
                                "tf": "prev_tf", "bigram": "prev_bigram",
                                "tok_len": "prev_tok_len"})
    keep = ["corp_code", "doc_type", "bsns_year", "section", "prev_rcept_no",
            "prev_rcept_dt", "prev_tf", "prev_bigram", "prev_tok_len"]
    M = d.merge(prev[keep], on=["corp_code", "doc_type", "bsns_year", "section"], how="inner")

    # ★ 전년본 접수일이 당년본보다 늦으면(데이터 오류) 그 쌍은 버린다 — 미래 문서와의 비교다.
    bad = M["prev_rcept_dt"] >= M["rcept_dt"]
    if bad.any():
        LOG.warn(f"전년본 접수일이 당년본 이후인 쌍 {int(bad.sum()):,}건을 제외했습니다"
                 f"(원문 접수일 오류 또는 정정 순서 역전).")
        M = M[~bad]

    M = M.reindex(columns=ARC_PAIR_COLS)
    n_doc = M["rcept_no"].nunique() if len(M) else 0
    LOG.ok(f"전년 동기 페어 {len(M):,}쌍 · 문서 {n_doc:,}건 "
           f"(유형별: " + ", ".join(f"{k}={v:,}" for k, v in
                                    (M["doc_type"].value_counts().items() if len(M) else [])) + ")")
    PIPE.io("OUT", "MEM", "dart_doc_pairs", M)
    return M

def arc_norm_sample_report(T: pd.DataFrame, n: int = 5) -> None:
    """§10-[4] 육안 검증. 정규화가 가짜 변화를 실제로 제거했는지 사람이 확인하는 관문.

    ★ 이 단계에서 숫자·날짜·사명이 그대로 보이면 이후 D1 결과는 전부 무의미하다.
      그래서 '통과'를 코드가 자동 선언하지 않고 사람에게 보여준다.
    """
    LOG.banner("정규화 육안 검증 샘플 (§10-[4])",
               "여기에 숫자·날짜·사명이 그대로 남아 있으면 이후 D1 결과는 전부 무의미합니다")
    if T is None or T.empty:
        LOG.warn("정규화 결과가 없어 샘플을 보여줄 수 없습니다.")
        return
    sub = T[T["section"] == "S_MDA"]
    if sub.empty:
        sub = T[T["section"] == "S_ALL"]
    sub = sub.drop_duplicates("corp_code").head(int(n))
    rows = []
    for r in sub.itertuples(index=False):
        try:
            toks = list(json.loads(r.tf).items())[:22]
        except Exception:
            toks = []
        #   (상세 근거는 커밋 로그 참조)
        _tl = pd.to_numeric(getattr(r, "tok_len", np.nan), errors="coerce")
        rows.append([str(r.corp_code), str(r.doc_type), str(r.bsns_year),
                     (f"{int(_tl):,}" if np.isfinite(_tl) else "—"),
                     _trunc(" ".join(f"{k}×{v}" for k, v in toks), 92)])
    LOG.table(rows, ["법인코드", "유형", "사업연도", "토큰수", "상위 토큰 (정규화 후)"],
              ["l", "c", "c", "r", "l"], maxw=96)
    # 마스크가 실제로 작동했는지 정량 확인
    try:
        s = " ".join(T["tf"].head(200).astype(str).tolist())
        n_num = s.count("<NUM>")
        n_date = s.count("<DATE>")
        n_comp = s.count("<COMPANY>")
        raw_digit = len(re.findall(r'"[^"]*\d[^"]*"', s))
        LOG.table([["<NUM> 마스크 등장", f"{n_num:,}"],
                   ["<DATE> 마스크 등장", f"{n_date:,}"],
                   ["<COMPANY> 마스크 등장", f"{n_comp:,}"],
                   ["숫자가 남은 토큰(있으면 정규화 누락)", f"{raw_digit:,}"],
                   ["형태소 분석기", _DOC_TAGGER.get("kind") or "미결정"]],
                  ["점검 항목", "값"], ["l", "r"], title="정규화 마스킹 정량 점검")
        if raw_digit > 0:
            LOG.warn(f"토큰에 숫자가 {raw_digit:,}개 남아 있습니다. 숫자 마스킹 정규식이 놓친 "
                     f"패턴이 있다는 뜻이며, 그만큼 가짜 변화가 신호에 섞입니다.")
    except Exception:
        pass

def arc_doc_years(T: Optional[pd.DataFrame] = None) -> List[int]:
    """수집된 정기보고서의 사업연도 목록. 매니페스트가 있으면 그걸, 없으면 캐시 샤드를 본다."""
    if T is not None and len(T) and "bsns_year" in T.columns:
        return sorted(int(y) for y in pd.to_numeric(T["bsns_year"], errors="coerce")
                      .dropna().unique())
    out = []
    for y in range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1):
        pth = os.path.join(VAULT.table_dir("shared"), f"dart_doc_norm_{y}.parquet")
        if os.path.exists(pth):
            out.append(y)
    return out

def arc_doc_load_years(years: Sequence[int]) -> pd.DataFrame:
    """지정 연도의 토큰 샤드만 메모리에 올린다.

    ★ 왜 필요한가: 전 구간 토큰을 한 번에 들면 (2,500사 × 10년 × 4유형 × 7섹션) × 수 KB
      = 수 GB 가 되어 노트북이 죽는다. D1 은 '전년 동기' 만 필요하므로 2개 연도씩만
      올리면 상주량이 문서 수와 무관하게 평평해진다.
    """
    frames = []
    for y in sorted({int(x) for x in years}):
        d = VAULT.get_table(f"dart_doc_norm_{y}", scope="shared")
        if d is not None and len(d):
            frames.append(d.reindex(columns=ARC_DOC_COLS))
    if not frames:
        return pd.DataFrame(columns=ARC_DOC_COLS)
    T = pd.concat(frames, ignore_index=True)
    T["rcept_dt"] = as_ts_series(T["rcept_dt"])
    return T.dropna(subset=["rcept_no", "section", "rcept_dt"])
