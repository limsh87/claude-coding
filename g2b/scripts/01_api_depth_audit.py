#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""01 — API 백필 감사 (§5).

메타데이터에 적힌 시간범위를 믿고 바로 전체수집하지 않는다.
표본기간을 호출해 실제 데이터 존재 여부를 '측정'한다.
특히 낙찰 API 는 공식 시간범위가 사실상 '실시간' 표기이므로 historical depth 를 직접 잰다.
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from collectors import order_plan, prespec, bid, award, contract, process
from collectors.base import collect_service, fetch_window, windows, FieldMap
from core.http import RawStore, report_http

PROBE_YEARS = [1995, 2000, 2005, 2010, 2015, 2020, 2023, 2024, 2025, 2026]
SPECS = {"order_plan": order_plan.SPEC_ORDER_PLAN, "prespec": prespec.SPEC_PRESPEC,
         "bid": bid.SPEC_BID_NOTICE, "award": award.SPEC_AWARD_INFO,
         "contract": contract.SPEC_CONTRACT, "process": process.SPEC_PROC_BID}


def probe_one(spec, year: int) -> dict:
    store = RawStore(spec.service)
    op = list(spec.operations.values())[0]
    w0 = pd.Timestamp(f"{year}-06-01")
    w1 = w0 + pd.offsets.MonthEnd(0)
    try:
        rows, info = fetch_window(spec, op, w0, w1, store, max_pages=1)
    except Exception as e:                                     # noqa: BLE001
        return {"연도": year, "건수": 0, "오류": f"{type(e).__name__}: {e}"[:60]}
    fm = FieldMap(spec.fieldmap)
    D = fm.apply(rows) if rows else pd.DataFrame()
    cov = {}
    for k in ("doc_id", "amount", "event_time", "supplier_bizno", "expected_price"):
        if k in spec.fieldmap:
            cov[k] = (float(D[k].notna().mean()) if len(D) and k in D.columns else 0.0)
    return {"연도": year, "건수": len(rows), "총건수(API보고)": info.get("total"),
            "캐시": info.get("from_cache", 0), "신규": info.get("fetched", 0),
            "메시지": str(info.get("msg", ""))[:40],
            "오류": ";".join(map(str, info.get("errors", [])))[:60],
            **{f"cov_{k}": v for k, v in cov.items()}}


def main() -> int:
    header("01 API 백필 감사", "§5 — 메타데이터를 믿지 않고 실측한다")
    CFG.ensure_dirs()
    if CFG.RUN_MODE == "SMOKE":
        LOG.warn("SMOKE 모드입니다 — 실제 API 를 호출하지 않습니다. "
                 "실측 감사는 FULL 모드에서 DATA_GO_KR_SERVICE_KEY 와 함께 실행하십시오.")
    if not CFG.have_key("datagokr") and CFG.RUN_MODE != "CACHED":
        LOG.warn("DATA_GO_KR_SERVICE_KEY 가 없습니다 — 실측 불가. "
                 "환경변수를 설정한 뒤 다시 실행하십시오(§4).")
    all_rows = []
    for name, spec in SPECS.items():
        LOG.info(f"[{name}] {spec.portal_id} — 공식표기 시간범위: {spec.official_range or '미상'}")
        rows = [probe_one(spec, y) for y in PROBE_YEARS]
        T = pd.DataFrame(rows)
        T.insert(0, "API", name)
        all_rows.append(T)
        LOG.table(T.astype(str).values.tolist(), list(T.columns), title=f"{name} 실측")
    A = pd.concat(all_rows, ignore_index=True)
    save("api_depth_probe", A)

    ok = A[A["건수"] > 0]
    summary = []
    for name, g in A.groupby("API"):
        gg = g[g["건수"] > 0]
        summary.append({"API": name, "포털ID": SPECS[name].portal_id,
                        "공식표기": SPECS[name].official_range or "미상",
                        "최초 실측연도": int(gg["연도"].min()) if len(gg) else None,
                        "마지막 실측연도": int(gg["연도"].max()) if len(gg) else None,
                        "실측 건수합": int(g["건수"].sum()),
                        "사용가능": "YES" if len(gg) else "NO_DATA"})
    S = pd.DataFrame(summary)
    save("api_depth_summary", S)
    LOG.table(S.astype(str).values.tolist(), list(S.columns), title="§5 API 실측 요약")
    usable = S[S["사용가능"] == "YES"]["최초 실측연도"]
    if len(usable):
        LOG.ok(f"제안 USABLE_START (모든 핵심 API 가 살아있는 최초 연도): {int(usable.max())}. "
               f"최종 확정은 03/09 스크립트에서 커버리지만 보고 정합니다(§48).")
    else:
        LOG.warn("실측된 데이터가 없습니다 → FINAL_DECISION 은 DATA_BLOCKED 후보입니다(§96).")
    report_http()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
