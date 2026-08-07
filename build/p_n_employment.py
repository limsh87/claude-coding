

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-N  국민연금 고용  (★ 1순위 · 본체)                                                   ║
# ║                                                                                          ║
# ║  고용은 되돌릴 수 없는 비용 지불이다. 경영진이 수요에 대한 확신 없이 하지 않는 행위이므로,  ║
# ║  매출 추정보다 신뢰도 높은 사적 정보 노출이다.                                              ║
# ║                                                                                          ║
# ║  ★ v2 최대 변경점 — 평균임금이 아니라 '한계임금' 을 쓴다.                                   ║
# ║    평균은 기존 인력에 희석되어 신규 채용의 성격을 못 본다.                                   ║
# ║    보조금 유인 채용은 구조적으로 저임금이므로 wage_premium < 1 이 된다.                     ║
# ║    → 보조금 필터가 별도 패치가 아니라 산식 자체에 내장된다.                                  ║
# ║                                                                                          ║
# ║  반드시 처리한 함정 3가지: (a) 7월 정기결정  (b) 기준소득월액 상한 캡  (c) 분모 불안정        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 국민연금 보험료율. 1998-07 이후 9.0% 로 장기 고정. 연도별로 두어 개정 시 한 줄만 고치면 되게 한다.
NPS_CONTRIB_RATE = {y: 0.09 for y in range(2010, 2027)}
# 기준소득월액 상한(월, 원). 매년 7월 개정. 캡 도달 비율(n5) 산출의 기준.
NPS_INCOME_CAP = {
    2016: 4_340_000, 2017: 4_490_000, 2018: 4_680_000, 2019: 4_860_000, 2020: 5_030_000,
    2021: 5_240_000, 2022: 5_530_000, 2023: 5_900_000, 2024: 6_170_000, 2025: 6_370_000,
    2026: 6_370_000,
}
NPS_REDETERMINE_MONTH = 7          # 기준소득월액 정기결정 시행월 (전년 소득 기준 일괄 갱신)

PACK_N_POLICY = [
    {"policy_id": "YOUTH_ADD_HIRE", "name": "청년추가고용장려금", "start": "2018-03-01",
     "end": "2021-12-31", "pack": "N", "req_type": "연령", "req_value": "만15~34세"},
    {"policy_id": "COVID_RETAIN", "name": "고용유지지원금(코로나 특례)", "start": "2020-02-01",
     "end": "2022-12-31", "pack": "N", "req_type": "없음", "req_value": ""},
    {"policy_id": "YOUTH_LEAP", "name": "청년일자리도약장려금", "start": "2022-01-01",
     "end": None, "pack": "N", "req_type": "연령", "req_value": "만15~34세"},
    {"policy_id": "INTEGRATED_EMP_TAXCREDIT", "name": "통합고용세액공제", "start": "2023-01-01",
     "end": None, "pack": "N", "req_type": "기업규모", "req_value": "중소·중견 우대"},
    {"policy_id": "EMP_INCREASE_TAXCREDIT", "name": "고용증대세액공제", "start": "2018-01-01",
     "end": "2022-12-31", "pack": "N", "req_type": "기업규모", "req_value": "중소·중견 우대"},
    {"policy_id": "DISABLED_QUOTA", "name": "장애인 의무고용률/부담금", "start": "2016-01-01",
     "end": None, "pack": "N", "req_type": "기업규모", "req_value": "상시근로자 50/100/300인"},
    {"policy_id": "SPECIAL_HIRE_PROMOTION", "name": "특별고용촉진장려금", "start": "2020-07-01",
     "end": "2021-12-31", "pack": "N", "req_type": "없음", "req_value": ""},
    {"policy_id": "MIDDLE_AGE_HIRE", "name": "중장년 채용장려금", "start": "2019-01-01",
     "end": None, "pack": "N", "req_type": "연령", "req_value": "만50세 이상"},
    {"policy_id": "REGION_EMP_PROMOTION", "name": "지역고용촉진지원금", "start": "2016-01-01",
     "end": None, "pack": "N", "req_type": "지역", "req_value": "고용위기지역"},
]

