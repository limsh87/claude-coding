

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-B  강건성 (§8.4) + 인과 순서 점검 (§7.1) + 부정 신호 검증 (§7.3)                       ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§9.1). 이 파일은 자동 조정을 하지 않는다.           ║
# ║  ★ 판정 불가는 None 으로 기록하고 사유를 남긴다. 예외로 죽지 않는다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: "OrderedDict[str, dict]" = OrderedDict()


def _rrec(rid: str, name: str, passed: Optional[bool], detail: str,
          metrics: Optional[dict] = None):
    # ★ numpy bool 주의: np.False_ is False → False. `is False` 분기가 조용히 빗나간다.
    passed = None if passed is None else bool(passed)
    ROBUST_RESULTS[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                           "metrics": metrics or {}}
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → " + {True: "✔", False: "✘", None: "—"}[passed] + f" {detail}")


def _rsharpe(bt) -> float:
    s = perf_stats(bt["returns"]) if bt else {}
    return float(s.get("Sharpe", np.nan)) if s else np.nan


def _rsafe(fn, rid: str, name: str):
    try:
        fn()
    except Exception as e:                                        # noqa
        _rrec(rid, name, None, f"실행 실패 — {type(e).__name__}: {str(e)[:140]}")


# ── R1. 서브기간 (전반부 / 후반부) ──────────────────────────────────────────────────────────
def R_subperiod(bt: dict) -> None:
    R = bt.get("returns")
    if R is None or len(R) < 8:
        _rrec("R1", "서브기간 분할", None, "표본 부족")
        return
    R = R.copy()
    half = len(R) // 2
    rows, mus = [], []
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        s = perf_stats(x)
        mus.append(s.get("분기평균", np.nan))
        rows.append([lab, f"{len(x)}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('승률', float('nan'))*100:.0f}%"])
    # 연도별도 함께
    R["year"] = as_ts_series(R["asof"]).dt.year
    yr = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        yr.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%",
                   f"{g['ret'].mean()*100:+.3f}%p", f"{(g['ret']>0).mean()*100:.0f}%",
                   f"{g['n'].mean():.1f}"])
    LOG.table(rows, ["구간", "분기수", "CAGR", "Sharpe", "MDD", "승률"],
              ["l", "r", "r", "r", "r", "r"], title="R1 서브기간 분할")
    LOG.table(yr, ["연도", "분기수", "연수익", "분기평균", "승률", "평균종목수"],
              ["c", "r", "r", "r", "r", "r"], title="R1b 연도별 분해")
    both_pos = all(np.isfinite(m) and m > 0 for m in mus)
    _rrec("R1", "서브기간 분할", both_pos,
          f"전반부 {mus[0]*100:+.3f}%p / 후반부 {mus[1]*100:+.3f}%p (분기평균). " +
          ("양 구간 모두 양(+)." if both_pos else
           "한 구간이 음(−)입니다 — 특정 레짐에 의존할 가능성을 배제할 수 없습니다."),
          {"mu_first": mus[0], "mu_second": mus[1]})


# ── R2. 시총 사분위별 분해 ──────────────────────────────────────────────────────────────────
def R_size_quartile(P: pd.DataFrame, bt: dict) -> None:
    H = bt.get("holdings")
    if H is None or H.empty or "mktcap" not in P.columns:
        _rrec("R2", "시총 사분위 분해", None, "보유 이력 또는 시총 없음")
        return
    key = P[["code", "asof", "mktcap", "sector"]].drop_duplicates(["code", "asof"])
    M = H.merge(key, on=["code", "asof"], how="left").dropna(subset=["mktcap"])
    if M.empty:
        _rrec("R2", "시총 사분위 분해", None, "결합 결과 없음")
        return
    try:
        M["qt"] = M.groupby("asof", observed=True)["mktcap"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 4, labels=False, duplicates="drop"))
    except Exception:
        M["qt"] = pd.qcut(M["mktcap"].rank(method="first"), 4, labels=False, duplicates="drop")
    rows = []
    for k, g in M.dropna(subset=["qt"]).groupby("qt"):
        contrib = float((g["weight"] * g["ret"]).sum())
        rows.append([f"Q{int(k)+1} ({'최소형' if k == 0 else ('최대형' if k == 3 else '')})",
                     f"{len(g):,}", f"{g['ret'].mean()*100:+.2f}%",
                     f"{(g['ret']>0).mean()*100:.0f}%", f"{contrib:+.3f}"])
    LOG.table(rows, ["시총 사분위", "보유건수", "평균 분기수익", "승률", "누적 기여"],
              ["l", "r", "r", "r", "r"], title="R2 시총 사분위별 성과 분해")
    _rrec("R2", "시총 사분위 분해", True, f"{len(rows)}개 분위로 분해 완료")


