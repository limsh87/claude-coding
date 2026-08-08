

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  analyst_forecasts 조립 — 명세 §2.1 의 표준 스키마를 실제 데이터로 채운다             ║
# ║                                                                                          ║
# ║  두 개의 메트릭 트랙을 만든다. 절대 섞지 않는다(§45.2 와 같은 이유).                         ║
# ║                                                                                          ║
# ║   ① EPS — 명세의 원형. 리포트 PDF 1면 '실적 추정표'에서 기하학적으로 추출한다.               ║
# ║          실측치 A = DART 주당이익 (없으면 지배주주순이익/주식수).                            ║
# ║   ② TP  — 목표주가. 한경 리스트 컬럼에 직접 있어 커버리지가 압도적이다.                      ║
# ║          실측치 A = 수정주가 기준 12개월 후 실제 주가.                                      ║
# ║                                                                                          ║
# ║  ★★ 이 파일에서 가장 중요한 경고 ★★                                                       ║
# ║   EPS 추출 실패는 무작위가 아니라 **증권사 템플릿별**로 발생한다. 즉 파서가 못 읽는 템플릿을  ║
# ║   쓰는 증권사의 애널리스트는 n^acc 이 작아 전원 0 으로 수축되고, 결과적으로 '실력'이 아니라  ║
# ║   'PDF 양식'으로 가중치가 갈린다. 이것은 조용한 선택편향이다.                                ║
# ║   → 그래서 증권사×연도 추출률 표를 반드시 출력하고, 추출률이 바닥인 증권사를 명시한다.       ║
# ║   → 그래서 TP 트랙을 같이 산출해 EPS 트랙 결론을 교차검증한다.                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EPS_PARSER_VERSION = "1.1"          # 올리면 이전 실패건을 자동으로 재파싱한다
EPS_TABLE = "analyst_eps_forecasts"          # 공용 인덱스 (다른 전략도 그대로 재사용)
EPS_STATUS_TABLE = "analyst_eps_extract_status"
FORECAST_ATTRIBUTION = "lead"       # "lead" = 대표저자 1인 | "all" = 공저자 전원

#  한 리포트 = 한 하우스뷰. 공저자 3명에게 같은 숫자로 3표를 주면 그 증권사가
#  equal-weight 컨센서스를 3배로 밀게 된다. 기본값이 "lead" 인 이유다.

# ── 숫자 파싱 ───────────────────────────────────────────────────────────────────────────────
#  △ 는 한국 재무자료에서 마이너스다. ▲/▼ 는 증감방향 표기라 부호로 쓰지 않는다.
_NEG_MARKS = ("△", "▵", "-", "−", "–", "—", "▲-")
_EPS_PLACEHOLDER = {
    "적전": "L2L", "적지": "L2L", "적자지속": "L2L", "적자전환": "L2L",
    "흑전": "L2P", "흑지": "L2P", "흑자전환": "L2P", "흑자지속": "L2P",
    "n/a": "NA", "na": "NA", "nm": "NA", "n.a.": "NA", "-": "NA", "—": "NA",
    "–": "NA", "": "NA", "적": "NA", "흑": "NA",
}
_NUM_RE = re.compile(r"^[\(\[]?\s*([△▵▲▼\-−–—+]?)\s*([0-9][0-9,\.]*)\s*[\)\]]?$")


def _eps_num(tok: str) -> Tuple[Optional[float], str]:
    """숫자 셀 → (값, 분류). 적전/흑전/n.a. 는 **0 이 아니라 결측**이다.

    ★ 이 구분이 중요한 이유: '적전'을 0.0 으로 읽으면 그 종목의 컨센서스 평균이
      실제보다 위로 끌려 올라가고, 그 오차가 그대로 Smart Gap 의 분자가 된다.
      (코드베이스가 이미 겪은 적정가격 "0" → int("0") 사고와 같은 부류다)
    """
    s = str(tok).strip().replace(" ", "")
    if not s:
        return None, "NA"
    low = s.lower()
    if low in _EPS_PLACEHOLDER:
        return None, _EPS_PLACEHOLDER[low]
    neg = s.startswith(("(", "[")) and s.endswith((")", "]"))
    m = _NUM_RE.match(s)
    if not m:
        return None, "NA"
    sign, body = m.group(1), m.group(2).replace(",", "")
    if body.count(".") > 1:
        return None, "NA"
    try:
        v = float(body)
    except ValueError:
        return None, "NA"
    if sign in ("△", "▵", "-", "−", "–", "—") or neg:
        v = -v
    return v, "NUM"


