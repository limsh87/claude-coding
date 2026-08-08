

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
        self.today = self._kst_day()
        self.n = 0
        self.exhausted = False
        self._lk = threading.RLock()
        self._reserved: Dict[str, int] = {}
        self._dirty = 0
        self._warned_reserve = False
        self._load()

    @staticmethod
    def _kst_day() -> str:
        """DART 한도의 리셋 경계는 00:00 KST 다. 로컬 날짜를 쓰면 UTC 컨테이너에서
        하루에 두 번 틀린다: 15~24 UTC 는 이미 리셋된 한도를 소진으로 착각해 9시간을
        헛차단하고, 그 뒤에는 남아 있다고 믿고 쏘다가 status 020 을 맞는다."""
        try:
            from zoneinfo import ZoneInfo
            return _dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        except Exception:
            return (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date().isoformat()

    def _roll_if_new_day(self):
        """긴 실행이 자정을 넘으면 한도도 리셋된다. take() 안에서 값싸게 확인한다."""
        d = self._kst_day()
        if d != self.today:
            LOG.info(f"KST 자정 경과 — DART 일일 한도가 초기화됐습니다 "
                     f"({self.today} → {d}, 직전 사용 {self.n:,}건).")
            self._save()
            self.today, self.n, self.exhausted = d, 0, False
            DART_HALT["reason"] = DART_HALT["detail"] = None

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

    def refund(self, k: int = 1, purpose: Optional[str] = None):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)
            # ★ 예약분도 함께 되돌린다. take(2) 후 refund(1) 이 정상 경로이므로,
            #   되돌리지 않으면 예약이 잡당 2 씩 깎여 14,000 예약이 7,000건만 보호한다.
            if purpose in self._reserved:
                self._reserved[purpose] += k
            self._dirty += k

    # ── 예약(reservation) ─────────────────────────────────────────────────────────────
    #  ★ 이 전략의 알파는 직원현황 하나뿐인데, 실행 3회 내내 dart_employees_ext 가 0행이었다.
    #    원인은 단순하다 — Tier-2 전체재무제표가 일일 한도를 먼저 다 써버렸다. 단계 순서를
    #    바꿔도 예산은 '날짜별 누적 카운터'라 어제 태운 것이 오늘까지 따라온다.
    #    → 특정 용도(purpose)에 호출 수를 **예약**해 두고, 예약분은 그 용도만 인출한다.
    #      일반 소비자는 (한도 − 예약잔량) 까지만 쓸 수 있다.
    def reserve(self, purpose: str, k: int):
        with self._lk:
            self._reserved[purpose] = max(0, int(k))

    def _reserved_for_others(self, purpose: Optional[str]) -> int:
        return sum(v for p, v in self._reserved.items() if p != purpose)

    def left(self, purpose: Optional[str] = None) -> int:
        """purpose 가 지금 쓸 수 있는 호출 수. 남의 예약분은 빼고 센다."""
        with self._lk:
            return max(0, DART_DAILY_LIMIT - self.n - self._reserved_for_others(purpose))

    def take(self, k: int = 1, purpose: Optional[str] = None) -> bool:
        with self._lk:
            self._roll_if_new_day()
            room = DART_DAILY_LIMIT - self._reserved_for_others(purpose)
            if self.n + k > room:
                # 예약 때문에 막힌 것인지, 한도 자체가 끝난 것인지 구별해서 알린다.
                if self.n + k > DART_DAILY_LIMIT:
                    if not self.exhausted:
                        self.exhausted = True
                        LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                                 f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, "
                                 f"내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                elif not self._warned_reserve:
                    self._warned_reserve = True
                    LOG.info(f"남은 호출은 다른 용도로 예약되어 있습니다 "
                             f"(예약 {self._reserved}). 이 단계는 여기서 멈춥니다 — "
                             f"예약분은 알파 원천(직원현황) 몫입니다.")
                if purpose in self._reserved:
                    self._reserved[purpose] = max(0, self._reserved[purpose] - k)
                return False
            self.n += k
            if purpose in self._reserved:
                self._reserved[purpose] = max(0, self._reserved[purpose] - k)
            self._dirty += k
            # ★ n % 500 은 refund 가 임의 값으로 감산하는 순간 영원히 안 맞을 수 있다.
            #   '마지막 저장 이후 변동량'으로 세면 어떤 감산 패턴에서도 반드시 저장된다.
            if self._dirty >= 200:
                self._dirty = 0
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★ '지금 못 받는다' 와 '원래 없다' 를 구별하는 단일 진실
#
#  dart_api() 는 세 가지 전혀 다른 사건을 모두 None 으로 뭉갠다:
#    ① 예산 게이트가 호출을 거부   ② 네트워크 실패   ③ API 가 '데이터 없음'(013) 응답
#  호출자는 ①②를 ③으로 읽는다. 실제로 이것 때문에 실행이 죽었다 —
#  일일 한도가 소진된 상태로 시작한 실행에서 CANARY 가 K8 을 '급여총액 미기재'로 판정하고
#  §12-2 킬 기준을 발동시켰다. 데이터는 멀쩡히 있었고 오늘 호출권이 없었을 뿐이다.
#  게다가 그 판정의 처방은 '백테스트 시작일 상향' — 일시적 조건으로 전략을 영구 훼손한다.
#
#  → 사유를 여기에 기록하고, 자원 조건으로 실패한 검사는 FAIL 이 아니라 SKIP 이어야 한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
DART_HALT: Dict[str, Optional[str]] = {"reason": None, "detail": None}


