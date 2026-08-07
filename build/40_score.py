

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  거부권(V1~V8) + 스코어 조립  Signal = rank_pct(E) × rank_pct(U) × ∏V               ║
# ║                                                                                          ║
# ║  ★ V 를 연속화하면 전략이 붕괴한다. 어떤 센서 점수도 밀어내기 정황을 상쇄할 수 없어야 한다. ║
# ║    이것이 "취지에서 벗어난 종목"이 유입되는 유일한 통로다(§1.3).                            ║
# ║  ★ E 와 U 는 모두 백분위 랭크 변환 후 곱한다. 원값 곱셈은 음수 구간에서 단조성이 깨진다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VETO_DEFS = [
    ("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출 > 1.5", "제외"),
    ("V2", "순이익>0 인데 영업CF < 0.5×순이익 3분기 연속", "제외"),
    ("V3", "90일 내 대규모 희석성 조달(유증/CB/BW)", "제외"),
    ("V4", "θ 미달 / 매핑 실패 / 플라시보 p>0.05", "해당 팩만 무효화"),
    ("V5", "감사의견 비적정·관리종목·자본잠식", "제외"),
    ("V6", "유동성 하한 미달 또는 거래정지", "제외"),
    ("V7", "위험요인·우발부채 문단 유사도 셀 내 하위 5%", "제외"),
    ("V8", "인원 급증 + 유효세율 급락 (정책 유인 채용 의심)", "제외"),
]


