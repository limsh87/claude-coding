#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCG_ORIGINAL_REPRO_V1 자가검정.

`python3 tools/scg_selftest.py` — 의존성만 있으면 어디서든 몇 분 안에 끝난다.

여기서 고정하는 것은 "성과"가 아니라 **정의와 불변식**이다:
  · SCG 산식(분모 abs 금지 포함)
  · PIT 규칙 (미래 추정치/미래 실적 차단)
  · 가중치 합·상한
  · 결측 자동대체 금지
  · 사전 정의 강건성 변형이 one-variable-at-a-time 인지
  · 벤더 필드가 없을 때 EXACT 가 자동 스킵되는지 / 있을 때 오염 없이 함께 도는지
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                        # noqa: E402
import pandas as pd                                                       # noqa: E402

from smart_consensus_gap import analyst_skill as SK                       # noqa: E402
from smart_consensus_gap import config as CFG                             # noqa: E402
from smart_consensus_gap import consensus as CONS                         # noqa: E402
from smart_consensus_gap import contracts as C                            # noqa: E402
from smart_consensus_gap import factors as FX                             # noqa: E402
from smart_consensus_gap import normalize as NORM                         # noqa: E402
from smart_consensus_gap import pit_engine as PIT                         # noqa: E402
from smart_consensus_gap import scoring as SC                             # noqa: E402
from smart_consensus_gap import synthetic as SYN                          # noqa: E402

RESULTS: List[Tuple[str, bool, str]] = []


def check(name: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        try:
            detail = fn() or ""
            RESULTS.append((name, True, str(detail)))
        except AssertionError as e:
            RESULTS.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            RESULTS.append((name, False, f"{type(e).__name__}: {e}\n"
                                         + traceback.format_exc().splitlines()[-1]))
        return fn
    return deco


# ════════════════════════════════════════════════════════════════════════════════════════
#  1. 산식
# ════════════════════════════════════════════════════════════════════════════════════════
@check("SCG 산식 단위테스트 (consensus.scg_formula_unit_tests)")
def _t_formula() -> str:
    ut = CONS.scg_formula_unit_tests()
    bad = ut[~ut["passed"].astype(bool)]
    assert len(bad) == 0, "; ".join(f"{r['test']}({r['detail']})" for _, r in bad.iterrows())
    return f"{len(ut)}건 통과"


@check("SCG 분모에 abs 를 쓰지 않는다 (소스 검사)")
def _t_no_abs() -> str:
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "smart_consensus_gap", "consensus.py"), encoding="utf-8").read()
    i = src.index("scg[calc] =")
    line = src[i:src.index("\n", i)]
    assert "abs" not in line.lower(), f"분모에 abs 가 등장한다: {line}"
    return line.strip()


@check("YoY 부호 변화는 성장률이 아니라 전환 플래그로 분리된다")
def _t_turnaround() -> str:
    cur = np.array([100.0, -50.0, 100.0, 100.0])
    prev = np.array([50.0, 50.0, -20.0, 0.0])
    y, tp, tn, fl = FX.yoy_growth(cur, prev)
    assert abs(y[0] - 1.0) < 1e-12, y[0]
    assert tn[1] == 1 and not np.isfinite(y[1]), (tn[1], y[1])
    assert tp[2] == 1 and not np.isfinite(y[2]), (tp[2], y[2])
    assert fl[3] in ("TURNAROUND_POS", "DENOM_NEAR_ZERO"), fl[3]
    return "흑자/적자전환 분리 확인"


@check("회계기간 파서 (여러 표기 → 2020Q2 / 2020FY)")
def _t_fp() -> str:
    cases = {"2020Q2": "2020Q2", "2020.06": "2020Q2", "2Q20": "2020Q2", "2Q2020": "2020Q2",
             "FY2020": "2020FY", "2020": "2020FY", "2020A": "2020FY", "쓰레기": ""}
    for raw, want in cases.items():
        got = NORM.normalize_fiscal_period(raw)
        assert got == want, f"{raw} → {got} (기대 {want})"
    return f"{len(cases)}종 표기 확인"


