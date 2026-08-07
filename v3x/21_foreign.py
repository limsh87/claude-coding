# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  FOREIGN — 다른 전략이 만들어 둔 구글드라이브 캐시를 '읽기 전용'으로 흡수한다               ║
# ║                                                                                             ║
# ║  ★★★ 절대 1원칙 ★★★                                                                        ║
# ║    이 모듈에는 **기존 인덱스를 수정하는 코드 경로가 하나도 없다.**                           ║
# ║    - 외부 인덱스 파일은 `open(..., "r")` 로만 연다. 쓰기 모드로 여는 곳이 없다.              ║
# ║    - 삭제/이동/개명 API 를 import 조차 하지 않는다.                                         ║
# ║    - 유일한 쓰기는 `foreign_publish_common()` 하나이며, 그마저도                             ║
# ║        (1) 새 데이터 파일은 **새 이름**으로만 쓰고                                           ║
# ║        (2) 레지스트리는 **새 키만 추가**하며(기존 키 값은 손대지 않음)                       ║
# ║        (3) 쓰기 전 타임스탬프 백업 → 원자적 교체 → 재읽기 검증 → 실패 시 자동 롤백           ║
# ║      을 전부 통과해야 커밋된다. 하나라도 실패하면 사이드카 파일로 물러난다.                  ║
# ║                                                                                             ║
# ║  왜 필요한가: 이 계정의 리포트 원장 본체는 tcd_cache 가 아니라 QuantCache/common/reports 에  ║
# ║  있다(report_ledger 30만행 · analyst_registry · blob_map). 워크스페이스마다 인덱스 형식이   ║
# ║  달라서(매니페스트 / kind|ym / JSONL / 플랫 dict) 어댑터 없이는 재활용이 불가능하다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 외부 인덱스의 '형식'별 어댑터. 실측된 4가지 형식을 전부 다룬다.
#   A) _manifest_*.json   : {dataset: {dataset,scope,keys,path,rows,ext,producer,updated_at,files}}
#   B) public_index.json  : {schema_version, entries:{ "kind|ym": {kind,ym,rows,file,updated_at,contributor} }}
#   C) index.jsonl        : 한 줄당 {uid,domain,subtype,key,path,abs_path,fmt,bytes,...}
#   D) done_index.json    : {"hk:331500": "OK", ...}   ← 상태 원장(재수집 스킵 판단용)
FOREIGN_INDEX_FILES = ("_manifest_common.json", "public_index.json", "index.jsonl",
                       "done_index.json", "private_index.json", "absorb_manifest.json")

# 외부 parquet 의 payload 컬럼명은 워크스페이스마다 다르다. 실행 시점에 발견해서 매핑한다.
# ★ 하드코딩하지 않는 이유: 매니페스트는 '키 컬럼'만 선언하고 payload 컬럼은 선언하지 않는다.
#   컬럼명을 추측해 고정하면 이름이 다른 순간 조용히 빈 프레임이 되고, 그게 가장 위험한 실패다.
FOREIGN_ALIAS: "dict[str, tuple]" = {
    "src_report_id": ("src_id", "src_report_id", "report_id", "nid", "artid", "seq", "id"),
    "source":        ("src", "source", "site", "provider"),
    "pub_date":      ("pub_date", "date", "report_date", "wdate", "published", "reg_date",
                      "regdate", "ymd", "dt", "write_date"),
    "stock_code":    ("stock_code", "code", "ticker", "isu_srt_cd", "shcode", "symbol",
                      "stk_cd", "corp_code6"),
    "stock_name":    ("stock_name", "name", "corp_name", "isu_nm", "종목명"),
    "broker_raw":    ("broker_raw", "broker", "broker_name", "house", "sec_firm", "office",
                      "company", "증권사"),
    "analyst_raw":   ("analyst_raw", "analyst", "analyst_name", "writer", "author", "작성자"),
    "analyst_id":    ("analyst_id", "aid", "analyst_key"),
    "target_price":  ("target_price", "tp", "goal_price", "target", "목표주가"),
    "opinion":       ("opinion", "rating", "investment_opinion", "투자의견"),
    "title":         ("title", "subject", "report_title", "제목"),
    "pdf_url":       ("pdf_url", "url", "file_url", "attach_url", "link"),
    "detail_url":    ("detail_url", "page_url", "view_url"),
}

