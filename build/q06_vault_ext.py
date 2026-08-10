

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  다중루트 캐시 (구글드라이브 + 로컬 미러) · DART 동적 호출한도                        ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙의 구조적 보장 ★★★                                                        ║
# ║   · 읽기는 여러 루트에서, 쓰기는 오직 '드라이브 쓰기루트' 하나에서만 일어난다.              ║
# ║     로컬 미러가 읽기 전용인 것은 규율이 아니라 구조다 — 쓰기 함수(put_table/put_blob/      ║
# ║     flush/compact)는 self.root 만 사용하고, 미러 경로는 애초에 그 함수들에 도달하지 않는다.║
# ║   · 미러에서 찾은 항목은 인덱스에 '_root' 를 달고 들어오며, 실제 파일 해석도 그 루트를      ║
# ║     기준으로 한다. (미러 상대경로를 쓰기루트에 이어붙이는 순간 조용히 엉뚱한 파일을 연다)  ║
# ║   · 미러에만 있는 '테이블'은 드라이브로 승격 복사한다(원본은 그대로 둔다). 드라이브에       ║
# ║     이미 있으면 승격 자체가 일어나지 않으므로 최신본을 과거본으로 덮을 수 없다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def ro_read_parquet(path: str) -> Tuple[Optional[pd.DataFrame], str]:
    """읽기 전용 parquet 리더. (프레임, 상태). ★ 어떤 경우에도 파일을 건드리지 않는다.

    ★★ 왜 read_parquet_safe 를 쓰면 안 되는가 (적대적 감사가 실증한 치명 결함) ★★
      공용 코어의 read_parquet_safe 는 읽기에 실패하면 손상 추정 파일을 `.corrupt.<ts>` 로
      **개명**한다. 자기 캐시에는 타당한 처리지만, 미러(사용자의 로컬 D: 또는 다른 전략의
      드라이브 캐시)에 대고 실행하면 남의 파일을 파괴하는 것이다.
      게다가 실패 원인 1·2위가 이상 상황도 아니다:
        · Drive for Desktop / rclone 의 placeholder(구체화 전 0바이트)
        · 동기화가 진행 중인 부분 파일
      둘 다 ArrowInvalid 를 던진다. 즉 '정상 동작 중인 드라이브'가 곧 파괴 조건이다.
      → 미러는 반드시 이 함수로만 읽는다. 실패는 그냥 결측으로 돌린다.
    """
    try:
        st1 = os.stat(path)
        if st1.st_size == 0:
            return None, "empty(동기화 미완료 추정)"
        time.sleep(0.05)
        st2 = os.stat(path)
        if (st2.st_size, st2.st_mtime_ns) != (st1.st_size, st1.st_mtime_ns):
            return None, "syncing(동기화 진행 중)"
        with open(path, "rb") as f:
            blob = f.read()
        return pd.read_parquet(io.BytesIO(blob)), "ok"
    except Exception as e:                                      # noqa
        return None, type(e).__name__


def _expand(p: str) -> str:
    try:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(str(p))))
    except Exception:
        return str(p)


def _same_place_key(p: str):
    """경로의 '실체' 식별자. 문자열 비교로는 같은 폴더를 두 번 걷는 것을 못 막는다.

    ★ Colab 은 /content/drive/MyDrive 와 /content/drive/My Drive 를 '둘 다' 만든다.
      realpath 가 서로 다르게 나오므로 문자열 dedup 이 실패하고, 같은 트리를 두 번 스캔한다.
      드라이브 FUSE 에서 그건 그대로 2배의 시간이다. (st_dev, st_ino) 가 있으면 그걸 쓰고,
      없으면 'My Drive' → 'MyDrive' 정규화한 realpath 로 떨어진다.
    """
    try:
        st = os.stat(p)
        if st.st_ino:
            return ("ino", st.st_dev, st.st_ino)
    except Exception:
        pass
    rp = os.path.realpath(p).replace("/My Drive/", "/MyDrive/").replace("\\My Drive\\", "\\MyDrive\\")
    return ("path", os.path.normcase(rp))


def _drive_mount_points() -> List[Tuple[str, str]]:
    """(마운트경로, 라벨) 후보. Colab / Windows / macOS / Linux 전부를 커버한다.
    존재하지 않는 경로는 호출자가 걸러낸다."""
    home = os.path.expanduser("~")
    cands: List[Tuple[str, str]] = []

    if ENV["colab"]:
        cands.append(("/content/drive/MyDrive", "COLAB"))
        cands.append(("/content/drive/My Drive", "COLAB"))

    # Windows — Drive for Desktop 은 드라이브 문자로 붙는다. 한글 로케일은 '내 드라이브'.
    for dl in ("G:", "H:", "I:", "J:"):
        for leaf in ("My Drive", "내 드라이브"):
            cands.append((f"{dl}/{leaf}", "WIN_DRIVE_FS"))
    cands.append((os.path.join(home, "Google Drive", "My Drive"), "WIN_LEGACY"))

    # macOS — CloudStorage 는 계정별 폴더명이라 glob 로 찾는다.
    cands.append((os.path.join(home, "Google Drive", "My Drive"), "MAC"))
    try:
        import glob as _glob
        for p in _glob.glob(os.path.join(home, "Library", "CloudStorage", "GoogleDrive-*", "My Drive")):
            cands.append((p, "MAC_CLOUDSTORAGE"))
    except Exception:
        pass

    # Linux — rclone / insync / gdrive 관행 경로
    for leaf in ("GoogleDrive", "google-drive", "gdrive", "Google Drive"):
        cands.append((os.path.join(home, leaf), "LINUX_SYNC"))

    seen, out = set(), []
    for p, lab in cands:
        e = _expand(p)
        if e not in seen:
            seen.add(e)
            out.append((e, lab))
    return out


