

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-Q2  2차 필터 — U-200 → 60~80종목 (§6.3)  ·  3차 필터 3-A 규칙판 (§7.2)                 ║
# ║                                                                                          ║
# ║  Score2 = 2.0·z(ΔNONFIN) + 1.0·z(ΔTONE_resid) − 배제                                      ║
# ║  배제플래그는 페널티가 아니라 '하드 제외'다. 가중치 2:1 은 커버리지 비대칭을 반영한          ║
# ║  사전등록 값이며 튜닝하지 않는다.                                                          ║
# ║                                                                                          ║
# ║  ★ 이 설계의 핵심은 '리포트 없는 종목이 살아남는가' 다(§6.2). 살아남지 못하면 U-200 으로   ║
# ║    유니버스를 넓힌 효과가 통째로 소멸한다. 그래서 코드가 매 실행 그 사실을 표로 검증한다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EXCL_FLAGS = ["x_related_up", "x_contingent", "x_lawsuit", "x_audit", "x_holder_chg", "x_cbbw"]
EXCL_LABEL = {
    "x_related_up": "특수관계자 비중 상승(상위20%)",
    "x_contingent": "우발부채·지급보증 자본대비 5%p↑",
    "x_lawsuit":    "신규 소송 (소송가액/자본 > 5%)",
    "x_audit":      "감사의견 강조사항·특기사항",
    "x_holder_chg": "최대주주 변경",
    "x_cbbw":       "전환사채·신주인수권부사채 발행",
}


def build_exclusion_flags(P: pd.DataFrame) -> pd.DataFrame:
    """§6.1 배제 플래그. 근거가 없으면(관측 결측) 배제하지 않는다 — fail-open 이 아니라
    '근거 없는 제외 금지' 원칙이다. 무엇을 근거 부족으로 넘겼는지는 표로 남긴다."""
    d = P.copy()
    eq = col(d, "equity")

    # ① 특수관계자 매입 또는 매출 비중 전분기 대비 상승 — 상승폭 상위 20%
    up_s = col(d, "related_sales_ratio") - col(d, "related_sales_ratio_prev")
    up_p = col(d, "related_purchase_ratio") - col(d, "related_purchase_ratio_prev")
    up = pd.concat([up_s, up_p], axis=1).max(axis=1, skipna=True)
    d["related_up"] = up
    thr = up.where(up > 0).groupby(d["rebal"], observed=True) \
            .transform(lambda s: s.quantile(1.0 - RELATED_PARTY_TOPQ))
    d["x_related_up"] = ((up > 0) & up.notna() & thr.notna() & (up >= thr)).astype(float)

    # ② 우발부채·지급보증 증가가 자기자본 대비 5%p 이상
    dc = col(d, "contingent_amt") - col(d, "contingent_amt_prev")
    d["contingent_pp"] = safe_div(dc, eq.where(eq > 0))
    d["x_contingent"] = (d["contingent_pp"] >= CONTINGENT_EQ_PP).fillna(False).astype(float)

    # ③ 신규 소송 제기 + 소송가액/자기자본 > 5%
    d["lawsuit_ratio"] = safe_div(col(d, "lawsuit_amt"), eq.where(eq > 0))
    new_suit = (col(d, "lawsuit_new").fillna(0) > 0) | (col(d, "lawsuit_filed").fillna(0) > 0)
    d["x_lawsuit"] = (new_suit & (d["lawsuit_ratio"] > LAWSUIT_EQ_2ND)).fillna(False).astype(float)

    # ④ 감사의견 특기사항 / 강조사항
    d["x_audit"] = (col(d, "audit_emphasis").fillna(0) > 0).astype(float)

    # ⑤ 최대주주 변경   ⑥ 전환사채·신주인수권부사채 발행
    d["x_holder_chg"] = (col(d, "major_holder_chg").fillna(0) > 0).astype(float)
    d["x_cbbw"] = ((col(d, "cb_issue").fillna(0) > 0) |
                   (col(d, "bw_issue").fillna(0) > 0)).astype(float)

    d["EXCLUDED"] = (d[EXCL_FLAGS].sum(axis=1) > 0).astype(int)

    evid = {
        "x_related_up": col(d, "related_sales_ratio").notna() | col(d, "related_purchase_ratio").notna(),
        "x_contingent": col(d, "contingent_amt").notna(),
        "x_lawsuit": col(d, "lawsuit_amt").notna() | col(d, "lawsuit_new").notna(),
        "x_audit": col(d, "audit_emphasis").notna(),
        "x_holder_chg": col(d, "major_holder_chg").notna(),
        "x_cbbw": col(d, "cb_issue").notna() | col(d, "bw_issue").notna(),
    }
    LOG.table([[EXCL_LABEL[f], f"{int(d[f].sum()):,}", f"{100*d[f].mean():.2f}%",
                f"{100*float(evid[f].mean()):.1f}%"] for f in EXCL_FLAGS],
              ["배제 플래그", "발동", "발동률", "근거 관측 보유율"], ["l", "r", "r", "r"],
              title="§6.1 배제 플래그 — 근거가 없으면 배제하지 않는다(근거 보유율을 함께 본다)")
    LOG.ok(f"배제 대상 {int(d['EXCLUDED'].sum()):,}행 / {len(d):,}행 ({100*d['EXCLUDED'].mean():.1f}%)")
    low = [EXCL_LABEL[f] for f in EXCL_FLAGS if float(evid[f].mean()) < 0.30]
    if low:
        LOG.warn("근거 관측 보유율이 30% 미만인 플래그: " + ", ".join(low) +
                 ". 해당 플래그는 사실상 일부 종목에만 작동하므로, 2층(지배구조 위험 배제) 효과가 "
                 "그만큼 약하게 측정됩니다. DART 본문 파싱률(§2.1)을 함께 보세요.")
    return d