# 통관/가격/재무 등 다른 도메인도 같은 방식으로 흡수한다.
FOREIGN_ALIAS_MARKET: "dict[str, tuple]" = {
    "code":   ("code", "ticker", "stock_code", "isu_srt_cd", "symbol", "shcode"),
    "date":   ("date", "trd_dd", "trade_date", "dt", "ymd", "basd_dt"),
    "close":  ("close", "clpr", "tdd_clsprc", "adj_close", "price"),
    "volume": ("volume", "acc_trdvol", "trdvol", "vol"),
    "amount": ("amount", "acc_trdval", "trdval", "value", "tr_amount"),
    "shares": ("shares", "listed_shares", "list_shrs", "lstg_stcnt", "shares_out"),
    "mcap":   ("mcap", "market_cap", "mktcap", "mkt_cap"),
}
FOREIGN_ALIAS_CUSTOMS: "dict[str, tuple]" = {
    "hs":       ("hs", "hs_code", "hsCode", "hsSgn", "hscode", "hs10", "hs6"),
    "ym":       ("ym", "year_month", "yyyymm", "period", "month"),
    "country":  ("country", "cnty", "cntyCd", "cntyNm", "nation", "ctry"),
    "exp_wgt":  ("exp_wgt", "expWgt", "export_weight", "wgt", "weight_kg"),
    "exp_usd":  ("exp_usd", "expDlr", "export_usd", "usd", "value_usd", "dlr"),
}


def _foreign_root_variants(root: str) -> "list[str]":
    """Colab 절대경로로 기록된 매니페스트를 JupyterLab 로컬에서도 찾을 수 있게 후보를 만든다.

    매니페스트의 `path` 는 대부분 `/content/drive/MyDrive/...` 로 굳어 있다.
    로컬에서 돌리면 그 경로는 존재하지 않으므로, 마운트 접두사만 바꿔 재시도한다.
    """
    out = [root]
    base = os.path.basename(root.rstrip("/"))
    cands = []
    try:
        cands.append(os.path.join(str(Path.home()), base))
        cands.append(os.path.join(os.getcwd(), base))
    except Exception:                                                   # noqa
        pass
    for pref in ("/content/drive/MyDrive", "/content/drive/Shareddrives",
                 os.environ.get("TCD_DRIVE_PREFIX", "")):
        if pref:
            cands.append(os.path.join(pref, base))
    for c in cands:
        if c and c not in out:
            out.append(c)
    return out


def foreign_remap(path: str, roots: "Sequence[str]") -> Optional[str]:
    """매니페스트에 적힌 절대경로를 실제 존재하는 경로로 되짚는다. 없으면 None."""
    if not path:
        return None
    if os.path.exists(path):
        return path
    norm = str(path).replace("\\", "/")
    # 알려진 마운트 접두사를 벗겨 상대경로를 얻고, 각 루트 후보에 다시 붙여 본다.
    for pref in ("/content/drive/MyDrive/", "/content/drive/Shareddrives/",
                 str(Path.home()).rstrip("/") + "/", "./"):
        if norm.startswith(pref):
            rel = norm[len(pref):]
            break
    else:
        rel = norm.lstrip("/")
    for r in roots:
        for rv in _foreign_root_variants(r):
            base = os.path.basename(rv.rstrip("/"))
            # rel 이 루트 이름으로 시작하면 중복을 제거한다
            rel2 = rel[len(base) + 1:] if rel.startswith(base + "/") else rel
            for cand in (os.path.join(rv, rel2), os.path.join(os.path.dirname(rv), rel)):
                if cand and os.path.exists(cand):
                    return cand
    return None


