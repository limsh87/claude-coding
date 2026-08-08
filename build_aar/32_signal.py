

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  종목 단위 신호 — AAR_pos / AAR_neg / AAR_total 과 포트폴리오 구성                   ║
# ║                                                                                          ║
# ║  §6.4  AAR_pos(i,t) = Σ_a ω(a,t)·VAS(a,i,t) / Σ_a ω(a,t)                                 ║
# ║  §6.6  AAR_total    = z(AAR_pos) + λ·z(AAR_neg)                                          ║
# ║  §7    5분위 → Q5 롱온리 동일가중 → AAR_neg 하위 10% 강제 배제 → 하한 20종목              ║
# ║                                                                                          ║
# ║  ★★ 결측을 0 으로 채우면 신호가 **정반대로 뒤집힌다.** ★★                                 ║
# ║     AAR_pos 결측은 "주의 재배분이 0" 이 아니라 "주의를 잴 애널리스트가 없음" 이다.         ║
# ║     유니버스 2,400 중 커버 700 인 상황에서 0 으로 채우면 0 이 전체의 70.8% 를 차지해       ║
# ║     80분위수 자체가 정확히 0.0 이 되고, **채워진 미커버 종목 1,700개가 Q5 에 동점 진입**   ║
# ║     한다(Q5 크기 140 → 2,060). 신호가 "커버리지 없음 = 최상위 매수" 로 뒤집히는 것이다.    ║
# ║     → 채우지 말고 **유니버스를 제한(restrict)** 한다: U(t) = {유효 애널 2명 이상}.         ║
# ║                                                                                          ║
# ║  ★★ AAR_neg 는 윈저라이즈하지 않는다. ★★                                                  ║
# ║     치역이 [-1.5, 0] 으로 구조적으로 유계이고 90% 이상이 정확히 0 인 점질량 분포라,        ║
# ║     ±3σ 절단이 최악의 철회 5건을 단일값 하나로 붕괴시킨다(z: -7.86/-7.63/… → 전부 -4.415). ║
# ║     이 신호가 존재하는 이유인 사건을 정확히 지우는 셈이다.                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MIN_ANALYSTS_U = 2      # U(t) 편입 최소 유효 애널 수. 사전 고정 — 격자를 늘리지 않는다.


def build_aar_pos(V: "pd.DataFrame", weight_mode: str) -> "pd.DataFrame":
    """종목×월 AAR_pos + 유효 애널 수.

    ω(a,t) — §6.4 의 세 가지 기회비용 가중. H2 는 "기회비용 가중이 비가중보다 강하다"는
    메커니즘 조건부 예측이며, 한가한 애널리스트에서 더 강하면 데이터마이닝으로 판정된다.
      uw       : 1              (비가중)
      nreports : N(a,t)         (그 달 발간량 = 바쁜 정도)
      ncover   : 커버 종목 수   (커버리지 폭)
    """
    cols = ["code", "month", "aar_pos", "n_analyst", "w_mode"]
    if V is None or V.empty or "VAS" not in V.columns:
        return pd.DataFrame(columns=cols)
    d = V.dropna(subset=["VAS"]).copy()
    if d.empty:
        return pd.DataFrame(columns=cols)
    if weight_mode == "nreports":
        w = pd.to_numeric(d["N_t"], errors="coerce")
    elif weight_mode == "ncover":
        w = (d.groupby(["unit_id", "month"], observed=True)["code"]
              .transform("nunique").astype("float64"))
    else:
        w = pd.Series(1.0, index=d.index)
    d["_w"] = w.where(np.isfinite(w) & (w > 0), 1.0)
    d["_wv"] = d["_w"] * d["VAS"].astype("float64")
    g = d.groupby(["code", "month"], observed=True)
    out = g.agg(_num=("_wv", "sum"), _den=("_w", "sum"),
                n_analyst=("unit_id", "nunique")).reset_index()
    out["aar_pos"] = out["_num"] / out["_den"].where(out["_den"] > 0)
    out["w_mode"] = weight_mode
    return out[cols]