# ── 연도 헤더 ───────────────────────────────────────────────────────────────────────────────
_YEAR_RE = re.compile(
    r"^\(?(?:FY|fy)?((?:19|20)\d{2}|\d{2})\)?(?:년|년도|년말)?"
    r"(?:\(([AEFPaefp])\)|([AEFPaefp])|(예상|추정|실적|확정|E|F|P))?$")
_SUFFIX_ROW_OK = {"e", "f", "p", "a", "(e)", "(f)", "(p)", "(a)",
                  "십억원", "억원", "백만원", "원", "%", "배", "천원"}
_FYEAR_MONTH_RE = re.compile(r"(\d{1,2})\s*월")

#  EPS 행 라벨: 완전일치로 앵커한다. re.search 로 하면 'EPS 증가율' 이 걸린다.
_EPS_OK_RE = re.compile(
    r"^(?:\(?(?:수정|조정|Adj\.?|adj\.?)\)?)?\s*"
    r"(?:지배주주|지배지분|보통주|희석|기본|연결|별도)?\s*"
    r"(?:EPS|eps|주당순이익|주당이익|주당순손익)\s*"
    r"(?:\(원\)|\(₩\)|\(krw\)|\(원\,?\s*\)|원)?\s*$")
_EPS_BAD_RE = re.compile(
    r"증가율|성장률|증감|감소|YoY|yoy|CAGR|cagr|배수|배\)|%|BPS|bps|DPS|dps|"
    r"SPS|CPS|EBITDA|PER|per|P/E|PBR|주가|목표|배당|수익률|비율", re.I)


def _eps_rows_from_words(words: Sequence[Sequence], ytol: float = 2.2) -> List[List[Tuple]]:
    """단어 8-튜플을 y 밴드로 묶어 '행'을 만든다.

    ★ find_tables() 는 쓰지 않는다. 한국 증권사 요약표는 세로 괘선이 없거나
      아예 괘선이 없어 표 인식기가 0개를 반환한다(검증됨). 좌표로 직접 재구성한다.
    """
    ws = sorted(words, key=lambda w: (round(float(w[1]), 1), float(w[0])))
    rows: List[List[Tuple]] = []
    cur: List[Tuple] = []
    cy = None
    for w in ws:
        ym = (float(w[1]) + float(w[3])) / 2.0
        if cy is None:
            cur, cy = [w], ym
        elif abs(ym - cy) <= ytol:
            cur.append(w)
            cy = (cy * (len(cur) - 1) + ym) / len(cur)
        else:
            rows.append(sorted(cur, key=lambda t: float(t[0])))
            cur, cy = [w], ym
    if cur:
        rows.append(sorted(cur, key=lambda t: float(t[0])))
    return rows


def _eps_cells(row: Sequence[Tuple], gap: float = 3.0) -> List[Tuple[float, float, str]]:
    """행의 단어들을 x 간격으로 셀로 병합. 반환 (x0, x1, text).

    ★ 숫자끼리는 절대 병합하지 않는다. 우측정렬된 두 숫자의 박스가 겹치는 경우가 있어
      그대로 두면 "1,234" + "5,678" → "1,2345,678" 이 된다(재현 확인된 사고).
    """
    out: List[List[Any]] = []
    for w in row:
        x0, x1, t = float(w[0]), float(w[2]), str(w[4])
        if out:
            p = out[-1]
            both_num = _eps_num(p[2])[1] == "NUM" and _eps_num(t)[1] == "NUM"
            if (x0 - p[1]) < gap and not both_num:
                p[1] = max(p[1], x1)
                p[2] = p[2] + t
                continue
        out.append([x0, x1, t])
    return [(c[0], c[1], c[2].strip()) for c in out]


def _eps_parse_header(cells: List[Tuple[float, float, str]]
                      ) -> Optional[List[Dict[str, Any]]]:
    """연도 헤더 행이면 [{year, suffix, xc}, ...] 를 돌려준다.

    ★ 연도 토큰 3개 이상 + 순증가 + 중복없음 을 요구한다. 2개로 낮추면
      '2024F 기존 / 2024F 수정 / 변동률' 같은 추정치 변경표가 헤더로 오인된다.
    """
    ys = []
    for x0, x1, t in cells:
        m = _YEAR_RE.match(t.replace(" ", ""))
        if not m:
            continue
        y = int(m.group(1))
        if y < 100:
            y += 2000
        if not (1990 <= y <= 2100):
            continue
        suf = (m.group(2) or m.group(3) or m.group(4) or "").upper()
        ys.append({"year": y, "suffix": suf, "xc": (x0 + x1) / 2.0})
    if len(ys) < 3:
        return None
    yrs = [d["year"] for d in ys]
    if len(set(yrs)) != len(yrs) or any(b <= a for a, b in zip(yrs, yrs[1:])):
        return None
    return ys


