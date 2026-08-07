

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-C  자본배분 체제 전환  (★ Phase 1 — 가장 싼 검정)                                    ║
# ║                                                                                          ║
# ║  TCD 영업센서가 구조적으로 못 보는 전환 유형: 제국 건설을 멈추고 자본을 돌려주기 시작.      ║
# ║  데이터가 전부 DART 정형 공시라 콜드빌드가 최단이다 → R2/R3 를 가장 빨리 돌릴 수 있다.      ║
# ║                                                                                          ║
# ║  ⚠ 레짐 경고: 밸류업 프로그램은 2024년 이후다. 10년 중 최근 2년만 현 레짐이다.              ║
# ║    2024년 이전 구간에서 알파가 0이면 이건 구조적 알파가 아니라 정책 베팅이다.               ║
# ║    R7/R10 에서 이 판정을 반드시 리포트에 명시한다.                                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_C_POLICY = [
    {"policy_id": "VALUEUP_2024", "name": "기업 밸류업 프로그램", "start": "2024-02-26",
     "end": None, "pack": "C", "req_type": "없음", "req_value": "",
     "url": "https://www.fsc.go.kr"},
    {"policy_id": "VALUEUP_INDEX_2024", "name": "코리아 밸류업 지수 발표", "start": "2024-09-24",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
    {"policy_id": "DIV_SEPARATE_TAX", "name": "배당소득 분리과세 논의/시행", "start": "2025-01-01",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
    {"policy_id": "TREASURY_CANCEL_2025", "name": "자사주 소각 관련 상법/제도 변경", "start": "2025-01-01",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
    {"policy_id": "SHAREHOLDER_RETURN_TAXCREDIT", "name": "주주환원 확대 기업 세액공제", "start": "2025-01-01",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
]

PACK_C_INTERP = [
    ("TP_P1", "진짜 잉여현금 창출력 획득 — 환원과 투자를 동시에 늘림", "성장 포기하고 환원만 늘림"),
    ("TP_P2", "자사주 진정성 있음 — 취득이 소각까지 감", "취득만 하고 물량 재활용(교환사채·경영권방어) 가능성"),
    ("TP_P3", "무차입 환원. 현금 체질로 전환", "차입해서 환원 — 지속 불가"),
]


def pack_c_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: P.groupby("code", observed=True)[c]

    # ── 센서 ──────────────────────────────────────────────────────────────────────────────
    # p1: 총주주환원 / 영업현금흐름.  현금흐름표에서 직접 읽으므로 결정공시 파싱이 불필요하다.
    payout = (P.get("dividend_paid_ttm").abs().fillna(0) +
              P.get("treasury_buy_ttm").abs().fillna(0))
    P["payout_ratio"] = safe_div(payout, P.get("cfo_ttm"))
    P["p1"] = g("payout_ratio").diff(12)

    # p2: (CapEx + R&D) / 매출
    invest = P.get("capex_ttm").abs().fillna(0) + P.get("rnd_ttm").abs().fillna(0)
    P["invest_ratio"] = safe_div(invest, P.get("revenue_ttm"))
    P["p2"] = g("invest_ratio").diff(12)

    # p3: 자사주 취득공시 대비 12M 내 실제 소각 실행률
    #     한국 특수성 — 취득 공시는 흔하지만 소각까지 가는 비율이 낮다. 이 갭을 추적하는
    #     참여자가 사실상 없다는 것이 이 센서의 알파 원천이다.
    P["treasury_acq_n"] = 0.0
    P["treasury_canc_n"] = 0.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis):
        d = dis[dis["event"].isin(["treasury_acq", "treasury_canc"])].copy()
        if len(d) and "corp_code" in d.columns:
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            cnt = (d.groupby(["corp_code", "month", "event"]).size()
                     .unstack("event").reset_index())
            for c in ("treasury_acq", "treasury_canc"):
                if c not in cnt.columns:
                    cnt[c] = 0.0
            cnt["corp_code"] = cnt["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(cnt[["corp_code", "month", "treasury_acq", "treasury_canc"]],
                        on=["corp_code", "month"], how="left", suffixes=("", "_x"))
            P["treasury_acq"] = P["treasury_acq"].fillna(0.0)
            P["treasury_canc"] = P["treasury_canc"].fillna(0.0)
            P = P.sort_values(["code", "month"])
            P["treasury_acq_n"] = (P.groupby("code", observed=True)["treasury_acq"]
                                    .transform(lambda s: s.rolling(12, min_periods=1).sum()))
            P["treasury_canc_n"] = (P.groupby("code", observed=True)["treasury_canc"]
                                     .transform(lambda s: s.rolling(12, min_periods=1).sum()))
    P["p3"] = safe_div(P["treasury_canc_n"], P["treasury_acq_n"]).clip(0, 2)
    P["acq_size"] = safe_div(P.get("treasury_buy_ttm").abs(), P.get("assets"))

    # p4: 부채비율 변화 (axis_C 에서 이미 계산)
    P["p4"] = P.get("d_debt_ratio")

    # ── 트레이드오프 쌍 ────────────────────────────────────────────────────────────────────
    z = lambda c: xsec_z(P[c], P["cell"]) if c in P.columns else pd.Series(np.nan, index=P.index)
    P["TP_P1"] = tp_product(z("p1"), z("p2"))          # ★ 이 팩의 전부: 환원↑ 인데 투자도↑
    P["TP_P2"] = tp_product(z("acq_size"), z("p3"))    # 취득 규모 큰데 소각까지 실행
    P["TP_P3"] = tp_product(z("p1"), -z("p4"))         # 환원↑ 인데 차입 안 늘림
    P["E_C_pack"] = nanmean_cols(P, ["TP_P1", "TP_P2", "TP_P3"])
    P["E_C"] = P["E_C_pack"]                            # 레지스트리 규약: E_<pid>
    return P


register_pack(
    pid="C", name="자본배분 체제 전환", tp_cols=["TP_P1", "TP_P2", "TP_P3"],
    features_fn=pack_c_features, policy=PACK_C_POLICY, interp=PACK_C_INTERP,
    notes="TP_P1(환원↑ & 투자↑)이 이 팩의 전부. 시장은 '환원 늘렸으니 성장 끝'이라는 "
          "기본값 해석 때문에 늦게 반영한다.")
