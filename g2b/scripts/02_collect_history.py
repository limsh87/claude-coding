#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""02 — 전체 이력 수집 (§2 §4 §87).

캐시 우선. 같은 historical request 를 두 번 호출하지 않는다.
raw 는 불변으로 보존하고, 정규화 결과는 구글드라이브 **공용 인덱스**에 적재한다
(다른 전략도 그대로 재사용할 수 있는 원본/범용 정제본이기 때문).
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
import pipeline as P
from core.http import report_http, BUDGET
from core.vault import get_vault


def main() -> int:
    header("02 이력 수집", "§2 §4 §87 — 캐시 우선 · raw 불변 · 공용 인덱스 적재")
    CFG.ensure_dirs()
    E, ctx = P.load_events()
    if not len(E):
        LOG.err("수집된 이벤트가 없습니다. 키/네트워크/모드를 확인하십시오. "
                "FINAL_DECISION 은 DATA_BLOCKED 입니다(§96).")
        return 1
    save("events_raw", E)
    T = (E.groupby(["stage", "proc_type"], observed=True)
         .agg(건수=("amount", "size"), 금액합=("amount", "sum"),
              최초=("event_time", "min"), 최종=("event_time", "max")).reset_index())
    LOG.table(T.astype(str).values.tolist(), list(T.columns), title="수집 결과")
    if "collect_audit" in ctx and len(ctx["collect_audit"]):
        save("collect_audit", ctx["collect_audit"])
    BUDGET.flush()
    report_http()
    get_vault().report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