def zscore_observed_then_neutral(P: pd.DataFrame, colname: str, mask: pd.Series) -> pd.Series:
    """관측치만으로 z 를 만든 뒤, 비관측치에 0(중립)을 채운다 (§6.2 결측 허용 설계).

    ★ 순서가 전부다. 0 을 먼저 채우고 z 를 만들면, 결측이 다수인 시점에서 평균이 0 으로
      끌려가 리포트를 가진 소수 종목의 z 가 통째로 부풀거나 눌린다. 즉 '리포트가 있다'는
      사실 자체가 신호가 되어 버린다 — 정확히 §6.2 가 막으려는 상황이다.
    """
    v = col(P, colname).where(mask)
    z = _cell_ladder_z(P, v)
    return z.fillna(0.0).astype("float32")


def apply_filter2(P: pd.DataFrame, variant: str, n: int = SECOND_N,
                  use_tone: bool = True, use_nonfin: bool = True,
                  use_exclusion: bool = True,
                  score_col: Optional[str] = None, score_raw: bool = False) -> pd.DataFrame:
    """U-200(변형별) → 상위 n 종목. 어블레이션(X2/X3)을 위해 구성요소를 켜고 끌 수 있다.

    score_col: TONE-MEASURE 어블레이션용 — 지정하면 그 컬럼이 Score2 를 통째로 대체한다.
               score_raw=False 면 관측치 z → 결측 0(§6.2 순서), True 면 원값 그대로(이미
               합성 z 인 score_f1/f2 용 — 두 번 z 하면 셀 사다리로 순서가 뒤틀린다).
    ★ 축 B 백본: TONE-MEASURE 결합층이 만든 dAXISB(B1+B2+B3 부호정렬 합성)가 있으면
      그것을, 없으면(스모크 등) 기존 dNONFIN 을 쓴다 — 명세 §5 의 'w_d × 축B점수' 구현.
    """
    d = P.copy()
    inu = col(d, f"u200_{variant}").fillna(0).astype(bool) if f"u200_{variant}" in d.columns \
        else pd.Series(True, index=d.index)

    if score_col is not None:
        if score_raw:
            d[f"score2_{variant}"] = pd.to_numeric(col(d, score_col), errors="coerce") \
                .fillna(0.0).astype("float32")
        else:
            d[f"score2_{variant}"] = zscore_observed_then_neutral(
                d, score_col, inu & col(d, score_col).notna())
    else:
        nonfin_src = "dAXISB" if "dAXISB" in d.columns else "dNONFIN"
        zN = pd.Series(0.0, index=d.index, dtype="float32")
        if use_nonfin:
            zN = zscore_observed_then_neutral(d, nonfin_src, inu & col(d, nonfin_src).notna())
        zT = pd.Series(0.0, index=d.index, dtype="float32")
        if use_tone:
            zT = zscore_observed_then_neutral(d, "dTONE_resid", inu & col(d, "dTONE_resid").notna())
        d[f"score2_{variant}"] = (SCORE2_W_NONFIN * zN + SCORE2_W_TONE * zT).astype("float32")
    excl = col(d, "EXCLUDED").fillna(0).astype(bool) if use_exclusion else \
        pd.Series(False, index=d.index)

    sel = pd.Series(False, index=d.index)
    for _t, g in d.groupby("rebal", observed=True):
        gg = g[inu.loc[g.index] & ~excl.loc[g.index]]
        if gg.empty:
            continue
        keys = [f"score2_{variant}", f"score1_{variant}", "code"]
        keys = [k for k in keys if k in gg.columns]
        asc = [False] * (len(keys) - 1) + [True]
        idx = gg.sort_values(keys, ascending=asc, kind="mergesort").head(min(n, len(gg))).index
        sel.loc[idx] = True
    d[f"f2_{variant}"] = sel
    return d


