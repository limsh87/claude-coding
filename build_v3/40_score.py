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

# ★ 셀 랭크 진단 원장. '왜 이 센서가 0% 인가'에 답하기 위한 유일한 기록이다.
#   예전엔 입력이 통째로 비어 있어도, 표본 미달로 걸려도 결과가 똑같이 NaN 이라
#   L2 에서 'TP 커버리지 0.0%' 만 보이고 원인은 어디에도 남지 않았다.
CELL_RANK_DIAG: List[dict] = []


def _diag_name(name_or_series) -> str:
    if isinstance(name_or_series, str):
        return name_or_series
    return str(getattr(name_or_series, "name", None) or "<식>")


def report_cell_rank_diag(top: int = 24):
    """센서별 '관측 → 랭크 해결' 표. 어느 계단에서 해결됐는지까지 보여준다."""
    if not CELL_RANK_DIAG:
        return
    # ★ 예전엔 `if name in seen: continue` 로 **가장 먼저** append 된 것만 남겼다.
    #   CELL_RANK_DIAG 는 L0.CONTRACT → L0.SMOKE → L1 → L2 내내 비워지지 않으므로,
    #   L2.SCORE 표에 계약검정(a=400)·스모크(i_capex=2,245) 값이 그대로 찍히고 실제 FULL
    #   값은 한 줄도 안 나왔다. 사용자가 "2,245건 있는데 왜 TP 가 0이지" 로 오판한다.
    #   → 같은 이름은 **마지막 것**(=이번 단계의 것)을 남긴다. clear 는 호출부가 한다.
    seen, rows = set(), []
    for d in reversed(CELL_RANK_DIAG):
        if d["name"] in seen:
            continue
        seen.add(d["name"])
        lv = d["by_level"]
        rows.append([d["name"], f"{d['obs']:,}", f"{d['resolved']:,}",
                     " / ".join(f"{k[-2:] if k != 'cell' else '1단'}:{v:,}"
                                for k, v in lv.items() if v) or "—",
                     "입력 없음" if d["obs"] == 0 else
                     ("표본 미달" if d["resolved"] == 0 else "")])
    rows = list(reversed(rows))[:top]
    LOG.table(rows, ["센서", "유효관측", "랭크산출", "해결 단계", "비고"],
              ["l", "r", "r", "l", "l"],
              title="셀 랭크 진단 — '입력이 없어서'와 '표본이 모자라서'를 구별합니다")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 사다리가 실제로 밟혔는가 — **행 수가 아니라 랭크 해결 건수**로 판정한다 ★★
    #    build_cells_v3 의 사다리 표는 '셀당 행 수'를 센다. 그런데 cell_rank 의 게이트는
    #    **센서별 유효관측수**(transform("count"))다. 30행짜리 셀이라도 그 센서를 관측한
    #    종목이 3개면 1단은 못 밟고 아래로 내려간다.
    #    그래서 행 기준 표에는 '표본≥8 비율 88%' 처럼 건강하게 찍히는데, 실제로는
    #    랭크의 대부분이 4단(month|ALL|ALL = 전체시장)에서 해결되고 있을 수 있다.
    #    그 상태면 산업·규모 중립화는 **한 번도 일어나지 않은 것**이고, 정책효과가
    #    셀 내 공통충격으로 흡수된다는 이 전략의 전제(§8)가 통째로 깨진다.
    #    감지 장치가 셋인데 셋 다 행을 세고 있었으므로 절대 걸리지 않았다 — 그래서 여기서 센다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    agg: Dict[str, int] = {}
    for d in CELL_RANK_DIAG:
        for k, v in (d.get("by_level") or {}).items():
            agg[k] = agg.get(k, 0) + int(v)
    tot = sum(agg.values())
    if not tot:
        return
    _nm = {"cell": "1단 month|업종|규모", "cell_l2": "2단 month|업종|ALL",
           "cell_l3": "3단 month|업종군|ALL", "cell_l4": "4단 month|ALL|ALL(전체시장)"}
    LOG.table([[_nm.get(k, k), f"{agg.get(k, 0):,}", f"{100*agg.get(k, 0)/tot:.1f}%"]
               for k in CELL_LADDER_V3 if k in agg],
              ["실제 해결 단계", "랭크 산출 건수", "비중"], ["l", "r", "r"],
              title="셀 사다리 실효 사용률 — 행 수가 아니라 '센서별 유효관측' 기준")
    _flat = agg.get("cell_l4", 0) / tot
    if _flat > 0.5:
        LOG.warn(f"★ 셀 랭크의 {_flat:.0%}가 **전체시장(4단)** 에서 해결됐습니다 — 산업·규모 "
                 f"중립화가 사실상 일어나지 않았습니다. 스펙 §8 이 셀에 규모를 넣은 이유는 "
                 f"정부 지원제도가 기업 규모에 연동되므로 정책효과를 셀 내 공통충격으로 "
                 f"흡수시키기 위함인데, 전체시장 랭크로 떨어지면 그 흡수가 사라지고 "
                 f"규모효과·산업효과가 신호로 둔갑합니다. "
                 f"원인은 센서 커버리지 부족(Tier-2·직원현황 미수집)이지 셀 정의가 아닙니다 — "
                 f"CELL_MIN_N_V3 를 낮추지 마시고 수집을 채우세요.")


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
        # ★ 입력이 통째로 비었는지, 임계치에 걸려 NaN 이 됐는지는 하류에서 구별할 수 없다.
        #   둘 다 조용히 NaN 이라 'TP 커버리지 0%' 만 남고 원인이 사라진다 → 여기서 남긴다.
        CELL_RANK_DIAG.append({"name": _diag_name(name_or_series), "obs": 0,
                               "resolved": 0, "by_level": {}})
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    _by_lvl = {}
    for lvl in CELL_LADDER_V3:
        if lvl not in P.columns:
            continue
        need = out.isna() & v.notna()
        if not need.any():
            break
        r, n = _rank_in(v, P[lvl], min_n)
        got = r.where(n >= min_n)
        _by_lvl[lvl] = int((need & got.notna()).sum())
        out = out.where(~need, got)
    CELL_RANK_DIAG.append({"name": _diag_name(name_or_series), "obs": int(v.notna().sum()),
                           "resolved": int(out.notna().sum()), "by_level": _by_lvl})
    return out.astype("float32")


