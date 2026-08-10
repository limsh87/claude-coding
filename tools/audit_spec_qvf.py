#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""명세 전수조사 러너 — 조립본 안의 `run_spec_audit()` 를 그대로 호출한다.

★ 검정 본문은 여기에 없다. `build/q71_specaudit.py` → 조립본 안에 있다.
  이유: 인수인계 계약이 "이 파일 하나만 실행하면 된다" 이기 때문이다. 검정이 tools/ 에만
  있으면 Colab 에 한 셀 붙여넣는 사용자는 계약 Q1~Q14 만 받고 전수조사는 못 받는다.
  사본을 두 벌 두면 둘이 갈라지므로(그리고 갈라진 쪽이 조용히 낡는다) 단일 원본으로 둔다.

    python3 tools/audit_spec_qvf.py            # 전체
    python3 tools/audit_spec_qvf.py 5 6        # §5·§6 만
"""
from __future__ import annotations

import os
import re
import sys
import types
from typing import Any, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "strategies", "qvf_funnel_v1.py")


def load_module(path: str = TARGET) -> Dict[str, Any]:
    """main() 을 돌리지 않고 조립본을 모듈로만 올린다(VAULT 는 스텁, 로그는 억제)."""
    src = open(path, encoding="utf-8").read()
    src = re.sub(r'^RUN_MODE\s*=\s*"FULL"', 'RUN_MODE = "SMOKE"', src, flags=re.M)
    mod = types.ModuleType("qvfmod")
    sys.modules["qvfmod"] = mod
    g = mod.__dict__
    g["__name__"] = "qvfmod"
    exec(compile(src, os.path.basename(path), "exec"), g)
    g["LOG"].min = 99

    class _Vault:                       # 디스크를 건드리지 않는 VAULT 스텁
        root = ""
        def put_table(self, *a, **k): return None
        def get_table(self, *a, **k): return None
        def flush(self, *a, **k): return None
        def compact(self, *a, **k): return None
    g["VAULT"] = _Vault()
    return g


def main(argv) -> int:
    g = load_module()
    only = [a for a in argv[1:]] or None
    g["LOG"].min = 0                    # 판정표를 보여준다
    ok = g["run_spec_audit"](strict=False, only=only)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
