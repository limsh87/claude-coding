#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""07 — 기업 역량 Capability(i,c,t) (§17 §18 §19)."""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from features.capability import build_capability, agency_capability, capability_persistence


def main() -> int:
    header("07 Capability", "§17 §18 §19 — 과거 수주만 사용, 억지 추론 금지")
    L = require("events_lifecycle", "05_build_lifecycle.py")
    months = months_for_research()
    C = build_capability(L, months)
    if not len(C):
        LOG.err("capability 를 만들 수 없습니다 (낙찰 관측 없음).")
        return 1
    save("capability", C)
    save("agency_capability", agency_capability(L, months))
    chk = C.groupby(["stock_code", "month"], observed=True)["capability"].sum().dropna()
    LOG.info(f"capability 합=1 검증: min {chk.min():.6f} max {chk.max():.6f}")
    P = capability_persistence(C)
    if len(P):
        LOG.table(P.astype(str).values.tolist(), list(P.columns),
                  title="capability 지속성 (지속성이 없으면 '잘하는 영역' 개념이 무너진다)")
        save("capability_persistence", P)
    LOG.info(f"§19 warm-up 충족 비중 {C['warmed_up'].mean() * 100:.1f}% — "
             f"미충족 기업의 NEW_* 지표는 계산하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
