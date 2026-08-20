# -*- coding: utf-8 -*-
"""수집기 공통 계층 — 정규 스키마 · 내성 필드매핑 · 창(window) 페이징 · 캐시/체크포인트.

설계 원칙
  ① 필드명을 하나로 가정하지 않는다. 나라장터 서비스는 같은 뜻의 필드를 서비스마다
     다른 이름으로 준다(bidNtceNo / bidNtceNoOrd / ntceNo …). 후보 리스트로 매핑하고
     '무엇을 못 찾았는지'를 반드시 보고한다. 조용히 0 을 만들지 않는다.
  ② 같은 historical 요청을 두 번 하지 않는다(§87). RawStore 매니페스트가 진실.
  ③ raw 는 불변. 정규화는 언제든 raw 에서 재생성 가능해야 한다(§4).
  ④ 모든 정규 레코드는 pit.timestamps.stamp() 를 통과한다(§6).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.http import RawStore, Checkpoint, http_json, register_schema, request_uid, ApiError, _decoding_key
from core.io import as_ts_series, digits
from pit.timestamps import stamp
# ── /PACKAGE IMPORTS ──

import os
import re
import json
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

G2B_BASE = "https://apis.data.go.kr/1230000/"

STAGE_RANK = {"PLAN": 1, "PRESPEC": 2, "BID": 3, "AWARD": 4, "CONTRACT": 5}

# 정규 이벤트 스키마 — 6개 서비스가 모두 이 모양으로 수렴한다.
CANON_COLS = [
    "stage", "stage_rank", "service", "operation", "proc_type",
    "doc_id", "doc_seq", "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
    "agency_cd", "agency_nm", "demand_agency_cd", "demand_agency_nm",
    "category_cd", "category_nm", "title",
    "amount", "amount_kind", "expected_price", "award_rate", "bidder_count", "award_rank",
    "supplier_bizno", "supplier_nm", "share_ratio", "consortium_flag",
    "method", "region_limit", "license_req", "status_raw",
    "event_time", "source_published_at", "raw_uid",
]


def _first(rec: Dict[str, Any], names: Sequence[str]) -> Any:
    for n in names:
        if n in rec:
            v = rec[n]
            if v is not None and str(v).strip() not in ("", "-", "null", "None"):
                return v
    return None


@dataclass
class FieldMap:
    """정규컬럼 → API 필드명 후보들. 실제로 무엇이 잡혔는지 통계를 남긴다."""
    mapping: Dict[str, Sequence[str]]
    hits: Dict[str, int] = field(default_factory=dict)
    seen_fields: set = field(default_factory=set)

    def apply(self, records: List[dict]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=list(self.mapping))
        for r in records[:2000]:
            self.seen_fields.update(r.keys())
        out: Dict[str, List[Any]] = {}
        for canon, cands in self.mapping.items():
            col = [_first(r, cands) for r in records]
            n = sum(1 for v in col if v is not None)
            self.hits[canon] = self.hits.get(canon, 0) + n
            out[canon] = col
        return pd.DataFrame(out)

    def coverage(self, n_rows: int) -> pd.DataFrame:
        return pd.DataFrame([{"정규컬럼": k, "매핑후보": ",".join(self.mapping[k][:3]),
                              "채워진행": self.hits.get(k, 0),
                              "커버리지": (self.hits.get(k, 0) / n_rows) if n_rows else np.nan}
                             for k in self.mapping]).sort_values("커버리지")

    def unmapped(self) -> List[str]:
        used = {n for c in self.mapping.values() for n in c}
        return sorted(self.seen_fields - used)


@dataclass
class ServiceSpec:
    """하나의 나라장터 서비스 정의."""
    service: str                     # 내부 이름 (raw 디렉터리명)
    portal_id: str                   # 공공데이터포털 데이터셋 ID
    path: str                        # 서비스 경로 (…/1230000/<path>/)
    stage: str                       # PLAN / PRESPEC / BID / AWARD / CONTRACT / LINK
    operations: Dict[str, str]       # {업무구분: 오퍼레이션명}
    date_params: Tuple[str, str]     # (시작, 종료) 파라미터명
    date_fmt: str                    # "%Y%m%d%H%M" or "%Y%m%d"
    fieldmap: Dict[str, Sequence[str]]
    amount_kind: str
    official_range: str = ""
    notes: str = ""


def _items_of(payload: Any) -> List[dict]:
    """공공데이터포털 응답에서 item 리스트를 꺼낸다. 형태가 4가지쯤 된다."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    if "_raw_xml" in payload:
        return []
    body = payload.get("response", {}).get("body") if "response" in payload else payload
    if not isinstance(body, dict):
        return []
    items = body.get("items", body.get("item"))
    if items is None:
        return []
    if isinstance(items, dict):
        it = items.get("item", items)
        return [it] if isinstance(it, dict) else ([x for x in it if isinstance(x, dict)]
                                                   if isinstance(it, list) else [])
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    return []