def apply_vetoes(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """V_k ∈ {0,1}. 연속화·가중치화·상쇄 금지 (C6)."""
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)          # 없는 컬럼도 NaN 으로 만들어 준 뒤 그룹화 (DART 부분실패 내성)
    n = len(P)

    # ── V1 밀어내기 ────────────────────────────────────────────────────────────────────────
    d_rev = g("revenue_ttm").diff(12)
    d_inv = g("inventory").diff(12)
    d_rec = g("receivable").diff(12)
    push = safe_div(d_inv.fillna(0) + d_rec.fillna(0), d_rev)
    P["v1_metric"] = push
    P["V1"] = np.where((d_rev > 0) & (push > 1.5), 0.0, 1.0)

    # ── V2 이익-현금 괴리 '3분기 연속' ─────────────────────────────────────────────────────
    #   ★ 연속성은 반드시 '분기 프레임'에서 센다. 예전엔 월 패널에서 rolling(9) 로 셌는데,
    #     그건 "3분기 = 9개월"이라는 잘못된 전제다. 월 패널의 한 행은 분기 관측이 아니라
    #     '그 시점에 가장 최근 알려진 분기값'이고, 같은 분기값이 몇 달 동안 반복되는지는
    #     보고서 유형과 제출 지연에 따라 1~4개월로 들쭉날쭉하다. 그래서 rolling(9) 는
    #     발동이 1~2개월 늦고, 결산→1Q→반기처럼 반복이 짧은 창은 아예 놓친다.
    #     분기 프레임에서 rolling(3) 으로 만든 플래그(v2_bad_3q)를 as-of 결합으로 실어 오면
    #     C1 게이트웨이를 그대로 타면서 지연도 0 이 된다. (12_ingest_dart_fin 참조)
    v2q = col(P, "v2_bad_3q")
    if v2q.notna().any():
        P["v2_streak"] = v2q
        P["V2"] = np.where(v2q.fillna(0.0) >= 1.0, 0.0, 1.0)
    else:
        # 분기 플래그가 없으면(재무 미수집) 거부하지 않는다 — 근거 없는 제외가 더 위험하다.
        P["v2_streak"] = np.nan
        P["V2"] = 1.0

    # ── V3 희석성 조달 (공시목록에서 직접 관측) ────────────────────────────────────────────
    P["V3"] = 1.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns:
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

    # ── V4 부분 거부권: 팩별 θ / 매핑 품질 ─────────────────────────────────────────────────
    #    전면 제외가 아니라 '해당 팩만 무효화' — 유일한 부분 거부권이다.
    P["V4"] = 1.0
    for p in active_packs():
        tc = p.get("theta_col")
        ecol = p["E_col"]
        if tc and tc in P.columns and ecol in P.columns:
            kill = P[tc].isna() | (P[tc] < 0.50)
            P.loc[kill, ecol] = np.nan
            if int(kill.sum()):
                LOG.info(f"V4 부분거부권 — 팩 {p['id']}: θ<0.50 인 {int(kill.sum()):,}행의 "
                         f"{ecol} 무효화 (전면 제외가 아님)")

    # ── V5 감사의견/관리종목/자본잠식 ──────────────────────────────────────────────────────
    impair = (col(P, "equity") <= 0)
    P["V5"] = np.where(impair.fillna(False), 0.0, 1.0)
    adm = ctx.get("administrative")
    if adm is not None and len(adm):
        bad_codes = set(adm["code"].dropna())
        P["V5"] = np.where(P["code"].isin(bad_codes), 0.0, P["V5"])

    # ── V6 유동성 ──────────────────────────────────────────────────────────────────────────
    P["V6"] = np.where((P["adv20"].fillna(0) >= MIN_ADV_KRW) & (P["close"].fillna(0) > 0), 1.0, 0.0)

    # ── V7 공시텍스트 (PACK-D) ─────────────────────────────────────────────────────────────
    P["V7"] = 1.0
    if "sim_risk_pct" in P.columns:
        P["V7"] = np.where(P["sim_risk_pct"] < 0.05, 0.0, 1.0)

    # ── V8 정책 유인 채용 의심 ─────────────────────────────────────────────────────────────
    P["V8"] = 1.0
    if "n1" in P.columns and "d_eff_tax" in P.columns:
        n1_hi = P["n1"] > P.groupby("month", observed=True)["n1"].transform(
            lambda s: s.quantile(0.90))
        tax_drop = P["d_eff_tax"] < -0.03
        P["V8"] = np.where(n1_hi.fillna(False) & tax_drop.fillna(False), 0.0, 1.0)

    vcols = [f"V{i}" for i in range(1, 9)]
    for c in vcols:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(1.0)
        uniq = set(np.unique(P[c].dropna()))
        if not uniq <= {0.0, 1.0}:
            raise ValueError(f"[C6 위반] 거부권 {c} 가 이진이 아닙니다: {sorted(uniq)[:5]}. "
                             f"거부권은 절대 연속화하지 않습니다.")
    P["VETO"] = P[vcols].prod(axis=1)
    fired = {c: int((P[c] == 0).sum()) for c in vcols}
    LOG.table([[c, d, act, f"{fired[c]:,}", f"{100*fired[c]/max(n,1):.2f}%"]
               for (c, d, act) in VETO_DEFS],
              ["ID", "조건", "조치", "발동 행수", "비율"], ["c", "l", "c", "r", "r"],
              title="거부권 발동 현황 (V∈{0,1} · 곱 · 상쇄 불가)")
    return P


MIN_FLOOR_AXES = 2


def compute_floor(P: pd.DataFrame, cols: Sequence[str], min_axes: int = MIN_FLOOR_AXES,
                  pct_out: Optional[dict] = None) -> pd.Series:
    """§8.2 하한선 — "그 종목이 실제로 보유한 축은 모두 셀 내 50th 이상 + 축이 최소 2개".

    ★ 왜 함수로 빼는가: 하한선은 본선에서만 쓰이는 게 아니라 R2 킬게이트·R5 절제실험의
      비교팔에서도 다시 만들어져야 한다. 예전엔 비교팔이 본선의 FLOOR 컬럼을 그대로
      복사해 썼는데, FLOOR 는 전부 TP 에서 파생된 값이라 '나이브 팔'조차 TP 로 선별된
      종목만 보게 된다. 실측하면 FLOOR 하나가 종목 선정의 92% 를 끝내 버려서, TP 팔과
      균등난수 팔의 보유종목 자카드 유사도가 0.73 이었다 — 무엇과도 구별하지 못하는
      킬게이트는 킬게이트가 아니다. 규칙을 한 곳에 두고 각 팔이 '자기 증거'로 만든다.
    """
    ok = pd.Series(0, index=P.index)
    bad = pd.Series(0, index=P.index)
    for c in cols:
        pct = xsec_rank_pct_l(P, c)
        if pct_out is not None:
            pct_out[c] = pct
        ok += (pct >= 0.50).fillna(False).astype(int)
        bad += (pct < 0.50).fillna(False).astype(int)
    return ((bad == 0) & (ok >= min_axes)).astype(float)


