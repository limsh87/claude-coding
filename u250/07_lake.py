import gzip
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  ★ CacheLake — 캐시 최우선 데이터 계층                                                    ║
# ║                                                                                          ║
# ║  전제: "거의 다 수집되어 있다." 그러므로 이 계층의 임무는 수집이 아니라 발굴이다.           ║
# ║                                                                                          ║
# ║    ① 구글드라이브 공용 인덱스(_shared)  — 다른 전략이 모아둔 원본/정제본                   ║
# ║    ② 로컬 D: 드라이브 재귀 스캔          — 이전 프로젝트가 남긴 parquet/csv/sqlite         ║
# ║    ③ 깃허브 raw 캐시                     — FDR 상장/폐지 목록 등                          ║
# ║                                                                                          ║
# ║  스키마를 모르는 캐시를 어떻게 쓰는가 — 컬럼 지문(signature)으로 역할을 추정한다.           ║
# ║  프로젝트마다 컬럼명이 다르다(code/종목코드/Symbol/ticker …). 별칭표로 정규화하고,          ║
# ║  점수가 임계 이상인 파일만 채택한다. 애매하면 채택하지 않고 목록에만 남긴다 —              ║
# ║  잘못 채택한 캐시는 없는 캐시보다 나쁘다.                                                  ║
# ║                                                                                          ║
# ║  ★ 절대 원칙: 스캔은 읽기 전용이다. 옮기지도, 지우지도, 덮어쓰지도 않는다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DATA_EXT = (".parquet", ".pq", ".csv", ".csv.gz", ".tsv", ".feather", ".ftr",
            ".pkl", ".pickle", ".jsonl", ".json", ".db", ".sqlite", ".sqlite3", ".h5")

# 스캔에서 건너뛸 디렉터리 (시간 낭비 + 데이터가 있을 리 없는 곳)
SKIP_DIRS = {".git", ".ipynb_checkpoints", "__pycache__", "node_modules", ".venv", "venv",
             "site-packages", ".cache", "AppData", "Windows", "Program Files",
             "Program Files (x86)", "$RECYCLE.BIN", "System Volume Information",
             ".vscode", ".idea", "_backup", "blob"}

