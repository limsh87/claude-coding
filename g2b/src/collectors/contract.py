# -*- coding: utf-8 -*-
"""계약정보서비스 (15129427) — 계약상세·변경이력·삭제이력·계약기관·수요기관·계약금액.

낙찰금액보다 최종 계약금액·변경계약이 경제적으로 더 중요한 경우가 있으므로
반드시 낙찰 데이터와 '별도 보관'한다(§2.E). 공식 시간범위 2004-07~.
변경/삭제 오퍼레이션을 함께 받아 §6 CLASS B 리비전 구간을 복원한다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

_FM = {
    "doc_id": ["cntrctNo", "cntrctRefNo", "cntrctInfoNo"],
    "doc_seq": ["cntrctChgOrd", "chgOrd", "cntrctOrd"],
    "title": ["cntrctNm", "prdctNm", "bizNm"],
    "agency_cd": ["cntrctInsttCd", "insttCd"], "agency_nm": ["cntrctInsttNm", "insttNm"],
    "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
    "category_cd": ["prdctClsfcNo", "clsfcNo", "cnstwkKindCd"],
    "category_nm": ["prdctClsfcNoNm", "clsfcNoNm", "cnstwkKindNm"],
    "amount": ["totlCntrctPrce", "cntrctPrce", "thtmCntrctPrce", "cntrctAmt"],
    "supplier_bizno": ["bizno", "corpBizno", "cntrctCorpBizno"],
    "supplier_nm": ["corpNm", "cntrctCorpNm", "cmpnyNm"],
    "share_ratio": ["jntcontrctRt", "shareRt"], "consortium_flag": ["jntcontrctYn"],
    "method": ["cntrctMthNm", "cntrctCnclsMthdNm"],
    "link_bid_no": ["bidNtceNo", "ntceNo"],
    "event_time": ["cntrctCnclsDate", "cntrctDate", "cntrctCnclsDt"],
    "source_published_at": ["rgstDt", "cntrctCnclsDate", "inputDt"],
    "status_raw": ["cntrctSttusNm", "chgRsn", "dltRsn", "sttusNm"],
}

SPEC_CONTRACT = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품": "getCntrctInfoListThng", "공사": "getCntrctInfoListCnstwk",
                "용역": "getCntrctInfoListServc", "외자": "getCntrctInfoListFrgcpt"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", official_range="2004-07~", fieldmap=_FM,
    notes="계약금액은 총계약금액(totlCntrctPrce)과 금차계약금액(thtmCntrctPrce)이 다르다 — 총액 우선.")

# 변경계약 / 삭제계약 — §40 증액·감액·취소·삭제 구분의 원천
SPEC_CHANGE = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품변경": "getCntrctInfoListThngChgCntrct", "공사변경": "getCntrctInfoListCnstwkChgCntrct",
                "용역변경": "getCntrctInfoListServcChgCntrct"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_FM, notes="계약 변경이력(CLASS B).")

SPEC_DELETE = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품삭제": "getCntrctInfoListThngDlt", "공사삭제": "getCntrctInfoListCnstwkDlt",
                "용역삭제": "getCntrctInfoListServcDlt"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_FM, notes="계약 삭제이력(CLASS B).")


def collect_contract(start: str, end: str, include_changes: bool = True, **kw):
    import pandas as pd
    D, A = collect_service(SPEC_CONTRACT, start, end, **kw)
    Ds = [stamp_stage(D, "CONTRACT")] if len(D) else []
    As = [A]
    if include_changes:
        for sp, tag in ((SPEC_CHANGE, "CHG"), (SPEC_DELETE, "DLT")):
            d, a = collect_service(sp, start, end, **kw)
            if len(d):
                d = stamp_stage(d, "CONTRACT")
                d["status_raw"] = d["status_raw"].fillna("").astype(str) + f"|{tag}"
                Ds.append(d)
            As.append(a)
    out = pd.concat(Ds, ignore_index=True) if Ds else D
    return out, pd.concat(As, ignore_index=True)
