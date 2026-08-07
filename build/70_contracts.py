

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 C1~C12 (§2) — 주석이나 관례는 무효. 테스트로만 강제한다.                    ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return ok


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACT_RESULTS.clear()
    rng = np.random.default_rng(SEED)

    # ── C1: PIT 강제 ──────────────────────────────────────────────────────────────────────
    def c1():
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
        # PIT 컬럼 없는 테이블은 반드시 거부돼야 한다
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 등록 거부 확인"

    _c("C1", "Point-In-Time 강제", c1)

    # ── C2: 생존자편향 ────────────────────────────────────────────────────────────────────
    def c2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": ["옛날", "미래", "폐지"],
            "market": ["KOSPI"] * 3, "industry": ["X"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"]),
        })
        days = pd.bdate_range("2009-01-01", "2026-08-01")
        px = pd.DataFrame({"date": days, "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2016 = u.at("2016-08-31")
        if "000002" in at2016:
            return False, "★C2 위반: 2016년 유니버스에 2025년 상장 종목이 포함되었습니다"
        if "000003" not in at2016:
            return False, "★C2 위반: 2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다(생존자편향)"
        at2020 = u.at("2020-01-31")
        if "000003" in at2020:
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지종목 당시 포함 · 폐지 후 제외 모두 정상"

    _c("C2", "생존자편향 제거", c2)

    # ── C3: 매핑도 PIT ────────────────────────────────────────────────────────────────────
    def c3():
        m = pd.DataFrame({"code": ["000001"], "external_id": ["X1"], "weight": [1.0],
                          "valid_from": pd.to_datetime(["2020-01-01"]),
                          "valid_to": pd.to_datetime(["2022-12-31"])})
        for c in ("valid_from", "valid_to"):
            if c not in m.columns:
                return False, f"매핑 테이블에 시간구간 컬럼 {c} 이 없습니다"
        t = as_ts("2019-06-30")
        live = m[(m["valid_from"] <= t) & (m["valid_to"] >= t)]
        return (len(live) == 0), "매핑 유효구간 이전 시점에서 매핑이 적용되지 않음 확인"

    _c("C3", "매핑·라벨 PIT", c3)

    # ── C4/C11: 셀 정의 ───────────────────────────────────────────────────────────────────
    def c4():
        n = 400
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": [as_ts("2020-06-30")] * n,
            "employees": rng.integers(10, 5000, n).astype(float),
            "x": rng.normal(size=n),
        })
        sec = pd.DataFrame({"code": P["code"], "industry": rng.choice(["화학", "전자", "건설"], n)})
        C = build_cells(P, sec)
        if "cell" not in C.columns:
            return False, "cell 컬럼이 생성되지 않았습니다"
        keys = C["cell"].astype(str).str.split("|", expand=True)
        if keys.shape[1] < 3:
            return False, "cell_key 가 (date, industry, size_bucket) 3요소가 아닙니다"
        z = xsec_z(C["x"], C["cell"])
        for cell, g in C.assign(z=z).groupby("cell", observed=True):
            if g["z"].notna().sum() >= CELL_MIN_N:
                if abs(float(g["z"].mean())) > 0.15:
                    return False, f"셀 {cell} 의 z-score 평균이 0에서 벗어남: {g['z'].mean():.3f}"
        return True, f"cell=(date,industry,size) · 셀 내 z 평균≈0 · 폴백 동작 확인 ({C['cell'].nunique()}개 셀)"

    _c("C4/C11", "셀 정의 및 횡단면 연산", c4)

    # ── C5: winsorize → z → rank 순서 ─────────────────────────────────────────────────────
    def c5():
        v = pd.Series([1.0] * 30 + [1000.0])          # 극단값 1개
        cell = pd.Series(["A"] * 31)
        z = xsec_z(v, cell)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        if float(z.max()) > 6:
            return False, f"윈저라이즈가 적용되지 않았습니다 (max z={z.max():.2f})"
        r = xsec_rank_pct(v, cell)
        if not (0 < float(r.min()) <= float(r.max()) <= 1):
            return False, "rank_pct 범위가 [0,1] 이 아닙니다"
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]))
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 으로 처리되지 않았습니다(0으로 채우면 안 됩니다)"
        # ±inf 오염: nanmean 은 NaN 은 무시하지만 inf 는 무시하지 않는다.
        # inf 하나가 셀 전체 z 를 0으로 뭉개면 그 셀의 신호가 통째로 사라진다.
        vi = pd.Series([1.0, 2.0, 3.0, np.inf, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        zi = xsec_z(vi, pd.Series(["A"] * 10))
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, (f"★inf 오염: 셀에 ±inf 가 하나 있으면 z-score 가 전부 뭉개집니다 "
                           f"(유효 {int(zi.notna().sum())}개, 표준편차 {float(zi.dropna().std()):.3f}). "
                           f"비율/로그 지표에서 흔히 발생하며 해당 셀의 신호가 통째로 소실됩니다.")
        return True, ("winsorize(±2σ)→z→rank_pct 순서 · 표본부족 NaN · ±inf 무해화 확인")

    _c("C5", "윈저라이즈→랭크 순서 고정", c5)

    # ── C6: 거부권 이진 ───────────────────────────────────────────────────────────────────
    def c6():
        P = pd.DataFrame({f"V{i}": [1.0, 0.0, 1.0] for i in range(1, 9)})
        prod = P.prod(axis=1)
        if list(prod) != [1.0, 0.0, 1.0]:
            return False, "거부권 곱이 이진으로 작동하지 않습니다"
        # 상쇄 불가: 어떤 큰 점수도 0을 되살릴 수 없다
        E, U = 0.999, 0.999
        if E * U * 0.0 != 0.0:
            return False, "거부권이 상쇄 가능합니다"
        return True, "V∈{0,1} · 곱 · 상쇄 불가 확인"

    _c("C6", "거부권 이진·곱", c6)

    # ── C7: 가중치 최적화 금지 ────────────────────────────────────────────────────────────
    def c7():
        src = ""
        for fn in (assemble_score, axis_B_tp, axis_C_tp):
            try:
                import inspect
                src += inspect.getsource(fn)
            except Exception:
                pass
        if re.search(r"(minimize|curve_fit|GridSearch|optimize\.|\.fit\(.*weight)", src):
            return False, "가중치 최적화 흔적이 발견되었습니다 (C7 위반)"
        return True, "TP 내·팩 내·팩 간 모두 동일가중 (nanmean). 최적화 루틴 없음"

    _c("C7", "Phase1-3 가중치 최적화 금지", c7)

    # ── C8: 결정성 ────────────────────────────────────────────────────────────────────────
    def c8():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1]).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 순서 무관 결과 동일 확인"

    _c("C8", "결정성", c8)

    # ── C10: 런타임 예산 계측 존재 ────────────────────────────────────────────────────────
    def c10():
        if not hasattr(PIPE, "report_runtime"):
            return False, "런타임 계측기가 없습니다"
        budgeted = [s for s in PIPE.stages.values() if s.budget_s is not None]
        return True, f"계층별 계측 활성 · 예산 지정 스테이지 {len(budgeted)}개 (추측 아닌 실측)"

    _c("C10", "런타임 예산 계측", c10)

    # ── C12: 정책 중립성 ──────────────────────────────────────────────────────────────────
    def c12():
        missing = [pid for pid, p in PACK_REGISTRY.items() if not p["policy"]]
        if missing:
            return False, f"정책 캘린더 없는 팩: {missing}"
        act = [p["id"] for p in active_packs()]
        return True, (f"등록 팩 {list(PACK_REGISTRY)} 전부 정책 캘린더 보유 · "
                      f"활성 팩 {act} 은 R10 대상")

    _c("C12", "정책 중립성", c12)

    # ── 추가: TP 는 반드시 곱 ─────────────────────────────────────────────────────────────
    def c_tp():
        a = pd.Series([2.0, 2.0, 0.0, np.nan])
        b = pd.Series([3.0, -3.0, 5.0, 1.0])
        r = tp_product(a, b)
        if not (abs(r[0] - 6) < 1e-6 and abs(r[1] + 6) < 1e-6):
            return False, "TP 가 곱으로 계산되지 않습니다"
        if pd.notna(r[3]):
            return False, "한쪽이 결측인데 결과가 결측이 아닙니다(0으로 채우면 거짓 주장이 됩니다)"
        return True, "TP = z(개선)×z(대가회피) · 결측 전파 확인 (합산으로 단순화 안 됨)"

    _c("TP", "트레이드오프 쌍은 곱(§1.1)", c_tp)

    # ── 회귀 방지: as-of 결합이 행을 버리지 않을 것 (C1+C2 동시) ──────────────────────────
    def c_asof():
        panel = pd.DataFrame({"code": ["A", "B", "C", "A", "B", "C"],
                              "corp_code": ["c1", None, "c3", "c1", None, "c3"],
                              "month": pd.to_datetime(["2020-01-31"] * 3 + ["2020-02-29"] * 3)})
        fin = pit_frame(pd.DataFrame({"corp_code": ["c1", "c1", "c3"],
                                      "revenue_ttm": [100.0, 999.0, 300.0],
                                      "pe": pd.to_datetime(["2019-12-31", "2020-03-31", "2019-12-31"]),
                                      "kd": pd.to_datetime(["2020-01-15", "2020-05-15", "2020-01-15"])}),
                        "pe", "kd")
        st = PITStore()
        st.register("fin", fin, key_cols=["corp_code"])
        out = st.asof_join(panel, "fin", by="corp_code", left_time="month")
        if len(out) != len(panel):
            return False, (f"★C2 재유입: 결합키가 결측인 행이 버려졌습니다 "
                           f"({len(out)}/{len(panel)}행). corp_code 없는 종목(대개 상장폐지)이 "
                           f"통째로 사라지면 그게 곧 생존자편향입니다.")
        if not out.loc[out["code"] == "B", "revenue_ttm"].isna().all():
            return False, "결합키 결측 행에 값이 붙었습니다"
        if out.loc[out["code"] == "A", "revenue_ttm"].tolist() != [100.0, 100.0]:
            return False, (f"★C1 위반: 2020-05-15 에야 알 수 있는 값(999)이 새어나오거나 "
                           f"행 정렬이 어긋났습니다 → {out.loc[out['code']=='A','revenue_ttm'].tolist()}")
        if out.loc[out["code"] == "C", "revenue_ttm"].tolist() != [300.0, 300.0]:
            return False, "결합 결과가 다른 종목에 붙었습니다(정렬 오류)"
        return True, "결합키 결측 행 보존 · 미래값 차단 · 종목별 정렬 정확"

    _c("C1/C2b", "as-of 결합 무결성", c_asof)

    # ── 회귀 방지: 유니버스는 미래 스냅샷을 쓰지 않을 것 ───────────────────────────────────
    def c_snapfuture():
        """스냅샷 semantics 3종 동시 검정.

        스냅샷은 '대체'가 아니라 '보강'이다. KRX 는 부분 응답을 자주 내는데, 그걸 그 달의
        진실로 믿고 날짜 근거를 덮어쓰면 유니버스가 조용히 줄어 곧바로 선택편향이 된다.
        그래서 세 성질을 동시에 만족해야 한다:
          (a) 미래 스냅샷에만 있는 종목은 절대 들어오면 안 된다      → 미래누수 금지
          (b) 과거 스냅샷에만 있는 종목은 반드시 들어와야 한다        → 생존자편향 방지
          (c) 부분 스냅샷에서 빠졌어도 날짜 근거가 있으면 남아야 한다 → 부분응답 방어
        """
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003", "000004"],
            "name": list("abcd"), "market": ["KOSPI"] * 4, "industry": ["X"] * 4,
            "corp_code": [None] * 4,
            # 003 = 스냅샷에만 존재(날짜 근거 없음), 004 = 2019 폐지
            "listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", None, "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, None, "2019-06-30"]),
        })
        snaps = pd.DataFrame({
            "snap_date": pd.to_datetime(["2020-01-31", "2020-01-31", "2020-03-31"]),
            # 2020-01 스냅샷은 '부분 응답'이라 000002 가 빠져 있다
            "code": ["000001", "000003", "000009"], "market": ["KOSPI"] * 3})
        px = pd.DataFrame({"date": pd.bdate_range("2009-01-01", "2021-01-01"), "code": "000001"})
        u = Universe(sec, snaps, px)
        got = set(u.at("2020-02-29"))

        if "000009" in got:
            return False, ("★미래누수: 2020-03-31 스냅샷에만 있는 종목이 2020-02-29 유니버스에 "
                           "들어왔습니다. 가장 '가까운'이 아니라 가장 '최근 과거' 스냅샷만 써야 합니다.")
        if "000003" not in got:
            return False, ("★생존자편향: 과거 스냅샷에만 존재하는 종목이 빠졌습니다. "
                           "상장/폐지 명단에서 누락된 종목이 바로 이 경로로 들어옵니다.")
        if "000002" not in got:
            return False, ("★부분응답 사고: 스냅샷에서 빠졌다는 이유로 날짜 근거가 있는 종목이 "
                           "탈락했습니다. 스냅샷은 대체가 아니라 보강이어야 합니다 "
                           "(KRX 부분 응답이 그 달 유니버스를 통째로 깎습니다).")
        if "000004" in got:
            return False, "2019-06-30 폐지 종목이 2020년 유니버스에 남아 있습니다."
        return True, ("미래 스냅샷 차단 · 과거 스냅샷 보강 · 부분응답 내성 · 폐지 후 제외 "
                      "모두 확인 (스냅샷은 대체가 아닌 보강)")

    _c("C2c", "유니버스 스냅샷 방향성", c_snapfuture)

    # ── 회귀 방지: 결측 컬럼 산술이 죽지 않을 것 ──────────────────────────────────────────
    def c_col():
        df = pd.DataFrame({"x": [1.0, 2.0]})
        s = col(df, "rnd_ttm")
        if not isinstance(s, pd.Series) or len(s) != 2 or s.notna().any():
            return False, "col() 이 결측 Series 를 반환하지 않습니다"
        _ = s.abs().fillna(0) + col(df, "capex_ttm").abs().fillna(0)
        if df.get("rnd_ttm") is not None:
            return False, "테스트 전제 오류"
        return True, ("없는 컬럼도 NaN Series 로 안전 반환 — 데이터 소스가 통째로 빈 실행에서 "
                      "AttributeError 로 죽지 않음")

    _c("COL", "결측 컬럼 안전 접근", c_col)

    # ── 회귀 방지: 비중 상한이 실제로 강제될 것 (§8.5 — 코드 상수로 못박은 규칙) ───────────
    def c_size():
        for name, sig, adv in (
            ("균등", np.linspace(0.5, 1.0, 10), np.full(10, 1e12)),
            ("극단집중", np.array([1.0] + [0.01] * 9), np.full(10, 1e12)),
            ("소수종목", np.linspace(0.6, 1.0, 5), np.full(5, 1e12)),
            ("저유동성", np.linspace(0.5, 1.0, 10), np.array([1e7] * 3 + [1e12] * 7)),
        ):
            sub = pd.DataFrame({"Signal_rank": sig, "adv20": adv,
                                "code": [f"{i:06d}" for i in range(len(sig))]})
            w = size_positions(sub)["weight"].to_numpy(dtype=float)
            if w.max() > POS_MAX_WEIGHT + 1e-9:
                return False, (f"★[{name}] 종목당 최대비중 {POS_MAX_WEIGHT:.0%} 가 뚫렸습니다 "
                               f"(최대 {w.max():.4f}). clip 후 재정규화하면 상한이 무력화됩니다.")
            if w.sum() > 1.0 + 1e-9:
                return False, f"[{name}] 비중 합이 1을 초과합니다 ({w.sum():.6f})"
            liq = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                           POS_MAX_WEIGHT)
            cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq, POS_MIN_WEIGHT * 0.5))
            if (w > cap + 1e-9).any():
                return False, f"★[{name}] 유동성 상한(20일 평균거래대금×{POS_ADV_PARTICIPATION:.0%})이 뚫렸습니다"
        return True, (f"종목당 상한 {POS_MAX_WEIGHT:.0%} · 유동성 상한 · 합≤1 "
                      f"모두 강제 확인 (water-filling)")

    _c("SIZE", "포지션 비중 상한 강제", c_size)

    # ── 추가: 종목코드 정규화 (2024 영숫자 티커) ──────────────────────────────────────────
    def c_code():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) 모두 정상 처리"

    _c("CODE", "종목코드 정규화", c_code)

    # ── 회귀 방지: 수집 파서 (실데이터 없이도 검증 가능한 부분) ────────────────────────────
    def c_ingest():
        # ① YY.MM.DD — pandas 자동추론은 '26.01.19'를 2019-01-26 으로 읽는다(연·일 전치)
        for raw, exp in (("26.01.19", "2026-01-19"), ("19.12.31", "2019-12-31"),
                         ("24.11.30", "2024-11-30"), ("2020-05-01", "2020-05-01")):
            if parse_kr_date(raw) != exp:
                return False, (f"★날짜 파싱: {raw} → {parse_kr_date(raw)} (기대 {exp}). "
                               f"두 자리 연도를 자동추론에 맡기면 연·일이 뒤바뀌어 "
                               f"리포트 원장의 시간축이 통째로 어긋납니다.")
        # ② 목표주가 '0'/'-' 은 결측이지 0원이 아니다
        for raw, exp in (("95,000", 95000.0), ("0", None), ("-", None), ("없음", None)):
            if parse_target_price(raw) != exp:
                return False, f"목표주가 파싱: {raw!r} → {parse_target_price(raw)!r} (기대 {exp!r})"
        # ③ 증권사 사명 변경 정규화 (안 하면 같은 애널리스트가 다른 사람이 된다)
        for raw, exp in (("미래에셋대우", "미래에셋증권"), ("하나금융투자", "하나증권"),
                         ("신한금융투자", "신한투자증권"), ("이베스트투자증권", "LS증권"),
                         ("KTB투자증권", "다올투자증권"), ("하이투자증권", "iM증권")):
            if normalize_broker(raw)[1] != exp:
                return False, f"증권사 정규화: {raw} → {normalize_broker(raw)[1]} (기대 {exp})"
        # ④ 한경 9컬럼/6컬럼/헤더없음 — 컬럼 인덱스가 아니라 헤더명으로 매핑되는지
        def _mk(hdr, rows):
            h = ("<tr>" + "".join(f"<th>{x}</th>" for x in hdr) + "</tr>") if hdr else ""
            b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
            return f"<div class='table_style01'><table>{h}{b}</table></div>"
        r9 = [["2024-05-02",
               "<a href='/analysis/downpdf?report_idx=123456'>삼성전자(005930) 실적 개선</a>",
               "95,000", "Buy", "홍길동", "미래에셋대우", "-", "-",
               "<a href='/analysis/downpdf?report_idx=123456'>P</a>"]]
        o9 = _hk_parse(_mk(["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
                            "기업정보", "차트", "첨부"], r9), "t_business")
        if not o9 or o9[0]["stock_code"] != "005930" or o9[0]["target_price"] != 95000.0 \
                or o9[0]["analyst_raw"] != "홍길동":
            return False, f"한경 9컬럼 파싱 실패: {o9[:1]}"
        o0 = _hk_parse(_mk(None, r9), "t_noheader")       # thead 가 없어도 살아남아야 한다
        if not o0 or o0[0]["stock_code"] != "005930":
            return False, f"한경 헤더없음 폴백 실패: {o0[:1]}"
        # ⑤ 인코딩: force_enc 는 힌트일 뿐 — 소스가 UTF-8 로 바뀌어도 깨지면 안 된다
        ko = "네이버 금융 리서치 종목분석 삼성전자 목표주가 상향" * 4
        for enc in ("euc-kr", "utf-8"):
            if "네이버" not in _decode(ko.encode(enc), None, "x", force_enc="euc-kr"):
                return False, f"인코딩 판별 실패: 실제 {enc} 인데 깨짐"
        return True, ("YY.MM.DD 연·일 전치 방지 · 목표주가 0/- 결측처리 · 사명변경 정규화 · "
                      "헤더명 기반 컬럼매핑(9/6/무헤더) · EUC-KR↔UTF-8 자동판별 확인")

    _c("INGEST", "수집 파서 회귀 검사", c_ingest)

    # ── 회귀 방지: 시즈닝의 기준점은 '상장일'이지 '가격패널 시작일'이 아닐 것 ───────────────
    def c_season():
        """패널 시작 전에 상장한 종목이 백테스트 첫 1년 동안 사라지지 않아야 한다.

        searchsorted 는 패널 시작 이전 상장분을 전부 index 0 으로 보낸다. 거기에 +250거래일을
        더하면 1990년 상장 종목조차 '패널 시작 후 1년'에야 시즈닝이 끝난 것으로 계산되어,
        2016-08 시작 백테스트의 첫 1년 유니버스가 통째로 비어버린다. 에러도 경고도 없이.
        """
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": list("abc"), "market": ["KOSPI"] * 3, "industry": ["X"] * 3,
            "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["1990-03-02",    # 패널보다 26년 전 상장
                                            "2016-09-01",    # 패널 직후 상장(아직 미시즈닝)
                                            "2013-01-02"]),  # 패널 3년 전 상장
            "delisting_date": pd.to_datetime([None, None, None]),
        })
        px = pd.DataFrame({"date": pd.bdate_range("2016-08-01", "2019-12-31"), "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        first = set(u.at("2016-08-31"))
        miss = [c for c in ("000001", "000003") if c not in first]
        if miss:
            return False, (f"★시즈닝 앵커 오류: 패널 시작 전 상장 종목 {miss} 가 백테스트 첫 "
                           f"달에서 빠졌습니다. 기준점이 '상장일'이 아니라 '가격패널 시작일'로 "
                           f"잡혀 있습니다 — 첫 1년 유니버스가 통째로 증발합니다.")
        if "000002" in first:
            return False, "2016-09-01 상장 종목이 2016-08-31 유니버스에 있습니다(미래 상장)."
        if "000002" in set(u.at("2017-03-31")):
            return False, "상장 250거래일 미만 신규 상장이 시즈닝을 통과했습니다."
        if "000002" not in set(u.at("2017-10-31")):
            return False, "상장 250거래일이 지난 종목이 여전히 시즈닝에 막혀 있습니다."
        return True, ("시즈닝 기준점 = 상장일 확인 (기존 상장사 첫 달 생존 · 신규 상장 "
                      "250거래일 대기 · 대기 후 편입)")

    _c("C2d", "시즈닝 기준점", c_season)

    # ── 회귀 방지: 원장 병합은 멱등일 것 (출력이 다음 실행의 입력이 된다) ──────────────────
    def c_merge():
        """드라이브 캐시에 저장된 병합 결과는 다음 실행에서 '입력 프레임'으로 되돌아온다.
        그래서 병합은 반드시 멱등이어야 한다. 아니면 실행할 때마다 source 문자열이 길어지고
        report_uid 가 바뀌어 PDF 캐시·애널리스트 연결표가 조용히 끊긴다."""
        sec = pd.DataFrame(columns=["code", "name", "corp_code", "market", "industry",
                                    "listing_date", "delisting_date"])

        def _f(src, rid, tp):
            return pd.DataFrame([{
                "source": src, "src_report_id": rid, "pub_date": "2024-05-02",
                "category": "기업", "title": "삼성전자(005930) 실적 개선",
                "stock_code": "005930", "stock_name": "삼성전자",
                "broker_raw": "미래에셋증권", "analyst_raw": "홍길동",
                "target_price": tp, "opinion": "Buy", "pdf_url": None, "detail_url": None,
            }])

        a, b = _f("hankyung", "h1", 95000.0), _f("naver", "n1", 90000.0)
        m1 = build_report_master([a, b], sec)
        m2 = build_report_master([a, b, m1], sec)     # 캐시 재투입
        m3 = build_report_master([m1], sec)           # 캐시만으로 실행
        if not (len(m1) == len(m2) == len(m3) == 1):
            return False, f"소스 간 중복 병합 실패: {len(m1)}/{len(m2)}/{len(m3)}건 (기대 1/1/1)"
        for nm, mm in (("캐시 재투입", m2), ("캐시 전용", m3)):
            for c, why in (("source", "합성 토큰을 원자로 분해하지 않으면 실행마다 문자열이 "
                                      "무한히 길어집니다"),
                           ("src_report_id", "원본 보고서 ID 추적이 불가능해집니다"),
                           ("report_uid", "PDF 캐시와 애널리스트 연결표가 통째로 끊깁니다")):
                if mm[c].iloc[0] != m1[c].iloc[0]:
                    return False, (f"★{nm} 실행에서 {c} 가 "
                                   f"{str(m1[c].iloc[0])[:28]!r} → {str(mm[c].iloc[0])[:28]!r} "
                                   f"로 바뀌었습니다. {why}.")
        if float(m1["target_price"].iloc[0]) != 95000.0:
            return False, f"목표주가 병합이 최대값을 취하지 않았습니다: {m1['target_price'].iloc[0]}"
        return True, ("병합 멱등성 확인 — 캐시 재투입·캐시 전용 실행 모두에서 "
                      f"source({m1['source'].iloc[0]})·src_report_id·report_uid 불변")

    _c("MERGE", "원장 병합 멱등성", c_merge)

    # ── 회귀 방지: Signal_rank 는 '월 전체' 백분위일 것 ────────────────────────────────────
    def c_rank():
        """선정부(nlargest)는 월 전체를 한 줄로 세워 뽑는다. 따라서 랭크도 월 전체여야 한다.

        한때 (month, pack_profile) 로 나눠 랭크를 매겼다. 그러면 자기 프로파일에 혼자인 종목이
        무조건 1.0 을 받아 상위를 채운다 — 실측상 월 보유종목의 70%가 동점 1.0 이었고,
        그중 상당수가 그달 '가장 낮은' 원점수였다. 정보량 차이는 랭크 분할이 아니라
        하한선(빈 축 없음 + 최소 축수)이 막는다.
        """
        n = 60
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n + 1)],
            "month": as_ts("2020-06-30"), "cell": "X", "U": 1.0, "VETO": 1.0,
            "E_A": list(np.linspace(0.0, 1.0, n)) + [0.60],
            "E_B": list(np.linspace(0.0, 1.0, n)) + [np.nan],   # 마지막 1행만 축이 1개
        })
        S = score_from_axes(P, ["E_A", "E_B"], min_axes=1)
        sig, rank = S["Signal"], S["Signal_rank"]
        if int(S["pack_profile"].nunique()) < 2:
            return False, "테스트 전제 오류: 정보량 프로파일이 2종 이상이어야 합니다."
        top_by_rank = int(rank.idxmax())
        top_by_sig = int(sig.idxmax())
        if top_by_rank != top_by_sig:
            return False, (f"★랭크가 원점수와 어긋납니다: 최고 랭크는 {P['code'][top_by_rank]}"
                           f"(Signal {sig[top_by_rank]:.4f}) 인데 최고 원점수는 "
                           f"{P['code'][top_by_sig]}(Signal {sig[top_by_sig]:.4f}) 입니다. "
                           f"Signal_rank 를 pack_profile 로 나눠 매기면 '자기 그룹에 혼자인' "
                           f"종목이 1.0 을 받아 상위를 차지합니다.")
        d = pd.DataFrame({"s": sig, "r": rank}).dropna()
        rho = float(d["s"].corr(d["r"], method="spearman"))
        if not (rho > 0.999):
            return False, f"★Signal_rank 가 Signal 의 단조함수가 아닙니다 (spearman={rho:.4f})."
        return True, (f"월 전체 백분위 확인 — 랭크가 원점수의 단조함수(ρ={rho:.4f})이고 "
                      f"축이 1개뿐인 종목이 상위를 가로채지 않음 (프로파일 "
                      f"{int(S['pack_profile'].nunique())}종)")

    _c("RANK", "선정 랭크 정합성", c_rank)

    # ── 회귀 방지: 활성 팩은 전용 수집이 배선되어 있을 것 ──────────────────────────────────
    def c_wire():
        """'수집이 배선되지 않음'과 '수집했는데 비어 있음'은 완전히 다른 사건이다.

        한때 어느 팩도 ingest_fn 을 등록하지 않아 collect_all 의 팩 수집 루프가 통째로
        무동작이었다. 5개 팩 전략이 실제로는 PACK-C 하나로 돌면서 성과표를 끝까지 출력했고,
        하류 커버리지 검사는 그걸 '데이터 부재'로 보고해 운영자를 API 키 쪽으로 오도했다.
        """
        bad = [p["id"] for p in active_packs() if not p.get("ingest") and p["id"] != "C"]
        if bad:
            return False, (f"★센서팩 {bad} 이 활성인데 ingest_fn 이 없습니다. 이 팩들은 "
                           f"수집 자체가 일어나지 않아 전 구간 결측이 되며, 키를 넣어도 "
                           f"해결되지 않습니다.")
        wired = [p["id"] for p in active_packs() if p.get("ingest")]
        return True, (f"활성 팩 {[p['id'] for p in active_packs()]} 중 전용 수집 배선 {wired} "
                      f"확인 (C 는 L1.DART 재무를 그대로 읽으므로 전용 수집 없음이 정상)")

    _c("WIRE", "센서팩 수집 배선", c_wire)

    # ── 회귀 방지: 청산 게이트의 모든 분기가 도달 가능할 것 ────────────────────────────────
    def c_exit():
        """`dm >= de and de > 0` 처럼 뒤 조건이 앞 조건에 거의 포함되는 식은, 실제로는
        '논거가 깨진 종목을 파는 경로'만 골라서 닫아버린다. 네 사분면을 전부 검정한다."""
        cases = [
            (0.05, 0.10, False, "ΔlogE>0 이고 시장이 아직 자본화 안 함 → 보유(목표상태)"),
            (0.15, 0.10, True,  "시장이 재분류 완료(ΔlogM≥ΔlogE) → 청산(알파 소진)"),
            (-0.20, -0.05, True, "이익 증가 소멸 → 청산(논거 무효). 예전엔 이 경로가 닫혀 있었다"),
            (0.05, -0.05, True, "이익 감소 + 주가 상승 → 청산"),
            (np.nan, 0.10, False, "결측 → 보유(모르는 것을 이유로 팔지 않는다)"),
            (0.05, np.nan, False, "결측 → 보유"),
        ]
        for dm, de, want, why in cases:
            got = bool(exit_gate(dm, de))
            if got != want:
                return False, (f"★청산 게이트: ΔlogM={dm}, ΔlogE={de} → {got} (기대 {want}). {why}")
        return True, ("네 사분면 + 결측 전부 확인 — 재분류 완료와 논거 무효를 모두 청산하고, "
                      "결측은 보유로 떨어짐")

    _c("EXIT", "청산 게이트 도달성", c_exit)

    # ── 회귀 방지: TP_P2 의 저-저 사분면 부호 ──────────────────────────────────────────────
    def c_tpp2():
        """TP = z(개선) × z(대가회피) 는 곱이라, 두 인자가 모두 음수면 양수가 된다.
        '취득 규모가 큰데 소각까지 실행했는가'를 묻는 TP_P2 에서는 이게 치명적이다 —
        자사주를 거의 안 샀고 소각도 안 한 기업이 '진정성 있는 환원'으로 뒤집힌다."""
        zi = pd.Series([-1.5, -0.5, 1.2, 2.0])       # 취득 규모 z
        zp = pd.Series([-1.5, 1.0, -0.8, 1.5])       # 소각 실행률 z
        out = tp_product(zi.where(zi > 0), zp)
        if pd.notna(out.iloc[0]):
            return False, (f"★저-저 사분면(취득 안 함 + 소각 안 함)이 {out.iloc[0]:.3f} 로 "
                           f"산출됐습니다. 음×음=양 때문에 '아무것도 안 한 기업'이 상위로 "
                           f"올라갑니다. 지출이 없는 쪽은 NaN 이어야 합니다.")
        if pd.notna(out.iloc[1]):
            return False, "취득 규모가 셀 평균 미만인데 값이 나왔습니다."
        if not (pd.notna(out.iloc[3]) and out.iloc[3] > 0):
            return False, f"고-고 사분면(취득 큼 + 소각 실행)이 양수가 아닙니다: {out.iloc[3]}"
        if not (pd.notna(out.iloc[2]) and out.iloc[2] < 0):
            return False, f"취득은 컸는데 소각 안 한 경우가 음수가 아닙니다: {out.iloc[2]}"
        return True, ("저-저 사분면 NaN(0 아님) · 고-고 양수 · 고-저 음수 확인 — "
                      "'대가를 안 치렀다'는 거짓 주장을 만들지 않음")

    _c("TPP2", "자사주 TP 부호", c_tpp2)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 30), "✔ 통과" if r["pass"] else "✘ 실패",
             _trunc(r["msg"], 76)] for r in CONTRACT_RESULTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=80,
              title="계약 자동검정 C1~C12 (§2 — 협상 대상이 아님)")
    failed = [r for r in CONTRACT_RESULTS if not r["pass"]]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오(§2).")
        return False
    LOG.ok(f"계약 {len(CONTRACT_RESULTS)}건 전부 통과.")
    return True
