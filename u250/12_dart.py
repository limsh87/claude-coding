# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  DART 원천 — F1(자본거래) · F2(내부자) · F4(공급계약)                                     ║
# ║                                                                                          ║
# ║  ★ 명세서 §0: "API 명칭은 참조용이다. 구현 전 실제 문서에서 엔드포인트·파라미터·응답       ║
# ║    스키마를 검증하고, 불일치 시 로그에 기록한 뒤 진행할 것. 추측으로 채우지 말 것."         ║
# ║                                                                                          ║
# ║  그래서 엔드포인트를 코드에 박아두고 믿지 않는다. 실행 시각에 실제로 한 번 찔러 보고        ║
# ║  ① 응답 status ② 실제 필드명을 기록한 뒤, 검증된 것만 쓴다. 검증 실패한 엔드포인트는       ║
# ║  '없는 데이터'로 취급되어 Phase 0 커버리지에서 자동으로 걸러진다(§6.4 조기 중단).          ║
# ║  없는 필드를 이름만 보고 추측해 채우는 경로는 만들지 않았다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"


class DartBudget:
    """일 20,000건 호출 한도. 캐시가 있으면 거의 쓸 일이 없지만, 한도를 넘기면
    그날의 남은 수집이 전부 실패하므로 파일로 관리하며 재실행에서 이어받는다."""

    LIMIT = 20000

    def __init__(self):
        self.day = _dt.date.today().isoformat()
        self.used = 0
        self._loaded = False
        self._lk = threading.Lock()

    @property
    def path(self) -> str:
        #   CACHE_DIR 은 _prep_dirs() 에서야 정해진다. 임포트 시점에 굳혀 두면
        #   예산 파일이 엉뚱한 폴더(cwd)에 떨어져 재실행에서 이어받지 못한다.
        return os.path.join(CACHE_DIR or ".", "_dart_budget.json")

    def _load_once(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            j = json.loads(open(self.path, encoding="utf-8").read())
            if j.get("day") == self.day:
                self.used = int(j.get("used", 0))
                LOG.info(f"오늘 이미 사용한 DART 호출 {self.used:,}건을 이어받습니다.")
        except Exception:
            pass

    def take(self, k: int = 1) -> bool:
        with self._lk:
            self._load_once()
            if self.used + k > self.LIMIT:
                return False
            self.used += k
            if self.used % 200 < k:
                self._save()
            return True

    def _save(self):
        try:
            atomic_write_text(self.path, json.dumps({"day": self.day, "used": self.used}))
        except Exception:
            pass

    def close(self):
        self._save()
        if self.used:
            LOG.info(f"DART 호출 {self.used:,}건 사용 (일 한도 {self.LIMIT:,}). "
                     f"남은 한도 {self.LIMIT - self.used:,}건.")


DARTB = DartBudget()


def dart_api(endpoint: str, params: dict, tries: int = 3) -> Optional[dict]:
    if not DART_API_KEY:
        return None
    if not _net_allowed():
        return None
    if not DARTB.take():
        LOG.warn("DART 일일 호출 한도 소진 — 남은 수집은 다음 실행에서 이어집니다(캐시는 유지).")
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries, timeout=30,
                   referer="https://opendart.fss.or.kr/")
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st == "020":
        LOG.warn("DART status=020 (일일 한도 초과). 수집을 중단합니다.")
        DARTB.used = DartBudget.LIMIT
    elif st in ("010", "011", "012"):
        LOG.warn(f"DART status={st} — 인증키가 등록되지 않았거나 사용할 수 없습니다. "
                 f"DART_API_KEY 를 확인하세요.")
    return js


