# -*- coding: utf-8 -*-
"""Lifecycle 연결 — §10 연결 우선순위와 link_method / link_score / link_known_at.

우선순위
  1순위  공식 식별번호                (link_score 1.00)
  2순위  계약과정통합공개서비스 관계    (0.90)
  3순위  발주기관+사업명+품목+금액+날짜 결정적 결합 (0.70)
  4순위  텍스트 유사도                 (0.40, 후보일 뿐 확정 아님)

원칙: **애매한 연결을 억지로 확정하지 않는다.** 3·4순위는 기본적으로 PRIMARY 에서 꺼져 있고,
      켜더라도 link_score 가 남아 민감도 분석이 가능하다.
      link_known_at = 그 연결을 '언제부터 알 수 있었는가' (두 문서의 available_at 중 늦은 쪽).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from entity.dart_crosswalk import norm_name
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

LINK_KEY_COLS = ("link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no")

LINK_METHOD_SCORE = {"OFFICIAL_ID": 1.00, "PROCESS_LEDGER": 0.90,
                     "DETERMINISTIC_ATTR": 0.70, "TEXT_SIMILARITY": 0.40}


def doc_key(E: pd.DataFrame) -> pd.Series:
    """문서 노드 식별자 — (service, doc_id). doc_id 가 없으면 행 자체를 고립 문서로 둔다."""
    svc = E["service"].astype("string").fillna("na")
    did = E["doc_id"].astype("string")
    fallback = pd.Series("row#" + E.index.astype(str), index=E.index, dtype="string")
    return svc + "␟" + did.where(did.notna() & (did.str.len() > 0), fallback)


def official_id_edges(E: pd.DataFrame) -> pd.DataFrame:
    """1순위 — 공식 식별번호로 문서와 키를 잇는 이분 간선."""
    dk = doc_key(E)
    parts = []
    for c in LINK_KEY_COLS:
        if c not in E.columns:
            continue
        v = E[c].astype("string")
        m = v.notna() & (v.str.len() > 0)
        if not bool(m.any()):
            continue
        parts.append(pd.DataFrame({
            "doc": dk[m].to_numpy(),
            "key": (c.replace("link_", "") + "␟" + v[m]).to_numpy(),
            "method": "OFFICIAL_ID",
            "known_at": E.loc[m, "available_at"].to_numpy()}))
    # 자기 자신의 doc_id 도 키로 등록 — 같은 문서의 리비전들이 뭉치도록
    parts.append(pd.DataFrame({"doc": dk.to_numpy(),
                               "key": ("self␟" + dk).to_numpy(),
                               "method": "OFFICIAL_ID",
                               "known_at": E["available_at"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])


def process_ledger_edges(E: pd.DataFrame) -> pd.DataFrame:
    """2순위 — 계약과정통합공개(service=='process') 행은 여러 단계 번호를 한 행에 갖는다.
    그 행을 매개로 서로 다른 단계의 문서가 이어진다."""
    P = E[E["service"].astype(str) == "process"]
    if not len(P):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    dk = doc_key(P)
    parts = []
    for c in LINK_KEY_COLS:
        if c not in P.columns:
            continue
        v = P[c].astype("string")
        m = v.notna() & (v.str.len() > 0)
        if bool(m.any()):
            parts.append(pd.DataFrame({"doc": dk[m].to_numpy(),
                                       "key": (c.replace("link_", "") + "␟" + v[m]).to_numpy(),
                                       "method": "PROCESS_LEDGER",
                                       "known_at": P.loc[m, "available_at"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])


def deterministic_attr_edges(E: pd.DataFrame, amount_tol: float = 0.05,
                             day_window: int = 400) -> pd.DataFrame:
    """3순위 — (발주기관 × 품목 × 정규화사업명) 이 같고 금액이 근접하며 시점이 가까운 문서 결합.

    PRIMARY 에서는 기본 OFF. 켜면 link_score 0.70 으로 기록되어 민감도 분석이 가능하다.
    금액 버킷을 쓰므로 O(N) 이다 — 전수 페어 비교를 하지 않는다.
    """
    need = ["agency_cd", "category_cd", "title", "amount", "available_at"]
    if any(c not in E.columns for c in need):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    d = E.dropna(subset=["amount"]).copy()
    if not len(d):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    d["_nm"] = d["title"].map(norm_name)
    d = d[d["_nm"].str.len() >= 4]
    if not len(d):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    # 금액을 로그 버킷으로 이산화 → 같은 버킷만 후보
    lg = np.log1p(pd.to_numeric(d["amount"], errors="coerce").clip(lower=0))
    bucket = np.floor(lg / max(amount_tol, 1e-6)).astype("Int64")
    per = (pd.to_datetime(d["available_at"]).view("int64") // (86400 * 10**9) // max(day_window, 1))
    key = (d["agency_cd"].astype("string").fillna("") + "␟" +
           d["category_cd"].astype("string").fillna("") + "␟" + d["_nm"] + "␟" +
           bucket.astype("string") + "␟" + per.astype("string"))
    return pd.DataFrame({"doc": doc_key(d).to_numpy(), "key": ("attr␟" + key).to_numpy(),
                         "method": "DETERMINISTIC_ATTR",
                         "known_at": d["available_at"].to_numpy()})


def build_edges(E: pd.DataFrame, use_official: bool = True, use_process: bool = True,
                use_attr: bool = False, use_text: bool = False) -> pd.DataFrame:
    parts = []
    if use_official:
        parts.append(official_id_edges(E))
    if use_process:
        parts.append(process_ledger_edges(E))
    if use_attr:
        parts.append(deterministic_attr_edges(E))
    if use_text:
        LOG.warn("텍스트 유사도 연결(4순위)은 확정 연결로 쓰지 않습니다 — 후보 생성만 지원합니다(§10).")
    ed = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])
    if len(ed):
        ed["link_score"] = ed["method"].map(LINK_METHOD_SCORE).astype(float)
    return ed
