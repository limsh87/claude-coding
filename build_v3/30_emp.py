# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  EMP-LITE — DART 직원현황(empSttus) 확장 수집 + C15 한계임금                         ║
# ║                                                                                          ║
# ║  코어(v2)의 fetch_dart_employees 는 sm 과 급여총액만 남기고 jan_salary_am·rgllbr_co 를     ║
# ║  버린다. 이 전략은 그 두 필드가 없으면 성립하지 않으므로 확장판을 따로 둔다.                 ║
# ║  → 공용 인덱스 테이블명도 다르다: dart_employees_ext (다른 전략도 그대로 재사용 가능)       ║
# ║                                                                                          ║
# ║  ★ 설계상 가장 중요한 결정: EMP 센서는 **연도 프레임에서 계산한다.**                        ║
# ║    월 패널에 먼저 붙인 뒤 diff(12) 를 하면, 제출일(rcept_dt)이 해마다 며칠씩 밀리는         ║
# ║    구조 때문에 "12개월 전 행"이 같은 사업연도를 가리키는 달이 생긴다 → 차분이 0 이 되고     ║
# ║    Δ직원수=0 이 되어 C15(a) 가 그 관측을 통째로 버린다. 조용히, 로그 없이.                  ║
# ║    연도 프레임에서 계산하면 Δ는 언제나 정확히 1개 사업연도 간격이고,                        ║
# ║    PIT 안전성은 merge_asof(knowledge_date=rcept_dt) 가 그대로 보장한다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EMP_EXT_COLS = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "employees",
                "regular", "payroll_total", "avg_salary", "n_rows", "unit_fix",
                "pay_fix", "src_flag"]

_TOTAL_TOKENS = {"합계", "계", "소계", "총계", "합 계", "전체", "총 계", "합계(계)", "-"}

# 서킷브레이커 — 연속 실패가 이 수를 넘으면 남은 호출을 즉시 포기한다(§3).
EMP_CIRCUIT_MAX = 15
_EMP_CB = {"consec": 0, "tripped": False, "lock": threading.Lock()}


def _emp_cb_ok() -> bool:
    with _EMP_CB["lock"]:
        return not _EMP_CB["tripped"]


def _emp_cb_mark(success: bool):
    with _EMP_CB["lock"]:
        if success:
            _EMP_CB["consec"] = 0
        else:
            _EMP_CB["consec"] += 1
            if _EMP_CB["consec"] >= EMP_CIRCUIT_MAX and not _EMP_CB["tripped"]:
                _EMP_CB["tripped"] = True
                LOG.warn(f"직원현황 수집 서킷브레이커 작동 — 연속 {EMP_CIRCUIT_MAX}건 실패. "
                         f"남은 호출을 포기하고 여기까지 받은 것을 저장합니다. "
                         f"(대개 일일 한도 소진 또는 IP 차단입니다. 내일 재실행하면 이어받습니다)")