# ── R3. 섹터별 분해 (§8.4 필수) ─────────────────────────────────────────────────────────────
def R_sector(P: pd.DataFrame, bt: dict, sec: pd.DataFrame) -> None:
    """★ v1.0 의 섹터 편향(기술·제조 쏠림)이 실제로 해소됐는지 확인하는 필수 검사."""
    H = bt.get("holdings")
    if H is None or H.empty or "sector" not in P.columns:
        _rrec("R3", "섹터별 성과 분해", None, "보유 이력 또는 섹터 없음")
        return
    key = P[["code", "asof", "sector"]].drop_duplicates(["code", "asof"])
    M = H.merge(key, on=["code", "asof"], how="left")
    M["sector"] = M["sector"].astype(str).fillna("기타")
    uni_mix = (P.groupby(P["sector"].astype(str)).size() / max(len(P), 1)).to_dict()
    rows = []
    for s, g in M.groupby("sector"):
        share = len(g) / max(len(M), 1)
        rows.append([s, f"{len(g):,}", f"{100*share:.1f}%",
                     f"{100*uni_mix.get(s, 0):.1f}%",
                     f"{100*(share - uni_mix.get(s, 0)):+.1f}%p",
                     f"{g['ret'].mean()*100:+.2f}%",
                     f"{(g['ret']>0).mean()*100:.0f}%",
                     f"{float((g['weight']*g['ret']).sum()):+.3f}"])
    rows.sort(key=lambda r: -float(r[2].rstrip("%")))
    LOG.table(rows, ["섹터", "보유건수", "보유비중", "유니버스비중", "초과배분",
                     "평균수익", "승률", "누적기여"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title="R3 섹터별 성과 분해 (§8.4 필수 — v1.0 섹터 편향 해소 확인)")
    over = [(r[0], float(r[4].rstrip("%p"))) for r in rows]
    worst = max(over, key=lambda x: abs(x[1])) if over else ("", 0.0)
    concentrated = abs(worst[1]) > 20.0
    _rrec("R3", "섹터별 성과 분해", not concentrated,
          f"최대 초과배분 섹터 '{worst[0]}' {worst[1]:+.1f}%p. " +
          ("유니버스 대비 섹터 배분이 크게 치우치지 않았습니다."
           if not concentrated else
           "★ 한 섹터에 20%p 이상 초과 배분되었습니다 — v1.0 의 섹터 편향이 남아 있을 "
           "가능성이 있습니다. D3 섹터 발화율 표와 함께 해석하세요."),
          {"max_over_sector": worst[0], "max_over": worst[1]})


# ── R4. 리밸런싱 ±5거래일 이동 ──────────────────────────────────────────────────────────────
def R_rebal_shift(P: pd.DataFrame, rebals, run_fn, px_daily: Optional[pd.DataFrame] = None) -> None:
    """리밸일을 ±5거래일 옮겨도 성과가 유지되는가.

    ★ 패널이 특정 리밸일에 묶여 있으므로 신호를 다시 만들 수는 없다. 대신 '한 시점씩
      당기거나 미룬' 수익률 배열로 근사한다. 이 근사의 한계를 명시한다.
    """
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    base = run_fn(Q, label="RS_base", apply_costs=True)
    s0 = _rsharpe(base)
    R0 = base["returns"]["ret"].fillna(0).to_numpy()
    rows = [["기준 (이동 없음)", f"{s0:.3f}", "—"]]
    ok = True
    for k in (-1, 1):
        r = np.roll(R0, k)
        r = r[1:-1] if len(r) > 2 else r
        if len(r) < 8:
            continue
        eq = np.cumprod(1 + r)
        yrs = len(r) / 4.0
        cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 and eq[-1] > 0 else np.nan
        vol = r.std(ddof=1) * math.sqrt(4) if len(r) > 1 else np.nan
        sk = cagr / vol if vol and np.isfinite(vol) and vol > 0 else np.nan
        rows.append([f"{'−' if k < 0 else '+'}1분기 시프트(≈±5거래일 대리)",
                     f"{sk:.3f}", f"{sk - s0:+.3f}"])
        if np.isfinite(sk) and np.isfinite(s0) and (s0 - sk) > 0.5:
            ok = False
    LOG.table(rows, ["구성", "Sharpe", "Δ"], ["l", "r", "r"],
              title="R4 리밸런싱 시점 민감도")
    _rrec("R4", "리밸런싱 시점 민감도", ok,
          "시점 이동에 성과가 붕괴하지 않습니다." if ok else
          "★ 시점을 옮기면 성과가 크게 떨어집니다 — 특정 날짜 효과에 의존할 가능성.",
          {"sharpe_base": s0})
    LOG.info("[방법론적 우려] 이 검사는 수익률 시계열 시프트로 근사한 것입니다. "
             "엄밀한 ±5거래일 검정은 체결가를 그 날짜로 다시 만들어야 하며, "
             "그 경우 신호 산출 시점도 함께 바뀌어야 합니다.")


# ── R5. 보유종목수 20 / 30 / 40 ─────────────────────────────────────────────────────────────
def R_holdings(P: pd.DataFrame, run_fn) -> None:
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    rows, sh = [], []
    for n in (ARC_TOP_N_MIN, ARC_TOP_N_DEFAULT, ARC_TOP_N_MAX):
        bt = run_fn(Q, label=f"HOLD{n}", apply_costs=True, top_n=n)
        s = perf_stats(bt["returns"])
        sh.append(s.get("Sharpe", np.nan))
        rows.append([f"{n}종목", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('평균회전율', float('nan')):.2f}",
                     f"{s.get('평균비용', float('nan'))*100:.3f}%p"])
    LOG.table(rows, ["보유종목수", "CAGR", "Sharpe", "MDD", "회전율", "분기평균비용"],
              ["l", "r", "r", "r", "r", "r"], title="R5 보유종목수 민감도")
    fin = [x for x in sh if np.isfinite(x)]
    stable = bool(fin) and (max(fin) - min(fin) < 0.5)
    _rrec("R5", "보유종목수 민감도", stable,
          f"Sharpe 범위 {min(fin):.3f}~{max(fin):.3f}" if fin else "산출 불가",
          {"sharpes": fin})


