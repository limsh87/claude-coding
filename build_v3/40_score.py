# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  셀 정규화 → TP(clip×clip) → 거부권 → Signal   (스펙 §8)                              ║
# ║                                                                                          ║
# ║  원칙 2 ── 트레이드오프 쌍은 clip(z,0) × clip(z,0). z×z 금지.                              ║
# ║    z×z 를 쓰면 '개선도 대가회피도 셀 하위'인 최악의 종목이 음×음=양 으로 최고점을 받는다.   ║
# ║    실측하면 이 사분면이 정의역의 약 4분의 1이다. 부호 버그 한 줄이 전략을 정확히 뒤집는다.  ║
# ║                                                                                          ║
# ║  원칙 3 ── 셀 정규화는 rank(pct=True) + transform. groupby.apply 금지(수십 배 느리다).     ║
# ║                                                                                          ║
# ║  ★ 본선과 강건성 비교팔은 **반드시 같은 함수(score_arm)** 를 통과한다.                      ║
# ║    비교팔이 다른 경로로 점수를 만들면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'  ║
# ║    를 재게 된다. 아무것도 빼지 않은 널-절제가 ΔSharpe +2.08 로 나온 전례가 있다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _clean_num(P: pd.DataFrame, name_or_series) -> pd.Series:
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(name_or_series, errors="coerce")
    # ±inf 를 먼저 NaN 으로. rank 는 inf 를 최대값으로 취급해 셀 순위를 통째로 왜곡한다.
    return v.replace([np.inf, -np.inf], np.nan).astype("float64")


def _rank_in(v: pd.Series, cells: pd.Series, min_n: int) -> Tuple[pd.Series, pd.Series]:
    """(셀 내 백분위, 셀 내 유효관측수). 표본 부족 셀은 호출자가 상위 셀로 폴백한다.

    ★ transform("size") 가 아니라 count 를 쓴다. size 는 NaN 행까지 세므로,
      30행짜리 셀에 그 센서 관측이 3개뿐이어도 '표본 충분'으로 통과해 3점짜리 순위가
      다른 셀의 30점짜리 순위와 나란히 곱해진다.
    """
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    return g.rank(pct=True, method="average"), g.transform("count")


def cell_rank(P: pd.DataFrame, name_or_series, min_n: int = None) -> pd.Series:
    """셀 내 백분위 [0,1] + 폴백 사다리 (month|ind_mid|size → month|ind_mid|ALL → month|ALL|ALL).

    폴백이 필요한 이유: 셀에 종목이 30개 있어도 '그 센서를 관측한' 종목은 5개뿐일 수 있다.
    셀 크기만 보고 판단하면 그 센서는 전부 NaN 이 되고, 아무 신호도 못 내면서
    로그에는 아무것도 남지 않는다 — 가장 나쁜 조용한 실패다.
    """
    min_n = CELL_MIN_N_V3 if min_n is None else min_n
    v = _clean_num(P, name_or_series)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    for lvl in ("cell", "cell_l2", "cell_l3"):
        if lvl not in P.columns:
            continue
        need = out.isna() & v.notna()
        if not need.any():
            break
        r, n = _rank_in(v, P[lvl], min_n)
        out = out.where(~need, r.where(n >= min_n))
    return out.astype("float32")


def cell_z(P: pd.DataFrame, name_or_series, min_n: int = None) -> pd.Series:
    """셀 내 z-score (winsorize ±2σ → z). U축 합성에만 쓴다 — TP 는 랭크 기반이다."""
    min_n = CELL_MIN_N_V3 if min_n is None else min_n
    v = _clean_num(P, name_or_series)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    for lvl in ("cell", "cell_l2", "cell_l3"):
        if lvl not in P.columns:
            continue
        need = out.isna() & v.notna()
        if not need.any():
            break
        grp = P[lvl].astype(object).fillna("__NA__").to_numpy()
        g = v.groupby(grp, observed=True, dropna=False)
        cnt, mu0, sd0 = g.transform("count"), g.transform("mean"), g.transform("std", ddof=0)
        w = v.clip(lower=mu0 - 2.0 * sd0, upper=mu0 + 2.0 * sd0)
        gw = w.groupby(grp, observed=True, dropna=False)
        mu, sd = gw.transform("mean"), gw.transform("std", ddof=0)
        z = (w - mu) / sd.where(sd > 0)
        z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)
        out = out.where(~need, z.where(cnt >= min_n))
    return out.astype("float32")


