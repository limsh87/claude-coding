# -*- coding: utf-8 -*-
"""Stage 1 — 정규화 (§18 Stage 1, §3.1, §4, §27).

여기서 다루는 것: 애널리스트 식별 / 종목코드 / 회계기간 / 단위 / 타임스탬프.

★ 가장 위험한 실수는 '조용한' 실수다.
  · 증권사 사명 변경을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로 다른 사람이 되어
    과거 정확도 이력이 끊긴다(→ skill 이 항상 n=0 으로 수렴해 smart consensus 가 무력화).
  · 반대로 이름만 같은 다른 사람을 합치면 정확도가 오염된다. 그래서 estimator_id 는
    broker::analyst 이며, **동명이인을 자동 병합하지 않는다**(§3.1).
  · 제거는 파싱오류/단위오류/회계기간 매핑오류만. "성과가 나빠서" 지우는 것은 금지(§4).
    제거 사유는 전부 카운트되어 데이터품질 표에 남는다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import contracts as C
from .util import LOG, fmt_table

# ════════════════════════════════════════════════════════════════════════════════════════
#  증권사 정규화 — 사명 변경 이력이 핵심 (2014~2026)
# ════════════════════════════════════════════════════════════════════════════════════════
BROKER_CANON: Tuple[Tuple[str, str], ...] = (
    (r"미래에셋(대우|증권)?", "미래에셋증권"),
    (r"(대우증권|KDB대우)", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),
    (r"한국투자|한투증권", "한국투자증권"),
    (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),
    (r"하나(증권|금융투자|금투)", "하나증권"),
    (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"),
    (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"),
    (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"),
    (r"IBK(투자증권|증권)", "IBK투자증권"),
    (r"신영증권", "신영증권"),
    (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),
    (r"SK증권", "SK증권"),
    (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권|하이證", "iM증권"),
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"), (r"부국증권", "부국증권"), (r"한양증권", "한양증권"),
    (r"상상인증권|골든브릿지", "상상인증권"), (r"케이프(투자증권|증권)", "케이프투자증권"),
    (r"토스증권", "토스증권"), (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"), (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"), (r"DS투자증권", "DS투자증권"),
    (r"에프앤가이드|FnGuide", "에프앤가이드"),
)
_BROKER_RE = tuple((re.compile(p, re.I), n) for p, n in BROKER_CANON)

_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")
_TITLE_RE = re.compile(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사|이사|부장)")


def _clean(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x if x is not None else "")).strip()


def map_unique(s: "pd.Series", fn) -> "pd.Series":
    """★ 성능 핵심: 정규화 함수를 **유니크 값에만** 적용하고 매핑으로 되돌린다.

    증권사명 정규화는 36개 정규식을 순회한다. 수백만 행에 행 단위로 돌리면 수십 분이
    걸리지만, 유니크 값은 보통 수백 개뿐이라 즉시 끝난다. (§0-6 파이썬 행 루프 금지)
    """
    v = s.astype("string").fillna("")
    uniq = pd.unique(v.to_numpy())
    table = {u: fn(u) for u in uniq}
    return v.map(table).astype(object).astype(str)


def normalize_broker(raw: Any) -> str:
    """정식 증권사명. 못 알아보면 정규화 문자열 자체를 쓰되 '미상'으로 뭉치지 않는다.
    (미상으로 뭉치면 서로 다른 소형사가 한 estimator 가 되어 정확도가 거짓이 된다)"""
    t = _clean(raw)
    if not t:
        return ""
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return canon
    return re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동 외 1인' → ['홍길동','김철수']. 순서 보존 = 1저자 우선."""
    t = _clean(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = _TITLE_RE.sub(" ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out: List[str] = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


def lead_analyst(raw: Any) -> str:
    a = split_analysts(raw)
    return a[0] if a else ""


def make_estimator_id(broker_norm: str, analyst_norm: str) -> str:
    """§3.1 — 1순위 broker::analyst, 2순위 broker. 동명이인 자동 병합 금지."""
    b = (broker_norm or "").strip()
    a = (analyst_norm or "").strip()
    if b and a:
        return f"{b}::{a}"
    return b or (f"UNKNOWN::{a}" if a else "")


# ════════════════════════════════════════════════════════════════════════════════════════
#  회계기간 파싱
# ════════════════════════════════════════════════════════════════════════════════════════
_FP_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"^(\d{4})\s*Q\s*([1-4])$", re.I), "YQ"),
    (re.compile(r"^(\d{4})\s*[.\-/]\s*([1-4])\s*Q$", re.I), "YQ"),
    (re.compile(r"^([1-4])\s*Q\s*(\d{4})$", re.I), "QY"),
    (re.compile(r"^([1-4])\s*Q\s*(\d{2})$", re.I), "QY2"),
    (re.compile(r"^(\d{4})\s*[.\-/]\s*(0?[1-9]|1[0-2])$"), "YM"),
    (re.compile(r"^(?:FY)?\s*(\d{4})\s*(?:FY|A|E)?$", re.I), "Y"),
)


