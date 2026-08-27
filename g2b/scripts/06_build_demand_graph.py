#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""06 — G2B Demand Graph (§12) 와 graph.asof(t) 검증 (§7)."""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from graph.demand_graph import build_graph


def main() -> int:
    header("06 Demand Graph", "§12 노드/엣지 · §7 asof")
    L = require("events_lifecycle", "05_build_lifecycle.py")
    cw = require("crosswalk", "04_build_company_crosswalk.py")
    G = build_graph(L, cw)
    save("graph_nodes", G.nodes)
    save("graph_edges", G.edges)
    S = G.summary()
    LOG.table(S.astype(str).values.tolist(), list(S.columns), title="§12 그래프 구성")
    save("graph_summary", S)

    # §7 asof 단조성 검증
    months = pd.to_datetime(G.nodes["known_at"]).dt.to_period("Y").dt.to_timestamp().unique()
    rows = []
    prev_n = prev_e = -1
    ok = True
    for t in sorted(months):
        g = G.asof(t)
        rows.append({"as_of": str(pd.Timestamp(t).date()), "노드": len(g.nodes), "엣지": len(g.edges)})
        if len(g.nodes) < prev_n or len(g.edges) < prev_e:
            ok = False
        prev_n, prev_e = len(g.nodes), len(g.edges)
        bad = int((pd.to_datetime(g.nodes["known_at"]) > pd.Timestamp(t)).sum())
        if bad:
            ok = False
            LOG.err(f"asof({t}) 가 미래 노드 {bad}개를 반환했습니다 — §7 위반")
    T = pd.DataFrame(rows)
    LOG.table(T.astype(str).values.tolist(), list(T.columns), title="graph.asof(t) 단조 성장")
    save("graph_asof_check", T)
    LOG.ok("graph.asof 시점제약 확인" if ok else "graph.asof 검증 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
