

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — §9.2 최종 산출물 11종                                                        ║
# ║                                                                                          ║
# ║  §9.1 증거 등급 (엄격 준수):                                                               ║
# ║   · 실증적 주장은 이 백테스트에서 산출된 수치로만 뒷받침한다.                                ║
# ║   · 방법론적 우려는 "[방법론적 우려]" 라벨을 붙여 명시한다.                                  ║
# ║   · 메커니즘 그럴듯함을 증거로 제시하지 않는다.                                              ║
# ║   · 인접 문헌(미국 10-K)을 한국 데이터 현상의 증거로 대체하지 않는다.                        ║
# ║   · 근거를 못 찾았으면 "근거 없음" 이라 명시한다. 이 기준은 낙관적 주장에도 동일 적용한다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = "",
                       uni_bench: Optional[pd.Series] = None) -> None:
    """성과 검증표 — 비용 전/후 병기 필수(§8.1)."""
    LOG.banner(f"성과 검증 — {label or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · 익영업일 시가 체결 · 롱온리")
    R = bt.get("returns")
    if R is None or len(R) == 0:
        LOG.warn("수익률 시계열이 비어 성과를 계산할 수 없습니다.")
        return
    net = perf_stats(R)
    gro = perf_stats(R, gross=True)
    order = ["기간수(분기)", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD",
             "Calmar", "승률", "분기평균", "t통계량(HAC)", "최장언더워터(분기)",
             "평균종목수", "평균회전율", "평균비용", "평균편입가능"]
    pct = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
    pctp = {"분기평균", "평균비용"}
    rows = []
    for k in order:
        def fmt(d):
            v = d.get(k)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            if k in pct:
                return f"{v*100:+.2f}%"
            if k in pctp:
                return f"{v*100:+.3f}%p"
            return f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"
        rows.append([k, fmt(gro), fmt(net)])
    LOG.table(rows, ["지표", "비용 차감 전", "비용 차감 후"], ["l", "r", "r"],
              title="포트폴리오 성과 (§8.1 — 비용 전만 보고하는 것은 금지)")

    # 벤치마크 대비
    Rs = measurable_ret(R)          # perf_stats 와 동일 표본(측정 불가 분기 제외)
    brows = []
    if uni_bench is not None and len(uni_bench):
        bb = uni_bench.reindex(Rs.index).fillna(0.0)
        ex = Rs.fillna(0) - bb
        _, t = hac_tstat(ex.to_numpy())
        brows.append(["U-1000 동일가중 ★기준", f"{(1+bb).prod()*100-100:+.1f}%",
                      f"{(1+Rs.fillna(0)).prod()*100-100:+.1f}%",
                      f"{ex.mean()*100:+.3f}%p", f"{t:.2f}"])
    for name, b in (bench or {}).items():
        bb = b.reindex(Rs.index).fillna(0.0)
        ex = Rs.fillna(0) - bb
        _, t = hac_tstat(ex.to_numpy())
        brows.append([name, f"{(1+bb).prod()*100-100:+.1f}%",
                      f"{(1+Rs.fillna(0)).prod()*100-100:+.1f}%",
                      f"{ex.mean()*100:+.3f}%p", f"{t:.2f}"])
    if brows:
        LOG.table(brows, ["벤치마크", "벤치 누적", "전략 누적", "분기평균 초과", "HAC t"],
                  ["l", "r", "r", "r", "r"], title="벤치마크 대비")
        LOG.info("★ 1순위 기준은 'U-1000 동일가중' 입니다. 지수(KOSPI/KOSDAQ)는 시총가중이라 "
                 "대형주가 지배하므로, 지수 대비 초과수익은 소형주 프리미엄을 알파로 "
                 "오인하게 만듭니다.")

    # 우측 꼬리 의존도
    H = bt.get("holdings")
    if H is not None and len(H):
        contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
        n = len(contrib)
        base = float(contrib.sum())
        rows = []
        for qv, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
            k = max(1, int(round(n * qv)))
            top = float(contrib.iloc[:k].sum())
            rows.append([lab, f"{k}", f"{top:+.3f}", f"{base-top:+.3f}"])
        rows.append(["전체", f"{n}", f"{base:+.3f}", "—"])
        LOG.table(rows, ["구간", "종목수", "기여", "제외 후 총기여"],
                  ["l", "r", "r", "r"], title="우측 꼬리 의존도")
        k5 = max(1, int(round(n * 0.05)))
        if base > 0 and (base - float(contrib.iloc[:k5].sum())) <= 0:
            LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. 성과가 소수 종목에 "
                     "전적으로 의존합니다 — 실전에서 그 종목을 놓치면 전략 전체가 실패합니다.")


