
# ────────────────────────────────────────────────────────────────────────────────────────
#  L1-C  DART — 재무제표 / 직원현황 / 공시목록
#  ★ PIT 핵심: knowledge_date = 접수일자(rcept_dt). 결산기준일이 아니다.
#  ★ 호출 예산: DART 는 일 20,000건 제한. 10년 분기 전체 재무제표는 그 몇 배다.
# ────────────────────────────────────────────────────────────────────────────────────────

DART_BASE = "https://opendart.fss.or.kr/api/"
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
    """DART 일일 호출 예산 — **상한을 하드코딩하지 않고 실시간으로 추적·학습한다.**
    ★ 왜 19,000 같은 상수를 박으면 안 되는가:
    """

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0                       # 오늘 사용한 호출 수 (우리가 센 것)
        self.exhausted = False
        self.learned_limit: Optional[int] = None   # 서버가 실제로 거부한 지점
        self.hit_020_at: Optional[int] = None
        self._lk = threading.Lock()
        self._load()

    # ── 상한 결정 ---------------------------------------------------------------------
    def limit(self) -> int:
        mode = globals().get("ARC_DART_LIMIT_MODE", "auto")
        if isinstance(mode, (int, float)) and not isinstance(mode, bool):
            return int(mode)
        base = int(self.learned_limit or globals().get("ARC_DART_LIMIT_HINT", 20_000))
        return max(100, base - int(globals().get("ARC_DART_SAFETY", 200)))

    def remaining(self) -> int:
        return max(0, self.limit() - self.n)

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_budget.json")

    LEARN_TTL_DAYS = 30          # 학습값 만료 — 한 번의 020 이 1년 뒤 실행까지 묶으면 안 된다

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            self.learned_limit = (int(j["learned_limit"])
                                  if j.get("learned_limit") else None)
            self.learned_at = j.get("learned_at") or ""
            # ★ 학습값에 만료를 준다. 예전에는 날짜 무관하게 무조건 읽어, 한 번의 020(또는
            #   021 오분류)으로 박힌 낮은 상한이 **1년 뒤에도 그대로** 적용됐다.
            if self.learned_limit and self.learned_at:
                try:
                    age = (_dt.date.today() -
                           _dt.date.fromisoformat(str(self.learned_at))).days
                    if age > self.LEARN_TTL_DAYS:
                        LOG.info(f"DART 상한 학습값({self.learned_limit:,})이 {age}일 전 값이라 "
                                 f"만료 처리하고 힌트값으로 되돌립니다 "
                                 f"(TTL {self.LEARN_TTL_DAYS}일).")
                        self.learned_limit, self.learned_at = None, ""
                except Exception:
                    pass
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
        except Exception:
            pass
        src = ("실측 학습값" if self.learned_limit else "추정 힌트값(아직 실측 전)")
        LOG.info(f"DART 호출 예산 — 오늘 사용 {self.n:,}건 / 상한 {self.limit():,}건 ({src}) → "
                 f"남은 호출 {self.remaining():,}건. 이 값은 실행 중 실시간으로 갱신됩니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n,
                 "learned_limit": self.learned_limit,
                 "learned_at": getattr(self, "learned_at", "") or "",
                 "updated": _dt.datetime.now().isoformat(timespec="seconds")}))
        except Exception:
            pass

    # ── 소비 / 환급 -------------------------------------------------------------------
    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.exhausted:
                return False
            if self.n + k > self.limit():
                self.exhausted = True
                LOG.warn(f"DART 호출 예산 소진 (사용 {self.n:,} / 상한 {self.limit():,}). "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일 같은 코드를 "
                         f"다시 실행하면 정확히 이 지점부터 이어받습니다.")
                self._save()
                return False
            self.n += k
            if self.n % 250 == 0:
                self._save()
            return True

    # 학습 하한 — 힌트값의 이 비율 아래로는 내려가지 않는다. 020 은 '같은 키를 다른
    # 노트북이 쓰는 중' 이거나 'UTC/KST 리셋 어긋남' 으로도 발생하는데, 그때 학습한
    # 낮은 값이 영구 고정되면 이후 모든 실행이 그 상한에 갇힌다.
    LEARN_FLOOR_RATIO = 0.5

    def note_rate_limited(self):
        """서버가 status=020 을 준 순간 = 실제 상한에 닿았다. 그 지점을 학습해 영속화한다."""
        with self._lk:
            self.exhausted = True
            self.hit_020_at = self.n
            prev = self.learned_limit
            hint = int(globals().get("ARC_DART_LIMIT_HINT", 20_000))
            floor = int(hint * self.LEARN_FLOOR_RATIO)
            learned = int(self.n)
            if learned < floor:
                LOG.warn(f"020 시점 사용량 {learned:,}건이 힌트값 {hint:,}의 "
                         f"{self.LEARN_FLOOR_RATIO:.0%}({floor:,}) 미만입니다. 같은 키를 다른 "
                         f"실행이 쓰고 있거나 UTC/KST 리셋이 어긋난 상황일 수 있으므로, "
                         f"이 값을 영구 상한으로 학습하지 않고 하한 {floor:,}로 기록합니다.")
                learned = floor
            self.learned_limit = learned
            self.learned_at = str(_dt.date.today())
            self._save()
        if prev != self.learned_limit:
            LOG.warn(f"DART 서버가 한도 초과(020)를 반환했습니다. 실제 상한을 {self.n:,}건으로 "
                     f"학습해 기록했습니다{'' if prev is None else f' (이전 학습값 {prev:,})'}. "
                     f"다음 실행부터는 이 값을 기준으로 남은 호출량을 계산합니다.")

    def report(self):
        LOG.table([["오늘 사용", f"{self.n:,}"],
                   ["적용 상한", f"{self.limit():,}"],
                   ["남은 호출", f"{self.remaining():,}"],
                   ["상한 출처", "서버 실측 학습값" if self.learned_limit else "추정 힌트값"],
                   ["020 발생 지점", f"{self.hit_020_at:,}" if self.hit_020_at else "없음"]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출 예산 (하드코딩 없이 실시간 추적)")

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None

_DART_TLS = threading.local()


def dart_last_status() -> str:
    return getattr(_DART_TLS, "status", "")


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    _DART_TLS.status = ""
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
    _DART_TLS.status = st
    if st and st != "000":
        if st == "020":
            # ★ 여기가 '실측 상한'을 배우는 유일한 지점이다. 상수를 믿지 않고 서버가 거부한
            #   순간의 사용량을 기록해 다음 실행의 예산 계산에 쓴다.
            if DBUDGET is not None:
                DBUDGET.note_rate_limited()
            LOG.warn(f"DART status=020 ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st == "021":
            #   (상세 근거는 커밋 로그 참조)
            LOG.warn(f"DART status=021 ({DART_STATUS_MSG.get(st, '?')}) — 요청의 회사 수가 "
                     f"많습니다. 일일 한도와 무관하므로 예산을 소진 처리하지 않고 배치 크기를 "
                     f"줄여 진행하세요(ARC 는 DART_MULTI_BATCH 로 조절).")
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
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]

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
#   (상세 근거는 커밋 로그 참조)
DART_MULTI_BATCH = 100
def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")

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
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
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
                 f"(오늘 남은 호출 {(DBUDGET.remaining() if DBUDGET else 0):,}건 — 실시간 추적값)")
        _avail = max(1, DBUDGET.remaining() if DBUDGET else 1)
        if total_needed > _avail:
            LOG.warn(f"필요 호출({total_needed:,})이 오늘 남은 호출({_avail:,})을 초과합니다. "
                     f"오늘 받을 수 있는 만큼 받고 저장합니다. "
                     f"약 {math.ceil(total_needed / _avail)}일에 걸쳐 콜드빌드가 완성됩니다. "
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
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세비용차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
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

def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다."""
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()
    d["amount"] = pd.to_numeric(
        d["thstrm_amount"].astype(str).str.replace(",", "", regex=False).str.replace("−", "-", regex=False),
        errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
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
        # 같은 항목에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "rcept_no", "item", "amount"]])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    rc = (L.sort_values("rcept_no").groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    # 누적치 → 분기 단독치 (Q1/H1/Q3/FY 는 누적 공시다. 차분하지 않으면 계절성이 곧 신호가 된다)
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    flow_items = FLOW_ITEMS
    # 누적 → 분기 단독. 직전 분기가 실제로 존재할 때만 차분한다.
    # (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    gk = ["corp_code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in flow_items:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        q_val = np.where(W["q"] == 1, W[c],
                         np.where(contiguous, W[c] - prev, np.nan))
        W[c + "_q"] = q_val
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])
    # ★ 재무상태표 항목(재고·매출채권·자산·자본 등)은 pivot 결과에 그 계정이 없으면
    #   컬럼 자체가 생성되지 않는다. 그러면 패널 스키마가 실행마다 달라져
    #   "어떤 날은 있고 어떤 날은 없는" 축이 생긴다. 여기서 전 항목을 계약적으로 보장한다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in W.columns:
            W[_k] = np.nan
    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' 플래그 ─────────────────────────────────────
    #   (상세 근거는 커밋 로그 참조)
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
# ── DART 엔드포인트 공용 러너 ───────────────────────────────────────────────────────────────
#   empSttus / stockTotqySttus / accnutAdtorNmNdAdtOpinion 은 바깥 골격이 동일하다:
#   캐시 재사용 → 미수집 키만 추림 → 병렬 호출 → 병합 → period_end/knowledge_date →
#   공용 인덱스 저장 → PIT frame. 다른 것은 응답 한 건을 dict 로 바꾸는 부분뿐이다.
#   ★ 여기에 '빈 응답 음성캐시'를 함께 넣는다. 상장 전/폐지 후 연도처럼 정상적으로 데이터가
#     없는 조합은 성공 캐시에 남지 않아 매 실행 전량 재조회됐고(실측 16조합 중 15조합 재호출),
#     콜드빌드가 수렴하지 않아 DART 예산이 늘 소진되고 뒤쪽 정기보고서 원문이 예산을
#     배정받지 못했다. 여기 한 곳에 넣으면 세 엔드포인트가 모두 고쳐진다.
_DART_MISS_TABLE = "dart_empty_attempts"
_DART_MISS_TTL_D = 180


def _dart_miss_load(ep: str) -> set:
    t = VAULT.get_table(_DART_MISS_TABLE, scope="shared")
    if t is None or not len(t) or "endpoint" not in t.columns:
        return set()
    t = t[t["endpoint"].astype(str) == ep]
    if not len(t):
        return set()
    age = (as_ts(_dt.date.today()) - as_ts_series(t["attempted_at"])).dt.days
    return set(t.loc[age < _DART_MISS_TTL_D, "jobkey"].astype(str))


def _dart_miss_save(ep: str, keys: Sequence[str]) -> None:
    if not keys:
        return
    new = pd.DataFrame([{"endpoint": ep, "jobkey": str(k),
                         "attempted_at": str(_dt.date.today())} for k in keys])
    old = VAULT.get_table(_DART_MISS_TABLE, scope="shared")
    allf = pd.concat([old, new], ignore_index=True) if old is not None and len(old) else new
    allf = allf.drop_duplicates(["endpoint", "jobkey"], keep="last")
    VAULT.put_table(_DART_MISS_TABLE, allf, scope="shared", domain="dart",
                    source="dart:negative_cache", allow_shrink=True)


def _dart_collect(name: str, table: str, cols: Sequence[str], jobs_all: Sequence[tuple],
                  key_cols: Sequence[str], parse: Callable[..., Optional[dict]],
                  source: str, workers: int = 12) -> pd.DataFrame:
    """DART (법인 × 연도 [× 보고서]) 엔드포인트 수집기.

    parse(*job) 가 행 dict 또는 None(데이터 없음)을 돌려준다. 나머지 골격은 전부 공통.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=list(cols))
    cached = VAULT.get_table(table, scope="shared")
    done = set()
    if cached is not None and len(cached) and all(c in cached.columns for c in key_cols):
        done = {"|".join(str(v) for v in row)
                for row in cached[list(key_cols)].astype(str).to_numpy()}
        LOG.info(f"공용 캐시에서 {name} {len(cached):,}행 재사용")
    miss = _dart_miss_load(table)
    if miss:
        LOG.info(f"{name}: 데이터 없음으로 기록된 {len(miss):,}조합을 건너뜁니다 "
                 f"({_DART_MISS_TTL_D}일 후 재시도).")
    jobs = [j for j in jobs_all
            if "|".join(str(v) for v in j) not in done
            and "|".join(str(v) for v in j) not in miss]
    if RUN_MODE == "CACHED":
        jobs = []

    def _run(job):
        try:
            r = parse(*job)
        except Exception:                                       # noqa
            return ("ERR", job, None)
        if r:
            return ("OK", job, r)
        # ★ '데이터 없음(013)' 일 때만 음성캐시에 남긴다. 네트워크 오류·예산 소진·파싱 실패를
        #   기록하면 일시적 장애가 180일짜리 영구 블랙리스트가 된다(가격 쪽에서 이미 겪은 사고).
        return (("MISS" if dart_last_status() == "013" else "ERR"), job, None)

    res = pmap_io(_run, jobs, workers=min(N_WORKERS_IO, workers),
                  desc=f"DART {name}") if jobs else []
    got = [r for st, _, r in res if st == "OK" and r]
    _dart_miss_save(table, ["|".join(str(v) for v in jb) for st, jb, _ in res if st == "MISS"])

    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=list(cols))
    D = pd.concat(frames, ignore_index=True).drop_duplicates(list(key_cols), keep="last")
    # ★ 컬럼이 없으면 D.get() 이 문자열을 돌려주고 zip 이 글자 단위로 훑어 knowledge_date 가
    #   전부 깨진다. 존재를 먼저 보장한다.
    if "rcept_no" not in D.columns:
        D["rcept_no"] = ""
    rc = D["reprt_code"].astype(str) if "reprt_code" in D.columns \
        else pd.Series([REPRT_CODES["FY"]] * len(D), index=D.index)
    D["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12, 31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12, 31))[1]:02d}")
                       for y, r in zip(D["bsns_year"], rc)]
    D["knowledge_date"] = [_knowledge_from_rcept(rn, str(r), int(y))
                           for rn, r, y in zip(D["rcept_no"], rc, D["bsns_year"])]
    if got:
        VAULT.put_table(table, D, scope="shared", domain="dart", source=source)
    D = pit_frame(D, "period_end", "knowledge_date", source="dart")
    PIPE.io("OUT", "DRIVE", table, D, source=source)
    return D


