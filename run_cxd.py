#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CXD 실행 진입점. `python3 run_cxd.py [--regime ...] [--open-returns "사유"]`"""
from __future__ import annotations
import argparse, sys
import pandas as pd
from cxd.data import SyntheticWorld
from cxd import pipeline

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="MECHANISM",
                    choices=["NULL", "MECHANISM", "ALPHA_PLANT"])
    ap.add_argument("--outdir", default="outputs/cxd")
    ap.add_argument("--open-returns", default="",
                    help="FUTURE_RETURN_LOCK 해제 사유 (사람이 적는다)")
    ap.add_argument("--top-n", type=int, default=50)
    a = ap.parse_args()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 60)
    W = SyntheticWorld(regime=a.regime).build()
    art = pipeline.run(W, outdir=a.outdir, open_returns_reason=a.open_returns, top_n=a.top_n)
    return 0 if not art.get("halt") else 3

if __name__ == "__main__":
    sys.exit(main())
