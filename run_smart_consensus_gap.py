#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCG_ORIGINAL_REPRO_V1 — 원클릭 실행기 (§24, §26).

    from run_smart_consensus_gap import run
    run()

실행 순서는 명세 §26 을 그대로 따른다:
  0 탐색 → 1 정규화 → 2 PIT → 3 애널리스트 정확도 → 4·5 컨센서스/팩터 → 6 백테스트
  → 7 강건성 → 8 감사·검증 → 산출물

데이터가 없으면? 조용히 그럴듯한 숫자를 만들지 않는다. 두 가지 중 하나로 끝난다:
  · allow_synthetic_fallback=True (기본) → **합성 픽스처 리허설**을 돌려 계산경로와 감사를
    증명하고, 모든 산출물에 synthetic=true 를 박는다. 성과 수치는 성과가 아니라고 명시한다.
  · allow_synthetic_fallback=False      → run_status=NO_DATA 로 즉시 종료.
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from smart_consensus_gap import analyst_skill as SK
from smart_consensus_gap import backtest as BT
from smart_consensus_gap import consensus as CONS
from smart_consensus_gap import contracts as C
from smart_consensus_gap import discover as DISC
from smart_consensus_gap import factors as FX
from smart_consensus_gap import normalize as NORM
from smart_consensus_gap import pit_engine as PIT
from smart_consensus_gap import portfolio as PF
from smart_consensus_gap import reporting as REP
from smart_consensus_gap import robustness as ROB
from smart_consensus_gap import scoring as SC
from smart_consensus_gap import synthetic as SYN
from smart_consensus_gap import validation as VAL
from smart_consensus_gap.config import (FACTORS_5F_NO_SCG, FACTORS_6F, FACTORS_7F, FACTOR_SCG,
                                        MODE_ORIGINAL_EXACT, MODE_PUBLIC_REPRO, SPEC_ID,
                                        STAGE_BUDGET_MINUTES, STRAT_IBK_6F_PUBLIC,
                                        STRAT_IBK_7F_EXACT, STRAT_SCG_SINGLE_RAW,
                                        STRAT_SCG_SINGLE_Z, STRATEGY_FACTORS,
                                        TOTAL_BUDGET_MINUTES, SCGConfig, base_config)
from smart_consensus_gap.util import LOG, Profiler, banner, fmt_table, setup_logging

STATUS_OK = "COMPLETED"
STATUS_FAILED_AUDIT = "FAILED_AUDIT"
STATUS_NO_DATA = "NO_DATA"
STATUS_SYNTHETIC = "SYNTHETIC_REHEARSAL_NO_REAL_DATA"
STATUS_ERROR = "ERROR"


