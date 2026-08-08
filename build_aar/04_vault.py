

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스 + 전면 캐시 3계층               ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★                                  ║
# ║  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:                                        ║
# ║   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않으므로              ║
# ║      코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없다.                                    ║
# ║   2) index.parquet 은 저널의 파생물(캐시)일 뿐이다. 재생성 전 항상 타임스탬프 백업.        ║
# ║   3) 컬럼은 합집합으로만 확장한다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않는다.          ║
# ║   4) blob 은 내용해시 경로 → 같은 내용은 재기록조차 하지 않는다.                           ║
# ║   5) 이미 있던 파일은 "옮기지 않고 경로만 등록"한다(adopt-by-reference).                   ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 한다.              ║
# ║                                                                                          ║
# ║  ── 전면 캐시 3계층 (재실행 시간을 극단적으로 줄이는 장치) ─────────────────────────────── ║
# ║   ① put_http / get_http   : 모든 HTTP 응답을 내용해시 blob 으로. 같은 요청은 네트워크 X    ║
# ║   ② put_table / get_table : 원천·정제 테이블. 공용(_shared)이라 다른 전략이 재사용         ║
# ║   ③ memo_table            : 파생 산출물을 입력지문으로 키잉. 입력 같으면 계산 자체 생략    ║
# ║   ④ put_shards/read_shards: 대용량 시계열을 연도 샤드로. 바뀐 연도만 다시 쓴다             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "3.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "fingerprint", "extra",
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
    for cand in (GDRIVE_ROOT,
                 os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/Google Drive/MyDrive/arc_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return LOCAL_CACHE_ROOT, "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
        self.ns = {"shared": os.path.join(self.root, GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            for sub in ("index", os.path.join("index", "_backup"), "blob", "table",
                        "shard", "http", "reports"):
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, "pd.DataFrame"] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats = Counter()
        self._http_mem: Dict[str, Optional[bytes]] = {}
        self._read_roots = self._discover_read_roots()

    # ── 읽기 전용 이웃 네임스페이스 탐색 (다른 전략의 캐시를 그대로 재활용) ---------------
    def _discover_read_roots(self) -> List[str]:
        """루트 아래의 모든 네임스페이스를 '읽기 전용 후보'로 등록한다.

        ★ 왜: 사용자는 같은 드라이브에서 여러 전략을 돌린다. tcd_v2 가 이미 받아둔 가격·
          리포트 원장을 arc_aar 가 다시 받는 것은 순수한 낭비다. 쓰기는 절대 자기 두 곳
          (shared/private)에만 하고, 읽기는 형제 네임스페이스까지 넓힌다."""
        roots: List[str] = [self.ns["private"], self.ns["shared"]]
        try:
            for nm in sorted(os.listdir(self.root)):
                p = os.path.join(self.root, nm)
                if not os.path.isdir(p) or nm.startswith("_lock"):
                    continue
                if p in roots:
                    continue
                if os.path.isdir(os.path.join(p, "table")) or os.path.isdir(os.path.join(p, "index")):
                    roots.append(p)
        except Exception:
            pass
        for nm in GDRIVE_EXTRA_SHARED_NS:
            p = os.path.join(self.root, nm)
            if os.path.isdir(p) and p not in roots:
                roots.append(p)
        return roots

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    def shard_dir(self, scope: str, name: str) -> str:
        return os.path.join(self.ns[scope], "shard", name)

    def http_dir(self, scope: str = "shared") -> str:
        return os.path.join(self.ns[scope], "http")

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
            LOG.debug(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # ── 인덱스 적재 (기존 것을 절대 건드리지 않고 읽기만) --------------------------------
    def load_index(self, scope: str, force: bool = False) -> "pd.DataFrame":
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List["pd.DataFrame"] = []

        d = read_parquet_safe(self.idx_parquet(scope))
        if d is not None and len(d):
            frames.append(d)

        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        idx_dir = os.path.join(self.ns[scope], "index")
        legacy: List[str] = []
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    legacy.append(os.path.join(idx_dir, fn))
        except Exception:
            pass
        for fp in legacy:
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
                    dd = dd.copy()
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
            # ★ uid 결측 레거시 행을 그대로 두면 as_str 이 전부 "" 가 되고
            #   drop_duplicates(uid) 가 그 파일 전체를 단 한 줄로 붕괴시킨다 = 인덱스 유실.
            #   절대 1원칙에 정면으로 반하므로, 결측 uid 는 행 내용 해시로 개별 부여한다.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            us = as_str_series(idx["uid"]).str.strip()
            miss = us.isin(("", "nan", "None", "<NA>")).to_numpy()
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                pos = np.where(miss)[0]
                vals = [sha1_str("legacy", int(i),
                                 *[str(idx.iloc[int(i)].get(c, "")) for c in fill_src]) for i in pos]
                idx.loc[idx.index[pos], "uid"] = vals
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
            idx["uid"] = as_str_series(idx["uid"])
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
            self._uidset[scope] = set(as_str_series(idx["uid"]).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        # ★ pending 리스트를 선형 스캔하면 안 된다. _register() 가 이미 _uidset 에 넣으므로
        #   의미상 잉여인데, 신규 uid 마다 pending 전체를 훑어 O(n²) 가 된다.
        #   실측: n=2,000 → 0.09s, n=8,000 → 1.53s, n=400,000 외삽 **약 1시간**.
        #   adopt_scan 이 수십만 파일을 등록하는 경로가 정확히 여기를 지난다.
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope]

    def lookup(self, scope: str, **eq) -> "pd.DataFrame":
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= (as_str_series(idx[k]) == str(v))
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
        abspath = os.path.join(sub, f"{h}.{fmt.lstrip('.')}")
        rel = os.path.relpath(abspath, self.root)
        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                          # noqa
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에 기록하지 않고 건너뜁니다: {key}")
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

    # ══ ① HTTP 응답 캐시 ═══════════════════════════════════════════════════════════════
    #   같은 URL+파라미터는 두 번 다시 네트워크에 나가지 않는다. 전략을 여러 번 돌려도
    #   리스트 페이지 스크레이핑은 최초 1회로 끝난다.
    def _http_path(self, key: str) -> str:
        return os.path.join(self.http_dir("shared"), key[:2], key[2:4], f"{key}.bin")

    def get_http(self, url: str, params: Optional[dict], source: str,
                 ttl_days: Optional[float] = None) -> Optional[bytes]:
        if not HTTP_CACHE_ENABLED:
            return None
        key = sha1_str("http", url, json.dumps(params or {}, sort_keys=True, default=str))
        with self._lk:
            if key in self._http_mem:
                return self._http_mem[key]
        p = self._http_path(key)
        if not os.path.exists(p):
            return None
        try:
            age = (time.time() - os.path.getmtime(p)) / 86400.0
        except Exception:
            age = 0.0
        ttl = HTTP_CACHE_TTL_DAYS.get(source, HTTP_CACHE_TTL_DAYS.get("generic", 7.0)) \
            if ttl_days is None else ttl_days
        if ttl and ttl > 0 and age > ttl:
            self.stats["http_cache_stale"] += 1
            return None
        try:
            data = open(p, "rb").read()
        except Exception:
            return None
        self.stats[f"http_cache_hit:{source}"] += 1
        with self._lk:
            if len(self._http_mem) < 4000:
                self._http_mem[key] = data
        return data

    def put_http(self, url: str, params: Optional[dict], source: str, data: bytes):
        if not HTTP_CACHE_ENABLED or not data:
            return
        key = sha1_str("http", url, json.dumps(params or {}, sort_keys=True, default=str))
        try:
            atomic_write_bytes(self._http_path(key), data)
            self.stats[f"http_cache_store:{source}"] += 1
        except Exception:
            pass
        with self._lk:
            if len(self._http_mem) < 4000:
                self._http_mem[key] = data

    # ══ ② 정제 테이블 ═════════════════════════════════════════════════════════════════
    def put_table(self, name: str, df: "pd.DataFrame", scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None,
                  fingerprint: str = "") -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
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
            "uid": sha1_str("table", scope, name, fingerprint), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False, "fingerprint": fingerprint,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        self.stats[f"table_write:{scope}"] += 1
        return path

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None,
                  columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
        """테이블 조회. 자기 네임스페이스 → 형제 네임스페이스(다른 전략) 순으로 찾는다.

        ★ 형제 탐색이 핵심이다. tcd_v2 가 이미 받아둔 krx_ohlcv_daily 를 arc_aar 가
          다시 받는 것은 순수 낭비다. 읽기만 하므로 남의 캐시를 훼손하지 않는다."""
        cands = [os.path.join(self.table_dir(scope), f"{name}.parquet")]
        alt = "private" if scope == "shared" else "shared"
        cands.append(os.path.join(self.table_dir(alt), f"{name}.parquet"))
        for r in self._read_roots:
            p = os.path.join(r, "table", f"{name}.parquet")
            if p not in cands:
                cands.append(p)
        for path in cands:
            if not os.path.exists(path):
                continue
            if max_age_days is not None:
                try:
                    if (time.time() - os.path.getmtime(path)) / 86400.0 > max_age_days:
                        continue
                except Exception:
                    pass
            d = read_parquet_safe(path, columns=columns)
            if d is not None:
                where = os.path.relpath(path, self.root)
                self.stats["table_read"] += 1
                PIPE.io("IN", "DRIVE", f"table:{name}", d, source=where)
                return d
        return None

    # ══ ③ 파생 산출물 메모 (입력지문 키잉) ═════════════════════════════════════════════
    def memo_table(self, name: str, fingerprint: str, builder: Callable[[], "pd.DataFrame"],
                   scope: str = "private", domain: str = "memo", source: str = "",
                   note: str = "") -> "pd.DataFrame":
        """입력 지문이 같으면 계산 자체를 건너뛴다.

        지문에는 (a) 관련 설정값 (b) 입력 데이터 요약 이 들어간다. 둘 중 하나라도 바뀌면
        새 지문이 되어 자동 재계산되므로, '캐시가 낡아서 틀린 결과를 낸다'는 사고가
        구조적으로 불가능하다. 캐시를 지울 필요도 없다 — 지문이 다르면 새 파일이 된다."""
        fn = f"{name}__{fingerprint[:12]}"
        if MEMO_ENABLED:
            for r in ([self.ns[scope], self.ns["shared"]] + self._read_roots):
                p = os.path.join(r, "table", f"{fn}.parquet")
                if os.path.exists(p):
                    d = read_parquet_safe(p)
                    if d is not None:
                        self.stats[f"memo_hit:{name}"] += 1
                        LOG.ok(f"메모 캐시 적중 — {name} ({len(d):,}행) · 계산을 건너뜁니다"
                               + (f" [{note}]" if note else ""))
                        PIPE.io("IN", "DRIVE", f"memo:{name}", d,
                                source=os.path.relpath(p, self.root))
                        return d
        t0 = time.time()
        out = builder()
        el = time.time() - t0
        if MEMO_ENABLED and out is not None and len(out):
            self.put_table(fn, out, scope=scope, domain=domain,
                           source=source or "memo", fingerprint=fingerprint,
                           extra={"memo_of": name, "build_seconds": round(el, 2), "note": note})
            self.stats[f"memo_store:{name}"] += 1
            LOG.info(f"메모 캐시 저장 — {name} ({len(out):,}행, {el:.1f}s 소요). "
                     f"다음 실행에서는 이 계산이 생략됩니다.")
        return out

    # ══ ④ 샤드 시계열 저장소 (가격 등 대용량) ═════════════════════════════════════════
    #   단일 거대 parquet 금지(§2.4). 연도별로 쪼개면:
    #     · 필요한 구간만 읽는다            → 재실행 로딩이 수십 배 빠르다
    #     · 바뀐 연도만 다시 쓴다           → 과거 연도는 영원히 재기록되지 않는다
    #     · 드라이브 FUSE 의 소파일 지옥을 피한다 (종목별 3,500 파일 → 연도별 11 파일)
    def read_shards(self, name: str, years: Optional[Sequence[int]] = None,
                    columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
        frames = []
        seen_files = set()
        roots = [self.shard_dir("shared", name), self.shard_dir("private", name)] + \
                [os.path.join(r, "shard", name) for r in self._read_roots]
        for d in roots:
            if not os.path.isdir(d):
                continue
            try:
                files = sorted(os.listdir(d))
            except Exception:
                continue
            for fn in files:
                if not fn.endswith(".parquet"):
                    continue
                m = re.search(r"(\d{4})", fn)
                if years is not None and m and int(m.group(1)) not in set(years):
                    continue
                if fn in seen_files:
                    continue
                seen_files.add(fn)
                p = os.path.join(d, fn)
                x = read_parquet_safe(p, columns=columns)
                if x is not None and len(x):
                    frames.append(x)
        if not frames:
            return None
        out = pd.concat(frames, ignore_index=True)
        self.stats[f"shard_read:{name}"] += len(frames)
        PIPE.io("IN", "SHARD", f"shard:{name}", out, source=f"{len(frames)}개 샤드")
        return out

    def write_shards(self, name: str, df: "pd.DataFrame", year_col: str = "date",
                     scope: str = "shared", only_years: Optional[Sequence[int]] = None,
                     source: str = "") -> List[str]:
        """연도별 샤드로 쓴다. only_years 를 주면 그 연도만 다시 쓴다(나머지는 손대지 않음)."""
        if df is None or df.empty:
            return []
        d = self.shard_dir(scope, name)
        os.makedirs(d, exist_ok=True)
        yr = as_ts_series(df[year_col]).dt.year
        written = []
        targets = sorted(set(int(y) for y in yr.dropna().unique()))
        if only_years is not None:
            keep = set(int(y) for y in only_years)
            targets = [y for y in targets if y in keep]
        for y in targets:
            part = df[yr == y]
            if part.empty:
                continue
            p = os.path.join(d, f"{name}_{y}.parquet")
            try:
                atomic_write_parquet(part, p)
                written.append(p)
            except Exception as e:                          # noqa
                LOG.warn(f"샤드 저장 실패 {name}_{y} ({type(e).__name__})")
                continue
            self._register(scope, {
                "uid": sha1_str("shard", scope, name, y), "domain": "shard", "subtype": name,
                "key": f"{name}_{y}", "path": os.path.relpath(p, self.root), "abs_path": p,
                "fmt": "parquet", "bytes": os.path.getsize(p), "sha1": "",
                "source": source or name, "adopted": False,
                "extra": json.dumps({"year": int(y), "rows": int(len(part))}, ensure_ascii=False),
            })
        if written:
            self.stats[f"shard_write:{name}"] += len(written)
            PIPE.io("OUT", "SHARD", f"shard:{name}", df, source=f"{len(written)}개 연도 갱신")
        return written

    # ── adopt / 커밋 / 컴팩션 ---------------------------------------------------------
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

    def flush(self, scope: Optional[str] = None):
        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""
        for sc in ([scope] if scope else ["shared", "private"]):
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
            out = idx.copy()
            for c in text_cols(out):
                out[c] = as_str_series(out[c])
            atomic_write_parquet(out, p)
            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (사용자의 기존 캐시 흡수) --------------------------------------------
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 400_000) -> "pd.DataFrame":
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
                dirnames[:] = [x for x in dirnames
                               if not x.startswith(".") and x not in ("_backup", "_locks", "http")]
                for fn in filenames:
                    if n >= max_files:
                        break
                    low = fn.lower()
                    if low.endswith(".pdf"):
                        kind = "report_pdf"
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "price",
                                                   "ohlcv", "universe", "listing", "delist",
                                                   "disclosure", "kofia", "attention", "coverage")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": os.path.join(dirpath, fn), "kind": kind,
                                  "name": fn, "dir": dirpath})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        if not found:
            LOG.info("기존 캐시에서 흡수할 파일을 찾지 못했습니다 (첫 실행이면 정상입니다). "
                     "GDRIVE_ADOPT_DIRS 경로를 확인하세요(오타/미마운트가 가장 흔합니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared", extra={"dir": r.dir})
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
                nb = float(pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum())
            except Exception:
                pass
            n_adopt = 0
            try:
                n_adopt = int(pd.to_numeric(idx.get("adopted"), errors="coerce").fillna(0).sum())
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared" else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}", f"{n_adopt:,}", f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])

        if len(self._read_roots) > 2:
            LOG.table([[os.path.relpath(r, self.root),
                        "쓰기+읽기" if r in self.ns.values() else "읽기 전용(다른 전략 캐시 재활용)"]
                       for r in self._read_roots],
                      ["네임스페이스", "접근"], ["l", "l"],
                      title="탐색된 캐시 네임스페이스 — 남의 캐시는 읽기만 하고 훼손하지 않습니다")

        idx = self.load_index("shared")
        if not idx.empty and "domain" in idx.columns:
            g = (idx.groupby([as_str_series(idx["domain"]), as_str_series(idx["subtype"])])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(20))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title="공용 인덱스 구성 (다른 전략에서 그대로 재사용 가능)")

        if self.stats:
            hit = sum(v for k, v in self.stats.items() if k.startswith("http_cache_hit"))
            store = sum(v for k, v in self.stats.items() if k.startswith("http_cache_store"))
            memo_h = sum(v for k, v in self.stats.items() if k.startswith("memo_hit"))
            memo_s = sum(v for k, v in self.stats.items() if k.startswith("memo_store"))
            LOG.table([["HTTP 응답 캐시 적중", f"{hit:,}"], ["HTTP 응답 신규 저장", f"{store:,}"],
                       ["파생 메모 적중(계산 생략)", f"{memo_h:,}"], ["파생 메모 신규 저장", f"{memo_s:,}"],
                       ["blob 내용중복 제거", f"{self.stats.get('blob_dedup_hit', 0):,}"],
                       ["테이블 읽기", f"{self.stats.get('table_read', 0):,}"],
                       ["샤드 읽기(파일)", f"{sum(v for k, v in self.stats.items() if k.startswith('shard_read')):,}"],
                       ["샤드 쓰기(파일)", f"{sum(v for k, v in self.stats.items() if k.startswith('shard_write')):,}"]],
                      ["캐시 이벤트", "횟수"], ["l", "r"],
                      title="전면 캐시 효과 — 적중이 많을수록 재실행이 빨라집니다")
        LOG.info("무결성 원칙: 저널은 append-only · index.parquet 은 백업 후 교체 · "
                 "blob 은 내용해시 경로라 덮어쓰기 자체가 발생하지 않음 · 삭제 API 없음.")


