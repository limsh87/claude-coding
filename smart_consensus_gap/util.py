# -*- coding: utf-8 -*-
"""공용 유틸 — 로깅 / 스테이지 타이머(§19) / IO / 벡터화 헬퍼.

수백만 행을 파이썬 루프로 돌지 않는다(§0-6). 여기 모인 헬퍼는 전부 NumPy 벡터화이며,
그룹 단위 연산은 groupby 대신 '정렬 + 그룹 코드 + bincount' 로 처리한다.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════════════════════════
#  로깅 — 콘솔 + run.log 동시 기록
# ════════════════════════════════════════════════════════════════════════════════════════
_ASCII_FALLBACK = str.maketrans({
    "─": "-", "│": "|", "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "═": "=", "║": "|", "╔": "+", "╗": "+", "╚": "+", "╝": "+",
    "✔": "OK", "✘": "X", "⚠": "!", "★": "*", "▶": ">", "·": ".", "…": "...", "→": "->",
})


class _SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        s = super().format(record)
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            s.encode(enc)
        except (UnicodeEncodeError, LookupError):
            s = s.translate(_ASCII_FALLBACK).encode("ascii", "replace").decode("ascii")
        return s


LOG = logging.getLogger("scg")


def setup_logging(out_dir: str, level: str = "INFO") -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "run.log")
    LOG.handlers.clear()
    LOG.setLevel(getattr(logging, level.upper(), logging.INFO))
    LOG.propagate = False
    fmt = _SafeFormatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    LOG.addHandler(sh)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s"))
    LOG.addHandler(fh)
    for h in ("reconfigure",):
        with contextlib.suppress(Exception):
            getattr(sys.stdout, h)(encoding="utf-8", errors="replace")
    return path


def banner(title: str, char: str = "═", width: int = 92) -> None:
    LOG.info(char * width)
    LOG.info(f"  {title}")
    LOG.info(char * width)


def head(title: str) -> None:
    LOG.info("")
    LOG.info(f"┌─ {title} " + "─" * max(0, 88 - len(title)))


# ════════════════════════════════════════════════════════════════════════════════════════
#  스테이지 타이머 (§19)
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class StageRecord:
    stage: str
    seconds: float
    budget_seconds: float
    rows_in: int = 0
    rows_out: int = 0
    note: str = ""

    @property
    def over_budget(self) -> bool:
        return self.budget_seconds > 0 and self.seconds > self.budget_seconds


class Profiler:
    def __init__(self, budgets_minutes: Dict[str, float], total_budget_minutes: float) -> None:
        self.budgets = {k: v * 60.0 for k, v in budgets_minutes.items()}
        self.total_budget = total_budget_minutes * 60.0
        self.records: List[StageRecord] = []
        self.t0 = time.time()

    @contextlib.contextmanager
    def stage(self, name: str, note: str = ""):
        t = time.time()
        head(f"{name} {note}".strip())
        box = {"rows_in": 0, "rows_out": 0, "note": note}
        try:
            yield box
        finally:
            dt = time.time() - t
            rec = StageRecord(name, dt, self.budgets.get(name, 0.0),
                              int(box.get("rows_in", 0)), int(box.get("rows_out", 0)),
                              str(box.get("note", "")))
            self.records.append(rec)
            flag = "  ⚠ 예산초과" if rec.over_budget else ""
            LOG.info(f"└─ {name} 완료 {dt:,.1f}s (예산 {rec.budget_seconds/60:.0f}m){flag}")

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def to_frame(self) -> "pd.DataFrame":
        rows = [
            {"stage": r.stage, "seconds": round(r.seconds, 2),
             "minutes": round(r.seconds / 60, 3),
             "budget_minutes": round(r.budget_seconds / 60, 1),
             "over_budget": r.over_budget, "rows_in": r.rows_in, "rows_out": r.rows_out,
             "note": r.note}
            for r in self.records
        ]
        rows.append({"stage": "TOTAL", "seconds": round(self.elapsed, 2),
                     "minutes": round(self.elapsed / 60, 3),
                     "budget_minutes": round(self.total_budget / 60, 1),
                     "over_budget": self.elapsed > self.total_budget,
                     "rows_in": 0, "rows_out": 0, "note": "§19 총 예산"})
        return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════════════════════════
#  IO
# ════════════════════════════════════════════════════════════════════════════════════════
def read_table(path: str) -> Optional["pd.DataFrame"]:
    """parquet / csv / jsonl 을 읽는다. 실패하면 None (호출부가 사유를 기록)."""
    try:
        low = path.lower()
        if low.endswith((".parquet", ".pq")):
            return pd.read_parquet(path)
        if low.endswith(".jsonl"):
            return pd.read_json(path, lines=True)
        if low.endswith((".csv", ".csv.gz", ".gz")):
            return pd.read_csv(path, dtype=str, keep_default_na=True, low_memory=False)
        if low.endswith((".xlsx", ".xls")):
            return pd.read_excel(path, dtype=str)
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 사유를 남기고 계속 간다
        LOG.warning(f"  읽기 실패 {path}: {type(e).__name__}: {e}")
    return None


def write_parquet(df: "pd.DataFrame", path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception as e:  # pyarrow 미설치/스키마 문제 → csv 폴백
        LOG.warning(f"  parquet 저장 실패({type(e).__name__}) → csv 폴백: {path}")
        alt = path.rsplit(".", 1)[0] + ".csv"
        df.to_csv(alt, index=False, encoding="utf-8-sig")
        return alt


def write_csv(df: "pd.DataFrame", path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_json(obj: Any, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return path


def write_text(text: str, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ════════════════════════════════════════════════════════════════════════════════════════
#  벡터화 그룹 헬퍼 — groupby.apply 없이 그룹 통계를 만든다
# ════════════════════════════════════════════════════════════════════════════════════════
def group_codes(keys: "pd.DataFrame") -> Tuple[np.ndarray, int]:
    """여러 컬럼을 하나의 0..G-1 정수 그룹코드로. 정렬 순서는 보존하지 않는다."""
    if len(keys) == 0:
        return np.zeros(0, dtype=np.int64), 0
    idx, uniq = pd.factorize(pd.MultiIndex.from_frame(keys), sort=False)
    return np.asarray(idx, dtype=np.int64), int(len(uniq))


def group_sum(vals: np.ndarray, g: np.ndarray, ng: int) -> np.ndarray:
    return np.bincount(g, weights=np.nan_to_num(vals, nan=0.0), minlength=ng)


def group_count(g: np.ndarray, ng: int, mask: Optional[np.ndarray] = None) -> np.ndarray:
    w = None if mask is None else mask.astype(np.float64)
    return np.bincount(g, weights=w, minlength=ng)


def group_broadcast(gvals: np.ndarray, g: np.ndarray) -> np.ndarray:
    return gvals[g]


def group_max(vals: np.ndarray, g: np.ndarray, ng: int) -> np.ndarray:
    out = np.full(ng, -np.inf)
    np.maximum.at(out, g, np.where(np.isfinite(vals), vals, -np.inf))
    return out


def within_group_rank(g: np.ndarray, order: np.ndarray) -> np.ndarray:
    """그룹 내 순위(0부터). order 는 정렬 기준값(오름차순)."""
    n = len(g)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    srt = np.lexsort((order, g))
    gs = g[srt]
    newgrp = np.empty(n, dtype=bool)
    newgrp[0] = True
    newgrp[1:] = gs[1:] != gs[:-1]
    grp_start = np.maximum.accumulate(np.where(newgrp, np.arange(n), 0))
    rank_sorted = np.arange(n) - grp_start
    out = np.empty(n, dtype=np.int64)
    out[srt] = rank_sorted
    return out


def winsorize(x: np.ndarray, lo_q: float, hi_q: float) -> np.ndarray:
    """유한값 분위수로 클립. 원본 배열은 변경하지 않는다."""
    v = np.asarray(x, dtype=np.float64).copy()
    fin = np.isfinite(v)
    if fin.sum() < 3:
        return v
    lo, hi = np.nanquantile(v[fin], [lo_q, hi_q])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi < lo:
        return v
    v[fin] = np.clip(v[fin], lo, hi)
    return v


def zscore(x: np.ndarray) -> np.ndarray:
    v = np.asarray(x, dtype=np.float64)
    fin = np.isfinite(v)
    out = np.full(v.shape, np.nan)
    if fin.sum() < 2:
        return out
    mu = v[fin].mean()
    sd = v[fin].std(ddof=0)
    if not np.isfinite(sd) or sd <= 0:
        out[fin] = 0.0
        return out
    out[fin] = (v[fin] - mu) / sd
    return out


def pct_rank(x: np.ndarray) -> np.ndarray:
    """0~1 퍼센타일 랭크(동률 평균). 유한값만 대상."""
    v = np.asarray(x, dtype=np.float64)
    fin = np.isfinite(v)
    out = np.full(v.shape, np.nan)
    n = int(fin.sum())
    if n == 0:
        return out
    if n == 1:
        out[fin] = 0.5
        return out
    r = pd.Series(v[fin]).rank(method="average").to_numpy()
    out[fin] = (r - 1.0) / (n - 1.0)
    return out


def mad(x: np.ndarray) -> float:
    v = np.asarray(x, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    med = np.median(v)
    return float(np.median(np.abs(v - med)))


def month_ends(start: "pd.Timestamp", end: "pd.Timestamp", months: Sequence[int]) -> List["pd.Timestamp"]:
    """지정 월의 말일(캘린더) 목록 (§11)."""
    rng = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="ME")
    return [d for d in rng if d.month in set(months)]


def safe_div(a: np.ndarray, b: np.ndarray, tol: float) -> np.ndarray:
    """|b| < tol 이면 NaN. 분모를 abs 로 바꾸지 않는다(§0-4)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    out = np.full(a.shape, np.nan)
    ok = np.isfinite(a) & np.isfinite(b) & (np.abs(b) >= tol)
    out[ok] = a[ok] / b[ok]
    return out


def human_int(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def fmt_table(df: "pd.DataFrame", max_rows: int = 40, floatfmt: str = "{:,.4f}") -> str:
    """의존성 없이 표를 문자열로. to_string 은 폭이 튀어서 직접 만든다."""
    if df is None or len(df) == 0:
        return "  (빈 표)"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
        else:
            d[c] = d[c].astype(str)
    widths = {c: max(len(str(c)), int(d[c].str.len().max() if len(d) else 0)) for c in d.columns}
    lines = ["  " + "  ".join(str(c).ljust(widths[c]) for c in d.columns),
             "  " + "  ".join("-" * widths[c] for c in d.columns)]
    for _, r in d.iterrows():
        lines.append("  " + "  ".join(str(r[c]).ljust(widths[c]) for c in d.columns))
    if len(df) > max_rows:
        lines.append(f"  … 외 {len(df) - max_rows:,}행")
    return "\n".join(lines)


__all__ = [n for n in dir() if not n.startswith("_")]
