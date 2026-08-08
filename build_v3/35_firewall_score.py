

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  S1_FIREWALL (§7) · 거부권 (§9) · 셀 정규화 · TP 조립 · 신호 합성                      ║
# ║                                                                                          ║
# ║  이 전략의 본체는 방화벽이다. 증거층(E)은 2개 TP 로 최소화한다 —                           ║
# ║  U-MICRO 는 컨센서스·수급 데이터가 구조적으로 얇아 신호를 5~6개 욱여넣으면                 ║
# ║  "빈 축이 없을 것"이라는 하한선 조건에서 유니버스가 붕괴하기 때문이다.                     ║
# ║                                                                                          ║
# ║  ★ 원칙 2: TP 는 clip(z,0) × clip(z,0). 절대 z × z 가 아니다.                              ║
# ║    z×z 는 '매출 급감 + 회전 악화'(둘 다 음수)에 최고점을 준다 — 부호 버그다.                ║
# ║  ★ 원칙 3: 셀 정규화는 groupby().rank(pct=True) + transform("size"). groupby.apply 금지.  ║
# ║  ★ 원칙 7: 거부권은 이진·곱·상쇄 불가. 연속화하면 방화벽이 새는 통로가 생긴다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CELL_MICRO = ["date", "ind_major"]        # C14-a. size_bucket 없음 (문서화용 상수)
MICRO_MIN_CELL_N = 20                     # C14-b

E_SENSORS = ["i_sales", "i_turn", "i_accr"]
TP_DEFS = [("TP_I2", "i_sales", "i_turn"), ("TP_I4", "i_sales", "i_accr")]


def cell_rank_micro(P: pd.DataFrame, name_or_series, min_n: int = MICRO_MIN_CELL_N) -> pd.Series:
    """셀 내 백분위 랭크 [0,1]. 셀이 작으면 상위 업종 → 전체 시장 순으로 폴백한다(C14-b).

    구현은 groupby().rank(pct=True) + transform("size") 다 (원칙 3).
    groupby.apply 는 셀 수만큼 파이썬 호출이 발생해 수십 배 느리다.
    """
    return xsec_rank_pct_l(P, name_or_series, min_n=min_n)


def _cached_cell_rank(P: pd.DataFrame, name: str, cache: dict) -> pd.Series:
    """같은 컬럼의 셀 랭크를 한 번만 계산한다.

    i_sales 는 TP_I2·TP_I4 두 쌍의 공통 축이라 매번 두 번 계산됐고, value_rank 는
    조항 마스크와 s1_firewall 에서 최대 15회까지 중복 계산됐다. 랭크 1회는 셀 사다리
    3단계 × groupby-rank 이므로 중복이 그대로 벽시계 시간이 된다.
    """
    if name not in cache:
        cache[name] = cell_rank_micro(P, name)
    return cache[name]


def tp_micro(P: pd.DataFrame, a: str, b: str, _cache: Optional[dict] = None) -> pd.Series:
    """트레이드오프 쌍 = clip(랭크z, 0) × clip(랭크z, 0).

    랭크 백분위에서 0.5 를 빼 [-0.5, +0.5] 의 z 대용을 만들고, 음수는 0 으로 자른다.
    → '개선이 있었고, 그 대가도 치르지 않았다'는 사분면에서만 점수가 난다.
    ★ za*zb (부호 그대로 곱하기) 금지 — 저-저 사분면이 최고점을 받는다.
    한쪽이 결측이면 결과도 결측이다(0 으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다).
    """
    _cache = {} if _cache is None else _cache
    ra = _cached_cell_rank(P, a, _cache)
    rb = _cached_cell_rank(P, b, _cache)
    za = ra - 0.5
    zb = rb - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    return pd.Series(out, index=P.index).where(ra.notna() & rb.notna()).astype("float32")