def _emp_pick_rows(d: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """부문×성별 분해 행만 남긴다. 소계/합계 행과 섞으면 인원이 두 배로 계산된다.

    다만 '분해 행이 아예 없고 합계 행 하나만 제출한 회사'가 실재한다. 그 경우까지
    버리면 중소형주가 통째로 사라지므로, 분해 행이 없을 때만 합계 행을 쓴다.
    어느 경로를 탔는지는 src_flag 로 남겨 하류에서 감사할 수 있게 한다.
    """
    def _is_total(colname):
        if colname not in d.columns:
            return pd.Series(False, index=d.index)
        v = d[colname].astype(str).str.strip()
        return v.isin(_TOTAL_TOKENS)

    tot_b, tot_s = _is_total("fo_bbm"), _is_total("sexdstn")
    detail = d[~tot_b & ~tot_s]
    if len(detail):
        return detail, "detail"
    # 부문만 합계이고 성별은 분해된 경우 (또는 그 반대)
    half = d[~(tot_b & tot_s)]
    if len(half):
        return half, "half"
    return d, "total_only"


def _norm_money(v: float, kind: str) -> Tuple[float, int]:
    """단위(원/천원/백만원) 혼재 보정. (보정값, 적용배수) 를 돌려준다.

    한국 상장사 1인 평균급여의 현실 범위는 대략 1,500만 ~ 3억원이다.
    이 범위를 크게 벗어나면 단위가 원이 아니라는 뜻이므로 1000 배수로 스냅한다.
    범위 안으로 못 들어오면 보정하지 않고 그대로 둔다 — 억지로 맞추면 조용한 오염이 된다.
    """
    if not np.isfinite(v) or v <= 0:
        return (np.nan, 1)
    lo, hi = (5e6, 5e8) if kind == "avg" else (0.0, np.inf)
    if kind != "avg":
        return (v, 1)
    for mult in (1, 1_000, 1_000_000):
        if lo <= v * mult <= hi:
            return (v * mult, mult)
    return (v, 1)


def _emp_one_raw(corp: str, year: int) -> Optional[dict]:
    """empSttus 단건 → 정규화된 연 1행. 실패는 None (예외를 위로 던지지 않는다)."""
    if not _emp_cb_ok():
        return None
    try:
        time.sleep(0.05 + random.random() * 0.10)          # §5 — 0.05~0.15s 지연
        js = dart_api("empSttus.json", {"corp_code": str(corp), "bsns_year": str(int(year)),
                                        "reprt_code": REPRT_CODES["FY"]}, no_data_ok=True)
    except Exception:
        _emp_cb_mark(False)
        return None
    # ★ '그 해에 사업보고서를 안 낸 회사'(status 013)는 **정상 응답**이지 실패가 아니다.
    #   실패로 세면 서킷브레이커가 정상 데이터만으로 터진다: 잡 격자가 corp × year 라
    #   신규상장사·폐지사는 초기/말기 연도가 통째로 013 이고, 12개 스레드가 공유하는
    #   연속실패 카운터는 그런 회사 몇 곳이면 15에 도달한다. 그러면 아직 받지 않은
    #   수천 건을 전부 포기하고, 로그에는 '차단당한 것 같다'는 오해를 남긴다.
    if isinstance(js, dict) and str(js.get("status", "")) == "013":
        _emp_cb_mark(True)
        return None
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        _emp_cb_mark(False)
        return None
    _emp_cb_mark(True)

    d = pd.DataFrame(js["list"])
    sel, flag = _emp_pick_rows(d)
    if sel.empty:
        return None

    sm = _num_series(sel.get("sm", pd.Series(dtype=object)))
    reg = _num_series(sel.get("rgllbr_co", pd.Series(dtype=object)))
    cnt = _num_series(sel.get("cnttk_co", pd.Series(dtype=object)))
    tot = _num_series(sel.get("fyer_salary_totamt", pd.Series(dtype=object)))
    jan = _num_series(sel.get("jan_salary_am", pd.Series(dtype=object)))

    emp = float(sm.sum(skipna=True)) if sm.notna().any() else np.nan
    if not np.isfinite(emp) or emp <= 0:
        # sm 이 비면 정규직+계약직으로 복원한다 (일부 제출본이 sm 을 비워 둔다)
        alt = float(reg.fillna(0).sum() + cnt.fillna(0).sum())
        emp = alt if alt > 0 else np.nan
    regular = float(reg.sum(skipna=True)) if reg.notna().any() else np.nan
    payroll = float(tot.sum(skipna=True)) if tot.notna().any() else np.nan

    # ★ jan_salary_am(1인 평균급여)은 절대 합산하지 않는다. 인원 가중평균이 유일하게 옳다.
    if jan.notna().any() and sm.notna().any():
        w = sm.where(sm > 0)
        num = (jan * w).sum(skipna=True)
        den = w.where(jan.notna()).sum(skipna=True)
        avg = float(num / den) if den and den > 0 else float(jan.mean(skipna=True))
    elif jan.notna().any():
        avg = float(jan.mean(skipna=True))
    else:
        avg = np.nan

    avg, unit_fix = _norm_money(avg, "avg")

    # ── 급여총액 단위 보정 ──────────────────────────────────────────────────────────────
    #   tot ≈ avg × emp 가 성립해야 한다. 다만 **먼저 '고칠 필요가 있는가'를 묻는다.**
    #
    #   ★ 가장 가까운 1000 배수를 무조건 고르면 멀쩡한 값을 망친다: 1인평균급여가 그 회사를
    #     대표하지 못하는 제출본(예: 임원만 기재)에서는 expect 가 실제보다 수십 배 작아지고,
    #     그러면 '÷1000' 이 오히려 오차를 줄이는 것처럼 보여 **정확한 급여총액이 1000분의 1로
    #     조용히 축소된다.** 한계임금은 이 값의 차분이므로 그대로 신호가 뒤집힌다.
    #   → 원값이 이미 10배 이내면 손대지 않는다. 명백히 틀렸을 때만, 그것도 배수 보정이
    #     3배 이내로 들어맞을 때만 고친다. 둘 다 아니면 폐기한다(0 채움 금지).
    pay_fix = 1
    if np.isfinite(payroll) and np.isfinite(avg) and np.isfinite(emp) and emp > 0 and avg > 0:
        expect = avg * emp
        err0 = abs(math.log10(max(payroll, 1e-9) / expect))
        if err0 > 1.0:                                     # 10배 넘게 어긋난 경우에만 개입
            best, best_err = None, np.inf
            for m2 in (1_000, 1_000_000, 0.001, 0.000001):
                err = abs(math.log10(max(payroll * m2, 1e-9) / expect))
                if err < best_err:
                    best, best_err = m2, err
            if best_err <= 0.5:                            # 보정 후 3배 이내로 맞을 때만 채택
                payroll, pay_fix = payroll * best, best
            else:
                payroll = np.nan                           # §5 — 불일치 10배+ 폐기

    rn = str(sel["rcept_no"].iloc[0]) if "rcept_no" in sel.columns and len(sel) else ""
    kd = _knowledge_from_rcept(rn, REPRT_CODES["FY"], int(year))
    return {"corp_code": str(corp), "bsns_year": int(year), "rcept_no": rn,
            "rcept_dt": kd, "employees": emp, "regular": regular,
            "payroll_total": payroll, "avg_salary": avg, "n_rows": int(len(sel)),
            "unit_fix": int(unit_fix), "pay_fix": float(pay_fix), "src_flag": flag}


def fetch_emp_status(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """empSttus 증분 수집. 공용 캐시(dart_employees_ext)를 먼저 소진하고 부족분만 호출한다."""
    cached = VAULT.get_table("dart_employees_ext", scope="shared")
    done = set()
    if cached is not None and len(cached):
        try:
            done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
            LOG.ok(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용 ({len(done):,} 조합) — "
                   f"이만큼은 API 를 다시 부르지 않습니다")
        except Exception:
            done = set()
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 직원현황 신규 수집을 건너뜁니다. "
                 "캐시에 있는 것만으로 진행하며, 없으면 EMP-LITE 전 센서가 결측입니다.")
        return _emp_finalize(cached, [])

    corps = [str(c) for c in dict.fromkeys(corp_codes) if str(c) and str(c) != "nan"]
    if EMP_MAX_CORPS and EMP_MAX_CORPS > 0:
        corps = corps[:EMP_MAX_CORPS]
    jobs = [(c, y) for c in corps for y in years if (c, int(y)) not in done]
    if RUN_MODE == "CACHED":
        if jobs:
            LOG.info(f"RUN_MODE='CACHED' — 신규 수집 대상 {len(jobs):,}건을 건너뜁니다.")
        jobs = []

    got: List[dict] = []
    if jobs:
        LOG.info(f"직원현황 신규 수집 {len(jobs):,}건 "
                 f"({len(corps):,}사 × {len(years)}년, 캐시 적중 {len(done):,}) — "
                 f"약 {len(jobs)/max(RATE_LIMIT_QPS.get('dart',8.0),1)/60:.0f}분 예상")
        _EMP_CB.update({"consec": 0, "tripped": False})
        res = pmap_io(lambda j: _emp_one_raw(j[0], j[1]), jobs,
                      workers=min(N_WORKERS_IO, 12), desc="DART 직원현황(확장)")
        got = [r for r in res if r]
        LOG.info(f"직원현황 신규 확보 {len(got):,}/{len(jobs):,}건")
    return _emp_finalize(cached, got)


def _emp_finalize(cached: Optional[pd.DataFrame], got: List[dict]) -> pd.DataFrame:
    frames = []
    if cached is not None and len(cached):
        frames.append(cached)
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        LOG.warn("직원현황 데이터가 전혀 없습니다 — EMP-LITE 3개 TP 가 모두 결측이 됩니다.")
        return pd.DataFrame(columns=EMP_EXT_COLS)
    E = pd.concat(frames, ignore_index=True)
    for c in EMP_EXT_COLS:
        if c not in E.columns:
            E[c] = np.nan
    E["corp_code"] = E["corp_code"].astype(str)
    E["bsns_year"] = pd.to_numeric(E["bsns_year"], errors="coerce").astype("Int64")
    E = E.dropna(subset=["bsns_year"])
    E["bsns_year"] = E["bsns_year"].astype(int)
    E = E.drop_duplicates(["corp_code", "bsns_year"], keep="last").reset_index(drop=True)
    E["rcept_dt"] = as_ts_series(E["rcept_dt"])
    # rcept_dt 가 없으면 법정 제출기한(사업보고서 90일)으로 보수적 추정 — '늦게 알았다' 방향
    miss = E["rcept_dt"].isna()
    if miss.any():
        E.loc[miss, "rcept_dt"] = [
            _knowledge_from_rcept("", REPRT_CODES["FY"], int(y)) for y in E.loc[miss, "bsns_year"]]
    if got:
        VAULT.put_table("dart_employees_ext", E, scope="shared", domain="dart",
                        source="opendart empSttus (v3 확장: jan_salary_am·rgllbr_co 포함)")
    PIPE.io("OUT", "DRIVE", "dart_employees_ext", E, source="opendart empSttus")
    LOG.ok(f"직원현황 총 {len(E):,}행 · {E['corp_code'].nunique():,}사 · "
           f"{E['bsns_year'].min()}~{E['bsns_year'].max()}년 "
           f"(급여총액 기재 {E['payroll_total'].notna().mean():.0%})")
    # 단위 정규화가 얼마나 개입했는지 드러낸다 — 조용한 보정은 조용한 오염과 구별되지 않는다.
    rows = []
    if "unit_fix" in E.columns:
        for m, n in E["unit_fix"].value_counts().sort_index().items():
            rows.append([f"1인평균급여 ×{int(m):,}", f"{int(n):,}",
                         "원 단위 그대로" if int(m) == 1 else "천원/백만원 기재로 판단해 환산"])
    if "pay_fix" in E.columns:
        for m, n in E["pay_fix"].value_counts().sort_index().items():
            rows.append([f"급여총액 ×{float(m):g}", f"{int(n):,}",
                         "손대지 않음" if float(m) == 1.0 else "10배 초과 불일치 → 배수 보정"])
    n_drop = int(E["payroll_total"].isna().sum())
    rows.append(["급여총액 결측/폐기", f"{n_drop:,}", "무기재이거나 10배+ 불일치로 폐기(0 채움 안 함)"])
    if "src_flag" in E.columns:
        for f, n in E["src_flag"].value_counts().items():
            rows.append([f"행 선택 경로: {f}", f"{int(n):,}",
                         {"detail": "부문×성별 분해행 사용(정상)",
                          "half": "한쪽만 합계 — 부분 분해",
                          "total_only": "합계행만 제출 — 이중계상 위험 없음"}.get(str(f), "")])
    LOG.table(rows, ["단위·행선택 정규화", "건수", "의미"], ["l", "r", "l"],
              title="직원현황 정규화 감사 (K9 단위 정합성의 실측 결과)")
    return E


# ── C15 : 한계임금 분모 안정성 (스펙 §4 신설 계약) ──────────────────────────────────────────
C15_STATS: Dict[str, Any] = {}


def build_emp_sensors(E: pd.DataFrame) -> pd.DataFrame:
    """연도 프레임에서 EMP-LITE 센서를 만든다. C15 (a)(b)(d) 를 여기서 강제한다.

    출력 컬럼(연 1행/사):
      nl_emp      Δlog(직원수)
      nl_dn       Δ(직원수)
      nl_marginal Δ(연간급여총액) / Δ(직원수)          ← C15 조건부
      nl_premium  nl_marginal / 전기 1인평균급여액       ← ★ 이 전략의 핵심
      nl_regular  Δ(정규직 비중)
      emp_ok      C15 전 조건 통과 여부 (커버리지 감사용)
    """
    if E is None or E.empty:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "knowledge_date"])
    D = E.sort_values(["corp_code", "bsns_year"]).copy()
    g = D.groupby("corp_code", observed=True)

    # ★ 연도가 비연속이면(예: 2018 → 2020) 차분이 2년치가 되어 '1년간 변화'라는 전제가 깨진다.
    #   그런 관측은 계산하지 않는다. 채워 넣지도 않는다(C15: forward-fill 금지).
    D["year_gap"] = g["bsns_year"].diff()
    contiguous = D["year_gap"] == 1

    emp_prev = g["employees"].shift(1)
    pay_prev = g["payroll_total"].shift(1)
    avg_prev = g["avg_salary"].shift(1)
    reg_ratio = safe_div(D["regular"], D["employees"])
    D["regular_ratio"] = reg_ratio.where((reg_ratio >= 0) & (reg_ratio <= 1.001))

    D["emp_prev"] = emp_prev.where(contiguous)
    D["dn"] = (D["employees"] - emp_prev).where(contiguous)
    D["d_pay"] = (D["payroll_total"] - pay_prev).where(contiguous)
    D["nl_emp"] = np.log(D["employees"].where(D["employees"] > 0)) - \
                  np.log(D["emp_prev"].where(D["emp_prev"] > 0))
    D["nl_dn"] = D["dn"]
    D["nl_regular"] = (D["regular_ratio"] - g["regular_ratio"].shift(1)).where(contiguous) \
        if "regular_ratio" in D.columns else np.nan

    # (a) |Δ직원수| >= max(5, 직원수_{t-1} × 3%) 일 때만 계산
    thresh = np.maximum(C15_MIN_ABS_DN, D["emp_prev"].fillna(0) * C15_MIN_REL_DN)
    gate_a = D["dn"].abs() >= thresh

    # (d) Δ직원수 급변 (>+100% / <-50%) = M&A·분할 의심 → 결측
    rel = safe_div(D["dn"], D["emp_prev"])
    gate_d = (rel <= C15_MNA_UP) & (rel >= C15_MNA_DN)

    ok = gate_a.fillna(False) & gate_d.fillna(False) & contiguous.fillna(False)
    D["nl_marginal"] = safe_div(D["d_pay"], D["dn"]).where(ok)

    # (b) 임금프리미엄 [0, 5] 클리핑. 초과는 '오류'로 보고 NaN — 절대 clip 으로 뭉개지 않는다.
    prem_raw = safe_div(D["nl_marginal"], avg_prev.where(avg_prev > 0))
    in_range = prem_raw.between(C15_PREMIUM_LO, C15_PREMIUM_HI)
    n_out = int((prem_raw.notna() & ~in_range).sum())
    D["nl_premium"] = prem_raw.where(in_range)
    D["emp_ok"] = (D["nl_premium"].notna()).astype(int)

    C15_STATS.update({
        "n_rows": int(len(D)),
        "n_contiguous": int(contiguous.sum()),
        "n_gate_a_fail": int((~gate_a.fillna(False) & contiguous.fillna(False)).sum()),
        "n_gate_d_fail": int((~gate_d.fillna(False) & contiguous.fillna(False)).sum()),
        "n_premium_out_of_range": n_out,
        "n_valid": int(D["nl_premium"].notna().sum()),
    })
    LOG.table([["전체 (사×연) 관측", f"{C15_STATS['n_rows']:,}"],
               ["연도 연속(Δ=1년)", f"{C15_STATS['n_contiguous']:,}"],
               ["(a) |Δ인원| 임계 미달 → 결측", f"{C15_STATS['n_gate_a_fail']:,}"],
               ["(d) M&A·분할 의심 → 결측", f"{C15_STATS['n_gate_d_fail']:,}"],
               ["(b) 프리미엄 [0,5] 이탈 → 결측", f"{C15_STATS['n_premium_out_of_range']:,}"],
               ["★ 최종 유효 임금프리미엄", f"{C15_STATS['n_valid']:,}"]],
              ["C15 게이트", "건수"], ["l", "r"],
              title="C15 한계임금 분모 안정성 (0 채움·forward-fill 금지)")

    # knowledge_date = 사업보고서 접수일. 이것이 PIT 의 전부다.
    D["knowledge_date"] = as_ts_series(D["rcept_dt"])
    D["period_end"] = as_ts_series(D["bsns_year"].astype(int).astype(str) + "-12-31")
    # ★ d_pay·avg_prev 를 함께 내보내는 이유: R5 절제검사가 C15 분모 임계값을 바꿔가며
    #   한계임금을 '재계산'해야 하는데, 원재료가 패널에 없으면 그 절제는 아예 불가능하다.
    D["avg_prev"] = avg_prev
    keep = ["corp_code", "bsns_year", "period_end", "knowledge_date", "employees", "emp_prev",
            "regular_ratio", "payroll_total", "avg_salary", "avg_prev", "dn", "d_pay",
            "nl_emp", "nl_dn", "nl_marginal", "nl_premium", "nl_regular", "emp_ok", "src_flag"]
    out = D[[c for c in keep if c in D.columns]].copy()
    return out


