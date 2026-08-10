
# ────────────────────────────────────────────────────────────────────────────────────────
#  L5-A  어블레이션 11종 (§8.2) + BH-FDR 다중검정 보정 (§8.3)
#  ★ 모든 팔은 assemble_final() 하나를 통과한다. 기준선과 절제팔이 서로 다른 계산경로를
#  ★ 비용 차감 전/후를 반드시 병기한다(§8.1). 비용 전만 보고하는 것은 금지다.
# ────────────────────────────────────────────────────────────────────────────────────────

ABLATIONS = [
    ("A1", "ΔTONE_resid 단독", "축 A 순기여",
     dict(use_axes=("A",), use_excl=True)),
    ("A2", "ΔTONE 직교화 미적용 단독", "직교화 효과 측정",
     dict(use_axes=("A_RAW",), use_excl=True)),
    ("B1", "D1 단독", "Lazy Prices 한국 재현 여부",
     dict(use_axes=("D1",), use_excl=True)),
    ("B2", "D2 단독", "재무 이상현상 기준선",
     dict(use_axes=("D2",), use_excl=True)),
    ("B3", "D3 단독", "하드팩트 순기여",
     dict(use_axes=("D3",), use_excl=True)),
    ("B4", "배제플래그 단독 (U-1000 전체)", "위험 배제만의 효과",
     dict(use_axes=(), use_excl=True)),
    ("B5", "DART_SCORE 전체 (축 A 없음)", "축 B 단독 성능",
     dict(use_axes=("D1", "D2", "D3"), use_excl=True)),
    ("F1", "풀버전 (축 A + 축 B + 배제)", "본선",
     dict(use_axes=("A", "D1", "D2", "D3"), use_excl=True)),
    ("F2", "풀버전 − D1", "D1 한계기여",
     dict(use_axes=("A", "D2", "D3"), use_excl=True)),
    ("F3", "풀버전 − D2", "D2 한계기여",
     dict(use_axes=("A", "D1", "D3"), use_excl=True)),
    ("F4", "v1.0 재현 (ΔTONE + ΔNONFIN>0 하드게이트 + 배제)", "v2.0 개선효과 정량화",
     dict(use_axes=("A_RAW",), use_excl=True, v1_hardgate=True)),
]

ABLATION_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

def _abl_one(P: pd.DataFrame, rebals, uni, sec, run_fn, aid: str, name: str,
             purpose: str, kw: dict) -> dict:
    """한 팔 실행 — 신호 재조립 → 비용 전/후 백테스트 → 지표 산출."""
    rec = {"id": aid, "name": name, "purpose": purpose, "ok": False, "err": "",
           "net": {}, "gross": {}, "ic": np.nan, "icir": np.nan,
           "ic_t": np.nan, "n_ic": 0,
           "p": np.nan, "excess": np.nan}
    try:
        Q = assemble_final(P, **kw)
        # B4 는 신호가 무정보(전 종목 동일)이므로 상위 N 선정이 임의가 된다.
        # → 배제 통과 종목 '전체'를 동일가중 보유하는 것으로 정의한다(표 각주에 명시).
        top_n = 10_000 if aid == "B4" else None
        bt_net = run_fn(Q, label=f"ABL_{aid}", apply_costs=True, top_n=top_n)
        rec["net"] = perf_stats(bt_net["returns"])
        rec["gross"] = perf_stats(bt_net["returns"], gross=True)
        # ★ bt_ic 의 2번째 값은 t통계량이다(IR × √n). 표에 'IC-IR' 로 찍으면 분기 40개에서
        #   6.32배 부풀려진 값을 읽게 되므로 IR 과 t 를 분리해 둘 다 보고한다.
        ic, icir, ic_t, n_ic = info_coef_full(Q["FINAL_RANK"], Q["fwd_ret_1q"],
                                              Q["asof"].astype(str))
        rec["ic"], rec["icir"], rec["ic_t"], rec["n_ic"] = ic, icir, ic_t, n_ic
        # 초과수익 = 전략 − U-1000 동일가중 (지수 대신 같은 유니버스를 쓴다 — 41 모듈 주석 참조)
        bench = equal_weight_universe_return(P)
        R = measurable_ret(bt_net["returns"])   # 측정 불가 분기 제외(성과표와 동일 표본)
        b = bench.reindex(R.index).fillna(0.0)
        ex = (R.fillna(0.0) - b).to_numpy(dtype=float)
        rec["excess"] = float(np.nanmean(ex)) if len(ex) else np.nan
        rec["p"] = newey_west_p(ex)
        rec["returns"] = bt_net["returns"]
        rec["holdings"] = bt_net.get("holdings")
        rec["ok"] = True
    except Exception as e:                                        # noqa
        rec["err"] = f"{type(e).__name__}: {str(e)[:160]}"
        LOG.warn(f"어블레이션 {aid} 실패 — {rec['err']} (나머지 실험은 계속 진행합니다)")
    return rec

