

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  Phase 예산 · 열화 사다리 · 실행 매니페스트 · 드라이브 루트 해석                     ║
# ║                                                                                          ║
# ║  입력: 없음        출력: PhaseBudget / degrade() / MANIFEST / resolve_gdrive_root()       ║
# ║                                                                                          ║
# ║  ★ 명세 §3.2 의 핵심 의미론: 예산 하드캡에 도달해도 **예외를 던지지 않는다.**              ║
# ║    현재까지 수집분을 저장하고, 열화 사다리를 한 단계 내려간 뒤, 그 사실을 로그와            ║
# ║    run_manifest.json 에 명시적으로 남긴다. 조용히 잘린 결과가 가장 위험하다.               ║
# ║  ★ L5(IR협의회 단독으로 축소)는 전략 취지를 훼손하므로 **자동 적용 금지**. 예외를 던진다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MANIFEST: Dict[str, Any] = {
    "strategy_id": STRATEGY_ID,
    "build_version": BUILD_VERSION,
    "started_at": _dt.datetime.now().isoformat(timespec="seconds"),
    "run_mode": RUN_MODE,
    "seed": SEED,
    "backtest_window_requested": [BACKTEST_START, BACKTEST_END],
    "degradation_applied": [],
    "phase_seconds": {},
    "phase_budget_seconds": dict(NCQ_PHASE_BUDGET_S),
    "notes": [],
}


def manifest_put(key: str, value: Any) -> None:
    """매니페스트 갱신. 직렬화 불가 값은 문자열로 낮춰 저장한다(매니페스트가 실패의 원인이 되면 안 된다)."""
    try:
        json.dumps({key: value}, ensure_ascii=False, default=str)
        MANIFEST[key] = value
    except Exception:
        MANIFEST[key] = str(value)


def manifest_note(msg: str) -> None:
    MANIFEST.setdefault("notes", []).append(f"[{_dt.datetime.now():%H:%M:%S}] {msg}")


# ── 열화 사다리 (명세 §3.3) ─────────────────────────────────────────────────────────────────
LADDER: "OrderedDict[str, str]" = OrderedDict([
    ("L1", "한경컨센서스 소스 드롭 (전략 취지 손상: 낮음 — 이미 선택 소스)"),
    ("L2", "PDF 텍스트 추출을 앞 6페이지로 제한 (낮음 — 투자포인트는 전면부 집중)"),
    ("L3", "백테스트 윈도우 10년 → 7년 (중간 — 검정력 감소)"),
    ("L4", "유니버스 하위 1000 → 하위 700 (중간 — 이벤트 수 감소)"),
    ("L5", "인덱스 수집을 IR협의회 단독으로 축소 (높음 — 자동 적용 금지)"),
])
_DEGRADED: "OrderedDict[str, str]" = OrderedDict()


def degrade(level: str, reason: str) -> None:
    """열화 단계를 적용한다. 같은 단계를 두 번 적용해도 부작용이 없어야 한다(멱등)."""
    level = str(level).upper()
    if level not in LADDER:
        raise ValueError(f"알 수 없는 열화 단계: {level} (가능: {list(LADDER)})")
    if level == "L5":
        raise KillCriteria(
            "열화 L5(IR협의회 단독 축소)는 자동 적용이 금지되어 있습니다(명세 §3.3). "
            "L4 까지 적용해도 예산을 못 맞추면 실행을 중단하고 사용자 판단을 요청합니다. "
            f"사유: {reason}")
    if level in _DEGRADED:
        return
    _DEGRADED[level] = reason
    MANIFEST["degradation_applied"] = [{"level": k, "reason": v} for k, v in _DEGRADED.items()]
    LOG.warn(f"⚠ 열화 사다리 {level} 적용 — {LADDER[level]}  |  사유: {reason}")
    manifest_note(f"열화 {level} 적용: {reason}")

    # 단계별 실제 부작용을 여기서 한 번에 반영한다(호출측이 잊어버릴 수 없도록).
    G = globals()
    if level == "L1":
        G["RESEARCH_SOURCES"] = [s for s in RESEARCH_SOURCES if s != "hankyung"]
        LOG.info(f"  → 활성 리서치 소스: {G['RESEARCH_SOURCES']}")
    elif level == "L2":
        G["NCQ_PDF_MAX_PAGES"] = 6
        LOG.info("  → PDF 텍스트 추출을 앞 6페이지로 제한합니다.")
    elif level == "L3":
        new_start = (as_ts(BACKTEST_END) - pd.DateOffset(years=7) + pd.Timedelta(days=1))
        G["BACKTEST_START"] = new_start.strftime("%Y-%m-%d")
        LOG.info(f"  → 백테스트 시작을 {G['BACKTEST_START']} 로 축소합니다. "
                 f"BH-FDR 임계는 그대로 두되 검정력 감소를 리포트에 명시합니다.")
    elif level == "L4":
        G["NCQ_UNIVERSE_BOTTOM_N"] = 700
        LOG.info("  → 유니버스를 시총 하위 700 종목으로 축소합니다.")


