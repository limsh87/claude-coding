

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  DART 호출량 관리 — "남은 만큼 쓴다"                                                ║
# ║                                                                                          ║
# ║  이전 구현의 결함 4가지를 전부 고쳤다:                                                     ║
# ║   ① 상한을 19,000 으로 하드코딩하고 그 숫자를 게이트로 썼다.                                ║
# ║      → 상한은 '표시용 힌트'일 뿐이고, 실제 정지 조건은 API 가 돌려주는 status='020' 이다.   ║
# ║        한도 상향 승인을 받은 계정이면 020 이 올 때까지 계속 쓴다. 관측으로 한도를 학습한다.  ║
# ║   ② status='020' 을 감지해 exhausted 플래그만 세우고 정작 게이트에 쓰지 않았다.             ║
# ║      → 020 이후에도 남은 작업이 전부 실제 HTTP 를 쏘고 실패했다. 이제 즉시 하드 스톱한다.    ║
# ║   ③ 카운터를 '전용(private)' 네임스페이스에 저장했다.                                       ║
# ║      → 호출량은 전략이 아니라 'API 키'에 걸린다. 두 전략이 각자 2만건이라고 착각했다.        ║
# ║        이제 공용(shared) 네임스페이스에 키 해시별로 저장해 모든 전략이 같은 잔량을 본다.     ║
# ║   ④ 날짜 경계를 컨테이너 로컬시각으로 잡았다 (Colab 은 UTC).                                ║
# ║      → DART 의 초기화 기준은 KST 자정이다. UTC 로 세면 매일 9시간 어긋난다.                  ║
# ║                                                                                          ║
# ║  그리고 애초에 이 전략은 DART 를 거의 쓰지 않는다.                                          ║
# ║  필요한 건 §6.3 직교화의 BM(장부/시가) 한 항목이고, 1순위는 KRX 월말 PBR 스냅샷(120호출)다.  ║
# ║  DART 는 그게 비었을 때만 '배치' 엔드포인트로 보강한다(100사/호출). 예상 총량은 실행 시작 시  ║
# ║  표로 출력된다 — 통상 2,000건 미만이다.                                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_LIMIT_HINT = 20_000          # 공식 기본 한도(표시용). 게이트가 아니다 — 관측으로 갱신된다.
DART_MULTI_BATCH = 100            # fnlttMultiAcnt: 1회 호출에 100개사
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

_KST = _dt.timezone(_dt.timedelta(hours=9))


def kst_today() -> str:
    """DART 일일 한도의 초기화 기준은 KST 자정이다. 컨테이너 로컬시각(UTC)이 아니다."""
    return _dt.datetime.now(_dt.timezone.utc).astimezone(_KST).date().isoformat()


def kst_seconds_to_reset() -> int:
    now = _dt.datetime.now(_dt.timezone.utc).astimezone(_KST)
    nxt = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