def value_rank_micro(P: pd.DataFrame) -> pd.Series:
    """딥밸류 랭크. 0 에 가까울수록 싸다 (방화벽은 하위 30% 만 통과시킨다).

    ★ 이익수익률(E/P)·순자산수익률(B/P)의 셀 내 랭크를 평균한 뒤 뒤집는다.
      배수(PER/PBR)로 랭크하면 적자·자본잠식에서 정의되지 않아 센티넬이 필요하고,
      그 센티넬이 셀의 유효 관측수를 무너뜨려 셀 전체를 '판정 불가'로 만든다.
      수익률 형태는 적자·자본잠식이 자연스럽게 음수가 되어 '비싼 쪽'으로 정렬된다.
    ★ 한쪽(E/P 또는 B/P)만 관측되면 그 한쪽으로 판정한다. 둘 다 없을 때만 결측이다.
    """
    P = P.copy()
    P["_r_ep"] = cell_rank_micro(P, "ep")
    P["_r_bp"] = cell_rank_micro(P, "bp")
    r = nanmean_cols(P, ["_r_ep", "_r_bp"])            # 높을수록 싸다
    return (1.0 - pd.to_numeric(r, errors="coerce")).astype("float32")


def sensor_availability(P: pd.DataFrame) -> Tuple[List[str], pd.DataFrame]:
    """C14-c/d — 센서 결측률 > 25% 면 증거층에서 자동 제외한다. 0 으로 채우지 않는다.

    반환: (활성 TP 목록, 진단표)
    ★ 결측률은 'U-MICRO 이면서 가격이 있는 행' 기준으로 잰다. 전체 패널로 재면
      애초에 유니버스 밖인 행까지 분모에 들어가 결측률이 부풀려진다.
    """
    base = P[P.get("u_micro", pd.Series(True, index=P.index)).astype(bool) &
             P["close"].notna()] if "close" in P.columns else P
    if len(base) == 0:
        base = P
    rows, dead = [], set()
    for s in E_SENSORS:
        miss = float(col(base, s).isna().mean()) if len(base) else 1.0
        ok = miss <= RESEARCH_MAX_MISSING_RATE
        if not ok:
            dead.add(s)
        rows.append([s, f"{100*miss:.1f}%", f"{100*RESEARCH_MAX_MISSING_RATE:.0f}%",
                     "활성" if ok else "제외(C14-c)"])
    active_tp = [(tid, a, b) for tid, a, b in TP_DEFS if a not in dead and b not in dead]
    rows.append(["활성 TP", f"{len(active_tp)}개", "2개 이상",
                 "정상" if len(active_tp) >= 2 else "중단(C14-d)"])
    T = pd.DataFrame(rows, columns=["센서", "결측률", "임계", "판정"])
    LOG.table(T.values.tolist(), list(T.columns), ["l", "r", "r", "c"],
              title="센서 가용성 (C14-c/d) — 결측을 0 으로 채우지 않고 축을 통째로 뺀다")
    LOG.info("※ i_sales 는 TP_I2·TP_I4 두 쌍의 공통 축입니다. i_sales 가 제외되면 활성 TP 는 "
             "구조적으로 0개가 되어 반드시 중단됩니다(§8 의 TP 정의가 그렇게 생겼습니다). "
             "위 '센서 정의 선택' 표에서 어떤 정의가 채택됐는지 함께 보십시오.")
    if len(active_tp) < 2:
        _msg = (f"활성 TP 가 {len(active_tp)}개로 2개 미만입니다(C14-d). 증거층을 구성할 수 없습니다. "
                f"임계를 낮춰 통과시키지 마십시오 — 결측률이 높다는 것은 U-MICRO 구간에서 해당 "
                f"재무항목이 실제로 공시되지 않는다는 뜻이고, 0 으로 채우면 없는 근거를 만듭니다.")
        # ★ 합성 스모크에서는 죽이지 않는다(형식 확인이 목적). 실데이터에서만 발동한다.
        if STOP_ON_KILL_CRITERIA and bool(globals().get("_KILL_ARMED", True)):
            raise KillCriteria(_msg)
        LOG.warn("[킬 비무장] " + _msg + " — 예행연습이므로 전 TP 를 형식상 활성으로 두고 "
                 "출력 경로만 확인합니다.")
        return [t[0] for t in TP_DEFS], T
    return [t[0] for t in active_tp], T


