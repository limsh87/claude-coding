# -*- coding: utf-8 -*-
"""pytest 부트스트랩 — src/ 를 import 경로에 올린다 (src-layout)."""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
os.environ.setdefault("G2B_RUN_MODE", "SMOKE")
os.environ.setdefault("G2B_VERBOSE", "0")
os.environ.setdefault("G2B_LOCAL_CACHE_ROOT",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pytest_cache_vault"))