def _read_json_ro(path: str) -> Optional[Any]:
    """외부 JSON 을 **읽기 전용**으로 연다. 파싱 실패는 경고만 하고 None."""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception as e:                                              # noqa
        LOG.debug(f"외부 인덱스 읽기 실패(무시): {os.path.basename(path)} — {type(e).__name__}")
        return None


class ForeignCatalog:
    """외부 캐시 카탈로그. **읽기 전용.** 쓰기 메서드가 존재하지 않는다."""

    def __init__(self, roots: "Sequence[str]"):
        self.roots: List[str] = []
        for r in roots or []:
            for rv in _foreign_root_variants(r):
                if os.path.isdir(rv) and rv not in self.roots:
                    self.roots.append(rv)
                    break
        self.datasets: Dict[str, dict] = {}      # name -> {path, rows, keys, producer, index, scope}
        self.status: Dict[str, str] = {}         # "hk:12345" -> "OK" (재수집 스킵 판단)
        self.indexes_seen: List[dict] = []
        self.errors: List[str] = []

    # ── 발견 ------------------------------------------------------------------------
    def scan(self, max_depth: int = 4) -> "ForeignCatalog":
        for root in self.roots:
            for idx_path in self._find_indexes(root, max_depth):
                self._absorb_index(idx_path, root)
        LOG.info(f"외부 캐시 스캔: 루트 {len(self.roots)}개 · 인덱스 {len(self.indexes_seen)}개 · "
                 f"데이터셋 {len(self.datasets)}개 · 상태원장 {len(self.status):,}건")
        return self

    def _find_indexes(self, root: str, max_depth: int) -> "List[str]":
        found: List[str] = []
        root = root.rstrip("/")
        base_depth = root.count("/")
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count("/") - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn in FOREIGN_INDEX_FILES or (
                        fn.startswith("_manifest_") and fn.endswith(".json")):
                    found.append(os.path.join(dirpath, fn))
        return found

    def _absorb_index(self, path: str, root: str) -> None:
        name = os.path.basename(path)
        try:
            if name == "index.jsonl":
                self._absorb_jsonl(path, root)
            elif name == "done_index.json":
                self._absorb_status(path)
            elif name == "public_index.json":
                self._absorb_public(path, root)
            elif name.startswith("_manifest_") or name == "absorb_manifest.json":
                self._absorb_manifest(path, root)
            elif name == "private_index.json":
                self._absorb_journal(path)
            self.indexes_seen.append({"path": path, "kind": name, "root": root})
        except Exception as e:                                          # noqa
            self.errors.append(f"{name}: {type(e).__name__}: {e}")

    def _absorb_manifest(self, path: str, root: str) -> None:
        obj = _read_json_ro(path)
        if not isinstance(obj, dict):
            return
        for key, rec in obj.items():
            if not isinstance(rec, dict):
                continue
            p = rec.get("path") or (rec.get("files") or [None])[0]
            real = foreign_remap(str(p or ""), [root] + self.roots)
            if not real:
                continue
            self.datasets[str(rec.get("dataset") or key)] = {
                "path": real, "rows": int(rec.get("rows") or 0),
                "keys": list(rec.get("keys") or []), "producer": str(rec.get("producer") or ""),
                "updated_at": str(rec.get("updated_at") or ""),
                "scope": str(rec.get("scope") or ""), "index": path,
            }

    def _absorb_public(self, path: str, root: str) -> None:
        obj = _read_json_ro(path)
        if not isinstance(obj, dict):
            return
        entries = obj.get("entries")
        if not isinstance(entries, dict):
            return
        base = os.path.dirname(path)
        # kind 별로 월 파일을 묶어 하나의 논리 데이터셋으로 등록한다.
        buckets: Dict[str, List[dict]] = {}
        for key, rec in entries.items():
            if not isinstance(rec, dict):
                continue
            f = rec.get("file")
            if not f:
                continue
            real = foreign_remap(os.path.join(base, str(f)), [root] + self.roots) \
                or foreign_remap(str(f), [root] + self.roots)
            if not real:
                continue
            buckets.setdefault(str(rec.get("kind") or "unknown"), []).append(
                {"path": real, "ym": str(rec.get("ym") or ""), "rows": int(rec.get("rows") or 0)})
        for kind, parts in buckets.items():
            parts.sort(key=lambda r: r["ym"])
            self.datasets[f"arc_{kind}"] = {
                "path": parts[0]["path"], "parts": [p["path"] for p in parts],
                "rows": sum(p["rows"] for p in parts), "keys": [], "producer": "ARC_COMMON_LEDGER",
                "updated_at": "", "scope": "common", "index": path,
            }

    def _absorb_jsonl(self, path: str, root: str) -> None:
        for rec in read_jsonl(path):
            if not isinstance(rec, dict):
                continue
            p = rec.get("abs_path") or rec.get("path")
            real = foreign_remap(str(p or ""), [root] + self.roots)
            if not real:
                continue
            key = str(rec.get("key") or os.path.basename(real))
            self.datasets.setdefault(key.replace(".parquet", ""), {
                "path": real, "rows": 0, "keys": [], "producer": str(rec.get("source") or ""),
                "updated_at": str(rec.get("collected_at") or ""),
                "scope": str(rec.get("scope") or ""), "index": path,
            })

    def _absorb_status(self, path: str) -> None:
        obj = _read_json_ro(path)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and ":" in k:
                    self.status[k] = str(v)

    def _absorb_journal(self, path: str) -> None:
        obj = _read_json_ro(path)
        if isinstance(obj, dict) and isinstance(obj.get("log"), list):
            self.indexes_seen.append({"path": path, "kind": "journal",
                                      "events": len(obj["log"])})

    # ── 적재 ------------------------------------------------------------------------
    def load(self, *names: str, alias: Optional[dict] = None,
             max_parts: int = 0) -> Optional[pd.DataFrame]:
        """이름 후보 중 먼저 발견되는 데이터셋을 읽고, 별칭표로 컬럼을 표준화한다."""
        for nm in names:
            rec = self.datasets.get(nm)
            if not rec:
                continue
            paths = rec.get("parts") or [rec["path"]]
            if max_parts:
                paths = paths[-max_parts:]
            frames = []
            for p in paths:
                d = read_parquet_safe(p)
                if d is not None and len(d):
                    frames.append(d)
            if not frames:
                continue
            out = frames[0] if len(frames) == 1 else pd.concat(
                [f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                 for f in frames], ignore_index=True)
            PIPE.io("IN", "FOREIGN", f"dataset:{nm}", out, source=rec.get("index", ""))
            return foreign_normalize(out, alias) if alias else out
        return None

    def find(self, *substrings: str) -> "List[str]":
        out = []
        for nm in self.datasets:
            low = nm.lower()
            if any(s.lower() in low for s in substrings):
                out.append(nm)
        return sorted(out)

    def report(self) -> None:
        if not self.datasets:
            LOG.warn("외부 캐시에서 재활용할 데이터셋을 찾지 못했습니다 "
                     "(GDRIVE_FOREIGN_ROOTS 경로를 확인하세요). 신규 수집으로 진행합니다.")
            return
        rows = []
        for nm, r in sorted(self.datasets.items(), key=lambda kv: -kv[1].get("rows", 0))[:28]:
            rows.append([nm[:34], f"{r.get('rows', 0):,}", (r.get('producer') or '')[:18],
                         (r.get('scope') or '')[:9],
                         os.path.basename(os.path.dirname(r['path']))[:22]])
        LOG.banner("외부 캐시 재활용 카탈로그 (읽기 전용)",
                   f"루트 {len(self.roots)}개 · 데이터셋 {len(self.datasets)}개 · "
                   f"상태원장 {len(self.status):,}건 — 기존 인덱스는 열지도 고치지도 않습니다")
        LOG.table(rows, ["데이터셋", "행수", "생산자", "스코프", "폴더"])
        if self.errors:
            LOG.warn(f"일부 인덱스 파싱 실패 {len(self.errors)}건(무시하고 진행): "
                     f"{self.errors[:3]}")


