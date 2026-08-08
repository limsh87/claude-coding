

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  원장 — 증권사 정규화 / 리포트 원장 / 애널리스트 원장 / 인물 추적 / Phase 0 게이트    ║
# ║                                                                                          ║
# ║  이 모듈이 답해야 하는 질문:                                                               ║
# ║    Q1. 리포트와 애널리스트가 제대로 연결되었는가?  → report_analyst_link + 연결 감사표      ║
# ║    Q2. 다중소스 원장 연결은 확실한가?              → dedup_key 병합 + 소스기여 감사표       ║
# ║    Q3. 이 사람이 이직한 것인가, 그만둔 것인가?     → analyst_person_id (§5 식별자 규약)     ║
# ║                                                                                          ║
# ║  ★ 식별자 두 개를 반드시 구분한다 (§5 — 혼동 금지):                                        ║
# ║      analyst_broker_identity = f"{analyst}@{broker}"  ← 주의 배분의 단위. 소속이 바뀌면     ║
# ║                                                        다른 예산이므로 다른 ID 가 맞다.     ║
# ║      analyst_person_id                                ← 인물 단위. 이직 추적용.             ║
# ║                                                        §6.5 M-EXIT 판정에서만 쓴다.        ║
# ║    이 둘을 섞으면 "이직했는데 자발적으로 끊은 것"으로 오분류되어 인과분해가 무너진다.       ║
# ║                                                                                          ║
# ║  증권사 사명 변경(2016~2026)을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로          ║
# ║  다른 사람이 되어 **모든 커버리지 철회가 가짜로 발생한다.** 이 전략에서는 치명적이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BROKER_CANON: List[Tuple[str, str]] = [
    (r"미래에셋(대우|증권|생명)?", "미래에셋증권"),          # 미래에셋대우→미래에셋증권(2021)
    (r"(대우증권|KDB대우)", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),        # 우리투자→NH투자(2014)
    (r"한국투자|한국證|한투증권", "한국투자증권"),
    (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),                # KB투자+현대증권→KB증권(2017)
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),        # 신한금융투자→신한투자증권(2022)
    (r"하나(증권|금융투자|금투)", "하나증권"),                # 하나금융투자→하나증권(2022)
    (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"),
    (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"),                       # 동양→유안타(2014)
    (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"),
    (r"IBK(투자증권|증권)|기업은행", "IBK투자증권"),
    (r"신영증권", "신영증권"),
    (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),      # HMC투자→현대차증권(2016)
    (r"SK증권", "SK증권"),
    (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권|하이證", "iM증권"),        # 하이투자→iM증권(2024)
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),           # 이베스트→LS증권(2024)
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),      # KTB→다올(2022)
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),             # 동부→DB금융투자(2018)
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"), (r"부국증권", "부국증권"),
    (r"한양증권", "한양증권"), (r"상상인증권|골든브릿지", "상상인증권"),
    (r"케이프(투자증권|증권)", "케이프투자증권"), (r"토스증권", "토스증권"),
    (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"), (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"), (r"DS투자증권", "DS투자증권"),
    (r"NICE|나이스", "NICE디앤비"), (r"에프앤가이드|FnGuide", "에프앤가이드"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]

MAJOR_BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "키움증권", "메리츠증권", "대신증권"]


