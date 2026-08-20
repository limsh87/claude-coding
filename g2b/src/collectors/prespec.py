# -*- coding: utf-8 -*-
"""사전규격정보서비스 (15129437) — 사전규격등록번호·사업명·배정예산액·발주기관·규격서 의견.

사전규격은 입찰공고보다 앞선 정보이므로 선행신호로 매우 중요하다(§2.B).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

SPEC_PRESPEC = ServiceSpec(
    service="prespec", portal_id="15129437", path="HrcspSsstndrdInfoService", stage="PRESPEC",
    operations={"물품": "getPublicPrcureThngInfoThng", "공사": "getPublicPrcureThngInfoCnstwk",
                "용역": "getPublicPrcureThngInfoServc", "외자": "getPublicPrcureThngInfoFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="BUDGET", official_range="사전규격 공개 개시 이후",
    fieldmap={
        "doc_id": ["bfSpecRgstNo", "prearngSpecRgstNo", "specRgstNo", "rgstNo"],
        "doc_seq": ["bfSpecRgstNoOrd", "chgOrd", "ord"],
        "title": ["prdctClsfcNoNm", "bfSpecNm", "bizNm", "cnstwkNm", "servcNm", "prdctNm"],
        "agency_cd": ["orderInsttCd", "rlDminsttCd", "ntceInsttCd"],
        "agency_nm": ["orderInsttNm", "rlDminsttNm", "ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "clsfcNo", "cnstwkKindCd"],
        "category_nm": ["prdctClsfcNoNm", "clsfcNoNm", "cnstwkKindNm"],
        "amount": ["asignBdgtAmt", "bdgtAmt", "prdctUprc", "asignBdgtAmtSum"],
        "link_bid_no": ["bidNtceNo", "refNo"],
        "event_time": ["rgstDt", "specRgstDt", "regDt"],
        "source_published_at": ["rgstDt", "regDt", "opninRgstBgnDt"],
        "status_raw": ["opninRgstClseDt", "sttusNm", "specDocNm"],
        "license_req": ["indstrytyNm", "lcnsLmtNm"],
    },
    notes="규격서 의견(opninRgstClseDt)은 의견수렴 마감 — 입찰공고 시점의 선행지표.")


def collect_prespec(start: str, end: str, **kw):
    D, A = collect_service(SPEC_PRESPEC, start, end, **kw)
    return (stamp_stage(D, "PRESPEC") if len(D) else D), A
