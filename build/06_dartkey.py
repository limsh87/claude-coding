# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  DART 인증키 풀 — '미리 정한 상한'이 아니라 '실시간 남은 호출량'을 쓴다               ║
# ║                                                                                          ║
# ║  ★ 설계 원칙 (예전 코드의 잘못을 명시적으로 뒤집는다)                                       ║
# ║    (구) DART_DAILY_LIMIT = 19,000 을 하드코딩 → 실제로 남은 양과 무관하게 미리 잘랐다.      ║
# ║         · 이미 오늘 5,000 을 썼든 0 을 썼든 똑같이 19,000 을 가정 → 과대 또는 과소 사용     ║
# ║         · 키가 여러 개여도 한 개 분량만 사용 → 남는 한도를 통째로 버렸다                    ║
# ║    (신) 상한을 두지 않는다. **서버가 status=020(요청 제한 초과)을 줄 때까지 쓴다.**          ║
# ║         · 멈추는 근거는 항상 서버의 응답이다. 우리 추정치가 아니다.                          ║
# ║         · 키가 여러 개면 020 을 받은 키만 오늘 소진 처리하고 다음 키로 자동 전환한다.        ║
# ║           → 가용 호출량 = 20,000 × 키 개수. 키 2개면 4만, 3개면 6만.                        ║
# ║         · 사용량은 (키해시, 날짜)로 드라이브에 영속 기록 → 재실행 시 남은 양을 즉시 안다.    ║
# ║           이 기록은 **표시·계획용**이며 게이트가 아니다. 실제 한도가 더 남아 있으면 더 쓴다. ║
# ║                                                                                          ║
# ║  ★ 왜 상한을 신뢰하면 안 되는가                                                            ║
# ║    같은 키를 다른 노트북·다른 전략이 함께 쓸 수 있고, DART 의 한도 리셋은 KST 자정 기준이며, ║
# ║    재시도(http_get 내부 tries)까지 실사용량에 포함된다. 로컬 카운터는 언제나 틀릴 수 있다.   ║
# ║    → 로컬 카운터는 '얼마나 남았을까'를 사람에게 보여주는 용도로만 쓰고,                      ║
# ║      '멈춰야 하는가'는 오직 서버의 020 응답으로 판단한다.                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_API_BASE = "https://opendart.fss.or.kr/api/"
DART_QUOTA_PER_KEY = 20_000      # 공식 일일 한도. ★게이트가 아니라 '남은 양' 표시용 기준치★
DART_SOFT_RESERVE = 0            # >0 이면 키당 그만큼 남겨두고 전환(다른 작업용 예약). 0=끝까지
_DART_ST_FALLBACK = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


def _dart_status_msg(st: str) -> str:
    return (globals().get("DART_STATUS_MSG") or _DART_ST_FALLBACK).get(str(st), "?")


def _dart_keys_configured() -> List[str]:
    """설정된 DART 키를 순서대로 모은다(중복 제거).

    받는 곳: 단일키 DART_API_KEY / 다중키 DART_API_KEYS / 환경변수 DART_API_KEY·DART_API_KEYS.
    ▶ 키는 opendart.fss.or.kr 에서 계정당 즉시·무료 발급된다. 계정을 더 만들면 키가 늘고,
      키가 늘면 일일 가용 호출량이 그만큼 선형으로 늘어난다(20,000 × 키 개수).
    """
    src: List[Any] = [globals().get("DART_API_KEY", "")]
    src.extend(list(globals().get("DART_API_KEYS", []) or []))
    src.extend(re.split(r"[,\s]+", os.environ.get("DART_API_KEYS", "") or ""))
    src.append(os.environ.get("DART_API_KEY", ""))
    out: List[str] = []
    seen: set = set()
    for k in src:
        k = str(k or "").strip()
        if len(k) >= 20 and k not in seen:      # DART 키는 40자 hex. 오타·자리표시자 방어
            seen.add(k)
            out.append(k)
    return out