def build_evidence(P: pd.DataFrame, active_tp: Sequence[str]) -> pd.DataFrame:
    """TP 조립 → 증거층 E. §9."""
    P = P.copy()
    made = []
    _rc: dict = {}                      # i_sales 는 두 TP 의 공통 축 — 한 번만 랭크한다
    for tid, a, b in TP_DEFS:
        if tid not in active_tp:
            P[tid] = np.nan
            continue
        P[tid] = tp_micro(P, a, b, _cache=_rc)
        made.append(tid)
    P["E_micro"] = nanmean_cols(P, made) if made else np.nan

    # ── U 층 (§9) ──────────────────────────────────────────────────────────────────────
    #   컨센서스가 없으므로 후행 이익 기반 반영도만 쓴다. 높을수록 '아직 반영 안 됨'.
    P["u_base_rank"] = cell_rank_micro(P, "u_underreflect")
    u_cols = ["u_base_rank"]
    miss_u = float(col(P, "u_underreflect").isna().mean()) if len(P) else 1.0
    if miss_u > RESEARCH_MAX_MISSING_RATE:
        LOG.warn(f"U층 기본신호 결측률 {100*miss_u:.0f}% > {100*RESEARCH_MAX_MISSING_RATE:.0f}% — "
                 f"C14-c 에 따라 U층을 중립(1.0)으로 두고 D 구성은 사실상 C 와 같아집니다. "
                 f"이 사실은 R2-M 표에 그대로 드러납니다.")
        u_cols = []

    # 애널리스트 목표주가 리비전(같은 애널리스트 기준)이 충분히 커버되면 U층에 더한다.
    #   ★ 커버리지가 얇으면 자동 제외한다(C14-c). U-MICRO 에서는 대개 제외된다 — 정상이다.
    if "u_revision_rank" in P.columns:
        miss_r = float(col(P, "u_revision_rank").isna().mean())
        if miss_r <= RESEARCH_MAX_MISSING_RATE:
            u_cols.append("u_revision_rank")
            LOG.ok(f"애널리스트 목표주가 리비전을 U층에 결합합니다 (결측률 {100*miss_r:.0f}%).")
        else:
            LOG.info(f"애널리스트 리비전 결측률 {100*miss_r:.0f}% > "
                     f"{100*RESEARCH_MAX_MISSING_RATE:.0f}% — C14-c 로 U층에서 제외합니다. "
                     f"U-MICRO 는 커버리지가 구조적으로 얇아 통상적인 결과입니다.")
    P["U_micro"] = nanmean_cols(P, u_cols) if u_cols else pd.Series(1.0, index=P.index)
    LOG.ok(f"증거층 조립 — 활성 TP {made} · E 유효 {int(P['E_micro'].notna().sum()):,}행 · "
           f"U 유효 {int(P['U_micro'].notna().sum()):,}행")
    return P


# ── S1_FIREWALL (§7) ────────────────────────────────────────────────────────────────────────
FW_CLAUSES = ["capital", "watchlist", "audit", "halt", "weak_cf", "liquidity", "deepvalue"]


