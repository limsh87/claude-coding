# -*- coding: utf-8 -*-
"""G2B 업체 ↔ DART 법인 ↔ 상장종목 crosswalk.

§13 PRIMARY  : 사업자등록번호 exact match  (G2B supplier_bizno == DART bizr_no)
§13 금지     : 기업명 fuzzy matching 만으로 자동 확정하지 않는다.
               fuzzy name 은 candidate generation 용도로만 쓴다.
§14          : bizr_no / corp_code / stock_code / valid_from / valid_to /
               mapping_type / confidence 구조. 현재 stock_code 를 과거 전체에 소급하지 않는다.
§52          : 매칭 품질 게이트 — exact / verified / ambiguous / unmatched 비중을 금액기준으로 보고.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import digits, to_code6, as_ts_series
from core.vault import get_vault
# ── /PACKAGE IMPORTS ──

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MAPPING_TYPES = ("EXACT_ID", "VERIFIED_MANUAL", "NAME_CANDIDATE", "AMBIGUOUS", "UNMATCHED")

_SUFFIX = re.compile(r"(주식회사|㈜|\(주\)|주\)|유한회사|유한책임회사|합자회사|합명회사|"
                     r"co\.?,?\s*ltd\.?|corp(oration)?\.?|inc\.?|company|limited)", re.I)
_PAREN = re.compile(r"\([^)]*\)")
_NONWORD = re.compile(r"[^0-9A-Za-z가-힣]")


def norm_name(s) -> str:
    """상호 정규화. 이것만으로 매칭을 확정하지 않는다 — 후보 생성용이다."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = _PAREN.sub(" ", t)
    t = _SUFFIX.sub(" ", t)
    return _NONWORD.sub("", t).upper()