def tp(P: pd.DataFrame, a, b) -> pd.Series:
    """★ 스펙 §8 그대로:  za = rank(a)-0.5, zb = rank(b)-0.5,  TP = max(za,0) × max(zb,0)

    · 결과는 항상 [0, 0.25]. 음수가 나올 수 없으므로 '최악이 최고점'이 구조적으로 불가능하다.
    · 한쪽이 결측이면 결과도 결측. 0 으로 채우면 '대가를 치르지 않았다'는 거짓 주장이 된다.
    """
    za = cell_rank(P, a) - 0.5
    zb = cell_rank(P, b) - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    return pd.Series(out, index=P.index).where(za.notna() & zb.notna()).astype("float32")


# ── TP 정의표 (스펙 §8) ─────────────────────────────────────────────────────────────────────
TP_DEFS = [
    ("TP_I1", "i_capex",  "i_roic",    "확장하는데 수익성 유지"),
    ("TP_I2", "i_sales",  "i_turn",    "매출↑ × 회전유지"),
    ("TP_N1", "nl_emp",   "nl_premium", "★고부가 인력 확충 (이 전략의 핵심 신호)"),
    ("TP_N2", "nl_emp",   "nl_vapp",   "희석 없는 확장"),
    ("TP_N3", "nl_emp",   "nl_regular", "정규직으로 늘림 = 확신의 증거"),
    ("TP_I4", "i_sales",  "i_accr",    "매출↑ × 발생액유지"),
    ("TP_P1", "p_payout", "p_invest",  "환원↑ × 투자↑ = 잉여현금창출력"),
    ("TP_P2", "acq_size", "p_cancel",  "취득규모 × 소각실행 = 진정성"),
]


def build_tps(P: pd.DataFrame) -> pd.DataFrame:
    P = P.copy()
    rows = []
    for name, a, b, desc in TP_DEFS:
        P[name] = tp(P, a, b)
        cov = float(P[name].notna().mean()) if len(P) else 0.0
        pos = float((P[name] > 0).mean()) if len(P) else 0.0
        rows.append([name, f"{a} × {b}", _trunc(desc, 30), f"{cov*100:.1f}%", f"{pos*100:.1f}%"])
    LOG.table(rows, ["TP", "구성 (개선 × 대가회피)", "의미", "관측 커버리지", "양(>0) 비율"],
              ["l", "l", "l", "r", "r"], title="트레이드오프 쌍 (clip×clip · 음수 불가)")
    dead = [n for n, *_ in TP_DEFS if P[n].notna().sum() == 0]
    if dead:
        LOG.warn(f"관측이 한 건도 없는 TP: {dead} — 해당 원천 데이터가 비었습니다. "
                 f"E 는 나머지 TP 의 결측 제외 평균으로 계산되며, 이 사실은 리포트에 남습니다.")
    return P


# ── 거부권 V ∈ {0,1} — 연속화·가중치화·상쇄 금지 ────────────────────────────────────────────
VETO_DEFS_V3 = [
    ("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출 > 1.5", "제외"),
    ("V2", "순이익>0 인데 영업CF < 0.5×순이익 3분기 연속", "제외"),
    ("V3", "90일 내 대규모 희석성 조달(유증/CB/BW/감자)", "제외"),
    ("V5", "자본잠식 · 관리종목 · 감사의견 비적정", "제외"),
    ("V6", "유동성 하한 미달 또는 거래정지", "제외"),
    ("V8", "인원 급증(상위20%) + 유효세율 급락(<-3%p)", "제외"),
]
VETO_COLS_V3 = [v[0] for v in VETO_DEFS_V3]


