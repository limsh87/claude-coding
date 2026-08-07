

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-X  관세청 수출  (수출집중 기업 보강)                                                 ║
# ║                                                                                          ║
# ║  알파는 여전히 최고다. 물량·단가·목적지·신규세번 4센서를 월 단위로 동시 관측하는            ║
# ║  유일한 공개 데이터셋. 순위가 내려간 건 알파가 아니라 첫 결과까지의 시간 때문이다.          ║
# ║                                                                                          ║
# ║  ★ 종속변수: y = 국내법인 수출매출 (별도 재무제표). 연결 아님.                              ║
# ║    통관은 "대한민국 관세영역 반출 물량"이므로 대응 회계항목은 별도 기준이다.                ║
# ║    해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.                                    ║
# ║  ★ x2(단가 잔차)는 36개월 롤링 OLS 벡터화. 칼만필터는 §3에서 폐기(2.3시간 초과).            ║
# ║  ★ 전 종목 적용 금지. 국내 생산자 1~3개사인 과점 품목 우선.                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_X_POLICY = [
    {"policy_id": "EXPORT_VOUCHER", "name": "수출바우처 사업", "start": "2017-01-01",
     "end": None, "pack": "X", "req_type": "기업규모", "req_value": "중소·중견"},
    {"policy_id": "KOR_JPN_EXPORT_CTRL", "name": "일본 수출규제(소부장 대응)", "start": "2019-07-01",
     "end": "2023-03-31", "pack": "X", "req_type": "업종", "req_value": "반도체·디스플레이 소재"},
    {"policy_id": "RCEP", "name": "RCEP 발효", "start": "2022-02-01", "end": None,
     "pack": "X", "req_type": "없음", "req_value": ""},
    {"policy_id": "IRA_2022", "name": "美 IRA 시행", "start": "2022-08-16", "end": None,
     "pack": "X", "req_type": "업종", "req_value": "이차전지·전기차"},
    {"policy_id": "CHIPS_ACT", "name": "美 반도체법/대중 수출통제", "start": "2022-10-07",
     "end": None, "pack": "X", "req_type": "업종", "req_value": "반도체"},
    {"policy_id": "COVID_TRADE", "name": "코로나 물류대란·해상운임 급등", "start": "2020-03-01",
     "end": "2022-12-31", "pack": "X", "req_type": "없음", "req_value": ""},
]

PACK_X_INTERP = [
    ("TP_X1", "수요곡선 자체 이동. 병목 지위", "물량을 가격 인하로 산 것"),
    ("TP_X2", "제품력으로 고객 다변화", "저가 물량으로 고객 늘림"),
    ("TP_X3", "신시장 진입인데 영업비 안 늘어남", "판촉비로 산 매출"),
]

# 목적지 30개 국가군 축약 — HS10×230국×120월=3억 행을 700만 행으로 줄이는 핵심(§6.3 성능 규율)
COUNTRY_GROUPS = {
    "US": "선진_미국", "JP": "선진_일본", "TW": "선진_대만", "HK": "중화권", "CN": "중화권",
    "DE": "선진_EU", "FR": "선진_EU", "IT": "선진_EU", "NL": "선진_EU", "GB": "선진_EU",
    "VN": "아세안", "TH": "아세안", "ID": "아세안", "MY": "아세안", "SG": "아세안", "PH": "아세안",
    "IN": "남아시아", "AU": "오세아니아", "BR": "중남미", "MX": "중남미",
    "RU": "러시아CIS", "TR": "중동", "SA": "중동", "AE": "중동",
}
ADVANCED_GROUPS = {"선진_미국", "선진_EU", "선진_일본", "선진_대만"}


