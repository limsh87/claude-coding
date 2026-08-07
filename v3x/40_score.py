# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2 — 셀 정규화 · 트레이드오프 쌍 · 거부권 · 최종 신호                                      ║
# ║                                                                                             ║
# ║  ★ 원칙 2 (이 코드 전체에서 가장 중요한 한 줄)                                              ║
# ║      TP = max(rank-0.5, 0) × max(rank-0.5, 0)                                                ║
# ║    절대 `z × z` 로 두지 않는다. 그러면 (-2)×(-2)=+4 가 되어                                  ║
# ║    '물량 급감 + 단가 급락' 종목이 최고점을 받는다. 횡단면 랭크이므로 유니버스의 약 25%가     ║
# ║    양쪽 음수이고, 그 25%가 상위 분위를 통째로 오염시킨다.                                    ║
# ║    음수 절단 후 곱하면 결과가 항상 [0, 0.25] 이라 '최악이 최고점'이 구조적으로 불가능하다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 트레이드오프 쌍 정의 (§8.1).
#   (ID, 개선축, 대가회피축, 축그룹, 발화 의미, 미발화 의미)
XCB_TP_SPECS: "list[tuple]" = [
    ("TP_X1", "a1", "a2", "A", "물량↑인데 단가 안 깎임 = 수요곡선 이동",
     "물량을 가격 인하로 산 것 / 정책 보조"),
    ("TP_X2", "a3", "a2", "A", "다변화인데 믹스 유지 = 제품력",
     "저가 물량으로 고객 늘림"),
    ("TP_X3", "a4", "c5_neg", "A", "선진시장↑인데 판관비 안 늘음 = 제품이 스스로 팔림",
     "마케팅으로 산 시장"),
    ("TP_X4", "a5", "a1", "A", "신규 세번 + 물량 = R&D→상업화 실물 증거",
     "시범 선적에 불과"),
    ("TP_XC", "c6", "a1", "A", "수주공시 × 통관물량 = 독립 2소스 교차확증",
     "공시만 있고 실물 없음"),
    ("TP_B1", "b1", "b2", "B", "매출↑인데 회전 유지 = 수요가 당김",
     "밀어내기 → V1 확인"),
    ("TP_B2", "b1", "b3", "B", "매출↑인데 발생액 유지 = 이익의 질",
     "회계적 이익 우위"),
    ("TP_C1", "c1", "c2", "C", "확장하는데 ROIC 유지 = 제약선 이동",
     "확장이 수익성 희석"),
    ("TP_C2", "c3", "c4", "C", "인원↑인데 고임금 채용 = 고부가 인력 확충",
     "저임금 대량채용(보조금 의심)"),
]
XCB_TP_COLS = [s[0] for s in XCB_TP_SPECS]
XCB_TP_AXIS = {s[0]: s[3] for s in XCB_TP_SPECS}

# 단계별로 활성화되는 TP (§12.1 단계 게이트)
STAGE_TPS = {
    "M0": ["TP_X1", "TP_X2", "TP_B1", "TP_B2"],
    "M1": ["TP_X1", "TP_X2", "TP_X3", "TP_X4", "TP_XC", "TP_B1", "TP_B2", "TP_C1"],
    "M2": XCB_TP_COLS,
    "ALL": XCB_TP_COLS,
}
STAGE_VETOES = {
    "M0": ["V1", "V2", "V5", "V6", "V10", "V12"],
    "M1": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
    "M2": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
    "ALL": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
}
STAGE_UAXES = {
    "M0": ["d1"],
    "M1": ["d1", "d3"],
    "M2": ["d1", "d2", "d3", "d4"],
    "ALL": ["d1", "d2", "d3", "d4"],
}

# 전면 거부권 / 부분 거부권 (§9). 부분 거부권은 A축 또는 a2 만 무효화한다.
VETO_HARD = ("V1", "V2", "V3", "V5", "V6", "V11")
VETO_PARTIAL = ("V9", "V10", "V12")


