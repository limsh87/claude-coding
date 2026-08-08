# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단카드 · 산출물 (§13)                                        ║
# ║                                                                                          ║
# ║  이 전략의 리포트는 '얼마 벌었나'가 아니라 '왜 벌었나 / 그게 알파인가 위험 프리미엄인가'를  ║
# ║  먼저 말해야 한다(§12-1). 그래서 R2-F 판정이 성과표보다 위에 온다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

INTERP_FLP = [
    ("TP_F1", "많이 빠졌는데 강제 재고 없음 = 소진 완료", "재고 남음 → 국면 A/B (진입 금지)"),
    ("TP_F2", "개인 이탈 × 기관 유입 = 소유권 이전 완료", "매도자만 있고 인수자가 없음"),
    ("TP_F3", "낙폭 크고 변동성 진정 = 패닉 종료", "아직 진행 중 (칼날 낙하)"),
    ("TP_F4", "잔고 감소 멈춤 × 거래 정상화", "청산이 계속되는 중"),
]


def report_grade_banner():
    """★ F1(신용잔고 등급)과 Fallback 단계를 리포트 '첫 줄'에 박는다(§13 체크리스트)."""
    lvl = {"PRIMARY_DAILY": "완전체 (일별 직접 관측)",
           "FALLBACK_A_WEEKLY": "해상도 손실 (주간 관측 + forward-fill)",
           "FALLBACK_B_PROXY": "★ 열등재 (개인 순매수 프록시) — 사실상 다른 전략",
           "NONE": "부재", "UNKNOWN": "미판정"}.get(CREDIT_GRADE, CREDIT_GRADE)
    LOG.banner(f"F1 신용융자잔고 등급 = {CREDIT_GRADE}", f"{lvl} · {CREDIT_SOURCE_NOTE}")
    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        LOG.error("§11-3 — 프록시로 내려간 사실을 숨기지 않습니다. 아래 모든 결과, 특히 R2-F 는 "
                  "'신용잔고 소진'이 아니라 '개인 누적순매수 감소'를 본 것입니다. "
                  "신뢰도를 하향해 해석하세요.")
    LOG.info(f"수급(F2) 등급 = {FLOW_GRADE} · 관리종목/거래정지(K6) 등급 = {WATCH_GRADE}")
    if FIREWALL_STATUS:
        LOG.table([[k, v] for k, v in FIREWALL_STATUS.items()], ["방화벽 조항", "상태"], ["l", "l"],
                  title="방어 가동 현황 — 무엇이 켜져 있고 무엇이 꺼져 있는가 (성과보다 먼저 볼 것)")


def report_canary():
    if not CANARY:
        return
    fails = [c for c in CANARY.values() if c["pass"] is False]
    rows = [[c["id"], _trunc(c["name"], 34),
             "✔ PASS" if c["pass"] else ("✘ FAIL" if c["pass"] is False else "→ 정보"),
             _trunc(c["measured"], 46), _trunc(c["action"], 34)]
            for c in list(CANARY.values())]
    # FAIL 항목을 표 상단으로 (§2 요구)
    rows.sort(key=lambda r: 0 if r[2].startswith("✘") else 1)
    LOG.table(rows, ["ID", "확인 항목", "판정", "실측", "조치"], ["l", "l", "c", "l", "l"],
              title=f"CANARY 실측표 (§2) — FAIL {len(fails)}건")