# ════════════════════════════════════════════════════════════════════════════════════════
#  전략 실행 단위
# ════════════════════════════════════════════════════════════════════════════════════════
class Engine:
    """정규화된 원장 위에서 팩터 → 선정 → 백테스트를 반복 실행하는 실행기."""

    def __init__(self, cfg: SCGConfig, tables: Dict[str, "pd.DataFrame"], mode: str) -> None:
        self.cfg = cfg
        self.mode = mode
        self.est = tables["analyst_estimates"]
        self.actuals = tables["actuals"]
        self.prices = tables["prices"]
        self.flows = tables.get("flows")
        self.universe_raw = tables["universe_membership"]
        self.vendor_raw = tables.get("vendor_consensus")
        self.bench_raw = tables.get("benchmark")
        self.fiscal_cal = tables.get("fiscal_calendar")

        self.cal = PIT.TradingCalendar.from_prices(self.prices)
        self.panel = PIT.MarketPanel.build(self.prices, self.flows, self.cal)
        self.est_index = PIT.EstimateIndex.build(self.est)
        self.resolver = PIT.TargetResolver.build(self.actuals, "EPS", self.fiscal_cal)
        self.actuals_pit = FX.ActualsPIT.build(self.actuals)
        self.vendor = FX.VendorPIT.build(self.vendor_raw)
        self.univ = PIT.UniverseIndex.build(self.universe_raw, cfg.universe)
        self.rebal = PIT.rebalance_dates(self.cal, cfg)
        self.snapshot_dates = self._monthly_snapshot_dates()
        self.events = pd.DataFrame()
        self.skill_index: Optional[SK.SkillIndex] = None
        self.twelve_mf_mode = "VENDOR" if (cfg.twelve_mf_source == "VENDOR_IF_AVAILABLE"
                                           and self.vendor.has_12mf) else "SYNTHETIC"
        self.fwd = VAL.ForwardReturns.build(self.panel, self.cal)
        self.benchmark, self.benchmark_kind = BT.benchmark_daily(
            self.bench_raw, self.panel, self.cal,
            {pd.Timestamp(d): self.univ.members.get(i, [])
             for i, d in enumerate(self.univ.dates)} if len(self.univ.dates) else None,
            "KOSPI200")
        self.bench_series = (pd.Series(self.benchmark["bench_ret"].to_numpy(dtype=float),
                                       index=pd.DatetimeIndex(self.benchmark["date"]))
                             if len(self.benchmark) else pd.Series(dtype=float))

    def _monthly_snapshot_dates(self) -> List["pd.Timestamp"]:
        """IC(§15)를 월 단위로 보기 위해 팩터는 **모든 월말**에 만든다.
        리밸런싱(3/6/9/12월)은 그 부분집합이므로 추가 비용 없이 재사용된다."""
        if not len(self.cal.days):
            return []
        lo = max(pd.Timestamp(self.cfg.backtest_start), pd.Timestamp(self.cal.days[0]))
        hi = min(pd.Timestamp(self.cfg.backtest_end), pd.Timestamp(self.cal.days[-1]))
        out = []
        for me in pd.date_range(lo - pd.offsets.MonthEnd(1), hi, freq="ME"):
            d = self.cal.on_or_before(me)
            if d is not None and lo <= d <= hi:
                out.append(d)
        return sorted(set(out))

    # ── 팩터 ────────────────────────────────────────────────────────────────────────
    def factor_engine(self, cfg: SCGConfig) -> FX.FactorEngine:
        return FX.FactorEngine(
            est_index=self.est_index, resolver=self.resolver, actuals_pit=self.actuals_pit,
            panel=self.panel, cal=self.cal, univ=PIT.UniverseIndex.build(self.universe_raw,
                                                                        cfg.universe),
            vendor=self.vendor, cfg=cfg, skill_index=self.skill_index,
            twelve_mf_mode=self.twelve_mf_mode)

    def build_factors(self, cfg: SCGConfig, dates: Optional[Sequence[Any]] = None
                      ) -> Tuple["pd.DataFrame", "pd.DataFrame", "pd.DataFrame"]:
        eng = self.factor_engine(cfg)
        return FX.build_factor_snapshots(eng, list(dates) if dates is not None
                                         else self.snapshot_dates)

    # ── 전략 1회 실행 ───────────────────────────────────────────────────────────────
    def evaluate(self, cfg: SCGConfig, fac: "pd.DataFrame", factors: Sequence[str],
                 strategy: str, score_col: Optional[str] = None,
                 execution: Optional[str] = None, mode: Optional[str] = None) -> Dict[str, Any]:
        mode = mode or self.mode
        rebal_dates = set(pd.to_datetime(self.rebal["signal_date"]))
        f = fac[pd.to_datetime(fac["asof"]).isin(rebal_dates)].copy() if len(fac) else fac
        if not len(f):
            return {"strategy": strategy, "n_rebalances": 0, "empty": True}
        scored = SC.score_all(f, factors, cfg)
        col = score_col or SC.strategy_score_column(strategy, cfg)
        if col not in scored.columns:
            col = "composite"
        selected = SC.rank_and_select(scored, cfg.n_holdings, col)
        holdings = PF.build_holdings(selected, self.rebal, cfg, strategy, mode, col)
        bt = BT.run_backtest(holdings, self.panel, self.cal, cfg, strategy, mode, execution)
        ret = BT.to_series(bt.daily, "ret_net")
        gross = BT.to_series(bt.daily, "ret_gross")
        turn = (pd.Series(bt.rebalances["turnover"].to_numpy(dtype=float))
                if len(bt.rebalances) else pd.Series(dtype=float))
        m = BT.performance_metrics(ret, self.bench_series, turn, f"{strategy}|{cfg.variant_id}|net")
        mg = BT.performance_metrics(gross, self.bench_series, turn, f"{strategy}|gross")
        m.update({"strategy": strategy, "variant_id": cfg.variant_id, "mode": mode,
                  "execution": bt.execution, "cost_basis": "net",
                  "n_rebalances": int(len(bt.rebalances)),
                  "CAGR_gross": mg.get("CAGR", np.nan),
                  "avg_n_holdings": float(bt.daily["n_holdings"].mean()) if len(bt.daily) else np.nan,
                  "avg_cash_weight": float(bt.daily["cash_weight"].mean()) if len(bt.daily) else np.nan,
                  "factors": ",".join(factors)})
        return {**m, "_scored": scored, "_selected": selected, "_holdings": holdings,
                "_bt": bt, "_ret": ret, "_gross": gross}


