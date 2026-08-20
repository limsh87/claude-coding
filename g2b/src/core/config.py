# -*- coding: utf-8 -*-
"""G2B-DEMAND-GRAPH-V1 — 전역 설정 / 실행 모드 / 미래수익률 잠금.

명세 §1.1(FUTURE_RETURN_LOCK), §4(키는 환경변수), §48(연구기간은 커버리지로 결정),
§87(호출제한), §88(재현성)에 대응한다.

이 모듈은 어떤 무거운 의존성도 import 하지 않는다 — 어느 스크립트에서든 첫 줄에 올 수 있어야 한다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
# (없음 — 최하위 계층)
# ── /PACKAGE IMPORTS ──

import os
import sys
import json
import hashlib
import datetime as _dt
from typing import Optional, Dict, Any

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