def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    s = perf_stats_w(bt.get("returns", pd.DataFrame()))
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다 (수익률 시계열 없음).")
        return {}
    LOG.banner(f"성과 검증 {label or bt.get('label','')}",
               "주 1회 리밸런싱 · 다음 거래일 시가 체결 · 수수료+세금+슬리피지 반영")
    order = ["주수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "주평균", "t통계량(HAC)", "최장언더워터(주)", "누적수익", "평균종목수",
             "평균투자비중", "주평균회전율", "주평균비용"]
    pct = {"CAGR", "연변동성", "MDD", "승률", "주평균", "누적수익", "주평균비용",
           "평균투자비중"}
    rows = []
    for k in order:
        if k not in s:
            continue
        v = s[k]
        rows.append([k, f"{v:.2%}" if k in pct and isinstance(v, float) and np.isfinite(v)
                     else (f"{v:,.2f}" if isinstance(v, float) else f"{v:,}")])
    LOG.table(rows, ["지표", "값"], ["l", "r"])

    inv = s.get("평균투자비중", np.nan)
    if np.isfinite(inv) and inv < 0.7:
        LOG.warn(f"평균 투자비중이 {inv:.0%} 입니다 — 종목당 상한({POS_MAX_WEIGHT:.0%})에 걸려 "
                 f"나머지는 현금으로 남습니다. 이는 '적격 종목이 적다'는 사실의 정직한 반영이며, "
                 f"CAGR 은 그만큼 희석됩니다. 상한을 올리려면 R12 결과를 먼저 보세요(§12-2).")

    inc = bt.get("incidents") or {}
    if any(inc.values()):
        LOG.table([["거래정지로 못 판 보유주(주-종목)", f"{inc.get('frozen',0):,}"],
                   ["폐지 확정 -100% 처리", f"{inc.get('delisted',0):,}"],
                   ["장기 시세부재 보수적 상각(-100%)", f"{inc.get('stale_writeoff',0):,}"]],
                  ["보유 중 사고", "건수"], ["l", "r"],
                  title="보유 중 사고 처리 — 이 숫자가 0 이면 오히려 의심하세요(C2)")

    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:.4f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 — 상위 종목을 빼면 성과가 사라지는가")
    return s