def make_cells(P: pd.DataFrame) -> pd.DataFrame:
    """셀 = date × HS군 × 규모버킷 (§8).

    ★ 산업분류 대신 HS군을 쓰는 이유: 이 전략의 비교 대상은 '같은 물건을 파는 회사'다.
      표준산업분류는 화학 하나에 범용수지와 이차전지 소재를 같이 넣는다.
    ★ 규모버킷을 셀에 넣는 이유: 정부 지원제도 요건 대부분이 기업 규모에 연동된다.
      규모를 셀에 넣으면 정책 효과가 셀 내 공통충격으로 흡수된다. 비용 0의 방어다(§10-②).
    """
    d = P.copy()
    hs_main = d.get("hs_main")
    if hs_main is None:
        d["hs_group"] = "NA"
    else:
        # HS 2자리(章)를 군으로 쓴다. 6자리는 셀이 종목 1개로 쪼개져 랭크가 의미를 잃는다.
        d["hs_group"] = hs_main.astype(str).str.zfill(6).str[:2].fillna("NA")
    mc = pd.to_numeric(d.get("mcap"), errors="coerce")
    if mc.notna().sum() == 0:
        mc = pd.to_numeric(d.get("adtv20"), errors="coerce")
    r = mc.groupby(d["ym"], observed=True).rank(pct=True)
    d["size_bucket"] = pd.cut(r, [-0.01, 0.33, 0.66, 1.01],
                              labels=["S", "M", "L"]).astype(object).fillna("NA")
    ym = d["ym"].astype("datetime64[ns]").astype(str)
    d["cell"] = ym + "|" + d["hs_group"].astype(str) + "|" + d["size_bucket"].astype(str)
    d["cell_l2"] = ym + "|" + d["hs_group"].astype(str)
    d["cell_l3"] = ym
    return d


def _cells_of(P: pd.DataFrame) -> "tuple":
    fb = [P[c] for c in ("cell_l2", "cell_l3") if c in P.columns]
    return (P["cell"] if "cell" in P.columns else pd.Series("NA", index=P.index)), fb


def tp_pair(P: pd.DataFrame, a: str, b: str, mode: str = "clip") -> pd.Series:
    """★ 음수 절단 후 곱. 개선이 없거나 대가를 치렀으면 정확히 0.

    mode="clip"    : max(rank-0.5,0) × max(rank-0.5,0)   ← XCB 사양 §8. 기본값.
    mode="zclip"   : max(z,0) × max(z,0)                  ← v3 코어 `tp()`. R5 비교용
    mode="rankprod": rank × rank                          ← R5 절제 비교용
    mode="signed"  : z × z                                ← v2 부호버그 재현(R5 에서만)

    ★ 사양이 rank 기반인 이유: 결과가 [0,0.25] 로 유계라 한 종목의 극단 z 가 E 평균을
      지배하지 못한다. z 절단은 상한이 없어 이상치 하나가 그 달 전체를 끌고 간다.
      두 정의를 R5 에서 실측 비교하고 결과를 그대로 보고한다.
    """
    if mode in ("zclip", "signed"):
        cells, fb = _cells_of(P)
        return tp_dispatch("signed" if mode == "signed" else "clip",
                           col(P, a), col(P, b), cells, fb)
    ra = xsec_rank_pct_l(P, a)
    rb = xsec_rank_pct_l(P, b)
    if mode == "rankprod":
        return (ra * rb).astype("float32")
    za = ra - 0.5
    zb = rb - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    # 한쪽이라도 관측이 없으면 TP 는 결측이다. 0 으로 채우면 '대가를 안 치렀다'는
    # 적극적 주장이 되어 버린다 — 모르는 것과 좋은 것을 구분해야 한다.
    return pd.Series(np.where(ra.isna() | rb.isna(), np.nan, out),
                     index=P.index, dtype="float32")


