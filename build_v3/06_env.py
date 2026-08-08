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
    # ★ '못 찾았다'만 말하면 사용자는 무엇을 고쳐야 할지 모른다. 실제로 뒤진 경로를 보여준다.
    tried = _gdrive_desktop_candidates()
    LOG.warn(f"구글드라이브 경로를 찾지 못해 로컬({local})에 저장합니다.\n"
             f"     뒤져본 경로 {len(tried)}개 중 앞부분: {tried[:6]}\n"
             f"     드라이브에 남기려면 상단 GDRIVE_ROOT 를 실제 경로로 바꾸세요. 확인 방법:\n"
             f"       · Windows 탐색기에서 구글 드라이브를 열고 주소창 경로를 복사\n"
             f"         예)  GDRIVE_ROOT = r\"G:/내 드라이브/tcd_cache\"\n"
             f"       · macOS  ~/Library/CloudStorage/GoogleDrive-<계정>/My Drive/tcd_cache\n"
             f"     ※ 로컬에 저장해도 백테스트는 정상 동작합니다. 다음 실행에서 드라이브 경로를 "
             f"지정하면 이 폴더를 GDRIVE_ADOPT_DIRS 에 넣어 그대로 흡수할 수 있습니다 "
             f"(파일 이동·삭제 없음).")
    return local, "LOCAL"


def _win_drivefs_roots() -> List[str]:
    """구글드라이브(데스크톱)가 **스스로 기록해 둔** 마운트 지점을 읽는다.

    ① 레지스트리 DefaultMountPoint — 정책(HKLM\\Policies) > 시스템 > 사용자 순.
       드라이브 문자일 수도, '%USERPROFILE%\\GFS' 같은 확장 경로일 수도 있다.
    ② %LOCALAPPDATA%\\Google\\DriveFS\\root_preference_sqlite.db
       media.last_mount_point = 실제로 마운트했던 지점,
       roots.last_seen_absolute_path = 미러링 폴더(문자 스캔으로는 절대 못 찾는 경로).
    부팅 경로에서 도는 함수이므로 어떤 예외도 밖으로 내보내지 않는다.
    """
    out: List[str] = []
    if platform.system() != "Windows":
        return out
    try:
        import winreg                                            # type: ignore
        for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"Software\Policies\Google\DriveFS"),
                          (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\DriveFS"),
                          (winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS")):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | view) as k:
                        v, _ = winreg.QueryValueEx(k, "DefaultMountPoint")
                        p = os.path.expandvars(str(v)).strip()
                        if p:
                            out.append(p + ":\\" if len(p.rstrip(":")) == 1 else p)
                except OSError:
                    continue
    except Exception:
        pass
    try:
        import sqlite3
        db = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS",
                          "root_preference_sqlite.db")
        if os.path.isfile(db):
            # 드라이브가 파일을 열어 두고 있으므로 반드시 읽기 전용·불변으로 연다.
            con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True, timeout=2)
            try:
                for q, colname in (("SELECT last_mount_point FROM media", 0),
                                   ("SELECT last_seen_absolute_path FROM roots", 0)):
                    try:
                        for row in con.execute(q):
                            p = str(row[colname] or "").strip()
                            if p:
                                out.append(p + ":\\" if len(p.rstrip(":")) == 1 else p)
                    except Exception:
                        continue
            finally:
                con.close()
    except Exception:
        pass
    # 루트 아래의 '내 드라이브' 계열 하위폴더도 후보에 넣는다(폴더 마운트 대응).
    kids = ("My Drive", "내 드라이브", "Shared drives", "공유 드라이브")
    return out + [os.path.join(r, k) for r in list(out) for k in kids]


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
        # ★ 드라이브 문자를 훑는 것만으로는 못 찾는다. 구글 드라이브는 (a) 드라이브 문자
        #   (b) **임의의 빈 폴더** (c) 미러링 모드의 로컬 폴더 중 하나로 붙을 수 있고,
        #   (b)(c)는 어떤 문자 스캔으로도 발견되지 않는다. 실제로 사용자 환경에서 못 찾았다.
        #   → 드라이브 자신이 기록해 둔 설정을 먼저 읽는다. 추측보다 조회가 정확하다.
        roots += _win_drivefs_roots()
        letters = "DEFGHIJKLMNOPQRSTUVWXYZ"     # 기본은 G: 지만 사용자가 바꿀 수 있다
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()      # type: ignore[attr-defined]
            live = "".join(L for L in letters if mask >> (ord(L) - ord("A")) & 1)
            letters = live or letters          # 비트마스크는 '힌트'다. 실패해도 스캔은 한다.
        except Exception:
            pass
        for L in letters:
            roots += [f"{L}:/내 드라이브", f"{L}:/My Drive", f"{L}:/공유 드라이브"]
        roots += [os.path.join(home, n) for n in
                  ("My Drive", "내 드라이브", "Google Drive", "GoogleDrive")]
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
WALL_CLOCK_LIMIT_H = 4.0        # §12-6 — 이 안에 끝나야 한다

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★★ 4시간 계약을 '경고'가 아니라 '강제'로 바꾸는 장치 ★★
#
#  예전 구조에서 이 상수는 **끝난 뒤에** 한 번 비교되는 데 쓰였다. PIPE.stage 의 budget_s 도
#  마찬가지로 컨텍스트가 닫힐 때 초과를 경고할 뿐, 진행 중인 수집을 멈추지 못한다.
#  즉 4시간 계약을 지키는 코드가 어디에도 없었다 — 계약서만 있고 집행자가 없었다.
#
#  → 실행 시작 시각에서 **역산한 데드라인**을 하나 만들고, 잡이 곱셈으로 늘어나는 수집
#    루프(직원현황·Tier-2 재무·가격·리서치)가 회사/청크 경계마다 이걸 확인해 스스로 멈춘다.
#    경계에서 멈추므로 받은 것은 전부 온전하고, 캐시는 append-only 라 다음 실행이 이어받는다.
#
#  ★ 왜 '건수'가 아니라 '시간'인가. 사용자 요구가 그것이다 —
#    "키호출량을 처음부터 19000이나 2만회로 정하지 말고 남은 호출량을 실시간으로 체크해서
#     그만큼 쓰게 하라." 건수 상한은 우리의 추정이고, 진짜 잔여량은 서버만 안다.
#    그러니 멈추는 조건은 두 개뿐이어야 한다:
#      ① 서버가 020/021 로 거부했다(진짜 한도 소진)   ② 시계가 다 됐다(4시간 계약)
#    그 사이에서는 남은 만큼 계속 쏜다.
# ══════════════════════════════════════════════════════════════════════════════════════════
POST_COLLECT_RESERVE_MIN = 60.0     # 수집 이후(피처·스코어·백테스트·강건성·리포트) 몫


