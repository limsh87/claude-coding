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
    if not dart_has_key():
        _k("K1", "DART 재무 배치(2016Q1)", None, "키 없음", f">{CANARY_K1_MIN_ROWS:,}행",
           "DART_API_KEY 미입력 — 재무 기반 TP 전부 비활성")
        _k("K2", "배치 최초 제공 사업연도", None, "키 없음", "≤2016", "")
        return None, None

    # ★ 배치 상한을 정확히 채우면 서버가 021(조회 가능한 회사 개수 초과)로 거부할 수 있다.
    #   5차 실행에서 죽은 DART 호출이 정확히 이 한 건이었다. CANARY 는 '수집을 시작해도
    #   되는지' 판정하는 단계인데, 그 판정 자체가 키를 죽이면 본말전도다. 여유를 둔다.
    batch = [str(c) for c in corps[:max(1, DART_MULTI_BATCH // 2)]]
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
    # ★ first_year 가 None 이면 '탐침이 아무것도 못 받았다'는 뜻이지 '2016년 데이터가 없다'가
    #   아니다. 예전엔 그대로 문자열에 끼워 "시작일을 None년 이후로 상향" 이라는 실행 불가능한
    #   지시가 찍혔다 — 처방이 원인 진단과 어긋나면 사용자는 엉뚱한 곳을 고친다.
    _k("K2", "배치 최초 제공 사업연도", k2, str(first_year or "미확인"), "≤2016",
       "" if k2 else (f"백테스트 시작일을 {first_year}년 이후로 상향해야 합니다" if first_year
                      else "2015~2018 탐침이 모두 빈 응답 — 키·한도·네트워크를 먼저 확인하세요. "
                           "이 결과만으로 시작연도를 바꾸지 마세요."))
    return k1, k2


# ── K3 : 필수 계정 커버리지 ─────────────────────────────────────────────────────────────────
CANARY_REQUIRED_ACCOUNTS = ["revenue", "inventory", "receivable", "cfo", "capex", "tax_expense"]


def _canary_accounts(corps: Sequence[str], year: int) -> Optional[bool]:
    if not dart_has_key():
        _k("K3", "필수계정 커버리지", None, "키 없음", f"≥{CANARY_K3_MIN_COV:.0%}", "")
        return None
    jobs = [(c, year, REPRT_CODES["FY"]) for c in corps]
    res = [d for d in pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 8),
                              desc="CANARY K3 계정") if d is not None and len(d)]
    if not res:
        _k("K3", "필수계정 커버리지", False, "응답 0건", f"≥{CANARY_K3_MIN_COV:.0%}",
           "재무 기반 TP 전부 비활성 위험 — 키·한도를 확인하세요")
        return False
    _raw = pd.concat(res, ignore_index=True)
    # ★ 탐침으로 받은 전체재무제표도 공용 인덱스에 남긴다(절대1원칙). 200사 × FY 1년치는
    #   Tier-2 본수집이 곧바로 다시 요청할 조합이고, 그 호출은 하루 예산에서 빠진다.
    try:
        _prev = VAULT.get_table("dart_fnltt_raw", scope="shared")
        _acc = pd.concat([f for f in (_prev, _raw) if f is not None and len(f)],
                         ignore_index=True)
        _keys = [c for c in ("corp_code", "bsns_year", "reprt_code", "sj_div",
                             "account_id", "account_nm") if c in _acc.columns]
        if _keys:
            _acc = _acc.drop_duplicates(_keys, keep="last")
        VAULT.put_table("dart_fnltt_raw", _acc, scope="shared", domain="dart",
                        source="CANARY K3 탐침분 (본수집이 재요청하지 않도록 영속)",
                        backup=False)
        LOG.ok(f"CANARY 탐침 재무 {len(_raw):,}행을 공용 인덱스에 저장했습니다 — "
               f"Tier-2 본수집이 같은 조합을 다시 묻지 않습니다.")
    except Exception as e:                                           # noqa
        LOG.debug(f"CANARY 재무 저장 실패({type(e).__name__}) — 판정에는 영향 없음")
    W = tidy_financials(_raw)
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
       "" if ok else (f"미달 계정 {weak} 을 쓰는 센서는 결측으로 두고 진행합니다(0 채움 금지). "
                      f"※ 재고·매출채권은 금융·지주·순수서비스 기업에 **원래 없는** 계정이라 "
                      f"표본에 그런 업종이 섞이면 80% 안팎이 정상입니다 — 수집 실패와 구분하려면 "
                      f"§6 커버리지표의 업종별 분포를 함께 보세요."))
    return ok