def verify_missing_tolerance(P: pd.DataFrame, variant: str) -> dict:
    """§6.2 결측 허용 설계가 실제로 지켜지는지 검증한다.
    리포트 없는 종목의 2차필터 통과율이 리포트 보유 종목과 비슷해야 정상이다."""
    d = P[P[f"u200_{variant}"].fillna(False).astype(bool)] if f"u200_{variant}" in P.columns else P
    if d.empty:
        return {}
    has_rep = pd.to_numeric(col(d, "n_reports"), errors="coerce").fillna(0) > 0
    passed = col(d, f"f2_{variant}").fillna(0).astype(bool)
    r_with = float(passed[has_rep].mean()) if int(has_rep.sum()) else float("nan")
    r_wo = float(passed[~has_rep].mean()) if int((~has_rep).sum()) else float("nan")
    LOG.table([["U-200 관측", f"{len(d):,}"],
               ["리포트 보유 종목", f"{int(has_rep.sum()):,} ({100*has_rep.mean():.1f}%)"],
               ["리포트 없는 종목", f"{int((~has_rep).sum()):,} ({100*(~has_rep).mean():.1f}%)"],
               ["2차필터 통과율 — 리포트 보유", f"{100*r_with:.1f}%" if np.isfinite(r_with) else "—"],
               ["2차필터 통과율 — 리포트 없음", f"{100*r_wo:.1f}%" if np.isfinite(r_wo) else "—"],
               ["최종 선정 중 리포트 없는 비중",
                f"{100*float((~has_rep)[passed].mean()):.1f}%" if int(passed.sum()) else "—"]],
              ["항목", "값"], ["l", "r"],
              title=f"[{variant}] §6.2 결측 허용 검증 — 리포트 없는 종목이 실제로 살아남는가")
    if np.isfinite(r_wo) and np.isfinite(r_with) and r_wo < r_with * 0.5:
        LOG.warn("리포트 없는 종목의 통과율이 보유 종목의 절반 미만입니다. ΔTONE_resid 가 "
                 "중립(0)이 아니라 사실상 벌점으로 작동하고 있을 수 있습니다 — "
                 "zscore_observed_then_neutral 의 순서(관측치 z 먼저, 결측 0 은 나중)를 확인하세요.")
        PIPE.note("WARN: 결측 허용 설계 위반 의심")
    else:
        LOG.ok("리포트 없는 종목이 정상적으로 살아남고 있습니다 — U-200 확장 효과가 보존됩니다.")
    return {"pass_with_report": r_with, "pass_without_report": r_wo}


# ── 3차 필터 3-A (§7.2) ─────────────────────────────────────────────────────────────────────
RULE_FLAGS = ["r_lawsuit", "r_related", "r_holder", "r_audit", "r_oploss", "r_impair"]
RULE_LABEL = {
    "r_lawsuit": f"소송가액/자기자본 > {RULE_LAWSUIT_EQ:.0%}",
    "r_related": f"특수관계자 매출비중 > {RULE_RELATED_SALES:.0%}",
    "r_holder":  f"최대주주 지분율 < {RULE_MAJOR_HOLDER:.0%}",
    "r_audit":   "감사보고서 강조사항 존재",
    "r_oploss":  f"{RULE_OP_LOSS_QUARTERS}개 분기 연속 영업적자",
    "r_impair":  f"자본잠식률 > {RULE_IMPAIRMENT:.0%}",
}


