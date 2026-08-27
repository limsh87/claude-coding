# -*- coding: utf-8 -*-
"""HTTP 계층 + 불변 RAW 저장소 + 호출 매니페스트 + 스키마 레지스트리.

명세 대응:
  §4  API 호출마다 source_service/operation/request_params/requested_at/fetched_at/
      HTTP status/row_count/response_hash/schema_version/raw_filename 을 남긴다.
      raw 는 절대 덮어쓰지 않는다.
  §86 필드 스키마를 날짜별 버전으로 관리한다 (schema_registry/).
  §87 pagination · cache · incremental · retry/backoff · checkpoint · resume.
      동일 historical request 를 반복 호출하지 않는다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import (sha1_str, sha256_bytes, atomic_write_bytes, append_jsonl, read_jsonl,
                     read_json, write_json, limiter, CallBudget)
# ── /PACKAGE IMPORTS ──

import os
import gzip
import json
import time
import random
import threading
import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_TLS = threading.local()
HTTP_STATS: Dict[str, int] = {}
_STAT_LK = threading.Lock()


def _stat(k: str, n: int = 1) -> None:
    with _STAT_LK:
        HTTP_STATS[k] = HTTP_STATS.get(k, 0) + n


def _session():
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    import requests
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    try:
        s.mount("https://", HTTPAdapter(pool_connections=max(8, CFG.N_WORKERS_IO * 2),
                                        pool_maxsize=max(16, CFG.N_WORKERS_IO * 4)))
    except Exception:                                          # noqa: BLE001
        pass
    s.headers.update({"User-Agent": "g2b-demand-graph/1.0 (research)",
                      "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"})
    _TLS.sess = s
    return s


BUDGET = CallBudget(os.path.join(CFG.AUDIT_DIR, "call_budget.json"))


class ApiError(Exception):
    pass


def _decoding_key(key: str) -> str:
    """공공데이터포털 키. Encoding 키(%2B/%3D 포함)를 그대로 넣으면 이중 인코딩으로 401 이 난다."""
    if not key:
        return key
    if "%" in key:
        try:
            from urllib.parse import unquote
            dec = unquote(key)
            if dec != key:
                LOG.warn("DATA_GO_KR_SERVICE_KEY 가 Encoding 키로 보입니다 — Decoding 키로 자동 변환합니다.")
                return dec
        except Exception:                                      # noqa: BLE001
            pass
    return key


def http_json(url: str, params: Dict[str, Any], source: str = "datagokr",
              tries: int = 4, timeout: float = 40.0) -> Tuple[Optional[Any], Dict[str, Any]]:
    """(payload, meta). 예외를 삼키지 않고 meta 에 실패 사유를 남긴다."""
    cap = CFG.DAILY_CALL_BUDGET.get(source)
    if cap is not None and BUDGET.remaining(source, cap) <= 0:
        raise ApiError(f"[{source}] 일일 호출예산 {cap:,}회 소진 — 체크포인트를 남기고 중단합니다(§87).")
    qps = CFG.RATE_LIMIT_QPS.get(source, 3.0)
    meta: Dict[str, Any] = {"requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
                            "http_status": None, "error": "", "attempts": 0}
    last_exc = ""
    for k in range(tries):
        meta["attempts"] = k + 1
        limiter(source, qps).wait()
        try:
            r = _session().get(url, params=params, timeout=timeout)
            BUDGET.charge(source)
            meta["http_status"] = r.status_code
            _stat(f"{source}:{r.status_code}")
            if r.status_code in (429, 500, 502, 503, 504):
                last_exc = f"HTTP {r.status_code}"
                time.sleep(min(30.0, (1.8 ** k) + random.random()))
                continue
            if r.status_code != 200:
                meta["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
                return None, meta
            body = r.content
            meta["fetched_at"] = _dt.datetime.now().isoformat(timespec="seconds")
            meta["response_hash"] = sha256_bytes(body)
            meta["bytes"] = len(body)
            txt = body.decode("utf-8", errors="replace")
            try:
                return json.loads(txt), meta
            except Exception:                                  # noqa: BLE001
                # 공공데이터포털은 오류 시 JSON 대신 XML/HTML 을 200 으로 돌려준다.
                meta["error"] = "NON_JSON"
                meta["raw_text"] = txt[:800]
                return {"_raw_xml": txt}, meta
        except Exception as e:                                 # noqa: BLE001
            last_exc = f"{type(e).__name__}: {e}"
            _stat(f"{source}:exc")
            time.sleep(min(30.0, (1.8 ** k) + random.random()))
    meta["error"] = last_exc or "unknown"
    meta["fetched_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    return None, meta


# ══════════════════════════════════════════════════════════════════════════════
#  RAW 저장소 — 불변. 같은 요청을 두 번 하지 않는다.
# ══════════════════════════════════════════════════════════════════════════════
_REDACT = ("serviceKey", "ServiceKey", "crtfc_key", "key")


def request_uid(service: str, operation: str, params: Dict[str, Any]) -> str:
    p = {k: v for k, v in sorted(params.items()) if k not in _REDACT}
    return sha1_str("g2breq", service, operation, json.dumps(p, sort_keys=True, default=str))


class RawStore:
    """data/raw/<service>/ 아래에 응답 원본을 gzip 으로 보존하고 매니페스트를 append 한다.

    · 파일명은 요청 uid 기반 → 같은 요청은 같은 파일. 이미 있으면 네트워크에 나가지 않는다.
    · 매니페스트는 append-only JSONL. 기존 줄을 재기록하지 않는다.
    """

    def __init__(self, service: str):
        self.service = service
        self.dir = os.path.join(CFG.RAW_DIR, service)
        os.makedirs(self.dir, exist_ok=True)
        self.manifest_path = os.path.join(self.dir, "_manifest.jsonl")
        self._lk = threading.Lock()
        self._seen: Optional[Dict[str, dict]] = None

    def manifest(self) -> Dict[str, dict]:
        if self._seen is None:
            rows = read_jsonl(self.manifest_path)
            self._seen = {str(r.get("uid")): r for r in rows if r.get("uid")}
        return self._seen

    def has(self, uid: str) -> bool:
        return uid in self.manifest()

    def path_for(self, uid: str) -> str:
        return os.path.join(self.dir, uid[:2], f"{uid}.json.gz")

    def load(self, uid: str) -> Optional[Any]:
        p = self.path_for(uid)
        if not os.path.exists(p):
            return None
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"raw 파손({type(e).__name__}) — 격리만 합니다: {p}")
            try:
                os.rename(p, p + ".corrupt")
            except Exception:                                  # noqa: BLE001
                pass
            return None

    def save(self, uid: str, operation: str, params: Dict[str, Any], payload: Any,
             meta: Dict[str, Any], row_count: int, schema_version: str) -> str:
        p = self.path_for(uid)
        if not os.path.exists(p):                      # 절대 덮어쓰지 않는다
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            atomic_write_bytes(p, gzip.compress(body, 6))
        rec = {"uid": uid, "source_service": self.service, "operation": operation,
               "request_params": {k: v for k, v in params.items() if k not in _REDACT},
               "requested_at": meta.get("requested_at"), "fetched_at": meta.get("fetched_at"),
               "http_status": meta.get("http_status"), "row_count": int(row_count),
               "response_hash": meta.get("response_hash", ""), "schema_version": schema_version,
               "raw_filename": os.path.relpath(p, CFG.PROJECT_ROOT),
               "bytes": meta.get("bytes", 0), "error": meta.get("error", ""),
               "run_id": CFG.run_id()}
        with self._lk:
            append_jsonl(self.manifest_path, [rec])
            if self._seen is not None:
                self._seen[uid] = rec
        return p

    def manifest_df(self) -> pd.DataFrame:
        rows = read_jsonl(self.manifest_path)
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["uid", "source_service", "operation", "row_count", "http_status"])


# ══════════════════════════════════════════════════════════════════════════════
#  체크포인트 — 중단 후 재개 (§87)
# ══════════════════════════════════════════════════════════════════════════════
class Checkpoint:
    def __init__(self, name: str):
        self.path = os.path.join(CFG.AUDIT_DIR, f"checkpoint_{name}.json")
        self.state: Dict[str, Any] = read_json(self.path, {}) or {}
        self._lk = threading.Lock()

    def done(self, key: str) -> bool:
        return bool(self.state.get(key))

    def mark(self, key: str, info: Any = True) -> None:
        with self._lk:
            self.state[key] = info
            if len(self.state) % 25 == 0:
                write_json(self.path, self.state)

    def save(self) -> None:
        with self._lk:
            write_json(self.path, self.state)


# ══════════════════════════════════════════════════════════════════════════════
#  스키마 레지스트리 (§86) — 필드 집합이 언제 바뀌었는지 날짜별로 기록
# ══════════════════════════════════════════════════════════════════════════════
def register_schema(service: str, operation: str, fields: List[str]) -> str:
    os.makedirs(CFG.SCHEMA_REGISTRY_DIR, exist_ok=True)
    fields = sorted(set(map(str, fields)))
    ver = sha1_str(service, operation, "|".join(fields))[:12]
    path = os.path.join(CFG.SCHEMA_REGISTRY_DIR, f"{service}.{operation}.jsonl")
    known = {r.get("schema_version") for r in read_jsonl(path)}
    if ver not in known:
        append_jsonl(path, [{"schema_version": ver, "service": service, "operation": operation,
                             "first_seen": _dt.date.today().isoformat(),
                             "n_fields": len(fields), "fields": fields,
                             "run_id": CFG.run_id()}])
        if known:
            LOG.warn(f"[§86] 스키마 변경 감지: {service}.{operation} → 새 버전 {ver} "
                     f"(기존 {len(known)}개). 과거·현재 식별자 정의가 같다고 가정하지 않습니다.")
    return ver


def report_http() -> None:
    if not HTTP_STATS:
        return
    LOG.table([[k, f"{v:,}"] for k, v in sorted(HTTP_STATS.items())],
              ["소스:상태", "건수"], ["l", "r"], title="HTTP 호출 통계")
    for src, cap in CFG.DAILY_CALL_BUDGET.items():
        LOG.info(f"호출예산 {src}: {BUDGET.used(src):,} / {cap:,} 사용")
