# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  리포트 — 성과검증 · 해석표 · 진단카드 · 감쇠표 · 런타임 · 데이터 흐름 지도                 ║
# ║                                                                                             ║
# ║  요구사항: "에러 발생 시 어디서 났는지, 데이터 입출력이 어디서 이뤄지는지,                  ║
# ║  애널리스트 보고서와 식별된 애널리스트가 제대로 연결됐는지, 다중소스 원장연결은 확실한지를  ║
# ║  한눈에 파악할 수 있게" — 아래 표들이 그 답이다.                                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

ATTRITION_LOG: "List[dict]" = []
OUTPUT_FILES: "List[str]" = []


def attrition(step: str, n: int, note: str = "") -> None:
    """유니버스 감쇠표(§12.2) — 어느 게이트에서 표본이 붕괴하는지 매 실행 기록한다."""
    ATTRITION_LOG.append({"단계": step, "종목수": int(n), "비고": note})


def report_attrition() -> "pd.DataFrame":
    if not ATTRITION_LOG:
        return pd.DataFrame()
    A = pd.DataFrame(ATTRITION_LOG)
    first = A["종목수"].iloc[0] if len(A) else 0
    A["잔존율"] = (A["종목수"] / first * 100).round(1) if first else np.nan
    LOG.banner("유니버스 감쇠표",
               "어느 게이트에서 표본이 붕괴하는가. 매핑게이트 통과 <150 이면 통계 검정 불가.")
    LOG.table([[r["단계"], f"{r['종목수']:,}", f"{r['잔존율']:.1f}%", r["비고"][:44]]
               for _, r in A.iterrows()], ["단계", "종목수", "잔존율", "비고"])
    return A


def report_performance_xcb(bt: dict, bench: "Dict[str, pd.Series]",
                           title: str = "성과 검증") -> dict:
    R = (bt or {}).get("returns")
    if R is None or not len(R):
        LOG.warn("성과를 계산할 수익률 시계열이 없습니다.")
        return {}
    st = perf_stats(R)
    LOG.banner(title, f"{bt.get('label','')} · {st.get('월수',0)}개월")
    order = ["월수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "월평균수익", "t통계량(HAC)", "최장언더워터(월)", "누적수익",
             "평균보유종목수", "월평균회전율", "월평균비용"]
    rows = []
    for k in order:
        v = st.get(k)
        if v is None:
            continue
        if k in ("CAGR", "연변동성", "MDD", "승률", "월평균수익", "누적수익",
                 "월평균회전율", "월평균비용"):
            rows.append([k, f"{_f(v)*100:,.2f}%"])
        elif k in ("월수", "최장언더워터(월)"):
            rows.append([k, f"{int(_f(v, 0)):,}"])
        else:
            rows.append([k, f"{_f(v):,.3f}"])
    LOG.table(rows, ["지표", "값"])

    # ★ §15.1 — 우측꼬리 의존도를 리포트 첫 페이지에 명시한다.
    rt = right_tail_contribution(bt)
    if rt:
        LOG.banner("우측 꼬리 의존도 (§15.1 — 첫 페이지에 명시)",
                   "유니버스가 얇으면 성과가 소수 종목에 달려 있다. 숨기지 않는다.")
        LOG.table([[k, (f"{_f(v)*100:.2f}%" if "CAGR" in k else str(v))]
                   for k, v in rt.items()], ["항목", "값"])
    if bench:
        LOG.banner("벤치마크 (이 실행이 직접 측정 — 하드코딩 없음)", "원칙 7")
        brows = []
        for nm, s in bench.items():
            b = perf_stats(pd.DataFrame({"ret": pd.to_numeric(s, errors="coerce").fillna(0.0)}))
            brows.append([nm, f"{_f(b.get('CAGR'))*100:6.2f}%", f"{_f(b.get('MDD'))*100:6.2f}%",
                          f"{_f(b.get('Sharpe')):6.3f}", f"{_f(b.get('Calmar')):6.3f}"])
        LOG.table(brows, ["벤치마크", "CAGR", "MDD", "Sharpe", "Calmar"])
    return st