def _eps_merge_suffix_row(hdr: List[Dict[str, Any]],
                          cells: List[Tuple[float, float, str]]) -> bool:
    """헤더 바로 아래가 'E F F' 나 '(십억원)' 같은 보조행이면 헤더에 흡수한다."""
    toks = [c[2].strip().lower() for c in cells if c[2].strip()]
    if not toks or not all(t in _SUFFIX_ROW_OK for t in toks):
        return False
    for x0, x1, t in cells:
        tt = t.strip().upper().strip("()")
        if tt not in ("E", "F", "P", "A"):
            continue
        xc = (x0 + x1) / 2.0
        near = min(hdr, key=lambda d: abs(d["xc"] - xc))
        if not near["suffix"]:
            near["suffix"] = tt
    return True


def _eps_map_to_years(hdr: List[Dict[str, Any]],
                      cells: List[Tuple[float, float, str]]) -> Dict[int, Tuple[float, str]]:
    """값 셀을 x 중심 근접도로 연도 컬럼에 붙인다.

    ★ 위치 zip 을 절대 쓰지 않는다. 값이 하나 비면(적전이 빈 셀로 렌더되는 등)
      그 뒤 모든 값이 한 칸씩 밀려 전 연도의 EPS 가 통째로 어긋난다 — 예외도 안 난다.
      매칭 실패는 '빈 값'으로 두지, 이웃으로 당겨오지 않는다.
    """
    if len(hdr) < 2:
        return {}
    xs = sorted(d["xc"] for d in hdr)
    pitch = float(np.median(np.diff(xs))) if len(xs) > 1 else 40.0
    tol = max(8.0, pitch * 0.6)
    out: Dict[int, Tuple[float, str]] = {}
    for x0, x1, t in cells:
        v, klass = _eps_num(t)
        if klass == "NA" and v is None and t.strip().lower() not in _EPS_PLACEHOLDER:
            continue
        xc = (x0 + x1) / 2.0
        near = min(hdr, key=lambda d: abs(d["xc"] - xc))
        if abs(near["xc"] - xc) > tol:
            continue                       # 밀어 넣지 않는다 — 비워 둔다
        if near["year"] in out:
            continue                       # 첫 매칭만 (뒤따르는 %·배 컬럼 방지)
        out[near["year"]] = (v, klass)
    return out


def _eps_scan_page(words: Sequence[Sequence]) -> Tuple[List[Dict[str, Any]], int, int]:
    """한 페이지에서 (EPS 추정치들, 헤더발견여부, EPS행발견여부)."""
    rows = _eps_rows_from_words(words)
    if not rows:
        return [], 0, 0
    cellrows = [_eps_cells(r) for r in rows]
    ymid = [float(np.mean([float(w[1]) for w in r])) for r in rows]
    pitch = float(np.median(np.diff(ymid))) if len(ymid) > 2 else 12.0
    n_hdr = n_eps = 0
    found: List[Dict[str, Any]] = []

    for i, cr in enumerate(cellrows):
        hdr = _eps_parse_header(cr)
        if not hdr:
            continue
        n_hdr += 1
        fmonth = 12
        for _, _, t in cr:
            m = _FYEAR_MONTH_RE.search(t)
            if m and 1 <= int(m.group(1)) <= 12:
                fmonth = int(m.group(1))
                break
        j = i + 1
        if j < len(cellrows) and _eps_merge_suffix_row(hdr, cellrows[j]):
            j += 1
        #  헤더 아래로 최대 30행까지 걸어가되, 행간격이 크게 벌어지면 다른 표다 → 중단
        limit = min(j + 30, len(cellrows))
        while j < limit:
            if j > 0 and (ymid[j] - ymid[j - 1]) > max(2.2 * pitch, pitch + 12.0):
                break
            cr2 = cellrows[j]
            if cr2:
                label = cr2[0][2].strip()
                if _EPS_OK_RE.match(label.replace(" ", "")) and not _EPS_BAD_RE.search(label):
                    n_eps += 1
                    mapped = _eps_map_to_years(hdr, cr2[1:])
                    if len(mapped) >= 2:
                        for y, (v, klass) in mapped.items():
                            found.append({"fiscal_year": y, "fiscal_month": fmonth,
                                          "value": v, "value_class": klass,
                                          "suffix": next((d["suffix"] for d in hdr
                                                          if d["year"] == y), "")})
                        return found, n_hdr, n_eps
            j += 1
    return found, n_hdr, n_eps


