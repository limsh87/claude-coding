
# ────────────────────────────────────────────────────────────────────────────────────────
#  L2-B3  D3 하드팩트(가점) + 배제 플래그(하드 제외)  §6.3 / §6.4
#  ★★ ΔNONFIN > 0 을 편입 조건으로 쓰지 않는다. v1.0 에서 폐기된 규칙이다.
#  D3 — 완료형 사실만 추출한다. 전망·계획·의지·기대·예정은 전부 제외.
# ────────────────────────────────────────────────────────────────────────────────────────

D3_EVENTS = [
    ("NF_RND_EMP",   "연구개발 인력 순증",              "기술·제조"),
    ("NF_RND_RATIO", "연구개발비/매출액 비율 상승",      "기술·제조"),
    ("NF_PATENT",    "특허 등록 건수 증가",              "기술·제조"),
    ("NF_CAPEX",     "유형자산 취득(설비투자)",          "제조·유통"),
    ("NF_CONTRACT",  "단일판매·공급계약 체결",           "전 섹터"),
    ("NF_GOVRND",    "정부 R&D 과제 선정",               "기술"),
    ("NF_NEWBIZ",    "신규 사업목적 추가 후 실제 매출",   "전 섹터"),
    ("NF_SUBSID",    "종속·관계기업 신규 취득",          "전 섹터"),
    ("NF_OVERSEAS",  "해외 신규 거점 설립",              "전 섹터"),
    ("NF_EMP",       "직원 수 순증(비R&D 포함)",         "전 섹터"),
]
D3_COLS = [c for c, _, _ in D3_EVENTS]

EXCL_DEFS = [
    ("EX_RELATED",    "특수관계자 매입/매출 비중 상승 (횡단면 상위 20%)"),
    ("EX_CONTINGENT", "우발부채·지급보증 증가 (자기자본 대비 5%p 이상)"),
    ("EX_LITIGATION", "신규 소송 (소송가액/자기자본 > 5%)"),
    ("EX_AUDIT",      "감사의견 특기사항/강조사항 존재"),
    ("EX_OWNER",      "최대주주 변경"),
    ("EX_CBBW",       "전환사채·신주인수권부사채 발행"),
    ("EX_LOSS4Q",     "4개 분기 연속 영업적자"),
    ("EX_IMPAIR",     "자본잠식률 > 30%"),
]
EXCL_COLS = [c for c, _ in EXCL_DEFS]

# ── 완료형 vs 전망형 (§6.3 추출 원칙) ───────────────────────────────────────────────────────
#   ★ 이 구분이 D3 의 전부다. '~할 계획입니다' 를 사실로 세면 D3 는 IR 문구 카운터가 된다.
_D3_FUTURE = re.compile(
    r"계획(이|입니다|임|중)|예정|전망|기대|목표로|추진\s*중|검토\s*중|협의\s*중|"
    r"할\s*것|하고자|하려|예상|방침|모색|준비\s*중|논의\s*중")
_D3_DONE = re.compile(
    r"완료(하였|했|되었|됨)|체결(하였|했|되었|함|됨)|취득(하였|했|함)|등록(하였|했|되었|됨)|"
    r"설립(하였|했|함)|선정(되었|됨)|승인(받았|되었)|개시(하였|했)|양수(하였|했)|"
    r"인수(하였|했|함)|출자(하였|했)|준공(하였|했)")
_D3_HAS_NUM = re.compile(r"<NUM>|\d")
_D3_HAS_DATE = re.compile(r"<DATE>|\d{4}\s*년|\d{1,2}\s*월")

_D3_KEY = {
    "NF_PATENT":   r"특허|실용신안|지식재산권|지적재산권",
    "NF_GOVRND":   r"국가연구개발|정부\s*과제|국책\s*과제|산업통상자원부|중소벤처기업부|"
                   r"과학기술정보통신부|한국산업기술|R&D\s*과제",
    "NF_SUBSID":   r"종속회사|관계기업|자회사|지분\s*취득|출자",
    "NF_OVERSEAS": r"해외\s*법인|현지\s*법인|해외\s*지점|해외\s*사무소|해외\s*공장|"
                   r"베트남|인도|멕시코|폴란드|헝가리|미국\s*법인|중국\s*법인",
    "NF_NEWBIZ":   r"사업\s*목적\s*(추가|변경)|신규\s*사업|신사업",
}
_D3_KEY_RE = {k: re.compile(v) for k, v in _D3_KEY.items()}

_D3_SENT_SPLIT = re.compile(r"(?<=[다\.])\s+|\n+")