def degraded() -> List[str]:
    return list(_DEGRADED.keys())


def is_degraded(level: str) -> bool:
    return str(level).upper() in _DEGRADED


NCQ_PDF_MAX_PAGES = 0        # 0 = 전체. degrade("L2") 가 6 으로 바꾼다.


# ── Phase 예산 가드 ─────────────────────────────────────────────────────────────────────────
class PhaseBudget:
    """Phase 별 시간 예산. 캡 도달 시 check() 가 False 를 돌려주고 **예외는 던지지 않는다.**

    사용법:
        with PhaseBudget("P1", NCQ_PHASE_BUDGET_S["P1"], on_exceed="L3") as B:
            for job in jobs:
                if not B.check():
                    break                      # 부분 결과를 저장하고 정상 종료
                ...

    ★ time.monotonic() 을 쓴다. time.time() 은 NTP 보정으로 뒤로 갈 수 있어서
      장시간 실행 중 예산이 음수가 되는 사고가 실제로 난다.
    """

    _spent: Dict[str, float] = {}

    def __init__(self, name: str, cap_seconds: float, on_exceed: Optional[str] = None,
                 quiet: bool = False):
        self.name = str(name)
        self.cap = float(cap_seconds) if cap_seconds and cap_seconds > 0 else float("inf")
        self.on_exceed = on_exceed
        self.quiet = quiet
        self.t0 = time.monotonic()
        self.exceeded = False
        self._warned = False

    # -- 컨텍스트 --------------------------------------------------------------------------
    def __enter__(self) -> "PhaseBudget":
        self.t0 = time.monotonic()
        if not self.quiet:
            LOG.info(f"[{self.name}] 예산 {self.cap/60:.0f}분 — 시작")
        return self

    def __exit__(self, exc_type, exc, tb):
        el = self.elapsed()
        PhaseBudget._spent[self.name] = PhaseBudget._spent.get(self.name, 0.0) + el
        MANIFEST["phase_seconds"][self.name] = round(PhaseBudget._spent[self.name], 1)
        if not self.quiet:
            pct = 100.0 * el / self.cap if np.isfinite(self.cap) and self.cap > 0 else float("nan")
            LOG.info(f"[{self.name}] 종료 — {el/60:.1f}분 / 예산 {self.cap/60:.0f}분"
                     + (f" ({pct:.0f}%)" if np.isfinite(pct) else ""))
        return False        # 예외를 삼키지 않는다

    # -- 조회 ------------------------------------------------------------------------------
    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.t0)

    def frac(self) -> float:
        return self.elapsed() / self.cap if np.isfinite(self.cap) and self.cap > 0 else 0.0

    def remaining(self) -> float:
        return max(0.0, self.cap - self.elapsed()) if np.isfinite(self.cap) else float("inf")

    def check(self) -> bool:
        """캡 도달 시 False. 최초 1회만 경고하고 on_exceed 열화를 적용한다."""
        if self.elapsed() < self.cap:
            return True
        self.exceeded = True
        if not self._warned:
            self._warned = True
            LOG.warn(f"[{self.name}] 시간 예산 {self.cap/60:.0f}분을 초과했습니다 — "
                     f"여기까지 수집된 결과를 저장하고 정상 종료합니다(예외 아님).")
            manifest_note(f"{self.name} 예산 초과 ({self.elapsed()/60:.1f}분)")
            if self.on_exceed:
                try:
                    degrade(self.on_exceed, f"{self.name} 예산 초과")
                except KillCriteria:
                    raise
                except Exception as e:                       # noqa
                    LOG.warn(f"열화 적용 실패({type(e).__name__}) — 계속 진행합니다.")
        return False

    @classmethod
    def total_spent(cls) -> float:
        return float(sum(cls._spent.values()))

    @classmethod
    def report(cls) -> None:
        if not cls._spent:
            return
        rows = []
        for k in ("P0", "P1", "P2", "P3", "P4", "P5", "P6"):
            if k not in cls._spent:
                continue
            cap = NCQ_PHASE_BUDGET_S.get(k, 0)
            sp = cls._spent[k]
            rows.append([k, f"{sp/60:7.1f}분", f"{cap/60:5.0f}분",
                         f"{100*sp/cap:5.0f}%" if cap else "—",
                         "✔ 예산 내" if (not cap or sp <= cap) else "❗ 초과"])
        tot = cls.total_spent()
        rows.append(["합계", f"{tot/60:7.1f}분", f"{NCQ_TOTAL_BUDGET_S/60:5.0f}분",
                     f"{100*tot/NCQ_TOTAL_BUDGET_S:5.0f}%",
                     "✔ 4시간 이내" if tot <= NCQ_TOTAL_BUDGET_S else "❗ 4시간 초과"])
        LOG.table(rows, ["Phase", "실측", "예산", "소진율", "판정"], ["c", "r", "r", "r", "l"],
                  title="Phase 시간 예산 (명세 §3.1 — 하드캡 4시간)")
        if degraded():
            LOG.table([[lv, LADDER[lv], _DEGRADED[lv]] for lv in degraded()],
                      ["단계", "조치", "발동 사유"], ["c", "l", "l"],
                      title="적용된 열화 사다리 (리포트 최상단에도 표시됩니다)")


