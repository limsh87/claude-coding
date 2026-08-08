

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-H  사전등록 가설 검정 H1~H4 (SPEC §3) + 메커니즘 검정                                  ║
# ║                                                                                          ║
# ║   H1  연결기업 직전 수익률이 초점기업 다음 수익률을 양(+)으로 예측      기각: t < 2.0        ║
# ║   H2  동일업종 링크를 전부 제거해도 유지된다                            기각: 교차업종 < 40% ║
# ║   H3  소형주·저커버리지·고개인비중에서 더 강하다                        기각: 하위군에서 약함 ║
# ║   H4  발간빈도 가중이 비가중보다 강화된다                               기각: 개선 없음      ║
# ║                                                                                          ║
# ║  ★ §3 의 메커니즘 테스트가 백테스트 통과보다 상위 필터다.                                  ║
# ║    효과는 있는데 이론이 예측한 방향으로 강해지지 않으면 폐기한다.                            ║
# ║  ★ 다중검정: H1~H4 전체에 BH-FDR(q=0.10). 개별 p 값만으로 판정하지 않는다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HYP: "OrderedDict[str, dict]" = OrderedDict()


def _rec(hid: str, name: str, passed: Optional[bool], stat: float, p: float,
         detail: str, extra: Optional[dict] = None):
    HYP[hid] = {"id": hid, "name": name, "pass": passed, "stat": float(stat) if stat is not None else float("nan"),
                "p": float(p) if p is not None else float("nan"), "detail": detail,
                "extra": extra or {}}


def spread_series(P: pd.DataFrame, signal_col: str, q: int = N_QUANTILES,
                  min_per_q: int = 5) -> pd.Series:
    """시점별 Q5−Q1 동일가중 스프레드. 알파 존재 검증용(실행가능성과 무관)."""
    if P is None or not len(P) or signal_col not in P.columns:
        return pd.Series(dtype=float)
    d = P[P[signal_col].notna() & P["fwd_ret"].notna()].copy()
    if not len(d):
        return pd.Series(dtype=float)
    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    g = d.groupby(["date", "qtile"])["fwd_ret"].agg(["mean", "size"]).reset_index()
    piv_m = g.pivot(index="date", columns="qtile", values="mean")
    piv_n = g.pivot(index="date", columns="qtile", values="size")
    if q not in piv_m.columns or 1 not in piv_m.columns:
        return pd.Series(dtype=float)
    ok = (piv_n[q] >= min_per_q) & (piv_n[1] >= min_per_q)
    return (piv_m[q] - piv_m[1])[ok].dropna()


