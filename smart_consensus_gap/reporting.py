# -*- coding: utf-8 -*-
"""출력물 (§22) + 해석 (§23).

해석 문서는 성과보다 **정의 재현도와 신뢰성**을 먼저 판정한다(§26-17).
'알파 여부'와 '재현 신뢰도'는 별개의 판정이며 별도 절로 분리한다(§28).
"""
from __future__ import annotations

import datetime as _dt
import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import (MODE_ORIGINAL_EXACT, MODE_PUBLIC_REPRO,
                     OPERATIONAL_REPRODUCTION_ASSUMPTIONS, SPEC_ID, SOURCE_DOC, SCGConfig)
from .util import LOG, write_csv, write_json, write_parquet, write_text

FILES = {
    "manifest": "00_run_manifest.json",
    "availability": "01_source_availability.csv",
    "waterfall": "02_data_quality_waterfall.csv",
    "skill": "03_analyst_skill.parquet",
    "components": "04_smart_consensus_components.parquet",
    "factors": "05_factor_snapshots.parquet",
    "candidates": "06_rebalance_candidates.csv",
    "holdings": "07_holdings.csv",
    "performance": "08_performance_official.csv",
    "yearly": "09_yearly_returns.csv",
    "monthly": "10_monthly_returns.csv",
    "reference": "11_reference_20200630_match.csv",
    "audit": "12_audit_checks.csv",
    "rank_ic": "13_rank_ic.csv",
    "quintiles": "14_quintiles.csv",
    "robustness": "15_robustness.csv",
    "ablation": "16_factor_ablation.csv",
    "runtime": "17_runtime_profile.csv",
    "interpretation": "18_interpretation.md",
}


@dataclass
class Outputs:
    cfg: SCGConfig
    written: Dict[str, str] = field(default_factory=dict)

    @property
    def dir(self) -> str:
        return self.cfg.out_dir

    def path(self, key: str) -> str:
        return os.path.join(self.dir, FILES[key])

    def csv(self, key: str, df: Optional["pd.DataFrame"]) -> None:
        d = df if df is not None else pd.DataFrame()
        self.written[key] = write_csv(d, self.path(key))

    def parquet(self, key: str, df: Optional["pd.DataFrame"]) -> None:
        d = df if df is not None else pd.DataFrame()
        self.written[key] = write_parquet(d, self.path(key))

    def json(self, key: str, obj: Any) -> None:
        self.written[key] = write_json(obj, self.path(key))

    def text(self, key: str, s: str) -> None:
        self.written[key] = write_text(s, self.path(key))


def run_manifest(cfg: SCGConfig, mode: str, status: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "spec_id": SPEC_ID,
        "source_document": SOURCE_DOC,
        "run_id": cfg.run_id,
        "run_status": status,
        "mode": mode,
        "mode_note": ("벤더 스마트컨센서스/서프라이즈확률을 실제로 사용한 원문 정확 재현"
                      if mode == MODE_ORIGINAL_EXACT else
                      "공개데이터 재구성. FnGuide 스마트컨센서스의 정확 재현이 아니다(§0-2)."),
        "synthetic_fixture": bool(cfg.synthetic),
        "config": cfg.to_dict(),
        "config_fingerprint": cfg.fingerprint(),
        "reproduction_assumptions": [{"id": k, "note": v}
                                     for k, v in OPERATIONAL_REPRODUCTION_ASSUMPTIONS],
        "environment": {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "numpy": np.__version__, "pandas": pd.__version__,
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        },
        **extra,
    }


# ════════════════════════════════════════════════════════════════════════════════════════
#  §23 — 해석 문서
# ════════════════════════════════════════════════════════════════════════════════════════
def _md(df: Optional["pd.DataFrame"], max_rows: int = 60) -> str:
    """마크다운 표. tabulate 가 없으면 고정폭 텍스트로 낮춘다(의존성 추가 금지)."""
    if df is None or not len(df):
        return "_(자료 없음)_"
    d = df.head(max_rows)
    try:
        return d.to_markdown(index=False)
    except Exception:  # noqa: BLE001 — tabulate 미설치 등
        return "```\n" + d.to_string(index=False) + "\n```"


