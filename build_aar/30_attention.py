

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  주의 배분 패널 → 초과주의(EA) → 축소추정 → 기계적발간 통제 → VAS                    ║
# ║                                                                                          ║
# ║  §6.1  share(a,i,t) = reports(a,i,t) / N(a,t)          N(a,t)<3 → **셀 전체** 결측        ║
# ║  §6.2  base(a,i,t)  = Σ_{t-12..t-1} reports / Σ N       Σ N<12 → **셀 전체** 결측         ║
# ║         EA = share − base   → 경험적 베이즈 축소추정 (해석적 분산 + tau² 3단 계층)        ║
# ║  §6.3  VAS = EA_shrunk 을 기계적 발간 요인으로 회귀한 잔차                                 ║
# ║                                                                                          ║
# ║  ★★ §6.3 을 건너뛰거나 약화시키면 산출물 전체가 무효다(§1-4, §13). ★★                     ║
# ║     통제 없는 원신호는 그냥 실적시즌 달력이다. 통제를 성실히 했는데 신호가 사라진다면       ║
# ║     그것이 정답이며, 통제를 약화시켜 신호를 되살리려는 모든 시도는 이 프로젝트의 실패다.    ║
# ║                                                                                          ║
# ║  ★ 미래누수 봉인 — 확장창을 **생산 경로로 확정**한다:                                      ║
# ║      · 월 t 의 회귀는 [t0, t] 표본으로 재적합하고 월 t 행의 잔차만 VAS 로 쓴다.            ║
# ║        (섹터×월 FE 는 정의상 당월 횡단면에서만 추정되므로 누수가 아니다 —                  ║
# ║         횡단면 z 표준화가 누수가 아닌 것과 같은 이유다. 반면 AnalystFE 를 전기간으로       ║
# ║         추정하면 **커리어 전체 평균 = 미래 포함** 을 빼게 되어 명백한 누수다.)             ║
# ║      · EB 의 tau²·v 도 동일하게 [t0, t] 로만 추정한다. 여기가 가장 놓치기 쉽다.            ║
# ║      · 전기간 회귀는 참고 진단으로만 병기해 "전기간을 썼다면 얼마나 훔쳤을지"를 보여준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CTRL_MIN_TRAIN_M = 24        # 확장창 최소 학습 개월(버인). 이보다 짧으면 VAS 를 만들지 않는다.
CONTROL_VARS = ["earnings_month", "new_cover", "index_event", "log_disclosure"]