def score_from_axes(P: pd.DataFrame, all_e: Sequence[str],
                    min_axes: int = MIN_FLOOR_AXES) -> dict:
    """주어진 축 집합 하나로 E·FLOOR·Signal·Signal_rank 를 만드는 단일 경로.

    본선(assemble_score)과 강건성 비교팔(R2·R5)이 **반드시 이 함수만** 통과해야 한다.
    비교팔이 다른 경로로 점수를 만들면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를
    재게 된다. 실제로 아무것도 빼지 않은 널-절제의 ΔSharpe 가 +2.08 로 나온 적이 있다.

    두 가지 계산상의 선택을 여기에 못박는다:

    ① 축을 평균하기 전에 축별로 z 표준화한다.
       E_AXB 같은 축은 표준편차가 0.9, E_X 같은 축은 0.1 인데 원값을 그대로 평균하면
       "팩 간 동일가중(C7)"이라고 로그에 찍으면서 실제로는 분산비 만큼(실측 9.4배)
       가중이 갈린다. z 로 분산을 맞춘 뒤 평균해야 로그가 참이 된다.
       (백분위 평균이 아니라 z 평균인 이유: 백분위는 1.0 에서 잘려서 '트레이드오프가
        극적으로 붕괴한 종목'과 '그냥 괜찮은 종목'을 구별하지 못한다. 이 전략이 재려는
        크기 정보가 바로 거기 있다. C5 가 정한 winsorize→z→백분위 순서와도 맞는다)

    ② Signal_rank 는 '월 전체' 백분위다. (month, pack_profile) 로 나눠 매기면 안 된다.
       프로파일이 다른 종목끼리 랭크가 서로 비교 불가능해지는데, 정작 선정부는
       nlargest 로 월 전체를 한 줄로 세워 뽑는다. 그러면 '자기 프로파일에서 혼자'인
       종목이 전부 1.0 을 받아 상위를 채우고, 실측상 월 보유종목의 70%가 동점 1.0 중
       종목코드 순으로 결정됐다. 정보량 차이는 pack_profile 랭킹이 아니라
       FLOOR(빈 축 없음 + 최소 2축)가 이미 막는다.
    """
    all_e = list(all_e)
    pcts: dict = {}
    Z = pd.DataFrame({c: xsec_z_l(P, c) for c in all_e}, index=P.index)
    E_raw = nanmean_cols(Z, all_e)                       # ① 축별 z → 동일가중 평균
    E = xsec_rank_pct_l(P, E_raw)
    FLOOR = compute_floor(P, all_e, min_axes, pct_out=pcts)
    U = P["U"].fillna(0) if "U" in P.columns else pd.Series(0.0, index=P.index)
    VETO = P["VETO"].fillna(0) if "VETO" in P.columns else pd.Series(1.0, index=P.index)
    Signal = E.fillna(0) * U * VETO * FLOOR
    prof = P[all_e].notna().astype(int).astype(str).agg("".join, axis=1)
    rank = Signal.groupby(P["month"], observed=True).rank(pct=True, method="average")  # ②
    return {"E_raw": E_raw, "E": E, "FLOOR": FLOOR, "Signal": Signal,
            "pack_profile": prof, "Signal_rank": rank,
            "n_axes_active": P[all_e].notna().sum(axis=1), "pcts": pcts}