def _total_of(payload: Any) -> Optional[int]:
    try:
        body = payload.get("response", {}).get("body", {})
        return int(body.get("totalCount"))
    except Exception:                                          # noqa: BLE001
        return None


def _result_msg(payload: Any) -> str:
    try:
        h = payload.get("response", {}).get("header", {})
        return f"{h.get('resultCode', '')} {h.get('resultMsg', '')}".strip()
    except Exception:                                          # noqa: BLE001
        return ""


def windows(start: str, end: str, freq: str = "MS") -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """수집 창 목록. 월 단위가 기본 — 창이 너무 크면 API 가 상한에서 잘라버린다."""
    s = pd.Timestamp(start).normalize().replace(day=1)
    e = pd.Timestamp(end).normalize()
    out = []
    for m in pd.date_range(s, e, freq=freq):
        w0 = m
        w1 = min(m + pd.offsets.MonthEnd(0), e)
        if w1 >= w0:
            out.append((w0, w1))
    return out


def fetch_window(spec: ServiceSpec, operation: str, w0: pd.Timestamp, w1: pd.Timestamp,
                 store: RawStore, max_pages: Optional[int] = None,
                 extra_params: Optional[dict] = None) -> Tuple[List[dict], Dict[str, Any]]:
    """한 창(window)을 페이징 수집. 이미 raw 에 있으면 네트워크에 나가지 않는다(§87)."""
    key = _decoding_key(CFG.DATA_GO_KR_SERVICE_KEY)
    fmt = spec.date_fmt
    d0 = w0.strftime(fmt) if len(fmt) > 8 else w0.strftime(fmt)
    d1 = (w1.strftime("%Y%m%d") + "2359") if fmt == "%Y%m%d%H%M" else w1.strftime(fmt)
    if fmt == "%Y%m%d%H%M":
        d0 = w0.strftime("%Y%m%d") + "0000"
    rows: List[dict] = []
    info = {"pages": 0, "from_cache": 0, "fetched": 0, "errors": [], "total": None, "msg": ""}
    max_pages = max_pages or CFG.MAX_PAGES_PER_WINDOW
    for page in range(1, max_pages + 1):
        params = {"serviceKey": key, "numOfRows": CFG.PAGE_ROWS, "pageNo": page,
                  "inqryDiv": "1", "type": "json",
                  spec.date_params[0]: d0, spec.date_params[1]: d1}
        params.update(extra_params or {})
        uid = request_uid(spec.service, operation, params)
        payload = None
        if store.has(uid):
            payload = store.load(uid)
            if payload is not None:
                info["from_cache"] += 1
        if payload is None:
            if CFG.RUN_MODE == "CACHED":
                break
            if not key:
                info["errors"].append("NO_KEY")
                break
            payload, meta = http_json(G2B_BASE + spec.path + "/" + operation, params,
                                      source="datagokr")
            if payload is None:
                info["errors"].append(meta.get("error", "unknown"))
                break
            its0 = _items_of(payload)
            store.save(uid, operation, params, payload, meta, len(its0),
                       register_schema(spec.service, operation,
                                       sorted({k for r in its0[:200] for k in r})) if its0 else "empty")
            info["fetched"] += 1
        its = _items_of(payload)
        if info["total"] is None:
            info["total"] = _total_of(payload)
            info["msg"] = _result_msg(payload)
        info["pages"] += 1
        rows.extend(its)
        if len(its) < CFG.PAGE_ROWS:
            break
        if info["total"] is not None and len(rows) >= info["total"]:
            break
    return rows, info


