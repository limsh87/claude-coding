#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""하네스 위양성률 측정 — 수익률이 순수 잡음인 세계를 여러 시드로 돌린다.

MECHANISM 레짐은 R-07 연결과 R-04 SNR 구조를 심되 **수익률에는 어떤 알파도 심지 않는다.**
따라서 arm 별 IC p값은 귀무 하에서 균등분포여야 하고, p<0.05 비율은 5% 근처여야 한다.
체계적으로 낮게 나오면 그것은 팩터가 아니라 **누수**다.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from cxd import factor as fx, pipeline as pl                      # noqa: E402
from cxd.data import SyntheticWorld                               # noqa: E402
from cxd.spec import ARMS, LOCK                                   # noqa: E402


def one(seed: int, regime: str = "MECHANISM") -> dict:
    LOCK.open("위양성률 측정 — 합성 귀무 세계에서 IC 분포를 재기 위함")
    W = SyntheticWorld(regime=regime, seed=seed).build()
    axmap = pl.derive_axes(pd.Series(W["cells"], name="cell"))
    cp = fx.build_cell_panel(W["customs"]).merge(axmap.drop_duplicates("cell"),
                                                 on="cell", how="left")
    fgr = fx.compute_fgr(W["rev"])
    fgr["rev_yoy"] = (fgr.sort_values(["code", "qend"])
                      .groupby("code", observed=True)["rev_ttm"].pct_change(4))
    P = pl.assemble_panel(W["univ"], W["sec"], cp, fgr, axmap)
    out = {"seed": seed}
    from scipy import stats
    for arm in ARMS.all():
        S = fx.build_signal(P, arm)
        d = S.dropna(subset=["CXD_rank", "fwd_ret_q"])
        ic = (d.groupby("rebal", observed=True)
              .apply(lambda g: g["CXD_rank"].corr(g["fwd_ret_q"], method="spearman")
                     if len(g) >= 10 else np.nan)).dropna()
        n = len(ic)
        if n < 5:
            out[f"p_{arm.key}"] = np.nan
            out[f"ic_{arm.key}"] = np.nan
            continue
        t = ic.mean() / (ic.std(ddof=1) / np.sqrt(n))
        out[f"ic_{arm.key}"] = float(ic.mean())
        out[f"p_{arm.key}"] = float(2 * stats.t.sf(abs(t), n - 1))
    return out


if __name__ == "__main__":
    regime = sys.argv[1] if len(sys.argv) > 1 else "MECHANISM"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    seeds = [20260816 + 1000 * i for i in range(n)]
    rows = []
    with cf.ProcessPoolExecutor(max_workers=8) as ex:
        for r in ex.map(one, seeds, [regime] * len(seeds)):
            rows.append(r)
            print(".", end="", flush=True)
    D = pd.DataFrame(rows).sort_values("seed")
    print(f"\n\n=== 레짐 {regime} · 시드 {len(D)}개 ===")
    for k in ("A", "B", "C", "D"):
        p, ic = D[f"p_{k}"].dropna(), D[f"ic_{k}"].dropna()
        print(f"arm {k}: 평균IC {ic.mean():+.4f} (표준편차 {ic.std():.4f}) · "
              f"p<0.05 비율 {(p < 0.05).mean():.1%} · p 중앙 {p.median():.3f}")
    D.to_csv(f"outputs/cxd_placebo_{regime}.csv", index=False)
    print(f"\n저장: outputs/cxd_placebo_{regime}.csv")