def run_ablations(P: pd.DataFrame, rebals, uni, sec, run_fn) -> pd.DataFrame:
    """§8.2 어블레이션 11종 전부 실행."""
    ABLATION_RESULTS.clear()
    LOG.banner("어블레이션 매트릭스 (§8.2) — 11개 실험",
               "각 축의 순기여와 한계기여를 귀속한다. 비용 전/후를 병기한다")
    t0 = time.time()

    # ── 널-절제 검증 ─────────────────────────────────────────────────────────────────────
    #   아무것도 빼지 않은 팔이 F1 과 정확히 같아야 한다. 다르면 어블레이션 표 전체가 무의미하다.
    try:
        n1 = run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                    label="NULL_ABL", apply_costs=True)["returns"]["ret"].to_numpy()
        n2 = run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                    label="NULL_ABL2", apply_costs=True)["returns"]["ret"].to_numpy()
        same = (len(n1) == len(n2)) and np.allclose(np.nan_to_num(n1), np.nan_to_num(n2))
        if same:
            LOG.ok("널-절제 검증 통과 — 같은 구성이 정확히 같은 결과를 냅니다(결정성 확인).")
        else:
            LOG.error("★ 널-절제 검증 실패 — 같은 구성인데 결과가 다릅니다. 어블레이션 Δ가 "
                      "'무엇을 뺐는가'가 아니라 '실행마다 달라지는 무언가'를 재고 있습니다. "
                      "이 상태의 어블레이션 표는 신뢰할 수 없습니다.")
    except Exception as e:                                        # noqa
        LOG.warn(f"널-절제 검증을 수행하지 못했습니다({type(e).__name__}).")

    for aid, name, purpose, kw in ABLATIONS:
        LOG.info(f"▷ [{aid}] {name}")
        ABLATION_RESULTS[aid] = _abl_one(P, rebals, uni, sec, run_fn, aid, name, purpose, kw)

    LOG.ok(f"어블레이션 11종 완료 — 소요 {time.time()-t0:.1f}초")
    return report_ablation_table()

