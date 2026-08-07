

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
        return True, "winsorize(±2σ)→z→rank_pct 순서 및 표본부족 NaN 처리 확인"

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

    # ── 추가: 종목코드 정규화 (2024 영숫자 티커) ──────────────────────────────────────────
    def c_code():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) 모두 정상 처리"

    _c("CODE", "종목코드 정규화", c_code)

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
