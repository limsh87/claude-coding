

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A2  프로젝트 루트 결정 (SPEC §2.1)                                                    ║
# ║                                                                                          ║
# ║  경로를 하드코딩하지 않는다. /content 도 하드코딩하지 않는다.                              ║
# ║  런타임 환경(Colab / 로컬 Linux / 로컬 Windows / 기타)을 감지해 루트를 결정한다.           ║
# ║                                                                                          ║
# ║  결정 순서:                                                                               ║
# ║   ① 환경변수 ARC_SACN_ROOT 가 있으면 그것 (CI·배치 실행용 탈출구)                          ║
# ║   ② Colab 이면 드라이브 마운트를 시도하고, 마운트된 실제 경로를 {DRIVE} 로 치환            ║
# ║   ③ 후보 목록 중 '이미 존재하는' 첫 경로                                                   ║
# ║   ④ 아무것도 없으면 후보 중 부모 디렉터리가 존재하는 첫 경로를 새로 만든다                  ║
# ║   ⑤ 그래도 안 되면 LOCAL_CACHE_ROOT (실행은 반드시 계속된다)                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _drive_mount_points() -> List[str]:
    """이 머신에서 '구글드라이브일 수 있는' 마운트 지점들. 하드코딩이 아니라 탐색이다."""
    out: List[str] = []

    # Colab: 마운트를 시도한다. 실패해도 예외를 밖으로 내보내지 않는다.
    if ENV.get("colab"):
        mp = "/content/drive"
        try:
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                from google.colab import drive as _gdrive      # type: ignore
                _gdrive.mount(mp, force_remount=False)
        except Exception as e:                                  # noqa
            _safe_print(f"[루트] 구글드라이브 마운트 실패({type(e).__name__}) — 로컬 경로로 진행합니다.")
        if os.path.isdir(os.path.join(mp, "MyDrive")):
            out.append(mp)

    # 로컬(윈도우/맥/리눅스)에서 드라이브 데스크톱이 동기화해 둔 경로들
    home = os.path.expanduser("~")
    cands = [
        os.environ.get("GOOGLE_DRIVE_ROOT", ""),
        os.path.join(home, "Google Drive"),
        os.path.join(home, "GoogleDrive"),
        os.path.join(home, "내 드라이브"),
        "/content/drive",
    ]
    # 윈도우: 드라이브 데스크톱이 잡는 가상 드라이브 문자 (G:\내 드라이브 등)
    if platform.system() == "Windows":
        for letter in "GHIJKDEF":
            for leaf in ("My Drive", "내 드라이브"):
                cands.append(f"{letter}:\\{leaf}")
    for c in cands:
        if c and os.path.isdir(c) and c not in out:
            out.append(c)
    return out


def _expand_candidate(tpl: str, drives: Sequence[str]) -> List[str]:
    """'{DRIVE}/MyDrive/x' 템플릿을 실제 마운트 지점 수만큼 펼친다."""
    tpl = os.path.expanduser(str(tpl or "").strip())
    if not tpl:
        return []
    if "{DRIVE}" not in tpl:
        return [tpl]
    out = []
    for d in drives:
        p = tpl.replace("{DRIVE}", d)
        # 드라이브 데스크톱 경로는 이미 'My Drive' 를 포함하므로 중복 MyDrive 를 접는다
        p = p.replace(os.path.join("My Drive", "MyDrive"), "My Drive")
        p = p.replace("/My Drive/MyDrive", "/My Drive")
        p = p.replace("내 드라이브/MyDrive", "내 드라이브")
        out.append(os.path.normpath(p))
    return out