def normalize_broker(raw: Any) -> Tuple[str, str]:
    """(broker_canon_id, 정식명). 합병 전후를 하나로 묶는 **정규화(canonical)** 식별자.
    용도: 목표주가 리비전 연속성 — 사명이 바뀌었다고 같은 애널의 TP 계열이 끊기면 안 된다."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return (sha1_str("broker", canon)[:12], canon)
    canon = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    return (sha1_str("broker", canon)[:12], canon)


# ── 법인 단위 식별자 (이직 탐지 전용) ───────────────────────────────────────────────────────
#   ★ 정규화 식별자만 쓰면 **이직이 통째로 사라진다.** 2016년 대우증권 → 미래에셋증권 이동이
#     둘 다 '미래에셋증권' 으로 정규화되어 같은 소속으로 보이기 때문이다. 동일 문제:
#     우리투자/NH, 현대/KB, 하나금투/하나, 동양/유안타, 하이/iM, 이베스트/LS, KTB/다올, 동부/DB.
#   → 발간 시점의 **실제 법인명**을 별도 식별자로 유지한다. 이동 판정은 오직 이것으로만 한다.
#   합병 이력 — 발효 전후 ±3개월의 철회 사건은 '제도적 소음'이라 라벨을 붙이지 않고 제외한다.
BROKER_MERGERS = [                    # (구법인 패턴, 신법인, 합병 발효일)
    (r"대우증권|KDB대우", "미래에셋증권", "2016-12-30"),
    (r"우리투자증권", "NH투자증권", "2014-12-31"),
    (r"현대증권", "KB증권", "2017-01-01"),
    (r"하나대투|하나금융투자", "하나증권", "2022-11-01"),
    (r"동양증권", "유안타증권", "2014-10-01"),
    (r"하이투자증권", "iM증권", "2024-09-01"),
    (r"이베스트투자증권", "LS증권", "2024-03-01"),
    (r"KTB투자증권", "다올투자증권", "2022-04-01"),
    (r"동부증권", "DB금융투자", "2018-01-01"),
    (r"신한금융투자", "신한투자증권", "2022-09-01"),
]

LEGAL_ALIASES = [                     # 철자 변형만 통합한다. 합병은 절대 통합하지 않는다.
    (r"^미래에셋대우증권$", "미래에셋대우"),
    (r"^KDB대우증권$", "대우증권"),
    (r"^우리투자$", "우리투자증권"),
    (r"^한국투자$|^한국투자증권$|^한국證$|^한투증권$", "한국투자증권"),
    (r"^하나대투증권$", "하나대투"),
    (r"^하나금융투자$|^하나금투$", "하나금융투자"),
    (r"^신한금융투자$|^신한금투$", "신한금융투자"),
    (r"^이베스트투자증권$|^eBEST투자증권$|^E\*?BEST투자증권$", "이베스트투자증권"),
    (r"^하이證$|^하이증권$", "하이투자증권"),
]
_LEGAL_RE = [(re.compile(p, re.I), n) for p, n in LEGAL_ALIASES]


def normalize_broker_legal(raw: Any) -> Tuple[str, str]:
    """(broker_legal_id, 법인명). 합병 전후를 **구분한다.** 이동 판정의 유일한 근거."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    t2 = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    for rx, nm in _LEGAL_RE:
        if rx.match(t2):
            t2 = nm
            break
    return (sha1_str("broker_legal", t2)[:12], t2)


_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")
_ROLE_WORDS = r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사|이사|부장|차장|대리|파트장)"


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동/김철수' / '홍길동 외 1인' → ['홍길동','김철수']"""
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(_ROLE_WORDS, " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치|센터|팀)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


def _atoms(vals, sep: str) -> List[str]:
    """합성 토큰을 원자로 되돌린 뒤 정렬·중복제거. 병합을 멱등하게 만드는 핵심 함수."""
    out = set()
    for v in vals:
        s = str(v)
        if not s or s.lower() in ("nan", "none", "<na>"):
            continue
        for tok in s.split(sep):
            tok = tok.strip()
            if tok and tok.lower() not in ("nan", "none", "<na>"):
                out.add(tok)
    return sorted(out)


def _pick_str(vals) -> str:
    """비어있지 않은 값 중 사전순 최소. '행 순서상 첫 값'과 달리 실행 간 재현된다."""
    c = sorted({str(v).strip() for v in vals
                if v is not None and str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "<na>")})
    return c[0] if c else ""