def foreign_normalize(df: pd.DataFrame, alias: dict) -> pd.DataFrame:
    """별칭표로 컬럼을 표준명으로 바꾼다. 원본 컬럼은 지우지 않고 남긴다(정보 손실 방지)."""
    if df is None or not len(df):
        return df
    lower = {str(c).lower().strip(): c for c in df.columns}
    ren = {}
    for canon, cands in alias.items():
        if canon in df.columns:
            continue
        for c in cands:
            src = lower.get(str(c).lower())
            if src is not None and src not in ren.values():
                ren[canon] = src
                break
    out = df.copy()
    for canon, src in ren.items():
        out[canon] = df[src]
    return out


def foreign_reports(cat: "ForeignCatalog") -> pd.DataFrame:
    """외부 리포트 원장을 이 코드의 REPORT_COLS 스키마로 정규화해서 돌려준다."""
    d = cat.load("report_ledger", "arc_reports", "reports", "raw_reports",
                 alias=FOREIGN_ALIAS)
    if d is None or not len(d):
        return pd.DataFrame(columns=REPORT_COLS)

    out = pd.DataFrame(index=d.index)
    # source: 실측상 'hk' / 'nv' 로 저장되어 있다 → 이 코드의 표기로 사상
    src = d["source"].astype(str).str.lower().str.strip() if "source" in d.columns else pd.Series("", index=d.index)
    out["source"] = src.map({"hk": "hankyung", "hankyung": "hankyung",
                             "nv": "naver", "naver": "naver"}).fillna(src)
    out["src_report_id"] = d["src_report_id"].astype(str) if "src_report_id" in d.columns else ""
    for c in ("title", "stock_name", "broker_raw", "analyst_raw", "opinion",
              "pdf_url", "detail_url", "category"):
        out[c] = d[c].astype(str) if c in d.columns else ""
    out["stock_code"] = (d["stock_code"].map(to_code6) if "stock_code" in d.columns
                         else pd.Series(pd.NA, index=d.index))
    out["target_price"] = (pd.to_numeric(d["target_price"], errors="coerce")
                           if "target_price" in d.columns else np.nan)
    out["pub_date"] = as_ts_series(d["pub_date"]) if "pub_date" in d.columns else pd.NaT

    # 목표주가 0/음수는 '없음'이다 — 0 으로 넣으면 리비전 팩터가 오염된다.
    out.loc[~(out["target_price"] > 0), "target_price"] = np.nan

    out["report_uid"] = [
        sha1_str("rpt", s, i) for s, i in zip(out["source"].astype(str),
                                              out["src_report_id"].astype(str))]
    out["broker_id"] = ""
    out["broker_name"] = ""
    out["pdf_uid"] = ""
    out["views"] = np.nan
    out = out[out["pub_date"].notna()].copy()
    # PIT: 리포트의 knowledge_date 는 게시일이다.
    out["event_date"] = out["pub_date"]
    out["knowledge_date"] = out["pub_date"]
    out = out.reindex(columns=REPORT_COLS)
    LOG.ok(f"외부 리포트 원장 흡수: {len(out):,}건 "
           f"(종목코드 {out['stock_code'].notna().mean() * 100:.0f}% · "
           f"애널리스트 {(out['analyst_raw'].astype(str).str.len() > 0).mean() * 100:.0f}% · "
           f"목표주가 {out['target_price'].notna().mean() * 100:.0f}%)")
    return out


