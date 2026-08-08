

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  API 호출 예산 — **하드코딩하지 않고 실시간으로 추적·학습한다**                      ║
# ║                                                                                          ║
# ║  이전 세대 설계의 잘못: 한도를 19,000 으로 미리 못박아 두고 그 숫자에 닿으면 멈췄다.       ║
# ║  실제 한도는 계정·시점·엔드포인트에 따라 다르고, 이미 쓴 양도 알 수 없으니 그 숫자는       ║
# ║  근거가 없다. 남아 있는데 멈추거나(낭비), 없는데 계속 두드리는(차단) 두 실패가 다 난다.    ║
# ║                                                                                          ║
# ║  이 구현이 하는 일:                                                                       ║
# ║   ① 오늘 사용량을 드라이브에 영속 기록 → 재실행/다른 노트북에서도 이어받는다               ║
# ║   ② **실제로 status=020(한도초과)이 올 때까지 멈추지 않는다**                              ║
# ║   ③ 020 이 온 순간의 사용량을 '관측된 실제 한도'로 학습해 이후 실행의 잔여량 표시에 쓴다   ║
# ║   ④ 잔여량을 진행 중 계속 로그에 표시한다 (추정치인지 실측치인지 함께 표기)                ║
# ║   ⑤ 한도가 끊겨도 깨끗하게 멈추고, 받은 만큼 저장하고, 이어받을 지점을 알려준다            ║
# ║                                                                                          ║
# ║  ▶ 애초에 이 전략은 DART 요구량이 작다. 재무제표를 회사별로 받지 않고 실적발표일·공시건수만 ║
# ║    시장 전체 스윕으로 받으므로 10년 콜드빌드가 2,000~4,000 호출이다. 한도가 모자랄 일이     ║
# ║    구조적으로 없다 — 모자랐다면 그건 설계가 비효율적이었다는 뜻이다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_LIMIT_HINT = 20_000        # 공식 고지값(추정 시작점). 실측되면 학습값이 이걸 대체한다.


class ApiQuota:
    """일일 호출 예산 추적기. 한도를 '가정'하지 않고 '관측'한다."""

    def __init__(self, name: str, hint: int = DART_LIMIT_HINT, key: str = ""):
        self.name = name
        self.hint = int(hint)
        self.key_tag = sha1_str(name, key)[:10] if key else sha1_str(name)[:10]
        self.today = _dt.date.today().isoformat()
        self.used = 0
        self.observed_limit: Optional[int] = None   # 실측 한도 (020 이 온 시점의 사용량)
        self.exhausted = False
        self.blocked_reason = ""
        self._lk = threading.Lock()
        self._last_report = 0.0
        self._load()

    # ── 영속화 ------------------------------------------------------------------------
    def _path(self) -> str:
        base = VAULT.ns["private"] if VAULT is not None else "."
        return os.path.join(base, "index", f"quota_{self.name}_{self.key_tag}.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
        except Exception:
            return
        if j.get("date") == self.today:
            self.used = int(j.get("used", 0))
            self.exhausted = bool(j.get("exhausted", False))
        ol = j.get("observed_limit")
        if ol:
            self.observed_limit = int(ol)          # 한도 학습값은 날짜와 무관하게 유지
        if self.used or self.observed_limit:
            LOG.info(f"[{self.name}] 오늘 사용량 {self.used:,}건 이어받음 · "
                     f"한도 {self._limit_str()}")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps({
                "date": self.today, "used": self.used, "exhausted": self.exhausted,
                "observed_limit": self.observed_limit,
                "updated": _dt.datetime.now().isoformat(timespec="seconds"),
            }))
        except Exception:
            pass

    # ── 조회 --------------------------------------------------------------------------
    def limit(self) -> int:
        return int(self.observed_limit or self.hint)

    def _limit_str(self) -> str:
        return (f"{self.observed_limit:,} (실측)" if self.observed_limit
                else f"{self.hint:,} (고지값 추정)")

    def remaining(self) -> int:
        """남은 호출량. 실측 한도가 있으면 그것 기준, 없으면 고지값 기준.
        어느 쪽이든 이 값이 0이 되어도 **실제 020 이 오기 전까지는 멈추지 않는다**
        (추정이 틀렸을 수 있으므로 남아 있는 예산을 버리지 않는다)."""
        return max(0, self.limit() - self.used)

    def status_line(self) -> str:
        if self.exhausted:
            return f"[{self.name}] 소진 — 오늘 {self.used:,}건 사용 (실측 한도 {self.limit():,})"
        return (f"[{self.name}] 사용 {self.used:,} / 한도 {self._limit_str()} "
                f"· 잔여 약 {self.remaining():,}건")

    # ── 소비 --------------------------------------------------------------------------
    def take(self, k: int = 1) -> bool:
        """호출 직전에 예약한다. 소진이 '관측된' 뒤에만 False 를 돌려준다."""
        with self._lk:
            if self.exhausted:
                return False
            self.used += k
            if self.used % 250 == 0:
                self._save()
            now = time.time()
            if now - self._last_report > 30:
                self._last_report = now
                LOG.debug(self.status_line())
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.used = max(0, self.used - k)

    def mark_exhausted(self, reason: str = "status=020"):
        """소진을 **관측**했다. 이 시점의 사용량이 곧 실제 한도다 — 학습해서 다음에 쓴다."""
        with self._lk:
            if self.exhausted:
                return
            self.exhausted = True
            self.blocked_reason = reason
            prev = self.observed_limit
            self.observed_limit = int(self.used)
            self._save()
        LOG.warn(f"[{self.name}] 일일 호출 한도 소진을 확인했습니다 ({reason}). "
                 f"이번에 관측된 실제 한도는 {self.used:,}건입니다"
                 + (f" (직전 학습값 {prev:,})." if prev else ".") +
                 f" 지금까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 "
                 f"정확히 이 지점부터 이어받습니다. 이번 실행은 확보된 데이터만으로 계속합니다.")

    def mark_blocked(self, reason: str):
        """키 오류·IP 차단 등 한도와 무관한 차단. 재시도해도 소용없으므로 즉시 멈춘다."""
        with self._lk:
            self.exhausted = True
            self.blocked_reason = reason
            self._save()
        LOG.error(f"[{self.name}] 호출이 차단되었습니다 — {reason}. "
                  f"재시도하지 않고 이 소스를 건너뜁니다.")

    def close(self):
        self._save()

    def report(self):
        LOG.table([["오늘 사용량", f"{self.used:,}"],
                   ["한도", self._limit_str()],
                   ["잔여(추정)", f"{self.remaining():,}"],
                   ["소진 여부", ("예 — " + self.blocked_reason) if self.exhausted else "아니오"],
                   ["학습 방식", "실제 020 응답 시점의 사용량을 한도로 기록 → 다음 실행에서 사용"]],
                  ["항목", "값"], ["l", "r"],
                  title=f"{self.name} 호출 예산 (하드코딩 없음 · 실시간 추적)")


QUOTA: Dict[str, ApiQuota] = {}


def quota(name: str, hint: int = DART_LIMIT_HINT, key: str = "") -> ApiQuota:
    if name not in QUOTA:
        QUOTA[name] = ApiQuota(name, hint, key)
    return QUOTA[name]
