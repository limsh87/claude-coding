# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  CANARY  K1~K9  (스펙 §2 · 예산 25분)                                                     ║
# ║                                                                                          ║
# ║  목적은 '수집을 시작해도 되는가'를 25분 안에 판정하는 것이다.                               ║
# ║  95분짜리 수집을 다 돌린 뒤 급여총액 기재율이 12% 였다는 걸 아는 것보다,                    ║
# ║  200종목 표본으로 20분 만에 아는 편이 압도적으로 싸다.                                      ║
# ║                                                                                          ║
# ║  ★ 판정은 실측값과 함께 남긴다. "PASS" 만 찍고 숫자를 숨기지 않는다.                        ║
# ║  ★ K5(상장폐지 목록) 실패는 즉시 중단이다. 생존자편향이 확정되기 때문이다(§12-1).           ║
# ║  ★ K8(급여총액 기재율) 실패도 중단이다. 임금프리미엄 자체가 계산 불가이므로                 ║
# ║    이 전략의 존재 이유가 사라진다(§12-2).                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY_RESULTS: List[dict] = []


def _k(kid: str, name: str, passed: Optional[bool], measured: str, criterion: str,
       action: str = "", fatal: bool = False):
    CANARY_RESULTS.append({"id": kid, "name": name, "passed": passed, "measured": measured,
                           "criterion": criterion, "action": action, "fatal": fatal})
    tag = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
    fn = LOG.ok if passed else (LOG.info if passed is None else LOG.warn)
    fn(f"[{kid}] {name} — {tag} · 실측 {measured} (기준 {criterion})" +
       (f" → {action}" if action else ""))


def _num_series(s) -> pd.Series:
    """DART 금액 문자열 → 숫자. 콤마·공백·유니코드 마이너스·'-'(무기재) 처리."""
    t = (pd.Series(s).astype(str)
         .str.replace(",", "", regex=False)
         .str.replace("−", "-", regex=False)
         .str.strip())
    t = t.where(~t.isin(["", "-", "--", "nan", "None", "N/A", "해당사항없음"]))
    return pd.to_numeric(t.str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")


# ── K1 / K2 : DART 재무 일괄(배치) 경로 ─────────────────────────────────────────────────────
def _canary_bulk(corps: Sequence[str], n_universe: int) -> Tuple[Optional[bool], Optional[bool]]:
    """K1: 2016Q1 배치 응답의 실측 행수를 전 유니버스로 외삽. K2: 최초 제공 사업연도 탐침.

    ※ '재무정보 일괄다운로드'는 웹 화면이고 API 가 아니다. 코드가 실제로 타는 배치 경로는
      fnlttMultiAcnt(100사/호출)이므로, 그 경로의 실측 처리량으로 판정한다.
      외삽값임을 표에 명시한다 — 실측처럼 위장하지 않는다.
    """
    if not DART_API_KEY:
        _k("K1", "DART 재무 배치(2016Q1)", None, "키 없음", f">{CANARY_K1_MIN_ROWS:,}행",
           "DART_API_KEY 미입력 — 재무 기반 TP 전부 비활성")
        _k("K2", "배치 최초 제공 사업연도", None, "키 없음", "≤2016", "")
        return None, None

    batch = [str(c) for c in corps[:DART_MULTI_BATCH]]
    rows_per_corp, ok_batch = 0.0, False
    js = dart_api("fnlttMultiAcnt.json", {"corp_code": ",".join(batch), "bsns_year": "2016",
                                          "reprt_code": REPRT_CODES["Q1"]})
    if js and isinstance(js.get("list"), list) and js["list"]:
        d = pd.DataFrame(js["list"])
        n_corp = d["corp_code"].nunique() if "corp_code" in d.columns else max(len(batch), 1)
        rows_per_corp = len(d) / max(n_corp, 1)
        ok_batch = True
    est = int(rows_per_corp * max(n_universe, 1) * 4)          # 4개 분기 보고서 기준
    k1 = ok_batch and est > CANARY_K1_MIN_ROWS
    _k("K1", "DART 재무 배치(2016Q1)", k1,
       f"{rows_per_corp:.1f}행/사 → 전체 외삽 {est:,}행", f">{CANARY_K1_MIN_ROWS:,}행",
       "" if k1 else "Fallback: fnlttSinglAcntAll 단건 경로로 자동 전환(코드에 이미 배선됨)")

    # K2 — 뒤로 탐침해 실제 최초 제공 연도를 찾는다.
    first_year = None
    for y in (2015, 2016, 2017, 2018):
        j = dart_api("fnlttMultiAcnt.json", {"corp_code": ",".join(batch[:50]),
                                             "bsns_year": str(y), "reprt_code": REPRT_CODES["FY"]})
        if j and isinstance(j.get("list"), list) and j["list"]:
            first_year = y
            break
    k2 = first_year is not None and first_year <= 2016
    _k("K2", "배치 최초 제공 사업연도", k2, str(first_year or "미확인"), "≤2016",
       "" if k2 else f"백테스트 시작일을 {first_year}년 이후로 상향해야 합니다")
    return k1, k2


# ── K3 : 필수 계정 커버리지 ─────────────────────────────────────────────────────────────────
CANARY_REQUIRED_ACCOUNTS = ["revenue", "inventory", "receivable", "cfo", "capex", "tax_expense"]


def _canary_accounts(corps: Sequence[str], year: int) -> Optional[bool]:
    if not DART_API_KEY:
        _k("K3", "필수계정 커버리지", None, "키 없음", f"≥{CANARY_K3_MIN_COV:.0%}", "")
        return None
    jobs = [(c, year, REPRT_CODES["FY"]) for c in corps]
    res = [d for d in pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 8),
                              desc="CANARY K3 계정") if d is not None and len(d)]
    if not res:
        _k("K3", "필수계정 커버리지", False, "응답 0건", f"≥{CANARY_K3_MIN_COV:.0%}",
           "재무 기반 TP 전부 비활성 위험 — 키·한도를 확인하세요")
        return False
    W = tidy_financials(pd.concat(res, ignore_index=True))
    n = W["corp_code"].nunique() if len(W) else 0
    cov, weak = {}, []
    for a in CANARY_REQUIRED_ACCOUNTS:
        c = float(W.loc[W[a].notna(), "corp_code"].nunique()) / max(n, 1) if a in W.columns else 0.0
        cov[a] = c
        if c < CANARY_K3_MIN_COV:
            weak.append(a)
    globals()["CANARY_WEAK_ACCOUNTS"] = weak
    ok = not weak
    _k("K3", "필수계정 커버리지", ok,
       " · ".join(f"{a}={cov[a]:.0%}" for a in CANARY_REQUIRED_ACCOUNTS),
       f"전 계정 ≥{CANARY_K3_MIN_COV:.0%}",
       "" if ok else f"미달 계정 {weak} 을 쓰는 센서는 결측으로 두고 진행합니다(0 채움 금지)")
    return ok