def report_interpretation(P: pd.DataFrame):
    LOG.banner("해석표", "각 TP 가 발화했다는 것과 발화하지 않았다는 것이 각각 무슨 뜻인가")
    live = P[P["Signal"] > 0] if "Signal" in P.columns else P.head(0)
    rows = []
    for tpc, on, off in INTERP_FLP:
        if tpc not in P.columns:
            continue
        fire = float((P[tpc] > 0).mean()) if len(P) else np.nan
        fire_sel = float((live[tpc] > 0).mean()) if len(live) else np.nan
        rows.append([tpc, f"{fire:.1%}", f"{fire_sel:.1%}", _trunc(on, 40), _trunc(off, 34)])
    LOG.table(rows, ["TP", "전체 발화율", "선정군 발화율", "발화 의미", "미발화 의미"],
              ["l", "r", "r", "l", "l"], maxw=44)

    if "phase" in P.columns:
        d = P.copy()
        d["ym"] = d["wk"].dt.to_period("Q").astype(str)
        piv = (d.groupby(["ym", "phase"], observed=True)["code"].nunique()
                .unstack("phase").fillna(0).astype(int))
        for c in ("A", "B", "C"):
            if c not in piv.columns:
                piv[c] = 0
        tail = piv.tail(12)
        LOG.table([[i, f"{int(tail.loc[i,'A']):,}", f"{int(tail.loc[i,'B']):,}",
                    f"{int(tail.loc[i,'C']):,}"] for i in tail.index],
                  ["분기", "A 물타기", "B 반대매매중", "C 소진(진입)"], ["c", "r", "r", "r"],
                  title="국면 분포 (최근 12분기) — 국면 C 가 언제 나타나는가")

    if "rs_cov_90d" in P.columns and P["rs_cov_90d"].notna().any() and len(live):
        cov = float((live["rs_cov_90d"].fillna(0) > 0).mean())
        upr = float(live["rs_tp_up_ratio"].mean(skipna=True))
        LOG.info(f"선정 종목의 애널리스트 커버리지 보유 비율 {cov:.1%} · "
                 f"목표주가 상향비율 평균 {upr:.1%} "
                 f"— 커버리지가 낮다는 것은 '기관이 이미 손을 뗀 구간'이라는 뜻이며, "
                 f"이 전략이 프리미엄을 받는 이유이기도 하다")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    """최근 신호 상위 종목의 '왜 뽑혔는가'를 센서 단위로 분해해 보여준다."""
    if "Signal" not in P.columns or not len(P):
        return
    last_wk = P.loc[P["Signal"] > 0, "wk"].max()
    if pd.isna(last_wk):
        LOG.warn("발화한 신호가 한 건도 없어 진단카드를 만들 수 없습니다. "
                 "국면 C 조건이 너무 엄격하거나 신용잔고가 결측일 가능성이 큽니다.")
        return
    sub = P[(P["wk"] == last_wk) & (P["Signal"] > 0)].nlargest(top_n, "Signal")
    names = sec.set_index("code")["name"].to_dict() if len(sec) else {}
    LOG.banner(f"진단 카드 — {pd.Timestamp(last_wk):%Y-%m-%d} 기준 상위 {len(sub)}종목",
               "신호가 아니라 '근거'를 본다")
    for r in sub.itertuples(index=False):
        LOG.rule(f"{getattr(r,'code','')} {names.get(getattr(r,'code',''),'')}")
        rows = [
            ["고점대비 낙폭 f_dd", f"{getattr(r,'f_dd',np.nan):.1%}"],
            ["신용잔고율 백분위 f_cr_pctl", f"{getattr(r,'f_cr_pctl',np.nan):.2f}"],
            ["신용잔고 20일 변화 f_cr_chg", f"{getattr(r,'f_cr_chg',np.nan):+.1%}"],
            ["개인 이탈(60일) f_ret_ex", f"{getattr(r,'f_ret_ex',np.nan):+.4f}"],
            ["기관+외국인(20일) f_inst", f"{getattr(r,'f_inst',np.nan):+.4f}"],
            ["변동성 진정 f_vol", f"{getattr(r,'f_vol',np.nan):+.4f}"],
            ["거래 정상화 f_turn", f"{getattr(r,'f_turn',np.nan):.2f}"],
            ["TP_F1/F2/F3/F4",
             " / ".join(f"{getattr(r,c,np.nan):.3f}" for c in TP_COLS)],
            ["국면", str(getattr(r, "phase", "-"))],
            ["방화벽·거부권", f"FW={getattr(r,'FIREWALL',0)} V1={getattr(r,'V1',1)} "
                              f"V3={getattr(r,'V3',1)} V_RS={getattr(r,'V_RS',1)}"],
            ["애널 커버리지(90일)", f"{getattr(r,'rs_cov_90d',np.nan)}"],
        ]
        LOG.table(rows, ["근거", "값"], ["l", "r"])


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도", "어느 소스가 어느 지표를 만들고, 없으면 무엇이 죽는가")
    rows = [
        ["KRX 마켓플레이스/수동CSV", "신용융자잔고", "f_cr · f_cr_pctl · TP_F1 · TP_F4 · 국면 A/B/C",
         f"등급 {CREDIT_GRADE} (KRX모드 {KRX_MODE})"],
        ["pykrx / ★네이버 매매동향", "개인/기관/외국인 순매수", "f_retail · f_inst · f_ret_ex · TP_F2",
         f"등급 {FLOW_GRADE}"],
        ["FDR/네이버/yfinance/pykrx", "일봉·거래대금", "f_dd · f_vol · f_turn · 체결가 · ADV",
         "FDR 우선(§1-8)"],
        ["FDR폐지목록+DART+★가격이력", "상장/폐지일", "PIT 유니버스(C2·C13)",
         "KRX 없이 생존자편향 제거"],
        ["★DART 주식총수 / pykrx 시총", "상장주식수", "시총 분모 · 규모버킷 · 상위250 제외",
         "DART 경로는 PIT 완전"],
        ["DART 재무·공시", "자본총계·영업CF·증자/CB/BW", "방화벽 · V1 · V3", "키 없으면 비활성"],
        ["KIND 관리종목/거래정지", "감시 플래그", "방화벽", f"등급 {WATCH_GRADE}"],
        ["한경컨센서스 · 네이버리서치", "리포트·애널리스트·목표주가", "V_RS 거부권 · 해석표",
         "공용 인덱스 재사용"],
    ]
    LOG.table(rows, ["소스", "산출물", "쓰이는 곳", "비고"], ["l", "l", "l", "l"], maxw=42)