def collect_service(spec: ServiceSpec, start: str, end: str,
                    ops: Optional[Sequence[str]] = None,
                    freq: str = "MS") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """서비스 전체 기간 수집 → (정규화 이벤트, 수집 감사표). 중단 후 재개 가능."""
    store = RawStore(spec.service)
    ckpt = Checkpoint(spec.service)
    fm = FieldMap(spec.fieldmap)
    op_items = [(k, v) for k, v in spec.operations.items() if (ops is None or k in ops)]
    wins = windows(start, end, freq)
    all_rows: List[dict] = []
    audit: List[dict] = []
    for proc_type, operation in op_items:
        for (w0, w1) in wins:
            ckey = f"{operation}|{w0:%Y%m}"
            try:
                rows, info = fetch_window(spec, operation, w0, w1, store)
            except ApiError as e:
                LOG.warn(f"{spec.service}/{operation} {w0:%Y-%m} 중단: {e}")
                ckpt.save()
                audit.append({"service": spec.service, "operation": operation, "proc_type": proc_type,
                              "window": f"{w0:%Y-%m}", "rows": 0, "pages": 0, "from_cache": 0,
                              "error": "BUDGET_EXHAUSTED"})
                return _finish(spec, fm, all_rows, audit, store)
            for r in rows:
                r["_proc_type"] = proc_type
                r["_operation"] = operation
            all_rows.extend(rows)
            ckpt.mark(ckey, {"rows": len(rows), "pages": info["pages"]})
            audit.append({"service": spec.service, "operation": operation, "proc_type": proc_type,
                          "window": f"{w0:%Y-%m}", "rows": len(rows), "pages": info["pages"],
                          "from_cache": info["from_cache"], "fetched": info["fetched"],
                          "total_reported": info["total"],
                          "error": ";".join(map(str, info["errors"]))[:120],
                          "msg": info["msg"][:80]})
    ckpt.save()
    return _finish(spec, fm, all_rows, audit, store)


def _finish(spec: ServiceSpec, fm: FieldMap, rows: List[dict], audit: List[dict],
            store: RawStore) -> Tuple[pd.DataFrame, pd.DataFrame]:
    A = pd.DataFrame(audit)
    if not rows:
        return pd.DataFrame(columns=CANON_COLS), A
    D = fm.apply(rows)
    D["service"] = spec.service
    D["stage"] = spec.stage
    D["stage_rank"] = STAGE_RANK.get(spec.stage, 0)
    D["amount_kind"] = spec.amount_kind
    D["proc_type"] = [r.get("_proc_type") for r in rows]
    D["operation"] = [r.get("_operation") for r in rows]
    D = normalize_common(D)
    if fm.unmapped():
        LOG.info(f"{spec.service}: 미매핑 필드 {len(fm.unmapped())}개 (raw 에는 보존됨) "
                 f"예: {fm.unmapped()[:8]}")
    return D, A


_NUM = re.compile(r"[^0-9.\-]")


def to_amount(s: pd.Series) -> pd.Series:
    """'1,234,000원' 같은 문자열 금액을 숫자로. 콤마를 안 지우면 전부 NaN 이 된다."""
    if s.dtype.kind in "if":
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(s.astype(str).str.replace(_NUM, "", regex=True).replace("", np.nan),
                         errors="coerce")


def normalize_common(D: pd.DataFrame) -> pd.DataFrame:
    d = D.copy()
    for c in CANON_COLS:
        if c not in d.columns:
            d[c] = np.nan
    for c in ("amount", "expected_price", "award_rate", "bidder_count", "award_rank", "share_ratio"):
        d[c] = to_amount(d[c])
    for c in ("supplier_bizno",):
        d[c] = d[c].map(digits).replace("", np.nan)
    for c in ("doc_id", "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
              "agency_cd", "agency_nm", "demand_agency_cd", "demand_agency_nm",
              "category_cd", "category_nm", "title", "supplier_nm", "method",
              "region_limit", "license_req", "status_raw", "proc_type"):
        d[c] = d[c].astype("string").str.strip()
    d["event_time"] = _parse_dt(d["event_time"])
    d["source_published_at"] = _parse_dt(d["source_published_at"])
    return d[CANON_COLS]


def _parse_dt(s: pd.Series) -> pd.Series:
    """'20240115' / '2024-01-15 13:20:00' / '202401151320' 를 모두 받는다."""
    x = s.astype("string").str.strip()
    x = x.str.replace(r"[^\d]", "", regex=True)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for ln, fmt in ((14, "%Y%m%d%H%M%S"), (12, "%Y%m%d%H%M"), (8, "%Y%m%d"), (6, "%Y%m")):
        m = out.isna() & (x.str.len() == ln)
        if bool(m.any()):
            out.loc[m] = pd.to_datetime(x[m], format=fmt, errors="coerce")
    m = out.isna() & x.notna() & (x.str.len() > 0)
    if bool(m.any()):
        out.loc[m] = pd.to_datetime(s[m], errors="coerce")
    return out


def stamp_stage(D: pd.DataFrame, stage: str) -> pd.DataFrame:
    """정규 이벤트에 PIT 3시각을 부여한다."""
    return stamp(D, "event_time", "source_published_at", stage=stage)
