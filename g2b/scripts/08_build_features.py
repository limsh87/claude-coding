#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""08 — 전 피처 구축 (§20~§44).

★ 여기까지가 '수익률을 보기 전' 단계다. 이 스크립트는 미래수익률을 절대 읽지 않는다.
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
import pipeline as P
from features.eligible_tam import maturity_distribution
from collectors.dart import load_pit_financials
from audit.leakage_test import scan_feature_inputs


def main() -> int:
    header("08 피처", "§20~§44 — 미래수익률 미열람 상태에서 수행")
    L = require("events_lifecycle", "05_build_lifecycle.py")
    months = months_for_research()

    md = maturity_distribution(L)
    if len(md):
        LOG.table(md.astype(str).values.tolist(), list(md.columns),
                  title="§23 단계→계약 성숙 분포 (MATURITY_EMBARGO 결정 근거)")
        save("maturity_distribution", md)
        emb = int(md["p90"].max())
        LOG.ok(f"MATURITY_EMBARGO 제안 = {emb}일 (전 단계 p90 최댓값) — "
               f"09 스크립트에서 동결합니다.")
        write_json(os.path.join(CFG.AUDIT_DIR, "maturity_embargo_candidate.json"),
                   {"maturity_embargo_days": emb, "basis": "단계별 p90 최댓값(수익률 미열람)"})
    else:
        emb = 365

    ctx = {}
    if CFG.RUN_MODE == "SMOKE":
        from collectors.synthetic import build_world, build_market
        ctx = build_world(opp_per_month=1)
        market = build_market(ctx)["panel"]
    else:
        market = P.load_market(months, ctx)
    save("market", market)
    sales = load_pit_financials()
    if len(sales):
        save("pit_sales", sales)

    feats = P.build_features(L, months, market, pit_sales=(sales if len(sales) else None),
                             maturity_days=emb)
    for k, df in feats.items():
        if isinstance(df, pd.DataFrame) and len(df):
            save(k, df)
    F = feats["company_g2b_features_monthly"]
    LOG.ok(f"피처 패널 {F.shape[0]:,}행 × {F.shape[1]}열")

    # 원천(이벤트) 컬럼과 파생 피처 컬럼을 모두 검사한다.
    # 등록되지 않은 컬럼은 자동으로 CLASS C 이므로, 새 피처를 만들면서 등급 선언을 빠뜨리면
    # 여기서 파이프라인이 멈춘다 — 그것이 이 장치의 목적이다(§6.1).
    v_src = scan_feature_inputs([c for c in L.columns if not c.startswith("_")])
    v_out = scan_feature_inputs([c for c in F.columns if not c.startswith("_")])
    if len(v_src) or len(v_out):
        LOG.err("CLASS C(PIT_UNCERTIFIED) 필드가 발견되었습니다:")
        for v in (v_src, v_out):
            if len(v):
                LOG.table(v.astype(str).values.tolist(), list(v.columns))
        LOG.err("→ 미등록 파생 피처라면 pit/timestamps.py 의 DERIVED_FEATURES 에 등급을 선언하십시오.")
        return 1
    LOG.ok("원천·파생 컬럼 모두 CLASS A/B — PIT_UNCERTIFIED 필드 없음")
    cov = (F.dropna(subset=["G2B_DWA"]).groupby("month", observed=True)["stock_code"]
           .nunique().describe())
    LOG.info(f"월별 스코어 기업수 — 중앙값 {cov['50%']:.0f}, 최소 {cov['min']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