# ── K4 : 가격 10년 ──────────────────────────────────────────────────────────────────────────
def _canary_price(codes: Sequence[str], sec: Optional[pd.DataFrame] = None) -> bool:
    """탐침 구간(2016 상반기) 가격 확보율.

    ★ 분모를 반드시 '그 구간에 실제로 상장돼 있던 종목'으로 좁힌다.
      이 전략의 CANARY 표본은 생존자편향을 없애려고 폐지종목을 대역 비중대로 섞어 뽑는다.
      2016 이후 상장했거나 2016 이전에 이미 폐지된 종목은 2016 상반기 시세가 **없는 게 정상**이다.
      그것을 실패로 세면, 편향을 제대로 제거할수록 K4 가 FAIL 로 기울어 임계값을 낮추라는
      압력이 생긴다 — 정확히 스펙이 금지하는 방향이다(§2 "임계값을 낮춰 통과시키지 말 것").
    """
    P0, P1 = as_ts("2016-01-01"), as_ts("2016-06-30")
    codes = [str(c) for c in codes]
    elig, n_off = codes, 0
    if sec is not None and len(sec):
        s = sec.drop_duplicates("code").copy()
        s.index = pd.Index(s["code"].astype(str))
        nat = pd.Series(pd.NaT, index=s.index)
        ld = as_ts_series(s["listing_date"]) if "listing_date" in s.columns else nat
        dd = as_ts_series(s["delisting_date"]) if "delisting_date" in s.columns else nat
        live = ((ld.isna() | (ld <= P1)) & (dd.isna() | (dd >= P0)))
        live = pd.Series(np.asarray(live), index=s.index)  # as_ts_series 가 인덱스를 갈아끼워도 안전
        elig = [c for c in codes if bool(live.get(c, True))]
        n_off = len(codes) - len(elig)
    if not elig:
        elig, n_off = codes, 0

    # ★ 판정 기준을 '폐지 예정 여부'로 쪼갠다.
    #   존속 종목의 시세 결손은 진짜 결손이다 — 그 종목은 실제로 담겨서 수익률을 만든다.
    #   반면 이미 폐지된 종목의 시세 결손은 백테스트 엔진이 -100%(정리매매가 없으면)로
    #   처리하므로 **보수적 방향**이며, 이를 실패로 세면 편향을 제대로 제거할수록
    #   K4 가 FAIL 로 기울어 임계값을 낮추라는 압력이 생긴다(§2 가 금지하는 방향).
    #   → 존속에 엄격한 기준(≥95%)을 걸고, 폐지분은 정보성으로 따로 보고한다.
    dead: set = set()
    if sec is not None and len(sec) and "delisting_date" in sec.columns:
        dead = set(sec.loc[sec["delisting_date"].notna(), "code"].astype(str))

    chain_used = Counter()
    def _one(c):
        for nm, fn in PRICE_CHAIN:
            try:
                d = fn(c, "2016-01-01", "2016-06-30")
            except Exception:
                d = None
            if d is not None and len(d):
                return nm
        return None
    res = pmap_io(_one, elig, workers=min(N_WORKERS_IO, 8), desc="CANARY K4 가격")
    live_n = live_ok = dead_n = dead_ok = 0
    for c, r in zip(elig, res):
        if r:
            chain_used[r] += 1
        if c in dead:
            dead_n += 1
            dead_ok += 1 if r else 0
        else:
            live_n += 1
            live_ok += 1 if r else 0
    rate_live = live_ok / max(live_n, 1)
    rate_dead = dead_ok / max(dead_n, 1)
    ok = (live_n == 0) or (rate_live >= 0.95)
    _k("K4", "10년 가격 확보", ok,
       f"존속 {live_ok}/{live_n} ({rate_live:.0%})" +
       (f" · 폐지 {dead_ok}/{dead_n} ({rate_dead:.0%}, 미확보분은 -100% 처리)" if dead_n else "") +
       (f" · 구간 미상장 {n_off}종목 분모 제외" if n_off else "") + " · " +
       (", ".join(f"{k}×{v}" for k, v in chain_used.most_common()) or "경로 없음"),
       "존속 종목 ≥95%",
       "" if ok else "존속 종목의 시세가 비어 있습니다 — 체인(pykrx→FDR→네이버→yfinance)과 "
                     "네트워크·차단을 확인하세요. 폐지 종목 결손은 여기 포함되지 않습니다.")
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
    if not dart_has_key():
        for kid, nm, crit in (("K7", "empSttus 응답", f"≥{CANARY_K7_MIN_RATE:.0%}"),
                              ("K8", "연간급여총액 기재율", f"≥{CANARY_K8_MIN_RATE:.0%}"),
                              ("K9", "단위 정합성", f"불일치<{CANARY_K9_MAX_BAD:.0%}")):
            _k(kid, nm, None, "키 없음", crit, "DART_API_KEY 미입력")
        return None, None, None

    rows = [r for r in pmap_io(lambda c: _emp_one_raw(c, year), list(corps),
                               workers=min(N_WORKERS_IO, 12), desc="CANARY K7~K9 직원현황")
            if r is not None]
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 탐침으로 받은 것도 **반드시 캐시에 남긴다** (절대1원칙) ★★
    #    예전엔 200사 × empSttus 를 실제로 받아 비율만 계산하고 프레임을 통째로 버렸다.
    #    같은 실행의 본수집(L1.EMP)이 조금 뒤에 그 200사를 **다시** 요청했고,
    #    그 호출들은 알파(직원현황)의 하루 예산에서 그대로 빠져나갔다.
    #    사용자 원칙은 '어떤 신규수집데이터든 무조건 캐시저장-재호출 가능하게' 다 —
    #    탐침이라고 예외가 아니다. 저장해 두면 본수집의 done 집합이 자동으로 흡수한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    if rows:
        try:
            _emp_checkpoint(VAULT.get_table("dart_employees_ext", scope="shared"), rows)
            LOG.ok(f"CANARY 탐침으로 받은 직원현황 {len(rows):,}행을 공용 인덱스에 저장했습니다 "
                   f"— 본수집(L1.EMP)이 같은 조합을 다시 묻지 않습니다(호출 예산 절약).")
        except Exception as e:                                       # noqa
            LOG.debug(f"CANARY 직원현황 저장 실패({type(e).__name__}) — 판정에는 영향 없음")
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


