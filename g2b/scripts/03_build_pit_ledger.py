#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""03 — PIT 원장 구축과 감사 (§6 §8 §11).

세 시각 부여 · 리비전 구간 복원 · 필드등급 판정 · 이중계산 제거 검증.
여기서 USABLE_START_DATE 후보를 '커버리지만 보고' 산출한다(§48).
"""
from _common import *                                          # noqa: F401,F403
import numpy as np
import pandas as pd
from pit.timestamps import stamp, require_pit
from audit.pit_audit import full_pit_audit
from audit.leakage_test import scan_events


def main() -> int:
    header("03 PIT 원장", "§6 §8 §11 §48")
    E = require("events_raw", "02_collect_history.py")
    if "available_at" not in E.columns:
        E = stamp(E, "event_time", "source_published_at", stage="BID")
    require_pit(E, "03_build_pit_ledger")

    viol = scan_events(E)
    if len(viol):
        LOG.err("PIT 구조 위반이 발견되었습니다:")
        LOG.table(viol.astype(str).values.tolist(), list(viol.columns))
        LOG.err("→ PIT_BLOCKED 후보입니다(§96). 원인을 해소하기 전에는 백테스트 금지.")
    else:
        LOG.ok("PIT 구조 위반 없음")

    R = full_pit_audit(E)
    for k, T in R.items():
        if isinstance(T, pd.DataFrame) and len(T):
            save(f"pit_audit_{k}", T)
            LOG.table(T.head(25).astype(str).values.tolist(), list(T.columns), title=k)

    # §48 USABLE_START_DATE — 커버리지만 본다 (수익률 미열람)
    m = (E.assign(month=pd.to_datetime(E["available_at"]) + pd.offsets.MonthEnd(0))
         .groupby("month", observed=True)
         .agg(n=("stage", "size"), stages=("stage", "nunique"),
              biz=("supplier_bizno", lambda s: s.notna().sum())).reset_index())
    stable = m[(m["stages"] >= 3) & (m["n"] >= max(50, int(m["n"].median() * 0.25)))]
    usable = None
    if len(stable):
        first = stable["month"].min()
        usable = (pd.Timestamp(first) + pd.DateOffset(months=CFG.WARMUP_MONTHS)
                  + pd.offsets.MonthEnd(0))
        LOG.ok(f"데이터 안정 개시: {first:%Y-%m} → warm-up {CFG.WARMUP_MONTHS}개월 후 "
               f"USABLE_START_DATE 후보 = {usable:%Y-%m-%d}")
    else:
        LOG.warn("안정 구간을 찾지 못했습니다 — DATA_BLOCKED 후보(§96)")
    save("pit_monthly_coverage", m)
    write_json(os.path.join(CFG.AUDIT_DIR, "usable_start_candidate.json"),
               {"usable_start_date": (str(usable.date()) if usable is not None else None),
                "first_stable_month": (str(stable["month"].min().date()) if len(stable) else None),
                "warmup_months": CFG.WARMUP_MONTHS, "basis": "데이터 커버리지만 사용(§48)"})
    save("events_pit", E)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