def report_correlation_matrix(P: pd.DataFrame) -> None:
    """§6.6 / §9.2-(3) D1·D2·D3 상호 상관행렬 (기간별)."""
    LOG.banner("[산출물 3] D1/D2/D3 상호 상관행렬 (§6.6)",
               "|상관| > 0.6 인 쌍이 있으면 독립 정보가 아니다 → 가중치 타당성 재검토 대상")
    cols = [c for c in ("D1_SCORE", "D2_SCORE", "D3_SCORE") if c in (P.columns if P is not None
                                                                     else [])]
    if P is None or P.empty or len(cols) < 2:
        LOG.warn("상관을 계산할 층이 2개 미만입니다.")
        return
    # 전체 기간 평균
    per = []
    for t, g in P.groupby("asof", observed=True):
        sub = g[cols].apply(pd.to_numeric, errors="coerce")
        if sub.notna().sum().min() < 30:
            continue
        c = sub.corr(method="spearman")
        per.append((t, c))
    if not per:
        LOG.warn("기간별 표본이 30행 미만이라 상관을 계산할 수 없습니다.")
        return
    avg = sum(c.fillna(0) for _t, c in per) / len(per)
    LOG.table([[a] + [f"{avg.loc[a, b]:+.3f}" for b in cols] for a in cols],
              ["층"] + cols, ["l"] + ["r"] * len(cols),
              title=f"기간 평균 상관행렬 (Spearman, {len(per)}개 시점)")
    tail = per[-8:]
    LOG.table([[str(pd.Timestamp(t).date())] +
               [f"{c.loc[a, b]:+.2f}" for i, a in enumerate(cols) for b in cols[i+1:]]
               for t, c in tail],
              ["리밸일"] + [f"{a}~{b}" for i, a in enumerate(cols) for b in cols[i+1:]],
              ["c"] + ["r"] * (len(cols) * (len(cols) - 1) // 2),
              title="최근 8시점 층간 상관 추이")
    hi = [(a, b, float(avg.loc[a, b])) for i, a in enumerate(cols) for b in cols[i+1:]
          if abs(float(avg.loc[a, b])) > 0.6]
    if hi:
        LOG.warn("★ |상관| > 0.6 인 쌍: " +
                 ", ".join(f"{a}~{b}={v:+.2f}" for a, b, v in hi) +
                 " → 독립 정보가 아니므로 0.40/0.40/0.20 가중치의 타당성을 재검토 대상으로 "
                 "보고합니다. §6.6 에 따라 자동 조정하지 않습니다.")
    else:
        LOG.ok("모든 층 쌍의 |상관| 이 0.6 이하 — 세 층이 서로 다른 정보를 담고 있다는 "
               "이 백테스트의 실증 근거입니다.")


def report_universe_attrition(uni) -> None:
    if uni is not None and hasattr(uni, "report_attrition"):
        uni.report_attrition()


def report_interpretation(P: pd.DataFrame) -> None:
    """해석 참조표 + §9.1 증거 등급 상기 블록."""
    LOG.banner("해석 참조표", "각 신호가 높을 때 / 낮을 때 무엇을 뜻하는가")
    LOG.table([
        ["ΔTONE_resid ↑", "컨센 수정·모멘텀·사이즈로 설명되지 않는 서술 톤 개선",
         "정량 지표보다 먼저 움직인 정성 판단"],
        ["D1_SCORE ↑ (변화 작음)", "전년 문안을 거의 그대로 유지",
         "Lazy Prices 가설상 '숨은 악재 정황 없음'"],
        ["D1_SCORE ↓ (변화 큼)", "MD&A·소송 문단을 능동적으로 고침",
         "★ 한국 데이터에서 이 방향의 유효성은 부호 검증 결과를 따를 것"],
        ["D2_SCORE ↑", "발생액 낮고 현금흐름이 이익을 뒷받침, 희석 적음", "이익의 질 양호"],
        ["D3_SCORE ↑", "완료형 하드팩트(설비·계약·인력·거점) 증분 관측",
         "가점일 뿐 편입 조건이 아님"],
        ["EXCLUDE = 1", "특수관계자·우발부채·소송·감사·최대주주·CB/BW·연속적자·자본잠식",
         "점수 무관 즉시 제외 (유일한 하드 게이트)"],
    ], ["신호", "의미", "비고"], ["l", "l", "l"], maxw=52)

    LOG.rule("§9.1 증거 등급 — 이 리포트를 읽는 규칙")
    _safe_print("""
  · 실증적 주장  : 이 백테스트에서 산출된 수치로만 뒷받침합니다. 수치 없는 낙관/비관 금지.
  · 방법론적 우려: "[방법론적 우려]" 라벨이 붙은 문장은 실증이 아니라 위험 지적입니다.
  · 인접 문헌    : Lazy Prices 는 미국 10-K 결과입니다. 한국 사업보고서 재현 증거로
                   대체하지 않습니다. D1 은 '검증해야 할 가설' 로만 취급합니다.
  · 근거 없음    : 데이터로 확인하지 못한 항목은 "근거 없음" 이라고 명시합니다.
  · 이 기준은 낙관적 주장에도 동일하게 적용됩니다.
""")
    if P is not None and len(P):
        rows = []
        for c in ("dTONE_resid", "D1_SCORE", "D2_SCORE", "D3_SCORE", "DART_SCORE",
                  "FINAL_SCORE"):
            v = pd.to_numeric(col(P, c), errors="coerce")
            n = int(v.notna().sum())
            rows.append([c, f"{n:,}", f"{100*n/max(len(P),1):.1f}%",
                         f"{float(v.quantile(0.1)):+.3f}" if n else "—",
                         f"{float(v.median()):+.3f}" if n else "—",
                         f"{float(v.quantile(0.9)):+.3f}" if n else "—"])
        LOG.table(rows, ["신호", "관측", "커버리지", "10분위", "중앙값", "90분위"],
                  ["l", "r", "r", "r", "r", "r"], title="신호 분포")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5) -> None:
    """최근 시점 상위 종목이 '왜' 뽑혔는지 한 장으로."""
    LOG.banner("종목별 진단 카드", "최근 리밸일 상위 종목 — 어느 축이 얼마나 기여했는가")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    last = P["asof"].max()
    sub = P[(P["asof"] == last) & (pd.to_numeric(col(P, "EXCLUDE"),
                                                 errors="coerce").fillna(0) == 0)]
    if sub.empty:
        sub = P[P["asof"] == last]
    if sub.empty or "FINAL_RANK" not in sub.columns:
        LOG.warn("마지막 시점 패널 또는 FINAL_RANK 가 없어 진단 카드를 만들 수 없습니다.")
        return
    names = (sec.drop_duplicates("code").set_index("code")["name"].to_dict()
             if sec is not None and len(sec) and "name" in sec.columns else {})
    top = sub.nlargest(min(int(top_n), len(sub)), "FINAL_RANK")
    for r in top.itertuples(index=False):
        code = getattr(r, "code", "?")
        _safe_print("\n" + "─" * 104)
        _safe_print(f"[{code}] {names.get(code, '')}    섹터: {getattr(r, 'sector', '?')}    "
                    f"리밸일: {pd.Timestamp(last).date()}    분기: {getattr(r, 'q', '?')}")
        _safe_print("─" * 104)
        fr = getattr(r, "FINAL_RANK", np.nan)
        _safe_print(f"FINAL_RANK {fr:.3f} (상위 {100*(1-fr):.1f}%)   "
                    f"FINAL_SCORE {getattr(r, 'FINAL_SCORE', np.nan):+.3f}   "
                    f"시총 {getattr(r, 'mktcap', np.nan)/1e8:,.0f}억   "
                    f"ADTV {getattr(r, 'adtv60', np.nan)/1e8:,.1f}억")
        _safe_print("\n■ 축별 기여")
        for lab, c in (("축 A ΔTONE_resid", "dTONE_resid"), ("  (원신호 ΔTONE)", "dTONE"),
                       ("  커버 리포트 수", "n_reports_q"),
                       ("축 B DART_SCORE", "DART_SCORE"),
                       ("  D1 (텍스트 변화)", "D1_SCORE"),
                       ("  D2 (재무 이상)", "D2_SCORE"),
                       ("  D3 (하드팩트)", "D3_SCORE"),
                       ("  ΔNONFIN", "DELTA_NONFIN")):
            v = getattr(r, c, np.nan)
            _safe_print(f"  {_pad(lab, 22)} " +
                        (f"{v:+.4f}" if isinstance(v, (int, float)) and np.isfinite(v)
                         else "결측 (0으로 채우지 않음)"))
        _safe_print("\n■ D1 섹션별 변화량 (z, 클수록 많이 바뀜)")
        cells = []
        for s in ARC_SECTIONS:
            v = getattr(r, f"CH_{s}", np.nan)
            cells.append(f"{s.replace('S_','')}={v:+.2f}" if isinstance(v, (int, float))
                         and np.isfinite(v) else f"{s.replace('S_','')}=—")
        _safe_print("  " + "  ".join(cells))
        _safe_print("\n■ 배제 플래그")
        flags = []
        for c, _d in EXCL_DEFS:
            v = getattr(r, c, np.nan)
            flags.append(f"{c.replace('EX_','')} " +
                         ("✘" if isinstance(v, (int, float)) and np.isfinite(v) and v > 0
                          else ("✔" if isinstance(v, (int, float)) and np.isfinite(v) else "—")))
        _safe_print("  " + "  ".join(flags))
    _safe_print("─" * 104)
    _safe_print("  범례: ✔ 통과 · ✘ 발동(제외) · — 미관측(결측)")