# ── R6. STRUCT_FLAG 포함 / 제외 ─────────────────────────────────────────────────────────────
def R_struct(P: pd.DataFrame, run_fn) -> None:
    if "STRUCT_FLAG" not in P.columns:
        _rrec("R6", "STRUCT_FLAG 민감도", None, "STRUCT_FLAG 컬럼 없음")
        return
    n_flag = int(pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0).sum())
    if n_flag == 0:
        _rrec("R6", "STRUCT_FLAG 민감도", None, "해당 종목-기간이 없어 비교 불가")
        return
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    b_ex = run_fn(Q, label="ST_excl", apply_costs=True)
    Pin = P[pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0) == 0].copy()
    b_in = run_fn(assemble_final(Pin, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                  label="ST_drop", apply_costs=True)
    s1, s2 = _rsharpe(b_ex), _rsharpe(b_in)
    LOG.table([["기본 (D1 결측 처리 후 잔류)", f"{s1:.3f}", f"{n_flag:,}행 해당"],
               ["STRUCT 종목 통째 제외", f"{s2:.3f}", f"{len(P)-len(Pin):,}행 제거"]],
              ["구성", "Sharpe", "비고"], ["l", "r", "l"],
              title="R6 STRUCT_FLAG 포함/제외 (§6.1.6 민감도)")
    _rrec("R6", "STRUCT_FLAG 민감도", bool(np.isfinite(s1) and np.isfinite(s2) and
                                          abs(s1 - s2) < 0.5),
          f"Sharpe {s1:.3f} → {s2:.3f} (Δ {s2-s1:+.3f})", {"s_base": s1, "s_drop": s2})


# ── R7. 한국IR협의회 기업의뢰 리포트 포함 / 제외 ────────────────────────────────────────────
def R_ircouncil(P: pd.DataFrame, rep: Optional[pd.DataFrame], run_fn) -> None:
    """기업의뢰형 리포트는 톤이 구조적으로 긍정 편향이다. 분리 검증한다(§0.4, §8.4).

    ★ 근사: TONE 을 재집계하려면 축 A 전체를 다시 돌려야 한다(수십 분). 여기서는
      '기업의뢰 리포트만 커버하는 종목-분기' 의 축 A 를 결측 처리하는 방식으로 근사하고,
      그 근사를 명시한다.
    """
    if rep is None or rep.empty or "is_sponsored" not in rep.columns:
        _rrec("R7", "기업의뢰 리포트 민감도", None, "sponsored 태깅 없음")
        return
    R = rep.dropna(subset=["stock_code"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["pub_date"])
    R["q"] = [qlabel(t) for t in R["pub_date"]]
    grp = R.groupby(["stock_code", "q"])["is_sponsored"].agg(["mean", "size"])
    only_sp = set(grp[(grp["mean"] >= 0.999)].index)          # 전부 기업의뢰인 종목-분기
    if not only_sp:
        _rrec("R7", "기업의뢰 리포트 민감도", None, "기업의뢰 전용 종목-분기가 없습니다")
        return
    Q1 = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    P2 = P.copy()
    keyv = list(zip(P2["code"].astype(str), P2["q"].astype(str)))
    mask = np.array([k in only_sp for k in keyv])
    for c in ("dTONE", "dTONE_resid"):
        if c in P2.columns:
            P2.loc[mask, c] = np.nan
    Q2 = assemble_final(P2, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    s1 = _rsharpe(run_fn(Q1, label="IR_in", apply_costs=True))
    s2 = _rsharpe(run_fn(Q2, label="IR_out", apply_costs=True))
    LOG.table([["기업의뢰 포함", f"{s1:.3f}", f"{int(mask.sum()):,}행 해당"],
               ["기업의뢰 제외(축 A 결측 처리)", f"{s2:.3f}", ""]],
              ["구성", "Sharpe", "비고"], ["l", "r", "l"],
              title="R7 한국IR협의회 등 기업의뢰 리포트 민감도")
    _rrec("R7", "기업의뢰 리포트 민감도",
          bool(np.isfinite(s1) and np.isfinite(s2) and (s2 >= s1 - 0.3)),
          f"Sharpe {s1:.3f} → {s2:.3f} (Δ {s2-s1:+.3f}). " +
          ("제외해도 성과가 유지됩니다." if np.isfinite(s2) and np.isfinite(s1) and
           s2 >= s1 - 0.3 else
           "★ 기업의뢰 리포트를 빼면 성과가 크게 떨어집니다 — 알파의 상당 부분이 "
           "구조적 긍정 편향에서 왔을 수 있습니다."),
          {"s_in": s1, "s_out": s2})
    LOG.info("[방법론적 우려] TONE 재집계 대신 '기업의뢰 전용 종목-분기의 축 A 결측 처리'로 "
             "근사했습니다. 혼합 커버 종목의 편향은 제거되지 않습니다.")


# ── R8. D1 유사도 지표 4종 단독 ─────────────────────────────────────────────────────────────
def R_d1_metrics(P: pd.DataFrame, run_fn) -> None:
    rows, sh = [], {}
    base = _rsharpe(run_fn(assemble_final(P, use_axes=("D1",), use_excl=True),
                           label="D1_comp", apply_costs=True))
    rows.append(["합성(4종 z 평균)", f"{base:.3f}", "—"])
    for m in ARC_D1_METRICS:
        if f"D1_SCORE_{m}" not in P.columns:
            rows.append([m, "—", "컬럼 없음"])
            continue
        s = _rsharpe(run_fn(assemble_final(P, use_axes=("D1",), use_excl=True, d1_metric=m),
                            label=f"D1_{m}", apply_costs=True))
        sh[m] = s
        rows.append([m, f"{s:.3f}", f"{s - base:+.3f}"])
    LOG.table(rows, ["D1 유사도 지표", "Sharpe", "합성 대비 Δ"], ["l", "r", "r"],
              title="R8 D1 유사도 지표 4종 단독 (합성의 타당성 검증)")
    fin = [v for v in sh.values() if np.isfinite(v)]
    better = bool(fin) and np.isfinite(base) and (base >= max(fin) - 0.05)
    _rrec("R8", "D1 지표 합성 타당성", better,
          (f"합성 {base:.3f} vs 최고 단독 {max(fin):.3f}" if fin else "산출 불가") +
          ("" if better else " — ★ 단독 지표가 합성을 이깁니다. 4종 평균이 정보를 희석하고 "
                            "있을 수 있습니다(사전등록 구성이므로 자동 변경하지 않고 보고만)."),
          {"base": base, **sh})


# ── R9. D1 섹션 가중치 균등배분 ─────────────────────────────────────────────────────────────
def R_d1_weights(P: pd.DataFrame, run_fn) -> None:
    if "D1_SCORE_equalw" not in P.columns:
        _rrec("R9", "D1 섹션 가중치 민감도", None, "균등가중 컬럼 없음")
        return
    a = _rsharpe(run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                        label="W_pre", apply_costs=True))
    b = _rsharpe(run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True,
                                       d1_equal_weights=True),
                        label="W_eq", apply_costs=True))
    LOG.table([["사전등록 가중 (MDA .35 / LEGAL .25 / …)", f"{a:.3f}"],
               ["섹션 균등배분", f"{b:.3f}"]],
              ["D1 섹션 가중", "Sharpe"], ["l", "r"],
              title="R9 D1 섹션 가중치 민감도")
    _rrec("R9", "D1 섹션 가중치 민감도",
          bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) < 0.4),
          f"사전등록 {a:.3f} vs 균등 {b:.3f} (Δ {b-a:+.3f}). " +
          ("가중치 선택에 성과가 크게 좌우되지 않습니다." if np.isfinite(a) and np.isfinite(b)
           and abs(a - b) < 0.4 else
           "★ 가중치 선택이 성과를 크게 바꿉니다 — 사전등록 값의 임의성이 결과에 반영됩니다."),
          {"preset": a, "equal": b})