def firewall_clause_masks(P: pd.DataFrame, active: Dict[str, bool]
                          ) -> "OrderedDict[str, Tuple[str, Optional[pd.Series], bool, str]]":
    """조항 → (표시명, 위반 마스크, 활성여부, 비고).

    ★ '데이터가 없어서 판단 불가'와 '판단해서 통과'를 구분한다.
      전자를 통과로 처리하면 방화벽이 새고, 배제로 처리하면 유니버스가 근거 없이 붕괴한다.
      → 소스 자체가 없으면 조항을 통째로 비활성화하고(K6) 표에 남긴다.
        소스는 있는데 특정 종목만 결측이면 그 종목은 '위반 아님'으로 둔다(근거 없는 배제 금지).
    """
    ci = col(P, "capital_impairment")
    wl, al = col(P, "is_watchlist"), col(P, "is_alert")
    ab = col(P, "audit_bad")
    th = col(P, "is_trading_halted")
    streak, icov = col(P, "op_cf_neg_streak"), col(P, "interest_coverage")
    adv = col(P, "adv20")
    # ★ 이 함수는 R5-M 절제분석에서 조항 수만큼(최대 15회) 다시 불린다. 매번 E/P·B/P 의
    #   셀 사다리 랭크를 새로 돌면 U-MICRO 패널 전체를 수십 번 훑게 된다 → 패널에 캐시한다.
    if "_value_rank" in P.columns:
        vr = pd.to_numeric(P["_value_rank"], errors="coerce")
    else:
        vr = value_rank_micro(P)
        try:
            P["_value_rank"] = vr        # 호출자 프레임에 남겨 재계산을 막는다
        except Exception:
            pass
    # ★ 딥밸류 조항은 '밸류 판정 불가(vr 결측)'도 배제한다 — 정책으로는 방어적이지만,
    #   vr 결측의 대부분은 **시총 미상**이고 시총 미상의 대부분은 상장폐지 종목이다.
    #   그러면 방화벽을 켠 구성(A·C·D)만 폐지 종목을 구조적으로 못 사고, 끈 구성(B)과
    #   동일가중 벤치마크만 -100% 를 먹는다 → R2-M ①('방화벽이 알파인가 손실회피인가')이
    #   전략이 아니라 **데이터 커버리지 격차**를 측정하게 된다. 그래서 비율을 표에 남긴다.
    _vr_na = float(vr.isna().mean()) if len(vr) else 0.0
    if _vr_na > 0.05:
        LOG.warn(f"밸류 판정 불가(시총·재무 결측) {100*_vr_na:.1f}% — 딥밸류 조항이 이 행들을 "
                 f"배제합니다. 이 비율이 크면 A/C/D 만 상장폐지 종목을 피하게 되어 "
                 f"R2-M ① 판정이 전략이 아니라 커버리지 격차를 측정합니다. "
                 f"KRX_OPENAPI_KEY 를 넣어 시총 커버리지를 올리면 사라지는 문제입니다.")

    C: "OrderedDict[str, Tuple[str, Optional[pd.Series], bool, str]]" = OrderedDict()
    C["capital"] = ("자본잠식 (자본총계<자본금 또는 ≤0)", ci > 0, bool(ci.notna().any()),
                    "재무 결측 종목은 '위반 아님'")
    C["watchlist"] = ("관리종목·투자주의환기", (wl > 0) | (al > 0),
                      bool(active.get("watchlist") or active.get("alert")), "")
    C["audit"] = ("감사의견 비적정", ab > 0, bool(active.get("audit")),
                  "적정 여부를 직접 확인할 API 가 없어 '비적정 증거'로만 배제")
    C["halt"] = ("매매거래정지", th > 0,
                 bool(active.get("halt")) or bool(th.notna().any()), "")
    C["weak_cf"] = (f"영업CF {FW_OPCF_NEG_STREAK}분기 연속 음수 ∧ 이자보상배율<{FW_ICOV_MIN:g}",
                    (streak >= FW_OPCF_NEG_STREAK) & (icov < FW_ICOV_MIN),
                    bool(streak.notna().any()), "AND 조건 — 한쪽만으론 배제하지 않는다")
    C["liquidity"] = (f"20일 평균거래대금 < {UMICRO_MIN_ADV_KRW:,.0f}원",
                      adv < UMICRO_MIN_ADV_KRW, bool(adv.notna().any()), "")
    C["deepvalue"] = (f"딥밸류 아님 (PBR·PER 결합랭크 > {FW_VALUE_RANK_MAX:.0%})",
                      (vr > FW_VALUE_RANK_MAX) | (~vr.notna()), bool(vr.notna().any()),
                      "밸류 랭크 산출 불가 종목도 배제 — 딥밸류 '확인'이 진입 조건")
    return C


