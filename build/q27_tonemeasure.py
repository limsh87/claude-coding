

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-TM  TONE-MEASURE v1.0 — 애널리스트 톤(축 A) · DART 텍스트(축 B) 측정 형태 확정 명세    ║
# ║                                                                                          ║
# ║  이 모듈은 TONE-MEASURE v1.0 실행 명령서의 구현이며, QVF-FUNNEL §6.2 의 ΔTONE_resid       ║
# ║  '정의'를 대체한다. 유니버스(U-1000→U-200)·1차 필터·3차 필터는 건드리지 않는다(명세 §0).   ║
# ║                                                                                          ║
# ║  핵심 설계(명세 §1) — 두 소스를 비대칭으로 다룬다. 대칭으로 되돌리지 말 것:                 ║
# ║    축 A(애널리스트): 알파 원천 = 서프라이즈 → 자기참조 1차 차분(T2, broker 단위) · 부호 +   ║
# ║    축 B(DART):      알파 원천 = 비정상 수준 → 자기이력 표준화 + 펀더멘털 잔차 · 부호 −      ║
# ║  부호는 사전등록이다. 데이터에서 역전되면 뒤집지 말고 '검증 실패'로 보고한다(§1.2, §7[7]).  ║
# ║                                                                                          ║
# ║  수집 범위(사용자 계약): 애널리스트 상세·PDF 도, DART 본문도 U-200 합집합만.               ║
# ║  전 종목 수집은 필요도 이유도 없다 — 소비처가 U-200 이기 때문이다.                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 사전등록 상수 (명세 §3·§4·§5 — 튜닝 금지) ───────────────────────────────────────────────
TM_GATE_A1_MIN = 0.30          # U-200 분기당 리포트≥1건 종목 비율
TM_GATE_A2_MIN = 0.90          # broker_id 추출 성공률
TM_GATE_A4_MIN = 0.20          # 동일 broker 연속 2건 (종목,분기) 비율 — T2 성립 요건
TM_GATE_A6_MIN = 0.30          # U-200 내 축 A 유효 관측 비율(분기 중앙값)
TM_DELTA_MAX_GAP_DAYS = 400    # §3.5[3] 직전 리포트 간격 상한 (커버리지 중단≠견해 변화)
TM_B2_MIN_HISTORY = 4          # §4.3[2] 자기이력 최소 동일유형 보고서 수
TM_B2_DEMOTE_COV = 0.50        # §4.3 U-200 내 B2 유효 비율 미달 시 보조 지표 강등
TM_INTERACT_TOP = 0.30         # §5.2 상호작용 상위 퍼센타일
TM_CORR_HALT = 0.50            # §5.3 축 간 상관 |ρ| 초과 시 중단 보고
TM_SECT_TRUNC = 30000          # 섹션 텍스트 저장 상한(문자)

TM_STATE: Dict[str, Any] = {"axisA_on": None, "b2_demoted": None, "tier": "T2",
                            "gates": {}, "halt_corr": None}


# ════════════════════════════════════════════════════════════════════════════════════════════
#  축 A — §3.3 리포트 유형 분류 (규칙 기반 · LLM 금지)
# ════════════════════════════════════════════════════════════════════════════════════════════
_RT_RULES = [
    ("EARNINGS_REVIEW", re.compile(r"실적|리뷰|review|잠정|영업이익|어닝|분기\s*(?:실적|리뷰)|"
                                   r"[1-4]Q\s*(?:리뷰|실적|Re)|컨퍼런스", re.I)),
    ("OUTLOOK", re.compile(r"전망|아웃룩|outlook|프리뷰|preview|년\s*전망|내년|하반기|상반기\s*전망", re.I)),
    ("INITIATION", re.compile(r"커버리지\s*(?:개시|신규)|개시|initiation|신규\s*편입|첫", re.I)),
    ("VISIT_NOTE", re.compile(r"탐방|방문|미팅|NDR|기업\s*노트|현장", re.I)),
    ("EVENT", re.compile(r"수주|계약|인수|합병|증자|유상|무상|공시|특허|승인|허가|출시|임상", re.I)),
]


