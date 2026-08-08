

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증 · 해석표 · 진단카드 · 데이터흐름 지도                                       ║
# ║                                                                                          ║
# ║  "숫자 하나"가 아니라 "그 숫자가 어디서 왔는가"를 같이 낸다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _s(bt: dict, k: str, pct: bool = False, nd: int = 2) -> str:
    v = (bt or {}).get("stats", {}).get(k, np.nan)
    if v is None or not np.isfinite(v):
        return "—"
    return f"{100*v:.{nd}f}%" if pct else f"{v:.{nd}f}"


def report_performance(bts: Dict[str, dict], bench_ew: dict, bench_idx: Dict[str, dict]):
    LOG.banner("성과 검증", f"{BACKTEST_START} ~ {BACKTEST_END} · 비용 시나리오 = {COST_BASE_SCENARIO}")
    rows = []
    items = [(k, bts[k]) for k in ("A", "B", "C", "D") if k in bts]
    items.append(("EW", bench_ew))
    for k, v in (bench_idx or {}).items():
        items.append((k, v))
    for k, bt in items:
        if not bt:
            continue
        name = VARIANTS[k]["desc"] if k in VARIANTS else (bt.get("label") or k)
        rows.append([k, _trunc(name, 34), _s(bt, "cagr", True), _s(bt, "total", True, 1),
                     _s(bt, "vol", True, 1), _s(bt, "mdd", True, 1), _s(bt, "sharpe"),
                     _s(bt, "calmar"), _s(bt, "hit", True, 1),
                     _s(bt, "turnover", True, 0), _s(bt, "avg_n", False, 0),
                     _s(bt, "cash", True, 0)])
    LOG.table(rows, ["구성", "정의", "CAGR", "누적", "변동성", "MDD", "Sharpe",
                     "Calmar", "적중률", "회전율", "종목수", "현금"],
              ["c", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=34)
    LOG.info("현금 = 거래대금 참여율 상한·종목당 최대비중 때문에 채우지 못한 비중입니다. "
             "소형주 용량 제약이 실제로 얼마나 무는지를 보여줍니다(0% 가 아니면 그만큼 "
             "자본이 놀고 있다는 뜻입니다).")
    LOG.info("EW = 유니버스 동일가중(이 파일이 같은 데이터·같은 비용모형으로 직접 측정). "
             "벤치마크 수치를 인용하지 않는다는 원칙 5 를 코드로 지킵니다.")


def report_yearly(bts: Dict[str, dict], bench_ew: dict):
    """연도별 수익률. 특정 연도 하나가 전체를 만든 것인지 본다."""
    series = {}
    for k in ("A", "C", "D"):
        bt = bts.get(k)
        if bt and len(bt.get("returns", [])):
            R = bt["returns"]
            series[k] = R.set_index("month")["ret"]
    if bench_ew and len(bench_ew.get("returns", [])):
        series["EW"] = bench_ew["returns"].set_index("month")["ret"]
    if not series:
        return
    yrs = sorted({int(pd.Timestamp(i).year) for s in series.values() for i in s.index})
    rows = []
    for y in yrs:
        row = [str(y)]
        for k in ("D", "C", "A", "EW"):
            if k not in series:
                continue
            s = series[k]
            sel = s[[pd.Timestamp(i).year == y for i in s.index]]
            row.append(f"{100*((1+sel).prod()-1):.1f}%" if len(sel) else "—")
        rows.append(row)
    hdr = ["년도"] + [k for k in ("D", "C", "A", "EW") if k in series]
    LOG.table(rows, hdr, ["c"] + ["r"] * (len(hdr) - 1),
              title="연도별 수익률 — 한 해가 전체를 만든 것인지 확인")


def report_subperiod(bt: dict):
    R = (bt or {}).get("returns")
    if R is None or len(R) < 24:
        return
    R = R.sort_values("month").reset_index(drop=True)
    h = len(R) // 2
    rows = []
    for lab, part in (("전반", R.iloc[:h]), ("후반", R.iloc[h:])):
        s = perf_stats(part)
        rows.append([lab, f"{part['month'].iloc[0]:%Y-%m}~{part['month'].iloc[-1]:%Y-%m}",
                     f"{100*s['cagr']:.1f}%", f"{100*s['mdd']:.1f}%", f"{s['sharpe']:.2f}",
                     f"{s['calmar']:.2f}"])
    LOG.table(rows, ["구간", "기간", "CAGR", "MDD", "Sharpe", "Calmar"],
              ["c", "l", "r", "r", "r", "r"],
              title="하위기간 안정성 — 한쪽 구간에만 성과가 몰려 있는가")


def right_tail_contribution(bt: dict):
    """상위 5% 종목-월을 빼면 성과가 사라지는가. 이 전략은 우측꼬리 의존적일 수 있다."""
    H = (bt or {}).get("holdings")
    R = (bt or {}).get("returns")
    if H is None or len(H) == 0 or R is None or len(R) == 0:
        return
    H = H.copy()
    H["contrib"] = H["w"] * H["fwd_ret"]
    thr = H["contrib"].quantile(0.95)
    trimmed = H.copy()
    trimmed.loc[trimmed["contrib"] > thr, "contrib"] = thr
    g0 = H.groupby("month", observed=True)["contrib"].sum()
    g1 = trimmed.groupby("month", observed=True)["contrib"].sum()
    cost = R.set_index("month")["cost"].reindex(g0.index).fillna(0.0)
    s0 = perf_stats(pd.DataFrame({"month": g0.index, "ret": (g0 - cost).to_numpy()}))
    s1 = perf_stats(pd.DataFrame({"month": g1.index, "ret": (g1 - cost).to_numpy()}))
    LOG.table([["원본", f"{100*s0['cagr']:.2f}%", f"{s0['calmar']:.2f}"],
               ["상위5% 기여 절단", f"{100*s1['cagr']:.2f}%", f"{s1['calmar']:.2f}"]],
              ["구성", "CAGR", "Calmar"], ["l", "r", "r"],
              title="우측꼬리 의존도 — 소수 대박 종목이 성과 전부인가")
    if np.isfinite(s0["cagr"]) and np.isfinite(s1["cagr"]) and s0["cagr"] > 0:
        drop = 1 - (s1["cagr"] / s0["cagr"]) if s0["cagr"] else np.nan
        if np.isfinite(drop) and drop > 0.6:
            LOG.warn(f"상위 5% 기여를 자르면 CAGR 이 {100*drop:.0f}% 사라집니다. "
                     f"소수 종목 의존적이므로 실제 운용에서 재현성이 낮을 수 있습니다.")


def report_interpretation(P: pd.DataFrame, fw_table: pd.DataFrame):
    LOG.banner("해석표", "신호가 실제로 무엇을 골랐는가")
    sel = P[P["Signal"] > 0]
    if len(sel) == 0:
        LOG.warn("신호가 발생한 행이 없습니다.")
        return
    rows = []
    for c, nm in [("i_sales", "매출 성장 Δlog(매출TTM)"), ("i_turn", "회전 개선 −Δ(DIO+DSO)"),
                  ("i_accr", "발생액 개선 −ΔAccruals"), ("pbr", "PBR"),
                  ("d1_trailing", "반영도 ΔlogM−ΔlogE"), ("adv20", "20일 평균거래대금")]:
        if c not in P.columns:
            continue
        a = pd.to_numeric(col(P, c), errors="coerce")
        b = pd.to_numeric(col(sel, c), errors="coerce")
        rows.append([nm, f"{a.median():,.3f}" if a.notna().any() else "—",
                     f"{b.median():,.3f}" if b.notna().any() else "—",
                     f"{100*b.notna().mean():.0f}%" if len(b) else "—"])
    LOG.table(rows, ["지표", "유니버스 중앙값", "선정종목 중앙값", "선정종목 관측률"],
              ["l", "r", "r", "r"],
              title="선정 종목의 성격 — 정말 '제약이 풀린 기업'을 고르고 있는가")

    yr = sel["month"].dt.year
    rows2 = [[str(y), f"{int((yr == y).sum()):,}",
              f"{sel.loc[yr == y, 'Signal'].mean():.4f}",
              f"{int(P.loc[P['month'].dt.year == y, 'FW'].sum()):,}"]
             for y in sorted(yr.unique())]
    LOG.table(rows2, ["년도", "신호 발생 종목월", "평균 신호", "방화벽 통과 종목월"],
              ["c", "r", "r", "r"], title="연도별 신호 생성량 — 특정 시기에만 작동하는가")
    if fw_table is not None and len(fw_table):
        LOG.table(fw_table.values.tolist(), list(fw_table.columns),
                  ["l", "c", "r", "r", "l"], title="방화벽 조항별 기여 (재출력)")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 6):
    """최근 시점 선정 종목의 '왜 골랐는가' 카드. 숫자가 아니라 논거를 본다."""
    H = (bt or {}).get("holdings")
    if H is None or len(H) == 0:
        return
    last_m = H["month"].max()
    cur = H[H["month"] == last_m].nlargest(top_n, "w")
    nm = sec.drop_duplicates("code").set_index("code")["name"].to_dict() if len(sec) else {}
    Pm = P[P["month"] == last_m].set_index("code")
    LOG.banner(f"진단 카드 — {pd.Timestamp(last_m):%Y-%m} 보유 상위 {len(cur)}종목",
               "각 종목이 어느 논거로 들어왔는지")
    rows = []
    for r in cur.itertuples(index=False):
        c = r.code
        g = (lambda k: (f"{float(Pm.at[c, k]):,.3f}"
                        if c in Pm.index and k in Pm.columns and pd.notna(Pm.at[c, k]) else "—"))
        rows.append([c, _trunc(nm.get(c, ""), 14), f"{100*r.w:.1f}%", f"{r.signal:.4f}",
                     g("i_sales"), g("i_turn"), g("i_accr"), g("pbr"), g("d1_trailing")])
    LOG.table(rows, ["코드", "종목명", "비중", "신호", "매출↑", "회전↑", "발생액↑",
                     "PBR", "반영도"], ["l", "l", "r", "r", "r", "r", "r", "r", "r"])
    LOG.info("반영도(ΔlogM−ΔlogE)가 0 에 가까워지면 청산 게이트가 발동합니다(§10).")