def mask_cross_sector(LM: LinkMatrices, sector: pd.DataFrame) -> LinkMatrices:
    """H2 — 동일업종 링크를 '전부' 제거한 링크 행렬을 만든다.

    업종 모멘텀의 재포장이 아님을 보이려면 같은 업종 쌍을 남겨두면 안 된다.
    희소행렬에서 업종 블록만 지우는 방식으로 처리한다(밀집 마스크를 만들지 않는다).
    """
    out = LinkMatrices(LM.mode + "_xsector")
    out.codes, out.cidx = list(LM.codes), dict(LM.cidx)
    if _sp is None or not LM.W:
        return out
    smap = (sector.set_index("code")["sector"].to_dict()
            if sector is not None and len(sector) else {})
    sec_arr = np.array([str(smap.get(c, "미분류")) for c in LM.codes])
    uniq = {s: i for i, s in enumerate(sorted(set(sec_arr)))}
    sid = np.array([uniq[s] for s in sec_arr], dtype=np.int32)
    for m, W in LM.W.items():
        C = W.tocoo()
        keep = sid[C.row] != sid[C.col]
        out.W[m] = _csr((C.data[keep], (C.row[keep], C.col[keep])), shape=W.shape)
        out.stats.append({"month": m, "n_pair": int(out.W[m].nnz // 2),
                          "n_pair_full": int(W.nnz // 2)})
    S = out.summary()
    if len(S) and S["n_pair_full"].sum() > 0:
        keep_pct = 100.0 * S["n_pair"].sum() / max(1, S["n_pair_full"].sum())
        LOG.info(f"H2 교차업종 마스킹: 링크쌍 {keep_pct:.1f}% 잔존 "
                 f"(동일업종 쌍 {100-keep_pct:.1f}% 제거)")
    return out


# ── H1 ──────────────────────────────────────────────────────────────────────────────────────
def test_H1(P: pd.DataFrame, signal_col: str, ppy: float) -> pd.Series:
    sp = spread_series(P, signal_col)
    if not len(sp):
        _rec("H1", "공동커버리지 신호의 예측력", None, np.nan, np.nan,
             "스프레드 계열을 만들 수 없음 (표본 부족)")
        return sp
    mu, t, lag = nw_tstat(sp.to_numpy(float), ppy)
    p = two_sided_p(t)
    passed = bool(np.isfinite(t) and t >= 2.0)
    _rec("H1", "공동커버리지 신호의 예측력", passed, t, p,
         f"Q5−Q1 평균 {mu*ppy:+.2%}/년 · NW t={t:+.2f} (lag={lag}) · 기각선 t<2.0",
         {"mean_period": mu, "ann": mu * ppy, "n": len(sp), "lag": lag})
    return sp


# ── H2 ──────────────────────────────────────────────────────────────────────────────────────
def test_H2(sp_full: pd.Series, sp_xsec: pd.Series, ppy: float) -> None:
    if not len(sp_full) or not len(sp_xsec):
        _rec("H2", "업종 모멘텀의 재포장이 아님", None, np.nan, np.nan,
             "교차업종 전용 스프레드를 만들 수 없음")
        return
    a, b = float(sp_full.mean()), float(sp_xsec.mean())
    ratio = float(b / a) if abs(a) > 1e-12 else float("nan")
    mu, t, lag = nw_tstat(sp_xsec.to_numpy(float), ppy)
    passed = bool(np.isfinite(ratio) and ratio >= 0.40 and a > 0)
    _rec("H2", "업종 모멘텀의 재포장이 아님", passed, t, two_sided_p(t),
         f"교차업종 전용 {b*ppy:+.2%}/년 vs 전체 {a*ppy:+.2%}/년 = {ratio:.0%} "
         f"(기각선 <40%) · NW t={t:+.2f}",
         {"ratio": ratio, "full_ann": a * ppy, "xsec_ann": b * ppy, "lag": lag})


# ── H3 (메커니즘) ───────────────────────────────────────────────────────────────────────────
def test_H3(P: pd.DataFrame, signal_col: str, ppy: float,
            retail: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """소형주 / 저커버리지 / 고개인비중 하위군에서 효과가 '더 강한지' 본다.

    제한된 주의(limited attention)와 느린 정보 전파가 메커니즘이라면 반드시 그래야 한다.
    반대로 나오면 알파가 아니라 데이터마이닝이다.
    """
    rows = []
    d = P.copy()
    if retail is not None and len(retail):
        rr = retail.copy()
        rr["code"] = rr["code"].astype(str)
        rr["month"] = as_ts_series(rr["month"])
        d["_m"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
        d = d.merge(rr.rename(columns={"month": "_m"}), on=["code", "_m"], how="left")

    axes = [("규모", "mktcap", "소형", "대형", True),
            ("커버리지", "n_link_used", "저커버리지", "고커버리지", True)]
    if "retail_share" in d.columns and d["retail_share"].notna().any():
        axes.append(("개인비중", "retail_share", "고개인", "저개인", False))
    else:
        LOG.warn("개인 거래비중이 없어 H3 의 세 번째 축을 건너뜁니다 (규모·커버리지로만 판정).")
        open_question("OQ-05", "H3 개인비중 축",
                      "종목별 개인 거래비중 데이터를 확보하지 못했다.",
                      "규모·커버리지 두 축으로만 H3 를 판정하고 그 사실을 명시했다.",
                      "H3 판정력이 약해진다. 통과해도 '부분 확인'으로만 해석해야 한다.")

    ok_axes, passed_axes = 0, 0
    for label, col, lo_name, hi_name, low_is_weak in axes:
        if col not in d.columns or not d[col].notna().any():
            continue
        g = d[d[col].notna()].copy()
        med = g.groupby("date")[col].transform("median")
        lo = g[g[col] <= med]
        hi = g[g[col] > med]
        s_lo = spread_series(lo, signal_col, min_per_q=3)
        s_hi = spread_series(hi, signal_col, min_per_q=3)
        if not len(s_lo) or not len(s_hi):
            continue
        # low_is_weak=True 이면 '하위 절반'이 메커니즘상 강해야 하는 쪽 (소형주·저커버리지)
        strong, weak = (s_lo, s_hi) if low_is_weak else (s_hi, s_lo)
        sname, wname = (lo_name, hi_name)
        m_s, t_s, _ = nw_tstat(strong.to_numpy(float), ppy)
        m_w, t_w, _ = nw_tstat(weak.to_numpy(float), ppy)
        diff = pd.concat([strong.rename("s"), weak.rename("w")], axis=1).dropna()
        m_d, t_d, _ = nw_tstat((diff["s"] - diff["w"]).to_numpy(float), ppy) \
            if len(diff) >= 12 else (np.nan, np.nan, 0)
        good = bool(np.isfinite(m_s) and np.isfinite(m_w) and m_s > m_w)
        ok_axes += 1
        passed_axes += int(good)
        rows.append({"축": label, "예측 강한군": sname, "강한군 연율": m_s * ppy,
                     "강한군 t": t_s, "약한군": wname, "약한군 연율": m_w * ppy,
                     "약한군 t": t_w, "차이 연율": m_d * ppy if np.isfinite(m_d) else np.nan,
                     "차이 t": t_d, "방향 일치": good})
    T = pd.DataFrame(rows)
    if not len(T):
        _rec("H3", "메커니즘 조건부 예측 (소형·저커버리지·고개인)", None, np.nan, np.nan,
             "하위군 분할 표본이 부족해 판정 불가")
        return T
    frac = passed_axes / max(1, ok_axes)
    passed = bool(frac >= 0.5)
    best_t = float(np.nanmax(T["차이 t"].to_numpy(float))) if T["차이 t"].notna().any() else np.nan
    _rec("H3", "메커니즘 조건부 예측 (소형·저커버리지·고개인)", passed, best_t,
         two_sided_p(best_t),
         f"검정 가능한 {ok_axes}개 축 중 {passed_axes}개에서 예측 방향 일치 ({frac:.0%})",
         {"axes": ok_axes, "agree": passed_axes})
    return T


# ── H4 ──────────────────────────────────────────────────────────────────────────────────────
def test_H4(sp_unw: pd.Series, sp_freq: pd.Series, ppy: float,
            sp_skill: Optional[pd.Series] = None) -> None:
    if not len(sp_unw) or not len(sp_freq):
        _rec("H4", "커버리지 강도 가중이 강화한다", None, np.nan, np.nan,
             "가중/비가중 스프레드를 비교할 수 없음")
        return
    j = pd.concat([sp_unw.rename("u"), sp_freq.rename("f")], axis=1).dropna()
    if len(j) < 12:
        _rec("H4", "커버리지 강도 가중이 강화한다", None, np.nan, np.nan,
             f"공통 시점 {len(j)}개로 비교 불가")
        return
    md, td, _ = nw_tstat((j["f"] - j["u"]).to_numpy(float), ppy)
    passed = bool(np.isfinite(md) and md > 0)
    extra = {"unw_ann": float(j["u"].mean()) * ppy, "freq_ann": float(j["f"].mean()) * ppy,
             "diff_ann": md * ppy}
    txt = (f"발간빈도 가중 {extra['freq_ann']:+.2%}/년 vs 비가중 {extra['unw_ann']:+.2%}/년 · "
           f"차이 {extra['diff_ann']:+.2%}/년 (t={td:+.2f})")
    if sp_skill is not None and len(sp_skill):
        js = pd.concat([sp_unw.rename("u"), sp_skill.rename("s")], axis=1).dropna()
        if len(js) >= 12:
            ms, ts, _ = nw_tstat((js["s"] - js["u"]).to_numpy(float), ppy)
            extra["skill_diff_ann"] = ms * ppy
            txt += f" · 고스킬한정 차이 {ms*ppy:+.2%}/년 (t={ts:+.2f})"
    _rec("H4", "커버리지 강도 가중이 강화한다", passed, td, two_sided_p(td), txt, extra)


# ── 종합 판정 ───────────────────────────────────────────────────────────────────────────────
def finalize_hypotheses(q: float = 0.10) -> pd.DataFrame:
    """BH-FDR 보정 후 최종 판정표. 개별 p 만으로 결론내지 않는다."""
    ids = [k for k in ("H1", "H2", "H3", "H4") if k in HYP]
    if not ids:
        return pd.DataFrame()
    F = fdr_table(ids, [HYP[i]["p"] for i in ids], q=q)
    rows = []
    for i, (_, fr) in zip(ids, F.iterrows()):
        h = HYP[i]
        raw = h["pass"]
        # BH-FDR 은 '유의성'에 대한 보정이다. 사전등록 기각조건(예: t<2.0)과 함께 봐야 한다.
        final = None if raw is None else bool(raw and bool(fr["기각(유의)"]))
        h["fdr_sig"] = bool(fr["기각(유의)"])
        h["final"] = final
        rows.append([i, h["name"],
                     {True: "통과", False: "기각", None: "판정불가"}[raw],
                     f"{h['stat']:+.2f}" if np.isfinite(h["stat"]) else "—",
                     f"{h['p']:.4f}" if np.isfinite(h["p"]) else "—",
                     f"{fr['BH 임계']:.4f}",
                     "유의" if fr["기각(유의)"] else "비유의",
                     {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[final]])
    LOG.table(rows, ["ID", "가설", "사전등록 기준", "통계량", "p", f"BH 임계(q={q})",
                     "FDR", "최종"],
              ["c", "l", "c", "r", "r", "r", "c", "c"],
              title=f"사전등록 가설 판정 — BH-FDR 다중검정 보정 (q={q})")
    for i in ids:
        LOG.info(f"  {i}: {HYP[i]['detail']}")
    return F


def final_verdict(bt_base: dict, bench_ew: pd.Series, pbo: dict, dsr: dict,
                  ppy: float) -> dict:
    """SPEC §11 — 사전 확정 기준으로만 기계적으로 판정한다. 사후 변경하지 않는다."""
    g = lambda k: (HYP.get(k, {}) or {}).get("final")
    h1, h2, h3 = g("H1"), g("H2"), g("H3")
    pbo_v = pbo.get("pbo", float("nan"))
    dsr_v = dsr.get("dsr", float("nan"))
    R = bt_base.get("returns", pd.DataFrame())
    excess = float("nan")
    if len(R) and bench_ew is not None and len(bench_ew):
        j = pd.concat([R.set_index(as_ts_series(R["date"]))["ret"].rename("s"),
                       bench_ew.rename("b")], axis=1).dropna()
        if len(j) >= 6:
            excess = float((j["s"] - j["b"]).mean() * ppy)

    crit = [
        ("H1 통과 (BH-FDR 보정 후)", h1 is True),
        ("H2 통과 (교차업종 ≥ 전체의 40%)", h2 is True),
        ("H3 통과 (소형·저커버리지에서 강화)", h3 is True),
        ("PBO < 0.5", bool(np.isfinite(pbo_v) and pbo_v < 0.5)),
        ("DSR > 0", bool(np.isfinite(dsr_v) and dsr_v > 0)),
        ("동일가중 유니버스 대비 연 +3%p 이상", bool(np.isfinite(excess) and excess >= 0.03)),
    ]
    # ★ 표본 부족으로 포지션 자체가 안 잡힌 경우를 '전략 실패'로 보고하면 안 된다.
    #   PBO=1.0, DSR 미산출 같은 산출물이 그럴듯한 KILL 로 둔갑한다 — 가장 위험한 오보다.
    cash_ratio = float((bt_base.get("meta") or {}).get("cash_ratio", 0.0) or 0.0)
    if cash_ratio > 0.5:
        why = (f"기간의 {cash_ratio:.0%}가 현금 — 유니버스가 작아 분위 포트폴리오가 "
               f"구성되지 않았습니다. 성과·PBO·DSR 은 전략의 성질이 아니라 표본 부족의 결과이며 "
               f"§11 판정을 적용할 수 없습니다.")
        LOG.banner("FINAL VERDICT — NOT_EVALUABLE", why)
        LOG.table([[n, "✔" if v else "✘"] for n, v in crit],
                  ["§11 판정 조건 (참고용 — 판정에 쓰지 않음)", "충족"], ["l", "c"])
        return {"verdict": "NOT_EVALUABLE", "why": why, "criteria": crit,
                "excess_ew": excess, "pbo": pbo_v, "dsr": dsr_v, "cash_ratio": cash_ratio}

    if all(c[1] for c in crit):
        verdict, why = "ACCEPT", "전 조건 충족 — 실전 후보로 승격"
    elif h1 is False or h2 is False or (np.isfinite(pbo_v) and pbo_v >= 0.5):
        reasons = []
        if h1 is False:
            reasons.append("H1 실패")
        if h2 is False:
            reasons.append("H2 실패(업종 모멘텀 재포장)")
        if np.isfinite(pbo_v) and pbo_v >= 0.5:
            reasons.append(f"PBO {pbo_v:.2f} ≥ 0.5")
        verdict, why = "KILL", " · ".join(reasons)
    elif h1 is True and h2 is True and h3 is False:
        verdict, why = "CONDITIONAL", ("H1·H2 통과 + H3 실패 — 알파일 수 있으나 메커니즘 미확인. "
                                       "실전 배분 금지, 페이퍼 트레이딩만.")
    else:
        verdict, why = "CONDITIONAL", "일부 조건 판정불가 — 확정 불가, 관찰 대상"
    LOG.banner(f"FINAL VERDICT — {verdict}", why)
    LOG.table([[n, "✔" if v else "✘"] for n, v in crit] +
              [["동일가중 대비 초과(연)", f"{excess:+.2%}" if np.isfinite(excess) else "—"],
               ["PBO", f"{pbo_v:.3f}" if np.isfinite(pbo_v) else "—"],
               ["DSR", f"{dsr_v:.3f}" if np.isfinite(dsr_v) else "—"]],
              ["§11 판정 조건", "충족"], ["l", "c"])
    return {"verdict": verdict, "why": why, "criteria": crit, "excess_ew": excess,
            "pbo": pbo_v, "dsr": dsr_v}
