# -*- coding: utf-8 -*-
"""Stage 5 — 팩터 스냅샷 (§1, §6, §7, §21).

리밸런싱 시점마다 만드는 것:
  SCG(FQ1) · FQ1 EPS YoY · FY1 EPS YoY · 12MF EPS 1M 리비전 · 기관 20D · 외국인 20D
  (+ ORIGINAL_EXACT 인 경우에만 벤더 서프라이즈 확률)

결측은 결측으로 남긴다. 0 으로 채우지 않는다(§9.1, §27). 대신 어느 단계에서 표본이
얼마나 줄었는지를 §21 워터폴로 매 시점 기록한다 — 특정 구간만 표본이 붕괴하면
성과가 아니라 데이터가 원인이라는 사실이 즉시 보여야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import contracts as C
from .config import (DENOM_NEAR_ZERO_TOL, EPS_NUMERIC_FLOOR, FACTOR_FGN, FACTOR_FQ1, FACTOR_FY1,
                     FACTOR_INST, FACTOR_REV, FACTOR_SCG, FACTOR_SP, MIN_ANALYST_COUNT,
                     UNIVERSE_PRIMARY, UNIVERSE_SENSITIVITY, SCGConfig)
from .consensus import general_consensus, smart_consensus, smart_gap
from .pit_engine import EstimateIndex, MarketPanel, TargetResolver, TradingCalendar, UniverseIndex, \
    covered_universe
from .util import LOG, safe_div

REVISION_LOOKBACK_TRADING_DAYS = 20     # §7.3 "1개월" = 20영업일

FACTOR_COLUMNS = [
    "asof", "company_code", "universe_id", "universe_snapshot_date",
    FACTOR_SCG, "SCG_RAW", "scg_flag",
    FACTOR_FQ1, "TURNAROUND_POS", "TURNAROUND_NEG", "fq1_flag",
    FACTOR_FY1, "fy1_flag",
    FACTOR_REV, "eps12mf_t", "eps12mf_t20", "twelve_mf_source",
    FACTOR_INST, FACTOR_FGN, "inst_net_20d", "foreign_net_20d", "flow_obs_20d",
    FACTOR_SP, "surprise_prob_source",
    "general_consensus_fq1", "smart_consensus_fq1", "analyst_count", "broker_count",
    "consensus_std", "consensus_mad", "estimate_age_median",
    "fq1_period", "fy1_period", "fy2_period", "target_source_q", "target_source_y",
    "market_cap", "price_close", "listed",
]


# ════════════════════════════════════════════════════════════════════════════════════════
#  PIT 조회 보조 구조
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class ActualsPIT:
    """(company, metric, fiscal_period) → (발표시각, 값). t 이하 발표된 것만 반환한다."""
    tbl: Dict[Tuple[str, str, str], Tuple[int, float]] = field(default_factory=dict)

    @classmethod
    def build(cls, actuals: "pd.DataFrame") -> "ActualsPIT":
        t: Dict[Tuple[str, str, str], Tuple[int, float]] = {}
        if actuals is None or not len(actuals):
            return cls(t)
        for code, metric, fp, val, ann in zip(
                actuals["company_code"].astype(str), actuals["metric"].astype(str),
                actuals["fiscal_period"].astype(str), actuals["actual_value"].astype(float),
                actuals["actual_announced_at"]):
            k = (code, metric, fp)
            ns = pd.Timestamp(ann).value
            prev = t.get(k)
            if prev is None or ns < prev[0]:      # 최초 발표 시점 유지(정정 소급 금지)
                t[k] = (ns, float(val))
        return cls(t)

    def values(self, codes: Sequence[str], periods: Sequence[str], asof: Any,
               metric: str = "EPS") -> np.ndarray:
        t_ns = pd.Timestamp(asof).value
        out = np.full(len(codes), np.nan)
        for i, (c, p) in enumerate(zip(codes, periods)):
            v = self.tbl.get((str(c), metric, str(p)))
            if v is not None and v[0] <= t_ns:
                out[i] = v[1]
        return out


@dataclass
class VendorPIT:
    """벤더 컨센서스 asof 조회. (company, metric, fiscal_period) 별 날짜 정렬 배열."""
    idx: Dict[Tuple[str, str, str], Tuple[np.ndarray, Dict[str, np.ndarray]]] = \
        field(default_factory=dict)
    has_smart: bool = False
    has_sp: bool = False
    has_12mf: bool = False

    @classmethod
    def build(cls, vendor: Optional["pd.DataFrame"]) -> "VendorPIT":
        obj = cls()
        if vendor is None or not len(vendor):
            return obj
        value_cols = [c for c in ("general_consensus", "smart_consensus", "surprise_probability",
                                  "eps_12mf") if c in vendor.columns]
        obj.has_smart = "smart_consensus" in value_cols and bool(vendor["smart_consensus"].notna().any())
        obj.has_sp = "surprise_probability" in value_cols and bool(
            vendor["surprise_probability"].notna().any())
        obj.has_12mf = "eps_12mf" in value_cols and bool(vendor["eps_12mf"].notna().any())
        for key, grp in vendor.groupby(["company_code", "metric", "fiscal_period"], observed=True):
            grp = grp.sort_values("date", kind="mergesort")
            dates = grp["date"].to_numpy("datetime64[ns]").astype("int64")
            vals = {c: grp[c].to_numpy(dtype=float) for c in value_cols}
            obj.idx[(str(key[0]), str(key[1]), str(key[2]))] = (dates, vals)
        return obj

    def get(self, codes: Sequence[str], periods: Sequence[str], asof: Any, col: str,
            metric: str = "EPS") -> np.ndarray:
        t_ns = pd.Timestamp(asof).value
        out = np.full(len(codes), np.nan)
        for i, (c, p) in enumerate(zip(codes, periods)):
            e = self.idx.get((str(c), metric, str(p)))
            if not e:
                continue
            dates, vals = e
            arr = vals.get(col)
            if arr is None:
                continue
            j = int(np.searchsorted(dates, t_ns, side="right")) - 1
            if j >= 0:
                out[i] = arr[j]
        return out


# ════════════════════════════════════════════════════════════════════════════════════════
#  개별 팩터
# ════════════════════════════════════════════════════════════════════════════════════════
def yoy_growth(cur: np.ndarray, prev: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """§7.1/§7.2 — (YoY, TURNAROUND_POS, TURNAROUND_NEG, flag).

    분모는 abs(전년 실적). 부호 변화를 성장률로 뭉개면 흑자전환이 −300% 로 둔갑한다.
    그래서 부호가 바뀌는 경우는 YoY 를 결측으로 두고 전용 플래그로 분리한다.
    """
    n = len(cur)
    out = np.full(n, np.nan)
    tpos = np.zeros(n, dtype=np.int8)
    tneg = np.zeros(n, dtype=np.int8)
    flag = np.array(["OK"] * n, dtype=object)

    fin = np.isfinite(cur) & np.isfinite(prev)
    flag[~fin] = "MISSING"
    near0 = fin & (np.abs(prev) < DENOM_NEAR_ZERO_TOL)
    flag[near0] = "DENOM_NEAR_ZERO"

    tpos[fin & (cur > 0) & (prev <= 0)] = 1
    tneg[fin & (cur < 0) & (prev >= 0)] = 1
    turn = (tpos == 1) | (tneg == 1)
    flag[turn & fin] = np.where(tpos[turn & fin] == 1, "TURNAROUND_POS", "TURNAROUND_NEG")

    ok = fin & ~near0 & ~turn
    out[ok] = (cur[ok] - prev[ok]) / np.abs(prev[ok])
    return out, tpos, tneg, flag


def twelve_month_forward(fy1: np.ndarray, fy2: np.ndarray, asof: "pd.Timestamp",
                         fy1_periods: Sequence[str], fy_end_months: Sequence[int]) -> np.ndarray:
    """§7.3 — 일수 가중 12개월 선행 EPS. w_current = FY1 결산일까지 잔여일 / 회계연도 일수."""
    n = len(fy1)
    out = np.full(n, np.nan)
    t = pd.Timestamp(asof)
    for i in range(n):
        if not (np.isfinite(fy1[i]) and np.isfinite(fy2[i])):
            continue
        fym = int(fy_end_months[i]) if fy_end_months is not None else 12
        end1 = C.fiscal_period_end(str(fy1_periods[i]), fym)
        if end1 is None:
            continue
        end0 = C.fiscal_period_end(C.fp_year(C.parse_fiscal_period(str(fy1_periods[i]))[0] - 1), fym)
        span = float((end1 - end0).days) if end0 is not None else 365.25
        if span <= 0:
            span = 365.25
        w = float((end1 - t).days) / span
        w = min(max(w, 0.0), 1.0)
        out[i] = w * fy1[i] + (1.0 - w) * fy2[i]
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
#  시점별 팩터 스냅샷
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class FactorEngine:
    est_index: EstimateIndex
    resolver: TargetResolver
    actuals_pit: ActualsPIT
    panel: MarketPanel
    cal: TradingCalendar
    univ: UniverseIndex
    vendor: VendorPIT
    cfg: SCGConfig
    skill_index: Any = None
    twelve_mf_mode: str = "SYNTHETIC"        # "VENDOR" | "SYNTHETIC" — 혼합 금지(§7.3)
    metric: str = "EPS"

    # ── 내부: 한 시점의 컨센서스 묶음 ────────────────────────────────────────────────
    def _consensus_bundle(self, asof: Any, codes: Sequence[str], with_smart: bool
                          ) -> Dict[str, Any]:
        cfg = self.cfg
        tg = self.resolver.resolve(codes, asof)
        snap = self.est_index.latest_snapshot(asof, cfg.active_estimate_window_days)
        if len(snap):
            snap = snap[snap["company_code"].isin(set(map(str, codes)))]
        wanted = pd.concat([
            tg[["company_code", "fq1_period"]].rename(columns={"fq1_period": "fiscal_period"}),
            tg[["company_code", "fy1_period"]].rename(columns={"fy1_period": "fiscal_period"}),
            tg[["company_code", "fy2_period"]].rename(columns={"fy2_period": "fiscal_period"}),
        ], ignore_index=True).drop_duplicates()
        if len(snap):
            snap = snap.merge(wanted, on=["company_code", "fiscal_period"], how="inner")

        gen = general_consensus(snap, self.metric, MIN_ANALYST_COUNT) if len(snap) \
            else general_consensus(None)
        smart = pd.DataFrame()
        audit = pd.DataFrame()
        if with_smart and len(snap) and len(gen):
            fq1_keys = tg[["company_code", "fq1_period"]].rename(
                columns={"fq1_period": "fiscal_period"})
            snap_fq1 = snap.merge(fq1_keys, on=["company_code", "fiscal_period"], how="inner")
            gen_fq1 = gen.merge(fq1_keys, on=["company_code", "fiscal_period"], how="inner")
            skills = self.skill_index.at(asof, cfg) if self.skill_index is not None else pd.DataFrame()
            smart, audit = smart_consensus(snap_fq1, gen_fq1, skills, cfg, self.metric)
        return {"targets": tg, "snap": snap, "general": gen, "smart": smart, "audit": audit}

    def _pick(self, gen: "pd.DataFrame", codes: Sequence[str], periods: Sequence[str],
              col: str = "general_consensus") -> np.ndarray:
        if gen is None or not len(gen):
            return np.full(len(codes), np.nan)
        key = pd.DataFrame({"company_code": list(map(str, codes)),
                            "fiscal_period": list(map(str, periods))})
        m = key.merge(gen[["company_code", "fiscal_period", col]],
                      on=["company_code", "fiscal_period"], how="left")
        return m[col].to_numpy(dtype=float)

    def _eps12mf(self, asof: Any, codes: Sequence[str], bundle: Dict[str, Any]) -> np.ndarray:
        tg = bundle["targets"]
        fy1p = tg["fy1_period"].tolist()
        fy2p = tg["fy2_period"].tolist()
        fym = tg["fy_end_month"].tolist()
        if self.twelve_mf_mode == "VENDOR":
            v1 = self.vendor.get(codes, fy1p, asof, "eps_12mf", self.metric)
            return v1                                  # 벤더 12MF 는 그 자체가 12MF 값
        fy1 = self._pick(bundle["general"], codes, fy1p)
        fy2 = self._pick(bundle["general"], codes, fy2p)
        return twelve_month_forward(fy1, fy2, pd.Timestamp(asof), fy1p, fym)

    def snapshot(self, signal_date: Any) -> Tuple["pd.DataFrame", Dict[str, Any], "pd.DataFrame"]:
        """한 리밸런싱 시점의 (팩터 표, §21 워터폴 행, 스마트 컨센서스 성분 감사표)."""
        cfg = self.cfg
        t = pd.Timestamp(signal_date)

        if cfg.universe == UNIVERSE_PRIMARY:
            codes = self.univ.at(t)
            snap_date = self.univ.snapshot_date(t)
        else:
            codes = covered_universe(self.est_index, self.panel, t,
                                     cfg.active_estimate_window_days, MIN_ANALYST_COUNT)
            snap_date = t
        # 상장 상태 확인 — 유니버스 스냅샷이 오래되었어도 상장폐지 종목을 끌고 가지 않는다
        i = self.panel.row_index(t)
        if i >= 0 and codes:
            keep = [c for c in codes if self.panel.code_pos.get(c) is not None
                    and self.panel.listed[i, self.panel.code_pos[c]]]
            codes = keep
        wf: Dict[str, Any] = {"asof": t, "universe_id": cfg.universe,
                              "universe_snapshot_date": snap_date, "universe_n": len(codes)}
        if not codes:
            return pd.DataFrame(columns=FACTOR_COLUMNS), wf, pd.DataFrame()

        bundle = self._consensus_bundle(t, codes, with_smart=True)
        tg = bundle["targets"].set_index("company_code").reindex(codes).reset_index()
        gen, smart = bundle["general"], bundle["smart"]

        # ── SCG (§6) ─────────────────────────────────────────────────────────────────
        fq1p = tg["fq1_period"].astype(str).tolist()
        if len(gen):
            fq1_keys = pd.DataFrame({"company_code": codes, "fiscal_period": fq1p})
            gen_fq1 = fq1_keys.merge(gen, on=["company_code", "fiscal_period"], how="left")
            gen_fq1["asof"] = t
            gen_fq1["metric"] = self.metric
            gen_fq1["sufficient"] = gen_fq1["sufficient"].fillna(False).astype(bool)
        else:
            gen_fq1 = pd.DataFrame(columns=["asof", "company_code", "fiscal_period", "metric",
                                            "general_consensus", "median", "std", "mad", "min",
                                            "max", "analyst_count", "broker_count",
                                            "estimate_age_median", "sufficient"])

        if self.cfg.is_exact and self.vendor.has_smart:
            #  ★ EXACT 는 벤더 필드만으로 성립해야 한다. 공개 추정치 스냅샷이 비어 있어도
            #    벤더 컨센서스가 있으면 SCG 가 계산되어야 하므로 gen_use 를 독립적으로 만든다.
            #    (공개 진단값 analyst_count/std 등은 참고용으로만 붙인다)
            vg = self.vendor.get(codes, fq1p, t, "general_consensus", self.metric)
            vs = self.vendor.get(codes, fq1p, t, "smart_consensus", self.metric)
            diag_cols = ["company_code", "fiscal_period", "median", "std", "mad", "min", "max",
                         "analyst_count", "broker_count", "estimate_age_median"]
            diag = (gen_fq1[diag_cols] if len(gen_fq1)
                    else pd.DataFrame(columns=diag_cols))
            gen_use = pd.DataFrame({"asof": t, "company_code": codes, "fiscal_period": fq1p,
                                    "metric": self.metric, "general_consensus": vg})
            gen_use = gen_use.merge(diag, on=["company_code", "fiscal_period"], how="left")
            gen_use["sufficient"] = np.isfinite(vg)
            gen_use = gen_use.reindex(columns=list(gen_fq1.columns) if len(gen_fq1.columns)
                                      else gen_use.columns)
            smart_use = pd.DataFrame({"company_code": codes, "fiscal_period": fq1p,
                                      "smart_consensus": vs})
            scg_src = "VENDOR"
        else:
            gen_use = gen_fq1
            smart_use = smart if len(smart) else pd.DataFrame(
                columns=["company_code", "fiscal_period", "smart_consensus"])
            scg_src = "PUBLIC_REPRO"
        scg = smart_gap(gen_use, smart_use)
        scg = pd.DataFrame({"company_code": codes, "fiscal_period": fq1p}).merge(
            scg, on=["company_code", "fiscal_period"], how="left")

        # ── FQ1 / FY1 YoY (§7.1, §7.2) ───────────────────────────────────────────────
        fq1_est = self._pick(gen_use, codes, fq1p)
        fq1_prev = self.actuals_pit.values(codes, tg["fq1_prev_year_period"].astype(str).tolist(),
                                           t, self.metric)
        fq1_yoy, tpos, tneg, fq1_flag = yoy_growth(fq1_est, fq1_prev)

        fy1p = tg["fy1_period"].astype(str).tolist()
        fy1_est = self._pick(gen, codes, fy1p)
        fy1_prev = self.actuals_pit.values(codes, tg["fy_prev_period"].astype(str).tolist(),
                                           t, self.metric)
        fy1_yoy, _, _, fy1_flag = yoy_growth(fy1_est, fy1_prev)

        # ── 12MF 1M 리비전 (§7.3) ────────────────────────────────────────────────────
        e12_t = self._eps12mf(t, codes, bundle)
        t20 = self.cal.shift(t, -REVISION_LOOKBACK_TRADING_DAYS)
        if t20 is not None:
            b20 = self._consensus_bundle(t20, codes, with_smart=False)
            tg20 = b20["targets"].set_index("company_code").reindex(codes).reset_index()
            b20["targets"] = tg20
            e12_t20 = self._eps12mf(t20, codes, b20)
        else:
            e12_t20 = np.full(len(codes), np.nan)
        rev = safe_div(e12_t - e12_t20, np.abs(e12_t20), DENOM_NEAR_ZERO_TOL)

        # ── 수급 (§7.4, §7.5) ────────────────────────────────────────────────────────
        inst_sum, fgn_sum, obs = self.panel.flow_20d(t, codes, 20)
        mcap = self.panel.values_at(self.panel.market_cap, t, codes)
        inst = safe_div(inst_sum, mcap, 1.0)
        fgn = safe_div(fgn_sum, mcap, 1.0)

        # ── 서프라이즈 확률 (§8) ─────────────────────────────────────────────────────
        if self.cfg.is_exact and self.vendor.has_sp:
            sp = self.vendor.get(codes, fq1p, t, "surprise_probability", self.metric)
            sp_src = "VENDOR"
        else:
            sp = np.full(len(codes), np.nan)
            sp_src = "UNAVAILABLE"

        px = self.panel.values_at(self.panel.adj_close, t, codes)
        out = pd.DataFrame({
            "asof": t, "company_code": codes, "universe_id": cfg.universe,
            "universe_snapshot_date": snap_date,
            FACTOR_SCG: scg["SCG_RAW"].to_numpy(dtype=float),
            "SCG_RAW": scg["SCG_RAW"].to_numpy(dtype=float),
            "scg_flag": scg["scg_flag"].fillna("MISSING_CONSENSUS").to_numpy(),
            FACTOR_FQ1: fq1_yoy, "TURNAROUND_POS": tpos, "TURNAROUND_NEG": tneg,
            "fq1_flag": fq1_flag,
            FACTOR_FY1: fy1_yoy, "fy1_flag": fy1_flag,
            FACTOR_REV: rev, "eps12mf_t": e12_t, "eps12mf_t20": e12_t20,
            "twelve_mf_source": self.twelve_mf_mode,
            FACTOR_INST: inst, FACTOR_FGN: fgn,
            "inst_net_20d": inst_sum, "foreign_net_20d": fgn_sum, "flow_obs_20d": obs,
            FACTOR_SP: sp, "surprise_prob_source": sp_src,
            "general_consensus_fq1": gen_use["general_consensus"].to_numpy(dtype=float)
            if len(gen_use) else np.nan,
            "smart_consensus_fq1": scg["smart_consensus"].to_numpy(dtype=float),
            "analyst_count": gen_use["analyst_count"].to_numpy() if len(gen_use) else np.nan,
            "broker_count": gen_use["broker_count"].to_numpy() if len(gen_use) else np.nan,
            "consensus_std": gen_use["std"].to_numpy(dtype=float) if len(gen_use) else np.nan,
            "consensus_mad": gen_use["mad"].to_numpy(dtype=float) if len(gen_use) else np.nan,
            "estimate_age_median": gen_use["estimate_age_median"].to_numpy(dtype=float)
            if len(gen_use) else np.nan,
            "fq1_period": fq1p, "fy1_period": fy1p, "fy2_period": tg["fy2_period"].astype(str),
            "target_source_q": tg["target_source_q"], "target_source_y": tg["target_source_y"],
            "market_cap": mcap, "price_close": px, "listed": True,
            "scg_source": scg_src,
        })

        # ── §21 데이터품질 워터폴 ────────────────────────────────────────────────────
        snap_all = bundle["snap"]
        wf.update({
            "covered_by_estimates_n": int(snap_all["company_code"].nunique()) if len(snap_all) else 0,
            "general_consensus_n": int(np.isfinite(fq1_est).sum()),
            "smart_consensus_n": int(np.isfinite(out["smart_consensus_fq1"].to_numpy(dtype=float)).sum()),
            "scg_n": int(np.isfinite(out[FACTOR_SCG].to_numpy(dtype=float)).sum()),
            "fq1_growth_n": int(np.isfinite(fq1_yoy).sum()),
            "fy1_growth_n": int(np.isfinite(fy1_yoy).sum()),
            "12mf_revision_n": int(np.isfinite(rev).sum()),
            "inst_flow_n": int(np.isfinite(inst).sum()),
            "foreign_flow_n": int(np.isfinite(fgn).sum()),
            "surprise_prob_n": int(np.isfinite(sp).sum()),
        })
        return out.reindex(columns=FACTOR_COLUMNS + ["scg_source"]), wf, bundle["audit"]


def build_factor_snapshots(engine: FactorEngine, signal_dates: Sequence[Any]
                           ) -> Tuple["pd.DataFrame", "pd.DataFrame", "pd.DataFrame"]:
    """(팩터 스냅샷, 워터폴, 스마트 컨센서스 성분 감사표)."""
    frames, waterfall, audits = [], [], []
    for t in signal_dates:
        df, wf, aud = engine.snapshot(t)
        if len(df):
            frames.append(df)
        if aud is not None and len(aud):
            audits.append(aud)
        waterfall.append(wf)
    fac = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FACTOR_COLUMNS)
    wfd = pd.DataFrame(waterfall)
    aud = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()
    return fac, wfd, aud


__all__ = ["FactorEngine", "ActualsPIT", "VendorPIT", "yoy_growth", "twelve_month_forward",
           "build_factor_snapshots", "FACTOR_COLUMNS", "REVISION_LOOKBACK_TRADING_DAYS"]