def report_ledger_integrity(rep: Optional[pd.DataFrame], A: Optional[pd.DataFrame],
                            L: Optional[pd.DataFrame], P: Optional[pd.DataFrame] = None):
    """리포트 ↔ 애널리스트 ↔ 종목 원장이 실제로 연결됐는지 한 화면에 보여준다."""
    LOG.banner("원장 무결성 — 리포트 · 애널리스트 · 종목",
               "다중소스가 하나의 원장으로 합쳐졌는지 · 애널리스트가 식별됐는지")
    if rep is None or len(rep) == 0:
        LOG.warn("수집·적재된 애널리스트 리포트가 없습니다. "
                 "이 전략의 E층은 리포트에 의존하지 않으므로 백테스트는 정상 진행됩니다. "
                 "(U층의 리비전 보조신호만 비활성화됩니다)")
        return
    try:
        audit_linkage(rep, A if A is not None else pd.DataFrame(),
                      L if L is not None else pd.DataFrame())
    except Exception as e:                                             # noqa
        LOG.warn(f"원장 감사 출력 실패({type(e).__name__}) — 아래 요약으로 대체합니다.")
        rows = [["리포트", f"{len(rep):,}행"],
                ["애널리스트", f"{0 if A is None else len(A):,}명"],
                ["리포트-애널리스트 링크", f"{0 if L is None else len(L):,}행"]]
        LOG.table(rows, ["원장", "규모"], ["l", "r"])

    # 전략 유니버스와의 교집합 — '수집은 됐는데 이 전략과 무관한' 경우를 잡는다.
    if P is not None and len(P) and "code" in rep.columns:
        uni_codes = set(P.loc[P.get("u_micro", pd.Series(True, index=P.index)).astype(bool), "code"])
        rc = set(rep["code"].dropna().astype(str))
        inter = uni_codes & rc
        LOG.table([["U-MICRO 유니버스 종목", f"{len(uni_codes):,}"],
                   ["리포트 보유 종목", f"{len(rc):,}"],
                   ["교집합(리포트가 있는 U-MICRO 종목)", f"{len(inter):,}"],
                   ["커버리지", f"{100*len(inter)/max(len(uni_codes),1):.1f}%"]],
                  ["항목", "값"], ["l", "r"],
                  title="리포트 커버리지 × U-MICRO — 소형주 구간이 구조적으로 얇다는 가설의 실측")


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도", "무엇이 어디서 와서 어디로 갔는가")
    _safe_print("""
  [수집 L1]                              [정제/PIT]                 [전략 L2]           [평가 L3/L5]
  FDR 상장/폐지 ─┐
  KIND 상장법인 ─┼→ security_master ──┐
  KRX 스냅샷    ─┘                     │
                                       ├→ Universe(C2/C13) ─┐
  FDR/pykrx/네이버/yfinance 가격 ──────┤                     │
       └→ price_panel(월말·익월시가) ──┘                     ├→ base_panel ─┐
                                                             │              │
  KRX/pykrx/DART 주식총수 → mcap_panel(시총·랭크) ───────────┘              ├→ 셀 정규화(date×업종)
                                                                            │   └→ TP_I2 · TP_I4 → E
  DART 재무(일괄) → tidy → 분기센서(i_sales/i_turn/i_accr) ─→ PIT ──────────┤   └→ 반영도 → U
                                                                            │
  DART 거래소공시(I)·외부감사(F) → 관리종목/감사의견/거래정지 ─→ PIT ───────┤→ S1_FIREWALL
  DART 주요사항(B) → 유증/CB/BW ────────────────────────────→ PIT ───────┤→ V1·V2·V3·V6
                                                                            │
  한경컨센서스 ─┐                                                           └→ Signal = E×U×FW×VETO
  네이버리서치 ─┴→ report_master + analyst_master + link ─→ (U층 보조·원장감사)      │
                                                                                     ▼
                                                      백테스트(A/B/C/D) → 성과 → R0/R2-M/R3/R5-M/R9
""".rstrip())
    LOG.info("공용 인덱스(_shared)에 적재되는 것 = 원본·범용 정제본(가격·시총·재무·공시·리포트 원장). "
             "전용 인덱스에 적재되는 것 = 이 전략의 해석물(패널·스코어·백테스트).")