def report_ablation_table() -> pd.DataFrame:
    """§9.2-(6) 어블레이션 성과표 (비용 전/후 병기)."""
    LOG.banner("[산출물 6] 어블레이션 11개 성과표 (§9.2-6)",
               "비용 차감 전 / 후를 병기한다 — 비용 전만 보고하는 것은 금지(§8.1)")
    rows = []
    for aid, name, purpose, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if not r or not r["ok"]:
            rows.append([aid, _trunc(name, 30), "판정불가", (r or {}).get("err", "미실행"),
                         "", "", "", "", "", "", ""])
            continue
        n, g = r["net"], r["gross"]

        def f(d, k, pct=False, dec=3):
            v = d.get(k)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            return f"{v*100:+.1f}%" if pct else f"{v:.{dec}f}"

        rows.append([
            aid, _trunc(name, 30),
            f(g, "CAGR", True), f(n, "CAGR", True),
            f(g, "Sharpe"), f(n, "Sharpe"),
            f(n, "MDD", True), f(n, "Sortino"),
            (f"{r['ic']:+.4f}" if np.isfinite(r["ic"]) else "—"),
            (f"{r['icir']:+.2f}" if np.isfinite(r["icir"]) else "—"),
            (f"{r.get('ic_t', float('nan')):+.2f}"
             if np.isfinite(r.get("ic_t", float("nan"))) else "—"),
            f"{n.get('평균종목수', float('nan')):.1f}",
        ])
    LOG.table(rows, ["ID", "구성", "CAGR(전)", "CAGR(후)", "Sharpe(전)", "Sharpe(후)",
                     "MDD", "Sortino", "IC", "IC-IR", "t(IC)", "종목수"],
              ["l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=32)
    LOG.info("IC-IR = mean(IC)/std(IC) (표준 정의) · t(IC) = IC-IR × √기간수. "
             "둘을 혼동하면 분기 40개에서 6.32배 부풀려진 값을 IR 로 읽게 됩니다.")

    rows2 = []
    for aid, name, purpose, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if not r or not r["ok"]:
            continue
        n = r["net"]
        rows2.append([aid, _trunc(purpose, 26),
                      f"{n.get('승률', float('nan'))*100:.0f}%",
                      f"{n.get('평균회전율', float('nan')):.2f}",
                      f"{n.get('평균비용', float('nan'))*100:.3f}%p",
                      f"{n.get('평균편입가능', float('nan')):.0f}",
                      f"{r['excess']*100:+.3f}%p" if np.isfinite(r["excess"]) else "—",
                      f"{r['p']:.4f}" if np.isfinite(r["p"]) else "—"])
    LOG.table(rows2, ["ID", "목적", "승률", "회전율", "분기평균비용", "평균편입가능",
                      "초과수익(분기)", "p(HAC)"],
              ["l", "l", "r", "r", "r", "r", "r", "r"], maxw=30)
    LOG.info("각주 ① B4 는 신호가 무정보이므로 '배제 통과 종목 전체 동일가중' 으로 정의했습니다. "
             "따라서 종목수가 다른 팔과 크게 다릅니다.  "
             "② 초과수익 기준은 U-1000 동일가중입니다(지수 대비가 아님 — 소형주 프리미엄을 "
             "알파로 오인하지 않기 위함).")
    out = pd.DataFrame([{"id": k, **{kk: vv for kk, vv in v.items()
                                     if kk not in ("returns", "holdings", "net", "gross")}}
                        for k, v in ABLATION_RESULTS.items()])
    return out

def report_f4_vs_f1() -> None:
    """§9.2-(7) v1.0(F4) 대비 v2.0(F1) 개선폭 정량 비교."""
    LOG.banner("[산출물 7] F4(v1.0 재현) 대비 F1(v2.0) 개선폭 (§9.2-7)",
               "수치 없이 '개선됐다'고 말하지 않기 위한 표. F1 이 나쁘면 그대로 보고한다")
    a, b = ABLATION_RESULTS.get("F4"), ABLATION_RESULTS.get("F1")
    if not a or not b or not a["ok"] or not b["ok"]:
        LOG.warn("F1 또는 F4 가 실행되지 않아 비교할 수 없습니다.")
        return
    rows = []
    for k in ("CAGR", "Sharpe", "Sortino", "MDD", "승률", "평균종목수",
              "평균회전율", "평균편입가능"):
        v4, v1 = a["net"].get(k), b["net"].get(k)
        if v4 is None or v1 is None or not (np.isfinite(v4) and np.isfinite(v1)):
            rows.append([k, "—", "—", "—", "—"])
            continue
        d = v1 - v4
        rel = (d / abs(v4) * 100.0) if abs(v4) > 1e-12 else np.nan
        pct = k in ("CAGR", "MDD", "승률")
        fmt = (lambda x: f"{x*100:+.2f}%") if pct else (lambda x: f"{x:.3f}")
        rows.append([k, fmt(v4), fmt(v1), fmt(d),
                     f"{rel:+.1f}%" if np.isfinite(rel) else "—"])
    rows.append(["IC", f"{a['ic']:+.4f}" if np.isfinite(a['ic']) else "—",
                 f"{b['ic']:+.4f}" if np.isfinite(b['ic']) else "—",
                 f"{b['ic']-a['ic']:+.4f}" if np.isfinite(a['ic']) and np.isfinite(b['ic'])
                 else "—", ""])
    LOG.table(rows, ["지표", "F4 (v1.0)", "F1 (v2.0)", "차이", "상대변화"],
              ["l", "r", "r", "r", "r"])
    s4, s1 = a["net"].get("Sharpe", np.nan), b["net"].get("Sharpe", np.nan)
    if np.isfinite(s4) and np.isfinite(s1):
        n4 = a["net"].get("평균편입가능", np.nan)
        n1 = b["net"].get("평균편입가능", np.nan)
        LOG.info(f"평균 편입 가능 종목수: v1.0 {n4:,.0f} → v2.0 {n1:,.0f}. "
                 f"v2.0 이 ΔNONFIN>0 하드게이트를 폐기한 직접적 효과가 여기에 나타납니다.")
        if s1 > s4:
            LOG.ok(f"이 백테스트에서 v2.0(F1) 이 v1.0(F4) 대비 Sharpe {s1-s4:+.3f} 개선.")
        else:
            LOG.error(f"★ 이 백테스트에서 v2.0(F1) 이 v1.0(F4) 를 이기지 못했습니다 "
                      f"(Sharpe {s1-s4:+.3f}). 개선 주장을 철회하고 그대로 보고합니다(§9.1).")

def apply_bh_fdr(q: Optional[float] = None) -> pd.DataFrame:
    """§8.3 — 11개 실험을 하나의 검정 패밀리로 묶어 BH-FDR 보정."""
    qq = float(q if q is not None else ARC_FDR_Q)
    LOG.banner(f"[산출물 8] BH-FDR 다중검정 보정 (q={qq:.2f}) (§9.2-8)",
               "11개 실험을 하나의 패밀리로 묶는다. 개별 유의성을 보정 없이 주장하지 않는다")
    ids, ps = [], []
    for aid, _n, _p, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if r and r["ok"] and np.isfinite(r.get("p", np.nan)):
            ids.append(aid)
            ps.append(float(r["p"]))
    if not ids:
        LOG.warn("p-value 를 계산할 수 있는 실험이 없어 보정할 수 없습니다.")
        return pd.DataFrame(columns=["id", "p", "sig_raw", "sig_bh"])
    arr = np.asarray(ps, dtype=float)
    passed = bh_fdr(arr, q=qq)
    order = np.argsort(arr)
    m = len(arr)
    rows = []
    for rank, i in enumerate(order, start=1):
        thr = qq * rank / m
        rows.append([ids[i], f"{arr[i]:.4f}", f"{thr:.4f}",
                     "✔" if arr[i] < 0.05 else "✘",
                     "✔ 유의" if passed[i] else "✘ 기각",
                     _trunc(next(n for a, n, _p, _k in ABLATIONS if a == ids[i]), 34)])
    LOG.table(rows, ["ID", "p(HAC)", "BH 임계", "보정 전(p<0.05)", "보정 후", "구성"],
              ["l", "r", "r", "c", "c", "l"], maxw=36)
    n_raw = int((arr < 0.05).sum())
    n_bh = int(passed.sum())
    LOG.info(f"보정 전 유의 {n_raw}/{m} → BH-FDR 보정 후 {n_bh}/{m}. "
             f"차이가 크다면 개별 p-value 를 그대로 인용해선 안 된다는 뜻입니다.")
    if n_bh == 0:
        LOG.warn("보정 후 유의한 실험이 하나도 없습니다. 이 백테스트에서 어떤 구성도 "
                 "U-1000 동일가중 대비 통계적으로 구분되는 초과수익을 내지 못했습니다.")
    out = pd.DataFrame({"id": ids, "p": arr, "sig_raw": arr < 0.05, "sig_bh": passed})
    return out
