

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무 (벌크 우선) · 직원현황 · 공시목록                                       ║
# ║                                                                                          ║
# ║  §4.1 Primary  : 재무정보 일괄다운로드 (분기 단위 벌크). 종목별 루프 금지.                 ║
# ║  §4.1 Fallback A: fnlttMultiAcnt 다종목 배치(100사/호출). 단, '주요계정'만 온다.           ║
# ║  §4.1 Fallback B: fnlttSinglAcntAll 종목별. 예산 초과 확실 — 사용자 승인 후에만.           ║
# ║                                                                                          ║
# ║  ★ 벌크 파일의 함정: 벌크 txt 에는 **접수일자(rcept_dt)가 없다.** 결산기준일만 있다.       ║
# ║    그대로 knowledge_date 로 쓰면 45~90일치 미래누수가 통째로 들어간다(C1 정면 위반).       ║
# ║    → 공시목록(list.json, pblntf_ty="A")에서 (회사, 보고서종류, 사업연도) → rcept_dt 를     ║
# ║      만들어 결합한다. 결합 실패분은 법정 제출기한으로 보수적 추정한다                       ║
# ║      (보수적 추정 = '늦게 알았다' 방향이므로 누수를 만들지 않는다).                         ║
# ║    이것이 사용자가 요구한 '다중소스 원장연결'의 실체다 — 벌크는 값을, 공시목록은 시점을.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_DAILY_LIMIT = 19_000                 # 공식 20,000 대비 여유
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
# 벌크 파일명·공시 제목에 쓰이는 보고서 명칭 ↔ reprt_code
REPRT_NAME = {"11013": "1분기보고서", "11012": "반기보고서",
              "11014": "3분기보고서", "11011": "사업보고서"}