@check("증권사 사명 변경 정규화 (같은 애널리스트가 갈라지지 않는다)")
def _t_broker() -> str:
    pairs = [("미래에셋대우", "미래에셋증권"), ("KDB대우증권", "미래에셋증권"),
             ("우리투자증권", "NH투자증권"), ("하나금융투자", "하나증권"),
             ("신한금융투자", "신한투자증권"), ("이베스트투자증권", "LS증권"),
             ("하이투자증권", "iM증권"), ("KTB투자증권", "다올투자증권")]
    for raw, want in pairs:
        got = NORM.normalize_broker(raw)
        assert got == want, f"{raw} → {got} (기대 {want})"
    a = NORM.make_estimator_id("삼성증권", "홍길동")
    b = NORM.make_estimator_id("키움증권", "홍길동")
    assert a != b, "동명이인이 병합되었다"
    return f"{len(pairs)}종 사명 + 동명이인 미병합"


# ════════════════════════════════════════════════════════════════════════════════════════
#  2. PIT
# ════════════════════════════════════════════════════════════════════════════════════════
def _tiny_estimates() -> "pd.DataFrame":
    rows = []
    for i, (d, v) in enumerate([("2020-01-10", 90.0), ("2020-05-01", 100.0),
                                ("2020-06-29", 110.0), ("2020-07-05", 999.0)]):
        rows.append({"published_at": pd.Timestamp(d), "report_id": f"R{i}",
                     "company_code": "000001", "broker_name_raw": f"B{i}",
                     "analyst_name_raw": f"A{i}", "metric": "EPS",
                     "fiscal_period": "2020Q3", "horizon": "FQ1", "estimate_value": v})
    return pd.DataFrame(rows)


@check("PIT: 미래 추정치는 스냅샷에 절대 들어오지 않는다")
def _t_pit_future() -> str:
    est, _ = NORM.normalize_estimates(_tiny_estimates())
    idx = PIT.EstimateIndex.build(est)
    snap = idx.latest_snapshot(pd.Timestamp("2020-06-30"), 90)
    vals = sorted(snap["estimate_value"].tolist())
    assert 999.0 not in vals, f"미래(2020-07-05) 추정치가 들어왔다: {vals}"
    assert 90.0 not in vals, f"90일 창 밖(2020-01-10) 추정치가 들어왔다: {vals}"
    assert vals == [100.0, 110.0], vals
    return f"창 안 {len(vals)}건만 선택"


@check("PIT: estimator 별 최신 1건만 남는다")
def _t_pit_latest() -> str:
    df = _tiny_estimates()
    df.loc[:, "broker_name_raw"] = "삼성증권"
    df.loc[:, "analyst_name_raw"] = "홍길동"
    est, _ = NORM.normalize_estimates(df)
    idx = PIT.EstimateIndex.build(est)
    snap = idx.latest_snapshot(pd.Timestamp("2020-06-30"), 90)
    assert len(snap) == 1, f"{len(snap)}건 (1건이어야)"
    assert float(snap["estimate_value"].iloc[0]) == 110.0, snap["estimate_value"].tolist()
    return "최신 1건 유지"