def eps_extract_from_pdf(path: str, max_pages: int = 3) -> Dict[str, Any]:
    """PDF 1개 → EPS 추정치 목록 + 진단 상태. 예외를 밖으로 내보내지 않는다."""
    res: Dict[str, Any] = {"status": "NO_PARSER", "rows": [], "n_words": 0}
    if fitz is None:
        return res
    try:
        with fitz.open(path) as doc:
            npg = min(max_pages, doc.page_count)
            total_words = 0
            for pi in range(npg):
                words = doc[pi].get_text("words")
                total_words += len(words)
                rows, n_hdr, n_eps = _eps_scan_page(words)
                if rows:
                    res.update(status="OK", rows=rows, n_words=total_words, page=pi)
                    return res
            res["n_words"] = total_words
            res["status"] = "NO_TEXT_LAYER" if total_words == 0 else "NO_TABLE"
    except Exception as e:
        res["status"] = f"ERR:{type(e).__name__}"
    return res


def _eps_worker(job: Tuple[str, str]) -> Tuple[str, Dict[str, Any]]:
    uid, path = job
    return uid, eps_extract_from_pdf(path)


def build_eps_forecasts(reports: pd.DataFrame, links: pd.DataFrame,
                        annual_rcept: Optional[Dict[Tuple[str, int], pd.Timestamp]] = None
                        ) -> pd.DataFrame:
    """캐시된 PDF 에서 EPS 추정치를 뽑아 §2.1 표준 스키마로 만든다.

    ★ 네트워크를 쓰지 않는다. 드라이브에 이미 있는 blob 만 읽는다(절대 1원칙: 캐시 우선).
    ★ 결과는 **공용 인덱스**에 저장한다 — EPS 추정치 원장은 이 전략 전용물이 아니라
      다른 전략도 그대로 쓸 수 있는 범용 정제본이기 때문이다.
    ★ 재실행 시 파서 버전이 같은 건은 건너뛴다(이어받기). 버전을 올리면 전부 재파싱된다.
    """
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if reports is None or reports.empty or links is None or links.empty:
        LOG.warn("리포트/애널리스트 원장이 비어 EPS 트랙을 만들 수 없습니다.")
        return empty
    if fitz is None:
        LOG.warn("pymupdf(fitz) 가 없어 EPS 추출을 건너뜁니다 — TP 트랙만 사용됩니다. "
                 "`pip install pymupdf` 로 EPS 트랙이 살아납니다.")
        return empty

    #  ① 캐시된 EPS 원장을 먼저 읽는다
    cached = VAULT.get_table(EPS_TABLE, scope="shared")
    done_ok: Dict[str, pd.DataFrame] = {}
    if cached is not None and len(cached) and "parser_version" in cached.columns:
        cached = cached[cached["parser_version"].astype(str) == EPS_PARSER_VERSION]
        LOG.info(f"공용 캐시에서 EPS 추정치 {len(cached):,}행 재사용 "
                 f"(파서 v{EPS_PARSER_VERSION})")
    else:
        cached = None
    st = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
    seen: set = set()
    if st is not None and len(st) and "parser_version" in st.columns:
        seen = set(st.loc[st["parser_version"].astype(str) == EPS_PARSER_VERSION,
                          "report_uid"].astype(str))

    #  ② uid → 실제 파일 경로. get_blob 은 바이트를 통째로 읽으므로 쓰지 않는다.
    idx = VAULT.load_index("shared")
    paths: Dict[str, str] = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        paths = dict(zip(sub["key"].astype(str), sub["abs_path"].astype(str)))
    if not paths:
        LOG.warn("드라이브 공용 인덱스에 리포트 PDF 가 없습니다 → EPS 트랙 비활성. "
                 "RESEARCH_DOWNLOAD_PDF=True 로 한 번 수집하면 이후 실행부터 캐시로 재사용됩니다.")
        return cached_to_forecasts(cached, links, annual_rcept) if cached is not None else empty

    todo = [(u, p) for u, p in paths.items()
            if u not in seen and os.path.exists(p)]
    LOG.info(f"EPS 추출 대상 {len(todo):,}건 (캐시 보유 {len(seen):,}건 건너뜀 · "
             f"드라이브 PDF 총 {len(paths):,}건)")

    new_rows, new_status = [], []
    if todo:
        chunk = max(200, int(PDF_PARSE_CHUNK))
        nch = (len(todo) - 1) // chunk + 1
        for k0 in range(0, len(todo), chunk):
            part = todo[k0:k0 + chunk]
            out = pmap_cpu(_eps_worker, part,
                           workers=(PDF_PARSE_WORKERS or None),
                           desc=f"EPS 추출 {k0//chunk + 1}/{nch}")
            for r in out:
                if not r:
                    continue
                uid, res = r
                new_status.append({"report_uid": uid, "status": res["status"],
                                   "n_words": res.get("n_words", 0),
                                   "parser_version": EPS_PARSER_VERSION})
                for row in res.get("rows", []):
                    new_rows.append({"report_uid": uid, **row,
                                     "parser_version": EPS_PARSER_VERSION})
            del out
            #  청크마다 저장 — 중간에 끊겨도 다음 실행이 정확히 이어받는다
            if new_rows or new_status:
                _eps_persist(cached, new_rows, new_status)
                cached = VAULT.get_table(EPS_TABLE, scope="shared")
                new_rows, new_status = [], []
    if new_rows or new_status:
        _eps_persist(cached, new_rows, new_status)
        cached = VAULT.get_table(EPS_TABLE, scope="shared")

    _eps_report_extraction(reports, links)
    return cached_to_forecasts(cached, links, annual_rcept)