def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    def _parse(corp: str, year: int) -> Optional[dict]:
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

    return _dart_collect("직원현황", "dart_employees", ["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"],
                         [(str(c), int(y)) for c in corp_codes for y in years],
                         ["corp_code", "bsns_year"], _parse, "opendart empSttus", workers=12)

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
    #   (상세 근거는 커밋 로그 참조)
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

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C+  ARC 추가 수집 — 주식총수(D2 SHARE_GROWTH) / 감사의견(배제 EX_AUDIT)               ║
# ║                                                                                          ║
# ║  ★ 주식총수를 왜 별도로 받는가: 소형주는 지속적 증자·CB 발행으로 실적이 개선돼도            ║
# ║    주당지표가 개선되지 않거나 악화된다. 이 항목 없이는 D2 가 소형주 구간에서 오작동한다.    ║
# ║    재무제표에는 '자본금'만 있고 주식수가 없는 경우가 많아 전용 엔드포인트가 필요하다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SHARE_REPRTS = [REPRT_CODES["Q1"], REPRT_CODES["H1"],
                 REPRT_CODES["Q3"], REPRT_CODES["FY"]]
_SHARE_COLS = ["corp_code", "bsns_year", "reprt_code", "shares_common", "shares_total",
               "treasury_shares", "period_end", "knowledge_date", "rcept_no"]

