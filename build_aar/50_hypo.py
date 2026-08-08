

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-A  사전등록 가설 검정 H1~H5 + BH-FDR (§4, §9-5)                                        ║
# ║                                                                                          ║
# ║  H1  자발적 주의 증가(VAS+)는 이후 1~3개월 수익률을 양(+)으로 예측       기각: Q5−Q1 t<2.0 ║
# ║  H2  효과는 애널리스트의 **기회비용이 클수록** 강하다 (메커니즘 조건부)  기각: 역방향     ║
# ║  H3  자발적 철회(V-DROP)는 음(−) 예측, 인사이동(M-EXIT)은 예측력 없음    기각: 차이 t<2.0 ║
# ║  H4  효과는 저커버리지·소형주에서 강하다                                 기각: 역방향     ║
# ║  H5  VAS 는 **컨센서스 개정에 선행한다**                                 기각: 선행성 없음║
# ║                                                                                          ║
# ║  ★ H5 가 이 전략의 경제적 정당성이다. 주의 재배분이 컨센서스 개정보다 늦다면              ║
# ║    이 신호는 그냥 '느린 개정 대리변수'이고 독립적 가치가 없다(§11 CONDITIONAL).            ║
# ║                                                                                          ║
# ║  ★ 다중검정 보정: 5개 가설에 BH-FDR(q=0.10). "다섯 개 세워두고 하나 통과하면 성공"은        ║
# ║    이 프로젝트에서 가장 흔한 자기기만이므로 구조적으로 막는다.                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HYPO: "OrderedDict[str, dict]" = OrderedDict()


def _record_h(hid: str, name: str, passed: Optional[bool], p: float, detail: str,
              metrics: Optional[dict] = None):
    HYPO[hid] = {"id": hid, "name": name, "pass": (None if passed is None else bool(passed)),
                 "p": (float(p) if p is not None and np.isfinite(p) else np.nan),
                 "detail": detail, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[HYPO[hid]["pass"]]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{hid}] {name} → {icon} · {detail}")


def quantile_spread(S: "pd.DataFrame", panel: "pd.DataFrame", months, hold: int = 1,
                    signal_col: str = "aar_total") -> "pd.DataFrame":
    """월별 Q5−Q1 스프레드 시계열. 백테스트 엔진과 별개로 신호 자체의 예측력을 본다."""
    fwd_col = f"fwd_ret{hold}"
    if fwd_col not in panel.columns:
        fwd_col = "fwd_ret1"
    P = panel[["code", "month", fwd_col]].copy()
    P["code"] = as_str_series(P["code"])
    P["month"] = as_ts_series(P["month"])
    # ★ 호출자가 이미 수익률 컬럼을 붙여 온 프레임을 넘기면 merge 가 _x/_y 접미사를 만들어
    #   dropna(subset=[fwd_col]) 가 KeyError 로 죽는다. 신호 컬럼만 남기고 결합한다.
    Sx = S[[c for c in S.columns if c not in P.columns or c in ("code", "month")]].copy()
    Sx["code"] = as_str_series(Sx["code"])
    Sx["month"] = as_ts_series(Sx["month"])
    d = Sx.merge(P, on=["code", "month"], how="inner").dropna(subset=[signal_col, fwd_col])
    rows = []
    for m, g in d.groupby("month", observed=True):
        if len(g) < PORT_QUANTILES * 4:
            continue
        try:
            q = pd.qcut(g[signal_col].rank(method="first"), PORT_QUANTILES,
                        labels=False, duplicates="drop")
        except Exception:
            continue
        hi, lo = int(np.nanmax(q)), int(np.nanmin(q))
        if hi == lo:
            continue
        r5 = float(g.loc[q == hi, fwd_col].mean())
        r1 = float(g.loc[q == lo, fwd_col].mean())
        rows.append({"month": m, "q5": r5, "q1": r1, "spread": r5 - r1,
                     "n": len(g), "mkt": float(g[fwd_col].mean())})
    out = pd.DataFrame(rows)
    if len(out) and hold > 1:
        # 중첩 보유의 자기상관은 HAC 이 처리한다. 스프레드는 hold 개월 수익이므로
        # 월 환산해 다른 보유기간과 비교 가능하게 만든다.
        out["spread"] = (1.0 + out["spread"]) ** (1.0 / hold) - 1.0
    return out