def apply_vetoes_v3(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)
    n = len(P)

    # V1 — 밀어내기
    d_rev = g("revenue_ttm").diff(12)
    push = safe_div(g("inventory").diff(12).fillna(0) + g("receivable").diff(12).fillna(0), d_rev)
    P["v1_metric"] = push
    P["V1"] = np.where((d_rev > 0) & (push > 1.5), 0.0, 1.0)

    # V2 — 이익-현금 괴리 3분기 연속. 분기 프레임에서 만든 플래그를 as-of 로 실어 왔다.
    #      (월 패널에서 rolling(9) 로 세면 같은 분기값이 1~4개월 반복돼 발동이 밀린다)
    v2q = col(P, "v2_bad_3q")
    P["V2"] = np.where(v2q.fillna(0.0) >= 1.0, 0.0, 1.0)

    # V3 — 희석성 조달
    P["V3"] = 1.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns and "event" in dis.columns:
        d = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue", "capital_reduce"])].copy()
        if len(d):
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            ev = d.groupby(["corp_code", "month"]).size().rename("dilution").reset_index()
            ev["corp_code"] = ev["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(ev, on=["corp_code", "month"], how="left")
            P["dilution"] = P["dilution"].fillna(0.0)
            P = P.sort_values(["code", "month"])
            rec = (P.groupby("code", observed=True)["dilution"]
                    .transform(lambda s: s.rolling(3, min_periods=1).sum()))   # 90일 ≈ 3개월
            P["V3"] = np.where(rec > 0, 0.0, 1.0)

    # V5 — 자본잠식/관리종목
    P["V5"] = np.where(col(P, "equity").le(0).fillna(False), 0.0, 1.0)
    adm = ctx.get("administrative")
    if adm is not None and len(adm) and "code" in adm.columns:
        P["V5"] = np.where(P["code"].isin(set(adm["code"].dropna())), 0.0, P["V5"])

    # V6 — 유동성
    P["V6"] = np.where((col(P, "adv20").fillna(0) >= MIN_ADV_KRW) &
                       (col(P, "close").fillna(0) > 0), 1.0, 0.0)

    # V8 — 정책 유인 채용 의심 (인원 급증 + 유효세율 급락). 세전이익≤0 이면 eff_tax 가 NaN 이라
    #      자동으로 '판정 유보(V8=1)'가 된다 — 스펙 §7 그대로.
    P["V8"] = 1.0
    if "nl_emp" in P.columns and "d_eff_tax" in P.columns:
        thr = P.groupby("month", observed=True)["nl_emp"].transform(
            lambda s: s.quantile(V8_EMP_TOP_Q))
        hi = (col(P, "nl_emp") > thr).fillna(False)
        drop = (col(P, "d_eff_tax") < V8_TAX_DROP).fillna(False)
        P["V8"] = np.where(hi & drop, 0.0, 1.0)

    for c in VETO_COLS_V3:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(1.0)
        uniq = set(np.unique(P[c].dropna().to_numpy()))
        if not uniq <= {0.0, 1.0}:
            raise ValueError(f"[거부권 위반] {c} 가 이진이 아닙니다: {sorted(uniq)[:5]}. "
                             f"거부권은 절대 연속화하지 않습니다 — 어떤 센서 점수도 "
                             f"밀어내기 정황을 상쇄할 수 없어야 합니다.")
    P["VETO"] = P[VETO_COLS_V3].prod(axis=1)
    fired = {c: int((P[c] == 0).sum()) for c in VETO_COLS_V3}
    LOG.table([[c, d, act, f"{fired[c]:,}", f"{100*fired[c]/max(n,1):.2f}%"]
               for (c, d, act) in VETO_DEFS_V3],
              ["ID", "조건", "조치", "발동 행수", "비율"], ["c", "l", "c", "r", "r"],
              title="거부권 발동 현황 (V∈{0,1} · 곱 · 상쇄 불가)")
    LOG.info(f"거부권 전체 통과 {int((P['VETO']==1).sum()):,}/{n:,}행 "
             f"({100*(P['VETO']==1).mean():.1f}%)")
    return P


# ── 스코어 조립 — 본선·비교팔이 공유하는 유일한 경로 ────────────────────────────────────────
def score_arm(P: pd.DataFrame, tp_cols: Sequence[str], min_tp: int = None,
              use_u: bool = True, use_veto: bool = True) -> Dict[str, pd.Series]:
    """주어진 TP 집합 하나로 E → Signal → Signal_rank 를 만든다.

    Signal = rank_pct(E) × rank_pct(U) × ∏V        (스펙 §8)

    min_tp: 관측된 TP 가 이보다 적으면 제외(FLOOR). 스펙에 없는 우리 쪽 안전장치이므로
            R5 절제검사에서 이 경계값의 민감도를 반드시 함께 출력한다.
    """
    tp_cols = [c for c in tp_cols if c in P.columns]
    min_tp = MIN_TP_OBSERVED if min_tp is None else min_tp
    if not tp_cols:
        raise RuntimeError("증거층(TP) 컬럼이 하나도 없습니다. 위 수집 로그에서 "
                           "어떤 원천이 비었는지 확인하세요.")
    T = P[tp_cols].astype("float64")
    n_obs = T.notna().sum(axis=1)
    E_raw = T.mean(axis=1, skipna=True)                       # 결측 제외 동일가중 (C7)
    E = cell_rank(P, E_raw)
    FLOOR = (n_obs >= min(min_tp, len(tp_cols))).astype(float)
    U = (P["U"].fillna(0.0) if use_u and "U" in P.columns else pd.Series(1.0, index=P.index))
    V = (P["VETO"].fillna(0.0) if use_veto and "VETO" in P.columns
         else pd.Series(1.0, index=P.index))
    Signal = E.fillna(0.0) * U * V * FLOOR
    rank = Signal.groupby(P["month"], observed=True).rank(pct=True, method="average")
    return {"E_raw": E_raw, "E": E, "FLOOR": FLOOR, "Signal": Signal,
            "Signal_rank": rank, "n_tp": n_obs}


def assemble_score_v3(P: pd.DataFrame, tp_cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
    tp_cols = list(tp_cols) if tp_cols else [c for c, *_ in TP_DEFS if c in P.columns]
    live = [c for c in tp_cols if P[c].notna().sum() > 0]
    if len(live) < len(tp_cols):
        LOG.warn(f"관측 0 인 TP {sorted(set(tp_cols)-set(live))} 를 증거층에서 제외합니다. "
                 f"제외하지 않으면 최소 TP 수 조건이 전 종목을 탈락시킵니다.")
    S = score_arm(P, live)
    for k, v in S.items():
        P[k] = v
    globals()["ACTIVE_TP_COLS"] = live

    ret = float(P["FLOOR"].mean()) if len(P) else 0.0
    LOG.table([[c, f"{float(P[c].notna().mean())*100:.1f}%",
                f"{float(P.loc[P[c].notna(), c].mean()):.4f}" if P[c].notna().any() else "-"]
               for c in live],
              ["증거층 TP", "관측 커버리지", "평균값"], ["l", "r", "r"],
              title=f"증거층 E 구성 — {len(live)}개 TP 동일가중 (결측 제외 평균)")
    LOG.info(f"최소 TP 조건(≥{MIN_TP_OBSERVED}개 관측) 통과 {int(P['FLOOR'].sum()):,}/{len(P):,}행 "
             f"({ret*100:.1f}%) · 관측 TP 중앙값 {float(P['n_tp'].median()):.0f}개")
    if ret < 0.03:
        LOG.warn(f"통과율 {ret*100:.1f}% 는 매우 낮습니다. MIN_TP_OBSERVED 를 낮추기 전에 "
                 f"위 TP 커버리지 표에서 '어떤 원천이 비었는지'를 먼저 확인하세요 — "
                 f"임계값을 낮추면 원인이 아니라 증상만 가려집니다.")
    PIPE.io("OUT", "MEM", "scored_panel", P)
    return P
