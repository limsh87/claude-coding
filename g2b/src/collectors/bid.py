# -*- coding: utf-8 -*-
"""입찰공고정보서비스 (15129394) — 공고·기초금액·면허제한·참가가능지역·변경이력.

공식 메타데이터 시간범위 1995-10~ 로 표기되어 있으나 그대로 믿지 않고 §5 실측한다.
ntceKindNm(공고종류: 일반/변경/재공고/취소)이 §8 리비전 처리의 입력이다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

SPEC_BID_NOTICE = ServiceSpec(
    service="bid", portal_id="15129394", path="BidPublicInfoService", stage="BID",
    operations={"물품": "getBidPblancListInfoThng", "공사": "getBidPblancListInfoCnstwk",
                "용역": "getBidPblancListInfoServc", "외자": "getBidPblancListInfoFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="EST", official_range="1995-10~ (공식표기)",
    fieldmap={
        "doc_id": ["bidNtceNo"],
        "doc_seq": ["bidNtceOrd", "ntceOrd"],
        "title": ["bidNtceNm", "ntceNm"],
        "agency_cd": ["ntceInsttCd"], "agency_nm": ["ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "pubPrcrmntClsfcNo", "cnstwkKindCd", "indstrytyCd"],
        "category_nm": ["prdctClsfcNoNm", "pubPrcrmntClsfcNoNm", "cnstwkKindNm", "indstrytyNm"],
        "amount": ["presmptPrce", "bdgtAmt", "asignBdgtAmt", "estmtPrce", "baseAmt"],
        "expected_price": ["presmptPrce", "estmtPrce"],
        "method": ["cntrctCnclsMthdNm", "bidMethdNm", "ntceKindNm"],
        "region_limit": ["prtcptPsblRgnNm", "rgnLmtBidLocplcJdgmBssCd"],
        "license_req": ["indstrytyLmtYn", "lcnsLmtNm", "indstrytyNm"],
        "event_time": ["bidNtceDt", "ntceDt", "rgstDt"],
        "source_published_at": ["bidNtceDt", "rgstDt", "ntceDt"],
        "status_raw": ["ntceKindNm", "bidNtceSttusNm", "rbidPermsnYn", "chgNtceRsn"],
        "link_prespec_no": ["bfSpecRgstNo", "refNo"],
        "link_plan_no": ["orderPlanNo", "planNo"],
    },
    notes="ntceKindNm 이 '변경공고/재공고/취소공고' 를 알려준다 → §8 상태변수 + 증분 처리의 입력.")


def collect_bid(start: str, end: str, **kw):
    D, A = collect_service(SPEC_BID_NOTICE, start, end, **kw)
    return (stamp_stage(D, "BID") if len(D) else D), A