def test_H1(S: "pd.DataFrame", panel: "pd.DataFrame", months) -> Tuple[bool, float, dict]:
    res = {}
    best_t = -np.inf
    detail = []
    for h in GRID_HOLD:
        sp = quantile_spread(S, panel, months, hold=h)
        if len(sp) < 24:
            detail.append(f"{h}M: 표본 {len(sp)}개월로 부족")
            continue
        mu, t = hac_tstat(sp["spread"].to_numpy())
        res[f"{h}M"] = {"mean": mu, "t": t, "n": len(sp)}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        detail.append(f"{h}M 스프레드 {mu*100:+.3f}%p/월 (HAC t={t:.2f}, {len(sp)}개월)")
    if not res:
        _record_h("H1", "VAS+ 의 양(+) 예측력", None, np.nan, "표본 부족 — 판정 불가", res)
        return (False, np.nan, res)
    p = t_to_p(best_t, dof=max(12, min(v["n"] for v in res.values()) - 1))
    passed = bool(np.isfinite(best_t) and best_t >= 2.0)
    _record_h("H1", "VAS+ 의 양(+) 예측력", passed, p,
              " · ".join(detail) + f" → 기각기준 t<2.0, 최대 t={best_t:.2f}", res)
    return passed, p, res


def test_H2(sig_by_weight: Dict[str, "pd.DataFrame"], panel: "pd.DataFrame",
            months) -> Tuple[Optional[bool], float, dict]:
    """기회비용 가중(발간량·커버리지폭)이 비가중보다 강한가.

    ★ 한가한 애널리스트에서 더 강하면 데이터마이닝 판정이다(명세 §4). 부호를 본다.
    검정: 가중팔 스프레드 − 비가중팔 스프레드 의 HAC t (짝지은 시계열 차이)."""
    if "uw" not in sig_by_weight:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, "비가중 팔이 없어 판정 불가")
        return None, np.nan, {}
    base = quantile_spread(sig_by_weight["uw"], panel, months, hold=1)
    if len(base) < 24:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, f"표본 {len(base)}개월로 부족")
        return None, np.nan, {}
    res, rows, best_t = {}, [], -np.inf
    for w in ("nreports", "ncover"):
        if w not in sig_by_weight:
            continue
        arm = quantile_spread(sig_by_weight[w], panel, months, hold=1)
        j = base.merge(arm, on="month", suffixes=("_uw", f"_{w}"))
        if len(j) < 24:
            continue
        diff = (j[f"spread_{w}"] - j["spread_uw"]).to_numpy()
        mu, t = hac_tstat(diff)
        res[w] = {"diff": mu, "t": t, "n": len(j)}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        rows.append([w, f"{float(j[f'spread_{w}'].mean())*100:+.3f}%p",
                     f"{float(j['spread_uw'].mean())*100:+.3f}%p",
                     f"{mu*100:+.3f}%p", f"{t:.2f}",
                     "기회비용 가중이 우세" if mu > 0 else "★ 비가중이 우세 — 데이터마이닝 신호"])
    if not res:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, "비교 가능한 가중 팔이 없습니다")
        return None, np.nan, res
    LOG.table(rows, ["가중 방식", "가중팔 스프레드", "비가중 스프레드", "차이", "HAC t", "판정"],
              ["l", "r", "r", "r", "r", "l"],
              title="H2 메커니즘 검정 — 바쁜 애널리스트가 특정 종목에 몰릴 때 더 강한가")
    p = t_to_p(best_t, dof=max(12, min(v["n"] for v in res.values()) - 1))
    passed = bool(np.isfinite(best_t) and best_t > 1.0)
    _record_h("H2", "기회비용 가중 우위", passed, p,
              f"최대 차이 t={best_t:.2f} " +
              ("— 기회비용이 큰 애널의 주의가 더 정보적입니다." if passed else
               "— 기회비용 가중이 비가중을 유의하게 이기지 못했습니다. 메커니즘 예측이 "
               "성립하지 않으므로 §11 ACCEPT 조건 미충족입니다."), res)
    return passed, p, res


