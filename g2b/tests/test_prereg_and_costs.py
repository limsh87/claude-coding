# -*- coding: utf-8 -*-
"""사전등록 동결·비용·통계의 회귀 고정."""
import json
import os

import numpy as np
import pandas as pd
import pytest


def test_prereg_freeze_and_tamper(tmp_path, monkeypatch):
    """동결 → 잠금해제, 파일 변조 → 자동 재잠금 (§1.1)."""
    from core import config as CFG
    from audit import prereg
    st = CFG.prereg_status()
    if not st["frozen"]:
        pytest.skip("이 저장소는 아직 동결되지 않았습니다 (09 스크립트 미실행)")
    assert not CFG.future_return_lock()
    p = os.path.join(CFG.CONFIG_DIR, "pit_policy.yaml")
    orig = open(p, encoding="utf-8").read()
    try:
        open(p, "a", encoding="utf-8").write("\n# tamper\n")
        assert CFG.future_return_lock(), "동결 후 파일을 고쳤는데 잠금이 다시 걸리지 않았습니다"
    finally:
        open(p, "w", encoding="utf-8").write(orig)
    assert not CFG.future_return_lock()


def test_trial_ledger_has_all_candidates():
    """§77 — 후보를 전부 사전등록했는가."""
    from audit.prereg import TRIAL_CANDIDATES, build_trial_ledger
    ids = {c["id"] for c in TRIAL_CANDIDATES}
    assert {"D1", "D2", "W1", "W2", "W3", "A1", "B1", "B2", "B3",
            "R1", "R2", "R3", "R4", "C1"} <= ids
    led = build_trial_ledger()
    assert led["primary"] == "A1"
    prim = [c for c in led["candidates"] if c.get("is_primary")]
    assert len(prim) == 1, "PRIMARY 는 정확히 하나여야 한다(§78)"


def test_sell_tax_not_retroactive():
    """현재 세율을 과거에 소급하면 안 된다 (§59)."""
    from backtest.costs import sell_tax_bps
    m = pd.to_datetime(["2016-05-31", "2020-01-31", "2024-01-31", "2025-06-30"])
    v = sell_tax_bps(m, pd.Series(["KOSPI"] * 4)).tolist()
    assert v == [30.0, 25.0, 20.0, 18.0], f"세율 스케줄이 잘못되었습니다: {v}"
    assert v[0] > v[-1], "과거 세율이 현재보다 낮게 적용되었습니다"


def test_cost_is_never_zero():
    """고정 0bp 백테스트를 최종성과로 쓰지 않는다 (§59)."""
    from backtest.costs import transaction_cost
    wp = pd.Series({"A": 0.5, "B": 0.5})
    wn = pd.Series({"B": 0.5, "C": 0.5})
    c = transaction_cost(wp, wn, pd.Timestamp("2024-01-31"))
    assert c > 0.0
    assert transaction_cost(wp, wn, pd.Timestamp("2024-01-31"), multiplier=2.0) > c


def test_newey_west_matches_ols_when_iid():
    """자기상관이 없으면 NW SE 가 단순 SE 에 가까워야 한다."""
    from backtest.statistics import newey_west_t
    rng = np.random.default_rng(0)
    x = rng.normal(0.01, 0.05, 500)
    mu, se, t = newey_west_t(x)
    plain = x.std(ddof=1) / np.sqrt(len(x))
    assert abs(se - plain) / plain < 0.30


def test_bh_fdr_controls_family():
    """§78 — 후보 14개 중 '가장 좋은 하나'가 순진한 0.05 를 넘겨도 family 에서는 살아남지 못한다."""
    from backtest.statistics import bh_fdr
    # 실제 상황: 대부분 무의미하고 하나만 p=0.04. 순진하게 보면 '성공'처럼 보인다.
    pv = [0.04] + [0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    r = bh_fdr(pv, q=0.10)
    assert not r["기각(FDR)"].any(), \
        "14개 후보 중 p=0.04 하나는 BH(q=0.10) 에서 기각되지 않아야 한다(임계값 0.10/14=0.0071)"
    # 진짜로 강한 신호는 살아남는다
    r2 = bh_fdr([0.0001] + [0.6] * 13, q=0.10)
    assert r2["기각(FDR)"].sum() == 1
    # 모두 똑같이 작으면 BH 는 전부 기각한다 — 이것이 BH 의 정의대로의 동작이다
    r3 = bh_fdr([0.04] * 14, q=0.10)
    assert r3["기각(FDR)"].all()


def test_dwa_is_geometric_mean():
    """§28 — 두 축 모두 높아야 높은 점수."""
    from features.g2b_dwa import build_dwa
    n = 300
    rng = np.random.default_rng(1)
    F = pd.DataFrame({"month": pd.to_datetime(["2024-01-31"] * n),
                      "stock_code": [f"{i:06d}" for i in range(n)],
                      "D1_DS_YOY": rng.normal(0, 1, n), "W_PRIMARY": rng.normal(0, 1, n),
                      "sector": rng.choice(list("ABC"), n),
                      "mcap": np.exp(rng.normal(25, 1, n))})
    d = build_dwa(F, neutral_mode="raw")
    ok = d.dropna(subset=["G2B_DWA"])
    assert np.allclose(ok["G2B_DWA"], np.sqrt(ok["P_D"] * ok["P_W"]))
    # 한 축만 극단적으로 높은 기업이 억제되는가
    one_sided = ok[(ok["P_D"] > 0.95) & (ok["P_W"] < 0.2)]
    both = ok[(ok["P_D"] > 0.7) & (ok["P_W"] > 0.7)]
    if len(one_sided) and len(both):
        assert one_sided["G2B_DWA"].max() < both["G2B_DWA"].min()