def build_crosswalk(dart_profiles: pd.DataFrame,
                    corp_codes: Optional[pd.DataFrame] = None,
                    listing_history: Optional[pd.DataFrame] = None,
                    verified_overrides: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """PIT crosswalk 생성.

    listing_history 가 있으면 상장/폐지일로 valid_from/valid_to 를 정한다.
    없으면 valid_from 을 NaT 로 두고 mapping_type 에 그 사실을 남긴다 —
    '현재 stock_code 를 과거 전체에 소급'하는 것을 방지하기 위해, 유효기간을 모르는 매핑은
    PRIMARY 백테스트에서 사용 금지로 표시한다(§14, §98).
    """
    if dart_profiles is None or not len(dart_profiles):
        return pd.DataFrame(columns=["bizr_no", "corp_code", "stock_code", "corp_name",
                                     "valid_from", "valid_to", "mapping_type", "confidence"])
    d = dart_profiles.copy()
    d["bizr_no"] = d.get("bizr_no", pd.Series(index=d.index, dtype=object)).map(digits).replace("", np.nan)
    d["stock_code"] = d.get("stock_code").map(lambda s: to_code6(s) if pd.notna(s) else None)
    d = d[d["stock_code"].notna()].copy()                    # 상장사만 (§49)
    d["corp_name_norm"] = d["corp_name"].map(norm_name)

    X = pd.DataFrame({
        "bizr_no": d["bizr_no"], "corp_code": d.get("corp_code"), "stock_code": d["stock_code"],
        "corp_name": d.get("corp_name"), "corp_name_norm": d["corp_name_norm"],
        "mapping_type": np.where(d["bizr_no"].notna(), "EXACT_ID", "UNMATCHED"),
        "confidence": np.where(d["bizr_no"].notna(), 1.0, 0.0)})

    if listing_history is not None and len(listing_history):
        lh = listing_history.copy()
        lh["stock_code"] = lh["stock_code"].map(lambda s: to_code6(s) if pd.notna(s) else None)
        for c in ("listing_date", "delisting_date"):
            if c in lh.columns:
                lh[c] = as_ts_series(lh[c])
        agg = lh.groupby("stock_code", dropna=True).agg(
            valid_from=("listing_date", "min"),
            valid_to=("delisting_date", "max")).reset_index()
        X = X.merge(agg, on="stock_code", how="left")
    else:
        X["valid_from"] = pd.NaT
        X["valid_to"] = pd.NaT
        X.loc[X["mapping_type"] == "EXACT_ID", "mapping_type"] = "EXACT_ID_NO_VALIDITY"
        LOG.warn("상장이력이 없어 crosswalk 유효기간을 복원하지 못했습니다 — "
                 "해당 매핑은 PRIMARY 에서 사용 금지로 표시합니다(§14).")

    if verified_overrides is not None and len(verified_overrides):
        v = verified_overrides.copy()
        v["bizr_no"] = v["bizr_no"].map(digits)
        v["stock_code"] = v["stock_code"].map(to_code6)
        v["mapping_type"] = "VERIFIED_MANUAL"
        v["confidence"] = v.get("confidence", 0.95)
        X = pd.concat([X, v], ignore_index=True)

    X = X.drop_duplicates(subset=["bizr_no", "stock_code"], keep="last")
    # 한 사업자번호가 여러 종목에 붙으면 확정하지 않는다 (§10 애매한 연결을 억지로 확정하지 않는다)
    dupe = X[X["bizr_no"].notna()].groupby("bizr_no")["stock_code"].transform("nunique") > 1
    if bool(dupe.any()):
        X.loc[dupe.reindex(X.index, fill_value=False), "mapping_type"] = "AMBIGUOUS"
        X.loc[dupe.reindex(X.index, fill_value=False), "confidence"] = 0.4
        LOG.warn(f"사업자번호 1개 ↔ 종목 2개 이상인 애매한 매핑 {int(dupe.sum()):,}건 → AMBIGUOUS 로 격리")
    LOG.ok(f"crosswalk {len(X):,}행 — " +
           ", ".join(f"{k}:{v:,}" for k, v in X["mapping_type"].value_counts().items()))
    return X.reset_index(drop=True)


def name_candidates(g2b_names: pd.Series, crosswalk: pd.DataFrame,
                    min_len: int = 3) -> pd.DataFrame:
    """상호 정규화 완전일치 후보만 생성한다. 확정이 아니라 '사람이 볼 후보 목록'이다(§13)."""
    if crosswalk is None or not len(crosswalk):
        return pd.DataFrame(columns=["g2b_name", "stock_code", "corp_name", "method"])
    cw = crosswalk.dropna(subset=["corp_name_norm"]) if "corp_name_norm" in crosswalk.columns else crosswalk
    idx = (cw.groupby("corp_name_norm")["stock_code"].agg(list)
           if "corp_name_norm" in cw.columns else pd.Series(dtype=object))
    src = pd.DataFrame({"g2b_name": pd.Series(g2b_names).dropna().unique()})
    src["norm"] = src["g2b_name"].map(norm_name)
    src = src[src["norm"].str.len() >= min_len]
    src["cands"] = src["norm"].map(lambda k: idx.get(k, []))
    src = src[src["cands"].map(len) > 0].explode("cands").rename(columns={"cands": "stock_code"})
    src["method"] = np.where(src.groupby("g2b_name")["stock_code"].transform("nunique") == 1,
                             "NAME_CANDIDATE", "AMBIGUOUS")
    LOG.info(f"상호 기반 후보 {len(src):,}건 생성 — PRIMARY 에는 절대 자동 반영하지 않습니다(§13).")
    return src[["g2b_name", "stock_code", "method"]].reset_index(drop=True)


def attach_stock_code(events: pd.DataFrame, crosswalk: pd.DataFrame,
                      time_col: str = "available_at",
                      allow_types: Tuple[str, ...] = ("EXACT_ID", "VERIFIED_MANUAL")) -> pd.DataFrame:
    """이벤트에 PIT 종목코드를 붙인다. 유효기간 밖의 매핑은 붙이지 않는다(§14).

    벡터화: 사업자번호 조인 후 시간구간 필터. 기업 루프 없음.
    """
    E = events.copy()
    if crosswalk is None or not len(crosswalk):
        E["stock_code"] = pd.Series(pd.NA, index=E.index, dtype="string")
        E["map_type"] = "UNMATCHED"
        return E
    cw = crosswalk[crosswalk["mapping_type"].isin(allow_types)].copy()
    cw["bizr_no"] = cw["bizr_no"].map(digits)
    cw = cw.dropna(subset=["bizr_no"])[["bizr_no", "stock_code", "valid_from", "valid_to",
                                        "mapping_type", "confidence"]]
    E["_bz"] = E["supplier_bizno"].map(lambda s: digits(s) if pd.notna(s) else "")
    E["_row"] = np.arange(len(E), dtype="int64")        # merge 가 인덱스를 버리므로 명시적 행 id
    M = E.merge(cw, left_on="_bz", right_on="bizr_no", how="left", suffixes=("", "_cw"))
    t = pd.to_datetime(M[time_col])
    ok = M["stock_code"].notna()
    ok &= M["valid_from"].isna() | (t >= M["valid_from"])
    ok &= M["valid_to"].isna() | (t <= M["valid_to"])
    M["map_type"] = np.where(ok, M["mapping_type"].fillna("UNMATCHED"),
                             np.where(M["stock_code"].notna(), "OUT_OF_VALIDITY", "UNMATCHED"))
    M.loc[~ok, "stock_code"] = np.nan
    # ★ 한 사업자번호가 crosswalk 여러 행에 걸리면 이벤트 행이 늘어나 낙찰금액이 중복 계상된다.
    #   원본 행수를 반드시 보존한다: 유효매핑 > 높은 confidence 순으로 행당 하나만 남긴다.
    n_before = len(E)
    if len(M) != n_before:
        M["_ok"] = ok.to_numpy().astype("int8")
        M["_conf"] = pd.to_numeric(M.get("confidence"), errors="coerce").fillna(0.0)
        M = (M.sort_values(["_row", "_ok", "_conf"], ascending=[True, False, False],
                           kind="stable")
             .drop_duplicates(subset=["_row"], keep="first").drop(columns=["_ok", "_conf"]))
        LOG.warn(f"사업자번호 1개가 crosswalk 여러 행에 걸려 {len(E):,}행이 일시적으로 늘어났습니다 "
                 f"— 행당 하나만 남겨 원본 행수를 복원했습니다(금액 중복계상 방지).")
    M = M.sort_values("_row", kind="stable").reset_index(drop=True)
    assert len(M) == n_before, f"행수 보존 실패: {n_before:,} → {len(M):,}"
    return M.drop(columns=[c for c in ("_bz", "_row", "bizr_no", "valid_from", "valid_to",
                                       "mapping_type", "confidence") if c in M.columns])


def mapping_quality(events: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """§52 매칭 품질 게이트 — 금액 기준 비중으로 본다(건수 기준은 소액건에 희석된다)."""
    e = events[events["supplier_bizno"].notna()].copy()
    if not len(e):
        return pd.DataFrame(columns=["map_type", "건수", "금액", "금액비중"])
    e["map_type"] = e.get("map_type", pd.Series("UNMATCHED", index=e.index)).fillna("UNMATCHED")
    g = e.groupby("map_type").agg(건수=(amount_col, "size"), 금액=(amount_col, "sum")).reset_index()
    g["금액비중"] = g["금액"] / max(g["금액"].sum(), 1e-9)
    return g.sort_values("금액", ascending=False).reset_index(drop=True)