def test_H3(drops: "pd.DataFrame", panel: "pd.DataFrame", months) -> Tuple[Optional[bool], float, dict]:
    """V-DROP(+H-EXIT) 은 음(−), M-EXIT 은 예측력 없음. **캘린더타임**으로 검정한다.

    ★ 겹치는 이벤트 창의 횡단면 상관 때문에 CAR 의 단순 t검정은 표준오차를 크게
      과소추정한다. 캘린더타임 포트폴리오는 각 달의 관측이 하나뿐이라 SE 가 정직하다."""
    if drops is None or drops.empty:
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan, "철회 사건이 없습니다")
        return None, np.nan, {}
    d = drops.copy()
    d["grp"] = np.where(d["klass"].isin(["V-DROP", "H-EXIT"]), "자발적철회",
                        np.where(d["klass"] == "M-EXIT", "M-EXIT(플라시보)", "기타"))
    ct = calendar_time_alpha(d[d["grp"] != "기타"], panel, months, hold_m=6, group_col="grp")
    if ct.empty or ct["t_hac"].isna().all():
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan,
                  "캘린더타임 포트폴리오를 만들 표본이 부족합니다")
        return None, np.nan, {}
    LOG.table([[r["group"], f"{int(r['n_months'])}", f"{r['avg_names']:.1f}",
                f"{r['mean_excess_m']*100:+.3f}%p", f"{r['t_hac']:.2f}",
                f"{r['p']:.4f}" if np.isfinite(r["p"]) else "—",
                f"{r['ann_excess']*100:+.1f}%"] for _, r in ct.iterrows()],
              ["군", "월수", "평균종목수", "월평균 초과", "HAC t", "p", "연환산"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="H3 캘린더타임 포트폴리오 (겹치는 이벤트 창의 상관을 구조적으로 제거)")
    v = ct[ct["group"] == "자발적철회"]
    mm = ct[ct["group"] == "M-EXIT(플라시보)"]
    tv = float(v["t_hac"].iloc[0]) if len(v) else np.nan
    tm = float(mm["t_hac"].iloc[0]) if len(mm) else np.nan
    mv = float(v["mean_excess_m"].iloc[0]) if len(v) else np.nan
    mm_ = float(mm["mean_excess_m"].iloc[0]) if len(mm) else np.nan
    res = {"t_vdrop": tv, "t_mexit": tm, "mean_vdrop": mv, "mean_mexit": mm_}
    if not np.isfinite(tv):
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan, "자발적 철회군 표본 부족", res)
        return None, np.nan, res
    p = t_to_p(tv, dof=max(12, int(v["n_months"].iloc[0]) - 1))
    passed = bool(mv < 0 and tv <= -2.0)
    _record_h("H3", "자발적 철회의 음(−) 예측력", passed, p,
              f"자발적 철회 {mv*100:+.3f}%p/월 (t={tv:.2f}) vs "
              f"M-EXIT {mm_*100:+.3f}%p/월 (t={tm:.2f}). " +
              ("자발적 철회가 유의한 음의 예측력을 가집니다." if passed else
               "자발적 철회의 음의 예측력이 기각기준(t≤-2.0)에 미달합니다."), res)
    return passed, p, res