REPRT_BY_NAME = {v: k for k, v in REPRT_NAME.items()}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class DartBudget:
    """일일 호출 한도를 드라이브에 영속 기록. 재실행 시 이어받기의 근거."""

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0
        self.exhausted = False
        self._lk = threading.Lock()
        self._load()

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_budget.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘 이미 사용한 DART 호출 {self.n:,}건 (한도 {DART_DAILY_LIMIT:,}) — 이어서 진행합니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps({"date": self.today, "n": self.n}))
        except Exception:
            pass

    def refund(self, k: int = 1):
        if k > 0:
            with self._lk:
                self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.n + k > DART_DAILY_LIMIT:
                if not self.exhausted:
                    self.exhausted = True
                    LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                             f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일 같은 "
                             f"코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                return False
            self.n += k
            if self.n % 500 == 0:
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, source: str = "dart", tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 tries 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 한도를 넘긴다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DBUDGET is not None:
        DBUDGET.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            LOG.warn(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Primary — 재무정보 일괄다운로드 (벌크)
# ═══════════════════════════════════════════════════════════════════════════════════════════
DART_BULK_PAGE = "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do"
DART_BULK_DL = [
    "https://opendart.fss.or.kr/cmm/downloadFnltt.do",
    "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/download.do",
]
# 벌크 파일명 규칙(관측된 형태). 확정할 수 없으므로 페이지에서 '발견'을 우선하고
# 이 후보들은 발견이 실패했을 때만 쓴다. 어느 경로가 통했는지는 CANARY 표에 남는다.
BULK_STATEMENTS = ["재무상태표", "손익계산서", "포괄손익계산서", "현금흐름표"]
BULK_CONSOL = ["연결", "개별"]

_BULK_FLNM_RE = re.compile(r"(20\d{2}_[^\"'<>|]{4,80}?\.(?:zip|txt))", re.I)


#  ★★ 추측 후보를 만들지 않는다 ★★
#  예전엔 f"{year}_{보고서}_{NN}_{제표}_{연결구분}.zip" 8개를 만들어 시도했다. 성공 확률은
#  **구조적으로 0** 이다 — 실물 파일명이
#      2024_사업보고서_01_재무상태표_연결_20250606.txt
#  처럼 끝에 **배포일자**를 달고 있고, 그건 관측하지 않으면 알 수 없다(제표·연도마다 다르고
#  재배포되면 바뀐다). 게다가 개별은 '_개별'이 아니라 접미사가 없고 확장자도 상황에 따라 다르다.
#  그 결과 이 함수는 '안전망'이 아니라 **실패를 8배로 부풀려 진짜 원인(목록 발견 실패)을
#  로그에서 가리는 장치**였고, 분기마다 32요청을 헛되이 태웠다.
#  → 발견하지 못하면 즉시 폴백으로 내려간다. 그게 유일하게 정직한 동작이다.


def _bulk_discover(year: int, reprt: str) -> Tuple[List[str], str]:
    """페이지에서 실제 fl_nm 을 찾아낸다. 파일명 규칙을 추측하지 않는 것이 1순위다.

    반환 (후보 목록, 진단문자열).
    ★ 진단문자열이 핵심이다. "후보 N개 전부 실패" 만 남기면 사용자 로그를 받아도 원인을
      특정할 수 없다. 페이지를 받았는지 / 로그인 벽인지 / 어떤 링크·폼·스크립트가 있었는지를
      남겨야 다음 실행 로그 한 장으로 고칠 수 있다.
    """
    # ★ 파라미터 이름을 창작하지 않는다. selectYear/selectReprtCode 는 근거가 없는 이름이었고
    #   (공개 코드 전수검색 0건), 그걸 붙여도 서버는 무시하고 기본(최신) 연도 목록만 준다.
    #   그러면 `if str(year) in h` 필터에서 hits=[] 가 되어 '발견 실패'가 조용히 발생한다.
    #   → 폼/스크립트에서 **실제 파라미터 이름을 배워서** 재시도한다. 배우지 못하면 실패로 보고.
    html = http_get(DART_BULK_PAGE, source="dart", tries=2,
                    referer="https://opendart.fss.or.kr/")
    if not html:
        return [], "페이지 응답 없음(네트워크 차단·타임아웃·403 가능). HTTP 감사표를 확인하세요"
    fields = dict.fromkeys(re.findall(r'<(?:input|select)[^>]+name\s*=\s*["\']([^"\']+)["\']',
                                      html, re.I))
    y_key = next((k for k in fields if re.search(r"year|yr|연도", k, re.I)), None)
    r_key = next((k for k in fields if re.search(r"reprt|report|qtr|quarter|분기", k, re.I)), None)
    if y_key:
        params = {y_key: str(year)}
        if r_key:
            params[r_key] = reprt
        h2 = http_get(DART_BULK_PAGE, source="dart", tries=1, params=params,
                      referer=DART_BULK_PAGE)
        if h2 and str(year) in h2:
            html = h2
    low = html.lower()
    marks = []
    if "login" in low or "로그인" in html:
        marks.append("로그인벽 의심")
    for kw in ("downloadfnltt", "fl_nm", "downloadzip", "flnm", "download.do"):
        if kw in low:
            marks.append(f"'{kw}' 발견")
    # 확인된 DOM(셀레늄 자동화 선례): table.tb01 의 a[onclick] 마지막 인자가 실제 파일명이다.
    hits = list(dict.fromkeys(
        [m for m in _BULK_FLNM_RE.findall(html)] +
        [a for a in re.findall(r"['\"]([^'\"]*\.(?:zip|txt))['\"]", html, re.I)
         if re.match(r"^20\d{2}_", a)]))
    hits = [h for h in hits if str(year) in h]
    acts = dict.fromkeys(re.findall(r'(?:action|href)\s*=\s*["\']([^"\']*(?:down|fnltt)[^"\']*)["\']',
                                    html, re.I))
    fns = dict.fromkeys(re.findall(r'onclick\s*=\s*["\'](?:javascript:)?\s*([A-Za-z_$][\w$]*)\s*\(',
                                   html, re.I))
    diag = (f"HTML {len(html):,}자 · 후보 {len(hits)}개 · "
            f"{', '.join(marks) if marks else '단서 없음'} · "
            f"액션 {list(acts)[:3]} · 폼필드 {list(fields)[:6]} · onclick함수 {list(fns)[:4]}")
    return hits, diag


def _bulk_fetch_one(fl_nm: str) -> Optional[bytes]:
    for base in DART_BULK_DL:
        for params in ({"fl_nm": fl_nm}, {"fl_nm": fl_nm, "crtfc_key": DART_API_KEY}):
            raw = http_get(base, source="dart", params=params, as_bytes=True, tries=2,
                           referer=DART_BULK_PAGE, timeout=120)
            if raw and len(raw) > 5000 and (raw[:2] == b"PK" or b"\t" in raw[:4000]):
                return raw
    return None


_BULK_VALUE_HINTS = ["당기 1분기 3개월", "당기 반기 3개월", "당기 3분기 3개월",
                     "당기 1분기 누적", "당기 반기 누적", "당기 3분기 누적",
                     "당기", "당기말"]


def _parse_bulk_txt(raw: bytes, year: int, reprt: str) -> pd.DataFrame:
    """벌크 zip/txt → 정규화 행. 컬럼 인덱스를 믿지 않고 헤더 텍스트로 찾는다."""
    blobs: List[bytes] = []
    if raw[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            for n in zf.namelist():
                if n.lower().endswith((".txt", ".csv")):
                    blobs.append(zf.read(n))
        except Exception:
            return pd.DataFrame()
    else:
        blobs.append(raw)

    rows = []
    for b in blobs:
        txt = _decode(b, None, "bulk")
        try:
            d = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str, engine="python",
                            on_bad_lines="skip")
        except Exception:
            continue
        if d is None or not len(d):
            continue
        cols = {re.sub(r"\s+", "", str(c)): c for c in d.columns}

        def pick(*names):
            for n in names:
                k = re.sub(r"\s+", "", n)
                if k in cols:
                    return cols[k]
            for k, orig in cols.items():
                if any(re.sub(r"\s+", "", n) in k for n in names):
                    return orig
            return None

        c_code = pick("종목코드")
        c_item = pick("항목코드")
        c_name = pick("항목명")
        c_sj = pick("재무제표종류")
        c_end = pick("결산기준일")
        if not (c_code and c_name):
            continue
        # 금액 컬럼: '당기...' 중 가장 먼저 맞는 것. 누적(3개월이 아닌)을 우선한다 —
        # 우리는 아래에서 누적→분기 차분을 하므로 누적이 정본이다.
        c_val = None
        for h in _BULK_VALUE_HINTS:
            c_val = pick(h)
            if c_val is not None:
                break
        if c_val is None:
            num_like = [c for c in d.columns if str(c).startswith("당기")]
            c_val = num_like[0] if num_like else None
        if c_val is None:
            continue

        t = pd.DataFrame({
            "stock_code": d[c_code].astype(str).str.replace(r"[\[\]\s]", "", regex=True).map(to_code6),
            "account_id": (d[c_item].astype(str) if c_item else ""),
            "account_nm": d[c_name].astype(str).str.replace(r"\s+", "", regex=True),
            "sj_raw": (d[c_sj].astype(str) if c_sj else ""),
            "period_end_raw": (d[c_end].astype(str) if c_end else ""),
            "thstrm_amount": d[c_val].astype(str),
        })
        rows.append(t)

    if not rows:
        return pd.DataFrame()
    R = pd.concat(rows, ignore_index=True).dropna(subset=["stock_code"])
    R["bsns_year"] = int(year)
    R["reprt_code"] = str(reprt)
    # 재무제표종류 문자열에서 BS/IS/CIS/CF 를 판별한다 (파일마다 표기가 조금씩 다르다)
    sj = R["sj_raw"].astype(str)
    R["sj_div"] = np.select(
        [sj.str.contains("재무상태", na=False),
         sj.str.contains("포괄손익", na=False),
         sj.str.contains("손익", na=False),
         sj.str.contains("현금흐름", na=False)],
        ["BS", "CIS", "IS", "CF"], default="OTHER")
    R["fs_div"] = np.where(sj.str.contains("연결", na=False), "CFS", "OFS")
    return R


def fetch_dart_bulk(years: Sequence[int], reprts: Sequence[str]) -> pd.DataFrame:
    """§4.1 Primary. 파일을 통째로 받고 필터는 다운로드 이후에 한다. 종목별 루프 없음."""
    cached = VAULT.get_table("dart_bulk_raw", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["bsns_year"].astype(int), cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 벌크 {len(cached):,}행 재사용 ({len(done)} 분기)")
    jobs = [(int(y), str(r)) for y in years for r in reprts if (int(y), str(r)) not in done]
    if RUN_MODE == "CACHED" or not DART_API_KEY:
        jobs = []

    got: List[pd.DataFrame] = []
    ok_q, fail_q = [], []
    if jobs:
        LOG.info(f"DART 재무정보 일괄다운로드 {len(jobs)} 분기 (분기당 파일 여러 개)")
        # ★ 벌크 페이지가 로그인벽으로 막히면 48분기가 **전부** 같은 이유로 실패한다.
        #   실측에서 26,035자짜리 동일 진단이 48줄 쏟아져 콘솔이 묻혔다. 원인은 하나인데
        #   증상을 48번 출력하는 건 정보가 아니라 소음이다.
        #   → 같은 진단이 연속 3회면 나머지는 시도하지 않고 한 줄로 요약한다.
        _first_diag, _streak, _bailed = "", 0, False
        for y, r in tqdm(jobs, desc="DART 벌크", ncols=88, leave=False):
            if _bailed:
                fail_q.append((y, r))
                continue
            names, diag = _bulk_discover(y, r)
            if not names:
                # 추측 후보를 만들지 않는다(성공확률 0 · 원인만 가림). 즉시 폴백으로 내려간다.
                if not _first_diag:
                    _first_diag = diag
                    LOG.debug(f"벌크 {y}/{REPRT_NAME.get(r, r)} 목록 발견 실패 → 건너뜀 · {diag}")
                _streak = _streak + 1 if diag == _first_diag else 0
                if _streak >= 3 and not ok_q:
                    _bailed = True
                    LOG.warn(
                        f"벌크 목록 발견이 동일한 이유로 연속 실패해 나머지 "
                        f"{len(jobs) - len(fail_q) - 1}분기는 시도하지 않습니다 "
                        f"(같은 진단 반복 = 사이트 구조/로그인벽 문제이지 분기별 문제가 아님). "
                        f"진단: {_first_diag[:120]}")
                fail_q.append((y, r))
                continue
            frames = []
            for fl in names:
                raw = _bulk_fetch_one(fl)
                if not raw:
                    continue
                # 원본은 공용 인덱스에 그대로 보관 — 다른 전략이 재파싱할 수 있게(L0 불변)
                VAULT.put_blob("dart", "fnltt_bulk", fl, raw,
                               "zip" if raw[:2] == b"PK" else "txt",
                               source="opendart bulk", scope="shared",
                               event_date=f"{y}-12-31", knowledge_date=None,
                               extra={"year": y, "reprt": r})
                t = _parse_bulk_txt(raw, y, r)
                if len(t):
                    frames.append(t)
            if frames:
                got.append(pd.concat(frames, ignore_index=True))
                ok_q.append((y, r))
            else:
                fail_q.append((y, r))
        VAULT.flush("shared")

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        if jobs:
            LOG.warn("재무정보 일괄다운로드를 한 건도 받지 못했습니다 — Fallback A(fnlttMultiAcnt)"
                     "로 전환합니다. (§4.1). 벌크 경로는 공개 API 가 아니라 웹 다운로드라 "
                     "사이트 구조 변경에 취약합니다 — CANARY K1 결과를 확인하세요.")
        return pd.DataFrame(columns=["stock_code", "account_id", "account_nm", "sj_div",
                                     "fs_div", "thstrm_amount", "bsns_year", "reprt_code"])
    B = pd.concat(frames, ignore_index=True)
    B = B.drop_duplicates(["stock_code", "bsns_year", "reprt_code", "sj_div", "fs_div",
                           "account_id", "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_bulk_raw", B, scope="shared", domain="dart",
                        source="opendart 재무정보 일괄다운로드")
    LOG.ok(f"DART 벌크 {len(B):,}행 · {B['stock_code'].nunique():,}종목 "
           f"(성공 분기 {len(ok_q)} / 실패 {len(fail_q)})")
    PIPE.io("IN", "HTTP", "dart:bulk", B, source="opendart bulk", ok=len(B) > 0)
    return B


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Fallback A — fnlttMultiAcnt 배치 (100사/호출)
# ═══════════════════════════════════════════════════════════════════════════════════════════
DART_MULTI_BATCH = 100
_FS_KEEP = ["corp_code", "stock_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no", "restated"]


def fetch_dart_multi(corp_codes: Sequence[str], years: Sequence[int],
                     reprts: Sequence[str]) -> pd.DataFrame:
    """주요계정 배치. 벌크가 실패했을 때의 1차 폴백.

    ⚠ '주요계정'만 온다: 매출·영업이익·순이익·자산·부채·자본.
      재고·매출채권·영업CF·유형자산취득이 **없다** → i_dio/i_dso/i_accr/i_capex 가 죽고
      TP_I2·TP_I4·TP_I1 이 전부 무력화된다. 이 사실을 커버리지 표에 명시한다.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        # ★★ 스키마 충돌 감지 ★★ 같은 테이블명을 구 버전(v2/build 계열)도 쓰는데
        #   그쪽 _FS_KEEP 에는 stock_code 가 없다. 그 캐시가 섞여 들어오면
        #   corp_code 는 멀쩡한데 stock_code 만 통째로 비어, 하류에서 종목코드 해석이
        #   실패하고 전 행이 사라진다(실측 1,249,787 → 6). 게다가 done 이 그 조합을
        #   '완료'로 표시해 **재수집으로 스스로 치유되지도 않는다.**
        #   지우지 않는다(절대1원칙) — 사실만 알리고 하류가 corp_code 로 복원하게 한다.
        if "stock_code" not in cached.columns:
            LOG.warn("공용 캐시 dart_multi_raw 에 stock_code 컬럼이 없습니다 "
                     "(구 버전 스키마로 기록된 캐시). corp_code→종목코드 매핑으로 "
                     "복원하므로 문제 없습니다 — 캐시는 그대로 보존합니다.")
        else:
            _sc_cov = float(cached["stock_code"].notna().mean())
            if _sc_cov < 0.5:
                LOG.warn(f"공용 캐시의 stock_code 채움률이 {_sc_cov*100:.0f}% 입니다 — "
                         f"구·신 스키마가 섞인 캐시입니다. corp_code 로 복원합니다.")
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")
    # ★★ '결과가 없다'와 '물어본 적 없다'를 구분한다 ★★
    #   done 은 캐시에 **행이 있는** 조합만 담는다. 그런데 상장 전 연도나 미제출 분기는
    #   아무리 물어도 영원히 빈다. 그 조합이 매 실행 다시 대상이 되어,
    #   실측에서 994배치(≈99,400조합)를 2분간 돌리고 **행수가 1도 안 늘었다**.
    #   그리고 그건 다음 실행에도, 그 다음에도 똑같이 반복된다.
    #   → 물어본 조합을 원장에 남긴다. 소스가 늦게 채워질 수 있으므로 영구가 아니라 20일.
    ASK_FRESH_DAYS = 20
    asked: set = set()
    _ask = VAULT.get_table("dart_multi_asked", scope="shared")
    if _ask is not None and len(_ask):
        _age = (pd.Timestamp.now() - as_ts_series(_ask["asked_at"])).dt.total_seconds() / 86400.0
        _fresh = _ask[_age <= ASK_FRESH_DAYS]
        asked = set(zip(_fresh["corp_code"].astype(str),
                        _fresh["bsns_year"].astype(int),
                        _fresh["reprt_code"].astype(str)))
        if len(asked):
            LOG.info(f"최근 {ASK_FRESH_DAYS}일 내 조회한 {len(asked):,}조합은 건너뜁니다 "
                     f"(제출이 없어 빈 응답이었던 조합 — 매 실행 다시 묻지 않습니다).")
    corps = [str(c) for c in corp_codes]
    jobs, ask_rows = [], []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps
                    if (c, int(y), str(r)) not in done and (c, int(y), str(r)) not in asked]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), str(r)))
            ask_rows.extend({"corp_code": c, "bsns_year": int(y), "reprt_code": str(r)}
                            for c in todo)
    if RUN_MODE == "CACHED":
        jobs, ask_rows = [], []

    def _one(job):
        batch, y, r = job
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(batch), "bsns_year": str(y), "reprt_code": r})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        d["reprt_code"] = str(r)
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]
        # 물어본 사실을 남긴다 — 성공이든 빈 응답이든. 이게 없으면 위 폭주가 재발한다.
        if ask_rows:
            _new = pd.DataFrame(ask_rows).assign(
                asked_at=pd.Timestamp.now().isoformat(timespec="seconds"))
            _all = (pd.concat([_ask, _new], ignore_index=True)
                    if _ask is not None and len(_ask) else _new)
            _all = (_all.sort_values("asked_at")
                        .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
                        .reset_index(drop=True))
            VAULT.put_table("dart_multi_asked", _all, scope="shared", domain="dart",
                            source="fnlttMultiAcnt:asked_ledger")
            LOG.info(f"조회 원장 {len(ask_rows):,}조합 기록 — 다음 실행은 이 지점부터 "
                     f"이어받습니다(빈 응답 반복 차단).")
    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    # ★ fs_div 를 키에 넣는다. fnlttMultiAcnt 는 한 응답에 CFS(연결)와 OFS(별도)를 함께
    #   주는데, 키에서 빼면 둘이 한 행으로 뭉개지고 keep="last" 가 임의로 하나를 고른다.
    #   지주회사는 연결/별도 매출이 자릿수로 다르다 — 기업마다 무작위로 섞인 값이 된다.
    #   (뒤에서 _fs_pri 로 CFS 를 우선하는 로직이 있는데, 여기서 이미 지워지면 무의미하다)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사")
    PIPE.io("IN", "HTTP", "dart:multi", M, source="opendart fnlttMultiAcnt")
    return M


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Fallback B — fnlttSinglAcntAll (전체 재무제표, 회사×연도×보고서 단건)
# ═══════════════════════════════════════════════════════════════════════════════════════════
#  ★ 왜 이게 필요한가 (실측으로 확인된 상황):
#    벌크(K1)가 실패하면 Fallback A(fnlttMultiAcnt)만 남는데, A 는 '주요계정'만 준다 —
#    매출·영업이익·순이익·자산·부채·자본. **재고·매출채권·영업CF·유형자산취득이 없다.**
#    그러면 i_dio·i_dso·i_accr·i_capex 가 전부 결측이 되고
#    TP_I2(매출↑인데 회전 유지)·TP_I4(매출↑인데 발생액 유지)·TP_I1(확장하는데 ROIC 유지)이
#    죽는다. 즉 전략의 코어가 사라진 채로 백테스트가 '성공'한다. 그건 결과가 아니라 착시다.
#
#  ★ 비용의 현실을 숨기지 않는다:
#    연 1회(사업보고서)  : 2,600사 × 11년         ≈ 28,600 콜 → 일 19,000 한도로 약 2일
#    분기 전체           : 2,600사 × 11년 × 4분기 ≈ 114,400 콜 →              약 6일
#    그래서 기본값은 annual 이고, 이어받기가 전제다. 중단돼도 받은 만큼 드라이브에 남고
#    다음 실행이 정확히 그 지점부터 잇는다.
DART_FS_FREQ = "annual"          # "annual"(약 2일) | "quarterly"(약 6일)


DART_MIN_YEAR = 2015          # OpenDART 재무 API 는 2015년 이후만 제공한다(그 이전 호출은 순낭비)
# 사업보고서 응답에는 전기(frmtrm_amount)·전전기(bfefrmtrm_amount)가 함께 온다.
_PRIOR_COLS = (("frmtrm_amount", 1), ("bfefrmtrm_amount", 2))


def _fs_one(job) -> Optional[pd.DataFrame]:
    """(corp, year, reprt) 1건. 사업보고서면 전기·전전기 비교치도 함께 수확한다.

    ★★ PIT 주의 — 이 수확은 '콜 수를 1/3 로 줄이는' 용도가 **아니다** ★★
      전기·전전기 금액은 그 보고서가 제출된 시점에 비로소 알 수 있다. 그러므로
      knowledge_date 는 **원 보고서의 접수일이 아니라 이 보고서의 접수일**이다.
      (게다가 소급 재작성된 값일 수 있어 원 공시치와 다르다 — restated=True 로 표시한다)

      만약 "FY2025 한 번 호출해서 2023·2024 를 채우자" 라고 하면, 2024년 백테스트 시점에
      2026년에야 알 수 있는 값을 쓰게 된다. 그건 정확히 미래누수다.
      그래서 이 수확분은 ① 항상 이 보고서의 rcept_no 를 달고 ② 원 공시가 없는 (회사,연도)
      조합을 메우는 용도로만 쓴다. 연도를 건너뛰며 호출하지 않는다.

      실익은 '콜 절감'이 아니라 **YoY 계산의 정합성**이다. t 시점에 알 수 있는 당기값과
      전기값이 같은 문서에서 나오므로 회계기준 변경·재작성으로 인한 불연속이 사라진다.
    """
    corp, year, reprt = job
    if int(year) < DART_MIN_YEAR:
        return None
    # 연결(CFS) 우선, 없으면 개별(OFS). 순서를 바꾸면 지주사에서 매출이 통째로 달라진다.
    for fs_div in ("CFS", "OFS"):
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": reprt, "fs_div": fs_div})
        if not (js and isinstance(js.get("list"), list) and js["list"]):
            continue
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["corp_code"] = corp
        d["bsns_year"] = int(year)
        d["reprt_code"] = str(reprt)
        d["fs_div"] = fs_div
        d["restated"] = False
        out = [d[_FS_KEEP]]
        if str(reprt) == REPRT_CODES["FY"]:
            for src_col, back in _PRIOR_COLS:
                if src_col not in d.columns:
                    continue
                p = d.copy()
                p["thstrm_amount"] = p[src_col]
                p["bsns_year"] = int(year) - back
                p["restated"] = True
                p = p[p["thstrm_amount"].notna()]
                # rcept_no 는 **이 보고서의 것**을 그대로 유지한다 → knowledge_date 가
                # 자동으로 '이 보고서 접수일'이 되어 PIT 가 지켜진다.
                if len(p) and int(year) - back >= DART_MIN_YEAR - 2:
                    out.append(p[_FS_KEEP])
        return pd.concat(out, ignore_index=True)
    return None


def fetch_dart_full(corp_codes: Sequence[str], years: Sequence[int],
                    priority: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """전체 재무제표. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(유동성 상위)대로 먼저 받는다. 일일 한도로 중간에 끊기는 것이
    **정상 시나리오**이므로, 끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가
    되도록 정렬한다. 무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아
    백테스트를 못 돌린다.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = set()
    if nonempty(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 전체재무제표 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = ([REPRT_CODES["FY"]] if DART_FS_FREQ == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes), key=lambda c: (order.get(c, 10 ** 9), c))
    jobs = [(c, y, r) for y in sorted(years, reverse=True)      # 최근 연도 우선
            for c in corp_sorted for r in reprts
            if int(y) >= DART_MIN_YEAR and (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    got = []
    if jobs:
        avail = max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0))
        days = math.ceil(len(jobs) * 1.3 / max(DART_DAILY_LIMIT, 1))
        LOG.warn(f"전체 재무제표 신규 수집 대상 {len(jobs):,}건 (오늘 가용 호출 {avail:,}건). "
                 f"콜당 최대 2회 요청이므로 콜드빌드에 약 {days}일이 걸립니다 "
                 f"(DART_FS_FREQ='{DART_FS_FREQ}'). 오늘 받을 수 있는 만큼 받아 드라이브에 "
                 f"저장하고, 내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다. "
                 f"유동성 상위·최근 연도부터 채우므로 중간에 끊겨도 상위 종목은 먼저 완성됩니다.")
        res = pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 12), desc="DART 전체재무제표")
        got = [d for d in res if nonempty(d)]

    frames = ([cached] if nonempty(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    F = pd.concat(frames, ignore_index=True)
    # ★ 원 공시(restated=False)가 재작성 수확치(True)를 항상 이긴다. 원 공시가 knowledge_date
    #   가 더 이르고(= 그 시점에 실제로 알 수 있었고) 값도 당시 공시된 그대로이기 때문이다.
    if "restated" in F.columns:
        F["restated"] = F["restated"].fillna(True).astype(bool)
        F = F.sort_values("restated", kind="stable")
    F = F.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                           "account_nm"], keep="first")
    if got:
        VAULT.put_table("dart_fnltt_raw", F, scope="shared", domain="dart",
                        source="opendart fnlttSinglAcntAll")
    n_have = F.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(F) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"전체 재무제표 진행률 {n_have:,}/{n_need:,} ({100*n_have/max(n_need,1):.1f}%) — "
             f"재실행하면 이 지점부터 이어받습니다.")
    PIPE.io("IN", "HTTP", "dart:fnlttSinglAcntAll", F, source="opendart", ok=len(F) > 0)
    return F