@check("PIT: 애널리스트 정확도는 아직 발표되지 않은 실적을 쓰지 않는다")
def _t_pit_skill() -> str:
    est = pd.DataFrame([{"published_at": pd.Timestamp("2020-01-15"), "report_id": "R1",
                         "company_code": "000001", "broker_name_raw": "삼성증권",
                         "analyst_name_raw": "홍길동", "metric": "EPS",
                         "fiscal_period": "2019Q4", "horizon": "FQ1", "estimate_value": 100.0},
                        {"published_at": pd.Timestamp("2020-01-15"), "report_id": "R2",
                         "company_code": "000001", "broker_name_raw": "키움증권",
                         "analyst_name_raw": "김철수", "metric": "EPS",
                         "fiscal_period": "2019Q4", "horizon": "FQ1", "estimate_value": 120.0}])
    est, _ = NORM.normalize_estimates(est)
    act = pd.DataFrame([{"company_code": "000001", "metric": "EPS", "fiscal_period": "2019Q4",
                         "actual_value": 110.0,
                         "actual_announced_at": pd.Timestamp("2020-02-14")}])
    act = NORM.normalize_actuals(act)
    ev = SK.build_realized_errors(est, act, "EPS", 90)
    assert len(ev) == 2, f"이벤트 {len(ev)}건"
    idx = SK.SkillIndex.build(ev, "EPS")
    cfg = CFG.base_config()
    before = idx.at(pd.Timestamp("2020-02-14"), cfg)     # 발표 당일 → 아직 못 쓴다
    after = idx.at(pd.Timestamp("2020-02-15"), cfg)
    assert int(before["n_events"].sum()) == 0, f"발표 당일에 이력이 잡혔다: {before['n_events'].tolist()}"
    assert int(after["n_events"].sum()) == 2, after["n_events"].tolist()
    return "발표 당일 차단 / 다음날 반영"


@check("PIT: 유니버스는 t 이하 최신 스냅샷만 본다")
def _t_pit_universe() -> str:
    um = pd.DataFrame([
        {"date": pd.Timestamp("2020-03-31"), "company_code": "000001",
         "universe_id": "KOSPI200_PIT", "is_member": True},
        {"date": pd.Timestamp("2020-09-30"), "company_code": "000002",
         "universe_id": "KOSPI200_PIT", "is_member": True}])
    ui = PIT.UniverseIndex.build(NORM.normalize_universe(um), "KOSPI200_PIT")
    assert ui.at(pd.Timestamp("2020-06-30")) == ["000001"], ui.at(pd.Timestamp("2020-06-30"))
    assert ui.at(pd.Timestamp("2020-12-31")) == ["000002"], ui.at(pd.Timestamp("2020-12-31"))
    return "미래 구성종목 미사용"


# ════════════════════════════════════════════════════════════════════════════════════════
#  3. 가중치 / 결측
# ════════════════════════════════════════════════════════════════════════════════════════
@check("가중치: 합=1, 상한 준수, infeasible 감지")
def _t_weights() -> str:
    rng = np.random.default_rng(0)
    for trial in range(200):
        n = int(rng.integers(1, 25))
        w = rng.lognormal(0, 2.0, size=n)
        g = np.zeros(n, dtype=np.int64)
        cap = float(rng.choice([0.25, 0.35, 0.5]))
        out, inf = CONS.apply_weight_cap(w, g, 1, cap)
        assert abs(out.sum() - 1.0) < 1e-10, f"합 {out.sum()} (n={n})"
        if not inf[0]:
            assert out.max() <= cap + 1e-9, f"상한 초과 {out.max()} > {cap} (n={n})"
        else:
            assert n * cap < 1.0 + 1e-12, f"infeasible 오탐 n={n} cap={cap}"
    return "무작위 200회"


@check("결측 팩터는 0 으로 채우지 않고 후보에서 제외된다")
def _t_no_impute() -> str:
    cfg = CFG.base_config()
    df = pd.DataFrame({"asof": [pd.Timestamp("2020-06-30")] * 4,
                       "company_code": ["000001", "000002", "000003", "000004"],
                       "SCG": [0.1, 0.2, np.nan, 0.4],
                       "FQ1_EPS_YOY": [0.1, 0.2, 0.3, 0.4],
                       "FY1_EPS_YOY": [0.1, 0.2, 0.3, 0.4],
                       "EPS12MF_REV_1M": [0.1, 0.2, 0.3, 0.4],
                       "INST_20D": [0.1, 0.2, 0.3, 0.4],
                       "FOREIGN_20D": [0.1, 0.2, 0.3, np.nan]})
    s = SC.cross_section_scores(df, CFG.FACTORS_6F, cfg)
    assert list(s["complete"]) == [True, True, False, False], s["complete"].tolist()
    assert not np.isfinite(s["composite"].iloc[2]), s["composite"].iloc[2]
    assert not np.isfinite(s["composite"].iloc[3]), s["composite"].iloc[3]
    sel = SC.rank_and_select(s, 30)
    assert set(sel["company_code"]) == {"000001", "000002"}, sel["company_code"].tolist()
    return "불완전 행 자동 제외"


