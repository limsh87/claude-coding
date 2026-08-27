#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전체 파이프라인 순차 실행 (§97 연구 우선순위 순서 — 순서를 바꾸지 않는다)."""
from _common import *                                          # noqa: F401,F403
import subprocess
import sys
import time

STEPS = ["01_api_depth_audit.py", "02_collect_history.py", "03_build_pit_ledger.py",
         "04_build_company_crosswalk.py", "05_build_lifecycle.py", "06_build_demand_graph.py",
         "07_build_capability.py", "08_build_features.py", "09_freeze_preregistration.py",
         "10_backtest_primary.py", "11_mechanism_tests.py", "12_robustness.py",
         "13_generate_report.py"]


def main() -> int:
    header("전체 실행", "§97 — 1 API depth → 2 PIT → 3 매핑 → 4 lifecycle → 5 capability → "
                       "6 TAM → 7 Demand → 8 Win → 9 Alignment → 10 Future return")
    here = os.path.dirname(os.path.abspath(__file__))
    only = sys.argv[1:] or None
    rows = []
    for s in STEPS:
        if only and not any(s.startswith(o) for o in only):
            continue
        t0 = time.time()
        LOG.banner(f"▶ {s}")
        r = subprocess.run([sys.executable, os.path.join(here, s)], cwd=here)
        rows.append({"단계": s, "코드": r.returncode, "초": round(time.time() - t0, 1)})
        if r.returncode != 0:
            LOG.err(f"{s} 실패(코드 {r.returncode}) — 이후 단계를 중단합니다.")
            break
    LOG.table([[r["단계"], r["코드"], r["초"]] for r in rows], ["단계", "종료코드", "소요(초)"],
              ["l", "r", "r"], title="실행 요약")
    return 0 if all(r["코드"] == 0 for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