def build_attention_panel(L: "pd.DataFrame", months: "pd.DatetimeIndex",
                          sec: "pd.DataFrame", unit_mode: str = "ANALYST") -> "pd.DataFrame":
    """(주체, 종목, 월) 주의 패널. share / base / EA / 해석적 분산 v 까지.

    unit_mode="HOUSE" 면 Phase 0 폴백 — 주의 예산의 주체를 (증권사 × 섹터)로 격하한다(§3).
    """
    cols = ["unit_id", "house", "code", "month", "r_t", "N_t", "r_lb", "N_lb",
            "share", "base", "EA", "v", "new_cover", "sector"]
    if L is None or L.empty:
        return pd.DataFrame(columns=cols)

    ind = {}
    if sec is not None and len(sec):
        scol = "sector" if "sector" in sec.columns else "industry"
        ind = dict(zip(as_str_series(sec["code"]), as_str_series(sec[scol])))

    x = L.copy()
    x["month"] = as_ts_series(x["month"] if "month" in x.columns else x["pub_date"]) \
        + pd.offsets.MonthEnd(0)
    x = x.dropna(subset=["month", "analyst_id", "report_uid"])
    src_code = "code" if "code" in x.columns else "stock_code"
    x["code"] = as_str_series(x[src_code]).replace("", np.nan)
    x["sector"] = x["code"].map(ind).fillna("미분류")
    x["house"] = as_str_series(x["broker_legal_id"]) if "broker_legal_id" in x.columns \
        else as_str_series(x.get("broker_id", ""))
    # 주의 예산의 주체 — 인물이 아니라 '소속-계정'이다. 소속이 바뀌면 예산이 다르다(§5).
    x["unit_id"] = as_str_series(x["analyst_id"])
    if unit_mode == "HOUSE":
        x["unit_id"] = x["house"] + "|" + as_str_series(x["sector"])
        LOG.warn("[하우스 단위 폴백] 주의 배분의 주체를 (증권사 × 섹터)로 격하했습니다. "
                 "이 결과를 애널리스트 단위 결과로 보고하지 마십시오(§3).")

    # ── 분수배분: 한 리포트가 종목 k개를 다루면 1/k 씩 ────────────────────────────────
    #   정수로 세면 Σ share 가 1 을 넘어 영합 항등식과 이항분산 공식이 동시에 깨진다.
    nstock = x.groupby("report_uid", observed=True)["code"].transform("nunique").clip(lower=1)
    x["w_alloc"] = 1.0 / nstock

    # ── N(a,t): 그 달 발간한 **총** 리포트 수 (종목 없는 산업리포트 포함) ──────────────
    #   ★ 종목 리포트만 세면 분모가 과소집계되어 share 가 부풀려진다. 주의 예산은 하나다.
    NA = (x.groupby(["unit_id", "month"], observed=True)["report_uid"]
           .nunique().rename("N_t").reset_index())
    xi = x.dropna(subset=["code"])
    if xi.empty:
        LOG.error("종목이 식별된 리포트가 없어 주의 패널을 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    CNT = (xi.groupby(["unit_id", "code", "month"], observed=True)["w_alloc"]
             .sum().rename("r_t").reset_index())

    # ── 조밀 격자 + 누적합으로 롤링 12개월을 벡터화한다 ────────────────────────────────
    all_months = pd.DatetimeIndex(sorted(set(months) | set(CNT["month"].unique())
                                         | set(NA["month"].unique())))
    mpos = {m: i for i, m in enumerate(all_months)}
    T = len(all_months)
    uniq_unit = pd.Index(sorted(set(as_str_series(CNT["unit_id"])) |
                                set(as_str_series(NA["unit_id"]))))
    umap = {u: i for i, u in enumerate(uniq_unit)}
    U_K = len(uniq_unit)

    pair_key = as_str_series(CNT["unit_id"]) + "\x1f" + as_str_series(CNT["code"])
    p_codes, p_k = factorize_codes(pair_key)
    t_idx = CNT["month"].map(mpos).to_numpy(dtype=np.int64)
    Cmat = np.zeros((p_k, T), dtype=np.float64)
    np.add.at(Cmat, (p_codes, t_idx), CNT["r_t"].to_numpy(dtype=np.float64))

    Nmat = np.zeros((U_K, T), dtype=np.float64)
    np.add.at(Nmat, (NA["unit_id"].map(umap).to_numpy(dtype=np.int64),
                     NA["month"].map(mpos).to_numpy(dtype=np.int64)),
              NA["N_t"].to_numpy(dtype=np.float64))

    pair_lookup = (pd.DataFrame({"_p": p_codes, "unit_id": CNT["unit_id"].to_numpy(),
                                 "code": CNT["code"].to_numpy()})
                   .drop_duplicates("_p").set_index("_p").sort_index())
    # ★★ 축 주의 — 여기가 조용히 틀리면 신호 전체가 무의미해진다. ★★
    #   np.where(Cmat...) 가 돌려주는 sel_p 는 **pair 코드**(0..p_k-1)다.
    #   그런데 pair_key 로부터 곧바로 만든 배열은 **CNT 행 번호** 축이다. 한 (주체,종목)
    #   쌍이 여러 달에 걸쳐 여러 행을 갖기 때문에 두 축은 절대 일치하지 않는다.
    #   그 배열을 pair 코드로 색인하면 관측 대부분이 **다른 애널리스트의 N(a,t)** 를
    #   분모로 쓰게 되고, 예외는 나지 않는다. 반드시 pair 코드 축에서 만든다.
    pair_unit = (as_str_series(pair_lookup["unit_id"]).map(umap)
                 .to_numpy(dtype=np.int64))
    if len(pair_unit) != p_k:
        raise KillCriteria(
            f"주의 패널 축 불일치: pair_unit {len(pair_unit)} vs pair 코드 {p_k}. "
            f"이 상태로 진행하면 분모가 뒤섞인 신호가 만들어집니다.")

    def trailing12(M: np.ndarray) -> np.ndarray:
        """Σ_{s=t-12}^{t-1} — **당월 t 를 포함하지 않는다.** 포함하면 그 자체가 정보 누수다."""
        cs = np.cumsum(M, axis=1)
        out = np.zeros_like(M)
        out[:, 1:] = cs[:, :-1]
        lag = np.zeros_like(M)
        if T > LOOKBACK_M:
            lag[:, LOOKBACK_M + 1:] = cs[:, :T - LOOKBACK_M - 1]
        return out - lag

    C12 = trailing12(Cmat)
    N12 = trailing12(Nmat)

    # ── 합집합 채움 (union fill) ───────────────────────────────────────────────────────
    #   ★ reports>0 행만 쌓으면 **음의 EA 가 통째로 사라진다**. 커버를 끊은 종목은
    #     share=0, base>0 이라 EA<0 인데, 그 행은 CNT 에 존재하지 않기 때문이다.
    #     (실측: 합집합이면 ΣEA=1.67e-16, 필터하면 +0.75 로 전량 양수 편향)
    has_now = Cmat > 0
    has_base = C12 > 0
    sel_p, sel_t = np.where(has_now | has_base)
    if not len(sel_p):
        return pd.DataFrame(columns=cols)

    u_of = pair_unit[sel_p]
    r_t = Cmat[sel_p, sel_t]
    N_t = Nmat[u_of, sel_t]
    r_lb = C12[sel_p, sel_t]
    N_lb = N12[u_of, sel_t]

    P = pd.DataFrame({
        "unit_id": pair_lookup.loc[sel_p, "unit_id"].to_numpy(),
        "code": pair_lookup.loc[sel_p, "code"].to_numpy(),
        "month": all_months.to_numpy()[sel_t],
        "r_t": r_t, "N_t": N_t, "r_lb": r_lb, "N_lb": N_lb,
    })

    # ── 결측 규칙: 반드시 (주체, 월) **셀 전체** 삭제 ─────────────────────────────────
    #   행 단위로 지우면 Σ share < 1 이 되어 EA 에 체계적 편향이 생긴다(§7-F9).
    n_before = len(P)
    keep_cell = (P["N_t"] >= MIN_REPORTS_MON) & (P["N_lb"] >= MIN_LOOKBACK_N)
    P = P[keep_cell]
    LOG.info(f"결측 규칙 적용 — N(a,t)≥{MIN_REPORTS_MON} 및 룩백ΣN≥{MIN_LOOKBACK_N} 인 "
             f"(주체,월) 셀만 유지: {n_before:,} → {len(P):,}행 "
             f"(셀 단위 삭제 — 행 단위로 지우면 Σshare 가 깨집니다)")
    if P.empty:
        return pd.DataFrame(columns=cols)

    P["share"] = P["r_t"] / P["N_t"]
    P["base"] = P["r_lb"] / P["N_lb"]
    P["EA"] = P["share"] - P["base"]
    P["v"] = ea_analytic_var(P["r_t"], P["N_t"], P["r_lb"], P["N_lb"])
    # NewCoverage: 12개월 룩백에 한 건도 없었는데 이번 달에 발간 = 신규 개시
    P["new_cover"] = ((P["r_lb"] <= 0) & (P["r_t"] > 0)).astype("float64")
    P["sector"] = as_str_series(P["code"]).map(ind).fillna("미분류")
    hmap = x.drop_duplicates("unit_id").set_index("unit_id")["house"].to_dict()
    P["house"] = as_str_series(P["unit_id"]).map(hmap).fillna("_H")

    # ── 좌측절단 방어 ─────────────────────────────────────────────────────────────────
    #   데이터 시작 12개월 안에는 NewCoverage 가 전부 1 로 잡힌다(과거를 못 봤을 뿐인데).
    #   0 으로 채우면 '기존 커버'라는 적극적 거짓 정보가 되므로 **행을 삭제**한다.
    first_seen = x.groupby("unit_id", observed=True)["month"].min()
    fs = as_str_series(P["unit_id"]).map(first_seen)
    trunc = fs.notna() & (P["month"] < (fs + pd.DateOffset(months=LOOKBACK_M)))
    if trunc.any():
        LOG.info(f"좌측절단 제거 — 주체의 최초 관측 후 {LOOKBACK_M}개월 이내 {int(trunc.sum()):,}행 "
                 f"삭제(NewCoverage 가 구조적으로 1 이 되는 구간. 0 으로 채우면 거짓 정보).")
        P = P[~trunc]

    # ── 항등식 진단 (계약검정과 동일한 값) ────────────────────────────────────────────
    #   Σ_i EA(a,i,t) = (당월 종목리포트 비중) − (룩백 종목리포트 비중).
    #   모든 리포트에 종목이 붙어 있으면 정확히 0 이다. 산업리포트가 섞이면 그만큼 벗어난다.
    try:
        zs = P.groupby(["unit_id", "month"], observed=True)["EA"].sum()
        LOG.info(f"영합 항등식 진단 — Σ_i EA 의 |중앙값| {float(zs.abs().median()):.3e}, "
                 f"|최대| {float(zs.abs().max()):.3e}. "
                 f"0 에서 벗어나는 만큼이 '종목 없는 산업리포트'의 비중 변화입니다"
                 f"(오류가 아니라 정의상 그렇습니다).")
    except Exception:
        pass

    LOG.ok(f"주의 패널 {len(P):,}행 — 주체 {P['unit_id'].nunique():,} × "
           f"종목 {P['code'].nunique():,} × {P['month'].nunique()}개월 · {mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "attention_panel_raw", P)
    return P.reset_index(drop=True)


def _build_index_event(uni: "pd.DataFrame") -> "pd.DataFrame":
    """IndexEvent — KRX 실제 편입이력이 없으므로 **제도 상수 기반 합성 멤버십**으로 대체한다.

    KOSPI200 / KOSDAQ150 은 정기변경 심사기준일이 5월말·11월말이고 발효가 6월·12월이다.
    시총 상위 N(=200/150) 밴드의 진입·이탈을 편입/제외로 본다.

    ★ '시총 순위가 X% 이상 점프' 같은 임계값 정의는 쓰지 않는다 — 임계값이 곧 튜닝
      파라미터가 되어 사전등록을 위반한다. 밴드 크기 200/150 은 제도 상수라 자유도가 없다.
    ★ 이것은 대리변수다. 실제 KOSPI200 은 산업군별 누적시총과 순위버퍼 룰을 쓰므로
      완전히 일치하지 않는다. 통제가 불완전한 만큼 해석표에 명시한다.
    """
    band = {"KOSPI": 200, "KOSDAQ": 150}
    if uni is None or uni.empty:
        return pd.DataFrame(columns=["code", "month", "index_event"])
    d = uni[["code", "month", "market", "marcap"]].copy()
    d["market"] = as_str_series(d["market"]).str.upper()
    d["rk"] = (d.groupby(["month", "market"], observed=True)["marcap"]
                .rank(ascending=False, method="first"))
    d["inband"] = (d["rk"] <= d["market"].map(band).fillna(10 ** 9)).astype("float64")
    scr = d[d["month"].dt.month.isin((5, 11))].copy()
    scr["eff"] = scr["month"] + pd.offsets.MonthEnd(1)
    scr = scr.sort_values(["code", "month"])
    scr["chg"] = scr.groupby("code", observed=True)["inband"].diff().abs()
    ev = scr.loc[scr["chg"] > 0, ["code", "eff"]].rename(columns={"eff": "month"})
    ev["index_event"] = 1.0
    # 신규상장월 · 관측 재개월도 편입성 이벤트로 본다
    first = d.groupby("code", observed=True)["month"].min().rename("month").reset_index()
    first["index_event"] = 1.0
    out = (pd.concat([ev, first], ignore_index=True)
             .drop_duplicates(["code", "month"]))
    return out


def attach_controls(P: "pd.DataFrame", ctrl: "pd.DataFrame", uni: "pd.DataFrame") -> "pd.DataFrame":
    """종목×월 통제변수를 주의 패널에 붙인다. 결합키 결측 행을 **떨어뜨리지 않는다**
    (버리면 그게 곧 선택편향)."""
    if P is None or P.empty:
        return P
    out = P.copy()
    n0 = len(out)
    if ctrl is not None and len(ctrl):
        c = ctrl.copy()
        c["code"] = as_str_series(c["code"])
        c["month"] = as_ts_series(c["month"])
        use = [x for x in ("earnings_month", "log_disclosure") if x in c.columns]
        out = out.merge(c[["code", "month"] + use].drop_duplicates(["code", "month"]),
                        on=["code", "month"], how="left")
    ie = _build_index_event(uni)
    if len(ie):
        ie["code"] = as_str_series(ie["code"])
        ie["month"] = as_ts_series(ie["month"])
        out = out.merge(ie, on=["code", "month"], how="left")
    for c in CONTROL_VARS:
        if c not in out.columns:
            out[c] = np.nan
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 이벤트 더미의 결측은 '이벤트 없음'(0)이 맞다. 연속 통제(공시건수)의 결측은
    # 0 으로 채우면 '공시가 없었다'는 적극적 거짓이므로 열 자체를 제외한다(아래 compute_vas).
    for c in ("earnings_month", "new_cover", "index_event"):
        out[c] = out[c].fillna(0.0)
    if len(out) != n0:
        LOG.warn(f"통제변수 결합에서 행수가 {n0:,}→{len(out):,} 로 변했습니다 — "
                 f"통제 테이블에 (code, month) 중복이 있습니다. 중복을 제거하고 진행합니다.")
        out = out.drop_duplicates(["unit_id", "code", "month"], keep="first")
    out["sector_month"] = as_str_series(out["sector"]) + "|" + out["month"].dt.strftime("%Y%m")
    return out


def compute_vas(P: "pd.DataFrame", months: "pd.DatetimeIndex"
                ) -> Tuple["pd.DataFrame", "pd.DataFrame", "pd.DataFrame"]:
    """§6.2 축소 + §6.3 통제회귀를 **확장창 안에서 함께** 수행해 VAS 를 만든다.

    반환 (패널, 축소진단, 회귀진단)
    """
    if P is None or P.empty:
        return P, pd.DataFrame(), pd.DataFrame()
    d = P.sort_values("month", kind="stable").reset_index(drop=True)
    mon = d["month"].to_numpy()
    uniq_m = pd.DatetimeIndex(sorted(pd.unique(mon)))

    Xcols = [c for c in CONTROL_VARS if c in d.columns and d[c].notna().any()
             and float(d[c].std(skipna=True) or 0) > 0]
    dropped = [c for c in CONTROL_VARS if c not in Xcols]

    vas = np.full(len(d), np.nan)
    ea_sh = np.full(len(d), np.nan)
    wgt = np.full(len(d), np.nan)
    shr_diag_rows: List[dict] = []
    reg_rows: List[dict] = []
    n_sing = 0
    n_fail = 0

    LOG.info(f"확장창 재적합 시작 — {len(uniq_m)}개월 중 버인 {CTRL_MIN_TRAIN_M}개월 이후부터 "
             f"VAS 를 산출합니다. 매월 [t0, t] 표본으로 축소추정과 통제회귀를 다시 적합합니다.")
    for i, m in enumerate(tqdm(uniq_m, desc="VAS 확장창", ncols=88, leave=False)):
        if i < CTRL_MIN_TRAIN_M:
            continue
        sub_mask = mon <= np.datetime64(m)
        cur_mask = mon == np.datetime64(m)
        if int(cur_mask.sum()) == 0 or int(sub_mask.sum()) < 500:
            continue
        sub = d.loc[sub_mask]

        # ① EB 축소 — tau²·v 를 [t0, t] 표본으로만 추정한다 (여기가 가장 놓치기 쉬운 누수)
        try:
            sh, w, sdiag = eb_shrink_tau2(sub, unit="unit_id", house="house",
                                          sector="sector", ea="EA", var="v")
        except Exception as e:                                    # noqa
            LOG.debug(f"{m:%Y-%m} 축소추정 실패({type(e).__name__}) — 원값 사용")
            sh, w, sdiag = sub["EA"].astype("float32"), pd.Series(1.0, index=sub.index), pd.DataFrame()
        ea_sh[np.where(cur_mask)[0]] = sh.reindex(d.index[cur_mask]).to_numpy()
        wgt[np.where(cur_mask)[0]] = w.reindex(d.index[cur_mask]).to_numpy()

        # ② 통제회귀 — 같은 [t0, t] 표본. 섹터×월 FE 는 당월 횡단면에서만 추정되므로
        #    당월을 포함해도 누수가 아니다(횡단면 z 표준화와 같은 성질).
        y = sh.to_numpy(dtype=np.float64)
        Xm = sub[Xcols].to_numpy(dtype=np.float64) if Xcols else None
        sm_c, sm_k = factorize_codes(sub["sector_month"])
        an_c, an_k = factorize_codes(sub["unit_id"])
        try:
            resid, beta, keep_rows, keep_cols, info = absorb_2way(
                y, Xm, [sm_c, an_c], [sm_k, an_k], strict=False)
        except Exception as e:                                    # noqa
            n_fail += 1
            LOG.debug(f"{m:%Y-%m} FE 흡수 실패({type(e).__name__})")
            continue
        if not info.get("converged", True):
            n_fail += 1
        n_sing += int(info.get("n_singleton_dropped", 0))
        # 잔차를 원래 위치에 되꽂는다. 탈락행(싱글턴/결측)은 **0 이 아니라 NaN** 으로 남는다.
        full = np.full(len(sub), np.nan)
        full[np.where(keep_rows)[0]] = resid
        rows_cur = np.where(cur_mask)[0]
        pos_in_sub = np.searchsorted(np.where(sub_mask)[0], rows_cur)
        vas[rows_cur] = full[pos_in_sub]

        if i % 12 == 0 or i == CTRL_MIN_TRAIN_M:
            reg_rows.append({
                "month": pd.Timestamp(m), "n_train": int(sub_mask.sum()),
                "n_test": int(cur_mask.sum()),
                "singleton_drop": int(info.get("n_singleton_dropped", 0)),
                "iters": int(info.get("iters", 0)),
                "R2_absorbed": round(float(info.get("r2_absorbed", np.nan)), 4),
                **({f"b_{c}": (round(float(b), 6) if np.isfinite(b) else None)
                    for c, b in zip(Xcols, beta)} if beta.size else {}),
            })
            if len(sdiag):
                shr_diag_rows.append({"month": pd.Timestamp(m),
                                      "mean_w": float(sdiag["mean_w"].iloc[0]),
                                      "p10_w": float(sdiag["p10_w"].iloc[0]),
                                      "p90_w": float(sdiag["p90_w"].iloc[0]),
                                      "tau2_analyst": float(sdiag["tau2"].iloc[-1])})

    d["EA_shrunk"] = ea_sh.astype("float32")
    d["shrink_w"] = wgt.astype("float32")
    d["VAS"] = vas.astype("float32")

    # ── 전기간 회귀 (참고 진단 — 생산에 쓰지 않는다) ────────────────────────────────────
    try:
        sh_f, w_f, _ = eb_shrink_tau2(d, unit="unit_id", house="house", sector="sector",
                                      ea="EA", var="v")
        sm_c, sm_k = factorize_codes(d["sector_month"])
        an_c, an_k = factorize_codes(d["unit_id"])
        Xf = d[Xcols].to_numpy(dtype=np.float64) if Xcols else None
        r_f, b_f, kr_f, kc_f, info_f = absorb_2way(sh_f.to_numpy(dtype=np.float64), Xf,
                                                   [sm_c, an_c], [sm_k, an_k], strict=False)
        vf = np.full(len(d), np.nan)
        vf[np.where(kr_f)[0]] = r_f
        d["VAS_fullsample"] = vf.astype("float32")
        beta_full, info_full = b_f, info_f
    except Exception as e:                                        # noqa
        LOG.debug(f"전기간 참고 회귀 실패({type(e).__name__})")
        d["VAS_fullsample"] = np.nan
        beta_full, info_full = np.array([]), {}

    # ── 진단 ───────────────────────────────────────────────────────────────────────────
    n_vas = int(d["VAS"].notna().sum())
    var_ea = float(np.nanvar(d["EA_shrunk"].to_numpy(dtype="float64")))
    var_vas = float(np.nanvar(vas))
    r2 = 1.0 - (var_vas / var_ea) if var_ea > 0 else np.nan
    both = d[["VAS", "VAS_fullsample"]].dropna()
    corr_fw = float(both["VAS"].corr(both["VAS_fullsample"])) if len(both) > 100 else np.nan
    mean_w = float(np.nanmean(wgt))

    LOG.table([["관측(EA 유효)", f"{len(d):,}"],
               ["VAS 산출 성공", f"{n_vas:,} ({100*n_vas/max(len(d),1):.1f}%)"],
               ["통제 적용 변수", ", ".join(Xcols) if Xcols else "없음 ★"],
               ["통제 불가 변수", ", ".join(dropped) if dropped else "없음"],
               ["평균 축소 신뢰도 w", f"{mean_w:.3f}" if np.isfinite(mean_w) else "—"],
               ["통제가 설명한 분산", f"{100*r2:.1f}%" if np.isfinite(r2) else "—"],
               ["확장창 vs 전기간 상관", f"{corr_fw:.4f}" if np.isfinite(corr_fw) else "—"],
               ["싱글턴 셀 제거 누계", f"{n_sing:,}행 (잔차 0 오염 방지 — NaN 처리)"],
               ["FE 미수렴/실패 월", f"{n_fail}개월"],
               ["확장창 버인", f"{CTRL_MIN_TRAIN_M}개월"]],
              ["항목", "값"], ["l", "r"],
              title="§6.2 축소 + §6.3 통제회귀 진단 (★ 이 단계를 건너뛰면 산출물 전체가 무효)")

    if np.isfinite(mean_w) and mean_w < 0.5:
        LOG.info(f"평균 축소 신뢰도가 {mean_w:.2f} 입니다 — EA 원값의 약 "
                 f"{100*(1-mean_w):.0f}% 가 표본잡음이라는 뜻이며, 명세가 축소추정을 "
                 f"필수로 규정한 이유가 정량적으로 확인됩니다.")
    if beta_full.size:
        LOG.table([[c, (f"{b:+.6f}" if np.isfinite(b) else "제거됨(상수/공선)")]
                   for c, b in zip(Xcols, beta_full)],
                  ["통제변수", "계수(전기간 참고)"], ["l", "r"],
                  title="통제변수 계수 — 실적발표월·신규개시·공시건수는 EA 를 밀어올리는 "
                        "방향(양수)이어야 상식과 맞습니다")
    if dropped:
        LOG.warn(f"통제하지 못한 변수: {dropped}"
                 f"{' (DART_API_KEY 미입력 → 공시건수 없음)' if 'log_disclosure' in dropped else ''}. "
                 f"0 으로 채우지 않고 **열에서 제외**했습니다 — 0 채움은 '공시가 없었다'는 "
                 f"적극적 거짓이기 때문입니다. 통제가 그만큼 약하므로 결과를 할인해 읽으십시오.")
    if np.isfinite(corr_fw) and corr_fw < 0.95:
        LOG.warn(f"확장창 VAS 와 전기간 VAS 의 상관이 {corr_fw:.3f} 입니다. 전기간 회귀를 "
                 f"썼다면 미래 정보가 잔차에 상당히 섞였을 것이라는 뜻입니다. "
                 f"생산 경로는 확장창이므로 안전합니다.")
    if np.isfinite(r2) and r2 > 0.5:
        LOG.info(f"통제변수와 고정효과가 축소 EA 분산의 {100*r2:.0f}% 를 설명합니다. "
                 f"남은 {100*(1-r2):.0f}% 가 자발적 주의 서프라이즈(VAS)입니다 — "
                 f"기계적 발간이 원신호의 대부분이었다는 뜻이며 §6.3 이 필수인 이유입니다.")
    LOG.info("★ 해석 주의: SectorMonthFE 를 넣는 순간 AAR_pos 는 **구조적으로 섹터중립** "
             "신호가 됩니다. '반도체로 주의가 몰렸다' 같은 섹터 로테이션은 신호에서 완전히 "
             "제거됩니다. 설계 의도이지만 명시하지 않으면 결과 해석이 틀어집니다.")
    PIPE.io("OUT", "MEM", "attention_panel_vas", d)
    return downcast(d), pd.DataFrame(shr_diag_rows), pd.DataFrame(reg_rows)
