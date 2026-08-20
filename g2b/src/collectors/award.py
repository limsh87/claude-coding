# -*- coding: utf-8 -*-
"""낙찰정보서비스 (15129397) — 개찰완료·최종낙찰자·개찰순위·예정가격·낙찰률·재입찰·유찰.

공식 정의상 낙찰률은 '예정가격 대비 낙찰금액' 비율이다(§2.D).
공식 메타데이터의 시간범위가 사실상 '실시간'으로만 표기되어 있으므로 실제 historical depth 를
§5 에서 직접 측정한다 — 이 서비스가 이 연구의 가장 큰 데이터 리스크다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

SPEC_AWARD_INFO = ServiceSpec(
    service="award", portal_id="15129397", path="ScsbidInfoService", stage="AWARD",
    operations={"물품": "getScsbidListSttusThng", "공사": "getScsbidListSttusCnstwk",
                "용역": "getScsbidListSttusServc", "외자": "getScsbidListSttusFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="AWARD", official_range="실시간(공식표기) → 실측 필요",
    fieldmap={
        "doc_id": ["bidNtceNo"],
        "doc_seq": ["bidNtceOrd", "ntceOrd", "opengOrd"],
        "title": ["bidNtceNm", "ntceNm"],
        "agency_cd": ["ntceInsttCd"], "agency_nm": ["ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "cnstwkKindCd", "indstrytyCd"],
        "category_nm": ["prdctClsfcNoNm", "cnstwkKindNm", "indstrytyNm"],
        "amount": ["sucsfbidAmt", "scsbidAmt", "fnlSucsfbidAmt"],
        "expected_price": ["plnprc", "presmptPrce", "prearngPrce", "estmtPrce"],
        "award_rate": ["sucsfbidRate", "scsbidRate"],
        "award_rank": ["opengRank", "sucsfbidRank", "rank"],
        "bidder_count": ["prtcptCnum", "bidwinnrCnt", "prcbdrCnt", "bidderCnt", "opengCnt"],
        "supplier_bizno": ["bizno", "bidwinnrBizno", "corpBizno", "prcbdrBizno"],
        "supplier_nm": ["bidwinnrNm", "corpNm", "prcbdrNm", "cmpnyNm"],
        "share_ratio": ["jntcontrctRt", "shareRt", "cntrctRt"],
        "consortium_flag": ["jntcontrctYn", "jntCntrctYn"],
        "method": ["cntrctCnclsMthdNm", "bidMethdNm"],
        "event_time": ["opengDt", "rlOpengDt", "scsbidDt"],
        "source_published_at": ["opengDt", "rgstDt", "rlOpengDt"],
        "status_raw": ["progrsSttusNm", "sttusNm", "rbidNo", "fnlSucsfbidYn", "rmrk"],
    },
    notes="복수예비가격/예정가격(plnprc)이 없으면 낙찰률이 죽는다 → §5 에서 보유율을 반드시 측정.")


def collect_award(start: str, end: str, **kw):
    D, A = collect_service(SPEC_AWARD_INFO, start, end, **kw)
    return (stamp_stage(D, "AWARD") if len(D) else D), A