PACK_N_INTERP = [
    ("TP_N1", "고부가 인력 확충. 사업 고도화", "저임금 대량채용 — ★보조금 유인 의심"),
    ("TP_N2", "정착하는 확장. 조직 역량 축적", "급조 조직. 회전문 채용"),
    ("TP_N3", "진짜 캐파 확대", "사업장 이전에 불과"),
    ("TP_N4", "희석 없는 확장", "단순 규모 확대"),
]

# 상시근로자 임계 밴드 — 회귀불연속 구간. 이 근처 기업은 신호 신뢰도를 낮춘다.
EMP_THRESHOLD_BANDS = [50, 100, 300]
EMP_BAND_TOL = 0.10


# ── 수집 ────────────────────────────────────────────────────────────────────────────────────
NPS_API = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireService/"
NPS_FIELDS = {
    "wkplNm": "wkpl_name", "bzowrRgstNo": "biz_no", "jnngpCnt": "members",
    "crrmmNtcAmt": "notice_amt", "nwAcqzrCnt": "acq_cnt", "lssJnngpCnt": "loss_cnt",
    "wkplRoadNmDtlAddr": "addr", "ldongAddrMgplDgCd": "sido", "vldtVlKrnNm": "industry",
    "dataCrtYm": "ym", "seq": "seq",
}


def _datagokr_key() -> str:
    """Decoding/Encoding 키 혼동은 공공데이터포털 실패의 1위 원인이다. 자동 감지해 교정한다."""
    k = (DATA_GO_KR_KEY or "").strip()
    if not k:
        return ""
    if "%" in k and re.search(r"%[0-9A-Fa-f]{2}", k):
        dec = unquote(k)
        LOG.warn("DATA_GO_KR_KEY 가 Encoding 키로 보입니다(%XX 포함). "
                 "이중 인코딩을 막기 위해 디코딩해서 사용합니다. "
                 "가능하면 포털에서 '일반 인증키(Decoding)' 를 복사해 넣으세요.")
        return dec
    return k


def fetch_nps_workplaces(months: pd.DatetimeIndex) -> pd.DataFrame:
    """국민연금 가입 사업장 내역(월별). 공용 인덱스에 저장 → 다른 전략도 그대로 재사용."""
    key = _datagokr_key()
    cached = VAULT.get_table("nps_workplace_monthly", scope="shared")
    have = set()
    if cached is not None and len(cached):
        have = set(cached["ym"].astype(str))
        LOG.info(f"공용 캐시에서 국민연금 사업장 {len(cached):,}행 재사용 ({len(have)}개월)")
    if not key:
        if not have:
            LOG.warn("DATA_GO_KR_KEY 미입력 — PACK-N 을 구동할 수 없습니다. "
                     "공공데이터포털에서 '국민연금 가입 사업장 내역' 활용신청 후 "
                     "일반 인증키(Decoding)를 넣어주세요.")
            return pd.DataFrame()
        return cached

    todo = [m for m in months if m.strftime("%Y%m") not in have]
    if RUN_MODE == "CACHED":
        todo = []
    new_rows: List[dict] = []

    def _one(m):
        ym = m.strftime("%Y%m")
        rows, page = [], 1
        while page <= 400:
            limiter("datagokr").wait()
            js = http_json(NPS_API + "getBassInfoSearch", source="datagokr", tries=3,
                           params={"serviceKey": key, "dataCrtYm": ym,
                                   "pageNo": page, "numOfRows": 1000, "resultType": "json"})
            if not js:
                break
            body = (js.get("response", {}).get("body") if isinstance(js, dict) else None) or {}
            items = body.get("items") or {}
            it = items.get("item") if isinstance(items, dict) else items
            if isinstance(it, dict):
                it = [it]
            if not it:
                break
            for r in it:
                rec = {NPS_FIELDS[k]: r.get(k) for k in NPS_FIELDS if k in r}
                rec["ym"] = ym
                rows.append(rec)
            tot = int(body.get("totalCount") or 0)
            if page * 1000 >= tot:
                break
            page += 1
        return rows

    if todo:
        LOG.info(f"국민연금 사업장 신규 수집 {len(todo)}개월")
        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="국민연금 사업장")
        for r in res:
            if r:
                new_rows.extend(r)

    frames = ([cached] if cached is not None and len(cached) else [])
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame()
    N = pd.concat(frames, ignore_index=True)
    for c in ("members", "notice_amt", "acq_cnt", "loss_cnt"):
        if c in N.columns:
            N[c] = pd.to_numeric(N[c], errors="coerce")
    N = N.drop_duplicates(["ym", "biz_no", "wkpl_name"], keep="last")
    if new_rows:
        VAULT.put_table("nps_workplace_monthly", N, scope="shared", domain="nps",
                        source="data.go.kr NpsBplcInfoInqireService")
    LOG.ok(f"국민연금 사업장 {len(N):,}행 · {N['ym'].nunique()}개월")
    PIPE.io("OUT", "DRIVE", "nps_workplace_monthly", N, source="data.go.kr")
    return N