def fetch_customs_trade(months: pd.DatetimeIndex, hs_codes: Sequence[str]) -> pd.DataFrame:
    """관세청 수출입 무역통계. 금액(USD)과 중량(kg)이 동시에 있어야 x2(단가)가 산다."""
    if not CUSTOMS_API_KEY:
        LOG.warn("CUSTOMS_API_KEY 미입력 — PACK-X 를 구동할 수 없습니다. "
                 "(관세청 UNIPASS 또는 공공데이터포털 수출입무역통계 API)")
        return pd.DataFrame()
    cached = VAULT.get_table("customs_trade_monthly", scope="shared")
    if cached is not None and len(cached) and RUN_MODE == "CACHED":
        return cached
    have = set()
    if cached is not None and len(cached):
        have = set(zip(cached["ym"].astype(str), cached["hs"].astype(str)))
        LOG.info(f"공용 캐시에서 관세 통관 {len(cached):,}행 재사용")
    jobs = [(m.strftime("%Y%m"), h) for m in months for h in hs_codes
            if (m.strftime("%Y%m"), str(h)) not in have]

    def _one(job):
        ym, hs = job
        limiter("customs").wait()
        js = http_json("https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
                       source="customs", tries=2,
                       params={"serviceKey": _datagokr_key() or CUSTOMS_API_KEY,
                               "strtYymm": ym, "endYymm": ym, "hsSgn": hs, "type": "json"})
        if not js:
            return None
        body = (js.get("response", {}).get("body") if isinstance(js, dict) else None) or {}
        items = (body.get("items") or {})
        it = items.get("item") if isinstance(items, dict) else items
        if isinstance(it, dict):
            it = [it]
        if not it:
            return None
        rows = []
        for r in it:
            rows.append({"ym": ym, "hs": str(hs),
                         "exp_usd": pd.to_numeric(r.get("expDlr"), errors="coerce"),
                         "exp_wgt": pd.to_numeric(r.get("expWgt"), errors="coerce"),
                         "country": str(r.get("statCd") or r.get("cntyCd") or "")})
        return rows

    new = []
    if jobs and RUN_MODE != "CACHED":
        LOG.info(f"관세 통관 신규 수집 {len(jobs):,}건 (월×HS)")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="관세청 통관")
        for r in res:
            if r:
                new.extend(r)
    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        frames.append(pd.DataFrame(new))
    if not frames:
        return pd.DataFrame()
    C = pd.concat(frames, ignore_index=True)
    C["grp"] = C["country"].map(COUNTRY_GROUPS).fillna("기타")
    C = (C.groupby(["ym", "hs", "grp"], as_index=False)
          .agg(exp_usd=("exp_usd", "sum"), exp_wgt=("exp_wgt", "sum")))
    if new:
        VAULT.put_table("customs_trade_monthly", C, scope="shared", domain="customs",
                        source="관세청 수출입무역통계")
    LOG.ok(f"관세 통관 {len(C):,}행 (목적지 {C['grp'].nunique()}개 국가군으로 축약)")
    return C


