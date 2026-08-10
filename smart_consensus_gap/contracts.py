# -*- coding: utf-8 -*-
"""데이터 계약 (§3) + 계약 검정.

계약은 "있으면 좋은 문서"가 아니라 게이트다. 계약을 통과하지 못한 테이블은 파이프라인에
들어갈 수 없고, 통과 여부는 01_source_availability.csv 에 그대로 남는다.

PIT 컬럼(published_at / actual_announced_at / date)이 없는 테이블은 '조용히' 통과시키지
않는다. 그 컬럼이 없다는 것은 곧 시점 통제가 불가능하다는 뜻이기 때문이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════════════════════════
#  테이블 스펙
# ════════════════════════════════════════════════════════════════════════════════════════
STR, F64, I64, DT, BOOL = "str", "float64", "int64", "datetime64[ns]", "bool"


@dataclass(frozen=True)
class TableSpec:
    name: str
    required: Tuple[Tuple[str, str], ...]          # (컬럼, dtype)
    optional: Tuple[Tuple[str, str], ...] = ()
    pit_columns: Tuple[str, ...] = ()              # 시점 통제의 근거가 되는 컬럼
    key: Tuple[str, ...] = ()                      # 논리적 키(중복 검사용)
    note: str = ""

    @property
    def columns(self) -> Tuple[str, ...]:
        return tuple(c for c, _ in self.required) + tuple(c for c, _ in self.optional)

    @property
    def dtypes(self) -> Dict[str, str]:
        return {c: t for c, t in (self.required + self.optional)}


#  ★ §3.1 의 전체 컬럼 목록은 **정규화가 끝난** 원장의 스키마다. 원본 캐시(한경/네이버/벤더
#    덤프)에는 broker_name_norm·analyst_name_norm·estimator_id 가 있을 리 없다 — 그건
#    Stage 1 이 만드는 파생 컬럼이다. 그것들을 '필수'로 두면 어떤 실데이터도 계약을 통과하지
#    못하고 파이프라인이 통째로 죽는다. 그래서 원본에 반드시 있어야 하는 것만 required 로 두고,
#    파생 컬럼은 optional 로 둔다. 파생 실패는 normalize 의 드롭 사유 표에 그대로 남는다.
ANALYST_ESTIMATES = TableSpec(
    name="analyst_estimates",
    required=(
        ("published_at", DT), ("company_code", STR),
        ("metric", STR), ("fiscal_period", STR), ("estimate_value", F64),
    ),
    optional=(
        ("report_id", STR), ("company_name", STR),
        ("broker_name_raw", STR), ("broker_name_norm", STR),
        ("analyst_name_raw", STR), ("analyst_name_norm", STR), ("estimator_id", STR),
        ("horizon", STR), ("source", STR), ("source_url_or_file", STR),
        ("parse_confidence", F64), ("ingested_at", DT),
    ),
    pit_columns=("published_at",),
    key=("estimator_id", "company_code", "metric", "fiscal_period", "report_id"),
    note="§3.1 — estimator_id = broker::analyst (1순위), broker (2순위). 동명이인 자동 병합 금지. "
         "norm/estimator_id 는 Stage 1 파생 컬럼이므로 원본에는 없어도 된다.",
)

#  정규화 이후 원장이 반드시 갖춰야 하는 컬럼 (Stage 1 출력 검정용)
NORMALIZED_ESTIMATE_COLUMNS = ("published_at", "report_id", "company_code", "broker_name_norm",
                               "analyst_name_norm", "estimator_id", "metric", "fiscal_period",
                               "estimate_value")

ACTUALS = TableSpec(
    name="actuals",
    required=(
        ("company_code", STR), ("metric", STR), ("fiscal_period", STR),
        ("actual_value", F64), ("actual_announced_at", DT),
    ),
    optional=(("source", STR),),
    pit_columns=("actual_announced_at",),
    key=("company_code", "metric", "fiscal_period"),
    note="§3.2",
)

PRICES = TableSpec(
    name="prices",
    required=(
        ("date", DT), ("company_code", STR), ("adj_close", F64), ("open", F64),
        ("market_cap", F64),
    ),
    optional=(("volume", F64), ("listed_flag", BOOL), ("adj_open", F64),
              ("delist_return", F64), ("close_raw", F64)),
    pit_columns=("date",),
    key=("date", "company_code"),
    note="§3.3 — open 이 없으면 다음 가용 close 로 체결하고 플래그를 남긴다(§12).",
)

FLOWS = TableSpec(
    name="flows",
    required=(
        ("date", DT), ("company_code", STR),
        ("institution_net_buy_value", F64), ("foreign_net_buy_value", F64),
    ),
    pit_columns=("date",),
    key=("date", "company_code"),
    note="§3.4 — 금액(원) 기준 순매수.",
)

UNIVERSE_MEMBERSHIP = TableSpec(
    name="universe_membership",
    required=(("date", DT), ("company_code", STR), ("universe_id", STR), ("is_member", BOOL)),
    pit_columns=("date",),
    key=("date", "company_code", "universe_id"),
    note="§3.5 — 반드시 과거 시점 구성종목. 현재 구성종목 소급 금지(§10, §27).",
)

VENDOR_CONSENSUS = TableSpec(
    name="vendor_consensus",
    required=(
        ("date", DT), ("company_code", STR), ("metric", STR), ("fiscal_period", STR),
        ("general_consensus", F64),
    ),
    optional=(("smart_consensus", F64), ("surprise_probability", F64), ("vendor", STR),
              ("eps_12mf", F64)),
    pit_columns=("date",),
    key=("date", "company_code", "metric", "fiscal_period"),
    note="§3.6 — 있을 때만. smart_consensus + surprise_probability 가 모두 있어야 EXACT 가능.",
)

BENCHMARK = TableSpec(
    name="benchmark",
    required=(("date", DT), ("benchmark_id", STR), ("close", F64)),
    pit_columns=("date",),
    key=("date", "benchmark_id"),
    note="계약 외 보조 테이블. 없으면 유니버스 시총가중 포트폴리오를 대용으로 쓰고 플래그를 남긴다(§17).",
)

FISCAL_CALENDAR = TableSpec(
    name="fiscal_calendar",
    required=(("company_code", STR), ("fy_end_month", I64)),
    optional=(("fy_end_day", I64),),
    note="보조. 없으면 12월 결산으로 가정하고 그 사실을 기록한다(§7.3).",
)

ALL_SPECS: Tuple[TableSpec, ...] = (
    ANALYST_ESTIMATES, ACTUALS, PRICES, FLOWS, UNIVERSE_MEMBERSHIP,
    VENDOR_CONSENSUS, BENCHMARK, FISCAL_CALENDAR,
)
SPEC_BY_NAME: Dict[str, TableSpec] = {s.name: s for s in ALL_SPECS}

REQUIRED_FOR_RUN = ("analyst_estimates", "actuals", "prices", "flows", "universe_membership")


# ════════════════════════════════════════════════════════════════════════════════════════
#  컬럼 별칭 — 외부 캐시(한경/네이버/pykrx/FDR/DART/TCD v2 _shared) 컬럼명을 계약으로 흡수
# ════════════════════════════════════════════════════════════════════════════════════════
COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "company_code": ("code", "stock_code", "ticker", "symbol", "종목코드", "isu_srt_cd", "shortcode"),
    "company_name": ("name", "stock_name", "corp_name", "종목명"),
    "published_at": ("pub_date", "report_date", "publish_date", "knowledge_date", "date_published"),
    "report_id": ("report_uid", "src_report_id", "rpt_id"),
    "broker_name_raw": ("broker_raw", "broker", "증권사", "sec_firm"),
    "broker_name_norm": ("broker_name", "broker_canon"),
    "analyst_name_raw": ("analyst_raw", "analyst", "작성자", "writer"),
    "analyst_name_norm": ("analyst_canon", "analyst_name"),
    "estimate_value": ("value", "est", "estimate", "eps_est", "추정치"),
    "fiscal_period": ("period", "fy", "target_period", "회계기간"),
    "metric": ("item", "account", "지표"),
    "horizon": ("hz", "term"),
    "actual_value": ("actual", "reported", "실적"),
    "actual_announced_at": ("announced_at", "rcept_dt", "report_date", "공시일"),
    "date": ("dt", "trade_date", "일자", "기준일"),
    "adj_close": ("close_adj", "adjclose", "수정종가", "adj_price"),
    "close_raw": ("close", "종가"),
    "open": ("open_price", "시가"),
    "market_cap": ("mktcap", "marcap", "시가총액", "market_capitalization"),
    "volume": ("vol", "거래량"),
    "institution_net_buy_value": ("inst_net_buy", "기관순매수", "institution_net", "inst_value"),
    "foreign_net_buy_value": ("foreign_net_buy", "외국인순매수", "foreign_net", "frgn_value"),
    "universe_id": ("universe", "index_id", "idx"),
    "is_member": ("member", "in_universe", "included"),
    "general_consensus": ("consensus", "cons_eps", "general"),
    "smart_consensus": ("smart", "smart_cons", "smart_eps"),
    "surprise_probability": ("surprise_prob", "sp", "prob_surprise"),
    "benchmark_id": ("index_name", "bm"),
    "close": ("index_close", "종가"),
    "listed_flag": ("listed", "is_listed"),
}


def apply_aliases(df: "pd.DataFrame", spec: TableSpec) -> "pd.DataFrame":
    """계약 컬럼이 없고 별칭만 있으면 이름을 바꿔 준다. 원본 컬럼은 지우지 않는다."""
    ren: Dict[str, str] = {}
    have = set(df.columns)
    for canon in spec.columns:
        if canon in have:
            continue
        for alias in COLUMN_ALIASES.get(canon, ()):
            if alias in have and alias not in ren:
                ren[alias] = canon
                break
    return df.rename(columns=ren) if ren else df


# ════════════════════════════════════════════════════════════════════════════════════════
#  코어싱 / 검정
# ════════════════════════════════════════════════════════════════════════════════════════
def normalize_code(s: "pd.Series") -> "pd.Series":
    """종목코드를 6자리 문자열로. 엑셀/parquet 왕복에서 '005930' 이 5930 이 되는 사고를 막는다."""
    x = s.astype("string").fillna("")
    x = x.str.replace(r"\.0$", "", regex=True).str.strip().str.upper()
    x = x.str.replace(r"^A", "", regex=True)
    num = x.str.fullmatch(r"\d{1,6}")
    x = x.where(~num.fillna(False), x.str.zfill(6))
    return x.astype(object).astype(str)


def coerce(df: "pd.DataFrame", spec: TableSpec) -> "pd.DataFrame":
    """계약 dtype 으로 강제. 실패한 값은 NaN 이 되며 이후 결측 감사에 잡힌다."""
    df = apply_aliases(df, spec)
    out = df.copy()
    for col, typ in spec.required + spec.optional:
        if col not in out.columns:
            continue
        if typ == DT:
            out[col] = pd.to_datetime(out[col], errors="coerce")
            try:
                if getattr(out[col].dtype, "tz", None) is not None:
                    out[col] = out[col].dt.tz_localize(None)
            except (AttributeError, TypeError):
                pass
            out[col] = out[col].astype("datetime64[ns]")
        elif typ == F64:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
        elif typ == I64:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        elif typ == BOOL:
            s = out[col]
            if s.dtype == object or str(s.dtype) == "string":
                s = s.astype("string").str.strip().str.lower().map(
                    {"true": True, "1": True, "y": True, "yes": True, "t": True,
                     "false": False, "0": False, "n": False, "no": False, "f": False})
            out[col] = s.astype("boolean").fillna(False).astype(bool)
        else:  # STR
            if col == "company_code":
                out[col] = normalize_code(out[col])
            else:
                out[col] = out[col].astype("string").fillna("").astype(object).astype(str)
    return out


@dataclass
class ContractResult:
    table: str
    ok: bool
    rows: int
    missing_required: List[str] = field(default_factory=list)
    null_pit_rows: int = 0
    duplicate_keys: int = 0
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    messages: List[str] = field(default_factory=list)

    def as_row(self) -> Dict[str, Any]:
        return {
            "table": self.table, "ok": self.ok, "rows": self.rows,
            "missing_required": ";".join(self.missing_required),
            "null_pit_rows": self.null_pit_rows, "duplicate_keys": self.duplicate_keys,
            "date_min": self.date_min or "", "date_max": self.date_max or "",
            "messages": " | ".join(self.messages),
        }


def validate(df: Optional["pd.DataFrame"], spec: TableSpec) -> ContractResult:
    if df is None:
        return ContractResult(spec.name, False, 0, [c for c, _ in spec.required],
                              messages=["테이블 없음"])
    res = ContractResult(spec.name, True, int(len(df)))
    missing = [c for c, _ in spec.required if c not in df.columns]
    res.missing_required = missing
    if missing:
        res.ok = False
        res.messages.append(f"필수 컬럼 결측: {missing}")
        return res

    for pc in spec.pit_columns:
        n_null = int(df[pc].isna().sum())
        res.null_pit_rows += n_null
        if n_null:
            res.messages.append(f"{pc} 결측 {n_null}행 → PIT 통제 불가로 제외 대상")
    if spec.pit_columns:
        pc = spec.pit_columns[0]
        s = df[pc].dropna()
        if len(s):
            res.date_min, res.date_max = str(s.min())[:10], str(s.max())[:10]

    if spec.key and all(k in df.columns for k in spec.key):
        dup = int(df.duplicated(subset=list(spec.key)).sum())
        res.duplicate_keys = dup
        if dup:
            res.messages.append(f"논리키 중복 {dup}행 (§3.1 최신 1건 규칙으로 정리 필요)")

    if res.rows == 0:
        res.ok = False
        res.messages.append("0행")
    return res


def empty_frame(spec: TableSpec) -> "pd.DataFrame":
    data = {}
    for col, typ in spec.required + spec.optional:
        if typ == DT:
            data[col] = pd.Series([], dtype="datetime64[ns]")
        elif typ == F64:
            data[col] = pd.Series([], dtype="float64")
        elif typ == I64:
            data[col] = pd.Series([], dtype="Int64")
        elif typ == BOOL:
            data[col] = pd.Series([], dtype=bool)
        else:
            data[col] = pd.Series([], dtype=object)
    return pd.DataFrame(data)


# ════════════════════════════════════════════════════════════════════════════════════════
#  회계기간 표기 (§3.1 예: 2020Q2, 2020FY)
# ════════════════════════════════════════════════════════════════════════════════════════
def fp_quarter(year: int, q: int) -> str:
    return f"{int(year):04d}Q{int(q)}"


def fp_year(year: int) -> str:
    return f"{int(year):04d}FY"


def parse_fiscal_period(fp: str) -> Tuple[Optional[int], Optional[int]]:
    """'2020Q2' → (2020, 2); '2020FY' → (2020, None). 알 수 없으면 (None, None)."""
    if not isinstance(fp, str):
        return (None, None)
    t = fp.strip().upper().replace(" ", "")
    if len(t) >= 6 and t[4] == "Q" and t[:4].isdigit() and t[5].isdigit():
        return (int(t[:4]), int(t[5]))
    if t.endswith("FY") and t[:-2].isdigit():
        return (int(t[:-2]), None)
    if t.endswith("A") and t[:-1].isdigit():   # 2020A 표기 허용
        return (int(t[:-1]), None)
    return (None, None)


def prev_year_same_quarter(fp: str) -> Optional[str]:
    y, q = parse_fiscal_period(fp)
    if y is None:
        return None
    return fp_quarter(y - 1, q) if q else fp_year(y - 1)


def is_quarter(fp: str) -> bool:
    return parse_fiscal_period(fp)[1] is not None


def fiscal_period_end(fp: str, fy_end_month: int = 12) -> Optional["pd.Timestamp"]:
    """회계기간 종료일. fy_end_month 는 회계연도 종료월(12월 결산이면 12)."""
    y, q = parse_fiscal_period(fp)
    if y is None:
        return None
    if q is None:
        m = int(fy_end_month)
        return pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
    # 분기: 회계연도 종료월 기준으로 3개월씩. 12월 결산이면 Q1=3월말.
    m = ((int(fy_end_month) - 12) + 3 * q - 1) % 12 + 1
    yy = y if int(fy_end_month) == 12 else y  # 비12월 결산의 연도 라벨은 소스 표기를 따른다
    ts = pd.Timestamp(year=yy, month=m, day=1) + pd.offsets.MonthEnd(0)
    if int(fy_end_month) != 12 and m > int(fy_end_month):
        ts = ts - pd.offsets.DateOffset(years=1) + pd.offsets.MonthEnd(0)
    return ts


__all__ = [n for n in dir() if not n.startswith("_")]