# ── R10. §7.3 부정 신호 (BOTTOM 그룹) ───────────────────────────────────────────────────────
def R_bottom_group(P: pd.DataFrame) -> None:
    """문헌상 부정 톤은 긍정 톤보다 정보력이 강하다. 필터로만 소비하지 말 것(§7.3)."""
    LOG.banner("R10 부정 신호 별도 검증 (§7.3)",
               "BOTTOM 그룹의 forward 1Q/2Q/4Q 수익률 — 비대칭이면 숏 슬리브 검토 대상")
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    if "FINAL_RANK" not in Q.columns:
        _rrec("R10", "부정 신호 검증", None, "FINAL_RANK 없음")
        return
    rows = []
    res = {}
    for lab, lo, hi in (("TOP 10%", 0.90, 1.01), ("중위 40~60%", 0.40, 0.60),
                        ("BOTTOM 10%", -0.01, 0.10)):
        m = (Q["FINAL_RANK"] >= lo) & (Q["FINAL_RANK"] < hi)
        g = Q[m]
        if g.empty:
            continue
        vals = []
        for h in ("fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q"):
            v = pd.to_numeric(col(g, h), errors="coerce")
            vals.append(float(v.mean()) if v.notna().any() else np.nan)
        res[lab] = vals
        rows.append([lab, f"{len(g):,}"] + [f"{v*100:+.2f}%" if np.isfinite(v) else "—"
                                            for v in vals])
    # 전체 평균 대비 초과
    base = [float(pd.to_numeric(col(Q, h), errors="coerce").mean())
            for h in ("fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q")]
    rows.append(["(유니버스 평균)", f"{len(Q):,}"] +
                [f"{v*100:+.2f}%" if np.isfinite(v) else "—" for v in base])
    LOG.table(rows, ["그룹", "표본", "1Q", "2Q", "4Q"], ["l", "r", "r", "r", "r"])
    top = res.get("TOP 10%", [np.nan] * 3)
    bot = res.get("BOTTOM 10%", [np.nan] * 3)
    if np.isfinite(top[0]) and np.isfinite(bot[0]) and np.isfinite(base[0]):
        a_top = top[0] - base[0]
        a_bot = base[0] - bot[0]          # BOTTOM 의 음의 알파 크기
        asym = a_bot > a_top
        LOG.table([["TOP 양의 알파 (1Q)", f"{a_top*100:+.3f}%p"],
                   ["BOTTOM 음의 알파 (1Q)", f"{a_bot*100:+.3f}%p"],
                   ["비대칭 여부", "BOTTOM 우세" if asym else "TOP 우세"]],
                  ["항목", "값"], ["l", "r"], title="§7.3 비대칭 판정")
        _rrec("R10", "부정 신호 검증", True,
              f"TOP 알파 {a_top*100:+.3f}%p / BOTTOM 음의 알파 {a_bot*100:+.3f}%p. " +
              ("BOTTOM 의 정보력이 더 강합니다." if asym else "TOP 의 정보력이 더 강합니다."),
              {"alpha_top": a_top, "alpha_bottom": a_bot, "asym": bool(asym)})
        if asym:
            LOG.warn("BOTTOM 의 음의 알파가 TOP 의 양의 알파보다 큽니다. §7.3 에 따라 "
                     "숏 슬리브 도입 여부는 **자동 결정하지 않고** 보고 후 지시를 기다립니다.")
    else:
        _rrec("R10", "부정 신호 검증", None, "표본 부족으로 비대칭 판정 불가")