def _clean(m: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in m.items() if not k.startswith("_")}


# ════════════════════════════════════════════════════════════════════════════════════════
#  메인
# ════════════════════════════════════════════════════════════════════════════════════════
def run(cfg: Optional[SCGConfig] = None, *, mode: Optional[str] = None,
        synthetic: Optional[bool] = None, allow_synthetic_fallback: bool = True,
        data_roots: Sequence[str] = (), run_robustness: Optional[bool] = None,
        run_bootstrap: Optional[bool] = None, output_root: Optional[str] = None,
        **overrides: Any) -> Dict[str, Any]:
    cfg = cfg or base_config()
    if mode:
        cfg = cfg.replace(mode=mode)
    if synthetic is not None:
        cfg = cfg.replace(synthetic=bool(synthetic))
    if data_roots:
        cfg = cfg.replace(data_roots=tuple(data_roots))
    if run_robustness is not None:
        cfg = cfg.replace(run_robustness=bool(run_robustness))
    if run_bootstrap is not None:
        cfg = cfg.replace(run_bootstrap=bool(run_bootstrap))
    if output_root:
        cfg = cfg.replace(output_root=output_root)
    if overrides:
        cfg = cfg.replace(**overrides)

    setup_logging(cfg.out_dir, cfg.log_level)
    prof = Profiler(STAGE_BUDGET_MINUTES, TOTAL_BUDGET_MINUTES)
    out = REP.Outputs(cfg)
    banner(f"{SPEC_ID}  run_id={cfg.run_id}  요청모드={cfg.mode}")
    LOG.info(f"  출력 폴더: {os.path.abspath(cfg.out_dir)}")
    LOG.info("  ※ 이 코드는 원문에 명시된 정의와 재현 가정을 분리해 표기한다. "
             "PUBLIC_REPRO 결과를 벤더 정확 재현이라고 부르지 않는다.")

    try:
        return _run_inner(cfg, prof, out, allow_synthetic_fallback)
    except Exception as e:  # noqa: BLE001
        LOG.error(f"✘ 실행 실패: {type(e).__name__}: {e}")
        for line in traceback.format_exc().splitlines()[-15:]:
            LOG.error("   " + line)
        out.json("manifest", REP.run_manifest(cfg, cfg.mode, STATUS_ERROR,
                                              {"error": f"{type(e).__name__}: {e}"}))
        out.csv("runtime", prof.to_frame())
        return {"status": STATUS_ERROR, "error": str(e), "out_dir": cfg.out_dir}


