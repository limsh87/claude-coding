# -*- coding: utf-8 -*-
"""§92 — graph.asof 시점제약과 단계확률 학습 컷오프."""
import numpy as np
import pandas as pd
import pytest


def test_graph_asof(events, world):
    """graph.asof(t) 는 t 까지 알려진 노드·엣지만 반환해야 한다 (§7 §12)."""
    from graph.demand_graph import build_graph
    from collectors.synthetic import crosswalk_from_world
    G = build_graph(events, crosswalk_from_world(world))
    prev_n = prev_e = -1
    for t in ("2016-06-30", "2018-06-30", "2020-06-30", "2023-06-30"):
        g = G.asof(t)
        ts = pd.Timestamp(t)
        assert (pd.to_datetime(g.nodes["known_at"]) <= ts).all(), f"asof({t}) 가 미래 노드 반환"
        assert (pd.to_datetime(g.edges["known_at"]) <= ts).all(), f"asof({t}) 가 미래 엣지 반환"
        alive = set(g.nodes["node_id"])
        assert set(g.edges["src"]) <= alive and set(g.edges["dst"]) <= alive, "고아 엣지"
        assert len(g.nodes) >= prev_n and len(g.edges) >= prev_e, "asof 가 단조 증가가 아님"
        prev_n, prev_e = len(g.nodes), len(g.edges)
    assert len(G.asof("2035-01-01").nodes) == len(G.nodes)


def test_stage_probability_training_cutoff(events, months):
    """단계확률은 label_available_at <= t 인 라벨만 써야 한다 (§23)."""
    from features.eligible_tam import _labels, stage_probability, DEFAULT_MATURITY_DAYS
    lbl = _labels(events, DEFAULT_MATURITY_DAYS)
    # 라벨은 지평 도달 시점에야 확정된다
    assert (lbl["label_available_at"] > lbl["t_stage"]).all()
    sp = stage_probability(events, months, maturity_days=DEFAULT_MATURITY_DAYS)
    assert sp["p_contract"].between(0, 1).all()

    # 가장 이른 달의 확률은 '그 시점 라벨'만 반영해야 한다 → 전체표본 확률과 달라야 정상
    early = sp[sp["month"] == sp["month"].min()]["p_contract"].mean()
    late = sp[sp["month"] == sp["month"].max()]["p_contract"].mean()
    assert np.isfinite(early) and np.isfinite(late)
    # 초기에는 라벨이 거의 없어 global prior(0.5) 근처여야 한다
    assert abs(early - 0.5) < abs(late - 0.5) + 1e-9, \
        "초기 시점이 후기보다 더 확신에 차 있다면 미래 라벨을 본 것이다"


def test_stage_probability_monotone_by_stage(events, months):
    """P(계약|PLAN) < P(계약|BID) < P(계약|AWARD) 가 상식적 순서다."""
    from features.eligible_tam import stage_probability
    sp = stage_probability(events, months)
    m = sp.groupby("stage")["p_contract"].mean()
    assert m.get("PLAN", 0) <= m.get("BID", 1) + 1e-6
    assert m.get("BID", 0) <= m.get("AWARD", 1) + 1e-6


def test_lifecycle_allows_many_to_many(events):
    """1 plan → N bids 등 N:M 구조를 강제 1:1 로 접지 않아야 한다 (§9)."""
    per_opp = events.groupby("opportunity_id")["stage"].nunique()
    assert per_opp.max() >= 3, "lifecycle 이 단계를 잇지 못했습니다"
    docs = events.groupby("opportunity_id")["doc_id"].nunique()
    assert docs.max() > 1, "한 opportunity 가 여러 문서를 묶지 못했습니다"


def test_capability_shares_sum_to_one(events, months):
    """capability 는 기업별 품목 점유이므로 합이 1 이어야 한다 (§17)."""
    from features.capability import build_capability
    C = build_capability(events, months)
    s = C.groupby(["stock_code", "month"])["capability"].sum().dropna()
    assert np.allclose(s.to_numpy(), 1.0, atol=1e-9)


def test_capability_warmup_gate(events, months):
    """36M warm-up 이 없는 기업의 NEW_* 는 계산하지 않는다 (§19)."""
    from features.win_features import breadth_features
    B = breadth_features(events, months)
    if not len(B):
        pytest.skip("breadth 피처 없음")
    cold = B[~B["breadth_warmed_up"]]
    if len(cold):
        for c in ("new_agency_count", "new_category_count", "REPEAT_WIN_RATE"):
            if c in cold.columns:
                assert cold[c].isna().all(), f"warm-up 미충족 기업에 {c} 가 계산되었습니다"
