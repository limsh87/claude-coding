#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09 — 사전등록 동결 (§1.1 §77 §78).

이 스크립트가 성공해야만 FUTURE_RETURN_LOCK 이 풀린다.
동결에 들어가는 데이터 기반 값은 08/03 이 '수익률을 보기 전에' 계산한 것만 쓴다.
"""
from _common import *                                          # noqa: F401,F403
from audit import prereg


def main() -> int:
    header("09 사전등록 동결", "§1.1 — 이 이후에만 미래수익률을 연다")
    emb = (read_json(os.path.join(CFG.AUDIT_DIR, "maturity_embargo_candidate.json"), {}) or {}
           ).get("maturity_embargo_days")
    usable = (read_json(os.path.join(CFG.AUDIT_DIR, "usable_start_candidate.json"), {}) or {}
              ).get("usable_start_date")
    if emb is None:
        LOG.warn("MATURITY_EMBARGO 후보가 없습니다 — 08 을 먼저 실행하는 것이 원칙입니다. "
                 "기본값 365일로 동결합니다.")
        emb = 365
    if usable is None:
        LOG.warn("USABLE_START_DATE 후보가 없습니다 — 03 을 먼저 실행하는 것이 원칙입니다.")
    rec = prereg.freeze(maturity_embargo_days=emb, usable_start_date=usable,
                        notes="01/03/08 의 커버리지·성숙분포 결과만 사용. 수익률 미열람 상태에서 동결.")
    V = prereg.verify()
    LOG.table(V.astype(str).values.tolist(), list(V.columns), title="동결 검증")
    T = prereg.ledger_table()
    LOG.table(T.astype(str).values.tolist(), list(T.columns), title="§77 시험 장부 (전 후보 사전등록)")
    LOG.ok(f"FUTURE_RETURN_LOCK = {CFG.future_return_lock()}  (False 여야 정상)")
    return 0 if not CFG.future_return_lock() else 1


if __name__ == "__main__":
    raise SystemExit(main())
