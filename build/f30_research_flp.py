# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-C  애널리스트 리포트 오버레이 (한경컨센서스 · 네이버 리서치)                        ║
# ║                                                                                          ║
# ║  이 전략에서 리포트는 알파 원천이 아니라 '거부권과 해석'이다.                               ║
# ║    · 낙폭 국면에서 같은 애널리스트가 목표주가를 계속 내리고 있다면 그건 '소진'이 아니라     ║
# ║      펀더멘털 악화다 → V_RS 거부권.                                                        ║
# ║    · 커버리지가 사라진 종목(리포트 0건)은 '기관이 이미 손을 뗀' 상태 → 해석표에 표기.       ║
# ║                                                                                          ║
# ║  ★ 목표주가 리비전은 '같은 애널리스트의 직전 제시가'와 비교해야 의미가 있다.                ║
# ║    그래서 애널리스트 원장(entity resolution)이 장식이 아니라 필수 입력이다.                 ║
# ║  ★ 원장은 공용 인덱스에 적재되어 다른 전략이 그대로 재사용한다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

RESEARCH_PANEL_COLS = ["code", "wk", "rs_cov_90d", "rs_tp_up_ratio", "rs_tp_gap", "rs_n_180d"]


def build_research_panel(links: pd.DataFrame, P_keys: pd.DataFrame,
                         weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """(code, wk) 별 리포트 오버레이.

    입력 links 는 build_analyst_ledger 의 산출(보고서×애널리스트 링크)이며
    최소한 code / date(발간일) / analyst_id / target_price 를 갖는다.

    PIT: 발간일 그 자체가 공개일이므로 knowledge_date = date. 미래 리포트는 절대 안 본다.
    """
    if links is None or not len(links):
        LOG.info("리포트 원장이 비어 있어 오버레이를 생성하지 않습니다 "
                 "(V_RS 거부권 비활성 · 해석표의 커버리지 열은 공란).")
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)

    L = links.copy()
    dcol = next((c for c in ("pub_date", "date", "report_date") if c in L.columns), None)
    ccol = next((c for c in ("stock_code", "code") if c in L.columns), None)
    if dcol is None or ccol is None:
        LOG.warn(f"리포트 원장에 발간일/종목코드 컬럼이 없습니다 → 오버레이 생략. "
                 f"컬럼={list(L.columns)[:12]}")
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)
    L["date"] = as_ts_series(L[dcol])
    L["code"] = L[ccol].map(to_code6)
    L = L.dropna(subset=["code", "date"])
    if "target_price" not in L.columns:
        L["target_price"] = np.nan
    L["target_price"] = pd.to_numeric(L["target_price"], errors="coerce")
    aid = next((c for c in ("analyst_id", "analyst_key", "analyst") if c in L.columns), None)
    if aid is None:
        L["analyst_id"] = L.get("broker", pd.Series("", index=L.index)).astype(str)
        aid = "analyst_id"

    # ── 같은 애널리스트·같은 종목의 직전 목표주가 대비 방향 ────────────────────────────────
    L = L.sort_values([aid, "code", "date"])
    prev_tp = L.groupby([aid, "code"], observed=True)["target_price"].shift(1)
    L["tp_dir"] = np.where(L["target_price"] > prev_tp * 1.01, 1,
                           np.where(L["target_price"] < prev_tp * 0.99, -1, 0))
    L.loc[L["target_price"].isna() | prev_tp.isna(), "tp_dir"] = np.nan

    # ── (code, week) 격자로 90일/180일 창 집계 — 종목 루프 없이 merge_asof + 롤링 ──────────
    #   주 격자에 맞춰 리포트를 주 단위로 먼저 압축한 뒤 rolling 하면 O(N) 이다.
    wk_of = pd.DatetimeIndex(weeks)
    if not len(wk_of):
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)
    pos = np.searchsorted(wk_of.values, L["date"].values, side="right")
    keep = pos < len(wk_of)
    L = L[keep].copy()
    L["wk"] = wk_of.values[pos[keep]]     # 발간일 '이후 첫 신호주'에 반영 (당일 누수 차단)
    if L.empty:
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)

    agg = (L.groupby(["code", "wk"], observed=True)
             .agg(n=("date", "size"),
                  up=("tp_dir", lambda s: float((s == 1).sum())),
                  dn=("tp_dir", lambda s: float((s == -1).sum())),
                  tp_med=("target_price", "median"))
             .reset_index())

    full = P_keys[["code", "wk"]].drop_duplicates()
    A = full.merge(agg, on=["code", "wk"], how="left").sort_values(["code", "wk"])
    for c in ("n", "up", "dn"):
        A[c] = A[c].fillna(0.0)
    g = lambda c: A.groupby("code", observed=True)[c]
    A["rs_n_180d"] = g("n").transform(lambda s: s.rolling(26, min_periods=1).sum())
    n90 = g("n").transform(lambda s: s.rolling(13, min_periods=1).sum())
    up90 = g("up").transform(lambda s: s.rolling(13, min_periods=1).sum())
    dn90 = g("dn").transform(lambda s: s.rolling(13, min_periods=1).sum())
    A["rs_cov_90d"] = n90
    denom = (up90 + dn90)
    A["rs_tp_up_ratio"] = np.where(denom > 0, up90 / denom, np.nan)
    A["rs_tp_med"] = g("tp_med").transform(lambda s: s.ffill(limit=26))
    A["rs_tp_gap"] = np.nan          # 가격 대비 괴리는 패널 결합 후 계산한다
    out = A[RESEARCH_PANEL_COLS].copy()
    LOG.ok(f"리포트 오버레이 {len(out):,}행 — 커버리지 보유 {int((out['rs_cov_90d']>0).sum()):,}행, "
           f"목표주가 방향 판정 가능 {int(out['rs_tp_up_ratio'].notna().sum()):,}행")
    PIPE.io("OUT", "MEM", "research_panel", out)
    return out


def audit_research_wiring(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame,
                          panel: pd.DataFrame):
    """'수집은 됐는데 배선이 끊긴' 상태를 '데이터 부재'와 구분한다.
    이 구분이 없으면 운영자가 엉뚱하게 API 키를 의심하며 시간을 쓴다."""
    rows = [
        ["리포트 원장(rep)", f"{len(rep):,}행" if rep is not None else "없음",
         "한경+네이버 통합 원장"],
        ["애널리스트 원장(A)", f"{len(A):,}명" if A is not None else "없음",
         "증권사 사명 정규화 + 동명이인 분리"],
        ["보고서×애널 링크(L)", f"{len(L):,}행" if L is not None else "없음",
         "목표주가 리비전의 유일한 근거"],
        ["패널 결합 결과", f"{int(panel['rs_cov_90d'].notna().sum()):,}행" if
         panel is not None and "rs_cov_90d" in panel.columns else "0행",
         "여기가 0이면 수집이 아니라 '배선'이 끊긴 것"],
    ]
    LOG.table(rows, ["단계", "규모", "의미"], ["l", "r", "l"],
              title="애널리스트 리포트 → 전략 배선 점검 (다중소스 원장 연결)")
    if (rep is not None and len(rep) > 0 and
            (panel is None or "rs_cov_90d" not in getattr(panel, "columns", []) or
             int(panel["rs_cov_90d"].notna().sum()) == 0)):
        LOG.warn("리포트는 수집됐는데 패널에 한 건도 결합되지 않았습니다. "
                 "종목코드 정규화(6자리) 또는 발간일 파싱을 먼저 의심하세요 — "
                 "'데이터 부재'가 아니라 '배선 결함'입니다.")