def _looks_like_cache_root(p: str) -> int:
    """캐시 루트다움 점수. 이미 공용 인덱스가 들어 있는 폴더를 최우선으로 고른다.
    (다른 전략이 쓰던 캐시를 그대로 이어받는 것이 사용자 요구사항이다)"""
    if not p or not os.path.isdir(p):
        return -1
    score = 0
    for sub, w in ((os.path.join(GDRIVE_SHARED_NS, "index", "index.jsonl"), 100),
                   (os.path.join(GDRIVE_SHARED_NS, "index", "index.parquet"), 60),
                   (os.path.join(GDRIVE_SHARED_NS, "table"), 30),
                   (os.path.join(GDRIVE_SHARED_NS, "blob"), 20),
                   (GDRIVE_PRIVATE_NS, 10)):
        if os.path.exists(os.path.join(p, sub)):
            score += w
    return score


def qvf_resolve_roots() -> Tuple[str, str, List[str]]:
    """(쓰기루트, 모드, 읽기전용 미러들).

    쓰기루트 선택 규칙:
      ① 사용자가 GDRIVE_ROOT 를 직접 지정했으면 그대로 (없으면 생성)
      ② 드라이브 마운트가 있으면 그 아래 GDRIVE_ROOT_NAMES 후보 중 '캐시다움 점수'가
         가장 높은 곳. 전부 비어 있으면 첫 이름으로 새로 만든다.
      ③ 드라이브가 없으면 LOCAL_CACHE_ROOT (그때만 로컬이 쓰기 대상이 된다)
    """
    # Colab 이면 먼저 마운트를 시도한다. 실패해도 죽지 않는다.
    if ENV["colab"] and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            _gdrive.mount("/content/drive", force_remount=False)
        except Exception as e:                                  # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 진행합니다. "
                     f"Colab 이라면 셀 실행 시 뜨는 인증 팝업을 승인하세요.")

    mounts = [(p, lab) for p, lab in _drive_mount_points() if os.path.isdir(p)]

    write_root, mode = "", "LOCAL"
    if str(GDRIVE_ROOT or "").strip():
        write_root, mode = _expand(GDRIVE_ROOT), "EXPLICIT"
    else:
        best, best_s, best_lab = "", -1, ""
        for mp, lab in mounts:
            for nm in GDRIVE_ROOT_NAMES:
                cand = os.path.join(mp, nm)
                s = _looks_like_cache_root(cand)
                if s > best_s:
                    best, best_s, best_lab = cand, s, lab
        if best and best_s > 0:
            write_root, mode = best, f"DRIVE:{best_lab}(기존캐시 이어받기)"
        elif mounts:
            write_root, mode = os.path.join(mounts[0][0], GDRIVE_ROOT_NAMES[0]), \
                f"DRIVE:{mounts[0][1]}(신규)"
        else:
            write_root, mode = _expand(LOCAL_CACHE_ROOT), "LOCAL(드라이브 미발견)"

    try:
        os.makedirs(write_root, exist_ok=True)
    except Exception as e:                                      # noqa
        LOG.warn(f"쓰기루트 생성 실패({type(e).__name__}) — 로컬로 폴백합니다: {write_root}")
        write_root, mode = _expand(LOCAL_CACHE_ROOT), "LOCAL(쓰기루트 생성 실패)"
        os.makedirs(write_root, exist_ok=True)

    # 읽기 전용 미러: 사용자가 지정한 로컬 경로 + 드라이브의 다른 캐시 폴더들
    mirrors: List[str] = []
    for m in list(CACHE_MIRROR_ROOTS):
        e = _expand(m)
        if os.path.isdir(e) and os.path.realpath(e) != os.path.realpath(write_root):
            mirrors.append(e)
    for mp, _lab in mounts:
        for nm in GDRIVE_ROOT_NAMES:
            cand = os.path.join(mp, nm)
            if os.path.isdir(cand) and os.path.realpath(cand) != os.path.realpath(write_root):
                mirrors.append(_expand(cand))
    # 로컬 폴백 루트도 (쓰기루트가 아니라면) 읽기 대상에 넣는다
    lf = _expand(LOCAL_CACHE_ROOT)
    if os.path.isdir(lf) and os.path.realpath(lf) != os.path.realpath(write_root):
        mirrors.append(lf)

    seen, uniq = {_same_place_key(write_root)}, []
    for m in mirrors:
        k = _same_place_key(m)
        if k not in seen:
            seen.add(k)
            uniq.append(m)
    return write_root, mode, uniq


