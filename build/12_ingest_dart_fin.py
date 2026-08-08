

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무제표 / 직원현황 / 공시목록                                               ║
# ║                                                                                          ║
# ║  ★ PIT 핵심: knowledge_date = 접수일자(rcept_dt). 결산기준일이 아니다.                     ║
# ║    fnltt* 응답의 rcept_no 앞 8자리가 곧 접수일자다 → 여기서 knowledge_date 를 얻는다.       ║
# ║    rcept_no 가 없으면 법정 제출기한(분기 45일 / 사업보고서 90일)으로 보수적 추정한다.       ║
# ║    ※ 보수적 추정은 '늦게 알았다'는 방향이므로 미래누수를 만들지 않는다.                     ║
# ║                                                                                          ║
# ║  ★ 호출 예산: DART 는 일 20,000건 제한. 10년 분기 전체 재무제표는 그 몇 배다.               ║
# ║    → 콜드빌드는 며칠에 걸쳐 '이어받기'로 완성된다(§3: 콜드빌드는 4시간 예산 밖).            ║
# ║    → 남은 호출량을 실시간으로 표시하고, 한도에 닿으면 깨끗하게 멈춘 뒤 진행률을 알려준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_DAILY_LIMIT = 19_000                 # 공식 20,000 대비 여유
DART_STATEMENT_FREQ = "quarterly"         # "quarterly" | "annual"
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class DartBudget:
    """일일 호출 한도를 드라이브에 영속 기록. 재실행 시 이어받기의 근거가 된다."""

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
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.n + k > DART_DAILY_LIMIT:
                if not self.exhausted:
                    self.exhausted = True
                    LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                             f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, "
                             f"내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                return False
            self.n += k
            if self.n % 500 == 0:
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/", on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DBUDGET is not None:
        DBUDGET.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "020":
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            LOG.warn(f"DART status=020 (일일 호출한도 초과) — 수집을 중단하고 받은 만큼 "
                     f"저장합니다. 내일 재실행하면 정확히 이어받습니다.")
        elif st == "021":
            # ★ 021 은 '조회 가능한 회사 개수 초과' = 요청 1건의 배치 크기 문제이지
            #   일일 한도가 아니다. 이걸 exhausted 로 처리하면 그 시점부터 남은 전 종목의
            #   수집이 중단된다 — 한 번의 배치 실수로 그날 수집 전체가 죽는다.
            LOG.debug(f"DART status=021 (배치 크기 초과) ep={endpoint} — 이 요청만 실패 처리하고 "
                      f"나머지는 계속 진행합니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자(YYYYMMDD). 없으면 법정기한으로 보수적 추정."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


# ── 전체 재무제표 ───────────────────────────────────────────────────────────────────────────
#  ★ 비교치(전기·전전기) 컬럼을 반드시 함께 보관한다 — 이 전략의 생사가 여기 걸려 있다.
#    DART 는 어떤 재무 응답에서도 '당기'와 함께 '전기 동기'를 같이 준다.
#      · 재무상태표(BS): frmtrm_amount = 전기말 잔액
#      · 손익/현금흐름(IS/CF): thstrm_add_amount = 당기 누적, frmtrm_add_amount = 전기 누적
#    이걸 읽으면 매출증가율·자산회전율변화·운전자본발생액이 **단일 행에서** 산출된다.
#    반대로 당기금액만 읽으면 YoY 를 만들려고 'TTM(연속 4분기) → lag4' 체인을 타야 하고,
#    그 순간 연속 8분기 공시를 요구하게 된다. 분기보고서를 거르는 소형주가 흔한
#    U-MICRO 에서는 그 체인만으로 결측률이 26% 를 넘어 C14-c 로 축이 통째로 죽는다.
#    (실측 사고: i_sales 26.1% 결측 → 임계 25% 초과 → 활성 TP 0개 → C14-d 중단)
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "thstrm_add_amount",
            "frmtrm_amount", "frmtrm_q_amount", "frmtrm_add_amount",
            "bfefrmtrm_amount", "rcept_no"]


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "CFS"})
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        return None
    d = pd.DataFrame(js["list"])
    for c in _FS_KEEP:
        if c not in d.columns:
            d[c] = None
    d["corp_code"] = corp
    d["bsns_year"] = int(year)
    d["reprt_code"] = reprt
    return d[_FS_KEEP]


