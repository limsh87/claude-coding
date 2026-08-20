# -*- coding: utf-8 -*-
"""변경이력 → PIT 리비전 구간 복원, 그리고 §8 이중계산 방지의 핵심 산식.

명세 §8 — 같은 입찰공고의 변경공고를 새로운 정부수요로 중복 계산하지 않는다.
    원공고 100억 → 수정공고 100억  ⇒ 신규수요 0    (200억이 아니다)
    원공고 100억 → 수정공고 120억  ⇒ 신규수요 +20억
    공고취소 / 재공고 / 재입찰      ⇒ 금액이 아니라 '상태변수'로 남긴다

명세 §6 CLASS B — 각 리비전의 유효기간(valid_from/valid_to)을 복원해야 PIT 로 쓸 수 있다.

전부 벡터화되어 있다 (groupby + shift/diff). 기업·월 루프가 없다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

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
