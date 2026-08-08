# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트  R0 · R1 · R2-N⭐ · R3 · R5 · R7 · R8 · R10   (스펙 §11)                ║
# ║                                                                                          ║
# ║  ★ 모든 비교팔은 score_arm() 이라는 **하나의 경로**만 통과한다.                             ║
# ║    비교팔이 다른 계산을 타면 Δ가 '무엇을 뺐는가'가 아니라 '어떻게 계산했는가'를 잰다.        ║
# ║  ★ 결과를 유리하게 해석하지 않는다. C ≈ max(A,B) 면 "무기여"라고 그대로 쓴다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_V3: List[dict] = []


def _rec(rid: str, name: str, passed: Optional[bool], detail: str, numbers: str = ""):
    ROBUST_V3.append({"id": rid, "name": name, "passed": passed,
                      "detail": detail, "numbers": numbers})
    tag = "PASS" if passed else ("N/A" if passed is None else "FAIL")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.warn))(
        f"[{rid}] {name} — {tag} · {detail}")


def _stat(bt: dict, key: str) -> float:
    try:
        return float(perf_stats(bt["returns"]).get(key, np.nan))
    except Exception:
        return np.nan


def _ret_series(bt: dict, months: pd.DatetimeIndex) -> pd.Series:
    R = bt["returns"]
    return pd.Series(R["ret"].to_numpy(dtype=float),
                     index=pd.DatetimeIndex(R["month"])).reindex(months).fillna(0.0)