def report_kill_criteria(ctx: dict) -> dict:
    """§9.2-(11) / §9.3 사전등록 폐기 조건 5개를 실측으로 판정."""
    LOG.banner("[산출물 11] 사전등록 폐기 조건 판정 (§9.3)",
               "사후 조정 금지 — 충족 시 파라미터 튜닝으로 되살리려 시도하지 않는다")
    res = {}
    rows = []

    # 1. GATE_4·5·6 이 모두 실패 → 축 B 성립 불가
    g = {k: (GATE_RESULTS.get(k, {}) or {}).get("pass") for k in ("GATE_4", "GATE_5", "GATE_6")}
    c1 = all(v is False for v in g.values())
    res["k1"] = c1
    rows.append(["1", "GATE_4·5·6 모두 실패 → 축 B 성립 불가",
                 " / ".join(f"{k}={'실패' if v is False else ('통과' if v else '판정불가')}"
                            for k, v in g.items()),
                 "⛔ 폐기" if c1 else "해당 없음"])

    # 2. 비용 차감 후 F1 의 알파 소멸
    f1 = ABLATION_RESULTS.get("F1")
    if f1 and f1.get("ok"):
        mu_net = f1["net"].get("분기평균", np.nan)
        sh = f1["net"].get("Sharpe", np.nan)
        c2 = not (np.isfinite(mu_net) and mu_net > 0 and np.isfinite(sh) and sh > 0)
        res["k2"] = c2
        rows.append(["2", "거래비용 차감 후 F1 의 알파 소멸",
                     f"분기평균 {mu_net*100:+.3f}%p · Sharpe {sh:.3f}"
                     if np.isfinite(mu_net) else "산출 불가",
                     "⛔ 폐기" if c2 else "통과"])
    else:
        res["k2"] = None
        rows.append(["2", "거래비용 차감 후 F1 의 알파 소멸", "F1 미실행", "판정불가"])

    # 3. A2 와 A1 의 차이가 미미 → 텍스트 고유 알파 부재
    a1, a2 = ABLATION_RESULTS.get("A1"), ABLATION_RESULTS.get("A2")
    if a1 and a2 and a1.get("ok") and a2.get("ok"):
        s1 = a1["net"].get("Sharpe", np.nan)
        s2 = a2["net"].get("Sharpe", np.nan)
        c3 = bool(np.isfinite(s1) and np.isfinite(s2) and abs(s1 - s2) < 0.10)
        res["k3"] = c3
        rows.append(["3", "A2(직교화 미적용)와 A1 차이 미미 → 텍스트 고유 알파 부재",
                     f"A1 {s1:.3f} vs A2 {s2:.3f} (Δ {s1-s2:+.3f})",
                     "⛔ 폐기" if c3 else "통과"])
    else:
        res["k3"] = None
        rows.append(["3", "A2 vs A1 차이", "미실행", "판정불가"])

    # 4. F1 이 B2(D2 단독)를 유의하게 상회하지 못함
    b2 = ABLATION_RESULTS.get("B2")
    if f1 and b2 and f1.get("ok") and b2.get("ok"):
        try:
            ra = measurable_ret(f1["returns"])
            rb = measurable_ret(b2["returns"]).reindex(ra.index)
            d = (ra.fillna(0) - rb.fillna(0)).to_numpy()
            mu, t = hac_tstat(d)
            c4 = not (np.isfinite(t) and t > 1.0 and mu > 0)
            res["k4"] = c4
            rows.append(["4", "F1 이 B2(D2 단독)를 유의하게 상회 못함",
                         f"차이 분기평균 {mu*100:+.3f}%p · HAC t={t:.2f}",
                         "⛔ 폐기" if c4 else "통과"])
        except Exception:
            res["k4"] = None
            rows.append(["4", "F1 vs B2", "계산 실패", "판정불가"])
    else:
        res["k4"] = None
        rows.append(["4", "F1 vs B2", "미실행", "판정불가"])

    # 5. D1 부호 역전
    sg = ctx.get("d1_sign") or {}
    ok5 = sg.get("sign_ok")
    c5 = (ok5 is False)
    res["k5"] = c5
    rows.append(["5", "D1 부호가 한국 데이터에서 역전",
                 _trunc(str(sg.get("verdict", "미실행")), 52),
                 "⛔ D1 검증 실패 → F2 를 주 결과로" if c5 else
                 ("통과" if ok5 else "판정불가")])

    LOG.table(rows, ["#", "사전등록 폐기 조건", "실측", "판정"], ["c", "l", "l", "c"], maxw=56)
    fired = [k for k, v in res.items() if v is True]
    if fired:
        LOG.error(f"★ 폐기 조건 {len(fired)}건 충족: {', '.join(fired)}. "
                  f"§9.3 에 따라 파라미터 튜닝으로 되살리려 시도하지 않습니다. "
                  f"폐기 보고 후 중단하는 것이 사전등록된 행동입니다.")
    else:
        LOG.ok("사전등록 폐기 조건에 해당하는 항목이 없습니다.")
    return res


