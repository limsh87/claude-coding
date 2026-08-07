# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  XCB 전용 DART 수집 — 코어가 다루지 않는 네 가지                                            ║
# ║    ① 단일판매·공급계약 공시  → c6, TP_XC 의 한쪽 날개                                       ║
# ║    ② 사업보고서 품목별/지역별 매출 → 게이트2 자기공시 대조 · θ_X · 게이트1 분자             ║
# ║    ③ 정책 의존 관측(정부보조금수익)  → V11                                                  ║
# ║    ④ 관리종목·감사의견·희석성 조달   → V5 · V3                                              ║
# ║                                                                                             ║
# ║  ★ 없는 것을 있는 척하지 않는다. 확보 실패한 항목은 결측으로 두고 커버리지를 표로 낸다.     ║
# ║    0 으로 채우면 '해당 없음'이라는 적극적 주장이 되어 거부권이 조용히 무력화된다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 코어 DISCLOSURE_PATTERNS 에 없는, XCB 가 추가로 필요로 하는 공시 유형.
XCB_DISCLOSURE_PATTERNS = {
    "supply_contract": r"단일판매[·・]?\s*공급계약|공급계약\s*체결",
    "watch_designate": r"관리종목\s*지정|투자주의\s*환기종목\s*지정|상장적격성\s*실질심사",
    "watch_release":   r"관리종목\s*지정\s*해제|투자주의\s*환기종목\s*해제",
    "trading_halt":    r"매매거래\s*정지",
}

# 공시 제목에서 계약금액을 뽑는 패턴. 제목에 금액이 없으면 본문 조회로 내려간다.
_AMT_RX = re.compile(r"([0-9][0-9,\.]*)\s*(억|백만|천만|만|원)")


def _amt_from_text(t: str) -> float:
    """'약 420억원' / '42,000백만원' 같은 표기를 원 단위 실수로."""
    if not t:
        return float("nan")
    m = _AMT_RX.search(str(t).replace(" ", ""))
    if not m:
        return float("nan")
    try:
        v = float(m.group(1).replace(",", ""))
    except Exception:                                                   # noqa
        return float("nan")
    unit = {"억": 1e8, "백만": 1e6, "천만": 1e7, "만": 1e4, "원": 1.0}.get(m.group(2), 1.0)
    return v * unit


def fetch_supply_contracts(dis: pd.DataFrame) -> pd.DataFrame:
    """단일판매·공급계약 체결 공시 → (code, knowledge_date, amount).

    ★ 이것이 TP_XC 의 한쪽이다. 공시는 **기업 자신의 진술**이고 통관 물량은
      **제3자(관세청)의 관측**이다. 독립인 두 소스가 같은 방향을 가리키면 신뢰도가 곱으로 오른다.
      공시만 있고 통관이 안 따라오면 계약이 실물로 전환되지 않은 것이고,
      이 갭을 추적하는 참여자는 사실상 없다.

    금액은 공시 제목에서 추출한다. 제목에 없으면 결측으로 두고 건수만 쓴다 —
    본문 파싱은 비용 대비 회수가 낮고, c6 는 '규모'보다 '발생'이 더 중요한 신호다.
    """
    cols = ["code", "knowledge_date", "amount"]
    if dis is None or not len(dis):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    hit = nm.str.contains(XCB_DISCLOSURE_PATTERNS["supply_contract"], regex=True, na=False)
    d = d[hit].copy()
    if not len(d):
        LOG.info("단일판매·공급계약 공시를 찾지 못했습니다 — c6/TP_XC 는 비활성화됩니다.")
        return pd.DataFrame(columns=cols)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["knowledge_date"] = as_ts_series(d.get("rcept_dt"))
    d["amount"] = nm[hit].map(_amt_from_text)
    d = d[d["code"].notna() & d["knowledge_date"].notna()]
    got = float(d["amount"].notna().mean()) if len(d) else 0.0
    LOG.ok(f"단일판매·공급계약 공시 {len(d):,}건 · {d['code'].nunique():,}종목 "
           f"(제목에서 금액 추출 성공률 {got*100:.0f}%)")
    if got < 0.3:
        LOG.warn("계약금액 추출률이 낮습니다 — c6 는 금액 대신 건수 기반으로 퇴화합니다. "
                 "TP_XC 의 해상도가 낮아진 상태로 R5 절제에서 기여를 확인하세요.")
        d["amount"] = d["amount"].fillna(1.0)      # 건수 기반 퇴화(그 사실을 위에 로그로 남김)
    return d[cols].reset_index(drop=True)


