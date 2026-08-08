# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  캐시 루트 해석 + 런타임 예산 추적  (스펙 §3 · §10)                                  ║
# ║                                                                                          ║
# ║  스펙 §3: "Colab: drive.mount, 실패시 /content/tcd_cache.                                 ║
# ║            JupyterLab: Path.home()/tcd_cache. /content 하드코딩 금지."                     ║
# ║  → 코어의 _mount_drive() 는 LOCAL_CACHE_ROOT 를 그대로 돌려주므로 None 이면 죽는다.        ║
# ║    v3 는 그 앞단에서 '환경별 기본값'을 먼저 확정한다.                                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def resolve_local_cache_root() -> str:
    """LOCAL_CACHE_ROOT 가 비어 있을 때 환경에 맞는 기본 경로를 만든다.

    ★ /content 를 하드코딩하지 않는다. Colab 이 아닌 곳에서 /content 를 쓰면 권한 오류가
      나거나(리눅스 루트 직하), 최악의 경우 컨테이너 종료와 함께 캐시가 통째로 사라진다.
    """
    v = globals().get("LOCAL_CACHE_ROOT")
    if isinstance(v, str) and v.strip():
        return os.path.abspath(os.path.expanduser(v.strip()))
    if ENV.get("colab"):
        return "/content/tcd_cache"
    try:
        from pathlib import Path as _P
        return str(_P.home() / "tcd_cache")
    except Exception:
        return os.path.abspath("./tcd_cache")