def build_tps(P: pd.DataFrame, tps: "Sequence[str]", mode: str = "clip") -> pd.DataFrame:
    d = P.copy()
    # TP_X3 은 -c5 를 쓴다(판관비가 '안 늘어난 것'이 미덕).
    if "c5" in d.columns:
        d["c5_neg"] = -pd.to_numeric(d["c5"], errors="coerce")
    for tid, ca, cb, _ax, _f, _n in XCB_TP_SPECS:
        if tid not in tps:
            d[tid] = np.nan
            continue
        if ca not in d.columns or cb not in d.columns:
            d[tid] = np.nan
            continue
        d[tid] = tp_pair(d, ca, cb, mode=mode)
    return d


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  거부권 — 이진 · 곱 · 상쇄 불가 (§9)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def apply_vetoes(P: pd.DataFrame, vetoes: "Sequence[str]",
                 cv_thresh_pct: float = CV_DEST_COMMODITY_PCT) -> pd.DataFrame:
    """거부권은 점수가 아니다. 이진값이고 곱이며 다른 축이 상쇄할 수 없다.

    전면 거부권(V1,V2,V3,V5,V6,V11) → 그 달 그 종목은 후보에서 완전히 빠진다.
    부분 거부권(V9,V10,V12)         → A축(또는 a2)만 무효화하고 E 를 재계산한다.
                                      정보량이 다른 종목을 직접 비교하지 않기 위해
                                      '활성 축 조합이 같은 종목끼리' 따로 랭크한다.
    """
    d = P.copy()
    zero = pd.Series(0.0, index=d.index)

    def _num(name: str) -> pd.Series:
        """★ 없는 컬럼에 d.get() 을 쓰면 None 이 오고, pd.to_numeric(None) 은 **스칼라**가 된다.
        그 스칼라에 비교연산을 걸면 numpy.bool 이 나와 .fillna 에서 크래시한다.
        데이터가 없을수록 잘 죽는 구조라 실데이터에서 더 자주 터진다 — 항상 Series 를 돌려준다."""
        if name in d.columns:
            return pd.to_numeric(d[name], errors="coerce")
        return pd.Series(np.nan, index=d.index, dtype="float64")

    def _f(name: str, cond) -> pd.Series:
        """조건이 참이면 1(발동). 판단 근거가 없으면 0(발동하지 않음) — 모른다고 배제하지 않는다."""
        if name not in vetoes:
            return zero
        c = cond if isinstance(cond, pd.Series) else pd.Series(bool(cond), index=d.index)
        return c.reindex(d.index).fillna(False).astype(float)

    # V1 밀어내기: Δ매출>0 ∧ (Δ재고+Δ매출채권)/Δ매출 > 1.5
    d["V1"] = _f("V1", _num("v1_ratio") > 1.5)
    # V2 이익-현금 괴리 3분기 연속
    d["V2"] = _f("V2", _num("v2_streak") > 0)
    # V3 90일 내 대규모 희석성 조달
    d["V3"] = _f("V3", _num("dilution_90d") > 0)
    # V5 감사의견 비적정 / 관리종목 / 자본잠식 / 거래정지
    d["V5"] = _f("V5", _num("watch_flag") > 0)
    # V6 유동성
    d["V6"] = _f("V6", _num("adtv20") < UNIVERSE_MIN_ADTV)
    # V11 정책 의존: 유효세율 급락(<-3%p) ∨ 정부보조금수익/매출 급증
    etr_drop = _num("etr_chg") < -0.03
    subsidy = _num("subsidy_ratio_chg") > 0.01
    d["V11"] = _f("V11", etr_drop | subsidy)

    # ── 부분 거부권
    # V9 해외생산 이전: θ_X 급락 ∧ 해외 종속기업 매출 급증
    theta_drop = _num("theta_x_chg") < -0.10
    oversea = _num("oversea_rev_chg") > 0.20
    d["V9"] = _f("V9", theta_drop & oversea)
    # V10 커모디티: cv_dest 하위 N% → a2 무효화
    if "cv_dest" in d.columns and pd.to_numeric(d["cv_dest"], errors="coerce").notna().any():
        cvr = _num("cv_dest").rank(pct=True)
        d["V10"] = _f("V10", cvr <= cv_thresh_pct)
    else:
        d["V10"] = zero
    # V12 매핑 게이트 실패 → A축 무효화
    d["V12"] = _f("V12", _num("map_gate_fail") > 0)

    for v in ("V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"):
        if v not in d.columns:
            d[v] = zero
    d["veto_hard"] = np.maximum.reduce([d[v].to_numpy() for v in VETO_HARD])
    d["veto_pass"] = 1.0 - d["veto_hard"]
    return d