def assemble_score(P: pd.DataFrame) -> pd.DataFrame:
    """E = mean(활성 팩 + 공용축 B·C), U = 반영도, Signal = rank(E)×rank(U)×∏V.

    C7: TP 내 → 팩 내 → 팩 간 모두 동일가중. 이것이 기본값이자 최종값이다.
    """
    packs = active_packs()
    ecols = [p["E_col"] for p in packs if p["E_col"] in P.columns]
    axcols = [c for c in ("E_AXB", "E_AXC") if c in P.columns]

    # ── ① 데이터가 아예 없는 팩은 자동 비활성화 (§8.4) ────────────────────────────────────
    #     이걸 안 하면 빈 팩 하나 때문에 아래 하한선에서 전 종목이 탈락한다.
    live_e = []
    for c in ecols:
        cov = float(P[c].notna().mean()) if len(P) else 0.0
        if cov < 0.01:
            pid = next((p["id"] for p in packs if p["E_col"] == c), c)
            disable_pack(pid, f"패널 내 {c} 관측 커버리지 {cov*100:.2f}% — 데이터 부재로 자동 비활성화")
            P[f"pct_{c}"] = np.nan
        else:
            live_e.append(c)
    all_e = live_e + axcols
    if not all_e:
        raise RuntimeError("합성할 증거층(E) 컬럼이 하나도 없습니다. "
                           "활성 팩의 원천 데이터가 전부 비어 있는지 위 수집 로그를 확인하세요.")
    if "U" not in P.columns:
        P["U"] = np.nan

    # ── ② 점수 조립 — 본선도 비교팔과 완전히 같은 경로를 탄다 ────────────────────────────
    #   (§8.2 하한선 원문: "활성 센서팩 및 B·C축 각각의 셀 내 백분위가 모두 ≥ 50th"
    #    "'모든 축이 상위'가 아니라 '빈 축이 없을 것'. 표본 붕괴 없이 단일 축 편중을 막고"
    #
    #    ★ 순진하게 '전 축 conjunction' 으로 구현하면 두 가지가 깨진다:
    #      (a) V4 는 §9에서 유일한 '부분' 거부권인데, θ 미달로 E_N 이 NaN 이 되면 그 종목이
    #          하한선에서 통째로 탈락한다 → 부분 거부권이 전면 제외로 변질된다.
    #      (b) 축이 7개면 잔존율이 0.5^7 ≈ 0.8% 로 붕괴한다 → 스펙이 명시적으로 금지한 '표본 붕괴'.
    #    그래서 "보유한 축은 모두 50th 이상" + "축 최소 MIN_FLOOR_AXES 개" 로 읽는다)
    S = score_from_axes(P, all_e)
    for k in ("E_raw", "E", "FLOOR", "Signal", "pack_profile", "Signal_rank", "n_axes_active"):
        P[k] = S[k]
    for c, pct in S["pcts"].items():
        P[f"pct_{c}"] = pct

    # ── ③ 진단 출력 ───────────────────────────────────────────────────────────────────────
    ret = float(P["FLOOR"].mean()) if len(P) else 0.0
    rows = [[c, f"{float(P[c].notna().mean())*100:.1f}%",
             f"{float((P[f'pct_{c}'] >= 0.50).mean())*100:.1f}%"] for c in all_e]
    LOG.table(rows, ["증거층 축", "관측 커버리지", "50th 이상 비율"], ["l", "r", "r"],
              title="하한선 구성 축 (§8.2 — 빈 축이 없을 것)")
    LOG.info(f"하한선 통과 {int(P['FLOOR'].sum()):,}행 / {len(P):,}행 ({ret*100:.1f}%) · "
             f"보유 축 중앙값 {float(P['n_axes_active'].median()):.0f}개")
    if ret < 0.03:
        LOG.warn(f"하한선 잔존율이 {ret*100:.1f}% 로 매우 낮습니다. 축이 많을수록 "
                 f"'모든 축 ≥ 50th' 조건은 기하급수적으로 좁아집니다(축 k개면 대략 0.5^k). "
                 f"§8.2 는 '표본 붕괴 없이' 를 명시하므로, 활성 팩 수를 줄이거나 "
                 f"팩별 단독 파일로 나눠 돌리는 편이 스펙 의도에 더 가깝습니다.")

    prof_n = int(P["pack_profile"].nunique())
    LOG.ok(f"스코어 조립 완료 — 증거층 {len(all_e)}개 축 z표준화 후 동일가중 "
           f"({', '.join(all_e)}) · 하한선 통과 {int(P['FLOOR'].sum()):,}행 "
           f"({100*P['FLOOR'].mean():.1f}%) · Signal_rank 는 월 전체 백분위 "
           f"(정보량 프로파일 {prof_n}종은 진단용으로만 기록)")
    PIPE.io("OUT", "MEM", "scored_panel", P)
    return P