def foreign_analysts(cat: "ForeignCatalog") -> pd.DataFrame:
    """외부 애널리스트 원장(analyst_registry 등)을 흡수한다. 없으면 빈 프레임."""
    d = cat.load("analyst_registry", "analyst_index", "naver_analyst_index",
                 alias=FOREIGN_ALIAS)
    if d is None or not len(d):
        return pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"])
    out = pd.DataFrame(index=d.index)
    out["analyst_id"] = (d["analyst_id"].astype(str) if "analyst_id" in d.columns
                         else d.index.astype(str))
    out["name"] = d["analyst_raw"].astype(str) if "analyst_raw" in d.columns else ""
    out["broker_name"] = d["broker_raw"].astype(str) if "broker_raw" in d.columns else ""
    out["broker_id"] = out["broker_name"].map(lambda s: sha1_str("brk", norm_text(s))[:10])
    out = out[out["name"].str.len() > 0].drop_duplicates("analyst_id")
    LOG.ok(f"외부 애널리스트 원장 흡수: {len(out):,}명")
    return out


# ── 공용 레지스트리에 '추가만' 하는 발행 경로 ───────────────────────────────────────────────────

def foreign_publish_common(cat: "ForeignCatalog", dataset: str, df: pd.DataFrame,
                           keys: "Sequence[str]", producer: str) -> bool:
    """새로 수집한 공용 데이터를 사용자의 기존 공용 레지스트리에 **추가만** 한다.

    이 함수가 지키는 것(하나라도 깨지면 커밋하지 않고 사이드카로 물러난다):
      1. 데이터 파일은 **새 이름**으로만 쓴다. 기존 parquet 을 덮어쓰지 않는다.
      2. 레지스트리는 **새 키만** 추가한다. 기존 키의 값은 읽고 그대로 되쓴다.
      3. 쓰기 전 타임스탬프 백업을 만든다. 백업 실패 시 레지스트리를 건드리지 않는다.
      4. 원자적 교체 후 **다시 읽어** 기존 키가 전부 살아있는지 검증한다.
      5. 검증 실패 시 백업에서 즉시 롤백한다.
    """
    if not FOREIGN_PUBLISH_TO_COMMON or df is None or not len(df):
        return False
    # 기존 공용 레지스트리(_manifest_common.json)를 찾는다.
    reg = None
    for rec in cat.indexes_seen:
        if os.path.basename(rec.get("path", "")) == "_manifest_common.json":
            reg = rec["path"]
            break
    if not reg or not os.path.exists(reg):
        LOG.debug("공용 레지스트리(_manifest_common.json)를 찾지 못해 발행을 건너뜁니다.")
        return False

    obj = _read_json_ro(reg)
    if not isinstance(obj, dict):
        LOG.warn("공용 레지스트리를 파싱할 수 없어 발행하지 않습니다(안전 우선).")
        return False
    if dataset in obj:
        # 이미 있는 키는 건드리지 않는다. 이름을 바꿔 새 키로 발행한다.
        dataset = f"{dataset}__{STRATEGY_ID.lower()}"
    if dataset in obj:
        LOG.debug(f"공용 레지스트리에 이미 {dataset} 이 있어 발행을 건너뜁니다.")
        return False

    base = os.path.dirname(reg)
    dom = os.path.join(base, "customs" if "customs" in dataset else "external")
    try:
        os.makedirs(dom, exist_ok=True)
    except Exception:                                                    # noqa
        dom = base
    fpath = os.path.join(dom, f"{dataset}.parquet")
    if os.path.exists(fpath):                       # 남의 파일을 절대 덮지 않는다
        fpath = os.path.join(dom, f"{dataset}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
    try:
        atomic_write_parquet(df, fpath)
    except Exception as e:                                               # noqa
        LOG.warn(f"공용 데이터 파일 저장 실패({type(e).__name__}) — 발행 취소")
        return False

    bakdir = os.path.join(base, "_backups")
    bak = os.path.join(bakdir, f"_manifest_common.{_dt.datetime.now():%Y%m%d_%H%M%S}.json")
    try:
        os.makedirs(bakdir, exist_ok=True)
        shutil.copy2(reg, bak)
    except Exception as e:                                               # noqa
        LOG.warn(f"공용 레지스트리 백업 실패({type(e).__name__}) — "
                 f"레지스트리를 건드리지 않고 사이드카에만 기록합니다.")
        _publish_sidecar(base, dataset, fpath, df, keys, producer)
        return False

    before = set(obj.keys())
    obj[dataset] = {
        "dataset": dataset, "scope": "common", "keys": list(keys),
        "path": fpath, "rows": int(len(df)), "ext": ".parquet",
        "producer": f"{producer} {BUILD_VERSION}",
        "updated_at": _dt.datetime.now().astimezone().isoformat(),
        "files": [fpath],
    }
    try:
        atomic_write_text(reg, json.dumps(obj, ensure_ascii=False, indent=1))
        back = _read_json_ro(reg)
        if not isinstance(back, dict) or not before.issubset(set(back.keys())):
            raise RuntimeError("재읽기 검증 실패 — 기존 키가 유실되었습니다")
    except Exception as e:                                               # noqa
        try:
            shutil.copy2(bak, reg)                     # 즉시 롤백
            LOG.error(f"공용 레지스트리 갱신 실패({type(e).__name__}) — 백업에서 롤백했습니다.")
        except Exception:                                                # noqa
            LOG.error(f"공용 레지스트리 갱신 및 롤백 실패 — 백업 파일: {bak}")
        _publish_sidecar(base, dataset, fpath, df, keys, producer)
        return False
    LOG.ok(f"공용 레지스트리에 추가: {dataset} ({len(df):,}행) — "
           f"기존 {len(before)}개 키 전부 보존 확인 · 백업 {os.path.basename(bak)}")
    return True


def _publish_sidecar(base: str, dataset: str, fpath: str, df: pd.DataFrame,
                     keys: "Sequence[str]", producer: str) -> None:
    """레지스트리를 건드릴 수 없을 때의 물러섬. 별도 파일에만 기록한다."""
    side = os.path.join(base, f"_manifest_common_{STRATEGY_ID.lower()}.json")
    cur = _read_json_ro(side) if os.path.exists(side) else {}
    if not isinstance(cur, dict):
        cur = {}
    cur[dataset] = {"dataset": dataset, "scope": "common", "keys": list(keys),
                    "path": fpath, "rows": int(len(df)), "ext": ".parquet",
                    "producer": f"{producer} {BUILD_VERSION}",
                    "updated_at": _dt.datetime.now().astimezone().isoformat(),
                    "files": [fpath]}
    try:
        atomic_write_text(side, json.dumps(cur, ensure_ascii=False, indent=1))
        LOG.info(f"사이드카 레지스트리에 기록: {os.path.basename(side)} ← {dataset}")
    except Exception:                                                    # noqa
        LOG.warn("사이드카 기록도 실패했습니다. 데이터 파일 자체는 저장되어 있습니다.")


FOREIGN: Optional["ForeignCatalog"] = None


def foreign_init() -> "ForeignCatalog":
    """외부 캐시를 스캔해 전역 카탈로그를 세운다. 실패해도 실행은 계속된다."""
    global FOREIGN
    try:
        FOREIGN = ForeignCatalog(GDRIVE_FOREIGN_ROOTS).scan()
        FOREIGN.report()
    except Exception as e:                                               # noqa
        LOG.warn(f"외부 캐시 스캔 실패({type(e).__name__}: {e}) — 신규 수집으로 진행합니다.")
        FOREIGN = ForeignCatalog([])
    return FOREIGN