def test_H4(S: "pd.DataFrame", panel: "pd.DataFrame", uni: "pd.DataFrame",
            months) -> Tuple[Optional[bool], float, dict]:
    """저커버리지·소형주에서 더 강한가. 조건부 분할 스프레드를 비교한다."""
    P = panel[["code", "month", "fwd_ret1"]].copy()
    P["code"] = as_str_series(P["code"])
    U = uni[["code", "month", "size_pct"]].copy()
    U["code"] = as_str_series(U["code"])
    d = (S.merge(P, on=["code", "month"], how="inner")
          .merge(U, on=["code", "month"], how="left")
          .dropna(subset=["aar_total", "fwd_ret1"]))
    if len(d) < 500:
        _record_h("H4", "소형·저커버리지 조건부 강도", None, np.nan, "표본 부족")
        return None, np.nan, {}
    rows, res, best_t = [], {}, -np.inf
    for cut_name, col, lo_lab, hi_lab in (("규모", "size_pct", "소형(하위50%)", "대형(상위50%)"),
                                          ("커버리지", "n_analyst", "저커버(하위50%)", "고커버(상위50%)")):
        if col not in d.columns or d[col].notna().sum() < 200:
            continue
        med = d.groupby("month", observed=True)[col].transform("median")
        lo = d[d[col] <= med]
        hi = d[d[col] > med]
        sp_l = quantile_spread(lo, panel, months, hold=1)
        sp_h = quantile_spread(hi, panel, months, hold=1)
        if len(sp_l) < 24 or len(sp_h) < 24:
            continue
        j = sp_l.merge(sp_h, on="month", suffixes=("_lo", "_hi"))
        diff = (j["spread_lo"] - j["spread_hi"]).to_numpy()
        mu, t = hac_tstat(diff)
        res[cut_name] = {"diff": mu, "t": t}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        rows.append([cut_name, lo_lab, f"{float(j['spread_lo'].mean())*100:+.3f}%p",
                     hi_lab, f"{float(j['spread_hi'].mean())*100:+.3f}%p",
                     f"{mu*100:+.3f}%p", f"{t:.2f}",
                     "예측 방향과 일치" if mu > 0 else "★ 반대 방향(대형에서 강함)"])
    if not rows:
        _record_h("H4", "소형·저커버리지 조건부 강도", None, np.nan, "분할 표본이 부족합니다")
        return None, np.nan, res
    LOG.table(rows, ["분할", "약군", "약군 스프레드", "강군", "강군 스프레드", "차이", "HAC t", "판정"],
              ["l", "l", "r", "l", "r", "r", "r", "l"], title="H4 조건부 예측 검정")
    p = t_to_p(best_t, dof=24)
    passed = bool(np.isfinite(best_t) and best_t > 1.0)
    _record_h("H4", "소형·저커버리지 조건부 강도", passed, p,
              f"최대 차이 t={best_t:.2f}", res)
    return passed, p, res


def build_consensus_revision(L: "pd.DataFrame", months) -> "pd.DataFrame":
    """컨센서스 개정 대리변수 — 목표주가 리비전.

    ★ 한계 명시: 역사적 컨센서스 fwd EPS 시계열은 복원이 불가능하다. 그래서 §5 의
      '컨센서스 EPS 추정치' 를 **같은 애널리스트가 같은 종목에 제시한 목표주가의 개정**
      으로 대체한다. 개정 방향은 EPS 개정과 강하게 동행하므로 선행성 검정의 취지는
      보존되지만, 이것이 대리변수라는 사실을 결과 해석에 반드시 반영해야 한다.
      (그래서 H5 결과는 '컨센서스 개정 대리변수 대비 선행성' 으로만 서술한다)
    """
    cols = ["code", "month", "rev"]
    if L is None or L.empty or "target_price" not in L.columns:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code", "target_price"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    x = x.sort_values(["code", "analyst_id", "pub_date"])
    x["prev_tp"] = x.groupby(["code", "analyst_id"], observed=True)["target_price"].shift(1)
    x["dir"] = np.where(x["target_price"] > x["prev_tp"] * 1.001, 1.0,
                        np.where(x["target_price"] < x["prev_tp"] * 0.999, -1.0, 0.0))
    x.loc[x["prev_tp"].isna(), "dir"] = np.nan
    r = (x.dropna(subset=["dir"]).groupby(["code", "month"], observed=True)["dir"]
          .mean().rename("rev").reset_index())
    r = r[r["month"].isin(months)]
    LOG.info(f"컨센서스 개정 대리변수(목표주가 리비전) {len(r):,}건 · "
             f"상향 비중 {float((r['rev']>0).mean())*100:.1f}%")
    return r[cols]


