

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스                                 ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★                                  ║
# ║                                                                                          ║
# ║  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:                                        ║
# ║   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않으므로              ║
# ║      코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없다.                                    ║
# ║   2) index.parquet 은 저널의 파생물(캐시)일 뿐이다. 재생성 전 항상 타임스탬프 백업.        ║
# ║   3) 컬럼은 합집합으로만 확장한다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않는다.          ║
# ║   4) 원본 blob 은 내용해시 기반 경로에 쓰므로 같은 내용은 재기록조차 하지 않는다.          ║
# ║      내용이 다르면 새 리비전으로 쓰고, 기존 파일은 건드리지 않는다.                        ║
# ║   5) 이미 드라이브에 있던 리포트는 "옮기지 않고 경로만 등록"한다(adopt-by-reference).      ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 한다.              ║
# ║                                                                                          ║
# ║  공용 인덱스(_shared) : 다른 전략에서도 그대로 재활용 가능한 원본/정제본                   ║
# ║  전용 인덱스(tcd_v2)  : 이 전략 고유의 피처·스코어·리포트                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "2.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "extra",
]


def _mount_drive() -> Tuple[str, str]:
    """(루트경로, 상태문자열). Colab이면 마운트 시도, 아니면 로컬 폴백. 어느 쪽이든 죽지 않는다."""
    if ENV["colab"]:
        try:
            from google.colab import drive as _gdrive      # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return GDRIVE_ROOT, "COLAB_DRIVE"
            return LOCAL_CACHE_ROOT, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                             # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return LOCAL_CACHE_ROOT, "COLAB_MOUNT_ERROR→LOCAL"
    # JupyterLab / CLI: 드라이브가 이미 동기화되어 있으면 그 경로를 쓴다.
    for cand in (GDRIVE_ROOT, os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return LOCAL_CACHE_ROOT, "LOCAL"


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★ 2단 캐시 — 로컬 미러 + 드라이브 원본
#
#  구글드라이브(Colab 마운트든 데스크톱 동기화든)는 로컬 디스크가 아니라 네트워크
#  파일시스템에 가깝다. 실측으로 340MB 짜리 일봉 테이블 한 번 읽기가 수십 초다.
#  같은 실행 안에서의 중복 읽기는 세션 메모가 이미 막고 있지만, **실행이 바뀌면**
#  다시 처음부터 드라이브를 읽는다 — 재실행이 잦은 이 파이프라인에서 그 비용이 크다.
#
#  → 드라이브에서 읽은 테이블을 로컬 디스크에 그대로 미러링한다. 다음 실행은
#    ① 세션 메모 → ② 로컬 미러 → ③ 드라이브 순으로 찾는다.
#    미러 유효성은 사이드카(.meta.json)에 적어 둔 드라이브 파일의 (mtime, size) 와
#    대조해 판정한다. stat 한 번은 FUSE 에서도 싸고, 읽기는 수십 초다.
#
#  ★ 진실의 원천은 언제나 드라이브다. 미러는 순수한 읽기 가속이며,
#    미러가 없거나 깨져도 결과는 동일하다(그냥 느려질 뿐). 미러는 삭제해도 안전하다.
#  ★ 반대로 **드라이브를 못 쓰는 실행**(마운트 실패·네트워크 단절)에서는 미러가
#    마지막 보루가 된다. 그때는 미러에서 읽고 그 사실을 로그에 남긴다.
#  ★ 미러는 절대 드라이브를 덮어쓰지 않는다. 방향은 항상 드라이브 → 로컬 한쪽뿐이고,
#    put_table 은 드라이브에 먼저 쓴 뒤 그 결과를 미러에 복사한다(절대1원칙).
# ══════════════════════════════════════════════════════════════════════════════════════════
def _default_mirror_root() -> str:
    v = globals().get("LOCAL_MIRROR_ROOT")
    if v:
        return os.path.abspath(str(v))
    if ENV.get("colab"):
        return "/content/tcd_cache_mirror"          # Colab 컨테이너 로컬 SSD
    return os.path.join(os.path.expanduser("~"), ".cache", "tcd_cache_mirror")


class Vault:
    def __init__(self, root: str, mode: str, mirror_root: Optional[str] = None):
        self.root = os.path.abspath(root)
        self.mode = mode
        # 루트가 이미 로컬이면 미러는 무의미하다(같은 디스크를 두 번 쓰는 낭비).
        _mr = os.path.abspath(mirror_root or _default_mirror_root())
        _is_net = ("drive" in self.root.lower() or "clouddrive" in self.root.lower()
                   or "cloudstorage" in self.root.lower() or mode.endswith("DRIVE")
                   or mode == "LOCAL_SYNCED_DRIVE")
        self.mirror_root = _mr if (_is_net and os.path.normpath(_mr) !=
                                   os.path.normpath(self.root)) else None
        self.mirror_stats = Counter()
        if self.mirror_root:
            try:
                os.makedirs(self.mirror_root, exist_ok=True)
            except Exception:                                    # noqa
                self.mirror_root = None
        self.ns = {"shared": os.path.join(self.root, GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            os.makedirs(os.path.join(p, "index"), exist_ok=True)
            os.makedirs(os.path.join(p, "index", "_backup"), exist_ok=True)
            os.makedirs(os.path.join(p, "blob"), exist_ok=True)
            os.makedirs(os.path.join(p, "table"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, pd.DataFrame] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats = Counter()
        # (파일경로, mtime) → 디코딩된 프레임. 같은 실행에서 같은 테이블을 다시 읽지 않는다.
        # 드라이브 동기화 폴더에서 수백 MB 파케이 재읽기는 수십 초짜리 비용이다.
        self._tbl_memo: Dict[tuple, pd.DataFrame] = {}

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 로컬 미러 -----------------------------------------------------------------------
    def _mirror_paths(self, scope: str, name: str) -> Optional[Tuple[str, str]]:
        if not self.mirror_root:
            return None
        d = os.path.join(self.mirror_root, scope, "table")
        return os.path.join(d, f"{name}.parquet"), os.path.join(d, f"{name}.meta.json")

    def _mirror_valid(self, mp: str, meta_p: str, src: str) -> bool:
        """미러가 드라이브 원본과 같은 세대인가. stat 두 번으로 판정한다(읽지 않는다)."""
        try:
            if not (os.path.exists(mp) and os.path.exists(meta_p)):
                return False
            st = os.stat(src)
            m = json.loads(open(meta_p, encoding="utf-8").read() or "{}")
            return (abs(float(m.get("src_mtime", -1)) - st.st_mtime) < 1e-6
                    and int(m.get("src_size", -1)) == int(st.st_size))
        except Exception:                                        # noqa
            return False

    def _mirror_write(self, scope: str, name: str, src: str) -> None:
        """드라이브 원본을 로컬로 복사하고 세대 정보를 사이드카에 남긴다. 실패해도 무해하다."""
        mpz = self._mirror_paths(scope, name)
        if not mpz:
            return
        mp, meta_p = mpz
        try:
            st = os.stat(src)
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            tmp = mp + f".tmp{os.getpid()}"
            shutil.copy2(src, tmp)
            os.replace(tmp, mp)
            atomic_write_text(meta_p, json.dumps(
                {"src": src, "src_mtime": st.st_mtime, "src_size": int(st.st_size),
                 "mirrored_at": _dt.datetime.now().isoformat(timespec="seconds")},
                ensure_ascii=False))
            self.mirror_stats["mirror_write"] += 1
        except Exception as e:                                   # noqa
            # 미러는 순수 가속이다. 실패하면 그냥 다음 실행에 드라이브를 읽으면 된다.
            self.mirror_stats["mirror_write_fail"] += 1
            LOG.debug(f"로컬 미러 기록 실패({type(e).__name__}) — 결과에는 영향 없습니다: {name}")

    # ── 잠금 (두 노트북이 동시에 돌아도 저널이 섞이지 않게) -----------------------------
    @contextmanager
    def lock(self, name: str, timeout: float = 60.0, stale: float = 900.0):
        lp = os.path.join(self.root, "_locks", f"{name}.lock")
        t0 = time.time()
        acquired = False
        while time.time() - t0 < timeout:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "host": platform.node(),
                                         "ts": time.time()}).encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                try:
                    info = json.loads(open(lp).read() or "{}")
                    if time.time() - float(info.get("ts", 0)) > stale:
                        LOG.warn(f"오래된 잠금 해제: {name} (>{stale:.0f}s)")
                        os.remove(lp)
                        continue
                except Exception:
                    try:
                        os.remove(lp)
                    except Exception:
                        pass
                time.sleep(0.4)
        if not acquired:
            LOG.warn(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # ── 인덱스 적재 (기존 것을 절대 건드리지 않고 읽기만) --------------------------------
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []

        # (a) 정규 parquet 인덱스
        p = self.idx_parquet(scope)
        d = read_parquet_safe(p)
        if d is not None and len(d):
            frames.append(d)

        # (b) append-only 저널 (진실의 원천)
        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # (c) 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        legacy_glob = []
        idx_dir = os.path.join(self.ns[scope], "index")
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    legacy_glob.append(os.path.join(idx_dir, fn))
        except Exception:
            pass
        for fp in legacy_glob:
            try:
                if fp.endswith(".parquet"):
                    dd = read_parquet_safe(fp)
                elif fp.endswith(".csv"):
                    dd = pd.read_csv(fp)
                elif fp.endswith(".jsonl"):
                    dd = pd.DataFrame(read_jsonl(fp))
                else:
                    dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                if dd is not None and len(dd):
                    dd["_legacy_file"] = os.path.basename(fp)
                    frames.append(dd)
                    self.stats[f"legacy_index_absorbed:{os.path.basename(fp)}"] += len(dd)
            except Exception:
                continue

        if frames:
            # 컬럼 합집합 — 기존 컬럼을 절대 떨어뜨리지 않는다
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            frames = [f.reindex(columns=allcols) for f in frames]
            idx = pd.concat(frames, ignore_index=True)
            # ★ uid 가 없거나 결측인 레거시 행을 그대로 두면 astype(str) 이 전부 "nan" 이 되고
            #   drop_duplicates(uid) 가 그 파일 전체를 단 한 줄로 붕괴시킨다 = 인덱스 유실.
            #   절대 1원칙에 정면으로 반하므로, 결측 uid 는 행 내용 해시로 개별 부여한다.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | (idx["uid"].astype(str).str.strip().isin(("", "nan", "None")))
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                idx.loc[miss, "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in fill_src])
                    for i in np.where(miss.to_numpy())[0]]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
            idx["uid"] = idx["uid"].astype(str)
            if "collected_at" in idx.columns:
                idx = idx.sort_values("collected_at", kind="stable")
            idx = idx.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        else:
            idx = pd.DataFrame(columns=INDEX_COLUMNS)

        for c in INDEX_COLUMNS:
            if c not in idx.columns:
                idx[c] = np.nan
        idx["scope"] = idx["scope"].fillna(scope)
        with self._lk:
            self._idx[scope] = idx
            self._uidset[scope] = set(idx["uid"].astype(str).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope] or any(r.get("uid") == uid for r in self._pending[scope])

    def lookup(self, scope: str, **eq) -> pd.DataFrame:
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= (idx[k].astype(str) == str(v))
        return idx[m]

    # ── 기록 --------------------------------------------------------------------------
    def _register(self, scope: str, rec: dict):
        rec.setdefault("scope", scope)
        rec.setdefault("schema_ver", VAULT_SCHEMA_VER)
        rec.setdefault("collected_at", _dt.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("strategy", STRATEGY_ID if scope == "private" else "")
        for c in INDEX_COLUMNS:
            rec.setdefault(c, None)
        with self._lk:
            self._pending[scope].append(rec)
            self._uidset.setdefault(scope, set()).add(str(rec["uid"]))
        self.stats[f"register:{scope}:{rec.get('domain')}"] += 1

    def put_blob(self, domain: str, subtype: str, key: str, data: bytes, fmt: str,
                 source: str = "", event_date=None, knowledge_date=None,
                 scope: str = "shared", extra: Optional[dict] = None,
                 uid: Optional[str] = None) -> Optional[str]:
        """원본 바이트를 내용해시 경로에 저장하고 인덱스에 등록. 같은 내용이면 재기록하지 않는다."""
        if not data:
            return None
        h = sha1_bytes(data)
        uid = uid or sha1_str(domain, subtype, key, h)
        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])
        fn = f"{h}.{fmt.lstrip('.')}"
        abspath = os.path.join(sub, fn)
        rel = os.path.relpath(abspath, self.root)
        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                          # noqa
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에만 기록하지 않고 건너뜁니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": rel, "abs_path": abspath, "fmt": fmt, "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "source": source, "adopted": False,
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        return abspath

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        if rows.empty:
            return None
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None,
                  backup: bool = True) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다.

        backup=False 는 **증분 체크포인트 전용**이다. 왜 필요한가:
          이 함수는 한 번 불릴 때마다 전체 파일 작업을 네 번 한다 —
          sha1_file(파일 전체 읽기) → copy2(전량 복사) → parquet 쓰기 → 미러 복사.
          대상이 구글드라이브 FUSE 이고 대상 테이블이 수백 MB 이면 한 번이 수십 초다.
          수집 루프는 청크마다 이 함수를 부르므로(EMP 1,000건·Tier-2 40사) 그 비용이
          수집 시간 자체를 압도하고, _backup 폴더도 청크 수만큼 불어난다.
        ★ 세대 보존 원칙은 깨지지 않는다: 진실의 원천은 append-only 저널이고,
          중간 체크포인트는 같은 실행 안에서 **단조 증가**하는 스냅샷이라
          마지막 저장 한 번만 백업하면 잃을 세대가 없다.
        """
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path) and backup:
            # ★★ 백업 이름을 타임스탬프에서 **내용해시**로 바꿨다 ★★
            #   실측: 340MB 짜리 가격 테이블이 신규 1종목만 있어도 매 실행 통째로 복사됐고,
            #   _backup 에는 개수·용량 상한이 없으며 삭제 API 도 없다(원칙상 있어서도 안 된다).
            #   일 1회 실행이면 10.2GB/월 · 124GB/년 — 무료 15GB 는 44회, 100GB 는 294회에 찬다.
            #   내용해시로 이름을 지으면 **같은 내용은 같은 이름**이라 중복 백업이 사라지고,
            #   내용이 다르면 절대 충돌하지 않는다. 세대는 그대로 보존된다(원칙 유지).
            #   덤으로 타임스탬프 1초 해상도 때문에 같은 초의 두 저장이 앞 백업을 조용히
            #   덮어쓰던 구멍도 닫힌다.
            try:
                _h = sha1_file(path)[:12]
            except Exception:                               # noqa
                _h = f"{_dt.datetime.now():%Y%m%d_%H%M%S}"
            bak = os.path.join(self.ns[scope], "index", "_backup", f"{name}.{_h}.parquet")
            try:
                if not os.path.exists(bak):
                    shutil.copy2(path, bak)
                else:
                    self.stats["backup_dedup"] += 1
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name} "
                         f"(get_table 은 활성 파일이 없거나 못 읽을 때 이 리비전을 읽습니다)")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                              # noqa
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        # 방금 쓴 내용을 세션 메모에 심어 둔다 — 바로 뒤에 get_table 하는 코드가
        # 드라이브에서 같은 것을 다시 읽지 않게 한다(수백 MB 파케이면 수십 초다).
        try:
            with self._lk:
                self._tbl_memo = {k: v for k, v in self._tbl_memo.items() if k[0] != path}
                self._tbl_memo[(path, os.path.getmtime(path))] = df
        except Exception:                                   # noqa
            pass
        # 드라이브에 쓴 그 파일을 로컬로도 복사한다. 방향은 항상 드라이브 → 로컬 한쪽이며,
        # 미러가 드라이브를 덮는 경로는 존재하지 않는다(절대1원칙).
        self._mirror_write(scope, name, path)
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        return path

    def _latest_revision(self, name: str, scope: str) -> Optional[str]:
        """{name}.rev*.parquet 중 가장 최근 것. 활성 파일이 없을 때만 쓰인다."""
        try:
            d = self.table_dir(scope)
            cand = [os.path.join(d, f) for f in os.listdir(d)
                    if f.startswith(f"{name}.rev") and f.endswith(".parquet")]
            return max(cand, key=os.path.getmtime) if cand else None
        except Exception:                                   # noqa
            return None

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None
                  ) -> Optional[pd.DataFrame]:
        """정제 테이블 읽기. **같은 실행 안에서는 파일을 한 번만 읽는다.**

        ★ 왜 메모이제이션이 필요한가. 이 파이프라인은 같은 테이블을 한 실행에서 여러 번
          읽는다 — 예: price_earliest_available 은 fetch_prices 안에서만 2회,
          dart_employees_ext 는 사전점검·수집·마감에서 3회. 구글드라이브 동기화 폴더는
          로컬 디스크가 아니라 네트워크 파일시스템에 가까워서, 수백 MB 파케이 한 번 읽기가
          수십 초다. 그걸 실행마다 중복으로 냈다.
        ★ 무효화는 mtime 으로 한다. 같은 실행에서 put_table 이 파일을 바꾸면 mtime 이
          달라지므로 자동으로 다시 읽는다 — 오래된 값을 붙들고 있을 수 없다.
        ★ 반환은 얕은 복사다. 호출자가 `d["date"] = ...` 처럼 컬럼을 갈아끼워도
          캐시 원본이 오염되지 않는다(공용 캐시를 제자리에서 고치는 것은 절대1원칙 위반이다).
        """
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        # ── 0단계: 로컬 미러가 드라이브와 같은 세대면 **드라이브를 읽지 않는다** ────────────
        #    stat 두 번(≈ms) 으로 판정하고, 유효하면 로컬 디스크에서 읽는다(수십 초 절약).
        _mz = self._mirror_paths(scope, name)
        if _mz and os.path.exists(path) and self._mirror_valid(_mz[0], _mz[1], path):
            try:
                _mt = os.path.getmtime(_mz[0])
                if max_age_days is None or (time.time() - os.path.getmtime(path)
                                            ) / 86400.0 <= max_age_days:
                    _ck = (_mz[0], _mt)
                    with self._lk:
                        _hit = self._tbl_memo.get(_ck)
                    if _hit is not None:
                        self.stats["table_memo_hit"] += 1
                        return _hit.copy(deep=False)
                    _t0 = time.time()
                    _d = read_parquet_safe(_mz[0])
                    if _d is not None:
                        with self._lk:
                            if len(self._tbl_memo) > 64:
                                self._tbl_memo.clear()
                            self._tbl_memo[_ck] = _d
                        self.mirror_stats["mirror_hit"] += 1
                        self.stats["table_read_mirror"] += 1
                        PIPE.io("IN", "PARQUET", f"table:{name}", _d,
                                source=f"로컬 미러 ({time.time()-_t0:.1f}s · 드라이브 재읽기 없음)")
                        return _d.copy(deep=False)
            except Exception:                                    # noqa
                pass                                             # 미러가 깨졌으면 원본으로 간다
        if not os.path.exists(path):
            # 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략이 만든 걸 재활용한다
            alt = "private" if scope == "shared" else "shared"
            path2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if os.path.exists(path2):
                path = path2
            elif _mz and os.path.exists(_mz[0]):
                # ★ 드라이브에 원본이 아예 없다 = 이번 실행에서 드라이브를 못 붙였거나
                #   다른 머신에서 돈 실행이다. 그럴 때 미러는 마지막 보루다 —
                #   "캐시가 있는데도 다시 수집" 하는 것보다 낫다. 사실을 로그로 남긴다.
                LOG.warn(f"드라이브에 {name}.parquet 이 없어 **로컬 미러**에서 읽습니다 "
                         f"({os.path.relpath(_mz[0], self.mirror_root)}). "
                         f"드라이브 마운트를 확인하세요 — 이번 실행의 신규 수집물은 "
                         f"드라이브에 저장되지 못할 수 있습니다.")
                d0 = read_parquet_safe(_mz[0])
                if d0 is not None:
                    self.mirror_stats["mirror_rescue"] += 1
                    return d0.copy(deep=False)
                return None
            else:
                # ★ 마지막 수단: put_table 이 백업 실패로 흘려 둔 리비전 파일.
                #   예전엔 이걸 아무도 읽지 않아, 워터마크·음성캐시 기록이 통째로 새고
                #   다음 실행이 같은 헛수고를 그대로 반복했다(실측 900초대).
                #   ★ 활성 파일이 **있으면** 절대 승격하지 않는다 — 더 넓은 활성본을
                #     더 좁은 옛 스냅샷으로 덮는 '좁혀 덮어쓰기'가 되기 때문이다.
                rev = self._latest_revision(name, scope) or self._latest_revision(name, alt)
                if not rev:
                    return None
                LOG.warn(f"활성 테이블 {name}.parquet 이 없어 리비전 파일을 읽습니다: "
                         f"{os.path.basename(rev)}. 이전 실행에서 백업 복사가 실패해 "
                         f"활성 파일 대신 리비전으로 저장된 기록입니다 — "
                         f"드라이브 용량·권한을 확인하세요.")
                path = rev
        try:
            mt = os.path.getmtime(path)
        except OSError:
            return None
        if max_age_days is not None:
            if (time.time() - mt) / 86400.0 > max_age_days:
                return None
        ck = (path, mt)
        with self._lk:
            hit = self._tbl_memo.get(ck)
        if hit is not None:
            self.stats["table_memo_hit"] += 1
            PIPE.io("IN", "MEM", f"table:{name}", hit, source="세션 내 재사용(파일 재읽기 없음)")
            return hit.copy(deep=False)
        t0 = time.time()
        d = read_parquet_safe(path)
        if d is not None:
            with self._lk:
                # 메모는 (경로, mtime) 키라 무한히 자라지 않는다. 그래도 상한을 둔다.
                if len(self._tbl_memo) > 64:
                    self._tbl_memo.clear()
                self._tbl_memo[ck] = d
            self.stats["table_read"] += 1
            _el = time.time() - t0
            PIPE.io("IN", "DRIVE", f"table:{name}", d, source=os.path.relpath(path, self.root))
            # 드라이브에서 읽었으니 로컬로 미러링해 둔다 — **다음 실행**이 이 비용을 안 낸다.
            self._mirror_write(scope, name, path)
            if _el > 5.0:
                LOG.info(f"드라이브에서 {name} {len(d):,}행 읽는 데 {_el:.1f}초 — "
                         f"이번 실행에서 다시 읽지 않고(세션 메모), 로컬 미러에 복사해 "
                         f"다음 실행도 다시 읽지 않습니다.")
            return d.copy(deep=False)
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,
              source: str = "", event_date=None, knowledge_date=None,
              scope: str = "shared", extra: Optional[dict] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 '경로만' 등록한다. 파일은 읽기만 한다."""
        try:
            sz = os.path.getsize(abs_path)
        except Exception:
            return None
        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)
        if self.has(scope, uid):
            return uid
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": abs_path, "abs_path": abs_path, "fmt": os.path.splitext(abs_path)[1].lstrip("."),
            "bytes": sz, "sha1": "", "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ------------------------------------------------------------------
    def flush(self, scope: Optional[str] = None):
        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""
        scopes = [scope] if scope else ["shared", "private"]
        for sc in scopes:
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)
            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")

    def compact(self, scope: str):
        """저널 → index.parquet 재생성. 저널은 남기고, 기존 parquet 은 반드시 백업한 뒤 교체."""
        self.flush(scope)
        idx = self.load_index(scope, force=True)
        p = self.idx_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 안전을 위해 컴팩션을 건너뜁니다. "
                         f"저널({os.path.basename(self.journal(scope))})에 모든 기록이 남아 있으므로 "
                         f"데이터 유실은 없습니다.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (사용자의 기존 캐시 흡수) --------------------------------------------
    _PDF_PAT = re.compile(r"\.(pdf)$", re.I)
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 400_000) -> pd.DataFrame:
        """기존에 모아둔 리포트/테이블을 재귀 스캔해 '등록만' 한다. 이동·개명·삭제 없음."""
        seen, found = set(), []
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            rd = os.path.realpath(d)
            if rd in seen:
                continue
            seen.add(rd)
            LOG.info(f"기존 캐시 스캔: {d}")
            n = 0
            for dirpath, dirnames, filenames in os.walk(d):
                dirnames[:] = [x for x in dirnames if not x.startswith(".") and x != "_backup"]
                for fn in filenames:
                    if n >= max_files:
                        break
                    fp = os.path.join(dirpath, fn)
                    low = fn.lower()
                    if low.endswith(".pdf"):
                        kind = "report_pdf"
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "nps",
                                                   "price", "ohlcv", "universe", "fnltt")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": fp, "kind": kind, "name": fn,
                                  "dir": dirpath, "bytes": _safe_size(fp)})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        if not found:
            LOG.warn("기존 캐시에서 흡수할 파일을 찾지 못했습니다. "
                     "GDRIVE_ADOPT_DIRS 경로를 확인하세요(오타/미마운트가 가장 흔합니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared",
                       extra={"dir": r.dir})
        self.flush("shared")
        LOG.ok(f"기존 캐시 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
               f"(파일은 원위치 그대로, 이동·삭제 없음).")
        return df

    # ── 감사 --------------------------------------------------------------------------
    def report(self):
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            nb = 0
            try:
                nb = sum(int(x) for x in pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0))
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared" else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}",
                         f"{int(pd.to_numeric(idx.get('adopted'), errors='coerce').fillna(0).sum()):,}"
                         if "adopted" in idx.columns else "0",
                         f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])
        idx = self.load_index("shared")
        if not idx.empty and "domain" in idx.columns:
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(24))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title="공용 인덱스 구성 (다른 전략에서 그대로 재사용 가능)")
        if self.stats:
            LOG.table([[k, f"{v:,}"] for k, v in sorted(self.stats.items())][:24],
                      ["이벤트", "횟수"], ["l", "r"], title="이번 실행의 캐시 이벤트")
        if self.mirror_root:
            _n = self.mirror_stats
            _sz = 0.0
            try:
                for dp, _dn, fns in os.walk(self.mirror_root):
                    _sz += sum(_safe_size(os.path.join(dp, f)) for f in fns if f.endswith(".parquet"))
            except Exception:
                pass
            LOG.table([["로컬 미러 경로", self.mirror_root],
                       ["미러에서 읽음(드라이브 생략)", f"{_n.get('mirror_hit', 0):,}회"],
                       ["미러로 복사", f"{_n.get('mirror_write', 0):,}회"],
                       ["드라이브 부재 시 미러 구제", f"{_n.get('mirror_rescue', 0):,}회"],
                       ["미러 용량", f"{max(_sz,0)/1e9:.2f} GB"]],
                      ["2단 캐시", "값"], ["l", "r"],
                      title="로컬 미러 — 드라이브는 진실의 원천, 로컬은 읽기 가속")
            LOG.info("로컬 미러는 언제 지워도 안전합니다(다음 실행에서 드라이브로부터 다시 만듭니다). "
                     "미러가 드라이브를 덮어쓰는 경로는 존재하지 않습니다.")
        LOG.info("무결성 원칙: 저널은 append-only(기존 줄 재기록 없음) · index.parquet 은 백업 후 교체 · "
                 "blob 은 내용해시 경로라 덮어쓰기 자체가 발생하지 않음 · 삭제 API 없음.")


def _safe_size(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:
        return -1


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return float("nan")


VAULT: Optional[Vault] = None
