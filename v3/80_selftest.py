

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  자가검정 — 계약 검정 + 합성데이터 엔드투엔드 스모크                                       ║
# ║                                                                                          ║
# ║  둘은 서로 다른 것을 본다:                                                                ║
# ║   · 계약 검정 : 협상 불가 규칙(PIT·생존자편향·거부권·부호·결정성)이 코드에 실제로 있는가    ║
# ║   · 스모크    : 알파가 심어진 합성 패널에서 L2→L3 계산경로가 그 알파를 찾아내는가          ║
# ║  스모크가 통과해야 실데이터 수집을 시작한다. 수집에 30분 쓰고 계산부에서 죽는 것을 막는다.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TESTS: List[Tuple[str, str, bool, str]] = []


def _t(cid: str, name: str, ok: bool, detail: str = ""):
    TESTS.append((cid, name, bool(ok), detail))
    (LOG.ok if ok else LOG.error)(f"[{cid}] {name} — {'PASS' if ok else 'FAIL'}"
                                  + (f"  ({detail})" if detail else ""))


def make_synthetic_panel(n_code: int = 240, n_month: int = 72, seed: int = SEED
                         ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """알파가 **심어진** 합성 패널. 심어놓은 것을 못 찾으면 계산경로가 고장난 것이다."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2018-01-31", periods=n_month, freq="ME")
    codes = [f"{i:06d}" for i in range(1, n_code + 1)]
    idx = pd.MultiIndex.from_product([codes, months], names=["code", "month"])
    P = pd.DataFrame(index=idx).reset_index()
    n = len(P)

    # ── 잠재 구조 ────────────────────────────────────────────────────────────────────
    #  이 전략이 존재를 가정하는 구조를 그대로 합성한다. 세 가지를 의도적으로 넣는다:
    #
    #   ① **두 개의 독립 잠재축** A(개선) 과 B(대가 회피).
    #      수익은 max(A,0)×max(B,0) 에만 붙고 A 단독·B 단독에는 붙지 않는다.
    #      → 이래야 R2(TP vs 나이브)가 진짜 검정이 된다. 하나의 잠재축이 모든 센서와 수익을
    #        동시에 움직이면 나이브 팔도 똑같이 잘 맞혀서 R2 가 아무것도 구별하지 못한다.
    #   ② **지속성.** 전환 상태는 8~26개월 지속된다. 매월 독립난수면 청산 게이트·보유상한·
    #      회전율 경로가 전혀 검정되지 않고 회전율만 100% 로 튄다.
    #   ③ **보고 지연 3개월.** 센서는 잠재 상태를 3개월 늦게 드러낸다(DART 는 45~90일 후행).
    #      → 이래야 R1a(knowledge_date -120일)가 개선을 보여줄 수 있다. 지연이 없으면
    #        R1a 는 구조적으로 아무 변화도 못 만들고, 정상 하네스가 WARN 을 받는다.
    T = len(months)

    def _latent_block():
        start = rng.integers(0, T, size=n_code)
        dur = rng.integers(8, 27, size=n_code)
        M = np.zeros((n_code, T))
        for i in range(n_code):
            M[i, start[i]:min(T, start[i] + dur[i])] = 1.0
        return M * rng.normal(1.0, 0.35, size=n_code)[:, None]

    A_true, B_true = _latent_block(), _latent_block()
    LAG = 3                                        # 보고 지연(개월)
    A_obs = np.roll(A_true, LAG, axis=1); A_obs[:, :LAG] = 0.0
    B_obs = np.roll(B_true, LAG, axis=1); B_obs[:, :LAG] = 0.0
    a_obs, b_obs = A_obs.reshape(-1), B_obs.reshape(-1)     # (code, month) = MultiIndex 순서
    a_true, b_true = A_true.reshape(-1), B_true.reshape(-1)

    def _sen(base, load, noise):
        return base * load + rng.normal(0, noise, size=n)

    # A 계열 = 개선 축 (매출↑·설비↑·환원↑·인원↑)
    P["i_sales"] = _sen(a_obs, 1.0, 0.6)
    P["i_capex"] = _sen(a_obs, 0.9, 0.7)
    P["p_payout"] = _sen(a_obs, 0.8, 0.7)
    P["i_emp"] = _sen(a_obs, 0.8, 0.7)
    P["treasury_acq_amt"] = np.clip(_sen(a_obs, 0.6, 0.9) + 1.5, 0, None)
    # B 계열 = 대가를 치르지 않았음 (회전 유지·발생액 유지·ROIC 유지·투자 유지·생산성 유지)
    P["i_turn"] = _sen(b_obs, 1.0, 0.6)
    P["i_accr"] = _sen(b_obs, 0.8, 0.7)
    P["i_roic"] = _sen(b_obs, 0.9, 0.7)
    P["p_invest"] = _sen(b_obs, 0.8, 0.7)
    P["i_vapp"] = _sen(b_obs, 0.8, 0.7)
    P["p_cancel"] = np.clip(_sen(b_obs, 0.35, 0.35) + 0.4, 0, 1)
    P["b4_defrev"] = _sen((a_obs + b_obs) / 2, 0.05, 0.05)
    P["d1"] = _sen((a_obs + b_obs) / 2, 0.5, 0.9)              # 시장이 아직 반영 안 함
    P["d3"] = _sen((a_obs + b_obs) / 2, 0.4, 1.0)
    # 전환 중엔 이익이 늘고(dlog_E>0) 배수는 아직 안 늘었다(dlog_M<dlog_E) → 청산 게이트 유지
    P["dlog_E"] = 0.02 + (a_true + b_true) * 0.02 + rng.normal(0, 0.01, size=n)
    P["dlog_M"] = -0.01 + (a_true + b_true) * 0.003 + rng.normal(0, 0.01, size=n)
    P["v1_push"] = rng.random(size=n) * 2.0
    P["v2_bad"] = (rng.random(size=n) < 0.03).astype(float)
    P["v3_dilute"] = (rng.random(size=n) < 0.02).astype(float)
    P["v5_impair"] = (rng.random(size=n) < 0.01).astype(float)
    for c in ("q_gpa", "q_roa", "q_mom", "q_size", "q_bm"):
        P[c] = rng.normal(size=n)

    # 가격·유동성·시총
    P["close"] = 10000 * np.exp(np.cumsum(rng.normal(0, 0.06, size=n)) / 50)
    P["exec_px"] = P["close"]
    P["adv20"] = np.exp(rng.normal(20.5, 1.1, size=n))
    P["volume"] = 10000.0
    P["mcap"] = np.exp(rng.normal(25.5, 1.0, size=n))
    P["mcap_src"] = "synthetic"
    P["listed"] = True
    P["days_listed"] = 1e6
    P["industry"] = "SYN"
    P["ind_mid"] = "SYN" + (P["code"].astype(int) % 6).astype(str)
    P["ym"] = P["month"].dt.strftime("%Y%m")
    q = P.groupby("month")["mcap"].rank(pct=True)
    P["size_bucket"] = np.select([q <= 1/3, q <= 2/3], ["S", "M"], default="L")
    P["mcap_rank"] = P.groupby("month")["mcap"].rank(ascending=False, method="first")
    P["mcap_pct"] = P.groupby("month")["mcap"].rank(ascending=False, pct=True)
    P["in_band"] = P["mcap_rank"].between(20, 220)
    P["u_mid"] = P["in_band"] & (P["adv20"] >= 3e8)
    P["u_micro"] = False

    # ★ 심어놓은 알파: 두 잠재축이 **동시에** 켜졌을 때만 수익이 붙는다.
    #   A 단독·B 단독에는 보상이 없다 — 트레이드오프 쌍의 정의를 그대로 데이터에 넣은 것이고,
    #   이래야 R2(TP vs 나이브)가 구별력을 갖는다.
    both = np.maximum(a_true, 0) * np.maximum(b_true, 0)
    P["fwd_ret"] = (0.002 + 0.028 * (both / (both.std() + 1e-9))
                    + rng.normal(0, 0.070, size=n))
    P["ret_m"] = P.groupby("code")["fwd_ret"].shift(1).fillna(0.0)
    P["knowledge_date_fin"] = P["month"] - pd.Timedelta(days=50)

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "market": "KOSPI", "industry": "SYN",
                        "listing_date": pd.Timestamp("2010-01-01"),
                        "delisting_date": pd.NaT})
    # 생존자편향 검정용: 10% 는 중간에 폐지시킨다
    dl = rng.choice(codes, size=max(1, n_code // 10), replace=False)
    sec.loc[sec["code"].isin(dl), "delisting_date"] = months[len(months) // 2]
    return downcast(P), sec, months


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정", "협상 불가 규칙이 코드에 실제로 있는지 실행으로 확인한다")
    rng = np.random.default_rng(SEED)

    # ── TP 부호 (§6.5) ★ v3 최우선 교정 ───────────────────────────────────────────────
    cells = pd.Series(["c"] * 400)
    a = pd.Series(np.concatenate([np.full(200, -2.0), np.full(200, 2.0)]))
    b = pd.Series(np.concatenate([np.full(200, -2.0), np.full(200, 2.0)]))
    v = tp(a, b, cells)
    lo, hi = float(v.iloc[:200].max()), float(v.iloc[200:].min())
    _t("TP-SIGN", "TP 는 음수×음수를 최고점으로 만들지 않는다 (§6.5)",
       lo <= 1e-9 < hi, f"양쪽 음수 그룹 최대 {lo:.3f} / 양쪽 양수 그룹 최소 {hi:.3f}")
    old = tp_signed_product(xsec_z(a, cells), xsec_z(b, cells))
    _t("TP-SIGN2", "v2 원형(z×z)은 실제로 부호버그를 갖는다 (재현 확인)",
       float(old.iloc[:200].mean()) > 0,
       f"z×z 의 '양쪽 음수' 그룹 평균 {float(old.iloc[:200].mean()):+.3f} (양수면 버그 재현)")
    na = tp(pd.Series([1.0, np.nan] * 200), pd.Series([1.0] * 400), cells)
    _t("TP-NAN", "한쪽이 결측이면 TP 도 결측 (0 으로 채우지 않는다)",
       bool(na.isna().sum() >= 190), f"결측 {int(na.isna().sum())}/400")

    # ── C5 순서 ───────────────────────────────────────────────────────────────────────
    x = pd.Series(np.concatenate([rng.normal(size=99), [1e6]]))
    z = xsec_z(x, pd.Series(["c"] * 100))
    _t("C5", "winsorize(±2σ) → cell_z 순서가 극단값을 흡수한다",
       bool(np.isfinite(z).all() and z.abs().max() < 4.0),
       f"이상치 포함 z 최대 |{float(z.abs().max()):.2f}| (윈저 없으면 ~9.9)")
    inf_s = pd.Series(np.concatenate([rng.normal(size=99), [np.inf]]))
    zi = xsec_z(inf_s, pd.Series(["c"] * 100))
    _t("C5-INF", "±inf 를 먼저 NaN 으로 바꾼다 (안 하면 셀 전체 z 가 0 으로 뭉개짐)",
       bool(zi.iloc[:99].std() > 0.5), f"inf 1개 포함 시 나머지 z 표준편차 {float(zi.iloc[:99].std()):.2f}")

    # ── C6 거부권 ─────────────────────────────────────────────────────────────────────
    P = pd.DataFrame({"v1_push": [0.0, 2.0, 0.0], "v2_bad": [0.0, 0.0, 1.0],
                      "v3_dilute": 0.0, "v5_impair": 0.0,
                      "adv20": [1e9] * 3, "volume": [1e4] * 3})
    P = apply_vetoes(P, stage="M3", quiet=True)
    _t("C6", "거부권은 이진이며 상쇄되지 않는다",
       list(P["VETO"]) == [1, 0, 0], f"VETO={list(P['VETO'])} (기대 [1,0,0])")
    Pm = pd.DataFrame({"v1_push": [np.nan], "v2_bad": [np.nan], "v3_dilute": [np.nan],
                       "v5_impair": [np.nan], "adv20": [1e9], "volume": [1e4]})
    _t("C6-NA", "근거가 없으면(결측) 거부하지 않는다 (= 선택편향 방지)",
       int(apply_vetoes(Pm, stage="M3", quiet=True)["VETO"].iloc[0]) == 1)

    # ── 청산 게이트 4사분면 (§8.3) ────────────────────────────────────────────────────
    quad = {(0.01, 0.05): False,     # de>0, dm<de → 보유 (논거 유효)
            (0.06, 0.05): True,      # dm>=de     → 청산 (재분류 완료)
            (-0.01, -0.05): True,    # de<=0      → 청산 (논거 무효)
            (-0.06, -0.05): True}
    got = {k: exit_gate(*k) for k in quad}
    _t("EXIT", "청산 게이트가 네 사분면 전부에서 옳게 동작한다",
       got == quad, f"{got}")
    _t("EXIT-NA", "모르는 것(NaN)을 이유로 팔지 않는다", exit_gate(np.nan, 0.05) is False)

    # ── C8 결정성 ─────────────────────────────────────────────────────────────────────
    Ps, secs, ms = make_synthetic_panel(n_code=80, n_month=36)
    s1 = assemble_score(Ps, stage="M3", quiet=True)
    s2 = assemble_score(Ps.sample(frac=1.0, random_state=1).reset_index(drop=True),
                        stage="M3", quiet=True)
    j1 = s1.sort_values(["code", "month"])["Signal"].round(6).to_numpy()
    j2 = s2.sort_values(["code", "month"])["Signal"].round(6).to_numpy()
    same = bool(len(j1) == len(j2) and np.allclose(np.nan_to_num(j1), np.nan_to_num(j2), atol=1e-5))
    _t("C8", "행 순서를 섞어도 결과가 같다 (결정성 · 정렬 의존 없음)", same)
    b1 = run_backtest(s1, ms, secs, quiet=True)
    b2 = run_backtest(s2.sort_values(["code", "month"]).reset_index(drop=True), ms, secs, quiet=True)
    _t("C8-BT", "백테스트도 행 순서에 무관하다 (동점 처리가 결정적)",
       bool(np.allclose(b1["returns"]["ret"].fillna(0), b2["returns"]["ret"].fillna(0), atol=1e-9)))

    # ── C2 생존자편향 ─────────────────────────────────────────────────────────────────
    dl_codes = set(secs.loc[secs["delisting_date"].notna(), "code"])
    H = b1["holdings"]
    ever = bool(len(H) and len(set(H["code"]) & dl_codes) > 0)
    _t("C2", "상장폐지 종목이 폐지 전 구간에 실제로 보유될 수 있다",
       ever, f"보유된 폐지예정 종목 {len(set(H['code']) & dl_codes) if len(H) else 0}개")
    if len(H):
        dm = secs.set_index("code")["delisting_date"].to_dict()
        after = [(c, m) for c, m in zip(H["code"], H["month"])
                 if pd.notna(dm.get(c)) and m > dm[c] + pd.offsets.MonthEnd(1)]
        _t("C2-AFTER", "폐지 이후에는 보유되지 않는다", len(after) == 0, f"위반 {len(after)}건")

    # ── C13 유니버스 PIT ──────────────────────────────────────────────────────────────
    u = UniverseV3(Ps, secs, mode="rank")
    Pu = u.annotate(Ps, mode="rank")
    r = Pu.groupby("month")["mcap_rank"].max()
    _t("C13", "시총 랭크가 매 시점 독립적으로 재산출된다 (현재 시총 사용 금지)",
       bool(r.nunique() >= 1 and Pu["mcap_rank"].notna().sum() > 0),
       f"월별 최대 랭크 {int(r.min())}~{int(r.max())}")
    Pu2 = Pu.copy()
    Pu2.loc[Pu2["month"] == Pu2["month"].max(), "mcap"] *= 100      # 마지막 달만 시총 폭증
    Pu2 = u.annotate(Pu2, mode="rank")
    same_hist = bool((Pu2[Pu2["month"] < Pu2["month"].max()]["mcap_rank"].fillna(-1).to_numpy()
                      == Pu[Pu["month"] < Pu["month"].max()]["mcap_rank"].fillna(-1).to_numpy()).all())
    _t("C13-PIT", "미래 시총 변화가 과거 랭크를 바꾸지 않는다", same_hist)

    # ── C1 (merge_asof 출력 전수 검증) ────────────────────────────────────────────────
    grid = Ps[["code", "month"]].copy()
    src = pd.DataFrame({"code": Ps["code"].unique()[:50]})
    src["knowledge_date"] = pd.Timestamp("2019-06-30")
    src["xval"] = 1.0
    j = build_pit_panel(grid, {"t": src})
    bad = assert_c1(j, strict=False)
    _t("C1", "merge_asof 출력 전 행이 knowledge_date <= asof 를 만족한다", len(bad) == 0,
       "; ".join(bad) if bad else "위반 0행")
    src_bad = src.copy()
    src_bad["knowledge_date"] = pd.Timestamp("2099-01-01")
    jb = build_pit_panel(grid, {"bad": src_bad})
    got_bad = ("xval" not in jb.columns) or bool(jb["xval"].notna().sum() == 0)
    _t("C1-NEG", "미래 시점 소스는 아무 행에도 붙지 않는다 (음성 대조군)", got_bad)

    # ── 하한선 축수 정합성 ────────────────────────────────────────────────────────────
    s_m0 = assemble_score(Ps, stage="M0", quiet=True)
    s_m3 = assemble_score(Ps, stage="M3", quiet=True)
    _t("FLOOR", "단계에 도달하지 않은 센서군 때문에 전 종목이 탈락하지 않는다",
       bool(s_m0["FLOOR"].sum() > 0 and s_m3["FLOOR"].sum() > 0),
       f"M0 통과 {int(s_m0['FLOOR'].sum()):,} · M3 통과 {int(s_m3['FLOOR'].sum()):,}")

    # ── Signal_rank 는 월 전체 백분위 ────────────────────────────────────────────────
    g = s_m3.groupby("month")["Signal_rank"]
    _t("RANK", "Signal_rank 는 하위그룹이 아니라 월 전체에서 매겨진다",
       bool((g.max() <= 1.0 + 1e-6).all() and (g.nunique() > 5).mean() > 0.9),
       f"월별 고유값 중앙 {int(g.nunique().median())}개")

    # ── C10 계측 ─────────────────────────────────────────────────────────────────────
    with Stage("selftest.probe", budget_min=0.001):
        time.sleep(0.01)
    _t("C10", "모든 단계가 계측된다 (추측 금지)",
       any(r["stage"] == "selftest.probe" for r in RUNTIME_LOG))

    # ── VAULT: 사용자의 절대 1원칙을 계약으로 강제한다 ────────────────────────────────
    _t(*_vault_integrity_test())


def _vault_integrity_test() -> Tuple[str, str, bool, str]:
    """★ 절대 1원칙 — 기존 캐시·인덱스를 훼손하지 않는다.

    말이 아니라 실행으로 증명한다: 다른 스키마의 테이블 · uid 없는 레거시 인덱스 · 기존 blob
    이 있는 금고에 대고 **세 번** 새로 실행한 뒤, ① 기존 uid 가 하나도 사라지지 않았는가
    ② 레거시 행이 실행마다 중복되지 않았는가 ③ 기존 blob 파일이 그대로인가 를 확인한다.

    ②가 특히 중요하다. uid 를 '행 위치'로 만들면 저널이 길어질 때마다 같은 레거시 행이 새 uid
    를 받아 인덱스가 매 실행 불어난다. 데이터가 사라지진 않지만 인덱스는 망가지고, 그건
    이 원칙이 막으려던 바로 그 일이다. (실측으로 재현했던 결함)
    """
    global VAULT
    keep = VAULT
    tmp = tempfile.mkdtemp(prefix="tcd_vault_selftest_")
    try:
        V = Vault(tmp, "SELFTEST")
        VAULT = globals()["VAULT"] = V
        V.put_table("krx_ohlcv_daily", pd.DataFrame({"code": ["005930"], "close": [55000]}),
                    scope="shared")
        V.put_blob("research", "report_pdf", "old-1", b"%PDF-1.4 old", "pdf", scope="shared")
        V.flush(); V.compact("shared")
        legacy = os.path.join(V.ns["shared"], "index", "legacy_v1.csv")
        pd.DataFrame({"uid": ["", "", ""], "key": list("abc")}).to_csv(legacy, index=False)
        before = V.load_index("shared", force=True)
        uid0 = set(before["uid"].astype(str))
        blob0 = {os.path.join(r, f) for r, _d, fs in os.walk(V.blob_dir("shared")) for f in fs}

        n_leg = -1
        for run in range(3):
            V2 = Vault(tmp, "SELFTEST")
            VAULT = globals()["VAULT"] = V2
            V2.load_index("shared")
            # 스키마가 다른 새 테이블 + 기존 테이블 교체 + 동일 내용 blob 재기록
            V2.put_table("krx_marketcap_monthly", pd.DataFrame({"code": ["000660"], "mcap": [1e12]}),
                         scope="shared")
            V2.put_table("krx_ohlcv_daily",
                         pd.DataFrame({"code": ["000660"], "close": [95000], "amount": [1e9]}),
                         scope="shared")
            V2.put_blob("research", "report_pdf", "old-1", b"%PDF-1.4 old", "pdf", scope="shared")
            V2.flush(); V2.compact("shared")
            after = V2.load_index("shared", force=True)
            n_leg = int((after.get("_legacy_file", pd.Series(dtype=str)).astype(str)
                         == "legacy_v1.csv").sum())
        lost = uid0 - set(after["uid"].astype(str))
        blob1 = {os.path.join(r, f) for r, _d, fs in os.walk(V2.blob_dir("shared")) for f in fs}
        lost_blob = blob0 - blob1
        has_delete = any(k in dir(V2) for k in ("delete", "remove", "purge", "drop"))
        ok = (not lost) and (not lost_blob) and n_leg == 3 and not has_delete
        return ("VAULT", "기존 캐시·인덱스 훼손 불가 (절대 1원칙 · 3회 재실행)", ok,
                f"uid유실 {len(lost)} · blob유실 {len(lost_blob)} · 레거시행 {n_leg}(기대 3) · "
                f"삭제API {'있음' if has_delete else '없음'}")
    except Exception as e:                                       # noqa
        return ("VAULT", "기존 캐시·인덱스 훼손 불가 (절대 1원칙)", False,
                f"{type(e).__name__}: {str(e)[:60]}")
    finally:
        VAULT = globals()["VAULT"] = keep
        shutil.rmtree(tmp, ignore_errors=True)

    n_fail = sum(1 for *_x, ok, _d in [(a, b, c, d) for a, b, c, d in TESTS] if not ok)
    LOG.table([[c, _trunc(n, 46), "✔ PASS" if ok else "✘ FAIL", _trunc(d, 34)]
               for c, n, ok, d in TESTS],
              ["ID", "계약", "결과", "실측"], ["c", "l", "c", "l"], maxw=48)
    if n_fail and strict:
        raise RuntimeError(f"계약 검정 {n_fail}건 실패 — 실데이터 수집을 시작하지 않습니다. "
                           f"위 표에서 FAIL 항목을 확인하세요.")
    LOG.ok(f"계약 검정 {len(TESTS) - n_fail}/{len(TESTS)} 통과")
    return n_fail == 0


def run_smoke(full: bool = False) -> dict:
    """합성 패널로 L2 → L3 → 성과 → 강건성까지 전 출력물을 예행연습한다."""
    LOG.banner("합성데이터 엔드투엔드 스모크",
               "알파가 심어진 패널에서 계산경로가 그 알파를 찾아내는지 확인한다")
    P, sec, months = make_synthetic_panel(n_code=(300 if full else 160),
                                          n_month=(96 if full else 60))
    runner = make_runner(months, sec)
    S = assemble_score(P, stage="M3", quiet=not full)
    bt = run_backtest(S, months, sec, label="SMOKE", quiet=not full)
    s = perf_stats(bt["returns"])
    ok = np.isfinite(s.get("CAGR", np.nan)) and s.get("CAGR", -1) > 0
    LOG.table([[k, (f"{v:+.2%}" if k in ("CAGR", "MDD", "누적수익") and isinstance(v, float)
                    else f"{v:,.3f}" if isinstance(v, float) else str(v))]
               for k, v in s.items()], ["지표", "값"], ["l", "r"],
              title="스모크 성과 (심어놓은 알파를 찾았는가)")
    if not ok:
        LOG.error("합성 패널에 알파를 심어 두었는데도 성과가 나오지 않습니다. "
                  "L2→L3 계산경로가 고장난 것입니다 — 실데이터로 넘어가지 않습니다.")
        raise RuntimeError("스모크 실패: 심어놓은 알파를 계산경로가 찾지 못했습니다.")
    LOG.ok(f"스모크 통과 — 합성 CAGR {s['CAGR']:+.2%} (알파를 심어놨으므로 양수가 정상)")
    if full:
        bench = {}
        report_performance(bt, bench, title="스모크 성과 검증")
        base = R0_baseline(P, months, sec, runner)
        R1_leakage(P, months, sec, runner, bt)
        R2_tp_vs_naive(P, months, sec, runner, bt)
        R3_orthogonal(P, bt, months)
        R5_ablation(P, months, sec, runner, bt)
        R6_pbo()
        R7_regime(bt, {})
        R8_subperiod(bt)
        R9_capacity(P, months, sec, runner, bt)
        R10_policy(P, months, sec, runner, bt)
        report_robustness()
        report_interpretation(S, bt)
        diagnostic_card(S, bt, sec)
        report_stage_matrix()
    return {"panel": S, "backtest": bt, "sec": sec, "months": months}
