# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1 센서 — 원시값만. 정규화는 여기서 하지 않는다(전부 L2).                                  ║
# ║                                                                                             ║
# ║  A축 통관(월)   → 트리거   : 상태 변화를 최초 감지                                          ║
# ║  B축 회계(분기) → 사전확률 : 그 변화를 감당할 체질인가                                      ║
# ║  C축 자원(분기) → 사전확률 : 능력을 미리 갖췄는가                                           ║
# ║  D축 기대(일)   → 할인율   : 얼마나 남았는가                                                ║
# ║                                                                                             ║
# ║  ★ B·C 를 '확인'이 아니라 '사전확률'로 쓰기 때문에 대기시간이 0이다.                        ║
# ║    A 가 움직인 시점에 즉시 판정이 끝난다 — 통관의 40~90일 선행성을 반납하지 않는 유일한 배치.║
# ║    그래서 "K분기 연속 정렬" 같은 대기조건을 절대 넣지 않는다(원칙 10).                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 선진시장 = 미국 + EU + 일본 + 대만 (§6.1). 국가군 축약은 수집 단계에서 이미 끝나 있다.
ADVANCED_MARKETS = ("US", "EU", "JP", "TW", "DE")

# a2 롤링 OLS 창 길이(월). 36개월 = 경기 1주기 내에서 β 를 재추정한다.
A2_WINDOW = 36
# 잔차 평균을 낼 최근 개월수. §7.1 의 mean(ε[t-5:t]).
A2_RECENT = 6
# a5 신규 세번 판정: 이 개월수 연속으로 임계 이상이면 '신규 등장'.
A5_STREAK = 3
# a5 더미의 지수감쇠 반감기(월).
A5_DECAY_HALFLIFE = 6.0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  A축 — 통관 4센서
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def customs_hs_monthly(cx: pd.DataFrame) -> pd.DataFrame:
    """(hs, ym, country) 원장 → (hs, ym) 월 집계 + 목적지 분포 지표.

    입력 표준 컬럼: hs, ym(월말 Timestamp), country, exp_wgt(kg), exp_usd(USD)
                    (선택) imp_wgt, imp_usd — 투입원가지수 산출에 쓴다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "ym", "wgt", "usd", "unit_price",
                                     "hhi_dest", "adv_share", "n_dest"])
    d = cx.copy()
    d["hs"] = d["hs"].astype(str)
    d["ym"] = as_ts_series(d["ym"])
    for c in ("exp_wgt", "exp_usd"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce").fillna(0.0)
    d = d[d["ym"].notna()]

    # ── (hs, ym) 총계
    g = d.groupby(["hs", "ym"], observed=True, sort=False)
    tot = g.agg(wgt=("exp_wgt", "sum"), usd=("exp_usd", "sum"),
                n_dest=("country", "nunique")).reset_index()
    # 단가는 반드시 USD 기준. 원화 환산 금지 — 환율 변동이 단가 신호로 오인된다(§6.1).
    tot["unit_price"] = safe_div(tot["usd"], tot["wgt"])
    tot.loc[~(tot["wgt"] > 0), "unit_price"] = np.nan

    # ── 목적지 집중도 HHI (금액 기준). groupby.apply 금지 → transform 으로.
    d["_tot_usd"] = d.groupby(["hs", "ym"], observed=True)["exp_usd"].transform("sum")
    share = safe_div(d["exp_usd"], d["_tot_usd"])
    d["_sh2"] = share ** 2
    d["_adv"] = np.where(d["country"].astype(str).str.upper().isin(ADVANCED_MARKETS),
                         d["exp_usd"], 0.0)
    agg2 = d.groupby(["hs", "ym"], observed=True, sort=False).agg(
        hhi_dest=("_sh2", "sum"), adv_usd=("_adv", "sum")).reset_index()
    out = tot.merge(agg2, on=["hs", "ym"], how="left")
    out["adv_share"] = safe_div(out["adv_usd"], out["usd"])
    out = out.drop(columns=["adv_usd"])
    return out.sort_values(["hs", "ym"]).reset_index(drop=True)


def customs_cv_dest(cx: pd.DataFrame, min_share: float = 0.01,
                    min_dest: int = 3) -> pd.DataFrame:
    """§5.4 커모디티 판별 — 같은 HS 안에서 목적지 간 단가가 얼마나 흩어지는가.

    cv 낮음 → 어느 나라에 팔든 같은 값 = 국제 시세 종속 = 커모디티 → 단가 축(a2) 무효
    cv 높음 → 고객·스펙별 가격 차별화 여지 존재 → 단가 축 유효

    주관이 아니라 데이터로 판정한다. 판정 결과는 V10 부분거부권으로 이어진다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])
    d = cx.copy()
    d["hs"] = d["hs"].astype(str)
    d["ym"] = as_ts_series(d["ym"])
    d["exp_wgt"] = pd.to_numeric(d.get("exp_wgt"), errors="coerce")
    d["exp_usd"] = pd.to_numeric(d.get("exp_usd"), errors="coerce")
    d = d[(d["exp_wgt"] > 0) & (d["exp_usd"] > 0) & d["ym"].notna()].copy()
    if not len(d):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])

    # 미미한 목적지는 단가가 튄다(샘플 1건짜리 특수 선적). 비중 하한으로 걸러낸다.
    d["_tot"] = d.groupby(["hs", "ym"], observed=True)["exp_usd"].transform("sum")
    d = d[safe_div(d["exp_usd"], d["_tot"]) >= min_share].copy()
    d["up"] = d["exp_usd"] / d["exp_wgt"]

    g = d.groupby(["hs", "ym"], observed=True, sort=False)["up"]
    m = g.transform("mean")
    s = g.transform("std")
    d["_cv"] = safe_div(s, m)
    d["_n"] = g.transform("size")
    d = d[d["_n"] >= min_dest]
    if not len(d):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])
    # 월별 cv 의 시계열 중앙값 = 그 HS 의 구조적 가격차별화 여지
    per = d.drop_duplicates(["hs", "ym"])[["hs", "ym", "_cv"]]
    out = per.groupby("hs", observed=True)["_cv"].agg(
        cv_dest="median", cv_n="size").reset_index()
    return out