# ── R11. §7.1 인과 순서 점검 ────────────────────────────────────────────────────────────────
def R_causal_order(P: pd.DataFrame, rep: Optional[pd.DataFrame],
                   doc: Optional[pd.DataFrame]) -> None:
    """애널리스트가 DART 를 읽고 리포트를 썼다면 두 축은 독립 확증이 아니라 중복 카운팅이다."""
    LOG.banner("R11 인과 순서 점검 (§7.1)",
               "리포트가 공시 직후에 몰려 있다면 두 축은 같은 정보를 두 번 세는 것이다")
    detail = []
    metrics = {}

    # ① 리포트 발간일 − 직전 정기보고서 접수일 시차 분포
    if (rep is not None and len(rep) and doc is not None and len(doc)):
        R = rep.dropna(subset=["stock_code"])[["stock_code", "pub_date"]].copy()
        R["pub_date"] = as_ts_series(R["pub_date"])
        R = R.dropna().rename(columns={"stock_code": "code"})
        D = doc[["corp_code", "rcept_dt"]].drop_duplicates().copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        c2c = {}
        if "corp_code" in P.columns:
            c2c = (P.dropna(subset=["corp_code"]).drop_duplicates("code")
                    .set_index("code")["corp_code"].astype(str).to_dict())
        R["corp_code"] = R["code"].astype(str).map(c2c)
        R = R.dropna(subset=["corp_code"]).sort_values("pub_date")
        D = D.dropna().sort_values("rcept_dt")
        if len(R) and len(D):
            try:
                M = pd.merge_asof(R, D, left_on="pub_date", right_on="rcept_dt",
                                  by="corp_code", direction="backward",
                                  tolerance=pd.Timedelta(days=400))
                M = M.dropna(subset=["rcept_dt"])
                lag = (M["pub_date"] - M["rcept_dt"]).dt.days
                bins = [("0~7일", (lag >= 0) & (lag <= 7)),
                        ("8~30일", (lag > 7) & (lag <= 30)),
                        ("31~90일", (lag > 30) & (lag <= 90)),
                        ("91일 이상", lag > 90)]
                tot = max(len(lag), 1)
                LOG.table([[k, f"{int(v.sum()):,}", f"{100*float(v.mean()):.1f}%"]
                           for k, v in bins],
                          ["공시 후 경과", "리포트 수", "비중"], ["l", "r", "r"],
                          title="리포트 발간 ~ 직전 정기보고서 접수 시차 분포")
                near = float(((lag >= 0) & (lag <= 7)).mean())
                metrics["report_within_7d"] = near
                detail.append(f"공시 후 7일 내 발간 비중 {100*near:.1f}%")
                if near > 0.30:
                    LOG.warn(f"리포트의 {100*near:.0f}% 가 정기보고서 접수 7일 내에 몰려 있습니다. "
                             f"두 축이 같은 정보를 반영할 가능성이 높습니다 — 결합 가중치 "
                             f"타당성을 재검토 대상으로 보고합니다(자동 조정하지 않습니다).")
            except Exception as e:                                # noqa
                LOG.warn(f"시차 분포 계산 실패({type(e).__name__})")
    else:
        detail.append("리포트 또는 공시 데이터 부족으로 시차 분포 산출 불가")

    # ② ΔTONE_resid × DART_SCORE 기간별 횡단면 상관
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=False)
    if "dTONE_resid" in Q.columns and "DART_SCORE" in Q.columns:
        cs = []
        for t, g in Q.groupby("asof", observed=True):
            a = pd.to_numeric(g["dTONE_resid"], errors="coerce")
            b = pd.to_numeric(g["DART_SCORE"], errors="coerce")
            m = a.notna() & b.notna()
            if int(m.sum()) >= 30:
                r = float(a[m].corr(b[m], method="spearman"))
                if np.isfinite(r):
                    cs.append((t, r))
        if cs:
            arr = np.array([c[1] for c in cs])
            mu = float(arr.mean())
            metrics["axes_corr_mean"] = mu
            LOG.table([[str(pd.Timestamp(t).date()), f"{r:+.3f}"] for t, r in cs[-12:]],
                      ["리밸일", "상관"], ["c", "r"],
                      title="ΔTONE_resid × DART_SCORE 기간별 횡단면 상관 (최근 12시점)")
            detail.append(f"두 축 상관 평균 {mu:+.3f} ({len(cs)}시점)")
            if abs(mu) > 0.30:
                LOG.warn(f"두 축의 평균 상관이 {mu:+.3f} 입니다. 독립 확증이 아니라 중복 "
                         f"카운팅일 수 있으므로 §7.1 에 따라 결합 가중치를 재검토 대상으로 "
                         f"보고합니다. 자동 조정하지 않습니다.")
        else:
            detail.append("상관을 계산할 표본이 부족")
    _rrec("R11", "인과 순서 점검", None if not detail else True,
          " · ".join(detail) or "판정불가", metrics)