class QVFVault(Vault):
    """Vault + 다중루트 읽기. 쓰기 경로는 부모 그대로(=self.root 전용)라 미러는 절대 안 건드린다."""

    def __init__(self, root: str, mode: str, mirrors: Optional[Sequence[str]] = None,
                 promote_tables: bool = True):
        super().__init__(root, mode)
        # ★ 미러 중복제거는 생성자에서도 한 번 더 한다. qvf_resolve_roots 만 믿으면, 다른 경로로
        #   생성자를 부르는 순간(테스트·재구성) 같은 트리를 두 번 읽고 인덱스가 두 배가 된다.
        #   Colab 의 MyDrive / "My Drive" 처럼 문자열은 다른데 실체가 같은 경우가 실제로 있다.
        _seen = {_same_place_key(self.root)}
        _keep: List[str] = []
        _dupes: List[str] = []
        for m in (mirrors or []):
            if not m or not os.path.isdir(m):
                continue
            k = _same_place_key(m)
            if k in _seen:
                _dupes.append(m)
                continue
            _seen.add(k)
            _keep.append(m)
        if _dupes:
            LOG.info(f"쓰기루트와 같은 실체를 가리키는 미러 {len(_dupes)}개를 제외했습니다 "
                     f"(같은 트리를 두 번 읽지 않습니다): {_trunc(', '.join(_dupes[:3]), 60)}")
        self.mirrors: List[str] = _keep
        self.promote_tables = bool(promote_tables)
        self._mirror_idx: Dict[str, pd.DataFrame] = {}
        self.table_src: Dict[str, str] = {}          # 어느 루트가 이 테이블을 줬는가(감사용)
        self._own_only = False                       # compact 중 미러 행을 배제하기 위한 스위치
        self._merged: Dict[str, pd.DataFrame] = {}   # 미러 병합 결과 캐시(더티 시 무효화)
        self._uidpath: Dict[str, Dict[str, Tuple[str, str, str]]] = {}   # uid → 경로

    # ── 쓰기 경로 구조적 봉인 ----------------------------------------------------------
    def _wpath(self, path: str) -> str:
        """쓰기 대상 경로 검증. 쓰기루트 밖이면 예외. 상속받은 어떤 코드도 미러를 못 쓴다.
        ★ 주석으로 '도달하지 않는다'고 쓰는 것과, 도달하면 터지게 만드는 것은 다르다."""
        rp = os.path.realpath(path)
        root = os.path.realpath(self.root)
        if not (rp == root or rp.startswith(root + os.sep)):
            raise PermissionError(
                f"[절대 1원칙 위반 차단] 쓰기루트 밖 경로에 쓰려 했습니다: {path}\n"
                f"  쓰기루트: {self.root}\n"
                f"  미러는 읽기 전용입니다. 이 예외는 버그를 조용히 넘기지 않기 위한 것입니다.")
        return path

    def journal(self, scope: str) -> str:
        return self._wpath(super().journal(scope))

    def idx_parquet(self, scope: str) -> str:
        return self._wpath(super().idx_parquet(scope))

    def blob_dir(self, scope: str) -> str:
        return self._wpath(super().blob_dir(scope))

    def table_dir(self, scope: str) -> str:
        return self._wpath(super().table_dir(scope))

    # ── 미러 인덱스 (읽기 전용) ---------------------------------------------------------
    def _load_mirror_index(self, scope: str) -> pd.DataFrame:
        key = scope
        if key in self._mirror_idx:
            return self._mirror_idx[key]
        frames: List[pd.DataFrame] = []
        for mr in self.mirrors:
            base = os.path.join(mr, GDRIVE_SHARED_NS if scope == "shared" else GDRIVE_PRIVATE_NS)
            idx_dir = os.path.join(base, "index")
            if not os.path.isdir(idx_dir):
                continue
            got: List[pd.DataFrame] = []
            d, _st = ro_read_parquet(os.path.join(idx_dir, "index.parquet"))
            if d is not None and len(d):
                got.append(d)
            elif _st not in ("ok", "FileNotFoundError"):
                LOG.debug(f"미러 인덱스 읽기 건너뜀({_st}): {idx_dir} — 파일은 그대로 둡니다.")
            jr = read_jsonl(os.path.join(idx_dir, "index.jsonl"))
            if jr:
                got.append(pd.DataFrame(jr))
            if not got:
                continue
            allc: List[str] = []
            for g in got:
                for c in g.columns:
                    if c not in allc:
                        allc.append(c)
            g2 = pd.concat([g.reindex(columns=allc) for g in got], ignore_index=True)
            g2["_root"] = mr
            frames.append(g2)
            self.stats[f"mirror_index_read:{os.path.basename(mr)}"] += len(g2)
        if not frames:
            out = pd.DataFrame(columns=list(INDEX_COLUMNS) + ["_root"])
        else:
            allc = []
            for f in frames:
                for c in f.columns:
                    if c not in allc:
                        allc.append(c)
            out = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
            if "uid" not in out.columns:
                out["uid"] = np.nan
            miss = out["uid"].isna() | out["uid"].astype(str).str.strip().isin(("", "nan", "None"))
            if miss.any():
                src = [c for c in ("path", "abs_path", "key", "sha1", "_root") if c in out.columns]
                out.loc[miss, "uid"] = [
                    sha1_str("mirror", i, *[str(out.iloc[i].get(c, "")) for c in src])
                    for i in np.where(miss.to_numpy())[0]]
            out["uid"] = out["uid"].astype(str)
            out = out.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        self._mirror_idx[key] = out
        return out

    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        own = super().load_index(scope, force=force)
        if self._own_only:
            return own
        if not force:
            cached = self._merged.get(scope)
            if cached is not None:
                return cached
        mir = self._load_mirror_index(scope)
        if mir.empty:
            self._merged[scope] = own
            return own
        o = own.copy()
        if "_root" not in o.columns:
            o["_root"] = self.root
        else:
            o["_root"] = o["_root"].fillna(self.root)
        allc: List[str] = []
        for f in (o, mir):
            for c in f.columns:
                if c not in allc:
                    allc.append(c)
        merged = pd.concat([o.reindex(columns=allc), mir.reindex(columns=allc)], ignore_index=True)
        # 쓰기루트(own)를 뒤에 두지 않는다 — 같은 uid 면 '쓰기루트 우선'이어야 하므로
        # keep="first" 로 own 이 이긴다.
        merged = merged.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)
        with self._lk:
            self._idx[scope] = merged
            self._uidset[scope] = set(merged["uid"].astype(str).tolist())
            self._merged[scope] = merged
        return merged

    # ── 다중루트 읽기 -------------------------------------------------------------------
    def get_table(self, name: str, scope: str = "shared",
                  max_age_days: Optional[float] = None) -> Optional[pd.DataFrame]:
        d = super().get_table(name, scope=scope, max_age_days=max_age_days)
        if d is not None:
            self.table_src[name] = self.root
            return d
        for mr in self.mirrors:
            for sc in (scope, "private" if scope == "shared" else "shared"):
                ns = GDRIVE_SHARED_NS if sc == "shared" else GDRIVE_PRIVATE_NS
                p = os.path.join(mr, ns, "table", f"{name}.parquet")
                if not os.path.exists(p):
                    continue
                if max_age_days is not None:
                    if (time.time() - os.path.getmtime(p)) / 86400.0 > max_age_days:
                        continue
                dd, _st = ro_read_parquet(p)
                if dd is None or not len(dd):
                    if _st not in ("ok", "FileNotFoundError"):
                        LOG.debug(f"미러 테이블 읽기 건너뜀({_st}): {p} — 파일은 그대로 둡니다.")
                    continue
                self.table_src[name] = mr
                self.stats[f"mirror_table_hit:{name}"] += 1
                LOG.info(f"로컬/미러 캐시 적중: {name} ({len(dd):,}행) ← {mr}")
                PIPE.io("IN", "MIRROR", f"table:{name}", dd, source=mr)
                if self.promote_tables:
                    # 드라이브에 '없을 때만' 승격한다 → 최신본을 과거본으로 덮을 수 없다.
                    try:
                        self.put_table(name, dd, scope=scope, domain="table",
                                       source=f"promoted_from_mirror:{os.path.basename(mr)}")
                        LOG.ok(f"  → 구글드라이브로 승격 복사 완료 (원본은 그대로 둡니다): {name}")
                    except Exception as e:                       # noqa
                        LOG.warn(f"  → 드라이브 승격 실패({type(e).__name__}) — 읽기만 하고 진행합니다.")
                return dd
        return None

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        if rows.empty:
            return None
        for _, r in rows.iterrows():
            base = str(r.get("_root") or self.root)
            cands = [r.get("abs_path")]
            rel = str(r.get("path") or "")
            if rel:
                cands.append(os.path.join(base, rel))
                if base != self.root:
                    cands.append(os.path.join(self.root, rel))
            for cand in cands:
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

    # ── O(1) 인덱스 계층 -----------------------------------------------------------------
    #  ★ 공용 Vault 는 규모를 가정하지 않고 짜여 있다. 30만 행 인덱스 + 수만 건 blob 조회에서는
    #    그 가정이 그대로 병목이 된다. 세 곳을 상수시간으로 내린다(코어는 손대지 않는다):
    #      ① has()      : _pending 리스트 선형탐색 → uid 집합 조회. 신규 uid n 건이면 O(n²)→O(n)
    #      ② load_index : 호출마다 미러 재병합 → 더티 플래그 캐시
    #      ③ get_blob   : 전 인덱스 불리언 마스크 → uid→경로 사전
    def _register(self, scope: str, rec: dict):
        super()._register(scope, rec)
        self._merged.pop(scope, None)
        self._uidpath.pop(scope, None)

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            # _register 가 이미 _uidset 에 넣으므로 pending 을 따로 훑을 필요가 없다.
            return str(uid) in self._uidset.get(scope, set())

    def _uid_path_map(self, scope: str) -> Dict[str, Tuple[str, str, str]]:
        m = self._uidpath.get(scope)
        if m is not None:
            return m
        idx = self.load_index(scope)
        m = {}
        if len(idx):
            root_col = (idx["_root"].astype(str) if "_root" in idx.columns
                        else pd.Series([self.root] * len(idx), index=idx.index))
            for u, ap, rel, rt in zip(idx["uid"].astype(str),
                                      idx.get("abs_path", pd.Series([""] * len(idx))).astype(str),
                                      idx.get("path", pd.Series([""] * len(idx))).astype(str),
                                      root_col):
                m[u] = (ap, rel, rt if rt and rt != "nan" else self.root)
        self._uidpath[scope] = m
        return m

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        ent = self._uid_path_map(scope).get(str(uid))
        if ent is None:
            return None
        ap, rel, base = ent
        cands = [ap]
        if rel and rel not in ("", "nan"):
            cands.append(os.path.join(base, rel))
            if base != self.root:
                cands.append(os.path.join(self.root, rel))
        for c in cands:
            try:
                if c and c not in ("", "nan") and os.path.exists(c):
                    return open(c, "rb").read()
            except Exception:
                continue
        return None

    # ── 기존 리포트 폴더 흡수 (드라이브 FUSE 안전판) --------------------------------------
    _MANAGED_DIRNAMES = {"blob", "table", "index", "_backup", "_locks", "reports"}
    _SKIP_DIRNAMES = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules",
                      ".cache", ".Trash", "$RECYCLE.BIN", "System Volume Information"}

    def _managed_keys(self) -> set:
        """쓰기루트·미러의 관리 트리. 여기는 이미 인덱스에 있으므로 절대 걷지 않는다."""
        out = set()
        for r in [self.root] + list(self.mirrors):
            out.add(_same_place_key(r))
            for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):
                p = os.path.join(r, ns)
                if os.path.isdir(p):
                    out.add(_same_place_key(p))
        return out

    def adopt_scan(self, dirs: Sequence[str], max_files: int = None,
                   max_seconds: float = None) -> pd.DataFrame:
        """기존에 모아둔 리포트를 '등록만' 한다. 이동·개명·삭제 없음.

        ★ 사용자의 실제 Colab 실행이 여기서 멈췄다. 원인은 하나가 아니라 넷이 겹친 것이었다:
          ① 캐시 루트 자신을 스캔했다 → blob 은 내용해시 2단이라 최대 65,536개 디렉터리이고
             드라이브 FUSE 에서 listdir 한 번이 50~200ms 다. 열거만 1~2시간인데,
             그 파일들은 '이미 인덱스에 있는 것'이라 전부 무의미한 작업이다.
          ② /content/drive/MyDrive 와 /content/drive/My Drive 를 중복 스캔했다.
          ③ 파일마다 getsize() 로 FUSE 왕복이 한 번 더 붙었다.
          ④ 코어의 max_files 상한은 안쪽 for 만 끊고 os.walk 는 계속 돌았다.
        → 관리 트리 프루닝 + 실체 기준 중복제거 + scandir 1회 stat + '진짜' 상한 +
          디렉터리 mtime 체크포인트(재실행 시 이어받기) + 진행률 출력.
        """
        max_files = int(ADOPT_SCAN_MAX_FILES if max_files is None else max_files)
        max_seconds = float(ADOPT_SCAN_MAX_SECONDS if max_seconds is None else max_seconds)
        if not ADOPT_SCAN_ENABLED:
            LOG.info("ADOPT_SCAN_ENABLED=False — 기존 리포트 폴더 스캔을 건너뜁니다 "
                     "(인덱스에 이미 등록된 자료는 그대로 사용됩니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])

        managed = self._managed_keys()
        roots, skipped_missing, skipped_managed = [], [], []
        seen_keys = set()
        for d in dirs:
            if not d:
                continue
            e = _expand(d)
            if not os.path.isdir(e):
                skipped_missing.append(d)
                continue
            k = _same_place_key(e)
            if k in managed:
                skipped_managed.append(e)
                continue
            if k in seen_keys:
                continue
            seen_keys.add(k)
            roots.append(e)

        if skipped_missing:
            LOG.info(f"존재하지 않는 스캔 경로 {len(skipped_missing)}개는 건너뜁니다"
                     f"(로컬 D: 가 없는 환경에서는 정상): "
                     f"{_trunc(', '.join(skipped_missing[:4]), 70)}")
        if skipped_managed:
            LOG.info(f"캐시 관리 트리 {len(skipped_managed)}개는 스캔 대상에서 제외합니다 — "
                     f"이미 인덱스에 있고, blob 은 내용해시 2단 구조라 드라이브에서 열거만 "
                     f"수 시간이 걸립니다.")
        if not roots:
            LOG.info("스캔할 외부 리포트 폴더가 없습니다. (기존 인덱스는 그대로 사용됩니다)")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])

        # 디렉터리 mtime 체크포인트 — 바뀌지 않은 폴더는 다시 걷지 않는다
        ckpt: Dict[str, float] = {}
        cdf = self.get_table("qvf_adopt_scan_state", scope="private")
        if cdf is not None and len(cdf):
            try:
                ckpt = dict(zip(cdf["dirpath"].astype(str),
                                pd.to_numeric(cdf["mtime"], errors="coerce").fillna(-1.0)))
            except Exception:
                ckpt = {}
            LOG.info(f"이전 스캔 체크포인트 {len(ckpt):,}개 디렉터리 — 변경되지 않은 폴더는 "
                     f"다시 걷지 않습니다.")

        t0 = time.time()
        found: List[dict] = []
        new_ckpt: Dict[str, float] = dict(ckpt)
        n_files = n_dirs = n_skipped_dirs = 0
        stopped = ""

        for root in roots:
            if stopped:
                break
            LOG.info(f"기존 리포트 폴더 스캔: {root}")
            stack = [root]
            while stack:
                if time.time() - t0 > max_seconds:
                    stopped = f"시간 예산 {max_seconds:.0f}초 초과"
                    break
                if n_files >= max_files:
                    stopped = f"파일 상한 {max_files:,}건 도달"
                    break
                cur = stack.pop()
                try:
                    st_m = os.stat(cur).st_mtime
                except Exception:
                    continue
                n_dirs += 1
                if n_dirs % 200 == 0:
                    LOG.info(f"  … 디렉터리 {n_dirs:,} · 파일 {n_files:,} · "
                             f"{time.time()-t0:.0f}초 경과")
                unchanged = (abs(ckpt.get(cur, -1.0) - st_m) < 1e-6)
                new_ckpt[cur] = st_m
                try:
                    with os.scandir(cur) as it:
                        for ent in it:
                            try:
                                if ent.is_dir(follow_symlinks=False):
                                    nm = ent.name
                                    if (nm.startswith(".") or nm in self._MANAGED_DIRNAMES
                                            or nm in self._SKIP_DIRNAMES):
                                        n_skipped_dirs += 1
                                        continue
                                    if _same_place_key(ent.path) in managed:
                                        n_skipped_dirs += 1
                                        continue
                                    stack.append(ent.path)
                                    continue
                                if unchanged:
                                    continue          # 내용이 안 바뀐 폴더의 파일은 건너뛴다
                                low = ent.name.lower()
                                if low.endswith(".pdf"):
                                    kind = "report_pdf"
                                elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                                        any(t in low for t in
                                            ("report", "consensus", "research", "analyst",
                                             "hankyung", "naver", "dart", "krx", "price",
                                             "ohlcv", "universe", "fnltt")):
                                    kind = "table_like"
                                else:
                                    continue
                                try:
                                    sz = ent.stat(follow_symlinks=False).st_size
                                except Exception:
                                    sz = -1
                                found.append({"abs_path": ent.path, "kind": kind,
                                              "name": ent.name, "dir": cur, "bytes": sz})
                                n_files += 1
                                if n_files >= max_files:
                                    break
                            except Exception:
                                continue
                except Exception as e:                              # noqa
                    LOG.debug(f"  디렉터리 열람 실패({type(e).__name__}): {cur}")
                    continue

        dur = time.time() - t0
        if not found:
            LOG.info(f"새로 등록할 리포트 파일이 없습니다 (디렉터리 {n_dirs:,}개 · {dur:.1f}초"
                     + (f" · {stopped}" if stopped else "") + "). "
                     f"이미 인덱스에 있는 자료는 그대로 사용됩니다.")
        else:
            df = pd.DataFrame(found)
            for r in df.itertuples(index=False):
                m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
                ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
                self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                           subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                           event_date=ed, knowledge_date=ed, scope="shared",
                           extra={"dir": r.dir})
            self.flush("shared")
            LOG.ok(f"기존 리포트 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
                   f"(파일은 원위치 그대로, 이동·삭제 없음) — "
                   f"디렉터리 {n_dirs:,}개 · {dur:.1f}초")

        if stopped:
            LOG.warn(f"스캔을 중단했습니다: {stopped}. 여기까지의 체크포인트를 저장했으므로 "
                     f"다음 실행에서 걷지 않은 폴더부터 이어받습니다. 상한을 늘리려면 "
                     f"ADOPT_SCAN_MAX_FILES / ADOPT_SCAN_MAX_SECONDS 를 조정하세요.")
        try:
            self.put_table("qvf_adopt_scan_state",
                           pd.DataFrame({"dirpath": list(new_ckpt.keys()),
                                         "mtime": list(new_ckpt.values())}),
                           scope="private", domain="index", source="adopt_scan checkpoint")
        except Exception as e:                                      # noqa
            LOG.debug(f"스캔 체크포인트 저장 실패({type(e).__name__}) — 기능에 영향 없음")
        return pd.DataFrame(found) if found else pd.DataFrame(columns=["abs_path", "kind", "name"])

    def compact(self, scope: str):
        """★ 미러 행을 드라이브 인덱스에 쓰면 안 된다.

        load_index 는 조회 편의를 위해 미러 행을 합쳐서 돌려주는데, 부모의 compact 는
        그 결과를 그대로 index.parquet 에 기록한다. 그러면 '로컬에만 존재하는 파일 경로'가
        공용 드라이브 인덱스에 박히고, 다른 기기·다른 전략이 그 경로를 열려다 실패한다.
        컴팩션 동안만 자기 루트 전용 모드로 내린다.
        """
        keep = self._own_only
        self._own_only = True
        try:
            super().compact(scope)
        finally:
            self._own_only = keep
            self._idx.pop(scope, None)      # 합쳐진 조회용 뷰를 다음 조회에서 재구성
            self._uidset.pop(scope, None)
            self._merged.pop(scope, None)
            self._uidpath.pop(scope, None)

    def report_roots(self):
        rows = [["쓰기 루트 (신규 수집분 저장)", self.root, self.mode]]
        for m in self.mirrors:
            rows.append(["읽기 전용 미러", m, "탐색만 — 절대 쓰지 않음"])
        missing = [m for m in CACHE_MIRROR_ROOTS if not os.path.isdir(_expand(m))]
        if missing:
            rows.append(["(없음 — 건너뜀)", _trunc(", ".join(missing), 44),
                         "이 환경에 없는 경로. 정상입니다"])
        LOG.table(rows, ["역할", "경로", "비고"], ["l", "l", "l"],
                  title="캐시 루트 구성 (로컬·드라이브 양쪽 탐색 → 신규는 드라이브에만 기록)")
        if not self.mirrors:
            LOG.info("읽기 전용 미러가 없습니다 — 구글드라이브만 탐색합니다. "
                     "로컬 D: 가 없는 PC나 Colab 에서는 정상이며, 기능에 영향이 없습니다. "
                     "다른 PC의 로컬 캐시를 함께 쓰려면 CACHE_MIRROR_ROOTS 에 경로를 "
                     "추가하세요(탐색만 하고 절대 쓰지 않습니다).")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  DART 일일 호출한도 — 고정값이 아니라 '실측·발견'                                          ║
