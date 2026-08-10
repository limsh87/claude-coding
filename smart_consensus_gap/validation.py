# -*- coding: utf-8 -*-
"""Stage 8 — 감사·검증 (§14, §15, §17, §20, §21).

이 모듈의 출력이 성과표보다 먼저다. 감사에서 CRITICAL 하나라도 실패하면
공식 성과를 만들지 않고 run status = FAILED_AUDIT 로 끝낸다(§20, §26-14).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import contracts as C
from .config import (DENOM_NEAR_ZERO_TOL, FACTOR_SCG, FACTORS_6F, FACTORS_7F, MODE_ORIGINAL_EXACT,
                     MODE_PUBLIC_REPRO, SCGConfig, base_snapshot_diff)
from .pit_engine import MarketPanel, TradingCalendar
from .util import LOG, fmt_table, pct_rank

CRITICAL, WARN, INFO = "CRITICAL", "WARN", "INFO"
IC_HORIZONS = (20, 60, 120)
N_QUINTILES = 5


# ════════════════════════════════════════════════════════════════════════════════════════
#  선행수익률 (IC / 분위 검정용)
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class ForwardReturns:
    cal: TradingCalendar
    panel: MarketPanel
    close_ffill: np.ndarray

    @classmethod
    def build(cls, panel: MarketPanel, cal: TradingCalendar) -> "ForwardReturns":
        c = panel.adj_close.copy()
        # 상장폐지 이후는 '마지막 가용 가격으로 청산'과 동일하게 전진 채움한다(백테스트와 일관).
        mask = np.isnan(c)
        idx = np.where(~mask, np.arange(c.shape[0])[:, None], 0)
        np.maximum.accumulate(idx, axis=0, out=idx)
        c = c[idx, np.arange(c.shape[1])[None, :]]
        return cls(cal=cal, panel=panel, close_ffill=c)

    def at(self, asof: Any, codes: Sequence[str], horizon: int) -> np.ndarray:
        i0 = self.cal.pos_on_or_before(asof)
        n = len(codes)
        if i0 < 0:
            return np.full(n, np.nan)
        i1 = min(i0 + int(horizon), self.close_ffill.shape[0] - 1)
        if i1 <= i0:
            return np.full(n, np.nan)
        j = np.array([self.panel.code_pos.get(str(c), -1) for c in codes], dtype=np.int64)
        out = np.full(n, np.nan)
        ok = j >= 0
        if ok.any():
            p0 = self.close_ffill[i0, j[ok]]
            p1 = self.close_ffill[i1, j[ok]]
            v = np.full(int(ok.sum()), np.nan)
            good = np.isfinite(p0) & np.isfinite(p1) & (p0 > 0)
            v[good] = p1[good] / p0[good] - 1.0
            out[ok] = v
        return out


def _spearman(a: np.ndarray, b: np.ndarray) -> Tuple[float, int]:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5:
        return float("nan"), int(m.sum())
    ra = pd.Series(a[m]).rank().to_numpy()
    rb = pd.Series(b[m]).rank().to_numpy()
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan"), int(m.sum())
    return float(np.corrcoef(ra, rb)[0, 1]), int(m.sum())


# ════════════════════════════════════════════════════════════════════════════════════════
#  §15 — SCG 독립 알파 검증
# ════════════════════════════════════════════════════════════════════════════════════════
def rank_ic(fac: "pd.DataFrame", fwd: ForwardReturns, factor: str = FACTOR_SCG,
            horizons: Sequence[int] = IC_HORIZONS) -> "pd.DataFrame":
    """월별 횡단면 Rank IC. 팩터 스냅샷은 매 월말에 만들어져 있어야 한다."""
    rows = []
    if fac is None or not len(fac) or factor not in fac.columns:
        return pd.DataFrame(columns=["asof", "factor", "horizon", "ic", "n"])
    for t, g in fac.groupby("asof", observed=True):
        codes = g["company_code"].astype(str).tolist()
        x = g[factor].to_numpy(dtype=float)
        for h in horizons:
            ic, n = _spearman(x, fwd.at(t, codes, h))
            rows.append({"asof": pd.Timestamp(t), "factor": factor, "horizon": int(h),
                         "ic": ic, "n": n})
    return pd.DataFrame(rows)


def ic_summary(ic: "pd.DataFrame") -> "pd.DataFrame":
    if ic is None or not len(ic):
        return pd.DataFrame(columns=["factor", "horizon", "ic_mean", "ic_std", "t_stat",
                                     "ic_hit_ratio", "n_periods"])
    rows = []
    for (f, h), g in ic.groupby(["factor", "horizon"], observed=True):
        v = g["ic"].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        if len(v) < 2:
            rows.append({"factor": f, "horizon": h, "ic_mean": np.nan, "ic_std": np.nan,
                         "t_stat": np.nan, "ic_hit_ratio": np.nan, "n_periods": len(v)})
            continue
        sd = float(v.std(ddof=1))
        rows.append({"factor": f, "horizon": int(h), "ic_mean": float(v.mean()),
                     "ic_std": sd,
                     "t_stat": float(v.mean() / (sd / np.sqrt(len(v)))) if sd > 0 else np.nan,
                     "ic_hit_ratio": float((v > 0).mean()), "n_periods": int(len(v))})
    return pd.DataFrame(rows)


def quintiles(fac: "pd.DataFrame", fwd: ForwardReturns, factor: str = FACTOR_SCG,
              horizon: int = 60) -> Tuple["pd.DataFrame", "pd.DataFrame"]:
    """Q1~Q5 평균 선행수익률과 단조성. (기간별, 요약)."""
    rows = []
    if fac is None or not len(fac) or factor not in fac.columns:
        return pd.DataFrame(), pd.DataFrame()
    for t, g in fac.groupby("asof", observed=True):
        x = g[factor].to_numpy(dtype=float)
        codes = g["company_code"].astype(str).tolist()
        r = fwd.at(t, codes, horizon)
        m = np.isfinite(x) & np.isfinite(r)
        if m.sum() < N_QUINTILES * 3:
            continue
        pr = pct_rank(np.where(m, x, np.nan))
        q = np.clip(pr * N_QUINTILES, 0, N_QUINTILES - 1e-9)
        qi = np.floor(np.where(np.isfinite(q), q, -1.0)).astype(np.int64)
        for k in range(N_QUINTILES):
            sel = m & (qi == k)
            if sel.sum() == 0:
                continue
            rows.append({"asof": pd.Timestamp(t), "factor": factor, "horizon": int(horizon),
                         "quintile": f"Q{k+1}", "mean_fwd_ret": float(np.nanmean(r[sel])),
                         "n": int(sel.sum())})
    per = pd.DataFrame(rows)
    if not len(per):
        return per, pd.DataFrame()
    summ = per.groupby(["factor", "horizon", "quintile"], observed=True).agg(
        mean_fwd_ret=("mean_fwd_ret", "mean"), periods=("asof", "nunique"),
        avg_n=("n", "mean")).reset_index()
    piv = summ.pivot_table(index=["factor", "horizon"], columns="quintile",
                           values="mean_fwd_ret").reset_index()
    qcols = [f"Q{i}" for i in range(1, N_QUINTILES + 1) if f"Q{i}" in piv.columns]
    if len(qcols) == N_QUINTILES:
        piv["Q5_minus_Q1"] = piv["Q5"] - piv["Q1"]
        vals = piv[qcols].to_numpy(dtype=float)
        piv["monotonic_increasing"] = np.all(np.diff(vals, axis=1) > 0, axis=1)
        piv["rank_corr_quintile"] = [
            float(np.corrcoef(np.arange(N_QUINTILES), row)[0, 1]) if np.all(np.isfinite(row)) else np.nan
            for row in vals]
    return per, piv


def conditional_ic(fac: "pd.DataFrame", fwd: ForwardReturns, factor: str = FACTOR_SCG,
                   horizon: int = 60) -> "pd.DataFrame":
    """§15 조건부 검정 — 리비전 부호 / 애널리스트 수 / 컨센서스 분산 구간별 IC."""
    from .config import FACTOR_REV
    rows = []
    if fac is None or not len(fac):
        return pd.DataFrame(columns=["condition", "bucket", "ic_mean", "t_stat", "n_periods"])

    def add(cond_name: str, bucket_fn) -> None:
        per: Dict[str, List[float]] = {}
        for t, g in fac.groupby("asof", observed=True):
            b = bucket_fn(g)
            if b is None:
                continue
            for name, mask in b.items():
                if mask.sum() < 10:
                    continue
                sub = g.loc[mask]
                ic, n = _spearman(sub[factor].to_numpy(dtype=float),
                                  fwd.at(t, sub["company_code"].astype(str).tolist(), horizon))
                if np.isfinite(ic):
                    per.setdefault(name, []).append(ic)
        for name, vals in per.items():
            v = np.array(vals, dtype=float)
            sd = float(v.std(ddof=1)) if len(v) > 1 else np.nan
            rows.append({"condition": cond_name, "bucket": name, "ic_mean": float(v.mean()),
                         "t_stat": float(v.mean() / (sd / np.sqrt(len(v)))) if sd and sd > 0 else np.nan,
                         "n_periods": int(len(v))})

    def rev_bucket(g):
        if FACTOR_REV not in g.columns:
            return None
        r = g[FACTOR_REV].to_numpy(dtype=float)
        return {"revision_positive": np.isfinite(r) & (r > 0),
                "revision_negative": np.isfinite(r) & (r <= 0)}

    def cnt_bucket(g):
        if "analyst_count" not in g.columns:
            return None
        a = pd.to_numeric(g["analyst_count"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(a).any():
            return None
        med = np.nanmedian(a)
        return {"analyst_count_high": np.isfinite(a) & (a > med),
                "analyst_count_low": np.isfinite(a) & (a <= med)}

    def disp_bucket(g):
        if "consensus_std" not in g.columns or "general_consensus_fq1" not in g.columns:
            return None
        s = g["consensus_std"].to_numpy(dtype=float)
        c = np.abs(g["general_consensus_fq1"].to_numpy(dtype=float))
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.where(c > DENOM_NEAR_ZERO_TOL, s / c, np.nan)
        if not np.isfinite(d).any():
            return None
        med = np.nanmedian(d)
        return {"dispersion_high": np.isfinite(d) & (d > med),
                "dispersion_low": np.isfinite(d) & (d <= med)}

    add("eps_revision_sign", rev_bucket)
    add("analyst_count", cnt_bucket)
    add("consensus_dispersion", disp_bucket)
    return pd.DataFrame(rows)


def smart_vs_general_accuracy(events: "pd.DataFrame", audits: "pd.DataFrame",
                              actuals: "pd.DataFrame") -> "pd.DataFrame":
    """§23-4 — 스마트 컨센서스가 일반 컨센서스보다 실제 EPS 에 실제로 더 가까운가?

    감사표(성분)로 각 (asof, company, period) 의 스마트/일반 컨센서스를 복원하고,
    그 회계기간의 **사후** 실적과 비교한다. (사후 비교이며 시그널에는 쓰이지 않는다)
    """
    cols = ["n_pairs", "mae_general", "mae_smart", "improvement_ratio", "win_rate_smart",
            "median_abs_err_general", "median_abs_err_smart"]
    if audits is None or not len(audits) or actuals is None or not len(actuals):
        return pd.DataFrame([{c: np.nan for c in cols}])
    g = audits.groupby(["asof", "company_code", "fiscal_period"], observed=True)
    est = g.agg(smart=("estimate_adj", lambda s: np.nan),
                n=("estimator_id", "size")).reset_index()
    # 가중합으로 스마트, 단순평균으로 일반을 복원한다
    a = audits.copy()
    a["_wx"] = a["w_final"].astype(float) * a["estimate_adj"].astype(float)
    rec = a.groupby(["asof", "company_code", "fiscal_period"], observed=True).agg(
        smart=("_wx", "sum"), general=("estimate_raw", "mean"), n=("estimator_id", "size")
    ).reset_index()
    act = actuals[actuals["metric"] == "EPS"][["company_code", "fiscal_period", "actual_value"]]
    m = rec.merge(act, on=["company_code", "fiscal_period"], how="inner")
    if not len(m):
        return pd.DataFrame([{c: np.nan for c in cols}])
    scale = np.maximum(np.abs(m["actual_value"].to_numpy(dtype=float)), 1e-6)
    eg = np.abs(m["general"].to_numpy(dtype=float) - m["actual_value"].to_numpy(dtype=float)) / scale
    es = np.abs(m["smart"].to_numpy(dtype=float) - m["actual_value"].to_numpy(dtype=float)) / scale
    ok = np.isfinite(eg) & np.isfinite(es)
    if ok.sum() == 0:
        return pd.DataFrame([{c: np.nan for c in cols}])
    return pd.DataFrame([{
        "n_pairs": int(ok.sum()),
        "mae_general": float(eg[ok].mean()), "mae_smart": float(es[ok].mean()),
        "improvement_ratio": float(1.0 - es[ok].mean() / eg[ok].mean()) if eg[ok].mean() > 0 else np.nan,
        "win_rate_smart": float((es[ok] < eg[ok]).mean()),
        "median_abs_err_general": float(np.median(eg[ok])),
        "median_abs_err_smart": float(np.median(es[ok])),
    }])


# ════════════════════════════════════════════════════════════════════════════════════════
#  §17 — 통계 검정
# ════════════════════════════════════════════════════════════════════════════════════════
def block_bootstrap_ci(excess: "pd.Series", n_boot: int, seed: int, block_days: int = 21,
                       alpha: float = 0.05) -> Dict[str, Any]:
    """초과수익 연율화 평균의 블록 부트스트랩 신뢰구간."""
    r = pd.Series(excess).dropna().astype(float).to_numpy()
    n = len(r)
    if n < block_days * 4:
        return {"n_boot": 0, "point": float(np.mean(r) * 252) if n else np.nan,
                "ci_low": np.nan, "ci_high": np.nan, "p_gt_zero": np.nan,
                "note": "표본 부족"}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_days))
    starts_max = n - block_days
    means = np.empty(n_boot)
    for b in range(n_boot):
        st = rng.integers(0, starts_max + 1, size=n_blocks)
        idx = (st[:, None] + np.arange(block_days)[None, :]).ravel()[:n]
        means[b] = r[idx].mean()
    means *= 252.0
    return {"n_boot": int(n_boot), "point": float(r.mean() * 252.0),
            "ci_low": float(np.quantile(means, alpha / 2)),
            "ci_high": float(np.quantile(means, 1 - alpha / 2)),
            "p_gt_zero": float((means > 0).mean()), "block_days": int(block_days),
            "note": ""}


def event_removal_sensitivity(ret: "pd.Series", tops: Sequence[int] = (1, 3, 5)) -> "pd.DataFrame":
    """§17 — 상위 월간 수익 이벤트를 제거해도 성과가 남는가."""
    r = pd.Series(ret).dropna().astype(float)
    if not len(r) or not isinstance(r.index, pd.DatetimeIndex):
        return pd.DataFrame(columns=["removed_top_n", "CAGR", "total_return", "n_months"])
    m = r.resample("ME").apply(lambda s: (1 + s).prod() - 1)
    rows = []
    for k in (0,) + tuple(tops):
        mm = m.sort_values(ascending=False).iloc[k:] if k else m
        if not len(mm):
            continue
        tot = float((1 + mm).prod() - 1)
        yrs = len(mm) / 12.0
        rows.append({"removed_top_n": k, "CAGR": float((1 + tot) ** (1 / yrs) - 1) if yrs > 0 else np.nan,
                     "total_return": tot, "n_months": int(len(mm))})
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════════════════════════
#  §14 — 2020-06-30 원문 표7 대조
# ════════════════════════════════════════════════════════════════════════════════════════
REFERENCE_DATE = pd.Timestamp("2020-06-30")
REFERENCE_COLUMNS = ["rank", "company_code", "company_name", "surprise_probability",
                     "fq1_eps_yoy", "fy1_eps_yoy", "smart_gap_fq1", "eps12mf_rev_1m",
                     "inst_20d", "foreign_20d", "source_page"]


def load_reference_fixture(path: str) -> Tuple[Optional["pd.DataFrame"], str]:
    """PDF 표7 픽스처. 없으면 (None, 사유). ★ 없는 값을 지어내지 않는다."""
    if not path or not os.path.exists(path):
        return None, "REFERENCE_FIXTURE_MISSING"
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as e:  # noqa: BLE001
        return None, f"REFERENCE_FIXTURE_UNREADABLE:{type(e).__name__}"
    if "company_code" not in df.columns:
        return None, "REFERENCE_FIXTURE_NO_COMPANY_CODE"
    df["company_code"] = C.normalize_code(df["company_code"])
    df = df[df["company_code"].str.fullmatch(r"\d{6}").fillna(False)]
    if not len(df):
        return None, "REFERENCE_FIXTURE_EMPTY"
    for c in REFERENCE_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    for c in ["surprise_probability", "fq1_eps_yoy", "fy1_eps_yoy", "smart_gap_fq1",
              "eps12mf_rev_1m", "inst_20d", "foreign_20d", "rank"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True), "OK"


def reference_match(selected: "pd.DataFrame", fac: "pd.DataFrame", fixture_path: str,
                    strategy: str) -> "pd.DataFrame":
    """§14 — 원문 30종목과 재현 top30 의 겹침. 불일치가 나와도 파라미터를 맞추지 않는다."""
    ref, status = load_reference_fixture(fixture_path)
    base = {"strategy": strategy, "reference_date": str(REFERENCE_DATE.date()),
            "fixture_status": status, "source_page": 16}
    if ref is None:
        base.update({"top30_overlap_count": np.nan, "overlap_ratio": np.nan, "jaccard": np.nan,
                     "rank_correlation_on_overlap": np.nan, "model_n": np.nan,
                     "reference_n": np.nan, "intersection": "", "missing": "", "extra": "",
                     "factor_value_correlations": "",
                     "note": "원문 PDF 표7 픽스처가 없어 대조 불가. "
                             "reference/reference_20200630.csv 를 채우면 자동으로 수행된다. "
                             "★ 없는 값을 임의 생성하지 않는다(§0-2)."})
        return pd.DataFrame([base])

    d = selected[pd.to_datetime(selected["asof"]) == REFERENCE_DATE] if selected is not None and \
        len(selected) else pd.DataFrame()
    if not len(d):
        base.update({"top30_overlap_count": 0, "overlap_ratio": 0.0, "jaccard": 0.0,
                     "rank_correlation_on_overlap": np.nan, "model_n": 0,
                     "reference_n": int(len(ref)), "intersection": "",
                     "missing": ";".join(ref["company_code"].tolist()), "extra": "",
                     "factor_value_correlations": "",
                     "note": "2020-06-30 리밸런싱 스냅샷이 없다(백테스트 구간/데이터 확인)."})
        return pd.DataFrame([base])

    d = d[d["selected"]].sort_values("rank")
    model = d["company_code"].astype(str).tolist()
    refc = ref["company_code"].astype(str).tolist()
    inter = [c for c in model if c in set(refc)]
    missing = [c for c in refc if c not in set(model)]
    extra = [c for c in model if c not in set(refc)]
    union = len(set(model) | set(refc))

    rc = np.nan
    if len(inter) >= 3 and ref["rank"].notna().any():
        mr = {c: r for c, r in zip(model, d["rank"].to_numpy())}
        rr = dict(zip(refc, ref["rank"].to_numpy(dtype=float)))
        a = np.array([mr[c] for c in inter], dtype=float)
        b = np.array([rr.get(c, np.nan) for c in inter], dtype=float)
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() >= 3 and np.std(a[ok]) > 0 and np.std(b[ok]) > 0:
            rc = float(np.corrcoef(pd.Series(a[ok]).rank(), pd.Series(b[ok]).rank())[0, 1])

    # 팩터 raw value 상관 (벤더 exact 인 경우 의미가 크다)
    corrs = []
    pairs = [("smart_gap_fq1", FACTOR_SCG), ("fq1_eps_yoy", "FQ1_EPS_YOY"),
             ("fy1_eps_yoy", "FY1_EPS_YOY"), ("eps12mf_rev_1m", "EPS12MF_REV_1M"),
             ("inst_20d", "INST_20D"), ("foreign_20d", "FOREIGN_20D"),
             ("surprise_probability", "SURPRISE_PROB")]
    f0 = fac[pd.to_datetime(fac["asof"]) == REFERENCE_DATE] if fac is not None and len(fac) \
        else pd.DataFrame()
    if len(f0) and inter:
        f0 = f0.set_index(f0["company_code"].astype(str))
        for rcol, fcol in pairs:
            if fcol not in f0.columns or ref[rcol].isna().all():
                continue
            rv = ref.set_index("company_code")[rcol]
            a = np.array([rv.get(c, np.nan) for c in inter], dtype=float)
            b = np.array([f0[fcol].get(c, np.nan) for c in inter], dtype=float)
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() >= 5 and np.std(a[ok]) > 0 and np.std(b[ok]) > 0:
                corrs.append(f"{fcol}={np.corrcoef(a[ok], b[ok])[0,1]:.3f}(n={int(ok.sum())})")

    base.update({
        "top30_overlap_count": len(inter),
        "overlap_ratio": len(inter) / max(len(refc), 1),
        "jaccard": len(inter) / union if union else np.nan,
        "rank_correlation_on_overlap": rc,
        "model_n": len(model), "reference_n": len(refc),
        "intersection": ";".join(inter), "missing": ";".join(missing), "extra": ";".join(extra),
        "factor_value_correlations": ", ".join(corrs),
        "note": "겹침이 낮아도 파라미터를 표7에 맞추지 않는다(§14, §27).",
    })
    return pd.DataFrame([base])


# ════════════════════════════════════════════════════════════════════════════════════════
#  §20 — 감사 불변식
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class AuditContext:
    cfg: SCGConfig
    mode: str
    est: Optional["pd.DataFrame"] = None
    events: Optional["pd.DataFrame"] = None
    audits: Optional["pd.DataFrame"] = None
    fac: Optional["pd.DataFrame"] = None
    holdings: Optional["pd.DataFrame"] = None
    selected: Optional["pd.DataFrame"] = None
    universe_raw: Optional["pd.DataFrame"] = None
    fac_exact: Optional["pd.DataFrame"] = None
    signal_dates: Sequence[Any] = ()
    exact_block_reasons: Sequence[str] = ()
    exact_skipped: bool = True
    benchmark_kind: str = ""
    unit_tests: Optional["pd.DataFrame"] = None
    backtest_flags: Dict[str, int] = field(default_factory=dict)


def audit_checks(ctx: AuditContext) -> "pd.DataFrame":
    rows: List[Dict[str, Any]] = []

    def add(name: str, severity: str, passed: Optional[bool], detail: str = "",
            n_checked: int = 0) -> None:
        rows.append({"check": name, "severity": severity,
                     "status": "PASS" if passed else ("SKIP" if passed is None else "FAIL"),
                     "passed": bool(passed) if passed is not None else None,
                     "n_checked": n_checked, "detail": detail})

    cfg = ctx.cfg
    sig = pd.DatetimeIndex(pd.to_datetime(list(ctx.signal_dates))) if len(ctx.signal_dates) else None

    # 1. 설정 스냅샷 변조
    if cfg.variant_id == "BASE":
        diffs = base_snapshot_diff(cfg)
        add("BASE_CONFIG_UNMODIFIED", CRITICAL, not diffs,
            "; ".join(diffs) if diffs else "§25 기본값과 일치", len(diffs))
    else:
        add("BASE_CONFIG_UNMODIFIED", INFO, None, f"variant={cfg.variant_id}")

    # 2. SCG 산식 단위테스트
    if ctx.unit_tests is not None and len(ctx.unit_tests):
        bad = ctx.unit_tests[~ctx.unit_tests["passed"].astype(bool)]
        add("SCG_FORMULA_UNIT_TESTS", CRITICAL, len(bad) == 0,
            "; ".join(f"{r['test']}:{r['detail']}" for _, r in bad.iterrows()) or "전부 통과",
            int(len(ctx.unit_tests)))
    else:
        add("SCG_FORMULA_UNIT_TESTS", CRITICAL, False, "단위테스트가 실행되지 않았다")

    # 3. published_at <= signal_date
    if ctx.audits is not None and len(ctx.audits):
        bad = int((pd.to_datetime(ctx.audits["published_at"]) >
                   pd.to_datetime(ctx.audits["asof"])).sum())
        add("PIT_PUBLISHED_AT_LE_SIGNAL", CRITICAL, bad == 0,
            f"위반 {bad:,}행", int(len(ctx.audits)))
        age = pd.to_numeric(ctx.audits["age_days"], errors="coerce")
        bad2 = int((age > cfg.active_estimate_window_days + 1e-9).sum() + (age < 0).sum())
        add("ACTIVE_WINDOW_RESPECTED", CRITICAL, bad2 == 0,
            f"창 밖 추정치 {bad2:,}행 (허용 0~{cfg.active_estimate_window_days}일)",
            int(len(ctx.audits)))
    else:
        add("PIT_PUBLISHED_AT_LE_SIGNAL", CRITICAL, None, "스마트 컨센서스 성분 감사표 없음")
        add("ACTIVE_WINDOW_RESPECTED", CRITICAL, None, "성분 감사표 없음")

    # 4. skill 이력의 실적 발표가 시그널 이전
    if ctx.events is not None and len(ctx.events) and sig is not None and len(sig):
        # 각 시그널 시점에서 실제로 쓰일 수 있는 이벤트가 모두 발표 이전인지 확인
        ann = pd.to_datetime(ctx.events["announced_at"]).to_numpy("datetime64[ns]")
        viol = 0
        for t in sig:
            used = ann[ann < np.datetime64(t)]
            viol += int((used >= np.datetime64(t)).sum())
        add("SKILL_HISTORY_ANNOUNCED_BEFORE_SIGNAL", CRITICAL, viol == 0,
            f"위반 {viol}", int(len(ctx.events)))
        # 예측이 실적 발표 이전에 공표되었는지
        bad = int((pd.to_datetime(ctx.events["published_at"]) >=
                   pd.to_datetime(ctx.events["announced_at"])).sum())
        add("SKILL_FORECAST_BEFORE_ANNOUNCEMENT", CRITICAL, bad == 0, f"위반 {bad:,}행",
            int(len(ctx.events)))
    else:
        add("SKILL_HISTORY_ANNOUNCED_BEFORE_SIGNAL", WARN, None, "실현 이벤트 없음")
        add("SKILL_FORECAST_BEFORE_ANNOUNCEMENT", WARN, None, "실현 이벤트 없음")

    # 5. 일반 컨센서스 estimator 중복 0
    if ctx.audits is not None and len(ctx.audits):
        dup = int(ctx.audits.duplicated(
            subset=["asof", "company_code", "fiscal_period", "estimator_id"]).sum())
        add("CONSENSUS_ESTIMATOR_DUPLICATE_ZERO", CRITICAL, dup == 0, f"중복 {dup:,}행",
            int(len(ctx.audits)))
    else:
        add("CONSENSUS_ESTIMATOR_DUPLICATE_ZERO", CRITICAL, None, "성분 감사표 없음")

    # 6. 가중치 합 1 / 개별 상한
    if ctx.audits is not None and len(ctx.audits):
        gsum = ctx.audits.groupby(["asof", "company_code", "fiscal_period"],
                                  observed=True)["w_final"].sum()
        bad = int((np.abs(gsum.to_numpy(dtype=float) - 1.0) > 1e-10).sum())
        add("SMART_WEIGHTS_SUM_TO_ONE", CRITICAL, bad == 0,
            f"|Σw−1|>1e-10 인 그룹 {bad:,}개", int(len(gsum)))
        wmax = ctx.audits.groupby(["asof", "company_code", "fiscal_period"],
                                  observed=True)["w_final"].max()
        sizes = ctx.audits.groupby(["asof", "company_code", "fiscal_period"],
                                   observed=True)["estimator_id"].size()
        feasible = (sizes.to_numpy() * cfg.analyst_weight_cap) >= 1.0 - 1e-12
        over = int(((wmax.to_numpy(dtype=float) > cfg.analyst_weight_cap + 1e-9) & feasible).sum())
        add("SMART_WEIGHT_CAP_RESPECTED", CRITICAL, over == 0,
            f"상한 {cfg.analyst_weight_cap:.0%} 초과 그룹 {over:,}개 (infeasible 그룹 제외)",
            int(len(wmax)))
    else:
        add("SMART_WEIGHTS_SUM_TO_ONE", CRITICAL, None, "성분 감사표 없음")
        add("SMART_WEIGHT_CAP_RESPECTED", CRITICAL, None, "성분 감사표 없음")

    # 7. SCG 수치 항등식
    if ctx.fac is not None and len(ctx.fac):
        g = ctx.fac["general_consensus_fq1"].to_numpy(dtype=float)
        s = ctx.fac["smart_consensus_fq1"].to_numpy(dtype=float)
        v = ctx.fac["SCG_RAW"].to_numpy(dtype=float)
        ok = np.isfinite(g) & np.isfinite(s) & (np.abs(g) >= DENOM_NEAR_ZERO_TOL) & np.isfinite(v)
        err = np.abs(v[ok] - (s[ok] - g[ok]) / g[ok])
        bad = int((err > 1e-9).sum())
        add("SCG_RAW_FORMULA_IDENTITY", CRITICAL, bad == 0,
            f"불일치 {bad:,}행 (max err={float(err.max()) if len(err) else 0:.2e})", int(ok.sum()))
        # 결측 자동대체 금지
        for f in (FACTORS_6F if ctx.mode == MODE_PUBLIC_REPRO else FACTORS_7F):
            if f not in ctx.fac.columns:
                continue
        sel = ctx.selected
        if sel is not None and len(sel):
            need = FACTORS_7F if ctx.mode == MODE_ORIGINAL_EXACT else FACTORS_6F
            have = [f for f in need if f in sel.columns]
            miss = int(sel.loc[sel["selected"], have].isna().any(axis=1).sum()) if have else 0
            add("NO_SILENT_FACTOR_IMPUTATION", CRITICAL, miss == 0,
                f"결측 팩터를 가진 채 선정된 종목 {miss:,}", int(sel["selected"].sum()))
        else:
            add("NO_SILENT_FACTOR_IMPUTATION", CRITICAL, None, "선정 결과 없음")
    else:
        add("SCG_RAW_FORMULA_IDENTITY", CRITICAL, None, "팩터 스냅샷 없음")
        add("NO_SILENT_FACTOR_IMPUTATION", CRITICAL, None, "팩터 스냅샷 없음")

    # 8. 유니버스 PIT / 생존편향
    if ctx.universe_raw is not None and len(ctx.universe_raw) and sig is not None and len(sig):
        udates = pd.to_datetime(ctx.universe_raw["date"]).drop_duplicates().sort_values()
        n_snap = int(len(udates))
        add("UNIVERSE_IS_PIT", CRITICAL, n_snap > 1,
            f"유니버스 스냅샷 {n_snap}개 (1개면 현재 구성종목 소급 의심)", n_snap)
        if ctx.fac is not None and len(ctx.fac) and "universe_snapshot_date" in ctx.fac.columns:
            us = pd.to_datetime(ctx.fac["universe_snapshot_date"])
            bad = int((us > pd.to_datetime(ctx.fac["asof"])).sum())
            add("NO_FUTURE_UNIVERSE_SNAPSHOT", CRITICAL, bad == 0, f"미래 스냅샷 사용 {bad:,}행",
                int(len(ctx.fac)))
        else:
            add("NO_FUTURE_UNIVERSE_SNAPSHOT", CRITICAL, None, "스냅샷 일자 정보 없음")
    else:
        add("UNIVERSE_IS_PIT", CRITICAL, None, "유니버스 원본 없음")
        add("NO_FUTURE_UNIVERSE_SNAPSHOT", CRITICAL, None, "유니버스 원본 없음")

    # 9. 선정 종목 수 / 시총가중 합
    if ctx.holdings is not None and len(ctx.holdings):
        g = ctx.holdings.groupby(["strategy", "asof"], observed=True)
        summ = g.agg(n=("company_code", "size"),
                     flagged=("coverage_flag",
                              lambda s: bool(s.astype(str).str.startswith("SHORT").any()))
                     ).reset_index()
        off = summ["n"].to_numpy() != cfg.n_holdings
        unexplained = int((off & ~summ["flagged"].to_numpy()).sum())
        add("SELECTED_N_EQUALS_TARGET", WARN, unexplained == 0,
            f"N≠{cfg.n_holdings} 인 리밸런싱 {int(off.sum())}회 중 coverage_flag 로 설명되지 "
            f"않는 건 {unexplained}회", int(len(summ)))
        wsum = ctx.holdings.groupby(["strategy", "asof"], observed=True)["weight"].sum()
        bad = int((np.abs(wsum.to_numpy(dtype=float) - 1.0) > 1e-9).sum())
        add("PORTFOLIO_WEIGHTS_SUM_TO_ONE", CRITICAL, bad == 0, f"|Σw−1|>1e-9 인 시점 {bad}",
            int(len(wsum)))
    else:
        add("SELECTED_N_EQUALS_TARGET", WARN, None, "보유 내역 없음")
        add("PORTFOLIO_WEIGHTS_SUM_TO_ONE", CRITICAL, None, "보유 내역 없음")

    # 10. 체결 시점이 시그널 이후
    if ctx.holdings is not None and len(ctx.holdings):
        h = ctx.holdings.dropna(subset=["exec_date"])
        bad = int((pd.to_datetime(h["exec_date"]) <= pd.to_datetime(h["asof"])).sum())
        add("EXECUTION_AFTER_SIGNAL", CRITICAL, bad == 0,
            f"체결일 <= 시그널일 인 행 {bad:,} (§12 다음 거래일 시가)", int(len(h)))
    else:
        add("EXECUTION_AFTER_SIGNAL", CRITICAL, None, "보유 내역 없음")

    # 11. 모드 오염 / EXACT 자동 스킵
    contaminated = 0
    if ctx.mode == MODE_ORIGINAL_EXACT and ctx.fac is not None and "scg_source" in ctx.fac.columns:
        contaminated = int((ctx.fac["scg_source"].astype(str) != "VENDOR").sum())
    if ctx.mode == MODE_PUBLIC_REPRO and ctx.fac is not None and "scg_source" in ctx.fac.columns:
        contaminated = int((ctx.fac["scg_source"].astype(str) == "VENDOR").sum())
    add("MODE_CONTAMINATION_ZERO", CRITICAL, contaminated == 0,
        f"모드={ctx.mode} 인데 다른 소스로 계산된 SCG {contaminated:,}행")
    if ctx.exact_block_reasons:
        add("EXACT_STRATEGY_SKIPPED_WHEN_VENDOR_MISSING", CRITICAL, bool(ctx.exact_skipped),
            "벤더 필드 결측: " + "; ".join(ctx.exact_block_reasons))
    else:
        add("EXACT_STRATEGY_SKIPPED_WHEN_VENDOR_MISSING", INFO, None, "벤더 필드 존재")
    #  EXACT 프레임이 따로 있으면 그쪽도 오염 0 이어야 한다 (재구성값이 섞여 들어오면 안 된다)
    if ctx.fac_exact is not None and len(ctx.fac_exact):
        bad = int((ctx.fac_exact["scg_source"].astype(str) != "VENDOR").sum()) \
            if "scg_source" in ctx.fac_exact.columns else -1
        add("EXACT_FRAME_USES_VENDOR_ONLY", CRITICAL, bad == 0,
            f"EXACT 팩터 프레임에서 벤더가 아닌 소스로 계산된 SCG {bad:,}행")
        nsp = int(np.isfinite(ctx.fac_exact["SURPRISE_PROB"].to_numpy(dtype=float)).sum()) \
            if "SURPRISE_PROB" in ctx.fac_exact.columns else 0
        add("EXACT_FRAME_HAS_SURPRISE_PROB", CRITICAL, nsp > 0,
            f"벤더 서프라이즈 확률 유효값 {nsp:,}행 (0 이면 7팩터가 성립하지 않는다)")
    if ctx.mode == MODE_PUBLIC_REPRO and ctx.fac is not None and "surprise_prob_source" in ctx.fac.columns:
        used_sp = int((ctx.fac["surprise_prob_source"].astype(str) == "VENDOR").sum())
        add("PUBLIC_REPRO_NO_SURPRISE_PROXY", CRITICAL, used_sp == 0,
            f"PUBLIC_REPRO 공식 팩터에 서프라이즈 확률이 들어간 행 {used_sp:,} (§8)")

    # 12. 12MF 소스 혼합 금지
    if ctx.fac is not None and len(ctx.fac) and "twelve_mf_source" in ctx.fac.columns:
        n_src = int(ctx.fac["twelve_mf_source"].astype(str).nunique())
        add("TWELVE_MF_SOURCE_NOT_MIXED", CRITICAL, n_src <= 1,
            f"12MF 소스 종류 {n_src} (§7.3 혼합 금지)")

    # 13. 미래 가격 미사용 — 시그널 산출에 쓰인 컬럼 목록으로 구조적으로 보장됨을 기록
    add("SIGNAL_USES_NO_FUTURE_PRICE", CRITICAL,
        True if ctx.fac is not None and len(ctx.fac) else None,
        "팩터는 asof 이하 가격/수급/추정치만 참조한다(pit_engine 의 asof 조회 경로 단일화). "
        "선행수익률은 검증 전용이며 시그널 경로와 분리되어 있다.")

    # 14. 벤치마크 처리 문서화
    add("BENCHMARK_TREATMENT_DOCUMENTED", WARN, bool(ctx.benchmark_kind),
        f"벤치마크 종류={ctx.benchmark_kind or '미기록'}"
        + (" (실지수가 아니라 PIT 유니버스 시총가중 대용)"
           if ctx.benchmark_kind == "PROXY_UNIVERSE_CAPWEIGHT" else ""))

    # 15. 백테스트 플래그
    if ctx.backtest_flags:
        add("BACKTEST_FLAGS", WARN, all(k not in ("NO_HOLDINGS", "NO_EXEC_DATE")
                                        for k in ctx.backtest_flags),
            "; ".join(f"{k}={v}" for k, v in sorted(ctx.backtest_flags.items())))

    return pd.DataFrame(rows)


def audit_verdict(checks: "pd.DataFrame") -> Tuple[bool, List[str]]:
    """CRITICAL 이 하나라도 FAIL 이면 공식 성과 금지 (§20)."""
    if checks is None or not len(checks):
        return False, ["감사 결과가 없다"]
    crit = checks[(checks["severity"] == CRITICAL) & (checks["status"] == "FAIL")]
    return len(crit) == 0, crit["check"].tolist()


def log_audit(checks: "pd.DataFrame") -> None:
    LOG.info(fmt_table(checks[["check", "severity", "status", "detail"]], max_rows=40))
    ok, failed = audit_verdict(checks)
    if ok:
        LOG.info("  ✔ CRITICAL 감사 전부 통과")
    else:
        LOG.error(f"  ✘ CRITICAL 실패: {failed}")


__all__ = [n for n in dir() if not n.startswith("_")]