def customs_input_cost(cx: pd.DataFrame, hs_digits: int = 2) -> pd.DataFrame:
    """투입원가지수 — 같은 HS 章(2자리)의 **수입** 단가(USD/kg).

    왜 수입 단가인가: a2 회귀의 목적은 '원가 변동으로 설명되는 단가 변화'를 걷어내는 것이다.
    같은 장(章)의 수입 단가는 그 산업의 투입물 가격을 대리하며, 개별 수출기업의 가격결정력과는
    독립이다(내생성이 낮다). 수입 데이터가 없으면 전체 수출 단가 중앙값으로 폴백한다 —
    이 경우 원가 통제가 약해지므로 그 사실을 로그에 남긴다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs2", "ym", "input_cost"])
    d = cx.copy()
    d["ym"] = as_ts_series(d["ym"])
    d["hs2"] = d["hs"].astype(str).str.slice(0, hs_digits)
    has_imp = ("imp_usd" in d.columns) and ("imp_wgt" in d.columns) and \
              (pd.to_numeric(d["imp_wgt"], errors="coerce").fillna(0) > 0).any()
    if has_imp:
        d["_u"] = pd.to_numeric(d["imp_usd"], errors="coerce").fillna(0.0)
        d["_w"] = pd.to_numeric(d["imp_wgt"], errors="coerce").fillna(0.0)
        src = "수입단가(장별)"
    else:
        d["_u"] = pd.to_numeric(d["exp_usd"], errors="coerce").fillna(0.0)
        d["_w"] = pd.to_numeric(d["exp_wgt"], errors="coerce").fillna(0.0)
        src = "수출단가(장별) — 수입 데이터 없음, 원가통제 약화"
        LOG.warn("투입원가지수를 수입단가로 만들 수 없어 수출단가로 대체합니다. "
                 "a2 의 원가 통제(γ항)가 약해집니다 — R5 절제에서 기여를 확인하세요.")
    g = d.groupby(["hs2", "ym"], observed=True, sort=False).agg(
        _u=("_u", "sum"), _w=("_w", "sum")).reset_index()
    g["input_cost"] = safe_div(g["_u"], g["_w"])
    g.loc[~(g["_w"] > 0), "input_cost"] = np.nan
    LOG.debug(f"투입원가지수 소스: {src} · {g['hs2'].nunique()}개 장 × {g['ym'].nunique()}개월")
    return g[["hs2", "ym", "input_cost"]]


def _stack_long(P: pd.DataFrame, value: str) -> pd.DataFrame:
    """(hs × ym) 와이드 → (hs, ym, value) 롱. pandas 2/3 양쪽에서 같은 순서를 보장한다.

    `stack(future_stack=...)` 은 버전마다 기본값과 인자 유무가 달라 조용히 결측 처리와
    행 순서가 바뀐다. 여기서는 순서가 곧 정합성이므로 numpy 로 직접 편다.
    """
    vals = P.to_numpy(dtype=float)
    n_hs, n_ym = vals.shape
    return pd.DataFrame({
        "hs": np.repeat(np.asarray(P.index, dtype=object), n_ym),
        "ym": np.tile(pd.DatetimeIndex(P.columns).to_numpy(), n_hs),
        value: vals.reshape(-1),
    })


def customs_a2_residual(hsm: pd.DataFrame, cost: pd.DataFrame,
                        window: int = A2_WINDOW, recent: int = A2_RECENT) -> pd.DataFrame:
    """a2 — 수출단가 잔차. 36개월 롤링 OLS (적률 방식, 원칙 4).

        log(단가) = α + β·log(물량) + γ·log(투입원가) + ε

    정상 기업은 β<0 (많이 팔려면 깎아야 한다). ε 이 지속적으로 양(+)이면
    '물량이 늘었는데 예상만큼 안 깎였다' = 제약선이 이동했다.

    ★ 종목×시점 파이썬 루프 금지. (N_hs, T) 배치로 한 번에 푼다.
    """
    empty = pd.DataFrame(columns=["hs", "ym", "a2", "a2_beta", "a2_resid"])
    if hsm is None or not len(hsm):
        return empty
    d = hsm.copy()
    d["hs2"] = d["hs"].astype(str).str.slice(0, 2)
    if cost is not None and len(cost):
        d = d.merge(cost, on=["hs2", "ym"], how="left")
    else:
        d["input_cost"] = np.nan

    # 균일 격자로 피벗 — 롤링 창이 달을 건너뛰면 안 된다.
    yms = pd.DatetimeIndex(sorted(d["ym"].dropna().unique()))
    hss = pd.Index(sorted(d["hs"].astype(str).unique()), name="hs")
    if len(yms) < window or not len(hss):
        LOG.warn(f"a2: 관측 개월 {len(yms)} < 창 {window} — 단가 잔차를 산출할 수 없습니다.")
        return empty

    def _piv(col: str) -> np.ndarray:
        p = d.pivot_table(index="hs", columns="ym", values=col, aggfunc="mean")
        return p.reindex(index=hss, columns=yms).to_numpy(dtype=float)

    up = _piv("unit_price")
    qty = _piv("wgt")
    ic = _piv("input_cost")

    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log(np.where(up > 0, up, np.nan))
        lq = np.log(np.where(qty > 0, qty, np.nan))
        lc = np.log(np.where(ic > 0, ic, np.nan))
    # 투입원가가 통째로 없는 HS 는 그 항을 상수로 둔다(회귀가 죽지 않도록).
    lc = np.where(np.isfinite(lc), lc, 0.0)

    N, T = y.shape
    X = np.empty((N, T, 3), dtype=float)
    X[:, :, 0] = 1.0
    X[:, :, 1] = lq
    X[:, :, 2] = lc
    resid = rolling_ols_resid(y, X, window=window)          # (N, T)

    R = pd.DataFrame(resid, index=hss, columns=yms)
    # a2 = mean(ε[t-5:t]) / std(ε)   — 표준편차는 그 HS 의 전체 잔차 산포
    # ★ rolling(axis=1) 은 pandas 2 에서 폐기되고 3 에서 제거됐다. 전치해서 축을 세운다.
    mean_r = (R.T.rolling(recent, min_periods=max(2, recent // 2)).mean()).T
    # ★ 분모를 '전체 표본 잔차 표준편차'로 쓰면 **미래 잔차가 오늘의 a2 를 스케일링**한다.
    #   같은 잔차라도 훗날 변동성이 커질 HS 는 오늘 a2 가 작아진다 — 명백한 미래누수다.
    #   시점 t 까지만 쓰는 확장 표준편차로 바꾼다(최소 12개월 확보 후부터 산출).
    sd_exp = (R.T.expanding(min_periods=12).std()).T.replace(0.0, np.nan)
    a2 = mean_r.div(sd_exp)

    beta = rolling_ols_beta_last(y, X, window=window)        # (N, 3) — 진단카드용 β
    # 두 프레임은 index/columns 가 동일하므로 stack 순서가 일치한다.
    out = _stack_long(a2, "a2")
    out["a2_resid"] = _stack_long(R, "a2_resid")["a2_resid"].to_numpy()
    out = out.merge(pd.DataFrame({"hs": np.asarray(hss), "a2_beta": beta[:, 1]}),
                    on="hs", how="left")
    n_ok = int(np.isfinite(out["a2"]).sum())
    b_med = float(np.nanmedian(beta[:, 1]))
    LOG.ok(f"a2 단가잔차: HS {len(hss)}개 × {len(yms)}개월 → 유효 {n_ok:,}관측 "
           f"(β 중앙값 {b_med:+.3f} — 음수여야 정상)")
    # ★ 이 전략의 전제는 "정상 기업은 β<0 (많이 팔려면 깎아야 한다)"이다.
    #   β 중앙값이 0 근처거나 양수면 전제가 데이터에서 성립하지 않는 것이고,
    #   그러면 a2 는 '제약선 이동'이 아니라 잡음을 재는 지표가 된다. 조용히 넘기지 않는다.
    if not np.isfinite(b_med):
        LOG.warn("a2: β 를 추정하지 못했습니다 — 단가 축 판정을 신뢰할 수 없습니다.")
    elif b_med > -0.02:
        LOG.warn(
            f"a2: β 중앙값이 {b_med:+.3f} 로 음수가 아닙니다. 이 전략의 전제("
            f"'많이 팔려면 깎아야 한다')가 이 표본에서 성립하지 않습니다.\n"
            f"    가능한 원인 ① 중량 보고오차가 회귀변수에 실려 β 가 0 으로 끌려감"
            f"(errors-in-variables 감쇠) ② 투입원가지수가 단가와 공선형이라 γ 가 β 를 흡수"
            f"(HS 하나가 章 하나를 독점하는 경우) ③ 해당 품목이 실제로 가격수용자.\n"
            f"    → a2 해석에 주의하고 R5 절제에서 a2 의존 TP(TP_X1·TP_X2) 기여를 반드시 확인하세요.")
    return out


def customs_a_sensors(cx: pd.DataFrame) -> pd.DataFrame:
    """A축 4센서를 (hs, ym) 격자에서 산출한다.

    a1 = Δlog(중량 12M 누계)          물량
    a2 = 단가 잔차                     가격결정력  ← 이 전략의 심장
    a3 = -Δ HHI(목적지)                고객 다변화
    a4 = Δ 선진시장 비중
    a5 = 신규 HS 등장(3개월 연속) → 12M 지수감쇠 더미
    """
    hsm = customs_hs_monthly(cx)
    if not len(hsm):
        return pd.DataFrame(columns=["hs", "ym", "a1", "a2", "a3", "a4", "a5",
                                     "wgt", "usd", "unit_price", "a2_beta"])
    cost = customs_input_cost(cx)
    a2 = customs_a2_residual(hsm, cost)

    # ★ shift(12)/rolling(12) 는 **행 위치** 기준이다. 통관은 그 달 선적이 없으면 행 자체가
    #   없으므로, 결측월이 있는 HS 에서는 '12행 전'이 12개월 전이 아니다(예: 2년 전).
    #   a2 는 피벗으로 균일 격자를 만들어 이 함정을 피하는데 a1/a3/a4/a5 는 그대로였다.
    #   → 여기서 (hs × 전체월) 완전격자로 펴서 위치=시간이 되도록 만든다.
    _yms = pd.DatetimeIndex(sorted(pd.unique(as_ts_series(hsm["ym"]).dropna())))
    _hss = pd.Index(sorted(hsm["hs"].astype(str).unique()), name="hs")
    _grid = pd.MultiIndex.from_product([_hss, _yms], names=["hs", "ym"]).to_frame(index=False)
    d = _grid.merge(hsm.assign(hs=hsm["hs"].astype(str)), on=["hs", "ym"], how="left")
    d = d.sort_values(["hs", "ym"]).reset_index(drop=True)
    # 선적이 없던 달은 물량 0 이 사실이다(누계·신규세번 판정의 전제).
    for _c in ("wgt", "usd"):
        if _c in d.columns:
            d[_c] = pd.to_numeric(d[_c], errors="coerce").fillna(0.0)
    g = d.groupby("hs", observed=True, sort=False)

    # a1: 12개월 누계 중량의 전년동기 대비 로그차. 계절성과 단월 노이즈를 함께 죽인다.
    d["wgt12"] = g["wgt"].transform(lambda s: s.rolling(12, min_periods=6).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        lw = np.log(d["wgt12"].where(d["wgt12"] > 0))
    d["a1"] = lw - lw.groupby(d["hs"], observed=True).shift(12)

    # a3: 다변화가 '개선'이므로 HHI 감소에 + 부호.
    d["a3"] = -(d["hhi_dest"] - g["hhi_dest"].shift(12))
    # a4: 선진시장 비중 증가.
    d["a4"] = d["adv_share"] - g["adv_share"].shift(12)

    # a5: 직전 12개월 물량이 사실상 0이었다가 3개월 연속 유의미하게 실린 경우 = 신규 세번.
    d["_active"] = (d["wgt"] > 0).astype(float)
    # ★ groupby 객체는 생성 시점의 컬럼 구성을 참조한다. 새 컬럼을 추가한 뒤에는 다시 만든다.
    g = d.groupby("hs", observed=True, sort=False)
    d["_streak"] = g["_active"].transform(
        lambda s: s.rolling(A5_STREAK, min_periods=A5_STREAK).sum())
    # ★ min_periods 로 느슨하게 두면 패널 앞 구간에서 prior 가 NaN 이고 `~(prior>0)` 가 True 라
    #   **오래된 HS 가 전부 '신규 세번'으로 발화**한다. 12개월 이력이 실제로 관측된 경우에만
    #   판정한다(이력을 모르면 '신규'라고 주장하지 않는다).
    prior = g["wgt"].transform(lambda s: s.shift(A5_STREAK).rolling(12, min_periods=12).sum())
    onset = (d["_streak"] >= A5_STREAK) & prior.notna() & (~(prior > 0))
    # 지수감쇠 더미: 발화 시점부터 12개월간 감쇠하며 남는다.
    lam = 0.5 ** (1.0 / max(A5_DECAY_HALFLIFE, 1e-9))
    d["a5"] = _decay_dummy(onset.to_numpy(), d["hs"].to_numpy(), lam, horizon=12)

    d = d.merge(a2[["hs", "ym", "a2", "a2_beta"]], on=["hs", "ym"], how="left")
    keep = ["hs", "ym", "a1", "a2", "a3", "a4", "a5", "wgt", "usd",
            "unit_price", "hhi_dest", "adv_share", "a2_beta"]
    return d[keep]


def _decay_dummy(onset: np.ndarray, groups: np.ndarray, lam: float,
                 horizon: int = 12) -> np.ndarray:
    """발화 시점부터 지수감쇠하며 horizon 개월간 살아있는 더미를 벡터화로 만든다.

    루프는 그룹 경계에서만 돈다(HS 수 ~600). 행 단위 파이썬 루프가 아니다.
    """
    out = np.zeros(len(onset), dtype=float)
    if not len(onset):
        return out
    # 그룹 경계 인덱스
    starts = np.flatnonzero(np.r_[True, groups[1:] != groups[:-1]])
    ends = np.r_[starts[1:], len(onset)]
    for s, e in zip(starts, ends):
        seg = onset[s:e]
        idx = np.flatnonzero(seg)
        if not len(idx):
            continue
        val = np.zeros(e - s, dtype=float)
        n = e - s
        for i in idx:
            j = min(n, i + horizon)
            k = np.arange(0, j - i)
            val[i:j] = np.maximum(val[i:j], lam ** k)
        out[s:e] = val
    return out


def map_hs_to_corp(a_hs: pd.DataFrame, mapping: pd.DataFrame,
                   months: pd.DatetimeIndex) -> pd.DataFrame:
    """HS 격자의 A축 센서를 매핑표를 통해 종목 격자로 옮긴다.

    ★ C3(PIT 라벨 고정): 매핑은 (code, hs, weight, valid_from, valid_to) 이고
      valid_from 은 그 제품구성을 알 수 있게 된 **사업보고서 접수일**이다.
      2024년 사업보고서로 알게 된 구성을 2022년 백테스트에 쓰면 성과는 전부 가짜다.
    """
    cols = ["code", "ym", "a1", "a2", "a3", "a4", "a5", "x_wgt", "x_usd",
            "a2_beta", "hs_main", "hs_n"]
    if a_hs is None or not len(a_hs) or mapping is None or not len(mapping):
        return pd.DataFrame(columns=cols)
    m = mapping.copy()
    m["hs"] = m["hs"].astype(str)
    m["valid_from"] = as_ts_series(m["valid_from"])
    m["valid_to"] = as_ts_series(m.get("valid_to"))
    m["valid_to"] = m["valid_to"].fillna(pd.Timestamp("2262-01-01"))
    m["weight"] = pd.to_numeric(m.get("weight"), errors="coerce").fillna(1.0)

    a = a_hs.copy()
    a["hs"] = a["hs"].astype(str)
    j = a.merge(m[["code", "hs", "weight", "valid_from", "valid_to"]], on="hs", how="inner")
    # PIT 유효구간 필터 — 알 수 있게 된 뒤에만 쓴다.
    j = j[(j["ym"] >= j["valid_from"]) & (j["ym"] <= j["valid_to"])].copy()
    if not len(j):
        return pd.DataFrame(columns=cols)

    j["w"] = j["weight"].clip(lower=0.0)
    # 가중평균. 결측 센서는 그 항의 가중치에서 빠져야 하므로 센서별로 분모를 따로 만든다.
    parts = {}
    for s in ("a1", "a2", "a3", "a4", "a5"):
        v = pd.to_numeric(j[s], errors="coerce")
        ok = v.notna()
        j[f"_n_{s}"] = np.where(ok, v * j["w"], 0.0)
        j[f"_d_{s}"] = np.where(ok, j["w"], 0.0)
    agg = {f"_n_{s}": (f"_n_{s}", "sum") for s in ("a1", "a2", "a3", "a4", "a5")}
    agg.update({f"_d_{s}": (f"_d_{s}", "sum") for s in ("a1", "a2", "a3", "a4", "a5")})
    agg.update(x_wgt=("wgt", "sum"), x_usd=("usd", "sum"),
               a2_beta=("a2_beta", "mean"), hs_n=("hs", "nunique"))
    G = j.groupby(["code", "ym"], observed=True, sort=False).agg(**agg).reset_index()
    for s in ("a1", "a2", "a3", "a4", "a5"):
        G[s] = safe_div(G[f"_n_{s}"], G[f"_d_{s}"])
        G.loc[~(G[f"_d_{s}"] > 0), s] = np.nan
        G = G.drop(columns=[f"_n_{s}", f"_d_{s}"])

    # 대표 HS(진단카드용) — 금액이 가장 큰 것
    top = (j.sort_values("usd", ascending=False)
             .drop_duplicates(["code", "ym"])[["code", "ym", "hs"]]
             .rename(columns={"hs": "hs_main"}))
    G = G.merge(top, on=["code", "ym"], how="left")
    return G.reindex(columns=cols)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  B축 — 회계 진정성 (사전확률)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def b_sensors(fin: pd.DataFrame) -> pd.DataFrame:
    """b1~b5 를 분기 프레임에서 산출한다.

    ★ 월 패널에서 diff(12) 를 하면 제출일이 해마다 밀리는 구조 때문에 "12개월 전 행"이
      같은 사업연도를 가리키는 달이 생겨 Δ가 0이 된다. 반드시 분기 프레임에서 계산하고,
      PIT 안전성은 뒤의 merge_asof(knowledge_date) 가 보장한다.

    b1 = Δlog(매출 TTM)
    b2 = -Δ(DIO + DSO)                      회전 유지
    b3 = -Δ((순이익-영업CF)/평균총자산)     Sloan accruals — 순이익 음수 구간에서도 안전
    b4 = Δ(계약부채+선수금)/매출            조작 여지 낮은 확정 미래매출
    b5 = Δ 매출총이익률
    """
    need = ["code", "period_end", "knowledge_date"]
    if fin is None or not len(fin) or any(c not in fin.columns for c in need):
        return pd.DataFrame(columns=need + ["b1", "b2", "b3", "b4", "b5"])
    d = fin.sort_values(["code", "period_end"]).copy()

    # ★ 한국 분기공시는 **누적** 공시다. revenue 원값에 rolling(4).sum() 을 걸면
    #   1~3분기가 이미 누적이라 매출을 크게 중복 계상한다. tidy_financials 가
    #   분기차분(_q)과 TTM(_ttm)을 이미 정확히 만들어 두므로 **반드시 그것을 쓴다**.
    def _ttm(name: str) -> pd.Series:
        for cand in (f"{name}_ttm", name):
            if cand in d.columns:
                return pd.to_numeric(d[cand], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    def _lag4(s: pd.Series) -> pd.Series:
        return s.groupby(d["code"], observed=True).shift(4)

    d["rev_ttm"] = _ttm("revenue")
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(d["rev_ttm"].where(d["rev_ttm"] > 0))
    d["b1"] = lr - _lag4(lr)

    # DIO / DSO — 분모가 TTM 이어야 계절성에 흔들리지 않는다.
    cogs_ttm = _ttm("cogs")
    dio = safe_div(col(d, "inventory") * 365.0, cogs_ttm)
    dso = safe_div(col(d, "receivable") * 365.0, d["rev_ttm"])
    ccc = dio + dso
    d["b2"] = -(ccc - _lag4(ccc))

    ta = col(d, "assets")
    ta_avg = (ta + _lag4(ta)) / 2.0
    ni_ttm = _ttm("net_income")
    cfo_ttm = _ttm("cfo")
    accr = safe_div(ni_ttm - cfo_ttm, ta_avg)
    d["b3"] = -(accr - _lag4(accr))

    # 계약부채 계정에 선수금이 함께 매핑되어 있다(ACCOUNT_MAP). 이중계상하지 않는다.
    dr_ratio = safe_div(col(d, "contract_liab"), d["rev_ttm"])
    d["b4"] = dr_ratio - _lag4(dr_ratio)

    gpm = safe_div(d["rev_ttm"] - cogs_ttm, d["rev_ttm"])
    d["b5"] = gpm - _lag4(gpm)

    # 밀어내기 판정(V1)용 원시값도 같이 내보낸다 — 거부권이 재계산하지 않도록.
    d_rev = d["rev_ttm"] - _lag4(d["rev_ttm"])
    d_inv = col(d, "inventory") - _lag4(col(d, "inventory"))
    d_rec = col(d, "receivable") - _lag4(col(d, "receivable"))
    d["v1_ratio"] = np.where(d_rev > 0, safe_div(d_inv + d_rec, d_rev), np.nan)
    # V2 는 '3분기 연속'이 조건이다. tidy_financials 가 이미 연속 카운트를 만들어 두면
    # 그것을 쓰고, 없으면 여기서 직접 만든다(단발 플래그를 3분기 롤링합으로).
    bad = ((ni_ttm > 0) & (cfo_ttm < 0.5 * ni_ttm)).astype(float)
    if "v2_bad_3q" in d.columns:
        # ★ tidy_financials 의 v2_bad_3q 는 rolling(3).min() 이라 이미 '3분기 연속' 자체를
        #   뜻하는 0/1 이다. 이걸 카운트로 오해해 ">=3" 으로 비교하면 영원히 거짓이 되어
        #   V2 거부권이 통째로 죽는다(예외는 안 난다).
        d["v2_streak"] = (pd.to_numeric(d["v2_bad_3q"], errors="coerce") > 0).astype(float)
    else:
        d["v2_streak"] = (bad.groupby(d["code"], observed=True).transform(
            lambda s: s.rolling(3, min_periods=3).min()) > 0).astype(float)
    d["gpm"] = gpm
    keep = need + ["b1", "b2", "b3", "b4", "b5", "v1_ratio", "v2_streak", "gpm", "rev_ttm"]
    return d.reindex(columns=keep)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  C축 — 능력 확충 (사전확률)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def c_sensors(fin: pd.DataFrame, emp: Optional[pd.DataFrame] = None,
              contracts: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """c1~c6.

    c1 = 유형자산취득 / 직전3년평균
    c2 = Δ(NOPAT / 평균IC)                IC = 순운전자본+유형자산+무형자산
    c3 = Δlog(직원수)
    c4 = Δ(연간급여총액)/Δ(직원수) / 전기1인평균급여     한계임금 프리미엄
    c5 = Δ(판관비/매출)
    c6 = 단일판매·공급계약 공시금액 12M / 매출          ★ 교차확증용
    """
    need = ["code", "period_end", "knowledge_date"]
    if fin is None or not len(fin) or any(c not in fin.columns for c in need):
        return pd.DataFrame(columns=need + ["c1", "c2", "c5"])
    d = fin.sort_values(["code", "period_end"]).copy()

    def _ttm(name: str) -> pd.Series:
        for cand in (f"{name}_ttm", name):
            if cand in d.columns:
                return pd.to_numeric(d[cand], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    def _lag(s: pd.Series, k: int = 4) -> pd.Series:
        return s.groupby(d["code"], observed=True).shift(k)

    capex_ttm = _ttm("capex").abs()          # 현금흐름표상 취득은 음수로 표기되기도 한다
    capex_3y = _lag(capex_ttm).groupby(d["code"], observed=True).transform(
        lambda s: s.rolling(12, min_periods=6).mean())
    d["c1"] = safe_div(capex_ttm, capex_3y)

    ppe = col(d, "ppe")
    intang = col(d, "intangible")
    # 매입채무 계정이 ACCOUNT_MAP 에 없으므로 유동부채로 순운전자본을 근사한다.
    # 근사임을 명시한다 — 없는 것을 있는 척하지 않는다.
    nwc = col(d, "cur_assets") - col(d, "cur_liab")
    ic = nwc + ppe + intang
    ic_avg = (ic + _lag(ic)) / 2.0
    ebit_ttm = _ttm("op_income")
    pretax_ttm = _ttm("pretax_income")
    taxexp_ttm = _ttm("tax_expense")
    etr = safe_div(taxexp_ttm, pretax_ttm)
    etr = etr.where((etr > -0.5) & (etr < 1.0))
    tax = etr.fillna(0.22).clip(0.0, 0.5)
    roic = safe_div(ebit_ttm * (1.0 - tax), ic_avg)
    d["c2"] = roic - _lag(roic)
    d["roic"] = roic
    d["ic"] = ic
    d["etr"] = etr
    d["etr_chg"] = etr - _lag(etr)

    rev_ttm = _ttm("revenue")
    sga_r = safe_div(_ttm("sgna"), rev_ttm)
    # c5 는 '판관비 비율 변화'이며, TP_X3 에서 -c5 로 쓰인다(안 늘어난 것이 미덕).
    d["c5"] = sga_r - _lag(sga_r)

    out = d.reindex(columns=need + ["c1", "c2", "c5", "roic", "ic", "etr", "etr_chg"])

    # ── c3, c4 는 **연도 프레임**(직원현황)에서 계산한다.
    #   ★ 월 패널에서 diff(12) 를 하면 제출일이 해마다 밀리는 구조 때문에 "12개월 전 행"이
    #     같은 사업연도를 가리키는 달이 생겨 Δ직원수가 0 이 되고 c4 가 통째로 결측이 된다.
    #     PIT 안전성은 뒤의 merge_asof(knowledge_date) 가 보장한다.
    if emp is not None and len(emp):
        e = emp.copy()
        # fetch_dart_employees 스키마: code, bsns_year, employees, payroll, knowledge_date
        ycol = "bsns_year" if "bsns_year" in e.columns else "period_end"
        e = e.sort_values(["code", ycol])
        n = pd.to_numeric(e.get("employees"), errors="coerce")
        pay = pd.to_numeric(e.get("payroll"), errors="coerce")
        if pay.isna().all() and "payroll_total" in e.columns:
            pay = pd.to_numeric(e["payroll_total"], errors="coerce")
        e["_n"], e["_pay"] = n, pay
        gcode = e["code"]
        with np.errstate(divide="ignore", invalid="ignore"):
            ln = np.log(n.where(n > 0))
        e["c3"] = ln - ln.groupby(gcode, observed=True).shift(1)
        n_prev = n.groupby(gcode, observed=True).shift(1)
        pay_prev = pay.groupby(gcode, observed=True).shift(1)
        dn = n - n_prev
        dpay = pay - pay_prev
        prev_avg = safe_div(pay_prev, n_prev)
        # 분모 안정성: |Δ직원수| >= max(5, 직원수_{t-1}×3%) 일 때만. 아니면 결측(0 금지).
        thresh = np.maximum(5.0, n_prev * 0.03)
        ok = (dn.abs() >= thresh) & (prev_avg > 0)
        e["c4"] = np.where(ok, safe_div(safe_div(dpay, dn), prev_avg), np.nan)
        keep_e = ["code", "knowledge_date", "c3", "c4"]
        out = pd.concat([out, e.reindex(columns=keep_e)], ignore_index=True, sort=False)

    # ── c6 은 공시 이벤트를 12개월 누계로 — 별도 처리(월 격자에서 붙임)
    return out


def c6_contract_ratio(contracts: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """c6 — 단일판매·공급계약 체결 공시금액의 12개월 누계 (월 격자).

    ★ 이것이 TP_XC 의 한쪽 날개다. 공시는 **기업 자신의 진술**이고 통관 물량은
      **제3자(관세청)의 관측**이다. 독립인 두 소스가 같은 방향을 가리키면 신뢰도가 곱으로 오른다.
    """
    if contracts is None or not len(contracts):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    c = contracts.copy()
    c["knowledge_date"] = as_ts_series(c["knowledge_date"])
    c["amount"] = pd.to_numeric(c.get("amount"), errors="coerce")
    c = c[c["knowledge_date"].notna() & (c["amount"] > 0)]
    if not len(c):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    # ★ 월 루프로 필터링하면 (이벤트 × 개월수) 비교가 된다. 이벤트가 유효한 월말로
    #   직접 펼치면 O(이벤트 × 12) 이고 groupby 는 1회다 — v3 코어의 원시함수를 쓴다.
    ex = expand_events_to_months(c[["code", "knowledge_date", "amount"]],
                                 "knowledge_date", months, window_days=365)
    if not len(ex):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    m = (ex.groupby(["code", "month"], observed=True)["amount"].sum()
           .rename("contract_12m").reset_index().rename(columns={"month": "ym"}))
    return m[["code", "ym", "contract_12m"]]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  D축 — 미반영도 (할인율 U)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def _merge_ready(df: "Optional[pd.DataFrame]", keys: Sequence[str], what: str) -> bool:
    """병합 직전에 키 존재를 확인한다. 없으면 **어느 프레임의 무엇이 없는지** 말하고 False.

    ★ 실측: 수급 프레임이 [code, date, ...] 인데 on=["code","ym"] 로 merge 해
      pandas 내부에서 `KeyError: 'ym'` 만 떨어졌다. 어느 데이터가 문제인지 알 수 없어
      6분짜리 수집을 다시 돌려가며 찾아야 했다. 계약 위반은 위반 지점에서 말한다.
    """
    if df is None or not len(df):
        return False
    miss = [k for k in keys if k not in df.columns]
    if miss:
        LOG.warn(f"[병합 계약] {what}: 키 {miss} 가 없습니다 "
                 f"(보유 컬럼 {list(df.columns)[:8]}). 이 소스를 건너뜁니다 — "
                 f"결측으로 두며 0 으로 채우지 않습니다.")
        return False
    return True


def d_sensors(px_m: pd.DataFrame, fin_m: pd.DataFrame,
              flows: Optional[pd.DataFrame] = None,
              coverage: Optional[pd.DataFrame] = None,
              window_m: int = 6) -> pd.DataFrame:
    """d1~d4.

    ★ d1 이 이 시스템에서 가장 중요한 단일 지표다.
      Δlog P = Δlog E + Δlog M  로 분해하면 M 은 멀티플이다.
        ΔlogE > 0, ΔlogM ≤ 0  = 시장이 이익 증가는 인정했으나 자본화를 거부 =
                                 "일회성으로 분류함" = 바로 이것이 노리는 미스프라이싱.
        ΔlogE > 0, ΔlogM > 0  = 이미 리레이팅 진행 중 = 배제.

    ⚠ 한계: 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 E 는 후행 12M 이익 대리변수다.
      이 대리변수의 한계는 리포트에 명시한다(§15.4). 숨기지 않는다.
    """
    cols = ["code", "ym", "d1", "d2", "d3", "d4", "dlogE", "dlogM"]
    if px_m is None or not len(px_m):
        return pd.DataFrame(columns=cols)
    d = px_m.sort_values(["code", "ym"]).copy()
    if fin_m is not None and len(fin_m):
        d = d.merge(fin_m[["code", "ym", "eps_ttm"]], on=["code", "ym"], how="left")
    else:
        d["eps_ttm"] = np.nan

    g = d.groupby("code", observed=True, sort=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        lp = np.log(pd.to_numeric(d["close"], errors="coerce").where(lambda s: s > 0))
        le = np.log(pd.to_numeric(d["eps_ttm"], errors="coerce").where(lambda s: s > 0))
    d["dlogP"] = lp - lp.groupby(d["code"], observed=True).shift(window_m)
    d["dlogE"] = le - le.groupby(d["code"], observed=True).shift(window_m)
    # 항등식으로 M 을 얻는다 — P/E 를 직접 만들면 E<=0 구간이 통째로 날아간다.
    d["dlogM"] = d["dlogP"] - d["dlogE"]
    d["d1"] = -d["dlogM"]

    if coverage is not None and len(coverage):
        d = d.merge(coverage, on=["code", "ym"], how="left")
        d["d2"] = -pd.to_numeric(d.get("n_analyst"), errors="coerce")
        d["d4"] = pd.to_numeric(d.get("coverage_init"), errors="coerce")
    else:
        d["d2"] = np.nan
        d["d4"] = np.nan

    # ★ 패널 병합은 계약을 먼저 확인한다. 없는 키로 merge 하면 pandas 내부에서
    #   KeyError 만 튀어나와 '어느 프레임의 어느 컬럼이 없는지'를 알 수 없다(실측 사고).
    if flows is not None and len(flows) and _merge_ready(flows, ["code", "ym"], "flows(d3)"):
        d = d.merge(flows, on=["code", "ym"], how="left")
        if "net_buy_120d" not in d.columns:
            LOG.warn("수급에 net_buy_120d 가 없어 d3 를 비활성화합니다 "
                     "(0 으로 채우면 '수급이 없었다'는 거짓 주장이 됩니다).")
            d["d3"] = np.nan
        else:
            d["d3"] = -safe_div(pd.to_numeric(d["net_buy_120d"], errors="coerce"),
                                pd.to_numeric(d.get("mcap"), errors="coerce"))
    else:
        d["d3"] = np.nan
    return d.reindex(columns=cols)


def theta_x(fin_m: pd.DataFrame) -> pd.Series:
    """θ_X = 국내법인 수출매출(별도) / 연결매출.  관측커버리지 가중치.

    통관은 '관세영역 반출 물량'이므로 대응 회계항목은 **별도(개별)** 기준 수출매출이다.
    연결이 아니다. 해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.

    θ_X 는 배제 기준이 아니라 **가중치**다. θ_X=0.2 인 기업은 신호가 있어도 연결 실적을
    못 움직이므로 자연스럽게 걸러진다.
    """
    if fin_m is None or not len(fin_m):
        return pd.Series(dtype=float)
    exp_sep = pd.to_numeric(fin_m.get("export_rev_sep"), errors="coerce")
    rev_con = pd.to_numeric(fin_m.get("revenue_con"), errors="coerce")
    t = safe_div(exp_sep, rev_con).clip(0.0, 1.0)
    return t
