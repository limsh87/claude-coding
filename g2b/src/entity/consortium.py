# -*- coding: utf-8 -*-
"""공동수급·컨소시엄 금액 배분 (§16).

같은 100억 계약을 참여기업 3곳에 각각 100억씩 할당하지 않는다.
  · 지분/계약분담액이 있으면 실제 비율 사용.
  · 없으면 PRIMARY 에서는 UNKNOWN_SHARE_CONSORTIUM 으로 표시하고 금액 팩터에서 제외한다.
  · equal split / winner-only / full allocation 비교는 Secondary sensitivity 에서만.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

from typing import Literal

import numpy as np
import pandas as pd

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