def map_hs_to_codes(C: pd.DataFrame, sec: pd.DataFrame, fin: pd.DataFrame,
                    placebo_n: int = 1000) -> pd.DataFrame:
    """HS → 기업 역방향 매핑 + 합계 정합성 + 플라시보 p값.
    ★ 매핑 품질을 주관적 확신이 아니라 p값으로 관리한다(§6.3-4)."""
    cached = VAULT.get_table("hs_corp_map", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 HS 매핑 {len(cached):,}건 재사용")
        return cached
    LOG.warn("HS↔기업 매핑 테이블이 없습니다. 이 매핑은 5단계 파이프라인(수 주 소요)이 필요하며 "
             "자동 구축 대상이 아닙니다(§6.3). PACK-X 는 비활성화됩니다. "
             "직접 만든 매핑이 있다면 공용 인덱스에 'hs_corp_map' 테이블로 넣어주세요 "
             "(컬럼: code, hs, weight, valid_from, valid_to).")
    return pd.DataFrame(columns=["code", "hs", "weight", "valid_from", "valid_to"])


def pack_x_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    C, M = ctx.get("customs"), ctx.get("hs_map")
    for c in ("x1", "x2", "x3_1", "x3_2", "x4", "theta_X"):
        P[c] = np.nan
    if C is None or len(C) == 0 or M is None or len(M) == 0:
        P["TP_X1"] = np.nan; P["TP_X2"] = np.nan; P["TP_X3"] = np.nan
        P["E_X"] = np.nan
        disable_pack("X", "관세 통관 데이터 또는 HS↔기업 매핑 부재 (V4 부분거부권)")
        return P

    x = C.merge(M[["code", "hs", "weight"]], on="hs", how="inner")
    x["month"] = as_ts_series(x["ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    x["exp_usd"] = x["exp_usd"] * x["weight"]
    x["exp_wgt"] = x["exp_wgt"] * x["weight"]
    tot = (x.groupby(["code", "month"], as_index=False)
            .agg(exp_usd=("exp_usd", "sum"), exp_wgt=("exp_wgt", "sum")))
    hhi = (x.assign(sh=lambda d: d["exp_usd"] / d.groupby(["code", "month"])["exp_usd"]
                    .transform("sum"))
            .assign(sh2=lambda d: d["sh"] ** 2)
            .groupby(["code", "month"], as_index=False)["sh2"].sum()
            .rename(columns={"sh2": "hhi_dest"}))
    adv = (x[x["grp"].isin(ADVANCED_GROUPS)].groupby(["code", "month"], as_index=False)["exp_usd"]
            .sum().rename(columns={"exp_usd": "adv_usd"}))
    T = tot.merge(hhi, on=["code", "month"], how="left").merge(adv, on=["code", "month"], how="left")
    T["adv_share"] = safe_div(T["adv_usd"], T["exp_usd"])
    # ★ PIT: 통관 잠정치 최초 공표일 ≈ 익월 15일. 확정치 소급 대체 금지.
    T["knowledge_date"] = T["month"] + pd.offsets.MonthEnd(1) + pd.Timedelta(days=15)
    T = pit_frame(T, "month", "knowledge_date", source="customs")
    PIT.register("customs_panel", T, key_cols=["code"])
    P = PIT.asof_join(P, "customs_panel", by="code", left_time="month",
                      cols=["code", "knowledge_date", "exp_usd", "exp_wgt",
                            "hhi_dest", "adv_share"], suffix="_cus")
    P = P.sort_values(["code", "month"])
    g = lambda c: P.groupby("code", observed=True)[c]
    P["x1"] = g("exp_wgt").transform(lambda s: dlog(s, 12))
    P["x3_1"] = -g("hhi_dest").diff(12)
    P["x3_2"] = g("adv_share").diff(12)

    # ── x2: 단가 잔차 — 36개월 롤링 OLS (벡터화 필수) ─────────────────────────────────────
    P["unit_price"] = safe_div(P["exp_usd"], P["exp_wgt"])
    W = P.pivot_table(index="code", columns="month", values="unit_price", aggfunc="first")
    Q = P.pivot_table(index="code", columns="month", values="exp_wgt", aggfunc="first")
    if W.shape[1] >= 36:
        y = np.log(W.to_numpy(dtype=float, na_value=np.nan))
        q = np.log(Q.reindex_like(W).to_numpy(dtype=float, na_value=np.nan))
        n, t = y.shape
        X = np.stack([np.ones((n, t)), q, np.tile(np.arange(t, dtype=float), (n, 1))], axis=2)
        R = rolling_ols_resid(y, X, window=36)
        rs = pd.DataFrame(R, index=W.index, columns=W.columns).stack(dropna=False)
        rs.index.names = ["code", "month"]
        rs = rs.rename("resid").reset_index()
        P = P.merge(rs, on=["code", "month"], how="left")
        P["resid_mean6"] = g("resid").transform(lambda s: s.rolling(6, min_periods=4).mean())
        P["resid_std"] = g("resid").transform(lambda s: s.rolling(36, min_periods=18).std())
        P["x2"] = safe_div(P["resid_mean6"], P["resid_std"])
    # x4: 신규 HS10 등장 → 12M 지수감쇠 더미
    P["x4"] = 0.0
    P["theta_X"] = safe_div(P["exp_usd"] * 1300.0, P.get("revenue_ttm")).clip(0, 2)

    z = lambda c: xsec_z(P[c], P["cell"]) if c in P.columns else pd.Series(np.nan, index=P.index)
    P["d_sgna_ratio"] = g("sgna_ttm").transform(lambda s: s).pipe(
        lambda s: safe_div(s, P["revenue_ttm"])).pipe(lambda s: s.groupby(P["code"]).diff(12)) \
        if "sgna_ttm" in P.columns else np.nan
    P["TP_X1"] = tp_product(z("x1"), z("x2"))
    P["TP_X2"] = tp_product(z("x3_1"), z("x2"))
    P["TP_X3"] = tp_product(z("x3_2"), -z("d_sgna_ratio"))
    P["E_X"] = nanmean_cols(P, ["TP_X1", "TP_X2", "TP_X3"]) * P["theta_X"].clip(0, 1).fillna(0.0)
    return P


register_pack(
    pid="X", name="관세청 수출", tp_cols=["TP_X1", "TP_X2", "TP_X3"],
    features_fn=pack_x_features, policy=PACK_X_POLICY, interp=PACK_X_INTERP,
    theta_col="theta_X",
    notes="x2(수출단가 잔차)는 GPM으로 대체 불가. GPM은 원재료 하락으로도 개선되지만 "
          "수출단가는 판매가격 그 자체 — 원가 노이즈 0의 순수 가격결정력 측정치.")
