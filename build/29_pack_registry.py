

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  센서팩 레지스트리                                                                   ║
# ║                                                                                          ║
# ║  팩은 플러그인이다. 각 팩은 자기 자신을 여기에 등록하고, 스코어 조립부는 레지스트리만 본다.  ║
# ║  → 이 파일에 어떤 팩이 포함되어 빌드되었는지가 곧 전략의 정의가 된다.                       ║
# ║  C12: 정책 캘린더가 없는 센서팩은 등록될 수 없다.                                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_REGISTRY: "OrderedDict[str, dict]" = OrderedDict()


def register_pack(pid: str, name: str, tp_cols: Sequence[str], features_fn: Callable,
                  policy: Sequence[dict], interp: Sequence[Tuple[str, str, str]],
                  ingest_fn: Optional[Callable] = None, theta_col: Optional[str] = None,
                  notes: str = ""):
    if not policy:
        raise RuntimeError(
            f"[C12 위반] 센서팩 '{pid}' 에 정책 캘린더가 없습니다. "
            f"정책 캘린더 없는 센서팩은 파이프라인에 등록될 수 없습니다(§12). "
            f"모든 대체데이터는 정책에 오염됩니다 — 이건 PACK-N 만의 문제가 아닙니다.")
    PACK_REGISTRY[pid] = {
        "id": pid, "name": name, "tp_cols": list(tp_cols), "features": features_fn,
        "ingest": ingest_fn, "policy": list(policy), "interp": list(interp),
        "theta_col": theta_col, "notes": notes,
        "enabled": True, "disable_reason": "", "E_col": f"E_{pid}",
    }


def active_packs() -> List[dict]:
    return [p for pid, p in PACK_REGISTRY.items()
            if p["enabled"] and pid in ACTIVE_PACKS]


def disable_pack(pid: str, reason: str):
    if pid in PACK_REGISTRY:
        PACK_REGISTRY[pid]["enabled"] = False
        PACK_REGISTRY[pid]["disable_reason"] = reason
        LOG.warn(f"센서팩 '{pid}' 비활성화 — {reason} (조용히 남겨두지 않고 명시적으로 끕니다)")