def persist_outputs(P: pd.DataFrame, bt: dict, r2f: dict, r12: dict, abl: pd.DataFrame,
                    phase_dist: pd.DataFrame, uni: "Universe") -> List[str]:
    """산출물을 전용 인덱스에 저장한다. 공용 원본은 수집 단계에서 이미 적재되어 있다.
    ★ 기존 파일을 지우지 않는다 — Vault 가 백업 후 교체하거나 리비전으로 남긴다."""
    outs: List[str] = []
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    def _csv(name: str, df: Optional[pd.DataFrame]):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{stamp}.csv")
        df.to_csv(p, index=False, encoding="utf-8-sig")
        outs.append(p)

    def _txt(name: str, text: str):
        p = os.path.join(outdir, f"{name}_{stamp}.md")
        atomic_write_text(p, text)
        outs.append(p)

    _csv("returns", bt.get("returns"))
    _csv("holdings", bt.get("holdings"))
    _csv("r5_ablation", abl)
    _csv("phase_distribution", phase_dist)
    _csv("attrition", pd.DataFrame(uni.attrition) if uni is not None else None)
    _csv("runtime", pd.DataFrame([{"stage": r.sid, "name": r.name, "layer": r.layer,
                                   "status": r.status, "seconds": round(r.dur, 2),
                                   "budget_s": r.budget_s, "rows_in": r.rows_in,
                                   "rows_out": r.rows_out}
                                  for r in PIPE.stages.values()]))
    _csv("canary", pd.DataFrame(list(CANARY.values())))

    # r2f_verdict.md — ★ 최우선 산출물
    v = r2f.get("verdict", "측정되지 않음")
    _txt("r2f_verdict",
         f"# R2-F 판정 — 소진 조건 vs 단순 낙폭과대\n\n"
         f"- 신용잔고 등급: **{CREDIT_GRADE}** ({CREDIT_SOURCE_NOTE})\n"
         f"- A 낙폭과대 단독 CAGR: {r2f.get('A', {}).get('CAGR', float('nan')):.4%}\n"
         f"- B 소진조건 단독 CAGR: {r2f.get('B', {}).get('CAGR', float('nan')):.4%}\n"
         f"- C FLP 전체 CAGR: {r2f.get('C', {}).get('CAGR', float('nan')):.4%}\n"
         f"- C−A HAC t: {r2f.get('t_CA', float('nan')):.2f}\n\n## 판정\n\n{v}\n")
    _txt("r12_tail_correlation",
         "# R12 꼬리 동시손실\n\n" +
         "\n".join(f"- {k}: {v}" for k, v in (r12 or {}).items()) +
         f"\n\n## 확정된 사이징\n\n- 종목당 최대비중(코드 상수): **{POS_MAX_WEIGHT:.0%}**\n"
         f"- R12 권고: **{(r12 or {}).get('recommended_pos_max', POS_MAX_WEIGHT):.1%}**\n"
         f"- 동시보유 상한: {PORTFOLIO_MAX_NAMES}종목 · ADV 참여율 {POS_ADV_PARTICIPATION:.0%}\n")
    _txt("robustness",
         "# 강건성 결과 (R0~R12)\n\n" +
         "\n".join(f"- **{r['id']}** {r['name']}: "
                   f"{'PASS' if r['pass'] else ('FAIL' if r['pass'] is False else 'INFO')} — {r['detail']}"
                   for r in ROBUST_RESULTS) +
         "\n\n> 벤치마크 수치는 이 실행에서 직접 재측정한 값이며 하드코딩이 아니다(§1-5).\n")
    lp = os.path.join(outdir, f"log_{stamp}.txt")
    atomic_write_text(lp, "\n".join(LOG.buffer))
    outs.append(lp)

    # 전용 인덱스 테이블 (다음 실행/다른 노트북에서 그대로 재호출 가능)
    keep = [c for c in ("code", "wk", "signal_date", "close", "exec_px", "fwd_ret", "adv20",
                        "mcap", "phase", "PHASE_A", "PHASE_B", "PHASE_C", "FIREWALL", "VETO",
                        "in_band", "E", "E_rank", "Signal") + tuple(SENSOR_COLS) + tuple(TP_COLS)
            if c in P.columns]
    VAULT.put_table(f"flp_panel_{STRATEGY_ID}", P[keep], scope="private", domain="features",
                    source="L1/L2 weekly panel",
                    extra={"credit_grade": CREDIT_GRADE, "flow_grade": FLOW_GRADE})
    VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt.get("returns", pd.DataFrame()),
                    scope="private", domain="backtest", source=STRATEGY_ID)
    if len(bt.get("holdings", pd.DataFrame())):
        VAULT.put_table(f"backtest_holdings_{STRATEGY_ID}", bt["holdings"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
    if abl is not None and len(abl):
        VAULT.put_table(f"r5_ablation_{STRATEGY_ID}", abl, scope="private", domain="robust",
                        source="R5")
    VAULT.put_table(f"robustness_{STRATEGY_ID}",
                    pd.DataFrame([{k: (json.dumps(v, ensure_ascii=False, default=str)
                                       if isinstance(v, dict) else v)
                                   for k, v in r.items()} for r in ROBUST_RESULTS]),
                    scope="private", domain="robust", source="R-suite")
    LOG.ok(f"산출물 {len(outs)}건 저장 → {outdir}")
    return outs
