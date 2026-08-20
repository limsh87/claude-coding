# -*- coding: utf-8 -*-
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
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import month_range
from pit.timestamps import stamp
from collectors.base import CANON_COLS, STAGE_RANK
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

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
