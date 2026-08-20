# -*- coding: utf-8 -*-
"""G2B Demand Graph — §12 노드/엣지 구조와 §7 graph.asof(t).

Node:  AGENCY · CATEGORY · PLAN · PRESPEC · BID · AWARD · CONTRACT · SUPPLIER · LISTED_COMPANY
Edge:  AGENCY -ISSUES-> PLAN            PLAN -PRECEDES-> PRESPEC
       PRESPEC -PRECEDES-> BID          BID -IN_CATEGORY-> CATEGORY
       BID -REQUIRES_LICENSE-> LICENSE  BID -IN_REGION-> REGION
       BID -AWARDED_TO-> SUPPLIER       SUPPLIER -MAPS_TO-> LISTED_COMPANY
       AWARD -BECOMES-> CONTRACT

★ graph.asof(t) 가 돌려주는 노드·속성·엣지는 t 시점까지 알려진 것만 포함한다.
  그래프 자체는 사후에 연결해도 되지만 조회는 반드시 시점을 통과해야 한다(§7).
  그래서 모든 노드·엣지에 known_at 이 붙어 있고, asof 는 known_at <= t 로 자른다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from graph.lifecycle import STAGE_RANK
# ── /PACKAGE IMPORTS ──

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

NODE_TYPES = ("AGENCY", "CATEGORY", "LICENSE", "REGION", "PLAN", "PRESPEC", "BID",
              "AWARD", "CONTRACT", "SUPPLIER", "LISTED_COMPANY", "OPPORTUNITY")
EDGE_TYPES = ("ISSUES", "PRECEDES", "IN_CATEGORY", "REQUIRES_LICENSE", "IN_REGION",
              "AWARDED_TO", "MAPS_TO", "BECOMES", "BELONGS_TO")


def _nodes_from(df: pd.DataFrame, ntype: str, id_col: str, known_col: str,
                attrs: Sequence[str] = ()) -> pd.DataFrame:
    v = df[id_col].astype("string")
    m = v.notna() & (v.str.len() > 0)
    if not bool(m.any()):
        return pd.DataFrame(columns=["node_id", "node_type", "known_at"] + list(attrs))
    out = pd.DataFrame({"node_id": ntype + "␟" + v[m], "node_type": ntype,
                        "known_at": df.loc[m, known_col].to_numpy()})
    for a in attrs:
        out[a] = df.loc[m, a].to_numpy() if a in df.columns else np.nan
    return (out.sort_values("known_at", kind="stable")
            .drop_duplicates(subset=["node_id"], keep="first"))


def build_graph_nodes(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """노드 테이블. known_at = 그 노드가 처음 관측된 available_at."""
    parts = [
        _nodes_from(E, "AGENCY", "agency_cd", "available_at", ["agency_nm"]),
        _nodes_from(E, "CATEGORY", "category_cd", "available_at", ["category_nm", "proc_type"]),
        _nodes_from(E, "LICENSE", "license_req", "available_at"),
        _nodes_from(E, "REGION", "region_limit", "available_at"),
        _nodes_from(E, "SUPPLIER", "supplier_bizno", "available_at", ["supplier_nm"]),
        _nodes_from(E, "OPPORTUNITY", "opportunity_id", "available_at",
                    ["agency_cd", "category_cd", "proc_type"]),
    ]
    for st in ("PLAN", "PRESPEC", "BID", "AWARD", "CONTRACT"):
        sub = E[E["stage"] == st]
        if len(sub):
            parts.append(_nodes_from(sub, st, "doc_id", "available_at",
                                     ["amount", "agency_cd", "category_cd"]))
    if crosswalk is not None and len(crosswalk):
        cw = crosswalk.dropna(subset=["stock_code"]).copy()
        cw["known_at"] = pd.to_datetime(cw.get("valid_from")).fillna(pd.Timestamp("1990-01-01"))
        parts.append(_nodes_from(cw, "LISTED_COMPANY", "stock_code", "known_at", ["corp_name"]))
    N = pd.concat([p for p in parts if len(p)], ignore_index=True)
    return N.sort_values(["node_type", "known_at"], kind="stable").reset_index(drop=True)


def _edges(src: pd.Series, dst: pd.Series, etype: str, known: pd.Series,
           weight: Optional[pd.Series] = None) -> pd.DataFrame:
    m = src.notna() & dst.notna()
    if not bool(m.any()):
        return pd.DataFrame(columns=["src", "dst", "edge_type", "known_at", "weight"])
    return pd.DataFrame({"src": src[m].to_numpy(), "dst": dst[m].to_numpy(),
                         "edge_type": etype, "known_at": known[m].to_numpy(),
                         "weight": (weight[m].to_numpy() if weight is not None else 1.0)})


def build_graph_edges(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    S = lambda c: E[c].astype("string") if c in E.columns else pd.Series(pd.NA, index=E.index, dtype="string")
    doc = ("DOC␟" + S("stage") + "␟" + S("doc_id"))
    stage_node = (S("stage") + "␟" + S("doc_id"))
    opp = "OPPORTUNITY␟" + S("opportunity_id")
    ka = E["available_at"]
    amt = pd.to_numeric(E.get("amount"), errors="coerce")
    parts = [
        _edges("AGENCY␟" + S("agency_cd"), stage_node, "ISSUES", ka, amt),
        _edges(stage_node, "CATEGORY␟" + S("category_cd"), "IN_CATEGORY", ka, amt),
        _edges(stage_node, "LICENSE␟" + S("license_req"), "REQUIRES_LICENSE", ka),
        _edges(stage_node, "REGION␟" + S("region_limit"), "IN_REGION", ka),
        _edges(stage_node, opp, "BELONGS_TO", ka, amt),
        _edges(stage_node.where(E["stage"].isin(["AWARD", "CONTRACT"])),
               "SUPPLIER␟" + S("supplier_bizno"), "AWARDED_TO", ka, amt),
    ]
    # 단계 전이 PRECEDES / BECOMES — 같은 opportunity 안에서 시간순 인접 단계끼리 잇는다
    d = E[["opportunity_id", "stage", "doc_id", "available_at"]].dropna(subset=["opportunity_id"]).copy()
    d["rank"] = d["stage"].map(STAGE_RANK)
    d = d.dropna(subset=["rank"]).sort_values(["opportunity_id", "rank", "available_at"], kind="stable")
    d["node"] = d["stage"].astype(str) + "␟" + d["doc_id"].astype(str)
    g = d.groupby("opportunity_id", sort=False)
    d["prev_node"] = g["node"].shift(1)
    d["prev_rank"] = g["rank"].shift(1)
    adv = d[d["prev_node"].notna() & (d["rank"] > d["prev_rank"])]
    if len(adv):
        et = np.where((adv["prev_rank"] == STAGE_RANK["AWARD"]) &
                      (adv["rank"] == STAGE_RANK["CONTRACT"]), "BECOMES", "PRECEDES")
        parts.append(pd.DataFrame({"src": adv["prev_node"].to_numpy(), "dst": adv["node"].to_numpy(),
                                   "edge_type": et, "known_at": adv["available_at"].to_numpy(),
                                   "weight": 1.0}))
    if crosswalk is not None and len(crosswalk):
        cw = crosswalk.dropna(subset=["stock_code", "bizr_no"]).copy()
        kn = pd.to_datetime(cw.get("valid_from")).fillna(pd.Timestamp("1990-01-01"))
        parts.append(_edges("SUPPLIER␟" + cw["bizr_no"].astype("string"),
                            "LISTED_COMPANY␟" + cw["stock_code"].astype("string"),
                            "MAPS_TO", kn, pd.to_numeric(cw.get("confidence"), errors="coerce")))
    G = pd.concat([p for p in parts if len(p)], ignore_index=True)
    G = G.dropna(subset=["src", "dst"])
    return G.sort_values("known_at", kind="stable").reset_index(drop=True)


@dataclass
class DemandGraph:
    nodes: pd.DataFrame
    edges: pd.DataFrame

    def asof(self, t) -> "DemandGraph":
        """§7 — 시점 t 까지 알려진 노드·엣지만. 이 메서드 밖으로 그래프를 노출하지 않는다."""
        t = pd.Timestamp(t)
        n = self.nodes[self.nodes["known_at"] <= t]
        e = self.edges[self.edges["known_at"] <= t]
        alive = set(n["node_id"])
        e = e[e["src"].isin(alive) & e["dst"].isin(alive)]
        return DemandGraph(n.reset_index(drop=True), e.reset_index(drop=True))

    def summary(self) -> pd.DataFrame:
        a = self.nodes.groupby("node_type").size().rename("노드수").reset_index()
        b = self.edges.groupby("edge_type").size().rename("엣지수").reset_index()
        return pd.concat([a.rename(columns={"node_type": "종류", "노드수": "개수"}).assign(구분="노드"),
                          b.rename(columns={"edge_type": "종류", "엣지수": "개수"}).assign(구분="엣지")],
                         ignore_index=True)[["구분", "종류", "개수"]]


def build_graph(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> DemandGraph:
    N = build_graph_nodes(E, crosswalk)
    G = build_graph_edges(E, crosswalk)
    LOG.ok(f"G2B Demand Graph: 노드 {len(N):,} · 엣지 {len(G):,}")
    return DemandGraph(N, G)