# ║                                                                                          ║
# ║  사실 확인: OpenDART 는 잔여 호출량을 알려주는 엔드포인트나 응답필드/헤더를 제공하지        ║
# ║  않는다. 확인 가능한 신호는 한도 초과 시 돌아오는 status="020" 뿐이다.                     ║
# ║  → 따라서 '남은 양'은 조회하는 것이 아니라 다음 방식으로 실측한다:                          ║
# ║     ① 같은 키를 쓰는 모든 전략이 공용 저널에 사용량을 append 한다 (전략 간 합산)            ║
# ║     ② 020 을 처음 만난 순간의 누적 사용량 = 그날의 실측 상한. 저널에 기록한다.              ║
# ║     ③ 과거에 실측된 상한이 있으면 그것을 '계획용 추정치'로 쓰되, 소비는 020 이 실제로       ║
# ║        올 때까지 계속한다. 추정치 때문에 남은 호출을 못 쓰는 일이 없다.                     ║
# ║     ④ 상한이 아직 미확정이면 '미확정'이라고 표시한다. 20,000 같은 숫자를 지어내지 않는다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class DartQuota:
    """DartBudget 의 드롭인 대체(take/refund/close/n/exhausted 동일 인터페이스).

    ★ 공용 스코프에 기록하는 이유: 하나의 DART 키를 여러 전략(TCD, QVF …)이 나눠 쓰면
      전략별 사설 카운터는 서로를 못 본다. 그러면 각자 '아직 여유 있다'고 믿으면서
      합계로는 한도를 넘겨 020 폭풍을 맞는다.
    """

    FLUSH_EVERY = 200
    # DART 한도는 한국시간 자정에 리셋된다. 로컬시간을 쓰면 Colab(UTC)에서 9시간 어긋나고,
    # 구축 시점에 한 번만 계산하면 자정을 넘긴 장시간 실행이 '어제 한도'에 계속 묶인다.
    KST = _dt.timezone(_dt.timedelta(hours=9))

    @staticmethod
    def _day_key() -> str:
        return _dt.datetime.now(DartQuota.KST).date().isoformat()

    def __init__(self, vault: "Vault"):
        self.vault = vault
        self.today = self._day_key()
        self.key_fp = sha1_str("dartkey", DART_API_KEY or "")[:12]
        self.n = 0                     # 이번 프로세스가 쓴 양
        self.n_other = 0               # 같은 키로 오늘 다른 프로세스/전략이 쓴 양
        self.observed_limit: Optional[int] = None   # 오늘 실측된 상한
        self.hist_limit: Optional[int] = None       # 과거 실측 상한(계획용 추정치)
        self._exhausted = False
        self._lk = threading.RLock()
        self._unflushed = 0
        self._probe_at = 0.0
        self._load()
        # 공용 코어(12_ingest_dart_fin)가 모듈 로드 시점에 DART_DAILY_LIMIT 를 19,000 으로
        # 되돌려 놓는다(조립 순서상 헤더보다 뒤). 사용자가 명시적으로 거부한 값이므로
        # 실측 소유자인 이 클래스가 되찾아온다. 실측되면 그 값으로 다시 덮인다.
        globals()["DART_DAILY_LIMIT"] = int(self.hist_limit or DART_DAILY_LIMIT_HINT)

    def _roll_if_needed(self):
        """자정(KST)을 넘겼으면 카운터를 새 날짜로 되돌린다. 며칠에 걸친 콜드빌드에서
        '어제 소진'을 오늘까지 끌고 가 하루를 통째로 버리는 사고를 막는다."""
        d = self._day_key()
        if d == self.today:
            return
        self._flush_locked()
        LOG.ok(f"DART 한도 리셋 감지 (KST {self.today} → {d}) — 카운터를 초기화하고 계속합니다.")
        self.today = d
        self.n = 0
        self.n_other = 0
        self.observed_limit = None
        self._exhausted = False
        self._unflushed = 0

    # -- 저널 ---------------------------------------------------------------------------
    def _path(self) -> str:
        return os.path.join(self.vault.ns["shared"], "index", "dart_quota.jsonl")

    def _mirror_paths(self) -> List[str]:
        out = []
        for mr in getattr(self.vault, "mirrors", []) or []:
            p = os.path.join(mr, GDRIVE_SHARED_NS, "index", "dart_quota.jsonl")
            if os.path.exists(p):
                out.append(p)
        return out

    def _load(self):
        rows: List[dict] = []
        for p in [self._path()] + self._mirror_paths():
            rows.extend(read_jsonl(p))
        mine_pid = os.getpid()
        for r in rows:
            if str(r.get("key_fp")) != self.key_fp:
                continue
            if r.get("event") == "limit_observed":
                try:
                    lim = int(r.get("limit", 0))
                except Exception:
                    continue
                if lim > 0:
                    self.hist_limit = max(self.hist_limit or 0, lim)
                    if str(r.get("date")) == self.today:
                        self.observed_limit = lim
                        self._exhausted = True
            elif r.get("event") == "use" and str(r.get("date")) == self.today:
                try:
                    k = int(r.get("n", 0))
                except Exception:
                    k = 0
                # 같은 pid 의 기록은 재실행 시 '남이 쓴 양'으로 다시 세면 안 되지만,
                # 프로세스가 죽었다 살아난 경우엔 실제로 소비된 양이므로 세는 게 맞다.
                # 보수적으로(=과다계상 방향) 전부 센다. 과소계상은 020 폭풍을 부른다.
                self.n_other += max(0, k)
        if self.n_other:
            LOG.info(f"오늘 이 DART 키로 이미 사용된 호출 {self.n_other:,}건 "
                     f"(다른 전략/이전 실행 포함, 공용 저널 기준) — 이어서 진행합니다.")
        if self.observed_limit:
            LOG.warn(f"오늘({self.today}) 이 키의 실측 한도 {self.observed_limit:,}건에 이미 "
                     f"도달한 기록이 있습니다. DART 신규 수집은 건너뛰고 캐시로 진행합니다. "
                     f"내일 재실행하면 정확히 이 지점부터 이어받습니다.")
        elif self.hist_limit:
            LOG.info(f"과거 실측된 일일 한도 {self.hist_limit:,}건을 '계획용 추정치'로만 씁니다. "
                     f"실제 소비는 서버가 020(한도초과)을 줄 때까지 계속합니다 — "
                     f"추정치 때문에 남은 호출을 놀리지 않습니다.")
        else:
            LOG.info("이 키의 일일 한도 실측 기록이 아직 없습니다. OpenDART 는 잔여량 조회 API 를 "
                     "제공하지 않으므로, 서버가 020 을 줄 때까지 소비하며 그 지점을 한도로 "
                     "기록합니다(다음 실행부터 계획에 반영됩니다).")

    def _append(self, rec: dict):
        rec = {"date": self.today, "key_fp": self.key_fp, "pid": os.getpid(),
               "host": platform.node(), "ts": _dt.datetime.now().isoformat(timespec="seconds"),
               **rec}
        try:
            with self.vault.lock("dart_quota", timeout=15.0):
                append_jsonl(self._path(), [rec])
        except Exception:
            try:
                append_jsonl(self._path(), [rec])
            except Exception:
                pass

    # -- 인터페이스 ---------------------------------------------------------------------
    @property
    def used_today(self) -> int:
        return self.n + self.n_other

    @property
    def exhausted(self) -> bool:
        return self._exhausted

    @exhausted.setter
    def exhausted(self, v: bool):
        """★ 공용 코어(dart_api)가 status 020/021 을 보면 여기에 True 를 넣는다.
        그 순간의 누적 사용량이 곧 '오늘의 실측 한도'다. 이 setter 가 발견 지점이다."""
        v = bool(v)
        if not v:
            self._exhausted = False
            return
        if self._exhausted:
            return
        # ★ 공용 코어는 020(일일한도 초과)과 021(조회 가능 회사 수 초과)을 같은 분기에서
        #   처리하며 둘 다 여기로 True 를 보낸다. 그런데 021 은 '요청이 잘못됐다'는 뜻이지
        #   한도와 아무 상관이 없다. 이를 한도로 기록하면 (a) 남은 호출을 전부 못 쓰고
        #   (b) 그 거짓 상한이 공용 저널에 박혀 내일 이후 실행과 '다른 전략'까지 오염된다.
        #   → 값싼 확인 호출을 한 번 던져 진짜 020 인지 확증한 뒤에만 기록한다.
        self._exhausted = True                      # 확인 전까지는 잠정 정지(호출 폭주 방지)
        if not self._confirm_exhaustion():
            self._exhausted = False
            LOG.warn("DART 오류를 받았지만 확인 호출이 성공했습니다 — 일일한도(020)가 아니라 "
                     "요청 오류(021 등)로 판단하고 수집을 계속합니다. 한도로 기록하지 않습니다.")
            return
        self.observed_limit = int(self.used_today)
        self._flush()
        self._append({"event": "limit_observed", "limit": int(self.observed_limit)})
        globals()["DART_DAILY_LIMIT"] = int(self.observed_limit)
        LOG.warn(f"DART 일일 한도 실측: {self.observed_limit:,}건에서 020(한도초과)을 확인했습니다. "
                 f"여기까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 정확히 "
                 f"이 지점부터 이어받습니다. (한도값을 코드에 고정하지 않고 실측한 값입니다)")

    def _confirm_exhaustion(self) -> bool:
        """가장 값싼 정상 요청을 한 번 던져 020 이 재현되는지 본다. True = 진짜 한도 소진."""
        now = time.monotonic()
        if now - self._probe_at < 30.0:
            return True                              # 직전에 확인함 — 중복 확인 금지
        self._probe_at = now
        if not DART_API_KEY:
            return True
        try:
            d = (_dt.datetime.now(self.KST) - _dt.timedelta(days=3)).strftime("%Y%m%d")
            js = http_json("https://opendart.fss.or.kr/api/list.json", source="dart", tries=1,
                           params={"crtfc_key": DART_API_KEY, "bgn_de": d, "end_de": d,
                                   "page_no": 1, "page_count": 1},
                           referer="https://opendart.fss.or.kr/")
        except Exception:
            return True                              # 확인 불가 → 보수적으로 소진 처리
        if not isinstance(js, dict):
            return True
        st = str(js.get("status", ""))
        # 000(정상) 또는 013(데이터 없음)이면 키는 살아 있다 = 한도 소진이 아니다.
        return st not in ("000", "013")

    def take(self, k: int = 1) -> bool:
        if not DART_API_KEY:
            return False
        with self._lk:
            self._roll_if_needed()
            if self._exhausted:
                return False
            # 과거 실측 상한이 있으면 '거기서 멈추지 않고' 계속 쓴다(§요구사항).
            # 다만 추정치의 2배를 넘어서면 저널이 오염됐을 가능성이 크므로 안전 정지한다.
            if self.hist_limit and self.used_today > self.hist_limit * 2:
                LOG.warn(f"누적 사용량({self.used_today:,})이 과거 실측 한도({self.hist_limit:,})의 "
                         f"2배를 넘었습니다. 저널 오염 가능성이 있어 안전 정지합니다.")
                self._exhausted = True
                return False
            self.n += k
            self._unflushed += k
            if self._unflushed >= self.FLUSH_EVERY:
                self._flush_locked()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)
            self._unflushed = max(0, self._unflushed - k)

    def _flush_locked(self):
        if self._unflushed <= 0:
            return
        k, self._unflushed = self._unflushed, 0
        self._append({"event": "use", "n": int(k)})

    def _flush(self):
        with self._lk:
            self._flush_locked()

    def remaining_str(self) -> str:
        if self.observed_limit is not None:
            return f"0 (오늘 실측 한도 {self.observed_limit:,} 도달)"
        if self.hist_limit:
            return f"약 {max(0, self.hist_limit - self.used_today):,} (과거 실측 {self.hist_limit:,} 기준 추정)"
        return "미확정 (OpenDART 는 잔여량 API 를 제공하지 않음 — 020 수신 시 확정)"

    def report(self):
        LOG.table([["오늘 날짜", self.today],
                   ["키 지문", self.key_fp or "(키 없음)"],
                   ["이번 실행 사용", f"{self.n:,}"],
                   ["오늘 누적 사용(공용 저널)", f"{self.used_today:,}"],
                   ["오늘 실측 한도", f"{self.observed_limit:,}" if self.observed_limit else "미도달"],
                   ["과거 실측 한도", f"{self.hist_limit:,}" if self.hist_limit else "기록 없음"],
                   ["남은 호출량", self.remaining_str()]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출량 (고정 상수가 아니라 실측 — 공용 저널로 전략 간 합산)")

    def close(self):
        self._flush()


DQUOTA: Optional["DartQuota"] = None
