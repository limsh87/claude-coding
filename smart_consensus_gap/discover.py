# -*- coding: utf-8 -*-
"""Stage 0 — 프로젝트/캐시 자동 탐색과 소스 가용성 매니페스트 (§18 Stage 0, §26-1~5).

원칙:
  · 캐시 우선(§0-5). 이미 있는 것을 다시 받지 않는다. 이 모듈은 **읽기 전용**이며
    어떤 파일도 옮기거나 지우거나 덮어쓰지 않는다(경로만 등록한다).
  · 파일명을 믿지 않는다. 파일명 힌트 + 실제 컬럼 구성(별칭 해석 후)의 겹침으로 점수를 매겨
    계약 테이블에 매핑한다. 컬럼을 못 맞추면 '없음'으로 처리하고 사유를 남긴다.
  · 벤더 필드가 없으면 ORIGINAL_EXACT 는 **불가능**으로 판정한다. 프록시를 몰래 넣지 않는다(§0-2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import contracts as C
from .config import MODE_ORIGINAL_EXACT, MODE_PUBLIC_REPRO, SCGConfig
from .util import LOG, fmt_table, read_table

_EXTS = (".parquet", ".pq", ".csv", ".csv.gz", ".jsonl", ".xlsx", ".xls")
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".ipynb_checkpoints", "outputs",
              ".venv", "venv", "site-packages", ".cache", "_backup"}

#  파일명 힌트: 계약 테이블 → 파일명에 나타날 법한 토큰
_NAME_HINTS: Dict[str, Tuple[str, ...]] = {
    "analyst_estimates": ("analyst_estimate", "estimates", "consensus_estimate", "eps_est",
                          "forecast", "추정", "estimate"),
    "actuals": ("actual", "reported", "fnltt", "실적", "earnings"),
    "prices": ("price", "ohlcv", "quote", "krx_ohlcv", "주가"),
    "flows": ("flow", "net_buy", "investor", "수급", "trading_value"),
    "universe_membership": ("universe", "membership", "kospi200", "constituent", "구성종목"),
    "vendor_consensus": ("vendor", "fnguide", "quantiwise", "wisereport", "smart_consensus"),
    "benchmark": ("benchmark", "index", "kospi200_index", "bm"),
    "fiscal_calendar": ("fiscal", "calendar", "fy_end", "결산"),
}


def default_roots(cfg: SCGConfig) -> List[str]:
    """탐색 루트. 존재하는 것만 남긴다."""
    home = os.path.expanduser("~")
    cands = list(cfg.data_roots) + [
        os.environ.get("SCG_DATA_DIR", ""),
        os.path.join(os.getcwd(), "data"),
        os.path.join(os.getcwd(), "scg_data"),
        cfg.cache_root,
        os.path.join(home, "scg_cache"),
        "/content/drive/MyDrive/scg_cache",
        # ── 기존 TCD v2 공용 캐시(§0-5: 이미 수집된 것을 재수집하지 않는다) ──
        "/content/drive/MyDrive/tcd_cache/_shared/table",
        "/content/drive/MyDrive/tcd_cache",
        os.path.join(home, "tcd_cache", "_shared", "table"),
        os.path.join(os.getcwd(), "tcd_cache"),
    ]
    out, seen = [], set()
    for c in cands:
        if not c:
            continue
        p = os.path.abspath(os.path.expanduser(c))
        if p in seen or not os.path.isdir(p):
            continue
        seen.add(p)
        out.append(p)
    return out


def _walk(root: str, max_depth: int = 5, max_files: int = 20000) -> List[str]:
    files: List[str] = []
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        if dirpath.count(os.sep) - base_depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if fn.lower().endswith(_EXTS):
                files.append(os.path.join(dirpath, fn))
                if len(files) >= max_files:
                    return files
    return files


def _peek_columns(path: str) -> List[str]:
    """행을 읽지 않고 컬럼만 본다. 수 GB 캐시를 전부 로드하지 않기 위한 장치."""
    low = path.lower()
    try:
        if low.endswith((".parquet", ".pq")):
            import pyarrow.parquet as pq  # noqa: PLC0415
            return [str(c) for c in pq.ParquetFile(path).schema_arrow.names]
        if low.endswith((".csv", ".csv.gz")):
            h = pd.read_csv(path, nrows=0)
            return [str(c) for c in h.columns]
        if low.endswith(".jsonl"):
            h = pd.read_json(path, lines=True, nrows=5)
            return [str(c) for c in h.columns]
        if low.endswith((".xlsx", ".xls")):
            h = pd.read_excel(path, nrows=0)
            return [str(c) for c in h.columns]
    except Exception as e:  # noqa: BLE001
        LOG.debug(f"  컬럼 확인 실패 {path}: {type(e).__name__}")
    return []


def _canonical_columns(cols: Sequence[str]) -> set:
    """별칭을 계약 컬럼명으로 되돌린 집합."""
    have = {str(c).strip() for c in cols}
    out = set(have)
    for canon, aliases in C.COLUMN_ALIASES.items():
        if canon in have:
            out.add(canon)
            continue
        if have & set(aliases):
            out.add(canon)
    return out


def _score(path: str, cols: Sequence[str], spec: C.TableSpec) -> Tuple[float, List[str]]:
    """(점수, 결측 필수컬럼). 필수컬럼 충족이 지배적이고 파일명 힌트는 동점 처리용."""
    canon = _canonical_columns(cols)
    req = [c for c, _ in spec.required]
    missing = [c for c in req if c not in canon]
    if not req:
        return 0.0, missing
    cover = 1.0 - len(missing) / len(req)
    if cover < 1.0:
        return cover * 0.5, missing          # 필수 결측이면 후보로만 남긴다
    name = os.path.basename(path).lower()
    hint = 1.0 if any(h in name for h in _NAME_HINTS.get(spec.name, ())) else 0.0
    opt_cols = [c for c, _ in spec.optional]
    opt = (sum(c in canon for c in opt_cols) / len(opt_cols)) if opt_cols else 0.0
    return 1.0 + hint * 0.5 + opt * 0.25, missing


@dataclass
class SourceHit:
    table: str
    paths: List[str] = field(default_factory=list)
    rows: int = 0
    score: float = 0.0
    missing_required: List[str] = field(default_factory=list)
    status: str = "MISSING"
    note: str = ""


@dataclass
class DataSources:
    frames: Dict[str, "pd.DataFrame"] = field(default_factory=dict)
    hits: Dict[str, SourceHit] = field(default_factory=dict)
    roots: List[str] = field(default_factory=list)
    exact_possible: bool = False
    exact_block_reasons: List[str] = field(default_factory=list)
    resolved_mode: str = MODE_PUBLIC_REPRO
    synthetic: bool = False

    def get(self, name: str) -> Optional["pd.DataFrame"]:
        df = self.frames.get(name)
        return df if df is not None and len(df) else None

    def has(self, name: str) -> bool:
        return self.get(name) is not None


def _load_and_validate(paths: List[str], spec: C.TableSpec) -> Tuple[Optional["pd.DataFrame"], str]:
    frames = []
    for p in paths:
        df = read_table(p)
        if df is None or not len(df):
            continue
        df = C.coerce(df, spec)
        keep = [c for c in spec.columns if c in df.columns]
        frames.append(df[keep])
    if not frames:
        return None, "읽기 실패 또는 0행"
    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return out, f"{len(paths)}개 파일 병합" if len(frames) > 1 else "단일 파일"


def discover(cfg: SCGConfig, injected: Optional[Dict[str, "pd.DataFrame"]] = None) -> DataSources:
    """캐시/디스크를 훑어 계약 테이블을 채운다. injected 가 있으면 그것을 우선한다(합성 리허설)."""
    src = DataSources(roots=default_roots(cfg))
    injected = injected or {}

    if injected:
        LOG.info(f"  주입된 테이블 사용: {sorted(injected)}")
        src.synthetic = bool(cfg.synthetic)

    scanned: List[Tuple[str, List[str]]] = []
    if len(injected) < len(C.REQUIRED_FOR_RUN):
        LOG.info(f"  탐색 루트 {len(src.roots)}개: " +
                 (", ".join(src.roots) if src.roots else "(없음)"))
        for root in src.roots:
            for p in _walk(root):
                scanned.append((p, _peek_columns(p)))
        LOG.info(f"  스캔한 데이터 파일 {len(scanned):,}개")

    for spec in C.ALL_SPECS:
        hit = SourceHit(table=spec.name)
        if spec.name in injected:
            df = C.coerce(injected[spec.name], spec)
            res = C.validate(df, spec)
            hit.paths = ["<injected>"]
            hit.rows = int(len(df))
            hit.score = 99.0
            hit.missing_required = res.missing_required
            hit.status = "OK" if res.ok else "INVALID"
            hit.note = "주입(합성 픽스처)" if cfg.synthetic else "주입"
            src.frames[spec.name] = df
            src.hits[spec.name] = hit
            continue

        best: List[Tuple[float, str, List[str]]] = []
        for path, cols in scanned:
            if not cols:
                continue
            sc, missing = _score(path, cols, spec)
            if sc >= 1.0:
                best.append((sc, path, missing))
        if not best:
            near = [(s, p, m) for p, c in scanned for s, m in [_score(p, c, spec)]
                    if 0.5 <= s < 1.0]
            near.sort(reverse=True, key=lambda x: x[0])
            hit.status = "MISSING"
            if near:
                hit.note = (f"유사 후보 {os.path.basename(near[0][1])} "
                            f"(필수 결측: {','.join(near[0][2][:5])})")
                hit.missing_required = near[0][2]
            src.hits[spec.name] = hit
            continue

        best.sort(reverse=True, key=lambda x: (x[0], -len(x[1])))
        top_score = best[0][0]
        paths = [p for s, p, _ in best if s >= top_score - 1e-9]
        df, note = _load_and_validate(paths, spec)
        res = C.validate(df, spec)
        hit.paths = paths
        hit.rows = int(len(df)) if df is not None else 0
        hit.score = float(top_score)
        hit.missing_required = res.missing_required
        hit.status = "OK" if res.ok else "INVALID"
        hit.note = "; ".join([note] + res.messages)[:300]
        if df is not None and res.ok:
            src.frames[spec.name] = df
        src.hits[spec.name] = hit

    _resolve_mode(cfg, src)
    return src


def _resolve_mode(cfg: SCGConfig, src: DataSources) -> None:
    """§0-2 / §26-5 — 벤더 필드 실측으로만 EXACT 여부를 결정한다."""
    reasons: List[str] = []
    vc = src.get("vendor_consensus")
    if vc is None:
        reasons.append("vendor_consensus 테이블 없음")
    else:
        for col in ("smart_consensus", "surprise_probability"):
            if col not in vc.columns:
                reasons.append(f"vendor_consensus.{col} 컬럼 없음")
            elif int(vc[col].notna().sum()) == 0:
                reasons.append(f"vendor_consensus.{col} 전부 결측")
    src.exact_block_reasons = reasons
    src.exact_possible = not reasons

    if cfg.mode == MODE_ORIGINAL_EXACT and not src.exact_possible:
        LOG.warning("  ⚠ MODE=ORIGINAL_EXACT 로 요청되었으나 벤더 필드가 없다 → PUBLIC_REPRO 로 강등")
    src.resolved_mode = MODE_ORIGINAL_EXACT if (
        src.exact_possible and cfg.mode in (MODE_ORIGINAL_EXACT, "AUTO")) else MODE_PUBLIC_REPRO

    LOG.info(f"  ORIGINAL_EXACT 가능 여부: {'가능' if src.exact_possible else '불가'}"
             + ("" if src.exact_possible else f" — {', '.join(reasons)}"))
    LOG.info(f"  확정 모드: {src.resolved_mode}")


def availability_frame(src: DataSources) -> "pd.DataFrame":
    """01_source_availability.csv."""
    rows = []
    for spec in C.ALL_SPECS:
        h = src.hits.get(spec.name) or SourceHit(spec.name)
        df = src.frames.get(spec.name)
        dmin = dmax = ""
        if df is not None and len(df) and spec.pit_columns:
            s = df[spec.pit_columns[0]].dropna()
            if len(s):
                dmin, dmax = str(s.min())[:10], str(s.max())[:10]
        rows.append({
            "table": spec.name,
            "required_for_run": spec.name in C.REQUIRED_FOR_RUN,
            "status": h.status,
            "rows": h.rows,
            "n_files": len(h.paths),
            "date_min": dmin, "date_max": dmax,
            "missing_required": ";".join(h.missing_required),
            "match_score": round(h.score, 3),
            "paths": " | ".join(os.path.basename(p) for p in h.paths[:5]),
            "note": h.note,
        })
    return pd.DataFrame(rows)


def blocking_gaps(src: DataSources) -> List[str]:
    """이게 비어야 실데이터 파이프라인을 돌릴 수 있다."""
    return [t for t in C.REQUIRED_FOR_RUN if not src.has(t)]


def log_availability(src: DataSources) -> "pd.DataFrame":
    av = availability_frame(src)
    LOG.info(fmt_table(av[["table", "required_for_run", "status", "rows",
                           "date_min", "date_max", "note"]], max_rows=20, floatfmt="{:,.0f}"))
    gaps = blocking_gaps(src)
    if gaps:
        LOG.warning(f"  ⚠ 필수 테이블 결측: {gaps} → 실데이터 백테스트 불가")
    return av


__all__ = ["DataSources", "SourceHit", "discover", "availability_frame", "blocking_gaps",
           "log_availability", "default_roots"]