def _eps_persist(cached: Optional[pd.DataFrame], rows: List[dict], status: List[dict]):
    """추출 결과를 공용 인덱스에 누적 저장 (기존 행을 지우지 않고 합집합)."""
    if rows:
        new = pd.DataFrame(rows)
        allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
        allr = allr.drop_duplicates(subset=["report_uid", "fiscal_year", "parser_version"],
                                    keep="last")
        VAULT.put_table(EPS_TABLE, allr, scope="shared", domain="research",
                        source=f"pdf_eps_parser v{EPS_PARSER_VERSION}")
        PIPE.io("OUT", "DRIVE", EPS_TABLE, allr, source="pdf eps extraction")
    if status:
        prev = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
        new = pd.DataFrame(status)
        alls = pd.concat([prev, new], ignore_index=True) if prev is not None and len(prev) else new
        alls = alls.drop_duplicates(subset=["report_uid", "parser_version"], keep="last")
        VAULT.put_table(EPS_STATUS_TABLE, alls, scope="shared", domain="research",
                        source=f"pdf_eps_parser v{EPS_PARSER_VERSION}")
    VAULT.flush("shared")


def cached_to_forecasts(eps: Optional[pd.DataFrame], links: pd.DataFrame,
                        annual_rcept: Optional[Dict[Tuple[str, int], pd.Timestamp]] = None
                        ) -> pd.DataFrame:
    """EPS 추출 원장 + 애널리스트 연결표 → §2.1 analyst_forecasts (metric='EPS')."""
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if eps is None or not len(eps):
        return empty
    L = links.copy()
    if FORECAST_ATTRIBUTION == "lead" and "role" in L.columns:
        L = L[L["role"].astype(str).eq("lead")]
    L = L.dropna(subset=["stock_code"])
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"])
    keep = ["report_uid", "analyst_id", "broker_id", "stock_code", "pub_date"]
    m = eps.merge(L[keep].drop_duplicates(), on="report_uid", how="inner")
    if m.empty:
        return empty

    #  ── 실적(ACTUAL) 컬럼 제거: 추정치만 남긴다 ────────────────────────────────────
    #  판정 순서 (§ PIT): ① 명시 접미사 → ② DART 사업보고서 접수일 → ③ 회계연도말 비교
    m["fiscal_month"] = m["fiscal_month"].fillna(12).astype(int).clip(1, 12)
    fy_end = pd.to_datetime(dict(year=m["fiscal_year"].astype(int),
                                 month=m["fiscal_month"], day=1)) + pd.offsets.MonthEnd(0)
    m["fiscal_period_end"] = fy_end
    suf = m["suffix"].astype(str).str.upper()
    is_est = pd.Series(np.nan, index=m.index, dtype="float64")
    is_est[suf.isin(["E", "F", "P"])] = 1.0
    is_est[suf.eq("A")] = 0.0
    m["ae_confidence"] = np.where(is_est.notna(), "HIGH", "LOW")

    if annual_rcept:
        key = list(zip(m["stock_code"].astype(str), m["fiscal_year"].astype(int)))
        rc = pd.Series([annual_rcept.get(k, pd.NaT) for k in key], index=m.index)
        known = is_est.isna() & rc.notna()
        #  리포트 발간일이 그 회계연도 사업보고서 접수일 이후면 이미 '실적'이다
        is_est[known] = (m.loc[known, "pub_date"] < rc[known]).astype(float)
        m.loc[known, "ae_confidence"] = "HIGH"
    fallback = is_est.isna()
    is_est[fallback] = (m.loc[fallback, "fiscal_period_end"] > m.loc[fallback, "pub_date"]).astype(float)
    m["is_estimate"] = is_est.astype(bool)

    n_all = len(m)
    m = m[m["is_estimate"]]
    LOG.debug(f"EPS: 추출 {n_all:,}행 중 추정치 {len(m):,}행 (실적 컬럼 {n_all-len(m):,}행 제외)")

    out = pd.DataFrame({
        "stock_id": m["stock_code"].astype(str),
        "analyst_id": m["analyst_id"].astype(str),
        "broker_id": m["broker_id"].astype(str),
        "report_id": m["report_uid"].astype(str),
        "report_date": m["pub_date"],
        "fiscal_period": (m["fiscal_year"].astype(int).astype(str) + "-" +
                          m["fiscal_month"].astype(int).map("{:02d}".format)),
        "forecast_metric": "EPS",
        "forecast_value": pd.to_numeric(m["value"], errors="coerce"),
        "value_class": m["value_class"].astype(str),
        "horizon_yrs": (m["fiscal_year"].astype(int) - m["pub_date"].dt.year).astype("int16"),
        "is_estimate": True,
        "ae_confidence": m["ae_confidence"].astype(str),
    })
    #  §32 — 값이 없는 행(적전/흑전/n.a.)만 제외한다. 애널리스트는 유지된다.
    out = out[out["forecast_value"].notna()]
    #  터무니없는 값 방어: 주당순이익이 1,000만원을 넘거나 0.0001 미만이면 파싱 오류다
    bad = out["forecast_value"].abs() > 1e7
    if bad.any():
        LOG.debug(f"EPS 이상치 {int(bad.sum()):,}행 제외 (|EPS| > 1,000만원 — 단위 오인 추정)")
        out = out[~bad]
    return out.reset_index(drop=True)


