# -*- coding: utf-8 -*-
"""§92 — 미래정보가 신호에 들어가지 않는지 (누수 회귀 고정)."""
import numpy as np
import pandas as pd
import pytest


def test_no_future_award_in_bid_signal(events, months):
    """입찰 시점 신호가 그 이후에야 알려진 낙찰을 보면 안 된다 (§7)."""
    from features.government_demand import preaward_ladder, PRE_AWARD_STAGES
    lad = preaward_ladder(events)
    used = set(events[events["stage"].isin(PRE_AWARD_STAGES)]["opportunity_id"])
    assert set(lad["opportunity_id"]) <= used
    # 사전단계 계단함수 어디에도 AWARD/CONTRACT 단계가 섞이면 안 된다
    assert set(lad["stage"].unique()) <= set(PRE_AWARD_STAGES)


def test_demand_panel_never_uses_winner(events, months):
    """정부수요는 winner 를 보기 전 정보로만 만들어져야 한다 (§20)."""
    from features.government_demand import demand_panel
    P, lad = demand_panel(events, months)
    # 낙찰만 있고 사전단계가 없는 opportunity 는 수요에 기여하지 않는다
    only_award = (events.groupby("opportunity_id")["stage"]
                  .agg(lambda s: set(s) <= {"AWARD", "CONTRACT"}))
    bad = set(only_award[only_award].index) & set(lad["opportunity_id"])
    assert not bad, f"낙찰만 있는 건이 수요에 들어갔습니다: {list(bad)[:3]}"


def test_no_future_contract_revision(events):
    """시점 t 에는 그때까지 알려진 리비전만 보여야 한다 (§40 §6 CLASS B)."""
    from pit.revisions import assign_revisions, effective_at
    c = events[events["stage"] == "CONTRACT"]
    r = assign_revisions(c, ["service", "doc_id"])
    t = pd.Timestamp("2020-06-30")
    eff = effective_at(r, t, ["service", "doc_id"])
    assert (eff["valid_from"] <= t).all()
    assert (eff["valid_to"].isna() | (eff["valid_to"] > t)).all()
    # 같은 문서가 한 시점에 두 판본으로 유효할 수 없다
    assert not eff.duplicated(subset=["service", "doc_id"]).any()


def test_no_future_dart_financial():
    """매출 분모는 filing_timestamp <= signal_timestamp 인 것만 (§58)."""
    from features.win_features import add_size_normalization
    W = pd.DataFrame({"stock_code": ["A"] * 4,
                      "month": pd.to_datetime(["2020-01-31", "2020-03-31", "2020-06-30",
                                               "2020-12-31"]),
                      "award_amt_12m": [100.0] * 4, "award_amt_3m": [10.0] * 4,
                      "contract_amt_12m": [50.0] * 4})
    sales = pd.DataFrame({"stock_code": ["A", "A"],
                          "filing_ts": pd.to_datetime(["2020-03-20", "2020-11-15"]),
                          "revenue": [1000.0, 2000.0]})
    out = add_size_normalization(W, None, sales)
    got = out.set_index("month")["pit_revenue"]
    assert pd.isna(got.loc["2020-01-31"]), "접수 전 재무를 썼습니다"
    assert got.loc["2020-03-31"] == 1000.0
    assert got.loc["2020-06-30"] == 1000.0, "아직 공개 안 된 11월 재무를 6월에 썼습니다"
    assert got.loc["2020-12-31"] == 2000.0


def test_forward_return_is_next_month(events):
    """신호월 t 는 t+1 월 수익률과 매칭되어야 한다 (§53 T+1)."""
    from backtest.portfolio import attach_forward_return
    from core import config as CFG
    if CFG.future_return_lock():
        pytest.skip("FUTURE_RETURN_LOCK 상태 — 09 동결 후에만 검사 가능")
    F = pd.DataFrame({"stock_code": ["A"] * 3,
                      "month": pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"])})
    M = pd.DataFrame({"stock_code": ["A"] * 4,
                      "month": pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31",
                                               "2024-04-30"]),
                      "ret": [.01, .02, .03, .04]})
    X = attach_forward_return(F, M)
    assert X["fwd_ret_1m"].tolist() == [0.02, 0.03, 0.04]


def test_future_return_lock_blocks_when_unfrozen(monkeypatch):
    """사전등록 전에는 미래수익률 접근이 예외로 막혀야 한다 (§1.1)."""
    from core import config as CFG
    monkeypatch.setenv("G2B_FORCE_LOCK", "1")
    with pytest.raises(PermissionError):
        CFG.assert_returns_unlocked("테스트")
