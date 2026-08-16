# -*- coding: utf-8 -*-
"""PART 4 Phase 0 게이트 + PART 5 폐기 조건.

게이트는 전부 **미래수익률을 보지 않고** 판정된다. 이것이 이 명세서에서 가장 값싼
반증 장치이며, G-C0·G-C1·G-C3 중 하나라도 실패하면 CXD 는 미래수익률에 접근하지 않는다.

통과시키기 위해 임계값을 조정하지 않는다. 실패는 실패로 기록한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .spec import CXD, RULES, KillLedger, add_unverified


@dataclass
class GateResult:
    gate: str
    passed: Optional[bool]          # None = 판정 불가(표본/데이터 부재)
    value: str
    criterion: str
    action: str = ""                # 실패 시 명세서가 지시한 조치
    note: str = ""

    @property
    def mark(self) -> str:
        return "통과" if self.passed else ("판정불가" if self.passed is None else "실패")


@dataclass
class GateBoard:
    results: List[GateResult] = field(default_factory=list)

    def add(self, g: GateResult) -> GateResult:
        self.results.append(g)
        return g

    def get(self, gate: str) -> Optional[GateResult]:
        for g in self.results:
            if g.gate == gate:
                return g
        return None

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([dict(게이트=g.gate, 판정=g.mark, 측정값=g.value,
                                  통과기준=g.criterion, 실패시조치=g.action, 비고=g.note)
                             for g in self.results])


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  PART 4.1 카나리 — 전면 실행 전 30분. 하나라도 실패하면 전면 실행 금지.
# ═══════════════════════════════════════════════════════════════════════════════════════════
def canary(probe: pd.DataFrame, cells_found: int, earliest_month: Optional[pd.Timestamp],
           linkage_ok: bool, istans_ok: bool) -> pd.DataFrame:
    rows = [
        dict(번호=1, 항목="공공데이터포털 관세청 신성질별 API 인증키 + 1콜 성공",
             결과=bool(probe.loc[probe["source"] == "customs", "ok"].any())
             if "source" in probe.columns else False),
        dict(번호=2, 항목="신성질별 세세분류 코드 755개 전량 회수", 결과=bool(cells_found >= 755)),
        dict(번호=3, 항목="2016년 1월 데이터 조회 가능 (이력 개시 시점)",
             결과=bool(earliest_month is not None
                       and pd.Timestamp(earliest_month) <= pd.Timestamp("2016-01-31"))),
        dict(번호=4, 항목="HSK↔신성질별 연계표 다운로드·파싱 성공", 결과=bool(linkage_ok)),
        dict(번호=5, 항목="ISTANS HS↔KSIC 연계자료 접근 (★단일 최대 병목)", 결과=bool(istans_ok)),
    ]
    df = pd.DataFrame(rows)
    df["판정"] = np.where(df["결과"], "통과", "실패")
    return df


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  G-C0 ~ G-C8
# ═══════════════════════════════════════════════════════════════════════════════════════════
def gate_C0(linkage: Optional[pd.DataFrame], err: str = "") -> GateResult:
    ok = linkage is not None and len(linkage) > 0
    return GateResult("G-C0", bool(ok),
                      f"{len(linkage):,}행" if ok else f"확보 실패 — {err[:90]}",
                      "HSK↔신성질별 연계표 확보 및 파싱 성공", "DATA_BLOCKED")


def gate_C1(panel: pd.DataFrame, by: str = "rebal") -> GateResult:
    """C1 종목의 유효 셀 매핑률 — 중앙 ≥ 60%."""
    if not len(panel):
        return GateResult("G-C1", None, "—", "중앙 ≥ 60%", "COVERAGE_FAIL", "표본 없음")
    r = panel.groupby(by, observed=True)["cell"].apply(lambda s: s.notna().mean())
    med = float(r.median())
    return GateResult("G-C1", bool(med >= RULES["gate_g1_map_rate"]),
                      f"중앙 {med:.1%} (최소 {r.min():.1%} / 최대 {r.max():.1%})",
                      f"중앙 ≥ {RULES['gate_g1_map_rate']:.0%}", "COVERAGE_FAIL")


def gate_C2(sig_incl: pd.DataFrame, sig_excl: pd.DataFrame, top_n: int = 30,
            by: str = "rebal", score: str = "CXD_rank") -> GateResult:
    """사명변경 종목 제외/포함 상위30 Jaccard ≥ 0.70.

    미만이면 **매핑 주도 팩터**로 판정하고 폐기한다(R-05).
    """
    def top(df):
        d = df.dropna(subset=[score])
        return {t: set(g.nlargest(top_n, score)["code"])
                for t, g in d.groupby(by, observed=True)}
    A, B = top(sig_incl), top(sig_excl)
    common = sorted(set(A) & set(B))
    if not common:
        return GateResult("G-C2", None, "—", f"Jaccard ≥ {CXD['GATE_JACCARD']:.2f}",
                          "매핑 주도 판정 → 폐기", "공통 시점 없음")
    js = [len(A[t] & B[t]) / max(1, len(A[t] | B[t])) for t in common]
    med = float(np.median(js))
    return GateResult("G-C2", bool(med >= CXD["GATE_JACCARD"]),
                      f"중앙 Jaccard {med:.3f} ({len(common)}개 시점)",
                      f"≥ {CXD['GATE_JACCARD']:.2f}", "매핑 주도 판정 → 폐기")


def _corr_with_p(x: np.ndarray, y: np.ndarray) -> tuple:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 8:
        return np.nan, np.nan, n
    xv, yv = x[m] - x[m].mean(), y[m] - y[m].mean()
    den = np.sqrt((xv ** 2).sum() * (yv ** 2).sum())
    if den <= 0:
        return np.nan, np.nan, n
    r = float((xv * yv).sum() / den)
    r = min(max(r, -0.999999), 0.999999)
    t = r * np.sqrt((n - 2) / (1 - r * r))
    from scipy import stats
    p = float(2 * stats.t.sf(abs(t), n - 2))
    return r, p, n


def gate_C3(cell_panel: pd.DataFrame, firm: pd.DataFrame, axis_col: str = "cell_mid",
            alpha: float = 0.05) -> GateResult:
    """통관-매출 연결 검증 — 미래수익률을 전혀 보지 않는다.

    ρ_c = Corr( IEG(c,t), median{매출 YoY of C1 종목 in c} ) over 10년
    유의 양(+)인 셀 비율 ≥ 40% → 통과 / < 40% → MECHANISM_FAIL, 즉시 폐기 (KILL-1)
    ★ 셀별 종목 수 부족을 피하기 위해 게이트는 **중분류 축**에서 실행한다(R-09).
    """
    if not len(firm) or axis_col not in firm.columns:
        return GateResult("G-C3", None, "—", f"유의 양(+) 셀 비율 ≥ {CXD['GATE_LINK_RATIO']:.0%}",
                          "MECHANISM_FAIL → 즉시 폐기", "축 컬럼 부재")
    med = (firm.dropna(subset=[axis_col, "rev_yoy"])
           .groupby([axis_col, "rebal"], observed=True)["rev_yoy"].median().rename("rev_med")
           .reset_index())
    cp = cell_panel.dropna(subset=[axis_col, "IEG"])[[axis_col, "rebal", "IEG"]]
    J = med.merge(cp, on=[axis_col, "rebal"], how="inner")
    rows = []
    for c, g in J.groupby(axis_col, observed=True):
        r, p, n = _corr_with_p(g["IEG"].to_numpy(float), g["rev_med"].to_numpy(float))
        rows.append(dict(cell=c, rho=r, p=p, n=n, sig_pos=bool(np.isfinite(r) and r > 0 and p < alpha)))
    D = pd.DataFrame(rows)
    D = D[D["n"] >= 8] if len(D) else D
    if not len(D):
        return GateResult("G-C3", None, "—", f"유의 양(+) 셀 비율 ≥ {CXD['GATE_LINK_RATIO']:.0%}",
                          "MECHANISM_FAIL → 즉시 폐기", "유효 셀 없음")
    ratio = float(D["sig_pos"].mean())
    return GateResult("G-C3", bool(ratio >= CXD["GATE_LINK_RATIO"]),
                      f"{ratio:.1%} ({int(D['sig_pos'].sum())}/{len(D)}셀, 중앙 ρ={D['rho'].median():+.3f})",
                      f"≥ {CXD['GATE_LINK_RATIO']:.0%}", "MECHANISM_FAIL → 즉시 폐기 (KILL-1)")


def gate_C4(panel: pd.DataFrame, by: str = "rebal") -> GateResult:
    """조건화 기제(IEG = SNR 조절자)의 **필요조건** 검증. 미래수익률 0회 접근.

    저-IEG 셀에서 (a) 셀 내 매출성장 횡단면 분산이 크고,
                  (b) DIV 의 분기 간 rank 자기상관이 높아야 한다.
    둘 다 양(+)이 아니면 곱 구조를 폐기하고 arm B 로 강등한다(KILL-2).
    """
    P = panel.dropna(subset=["IEG", "FGR"]).copy()
    if len(P) < 200:
        return GateResult("G-C4", None, "—", "(a)·(b) 둘 다 양(+)", "곱 구조 폐기 → arm B 강등",
                          "표본 부족")
    P["ieg_grp"] = P.groupby(by, observed=True)["IEG"].transform(
        lambda s: pd.qcut(s, 3, labels=["저", "중", "고"], duplicates="drop"))
    v = P.groupby(["ieg_grp", by], observed=True)["FGR"].std().groupby("ieg_grp",
                                                                      observed=True).median()
    lo_v, hi_v = float(v.get("저", np.nan)), float(v.get("고", np.nan))
    a_ok = np.isfinite(lo_v) and np.isfinite(hi_v) and lo_v > hi_v

    # (b) DIV rank 의 분기 간 자기상관 — 저/고 IEG 그룹별
    Q = panel.dropna(subset=["DIV", "IEG"]).copy()
    Q["ieg_grp"] = Q.groupby(by, observed=True)["IEG"].transform(
        lambda s: pd.qcut(s, 3, labels=["저", "중", "고"], duplicates="drop"))
    Q["div_r"] = Q.groupby(by, observed=True)["DIV"].rank(pct=True)
    Q = Q.sort_values(["code", by])
    Q["div_r_prev"] = Q.groupby("code", observed=True)["div_r"].shift(1)
    Q["grp_prev"] = Q.groupby("code", observed=True)["ieg_grp"].shift(1)
    ac = {}
    for grp in ("저", "고"):
        s = Q[(Q["ieg_grp"] == grp) & (Q["grp_prev"] == grp)]
        r, _, n = _corr_with_p(s["div_r"].to_numpy(float), s["div_r_prev"].to_numpy(float))
        ac[grp] = (r, n)
    lo_a, hi_a = ac.get("저", (np.nan, 0))[0], ac.get("고", (np.nan, 0))[0]
    b_ok = np.isfinite(lo_a) and np.isfinite(hi_a) and lo_a > hi_a

    ok = bool(a_ok and b_ok)
    return GateResult("G-C4", ok,
                      f"(a) 분산 저{lo_v:.3f} vs 고{hi_v:.3f} {'✓' if a_ok else '✗'} · "
                      f"(b) DIV rank 자기상관 저{lo_a:+.3f} vs 고{hi_a:+.3f} {'✓' if b_ok else '✗'}",
                      "(a)·(b) 둘 다 저-IEG 우위", "곱 구조 폐기 → arm B 강등 (KILL-2)")


def gate_C5(vintages: Optional[Dict[str, pd.DataFrame]]) -> GateResult:
    """잠정↔확정 셀 순위 변동 — 전향적 3개월 누적이 필요하다.

    과거 vintage 는 존재하지 않으므로 **소급 측정이 불가능**하다(R-06c). 이 사실은
    영구 UNVERIFIED 로 기록되며, 결과 해석 시 반드시 병기된다.
    """
    if not vintages or len(vintages) < 2:
        add_unverified("G-C5 잠정↔확정 개정 크기 — 과거 vintage 부재로 소급 측정 불가",
                       "UNVERIFIED (전향적 3개월 수집 필요)", "방법론적 한계")
        return GateResult("G-C5", None, "—",
                          f"중앙 |Δ순위| ≤ {RULES['gate_g5_rank_drift']:.0%}p",
                          "DATA_RISK 강등 · 소급불가는 UNVERIFIED",
                          "과거 vintage 부재 — 오늘부터 매월 스냅샷을 immutable 로 적재해야 측정 가능")
    keys = sorted(vintages)
    prov, fin = vintages[keys[0]], vintages[keys[-1]]
    M = prov.merge(fin, on=["cell", "month"], suffixes=("_p", "_f"))
    if not len(M):
        return GateResult("G-C5", None, "—", "중앙 |Δ순위| ≤ 5%p", "DATA_RISK 강등", "교집합 없음")
    rp = M.groupby("month", observed=True)["IEG_p"].rank(pct=True)
    rf = M.groupby("month", observed=True)["IEG_f"].rank(pct=True)
    d = float((rp - rf).abs().median())
    return GateResult("G-C5", bool(d <= RULES["gate_g5_rank_drift"]), f"중앙 |Δ순위| {d:.2%}p",
                      f"≤ {RULES['gate_g5_rank_drift']:.0%}p", "DATA_RISK 강등")


def gate_C6(missing_by_axis: Dict[str, float]) -> GateResult:
    """셀 해상도별 IEG 결측률 — ≤ 10% 를 만족하는 **가장 세밀한** 층을 선택하고 동결."""
    if not missing_by_axis:
        return GateResult("G-C6", None, "—", "결측률 ≤ 10% 중 최세밀 층", "층 상향 후 재측정")
    order = ["SINSUNGJIL_SESEBUN", "SINSUNGJIL_SEBUN", "SINSUNGJIL_JUNG", "SINSUNGJIL_DAE"]
    ranked = [a for a in order if a in missing_by_axis]
    ok = [a for a in ranked if missing_by_axis[a] <= (1 - CXD["MIN_CELL_COV"])]
    chosen = ok[0] if ok else None
    detail = " · ".join(f"{a}={missing_by_axis[a]:.1%}" for a in ranked)
    return GateResult("G-C6", bool(chosen is not None),
                      f"{detail} → 선택: {chosen or '없음'}",
                      f"결측률 ≤ {1 - CXD['MIN_CELL_COV']:.0%} 중 최세밀", "층 상향 후 재측정",
                      f"동결 축 = {chosen}" if chosen else "모든 층이 결측률 기준 미달")


def gate_C7(cell_at_rebal: pd.DataFrame) -> GateResult:
    """TREND 부호의 분기 간 변경률 ≤ 10%. 초과 시 60개월 창 재검토(1회만 허용)."""
    D = cell_at_rebal.dropna(subset=["TREND"]).sort_values(["cell", "rebal"]).copy()
    if len(D) < 50:
        return GateResult("G-C7", None, "—", "≤ 10%", "60개월 창 재검토 (1회만)", "표본 부족")
    D["s"] = np.sign(D["TREND"])
    D["s_prev"] = D.groupby("cell", observed=True)["s"].shift(1)
    m = D["s_prev"].notna()
    rate = float((D.loc[m, "s"] != D.loc[m, "s_prev"]).mean())
    return GateResult("G-C7", bool(rate <= RULES["gate_g7_trend_flip"]), f"{rate:.1%}",
                      f"≤ {RULES['gate_g7_trend_flip']:.0%}", "60개월 창 재검토 (1회만 허용)")


def gate_C8(sec: pd.DataFrame, col: str = "has_goodwill") -> GateResult:
    """영업권 계정 존재율 ≥ 70%. 미달이면 R-12 조건을 도입하지 않고 한계로 기록한다."""
    if col not in sec.columns or not len(sec):
        add_unverified("R-12 M&A·연결범위 변동 통제 — 영업권 커버리지 미측정", "미측정")
        return GateResult("G-C8", None, "—", f"≥ {RULES['gate_g8_goodwill_cov']:.0%}",
                          "R-12 조건 미도입, 한계로 기록", "영업권 컬럼 부재")
    cov = float(pd.Series(sec[col]).astype(bool).mean())
    ok = cov >= RULES["gate_g8_goodwill_cov"]
    if not ok:
        add_unverified("R-12 M&A·연결범위 변동 기인 매출성장 — 영업권 커버리지 미달로 조건 미도입",
                       f"부분 통제 (커버리지 {cov:.1%})", "방법론적 한계")
    return GateResult("G-C8", bool(ok), f"{cov:.1%}", f"≥ {RULES['gate_g8_goodwill_cov']:.0%}",
                      "R-12 조건 미도입, 한계로 기록")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  상관 감사 — KILL-3 / KILL-4 / R-08 주의사항
# ═══════════════════════════════════════════════════════════════════════════════════════════
def correlation_audit(panel: pd.DataFrame, kill: KillLedger,
                      sig: str = "CXD", by: str = "rebal") -> pd.DataFrame:
    """ρ(CXD, RESC) · ρ(CXD, IDR) · ρ(CXD, RCV) 를 시점별로 재고 중앙값으로 판정한다.

    RCV(F-09)는 붕괴 배제 게이트와 **정면으로 반대 방향**이므로 필수 포함이다(R-08).
    """
    rows = []
    for other in ("RESC", "P_RS", "P_EG", "IDR", "RCV"):
        if other not in panel.columns:
            continue
        r = (panel.dropna(subset=[sig, other])
             .groupby(by, observed=True)[[sig, other]]
             .apply(lambda g: g[sig].corr(g[other], method="spearman")))
        r = r.replace([np.inf, -np.inf], np.nan).dropna()
        if not len(r):
            continue
        rows.append(dict(대상=other, 중앙ρ=float(r.median()), 절대중앙=float(r.abs().median()),
                         최대절대=float(r.abs().max()), 시점수=int(len(r))))
    D = pd.DataFrame(rows)
    if not len(D):
        return D
    for _, row in D.iterrows():
        if row["대상"] == "RESC" and row["절대중앙"] > RULES["corr_kill_resc"]:
            kill.fire("KILL-3", f"|ρ(CXD, RESC)| 중앙 {row['절대중앙']:.3f} > "
                                f"{RULES['corr_kill_resc']:.2f}", hard=True)
        if row["대상"] == "IDR" and row["절대중앙"] > RULES["corr_kill_idr"]:
            kill.note("KILL-4", f"|ρ(CXD, IDR)| 중앙 {row['절대중앙']:.3f} > "
                                f"{RULES['corr_kill_idr']:.2f} → 중복. 커버리지 높은 쪽만 채택")
    rcv = D[D["대상"] == "RCV"]
    if len(rcv) and float(rcv["중앙ρ"].iloc[0]) < -0.30:
        add_unverified("ρ(CXD, RCV) 강한 음(−) — 결합 단계에서 상쇄되지 않도록 별도 슬리브 분리 필요",
                       f"중앙 ρ={float(rcv['중앙ρ'].iloc[0]):+.3f}", "R-08 주의사항")
    return D


def phase0_verdict(board: GateBoard, kill: KillLedger) -> dict:
    """G-C0·G-C1·G-C3 중 하나라도 실패하면 CXD 는 미래수익률에 접근하지 않는다."""
    blocking = ["G-C0", "G-C1", "G-C3"]
    fails = [g for g in blocking if (board.get(g) is not None and board.get(g).passed is False)]
    undet = [g for g in blocking if (board.get(g) is None or board.get(g).passed is None)]
    g4 = board.get("G-C4")
    demote = bool(g4 is not None and g4.passed is False)
    if demote:
        kill.note("KILL-2", "G-C4 실패 → 곱 구조 폐기, arm B(DIV 단독)로 강등. "
                            "CXD 는 F-08 IDR 의 변형으로 재분류된다.")
    return dict(blocking_fail=fails, undetermined=undet, demote_to_B=demote,
                may_open_returns=(not fails and not undet and not kill.any_hard))