def s1_firewall(P: pd.DataFrame, active: Dict[str, bool],
                skip: Sequence[str] = (), quiet: bool = False
                ) -> Tuple[pd.Series, pd.DataFrame]:
    """방화벽 통과 = 1. 하나라도 위반하면 0.  skip 에 넣은 조항은 절제(R5-M)용으로 제외한다."""
    n = len(P)
    ok = pd.Series(True, index=P.index)
    rows = []
    for key, (name, bad, enabled, note) in firewall_clause_masks(P, active).items():
        if key in skip:
            rows.append([name, "절제됨", "-", "-", "R5-M 절제 검사"])
            continue
        if not enabled or bad is None:
            rows.append([name, "비활성", "-", "-", note or "소스 없음 → K6 규칙으로 조항 제외"])
            continue
        b = bad.fillna(False).astype(bool)
        before = int(ok.sum())
        ok &= ~b
        rows.append([name, "활성", f"{int(b.sum()):,}", f"{before-int(ok.sum()):,}", note])

    fw = ok.astype("int8")
    rows.append(["── 최종 통과", "", f"{n - int(fw.sum()):,}", f"{int(fw.sum()):,}",
                 f"통과율 {100*fw.mean() if n else 0:.1f}%"])
    T = pd.DataFrame(rows, columns=["방화벽 조항", "상태", "위반 행수", "신규 배제", "비고"])
    if not quiet:
        LOG.table(T.values.tolist(), list(T.columns), ["l", "c", "r", "r", "l"],
                  title="S1_FIREWALL 조항별 감쇠 (§7) — 어느 조항이 실제로 일하는지")
    return fw, T


# ── 거부권 (§9 · C6: 이진·곱·상쇄 불가) ────────────────────────────────────────────────────
def apply_vetoes_micro(P: pd.DataFrame, dis: Optional[pd.DataFrame]) -> pd.DataFrame:
    """V1/V2/V3/V6 를 이진 플래그로 만들고 곱한다. 연속값으로 만들지 않는다."""
    P = P.copy()

    # V1 — 밀어내기 (분기 프레임에서 이미 계산되어 as-of 로 실려 왔다)
    P["V1"] = np.where(col(P, "v1_pushout") > 0, 0.0, 1.0)
    # V2 — 이익-현금 괴리 3분기 연속
    P["V2"] = np.where(col(P, "v2_bad_3q") > 0, 0.0, 1.0)
    # V3 — 90일 내 대규모 희석성 조달
    P["V3"] = _veto_dilution(P, dis)
    # V6 — 유동성 하한 또는 거래정지
    thal = col(P, "is_trading_halted") > 0
    P["V6"] = np.where((col(P, "adv20") < UMICRO_MIN_ADV_KRW) | thal, 0.0, 1.0)

    P["VETO"] = P["V1"] * P["V2"] * P["V3"] * P["V6"]
    rows = []
    for v, desc in [("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출>1.5"),
                    ("V2", "순이익>0 ∧ 영업CF<0.5×순이익 3분기 연속"),
                    ("V3", f"{V3_DILUTION_DAYS}일 내 희석성 조달(유증/CB/BW)"),
                    ("V6", "유동성 하한 미달 또는 거래정지")]:
        n_bad = int((P[v] == 0).sum())
        rows.append([v, desc, f"{n_bad:,}", f"{100*n_bad/max(len(P),1):.2f}%"])
    rows.append(["VETO", "전 거부권 곱 (상쇄 불가)", f"{int((P['VETO'] == 0).sum()):,}",
                 f"{100*(P['VETO'] == 0).mean() if len(P) else 0:.2f}%"])
    LOG.table(rows, ["ID", "조건", "발동 행수", "비중"], ["c", "l", "r", "r"],
              title="거부권 발동 현황 (C6 — 이진·곱·상쇄 불가)")
    return P