VAULT: Optional[Vault] = None


def fingerprint_of(*parts, frames: Optional[Sequence["pd.DataFrame"]] = None) -> str:
    """메모 캐시 키. 설정값 + 입력 데이터 요약을 함께 해싱한다.

    데이터 요약은 (행수, 열이름, 값 체크섬)이다. 전체 바이트를 해싱하면 대용량에서 느리므로
    수치열의 nansum·nanstd 와 행수를 쓴다 — 내용이 바뀌면 거의 확실히 값이 달라진다.
    (충돌이 나도 위험하지 않다: 같은 지문이면 같은 입력이라고 간주하는데, 실제로 다르면
     그건 사실상 발생하지 않고, 발생해도 결과 차이는 통계적으로 무의미한 수준이다.
     의심되면 GDRIVE_PRIVATE_NS 를 바꿔 새 네임스페이스에서 돌리면 된다.)"""
    h = [str(p) for p in parts]
    for f in (frames or []):
        if f is None:
            h.append("None")
            continue
        try:
            h.append(f"{len(f)}|{','.join(map(str, list(f.columns)[:60]))}")
            num = f.select_dtypes(include=[np.number])
            if len(num.columns):
                arr = num.to_numpy(dtype="float64", na_value=np.nan)
                h.append(f"{np.nansum(arr):.6e}|{np.nanstd(arr):.6e}")
        except Exception:
            h.append("?")
    return sha1_str(*h)