def cell_z(P: pd.DataFrame, name_or_series, min_n: int = None) -> pd.Series:
    """셀 내 z-score (winsorize ±2σ → z). U축 합성에만 쓴다 — TP 는 랭크 기반이다."""
    min_n = CELL_MIN_N_V3 if min_n is None else min_n
    v = _clean_num(P, name_or_series)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = pd.Series(np.nan, index=P.index, dtype="float64")
    for lvl in CELL_LADDER_V3:
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


# ★ 센서 → 그 센서를 만들려면 무엇을 받아야 하는가. 결손 진단 로그가 원인을 지목할 때 쓴다.
#   이 표가 없어서 '증거층 8개 전부 0%' 라는 결과만 보이고 "Tier-2 를 안 받아서" 라는
#   한 줄짜리 원인이 27분 뒤 RuntimeError 로만 드러났다.
SENSOR_SOURCE_HINT = {
    "i_sales":    "DART Tier-1 주요계정(매출액)",
    "i_turn":     "DART Tier-2 전체재무제표(재고·매출채권·매출원가)",
    "i_accr":     "DART Tier-2 현금흐름표(영업활동현금흐름)",
    "i_capex":    "DART Tier-2 현금흐름표(유형자산 취득)",
    "i_roic":     "DART Tier-2 재무상태표(재고·매출채권·매입채무·유형/무형자산)",
    "p_payout":   "DART Tier-2 현금흐름표(배당금지급·자기주식취득·영업CF)",
    "p_invest":   "DART Tier-2 현금흐름표(유형자산취득·연구개발비)",
    "acq_size":   "DART Tier-2 현금흐름표(자기주식 취득)",
    "p_cancel":   "DART 공시목록(자기주식 소각)",
    "nl_emp":     "DART 직원현황 empSttus (알파 원천)",
    "nl_premium": "DART 직원현황 empSttus (연간급여총액 · 한계임금)",
    "nl_vapp":    "DART 직원현황 empSttus + Tier-1 손익",
    "nl_regular": "DART 직원현황 empSttus (정규직 수)",
}

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