class DartKeyPool:
    """DART 호출량을 실시간으로 관리한다. 상한을 미리 정하지 않는다."""

    def __init__(self, keys: Optional[Sequence[str]] = None):
        self.keys: List[str] = list(keys) if keys is not None else _dart_keys_configured()
        self.today = _dt.date.today().isoformat()
        self.used: Dict[str, int] = {}
        self.dead: Dict[str, str] = {}          # kid -> 사유코드
        self.calls = 0                           # 이번 실행에서 실제로 보낸 요청 수
        self._lk = threading.Lock()
        self._since_save = 0
        self._warned_over = set()
        self._load()

    # ── 영속화 ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _kid(key: str) -> str:
        return hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _mask(key: str) -> str:
        s = str(key)
        return f"{s[:6]}…{s[-4:]}" if len(s) > 12 else "****"

    def _path(self) -> Optional[str]:
        try:
            d = os.path.join(VAULT.ns["private"], "state")
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "_dart_quota.json")   # 앞의 '_' → 인덱스 스캔 대상 아님
        except Exception:
            return None

    def _load(self):
        p = self._path()
        if not p or not os.path.exists(p):
            return
        try:
            j = json.loads(open(p, encoding="utf-8").read())
        except Exception:
            return
        if str(j.get("date")) != self.today:
            return                                   # 날짜가 바뀌면 한도는 리셋된다
        # 어제의 '소진' 상태는 물려받지 않는다(self.dead 는 비운 채로 시작).
        # 020 은 오늘 다시 받아야 소진이다 — 한도는 날짜가 바뀌면 리셋되기 때문이다.
        self.used = {str(k): int(v) for k, v in (j.get("used") or {}).items()}
        n_prior = sum(self.used.values())
        if n_prior:
            LOG.info(f"오늘 이미 사용한 DART 호출 {n_prior:,}건이 기록되어 있습니다 — "
                     f"남은 양부터 이어서 씁니다(추정 잔량 {self.remaining_hint():,}건).")

    def _save_locked(self):
        p = self._path()
        if not p:
            return
        try:
            atomic_write_text(p, json.dumps(
                {"date": self.today, "used": self.used}, ensure_ascii=False))
        except Exception:
            pass

    def save(self):
        with self._lk:
            self._save_locked()

    # ── 상태 조회 ───────────────────────────────────────────────────────────────────────
    def configured(self) -> bool:
        return bool(self.keys)

    def alive(self) -> List[str]:
        return [k for k in self.keys if self._kid(k) not in self.dead]

    @property
    def exhausted(self) -> bool:
        """살아 있는 키가 하나도 없다 = 오늘은 더 못 받는다(서버가 그렇게 답했다)."""
        return bool(self.keys) and not self.alive()

    def remaining_hint(self) -> int:
        """남은 호출량 **추정치**. 계획·표시용이며 멈춤 판단에는 쓰지 않는다."""
        tot = 0
        for k in self.alive():
            tot += max(0, DART_QUOTA_PER_KEY - DART_SOFT_RESERVE - self.used.get(self._kid(k), 0))
        return tot

    def acquire(self) -> Optional[str]:
        """지금 써야 할 키. 소진된 키는 건너뛴다. 없으면 None."""
        with self._lk:
            for k in self.keys:
                kid = self._kid(k)
                if kid in self.dead:
                    continue
                if DART_SOFT_RESERVE > 0 and \
                        self.used.get(kid, 0) >= DART_QUOTA_PER_KEY - DART_SOFT_RESERVE:
                    continue                       # 예약분은 남긴다(사용자가 명시했을 때만)
                return k
            return None

    def spend(self, key: str, n: int = 1):
        if n <= 0:
            return
        kid = self._kid(key)
        with self._lk:
            self.used[kid] = self.used.get(kid, 0) + n
            self.calls += n
            self._since_save += n
            over = self.used[kid] > DART_QUOTA_PER_KEY and kid not in self._warned_over
            if self._since_save >= 200:
                self._since_save = 0
                self._save_locked()
        if over:
            self._warned_over.add(kid)
            LOG.info(f"키 {self._mask(key)} 의 오늘 사용량이 공식 한도({DART_QUOTA_PER_KEY:,})를 "
                     f"넘었는데도 서버가 정상 응답 중입니다 — 추정치보다 실제 잔량이 많다는 뜻이라 "
                     f"계속 진행합니다(멈춤 판단은 서버의 020 응답으로만 합니다).")

    def mark_exhausted(self, key: str, reason: str = "020"):
        kid = self._kid(key)
        with self._lk:
            if kid in self.dead:
                return
            self.dead[kid] = str(reason)
            if str(reason) in ("020", "021"):
                # 서버가 한도 초과라고 했으니 오늘 이 키의 잔량은 0 이다. 기록을 진실에 맞춘다.
                self.used[kid] = max(self.used.get(kid, 0), DART_QUOTA_PER_KEY)
            n_alive = len([k for k in self.keys if self._kid(k) not in self.dead])
            self._save_locked()
        if str(reason) in ("020", "021"):
            if n_alive:
                LOG.info(f"키 {self._mask(key)} 일일 한도 소진(status={reason}) — "
                         f"남은 키 {n_alive}개로 자동 전환합니다(추정 잔량 {self.remaining_hint():,}건).")
            else:
                LOG.warn(f"모든 DART 키의 오늘 한도가 소진되었습니다(status={reason}). "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일 같은 코드를 "
                         f"다시 실행하면 정확히 이 지점부터 이어받습니다. "
                         f"오늘 안에 끝내려면 키를 더 넣으세요 → DART_API_KEYS 에 나열하면 "
                         f"가용량이 20,000 × 키개수 로 늘어납니다.")
        else:
            LOG.error(f"DART 키 {self._mask(key)} 사용 불가 status={reason} "
                      f"({_dart_status_msg(reason)}) — 이 키를 제외하고 진행합니다.")

    def report(self, title: str = "DART 호출량 (실시간)"):
        if not self.keys:
            LOG.info("DART 키가 없습니다 — DART 경로는 건너뜁니다.")
            return
        rows = []
        for i, k in enumerate(self.keys, 1):
            kid = self._kid(k)
            u = self.used.get(kid, 0)
            st = ("소진(020)" if self.dead.get(kid) in ("020", "021")
                  else (f"제외({self.dead[kid]})" if kid in self.dead else "가용"))
            rem = "-" if kid in self.dead else f"{max(0, DART_QUOTA_PER_KEY - u):,}"
            rows.append([f"#{i} {self._mask(k)}", f"{u:,}", rem, st])
        rows.append(["합계", f"{sum(self.used.values()):,}", f"{self.remaining_hint():,}", ""])
        LOG.table(rows, ["키", "오늘 사용", "남은(추정)", "상태"], ["l", "r", "r", "l"],
                  title=title)


