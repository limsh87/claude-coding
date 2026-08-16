# -*- coding: utf-8 -*-
"""PART 6 실행 순서 STEP 1~10 (+ 사람이 잠금을 연 경우에만 Phase 2).

STEP 1 카나리 → 2 G-C0 → 3 통관 수집 → 4 G-C6 해상도 동결 → 5 G-C1·G-C2
     → 6 G-C3(실패 시 종료) → 7 G-C4(실패 시 arm B 강등) → 8 G-C7·G-C8
     → 9 4개 arm 신호 + 상관감사 → 10 Phase 0/1 보고서 → **여기서 멈춘다**
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import backtest as bt
from . import factor as fx
from . import gates as gt
from .data import (CUSTOMS_ENDPOINT, DART_ENDPOINT, ISTANS_URL, CacheLake,
                   DataUnavailable, SyntheticWorld, probe_endpoints)
from .spec import (ARMS, CONTROL_ARM, CXD, FRAME, LOCK, PRIMARY_ARM, RULES,
                   UNVERIFIED_LOG, KillCriteria, KillLedger, spec_sha256)

NA = "__NA__"


def _log(msg: str) -> None:
    print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  축 유도 — 신성질별 계층 (세분류 → 중분류 → 대분류)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def derive_axes(cell: pd.Series) -> pd.DataFrame:
    """세분류 코드에서 상위 층을 유도한다. 실데이터에서는 관세청 연계표의 계층을 그대로 쓴다."""
    s = cell.astype(str)
    num = pd.to_numeric(s.str.extract(r"(\d+)")[0], errors="coerce")
    return pd.DataFrame({
        "cell": cell,
        "cell_mid": np.where(num.notna(), "M" + (num // 10).astype("Int64").astype(str), None),
        "cell_dae": np.where(num.notna(), "D" + (num // 40).astype("Int64").astype(str), None),
    }, index=cell.index)


def missing_rate_by_axis(customs: pd.DataFrame, axmap: pd.DataFrame) -> Dict[str, float]:
    """G-C6 — 층별 IEG 결측률. 세세분류는 합성 세계에 존재하지 않으므로 보고하지 않는다."""
    out: Dict[str, float] = {}
    for axis_name, col in (("SINSUNGJIL_SEBUN", "cell"),
                           ("SINSUNGJIL_JUNG", "cell_mid"),
                           ("SINSUNGJIL_DAE", "cell_dae")):
        m = customs.merge(axmap.drop_duplicates("cell"), on="cell", how="left")
        agg = (m.dropna(subset=[col]).groupby([col, "month"], observed=True, as_index=False)
               ["exp_usd"].sum().rename(columns={col: "cell"}))
        if not len(agg):
            continue
        P = fx.build_cell_panel(agg)
        # 연구기간 내에서만 결측률을 잰다 (앞쪽 12/60M 워밍업은 정의상 결측)
        w = P[(P["month"] >= FRAME["research_start"]) & (P["month"] <= FRAME["research_end"])]
        out[axis_name] = float(w["IEG"].isna().mean()) if len(w) else 1.0
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  패널 조립 — PIT 결합
# ═══════════════════════════════════════════════════════════════════════════════════════════
def assemble_panel(univ: pd.DataFrame, sec: pd.DataFrame, cell_panel: pd.DataFrame,
                   fgr: pd.DataFrame, axmap: pd.DataFrame,
                   drop_renamed: bool = False) -> pd.DataFrame:
    """C1 × 리밸일 패널에 셀 지표(통관)와 기업 지표(DART)를 **PIT 로만** 붙인다."""
    P = univ[univ["in_C1"].fillna(False)].copy()
    P["rebal"] = pd.to_datetime(P["rebal"])
    P = P.merge(sec[["code", "cell", "renamed", "has_goodwill"]], on="code", how="left")
    if drop_renamed:
        P = P[~P["renamed"].fillna(False)]
    P = P.merge(axmap.drop_duplicates("cell"), on="cell", how="left")

    cp = cell_panel.copy()
    cp["cell"] = cp["cell"].fillna(NA)
    cp = cp.sort_values("knowledge_date")
    P["cell"] = P["cell"].fillna(NA)
    P = P.sort_values("rebal")
    P = pd.merge_asof(P, cp[["cell", "knowledge_date", "IEG", "TREND", "CYCLE", "exp_usd"]],
                      left_on="rebal", right_on="knowledge_date", by="cell",
                      direction="backward")
    P = P.rename(columns={"knowledge_date": "kd_cell"})

    f = fgr.copy().sort_values("knowledge_date")
    P = P.sort_values("rebal")
    P = pd.merge_asof(P, f[["code", "knowledge_date", "FGR", "rev_ttm", "rev_yoy"]],
                      left_on="rebal", right_on="knowledge_date", by="code",
                      direction="backward")
    P = P.rename(columns={"knowledge_date": "kd_firm"})
    P.loc[P["cell"] == NA, ["cell", "cell_mid", "cell_dae", "IEG", "TREND", "CYCLE"]] = np.nan
    return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  실행
# ═══════════════════════════════════════════════════════════════════════════════════════════
def run(world: Optional[dict] = None, outdir: str = "outputs/cxd",
        cache_dirs: Optional[List[str]] = None,
        open_returns_reason: str = "", top_n: int = 50) -> dict:
    os.makedirs(outdir, exist_ok=True)
    art: Dict[str, object] = {}
    kill = KillLedger()
    board = gt.GateBoard()
    _log(f"\n{'=' * 92}\n  U250-F1 / F-11 CXD v1.0 — 사전등록 명세 실행체")
    _log(f"  SPEC SHA256 = {spec_sha256()}\n{'=' * 92}")

    # ── STEP 0. 캐시 하베스트 (캐시 최우선 — 신규 수집은 예외) ────────────────────────────
    lake = CacheLake(cache_dirs or ["./cache", "./cxd_cache", "/home/user/work",
                                    os.path.expanduser("~/quant"), "D:\\quant"]).scan()
    _log(f"\n[STEP 0] 캐시 스캔 — 파일 {lake.scanned:,}개 검사, 역할 적중 {len(lake.found)}종")
    art["cache_table"] = lake.table()

    # ── STEP 1. 카나리 5항목 ─────────────────────────────────────────────────────────────
    probe = probe_endpoints({
        "customs": CUSTOMS_ENDPOINT, "dart": DART_ENDPOINT + "/list.json", "istans": ISTANS_URL})
    art["probe"] = probe
    synthetic = world is not None
    can = gt.canary(probe.assign(source=probe["source"]),
                    cells_found=len(world["cells"]) if synthetic else 0,
                    earliest_month=(pd.Timestamp(world["months"][0]) if synthetic else None),
                    linkage_ok=synthetic, istans_ok=False)
    art["canary"] = can
    _log(f"\n[STEP 1] 카나리\n{can.to_string(index=False)}")
    if not synthetic and not can["결과"].all():
        _log("\n  ⛔ 카나리 실패 → 전면 실행 금지 (PART 4.1). 실데이터 경로를 열 수 없습니다.")
        art["halt"] = "CANARY_FAIL"
        return art

    W = world
    axmap = derive_axes(pd.Series(W["cells"], name="cell"))

    # ── STEP 2. G-C0 연계표 ──────────────────────────────────────────────────────────────
    board.add(gt.gate_C0(W.get("hs_cell_map")))
    _log(f"[STEP 2] G-C0 {board.get('G-C0').mark} — {board.get('G-C0').value}")

    # ── STEP 3. 통관 수집 → 셀 패널 ──────────────────────────────────────────────────────
    customs = W["customs"]
    _log(f"[STEP 3] 통관 패널 {len(customs):,}행 "
         f"({customs['month'].min():%Y-%m} ~ {customs['month'].max():%Y-%m}, "
         f"셀 {customs['cell'].nunique()}개)")

    # ── STEP 4. G-C6 해상도 결정 → 동결 ─────────────────────────────────────────────────
    miss = missing_rate_by_axis(customs, axmap)
    g6 = board.add(gt.gate_C6(miss))
    _log(f"[STEP 4] G-C6 {g6.mark} — {g6.value}")

    cell_panel = fx.build_cell_panel(customs)
    cell_panel = cell_panel.merge(axmap.drop_duplicates("cell"), on="cell", how="left")

    # ── 기업 축 ─────────────────────────────────────────────────────────────────────────
    rev = W["rev"].copy()
    fgr = fx.compute_fgr(rev)
    fgr["rev_yoy"] = (fgr.sort_values(["code", "qend"]).groupby("code", observed=True)["rev_ttm"]
                      .pct_change(4))

    # ── STEP 5. G-C1 매핑률 · G-C2 오염 ─────────────────────────────────────────────────
    panel_in = assemble_panel(W["univ"], W["sec"], cell_panel, fgr, axmap, drop_renamed=False)
    panel_ex = assemble_panel(W["univ"], W["sec"], cell_panel, fgr, axmap, drop_renamed=True)
    g1 = board.add(gt.gate_C1(panel_in))
    _log(f"[STEP 5] G-C1 {g1.mark} — {g1.value}")

    armA = ARMS.get(PRIMARY_ARM)
    sig_in = fx.build_signal(panel_in, armA)
    sig_ex = fx.build_signal(panel_ex, armA)
    g2 = board.add(gt.gate_C2(sig_in, sig_ex))
    _log(f"         G-C2 {g2.mark} — {g2.value}")

    # ── STEP 6. G-C3 통관-매출 연결 (실패 시 여기서 종료) ───────────────────────────────
    rebals = W["univ"]["rebal"].unique()
    cp_at_rebal = _at_rebal(cell_panel, rebals, key="cell")          # 신호 축 = 세분류
    mid_at_rebal = _at_rebal(axis_cell_panel(customs, axmap, "cell_mid"),
                             rebals, key="cell_mid")                  # 게이트 축 = 중분류
    firm_for_g3 = sig_in[["rebal", "code", "cell_mid", "rev_yoy"]].copy()
    g3 = board.add(gt.gate_C3(mid_at_rebal, firm_for_g3, axis_col="cell_mid"))
    _log(f"[STEP 6] G-C3 {g3.mark} — {g3.value}")
    if g3.passed is False:
        try:
            kill.fire("KILL-1", f"G-C3 실패 — {g3.value}", hard=True)
        except KillCriteria as e:
            _log(f"\n  ⛔ {e}")
            art.update(board=board, kill=kill, halt="MECHANISM_FAIL",
                       signal=sig_in, cell_panel=cell_panel)
            _write_reports(art, outdir, synthetic=True, world=W)
            return art

    # ── STEP 7. G-C4 기제 전제 (실패 시 arm B 로 강등) ──────────────────────────────────
    g4 = board.add(gt.gate_C4(sig_in))
    _log(f"[STEP 7] G-C4 {g4.mark} — {g4.value}")

    # ── STEP 8. G-C5 / G-C7 / G-C8 ──────────────────────────────────────────────────────
    board.add(gt.gate_C5(None))
    g7 = board.add(gt.gate_C7(cp_at_rebal))
    g8 = board.add(gt.gate_C8(W["sec"]))
    _log(f"[STEP 8] G-C5 {board.get('G-C5').mark} · G-C7 {g7.mark} ({g7.value}) · "
         f"G-C8 {g8.mark} ({g8.value})")

    # ── STEP 9. 4개 arm 신호 + 상관 감사 ────────────────────────────────────────────────
    sigs: Dict[str, pd.DataFrame] = {}
    for arm in ARMS.all():
        sigs[arm.key] = fx.build_signal(panel_in, arm)
        cov = sigs[arm.key]["CXD_rank"].notna().mean()
        _log(f"[STEP 9] arm {arm.key} ({arm.name}) — 신호 커버리지 {cov:.1%}")
    art["signals"] = sigs

    corr = gt.correlation_audit(sigs[PRIMARY_ARM], kill)
    art["corr"] = corr
    if len(corr):
        _log(f"\n  상관 감사\n{corr.to_string(index=False)}")

    verdict = gt.phase0_verdict(board, kill)
    art.update(board=board, kill=kill, verdict=verdict, cell_panel=cell_panel,
               diag=bt.signal_diagnostics(sigs[PRIMARY_ARM]))

    # ── STEP 10. Phase 0/1 보고서 → 여기서 멈춘다 ───────────────────────────────────────
    _log(f"\n[STEP 10] Phase 0 판정 — 차단게이트 실패 {verdict['blocking_fail'] or '없음'} · "
         f"판정불가 {verdict['undetermined'] or '없음'} · "
         f"곱구조 강등 {'예' if verdict['demote_to_B'] else '아니오'}")
    _log(f"          미래수익률 개봉 가능 = {verdict['may_open_returns']} "
         f"(잠금 상태: {'열림' if LOCK.opened else '닫힘'}, 차단된 시도 {LOCK.blocked}회)")

    # ── Phase 2 — 사람이 잠금을 연 경우에만 ─────────────────────────────────────────────
    if open_returns_reason and verdict["may_open_returns"]:
        LOCK.open(open_returns_reason)
        art["phase2"] = _phase2(sigs, panel_in, top_n=top_n)
        _log("\n[Phase 2] 백테스트 완료 (잠금 해제 사유가 기록되었습니다)")
    elif open_returns_reason:
        _log("\n  ⚠ 잠금 해제 요청이 있었으나 Phase 0 차단게이트가 통과하지 못해 열지 않았습니다.")

    _write_reports(art, outdir, synthetic=True, world=W)
    return art


def axis_cell_panel(customs: pd.DataFrame, axmap: pd.DataFrame, col: str) -> pd.DataFrame:
    """지정한 신성질별 층으로 수출액을 **먼저 합산한 뒤** IEG/TREND 를 계산한다.

    세분류 IEG 를 중분류 라벨로 재사용하면 한 중분류가 10개 행으로 중복되어
    상관계수가 셀 수가 아니라 하위 셀 수에 좌우된다. 게이트 축(중분류)은
    반드시 그 층에서 집계한 값으로 판정해야 한다(R-09).
    """
    m = customs.merge(axmap.drop_duplicates("cell"), on="cell", how="left")
    agg = (m.dropna(subset=[col]).groupby([col, "month"], observed=True, as_index=False)
           ["exp_usd"].sum().rename(columns={col: "cell"}))
    P = fx.build_cell_panel(agg)
    return P.rename(columns={"cell": col})


def _at_rebal(panel: pd.DataFrame, rebals, key: str = "cell") -> pd.DataFrame:
    """리밸일 기준 PIT 유효한 최신 셀 관측만 남긴다 (G-C3·G-C7 판정용)."""
    R = pd.DataFrame({"rebal": pd.to_datetime(pd.Series(sorted(pd.unique(rebals))))})
    cp = panel.dropna(subset=[key]).sort_values("knowledge_date")
    cols = [c for c in ("knowledge_date", "IEG", "TREND", "CYCLE", key) if c in cp.columns]
    out = [pd.merge_asof(R, g[cols], left_on="rebal", right_on="knowledge_date",
                         direction="backward").assign(**{key: c})
           for c, g in cp.groupby(key, observed=True)]
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _phase2(sigs: Dict[str, pd.DataFrame], panel: pd.DataFrame, top_n: int) -> dict:
    base_c1 = bt.backtest(panel.assign(_all=True), "베이스라인 C1 동일가중", sig=None,
                          universe_mask="_all")
    res, ics, pv = {}, {}, {}
    for k, s in sigs.items():
        res[k] = bt.backtest(s, f"arm {k}", top_n=top_n)
        tbl, ic = bt.rank_ic(s)
        ics[k] = tbl.assign(arm=k)
        pv[f"arm {k}"] = float(tbl["IC_p"].iloc[0])
    rows = []
    for k, r in res.items():
        g, n = r.stats("gross"), r.stats("net")
        rows.append(dict(arm=k, gross_CAGR=g["cagr"], net_CAGR=n["cagr"],
                         net_vol=n["vol"], net_Sharpe=n["sharpe"], net_MDD=n["mdd"],
                         승률=n["hit"], 회전율=float(r.turnover.mean()),
                         초과net=n["cagr"] - base_c1.stats("net")["cagr"]))
    perf = pd.DataFrame(rows)
    bl = base_c1.stats("net")
    perf.loc[len(perf)] = dict(arm="C1(베이스라인)", gross_CAGR=base_c1.stats("gross")["cagr"],
                               net_CAGR=bl["cagr"], net_vol=bl["vol"], net_Sharpe=bl["sharpe"],
                               net_MDD=bl["mdd"], 승률=bl["hit"],
                               회전율=float(base_c1.turnover.mean()), 초과net=0.0)
    return dict(perf=perf, ic=pd.concat(ics.values(), ignore_index=True),
                quint=bt.quintile_profile(sigs[PRIMARY_ARM]),
                fdr=bt.bh_fdr(pv),
                kill5=bt.kill5_check(res[PRIMARY_ARM], res[CONTROL_ARM], base_c1),
                results=res, base=base_c1)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  산출물
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _write_reports(art: dict, outdir: str, synthetic: bool, world: dict) -> None:
    os.makedirs(outdir, exist_ok=True)
    board: gt.GateBoard = art.get("board")
    files = {}
    if board is not None:
        files["phase0_gates.csv"] = board.frame()
    for k, name in (("canary", "canary.csv"), ("probe", "endpoint_probe.csv"),
                    ("corr", "correlation_audit.csv"), ("diag", "signal_diagnostics.csv"),
                    ("cache_table", "cache_inventory.csv")):
        if isinstance(art.get(k), pd.DataFrame):
            files[name] = art[k]
    p2 = art.get("phase2")
    if p2:
        files["phase2_performance.csv"] = p2["perf"]
        files["phase2_rank_ic.csv"] = p2["ic"]
        files["phase2_quintile.csv"] = p2["quint"]
        files["phase2_bh_fdr.csv"] = p2["fdr"]
    files["unverified_log.csv"] = pd.DataFrame(UNVERIFIED_LOG)
    for fn, df in files.items():
        df.to_csv(os.path.join(outdir, fn), index=False, encoding="utf-8-sig")
    sig = art.get("signals", {}).get(PRIMARY_ARM)
    if sig is not None:
        keep = [c for c in ("rebal", "code", "cell", "IEG", "TREND", "CYCLE", "FGR",
                            "DIV", "DIV_z", "IEG_z", "CXD_raw", "CXD", "CXD_rank")
                if c in sig.columns]
        sig[keep].to_parquet(os.path.join(outdir, "cxd_signal_armA.parquet"), index=False)
    art["files"] = sorted(files) + (["cxd_signal_armA.parquet"] if sig is not None else [])