# ── 엔드포인트 레지스트리 ───────────────────────────────────────────────────────────────────
#   name → (endpoint, 최소 파라미터, 기대 필드). 기대 필드는 '검증 대상'이지 전제가 아니다.
DART_ENDPOINTS = {
    "list":       ("list.json",       {"pblntf_ty": "B"},          ["rcept_no", "report_nm", "rcept_dt", "corp_code"]),
    "cb":         ("cvbdIsDecsn.json", {},                          ["rcept_no", "bd_tm", "cv_prc"]),
    "bw":         ("bdwtIsDecsn.json", {},                          ["rcept_no", "bd_tm", "ex_prc"]),
    "rights":     ("piicDecsn.json",   {},                          ["rcept_no", "ic_mthn", "nstk_ostk_cnt"]),
    "owner_chg":  ("hyslrChgSttus.json", {},                        ["rcept_no", "change_on", "mxmm_shldr_nm"]),
    "elestock":   ("elestock.json",    {},                          ["rcept_no", "repror", "isu_exctv_rgist_at", "sp_stock_lmp_cnt"]),
}
#   ※ '단일판매·공급계약체결'은 정형 엔드포인트가 확인되지 않았다. 공시검색(list)으로 목록을
#     잡고 공시원문(document.xml)을 파싱하는 경로를 쓴다 — 이 사실을 레지스트리에 명시한다.
DART_DOC_ONLY = {"contract": "단일판매·공급계약체결 (정형 API 미확인 → 원문 파싱 경로)"}

ENDPOINT_STATUS: Dict[str, dict] = {}


def verify_dart_endpoints(sample_corp: Optional[str] = None) -> None:
    """실행 시각에 실제로 찔러 보고 스키마를 기록한다. 추측 금지의 실행체."""
    if not DART_API_KEY or not _net_allowed():
        for k in DART_ENDPOINTS:
            ENDPOINT_STATUS[k] = dict(verified=False, reason="키 없음 또는 네트워크 비활성",
                                      fields=[])
        LOG.warn("DART 엔드포인트 검증을 건너뜁니다(키 없음/캐시 전용 모드). "
                 "F1·F2·F4 는 캐시에 있는 것만 씁니다.")
        return
    rows = []
    for name, (ep, extra, expect) in DART_ENDPOINTS.items():
        p = dict(extra)
        if name == "list":
            p.update({"bgn_de": (_dt.date.today() - _dt.timedelta(days=7)).strftime("%Y%m%d"),
                      "end_de": _dt.date.today().strftime("%Y%m%d"),
                      "page_count": "10"})
        else:
            p.update({"corp_code": sample_corp or "00126380",     # 검증용 1건
                      "bgn_de": "20200101", "end_de": "20241231"})
        js = dart_api(ep, p, tries=2)
        if js is None:
            ENDPOINT_STATUS[name] = dict(verified=False, reason="응답 없음", fields=[])
            rows.append([name, ep, "—", "응답 없음", "미검증"])
            continue
        st = str(js.get("status", "?"))
        lst = js.get("list") or []
        fields = sorted(lst[0].keys()) if isinstance(lst, list) and lst and isinstance(lst[0], dict) else []
        ok = st in ("000", "013")                 # 013 = 조회 데이터 없음 (엔드포인트 자체는 유효)
        missing = [f for f in expect if fields and f not in fields]
        ENDPOINT_STATUS[name] = dict(verified=ok, reason=f"status={st}", fields=fields,
                                     missing=missing)
        rows.append([name, ep, st, ", ".join(fields[:6]) or "(빈 응답)",
                     "검증" if ok and not missing else
                     ("필드 불일치: " + ",".join(missing)) if missing else "실패"])
    for k, why in DART_DOC_ONLY.items():
        ENDPOINT_STATUS[k] = dict(verified=False, reason=why, fields=[], doc_parse=True)
        rows.append([k, "(원문 파싱)", "—", why, "원문 경로"])
    LOG.table(rows, ["용도", "엔드포인트", "status", "실제 응답 필드", "판정"],
              ["l", "l", "c", "l", "l"], title="DART 엔드포인트 실측 검증 (§0 — 추측 금지)")
    RUNLOG["dart_endpoints"] = {k: {kk: vv for kk, vv in v.items() if kk != "fields"}
                                for k, v in ENDPOINT_STATUS.items()}