@check("일반 컨센서스는 최소 3인 미달 시 결측이다")
def _t_min_analysts() -> str:
    base = {"asof": pd.Timestamp("2020-06-30"), "company_code": "000001",
            "fiscal_period": "2020Q3", "metric": "EPS", "age_days": 5.0,
            "published_at": pd.Timestamp("2020-06-25"), "report_id": "x"}
    for n, want_nan in ((2, True), (3, False)):
        snap = pd.DataFrame([{**base, "estimator_id": f"B{i}::a{i}", "broker_name_norm": f"B{i}",
                              "analyst_name_norm": f"a{i}", "estimate_value": 100.0 + i}
                             for i in range(n)])
        g = CONS.general_consensus(snap)
        got_nan = bool(g["general_consensus"].isna().all())
        assert got_nan == want_nan, f"n={n} → nan={got_nan}"
    return "2인 결측 / 3인 산출"


# ════════════════════════════════════════════════════════════════════════════════════════
#  4. 설정 / 강건성 규율
# ════════════════════════════════════════════════════════════════════════════════════════
@check("§25 기본값이 리터럴 스냅샷과 일치한다")
def _t_base_cfg() -> str:
    diffs = CFG.base_snapshot_diff(CFG.base_config())
    assert not diffs, "; ".join(diffs)
    return "일치"


@check("강건성 변형은 사전 정의 + 한 번에 한 축만")
def _t_variants() -> str:
    cfg = CFG.base_config()
    seen: Dict[str, int] = {}
    for v, vc in CFG.variant_configs(cfg):
        assert len(v.overrides) == 1, f"{v.variant_id}: {v.overrides}"
        base = cfg.definition_dict()
        cur = vc.definition_dict()
        changed = [k for k in base if base[k] != cur[k]]
        assert changed == [v.axis], f"{v.variant_id}: 바뀐 축 {changed}"
        seen[v.axis] = seen.get(v.axis, 0) + 1
    return f"{len(CFG.PREDEFINED_ROBUSTNESS_VARIANTS)}개 변형 / {len(seen)}개 축"


@check("계약: 파생 컬럼이 없는 원본도 통과한다")
def _t_contract_raw() -> str:
    raw = _tiny_estimates().drop(columns=["horizon"])
    res = C.validate(C.coerce(raw, C.ANALYST_ESTIMATES), C.ANALYST_ESTIMATES)
    assert res.ok, f"{res.messages}"
    est, rep = NORM.normalize_estimates(raw)
    for col in C.NORMALIZED_ESTIMATE_COLUMNS:
        assert col in est.columns, f"정규화 후 {col} 없음"
    return f"{rep.rows_out}행 정규화"


@check("종목코드 정규화 (앞자리 0 유지)")
def _t_code() -> str:
    s = C.normalize_code(pd.Series(["5930", "005930", "A005930", "005930.0", 5930]))
    assert list(s) == ["005930"] * 5, list(s)
    return "5종 표기 → 005930"


# ════════════════════════════════════════════════════════════════════════════════════════
#  5. 엔드투엔드 (합성 픽스처, 소형)
# ════════════════════════════════════════════════════════════════════════════════════════
@check("엔드투엔드: 합성 픽스처로 전 구간 통과 + CRITICAL 감사 0 실패")
def _t_e2e() -> str:
    import tempfile

    from run_smart_consensus_gap import run
    with tempfile.TemporaryDirectory() as td:
        r = run(synthetic=True, run_robustness=False, run_bootstrap=False, output_root=td,
                backtest_start="2018-06-30")
        assert r["status"] in ("SYNTHETIC_REHEARSAL_NO_REAL_DATA", "COMPLETED"), r["status"]
        a = r["audit"]
        bad = a[(a["severity"] == "CRITICAL") & (a["status"] == "FAIL")]
        assert len(bad) == 0, "; ".join(bad["check"].tolist())
        files = os.listdir(r["out_dir"])
        from smart_consensus_gap.reporting import FILES
        missing = [f for f in FILES.values()
                   if f not in files and f.replace(".parquet", ".csv") not in files]
        assert not missing, f"산출물 누락 {missing}"
        return f"{len(files)}개 산출물 / CRITICAL 0 실패"


