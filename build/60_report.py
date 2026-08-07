

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — 성과검증표 / 해석표 / 종목별 진단 카드                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

INTERP_D_STATE = [
    ("ΔE>0, ΔM≤0", "★목표 상태. 시장이 개선을 일회성으로 분류", "진입"),
    ("ΔE>0, ΔM>0", "리레이팅 진행 중. 알파 소진", "관망/청산"),
    ("ΔE≤0, ΔM>0", "기대만 앞섬", "배제"),
    ("ΔE≤0, ΔM≤0", "개선 없음", "배제"),
]
INTERP_COMMON = [
    ("TP_B1", "수요가 공급을 당김. 협상력", "밀어내기 가능성 → V1 확인"),
    ("TP_B2", "이익의 질 양호", "회계적 이익 우위"),
    ("TP_C1", "수익성 유지하며 확장. 제약선 이동", "확장이 수익성 희석"),
    ("TP_C2", "희석 없는 인력 확장", "단순 규모 확대"),
]


def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    LOG.banner(f"성과 검증 — {label or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 1회 리밸런싱 · 익일 시가 체결 · 롱온리")
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return
    order = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
             "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
             "월평균회전율", "월평균비용"]
    fmt = {"누적수익": "pct", "CAGR": "pct", "연변동성": "pct", "MDD": "pct", "승률": "pct",
           "월평균": "pctp", "월평균비용": "pctp", "월평균회전율": "num"}
    rows = []
    for k in order:
        v = s.get(k)
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            rows.append([k, "—"]); continue
        f = fmt.get(k)
        rows.append([k, f"{v*100:+.2f}%" if f == "pct" else
                        f"{v*100:+.3f}%p" if f == "pctp" else
                        f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"])
    LOG.table(rows, ["지표", "값"], ["l", "r"], title="포트폴리오 성과")

    brows = []
    R = bt["returns"].set_index("month")["ret"]
    for name, b in bench.items():
        bb = b.reindex(R.index).fillna(0)
        cum_s = float((1 + R.fillna(0)).prod() - 1)
        cum_b = float((1 + bb).prod() - 1)
        excess = R.fillna(0) - bb
        _, t = hac_tstat(excess.to_numpy())
        brows.append([name, f"{cum_b*100:+.1f}%", f"{cum_s*100:+.1f}%",
                      f"{(cum_s-cum_b)*100:+.1f}%p", f"{excess.mean()*100:+.3f}%p", f"{t:.2f}"])
    if brows:
        LOG.table(brows, ["벤치마크", "벤치 누적", "전략 누적", "초과", "월평균 초과", "HAC t"],
                  ["l", "r", "r", "r", "r", "r"], title="벤치마크 대비")

    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:,.3f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 (§10.2 — 이 전략은 IR 이 아니라 꼬리에 의존한다)")
        if rt.get("총기여") and rt.get("상위5% 제외 후 총기여") is not None:
            base, ex = rt["총기여"], rt["상위5% 제외 후 총기여"]
            if base > 0 and ex <= 0:
                LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. "
                         "성과가 소수 종목에 전적으로 의존합니다 — 실전에서 그 종목을 놓치면 "
                         "전략 전체가 실패합니다. 이 사실을 반드시 인지하고 사이징하세요.")


def report_interpretation(P: pd.DataFrame):
    LOG.banner("해석 참조표 (§13.2)", "TP 가 발화했을 때와 안 했을 때 각각 무슨 뜻인가")
    rows = []
    for p in active_packs():
        for tp, fire, nofire in p["interp"]:
            rows.append([p["id"], tp, _trunc(fire, 44), _trunc(nofire, 44)])
    for tp, fire, nofire in INTERP_COMMON:
        rows.append(["공용", tp, _trunc(fire, 44), _trunc(nofire, 44)])
    LOG.table(rows, ["팩", "TP", "발화 의미", "미발화 의미"], ["c", "l", "l", "l"], maxw=46)
    LOG.table([[a, b, c] for a, b, c in INTERP_D_STATE],
              ["D축 상태", "해석", "조치"], ["l", "l", "c"], title="D축(반영도) 상태 해석")

    if "D_state" in P.columns:
        cnt = P["D_state"].value_counts()
        LOG.table([[k, f"{v:,}", f"{100*v/len(P):.1f}%"] for k, v in cnt.items()],
                  ["상태", "행수", "비중"], ["l", "r", "r"],
                  title="실제 패널의 D축 상태 분포")

    fired = []
    for p in active_packs():
        for tp in p["tp_cols"]:
            if tp in P.columns:
                v = P[tp]
                fired.append([p["id"], tp, f"{int(v.notna().sum()):,}",
                              f"{float(v.mean()):+.3f}" if v.notna().any() else "—",
                              f"{int((v > 1).sum()):,}", f"{100*float((v > 1).mean()):.2f}%"])
    for tp in ("TP_B1", "TP_B2", "TP_C1", "TP_C2"):
        if tp in P.columns:
            v = P[tp]
            fired.append(["공용", tp, f"{int(v.notna().sum()):,}",
                          f"{float(v.mean()):+.3f}" if v.notna().any() else "—",
                          f"{int((v > 1).sum()):,}", f"{100*float((v > 1).mean()):.2f}%"])
    if fired:
        LOG.table(fired, ["팩", "TP", "관측행수", "평균", "발화(>1σ²)", "발화율"],
                  ["c", "l", "r", "r", "r", "r"],
                  title="트레이드오프 쌍 발화 통계 (TP는 곱이므로 두 조건이 동시 성립할 때만 양수)")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    LOG.banner("종목별 진단 카드 (§13.1)", "최근 시점 신호 상위 종목 — 왜 뽑혔는지 한 장으로")
    last_m = P["month"].max()
    sub = P[(P["month"] == last_m) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    if sub.empty:
        sub = P[P["month"] == last_m]
    if sub.empty:
        LOG.warn("마지막 시점 패널이 비어 진단 카드를 만들 수 없습니다.")
        return
    names = sec.set_index("code")["name"].to_dict()
    top = sub.nlargest(min(top_n, len(sub)), "Signal_rank")
    for r in top.itertuples(index=False):
        code = r.code
        _safe_print("\n" + "─" * 104)
        _safe_print(f"[{code}] {names.get(code, '')}    셀: {getattr(r, 'cell', '?')}    "
              f"신호일: {pd.Timestamp(last_m).date()}")
        _safe_print("─" * 104)
        sig = getattr(r, "Signal_rank", np.nan)
        _safe_print(f"Signal {sig:.3f} (상위 {100*(1-sig):.1f}%)   "
              f"E: {getattr(r,'E',np.nan):.3f}   U: {getattr(r,'U',np.nan):.3f}   "
              f"Veto: {'통과' if getattr(r,'VETO',0)==1 else '차단'}")
        act = ",".join(p["id"] for p in active_packs()
                       if p["E_col"] in P.columns and np.isfinite(getattr(r, p["E_col"], np.nan)))
        ina = ",".join(p["id"] for p in active_packs()
                       if p["E_col"] in P.columns and not np.isfinite(getattr(r, p["E_col"], np.nan)))
        _safe_print(f"활성 팩: {act or '없음'}  |  비활성: {ina or '없음'}")

        _safe_print("\n■ 발화한 트레이드오프")
        tps = []
        for p in active_packs():
            for tp, fire, nofire in p["interp"]:
                v = getattr(r, tp, np.nan)
                if np.isfinite(v):
                    tps.append((tp, v, fire if v > 0 else nofire))
        for tp in ("TP_B1", "TP_B2", "TP_C1", "TP_C2"):
            v = getattr(r, tp, np.nan)
            if np.isfinite(v):
                meaning = next((f if v > 0 else nf for t, f, nf in INTERP_COMMON if t == tp), "")
                tps.append((tp, v, meaning))
        for tp, v, meaning in sorted(tps, key=lambda x: -x[1])[:8]:
            mark = "발화" if v > 0 else "미발화"
            _safe_print(f"  {_pad(tp,7)} {v:+7.2f}  [{mark}] {_trunc(meaning, 62)}")

        _safe_print("\n■ 미반영도 (U)")
        _safe_print(f"  d1  ΔlogE {getattr(r,'dlog_E',np.nan):+.3f}, ΔlogM {getattr(r,'dlog_M',np.nan):+.3f}"
              f"  → {getattr(r,'D_state','?')}")
        for k, lab in (("d2", "컨센 목표주가 리비전"), ("d3", "기관+외인 수급"), ("d4", "커버리지 변화")):
            v = getattr(r, k, np.nan)
            _safe_print(f"  {k}  {lab}: " + (f"{v:+.4f}" if np.isfinite(v) else "데이터 부족(결측 — 0으로 채우지 않음)"))
        if np.isfinite(getattr(r, "n_analyst", np.nan)):
            _safe_print(f"      커버 애널리스트 {int(getattr(r,'n_analyst',0))}명 · "
                  f"목표주가 중앙값 {getattr(r,'tp_median',np.nan):,.0f}원")

        _safe_print("\n■ 정책 오염 점검")
        det = getattr(r, "d_eff_tax", np.nan)
        _safe_print(f"  유효세율 변화 {det:+.4f} (임계 -0.03)   "
              f"{'✔ V8 통과' if getattr(r,'V8',1)==1 else '✘ V8 발동 — 정책 유인 채용 의심'}")
        if np.isfinite(getattr(r, "emp_band_flag", np.nan)):
            _safe_print(f"  임계밴드(50/100/300인) 근접: "
                  f"{'❗해당 — 신뢰도 하향' if getattr(r,'emp_band_flag',0)==1 else '✔ 이격'}")

        _safe_print("\n■ 거부권")
        vs = []
        for i in range(1, 9):
            v = getattr(r, f"V{i}", 1)
            vs.append(f"V{i} {'✔' if v == 1 else '✘'}")
        _safe_print("  " + "  ".join(vs))
    _safe_print("─" * 104)


def report_dataflow_map():
    """거시적 흐름 한 장 — 어디서 어디로 데이터가 가는지."""
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────┐
  │  환경감지 → 의존성 → 구글드라이브 마운트 → VAULT(공용/전용 인덱스, append-only 저널)  │
  │            └ adopt_scan: 기존 캐시 '이동 없이 참조 등록'                              │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │  종목마스터  ← FDR GitHub캐시 / KIND / pykrx월말스냅샷 / DART corpCode                 │
  │  가격·수급   ← KRX인증 → pykrx → FDR → 네이버 → yfinance  (폴백 체인, 소스 감사표)     │
  │  DART        ← 재무제표(rcept_no→knowledge_date) / 직원현황 / 공시목록 스윕             │
  │  리서치      ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장    │
  │                └ 애널리스트 원장 → (analyst_id, code, date, tp) → 목표주가 리비전       │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼  모든 테이블은 pit_frame() 통과 → PIT.register()
  ┌── L1/L2 피처 ─────────────────────────────────────────────────────────────────────────┐
  │  PIT 유니버스(상폐 포함) → 셀(date,industry,size) → 기본패널                            │
  │  PIT.asof_join(knowledge_date ≤ month)  ← C1 이 강제되는 유일한 관문                    │
  │  공용축 B/C/D  +  활성 센서팩(레지스트리)  →  TP = z(개선) × z(대가회피)                 │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L2 스코어 ──────────────────────────────────────────────────────────────────────────┐
  │  거부권 V1~V8 (이진·곱) → 하한선(빈 축 없을 것) → Signal = rank(E)×rank(U)×∏V           │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L3 백테스트 → L5 강건성 → L6 리포트 ────────────────────────────────────────────────┐
  │  익일시가 체결 · 상폐 -100% · 비용(수수료+거래세이력+제곱근충격)                          │
  │  R1 누수 → R2 TP vs 나이브⭐ → R3 직교화⭐ → R4 플라시보 → R10 정책반증 → R5~R11        │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")