def resolve_nps_to_corp(N: pd.DataFrame, sec: pd.DataFrame,
                        emp: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """사업장 → corp_code 매칭. ① 사업자번호 앞자리 ② 상호 유사도 ③ 주소 검증.
    매칭 결과는 시간구간 테이블로 남긴다(C3)."""
    if N is None or N.empty or sec.empty:
        return (pd.DataFrame(), pd.DataFrame())
    cached = VAULT.get_table("nps_entity_map", scope="shared")
    if cached is not None and len(cached) and RUN_MODE != "FULL":
        LOG.info(f"공용 캐시에서 국민연금 매칭 {len(cached):,}건 재사용")
        return (cached, pd.DataFrame())

    wk = (N.groupby(["biz_no", "wkpl_name"], as_index=False)
           .agg(members=("members", "max"), addr=("addr", "first"),
                first_ym=("ym", "min"), last_ym=("ym", "max")))
    wk["nm"] = wk["wkpl_name"].map(norm_corp_name)
    sec2 = sec.copy()
    sec2["nm"] = sec2["name"].map(norm_corp_name)
    exact = wk.merge(sec2[["code", "corp_code", "name", "nm"]], on="nm", how="left")

    unmatched = exact[exact["code"].isna()].copy()
    if len(unmatched) and len(sec2):
        cand_nm = sec2["nm"].tolist()
        cand_code = sec2["code"].tolist()
        pref: Dict[str, List[int]] = defaultdict(list)
        for i, n in enumerate(cand_nm):
            if n:
                pref[n[:2]].append(i)

        def _fuzzy(n: str) -> Optional[Tuple[str, float]]:
            if not n or len(n) < 2:
                return None
            idxs = pref.get(n[:2], [])
            best, bs = None, 0.0
            for i in idxs:
                s = similarity(n, cand_nm[i])
                if s > bs:
                    best, bs = cand_code[i], s
            return (best, bs) if best and bs >= 92 else None

        hits = [(_fuzzy(n)) for n in unmatched["nm"].tolist()]
        unmatched["code"] = [h[0] if h else None for h in hits]
        unmatched["match_score"] = [h[1] if h else np.nan for h in hits]
        exact.loc[unmatched.index, "code"] = unmatched["code"]
        exact.loc[unmatched.index, "match_score"] = unmatched["match_score"]
    exact["match_score"] = exact.get("match_score", pd.Series(np.nan, index=exact.index)).fillna(100.0)
    exact["match_method"] = np.where(exact["match_score"] >= 99.9, "exact_name", "fuzzy_name")
    M = exact.dropna(subset=["code"])[["biz_no", "wkpl_name", "code", "match_method",
                                       "match_score", "first_ym", "last_ym"]]
    M["valid_from"] = as_ts_series(M["first_ym"].astype(str) + "01")
    M["valid_to"] = as_ts_series(M["last_ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    VAULT.put_table("nps_entity_map", M, scope="shared", domain="nps", source="entity_resolution")
    LOG.ok(f"국민연금 사업장 매칭 {len(M):,}건 → {M['code'].nunique():,}종목 "
           f"(정확일치 {int((M['match_method']=='exact_name').sum()):,} / "
           f"유사매칭 {int((M['match_method']=='fuzzy_name').sum()):,})")
    if M["code"].nunique() < 50:
        LOG.warn(f"매칭 성공 종목이 {M['code'].nunique()}개로 50개 미만입니다 (§15-6 킬 기준). "
                 f"통계적 검정이 불가능하니 PACK-N 결과를 신뢰하지 마세요.")
    PIPE.io("OUT", "DRIVE", "nps_entity_map", M, source="entity_resolution")
    return (M, pd.DataFrame())


def build_nps_panel(N: pd.DataFrame, M: pd.DataFrame, emp: pd.DataFrame,
                    months: pd.DatetimeIndex) -> pd.DataFrame:
    """종목-월 단위 국민연금 패널 + θ_N (관측커버리지)."""
    if N is None or N.empty or M is None or M.empty:
        return pd.DataFrame(columns=["code", "month", "nps_members", "nps_amt", "theta_N"])
    keep = ["biz_no", "wkpl_name", "code"] + \
           [c for c in ("valid_from", "valid_to") if c in M.columns]
    x = N.merge(M[keep], on=["biz_no", "wkpl_name"], how="inner")
    x["month"] = as_ts_series(x["ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    # ★ C3: 매핑은 시간구간 테이블이다. 유효구간을 무시하고 전 기간에 적용하면
    #   "나중에야 알게 된 사업장↔법인 관계"를 과거에 소급 적용하는 미래누수가 된다.
    if "valid_from" in x.columns:
        vf = as_ts_series(x["valid_from"])
        vt = as_ts_series(x["valid_to"]) if "valid_to" in x.columns else pd.Series(pd.NaT, index=x.index)
        before = len(x)
        x = x[(vf.isna() | (x["month"] >= vf)) & (vt.isna() | (x["month"] <= vt))]
        if before - len(x):
            LOG.info(f"국민연금 매핑 유효구간(C3) 적용 — 구간 밖 {before-len(x):,}행 제외")
    agg = (x.groupby(["code", "month"], as_index=False)
            .agg(nps_members=("members", "sum"), nps_amt=("notice_amt", "sum"),
                 nps_acq=("acq_cnt", "sum"), nps_loss=("loss_cnt", "sum"),
                 n_wkpl=("wkpl_name", "nunique")))
    # ★ PIT: 공공데이터포털은 귀속월 파일을 익월 이후에 공개한다 → 보수적으로 +2개월
    agg["knowledge_date"] = agg["month"] + pd.offsets.MonthEnd(2)
    agg = pit_frame(agg, "month", "knowledge_date", source="nps")
    return downcast(agg)


# ── 피처 ────────────────────────────────────────────────────────────────────────────────────
def pack_n_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    npsp = ctx.get("nps_panel")
    NPS_COLS = ("nps_members", "nps_amt", "nps_acq", "nps_loss", "n_wkpl")
    if npsp is not None and len(npsp):
        PIT.register("nps_panel", npsp, key_cols=["code"])
        P = PIT.asof_join(P, "nps_panel", by="code", left_time="month",
                          cols=["code", "knowledge_date", *NPS_COLS], suffix="_nps")
    # ★ 결합 '이후에' 결측 컬럼을 채운다. 먼저 NaN 컬럼을 만들어두면 merge_asof 가 들어오는
    #   실제 데이터에 접미사(_nps)를 붙여 다른 이름으로 넣고, 원래의 빈 컬럼이 그대로 남는다.
    #   → 팩 전체가 조용히 결측이 되는 유형의 사고. (커버리지 0% 로만 드러난다)
    for c in NPS_COLS:
        if c not in P.columns:
            P[c] = np.nan
    g = lambda c: P.groupby("code", observed=True)[c]
    P["_year"] = P["month"].dt.year
    P["_rate"] = P["_year"].map(NPS_CONTRIB_RATE).fillna(0.09)
    P["_cap"] = P["_year"].map(NPS_INCOME_CAP).fillna(6_370_000)

    # n1: 인원 성장
    P["n1"] = g("nps_members").transform(lambda s: dlog(s, 12))

    # ── ★ 한계임금 ────────────────────────────────────────────────────────────────────────
    d_amt = g("nps_amt").diff(1)
    d_mem = g("nps_members").diff(1)
    # (c) 분모 불안정: |Δ가입자수| >= max(3, 가입자수×0.5%) 일 때만 계산. 결측을 0으로 채우지 않는다.
    thr = np.maximum(3.0, P["nps_members"] * 0.005)
    ok = d_mem.abs() >= thr
    marginal_wage = safe_div(d_amt, d_mem) / P["_rate"]
    marginal_wage = marginal_wage.where(ok)
    # (a) 7월 정기결정: 기존 인력 임금이 점프하므로 한계임금 추정이 오염된다 → 결측 처리
    jul = P["month"].dt.month == NPS_REDETERMINE_MONTH
    marginal_wage = marginal_wage.where(~jul)
    P["marginal_wage"] = marginal_wage.clip(lower=0, upper=5e7)

    est_income_prev = safe_div(g("nps_amt").shift(1) / P["_rate"], g("nps_members").shift(1))
    P["wage_premium"] = safe_div(P["marginal_wage"], est_income_prev)
    P["wage_premium"] = P["wage_premium"].where((P["wage_premium"] > 0.1) & (P["wage_premium"] < 10))
    P["n2"] = P["wage_premium"]

    # n3: 이직률 하락
    P["loss_rate"] = safe_div(P["nps_loss"], P["nps_members"])
    P["n3"] = -g("loss_rate").diff(12)

    # n4: 신규 사업장 순증 더미 (신규 적용 사업장 & 기존 사업장 인원 유지)
    P["d_wkpl"] = g("n_wkpl").diff(12)
    P["n4"] = ((P["d_wkpl"] > 0) & (P["n1"] > 0)).astype("float32")

    # n5: 캡 도달 인원 비율 변화 (절단을 역이용). 평균 기준소득이 캡에 근접할수록 절단 심함.
    est_income = safe_div(P["nps_amt"] / P["_rate"], P["nps_members"])
    P["cap_ratio"] = (est_income / P["_cap"]).clip(0, 2)
    P["n5"] = g("cap_ratio").diff(12)
    P["high_wage_flag"] = (P["cap_ratio"] > 0.85).astype("float32")   # 임금신호 신뢰도 하향 플래그

    # n6: 7월 점프폭 = 연 1회 임금상승률 (깨끗한 측정치)
    jul_jump = safe_div(est_income, est_income.groupby(P["code"], observed=True).shift(1)) - 1.0
    P["n6"] = jul_jump.where(jul)
    P["n6"] = g("n6").ffill(limit=11)

    # ── θ_N 관측커버리지 = 매핑 사업장 가입자수 / DART 종업원수(별도) ──────────────────────
    P["theta_N"] = safe_div(P["nps_members"], col(P, "employees")).clip(0, 2)
    P["theta_N"] = P["theta_N"].where(P["theta_N"] > 0)

    # ── 임계 밴드 플래그 (회귀불연속 구간) ────────────────────────────────────────────────
    band = pd.Series(False, index=P.index)
    for b in EMP_THRESHOLD_BANDS:
        band |= (P["nps_members"] - b).abs() <= b * EMP_BAND_TOL
    P["emp_band_flag"] = band.astype("float32")

    # ── V8 입력: 유효세율 급락 ────────────────────────────────────────────────────────────
    P["eff_tax_rate"] = safe_div(col(P, "tax_expense"), col(P, "pretax_income")).clip(-1, 1)
    P["d_eff_tax"] = g("eff_tax_rate").diff(12)

    # ── 트레이드오프 쌍 ────────────────────────────────────────────────────────────────────
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_N1"] = tp_product(z("n1"), z("n2"))                    # 인원↑ 인데 신규가 고임금
    P["TP_N2"] = tp_product(z("n1"), z("n3"))                    # 인원↑ 인데 이직률 안 오름
    P["TP_N3"] = tp_product(z("n4"), z("n1"))                    # 신규 사업장 + 순증
    P["TP_N4"] = tp_product(z("n1"), z("d_va_per_emp"))          # 인원↑ 인데 생산성 유지
    E = nanmean_cols(P, ["TP_N1", "TP_N2", "TP_N3", "TP_N4"])
    P["E_N"] = E * P["theta_N"].clip(0, 1).fillna(0.0)           # θ 는 배제기준이 아니라 가중치
    return P


register_pack(
    pid="N", name="국민연금 고용", tp_cols=["TP_N1", "TP_N2", "TP_N3", "TP_N4"],
    features_fn=pack_n_features, policy=PACK_N_POLICY, interp=PACK_N_INTERP,
    theta_col="theta_N",
    notes="한계임금(n2)이 핵심. 보조금 유인 채용은 구조적으로 저임금이므로 "
          "wage_premium<1 → 보조금 필터가 산식에 내장된다.")