@check("엔드투엔드: 벤더 필드가 있으면 EXACT 가 함께 돌고 오염 0")
def _t_e2e_vendor() -> str:
    import tempfile

    from run_smart_consensus_gap import run
    os.environ["SCG_SYNTHETIC_VENDOR"] = "1"
    try:
        with tempfile.TemporaryDirectory() as td:
            r = run(synthetic=True, run_robustness=False, run_bootstrap=False, output_root=td,
                    backtest_start="2018-06-30")
            a = r["audit"]
            bad = a[(a["severity"] == "CRITICAL") & (a["status"] == "FAIL")]
            assert len(bad) == 0, "; ".join(bad["check"].tolist())
            perf = r["performance"]
            row = perf[perf["strategy"] == CFG.STRAT_IBK_7F_EXACT]
            assert len(row), "IBK_7F_EXACT 결과 없음"
            assert "status" not in row.columns or pd.isna(row["status"].iloc[0]), \
                f"EXACT 가 스킵되었다: {row.get('status')}"
            assert str(row["mode"].iloc[0]) == CFG.MODE_ORIGINAL_EXACT, row["mode"].iloc[0]
            names = set(a["check"])
            assert "EXACT_FRAME_USES_VENDOR_ONLY" in names
            return "EXACT 동시 실행 + 오염 0"
    finally:
        os.environ.pop("SCG_SYNTHETIC_VENDOR", None)


@check("엔드투엔드: 벤더가 없으면 EXACT 는 SKIPPED_MISSING_VENDOR_FIELDS")
def _t_e2e_skip() -> str:
    import tempfile

    from run_smart_consensus_gap import run
    with tempfile.TemporaryDirectory() as td:
        r = run(synthetic=True, run_robustness=False, run_bootstrap=False, output_root=td,
                backtest_start="2020-06-30")
        perf = r["performance"]
        row = perf[perf["strategy"] == CFG.STRAT_IBK_7F_EXACT]
        assert len(row), "EXACT 행이 아예 없다 (스킵 사실도 기록되어야 한다)"
        assert str(row["status"].iloc[0]) == "SKIPPED_MISSING_VENDOR_FIELDS", row["status"].iloc[0]
        fac = r["factors"]
        assert not np.isfinite(fac["SURPRISE_PROB"].to_numpy(dtype=float)).any(), \
            "PUBLIC_REPRO 인데 서프라이즈 확률이 채워졌다"
        return "스킵 기록 + 프록시 미주입"


@check("데이터가 없고 폴백을 끄면 NO_DATA 로 끝난다")
def _t_no_data() -> str:
    import tempfile

    from run_smart_consensus_gap import run
    with tempfile.TemporaryDirectory() as td:
        r = run(allow_synthetic_fallback=False, output_root=td, data_roots=[td])
        assert r["status"] == "NO_DATA", r["status"]
        return "NO_DATA"


def main() -> int:
    print("=" * 92)
    print(f"  {CFG.SPEC_ID} 자가검정")
    print("=" * 92)
    width = max(len(n) for n, _, _ in RESULTS)
    n_fail = 0
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name.ljust(width)}  {detail.splitlines()[0] if detail else ''}")
        if not ok:
            n_fail += 1
            for line in detail.splitlines()[1:]:
                print(f"         {line}")
    print("-" * 92)
    print(f"  {len(RESULTS) - n_fail}/{len(RESULTS)} 통과")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