def build_report_master(raw: "pd.DataFrame", sec: "pd.DataFrame") -> "pd.DataFrame":
    """다중 소스 병합 → 리포트 원장. 중복 제거가 아니라 '병합'이다(정보를 버리지 않는다).

    ★ 이 함수의 출력은 다음 실행에서 드라이브 캐시로부터 '입력'으로 되돌아온다.
      그래서 반드시 **멱등**이어야 한다. 아니면 실행할 때마다 source 문자열이 길어지고
      report_uid 가 바뀌어 애널리스트 연결표가 조용히 끊긴다."""
    if raw is None or raw.empty:
        LOG.warn("수집된 리포트가 없습니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    d = raw.copy()
    for c in REPORT_COLS:
        if c not in d.columns:
            d[c] = np.nan

    n_raw0 = len(d)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("2005-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일이 없거나 범위를 벗어난 리포트 {int(bad.sum()):,}건 제외 "
                 f"({100*bad.mean():.2f}%). 이 비율이 크면 소스의 날짜 형식이 바뀐 것입니다 — "
                 f"조용히 넘기지 말고 parse_kr_date 를 확인하세요.")
    d = d[~bad]
    if len(d) == 0:
        LOG.error("발간일이 유효한 리포트가 하나도 없습니다. 날짜 파싱이 깨졌습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    bid = as_str_series(d["broker_raw"]).map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]
    lid = as_str_series(d["broker_raw"]).map(normalize_broker_legal)
    d["broker_legal_id"] = [x[0] for x in lid]
    d["broker_legal_name"] = [x[1] for x in lid]

    # 종목코드: ① 소스 제공 ② 제목 정규식 ③ 종목명→코드 사전
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = as_str_series(d.loc[need, "title"]).map(code_from_title)
    need = d["stock_code"].isna() & (as_str_series(d["stock_name"]).str.len() > 0)
    if need.any() and sec is not None and len(sec):
        n2c: Dict[str, str] = {}
        for nm, cd in zip(sec["name"], sec["code"]):
            k = norm_corp_name(nm)
            if k and k not in n2c:
                n2c[k] = cd
        d.loc[need, "stock_code"] = as_str_series(d.loc[need, "stock_name"]).map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = as_str_series(d["title"]).map(_dedup_repeat)
    # report_uid 는 '한 번 붙으면 안 바뀌는' 식별자여야 한다. 이미 붙어 있으면 보존한다.
    _uid_new = [sha1_str(s, i) for s, i in zip(as_str_series(d["source"]),
                                               as_str_series(d["src_report_id"]))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b, c or "", norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             as_str_series(d["stock_code"]), d["title"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"])

    # ── 멱등 병합 (재실행 안전) ────────────────────────────────────────────────────────
    #   source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로 단순 set 병합은
    #   그걸 원자 하나로 취급해 실행마다 문자열이 무한히 길어진다. 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌므로
    #   순서 무관한 min 으로 고정한다. (min{u1,u2,min(u1,u2)} = min(u1,u2))
    m = d.groupby("dedup_key", as_index=False).agg(**{
        "report_uid": ("report_uid", "min"),
        "src_report_id": ("src_report_id", lambda s: "|".join(_atoms(s, "|"))),
        "source": ("source", lambda s: "+".join(_atoms(s, "+"))),
        "category": ("category", _pick_str),
        "pub_date": ("pub_date", "min"),
        "title": ("title", lambda s: max(sorted(set(map(str, s))), key=len)),
        "stock_code": ("stock_code", lambda s: _pick_str(s) or None),
        "stock_name": ("stock_name", _pick_str),
        "broker_id": ("broker_id", "min"),          # dedup_key 구성요소라 그룹 내 동일
        "broker_name": ("broker_name", "min"),
        "broker_legal_id": ("broker_legal_id", "min"),
        "broker_legal_name": ("broker_legal_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),    # 네이티브 max = NaN 무시
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"리포트 원장 병합: 수집 {n_raw0:,} → 날짜유효 {n_raw:,} → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0-n_raw:,} · 소스 간 중복 병합 {n_raw-len(m):,})")
    m["month"] = m["pub_date"] + pd.offsets.MonthEnd(0)
    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver")
    return m


# ── 애널리스트 원장 + 인물 추적 ─────────────────────────────────────────────────────────────
def build_analyst_ledger(rep: "pd.DataFrame") -> Tuple["pd.DataFrame", "pd.DataFrame"]:
    """(애널리스트 마스터, 리포트↔애널리스트 연결표). 연결 방법과 신뢰도를 반드시 기록한다."""
    empty_a = pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name",
                                    "analyst_person_id"])
    empty_l = pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"])
    if rep is None or rep.empty:
        return empty_a, empty_l

    links = []
    for r in rep.itertuples(index=False):
        raw = getattr(r, "analyst_raw", "") or ""
        names, method, conf = [], "unresolved", 0.0
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98        # 한경 '작성자' 컬럼 — 최고 신뢰도
        if not names:
            praw = getattr(r, "pdf_analysts", "") or ""
            if str(praw).strip():
                names = [n for n in str(praw).split(",") if n.strip()]
                method, conf = "pdf_header", 0.80
        if not names:
            continue
        for i, nm in enumerate(names):
            links.append({
                "report_uid": r.report_uid, "name": nm, "broker_id": r.broker_id,
                "broker_name": r.broker_name,
                "broker_legal_id": getattr(r, "broker_legal_id", r.broker_id),
                "broker_legal_name": getattr(r, "broker_legal_name", r.broker_name),
                "role": "lead" if i == 0 else "co",
                "link_method": method, "link_conf": conf,
                "pub_date": r.pub_date, "month": r.month, "code": r.stock_code,
                "category": getattr(r, "category", ""), "target_price": r.target_price,
                "opinion": r.opinion,
            })
    if not links:
        LOG.error("애널리스트를 한 건도 식별하지 못했습니다. 한경컨센서스 수집이 실패했거나 "
                  "skinType=business 응답에 작성자 컬럼이 없습니다. "
                  "★ Phase 0 게이트가 이 상태를 감지해 하우스 단위 폴백으로 격하시킵니다.")
        return empty_a, empty_l

    L = pd.DataFrame(links)
    L["name_norm"] = as_str_series(L["name"]).str.replace(r"\s+", "", regex=True)
    L["code"] = as_str_series(L["code"]).replace("", np.nan)
    # 주의 배분의 단위: (법인, 이름). 소속이 바뀌면 예산이 다르므로 다른 ID 가 맞다.
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14]
                       for b, n in zip(L["broker_legal_id"], L["name_norm"])]

    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name_norm", "first"),
               broker_id=("broker_id", "first"), broker_name=("broker_name", "first"),
               broker_legal_id=("broker_legal_id", "first"),
               broker_legal_name=("broker_legal_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("code", lambda s: int(s.dropna().nunique()))))
    A, n_moves, borderline = _build_person_map(A, L)
    L = L.merge(A[["analyst_id", "analyst_person_id"]], on="analyst_id", how="left")

    LOG.ok(f"애널리스트 원장 {len(A):,}개 법인-계정 · 인물 "
           f"{A['analyst_person_id'].nunique():,}명 · 이직 판정 {n_moves:,}건 · "
           f"연결 {len(L):,}건 (동명 후보 {int(A['name_ambiguous'].sum()):,})")
    if borderline:
        LOG.table(borderline[:20], ["이름", "이전 법인", "이후 법인", "공백(개월)",
                                    "종목 Jaccard", "점수", "판정"],
                  ["l", "l", "l", "r", "r", "r", "l"],
                  title="이직 판정 경계 사례 (점수 0.4~0.9) — 동명이인일 가능성을 숨기지 않습니다")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


PERSON_MERGE_ACCEPT = 0.70      # 사전 고정. 사후 조정 금지.
PERSON_MERGE_REJECT = 0.40


def _build_person_map(A: "pd.DataFrame", L: "pd.DataFrame"
                      ) -> Tuple["pd.DataFrame", int, List[list]]:
    """analyst_person_id — 이직 추적. **점수화**하고 회색지대는 라벨을 붙이지 않는다.

    같은 이름이 두 법인에 나타나면 ① 이직 ② 동명이인 둘 중 하나다. 10년 누적 3,500명이면
    동명쌍이 60~245개, 그중 타사×시간인접한 '실질 위험쌍'이 18~71개 발생한다(생일문제 근사).
    0.5 에서 이진 병합하면 그 전부를 잘못 판정한다.

    규칙:
      · 재직 구간이 3개월 넘게 **겹치면** 즉시 별개인 (시간 배타성 — 비용 0, 거짓병합 대부분 제거)
      · 공백이 18개월을 넘으면 별개인
      · 점수 = 0.35·섹터겹침 + 0.35·종목겹침 + 0.20·(공백 짧을수록) + 0.10·공저자겹침
      · ≥0.70 동일인 / 0.40~0.70 **UNCLASSIFIED (사건에서 제외)** / <0.40 별개인

    ★ 회색지대를 억지로 한쪽에 붙이지 않는 것이 핵심이다. 붙이면 M-EXIT 과 V-DROP 이
      서로 오염되어 §6.5 인과분해 전체가 무의미해진다.
    """
    A = A.copy()
    A["analyst_person_id"] = A["analyst_id"]
    A["person_merge_conf"] = 1.0
    A["person_unclassified"] = False
    dup = A.groupby("name")["analyst_id"].transform("size")
    A["name_ambiguous"] = dup > 1

    sub = L.dropna(subset=["code"])
    cov = sub.groupby("analyst_id")["code"].apply(lambda s: set(map(str, s))).to_dict()
    sec_ = (L.groupby("analyst_id")["category"].apply(lambda s: set(map(str, s.dropna())))
            .to_dict())
    coa = (L.groupby("report_uid")["analyst_id"].apply(set))
    peers: Dict[str, set] = defaultdict(set)
    for _, ids in coa.items():
        if len(ids) > 1:
            for i in ids:
                peers[i] |= (ids - {i})

    def _jac(a: set, b: set) -> float:
        return len(a & b) / max(1, len(a | b))

    n_moves = 0
    borderline: List[list] = []
    for nm, grp in A[A["name_ambiguous"]].groupby("name"):
        g = grp.sort_values("first_seen")
        ids = g["analyst_id"].tolist()
        anchor = {ids[0]: ids[0]}
        for prev, cur in zip(ids[:-1], ids[1:]):
            rp = g[g["analyst_id"] == prev].iloc[0]
            rc = g[g["analyst_id"] == cur].iloc[0]
            if rp["broker_legal_id"] == rc["broker_legal_id"]:
                anchor[cur] = anchor.get(prev, prev)
                continue
            overlap_m = ((min(as_ts(rp["last_seen"]), as_ts(rc["last_seen"])) -
                          max(as_ts(rp["first_seen"]), as_ts(rc["first_seen"]))).days / 30.44)
            gap_m = (as_ts(rc["first_seen"]) - as_ts(rp["last_seen"])).days / 30.44
            if overlap_m > 2 or gap_m > 18:
                anchor[cur] = cur                     # 동시 재직 또는 긴 공백 → 별개인
                continue
            j_stk = _jac(cov.get(prev, set()), cov.get(cur, set()))
            j_sec = _jac(sec_.get(prev, set()), sec_.get(cur, set()))
            has_peer = 1.0 if (peers.get(prev, set()) & peers.get(cur, set())) else 0.0
            s = (0.35 * min(1.0, j_sec / 0.5) + 0.35 * min(1.0, j_stk / 0.2)
                 + 0.20 * (1 - min(1.0, max(gap_m, 0) / 18.0)) + 0.10 * has_peer)
            s = float(np.clip(s, 0, 1))
            if s >= PERSON_MERGE_ACCEPT:
                anchor[cur] = anchor.get(prev, prev)
                n_moves += 1
                verdict = "동일인(이직)"
            elif s >= PERSON_MERGE_REJECT:
                anchor[cur] = cur
                A.loc[A["analyst_id"].isin([prev, cur]), "person_unclassified"] = True
                verdict = "★판정불가 → 철회 사건에서 제외"
            else:
                anchor[cur] = cur
                verdict = "별개인(동명이인)"
            A.loc[A["analyst_id"] == cur, "person_merge_conf"] = s
            if 0.40 <= s <= 0.90:
                borderline.append([nm, str(rp["broker_legal_name"])[:14],
                                   str(rc["broker_legal_name"])[:14], f"{gap_m:.1f}",
                                   f"{j_stk:.2f}", f"{s:.2f}", verdict])
        m = A["analyst_id"].isin(ids)
        A.loc[m, "analyst_person_id"] = A.loc[m, "analyst_id"].map(anchor).fillna(
            A.loc[m, "analyst_id"])

    nper = A.groupby("analyst_person_id")["broker_legal_id"].nunique()
    many = nper[nper >= 4]
    if len(many):
        LOG.warn(f"10년간 소속 법인이 4개 이상인 인물 {len(many)}명 — 동명이인이 뭉쳤을 "
                 f"가능성이 있습니다(5개 초과는 사실상 확실). 해당 인물의 철회 사건은 "
                 f"M-EXIT 로 과잉 판정되어 신호가 보수적으로 약해지는 방향입니다.")
    return A, n_moves, borderline


# ── 무결성 감사 ─────────────────────────────────────────────────────────────────────────────
def audit_linkage(rep: "pd.DataFrame", A: "pd.DataFrame", L: "pd.DataFrame"):
    """★ '리포트와 식별된 애널리스트가 제대로 연결되었는지 한눈에'."""
    LOG.banner("원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출한다. 숫자가 낮으면 그대로 보고한다.")
    if rep is None or rep.empty:
        LOG.warn("리포트 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if L is not None and len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()

    rows = []
    for y, g in r.groupby("year"):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g.loc[g['has_analyst'], 'report_uid'].nunique()):,}"])
    LOG.table(rows, ["연도", "리포트", "애널연결", "연결률", "종목코드", "코드율", "유효(연결∧코드)"],
              ["c", "r", "r", "r", "r", "r", "r"])

    src = r.groupby("source").agg(n=("report_uid", "size"), analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%", f"{100*s['code']:.1f}%"]
               for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "종목코드율"], ["l", "r", "r", "r"],
              title="다중소스 원장 연결 — 어느 소스가 무엇을 채웠는가 "
                    "('hankyung+naver' 는 두 소스가 같은 리포트로 병합된 건)")

    if L is not None and len(L):
        mth = L.groupby("link_method").agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "리포트 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 (list_field=한경 작성자컬럼 0.98)")

    if A is not None and len(A):
        bro = (A.groupby("broker_name").agg(analysts=("analyst_id", "nunique"),
                                            reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        LOG.table([[b, f"{int(bro.loc[b, 'analysts']):,}", f"{int(bro.loc[b, 'reports']):,}"]
                   for b in bro.index[:25]],
                  ["증권사", "애널리스트 수", "리포트 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 전체 증권사 {len(bro)}개")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source").size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없습니다.")


# ── Phase 0 데이터 실현가능성 게이트 (§3) ───────────────────────────────────────────────────
def phase0_gate(rep: "pd.DataFrame", L: "pd.DataFrame") -> dict:
    """명세 §3: 표본 3개월 × 300건에서 analyst_id 확보율을 측정하고 진행 방식을 판정한다.

      ≥70%    → 정상 진행 (애널리스트 단위)
      40~70%  → 진행하되 §6.7 결측 민감도 분석 필수
      <40%    → **애널리스트 단위 포기.** 단위를 broker_id × sector 로 격하하고
                신호를 '하우스 단위 주의 재배분'으로 재정의. 모든 산출물 최상단에 폴백 명시.
    """
    res = {"rate": np.nan, "mode": "ANALYST", "samples": [], "note": ""}
    if rep is None or rep.empty:
        res.update(mode="HOUSE", note="리포트 원장이 비어 판정 불가 — 가장 보수적으로 하우스 단위")
        return res
    linked = set(L["report_uid"]) if L is not None and len(L) else set()
    r = rep.copy()
    r["ym"] = r["pub_date"].dt.strftime("%Y-%m")
    r["ok"] = r["report_uid"].isin(linked)

    rates, rows = [], []
    for ym in PHASE0_SAMPLE_MONTHS:
        g = r[r["ym"] == ym]
        if g.empty:
            rows.append([ym, "0", "—", "표본 없음(해당 월 수집분 없음)"])
            continue
        s = g.head(PHASE0_SAMPLE_N)
        rate = float(s["ok"].mean())
        rates.append(rate)
        rows.append([ym, f"{len(s):,}", f"{100*rate:.1f}%",
                     "정상" if rate >= PHASE0_PASS else
                     ("결측 민감도 필요" if rate >= PHASE0_DEGRADE else "하우스 단위 격하")])
    # 표본 월이 하나도 없으면 전체 구간으로 대체 측정한다(판정 자체를 포기하지 않는다)
    if not rates:
        rate = float(r["ok"].mean())
        rates = [rate]
        rows.append(["전체구간(대체)", f"{len(r):,}", f"{100*rate:.1f}%", "표본월 부재로 전체 측정"])

    overall = float(np.mean(rates))
    res["rate"] = overall
    res["samples"] = rows
    if overall >= PHASE0_PASS:
        res["mode"] = "ANALYST"
        res["note"] = "애널리스트 단위로 정상 진행합니다."
    elif overall >= PHASE0_DEGRADE:
        res["mode"] = "ANALYST_IPW"
        res["note"] = ("애널리스트 단위로 진행하되 §6.7 결측 민감도 분석(로지스틱 + IPW 재추정)을 "
                       "반드시 병기합니다.")
    else:
        res["mode"] = "HOUSE"
        res["note"] = ("★ 애널리스트 단위를 포기합니다. 단위를 broker_id × sector 로 격하하고 "
                       "신호를 '하우스 단위 주의 재배분'으로 재정의합니다. 이 결과를 "
                       "애널리스트 단위 결과로 보고하지 마십시오.")

    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§3)",
               "애널리스트 식별률에 따라 분석 단위가 결정됩니다")
    LOG.table(rows, ["표본월", "표본수", "애널 식별률", "판정"], ["c", "r", "r", "l"])
    LOG.table([["종합 식별률", f"{100*overall:.1f}%"],
               ["판정 기준", f"≥{100*PHASE0_PASS:.0f}% 정상 / "
                             f"{100*PHASE0_DEGRADE:.0f}~{100*PHASE0_PASS:.0f}% IPW 병기 / "
                             f"<{100*PHASE0_DEGRADE:.0f}% 하우스 격하"],
               ["결정된 분석 단위", {"ANALYST": "애널리스트 (analyst@broker)",
                                     "ANALYST_IPW": "애널리스트 + 결측 민감도 필수",
                                     "HOUSE": "★ 하우스 (broker × sector) — 폴백"}[res["mode"]]],
               ["비고", res["note"]]],
              ["항목", "값"], ["l", "l"])
    if res["mode"] == "HOUSE":
        LOG.error("Phase 0 폴백 발동 — 이후 모든 산출물 제목에 [하우스 단위 폴백] 이 붙습니다.")
    return res