def tm_report_type(rep: pd.DataFrame) -> pd.Series:
    """리포트 유형. 제목 키워드 + 발간 시점(1·12월 → OUTLOOK 가점) + 커버리지 이력.

    INITIATION 판정(명세 §3.3): 해당 broker 가 해당 종목에 과거 24개월 리포트 이력이 없으면
    이니시에이션. 데이터 시작 24개월 이내는 판정 불가 → UNKNOWN.
    """
    if rep is None or rep.empty:
        return pd.Series(dtype=object)
    R = rep[["report_uid", "stock_code", "broker_id", "pub_date"]].copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    title = rep.get("title", pd.Series([""] * len(rep))).astype(str)

    out = pd.Series("OTHER", index=rep.index, dtype=object)
    for name, rx in _RT_RULES:
        hit = title.str.contains(rx) & (out == "OTHER")
        out.loc[hit] = name

    # 커버리지 이력 기반 INITIATION — 제목 규칙과 무관하게 이력이 최우선 증거다
    R = R.sort_values("pub_date", kind="stable")
    prev = R.groupby(["stock_code", "broker_id"], observed=True)["pub_date"].shift(1)
    gap = (R["pub_date"] - prev).dt.days
    data_start = R["pub_date"].min()
    with np.errstate(all="ignore"):
        is_init = prev.isna() | (gap > 730)
        undecidable = R["pub_date"] < (data_start + pd.DateOffset(months=24))
    init_idx = R.index[is_init & ~undecidable]
    unk_idx = R.index[is_init & undecidable]
    out.loc[out.index.intersection(init_idx)] = "INITIATION"
    out.loc[out.index.intersection(unk_idx)] = "UNKNOWN"

    dist = out.value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/len(out):.1f}%"] for k, v in dist.items()],
              ["report_type", "건수", "비중"], ["l", "r", "r"],
              title="리포트 유형 분포 (TONE-MEASURE §3.3 — 규칙 기반 · 유형은 톤의 구조적 결정요인)")
    other_pct = float((out == "OTHER").mean())
    if other_pct > 0.30:
        LOG.warn(f"OTHER 비중 {100*other_pct:.1f}% > 30% (명세 §3.3). 분류 규칙 보완이 필요합니다 — "
                 f"미분류 유형 계절성이 ΔTONE 에 남습니다. 진행하되 이 사실을 보고서에 남깁니다.")
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
#  축 A — §3.1 Phase 0 게이트 A1~A5 (실측 — 추정치로 진행 금지)
# ════════════════════════════════════════════════════════════════════════════════════════════
def tm_gates_axisA(S: pd.DataFrame, P: pd.DataFrame, cal: pd.DataFrame) -> dict:
    """게이트 실측. A3/A5 는 기준 없음(측정만)이되 반드시 '증권사별 분해'로 보고한다(§3.1).

    S: 리포트 단위 톤 테이블(report_uid·stock_code·broker_id·analyst_id·pub_date)
    P: U-200 플래그가 붙은 패널
    """
    g: Dict[str, Any] = {}
    u200 = pd.Series(False, index=P.index)
    for v in VARIANTS:
        if f"u200_{v}" in P.columns:
            u200 |= P[f"u200_{v}"].fillna(False).astype(bool)
    pu = P[u200][["code", "rebal"]].drop_duplicates()

    if S is None or S.empty or pu.empty:
        g.update({"A1": 0.0, "A2": 0.0, "A3": float("nan"), "A4": 0.0, "A5": float("nan")})
    else:
        R = S.copy()
        R["pub_date"] = as_ts_series(R["pub_date"])
        R = R.dropna(subset=["stock_code", "pub_date"])
        # 분기 배정: 발간일 → 그 발간을 소비하는 리밸 분기 (발간 ≤ 그 분기 signal_date).
        # pd.cut 은 datetime 경계에서 단위(us/ns) 혼합에 취약하므로 searchsorted 로 배정한다.
        reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
        sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
        edges = np.array([np.datetime64(as_ts(sig.get(as_ts(t)))) for t in reb],
                         dtype="datetime64[ns]")
        idx = np.searchsorted(edges, R["pub_date"].to_numpy(dtype="datetime64[ns]"), side="left")
        R["_q"] = [str(as_ts(reb[i])) if i < len(reb) else None for i in idx]
        R = R.dropna(subset=["_q"])

        # A1: U-200 내 분기당 리포트 ≥1건 종목 비율
        have = set(zip(R["stock_code"].astype(str), R["_q"].astype(str)))
        pu2 = pu.copy()
        pu2["_hit"] = [(str(c), str(as_ts(t))) in have for c, t in zip(pu2["code"], pu2["rebal"])]
        g["A1"] = float(pu2["_hit"].mean()) if len(pu2) else 0.0

        # A2: broker_id 추출 성공률
        bid = S.get("broker_id", pd.Series([""] * len(S))).astype(str)
        g["A2"] = float((bid.str.len() > 0).mean())

        # A3: analyst_id 추출 성공률 (물량가중 = 리포트 건수 가중) — 측정만
        aid = S.get("analyst_id", pd.Series([""] * len(S))).astype(str)
        g["A3"] = float(((aid.str.len() > 0) & (aid != "nan")).mean())

        # A4/A5: 동일 주체가 동일 종목에 연속 2건 이상 발간한 (종목,분기) 비율
        def _consec(keycols):
            RR = R.dropna(subset=keycols).sort_values("pub_date", kind="stable")
            prev = RR.groupby(keycols, observed=True)["pub_date"].shift(1)
            ok_pair = prev.notna() & ((RR["pub_date"] - prev).dt.days <= TM_DELTA_MAX_GAP_DAYS)
            hit = set(zip(RR.loc[ok_pair, "stock_code"].astype(str),
                          RR.loc[ok_pair, "_q"].astype(str)))
            return float(np.mean([(str(c), str(as_ts(t))) in hit
                                  for c, t in zip(pu["code"], pu["rebal"])])) if len(pu) else 0.0
        g["A4"] = _consec(["stock_code", "broker_id"])
        S2 = R[aid.reindex(R.index).astype(str).str.len() > 0]
        g["A5"] = _consec(["stock_code", "analyst_id"]) if "analyst_id" in R.columns and len(S2) \
            else float("nan")

        # 증권사별 분해 (명세: 전체 평균만 보고 금지)
        if "broker_id" in S.columns:
            bb = S.assign(_has_aid=((aid.str.len() > 0) & (aid != "nan")).astype(float)) \
                  .groupby(S["broker_id"].astype(str), observed=True) \
                  .agg(n=("report_uid", "count"), aid_rate=("_has_aid", "mean"))
            bb = bb.sort_values("n", ascending=False).head(15)
            LOG.table([[i or "(미상)", f"{int(r.n):,}", f"{100*r.aid_rate:.0f}%"]
                       for i, r in bb.iterrows()],
                      ["broker_id", "리포트", "analyst_id 추출률"], ["l", "r", "r"],
                      title="GATE_A3/A5 증권사별 분해 (§3.1 — 추출률이 이진적으로 갈리면 T1 은 표본편향)")

    rows = [["GATE_A1", "U-200 분기당 리포트≥1건 종목 비율", f"{100*g['A1']:.1f}%",
             f"≥ {100*TM_GATE_A1_MIN:.0f}%", "✔" if g["A1"] >= TM_GATE_A1_MIN else "✘"],
            ["GATE_A2", "broker_id 추출 성공률", f"{100*g['A2']:.1f}%",
             f"≥ {100*TM_GATE_A2_MIN:.0f}%", "✔" if g["A2"] >= TM_GATE_A2_MIN else "✘"],
            ["GATE_A3", "analyst_id 추출 성공률 (측정만)",
             "—" if not np.isfinite(g.get("A3", float("nan"))) else f"{100*g['A3']:.1f}%", "—", "—"],
            ["GATE_A4", "동일 broker 연속 2건 (종목,분기) 비율", f"{100*g['A4']:.1f}%",
             f"≥ {100*TM_GATE_A4_MIN:.0f}%", "✔" if g["A4"] >= TM_GATE_A4_MIN else "✘"],
            ["GATE_A5", "동일 analyst@broker 연속 2건 비율 (측정만)",
             "—" if not np.isfinite(g.get("A5", float("nan"))) else f"{100*g['A5']:.1f}%", "—", "—"]]
    LOG.table(rows, ["게이트", "측정 대상", "실측", "기준", "판정"], ["l", "l", "r", "r", "c"],
              title="TONE-MEASURE Phase 0 게이트 (§3.1) — Tier 는 데이터 가용성에 종속된다")

    axisA_on = (g["A1"] >= TM_GATE_A1_MIN) and (g["A2"] >= TM_GATE_A2_MIN)
    tier = "T2"
    if axisA_on and g["A4"] < TM_GATE_A4_MIN:
        tier = "T3"
        LOG.warn("GATE_A4 실패 — T2(broker 자기참조) 성립 불가. T3(종목단위)로 폴백합니다. "
                 "이 사실은 보고서 1페이지 기재 대상입니다(§3.1).")
    if not axisA_on:
        LOG.warn("GATE_A1/A2 실패 — 축 A 를 전면 비활성화합니다(§3.1 판정 로직). "
                 "2차 필터는 축 B 단독으로 실행되며, ΔTONE_resid 는 전부 중립(0)이 됩니다.")
    TM_STATE["gates"].update(g)
    TM_STATE["axisA_on"] = bool(axisA_on)
    TM_STATE["tier"] = tier
    return g


# ════════════════════════════════════════════════════════════════════════════════════════════
#  축 A — §3.5 T2 자기참조 차분 → 분기 집계 (사전등록 형태)
# ════════════════════════════════════════════════════════════════════════════════════════════
def tm_t2_delta(S: pd.DataFrame, G: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """broker×종목 자기참조 1차 차분 → 분기 단순평균. §3.5 를 문언대로 구현한다.

      · ΔX(f,b,r) = X(f,b,r) − X(f,b,직전 r)  (X ∈ {POS, NEG, TONE})
      · 직전 리포트 부재 또는 간격 > 400일 → 결측 (0 으로 채우지 않는다)
      · 분기 집계 = 단순평균 (역변동성·최신성 가중 금지 — broker 1~2개에 가중은 자유도 낭비)
      · n_b(f,q) = 분기 내 유효 broker 수 기록

    T4(절대톤 횡단면 z)와 T3 는 어블레이션 대조군으로만 산출한다(주 결과 승격 금지).
    """
    base = G[["code", "rebal", "signal_date"]].drop_duplicates()
    out_cols = ["code", "rebal", "dPOS_t2", "dNEG_t2", "dTONE_t2", "n_b", "tone_abs_q"]
    if S is None or S.empty:
        for c in out_cols[2:]:
            base[c] = np.nan
        base["n_b"] = 0.0
        return base.rename(columns={})
    R = S.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["stock_code", "pub_date", "tone"])
    for c in ("pos_frac", "neg_frac"):
        if c not in R.columns:
            R[c] = np.nan
    R["broker_id"] = R.get("broker_id", pd.Series([""] * len(R))).astype(str)
    R = R.sort_values("pub_date", kind="stable")

    # 자기참조 차분 — 동일 (종목, broker) 의 직전 리포트 대비
    gb = R.groupby(["stock_code", "broker_id"], observed=True)
    prev_d = gb["pub_date"].shift(1)
    gap_ok = (R["pub_date"] - prev_d).dt.days <= TM_DELTA_MAX_GAP_DAYS
    for x, dx in (("tone", "dTONE"), ("pos_frac", "dPOS"), ("neg_frac", "dNEG")):
        R[dx] = (R[x] - gb[x].shift(1)).where(gap_ok)

    # 분기 배정: 사용가능일(발간+1거래일)이 속하는 소비 창 (직전 signal, 이번 signal]
    R["usable"] = next_trading_day_series(R["pub_date"])
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = R[(R["usable"] > lo) & (R["usable"] <= hi)]
        if w.empty:
            continue
        a = (w.groupby("stock_code", observed=True)
              .agg(dTONE_t2=("dTONE", "mean"), dPOS_t2=("dPOS", "mean"),
                   dNEG_t2=("dNEG", "mean"), tone_abs_q=("tone", "mean"),
                   n_b=("broker_id", lambda s: s[w.loc[s.index, "dTONE"].notna()].nunique()))
              .reset_index().rename(columns={"stock_code": "code"}))
        a["rebal"] = as_ts(t)
        parts.append(a)
    if not parts:
        for c in out_cols[2:]:
            base[c] = np.nan
        base["n_b"] = 0.0
        return base
    A = pd.concat(parts, ignore_index=True)
    out = base.merge(A, on=["code", "rebal"], how="left")
    out["n_b"] = pd.to_numeric(out["n_b"], errors="coerce").fillna(0.0)
    nb = out.loc[out["dTONE_t2"].notna(), "n_b"]
    LOG.table([["ΔTONE(T2) 관측", f"{int(out['dTONE_t2'].notna().sum()):,}행 "
                f"({100*out['dTONE_t2'].notna().mean():.1f}%)"],
               ["유효 broker 수 분포", (f"중앙값 {nb.median():.0f} · 최대 {nb.max():.0f}"
                                        if len(nb) else "—")],
               ["ΔPOS/ΔNEG 관측", f"{int(out['dPOS_t2'].notna().sum()):,} / "
                f"{int(out['dNEG_t2'].notna().sum()):,}행"]],
              ["항목", "값"], ["l", "r"],
              title="축 A — T2 자기참조 차분 (§3.5 · 직전 리포트 부재/400일 초과는 결측)")
    return out


