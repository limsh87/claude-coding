# -*- coding: utf-8 -*-
"""PIT 저장소와 as-of 조회. 시점 t 의 계산은 t 까지 알려진 정보만 볼 수 있다 (§7).

  · 등록: PIT.register(name, df)  — available_at 없는 프레임은 KeyError 로 거부한다.
  · 조회: PIT.asof(name, t)            (단일 시점 스냅샷)
          PIT.asof_join(left, name, ...)(벡터화 등가물 — merge_asof backward)
  우회 인자를 의도적으로 만들지 않았다. 조회 경로가 둘뿐이므로 감사가 가능하다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from pit.timestamps import require_pit
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


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