def assemble_signal(pos: "pd.DataFrame", neg: "pd.DataFrame", uni: "pd.DataFrame",
                    lam: float) -> "pd.DataFrame":
    """AAR_total = z(AAR_pos) + λ·z(AAR_neg). 유니버스는 U(t) 로 **제한**한다."""
    cols = ["code", "month", "aar_pos", "aar_neg", "z_pos", "z_neg", "aar_total",
            "n_analyst", "n_drop"]
    if pos is None or pos.empty:
        return pd.DataFrame(columns=cols)
    U = pos[pos["n_analyst"] >= MIN_ANALYSTS_U].copy()
    if U.empty:
        LOG.warn(f"유효 애널 {MIN_ANALYSTS_U}명 이상인 종목-월이 없습니다 — 신호를 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    # PIT 유니버스와 교집합 (상장·보통주·시총>0 조건을 통과한 것만)
    if uni is not None and len(uni):
        key = set(zip(as_str_series(uni["code"]), uni["month"]))
        U = U[[(c, m) in key for c, m in zip(as_str_series(U["code"]), U["month"])]]
    if U.empty:
        return pd.DataFrame(columns=cols)

    if neg is not None and len(neg):
        U = U.merge(neg[["code", "month", "aar_neg", "n_drop"]], on=["code", "month"], how="left")
    else:
        U["aar_neg"] = np.nan
        U["n_drop"] = np.nan
    # ★ AAR_neg 결측은 '철회 사건 없음' = 0 이 맞다(AAR_pos 결측과 성질이 다르다).
    #   AAR_pos 결측은 '잴 수 없음'이라 0 으로 채우면 거짓이지만,
    #   AAR_neg 는 U(t) 안에 있는 이상 커버 로스터가 존재하므로 '철회 0건'이 실제 관측이다.
    U["aar_neg"] = pd.to_numeric(U["aar_neg"], errors="coerce").fillna(0.0)
    U["n_drop"] = pd.to_numeric(U["n_drop"], errors="coerce").fillna(0.0)

    U["z_pos"] = xsec_z(U["aar_pos"], U["month"], min_n=CELL_MIN_N, k=WINSOR_SIGMA)
    U["z_neg"] = xsec_z(U["aar_neg"], U["month"], min_n=CELL_MIN_N, k=None)   # ★ 윈저 금지
    U["aar_total"] = U["z_pos"].astype("float64") + float(lam) * U["z_neg"].astype("float64")
    return U[cols]


def select_portfolio(S: "pd.DataFrame", month, uni_obj: Optional["Universe"] = None
                     ) -> Tuple[List[str], dict]:
    """5분위 → Q5 → AAR_neg 하위 10% 강제 배제 → 하한 검사. **순서 고정.**

    ★ 순진한 구현 `aar_neg <= aar_neg.quantile(0.10)` 은 재앙이다. 10분위수가 정확히 0.0
      이므로 그 한 줄이 유니버스 **전부를 배제**하고 포트폴리오가 조용히 전액 현금이 된다.
      '엄격히 음수' 조건과 rank(method='min') 을 함께 써야 무붕괴다. 하위10% 는 상한으로
      해석한다 — 철회가 10%보다 적은 달에는 배제도 그만큼만 일어난다.
    ★ 배제 임계는 **U(t) 전체 기준**이다. Q5 부분집합 기준으로 잡으면 매달 Q5 의 10% 가
      기계적으로 잘려나간다. 그리고 하드 거부권은 반드시 **마지막**에 적용한다 —
      배제를 먼저 하고 재분위하면 분위 경계가 이동해 거부권이 희석된다.
    """
    info = {"n_U": 0, "n_q5": 0, "n_excl": 0, "n_port": 0, "cash": False}
    sub = S[(S["month"] == month) & S["aar_total"].notna()]
    n_u = len(sub)
    info["n_U"] = n_u
    if n_u < PORT_QUANTILES * 2:
        info["cash"] = True
        return [], info
    try:
        q = pd.qcut(sub["aar_total"].rank(method="first"), PORT_QUANTILES,
                    labels=False, duplicates="drop")
    except Exception:
        info["cash"] = True
        return [], info
    top = int(np.nanmax(q.to_numpy())) if len(q) else 0
    q5 = sub[q == top]
    info["n_q5"] = len(q5)

    k = int(np.ceil(NEG_EXCLUDE_PCT * n_u))
    rk = sub["aar_neg"].rank(method="min", ascending=True)
    excl = set(as_str_series(sub.loc[(sub["aar_neg"] < 0) & (rk <= k), "code"]))
    info["n_excl"] = len(excl)

    port = [c for c in as_str_series(q5["code"]).tolist() if c not in excl]
    info["n_port"] = len(port)
    if len(port) < PORT_MIN_NAMES:
        info["cash"] = True
        return [], info
    return port, info


# ── 나이브 벤치마크 신호 (§8 — 통제의 가치를 보여주는 진짜 비교 대상) ───────────────────────
def build_naive_signal(L: "pd.DataFrame", months: "pd.DatetimeIndex",
                       uni: "pd.DataFrame") -> "pd.DataFrame":
    """"단순 리포트 건수 증가" 신호. **§6.3 통제를 전혀 하지 않은** 순진한 버전이다.

    이것이 AAR 의 진짜 비교 대상이다. AAR 이 이걸 못 이기면 §6.3 통제회귀와 축소추정,
    인과분해 전부가 불필요한 복잡도라는 뜻이고, 그 사실을 그대로 보고해야 한다.
    (KOSPI 를 이기는 것은 아무것도 증명하지 못한다 — 소형주 프리미엄일 수 있다)
    """
    cols = ["code", "month", "naive", "aar_total"]
    if L is None or L.empty:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    cnt = (x.groupby(["code", "month"], observed=True)["report_uid"]
            .nunique().rename("n").reset_index())
    all_m = pd.DatetimeIndex(sorted(set(cnt["month"].unique()) | set(months)))
    mp = {m: i for i, m in enumerate(all_m)}
    c_codes, c_uniq = pd.factorize(cnt["code"])
    M = np.zeros((len(c_uniq), len(all_m)), dtype=np.float32)
    np.add.at(M, (np.asarray(c_codes, dtype=np.int64),
                  cnt["month"].map(mp).to_numpy(dtype=np.int64)),
              cnt["n"].to_numpy(dtype=np.float32))
    base = np.zeros_like(M)
    cs = np.cumsum(M, axis=1)
    base[:, 1:] = cs[:, :-1]
    lag = np.zeros_like(M)
    if len(all_m) > LOOKBACK_M:
        lag[:, LOOKBACK_M + 1:] = cs[:, :len(all_m) - LOOKBACK_M - 1]
    base = (base - lag) / float(LOOKBACK_M)
    raw = M - base
    ci, ti = np.where((M > 0) | (base > 0))
    out = pd.DataFrame({"code": np.asarray(c_uniq)[ci], "month": all_m.to_numpy()[ti],
                        "naive": raw[ci, ti].astype("float64")})
    out = out[out["month"].isin(months)]
    if uni is not None and len(uni):
        key = set(zip(as_str_series(uni["code"]), uni["month"]))
        out = out[[(c, m) in key for c, m in zip(as_str_series(out["code"]), out["month"])]]
    out["aar_total"] = xsec_z(out["naive"], out["month"], min_n=CELL_MIN_N)
    out["aar_neg"] = 0.0
    out["n_analyst"] = np.nan
    LOG.info(f"나이브 신호(단순 리포트 건수 증가) {len(out):,}행 — §6.3 통제 없음. "
             f"AAR 이 이것을 이기지 못하면 통제회귀·축소추정·인과분해가 전부 불필요한 "
             f"복잡도라는 뜻입니다.")
    return out


def signal_grid() -> List[dict]:
    """§6.6 사전등록 파라미터 격자 — 정확히 12개. **확장 금지.**"""
    g = []
    for w in GRID_WEIGHTS:
        for lam in GRID_LAMBDA:
            for h in GRID_HOLD:
                g.append({"weight": w, "lam": lam, "hold": h,
                          "label": f"{w}|λ{lam:g}|{h}M"})
    if len(g) != 12:
        raise KillCriteria(
            f"사전등록 격자가 {len(g)}개입니다(12개여야 함). §6.6 은 3×2×2 로 고정되어 "
            f"있으며 확장은 사전등록 위반입니다. GRID_WEIGHTS/GRID_LAMBDA/GRID_HOLD 를 "
            f"원래 값으로 되돌리세요.")
    return g
