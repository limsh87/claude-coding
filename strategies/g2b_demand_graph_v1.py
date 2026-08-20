#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  G2B-DEMAND-GRAPH-V1
#  나라장터 정부수요 이동 → 기업역량 정합 → 실제 수주 전환  투자전략 연구 엔진
#  build: v1.20260820.0216
#
#  «기업이 잘하고 있다"를 사는 것이 아니라, 그 기업이 과거부터 경쟁력을 입증한 사업영역으로
#    외생적인 정부수요가 이동하고 있으며, 해당 기업이 그 증가한 수요를 실제 수주로
#    전환하고 있는지를 측정한다.»
#
#  ── 이 파일 하나로 끝납니다 ──────────────────────────────────────────────────────────────
#   Colab / JupyterLab 한 셀에 붙여넣거나 `python g2b_demand_graph_v1.py` 로 실행하십시오.
#
#   실행 순서 (§97 연구 우선순위 — 순서를 바꾸지 않습니다)
#     [1] API historical depth 실측      [2] PIT 복원 가능성
#     [3] 낙찰기업 ↔ 상장회사 exact mapping [4] lifecycle 중복 제거
#     [5] 기업 capability                 [6] Eligible Government TAM
#     [7] Demand Shift                    [8] Win Realization
#     [9] Demand-Win Alignment            [10] Future return  ← 사전등록 동결 이후에만
#
#  ── 필수 설정 (환경변수) ─────────────────────────────────────────────────────────────────
#     DATA_GO_KR_SERVICE_KEY   공공데이터포털 일반 인증키(Decoding)
#     OPENDART_API_KEY         OpenDART 인증키
#     G2B_RUN_MODE             SMOKE | FULL | CACHED   (기본 SMOKE)
#     G2B_GDRIVE_ROOT          구글드라이브 캐시 루트 (기본 /content/drive/MyDrive/tcd_cache)
#
#  ── 구글드라이브 인덱스 ──────────────────────────────────────────────────────────────────
#     공용 _shared   : 원본·범용 정제본 (G2B 원장 6종, crosswalk, 계약이력) — 다른 전략도 재사용
#     전용 g2b_dg_v1 : 이 연구의 해석물 (lifecycle, graph, feature, backtest)
#     기존 캐시를 삭제·덮어쓰기하지 않습니다. 저널은 append-only 입니다.
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import io
import io as _io
import json
import numpy as np
import os
import pandas as pd
import platform
import random
import re
import shutil
import sys
import threading
import time
import unicodedata
import zipfile
from typing import Optional, Dict, Any
from contextlib import contextmanager
from typing import Sequence, List, Optional
from typing import Any, Iterable, List, Optional, Dict
from collections import Counter
from typing import Dict, List, Optional, Tuple, Sequence
from typing import Any, Dict, List, Optional, Tuple
from typing import Dict, List, Optional, Sequence
from typing import List, Optional, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from typing import Dict, List, Optional, Tuple
from typing import Dict, Optional, Tuple
from typing import Optional
from typing import Literal
from typing import Dict, List, Optional, Sequence, Tuple
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
from typing import Dict, Optional, Sequence, Tuple
from typing import Optional, Sequence
from typing import Any, Dict, List, Optional
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ── 단일파일 shim: CFG 는 이 모듈 자신을 가리킨다 (패키지 형태의 `from core import config as CFG` 대체) ──
CFG = sys.modules[__name__]


# ==========================================================================================
#  core/config.py
# ==========================================================================================
"""G2B-DEMAND-GRAPH-V1 — 전역 설정 / 실행 모드 / 미래수익률 잠금.

명세 §1.1(FUTURE_RETURN_LOCK), §4(키는 환경변수), §48(연구기간은 커버리지로 결정),
§87(호출제한), §88(재현성)에 대응한다.

이 모듈은 어떤 무거운 의존성도 import 하지 않는다 — 어느 스크립트에서든 첫 줄에 올 수 있어야 한다.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  ① 실행 모드
#     SMOKE  : 합성 G2B 세계로 전 계산경로를 실행 (네트워크·키 불필요)
#     FULL   : 캐시 우선 → 부족분만 신규 수집 → 드라이브 재적재
#     CACHED : 캐시/드라이브에 이미 있는 것만 사용 (신규 수집 금지)
# ══════════════════════════════════════════════════════════════════════════════
RUN_MODE = os.environ.get("G2B_RUN_MODE", "SMOKE").upper()
SEED = int(os.environ.get("G2B_SEED", "20260820"))
VERBOSE = os.environ.get("G2B_VERBOSE", "1") not in ("0", "false", "False")

# ══════════════════════════════════════════════════════════════════════════════
#  ② API 키 — §4 코드에 직접 기록하지 않는다
# ══════════════════════════════════════════════════════════════════════════════
DATA_GO_KR_SERVICE_KEY = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
OPENDART_API_KEY = os.environ.get("OPENDART_API_KEY", "")


def have_key(which: str) -> bool:
    return bool({"datagokr": DATA_GO_KR_SERVICE_KEY, "opendart": OPENDART_API_KEY}.get(which, ""))


# ══════════════════════════════════════════════════════════════════════════════
#  ③ 경로 — §4 데이터 레이크 / §89 산출물
#     raw 는 절대 덮어쓰지 않는다(수집기에서 구조적으로 강제).
# ══════════════════════════════════════════════════════════════════════════════
def _resolve_project_root() -> str:
    """패키지 형태(src/core/config.py)와 단일파일 형태 양쪽에서 올바른 루트를 찾는다."""
    env = os.environ.get("G2B_PROJECT_ROOT")
    if env:
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(here) == "core" and os.path.basename(os.path.dirname(here)) == "src":
        return os.path.abspath(os.path.join(here, "..", ".."))     # 패키지: <proj>/src/core → <proj>
    return os.path.abspath(os.path.join(here, "g2b_run"))          # 단일파일: 옆에 작업폴더 생성


PROJECT_ROOT = _resolve_project_root()
DATA_ROOT = os.environ.get("G2B_DATA_ROOT", os.path.join(PROJECT_ROOT, "data"))

RAW_DIR = os.path.join(DATA_ROOT, "raw")
BRONZE_DIR = os.path.join(DATA_ROOT, "bronze")
SILVER_DIR = os.path.join(DATA_ROOT, "silver")
GOLD_DIR = os.path.join(DATA_ROOT, "gold")
PIT_DIR = os.path.join(DATA_ROOT, "pit")
BACKTEST_DIR = os.path.join(DATA_ROOT, "backtest")

CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
AUDIT_DIR = os.path.join(PROJECT_ROOT, "audit")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
SCHEMA_REGISTRY_DIR = os.path.join(PROJECT_ROOT, "schema_registry")   # §86

RAW_SERVICES = ("order_plan", "prespec", "bid", "award", "contract", "process")


def ensure_dirs() -> None:
    for d in (RAW_DIR, BRONZE_DIR, SILVER_DIR, GOLD_DIR, PIT_DIR, BACKTEST_DIR,
              CONFIG_DIR, AUDIT_DIR, REPORTS_DIR, SCHEMA_REGISTRY_DIR):
        os.makedirs(d, exist_ok=True)
    for s in RAW_SERVICES:
        os.makedirs(os.path.join(RAW_DIR, s), exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ④ 구글드라이브 캐시 — 공용 인덱스 / 전용 인덱스   (사용자 필수 요구사항)
#     공용(_shared): 원본·범용 정제본. 다른 전략이 그대로 재사용한다.
#     전용(g2b_dg_v1): 이 연구 고유의 그래프·피처·스코어·백테스트 산출물.
# ══════════════════════════════════════════════════════════════════════════════
GDRIVE_ROOT = os.environ.get("G2B_GDRIVE_ROOT", "/content/drive/MyDrive/tcd_cache")
GDRIVE_SHARED_NS = "_shared"
GDRIVE_PRIVATE_NS = "g2b_dg_v1"
LOCAL_CACHE_ROOT = os.environ.get("G2B_LOCAL_CACHE_ROOT", os.path.join(PROJECT_ROOT, "..", "tcd_cache"))

# 공용 인덱스에서 재사용하는 기존 테이블 (캐시활용 최우선 — 절대 재수집하지 않는다)
SHARED_REUSE_TABLES = {
    "price": "krx_ohlcv_daily",
    "security_master": "security_master",
    "listing_snapshots": "krx_listing_snapshots",
    "dart_corpcode": "dart_corpcode",
    "dart_fin": "dart_fnltt_raw",
    "dart_company": "dart_company_profile",
}
# 이 연구가 공용 인덱스에 새로 기여하는 테이블 (다른 전략도 재사용 가능한 원본/범용 정제본)
SHARED_CONTRIB_TABLES = {
    "order_plan": "g2b_order_plan_raw",
    "prespec": "g2b_prespec_raw",
    "bid": "g2b_bid_raw",
    "award": "g2b_award_raw",
    "contract": "g2b_contract_raw",
    "process": "g2b_process_raw",
    "events": "g2b_events_normalized",
    "crosswalk": "g2b_company_crosswalk",
}

# ══════════════════════════════════════════════════════════════════════════════
#  ⑤ 연구기간 — §48. 시작일은 "수익률 성과"가 아니라 "데이터 커버리지"로만 정한다.
#     아래는 목표 구간이며 실제 USABLE_START_DATE 는 01_api_depth_audit 이 결정해
#     config/universe_definition.yaml 에 동결한다.
# ══════════════════════════════════════════════════════════════════════════════
TARGET_START = "2015-01-01"
TARGET_END = "2026-07-31"
WARMUP_MONTHS = 36          # §19 left-censoring

# ══════════════════════════════════════════════════════════════════════════════
#  ⑥ 성능 / 호출제한 — §87
# ══════════════════════════════════════════════════════════════════════════════
N_WORKERS_IO = int(os.environ.get("G2B_WORKERS", "8"))
RATE_LIMIT_QPS = {"datagokr": 4.0, "opendart": 8.0, "generic": 3.0}
DAILY_CALL_BUDGET = {"datagokr": int(os.environ.get("G2B_DATAGOKR_DAILY", "9000")),
                     "opendart": int(os.environ.get("G2B_OPENDART_DAILY", "18000"))}
PAGE_ROWS = 999
MAX_PAGES_PER_WINDOW = 400

# ══════════════════════════════════════════════════════════════════════════════
#  ⑦ FUTURE_RETURN_LOCK — §1.1 절대 준수
#     사전등록 4개 파일이 동결되고 SHA256 이 audit/prereg_hash.txt 에 기록되기
#     전까지 미래수익률을 팩터 선택에 사용할 수 없다. 우회 파라미터를 두지 않는다.
# ══════════════════════════════════════════════════════════════════════════════
PREREG_FILES = ("factor_preregistration.yaml", "universe_definition.yaml",
                "pit_policy.yaml", "backtest_policy.yaml")
TRIAL_LEDGER = os.path.join(AUDIT_DIR, "trial_ledger.json")
PREREG_HASH_FILE = os.path.join(AUDIT_DIR, "prereg_hash.txt")

_LOCK_MSG = (
    "[FUTURE_RETURN_LOCK] 미래수익률 접근이 차단되었습니다 (명세 §1.1).\n"
    "  사전등록이 동결되기 전에는 forward_return / future_price / future_market_cap /\n"
    "  future_financial / future_contract_outcome / future_winner / future_revenue 를\n"
    "  팩터 선택에 사용할 수 없습니다.\n"
    "  해제 절차: scripts/09_freeze_preregistration.py 를 실행하여\n"
    f"    {', '.join('config/' + f for f in PREREG_FILES)}\n"
    f"    {os.path.relpath(TRIAL_LEDGER, PROJECT_ROOT)}\n"
    "  를 동결하고 SHA256 을 audit/prereg_hash.txt 에 기록하십시오."
)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prereg_manifest() -> Dict[str, str]:
    """동결 대상 파일의 SHA256 목록. 파일이 없으면 그 키가 아예 없다."""
    out: Dict[str, str] = {}
    for fn in PREREG_FILES:
        p = os.path.join(CONFIG_DIR, fn)
        if os.path.exists(p):
            out["config/" + fn] = sha256_file(p)
    if os.path.exists(TRIAL_LEDGER):
        out["audit/trial_ledger.json"] = sha256_file(TRIAL_LEDGER)
    return out


def prereg_status() -> Dict[str, Any]:
    """(frozen, reason, manifest, recorded). 해시 불일치는 '동결 아님'으로 취급한다."""
    man = prereg_manifest()
    missing = [f for f in ("config/" + x for x in PREREG_FILES) if f not in man]
    if "audit/trial_ledger.json" not in man:
        missing.append("audit/trial_ledger.json")
    if missing:
        return {"frozen": False, "reason": f"미생성 파일: {missing}", "manifest": man, "recorded": None}
    if not os.path.exists(PREREG_HASH_FILE):
        return {"frozen": False, "reason": "audit/prereg_hash.txt 없음", "manifest": man, "recorded": None}
    try:
        rec = json.loads(open(PREREG_HASH_FILE, encoding="utf-8").read())
    except Exception as e:                                     # noqa: BLE001
        return {"frozen": False, "reason": f"prereg_hash.txt 파손({type(e).__name__})",
                "manifest": man, "recorded": None}
    diff = {k: (rec.get("files", {}).get(k), v) for k, v in man.items()
            if rec.get("files", {}).get(k) != v}
    if diff:
        return {"frozen": False,
                "reason": ("동결 이후 파일이 변경되었습니다 → " +
                           ", ".join(sorted(diff))[:300]),
                "manifest": man, "recorded": rec}
    return {"frozen": True, "reason": "", "manifest": man, "recorded": rec}


def future_return_lock() -> bool:
    """True 면 잠금 상태(미래수익률 사용 금지)."""
    if os.environ.get("G2B_FORCE_LOCK", "") == "1":
        return True
    return not prereg_status()["frozen"]


def assert_returns_unlocked(what: str = "미래수익률") -> None:
    """수익률을 만지는 모든 코드 경로의 유일한 관문. 예외를 던지지 조용히 통과시키지 않는다."""
    if future_return_lock():
        st = prereg_status()
        raise PermissionError(f"{_LOCK_MSG}\n  현재 상태: {st['reason']}\n  요청: {what}")


# ══════════════════════════════════════════════════════════════════════════════
#  ⑧ 재현성 스탬프 — §88
# ══════════════════════════════════════════════════════════════════════════════
def git_commit() -> str:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:                                          # noqa: BLE001
        return "unknown"


def config_hash() -> str:
    """설정 스냅샷 해시. 같은 입력 → 같은 factor parquet 를 보장하기 위한 키."""
    snap = {k: v for k, v in sorted(globals().items())
            if k.isupper() and isinstance(v, (str, int, float, bool, tuple, list, dict))
            and "KEY" not in k}
    return hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()[:16]


_RUN_ID: Optional[str] = None


def run_id() -> str:
    global _RUN_ID
    if _RUN_ID is None:
        _RUN_ID = _dt.datetime.now().strftime("run_%Y%m%d_%H%M%S_") + config_hash()[:6]
    return _RUN_ID


def run_stamp() -> Dict[str, str]:
    return {"run_id": run_id(), "git_commit": git_commit(), "config_hash": config_hash(),
            "run_mode": RUN_MODE, "seed": str(SEED), "python": sys.version.split()[0],
            "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "future_return_lock": str(future_return_lock())}


# ==========================================================================================
#  core/log.py
# ==========================================================================================
"""로그 · 표 출력 · 단계 타이머. 조용한 실패를 만들지 않는 것이 유일한 목표다."""


_T0 = time.time()


def _w(s: str) -> int:
    """동아시아 전각 문자를 2칸으로 계산 — 안 하면 한글 표가 전부 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))


def _pad(s: str, width: int, align: str = "l") -> str:
    s = str(s)
    gap = max(0, width - _w(s))
    if align == "r":
        return " " * gap + s
    if align == "c":
        return " " * (gap // 2) + s + " " * (gap - gap // 2)
    return s + " " * gap


class Log:
    def _emit(self, tag: str, msg: str) -> None:
        el = time.time() - _T0
        sys.stdout.write(f"[{el:7.1f}s] {tag} {msg}\n")
        sys.stdout.flush()

    def info(self, m: str) -> None:
        if VERBOSE:
            self._emit("   ", m)

    def ok(self, m: str) -> None:
        self._emit("✔  ", m)

    def warn(self, m: str) -> None:
        self._emit("⚠  ", m)

    def err(self, m: str) -> None:
        self._emit("✖  ", m)

    def debug(self, m: str) -> None:
        if VERBOSE:
            self._emit("·  ", m)

    def banner(self, title: str, sub: str = "") -> None:
        bar = "═" * 92
        sys.stdout.write(f"\n{bar}\n  {title}\n" + (f"  {sub}\n" if sub else "") + f"{bar}\n")
        sys.stdout.flush()

    def table(self, rows: Sequence[Sequence], head: Sequence[str],
              align: Optional[Sequence[str]] = None, title: str = "",
              max_rows: int = 200) -> None:
        rows = [list(map(lambda x: "" if x is None else str(x), r)) for r in rows]
        if not rows:
            if title:
                sys.stdout.write(f"\n  {title}\n    (행 없음)\n")
            return
        n = len(head)
        align = list(align) if align else ["l"] * n
        align = (align + ["l"] * n)[:n]
        widths = [max(_w(head[i]), *(_w(r[i]) if i < len(r) else 0 for r in rows)) for i in range(n)]
        out: List[str] = []
        if title:
            out.append(f"\n  {title}")
        out.append("  " + " │ ".join(_pad(head[i], widths[i], "c") for i in range(n)))
        out.append("  " + "─┼─".join("─" * widths[i] for i in range(n)))
        for r in rows[:max_rows]:
            out.append("  " + " │ ".join(_pad(r[i] if i < len(r) else "", widths[i], align[i])
                                         for i in range(n)))
        if len(rows) > max_rows:
            out.append(f"  … 외 {len(rows) - max_rows:,}행")
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

    @contextmanager
    def stage(self, name: str):
        t0 = time.time()
        self.banner(name)
        try:
            yield
        except Exception as e:                                  # noqa: BLE001
            self.err(f"{name} 실패 — {type(e).__name__}: {e}")
            raise
        finally:
            self.info(f"↳ {name} 완료 ({time.time() - t0:.1f}s)")


LOG = Log()


# ==========================================================================================
#  core/io.py
# ==========================================================================================
"""파일 입출력 · 해시 · 원자적 쓰기 · 레이트리미터. raw 는 절대 덮어쓰지 않는다(§4)."""




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


# ==========================================================================================
#  core/vault.py
# ==========================================================================================
"""VAULT — 구글드라이브 공용/전용 인덱스.

★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. 약속이 아니라 구조로 보장한다.
   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않는다.
   2) index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업.
   3) 컬럼은 합집합으로만 확장한다.
   4) blob 은 내용해시 경로 → 같은 내용은 재기록조차 없고, 다르면 새 리비전.
   5) 이미 드라이브에 있던 파일은 이동·개명 없이 경로만 등록한다(adopt-by-reference).
   6) 삭제 API 자체가 없다. 손상 파일도 .corrupt 로 격리만 한다.

  공용(_shared)  : 원본·범용 정제본. 다른 전략이 그대로 재사용한다.
                   → 이 연구가 새로 수집한 G2B 원장 6종이 여기에 기여된다.
  전용(g2b_dg_v1): 이 연구 고유의 lifecycle·graph·feature·backtest 산출물.
"""



VAULT_SCHEMA_VER = "g2b-1.0"

INDEX_COLUMNS = ["uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
                 "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
                 "project", "adopted", "schema_ver", "run_id", "extra"]


def _mount_drive() -> Tuple[str, str]:
    """(루트, 모드). Colab이면 마운트 시도, 아니면 동기화 폴더 → 로컬 폴백. 어느 쪽이든 죽지 않는다."""
    in_colab = False
    try:
        import google.colab  # noqa: F401
        in_colab = True
    except Exception:                                          # noqa: BLE001
        in_colab = False
    if in_colab:
        try:
            from google.colab import drive as _gdrive          # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return CFG.GDRIVE_ROOT, "COLAB_DRIVE"
            return CFG.LOCAL_CACHE_ROOT, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return CFG.LOCAL_CACHE_ROOT, "COLAB_MOUNT_ERROR→LOCAL"
    for cand in (CFG.GDRIVE_ROOT,
                 os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return CFG.LOCAL_CACHE_ROOT, "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
        self.ns = {"shared": os.path.join(self.root, CFG.GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, CFG.GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            for sub in ("index", os.path.join("index", "_backup"), "blob", "table"):
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, pd.DataFrame] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats: Counter = Counter()

    # ── 경로 ─────────────────────────────────────────────────────────────────
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 잠금 ─────────────────────────────────────────────────────────────────
    @contextmanager
    def lock(self, name: str, timeout: float = 60.0, stale: float = 900.0):
        lp = os.path.join(self.root, "_locks", f"{name}.lock")
        t0, acquired = time.time(), False
        while time.time() - t0 < timeout:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "host": platform.node(),
                                         "ts": time.time()}).encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                try:
                    info = json.loads(open(lp).read() or "{}")
                    if time.time() - float(info.get("ts", 0)) > stale:
                        os.remove(lp)
                        continue
                except Exception:                              # noqa: BLE001
                    try:
                        os.remove(lp)
                    except Exception:                          # noqa: BLE001
                        pass
                time.sleep(0.3)
        if not acquired:
            LOG.warn(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:                              # noqa: BLE001
                    pass

    # ── 인덱스 적재 (읽기 전용) ───────────────────────────────────────────────
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []
        d = read_parquet_safe(self.idx_parquet(scope))
        if d is not None and len(d):
            frames.append(d)
        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))
        idx_dir = os.path.join(self.ns[scope], "index")
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if not fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    continue
                fp = os.path.join(idx_dir, fn)
                try:
                    if fl.endswith(".parquet"):
                        dd = read_parquet_safe(fp)
                    elif fl.endswith(".csv"):
                        dd = pd.read_csv(fp)
                    elif fl.endswith(".jsonl"):
                        dd = pd.DataFrame(read_jsonl(fp))
                    else:
                        dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                except Exception:                              # noqa: BLE001
                    continue
                if dd is not None and len(dd):
                    dd = dd.copy()
                    dd["_legacy_file"] = fn
                    frames.append(dd)
                    self.stats[f"legacy_index_absorbed:{fn}"] += len(dd)
        except Exception:                                      # noqa: BLE001
            pass

        if frames:
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            idx = pd.concat([f.reindex(columns=allcols) for f in frames], ignore_index=True)
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | idx["uid"].astype(str).str.strip().isin(("", "nan", "None"))
            if bool(miss.any()):
                # uid 결측 행을 astype(str) 하면 전부 "nan" 이 되어 drop_duplicates 가
                # 그 파일 전체를 한 줄로 붕괴시킨다 = 인덱스 유실. 절대 1원칙 위반이므로 개별 부여.
                src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                   "_legacy_file") if c in idx.columns]
                pos = np.where(miss.to_numpy())[0]
                idx.loc[idx.index[pos], "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in src]) for i in pos]
                LOG.info(f"레거시 인덱스 {len(pos):,}행에 uid 부여 (기존 기록 보존)")
            idx["uid"] = idx["uid"].astype(str)
            if "collected_at" in idx.columns:
                idx = idx.sort_values("collected_at", kind="stable")
            idx = idx.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        else:
            idx = pd.DataFrame(columns=INDEX_COLUMNS)
        for c in INDEX_COLUMNS:
            if c not in idx.columns:
                idx[c] = np.nan
        idx["scope"] = idx["scope"].fillna(scope)
        with self._lk:
            self._idx[scope] = idx
            self._uidset[scope] = set(idx["uid"].astype(str).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope] or any(r.get("uid") == uid for r in self._pending[scope])

    def lookup(self, scope: str, **eq) -> pd.DataFrame:
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= idx[k].astype(str) == str(v)
        return idx[m]

    # ── 기록 ─────────────────────────────────────────────────────────────────
    def _register(self, scope: str, rec: dict) -> None:
        rec.setdefault("scope", scope)
        rec.setdefault("schema_ver", VAULT_SCHEMA_VER)
        rec.setdefault("collected_at", _dt.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("project", "g2b_demand_graph_v1")
        rec.setdefault("run_id", CFG.run_id())
        for c in INDEX_COLUMNS:
            rec.setdefault(c, None)
        with self._lk:
            self._pending[scope].append(rec)
            self._uidset.setdefault(scope, set()).add(str(rec["uid"]))
        self.stats[f"register:{scope}:{rec.get('domain')}"] += 1

    def put_blob(self, domain: str, subtype: str, key: str, data: bytes, fmt: str,
                 source: str = "", event_date=None, knowledge_date=None,
                 scope: str = "shared", extra: Optional[dict] = None,
                 uid: Optional[str] = None) -> Optional[str]:
        """원본 바이트를 내용해시 경로에 보존(§4 raw 불변). 같은 내용이면 재기록조차 하지 않는다."""
        if not data:
            return None
        h = sha1_bytes(data)
        uid = uid or sha1_str(domain, subtype, key, h)
        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])
        abspath = os.path.join(sub, f"{h}.{fmt.lstrip('.')}")
        if not os.path.exists(abspath):
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에도 남기지 않습니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": os.path.relpath(abspath, self.root), "abs_path": abspath, "fmt": fmt,
            "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "source": source, "adopted": False,
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str)})
        return abspath

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:                              # noqa: BLE001
                    continue
        return None

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "",
                  extra: Optional[dict] = None) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 덮어쓰지 않고 리비전 파일로 저장: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "", "source": source,
            "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:100]},
                                ensure_ascii=False, default=str)})
        self.stats[f"put_table:{scope}"] += 1
        return path

    def get_table(self, name: str, scope: str = "shared",
                  max_age_days: Optional[float] = None) -> Optional[pd.DataFrame]:
        """캐시 우선 조회. 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략 산출물도 재활용."""
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if not os.path.exists(path):
            alt = "private" if scope == "shared" else "shared"
            p2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if not os.path.exists(p2):
                return None
            path = p2
        if max_age_days is not None and (time.time() - os.path.getmtime(path)) / 86400.0 > max_age_days:
            return None
        d = read_parquet_safe(path)
        if d is not None:
            self.stats[f"cache_hit:{name}"] += 1
            LOG.debug(f"캐시 적중 {name}: {len(d):,}행 ← {os.path.relpath(path, self.root)}")
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str, source: str = "",
              event_date=None, knowledge_date=None, scope: str = "shared",
              extra: Optional[dict] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 경로만 등록한다."""
        try:
            sz = os.path.getsize(abs_path)
        except Exception:                                      # noqa: BLE001
            return None
        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)
        if self.has(scope, uid):
            return uid
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": abs_path, "abs_path": abs_path,
            "fmt": os.path.splitext(abs_path)[1].lstrip("."), "bytes": sz, "sha1": "",
            "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str)})
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ────────────────────────────────────────────────────────
    def flush(self, scope: Optional[str] = None) -> None:
        for sc in ([scope] if scope else ["shared", "private"]):
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)

    def compact(self, scope: str) -> None:
        self.flush(scope)
        idx = self.load_index(scope, force=True)
        p = self.idx_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                             # noqa: BLE001
                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 컴팩션을 건너뜁니다. "
                         f"저널이 원천이므로 유실 없음.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns
                                             if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션: {scope} — {len(idx):,}행")
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 감사 ─────────────────────────────────────────────────────────────────
    def report(self) -> None:
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc, ns in (("shared", CFG.GDRIVE_SHARED_NS), ("private", CFG.GDRIVE_PRIVATE_NS)):
            idx = self.load_index(sc)
            nb = float(pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum()) if len(idx) else 0.0
            nad = int(pd.to_numeric(idx.get("adopted"), errors="coerce").fillna(0).sum()) if len(idx) else 0
            rows.append([("공용 " + ns) if sc == "shared" else ("전용 " + ns), f"{len(idx):,}",
                         f"{nad:,}", f"{nb / 1e9:.3f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록", "용량", "저널"], ["l", "r", "r", "r", "l"])
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            if idx.empty or "domain" not in idx.columns:
                continue
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(20))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title=f"{'공용' if sc == 'shared' else '전용'} 인덱스 구성")
        if self.stats:
            LOG.table([[k, f"{v:,}"] for k, v in sorted(self.stats.items())][:30],
                      ["이벤트", "횟수"], ["l", "r"], title="이번 실행의 캐시 이벤트")
        LOG.info("무결성: 저널 append-only · index.parquet 백업 후 교체 · blob 내용해시 · 삭제 API 없음")


VAULT: Optional[Vault] = None


def get_vault() -> Vault:
    global VAULT
    if VAULT is None:
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        LOG.ok(f"VAULT 연결: {VAULT.root}  [{mode}]  "
               f"공용={CFG.GDRIVE_SHARED_NS} / 전용={CFG.GDRIVE_PRIVATE_NS}")
    return VAULT


# ==========================================================================================
#  core/http.py
# ==========================================================================================
"""HTTP 계층 + 불변 RAW 저장소 + 호출 매니페스트 + 스키마 레지스트리.

명세 대응:
  §4  API 호출마다 source_service/operation/request_params/requested_at/fetched_at/
      HTTP status/row_count/response_hash/schema_version/raw_filename 을 남긴다.
      raw 는 절대 덮어쓰지 않는다.
  §86 필드 스키마를 날짜별 버전으로 관리한다 (schema_registry/).
  §87 pagination · cache · incremental · retry/backoff · checkpoint · resume.
      동일 historical request 를 반복 호출하지 않는다.
"""



_TLS = threading.local()
HTTP_STATS: Dict[str, int] = {}
_STAT_LK = threading.Lock()


def _stat(k: str, n: int = 1) -> None:
    with _STAT_LK:
        HTTP_STATS[k] = HTTP_STATS.get(k, 0) + n


def _session():
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    import requests
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    try:
        s.mount("https://", HTTPAdapter(pool_connections=max(8, CFG.N_WORKERS_IO * 2),
                                        pool_maxsize=max(16, CFG.N_WORKERS_IO * 4)))
    except Exception:                                          # noqa: BLE001
        pass
    s.headers.update({"User-Agent": "g2b-demand-graph/1.0 (research)",
                      "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"})
    _TLS.sess = s
    return s


BUDGET = CallBudget(os.path.join(CFG.AUDIT_DIR, "call_budget.json"))


class ApiError(Exception):
    pass


def _decoding_key(key: str) -> str:
    """공공데이터포털 키. Encoding 키(%2B/%3D 포함)를 그대로 넣으면 이중 인코딩으로 401 이 난다."""
    if not key:
        return key
    if "%" in key:
        try:
            from urllib.parse import unquote
            dec = unquote(key)
            if dec != key:
                LOG.warn("DATA_GO_KR_SERVICE_KEY 가 Encoding 키로 보입니다 — Decoding 키로 자동 변환합니다.")
                return dec
        except Exception:                                      # noqa: BLE001
            pass
    return key


def http_json(url: str, params: Dict[str, Any], source: str = "datagokr",
              tries: int = 4, timeout: float = 40.0) -> Tuple[Optional[Any], Dict[str, Any]]:
    """(payload, meta). 예외를 삼키지 않고 meta 에 실패 사유를 남긴다."""
    cap = CFG.DAILY_CALL_BUDGET.get(source)
    if cap is not None and BUDGET.remaining(source, cap) <= 0:
        raise ApiError(f"[{source}] 일일 호출예산 {cap:,}회 소진 — 체크포인트를 남기고 중단합니다(§87).")
    qps = CFG.RATE_LIMIT_QPS.get(source, 3.0)
    meta: Dict[str, Any] = {"requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
                            "http_status": None, "error": "", "attempts": 0}
    last_exc = ""
    for k in range(tries):
        meta["attempts"] = k + 1
        limiter(source, qps).wait()
        try:
            r = _session().get(url, params=params, timeout=timeout)
            BUDGET.charge(source)
            meta["http_status"] = r.status_code
            _stat(f"{source}:{r.status_code}")
            if r.status_code in (429, 500, 502, 503, 504):
                last_exc = f"HTTP {r.status_code}"
                time.sleep(min(30.0, (1.8 ** k) + random.random()))
                continue
            if r.status_code != 200:
                meta["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
                return None, meta
            body = r.content
            meta["fetched_at"] = _dt.datetime.now().isoformat(timespec="seconds")
            meta["response_hash"] = sha256_bytes(body)
            meta["bytes"] = len(body)
            txt = body.decode("utf-8", errors="replace")
            try:
                return json.loads(txt), meta
            except Exception:                                  # noqa: BLE001
                # 공공데이터포털은 오류 시 JSON 대신 XML/HTML 을 200 으로 돌려준다.
                meta["error"] = "NON_JSON"
                meta["raw_text"] = txt[:800]
                return {"_raw_xml": txt}, meta
        except Exception as e:                                 # noqa: BLE001
            last_exc = f"{type(e).__name__}: {e}"
            _stat(f"{source}:exc")
            time.sleep(min(30.0, (1.8 ** k) + random.random()))
    meta["error"] = last_exc or "unknown"
    meta["fetched_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    return None, meta


# ══════════════════════════════════════════════════════════════════════════════
#  RAW 저장소 — 불변. 같은 요청을 두 번 하지 않는다.
# ══════════════════════════════════════════════════════════════════════════════
_REDACT = ("serviceKey", "ServiceKey", "crtfc_key", "key")


def request_uid(service: str, operation: str, params: Dict[str, Any]) -> str:
    p = {k: v for k, v in sorted(params.items()) if k not in _REDACT}
    return sha1_str("g2breq", service, operation, json.dumps(p, sort_keys=True, default=str))


class RawStore:
    """data/raw/<service>/ 아래에 응답 원본을 gzip 으로 보존하고 매니페스트를 append 한다.

    · 파일명은 요청 uid 기반 → 같은 요청은 같은 파일. 이미 있으면 네트워크에 나가지 않는다.
    · 매니페스트는 append-only JSONL. 기존 줄을 재기록하지 않는다.
    """

    def __init__(self, service: str):
        self.service = service
        self.dir = os.path.join(CFG.RAW_DIR, service)
        os.makedirs(self.dir, exist_ok=True)
        self.manifest_path = os.path.join(self.dir, "_manifest.jsonl")
        self._lk = threading.Lock()
        self._seen: Optional[Dict[str, dict]] = None

    def manifest(self) -> Dict[str, dict]:
        if self._seen is None:
            rows = read_jsonl(self.manifest_path)
            self._seen = {str(r.get("uid")): r for r in rows if r.get("uid")}
        return self._seen

    def has(self, uid: str) -> bool:
        return uid in self.manifest()

    def path_for(self, uid: str) -> str:
        return os.path.join(self.dir, uid[:2], f"{uid}.json.gz")

    def load(self, uid: str) -> Optional[Any]:
        p = self.path_for(uid)
        if not os.path.exists(p):
            return None
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:                                 # noqa: BLE001
            LOG.warn(f"raw 파손({type(e).__name__}) — 격리만 합니다: {p}")
            try:
                os.rename(p, p + ".corrupt")
            except Exception:                                  # noqa: BLE001
                pass
            return None

    def save(self, uid: str, operation: str, params: Dict[str, Any], payload: Any,
             meta: Dict[str, Any], row_count: int, schema_version: str) -> str:
        p = self.path_for(uid)
        if not os.path.exists(p):                      # 절대 덮어쓰지 않는다
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            atomic_write_bytes(p, gzip.compress(body, 6))
        rec = {"uid": uid, "source_service": self.service, "operation": operation,
               "request_params": {k: v for k, v in params.items() if k not in _REDACT},
               "requested_at": meta.get("requested_at"), "fetched_at": meta.get("fetched_at"),
               "http_status": meta.get("http_status"), "row_count": int(row_count),
               "response_hash": meta.get("response_hash", ""), "schema_version": schema_version,
               "raw_filename": os.path.relpath(p, CFG.PROJECT_ROOT),
               "bytes": meta.get("bytes", 0), "error": meta.get("error", ""),
               "run_id": CFG.run_id()}
        with self._lk:
            append_jsonl(self.manifest_path, [rec])
            if self._seen is not None:
                self._seen[uid] = rec
        return p

    def manifest_df(self) -> pd.DataFrame:
        rows = read_jsonl(self.manifest_path)
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["uid", "source_service", "operation", "row_count", "http_status"])


# ══════════════════════════════════════════════════════════════════════════════
#  체크포인트 — 중단 후 재개 (§87)
# ══════════════════════════════════════════════════════════════════════════════
class Checkpoint:
    def __init__(self, name: str):
        self.path = os.path.join(CFG.AUDIT_DIR, f"checkpoint_{name}.json")
        self.state: Dict[str, Any] = read_json(self.path, {}) or {}
        self._lk = threading.Lock()

    def done(self, key: str) -> bool:
        return bool(self.state.get(key))

    def mark(self, key: str, info: Any = True) -> None:
        with self._lk:
            self.state[key] = info
            if len(self.state) % 25 == 0:
                write_json(self.path, self.state)

    def save(self) -> None:
        with self._lk:
            write_json(self.path, self.state)


# ══════════════════════════════════════════════════════════════════════════════
#  스키마 레지스트리 (§86) — 필드 집합이 언제 바뀌었는지 날짜별로 기록
# ══════════════════════════════════════════════════════════════════════════════
def register_schema(service: str, operation: str, fields: List[str]) -> str:
    os.makedirs(CFG.SCHEMA_REGISTRY_DIR, exist_ok=True)
    fields = sorted(set(map(str, fields)))
    ver = sha1_str(service, operation, "|".join(fields))[:12]
    path = os.path.join(CFG.SCHEMA_REGISTRY_DIR, f"{service}.{operation}.jsonl")
    known = {r.get("schema_version") for r in read_jsonl(path)}
    if ver not in known:
        append_jsonl(path, [{"schema_version": ver, "service": service, "operation": operation,
                             "first_seen": _dt.date.today().isoformat(),
                             "n_fields": len(fields), "fields": fields,
                             "run_id": CFG.run_id()}])
        if known:
            LOG.warn(f"[§86] 스키마 변경 감지: {service}.{operation} → 새 버전 {ver} "
                     f"(기존 {len(known)}개). 과거·현재 식별자 정의가 같다고 가정하지 않습니다.")
    return ver


def report_http() -> None:
    if not HTTP_STATS:
        return
    LOG.table([[k, f"{v:,}"] for k, v in sorted(HTTP_STATS.items())],
              ["소스:상태", "건수"], ["l", "r"], title="HTTP 호출 통계")
    for src, cap in CFG.DAILY_CALL_BUDGET.items():
        LOG.info(f"호출예산 {src}: {BUDGET.used(src):,} / {cap:,} 사용")


# ==========================================================================================
#  pit/timestamps.py
# ==========================================================================================
"""PIT 시각 3종 + 필드 등급(CLASS A/B/C) 레지스트리.

명세 §6 — 각 레코드에 세 시간을 구분한다.
    event_time            실제로 사건이 일어난 시각 (발주예정시기·공고일·개찰일·계약체결일)
    source_published_at   원천이 그 정보를 공개한 시각 (등록일시·공고일시)
    available_at          우리가 그 정보를 쓸 수 있게 된 시각 = published + 공개지연

명세 §6.1 — 필드 3등급
    CLASS A  당시 공개시각과 값이 확정적으로 복원됨            → 사용 허용
    CLASS B  변경이력으로 PIT 복원 가능                        → revision 유효기간 복원 후 사용
    CLASS C  현재 API 가 과거 '최종값'만 반환하고 변경과정 불명 → 역사적 백테스트 사용 금지
             (PIT_UNCERTIFIED 로 표시)
"""



PIT_COLS = ("event_time", "source_published_at", "available_at")

# ── 공개지연(일). 발표가 장마감 전인지 확실하지 않으면 보수적으로 잡는다(§53) ──────────
#    나라장터는 등록 즉시 공개되지만 API 반영 지연이 존재하므로 스테이지별로 보수값을 둔다.
PUBLICATION_LAG_DAYS: Dict[str, float] = {
    "PLAN": 1.0,        # 발주계획: 게시 후 API 반영 지연
    "PRESPEC": 1.0,     # 사전규격
    "BID": 1.0,         # 입찰공고
    "AWARD": 1.0,       # 개찰/낙찰
    "CONTRACT": 2.0,    # 계약: 체결 후 등록까지 통상 더 걸린다
    "DART": 0.0,        # DART 는 접수시각 자체가 공개시각
}

# ══════════════════════════════════════════════════════════════════════════════
#  필드 등급 레지스트리 (§6.1)
#  ★ 여기 없는 필드는 자동으로 CLASS C 로 간주된다 — 모르면 쓰지 않는다가 기본값이다.
# ══════════════════════════════════════════════════════════════════════════════
FIELD_CLASS: Dict[str, str] = {}
FIELD_CLASS_NOTE: Dict[str, str] = {}


def declare(cls: str, fields: Sequence[str], note: str = "") -> None:
    assert cls in ("A", "B", "C")
    for f in fields:
        FIELD_CLASS[f] = cls
        FIELD_CLASS_NOTE[f] = note


declare("A", ["stage", "stage_rank", "doc_id", "agency_cd", "agency_nm", "proc_type",
              "event_time", "source_published_at", "available_at", "region_limit",
              "license_req", "category_cd", "category_nm", "broad_category"],
        "공고문에 그대로 실려 당시 값이 확정 복원됨")
declare("A", ["plan_budget_amt", "prespec_budget_amt", "bid_base_amt", "bid_est_amt"],
        "각 단계 공고 시점의 금액 — 그 시점 문서에 확정 기재")
declare("A", ["award_amt", "award_rate", "expected_price", "open_dt", "supplier_bizno",
              "supplier_nm", "bidder_count", "award_rank"],
        "개찰 결과는 개찰 시점에 확정 공개")
declare("B", ["bid_amt_current", "contract_amt_current", "bid_status", "contract_status",
              "revision_no", "valid_from", "valid_to", "is_cancelled", "is_rebid"],
        "변경이력 API 로 각 리비전의 유효기간을 복원해 사용")
declare("C", ["contract_final_amt", "contract_revision_ratio_final", "lifecycle_final_outcome",
              "final_winner", "total_contract_including_future_change",
              "reached_stage", "max_stage_rank", "winner_bizno", "winner_nm", "last_seen",
              "t_CONTRACT", "amt_CONTRACT"],
        "현재 API 가 과거 최종값만 반환 — 변경과정 복원 불가 → 역사적 백테스트 사용 금지")

# ── 정규 스키마 컬럼 (collectors.base.CANON_COLS) 등급 ─────────────────────────
#    'amount' 는 단계별 공고문에 확정 기재되지만 변경공고로 바뀔 수 있으므로 CLASS B 다:
#    리비전 유효구간을 복원해야만 PIT 로 쓸 수 있다. 이 구분을 흐리면 §8 이 무의미해진다.
declare("B", ["amount", "attributed_amount", "doc_seq", "amount_kind"],
        "각 판본 금액 — 변경이력으로 유효기간 복원 후 사용(§8)")
declare("A", ["title", "method", "share_ratio"],
        "공고문·개찰결과에 그 시점 값이 그대로 기재됨")
declare("B", ["status_raw"],
        "공고종류/상태는 변경공고로 바뀐다 — 리비전 유효기간 복원 후 사용")
declare("A", ["service", "operation", "raw_uid", "opportunity_id", "pit_stage",
              "published_imputed", "demand_agency_cd", "demand_agency_nm",
              "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
              "link_method", "link_score", "link_known_at", "giant_component",
              "consortium_flag", "consortium_unknown_share", "alloc_mode",
              "map_type", "stock_code", "synthetic", "broad_category", "month"],
        "수집 시점에 확정되어 이후 바뀌지 않는 식별·구조 필드")


def field_class(name: str) -> str:
    return FIELD_CLASS.get(name, "C")


def assert_pit_safe(cols: Sequence[str], where: str = "") -> None:
    """CLASS C 필드가 팩터 계산에 들어오면 즉시 막는다. 우회 파라미터를 두지 않는다."""
    bad = [c for c in cols if field_class(c) == "C"]
    if bad:
        raise PermissionError(
            f"[PIT_UNCERTIFIED] CLASS C 필드를 역사적 계산에 사용할 수 없습니다 (§6.1): {bad}"
            + (f" — 위치: {where}" if where else "")
            + "\n  CLASS C = 현재 API 가 과거 '최종값'만 돌려주고 변경과정을 알 수 없는 필드입니다.")


def class_table() -> pd.DataFrame:
    return pd.DataFrame({"field": list(FIELD_CLASS), "pit_class": list(FIELD_CLASS.values()),
                         "note": [FIELD_CLASS_NOTE.get(f, "") for f in FIELD_CLASS]}
                        ).sort_values(["pit_class", "field"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PIT 스탬프 부여
# ══════════════════════════════════════════════════════════════════════════════
def stamp(df: pd.DataFrame, event_col: str, published_col: Optional[str] = None,
          stage: str = "BID", lag_days: Optional[float] = None) -> pd.DataFrame:
    """event_time / source_published_at / available_at 세 컬럼을 붙인다.

    published 가 없으면 event_time 을 공개시각으로 쓰되, 그 사실이 감사표에 남도록
    `published_imputed` 플래그를 세운다. 조용히 같은 값으로 만들지 않는다.
    """
    d = df.copy()
    ev = as_ts_series(d[event_col]) if event_col in d.columns else pd.Series(pd.NaT, index=d.index)
    if published_col and published_col in d.columns:
        pb = as_ts_series(d[published_col])
        imputed = pb.isna()
        pb = pb.fillna(ev)
    else:
        pb = ev.copy()
        imputed = pd.Series(True, index=d.index)
    lag = float(PUBLICATION_LAG_DAYS.get(stage, 1.0) if lag_days is None else lag_days)
    d["event_time"] = ev
    d["source_published_at"] = pb
    # 공개시각을 모르면 event_time 기준이므로 보수적으로 지연을 더 얹는다.
    extra = np.where(imputed.to_numpy(), 1.0, 0.0)
    d["available_at"] = pb + pd.to_timedelta(lag + extra, unit="D")
    d["published_imputed"] = imputed.to_numpy()
    d["pit_stage"] = stage
    return d


def require_pit(df: pd.DataFrame, where: str = "") -> pd.DataFrame:
    """PIT 컬럼이 없으면 KeyError 로 거부한다 — 우회 인자를 의도적으로 만들지 않았다."""
    miss = [c for c in PIT_COLS if c not in df.columns]
    if miss:
        raise KeyError(f"PIT 컬럼 누락 {miss} — {where or 'unknown'} (명세 §6). "
                       f"pit.timestamps.stamp() 을 먼저 통과시키십시오.")
    bad = int((df["available_at"] < df["source_published_at"]).sum())
    if bad:
        raise ValueError(f"available_at < source_published_at 인 행 {bad:,}개 — {where}. "
                         f"이는 정의상 불가능하며 미래누수의 직접 증거입니다.")
    return df


def audit_lag(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """event → published → available 지연 분포. 커버리지 보고서(§94 01_PIT_AUDIT)용."""
    d = require_pit(df, name)
    lag1 = (d["source_published_at"] - d["event_time"]).dt.total_seconds() / 86400.0
    lag2 = (d["available_at"] - d["source_published_at"]).dt.total_seconds() / 86400.0
    q = lambda s, p: float(np.nanpercentile(s.dropna(), p)) if s.notna().any() else np.nan
    return pd.DataFrame([{
        "table": name, "rows": len(d),
        "event_time_결측률": float(d["event_time"].isna().mean()),
        "published_추정률": float(d.get("published_imputed", pd.Series(False, index=d.index)).mean()),
        "pub-event_p50": q(lag1, 50), "pub-event_p95": q(lag1, 95),
        "avail-pub_p50": q(lag2, 50),
        "event_min": d["event_time"].min(), "event_max": d["event_time"].max(),
    }])


# ══════════════════════════════════════════════════════════════════════════════
#  파생 피처 등급 (§6.1 확장)
#
#  파생 피처는 '원천 필드'가 아니라 그 함수다. 따라서 등급은 입력의 등급을 물려받는다:
#  아래 목록은 전부 CLASS A/B 입력만으로, 시점 t 까지 available_at 인 이벤트만 써서
#  계산된다는 것을 개발자가 명시적으로 선언한 것이다.
#
#  ★ 여기 없는 피처는 자동으로 CLASS C 가 되어 파이프라인이 멈춘다.
#    새 피처를 추가하려면 반드시 여기에 등급을 선언해야 한다 — 그것이 이 장치의 목적이다.
# ══════════════════════════════════════════════════════════════════════════════
DERIVED_FEATURES = [
    # capability / TAM (§17 §21)
    "capability", "decayed_award", "firm_decayed_total", "n_obs_36m", "first_award_month",
    "months_since_first_award", "warmed_up", "agency_share", "capability_hhi",
    "n_active_categories",
    "eligible_demand_flow", "eligible_demand_flow_3m", "eligible_demand_flow_12m",
    "eligible_pipeline_stock", "eligible_demand_flow_lofo",
    # 정부수요 (§20 §24 §45 §83)
    "demand_flow", "demand_flow_3m", "demand_flow_12m", "demand_flow_w", "pipeline_stock",
    "n_new_opp", "own_flow_known", "incumbent_share", "new_agency_flow_share",
    "best_amount", "is_advance", "is_revision", "is_first_seen", "amount_increment",
    "D1_DS_YOY", "D1_DS_YOY_LOFO", "D2_PIPELINE", "D2_PIPELINE_YOY",
    # 단계확률 (§22 §23)
    "p_contract", "n_train", "p_source",
    # 수주 실현 (§25 §26 §27)
    "award_amt", "award_n", "contract_amt", "contract_n",
    "award_amt_3m", "award_amt_6m", "award_amt_12m", "award_amt_ttm", "award_amt_prev9m",
    "award_n_3m", "award_n_6m", "award_n_12m", "contract_amt_12m", "award_ttm_lag12",
    "win_accel_rate", "win_accel_log", "W_PRIMARY",
    "WIN_MCAP", "WIN_MCAP_3M", "WIN_SALES", "CONTRACT_MCAP", "CONTRACT_SALES",
    "pit_revenue", "sales_filing_ts",
    # 저변 (§30 §31 §32)
    "new_agency_count", "new_agency_amt", "tot_agency_amt", "new_agency_award_share",
    "active_agency_count", "new_category_count", "new_category_amt", "tot_category_amt",
    "new_category_award_share", "active_category_count",
    "repeat_pairs", "active_pairs", "REPEAT_WIN_RATE", "breadth_warmed_up",
    # 경쟁·낙찰률 (§35 §36 §37) — 진단용이며 PRIMARY 부호를 붙이지 않는다
    "award_rate_use", "award_rate_mean", "resid_award_rate", "award_rate_n",
    "bidder_count_mean", "resid_bidder_count", "fail_rate", "rebid_rate",
    "FAIL_RATE_exposure", "REBID_RATE_exposure",
    # 집중도·위험 (§33 §34 §40 §41 §42 §43)
    "AGENCY_HHI", "CATEGORY_HHI", "TOP1_SHARE", "TOP3_SHARE", "PROC_RISK",
    "CONTRACT_REVISION_RATIO", "contract_increase_n", "contract_decrease_n",
    "contract_cancel_n", "contract_delta_amt",
    # PRIMARY (§28 §44)
    "P_D", "P_W", "G2B_DWA",
    "P_D_raw", "P_W_raw", "G2B_DWA_raw", "P_D_sec", "P_W_sec", "G2B_DWA_sec",
    "P_D_secsz", "P_W_secsz", "G2B_DWA_secsz",
    # 시장 속성 (PIT 가격 DB 에서 온 당시 값)
    "sector", "market", "mcap", "turnover_value", "ret", "close", "shares", "name",
    "listing_date", "delisting_date", "delisted",
]
declare("A", DERIVED_FEATURES,
        "CLASS A/B 입력만으로 available_at <= t 이벤트에서 계산된 파생 피처")

# 미래수익률 계열 — 신호에 들어가면 절대 안 되는 것들을 명시적으로 C 로 못박는다(§1.1 §7)
declare("C", ["forward_return", "future_price", "future_market_cap", "future_financial",
              "future_contract_outcome", "future_winner", "future_revenue",
              "fwd_ret_1m", "fwd_ret_3m", "fwd_ret_6m", "fwd_ret_12m",
              "fwd_award_3m", "fwd_award_6m", "fwd_award_12m",
              "fwd_contract_3m", "fwd_contract_6m", "fwd_contract_12m"],
        "미래정보 — 신호/팩터 입력으로 사용 금지. 성과검정과 메커니즘 검정에서만 등장한다.")


# ==========================================================================================
#  pit/revisions.py
# ==========================================================================================
"""변경이력 → PIT 리비전 구간 복원, 그리고 §8 이중계산 방지의 핵심 산식.

명세 §8 — 같은 입찰공고의 변경공고를 새로운 정부수요로 중복 계산하지 않는다.
    원공고 100억 → 수정공고 100억  ⇒ 신규수요 0    (200억이 아니다)
    원공고 100억 → 수정공고 120억  ⇒ 신규수요 +20억
    공고취소 / 재공고 / 재입찰      ⇒ 금액이 아니라 '상태변수'로 남긴다

명세 §6 CLASS B — 각 리비전의 유효기간(valid_from/valid_to)을 복원해야 PIT 로 쓸 수 있다.

전부 벡터화되어 있다 (groupby + shift/diff). 기업·월 루프가 없다.
"""



# 상태 변수(§8) — 금액 흐름과 절대 섞지 않는다
STATE_FLAGS = ("is_cancelled", "is_rebid", "is_reannounce", "is_failed")


def assign_revisions(df: pd.DataFrame, key_cols: Sequence[str],
                     time_col: str = "available_at",
                     tiebreak_cols: Sequence[str] = ()) -> pd.DataFrame:
    """같은 문서(key)의 여러 판본에 revision_no / valid_from / valid_to 를 부여한다.

    valid_to 는 '다음 리비전이 공개된 시각'이다. 마지막 리비전은 NaT(열린 구간).
    → 시점 t 에서 유효한 판본은 valid_from <= t < valid_to 인 단 하나.
    """
    key_cols = list(key_cols)
    if df is None or len(df) == 0:
        out = df.copy() if df is not None else pd.DataFrame()
        for c in ("revision_no", "valid_from", "valid_to"):
            out[c] = pd.Series(dtype="float64" if c == "revision_no" else "datetime64[ns]")
        return out
    order = key_cols + [time_col] + list(tiebreak_cols)
    d = df.sort_values(order, kind="stable").reset_index(drop=True)
    g = d.groupby(key_cols, sort=False, dropna=False)
    d["revision_no"] = g.cumcount().astype("int32")
    d["valid_from"] = d[time_col]
    d["valid_to"] = g[time_col].shift(-1)
    # 같은 시각에 두 판본이 있으면 구간 길이가 0 이 되어 조회에서 사라진다 → 뒤 판본을 채택.
    zero = d["valid_to"].notna() & (d["valid_to"] <= d["valid_from"])
    if bool(zero.any()):
        d.loc[zero, "valid_to"] = d.loc[zero, "valid_from"]
    d["is_latest_known"] = d["valid_to"].isna()
    return d


def effective_at(df: pd.DataFrame, as_of, key_cols: Sequence[str]) -> pd.DataFrame:
    """시점 as_of 에서 각 key 의 '그때 유효했던' 판본만 남긴다 (§7 graph.asof)."""
    t = pd.Timestamp(as_of)
    d = df[(df["valid_from"] <= t) & (df["valid_to"].isna() | (df["valid_to"] > t))]
    return d.sort_values(list(key_cols) + ["revision_no"], kind="stable")


def amount_increments(df: pd.DataFrame, key_cols: Sequence[str], amount_col: str,
                      out_col: str = "amount_increment") -> pd.DataFrame:
    """§8 신규 정부수요 = 금액의 '증분'. 첫 판본은 전액, 이후는 차분.

    합계 보존성: 한 key 의 증분 합 = 그 key 의 마지막 판본 금액.
    → 어떤 순서로 집계해도 이중계산이 원천적으로 불가능하다.
    """
    key_cols = list(key_cols)
    d = df.sort_values(key_cols + ["revision_no"], kind="stable").copy()
    a = pd.to_numeric(d[amount_col], errors="coerce")
    prev = a.groupby([d[c] for c in key_cols], sort=False, dropna=False).shift(1)
    d[out_col] = a - prev.fillna(0.0)
    # 금액 결측 판본은 증분 0 (모르는 것을 0 원 감액으로 해석하지 않는다)
    d.loc[a.isna(), out_col] = np.nan
    d[out_col] = d[out_col].where(a.notna())
    return d


def normalize_states(df: pd.DataFrame, status_col: Optional[str] = None) -> pd.DataFrame:
    """상태 문자열 → 상태 플래그(§8). 금액 팩터에 부호로 섞지 않는다."""
    d = df.copy()
    s = d[status_col].astype(str) if status_col and status_col in d.columns else pd.Series("", index=d.index)
    d["is_cancelled"] = s.str.contains("취소|철회|무효", regex=True, na=False)
    d["is_rebid"] = s.str.contains("재입찰", regex=True, na=False)
    d["is_reannounce"] = s.str.contains("재공고", regex=True, na=False)
    d["is_failed"] = s.str.contains("유찰", regex=True, na=False)
    for c in STATE_FLAGS:
        d[c] = d[c].fillna(False).astype(bool)
    return d


def revision_audit(df: pd.DataFrame, key_cols: Sequence[str], amount_col: str,
                   name: str = "") -> pd.DataFrame:
    """리비전 처리가 실제로 이중계산을 막았는지 수치로 보인다 (§92 회귀 테스트가 이 값을 본다)."""
    key_cols = list(key_cols)
    d = amount_increments(assign_revisions(df, key_cols), key_cols, amount_col)
    naive = float(pd.to_numeric(d[amount_col], errors="coerce").sum())
    correct = float(pd.to_numeric(d["amount_increment"], errors="coerce").sum())
    last = (d.sort_values(key_cols + ["revision_no"]).groupby(key_cols, dropna=False)[amount_col]
            .last().pipe(pd.to_numeric, errors="coerce").sum())
    return pd.DataFrame([{
        "table": name, "행수": len(d), "문서수": int(d.groupby(key_cols, dropna=False).ngroups),
        "리비전보유문서": int((d.groupby(key_cols, dropna=False)["revision_no"].max() > 0).sum()),
        "순진한합계": naive, "증분합계": correct, "최종판본합계": float(last),
        "이중계상액": naive - correct,
        "증분=최종판본": bool(abs(correct - float(last)) < max(1.0, abs(float(last)) * 1e-9)),
    }])


# ==========================================================================================
#  pit/asof.py
# ==========================================================================================
"""PIT 저장소와 as-of 조회. 시점 t 의 계산은 t 까지 알려진 정보만 볼 수 있다 (§7).

  · 등록: PIT.register(name, df)  — available_at 없는 프레임은 KeyError 로 거부한다.
  · 조회: PIT.asof(name, t)            (단일 시점 스냅샷)
          PIT.asof_join(left, name, ...)(벡터화 등가물 — merge_asof backward)
  우회 인자를 의도적으로 만들지 않았다. 조회 경로가 둘뿐이므로 감사가 가능하다.
"""




class PITStore:
    def __init__(self) -> None:
        self._t: Dict[str, pd.DataFrame] = {}
        self._keys: Dict[str, List[str]] = {}
        self.access_log: List[dict] = []

    def register(self, name: str, df: pd.DataFrame, key_cols: Sequence[str] = ()) -> None:
        d = require_pit(df, f"PIT.register({name})")
        d = d.sort_values("available_at", kind="stable").reset_index(drop=True)
        self._t[name] = d
        self._keys[name] = list(key_cols)
        LOG.debug(f"PIT 등록 {name}: {len(d):,}행  available_at "
                  f"{d['available_at'].min()} ~ {d['available_at'].max()}")

    def names(self) -> List[str]:
        return list(self._t)

    def raw(self, name: str) -> pd.DataFrame:
        """as-of 를 거치지 않는 원본 접근. 감사/진단 전용이며 팩터 계산에서 쓰면 안 된다."""
        return self._t[name]

    def asof(self, name: str, t) -> pd.DataFrame:
        """시점 t 까지 '알 수 있었던' 행만. available_at <= t."""
        t = pd.Timestamp(t)
        d = self._t[name]
        i = int(np.searchsorted(d["available_at"].to_numpy(), np.datetime64(t), side="right"))
        self.access_log.append({"table": name, "as_of": t, "rows": i})
        return d.iloc[:i]

    def asof_join(self, left: pd.DataFrame, name: str, by: Sequence[str], left_time: str,
                  cols: Optional[Sequence[str]] = None, suffix: str = "") -> pd.DataFrame:
        """벡터화 as-of 결합: left 각 행의 시각 기준으로 가장 최근 '알려진' 값을 붙인다."""
        by = list(by)
        R = self._t[name]
        take = list(dict.fromkeys(list(by) + ["available_at"] + list(cols or
                    [c for c in R.columns if c not in by])))
        take = [c for c in take if c in R.columns]
        R = R[take].sort_values("available_at", kind="stable")
        L = left.sort_values(left_time, kind="stable").copy()
        L[left_time] = pd.to_datetime(L[left_time])
        for c in by:
            if c in L.columns and c in R.columns:
                R[c] = R[c].astype(L[c].dtype, errors="ignore")
        ren = {c: c + suffix for c in R.columns if c not in by and c != "available_at" and suffix}
        out = pd.merge_asof(L, R.rename(columns=ren), left_on=left_time, right_on="available_at",
                            by=by, direction="backward", allow_exact_matches=True)
        self.access_log.append({"table": name, "as_of": "vectorized", "rows": len(out)})
        return out


PIT = PITStore()


def asof_panel(events: pd.DataFrame, months: pd.DatetimeIndex, value_col: str,
               group_cols: Sequence[str], how: str = "sum") -> pd.DataFrame:
    """이벤트 → (group × month) 패널. 각 이벤트는 available_at 이 속한 '월말' 이후부터 보인다.

    벡터화 규칙: available_at 이 M월 말일 이전이면 M월 신호에 포함, 아니면 다음 달로 넘어간다.
    이것이 §53(월말까지 공개된 데이터로 신호 계산)의 구현이다.
    """
    group_cols = list(group_cols)
    if events is None or len(events) == 0:
        return pd.DataFrame(columns=group_cols + ["month", value_col])
    e = events.copy()
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    # available_at 이 월말 '당일'이면 그 달에 포함(월말 종가 기준 신호 → T+1 체결이므로 안전)
    agg = e.groupby(group_cols + ["month"], dropna=False, observed=True)[value_col]
    P = (agg.sum() if how == "sum" else agg.mean()).reset_index()
    return P[P["month"].isin(months)] if len(months) else P


def expand_monthly(panel: pd.DataFrame, months: pd.DatetimeIndex, group_cols: Sequence[str],
                   value_cols: Sequence[str], fill: float = 0.0) -> pd.DataFrame:
    """희소 패널을 (group × 전체월) 조밀 격자로 확장한다. 롤링/EWM 이 월 결손에 흔들리지 않게."""
    group_cols, value_cols = list(group_cols), list(value_cols)
    if panel is None or len(panel) == 0:
        return pd.DataFrame(columns=group_cols + ["month"] + value_cols)
    keys = panel[group_cols].drop_duplicates()
    grid = keys.merge(pd.DataFrame({"month": months}), how="cross")
    out = grid.merge(panel, on=group_cols + ["month"], how="left")
    for c in value_cols:
        if c in out.columns:
            out[c] = out[c].fillna(fill)
        else:
            out[c] = fill
    return out.sort_values(group_cols + ["month"], kind="stable").reset_index(drop=True)


# ==========================================================================================
#  collectors/base.py
# ==========================================================================================
"""수집기 공통 계층 — 정규 스키마 · 내성 필드매핑 · 창(window) 페이징 · 캐시/체크포인트.

설계 원칙
  ① 필드명을 하나로 가정하지 않는다. 나라장터 서비스는 같은 뜻의 필드를 서비스마다
     다른 이름으로 준다(bidNtceNo / bidNtceNoOrd / ntceNo …). 후보 리스트로 매핑하고
     '무엇을 못 찾았는지'를 반드시 보고한다. 조용히 0 을 만들지 않는다.
  ② 같은 historical 요청을 두 번 하지 않는다(§87). RawStore 매니페스트가 진실.
  ③ raw 는 불변. 정규화는 언제든 raw 에서 재생성 가능해야 한다(§4).
  ④ 모든 정규 레코드는 pit.timestamps.stamp() 를 통과한다(§6).
"""



G2B_BASE = "https://apis.data.go.kr/1230000/"

STAGE_RANK = {"PLAN": 1, "PRESPEC": 2, "BID": 3, "AWARD": 4, "CONTRACT": 5}

# 정규 이벤트 스키마 — 6개 서비스가 모두 이 모양으로 수렴한다.
CANON_COLS = [
    "stage", "stage_rank", "service", "operation", "proc_type",
    "doc_id", "doc_seq", "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
    "agency_cd", "agency_nm", "demand_agency_cd", "demand_agency_nm",
    "category_cd", "category_nm", "title",
    "amount", "amount_kind", "expected_price", "award_rate", "bidder_count", "award_rank",
    "supplier_bizno", "supplier_nm", "share_ratio", "consortium_flag",
    "method", "region_limit", "license_req", "status_raw",
    "event_time", "source_published_at", "raw_uid",
]


def _first(rec: Dict[str, Any], names: Sequence[str]) -> Any:
    for n in names:
        if n in rec:
            v = rec[n]
            if v is not None and str(v).strip() not in ("", "-", "null", "None"):
                return v
    return None


@dataclass
class FieldMap:
    """정규컬럼 → API 필드명 후보들. 실제로 무엇이 잡혔는지 통계를 남긴다."""
    mapping: Dict[str, Sequence[str]]
    hits: Dict[str, int] = field(default_factory=dict)
    seen_fields: set = field(default_factory=set)

    def apply(self, records: List[dict]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=list(self.mapping))
        for r in records[:2000]:
            self.seen_fields.update(r.keys())
        out: Dict[str, List[Any]] = {}
        for canon, cands in self.mapping.items():
            col = [_first(r, cands) for r in records]
            n = sum(1 for v in col if v is not None)
            self.hits[canon] = self.hits.get(canon, 0) + n
            out[canon] = col
        return pd.DataFrame(out)

    def coverage(self, n_rows: int) -> pd.DataFrame:
        return pd.DataFrame([{"정규컬럼": k, "매핑후보": ",".join(self.mapping[k][:3]),
                              "채워진행": self.hits.get(k, 0),
                              "커버리지": (self.hits.get(k, 0) / n_rows) if n_rows else np.nan}
                             for k in self.mapping]).sort_values("커버리지")

    def unmapped(self) -> List[str]:
        used = {n for c in self.mapping.values() for n in c}
        return sorted(self.seen_fields - used)


@dataclass
class ServiceSpec:
    """하나의 나라장터 서비스 정의."""
    service: str                     # 내부 이름 (raw 디렉터리명)
    portal_id: str                   # 공공데이터포털 데이터셋 ID
    path: str                        # 서비스 경로 (…/1230000/<path>/)
    stage: str                       # PLAN / PRESPEC / BID / AWARD / CONTRACT / LINK
    operations: Dict[str, str]       # {업무구분: 오퍼레이션명}
    date_params: Tuple[str, str]     # (시작, 종료) 파라미터명
    date_fmt: str                    # "%Y%m%d%H%M" or "%Y%m%d"
    fieldmap: Dict[str, Sequence[str]]
    amount_kind: str
    official_range: str = ""
    notes: str = ""


def _items_of(payload: Any) -> List[dict]:
    """공공데이터포털 응답에서 item 리스트를 꺼낸다. 형태가 4가지쯤 된다."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    if "_raw_xml" in payload:
        return []
    body = payload.get("response", {}).get("body") if "response" in payload else payload
    if not isinstance(body, dict):
        return []
    items = body.get("items", body.get("item"))
    if items is None:
        return []
    if isinstance(items, dict):
        it = items.get("item", items)
        return [it] if isinstance(it, dict) else ([x for x in it if isinstance(x, dict)]
                                                   if isinstance(it, list) else [])
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    return []


def _total_of(payload: Any) -> Optional[int]:
    try:
        body = payload.get("response", {}).get("body", {})
        return int(body.get("totalCount"))
    except Exception:                                          # noqa: BLE001
        return None


def _result_msg(payload: Any) -> str:
    try:
        h = payload.get("response", {}).get("header", {})
        return f"{h.get('resultCode', '')} {h.get('resultMsg', '')}".strip()
    except Exception:                                          # noqa: BLE001
        return ""


def windows(start: str, end: str, freq: str = "MS") -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """수집 창 목록. 월 단위가 기본 — 창이 너무 크면 API 가 상한에서 잘라버린다."""
    s = pd.Timestamp(start).normalize().replace(day=1)
    e = pd.Timestamp(end).normalize()
    out = []
    for m in pd.date_range(s, e, freq=freq):
        w0 = m
        w1 = min(m + pd.offsets.MonthEnd(0), e)
        if w1 >= w0:
            out.append((w0, w1))
    return out


def fetch_window(spec: ServiceSpec, operation: str, w0: pd.Timestamp, w1: pd.Timestamp,
                 store: RawStore, max_pages: Optional[int] = None,
                 extra_params: Optional[dict] = None) -> Tuple[List[dict], Dict[str, Any]]:
    """한 창(window)을 페이징 수집. 이미 raw 에 있으면 네트워크에 나가지 않는다(§87)."""
    key = _decoding_key(CFG.DATA_GO_KR_SERVICE_KEY)
    fmt = spec.date_fmt
    d0 = w0.strftime(fmt) if len(fmt) > 8 else w0.strftime(fmt)
    d1 = (w1.strftime("%Y%m%d") + "2359") if fmt == "%Y%m%d%H%M" else w1.strftime(fmt)
    if fmt == "%Y%m%d%H%M":
        d0 = w0.strftime("%Y%m%d") + "0000"
    rows: List[dict] = []
    info = {"pages": 0, "from_cache": 0, "fetched": 0, "errors": [], "total": None, "msg": ""}
    max_pages = max_pages or CFG.MAX_PAGES_PER_WINDOW
    for page in range(1, max_pages + 1):
        params = {"serviceKey": key, "numOfRows": CFG.PAGE_ROWS, "pageNo": page,
                  "inqryDiv": "1", "type": "json",
                  spec.date_params[0]: d0, spec.date_params[1]: d1}
        params.update(extra_params or {})
        uid = request_uid(spec.service, operation, params)
        payload = None
        if store.has(uid):
            payload = store.load(uid)
            if payload is not None:
                info["from_cache"] += 1
        if payload is None:
            if CFG.RUN_MODE == "CACHED":
                break
            if not key:
                info["errors"].append("NO_KEY")
                break
            payload, meta = http_json(G2B_BASE + spec.path + "/" + operation, params,
                                      source="datagokr")
            if payload is None:
                info["errors"].append(meta.get("error", "unknown"))
                break
            its0 = _items_of(payload)
            store.save(uid, operation, params, payload, meta, len(its0),
                       register_schema(spec.service, operation,
                                       sorted({k for r in its0[:200] for k in r})) if its0 else "empty")
            info["fetched"] += 1
        its = _items_of(payload)
        if info["total"] is None:
            info["total"] = _total_of(payload)
            info["msg"] = _result_msg(payload)
        info["pages"] += 1
        rows.extend(its)
        if len(its) < CFG.PAGE_ROWS:
            break
        if info["total"] is not None and len(rows) >= info["total"]:
            break
    return rows, info


def collect_service(spec: ServiceSpec, start: str, end: str,
                    ops: Optional[Sequence[str]] = None,
                    freq: str = "MS") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """서비스 전체 기간 수집 → (정규화 이벤트, 수집 감사표). 중단 후 재개 가능."""
    store = RawStore(spec.service)
    ckpt = Checkpoint(spec.service)
    fm = FieldMap(spec.fieldmap)
    op_items = [(k, v) for k, v in spec.operations.items() if (ops is None or k in ops)]
    wins = windows(start, end, freq)
    all_rows: List[dict] = []
    audit: List[dict] = []
    for proc_type, operation in op_items:
        for (w0, w1) in wins:
            ckey = f"{operation}|{w0:%Y%m}"
            try:
                rows, info = fetch_window(spec, operation, w0, w1, store)
            except ApiError as e:
                LOG.warn(f"{spec.service}/{operation} {w0:%Y-%m} 중단: {e}")
                ckpt.save()
                audit.append({"service": spec.service, "operation": operation, "proc_type": proc_type,
                              "window": f"{w0:%Y-%m}", "rows": 0, "pages": 0, "from_cache": 0,
                              "error": "BUDGET_EXHAUSTED"})
                return _finish(spec, fm, all_rows, audit, store)
            for r in rows:
                r["_proc_type"] = proc_type
                r["_operation"] = operation
            all_rows.extend(rows)
            ckpt.mark(ckey, {"rows": len(rows), "pages": info["pages"]})
            audit.append({"service": spec.service, "operation": operation, "proc_type": proc_type,
                          "window": f"{w0:%Y-%m}", "rows": len(rows), "pages": info["pages"],
                          "from_cache": info["from_cache"], "fetched": info["fetched"],
                          "total_reported": info["total"],
                          "error": ";".join(map(str, info["errors"]))[:120],
                          "msg": info["msg"][:80]})
    ckpt.save()
    return _finish(spec, fm, all_rows, audit, store)


def _finish(spec: ServiceSpec, fm: FieldMap, rows: List[dict], audit: List[dict],
            store: RawStore) -> Tuple[pd.DataFrame, pd.DataFrame]:
    A = pd.DataFrame(audit)
    if not rows:
        return pd.DataFrame(columns=CANON_COLS), A
    D = fm.apply(rows)
    D["service"] = spec.service
    D["stage"] = spec.stage
    D["stage_rank"] = STAGE_RANK.get(spec.stage, 0)
    D["amount_kind"] = spec.amount_kind
    D["proc_type"] = [r.get("_proc_type") for r in rows]
    D["operation"] = [r.get("_operation") for r in rows]
    D = normalize_common(D)
    if fm.unmapped():
        LOG.info(f"{spec.service}: 미매핑 필드 {len(fm.unmapped())}개 (raw 에는 보존됨) "
                 f"예: {fm.unmapped()[:8]}")
    return D, A


_NUM = re.compile(r"[^0-9.\-]")


def to_amount(s: pd.Series) -> pd.Series:
    """'1,234,000원' 같은 문자열 금액을 숫자로. 콤마를 안 지우면 전부 NaN 이 된다."""
    if s.dtype.kind in "if":
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(s.astype(str).str.replace(_NUM, "", regex=True).replace("", np.nan),
                         errors="coerce")


def normalize_common(D: pd.DataFrame) -> pd.DataFrame:
    d = D.copy()
    for c in CANON_COLS:
        if c not in d.columns:
            d[c] = np.nan
    for c in ("amount", "expected_price", "award_rate", "bidder_count", "award_rank", "share_ratio"):
        d[c] = to_amount(d[c])
    for c in ("supplier_bizno",):
        d[c] = d[c].map(digits).replace("", np.nan)
    for c in ("doc_id", "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
              "agency_cd", "agency_nm", "demand_agency_cd", "demand_agency_nm",
              "category_cd", "category_nm", "title", "supplier_nm", "method",
              "region_limit", "license_req", "status_raw", "proc_type"):
        d[c] = d[c].astype("string").str.strip()
    d["event_time"] = _parse_dt(d["event_time"])
    d["source_published_at"] = _parse_dt(d["source_published_at"])
    return d[CANON_COLS]


def _parse_dt(s: pd.Series) -> pd.Series:
    """'20240115' / '2024-01-15 13:20:00' / '202401151320' 를 모두 받는다."""
    x = s.astype("string").str.strip()
    x = x.str.replace(r"[^\d]", "", regex=True)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for ln, fmt in ((14, "%Y%m%d%H%M%S"), (12, "%Y%m%d%H%M"), (8, "%Y%m%d"), (6, "%Y%m")):
        m = out.isna() & (x.str.len() == ln)
        if bool(m.any()):
            out.loc[m] = pd.to_datetime(x[m], format=fmt, errors="coerce")
    m = out.isna() & x.notna() & (x.str.len() > 0)
    if bool(m.any()):
        out.loc[m] = pd.to_datetime(s[m], errors="coerce")
    return out


def stamp_stage(D: pd.DataFrame, stage: str) -> pd.DataFrame:
    """정규 이벤트에 PIT 3시각을 부여한다."""
    return stamp(D, "event_time", "source_published_at", stage=stage)


# ==========================================================================================
#  collectors/order_plan.py
# ==========================================================================================
"""발주계획현황서비스 (공공데이터포털 15129462) — 조달대상·예산액·발주예정시기·발주방법·발주기관.

공식 메타데이터 시간범위 2004-12~. 단 '발주계획이 없는 입찰·계약도 존재'한다고 명시되어 있으므로
연결 실패를 사건 실패로 간주하지 않는다(§2.F).
이 단계는 winner 를 보기 전 정보라 §20 외생적 정부수요의 최선행 원천이다.
"""

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


# ==========================================================================================
#  collectors/prespec.py
# ==========================================================================================
"""사전규격정보서비스 (15129437) — 사전규격등록번호·사업명·배정예산액·발주기관·규격서 의견.

사전규격은 입찰공고보다 앞선 정보이므로 선행신호로 매우 중요하다(§2.B).
"""

SPEC_PRESPEC = ServiceSpec(
    service="prespec", portal_id="15129437", path="HrcspSsstndrdInfoService", stage="PRESPEC",
    operations={"물품": "getPublicPrcureThngInfoThng", "공사": "getPublicPrcureThngInfoCnstwk",
                "용역": "getPublicPrcureThngInfoServc", "외자": "getPublicPrcureThngInfoFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="BUDGET", official_range="사전규격 공개 개시 이후",
    fieldmap={
        "doc_id": ["bfSpecRgstNo", "prearngSpecRgstNo", "specRgstNo", "rgstNo"],
        "doc_seq": ["bfSpecRgstNoOrd", "chgOrd", "ord"],
        "title": ["prdctClsfcNoNm", "bfSpecNm", "bizNm", "cnstwkNm", "servcNm", "prdctNm"],
        "agency_cd": ["orderInsttCd", "rlDminsttCd", "ntceInsttCd"],
        "agency_nm": ["orderInsttNm", "rlDminsttNm", "ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "clsfcNo", "cnstwkKindCd"],
        "category_nm": ["prdctClsfcNoNm", "clsfcNoNm", "cnstwkKindNm"],
        "amount": ["asignBdgtAmt", "bdgtAmt", "prdctUprc", "asignBdgtAmtSum"],
        "link_bid_no": ["bidNtceNo", "refNo"],
        "event_time": ["rgstDt", "specRgstDt", "regDt"],
        "source_published_at": ["rgstDt", "regDt", "opninRgstBgnDt"],
        "status_raw": ["opninRgstClseDt", "sttusNm", "specDocNm"],
        "license_req": ["indstrytyNm", "lcnsLmtNm"],
    },
    notes="규격서 의견(opninRgstClseDt)은 의견수렴 마감 — 입찰공고 시점의 선행지표.")


def collect_prespec(start: str, end: str, **kw):
    D, A = collect_service(SPEC_PRESPEC, start, end, **kw)
    return (stamp_stage(D, "PRESPEC") if len(D) else D), A


# ==========================================================================================
#  collectors/bid.py
# ==========================================================================================
"""입찰공고정보서비스 (15129394) — 공고·기초금액·면허제한·참가가능지역·변경이력.

공식 메타데이터 시간범위 1995-10~ 로 표기되어 있으나 그대로 믿지 않고 §5 실측한다.
ntceKindNm(공고종류: 일반/변경/재공고/취소)이 §8 리비전 처리의 입력이다.
"""

SPEC_BID_NOTICE = ServiceSpec(
    service="bid", portal_id="15129394", path="BidPublicInfoService", stage="BID",
    operations={"물품": "getBidPblancListInfoThng", "공사": "getBidPblancListInfoCnstwk",
                "용역": "getBidPblancListInfoServc", "외자": "getBidPblancListInfoFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="EST", official_range="1995-10~ (공식표기)",
    fieldmap={
        "doc_id": ["bidNtceNo"],
        "doc_seq": ["bidNtceOrd", "ntceOrd"],
        "title": ["bidNtceNm", "ntceNm"],
        "agency_cd": ["ntceInsttCd"], "agency_nm": ["ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "pubPrcrmntClsfcNo", "cnstwkKindCd", "indstrytyCd"],
        "category_nm": ["prdctClsfcNoNm", "pubPrcrmntClsfcNoNm", "cnstwkKindNm", "indstrytyNm"],
        "amount": ["presmptPrce", "bdgtAmt", "asignBdgtAmt", "estmtPrce", "baseAmt"],
        "expected_price": ["presmptPrce", "estmtPrce"],
        "method": ["cntrctCnclsMthdNm", "bidMethdNm", "ntceKindNm"],
        "region_limit": ["prtcptPsblRgnNm", "rgnLmtBidLocplcJdgmBssCd"],
        "license_req": ["indstrytyLmtYn", "lcnsLmtNm", "indstrytyNm"],
        "event_time": ["bidNtceDt", "ntceDt", "rgstDt"],
        "source_published_at": ["bidNtceDt", "rgstDt", "ntceDt"],
        "status_raw": ["ntceKindNm", "bidNtceSttusNm", "rbidPermsnYn", "chgNtceRsn"],
        "link_prespec_no": ["bfSpecRgstNo", "refNo"],
        "link_plan_no": ["orderPlanNo", "planNo"],
    },
    notes="ntceKindNm 이 '변경공고/재공고/취소공고' 를 알려준다 → §8 상태변수 + 증분 처리의 입력.")


def collect_bid(start: str, end: str, **kw):
    D, A = collect_service(SPEC_BID_NOTICE, start, end, **kw)
    return (stamp_stage(D, "BID") if len(D) else D), A


# ==========================================================================================
#  collectors/award.py
# ==========================================================================================
"""낙찰정보서비스 (15129397) — 개찰완료·최종낙찰자·개찰순위·예정가격·낙찰률·재입찰·유찰.

공식 정의상 낙찰률은 '예정가격 대비 낙찰금액' 비율이다(§2.D).
공식 메타데이터의 시간범위가 사실상 '실시간'으로만 표기되어 있으므로 실제 historical depth 를
§5 에서 직접 측정한다 — 이 서비스가 이 연구의 가장 큰 데이터 리스크다.
"""

SPEC_AWARD_INFO = ServiceSpec(
    service="award", portal_id="15129397", path="ScsbidInfoService", stage="AWARD",
    operations={"물품": "getScsbidListSttusThng", "공사": "getScsbidListSttusCnstwk",
                "용역": "getScsbidListSttusServc", "외자": "getScsbidListSttusFrgcpt"},
    date_params=("inqryBgnDt", "inqryEndDt"), date_fmt="%Y%m%d%H%M",
    amount_kind="AWARD", official_range="실시간(공식표기) → 실측 필요",
    fieldmap={
        "doc_id": ["bidNtceNo"],
        "doc_seq": ["bidNtceOrd", "ntceOrd", "opengOrd"],
        "title": ["bidNtceNm", "ntceNm"],
        "agency_cd": ["ntceInsttCd"], "agency_nm": ["ntceInsttNm"],
        "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
        "category_cd": ["prdctClsfcNo", "cnstwkKindCd", "indstrytyCd"],
        "category_nm": ["prdctClsfcNoNm", "cnstwkKindNm", "indstrytyNm"],
        "amount": ["sucsfbidAmt", "scsbidAmt", "fnlSucsfbidAmt"],
        "expected_price": ["plnprc", "presmptPrce", "prearngPrce", "estmtPrce"],
        "award_rate": ["sucsfbidRate", "scsbidRate"],
        "award_rank": ["opengRank", "sucsfbidRank", "rank"],
        "bidder_count": ["prtcptCnum", "bidwinnrCnt", "prcbdrCnt", "bidderCnt", "opengCnt"],
        "supplier_bizno": ["bizno", "bidwinnrBizno", "corpBizno", "prcbdrBizno"],
        "supplier_nm": ["bidwinnrNm", "corpNm", "prcbdrNm", "cmpnyNm"],
        "share_ratio": ["jntcontrctRt", "shareRt", "cntrctRt"],
        "consortium_flag": ["jntcontrctYn", "jntCntrctYn"],
        "method": ["cntrctCnclsMthdNm", "bidMethdNm"],
        "event_time": ["opengDt", "rlOpengDt", "scsbidDt"],
        "source_published_at": ["opengDt", "rgstDt", "rlOpengDt"],
        "status_raw": ["progrsSttusNm", "sttusNm", "rbidNo", "fnlSucsfbidYn", "rmrk"],
    },
    notes="복수예비가격/예정가격(plnprc)이 없으면 낙찰률이 죽는다 → §5 에서 보유율을 반드시 측정.")


def collect_award(start: str, end: str, **kw):
    D, A = collect_service(SPEC_AWARD_INFO, start, end, **kw)
    return (stamp_stage(D, "AWARD") if len(D) else D), A


# ==========================================================================================
#  collectors/contract.py
# ==========================================================================================
"""계약정보서비스 (15129427) — 계약상세·변경이력·삭제이력·계약기관·수요기관·계약금액.

낙찰금액보다 최종 계약금액·변경계약이 경제적으로 더 중요한 경우가 있으므로
반드시 낙찰 데이터와 '별도 보관'한다(§2.E). 공식 시간범위 2004-07~.
변경/삭제 오퍼레이션을 함께 받아 §6 CLASS B 리비전 구간을 복원한다.
"""

_FM = {
    "doc_id": ["cntrctNo", "cntrctRefNo", "cntrctInfoNo"],
    "doc_seq": ["cntrctChgOrd", "chgOrd", "cntrctOrd"],
    "title": ["cntrctNm", "prdctNm", "bizNm"],
    "agency_cd": ["cntrctInsttCd", "insttCd"], "agency_nm": ["cntrctInsttNm", "insttNm"],
    "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
    "category_cd": ["prdctClsfcNo", "clsfcNo", "cnstwkKindCd"],
    "category_nm": ["prdctClsfcNoNm", "clsfcNoNm", "cnstwkKindNm"],
    "amount": ["totlCntrctPrce", "cntrctPrce", "thtmCntrctPrce", "cntrctAmt"],
    "supplier_bizno": ["bizno", "corpBizno", "cntrctCorpBizno"],
    "supplier_nm": ["corpNm", "cntrctCorpNm", "cmpnyNm"],
    "share_ratio": ["jntcontrctRt", "shareRt"], "consortium_flag": ["jntcontrctYn"],
    "method": ["cntrctMthNm", "cntrctCnclsMthdNm"],
    "link_bid_no": ["bidNtceNo", "ntceNo"],
    "event_time": ["cntrctCnclsDate", "cntrctDate", "cntrctCnclsDt"],
    "source_published_at": ["rgstDt", "cntrctCnclsDate", "inputDt"],
    "status_raw": ["cntrctSttusNm", "chgRsn", "dltRsn", "sttusNm"],
}

SPEC_CONTRACT = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품": "getCntrctInfoListThng", "공사": "getCntrctInfoListCnstwk",
                "용역": "getCntrctInfoListServc", "외자": "getCntrctInfoListFrgcpt"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", official_range="2004-07~", fieldmap=_FM,
    notes="계약금액은 총계약금액(totlCntrctPrce)과 금차계약금액(thtmCntrctPrce)이 다르다 — 총액 우선.")

# 변경계약 / 삭제계약 — §40 증액·감액·취소·삭제 구분의 원천
SPEC_CHANGE = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품변경": "getCntrctInfoListThngChgCntrct", "공사변경": "getCntrctInfoListCnstwkChgCntrct",
                "용역변경": "getCntrctInfoListServcChgCntrct"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_FM, notes="계약 변경이력(CLASS B).")

SPEC_DELETE = ServiceSpec(
    service="contract", portal_id="15129427", path="CntrctInfoService", stage="CONTRACT",
    operations={"물품삭제": "getCntrctInfoListThngDlt", "공사삭제": "getCntrctInfoListCnstwkDlt",
                "용역삭제": "getCntrctInfoListServcDlt"},
    date_params=("inqryBgnDate", "inqryEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_FM, notes="계약 삭제이력(CLASS B).")


def collect_contract(start: str, end: str, include_changes: bool = True, **kw):
    import pandas as pd
    D, A = collect_service(SPEC_CONTRACT, start, end, **kw)
    Ds = [stamp_stage(D, "CONTRACT")] if len(D) else []
    As = [A]
    if include_changes:
        for sp, tag in ((SPEC_CHANGE, "CHG"), (SPEC_DELETE, "DLT")):
            d, a = collect_service(sp, start, end, **kw)
            if len(d):
                d = stamp_stage(d, "CONTRACT")
                d["status_raw"] = d["status_raw"].fillna("").astype(str) + f"|{tag}"
                Ds.append(d)
            As.append(a)
    out = pd.concat(Ds, ignore_index=True) if Ds else D
    return out, pd.concat(As, ignore_index=True)


# ==========================================================================================
#  collectors/process.py
# ==========================================================================================
"""계약과정통합공개서비스 (15129459) — lifecycle 연결의 '보조원장'.

발주계획 ↕ 사전규격 ↕ 입찰공고 ↕ 낙찰 ↕ 계약 을 잇는 2순위 연결 근거다(§10).
공식 설명에서도 모든 건에 5단계가 다 존재하지는 않는다고 명시하므로
연결 실패를 사건 실패로 간주하지 않는다(§2.F).
"""


_LINK_FM = {
    "doc_id": ["bidNtceNo", "cntrctNo"],
    "doc_seq": ["bidNtceOrd", "cntrctChgOrd"],
    "title": ["bidNtceNm", "cntrctNm"],
    "agency_cd": ["ntceInsttCd", "cntrctInsttCd"], "agency_nm": ["ntceInsttNm", "cntrctInsttNm"],
    "demand_agency_cd": ["dminsttCd"], "demand_agency_nm": ["dminsttNm"],
    "category_cd": ["prdctClsfcNo", "pubPrcrmntClsfcNo"],
    "category_nm": ["prdctClsfcNoNm", "pubPrcrmntClsfcNoNm"],
    "amount": ["sucsfbidAmt", "totlCntrctPrce", "presmptPrce", "asignBdgtAmt"],
    "expected_price": ["plnprc", "presmptPrce"],
    "award_rate": ["sucsfbidRate"],
    "supplier_bizno": ["bidwinnrBizno", "bizno", "corpBizno"],
    "supplier_nm": ["bidwinnrNm", "corpNm"],
    "link_bid_no": ["bidNtceNo"], "link_contract_no": ["cntrctNo"],
    "link_plan_no": ["orderPlanNo"], "link_prespec_no": ["bfSpecRgstNo"],
    "method": ["cntrctCnclsMthdNm", "cntrctMthNm"],
    "event_time": ["bidNtceDate", "bidNtceDt", "opengDate", "cntrctCnclsDate", "rgstDt"],
    "source_published_at": ["rgstDt", "bidNtceDate", "cntrctCnclsDate"],
    "status_raw": ["ntceKindNm", "cntrctSttusNm", "progrsSttusNm"],
}

SPEC_PROC_BID = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="BID",
    operations={"공고표준": "getDataSetOpnStdBidPblancInfo"},
    date_params=("bidNtceBgnDt", "bidNtceEndDt"), date_fmt="%Y%m%d",
    amount_kind="EST", fieldmap=_LINK_FM)

SPEC_PROC_AWARD = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="AWARD",
    operations={"낙찰표준": "getDataSetOpnStdScsbidInfo"},
    date_params=("opengBgnDt", "opengEndDt"), date_fmt="%Y%m%d",
    amount_kind="AWARD", fieldmap=_LINK_FM)

SPEC_PROC_CNTRCT = ServiceSpec(
    service="process", portal_id="15129459", path="ao/PubDataOpnStdService", stage="CONTRACT",
    operations={"계약표준": "getDataSetOpnStdCntrctInfo"},
    date_params=("cntrctCnclsBgnDate", "cntrctCnclsEndDate"), date_fmt="%Y%m%d",
    amount_kind="CONTRACT", fieldmap=_LINK_FM)

ALL_SPECS = (SPEC_PROC_BID, SPEC_PROC_AWARD, SPEC_PROC_CNTRCT)


def collect_process(start: str, end: str, **kw):
    Ds, As = [], []
    for sp in ALL_SPECS:
        d, a = collect_service(sp, start, end, **kw)
        if len(d):
            Ds.append(stamp_stage(d, sp.stage))
        As.append(a)
    out = pd.concat(Ds, ignore_index=True) if Ds else pd.DataFrame()
    return out, (pd.concat(As, ignore_index=True) if As else pd.DataFrame())


# ==========================================================================================
#  collectors/dart.py
# ==========================================================================================
"""OpenDART 수집 — 회사개황(bizr_no ↔ stock_code)과 PIT 재무.

§3.1 회사개황 API 는 corp_code / stock_code / bizr_no / jurir_no / corp_name 을 함께 준다.
     → 사업자등록번호를 이용한 G2B 업체 ↔ DART 법인 연결을 최우선으로 한다(§13).
§58 매출 분모는 반드시 filing_timestamp <= signal_timestamp 인 최신 재무제표만 쓴다.
     DART 의 공개시각은 결산일이 아니라 접수일자(rcept_no 앞 8자리)다.

캐시 우선: 공용 인덱스에 이미 dart_corpcode / dart_fnltt_raw 가 있으면 재수집하지 않는다.
"""



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


# ==========================================================================================
#  collectors/synthetic.py
# ==========================================================================================
"""합성 G2B 세계 — SMOKE 모드 / 리허설 / 누수 카나리아(§93)의 데이터 원천.

목적은 단 하나: **실데이터 없이 계산경로 전체가 옳게 도는지 증명**하는 것이다.
여기서 나온 성과 수치는 연구 결론이 아니다. 모든 산출물에 SYNTHETIC 딱지가 붙는다.

세계의 구성 (실제 조달 구조를 최소한으로 모사)
  · 카테고리별 정부수요가 시간에 따라 이동한다(일부는 붐, 일부는 축소).
  · 각 조달건은 PLAN → PRESPEC → BID → AWARD → CONTRACT 를 '확률적으로' 통과한다.
    (모든 건에 5단계가 다 있지 않다 — §2.F 를 그대로 반영)
  · 변경공고(금액 증감), 취소, 유찰, 재입찰, 공동수급이 실제 비율 수준으로 섞인다.
  · 낙찰자는 그 카테고리에서의 과거 실적(=역량)에 비례해 뽑힌다 → capability 가 지속성을 갖는다.
  · 주가수익률에는 '역량정합 수요증가 × 실제수주전환' 이 약한 진짜 신호로 심겨 있다.
    (강하게 심으면 하네스가 아니라 장난감을 검증하게 된다)

전부 벡터화되어 있다. 12년치 세계를 수 초에 만든다.
"""



N_AGENCY = 45
N_CATEGORY = 70
N_SUPPLIER = 900
N_LISTED = 260


def _rng(seed: int = None) -> np.random.Generator:
    return np.random.default_rng(CFG.SEED if seed is None else seed)


def _unique_ints(rg: np.random.Generator, lo: int, hi: int, n: int) -> np.ndarray:
    """거대한 후보배열을 만들지 않고 유일한 정수 n개를 뽑는다 (np.arange(1e10) 은 67GB다)."""
    out = np.unique(rg.integers(lo, hi, int(n * 1.3)))
    while len(out) < n:
        out = np.unique(np.concatenate([out, rg.integers(lo, hi, n)]))
    rg.shuffle(out)
    return out[:n]


def build_world(start: str = None, end: str = None, seed: int = None,
                opp_per_month: int = 260) -> Dict[str, pd.DataFrame]:
    start = start or CFG.TARGET_START
    end = end or CFG.TARGET_END
    rg = _rng(seed)
    months = month_range(start, end)
    M = len(months)

    # ── 1. 마스터 -----------------------------------------------------------
    agencies = pd.DataFrame({
        "agency_cd": [f"A{i:04d}" for i in range(N_AGENCY)],
        "agency_nm": [f"합성기관{i:03d}" for i in range(N_AGENCY)],
        "agency_type": rg.choice(["중앙", "지자체", "공공기관", "교육"], N_AGENCY,
                                 p=[.25, .35, .3, .1])})
    broad = rg.choice(["건설", "IT서비스", "기계장비", "의료", "방산", "환경", "물류"],
                      N_CATEGORY, p=[.22, .18, .16, .12, .1, .12, .1])
    categories = pd.DataFrame({
        "category_cd": [f"C{i:05d}" for i in range(N_CATEGORY)],
        "category_nm": [f"합성품목{i:03d}" for i in range(N_CATEGORY)],
        "broad_category": broad,
        "proc_type": rg.choice(["물품", "공사", "용역", "외자"], N_CATEGORY, p=[.4, .25, .3, .05])})

    biz = _unique_ints(rg, 1_000_000_000, 9_999_999_999, N_SUPPLIER)
    suppliers = pd.DataFrame({
        "supplier_bizno": [f"{b:010d}" for b in biz],
        "supplier_nm": [f"합성기업{i:04d}" for i in range(N_SUPPLIER)]})
    listed_idx = rg.choice(N_SUPPLIER, N_LISTED, replace=False)
    suppliers["is_listed"] = False
    suppliers.loc[listed_idx, "is_listed"] = True
    suppliers.loc[listed_idx, "stock_code"] = [f"{c:06d}" for c in
                                               _unique_ints(rg, 100, 999_999, N_LISTED)]

    # ── 2. 카테고리 수요 궤적 (외생적 이동) ----------------------------------
    #     일부 카테고리는 특정 시점부터 붐, 일부는 축소. AR(1) + 레짐 점프.
    trend = np.zeros((N_CATEGORY, M))
    shock = rg.normal(0, .12, (N_CATEGORY, M))
    for t in range(1, M):
        trend[:, t] = .93 * trend[:, t - 1] + shock[:, t]
    n_boom = max(4, N_CATEGORY // 8)
    boom_cat = rg.choice(N_CATEGORY, n_boom, replace=False)
    boom_t0 = rg.integers(int(M * .25), int(M * .8), n_boom)
    for k, c in enumerate(boom_cat):
        trend[c, boom_t0[k]:] += np.linspace(0, 1.4, M - boom_t0[k])
    base = rg.uniform(.6, 1.6, N_CATEGORY)[:, None]
    intensity = np.clip(base * np.exp(trend), .05, None)
    intensity = intensity / intensity.sum(axis=0, keepdims=True)      # 월별 점유

    # ── 3. 조달건 생성 -------------------------------------------------------
    n_opp = rg.poisson(opp_per_month, M)
    rows_m = np.repeat(np.arange(M), n_opp)
    N = len(rows_m)
    p = intensity[:, rows_m]                                          # (C, N)
    cum = p.cumsum(axis=0)
    u = rg.random(N) * cum[-1, :]
    cat_i = (u[None, :] > cum).sum(axis=0).clip(0, N_CATEGORY - 1)
    ag_i = rg.integers(0, N_AGENCY, N)
    amount = np.exp(rg.normal(19.0, 1.5, N))                          # 중앙값 ~1.8억
    amount *= np.where(categories["proc_type"].to_numpy()[cat_i] == "공사", 4.0, 1.0)

    opp = pd.DataFrame({
        "opportunity_id": [f"OPP{i:07d}" for i in range(N)],
        "month_i": rows_m, "cat_i": cat_i, "ag_i": ag_i, "amount0": amount})
    opp["base_month"] = months.to_numpy()[opp["month_i"].to_numpy()]
    opp["category_cd"] = categories["category_cd"].to_numpy()[cat_i]
    opp["category_nm"] = categories["category_nm"].to_numpy()[cat_i]
    opp["proc_type"] = categories["proc_type"].to_numpy()[cat_i]
    opp["agency_cd"] = agencies["agency_cd"].to_numpy()[ag_i]
    opp["agency_nm"] = agencies["agency_nm"].to_numpy()[ag_i]

    # 단계 통과 여부 (모든 건에 5단계가 다 있지 않다)
    opp["has_plan"] = rg.random(N) < .62
    opp["has_prespec"] = rg.random(N) < .43
    opp["has_bid"] = rg.random(N) < .97
    opp["failed"] = rg.random(N) < .11                                # 유찰
    opp["cancelled"] = rg.random(N) < .04
    opp["has_award"] = opp["has_bid"] & ~opp["cancelled"] & (rg.random(N) < .88)
    opp["has_contract"] = opp["has_award"] & (rg.random(N) < .93)

    # 단계별 시차(일)
    d_plan = -rg.integers(60, 400, N)
    d_prespec = -rg.integers(20, 90, N)
    d_bid = np.zeros(N, dtype=int)
    d_open = rg.integers(12, 45, N)
    d_cntrct = d_open + rg.integers(5, 60, N)
    bid_dt = pd.to_datetime(opp["base_month"]) - pd.to_timedelta(rg.integers(0, 28, N), unit="D")

    # ── 4. 낙찰자 배정: 카테고리 역량이 지속되도록 ---------------------------
    #     기업별 카테고리 선호(디리클레) → 이 선호가 곧 '과거 실적으로 드러나는 역량'.
    aff = rg.gamma(0.25, 1.0, (N_SUPPLIER, N_CATEGORY))
    aff = aff / aff.sum(axis=0, keepdims=True)
    w = aff[:, cat_i]                                                  # (S, N)
    cw = w.cumsum(axis=0)
    uu = rg.random(N) * cw[-1, :]
    win_i = (uu[None, :] > cw).sum(axis=0).clip(0, N_SUPPLIER - 1)
    opp["winner_i"] = win_i
    opp["supplier_bizno"] = suppliers["supplier_bizno"].to_numpy()[win_i]
    opp["supplier_nm"] = suppliers["supplier_nm"].to_numpy()[win_i]
    opp["consortium"] = rg.random(N) < .09
    opp["share_ratio"] = np.where(opp["consortium"], rg.uniform(.3, .7, N), 1.0)
    # 공동수급 중 절반은 지분 정보가 아예 없다 → UNKNOWN_SHARE_CONSORTIUM (§16)
    opp.loc[opp["consortium"] & (rg.random(N) < .5), "share_ratio"] = np.nan

    exp_price = opp["amount0"].to_numpy() * rg.uniform(.95, 1.05, N)
    award_rate = np.clip(rg.normal(86, 7, N), 60, 100)
    award_amt = exp_price * award_rate / 100.0
    contract_amt = award_amt * np.clip(rg.normal(1.02, .08, N), .6, 1.9)

    # ── 5. 단계 이벤트 테이블로 전개 (벡터화) --------------------------------
    def _ev(mask, stage, ev_dt, amt, kind, **extra) -> pd.DataFrame:
        m = mask.to_numpy() if isinstance(mask, pd.Series) else mask
        if not m.any():
            return pd.DataFrame(columns=CANON_COLS)
        o = opp.loc[m]
        d = pd.DataFrame({
            "stage": stage, "stage_rank": STAGE_RANK[stage], "service": stage.lower(),
            "operation": f"synthetic_{stage}", "proc_type": o["proc_type"].to_numpy(),
            "doc_id": (stage[:2] + o["opportunity_id"].str[3:]).to_numpy(),
            "doc_seq": 0,
            "link_bid_no": ("BD" + o["opportunity_id"].str[3:]).to_numpy(),
            "link_plan_no": np.where(o["has_plan"].to_numpy(),
                                     ("PL" + o["opportunity_id"].str[3:]).to_numpy(), None),
            "link_prespec_no": np.where(o["has_prespec"].to_numpy(),
                                        ("PS" + o["opportunity_id"].str[3:]).to_numpy(), None),
            "link_contract_no": np.where(o["has_contract"].to_numpy(),
                                         ("CT" + o["opportunity_id"].str[3:]).to_numpy(), None),
            "agency_cd": o["agency_cd"].to_numpy(), "agency_nm": o["agency_nm"].to_numpy(),
            "demand_agency_cd": o["agency_cd"].to_numpy(),
            "demand_agency_nm": o["agency_nm"].to_numpy(),
            "category_cd": o["category_cd"].to_numpy(), "category_nm": o["category_nm"].to_numpy(),
            "title": ("합성사업 " + o["opportunity_id"]).to_numpy(),
            "amount": amt[m], "amount_kind": kind,
            "event_time": ev_dt[m], "source_published_at": ev_dt[m],
            "raw_uid": "SYNTHETIC"})
        for k, v in extra.items():
            d[k] = v[m] if isinstance(v, np.ndarray) else v
        for c in CANON_COLS:
            if c not in d.columns:
                d[c] = np.nan
        return d[CANON_COLS]

    plan_dt = bid_dt + pd.to_timedelta(d_plan, unit="D")
    ps_dt = bid_dt + pd.to_timedelta(d_prespec, unit="D")
    open_dt = bid_dt + pd.to_timedelta(d_open, unit="D")
    ct_dt = bid_dt + pd.to_timedelta(d_cntrct, unit="D")
    plan_amt = opp["amount0"].to_numpy() * rg.uniform(.85, 1.2, N)
    ps_amt = opp["amount0"].to_numpy() * rg.uniform(.92, 1.1, N)

    status_bid = np.where(opp["cancelled"].to_numpy(), "취소공고",
                          np.where(opp["failed"].to_numpy(), "유찰", "일반공고"))
    parts = [
        _ev(opp["has_plan"], "PLAN", plan_dt, plan_amt, "BUDGET"),
        _ev(opp["has_prespec"], "PRESPEC", ps_dt, ps_amt, "BUDGET"),
        _ev(opp["has_bid"], "BID", bid_dt, opp["amount0"].to_numpy(), "EST",
            expected_price=exp_price, status_raw=status_bid,
            license_req=categories["broad_category"].to_numpy()[cat_i],
            region_limit=np.where(rg.random(N) < .25, "지역제한", "전국")),
        _ev(opp["has_award"], "AWARD", open_dt, award_amt, "AWARD",
            expected_price=exp_price, award_rate=award_rate,
            bidder_count=rg.integers(1, 22, N).astype(float),
            award_rank=np.ones(N),
            supplier_bizno=opp["supplier_bizno"].to_numpy(),
            supplier_nm=opp["supplier_nm"].to_numpy(),
            share_ratio=opp["share_ratio"].to_numpy(),
            consortium_flag=np.where(opp["consortium"].to_numpy(), "Y", "N")),
        _ev(opp["has_contract"], "CONTRACT", ct_dt, contract_amt, "CONTRACT",
            supplier_bizno=opp["supplier_bizno"].to_numpy(),
            supplier_nm=opp["supplier_nm"].to_numpy(),
            share_ratio=opp["share_ratio"].to_numpy(),
            consortium_flag=np.where(opp["consortium"].to_numpy(), "Y", "N")),
    ]
    E = pd.concat([p for p in parts if len(p)], ignore_index=True)

    # ── 6. 변경공고 / 변경계약 (§8 이 실제로 작동하는지 보려면 반드시 있어야 함) ──
    for st, frac, amt_mult in (("BID", .18, (0.9, 1.35)), ("CONTRACT", .14, (0.85, 1.4))):
        src = E[E["stage"] == st]
        if not len(src):
            continue
        k = int(len(src) * frac)
        if k <= 0:
            continue
        pick = src.sample(n=k, random_state=int(CFG.SEED) % (2**31))
        chg = pick.copy()
        chg["doc_seq"] = 1
        chg["amount"] = chg["amount"].to_numpy() * rg.uniform(*amt_mult, k)
        chg["event_time"] = chg["event_time"] + pd.to_timedelta(rg.integers(3, 70, k), unit="D")
        chg["source_published_at"] = chg["event_time"]
        chg["status_raw"] = "변경공고" if st == "BID" else "변경계약"
        E = pd.concat([E, chg], ignore_index=True)
    # 순수 재공고(금액 동일) — 100억→100억 이 200억이 되지 않는지 검증하는 표본
    src = E[(E["stage"] == "BID") & (E["doc_seq"] == 0)]
    k = int(len(src) * .07)
    if k > 0:
        rep = src.sample(n=k, random_state=(int(CFG.SEED) + 7) % (2**31)).copy()
        rep["doc_seq"] = 2
        rep["event_time"] = rep["event_time"] + pd.to_timedelta(rg.integers(5, 40, k), unit="D")
        rep["source_published_at"] = rep["event_time"]
        rep["status_raw"] = "재공고"
        E = pd.concat([E, rep], ignore_index=True)

    E = E[E["event_time"].notna()].reset_index(drop=True)
    out = []
    for st, g in E.groupby("stage", sort=False):
        out.append(stamp(g, "event_time", "source_published_at", stage=st))
    E = pd.concat(out, ignore_index=True)
    E["synthetic"] = True

    LOG.ok(f"합성 G2B 세계: 조달건 {N:,} · 이벤트 {len(E):,} · 기간 {months[0]:%Y-%m}~{months[-1]:%Y-%m} "
           f"· 상장 공급자 {N_LISTED}/{N_SUPPLIER}")
    return {"events": E, "opportunities": opp, "agencies": agencies, "categories": categories,
            "suppliers": suppliers, "months": pd.Series(months), "affinity": pd.DataFrame(aff)}


def build_market(world: Dict[str, pd.DataFrame], seed: int = None,
                 alpha_strength: float = 0.0,
                 signal: "Optional[pd.DataFrame]" = None) -> Dict[str, pd.DataFrame]:
    """합성 주식시장 — PIT 유니버스 · 월수익률 · 시총 · 섹터 · 상장폐지.

    alpha_strength = 0 (기본)  : **알파가 전혀 없는 null 세계**.
        하네스가 여기서 유의한 알파를 만들어내면 그것은 하네스의 버그다.
    alpha_strength > 0         : signal(stock_code, month, value)을 다음달 수익률에 심는다.
        하네스가 '있는 알파를 실제로 찾아내는지' 반대편에서 검증한다.

    두 방향을 모두 통과해야 백테스트 결과를 믿을 수 있다.
    (합성이므로 어느 쪽 성과도 연구 결론이 아니다)
    """
    rg = _rng((CFG.SEED + 991) if seed is None else seed)
    sup = world["suppliers"]
    months = pd.DatetimeIndex(world["months"])
    L = sup[sup["is_listed"]].reset_index(drop=True)
    n, M = len(L), len(months)

    listing_i = rg.integers(0, max(1, int(M * .35)), n)                # 상장시점 분산
    alive = np.arange(M)[None, :] >= listing_i[:, None]
    delist_i = np.where(rg.random(n) < .16, rg.integers(int(M * .4), M + 12, n), 10**6)
    alive &= np.arange(M)[None, :] < delist_i[:, None]

    mcap0 = np.exp(rg.normal(25.6, 1.25, n))                          # 중앙값 ~1300억
    mkt = rg.normal(.006, .052, M)
    beta = rg.uniform(.5, 1.5, n)[:, None]
    idio = rg.normal(0, .105, (n, M))
    ret = beta * mkt[None, :] + idio

    G = pd.DataFrame({
        "stock_code": np.repeat(L["stock_code"].to_numpy(), M),
        "month": np.tile(months.to_numpy(), n),
        "ret": ret.ravel(), "alive": alive.ravel(),
        "sector": np.repeat(rg.choice(["건설", "IT", "기계", "헬스케어", "방산", "소재", "운송"],
                                      n, p=[.2, .2, .18, .12, .1, .1, .1]), M),
        "market": np.repeat(rg.choice(["KOSPI", "KOSDAQ"], n, p=[.42, .58]), M)})
    G["mcap"] = np.repeat(mcap0, M) * np.exp(
        pd.Series(ret.ravel()).groupby(G["stock_code"]).cumsum().to_numpy())
    G["turnover_value"] = G["mcap"] * np.exp(rg.normal(-4.2, 1.0, len(G)))
    G = G[G["alive"]].drop(columns=["alive"]).reset_index(drop=True)
    if alpha_strength and signal is not None and len(signal):
        # 신호(t)를 수익률(t+1)에 심는다 — 하네스의 T+1 정렬과 같은 규약을 쓴다
        sg = signal.rename(columns={signal.columns[-1]: "_sig"}).copy()
        sg["month"] = pd.to_datetime(sg["month"]) + pd.offsets.MonthEnd(1)
        G = G.merge(sg[["stock_code", "month", "_sig"]], on=["stock_code", "month"], how="left")
        z = G.groupby("month", observed=True)["_sig"].transform(
            lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-12))
        G["ret"] = G["ret"] + alpha_strength * z.fillna(0.0)
        G = G.drop(columns=["_sig"])
        LOG.info(f"합성 시장에 알파를 심었습니다 (strength={alpha_strength:.3f}) — "
                 f"하네스 탐지력 검증용")
    # 상장폐지월 수익률 -100% (누락 처리 금지)
    last = G.groupby("stock_code")["month"].transform("max")
    dl = (last < months[-1]) & (G["month"] == last)
    G.loc[dl, "ret"] = -1.0
    G["delisted"] = dl
    LOG.ok(f"합성 시장: 종목 {n:,} · 월관측 {len(G):,} · 상장폐지 {int(dl.sum()):,}종목(수익률 -100% 반영)")
    return {"panel": G, "listed": L}


def crosswalk_from_world(world: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """합성 crosswalk — 실제 파이프라인과 같은 스키마(§14)."""
    s = world["suppliers"]
    L = s[s["is_listed"]].copy()
    return pd.DataFrame({
        "bizr_no": L["supplier_bizno"].to_numpy(),
        "corp_code": ["S" + str(i).zfill(7) for i in range(len(L))],
        "stock_code": L["stock_code"].to_numpy(),
        "corp_name": L["supplier_nm"].to_numpy(),
        "valid_from": pd.Timestamp("2000-01-01"), "valid_to": pd.NaT,
        "mapping_type": "EXACT_ID", "confidence": 1.0})


# ==========================================================================================
#  entity/dart_crosswalk.py
# ==========================================================================================
"""G2B 업체 ↔ DART 법인 ↔ 상장종목 crosswalk.

§13 PRIMARY  : 사업자등록번호 exact match  (G2B supplier_bizno == DART bizr_no)
§13 금지     : 기업명 fuzzy matching 만으로 자동 확정하지 않는다.
               fuzzy name 은 candidate generation 용도로만 쓴다.
§14          : bizr_no / corp_code / stock_code / valid_from / valid_to /
               mapping_type / confidence 구조. 현재 stock_code 를 과거 전체에 소급하지 않는다.
§52          : 매칭 품질 게이트 — exact / verified / ambiguous / unmatched 비중을 금액기준으로 보고.
"""



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


# ==========================================================================================
#  entity/company_history.py
# ==========================================================================================
"""법인 이력 — 상호변경·합병·분할을 PIT 로 다룬다 (§14, §98).

핵심 금지사항:
  · 현재 기업명을 과거에 소급하지 않는다.
  · 현재 stock_code 를 과거 전체에 소급하지 않는다.
따라서 이 모듈은 '언제부터 언제까지 그 이름/코드가 유효했는가' 만 다룬다.
복원 불가능하면 복원 불가능하다고 표시한다 — 추정으로 메우지 않는다.
"""




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


# ==========================================================================================
#  entity/consortium.py
# ==========================================================================================
"""공동수급·컨소시엄 금액 배분 (§16).

같은 100억 계약을 참여기업 3곳에 각각 100억씩 할당하지 않는다.
  · 지분/계약분담액이 있으면 실제 비율 사용.
  · 없으면 PRIMARY 에서는 UNKNOWN_SHARE_CONSORTIUM 으로 표시하고 금액 팩터에서 제외한다.
  · equal split / winner-only / full allocation 비교는 Secondary sensitivity 에서만.
"""



ALLOC_MODES = ("primary", "equal_split", "winner_only", "full_allocation")


def allocate(events: pd.DataFrame, mode: str = "primary",
             amount_col: str = "amount", out_col: str = "attributed_amount") -> pd.DataFrame:
    """참여기업별 귀속금액을 만든다. PRIMARY 는 지분 불명 컨소시엄을 NaN 으로 둔다."""
    if mode not in ALLOC_MODES:
        raise ValueError(f"알 수 없는 배분모드: {mode} (가능: {ALLOC_MODES})")
    e = events.copy()
    amt = pd.to_numeric(e[amount_col], errors="coerce")
    flag = e.get("consortium_flag")
    is_cons = (flag.astype(str).str.upper().isin(["Y", "TRUE", "1", "공동수급"])
               if flag is not None else pd.Series(False, index=e.index))
    share = pd.to_numeric(e.get("share_ratio"), errors="coerce")
    share = share.where(share.between(0, 1), share / 100.0)          # 30 → 0.30 허용
    share = share.where(share.between(0, 1))
    known = share.notna()

    if mode == "primary":
        # 단독계약: 전액. 컨소시엄+지분있음: 지분비율. 컨소시엄+지분없음: 제외(NaN).
        e[out_col] = np.where(~is_cons, amt, np.where(known, amt * share, np.nan))
    elif mode == "equal_split":
        n = pd.to_numeric(e.get("consortium_n"), errors="coerce").fillna(2.0)
        e[out_col] = np.where(~is_cons, amt, amt / n.clip(lower=1))
    elif mode == "winner_only":
        e[out_col] = np.where(~is_cons, amt, np.where(e.get("award_rank", 1) == 1, amt, 0.0))
    else:                                                             # full_allocation
        e[out_col] = amt
    e["consortium_unknown_share"] = (is_cons & ~known).to_numpy()
    e["alloc_mode"] = mode
    return e


def consortium_audit(events: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """지분 불명 컨소시엄이 금액에서 얼마나 빠지는지 — 이 숫자를 숨기면 §16 이 무의미해진다."""
    e = allocate(events, "primary", amount_col)
    tot = float(pd.to_numeric(e[amount_col], errors="coerce").sum())
    excl = float(pd.to_numeric(e.loc[e["consortium_unknown_share"], amount_col],
                               errors="coerce").sum())
    n_c = int(e["consortium_unknown_share"].sum())
    return pd.DataFrame([{"전체건수": len(e), "지분불명_컨소시엄_건수": n_c,
                          "전체금액": tot, "제외금액": excl,
                          "제외비중": (excl / tot) if tot else np.nan,
                          "PRIMARY귀속금액": float(pd.to_numeric(e["attributed_amount"],
                                                              errors="coerce").sum())}])


# ==========================================================================================
#  graph/linker.py
# ==========================================================================================
"""Lifecycle 연결 — §10 연결 우선순위와 link_method / link_score / link_known_at.

우선순위
  1순위  공식 식별번호                (link_score 1.00)
  2순위  계약과정통합공개서비스 관계    (0.90)
  3순위  발주기관+사업명+품목+금액+날짜 결정적 결합 (0.70)
  4순위  텍스트 유사도                 (0.40, 후보일 뿐 확정 아님)

원칙: **애매한 연결을 억지로 확정하지 않는다.** 3·4순위는 기본적으로 PRIMARY 에서 꺼져 있고,
      켜더라도 link_score 가 남아 민감도 분석이 가능하다.
      link_known_at = 그 연결을 '언제부터 알 수 있었는가' (두 문서의 available_at 중 늦은 쪽).
"""



LINK_KEY_COLS = ("link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no")

LINK_METHOD_SCORE = {"OFFICIAL_ID": 1.00, "PROCESS_LEDGER": 0.90,
                     "DETERMINISTIC_ATTR": 0.70, "TEXT_SIMILARITY": 0.40}


def doc_key(E: pd.DataFrame) -> pd.Series:
    """문서 노드 식별자 — (service, doc_id). doc_id 가 없으면 행 자체를 고립 문서로 둔다."""
    svc = E["service"].astype("string").fillna("na")
    did = E["doc_id"].astype("string")
    fallback = pd.Series("row#" + E.index.astype(str), index=E.index, dtype="string")
    return svc + "␟" + did.where(did.notna() & (did.str.len() > 0), fallback)


def official_id_edges(E: pd.DataFrame) -> pd.DataFrame:
    """1순위 — 공식 식별번호로 문서와 키를 잇는 이분 간선."""
    dk = doc_key(E)
    parts = []
    for c in LINK_KEY_COLS:
        if c not in E.columns:
            continue
        v = E[c].astype("string")
        m = v.notna() & (v.str.len() > 0)
        if not bool(m.any()):
            continue
        parts.append(pd.DataFrame({
            "doc": dk[m].to_numpy(),
            "key": (c.replace("link_", "") + "␟" + v[m]).to_numpy(),
            "method": "OFFICIAL_ID",
            "known_at": E.loc[m, "available_at"].to_numpy()}))
    # 자기 자신의 doc_id 도 키로 등록 — 같은 문서의 리비전들이 뭉치도록
    parts.append(pd.DataFrame({"doc": dk.to_numpy(),
                               "key": ("self␟" + dk).to_numpy(),
                               "method": "OFFICIAL_ID",
                               "known_at": E["available_at"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])


def process_ledger_edges(E: pd.DataFrame) -> pd.DataFrame:
    """2순위 — 계약과정통합공개(service=='process') 행은 여러 단계 번호를 한 행에 갖는다.
    그 행을 매개로 서로 다른 단계의 문서가 이어진다."""
    P = E[E["service"].astype(str) == "process"]
    if not len(P):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    dk = doc_key(P)
    parts = []
    for c in LINK_KEY_COLS:
        if c not in P.columns:
            continue
        v = P[c].astype("string")
        m = v.notna() & (v.str.len() > 0)
        if bool(m.any()):
            parts.append(pd.DataFrame({"doc": dk[m].to_numpy(),
                                       "key": (c.replace("link_", "") + "␟" + v[m]).to_numpy(),
                                       "method": "PROCESS_LEDGER",
                                       "known_at": P.loc[m, "available_at"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])


def deterministic_attr_edges(E: pd.DataFrame, amount_tol: float = 0.05,
                             day_window: int = 400) -> pd.DataFrame:
    """3순위 — (발주기관 × 품목 × 정규화사업명) 이 같고 금액이 근접하며 시점이 가까운 문서 결합.

    PRIMARY 에서는 기본 OFF. 켜면 link_score 0.70 으로 기록되어 민감도 분석이 가능하다.
    금액 버킷을 쓰므로 O(N) 이다 — 전수 페어 비교를 하지 않는다.
    """
    need = ["agency_cd", "category_cd", "title", "amount", "available_at"]
    if any(c not in E.columns for c in need):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    d = E.dropna(subset=["amount"]).copy()
    if not len(d):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    d["_nm"] = d["title"].map(norm_name)
    d = d[d["_nm"].str.len() >= 4]
    if not len(d):
        return pd.DataFrame(columns=["doc", "key", "method", "known_at"])
    # 금액을 로그 버킷으로 이산화 → 같은 버킷만 후보
    lg = np.log1p(pd.to_numeric(d["amount"], errors="coerce").clip(lower=0))
    bucket = np.floor(lg / max(amount_tol, 1e-6)).astype("Int64")
    per = (pd.to_datetime(d["available_at"]).view("int64") // (86400 * 10**9) // max(day_window, 1))
    key = (d["agency_cd"].astype("string").fillna("") + "␟" +
           d["category_cd"].astype("string").fillna("") + "␟" + d["_nm"] + "␟" +
           bucket.astype("string") + "␟" + per.astype("string"))
    return pd.DataFrame({"doc": doc_key(d).to_numpy(), "key": ("attr␟" + key).to_numpy(),
                         "method": "DETERMINISTIC_ATTR",
                         "known_at": d["available_at"].to_numpy()})


def build_edges(E: pd.DataFrame, use_official: bool = True, use_process: bool = True,
                use_attr: bool = False, use_text: bool = False) -> pd.DataFrame:
    parts = []
    if use_official:
        parts.append(official_id_edges(E))
    if use_process:
        parts.append(process_ledger_edges(E))
    if use_attr:
        parts.append(deterministic_attr_edges(E))
    if use_text:
        LOG.warn("텍스트 유사도 연결(4순위)은 확정 연결로 쓰지 않습니다 — 후보 생성만 지원합니다(§10).")
    ed = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame(
        columns=["doc", "key", "method", "known_at"])
    if len(ed):
        ed["link_score"] = ed["method"].map(LINK_METHOD_SCORE).astype(float)
    return ed


# ==========================================================================================
#  graph/lifecycle.py
# ==========================================================================================
"""G2B Opportunity Lifecycle — §9 통합, §11 이중계산 방지의 구현체.

핵심 산식 (이 파일의 존재 이유)
─────────────────────────────────────────────────────────────────────────────
  시점 t 에서 한 조달건 o 의 정부수요는
      best_known_amount(o, t) = '그때까지 알려진 가장 진척된 단계'의 금액
  이고, 신규 정부수요 flow 는 그 계단함수의 **증분**이다.

      demand_flow(o, t) = Δ_t best_known_amount(o, t)

  이 한 줄이 §8(수정공고 중복금지)과 §11(plan+bid+award+contract 4중계상 금지)을
  동시에 해결한다. 증분의 총합은 항상 마지막으로 알려진 금액과 정확히 같으므로
  어떤 순서로 집계해도 이중계산이 원천적으로 불가능하다.

  1 plan → N bids, N plans → 1 bid, 1 bid → 재입찰 N회, 1 award → 복수 계약
  모두 허용된다 — 강제 1:1 매칭을 하지 않는다(§9).
"""



STAGE_ORDER = ["PLAN", "PRESPEC", "BID", "AWARD", "CONTRACT"]   # STAGE_RANK 는 collectors.base 가 원천

GIANT_COMPONENT_DOCS = 200          # 이보다 큰 덩어리는 '과잉병합'으로 표시한다


def _connected_components(edges: pd.DataFrame) -> pd.DataFrame:
    """이분 간선(doc↔key) → 연결요소. scipy 로 완전 벡터화 (문서 수백만 건도 수 초)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    docs = pd.Index(pd.unique(edges["doc"]))
    keys = pd.Index(pd.unique(edges["key"]))
    di = docs.get_indexer(edges["doc"])
    ki = keys.get_indexer(edges["key"]) + len(docs)
    n = len(docs) + len(keys)
    A = coo_matrix((np.ones(len(edges), dtype=np.int8), (di, ki)), shape=(n, n))
    ncomp, lab = connected_components(A, directed=False)
    return pd.DataFrame({"doc": docs, "comp": lab[:len(docs)]})


def resolve_opportunities(E: pd.DataFrame, use_attr: bool = False,
                          use_process: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """이벤트에 opportunity_id 를 부여한다. 반환 (이벤트+opportunity_id, 연결 진단표)."""
    if E is None or not len(E):
        return E, pd.DataFrame()
    ed = build_edges(E, use_official=True, use_process=use_process, use_attr=use_attr)
    if not len(ed):
        out = E.copy()
        out["opportunity_id"] = "OPP_" + doc_key(out)
        out["link_method"] = "ISOLATED"
        out["link_score"] = 0.0
        out["link_known_at"] = out["available_at"]
        return out, pd.DataFrame()
    comp = _connected_components(ed)
    dk = doc_key(E)
    out = E.copy()
    out["_doc"] = dk.to_numpy()
    out = out.merge(comp, left_on="_doc", right_on="doc", how="left").drop(columns=["doc"])
    out["comp"] = out["comp"].fillna(-1).astype("int64")
    # 안정적 opportunity_id: 연결요소의 가장 이른 available_at + 최소 doc key 로 결정 (§88 재현성)
    anchor = (out.sort_values(["comp", "available_at", "_doc"], kind="stable")
              .groupby("comp", as_index=False).first()[["comp", "_doc"]]
              .rename(columns={"_doc": "_anchor"}))
    out = out.merge(anchor, on="comp", how="left")
    out["opportunity_id"] = "OPP_" + pd.util.hash_pandas_object(
        out["_anchor"].astype(str), index=False).astype("uint64").astype(str).str.slice(0, 15)

    # 각 문서에 붙은 연결근거 중 가장 강한 것
    best = (ed.sort_values("link_score", ascending=False, kind="stable")
            .drop_duplicates(subset=["doc"], keep="first")[["doc", "method", "link_score"]])
    out = out.merge(best.rename(columns={"doc": "_doc", "method": "link_method"}),
                    on="_doc", how="left")
    out["link_method"] = out["link_method"].fillna("ISOLATED")
    out["link_score"] = out["link_score"].fillna(0.0)
    # link_known_at: 그 연결을 알 수 있었던 시각 = 같은 opportunity 내 문서들의 available_at 누적 최대
    out = out.sort_values(["opportunity_id", "available_at"], kind="stable")
    out["link_known_at"] = out.groupby("opportunity_id")["available_at"].cummax()

    sizes = out.groupby("opportunity_id")["_doc"].nunique()
    giant = sizes[sizes > GIANT_COMPONENT_DOCS]
    if len(giant):
        LOG.warn(f"과잉병합 의심 opportunity {len(giant):,}개 (문서 {GIANT_COMPONENT_DOCS}개 초과, "
                 f"최대 {int(sizes.max()):,}). 연결근거를 재검토해야 합니다 — "
                 f"억지 확정 대신 진단표에 남깁니다(§10).")
        out["giant_component"] = out["opportunity_id"].isin(giant.index)
    else:
        out["giant_component"] = False

    diag = pd.DataFrame([{
        "이벤트": len(out), "문서": int(out["_doc"].nunique()),
        "opportunity": int(out["opportunity_id"].nunique()),
        "문서/opportunity_평균": float(sizes.mean()), "최대": int(sizes.max()),
        "과잉병합_opportunity": int(len(giant)),
        "단계2개이상_보유": int((out.groupby("opportunity_id")["stage"].nunique() > 1).sum()),
    }])
    LOG.ok(f"lifecycle 해석: 이벤트 {len(out):,} → opportunity {out['opportunity_id'].nunique():,} "
           f"(문서/건 평균 {sizes.mean():.2f})")
    return out.drop(columns=["_doc", "_anchor", "comp"]), diag


def stage_ladder(E: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """§11 핵심. opportunity 별 '가장 진척된 단계' 계단함수와 그 증분(신규 정부수요)을 만든다.

    반환 컬럼
      opportunity_id, available_at, stage, stage_rank, best_amount, demand_flow,
      is_advance(단계 전진), is_revision(같은 단계 내 금액변경)
    전부 groupby+cummax+diff 로 벡터화. opportunity 루프 없음.
    """
    need = ["opportunity_id", "available_at", "stage", amount_col]
    miss = [c for c in need if c not in E.columns]
    if miss:
        raise KeyError(f"stage_ladder 입력 컬럼 누락: {miss}")
    d = E[E[amount_col].notna()].copy()
    if not len(d):
        return pd.DataFrame(columns=["opportunity_id", "available_at", "stage", "stage_rank",
                                     "best_amount", "demand_flow", "is_advance", "is_revision"])
    d["stage_rank"] = d["stage"].map(STAGE_RANK).astype("float64")
    d = d.dropna(subset=["stage_rank"])
    # 같은 시각·같은 단계에 여러 문서가 있으면 금액을 합산해 한 관측으로 만든다
    d = (d.groupby(["opportunity_id", "available_at", "stage", "stage_rank"], as_index=False,
                   observed=True)[amount_col].sum())
    d = d.sort_values(["opportunity_id", "available_at", "stage_rank"], kind="stable")
    g = d.groupby("opportunity_id", sort=False)
    run_max = g["stage_rank"].cummax()
    # '현재 최고 단계 이상'인 관측만 상태를 바꾼다. 뒤늦게 도착한 하위단계 문서는 상태를 되돌리지 않는다.
    d["is_state_change"] = d["stage_rank"].to_numpy() >= run_max.to_numpy()
    s = d[d["is_state_change"]].copy()
    s["best_amount"] = s[amount_col]
    gs = s.groupby("opportunity_id", sort=False)
    prev_amt = gs["best_amount"].shift(1)
    prev_rank = gs["stage_rank"].shift(1)
    s["demand_flow"] = s["best_amount"] - prev_amt.fillna(0.0)
    s["is_advance"] = (prev_rank.isna()) | (s["stage_rank"] > prev_rank)
    s["is_revision"] = (~s["is_advance"])
    return s[["opportunity_id", "available_at", "stage", "stage_rank", "best_amount",
              "demand_flow", "is_advance", "is_revision"]].reset_index(drop=True)


def opportunity_lifecycle(E: pd.DataFrame) -> pd.DataFrame:
    """gold/g2b_opportunity_lifecycle.parquet (§89) — opportunity 1행 요약.

    ⚠ 여기 담기는 '최종' 컬럼은 사후 요약이며 CLASS C 다. 팩터에 쓰면 assert_pit_safe 가 막는다.
    """
    if E is None or not len(E):
        return pd.DataFrame()
    d = E.copy()
    d["stage_rank"] = d["stage"].map(STAGE_RANK)
    first_by_stage = (d.sort_values("available_at", kind="stable")
                      .groupby(["opportunity_id", "stage"], as_index=False)
                      .agg(first_available=("available_at", "first"),
                           first_event=("event_time", "first"), amt=("amount", "first")))
    piv = first_by_stage.pivot_table(index="opportunity_id", columns="stage",
                                     values="first_available", aggfunc="min")
    piv.columns = [f"t_{c}" for c in piv.columns]
    amt = first_by_stage.pivot_table(index="opportunity_id", columns="stage",
                                     values="amt", aggfunc="sum")
    amt.columns = [f"amt_{c}" for c in amt.columns]
    base = (d.sort_values("available_at", kind="stable").groupby("opportunity_id", as_index=False)
            .agg(agency_cd=("agency_cd", "first"), agency_nm=("agency_nm", "first"),
                 category_cd=("category_cd", "first"), category_nm=("category_nm", "first"),
                 proc_type=("proc_type", "first"), title=("title", "first"),
                 first_seen=("available_at", "min"), last_seen=("available_at", "max"),
                 max_stage_rank=("stage_rank", "max"), n_events=("stage", "size"),
                 n_stages=("stage", "nunique")))
    out = base.merge(piv.reset_index(), on="opportunity_id", how="left") \
              .merge(amt.reset_index(), on="opportunity_id", how="left")
    win = (d[d["supplier_bizno"].notna()].sort_values("available_at", kind="stable")
           .groupby("opportunity_id", as_index=False)
           .agg(winner_bizno=("supplier_bizno", "last"), winner_nm=("supplier_nm", "last"),
                winner_known_at=("available_at", "min")))
    out = out.merge(win, on="opportunity_id", how="left")
    out["reached_stage"] = out["max_stage_rank"].map({v: k for k, v in STAGE_RANK.items()})
    return out


def double_count_audit(E: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """§11 이 실제로 작동했는지 수치로 증명한다. 회귀 테스트가 이 표를 본다."""
    lad = stage_ladder(E, amount_col)
    naive_all = float(pd.to_numeric(E[amount_col], errors="coerce").sum())
    by_stage = E.groupby("stage")[amount_col].sum()
    correct = float(lad["demand_flow"].sum())
    last_known = float(lad.sort_values(["opportunity_id", "available_at"])
                       .groupby("opportunity_id")["best_amount"].last().sum())
    rows = [{"측정": "전 단계 단순합산(금지된 계산)", "금액": naive_all},
            *[{"측정": f"  └ {s} 단계 합", "금액": float(v)} for s, v in by_stage.items()],
            {"측정": "lifecycle 증분합(정답)", "금액": correct},
            {"측정": "opportunity 최종 알려진 금액 합", "금액": last_known},
            {"측정": "제거된 이중계상액", "금액": naive_all - correct},
            {"측정": "이중계상 배수", "금액": (naive_all / correct) if correct else np.nan}]
    return pd.DataFrame(rows)


# ==========================================================================================
#  graph/demand_graph.py
# ==========================================================================================
"""G2B Demand Graph — §12 노드/엣지 구조와 §7 graph.asof(t).

Node:  AGENCY · CATEGORY · PLAN · PRESPEC · BID · AWARD · CONTRACT · SUPPLIER · LISTED_COMPANY
Edge:  AGENCY -ISSUES-> PLAN            PLAN -PRECEDES-> PRESPEC
       PRESPEC -PRECEDES-> BID          BID -IN_CATEGORY-> CATEGORY
       BID -REQUIRES_LICENSE-> LICENSE  BID -IN_REGION-> REGION
       BID -AWARDED_TO-> SUPPLIER       SUPPLIER -MAPS_TO-> LISTED_COMPANY
       AWARD -BECOMES-> CONTRACT

★ graph.asof(t) 가 돌려주는 노드·속성·엣지는 t 시점까지 알려진 것만 포함한다.
  그래프 자체는 사후에 연결해도 되지만 조회는 반드시 시점을 통과해야 한다(§7).
  그래서 모든 노드·엣지에 known_at 이 붙어 있고, asof 는 known_at <= t 로 자른다.
"""



NODE_TYPES = ("AGENCY", "CATEGORY", "LICENSE", "REGION", "PLAN", "PRESPEC", "BID",
              "AWARD", "CONTRACT", "SUPPLIER", "LISTED_COMPANY", "OPPORTUNITY")
EDGE_TYPES = ("ISSUES", "PRECEDES", "IN_CATEGORY", "REQUIRES_LICENSE", "IN_REGION",
              "AWARDED_TO", "MAPS_TO", "BECOMES", "BELONGS_TO")


def _nodes_from(df: pd.DataFrame, ntype: str, id_col: str, known_col: str,
                attrs: Sequence[str] = ()) -> pd.DataFrame:
    v = df[id_col].astype("string")
    m = v.notna() & (v.str.len() > 0)
    if not bool(m.any()):
        return pd.DataFrame(columns=["node_id", "node_type", "known_at"] + list(attrs))
    out = pd.DataFrame({"node_id": ntype + "␟" + v[m], "node_type": ntype,
                        "known_at": df.loc[m, known_col].to_numpy()})
    for a in attrs:
        out[a] = df.loc[m, a].to_numpy() if a in df.columns else np.nan
    return (out.sort_values("known_at", kind="stable")
            .drop_duplicates(subset=["node_id"], keep="first"))


def build_graph_nodes(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """노드 테이블. known_at = 그 노드가 처음 관측된 available_at."""
    parts = [
        _nodes_from(E, "AGENCY", "agency_cd", "available_at", ["agency_nm"]),
        _nodes_from(E, "CATEGORY", "category_cd", "available_at", ["category_nm", "proc_type"]),
        _nodes_from(E, "LICENSE", "license_req", "available_at"),
        _nodes_from(E, "REGION", "region_limit", "available_at"),
        _nodes_from(E, "SUPPLIER", "supplier_bizno", "available_at", ["supplier_nm"]),
        _nodes_from(E, "OPPORTUNITY", "opportunity_id", "available_at",
                    ["agency_cd", "category_cd", "proc_type"]),
    ]
    for st in ("PLAN", "PRESPEC", "BID", "AWARD", "CONTRACT"):
        sub = E[E["stage"] == st]
        if len(sub):
            parts.append(_nodes_from(sub, st, "doc_id", "available_at",
                                     ["amount", "agency_cd", "category_cd"]))
    if crosswalk is not None and len(crosswalk):
        cw = crosswalk.dropna(subset=["stock_code"]).copy()
        cw["known_at"] = pd.to_datetime(cw.get("valid_from")).fillna(pd.Timestamp("1990-01-01"))
        parts.append(_nodes_from(cw, "LISTED_COMPANY", "stock_code", "known_at", ["corp_name"]))
    N = pd.concat([p for p in parts if len(p)], ignore_index=True)
    return N.sort_values(["node_type", "known_at"], kind="stable").reset_index(drop=True)


def _edges(src: pd.Series, dst: pd.Series, etype: str, known: pd.Series,
           weight: Optional[pd.Series] = None) -> pd.DataFrame:
    m = src.notna() & dst.notna()
    if not bool(m.any()):
        return pd.DataFrame(columns=["src", "dst", "edge_type", "known_at", "weight"])
    return pd.DataFrame({"src": src[m].to_numpy(), "dst": dst[m].to_numpy(),
                         "edge_type": etype, "known_at": known[m].to_numpy(),
                         "weight": (weight[m].to_numpy() if weight is not None else 1.0)})


def build_graph_edges(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    S = lambda c: E[c].astype("string") if c in E.columns else pd.Series(pd.NA, index=E.index, dtype="string")
    doc = ("DOC␟" + S("stage") + "␟" + S("doc_id"))
    stage_node = (S("stage") + "␟" + S("doc_id"))
    opp = "OPPORTUNITY␟" + S("opportunity_id")
    ka = E["available_at"]
    amt = pd.to_numeric(E.get("amount"), errors="coerce")
    parts = [
        _edges("AGENCY␟" + S("agency_cd"), stage_node, "ISSUES", ka, amt),
        _edges(stage_node, "CATEGORY␟" + S("category_cd"), "IN_CATEGORY", ka, amt),
        _edges(stage_node, "LICENSE␟" + S("license_req"), "REQUIRES_LICENSE", ka),
        _edges(stage_node, "REGION␟" + S("region_limit"), "IN_REGION", ka),
        _edges(stage_node, opp, "BELONGS_TO", ka, amt),
        _edges(stage_node.where(E["stage"].isin(["AWARD", "CONTRACT"])),
               "SUPPLIER␟" + S("supplier_bizno"), "AWARDED_TO", ka, amt),
    ]
    # 단계 전이 PRECEDES / BECOMES — 같은 opportunity 안에서 시간순 인접 단계끼리 잇는다
    d = E[["opportunity_id", "stage", "doc_id", "available_at"]].dropna(subset=["opportunity_id"]).copy()
    d["rank"] = d["stage"].map(STAGE_RANK)
    d = d.dropna(subset=["rank"]).sort_values(["opportunity_id", "rank", "available_at"], kind="stable")
    d["node"] = d["stage"].astype(str) + "␟" + d["doc_id"].astype(str)
    g = d.groupby("opportunity_id", sort=False)
    d["prev_node"] = g["node"].shift(1)
    d["prev_rank"] = g["rank"].shift(1)
    adv = d[d["prev_node"].notna() & (d["rank"] > d["prev_rank"])]
    if len(adv):
        et = np.where((adv["prev_rank"] == STAGE_RANK["AWARD"]) &
                      (adv["rank"] == STAGE_RANK["CONTRACT"]), "BECOMES", "PRECEDES")
        parts.append(pd.DataFrame({"src": adv["prev_node"].to_numpy(), "dst": adv["node"].to_numpy(),
                                   "edge_type": et, "known_at": adv["available_at"].to_numpy(),
                                   "weight": 1.0}))
    if crosswalk is not None and len(crosswalk):
        cw = crosswalk.dropna(subset=["stock_code", "bizr_no"]).copy()
        kn = pd.to_datetime(cw.get("valid_from")).fillna(pd.Timestamp("1990-01-01"))
        parts.append(_edges("SUPPLIER␟" + cw["bizr_no"].astype("string"),
                            "LISTED_COMPANY␟" + cw["stock_code"].astype("string"),
                            "MAPS_TO", kn, pd.to_numeric(cw.get("confidence"), errors="coerce")))
    G = pd.concat([p for p in parts if len(p)], ignore_index=True)
    G = G.dropna(subset=["src", "dst"])
    return G.sort_values("known_at", kind="stable").reset_index(drop=True)


@dataclass
class DemandGraph:
    nodes: pd.DataFrame
    edges: pd.DataFrame

    def asof(self, t) -> "DemandGraph":
        """§7 — 시점 t 까지 알려진 노드·엣지만. 이 메서드 밖으로 그래프를 노출하지 않는다."""
        t = pd.Timestamp(t)
        n = self.nodes[self.nodes["known_at"] <= t]
        e = self.edges[self.edges["known_at"] <= t]
        alive = set(n["node_id"])
        e = e[e["src"].isin(alive) & e["dst"].isin(alive)]
        return DemandGraph(n.reset_index(drop=True), e.reset_index(drop=True))

    def summary(self) -> pd.DataFrame:
        a = self.nodes.groupby("node_type").size().rename("노드수").reset_index()
        b = self.edges.groupby("edge_type").size().rename("엣지수").reset_index()
        return pd.concat([a.rename(columns={"node_type": "종류", "노드수": "개수"}).assign(구분="노드"),
                          b.rename(columns={"edge_type": "종류", "엣지수": "개수"}).assign(구분="엣지")],
                         ignore_index=True)[["구분", "종류", "개수"]]


def build_graph(E: pd.DataFrame, crosswalk: Optional[pd.DataFrame] = None) -> DemandGraph:
    N = build_graph_nodes(E, crosswalk)
    G = build_graph_edges(E, crosswalk)
    LOG.ok(f"G2B Demand Graph: 노드 {len(N):,} · 엣지 {len(G):,}")
    return DemandGraph(N, G)


# ==========================================================================================
#  features/capability.py
# ==========================================================================================
"""기업의 '잘하는 영역' — Capability(i,c,t).   §17 · §18 · §19

정의 (PRIMARY — 과거 계약·낙찰만 사용, 미래정보 없음)

    decayed(i,c,t) = Σ_{k: t-L < t_k <= t}  award(i,c,t_k) · λ^(t - t_k)
    Capability(i,c,t) = decayed(i,c,t) / Σ_c decayed(i,c,t)

  L = lookback (기본 36개월), λ = 0.5^(1/half_life)

§18 첫 수주 이전 기업은 capability 를 알 수 없다 → 억지 추론하지 않고 결측으로 둔다.
§19 NEW_CATEGORY_ENTRY / NEW_AGENCY_ENTRY 는 36M warm-up 이 없는 기업에서 계산하지 않는다.

벡터화: (firm,cat,month) 희소 관측을 36개월 영향창으로 한 번 전개한 뒤 groupby-sum 한다.
        기업 루프·월 루프가 없다.
"""



DEFAULT_LOOKBACK_M = 36
DEFAULT_HALFLIFE_M = 18.0


def award_observations(events: pd.DataFrame, amount_col: str = "attributed_amount",
                       stages: Sequence[str] = ("AWARD",),
                       firm_col: str = "stock_code") -> pd.DataFrame:
    """(firm, category, agency, month, amount) 희소 관측. available_at 기준 월 배정(§53)."""
    e = events[events["stage"].isin(stages)].copy()
    e = e[e[firm_col].notna() & e[amount_col].notna()]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "category_cd", "agency_cd", "month", "amount"])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    g = (e.groupby([firm_col, "category_cd", "agency_cd", "month"], as_index=False, observed=True)
         [amount_col].sum().rename(columns={amount_col: "amount"}))
    return g


def _decay_expand(obs: pd.DataFrame, key_cols: Sequence[str], months: pd.DatetimeIndex,
                  lookback_m: int, halflife_m: float, value_col: str = "amount",
                  out_col: str = "decayed") -> pd.DataFrame:
    """희소 관측 → 36개월 영향창 전개 → 감쇠 가중합. 결과는 (key..., month, decayed).

    exp 감쇠이므로 관측 t_k 는 t_k..t_k+L-1 개월에만 영향을 준다. 그 창만 전개한다.
    """
    key_cols = list(key_cols)
    if obs is None or not len(obs):
        return pd.DataFrame(columns=key_cols + ["month", out_col])
    midx = pd.Series(np.arange(len(months)), index=months)
    o = obs.copy()
    o["_mi"] = o["month"].map(midx)
    o = o.dropna(subset=["_mi"])
    if not len(o):
        return pd.DataFrame(columns=key_cols + ["month", out_col])
    o["_mi"] = o["_mi"].astype("int32")
    lam = 0.5 ** (1.0 / max(halflife_m, 1e-6))
    off = np.arange(lookback_m, dtype="int32")
    w = lam ** off
    n = len(o)
    rep_i = np.repeat(np.arange(n), lookback_m)
    tgt = o["_mi"].to_numpy()[rep_i] + np.tile(off, n)
    val = o[value_col].to_numpy()[rep_i] * np.tile(w, n)
    keep = tgt < len(months)
    D = pd.DataFrame({c: o[c].to_numpy()[rep_i][keep] for c in key_cols})
    D["_mi"] = tgt[keep]
    D[out_col] = val[keep]
    R = D.groupby(key_cols + ["_mi"], as_index=False, observed=True)[out_col].sum()
    R["month"] = months.to_numpy()[R["_mi"].to_numpy()]
    return R.drop(columns=["_mi"])


def build_capability(events: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                     lookback_m: int = DEFAULT_LOOKBACK_M,
                     halflife_m: float = DEFAULT_HALFLIFE_M,
                     stages: Sequence[str] = ("AWARD",)) -> pd.DataFrame:
    """pit/company_capability_monthly.parquet (§89).

    반환: [firm, category_cd, month, decayed_award, capability, firm_decayed_total,
           n_obs_36m, first_award_month, months_since_first_award, warmed_up]
    """
    obs = award_observations(events, amount_col, stages, firm_col)
    if not len(obs):
        LOG.warn("낙찰 관측이 없어 capability 를 만들 수 없습니다(§18 억지 추론 금지).")
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "capability"])
    dec = _decay_expand(obs, [firm_col, "category_cd"], months, lookback_m, halflife_m,
                        "amount", "decayed_award")
    cnt = _decay_expand(obs.assign(one=1.0), [firm_col, "category_cd"], months,
                        lookback_m, 1e9, "one", "n_obs_36m")     # halflife 무한 = 단순 건수
    C = dec.merge(cnt, on=[firm_col, "category_cd", "month"], how="left")
    C["firm_decayed_total"] = C.groupby([firm_col, "month"], observed=True)["decayed_award"].transform("sum")
    C["capability"] = C["decayed_award"] / C["firm_decayed_total"].replace(0, np.nan)

    first = obs.groupby(firm_col, observed=True)["month"].min().rename("first_award_month")
    C = C.merge(first, left_on=firm_col, right_index=True, how="left")
    C["months_since_first_award"] = (
        (C["month"].dt.year - C["first_award_month"].dt.year) * 12 +
        (C["month"].dt.month - C["first_award_month"].dt.month))
    C["warmed_up"] = C["months_since_first_award"] >= lookback_m     # §19
    LOG.ok(f"capability: {C[firm_col].nunique():,}개 기업 × {C['category_cd'].nunique():,}개 품목 "
           f"= {len(C):,}행 (lookback {lookback_m}M, 반감기 {halflife_m:.0f}M)")
    return C


def agency_capability(events: pd.DataFrame, months: pd.DatetimeIndex,
                      firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                      lookback_m: int = DEFAULT_LOOKBACK_M,
                      halflife_m: float = DEFAULT_HALFLIFE_M) -> pd.DataFrame:
    """발주기관 축 역량 — §30 NEW_AGENCY 와 §33 집중도의 입력."""
    obs = award_observations(events, amount_col, ("AWARD",), firm_col)
    if not len(obs):
        return pd.DataFrame(columns=[firm_col, "agency_cd", "month", "decayed_award"])
    A = _decay_expand(obs, [firm_col, "agency_cd"], months, lookback_m, halflife_m,
                      "amount", "decayed_award")
    A["firm_decayed_total"] = A.groupby([firm_col, "month"], observed=True)["decayed_award"].transform("sum")
    A["agency_share"] = A["decayed_award"] / A["firm_decayed_total"].replace(0, np.nan)
    return A


def capability_persistence(C: pd.DataFrame, firm_col: str = "stock_code",
                           horizons: Sequence[int] = (12, 24, 36)) -> pd.DataFrame:
    """capability 가 실제로 지속적인지 진단 — 지속성이 없으면 '잘하는 영역' 개념 자체가 무너진다."""
    if C is None or not len(C):
        return pd.DataFrame()
    d = C[[firm_col, "category_cd", "month", "capability"]].dropna()
    rows = []
    for h in horizons:
        fut = d.copy()
        fut["month"] = fut["month"] - pd.DateOffset(months=h)
        m = d.merge(fut, on=[firm_col, "category_cd", "month"], suffixes=("", "_fwd"))
        if len(m) > 10:
            rows.append({"수평선(개월)": h, "표본": len(m),
                         "자기상관(Spearman)": float(m["capability"].corr(m["capability_fwd"],
                                                                        method="spearman"))})
    return pd.DataFrame(rows)


# ==========================================================================================
#  features/government_demand.py
# ==========================================================================================
"""GovernmentDemand(c,t) — 외생적 정부수요.   §20 · §45 · §83

★ 이 파일의 유일한 규율: **winner 를 보기 전에 계산한다.**
   정부수요는 발주계획·사전규격·입찰공고에서만 만든다. 기업의 낙찰액으로 정의하면
   그것은 '정부수요'가 아니라 '그 기업 실적'이고, 축이 두 개가 아니라 하나가 된다.

산출
  D1 flow  : 신규로 등장한 정부수요 (lifecycle 증분 — §8/§11 이중계산 불가)
  D2 stock : 시점 t 에 이미 공개되어 있고 아직 집행되지 않은 파이프라인 잔량
  §45 LOFO : 시점 t 까지 '이미 알려진' 낙찰이 기업 i 인 건을 i 의 수요에서 뺀다.
             (미래 낙찰자를 쓰면 그 자체가 누수이므로 '알려진' 것만 쓴다)
  §83      : 반복발주(기존 수주기업 대상)와 카테고리 전체 성장을 분리한다.
"""



PRE_AWARD_STAGES = ("PLAN", "PRESPEC", "BID")
PIPELINE_MAX_AGE_M = 24          # 낙찰이 관측되지 않은 채 이만큼 지나면 파이프라인에서 소멸시킨다
WARMUP_NOTE_M = 36               # §19 좌측절단 경고문에 쓰는 권장 warm-up 개월


def preaward_ladder(events: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """winner 를 보기 전 단계만으로 계단함수를 만든다 — 이것이 외생성의 정의다."""
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)]
    if not len(pre):
        LOG.warn("PLAN/PRESPEC/BID 이벤트가 없습니다 — 외생 수요축을 만들 수 없습니다(§20).")
        return pd.DataFrame(columns=["opportunity_id", "available_at", "stage", "stage_rank",
                                     "best_amount", "demand_flow", "is_advance", "is_revision"])
    return stage_ladder(pre, amount_col)


def opportunity_attrs(events: pd.DataFrame) -> pd.DataFrame:
    """opportunity 의 카테고리/기관/유형 — 가장 이른 사전단계 문서 기준(사후 정보 사용 안 함)."""
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)]
    src = pre if len(pre) else events
    return (src.sort_values("available_at", kind="stable")
            .groupby("opportunity_id", as_index=False)
            .agg(category_cd=("category_cd", "first"), category_nm=("category_nm", "first"),
                 agency_cd=("agency_cd", "first"), proc_type=("proc_type", "first"),
                 license_req=("license_req", "first"), region_limit=("region_limit", "first"),
                 broad_category=("broad_category", "first") if "broad_category" in src.columns
                 else ("category_cd", "first")))


def award_known_at(events: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """각 opportunity 의 낙찰자가 '언제부터 알려졌는가'. §45 LOFO 와 파이프라인 소멸에 쓴다."""
    a = events[(events["stage"] == "AWARD")]
    if not len(a):
        return pd.DataFrame(columns=["opportunity_id", "award_known_at", firm_col])
    return (a.sort_values("available_at", kind="stable")
            .groupby("opportunity_id", as_index=False)
            .agg(award_known_at=("available_at", "min"),
                 **{firm_col: (firm_col, "first")} if firm_col in a.columns else {}))


def demand_panel(events: pd.DataFrame, months: pd.DatetimeIndex,
                 amount_col: str = "amount") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(카테고리×월 수요패널, opportunity 단위 수요흐름).

    반환 패널 컬럼:
      category_cd, month, demand_flow, pipeline_stock, n_new_opp, demand_flow_12m
    전부 groupby/cumsum 벡터화 — 카테고리 루프 없음.
    """
    lad = preaward_ladder(events, amount_col)
    if not len(lad):
        return (pd.DataFrame(columns=["category_cd", "month", "demand_flow", "pipeline_stock"]),
                lad)
    attrs = opportunity_attrs(events)
    lad = lad.merge(attrs, on="opportunity_id", how="left")
    lad["month"] = pd.to_datetime(lad["available_at"]) + pd.offsets.MonthEnd(0)

    # opportunity 의 첫 관측 여부 — '신규 조달건 수'는 단계전진 횟수가 아니다
    lad = lad.sort_values(["opportunity_id", "available_at"], kind="stable")
    lad["is_first_seen"] = ~lad.duplicated(subset=["opportunity_id"], keep="first")

    midx = pd.Series(np.arange(len(months)), index=months)
    lad["_mi"] = lad["month"].map(midx)
    n_before = int(lad["_mi"].isna().sum())
    lad = lad.dropna(subset=["_mi"]).copy()
    lad["_mi"] = lad["_mi"].astype("int32")
    if n_before:
        # 창 밖(주로 창 시작 이전)의 단계관측은 버려진다 → 그만큼 flow 합이 최종금액합보다 작다.
        # 이것은 좌측절단(§19)이며 숨기지 않는다. warm-up 구간을 두는 이유가 이것이다.
        LOG.info(f"수요 계단관측 {n_before:,}건이 분석창 밖이라 제외되었습니다(좌측절단 §19) — "
                 f"창 시작 전 {WARMUP_NOTE_M}개월 warm-up 수집이 필요한 이유입니다.")

    # ── D1 flow ────────────────────────────────────────────────────────────
    flow = (lad.groupby(["category_cd", "_mi"], as_index=False, observed=True)
            .agg(demand_flow=("demand_flow", "sum"),
                 n_new_opp=("is_first_seen", "sum")))

    # ── D2 pipeline stock: +증분 / 낙찰(또는 노후화) 시점에 -잔액 ────────────
    ak = award_known_at(events)
    last_state = (lad.sort_values(["opportunity_id", "_mi"], kind="stable")
                  .groupby("opportunity_id", as_index=False)
                  .agg(last_mi=("_mi", "last"), last_amt=("best_amount", "last"),
                       category_cd=("category_cd", "last")))
    exit_tbl = last_state.merge(ak[["opportunity_id", "award_known_at"]], on="opportunity_id", how="left")
    aw_mi = ((pd.to_datetime(exit_tbl["award_known_at"]) + pd.offsets.MonthEnd(0))
             .map(midx))
    stale_mi = exit_tbl["last_mi"] + PIPELINE_MAX_AGE_M
    exit_tbl["exit_mi"] = np.fmin(aw_mi.fillna(np.inf).to_numpy(), stale_mi.to_numpy())
    exit_tbl = exit_tbl[np.isfinite(exit_tbl["exit_mi"])]
    exit_tbl = exit_tbl[exit_tbl["exit_mi"] < len(months)]
    neg = exit_tbl.assign(_mi=exit_tbl["exit_mi"].astype("int32"),
                          delta=-exit_tbl["last_amt"])[["category_cd", "_mi", "delta"]]
    pos = lad.rename(columns={"demand_flow": "delta"})[["category_cd", "_mi", "delta"]]
    deltas = (pd.concat([pos, neg], ignore_index=True)
              .groupby(["category_cd", "_mi"], as_index=False, observed=True)["delta"].sum())

    # 조밀 격자 위에서 cumsum → 재고
    cats = pd.Index(pd.unique(pd.concat([flow["category_cd"], deltas["category_cd"]]).dropna()))
    grid = pd.MultiIndex.from_product([cats, np.arange(len(months))],
                                      names=["category_cd", "_mi"]).to_frame(index=False)
    P = (grid.merge(flow, on=["category_cd", "_mi"], how="left")
             .merge(deltas, on=["category_cd", "_mi"], how="left"))
    for c in ("demand_flow", "n_new_opp", "delta"):
        P[c] = P[c].fillna(0.0)
    P = P.sort_values(["category_cd", "_mi"], kind="stable")
    P["pipeline_stock"] = P.groupby("category_cd", observed=True)["delta"].cumsum().clip(lower=0)
    P["demand_flow_12m"] = (P.groupby("category_cd", observed=True)["demand_flow"]
                            .transform(lambda s: s.rolling(12, min_periods=1).sum()))
    P["demand_flow_3m"] = (P.groupby("category_cd", observed=True)["demand_flow"]
                           .transform(lambda s: s.rolling(3, min_periods=1).sum()))
    P["month"] = months.to_numpy()[P["_mi"].to_numpy()]
    P = P.drop(columns=["delta", "_mi"])
    LOG.ok(f"정부수요 패널: {P['category_cd'].nunique():,}개 품목 × {len(months)}개월 = {len(P):,}행 "
           f"(winner 정보 미사용 — 외생축)")
    return P.reset_index(drop=True), lad


def lofo_adjustment(lad: pd.DataFrame, events: pd.DataFrame, months: pd.DatetimeIndex,
                    firm_col: str = "stock_code") -> pd.DataFrame:
    """§45 Leave-One-Firm-Out — 시점 t 까지 '이미 알려진' 낙찰자가 i 인 건의 수요를 (i,c,t) 에서 뺀다.

    미래 낙찰자를 쓰면 그 자체가 누수이므로 award_known_at <= t 인 건만 뺀다.
    반환: [firm, category_cd, month, own_flow_known, own_stock_known]
    """
    a = events[(events["stage"] == "AWARD") & events[firm_col].notna()]
    if not len(a) or not len(lad):
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "own_flow_known"])
    ak = (a.sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False)
          .agg(award_known_at=("available_at", "min"), **{firm_col: (firm_col, "first")}))
    L = lad.merge(ak, on="opportunity_id", how="inner")
    # 그 낙찰이 알려진 이후의 월에만 차감한다
    L["known_month"] = pd.to_datetime(L["award_known_at"]) + pd.offsets.MonthEnd(0)
    L = L[L["month"] >= L["known_month"]]
    if not len(L):
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "own_flow_known"])
    out = (L.groupby([firm_col, "category_cd", "month"], as_index=False, observed=True)
           .agg(own_flow_known=("demand_flow", "sum")))
    return out


def exogeneity_split(events: pd.DataFrame, panel: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code") -> pd.DataFrame:
    """§83 — 카테고리 전체 성장 vs '기존 수주기업에 대한 반복발주'를 분리한다.

    반환 패널에 다음을 덧붙인다:
      incumbent_share  : 그 카테고리에서 직전 36M 낙찰이 상위 3개사에 집중된 정도
      new_agency_flow  : 그 카테고리에 '처음 등장한 발주기관'이 만든 수요 비중
    """
    if not len(panel):
        return panel
    a = events[(events["stage"] == "AWARD")].copy()
    P = panel.copy()
    if len(a):
        a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
        top = (a.groupby(["category_cd", "month", "supplier_bizno"], as_index=False, observed=True)
               ["amount"].sum())
        top["rk"] = top.groupby(["category_cd", "month"], observed=True)["amount"].rank(
            ascending=False, method="first")
        agg = top.groupby(["category_cd", "month"], as_index=False, observed=True).agg(
            tot=("amount", "sum"), top3=("amount", lambda s: s.nlargest(3).sum()))
        agg["incumbent_share"] = agg["top3"] / agg["tot"].replace(0, np.nan)
        P = P.merge(agg[["category_cd", "month", "incumbent_share"]],
                    on=["category_cd", "month"], how="left")
    else:
        P["incumbent_share"] = np.nan
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)].copy()
    if len(pre):
        pre["month"] = pd.to_datetime(pre["available_at"]) + pd.offsets.MonthEnd(0)
        first_seen = pre.groupby(["category_cd", "agency_cd"], observed=True)["month"].transform("min")
        pre["is_new_agency"] = pre["month"] == first_seen
        na = (pre.groupby(["category_cd", "month"], as_index=False, observed=True)
              .agg(tot_amt=("amount", "sum")))
        na2 = (pre[pre["is_new_agency"]].groupby(["category_cd", "month"], as_index=False, observed=True)
               .agg(new_agency_amt=("amount", "sum")))
        na = na.merge(na2, on=["category_cd", "month"], how="left")
        na["new_agency_flow_share"] = na["new_agency_amt"].fillna(0) / na["tot_amt"].replace(0, np.nan)
        P = P.merge(na[["category_cd", "month", "new_agency_flow_share"]],
                    on=["category_cd", "month"], how="left")
    return P


# ==========================================================================================
#  features/eligible_tam.py
# ==========================================================================================
"""Firm Eligible TAM 과 단계전환확률.   §21 · §22 · §23

    EligibleTAM(i,t) = Σ_c Capability(i,c,t) × GovernmentDemand(c,t)

  정교한 버전(§21):
    Σ_opportunity amount × capability_match × license_match × region_match × stage_probability

§22 발주계획 100억과 계약 100억을 같은 확률로 보지 않는다 → P(contract | stage) 를 곱한다.
§23 그 확률은 반드시 walk-forward 로 추정한다.
      · training_end < t
      · 아직 결과가 관측되지 않은 최근 건은 training label 에서 제거 (MATURITY_EMBARGO)
      · category → broad category → procurement type → global 로 hierarchical shrinkage
      · 표본이 작은 세부품목 확률을 직접 추정하지 않는다
"""



DEFAULT_MATURITY_DAYS = 365      # §23 사전 동결 대상 — 실제 분포를 보고 정한 뒤 preregistration 에 고정
SHRINK_K = 25.0                  # 경험적 베이즈 축소 강도 (상위 계층으로 backoff)


def maturity_distribution(events: pd.DataFrame) -> pd.DataFrame:
    """단계 → 계약까지 걸린 실제 일수 분포. MATURITY_EMBARGO 를 '수익률 보기 전에' 정하는 근거."""
    ct = (events[events["stage"] == "CONTRACT"].sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False).agg(t_contract=("available_at", "min")))
    if not len(ct):
        return pd.DataFrame()
    rows = []
    for st in ("PLAN", "PRESPEC", "BID", "AWARD"):
        s = (events[events["stage"] == st].sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False).agg(t_stage=("available_at", "min")))
        if not len(s):
            continue
        m = s.merge(ct, on="opportunity_id", how="inner")
        d = (m["t_contract"] - m["t_stage"]).dt.total_seconds() / 86400.0
        d = d[d >= 0]
        if not len(d):
            continue
        rows.append({"stage": st, "표본": len(d), "p25": float(d.quantile(.25)),
                     "중앙값": float(d.median()), "p75": float(d.quantile(.75)),
                     "p90": float(d.quantile(.90)), "p95": float(d.quantile(.95))})
    return pd.DataFrame(rows)


def _labels(events: pd.DataFrame, maturity_days: int) -> pd.DataFrame:
    """단계별 (코호트, 결과, 라벨가용시각). 결과는 'maturity_days 안에 계약에 도달했는가'."""
    attrs = opportunity_attrs(events)
    ct = (events[events["stage"] == "CONTRACT"].sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False).agg(t_contract=("available_at", "min")))
    out = []
    for st in ("PLAN", "PRESPEC", "BID", "AWARD"):
        s = (events[events["stage"] == st].sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False).agg(t_stage=("available_at", "min")))
        if not len(s):
            continue
        m = s.merge(ct, on="opportunity_id", how="left").merge(attrs, on="opportunity_id", how="left")
        horizon = m["t_stage"] + pd.Timedelta(days=maturity_days)
        m["outcome"] = (m["t_contract"].notna() & (m["t_contract"] <= horizon)).astype(float)
        # 라벨은 지평 도달 시점에야 확정된다. 그 전에 쓰면 미래를 보는 것이다.
        m["label_available_at"] = horizon
        m["stage"] = st
        out.append(m[["opportunity_id", "stage", "t_stage", "label_available_at", "outcome",
                      "category_cd", "broad_category", "proc_type"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _running(lbl: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """라벨가용시각 순 누적 (합, 건수). 이후 as-of 로 어느 시점에든 walk-forward 조회 가능."""
    keys = list(keys)
    d = lbl.sort_values("label_available_at", kind="stable").copy()
    g = d.groupby(keys, sort=False, observed=True)
    d["_s"] = g["outcome"].cumsum()
    d["_n"] = g.cumcount() + 1
    return (d[keys + ["label_available_at", "_s", "_n"]]
            .drop_duplicates(subset=keys + ["label_available_at"], keep="last"))


def stage_probability(events: pd.DataFrame, months: pd.DatetimeIndex,
                      maturity_days: int = DEFAULT_MATURITY_DAYS,
                      shrink_k: float = SHRINK_K) -> pd.DataFrame:
    """walk-forward P(contract | stage, category) — 계층 축소 포함.

    반환: [stage, category_cd, month, p_contract, n_train, p_source]
    각 month 에서 label_available_at <= month 인 라벨만 사용한다(§23).
    """
    lbl = _labels(events, maturity_days)
    if not len(lbl):
        return pd.DataFrame(columns=["stage", "category_cd", "month", "p_contract", "n_train"])
    lvl = {"cat": ["stage", "category_cd"], "broad": ["stage", "broad_category"],
           "ptype": ["stage", "proc_type"], "glob": ["stage"]}
    run = {k: _running(lbl, v) for k, v in lvl.items()}

    cells = lbl[["stage", "category_cd", "broad_category", "proc_type"]].drop_duplicates()
    grid = cells.merge(pd.DataFrame({"month": months}), how="cross")
    grid = grid.sort_values("month", kind="stable")
    for k, keys in lvl.items():
        r = run[k].sort_values("label_available_at", kind="stable")
        grid = pd.merge_asof(grid, r.rename(columns={"_s": f"s_{k}", "_n": f"n_{k}"}),
                             left_on="month", right_on="label_available_at", by=keys,
                             direction="backward", allow_exact_matches=True)
        grid = grid.drop(columns=["label_available_at"])
        grid[f"s_{k}"] = grid[f"s_{k}"].fillna(0.0)
        grid[f"n_{k}"] = grid[f"n_{k}"].fillna(0.0)

    # 위에서부터 내려오며 축소: global → ptype → broad → category
    p = np.where(grid["n_glob"] > 0, grid["s_glob"] / grid["n_glob"].replace(0, np.nan), 0.5)
    p = pd.Series(p, index=grid.index).fillna(0.5)
    for k in ("ptype", "broad", "cat"):
        s, n = grid[f"s_{k}"], grid[f"n_{k}"]
        p = (s + shrink_k * p) / (n + shrink_k)
    grid["p_contract"] = p.clip(0.0, 1.0)
    grid["n_train"] = grid["n_cat"]
    grid["p_source"] = np.where(grid["n_cat"] >= 30, "category",
                                np.where(grid["n_broad"] >= 30, "broad",
                                         np.where(grid["n_ptype"] >= 30, "proc_type", "global")))
    out = grid[["stage", "category_cd", "month", "p_contract", "n_train", "p_source"]]
    LOG.ok(f"단계전환확률(walk-forward, embargo {maturity_days}일): {len(out):,}행 · "
           f"평균 P(계약|BID)={out.loc[out['stage'] == 'BID', 'p_contract'].mean():.3f}")
    return out.reset_index(drop=True)


def stage_weighted_demand(lad: pd.DataFrame, sprob: pd.DataFrame,
                          months: pd.DatetimeIndex) -> pd.DataFrame:
    """단계확률 가중 정부수요 — (category × month). §22 의 구현.

    발주계획 단계의 100억은 P(contract|PLAN) 만큼만 수요로 센다.
    """
    if not len(lad):
        return pd.DataFrame(columns=["category_cd", "month", "demand_flow_w", "pipeline_w"])
    d = lad.copy()
    if len(sprob):
        d = d.merge(sprob[["stage", "category_cd", "month", "p_contract"]],
                    on=["stage", "category_cd", "month"], how="left")
        d["p_contract"] = d["p_contract"].fillna(d.groupby("stage")["p_contract"].transform("mean"))
    else:
        d["p_contract"] = 1.0
    d["p_contract"] = d["p_contract"].fillna(1.0)
    d["demand_flow_w"] = d["demand_flow"] * d["p_contract"]
    out = (d.groupby(["category_cd", "month"], as_index=False, observed=True)
           .agg(demand_flow_w=("demand_flow_w", "sum")))
    return out


def build_eligible_tam(capability: pd.DataFrame, demand: pd.DataFrame,
                       firm_col: str = "stock_code",
                       demand_cols: Sequence[str] = ("demand_flow", "demand_flow_3m",
                                                     "demand_flow_12m", "pipeline_stock"),
                       lofo: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """pit/eligible_tam_monthly.parquet (§89).

    EligibleTAM(i,t) = Σ_c Capability(i,c,t) × Demand(c,t)
    벡터화: capability(firm,cat,month) ⨝ demand(cat,month) → groupby(firm,month) 합.
    """
    if capability is None or not len(capability) or demand is None or not len(demand):
        return pd.DataFrame(columns=[firm_col, "month"])
    use = [c for c in demand_cols if c in demand.columns]
    M = capability[[firm_col, "category_cd", "month", "capability", "decayed_award",
                    "warmed_up"]].merge(
        demand[["category_cd", "month"] + use], on=["category_cd", "month"], how="left")
    for c in use:
        M[c] = M[c].fillna(0.0)
        M["_w_" + c] = M["capability"].fillna(0.0) * M[c]
    if lofo is not None and len(lofo):
        M = M.merge(lofo, on=[firm_col, "category_cd", "month"], how="left")
        M["own_flow_known"] = M["own_flow_known"].fillna(0.0)
        # §45 자기 자신의 '이미 알려진' 낙찰건이 만든 수요는 그 기업의 TAM 에서 뺀다
        M["_w_demand_flow_lofo"] = (M["capability"].fillna(0.0) *
                                    (M["demand_flow"] - M["own_flow_known"]))
    # lambda 집계는 그룹 수만큼 파이썬 호출이 일어난다 → 미리 컬럼으로 만들고 sum 으로 끝낸다
    M["_active"] = (M["capability"].fillna(0.0) > 0.01).astype("int32")
    M["_cap2"] = M["capability"].fillna(0.0) ** 2
    agg = {("eligible_" + c): ("_w_" + c, "sum") for c in use}
    if "_w_demand_flow_lofo" in M.columns:
        agg["eligible_demand_flow_lofo"] = ("_w_demand_flow_lofo", "sum")
    T = (M.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(**agg, n_active_categories=("_active", "sum"),
              capability_hhi=("_cap2", "sum"), warmed_up=("warmed_up", "max")))
    LOG.ok(f"EligibleTAM: {T[firm_col].nunique():,}개 기업 × 월 = {len(T):,}행")
    return T


# ==========================================================================================
#  features/win_features.py
# ==========================================================================================
"""기업 실행력 — WIN_REALIZATION 계열.   §25 · §26 · §27 · §30 · §31 · §32

  §25 award_amount_3M / 6M / 12M, contract_amount_12M
  §26 반드시 기업크기로 정규화: WIN_MCAP = award/PIT_market_cap, WIN_SALES = award/PIT_last_known_sales
      매출은 t 시점에 '공개된' 마지막 DART 재무제표만 쓴다(§58) — 미래 사업보고서 소급 금지.
  §27 낙찰 가속도 — 두 산식을 모두 산출하되 PRIMARY 는 사전등록에서 하나만 동결.
  §30 NEW_AGENCY (과거 36M 미거래 기관), §31 NEW_CATEGORY (36M clean history 필수)
  §32 REPEAT_WIN_RATE (기관×품목)

수요가 늘어도 회사가 못 따내면 의미가 없다 — 이 축이 W 다.
"""




def _monthly_firm(events: pd.DataFrame, stage: str, months: pd.DatetimeIndex,
                  firm_col: str, amount_col: str) -> pd.DataFrame:
    e = events[(events["stage"] == stage) & events[firm_col].notna() & events[amount_col].notna()]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month", "amt", "n"])
    e = e.copy()
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    g = (e.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(amt=(amount_col, "sum"), n=(amount_col, "size")))
    return g[g["month"].isin(months)]


def _dense(panel: pd.DataFrame, months: pd.DatetimeIndex, firm_col: str,
           value_cols: Sequence[str]) -> pd.DataFrame:
    if not len(panel):
        return pd.DataFrame(columns=[firm_col, "month"] + list(value_cols))
    firms = pd.Index(pd.unique(panel[firm_col]))
    grid = pd.MultiIndex.from_product([firms, months], names=[firm_col, "month"]).to_frame(index=False)
    out = grid.merge(panel, on=[firm_col, "month"], how="left")
    for c in value_cols:
        out[c] = out[c].fillna(0.0)
    return out.sort_values([firm_col, "month"], kind="stable").reset_index(drop=True)


def build_win_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                       firm_col: str = "stock_code",
                       amount_col: str = "attributed_amount") -> pd.DataFrame:
    """수주 실현 피처 (기업×월). 전부 groupby+rolling 벡터화."""
    aw = _monthly_firm(events, "AWARD", months, firm_col, amount_col)
    ct = _monthly_firm(events, "CONTRACT", months, firm_col, amount_col)
    if not len(aw) and not len(ct):
        LOG.warn("낙찰/계약 이벤트가 없어 WIN 피처를 만들 수 없습니다.")
        return pd.DataFrame(columns=[firm_col, "month"])
    A = _dense(aw.rename(columns={"amt": "award_amt", "n": "award_n"}), months, firm_col,
               ["award_amt", "award_n"])
    if len(ct):
        C = _dense(ct.rename(columns={"amt": "contract_amt", "n": "contract_n"}), months, firm_col,
                   ["contract_amt", "contract_n"])
        W = A.merge(C, on=[firm_col, "month"], how="outer")
    else:
        W = A.assign(contract_amt=0.0, contract_n=0.0)
    for c in ("award_amt", "award_n", "contract_amt", "contract_n"):
        W[c] = W[c].fillna(0.0)
    W = W.sort_values([firm_col, "month"], kind="stable")
    g = W.groupby(firm_col, sort=False, observed=True)
    for w in (3, 6, 12):
        W[f"award_amt_{w}m"] = g["award_amt"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
        W[f"award_n_{w}m"] = g["award_n"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
    W["contract_amt_12m"] = g["contract_amt"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    W["award_amt_ttm"] = W["award_amt_12m"]

    # §27 두 가지 가속도 산식 — PRIMARY 는 preregistration 에서 하나만 고른다
    W["award_amt_prev9m"] = g["award_amt"].transform(
        lambda s: s.shift(3).rolling(9, min_periods=3).sum())
    W["win_accel_rate"] = (W["award_amt_3m"] / 3.0) - (W["award_amt_prev9m"] / 9.0)
    W["award_ttm_lag12"] = g["award_amt_ttm"].transform(lambda s: s.shift(12))
    W["win_accel_log"] = np.log1p(W["award_amt_ttm"].clip(lower=0)) - \
                         np.log1p(W["award_ttm_lag12"].clip(lower=0))
    return W.reset_index(drop=True)


def add_size_normalization(W: pd.DataFrame, market: Optional[pd.DataFrame],
                           pit_sales: Optional[pd.DataFrame], firm_col: str = "stock_code"
                           ) -> pd.DataFrame:
    """§26 — WIN_MCAP / WIN_SALES. 매출은 §58 에 따라 '그 시점에 공개된' 것만 쓴다."""
    out = W.copy()
    if market is not None and len(market):
        mk = market[[firm_col, "month", "mcap"]].dropna()
        out = out.merge(mk, on=[firm_col, "month"], how="left")
        out["WIN_MCAP"] = safe_div(out["award_amt_12m"], out["mcap"])
        out["WIN_MCAP_3M"] = safe_div(out["award_amt_3m"], out["mcap"])
        out["CONTRACT_MCAP"] = safe_div(out["contract_amt_12m"], out["mcap"])
    else:
        out["WIN_MCAP"] = np.nan
        LOG.warn("시가총액이 없어 WIN_MCAP(§26)을 계산할 수 없습니다.")
    if pit_sales is not None and len(pit_sales):
        s = pit_sales.sort_values("filing_ts", kind="stable")
        left = out.sort_values("month", kind="stable")
        # merge_asof: month 시점에 이미 '접수'된 마지막 재무제표만 붙는다 (§58)
        out = pd.merge_asof(left, s[[firm_col, "filing_ts", "revenue"]].rename(
            columns={"filing_ts": "sales_filing_ts", "revenue": "pit_revenue"}),
            left_on="month", right_on="sales_filing_ts", by=firm_col, direction="backward",
            allow_exact_matches=True)
        out["WIN_SALES"] = safe_div(out["award_amt_12m"], out["pit_revenue"])
        out["CONTRACT_SALES"] = safe_div(out["contract_amt_12m"], out["pit_revenue"])
    else:
        out["WIN_SALES"] = np.nan
        LOG.warn("PIT 매출이 없어 WIN_SALES(§26)를 계산할 수 없습니다 — NOT_IDENTIFIABLE 로 보고합니다.")
    return out


def breadth_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code", lookback_m: int = 36,
                     recent_m: int = 12, amount_col: str = "attributed_amount") -> pd.DataFrame:
    """§30 NEW_AGENCY · §31 NEW_CATEGORY · §32 REPEAT_WIN.

    '신규'는 과거 36개월에 거래하지 않았던 기관/품목이다. 36M clean history 가 없는 기업에서는
    계산하지 않는다(§19 좌측절단) → warmed_up=False 로 표시하고 값을 NaN 으로 둔다.
    """
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month"])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    e = e[e["month"].isin(months)]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month"])
    e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)

    rows = []
    for dim, col in (("agency", "agency_cd"), ("category", "category_cd")):
        o = (e.dropna(subset=[col]).groupby([firm_col, col, "month"], as_index=False, observed=True)
             .agg(amt=("amt", "sum")))
        if not len(o):
            continue
        # 최근 12M 거래 / 과거 36M 거래 (감쇠 없음 = halflife 무한)
        rec = _decay_expand(o.assign(one=1.0), [firm_col, col], months, recent_m, 1e9, "one", "n_recent")
        rec_amt = _decay_expand(o, [firm_col, col], months, recent_m, 1e9, "amt", "amt_recent")
        old = _decay_expand(o.assign(one=1.0), [firm_col, col], months, lookback_m + recent_m,
                            1e9, "one", "n_all")
        M = rec.merge(rec_amt, on=[firm_col, col, "month"], how="outer") \
               .merge(old, on=[firm_col, col, "month"], how="outer")
        for c in ("n_recent", "amt_recent", "n_all"):
            M[c] = M[c].fillna(0.0)
        # 과거 36M(=n_all - n_recent) 에 없었고 최근 12M 에 있으면 '신규'
        M["is_new"] = (M["n_recent"] > 0) & ((M["n_all"] - M["n_recent"]) <= 0)
        M["_act"] = (M["n_recent"] > 0).astype("int32")
        F = (M.groupby([firm_col, "month"], as_index=False, observed=True)
             .agg(**{f"new_{dim}_count": ("is_new", "sum"),
                     f"active_{dim}_count": ("_act", "sum")}))
        na = (M[M["is_new"]].groupby([firm_col, "month"], as_index=False, observed=True)
              .agg(**{f"new_{dim}_amt": ("amt_recent", "sum")}))
        tot = (M.groupby([firm_col, "month"], as_index=False, observed=True)
               .agg(**{f"tot_{dim}_amt": ("amt_recent", "sum")}))
        F = F.merge(na, on=[firm_col, "month"], how="left").merge(tot, on=[firm_col, "month"], how="left")
        F[f"new_{dim}_award_share"] = (F[f"new_{dim}_amt"].fillna(0.0) /
                                       F[f"tot_{dim}_amt"].replace(0, np.nan))
        rows.append(F)
    if not rows:
        return pd.DataFrame(columns=[firm_col, "month"])
    B = rows[0]
    for r in rows[1:]:
        B = B.merge(r, on=[firm_col, "month"], how="outer")

    # §32 REPEAT_WIN — 같은 (기관×품목)에서 이전 수주 이후 재수주한 비율
    pair = (e.dropna(subset=["agency_cd", "category_cd"])
            .groupby([firm_col, "agency_cd", "category_cd", "month"], as_index=False, observed=True)
            .agg(amt=("amt", "sum")))
    if len(pair):
        p_recent = _decay_expand(pair.assign(one=1.0), [firm_col, "agency_cd", "category_cd"],
                                 months, recent_m, 1e9, "one", "n_recent")
        p_all = _decay_expand(pair.assign(one=1.0), [firm_col, "agency_cd", "category_cd"],
                              months, lookback_m + recent_m, 1e9, "one", "n_all")
        PP = p_recent.merge(p_all, on=[firm_col, "agency_cd", "category_cd", "month"], how="outer")
        PP[["n_recent", "n_all"]] = PP[["n_recent", "n_all"]].fillna(0.0)
        PP["is_repeat"] = (PP["n_recent"] > 0) & ((PP["n_all"] - PP["n_recent"]) > 0)
        PP["is_active"] = PP["n_recent"] > 0
        R = (PP.groupby([firm_col, "month"], as_index=False, observed=True)
             .agg(repeat_pairs=("is_repeat", "sum"), active_pairs=("is_active", "sum")))
        R["REPEAT_WIN_RATE"] = R["repeat_pairs"] / R["active_pairs"].replace(0, np.nan)
        B = B.merge(R, on=[firm_col, "month"], how="outer")

    first = e.groupby(firm_col, observed=True)["month"].min().rename("first_award_month")
    B = B.merge(first, left_on=firm_col, right_index=True, how="left")
    msf = ((B["month"].dt.year - B["first_award_month"].dt.year) * 12 +
           (B["month"].dt.month - B["first_award_month"].dt.month))
    B["breadth_warmed_up"] = msf >= lookback_m
    for c in [c for c in B.columns if c.startswith(("new_", "REPEAT_"))]:
        B.loc[~B["breadth_warmed_up"], c] = np.nan       # §19 warm-up 없으면 계산하지 않는다
    LOG.ok(f"breadth 피처: {len(B):,}행 (warm-up 충족 {B['breadth_warmed_up'].mean() * 100:.0f}%)")
    return B.reset_index(drop=True)


# ==========================================================================================
#  features/competition.py
# ==========================================================================================
"""경쟁강도 · 낙찰률 · 유찰/재입찰 · 전환율.   §35 · §36 · §37 · §38 · §39

★ 이 파일의 모든 변수는 PRIMARY 팩터가 아니라 **진단용**이다(§76).
  경제적 부호가 조달방식마다 다르므로 성과를 본 뒤 부호를 뒤집는 짓을 막기 위해
  여기서는 부호를 붙이지 않고 값만 만든다. V2 에 넣으려면 별도 preregistration 이 필요하다.

§35 bidder_count 는 절대값이 아니라 (category × method × year × agency_type) 내 상대값으로 본다.
§36 낙찰률은 제도 차이가 있으므로 raw 비교 금지 → ResidualAwardRate.
§37 높은 유찰률은 반드시 악재가 아니다 → 임의의 음(-) 부호를 넣지 않는다.
§38 참여업체 전체정보가 불완전하면 NOT_IDENTIFIABLE 로 두고 가짜 conversion rate 를 만들지 않는다.
"""




def _cell_residual(d: pd.DataFrame, value: str, cells: Sequence[str], min_n: int = 20) -> pd.Series:
    """셀 내 평균 대비 잔차. 셀 표본이 작으면 상위 셀로 backoff 하고, 끝내 작으면 NaN."""
    v = pd.to_numeric(d[value], errors="coerce")
    out = pd.Series(np.nan, index=d.index)
    remaining = pd.Series(True, index=d.index)
    for k in range(len(cells), 0, -1):
        key = list(cells[:k])
        g = v.groupby([d[c] for c in key], observed=True)
        mu = g.transform("mean")
        n = g.transform("size")
        ok = remaining & (n >= min_n) & v.notna()
        out[ok] = (v - mu)[ok]
        remaining &= ~ok
        if not bool(remaining.any()):
            break
    return out


def award_rate_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                        firm_col: str = "stock_code") -> pd.DataFrame:
    """§36 — ResidualAwardRate 를 (category × method × year) 안에서 계산한 뒤 기업×월로 집계."""
    a = events[(events["stage"] == "AWARD")].copy()
    if not len(a):
        return pd.DataFrame(columns=[firm_col, "month"])
    rate = pd.to_numeric(a.get("award_rate"), errors="coerce")
    fallback = safe_div(a.get("amount"), a.get("expected_price")) * 100.0
    a["award_rate_use"] = rate.where(rate.between(30, 130), fallback)
    a["year"] = pd.to_datetime(a["available_at"]).dt.year
    a["resid_award_rate"] = _cell_residual(a, "award_rate_use",
                                           ["category_cd", "method", "year"])
    a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    f = a[a[firm_col].notna()]
    if not len(f):
        return pd.DataFrame(columns=[firm_col, "month"])
    W = (f.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(award_rate_mean=("award_rate_use", "mean"),
              resid_award_rate=("resid_award_rate", "mean"),
              award_rate_n=("award_rate_use", "count")))
    cov = float(a["award_rate_use"].notna().mean())
    if cov < 0.2:
        LOG.warn(f"예정가격/낙찰률 보유율 {cov * 100:.1f}% — §36 낙찰률 지표가 사실상 죽습니다. "
                 f"결과 해석 시 반드시 감안하십시오.")
    return W


def competition_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                         firm_col: str = "stock_code") -> pd.DataFrame:
    """§35 — 기업이 노출된 시장의 상대적 경쟁강도."""
    a = events[(events["stage"] == "AWARD")].copy()
    if not len(a) or "bidder_count" not in a.columns:
        return pd.DataFrame(columns=[firm_col, "month"])
    a["year"] = pd.to_datetime(a["available_at"]).dt.year
    a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    bc = pd.to_numeric(a["bidder_count"], errors="coerce")
    if bc.notna().mean() < 0.05:
        LOG.warn("bidder_count 보유율이 5% 미만 — 경쟁강도(§35)를 NOT_IDENTIFIABLE 로 둡니다.")
        return pd.DataFrame(columns=[firm_col, "month"])
    a["resid_bidder_count"] = _cell_residual(a, "bidder_count", ["category_cd", "method", "year"])
    f = a[a[firm_col].notna()]
    return (f.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(bidder_count_mean=("bidder_count", "mean"),
                 resid_bidder_count=("resid_bidder_count", "mean")))


def failure_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                     capability: Optional[pd.DataFrame] = None,
                     firm_col: str = "stock_code") -> pd.DataFrame:
    """§37 — 기업이 '노출된 시장'의 유찰률·재입찰률. 부호를 붙이지 않는다.

    기업 단위 유찰은 관측되지 않으므로 (기업 역량비중 × 카테고리 유찰률) 로 노출도를 만든다.
    """
    b = events[events["stage"] == "BID"].copy()
    if not len(b):
        return pd.DataFrame(columns=[firm_col, "month"])
    st = b.get("status_raw", pd.Series("", index=b.index)).astype(str)
    b["is_failed"] = st.str.contains("유찰", na=False)
    b["is_rebid"] = st.str.contains("재입찰|재공고", regex=True, na=False)
    b["month"] = pd.to_datetime(b["available_at"]) + pd.offsets.MonthEnd(0)
    cat = (b.groupby(["category_cd", "month"], as_index=False, observed=True)
           .agg(fail_rate=("is_failed", "mean"), rebid_rate=("is_rebid", "mean"),
                n_bid=("is_failed", "size")))
    if capability is None or not len(capability):
        return cat.rename(columns={"category_cd": "category_cd"})
    M = capability[[firm_col, "category_cd", "month", "capability"]].merge(
        cat, on=["category_cd", "month"], how="left")
    M["_f"] = M["capability"] * M["fail_rate"]
    M["_r"] = M["capability"] * M["rebid_rate"]
    return (M.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(FAIL_RATE_exposure=("_f", "sum"), REBID_RATE_exposure=("_r", "sum")))


def win_conversion(events: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """§38 — wins / participated_bids.

    참여업체 전체정보가 복원되지 않으면 승자만으로 가짜 conversion rate 를 만들지 않는다.
    그런 경우 NOT_IDENTIFIABLE 한 줄만 반환한다.
    """
    part_cols = [c for c in ("participant_bizno", "prcbdr_bizno", "bidder_bizno")
                 if c in events.columns]
    if not part_cols:
        LOG.warn("입찰 참여업체 명부가 없습니다 → WIN_CONVERSION = NOT_IDENTIFIABLE (§38). "
                 "승자만으로 전환율을 만들지 않습니다.")
        return pd.DataFrame([{"status": "NOT_IDENTIFIABLE",
                              "reason": "참여업체 전체정보 부재 — 승자편향 전환율 생성 금지(§38)"}])
    p = events.dropna(subset=part_cols[:1])
    won = p.get("award_rank", pd.Series(np.nan, index=p.index)) == 1
    return (p.assign(won=won).groupby(part_cols[0], as_index=False)
            .agg(participated=("won", "size"), wins=("won", "sum"))
            .assign(WIN_CONVERSION=lambda d: d["wins"] / d["participated"].replace(0, np.nan)))


def pipeline_conversion(events: pd.DataFrame) -> pd.DataFrame:
    """§39 — category/agency 단위 단계전환율. 기업단위보다 이 수준에서 측정한다."""
    if not len(events):
        return pd.DataFrame()
    st = (events.groupby(["opportunity_id", "stage"], as_index=False, observed=True)
          .agg(t=("available_at", "min")))
    piv = st.pivot_table(index="opportunity_id", columns="stage", values="t", aggfunc="min")
    attrs = (events.sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False)
             .agg(category_cd=("category_cd", "first"), agency_cd=("agency_cd", "first"),
                  proc_type=("proc_type", "first")))
    P = attrs.merge(piv.reset_index(), on="opportunity_id", how="left")
    pairs = [("PLAN", "BID", "plan_to_bid"), ("PRESPEC", "BID", "prespec_to_bid"),
             ("BID", "AWARD", "bid_to_award"), ("AWARD", "CONTRACT", "award_to_contract")]
    rows = []
    for src, dst, nm in pairs:
        if src not in P.columns:
            continue
        has_src = P[src].notna()
        has_dst = P[dst].notna() if dst in P.columns else pd.Series(False, index=P.index)
        g = (P[has_src].assign(_ok=has_dst[has_src].astype(float))
             .groupby(["proc_type"], as_index=False, observed=True)
             .agg(n=("_ok", "size"), rate=("_ok", "mean")))
        g["transition"] = nm
        rows.append(g)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ==========================================================================================
#  features/concentration.py
# ==========================================================================================
"""집중도 · 대형계약 의존 · 계약변경.   §33 · §34 · §40 · §41 · §42 · §43

  §33 AGENCY_HHI = Σ s_a²      §34 CATEGORY_HHI
  §40 CONTRACT_REVISION_RATIO = final_known_contract / initial_contract
      단 t 시점에는 '그때까지 알려진 revision' 만 쓴다.
  §41 TOP1_SHARE / TOP3_SHARE — PRIMARY 와 분리된 risk diagnostic
  §42 처음부터 hard exclusion 하지 않는다. 연속형 risk score 로 만든다.
  §43 PROC_RISK 는 G2B_DWA 와 섞지 않은 상태로 먼저 검정한다.
"""




def _hhi(events: pd.DataFrame, months: pd.DatetimeIndex, dim: str, firm_col: str,
         amount_col: str, lookback_m: int, out_name: str) -> pd.DataFrame:
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].dropna(subset=[dim]).copy()
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month", out_name])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)
    o = e.groupby([firm_col, dim, "month"], as_index=False, observed=True).agg(amt=("amt", "sum"))
    R = _decay_expand(o, [firm_col, dim], months, lookback_m, 1e9, "amt", "amt_w")
    R["tot"] = R.groupby([firm_col, "month"], observed=True)["amt_w"].transform("sum")
    R["s2"] = (R["amt_w"] / R["tot"].replace(0, np.nan)) ** 2
    return (R.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(**{out_name: ("s2", "sum")}))


def build_concentration(events: pd.DataFrame, months: pd.DatetimeIndex,
                        firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                        lookback_m: int = 12) -> pd.DataFrame:
    """AGENCY_HHI · CATEGORY_HHI · TOP1/TOP3_SHARE."""
    A = _hhi(events, months, "agency_cd", firm_col, amount_col, lookback_m, "AGENCY_HHI")
    C = _hhi(events, months, "category_cd", firm_col, amount_col, lookback_m, "CATEGORY_HHI")
    out = A.merge(C, on=[firm_col, "month"], how="outer") if len(A) or len(C) else \
        pd.DataFrame(columns=[firm_col, "month"])

    # §41 단일 초대형 계약 의존 — TTM 내 최대 계약 / TTM 총액
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if len(e):
        e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
        e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)
        deal = e.groupby([firm_col, "opportunity_id", "month"], as_index=False, observed=True) \
                .agg(amt=("amt", "sum"))
        D = _decay_expand(deal, [firm_col, "opportunity_id"], months, lookback_m, 1e9, "amt", "amt_w")
        D = D[D["amt_w"] > 0]
        if len(D):
            D["rk"] = D.groupby([firm_col, "month"], observed=True)["amt_w"].rank(
                ascending=False, method="first")
            tot = (D.groupby([firm_col, "month"], as_index=False, observed=True)
                   .agg(tot=("amt_w", "sum")))
            t1 = (D[D["rk"] <= 1].groupby([firm_col, "month"], as_index=False, observed=True)
                  .agg(top1=("amt_w", "sum")))
            t3 = (D[D["rk"] <= 3].groupby([firm_col, "month"], as_index=False, observed=True)
                  .agg(top3=("amt_w", "sum")))
            T = tot.merge(t1, on=[firm_col, "month"], how="left").merge(
                t3, on=[firm_col, "month"], how="left")
            T["TOP1_SHARE"] = T["top1"] / T["tot"].replace(0, np.nan)
            T["TOP3_SHARE"] = T["top3"] / T["tot"].replace(0, np.nan)
            out = out.merge(T[[firm_col, "month", "TOP1_SHARE", "TOP3_SHARE"]],
                            on=[firm_col, "month"], how="outer")
    return out.reset_index(drop=True)


def contract_revision(events: pd.DataFrame, months: pd.DatetimeIndex,
                      firm_col: str = "stock_code") -> pd.DataFrame:
    """§40 — 시점 t 까지 '알려진' 계약변경만 반영한 증액/감액/취소 지표."""
    c = events[(events["stage"] == "CONTRACT") & events[firm_col].notna()].copy()
    if not len(c):
        return pd.DataFrame(columns=[firm_col, "month"])
    c["month"] = pd.to_datetime(c["available_at"]) + pd.offsets.MonthEnd(0)
    c = c.sort_values(["opportunity_id", "available_at"], kind="stable")
    g = c.groupby("opportunity_id", sort=False, observed=True)
    c["initial_amt"] = g["amount"].transform("first")
    c["prev_amt"] = g["amount"].shift(1)
    c["delta"] = pd.to_numeric(c["amount"], errors="coerce") - c["prev_amt"]
    c["is_increase"] = c["delta"] > 0
    c["is_decrease"] = c["delta"] < 0
    st = c.get("status_raw", pd.Series("", index=c.index)).astype(str)
    c["is_cancel"] = st.str.contains("취소|해지|DLT|삭제", regex=True, na=False)
    c["rev_ratio"] = pd.to_numeric(c["amount"], errors="coerce") / c["initial_amt"].replace(0, np.nan)
    out = (c.groupby([firm_col, "month"], as_index=False, observed=True)
           .agg(CONTRACT_REVISION_RATIO=("rev_ratio", "mean"),
                contract_increase_n=("is_increase", "sum"),
                contract_decrease_n=("is_decrease", "sum"),
                contract_cancel_n=("is_cancel", "sum"),
                contract_delta_amt=("delta", "sum")))
    return out


def proc_risk_score(F: pd.DataFrame, cols: Sequence[str] = ("AGENCY_HHI", "CATEGORY_HHI",
                                                            "TOP1_SHARE"),
                    month_col: str = "month") -> pd.Series:
    """§42·§43 — 연속형 risk score. hard exclusion 을 하지 않는다.

    각 위험 축을 월별 횡단면 백분위로 만든 뒤 평균. PRIMARY alpha 와 섞지 않는다.
    """
    use = [c for c in cols if c in F.columns]
    if not use:
        return pd.Series(np.nan, index=F.index)
    pct = pd.DataFrame(index=F.index)
    for c in use:
        pct[c] = F.groupby(month_col, observed=True)[c].rank(pct=True)
    return pct.mean(axis=1)


# ==========================================================================================
#  features/g2b_dwa.py
# ==========================================================================================
"""PRIMARY FACTOR — Demand-Win Alignment.   §24 · §28 · §29 · §44

    P_D = 횡단면 백분위(정부수요 이동 D)   ∈ [0,1]
    P_W = 횡단면 백분위(실제 수주 증가 W)  ∈ [0,1]

    G2B_DWA = sqrt(P_D × P_W)

  기하평균이므로 두 신호가 **모두** 높아야 높다. hard filter 를 쓰지 않아 표본이 붕괴하지 않고,
  한 축만 극단적으로 높은 기업이 억제된다(§28).

§24 D1 = DS_YOY = log1p(EligibleDemandFlow_3M_t) − log1p(EligibleDemandFlow_3M_{t−12})
    D2 = ExpectedGovernmentPipeline_12M  (t 시점에 이미 공개되어 있고 미래에 집행될 파이프라인)
§44 raw / sector-neutral / sector+log(mcap)-neutral 세 버전을 모두 만든다. PRIMARY 는 세 번째.
§29 2×2 메커니즘 검정 버킷도 여기서 만든다 (파라미터 탐색 도구로 쓰지 않는다).
"""



EPS = 1e-12


def xsec_pct(F: pd.DataFrame, col: str, month_col: str = "month",
             min_n: int = 20) -> pd.Series:
    """월별 횡단면 백분위 [0,1]. 표본이 min_n 미만인 달은 NaN — 가짜 순위를 만들지 않는다."""
    if col not in F.columns:
        return pd.Series(np.nan, index=F.index)
    v = pd.to_numeric(F[col], errors="coerce")
    g = v.groupby(F[month_col], observed=True)
    r = g.rank(pct=True, method="average")
    n = g.transform("count")
    return r.where(n >= min_n)


def neutralize(F: pd.DataFrame, col: str, month_col: str = "month",
               sector_col: str = "sector", size_col: str = "mcap",
               mode: str = "sector_size") -> pd.Series:
    """§44 — raw / sector / sector_size 중립화. 월별 OLS 잔차(더미+log시총)를 벡터적으로 계산.

    조달수요는 건설·방산·IT서비스에 집중되므로, 중립화를 하지 않으면
    '정부조달 산업에 투자한 효과'를 '기업선별 알파'로 오인하게 된다.
    """
    y = pd.to_numeric(F[col], errors="coerce")
    if mode == "raw":
        return y
    out = pd.Series(np.nan, index=F.index)
    has_sec = sector_col in F.columns
    has_size = size_col in F.columns and mode == "sector_size"
    for _, idx in F.groupby(month_col, observed=True).indices.items():
        idx = np.asarray(idx)
        yy = y.to_numpy()[idx]
        ok = np.isfinite(yy)
        if ok.sum() < 10:
            continue
        parts = [np.ones((ok.sum(), 1))]
        if has_sec:
            sec = pd.Categorical(F[sector_col].to_numpy()[idx][ok])
            if len(sec.categories) > 1:
                D = np.zeros((ok.sum(), len(sec.categories) - 1))
                codes = sec.codes
                for j in range(1, len(sec.categories)):
                    D[:, j - 1] = (codes == j).astype(float)
                parts.append(D)
        if has_size:
            sz = pd.to_numeric(pd.Series(F[size_col].to_numpy()[idx][ok]), errors="coerce")
            sz = np.log(sz.clip(lower=1.0)).to_numpy()
            sz = np.nan_to_num(sz, nan=float(np.nanmean(sz)) if np.isfinite(sz).any() else 0.0)
            parts.append(sz.reshape(-1, 1))
        X = np.hstack(parts)
        try:
            beta, *_ = np.linalg.lstsq(X, yy[ok], rcond=None)
            res = yy[ok] - X @ beta
        except Exception:                                      # noqa: BLE001
            continue
        pos = idx[ok]
        out.iloc[pos] = res
    return out


def build_demand_axis(T: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """§24 — D1(신규공고 Flow YoY) 과 D2(Forward Pipeline)."""
    d = T.sort_values([firm_col, "month"], kind="stable").copy()
    g = d.groupby(firm_col, sort=False, observed=True)
    flow3 = d.get("eligible_demand_flow_3m")
    if flow3 is None:
        d["eligible_demand_flow_3m"] = 0.0
        flow3 = d["eligible_demand_flow_3m"]
    d["_l3"] = np.log1p(flow3.clip(lower=0))
    d["_l3_lag12"] = g["_l3"].shift(12)
    d["D1_DS_YOY"] = d["_l3"] - d["_l3_lag12"]
    pipe = d.get("eligible_pipeline_stock")
    d["D2_PIPELINE"] = np.log1p(pipe.clip(lower=0)) if pipe is not None else np.nan
    if pipe is not None:
        d["_lp"] = np.log1p(pipe.clip(lower=0))
        d["D2_PIPELINE_YOY"] = d["_lp"] - g["_lp"].shift(12)
    lofo = d.get("eligible_demand_flow_lofo")
    if lofo is not None:
        d["_ll"] = np.log1p(lofo.clip(lower=0))
        d["D1_DS_YOY_LOFO"] = d["_ll"] - g["_ll"].shift(12)
    return d.drop(columns=[c for c in ("_l3", "_l3_lag12", "_lp", "_ll") if c in d.columns])


def build_win_axis(W: pd.DataFrame, firm_col: str = "stock_code",
                   primary: str = "win_accel_log") -> pd.DataFrame:
    """§25~§27 — W 축. PRIMARY 산식은 preregistration 에서 하나만 동결한다."""
    d = W.copy()
    if primary not in d.columns:
        raise KeyError(f"W축 PRIMARY 산식 '{primary}' 이 피처에 없습니다. "
                       f"사용가능: {[c for c in d.columns if c.startswith('win_')]}")
    d["W_PRIMARY"] = pd.to_numeric(d[primary], errors="coerce")
    return d


def build_dwa(F: pd.DataFrame, demand_col: str = "D1_DS_YOY", win_col: str = "W_PRIMARY",
              month_col: str = "month", min_n: int = 20,
              neutral_mode: str = "sector_size") -> pd.DataFrame:
    """G2B_DWA = sqrt(P_D × P_W). raw/sector/sector_size 세 버전 모두 산출(§44)."""
    d = F.copy()
    d["_D_raw"] = pd.to_numeric(d[demand_col], errors="coerce")
    d["_W_raw"] = pd.to_numeric(d[win_col], errors="coerce")
    for mode, tag in (("raw", "raw"), ("sector", "sec"), ("sector_size", "secsz")):
        Dn = neutralize(d, "_D_raw", month_col, mode=mode)
        Wn = neutralize(d, "_W_raw", month_col, mode=mode)
        d[f"P_D_{tag}"] = xsec_pct(d.assign(_x=Dn), "_x", month_col, min_n)
        d[f"P_W_{tag}"] = xsec_pct(d.assign(_x=Wn), "_x", month_col, min_n)
        d[f"G2B_DWA_{tag}"] = np.sqrt(d[f"P_D_{tag}"].clip(0, 1) * d[f"P_W_{tag}"].clip(0, 1))
    tag = {"raw": "raw", "sector": "sec", "sector_size": "secsz"}[neutral_mode]
    d["P_D"] = d[f"P_D_{tag}"]
    d["P_W"] = d[f"P_W_{tag}"]
    d["G2B_DWA"] = d[f"G2B_DWA_{tag}"]
    n_ok = int(d["G2B_DWA"].notna().sum())
    LOG.ok(f"G2B_DWA 산출: {n_ok:,}개 기업×월 유효 (중립화={neutral_mode}, "
           f"D={demand_col}, W={win_col})")
    return d


def mechanism_2x2(F: pd.DataFrame, month_col: str = "month") -> pd.DataFrame:
    """§29 — Demand High/Low × Win High/Low 버킷. 진단용이며 파라미터 탐색에 쓰지 않는다."""
    d = F.dropna(subset=["P_D", "P_W"]).copy()
    if not len(d):
        return pd.DataFrame()
    d["D_hi"] = d["P_D"] >= 0.5
    d["W_hi"] = d["P_W"] >= 0.5
    d["bucket"] = np.where(d["D_hi"] & d["W_hi"], "D_high_W_high",
                    np.where(d["D_hi"] & ~d["W_hi"], "D_high_W_low",
                      np.where(~d["D_hi"] & d["W_hi"], "D_low_W_high", "D_low_W_low")))
    return d


def factor_family(F: pd.DataFrame) -> Dict[str, str]:
    """§84 최종 비교표에 들어갈 5개 팩터의 컬럼 매핑."""
    return {
        "1_Award_Amount_only": "award_amt_12m",
        "2_Award_over_MCap": "WIN_MCAP",
        "3_Demand_Shift_only": "D1_DS_YOY",
        "4_Win_Acceleration_only": "W_PRIMARY",
        "5_Demand_Win_Alignment": "G2B_DWA",
    }


# ==========================================================================================
#  backtest/universe.py
# ==========================================================================================
"""PIT 투자 유니버스.   §49 · §50 · §51 · §57

  · 상장폐지 종목을 제거한 현재 종목목록을 과거 전체 기간에 쓰지 않는다(§3.2 §57).
  · 조달기업만으로 universe 를 사후 정의하지 않는다 — All tradable 과
    PIT procurement-observable 을 각각 보고한다(§50).
  · 매월 커버리지 게이트를 출력한다(§51). 미달이면 성과와 무관하게 SAMPLE_COLLAPSE.

가격 원천 우선순위 (캐시활용 최우선)
  ① 사용자의 PIT 한국주식 가격 DB (공용 인덱스 krx_ohlcv_daily / security_master)
  ② 없으면 SMOKE 합성 시장
"""



EXCLUDE_NAME_PAT = r"스팩|SPAC|우선주|리츠|REIT|ETN|상장지수"


def load_market_panel(months: pd.DatetimeIndex) -> Optional[pd.DataFrame]:
    """공용 인덱스의 일봉 → 월말 패널. 사용자가 이미 가진 PIT 가격 DB 를 그대로 재사용한다."""
    V = get_vault()
    px = V.get_table(CFG.SHARED_REUSE_TABLES["price"], scope="shared")
    if px is None or not len(px):
        LOG.warn("공용 인덱스에 krx_ohlcv_daily 가 없습니다 — SMOKE 합성 시장으로 진행합니다.")
        return None
    d = px.copy()
    cols = {c.lower(): c for c in d.columns}
    pick = lambda *n: next((cols[x] for x in n if x in cols), None)
    c_code, c_date = pick("code", "stock_code", "ticker"), pick("date", "dt", "trade_date")
    c_close = pick("adj_close", "close", "종가")
    if not all((c_code, c_date, c_close)):
        LOG.warn(f"krx_ohlcv_daily 스키마를 해석하지 못했습니다 (code={c_code}, date={c_date}, "
                 f"close={c_close}) — 합성 시장으로 진행합니다.")
        return None
    d["stock_code"] = d[c_code].map(to_code6)
    d["date"] = as_ts_series(d[c_date])
    d = d.dropna(subset=["stock_code", "date"])
    d["month"] = d["date"] + pd.offsets.MonthEnd(0)
    c_shares = pick("shares_outstanding", "shares", "listed_shares", "상장주식수")
    c_val = pick("turnover_value", "value", "거래대금", "amount")
    agg = {"close": (c_close, "last")}
    if c_shares:
        agg["shares"] = (c_shares, "last")
    if c_val:
        agg["turnover_value"] = (c_val, "mean")
    M = d.groupby(["stock_code", "month"], as_index=False, observed=True).agg(**agg)
    M = M.sort_values(["stock_code", "month"], kind="stable")
    M["ret"] = M.groupby("stock_code", observed=True)["close"].pct_change()
    M["mcap"] = M["close"] * M["shares"] if "shares" in M.columns else np.nan
    sm = V.get_table(CFG.SHARED_REUSE_TABLES["security_master"], scope="shared")
    if sm is not None and len(sm):
        s = sm.copy()
        idc = [c for c in s.columns if c.lower() in ("code", "stock_code", "ticker")]
        if idc:
            s["stock_code"] = s[idc[0]].map(to_code6)
            keep = [c for c in s.columns if c.lower() in
                    ("market", "sector", "name", "listing_date", "delisting_date")]
            M = M.merge(s[["stock_code"] + keep].drop_duplicates("stock_code"),
                        on="stock_code", how="left")
    LOG.ok(f"공용 캐시 가격 패널 재사용: {M['stock_code'].nunique():,}종목 × {len(M):,}행")
    return M[M["month"].isin(months)]


def build_universe(market: pd.DataFrame, months: pd.DatetimeIndex,
                   min_turnover: float = 3e8) -> pd.DataFrame:
    """PIT 유니버스 판정. 각 게이트에서 몇 종목이 떨어지는지 반드시 남긴다(§51)."""
    m = market.copy()
    if "month" not in m.columns:
        raise KeyError("market 패널에 month 가 없습니다.")
    m["in_listed"] = True
    nm = m.get("name", pd.Series("", index=m.index)).astype(str)
    m["not_excluded"] = ~nm.str.contains(EXCLUDE_NAME_PAT, regex=True, na=False)
    tv = pd.to_numeric(m.get("turnover_value"), errors="coerce")
    m["liquid"] = tv.isna() | (tv >= min_turnover)     # 거래대금 정보가 없으면 배제하지 않는다
    m["has_price"] = pd.to_numeric(m.get("ret"), errors="coerce").notna()
    m["in_universe"] = m["in_listed"] & m["not_excluded"] & m["liquid"] & m["has_price"]
    return m


def universe_decay_table(u: pd.DataFrame) -> pd.DataFrame:
    """어느 게이트에서 표본이 붕괴하는지 — 선택편향 감사표."""
    gates = ["in_listed", "not_excluded", "liquid", "has_price", "in_universe"]
    rows, prev = [], None
    for g in gates:
        if g not in u.columns:
            continue
        n = int(u[g].sum())
        rows.append({"게이트": g, "통과 관측": n,
                     "직전 대비 감소": (prev - n) if prev is not None else 0})
        prev = n
    return pd.DataFrame(rows)


def procurement_observable(events: pd.DataFrame, months: pd.DatetimeIndex,
                           firm_col: str = "stock_code") -> pd.DataFrame:
    """§50 — t 시점까지 낙찰이 '관측된' 기업. 현재 명단을 과거에 소급하지 않는다."""
    a = events[(events["stage"].isin(["AWARD", "CONTRACT"])) & events[firm_col].notna()]
    if not len(a):
        return pd.DataFrame(columns=[firm_col, "month", "observable"])
    first = (a.groupby(firm_col, observed=True)["available_at"].min()
             .rename("first_observed_at").reset_index())
    first["first_month"] = pd.to_datetime(first["first_observed_at"]) + pd.offsets.MonthEnd(0)
    grid = first.merge(pd.DataFrame({"month": months}), how="cross")
    grid = grid[grid["month"] >= grid["first_month"]]
    grid["observable"] = True
    return grid[[firm_col, "month", "observable"]]


def coverage_gate(F: pd.DataFrame, score_col: str, universe: Optional[pd.DataFrame],
                  top_pct: float = 0.20, gates: Optional[dict] = None) -> Tuple[pd.DataFrame, dict]:
    """§51 — 매월 universe_N / mapped_N / scored_N / top_bucket_N 과 median·p10·min."""
    gates = gates or {"median_scored_firms_min": 100, "p10_scored_firms_min": 60,
                      "median_holdings_min": 20}
    if universe is not None and len(universe) and "in_universe" in universe.columns:
        u = (universe[universe["in_universe"]].groupby("month", observed=True)["stock_code"]
             .nunique().rename("universe_N"))
    else:
        u = pd.Series(dtype=int, name="universe_N")
    mapped = (F.dropna(subset=["stock_code"]).groupby("month", observed=True)["stock_code"]
              .nunique().rename("mapped_firms_N"))
    sc = F.dropna(subset=[score_col])
    scored = sc.groupby("month", observed=True)["stock_code"].nunique().rename("scored_firms_N")
    top = (scored * top_pct).apply(np.floor).rename("top_bucket_N")
    T = pd.concat([u, mapped, scored, top], axis=1).fillna(0).astype(int).reset_index(
        names="month")
    stat = lambda s: {"median": float(np.median(s)) if len(s) else 0.0,
                      "p10": float(np.percentile(s, 10)) if len(s) else 0.0,
                      "min": float(np.min(s)) if len(s) else 0.0}
    nz = T[T["scored_firms_N"] > 0]
    res = {"universe": stat(T["universe_N"]), "scored": stat(nz["scored_firms_N"]),
           "top_bucket": stat(nz["top_bucket_N"]), "months": len(T),
           "months_with_scores": len(nz)}
    res["pass_median_scored"] = bool(res["scored"]["median"] >= gates["median_scored_firms_min"])
    res["pass_p10_scored"] = bool(res["scored"]["p10"] >= gates["p10_scored_firms_min"])
    res["pass_median_holdings"] = bool(res["top_bucket"]["median"] >= gates["median_holdings_min"])
    res["verdict"] = ("PASS" if all((res["pass_median_scored"], res["pass_p10_scored"],
                                     res["pass_median_holdings"])) else "SAMPLE_COLLAPSE")
    return T, res


# ==========================================================================================
#  backtest/costs.py
# ==========================================================================================
"""거래비용 — §59. 고정 0bp 백테스트를 최종성과로 쓰지 않는다.

  commission + 당시 제도의 증권거래세(매도) + bid-ask/slippage + market impact
  1× / 2× / 3× 스트레스 배수를 함께 산출한다.
"""



# 당시 제도 기준 매도 증권거래세(농특세 포함, bp). backtest_policy.yaml 과 같은 값.
SELL_TAX_SCHEDULE: List[dict] = [
    {"from": "2015-01-01", "KOSPI": 30.0, "KOSDAQ": 30.0},
    {"from": "2019-06-03", "KOSPI": 25.0, "KOSDAQ": 25.0},
    {"from": "2021-01-01", "KOSPI": 23.0, "KOSDAQ": 23.0},
    {"from": "2023-01-01", "KOSPI": 20.0, "KOSDAQ": 20.0},
    {"from": "2025-01-01", "KOSPI": 18.0, "KOSDAQ": 18.0},
]


def sell_tax_bps(months, market=None) -> pd.Series:
    """월별·시장별 매도세(bp). 현재 세율을 과거에 소급하지 않는다."""
    sch = pd.DataFrame(SELL_TAX_SCHEDULE)
    sch["from"] = pd.to_datetime(sch["from"])
    sch = sch.sort_values("from")
    ms = pd.Series(months)
    idx = np.searchsorted(sch["from"].to_numpy(),
                          pd.to_datetime(ms).to_numpy(), side="right") - 1
    idx = np.clip(idx, 0, len(sch) - 1)
    if market is None:
        return pd.Series(sch["KOSPI"].to_numpy()[idx], index=ms.index)
    mk = pd.Series(market).astype(str).str.upper()
    out = np.where(mk.str.contains("KOSDAQ").to_numpy(), sch["KOSDAQ"].to_numpy()[idx],
                   sch["KOSPI"].to_numpy()[idx])
    return pd.Series(out, index=ms.index)


def transaction_cost(weights_prev: pd.Series, weights_new: pd.Series, month,
                     market: Optional[pd.Series] = None, commission_bps: float = 1.5,
                     slippage_bps: float = 15.0, adv: Optional[pd.Series] = None,
                     portfolio_krw: float = 1e9, impact_coef: float = 10.0,
                     multiplier: float = 1.0) -> float:
    """한 리밸런싱의 총비용(포트폴리오 대비 비율). 세금은 매도에만 매긴다."""
    idx = weights_prev.index.union(weights_new.index)
    wp = weights_prev.reindex(idx).fillna(0.0)
    wn = weights_new.reindex(idx).fillna(0.0)
    d = wn - wp
    buy, sell = d.clip(lower=0), (-d).clip(lower=0)
    turn = float(buy.sum() + sell.sum())
    mk = market.reindex(idx) if market is not None else None
    tax = sell_tax_bps(pd.Series([month] * len(idx), index=idx), mk) / 1e4
    cost = (commission_bps / 1e4) * turn + float((sell * tax).sum()) + (slippage_bps / 1e4) * turn
    if adv is not None:
        a = pd.to_numeric(adv.reindex(idx), errors="coerce").replace(0, np.nan)
        participation = ((buy + sell) * portfolio_krw / a).clip(upper=1.0).fillna(0.0)
        cost += float(((impact_coef / 1e4) * np.sqrt(participation) * (buy + sell)).sum())
    return float(cost * multiplier)


def cost_table(turnover: pd.Series, gross: pd.Series, costs: pd.Series) -> pd.DataFrame:
    return pd.DataFrame([{"월평균 회전율": float(turnover.mean()),
                          "연환산 회전율": float(turnover.mean() * 12),
                          "월평균 비용(bp)": float(costs.mean() * 1e4),
                          "연환산 비용(%)": float(costs.mean() * 12 * 100),
                          "총수익(연,%)": float(gross.mean() * 12 * 100),
                          "순수익(연,%)": float((gross - costs).mean() * 12 * 100)}])


# ==========================================================================================
#  backtest/statistics.py
# ==========================================================================================
"""성과·검정 통계.   §60 · §61 · §62 · §78"""




def newey_west_t(x, lags: Optional[int] = None) -> Tuple[float, float, float]:
    """(mean, se_nw, t). 자기상관·이분산에 강건한 표준오차."""
    a = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(a)
    if n < 6:
        return (float(a.mean()) if n else np.nan, np.nan, np.nan)
    mu = float(a.mean())
    e = a - mu
    L = int(lags if lags is not None else max(1, int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))))
    s = float(e @ e) / n
    for k in range(1, min(L, n - 1) + 1):
        s += 2.0 * (1.0 - k / (L + 1.0)) * (float(e[k:] @ e[:-k]) / n)
    se = float(np.sqrt(max(s, 0.0) / n))
    return mu, se, (mu / se if se > 0 else np.nan)


def t_to_p(t: float, dof: int = 200) -> float:
    if t is None or not np.isfinite(t):
        return np.nan
    from scipy import stats
    return float(2 * (1 - stats.t.cdf(abs(t), dof)))


def perf_table(ret, freq: int = 12, label: str = "") -> pd.DataFrame:
    """§60 필수 성과표."""
    r = pd.Series(ret).dropna().astype(float)
    if not len(r):
        return pd.DataFrame([{"전략": label, "관측월": 0}])
    cum = float((1 + r).prod())
    yrs = len(r) / freq
    cagr = (cum ** (1 / yrs) - 1) if (yrs > 0 and cum > 0) else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(freq))
    curve = (1 + r).cumprod()
    mdd = float((curve / curve.cummax() - 1).min())
    mu, se, t = newey_west_t(r.to_numpy())
    return pd.DataFrame([{
        "전략": label, "관측월": len(r), "CAGR": cagr, "연환산수익": float(r.mean() * freq),
        "변동성": vol, "Sharpe": (float(r.mean() * freq) / vol) if vol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if (mdd < 0 and pd.notna(cagr)) else np.nan,
        "적중률": float((r > 0).mean()), "월평균": mu, "NW_SE": se, "NW_t": t,
        "p(NW)": t_to_p(t, max(len(r) - 1, 5)),
        "CI95_low": (mu - 1.96 * se) if pd.notna(se) else np.nan,
        "CI95_high": (mu + 1.96 * se) if pd.notna(se) else np.nan}])


def information_coefficient(F: pd.DataFrame, score_col: str, ret_col: str,
                            month_col: str = "month", min_n: int = 10
                            ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§61 — 월별 Spearman IC 와 그 시계열 검정. (요약, 월별 시계열)."""
    d = F[[month_col, score_col, ret_col]].dropna()
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    rk = d.groupby(month_col, observed=True)[[score_col, ret_col]].rank()
    rk[month_col] = d[month_col].to_numpy()
    n = rk.groupby(month_col, observed=True)[score_col].transform("count")
    rk = rk[n >= min_n]
    if not len(rk):
        return pd.DataFrame(), pd.DataFrame()
    # 순위 상관 = 순위변수의 피어슨 상관 (그룹 루프 없이 벡터화)
    # 순위 상관 = 순위변수의 피어슨 상관. groupby.apply 를 피하고 완전 벡터화한다
    # (pandas 버전마다 include_groups 시그니처가 달라 apply 는 이식성이 나쁘다).
    a = rk[score_col].to_numpy(dtype=float)
    b = rk[ret_col].to_numpy(dtype=float)
    key = rk[month_col]
    df = pd.DataFrame({"m": key.to_numpy(), "a": a, "b": b,
                       "ab": a * b, "a2": a * a, "b2": b * b})
    G = df.groupby("m", observed=True).agg(n=("a", "size"), sa=("a", "sum"), sb=("b", "sum"),
                                            sab=("ab", "sum"), sa2=("a2", "sum"),
                                            sb2=("b2", "sum")).reset_index()
    cov = G["sab"] - G["sa"] * G["sb"] / G["n"]
    va = G["sa2"] - G["sa"] ** 2 / G["n"]
    vb = G["sb2"] - G["sb"] ** 2 / G["n"]
    den = np.sqrt(va.clip(lower=0) * vb.clip(lower=0))
    ic = pd.DataFrame({month_col: G["m"],
                       "IC": np.where((G["n"] > 2) & (den > 0), cov / den.replace(0, np.nan),
                                      np.nan)})
    v = ic["IC"].dropna().to_numpy()
    mu, se, t = newey_west_t(v)
    summ = pd.DataFrame([{"팩터": score_col, "월수": len(v), "평균IC": mu, "IC_SE": se, "IC_t": t,
                          "p(IC)": t_to_p(t, max(len(v) - 1, 5)),
                          "IC>0 비율": float((v > 0).mean()) if len(v) else np.nan,
                          "IR": (float(np.mean(v) / np.std(v, ddof=1))
                                 if len(v) > 1 and np.std(v, ddof=1) > 0 else np.nan)}])
    return summ, ic


def quantile_returns(F: pd.DataFrame, score_col: str, ret_col: str, q: int = 5,
                     month_col: str = "month", weight: str = "equal",
                     min_n: int = 20) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§55 분위 포트폴리오 월수익 + monotonicity 표."""
    cols = [month_col, "stock_code", score_col, ret_col]
    d = F[[c for c in cols if c in F.columns]].dropna().copy()
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    n = d.groupby(month_col, observed=True)[score_col].transform("count")
    d = d[n >= max(min_n, q * 2)]
    if not len(d):
        return pd.DataFrame(), pd.DataFrame()
    d["q"] = (d.groupby(month_col, observed=True)[score_col]
              .transform(lambda s: pd.qcut(s.rank(method="first"), q, labels=False,
                                           duplicates="drop") + 1))
    d = d.dropna(subset=["q"])
    if weight == "equal":
        d["w"] = 1.0
    else:
        d["w"] = d.groupby([month_col, "q"], observed=True)[score_col].rank(method="average")
    d["w"] = d["w"] / d.groupby([month_col, "q"], observed=True)["w"].transform("sum")
    QR = (d.assign(_wr=d["w"] * d[ret_col])
          .groupby([month_col, "q"], as_index=False, observed=True)
          .agg(ret=("_wr", "sum"), n=(ret_col, "size")))
    piv = QR.pivot(index=month_col, columns="q", values="ret")
    piv.columns = [f"Q{int(c)}" for c in piv.columns]
    piv = piv.join(d.groupby(month_col, observed=True)[ret_col].mean().rename("Universe"))
    hi = f"Q{q}"
    if hi in piv.columns:
        piv[f"{hi}-Universe"] = piv[hi] - piv["Universe"]
        if "Q1" in piv.columns:
            piv[f"{hi}-Q1"] = piv[hi] - piv["Q1"]
    tab = pd.concat([perf_table(piv[c], label=c) for c in piv.columns], ignore_index=True)
    return piv, tab


def fama_macbeth(F: pd.DataFrame, y: str, xs: Sequence[str], month_col: str = "month",
                 sector_col: Optional[str] = "sector", min_n: int = 30) -> pd.DataFrame:
    """§62 — 월별 횡단면 회귀 계수의 시계열 평균과 NW t."""
    xs = [c for c in xs if c in F.columns]
    if not xs or y not in F.columns:
        return pd.DataFrame()
    use = [month_col, y] + xs + ([sector_col] if sector_col and sector_col in F.columns else [])
    d = F[use].dropna(subset=[y] + xs)
    coefs: List[dict] = []
    for mth, g in d.groupby(month_col, observed=True):
        if len(g) < min_n:
            continue
        X, names = [np.ones((len(g), 1))], ["const"]
        for c in xs:
            v = pd.to_numeric(g[c], errors="coerce").to_numpy(dtype=float)
            sd = np.nanstd(v)
            v = (v - np.nanmean(v)) / (sd + 1e-12)
            X.append(np.nan_to_num(v).reshape(-1, 1))
            names.append(c)
        if sector_col and sector_col in g.columns:
            sec = pd.Categorical(g[sector_col].astype(str))
            if len(sec.categories) > 1:
                D = np.zeros((len(g), len(sec.categories) - 1))
                for j in range(1, len(sec.categories)):
                    D[:, j - 1] = (sec.codes == j).astype(float)
                X.append(D)
                names += [f"sec_{i}" for i in range(D.shape[1])]
        try:
            beta, *_ = np.linalg.lstsq(np.hstack(X), g[y].to_numpy(dtype=float), rcond=None)
        except Exception:                                      # noqa: BLE001
            continue
        coefs.append({"month": mth, **{n: b for n, b in zip(names, beta)
                                       if not n.startswith("sec_")}})
    if not coefs:
        return pd.DataFrame()
    C = pd.DataFrame(coefs)
    rows = []
    for c in [x for x in C.columns if x != "month"]:
        mu, se, t = newey_west_t(C[c].to_numpy())
        rows.append({"변수": c, "월수": int(C[c].notna().sum()), "평균계수": mu,
                     "NW_SE": se, "NW_t": t, "p": t_to_p(t, max(len(C) - 1, 5))})
    return pd.DataFrame(rows)


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> pd.DataFrame:
    """§78 — Benjamini-Hochberg. 최고 t 하나만 보고 '성공' 판정하지 않기 위함."""
    p = np.asarray(list(pvals), dtype=float)
    ok = np.isfinite(p)
    m = int(ok.sum())
    crit = np.full(len(p), np.nan)
    rej = np.zeros(len(p), dtype=bool)
    if m:
        order = np.argsort(np.where(ok, p, np.inf))
        ranks = np.arange(1, len(p) + 1)
        crit_sorted = q * ranks / m
        below = p[order][:m] <= crit_sorted[:m]
        kmax = (np.where(below)[0].max() + 1) if below.any() else 0
        rej[order[:kmax]] = True
        crit[order] = crit_sorted
    return pd.DataFrame({"p": p, "BH_임계값": crit, "기각(FDR)": rej})


# ==========================================================================================
#  backtest/portfolio.py
# ==========================================================================================
"""포트폴리오 구성과 백테스트 실행.   §53 · §55 · §56 · §57 · §59

  · 월말까지 공개된 데이터로 신호 → 다음 거래일부터 매매(T+1).
    구현상 신호월 t 의 성과는 t+1 월 수익률과 매칭한다. 같은 달 수익률을 절대 쓰지 않는다.
  · 미래수익률 진입점은 attach_forward_return() 하나뿐이고 잠금이 걸려 있다(§1.1).
"""




def attach_forward_return(F: pd.DataFrame, market: pd.DataFrame, firm_col: str = "stock_code",
                          month_col: str = "month", ret_col: str = "ret",
                          horizon: int = 1) -> pd.DataFrame:
    """t 월 신호 ↔ t+horizon 월 수익률. **미래수익률 진입점 — 잠금 통과 필수.**"""
    CFG.assert_returns_unlocked(f"forward_return(h={horizon})")
    mk = market[[firm_col, month_col, ret_col]].dropna(subset=[month_col]).copy()
    mk["_sig_month"] = ((pd.to_datetime(mk[month_col]) - pd.DateOffset(months=horizon))
                        + pd.offsets.MonthEnd(0))
    fwd = mk.rename(columns={ret_col: f"fwd_ret_{horizon}m"})[
        [firm_col, "_sig_month", f"fwd_ret_{horizon}m"]]
    out = F.merge(fwd, left_on=[firm_col, month_col], right_on=[firm_col, "_sig_month"],
                  how="left").drop(columns=["_sig_month"])
    return out


def build_portfolio(F: pd.DataFrame, score_col: str, ret_col: str, top_pct: float = 0.20,
                    weighting: str = "equal", month_col: str = "month",
                    firm_col: str = "stock_code", min_holdings: int = 10,
                    max_weight: float = 0.10, cost_multiplier: float = 1.0,
                    commission_bps: float = 1.5, slippage_bps: float = 15.0,
                    apply_costs: bool = True) -> Dict[str, pd.DataFrame]:
    """상위 top_pct Long-only 포트폴리오. 반환: returns / holdings / summary."""
    base = [month_col, firm_col, score_col, ret_col]
    extra = [c for c in ("market", "turnover_value", "mcap", "sector") if c in F.columns]
    d = F[[c for c in base if c in F.columns] + extra].dropna(subset=[score_col, ret_col])
    empty = {"returns": pd.DataFrame(), "holdings": pd.DataFrame(), "summary": pd.DataFrame()}
    if not len(d):
        return empty
    d = d.sort_values([month_col, score_col], ascending=[True, False], kind="stable").copy()
    d["rk"] = d.groupby(month_col, observed=True)[score_col].rank(ascending=False, method="first")
    d["n_month"] = d.groupby(month_col, observed=True)[score_col].transform("count")
    H = d[(d["rk"] <= np.maximum(np.floor(d["n_month"] * top_pct), min_holdings)) &
          (d["n_month"] >= min_holdings)].copy()
    if not len(H):
        return empty
    if weighting == "equal":
        H["w_raw"] = 1.0
    elif weighting == "rank":
        H["w_raw"] = H.groupby(month_col, observed=True)["rk"].transform("max") - H["rk"] + 1.0
    elif weighting == "cap":
        H["w_raw"] = pd.to_numeric(H.get("mcap"), errors="coerce").fillna(1.0)
    else:
        raise ValueError(f"알 수 없는 가중방식: {weighting}")
    H["w"] = H["w_raw"] / H.groupby(month_col, observed=True)["w_raw"].transform("sum")
    H["w"] = H["w"].clip(upper=max_weight)
    H["w"] = H["w"] / H.groupby(month_col, observed=True)["w"].transform("sum")

    gross = (H.assign(_x=H["w"] * H[ret_col]).groupby(month_col, as_index=False, observed=True)
             .agg(gross_ret=("_x", "sum"), holdings=("w", "size"), max_w=("w", "max")))
    rows: List[dict] = []
    prev = pd.Series(dtype=float)
    for mth, g in H.groupby(month_col, sort=True, observed=True):
        cur = g.set_index(firm_col)["w"]
        idx = cur.index.union(prev.index)
        turn = float((cur.reindex(idx).fillna(0.0) - prev.reindex(idx).fillna(0.0)).abs().sum())
        c = (transaction_cost(prev, cur, mth,
                              market=g.set_index(firm_col)["market"] if "market" in g else None,
                              commission_bps=commission_bps, slippage_bps=slippage_bps,
                              adv=g.set_index(firm_col)["turnover_value"]
                              if "turnover_value" in g else None,
                              multiplier=cost_multiplier) if apply_costs else 0.0)
        rows.append({month_col: mth, "turnover": turn, "cost": c})
        prev = cur
    R = gross.merge(pd.DataFrame(rows), on=month_col, how="left")
    R["cost"] = R["cost"].fillna(0.0)
    R["net_ret"] = R["gross_ret"] - R["cost"]
    summ = pd.concat([perf_table(R["gross_ret"], label=f"{score_col} gross"),
                      perf_table(R["net_ret"], label=f"{score_col} net")], ignore_index=True)
    summ["평균보유종목"] = float(R["holdings"].mean())
    summ["중앙보유종목"] = float(R["holdings"].median())
    summ["월평균회전율"] = float(R["turnover"].mean())
    return {"returns": R, "holdings": H, "summary": summ}


def benchmark_returns(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.Series:
    """유니버스 동일가중 벤치마크 — Q5-Universe 초과수익의 기준."""
    return F.dropna(subset=[ret_col]).groupby(month_col, observed=True)[ret_col].mean()


def run_backtest(F: pd.DataFrame, market: pd.DataFrame, score_col: str, top_pct: float = 0.20,
                 weighting: str = "equal", cost_multiplier: float = 1.0, horizon: int = 1,
                 quantiles: int = 5, min_holdings: int = 10) -> Dict[str, object]:
    """PRIMARY 백테스트 한 번의 전체 실행."""
    Fx = attach_forward_return(F, market, horizon=horizon)
    rc = f"fwd_ret_{horizon}m"
    pf = build_portfolio(Fx, score_col, rc, top_pct=top_pct, weighting=weighting,
                         cost_multiplier=cost_multiplier, min_holdings=min_holdings)
    qr, qt = quantile_returns(Fx, score_col, rc, q=quantiles)
    bm = benchmark_returns(Fx, rc)
    excess = pd.DataFrame()
    if len(pf["returns"]):
        R = pf["returns"].set_index("month")
        excess = pd.DataFrame({"gross_excess": R["gross_ret"] - bm.reindex(R.index),
                               "net_excess": R["net_ret"] - bm.reindex(R.index)}).dropna()
    return {"returns": pf["returns"], "holdings": pf["holdings"], "summary": pf["summary"],
            "quantile_returns": qr, "quantile_table": qt, "benchmark": bm,
            "excess": excess, "scored": Fx, "ret_col": rc}


# ==========================================================================================
#  audit/prereg.py
# ==========================================================================================
"""사전등록 동결 · 시험 장부 · FUTURE_RETURN_LOCK 해제.   §1.1 · §77 · §78

동결이란 무엇인가:
  ① 4개 config YAML + audit/trial_ledger.json 의 내용을 확정하고
  ② 그 SHA256 을 audit/prereg_hash.txt 에 기록하는 것.
그 이후에만 FUTURE_RETURN_LOCK 이 풀린다. 동결 이후 파일을 고치면 해시가 어긋나
잠금이 자동으로 다시 걸린다 — 사후에 정의를 바꾸는 것을 구조로 막는다.

★ 동결 시점에 넣는 데이터 기반 값(MATURITY_EMBARGO, USABLE_START_DATE)은
  반드시 '수익률을 보기 전' 감사 결과로만 정한다(§23 §48).
"""



# §77 — 시작 전 모두 등록해야 하는 알파 후보 전체 장부
TRIAL_CANDIDATES: List[Dict[str, Any]] = [
    {"id": "D1", "name": "Demand Flow", "column": "D1_DS_YOY", "family": "demand",
     "spec": "§24", "hypothesis": "역량정합 신규 정부수요의 YoY 증가가 향후 수익률을 예측한다"},
    {"id": "D2", "name": "Forward Pipeline", "column": "D2_PIPELINE_YOY", "family": "demand",
     "spec": "§24", "hypothesis": "이미 공개되었으나 미집행인 파이프라인 잔량 증가가 선행신호다"},
    {"id": "W1", "name": "Award / MCap", "column": "WIN_MCAP", "family": "win",
     "spec": "§26", "hypothesis": "시총 대비 수주 규모가 클수록 향후 수익률이 높다"},
    {"id": "W2", "name": "Award / Sales", "column": "WIN_SALES", "family": "win",
     "spec": "§26", "hypothesis": "PIT 매출 대비 수주 규모가 클수록 향후 수익률이 높다"},
    {"id": "W3", "name": "Win Acceleration", "column": "win_accel_log", "family": "win",
     "spec": "§27", "hypothesis": "수주의 가속(TTM 로그차분)이 향후 수익률을 예측한다"},
    {"id": "A1", "name": "Demand-Win Alignment", "column": "G2B_DWA", "family": "primary",
     "spec": "§28", "hypothesis": "수요이동과 수주전환이 동시에 강한 기업이 초과수익을 낸다",
     "is_primary": True},
    {"id": "B1", "name": "New Agency Breadth", "column": "new_agency_count", "family": "breadth",
     "spec": "§30", "hypothesis": "신규 발주기관 확대가 고객저변 확장을 뜻한다"},
    {"id": "B2", "name": "New Category Entry", "column": "new_category_award_share",
     "family": "breadth", "spec": "§31", "hypothesis": "신규 사업영역 진입이 성장을 예고한다"},
    {"id": "B3", "name": "Repeat Win", "column": "REPEAT_WIN_RATE", "family": "breadth",
     "spec": "§32", "hypothesis": "반복수주는 경쟁력일 수도, 의존성일 수도 있다 — 부호 미확정"},
    {"id": "R1", "name": "Agency Concentration", "column": "AGENCY_HHI", "family": "risk",
     "spec": "§33", "hypothesis": "발주기관 집중은 위험이다 — 부호 미확정"},
    {"id": "R2", "name": "Category Concentration", "column": "CATEGORY_HHI", "family": "risk",
     "spec": "§34", "hypothesis": "품목 집중은 위험이다 — 부호 미확정"},
    {"id": "R3", "name": "Mega Deal", "column": "TOP1_SHARE", "family": "risk",
     "spec": "§41", "hypothesis": "단일 초대형 계약 의존은 위험이다 — 부호 미확정"},
    {"id": "R4", "name": "Contract Revision", "column": "CONTRACT_REVISION_RATIO",
     "family": "risk", "spec": "§40", "hypothesis": "계약 감액·취소는 악재다 — 부호 미확정"},
    {"id": "C1", "name": "Competition", "column": "resid_bidder_count", "family": "diagnostic",
     "spec": "§35 §76", "hypothesis": "경쟁강도 — 부호가 조달방식마다 다르므로 PRIMARY 에 넣지 않는다"},
]


def build_trial_ledger(extra: Optional[List[dict]] = None) -> dict:
    """§77 — 성과를 보기 전에 후보를 전부 등록한다. 나중에 추가하려면 여기 먼저 등록해야 한다."""
    return {
        "version": "v1",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "rule": ("성과를 본 뒤 후보를 추가하거나 정의를 바꾸지 않는다. "
                 "추가 후보가 생기면 성과를 보기 전에 이 장부에 등록한다(§77)."),
        "primary": "A1",
        "multiple_testing": {"method": "BH/FDR", "q": 0.10,
                             "scope": "primary 를 제외한 secondary family 전체(§78)"},
        "candidates": TRIAL_CANDIDATES + list(extra or []),
        "n_candidates": len(TRIAL_CANDIDATES) + len(extra or []),
    }


def _patch_yaml_scalar(path: str, key: str, value: Any) -> bool:
    """'key: null' 한 줄을 실측값으로 채운다. YAML 재작성(주석 유실)을 피하려고 줄 단위로 바꾼다."""
    if not os.path.exists(path):
        return False
    src = open(path, encoding="utf-8").read()
    out, done = [], False
    for ln in src.split("\n"):
        stripped = ln.strip()
        if not done and stripped.startswith(key + ":"):
            indent = ln[:len(ln) - len(ln.lstrip())]
            rest = ln.split("#", 1)
            comment = ("  #" + rest[1]) if len(rest) > 1 else ""
            v = "null" if value is None else (f'"{value}"' if isinstance(value, str) else str(value))
            out.append(f"{indent}{key}: {v}{comment}")
            done = True
        else:
            out.append(ln)
    if done:
        atomic_write_text(path, "\n".join(out))
    return done


def freeze(maturity_embargo_days: Optional[int] = None,
           usable_start_date: Optional[str] = None,
           extra_candidates: Optional[List[dict]] = None,
           notes: str = "") -> dict:
    """사전등록 동결. 반환은 기록된 매니페스트."""
    CFG.ensure_dirs()
    materialize_templates()
    missing = [f for f in CFG.PREREG_FILES if not os.path.exists(os.path.join(CFG.CONFIG_DIR, f))]
    if missing:
        raise FileNotFoundError(f"사전등록 파일이 없습니다: {missing} — config/ 를 먼저 작성하십시오.")

    if maturity_embargo_days is not None:
        ok = _patch_yaml_scalar(os.path.join(CFG.CONFIG_DIR, "factor_preregistration.yaml"),
                                "maturity_embargo_days", int(maturity_embargo_days))
        LOG.info(f"MATURITY_EMBARGO = {maturity_embargo_days}일 동결 "
                 f"(실측 분포 기반, 수익률 미열람 상태) {'✔' if ok else '— 키를 찾지 못함'}")
    if usable_start_date is not None:
        ok = _patch_yaml_scalar(os.path.join(CFG.CONFIG_DIR, "universe_definition.yaml"),
                                "usable_start_date", str(usable_start_date))
        LOG.info(f"USABLE_START_DATE = {usable_start_date} 동결 "
                 f"(데이터 커버리지만 보고 결정) {'✔' if ok else '— 키를 찾지 못함'}")

    write_json(CFG.TRIAL_LEDGER, build_trial_ledger(extra_candidates))
    man = CFG.prereg_manifest()
    rec = {"frozen_at": _dt.datetime.now().isoformat(timespec="seconds"),
           "files": man, "run_stamp": CFG.run_stamp(), "notes": notes,
           "declaration": ("이 시점 이후에만 미래수익률을 열람한다. 이 파일들을 수정하면 "
                           "해시가 어긋나 FUTURE_RETURN_LOCK 이 자동으로 다시 걸린다.")}
    write_json(CFG.PREREG_HASH_FILE, rec)
    st = CFG.prereg_status()
    if not st["frozen"]:
        raise RuntimeError(f"동결 실패: {st['reason']}")
    LOG.ok("사전등록 동결 완료 — FUTURE_RETURN_LOCK = FALSE")
    for k, v in man.items():
        LOG.info(f"  {k}  sha256={v[:16]}…")
    return rec


def verify() -> pd.DataFrame:
    st = CFG.prereg_status()
    man = st["manifest"]
    rec = (st["recorded"] or {}).get("files", {})
    rows = [{"파일": k, "현재 sha256": v[:16] + "…",
             "동결 sha256": (rec.get(k, "—")[:16] + "…") if rec.get(k) else "—",
             "일치": "✔" if rec.get(k) == v else "✖"} for k, v in sorted(man.items())]
    rows.append({"파일": "FUTURE_RETURN_LOCK", "현재 sha256": "",
                 "동결 sha256": "", "일치": "FALSE(해제)" if st["frozen"] else "TRUE(잠김)"})
    return pd.DataFrame(rows)


def ledger_table() -> pd.DataFrame:
    d = read_json(CFG.TRIAL_LEDGER, {}) or {}
    c = d.get("candidates", [])
    if not c:
        return pd.DataFrame()
    return pd.DataFrame([{"ID": x["id"], "이름": x["name"], "컬럼": x["column"],
                          "계열": x["family"], "명세": x["spec"],
                          "PRIMARY": "★" if x.get("is_primary") else "",
                          "가설": x["hypothesis"][:52]} for x in c])

# ══════════════════════════════════════════════════════════════════════════════
#  사전등록 YAML 템플릿 (단일파일 배포용 내장본)
#  config/ 에 파일이 없으면 이 템플릿을 '쓰기'만 한다. 이미 있으면 절대 덮어쓰지 않는다
#  — 사용자가 손으로 고친 사전등록을 코드가 되돌리면 §1.1 이 무의미해지기 때문이다.
# ══════════════════════════════════════════════════════════════════════════════
PREREG_TEMPLATES = {
    "factor_preregistration.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  G2B-DEMAND-GRAPH-V1 — 팩터 사전등록 (§1.1)
#  이 파일이 동결(SHA256 기록)되기 전에는 FUTURE_RETURN_LOCK 이 풀리지 않는다.
#  동결 이후 이 파일을 고치면 해시가 어긋나 잠금이 자동으로 다시 걸린다.
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
frozen_by: "scripts/09_freeze_preregistration.py"

primary_factor:
  name: G2B_DWA
  formula: "sqrt(P_D * P_W)"
  description: "Demand-Win Alignment — 역량정합 정부수요 이동(D)과 실제 수주전환(W)의 기하평균"
  neutralization: sector_size          # §44 PRIMARY 는 sector + log(mcap) 중립
  min_cross_section_n: 20              # 월별 스코어 기업이 이보다 적으면 그 달은 NaN
  # ── D 축 (정부수요 이동) ──────────────────────────────────────────────────
  demand_axis:
    column: D1_DS_YOY
    formula: "log1p(EligibleDemandFlow_3M_t) - log1p(EligibleDemandFlow_3M_{t-12})"
    source_stages: [PLAN, PRESPEC, BID]     # §20 winner 를 보기 전 단계만
    leave_one_firm_out: true                # §45 (이미 알려진 자사 낙찰건 제외)
    stage_probability_weighted: true        # §22
  # ── W 축 (실제 수주 전환) ─────────────────────────────────────────────────
  win_axis:
    column: win_accel_log
    formula: "log1p(TTM award) - log1p(TTM award 12M ago)"
    alternative_not_used: win_accel_rate    # §27 둘 다 산출하되 PRIMARY 는 하나만 동결
    amount_basis: attributed_amount         # §16 컨소시엄 지분 반영, 지분불명은 제외

capability:                                  # §17
  lookback_months: 36
  halflife_months: 18
  source_stages: [AWARD]
  normalization: "share of firm's decayed award across categories"
  warmup_required_months: 36                 # §19

stage_probability:                           # §22 §23
  method: walk_forward_hierarchical_shrinkage
  hierarchy: [category, broad_category, proc_type, global]
  shrink_k: 25.0
  maturity_embargo_days: 427  # ← 09 스크립트가 실측 분포 p90 으로 채우고 동결
  training_rule: "label_available_at <= t 인 라벨만 사용 (training_end < t)"

secondary_factors:                           # §78 PRIMARY 는 하나, 나머지는 전부 Secondary
  - D1_DS_YOY
  - D2_PIPELINE_YOY
  - WIN_MCAP
  - WIN_SALES
  - win_accel_rate
  - new_agency_count
  - new_category_award_share
  - REPEAT_WIN_RATE
  - AGENCY_HHI
  - CATEGORY_HHI
  - TOP1_SHARE
  - CONTRACT_REVISION_RATIO
  - resid_bidder_count
multiple_testing: "BH/FDR q=0.10 across secondary family"

risk_track:                                  # §42 §43 — PRIMARY 와 섞지 않는다
  name: PROC_RISK
  components: [AGENCY_HHI, CATEGORY_HHI, TOP1_SHARE]
  combination: "mean of monthly cross-sectional percentiles"
  hard_exclusion: false
  mixed_with_primary: false

nested_comparison:                           # §84 §99 — 이 표가 연구의 최종 판정 근거
  - Award_Amount_only
  - Award_over_MCap
  - Demand_Shift_only
  - Win_Acceleration_only
  - Demand_Win_Alignment
decision_rule: "Full 모델이 단순모델을 명백히 이기지 못하면 단순모델을 채택한다(§99)."
""",
    "universe_definition.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  투자 유니버스 정의 (§49 · §50 · §51)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
markets: [KOSPI, KOSDAQ]
security_type: 보통주
exclude:
  - SPAC
  - 우선주
  - ETF
  - ETN
  - REITs            # §49 별도 취급
point_in_time: true
survivorship_bias_free: true
delisted_included: true
delisting_return: -1.0                # 정리매매 정보가 없으면 -100% (누락 처리 금지)
admin_issue_rule: "관리·정지 여부는 당시 정보 기준으로만 판정"

liquidity:
  min_20d_turnover_value_krw: 300000000
  applied_at: signal_date

procurement_observability:            # §50 — 조달기업만으로 universe 를 사후 정의하지 않는다
  report_both: true
  definitions:
    all_tradable: "PIT 상장 보통주 전체"
    procurement_observable: "t 시점까지 G2B 낙찰이 1건 이상 '관측된' 기업"
  forbidden: "현재 나라장터 등록업체 명단으로 과거 universe 를 만드는 것"

usable_start_date: "2018-01-31"  # ← 01/03 감사 결과로 09 스크립트가 채우고 동결
usable_end_date: "2026-07-31"
warmup_months: 36

coverage_gate:                        # §51
  median_scored_firms_min: 100
  p10_scored_firms_min: 60
  median_holdings_min: 20
  fail_label: SAMPLE_COLLAPSE

entity_mapping_gate:                  # §52
  primary_allowed_types: [EXACT_ID, VERIFIED_MANUAL]
  forbidden: "기업명 fuzzy matching 만으로 자동 확정"
  report_shares_by: amount
""",
    "pit_policy.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  Point-in-Time 정책 (§6 · §7 · §8 · §11 · §53 · §57 · §58)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
timestamps: [event_time, source_published_at, available_at]
revision_fields: [valid_from, valid_to, revision_no]

publication_lag_days:                 # available_at = source_published_at + lag
  PLAN: 1
  PRESPEC: 1
  BID: 1
  AWARD: 1
  CONTRACT: 2
  DART: 0
imputed_published_extra_lag_days: 1   # 공개시각을 모르면 보수적으로 하루 더

field_classes:                        # §6.1
  A: "당시 공개시각·값이 확정 복원 → 사용 허용"
  B: "변경이력으로 각 리비전 유효기간 복원 후 사용"
  C: "과거 최종값만 반환·변경과정 불명 → 역사적 백테스트 사용 금지 (PIT_UNCERTIFIED)"
unknown_field_default: C              # 모르면 쓰지 않는다

double_counting:                      # §8 §11
  rule: "opportunity 별 '가장 진척된 단계' 계단함수의 증분만 신규수요로 센다"
  guarantee: "증분 총합 == 최종 알려진 금액 (구조적 보존)"
  cancel_rebid_handling: "금액이 아니라 상태변수로 보관"

signal_timing:                        # §53
  rebalance: MONTHLY
  signal_cutoff: "월말까지 available_at 이 도달한 정보만"
  execution: "T+1 (장마감 전 공개 여부가 불확실하면 보수적으로 T+1)"

price_pit:                            # §57
  forbidden:
    - "현재 수정주가 파일에서 상폐종목 삭제"
    - "현재 상장주식수 과거 소급"
    - "현재 섹터분류 과거 소급"
  total_return: true
  include_delisting_loss: true

financial_pit:                        # §58
  rule: "filing_timestamp <= signal_timestamp 인 최신 재무제표만"
  filing_timestamp_source: "rcept_no 앞 8자리 (접수일자)"
  fallback_if_missing: "결산일 + 90일 (보수적)"

consortium:                           # §16
  primary_rule: "지분 있으면 지분비율, 없으면 UNKNOWN_SHARE_CONSORTIUM 으로 금액 팩터 제외"
  sensitivity_modes: [equal_split, winner_only, full_allocation]

linkage:                              # §10
  priority: [OFFICIAL_ID, PROCESS_LEDGER, DETERMINISTIC_ATTR, TEXT_SIMILARITY]
  primary_enabled: [OFFICIAL_ID, PROCESS_LEDGER]
  record_fields: [link_method, link_score, link_known_at]
  rule: "애매한 연결을 억지로 확정하지 않는다. 연결 실패 != 사건 실패(§2.F)"
""",
    "backtest_policy.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  백테스트 정책 (§53 ~ §62, §79)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
rebalance: MONTHLY
execution_lag: "T+1"
portfolio:
  primary: "G2B_DWA 상위 20% (Long-only)"
  quantiles: 5
  report: [Q1, Q2, Q3, Q4, Q5, "Q5-Universe", "Q5-Q1"]
  weighting_primary: equal_weight       # §56
  weighting_secondary: rank_weight
  weighting_diagnostic: cap_weight
  max_position_weight: 0.10
  min_holdings: 10

costs:                                  # §59 고정 0bp 백테스트를 최종성과로 쓰지 않는다
  commission_bps: 1.5
  slippage_bps: 15.0
  market_impact_model: "sqrt(participation) * spread_proxy"
  sell_tax_schedule:                    # 당시 제도 기준 (매도 시 거래세, KOSPI 는 농특세 포함)
    - {from: "2015-01-01", kospi_bps: 30.0, kosdaq_bps: 30.0}
    - {from: "2019-06-03", kospi_bps: 25.0, kosdaq_bps: 25.0}
    - {from: "2021-01-01", kospi_bps: 23.0, kosdaq_bps: 23.0}
    - {from: "2023-01-01", kospi_bps: 20.0, kosdaq_bps: 20.0}
    - {from: "2025-01-01", kospi_bps: 18.0, kosdaq_bps: 18.0}
  stress_multipliers: [1.0, 2.0, 3.0]

statistics:                             # §60 §61 §62
  report: [CAGR, ann_return, volatility, Sharpe, MDD, Calmar, turnover,
           avg_holdings, median_holdings, hit_ratio]
  newey_west_lags: 6
  ic: [spearman, rank]
  fama_macbeth_controls: [log_mcap, value, momentum, profitability, volatility, sector_FE]

pass_criteria:                          # §79
  DATA_PASS: ["PIT 복원 가능", "exact match 충분", "표본 붕괴 없음",
              "lifecycle 중복제거 성공", "revision 처리 성공"]
  ALPHA_PASS: {net_alpha_gt: 0.0, newey_west_t_min: 2.0, late_period_direction: positive}
  STRONG_PASS: {net_annual_excess_min: 0.03, newey_west_t_min: 2.0,
                late_period_positive: true, cost_2x_positive: true,
                loyo_mostly_positive: true, mega_deal_removed_positive: true,
                top_contributors_removed_positive: true}
  rule: "숫자를 못 넘겼다고 정의를 바꾸어 다시 탐색하지 않는다."

robustness_required:                    # §65 ~ §75
  - time_thirds
  - by_year
  - leave_one_year_out
  - leave_one_agency_out
  - leave_one_category_out
  - mega_contract_winsorize: [0.001, 0.005, 0.01]
  - drop_top_contributors: [1, 3, 5, 10]
  - by_size_bucket
  - by_market
  - by_sector
  - placebo_permutation
  - temporal_placebo
""",
}


def materialize_templates() -> list:
    """config/ 에 없는 사전등록 파일만 템플릿으로 생성한다. 반환은 생성된 파일 목록."""
    CFG.ensure_dirs()
    made = []
    for fn, body in PREREG_TEMPLATES.items():
        p = os.path.join(CFG.CONFIG_DIR, fn)
        if not os.path.exists(p):
            atomic_write_text(p, body)
            made.append(fn)
    if made:
        LOG.info(f"사전등록 템플릿 생성: {made} (기존 파일은 건드리지 않았습니다)")
    return made


# ==========================================================================================
#  audit/pit_audit.py
# ==========================================================================================
"""PIT 감사표 — reports/01_PIT_AUDIT.md 의 내용물.   §5 · §6 · §8 · §11

  · API 실측 깊이 (01 스크립트 산출물을 표로)
  · 필드 등급(CLASS A/B/C) 분포와 PIT_UNCERTIFIED 목록
  · event → published → available 지연 분포
  · 리비전 처리 / 이중계산 제거가 실제로 작동했는지 수치 증명
"""




def api_depth_table(manifests: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """§5 — API별 최초/마지막 실측일·건수·핵심필드 커버리지·수정이력·사용가능."""
    rows = []
    for svc, M in manifests.items():
        if M is None or not len(M):
            rows.append({"API": svc, "최초 실측일": "—", "마지막 실측일": "—", "건수": 0,
                         "핵심필드 커버리지": "—", "수정이력 존재": "—", "사용가능": "NO_DATA"})
            continue
        n = int(pd.to_numeric(M.get("row_count"), errors="coerce").fillna(0).sum())
        ok = M[pd.to_numeric(M.get("row_count"), errors="coerce").fillna(0) > 0]
        def _wd(x, how):
            if not len(ok):
                return "—"
            w = ok["request_params"].map(
                lambda p: (p or {}).get("inqryBgnDt") or (p or {}).get("inqryBgnDate") or
                          (p or {}).get("bidNtceBgnDt") or (p or {}).get("opengBgnDt") or
                          (p or {}).get("cntrctCnclsBgnDate") or "")
            w = w[w.astype(str).str.len() >= 6]
            return (w.min() if how == "min" else w.max()) if len(w) else "—"
        rows.append({"API": svc, "최초 실측일": _wd(ok, "min"), "마지막 실측일": _wd(ok, "max"),
                     "건수": n,
                     "핵심필드 커버리지": f"{100 * len(ok) / max(len(M), 1):.0f}% 창에서 데이터",
                     "수정이력 존재": ("Y" if M["operation"].astype(str).str.contains(
                         "Chg|Dlt", regex=True).any() else "N"),
                     "사용가능": "YES" if n > 0 else "NO_DATA"})
    return pd.DataFrame(rows)


def field_class_report(events: pd.DataFrame) -> pd.DataFrame:
    """실제 수집된 컬럼이 어떤 등급인지. 미등록 컬럼은 자동 CLASS C(=사용 금지)."""
    cols = [c for c in events.columns if not c.startswith("_")]
    return pd.DataFrame([{"컬럼": c, "PIT_CLASS": field_class(c),
                          "결측률": float(events[c].isna().mean()),
                          "사용가능": "✔" if field_class(c) in ("A", "B") else "✖ PIT_UNCERTIFIED"}
                         for c in cols]).sort_values(["PIT_CLASS", "컬럼"]).reset_index(drop=True)


def lag_report(events: pd.DataFrame) -> pd.DataFrame:
    out = []
    for st, g in events.groupby("stage", observed=True):
        try:
            out.append(audit_lag(g, st))
        except Exception as e:                                 # noqa: BLE001
            out.append(pd.DataFrame([{"table": st, "rows": len(g), "error": str(e)[:80]}]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def revision_report(events: pd.DataFrame) -> pd.DataFrame:
    out = []
    for st in ("BID", "CONTRACT"):
        g = events[events["stage"] == st]
        if len(g):
            out.append(revision_audit(g, ["service", "doc_id"], "amount", st))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def full_pit_audit(events: pd.DataFrame, manifests: Optional[Dict[str, pd.DataFrame]] = None
                   ) -> Dict[str, pd.DataFrame]:
    res = {"field_class_summary": class_table().groupby("pit_class").size()
           .rename("필드수").reset_index(),
           "field_class_detail": field_class_report(events),
           "lag": lag_report(events),
           "revision": revision_report(events)}
    # 이중계산 감사는 lifecycle 해석(opportunity_id) 이후에만 가능하다 → 05 스크립트에서 수행.
    if "opportunity_id" in events.columns:
        res["double_count"] = double_count_audit(events)
    else:
        LOG.info("opportunity_id 가 아직 없어 이중계산 감사(§11)는 05_build_lifecycle 단계에서 수행합니다.")
    if manifests:
        res["api_depth"] = api_depth_table(manifests)
    return res


# ==========================================================================================
#  audit/leakage_test.py
# ==========================================================================================
"""누수 탐지기와 카나리아 테스트.   §7 · §74 · §75 · §93

§93 이 파일의 존재 이유:
   의도적으로 미래 낙찰정보를 t 이전 데이터에 삽입한 mock dataset 을 만들고
   **누수 탐지기가 그것을 실패시키는지** 확인한다.
   이 테스트가 통과하지 못하면 본 백테스트 실행을 금지한다.

탐지기는 세 층이다.
  L1 구조 탐지  : 시각 자체가 불가능한 행 (available_at < published, 개찰 전 낙찰자 공개 등)
  L2 사용 탐지  : 시점 t 의 피처가 available_at > t 인 이벤트를 썼는가
  L3 통계 탐지  : 미래 정부수요가 과거 수익률을 설명하는가 (§75 temporal placebo)
"""




class LeakageDetected(Exception):
    """누수가 탐지되면 조용히 로그만 남기지 않고 파이프라인을 세운다."""


# ══════════════════════════════════════════════════════════════════════════════
#  L1 — 구조 탐지
# ══════════════════════════════════════════════════════════════════════════════
def scan_events(E: pd.DataFrame) -> pd.DataFrame:
    """이벤트 원장 자체의 시간 모순을 찾는다. 반환은 위반 요약표(빈 표 = 정상)."""
    v: List[dict] = []
    if E is None or not len(E):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    miss = [c for c in PIT_COLS if c not in E.columns]
    if miss:
        v.append({"검사": "PIT_COLUMNS", "위반건수": len(E), "설명": f"PIT 컬럼 누락 {miss}"})
        return pd.DataFrame(v)
    n = int((E["available_at"] < E["source_published_at"]).sum())
    if n:
        v.append({"검사": "AVAIL_BEFORE_PUBLISH", "위반건수": n,
                  "설명": "공개되기 전에 사용가능해진 행 — 정의상 불가능"})
    # 낙찰/계약은 사건이 일어나기 전에 공개될 수 없다
    late = E[E["stage"].isin(["AWARD", "CONTRACT"])]
    if len(late):
        n = int((late["source_published_at"] < late["event_time"]).sum())
        if n:
            v.append({"검사": "PUBLISH_BEFORE_EVENT", "위반건수": n,
                      "설명": "개찰/계약 이전에 결과가 공개된 행 — 미래정보 삽입의 전형적 흔적"})
    # 낙찰자가 입찰공고보다 먼저 알려진 경우
    if "opportunity_id" in E.columns:
        bid = (E[E["stage"] == "BID"].groupby("opportunity_id")["available_at"].min()
               .rename("t_bid"))
        aw = (E[E["stage"] == "AWARD"].groupby("opportunity_id")["available_at"].min()
              .rename("t_award"))
        j = pd.concat([bid, aw], axis=1).dropna()
        if len(j):
            n = int((j["t_award"] < j["t_bid"]).sum())
            if n:
                v.append({"검사": "WINNER_BEFORE_BID", "위반건수": n,
                          "설명": "입찰공고보다 먼저 알려진 낙찰자 — §7 직접 위반"})
    return pd.DataFrame(v) if v else pd.DataFrame(columns=["검사", "위반건수", "설명"])


def scan_feature_inputs(feature_cols: Sequence[str]) -> pd.DataFrame:
    """§6.1 — 팩터 입력에 CLASS C 필드가 섞였는지."""
    bad = [c for c in feature_cols if field_class(c) == "C"]
    return pd.DataFrame([{"검사": "CLASS_C_FIELD", "위반건수": len(bad),
                          "설명": f"PIT_UNCERTIFIED 필드 사용: {bad}"}] if bad else [],
                        columns=["검사", "위반건수", "설명"])


# ══════════════════════════════════════════════════════════════════════════════
#  L2 — 사용 탐지 (시점 t 피처가 t 이후 이벤트를 봤는가)
# ══════════════════════════════════════════════════════════════════════════════
def scan_panel_provenance(panel: pd.DataFrame, events: pd.DataFrame,
                          firm_col: str = "stock_code", month_col: str = "month",
                          value_col: str = "award_amt_12m", window_m: int = 12) -> pd.DataFrame:
    """기업×월 피처값이 그 시점에 알려진 이벤트만으로 설명되는지 대조 검증한다.

    award_amt_12m 을 available_at 기준으로 독립 재계산해 원 패널과 비교한다.
    원 패널이 더 크면 = 아직 몰랐던 낙찰을 이미 세고 있다 = 누수.
    """
    if panel is None or not len(panel) or events is None or not len(events):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    a = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if not len(a):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    amt = "attributed_amount" if "attributed_amount" in a.columns else "amount"
    a["m"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    obs = a.groupby([firm_col, "m"], as_index=False, observed=True)[amt].sum()
    p = panel[[firm_col, month_col, value_col]].dropna()
    if not len(p):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    chk = p.merge(obs.rename(columns={"m": month_col}), on=[firm_col, month_col], how="left")
    ref = (obs.sort_values("m").set_index("m").groupby(firm_col)[amt]
           .rolling(f"{window_m * 31}D").sum().reset_index()
           .rename(columns={"m": month_col, amt: "ref"}))
    chk = chk.merge(ref, on=[firm_col, month_col], how="left")
    bad = chk[chk["ref"].notna() & (chk[value_col] > chk["ref"] * 1.001 + 1.0)]
    return pd.DataFrame([{"검사": "PANEL_AHEAD_OF_EVENTS", "위반건수": len(bad),
                          "설명": f"{value_col} 이 그 시점 관측 누적을 초과한 행"}]
                        if len(bad) else [], columns=["검사", "위반건수", "설명"])


# ══════════════════════════════════════════════════════════════════════════════
#  L3 — 통계 탐지 (§74 permutation placebo, §75 temporal placebo)
# ══════════════════════════════════════════════════════════════════════════════
def permutation_placebo(F: pd.DataFrame, score_col: str, ret_col: str, n_perm: int = 200,
                        month_col: str = "month", seed: int = 20260820) -> pd.DataFrame:
    """§74 — 같은 달 안에서 신호를 섞어 null 분포를 만든다. 실제 IC 가 얼마나 극단적인가."""
    d = F[[month_col, score_col, ret_col]].dropna()
    if len(d) < 50:
        return pd.DataFrame()
    real, _ = information_coefficient(d, score_col, ret_col, month_col)
    if not len(real):
        return pd.DataFrame()
    real_ic = float(real["평균IC"].iloc[0])
    rg = np.random.default_rng(seed)
    codes = d[month_col].astype("category").cat.codes.to_numpy()
    order = np.argsort(codes, kind="stable")
    s_sorted = d[score_col].to_numpy()[order]
    starts = np.searchsorted(codes[order], np.arange(codes.max() + 1), side="left")
    ends = np.searchsorted(codes[order], np.arange(codes.max() + 1), side="right")
    null = np.empty(n_perm)
    base = d.iloc[order].reset_index(drop=True)
    for i in range(n_perm):
        sh = s_sorted.copy()
        for a, b in zip(starts, ends):
            if b - a > 1:
                sh[a:b] = rg.permutation(sh[a:b])
        tmp = base.assign(**{score_col: sh})
        r, _ = information_coefficient(tmp, score_col, ret_col, month_col)
        null[i] = float(r["평균IC"].iloc[0]) if len(r) else np.nan
    null = null[np.isfinite(null)]
    if not len(null):
        return pd.DataFrame()
    p = float((np.abs(null) >= abs(real_ic)).mean())
    return pd.DataFrame([{"검정": "permutation_placebo(§74)", "실제 평균IC": real_ic,
                          "null 평균": float(null.mean()), "null 표준편차": float(null.std(ddof=1)),
                          "z": (real_ic - null.mean()) / (null.std(ddof=1) + 1e-12),
                          "양측 p": p, "순열수": len(null)}])


def temporal_placebo(F: pd.DataFrame, score_col: str, market: pd.DataFrame,
                     firm_col: str = "stock_code", month_col: str = "month",
                     lead_months: int = 12) -> pd.DataFrame:
    """§75 — '미래 신호'가 '과거 수익률'을 설명하면 leakage 의심. 비정상적으로 강하면 재감사."""
    mk = market[[firm_col, month_col, "ret"]].copy()
    fut = F[[firm_col, month_col, score_col]].copy()
    fut[month_col] = (pd.to_datetime(fut[month_col]) - pd.DateOffset(months=lead_months)
                      + pd.offsets.MonthEnd(0))
    j = mk.merge(fut.rename(columns={score_col: "future_signal"}),
                 on=[firm_col, month_col], how="inner").dropna()
    if len(j) < 100:
        return pd.DataFrame()
    summ, _ = information_coefficient(j, "future_signal", "ret", month_col)
    if not len(summ):
        return pd.DataFrame()
    ic = float(summ["평균IC"].iloc[0])
    t = float(summ["IC_t"].iloc[0])
    return pd.DataFrame([{"검정": f"temporal_placebo(§75, lead={lead_months}M)",
                          "미래신호→과거수익 IC": ic, "IC_t": t, "표본": int(summ["월수"].iloc[0]),
                          "판정": ("LEAKAGE_SUSPECT" if abs(t) >= 3.0 else
                                  "WARN" if abs(t) >= 2.0 else "OK"),
                          "해석": ("미래 정부수요가 과거 주가를 설명한다면 타임스탬프/PIT 를 "
                                 "재감사해야 한다(§75)")}])


# ══════════════════════════════════════════════════════════════════════════════
#  §93 카나리아 — 탐지기가 실제로 실패시키는지 증명한다
# ══════════════════════════════════════════════════════════════════════════════
def make_canary_events(E: pd.DataFrame, n_inject: int = 50, seed: int = 20260820) -> pd.DataFrame:
    """미래 낙찰정보를 입찰 이전 시점으로 앞당긴 오염 데이터셋을 만든다."""
    rg = np.random.default_rng(seed)
    d = E.copy()
    aw = d.index[(d["stage"] == "AWARD")].to_numpy()
    if len(aw) == 0:
        raise ValueError("AWARD 이벤트가 없어 카나리아를 만들 수 없습니다.")
    pick = rg.choice(aw, size=min(n_inject, len(aw)), replace=False)
    # 낙찰 결과를 개찰 400일 전에 '알고 있었던' 것처럼 앞당긴다
    d.loc[pick, "available_at"] = d.loc[pick, "available_at"] - pd.Timedelta(days=400)
    d.loc[pick, "source_published_at"] = d.loc[pick, "available_at"]
    d.loc[pick, "_canary"] = True
    d["_canary"] = d.get("_canary", pd.Series(False, index=d.index)).fillna(False)
    return d


def make_canary_signal(F: pd.DataFrame, ret_col: str, score_col: str = "G2B_DWA",
                       strength: float = 0.6, seed: int = 20260820) -> pd.DataFrame:
    """신호에 미래수익률을 직접 섞은 오염본 — 하네스가 둔감하지 않은지 검증한다(R1a 형)."""
    rg = np.random.default_rng(seed)
    d = F.copy()
    r = pd.to_numeric(d[ret_col], errors="coerce")
    rk = r.groupby(d["month"], observed=True).rank(pct=True)
    base = pd.to_numeric(d[score_col], errors="coerce")
    d[score_col + "_CONTAMINATED"] = (1 - strength) * base.fillna(0.5) + strength * rk.fillna(0.5)
    return d


def run_canary(E: pd.DataFrame) -> Tuple[bool, pd.DataFrame]:
    """(통과여부, 표). 오염본에서 탐지기가 반드시 위반을 잡아야 한다."""
    clean = scan_events(E)
    canary = scan_events(make_canary_events(E))
    n_clean = int(clean["위반건수"].sum()) if len(clean) else 0
    n_canary = int(canary["위반건수"].sum()) if len(canary) else 0
    passed = (n_clean == 0) and (n_canary > 0)
    tab = pd.DataFrame([
        {"데이터셋": "정상(clean)", "탐지 위반건수": n_clean, "기대": "0", "판정": "✔" if n_clean == 0 else "✖"},
        {"데이터셋": "오염(canary)", "탐지 위반건수": n_canary, "기대": ">0",
         "판정": "✔" if n_canary > 0 else "✖"}])
    if passed:
        LOG.ok("§93 누수 카나리아 통과 — 탐지기가 삽입된 미래정보를 실패시켰습니다.")
    else:
        LOG.err("§93 누수 카나리아 실패 — 본 백테스트 실행을 금지합니다.")
    return passed, tab


def gate_or_raise(E: pd.DataFrame) -> pd.DataFrame:
    """본 백테스트 전에 반드시 통과해야 하는 관문(§93)."""
    passed, tab = run_canary(E)
    if not passed:
        raise LeakageDetected(
            "§93 누수 카나리아가 통과하지 못했습니다. 탐지기가 미래정보 삽입을 잡지 못하는 상태에서는 "
            "백테스트 결과를 신뢰할 수 없으므로 실행을 중단합니다.")
    return tab


# ==========================================================================================
#  audit/coverage.py
# ==========================================================================================
"""커버리지 게이트와 기업매칭 품질.   §51 · §52 · §50"""




def entity_gate(events: pd.DataFrame, amount_col: str = "amount") -> Tuple[pd.DataFrame, dict]:
    """§52 — 상장기업 관련 낙찰/계약금액 중 exact / verified / ambiguous / unmatched 비중."""
    a = events[events["stage"].isin(["AWARD", "CONTRACT"])]
    q = mapping_quality(a, amount_col)
    if not len(q):
        return q, {"verdict": "NO_DATA", "exact_amount_share": np.nan}
    exact = float(q.loc[q["map_type"].isin(["EXACT_ID", "VERIFIED_MANUAL"]), "금액비중"].sum())
    res = {"exact_amount_share": exact,
           "ambiguous_share": float(q.loc[q["map_type"] == "AMBIGUOUS", "금액비중"].sum()),
           "unmatched_share": float(q.loc[q["map_type"] == "UNMATCHED", "금액비중"].sum()),
           "out_of_validity_share": float(q.loc[q["map_type"] == "OUT_OF_VALIDITY",
                                                "금액비중"].sum())}
    # 상장사 귀속 금액은 전체 조달의 일부일 수밖에 없다(비상장 공급자가 다수).
    # 따라서 게이트는 '전체 대비'가 아니라 '식별된 것 중 exact 비중'으로 본다.
    ident = exact + res["ambiguous_share"]
    res["exact_among_identified"] = (exact / ident) if ident > 0 else np.nan
    res["verdict"] = ("PASS" if (pd.notna(res["exact_among_identified"]) and
                                 res["exact_among_identified"] >= 0.90) else "REVIEW")
    return q, res


def observability_report(events: pd.DataFrame, months: pd.DatetimeIndex,
                         firm_col: str = "stock_code") -> pd.DataFrame:
    """§50 — 월별 procurement-observable 기업 수 (현재 명단 소급 금지의 실증)."""
    from backtest.universe import procurement_observable
    o = procurement_observable(events, months, firm_col)
    if not len(o):
        return pd.DataFrame()
    return (o.groupby("month", observed=True)[firm_col].nunique()
            .rename("procurement_observable_N").reset_index())


def monthly_gate(F: pd.DataFrame, score_col: str, universe: Optional[pd.DataFrame],
                 top_pct: float = 0.20, gates: Optional[dict] = None
                 ) -> Tuple[pd.DataFrame, dict]:
    T, res = coverage_gate(F, score_col, universe, top_pct, gates)
    if res["verdict"] != "PASS":
        LOG.warn(f"[§51 SAMPLE_COLLAPSE] scored 중앙값 {res['scored']['median']:.0f} / "
                 f"p10 {res['scored']['p10']:.0f} / top bucket 중앙값 "
                 f"{res['top_bucket']['median']:.0f} — 성과와 무관하게 표본붕괴로 표시합니다.")
    else:
        LOG.ok(f"[§51] 커버리지 게이트 통과 — scored 중앙값 {res['scored']['median']:.0f}, "
               f"top bucket 중앙값 {res['top_bucket']['median']:.0f}")
    return T, res


# ==========================================================================================
#  audit/robustness.py
# ==========================================================================================
"""강건성 검사.   §65 ~ §73

  §65 전체 / 초기·중기·후기 1/3 / 연도별
  §66 Leave-One-Year-Out
  §67 Leave-One-Agency-Out        ← 이벤트를 지우고 피처를 다시 만든다(기관 제거는 수요도 바꾼다)
  §68 Leave-One-Category-Out      ← 같은 이유로 재구축
  §69 Mega contract 상위 0.1/0.5/1% 제거·윈저
  §70 상위 성과기여 1/3/5/10 종목 제거
  §71 시총버킷 · §72 시장(KOSPI/KOSDAQ) · §73 업종별 기여

재구축형 검사는 rebuild_fn(events)->scored_panel 콜백을 받는다.
'해당 기관을 뺐다'고 말하면서 피처는 그대로 두면 검사가 아니라 연출이다.
"""




def _run(F: pd.DataFrame, score_col: str, ret_col: str, label: str,
         top_pct: float = 0.20, min_holdings: int = 10, **kw) -> pd.DataFrame:
    pf = build_portfolio(F, score_col, ret_col, top_pct=top_pct, min_holdings=min_holdings, **kw)
    if not len(pf["returns"]):
        return pd.DataFrame([{"구분": label, "관측월": 0, "판정": "표본부족"}])
    bm = F.dropna(subset=[ret_col]).groupby("month", observed=True)[ret_col].mean()
    R = pf["returns"].set_index("month")
    ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
    t = perf_table(ex, label=label).iloc[0]
    return pd.DataFrame([{"구분": label, "관측월": int(t["관측월"]),
                          "순초과(연,%)": 100 * float(t["연환산수익"]),
                          "NW_t": float(t["NW_t"]), "MDD": float(t["MDD"]),
                          "적중률": float(t["적중률"]),
                          "평균보유": float(pf["returns"]["holdings"].mean())}])


def by_period(F: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """§65 — 전체 / 1·2·3분기간 / 연도별."""
    d = F.dropna(subset=[score_col, ret_col])
    if not len(d):
        return pd.DataFrame()
    months = np.sort(d["month"].unique())
    n = len(months)
    parts = [_run(d, score_col, ret_col, "전체")]
    for k, nm in ((0, "초기 1/3"), (1, "중기 1/3"), (2, "후기 1/3")):
        sel = months[int(n * k / 3): int(n * (k + 1) / 3)]
        parts.append(_run(d[d["month"].isin(sel)], score_col, ret_col, nm))
    for y, g in d.groupby(d["month"].dt.year):
        parts.append(_run(g, score_col, ret_col, f"{y}년"))
    return pd.concat(parts, ignore_index=True)


def leave_one_year_out(F: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """§66 — 특정 연도 의존 여부."""
    d = F.dropna(subset=[score_col, ret_col])
    parts = [_run(d, score_col, ret_col, "전체")]
    for y in sorted(d["month"].dt.year.unique()):
        parts.append(_run(d[d["month"].dt.year != y], score_col, ret_col, f"{y} 제외"))
    return pd.concat(parts, ignore_index=True)


def leave_one_out_rebuild(events: pd.DataFrame, rebuild_fn: Callable[[pd.DataFrame], pd.DataFrame],
                          score_col: str, ret_col: str, dim: str, top_k: int = 5,
                          amount_col: str = "amount") -> pd.DataFrame:
    """§67 · §68 — 상위 기관/품목을 하나씩 빼고 **피처를 다시 만들어** 재측정한다."""
    if dim not in events.columns:
        return pd.DataFrame()
    tot = (events.groupby(dim, observed=True)[amount_col].sum()
           .sort_values(ascending=False).head(top_k))
    base = rebuild_fn(events)
    parts = [_run(base, score_col, ret_col, "전체(재구축)")]
    for k in tot.index:
        sub = events[events[dim] != k]
        try:
            F = rebuild_fn(sub)
            parts.append(_run(F, score_col, ret_col, f"{dim}={k} 제외"))
        except Exception as e:                                 # noqa: BLE001
            parts.append(pd.DataFrame([{"구분": f"{dim}={k} 제외", "관측월": 0,
                                        "판정": f"재구축 실패 {type(e).__name__}"}]))
    return pd.concat(parts, ignore_index=True)


def mega_contract_sensitivity(events: pd.DataFrame,
                              rebuild_fn: Callable[[pd.DataFrame], pd.DataFrame],
                              score_col: str, ret_col: str,
                              quantiles: Sequence[float] = (0.001, 0.005, 0.01),
                              amount_col: str = "amount", mode: str = "drop") -> pd.DataFrame:
    """§69 — 상위 0.1/0.5/1% 계약을 제거(또는 윈저)하고 재측정."""
    parts = [_run(rebuild_fn(events), score_col, ret_col, "전체")]
    a = pd.to_numeric(events[amount_col], errors="coerce")
    for q in quantiles:
        thr = float(a.quantile(1 - q))
        if mode == "drop":
            sub = events[~(a > thr)]
            lab = f"상위 {q * 100:.1f}% 계약 제거"
        else:
            sub = events.copy()
            sub[amount_col] = a.clip(upper=thr)
            lab = f"상위 {q * 100:.1f}% 윈저"
        try:
            parts.append(_run(rebuild_fn(sub), score_col, ret_col, lab))
        except Exception as e:                                 # noqa: BLE001
            parts.append(pd.DataFrame([{"구분": lab, "관측월": 0,
                                        "판정": f"재구축 실패 {type(e).__name__}"}]))
    return pd.concat(parts, ignore_index=True)


def drop_top_contributors(F: pd.DataFrame, score_col: str, ret_col: str,
                          ks: Sequence[int] = (1, 3, 5, 10)) -> pd.DataFrame:
    """§70 — 성과기여 상위 종목을 빼도 살아남는가."""
    pf = build_portfolio(F, score_col, ret_col)
    if not len(pf["holdings"]):
        return pd.DataFrame()
    H = pf["holdings"]
    contrib = (H.assign(_c=H["w"] * H[ret_col]).groupby("stock_code", observed=True)["_c"]
               .sum().sort_values(ascending=False))
    parts = [_run(F, score_col, ret_col, "전체")]
    for k in ks:
        drop = set(contrib.head(k).index)
        parts.append(_run(F[~F["stock_code"].isin(drop)], score_col, ret_col,
                          f"상위기여 {k}종목 제외"))
    return pd.concat(parts, ignore_index=True)


def by_bucket(F: pd.DataFrame, score_col: str, ret_col: str, col: str,
              n_bins: int = 4, labels: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """§71 §72 §73 — 시총버킷 / 시장 / 업종별."""
    d = F.dropna(subset=[score_col, ret_col])
    if col not in d.columns or not len(d):
        return pd.DataFrame()
    if pd.api.types.is_numeric_dtype(d[col]):
        lab = list(labels or ["Micro", "Small", "Mid", "Large"])[:n_bins]
        d = d.assign(_b=d.groupby("month", observed=True)[col].transform(
            lambda s: pd.qcut(s.rank(method="first"), min(n_bins, max(1, s.nunique())),
                              labels=lab[:min(n_bins, max(1, s.nunique()))], duplicates="drop")))
    else:
        d = d.assign(_b=d[col].astype(str))
    parts = []
    for b, g in d.groupby("_b", observed=True):
        parts.append(_run(g, score_col, ret_col, f"{col}={b}", min_holdings=5))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def cost_stress(F: pd.DataFrame, score_col: str, ret_col: str,
                multipliers: Sequence[float] = (1.0, 2.0, 3.0)) -> pd.DataFrame:
    """§59 — 비용 1×/2×/3× 스트레스."""
    return pd.concat([_run(F, score_col, ret_col, f"비용 {m:g}×", cost_multiplier=m)
                      for m in multipliers], ignore_index=True)


def summarize(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """강건성 요약 — 몇 개 분할에서 양(+)이 유지되었나."""
    rows = []
    for name, T in tables.items():
        if T is None or not len(T) or "순초과(연,%)" not in T.columns:
            rows.append({"검사": name, "분할수": 0, "양수비율": np.nan, "최악": np.nan})
            continue
        v = pd.to_numeric(T[T["구분"] != "전체"]["순초과(연,%)"], errors="coerce").dropna()
        rows.append({"검사": name, "분할수": len(v),
                     "양수비율": float((v > 0).mean()) if len(v) else np.nan,
                     "최악": float(v.min()) if len(v) else np.nan,
                     "중앙값": float(v.median()) if len(v) else np.nan})
    return pd.DataFrame(rows)


# ==========================================================================================
#  audit/mechanism.py
# ==========================================================================================
"""메커니즘 검정.   §29 · §39 · §46 · §54 · §63 · §64 · §80 · §81 · §82 · §84

이 파일이 답해야 하는 질문
  §80 정부수요↑ → EligibleTAM↑ → 낙찰확률↑ → 계약금액↑ → 향후 매출↑
      각 화살표마다 effect size · t · N · lag 를 낸다.
  §63 Demand only / Win only / Alignment 의 증분성
  §64 단계별(PLAN/PRESPEC/BID/AWARD/CONTRACT) 정보가치 — 사후선택 금지
  §84 가장 중요한 비교: 복잡한 Demand Graph 가 단순 '낙찰금액/시총'보다 나은가
  §46 §47 계약 → DART 매출 인식 지연 — rolling estimation 아니면 MECHANISM_VALIDATION_ONLY
  §82 각 이벤트의 [-20,+60] 거래일 CAR
"""




def _panel_regression(d: pd.DataFrame, y: str, x: str, month_col: str = "month",
                      min_n: int = 20) -> dict:
    """월별 횡단면 회귀 계수의 시계열 평균 + NW t (Fama-MacBeth 형)."""
    d = d[[month_col, x, y]].dropna()
    if len(d) < min_n * 3:
        return {"beta": np.nan, "t": np.nan, "N": len(d), "months": 0}
    betas = []
    for m, g in d.groupby(month_col, observed=True):
        if len(g) < min_n:
            continue
        xv = pd.to_numeric(g[x], errors="coerce").to_numpy(float)
        yv = pd.to_numeric(g[y], errors="coerce").to_numpy(float)
        sx = np.nanstd(xv)
        if not np.isfinite(sx) or sx <= 0:
            continue
        xz = (xv - np.nanmean(xv)) / sx
        A = np.column_stack([np.ones(len(g)), np.nan_to_num(xz)])
        try:
            b, *_ = np.linalg.lstsq(A, yv, rcond=None)
            betas.append(b[1])
        except Exception:                                      # noqa: BLE001
            continue
    if not betas:
        return {"beta": np.nan, "t": np.nan, "N": len(d), "months": 0}
    mu, se, t = newey_west_t(np.array(betas))
    return {"beta": mu, "t": t, "N": len(d), "months": len(betas)}


def causal_chain(F: pd.DataFrame, firm_col: str = "stock_code",
                 month_col: str = "month") -> pd.DataFrame:
    """§80 — 인과 사슬 각 화살표의 효과크기·t·N·lag."""
    d = F.sort_values([firm_col, month_col], kind="stable").copy()
    g = d.groupby(firm_col, sort=False, observed=True)
    # 미래 자기변수(수주·계약)는 '메커니즘 검정'이지 신호가 아니다 — 팩터에 절대 넣지 않는다.
    for h in (3, 6, 12):
        d[f"fwd_award_{h}m"] = g["award_amt_12m"].shift(-h)
        if "contract_amt_12m" in d.columns:
            d[f"fwd_contract_{h}m"] = g["contract_amt_12m"].shift(-h)
    rows = []
    links = [
        ("① 정부수요↑ → EligibleTAM↑", "eligible_demand_flow_12m", "D1_DS_YOY", 0),
        ("② EligibleTAM↑ → 향후 낙찰↑(3M)", "fwd_award_3m", "D1_DS_YOY", 3),
        ("② EligibleTAM↑ → 향후 낙찰↑(6M)", "fwd_award_6m", "D1_DS_YOY", 6),
        ("② EligibleTAM↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "D1_DS_YOY", 12),
        ("③ 파이프라인↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "D2_PIPELINE_YOY", 12),
        ("④ 낙찰↑ → 계약↑(6M)", "fwd_contract_6m", "win_accel_log", 6),
        ("⑤ 정합(DWA)↑ → 향후 낙찰↑(12M)", "fwd_award_12m", "G2B_DWA", 12),
    ]
    for name, y, x, lag in links:
        if y not in d.columns or x not in d.columns:
            rows.append({"연결": name, "설명변수": x, "피설명": y, "lag(M)": lag,
                         "효과크기": np.nan, "t": np.nan, "N": 0, "월수": 0, "비고": "변수 없음"})
            continue
        dd = d.copy()
        dd[y] = np.log1p(pd.to_numeric(dd[y], errors="coerce").clip(lower=0))
        r = _panel_regression(dd, y, x, month_col)
        rows.append({"연결": name, "설명변수": x, "피설명": y, "lag(M)": lag,
                     "효과크기": r["beta"], "t": r["t"], "N": r["N"], "월수": r["months"],
                     "비고": ""})
    return pd.DataFrame(rows)


def revenue_lag_analysis(F: pd.DataFrame, sales: pd.DataFrame, firm_col: str = "stock_code",
                         month_col: str = "month",
                         quarters: Sequence[int] = (1, 2, 3, 4, 6, 8)) -> pd.DataFrame:
    """§46 §47 — G2B 계약 → DART 매출 인식 지연.

    ★ §47 이 결과로 signal weighting 을 바꾸려면 rolling historical estimation 만 허용된다.
      그렇지 않으면 MECHANISM_VALIDATION_ONLY 로 둔다. 이 함수는 후자다.
    """
    if sales is None or not len(sales) or "contract_amt_12m" not in F.columns:
        return pd.DataFrame([{"상태": "NOT_IDENTIFIABLE",
                              "사유": "PIT 매출 또는 계약금액이 없어 매출인식 지연을 볼 수 없습니다"}])
    s = sales.copy()
    s["month"] = pd.to_datetime(s["filing_ts"]) + pd.offsets.MonthEnd(0)
    s = s.sort_values([firm_col, "month"], kind="stable")
    s["rev_yoy"] = s.groupby(firm_col, observed=True)["revenue"].pct_change(4)
    rows = []
    for k in quarters:
        sk = s.copy()
        sk[month_col] = sk["month"] - pd.DateOffset(months=3 * k)
        sk[month_col] = sk[month_col] + pd.offsets.MonthEnd(0)
        j = F[[firm_col, month_col, "contract_amt_12m", "mcap"]].merge(
            sk[[firm_col, month_col, "rev_yoy"]], on=[firm_col, month_col], how="inner").dropna()
        if len(j) < 60:
            rows.append({"lag(분기)": k, "표본": len(j), "효과크기": np.nan, "t": np.nan,
                         "비고": "표본부족"})
            continue
        j["x"] = np.log1p(j["contract_amt_12m"].clip(lower=0) / j["mcap"].replace(0, np.nan))
        r = _panel_regression(j, "rev_yoy", "x", month_col, min_n=10)
        rows.append({"lag(분기)": k, "표본": r["N"], "효과크기": r["beta"], "t": r["t"],
                     "비고": "MECHANISM_VALIDATION_ONLY (§47)"})
    return pd.DataFrame(rows)


def decomposition(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§63 — Demand only / Win only / Alignment 의 증분성."""
    specs = [("Demand only (D1)", "D1_DS_YOY"), ("Win only (W)", "W_PRIMARY"),
             ("Demand-Win Alignment", "G2B_DWA")]
    rows = []
    for name, col in specs:
        if col not in F.columns:
            continue
        pf = build_portfolio(F, col, ret_col)
        if not len(pf["returns"]):
            rows.append({"구성": name, "팩터": col, "관측월": 0})
            continue
        bm = benchmark_returns(F, ret_col)
        R = pf["returns"].set_index(month_col)
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        ic, _ = information_coefficient(F, col, ret_col, month_col)
        rows.append({"구성": name, "팩터": col, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "평균IC": float(ic["평균IC"].iloc[0]) if len(ic) else np.nan,
                     "IC_t": float(ic["IC_t"].iloc[0]) if len(ic) else np.nan})
    return pd.DataFrame(rows)


def stage_information_value(F_by_stage: Dict[str, pd.DataFrame], ret_col: str,
                            score_col: str = "G2B_DWA") -> pd.DataFrame:
    """§64 — PLAN/PRESPEC/BID/AWARD/CONTRACT 각각의 정보가치.

    ★ 이 5개 중 성과가 가장 좋은 것을 골라 PRIMARY 라 부르지 않는다. 해석용이다.
    """
    rows = []
    for st, F in F_by_stage.items():
        if F is None or not len(F) or score_col not in F.columns:
            rows.append({"단계": st, "관측월": 0, "비고": "데이터 없음"})
            continue
        pf = build_portfolio(F, score_col, ret_col)
        if not len(pf["returns"]):
            rows.append({"단계": st, "관측월": 0, "비고": "표본부족"})
            continue
        bm = benchmark_returns(F, ret_col)
        R = pf["returns"].set_index("month")
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        rows.append({"단계": st, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "비고": "해석용 — PRIMARY 사후선택 금지(§64)"})
    return pd.DataFrame(rows)


def nested_comparison(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§84 §99 — 이 연구의 최종 판정표.

    '복잡한 Demand Graph 가 단순 낙찰금액/시총보다 실제로 나은가?'
    복잡성이 단순모델을 이기지 못하면 단순모델을 채택한다.
    """
    fam = factor_family(F)
    rows = []
    for name, col in fam.items():
        if col not in F.columns or F[col].notna().sum() < 100:
            rows.append({"모델": name, "팩터": col, "관측월": 0, "비고": "산출 불가"})
            continue
        pf = build_portfolio(F, col, ret_col)
        bm = benchmark_returns(F, ret_col)
        if not len(pf["returns"]):
            rows.append({"모델": name, "팩터": col, "관측월": 0, "비고": "표본부족"})
            continue
        R = pf["returns"].set_index(month_col)
        ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
        t = perf_table(ex).iloc[0]
        ic, _ = information_coefficient(F, col, ret_col, month_col)
        rows.append({"모델": name, "팩터": col, "관측월": int(t["관측월"]),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "p": float(t["p(NW)"]), "Sharpe": float(t["Sharpe"]),
                     "MDD": float(t["MDD"]),
                     "평균IC": float(ic["평균IC"].iloc[0]) if len(ic) else np.nan,
                     "복잡도": {"1_Award_Amount_only": "단순", "2_Award_over_MCap": "단순",
                              "3_Demand_Shift_only": "중간", "4_Win_Acceleration_only": "중간",
                              "5_Demand_Win_Alignment": "복합"}.get(name, "")})
    T = pd.DataFrame(rows)
    if len(T) and "순초과(연,%)" in T.columns:
        simple = T[T["복잡도"] == "단순"]["순초과(연,%)"].max()
        full = T[T["복잡도"] == "복합"]["순초과(연,%)"].max()
        if pd.notna(simple) and pd.notna(full):
            T.attrs["verdict"] = ("FULL_WINS" if full > simple + 0.5 else "SIMPLE_ADOPTED")
            LOG.info(f"§99 판정: 단순 최고 {simple:.2f}%p vs 복합 {full:.2f}%p → "
                     f"{T.attrs['verdict']}")
    return T


def bucket_2x2(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.DataFrame:
    """§29 — Demand High/Low × Win High/Low. 핵심 가설상 D_high·W_high 가 가장 좋아야 한다."""
    d = F.dropna(subset=["P_D", "P_W", ret_col]).copy()
    if not len(d):
        return pd.DataFrame()
    d["bucket"] = np.where((d["P_D"] >= .5) & (d["P_W"] >= .5), "D_high_W_high",
                    np.where((d["P_D"] >= .5) & (d["P_W"] < .5), "D_high_W_low",
                      np.where((d["P_D"] < .5) & (d["P_W"] >= .5), "D_low_W_high", "D_low_W_low")))
    bm = benchmark_returns(d, ret_col)
    rows = []
    for b, g in d.groupby("bucket", observed=True):
        r = g.groupby(month_col, observed=True)[ret_col].mean()
        ex = (r - bm.reindex(r.index)).dropna()
        t = perf_table(ex).iloc[0]
        rows.append({"버킷": b, "평균 종목수": float(g.groupby(month_col).size().mean()),
                     "순초과(연,%)": 100 * float(t["연환산수익"]), "NW_t": float(t["NW_t"]),
                     "관측월": int(t["관측월"])})
    T = pd.DataFrame(rows).sort_values("순초과(연,%)", ascending=False).reset_index(drop=True)
    T["비고"] = np.where(T["버킷"] == "D_high_W_high",
                       "가설상 최상위여야 함 — 메커니즘 확인용이며 파라미터 탐색 도구가 아니다(§29)", "")
    return T


def secondary_family_fdr(F: pd.DataFrame, ret_col: str, candidates: Sequence[str],
                         month_col: str = "month", q: float = 0.10) -> pd.DataFrame:
    """§78 — Secondary family 에 BH/FDR 적용. 최고 t 하나만 보고 성공이라 하지 않는다."""
    rows = []
    for c in candidates:
        if c not in F.columns or F[c].notna().sum() < 100:
            continue
        ic, _ = information_coefficient(F, c, ret_col, month_col)
        if not len(ic):
            continue
        t = float(ic["IC_t"].iloc[0])
        rows.append({"팩터": c, "평균IC": float(ic["평균IC"].iloc[0]), "IC_t": t,
                     "월수": int(ic["월수"].iloc[0]), "p": t_to_p(t, max(int(ic["월수"].iloc[0]) - 1, 5))})
    if not rows:
        return pd.DataFrame()
    T = pd.DataFrame(rows)
    bh = bh_fdr(T["p"].tolist(), q=q)
    T["BH_임계값"] = bh["BH_임계값"].to_numpy()
    T["FDR 기각"] = bh["기각(FDR)"].to_numpy()
    return T.sort_values("p").reset_index(drop=True)


def event_study(events: pd.DataFrame, market_daily: Optional[pd.DataFrame], firm_col: str = "stock_code",
                window: Tuple[int, int] = (-20, 60)) -> pd.DataFrame:
    """§54 §82 — 단계별 [-20,+60] 거래일 CAR.

    일별 가격이 없으면 NOT_IDENTIFIABLE 로 두고 월별 근사로 대체하지 않는다
    (월 단위로 [-20,+60] 을 흉내내면 그건 event study 가 아니다).
    """
    if market_daily is None or not len(market_daily):
        return pd.DataFrame([{"상태": "NOT_IDENTIFIABLE",
                              "사유": "일별 수익률 패널이 없어 [-20,+60] CAR 을 계산할 수 없습니다(§82). "
                                    "공용 인덱스에 krx_ohlcv_daily 가 있으면 자동으로 계산됩니다."}])
    md = market_daily[[firm_col, "date", "ret"]].dropna().sort_values([firm_col, "date"])
    md["_i"] = md.groupby(firm_col, observed=True).cumcount()
    idx = md.set_index([firm_col, "date"])["_i"]
    rows = []
    for st, g in events[events[firm_col].notna()].groupby("stage", observed=True):
        ev = g[[firm_col, "available_at"]].dropna().copy()
        ev["date"] = pd.to_datetime(ev["available_at"]).dt.normalize()
        j = ev.join(idx, on=[firm_col, "date"], how="inner")
        if not len(j):
            continue
        car = []
        for off in range(window[0], window[1] + 1):
            t = md.merge(j.assign(_t=j["_i"] + off)[[firm_col, "_t"]],
                         left_on=[firm_col, "_i"], right_on=[firm_col, "_t"], how="inner")
            if len(t):
                car.append({"stage": st, "day": off, "mean_ret": float(t["ret"].mean()),
                            "n": len(t)})
        if car:
            C = pd.DataFrame(car).sort_values("day")
            C["CAR"] = C["mean_ret"].cumsum()
            rows.append(C)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        [{"상태": "NO_MATCH", "사유": "이벤트 일자와 거래일이 매칭되지 않았습니다"}])


# ==========================================================================================
#  pipeline.py
# ==========================================================================================
"""파이프라인 배선 — 수집 → lifecycle → graph → PIT 피처 → 저장.

★ 사용자 필수 요구사항의 구현부:
   · 캐시활용 최우선 : 공용 인덱스에 있으면 절대 재수집하지 않는다.
   · 신규 수집 데이터 → **공용 인덱스**(다른 전략도 재사용 가능한 원본/범용 정제본)
   · 이 연구의 해석물 → **전용 인덱스**(lifecycle · graph · feature · backtest)

§89 최종 산출물 파일명을 그대로 만든다.
"""



# 서비스명 → (ServiceSpec, 수집함수). 단일파일 빌드에서도 이름이 충돌하지 않도록
# 각 수집기는 고유한 SPEC_*/collect_* 이름을 쓴다.
COLLECTORS = {
    "order_plan": (SPEC_ORDER_PLAN, collect_order_plan),
    "prespec": (SPEC_PRESPEC, collect_prespec),
    "bid": (SPEC_BID_NOTICE, collect_bid),
    "award": (SPEC_AWARD_INFO, collect_award),
    "contract": (SPEC_CONTRACT, collect_contract),
    "process": (SPEC_PROC_BID, collect_process),
}


# ══════════════════════════════════════════════════════════════════════════════
#  1. 수집 / 적재
# ══════════════════════════════════════════════════════════════════════════════
def collect_events(start: str, end: str, services: Optional[List[str]] = None
                   ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """FULL 모드 수집. 캐시(raw 매니페스트/공용 인덱스)에 있으면 네트워크에 나가지 않는다."""
    V = get_vault()
    parts, audits = [], []
    for name in (services or list(COLLECTORS)):
        spec, collect_fn = COLLECTORS[name]
        tbl = CFG.SHARED_CONTRIB_TABLES[name]
        cached = V.get_table(tbl, scope="shared")
        if CFG.RUN_MODE == "CACHED":
            if cached is not None and len(cached):
                LOG.ok(f"[{name}] 공용 캐시 {len(cached):,}행 재사용 (CACHED 모드 — 신규 수집 없음)")
                parts.append(cached)
            else:
                LOG.warn(f"[{name}] 공용 캐시가 없습니다 (CACHED 모드이므로 수집하지 않음)")
            continue
        LOG.info(f"[{name}] 수집 시작 {start} ~ {end}")
        D, A = collect_fn(start, end)
        audits.append(A)
        if cached is not None and len(cached):
            # append-merge: 기존 캐시를 버리지 않고 합집합으로만 늘린다
            key = [c for c in ("service", "doc_id", "doc_seq", "stage", "event_time")
                   if c in cached.columns and c in D.columns]
            D = (pd.concat([cached, D], ignore_index=True)
                 .drop_duplicates(subset=key or None, keep="last"))
        if D is not None and len(D):
            V.put_table(tbl, D, scope="shared", domain="procurement",
                        source=f"나라장터 {name} (data.go.kr {spec.portal_id})",
                        extra={"start": start, "end": end})
            parts.append(D)
    V.flush("shared")
    E = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CANON_COLS)
    A = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()
    return E, A


def load_events(start: str = None, end: str = None, smoke_scale: int = 260
                ) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """실행모드에 맞춰 이벤트를 얻는다. SMOKE 는 합성 세계."""
    start = start or CFG.TARGET_START
    end = end or CFG.TARGET_END
    ctx: Dict[str, pd.DataFrame] = {}
    if CFG.RUN_MODE == "SMOKE":
        W = build_world(start, end, opp_per_month=smoke_scale)
        ctx.update(W)
        E = W["events"]
        E["broad_category"] = E["license_req"]
        return E, ctx
    E, A = collect_events(start, end)
    ctx["collect_audit"] = A
    if len(E) and "available_at" not in E.columns:
        E = stamp(E, "event_time", "source_published_at", stage="BID")
    return E, ctx


def load_crosswalk(events: pd.DataFrame, ctx: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """§13 §14 — 사업자등록번호 exact match 우선. 캐시 우선."""
    V = get_vault()
    if CFG.RUN_MODE == "SMOKE" and "suppliers" in ctx:
        cw = crosswalk_from_world(ctx)
        return cw
    cached = V.get_table(CFG.SHARED_CONTRIB_TABLES["crosswalk"], scope="shared")
    if cached is not None and len(cached) and CFG.RUN_MODE == "CACHED":
        LOG.ok(f"공용 캐시 crosswalk {len(cached):,}행 재사용")
        return cached
    cc = fetch_corp_codes()
    listed = cc[cc["stock_code"].notna()]["corp_code"].astype(str).tolist() if len(cc) else []
    prof = fetch_company_profiles(listed)
    lh = None
    sm = V.get_table(CFG.SHARED_REUSE_TABLES["listing_snapshots"], scope="shared")
    if sm is not None and len(sm):
        lh = sm
    cw = build_crosswalk(prof, corp_codes=cc, listing_history=lh)
    if len(cw):
        V.put_table(CFG.SHARED_CONTRIB_TABLES["crosswalk"], cw, scope="shared", domain="entity",
                    source="G2B bizr_no ↔ DART bizr_no exact match")
        V.flush("shared")
    return cw


def load_market(months: pd.DatetimeIndex, ctx: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """PIT 가격/시총/섹터 패널. 사용자 보유 PIT DB(공용 인덱스) 최우선."""
    if CFG.RUN_MODE != "SMOKE":
        M = load_market_panel(months)
        if M is not None and len(M):
            return M
    if "suppliers" in ctx:
        return build_market(ctx)["panel"]
    LOG.warn("가격 패널을 얻지 못했습니다 — 백테스트를 수행할 수 없습니다.")
    return pd.DataFrame(columns=["stock_code", "month", "ret", "mcap", "sector", "market"])


# ══════════════════════════════════════════════════════════════════════════════
#  2. GOLD — lifecycle · graph
# ══════════════════════════════════════════════════════════════════════════════
def build_gold(events: pd.DataFrame, crosswalk: pd.DataFrame,
               use_attr_linkage: bool = False) -> Dict[str, object]:
    L, diag = resolve_opportunities(events, use_attr=use_attr_linkage)
    L = attach_stock_code(L, crosswalk)
    L = allocate(L, "primary")
    if "broad_category" not in L.columns:
        L["broad_category"] = L.get("license_req", L["proc_type"])
    lc = opportunity_lifecycle(L)
    G = build_graph(L, crosswalk)
    return {"events": L, "link_diag": diag, "lifecycle": lc,
            "graph_nodes": G.nodes, "graph_edges": G.edges, "graph": G}


# ══════════════════════════════════════════════════════════════════════════════
#  3. PIT 피처
# ══════════════════════════════════════════════════════════════════════════════
def build_features(L: pd.DataFrame, months: pd.DatetimeIndex, market: pd.DataFrame,
                   pit_sales: Optional[pd.DataFrame] = None,
                   maturity_days: int = 365,
                   demand_col: str = "D1_DS_YOY",
                   win_col: str = "win_accel_log",
                   neutral_mode: str = "sector_size") -> Dict[str, pd.DataFrame]:
    """§17~§44 전체. 반환 dict 는 §89 산출물 이름을 따른다."""
    cap = build_capability(L, months)
    dem, lad = demand_panel(L, months)
    dem = exogeneity_split(L, dem, months)
    sp = stage_probability(L, months, maturity_days=maturity_days)
    swd = stage_weighted_demand(lad, sp, months)
    if len(swd):
        dem = dem.merge(swd, on=["category_cd", "month"], how="left")
        dem["demand_flow_w"] = dem["demand_flow_w"].fillna(0.0)
    lofo = lofo_adjustment(lad, L, months)
    tam = build_eligible_tam(cap, dem, lofo=lofo)

    win = build_win_features(L, months)
    win = add_size_normalization(win, market, pit_sales)
    brd = breadth_features(L, months)
    arf = award_rate_features(L, months)
    cmp_ = competition_features(L, months)
    fail = failure_features(L, months, cap)
    con = build_concentration(L, months)
    rev = contract_revision(L, months)

    F = build_demand_axis(tam)
    for X in (build_win_axis(win, primary=win_col), brd, arf, cmp_, fail, con, rev):
        if X is not None and len(X):
            F = F.merge(X, on=["stock_code", "month"], how="outer")
    # add_size_normalization 이 이미 mcap 을 붙였을 수 있다 → 중복 병합은 mcap_x/mcap_y 를 만든다
    mk = [c for c in ("sector", "market", "mcap", "turnover_value")
          if c in market.columns and c not in F.columns]
    if mk:
        F = F.merge(market[["stock_code", "month"] + mk], on=["stock_code", "month"], how="left")
    dup = [c for c in F.columns if c.endswith(("_x", "_y"))]
    if dup:
        raise RuntimeError(f"병합 접미사 충돌 컬럼이 생겼습니다: {dup} — 중복 병합을 제거하십시오.")
    F["PROC_RISK"] = proc_risk_score(F)
    F = build_dwa(F, demand_col=demand_col, win_col="W_PRIMARY", neutral_mode=neutral_mode)
    return {"company_capability_monthly": cap, "government_demand_monthly": dem,
            "eligible_tam_monthly": tam, "company_g2b_features_monthly": F,
            "stage_probability": sp, "demand_ladder": lad,
            "agency_capability": agency_capability(L, months)}


# ══════════════════════════════════════════════════════════════════════════════
#  4. 저장 — 로컬 data/ + 구글드라이브(공용/전용)
# ══════════════════════════════════════════════════════════════════════════════
GOLD_FILES = {"lifecycle": "g2b_opportunity_lifecycle", "crosswalk": "g2b_company_crosswalk",
              "graph_nodes": "g2b_demand_graph_nodes", "graph_edges": "g2b_demand_graph_edges",
              "contract_history": "g2b_contract_history"}
PIT_FILES = {"company_capability_monthly": "company_capability_monthly",
             "government_demand_monthly": "government_demand_monthly",
             "eligible_tam_monthly": "eligible_tam_monthly",
             "company_g2b_features_monthly": "company_g2b_features_monthly"}


def save_outputs(gold: Dict[str, object], feats: Dict[str, pd.DataFrame],
                 crosswalk: pd.DataFrame, backtest: Optional[Dict[str, pd.DataFrame]] = None
                 ) -> pd.DataFrame:
    """§89 산출물을 로컬과 드라이브에 남긴다. 공용/전용 구분은 재사용성 기준이다."""
    CFG.ensure_dirs()
    V = get_vault()
    rows = []

    def _put(df: pd.DataFrame, local_dir: str, name: str, scope: str, domain: str):
        if df is None or not len(df):
            rows.append({"산출물": name, "행수": 0, "위치": "—", "인덱스": "—"})
            return
        p = os.path.join(local_dir, f"{name}.parquet")
        atomic_write_parquet(df, p)
        V.put_table(name, df, scope=scope, domain=domain, source="g2b_demand_graph_v1",
                    extra={"run_id": CFG.run_id(), "df_sha256": df_hash(df)})
        rows.append({"산출물": name, "행수": len(df), "위치": os.path.relpath(p, CFG.PROJECT_ROOT),
                     "인덱스": ("공용 " + CFG.GDRIVE_SHARED_NS) if scope == "shared"
                                else ("전용 " + CFG.GDRIVE_PRIVATE_NS)})

    # 공용: 다른 전략도 그대로 쓸 수 있는 원장 (crosswalk, 계약이력)
    _put(crosswalk, CFG.GOLD_DIR, GOLD_FILES["crosswalk"], "shared", "entity")
    ev = gold.get("events")
    if isinstance(ev, pd.DataFrame) and len(ev):
        ch = ev[ev["stage"] == "CONTRACT"]
        _put(ch, CFG.GOLD_DIR, GOLD_FILES["contract_history"], "shared", "procurement")
        _put(ev, CFG.GOLD_DIR, "g2b_events_normalized", "shared", "procurement")
    # 전용: 이 연구의 해석물
    _put(gold.get("lifecycle"), CFG.GOLD_DIR, GOLD_FILES["lifecycle"], "private", "graph")
    _put(gold.get("graph_nodes"), CFG.GOLD_DIR, GOLD_FILES["graph_nodes"], "private", "graph")
    _put(gold.get("graph_edges"), CFG.GOLD_DIR, GOLD_FILES["graph_edges"], "private", "graph")
    for k, nm in PIT_FILES.items():
        _put(feats.get(k), CFG.PIT_DIR, nm, "private", "features")
    if backtest:
        for k, df in backtest.items():
            if isinstance(df, pd.DataFrame) and len(df):
                _put(df, CFG.BACKTEST_DIR, f"g2b_dwa_{k}", "private", "backtest")
    V.flush()
    V.compact("shared")
    V.compact("private")
    T = pd.DataFrame(rows)
    LOG.table(T.values.tolist(), list(T.columns), ["l", "r", "l", "l"],
              title="§89 산출물 저장 (로컬 + 구글드라이브 공용/전용 인덱스)")
    write_json(os.path.join(CFG.AUDIT_DIR, f"run_{CFG.run_id()}.json"),
               {"stamp": CFG.run_stamp(), "outputs": rows})
    return T

# ============================================================================================
#  단일파일 실행 드라이버 — §91 의 01~13 을 인프로세스로 순차 수행한다.
# ============================================================================================
def _md_table(df, max_rows: int = 200, floatfmt: str = "{:,.4g}") -> str:
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
    return "\n".join(out) + "\n"


def run_research(smoke_scale: int = 260) -> dict:
    """전 과정 실행. 반환 dict 에 모든 산출 테이블이 담긴다."""
    ensure_dirs()
    t0 = time.time()
    res: dict = {}
    LOG.banner("G2B-DEMAND-GRAPH-V1", f"mode={RUN_MODE}  run_id={run_id()}")
    LOG.info("§97 순서: API depth → PIT → 매핑 → lifecycle → capability → TAM → "
             "Demand → Win → Alignment → Future return")

    # [1~2] 수집 (캐시 우선)
    with LOG.stage("[1-2] 수집 · PIT 원장"):
        months = month_range(
            (pd.Timestamp(TARGET_START) - pd.DateOffset(months=WARMUP_MONTHS)).strftime("%Y-%m-%d"),
            TARGET_END)
        E, ctx = load_events(smoke_scale=smoke_scale)
        if not len(E):
            LOG.err("수집된 이벤트가 없습니다 → FINAL_DECISION = DATA_BLOCKED (§96)")
            return {"verdict": "DATA_BLOCKED", "reason": "이벤트 수집 실패"}
        viol = scan_events(E)
        if len(viol):
            LOG.table(viol.astype(str).values.tolist(), list(viol.columns), title="PIT 구조 위반")
            return {"verdict": "PIT_BLOCKED", "reason": "PIT 구조 위반", "violations": viol}
        LOG.ok("PIT 구조 위반 없음")

    # [3] 기업 매핑
    with LOG.stage("[3] 기업 매핑 (사업자등록번호 exact match)"):
        cw = load_crosswalk(E, ctx)
        res["crosswalk"] = cw

    # [4] lifecycle + graph
    with LOG.stage("[4] lifecycle · demand graph (이중계산 제거)"):
        gold = build_gold(E, cw)
        L = gold["events"]
        dc = double_count_audit(L)
        LOG.table(dc.assign(금액=lambda d: (d["금액"] / 1e8).round(1)).astype(str).values.tolist(),
                  ["측정", "금액(억원)"], title="§11 이중계산 제거 검증")
        res["double_count"] = dc
        q, eg = entity_gate(L)
        LOG.table(q.astype(str).values.tolist(), list(q.columns), title="§52 매칭 품질")
        res["entity_gate"] = q
        res["entity_gate_summary"] = eg
        gate_or_raise(L)          # §93 카나리아

    # [5~9] 피처
    with LOG.stage("[5-9] capability → TAM → Demand → Win → Alignment"):
        market = load_market(months, ctx)
        md = maturity_distribution(L)
        emb = int(md["p90"].max()) if len(md) else 365
        LOG.info(f"§23 MATURITY_EMBARGO = {emb}일 (실측 p90 최댓값, 수익률 미열람)")
        sales = load_pit_financials()
        feats = build_features(L, months, market,
                               pit_sales=(sales if len(sales) else None), maturity_days=emb)
        F = feats["company_g2b_features_monthly"]
        res.update(feats)
        res["market"] = market
        bad = scan_feature_inputs([c for c in F.columns if not c.startswith("_")])
        if len(bad):
            LOG.table(bad.astype(str).values.tolist(), list(bad.columns))
            return {"verdict": "PIT_BLOCKED", "reason": "CLASS C 필드가 피처에 혼입"}

    # 사전등록 동결 — 여기까지가 수익률 미열람 구간
    with LOG.stage("사전등록 동결 (§1.1) — 이 이후에만 미래수익률을 연다"):
        cov_m = (E.assign(month=pd.to_datetime(E["available_at"]) + pd.offsets.MonthEnd(0))
                 .groupby("month", observed=True).agg(n=("stage", "size"),
                                                      stages=("stage", "nunique")).reset_index())
        st = cov_m[(cov_m["stages"] >= 3) & (cov_m["n"] >= max(50, int(cov_m["n"].median() * .25)))]
        usable = ((pd.Timestamp(st["month"].min()) + pd.DateOffset(months=WARMUP_MONTHS)
                   + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d") if len(st) else None)
        try:
            freeze(maturity_embargo_days=emb, usable_start_date=usable,
                   notes="단일파일 실행 — 커버리지·성숙분포만 사용, 수익률 미열람 상태에서 동결")
        except FileNotFoundError as e:
            LOG.warn(f"사전등록 파일이 없어 동결을 건너뜁니다: {e}")
        LOG.table(verify().astype(str).values.tolist(), list(verify().columns), title="동결 검증")
        if usable:
            F = F[F["month"] >= pd.Timestamp(usable)]

    if future_return_lock():
        LOG.err("FUTURE_RETURN_LOCK 이 걸려 있어 수익률 검정을 수행할 수 없습니다. "
                "config/ 4개 YAML 과 audit/trial_ledger.json 을 배치한 뒤 다시 실행하십시오.")
        res["verdict"] = "PIT_BLOCKED"
        return res

    # [10] 백테스트 · 메커니즘 · 강건성
    with LOG.stage("[10] PRIMARY 백테스트"):
        T, cov = monthly_gate(F, "G2B_DWA", None)
        res["coverage_monthly"], res["coverage_gate"] = T, cov
        bt = run_backtest(F, market, "G2B_DWA", top_pct=0.20, weighting="equal")
        res["backtest"] = bt
        if not len(bt["returns"]):
            res["verdict"] = "SAMPLE_COLLAPSE"
            return res
        rc = bt["ret_col"]
        LOG.table(bt["summary"].T.reset_index().astype(str).values.tolist(),
                  ["지표", "gross", "net"], title="§60 성과표")
        LOG.table(bt["quantile_table"].astype(str).values.tolist(),
                  list(bt["quantile_table"].columns), title="§55 분위 성과")
        ic, _ = information_coefficient(bt["scored"], "G2B_DWA", rc)
        res["ic"] = ic
        LOG.table(ic.astype(str).values.tolist(), list(ic.columns), title="§61 IC")
        tp = temporal_placebo(F, "G2B_DWA", market)
        if len(tp):
            LOG.table(tp.astype(str).values.tolist(), list(tp.columns), title="§75 Temporal placebo")
            res["temporal_placebo"] = tp

    with LOG.stage("메커니즘 검정 (§63 §80 §84)"):
        S = bt["scored"]
        res["causal_chain"] = causal_chain(S)
        res["decomposition"] = decomposition(S, rc)
        res["nested"] = nested_comparison(S, rc)
        res["bucket_2x2"] = bucket_2x2(S, rc)
        for k, title in (("causal_chain", "§80 인과 사슬"), ("decomposition", "§63 분해"),
                         ("nested", "§84 ★최종 비교 — Demand Graph vs 단순 낙찰금액/시총"),
                         ("bucket_2x2", "§29 2×2")):
            if len(res[k]):
                LOG.table(res[k].astype(str).values.tolist(), list(res[k].columns), title=title)

    with LOG.stage("강건성 (§65~§73)"):
        rb = {"기간(§65)": by_period(S, "G2B_DWA", rc),
              "LOYO(§66)": leave_one_year_out(S, "G2B_DWA", rc),
              "시장(§72)": by_bucket(S, "G2B_DWA", rc, "market"),
              "시총(§71)": by_bucket(S, "G2B_DWA", rc, "mcap"),
              "업종(§73)": by_bucket(S, "G2B_DWA", rc, "sector"),
              "비용(§59)": cost_stress(S, "G2B_DWA", rc),
              "상위기여제거(§70)": drop_top_contributors(S, "G2B_DWA", rc)}
        for k, Tb in rb.items():
            if Tb is not None and len(Tb):
                LOG.table(Tb.astype(str).values.tolist(), list(Tb.columns), title=k)
        res["robustness"] = rb
        res["robust_summary"] = summarize(rb)
        LOG.table(res["robust_summary"].astype(str).values.tolist(),
                  list(res["robust_summary"].columns), title="강건성 요약")

    # 판정 + 저장
    ex = bt["excess"]
    net_t = float(hac_t(ex["net_excess"])) if len(ex) else float("nan")
    net_ann = float(ex["net_excess"].mean() * 12) if len(ex) else float("nan")
    if RUN_MODE == "SMOKE":
        verdict = "DATA_BLOCKED"
    elif cov["verdict"] != "PASS":
        verdict = "SAMPLE_COLLAPSE"
    elif not np.isfinite(net_t):
        verdict = "DATA_BLOCKED"
    elif net_t >= 2.0 and net_ann >= 0.03:
        verdict = "STRONG_PASS"
    elif net_t >= 2.0 and net_ann > 0:
        verdict = "PASS"
    elif net_t >= 1.0 and net_ann > 0:
        verdict = "WEAK_EVIDENCE"
    else:
        verdict = "NO_ALPHA"
    res["verdict"] = verdict

    save_outputs(gold, feats, cw, {"portfolios": bt["returns"]})
    get_vault().report()
    LOG.banner(f"FINAL DECISION: {verdict}",
               f"순초과 {net_ann * 100:.2f}%p/yr · NW t {net_t:.2f} · "
               f"소요 {time.time() - t0:.0f}s")
    if RUN_MODE == "SMOKE":
        LOG.warn("SMOKE 모드 결과는 합성 데이터입니다 — 연구 결론이 아닙니다. "
                 "실증 판정은 키를 넣고 G2B_RUN_MODE=FULL 로 실행하십시오.")
    return res


def hac_t(x) -> float:
    return newey_west_t(x)[2]


if __name__ == "__main__":
    run_research()
