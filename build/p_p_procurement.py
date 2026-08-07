

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-P  조달청 낙찰  (내수 수주기업 보강)                                                 ║
# ║                                                                                          ║
# ║  매핑 문제가 구조적으로 없다 — 낙찰업체가 사업자등록번호로 직접 식별된다.                    ║
# ║  낙찰률(q2)은 원가 노이즈가 없는 순수 가격 지표라는 점에서 수출단가와 동일한 성질.           ║
# ║                                                                                          ║
# ║  ⚠ 레짐 편승 경고: 이 데이터는 방산·전력기기·원전·철도·건설에 집중되는데,                    ║
# ║    이것이 정확히 현 KOSPI 주도 섹터다. R7 레짐 분할을 필수 통과 조건으로 건다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_P_POLICY = [
    {"policy_id": "SME_COMPETE_ITEM", "name": "중소기업자간 경쟁제품 지정(3년 주기 갱신)",
     "start": "2016-01-01", "end": None, "pack": "P", "req_type": "기업규모", "req_value": "중소기업"},
    {"policy_id": "REGION_LIMIT_BID", "name": "지역제한 입찰 제도", "start": "2016-01-01",
     "end": None, "pack": "P", "req_type": "지역", "req_value": "본점 소재지"},
    {"policy_id": "DEFENSE_BUDGET_EXPAND", "name": "국방예산 증액 국면", "start": "2022-01-01",
     "end": None, "pack": "P", "req_type": "업종", "req_value": "방산"},
    {"policy_id": "NEWDEAL_2020", "name": "한국판 뉴딜(SOC·디지털)", "start": "2020-07-14",
     "end": "2022-12-31", "pack": "P", "req_type": "없음", "req_value": ""},
    {"policy_id": "NUCLEAR_POLICY_SHIFT", "name": "원전 정책 전환(탈원전→원전확대)",
     "start": "2022-05-10", "end": None, "pack": "P", "req_type": "업종", "req_value": "원전"},
]

PACK_P_INTERP = [
    ("TP_Q1", "가격 안 깎고 수주 확대", "저가 수주로 물량만 늘림"),
    ("TP_Q2", "발주처 다변화인데 마진 유지", "특정 발주처 의존 심화 또는 저가 확장"),
]

G2B_API = "https://apis.data.go.kr/1230000/ScsbidInfoService/"


def fetch_procurement(months: pd.DatetimeIndex) -> pd.DataFrame:
    """나라장터 낙찰정보. 사업자등록번호와 예정가격이 있어야 q2(낙찰률)가 산다."""
    key = _datagokr_key()
    cached = VAULT.get_table("g2b_awards_monthly", scope="shared")
    have = set(cached["ym"].astype(str)) if cached is not None and len(cached) else set()
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 조달 낙찰 {len(cached):,}행 재사용")
    if not key:
        if not have:
            LOG.warn("DATA_GO_KR_KEY 미입력 — PACK-P 를 구동할 수 없습니다.")
            return pd.DataFrame()
        return cached
    todo = [m for m in months if m.strftime("%Y%m") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    def _one(m):
        rows, page = [], 1
        while page <= 200:
            limiter("datagokr").wait()
            js = http_json(G2B_API + "getScsbidListSttusThng", source="datagokr", tries=2,
                           params={"serviceKey": key, "numOfRows": 999, "pageNo": page,
                                   "inqryDiv": 1, "type": "json",
                                   "inqryBgnDt": m.strftime("%Y%m01") + "0000",
                                   "inqryEndDt": (m + pd.offsets.MonthEnd(0)).strftime("%Y%m%d") + "2359"})
            if not js:
                break
            body = (js.get("response", {}).get("body") if isinstance(js, dict) else None) or {}
            items = body.get("items") or []
            it = items.get("item") if isinstance(items, dict) else items
            if isinstance(it, dict):
                it = [it]
            if not it:
                break
            for r in it:
                rows.append({
                    "ym": m.strftime("%Y%m"),
                    "biz_no": re.sub(r"\D", "", str(r.get("bizno") or r.get("bidwinnrBizno") or "")),
                    "corp_nm": str(r.get("bidwinnrNm") or r.get("cmpnyNm") or ""),
                    "award_amt": pd.to_numeric(r.get("sucsfbidAmt"), errors="coerce"),
                    "plan_price": pd.to_numeric(r.get("presmptPrce"), errors="coerce"),
                    "rate": pd.to_numeric(r.get("sucsfbidRate"), errors="coerce"),
                    "org": str(r.get("dminsttNm") or ""),
                    "item_cls": str(r.get("prdctClsfcNo") or ""),
                })
            page += 1
        return rows

    new = []
    if todo:
        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="조달청 낙찰")
        for r in res:
            if r:
                new.extend(r)
    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        frames.append(pd.DataFrame(new))
    if not frames:
        return pd.DataFrame()
    G = pd.concat(frames, ignore_index=True)
    if new:
        VAULT.put_table("g2b_awards_monthly", G, scope="shared", domain="procurement",
                        source="나라장터 낙찰정보")
    has_plan = float(G["plan_price"].notna().mean()) if "plan_price" in G.columns else 0.0
    LOG.ok(f"조달 낙찰 {len(G):,}건 (예정가격 보유율 {100*has_plan:.1f}%)")
    if has_plan < 0.2:
        LOG.warn("예정가격 보유율이 20% 미만입니다. q2(낙찰률)가 사실상 죽고 팩 가치가 급감합니다 "
                 "(§6.4 착수 전 확인 항목). TP_Q1/TP_Q2 결과 해석 시 반드시 감안하세요.")
    return G


