

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B2  D2 — 재무제표 이상현상 (§6.2)                                                      ║
# ║                                                                                          ║
# ║  발생액·순영업자산·재고/매출채권 괴리는 이미 문헌 검증된 이상현상이며, 섹터 무관하게        ║
# ║  100% 커버된다. D1 이 텍스트 파싱 실패로 결측일 때 축 B 를 지탱하는 것이 이 층이다.         ║
# ║                                                                                          ║
# ║  ★ 반드시 '분기 프레임' 에서 계산한다. 패널(asof)에서 diff 를 하면 같은 분기값이 여러       ║
# ║    리밸일에 반복되어 증가율이 0 또는 폭발한다. 이건 조용한 실패라 더 위험하다.               ║
# ║  ★ 주식수 증가율을 포함하는 이유(§6.2): 소형주는 지속적 증자·CB 발행으로 실적이 개선돼도    ║
# ║    주당지표가 개선되지 않거나 악화된다. 이 항목 없이는 D2 가 소형주 구간에서 오작동한다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# (컬럼, 방향) — 방향 +1 = 높을수록 우수, -1 = 낮을수록 우수
D2_ITEMS = [("ACCRUAL", -1), ("NOA", -1), ("AR_DIVERGE", -1),
            ("INV_DIVERGE", -1), ("CFO_NI_GAP", +1), ("SHARE_GROWTH", -1)]
D2_COLS = [c for c, _ in D2_ITEMS]
D2_PANEL_COLS = ["corp_code", "event_date", "knowledge_date", "bsns_year", "reprt_code"] + \
                D2_COLS + ["D2_FORCED_LOW"]

_D2_QORD = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}