# ── 컬럼 별칭표 ─────────────────────────────────────────────────────────────────────────────
#   같은 뜻인데 프로젝트마다 다르게 쓴 이름들. 소문자·공백제거 후 비교한다.
ALIAS = {
    "code":        ["code", "종목코드", "단축코드", "symbol", "ticker", "stock_code", "isu_srt_cd",
                    "shortcode", "srtncd", "종목", "isu_cd", "stockcode", "scode"],
    "name":        ["name", "종목명", "회사명", "기업명", "corp_name", "isu_nm", "itemname",
                    "한글종목명", "stock_name", "korean name", "종목이름"],
    "date":        ["date", "일자", "기준일", "기준일자", "trd_dd", "dt", "basdt", "ymd",
                    "거래일", "date_", "std_dt", "base_date"],
    "open":        ["open", "시가", "opnprc", "tdd_opnprc"],
    "high":        ["high", "고가", "hgprc", "tdd_hgprc"],
    "low":         ["low", "저가", "lwprc", "tdd_lwprc"],
    "close":       ["close", "종가", "clsprc", "tdd_clsprc", "adj close", "adjclose", "price",
                    "수정종가", "종가_수정"],
    "volume":      ["volume", "거래량", "acc_trdvol", "trdvol", "vol"],
    "amount":      ["amount", "거래대금", "acc_trdval", "trdval", "value", "거래금액", "tradingvalue"],
    "market_cap":  ["market_cap", "시가총액", "mktcap", "marketcap", "mkt_cap", "cap", "시총",
                    "mktcap_krw", "market_capitalization"],
    "shares":      ["shares", "상장주식수", "listed_shares", "list_shrs", "발행주식수", "shrs"],
    "market":      ["market", "시장", "시장구분", "mkt", "mktid", "market_name", "mkt_tp_nm"],
    "listing_date":   ["listing_date", "상장일", "listingdate", "list_dt", "상장일자", "listed_date"],
    "delisting_date": ["delisting_date", "폐지일", "상장폐지일", "delistingdate", "delist_dt",
                       "상장폐지일자", "delisted_date"],
    "corp_code":   ["corp_code", "고유번호", "corpcode", "dart_code", "corp_cd"],
    "rcept_no":    ["rcept_no", "접수번호", "receptno", "rcp_no", "rceptno"],
    "rcept_dt":    ["rcept_dt", "접수일자", "공시일", "공시일자", "receptdt", "rcp_dt", "rceptdt"],
    "report_nm":   ["report_nm", "보고서명", "공시제목", "title", "reportnm", "rpt_nm", "제목"],
    "bsns_year":   ["bsns_year", "사업연도", "year", "회계연도", "fy"],
    "account_nm":  ["account_nm", "계정명", "계정과목", "accountnm", "account_name"],
    "amount_fs":   ["thstrm_amount", "당기금액", "당기", "amount_fs", "value_fs"],
    "revenue":     ["revenue", "매출액", "sales", "영업수익", "매출"],
    "equity":      ["equity", "자본총계", "total_equity", "자기자본", "자본"],
    "capital":     ["capital", "자본금", "paid_in_capital", "납입자본금"],
    "industry":    ["industry", "업종", "섹터", "sector", "업종명", "industry_name", "gics", "wics"],
    "reason":      ["reason", "취득처분사유", "사유", "변동사유", "취득방법", "reason_nm"],
    "insider_nm":  ["insider_nm", "보고자", "성명", "repror", "보고자명", "reporter"],
    "contract_amt": ["contract_amt", "계약금액", "contract_amount", "계약총액"],
    "ratio_sales": ["ratio_sales", "매출액대비", "매출액대비비율", "sales_ratio", "비율"],
}
_ALIAS_REV = {a.replace(" ", "").replace("_", "").lower(): k
              for k, v in ALIAS.items() for a in v}


def canon_col(c: Any) -> Optional[str]:
    return _ALIAS_REV.get(str(c).strip().replace(" ", "").replace("_", "").lower())


# ── 역할 지문 ───────────────────────────────────────────────────────────────────────────────
#   need : 전부 있어야 채택   nice : 있으면 가점   role 별 최소 점수로 오채택을 막는다
ROLE_SIG = {
    "price_daily":     dict(need=["code", "date", "close"],
                            nice=["amount", "volume", "open", "high", "low", "market_cap"], min_score=4),
    "mktcap_daily":    dict(need=["code", "date", "market_cap"], nice=["shares", "amount"], min_score=3),
    "sec_master":      dict(need=["code", "name"],
                            nice=["listing_date", "delisting_date", "market", "industry", "corp_code"],
                            min_score=3),
    "corp_map":        dict(need=["corp_code", "code"], nice=["name"], min_score=2),
    "dart_disclosure": dict(need=["rcept_no", "report_nm"], nice=["corp_code", "rcept_dt", "code"],
                            min_score=3),
    "dart_fin":        dict(need=["corp_code", "bsns_year", "account_nm"],
                            nice=["amount_fs", "rcept_no"], min_score=4),
    "dart_insider":    dict(need=["rcept_no", "reason"], nice=["code", "corp_code", "insider_nm"],
                            min_score=3),
    "dart_contract":   dict(need=["rcept_no", "contract_amt"], nice=["ratio_sales", "code", "corp_code"],
                            min_score=3),
    "financials":      dict(need=["code", "revenue"], nice=["equity", "capital", "date", "bsns_year"],
                            min_score=3),
}
# 파일명 힌트 — 컬럼 지문과 독립적인 2차 증거. 단독으로는 채택하지 않는다.
NAME_HINT = {
    "price_daily": ("ohlcv", "price", "시세", "주가", "daily"),
    "mktcap_daily": ("mktcap", "시가총액", "cap", "marketcap"),
    "sec_master": ("master", "listing", "종목", "krx_stock", "sec_master", "universe"),
    "corp_map": ("corpcode", "corp_code", "corpmap"),
    "dart_disclosure": ("disclosure", "공시", "list", "dart_list", "rcept"),
    "dart_fin": ("fnltt", "financial", "재무", "dart_fin"),
    "dart_insider": ("insider", "지분", "임원", "주요주주", "소유상황"),
    "dart_contract": ("contract", "공급계약", "수주", "단일판매"),
    "financials": ("fin", "재무", "financ"),
}


