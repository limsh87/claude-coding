#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-SACN 통합 테스트 — 수집 계층만 합성으로 대체하고 FULL 경로 전체를 실물 실행한다.

스모크(SMOKE 모드)는 L0 에서 멈추므로 유니버스·Phase0·백테스트·가설검정·산출물 생성
경로가 한 줄도 실행되지 않는다. 네트워크가 없는 환경에서 그 구간을 검증하는 유일한 방법이
이 테스트다. 여기서 도는 함수는 전부 배포될 실물 코드다(가짜는 '데이터'뿐이다).
"""
from __future__ import annotations
import os, re, sys, time, shutil, tempfile, importlib.util, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "strategies", "arc_sacn_shared_coverage_network.py")


def load(cache: str, mode: str = "FULL"):
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'^RUN_MODE = "FULL"', f'RUN_MODE = "{mode}"', src, flags=re.M)
    src = re.sub(r'^GDRIVE_ROOT_CANDIDATES = \[.*?\n\]',
                 f'GDRIVE_ROOT_CANDIDATES = [{cache!r}]', src, flags=re.M | re.S)
    src = re.sub(r'^GDRIVE_ADOPT_DIRS = \[.*?\n\]',
                 f'GDRIVE_ADOPT_DIRS = [{cache!r}]', src, flags=re.M | re.S)
    src = re.sub(r'^LOCAL_CACHE_ROOT = ".*?"', f'LOCAL_CACHE_ROOT = {cache!r}', src, flags=re.M)
    src = src.replace(
        "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
        "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n"
        "    if os.environ.get('SACN_NO_PIP'): return True, 'skipped'")
    # 짧게 돌리기 위한 축소 (경로는 동일, 규모만 축소)
    src = re.sub(r'^BACKTEST_START = ".*?"', 'BACKTEST_START = "2021-01-01"', src, flags=re.M)
    src = re.sub(r'^BACKTEST_END   = ".*?"', 'BACKTEST_END   = "2026-07-31"', src, flags=re.M)
    p = os.path.join(cache, "sacn_itest.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("sacn_itest", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["sacn_itest"] = m
    spec.loader.exec_module(m)              # ENV['ipython']=False → main() 자동실행 안 함
    return m


def synth_ctx(M, months):
    """실제 스키마 그대로의 합성 수집 결과. 이후 단계는 전부 실물 함수가 처리한다."""
    np, pd = M.np, M.pd
    rng = np.random.default_rng(7)
    S = M._synth(n_codes=620, n_months=len(months) + 8, n_analysts=420)
    codes = S["codes"]
    sec = S["sec"].copy()
    # ★ 생존편향 검증: 20% 를 실제로 상장폐지시킨다
    dl_idx = rng.choice(len(sec), size=max(1, len(sec) // 5), replace=False)
    dmon = [months[int(rng.integers(1, len(months) - 1))] for _ in dl_idx]
    sec.loc[dl_idx, "delisting_date"] = pd.to_datetime(dmon)

    daily = S["daily"]
    # 폐지 종목은 폐지일 이후 가격을 실제로 지운다 (안 지우면 생존편향 테스트가 무의미)
    dmap = dict(zip(sec.loc[dl_idx, "code"], pd.to_datetime(dmon)))
    if dmap:
        bad = daily["code"].map(dmap)
        daily = daily[bad.isna() | (M.as_ts_series(daily["date"]) <= bad)]

    panel = M.build_price_panel(daily.copy(), months)
    snaps = pd.DataFrame([{"snap_date": m, "code": c, "market": "KOSPI"}
                          for m in months for c in codes
                          if not (c in dmap and M.as_ts(m) > dmap[c])])

    mcap = S["mcap"][S["mcap"]["month"].isin(months)].copy()
    fund = S["fund"].merge(mcap[["code", "month"]], on=["code", "month"], how="inner")
    nonequity = pd.DataFrame(columns=["snap", "code", "kind"])
    flags = M.build_exclusion_flags(sec, nonequity)
    sector = M.build_sector_map(sec)

    # 리포트 원장 (report master 실제 스키마)
    led = S["ledger"]
    led = led[M.as_ts_series(led["pub_date"]) >= M.as_ts(months[0]) - pd.DateOffset(months=14)]
    rep = pd.DataFrame({
        "report_uid": [M.sha1_str("r", i) for i in range(len(led))],
        "source": rng.choice(["hankyung", "naver", "hankyung+naver"], len(led)),
        "pub_date": M.as_ts_series(led["pub_date"].to_numpy()),
        "title": "합성 리포트", "stock_code": led["code"].to_numpy(),
        "stock_name": "합성", "broker_id": led["broker_id"].to_numpy(),
        "broker_name": led["broker_name"].to_numpy(),
        "analyst_raw": [a.split("@")[0] for a in led["analyst_key"]],
        "target_price": led["target_price"].to_numpy(), "opinion": "BUY",
    })
    rep = M.apply_publication_lag(rep)
    # 15% 는 애널리스트 식별 실패로 둔다 (Phase 0 게이트가 실제로 판정하도록)
    keep = rng.random(len(led)) > 0.15
    L = pd.DataFrame({
        "report_uid": rep["report_uid"].to_numpy()[keep],
        "analyst_id": [a.split("@")[0] for a in led["analyst_key"][keep]],
        "broker_id": led["broker_id"].to_numpy()[keep],
        "broker_name": led["broker_name"].to_numpy()[keep],
        "stock_code": led["code"].to_numpy()[keep],
        "pub_date": M.as_ts_series(led["pub_date"].to_numpy()[keep]),
        "target_price": led["target_price"].to_numpy()[keep],
        "link_method": "list_field", "link_conf": 0.98, "role": "lead",
    })
    A = L.groupby("analyst_id", as_index=False).agg(broker_id=("broker_id", "first"))
    return {"sec": sec, "snapshots": snaps, "px": daily, "panel": panel, "mcap": mcap,
            "fund": fund, "nonequity": nonequity, "flags": flags, "sector": sector,
            "reports": rep, "analysts": A, "links": L}


def main():
    cache = tempfile.mkdtemp(prefix="sacn_itest_")
    os.environ.update(SACN_NO_PIP="1", TQDM_DISABLE="1", ARC_SACN_ROOT=cache)
    t0 = time.time()
    rc = 1
    try:
        M = load(cache)
        months = M.month_range(M.BACKTEST_START, M.BACKTEST_END)
        M.RESEARCH_COLLECT = False
        M.collect_all = lambda mo: synth_ctx(M, mo)
        M.fetch_retail_share = lambda *a, **kw: M.pd.DataFrame(
            columns=["code", "month", "retail_share"])
        M.index_benchmarks = lambda dates: {}
        res = M.main()
        v = (res.get("verdict") or {}).get("verdict")
        outs = res.get("outputs", [])
        print(f"\n=== 통합 테스트 결과 ===")
        print(f"판정        : {v}")
        print(f"산출물      : {len(outs)}개")
        need = {"PHASE0_DATA_FEASIBILITY.md", "run_summary.json", "metrics_all_configs.csv",
                "equity_curves.parquet", "trade_log.parquet", "hypothesis_test_report.md",
                "mechanism_tests.md", "cost_sensitivity.md", "delisting_sensitivity.md",
                "OPEN_QUESTIONS.md", "FINAL_VERDICT.md"}
        got = {os.path.basename(p) for p in outs}
        miss = need - got
        print(f"§10 필수산출: {len(need - miss)}/{len(need)}" + (f"  누락={miss}" if miss else "  전부 생성"))
        rc = 0 if (v and not miss) else 1
    except Exception:
        traceback.print_exc()
    finally:
        print(f"소요 {time.time()-t0:.1f}s")
        shutil.rmtree(cache, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