# ── Tier-1: 다중회사 주요계정 (배치) ────────────────────────────────────────────────────────
#   fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개까지 받는다.
#   2,500사 × 10년 × 4분기를 단건으로 받으면 100,000 호출(일 20,000 한도로 5일)이지만
#   배치로는 1,000 호출(1시간 이내)이면 끝난다. ★100배 차이다.
#   다만 '주요계정'만 오므로 B/C축이 필요로 하는 재고·매출채권·영업CF 는 없다.
#   → 헤드라인은 배치로 싹 깔고, 전체 재무제표는 우선순위대로 단건 수집해 덮어쓴다(2단 구성).
DART_MULTI_BATCH = 100
_MULTI_ACCOUNT_MAP = {
    "매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income",
    "자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity",
}


def _done_keys(cached: Optional[pd.DataFrame], label: str) -> set:
    """이미 받은 (회사, 연도, 보고서) 조합. ★비교치가 없는 옛 캐시는 '미완'으로 본다.

    ★ 왜 이 구분이 필요한가 ─────────────────────────────────────────────────────────────
      예전 버전은 당기금액만 저장했다. 그 캐시를 '완료'로 처리하면 전기 비교치가 영원히
      비고, YoY 센서가 분기 체인(연속 8분기)에 의존하게 되어 결측률이 25% 를 넘는다.
      → 비교치가 없는 조합은 재수집 대상으로 되돌린다. 단 **기존 행은 지우지 않는다**
        (드라이브 캐시 불훼손 원칙). 재수집분이 keep="last" 로 덮어쓸 뿐이다.
      배치 경로는 재수집 비용이 수백 회에 불과해 이 업그레이드가 몇 분이면 끝난다.
    """
    if cached is None or not len(cached):
        return set()
    c = cached
    key = ["corp_code", "bsns_year", "reprt_code"]
    if any(k not in c.columns for k in key):
        return set()
    if "frmtrm_amount" not in c.columns:
        LOG.warn(f"{label} 캐시 {len(c):,}행에 전기 비교치가 없습니다(구버전 형식). "
                 f"당기금액은 그대로 재사용하고, 비교치는 이번 실행에서 보강합니다.")
        return set()
    ok = c.groupby(key, observed=True)["frmtrm_amount"].transform(
        lambda s: s.notna().any() if len(s) else False)
    good = c[ok.fillna(False).astype(bool)]
    n_old = c.groupby(key, observed=True).ngroups - good.groupby(key, observed=True).ngroups \
        if len(good) else c.groupby(key, observed=True).ngroups
    if n_old > 0:
        LOG.info(f"{label} — 비교치가 없는 {n_old:,}개 조합은 재수집 대상입니다"
                 f"(기존 행은 보존됩니다).")
    return set(zip(good["corp_code"].astype(str), good["bsns_year"].astype(int),
                   good["reprt_code"].astype(str)))


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = _done_keys(cached, "DART 주요계정")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용 "
                 f"(비교치 확보 {len(done):,} 조합)")

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    corps = [str(c) for c in corp_codes]
    jobs = []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps if (c, int(y), str(r)) not in done]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), r))
    if RUN_MODE == "CACHED":
        jobs = []

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
        d["reprt_code"] = r
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건 수집이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량입니다")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사 "
           f"(호출 {len(jobs):,}회로 확보)")
    PIPE.io("OUT", "DRIVE", "dart_multi_raw", M, source="opendart fnlttMultiAcnt")
    return M