@dataclass
class LakeItem:
    path: str
    role: str
    score: float
    rows: int
    cols: List[str]
    fmt: str
    origin: str          # drive | local | github | vault
    sub: str = ""        # sqlite 테이블명 등
    mtime: float = 0.0


def _sniff_parquet(path: str) -> Optional[Tuple[List[str], int]]:
    """★ 데이터를 읽지 않는다. 푸터 메타데이터만 본다 — 수 GB 파일도 수 ms."""
    try:
        import pyarrow.parquet as pq
        f = pq.ParquetFile(path)
        return [str(c) for c in f.schema_arrow.names], int(f.metadata.num_rows)
    except Exception:
        try:
            d = pd.read_parquet(path)
            return [str(c) for c in d.columns], len(d)
        except Exception:
            return None


def _sniff_csv(path: str) -> Optional[Tuple[List[str], int]]:
    try:
        opener = gzip.open if path.endswith(".gz") else open
        sep = "\t" if path.endswith((".tsv", ".tsv.gz")) else ","
        with opener(path, "rt", encoding="utf-8-sig", errors="replace") as fh:
            head = fh.readline()
        if not head:
            return None
        cols = [c.strip().strip('"') for c in head.rstrip("\r\n").split(sep)]
        if len(cols) < 2:
            return None
        # 행수는 바이트/행길이 추정 (전체를 읽지 않는다)
        try:
            approx = max(1, int(os.path.getsize(path) / max(len(head), 1)) - 1)
        except Exception:
            approx = -1
        return cols, approx
    except Exception:
        return None


def _sniff_sqlite(path: str) -> List[Tuple[str, List[str], int]]:
    out = []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            tabs = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()]
            for t in tabs[:60]:
                try:
                    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
                    if len(cols) >= 2:
                        out.append((t, [str(c) for c in cols], -1))
                except Exception:
                    continue
        finally:
            con.close()
    except Exception:
        pass
    return out


def _score_role(cols: List[str], fname: str) -> Tuple[Optional[str], float]:
    canon = {c for c in (canon_col(x) for x in cols) if c}
    best, best_s = None, 0.0
    low = os.path.basename(fname).lower()
    for role, sig in ROLE_SIG.items():
        if not all(n in canon for n in sig["need"]):
            continue
        s = float(len(sig["need"])) + sum(1.0 for n in sig["nice"] if n in canon)
        if any(h in low for h in NAME_HINT.get(role, ())):
            s += 1.0
        if s >= sig["min_score"] and s > best_s:
            best, best_s = role, s
    return best, best_s