def run_elapsed_s() -> float:
    return time.time() - _T0_PROCESS


def collect_deadline_ts() -> float:
    """수집 단계가 넘으면 안 되는 절대 시각(epoch)."""
    return _T0_PROCESS + WALL_CLOCK_LIMIT_H * 3600.0 - POST_COLLECT_RESERVE_MIN * 60.0


def collect_time_left() -> float:
    """수집에 남은 초. 음수면 이미 넘긴 것이다."""
    return collect_deadline_ts() - time.time()


def deadline_hit(margin_s: float = 0.0) -> bool:
    return collect_time_left() <= margin_s


def deadline_note() -> str:
    left = collect_time_left()
    if left <= 0:
        return (f"4시간 계약의 수집 몫을 모두 썼습니다"
                f"(경과 {run_elapsed_s()/60:.0f}분 · 후속 단계 몫 "
                f"{POST_COLLECT_RESERVE_MIN:.0f}분 확보).")
    return f"수집 잔여 {left/60:.0f}분"


def stage_time_budget(share: float, floor_s: float = 60.0) -> float:
    """남은 수집시간 중 이 단계가 쓸 몫(초). share 는 0~1.

    ★ 고정 상수(예전 FS_TIME_BUDGET_S=1200)를 쓰지 않는 이유: 앞 단계가 빨리 끝나면
      그만큼을 뒤 단계가 써야 하고, 앞 단계가 늦어지면 뒤 단계가 줄어야 한다.
      고정 상수는 둘 다 못 한다 — 합이 4시간을 넘거나, 남는 시간을 버린다.
    """
    return max(floor_s, collect_time_left() * float(share))


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