# ── K4 : 가격 10년 ──────────────────────────────────────────────────────────────────────────
def _canary_price(codes: Sequence[str]) -> bool:
    got, chain_used = 0, Counter()
    def _one(c):
        for nm, fn in PRICE_CHAIN:
            try:
                d = fn(c, "2016-01-01", "2016-06-30")
            except Exception:
                d = None
            if d is not None and len(d):
                return nm
        return None
    res = pmap_io(_one, list(codes), workers=min(N_WORKERS_IO, 8), desc="CANARY K4 가격")
    for r in res:
        if r:
            got += 1
            chain_used[r] += 1
    rate = got / max(len(codes), 1)
    ok = rate >= 0.90
    _k("K4", "10년 가격 확보", ok, f"{got}/{len(codes)} ({rate:.0%}) · 경로 " +
       (", ".join(f"{k}×{v}" for k, v in chain_used.most_common()) or "없음"),
       "표본 대부분 성공",
       "" if ok else "체인(pykrx→FDR→네이버→yfinance)이 전부 실패 — 네트워크/차단을 확인하세요")
    return ok


# ── K5 : 상장폐지 목록  ★ 실패 시 즉시 중단 ─────────────────────────────────────────────────
def _canary_delisting(sec: pd.DataFrame) -> bool:
    n = int(sec["delisting_date"].notna().sum()) if "delisting_date" in sec.columns else 0
    ok = n >= 50
    _k("K5", "상장폐지 목록 확보", ok, f"폐지일 보유 {n:,}종목", "≥50종목",
       "" if ok else "★ 생존자편향이 확정됩니다 — 중단합니다(§12-1)", fatal=True)
    return ok


