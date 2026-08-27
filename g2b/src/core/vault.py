# -*- coding: utf-8 -*-
"""VAULT — 구글드라이브 공용/전용 인덱스.

★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. 약속이 아니라 구조로 보장한다.
   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않는다.
   2) index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업.
   3) 컬럼은 합집합으로만 확장한다.
   4) blob 은 내용해시 경로 → 같은 내용은 재기록조차 없고, 다르면 새 리비전.
   5) 이미 드라이브에 있던 파일은 이동·개명 없이 경로만 등록한다(adopt-by-reference).
   6) 삭제 API 자체가 없다. 손상 파일도 .corrupt 로 격리만 한다.

  공용(_shared)  : 원본·범용 정제본. 다른 전략이 그대로 재사용한다.
                   → 이 연구가 새로 수집한 G2B 원장 6종이 여기에 기여된다.
  전용(g2b_dg_v1): 이 연구 고유의 lifecycle·graph·feature·backtest 산출물.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import (sha1_str, sha1_bytes, atomic_write_bytes, atomic_write_parquet,
                     read_parquet_safe, read_jsonl, append_jsonl, as_ts)
# ── /PACKAGE IMPORTS ──

import os
import json
import time
import shutil
import platform
import threading
import datetime as _dt
from collections import Counter
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Sequence

import numpy as np
import pandas as pd

VAULT_SCHEMA_VER = "g2b-1.0"

INDEX_COLUMNS = ["uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
                 "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
                 "project", "adopted", "schema_ver", "run_id", "extra"]


def _mount_drive() -> Tuple[str, str]:
    """(루트, 모드). Colab이면 마운트 시도, 아니면 동기화 폴더 → 로컬 폴백. 어느 쪽이든 죽지 않는다."""
    in_colab = False
    try:
        import google.colab  # noqa: F401
        in_colab = True
    except Exception:                                          # noqa: BLE001
        in_colab = False
    if in_colab:
        try:
            from google.colab import drive as _gdrive          # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return CFG.GDRIVE_ROOT, "COLAB_DRIVE"
            return CFG.LOCAL_CACHE_ROOT, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return CFG.LOCAL_CACHE_ROOT, "COLAB_MOUNT_ERROR→LOCAL"
    for cand in (CFG.GDRIVE_ROOT,
                 os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return CFG.LOCAL_CACHE_ROOT, "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
        self.ns = {"shared": os.path.join(self.root, CFG.GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, CFG.GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            for sub in ("index", os.path.join("index", "_backup"), "blob", "table"):
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, pd.DataFrame] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats: Counter = Counter()

    # ── 경로 ─────────────────────────────────────────────────────────────────
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 잠금 ─────────────────────────────────────────────────────────────────
    @contextmanager
    def lock(self, name: str, timeout: float = 60.0, stale: float = 900.0):
        lp = os.path.join(self.root, "_locks", f"{name}.lock")
        t0, acquired = time.time(), False
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
                        os.remove(lp)
                        continue
                except Exception:                              # noqa: BLE001
                    try:
                        os.remove(lp)
                    except Exception:                          # noqa: BLE001
                        pass
                time.sleep(0.3)
        if not acquired:
            LOG.warn(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:                              # noqa: BLE001
                    pass

    # ── 인덱스 적재 (읽기 전용) ───────────────────────────────────────────────
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []
        d = read_parquet_safe(self.idx_parquet(scope))
        if d is not None and len(d):
            frames.append(d)
        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))
        idx_dir = os.path.join(self.ns[scope], "index")
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if not fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    continue
                fp = os.path.join(idx_dir, fn)
                try:
                    if fl.endswith(".parquet"):
                        dd = read_parquet_safe(fp)
                    elif fl.endswith(".csv"):
                        dd = pd.read_csv(fp)
                    elif fl.endswith(".jsonl"):
                        dd = pd.DataFrame(read_jsonl(fp))
                    else:
                        dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                except Exception:                              # noqa: BLE001
                    continue
                if dd is not None and len(dd):
                    dd = dd.copy()
                    dd["_legacy_file"] = fn
                    frames.append(dd)
                    self.stats[f"legacy_index_absorbed:{fn}"] += len(dd)
        except Exception:                                      # noqa: BLE001
            pass

        if frames:
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            idx = pd.concat([f.reindex(columns=allcols) for f in frames], ignore_index=True)
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | idx["uid"].astype(str).str.strip().isin(("", "nan", "None"))
            if bool(miss.any()):
                # uid 결측 행을 astype(str) 하면 전부 "nan" 이 되어 drop_duplicates 가
                # 그 파일 전체를 한 줄로 붕괴시킨다 = 인덱스 유실. 절대 1원칙 위반이므로 개별 부여.
                src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                   "_legacy_file") if c in idx.columns]
                pos = np.where(miss.to_numpy())[0]
                idx.loc[idx.index[pos], "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in src]) for i in pos]
                LOG.info(f"레거시 인덱스 {len(pos):,}행에 uid 부여 (기존 기록 보존)")
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
            m &= idx[k].astype(str) == str(v)
        return idx[m]

    # ── 기록 ─────────────────────────────────────────────────────────────────
    def _register(self, scope: str, rec: dict) -> None:
        rec.setdefault("scope", scope)
        rec.setdefault("schema_ver", VAULT_SCHEMA_VER)
        rec.setdefault("collected_at", _dt.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("project", "g2b_demand_graph_v1")
        rec.setdefault("run_id", CFG.run_id())
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
        """원본 바이트를 내용해시 경로에 보존(§4 raw 불변). 같은 내용이면 재기록조차 하지 않는다."""
        if not data:
            return None
        h = sha1_bytes(data)
        uid = uid or sha1_str(domain, subtype, key, h)
        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])
        abspath = os.path.join(sub, f"{h}.{fmt.lstrip('.')}")
        if not os.path.exists(abspath):
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에도 남기지 않습니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": os.path.relpath(abspath, self.root), "abs_path": abspath, "fmt": fmt,
            "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "source": source, "adopted": False,
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str)})
        return abspath

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:                              # noqa: BLE001
                    continue
        return None

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "",
                  extra: Optional[dict] = None) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 덮어쓰지 않고 리비전 파일로 저장: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "", "source": source,
            "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:100]},
                                ensure_ascii=False, default=str)})
        self.stats[f"put_table:{scope}"] += 1
        return path

    def get_table(self, name: str, scope: str = "shared",
                  max_age_days: Optional[float] = None) -> Optional[pd.DataFrame]:
        """캐시 우선 조회. 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략 산출물도 재활용."""
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if not os.path.exists(path):
            alt = "private" if scope == "shared" else "shared"
            p2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if not os.path.exists(p2):
                return None
            path = p2
        if max_age_days is not None and (time.time() - os.path.getmtime(path)) / 86400.0 > max_age_days:
            return None
        d = read_parquet_safe(path)
        if d is not None:
            self.stats[f"cache_hit:{name}"] += 1
            LOG.debug(f"캐시 적중 {name}: {len(d):,}행 ← {os.path.relpath(path, self.root)}")
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str, source: str = "",
              event_date=None, knowledge_date=None, scope: str = "shared",
              extra: Optional[dict] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 경로만 등록한다."""
        try:
            sz = os.path.getsize(abs_path)
        except Exception:                                      # noqa: BLE001
            return None
        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)
        if self.has(scope, uid):
            return uid
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": abs_path, "abs_path": abs_path,
            "fmt": os.path.splitext(abs_path)[1].lstrip("."), "bytes": sz, "sha1": "",
            "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str)})
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ────────────────────────────────────────────────────────
    def flush(self, scope: Optional[str] = None) -> None:
        for sc in ([scope] if scope else ["shared", "private"]):
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)

    def compact(self, scope: str) -> None:
        self.flush(scope)
        idx = self.load_index(scope, force=True)
        p = self.idx_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 컴팩션을 건너뜁니다. "
                         f"저널이 원천이므로 유실 없음.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns
                                             if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션: {scope} — {len(idx):,}행")
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 감사 ─────────────────────────────────────────────────────────────────
    def report(self) -> None:
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc, ns in (("shared", CFG.GDRIVE_SHARED_NS), ("private", CFG.GDRIVE_PRIVATE_NS)):
            idx = self.load_index(sc)
            nb = float(pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum()) if len(idx) else 0.0
            nad = int(pd.to_numeric(idx.get("adopted"), errors="coerce").fillna(0).sum()) if len(idx) else 0
            rows.append([("공용 " + ns) if sc == "shared" else ("전용 " + ns), f"{len(idx):,}",
                         f"{nad:,}", f"{nb / 1e9:.3f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록", "용량", "저널"], ["l", "r", "r", "r", "l"])
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            if idx.empty or "domain" not in idx.columns:
                continue
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(20))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title=f"{'공용' if sc == 'shared' else '전용'} 인덱스 구성")
        if self.stats:
            LOG.table([[k, f"{v:,}"] for k, v in sorted(self.stats.items())][:30],
                      ["이벤트", "횟수"], ["l", "r"], title="이번 실행의 캐시 이벤트")
        LOG.info("무결성: 저널 append-only · index.parquet 백업 후 교체 · blob 내용해시 · 삭제 API 없음")


VAULT: Optional[Vault] = None


def get_vault() -> Vault:
    global VAULT
    if VAULT is None:
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        LOG.ok(f"VAULT 연결: {VAULT.root}  [{mode}]  "
               f"공용={CFG.GDRIVE_SHARED_NS} / 전용={CFG.GDRIVE_PRIVATE_NS}")
    return VAULT