def pack_p_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    G, sec = ctx.get("procurement"), ctx.get("sec")
    for c in ("q1", "q2", "q3", "q4"):
        P[c] = np.nan
    if G is None or len(G) == 0:
        P["TP_Q1"] = np.nan; P["TP_Q2"] = np.nan; P["E_P"] = np.nan
        disable_pack("P", "조달청 낙찰 데이터 부재")
        return P
    # 사업자번호 → 종목코드: DART 회사개황이 없으면 상호 유사도로 연결
    n2c = {}
    if sec is not None and len(sec):
        for _, r in sec.iterrows():
            n = norm_corp_name(r.get("name"))
            if n and n not in n2c:
                n2c[n] = r.get("code")
    G = G.copy()
    G["code"] = G["corp_nm"].map(lambda s: n2c.get(norm_corp_name(s)))
    G = G.dropna(subset=["code"])
    if G.empty:
        P["TP_Q1"] = np.nan; P["TP_Q2"] = np.nan; P["E_P"] = np.nan
        disable_pack("P", "조달 낙찰업체를 상장사와 연결하지 못함")
        return P
    G["month"] = as_ts_series(G["ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    G["win_rate"] = G["rate"].where(G["rate"].between(50, 120),
                                    safe_div(G["award_amt"], G["plan_price"]) * 100.0)
    T = (G.groupby(["code", "month"], as_index=False)
          .agg(award_amt=("award_amt", "sum"), win_rate=("win_rate", "mean"),
               n_org=("org", "nunique"), n_award=("award_amt", "size")))
    org_sh = (G.assign(one=1).groupby(["code", "month", "org"], as_index=False)["award_amt"].sum())
    org_sh["sh"] = org_sh["award_amt"] / org_sh.groupby(["code", "month"])["award_amt"].transform("sum")
    hhi = org_sh.assign(sh2=lambda d: d["sh"] ** 2).groupby(["code", "month"], as_index=False)["sh2"].sum()
    T = T.merge(hhi.rename(columns={"sh2": "hhi_org"}), on=["code", "month"], how="left")
    # PIT: 개찰일/공고일 중 늦은 것 → 월말 + 공개 지연 15일
    T["knowledge_date"] = T["month"] + pd.Timedelta(days=15)
    T = pit_frame(T, "month", "knowledge_date", source="procurement")
    PIT.register("procure_panel", T, key_cols=["code"])
    P = PIT.asof_join(P, "procure_panel", by="code", left_time="month",
                      cols=["code", "knowledge_date", "award_amt", "win_rate", "hhi_org", "n_award"],
                      suffix="_g2b")
    P = P.sort_values(["code", "month"])
    g = lambda c: P.groupby("code", observed=True)[c]
    P["q1"] = g("award_amt").transform(lambda s: dlog(s.rolling(12, min_periods=6).sum(), 12))
    P["q2"] = g("win_rate").diff(12)
    P["q3"] = -g("hhi_org").diff(12)
    z = lambda c: xsec_z(P[c], P["cell"]) if c in P.columns else pd.Series(np.nan, index=P.index)
    P["TP_Q1"] = tp_product(z("q1"), z("q2"))
    P["TP_Q2"] = tp_product(z("q3"), z("q2"))
    P["E_P"] = nanmean_cols(P, ["TP_Q1", "TP_Q2"])
    return P


register_pack(
    pid="P", name="조달청 낙찰", tp_cols=["TP_Q1", "TP_Q2"],
    features_fn=pack_p_features, policy=PACK_P_POLICY, interp=PACK_P_INTERP,
    notes="낙찰률은 원가 노이즈가 없는 순수 가격 지표 — 수출단가와 동일한 성질. "
          "단 방산·원전 레짐 편승 위험이 크므로 R7 필수.")