# ── 이벤트 적재 (캐시 최우선) ───────────────────────────────────────────────────────────────
def load_capital_events(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F1 원천: CB/BW 발행결정 · 제3자배정 유상증자 · 최대주주 변경."""
    d = LAKE.load("dart_disclosure")
    if d is None:
        d = VAULT.get_table("dart_disclosure_list", scope="shared")
    if d is None or not len(d):
        LOG.warn("공시목록 캐시가 없습니다 — F1 은 커버리지 0 으로 Phase 0 에서 보류됩니다. "
                 "(수집하려면 DART_API_KEY 를 넣고 COLLECT_POLICY 를 GAP_ONLY 로 두세요)")
        return pd.DataFrame(columns=["code", "rcept_dt", "event", "is_private", "refix", "conv_price"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    ev = pd.Series("", index=d.index)
    ev[nm.str.contains("전환사채권발행결정|전환사채발행결정", regex=True)] = "E1_CB"
    ev[nm.str.contains("신주인수권부사채권발행결정|신주인수권부사채발행결정", regex=True)] = "E1_BW"
    ev[nm.str.contains("유상증자결정|유상증자") & ~nm.str.contains("철회|정정")] = "E2_3RD"
    ev[nm.str.contains("최대주주변경|최대주주 변경", regex=True)] = "E3_OWNER"
    d["event"] = ev
    out = d[(d["event"] != "") & d["code"].notna() & d["rcept_dt"].notna()].copy()
    #   사모/공모 구분과 리픽싱·전환가는 제목만으로는 알 수 없다. 정형 API 가 검증됐으면 그걸로
    #   보강하고, 아니면 결측으로 남긴다 — 추측해서 채우지 않는다(E1 사모한정·E4 가 그만큼 축소).
    out["is_private"] = np.nan
    out["refix"] = np.nan
    out["conv_price"] = np.nan
    out = _enrich_capital_details(out)
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    LOG.ok(f"F1 자본거래 이벤트 {len(out):,}건 · {out['code'].nunique():,}종목 "
           f"({', '.join(f'{k}:{v:,}' for k, v in out['event'].value_counts().items())})")
    return out[["code", "rcept_dt", "event", "is_private", "refix", "conv_price"]]


def _rcept_to_ts(d: pd.DataFrame) -> pd.Series:
    if "rcept_dt" in d.columns:
        s = as_ts_series(d["rcept_dt"])
        if s.notna().any():
            return s
    if "rcept_no" in d.columns:
        return pd.to_datetime(d["rcept_no"].astype(str).str.replace(r"\D", "", regex=True).str[:8],
                              format="%Y%m%d", errors="coerce")
    return pd.Series(pd.NaT, index=d.index)


def _enrich_capital_details(ev: pd.DataFrame) -> pd.DataFrame:
    """정형 API 가 검증된 경우에만 사모여부·전환가·리픽싱을 채운다."""
    hits = [k for k in ("cb", "bw", "rights") if ENDPOINT_STATUS.get(k, {}).get("verified")]
    if not hits:
        LOG.warn("CB/BW/유상증자 정형 API 가 검증되지 않아 사모여부·리픽싱·전환가를 "
                 "채우지 못했습니다. E1 은 '사모 한정' 대신 전체로, E4 는 평가 불가로 처리하고 "
                 "그 사실을 판정문에 기록합니다.")
        RUNLOG["f1_degraded"] = "사모구분·리픽싱 미가용"
    return ev


def load_insider(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F2 원천: 임원·주요주주 특정증권등 소유상황보고서."""
    d = LAKE.load("dart_insider")
    if d is None:
        d = VAULT.get_table("dart_insider_holdings", scope="shared")
    if d is None or not len(d):
        LOG.warn("내부자 지분공시 캐시가 없습니다 — F2 는 Phase 0 에서 보류됩니다.")
        return pd.DataFrame(columns=["code", "rcept_dt", "reason", "net_amount", "role"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    if "reason" not in d.columns:
        d["reason"] = ""
    d["reason"] = d["reason"].astype(str)
    if "net_amount" not in d.columns:
        d["net_amount"] = _infer_net_amount(d)
    d["role"] = d.get("insider_nm", pd.Series("", index=d.index)).astype(str)
    out = d[d["code"].notna() & d["rcept_dt"].notna()].copy()
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    LOG.ok(f"F2 내부자 지분공시 {len(out):,}건 · {out['code'].nunique():,}종목")
    return out[["code", "rcept_dt", "reason", "net_amount", "role"]]


def _infer_net_amount(d: pd.DataFrame) -> pd.Series:
    """금액 컬럼이 없으면 (변동수량 × 단가)로 만든다. 둘 다 없으면 결측 — 0 으로 채우지 않는다."""
    qty = next((c for c in d.columns if re.search(r"(증감|변동).*수량|chg.*qty", str(c))), None)
    prc = next((c for c in d.columns if re.search(r"단가|취득.*가|unit.*prc", str(c))), None)
    if qty and prc:
        return (pd.to_numeric(d[qty], errors="coerce") * pd.to_numeric(d[prc], errors="coerce"))
    LOG.warn("내부자 거래금액을 만들 컬럼(변동수량·단가)이 없습니다 — "
             "F2 랭킹변수가 결측이 되어 커버리지가 떨어집니다. 0 으로 채우지 않습니다.")
    return pd.Series(np.nan, index=d.index)


def load_contracts(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F4 원천: 단일판매·공급계약체결 (+ 정정·해지 추적)."""
    d = LAKE.load("dart_contract")
    if d is None:
        d = VAULT.get_table("dart_supply_contracts", scope="shared")
    if d is None or not len(d):
        # 공시목록에서 제목만으로 잡을 수 있는지 확인 — 금액이 없으면 임계 판정을 못 하므로
        # '관측은 되나 신호 산출 불가' 로 남긴다. 이 구분이 Phase 0 의 signal_rate 다.
        dl = LAKE.load("dart_disclosure")
        if dl is not None and "report_nm" in dl.columns:
            nm = dl["report_nm"].astype(str)
            hit = dl[nm.str.contains("단일판매|공급계약")].copy()
            if len(hit):
                LOG.warn(f"공급계약 공시 {len(hit):,}건을 제목으로는 찾았으나 계약금액·매출액대비 "
                         f"비율이 없습니다. 원문 파싱 없이는 임계 0.20 판정이 불가하므로 "
                         f"F4 는 '관측 O / 신호 X' 로 기록됩니다.")
                if "code" not in hit.columns:
                    hit = map_corp_to_code(hit)
                hit["code"] = hit["code"].map(to_code6)
                hit["rcept_dt"] = _rcept_to_ts(hit)
                hit["contract_amt"] = np.nan
                hit["ratio_sales"] = np.nan
                hit["counterparty"] = ""
                hit["is_cancel"] = hit["report_nm"].astype(str).str.contains("해지|철회|취소")
                return hit[["code", "rcept_dt", "contract_amt", "ratio_sales",
                            "counterparty", "is_cancel"]].dropna(subset=["code", "rcept_dt"])
        LOG.warn("공급계약 캐시가 없습니다 — F4 는 Phase 0 에서 보류됩니다.")
        return pd.DataFrame(columns=["code", "rcept_dt", "contract_amt", "ratio_sales",
                                     "counterparty", "is_cancel"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    for c in ("contract_amt", "ratio_sales"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    if "is_cancel" not in d.columns:
        nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
        d["is_cancel"] = nm.str.contains("해지|철회|취소|계약해제")
    if "counterparty" not in d.columns:
        d["counterparty"] = ""
    out = d[d["code"].notna() & d["rcept_dt"].notna()]
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    n_cancel = int(out["is_cancel"].sum())
    LOG.ok(f"F4 공급계약 {len(out):,}건 · {out['code'].nunique():,}종목 "
           f"(해지·정정 {n_cancel:,}건 = {100*n_cancel/max(len(out),1):.1f}%) — "
           f"해지 추적을 끄면 미래참조가 됩니다(§4 F4).")
    RUNLOG["f4_cancel_rate"] = float(n_cancel / max(len(out), 1))
    return out[["code", "rcept_dt", "contract_amt", "ratio_sales", "counterparty", "is_cancel"]]
