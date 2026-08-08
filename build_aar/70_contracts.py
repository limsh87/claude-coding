

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 — 주석이나 관례는 무효. 테스트로만 강제한다.                                ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ║                                                                                          ║
# ║  여기 있는 검사는 전부 **실제로 겪었거나 실측으로 재현된 실패**를 고정한 것이다.           ║
# ║  "그럴 리 없다"고 생각되는 항목일수록 과거에 조용히 틀렸던 것이다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACTS.append({"id": cid, "name": name, "pass": bool(ok), "msg": msg})
    return ok


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACTS.clear()
    rng = np.random.default_rng(SEED)

    # ── PIT 강제 ──────────────────────────────────────────────────────────────────────
    def c_pit():
        d = pd.DataFrame({"code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 필터가 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 등록 거부 확인"

    _c("PIT", "Point-In-Time 강제", c_pit)

    # ── 날짜 규약: as_ts 와 as_ts_series 가 같은 값을 낼 것 (KST 벽시계) ────────────────
    def c_tz():
        cases = ["2020-01-15 08:00:00+09:00", "2020-01-15 23:30:00+09:00",
                 "2020-01-15", "2020-01-15 00:00:00+00:00"]
        for s in cases:
            a = as_ts(s)
            b = as_ts_series([s]).iloc[0]
            if a is None or pd.isna(b) or a != b:
                return False, (f"★as_ts({s!r})={a} 인데 as_ts_series 는 {b} 입니다. "
                               f"두 함수가 다른 날짜를 내면 knowledge_date 가 하루 어긋나 "
                               f"PIT 를 정면 위반합니다.")
        if as_ts("2020-01-15 08:00:00+09:00") != as_ts("2020-01-15"):
            return False, ("★KST 09시 이전 시각이 전날로 밀렸습니다. tz_convert(None) 은 "
                           "UTC 변환이라 한국 데이터에 쓰면 안 됩니다.")
        mixed = as_ts_series(["2020-01-15 08:00:00+09:00", "2020-01-16"])
        if mixed.isna().any():
            return False, "타임존이 섞인 열에서 결측이 발생했습니다"
        if str(mixed.dtype) != "datetime64[ns]":
            return False, f"날짜 단위가 ns 가 아닙니다({mixed.dtype}) — merge_asof 가 실패합니다"
        return True, "KST 벽시계 일치 · tz 혼재 흡수 · datetime64[ns] 고정 확인"

    _c("TZ", "날짜 정규화 규약", c_tz)

    # ── A4: 축소추정 — 단조성·경계·자유도 0 ────────────────────────────────────────────
    def c_eb():
        n = 600
        unit = np.repeat([f"u{i}" for i in range(60)], 10)
        Nt = np.tile(np.array([3, 5, 8, 12, 20, 40, 60, 90, 140, 200], dtype=float), 60)
        Nlb = Nt * 12
        rt = rng.binomial(np.maximum(Nt, 1).astype(int), 0.1).astype(float)
        rlb = rng.binomial(np.maximum(Nlb, 1).astype(int), 0.1).astype(float)
        df = pd.DataFrame({"unit_id": unit, "house": np.repeat(["h1", "h2"], n // 2),
                           "sector": np.tile(["s1", "s2", "s3"], n // 3),
                           "r_t": rt, "N_t": Nt, "r_lb": rlb, "N_lb": Nlb})
        df["v"] = ea_analytic_var(df["r_t"], df["N_t"], df["r_lb"], df["N_lb"])
        df["EA"] = df["r_t"] / df["N_t"] - df["r_lb"] / df["N_lb"]
        if not (df["v"] > 0).all():
            return False, "해석적 분산에 비양수가 있습니다"
        sh, w, diag = eb_shrink_tau2(df, "unit_id", "house", "sector", "EA", "v")
        if not ((w >= -1e-9) & (w <= 1 + 1e-9)).all():
            return False, f"신뢰도 w 가 [0,1] 밖입니다: {float(w.min()):.3f}~{float(w.max()):.3f}"
        if not (sh.abs() <= df["EA"].abs() + 1e-9).all():
            return False, "★축소 결과가 원값보다 큽니다 — 0 을 향한 축소가 아닙니다"
        lo = df["N_t"] <= 8
        hi = df["N_t"] >= 90
        if float(w[lo.to_numpy()].mean()) >= float(w[hi.to_numpy()].mean()):
            return False, (f"★단조성 위반: 관측이 적은 쪽(w={float(w[lo.to_numpy()].mean()):.3f})이 "
                           f"많은 쪽(w={float(w[hi.to_numpy()].mean()):.3f})보다 덜 축소되었습니다. "
                           f"관측이 적을수록 사전분포로 강하게 끌어당겨야 합니다(§6.2).")
        return True, (f"w∈[0,1] · |축소값|≤|원값| · 관측수 단조성 확인 "
                      f"(적은쪽 w={float(w[lo.to_numpy()].mean()):.3f} < "
                      f"많은쪽 {float(w[hi.to_numpy()].mean()):.3f})")

    _c("A4", "경험적 베이즈 축소추정", c_eb)

    # ── 고정효과 흡수: 싱글턴 처리 · NaN 오염 방지 · 수렴 ───────────────────────────────
    def c_fe():
        n = 4000
        a = rng.integers(0, 200, n)
        s = rng.integers(0, 150, n)
        x = rng.normal(size=(n, 2))
        y = 1.5 * x[:, 0] - 0.8 * x[:, 1] + rng.normal(0, 0.3, n) \
            + np.bincount(a, minlength=200)[a] * 0.0 + a * 0.001 + s * 0.002
        r, b, kr, kc, info = absorb_2way(y, x, [a, s], [200, 150], strict=False)
        if not info.get("converged", False):
            return False, f"수렴 실패 (iters={info.get('iters')})"
        if b.size < 2 or not np.isfinite(b[:2]).all():
            return False, "계수를 추정하지 못했습니다"
        if abs(b[0] - 1.5) > 0.08 or abs(b[1] + 0.8) > 0.08:
            return False, f"계수 복원 실패: {b[:2]} (기대 [1.5, -0.8])"
        # NaN 오염 — bincount 는 NaN 을 무시하지 않는다
        y2 = y.copy()
        y2[7] = np.nan
        r2, _, kr2, _, info2 = absorb_2way(y2, x, [a, s], [200, 150], strict=False)
        if not np.isfinite(r2).all():
            return False, "★NaN 이 잔차로 전파되었습니다 — 완전관측 마스크가 동작하지 않습니다"
        if kr2[7]:
            return False, "NaN 행이 회귀에 포함되었습니다"
        # 싱글턴 — 잔차가 정확히 0 이 되는 가짜 관측을 만들면 안 된다
        a3 = np.concatenate([a, [999]])
        s3 = np.concatenate([s, [999]])
        y3 = np.concatenate([y, [1.0]])
        x3 = np.vstack([x, [[0.0, 0.0]]])
        _, _, kr3, _, info3 = absorb_2way(y3, x3, [a3, s3], [1000, 1000], strict=False)
        if kr3[-1]:
            return False, ("★싱글턴 셀 행이 회귀에 남았습니다. 그 잔차는 정확히 0 이 되어 "
                           "'주의 이상 없음'이라는 가짜 관측으로 VAS 에 흘러갑니다.")
        return True, (f"계수 복원 정확 · NaN 격리 · 싱글턴 제거 "
                      f"{info3.get('n_singleton_dropped', 0)}행 · 수렴 {info.get('iters')}회")

    _c("FE", "고정효과 흡수 회귀", c_fe)

    # ── A9: 결측 채움 금지 + AAR_neg 배제 규칙이 유니버스를 전멸시키지 않을 것 ──────────
    def c_fill():
        n = 700
        S = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": as_ts("2020-06-30"),
            "aar_pos": rng.normal(0, 0.04, n),
            "n_analyst": rng.integers(2, 8, n),
            "n_drop": 0.0,
        })
        # 90.7% 가 정확히 0 인 점질량 분포 (실제 AAR_neg 분포와 동일 성질)
        neg = np.zeros(n)
        k = int(n * 0.093)
        neg[:k] = -rng.uniform(0.2, 1.5, k)
        rng.shuffle(neg)
        S["aar_neg"] = neg
        S["z_pos"] = xsec_z(S["aar_pos"], S["month"], min_n=5)
        S["z_neg"] = xsec_z(S["aar_neg"], S["month"], min_n=5, k=None)
        S["aar_total"] = S["z_pos"].astype("float64") + 1.0 * S["z_neg"].astype("float64")

        # 순진한 구현: quantile(0.10) → 10분위수가 0.0 이라 전체 배제
        naive_thr = float(S["aar_neg"].quantile(NEG_EXCLUDE_PCT))
        naive_excl = int((S["aar_neg"] <= naive_thr).sum())
        port, info = select_portfolio(S, as_ts("2020-06-30"))
        if naive_excl < n * 0.5:
            return False, "테스트 전제 오류: 순진한 배제가 재앙적이지 않습니다"
        if info["n_excl"] > n * 0.15:
            return False, (f"★배제가 {info['n_excl']}/{n} 종목으로 폭주했습니다. "
                           f"'엄격히 음수' 조건과 rank(method='min') 을 함께 써야 합니다.")
        if not port:
            return False, (f"★포트폴리오가 비었습니다(전액 현금). 순진한 quantile 배제가 "
                           f"{naive_excl}/{n} 를 배제하는 분포에서 무붕괴여야 합니다.")
        if len(port) < PORT_MIN_NAMES:
            return False, f"보유 {len(port)}종목으로 하한 미달"
        # 윈저라이즈 금지 — 최악 사건들이 하나로 붕괴하면 안 된다
        worst = S.nsmallest(5, "aar_neg")["z_neg"].to_numpy()
        if len(np.unique(np.round(worst, 6))) < 3:
            return False, ("★AAR_neg 최악 5건의 z 가 뭉개졌습니다. 윈저라이즈가 이 신호의 "
                           "존재 이유인 극단 철회 사건을 정확히 지웁니다(k=None 이어야 함).")
        return True, (f"순진한 배제 {naive_excl}/{n}(재앙) vs 올바른 배제 {info['n_excl']}/{n} · "
                      f"보유 {len(port)}종목 · 극단 철회 {len(np.unique(np.round(worst,6)))}단계 보존")

    _c("A9", "결측 채움 금지 · 배제 규칙 무붕괴", c_fill)

    # ── A5: 사전등록 격자가 정확히 12개일 것 ───────────────────────────────────────────
    def c_grid():
        g = signal_grid()
        if len(g) != 12:
            return False, f"격자가 {len(g)}개입니다 (12개여야 함)"
        if len(set(x["label"] for x in g)) != 12:
            return False, "격자 라벨에 중복이 있습니다"
        fixed = {"LOOKBACK_M": (LOOKBACK_M, 12), "MIN_REPORTS_MON": (MIN_REPORTS_MON, 3),
                 "MIN_LOOKBACK_N": (MIN_LOOKBACK_N, 12), "NEG_W_VDROP": (NEG_W_VDROP, 1.0),
                 "NEG_W_HEXIT": (NEG_W_HEXIT, 1.5), "COVER_WINDOW_M": (COVER_WINDOW_M, 12),
                 "PORT_QUANTILES": (PORT_QUANTILES, 5), "NEG_EXCLUDE_PCT": (NEG_EXCLUDE_PCT, 0.10),
                 "PORT_MIN_NAMES": (PORT_MIN_NAMES, 20), "POS_MAX_WEIGHT": (POS_MAX_WEIGHT, 0.05)}
        bad = [k for k, (got, want) in fixed.items() if abs(float(got) - float(want)) > 1e-12]
        if bad:
            return False, (f"★사전등록 고정값이 변경되었습니다: {bad}. 이 값들은 명세가 "
                           f"'튜닝 대상이 아니다'라고 명시한 상수입니다.")
        return True, f"격자 12개 · 고정 상수 {len(fixed)}개 전부 명세값 유지"

    _c("A5", "사전등록 파라미터 고정", c_grid)

    # ── A6: BH-FDR 정확성 ──────────────────────────────────────────────────────────────
    def c_fdr():
        p = np.array([0.001, 0.008, 0.039, 0.041, 0.9])
        rej, padj = bh_fdr(p, q=0.10)
        if not (rej[0] and rej[1]):
            return False, f"명백히 유의한 p 가 기각되지 않았습니다: {rej}"
        if rej[4]:
            return False, "p=0.9 가 기각되었습니다"
        if not np.all(np.diff(padj[np.argsort(p)]) >= -1e-12):
            return False, "보정 p 가 단조가 아닙니다"
        rej2, _ = bh_fdr([np.nan, np.nan], q=0.10)
        if rej2.any():
            return False, "전부 결측인 입력에서 기각이 발생했습니다"
        return True, f"BH 절차 정확 · 보정 p 단조 · 결측 안전 (기각 {int(rej.sum())}/5)"

    _c("A6", "BH-FDR 다중검정 보정", c_fdr)

    # ── A1: 커버리지 격자 완전성 — 철회가 데이터에 나타날 것 ───────────────────────────
    def c_drop():
        """세 시나리오를 한 번에 검정한다:
             a0 : b1 소속, 000001 을 4분기 연속 커버하다 중단. 다른 종목은 계속 발간 → V-DROP
             a1 : b1 소속, 000001 을 계속 커버              → 하우스는 살아 있음(H-EXIT 아님)
             a2 : b2 소속, 000001 을 계속 커버              → 시장 커버가 0 이 되지 않음
             a3 : b3 소속, 000001 커버하다 중단 + **전 종목 발간 중단** → M-EXIT
             a4 : b3 소속, 계속 발간 → b3 의 소스 건강 유지 (없으면 a3 의 침묵이
                  '증권사 전체 발간 급감'과 구별되지 않아 CENSORED-SOURCE 로 빠진다.
                  이 가드가 분류보다 먼저 도는 것이 설계 의도다 — §3.4)
        """
        # 48개월 — 사건(26개월째) 이후 검증용 확정지연 12개월의 여유를 확보한다.
        # 짧게 잡으면 우측절단으로 검증용 라벨이 전량 사라지는데, 그건 버그가 아니라
        # 설계된 동작이므로 표본 길이로 해결해야 한다(§7-F12).
        ms = pd.date_range("2018-01-31", periods=48, freq="ME")
        rows = []

        def emit(a, b, code, k, m, tag):
            rows.append({"report_uid": f"{tag}_{a}_{code}_{k}", "analyst_id": a,
                         "broker_legal_id": b, "broker_legal_name": b,
                         "broker_id": b, "broker_name": b,
                         "code": code, "month": m, "pub_date": m, "category": "기업",
                         "target_price": None, "opinion": None})
        for k, m in enumerate(ms):
            if k < 24:
                emit("a0", "b1", "000001", k, m, "x")       # a0 은 24개월째부터 000001 중단
            emit("a0", "b1", "000002", k, m, "o")           # 다른 종목은 계속 → 재직 중
            emit("a1", "b1", "000001", k, m, "x")           # 하우스 잔여 커버
            emit("a2", "b2", "000001", k, m, "x")           # 시장 커버 유지
            if k < 24:
                emit("a3", "b3", "000001", k, m, "x")       # a3 은 24개월째부터 전면 침묵
                emit("a3", "b3", "000003", k, m, "o")
            for j in range(4):                              # a4 가 b3 의 발간량을 유지시킨다
                emit("a4", "b3", "000003", k * 10 + j, m, f"h{j}")
        L = pd.DataFrame(rows)
        aids = ["a0", "a1", "a2", "a3", "a4"]
        A = pd.DataFrame({"analyst_id": aids, "analyst_person_id": aids,
                          "person_unclassified": False})
        codes = ["000001", "000002", "000003"]
        sec = pd.DataFrame({"code": codes, "delisting_date": [pd.NaT] * 3})
        uni = pd.DataFrame([{"code": c, "month": m} for c in codes for m in ms])
        out = classify_coverage_drops(L, A, pd.DatetimeIndex(ms), sec, uni)
        S = out["signal"]
        if S is None or S.empty:
            return False, ("★4분기 연속 커버 후 침묵인데 철회 사건이 하나도 잡히지 "
                           "않았습니다. 커버 격자가 '리포트가 있는 달'만 담고 있으면 "
                           "진짜 철회가 데이터에 절대 나타나지 않습니다.")
        a0 = S[(S["code"] == "000001") & (S["analyst_id"] == "a0")]
        if a0.empty:
            return False, "재직 중 철회(a0)가 탐지되지 않았습니다"
        if set(a0["klass"]) != {"V-DROP"}:
            return False, (f"★a0 은 재직 중(000002 계속 발간)이고 하우스도 살아 있으므로 "
                           f"V-DROP 이어야 하는데 {sorted(set(a0['klass']))} 로 분류됐습니다. "
                           f"M-EXIT 으로 새면 플라시보군이 오염돼 인과분해가 무너집니다.")
        a3 = S[(S["code"] == "000001") & (S["analyst_id"] == "a3")]
        if a3.empty or set(a3["klass"]) != {"M-EXIT"}:
            return False, (f"★a3 은 전 종목 발간을 멈췄으므로 M-EXIT 이어야 하는데 "
                           f"{sorted(set(a3['klass'])) if len(a3) else '미탐지'} 입니다. "
                           f"자발적 철회로 새면 음의 신호가 기계적 사건으로 오염됩니다.")
        if len(out["verify"]) == 0:
            return False, "검증용 라벨이 생성되지 않았습니다"
        return True, (f"V-DROP(재직 중 철회) · M-EXIT(전면 침묵) 정확 분리 · "
                      f"사건 {len(S)}건 · 검증용 {len(out['verify'])}건")

    _c("A1", "커버리지 철회 탐지 · 분류", c_drop)

    # ── 횡단면 통계: winsor 순서 · ±inf 무해화 · k=None ───────────────────────────────
    def c_xsec():
        # ★ 검정해야 할 성질은 'max z 가 작아지는가'가 아니라
        #   **서로 다른 극단값이 하나로 뭉개지는가** 다. 단일 이상치 하나만 두면
        #   윈저라이즈 후 재표준화 때문에 max z 가 거의 그대로라 아무것도 못 잡는다.
        v = pd.Series([0.0] * 40 + [8.0, 9.0, 10.0, 11.0, 12.0])
        cell = pd.Series(["A"] * 45)
        z = xsec_z(v, cell, min_n=5)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        nz_w = len(np.unique(np.round(z.nlargest(5).to_numpy(), 6)))
        zn = xsec_z(v, cell, min_n=5, k=None)
        nz_r = len(np.unique(np.round(zn.nlargest(5).to_numpy(), 6)))
        if nz_w >= nz_r:
            return False, (f"★윈저라이즈가 극단값을 뭉개지 않았습니다 "
                           f"(윈저 {nz_w}단계 vs 원값 {nz_r}단계). 검정 전제가 깨졌습니다.")
        if nz_r < 5:
            return False, (f"★k=None 인데 극단값 5개가 {nz_r}단계로 뭉개졌습니다. "
                           f"AAR_neg 는 이 경로를 쓰므로 최악의 철회 사건이 지워집니다.")
        vi = pd.Series([1.0, 2.0, 3.0, np.inf, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        zi = xsec_z(vi, pd.Series(["A"] * 10), min_n=5)
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, ("★±inf 오염: 셀에 inf 가 하나 있으면 z 가 전부 뭉개집니다. "
                           "해당 셀의 신호가 통째로 소실됩니다.")
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]), min_n=5)
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 으로 처리되지 않았습니다(0으로 채우면 안 됩니다)"
        return True, "winsor→z 순서 · k=None 분기 · ±inf 무해화 · 표본부족 NaN 확인"

    _c("XSEC", "횡단면 통계", c_xsec)

    # ── 결정성 ─────────────────────────────────────────────────────────────────────────
    def c_det():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell, min_n=5)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1], min_n=5).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 순서 무관 결과 동일 확인"

    _c("DET", "결정성", c_det)

    # ── 종목코드 정규화 (2024 영숫자 티커) ─────────────────────────────────────────────
    def c_code():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) 모두 정상"

    _c("CODE", "종목코드 정규화", c_code)

    # ── 수집 파서 회귀 ─────────────────────────────────────────────────────────────────
    def c_parse():
        for raw, exp in (("26.01.19", "2026-01-19"), ("19.12.31", "2019-12-31"),
                         ("24.11.30", "2024-11-30"), ("2020-05-01", "2020-05-01")):
            if parse_kr_date(raw) != exp:
                return False, (f"★날짜 파싱: {raw} → {parse_kr_date(raw)} (기대 {exp}). "
                               f"두 자리 연도를 자동추론에 맡기면 연·일이 뒤바뀝니다.")
        for raw, exp in (("95,000", 95000.0), ("0", None), ("-", None), ("없음", None)):
            if parse_target_price(raw) != exp:
                return False, f"목표주가 파싱: {raw!r} → {parse_target_price(raw)!r}"
        for raw, exp in (("미래에셋대우", "미래에셋증권"), ("하나금융투자", "하나증권"),
                         ("신한금융투자", "신한투자증권"), ("이베스트투자증권", "LS증권"),
                         ("KTB투자증권", "다올투자증권"), ("하이투자증권", "iM증권")):
            if normalize_broker(raw)[1] != exp:
                return False, f"증권사 정규화: {raw} → {normalize_broker(raw)[1]} (기대 {exp})"
        # ★ 법인 식별자는 합병 전후를 **구분해야** 한다 (이직 탐지의 근거)
        if normalize_broker_legal("대우증권")[0] == normalize_broker_legal("미래에셋증권")[0]:
            return False, ("★법인 식별자가 합병 전후를 하나로 뭉갰습니다. 2016년 대우증권→"
                           "미래에셋 이동이 보이지 않게 되어 M-EXIT 이 통째로 사라집니다.")
        if normalize_broker("대우증권")[0] != normalize_broker("미래에셋증권")[0]:
            return False, "정규화 식별자가 합병 전후를 구분했습니다(목표주가 연속성이 끊깁니다)"
        return True, ("YY.MM.DD 연·일 전치 방지 · 목표주가 0/- 결측 · 사명 정규화 · "
                      "법인/정규화 식별자 이원화 확인")

    _c("PARSE", "수집 파서 회귀", c_parse)

    # ── 원장 병합 멱등성 (출력이 다음 실행의 입력이 된다) ───────────────────────────────
    def c_merge():
        sec = pd.DataFrame(columns=["code", "name"])

        def _f(src, rid, tp):
            return pd.DataFrame([{
                "source": src, "src_report_id": rid, "pub_date": "2024-05-02",
                "category": "기업", "title": "삼성전자(005930) 실적 개선",
                "stock_code": "005930", "stock_name": "삼성전자",
                "broker_raw": "미래에셋증권", "analyst_raw": "홍길동",
                "target_price": tp, "opinion": "Buy", "detail_url": None}])

        a, b = _f("hankyung", "h1", 95000.0), _f("naver", "n1", 90000.0)
        cols = sorted(set(a.columns) | set(b.columns))
        m1 = build_report_master(pd.concat([a, b], ignore_index=True)[cols], sec)
        m2 = build_report_master(pd.concat([a, b, m1.reindex(columns=cols)],
                                           ignore_index=True), sec)
        m3 = build_report_master(m1.copy(), sec)
        if not (len(m1) == len(m2) == len(m3) == 1):
            return False, f"소스 간 중복 병합 실패: {len(m1)}/{len(m2)}/{len(m3)}건 (기대 1/1/1)"
        for nm, mm in (("캐시 재투입", m2), ("캐시 전용", m3)):
            for c, why in (("source", "합성 토큰을 원자로 분해하지 않으면 실행마다 문자열이 "
                                      "무한히 길어집니다"),
                           ("report_uid", "PDF 캐시와 애널리스트 연결표가 통째로 끊깁니다")):
                if str(mm[c].iloc[0]) != str(m1[c].iloc[0]):
                    return False, (f"★{nm} 실행에서 {c} 가 {str(m1[c].iloc[0])[:24]!r} → "
                                   f"{str(mm[c].iloc[0])[:24]!r} 로 바뀌었습니다. {why}.")
        if float(m1["target_price"].iloc[0]) != 95000.0:
            return False, f"목표주가 병합이 최대값을 취하지 않았습니다"
        return True, f"병합 멱등 확인 — source={m1['source'].iloc[0]} · report_uid 불변"

    _c("MERGE", "원장 병합 멱등성", c_merge)

    # ── 폐지 처리: 승계 vs 전손 ────────────────────────────────────────────────────────
    def c_delist():
        dl = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "delisting_date": pd.to_datetime(["2020-03-31"] * 3),
            "reason": ["상장폐지기준 해당", "합병에 의한 소멸", "기타"],
            "to_symbol": [None, None, "000009"]})
        k = classify_delisting(dl)
        if k.get("000001") != "WIPEOUT":
            return False, f"상장폐지기준 해당이 전손으로 분류되지 않았습니다: {k.get('000001')}"
        if k.get("000002") != "SUCCEED":
            return False, "합병 소멸이 승계로 분류되지 않았습니다(전손 처리 시 하방 편향)"
        if k.get("000003") != "SUCCEED":
            return False, "승계종목(ToSymbol)이 있는데 전손으로 분류되었습니다"
        return True, "전손/승계 분기 확인 — 일괄 처리는 양방향 모두 편향입니다"

    _c("DELIST", "상장폐지 수익률 분기", c_delist)

    # ── 통계 커널: DSR · PBO · TOST 가 극단 입력에서 죽지 않을 것 ──────────────────────
    def c_stats():
        r = np.random.default_rng(1).normal(0.01, 0.05, 120)
        d = deflated_sharpe(r, n_trials=24)
        if not np.isfinite(d.get("dsr", np.nan)):
            return False, f"DSR 산출 실패: {d}"
        if not (0 <= d["dsr"] <= 1):
            return False, f"DSR 이 확률 범위 밖입니다: {d['dsr']}"
        M = np.random.default_rng(2).normal(0.005, 0.05, (120, 12))
        p = pbo_cscv(M, S=8, max_combos=60)
        if not np.isfinite(p.get("pbo", np.nan)) or not (0 <= p["pbo"] <= 1):
            return False, f"PBO 산출 실패: {p}"
        t = tost_equivalence(np.random.default_rng(3).normal(0, 0.01, 60), bound=0.02)
        if t.get("equivalent") is None:
            return False, f"TOST 판정 실패: {t}"
        short = deflated_sharpe(np.array([0.01, 0.02]), n_trials=12)
        if np.isfinite(short.get("dsr", np.nan)):
            return False, "표본 2개인데 DSR 이 산출되었습니다 (판정불가여야 합니다)"
        return True, (f"DSR={d['dsr']:.3f} · PBO={p['pbo']:.3f} · TOST 동작 · "
                      f"표본부족 시 판정불가 반환 확인")

    _c("STATS", "통계 커널", c_stats)

    # ── 결과 ───────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 28), "✔ 통과" if r["pass"] else "✘ 실패",
             _trunc(r["msg"], 78)] for r in CONTRACTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=82,
              title="계약 자동검정 (협상 대상이 아님 — 전부 실측으로 재현된 실패를 고정한 것)")
    failed = [r for r in CONTRACTS if not r["pass"]]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS)}건 전부 통과.")
    return True