def fetch_dart_financials(corp_codes: Sequence[str], years: Sequence[int],
                          priority: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다."""
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — B축(회계품질)·C축(자원투입)·PACK-C 가 전부 비활성화됩니다. "
                 "이 전략의 핵심 입력이므로 키 입력을 강력히 권합니다.")
        return pd.DataFrame(columns=_FS_KEEP)

    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = _done_keys(cached, "DART 전체 재무제표")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART 재무 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = ([REPRT_CODES["FY"]] if DART_STATEMENT_FREQ == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    jobs = [(c, y, r) for y in sorted(years, reverse=True) for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        total_needed = len(jobs)
        LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 "
                 f"(오늘 가용 호출 {max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0)):,}건)")
        if total_needed > DART_DAILY_LIMIT:
            LOG.warn(f"필요 호출({total_needed:,})이 일일 한도({DART_DAILY_LIMIT:,})를 초과합니다. "
                     f"오늘 받을 수 있는 만큼 받고 저장합니다. "
                     f"약 {math.ceil(total_needed / DART_DAILY_LIMIT)}일에 걸쳐 콜드빌드가 완성됩니다. "
                     f"(§3 — 콜드빌드는 4시간 반복예산 밖입니다)")
        res = pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 12), desc="DART 재무제표")
        got = [d for d in res if d is not None and len(d)]
    else:
        got = []

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        LOG.warn("DART 재무 데이터를 확보하지 못했습니다.")
        return pd.DataFrame(columns=_FS_KEEP)
    fs = pd.concat(frames, ignore_index=True)
    fs = fs.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                             "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_fnltt_raw", fs, scope="shared", domain="dart", source="opendart")
    n_have = fs.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(fs) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"DART 전체 재무제표 진행률 {n_have:,}/{n_need:,} "
             f"({100*n_have/max(n_need,1):.1f}%) — 최근 연도·우선순위 종목부터 채웁니다. "
             f"재실행하면 정확히 이 지점부터 이어받습니다.")
    PIPE.io("OUT", "DRIVE", "dart_fnltt_raw", fs, source="opendart fnlttSinglAcntAll")
    return fs


def merge_financial_tiers(full: pd.DataFrame, multi: pd.DataFrame) -> pd.DataFrame:
    """Tier-2(전체 재무제표)를 우선하고, 없는 (회사, 기간)만 Tier-1(주요계정)로 메운다.

    콜드빌드가 며칠 걸리는 동안에도 매출·영업이익·순이익·자산·부채·자본은 전 종목이
    확보되어 있어 유니버스 구성과 규모 버킷(C11), R3 팩터가 즉시 동작한다."""
    if multi is None or multi.empty:
        return full if full is not None else pd.DataFrame(columns=_FS_KEEP)
    if full is None or full.empty:
        LOG.info("전체 재무제표가 아직 없어 주요계정(배치)만으로 진행합니다 — "
                 "B축의 재고·매출채권·영업CF 는 결측이므로 TP_B1/TP_B2 가 약해집니다.")
        return multi
    have = set(zip(full["corp_code"].astype(str), full["bsns_year"].astype(int),
                   full["reprt_code"].astype(str)))
    key = list(zip(multi["corp_code"].astype(str), multi["bsns_year"].astype(int),
                   multi["reprt_code"].astype(str)))
    fill = multi[[k not in have for k in key]]
    if len(fill):
        LOG.info(f"주요계정으로 보완한 (회사×기간) {fill.groupby(['corp_code','bsns_year','reprt_code']).ngroups:,}건 "
                 f"— 전체 재무제표 콜드빌드가 끝나면 자동으로 대체됩니다.")
    return pd.concat([full, fill], ignore_index=True)


# ── 계정 매핑 (한국 XBRL 계정명은 회사마다 다르다 → 정규식 다중 매칭) ────────────────────────
ACCOUNT_PATTERNS: Dict[str, Tuple[str, List[str]]] = {
    # 키:            (재무제표구분, [account_id 또는 account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$"]),
    "cogs":          ("IS", [r"CostOfSales", r"^매출원가$"]),
    "gross_profit":  ("IS", [r"GrossProfit", r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense", r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense", r"경상(연구)?개발비", r"^연구개발비"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense", r"법인세비용"]),
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세(비용)?차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    # ★ 아래 5개는 '다중회사 주요계정(fnlttMultiAcnt)' 이 주는 전부다. 배치 1회로 100사가
    #   오므로 전 종목·전 분기를 예산 안에서 확보할 수 있는 유일한 계정군이다.
    #   운전자본 발생액(유동자산−유동부채 변화)과 자본잠식 판정이 여기서 나온다.
    "current_assets":  ("BS", [r"ifrs-full_CurrentAssets$", r"^유동자산$"]),
    "noncur_assets":   ("BS", [r"ifrs-full_NoncurrentAssets$", r"^비유동자산$"]),
    "current_liab":    ("BS", [r"ifrs-full_CurrentLiabilities$", r"^유동부채$"]),
    "noncur_liab":     ("BS", [r"ifrs-full_NoncurrentLiabilities$", r"^비유동부채$"]),
    "retained":        ("BS", [r"ifrs-full_RetainedEarnings", r"^이익잉여금", r"^결손금"]),
    "capital_stock":   ("BS", [r"ifrs-full_IssuedCapital$", r"^자본금$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment", r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssetsOtherThanGoodwill", r"^무형자산$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents", r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities", r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities", r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment", r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense", r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid", r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares", r"자기주식의?\s*취득"]),
    "debt_raise":    ("CF", [r"ProceedsFromBorrowings", r"차입금의?\s*증가", r"사채의?\s*발행"]),
}
_SJ_MAP = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# ★ 손익·현금흐름 성격의 전 계정. 빠뜨리면 <계정>_ttm 컬럼이 아예 생성되지 않고,
#   그걸 쓰는 팩이 실데이터 실행에서만 터진다(합성 스모크는 통과한다).
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy", "debt_raise",
              "tax_expense", "pretax_income", "other_income"]

# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼 전체 목록.
# attach_fundamentals 가 이 목록으로 스키마를 계약적으로 보장한다 — 수집이 얼마나 실패하든
# 패널의 컬럼 집합은 항상 같아야 한다. 그래야 "어떤 실행에선 있고 어떤 실행엔 없는" 축이
# 사라지고, 결측은 결측대로 조용히가 아니라 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_PATTERNS)
                    + [f"{k}{s}" for k in ACCOUNT_PATTERNS for s in ("_cm", "_pv", "_pc")]
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


#  값 필드 → 컬럼 접미사.  <항목> = 당기금액 · <항목>_cm = 당기누적 · <항목>_pv = 전기
#  · <항목>_pc = 전기누적.   BS 는 누적 개념이 없으므로 _cm 은 당기말, _pv 는 전기말이다.
_AMT_FIELDS = {"_cur": "thstrm_amount",     "_cum": "thstrm_add_amount",
               "_pv":  "frmtrm_amount",     "_pq":  "frmtrm_q_amount",
               "_pc":  "frmtrm_add_amount"}
_AMT_SUFFIX = {"_cur": "", "_cum": "_cm", "_pv": "_pv", "_pq": "_pq", "_pc": "_pc"}
# 비교치까지 포함한 계약 스키마. 어떤 실행에서도 이 컬럼들은 반드시 존재해야 한다.
COMPARATIVE_SUFFIXES = ["_cm", "_pv", "_pq", "_pc"]


def _detect_cumulative(W: pd.DataFrame) -> Tuple[bool, float, int]:
    """분기보고서의 손익금액이 '누적'인지 '3개월 단독'인지 데이터로 판정한다.

    ★ 추측하지 않는 이유 ────────────────────────────────────────────────────────────────
      DART 응답은 엔드포인트(단건/다중)와 회사에 따라 당기금액이 누적일 수도, 3개월
      단독일 수도 있다. 코드가 한쪽을 가정하면 다른 쪽에서 **에러 없이 값만 틀린다**.
      누적을 3개월로 오인하면 매출이 계단식으로 튀어 성장률이 통째로 가짜가 되고,
      3개월을 누적으로 오인하면 차분이 음수·양수를 오가며 TTM 이 무의미해진다.
    판별식: 사업보고서(연간) 대비 반기보고서 금액의 비율 중앙값.
      · 누적이면 반기 ≈ 연간의 0.5
      · 3개월 단독이면 반기(=2분기 단독) ≈ 연간의 0.25
    """
    try:
        r = W[["corp_code", "bsns_year", "reprt_code", "revenue"]].dropna(subset=["revenue"])
        piv = r.pivot_table(index=["corp_code", "bsns_year"], columns="reprt_code",
                            values="revenue", aggfunc="first")
        h1, fy = REPRT_CODES["H1"], REPRT_CODES["FY"]
        if h1 not in piv.columns or fy not in piv.columns:
            return True, float("nan"), 0
        a, b = piv[h1], piv[fy]
        ratio = (a / b).where((b > 0) & (a > 0))
        ratio = ratio[(ratio > 0.05) & (ratio < 1.5)]
        n = int(ratio.notna().sum())
        if n < 50:
            return True, (float(ratio.median()) if n else float("nan")), n
        med = float(ratio.median())
        return (med > 0.375), med, n
    except Exception:
        return True, float("nan"), 0


def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다.

    ★ 당기금액뿐 아니라 **전기 비교치**까지 함께 실어 나른다. YoY 를 만들려고 분기 체인을
      타지 않아도 되게 하기 위해서다(_FS_KEEP 주석 참조).
    """
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()

    def _num(name: str) -> pd.Series:
        if name not in d.columns:
            return pd.Series(np.nan, index=d.index, dtype="float64")
        s = (d[name].astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("−", "-", regex=False)
                    .str.strip())
        s = s.where(~s.isin(["", "-", "nan", "None", "NaN"]))
        return pd.to_numeric(s, errors="coerce")

    for k, src in _AMT_FIELDS.items():
        d[k] = _num(src)
    # 당기금액이 비어 있고 누적만 있는 행(일부 CF 계정)을 버리지 않는다.
    d["_cur"] = d["_cur"].where(d["_cur"].notna(), d["_cum"])
    d = d.dropna(subset=["_cur"])
    if d.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
    _vals = list(_AMT_FIELDS)
    for key, (sj, pats) in ACCOUNT_PATTERNS.items():
        sjs = _SJ_MAP.get(sj, (sj,))
        sub = d[d["sj_div"].astype(str).isin(sjs)]
        if sub.empty:
            continue
        rx = re.compile("|".join(pats), re.I)
        hit = sub[sub["account_id"].str.contains(rx, na=False) |
                  sub["account_nm"].str.contains(rx, na=False)]
        if hit.empty:
            continue
        # 같은 항목·같은 연결범위에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다.
        hit = (hit.assign(_a=hit["_cur"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code", "fs_div"],
                                   keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "fs_div", "rcept_no", "item"] + _vals])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)

    # ── ★ 연결범위(연결/별도) 고정 — 보고서 단위로 하나만 쓴다 ──────────────────────────
    #   고정하지 않으면 항목마다 연결범위가 뒤섞인다. 실제로 일어나는 조합이다:
    #     매출액 → 배치(주요계정)의 연결(CFS),  재고자산 → 단건(전체 재무제표)의 별도(OFS)
    #   이러면 매출채권회전일수 = 별도 매출채권 ÷ 연결 매출 이 되어 **의미가 없는 수**가 된다.
    #   지주회사·자회사 비중이 큰 기업일수록 오차가 크고, 그 오차가 해마다 바뀌면
    #   i_sales 가 그 변화를 '성장'으로 읽는다. 에러는 나지 않는다 — 값만 조용히 틀린다.
    #   → (회사, 연도, 보고서)별로 **항목을 가장 많이 채우는 연결범위**를 골라 그것만 쓴다.
    #     동수면 연결(CFS) 우선. 단건이 전체 계정을 준 보고서는 자연히 그쪽이 이긴다.
    _key = ["corp_code", "bsns_year", "reprt_code"]
    L["fs_div"] = L["fs_div"].astype(str)
    _cov = (L.groupby(_key + ["fs_div"], observed=True)["item"].nunique()
             .reset_index(name="_n"))
    _cov["_pref"] = (_cov["fs_div"] != "CFS").astype(int)
    _cov = _cov.sort_values(_key + ["_n", "_pref"], ascending=[True] * 3 + [False, True])
    _win = _cov.drop_duplicates(_key, keep="first")[_key + ["fs_div"]]
    _n0 = len(L)
    L = L.merge(_win, on=_key + ["fs_div"], how="inner")
    if _n0 - len(L) > 0:
        LOG.debug(f"연결범위 고정 — 보고서당 한 기준만 채택해 {_n0-len(L):,}행을 제외했습니다 "
                  f"(연결/별도 혼용 방지).")
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values=_vals, aggfunc="first")
    W.columns = [f"{item}{_AMT_SUFFIX[val]}" for val, item in W.columns]
    W = W.reset_index()
    # ★ knowledge_date 는 '실제로 채택된 금액이 공시된 시점' 이상이어야 한다.
    #   first()(=가장 이른 접수번호)를 쓰면, 정정공시로 바뀐 금액을 채택해 놓고 날짜만
    #   원공시 날짜를 붙이게 된다 → 그 차이만큼 미래를 미리 아는 셈이다(C1 위반).
    #   max() 는 채택 후보 중 가장 늦은 접수일이므로 어떤 경우에도 누수가 없다(보수적).
    rc = (L.groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .max().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"], kind="stable").reset_index(drop=True)

    # ★ 계약 스키마 — 당기·당기누적·전기·전기누적 네 벌이 항상 존재해야 한다.
    #   pivot 결과에 그 계정이 없으면 컬럼 자체가 안 생겨 실행마다 축이 달라진다.
    for _k in ACCOUNT_PATTERNS:
        for _s in [""] + COMPARATIVE_SUFFIXES:
            if _k + _s not in W.columns:
                W[_k + _s] = np.nan

    # ── 분기 공시금액이 누적인지 3개월 단독인지 '데이터로' 판정 ──────────────────────────
    is_cum, med_ratio, n_ratio = _detect_cumulative(W)
    LOG.table([["분기 손익금액", "누적(YTD)" if is_cum else "3개월 단독",
                (f"{med_ratio:.3f}" if med_ratio == med_ratio else "표본없음"),
                f"{n_ratio:,}건", "반기/연간 ≈0.5 이면 누적, ≈0.25 면 3개월"]],
              ["판정 대상", "결론", "비율 중앙값", "표본", "판별 근거"],
              ["l", "c", "r", "r", "l"],
              title="분기 공시금액 누적여부 자동판정 — 가정하지 않고 실측으로 정한다")
    if n_ratio < 50:
        LOG.info("표본이 적어 기본값(누적)을 씁니다. 사업보고서·분기보고서가 함께 쌓이면 "
                 "다음 실행에서 실측으로 재판정합니다.")

    gk = ["corp_code", "bsns_year"]
    # 연내 누적합을 인정하는 조건: q 가 1..k 로 빠짐없이 이어지고, 값도 전부 존재할 것.
    seq_ok = (W.groupby(gk, observed=True).cumcount() + 1) == W["q"]
    # 전기금액을 '전기 누적'으로 대체해도 되는 행 (스칼라 bool 을 where 에 넘기면
    # "Array conditional must be same shape as self" 로 죽는다 — 계약검정이 잡아냈다)
    _pv_usable = (pd.Series(True, index=W.index) if is_cum else (W["q"] >= 4))
    for c in FLOW_ITEMS:
        cm, pc, pv = f"{c}_cm", f"{c}_pc", f"{c}_pv"
        cur = W[c]
        if is_cum:
            cum = cur
        else:
            # 3개월 단독 → 연내 누적합. 단 사업보고서(q=4)는 언제나 '연간' 이므로 그대로 쓴다.
            run = W.groupby(gk, observed=True)[c].cumsum()
            nn = W[c].notna().groupby([W["corp_code"], W["bsns_year"]], observed=True).cumsum()
            ok = seq_ok & (nn == W["q"])
            cum = pd.Series(np.where(W["q"] >= 4, cur, run.where(ok)), index=W.index)
        W[cm] = W[cm].where(W[cm].notna(), cum)
        # 전기 누적: 명시 컬럼(frmtrm_add_amount) 우선.
        # ★ 없을 때 전기금액으로 대체할 수 있는 조건이 두 가지다:
        #     ① 분기 공시가 누적 형식이면 전기금액도 누적이다.
        #     ② **사업보고서(q=4)는 형식과 무관하게 전기금액이 곧 '전기 연간'이다.**
        #   ②를 빠뜨리면 연 1회만 공시하는 기업(U-MICRO 에 흔하다)의 전기 매출이 통째로
        #   비어 i_sales 가 결측이 된다 — 실제로 합성 스모크에서 i_sales 31.4% 결측으로
        #   C14-c 에 걸렸다. 데이터가 아니라 이 한 줄이 원인이었다.
        W[pc] = W[pc].where(W[pc].notna(), W[pv].where(_pv_usable))
    # 재무상태표 항목은 누적 개념이 없다 — 당기말 잔액이 곧 _cm 이다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in FLOW_ITEMS:
            W[f"{_k}_cm"] = W[f"{_k}_cm"].where(W[f"{_k}_cm"].notna(), W[_k])
            W[f"{_k}_pc"] = W[f"{_k}_pc"].where(W[f"{_k}_pc"].notna(), W[f"{_k}_pv"])

    # ── 누적 → 분기 단독 → TTM ────────────────────────────────────────────────────────
    #   직전 분기가 실제로 존재할 때만 차분한다.
    #   (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in FLOW_ITEMS:
        cm = f"{c}_cm"
        prev = W.groupby(gk, observed=True)[cm].shift(1)
        W[c + "_q"] = np.where(W["q"] == 1, W[cm],
                               np.where(contiguous, W[cm] - prev, np.nan))
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])
    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' 플래그 ─────────────────────────────────────
    #   ★ 여기서 만드는 이유: 연속성은 분기 관측을 세야 하는데, 월 패널에서 세면
    #     같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도 정답이 아니다. 분기 프레임은
    #     관측당 정확히 한 행이고 이미 (corp_code, bsns_year, q) 로 정렬돼 있다.
    #     as-of 결합이 이 플래그를 C1 게이트웨이 그대로 실어 나른다.
    #   min_periods=3 — 제출분이 3개 미만이면 NaN(=거부하지 않음). 근거 없는 제외 금지.
    _bad_q = ((col(W, "net_income_ttm") > 0) &
              (col(W, "cfo_ttm") < 0.5 * col(W, "net_income_ttm"))).astype(float)
    W["v2_bad_3q"] = (_bad_q.groupby(W["corp_code"], observed=True)
                            .transform(lambda s: s.rolling(3, min_periods=3).min()))

    _missing = [k for k in ACCOUNT_PATTERNS if W[k].notna().sum() == 0]
    if _missing:
        LOG.warn(f"DART 재무에서 한 건도 매칭되지 않은 계정 {len(_missing)}개: "
                 f"{_missing[:8]}{'...' if len(_missing) > 8 else ''} — "
                 f"해당 계정을 쓰는 지표는 전부 결측이 됩니다(0으로 채우지 않음). "
                 f"ACCOUNT_PATTERNS 정규식이 이 회사들의 계정명과 안 맞을 수 있습니다.")
    n_ttm = int(W["revenue_ttm"].notna().sum()) if "revenue_ttm" in W.columns else 0
    if len(W) and n_ttm / len(W) < 0.35:
        LOG.warn(f"TTM 산출률이 {100*n_ttm/len(W):.0f}% 로 낮습니다. 분기보고서가 결측인 기업이 "
                 f"많다는 뜻이며(중소형주에서 흔함), 해당 종목은 B/C축이 결측 처리됩니다. "
                 f"DART_STATEMENT_FREQ='quarterly' 콜드빌드가 아직 미완이라면 이어받기를 계속하세요.")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 재무 정제 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(knowledge_date = 접수일자 기준, 누적→분기 차분 완료)")
    PIPE.io("OUT", "MEM", "dart_financials_tidy", W)
    return downcast(W)