class DartQuota:
    """실시간 잔여 호출량 관리자.

    핵심 원리: **한도를 가정하지 않고 관측한다.**
      · used  : 실제로 나간 HTTP 요청 수 (재시도 포함). 정확히 센다.
      · limit : 처음엔 힌트(20,000). status='020' 을 받은 시점의 used 를 '관측된 한도'로
                기록하고 이후 그 값을 쓴다. 다음 날 그 관측치를 사전값으로 재사용한다.
      · 정지  : limit 도달이 아니라 **020 수신**이 하드 스톱이다.
                (한도가 상향된 계정은 20,000 을 넘겨도 020 이 안 오므로 계속 쓴다)
    """

    def __init__(self, api_key: str, scope: str = "shared"):
        self.key_id = sha1_str("dartkey", api_key or "")[:12] if api_key else "nokey"
        self.scope = scope
        self.today = kst_today()
        self.used = 0
        self.observed_limit: Optional[int] = None   # 020 을 실제로 받은 지점
        self.exhausted = False
        self.calls_api = 0                          # 논리 호출 수 (HTTP 요청 수와 구분)
        self._lk = threading.RLock()
        self._dirty = 0
        self._load()

    # ── 영속화: 공용 네임스페이스, 키별 ──────────────────────────────────────────────
    def _path(self) -> str:
        return os.path.join(VAULT.ns[self.scope], "index", f"dart_quota_{self.key_id}.json")

    def _load(self):
        try:
            j = json.loads(open(self._path(), encoding="utf-8").read())
        except Exception:
            return
        # 어제까지의 '관측된 한도'는 날짜가 바뀌어도 유효한 지식이므로 이어받는다
        ol = j.get("observed_limit")
        if isinstance(ol, int) and ol > 0:
            self.observed_limit = ol
        if j.get("date") == self.today:
            self.used = int(j.get("used", 0))
            self.exhausted = bool(j.get("exhausted", False))
            if self.used:
                LOG.info(f"오늘(KST {self.today}) 이 키로 이미 사용한 DART 호출 {self.used:,}건 — "
                         f"잔여 {self.remaining():,}건. 이어서 진행합니다.")
            if self.exhausted:
                LOG.warn(f"이 키는 오늘 이미 한도 초과(020)를 받았습니다. "
                         f"KST 자정까지 {kst_seconds_to_reset() // 3600}시간 "
                         f"{kst_seconds_to_reset() % 3600 // 60}분 남았습니다. "
                         f"DART 경로는 건너뛰고 캐시/KRX 경로로 진행합니다.")

    def _save(self, force: bool = False):
        if not force and self._dirty < 100:
            return
        self._dirty = 0
        try:
            atomic_write_text(self._path(), json.dumps({
                "date": self.today, "used": self.used, "exhausted": self.exhausted,
                "observed_limit": self.observed_limit, "key_id": self.key_id,
                "updated_at": _dt.datetime.now(_KST).isoformat(timespec="seconds"),
            }, ensure_ascii=False))
        except Exception:
            pass

    # ── 잔여량 ──────────────────────────────────────────────────────────────────────
    @property
    def limit(self) -> int:
        return int(self.observed_limit or DART_LIMIT_HINT)

    def remaining(self) -> int:
        """지금 이 순간 남은 호출량. 020 을 받았으면 0."""
        with self._lk:
            if self.exhausted:
                return 0
            return max(0, self.limit - self.used)

    def limit_is_observed(self) -> bool:
        return self.observed_limit is not None

    # ── 예약 / 환급 ─────────────────────────────────────────────────────────────────
    def take(self, k: int = 1) -> bool:
        """k회의 HTTP 요청을 예약. 020 을 받았으면 무조건 거부(하드 스톱)."""
        with self._lk:
            if self.exhausted:
                return False
            # 힌트 한도를 넘어서도, 020 을 실제로 받기 전까지는 막지 않는다.
            # (한도 상향 계정을 스스로 19,000 에서 멈추게 만든 것이 이전 구현의 핵심 결함)
            if self.observed_limit is not None and self.used + k > self.observed_limit:
                return False
            self.used += k
            self._dirty += k
            self._save()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.used = max(0, self.used - k)

    def mark_exhausted(self):
        """API 가 020 을 돌려줬다 = 진짜 한도. 이 지점을 관측치로 학습한다."""
        with self._lk:
            if self.exhausted:
                return
            self.exhausted = True
            self.observed_limit = int(self.used)
            LOG.warn(f"DART 일일 한도에 실제로 도달했습니다 (status=020). "
                     f"이 키의 관측 한도 = {self.observed_limit:,}건 — 다음 실행부터 이 값을 씁니다. "
                     f"KST 자정({kst_seconds_to_reset() // 3600}시간 후) 초기화됩니다. "
                     f"여기까지 받은 데이터는 캐시에 저장되어 있으므로 재실행 시 정확히 이어받습니다.")
            self._save(force=True)

    def plan(self, need_calls: int, label: str) -> int:
        """이번 배치에서 '실제로 쓸 수 있는' 호출 수를 돌려준다. 미리 자르지 않는다.

        need <= remaining  → need 그대로 (전량 수행)
        need >  remaining  → remaining 만큼만 수행하고 나머지는 다음 실행으로 이월.
                             (예전처럼 19,000 에서 임의로 멈추는 게 아니라, 실제 잔량 기준)
        """
        rem = self.remaining()
        src = "관측" if self.limit_is_observed() else "기본값(미관측)"
        if need_calls <= rem:
            LOG.info(f"[DART 예산] {label}: 필요 {need_calls:,}건 / 잔여 {rem:,}건 "
                     f"(한도 {self.limit:,} {src}, 사용 {self.used:,}) → 전량 수행")
            return need_calls
        LOG.warn(f"[DART 예산] {label}: 필요 {need_calls:,}건 > 잔여 {rem:,}건 "
                 f"(한도 {self.limit:,} {src}) → 이번 실행은 {rem:,}건만 받고 "
                 f"나머지 {need_calls - rem:,}건은 KST 자정 이후 재실행 시 이어받습니다.")
        return rem

    def close(self):
        self._save(force=True)

    def report(self):
        LOG.table([
            ["키 식별자", self.key_id],
            ["기준일 (KST)", self.today],
            ["사용 (HTTP 요청 수)", f"{self.used:,}"],
            ["논리 호출 수", f"{self.calls_api:,}"],
            ["한도", f"{self.limit:,} ({'관측됨' if self.limit_is_observed() else '기본값 — 미관측'})"],
            ["잔여", f"{self.remaining():,}"],
            ["한도초과(020) 수신", "예 — 하드 스톱" if self.exhausted else "아니오"],
            ["KST 초기화까지", f"{kst_seconds_to_reset() // 3600}시간 "
                               f"{kst_seconds_to_reset() % 3600 // 60}분"],
        ], ["항목", "값"], ["l", "r"], title="DART 호출량 (실시간 추적 · 한도는 관측으로 학습)")


