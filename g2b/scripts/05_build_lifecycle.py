#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""05 — Opportunity Lifecycle (§9 §10 §11).

강제 1:1 매칭을 하지 않는다. 1 plan→N bids, N plans→1 bid, 재입찰 N회, 1 award→복수 계약 모두 허용.
그리고 §11 이중계산이 실제로 제거되었는지 수치로 증명한다.
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from graph.lifecycle import (resolve_opportunities, opportunity_lifecycle,
                             double_count_audit, stage_ladder)
from entity.consortium import allocate, consortium_audit


def main() -> int:
    header("05 Lifecycle", "§9 §10 §11 — 이중계산 방지가 핵심")
    E = require("events_mapped", "04_build_company_crosswalk.py")
    L, diag = resolve_opportunities(E, use_attr=False)
    if len(diag):
        LOG.table(diag.T.reset_index().astype(str).values.tolist(), ["항목", "값"],
                  title="연결 진단")
    L = allocate(L, "primary")
    if "broad_category" not in L.columns:
        L["broad_category"] = L.get("license_req", L["proc_type"])
    save("events_lifecycle", L)

    dc = double_count_audit(L)
    LOG.table(dc.assign(금액=lambda d: (d["금액"] / 1e8).round(1)).astype(str).values.tolist(),
              ["측정", "금액(억원)"], title="§11 이중계산 제거 검증")
    save("double_count_audit", dc)
    corr = float(dc.loc[dc["측정"] == "lifecycle 증분합(정답)", "금액"].iloc[0])
    last = float(dc.loc[dc["측정"] == "opportunity 최종 알려진 금액 합", "금액"].iloc[0])
    if abs(corr - last) > max(1.0, abs(last) * 1e-6):
        LOG.err("증분합 ≠ 최종금액합 — 보존성이 깨졌습니다. 파이프라인을 세웁니다.")
        return 1
    LOG.ok("증분합 == 최종 알려진 금액 합 (이중계산 구조적 불가 확인)")

    ca = consortium_audit(L)
    LOG.table(ca.T.reset_index().astype(str).values.tolist(), ["항목", "값"],
              title="§16 공동수급 처리")
    save("consortium_audit", ca)

    lc = opportunity_lifecycle(L)
    save("opportunity_lifecycle", lc)
    LOG.table(lc["reached_stage"].value_counts().reset_index().astype(str).values.tolist(),
              ["도달단계", "건수"], title="lifecycle 도달 분포 (모든 건에 5단계가 다 있지 않다 §2.F)")
    save("stage_ladder", stage_ladder(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