def dart_note_halt(reason: str, detail: str = ""):
    if DART_HALT["reason"] is None:
        DART_HALT["reason"], DART_HALT["detail"] = reason, detail


def dart_halt_reason(purpose: Optional[str] = None) -> Optional[str]:
    """지금 DART 를 쓸 수 없는 이유. None 이면 정상 — 즉 '응답 0건'은 진짜 데이터 부재다.

    purpose 를 주면 그 용도의 **예약분까지 고려**해서 판정한다. 예약이 남아 있으면
    전체 잔량이 0 이어도 그 용도는 계속 진행할 수 있다."""
    if not DART_API_KEY:
        return "DART_API_KEY 미입력"
    if DBUDGET is not None:
        if DBUDGET.left(purpose) <= 0 or DBUDGET.n >= DART_DAILY_LIMIT:
            return f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})"
        if purpose is None and DBUDGET.exhausted:
            return f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})"
    return DART_HALT["reason"]


def dart_budget_left(purpose: Optional[str] = None) -> int:
    return DBUDGET.left(purpose) if DBUDGET else DART_DAILY_LIMIT


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2, no_data_ok: bool = False,
             purpose: Optional[str] = None) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries, purpose=purpose):
        dart_note_halt(f"일일 호출 한도 소진 ({DBUDGET.n:,}/{DART_DAILY_LIMIT:,})",
                       "내일 재실행하면 정확히 이 지점부터 이어받습니다.")
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    # ★ try/finally 가 없으면 http_json 에서 예외가 새는 순간 tries 만큼이 영구 소실된다.
    #   EMP 경로는 상위에서 예외를 삼키므로 이 누수가 **완전히 조용하다**.
    try:
        js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                       referer="https://opendart.fss.or.kr/",
                       on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    finally:
        if DBUDGET is not None:
            DBUDGET.refund(max(0, tries - max(1, attempts["n"])), purpose=purpose)
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            dart_note_halt(f"DART 서버가 한도 초과 응답(status={st})",
                           "내일 재실행하면 이어받습니다.")
            LOG.warn(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            dart_note_halt(f"DART 인증 오류(status={st} · {DART_STATUS_MSG.get(st, '?')})",
                           "DART_API_KEY 를 확인하세요. 데이터 부재가 아닙니다.")
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st == "800":
            dart_note_halt("DART 시스템 점검 중(status=800)", "점검 종료 후 재실행하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        # ★ 013("조회된 데이터 없음")은 통신 실패가 아니라 **정상 응답**이다. 그런데 None 으로
        #   뭉개면 호출자가 '실패'와 구별할 수 없다. 서킷브레이커를 둔 호출자에게 이건 치명적이다
        #   — 그 해에 사업보고서를 안 낸 회사가 몇 곳만 연속돼도 브레이커가 터져 남은 수집을
        #   통째로 포기한다. 원하는 호출자만 opt-in 으로 빈 응답을 받아 구별할 수 있게 한다.
        if st == "013" and no_data_ok:
            return {"status": "013", "list": []}
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
    # ★ 예산·인증이 이미 막혔으면 남은 잡을 즉시 포기한다. 계속 돌면 OFS/CFS 두 번씩
    #   헛호출하며 큐 전체(최대 12,000건)를 소진하고, 로그만 실패로 채운다.
    if dart_halt_reason():
        return None
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        if dart_halt_reason():
            return None
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
        if dart_halt_reason():          # 예산·인증이 막히면 남은 배치를 즉시 포기
            return None
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
                          priority: Optional[Sequence[str]] = None,
                          max_calls: Optional[int] = None,
                          freq: Optional[str] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다.

    ★ max_calls (2026-08 추가 — 이번 실행에서 던질 호출 수의 하드 상한)
      이 함수의 잡 수는 |기업| × |연도| × |보고서| 로 **곱셈으로 폭발**한다.
      3,981사 × 13년 × 4분기 = 207,012건 = 11일치. 호출자가 상한을 주지 않으면
      tqdm 이 11시간짜리 ETA 를 띄운 채 그대로 돌아간다 — 4시간 예산 계약이 있는
      호출자에게 이것은 계약 위반이다. 상한을 받으면 **우선순위 순으로 잘라서** 그만큼만
      던지고, 무엇을 남겼는지 로그로 밝힌다. None 이면 종전과 동일(무제한 콜드빌드).

    ★ freq  ("annual" | "quarterly") — 전역 DART_STATEMENT_FREQ 를 호출자가 덮어쓴다.
      연간만 받으면 잡 수가 정확히 1/4 이 된다.
    """
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

    reprts = ([REPRT_CODES["FY"]] if (freq or DART_STATEMENT_FREQ) == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    # 연도 내림차순 → 기업 우선순위 → 사업보고서(FY) 우선. FY 를 먼저 받아야 연간 축(직원현황·
    # 한계임금)과 짝이 맞는 회계 데이터가 먼저 완성된다.
    _rorder = {REPRT_CODES["FY"]: 0, REPRT_CODES["Q3"]: 1,
               REPRT_CODES["H1"]: 2, REPRT_CODES["Q1"]: 3}
    reprts = sorted(reprts, key=lambda r: _rorder.get(r, 9))
    jobs = [(c, y, r) for y in sorted(years, reverse=True) for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    total_needed = len(jobs)
    left_today = max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0))
    cap = total_needed
    if max_calls is not None:
        cap = max(0, min(cap, int(max_calls), left_today))
    if jobs:
        LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 (오늘 가용 호출 {left_today:,}건)")
        if cap < total_needed:
            jobs = jobs[:cap]
            LOG.warn(
                f"이번 실행에서는 상한 {cap:,}건만 받습니다 "
                f"(전체 {total_needed:,}건 = 약 {math.ceil(total_needed / max(DART_DAILY_LIMIT,1))}일치). "
                f"미수집분은 Tier-1 주요계정(fnlttMultiAcnt)으로 대체되며, "
                f"재실행하면 정확히 이 지점부터 이어받습니다. "
                f"상한은 DART_FS_MAX_CALLS 로 조절합니다.")
        elif total_needed > DART_DAILY_LIMIT:
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

# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼 전체 목록.
# attach_fundamentals 가 이 목록으로 스키마를 계약적으로 보장한다 — 수집이 얼마나 실패하든
# 패널의 컬럼 집합은 항상 같아야 한다. 그래야 "어떤 실행에선 있고 어떤 실행엔 없는" 축이
# 사라지고, 결측은 결측대로 조용히가 아니라 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_PATTERNS)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


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


# ★ 모듈 스코프여야 한다. 예전엔 fetch_dart_disclosures 안의 지역변수였는데
#   _disclosure_done_months 가 이를 참조해 NameError 가 잠복해 있었다. 예산이 남아 있는
#   첫 실행에서 L1.DART 가 통째로 죽는다(critical=False 라 조용한 WARN 으로).
DISCLOSURE_TYPES = ("A", "B")     # A=정기공시(사업/반기/분기보고서), B=주요사항보고
DISCLOSURE_LEDGER = "dart_disclosure_months"


def _disclosure_done_months(cached: Optional[pd.DataFrame]) -> set:
    """완결이 **증명된** 달만 돌려준다.

    기존 캐시에는 이 원장이 없다. 그렇다고 '캐시에 행이 있으니 완결'로 간주하면
    이미 뚫려 있는 구멍을 그대로 물려받는다. 그래서 레거시 캐시는 (달 × 유형)당
    1회짜리 값싼 탐침으로 total_count 를 받아 실제 보유 행수와 대조해 검증한다.
    120개월이면 240회 — 전체 재수집(수천 회)에 비하면 무시할 수 있는 비용이고,
    이 한 번으로 과거 실행이 남긴 조용한 결손이 드러난다.
    """
    led = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    if led is not None and len(led) and "month" in led.columns:
        d = led[led.get("complete", False).astype(bool)] if "complete" in led.columns else led
        return set(d["month"].astype(str))
    if cached is None or not len(cached):
        return set()

    have = cached["rcept_dt"].dt.to_period("M").astype(str).value_counts().to_dict()
    if not have or not DART_API_KEY or RUN_MODE == "CACHED" or dart_halt_reason():
        # 검증할 수 없으면 재수집 대상으로 둔다 — 조용히 '완결'로 승격시키지 않는다.
        return set()

    LOG.info(f"공시목록 캐시 {len(have)}개월의 완결성을 검증합니다 "
             f"(달당 {len(DISCLOSURE_TYPES)}회 탐침 — 과거 실행이 페이지 중간에 끊겼는지 확인).")

    def _probe(mk):
        p = pd.Period(mk, freq="M")
        total = 0
        for ty in DISCLOSURE_TYPES:
            js = dart_api("list.json", {
                "bgn_de": p.start_time.strftime("%Y%m%d"), "end_de": p.end_time.strftime("%Y%m%d"),
                "pblntf_ty": ty, "page_no": 1, "page_count": 1, "last_reprt_at": "N"},
                no_data_ok=True)
            if js is None:
                return mk, None                       # 검증 실패 → 완결로 승격하지 않는다
            total += int(js.get("total_count", 0) or 0)
        return mk, total

    res = pmap_io(_probe, sorted(have), workers=min(N_WORKERS_IO, 8), desc="공시 캐시 완결성 검증")
    ok, holed, unknown = set(), [], 0
    for r in res:
        if not r:
            unknown += 1
            continue
        mk, total = r
        if total is None:
            unknown += 1
        elif have.get(mk, 0) >= total:
            ok.add(mk)
        else:
            holed.append((mk, have.get(mk, 0), total))
    if holed:
        LOG.warn(f"과거 실행이 남긴 공시목록 결손 {len(holed)}개월을 찾았습니다 — "
                 f"예: {[f'{m}: {h}/{t}행' for m, h, t in holed[:3]]}. "
                 f"이 달들을 다시 받습니다. (그대로 뒀다면 유상증자·전환사채·자기주식 공시가 "
                 f"'애초에 없었던 것'으로 백테스트에 들어갔습니다)")
    if unknown:
        LOG.info(f"  {unknown}개월은 검증하지 못해 재수집 대상으로 둡니다(안전한 방향).")
    _save_disclosure_ledger(ok)
    return ok


def _save_disclosure_ledger(complete_months) -> None:
    prev = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    rows = set()
    if prev is not None and len(prev) and "month" in prev.columns:
        keep = prev[prev["complete"].astype(bool)] if "complete" in prev.columns else prev
        rows |= set(keep["month"].astype(str))
    rows |= {str(m) for m in complete_months}
    if not rows:
        return
    VAULT.put_table(DISCLOSURE_LEDGER,
                    pd.DataFrame({"month": sorted(rows), "complete": True}),
                    scope="shared", domain="dart",
                    source="공시목록 완결성 원장 — 페이지를 끝까지 훑은 달만 기록")


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ '그 달에 행이 하나라도 있다' ≠ '그 달을 다 받았다'
    #
    #  예전에는 have_months 를 캐시 행의 rcept_dt 에서 유도했다. 그래서 12페이지짜리 달을
    #  3페이지에서 예산·네트워크로 놓쳐도, 1~2페이지가 저장되는 순간 그 달은 영원히
    #  '보유'로 표시되고 나머지 페이지는 **두 번 다시 시도되지 않았다.**
    #  잃어버리는 것이 유상증자·전환사채·자기주식 공시라서, 하류(V3 희석 거부권·PACK-C)는
    #  '이벤트 없음'이라는 **정상적인 값**을 읽는다 — 경고도 FAIL 도 뜨지 않고, 재실행할수록
    #  그 거짓이 굳는다. 일시적 장애를 영구적 음성 관측으로 세탁하는 최악의 형태다.
    #  → 완결 여부를 별도 원장에 명시적으로 기록하고, 그 원장만 신뢰한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    done_months = _disclosure_done_months(cached)
    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in done_months]
    if RUN_MODE == "CACHED":
        todo = []
    elif todo and cached is not None and len(cached):
        LOG.info(f"공시목록 미완결 {len(todo)}개월을 다시 받습니다 "
                 f"(완결 확인 {len(done_months)}개월). 페이지 중간에 끊긴 달은 "
                 f"'보유'로 세지 않습니다 — 그렇게 세면 빠진 공시가 영구히 없는 것이 됩니다.")

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)

    def _one(m):
        """(월, 행들, 완결여부). 한 페이지라도 못 받으면 그 달은 미완결이다."""
        rows, complete = [], True
        for ty in DISCLOSURE_TYPES:
            page, walked = 1, False
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"}, no_data_ok=True)
                if js is None:                       # 예산·네트워크·인증 → 이 달은 미완결
                    complete = False
                    break
                lst = js.get("list")
                if not isinstance(lst, list) or not lst:
                    walked = True                    # 정상 빈 응답 = 이 유형은 여기서 끝
                    break
                rows.extend(lst)
                if page >= int(js.get("total_page", 1) or 1):
                    walked = True
                    break
                page += 1
            else:
                complete = False                     # 100페이지 상한 = 다 못 훑었다
            if not walked and complete is not False:
                complete = False
        return str(m), rows, complete

    new, ok_months, bad_months = [], [], []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if not r:
                continue
            mkey, rows, complete = r
            new.extend(rows)
            (ok_months if complete else bad_months).append(mkey)
        if bad_months:
            LOG.warn(f"공시목록 {len(bad_months)}개월이 미완결로 남았습니다 "
                     f"(예: {bad_months[:3]}). 받은 부분은 저장하되 **완결로 표시하지 않으므로** "
                     f"다음 실행에서 그 달부터 다시 받습니다. "
                     + (f"사유: {dart_halt_reason()}" if dart_halt_reason() else ""))

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
    # 원장 갱신은 저장 뒤에. 완결로 표시한 달은 실제로 저장된 달이어야 한다.
    if ok_months:
        _save_disclosure_ledger(ok_months)
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")     # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — 이벤트 분류: " +
           ", ".join(f"{k}={int((D['event']==k).sum()):,}" for k in DISCLOSURE_PATTERNS if (D['event']==k).any()))
    PIPE.io("OUT", "DRIVE", "dart_disclosures", D, source="opendart list.json")
    return D
