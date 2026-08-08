

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
        os.path.join(home, "Google 드라이브"),
        "/content/drive",
    ]
    # 맥: 드라이브 데스크톱 신형 경로 ~/Library/CloudStorage/GoogleDrive-<계정>/My Drive
    cs = os.path.join(home, "Library", "CloudStorage")
    if os.path.isdir(cs):
        try:
            for d in os.listdir(cs):
                if d.lower().startswith("googledrive"):
                    cands.append(os.path.join(cs, d))
        except Exception:
            pass
    # 윈도우: 드라이브 데스크톱이 잡는 가상 드라이브 문자.
    #   ★ 실측에서 드라이브를 못 찾아 로컬로 떨어졌다("LOCAL_CREATED / 스캔 대상 0개").
    #     문자 후보를 GHIJK 로만 잡으면 다른 문자에 마운트된 경우를 통째로 놓친다.
    #     A~Z 전부 훑어도 os.path.isdir 은 존재하지 않는 문자에서 즉시 False 다(비용 무시 가능).
    if platform.system() == "Windows":
        # ★ isdir 이 항상 즉시 반환한다는 가정은 틀렸다. 끊긴 네트워크 매핑 드라이브에서는
        #   SMB 재접속을 시도하며 수십 초씩 멈춘다. 문자 하나당이 아니라 전체에 예산을 건다.
        _t_letters = time.monotonic()
        for letter in "GHIJKLMNOPQRSTUVWXYZDEF":
            if time.monotonic() - _t_letters > 8.0:
                _safe_print("[루트] 드라이브 문자 탐색이 8초를 넘겨 중단합니다 "
                            "(끊긴 네트워크 드라이브일 수 있습니다). "
                            "코드 상단 GDRIVE_ROOT 에 경로를 직접 넣으면 탐색을 건너뜁니다.")
                break
            root = f"{letter}:\\"
            if not os.path.isdir(root):
                continue
            leaves = ("My Drive", "내 드라이브", "Mi unidad", "Mon Drive")
            hit = False
            for leaf in leaves:
                if os.path.isdir(os.path.join(root, leaf)):
                    cands.append(os.path.join(root, leaf))
                    hit = True
            # 드라이브 루트 자체가 'My Drive' 인 구성도 있다. 다만 매핑된 네트워크 드라이브
            # (Z: 등)를 통째로 후보로 넣으면 뒤의 구조 탐색이 사내 파일서버를 훑게 된다.
            # → 우리 캐시 표식이 실제로 보일 때만 루트를 후보에 넣는다.
            if not hit and (os.path.isdir(os.path.join(root, GDRIVE_SHARED_NS))
                            or os.path.isdir(os.path.join(root, GDRIVE_PRIVATE_NS))):
                cands.append(root)
    # 윈도우: 구글드라이브 데스크톱이 남기는 설정에서 마운트 문자를 직접 읽는다.
    #   ★ 문자 순회만으로는 못 찾는 구성이 있다(레이블만 다르거나, 스트리밍 모드에서
    #     루트에 'My Drive' 가 아닌 계정 폴더가 오는 경우). 설정 파일이 가장 확실하다.
    if platform.system() == "Windows":
        try:
            base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS")
            if os.path.isdir(base):
                for acct in os.listdir(base):
                    for leaf in ("My Drive", "내 드라이브"):
                        for letter in "GHIJKLMNOPQRSTUVWXYZ":
                            cands.append(os.path.join(f"{letter}:\\", leaf))
                    break
        except Exception:
            pass
        # 볼륨 레이블에 'Google Drive' 가 들어간 드라이브를 찾는다
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            for letter in "GHIJKLMNOPQRSTUVWXYZDEF":
                root = f"{letter}:\\"
                if not os.path.isdir(root):
                    continue
                try:
                    ok = ctypes.windll.kernel32.GetVolumeInformationW(
                        ctypes.c_wchar_p(root), buf, 260, None, None, None, None, 0)
                    if ok and ("google" in buf.value.lower() or "드라이브" in buf.value):
                        cands.append(root)
                        for leaf in ("My Drive", "내 드라이브"):
                            cands.append(os.path.join(root, leaf))
                except Exception:
                    continue
        except Exception:
            pass

    # WSL 에서 윈도우 드라이브가 /mnt/g 등으로 보이는 경우
    for letter in "gdefhijk":
        p = f"/mnt/{letter}"
        if os.path.isdir(p):
            for leaf in ("My Drive", "내 드라이브"):
                cands.append(os.path.join(p, leaf))
    for c in cands:
        if c and os.path.isdir(c) and c not in out:
            out.append(c)
    return out