def report_interpretation_xcb(P: pd.DataFrame, bt: dict) -> None:
    """해석표 — 각 TP 가 실제로 얼마나 발화했고 무엇을 뜻하는지."""
    LOG.banner("해석표 — 트레이드오프 쌍별 발화 현황",
               "TP 는 '개선 × 대가회피'의 곱이다. 0 이면 둘 중 하나가 없었다는 뜻이다.")
    rows = []
    for tid, ca, cb, ax, fire, nofire in XCB_TP_SPECS:
        if tid not in P.columns:
            rows.append([tid, ax, "미산출", "", fire[:34]])
            continue
        v = pd.to_numeric(P[tid], errors="coerce")
        obs = int(v.notna().sum())
        pos = float((v > 0).mean()) if obs else float("nan")
        rows.append([tid, ax, f"{obs:,}", f"{pos*100:.1f}%", fire[:34]])
    LOG.table(rows, ["TP", "축", "유효관측", "발화율", "발화 의미"])

    LOG.banner("거부권 발동 현황", "이진·곱·상쇄 불가. 부분 거부권은 축만 무효화한다.")
    vrows = []
    for v in ("V1", "V2", "V3", "V5", "V6", "V11", "V9", "V10", "V12"):
        if v not in P.columns:
            continue
        s = pd.to_numeric(P[v], errors="coerce").fillna(0)
        kind = "전면" if v in VETO_HARD else "부분"
        vrows.append([v, kind, f"{int(s.sum()):,}", f"{s.mean()*100:.2f}%"])
    LOG.table(vrows, ["거부권", "종류", "발동 종목월", "발동률"])

    if "axis_flag" in P.columns:
        LOG.table([[k, f"{v:,}"] for k, v in
                   P["axis_flag"].value_counts().items()], ["활성 축 조합", "종목월"])


