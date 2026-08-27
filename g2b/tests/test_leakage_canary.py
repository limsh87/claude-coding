# -*- coding: utf-8 -*-
"""§93 — 누수 카나리아. 이 테스트가 통과하지 못하면 본 백테스트 실행 금지."""
import numpy as np
import pandas as pd
import pytest


def test_canary_clean_data_has_no_violation(events):
    from audit.leakage_test import scan_events
    v = scan_events(events)
    assert len(v) == 0, f"정상 데이터에서 위반이 검출되었습니다: {v.to_dict('records')}"


def test_canary_detects_injected_future_award(events):
    """의도적으로 미래 낙찰정보를 t 이전에 삽입하면 탐지기가 반드시 실패시켜야 한다."""
    from audit.leakage_test import scan_events, make_canary_events
    poisoned = make_canary_events(events, n_inject=50)
    v = scan_events(poisoned)
    assert len(v) > 0, "삽입된 미래정보를 탐지하지 못했습니다 — 백테스트 실행 금지 조건"
    assert int(v["위반건수"].sum()) >= 50


def test_gate_raises_when_detector_blind(events, monkeypatch):
    """탐지기가 눈이 멀면 gate 가 예외를 던져야 한다 (fail-closed)."""
    import audit.leakage_test as LT
    monkeypatch.setattr(LT, "scan_events", lambda E: pd.DataFrame(
        columns=["검사", "위반건수", "설명"]))
    with pytest.raises(LT.LeakageDetected):
        LT.gate_or_raise(events)


def test_gate_passes_on_healthy_pipeline(events):
    from audit.leakage_test import gate_or_raise
    tab = gate_or_raise(events)
    assert tab["판정"].tolist() == ["✔", "✔"]


def test_class_c_field_blocked():
    """CLASS C 필드를 팩터에 넣으면 즉시 막혀야 한다 (§6.1)."""
    from pit.timestamps import assert_pit_safe, field_class
    assert field_class("무엇이든_등록되지_않은_필드") == "C"
    with pytest.raises(PermissionError):
        assert_pit_safe(["award_amt_12m", "future_revenue"], "test")
    with pytest.raises(PermissionError):
        assert_pit_safe(["fwd_ret_1m"], "test")
    assert_pit_safe(["G2B_DWA", "D1_DS_YOY", "amount"], "test")


def test_harness_detects_planted_alpha(world, events, months):
    """하네스가 '있는 알파'를 실제로 찾아내는지 (둔감하지 않은지) 확인한다."""
    from core import config as CFG
    if CFG.future_return_lock():
        pytest.skip("FUTURE_RETURN_LOCK 상태")
    from collectors.synthetic import build_market
    from backtest.statistics import information_coefficient
    from backtest.portfolio import attach_forward_return
    rng = np.random.default_rng(7)
    sig = (events[events["stage"] == "AWARD"].dropna(subset=["stock_code"])
           .assign(month=lambda d: pd.to_datetime(d["available_at"]) + pd.offsets.MonthEnd(0))
           .groupby(["stock_code", "month"], as_index=False)["amount"].sum()
           .rename(columns={"amount": "s"}))
    mk = build_market(world, alpha_strength=0.05, signal=sig)["panel"]
    F = attach_forward_return(sig, mk)
    ic, _ = information_coefficient(F, "s", "fwd_ret_1m")
    assert len(ic) and float(ic["IC_t"].iloc[0]) > 3.0, \
        "심어놓은 알파를 하네스가 찾지 못했습니다 — 둔감한 하네스입니다"


def test_null_world_gives_null_result(world, events, months):
    """알파가 없는 세계에서 유의한 알파가 나오면 그것은 하네스의 버그다."""
    from core import config as CFG
    if CFG.future_return_lock():
        pytest.skip("FUTURE_RETURN_LOCK 상태")
    from collectors.synthetic import build_market
    from backtest.statistics import information_coefficient
    from backtest.portfolio import attach_forward_return
    sig = (events[events["stage"] == "AWARD"].dropna(subset=["stock_code"])
           .assign(month=lambda d: pd.to_datetime(d["available_at"]) + pd.offsets.MonthEnd(0))
           .groupby(["stock_code", "month"], as_index=False)["amount"].sum()
           .rename(columns={"amount": "s"}))
    mk = build_market(world, alpha_strength=0.0)["panel"]
    F = attach_forward_return(sig, mk)
    ic, _ = information_coefficient(F, "s", "fwd_ret_1m")
    assert len(ic)
    assert abs(float(ic["IC_t"].iloc[0])) < 3.0, \
        "알파 없는 세계에서 유의한 IC 가 나왔습니다 — 누수 또는 하네스 버그"