def disable_axes(P: pd.DataFrame) -> pd.DataFrame:
    """부분 거부권을 실제 무효화로 반영한다.

    V10 → a2 무효화 (a1·a3·a4 는 유지). a2 를 쓰는 TP_X1·TP_X2 가 결측이 된다.
    V9/V12 → A축 전체 무효화. E 를 B·C축만으로 재계산한다. flag="X_DISABLED".
    """
    d = P.copy()
    v10 = pd.to_numeric(d.get("V10"), errors="coerce").fillna(0) > 0
    v_a = (pd.to_numeric(d.get("V9"), errors="coerce").fillna(0) > 0) | \
          (pd.to_numeric(d.get("V12"), errors="coerce").fillna(0) > 0)

    for tid, ca, cb, ax, _f, _n in XCB_TP_SPECS:
        if tid not in d.columns:
            continue
        kill = v_a if ax == "A" else pd.Series(False, index=d.index)
        if "a2" in (ca, cb):
            kill = kill | v10
        d.loc[kill, tid] = np.nan

    d["axis_flag"] = np.where(v_a, "X_DISABLED",
                              np.where(v10, "A2_DISABLED", "FULL"))
    return d


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  최종 신호
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def compose_signal(P: pd.DataFrame, tps: "Sequence[str]", uaxes: "Sequence[str]",
                   use_theta: bool = True,
                   breadth_floor: float = BREADTH_FLOOR_PCT) -> pd.DataFrame:
    """E · U · Signal 을 조립한다.

        E      = mean(활성 TP) × θ_X
        U      = mean(z(활성 d축))          ← 결측 축은 '제외 평균'. 0으로 채우지 않는다.
        Signal = rank_pct(E) × rank_pct(U) × ∏V

    ★ E 와 U 를 각각 백분위 랭크한 뒤 곱한다. 원값 곱은 음수 구간에서 단조성이 깨진다.
    ★ 랭크는 '활성 축 조합이 같은 종목끼리' 따로 매긴다 — A축이 죽은 종목과 살아있는 종목은
      정보량이 다르므로 같은 자에 놓고 재면 안 된다.
    """
    d = P.copy()
    have = [t for t in tps if t in d.columns]
    if not have:
        d["E"] = np.nan
        d["U"] = np.nan
        d["Signal"] = np.nan
        d["Signal_rank"] = np.nan
        return d

    # ── E: 활성 TP 의 '제외 평균'. 관측된 TP 가 하나도 없으면 결측이다.
    d["E_raw"] = nanmean_cols(d, have)
    d["n_tp"] = d[have].notna().sum(axis=1)
    th = pd.to_numeric(d.get("theta_x"), errors="coerce")
    if use_theta:
        # θ_X 를 못 구한 종목은 1.0 이 아니라 중앙값으로 둔다. 1.0 은 '수출이 전부'라는
        # 적극적 주장이라 관측 실패를 강점으로 바꿔 버린다.
        th = th.fillna(th.median() if th.notna().any() else 1.0)
        d["E"] = d["E_raw"] * th.clip(0.0, 1.0)
    else:
        d["E"] = d["E_raw"]

    # ── U: z 의 제외 평균
    zs = []
    for u in uaxes:
        if u in d.columns and pd.to_numeric(d[u], errors="coerce").notna().any():
            zs.append(xsec_z_l(d, u))
    if zs:
        Z = pd.concat(zs, axis=1)
        d["U"] = Z.mean(axis=1, skipna=True)
        d["n_u"] = Z.notna().sum(axis=1)
    else:
        d["U"] = np.nan
        d["n_u"] = 0

    # ── 하한선(breadth floor): 활성 축 각각의 셀 내 백분위 ≥ 50th
    #   ★ TP 곱으로 재면 안 된다. clip(z,0) 은 0 동점 덩어리가 크고(약 75%),
    #     그 덩어리의 평균 랭크가 0.375 라 50th 문턱에서 전량 탈락한다.
    #     '개선축의 원시 센서'로 재야 의도대로 "빈 축이 없을 것"을 뜻한다.
    axis_src = {"A": ["a1", "a2", "a3", "a4"], "B": ["b1", "b2", "b3"],
                "C": ["c1", "c2", "c3"]}
    floor_ok = pd.Series(True, index=d.index)
    for ax, cols in axis_src.items():
        act = [c for c in cols if c in d.columns and
               pd.to_numeric(d[c], errors="coerce").notna().any()]
        if not act:
            continue
        rk = pd.concat([xsec_rank_pct_l(d, c) for c in act], axis=1).mean(axis=1, skipna=True)
        d[f"floor_{ax}"] = rk
        # 그 축을 아예 관측 못한 종목은 '빈 축'이 아니라 '모르는 축'이다 → 통과시킨다.
        floor_ok &= (rk >= breadth_floor) | rk.isna()
    d["breadth_ok"] = floor_ok.astype(float)

    # ── 활성 축 조합별 분리 랭크
    combo = d.get("axis_flag", pd.Series("FULL", index=d.index)).astype(str) + \
        "|" + d["n_tp"].astype(str)
    key = d["ym"].astype(str) + "|" + combo
    eligible = (pd.to_numeric(d.get("veto_pass"), errors="coerce").fillna(1.0) > 0) & \
               (d["breadth_ok"] > 0) & d["E"].notna()
    Emask = d["E"].where(eligible)
    Umask = d["U"].where(eligible)
    d["E_rank"] = Emask.groupby(key, observed=True).rank(pct=True)
    d["U_rank"] = Umask.groupby(key, observed=True).rank(pct=True)
    # U 를 통째로 못 구한 구간에서는 U 를 중립(0.5)으로 두되 그 사실을 표에 남긴다.
    u_missing = d["U_rank"].isna() & d["E_rank"].notna()
    d["U_rank"] = d["U_rank"].fillna(0.5)
    d["u_imputed"] = u_missing.astype(float)

    d["Signal"] = (d["E_rank"] * d["U_rank"]).where(eligible)
    d["Signal_rank"] = d["Signal"].groupby(d["ym"], observed=True).rank(pct=True)
    return d