DKEY: Optional[DartKeyPool] = None


def dart_pool() -> DartKeyPool:
    """키 풀 싱글턴. VAULT 준비 이후 최초 호출 시점에 만들어진다(지연 초기화)."""
    global DKEY
    if DKEY is None:
        DKEY = DartKeyPool()
        globals()["DKEY"] = DKEY
    return DKEY


def dart_json(endpoint: str, params: dict, source: str = "dart",
              tries: int = 2, _depth: int = 0) -> Optional[dict]:
    """DART API 호출 1건. 키 선택·사용량 집계·020 자동 전환을 여기서 전담한다.

    · endpoint 는 "list.json" 같은 상대경로도, 전체 URL 도 받는다.
    · 반환 None 의 의미는 '이 요청은 쓸 데이터가 없다'이다. **중단 판단은 dart_pool().exhausted
      로 하라.** (013 조회없음 과 020 한도소진 을 반환값으로 구분하지 않는다)
    """
    pool = dart_pool()
    key = pool.acquire()
    if not key:
        return None
    url = endpoint if str(endpoint).startswith("http") else \
        (globals().get("DART_BASE") or DART_API_BASE) + str(endpoint)
    p = dict(params or {})
    p["crtfc_key"] = key
    att = {"n": 0}
    js = http_json(url, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: att.__setitem__("n", att["n"] + 1))
    # ★ 실사용량 = 실제로 보낸 요청 수. http_get 내부 재시도까지 DART 한도를 깎는다.
    pool.spend(key, max(1, att["n"]))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st in ("020", "021", "010", "011", "012", "901"):
        pool.mark_exhausted(key, st)
        if _depth + 1 < len(pool.keys) and pool.acquire():
            return dart_json(endpoint, params, source=source, tries=tries, _depth=_depth + 1)
        return None
    if st and st != "000":
        if st != "013":
            LOG.debug(f"DART status={st} ({_dart_status_msg(st)}) ep={endpoint}")
        return None
    return js


def dart_plan_note(n_jobs: int, what: str) -> None:
    """수집 계획과 실시간 잔량을 나란히 찍는다. '왜 오늘 다 못 받는가'를 숨기지 않는다."""
    pool = dart_pool()
    if not pool.configured():
        return
    rem = pool.remaining_hint()
    LOG.info(f"{what}: 신규 호출 대상 {n_jobs:,}건 · 오늘 남은 추정 호출량 {rem:,}건 "
             f"(키 {len(pool.alive())}/{len(pool.keys)}개 가용)")
    if n_jobs > rem and rem >= 0:
        need_keys = max(1, math.ceil(n_jobs / max(DART_QUOTA_PER_KEY, 1)))
        LOG.warn(f"필요 호출({n_jobs:,})이 오늘 남은 추정 잔량({rem:,})보다 많습니다. "
                 f"상한으로 미리 자르지 않고 서버가 한도초과(020)를 줄 때까지 받은 뒤 저장합니다. "
                 f"중요도 순으로 정렬돼 있어 중간에 끊겨도 쓸모 있는 구간부터 채워집니다. "
                 f"하루에 끝내려면 DART 키를 {need_keys}개까지 늘려 DART_API_KEYS 에 넣으세요.")