def diagnostic_cards_xcb(P: pd.DataFrame, bt: dict, sec: pd.DataFrame,
                         top_n: int = 10) -> str:
    """§13 진단 카드 — 최근 시점 상위 종목."""
    if P is None or not len(P) or "Signal" not in P.columns:
        return ""
    last = P[P["Signal"].notna()]
    if not len(last):
        return ""
    m = last["ym"].max()
    sub = last[last["ym"] == m].nlargest(top_n, "Signal")
    names = {}
    if sec is not None and "code" in sec.columns:
        nc = "name" if "name" in sec.columns else ("stock_name" if "stock_name" in sec.columns else None)
        if nc:
            names = dict(zip(sec["code"].astype(str), sec[nc].astype(str)))
    out = []
    W = 92
    for _, r in sub.iterrows():
        code = str(r["code"])
        L = ["─" * W,
             f"[{code}] {names.get(code, '')[:16]:<16} 셀: {str(r.get('cell', ''))[:26]:<26} "
             f"신호일: {pd.Timestamp(r['ym']):%Y-%m-%d}",
             "─" * W,
             f"Signal {_f(r.get('Signal')):.4f} (월내 상위 {(1-_f(r.get('Signal_rank'),0))*100:.1f}%)   "
             f"E {_f(r.get('E')):.3f}  U {_f(r.get('U')):+.3f}  "
             f"θ_X {_f(r.get('theta_x')):.2f}   활성축: {r.get('axis_flag', '')}",
             "■ A축 통관 (트리거)  매핑 HS: "
             f"{str(r.get('hs_main',''))} (매핑 {int(_f(r.get('hs_n'),0))}개)"]
        for tid, ca, cb, ax, fire, _n in XCB_TP_SPECS:
            if ax != "A" or tid not in P.columns:
                continue
            v = _f(r.get(tid))
            if np.isfinite(v):
                L.append(f"  {tid}  {v:6.4f}  {fire[:38]}   "
                         f"[{ca}={_f(r.get(ca)):+.3f} / {cb}={_f(r.get(cb)):+.3f}]")
        cv = _f(r.get("cv_dest"))
        L.append(f"  cv_dest {cv:.3f} → "
                 + ("커모디티 아님, a2 유효 ✔" if _f(r.get('V10'), 0) < 1 else
                    "커모디티 → V10 발동, a2 무효화 ✘"))
        L.append("■ B·C축 (사전확률)")
        for tid, ca, cb, ax, fire, _n in XCB_TP_SPECS:
            if ax == "A" or tid not in P.columns:
                continue
            v = _f(r.get(tid))
            if np.isfinite(v):
                L.append(f"  {tid}  {v:6.4f}  {fire[:38]}   "
                         f"[{ca}={_f(r.get(ca)):+.3f} / {cb}={_f(r.get(cb)):+.3f}]")
        L.append("■ D축 미반영도 (U)")
        L.append(f"  d1  ΔlogE {_f(r.get('dlogE'))*100:+.1f}%, ΔlogM {_f(r.get('dlogM'))*100:+.1f}%"
                 + ("  → 이익 인정, 자본화 거부 ✔ [목표 상태]"
                    if (_f(r.get('dlogE'), 0) > 0 and _f(r.get('dlogM'), 0) <= 0) else
                    "  → 목표 상태 아님"))
        L.append(f"  d2  커버리지 {int(_f(r.get('n_analyst'), 0))}명   "
                 f"d3 수급 {_f(r.get('d3')):+.4f}   d4 개시 {_f(r.get('coverage_init'), 0):.0f}")
        L.append("■ 정책 오염 점검 (5중 방어)")
        L.append(f"  ① 단가 유지 여부 a2={_f(r.get('a2')):+.3f} "
                 + ("→ 보조금 저가수주 패턴 아님 ✔" if _f(r.get('a2'), -1) > 0 else "→ 단가 하락 ⚠"))
        L.append(f"  ③ 유효세율 변화 {_f(r.get('etr_chg'))*100:+.2f}%p (임계 -3%p) "
                 + ("✔ V11 통과" if _f(r.get('V11'), 0) < 1 else "✘ V11 발동"))
        L.append("■ 거부권")
        L.append("  " + "  ".join(
            f"{v}{'✘' if _f(r.get(v), 0) > 0 else '✔'}"
            for v in ("V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12")))
        L.append("─" * W)
        out.append("\n".join(L))
    txt = "\n\n".join(out)
    LOG.banner("진단 카드 — 최근 시점 상위 종목", f"{pd.Timestamp(m):%Y-%m} 기준 {len(sub)}종목")
    _safe_print(txt)
    return txt