def test_c15(df: pd.DataFrame) -> Tuple[bool, str]:
    """스펙 §4 의 test_c15 를 그대로 코드로 옮긴 자가검정."""
    if df is None or df.empty or "dn" not in df.columns:
        return True, "표본 없음 — 검정 생략"
    d = df.dropna(subset=["emp_prev"])
    if d.empty:
        return True, "표본 없음 — 검정 생략"
    ok = d["dn"].abs() >= np.maximum(C15_MIN_ABS_DN, d["emp_prev"] * C15_MIN_REL_DN)
    leak = int(d.loc[~ok, "nl_marginal"].notna().sum())
    if leak:
        return False, f"C15(a) 위반 — 임계 미달인데 한계임금이 계산된 행 {leak:,}건"
    p = d["nl_premium"].dropna()
    if len(p) and not p.between(C15_PREMIUM_LO, C15_PREMIUM_HI).all():
        return False, (f"C15(b) 위반 — 임금프리미엄이 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}] 밖: "
                       f"min={p.min():.2f} max={p.max():.2f}")
    return True, f"통과 (유효 프리미엄 {len(p):,}건 · 전부 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}])"


# ── §6 커버리지 감사 (필수 출력) ────────────────────────────────────────────────────────────
def emp_coverage_audit(S: pd.DataFrame, umid_n: Dict[int, int],
                       umid_corps: Optional[Dict[int, set]] = None) -> pd.DataFrame:
    """연도별: U-MID 대상 / empSttus 성공 / 급여총액 기재 / C15 통과 / 유효 관측치.

    ★ 분자와 분모는 반드시 같은 모집단이어야 한다. umid_corps 를 주면 그 해 U-MID 였던
      기업으로 분자를 제한한다. 주지 않으면 전 상장사 기준이며, 그 사실을 표 제목에 밝힌다.
    반환 DataFrame 은 emp_coverage.csv 로 저장되고, 시작연도 판정의 근거가 된다.
    """
    rows = []
    if S is None or S.empty:
        LOG.warn("직원현황 패널이 비어 커버리지 감사를 출력할 수 없습니다.")
        return pd.DataFrame(columns=["year", "u_mid", "emp_ok", "pay_ok", "c15_ok", "valid"])
    scoped = umid_corps is not None and len(umid_corps) > 0
    for y in sorted(S["bsns_year"].dropna().astype(int).unique()):
        sub = S[S["bsns_year"] == y]
        if scoped:
            # 사업연도 y 의 공시는 y+1 년에 알려지므로, 그 해 U-MID 였던 기업 기준으로 센다.
            #   ★ 교집합이 비면 그 해엔 U-MID 종목이 아예 없다는 뜻이다(대개 백테스트 창 밖).
            #     그때 필터를 건너뛰면 분자만 전 상장사로 튀어 분모(0)와 어긋난다 → 0 으로 센다.
            keep = umid_corps.get(int(y), set()) | umid_corps.get(int(y) + 1, set())
            sub = sub[sub["corp_code"].astype(str).isin(keep)] if keep else sub.iloc[0:0]
        # ★ 분모도 분자와 **같은 집합**에서 센다. 분모를 '그 해 U-MID', 분자를 'y 또는 y+1 에
        #   U-MID' 로 두면 (사업연도 y 의 공시는 y+1 에 알려지므로 분자는 y+1 을 포함해야 한다)
        #   표가 자기모순에 빠진다 — 분모 0 인데 분자 84 같은 행이 나온다.
        denom = len(keep) if scoped else int(umid_n.get(int(y), 0))
        rows.append({
            "year": int(y),
            "u_mid": int(denom),
            "emp_ok": int(sub["employees"].notna().sum()),
            "pay_ok": int(sub["payroll_total"].notna().sum()),
            "c15_ok": int(sub["nl_marginal"].notna().sum()),
            "valid": int(sub["nl_premium"].notna().sum()),
        })
    C = pd.DataFrame(rows)
    LOG.table([[str(r.year), f"{r.u_mid:,}", f"{r.emp_ok:,}", f"{r.pay_ok:,}",
                f"{r.c15_ok:,}", f"{r.valid:,}",
                "구간밖" if (scoped and r.u_mid == 0) else
                ("부족" if r.valid < C15_MIN_OBS_PER_YR else
                 ("경계" if r.valid < COVERAGE_MIN_OBS_START else "충분"))]
               for r in C.itertuples(index=False)],
              ["사업연도", "U-MID 대상", "empSttus 성공", "급여총액 기재", "C15 통과",
               "유효 관측치", "판정"],
              ["c", "r", "r", "r", "r", "r", "c"],
              title="EMP 커버리지 감사 (§6 — 필수 출력) · 분자 모집단 = " +
                    ("U-MID 기업" if scoped else "전 상장사(분모와 불일치, 참고용)"))
    if not scoped:
        LOG.warn("커버리지 분자를 U-MID 로 제한하지 못했습니다(corp_code 매핑 부재). "
                 "비율이 과대평가될 수 있으므로 시작연도 판정을 보수적으로 읽으세요.")
    return C


