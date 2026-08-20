# -*- coding: utf-8 -*-
"""PIT 감사표 — reports/01_PIT_AUDIT.md 의 내용물.   §5 · §6 · §8 · §11

  · API 실측 깊이 (01 스크립트 산출물을 표로)
  · 필드 등급(CLASS A/B/C) 분포와 PIT_UNCERTIFIED 목록
  · event → published → available 지연 분포
  · 리비전 처리 / 이중계산 제거가 실제로 작동했는지 수치 증명
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from pit.timestamps import audit_lag, class_table, field_class
from pit.revisions import revision_audit
from graph.lifecycle import double_count_audit
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


def api_depth_table(manifests: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """§5 — API별 최초/마지막 실측일·건수·핵심필드 커버리지·수정이력·사용가능."""
    rows = []
    for svc, M in manifests.items():
        if M is None or not len(M):
            rows.append({"API": svc, "최초 실측일": "—", "마지막 실측일": "—", "건수": 0,
                         "핵심필드 커버리지": "—", "수정이력 존재": "—", "사용가능": "NO_DATA"})
            continue
        n = int(pd.to_numeric(M.get("row_count"), errors="coerce").fillna(0).sum())
        ok = M[pd.to_numeric(M.get("row_count"), errors="coerce").fillna(0) > 0]
        def _wd(x, how):
            if not len(ok):
                return "—"
            w = ok["request_params"].map(
                lambda p: (p or {}).get("inqryBgnDt") or (p or {}).get("inqryBgnDate") or
                          (p or {}).get("bidNtceBgnDt") or (p or {}).get("opengBgnDt") or
                          (p or {}).get("cntrctCnclsBgnDate") or "")
            w = w[w.astype(str).str.len() >= 6]
            return (w.min() if how == "min" else w.max()) if len(w) else "—"
        rows.append({"API": svc, "최초 실측일": _wd(ok, "min"), "마지막 실측일": _wd(ok, "max"),
                     "건수": n,
                     "핵심필드 커버리지": f"{100 * len(ok) / max(len(M), 1):.0f}% 창에서 데이터",
                     "수정이력 존재": ("Y" if M["operation"].astype(str).str.contains(
                         "Chg|Dlt", regex=True).any() else "N"),
                     "사용가능": "YES" if n > 0 else "NO_DATA"})
    return pd.DataFrame(rows)


def field_class_report(events: pd.DataFrame) -> pd.DataFrame:
    """실제 수집된 컬럼이 어떤 등급인지. 미등록 컬럼은 자동 CLASS C(=사용 금지)."""
    cols = [c for c in events.columns if not c.startswith("_")]
    return pd.DataFrame([{"컬럼": c, "PIT_CLASS": field_class(c),
                          "결측률": float(events[c].isna().mean()),
                          "사용가능": "✔" if field_class(c) in ("A", "B") else "✖ PIT_UNCERTIFIED"}
                         for c in cols]).sort_values(["PIT_CLASS", "컬럼"]).reset_index(drop=True)


def lag_report(events: pd.DataFrame) -> pd.DataFrame:
    out = []
    for st, g in events.groupby("stage", observed=True):
        try:
            out.append(audit_lag(g, st))
        except Exception as e:                                 # noqa: BLE001
            out.append(pd.DataFrame([{"table": st, "rows": len(g), "error": str(e)[:80]}]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def revision_report(events: pd.DataFrame) -> pd.DataFrame:
    out = []
    for st in ("BID", "CONTRACT"):
        g = events[events["stage"] == st]
        if len(g):
            out.append(revision_audit(g, ["service", "doc_id"], "amount", st))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def full_pit_audit(events: pd.DataFrame, manifests: Optional[Dict[str, pd.DataFrame]] = None
                   ) -> Dict[str, pd.DataFrame]:
    res = {"field_class_summary": class_table().groupby("pit_class").size()
           .rename("필드수").reset_index(),
           "field_class_detail": field_class_report(events),
           "lag": lag_report(events),
           "revision": revision_report(events)}
    # 이중계산 감사는 lifecycle 해석(opportunity_id) 이후에만 가능하다 → 05 스크립트에서 수행.
    if "opportunity_id" in events.columns:
        res["double_count"] = double_count_audit(events)
    else:
        LOG.info("opportunity_id 가 아직 없어 이중계산 감사(§11)는 05_build_lifecycle 단계에서 수행합니다.")
    if manifests:
        res["api_depth"] = api_depth_table(manifests)
    return res