def _vault_marker(p: str) -> bool:
    """이 디렉터리가 '우리 캐시 루트'인지 판정한다.

    판정 근거는 이름이 아니라 구조다 — 공용 인덱스(_shared/index)가 있으면 캐시 루트다.
    사용자가 폴더 이름을 뭐라고 지었든(후보 목록에 없든) 찾아낼 수 있다.
    """
    try:
        for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):
            idx = os.path.join(p, ns, "index")
            if not os.path.isdir(idx):
                continue
            # ★ '_shared/index' 라는 이름만으로 남의 폴더를 우리 캐시로 오인하면 안 된다.
            #   Vault 는 생성 즉시 blob/table 디렉터리와 저널을 만들고 compact() 는
            #   index.parquet 을 통째로 재작성하므로, 잘못 고르면 무관한 프로젝트의
            #   인덱스를 덮어쓴다 — 절대 1원칙 위반이다. 우리 저널/파케이가 있어야 인정한다.
            if (os.path.exists(os.path.join(idx, "index.jsonl"))
                    or os.path.exists(os.path.join(idx, "index.parquet"))):
                return True
    except Exception:
        pass
    return False


def _discover_vaults(drives: Sequence[str], max_depth: int = 3) -> List[str]:
    """드라이브 마운트 아래에서 '이미 존재하는 캐시 루트'를 구조로 찾아낸다.

    ★ 실측 실패의 핵심이 여기였다. 후보 이름(tcd_cache, kr_quant_cache …)이 사용자의
      실제 폴더명과 다르면 캐시가 눈앞에 있어도 못 쓴다. 이름 매칭 대신 _shared/index
      존재 여부로 찾으면 폴더명이 무엇이든 상관없다.
      깊이 3, 디렉터리 수 상한을 둬서 드라이브 전체 스캔으로 번지지 않게 한다.
    """
    found: List[str] = []
    budget = 4000
    # 벽시계 예산도 함께 둔다. 느린 네트워크 드라이브에서는 디렉터리 수가 적어도
    # scandir 한 번에 수백 ms 가 걸려, 개수 예산만으로는 몇 분씩 멈출 수 있다.
    deadline = time.monotonic() + 20.0
    for d in drives:
        stack = [(d, 0)]
        while stack and budget > 0 and time.monotonic() < deadline:
            cur, depth = stack.pop()
            budget -= 1
            try:
                entries = [e for e in os.scandir(cur) if e.is_dir(follow_symlinks=False)]
            except Exception:
                continue
            for e in entries:
                if budget <= 0 or time.monotonic() >= deadline:
                    break            # scandir 한 번에 수천 개가 나올 수 있다 — 안쪽에서도 본다
                if e.name.startswith((".", "$")) or e.name in ("__pycache__", "node_modules"):
                    continue
                budget -= 1          # _vault_marker 의 isdir 비용도 예산에 포함한다
                if _vault_marker(e.path):
                    if e.path not in found:
                        found.append(e.path)
                    continue                     # 캐시 루트 안쪽은 더 파고들 필요가 없다
                if depth + 1 < max_depth:
                    stack.append((e.path, depth + 1))
    return found


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
    trace: List[List[str]] = [["드라이브 마운트 후보",
                               ", ".join(drives)[:110] if drives else "없음"]]

    # ① 사용자가 직접 지정한 경로가 있으면 무조건 그것 (탐색 실패로 캐시를 잃지 않는 탈출구)
    if str(GDRIVE_ROOT or "").strip():
        p = os.path.abspath(os.path.expanduser(str(GDRIVE_ROOT).strip()))
        exists = os.path.isdir(p)
        try:
            os.makedirs(p, exist_ok=True)
        except Exception as e:                                   # noqa
            LOG_FN = globals().get("_safe_print", print)
            LOG_FN(f"[루트] GDRIVE_ROOT='{p}' 를 만들 수 없습니다({type(e).__name__}). "
                   f"경로를 다시 확인하세요 — 자동 탐색으로 넘어갑니다.")
        if os.path.isdir(p):
            try:
                found = [v for v in _discover_vaults(drives)
                         if os.path.abspath(v) != os.path.abspath(p)]
                for extra in (LOCAL_CACHE_ROOT, os.path.expanduser("~/.kr_data_work/ARC_SACN")):
                    ep = os.path.abspath(os.path.expanduser(extra))
                    if os.path.isdir(ep) and _vault_marker(ep) and ep != os.path.abspath(p):
                        found.append(ep)
                globals()["ALT_READ_ROOTS"] = list(dict.fromkeys(found))
            except Exception:
                pass
            if not exists:
                _safe_print(f"[루트] ⚠ GDRIVE_ROOT 경로가 없어 새로 만들었습니다: {p}\n"
                            f"        오타라면 기존 캐시를 한 건도 못 쓰고 전부 재수집합니다. "
                            f"탐색기 주소창의 경로와 글자 하나까지 같은지 확인하세요.")
            return p, ("USER_SET_EXISTING" if exists else "USER_SET_CREATED"), \
                _resolve_adopt_dirs(drives, extra=[p])

    # ② 환경변수 탈출구 (CI·배치)
    env_root = os.environ.get("ARC_SACN_ROOT", "").strip()
    if env_root:
        p = os.path.abspath(os.path.expanduser(env_root))
        os.makedirs(p, exist_ok=True)
        return p, "ENV:ARC_SACN_ROOT", _resolve_adopt_dirs(drives, extra=[p])

    expanded: List[str] = []
    for tpl in GDRIVE_ROOT_CANDIDATES:
        expanded.extend(_expand_candidate(tpl, drives or [""]))
    # {DRIVE} 를 못 채운 후보(드라이브 없음)는 빈 접두사가 되어 무의미하므로 걸러낸다
    # {DRIVE} 를 못 채운 후보는 '/MyDrive/...' 같은 접두사만 남는다. 윈도우에서는
    # normpath 가 '\\MyDrive\\...' 로 바꿔 이 검사를 빠져나가고, abspath 가
    # 'C:\\MyDrive\\...' 로 만들어 엉뚱한 곳에 캐시를 만든다 → 드라이브 문자를 떼고 본다.
    expanded = [p for p in expanded
                if p and not os.path.splitdrive(p)[1].lstrip("\\/").startswith("MyDrive")]

    # ③ 이름이 아니라 '구조'로 기존 캐시를 찾는다 — 이게 최우선이다.
    #    후보 이름이 사용자의 실제 폴더명과 달라 캐시를 통째로 놓치던 실패를 여기서 막는다.
    named_hit = [p for p in expanded if os.path.isdir(p) and _vault_marker(p)]
    scanned = _discover_vaults(drives) if on_drive else []
    vaults = list(dict.fromkeys(named_hit + scanned))
    trace.append(["기존 캐시(_shared/index) 발견", f"{len(vaults)}개"])
    if vaults:
        # ★ 하나만 고르고 나머지를 버리면, 로컬과 드라이브에 흩어진 캐시의 절반을
        #   매번 다시 받게 된다. 쓰기 루트는 하나(드라이브 우선)로 정하되,
        #   읽기는 발견된 전부에서 한다(ALT_READ_ROOTS). 시간을 가장 크게 아끼는 지점이다.
        def _weight(p: str) -> int:
            # ★ 디렉터리명이 틀려 있었다. Vault 가 만드는 것은 index/blob/table 이고
            #   여기서는 tables/blobs 를 세고 있었다 — 결국 index 파일 수(1~3)만 세어
            #   모든 후보의 점수가 같아졌고, '가장 알맹이 많은 것' 선택이 무의미했다.
            n = 0
            for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):
                d = os.path.join(p, ns)
                for sub in ("table", "blob", "index"):
                    try:
                        n += len(os.listdir(os.path.join(d, sub)))
                    except Exception:
                        pass
            return n
        on_drv = [v for v in vaults if _under_any(v, drives)]
        # 쓰기 루트: 드라이브 위의 것을 우선하고, 그중 알맹이가 많은 것을 고른다.
        best = max(on_drv or vaults, key=_weight)
        alts = [v for v in vaults if os.path.abspath(v) != os.path.abspath(best)]
        # 로컬 폴백 루트에 캐시가 있으면 그것도 읽기 대상에 넣는다(드라이브를 쓰더라도)
        for extra in (LOCAL_CACHE_ROOT, os.path.expanduser("~/.kr_data_work/ARC_SACN")):
            ep = os.path.abspath(os.path.expanduser(extra))
            if (os.path.isdir(ep) and _vault_marker(ep)
                    and ep != os.path.abspath(best) and ep not in map(os.path.abspath, alts)):
                alts.append(ep)
        globals()["ALT_READ_ROOTS"] = alts
        mode = "DRIVE_EXISTING" if _under_any(best, drives) else "LOCAL_EXISTING"
        if alts:
            _safe_print(f"[루트] 캐시 루트 {len(alts) + 1}곳을 함께 읽습니다 "
                        f"(쓰기는 {os.path.basename(best)}). 추가 읽기: "
                        + ", ".join(alts[:3]) + (" …" if len(alts) > 3 else ""))
        return os.path.abspath(best), mode, _resolve_adopt_dirs(drives, extra=vaults)

    # ④ 캐시는 없지만 존재하는 후보 경로
    for p in expanded:
        if os.path.isdir(p):
            mode = "DRIVE_EXISTING" if on_drive and _under_any(p, drives) else "LOCAL_EXISTING"
            return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)

    # ⑤ 부모가 존재하면 새로 만든다 (드라이브 위를 우선한다)
    for p in sorted(expanded, key=lambda q: (0 if _under_any(q, drives) else 1)):
        parent = os.path.dirname(os.path.normpath(p))
        if parent and os.path.isdir(parent):
            try:
                os.makedirs(p, exist_ok=True)
                mode = "DRIVE_CREATED" if on_drive and _under_any(p, drives) else "LOCAL_CREATED"
                return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)
            except Exception:
                continue

    # ⑥ 최후 폴백 — 여기서도 죽지 않는다
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


