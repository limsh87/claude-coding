

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

def _expand(p: str) -> str:
    try:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(str(p))))
    except Exception:
        return str(p)


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

    seen, uniq = set(), []
    for m in mirrors:
        rp = os.path.realpath(m)
        if rp not in seen:
            seen.add(rp)
            uniq.append(m)
    return write_root, mode, uniq


class QVFVault(Vault):
    """Vault + 다중루트 읽기. 쓰기 경로는 부모 그대로(=self.root 전용)라 미러는 절대 안 건드린다."""

    def __init__(self, root: str, mode: str, mirrors: Optional[Sequence[str]] = None,
                 promote_tables: bool = True):
        super().__init__(root, mode)
        self.mirrors: List[str] = [m for m in (mirrors or []) if os.path.isdir(m)]
        self.promote_tables = bool(promote_tables)
        self._mirror_idx: Dict[str, pd.DataFrame] = {}
        self.table_src: Dict[str, str] = {}          # 어느 루트가 이 테이블을 줬는가(감사용)

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
            d = read_parquet_safe(os.path.join(idx_dir, "index.parquet"))
            if d is not None and len(d):
                got.append(d)
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
        mir = self._load_mirror_index(scope)
        if mir.empty:
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
                dd = read_parquet_safe(p)
                if dd is None or not len(dd):
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

    def report_roots(self):
        rows = [["쓰기 루트 (신규 수집분 저장)", self.root, self.mode]]
        for m in self.mirrors:
            rows.append(["읽기 전용 미러", m, "탐색만 — 절대 쓰지 않음"])
        LOG.table(rows, ["역할", "경로", "비고"], ["l", "l", "l"],
                  title="캐시 루트 구성 (로컬·드라이브 양쪽 탐색 → 신규는 드라이브에만 기록)")
        if not self.mirrors:
            LOG.info("읽기 전용 미러가 없습니다. 로컬 D: 등에 기존 캐시가 있다면 "
                     "CACHE_MIRROR_ROOTS 에 경로를 추가하세요(탐색만 하고 절대 쓰지 않습니다).")


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

    def __init__(self, vault: "Vault"):
        self.vault = vault
        self.today = _dt.date.today().isoformat()
        self.key_fp = sha1_str("dartkey", DART_API_KEY or "")[:12]
        self.n = 0                     # 이번 프로세스가 쓴 양
        self.n_other = 0               # 같은 키로 오늘 다른 프로세스/전략이 쓴 양
        self.observed_limit: Optional[int] = None   # 오늘 실측된 상한
        self.hist_limit: Optional[int] = None       # 과거 실측 상한(계획용 추정치)
        self._exhausted = False
        self._lk = threading.RLock()
        self._unflushed = 0
        self._load()

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
        if v and not self._exhausted:
            self._exhausted = True
            self.observed_limit = int(self.used_today)
            self._flush()
            self._append({"event": "limit_observed", "limit": int(self.observed_limit)})
            globals()["DART_DAILY_LIMIT"] = int(self.observed_limit)
            LOG.warn(f"DART 일일 한도 실측: {self.observed_limit:,}건에서 020(한도초과)을 받았습니다. "
                     f"여기까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 정확히 "
                     f"이 지점부터 이어받습니다. (한도값을 코드에 고정하지 않고 실측한 값입니다)")
        else:
            self._exhausted = v

    def take(self, k: int = 1) -> bool:
        if not DART_API_KEY:
            return False
        with self._lk:
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