def build_tps(P: pd.DataFrame, disabled: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """TP 조립. disabled 에 든 TP 는 만들되 **전량 결측으로 비활성화**한다.

    ★★ 왜 '만들되 비활성화' 인가 — CANARY 판정이 소비되지 않던 문제 ★★
      CANARY 는 K8(연간급여총액 기재율)이 기준 미달이면 "임금프리미엄 계산 불가"
      라고 판정하고, K3 은 커버리지 미달 계정 목록(weak_accounts)을 남긴다.
      그런데 그 verdict 는 ctx["canary"] 에 저장만 되고 **읽는 코드가 한 줄도 없었다.**
      즉 "FAIL 시 조치" 열에 적힌 처방이 실행되지 않는 약속이었고, 미달인 원천으로
      만든 TP 가 정상 TP 와 나란히 증거층 평균에 들어갔다.
      → 비활성 TP 는 컬럼을 남기되 값을 비운다. 그래야 하류의 '살아 있는 TP' 판정이
        자동으로 제외하고, 진단표에는 '왜 죽었는지'가 그대로 남는다.
    """
    # ★ 이 단계의 진단만 표에 나오게 한다. 전역 리스트라 계약검정·스모크 값이 누적된다.
    CELL_RANK_DIAG.clear()
    P = P.copy()
    disabled = set(disabled or [])
    if disabled:
        LOG.warn(f"CANARY 판정에 따라 TP {sorted(disabled)} 를 비활성화합니다 — "
                 f"원천 기재율이 기준에 미달해 그 TP 의 값을 신뢰할 수 없습니다. "
                 f"컬럼은 남기되 값을 비워 증거층에서 자동 제외되게 합니다"
                 f"(0 으로 채우면 '대가를 치르지 않았다'는 거짓 주장이 됩니다).")
    rows = []
    for name, a, b, desc in TP_DEFS:
        P[name] = (pd.Series(np.nan, index=P.index, dtype="float32") if name in disabled
                   else tp(P, a, b))
        cov = float(P[name].notna().mean()) if len(P) else 0.0
        pos = float((P[name] > 0).mean()) if len(P) else 0.0
        rows.append([name, f"{a} × {b}", _trunc(desc, 30), f"{cov*100:.1f}%", f"{pos*100:.1f}%"])
    LOG.table(rows, ["TP", "구성 (개선 × 대가회피)", "의미", "관측 커버리지", "양(>0) 비율"],
              ["l", "l", "l", "r", "r"], title="트레이드오프 쌍 (clip×clip · 음수 불가)")
    report_cell_rank_diag()
    dead = [n for n, *_ in TP_DEFS if P[n].notna().sum() == 0]
    if dead:
        # ★ 어느 '다리'가 죽었는지, 그 다리가 어느 원천을 요구하는지까지 지목한다.
        #   예전엔 죽은 TP 이름만 나열해서, 8개가 전부 죽었을 때조차 원인이 안 보였다.
        #   실제로 그 상태로 27분을 더 돌다가 백테스트 직전에 RuntimeError 로 죽었다.
        drows = []
        for n, a, b, _d in TP_DEFS:
            if n not in dead:
                continue
            legs = []
            for leg in (a, b):
                obs = int(col(P, leg).notna().sum()) if leg in P.columns else 0
                legs.append(f"{leg}={obs:,}")
            culprit = [leg for leg in (a, b)
                       if leg not in P.columns or col(P, leg).notna().sum() == 0]
            drows.append([n, " · ".join(legs),
                          ", ".join(culprit) or "둘 다 있으나 겹치는 행이 없음",
                          " / ".join(sorted({SENSOR_SOURCE_HINT.get(c, "?") for c in culprit}))])
        LOG.table(drows, ["죽은 TP", "다리별 유효관측", "비어 있는 다리", "그 다리가 요구하는 원천"],
                  ["l", "l", "l", "l"],
                  title=f"증거층 결손 진단 — {len(dead)}/{len(TP_DEFS)}개 TP 가 관측 0")
        LOG.warn(f"관측이 한 건도 없는 TP: {dead} — 위 표의 '요구하는 원천'을 먼저 확보하세요. "
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
            # ★★ 90일 창은 '패널 행 3개'가 아니라 '달력 3개월'이어야 한다 ★★
            #   이 패널은 U-MID 대역으로 이미 잘려 있어 종목별 행이 월 연속이 아니다.
            #   rolling(3) 을 쓰면 (a) 유동성이 출렁여 중간 달이 빠진 종목에서 창이 실제
            #   6~9개월로 늘어나 멀쩡한 종목을 계속 제외하고, (b) 공시가 난 달에 패널 행이
            #   없으면 그 이벤트는 아예 사라져 거부권이 발동조차 하지 않는다.
            #   → 이벤트 날짜에서 직접 창을 펼쳐 패널 행 유무와 무관하게 만든다.
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            ev = d[["corp_code", "month"]].dropna().drop_duplicates()
            ev["corp_code"] = ev["corp_code"].astype(str)
            win = pd.concat([ev.assign(month=ev["month"] + pd.offsets.MonthEnd(k))
                             for k in range(3)], ignore_index=True)   # 공시 당월 + 2개월
            win = win.drop_duplicates()
            win["dilution_win"] = 1.0
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(win, on=["corp_code", "month"], how="left")
            P["V3"] = np.where(P["dilution_win"].fillna(0.0) > 0, 0.0, 1.0)
            P = P.drop(columns=["dilution_win"], errors="ignore")

    # V5 — 자본잠식/관리종목
    P["V5"] = np.where(col(P, "equity").le(0).fillna(False), 0.0, 1.0)
    adm = ctx.get("administrative")
    if adm is not None and len(adm) and "code" in adm.columns:
        P["V5"] = np.where(P["code"].isin(set(adm["code"].dropna())), 0.0, P["V5"])
    else:
        # ★★ 선언한 거부권이 배선되지 않은 채 조용히 통과하고 있었다 ★★
        #   VETO_DEFS_V3 는 V5 를 '자본잠식 · 관리종목 · 감사의견 비적정' 이라고 선언하는데,
        #   ctx["administrative"] 를 채우는 코드가 저장소 어디에도 없다. 즉 실제로 걸리는
        #   것은 자본잠식(equity<=0) 하나뿐이고, **관리종목·감사의견 비적정은 한 번도
        #   거부되지 않았다.** 그런데 거부권 발동표에는 V5 가 정상 항목으로 찍히므로
        #   읽는 사람은 세 다리가 모두 작동한다고 믿는다 — 조용히 성과를 부풀리는 쪽이다.
        #   (관리종목은 폭락 직전 구간이 많아, 빠지지 않으면 손실이 그대로 들어온다)
        LOG.warn("V5 거부권의 '관리종목·감사의견 비적정' 다리가 배선되지 않았습니다 "
                 "— 실제로 걸리는 것은 자본잠식(자본총계≤0) 하나뿐입니다. "
                 "관리종목 목록이 없으면 그 종목들이 유니버스에 그대로 남아 성과가 "
                 "**과대평가**될 수 있습니다. 아래 거부권 표의 V5 수치를 그렇게 읽으세요.")

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
              use_u: bool = True, use_veto: bool = True,
              min_arms: int = None) -> Dict[str, pd.Series]:
    """주어진 TP 집합 하나로 E → Signal → Signal_rank 를 만든다.

    Signal = rank_pct(E) × rank_pct(U) × ∏V        (스펙 §8)

    min_tp:   관측된 TP 가 이보다 적으면 제외(FLOOR). 스펙에 없는 우리 쪽 안전장치이므로
              R5 절제검사에서 이 경계값의 민감도를 반드시 함께 출력한다.
    min_arms: 증거층으로 인정할 최소 TP **개수**. 기본값은 MIN_TP_ARMS(=2) 이고,
              본선이 단일 팩터로 조용히 퇴화하는 것을 막는 장치다.

      ★★ 왜 파라미터가 되어야 하는가 (7회차에서 이 전략의 존재이유가 죽은 자리) ★★
        R2-N 킬게이트는 설계상 **단일 센서 팔**(A: nl_emp 단독, B: nl_premium 단독)을
        만들어 트레이드오프 팔(C)과 비교한다. 단일 팔인 것이 검정의 목적 그 자체다.
        그런데 이 함수가 MIN_TP_ARMS 를 전역 상수로 강제하고 있어서,
        R2-N 이 A 팔을 만들려는 순간 "TP 가 1개뿐입니다" 로 RuntimeError 가 났다.
        그래서 이 파일의 존재 이유인 검정이 **한 번도 실행되지 못했다.**
        본선의 안전장치가 검정을 죽인 것이다 — 안전장치는 호출자가 의도를 말할 수
        있어야 한다. 본선은 기본값(2)을 그대로 쓰고, 단일팔 비교만 1 을 명시한다.
    """
    tp_cols = [c for c in tp_cols if c in P.columns]
    min_tp = MIN_TP_OBSERVED if min_tp is None else min_tp
    min_arms = MIN_TP_ARMS if min_arms is None else max(1, int(min_arms))
    if len(tp_cols) < min_arms:
        # ★ 예전 메시지는 사실을 잘못 말했다 — "컬럼이 하나도 없습니다" 라고 했지만
        #   컬럼 8개는 전부 존재했고, 전량 NaN 이라 호출자가 직전 줄에서 걸러낸 것이었다.
        #   그래서 사용자는 있지도 않은 컬럼 생성 버그를 찾게 됐다. 원인을 지목해서 말한다.
        need = sorted({SENSOR_SOURCE_HINT.get(leg, leg)
                       for n, a, b, _ in TP_DEFS if n not in tp_cols for leg in (a, b)
                       if leg not in P.columns or col(P, leg).notna().sum() == 0})
        # ★ 처방은 **이번 실행에서 실제로 일어난 일**을 근거로 말해야 한다.
        #   예전 메시지는 무조건 'DART_FS_MAX_CALLS 가 0 이 아닌지 확인하세요' 라고 했는데,
        #   5차 실행에서 그 값은 3,667 이었고 진짜 원인은 서버가 첫 호출에서 거부한 것이었다.
        #   원인과 어긋난 처방은 사용자를 엉뚱한 곳으로 보낸다.
        _halt = None
        try:
            _halt = dart_halt_reason()
        except Exception:                                           # noqa
            _halt = None
        if _halt:
            raise RuntimeError(
                f"증거층으로 쓸 수 있는 TP 가 {len(tp_cols)}개뿐입니다(최소 {min_arms}개 필요).\n"
                f"  원인은 **수집 설정이 아니라 자원**입니다 — {_halt}\n"
                f"  · 살아 있는 TP : {tp_cols or '없음'}\n"
                f"  · 이번 실행에서 채우지 못한 원천 :"
                f"{chr(10) + '      - ' + (chr(10) + '      - ').join(need) if need else ' 판별 불가'}\n"
                f"  처방:\n"
                f"    ① KST 자정 이후 재실행하세요. 캐시는 append-only 라 정확히 이어받습니다.\n"
                f"    ② 같은 DART 키로 다른 전략을 함께 돌리셨다면 한도를 나눠 쓴 것입니다.\n"
                f"       한도는 **키 단위**지 전략 단위가 아닙니다.\n"
                f"    ③ DART_API_KEYS 에 키를 추가하면 하루 한도가 키 개수만큼 곱해집니다\n"
                f"       (opendart.fss.or.kr 에서 무료·즉시 발급).\n"
                f"    설정을 바꾸지 마세요 — 이번 실행의 설정에는 문제가 없었습니다.")
        raise RuntimeError(
            f"증거층으로 쓸 수 있는 TP 가 {len(tp_cols)}개뿐입니다(최소 {min_arms}개 필요). "
            f"컬럼은 만들어졌지만 관측이 0이라 제외됐습니다 — 계산 버그가 아니라 원천 결손입니다.\n"
            f"  · 살아 있는 TP : {tp_cols or '없음'}\n"
            f"  · 비어 있는 원천 : {chr(10) + '      - ' + (chr(10) + '      - ').join(need) if need else '판별 불가'}\n"
            f"  처방:\n"
            f"    ① 'DART Tier-2' 가 목록에 있으면 DART_FS_MAX_CALLS 가 0 이 아닌지 확인하세요.\n"
            f"       Tier-1(주요계정)에는 현금흐름표가 통째로 없어 CORE-D 5개 TP 가 전부 죽습니다.\n"
            f"    ② 'empSttus' 가 목록에 있으면 직원현황 수집이 0건이었다는 뜻입니다.\n"
            f"       위 L1.EMP 로그에서 '신규 확보 N/M건' 을 확인하세요.\n"
            f"    ③ 연속된 회계연도가 모자라면 12개월 차분 센서가 전부 죽습니다 —\n"
            f"       Tier-2 는 **회사 우선**으로 받으므로 재실행할수록 완성된 회사가 늘어납니다.\n"
            f"    캐시는 append-only 라 재실행하면 정확히 이어받습니다 — 처음부터 다시 받지 않습니다.")
    if len(tp_cols) < min_tp:
        # ★ FLOOR = n_obs >= min(min_tp, len(tp_cols)) 이므로, 살아 있는 TP 가 min_tp 보다
        #   적으면 문턱이 자동으로 낮아져 '증거 없이도 통과' 하게 된다. 조용히 넘기지 않는다.
        LOG.warn(f"살아 있는 TP 가 {len(tp_cols)}개로 MIN_TP_OBSERVED={min_tp} 보다 적습니다 — "
                 f"최소 TP 조건이 {len(tp_cols)}개로 자동 완화됩니다. 즉 이번 실행의 종목 선정은 "
                 f"트레이드오프 증거가 아니라 사실상 단일 축에 의존합니다. 결과 해석에 반드시 반영하세요.")
    T = P[tp_cols].astype("float64")
    n_obs = T.notna().sum(axis=1)
    E_raw = T.mean(axis=1, skipna=True)                       # 결측 제외 동일가중 (C7)
    # ★ 이름 없는 Series 를 cell_rank 에 넘기면 진단표에 '<식>' 으로 찍혀 정체를 알 수 없다.
    E_raw.name = "E_raw(증거층 평균)"
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