# ── 구글드라이브 루트 해석 (Colab / JupyterLab / Windows 양방향) ────────────────────────────
def _ncq_drive_candidates() -> List[str]:
    """드라이브 루트 후보를 우선순위대로. 존재 검사는 호출측에서 한다."""
    home = os.path.expanduser("~")
    leaf = "tcd_cache"          # ★ 공용 인덱스를 TCD v2 와 공유하려면 같은 루트를 써야 한다
    cands = [
        os.environ.get("ARC_NCQ_GDRIVE_ROOT", ""),
        os.environ.get("GDRIVE_ROOT", ""),
        "/content/drive/MyDrive/" + leaf,
        os.path.join(home, "Google Drive", "내 드라이브", leaf),
        os.path.join(home, "Google Drive", "My Drive", leaf),
        os.path.join(home, "GoogleDrive", "MyDrive", leaf),
        os.path.join(home, "Google 드라이브", "내 드라이브", leaf),
    ]
    # 윈도우 드라이브 문자 마운트 (구글 드라이브 데스크톱 기본 G:)
    for dl in ("G:", "H:", "I:"):
        cands.append(os.path.join(dl + os.sep, "내 드라이브", leaf))
        cands.append(os.path.join(dl + os.sep, "My Drive", leaf))
    return [c for c in cands if c]


def resolve_gdrive_root() -> str:
    """GDRIVE_ROOT 를 환경에 맞게 확정하고 전역에 반영한다.

    ★ 하드코딩된 '/content/...' 를 절대 그대로 쓰지 않는다(명세 §13.2). Colab 이면 마운트를
      시도하고, 아니면 이미 동기화된 드라이브 폴더를 찾고, 그마저 없으면 로컬로 폴백한다.
      어느 경로가 선택됐는지는 반드시 로그와 매니페스트에 남긴다.
    """
    G = globals()
    explicit = str(GDRIVE_ROOT or "").strip()
    if explicit:
        os.makedirs(explicit, exist_ok=True)
        G["GDRIVE_ROOT"] = explicit
        manifest_put("gdrive_root", explicit)
        manifest_put("gdrive_root_mode", "EXPLICIT")
        LOG.ok(f"드라이브 루트(사용자 지정): {explicit}")
        return explicit

    if ENV.get("colab"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            if not os.path.isdir("/content/drive/MyDrive"):
                LOG.info("Colab 구글드라이브 마운트를 시도합니다 — 인증 팝업을 승인해 주세요.")
                _gdrive.mount("/content/drive", force_remount=False)
        except Exception as e:                                  # noqa
            LOG.warn(f"Colab 드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다. "
                     f"이 경우 캐시가 세션 종료와 함께 사라지므로 재실행 비용이 큽니다.")

    for c in _ncq_drive_candidates():
        try:
            if os.path.isdir(c) or os.path.isdir(os.path.dirname(c)):
                os.makedirs(c, exist_ok=True)
                G["GDRIVE_ROOT"] = c
                manifest_put("gdrive_root", c)
                manifest_put("gdrive_root_mode", "AUTO_DRIVE")
                LOG.ok(f"드라이브 루트(자동 탐색): {c}")
                return c
        except Exception:
            continue

    root = os.path.abspath(LOCAL_CACHE_ROOT)
    os.makedirs(root, exist_ok=True)
    G["GDRIVE_ROOT"] = root
    manifest_put("gdrive_root", root)
    manifest_put("gdrive_root_mode", "LOCAL_FALLBACK")
    LOG.warn(f"구글드라이브를 찾지 못해 로컬 캐시를 사용합니다: {root}\n"
             f"    드라이브를 쓰려면 상단 GDRIVE_ROOT 에 경로를 직접 적어주세요 "
             f"(예: r\"G:\\내 드라이브\\tcd_cache\").")
    return root


def ncq_adopt_dirs() -> List[str]:
    """빈 문자열을 GDRIVE_ROOT 로 치환하고 중복·미존재를 정리한 스캔 대상 목록."""
    out, seen = [], set()
    for d in GDRIVE_ADOPT_DIRS:
        p = (d or "").strip() or GDRIVE_ROOT
        if not p:
            continue
        rp = os.path.abspath(p)
        if rp in seen or not os.path.isdir(rp):
            continue
        seen.add(rp)
        out.append(rp)
    return out