def _d3_count_facts(text: str, pat: "re.Pattern") -> int:
    """완료형 동사 + 날짜 + 숫자가 모두 있는 문장만 센다. 정성적 판단은 하지 않는다."""
    if not text:
        return 0
    n = 0
    for s in _D3_SENT_SPLIT.split(text)[:4000]:
        if len(s) < 10 or not pat.search(s):
            continue
        if _D3_FUTURE.search(s):
            continue                      # 전망·계획·의지는 전부 제외
        if not _D3_DONE.search(s):
            continue                      # 완료형 동사 필수
        if not (_D3_HAS_NUM.search(s) and _D3_HAS_DATE.search(s)):
            continue                      # 날짜 + 숫자 필수
        n += 1
    return n

def _d3_text_by_doc(T: pd.DataFrame) -> pd.DataFrame:
    """정규화 토큰 테이블 → 문서 단위 **토큰 집합**.
    ★ 예전에는 tf(JSON dict 문자열)들을 이어붙인 문자열에 정규식을 그대로 걸었다. 두 가지가
    """
    cols = ["corp_code", "rcept_no", "rcept_dt", "blob", "tokens", "exact"]
    if T is None or T.empty:
        return pd.DataFrame(columns=cols)

    def _tokset(ss) -> set:
        out: set = set()
        for x in ss:
            d = _d1_load(x) if "_d1_load" in globals() else None
            if isinstance(d, dict) and d:
                out.update(map(str, d.keys()))
            else:
                out.update(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|<[A-Z]+>", str(x)))
        return out

    g = (T.sort_values("section")
          .groupby(["corp_code", "rcept_no"], observed=True)
          .agg(rcept_dt=("rcept_dt", "min"), tokens=("tf", _tokset)).reset_index())

    # ── 원문 재조회 → §6.3 완료형 판정(정확 경로)을 **실제로** 태운다 ──────────────────
    #   원문 zip 은 15 모듈이 공용 인덱스에 ("dart_doc","raw", rcept_no) 로 저장해 둔다.
    #   put_blob 의 uid 는 내용해시를 포함해 재구성할 수 없으므로 get_blob_by_key 로 찾는다.
    #   (상세 근거는 커밋 로그 참조)
    _keys = list(_D3_KEY_RE.keys())
    cand = g["tokens"].map(lambda ts: any(_d3_tokens_hit(ts, k) for k in _keys) or
                                      any(_d3_tokens_hit(ts, k) for k in _D3_WEAK_CONSTANT))
    cap = int(globals().get("ARC_D3_EXACT_MAX_DOCS", 4000))
    order = [i for i, c in enumerate(cand.to_numpy()) if c][:cap]
    n_cand, n_over = int(cand.sum()), max(0, int(cand.sum()) - len(order))
    blobs = [""] * len(g)
    exacts = [False] * len(g)
    _v = globals().get("VAULT")
    if _v is not None and order:
        rn_all = g["rcept_no"].astype(str).tolist()
        for i in order:
            raw = None
            try:
                raw = _v.get_blob_by_key("dart_doc", "raw", rn_all[i])
            except Exception:
                raw = None
            if not raw:
                continue
            try:
                txt = _doc_unzip_text(raw) if isinstance(raw, (bytes, bytearray)) else str(raw)
            except Exception:
                continue
            if txt and len(txt) > 500:
                # 원문 그대로 쓰면 표·태그가 문장 판정을 망친다 → 6단계 정규화를 태운다.
                try:
                    txt = arc_normalize_text(txt)
                except Exception:
                    pass
                blobs[i] = txt[:400_000]
                exacts[i] = True
    g["blob"] = blobs
    g["exact"] = exacts
    n_ex = int(sum(exacts))
    if n_cand:
        LOG.info(f"§6.3 정확 판정 후보 {n_cand:,}건 중 원문 확보 {n_ex:,}건"
                 + (f" · 상한({cap:,})으로 {n_over:,}건 미처리" if n_over else "")
                 + ". 원문이 없는 후보는 토큰 집합 기반 약한 판정으로 남습니다.")
    return g[cols]

# 다단어 판정용 — 패턴을 '있어야 할 토큰들의 선택지 집합' 으로 표현한다.
#   값: [[대안1토큰들], [대안2토큰들], ...]  (한 대안의 토큰이 전부 있으면 발화)
_D3_TOKEN_RULES: Dict[str, List[List[str]]] = {
    "NF_PATENT":   [["특허"], ["실용신안"], ["지식재산권"], ["지적재산권"]],
    "NF_GOVRND":   [["국가연구개발"], ["정부", "과제"], ["국책", "과제"],
                    ["산업통상자원부"], ["중소벤처기업부"], ["과학기술정보통신부"]],
    "NF_SUBSID":   [["종속회사"], ["관계기업"], ["자회사"], ["지분", "취득"], ["출자"]],
    "NF_OVERSEAS": [["해외", "법인"], ["현지", "법인"], ["해외", "지점"], ["해외", "공장"],
                    ["베트남"], ["인도"], ["멕시코"], ["폴란드"], ["헝가리"]],
    "NF_NEWBIZ":   [["사업", "목적", "추가"], ["사업", "목적", "변경"],
                    ["신규", "사업"], ["신사업"]],
}
# 단일 토큰만으로 발화하는 규칙은 '이 단어가 보고서 어딘가에 있는가' 라 사실상 상수가 된다.
# 원문(exact) 경로가 없을 때는 이 태그들을 0 이 아니라 **NaN(미판정)** 으로 둔다.
_D3_WEAK_CONSTANT = {"NF_PATENT", "NF_SUBSID"}

def _d3_tokens_hit(tokens: set, key: str) -> bool:
    for alt in _D3_TOKEN_RULES.get(key, []):
        if all(t in tokens for t in alt):
            return True
    return False

def extract_hardfacts(T: pd.DataFrame, fin: pd.DataFrame, emp: pd.DataFrame,
                      dis: pd.DataFrame, notes: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """§6.3 하드팩트 추출. 반환 (PIT frame): corp_code, event_date, knowledge_date, NF_*, DELTA_NONFIN."""
    cols = ["corp_code", "event_date", "knowledge_date"] + D3_COLS + \
           ["DELTA_NONFIN", "D3_N_OBS"]
    parts: List[pd.DataFrame] = []

    # ── (A) 재무 기반 이벤트: 정량이라 가장 신뢰도 높다 ────────────────────────────────────
    if fin is not None and len(fin) and "corp_code" in fin.columns:
        F = fin.copy()
        F["corp_code"] = F["corp_code"].astype(str)
        F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
        F["_q"] = F["reprt_code"].astype(str).map(_D2_QORD)
        F = F.dropna(subset=["bsns_year", "_q"])
        F["_seq"] = F["bsns_year"].astype(int) * 4 + F["_q"].astype(int)
        F = (F.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last"))

        def _lag4(v: pd.Series) -> pd.Series:
            prev = v.groupby(F["corp_code"], observed=True).shift(4)
            pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(4)
            return prev.where((F["_seq"] - pseq) == 4)

        rnd_ratio = safe_div(col(F, "rnd_ttm"), col(F, "revenue_ttm"))
        ppe = col(F, "ppe")
        A = pd.DataFrame({
            "corp_code": F["corp_code"],
            "event_date": as_ts_series(F["period_end"]) if "period_end" in F.columns else pd.NaT,
            # §4 접수일 + 1거래일 (재무제표는 접수 당일 사용 불가)
            "knowledge_date": (as_ts_series(F["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in F.columns else pd.NaT,
            # 완료형 정량 사실: 전년 동기 대비 실제 증가 (계획이 아니라 재무제표에 찍힌 값)
            "NF_RND_RATIO": (rnd_ratio > _lag4(rnd_ratio)).astype(float)
                            .where(rnd_ratio.notna() & _lag4(rnd_ratio).notna()),
            "NF_CAPEX": (safe_div(ppe - _lag4(ppe), _lag4(ppe).abs()) > 0.10).astype(float)
                        .where(_lag4(ppe).notna()),
        })
        parts.append(A)

    # ── (B) 직원 현황 기반 ─────────────────────────────────────────────────────────────────
    if emp is not None and len(emp) and "corp_code" in emp.columns:
        E = emp.copy()
        E["corp_code"] = E["corp_code"].astype(str)
        E["bsns_year"] = pd.to_numeric(E["bsns_year"], errors="coerce")
        E = E.dropna(subset=["bsns_year"]).sort_values(["corp_code", "bsns_year"], kind="stable")
        prev = E.groupby("corp_code", observed=True)["employees"].shift(1)
        pyr = E.groupby("corp_code", observed=True)["bsns_year"].shift(1)
        prev = prev.where((E["bsns_year"] - pyr) == 1)
        B = pd.DataFrame({
            "corp_code": E["corp_code"],
            "event_date": as_ts_series(E["period_end"]) if "period_end" in E.columns else pd.NaT,
            "knowledge_date": (as_ts_series(E["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in E.columns else pd.NaT,
            "NF_EMP": (pd.to_numeric(E["employees"], errors="coerce") > prev).astype(float)
                      .where(prev.notna()),
        })
        # R&D 인력은 별도 컬럼이 없다 → 직원 순증과 R&D 비율 상승이 동시 성립할 때만 인정
        B["NF_RND_EMP"] = np.nan
        parts.append(B)

    # ── (C) 수시공시 기반: 단일판매·공급계약 ───────────────────────────────────────────────
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        D = dis.copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        hit = D["report_nm"].astype(str).str.contains(
            r"단일판매|공급계약\s*체결|수주", regex=True, na=False)
        C = D.loc[hit, ["corp_code", "rcept_dt"]].dropna().copy()
        if len(C):
            C["corp_code"] = C["corp_code"].astype(str)
            C["event_date"] = C["rcept_dt"]
            C["knowledge_date"] = C["rcept_dt"] + pd.Timedelta(days=ARC_DART_LAG_DAYS)
            C["NF_CONTRACT"] = 1.0
            parts.append(C[["corp_code", "event_date", "knowledge_date", "NF_CONTRACT"]])

    # ── (D) 문서 텍스트 기반: 특허·정부과제·종속회사·해외거점·신규사업 ─────────────────────
    n_weak, n_exact, n_doc_txt = 0, 0, 0
    if T is not None and len(T):
        DOC = _d3_text_by_doc(T)
        n_doc_txt = int(len(DOC))
        if len(DOC):
            rows = []
            for r in DOC.itertuples(index=False):
                blob = str(getattr(r, "blob", "") or "")
                toks = getattr(r, "tokens", None) or set()
                rec = {"corp_code": str(r.corp_code),
                       "event_date": as_ts(r.rcept_dt),
                       "knowledge_date": as_ts(r.rcept_dt) + pd.Timedelta(days=ARC_DART_LAG_DAYS)}
                if bool(r.exact):
                    n_exact += 1
                for k, rx in _D3_KEY_RE.items():
                    if bool(r.exact):
                        # §6.3 정확 경로 — 완료형 동사 + 날짜 + 숫자를 갖춘 문장만 센다.
                        rec[k] = 1.0 if _d3_count_facts(blob, rx) > 0 else 0.0
                    elif k in _D3_WEAK_CONSTANT:
                        # ★ 단일 토큰 존재 여부는 이벤트가 아니라 상수다. 0 으로 두면
                        #   '사실 없음' 으로 오독되므로 NaN(미판정) 으로 남긴다.
                        rec[k] = np.nan
                    else:
                        # 약한 증거 경로: 토큰 집합 기반 다단어 판정. 완료형/전망형은
                        #   구분할 수 없으므로 과대계상 가능 — 건수를 따로 보고한다.
                        rec[k] = 1.0 if _d3_tokens_hit(toks, k) else 0.0
                rows.append(rec)
            Dx = pd.DataFrame(rows)
            if len(Dx):
                n_weak = int(Dx[[c for c in _D3_KEY_RE if c in Dx.columns]].sum().sum())
                parts.append(Dx)

    if not parts:
        LOG.warn("D3 하드팩트 입력이 하나도 없습니다 — D3_SCORE 는 전 구간 결측입니다 "
                 "(§6.3 은 가점이므로 다른 축으로 가중치가 재배분됩니다).")
        return pd.DataFrame(columns=cols)

    H = pd.concat([p for p in parts if p is not None and len(p)], ignore_index=True)
    H["corp_code"] = H["corp_code"].astype(str)
    H["event_date"] = as_ts_series(H["event_date"])
    H["knowledge_date"] = as_ts_series(H["knowledge_date"])
    H = H.dropna(subset=["corp_code", "knowledge_date"])
    H = ensure_cols(H, D3_COLS, fill=np.nan)
    # 같은 (법인, 공개일) 의 여러 소스를 합친다. 각 이벤트는 바이너리 태그이므로 max.
    H = H.groupby(["corp_code", "knowledge_date"], as_index=False).agg(
        **{"event_date": ("event_date", "min"),
           **{c: (c, "max") for c in D3_COLS}})
    # ★ 배제 플래그와 같은 이유로(소스별 행이 서로를 덮음) 상태 테이블로 변환한다.
    #   D3 는 '직전 1년 안에 이 사실이 관측되었는가' 의 합이 된다 — 분기 내 여러 이벤트가
    #   마지막 1행으로 대체되어 사라지던 문제도 함께 해소된다.
    H = _event_state_table(H, D3_COLS, D3_VALID_DAYS)
    # ★ sum(skipna=True) 는 NaN 을 0 으로 취급하고 전부 NaN 인 행도 0.0 을 돌려준다.
    #   _event_state_table 이 방금 보존한 '모름 ≠ 미발화' 불변식이 두 줄 뒤에서 깨진다.
    #   (상세 근거는 커밋 로그 참조)
    H["D3_N_OBS"] = H[D3_COLS].notna().sum(axis=1).astype("int16")
    H["DELTA_NONFIN"] = H[D3_COLS].sum(axis=1, skipna=True).where(H["D3_N_OBS"] > 0)
    H = pit_frame(H, "event_date", "knowledge_date", source="dart_d3")
    H = ensure_cols(H, cols)
    fired = {c: int(pd.to_numeric(H[c], errors="coerce").fillna(0).sum()) for c in D3_COLS}
    LOG.ok(f"D3 하드팩트 {len(H):,}행 · {H['corp_code'].nunique():,}사 · "
           f"이벤트 총 {int(H['DELTA_NONFIN'].sum()):,}건")
    LOG.table([[c, d, s, f"{fired[c]:,}"] for c, d, s in D3_EVENTS],
              ["태그", "이벤트", "섹터 적용성", "발화 건수"], ["l", "l", "l", "r"],
              title="D3 이벤트별 발화 (v2.0 에서 전 섹터 항목 4개 추가)")
    if n_weak:
        LOG.warn(f"문서 텍스트 기반 이벤트 {n_weak:,}건은 '약한 증거' 경로로 판정되었습니다. "
                 f"원문 blob 이 없는 문서는 토큰 집합만으로 판정하므로 완료형/전망형을 "
                 f"구분하지 못합니다 → D3 가 과대계상될 수 있습니다. D3 가중치가 0.20 으로 "
                 f"낮고 가점으로만 쓰이는 것이 이 한계를 완충합니다.")
    if n_doc_txt:
        LOG.info(f"§6.3 완료형 판정 — 원문 확보 {n_exact:,}/{n_doc_txt:,}건에서만 문장 단위 "
                 f"(완료형 동사 + 날짜 + 숫자) 필터가 적용됩니다. 나머지는 토큰 집합 기반 "
                 f"약한 판정이며, 단일 토큰만으로 발화하는 태그"
                 f"({' · '.join(sorted(_D3_WEAK_CONSTANT))})는 0 이 아니라 결측입니다.")
        if n_exact == 0:
            LOG.warn("원문 blob 을 하나도 확보하지 못해 §6.3 '완료형만' 필터가 한 건도 "
                     "적용되지 않았습니다. 문서 텍스트 기반 NF_* 는 '그 단어가 보고서에 "
                     "나오는가' 수준의 약한 증거입니다 — D3 해석 시 반드시 감안하세요.")
    PIPE.io("OUT", "MEM", "d3_hardfacts", H)
    return H[cols]

# ── 배제 플래그 (§6.4) ──────────────────────────────────────────────────────────────────────
_EX_OWNER_PAT = r"최대주주\s*변경|최대주주변경"
_EX_CBBW_PAT = r"전환사채|신주인수권부사채|교환사채"

# 플래그별 유효기간(일). 감사의견은 연 1회 갱신되므로 다음 감사보고서까지(≈15개월),
# 나머지 이벤트는 1년 남짓 유효한 것으로 사전등록한다. 튜닝 대상이 아니다.
EXCL_VALID_DAYS = {"EX_RELATED": 400, "EX_CONTINGENT": 400, "EX_LITIGATION": 400,
                   "EX_AUDIT": 460, "EX_OWNER": 370, "EX_CBBW": 370,
                   "EX_LOSS4Q": 400, "EX_IMPAIR": 400}
D3_VALID_DAYS = 370          # 하드팩트 이벤트는 직전 1년치를 센다

def _event_state_table(X: pd.DataFrame, cols: Sequence[str],
                       valid_days, key: str = "corp_code",
                       tcol: str = "knowledge_date") -> pd.DataFrame:
    """소스별로 흩어진 '이벤트' 행들을 시점마다 완결된 '상태' 행으로 바꾼다.
    ★ 이 함수가 없으면 §6.4 하드 제외가 사실상 작동하지 않는다. 왜인지 남긴다:
    """
    if X is None or len(X) == 0:
        return X
    cols = [c for c in cols if c in X.columns]
    if not cols:
        return X
    W = {c: int(valid_days.get(c, 400) if isinstance(valid_days, dict) else valid_days)
         for c in cols}

    B = X[[key, tcol]].copy()
    B[tcol] = as_ts_series(B[tcol])
    B = B.dropna(subset=[key, tcol])

    # 타임라인 = 원 관측 시점 ∪ 발화 만료 시점
    tls = [B]
    fired: Dict[str, pd.DataFrame] = {}
    for c in cols:
        v = pd.to_numeric(X[c], errors="coerce")
        f = X.loc[v > 0, [key, tcol]].copy()
        f[tcol] = as_ts_series(f[tcol])
        f = f.dropna(subset=[key, tcol]).sort_values([tcol], kind="stable")
        fired[c] = f.rename(columns={tcol: "_fired"})
        if len(f):
            e = f.copy()
            e[tcol] = e[tcol] + pd.Timedelta(days=W[c])
            tls.append(e[[key, tcol]])
    TL = (pd.concat(tls, ignore_index=True)
            .drop_duplicates([key, tcol]).sort_values([tcol, key], kind="stable")
            .reset_index(drop=True))

    # 플래그별로 '가장 최근 발화'를 as-of 로 찾아 유효기간 내면 1, 아니면 0
    for c in cols:
        f = fired[c]
        if len(f):
            m = pd.merge_asof(TL, f.sort_values("_fired", kind="stable"),
                              left_on=tcol, right_on="_fired", by=key, direction="backward")
            age = (m[tcol] - m["_fired"]).dt.days
            TL[c] = np.where(age.notna() & (age < W[c]), 1.0, 0.0)
        else:
            TL[c] = 0.0
        # 그 법인에 대해 해당 플래그의 관측이 애초에 없었다면 0 이 아니라 NaN(모름)
        obs = X.loc[pd.to_numeric(X[c], errors="coerce").notna(), key].astype(str).unique()
        TL[c] = TL[c].where(TL[key].astype(str).isin(set(obs)))

    # event_date 는 그 시점까지 알려진 가장 이른 원 이벤트일 — 없으면 관측 시점 자체
    if "event_date" in X.columns:
        ed = (X[[key, tcol, "event_date"]].copy())
        ed[tcol] = as_ts_series(ed[tcol]); ed["event_date"] = as_ts_series(ed["event_date"])
        ed = ed.dropna(subset=[key, tcol]).sort_values(tcol, kind="stable")
        m = pd.merge_asof(TL, ed, left_on=tcol, right_on=tcol, by=key, direction="backward")
        TL["event_date"] = m["event_date"].fillna(TL[tcol])
    else:
        TL["event_date"] = TL[tcol]
    return TL

def build_exclusion_flags(fin: pd.DataFrame, dis: pd.DataFrame,
                          audit: Optional[pd.DataFrame] = None,
                          T: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """§6.4 하드 제외 플래그. 반환 (PIT frame): corp_code, event_date, knowledge_date, EX_*."""
    cols = ["corp_code", "event_date", "knowledge_date"] + EXCL_COLS
    parts: List[pd.DataFrame] = []
    miss_note: List[str] = []

    # ── 재무 기반: 4분기 연속 영업적자 / 자본잠식 ─────────────────────────────────────────
    if fin is not None and len(fin) and "corp_code" in fin.columns:
        F = fin.copy()
        F["corp_code"] = F["corp_code"].astype(str)
        F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
        F["_q"] = F["reprt_code"].astype(str).map(_D2_QORD)
        F = F.dropna(subset=["bsns_year", "_q"])
        F["_seq"] = F["bsns_year"].astype(int) * 4 + F["_q"].astype(int)
        F = (F.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last").reset_index(drop=True))
        # ★ 분기 프레임에서 센다. 패널에서 세면 같은 분기값 반복 때문에 4연속 판정이 틀어진다.
        #   min_periods=4 — 제출분이 4개 미만이면 발동하지 않는다(근거 없는 제외 금지).
        neg = (col(F, "op_income_q") < 0).astype(float)
        neg = neg.where(col(F, "op_income_q").notna())
        streak = (neg.groupby(F["corp_code"], observed=True)
                     .transform(lambda s: s.rolling(4, min_periods=4).min()))
        eq = col(F, "equity")
        cap = col(F, "capital_stock") if "capital_stock" in F.columns else pd.Series(np.nan,
                                                                                     index=F.index)
        if cap.notna().any():
            impair = safe_div(cap - eq, cap)
            ex_imp = (impair > 0.30).astype(float).where(impair.notna())
        else:
            miss_note.append("자본금 계정이 없어 EX_IMPAIR 은 완전자본잠식(자기자본<0)만 판정")
            ex_imp = (eq < 0).astype(float).where(eq.notna())
        parts.append(pd.DataFrame({
            "corp_code": F["corp_code"],
            "event_date": as_ts_series(F["period_end"]) if "period_end" in F.columns else pd.NaT,
            "knowledge_date": (as_ts_series(F["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in F.columns else pd.NaT,
            "EX_LOSS4Q": streak.fillna(0.0),
            "EX_IMPAIR": ex_imp,
        }))

    # ── 공시목록 기반: 최대주주 변경 / CB·BW ──────────────────────────────────────────────
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        D = dis.copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        D["corp_code"] = D["corp_code"].astype(str)
        nm = D["report_nm"].astype(str)
        ev = pd.DataFrame({
            "corp_code": D["corp_code"], "event_date": D["rcept_dt"],
            "knowledge_date": D["rcept_dt"] + pd.Timedelta(days=ARC_DART_LAG_DAYS),
            "EX_OWNER": nm.str.contains(_EX_OWNER_PAT, regex=True, na=False).astype(float),
            "EX_CBBW": nm.str.contains(_EX_CBBW_PAT, regex=True, na=False).astype(float),
        })
        ev = ev[(ev["EX_OWNER"] > 0) | (ev["EX_CBBW"] > 0)].dropna(subset=["knowledge_date"])
        if len(ev):
            parts.append(ev)

    # ── 감사의견 ──────────────────────────────────────────────────────────────────────────
    if audit is not None and len(audit):
        A = audit.copy()
        A["corp_code"] = A["corp_code"].astype(str)
        opi = A.get("audit_opinion", pd.Series("", index=A.index)).astype(str)
        emp_ = A.get("emphasis", pd.Series("", index=A.index)).astype(str)
        key = A.get("key_matter", pd.Series("", index=A.index)).astype(str)
        bad_opinion = opi.str.contains("한정|부적정|의견거절", na=False)
        has_emph = (emp_.str.len() > 0) | (key.str.len() > 0)
        parts.append(pd.DataFrame({
            "corp_code": A["corp_code"],
            "event_date": as_ts_series(A["period_end"]) if "period_end" in A.columns else pd.NaT,
            "knowledge_date": (as_ts_series(A["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in A.columns else pd.NaT,
            "EX_AUDIT": (bad_opinion | has_emph).astype(float),
        }))
    else:
        miss_note.append("감사의견 데이터 부재 — EX_AUDIT 결측")

    # ── 특수관계자 / 우발부채 / 소송 ──────────────────────────────────────────────────────
    #   ★ 이 셋은 '금액' 판정이 필요한데, 15 모듈의 정규화는 숫자를 <NUM> 으로 치환한다.
    #   (상세 근거는 커밋 로그 참조)
    miss_note.append("EX_RELATED / EX_CONTINGENT / EX_LITIGATION 은 금액 판정이 필요해 "
                     "정규화 이전 원문 재파싱이 선행되어야 합니다 — 현재 결측 처리")

    if not parts:
        LOG.warn("배제 플래그 입력이 없습니다 — EXCLUDE 는 전부 0 이 되며, §6.4 하드 제외가 "
                 "작동하지 않습니다. 이는 위험 종목이 그대로 편입된다는 뜻이므로 심각합니다.")
        return pd.DataFrame(columns=cols)

    X = pd.concat([p for p in parts if p is not None and len(p)], ignore_index=True)
    X["corp_code"] = X["corp_code"].astype(str)
    X["event_date"] = as_ts_series(X["event_date"])
    X["knowledge_date"] = as_ts_series(X["knowledge_date"])
    X = X.dropna(subset=["corp_code", "knowledge_date"])
    X = ensure_cols(X, EXCL_COLS, fill=np.nan)
    X = X.groupby(["corp_code", "knowledge_date"], as_index=False).agg(
        **{"event_date": ("event_date", "min"), **{c: (c, "max") for c in EXCL_COLS}})
    n_raw_fire = int(sum(int((pd.to_numeric(X[c], errors="coerce") > 0).sum())
                         for c in EXCL_COLS))
    # ★ 소스별 행이 서로의 플래그를 지우는 문제를 여기서 잡는다(_event_state_table 주석 참조).
    X = _event_state_table(X, EXCL_COLS, EXCL_VALID_DAYS)
    X = pit_frame(X, "event_date", "knowledge_date", source="dart_excl")
    X = ensure_cols(X, cols)
    n_state_on = int((pd.DataFrame({c: pd.to_numeric(X[c], errors="coerce").fillna(0.0)
                                    for c in EXCL_COLS}).sum(axis=1) > 0).sum())
    LOG.ok(f"배제 플래그 {len(X):,}상태행 · {X['corp_code'].nunique():,}사 · "
           f"원 발화 {n_raw_fire:,}건 → 유효기간 반영 후 '제외 상태' {n_state_on:,}행")
    LOG.info("플래그 유효기간(사전등록): " +
             " · ".join(f"{c} {EXCL_VALID_DAYS.get(c, 400)}일" for c in EXCL_COLS))
    for n in miss_note:
        LOG.warn(f"[배제 플래그 한계] {n}")
    PIPE.io("OUT", "MEM", "exclusion_flags", X)
    return X[cols]

def attach_d3(P: pd.DataFrame, d3: Optional[pd.DataFrame],
              excl: Optional[pd.DataFrame]) -> pd.DataFrame:
    """D3_SCORE(가점) + EXCLUDE(하드 제외) 결합."""
    P = P.copy()
    if d3 is not None and len(d3) and "corp_code" in P.columns:
        PIT.register("arc_d3", d3, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d3", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + D3_COLS +
                               ["DELTA_NONFIN", "D3_N_OBS"],
                          suffix="_d3")
    P = ensure_cols(P, D3_COLS + ["DELTA_NONFIN", "D3_N_OBS"])

    if excl is not None and len(excl) and "corp_code" in P.columns:
        PIT.register("arc_excl", excl, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_excl", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + EXCL_COLS, suffix="_ex")
    P = ensure_cols(P, EXCL_COLS)

    # ★ D3_SCORE = z(ΔNONFIN). 가점이다. ΔNONFIN>0 을 편입 조건으로 쓰는 코드는 없다(A9).
    P["DELTA_NONFIN"] = pd.to_numeric(P["DELTA_NONFIN"], errors="coerce")
    P["D3_SCORE"] = xsec_z_arc(P, "DELTA_NONFIN")

    ex = pd.DataFrame({c: pd.to_numeric(P[c], errors="coerce").fillna(0.0) for c in EXCL_COLS})
    P["EXCLUDE"] = (ex.sum(axis=1) > 0).astype("float32")
    n_ex = int(P["EXCLUDE"].sum())
    LOG.ok(f"D3 가점 유효 {int(P['D3_SCORE'].notna().sum()):,}행 · "
           f"배제 발동 {n_ex:,}행 ({100*n_ex/max(len(P),1):.1f}%)")
    n_zero = int((P["DELTA_NONFIN"].fillna(0) == 0).sum())
    LOG.info(f"ΔNONFIN = 0 인 종목-시점 {n_zero:,}행 ({100*n_zero/max(len(P),1):.1f}%) — "
             f"★ v1.0 과 달리 이들도 편입 가능합니다(하드게이트 폐기, §6.3).")
    return P

def report_d3_sector(P: pd.DataFrame) -> None:
    """§9.2-(9) 근거 — 섹터별 D3 발화율. v1.0 의 기술·제조 편향이 완화됐는지 직접 본다."""
    LOG.banner("D3 섹터 편향 점검 (§6.3 v2.0 개선 확인)",
               "v1.0 화이트리스트 6개는 기술·제조 편향이 심했다. 전 섹터 항목 4개를 추가한 효과를 본다")
    if P is None or P.empty or "sector" not in P.columns:
        LOG.warn("섹터 정보가 없어 편향 점검을 할 수 없습니다.")
        return
    rows = []
    for s, g in P.groupby(P["sector"].astype(str)):
        n = len(g)
        fire = float((pd.to_numeric(g["DELTA_NONFIN"], errors="coerce").fillna(0) > 0).mean())
        legacy = [c for c in ("NF_RND_EMP", "NF_RND_RATIO", "NF_PATENT", "NF_CAPEX",
                              "NF_CONTRACT", "NF_GOVRND") if c in g.columns]
        newc = [c for c in ("NF_NEWBIZ", "NF_SUBSID", "NF_OVERSEAS", "NF_EMP") if c in g.columns]
        lf = float(g[legacy].fillna(0).max(axis=1).mean()) if legacy else np.nan
        nf = float(g[newc].fillna(0).max(axis=1).mean()) if newc else np.nan
        rows.append([s, f"{n:,}", f"{100*fire:.1f}%",
                     f"{100*lf:.1f}%" if np.isfinite(lf) else "—",
                     f"{100*nf:.1f}%" if np.isfinite(nf) else "—"])
    LOG.table(sorted(rows, key=lambda r: -float(r[2].rstrip("%"))),
              ["섹터", "표본", "ΔNONFIN>0 비율", "v1.0 항목 발화율", "v2.0 추가항목 발화율"],
              ["l", "r", "r", "r", "r"])
    LOG.info("v2.0 추가항목(신규사업·종속기업·해외거점·직원증가)의 발화율이 비기술 섹터에서 "
             "v1.0 항목보다 높다면, 섹터 편향 완화가 실제로 작동한 것입니다.")

def report_exclusion(P: pd.DataFrame) -> None:
    """배제 플래그별 발동 건수·비율·연도별 추이."""
    LOG.banner("배제 플래그 (§6.4 — 유일한 하드 제외)",
               "하나라도 해당하면 점수 무관 즉시 제외한다")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    rows = []
    for c, desc in EXCL_DEFS:
        v = pd.to_numeric(col(P, c), errors="coerce")
        n_obs = int(v.notna().sum())
        n_fire = int((v.fillna(0) > 0).sum())
        rows.append([c, _trunc(desc, 42), f"{n_obs:,}", f"{100*n_obs/max(len(P),1):.0f}%",
                     f"{n_fire:,}", f"{100*n_fire/max(len(P),1):.2f}%"])
    LOG.table(rows, ["플래그", "정의", "관측", "관측률", "발동", "발동률"],
              ["l", "l", "r", "r", "r", "r"])
    tot = int(pd.to_numeric(col(P, "EXCLUDE"), errors="coerce").fillna(0).sum())
    LOG.info(f"최종 배제 {tot:,}행 ({100*tot/max(len(P),1):.1f}%). "
             f"관측률이 0% 인 플래그는 그 위험을 전혀 거르지 못한다는 뜻이므로, "
             f"위 '배제 플래그 한계' 경고와 함께 해석하세요.")
    if "asof" in P.columns:
        yr = as_ts_series(P["asof"]).dt.year
        tr = []
        for y, g in P.groupby(yr):
            tr.append([int(y), f"{len(g):,}"] +
                      [f"{100*pd.to_numeric(col(g,c),errors='coerce').fillna(0).gt(0).mean():.1f}%"
                       for c, _ in EXCL_DEFS])
        LOG.table(tr, ["연도", "표본"] + EXCL_COLS, ["c", "r"] + ["r"] * len(EXCL_COLS),
                  title="배제 플래그 연도별 발동률")
