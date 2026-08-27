# -*- coding: utf-8 -*-
"""발주계획현황서비스 (공공데이터포털 15129462) — 조달대상·예산액·발주예정시기·발주방법·발주기관.

공식 메타데이터 시간범위 2004-12~. 단 '발주계획이 없는 입찰·계약도 존재'한다고 명시되어 있으므로
연결 실패를 사건 실패로 간주하지 않는다(§2.F).
이 단계는 winner 를 보기 전 정보라 §20 외생적 정부수요의 최선행 원천이다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from collectors.base import ServiceSpec, collect_service, stamp_stage
# ── /PACKAGE IMPORTS ──

SPEC_ORDER_PLAN = ServiceSpec(
    service="order_plan", portal_id="15129462", path="OrderPlanSttusService", stage="PLAN",
    operations={"물품": "getOrderPlanSttusListThng", "공사": "getOrderPlanSttusListCnstwk",
                "용역": "getOrderPlanSttusListServc", "외자": "getOrderPlanSttusListFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="BUDGET", official_range="2004-12~",
    fieldmap={
        "doc_id": ["orderPlanNo", "planNo", "ordrPlanNo", "bizNo", "orderPlanSno", "sno"],
        "doc_seq": ["orderPlanOrd", "chgOrd", "ord"],
        "title": ["bizNm", "prdctNm", "orderPlanNm", "cnstwkNm", "servcNm", "bizNmKor"],
        "agency_cd": ["orderInsttCd", "ntceInsttCd", "insttCd"],
        "agency_nm": ["orderInsttNm", "ntceInsttNm", "insttNm"],
        "demand_agency_cd": ["dminsttCd", "demandInsttCd"],
        "demand_agency_nm": ["dminsttNm", "demandInsttNm"],
        "category_cd": ["prdctClsfcNo", "clsfcNo", "cnstwkKindCd", "servcKindCd"],
        "category_nm": ["prdctClsfcNoNm", "clsfcNoNm", "cnstwkKindNm", "servcKindNm", "bsnsDivNm"],
        "amount": ["asignBdgtAmt", "bdgtAmt", "orderPlanAmt", "totlAsignBdgtAmt", "sumAmt"],
        "method": ["cntrctMthNm", "orderMthNm", "cntrctCnclsMthdNm", "bidMethdNm"],
        "region_limit": ["rgnLmtNm", "prtcptPsblRgnNm"],
        "event_time": ["orderPrearngMt", "orderPlanPrearngMt", "orderPrearngDt", "rgstDt", "regDt"],
        "source_published_at": ["rgstDt", "regDt", "inputDt", "bsnsRgstDt"],
        "status_raw": ["orderPlanSttusNm", "sttusNm", "chgRsn"],
    },
    notes="발주예정시기(orderPrearngMt)는 'YYYYMM' 수준인 경우가 많다 → event_time 은 월 정밀도.")


def collect_order_plan(start: str, end: str, **kw):
    D, A = collect_service(SPEC_ORDER_PLAN, start, end, **kw)
    return (stamp_stage(D, "PLAN") if len(D) else D), A