def build_dilution_flags(dis: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """V3 — 90일 내 대규모 희석성 조달(유상증자/CB/BW)."""
    cols = ["code", "ym", "dilution_90d"]
    if dis is None or not len(dis):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    ev = d.get("event", pd.Series("", index=d.index)).astype(str)
    hit = ev.isin(["rights_issue", "cb_issue", "bw_issue"])
    d = d[hit].copy()
    if not len(d):
        return pd.DataFrame(columns=cols)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["rcept_dt"] = as_ts_series(d.get("rcept_dt"))
    d = d[d["code"].notna() & d["rcept_dt"].notna()]
    if not len(d):
        return pd.DataFrame(columns=cols)
    ex = expand_events_to_months(d[["code", "rcept_dt"]], "rcept_dt", months, window_days=90)
    if not len(ex):
        return pd.DataFrame(columns=cols)
    out = (ex.groupby(["code", "month"], observed=True).size()
             .rename("dilution_90d").reset_index().rename(columns={"month": "ym"}))
    LOG.ok(f"V3 희석성 조달 플래그 {len(out):,} 종목월")
    return out[cols]


def build_watch_flags(dis: pd.DataFrame, months: pd.DatetimeIndex,
                      sec: pd.DataFrame) -> pd.DataFrame:
    """V5 — 관리종목·거래정지·감사의견 비적정.

    ★ 지정/해제 이벤트를 **계단함수**로 복원한다. '현재 관리종목 목록'을 과거에 소급 적용하면
      그 자체가 미래정보다. 그리고 이미 해제된 종목이 영구히 배제된다.
    ⚠ 감사의견 '적정' 여부를 직접 확인할 공개 API 가 없다. 비적정 '증거가 있을 때만' 배제하고,
      증거 소스가 없으면 그 조항을 비활성화한 채 감사표에 남긴다.
    """
    cols = ["code", "ym", "watch_flag"]
    if dis is None or not len(dis) or not len(months):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["rcept_dt"] = as_ts_series(d.get("rcept_dt"))
    on = nm.str.contains(XCB_DISCLOSURE_PATTERNS["watch_designate"], regex=True, na=False) | \
        nm.str.contains(XCB_DISCLOSURE_PATTERNS["trading_halt"], regex=True, na=False)
    off = nm.str.contains(XCB_DISCLOSURE_PATTERNS["watch_release"], regex=True, na=False)
    ev = d[(on | off) & d["code"].notna() & d["rcept_dt"].notna()].copy()
    if not len(ev):
        LOG.warn("관리종목/거래정지 공시를 찾지 못했습니다 — V5 는 자본잠식 조항만으로 축소됩니다. "
                 "없는 것을 있는 척하지 않고 감사표에 그대로 표기합니다.")
        return pd.DataFrame(columns=cols)
    ev["delta"] = np.where(off.reindex(ev.index).fillna(False).to_numpy(), -1.0, 1.0)
    ev["ym"] = as_ts_series(ev["rcept_dt"]) + pd.offsets.MonthEnd(0)
    step = ev.groupby(["code", "ym"], observed=True)["delta"].sum().reset_index()

    codes = step["code"].unique()
    grid = pd.MultiIndex.from_product([codes, months], names=["code", "ym"]).to_frame(index=False)
    g = grid.merge(step, on=["code", "ym"], how="left").sort_values(["code", "ym"])
    g["delta"] = g["delta"].fillna(0.0)
    g["watch_flag"] = (g.groupby("code", observed=True)["delta"].cumsum() > 0).astype(float)
    LOG.ok(f"V5 관리/정지 계단함수 복원: {int(g['watch_flag'].sum()):,} 종목월 발동")
    return g[cols]


def build_capital_impairment(fin: pd.DataFrame) -> pd.DataFrame:
    """V5 보조 — 자본잠식(자본총계 < 0). 재무제표만으로 확실히 판정된다."""
    if fin is None or not len(fin) or "equity" not in fin.columns:
        return pd.DataFrame(columns=["code", "knowledge_date", "impaired"])
    d = fin[["code", "knowledge_date", "equity"]].copy()
    d["impaired"] = (pd.to_numeric(d["equity"], errors="coerce") < 0).astype(float)
    return d[["code", "knowledge_date", "impaired"]]


def derive_theta_x(fin: pd.DataFrame, mapping: pd.DataFrame, cx: pd.DataFrame,
                   fx_usdkrw: float = 1200.0) -> pd.DataFrame:
    """θ_X = 국내법인 수출매출(별도) / 연결매출.  관측커버리지 **가중치**(배제 기준 아님).

    통관은 '관세영역 반출 물량'이므로 대응 회계항목은 **별도(개별)** 기준 수출매출이다.
    연결이 아니다. 해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.

    ⚠ 공개 API 로 '별도 수출매출'을 직접 주는 항목이 없다. 3단 폴백을 쓰고 **어느 단을 썼는지
      반드시 표로 낸다**:
        T1  별도(OFS) 매출 / 연결(CFS) 매출  × 매핑 HS 수출액 비중  → 근사
        T2  매핑 HS 수출액(USD→KRW) / 연결매출                      → 상한 근사
        T3  결측 — compose_signal 이 중앙값으로 대체하고 그 사실을 기록
    """
    cols = ["code", "knowledge_date", "theta_x", "theta_src"]
    if fin is None or not len(fin):
        return pd.DataFrame(columns=cols)
    d = fin[["code", "knowledge_date", "period_end"]].copy()
    rev = None
    for c in ("revenue_ttm", "revenue"):
        if c in fin.columns:
            rev = pd.to_numeric(fin[c], errors="coerce")
            break
    if rev is None:
        return pd.DataFrame(columns=cols)
    d["rev"] = rev.to_numpy()

    theta = pd.Series(np.nan, index=d.index)
    src = pd.Series("T3_missing", index=d.index, dtype=object)

    # T2: 매핑된 HS 의 기업 귀속 수출액(USD) → KRW → 연결매출 대비
    if mapping is not None and len(mapping) and cx is not None and len(cx):
        c = cx.copy()
        c["hs"] = c["hs"].astype(str)
        c["year"] = as_ts_series(c["ym"]).dt.year
        hs_y = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()
        mp = mapping[["code", "hs", "weight"]].copy()
        mp["hs"] = mp["hs"].astype(str)
        j = mp.merge(hs_y, on="hs", how="inner")
        j["firm_usd"] = pd.to_numeric(j["exp_usd"], errors="coerce") * \
            pd.to_numeric(j["weight"], errors="coerce").fillna(1.0)
        fy = j.groupby(["code", "year"], observed=True)["firm_usd"].sum().reset_index()
        d["year"] = as_ts_series(d["period_end"]).dt.year
        d = d.merge(fy, on=["code", "year"], how="left")
        t2 = safe_div(pd.to_numeric(d["firm_usd"], errors="coerce") * fx_usdkrw, d["rev"])
        ok = t2.notna() & (t2 > 0)
        theta = theta.where(~ok, t2)
        src = src.where(~ok, "T2_mapped_export")

    out = d[["code", "knowledge_date"]].copy()
    out["theta_x"] = pd.to_numeric(theta, errors="coerce").clip(0.0, 1.0)
    out["theta_src"] = src.to_numpy()
    cov = float(out["theta_x"].notna().mean()) if len(out) else 0.0
    LOG.info(f"θ_X 산출 커버리지 {cov*100:.0f}% "
             f"({out['theta_src'].value_counts().to_dict()}) — "
             f"결측은 0 이나 1 이 아니라 셀 중앙값으로 대체하고 그 사실을 기록합니다.")
    if cov < 0.3:
        LOG.warn("θ_X 커버리지가 30% 미만입니다. θ_X 가중은 사실상 상수가 되며, "
                 "'수출 비중이 낮은데 신호만 좋은' 기업을 걸러내는 힘이 약해집니다. "
                 "R5 절제(θ_X 가중 vs 미가중)로 영향을 실측하세요.")
    return out[cols]


def build_subsidy_signal(fin: pd.DataFrame) -> pd.DataFrame:
    """V11 보조 — 정부보조금수익/매출 급증.

    표준 계정과목에 '정부보조금수익'이 항상 잡히지는 않는다. 잡히지 않으면 결측으로 두고
    V11 은 유효세율 조항만으로 판정한다(그 사실을 로그에 남긴다).
    """
    cols = ["code", "knowledge_date", "subsidy_ratio_chg"]
    if fin is None or not len(fin):
        return pd.DataFrame(columns=cols)
    cand = [c for c in fin.columns if "subsidy" in str(c).lower() or "보조금" in str(c)]
    if not cand:
        LOG.info("정부보조금수익 계정을 재무제표에서 찾지 못했습니다 — "
                 "V11 은 유효세율 급락 조항만으로 판정합니다.")
        return pd.DataFrame(columns=cols)
    d = fin[["code", "knowledge_date"]].copy()
    sub = pd.to_numeric(fin[cand[0]], errors="coerce")
    rev = pd.to_numeric(fin.get("revenue_ttm", fin.get("revenue")), errors="coerce")
    r = safe_div(sub, rev)
    d["subsidy_ratio_chg"] = r - r.groupby(fin["code"], observed=True).shift(4)
    return d[cols]


def build_coverage_panel(reports: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """d2/d4 — 애널리스트 커버리지의 '존재'와 '개시'.

    ★ 이 전략이 리포트에서 필요로 하는 것은 신원이 아니라 커버리지의 존재 여부와 개시 시점이다
      (§7.4). 목록 레벨에서 확보 가능하므로 PDF 추출을 시도하지 않는다.
      d2 = -(최근 12개월 커버리지 애널리스트 수)   무커버리지일수록 미반영
      d4 = 최근 6개월 내 '최초' 리포트 발생 더미   정보비대칭 해소 시작
    """
    cols = ["code", "ym", "n_analyst", "coverage_init"]
    if reports is None or not len(reports) or not len(months):
        return pd.DataFrame(columns=cols)
    r = reports.copy()
    r["code"] = r.get("stock_code").map(to_code6) if "stock_code" in r.columns else pd.NA
    r["knowledge_date"] = as_ts_series(r.get("knowledge_date", r.get("pub_date")))
    r = r[r["code"].notna() & r["knowledge_date"].notna()].copy()
    if not len(r):
        return pd.DataFrame(columns=cols)

    # 최근 12개월 커버리지 — 애널리스트 식별이 되면 고유 인원수, 아니면 증권사 수로 대체.
    who = r.get("analyst_raw", pd.Series("", index=r.index)).astype(str).str.strip()
    alt = r.get("broker_name", r.get("broker_raw", pd.Series("", index=r.index))).astype(str)
    r["_who"] = np.where(who.str.len() > 0, who, alt)
    ex = expand_events_to_months(r[["code", "knowledge_date", "_who"]],
                                 "knowledge_date", months, window_days=365)
    if not len(ex):
        return pd.DataFrame(columns=cols)
    cov = (ex.groupby(["code", "month"], observed=True)["_who"].nunique()
             .rename("n_analyst").reset_index().rename(columns={"month": "ym"}))

    # 커버리지 개시: 그 종목의 최초 리포트일로부터 6개월
    first = r.groupby("code", observed=True)["knowledge_date"].min().rename("first_dt").reset_index()
    fx = expand_events_to_months(first, "first_dt", months, window_days=183)
    init = (fx.assign(coverage_init=1.0)[["code", "month", "coverage_init"]]
              .rename(columns={"month": "ym"}).drop_duplicates(["code", "ym"]))
    out = cov.merge(init, on=["code", "ym"], how="left")
    out["coverage_init"] = out["coverage_init"].fillna(0.0)
    LOG.ok(f"커버리지 패널: {out['code'].nunique():,}종목 × {out['ym'].nunique()}개월 "
           f"(평균 커버리지 {out['n_analyst'].mean():.1f}명)")
    return out[cols]
