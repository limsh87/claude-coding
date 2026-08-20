#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04 — 기업 crosswalk (§13 §14 §52).

사업자등록번호 exact match 우선. 상호 fuzzy 는 후보 생성용으로만.
결과는 공용 인덱스에 적재한다(다른 전략도 그대로 쓴다).
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
import pipeline as P
from entity.dart_crosswalk import attach_stock_code, name_candidates
from audit.coverage import entity_gate


def main() -> int:
    header("04 기업 crosswalk", "§13 §14 §52 — 사업자등록번호 exact match 우선")
    E = require("events_pit", "03_build_pit_ledger.py")
    ctx = {}
    if CFG.RUN_MODE == "SMOKE":
        from collectors.synthetic import build_world
        ctx = build_world(opp_per_month=1)          # 마스터만 필요
    cw = P.load_crosswalk(E, ctx)
    if not len(cw):
        LOG.err("crosswalk 을 만들지 못했습니다 — OPENDART_API_KEY 또는 캐시를 확인하십시오.")
        return 1
    save("crosswalk", cw)
    L = attach_stock_code(E, cw)
    save("events_mapped", L)
    q, res = entity_gate(L)
    LOG.table(q.astype(str).values.tolist(), list(q.columns), title="§52 매칭 품질 (금액기준)")
    LOG.info(f"식별된 금액 중 exact 비중 {res.get('exact_among_identified', float('nan')):.3f} "
             f"→ 판정 {res['verdict']}")
    save("entity_gate", q)
    write_json(os.path.join(CFG.AUDIT_DIR, "entity_gate.json"), res)
    cand = name_candidates(E["supplier_nm"].dropna().unique()[:20000], cw)
    if len(cand):
        save("name_candidates", cand)
        LOG.info(f"상호 기반 후보 {len(cand):,}건 저장 — 사람이 검토해 VERIFIED_MANUAL 로 "
                 f"승격하기 전에는 PRIMARY 에 쓰지 않습니다(§13).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
