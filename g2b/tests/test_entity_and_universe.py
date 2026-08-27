# -*- coding: utf-8 -*-
"""§92 — 매핑 유효기간과 생존자편향."""
import numpy as np
import pandas as pd


def test_crosswalk_validity_date():
    """현재 stock_code 를 과거/미래로 소급하면 안 된다 (§14)."""
    from entity.dart_crosswalk import build_crosswalk, attach_stock_code
    prof = pd.DataFrame({"corp_code": ["C1"], "corp_name": ["테스트"],
                         "stock_code": ["111111"], "bizr_no": ["1112223334"]})
    lh = pd.DataFrame({"stock_code": ["111111"], "listing_date": ["2010-01-01"],
                       "delisting_date": ["2020-06-30"]})
    cw = build_crosswalk(prof, listing_history=lh)
    ev = pd.DataFrame({"supplier_bizno": ["1112223334"] * 3,
                       "available_at": pd.to_datetime(["2009-01-01", "2015-01-01",
                                                       "2024-01-01"]),
                       "amount": [1.0, 1.0, 1.0]})
    out = attach_stock_code(ev, cw)
    assert pd.isna(out["stock_code"].iloc[0]), "상장 전에 종목코드가 붙었습니다"
    assert out["stock_code"].iloc[1] == "111111"
    assert pd.isna(out["stock_code"].iloc[2]), "상장폐지 후에 종목코드가 붙었습니다"
    assert out["map_type"].tolist() == ["OUT_OF_VALIDITY", "EXACT_ID", "OUT_OF_VALIDITY"]


def test_no_fuzzy_auto_confirm():
    """상호 유사도만으로 매핑을 확정하면 안 된다 (§13)."""
    from entity.dart_crosswalk import build_crosswalk, name_candidates, attach_stock_code
    prof = pd.DataFrame({"corp_code": ["C1"], "corp_name": ["(주)합성전자"],
                         "stock_code": ["111111"], "bizr_no": ["1112223334"]})
    cw = build_crosswalk(prof, listing_history=pd.DataFrame(
        {"stock_code": ["111111"], "listing_date": ["2000-01-01"], "delisting_date": [None]}))
    cand = name_candidates(pd.Series(["합성전자 주식회사"]), cw)
    assert len(cand) >= 1 and cand["method"].iloc[0] == "NAME_CANDIDATE"
    # 상호만 같고 사업자번호가 다른 이벤트는 절대 매핑되지 않는다
    ev = pd.DataFrame({"supplier_bizno": ["9999999999"], "supplier_nm": ["합성전자 주식회사"],
                       "available_at": pd.to_datetime(["2020-01-01"]), "amount": [1.0]})
    out = attach_stock_code(ev, cw)
    assert pd.isna(out["stock_code"].iloc[0])


def test_delisted_stock_retained(world):
    """상장폐지 종목이 과거 패널에서 사라지면 안 되고 -100% 가 반영되어야 한다 (§57)."""
    from collectors.synthetic import build_market
    M = build_market(world)["panel"]
    assert M["delisted"].any(), "합성 시장에 상장폐지 종목이 없습니다"
    dl = M[M["delisted"]]
    assert (dl["ret"] == -1.0).all(), "상장폐지 손실이 -100% 로 반영되지 않았습니다"
    # 폐지 종목도 폐지 이전 기간에는 패널에 존재해야 한다
    code = dl["stock_code"].iloc[0]
    hist = M[M["stock_code"] == code]
    assert len(hist) > 1, "폐지 종목의 과거 관측이 삭제되었습니다(생존자편향)"


def test_procurement_observable_not_retroactive(events, months):
    """현재 조달 참여기업 명단을 과거에 소급하면 안 된다 (§50)."""
    from backtest.universe import procurement_observable
    o = procurement_observable(events, months)
    first_evt = (events[events["stage"].isin(["AWARD", "CONTRACT"])]
                 .dropna(subset=["stock_code"])
                 .groupby("stock_code")["available_at"].min())
    j = o.merge(first_evt.rename("first").reset_index(), on="stock_code")
    assert (j["month"] >= (pd.to_datetime(j["first"]) + pd.offsets.MonthEnd(0))).all()


def test_attach_stock_code_preserves_rows_and_amounts():
    """crosswalk 다중 매칭이 이벤트 행을 늘려 금액을 중복 계상하면 안 된다."""
    from entity.dart_crosswalk import attach_stock_code
    cw = pd.DataFrame({"bizr_no": ["1112223334", "1112223334", "5556667778"],
                       "stock_code": ["111111", "222222", "555555"],
                       "valid_from": pd.to_datetime(["2000-01-01"] * 3),
                       "valid_to": [pd.NaT] * 3,
                       "mapping_type": ["EXACT_ID", "VERIFIED_MANUAL", "EXACT_ID"],
                       "confidence": [1.0, 0.95, 1.0]})
    ev = pd.DataFrame({"supplier_bizno": ["1112223334", "5556667778", "9999999999"],
                       "available_at": pd.to_datetime(["2020-01-01"] * 3),
                       "amount": [100.0, 50.0, 25.0]})
    out = attach_stock_code(ev, cw)
    assert len(out) == len(ev), "행이 늘어났습니다 — 낙찰금액 중복 계상 위험"
    assert out["amount"].sum() == ev["amount"].sum()
    assert out["stock_code"].tolist()[:2] == ["111111", "555555"]