# ── 직원현황 (θ_N, TP_C2) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(c, y) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list):
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 각 조합은 서로소이므로
        #   합산이 맞지만, 일부 기업은 '합계/계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   또 jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이므로 아예 쓰지 않는다.
        for col in ("fo_bbm", "sexdstn"):
            if col in d.columns:
                d = d[~d[col].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        num = lambda s: pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                                      errors="coerce")
        emp = num(d.get("sm", pd.Series(dtype=object))).sum(skipna=True) if "sm" in d.columns else np.nan
        pay = num(d.get("fyer_salary_totamt", pd.Series(dtype=object))).sum(skipna=True) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "employees": float(emp),
                "payroll": float(pay), "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    # ★ E.get("rcept_no", "") 는 컬럼이 없으면 '문자열'을 돌려주고, zip 이 그걸 글자 단위로
    #   훑어 knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    E["knowledge_date"] = [_knowledge_from_rcept(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(E["rcept_no"], E["bsns_year"])]
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart", source="opendart empSttus")
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E


# ── 공시목록 스윕 (시장 전체를 날짜로 훑는다 — 회사별 호출보다 수십 배 싸다) ──────────────────
DISCLOSURE_PATTERNS = {
    "treasury_acq":  r"자기주식\s*취득",
    "treasury_disp": r"자기주식\s*처분",
    "treasury_canc": r"자기주식\s*소각|이익소각",
    "dividend":      r"(현금|현물)?\s*[·ㆍ]?\s*배당\s*결정|결산배당|중간배당",
    "rights_issue":  r"유상증자",
    "cb_issue":      r"전환사채",
    "bw_issue":      r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion": r"감사보고서",
}


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    have_months = set()
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        todo = []

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)
    DISCLOSURE_TYPES = ("A", "B")            # A=정기공시(사업/반기/분기보고서), B=주요사항보고

    def _one(m):
        rows = []
        for ty in DISCLOSURE_TYPES:
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})
                if not js or not isinstance(js.get("list"), list) or not js["list"]:
                    break
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
                            "report_nm", "flr_nm", "corp_cls") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures", D, scope="shared", domain="dart", source="opendart list.json")
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")     # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — 이벤트 분류: " +
           ", ".join(f"{k}={int((D['event']==k).sum()):,}" for k in DISCLOSURE_PATTERNS if (D['event']==k).any()))
    PIPE.io("OUT", "DRIVE", "dart_disclosures", D, source="opendart list.json")
    return D