def _eps_report_extraction(reports: pd.DataFrame, links: pd.DataFrame):
    """★ 증권사×연도 추출률 — 선택편향을 눈에 보이게 만드는 표."""
    st = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
    if st is None or not len(st):
        return
    st = st[st["parser_version"].astype(str) == EPS_PARSER_VERSION]
    if not len(st) or reports is None or reports.empty:
        return
    r = reports[["report_uid", "broker_name", "pub_date"]].copy()
    r["year"] = as_ts_series(r["pub_date"]).dt.year
    m = r.merge(st[["report_uid", "status"]], on="report_uid", how="inner")
    if m.empty:
        return
    m["ok"] = m["status"].astype(str).eq("OK")

    tot = m.groupby("status", observed=True).size().sort_values(ascending=False)
    LOG.table([[k, f"{v:,}", f"{100*v/len(m):.1f}%"] for k, v in tot.items()],
              ["추출 상태", "건수", "비중"], ["l", "r", "r"],
              title="EPS 추출 결과 분포 (OK=추정표 발견 · NO_TABLE=표 못 찾음 · "
                    "NO_TEXT_LAYER=스캔본이라 글자가 없음)")

    piv = m.pivot_table(index="broker_name", columns="year", values="ok", aggfunc="mean")
    cnt = m.groupby("broker_name", observed=True).size().sort_values(ascending=False)
    top = [b for b in cnt.index[:25] if b in piv.index]
    yrs = sorted(piv.columns)[-10:]
    rows = [[b, f"{cnt[b]:,}"] + [f"{100*piv.loc[b, y]:.0f}%" if pd.notna(piv.loc[b, y]) else "—"
                                  for y in yrs] for b in top]
    LOG.table(rows, ["증권사", "리포트"] + [str(y) for y in yrs],
              ["l", "r"] + ["r"] * len(yrs),
              title="★ 증권사×연도 EPS 추출률 — 이 표가 균일하지 않으면 EPS 트랙의 애널리스트 "
                    "점수는 '실력'이 아니라 'PDF 양식'을 반영합니다 (구조적 선택편향)")

    low = [b for b in top if np.nanmean(piv.loc[b, yrs].to_numpy(dtype="float64")) < 0.20]
    if low:
        LOG.warn(f"EPS 추출률 20% 미만 증권사 {len(low)}개: {', '.join(low[:8])}"
                 f"{' 외' if len(low) > 8 else ''} — 이 증권사 애널리스트는 EPS 트랙에서 "
                 f"이력이 얇아 전원 중립(0)으로 수축됩니다. 탈락은 아니지만 차등도 못 받습니다. "
                 f"→ 결론은 반드시 TP 트랙과 교차검증하세요.")