def score_panel(P: pd.DataFrame, stage: str = "ALL", tp_mode: str = "clip",
                use_theta: bool = True, drop_tps: "Sequence[str]" = (),
                drop_axes: "Sequence[str]" = (),
                uaxes: "Optional[Sequence[str]]" = None,
                cv_thresh_pct: float = CV_DEST_COMMODITY_PCT,
                breadth_floor: float = BREADTH_FLOOR_PCT) -> pd.DataFrame:
    """L2 전체. R5 절제가 이 함수의 인자만 바꿔 반복 호출한다(백테스트 재실행 없이)."""
    tps = [t for t in STAGE_TPS.get(stage, XCB_TP_COLS) if t not in drop_tps]
    if drop_axes:
        tps = [t for t in tps if XCB_TP_AXIS[t] not in drop_axes]
    ua = list(uaxes) if uaxes is not None else STAGE_UAXES.get(stage, ["d1", "d2", "d3", "d4"])
    if "D" in drop_axes:
        ua = []
    vet = STAGE_VETOES.get(stage, list(VETO_HARD) + list(VETO_PARTIAL))

    d = make_cells(P)
    d = build_tps(d, tps, mode=tp_mode)
    d = apply_vetoes(d, vet, cv_thresh_pct=cv_thresh_pct)
    d = disable_axes(d)
    d = compose_signal(d, tps, ua, use_theta=use_theta, breadth_floor=breadth_floor)
    return d