def merge_financial_tiers(*tiers: pd.DataFrame) -> pd.DataFrame:
    """상위 티어를 우선하고, 없는 (회사, 기간) 조합만 하위 티어로 메운다.

    티어 순서 = 정보량 순서: 벌크/전체재무제표(전 계정) > 주요계정(6개 계정).
    콜드빌드가 며칠 걸리는 동안에도 주요계정이 전 종목을 덮고 있어 유니버스·규모버킷·
    R3 팩터가 즉시 동작하고, 전체 재무제표가 도착하는 종목부터 TP 가 살아난다.
    """
    tiers = [t for t in tiers if nonempty(t)]
    if not tiers:
        return pd.DataFrame(columns=_FS_KEEP)
    out = tiers[0]
    for t in tiers[1:]:
        keys = ("corp_code", "bsns_year", "reprt_code")
        if not all(k in out.columns for k in keys) or not all(k in t.columns for k in keys):
            out = pd.concat([out, t], ignore_index=True)
            continue
        have = set(zip(out["corp_code"].astype(str), out["bsns_year"].astype(int),
                       out["reprt_code"].astype(str)))
        key = list(zip(t["corp_code"].astype(str), t["bsns_year"].astype(int),
                       t["reprt_code"].astype(str)))
        fill = t[[k not in have for k in key]]
        if len(fill):
            LOG.info(f"하위 티어로 보완한 (회사×기간) "
                     f"{fill.groupby(list(keys)).ngroups:,}건 — 상위 티어가 도착하면 자동 대체됩니다.")
            out = pd.concat([out, fill], ignore_index=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  공시목록 — 값이 아니라 '시점'과 '이벤트'를 준다
# ═══════════════════════════════════════════════════════════════════════════════════════════
# 수집할 공시 유형. A·B 만으로는 XCB 의 c6·V2·V3 이 구조적으로 0건이 된다(위 주석 참조).
DISCLOSURE_TYPES = ("A", "B", "I")
DISCLOSURE_TYPE_NAME = {"A": "정기공시", "B": "주요사항보고", "I": "거래소공시"}

DISCLOSURE_PATTERNS = {
    "treasury_acq":   r"자기주식\s*취득(?!.*신탁\s*해지)",
    "treasury_trust": r"자기주식\s*취득\s*신탁",
    "treasury_canc":  r"자기주식\s*소각|이익소각|주식소각",
    "dividend":       r"현금.?현물배당결정|결산배당|중간배당|배당\s*결정",
    "rights_issue":   r"유상증자",
    "cb_issue":       r"전환사채",
    "bw_issue":       r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion":  r"감사보고서",
    "periodic":       r"(사업보고서|반기보고서|분기보고서)",
}


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다.

    두 가지 용도가 있고 둘 다 필수다:
      ① 정기공시(A) → (회사, 보고서종류, 연도) → **접수일자**. 벌크 재무의 knowledge_date.
      ② 주요사항(B) → 자사주 취득/소각(TP_P2), 유증·CB·BW(V3), 감사의견(V5).
    """
    empty = pd.DataFrame(columns=["corp_code", "stock_code", "rcept_no", "rcept_dt",
                                  "report_nm", "event", "event_date", "knowledge_date"])
    if not DART_API_KEY:
        return empty
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        _pm = cached["rcept_dt"].dt.to_period("M").astype(str)
        if "pblntf_ty" in cached.columns:
            have = set(zip(_pm, cached["pblntf_ty"].astype(str)))
        else:
            # 구 캐시에는 유형 표시가 없다. 예전 코드가 A·B 만 받았으므로 그렇게 간주하고,
            # I(거래소공시)는 '아직 없음'으로 둬서 자동 백필되게 한다.
            have = {(m, t) for m in set(_pm) for t in ("A", "B")}
            LOG.info("구 버전 공시 캐시(유형 미표기)를 A·B 로 간주하고 I(거래소공시)만 "
                     "보충합니다 — 기존 캐시는 그대로 재사용됩니다.")
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    # ★★ I(거래소공시)를 반드시 받아야 한다 ★★
    #   XCB 가 쓰는 네 가지 — 단일판매·공급계약(c6/TP_XC), 관리종목 지정/해제(V2),
    #   매매거래정지(V3) — 는 전부 **거래소 수시공시**다. 예전엔 A·B 만 받아서
    #   이 네 개가 구조적으로 0건이었다(실측: "단일판매·공급계약 공시를 찾지 못했습니다",
    #   공시 유형별 집계에 supply_contract 가 아예 없음). 거부권 V2·V3 도 발동 불가였다.
    todo = [(m, t) for m in months for t in DISCLOSURE_TYPES if (str(m), t) not in have]
    if RUN_MODE == "CACHED":
        todo = []
    if todo:
        _by_ty = Counter(t for _, t in todo)
        LOG.info(f"공시목록 수집 대상 {len(todo):,}건 "
                 f"({' · '.join(f'{DISCLOSURE_TYPE_NAME.get(t, t)}={n:,}개월' for t, n in sorted(_by_ty.items()))})")

    def _one(job):
        m, ty = job
        rows = []
        page = 1
        while page <= 100:
            js = dart_api("list.json", {
                "bgn_de": m.start_time.strftime("%Y%m%d"),
                "end_de": m.end_time.strftime("%Y%m%d"),
                "pblntf_ty": ty, "page_no": page, "page_count": 100,
                "last_reprt_at": "N"})           # ★ 'N' — 정정 전 원본까지 전부 받는다
            if not js or not isinstance(js.get("list"), list) or not js["list"]:
                break
            for r in js["list"]:
                r["pblntf_ty"] = ty
            rows.extend(js["list"])
            if page >= int(js.get("total_page", 1) or 1):
                break
            page += 1
        return rows

    new = []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if r:
                new.extend(r)

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "flr_nm", "corp_cls", "pblntf_ty") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return empty
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    if "stock_code" in D.columns:
        D["stock_code"] = D["stock_code"].map(to_code6)
    D["event"] = ""
    # 전략층이 추가 유형을 정의했으면 함께 태깅한다(없으면 그대로). 이렇게 해야
    # 아래 집계 로그에 supply_contract 같은 XCB 전용 유형이 실제로 드러난다.
    _pats = dict(DISCLOSURE_PATTERNS)
    _pats.update(globals().get("XCB_DISCLOSURE_PATTERNS", {}) or {})
    for ev, pat in _pats.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        out = D.copy()
        out["rcept_dt"] = out["rcept_dt"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("dart_disclosures", out, scope="shared", domain="dart",
                        source="opendart list.json")
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")       # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={int((D['event'] == k).sum()):,}"
                     for k in _pats if (D["event"] == k).any()))
    # ★ 거래소공시(I)를 받았는지 눈으로 확인 가능하게 남긴다 — c6·V2·V3 의 생사가 여기 달렸다.
    if "pblntf_ty" in D.columns:
        _tyc = D["pblntf_ty"].astype(str).value_counts().to_dict()
        LOG.info("  공시 유형별: " + " · ".join(
            f"{DISCLOSURE_TYPE_NAME.get(k, k)} {v:,}건" for k, v in sorted(_tyc.items())))
        if not _tyc.get("I"):
            LOG.warn("거래소공시(I)가 0건입니다 — 단일판매·공급계약(c6/TP_XC)과 "
                     "관리종목·매매거래정지 거부권(V2·V3)이 전부 비활성화됩니다.")
    PIPE.io("IN", "HTTP", "dart:list", D, source="opendart list.json")
    return D


_PERIODIC_RE = re.compile(r"(사업보고서|반기보고서|분기보고서)")
_PERIOD_IN_TITLE = re.compile(r"\((\d{4})\.(\d{2})\)")


def build_knowledge_map(dis: pd.DataFrame) -> pd.DataFrame:
    """공시목록 → (stock_code, bsns_year, reprt_code) → 접수일자.

    ★ 벌크 재무에 없는 유일한 것이 시점이다. 이 표가 없으면 C1 을 만족할 수 없다.
    ★ 정정공시가 있으면 접수일자가 여러 개다. **가장 이른 접수일자**를 쓴다 —
      정정본의 접수일을 쓰면 원본을 알 수 있었던 시점보다 늦춰 잡아 보수적이지만,
      우리가 결합하는 값은 원본 값이므로 원본 시점이 맞다.
      (반대로 정정본 값을 원본 접수일에 붙이면 그게 곧 미래누수다 — 그건 하지 않는다)
    """
    cols = ["stock_code", "bsns_year", "reprt_code", "knowledge_date"]
    if dis is None or dis.empty:
        return pd.DataFrame(columns=cols)
    d = dis[dis["report_nm"].str.contains(_PERIODIC_RE, na=False)].copy()
    if d.empty or "stock_code" not in d.columns:
        return pd.DataFrame(columns=cols)
    d = d.dropna(subset=["stock_code"])

    nm = d["report_nm"].astype(str)
    # 제목 예: "분기보고서 (2016.03)" / "사업보고서 (2015.12)" / "반기보고서 (2016.06)"
    per = nm.str.extract(_PERIOD_IN_TITLE)
    d["p_year"] = pd.to_numeric(per[0], errors="coerce")
    d["p_month"] = pd.to_numeric(per[1], errors="coerce")

    d["reprt_code"] = np.select(
        [nm.str.contains("사업보고서", na=False),
         nm.str.contains("반기보고서", na=False),
         nm.str.contains("분기보고서", na=False) & d["p_month"].eq(3),
         nm.str.contains("분기보고서", na=False) & d["p_month"].eq(9)],
        [REPRT_CODES["FY"], REPRT_CODES["H1"], REPRT_CODES["Q1"], REPRT_CODES["Q3"]],
        default="")
    # 제목에 기간이 없는 분기보고서는 접수월로 추정한다(1~5월 접수 → Q1, 그 외 → Q3).
    miss = (d["reprt_code"] == "") & nm.str.contains("분기보고서", na=False)
    if miss.any():
        mo = d.loc[miss, "rcept_dt"].dt.month
        d.loc[miss, "reprt_code"] = np.where(mo <= 8, REPRT_CODES["Q1"], REPRT_CODES["Q3"])
        d.loc[miss, "p_year"] = d.loc[miss, "rcept_dt"].dt.year - np.where(mo <= 2, 1, 0)
    d = d[d["reprt_code"] != ""]
    if d.empty:
        return pd.DataFrame(columns=cols)

    # 사업연도: 제목의 연도가 있으면 그것, 없으면 접수일 기준 추정
    yr = d["p_year"]
    fallback_yr = d["rcept_dt"].dt.year - np.where(d["rcept_dt"].dt.month <= 4, 1, 0)
    d["bsns_year"] = pd.to_numeric(yr.fillna(pd.Series(fallback_yr, index=d.index)),
                                   errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    d["bsns_year"] = d["bsns_year"].astype(int)

    K = (d.groupby(["stock_code", "bsns_year", "reprt_code"], as_index=False)["rcept_dt"]
          .min().rename(columns={"rcept_dt": "knowledge_date"}))
    LOG.ok(f"접수일자 원장 {len(K):,}건 ({K['stock_code'].nunique():,}종목) — "
           f"벌크 재무의 knowledge_date 를 여기서 확정합니다 (다중소스 원장연결).")
    PIPE.io("OUT", "MEM", "dart_knowledge_map", K, source="dart list.json → 접수일자")
    return K


def _deadline_knowledge(year: int, reprt: str) -> pd.Timestamp:
    mm, dd = REPRT_PERIOD_END.get(reprt, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt, 90))


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  계정 매핑 — account_id(IFRS 표준코드) 우선, 실패 시 account_nm
# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1: "매핑 테이블은 config/account_map.yaml 로 분리하고 커버리지를 로깅한다(K3)."
#  단일 파일 배포이므로 dict 로 인라인하되, 구조는 동일하게 (sj, [id정규식], [명칭정규식]) 로 분리한다.
ACCOUNT_MAP: Dict[str, Tuple[str, List[str], List[str]]] = {
    # 항목:            (재무제표, [account_id 정규식],                      [account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"_Revenue$"],
                            [r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$", r"^매출$"]),
    "cogs":          ("IS", [r"CostOfSales"], [r"^매출원가$", r"^영업비용$"]),
    "gross_profit":  ("IS", [r"GrossProfit"], [r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense"], [r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense"], [r"경상(연구)?개발비", r"^연구개발비"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"_ProfitLossFromOperatingActivities"],
                            [r"^영업이익"]),
    "net_income":    ("IS", [r"ifrs-full_ProfitLoss$"], [r"^당기순이익", r"^분기순이익", r"^반기순이익"]),
    "inventory":     ("BS", [r"Inventories"], [r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"CurrentTradeReceivables"],
                            [r"^매출채권", r"^매출채권및기타"]),
    "assets":        ("BS", [r"ifrs-full_Assets$"], [r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$"], [r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$"], [r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment$"], [r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssets"], [r"^무형자산$"]),
    "cur_assets":    ("BS", [r"ifrs-full_CurrentAssets$"], [r"^유동자산$"]),
    "cur_liab":      ("BS", [r"ifrs-full_CurrentLiabilities$"], [r"^유동부채$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents"], [r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities"], [r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities"], [r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment"], [r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense"], [r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid"], [r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares"], [r"자기주식의?\s*취득"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense"], [r"법인세비용"]),
    # 주요계정 명칭은 '법인세차감전 순이익', 전체재무제표는 '법인세비용차감전순이익' —
    # '비용'을 필수로 두면 주요계정 경로에서 구조적으로 매칭이 0건이 된다.
    "pretax_income": ("IS", [r"ProfitLossBeforeTax"], [r"법인세(비용)?차감전"]),
}
_SJ_ACCEPT = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# 손익·현금흐름 성격의 전 계정 — 누적공시라 분기 차분이 필요하다.
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy",
              "tax_expense", "pretax_income"]
# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼. 수집이 얼마나 실패하든 스키마는 항상 같아야
# 한다 — 그래야 "어떤 실행엔 있고 어떤 실행엔 없는" 축이 사라지고 결측이 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_MAP)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q", "period_end"])

ACCOUNT_COVERAGE: Dict[str, float] = {}


def _num(s) -> pd.Series:
    return pd.to_numeric(
        pd.Series(s).astype(str)
          .str.replace(",", "", regex=False)
          .str.replace("−", "-", regex=False)
          .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
          .str.replace(r"[^\d.\-]", "", regex=True)
          .replace({"": np.nan, "-": np.nan, ".": np.nan}),
        errors="coerce")


def tidy_financials(raw: pd.DataFrame, kmap: pd.DataFrame,
                    code_of_corp: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """원시 계정 → (code, period_end, 항목) 와이드. knowledge_date 를 여기서 확정한다."""
    base_cols = ["code", "period_end", "knowledge_date", "bsns_year", "reprt_code"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)
    d = raw.copy()

    # 종목코드 통일 — 벌크는 stock_code, API 는 corp_code 로 온다
    if "stock_code" in d.columns:
        d["code"] = d["stock_code"].map(to_code6)
    else:
        d["code"] = None
    if d["code"].isna().any() and code_of_corp and "corp_code" in d.columns:
        need = d["code"].isna()
        d.loc[need, "code"] = d.loc[need, "corp_code"].astype(str).map(code_of_corp)
    # ★ 조용한 전멸을 막는다. 여기서 행이 사라지면 B·C축이 통째로 죽는데,
    #   예전엔 아무 말 없이 dropna 만 하고 지나가 '재무 정제 6행'이 정상처럼 보였다.
    _n0 = len(d)
    d = d.dropna(subset=["code"])
    if _n0 and len(d) < 0.5 * _n0:
        _has_sc = "stock_code" in d.columns or "stock_code" in base_cols
        LOG.error(
            f"종목코드 해석 실패로 {_n0 - len(d):,}/{_n0:,}행이 사라졌습니다 "
            f"({len(d)/max(_n0,1)*100:.1f}%만 생존).\n"
            f"    원인 1: 캐시가 stock_code 없이 저장된 판(구 버전 스키마) — "
            f"{'컬럼 있음' if _has_sc else '**컬럼 자체가 없음**'}\n"
            f"    원인 2: tidy_financials(raw, kmap, **code_of_corp**) 세 번째 인자 미전달 — "
            f"{'전달됨' if code_of_corp else '**미전달**'}\n"
            f"    둘 중 하나면 corp_code→종목코드 복원이 불가능해 전 행이 버려집니다.")
    if d.empty:
        LOG.error("재무 원본에서 종목코드를 하나도 해석하지 못했습니다 — B·C축 전멸입니다.")
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)

    d["amount"] = _num(d["thstrm_amount"])
    d = d.dropna(subset=["amount"])
    # ★ astype(str) 이 먼저면 None/NaN 이 "None"/"nan" 문자열이 되어 fillna 가 무의미하다.
    #   그러면 '표준코드 없음'과 '진짜 코드'를 구분할 수 없다. 결측을 먼저 지운다.
    d["account_id"] = d["account_id"].fillna("").astype(str).replace(
        {"None": "", "nan": "", "<NA>": ""})
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    d["sj_div"] = d["sj_div"].astype(str)
    # 연결(CFS) 우선. 개별만 있는 회사는 개별을 쓴다.
    d["_fs_pri"] = np.where(d.get("fs_div", pd.Series("", index=d.index)).astype(str) == "CFS", 0, 1)

    out_rows = []
    cov = {}
    for key, (sj, id_pats, nm_pats) in ACCOUNT_MAP.items():
        sub = d[d["sj_div"].isin(_SJ_ACCEPT.get(sj, (sj,)))]
        if sub.empty:
            cov[key] = 0.0
            continue
        # ★ account_id(IFRS 표준코드) 우선. 표준코드가 붙은 행이 있으면 명칭 매칭은 보지 않는다.
        #   명칭은 회사마다 제각각이라 '영업수익'을 매출로 잡는 등 오매칭이 잦다.
        rx_id = re.compile("|".join(id_pats), re.I) if id_pats else None
        rx_nm = re.compile("|".join(nm_pats), re.I) if nm_pats else None
        hit_id = sub[sub["account_id"].str.contains(rx_id, na=False)] if rx_id is not None \
            else sub.iloc[0:0]
        hit_nm = sub[sub["account_nm"].str.contains(rx_nm, na=False)] if rx_nm is not None \
            else sub.iloc[0:0]
        hit_id = hit_id.assign(_pri=0)
        hit_nm = hit_nm.assign(_pri=1)
        hit = pd.concat([hit_id, hit_nm], ignore_index=True)
        if hit.empty:
            cov[key] = 0.0
            continue
        # (회사, 기간) 당 1행: 표준코드 > 명칭, 연결 > 개별, 그다음 절대값 큰 쪽(대표 계정)
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values(["_pri", "_fs_pri", "_a"], ascending=[True, True, False])
                  .drop_duplicates(["code", "bsns_year", "reprt_code"], keep="first"))
        cov[key] = float(hit["code"].nunique())
        cols = ["code", "bsns_year", "reprt_code", "amount"]
        if "rcept_no" in hit.columns:
            cols.append("rcept_no")
        out_rows.append(hit.assign(item=key)[cols + ["item"]])

    if not out_rows:
        LOG.error("계정 매핑이 한 건도 성립하지 않았습니다. ACCOUNT_MAP 정규식과 소스 스키마를 "
                  "확인하세요. (재무 기반 센서가 전부 결측이 됩니다)")
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)

    L = pd.concat(out_rows, ignore_index=True)
    # ★★ 커버리지 분모를 '살아남은 종목'으로 잡으면 안 된다 ★★
    #   3,107사 중 5사만 남았을 때 5/5 = 100% 가 되어, 재무 전멸을 감시하라고 만든
    #   경보가 오히려 '완전 정상'을 보고했다. 분모는 **요청한 유니버스**여야 한다.
    n_survived = max(L["code"].nunique(), 1)
    n_universe = max(len(code_of_corp) if code_of_corp else 0, n_survived)
    ACCOUNT_COVERAGE.clear()
    ACCOUNT_COVERAGE.update({k: v / n_universe for k, v in cov.items()})
    if n_survived < 0.5 * n_universe:
        LOG.error(f"재무를 확보한 종목이 {n_survived:,}개로 요청 유니버스 {n_universe:,}개의 "
                  f"{n_survived/n_universe*100:.1f}% 에 불과합니다 — 계정 커버리지 표는 "
                  f"**유니버스 기준**으로 계산했으니 그 낮은 값을 그대로 보세요.")

    W = L.pivot_table(index=["code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    if "rcept_no" in L.columns:
        rc = (L.dropna(subset=["rcept_no"]).sort_values("rcept_no")
               .groupby(["code", "bsns_year", "reprt_code"])["rcept_no"].first().reset_index())
        W = W.merge(rc, on=["code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12, 31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12, 31))[1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]

    # ── knowledge_date 확정 (C1 의 급소) ─────────────────────────────────────────────────
    W["bsns_year"] = W["bsns_year"].astype(int)
    W["reprt_code"] = W["reprt_code"].astype(str)
    W["knowledge_date"] = pd.NaT
    n_map = n_rcept = n_deadline = 0
    if kmap is not None and len(kmap):
        k = kmap.copy()
        k["bsns_year"] = k["bsns_year"].astype(int)
        k["reprt_code"] = k["reprt_code"].astype(str)
        k = k.rename(columns={"stock_code": "code", "knowledge_date": "_kd_map"})
        W = W.merge(k[["code", "bsns_year", "reprt_code", "_kd_map"]],
                    on=["code", "bsns_year", "reprt_code"], how="left")
        W["knowledge_date"] = as_ts_series(W["_kd_map"])
        n_map = int(W["knowledge_date"].notna().sum())
        W = W.drop(columns=["_kd_map"])
    if "rcept_no" in W.columns:
        need = W["knowledge_date"].isna()
        if need.any():
            s = W.loc[need, "rcept_no"].astype(str).str.replace(r"\D", "", regex=True)
            kd = as_ts_series(s.str.slice(0, 8))
            W.loc[need, "knowledge_date"] = kd.where(kd.dt.year.between(2000, 2100))
            n_rcept = int(W["knowledge_date"].notna().sum()) - n_map
    need = W["knowledge_date"].isna()
    if need.any():
        W.loc[need, "knowledge_date"] = [
            _deadline_knowledge(int(y), str(r))
            for y, r in zip(W.loc[need, "bsns_year"], W.loc[need, "reprt_code"])]
        n_deadline = int(need.sum())
    LOG.table([["① 공시목록 접수일자 (정확)", f"{n_map:,}", "✔ C1 정확"],
               ["② rcept_no 앞 8자리", f"{n_rcept:,}", "✔ C1 정확"],
               ["③ 법정 제출기한 추정", f"{n_deadline:,}",
                "⚠ 보수적(늦게 앎) — 누수는 없으나 신호가 늦어짐"]],
              ["knowledge_date 출처", "행수", "판정"], ["l", "r", "l"],
              title="재무 PIT 시점 확정 — 벌크 파일에는 접수일자가 없어 공시목록과 결합합니다")
    if n_deadline > 0.5 * len(W):
        LOG.warn(f"재무 {100*n_deadline/max(len(W),1):.0f}% 가 법정기한 추정입니다. "
                 f"공시목록 수집이 부족하다는 뜻입니다 — 신호가 실제보다 최대 45일 늦게 반영되어 "
                 f"성과가 보수적으로(낮게) 나옵니다. 미래누수 방향은 아닙니다.")

    # ── 누적 → 분기 단독 ─────────────────────────────────────────────────────────────────
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.dropna(subset=["q"]).sort_values(["code", "bsns_year", "q"]).reset_index(drop=True)
    gk = ["code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in FLOW_ITEMS:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        # ★ 누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다. fail-open 금지.
        W[c + "_q"] = np.where(W["q"] == 1, W[c], np.where(contiguous, W[c] - prev, np.nan))
        # TTM = 4분기 이동합. min_periods=4 — 3개로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])

    for k in ACCOUNT_MAP:
        if k not in W.columns:
            W[k] = np.nan

    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' (분기 프레임에서 센다) ───────────────────
    #   ★ 월 패널에서 rolling(9) 로 세면 같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도
    #     정답이 아니다. 발동이 1~2개월 늦고 결산→1Q→반기 창은 아예 놓친다.
    #     분기 프레임은 관측당 정확히 한 행이고 이미 (code, year, q) 로 정렬돼 있다.
    #   ★★ fail-open 금지 ★★ cfo 는 fnlttMultiAcnt(주요계정)에 **없다**. 그러면
    #     NaN 비교가 전부 False → astype(float) → 0.0 → rolling.min()=0.0 이 되어
    #     "이익-현금 괴리 없음(깨끗함)"으로 읽힌다. 데이터가 없어서 깨끗한 것을
    #     깨끗하다고 판정하면 그게 곧 거부권 무력화다. 없으면 결측으로 둔다.
    _ni, _cfo = col(W, "net_income_ttm"), col(W, "cfo_ttm")
    _bad = ((_ni > 0) & (_cfo < 0.5 * _ni)).astype(float)
    _bad = _bad.where(_ni.notna() & _cfo.notna())        # 둘 중 하나라도 없으면 판정 불가
    W["v2_bad_3q"] = (_bad.groupby(W["code"], observed=True)
                          .transform(lambda s: s.rolling(3, min_periods=3).min()))
    if _cfo.notna().sum() == 0:
        LOG.warn("영업현금흐름(cfo)이 전무해 V2(이익-현금 괴리) 거부권을 **판정 불가**로 "
                 "둡니다 — 0(깨끗함)으로 채우지 않습니다. 이 계정은 주요계정 API 에 없으며 "
                 "fnlttSinglAcntAll(Fallback B)가 있어야 살아납니다.")

    miss = [k for k in ACCOUNT_MAP if W[k].notna().sum() == 0]
    if miss:
        LOG.warn(f"한 건도 매칭되지 않은 계정 {len(miss)}개: {miss[:10]} — "
                 f"이 계정을 쓰는 센서는 전부 결측이 됩니다(0으로 채우지 않음).")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"재무 정제 {len(W):,}행 · {W['code'].nunique():,}종목 "
           f"(누적→분기 차분 · TTM min_periods=4 완료)")
    PIPE.io("OUT", "MEM", "financials_tidy", W)
    return downcast(W)


def report_account_coverage(min_cov: float = 0.85):
    """CANARY K3 의 본선 판. 필수 계정 커버리지가 기준 미만이면 어떤 TP 가 죽는지 명시한다."""
    if not ACCOUNT_COVERAGE:
        return set()
    need = {"revenue": ["TP_I2", "TP_I4", "V1"], "cogs": ["TP_I2(i_dio)"],
            "inventory": ["TP_I2(i_dio)", "V1"], "receivable": ["TP_I2(i_dso)", "V1"],
            "cfo": ["TP_I4(i_accr)", "TP_P1", "V2"], "capex": ["TP_I1", "TP_P1"],
            "net_income": ["TP_I4", "V2"], "assets": ["TP_I4"],
            "equity": ["V5"], "ppe": ["TP_I1(i_ic)"], "op_income": ["TP_I3(i_vapp)"]}
    rows, weak = [], set()
    for k, tps in need.items():
        c = ACCOUNT_COVERAGE.get(k, 0.0)
        ok = c >= min_cov
        if not ok:
            weak.update(tps)
        rows.append([k, f"{100*c:.1f}%", "✔" if ok else f"❗ {min_cov:.0%} 미만",
                     ", ".join(tps)])
    LOG.table(sorted(rows, key=lambda r: float(r[1].rstrip("%"))),
              ["계정", "커버리지", "판정", "영향받는 지표"], ["l", "r", "l", "l"],
              title=f"필수 계정 커버리지 (CANARY K3 · 기준 {min_cov:.0%})")
    if weak:
        LOG.warn(f"커버리지 미달로 신뢰도가 낮은 지표: {sorted(weak)}. "
                 f"§1 K3 는 '85% 미만 계정을 쓰는 TP 를 비활성화' 하라고 요구합니다 — "
                 f"비활성화 여부는 아래 CANARY 판정표를 따릅니다.")
    return weak


# ── 직원현황 (M2 · TP_I3) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int],
                         code_of_corp: Dict[str, str]) -> pd.DataFrame:
    cols = ["code", "bsns_year", "employees", "payroll", "event_date", "knowledge_date"]
    if not DART_API_KEY:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(str(c), int(y)) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 서로소이므로 합산이
        #   맞지만, 일부 기업은 '합계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이라 아예 쓰지 않는다.
        for c in ("fo_bbm", "sexdstn"):
            if c in d.columns:
                d = d[~d[c].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        emp = float(_num(d["sm"]).sum(skipna=True)) if "sm" in d.columns else np.nan
        pay = float(_num(d["fyer_salary_totamt"]).sum(skipna=True)) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year),
                "employees": emp if emp > 0 else np.nan,
                "payroll": pay if pay > 0 else np.nan, "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart",
                        source="opendart empSttus")
    # ★ E.get("rcept_no","") 는 컬럼이 없으면 '문자열'을 돌려주고 zip 이 그걸 글자 단위로 훑어
    #   knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["code"] = E["corp_code"].astype(str).map(code_of_corp)
    E = E.dropna(subset=["code"])
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    s = E["rcept_no"].astype(str).str.replace(r"\D", "", regex=True)
    kd = as_ts_series(s.str.slice(0, 8))
    E["knowledge_date"] = kd.where(kd.dt.year.between(2000, 2100))
    need = E["knowledge_date"].isna()
    if need.any():
        E.loc[need, "knowledge_date"] = [_deadline_knowledge(int(y), REPRT_CODES["FY"])
                                         for y in E.loc[need, "bsns_year"]]
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"직원현황 {len(E):,}행 · {E['code'].nunique():,}종목")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E