def coverage_verdict(C: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], str]:
    """§6 판정: 앞구간의 유효 관측치가 부족하면 백테스트 시작월을 상향한다.

    ★ 시작연도 y 의 관측은 그 해 사업보고서(다음해 3~4월 접수)부터 신호가 되므로,
      창을 자를 때도 '사업연도 y' 가 아니라 '실제로 알 수 있게 된 시점'을 기준으로 자른다.
    """
    if C is None or C.empty:
        return None, "커버리지 표가 비어 판정을 유보합니다."
    good = C[C["valid"] >= COVERAGE_MIN_OBS_START]
    if good.empty:
        worst = int(C["valid"].max()) if len(C) else 0
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 미만입니다 "
                      f"(최대 {worst:,}건). 창을 자르지 않고 전 구간을 쓰되, "
                      f"EMP 신호의 검정력이 낮다는 사실을 결론에 명시합니다.")
    y0 = int(good["year"].min())
    thin = C[C["year"] < y0]
    if thin.empty:
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 이상입니다 "
                      f"— 백테스트 창을 그대로 사용합니다.")
    start = as_ts(f"{y0 + 1}-04-01")          # 사업연도 y0 는 y0+1 년 3~4월에 공시된다
    msg = (f"{int(thin['year'].min())}~{int(thin['year'].max())}년 유효 관측치가 "
           f"{COVERAGE_MIN_OBS_START}건 미만(" +
           ", ".join(f"{int(r.year)}:{int(r.valid)}" for r in thin.itertuples(index=False)) +
           f") → EMP 신호 유효 시작 {start:%Y-%m}. ")
    if COVERAGE_AUTO_TRIM:
        msg += "COVERAGE_AUTO_TRIM=True 이므로 EMP TP 를 이 시점 이전에는 결측으로 둡니다."
    else:
        msg += "COVERAGE_AUTO_TRIM=False 이므로 자르지 않고 그대로 진행합니다."
    return (start if COVERAGE_AUTO_TRIM else None), msg
