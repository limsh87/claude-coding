# -*- coding: utf-8 -*-
"""법인 이력 — 상호변경·합병·분할을 PIT 로 다룬다 (§14, §98).

핵심 금지사항:
  · 현재 기업명을 과거에 소급하지 않는다.
  · 현재 stock_code 를 과거 전체에 소급하지 않는다.
따라서 이 모듈은 '언제부터 언제까지 그 이름/코드가 유효했는가' 만 다룬다.
복원 불가능하면 복원 불가능하다고 표시한다 — 추정으로 메우지 않는다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import as_ts_series, to_code6
# ── /PACKAGE IMPORTS ──

from typing import Optional

import numpy as np
import pandas as pd


def build_name_history(profiles: pd.DataFrame, disclosures: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """[stock_code, corp_name, valid_from, valid_to, source].

    DART 공시목록에 상호변경 공시가 있으면 그 접수일을 변경시점으로 쓴다.
    없으면 현재 상호 하나만 남기고 valid_from 을 NaT 로 둔다(= 시점 불명, 소급 금지).
    """
    if profiles is None or not len(profiles):
        return pd.DataFrame(columns=["stock_code", "corp_name", "valid_from", "valid_to", "source"])
    base = profiles.dropna(subset=["stock_code"])[["stock_code", "corp_name"]].drop_duplicates()
    base["valid_from"] = pd.NaT
    base["valid_to"] = pd.NaT
    base["source"] = "current_profile(시점불명)"
    if disclosures is None or not len(disclosures):
        LOG.info("상호변경 이력 원천이 없습니다 — 현재 상호를 과거에 소급하지 않고 '시점불명'으로 둡니다.")
        return base.reset_index(drop=True)
    d = disclosures.copy()
    for c in ("report_nm", "rpt_nm", "title"):
        if c in d.columns:
            nm = d[c].astype(str)
            break
    else:
        return base.reset_index(drop=True)
    m = nm.str.contains("상호변경|사명변경|회사명변경", regex=True, na=False)
    chg = d[m].copy()
    if not len(chg):
        return base.reset_index(drop=True)
    chg["stock_code"] = chg.get("stock_code", chg.get("code")).map(
        lambda s: to_code6(s) if pd.notna(s) else None)
    chg["valid_from"] = as_ts_series(chg.get("rcept_dt", chg.get("rcept_no")).astype(str).str[:8])
    out = pd.concat([base, chg.assign(corp_name=np.nan, valid_to=pd.NaT,
                                      source="disclosure_상호변경")[base.columns]],
                    ignore_index=True)
    LOG.info(f"상호변경 공시 {int(m.sum()):,}건 반영")
    return out.reset_index(drop=True)


def flag_corporate_actions(profiles: pd.DataFrame, disclosures: Optional[pd.DataFrame] = None
                           ) -> pd.DataFrame:
    """합병·분할 발생 종목/시점. capability 연속성 해석에 필요하다(합병 후 실적 점프는 역량이 아니다)."""
    if disclosures is None or not len(disclosures):
        return pd.DataFrame(columns=["stock_code", "event", "event_date"])
    d = disclosures.copy()
    col = next((c for c in ("report_nm", "rpt_nm", "title") if c in d.columns), None)
    if col is None:
        return pd.DataFrame(columns=["stock_code", "event", "event_date"])
    nm = d[col].astype(str)
    kinds = {"합병": "MERGER", "분할": "SPLIT", "영업양수": "ACQ", "영업양도": "DIV"}
    parts = []
    for k, v in kinds.items():
        m = nm.str.contains(k, na=False)
        if bool(m.any()):
            x = d[m].copy()
            x["event"] = v
            x["event_date"] = as_ts_series(x.get("rcept_dt", x.get("rcept_no")).astype(str).str[:8])
            x["stock_code"] = x.get("stock_code", x.get("code")).map(
                lambda s: to_code6(s) if pd.notna(s) else None)
            parts.append(x[["stock_code", "event", "event_date"]])
    return (pd.concat(parts, ignore_index=True).dropna(subset=["stock_code"])
            if parts else pd.DataFrame(columns=["stock_code", "event", "event_date"]))