DQ: Optional[DartQuota] = None


def dart_api(endpoint: str, params: dict, source: str = "dart", tries: int = 2) -> Optional[dict]:
    """DART 호출 1건. 예산은 '최악(tries회)'을 먼저 예약하고 실제 시도 수만큼만 남긴다.

    http_get 은 내부적으로 최대 tries 회 실제 요청을 보낸다. 호출당 1건으로 세면
    실사용량을 최대 tries 배 과소집계한다 — 그래서 예약 후 환급하는 구조다.
    """
    if not DART_API_KEY:
        return None
    if DQ is not None and not DQ.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DQ is not None:
        DQ.refund(max(0, tries - max(1, attempts["n"])))
        DQ.calls_api += 1
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DQ is not None:
                DQ.mark_exhausted()          # ★ 이제 진짜로 멈춘다
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요 (https://opendart.fss.or.kr → 인증키 신청/관리).")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def dart_probe() -> Tuple[bool, str]:
    """카나리 (SPEC §2.3): 전체 수집 전에 1건으로 도달 가능성을 먼저 확인한다."""
    if not DART_API_KEY:
        return False, "키 미입력 — DART 경로 건너뜀 (KRX 스냅샷만으로 BM 산출)"
    if DQ is not None and DQ.exhausted:
        return False, "오늘 한도 초과(020) 상태 — KST 자정 이후 재시도"
    js = dart_api("list.json", {"bgn_de": "20240102", "end_de": "20240102",
                                "page_no": 1, "page_count": 1}, tries=1)
    if js is None:
        return False, "응답 없음/오류 — 키 또는 네트워크 확인"
    return True, "정상"


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자. 없으면 법정기한으로 보수적 추정 (미래누수 방지)."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


_EQUITY_PAT = re.compile(r"자본총계|^ifrs-full_Equity$|^ifrs_Equity$")


def fetch_dart_equity(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """§6.3 BM 의 DART 폴백 — 자본총계(장부가)만 배치로 받는다.

    fnlttMultiAcnt 는 1회 호출에 100개사를 처리하므로, 2,500사 × 11년 × 4보고서라도
    2500/100 × 11 × 4 ≈ 1,100 호출이면 끝난다. 전체 재무제표(fnlttSinglAcntAll)를
    사별로 긁으면 11만 호출이 필요하다 — 애초에 그렇게 설계하면 안 되는 것이다.
    """
    cols = ["corp_code", "bsns_year", "reprt_code", "equity", "period_end",
            "knowledge_date", "event_date"]
    cached = VAULT.get_table("dart_equity_quarterly", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        try:
            have = set(zip(cached["corp_code"].astype(str),
                           cached["bsns_year"].astype(int),
                           cached["reprt_code"].astype(str)))
        except Exception:
            have = set()
    if not DART_API_KEY or DQ is None or DQ.exhausted:
        return cached if cached is not None else pd.DataFrame(columns=cols)

    codes = sorted({str(c).zfill(8) for c in corp_codes if str(c).strip() and str(c) != "nan"})
    batches = [codes[i:i + DART_MULTI_BATCH] for i in range(0, len(codes), DART_MULTI_BATCH)]
    jobs = [(b, y, rc) for y in years for rc in REPRT_CODES.values() for b in batches
            if not all((c, int(y), rc) in have for c in b)]
    if not jobs:
        LOG.ok(f"DART 자본총계: 캐시로 충족 ({len(cached):,}행) — 신규 호출 0건")
        return cached

    allowed = DQ.plan(len(jobs) * 2, "자본총계 배치(BM 폴백)") // 2
    if allowed <= 0:
        LOG.warn("DART 잔여 호출량이 없어 이번 실행은 캐시만 사용합니다.")
        return cached if cached is not None else pd.DataFrame(columns=cols)
    jobs = jobs[:allowed]

    def _one(job):
        b, y, rc = job
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(b), "bsns_year": str(y), "reprt_code": rc})
        if not js or not isinstance(js.get("list"), list):
            return None
        rows = []
        for it in js["list"]:
            nm = str(it.get("account_nm", ""))
            aid = str(it.get("account_id", ""))
            if not (_EQUITY_PAT.search(nm) or _EQUITY_PAT.search(aid)):
                continue
            v = re.sub(r"[^\d\-]", "", str(it.get("thstrm_amount", "")))
            if not v or v == "-":
                continue
            mm, dd = REPRT_PERIOD_END.get(rc, (12, 31))
            rows.append({
                "corp_code": str(it.get("corp_code", "")).zfill(8),
                "bsns_year": int(y), "reprt_code": rc, "equity": float(v),
                "period_end": as_ts(f"{y}-{mm:02d}-{dd:02d}"),
                "knowledge_date": _knowledge_from_rcept(it.get("rcept_no"), rc, int(y)),
            })
        return pd.DataFrame(rows) if rows else None

    got = pmap_io(_one, jobs, workers=min(4, N_WORKERS_IO), desc="DART 자본총계")
    frames = [d for d in got if d is not None and len(d)]
    if cached is not None and len(cached):
        frames.append(cached)
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["corp_code", "bsns_year", "reprt_code"], keep="last")
    out = pit_frame(out, "period_end", "knowledge_date", source="dart")
    VAULT.put_table("dart_equity_quarterly", out, scope="shared", domain="dart",
                    source="opendart fnlttMultiAcnt (equity only)")
    LOG.ok(f"DART 자본총계 {len(out):,}행 (신규 호출 {DQ.calls_api:,}건, 잔여 {DQ.remaining():,}건)")
    return out
