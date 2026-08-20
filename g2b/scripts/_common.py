# -*- coding: utf-8 -*-
"""스크립트 공통 부트스트랩 — sys.path 설정과 단계간 상태 전달."""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core import config as CFG          # noqa: E402
from core.log import LOG                 # noqa: E402
from core.io import (read_parquet_safe, atomic_write_parquet, write_json,  # noqa: E402
                     read_json, month_range)

import pandas as pd                      # noqa: E402

STATE_DIR = os.path.join(CFG.DATA_ROOT, "_state")


def save(name: str, df, subdir: str = None) -> str:
    d = subdir or STATE_DIR
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{name}.parquet")
    atomic_write_parquet(df, p)
    return p


def load(name: str, subdir: str = None):
    d = subdir or STATE_DIR
    return read_parquet_safe(os.path.join(d, f"{name}.parquet"))


def require(name: str, script_hint: str, subdir: str = None):
    df = load(name, subdir)
    if df is None:
        raise SystemExit(f"[중단] 선행 산출물 '{name}' 이 없습니다. 먼저 {script_hint} 를 실행하십시오.")
    return df


def header(title: str, spec: str = "") -> None:
    LOG.banner(f"G2B-DEMAND-GRAPH-V1 — {title}", spec)
    st = CFG.run_stamp()
    LOG.info(f"run_id={st['run_id']}  mode={st['run_mode']}  "
             f"git={st['git_commit'][:8]}  cfg={st['config_hash']}  "
             f"FUTURE_RETURN_LOCK={st['future_return_lock']}")


def months_for_research(warmup: bool = True):
    start = CFG.TARGET_START
    if warmup:
        start = (pd.Timestamp(CFG.TARGET_START) -
                 pd.DateOffset(months=CFG.WARMUP_MONTHS)).strftime("%Y-%m-%d")
    return month_range(start, CFG.TARGET_END)


def report_write(name: str, text: str) -> str:
    os.makedirs(CFG.REPORTS_DIR, exist_ok=True)
    p = os.path.join(CFG.REPORTS_DIR, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    LOG.ok(f"보고서 작성: reports/{name}")
    return p


def md_table(df, max_rows: int = 200, floatfmt: str = "{:,.4g}") -> str:
    """DataFrame → 마크다운 표."""
    if df is None or not len(df):
        return "_(행 없음)_\n"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
        else:
            d[c] = d[c].astype(str)
    cols = [str(c) for c in d.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in d.iterrows():
        out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in r.tolist()) + " |")
    if len(df) > max_rows:
        out.append(f"\n_… 외 {len(df) - max_rows:,}행_")
    return "\n".join(out) + "\n"
