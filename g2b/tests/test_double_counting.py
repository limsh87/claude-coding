# -*- coding: utf-8 -*-
"""§92 — 이중계산 금지 (§8 §11 §16)."""
import numpy as np
import pandas as pd


def test_bid_revision_not_double_counted():
    """원공고 100억 → 수정공고 100억 이면 신규수요는 0 이어야 한다 (§8)."""
    from pit.revisions import assign_revisions, amount_increments
    d = pd.DataFrame({"doc_id": ["A", "A", "B", "B"],
                      "available_at": pd.to_datetime(["2024-01-05", "2024-01-20",
                                                      "2024-02-01", "2024-03-01"]),
                      "amount": [100e8, 100e8, 100e8, 120e8]})
    r = amount_increments(assign_revisions(d, ["doc_id"]), ["doc_id"], "amount")
    a = r[r["doc_id"] == "A"]["amount_increment"].tolist()
    b = r[r["doc_id"] == "B"]["amount_increment"].tolist()
    assert a == [100e8, 0.0], f"동일금액 수정공고가 중복 계상됨: {a}"
    assert b == [100e8, 20e8], f"증액분만 계상되어야 함: {b}"
    assert r["amount_increment"].sum() == 220e8


def test_plan_bid_contract_not_triple_counted(events):
    """PLAN+PRESPEC+BID+AWARD+CONTRACT 단순합산이 아니라 증분합이어야 한다 (§11)."""
    from graph.lifecycle import stage_ladder, double_count_audit
    dc = double_count_audit(events)
    naive = float(dc.loc[dc["측정"] == "전 단계 단순합산(금지된 계산)", "금액"].iloc[0])
    corr = float(dc.loc[dc["측정"] == "lifecycle 증분합(정답)", "금액"].iloc[0])
    last = float(dc.loc[dc["측정"] == "opportunity 최종 알려진 금액 합", "금액"].iloc[0])
    assert corr < naive * 0.75, "이중계상이 제거되지 않았습니다"
    assert abs(corr - last) < max(1.0, abs(last) * 1e-6), "증분합 != 최종금액합 (보존성 위반)"


def test_ladder_conservation_property(events):
    """어떤 opportunity 든 증분의 합 == 마지막으로 알려진 금액."""
    from graph.lifecycle import stage_ladder
    lad = stage_ladder(events)
    g = lad.sort_values(["opportunity_id", "available_at"]).groupby("opportunity_id")
    s = g["demand_flow"].sum()
    l = g["best_amount"].last()
    assert np.allclose(s.to_numpy(), l.to_numpy(), rtol=1e-9, atol=1.0)


def test_consortium_not_full_allocated():
    """같은 100억 계약을 참여 3사에 각각 100억씩 주면 안 된다 (§16)."""
    from entity.consortium import allocate
    e = pd.DataFrame({"amount": [100.0, 100.0, 100.0],
                      "consortium_flag": ["Y", "Y", "Y"],
                      "share_ratio": [0.5, 0.3, np.nan],
                      "award_rank": [1, 2, 3]})
    out = allocate(e, "primary")
    assert out["attributed_amount"].tolist()[:2] == [50.0, 30.0]
    assert pd.isna(out["attributed_amount"].iloc[2]), "지분불명 컨소시엄은 제외되어야 함"
    assert out["consortium_unknown_share"].tolist() == [False, False, True]
    assert out["attributed_amount"].sum() < 3 * 100.0


def test_stage_ladder_ignores_late_lower_stage(events):
    """뒤늦게 도착한 하위단계 문서가 상태를 되돌리면 안 된다."""
    from graph.lifecycle import stage_ladder
    d = pd.DataFrame({
        "opportunity_id": ["X"] * 3,
        "available_at": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
        "stage": ["BID", "AWARD", "PLAN"],
        "amount": [100.0, 90.0, 500.0]})
    lad = stage_ladder(d)
    assert "PLAN" not in lad["stage"].tolist(), "뒤늦은 PLAN 이 상태를 되돌렸습니다"
    assert lad["demand_flow"].sum() == 90.0