def build_d2_panel(fin: pd.DataFrame, shares: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """분기 프레임에서 6개 지표를 만든다. 반환은 PIT frame (corp_code 키)."""
    if fin is None or fin.empty:
        LOG.warn("재무 데이터가 없어 D2 를 만들 수 없습니다 — GATE_6 실패 대상(심각 이슈).")
        return pd.DataFrame(columns=D2_PANEL_COLS)

    F = fin.copy()
    for c in ("corp_code", "bsns_year", "reprt_code"):
        if c not in F.columns:
            LOG.warn(f"재무 프레임에 '{c}' 가 없습니다 — D2 를 만들 수 없습니다.")
            return pd.DataFrame(columns=D2_PANEL_COLS)
    F["corp_code"] = F["corp_code"].astype(str)
    F["reprt_code"] = F["reprt_code"].astype(str)
    F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
    F = F.dropna(subset=["bsns_year"])
    F["bsns_year"] = F["bsns_year"].astype(int)
    F["_q"] = F["reprt_code"].map(_D2_QORD)
    F = F.dropna(subset=["_q"])
    F["_seq"] = F["bsns_year"] * 4 + F["_q"].astype(int)
    F = (F.sort_values(["corp_code", "_seq"], kind="stable")
           .drop_duplicates(["corp_code", "_seq"], keep="last").reset_index(drop=True))

    g = F.groupby("corp_code", observed=True, sort=False)

    def lag(name: str, k: int = 1) -> pd.Series:
        """k 분기 전 값. 실제 간격이 k 분기일 때만 유효(결측 분기 건너뛰기 방지)."""
        v = col(F, name)
        prev = v.groupby(F["corp_code"], observed=True).shift(k)
        pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(k)
        return prev.where((F["_seq"] - pseq) == k)

    assets = col(F, "assets")
    assets_prev = lag("assets", 1)
    assets_avg = (assets + assets_prev) / 2.0
    assets_avg = assets_avg.where(assets_avg.notna(), assets)

    ni = col(F, "net_income_ttm")
    cfo = col(F, "cfo_ttm")
    rev = col(F, "revenue_ttm")
    inv = col(F, "inventory")
    rec = col(F, "receivable")
    cash = col(F, "cash")
    liab = col(F, "liabilities")

    out = pd.DataFrame({"corp_code": F["corp_code"], "bsns_year": F["bsns_year"],
                        "reprt_code": F["reprt_code"], "_seq": F["_seq"]})

    # ① ACCRUAL = (당기순이익 − 영업현금흐름) / 평균총자산
    out["ACCRUAL"] = safe_div(ni - cfo, assets_avg)

    # ② NOA = 순영업자산 / 전기말 총자산
    #    순영업자산 = (자산총계 − 현금성자산) − (부채총계 − 총차입금)
    #    ★ tidy_financials 에는 '총차입금' 계정이 없다. 근사하되 조용히 넘기지 않고 로그로 남긴다.
    has_debt = "total_debt" in F.columns and col(F, "total_debt").notna().any()
    debt = col(F, "total_debt") if has_debt else pd.Series(0.0, index=F.index)
    if not has_debt:
        LOG.info("총차입금 계정이 없어 NOA 를 (자산−현금) − 부채 로 근사합니다 "
                 "[방법론적 한계 — 차입 의존도가 높은 기업에서 NOA 가 과소평가됩니다].")
    noa_num = (assets - cash.fillna(0)) - (liab - debt.fillna(0))
    out["NOA"] = safe_div(noa_num, assets_prev.where(assets_prev.notna(), assets))

    # ③④ 매출채권 / 재고 괴리 (YoY 증가율 차이)
    def yoy(v: pd.Series) -> pd.Series:
        prev = v.groupby(F["corp_code"], observed=True).shift(4)
        pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(4)
        prev = prev.where((F["_seq"] - pseq) == 4)
        return safe_div(v - prev, prev.abs())

    rev_g = yoy(rev)
    out["AR_DIVERGE"] = yoy(rec) - rev_g
    out["INV_DIVERGE"] = yoy(inv) - rev_g

    # ⑤ CFO_NI_GAP = (영업현금흐름 − 당기순이익) / 총자산
    out["CFO_NI_GAP"] = safe_div(cfo - ni, assets)

    # ⑥ SHARE_GROWTH = 주식수 TTM 증가율
    out["SHARE_GROWTH"] = np.nan
    if shares is not None and len(shares):
        S = shares.copy()
        S["corp_code"] = S["corp_code"].astype(str)
        S["bsns_year"] = pd.to_numeric(S["bsns_year"], errors="coerce")
        S = S.dropna(subset=["bsns_year"])
        S["bsns_year"] = S["bsns_year"].astype(int)
        S["_q"] = S["reprt_code"].astype(str).map(_D2_QORD)
        S = S.dropna(subset=["_q"])
        S["_seq"] = S["bsns_year"] * 4 + S["_q"].astype(int)
        S = (S.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last"))
        sh = pd.to_numeric(S["shares_total"], errors="coerce")
        sprev = sh.groupby(S["corp_code"], observed=True).shift(4)
        pseq = S["_seq"].groupby(S["corp_code"], observed=True).shift(4)
        sprev = sprev.where((S["_seq"] - pseq) == 4)
        S["SHARE_GROWTH"] = safe_div(sh - sprev, sprev.abs())
        out = out.merge(S[["corp_code", "_seq", "SHARE_GROWTH"]], on=["corp_code", "_seq"],
                        how="left", suffixes=("", "_s"))
        if "SHARE_GROWTH_s" in out.columns:
            out["SHARE_GROWTH"] = out["SHARE_GROWTH_s"]
            out = out.drop(columns=["SHARE_GROWTH_s"])
    else:
        LOG.warn("주식총수 데이터가 없어 SHARE_GROWTH 를 결측 처리합니다. "
                 "★ 소형주는 지속 증자·CB 로 주당지표가 악화되므로, 이 항목 없이는 D2 가 "
                 "소형주 구간에서 오작동할 수 있습니다(§6.2). 결측률 표를 반드시 확인하세요.")

    # ── 분모 0/음수 강제 최하위 배정 (§6.2) ────────────────────────────────────────────────
    #   ★ 역수 부호 반전 방지. 예: 전기 총자산이 음수면 ACCRUAL 부호가 뒤집혀
    #     '최악'이 '최우수'로 둔갑한다. NaN 으로 두면 그 종목이 그 지표에서 빠져
    #     오히려 유리해지므로, 명세는 '최하위 순위로 강제 배정' 을 지시한다.
    bad_den = (~np.isfinite(assets_avg)) | (assets_avg <= 0) | \
              (~np.isfinite(assets)) | (assets <= 0)
    out["D2_FORCED_LOW"] = bad_den.astype("float32").to_numpy()
    n_forced = int(bad_den.sum())
    if n_forced:
        LOG.info(f"분모(총자산)가 0 이하이거나 결측인 {n_forced:,}행을 각 지표의 최하위 순위로 "
                 f"강제 배정합니다 (역수 부호 반전 방지 — §6.2).")

    out["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12,31))[0]:02d}-"
                               f"{REPRT_PERIOD_END.get(str(r), (12,31))[1]:02d}")
                         for y, r in zip(out["bsns_year"], out["reprt_code"])]
    kd = F[["knowledge_date"]].reset_index(drop=True) if "knowledge_date" in F.columns else None
    out["knowledge_date"] = (as_ts_series(kd["knowledge_date"]) if kd is not None
                             else as_ts_series(out["period_end"]) + pd.Timedelta(days=45))
    out = out.drop(columns=["_seq"])
    out = pit_frame(out, "period_end", "knowledge_date", source="dart_d2")
    out = ensure_cols(out, D2_PANEL_COLS)
    LOG.ok(f"D2 분기 패널 {len(out):,}행 · {out['corp_code'].nunique():,}사 — " +
           " · ".join(f"{c} {100*out[c].notna().mean():.0f}%" for c in D2_COLS))
    PIPE.io("OUT", "MEM", "d2_panel", out)
    return downcast(out[D2_PANEL_COLS])


def attach_d2(P: pd.DataFrame, d2: Optional[pd.DataFrame]) -> pd.DataFrame:
    """as-of 결합 후 §6.2 합성: 섹터 중립 z → 상하위 1% 윈저 → 동일가중 평균."""
    P = P.copy()
    if d2 is not None and len(d2) and "corp_code" in P.columns:
        PIT.register("arc_d2", d2, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d2", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + D2_COLS + ["D2_FORCED_LOW"],
                          suffix="_d2")
    P = ensure_cols(P, D2_COLS + ["D2_FORCED_LOW"])

    zs = []
    for c, sgn in D2_ITEMS:
        v = winsor_series(col(P, c), ARC_D2_WINSOR_P) * float(sgn)   # 방향 통일(높을수록 우수)
        # 강제 최하위: 방향 통일 후이므로 '가장 작은 값'을 준다
        forced = pd.to_numeric(P["D2_FORCED_LOW"], errors="coerce").fillna(0) > 0
        if forced.any() and v.notna().any():
            v = v.mask(forced, float(np.nanmin(v.to_numpy())) - 1e-6)
        z = xsec_z_arc(P.assign(**{f"_v_{c}": v}), f"_v_{c}")
        P[f"z_{c}"] = z
        zs.append(f"z_{c}")
    P["D2_SCORE"] = xsec_z_arc(P.assign(_d2raw=nanmean_cols(P, zs)), "_d2raw")
    n_ok = int(P["D2_SCORE"].notna().sum())
    LOG.ok(f"D2 결합·합성 완료 — 유효 {n_ok:,}행 ({100*n_ok/max(len(P),1):.1f}%) · "
           f"구성 지표 {len(zs)}개")
    if n_ok / max(len(P), 1) < 0.5:
        LOG.warn(f"D2 유효율이 {100*n_ok/max(len(P),1):.0f}% 로 낮습니다. DART 재무 콜드빌드가 "
                 f"미완이거나 corp_code 매칭률이 낮다는 뜻입니다. "
                 f"D2 는 D1 보다 대체 불가하므로(§2.3) 심각 이슈로 취급하세요.")
    return P


def report_d2_coverage(P: pd.DataFrame) -> dict:
    """지표별 결측률 — GATE_6 의 근거이자 '어느 지표가 D2 를 지탱하는가' 의 답."""
    LOG.banner("D2 지표 커버리지", "결측률이 높은 지표는 사실상 합성에 기여하지 않는다")
    out = {}
    if P is None or P.empty:
        LOG.warn("패널이 비어 커버리지를 계산할 수 없습니다.")
        return out
    rows = []
    for c, sgn in D2_ITEMS:
        v = col(P, c)
        n = int(v.notna().sum())
        out[c] = n / max(len(P), 1)
        rows.append([c, "낮을수록 우수" if sgn < 0 else "높을수록 우수",
                     f"{n:,}", f"{100*out[c]:.1f}%",
                     f"{float(v.mean()):+.4f}" if n else "—",
                     f"{float(v.std()):.4f}" if n > 1 else "—"])
    LOG.table(rows, ["지표", "방향", "관측", "커버리지", "평균", "표준편차"],
              ["l", "l", "r", "r", "r", "r"])
    if "SHARE_GROWTH" in out and out["SHARE_GROWTH"] < 0.3:
        LOG.warn(f"SHARE_GROWTH 커버리지가 {100*out['SHARE_GROWTH']:.0f}% 에 불과합니다. "
                 f"소형주의 증자·CB 희석을 못 잡는다는 뜻이며, 명세 §6.2 가 경고한 "
                 f"'소형주 구간 오작동' 위험이 실재합니다.")
    # 연도별 추이
    if "asof" in P.columns:
        yr = as_ts_series(P["asof"]).dt.year
        tr = []
        for y, g in P.groupby(yr):
            tr.append([int(y)] + [f"{100*col(g, c).notna().mean():.0f}%" for c in D2_COLS])
        LOG.table(tr, ["연도"] + D2_COLS, ["c"] + ["r"] * len(D2_COLS),
                  title="D2 지표 커버리지 연도별 추이 (콜드빌드 진행 상황이 그대로 보입니다)")
    return out