def resolve_project_root() -> Tuple[str, str, List[str]]:
    """(루트경로, 상태문자열, 실제로 존재하는 adopt 디렉터리 목록).

    SPEC §2.1 이 요구하는 함수. 어떤 환경에서도 예외 없이 (경로, 사유) 를 돌려준다.
    """
    drives = _drive_mount_points()
    on_drive = bool(drives)

    # ① 환경변수 탈출구
    env_root = os.environ.get("ARC_SACN_ROOT", "").strip()
    if env_root:
        p = os.path.abspath(os.path.expanduser(env_root))
        os.makedirs(p, exist_ok=True)
        return p, "ENV:ARC_SACN_ROOT", _resolve_adopt_dirs(drives)

    expanded: List[str] = []
    for tpl in GDRIVE_ROOT_CANDIDATES:
        expanded.extend(_expand_candidate(tpl, drives or [""]))
    # {DRIVE} 를 못 채운 후보(드라이브 없음)는 빈 접두사가 되어 무의미하므로 걸러낸다
    expanded = [p for p in expanded if p and not p.startswith(("/MyDrive", "MyDrive"))]

    # ③ 이미 존재하는 첫 경로 — 기존 캐시를 그대로 물려받는 가장 중요한 분기
    for p in expanded:
        if os.path.isdir(p):
            mode = "DRIVE_EXISTING" if on_drive and _under_any(p, drives) else "LOCAL_EXISTING"
            return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)

    # ④ 부모가 존재하면 새로 만든다 (드라이브 위를 우선한다)
    for p in expanded:
        parent = os.path.dirname(os.path.normpath(p))
        if parent and os.path.isdir(parent):
            try:
                os.makedirs(p, exist_ok=True)
                mode = "DRIVE_CREATED" if on_drive and _under_any(p, drives) else "LOCAL_CREATED"
                return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)
            except Exception:
                continue

    # ⑤ 최후 폴백 — 여기서도 죽지 않는다
    p = os.path.abspath(os.path.expanduser(LOCAL_CACHE_ROOT))
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        p = os.path.abspath(tempfile.mkdtemp(prefix="arc_sacn_"))
    return p, "FALLBACK_LOCAL", _resolve_adopt_dirs(drives)


def _under_any(p: str, roots: Sequence[str]) -> bool:
    try:
        ap = os.path.abspath(p)
        return any(ap.startswith(os.path.abspath(r)) for r in roots if r)
    except Exception:
        return False


def _resolve_adopt_dirs(drives: Sequence[str]) -> List[str]:
    out: List[str] = []
    for tpl in GDRIVE_ADOPT_DIRS:
        for p in _expand_candidate(tpl, drives or [""]):
            if p and os.path.isdir(p) and p not in out:
                out.append(p)
    return out


# 재사용 코어(04_vault.py 의 _mount_drive)가 이 이름을 참조한다. 런타임에 확정된다.
GDRIVE_ROOT: str = ""
ADOPT_DIRS_RESOLVED: List[str] = []

# ── 판단 보류 항목 (SPEC §0 / §10 OPEN_QUESTIONS.md) ────────────────────────────────────────
#   "애매한 지점이 있으면 임의 판단하지 말고 여기 기록한 뒤 가장 보수적인 선택을 하라."
#   코드가 보수적 선택을 할 때마다 이 목록에 남기고, 마지막에 파일로 떨군다.
OPEN_QUESTIONS: List[dict] = []


def open_question(qid: str, topic: str, issue: str, choice: str, impact: str = ""):
    if any(q.get("id") == qid for q in OPEN_QUESTIONS):
        return
    OPEN_QUESTIONS.append({"id": qid, "topic": topic, "issue": issue,
                           "choice": choice, "impact": impact})


# ── 월말 주기 별칭 (pandas 버전 호환) ───────────────────────────────────────────────────────
#   pandas <2.2 는 "ME" 를 모르고, pandas 3.x 는 "M" 을 제거했다. 어느 쪽에서도 죽지 않도록
#   런타임에 한 번만 판별해 고정한다. Colab 과 로컬 JupyterLab 의 pandas 버전이 다른 것은
#   매우 흔하고, 이건 첫 줄에서 죽는 종류의 실패다.
def _resolve_month_end_alias() -> str:
    import pandas as _pd
    for alias in ("ME", "M"):
        try:
            _pd.date_range("2020-01-31", periods=2, freq=alias)
            return alias
        except Exception:
            continue
    return "ME"


MONTH_END_ALIAS = _resolve_month_end_alias()


def sacn_month_range(start, end) -> "pd.DatetimeIndex":
    """월말 인덱스. pandas 버전에 무관하게 동작한다."""
    return pd.date_range(month_end(start), month_end(end), freq=MONTH_END_ALIAS)