def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    def _parse(corp: str, year: int, reprt: str) -> Optional[dict]:
        js = dart_api("stockTotqySttus.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        if d.empty:
            return None
        se = d.get("se", pd.Series([""] * len(d))).astype(str).str.replace(r"\s+", "", regex=True)
        # 발행주식총수 컬럼명은 연도별로 isu_stock_totqy / istc_totqy 등으로 흔들린다.
        cand = [c for c in ("isu_stock_totqy", "istc_totqy", "now_to_isu_stock_totqy")
                if c in d.columns]
        if not cand:
            return None
        tot = _num_kr_series(d[cand[0]])
        tesstk = _num_kr_series(d["tesstk_co"]) if "tesstk_co" in d.columns else pd.Series(np.nan, index=d.index)
        is_sum = se.str.contains("합계|계$", regex=True)
        is_common = se.str.contains("보통주")
        if is_sum.any():
            shares_total = float(tot[is_sum].max())
        else:
            shares_total = float(tot[~is_sum].sum(skipna=True)) if len(tot) else float("nan")
        shares_common = float(tot[is_common].max()) if is_common.any() else shares_total
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "reprt_code": str(reprt),
                "shares_common": shares_common, "shares_total": shares_total,
                "treasury_shares": float(tesstk.sum(skipna=True)) if tesstk.notna().any() else np.nan,
                "rcept_no": rn}

    return _dart_collect("주식총수", "dart_shares", _SHARE_COLS,
                         [(str(c), int(y), r) for y in sorted(years, reverse=True)
             for c in corp_codes for r in _SHARE_REPRTS],
                         ["corp_code", "bsns_year", "reprt_code"], _parse, "opendart stockTotqySttus", workers=12)