def _run_inner(cfg: SCGConfig, prof: Profiler, out: REP.Outputs,
               allow_synthetic_fallback: bool) -> Dict[str, Any]:
    # ══ Stage 0 — 탐색 ═══════════════════════════════════════════════════════════════
    with prof.stage("S0_DISCOVERY", "프로젝트/캐시 탐색 · 소스 가용성"):
        src = DISC.discover(cfg, None)
        gaps = DISC.blocking_gaps(src)
        DISC.log_availability(src)

        if gaps:
            if not allow_synthetic_fallback:
                LOG.error(f"  ✘ 필수 테이블 결측 {gaps} — allow_synthetic_fallback=False 이므로 종료")
                out.csv("availability", DISC.availability_frame(src))
                out.json("manifest", REP.run_manifest(cfg, src.resolved_mode, STATUS_NO_DATA,
                                                      {"missing_tables": gaps}))
                out.csv("runtime", prof.to_frame())
                return {"status": STATUS_NO_DATA, "missing": gaps, "out_dir": cfg.out_dir}
            LOG.warning("")
            LOG.warning("  " + "!" * 84)
            LOG.warning(f"  실데이터 필수 테이블이 없다: {gaps}")
            LOG.warning("  → 합성 픽스처 리허설로 전환한다. 계산경로·감사·산출물은 전부 실제로 돌지만,")
            LOG.warning("    나오는 성과 수치는 성과가 아니다(설계자가 심은 신호를 되찾는 것뿐).")
            LOG.warning("  " + "!" * 84)
            LOG.warning("")
            cfg = cfg.replace(synthetic=True)
            out.cfg = cfg
            spec = SYN.SyntheticSpec(seed=cfg.synthetic_seed,
                                     with_vendor=bool(os.environ.get("SCG_SYNTHETIC_VENDOR")))
            src = DISC.discover(cfg, SYN.generate(spec))
            DISC.log_availability(src)
            gaps = DISC.blocking_gaps(src)
            if gaps:
                raise RuntimeError(f"합성 픽스처조차 계약을 만족하지 못했다: {gaps}")
        availability = DISC.availability_frame(src)
        out.csv("availability", availability)
        mode = src.resolved_mode
        exact_possible = src.exact_possible

    # ══ Stage 1 — 정규화 ═════════════════════════════════════════════════════════════
    with prof.stage("S1_NORMALIZE", "애널리스트 식별 · 회계기간 · 단위 · 타임스탬프") as box:
        est, nrep = NORM.normalize_estimates(src.frames["analyst_estimates"])
        NORM.log_normalize_report(nrep)
        tables = {
            "analyst_estimates": est,
            "actuals": NORM.normalize_actuals(src.frames["actuals"]),
            "prices": NORM.normalize_prices(src.frames["prices"]),
            "flows": NORM.normalize_flows(src.frames["flows"]) if src.has("flows") else None,
            "universe_membership": NORM.normalize_universe(src.frames["universe_membership"]),
            "vendor_consensus": NORM.normalize_vendor(src.frames["vendor_consensus"])
            if src.has("vendor_consensus") else None,
            "benchmark": src.frames.get("benchmark"),
            "fiscal_calendar": src.frames.get("fiscal_calendar"),
        }
        box["rows_in"] = int(nrep.rows_in)
        box["rows_out"] = int(nrep.rows_out)
        for k in ("actuals", "prices", "universe_membership"):
            LOG.info(f"  {k}: {len(tables[k]):,}행")

    # ══ Stage 2 — PIT 스냅샷 엔진 ═════════════════════════════════════════════════════
    with prof.stage("S2_PIT_SNAPSHOT", "거래캘린더 · 시장패널 · 추정치 인덱스") as box:
        eng = Engine(cfg, tables, mode)
        LOG.info(f"  거래일 {len(eng.cal.days):,}일 / 종목 {len(eng.panel.codes):,} / "
                 f"추정치 그룹 {eng.est_index.ng:,}")
        LOG.info(f"  리밸런싱 {len(eng.rebal)}회 "
                 f"({str(eng.rebal['signal_date'].min())[:10]} ~ "
                 f"{str(eng.rebal['signal_date'].max())[:10]}), "
                 f"팩터 스냅샷 {len(eng.snapshot_dates)}회(월말)")
        LOG.info(f"  유니버스 {cfg.universe} 스냅샷 {len(eng.univ.dates)}개 / "
                 f"12MF 소스 {eng.twelve_mf_mode} / 벤치마크 {eng.benchmark_kind}")
        box["rows_out"] = len(eng.snapshot_dates)
        if len(eng.rebal) == 0:
            raise RuntimeError("리밸런싱 시점이 0회다 — 백테스트 구간과 가격 데이터 범위를 확인하라")

    # ══ Stage 3 — 애널리스트 정확도 ═══════════════════════════════════════════════════
    with prof.stage("S3_ANALYST_SKILL", "실현 예측오차 원장 → 시점별 skill/bias") as box:
        eng.events = SK.build_realized_errors(tables["analyst_estimates"], tables["actuals"],
                                              "EPS", cfg.active_estimate_window_days)
        eng.skill_index = SK.SkillIndex.build(eng.events, "EPS")
        skills, _ = SK.skill_table(eng.events, eng.snapshot_dates, cfg, "EPS")
        SK.log_skill_summary(eng.events, skills)
        box["rows_out"] = int(len(eng.events))
        out.parquet("skill", skills)

    # ══ Stage 4·5 — 컨센서스 + 팩터 ═══════════════════════════════════════════════════
    with prof.stage("S4_5_CONSENSUS_FACTORS", "일반/스마트 컨센서스 · SCG · 6팩터") as box:
        unit_tests = CONS.scg_formula_unit_tests()
        bad_ut = unit_tests[~unit_tests["passed"].astype(bool)]
        LOG.info(f"  SCG 산식 단위테스트: {len(unit_tests) - len(bad_ut)}/{len(unit_tests)} 통과")
        if len(bad_ut):
            LOG.error(fmt_table(bad_ut))

        fac, waterfall, components = eng.build_factors(cfg)
        box["rows_out"] = int(len(fac))
        LOG.info(f"  팩터 스냅샷 {len(fac):,}행 / 성분 감사표 {len(components):,}행")
        if len(fac):
            avail = {f: float(np.isfinite(fac[f].to_numpy(dtype=float)).mean())
                     for f in FACTORS_7F if f in fac.columns}
            LOG.info("  팩터 가용률: " + ", ".join(f"{k}={v:.1%}" for k, v in avail.items()))

    # ══ Stage 6 — 전략 실행 / 백테스트 ════════════════════════════════════════════════
    with prof.stage("S6_BACKTEST", "4개 전략 + 진단 변형") as box:
        results: Dict[str, Dict[str, Any]] = {}
        perf_rows: List[Dict[str, Any]] = []

        plan: List[Tuple[str, Sequence[str], Optional[str]]] = [
            (STRAT_SCG_SINGLE_RAW, (FACTOR_SCG,), "SCG_RAW"),
            (STRAT_SCG_SINGLE_Z, (FACTOR_SCG,), "composite"),
            (STRAT_IBK_6F_PUBLIC, FACTORS_6F, "composite"),
        ]
        for strat, factors, col in plan:
            r = eng.evaluate(cfg, fac, factors, strat, col)
            results[strat] = r
            perf_rows.append(_clean(r))
            LOG.info(f"  {strat:22s} CAGR={r.get('CAGR', float('nan')):7.2%} "
                     f"MDD={r.get('MDD', float('nan')):7.2%} "
                     f"IR={r.get('information_ratio', float('nan')):6.2f} "
                     f"리밸 {r.get('n_rebalances', 0)}회")

        # ORIGINAL_EXACT — 벤더 필드가 없으면 실행하지 않는다(§2 C, §20, §26-12).
        #  ★ 기본 모드가 PUBLIC_REPRO 라도, 벤더 필드가 실제로 있으면 EXACT 도 **함께** 돌린다.
        #    두 결과는 별도 팩터 프레임에서 나오며 서로 섞이지 않는다(§20 오염 0).
        #    EXACT 프레임은 비용을 고려해 리밸런싱 시점에서만 만든다(IC 는 공개재구성 경로에서 본다).
        fac_exact = None
        if exact_possible:
            exact_cfg = cfg.replace(mode=MODE_ORIGINAL_EXACT, variant_id="EXACT")
            fac_exact, _wf_x, _aud_x = eng.build_factors(
                exact_cfg, list(pd.to_datetime(eng.rebal["signal_date"])))
            r = eng.evaluate(exact_cfg, fac_exact, FACTORS_7F, STRAT_IBK_7F_EXACT, "composite",
                             mode=MODE_ORIGINAL_EXACT)
            results[STRAT_IBK_7F_EXACT] = r
            perf_rows.append(_clean(r))
            exact_skipped = False
            LOG.info(f"  {STRAT_IBK_7F_EXACT:22s} CAGR={r.get('CAGR', float('nan')):7.2%} "
                     f"MDD={r.get('MDD', float('nan')):7.2%} "
                     f"IR={r.get('information_ratio', float('nan')):6.2f} "
                     f"리밸 {r.get('n_rebalances', 0)}회  [벤더 필드 사용]")
        else:
            LOG.warning(f"  {STRAT_IBK_7F_EXACT:22s} SKIPPED_MISSING_VENDOR_FIELDS — "
                        + "; ".join(src.exact_block_reasons))
            perf_rows.append({"strategy": STRAT_IBK_7F_EXACT, "mode": mode,
                              "status": "SKIPPED_MISSING_VENDOR_FIELDS",
                              "note": "; ".join(src.exact_block_reasons)})
            exact_skipped = True

        # 진단용 당일 종가 체결 (§12 — 공식 성과 아님)
        diag = eng.evaluate(cfg, fac, FACTORS_6F, STRAT_IBK_6F_PUBLIC, "composite",
                            execution="SAME_DAY_CLOSE")
        d = _clean(diag)
        d.update({"strategy": STRAT_IBK_6F_PUBLIC + "|DIAGNOSTIC_SAME_DAY_CLOSE",
                  "official": False,
                  "note": "§12 진단용. 공식 no-lookahead 성과로 사용 금지."})
        perf_rows.append(d)
        box["rows_out"] = len(perf_rows)

        official = results[STRAT_IBK_6F_PUBLIC]
        holdings_all = pd.concat([r["_holdings"] for r in results.values()
                                  if isinstance(r.get("_holdings"), pd.DataFrame)],
                                 ignore_index=True)
        candidates_all = pd.concat(
            [r["_selected"].assign(strategy=s) for s, r in results.items()
             if isinstance(r.get("_selected"), pd.DataFrame)], ignore_index=True)

        # §21 워터폴에 완비/선정 수 합류
        sel6 = results[STRAT_IBK_6F_PUBLIC].get("_scored")
        if isinstance(sel6, pd.DataFrame) and len(sel6):
            agg = sel6.groupby("asof", observed=True).agg(
                complete_6f_n=("complete", "sum")).reset_index()
            waterfall = waterfall.merge(agg, on="asof", how="left")
        sels = results[STRAT_IBK_6F_PUBLIC].get("_selected")
        if isinstance(sels, pd.DataFrame) and len(sels):
            agg2 = sels.groupby("asof", observed=True).agg(
                selected_n=("selected", "sum"), candidates_n=("candidates_n", "max")).reset_index()
            waterfall = waterfall.merge(agg2, on="asof", how="left")
        waterfall["complete_7f_n"] = (
            int(np.isfinite(fac["SURPRISE_PROB"].to_numpy(dtype=float)).sum())
            if "SURPRISE_PROB" in fac.columns and mode == MODE_ORIGINAL_EXACT else 0)

    # ══ Stage 7 — 강건성 + 절제 ═══════════════════════════════════════════════════════
    rob = pd.DataFrame()
    ablation = pd.DataFrame()
    with prof.stage("S7_ROBUSTNESS", "§16 사전 정의 변형 · §15 팩터 절제"):
        rebal_dates = list(pd.to_datetime(eng.rebal["signal_date"]))

        def factor_fn(vcfg: SCGConfig) -> "pd.DataFrame":
            f, _, _ = eng.build_factors(vcfg, rebal_dates)
            return f

        def evaluate_fn(vcfg: SCGConfig, f: "pd.DataFrame", strategy: str) -> Dict[str, Any]:
            return _clean(eng.evaluate(vcfg, f, STRATEGY_FACTORS[strategy], strategy))

        def evaluate_factors_fn(vcfg: SCGConfig, f: "pd.DataFrame", factors: Sequence[str],
                                name: str) -> Dict[str, Any]:
            return _clean(eng.evaluate(vcfg, f, factors, name, "composite"))

        if cfg.run_robustness:
            rob = ROB.run_robustness(cfg, STRAT_IBK_6F_PUBLIC, factor_fn, evaluate_fn, fac)
            ROB.log_robustness(rob)
            ablation = ROB.factor_ablation(cfg, fac, evaluate_factors_fn)
            LOG.info(fmt_table(ablation[["spec", "removed", "CAGR", "Sharpe", "information_ratio",
                                         "delta_CAGR_vs_full"]], max_rows=12))
        else:
            LOG.info("  (강건성 생략 — run_robustness=False)")

    # ══ Stage 8 — 감사·검증·해석 ══════════════════════════════════════════════════════
    with prof.stage("S8_AUDIT", "§20 감사 · §15 IC/분위 · §14 표7 대조 · §17 통계"):
        ic = VAL.rank_ic(fac, eng.fwd, FACTOR_SCG, VAL.IC_HORIZONS)
        icsum = VAL.ic_summary(ic)
        LOG.info("  SCG Rank IC:")
        LOG.info(fmt_table(icsum))
        qper, qsum = VAL.quintiles(fac, eng.fwd, FACTOR_SCG, 60)
        if len(qsum):
            LOG.info("  SCG 분위(60일 선행):")
            LOG.info(fmt_table(qsum))
        cond_ic = VAL.conditional_ic(fac, eng.fwd, FACTOR_SCG, 60)
        acc = VAL.smart_vs_general_accuracy(eng.events, components, tables["actuals"])

        ref = VAL.reference_match(official.get("_selected"), fac, cfg.reference_fixture_path,
                                  STRAT_IBK_6F_PUBLIC)
        if STRAT_IBK_7F_EXACT in results:
            ref_x = VAL.reference_match(results[STRAT_IBK_7F_EXACT].get("_selected"), fac_exact,
                                        cfg.reference_fixture_path, STRAT_IBK_7F_EXACT)
            ref = pd.concat([ref, ref_x], ignore_index=True)
        if str(ref["fixture_status"].iloc[0]) != "OK":
            LOG.warning(f"  ⚠ §14 표7 대조 불가: {ref['fixture_status'].iloc[0]} — "
                        f"{cfg.reference_fixture_path} 를 채우면 자동 수행된다.")
        else:
            LOG.info(f"  §14 표7 overlap {int(ref['top30_overlap_count'].iloc[0])}/"
                     f"{int(ref['reference_n'].iloc[0])}")

        ret_net = official.get("_ret", pd.Series(dtype=float))
        excess = (ret_net - eng.bench_series.reindex(ret_net.index)).dropna() \
            if len(ret_net) and len(eng.bench_series) else pd.Series(dtype=float)
        boot = VAL.block_bootstrap_ci(excess, cfg.bootstrap_n, cfg.random_seed) \
            if cfg.run_bootstrap else {}
        evrm = VAL.event_removal_sensitivity(ret_net)

        ctxa = VAL.AuditContext(
            cfg=cfg, mode=mode, est=tables["analyst_estimates"], events=eng.events,
            audits=components, fac=fac, holdings=holdings_all,
            selected=official.get("_selected"), universe_raw=tables["universe_membership"],
            fac_exact=fac_exact,
            signal_dates=list(pd.to_datetime(eng.rebal["signal_date"])),
            exact_block_reasons=src.exact_block_reasons, exact_skipped=exact_skipped,
            benchmark_kind=eng.benchmark_kind, unit_tests=unit_tests,
            backtest_flags=official.get("_bt").flags if official.get("_bt") else {})
        checks = VAL.audit_checks(ctxa)
        VAL.log_audit(checks)
        audit_ok, failed = VAL.audit_verdict(checks)

    # ══ 산출물 ═══════════════════════════════════════════════════════════════════════
    status = STATUS_OK
    if not audit_ok:
        status = STATUS_FAILED_AUDIT
    elif cfg.synthetic:
        status = STATUS_SYNTHETIC

    perf = pd.DataFrame(perf_rows)
    if not audit_ok:
        LOG.error("  ✘ CRITICAL 감사 실패 → 공식 성과표를 생성하지 않는다(§20).")
        perf_out = pd.DataFrame([{"run_status": STATUS_FAILED_AUDIT,
                                  "failed_checks": ";".join(failed),
                                  "note": "§20 에 따라 공식 성과 산출을 차단했다."}])
    else:
        perf_out = perf

    yearly = BT.yearly_returns(ret_net, eng.bench_series)
    monthly = BT.monthly_returns(ret_net, eng.bench_series)

    out.csv("waterfall", waterfall)
    out.parquet("components", components)
    out.parquet("factors", fac)
    out.csv("candidates", candidates_all)
    out.csv("holdings", holdings_all)
    out.csv("performance", perf_out)
    out.csv("yearly", yearly)
    out.csv("monthly", monthly)
    out.csv("reference", ref)
    out.csv("audit", checks)
    out.csv("rank_ic", pd.concat([ic, icsum.assign(asof="SUMMARY")], ignore_index=True)
            if len(ic) else icsum)
    out.csv("quintiles", pd.concat([qper, qsum.assign(asof="SUMMARY")], ignore_index=True)
            if len(qper) else qsum)
    out.csv("robustness", rob)
    out.csv("ablation", ablation)
    out.csv("runtime", prof.to_frame())

    interp = REP.build_interpretation(cfg, mode, status, {
        "ic_summary": icsum, "quintile_summary": qsum, "ablation": ablation, "performance": perf,
        "reference": ref, "audit": checks, "waterfall": waterfall, "smart_vs_general": acc,
        "bootstrap": boot, "event_removal": evrm, "conditional_ic": cond_ic, "robustness": rob,
        "yearly": yearly, "exact_block_reasons": list(src.exact_block_reasons),
    })
    out.text("interpretation", interp)

    runtime = prof.to_frame()
    over = runtime[runtime["over_budget"].astype(bool)]
    out.json("manifest", REP.run_manifest(cfg, mode, status, {
        "exact_possible": bool(exact_possible),
        "exact_block_reasons": list(src.exact_block_reasons),
        "strategies_run": sorted(results),
        "strategy_skipped": [STRAT_IBK_7F_EXACT] if exact_skipped else [],
        "twelve_mf_source": eng.twelve_mf_mode,
        "exact_factor_rows": int(len(fac_exact)) if fac_exact is not None else 0,
        "benchmark_kind": eng.benchmark_kind,
        "n_rebalances": int(len(eng.rebal)),
        "n_factor_snapshots": int(len(eng.snapshot_dates)),
        "backtest_range": [str(eng.rebal["signal_date"].min())[:10],
                           str(eng.rebal["signal_date"].max())[:10]],
        "audit_critical_failed": failed,
        "runtime_seconds": round(prof.elapsed, 1),
        "runtime_over_budget_stages": over["stage"].tolist(),
        "outputs": {k: os.path.basename(v) for k, v in out.written.items()},
    }))

    banner(f"완료  status={status}  경과 {prof.elapsed/60:.1f}분 / 예산 {TOTAL_BUDGET_MINUTES:.0f}분")
    LOG.info(fmt_table(runtime, max_rows=20, floatfmt="{:,.2f}"))
    if prof.elapsed > cfg.max_full_runtime_seconds:
        LOG.warning(f"  ⚠ 총 실행시간이 {cfg.max_full_runtime_seconds/3600:.1f}시간 예산을 넘었다. "
                    "정의를 줄이지 말고 구현을 최적화하라(§19).")
    LOG.info(f"  산출물 {len(out.written)}개 → {os.path.abspath(cfg.out_dir)}")
    LOG.info(f"  해석: {REP.FILES['interpretation']} — 성과보다 재현도/신뢰도를 먼저 읽을 것")

    return {"status": status, "mode": mode, "out_dir": cfg.out_dir, "cfg": cfg,
            "performance": perf, "audit": checks, "interpretation": interp,
            "factors": fac, "holdings": holdings_all, "robustness": rob, "ablation": ablation,
            "ic": icsum, "quintiles": qsum, "reference": ref, "runtime": runtime}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=f"{SPEC_ID} 실행기")
    ap.add_argument("--mode", default=None, choices=[MODE_PUBLIC_REPRO, MODE_ORIGINAL_EXACT, "AUTO"])
    ap.add_argument("--data-root", action="append", default=[])
    ap.add_argument("--synthetic", action="store_true", help="합성 픽스처 리허설을 강제한다")
    ap.add_argument("--no-synthetic-fallback", action="store_true",
                    help="실데이터가 없으면 합성으로 넘어가지 말고 NO_DATA 로 종료")
    ap.add_argument("--no-robustness", action="store_true")
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--output-root", default=None)
    a = ap.parse_args()
    res = run(mode=a.mode, synthetic=True if a.synthetic else None,
              allow_synthetic_fallback=not a.no_synthetic_fallback,
              data_roots=a.data_root, run_robustness=not a.no_robustness,
              run_bootstrap=not a.no_bootstrap, output_root=a.output_root)
    sys.exit(0 if res.get("status") in (STATUS_OK, STATUS_SYNTHETIC) else 1)