def report_final_deliverables(ctx: dict) -> None:
    """§9.2 산출물 11종의 목차 — 무엇이 어디에 나왔고 판정이 무엇인지 한 표로."""
    LOG.banner("최종 산출물 점검표 (§9.2)", "11개 항목이 전부 출력되었는지 확인한다")
    gates_done = bool(GATE_RESULTS)
    ica = ctx.get("axis_a_ic") or {}
    sign = ctx.get("d1_sign") or {}
    abl_done = bool(ABLATION_RESULTS)
    rob_done = bool(ROBUST_RESULTS)
    kill = ctx.get("kill") or {}
    rows = [
        ["1", "Phase 0 게이트 결과표 (6개 실측 + 판정)", "21_gate",
         "출력" if gates_done else "미실행",
         f"{sum(1 for v in GATE_RESULTS.values() if v['pass'] is True)}/"
         f"{len(GATE_RESULTS)} 통과" if gates_done else "—"],
        ["2", "축 A 직교화 전/후 IC 비교표", "30_axis_a_tone",
         "출력" if ica else "미실행",
         (f"IC {ica.get('ic_raw', float('nan')):+.4f} → "
          f"{ica.get('ic_resid', float('nan')):+.4f}") if ica else "—"],
        ["3", "D1/D2/D3 상호 상관행렬 (기간별)", "60_report", "출력", "—"],
        ["4", "D1 부호 검증 (변화=악재 성립 여부)", "31_axis_b_d1",
         "출력" if sign else "미실행",
         ("성립" if sign.get("sign_ok") else ("역전" if sign.get("sign_ok") is False
                                              else "판정불가")) if sign else "—"],
        ["5", "인과 순서 점검 (리포트-공시 시차 · 두 축 상관)", "51_robust",
         "출력" if "R11" in ROBUST_RESULTS else "미실행",
         _trunc(str((ROBUST_RESULTS.get("R11") or {}).get("detail", "")), 34)],
        ["6", "어블레이션 11개 성과표 (비용 전/후)", "50_ablation",
         "출력" if abl_done else "미실행",
         f"{sum(1 for v in ABLATION_RESULTS.values() if v['ok'])}/{len(ABLATION_RESULTS)} 성공"
         if abl_done else "—"],
        ["7", "F4(v1.0) 대비 F1(v2.0) 개선폭", "50_ablation",
         "출력" if ("F1" in ABLATION_RESULTS and "F4" in ABLATION_RESULTS) else "미실행", "—"],
        ["8", "BH-FDR 보정 후 유의성 판정표", "50_ablation",
         "출력" if ctx.get("fdr") is not None else "미실행",
         f"{int(ctx['fdr']['sig_bh'].sum())}건 유의"
         if ctx.get("fdr") is not None and len(ctx["fdr"]) else "—"],
        ["9", "섹터별 성과 분해표", "51_robust",
         "출력" if "R3" in ROBUST_RESULTS else "미실행",
         _trunc(str((ROBUST_RESULTS.get("R3") or {}).get("detail", "")), 34)],
        ["10", "강건성 테스트 결과 (R1~R11)", "51_robust",
         "출력" if rob_done else "미실행", f"{len(ROBUST_RESULTS)}건 기록"],
        ["11", "폐기 판정 여부 및 근거", "60_report",
         "출력" if kill else "미실행",
         f"{sum(1 for v in kill.values() if v is True)}건 충족" if kill else "—"],
    ]
    LOG.table(rows, ["#", "산출물", "담당 모듈", "상태", "요약"],
              ["c", "l", "l", "c", "l"], maxw=48)
    miss = [r[0] for r in rows if r[3] == "미실행"]
    if miss:
        LOG.warn(f"미출력 산출물: {', '.join(miss)} — 해당 축이 비활성화되었거나 "
                 f"상위 단계에서 표본이 부족했기 때문입니다. 위 로그에서 사유를 확인하세요.")