def apply_filter3a(P: pd.DataFrame) -> pd.DataFrame:
    """명문화된 체크리스트만 사용한다. 임계값은 사전등록 후 고정이며 튜닝하지 않는다.
    ★ 근거가 결측이면 제외하지 않는다(모른다는 이유로 버리면 그게 곧 선택편향)."""
    d = P.copy()
    eq = col(d, "equity")
    cap_stock = col(d, "capital_stock")

    d["r_lawsuit"] = (col(d, "lawsuit_ratio") > RULE_LAWSUIT_EQ).fillna(False).astype(float)
    d["r_related"] = (col(d, "related_sales_ratio") > RULE_RELATED_SALES).fillna(False).astype(float)
    d["r_holder"] = ((col(d, "major_holder_pct").notna()) &
                     (col(d, "major_holder_pct") < RULE_MAJOR_HOLDER)).astype(float)
    d["r_audit"] = (col(d, "audit_emphasis").fillna(0) > 0).astype(float)
    d["r_oploss"] = (col(d, "op_loss_4q").fillna(0) > 0).astype(float)
    # 자본잠식률 = (자본금 − 자기자본) / 자본금
    d["impair_ratio"] = safe_div(cap_stock - eq, cap_stock.where(cap_stock > 0))
    d["r_impair"] = (d["impair_ratio"] > RULE_IMPAIRMENT).fillna(False).astype(float)

    d["RULE3A_BLOCK"] = (d[RULE_FLAGS].sum(axis=1) > 0).astype(int)
    evid = {
        "r_lawsuit": col(d, "lawsuit_ratio").notna(),
        "r_related": col(d, "related_sales_ratio").notna(),
        "r_holder": col(d, "major_holder_pct").notna(),
        "r_audit": col(d, "audit_emphasis").notna(),
        "r_oploss": col(d, "op_loss_4q").notna(),
        "r_impair": d["impair_ratio"].notna(),
    }
    LOG.table([[RULE_LABEL[f], f"{int(d[f].sum()):,}", f"{100*d[f].mean():.2f}%",
                f"{100*float(evid[f].mean()):.1f}%"] for f in RULE_FLAGS],
              ["3-A 규칙", "발동", "발동률", "근거 관측 보유율"], ["l", "r", "r", "r"],
              title="3-A 규칙판 (§7.2) — 백테스트는 여기까지만 포함한다(3-B 재량은 소급 금지)")
    LOG.ok(f"3-A 차단 {int(d['RULE3A_BLOCK'].sum()):,}행 ({100*d['RULE3A_BLOCK'].mean():.1f}%)")
    return d


def build_final_selection(P: pd.DataFrame, variant: str, n_final: int = FINAL_N,
                          use_rule3a: bool = True, stage: str = "full") -> pd.Series:
    """최종 편입 종목 플래그.

    stage: "full"(1→2→3A) | "x1"(1차만) | "x4"(1→2, 3A 없음)
    """
    d = P
    if stage == "x1":
        pool = col(d, f"u200_{variant}").fillna(0).astype(bool)
        rank_col = f"score1_{variant}"
    else:
        pool = col(d, f"f2_{variant}").fillna(0).astype(bool)
        rank_col = f"score2_{variant}"
    # ★ X1 은 §8.2 정의상 "1차만 (2차·3차 없음)" 이다. 여기에 3-A 를 적용하면 X1 이 사실은
    #   '1차 + 3차' 가 되고, §10.4 의 폐기조건 ②(깔때기 기여)와 ③(배제가 MDD 를 개선하는가)이
    #   둘 다 잘못된 기준선과 비교하게 된다. 특히 ③은 X1 에 이미 배제가 들어가 있으므로
    #   '배제의 기여가 없다'는 결론을 구조적으로 유도한다 — 2층 논리를 부당하게 반증한다.
    if use_rule3a and stage != "x1":
        pool = pool & (col(d, "RULE3A_BLOCK").fillna(0) == 0)

    sel = pd.Series(False, index=d.index)
    short_q: List[Tuple[Any, int]] = []
    for _t, g in d.groupby("rebal", observed=True):
        gg = g[pool.loc[g.index]]
        if gg.empty:
            short_q.append((_t, 0))
            continue
        keys = [c for c in (rank_col, f"score1_{variant}", "code") if c in gg.columns]
        asc = [False] * (len(keys) - 1) + [True]
        k = int(min(max(FINAL_N_MIN, min(n_final, FINAL_N_MAX)), len(gg)))
        # ★ §7.4 는 보유 20~40 종목을 규정한다. 풀이 20 미만이면 그 분기는 규정 미달이며,
        #   조용히 진행하면 '집중 포트폴리오의 우연한 성과'가 규정 준수로 보고된다.
        #   여기서 종목을 억지로 채우면(제외 규칙을 되돌려서) 그게 더 큰 위반이므로,
        #   미달 자체는 허용하되 분기와 종목수를 반드시 표면화한다.
        if k < FINAL_N_MIN:
            short_q.append((_t, k))
        sel.loc[gg.sort_values(keys, ascending=asc, kind="mergesort").head(k).index] = True
    if short_q:
        LOG.warn(f"§7.4 보유 하한({FINAL_N_MIN}종목) 미달 분기 {len(short_q)}회 "
                 f"[{stage}/{variant}] — " +
                 ", ".join(f"{as_ts(t):%Y-%m}:{n}종목" for t, n in short_q[:8]) +
                 (" …" if len(short_q) > 8 else "") +
                 ". 규칙을 되돌려 억지로 채우지 않았습니다. 해당 분기의 성과는 "
                 "'규정 범위 밖의 집중 포트폴리오' 로 해석해야 합니다.")
    return sel