def report_robustness() -> None:
    LOG.banner("[산출물 10] 강건성 검사 요약 (§9.2-10)",
               "실패는 그대로 보고한다. 파라미터를 조정해 통과시키지 않는다")
    order = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11"]
    rows = []
    for rid in order:
        r = ROBUST_RESULTS.get(rid)
        if not r:
            rows.append([rid, "—", "미실행", ""])
            continue
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid, _trunc(r["name"], 26), icon, _trunc(r["detail"], 88)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=92)
    fails = [r for r in ROBUST_RESULTS.values() if r["pass"] is False]
    if fails:
        LOG.warn(f"강건성 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails) +
                 " — 파라미터를 조정하지 않고 그대로 보고합니다(§9.1).")
    else:
        LOG.ok("강건성 검사에서 실패 항목이 없습니다.")


def run_robustness_suite(P, bt, rebals, uni, sec, run_fn,
                         rep=None, doc=None, px_daily=None) -> None:
    """§8.4 전 항목 실행. 각 검사는 실패해도 다음으로 넘어간다."""
    LOG.banner("강건성 스위트 (§8.4)", "서브기간 · 시총 · 섹터 · 리밸시점 · 보유수 · "
                                       "STRUCT · 기업의뢰 · D1지표 · D1가중 · 부정신호 · 인과순서")
    _rsafe(lambda: R_subperiod(bt), "R1", "서브기간 분할")
    _rsafe(lambda: R_size_quartile(P, bt), "R2", "시총 사분위 분해")
    _rsafe(lambda: R_sector(P, bt, sec), "R3", "섹터별 성과 분해")
    _rsafe(lambda: R_rebal_shift(P, rebals, run_fn, px_daily), "R4", "리밸런싱 시점 민감도")
    _rsafe(lambda: R_holdings(P, run_fn), "R5", "보유종목수 민감도")
    _rsafe(lambda: R_struct(P, run_fn), "R6", "STRUCT_FLAG 민감도")
    _rsafe(lambda: R_ircouncil(P, rep, run_fn), "R7", "기업의뢰 리포트 민감도")
    _rsafe(lambda: R_d1_metrics(P, run_fn), "R8", "D1 지표 합성 타당성")
    _rsafe(lambda: R_d1_weights(P, run_fn), "R9", "D1 섹션 가중치 민감도")
    _rsafe(lambda: R_bottom_group(P), "R10", "부정 신호 검증")
    _rsafe(lambda: R_causal_order(P, rep, doc), "R11", "인과 순서 점검")
    report_robustness()