def report_dataflow_map() -> None:
    LOG.banner("데이터 흐름 지도 (거시)", "에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────────┐
  │ 환경감지 → 의존성 → 캐시 연결(로컬 D: + 구글드라이브 양쪽 탐색)                            │
  │   VAULT: 공용(_shared) = 가격·재무·공시·리포트원장·DART원문·정규화토큰  ← 타 전략 재사용   │
  │          전용(arc_txt_v2) = 유사도·피처패널·스코어·백테스트·리포트                        │
  │   append-only 저널 · 백업 후 교체 · 내용해시 blob · 삭제 API 없음 (절대 1원칙)            │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L1 수집 ──────────────────────────────────────────────────────────────────────────────┐
  │ 종목마스터 ← FDR GitHub캐시(상장/폐지) + KIND + pykrx스냅샷 + DART corpCode + 네이버      │
  │ 가격/시총  ← pykrx → FDR → 네이버 → yfinance (폴백체인, 소스 감사표)                      │
  │              PIT 시가총액 3중 경로 → U-1000 의 유일한 근거                                │
  │ DART       ← 재무(rcept_no→knowledge_date) · 직원 · 공시목록 · 주식총수 · 감사의견          │
  │              정기보고서 원문(document.xml) → 6단계 정규화 → 섹션별 토큰                    │
  │ 리서치     ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장          │
  │              → 애널리스트 원장 → 리비전 패널(직교화 통제변수)                              │
  │              → PDF 본문 전문(연도 샤드) → 축 A TONE 입력                                   │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼  모든 테이블은 pit_frame() 통과 → PIT.register()
  ┌── Phase 0 게이트 (§2) ──────────────────────────────────────────────────────────────────┐
  │ GATE_1/2 pair_count · GATE_3 본문추출률 · GATE_4 페어링 · GATE_5 판독 · GATE_6 재무       │
  │ 실패 → 해당 축만 비활성화 (전략 폐기 아님). 축 A 죽으면 DART-ONLY 폴백                     │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L2 신호 ──────────────────────────────────────────────────────────────────────────────┐
  │ U-1000 PIT 유니버스(상폐 포함) → 분기 패널 → 셀(분기×섹터)                                 │
  │ 축 A: 본문 → 문장 → 확장윈도우 분류기 → TONE → ΔTONE → **직교화** → ΔTONE_resid           │
  │ 축 B: D1 유사도4종(기간 횡단면 z) + D2 이상현상6종 + D3 하드팩트 → 0.4/0.4/0.2            │
  │       배제 플래그 8종 = 유일한 하드 제외                                                   │
  │ FINAL = 0.5·z(ΔTONE_resid) + 0.5·z(DART_SCORE)   ← 결측은 비례 재배분, 탈락 없음          │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L3 백테스트 → L5 검정 → L6 리포트 ────────────────────────────────────────────────────┐
  │ 분기 리밸 · 익영업일 시가 체결 · 상폐 −100% · 비용(수수료+거래세이력+스프레드 하한)         │
  │ 어블레이션 11종(A1·A2·B1~B5·F1~F4) → BH-FDR(q=0.10) → 강건성 R1~R11                      │
  │ → 성과표 · 상관행렬 · 부호검증 · 섹터분해 · 진단카드 · 폐기 판정                            │
  └─────────────────────────────────────────────────────────────────────────────────────────┘
""")