class CacheLake:
    """읽기 전용 캐시 발굴기. 채택한 파일만 실제로 로드한다."""

    def __init__(self):
        self.items: List[LakeItem] = []
        self.scanned = 0
        self.skipped_dirs = 0
        self.roots_used: List[Tuple[str, str]] = []
        self._loaded: Dict[str, pd.DataFrame] = {}
        self.rejected: List[Tuple[str, List[str]]] = []

    # ── 스캔 ────────────────────────────────────────────────────────────────────────────
    def _roots(self) -> List[Tuple[str, str]]:
        seen, out = set(), []
        # ① 볼트(구글드라이브 또는 로컬 폴백)의 table 디렉터리 — 가장 신뢰도가 높다
        for scope in ("shared", "private"):
            try:
                p = VAULT.table_dir(scope)
                if os.path.isdir(p) and p not in seen:
                    seen.add(p); out.append((p, "vault"))
            except Exception:
                pass
        # ② 구글드라이브 채택 폴더
        for p in GDRIVE_ADOPT_DIRS:
            p = os.path.expanduser(str(p))
            if os.path.isdir(p) and p not in seen:
                seen.add(p); out.append((p, "drive"))
        # ③ 로컬 (D: 포함)
        for p in CACHE_SEARCH_DIRS + [CACHE_DIR, BASE_DIR, LOCAL_CACHE_ROOT]:
            p = os.path.expanduser(str(p or ""))
            if p and os.path.isdir(p) and p not in seen:
                seen.add(p); out.append((p, "local"))
        return out

    def scan_local(self):
        roots = self._roots()
        self.roots_used = roots
        if not roots:
            LOG.warn("스캔할 캐시 경로가 하나도 없습니다 — CACHE_SEARCH_DIRS / GDRIVE_ADOPT_DIRS 를 "
                     "확인하세요. (경로가 없어도 실행은 되지만 전부 신규 수집이 됩니다)")
            return
        _names = [(os.path.basename(p.rstrip("/" + os.sep)) or p) + f"[{k}]" for p, k in roots]
        LOG.info(f"캐시 스캔 시작 — 루트 {len(roots)}개: " + ", ".join(_names))
        cands: List[Tuple[str, str]] = []
        for root, kind in roots:
            base_depth = root.rstrip("/" + os.sep).count(os.sep)
            t0, n0, timed_out = time.time(), len(cands), False
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.count(os.sep) - base_depth >= CACHE_SCAN_MAX_DEPTH:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                self.skipped_dirs += 1
                for fn in filenames:
                    if fn.lower().endswith(DATA_EXT) and not fn.startswith("."):
                        cands.append((os.path.join(dirpath, fn), kind))
                if len(cands) >= CACHE_SCAN_MAX_FILES:
                    break
                #   구글드라이브 스트리밍은 디렉터리 하나 여는 데도 수백 ms 가 걸린다.
                #   루트 하나가 느리다고 실행 전체가 멈추면 안 되므로 예산을 둔다.
                if time.time() - t0 > CACHE_SCAN_BUDGET_S:
                    timed_out = True
                    break
            if timed_out:
                LOG.warn(f"캐시 스캔 시간 예산({CACHE_SCAN_BUDGET_S:.0f}s) 초과 — {root} 는 "
                         f"여기까지 찾은 {len(cands)-n0:,}개만 씁니다. 더 정확히 잡으려면 "
                         f"CACHE_SEARCH_DIRS 에 하위 폴더를 직접 지정하세요.")
            if len(cands) >= CACHE_SCAN_MAX_FILES:
                LOG.warn(f"후보 파일 상한({CACHE_SCAN_MAX_FILES:,})에 도달해 스캔을 멈춥니다.")
                break
        # 같은 파일이 여러 루트로 잡히면 한 번만
        uniq: Dict[str, str] = {}
        for p, k in cands:
            rp = os.path.realpath(p)
            if rp not in uniq or k == "vault":
                uniq[rp] = k
        LOG.info(f"데이터 후보 파일 {len(uniq):,}개 발견 — 컬럼 지문으로 역할을 판별합니다 "
                 f"(파일 내용은 읽지 않고 스키마만 봅니다).")

        def _one(item):
            path, kind = item
            out: List[LakeItem] = []
            low = path.lower()
            try:
                mt = os.path.getmtime(path)
                if low.endswith((".db", ".sqlite", ".sqlite3")):
                    for t, cols, n in _sniff_sqlite(path):
                        role, s = _score_role(cols, f"{path}:{t}")
                        if role:
                            out.append(LakeItem(path, role, s, n, cols, "sqlite", kind, t, mt))
                    return out
                if low.endswith((".parquet", ".pq")):
                    sn = _sniff_parquet(path)
                elif low.endswith((".csv", ".csv.gz", ".tsv")):
                    sn = _sniff_csv(path)
                elif low.endswith((".feather", ".ftr")):
                    try:
                        import pyarrow.feather as fe
                        sn = ([str(c) for c in fe.read_table(path, columns=None).schema.names], -1)
                    except Exception:
                        sn = None
                elif low.endswith((".pkl", ".pickle")):
                    if os.path.getsize(path) > 600 * 1024 * 1024:
                        return out                       # 거대 pickle 은 안전하게 건너뛴다
                    try:
                        d = pd.read_pickle(path)
                        sn = ([str(c) for c in d.columns], len(d)) if isinstance(d, pd.DataFrame) else None
                    except Exception:
                        sn = None
                elif low.endswith(".jsonl"):
                    rows = read_jsonl(path)[:1]
                    sn = ([str(c) for c in rows[0].keys()], -1) if rows else None
                else:
                    return out
                if not sn:
                    return out
                cols, n = sn
                role, s = _score_role(cols, path)
                if role:
                    out.append(LakeItem(path, role, s, n, cols, os.path.splitext(low)[1].lstrip("."),
                                        kind, "", mt))
                else:
                    self.rejected.append((path, cols[:12]))
            except Exception:
                pass
            return out

        res = pmap_io(_one, list(uniq.items()), workers=min(N_WORKERS_IO, 12), desc="캐시 지문 판별")
        for lst in res:
            if lst:
                self.items.extend(lst)
        self.scanned = len(uniq)

    # ── 깃허브 ──────────────────────────────────────────────────────────────────────────
    def scan_github(self):
        if COLLECT_POLICY == "NEVER":
            LOG.info("COLLECT_POLICY=NEVER — 깃허브 캐시 조회를 건너뜁니다.")
            return
        for owner_repo, branch, sub in GITHUB_CACHE_REPOS:
            url = f"https://api.github.com/repos/{owner_repo}/git/trees/{branch}?recursive=1"
            hdr = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else None
            js = http_json(url, source="github", headers=hdr, tries=2, timeout=30)
            if not isinstance(js, dict) or "tree" not in js:
                LOG.warn(f"깃허브 캐시 목록 조회 실패: {owner_repo} — 이 소스는 건너뜁니다.")
                continue
            files = [t["path"] for t in js["tree"]
                     if t.get("type") == "blob" and str(t.get("path", "")).startswith(sub)
                     and str(t.get("path", "")).lower().endswith((".csv", ".parquet"))]
            LOG.ok(f"깃허브 {owner_repo}@{branch}/{sub} — 파일 {len(files):,}개 확인 "
                   f"(내려받지 않고 목록만 확보. 필요한 날짜만 그때 받습니다).")
            self._gh_files = getattr(self, "_gh_files", {})
            self._gh_files[owner_repo] = (branch, files)

    def harvest(self):
        with PIPE.stage("L0.LAKE", "캐시 하베스트 (드라이브·로컬D·깃허브)", "L0", budget_s=900):
            self.scan_local()
            self.scan_github()
            self.report()
            self.adopt_into_vault()

    # ── 보고 ────────────────────────────────────────────────────────────────────────────
    def report(self):
        if not self.items:
            LOG.warn("재활용 가능한 캐시를 찾지 못했습니다. 경로 설정을 확인하세요 — "
                     "이대로 진행하면 전부 신규 수집이라 매우 느립니다.")
            if self.rejected:
                LOG.info("판별 실패한 파일 예시 (컬럼이 지문과 맞지 않음):")
                for p, cols in self.rejected[:5]:
                    LOG.info(f"    {os.path.basename(p)} → {cols}")
            return
        agg: Dict[Tuple[str, str], List[int]] = {}
        for it in self.items:
            k = (it.role, it.origin)
            a = agg.setdefault(k, [0, 0])
            a[0] += 1
            a[1] += max(it.rows, 0)
        rows = [[role, origin, f"{n:,}", f"{r:,}" if r else "?"]
                for (role, origin), (n, r) in sorted(agg.items())]
        LOG.table(rows, ["역할", "출처", "파일수", "행수(추정)"], ["l", "l", "r", "r"],
                  title=f"★ 재활용 캐시 목록 — 후보 {self.scanned:,}개 중 {len(self.items):,}개 채택")

    def adopt_into_vault(self):
        """경로만 인덱스에 등록한다. 파일을 옮기거나 고치지 않는다(adopt-by-reference)."""
        n = 0
        for it in self.items:
            if it.origin == "vault":
                continue
            try:
                VAULT.adopt(it.path, domain="lake", subtype=it.role,
                                 key=f"{it.role}:{os.path.basename(it.path)}{(':'+it.sub) if it.sub else ''}",
                                 source=f"lake:{it.origin}", scope="shared")
                n += 1
            except Exception:
                continue
        if n:
            LOG.ok(f"외부 캐시 {n:,}건을 인덱스에 '경로만' 등록했습니다 — "
                   f"파일은 원위치 그대로이며 다음 실행에서도 즉시 재활용됩니다.")
        VAULT.flush()

    # ── 적재 ────────────────────────────────────────────────────────────────────────────
    def _read_item(self, it: LakeItem) -> Optional[pd.DataFrame]:
        try:
            if it.fmt == "sqlite":
                con = sqlite3.connect(f"file:{it.path}?mode=ro", uri=True)
                try:
                    d = pd.read_sql_query(f'SELECT * FROM "{it.sub}"', con)
                finally:
                    con.close()
            elif it.fmt in ("parquet", "pq"):
                d = read_parquet_safe(it.path)
            elif it.fmt in ("csv", "gz", "tsv"):
                d = pd.read_csv(it.path, encoding="utf-8-sig", low_memory=False,
                                sep="\t" if it.path.endswith(".tsv") else ",")
            elif it.fmt in ("feather", "ftr"):
                d = pd.read_feather(it.path)
            elif it.fmt in ("pkl", "pickle"):
                d = pd.read_pickle(it.path)
            elif it.fmt == "jsonl":
                d = pd.DataFrame(read_jsonl(it.path))
            else:
                return None
        except Exception as e:                                          # noqa
            LOG.debug(f"캐시 적재 실패 {os.path.basename(it.path)}: {type(e).__name__}")
            return None
        if d is None or not len(d):
            return None
        ren = {}
        for c in d.columns:
            k = canon_col(c)
            if k and k not in ren.values():
                ren[c] = k
        d = d.rename(columns=ren)
        d = d.loc[:, ~pd.Index(d.columns).duplicated()]
        d["_src"] = os.path.basename(it.path) + (f":{it.sub}" if it.sub else "")
        return d

    def load(self, role: str, required: Sequence[str] = ()) -> Optional[pd.DataFrame]:
        """역할별 최적 캐시를 합쳐서 반환. 큰 것·최신 것 우선, 중복은 뒤에 오는 것을 버린다."""
        if role in self._loaded:
            return self._loaded[role]
        cand = sorted([i for i in self.items if i.role == role],
                      key=lambda x: (-x.score, -max(x.rows, 0), -x.mtime))
        if not cand:
            return None
        frames, used = [], []
        for it in cand[:12]:                       # 상위 12개까지만 — 같은 데이터의 사본이 흔하다
            d = self._read_item(it)
            if d is None:
                continue
            if required and not all(c in d.columns for c in required):
                continue
            frames.append(d)
            used.append(f"{os.path.basename(it.path)}({len(d):,})")
            if sum(len(f) for f in frames) > 40_000_000:
                LOG.warn(f"[{role}] 적재량이 4천만행을 넘어 나머지 사본은 건너뜁니다.")
                break
        if not frames:
            return None
        allc: List[str] = []
        for f in frames:
            for c in f.columns:
                if c not in allc:
                    allc.append(c)
        d = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
        LOG.ok(f"[{role}] 캐시 재활용 {len(d):,}행 ← {', '.join(used[:5])}"
               f"{' 외 %d개' % (len(used)-5) if len(used) > 5 else ''}")
        PIPE.io("IN", "CACHE", f"lake:{role}", d, source=",".join(used[:3]))
        self._loaded[role] = d
        return d

    def has(self, role: str) -> bool:
        return any(i.role == role for i in self.items)


LAKE = CacheLake()