def mount_cache_v3() -> Tuple[str, str]:
    """(루트경로, 상태). 어느 환경에서도 절대 None 을 돌려주지 않는다.

    우선순위
      Colab      : drive.mount → GDRIVE_ROOT           (실패 시 로컬 폴백)
      Jupyter/CLI: 이미 동기화된 드라이브 경로가 있으면 그것 → 없으면 홈 아래 로컬
    """
    local = resolve_local_cache_root()
    if ENV.get("colab"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                LOG.info("구글드라이브 마운트를 시도합니다. 브라우저에서 권한을 승인해 주세요.")
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                os.makedirs(GDRIVE_ROOT, exist_ok=True)
                return GDRIVE_ROOT, "COLAB_DRIVE"
            LOG.warn("드라이브가 마운트되지 않았습니다 — 로컬 캐시로 폴백합니다. "
                     "이번 실행의 수집물은 세션 종료 시 사라질 수 있습니다.")
            return local, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                                  # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return local, "COLAB_MOUNT_ERROR→LOCAL"

    # JupyterLab / CLI — 드라이브 데스크톱이 동기화해 둔 경로가 있으면 그것을 우선한다.
    for c in _gdrive_desktop_candidates():
        if c and os.path.isdir(c):
            os.makedirs(c, exist_ok=True)
            return c, "LOCAL_SYNCED_DRIVE"
    # 캐시 폴더는 없지만 드라이브 자체는 붙어 있는 경우 → 거기에 만들어 준다.
    #   ★ 이것이 없으면 첫 실행에서 조용히 홈 폴더로 폴백해, 수집물이 드라이브에
    #     한 줄도 남지 않는다(사용자 절대1원칙 위반). 부모가 실재할 때만 만든다.
    for c in _gdrive_desktop_candidates():
        par = os.path.dirname(c.rstrip("/\\"))
        if par and os.path.isdir(par):
            try:
                os.makedirs(c, exist_ok=True)
                LOG.ok(f"구글드라이브(데스크톱 동기화) 안에 캐시 폴더를 새로 만들었습니다: {c}")
                return c, "LOCAL_SYNCED_DRIVE"
            except Exception:
                continue
    os.makedirs(local, exist_ok=True)
    LOG.warn(f"구글드라이브 경로를 찾지 못해 로컬({local})에 저장합니다. "
             f"드라이브에 남기려면 상단 GDRIVE_ROOT 를 실제 드라이브 경로로 바꾸세요 "
             f"(예: Windows 'G:/내 드라이브/tcd_cache', macOS "
             f"'~/Library/CloudStorage/GoogleDrive-<계정>/My Drive/tcd_cache').")
    return local, "LOCAL"


def _gdrive_desktop_candidates() -> List[str]:
    """구글드라이브 '데스크톱' 동기화 폴더 후보. 환경마다 이름이 다르다.

    Windows 는 드라이브 문자(G:, H: …)로 붙고 한국어 계정은 '내 드라이브'다.
    macOS 는 최신 버전이 ~/Library/CloudStorage/GoogleDrive-<메일>/My Drive 로 바뀌었다.
    이 목록을 갖고 있지 않으면 JupyterLab 사용자는 매번 홈 폴더로 폴백한다.
    """
    out: List[str] = [GDRIVE_ROOT] if GDRIVE_ROOT else []
    leaf = os.path.basename(str(GDRIVE_ROOT).rstrip("/\\")) or "tcd_cache"
    home = os.path.expanduser("~")
    roots: List[str] = []
    if platform.system() == "Windows":
        # ★ 존재하지 않거나 '연결 끊긴 네트워크 드라이브'에 os.path.isdir 를 던지면 letter 당
        #   수 초씩 블로킹된다. 비트마스크로 **실재하는 드라이브만** 먼저 걸러낸다.
        letters = "GHIJKLMNOPQRSTUVWXYZ"
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()      # type: ignore[attr-defined]
            letters = "".join(L for L in letters
                              if mask >> (ord(L) - ord("A")) & 1)
        except Exception:
            pass
        for L in letters:
            roots += [f"{L}:/내 드라이브", f"{L}:/My Drive", f"{L}:/공유 드라이브"]
    roots += [os.path.join(home, "Google Drive", "My Drive"),
              os.path.join(home, "Google Drive", "MyDrive"),
              os.path.join(home, "GoogleDrive", "MyDrive"),
              os.path.join(home, "내 드라이브")]
    cs = os.path.join(home, "Library", "CloudStorage")
    try:
        for d in sorted(os.listdir(cs)):
            if d.startswith("GoogleDrive"):
                roots += [os.path.join(cs, d, "My Drive"), os.path.join(cs, d, "내 드라이브")]
    except Exception:
        pass
    out += [os.path.join(r, leaf) for r in roots]
    seen, uniq = set(), []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


# ── 런타임 예산 추적 (§10) ──────────────────────────────────────────────────────────────────
RUNTIME_ROWS: List[dict] = []
_RUNTIME_BUDGET_MIN = {
    "L0.준비": 3, "CANARY": 25, "수집": 95, "L1.센서+커버리지": 5,
    "L2+L3.백테스트": 2, "R-SUITE": 26,
}
WALL_CLOCK_LIMIT_H = 4.0        # §12-6 — 초과하면 구조 재점검 경고를 띄운다


def runtime_mark(phase: str, seconds: float, note: str = ""):
    RUNTIME_ROWS.append({"phase": phase, "seconds": float(seconds),
                         "minutes": float(seconds) / 60.0,
                         "budget_min": _RUNTIME_BUDGET_MIN.get(phase, np.nan), "note": note})


def report_runtime_v3(t0: float) -> pd.DataFrame:
    total_s = time.time() - t0
    rows = []
    for r in RUNTIME_ROWS:
        b = r["budget_min"]
        verdict = "-" if not np.isfinite(b) else ("초과" if r["minutes"] > b * 1.5 else "예산내")
        rows.append([r["phase"], f"{r['minutes']:.1f}",
                     "-" if not np.isfinite(b) else f"{b:.0f}", verdict, _trunc(r["note"], 40)])
    rows.append(["── 합계", f"{total_s/60:.1f}", "153", "", ""])
    LOG.table(rows, ["단계", "실측(분)", "예산(분)", "판정", "비고"],
              ["l", "r", "r", "c", "l"], title="런타임 감사 (§10)")
    if total_s > WALL_CLOCK_LIMIT_H * 3600:
        LOG.warn(f"총 wall-clock {total_s/3600:.1f}시간 — §12-6 킬 기준(4시간)을 넘었습니다. "
                 f"파라미터가 아니라 구조를 재점검하세요(수집 범위·캐시 적중률).")
    return pd.DataFrame(RUNTIME_ROWS)