def test_H5(V: "pd.DataFrame", rev: "pd.DataFrame", months) -> Tuple[Optional[bool], float, dict]:
    """VAS 가 컨센서스 개정에 **선행**하는가 (양방향 패널 그레인저)."""
    if V is None or V.empty or rev is None or rev.empty:
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan,
                  "VAS 또는 컨센서스 개정 대리변수가 없어 판정 불가")
        return None, np.nan, {}
    vas_i = (V.dropna(subset=["VAS"]).groupby(["code", "month"], observed=True)["VAS"]
              .mean().rename("vas").reset_index())
    d = vas_i.merge(rev, on=["code", "month"], how="inner")
    if len(d) < 500:
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan,
                  f"공통 관측 {len(d):,}행으로 부족 — 판정 불가")
        return None, np.nan, {}
    fwd = panel_granger(d, cause="vas", effect="rev", entity="code", time="month", lags=3)
    bwd = panel_granger(d, cause="rev", effect="vas", entity="code", time="month", lags=3)
    LOG.table([["VAS → 컨센서스 개정 (선행)", f"{fwd.get('F', np.nan):.2f}",
                f"{fwd.get('p', np.nan):.4g}", f"{fwd.get('n', 0):,}"],
               ["컨센서스 개정 → VAS (후행)", f"{bwd.get('F', np.nan):.2f}",
                f"{bwd.get('p', np.nan):.4g}", f"{bwd.get('n', 0):,}"]],
              ["방향", "F", "p", "관측"], ["l", "r", "r", "r"],
              title="H5 양방향 패널 그레인저 (개체·시간 고정효과, lag 1~3)")
    pf, pb = fwd.get("p", np.nan), bwd.get("p", np.nan)
    res = {"p_fwd": pf, "p_bwd": pb, "F_fwd": fwd.get("F"), "F_bwd": bwd.get("F")}
    if not np.isfinite(pf):
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan, "그레인저 검정 산출 실패", res)
        return None, np.nan, res
    lead = bool(pf < 0.05 and (not np.isfinite(pb) or fwd.get("F", 0) > bwd.get("F", 0)))
    _record_h("H5", "컨센서스 개정 대비 선행성", lead, pf,
              f"선행 p={pf:.4g} (F={fwd.get('F', np.nan):.2f}) vs "
              f"후행 p={pb:.4g} (F={bwd.get('F', np.nan):.2f}). " +
              ("VAS 가 개정보다 먼저 움직입니다 — 독립적 정보 가치가 있습니다."
               if lead else
               "★ 선행성을 보이지 못했습니다. §11 CONDITIONAL — 이 신호는 컨센서스 개정의 "
               "느린 대리변수일 수 있으므로 독립 배분을 금지하고 기존 개정 팩터와의 "
               "상관 분석만 수행해야 합니다."), res)
    return lead, pf, res


def finalize_hypotheses() -> "pd.DataFrame":
    """BH-FDR(q=0.10) 적용 후 최종 판정표."""
    ids = list(HYPO)
    if not ids:
        return pd.DataFrame()
    p = np.array([HYPO[i]["p"] for i in ids], dtype=float)
    rej, padj = bh_fdr(p, q=FDR_Q)
    rows = []
    for i, hid in enumerate(ids):
        h = HYPO[hid]
        raw = {True: "통과", False: "기각", None: "판정불가"}[h["pass"]]
        fdr_ok = ("—" if not np.isfinite(p[i]) else ("생존" if rej[i] else "탈락"))
        final = (h["pass"] is True) and (rej[i] if np.isfinite(p[i]) else False)
        h["fdr_pass"] = bool(final)
        rows.append([hid, _trunc(h["name"], 28), raw,
                     f"{p[i]:.4g}" if np.isfinite(p[i]) else "—",
                     f"{padj[i]:.4g}" if np.isfinite(padj[i]) else "—",
                     fdr_ok, "✔ 최종통과" if final else "✘"])
    LOG.table(rows, ["ID", "가설", "개별판정", "p", "보정 p", f"BH-FDR(q={FDR_Q})", "최종"],
              ["l", "l", "c", "r", "r", "c", "c"],
              title="사전등록 가설 최종 판정 (다중검정 보정 후) — "
                    "다섯 개 중 하나 통과를 성공이라 부르지 않기 위한 장치")
    return pd.DataFrame([{**HYPO[i], "p_adj": float(padj[k])} for k, i in enumerate(ids)])