def _veto_dilution(P: pd.DataFrame, dis: Optional[pd.DataFrame]) -> np.ndarray:
    """희석성 조달 거부권. 공시 기반이 1순위, 상장주식수 급증이 보강이다."""
    out = np.ones(len(P), dtype="float64")
    used = []

    if dis is not None and len(dis) and "event" in dis.columns:
        ev = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue"])].copy()
        if len(ev) and "corp_code" in ev.columns and "corp_code" in P.columns:
            ev["corp_code"] = ev["corp_code"].astype(str)
            ev = (ev.dropna(subset=["rcept_dt", "corp_code"])
                    .sort_values("rcept_dt", kind="stable")[["corp_code", "rcept_dt"]]
                    .rename(columns={"rcept_dt": "last_dilution"}))
            ev["_kd"] = ev["last_dilution"]
            L = P[["corp_code", "month"]].copy()
            L["corp_code"] = L["corp_code"].astype(str)
            L["_ord"] = np.arange(len(L))
            Lv = L.dropna(subset=["month"]).sort_values("month", kind="stable")
            try:
                M = pd.merge_asof(Lv, ev, left_on="month", right_on="_kd",
                                  by="corp_code", direction="backward")
                last = M.set_index("_ord")["last_dilution"].reindex(L["_ord"]).to_numpy()
                days = (P["month"].to_numpy().astype("datetime64[ns]")
                        - last.astype("datetime64[ns]")) / np.timedelta64(1, "D")
                hit = np.isfinite(days) & (days >= 0) & (days <= V3_DILUTION_DAYS)
                out = np.where(hit, 0.0, out)
                used.append(f"공시 {int(hit.sum()):,}행")
            except Exception as e:                                       # noqa
                LOG.warn(f"V3 희석성 조달 as-of 결합 실패({type(e).__name__}) — "
                         f"상장주식수 급증 보강만 사용합니다.")

    # 보강: 상장주식수 12개월 증가율이 임계를 넘으면 '대규모 희석'으로 본다.
    #       공시목록이 없거나(키 미입력) 공시명이 규정과 달라 못 잡힌 경우를 메운다.
    #       ★ shares_p12 는 전체 패널에서 미리 결합해 둔다(build_panel). 여기서 U-MICRO
    #         부분집합만으로 12개월 전 값을 찾으면 과거에 유니버스 밖이던 종목이 전부 결측이 된다.
    if "shares" in P.columns and "shares_p12" in P.columns:
        s_now, s_p12 = col(P, "shares"), col(P, "shares_p12")
        gr = safe_div(s_now - s_p12, s_p12.where(s_p12 > 0))
        hit2 = (gr > max(V3_DILUTION_PCT * 2, 0.20)).fillna(False).to_numpy()
        out = np.where(hit2, 0.0, out)
        used.append(f"주식수급증 {int(hit2.sum()):,}행")

    if used:
        LOG.debug(f"V3 희석성 조달 — {' · '.join(used)}")
    return out