def tm_orthogonalize(P: pd.DataFrame, ycol: str, outcol: str,
                     type_shares: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """§3.6 직교화 — 분기별 횡단면 회귀 잔차 (전 기간 풀링 금지 = 룩어헤드 금지).

    설명변수: 목표주가 수정률 · 12-1 모멘텀 · log(시총) · log(ADTV) · n_b ·
              report_type 비중 · 섹터 더미.
    EPS 컨센서스 수정률·투자의견 변경은 과거 시계열 복원 불가 → 제외(§10.1 한계 기재).
    """
    d = P.copy()
    d[outcol] = np.nan
    if ycol not in d.columns or d[ycol].notna().sum() < 30:
        return d
    if "log_cap" not in d.columns:
        d["log_cap"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").where(lambda s: s > 0))
    if "log_adtv" not in d.columns:
        d["log_adtv"] = np.log(pd.to_numeric(d.get("adtv"), errors="coerce").where(lambda s: s > 0))
    feats = [c for c in ("tp_revision", "mom12_1", "log_cap", "log_adtv", "n_b") if c in d.columns]
    tcols = [c for c in d.columns if c.startswith("rt_share_")]

    resid = pd.Series(np.nan, index=d.index, dtype="float64")
    n_fit = 0
    for t, g in d.groupby("rebal", observed=True):
        m = g[ycol].notna()
        if int(m.sum()) < 20:
            continue
        gg = g[m]
        y = pd.to_numeric(gg[ycol], errors="coerce").to_numpy(dtype="float64")
        Xp = [np.ones((len(gg), 1))]
        for c in feats + tcols:
            v = pd.to_numeric(gg[c], errors="coerce")
            v = v.fillna(v.median() if v.notna().any() else 0.0)
            if v.std(ddof=0) > 0:
                Xp.append(((v - v.mean()) / v.std(ddof=0)).to_numpy().reshape(-1, 1))
        sec_s = gg["sector"].astype(str)
        big = sec_s.value_counts()
        for s in big[big >= 20].index.tolist()[:40][1:]:
            Xp.append((sec_s == s).to_numpy(dtype="float64").reshape(-1, 1))
        X = np.hstack(Xp)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if ok.sum() < max(20, X.shape[1] + 5):
            continue
        try:
            beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
            resid.loc[gg.index[ok]] = (y - X @ beta)[ok]
        except Exception:
            continue
        n_fit += 1
    d[outcol] = resid.astype("float32")
    LOG.ok(f"직교화 {ycol} → {outcol}: 횡단면 {n_fit}개 시점 · "
           f"잔차 {int(d[outcol].notna().sum()):,}행 "
           f"(설명변수: {', '.join(feats)} + report_type 비중 {len(tcols)}개 + 섹터더미 · "
           f"EPS 컨센서스는 복원 불가로 제외)")
    return d


# ════════════════════════════════════════════════════════════════════════════════════════════
#  축 B — §4.2 B1 텍스트 정규화 6단계 · 유사도 4종 (Lazy Prices)
# ════════════════════════════════════════════════════════════════════════════════════════════
TM_BOILER_DART = [
    r"본\s*보고서[^.。\n]{0,120}[.。]?", r"기재\s*하지\s*아니\s*합니다",
    r"해당\s*사항\s*없음", r"공시\s*대상\s*기간", r"작성\s*기준일",
    r"금융위원회\s*귀중", r"한국거래소\s*귀중",
]
_TM_BOILER_RE = re.compile("|".join(TM_BOILER_DART))
_TM_TABLECHR_RE = re.compile(r"[│─┼┤├┬┴╋┏┓┗┛==＝\-]{2,}|[\|]{1,}")
_TM_PAGENO_RE = re.compile(r"-\s*\d{1,4}\s*-|\b\d{1,4}\s*(?:페이지|page|쪽)\b", re.I)
_TM_FOOTNOTE_RE = re.compile(r"주\s*\d{1,2}\s*[)\]]")
_TM_EXEC_RE = re.compile(r"(?:대표이사|사내이사|사외이사|감사|이사|부회장|회장|사장|부사장|전무|상무)"
                         r"\s+[가-힣]{2,4}(?=[\s,.(]|$)")
_TM_ORG_RE = re.compile(r"(?:주식회사|㈜)\s*[가-힣A-Za-z0-9&]{2,20}|[가-힣A-Za-z0-9&]{2,20}\s*(?:주식회사|㈜)")
_TM_ADDR_RE = re.compile(r"[가-힣]{2,8}(?:특별시|광역시|도)\s[^\s]{1,12}(?:시|군|구)[^\n,]{0,40}")


def tm_normalize_text(text: str) -> str:
    """B1 정규화 6단계 (§4.2.2 — 순서대로). 숫자 마스킹이 빠지면 금액이 매년 바뀌는 것만으로
    전 종목이 100% '변경 기업'이 된다 — 이 함수가 B1 의 성립 조건이다."""
    if not text:
        return ""
    t = text
    t = re.sub(r"\d[\d,]*(?:\.\d+)?\s*%?", " <NUM> ", t)                       # [1] 숫자·금액·비율
    t = re.sub(r"<NUM>\s*[년.\-/]\s*<NUM>\s*[월.\-/]?\s*(?:<NUM>\s*일?)?", " <DATE> ", t)  # [2] 날짜
    t = _TM_EXEC_RE.sub(" <NAME> ", t)                                          # [3] 고유명사
    t = _TM_ORG_RE.sub(" <ORG> ", t)
    t = _TM_ADDR_RE.sub(" <ADDR> ", t)
    t = _TM_TABLECHR_RE.sub(" ", t)                                             # [4] 문서 구조
    t = _TM_PAGENO_RE.sub(" ", t)
    t = _TM_FOOTNOTE_RE.sub(" ", t)
    t = _TM_BOILER_RE.sub(" ", t)                                               # [5] 법정 정형문구
    t = unicodedata.normalize("NFKC", t)                                        # [6] 전각/반각·공백
    return re.sub(r"\s+", " ", t).strip()


def _tm_tokens(t: str) -> List[str]:
    return re.findall(r"[가-힣A-Za-z<>]{2,}", t)


def tm_similarity(a: str, b: str) -> dict:
    """유사도 4종 (§4.2.3): cosine(TF) · Jaccard · 편집거리 기반 · 문서길이 변화율."""
    ta, tb = _tm_tokens(a), _tm_tokens(b)
    if not ta or not tb:
        return {"cos": np.nan, "jac": np.nan, "edit": np.nan, "lenr": np.nan, "change": np.nan}
    ca, cb = Counter(ta), Counter(tb)
    num = sum(ca[k] * cb.get(k, 0) for k in ca)
    den = math.sqrt(sum(v * v for v in ca.values())) * math.sqrt(sum(v * v for v in cb.values()))
    cos = num / den if den > 0 else 0.0
    sa, sb = set(ca), set(cb)
    jac = len(sa & sb) / max(len(sa | sb), 1)
    import difflib as _dl
    edit = _dl.SequenceMatcher(None, " ".join(ta[:3000]), " ".join(tb[:3000])).ratio()
    lenr = 1.0 - abs(len(ta) - len(tb)) / max(len(ta), len(tb), 1)
    sim = float(np.mean([cos, jac, edit, lenr]))
    return {"cos": cos, "jac": jac, "edit": edit, "lenr": lenr, "change": 1.0 - sim}


def fetch_dart_section_texts(targets: pd.DataFrame) -> pd.DataFrame:
    """U-200 합집합 × 사업보고서의 섹션 텍스트(S1 사업의 내용 · S2 경영진단(MD&A) · S3 위험/기타).

    ★ 수집 범위는 targets(U-200 합집합)뿐이다 — 전 종목 본문은 필요도 이유도 없다.
    ★ 전년 동기 페어링(§4.2.1)을 위해 '사업보고서 ↔ 전년 사업보고서'만 쓴다. 분기보고서와
      섞으면 법정 기재사항 차이만으로 가짜 변화가 폭발한다.
    """
    cols = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "sect_status",
            "s1_text", "s2_text", "s3_text"]
    if targets is None or targets.empty or not DART_API_KEY:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_section_text", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(cached["rcept_no"].astype(str))
        LOG.info(f"캐시에서 DART 섹션 텍스트 {len(cached):,}건 재사용")
    todo = targets[~targets["rcept_no"].astype(str).isin(done)].copy()
    if RUN_MODE == "CACHED":
        todo = todo.iloc[0:0]

    rows: List[dict] = []
    if len(todo):
        LOG.info(f"DART 섹션 텍스트 신규 추출 {len(todo):,}건 (B1/B2 입력 · U-200 합집합만) — "
                 f"남은 호출: {DQUOTA.remaining_str() if DQUOTA else '?'}")
        breaker = {"fail": 0}

        def _one(rec):
            corp, yr, rno, rdt = rec
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                return None
            if DQUOTA is not None and not DQUOTA.take(1):
                return None
            raw = http_get("https://opendart.fss.or.kr/api/" + DOC_API, source="dart",
                           params={"crtfc_key": DART_API_KEY, "rcept_no": str(rno)},
                           as_bytes=True, tries=2, referer="https://opendart.fss.or.kr/")
            base = {"corp_code": corp, "bsns_year": yr, "rcept_no": rno, "rcept_dt": rdt}
            if not raw:
                breaker["fail"] += 1
                base["sect_status"] = "api_empty"
                return base
            breaker["fail"] = 0
            text, status = _xml_to_text(raw)
            del raw
            base["sect_status"] = status
            if status != "ok":
                return base
            base["s1_text"] = _section(text, "business", span=TM_SECT_TRUNC)[:TM_SECT_TRUNC] \
                if "business" in _SECTION_RE else ""
            base["s2_text"] = _section(text, "mdna", span=TM_SECT_TRUNC)[:TM_SECT_TRUNC] \
                if "mdna" in _SECTION_RE else ""
            base["s3_text"] = _section(text, "risk", span=TM_SECT_TRUNC)[:TM_SECT_TRUNC] \
                if "risk" in _SECTION_RE else ""
            if not (base["s1_text"] or base["s2_text"]):
                # 전용 앵커가 없으면 문서 앞부분을 S1 대용으로 저장(없는 것보다 낫고, 정규화가
                # 정형부를 걷어낸다). 대용 사실은 상태로 남긴다.
                base["s1_text"] = text[:TM_SECT_TRUNC]
                base["sect_status"] = "ok_fallback_head"
            del text
            return base

        jobs = list(zip(todo["corp_code"].astype(str), todo["bsns_year"].astype(int),
                        todo["rcept_no"].astype(str), todo["rcept_dt"]))
        CHUNK = 300
        for k0 in range(0, len(jobs), CHUNK):
            res = pmap_io(_one, jobs[k0:k0 + CHUNK], workers=min(N_WORKERS_IO, 6),
                          desc=f"DART 섹션 {k0//CHUNK+1}/{(len(jobs)-1)//CHUNK+1}")
            rows.extend([r for r in res if r])
            del res
            gc.collect()
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS or (DQUOTA is not None and DQUOTA.exhausted):
                LOG.warn("섹션 텍스트 수집 중단(서킷/한도) — 받은 만큼 저장하고 이어받습니다.")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    T = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    for c in cols:
        if c not in T.columns:
            T[c] = np.nan
    if rows:
        VAULT.put_table("dart_section_text", T[cols], scope="shared", domain="dart",
                        source="opendart document.xml → S1/S2/S3")
    ok_n = int((T["sect_status"].astype(str).str.startswith("ok")).sum())
    LOG.ok(f"DART 섹션 텍스트 {len(T):,}건 (판독 성공 {ok_n:,} · "
           f"{100*ok_n/max(len(T),1):.0f}%) — B1 변화량·B2 비정상 톤 입력")
    return T[cols]


def build_b1_change(sect: pd.DataFrame, sec: pd.DataFrame, G: pd.DataFrame) -> pd.DataFrame:
    """B1 — 전년 동기(사업보고서↔전년 사업보고서) 텍스트 변화량. CHANGE = 1 − similarity.

    부호는 사전등록 'CHANGE_z ↑ → 사후수익률 −'(§4.2.5)이며 결합층에서 −방향으로 정렬된다.
    횡단면 z 는 패널 결합 후 (섹터×리밸) 셀에서 산출한다(§4.2.4 — 서식 개정 공통충격 흡수).
    """
    out_cols = ["corp_code", "knowledge_date", "b1_change", "b1_cos", "b1_jac", "b1_edit", "b1_lenr"]
    if sect is None or sect.empty:
        return pd.DataFrame(columns=out_cols)
    S = sect[sect["sect_status"].astype(str).str.startswith("ok")].copy()
    if S.empty:
        return pd.DataFrame(columns=out_cols)
    S["bsns_year"] = pd.to_numeric(S["bsns_year"], errors="coerce")
    S = S.dropna(subset=["corp_code", "bsns_year"]).sort_values(["corp_code", "bsns_year"],
                                                                kind="stable")
    # 정규화(6단계)를 섹션별로 적용한 뒤, 전년 동기와 섹션별 유사도 → 평균 CHANGE
    rows = []
    for corp, g in S.groupby("corp_code", observed=True):
        prev_txt: Dict[str, str] = {}
        prev_year = None
        for _i, r in g.iterrows():
            cur = {k: tm_normalize_text(str(r.get(k) or "")) for k in ("s1_text", "s2_text", "s3_text")}
            if prev_year is not None and int(r["bsns_year"]) - int(prev_year) == 1:
                sims, per = [], {}
                for k in ("s1_text", "s2_text", "s3_text"):
                    if len(cur[k]) > 200 and len(prev_txt.get(k, "")) > 200:
                        m = tm_similarity(cur[k], prev_txt[k])
                        if np.isfinite(m["change"]):
                            sims.append(m)
                if sims:
                    per = {kk: float(np.nanmean([m[kk] for m in sims]))
                           for kk in ("cos", "jac", "edit", "lenr", "change")}
                    rows.append({"corp_code": str(corp), "bsns_year": int(r["bsns_year"]),
                                 "rcept_dt": r["rcept_dt"], "b1_change": per["change"],
                                 "b1_cos": per["cos"], "b1_jac": per["jac"],
                                 "b1_edit": per["edit"], "b1_lenr": per["lenr"]})
            prev_txt, prev_year = cur, r["bsns_year"]
    if not rows:
        return pd.DataFrame(columns=out_cols)
    B = pd.DataFrame(rows)
    B["knowledge_date"] = next_trading_day_series(as_ts_series(B["rcept_dt"]))
    LOG.ok(f"B1 텍스트 변화량 {len(B):,}건 (전년 동기 페어링 · 정규화 6단계 후 유사도 4종 평균) · "
           f"CHANGE 중앙값 {B['b1_change'].median():.3f}")
    return B[out_cols]


# ════════════════════════════════════════════════════════════════════════════════════════════
#  축 B — §4.3 B2 비정상 톤 (자기이력 표준화 + 펀더멘털 잔차)
# ════════════════════════════════════════════════════════════════════════════════════════════
def build_b2_tone(sect: pd.DataFrame, sec: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """B2 1~2단계: DART 전용 분류기(확장윈도우)로 S1+S2 톤 → 자기이력 표준화 TONE_selfz.

    ★ 축 A 분류기를 그대로 쓰지 않는다 — 문체 도메인이 다르다(§4.3[1]).
    ★ 라벨 오염 경고(명세 원문): 정기보고서는 재무제표와 동시 제출이라 2일 CAR 은 실적
      서프라이즈를 반영한다. 이 분류기는 '실적 방향 예측 문장'을 학습하는 것에 가깝고,
      그 오염은 [3] 펀더멘털 회귀(패널 층)가 제거한다. 이 한계는 보고서에 명시된다.
    """
    out_cols = ["corp_code", "bsns_year", "knowledge_date", "b2_tone", "b2_selfz"]
    if sect is None or sect.empty or not ensure_sklearn():
        return pd.DataFrame(columns=out_cols)
    S = sect[sect["sect_status"].astype(str).str.startswith("ok")].copy()
    if len(S) < 50:
        return pd.DataFrame(columns=out_cols)
    S["text"] = (S["s1_text"].astype(str).fillna("") + " " +
                 S["s2_text"].astype(str).fillna("")).str.strip()
    S = S[S["text"].str.len() > 300].copy()
    S["rcept_dt"] = as_ts_series(S["rcept_dt"])
    S = S.dropna(subset=["rcept_dt", "corp_code"])
    c2 = (sec.dropna(subset=["corp_code"]).drop_duplicates("corp_code")
             .set_index(sec.dropna(subset=["corp_code"]).drop_duplicates("corp_code")
                        ["corp_code"].astype(str))["code"].to_dict()) if len(sec) else {}
    S["code"] = S["corp_code"].astype(str).map(c2)

    # 라벨: 제출일 2일 시장조정 CAR (축 A 와 같은 구성 방식 재사용)
    lab_in = S.rename(columns={"rcept_no": "report_uid", "rcept_dt": "pub_date",
                               "code": "stock_code"})[["report_uid", "pub_date", "stock_code"]]
    lab = build_car_labels(lab_in.assign(text=""), px_daily) if len(lab_in) else pd.DataFrame()
    if lab is None or lab.empty:
        return pd.DataFrame(columns=out_cols)
    D = S.rename(columns={"rcept_no": "report_uid"}).merge(lab, on="report_uid", how="left")
    D = D.sort_values("rcept_dt", kind="stable")
    D["label_ready"] = as_ts_series(D["label_ready"])

    # 확장윈도우(연 단위) 학습 → 문서 확률 → tone = 2P−1
    years = sorted(D["rcept_dt"].dt.year.unique())
    scored = []
    for y in years:
        edge = as_ts(f"{y}-01-01")
        tr = D[D["label_ready"].notna() & (D["label_ready"] < edge) & D["label"].notna()]
        sub = D[D["rcept_dt"].dt.year == y]
        if sub.empty:
            continue
        if len(tr) < max(120, TONE_MIN_TRAIN_DOCS // 3) or tr["label"].nunique() < 2:
            continue
        try:
            vec = _SK["Tfidf"](analyzer="char_wb", ngram_range=(2, 4), min_df=3,
                               max_features=80000, sublinear_tf=True)
            Xtr = vec.fit_transform(tm_normalize_text_series(tr["text"]))
            clf = _SK["LR"](max_iter=500, C=0.5)
            clf.fit(Xtr, tr["label"].astype(int).to_numpy())
            p = clf.predict_proba(vec.transform(tm_normalize_text_series(sub["text"])))[:, 1]
        except Exception:
            continue
        r = sub[["corp_code", "bsns_year", "rcept_dt"]].copy()
        r["b2_tone"] = 2.0 * p - 1.0
        scored.append(r)
    if not scored:
        LOG.warn("B2 분류기 학습 표본이 부족합니다 — B2(비정상 톤)는 결측이며, "
                 "축 B 는 B1+B3 로 동작합니다(명세 §4.3 강등 규칙과 정합).")
        return pd.DataFrame(columns=out_cols)
    B = pd.concat(scored, ignore_index=True).dropna(subset=["b2_tone"])
    B["bsns_year"] = pd.to_numeric(B["bsns_year"], errors="coerce")
    B = B.sort_values(["corp_code", "bsns_year"], kind="stable")

    # [2] 자기이력 표준화 — 확장윈도우: 과거 동일유형(사업보고서) ≥ 4개 요건, 미달 결측
    B["b2_selfz"] = B.groupby("corp_code", observed=True)["b2_tone"] \
                     .transform(tm_selfz).astype("float32")
    B["knowledge_date"] = next_trading_day_series(as_ts_series(B["rcept_dt"]))
    n_hist = int(B["b2_selfz"].notna().sum())
    LOG.ok(f"B2 톤 {len(B):,}건 · 자기이력 표준화 성립 {n_hist:,}건 "
           f"(최소 이력 {TM_B2_MIN_HISTORY}개 요건 — 미달 {len(B)-n_hist:,}건은 결측)")
    LOG.info("한계 명시(명세 §4.3[1]): B2 라벨(제출일 2일 CAR)은 동시 제출된 재무제표의 실적 "
             "서프라이즈에 오염되어 있습니다. 펀더멘털 회귀 잔차(ABTONE)가 이 오염을 제거하는 "
             "역할을 하며, 그 전의 b2_tone 을 단독 신호로 읽으면 안 됩니다.")
    return B[out_cols]


def tm_normalize_text_series(s: pd.Series) -> pd.Series:
    return s.astype(str).map(tm_normalize_text)


def tm_selfz(s: pd.Series) -> pd.Series:
    """§4.3[2] 자기이력 표준화 — TONE_selfz(f,q) = [x_q − mean_{s<q}] / sd_{s<q}.

    확장윈도우: 분모·분자 모두 '자기 이전' 관측만 쓴다(shift(1) 후 expanding).
    최소 이력 TM_B2_MIN_HISTORY(=4) 미달이면 결측 — 1차 차분(분산 2σ²) 대비
    σ²(1+1/n) 로 노이즈가 낮다는 것이 이 형태를 사전등록한 이유다(n=4 에서 약 37% 감소).
    """
    prev = s.shift(1)
    mu = prev.expanding(min_periods=TM_B2_MIN_HISTORY).mean()
    sd = prev.expanding(min_periods=TM_B2_MIN_HISTORY).std(ddof=0)
    return (s - mu) / sd.where(sd > 0)


def tm_abtone_panel(P: pd.DataFrame) -> pd.DataFrame:
    """B2 3단계 — TONE_selfz 를 펀더멘털에 회귀한 잔차 ABTONE (분기별 횡단면 · 풀링 금지).

    설명변수(§4.3[3]): ROA · ΔROA · log시총 · BM · 수익률변동성 · 매출성장률 · 발생액 ·
    부채비율 · 섹터더미. 패널에서 구성 가능한 것만 쓰고 목록을 로그로 남긴다.
    """
    d = P.copy()
    d["abtone"] = np.nan
    if "b2_selfz" not in d.columns or d["b2_selfz"].notna().sum() < 30:
        return d
    d["_roa"] = safe_div(col(d, "net_income_ttm"), col(d, "assets"))
    d["_droa"] = d.sort_values("rebal").groupby("code", observed=True)["_roa"].diff(4)
    d["_bm"] = safe_div(col(d, "equity"), col(d, "mktcap"))
    d["_salesg"] = d.sort_values("rebal").groupby("code", observed=True)["revenue_ttm"] \
        .transform(lambda s: s / s.shift(4) - 1.0)
    feats = [c for c in ("_roa", "_droa", "log_cap", "_bm", "vol_d", "_salesg",
                         "accruals", "debt_ratio") if c in d.columns]
    if "log_cap" not in d.columns:
        d["log_cap"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").where(lambda s: s > 0))
        feats = ["log_cap"] + feats

    resid = pd.Series(np.nan, index=d.index, dtype="float64")
    n_fit = 0
    for t, g in d.groupby("rebal", observed=True):
        m = g["b2_selfz"].notna()
        if int(m.sum()) < 20:
            continue
        gg = g[m]
        y = pd.to_numeric(gg["b2_selfz"], errors="coerce").to_numpy(dtype="float64")
        Xp = [np.ones((len(gg), 1))]
        for c in feats:
            v = pd.to_numeric(gg[c], errors="coerce")
            v = v.fillna(v.median() if v.notna().any() else 0.0)
            if v.std(ddof=0) > 0:
                Xp.append(((v - v.mean()) / v.std(ddof=0)).clip(-5, 5).to_numpy().reshape(-1, 1))
        sec_s = gg["sector"].astype(str)
        for s in sec_s.value_counts()[lambda x: x >= 20].index.tolist()[:40][1:]:
            Xp.append((sec_s == s).to_numpy(dtype="float64").reshape(-1, 1))
        X = np.hstack(Xp)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if ok.sum() < max(20, X.shape[1] + 5):
            continue
        try:
            beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
            resid.loc[gg.index[ok]] = (y - X @ beta)[ok]
        except Exception:
            continue
        n_fit += 1
    d["abtone"] = resid.astype("float32")
    cov = float(d.loc[d["b2_selfz"].notna(), "abtone"].notna().mean()) \
        if d["b2_selfz"].notna().any() else 0.0
    LOG.ok(f"ABTONE(펀더멘털 잔차) {int(d['abtone'].notna().sum()):,}행 · 횡단면 {n_fit}시점 "
           f"(설명변수 {len(feats)}종: {', '.join(feats)}) — 사전등록 부호: ABTONE↑ → 수익률 −")
    d = d.drop(columns=[c for c in ("_roa", "_droa", "_bm", "_salesg") if c in d.columns])
    return d


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §5 — 결합 (부호 정렬 · INTERACT · 인과 점검)
# ════════════════════════════════════════════════════════════════════════════════════════════
def tm_combine(P: pd.DataFrame) -> pd.DataFrame:
    """축 B 합성점수 + Score2 입력 구성. 부호가 반대이므로 단순 합산을 금지한다(§5.1).

      축 B 성분(전부 '높을수록 악재' → −방향 정렬):
        · b1_change_z (섹터×리밸 z)        → −
        · abtone                            → −
        · dNONFIN (하드팩트, 높을수록 호재) → +   ← B3 층
      AXISB = 성분별 관측치 z 의 부호정렬 평균 (관측된 성분만 — 결측 성분으로 벌점 주지 않음)

      ★ 합성 산식 자체(성분 동일가중)는 명세가 정하지 않은 임의 선택이다 — §10.1 원장 기재.
      ★ INTERACT 는 사전등록 '가설'이며 선정 규칙이 아니다(§5.2 — 승격은 보고 후 지시 대기).
        F1 어블레이션에서만 페널티 항으로 검정한다.
    """
    d = P.copy()
    if "b1_change" in d.columns:
        d["b1_change_z"] = _cell_ladder_z(d, pd.to_numeric(d["b1_change"], errors="coerce"))
    comps = []                                    # (성분 z, 부호)
    if "b1_change_z" in d.columns and d["b1_change_z"].notna().sum() >= 30:
        comps.append(("b1_change_z", -1.0))
    if "abtone" in d.columns and d["abtone"].notna().sum() >= 30:
        z_ab = _cell_ladder_z(d, pd.to_numeric(d["abtone"], errors="coerce"))
        d["abtone_z"] = z_ab
        comps.append(("abtone_z", -1.0))
    if "dNONFIN" in d.columns and d["dNONFIN"].notna().sum() >= 30:
        d["dnonfin_z"] = _cell_ladder_z(d, pd.to_numeric(d["dNONFIN"], errors="coerce"))
        comps.append(("dnonfin_z", +1.0))

    if len(comps) >= 2:
        M = np.column_stack([sign * pd.to_numeric(d[c], errors="coerce").to_numpy(dtype="float64")
                             for c, sign in comps])
        with np.errstate(all="ignore"):
            d["dAXISB"] = np.nanmean(M, axis=1)
        d.loc[~np.isfinite(pd.to_numeric(d["dAXISB"], errors="coerce")), "dAXISB"] = np.nan
    else:
        # 성분이 dNONFIN 하나뿐(또는 전무)이면 원값 그대로 후퇴한다 — 스케일 혼합이 없으니
        # 합성 z 가 불필요하고, 하류 apply_filter2 의 z(관측→중립0)와 정확히 기존 QVF §6.3
        # 동작이 재현된다(어블레이션 B3v 와 C1 이 이 경우 같아지는 것도 명세와 정합).
        comps = []
        d["dAXISB"] = col(d, "dNONFIN")
    LOG.table([["축 B 성분", " · ".join(f"{c}({'+' if s>0 else '−'})" for c, s in comps) or
                "dNONFIN 단독(후퇴)"],
               ["AXISB 관측", f"{int(pd.to_numeric(d['dAXISB'], errors='coerce').notna().sum()):,}행"]],
              ["항목", "값"], ["l", "l"],
              title="축 B 합성 (§5.1 부호 정렬 — B1↑·ABTONE↑ 은 악재, 하드팩트↑ 는 호재)")

    # INTERACT (§5.2) — 보고 전용 플래그
    #  ★ d.get() 은 컬럼이 없으면 None/스칼라를 주고, 그 위의 .notna() 는 AttributeError 로
    #    죽는다(축 A 비활성 실행에서 실제 경로다). col() 은 항상 Series 를 돌려준다.
    d["INTERACT"] = 0.0
    a = pd.to_numeric(col(d, "dTONE_resid"), errors="coerce")
    b = pd.to_numeric(col(d, "abtone"), errors="coerce")
    if a.notna().sum() >= 30 and b.notna().sum() >= 30:
        for t, g in d.groupby("rebal", observed=True):
            aa, bb = a.loc[g.index], b.loc[g.index]
            if aa.notna().sum() < 10 or bb.notna().sum() < 10:
                continue
            ta = aa >= aa.quantile(1.0 - TM_INTERACT_TOP)
            tb = bb >= bb.quantile(1.0 - TM_INTERACT_TOP)
            d.loc[g.index[ta & tb & aa.notna() & bb.notna()], "INTERACT"] = 1.0
        LOG.info(f"INTERACT(톤 관리 탐지 가설) 발동 {int(d['INTERACT'].sum()):,}행 — "
                 f"선정 규칙이 아니라 사전등록 가설입니다. F1 어블레이션에서만 검정하고, "
                 f"배제 규칙 승격은 보고 후 지시를 기다립니다(§5.2).")
    return d


def tm_causal_check(P: pd.DataFrame) -> dict:
    """§5.3 — 두 축이 같은 정보의 두 반영이면 결합 가치가 없다. |ρ|>0.5 → 중단 보고."""
    out: Dict[str, Any] = {"halt": False}
    a = pd.to_numeric(P.get("dTONE_resid"), errors="coerce")
    b = pd.to_numeric(P.get("abtone"), errors="coerce")
    rows = []
    if a is not None and b is not None:
        cors = []
        for t, g in P.groupby("rebal", observed=True):
            sub = pd.DataFrame({"a": a.loc[g.index], "b": b.loc[g.index]}).dropna()
            if len(sub) >= 15:
                c = float(sub["a"].corr(sub["b"], method="spearman"))
                if np.isfinite(c):
                    cors.append((t, c))
        if cors:
            vals = [c for _t, c in cors]
            med = float(np.median(vals))
            out["corr_median"] = med
            rows.append(["ΔTONE_resid ↔ ABTONE 분기 상관 중앙값", f"{med:+.3f}"])
            rows.append(["상관 산출 시점 수", f"{len(cors)}"])
            if abs(med) > TM_CORR_HALT:
                out["halt"] = True
    if rows:
        LOG.table(rows, ["항목", "값"], ["l", "r"],
                  title="인과 순서 점검 확장 (TONE-MEASURE §5.3) — |ρ| > 0.5 면 결합 재설계 필요")
    if out.get("halt"):
        LOG.warn(f"★ §5.3 위반: 축 간 상관 중앙값 |{out['corr_median']:+.3f}| > "
                 f"{TM_CORR_HALT} — 두 축이 같은 정보를 세고 있습니다. 결합 구조 재설계가 "
                 f"필요하므로 이 사실을 폐기조건 TM[8]로 보고합니다(자동 재설계 금지).")
    TM_STATE["halt_corr"] = out.get("halt", False)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
#  §6 어블레이션 11종 · §7 폐기조건
# ════════════════════════════════════════════════════════════════════════════════════════════
TM_ABLATIONS = [
    ("A1", "축A 단독 — T2 · 직교화 ΔTONE_resid", "dTONE_resid"),
    ("A2", "축A 단독 — T2 · 직교화 미적용", "dTONE_t2"),
    ("A3", "축A 단독 — T3 종목단위(구 v1.0 재현)", "dTONE"),
    ("A4", "축A 단독 — T4 절대톤 횡단면 z(대조군)", "tone_abs_z"),
    ("A5", "축A 단독 — ΔNEG_resid 만(부정 단독 · 부호 −)", "neg_only"),
    ("B1v", "축B 단독 — B1 텍스트 변화량(부호 −)", "b1_only"),
    ("B2v", "축B 단독 — B2 비정상 톤(부호 −)", "b2_only"),
    ("B3v", "축B 단독 — B3 하드팩트", "dNONFIN"),
    ("C1", "축B 전체 (B1+B2+B3)", "dAXISB"),
    ("F1", "풀버전 + INTERACT 페널티(가설 검정용)", "score_f1"),
    ("F2", "풀버전 − INTERACT (실선정과 동일)", "score_f2"),
]


def tm_build_ablation_columns(P: pd.DataFrame) -> pd.DataFrame:
    """어블레이션이 쓰는 파생 점수 컬럼을 만든다. 전부 '높을수록 좋게' 부호 정렬돼 있다."""
    d = P.copy()
    if "tone_abs_q" in d.columns:
        d["tone_abs_z"] = _cell_ladder_z(d, pd.to_numeric(d["tone_abs_q"], errors="coerce"))
    if "dNEG_resid" in d.columns:
        d["neg_only"] = -pd.to_numeric(d["dNEG_resid"], errors="coerce")   # NEG↑ = 악재
    if "b1_change_z" in d.columns:
        d["b1_only"] = -pd.to_numeric(d["b1_change_z"], errors="coerce")
    if "abtone" in d.columns:
        d["b2_only"] = -pd.to_numeric(d["abtone"], errors="coerce")
    # F2 = 실선정 Score2 형태(2·축B + 1·ΔTONE_resid_z) · F1 = F2 − INTERACT 페널티
    zB = zscore_observed_then_neutral(d, "dAXISB", col(d, "dAXISB").notna())
    zT = zscore_observed_then_neutral(d, "dTONE_resid", col(d, "dTONE_resid").notna())
    d["score_f2"] = (SCORE2_W_NONFIN * zB + SCORE2_W_TONE * zT).astype("float32")
    _int = pd.to_numeric(col(d, "INTERACT", 0.0), errors="coerce").fillna(0.0)
    d["score_f1"] = (d["score_f2"] - 1.0 * _int).astype("float32")
    return d


def report_tm_kill(P: pd.DataFrame, fwd: pd.DataFrame, gates: dict, causal: dict) -> dict:
    """TONE-MEASURE §7 폐기조건. 파라미터 튜닝으로 되살리지 않는다 — 판정과 근거만 남긴다.
    ([4] 비용 차감 후 알파 소멸은 QVF §10.4 ① 이 같은 실행에서 판정한다.)"""
    out: Dict[str, Any] = {}
    rows = []

    k1 = not TM_STATE.get("axisA_on", False)
    out["TM1_axisA_off"] = k1
    rows.append(["[1] GATE_A1/A2 실패 → 축 A 비활성", f"A1 {100*gates.get('A1',0):.0f}% · "
                 f"A2 {100*gates.get('A2',0):.0f}%",
                 "❗ 축 A 꺼짐(축 B 단독이 주 결과)" if k1 else "✔ 축 A 활성"])

    a6 = gates.get("A6", float("nan"))
    k2 = bool(np.isfinite(a6) and a6 < TM_GATE_A6_MIN)
    out["TM2_A6_fail"] = k2
    rows.append(["[2] GATE_A6 (유효비율 < 30%) → 검증 불가",
                 f"{100*a6:.1f}%" if np.isfinite(a6) else "산출 불가",
                 "❗ 축 A 검증 불가" if k2 else "✔"])

    ic, icir, n_ic = rank_ic(P, "dTONE_resid", fwd) if "dTONE_resid" in P.columns \
        else (np.nan, np.nan, 0)
    t_ic = ic / (abs(ic) / max(abs(icir), 1e-9)) if np.isfinite(ic) and np.isfinite(icir) and icir != 0 else np.nan
    k3 = bool(np.isfinite(icir) and n_ic >= 8 and abs(icir) * math.sqrt(n_ic) < 2.0)
    out["TM3_ic_null"] = k3 if n_ic >= 8 else None
    rows.append(["[3] 직교화 후 ΔTONE_resid IC ≈ 0 → 축 A 폐기",
                 f"IC {ic:+.4f} · IC-IR {icir:+.3f} · n {n_ic}" if np.isfinite(ic) else "산출 불가",
                 ("판정불가(표본<8)" if n_ic < 8 else ("❗ IC 구분 불가" if k3 else "✔ 유의 후보"))])

    # [5] F1 vs B3v · [6] A1 vs A4 — 어블레이션 실행 후 paired_diff_test 로 판정
    for kid, a, b, desc in (("TM5", "TM-F1", "TM-B3v", "[5] F1 이 B3v 를 상회하는가"),
                            ("TM6", "TM-A1", "TM-A4", "[6] A1 이 A4(절대톤)를 상회하는가")):
        dt = paired_diff_test(a, b)
        bad = bool(np.isfinite(dt.get("p", np.nan)) and dt["p"] >= 0.10)
        out[kid] = bad if np.isfinite(dt.get("p", np.nan)) else None
        rows.append([desc, (f"차이 HAC t {dt['t']:+.2f} · p {dt['p']:.3f}"
                            if np.isfinite(dt.get("p", np.nan)) else "산출 불가"),
                     ("판정불가" if out[kid] is None else ("❗ 상회 못함" if bad else "✔ 상회"))])

    # [7] B1/B2 부호 역전 — 사전등록 부호(−)와 실측 IC 방향 비교 (뒤집지 말고 보고)
    for kid, colname, desc in (("TM7_B1", "b1_only", "[7] B1 부호(−) 역전 여부"),
                               ("TM7_B2", "b2_only", "[7] B2 부호(−) 역전 여부")):
        icb, icirb, nb = rank_ic(P, colname, fwd) if colname in P.columns else (np.nan, np.nan, 0)
        rev = bool(np.isfinite(icb) and nb >= 8 and icb < 0 and abs(icirb) * math.sqrt(max(nb, 1)) >= 2.0)
        out[kid] = rev if nb >= 8 else None
        rows.append([desc, f"정렬 후 IC {icb:+.4f} (n {nb})" if np.isfinite(icb) else "산출 불가",
                     ("판정불가" if out[kid] is None else
                      ("❗ 역전 — 해당 층 제외 버전이 주 결과" if rev else "✔ 사전등록 방향"))])

    k8 = bool(causal.get("halt"))
    out["TM8_corr"] = k8
    rows.append(["[8] 축 간 |ρ| > 0.5 → 결합 재설계", f"중앙값 {causal.get('corr_median', float('nan')):+.3f}"
                 if np.isfinite(causal.get("corr_median", float("nan"))) else "산출 불가",
                 "❗ 중단 보고" if k8 else "✔"])

    LOG.table(rows, ["폐기 조건 (TONE-MEASURE §7)", "근거 수치", "판정"], ["l", "l", "l"], maxw=46,
              title="TONE-MEASURE 사전등록 폐기조건 — 충족 시 튜닝으로 되살리지 않는다")
    LOG.info("보고서 1페이지 기재(§9.3): "
             f"Tier={TM_STATE.get('tier')} · 축A 활성={TM_STATE.get('axisA_on')} · "
             f"축A 유효비율(분기 중앙값)={100*a6:.1f}%" if np.isfinite(a6) else
             f"보고서 1페이지 기재(§9.3): Tier={TM_STATE.get('tier')} · "
             f"축A 활성={TM_STATE.get('axisA_on')} · 축A 유효비율 산출 불가")
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
#  패널 진입점 — pass2 에서 한 번 호출한다 (q90 배선을 최소로 유지)
# ════════════════════════════════════════════════════════════════════════════════════════════
def tm_type_shares(rep: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """(code, rebal)별 리포트 유형 비중 — §3.6 직교화의 유형 계절성 통제 입력."""
    R = rep.dropna(subset=["stock_code", "pub_date"]).copy()
    R["usable"] = next_trading_day_series(as_ts_series(R["pub_date"]))
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = R[(R["usable"] > lo) & (R["usable"] <= hi)]
        if w.empty:
            continue
        pv = (w.groupby(["stock_code", "report_type"], observed=True).size()
               .unstack(fill_value=0))
        pv = pv.div(pv.sum(axis=1), axis=0)
        pv.columns = [f"rt_share_{c}" for c in pv.columns]
        pv = pv.reset_index().rename(columns={"stock_code": "code"})
        pv["rebal"] = as_ts(t)
        parts.append(pv)
    if not parts:
        return pd.DataFrame(columns=["code", "rebal"])
    return pd.concat(parts, ignore_index=True).fillna(0.0)


def tm_gate_a6(P: pd.DataFrame) -> float:
    """GATE_A6 — U-200 내 축 A 유효 관측 비율의 분기 중앙값(§3.7)."""
    u200 = pd.Series(False, index=P.index)
    for v in VARIANTS:
        if f"u200_{v}" in P.columns:
            u200 |= P[f"u200_{v}"].fillna(False).astype(bool)
    if not u200.any() or "dTONE_resid" not in P.columns:
        return float("nan")
    shares = []
    for t, g in P[u200].groupby("rebal", observed=True):
        if len(g):
            shares.append(float(g["dTONE_resid"].notna().mean()))
    return float(np.median(shares)) if shares else float("nan")


def tm_panel(P: pd.DataFrame, ctx: dict, cal: pd.DataFrame) -> pd.DataFrame:
    """TONE-MEASURE 패널 층 — pass2 에서 orthogonalize_tone(구 T3) 직후 호출된다.

    실행 순서: 게이트 A1~A5 → 유형 비중 → T2 차분 → tier 별 ΔTONE_resid → B1/B2 결합 →
               ABTONE → 축 결합(dAXISB · INTERACT) → GATE_A6 → 어블레이션 컬럼.
    """
    d = P
    S = ctx.get("tone")
    links = ctx.get("links")
    if S is not None and len(S) and links is not None and len(links) \
            and "analyst_id" in links.columns:
        aid = links.drop_duplicates("report_uid")[["report_uid", "analyst_id"]]
        S = S.merge(aid, on="report_uid", how="left")

    gates = tm_gates_axisA(S, d, cal)

    rep = ctx.get("reports")
    if rep is not None and len(rep):
        rt = tm_report_type(rep)
        shares = tm_type_shares(rep.assign(report_type=rt), cal)
        if len(shares) and "code" in shares.columns:
            d = d.merge(shares, on=["code", "rebal"], how="left")

    t2 = tm_t2_delta(S, d, cal)
    keep = [c for c in ("dPOS_t2", "dNEG_t2", "dTONE_t2", "n_b", "tone_abs_q") if c in t2.columns]
    d = d.merge(t2[["code", "rebal"] + keep], on=["code", "rebal"], how="left")

    # A3(구 v1.0 재현) 보존 — pass2 가 이미 만든 종목단위 잔차
    if "dTONE_resid" in d.columns:
        d["dTONE_t3_resid"] = d["dTONE_resid"]

    if TM_STATE.get("axisA_on") and TM_STATE.get("tier") == "T2":
        d = tm_orthogonalize(d, "dTONE_t2", "dTONE_resid")
        d = tm_orthogonalize(d, "dNEG_t2", "dNEG_resid")
        d = tm_orthogonalize(d, "dPOS_t2", "dPOS_resid")
    elif TM_STATE.get("axisA_on"):
        LOG.warn("Tier=T3 폴백 — ΔTONE_resid 는 종목단위 차분 잔차(구 v1.0)를 그대로 씁니다.")
        d["dNEG_resid"] = np.nan
    else:
        d["dTONE_resid"] = np.nan
        d["dNEG_resid"] = np.nan

    sec = ctx.get("sec", pd.DataFrame())
    b1, b2 = ctx.get("b1"), ctx.get("b2")
    if b1 is not None and len(b1):
        d = _asof_attach(d, b1[["corp_code", "knowledge_date", "b1_change", "b1_cos",
                                "b1_jac", "b1_edit", "b1_lenr"]], sec,
                         ["b1_change", "b1_cos", "b1_jac", "b1_edit", "b1_lenr"])
    if b2 is not None and len(b2):
        d = _asof_attach(d, b2[["corp_code", "knowledge_date", "b2_tone", "b2_selfz"]], sec,
                         ["b2_tone", "b2_selfz"])
        d = tm_abtone_panel(d)
        # §4.3 강등 규칙 — U-200 내 B2 유효 비율 < 50% 면 보조 지표로 강등(합성에서 제외).
        u200 = pd.Series(False, index=d.index)
        for v in VARIANTS:
            if f"u200_{v}" in d.columns:
                u200 |= d[f"u200_{v}"].fillna(False).astype(bool)
        cov = float(d.loc[u200, "abtone"].notna().mean()) if u200.any() else 0.0
        TM_STATE["b2_demoted"] = bool(cov < TM_B2_DEMOTE_COV)
        if TM_STATE["b2_demoted"]:
            LOG.warn(f"B2 유효 비율 {100*cov:.1f}% < {100*TM_B2_DEMOTE_COV:.0f}% — 명세 §4.3 "
                     f"규칙대로 B2 를 '보조 지표'로 강등합니다(합성 제외 · 어블레이션 B2v 는 유지, "
                     f"제거는 하지 않는다 — B1 이 남는다).")
            d["_abtone_demoted"] = d["abtone"]
            d["abtone"] = np.nan

    d = tm_combine(d)
    a6 = tm_gate_a6(d)
    gates["A6"] = a6
    if np.isfinite(a6):
        ok6 = a6 >= TM_GATE_A6_MIN
        LOG.info(f"GATE_A6 (U-200 축A 유효비율 · 분기 중앙값) = {100*a6:.1f}% "
                 f"(기준 ≥ {100*TM_GATE_A6_MIN:.0f}%) → {'✔ 통과' if ok6 else '✘ 검증 불가'}")
        if not ok6 and TM_STATE.get("axisA_on"):
            LOG.warn("GATE_A6 미달 — 축 A 를 '검증 불가'로 판정하고 비활성화한 결과를 주 결과로 "
                     "삼습니다(§3.7). 결측 0 처리로 소수 종목에만 조용히 작동하는 상태를 "
                     "방치하지 않습니다. 가중치 재조정은 하지 않습니다(그건 튜닝이다).")
            d["_dTONE_resid_gated"] = d["dTONE_resid"]
            d["dTONE_resid"] = np.nan
            TM_STATE["axisA_valid"] = False
        else:
            TM_STATE["axisA_valid"] = bool(TM_STATE.get("axisA_on"))
    ctx["tm_gates"] = gates
    d = tm_build_ablation_columns(d)
    return d


def tm_required_comparisons() -> None:
    """§6.1 필수 비교 6종 — 어블레이션 실행 뒤 paired HAC 차이검정으로 정량 보고."""
    pairs = [("TM-A1", "TM-A3", "[1] Tier 개선폭 (T2 가 T3 를 상회 못하면 오염 제거 전제가 틀림)"),
             ("TM-A1", "TM-A4", "[2] 변화량 vs 절대톤 — 명세 핵심 주장 직접 검정"),
             ("TM-A1", "TM-A2", "[3] 직교화가 신호를 얼마나 깎는가"),
             ("TM-A1", "TM-A5", "[4] 긍정/부정 비대칭 (A5≈A1 이면 긍정 신호 폐기 대상)"),
             ("TM-F1", "TM-B3v", "[5] 텍스트 파이프라인이 재무 이상현상 하나를 이기는가"),
             ("TM-F1", "TM-F2", "[6] INTERACT 상호작용 항의 순기여")]
    rows = []
    for a, b, desc in pairs:
        if a not in EXPERIMENTS or b not in EXPERIMENTS:
            rows.append([desc, "산출 불가(버전 비활성)", "—"])
            continue
        dt = paired_diff_test(a, b)
        rows.append([desc,
                     (f"평균차 {dt['mean']*100:+.3f}%p · HAC t {dt['t']:+.2f} · p {dt['p']:.3f}"
                      if np.isfinite(dt.get("t", np.nan)) else "표본 부족"),
                     ("우위" if np.isfinite(dt.get("t", np.nan)) and dt["t"] > 0 else "열위/무차")])
    LOG.table(rows, ["필수 비교 (§6.1)", "정량 결과", "방향"], ["l", "l", "c"], maxw=58,
              title="TONE-MEASURE 필수 비교 6종 — 결과가 나쁘면 그대로 보고한다(§9.1)")


def tm_bottom_and_interact(P: pd.DataFrame, fwd: pd.DataFrame) -> None:
    """§6.2 부정 신호(BOTTOM 30%) 검증 + §5.2 INTERACT 그룹 사후수익률 비교."""
    if fwd is None or not len(fwd) or "dTONE_resid" not in P.columns:
        return
    F = fwd.set_index(["code", "rebal"])["fwd_ret"]
    a = pd.to_numeric(P["dTONE_resid"], errors="coerce")
    rows = []
    bot_r, top_r = [], []
    int_r, noint_r = [], []
    for t, g in P.groupby("rebal", observed=True):
        aa = a.loc[g.index].dropna()
        if len(aa) < 20:
            continue
        qlo, qhi = aa.quantile(0.30), aa.quantile(0.70)
        for idx in aa.index[aa <= qlo]:
            fr = F.get((str(P.at[idx, "code"]), as_ts(t)), np.nan)
            if np.isfinite(fr):
                bot_r.append(float(fr))
        top_idx = aa.index[aa >= qhi]
        it = pd.to_numeric(P.get("INTERACT"), errors="coerce").fillna(0.0)
        for idx in top_idx:
            fr = F.get((str(P.at[idx, "code"]), as_ts(t)), np.nan)
            if not np.isfinite(fr):
                continue
            top_r.append(float(fr))
            (int_r if it.loc[idx] > 0 else noint_r).append(float(fr))
    if bot_r and top_r:
        rows.append(["BOTTOM 30% 평균 forward 1Q", f"{np.mean(bot_r)*100:+.2f}% (n={len(bot_r):,})"])
        rows.append(["TOP 30% 평균 forward 1Q", f"{np.mean(top_r)*100:+.2f}% (n={len(top_r):,})"])
        asym = abs(np.mean(bot_r)) > abs(np.mean(top_r))
        rows.append(["비대칭 (|BOTTOM 알파| > |TOP 알파|)", "예 — 숏 슬리브는 보고 후 지시 대기(§6.2)"
                     if asym else "아니오"])
    if int_r and noint_r:
        rows.append(["INTERACT=1 ∧ ΔTONE 상위", f"{np.mean(int_r)*100:+.2f}% (n={len(int_r):,})"])
        rows.append(["INTERACT=0 ∧ ΔTONE 상위", f"{np.mean(noint_r)*100:+.2f}% (n={len(noint_r):,})"])
        rows.append(["§5.2 가설(관리된 낙관은 낮은 수익)",
                     "지지" if np.mean(int_r) < np.mean(noint_r) else
                     "기각 — 배제 승격 근거 없음(그대로 보고)"])
    if rows:
        LOG.table(rows, ["항목", "값"], ["l", "r"],
                  title="부정 신호 비대칭(§6.2) · INTERACT 그룹 비교(§5.2) — 자동 승격 금지")