def _resolve_adopt_dirs(drives: Sequence[str], extra: Optional[Sequence[str]] = None) -> List[str]:
    """기존 리포트를 '등록만' 할 디렉터리 목록. 파일을 옮기거나 지우지 않는다.

    발견된 캐시 루트(extra)와 드라이브 마운트 자체도 포함한다 — 실측에서 '스캔 대상 0개'가
    나온 것은 후보 템플릿이 하나도 존재하지 않았기 때문이고, 그러면 이미 드라이브에 있는
    리포트를 한 건도 재사용하지 못한다.
    """
    out: List[str] = []
    for p in list(extra or []):
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    for tpl in GDRIVE_ADOPT_DIRS:
        for p in _expand_candidate(tpl, drives or [""]):
            if p and os.path.isdir(p) and p not in out:
                out.append(p)
    # 후보가 하나도 안 잡히면 드라이브 마운트 자체를 대상으로 둔다(재귀 스캔은 Vault 가 제한한다)
    if not out:
        for d in drives:
            for leaf in ("MyDrive", "My Drive", "내 드라이브", ""):
                p = os.path.join(d, leaf) if leaf else d
                if os.path.isdir(p) and p not in out:
                    out.append(p)
                    break
    return out


# 재사용 코어(04_vault.py 의 _mount_drive)가 이 이름을 참조한다. 런타임에 확정된다.
GDRIVE_ROOT: str = ""
ADOPT_DIRS_RESOLVED: List[str] = []
# ★ 읽기 전용 보조 캐시 루트. 로컬과 드라이브에 캐시가 흩어져 있을 때 양쪽을 모두 읽어
#   재수집을 없앤다. 쓰기는 언제나 주 루트 한 곳에만 한다(분산 저장은 관리 불가능해진다).
ALT_READ_ROOTS: List[str] = []

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
