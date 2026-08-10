
# ────────────────────────────────────────────────────────────────────────────────────────
#  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스
#  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★
#  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:
# ────────────────────────────────────────────────────────────────────────────────────────

VAULT_SCHEMA_VER = "2.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "extra",
]

def _mount_drive() -> Tuple[str, str]:
    """(루트경로, 상태문자열).

    ★★ 마운트 실패를 조용히 로컬로 폴백하면 안 된다. 드라이브에 이미 모아둔 캐시가 통째로
       안 보이게 되어 **전량 재수집**이 시작되고(일봉 5천 종목 = 수 시간), 새로 받은 것도
       드라이브가 아닌 곳에 쌓인다(사용자의 절대 원칙 위반). 재시도하고, 그래도 안 되면
       계속 진행할지 여부를 명시적으로 정하게 한다.
    """
    if ENV["colab"]:
        mp = "/content/drive"
        last = ""
        for attempt in range(3):
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return GDRIVE_ROOT, "COLAB_DRIVE"
            try:
                from google.colab import drive as _gdrive  # type: ignore
                _gdrive.mount(mp, force_remount=(attempt > 0))
            except Exception as e:                         # noqa
                last = f"{type(e).__name__}: {str(e)[:160]}"
                LOG.warn(f"구글드라이브 마운트 실패 {attempt+1}/3 ({last})")
                time.sleep(2.0 * (attempt + 1))
        if os.path.isdir(os.path.join(mp, "MyDrive")):
            return GDRIVE_ROOT, "COLAB_DRIVE"
        LOG.error("구글드라이브를 마운트하지 못했습니다 (3회 시도). " + (last or ""))
        LOG.error("★ 이대로 진행하면 ① 드라이브의 기존 캐시가 전혀 보이지 않아 일봉·DART·"
                  "리포트를 **전량 재수집**하고 ② 새로 받은 데이터도 드라이브에 저장되지 "
                  "않습니다. 노트북을 재시작하고 드라이브 인증 팝업을 승인한 뒤 다시 "
                  "실행하세요. 그래도 진행하려면 코드 상단에 "
                  "ALLOW_NO_DRIVE = True 를 넣으십시오.")
        if not globals().get("ALLOW_NO_DRIVE", False):
            raise RuntimeError("구글드라이브 마운트 실패 — 캐시 없이 시작하면 전량 재수집이 "
                               "됩니다. ALLOW_NO_DRIVE=True 로 명시하지 않는 한 중단합니다.")
        return os.path.abspath(LOCAL_CACHE_ROOT), "COLAB_MOUNT_ERROR→LOCAL(명시적 허용)"

    # JupyterLab / CLI: 드라이브가 이미 동기화되어 있으면 그 경로를 쓴다.
    # ★ 후보를 CACHE_SEARCH_DIRS 에서 파생시킨다. 예전에는 다른 전략 폴더(tcd_cache)만
    #   후보라, 로컬 동기화 환경에서 신규 수집분이 전부 CWD 상대경로에 쌓였다.
    cands = [GDRIVE_ROOT]
    for d in globals().get("CACHE_SEARCH_DIRS", []):
        e = os.path.expanduser(str(d))
        if re.search(r"(drive|드라이브)", e, re.I) and e not in cands:
            cands.append(e)
    for cand in cands:
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    LOG.warn(f"구글드라이브 경로를 찾지 못해 로컬 캐시({LOCAL_CACHE_ROOT})를 씁니다. "
             f"★ 이 실행의 신규 수집분은 드라이브에 저장되지 않습니다.")
    return os.path.abspath(LOCAL_CACHE_ROOT), "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
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
        self._sibs: Optional[List[str]] = None
        self._lk = threading.RLock()
        self.stats = Counter()

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

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
                # ★ 행 '위치'를 해시에 넣으면 저널이 커질수록 같은 레거시 행의 uid 가
                #   달라져 컴팩션마다 인덱스가 증식한다(5→10→15→20행). 내용만으로 해시한다.
                _sub = idx.loc[miss, fill_src].astype(str) if fill_src else None
                idx.loc[miss, "uid"] = (
                    [sha1_str("legacy", *row) for row in _sub.to_numpy().tolist()]
                    if _sub is not None else
                    [sha1_str("legacy", str(k)) for k in np.where(miss.to_numpy())[0]])
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
            # ★ _pending 선형탐색을 하면 안 된다. _register 가 이미 _uidset 에 uid 를 넣으므로
            #   중복이고, adopt_scan 처럼 파일마다 has() 를 부르는 경로에서 O(n²)가 되어
            #   파일 수가 늘면 사실상 멈춘다(8,000건 3.3초 → 배가마다 3.3배).
            return uid in self._uidset[scope]

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

    def get_blob_by_key(self, domain: str, subtype: str, key: str,
                        scope: str = "shared") -> Optional[bytes]:
        """(domain, subtype, key) 로 원본 바이트를 찾는다.

        put_blob 의 uid 는 내용해시를 포함하므로 호출자가 재구성할 수 없다. 그래서
        uid 를 모르는 소비자(§6.3 완료형 판정 등)는 이 경로로 인덱스를 조회해야 한다.
        ★ 인덱스를 읽기만 한다 — 어떤 경우에도 기존 인덱스를 변형하지 않는다.
        """
        rows = self.lookup(scope, domain=domain, subtype=subtype, key=str(key))
        if rows is None or rows.empty:
            return None
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

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

    # 공용 테이블이 이 비율 아래로 줄면 '수집 실패' 로 보고 교체하지 않는다.
    SHRINK_GUARD = 0.5

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None,
                  allow_shrink: bool = False) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        self._prune_backups(scope, name)

        # ★ 공용 테이블은 전부 누적 수집물이라 정상 실행에서 크게 줄 수 없다. 수집 실패로
        #   빈 프레임이 오면 살아 있는 캐시가 비어버리므로(백업은 남지만 다음 실행이 그
        #   빈 값을 읽는다) 여기서 막는다 — 절대 원칙.
        if (scope == "shared" and not allow_shrink and os.path.exists(path)):
            try:
                n_old = int(pq_num_rows(path))
            except Exception:
                n_old = -1
            n_new = int(len(df))
            if n_old > 0 and n_new < max(1, int(n_old * self.SHRINK_GUARD)):
                rev = os.path.join(self.table_dir(scope),
                                   f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
                try:
                    atomic_write_parquet(df, rev)
                except Exception:
                    rev = "(저장 실패)"
                LOG.warn(f"공용 테이블 '{name}' 이 {n_old:,}행 → {n_new:,}행으로 급감해 "
                         f"교체하지 않았습니다(수집 실패로 판단). 기존 캐시는 그대로 두고 "
                         f"새 결과는 리비전 파일로만 남깁니다: {os.path.basename(str(rev))}. "
                         f"의도한 축소라면 allow_shrink=True 로 호출하세요.")
                return None

        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                              # noqa
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        return path

    BACKUP_KEEP = 3          # 테이블당 남길 백업 세대 수

    def _prune_backups(self, scope: str, name: str):
        """백업 세대 상한. 무한 증식하면 드라이브가 차고, 그 순간 신규 수집분이 소실된다."""
        try:
            bdir = os.path.join(self.ns[scope], "index", "_backup")
            pre = f"{name}."
            fs = sorted(f for f in os.listdir(bdir)
                        if f.startswith(pre) and f.endswith(".parquet"))
            if len(fs) > self.BACKUP_KEEP:
                for f in fs[:-self.BACKUP_KEEP]:
                    try:
                        os.remove(os.path.join(bdir, f))   # 백업의 구세대만 지운다(원본 아님)
                    except Exception:
                        pass
        except Exception:
            pass

    def sibling_table_dirs(self) -> List[str]:
        """다른 전략 볼트의 공용(_shared) 테이블 폴더들.

        ★★ '공용 인덱스'는 전략 간 공유가 목적인데, 볼트 루트가 전략마다 다르면
           (quant_cache vs tcd_cache) 서로의 _shared 를 전혀 못 본다. 그러면 다른 전략이
           이미 받아둔 일봉·DART 원자료를 눈앞에 두고 **전량 재수집**한다.
           읽기 전용으로만 훑는다 — 남의 볼트에 쓰지 않는다.
        """
        if getattr(self, "_sibs", None) is not None:
            return self._sibs
        out, seen = [], {os.path.realpath(self.table_dir("shared"))}
        roots = [os.path.expanduser(str(d)) for d in globals().get("CACHE_SEARCH_DIRS", [])]
        roots += [os.path.dirname(self.root)]                 # 형제 폴더 스캔용 상위
        for r in roots:
            if not r or not os.path.isdir(r):
                continue
            cands = [r] + [os.path.join(r, x) for x in (os.listdir(r)[:200]
                                                        if os.path.isdir(r) else [])]
            for c in cands:
                td = os.path.join(c, GDRIVE_SHARED_NS, "table")
                rp = os.path.realpath(td)
                if os.path.isdir(td) and rp not in seen:
                    seen.add(rp); out.append(td)
        self._sibs = out
        if out:
            LOG.info(f"타 전략 공용 캐시 {len(out)}곳을 읽기 전용으로 함께 조회합니다: "
                     + " · ".join(os.path.relpath(x, os.path.dirname(self.root))
                                  for x in out[:4]))
        return out

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None
                  ) -> Optional[pd.DataFrame]:
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        # ★ 백업 실패로 rev 파일에만 저장된 경우가 있다. 정본이 없으면 최신 rev 를 읽는다 —
        #   그러지 않으면 그 테이블은 영원히 갱신되지 않고 rev 만 쌓인다.
        if not os.path.exists(path):
            try:
                td = self.table_dir(scope)
                revs = sorted(f for f in os.listdir(td)
                              if f.startswith(f"{name}.rev") and f.endswith(".parquet"))
                if revs:
                    LOG.info(f"테이블 '{name}' 정본이 없어 최신 리비전을 사용합니다: {revs[-1]}")
                    return read_parquet_safe(os.path.join(td, revs[-1]))
            except Exception:
                pass
            if scope == "shared":
                for sd in self.sibling_table_dirs():
                    sp = os.path.join(sd, f"{name}.parquet")
                    if os.path.exists(sp):
                        d = read_parquet_safe(sp)
                        if d is not None and len(d):
                            LOG.ok(f"타 전략 공용 캐시에서 '{name}' {len(d):,}행 재사용 "
                                   f"({os.path.dirname(os.path.dirname(sd)).split(os.sep)[-1]})"
                                   f" — 재수집하지 않습니다.")
                            return d
        if not os.path.exists(path):
            # 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략이 만든 걸 재활용한다
            alt = "private" if scope == "shared" else "shared"
            path2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if os.path.exists(path2):
                path = path2
            else:
                return None
        if max_age_days is not None:
            age = (time.time() - os.path.getmtime(path)) / 86400.0
            if age > max_age_days:
                return None
        d = read_parquet_safe(path)
        if d is not None:
            PIPE.io("IN", "DRIVE", f"table:{name}", d, source=os.path.relpath(path, self.root))
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,
              source: str = "", event_date=None, knowledge_date=None,
              scope: str = "shared", extra: Optional[dict] = None,
              size: Optional[int] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 '경로만' 등록한다. 파일은 읽기만 한다."""
        if size is not None and size >= 0:
            sz = int(size)          # 스캔에서 이미 얻은 크기를 재사용(FUSE stat 왕복 절약)
        else:
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

    def adopt_scan(self, dirs: Sequence[str], max_files: Optional[int] = None,
                   budget_s: Optional[float] = None) -> pd.DataFrame:
        """기존에 모아둔 리포트/테이블을 재귀 스캔해 '등록만' 한다. 이동·개명·삭제 없음.

        ★ 구글드라이브 FUSE 에서 os.walk 는 디렉터리 하나당 왕복이 발생해 매우 느리다.
          그래서 ① 시간 예산 ② 진행 표시 ③ 볼트 자신의 blob/table/index 제외
          ④ scandir 의 DirEntry 로 stat 왕복 1회로 축소 를 전부 건다. 예산을 넘기면
          '멈춘 것처럼' 보이지 않게 남은 경로를 보고하고 중단한다 — 흡수는 부가 기능이지
          백테스트의 전제가 아니다.
        """
        max_files = int(max_files if max_files is not None
                        else globals().get("ADOPT_SCAN_MAX_FILES", 60_000))
        budget_s = float(budget_s if budget_s is not None
                         else globals().get("ADOPT_SCAN_BUDGET_S", 180.0))
        if not globals().get("ADOPT_SCAN_ENABLED", True):
            LOG.info("기존 캐시 흡수 스캔이 꺼져 있습니다(ADOPT_SCAN_ENABLED=False).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])

        # 볼트 자신의 내부 디렉터리는 스캔 대상이 아니다(자기 blob/table 을 다시 등록하게 된다)
        self_dirs = set()
        for sc in ("shared", "private"):
            try:
                self_dirs |= {os.path.realpath(self.blob_dir(sc)),
                              os.path.realpath(self.table_dir(sc)),
                              os.path.realpath(os.path.join(self.ns[sc], "index"))}
            except Exception:
                pass
        SKIP_DIR = {"_backup", "index", "blob", "table", "__pycache__", ".git",
                    ".ipynb_checkpoints", ".shortcut-targets-by-id", ".Trash", ".tmp"}
        KEY = ("report", "consensus", "research", "analyst", "hankyung", "naver",
               "dart", "krx", "nps", "price", "ohlcv", "universe", "fnltt")

        t0 = time.time()
        seen, found, stopped = set(), [], []
        n_all = 0
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            rd = os.path.realpath(d)
            if rd in seen:
                continue
            seen.add(rd)
            if time.time() - t0 > budget_s or n_all >= max_files:
                stopped.append(d)
                continue
            LOG.info(f"기존 캐시 스캔: {d}")
            n, t_dir, last = 0, time.time(), time.time()
            stack = [rd]
            hit_limit = False
            while stack:
                cur = stack.pop()
                if os.path.realpath(cur) in self_dirs:
                    continue
                try:
                    it = list(os.scandir(cur))
                except Exception:
                    continue
                for e in it:
                    if time.time() - t0 > budget_s or n_all >= max_files:
                        hit_limit = True
                        break
                    try:
                        if e.is_dir(follow_symlinks=False):
                            nm = e.name
                            if nm.startswith(".") or nm in SKIP_DIR:
                                continue
                            if os.path.realpath(e.path) in self_dirs:
                                continue
                            stack.append(e.path)
                            continue
                        low = e.name.lower()
                        if low.endswith(".pdf"):
                            kind = "report_pdf"
                        elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                                any(t in low for t in KEY):
                            kind = "table_like"
                        else:
                            continue
                        try:
                            sz = e.stat(follow_symlinks=False).st_size
                        except Exception:
                            sz = -1
                        found.append({"abs_path": e.path, "kind": kind, "name": e.name,
                                      "dir": cur, "bytes": sz})
                        n += 1; n_all += 1
                    except Exception:
                        continue
                    if time.time() - last > 20.0:
                        last = time.time()
                        LOG.info(f"  … 스캔 중 {n:,}건 ({time.time()-t_dir:.0f}s 경과, "
                                 f"예산 {budget_s:.0f}s)")
                if hit_limit:
                    break
            LOG.info(f"  → {n:,}개 후보 발견 ({time.time()-t_dir:.0f}s)")
            if hit_limit:
                stopped.append(d)
                break
        if stopped:
            LOG.warn(f"흡수 스캔을 예산({budget_s:.0f}s / {max_files:,}건)에서 중단했습니다. "
                     f"미완 경로: {', '.join(stopped[:4])}. 드라이브 FUSE 는 디렉터리마다 왕복이 "
                     f"생겨 느립니다 — 흡수는 부가 기능이므로 백테스트는 그대로 진행합니다. "
                     f"전부 흡수하려면 ADOPT_SCAN_BUDGET_S 를 늘리거나 CACHE_SEARCH_DIRS 를 "
                     f"실제 리포트 폴더로 좁히세요.")
        if not found:
            LOG.info("기존 캐시에서 흡수할 파일을 찾지 못했습니다(정상일 수 있습니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        n_new = 0
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            before = self.stats.get("adopted", 0)
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared",
                       extra={"dir": r.dir}, size=int(r.bytes))
            n_new += int(self.stats.get("adopted", 0) > before)
        self.flush("shared")
        LOG.ok(f"기존 캐시 {len(df):,}건 확인 · 신규 참조 등록 {n_new:,}건 "
               f"(파일은 원위치 그대로, 이동·삭제 없음) · {time.time()-t0:.0f}s")
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