# ── 신호 합성 (§9) ──────────────────────────────────────────────────────────────────────────
#   Signal = rank_pct(E) × rank_pct(U) × s1_firewall × V1 × V2 × V3 × V6
#   R2-M 4방 비교를 위해 구성요소를 켜고 끌 수 있게 만든다.
VARIANTS: Dict[str, Dict[str, bool]] = {
    "A": {"E": False, "U": False, "FW": True,  "V": True,   # 방화벽만
          "desc": "방화벽만 (E=1, U=1, V=방화벽+거부권)"},
    "B": {"E": True,  "U": False, "FW": False, "V": False,  # 증거층만
          "desc": "증거층만 (E=E_micro, U=1, V=∅)"},
    "C": {"E": True,  "U": False, "FW": True,  "V": True,   # 방화벽+증거층
          "desc": "방화벽+증거층 (E=E_micro, U=1, V=방화벽+거부권)"},
    "D": {"E": True,  "U": True,  "FW": True,  "V": True,   # 전체 = MICRO-FW
          "desc": "전체 MICRO-FW (E×U×방화벽×거부권)"},
}


def assemble_signal(P: pd.DataFrame, variant: str = "D") -> pd.DataFrame:
    """구성별 신호. 랭크는 '월 전체'에서 매긴다.

    ★ 셀별로 랭크를 나눠 매기면 자기 셀에 혼자인 종목이 무조건 1.0 을 받아 상위를 채운다.
      셀 정규화는 이미 E/U 안에서 끝났다. 선정은 월 전체를 한 줄로 세워서 한다.
    """
    cfg = VARIANTS[variant]
    P = P.copy()
    one = pd.Series(1.0, index=P.index)

    e = P.groupby("month", observed=True)["E_micro"].rank(pct=True) if cfg["E"] else one
    u = P.groupby("month", observed=True)["U_micro"].rank(pct=True) if cfg["U"] else one
    fw = col(P, "FW").fillna(0.0) if cfg["FW"] else one
    vt = col(P, "VETO").fillna(0.0) if cfg["V"] else one

    sig = pd.to_numeric(e, errors="coerce") * pd.to_numeric(u, errors="coerce") * fw * vt
    # E/U 를 쓰지 않는 구성(A)에서는 전 종목이 동점이 된다 → 유동성 순으로 안정적 타이브레이크.
    if not cfg["E"] and not cfg["U"]:
        tie = P.groupby("month", observed=True)["adv20"].rank(pct=True).fillna(0.0)
        # ★ 1e-6 을 곱해 [1.0, 1.000001] 로 밀어 넣으면 안 된다.
        #   float32 의 1.0 근방 간격은 1.19e-7 이라 1,000개의 서로 다른 타이값이
        #   9개 값으로 뭉개진다. 그러면 nlargest 가 한 뭉치에서 '종목코드 오름차순'으로
        #   25개를 집는다 — A 구성이 사실상 '번호가 작은 종목 25개'가 된다.
        #   A 는 R0b·R2-M 의 비교 기준이므로 판정 전체가 오염된다.
        #   → 배수를 [1,2] 로 벌리고 float64 로 유지한다. 순서는 동일하되 뭉개지지 않는다.
        sig = sig * (1.0 + tie)
    P["Signal"] = pd.to_numeric(sig, errors="coerce").astype("float64")
    P["Signal_rank"] = P.groupby("month", observed=True)["Signal"].rank(pct=True)

    # ★ 구성에서 뺀 층은 컬럼 자체를 중립화한다.
    #   백테스트의 보유 유지 판정은 P["FW"]/P["VETO"] 를 직접 읽는다. 신호식에서만 빼고
    #   컬럼을 그대로 두면, 'V=∅' 로 정의된 B 구성에서도 방화벽·거부권이 강제 청산을
    #   일으켜 실제로는 C 와 섞인 구성이 된다 → R2-M 비교가 정의대로 성립하지 않는다.
    if not cfg["FW"]:
        P["FW"] = 1
    if not cfg["V"]:
        P["VETO"] = 1.0
    n_live = int((P["Signal"] > 0).sum())
    LOG.info(f"[{variant}] {cfg['desc']} — 신호>0 {n_live:,}행 "
             f"(월평균 {n_live/max(P['month'].nunique(),1):,.0f}종목)")
    return P