# ── K7 / K8 / K9 : empSttus ─────────────────────────────────────────────────────────────────
def _canary_emp(corps: Sequence[str], year: int) -> Tuple[Optional[bool], Optional[bool], Optional[bool]]:
    if not DART_API_KEY:
        for kid, nm, crit in (("K7", "empSttus 응답", f"≥{CANARY_K7_MIN_RATE:.0%}"),
                              ("K8", "연간급여총액 기재율", f"≥{CANARY_K8_MIN_RATE:.0%}"),
                              ("K9", "단위 정합성", f"불일치<{CANARY_K9_MAX_BAD:.0%}")):
            _k(kid, nm, None, "키 없음", crit, "DART_API_KEY 미입력")
        return None, None, None

    rows = [r for r in pmap_io(lambda c: _emp_one_raw(c, year), list(corps),
                               workers=min(N_WORKERS_IO, 12), desc="CANARY K7~K9 직원현황")
            if r is not None]
    n_try = len(corps)
    n_ok = len(rows)
    rate7 = n_ok / max(n_try, 1)
    k7 = rate7 >= CANARY_K7_MIN_RATE
    _k("K7", "empSttus 응답", k7, f"{n_ok}/{n_try} ({rate7:.0%})", f"≥{CANARY_K7_MIN_RATE:.0%}",
       "" if k7 else "실제 최초 가용연도를 찾아 백테스트 시작일을 상향하세요")

    if not rows:
        _k("K8", "연간급여총액 기재율", False, "표본 0건", f"≥{CANARY_K8_MIN_RATE:.0%}",
           "★ 임금프리미엄 계산 불가 — 중단(§12-2)", fatal=True)
        _k("K9", "단위 정합성", None, "표본 0건", f"불일치<{CANARY_K9_MAX_BAD:.0%}", "")
        return k7, False, None

    D = pd.DataFrame(rows)
    n_pay = int(D["payroll_total"].notna().sum())
    rate8 = n_pay / max(len(D), 1)
    k8 = rate8 >= CANARY_K8_MIN_RATE
    _k("K8", "연간급여총액 기재율", k8, f"{n_pay}/{len(D)} ({rate8:.0%})",
       f"≥{CANARY_K8_MIN_RATE:.0%}",
       "" if k8 else "★ 미달 — 임금프리미엄 TP 를 비활성화하고 CORE-D 로 축소 실행합니다",
       fatal=False)

    # K9 — jan_salary_am × sm ≈ fyer_salary_totamt 인가 (단위 혼재 탐지)
    m = D.dropna(subset=["payroll_total", "avg_salary", "employees"])
    m = m[(m["employees"] > 0) & (m["avg_salary"] > 0)]
    if len(m) < 10:
        _k("K9", "단위 정합성", None, f"검증가능 표본 {len(m)}건", f"불일치<{CANARY_K9_MAX_BAD:.0%}",
           "표본 부족 — 본수집에서 재판정합니다")
        return k7, k8, None
    ratio = (m["payroll_total"] / (m["avg_salary"] * m["employees"])).replace([np.inf, -np.inf], np.nan)
    bad = float(((ratio > 10) | (ratio < 0.1)).mean())
    k9 = bad < CANARY_K9_MAX_BAD
    _k("K9", "단위 정합성 (jan×sm≈tot)", k9,
       f"중앙비 {ratio.median():.2f} · 10배이상 불일치 {bad:.1%} (n={len(m)})",
       f"불일치<{CANARY_K9_MAX_BAD:.0%}",
       "" if k9 else "단위(원/천원/백만원) 혼재 — 정규화에서 배수 역추정을 적용합니다")
    return k7, k8, k9


