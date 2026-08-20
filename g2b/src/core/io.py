# -*- coding: utf-8 -*-
"""파일 입출력 · 해시 · 원자적 쓰기 · 레이트리미터. raw 는 절대 덮어쓰지 않는다(§4)."""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

import os
import io as _io
import json
import gzip
import time
import hashlib
import threading
import datetime as _dt
from typing import Any, Iterable, List, Optional, Dict

import numpy as np
import pandas as pd


# ── 해시 ──────────────────────────────────────────────────────────────────────
def sha1_str(*parts: Any) -> str:
    return hashlib.sha1("␟".join(map(str, parts)).encode("utf-8")).hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def df_hash(df: pd.DataFrame) -> str:
    """데이터프레임 내용 해시 — §88 동일 입력 → 동일 산출 검증용."""
    if df is None or len(df) == 0:
        return sha256_bytes(b"")
    d = df.reindex(sorted(df.columns), axis=1)
    try:
        return hashlib.sha256(
            pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()).hexdigest()
    except Exception:                                          # noqa: BLE001
        return sha256_bytes(d.astype(str).to_csv(index=False).encode())


# ── 원자적 쓰기 ───────────────────────────────────────────────────────────────
def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def atomic_write_bytes(path: str, data: bytes) -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_parquet(df: pd.DataFrame, path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    d = df.copy()
    for c in d.columns:                       # object 혼합열은 parquet 에서 죽는다
        if d[c].dtype == object:
            try:
                pd.api.types.infer_dtype(d[c], skipna=True)
            except Exception:                                  # noqa: BLE001
                d[c] = d[c].astype(str)
    try:
        d.to_parquet(tmp, index=False, compression=compression)
    except Exception:                                          # noqa: BLE001
        d.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    if not path or not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:                                     # noqa: BLE001
        LOG.warn(f"parquet 읽기 실패({type(e).__name__}) — 격리만 하고 삭제하지 않습니다: {path}")
        try:
            os.rename(path, path + f".corrupt.{_dt.datetime.now():%Y%m%d_%H%M%S}")
        except Exception:                                      # noqa: BLE001
            pass
        return None


# ── JSONL (append-only) ───────────────────────────────────────────────────────
def read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out: List[dict] = []
    op = gzip.open if path.endswith(".gz") else open
    try:
        with op(path, "rt", encoding="utf-8") as f:            # type: ignore[call-arg]
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:                              # noqa: BLE001
                    continue
    except Exception as e:                                     # noqa: BLE001
        LOG.warn(f"jsonl 읽기 실패({type(e).__name__}): {path}")
    return out


_APPEND_LK = threading.Lock()


def append_jsonl(path: str, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    _ensure_dir(path)
    buf = _io.StringIO()
    for r in rows:
        buf.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    with _APPEND_LK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(buf.getvalue())
            f.flush()
            os.fsync(f.fileno())


def write_json(path: str, obj: Any) -> str:
    return atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:                                          # noqa: BLE001
        return default


# ── 레이트리미터 · 호출예산 (§87) ──────────────────────────────────────────────
class RateLimiter:
    def __init__(self, qps: float):
        self.min_iv = 1.0 / max(qps, 0.01)
        self._lk = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lk:
            now = time.time()
            dt = self._last + self.min_iv - now
            if dt > 0:
                time.sleep(dt)
                now = time.time()
            self._last = now


_LIMITERS: Dict[str, RateLimiter] = {}
_LIM_LK = threading.Lock()


def limiter(source: str, qps: float = 3.0) -> RateLimiter:
    with _LIM_LK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(qps)
        return _LIMITERS[source]


class CallBudget:
    """일일 호출량 상한. 초과하면 조용히 계속하지 않고 멈추고 체크포인트를 남긴다(§87)."""

    def __init__(self, path: str):
        self.path = path
        self._lk = threading.Lock()
        self._state = read_json(path, {}) or {}

    def _today(self) -> str:
        return _dt.date.today().isoformat()

    def used(self, source: str) -> int:
        return int(self._state.get(self._today(), {}).get(source, 0))

    def charge(self, source: str, n: int = 1) -> None:
        with self._lk:
            d = self._state.setdefault(self._today(), {})
            d[source] = int(d.get(source, 0)) + n
            if (d[source] % 200) == 0:
                write_json(self.path, self._state)

    def remaining(self, source: str, cap: int) -> int:
        return max(0, cap - self.used(source))

    def flush(self) -> None:
        with self._lk:
            write_json(self.path, self._state)


# ── 작은 유틸 ─────────────────────────────────────────────────────────────────
def as_ts(x: Any) -> Optional[pd.Timestamp]:
    if x is None:
        return None
    try:
        t = pd.to_datetime(x, errors="coerce")
    except Exception:                                          # noqa: BLE001
        return None
    if t is pd.NaT or (isinstance(t, float) and np.isnan(t)):
        return None
    try:
        if getattr(t, "tz", None) is not None:
            t = t.tz_localize(None)
    except Exception:                                          # noqa: BLE001
        pass
    return None if pd.isna(t) else pd.Timestamp(t)


def as_ts_series(s: Any, fmt: Optional[str] = None) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce", format=fmt)
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:                                          # noqa: BLE001
        pass
    return out


def month_end(x: Any) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start: Any, end: Any) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start) + pd.offsets.MonthEnd(0),
                         pd.Timestamp(end) + pd.offsets.MonthEnd(0), freq="ME")


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(pd.Series(a) if not isinstance(a, pd.Series) else a, errors="coerce")
    b = pd.to_numeric(pd.Series(b) if not isinstance(b, pd.Series) else b, errors="coerce")
    return a / b.where(b.abs() > eps, np.nan)


def digits(x: Any) -> str:
    """사업자등록번호 등 숫자만 남긴다."""
    import re as _re
    return _re.sub(r"\D", "", str(x or ""))


def to_code6(x: Any) -> Optional[str]:
    d = digits(x)
    if not d:
        return None
    d = d[-6:].zfill(6) if len(d) >= 6 else d.zfill(6)
    return d if len(d) == 6 else None