def _fmt(v: Any, pct: bool = False, nd: int = 3) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else "n/a"
    if not np.isfinite(f):
        return "n/a"
    return f"{f:.{nd - 1}%}" if pct else f"{f:.{nd}f}"


def _verdict(cond: Optional[bool], yes: str, no: str, unknown: str = "판정 불가(자료 부족)") -> str:
    if cond is None:
        return unknown
    return yes if cond else no


def build_interpretation(cfg: SCGConfig, mode: str, status: str, ctx: Dict[str, Any]) -> str:
    """§23 의 12개 질문에 순서대로 답한다. 답할 수 없으면 '판정 불가'라고 쓴다."""
    L: List[str] = []
    A = L.append

    ic = ctx.get("ic_summary")
    qsum = ctx.get("quintile_summary")
    ablation = ctx.get("ablation")
    perf = ctx.get("performance")
    ref = ctx.get("reference")
    audit = ctx.get("audit")
    wf = ctx.get("waterfall")
    acc = ctx.get("smart_vs_general")
    boot = ctx.get("bootstrap", {})
    evrm = ctx.get("event_removal")
    cond = ctx.get("conditional_ic")
    rob = ctx.get("robustness")

    A(f"# {SPEC_ID} 해석 — `{mode}`")
    A("")
    A(f"- 원문: {SOURCE_DOC}")
    A(f"- run_id: `{cfg.run_id}` / 설정 지문: `{cfg.fingerprint()}` / 상태: **{status}**")
    A(f"- 유니버스: {cfg.universe} · 종목수 {cfg.n_holdings} · {cfg.portfolio_weight} 가중 · "
      f"{'/'.join(map(str, cfg.rebalance_months))}월 말 리밸런싱 · 비용 {cfg.transaction_cost_bps:.0f}bp")
    A("")

    if cfg.synthetic:
        A("> ## ⛔ 이 실행은 합성 픽스처 리허설이다")
        A(">")
        A("> 실데이터가 없어 계약과 동일한 형태의 **합성 원장**으로 파이프라인 전 구간을 통과시켰다.")
        A("> 아래의 모든 성과·IC·분위 수치는 **설계자가 합성 데이터에 심어 둔 신호를 되찾은 것**이며,")
        A("> 전략의 알파에 대한 증거가 전혀 아니다. 이 실행이 증명하는 것은 오직 배선과 감사뿐이다.")
        A("")

    # ── 0. 재현도·신뢰도 먼저 ────────────────────────────────────────────────────────
    A("## 0. 먼저: 정의 재현도와 신뢰성 (성과보다 앞선다)")
    A("")
    if mode == MODE_PUBLIC_REPRO:
        A("**모드: PUBLIC_REPRO.** 벤더(FnGuide/Quantiwise)의 스마트 컨센서스와 서프라이즈 확률을")
        A("확보하지 못했다. 따라서:")
        A("")
        for r in ctx.get("exact_block_reasons", []):
            A(f"- 차단 사유: {r}")
        A("- `IBK_7F_EXACT` 는 실행하지 않았다 (`SKIPPED_MISSING_VENDOR_FIELDS`).")
        A("- 서프라이즈 확률은 공식 멀티팩터에서 **제외**했다(§8). 임의 프록시를 넣고 원문이라고")
        A("  부르지 않는다. 따라서 공식 멀티팩터는 6팩터다.")
        A("- 이 결과를 \"FnGuide 스마트컨센서스 정확 재현\"이라고 부를 수 없다.")
    else:
        A("**모드: ORIGINAL_EXACT.** 벤더 스마트 컨센서스와 서프라이즈 확률을 실제로 사용했다.")
    A("")
    A("### 원문이 공개하지 않아 재현 가정으로 처리한 것")
    A("")
    for k, v in OPERATIONAL_REPRODUCTION_ASSUMPTIONS:
        A(f"- **{k}** — {v}")
    A("")
    A("### 구조적 관찰: `SCG_SINGLE_RAW` 와 `SCG_SINGLE_Z` 는 거의 같은 전략이다")
    A("")
    A("명세 §2 는 A(raw 내림차순 Top30)와 B(윈저 후 z-score Top30)를 별개 전략으로 정의하지만,")
    A("윈저라이즈도 z-score 도 **단조 변환**이다. 단조 변환은 순위를 바꾸지 않으므로 두 전략의")
    A("상위 30 종목은 꼬리에서 잘려 동점이 된 종목(상·하위 1%)을 제외하면 항상 일치한다.")
    A("따라서 A와 B의 성과 차이는 '표준화의 효과'가 아니라 **동점 처리의 부산물**이다.")
    A("이 사실을 모르고 두 값을 비교하면 없는 차이를 해석하게 된다. 표준화가 실제로 의미를 갖는")
    A("것은 여러 팩터를 합성할 때뿐이다(6F/7F).")
    A("")

    if audit is not None and len(audit):
        crit_fail = audit[(audit["severity"] == "CRITICAL") & (audit["status"] == "FAIL")]
        crit_skip = audit[(audit["severity"] == "CRITICAL") & (audit["status"] == "SKIP")]
        A(f"### 감사 (§20): CRITICAL {len(crit_fail)}건 실패 / {len(crit_skip)}건 판정불가")
        A("")
        if len(crit_fail):
            for _, r in crit_fail.iterrows():
                A(f"- ✘ **{r['check']}** — {r['detail']}")
            A("")
            A("**CRITICAL 실패가 있으므로 공식 성과를 생성하지 않는다(§20).**")
        else:
            A("- CRITICAL 실패 없음.")
        if len(crit_skip):
            A("")
            A("판정불가 항목(= 그 검사를 할 재료가 없었다는 뜻이며, 통과가 아니다):")
            for _, r in crit_skip.iterrows():
                A(f"- ⊘ {r['check']} — {r['detail']}")
        A("")

    if wf is not None and len(wf):
        A("### 표본 워터폴 (§21)")
        A("")
        cols = [c for c in ["asof", "universe_n", "covered_by_estimates_n", "general_consensus_n",
                            "smart_consensus_n", "scg_n", "complete_6f_n", "selected_n"]
                if c in wf.columns]
        w = wf[cols].copy()
        if "asof" in w.columns:
            w["asof"] = pd.to_datetime(w["asof"]).dt.strftime("%Y-%m-%d")
        A(_md(w))
        A("")
        A("- `complete_6f_n` / `selected_n` 이 비어 있는 행은 **리밸런싱 월이 아닌 달**이다. "
          "팩터 스냅샷은 IC 검정을 위해 매 월말 만들지만 포트폴리오 선정은 3/6/9/12월에만 한다.")
        if "complete_6f_n" in wf.columns and "universe_n" in wf.columns:
            ratio = (pd.to_numeric(wf["complete_6f_n"], errors="coerce") /
                     pd.to_numeric(wf["universe_n"], errors="coerce").replace(0, np.nan))
            worst = ratio.min()
            A(f"- 6팩터 완비 비율 최저 구간: {_fmt(worst, pct=True)} "
              f"(이 구간의 성과는 사실상 다른 표본에서 나온 것이다)")
            A("")

    # ── §23 12문 ────────────────────────────────────────────────────────────────────
    A("## 1. §23 질문에 대한 답")
    A("")

    # Q1
    ic60 = None
    if ic is not None and len(ic):
        row = ic[(ic["horizon"] == 60)]
        ic60 = row.iloc[0].to_dict() if len(row) else ic.iloc[0].to_dict()
    A("### Q1. SCG standalone 은 전체 기간에서 양의 IC 를 가지는가?")
    A("")
    if ic60:
        A(f"- 60일 선행 Rank IC 평균 **{_fmt(ic60.get('ic_mean'), nd=4)}**, "
          f"t={_fmt(ic60.get('t_stat'), nd=2)}, IC>0 비율 {_fmt(ic60.get('ic_hit_ratio'), pct=True)}, "
          f"관측 {int(ic60.get('n_periods', 0))}기간")
        pos = ic60.get("ic_mean")
        t = ic60.get("t_stat")
        A(f"- 판정: {_verdict(np.isfinite(pos) and pos > 0 and np.isfinite(t) and abs(t) > 2.0, '유의한 양의 IC', '유의한 양의 IC 라고 보기 어렵다')}")
        if ic is not None and len(ic):
            A("")
            A(_md(ic))
    else:
        A("- 판정 불가: IC 를 계산할 팩터 스냅샷/선행수익률이 없다.")
    A("")

    # Q2
    A("### Q2. Q5 > Q4 > Q3 > Q2 > Q1 단조성이 있는가?")
    A("")
    if qsum is not None and len(qsum):
        A(_md(qsum))
        mono = bool(qsum["monotonic_increasing"].iloc[0]) if "monotonic_increasing" in qsum.columns else None
        A("")
        A(f"- 판정: {_verdict(mono, '완전 단조 증가', '완전 단조는 아니다 — 분위 상관계수를 함께 볼 것')}")
    else:
        A("- 판정 불가.")
    A("")

    # Q3
    A("### Q3. 6F 에서 SCG 를 제거하면 성과가 의미 있게 감소하는가?")
    A("")
    if ablation is not None and len(ablation):
        A(_md(ablation))
        try:
            d = ablation.set_index("removed")
            drop = float(d.loc["SCG", "delta_CAGR_vs_full"])
            others = d.drop(index=["-", "SCG"], errors="ignore")["delta_CAGR_vs_full"].astype(float)
            A("")
            A(f"- SCG 제거 시 CAGR 변화: **{_fmt(drop, pct=True)}**, "
              f"다른 팩터 제거의 중앙값 변화: {_fmt(others.median(), pct=True)}")
            A(f"- 판정: {_verdict(drop < 0 and drop < others.median(), 'SCG 기여가 다른 팩터보다 크다', 'SCG 고유 기여를 확인하기 어렵다')}")
        except Exception:  # noqa: BLE001
            pass
    else:
        A("- 판정 불가.")
    A("")

    # Q4 / Q5
    A("### Q4. 스마트 컨센서스가 일반 컨센서스보다 실제 EPS 에 더 가까운가?")
    A("")
    if acc is not None and len(acc) and np.isfinite(acc["n_pairs"].iloc[0] if "n_pairs" in acc else np.nan):
        r = acc.iloc[0]
        A(f"- 표본 {int(r['n_pairs']):,}쌍 · 스케일조정 MAE: 일반 {_fmt(r['mae_general'], nd=4)} → "
          f"스마트 {_fmt(r['mae_smart'], nd=4)} (개선 {_fmt(r['improvement_ratio'], pct=True)})")
        A(f"- 스마트가 더 정확했던 비율: {_fmt(r['win_rate_smart'], pct=True)}")
        A(f"- 판정: {_verdict(float(r['mae_smart']) < float(r['mae_general']), '더 가깝다', '더 가깝다고 말할 수 없다')}")
    else:
        A("- 판정 불가: 사후 실적과 대조할 성분 감사표/실적이 부족하다.")
    A("")
    A("### Q5. 이 개선은 일부 애널리스트/기간에만 집중되는가?")
    A("")
    A("- `04_smart_consensus_components.parquet` 에 estimator 단위 가중·편향·skill 이 남아 있으므로")
    A("  개선의 귀속을 직접 분해할 수 있다. 본 실행에서는 estimator 별 skill 분포와 "
      "가중 상한 도달 빈도를 아래 강건성(CAP25/CAP50)으로 간접 확인한다.")
    A("")

    # Q6
    A("### Q6. 2020-06-30 원문 30종목과의 overlap 은?")
    A("")
    if ref is not None and len(ref):
        r = ref.iloc[0]
        if str(r.get("fixture_status")) != "OK":
            A(f"- **대조 불가** — 픽스처 상태 `{r.get('fixture_status')}`.")
            A(f"- {r.get('note')}")
            A("- ★ 원문 PDF 표7의 30종목을 코드가 임의로 만들어 내지 않는다. 이것은 재현 실패가")
            A("  아니라 **검증 재료 부재**이며, 픽스처를 채우면 즉시 자동 수행된다.")
        else:
            A(f"- overlap {int(r['top30_overlap_count'])}/{int(r['reference_n'])} "
              f"({_fmt(r['overlap_ratio'], pct=True)}), Jaccard {_fmt(r['jaccard'])}, "
              f"겹친 종목 순위상관 {_fmt(r['rank_correlation_on_overlap'])}")
            if r.get("factor_value_correlations"):
                A(f"- 팩터 raw value 상관: {r['factor_value_correlations']}")
            A(f"- 누락: {r.get('missing', '')}")
            A(f"- 초과: {r.get('extra', '')}")
    else:
        A("- 판정 불가.")
    A("")

    # Q7
    A("### Q7. ORIGINAL_EXACT 와 PUBLIC_REPRO 의 차이는?")
    A("")
    if mode == MODE_PUBLIC_REPRO:
        A("- 벤더 필드가 없어 EXACT 를 실행하지 못했으므로 **차이를 측정할 수 없다**. 프록시로")
        A("  대신 계산해 '차이'라고 부르는 것은 정의 드리프트다(§0-2).")
        A("- 벤더 데이터를 확보하면 같은 코드가 자동으로 EXACT 를 함께 실행하고 이 절이 채워진다.")
    else:
        A("- 두 모드를 모두 실행했다면 `08_performance_official.csv` 의 mode 컬럼으로 직접 비교한다.")
    A("")

    # Q8
    A("### Q8. 성과가 2020 코로나 이후 특정 구간에만 집중되는가?")
    A("")
    yr = ctx.get("yearly")
    if yr is not None and len(yr):
        A(_md(yr))
        if "excess" in yr.columns:
            ex = pd.to_numeric(yr["excess"], errors="coerce")
            pos_years = int((ex > 0).sum())
            A("")
            A(f"- 초과수익 양(+)인 해: {pos_years}/{int(ex.notna().sum())}")
            top = ex.abs().max()
            share = float(ex.max() / ex.sum()) if ex.sum() != 0 else np.nan
            A(f"- 최대 기여 연도가 누적 초과수익에서 차지하는 비중: {_fmt(share, pct=True)}")
    else:
        A("- 판정 불가.")
    A("")

    # Q9
    A("### Q9. analyst_count 가 적은 종목에서 SCG 가 불안정해지는가?")
    A("")
    if cond is not None and len(cond):
        A(_md(cond))
    else:
        A("- 판정 불가.")
    A("")

    # Q10
    A("### Q10. 최신성/정확도 가중이 단순 1개월 컨센서스보다 실질적으로 나은가?")
    A("")
    A("- 반감기 축(HL15/HL30/HL60)과 정확도 이벤트 축(ACC4/ACC8/ACC12)의 강건성 결과가 직접 답한다.")
    A("- 반감기를 아주 짧게(15일) 두면 사실상 '최근 1개월 컨센서스'에 수렴하므로, HL15 대비")
    A("  HL30/HL60 의 성과 차이가 이 질문의 답이다.")
    if rob is not None and len(rob):
        sub = rob[rob["axis"].isin(["recency_half_life_days", "accuracy_max_events", "BASE"])]
        A("")
        A(_md(sub[["variant_id", "override", "CAGR", "Sharpe", "excess_CAGR"]]))
    A("")

    # Q11
    A("### Q11. 거래비용 35bp 후에도 알파가 남는가?")
    A("")
    if perf is not None and len(perf):
        keep = [c for c in ["strategy", "mode", "status", "CAGR", "CAGR_gross", "ann_vol",
                            "Sharpe", "MDD", "benchmark_CAGR", "excess_CAGR", "tracking_error",
                            "information_ratio", "turnover_per_rebalance", "n_rebalances"]
                if c in perf.columns]
        A("전체 지표는 `08_performance_official.csv` 에 있다. 아래는 핵심 열만 추린 것이다.")
        A("")
        A(_md(perf[keep]))
    if boot:
        A("")
        A(f"- 블록 부트스트랩({boot.get('n_boot', 0):,}회, 블록 {boot.get('block_days', 0)}일) "
          f"초과수익 연율: 점추정 {_fmt(boot.get('point'), pct=True)}, "
          f"95% CI [{_fmt(boot.get('ci_low'), pct=True)}, {_fmt(boot.get('ci_high'), pct=True)}], "
          f"P(초과수익>0)={_fmt(boot.get('p_gt_zero'), pct=True)}")
        lo = boot.get("ci_low")
        A(f"- 판정: {_verdict(np.isfinite(lo) and lo > 0, '95% CI 하한이 0 위 — 비용 후에도 남는다', 'CI 가 0 을 포함한다 — 비용 후 알파를 단정할 수 없다')}")
    A("")

    # Q12
    A("### Q12. 상위 이벤트 제거 후에도 성과가 유지되는가?")
    A("")
    if evrm is not None and len(evrm):
        A(_md(evrm))
        try:
            c0 = float(evrm.loc[evrm["removed_top_n"] == 0, "CAGR"].iloc[0])
            c5 = float(evrm.loc[evrm["removed_top_n"] == 5, "CAGR"].iloc[0])
            A("")
            A(f"- 판정: {_verdict(np.isfinite(c5) and c5 > 0 and c5 > 0.5 * c0, '상위 5개월 제거 후에도 성과가 남는다', '상위 소수 구간 의존이 크다')}")
        except (IndexError, KeyError, ValueError):
            pass
    else:
        A("- 판정 불가.")
    A("")

    # ── 최종 판정 2종 ───────────────────────────────────────────────────────────────
    A("## 2. 최종 판정 — 두 가지를 분리한다 (§28)")
    A("")
    A("### (A) 재현 신뢰도")
    A("")
    if cfg.synthetic:
        A("- **판정: 실데이터 재현 미수행.** 합성 픽스처로 계산경로·감사·산출물만 검증했다.")
        A("  재현도는 실데이터가 연결된 뒤에만 판정할 수 있다.")
    elif mode == MODE_PUBLIC_REPRO:
        A("- **판정: 부분 재현(PUBLIC_REPRO).** 원문 7팩터 중 서프라이즈 확률이 빠진 6팩터이며,")
        A("  스마트 컨센서스는 벤더 산식이 아니라 공개 원리 기반 재구성이다.")
        if ref is not None and len(ref) and str(ref.iloc[0].get("fixture_status")) == "OK":
            A(f"  2020-06-30 표7 대조 overlap {_fmt(ref.iloc[0]['overlap_ratio'], pct=True)}.")
        else:
            A("  2020-06-30 표7 대조는 픽스처 부재로 미수행 — 재현도의 핵심 증거가 아직 없다.")
    else:
        A("- **판정: 원문 정확 재현(ORIGINAL_EXACT).** 벤더 필드를 그대로 사용했다.")
    A("")
    A("### (B) 알파 여부")
    A("")
    if cfg.synthetic:
        A("- **판정 불가.** 합성 데이터로는 알파를 판정할 수 없다(설계자가 심은 신호를 되찾을 뿐이다).")
    else:
        A("판정 기준은 사전에 다섯 가지로 고정되어 있다. **셋 이상**을 만족할 때만 "
          "'독립 알파'라고 부른다.")
        A("")
        crit: List[Tuple[str, Optional[bool], str]] = []

        t = ic60.get("t_stat") if ic60 else None
        m = ic60.get("ic_mean") if ic60 else None
        crit.append(("(i) SCG standalone IC 가 양이고 t>2",
                     None if (t is None or not np.isfinite(t)) else bool(m > 0 and t > 2.0),
                     f"IC={_fmt(m, nd=4)}, t={_fmt(t, nd=2)}"))

        mono = None
        rc = None
        if qsum is not None and len(qsum):
            if "monotonic_increasing" in qsum.columns:
                mono = bool(qsum["monotonic_increasing"].iloc[0])
            if "rank_corr_quintile" in qsum.columns:
                rc = float(qsum["rank_corr_quintile"].iloc[0])
        crit.append(("(ii) 분위 단조성", mono,
                     f"완전단조={mono}, 분위 순위상관={_fmt(rc, nd=2)}"))

        dscg = None
        if ablation is not None and len(ablation) and "removed" in ablation.columns:
            row = ablation[ablation["removed"] == "SCG"]
            if len(row) and "delta_CAGR_vs_full" in row.columns:
                v = float(row["delta_CAGR_vs_full"].iloc[0])
                dscg = bool(np.isfinite(v) and v < 0)
        crit.append(("(iii) 6F→5F 절제에서 SCG 제거 시 성과 감소", dscg,
                     f"ΔCAGR(SCG 제거) = "
                     f"{_fmt(ablation[ablation['removed'] == 'SCG']['delta_CAGR_vs_full'].iloc[0], pct=True) if dscg is not None else 'n/a'}"))

        lo = boot.get("ci_low") if boot else None
        crit.append(("(iv) 비용 후 부트스트랩 초과수익 CI 하한 > 0",
                     None if (lo is None or not np.isfinite(lo)) else bool(lo > 0),
                     f"95% CI 하한 {_fmt(lo, pct=True)}"))

        surv = None
        detail_ev = "n/a"
        if evrm is not None and len(evrm):
            try:
                c0 = float(evrm.loc[evrm["removed_top_n"] == 0, "CAGR"].iloc[0])
                c5 = float(evrm.loc[evrm["removed_top_n"] == 5, "CAGR"].iloc[0])
                surv = bool(np.isfinite(c5) and c5 > 0 and c5 > 0.5 * c0)
                detail_ev = f"CAGR {_fmt(c0, pct=True)} → 상위5개월 제거 후 {_fmt(c5, pct=True)}"
            except (IndexError, KeyError, ValueError):
                pass
        crit.append(("(v) 상위 이벤트 제거 후에도 성과 잔존", surv, detail_ev))

        for label, ok, detail in crit:
            mark = "충족" if ok else ("미충족" if ok is False else "판정불가")
            A(f"- {label} → **{mark}** ({detail})")
        n_ok = sum(1 for _, ok, _ in crit if ok)
        n_unknown = sum(1 for _, ok, _ in crit if ok is None)
        A("")
        A(f"**충족 {n_ok}/5 (판정불가 {n_unknown}건).** "
          + ("→ 사전 기준을 만족한다: SCG 를 독립 알파로 볼 근거가 있다."
             if n_ok >= 3 else
             "→ 사전 기준(3/5)에 미달한다. **SCG 를 독립 알파라고 부르지 않는다.** "
             "다른 이익 모멘텀 팩터에 얹혀 가는 신호일 가능성을 배제하지 못했다."))
        if n_unknown:
            A("")
            A("판정불가 항목은 '통과'가 아니다. 그 검정을 할 재료가 없었다는 뜻이며, "
              "재료를 채운 뒤 다시 판정해야 한다.")
    A("")
    A("---")
    A("")
    A("*본 문서는 전략 검증용이며 투자자문이 아니다.*")
    return "\n".join(L)


__all__ = ["Outputs", "FILES", "run_manifest", "build_interpretation"]