def report_ledger_integrity(reports: pd.DataFrame, analysts: pd.DataFrame,
                            cov: pd.DataFrame) -> None:
    """원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목 연결이 제대로 됐는가.

    사용자 요구사항의 핵심 확인 항목이다. 연도×소스별로 연결률을 표로 낸다.
    """
    LOG.banner("원장 무결성 감사",
               "리포트 ↔ 애널리스트 ↔ 종목 연결. 다중소스가 하나의 원장으로 합쳐졌는가.")
    if reports is None or not len(reports):
        LOG.warn("리포트 원장이 비어 있습니다 — d2/d4 는 비활성화됩니다. "
                 "(드라이브 캐시 경로와 RESEARCH_COLLECT 설정을 확인하세요)")
        return
    r = reports.copy()
    r["연도"] = as_ts_series(r.get("pub_date")).dt.year
    r["소스"] = r.get("source", "").astype(str)
    g = r.groupby(["연도", "소스"], observed=True)
    tab = g.agg(건수=("report_uid", "size"),
                종목코드율=("stock_code", lambda s: float(s.notna().mean())),
                애널연결률=("analyst_raw", lambda s: float(
                    (s.astype(str).str.len() > 0).mean())),
                목표주가율=("target_price", lambda s: float(s.notna().mean()))).reset_index()
    LOG.table([[int(x["연도"]) if pd.notna(x["연도"]) else "?", x["소스"], f"{x['건수']:,}",
                f"{x['종목코드율']*100:5.1f}%", f"{x['애널연결률']*100:5.1f}%",
                f"{x['목표주가율']*100:5.1f}%"]
               for _, x in tab.tail(24).iterrows()],
              ["연도", "소스", "건수", "종목코드율", "애널연결률", "목표주가율"])
    LOG.info(f"애널리스트 원장 {0 if analysts is None else len(analysts):,}명 · "
             f"커버리지 패널 {0 if cov is None else len(cov):,} 종목월")
    ok_code = float(r["stock_code"].notna().mean())
    if ok_code < 0.5:
        LOG.warn(f"종목코드 연결률이 {ok_code*100:.0f}% 로 낮습니다. "
                 f"d2(커버리지 수)가 체계적으로 과소계상되며, 그 방향은 "
                 f"'커버리지가 적어 보이게' 하므로 U 를 인위적으로 높입니다. "
                 f"이 편의를 인지하고 R5 절제에서 D축 기여를 확인하세요.")


def report_dataflow_xcb() -> None:
    """데이터 흐름 지도 — 어느 스테이지에서 무엇이 들어오고 나가는가."""
    try:
        PIPE.report_flow()
    except Exception as e:                                              # noqa
        LOG.debug(f"데이터 흐름 지도 출력 실패: {type(e).__name__}")


def save_outputs_xcb(P: pd.DataFrame, bt: dict, abl: "Optional[pd.DataFrame]",
                     attr: "Optional[pd.DataFrame]", cards: str,
                     canary: "Optional[pd.DataFrame]", gates: dict) -> "List[str]":
    """§16 산출물 체크리스트를 실제 파일로 남긴다(전용 인덱스)."""
    out: List[str] = []
    d = VAULT.table_dir("private")

    def _w(name: str, obj, kind: str = "csv"):
        try:
            p = os.path.join(d, name)
            _ensure_dir(p)
            if kind == "csv" and obj is not None and len(obj):
                obj.to_csv(p, index=False, encoding="utf-8-sig")
            elif kind == "txt" and obj:
                atomic_write_text(p, str(obj))
            elif kind == "json":
                atomic_write_text(p, json.dumps(obj, ensure_ascii=False,
                                                indent=1, default=str))
            elif kind == "parquet" and obj is not None and len(obj):
                atomic_write_parquet(obj, p)
            else:
                return
            out.append(p)
        except Exception as e:                                          # noqa
            LOG.debug(f"산출물 저장 실패 {name}: {type(e).__name__}")

    _w("attrition.csv", attr)
    _w("r5_ablation.csv", abl)
    _w("canary_report.csv", canary)
    _w("card_sample.txt", cards, "txt")
    _w("policy_calendar_x.csv", pd.DataFrame(XCB_POLICY_CALENDAR))
    _w("robustness.json", ROBUST_LOG, "json")
    _w("mapping_gates.json", gates, "json")
    _w("runtime.csv", pd.DataFrame(RUNTIME_LOG))
    if bt and bt.get("returns") is not None:
        _w("backtest_returns.csv", bt["returns"])
        _w(f"backtest_{STAGE}.json", perf_stats(bt["returns"]), "json")
    if P is not None and len(P):
        keep = [c for c in P.columns if not str(c).startswith("_")]
        _w("panel.parquet", P[keep], "parquet")
    OUTPUT_FILES.extend(out)
    if out:
        LOG.banner("산출물", f"{len(out)}개 파일 → {d}")
        LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:,.0f}KB"] for p in out],
                  ["파일", "크기"])
    return out