# ══════════════════════════════════════════════════════════════════════════════════════
#  TP 트랙 — 목표주가를 같은 산식에 그대로 태운다
# ══════════════════════════════════════════════════════════════════════════════════════

TP_FISCAL_PERIOD = "TP12M"          # 목표주가는 통상 12개월 선행 → 단일 버킷
TP_HORIZON_TRADING_DAYS = 250       # 실측 시점 (≈12개월)


def build_tp_forecasts(links: pd.DataFrame, adj_factor: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """목표주가 → §2.1 analyst_forecasts (metric='TP').

    ★ 액면분할 보정: 원 목표주가는 발표 시점의 '실제 주가' 단위다. 10년치를 한 통에 담으면
      분할 종목에서 컨센서스와 리비전이 통째로 망가진다. 그래서 발표일의
      adj_factor = 수정주가/실제주가 를 곱해 모든 목표주가를 '수정주가 통화'로 환산한다.
      (같은 날짜의 비율이므로 미래 정보가 들어가지 않는다 — adj_factor 는 t 시점에
       관측 가능한 두 가격의 비이며, 이후의 분할은 두 계열을 함께 움직인다)
    """
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if links is None or links.empty:
        return empty
    L = links.copy()
    if FORECAST_ATTRIBUTION == "lead" and "role" in L.columns:
        L = L[L["role"].astype(str).eq("lead")]
    L["pub_date"] = as_ts_series(L["pub_date"])
    L["target_price"] = pd.to_numeric(L["target_price"], errors="coerce")
    #  적정가격 "0"/"-" 는 '목표주가 없음' 이지 0원이 아니다
    L = L[L["target_price"].notna() & (L["target_price"] > 0)]
    L = L.dropna(subset=["stock_code", "pub_date", "analyst_id"])
    if L.empty:
        return empty

    tp = L["target_price"].astype("float64")
    n_adj = 0
    if adj_factor is not None and len(adj_factor):
        af = adj_factor[["code", "date", "adj_factor"]].dropna().copy()
        af["date"] = _scg_ns(af["date"])
        af = af.sort_values("date")
        Ls = L.assign(_i=np.arange(len(L)))
        Ls["pub_date"] = _scg_ns(Ls["pub_date"])
        Ls = Ls.sort_values("pub_date")
        j = pd.merge_asof(Ls, af.rename(columns={"date": "pub_date"}),
                          on="pub_date", left_by="stock_code", right_by="code",
                          direction="backward", tolerance=pd.Timedelta(days=10))
        j = j.sort_values("_i")
        f = pd.to_numeric(j["adj_factor"], errors="coerce").to_numpy("float64")
        n_adj = int(np.isfinite(f).sum())
        tp = tp.to_numpy("float64") * np.where(np.isfinite(f) & (f > 0), f, 1.0)
    LOG.debug(f"TP 트랙: {len(L):,}건 (분할보정 적용 {n_adj:,}건)")

    return pd.DataFrame({
        "stock_id": L["stock_code"].astype(str),
        "analyst_id": L["analyst_id"].astype(str),
        "broker_id": L["broker_id"].astype(str),
        "report_id": L["report_uid"].astype(str),
        "report_date": L["pub_date"].values,
        "fiscal_period": TP_FISCAL_PERIOD,
        "forecast_metric": "TP",
        "forecast_value": np.asarray(tp, dtype="float64"),
        "value_class": "NUM",
        "horizon_yrs": np.int16(1),
        "is_estimate": True,
        "ae_confidence": "HIGH",
    }).reset_index(drop=True)


def build_tp_accuracy_events(forecasts: pd.DataFrame, px_adj: pd.DataFrame, cal,
                             cfg: SCGConfig = SCG) -> pd.DataFrame:
    """TP 트랙의 Accuracy Event — §8 의 산식을 그대로, '실적' 대신 '실제 주가'로 채점한다.

    왜 build_accuracy_events 를 재사용하지 않는가:
      EPS 는 (종목·회계연도)마다 실측치가 **한 번** 나오지만, 목표주가는 회계연도가 없다.
      TP 의 fiscal_period 를 분기로 쪼개면 신호 단계의 컨센서스까지 분기별로 조각나
      (§6 의 '활성 전망 집합'이 무너진다). 그래서 신호용 fiscal_period 는 단일 버킷으로
      두고, 채점만 여기서 분기 빈티지 단위로 따로 만든다. 산식·클리핑·스케일은 §8 동일.

    ★ PIT: 사건 완료일 = 예측 시점(분기말) + 250거래일. build_analyst_scores 가
      '완료일 < T' 만 쓰므로 미래 주가는 현재 점수에 들어갈 수 없다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "actual_announcement_date", "actual_value", "forecast_value",
            "consensus_at_event", "n_analysts", "scale", "ne_analyst", "ne_consensus",
            "acc_event", "acc_event_loo", "report_date", "forecast_age_days"]
    f = forecasts[forecasts["forecast_metric"].astype(str).eq("TP")] if forecasts is not None and len(forecasts) else None
    if f is None or f.empty or px_adj is None or px_adj.empty:
        return pd.DataFrame(columns=cols)

    calv = _scg_trading_calendar(cal)
    M, codes, didx = _scg_price_matrix(px_adj, calv)
    if M.size == 0:
        return pd.DataFrame(columns=cols)

    #  분기말을 '예측 기준일' 로 삼는다. 그 시점의 활성 목표주가 집합이 하나의 예측 사건.
    f = f.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f = f.dropna(subset=["report_date", "forecast_value"])
    qs = pd.PeriodIndex(pd.DatetimeIndex(sorted(f["report_date"].dropna().unique())).to_period("Q")).unique()
    ref = pd.DatetimeIndex([q.end_time.normalize() for q in qs]).sort_values()
    if not len(ref):
        return pd.DataFrame(columns=cols)

    act = build_active_forecasts(f, ref, cfg)
    if act.empty:
        return pd.DataFrame(columns=cols)
    act = act.rename(columns={"signal_date": "event_ref"})
    act["outcome_date"] = _scg_shift_td(act["event_ref"], TP_HORIZON_TRADING_DAYS, calv)
    act = act[act["outcome_date"].notna()]
    if act.empty:
        return pd.DataFrame(columns=cols)

    ci = act["stock_id"].map(codes)
    pos = np.searchsorted(didx, act["outcome_date"].values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = ci.notna().to_numpy() & (pos >= 0)
    act["actual_value"] = np.where(
        ok, M[np.clip(pos, 0, len(didx) - 1), ci.fillna(0).to_numpy("int64")], np.nan)
    act = act.dropna(subset=["actual_value"])
    if act.empty:
        return pd.DataFrame(columns=cols)

    #  §8 산식 — EPS 트랙과 완전히 동일하다
    key = ["stock_id", "event_ref"]
    g = act.groupby(key, observed=True, sort=False)["forecast_value"]
    act["n_analysts"] = g.transform("size").astype("int32")
    act["_sum"] = g.transform("sum")
    act["consensus_at_event"] = g.transform("mean")
    act["_median_abs"] = act.groupby(key, observed=True, sort=False)["forecast_value"] \
                            .transform(lambda s: s.abs().median())
    act = act[act["n_analysts"] >= cfg.MIN_ANALYSTS]
    if act.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    A = act["actual_value"].to_numpy("float64")
    F = act["forecast_value"].to_numpy("float64")
    C = act["consensus_at_event"].to_numpy("float64")
    scale = np.maximum.reduce([np.abs(A), act["_median_abs"].to_numpy("float64"),
                               np.full(A.shape, eps)])
    ne_j, ne_c = np.abs(F - A) / scale, np.abs(C - A) / scale
    n = act["n_analysts"].to_numpy("float64")
    c_loo = np.where(n > 1, (act["_sum"].to_numpy("float64") - F) / np.maximum(n - 1, 1), np.nan)

    out = pd.DataFrame({
        "stock_id": act["stock_id"].values,
        "analyst_id": act["analyst_id"].values,
        "fiscal_period": TP_FISCAL_PERIOD,
        "forecast_metric": "TP",
        "actual_announcement_date": act["outcome_date"].values,
        "actual_value": A, "forecast_value": F,
        "consensus_at_event": C, "n_analysts": act["n_analysts"].values,
        "scale": scale, "ne_analyst": ne_j, "ne_consensus": ne_c,
        "acc_event": np.clip(np.log((ne_c + eps) / (ne_j + eps)),
                             -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP),
        "acc_event_loo": np.clip(np.log((np.abs(c_loo - A) / scale + eps) / (ne_j + eps)),
                                 -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP),
        "report_date": act["report_date"].values,
        "forecast_age_days": act["forecast_age_days"].values,
    })
    LOG.debug(f"TP Accuracy 이벤트 {len(out):,}건 ({out['analyst_id'].nunique():,}명)")
    return out[cols].reset_index(drop=True)
