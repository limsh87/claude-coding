# -*- coding: utf-8 -*-
"""계약과정통합공개서비스 (15129459) — lifecycle 연결의 '보조원장'.

발주계획 ↕ 사전규격 ↕ 입찰공고 ↕ 낙찰 ↕ 계약 을 잇는 2순위 연결 근거다(§10).
공식 설명에서도 모든 건에 5단계가 다 존재하지는 않는다고 명시하므로
연결 실패를 사건 실패로 간주하지 않는다(§2.F).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

import pandas as pd

_LINK_FM = {
    "doc_id": ["bidNtceNo", "cntrctNo"],
    "doc_seq": ["bidNtceOrd", "cntrctChgOrd"],
    "title": ["bidNtceNm", "cntrctNm"],
    "agency_cd": ["ntceInsttCd", "cntrctInsttCd"], "agency_nm": ["ntceInsttNm", "cntrctInsttNm"],
    "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
    "category_cd": ["prdctClsfcNo", "pubPrcrmntClsfcNo"],
    "category_nm": ["prdctClsfcNoNm", "pubPrcrmntClsfcNoNm"],
    "amount": ["sucsfbidAmt", "totlCntrctPrce", "presmptPrce", "asignBdgtAmt"],
    "expected_price": ["plnprc", "presmptPrce"],
    "award_rate": ["sucsfbidRate"],
    "supplier_bizno": ["bidwinnrBizno", "bizno", "corpBizno"],
    "supplier_nm": ["bidwinnrNm", "corpNm"],
    "link_bid_no": ["bidNtceNo"], "link_contract_no": ["cntrctNo"],
    "link_plan_no": ["orderPlanNo"], "link_prespec_no": ["bfSpecRgstNo"],
    "method": ["cntrctCnclsMthdNm", "cntrctMthNm"],
    "event_time": ["bidNtceDate", "bidNtceDt", "opengDate", "cntrctCnclsDate", "rgstDt"],
    "source_published_at": ["rgstDt", "bidNtceDate", "cntrctCnclsDate"],
    "status_raw": ["ntceKindNm", "cntrctSttusNm", "progrsSttusNm"],
}

SPEC_PROC_BID = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="BID",
    operations={"공고표준": "getDataSetOpnStdBidPblancInfo"},
    date_params=("bidNtceBgnDt", "bidNtceEndDt"), date_fmt="%Y%m%d",
    amount_kind="EST", fieldmap=_LINK_FM)

SPEC_PROC_AWARD = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="AWARD",
    operations={"낙찰표준": "getDataSetOpnStdScsbidInfo"},
    date_params=("opengBgnDt", "opengEndDt"), date_fmt="%Y%m%d",
    amount_kind="AWARD", fieldmap=_LINK_FM)

SPEC_PROC_CNTRCT = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="CONTRACT",
    operations={"계약표준": "getDataSetOpnStdCntrctInfo"},
    date_params=("cntrctCnclsBgnDate", "cntrctCnclsEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_LINK_FM)

ALL_SPECS = (SPEC_PROC_BID, SPEC_PROC_AWARD, SPEC_PROC_CNTRCT)


def collect_process(start: str, end: str, **kw):
    Ds, As = [], []
    for sp in ALL_SPECS:
        d, a = collect_service(sp, start, end, **kw)
        if len(d):
            Ds.append(stamp_stage(d, sp.stage))
        As.append(a)
    out = pd.concat(Ds, ignore_index=True) if Ds else pd.DataFrame()
    return out, (pd.concat(As, ignore_index=True) if As else pd.DataFrame())