DART_DEPENDENT_KS = ("K1", "K2", "K3", "K7", "K8", "K9")


def canary_resource_flip() -> bool:
    """DART 가 자원 조건으로 멈춘 상태라면, 이미 기록된 DART 검사 FAIL 을 SKIP 으로 되돌린다.

    ★ 예산은 CANARY 도중에도 바닥난다(시작 시점엔 남아 있었던 경우). 그때 기록된 FAIL 은
      '자원 없음'을 '데이터 없음'으로 오판한 결과다. 되돌린 사실 자체를 로그로 남겨
      은폐가 아니라 정정임을 밝힌다. 되돌렸으면 True.
    """
    why = dart_halt_reason()
    if not why:
        return False
    flipped = [r["id"] for r in CANARY_RESULTS
               if r["id"] in DART_DEPENDENT_KS and r["passed"] is False]
    for r in CANARY_RESULTS:
        if r["id"] in DART_DEPENDENT_KS and r["passed"] is False:
            r["passed"], r["fatal"] = None, False
            r["measured"] = f"{r['measured']}  ← 측정 중 {why}"
            r["action"] = "자원 조건으로 판정 보류. 데이터 부재가 아닙니다."
    if flipped:
        LOG.warn(f"수집 도중 DART 가 중단됐습니다 — {why}. "
                 f"{flipped} 의 FAIL 을 **판정 보류(SKIP)** 로 되돌립니다. "
                 f"호출권이 없어 못 받은 것을 '데이터가 없다'로 판정하면 안 됩니다.")
    return True


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

    # ★ DART 를 지금 쓸 수 없는 상태라면, DART 의존 검사는 FAIL 이 아니라 SKIP 이다.
    #   '오늘 호출권이 없다'는 것과 '그 데이터가 세상에 없다'는 것은 전혀 다른 사건이고,
    #   후자의 처방(백테스트 시작연도 상향·전략 축소)을 전자에 적용하면 일시적 조건 때문에
    #   전략이 영구히 훼손된다. 실제로 이것 때문에 실행이 §12-2 킬 기준으로 죽었다.
    halt = dart_halt_reason()
    if halt:
        LOG.warn(f"DART 를 지금 쓸 수 없습니다 — {halt}. "
                 f"K1·K2·K3·K7·K8·K9 는 **판정 보류(SKIP)** 로 두고 진행합니다. "
                 f"이 상태에서의 '응답 0건'은 데이터 부재의 증거가 아니므로 킬 기준을 걸지 않습니다.")
        for kid, nm, crit in (("K1", "DART 재무 배치(2016Q1)", f">{CANARY_K1_MIN_ROWS:,}행"),
                              ("K2", "배치 최초 제공 사업연도", "≤2016"),
                              ("K3", "필수계정 커버리지", f"≥{CANARY_K3_MIN_COV:.0%}"),
                              ("K7", "empSttus 응답", f"≥{CANARY_K7_MIN_RATE:.0%}"),
                              ("K8", "연간급여총액 기재율", f"≥{CANARY_K8_MIN_RATE:.0%}"),
                              ("K9", "단위 정합성", f"불일치<{CANARY_K9_MAX_BAD:.0%}")):
            _k(kid, nm, None, f"측정 불가 — {halt}", crit,
               "자원 조건입니다. 데이터 부재가 아니므로 시작연도·전략을 바꾸지 마세요.")
        k1 = k2 = k3 = k7 = k8 = k9 = None
    else:
        k1, k2 = _canary_bulk(corps, n_uni)
        k3 = _canary_accounts(corps, probe_year)
        k7, k8, k9 = _canary_emp(corps, probe_year)
        # ══════════════════════════════════════════════════════════════════════════════════
        #  ★ 최근 1개 연도만 재고 PASS 를 주면 앞 구간 공백을 구조적으로 못 본다 ★
        #    7회차가 정확히 그랬다 — K7/K8 이 최근 연도에서 PASS 인데 실제 EMP 커버리지는
        #    2022~2025 네 해뿐이었고, 백테스트 120개월 중 앞 80개월이 무증거였다.
        #    CANARY 의 목적은 '몇 시간 쓰기 전에 막는 것'이므로 **앞 구간을 같이 재야** 한다.
        #    표본을 줄여(1/4) 호출을 늘리지 않으면서 시작연도를 한 번 더 찔러 본다.
        #    받은 것은 캐시에 남으므로 이 호출도 버려지지 않는다.
        # ══════════════════════════════════════════════════════════════════════════════════
        _y0 = as_ts(BACKTEST_START).year - 1
        if _y0 < probe_year and not dart_halt_reason():
            _small = corps[:max(20, CANARY_SAMPLE_N // 4)]
            try:
                _rows = [r for r in pmap_io(lambda c: _emp_one_raw(c, _y0), _small,
                                            workers=min(N_WORKERS_IO, 12),
                                            desc=f"CANARY 시작연도 탐침({_y0})")
                         if r is not None]
                if _rows:
                    _emp_checkpoint(VAULT.get_table("dart_employees_ext", scope="shared"), _rows)
                _r0 = len(_rows) / max(len(_small), 1)
                _p0 = (int(pd.DataFrame(_rows)["payroll_total"].notna().sum()) / max(len(_rows), 1)
                       if _rows else 0.0)
                _ok0 = (_r0 >= CANARY_K7_MIN_RATE) and (_p0 >= CANARY_K8_MIN_RATE)
                _k("K7b", f"시작연도({_y0}) 직원현황 가용성", _ok0,
                   f"응답 {len(_rows)}/{len(_small)} ({_r0:.0%}) · 급여총액 {_p0:.0%}",
                   f"응답≥{CANARY_K7_MIN_RATE:.0%} · 급여≥{CANARY_K8_MIN_RATE:.0%}",
                   "" if _ok0 else
                   f"백테스트 앞 구간에 EMP 신호가 얇습니다. 최근 연도만 PASS 인 것을 "
                   f"'10년 커버리지 확보'로 읽지 마세요 — 결과는 EMP 레짐 분할표에서 읽으세요.")
            except Exception as e:                                   # noqa
                LOG.debug(f"시작연도 탐침 실패({type(e).__name__}) — 판정을 생략합니다.")
    k4 = _canary_price(codes, sec)
    k5 = _canary_delisting(sec)

    if canary_resource_flip():
        k1 = k2 = k3 = k7 = k8 = k9 = None

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