def normalize_fiscal_period(raw: Any) -> str:
    """다양한 표기를 '2020Q2' / '2020FY' 로. 실패하면 빈 문자열(→ FP_MAPPING_ERROR)."""
    t = _clean(raw).upper().replace(" ", "")
    if not t:
        return ""
    for rx, kind in _FP_PATTERNS:
        m = rx.match(t)
        if not m:
            continue
        if kind == "YQ":
            return C.fp_quarter(int(m.group(1)), int(m.group(2)))
        if kind == "QY":
            return C.fp_quarter(int(m.group(2)), int(m.group(1)))
        if kind == "QY2":
            return C.fp_quarter(2000 + int(m.group(2)), int(m.group(1)))
        if kind == "YM":
            mm = int(m.group(2))
            if mm in (3, 6, 9, 12):
                return C.fp_quarter(int(m.group(1)), mm // 3)
            return ""
        if kind == "Y":
            return C.fp_year(int(m.group(1)))
    return ""


def normalize_horizon(raw: Any) -> str:
    t = _clean(raw).upper().replace(" ", "")
    if t in ("FQ1", "FQ2", "FY1", "FY2", "FY3"):
        return t
    if t in ("Q1", "1Q"):
        return "FQ1"
    if t in ("Y1", "1Y", "CY1"):
        return "FY1"
    if t in ("Y2", "2Y", "CY2"):
        return "FY2"
    return t


METRIC_CANON = {"EPS": "EPS", "주당순이익": "EPS", "OP": "OP", "영업이익": "OP",
                "OPERATINGPROFIT": "OP", "NP": "NP", "당기순이익": "NP", "NETPROFIT": "NP",
                "NETINCOME": "NP", "SALES": "SALES", "매출액": "SALES", "REVENUE": "SALES"}


def normalize_metric(raw: Any) -> str:
    t = _clean(raw).upper().replace(" ", "")
    return METRIC_CANON.get(t, t)


# ════════════════════════════════════════════════════════════════════════════════════════
#  추정치 정규화 파이프라인
# ════════════════════════════════════════════════════════════════════════════════════════
UNIT_SANITY_ABS_MAX = 5e7          # 원 단위 EPS 상한(현실적 상한). 초과 = 단위 오류 의심
UNIT_MIN_MEDIAN_ABS = 1.0          # 중앙값이 1원 미만이면 배율 검정 자체가 무의미하다
UNIT_MIN_RATIO = 50.0              # 최소 배율
UNIT_LOG10_TOL = 0.15              # 10의 거듭제곱에서 얼마나 벗어나도 되는가(로그10 기준)


@dataclass
class NormalizeReport:
    rows_in: int = 0
    rows_out: int = 0
    drops: Dict[str, int] = field(default_factory=dict)
    n_estimators: int = 0
    n_companies: int = 0
    unknown_broker_rows: int = 0
    broker_only_estimator_rows: int = 0

    def frame(self) -> "pd.DataFrame":
        rows = [{"reason": k, "rows": v} for k, v in sorted(self.drops.items())]
        rows.append({"reason": "KEPT", "rows": self.rows_out})
        rows.append({"reason": "INPUT_TOTAL", "rows": self.rows_in})
        return pd.DataFrame(rows)


def _drop(mask: "pd.Series", reason: str, rep: NormalizeReport) -> "pd.Series":
    n = int(mask.sum())
    if n:
        rep.drops[reason] = rep.drops.get(reason, 0) + n
    return mask


def _unit_error_mask(df: "pd.DataFrame") -> "pd.Series":
    """동일 (company, metric, fiscal_period) 내 중앙값 대비 10의 거듭제곱 배율로 벗어난 행.

    ★ '값이 튄다'는 이유로 지우는 것이 아니다 — 그건 §4 가 명시적으로 금지한다.
      다음 세 조건을 **동시에** 만족할 때만 단위 오류로 본다:
        (1) 동일 그룹 중앙값이 1원 이상 — 0 근처에서는 배율 자체가 의미가 없다
            (적자 전환 구간에서 EPS 가 0을 지나면 배율이 쉽게 100배가 된다)
        (2) 배율이 50배 이상
        (3) log10(배율) 이 정수에서 0.15 이내 — 원/천원/백만원 혼용은 정확히 10^k 다.
      애널리스트 사이의 단순한 이견은 (1)(2)(3)을 동시에 만족할 수 없다.
      제거된 행 수는 드롭 사유 표(UNIT_SCALE_ERROR)에 그대로 남는다.
    """
    v = df["estimate_value"].to_numpy(dtype=float)
    grp = df.groupby(["company_code", "metric", "fiscal_period"], observed=True)
    med = df.assign(_a=np.abs(v)).groupby(
        ["company_code", "metric", "fiscal_period"], observed=True)["_a"].transform("median")
    med = med.to_numpy(dtype=float)
    cnt = grp["company_code"].transform("size").to_numpy()
    a = np.abs(v)
    ok = ((cnt >= 3) & np.isfinite(a) & np.isfinite(med)
          & (med >= UNIT_MIN_MEDIAN_ABS) & (a > 0))
    ratio = np.where(ok, np.maximum(a, med) / np.maximum(np.minimum(a, med), 1e-12), 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        lg = np.log10(np.where(ratio > 0, ratio, np.nan))
    near_pow10 = np.isfinite(lg) & (np.abs(lg - np.round(lg)) <= UNIT_LOG10_TOL) & (np.round(lg) >= 2)
    return pd.Series(ok & (ratio >= UNIT_MIN_RATIO) & near_pow10, index=df.index)


def normalize_estimates(df: "pd.DataFrame") -> Tuple["pd.DataFrame", NormalizeReport]:
    """analyst_estimates 정규화 + 계약 준수 + 중복 정리."""
    rep = NormalizeReport(rows_in=int(len(df)))
    d = C.coerce(df, C.ANALYST_ESTIMATES).copy()

    # 식별자 — 원본이 이미 정규화 컬럼을 갖고 있으면 존중하고, 없으면 생성한다.
    def _src(norm_col: str, raw_col: str) -> "pd.Series":
        if norm_col in d.columns and (d[norm_col].astype(str).str.len() > 0).any():
            return d[norm_col]
        return d[raw_col] if raw_col in d.columns else pd.Series("", index=d.index, dtype=object)

    d["broker_name_norm"] = map_unique(_src("broker_name_norm", "broker_name_raw"), normalize_broker)
    d["analyst_name_norm"] = map_unique(_src("analyst_name_norm", "analyst_name_raw"), lead_analyst)
    #  estimator_id 는 두 컬럼의 조합이므로 조합 단위로 유니크 매핑한다
    combo = d["broker_name_norm"].astype(str) + "\x1f" + d["analyst_name_norm"].astype(str)
    d["estimator_id"] = map_unique(combo, lambda s: make_estimator_id(*s.split("\x1f", 1)))
    rep.unknown_broker_rows = int((d["broker_name_norm"].astype(str).str.len() == 0).sum())
    rep.broker_only_estimator_rows = int((d["analyst_name_norm"].astype(str).str.len() == 0).sum())

    d["metric"] = map_unique(d["metric"], normalize_metric)
    d["fiscal_period"] = map_unique(d["fiscal_period"], normalize_fiscal_period)
    if "horizon" in d.columns:
        d["horizon"] = map_unique(d["horizon"], normalize_horizon)

    #  report_id 가 없거나 비어 있으면 결정적 대체 ID 를 만든다. 행 단위 sha1 은 수백만 행에서
    #  수 분이 걸리므로 벡터화된 해시를 쓴다(값이 같으면 실행 간에도 같은 ID 가 나온다).
    have_rid = (d["report_id"].astype("string").fillna("").str.len() > 0
                if "report_id" in d.columns else pd.Series(False, index=d.index))
    if not bool(have_rid.all()):
        key = (d["estimator_id"].astype(str) + "|" + d["company_code"].astype(str) + "|"
               + d["metric"].astype(str) + "|" + d["fiscal_period"].astype(str) + "|"
               + d["published_at"].astype("int64").astype(str) + "|"
               + d["estimate_value"].astype(str))
        gen = "G" + pd.util.hash_pandas_object(key, index=False).astype("uint64").astype(str)
        d["report_id"] = np.where(have_rid.to_numpy(),
                                  d["report_id"].astype("string").fillna("").to_numpy()
                                  if "report_id" in d.columns else "",
                                  gen.to_numpy())

    # ── 제거는 아래 사유들만 (§4) ─────────────────────────────────────────────────────
    bad = pd.Series(False, index=d.index)
    bad |= _drop(d["published_at"].isna(), "PIT_MISSING_PUBLISHED_AT", rep)
    bad |= _drop(~d["estimate_value"].apply(np.isfinite).fillna(False), "PARSE_NONFINITE", rep)
    bad |= _drop(d["fiscal_period"].astype(str).str.len() == 0, "FP_MAPPING_ERROR", rep)
    bad |= _drop(~d["company_code"].astype(str).str.fullmatch(r"\d{6}").fillna(False),
                 "COMPANY_CODE_ERROR", rep)
    bad |= _drop(d["estimator_id"].astype(str).str.len() == 0, "ESTIMATOR_ID_MISSING", rep)
    bad |= _drop(d["estimate_value"].abs() > UNIT_SANITY_ABS_MAX, "UNIT_ABS_IMPLAUSIBLE", rep)
    keep = d.loc[~bad].copy()
    if len(keep):
        um = _unit_error_mask(keep)
        _drop(um, "UNIT_SCALE_ERROR", rep)
        keep = keep.loc[~um].copy()

    # ── 완전 중복 제거 (같은 보고서의 같은 줄이 두 소스에서 들어온 경우) ─────────────────
    subset = ["estimator_id", "company_code", "metric", "fiscal_period", "published_at",
              "report_id", "estimate_value"]
    n0 = len(keep)
    keep = keep.drop_duplicates(subset=subset, keep="first")
    if n0 - len(keep):
        rep.drops["EXACT_DUPLICATE"] = rep.drops.get("EXACT_DUPLICATE", 0) + (n0 - len(keep))

    # ── 같은 estimator/company/period/metric 이 같은 시점에 다수 → 최신, 동률이면
    #    report_id 결정적 정렬 후 마지막 1건 (§3.1) ────────────────────────────────────
    keep = keep.sort_values(
        ["estimator_id", "company_code", "metric", "fiscal_period", "published_at", "report_id"],
        kind="mergesort")
    n0 = len(keep)
    keep = keep.drop_duplicates(
        subset=["estimator_id", "company_code", "metric", "fiscal_period", "published_at"],
        keep="last")
    if n0 - len(keep):
        rep.drops["SAME_TIMESTAMP_SUPERSEDED"] = rep.drops.get("SAME_TIMESTAMP_SUPERSEDED", 0) + (n0 - len(keep))

    keep = keep.reset_index(drop=True)
    rep.rows_out = int(len(keep))
    rep.n_estimators = int(keep["estimator_id"].nunique()) if len(keep) else 0
    rep.n_companies = int(keep["company_code"].nunique()) if len(keep) else 0
    return keep, rep


def normalize_actuals(df: "pd.DataFrame") -> "pd.DataFrame":
    d = C.coerce(df, C.ACTUALS).copy()
    d["metric"] = map_unique(d["metric"], normalize_metric)
    d["fiscal_period"] = map_unique(d["fiscal_period"], normalize_fiscal_period)
    d = d[(d["fiscal_period"].astype(str).str.len() > 0)
          & d["actual_announced_at"].notna()
          & d["actual_value"].apply(np.isfinite).fillna(False)
          & d["company_code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)]
    # 동일 (company, metric, period) 다건 → 최초 발표 시점 1건 (정정공시를 소급 반영하지 않는다)
    d = d.sort_values(["company_code", "metric", "fiscal_period", "actual_announced_at"],
                      kind="mergesort")
    d = d.drop_duplicates(subset=["company_code", "metric", "fiscal_period"], keep="first")
    return d.reset_index(drop=True)


def normalize_prices(df: "pd.DataFrame") -> "pd.DataFrame":
    d = C.coerce(df, C.PRICES).copy()
    d = d[d["date"].notna() & d["company_code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)]
    d = d.sort_values(["company_code", "date"], kind="mergesort")
    d = d.drop_duplicates(subset=["company_code", "date"], keep="last")
    if "listed_flag" not in d.columns:
        d["listed_flag"] = True
    return d.reset_index(drop=True)


def normalize_flows(df: "pd.DataFrame") -> "pd.DataFrame":
    d = C.coerce(df, C.FLOWS).copy()
    d = d[d["date"].notna() & d["company_code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)]
    d = d.sort_values(["company_code", "date"], kind="mergesort")
    return d.drop_duplicates(subset=["company_code", "date"], keep="last").reset_index(drop=True)


def normalize_universe(df: "pd.DataFrame") -> "pd.DataFrame":
    d = C.coerce(df, C.UNIVERSE_MEMBERSHIP).copy()
    d = d[d["date"].notna() & d["company_code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)]
    d = d.sort_values(["universe_id", "date", "company_code"], kind="mergesort")
    return d.drop_duplicates(subset=["date", "company_code", "universe_id"],
                             keep="last").reset_index(drop=True)


def normalize_vendor(df: "pd.DataFrame") -> "pd.DataFrame":
    d = C.coerce(df, C.VENDOR_CONSENSUS).copy()
    d["metric"] = map_unique(d["metric"], normalize_metric)
    d["fiscal_period"] = map_unique(d["fiscal_period"], normalize_fiscal_period)
    d = d[d["date"].notna()]
    return d.sort_values(["company_code", "metric", "fiscal_period", "date"],
                         kind="mergesort").reset_index(drop=True)


def log_normalize_report(rep: NormalizeReport) -> None:
    LOG.info(f"  추정치 {rep.rows_in:,}행 → {rep.rows_out:,}행 유지 "
             f"(estimator {rep.n_estimators:,} / 종목 {rep.n_companies:,})")
    if rep.drops:
        LOG.info(fmt_table(rep.frame(), max_rows=20, floatfmt="{:,.0f}"))
    if rep.broker_only_estimator_rows:
        LOG.info(f"  · 애널리스트명이 없어 broker 단위 estimator 로 처리한 행: "
                 f"{rep.broker_only_estimator_rows:,} (§3.1 2순위 규칙)")


__all__ = [n for n in dir() if not n.startswith("_")]
