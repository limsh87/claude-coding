# -*- coding: utf-8 -*-
"""OpenDART 수집 — 회사개황(bizr_no ↔ stock_code)과 PIT 재무.

§3.1 회사개황 API 는 corp_code / stock_code / bizr_no / jurir_no / corp_name 을 함께 준다.
     → 사업자등록번호를 이용한 G2B 업체 ↔ DART 법인 연결을 최우선으로 한다(§13).
§58 매출 분모는 반드시 filing_timestamp <= signal_timestamp 인 최신 재무제표만 쓴다.
     DART 의 공개시각은 결산일이 아니라 접수일자(rcept_no 앞 8자리)다.

캐시 우선: 공용 인덱스에 이미 dart_corpcode / dart_fnltt_raw 가 있으면 재수집하지 않는다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.http import http_json, ApiError
from core.io import limiter, digits, as_ts_series, to_code6
from core.vault import get_vault
# ── /PACKAGE IMPORTS ──

import io
import os
import zipfile
import datetime as _dt
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

DART_BASE = "https://opendart.fss.or.kr/api/"


def fetch_corp_codes() -> pd.DataFrame:
    """corp_code 전체 목록. 공용 인덱스 캐시를 최우선으로 재사용한다."""
    V = get_vault()
    cached = V.get_table(CFG.SHARED_REUSE_TABLES["dart_corpcode"], scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.ok(f"공용 캐시 재사용: dart_corpcode {len(cached):,}행 (재수집 안 함)")
        return cached
    if CFG.RUN_MODE == "CACHED" or not CFG.have_key("opendart"):
        LOG.warn("OPENDART_API_KEY 없음 또는 CACHED 모드 — corp_code 를 가져올 수 없습니다.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "stock_code", "modify_date"])
    import requests
    limiter("opendart", CFG.RATE_LIMIT_QPS["opendart"]).wait()
    r = requests.get(DART_BASE + "corpCode.xml", params={"crtfc_key": CFG.OPENDART_API_KEY},
                     timeout=90)
    if r.status_code != 200 or len(r.content) < 1000:
        LOG.warn(f"corpCode 실패 HTTP {r.status_code} — {r.text[:150]}")
        return pd.DataFrame(columns=["corp_code", "corp_name", "stock_code", "modify_date"])
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xml = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    rows = [{c: (e.findtext(c) or "").strip()
             for c in ("corp_code", "corp_name", "stock_code", "modify_date")}
            for e in root.iter("list")]
    D = pd.DataFrame(rows)
    D["stock_code"] = D["stock_code"].map(lambda s: to_code6(s) if s and s.strip() else None)
    V.put_table(CFG.SHARED_REUSE_TABLES["dart_corpcode"], D, scope="shared", domain="dart",
                source="opendart corpCode.xml")
    V.flush("shared")
    LOG.ok(f"DART corp_code {len(D):,}건 (상장 {D['stock_code'].notna().sum():,}) → 공용 인덱스 적재")
    return D


def fetch_company_profiles(corp_codes: List[str], workers: Optional[int] = None) -> pd.DataFrame:
    """회사개황 — bizr_no(사업자등록번호)를 얻는 유일한 경로. 이것이 §13 PRIMARY 매칭의 근간."""
    V = get_vault()
    name = CFG.SHARED_REUSE_TABLES["dart_company"]
    cached = V.get_table(name, scope="shared")
    have = set(cached["corp_code"].astype(str)) if cached is not None and len(cached) else set()
    todo = [c for c in dict.fromkeys(map(str, corp_codes)) if c and c not in have]
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시 재사용: dart_company_profile {len(cached):,}행, 신규 대상 {len(todo):,}건")
    if CFG.RUN_MODE == "CACHED" or not CFG.have_key("opendart"):
        todo = []
    rows: List[dict] = []
    if todo:
        from concurrent.futures import ThreadPoolExecutor

        def _one(cc: str) -> Optional[dict]:
            js, meta = http_json(DART_BASE + "company.json",
                                 {"crtfc_key": CFG.OPENDART_API_KEY, "corp_code": cc},
                                 source="opendart", tries=3)
            if not isinstance(js, dict) or js.get("status") not in ("000",):
                return None
            return {k: js.get(k) for k in ("corp_code", "corp_name", "corp_name_eng", "stock_name",
                                           "stock_code", "jurir_no", "bizr_no", "adres",
                                           "induty_code", "est_dt", "acc_mt")}

        with ThreadPoolExecutor(max_workers=workers or CFG.N_WORKERS_IO) as ex:
            for i, res in enumerate(ex.map(_one, todo)):
                if res:
                    rows.append(res)
                if (i + 1) % 500 == 0:
                    LOG.info(f"  회사개황 {i + 1:,}/{len(todo):,}")
    frames = [x for x in (cached, pd.DataFrame(rows) if rows else None) if x is not None and len(x)]
    if not frames:
        return pd.DataFrame(columns=["corp_code", "corp_name", "stock_code", "bizr_no", "jurir_no"])
    D = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["corp_code"], keep="last")
    D["bizr_no"] = D["bizr_no"].map(digits).replace("", np.nan)
    D["jurir_no"] = D["jurir_no"].map(digits).replace("", np.nan)
    D["stock_code"] = D["stock_code"].map(lambda s: to_code6(s) if pd.notna(s) and str(s).strip() else None)
    if rows:
        V.put_table(name, D, scope="shared", domain="dart", source="opendart company.json")
        V.flush("shared")
        LOG.ok(f"회사개황 {len(D):,}건 (사업자번호 보유 {D['bizr_no'].notna().sum():,}) → 공용 인덱스")
    return D


def load_pit_financials() -> pd.DataFrame:
    """PIT 매출 — 공용 인덱스의 dart_fnltt_raw 를 재사용한다.

    반환: [stock_code, fiscal_end, revenue, filing_ts]
    filing_ts = 접수일자(rcept_no 앞 8자리). 이 시각 이후에만 그 매출을 쓸 수 있다(§58).
    """
    V = get_vault()
    fs = V.get_table(CFG.SHARED_REUSE_TABLES["dart_fin"], scope="shared")
    if fs is None or not len(fs):
        LOG.warn("공용 인덱스에 dart_fnltt_raw 가 없습니다 — WIN_SALES(§26) 는 계산 불가로 표시됩니다.")
        return pd.DataFrame(columns=["stock_code", "fiscal_end", "revenue", "filing_ts"])
    d = fs.copy()
    cols = {c.lower(): c for c in d.columns}

    def pick(*names):
        for n in names:
            if n in d.columns:
                return n
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    c_code = pick("stock_code", "code", "corp_code")
    c_rev = pick("revenue", "sales", "매출액", "thstrm_amount_revenue")
    c_rcept = pick("rcept_no", "rcept", "rcp_no")
    c_fiscal = pick("fiscal_end", "bsns_year", "end_dt", "결산기")
    if c_code is None:
        LOG.warn("dart_fnltt_raw 에 종목/법인 식별자가 없습니다 — 매출 분모를 만들 수 없습니다.")
        return pd.DataFrame(columns=["stock_code", "fiscal_end", "revenue", "filing_ts"])
    out = pd.DataFrame({"stock_code": d[c_code].map(to_code6)})
    out["revenue"] = pd.to_numeric(d[c_rev], errors="coerce") if c_rev else np.nan
    out["fiscal_end"] = as_ts_series(d[c_fiscal]) if c_fiscal else pd.NaT
    if c_rcept is not None:
        out["filing_ts"] = pd.to_datetime(d[c_rcept].astype(str).str.slice(0, 8),
                                          format="%Y%m%d", errors="coerce")
    else:
        # 접수일자가 없으면 결산 후 보수적으로 90일 뒤에나 알 수 있었다고 본다.
        LOG.warn("rcept_no 가 없어 접수일자를 복원할 수 없습니다 — 결산일+90일로 보수 처리합니다(§58).")
        out["filing_ts"] = out["fiscal_end"] + pd.Timedelta(days=90)
    out = out.dropna(subset=["stock_code"]).dropna(subset=["filing_ts"])
    LOG.ok(f"PIT 재무 {len(out):,}행 (접수일자 기준) — 공용 캐시 재사용")
    return out.sort_values("filing_ts", kind="stable").reset_index(drop=True)