def _num_kr_series(s) -> pd.Series:
    return pd.to_numeric(
        pd.Series(s).astype(str)
          .str.replace("−", "-", regex=False).str.replace("△", "-", regex=False)
          .str.replace(r"[^\d.\-]", "", regex=True).replace("", np.nan),
        errors="coerce")


_AUDIT_COLS = ["corp_code", "bsns_year", "audit_opinion", "emphasis", "key_matter",
               "auditor", "period_end", "knowledge_date"]

def fetch_dart_audit(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """감사의견 + 특기사항/강조사항. 배제 플래그 EX_AUDIT 입력.
    ★ '적정의견'이라도 강조사항(계속기업 불확실성 등)이 붙으면 그 자체가 경고다(§6.4).
      필드명이 연도별로 흔들리므로 후보를 전부 훑어 하나라도 비어있지 않으면 존재로 본다."""
    _OPI = ("adt_opinion", "adt_opinion_nm", "opinion")
    _EMP = ("emphs_matter", "adt_reprt_spcmnt_matter", "spcmnt_matter")
    _KEY = ("core_adt_matter", "core_adt_matter_nm")
    _AUD = ("adtor", "adt_nm", "auditor")

    def _pick_field(d: pd.DataFrame, names) -> str:
        for n in names:
            if n in d.columns:
                v = re.sub(r"\s+", " ",
                           " ".join(str(x) for x in d[n].dropna().astype(str).tolist())).strip()
                if v and v not in ("-", "해당사항 없음", "해당사항없음", "없음", "nan"):
                    return v[:400]
        return ""

    def _parse(corp: str, year: int) -> Optional[dict]:
        js = dart_api("accnutAdtorNmNdAdtOpinion.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year),
                "audit_opinion": _pick_field(d, _OPI),
                "emphasis": _pick_field(d, _EMP),
                "key_matter": _pick_field(d, _KEY),
                "auditor": _pick_field(d, _AUD), "rcept_no": rn}

    return _dart_collect("감사의견", "dart_audit", _AUDIT_COLS,
                         [(str(c), int(y)) for y in sorted(years, reverse=True) for c in corp_codes],
                         ["corp_code", "bsns_year"], _parse, "opendart accnutAdtorNmNdAdtOpinion", workers=10)