def canary_sample(sec: pd.DataFrame, monthly: pd.DataFrame, n: int = None) -> List[str]:
    """CANARY 표본 추출 — U-MID 대역에서, **폐지 종목 비율까지 유니버스와 맞춰서** 뽑는다.

    ★ 전 구간 거래대금 중앙값으로 한 줄 세우면 표본이 조용히 생존자 쪽으로 쏠린다.
      일찍 폐지된 종목은 관측 개월 수가 적어 중앙값 순위가 낮게 잡히고, 그 결과 K3/K7/K8 이
      '오래 살아남은 회사의 공시 충실도'를 재게 된다 — 실제 수집률보다 낙관적인 수치가 나오고,
      그걸 근거로 수집을 시작한다. 캐너리의 목적과 정반대다.
    → ① 월별 랭크로 U-MID 대역에 한 번이라도 들어온 종목을 후보로 삼고
      ② 그 후보 안에서 폐지/존속 비율을 그대로 유지해 균등 간격 추출한다.
    """
    n = CANARY_SAMPLE_N if n is None else n
    if monthly is None or monthly.empty or "adv20" not in monthly.columns:
        return sec["code"].astype(str).tolist()[:n]
    pm = monthly[["code", "month", "adv20"]].copy()
    pm["rk"] = pm.groupby("month", observed=True)["adv20"].rank(ascending=False, method="first")
    band = pm[pm["rk"].between(UMID_RANK_LO, UMID_RANK_HI) & (pm["adv20"] >= MIN_ADV_KRW)]
    cand = band["code"].value_counts()               # 대역에 머문 개월 수 순
    codes = [str(c) for c in cand.index]
    if not codes:
        LOG.warn("U-MID 대역 후보가 없어 거래대금 상위 순으로 캐너리 표본을 뽑습니다.")
        codes = (monthly.groupby("code", observed=True)["adv20"].median()
                 .sort_values(ascending=False).index.astype(str).tolist())
    dead = set(sec.loc[sec["delisting_date"].notna(), "code"].astype(str))
    d_list = [c for c in codes if c in dead]
    l_list = [c for c in codes if c not in dead]
    share = len(d_list) / max(len(codes), 1)
    n_d = min(len(d_list), int(round(n * share)))
    n_l = min(len(l_list), n - n_d)

    def _stride(xs, k):
        if k <= 0 or not xs:
            return []
        step = max(1, len(xs) // k)
        return xs[::step][:k]

    pick = _stride(d_list, n_d) + _stride(l_list, n_l)
    LOG.info(f"CANARY 표본 {len(pick)}종목 — U-MID 대역 후보 {len(codes):,}개 중 "
             f"폐지 {n_d}·존속 {n_l} (대역 내 폐지비율 {share:.1%}을 그대로 반영해 "
             f"생존자 쏠림을 제거)")
    return pick


def run_canary(sec: pd.DataFrame, sample_codes: Sequence[str]) -> dict:
    """CANARY 전체 실행. 반환 dict 는 하류가 '무엇을 끄고 갈지' 정하는 데 쓴다."""
    LOG.banner("③ CANARY K1~K9", "수집을 시작해도 되는지 25분 안에 판정합니다 (스펙 §2)")
    CANARY_RESULTS.clear()
    t0 = time.time()

    s = sec[sec["code"].isin(list(sample_codes))].copy()
    if s.empty:
        s = sec.head(CANARY_SAMPLE_N).copy()
    corps = [c for c in s["corp_code"].dropna().astype(str).unique().tolist()][:CANARY_SAMPLE_N]
    codes = s["code"].astype(str).tolist()[:CANARY_SAMPLE_N]
    n_uni = int(sec["corp_code"].notna().sum())
    probe_year = min(as_ts(BACKTEST_END).year - 1, _dt.date.today().year - 1)

    LOG.info(f"표본 {len(codes)}종목 / corp_code {len(corps)}개 · 직원현황 탐침연도 {probe_year}")

    k1, k2 = _canary_bulk(corps, n_uni)
    k3 = _canary_accounts(corps, probe_year)
    k4 = _canary_price(codes)
    k5 = _canary_delisting(sec)
    k7, k8, k9 = _canary_emp(corps, probe_year)

    LOG.table([[r["id"], _trunc(r["name"], 26),
                "PASS" if r["passed"] else ("SKIP" if r["passed"] is None else "FAIL"),
                _trunc(r["measured"], 46), _trunc(r["criterion"], 18),
                _trunc(r["action"], 34)] for r in CANARY_RESULTS],
              ["ID", "확인 항목", "판정", "실측", "기준", "FAIL 시 조치"],
              ["c", "l", "c", "l", "l", "l"], title="CANARY 실측표 (§2)", maxw=48)

    runtime_mark("CANARY", time.time() - t0)
    verdict = {"K1": k1, "K2": k2, "K3": k3, "K4": k4, "K5": k5, "K7": k7, "K8": k8, "K9": k9,
               "wage_premium_ok": (k8 is not False),
               "weak_accounts": globals().get("CANARY_WEAK_ACCOUNTS", [])}

    fatal = [r for r in CANARY_RESULTS if r["fatal"] and r["passed"] is False]
    if fatal and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(
            "CANARY 치명 실패: " + ", ".join(f"{r['id']}({r['name']})" for r in fatal) +
            " — §12 킬 기준입니다. 임계값을 낮춰 통과시키지 마십시오.")
    if k8 is False:
        LOG.warn("K8 미달 — 임금프리미엄(TP_N1)을 비활성화하고 CORE-D + TP_N2/N3 로 진행합니다. "
                 "이 사실은 최종 리포트에 그대로 명시됩니다.")
    return verdict


def canary_report_md() -> str:
    lines = ["# CANARY 실측 리포트 (TCD v3 · 전략3)", "",
             f"- 생성: {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
             f"- 백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
             "| ID | 항목 | 판정 | 실측 | 기준 | 조치 |", "|---|---|---|---|---|---|"]
    for r in CANARY_RESULTS:
        tag = "PASS" if r["passed"] else ("SKIP" if r["passed"] is None else "**FAIL**")
        lines.append(f"| {r['id']} | {r['name']} | {tag} | {r['measured']} | "
                     f"{r['criterion']} | {r['action'] or '-'} |")
    return "\n".join(lines) + "\n"