def _diff_t(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """두 수익률 시계열 차이의 HAC 평균·t통계량. 월별 쌍대비교라 표본상관을 자동 상쇄한다."""
    d = (a - b).dropna().to_numpy(dtype=float)
    return hac_tstat(d)


def _budget_ok(rid: str, t0: float) -> bool:
    lim = ROBUST_BUDGET_S.get(rid)
    return not (lim and (time.time() - t0) > lim)


ALPHA_FLOOR = 0.20      # 이 아래의 Sharpe 는 '알파가 있다'고 말하지 않는다


def _no_alpha_to_test(base: float) -> bool:
    """기준선에 애초에 알파가 없으면 '살아남았다/유지됐다'는 판정은 무의미하다.

    ★ 이걸 막지 않으면 R3·R7·R10 이 전부 조용히 PASS 를 찍는다. 기준 Sharpe 가 -0.05 인데
      직교화 후 0.04 가 나오면 `orth > 0` 이 참이라 '알파 잔존'이라고 출력되는 식이다.
      아무 알파도 없는 전략이 강건성 검사를 3개나 통과한 것처럼 보이는 것 —
      스펙 §11 이 금지하는 '유리한 해석'의 가장 전형적인 형태다.
      그래서 이 경우는 PASS 도 FAIL 도 아닌 **판정 유보(N/A)** 로 돌려보낸다.
    """
    return (not np.isfinite(base)) or base <= ALPHA_FLOOR


# ── R0 : 자체측정 벤치마크 (하드코딩 금지 — 이 문서가 직접 잰다) ────────────────────────────
def R0_benchmark(P: pd.DataFrame, bt: dict, months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """유니버스 동일가중 = 이 전략이 반드시 이겨야 하는 최소 기준선.

    ★ 지수(KOSPI/KOSDAQ)가 아니라 '우리가 실제로 고를 수 있었던 종목의 동일가중'이다.
      지수와 비교하면 유니버스 선택(중형주 편중)의 효과가 알파로 둔갑한다.
    """
    t0 = time.time()
    _liq = P[col(P, "V6") == 1]
    elig = _liq[col(_liq, "fwd_ret").notna()]
    if elig.empty:
        _rec("R0", "자체측정 벤치마크(유니버스 동일가중)", None, "유효 표본 없음")
        return {}
    # ★★ 기준선의 비대칭을 숨기지 않는다 ★★
    #   벤치마크는 fwd_ret 이 있는 행만 평균한다. 그런데 거래정지·상장폐지로 다음 달 행이
    #   사라지면 그 달 fwd_ret 이 정확히 NaN 이다 — 즉 **벤치마크는 폐지 손실을 구조적으로
    #   먹지 않는다.** 반면 전략은 백테스트 엔진에서 -100% 를 그대로 맞는다.
    #   이 비대칭은 기준선을 위로 밀어 전략을 부당하게 탈락시키는 방향이다.
    #   완전한 교정은 벤치마크에도 같은 폐지 규약을 적용하는 것이지만, 그러려면 R0 가
    #   Universe 를 받아야 한다. 지금은 **크기를 재서 보고**한다 — 모르는 채로 두지 않는다.
    _drop_n = int(len(_liq) - len(elig))
    _drop_r = _drop_n / max(len(_liq), 1)

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 왜 단순 평균을 쓰지 않는가 (7회차에서 CAGR inf% / MDD nan% 를 낸 자리) ★★
    #    ARM_MAIN="ALL" 이면 유동성 하한만 남고 규모 상한이 없어 월 1,500종목 안팎이 들어온다.
    #    그 중 한 종목이라도 수정주가 불일치로 +900% 를 기록하면 동일가중 평균에 +0.6%p 가
    #    실린다. 그런 달이 몇 번 겹치면 복리가 발산하고, 발산한 뒤에는 eq/peak = inf/inf = nan
    #    이라 MDD·Calmar 가 통째로 사라진다. 그런데 판정식은 isfinite 하나로 되어 있어
    #    **'벤치마크에 졌다'** 고 출력됐다 — 비교조차 못 했는데.
    #
    #    가격 쪽 무결성 게이트(build_price_panel)가 물리적으로 불가능한 값을 이미 걷어내지만,
    #    여기서 한 겹 더 둔다. 이유는 두 가지다.
    #      · 게이트를 통과한 '가능하지만 담을 수 없는' 수익(상한가 연속 잡주)이 남는다.
    #        1,500종목 동일가중 지수는 그런 종목을 실제로 담지 못한다 — 기준선이 과대해진다.
    #      · 기준선은 전략이 **이겨야 하는 선**이다. 과대한 기준선은 전략을 부당하게 탈락시키고,
    #        발산한 기준선은 판정 자체를 불가능하게 만든다. 둘 다 틀린 결론을 만든다.
    #    → 월별 횡단면 1%/99% 절사평균을 기본 기준선으로 쓰고, **원시 평균과 중앙값을 나란히
    #      출력**해 절사가 얼마나 바꿨는지 사용자가 직접 보게 한다. 숨기지 않는다.
    #    ★ 전략 수익률에는 절사를 적용하지 않는다. 그건 성과를 지어내는 것이다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    _fr = pd.to_numeric(elig["fwd_ret"], errors="coerce")
    _fr = _fr.where(np.isfinite(_fr.to_numpy(dtype="float64")))
    E = pd.DataFrame({"month": elig["month"].to_numpy(), "r": _fr.to_numpy()}).dropna()
    if E.empty:
        _rec("R0", "자체측정 벤치마크(유니버스 동일가중)", None,
             "유효한(유한한) fwd_ret 이 한 건도 없습니다 — 가격 무결성 게이트 로그를 확인하세요")
        return {}
    _g = E.groupby("month", observed=True)["r"]
    lo_q = _g.transform(lambda s: s.quantile(0.01))
    hi_q = _g.transform(lambda s: s.quantile(0.99))
    E["rw"] = E["r"].clip(lower=lo_q, upper=hi_q)
    ew_raw = _g.mean().reindex(months)
    ew = E.groupby("month", observed=True)["rw"].mean().reindex(months)
    ew_med = _g.median().reindex(months)
    n_by_m = _g.size().reindex(months)

    def _fin(s: pd.Series) -> pd.Series:
        v = pd.to_numeric(s, errors="coerce")
        return v.where(np.isfinite(v.to_numpy(dtype="float64"))).fillna(0.0)

    ew, ew_raw, ew_med = _fin(ew), _fin(ew_raw), _fin(ew_med)
    bench = {"유니버스 동일가중": ew}
    try:
        for k, v in benchmark_returns(months).items():
            if v is not None and v.notna().any():
                bench[k] = _fin(v.reindex(months))
    except Exception as e:                                       # noqa
        LOG.debug(f"지수 벤치마크 수집 실패({type(e).__name__}) — 자체측정만 사용합니다.")

    def _mk(s: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({"month": months, "ret": s.to_numpy(dtype=float), "n": 0,
                             "turnover": 0.0, "cost": 0.0})

    bs = perf_stats(_mk(ew))
    bs_raw = perf_stats(_mk(ew_raw))
    bs_med = perf_stats(_mk(ew_med))
    ss = perf_stats(bt["returns"])

    _f = lambda d, k, fmt: (format(d[k], fmt)
                            if k in d and np.isfinite(d.get(k, np.nan)) else "산출불가")
    LOG.table([["전략", _f(ss, "CAGR", ".2%"), _f(ss, "MDD", ".1%"), _f(ss, "Calmar", ".2f"),
                _f(ss, "Sharpe", ".2f"), "-"],
               ["유니버스 동일가중 (1%절사) ★판정기준", _f(bs, "CAGR", ".2%"),
                _f(bs, "MDD", ".1%"), _f(bs, "Calmar", ".2f"), _f(bs, "Sharpe", ".2f"),
                f"월 {n_by_m.mean():,.0f}종목"],
               ["유니버스 동일가중 (원시 평균, 참고)", _f(bs_raw, "CAGR", ".2%"),
                _f(bs_raw, "MDD", ".1%"), _f(bs_raw, "Calmar", ".2f"),
                _f(bs_raw, "Sharpe", ".2f"), "절사 전"],
               ["유니버스 중앙값 (참고)", _f(bs_med, "CAGR", ".2%"), _f(bs_med, "MDD", ".1%"),
                _f(bs_med, "Calmar", ".2f"), _f(bs_med, "Sharpe", ".2f"), "꼬리 무관"]],
              ["기준선", "CAGR", "MDD", "Calmar", "Sharpe", "비고"],
              ["l", "r", "r", "r", "r", "l"],
              title="R0 자체측정 벤치마크 — 절사 전/후를 나란히 둡니다(절사가 결론을 바꾸는지 보세요)")
    if not np.isfinite(bs_raw.get("CAGR", np.nan)):
        LOG.warn("★ 원시 평균 기준선이 발산했습니다(비유한). 유니버스에 가격으로 설명되지 않는 "
                 "극단 수익률이 남아 있다는 뜻입니다 — 위 '월수익률 분포' 표와 무결성 원장"
                 "(price_return_sanity_ledger)을 확인하세요. 판정은 절사 기준선으로 합니다.")
    if _drop_r > 0.005:
        LOG.warn(f"★ 기준선의 비대칭 고지 — 유동성 통과 {len(_liq):,}행 중 {_drop_n:,}행"
                 f"({_drop_r:.1%})은 다음 달 수익을 알 수 없어(거래정지·상장폐지·월 연속성 단절) "
                 f"벤치마크 평균에서 빠졌습니다. 즉 **벤치마크는 폐지 손실을 먹지 않고 전략만 "
                 f"먹습니다.** 이 비대칭은 기준선을 위로 밀어 전략을 불리하게 만드는 방향이므로, "
                 f"R0 에서 지더라도 그 차이의 일부는 신호가 아니라 이 규약 차이입니다.")

    cal_s, cal_b = ss.get("Calmar", np.nan), bs.get("Calmar", np.nan)
    nums = (f"전략 Calmar {_f(ss,'Calmar','.2f')} / 벤치 {_f(bs,'Calmar','.2f')} · "
            f"CAGR {_f(ss,'CAGR','.2%')} vs {_f(bs,'CAGR','.2%')} · "
            f"MDD {_f(ss,'MDD','.1%')} vs {_f(bs,'MDD','.1%')}")
    # ★★ 비교가 불가능한 것과 비교해서 진 것은 다른 사건이다 ★★
    #   예전엔 둘 다 FAIL 이었다. 지표가 nan 이면 '미달'이 아니라 **판정불가(N/A)** 다.
    if not (np.isfinite(cal_s) and np.isfinite(cal_b)):
        why = []
        if not np.isfinite(cal_s):
            why.append("전략 Calmar 산출불가(MDD 가 0 이거나 수익 시계열이 손상)")
        if not np.isfinite(cal_b):
            why.append("벤치 Calmar 산출불가")
        _rec("R0", "자체측정 벤치마크(유니버스 동일가중) 대비", None,
             "비교 지표를 산출할 수 없어 판정을 유보합니다 — " + " · ".join(why) +
             ". '벤치마크에 미달'이라고 쓰지 않습니다(비교 자체가 성립하지 않았습니다).", nums)
        runtime_mark("R0", time.time() - t0)
        return bench
    ok = bool(cal_s > cal_b)
    _rec("R0", "자체측정 벤치마크(유니버스 동일가중) 대비", ok,
         "Calmar 상회" if ok else "Calmar 미달 — 스펙 §11 기준상 폐기 대상", nums)
    runtime_mark("R0", time.time() - t0)
    return bench


# ── R1 : 누수 자가검정 (이중 대조군) ────────────────────────────────────────────────────────
def R1_leakage(P: pd.DataFrame, months: pd.DatetimeIndex, run_fn: Callable) -> None:
    """하네스가 '누수를 감지할 수 있는 상태인가'를 먼저 증명한다.

    두 개의 **고의 오염 대조군**을 넣는다:
      ① 미래수익 직접주입 — 신호를 fwd_ret 의 랭크로 바꾼다. 완벽한 예지력.
      ② 신호 6개월 앞당김 — 미래의 신호를 현재에 쓴다(스펙의 '-120일 앞당김').

    ★ 판정은 ①만으로 한다. 이유를 분명히 해 둔다:
      ①은 '하네스가 누수를 감지할 수 있는가'를 재는 **인과적으로 옳은** 검정이다.
      미래 수익을 신호에 그대로 넣었는데도 성과가 안 오르면 체결·정렬·결합 어딘가가
      끊어진 것이고, 그러면 본선 결과 전체가 무효다.
      ②는 성격이 다르다. 신호를 앞당겨 개선되려면 **신호에 실제 예측력이 있어야** 한다.
      알파가 0인 신호는 앞당겨도 0이므로, ②의 미개선은 하네스 결함이 아니라
      '신호에 지속성이 없다'는 별개의 사실이다. 둘을 한 판정에 묶으면 서로 다른 두
      사건을 구별할 수 없게 된다 — 그래서 ②는 참고 지표로 따로 보고한다.
    """
    t0 = time.time()
    base = _stat(run_fn(P, label="R1_base"), "Sharpe")

    A = P.copy()
    A["Signal_rank"] = (col(A, "fwd_ret").groupby(A["month"], observed=True)
                        .rank(pct=True, method="average"))
    A["FLOOR"] = 1.0
    s_inject = _stat(run_fn(A, label="R1_inject"), "Sharpe")

    B = P.sort_values(["code", "month"]).copy()
    B["Signal_rank"] = B.groupby("code", observed=True)["Signal_rank"].shift(-6)
    s_ahead = _stat(run_fn(B, label="R1_ahead"), "Sharpe")

    d1 = s_inject - base
    d2 = s_ahead - base
    ok = np.isfinite(d1) and d1 > 0.5
    note = ("하네스가 누수에 민감 — 본선 결과를 신뢰할 수 있음" if ok else
            "★ 미래수익을 주입해도 성과가 오르지 않음 — 하네스 결함입니다. "
            "전 결과를 무효로 다루고 체결·정렬·결합 경로를 먼저 고치세요")
    if ok:
        note += ("; 신호 앞당김도 개선(지속성 있음)" if np.isfinite(d2) and d2 > 0.1 else
                 "; 다만 신호 앞당김은 개선되지 않음 — 하네스가 아니라 "
                 "'신호의 예측 지속성이 약하다'는 별개의 신호로 읽으세요")
    _rec("R1", "누수 자가검정 (대조군 ①주입 판정 / ②앞당김 참고)", bool(ok), note,
         f"기준 Sharpe {base:.2f} · ①미래수익주입 {s_inject:.2f}(Δ{d1:+.2f}, 판정근거) · "
         f"②신호6M앞당김 {s_ahead:.2f}(Δ{d2:+.2f}, 참고)")
    runtime_mark("R1", time.time() - t0)


# ── R2-N : 한계임금 킬게이트 ⭐⭐ (이 문서의 존재 이유) ──────────────────────────────────────
R2N_VERDICT: Dict[str, Any] = {}


def R2N_kill_gate(P: pd.DataFrame, run_fn: Callable) -> None:
    """스펙 §11.1.

      A. clip(z(nl_emp),0)     단독          ← 나이브
      B. clip(z(nl_premium),0) 단독
      C. TP_N1 = clip × clip                 ← 트레이드오프
      D. 전체 E (8개 TP)   vs   CORE-D 단독 (5개 TP)

    ★ A·B·C 는 **동일한 행 집합**에서 비교한다. nl_emp 만 있고 nl_premium 이 없는 행을
      A 에만 허용하면 A 의 유니버스가 넓어져 비교가 성립하지 않는다.
      (실제로 이 통제를 빠뜨리면 나이브 팔이 표본 수 덕분에 이기는 일이 생긴다)
    """
    t0 = time.time()
    have_emp = ("nl_emp" in P.columns and "nl_premium" in P.columns
                and P["nl_emp"].notna().any() and P["nl_premium"].notna().any())
    if not have_emp:
        _rec("R2-N", "한계임금 킬게이트", None,
             "nl_emp 또는 nl_premium 관측이 없어 검정 불가 — "
             "K7/K8 실측표와 EMP 커버리지 감사를 확인하세요")
        R2N_VERDICT.update({"verdict": "검정불가", "reason": "EMP 관측 부재"})
        return

    # ── 공통 행 집합: 두 센서가 모두 관측된 행만 ───────────────────────────────────────────
    common = P["nl_emp"].notna() & P["nl_premium"].notna()
    n_common = int(common.sum())
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 여섯 팔을 **같은 기간**에서 비교한다 ★★
    #    A·B·C 는 nl_emp·nl_premium 동시관측 행에서만 신호가 산다. EMP 커버리지가 얇으면
    #    앞 구간 전체가 FLOOR=0 이라 선정이 0건이고, 그 달은 수익 0% 로 기록된다.
    #    반면 D·CORE-D 는 재무만으로 전 구간을 돈다. 그 둘의 Sharpe·CAGR 을 한 표에 나란히
    #    놓으면 '트레이드오프의 기여'가 아니라 **'몇 개월을 실제로 운용했는가'** 를 재게 된다.
    #    → EMP 관측이 존재하는 달로 창을 좁혀 모든 팔을 같은 창에서 돌린다.
    #      좁힌 사실과 개월 수는 판정문에 그대로 적는다(숨기고 좁히면 그게 더 나쁘다).
    # ══════════════════════════════════════════════════════════════════════════════════════
    _emp_months = pd.DatetimeIndex(sorted(pd.unique(P.loc[common, "month"])))
    _all_months = pd.DatetimeIndex(sorted(pd.unique(P["month"])))
    _win = _all_months[(_all_months >= _emp_months.min()) &
                       (_all_months <= _emp_months.max())] if len(_emp_months) else _all_months
    if len(_win) < 18:
        _rec("R2-N", "한계임금 킬게이트 ⭐⭐", None,
             f"EMP 관측이 존재하는 구간이 {len(_win)}개월뿐이라(최소 18개월) 검정할 수 없습니다. "
             f"직원현황 수집을 더 채운 뒤 재판정하세요 — 회사 우선 격자라 재실행할수록 "
             f"과거 구간이 함께 채워집니다.",
             f"공통표본 {n_common:,}행 · EMP 구간 "
             f"{(_emp_months.min() if len(_emp_months) else pd.NaT)}~"
             f"{(_emp_months.max() if len(_emp_months) else pd.NaT)}")
        R2N_VERDICT.update({"verdict": "검정불가", "reason": "EMP 유효 구간 부족",
                            "n_common": n_common, "emp_months": len(_win)})
        runtime_mark("R2N", time.time() - t0)
        return
    if len(_win) < len(_all_months):
        LOG.info(f"R2-N 은 EMP 관측 구간 {_win[0]:%Y-%m}~{_win[-1]:%Y-%m} "
                 f"({len(_win)}/{len(_all_months)}개월)에서만 비교합니다 — 여섯 팔이 같은 "
                 f"기간을 돌아야 차이가 '기간'이 아니라 '신호'에서 나옵니다.")
    Q = P.copy()
    Q["ARM_A"] = np.maximum(cell_rank(Q, "nl_emp") - 0.5, 0.0)
    Q["ARM_B"] = np.maximum(cell_rank(Q, "nl_premium") - 0.5, 0.0)
    Q["ARM_C"] = Q["TP_N1"] if "TP_N1" in Q.columns else tp(Q, "nl_emp", "nl_premium")
    for c in ("ARM_A", "ARM_B", "ARM_C"):
        Q[c] = pd.to_numeric(Q[c], errors="coerce").where(common)

    arms = {}
    # ★★ min_arms=1 이 이 검정의 핵심이다 ★★
    #   A·B 는 **단일 센서 팔**이고, 단일인 것이 검정의 목적이다("트레이드오프 곱이
    #   나이브 단독보다 나은가"). 본선용 안전장치(MIN_TP_ARMS=2)를 그대로 적용하면
    #   A 팔을 만드는 첫 줄에서 RuntimeError 가 나고 — 7회차에 실제로 그랬다 —
    #   이 파일의 존재 이유인 킬게이트가 한 번도 실행되지 못한다.
    for lab, cols in (("A. nl_emp 단독(나이브)", ["ARM_A"]),
                      ("B. nl_premium 단독", ["ARM_B"]),
                      ("C. TP_N1 = clip×clip", ["ARM_C"])):
        S = score_arm(Q, cols, min_tp=1, min_arms=1)
        Z = Q.copy()
        for k, v in S.items():
            Z[k] = v
        arms[lab] = run_fn(Z, label=f"R2N_{lab[:1]}", months_override=_win)

    months = _win
    rs = {k: _ret_series(v, months) for k, v in arms.items()}
    sh = {k: _stat(v, "Sharpe") for k, v in arms.items()}
    cg = {k: _stat(v, "CAGR") for k, v in arms.items()}
    ca = {k: _stat(v, "Calmar") for k, v in arms.items()}

    kA, kB, kC = list(arms)
    best_naive = kA if (sh.get(kA, -9) >= sh.get(kB, -9)) else kB
    mu, tstat = _diff_t(rs[kC], rs[best_naive])
    sig = np.isfinite(tstat) and tstat > 1.65

    # ── D: 전체 E vs CORE-D 단독 (같은 min_tp, 전 패널) ────────────────────────────────────
    live_all = [c for c in TP_ALL if c in P.columns and P[c].notna().any()]
    live_core = [c for c in TP_CORE_D if c in P.columns and P[c].notna().any()]
    dD = dC = None
    if live_core:
        # ★ D 비교는 '전체 E 가 CORE-D 단독보다 나은가'를 잰다. 살아 있는 TP 개수는
        #   이번 실행의 수집 결과에 따라 달라지므로 개수 자체를 라벨에 넣는다 —
        #   '8TP' 라고 써 놓고 실제로는 2개인 표를 만들면 그 표가 사용자를 속인다.
        _labD = f"D. 전체 E ({len(live_all)}TP)"
        _labC = f"CORE-D 단독 ({len(live_core)}TP)"
        try:
            for lab, cols in ((_labD, live_all), (_labC, live_core)):
                S = score_arm(P, cols, min_arms=1)
                Z = P.copy()
                for k, v in S.items():
                    Z[k] = v
                arms[lab] = run_fn(Z, label=f"R2N_{lab[:1]}", months_override=_win)
                rs[lab] = _ret_series(arms[lab], months)
                sh[lab] = _stat(arms[lab], "Sharpe")
                cg[lab] = _stat(arms[lab], "CAGR")
                ca[lab] = _stat(arms[lab], "Calmar")
            dD, dC = _labD, _labC
        except Exception as e:                                      # noqa
            LOG.warn(f"R2-N 의 D 비교(전체 E vs CORE-D)를 실행하지 못했습니다 "
                     f"({type(e).__name__}: {str(e)[:120]}) — A·B·C 판정은 그대로 진행합니다.")
            arms.pop(_labD, None); arms.pop(_labC, None)
            dD = dC = None

    LOG.table([[k, f"{cg.get(k, np.nan):.2%}", f"{sh.get(k, np.nan):.2f}",
                f"{ca.get(k, np.nan):.2f}", f"{_stat(arms[k],'MDD'):.1%}",
                f"{_stat(arms[k],'평균종목수'):.0f}"] for k in arms],
              ["비교팔", "CAGR", "Sharpe", "Calmar", "MDD", "평균종목"],
              ["l", "r", "r", "r", "r", "r"],
              title=f"R2-N 한계임금 킬게이트 — 여섯 팔 모두 {_win[0]:%Y-%m}~{_win[-1]:%Y-%m} ({len(_win)}개월) 동일 창 · A·B·C 는 공통 {n_common:,}행")

    # ── 판정 (유리하게 해석하지 않는다) ───────────────────────────────────────────────────
    # ★★ 측정 실패를 결론으로 쓰지 않는다 ★★
    #   hac_tstat 은 유효 표본이 12개월 미만이면 (nan, nan) 을 돌려준다. 그런데 예전 코드는
    #   `sig = isfinite(tstat) and tstat > 1.65` 하나로 판정해서, 표본이 없어 재지 못한
    #   경우와 재서 졌을 경우를 구별하지 않고 둘 다 **"무기여"** 라고 확정했다.
    #   EMP 커버리지가 얇으면 A·B·C 팔이 아예 종목을 못 고르는데, 그 결과가
    #   'NPS 정밀화 투자의 근거가 확보되지 않았다'는 결론으로 리포트에 박혔다.
    _n_eff = int((rs[kC] - rs[best_naive]).replace(0.0, np.nan).notna().sum())
    if not np.isfinite(tstat) or _n_eff < 12:
        _rec("R2-N", "한계임금 킬게이트 ⭐⭐", None,
             f"비교 가능한 달이 {_n_eff}개월뿐이라(최소 12개월) 검정할 수 없습니다. "
             f"A·B·C 팔이 종목을 고르지 못했거나 EMP 관측 구간이 너무 짧습니다 — "
             f"'무기여'라고 쓰지 않습니다. 위 EMP 커버리지 감사표를 먼저 보세요.",
             f"공통표본 {n_common:,}행 · 유효 비교 {_n_eff}개월 · "
             f"C 평균종목 {_stat(arms[kC],'평균종목수'):.1f} / "
             f"{best_naive[:1]} 평균종목 {_stat(arms[best_naive],'평균종목수'):.1f}")
        R2N_VERDICT.update({"verdict": "검정불가", "reason": "유효 비교 개월 부족",
                            "n_common": n_common, "n_eff_months": _n_eff})
        runtime_mark("R2N", time.time() - t0)
        return
    if sig:
        verdict = "PASS"
        msg = ("한계임금 트레이드오프 신호가 나이브 지표를 유의하게 이겼습니다. "
               "→ 국민연금 월 해상도 데이터로 정밀화할 가치가 있다는 근거를 확보했습니다.")
    else:
        verdict = "무기여"
        msg = ("C ≈ max(A,B) — 트레이드오프 논리가 기여하지 않습니다. 연 1회 해상도의 한계로 "
               "보입니다. → NPS 정밀화 투자의 근거가 이 실험에서는 확보되지 않았습니다.")
    emp_contrib = None
    if dD and np.isfinite(sh.get(dD, np.nan)) and np.isfinite(sh.get(dC, np.nan)):
        emp_contrib = sh[dD] - sh[dC]
        if emp_contrib <= 0:
            msg += (f" 또한 전체 E(8TP)가 CORE-D 단독(5TP)을 넘지 못했습니다"
                    f"(ΔSharpe {emp_contrib:+.2f}) → EMP 신호 전체가 무기여이므로 "
                    f"TP_N1~N3 를 제외한 CORE-D 6TP 축소안을 병행 제시합니다.")

    _rec("R2-N", "한계임금 킬게이트 ⭐⭐", bool(sig), msg,
         f"C-{best_naive[:1]} 월평균차 {mu:+.4%} · HAC t={tstat:.2f} "
         f"(유의 기준 t>1.65) · 공통표본 {n_common:,}행" +
         (f" · D-CORE ΔSharpe {emp_contrib:+.2f}" if emp_contrib is not None else ""))

    R2N_VERDICT.update({
        "verdict": verdict, "t_stat": float(tstat) if np.isfinite(tstat) else None,
        "mean_diff": float(mu) if np.isfinite(mu) else None,
        "best_naive": best_naive, "n_common": n_common,
        "sharpe": {k: (float(v) if np.isfinite(v) else None) for k, v in sh.items()},
        "cagr": {k: (float(v) if np.isfinite(v) else None) for k, v in cg.items()},
        "emp_contribution_sharpe": (float(emp_contrib) if emp_contrib is not None else None),
        "message": msg})
    runtime_mark("R2N", time.time() - t0)

    if (not sig) and STOP_ON_KILL_CRITERIA:
        LOG.warn("§12-4 킬 기준: R2-N 무기여. 중단하지 않고 끝까지 돌려 축소안까지 보여주지만, "
                 "이 결과를 '거의 유의함' 따위로 포장하지 않습니다.")


def r2n_verdict_md() -> str:
    v = R2N_VERDICT
    if not v:
        return "# R2-N 판정\n\n검정이 실행되지 않았습니다.\n"
    # ★ f-string 안에 같은 따옴표를 다시 쓰지 않는다(3.12 미만에서 SyntaxError).
    #   서식은 전부 밖에서 문자열로 만들어 두고, f-string 은 그 변수만 끼워 넣는다.
    md = v.get("mean_diff")
    ts = v.get("t_stat")
    s_md = "-" if md is None else format(md, "+.4%")
    s_ts = "-" if ts is None else format(ts, ".2f")
    L = ["# R2-N 판정 — 한계임금 킬게이트 (TCD v3 · 전략3)", "",
         f"**판정: {v.get('verdict')}**", "", v.get("message", ""), "",
         "## 실측", "", "| 비교팔 | CAGR | Sharpe |", "|---|---|---|"]
    for k, s in (v.get("sharpe") or {}).items():
        c = (v.get("cagr") or {}).get(k)
        s_c = "-" if c is None else format(c, ".2%")
        s_s = "-" if s is None else format(s, ".2f")
        L.append(f"| {k} | {s_c} | {s_s} |")
    L += ["", f"- 공통 표본: {v.get('n_common', 0):,}행",
          f"- 최강 나이브: {v.get('best_naive')}",
          f"- C − 나이브 월평균차: {s_md}",
          f"- HAC t통계량: {s_ts} (유의 기준 1.65)",
          "", "## 해석 규약", "",
          "판정을 유리하게 재해석하지 않는다. `C ≈ max(A,B)` 이면 트레이드오프 논리가",
          "이 해상도에서 무기여라는 뜻이며, 그것이 이 문서의 정직한 산출물이다.", ""]
    return "\n".join(L)


# ── R3 : 퀄리티 직교화 ──────────────────────────────────────────────────────────────────────
def R3_orthogonal(P: pd.DataFrame, run_fn: Callable) -> None:
    """E 를 규모·수익성·모멘텀·발생액에 회귀시키고 잔차로 다시 돌린다.

    '트레이드오프'라는 게 사실 그냥 퀄리티 팩터의 다른 이름이라면, 직교화 후 알파가 사라진다.
    """
    t0 = time.time()
    Q = P.sort_values(["code", "month"]).copy()
    Q["f_size"] = np.log(col(Q, "assets").where(col(Q, "assets") > 0))
    Q["f_prof"] = safe_div(col(Q, "net_income_ttm"), col(Q, "assets"))
    Q["f_mom"] = gby(Q, "close").transform(lambda s: dlog(s, 12))
    Q["f_accr"] = col(Q, "accruals")
    facs = ["f_size", "f_prof", "f_mom", "f_accr"]
    y = col(Q, "E_raw")
    if y.notna().sum() < 100:
        _rec("R3", "퀄리티 직교화", None, "E_raw 표본 부족")
        return

    resid = pd.Series(np.nan, index=Q.index, dtype="float64")
    for m, idx in Q.groupby("month", observed=True).indices.items():
        idx = np.asarray(idx)
        yy = y.to_numpy()[idx]
        XX = np.column_stack([np.ones(len(idx))] + [Q[f].to_numpy()[idx] for f in facs])
        ok = np.isfinite(yy) & np.isfinite(XX).all(axis=1)
        if ok.sum() < 20:
            continue
        try:
            beta, *_ = np.linalg.lstsq(XX[ok], yy[ok], rcond=None)
        except np.linalg.LinAlgError:
            continue
        r = np.full(len(idx), np.nan)
        r[ok] = yy[ok] - XX[ok] @ beta
        resid[idx] = r

    Z = Q.copy()
    Z["E"] = cell_rank(Z, resid)
    Z["Signal"] = Z["E"].fillna(0) * Z["U"].fillna(0) * Z["VETO"].fillna(0) * Z["FLOOR"].fillna(0)
    Z["Signal_rank"] = Z["Signal"].groupby(Z["month"], observed=True).rank(pct=True, method="average")
    base = _stat(run_fn(P, label="R3_base"), "Sharpe")
    orth = _stat(run_fn(Z, label="R3_orth"), "Sharpe")
    nums = (f"원본 Sharpe {base:.2f} → 잔차 {orth:.2f} · "
            f"통제변수 규모·수익성·모멘텀·발생액")
    if _no_alpha_to_test(base):
        _rec("R3", "퀄리티 직교화", None,
             f"원본 구간에 직교화로 검정할 알파가 없습니다(Sharpe {base:.2f} ≤ {ALPHA_FLOOR}). "
             f"'잔존'이라고 쓰지 않습니다 — 남을 것이 없었습니다.", nums)
        runtime_mark("R3", time.time() - t0)
        return
    keep = orth / base
    ok = np.isfinite(orth) and orth > 0 and keep >= 0.5
    _rec("R3", "퀄리티 직교화", bool(ok),
         "직교화 후에도 알파 잔존" if ok else
         "직교화하면 알파가 사라짐 — 트레이드오프가 아니라 퀄리티 팩터의 재포장일 수 있음",
         nums + f" · 잔존율 {keep:.0%}")
    runtime_mark("R3", time.time() - t0)


# ── R5 : 절제 (TP별 · 경계 · 분모임계) ─────────────────────────────────────────────────────
def R5_ablation(P: pd.DataFrame, run_fn: Callable) -> None:
    t0 = time.time()
    live = [c for c in TP_ALL if c in P.columns and P[c].notna().any()]
    base_bt = run_fn(P, label="R5_base")
    base = _stat(base_bt, "Sharpe")
    # ★★ 알파가 없으면 절제 안정성은 판정할 수 없다 ★★
    #   판정식이 `spread < 1.5` 라서, 어느 TP 를 빼도 Sharpe 가 똑같이 무의미하면
    #   Δ가 전부 0 근처가 되어 spread≈0 → **PASS**. '단일 요소에 종속되지 않음' 이라는
    #   문구가 출력되지만 실제로 성립하는 것은 '뺄 것이 없었다' 뿐이다.
    #   _no_alpha_to_test 가 R3·R7·R10 에만 걸려 있어 R5·R8 이 이 구멍으로 새고 있었다.
    if _no_alpha_to_test(base):
        _rec("R5", "절제 안정성", None,
             f"기준선에 절제로 검정할 알파가 없습니다(Sharpe {base:.2f} ≤ {ALPHA_FLOOR}). "
             f"'단일 요소에 종속되지 않음'이라고 쓰지 않습니다 — 뺄 것이 없었습니다.",
             f"살아 있는 TP {len(live)}개")
        runtime_mark("R5", time.time() - t0)
        return
    rows = [["(기준) 전체", f"{base:.2f}", "0.00", f"{len(live)}개 TP"]]
    # ★ 판정은 **표시용 문자열이 아니라 원시 수치**로 한다. 예전엔 float(r[2]) 로 표를
    #   다시 파싱했는데, Sharpe 가 nan 인 절제팔은 "+nan" 으로 찍히고 float("+nan")=nan 이다.
    #   내장 max/min 은 nan 을 순서에 따라 건너뛰므로 spread 가 작게 나와 **조용히 PASS** 했다.
    deltas: List[float] = []

    # ① TP 하나씩 제거
    for c in live:
        cols = [x for x in live if x != c]
        if not cols:
            continue
        S = score_arm(P, cols, min_arms=1)
        Z = P.copy()
        for k, v in S.items():
            Z[k] = v
        s = _stat(run_fn(Z, label=f"R5_-{c}"), "Sharpe")
        rows.append([f"− {c}", f"{s:.2f}", f"{s-base:+.2f}", "TP 제거"])
        deltas.append(float(s - base))
        if not _budget_ok("R5", t0):
            rows.append(["(예산 초과로 이후 절제 생략)", "-", "-", ""])
            break

    # ② 경계: 최소 TP 관측 수
    if _budget_ok("R5", t0):
        for k in (2, 4):
            S = score_arm(P, live, min_tp=k, min_arms=1)
            Z = P.copy()
            for kk, v in S.items():
                Z[kk] = v
            s = _stat(run_fn(Z, label=f"R5_mintp{k}"), "Sharpe")
            rows.append([f"MIN_TP_OBSERVED={k}", f"{s:.2f}", f"{s-base:+.2f}",
                         f"기본값 {MIN_TP_OBSERVED}"])
            deltas.append(float(s - base))

    # ③ C15 분모 임계값 — 한계임금을 실제로 재계산해서 본다
    if _budget_ok("R5", t0) and {"dn", "emp_prev", "d_pay", "avg_prev"} <= set(P.columns):
        for thr in (0.02, 0.05):
            Z = P.copy()
            gate = col(Z, "dn").abs() >= np.maximum(C15_MIN_ABS_DN, col(Z, "emp_prev") * thr)
            rel = safe_div(col(Z, "dn"), col(Z, "emp_prev"))
            gate &= (rel <= C15_MNA_UP) & (rel >= C15_MNA_DN)
            mw = safe_div(col(Z, "d_pay"), col(Z, "dn")).where(gate.fillna(False))
            prem = safe_div(mw, col(Z, "avg_prev").where(col(Z, "avg_prev") > 0))
            Z["nl_premium"] = prem.where(prem.between(C15_PREMIUM_LO, C15_PREMIUM_HI))
            Z["TP_N1"] = tp(Z, "nl_emp", "nl_premium")
            S = score_arm(Z, live)
            for kk, v in S.items():
                Z[kk] = v
            s = _stat(run_fn(Z, label=f"R5_c15_{thr}"), "Sharpe")
            rows.append([f"C15 분모임계 {thr:.0%}", f"{s:.2f}", f"{s-base:+.2f}",
                         f"기본값 {C15_MIN_REL_DN:.0%}"])
            deltas.append(float(s - base))

    LOG.table(rows, ["절제 조건", "Sharpe", "Δ", "비고"], ["l", "r", "r", "l"],
              title="R5 절제 검사 (TP별 · 경계 · 분모임계)")
    vals = [d for d in deltas if np.isfinite(d)]
    n_bad = len(deltas) - len(vals)
    if n_bad:
        # 측정 불가한 절제팔이 하나라도 있으면 '안정적'이라고 말할 수 없다.
        _rec("R5", "절제 안정성", None,
             f"절제팔 {n_bad}/{len(deltas)}개에서 Sharpe 를 산출하지 못했습니다"
             f"(표본 전멸 또는 선정 0종목). 측정되지 못한 절제를 '변화 없음'으로 읽으면 "
             f"안정성을 지어내는 것이라 판정을 유보합니다.",
             f"측정 성공 {len(vals)}종 · ΔSharpe 폭 "
             f"{(max(vals)-min(vals)) if vals else float('nan'):.2f}")
        runtime_mark("R5", time.time() - t0)
        return
    spread = (max(vals) - min(vals)) if vals else np.nan
    ok = np.isfinite(spread) and spread < 1.5
    _rec("R5", "절제 안정성", bool(ok),
         "단일 TP·단일 임계값에 성과가 종속되지 않음" if ok else
         "특정 절제에서 성과가 급변 — 결과가 한 요소에 종속되어 있습니다(재설계 검토)",
         f"ΔSharpe 폭 {spread:.2f} (기준 <1.5) · 절제 {len(vals)}종")
    runtime_mark("R5", time.time() - t0)


# ── R7 : 레짐 (밸류업 이전/이후) ────────────────────────────────────────────────────────────
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    t0 = time.time()
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    cut = as_ts("2024-02-26")
    pre, post = R[R["month"] < cut], R[R["month"] >= cut]
    rows = []
    for lab, sub in (("전체", R), ("밸류업 이전 (~2024-02)", pre), ("밸류업 이후 (2024-03~)", post)):
        if len(sub) < 6:
            rows.append([lab, f"{len(sub)}", "표본부족", "", "", ""])
            continue
        s = perf_stats(sub.reset_index(drop=True))
        rows.append([lab, f"{len(sub)}", f"{s.get('CAGR', np.nan):.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('MDD', np.nan):.1%}",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
    LOG.table(rows, ["레짐", "월수", "CAGR", "Sharpe", "MDD", "t(HAC)"],
              ["l", "r", "r", "r", "r", "r"],
              title="R7 레짐 분할 — TP_P1/P2 는 최근 2년만 현 레짐입니다")
    pre_s = perf_stats(pre.reset_index(drop=True)).get("Sharpe", np.nan) if len(pre) >= 6 else np.nan
    full_s = perf_stats(R.reset_index(drop=True)).get("Sharpe", np.nan)
    nums = (f"이전 Sharpe {pre_s:.2f} / 전체 {full_s:.2f} · "
            f"이전 {len(pre)}개월 / 이후 {len(post)}개월")
    if _no_alpha_to_test(full_s):
        _rec("R7", "레짐 (밸류업 이전 알파)", None,
             f"전체 구간 알파 자체가 없어(Sharpe {full_s:.2f} ≤ {ALPHA_FLOOR}) "
             f"레짐 귀속을 논할 단계가 아닙니다.", nums)
        runtime_mark("R7", time.time() - t0)
        return
    ok = np.isfinite(pre_s) and pre_s > ALPHA_FLOOR
    _rec("R7", "레짐 (밸류업 이전 알파)", bool(ok),
         "밸류업 이전 구간에서도 알파가 존재 — 구조적 알파로 볼 근거가 있음" if ok else
         "★ 밸류업 이전 알파가 사실상 0 — 이건 구조적 알파가 아니라 정책 베팅입니다. "
         "TP_P1/P2 는 10년 중 최근 2년만 현 레짐임을 결론에 명시하세요",
         nums)
    runtime_mark("R7", time.time() - t0)


# ── R8 : 하위기간 ───────────────────────────────────────────────────────────────────────────
def R8_subperiod(bt: dict) -> None:
    t0 = time.time()
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    R["year"] = R["month"].dt.year
    rows, pos = [], 0
    yrs = sorted(R["year"].unique())
    for y in yrs:
        sub = R[R["year"] == y]
        r = sub["ret"].fillna(0)
        tot = float((1 + r).prod() - 1)
        pos += 1 if tot > 0 else 0
        rows.append([str(y), f"{len(sub)}", f"{tot:+.2%}", f"{float(r.mean()):+.2%}",
                     f"{float((r>0).mean()):.0%}", f"{float(sub['n'].mean()):.0f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목"],
              ["c", "r", "r", "r", "r", "r"], title="R8 하위기간 (연도별)")
    ratio = pos / max(len(yrs), 1)
    # ★ R5 와 같은 구멍이 여기에도 있었다. 알파가 없는데 우연히 절반 넘는 해가 양수면
    #   '일관성 있음'으로 PASS 한다 — 일관되게 무의미한 것을 일관성이라 부르는 셈이다.
    _full = perf_stats(R.reset_index(drop=True)).get("Sharpe", np.nan)
    if _no_alpha_to_test(_full):
        _rec("R8", "하위기간 일관성", None,
             f"전체 구간 알파가 없어(Sharpe {_full:.2f} ≤ {ALPHA_FLOOR}) 연도별 일관성을 "
             f"논할 단계가 아닙니다. 양수 연도 비율만으로 '일관성 있음'이라고 쓰지 않습니다.",
             f"{pos}/{len(yrs)}개 연도 양수 ({ratio:.0%})")
        runtime_mark("R8", time.time() - t0)
        return
    ok = ratio >= 0.6
    _rec("R8", "하위기간 일관성", bool(ok),
         "대부분의 연도에서 양(+)" if ok else "특정 연도에 성과가 몰려 있음 — 일관성 부족",
         f"{pos}/{len(yrs)}개 연도 양수 ({ratio:.0%})")
    runtime_mark("R8", time.time() - t0)


# ── R10 : 정책반증 (고용장려금 캘린더 ±6M 제외) ─────────────────────────────────────────────
def R10_policy_falsify(P: pd.DataFrame, cal: pd.DataFrame, months: pd.DatetimeIndex,
                       run_fn: Callable) -> None:
    t0 = time.time()
    m = policy_mask(cal, months)
    clean = pd.DatetimeIndex(months[~m.to_numpy()])
    if len(clean) < 18:
        _rec("R10", "정책반증 (고용정책 ±6M 제외)", None,
             f"정책 제외 후 남은 표본이 {len(clean)}개월뿐이라 검정력이 없습니다. "
             f"제외 대상 정책이 10년을 거의 덮고 있다는 사실 자체를 결론에 명시하세요.")
        runtime_mark("R10", time.time() - t0)
        return
    # ★★ 불연속 월 인덱스를 백테스트에 그대로 넘기지 않는다 ★★
    #   clean 은 정책창을 도려낸 결과라 중간에 수십 개월짜리 구멍이 있다. 그것을
    #   months_override 로 넘기면 포지션·보유개월·회전율·복리가 **구멍을 건너뛰며 이어져**
    #   존재한 적 없는 연속 시계열이 만들어진다. 그 위에서 'TP_N1 폐기' 를 판정하고 있었다.
    #   → 백테스트는 실제 연속 구간에서 한 번만 돌리고, **성과 통계만** 정책창 밖 달로
    #     제한한다. 포지션은 진짜 역사 위에서 형성되고, 판정은 '알파가 정책창에서만
    #     나왔는가'라는 원래 질문에 정확히 답한다.
    bt_full = run_fn(P, label="R10_base", months_override=months)
    base = _stat(bt_full, "Sharpe")
    try:
        _r = _ret_series(bt_full, pd.DatetimeIndex(months))
        _sub = _r.reindex(clean).dropna()
        # ★ perf_stats 는 n/turnover/cost 를 선택 컬럼으로 다루도록 고쳤지만, 호출 규약은
        #   R0 과 똑같이 맞춰 둔다. 예전엔 month·ret 두 열만 넘겨 KeyError('n') 가 났고,
        #   아래 except 가 그것을 삼켜 off=nan → **항상 FAIL** 이었다.
        #   즉 이 검사는 데이터와 무관하게 100% 확률로 'TP_N1 폐기 대상' 을 출력했다.
        off = float(perf_stats(pd.DataFrame({"month": _sub.index, "ret": _sub.to_numpy(),
                                             "n": 0, "turnover": 0.0, "cost": 0.0}))
                    .get("Sharpe", np.nan)) if len(_sub) >= 18 else np.nan
    except Exception as e:                                          # noqa
        LOG.warn(f"R10 정책제외 구간 통계 산출 실패({type(e).__name__}: {str(e)[:120]}) — "
                 f"판정을 유보합니다.")
        off = np.nan
    if not np.isfinite(off):
        _rec("R10", "정책반증 (고용정책 ±6M 제외)", None,
             f"정책제외 구간의 Sharpe 를 산출하지 못해 판정을 유보합니다"
             f"(유효 {len(clean)}개월). '알파가 사라졌다'고 쓰지 않습니다 — "
             f"측정에 실패한 것과 반증된 것은 다른 사건입니다.",
             f"전체 {len(months)}개월 Sharpe {base:.2f}")
        runtime_mark("R10", time.time() - t0)
        return
    nums = (f"전체 {len(months)}개월 Sharpe {base:.2f} → "
            f"정책제외 {len(clean)}개월 {off:.2f} (같은 백테스트의 부분표본)")
    if _no_alpha_to_test(base):
        _rec("R10", "정책반증 (고용정책 ±6M 제외)", None,
             f"전체 구간에 반증할 알파가 없습니다(Sharpe {base:.2f} ≤ {ALPHA_FLOOR}). "
             f"'정책 구간을 빼도 유지됐다'고 쓰지 않습니다 — 유지될 것이 없었습니다.", nums)
        runtime_mark("R10", time.time() - t0)
        return
    keep = off / base
    ok = np.isfinite(off) and off > 0 and keep >= 0.5
    _rec("R10", "정책반증 (고용정책 ±6M 제외)", bool(ok),
         "정책 구간을 빼도 알파가 유지됨 — 보조금 유인 채용의 부산물이 아님" if ok else
         "★ 정책 구간을 빼면 알파가 사라짐 — 스펙 §12-5 상 TP_N1 폐기 대상입니다",
         nums + f" (잔존 {keep:.0%})")
    runtime_mark("R10", time.time() - t0)


def report_robustness_v3():
    rows = [[r["id"], _trunc(r["name"], 26),
             "PASS" if r["passed"] else ("N/A" if r["passed"] is None else "FAIL"),
             _trunc(r["numbers"] or "", 52), _trunc(r["detail"], 46)] for r in ROBUST_V3]
    LOG.table(rows, ["ID", "검사", "판정", "실측", "해석"],
              ["c", "l", "c", "l", "l"], title="강건성 검사 종합 (§11)", maxw=54)
    n_fail = sum(1 for r in ROBUST_V3 if r["passed"] is False)
    n_pass = sum(1 for r in ROBUST_V3 if r["passed"] is True)
    n_na = sum(1 for r in ROBUST_V3 if r["passed"] is None)
    LOG.info(f"강건성 종합 — 통과 {n_pass} · 실패 {n_fail} · 판정불가 {n_na}")
    kills = [r for r in ROBUST_V3 if r["passed"] is False and r["id"] in ("R0", "R1", "R2-N", "R10")]
    if kills:
        LOG.warn("★ 킬 기준에 해당하는 실패: " + ", ".join(r["id"] for r in kills) +
                 " — 스펙 §12 는 파라미터 조정으로 통과시키는 것을 금지합니다. "
                 "실패는 실패대로 보고하는 것이 이 문서의 산출물입니다.")
