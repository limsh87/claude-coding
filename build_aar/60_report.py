

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — 성과검증표 / 격자표 / 해석표 / 유니버스 비교 / 최종판정 / 흐름지도           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PERF_ORDER = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
              "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
              "월평균회전율", "월평균비용", "현금비중"]
PERF_FMT = {"누적수익": "pct", "CAGR": "pct", "연변동성": "pct", "MDD": "pct", "승률": "pct",
            "현금비중": "pct", "월평균": "pctp", "월평균비용": "pctp", "월평균회전율": "num"}


def _fmt(k: str, v) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    f = PERF_FMT.get(k)
    if f == "pct":
        return f"{v*100:+.2f}%"
    if f == "pctp":
        return f"{v*100:+.3f}%p"
    if isinstance(v, float):
        return f"{v:,.3f}"
    return f"{v:,}"


def report_performance(bt: dict, bench: Dict[str, "pd.Series"], title: str = ""):
    LOG.banner(f"성과 검증 — {title or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 리밸런싱 · 익영업일 종가 체결 · "
               f"Q5 롱온리 동일가중 · 종목당 상한 {POS_MAX_WEIGHT:.0%}")
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return
    LOG.table([[k, _fmt(k, s.get(k))] for k in PERF_ORDER], ["지표", "값"], ["l", "r"],
              title="포트폴리오 성과")
    rows = bench_stats(bt["returns"], bench)
    if rows:
        LOG.table(rows, ["벤치마크", "벤치 누적", "전략 누적", "초과", "연환산 초과", "HAC t"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="벤치마크 대비 (§11 ACCEPT 조건: 동일가중 유니버스 대비 연 +3%p 이상)")
    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:,.3f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 — 소수 종목에 성과가 몰려 있는지")
        base, ex = rt.get("총기여"), rt.get("상위5% 제외 후")
        if base and ex is not None and base > 0 and ex <= 0:
            LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. 성과가 소수 종목에 "
                     "전적으로 의존합니다 — 실전에서 그 종목을 놓치면 전략 전체가 실패합니다.")


def report_grid(grid_stats: List[dict]):
    if not grid_stats:
        return
    rows = []
    for g in grid_stats:
        s = g["stats"]
        rows.append([g["label"], g["weight"], f"{g['lam']:g}", f"{g['hold']}M",
                     _fmt("CAGR", s.get("CAGR")), f"{s.get('Sharpe', np.nan):.3f}",
                     _fmt("MDD", s.get("MDD")), _fmt("월평균", s.get("월평균")),
                     f"{s.get('t통계량(HAC)', np.nan):.2f}", f"{s.get('평균종목수', np.nan):.1f}"])
    LOG.table(rows, ["구성", "가중", "λ", "보유", "CAGR", "Sharpe", "MDD", "월평균",
                     "HAC t", "평균종목"],
              ["l", "l", "c", "c", "r", "r", "r", "r", "r", "r"],
              title="§6.6 사전등록 파라미터 격자 12개 전체 결과 "
                    "(최고 성과만 보고하는 것을 막기 위해 전부 출력합니다)")
    sh = [g["stats"].get("Sharpe", np.nan) for g in grid_stats]
    sh = [x for x in sh if np.isfinite(x)]
    if sh:
        LOG.info(f"격자 Sharpe 분포 — 최소 {min(sh):.3f} / 중앙 {np.median(sh):.3f} / "
                 f"최대 {max(sh):.3f}. 최대값만 보고 판단하지 마십시오. "
                 f"DSR 은 이 시행횟수를 반영해 이미 할인되어 있습니다.")


def report_interpretation(S: "pd.DataFrame", V: "pd.DataFrame", drops: "pd.DataFrame"):
    LOG.banner("해석 참조표", "신호가 발화했을 때와 안 했을 때 각각 무슨 뜻인가")
    LOG.table([
        ["AAR_pos > 0", "애널리스트가 기계적 발간 요인을 넘어 **자발적으로** 이 종목에 "
                        "주의를 더 썼다", "검열될 수 없는 양(+) 신호"],
        ["AAR_pos < 0", "주의를 거둬들이는 중 (아직 커버는 유지)", "약한 음의 신호"],
        ["AAR_neg < 0", "직전 4분기 연속 커버하던 애널이 **재직 중인데** 이 종목만 끊었다",
         "한국에서 관측 가능한 사실상 유일한 부정적 정보 경로"],
        ["AAR_neg = 0", "철회 사건 없음 (커버 로스터 유지)", "중립 — 결측이 아니다"],
        ["M-EXIT", "담당자 이직·퇴사로 끊김. **종목에 대한 정보가 아니다**",
         "플라시보군 — 여기서 효과가 나오면 인과분해 실패"],
        ["HANDOFF", "하우스가 계속 커버하고 인원도 불변 (승계)", "철회가 아님 — 가중 0"],
    ], ["신호 상태", "의미", "해석"], ["l", "l", "l"], maxw=52)

    LOG.table([
        ["섹터중립", "SectorMonthFE 를 넣으므로 '반도체로 주의가 몰렸다' 같은 섹터 로테이션은 "
                     "신호에서 **완전히 제거**된다. 설계 의도다."],
        ["3개월 지연", "철회는 '3개월 침묵을 관측한 달'에 발화한다. 마지막 리포트로부터 "
                       "3개월 늦지만 그 시점에 100% 관측 가능하다(선견 없음)."],
        ["의견·목표주가 미사용", "매도의견 부재와 목표주가 상향 편향에 면역이다. "
                                 "목표주가는 H5 선행성 검정에만 쓴다."],
        ["대리변수", "컨센서스 EPS 는 역사적 복원이 불가능해 **목표주가 리비전**으로 대체했다. "
                     "H5 결과는 그 대리변수 대비 선행성으로만 해석해야 한다."],
    ], ["항목", "반드시 함께 읽어야 할 사실"], ["l", "l"], maxw=86,
        title="구조적 한계 — 숨기지 않고 명시합니다")

    if S is not None and len(S):
        q = S.groupby("month", observed=True).agg(
            n=("code", "size"), pos=("aar_pos", "mean"), neg=("aar_neg", "mean"),
            drop=("n_drop", "sum"))
        LOG.table([["신호 보유 종목-월", f"{len(S):,}"],
                   ["월평균 신호 종목수", f"{q['n'].mean():,.0f}"],
                   ["AAR_pos 평균", f"{float(S['aar_pos'].mean()):+.5f}"],
                   ["AAR_neg 평균", f"{float(S['aar_neg'].mean()):+.5f}"],
                   ["AAR_neg < 0 비중", f"{float((S['aar_neg']<0).mean())*100:.1f}%"],
                   ["철회 사건 총계", f"{int(q['drop'].sum()):,}"]],
                  ["항목", "값"], ["l", "r"], title="신호 분포 요약")


def report_universe_compare(results: Dict[str, dict]):
    """§10 — 전체 유니버스 vs 시총 하위 1000 비교."""
    if len(results) < 2:
        return
    LOG.banner("유니버스 변형 비교", "전체 PIT 유니버스 vs 시가총액 하위 1000 압축")
    rows = []
    for name, r in results.items():
        s = r.get("stats", {})
        rows.append([name, f"{s.get('월수', 0):,}", _fmt("CAGR", s.get("CAGR")),
                     f"{s.get('Sharpe', np.nan):.3f}", _fmt("MDD", s.get("MDD")),
                     _fmt("월평균", s.get("월평균")), f"{s.get('t통계량(HAC)', np.nan):.2f}",
                     f"{s.get('평균종목수', np.nan):.1f}",
                     _fmt("월평균회전율", s.get("월평균회전율"))])
    LOG.table(rows, ["유니버스", "월수", "CAGR", "Sharpe", "MDD", "월평균", "HAC t",
                     "평균종목", "회전율"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r"])
    try:
        a = results["FULL"]["bt"]["returns"]["ret"].fillna(0).to_numpy()
        b = results["SMALL1000"]["bt"]["returns"]["ret"].fillna(0).to_numpy()
        k = min(len(a), len(b))
        mu, t = hac_tstat(b[:k] - a[:k])
        LOG.info(f"SMALL1000 − FULL 월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). "
                 + ("소형주 압축이 신호를 강화합니다 — H4(저커버리지·소형주에서 강함) 예측과 "
                    "일치합니다." if mu > 0 else
                    "소형주 압축이 신호를 강화하지 못했습니다 — H4 예측과 어긋납니다."))
    except Exception:
        pass


def final_verdict(results: Dict[str, dict], hyp: "pd.DataFrame") -> str:
    """§11 수용/폐기 기준 — 사전 확정, 사후 변경 금지."""
    LOG.banner("최종 판정 (§11)", "사전 확정 기준 · 사후 변경 없음")

    def _h(hid: str) -> Optional[bool]:
        r = HYPO.get(hid)
        return None if not r else r.get("fdr_pass", r.get("pass"))

    def _r(rid: str) -> Optional[bool]:
        r = ROBUST.get(rid)
        return None if not r else r["pass"]

    main = results.get("FULL") or next(iter(results.values()), {})
    s = main.get("stats", {})
    bench_ok = None
    try:
        ew = main["bench"].get("동일가중유니버스")
        R = main["bt"]["returns"].set_index("month")["ret"].fillna(0)
        bb = pd.Series(ew).reindex(R.index).fillna(0)
        ann_ex = float((1 + (R - bb).mean()) ** 12 - 1)
        bench_ok = ann_ex >= 0.03
    except Exception:
        ann_ex = np.nan

    checks = [
        ("H1 (BH-FDR 후)", _h("H1"), "자발적 주의 증가의 양(+) 예측력"),
        ("H5 (BH-FDR 후)", _h("H5"), "컨센서스 개정 대비 선행성 — 경제적 정당성"),
        ("H2 (BH-FDR 후)", _h("H2"), "기회비용 가중이 비가중보다 강함"),
        ("R5 M-EXIT 플라시보", _r("R5"), "기계적 철회군에서 효과 없음"),
        ("R2 PBO < 0.5", _r("R2"), "과적합 위험"),
        ("R3 DSR > 0", _r("R3"), "시행횟수 보정 후 유의"),
        ("R10 나이브 대비 우위", _r("R10"), "통제·축소·분해의 가치"),
        ("동일가중 대비 연 +3%p", bench_ok, f"실측 연환산 초과 {ann_ex*100:+.2f}%p"),
    ]
    LOG.table([[n, {True: "✔ 충족", False: "✘ 미충족", None: "— 판정불가"}[v], d]
               for n, v, d in checks], ["ACCEPT 조건", "판정", "비고"], ["l", "c", "l"], maxw=56)

    h1 = _h("H1")
    h5 = _h("H5")
    r5 = _r("R5")
    r2 = _r("R2")
    r10 = _r("R10")

    if h1 is False or r2 is False or r5 is False or r10 is False:
        verdict = "KILL"
        why = []
        if h1 is False:
            why.append("H1 기각 — 자발적 주의 증가에 양의 예측력이 없습니다")
        if r2 is False:
            why.append("PBO ≥ 0.5 — 과적합 위험이 높습니다")
        if r5 is False:
            why.append("M-EXIT 플라시보 실패 — 인과분해가 성립하지 않습니다. "
                       "신호는 '커버리지 감소 = 소외주'의 재발견일 수 있습니다")
        if r10 is False:
            why.append("나이브(단순 건수증가) 대비 우위 없음 — 통제회귀·축소추정·인과분해가 "
                       "불필요한 복잡도입니다")
        reason = " / ".join(why)
    elif h1 is True and h5 is False:
        verdict = "CONDITIONAL"
        reason = ("H1 은 통과했으나 H5(선행성)가 실패했습니다. 이 신호는 컨센서스 개정의 "
                  "느린 대리변수일 가능성이 큽니다. §11 에 따라 **독립 배분을 금지**하고 "
                  "기존 개정 팩터와의 상관 분석만 수행하십시오.")
    elif all(v is True for v in (h1, h5, _h("H2"), r5, r2, _r("R3"), r10)) and bench_ok:
        verdict = "ACCEPT"
        reason = "사전 확정된 ACCEPT 조건을 모두 충족했습니다."
    else:
        verdict = "INCONCLUSIVE"
        pend = [n for n, v, _ in checks if v is None]
        reason = ("판정불가 항목이 남아 있어 ACCEPT 도 KILL 도 선언할 수 없습니다: "
                  + ", ".join(pend) + ". 표본 부족을 '통과'로 읽지 않기 위해 "
                  "의도적으로 미판정으로 둡니다.")

    icon = {"ACCEPT": "✔", "CONDITIONAL": "⚠", "KILL": "⛔", "INCONCLUSIVE": "—"}[verdict]
    LOG.banner(f"{icon} 최종 판정: {verdict}", _trunc(reason, 100))
    if len(reason) > 100:
        _safe_print("  " + reason)
    LOG.info("이 판정은 §11 의 사전 확정 기준을 기계적으로 적용한 결과입니다. "
             "기준을 사후에 바꿔 통과시키지 마십시오 — 그것이 이 프로젝트에서 가장 "
             "해로운 행동입니다(§13).")
    return verdict


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────┐
  │  환경감지 → 의존성 → 드라이브 마운트 → VAULT (공용/전용 인덱스, append-only 저널)    │
  │   ├ HTTP 응답 캐시 : 같은 URL+파라미터는 두 번 다시 네트워크에 나가지 않음            │
  │   ├ 메모 캐시      : 입력 지문이 같으면 계산 자체를 건너뜀                            │
  │   └ adopt_scan     : 기존 캐시를 '이동 없이 참조 등록'                                │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │  marcap (연도 parquet 11개)  →  일별 수정수익률 · 월말 단면 · 종목 마스터              │
  │     └ PIT 시총 · 상장주식수 · 실거래대금 · 생존자편향 구조적 제거를 한 번에            │
  │  DART list.json 스윕        →  실적발표월 · 월별 공시건수 (통제변수 2개뿐)             │
  │  한경컨센서스 + 네이버      →  리포트 원장 → 애널리스트 원장 → 인물 추적(이직)         │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼   모든 테이블은 pit_frame() 통과
  ┌── L2 신호 ────────────────────────────────────────────────────────────────────────────┐
  │  주의 패널 (분수배분·합집합채움·셀단위 결측)                                            │
  │      → EA = share − base            (해석적 분산 v 동반)                               │
  │      → 경험적베이즈 축소 (tau² 3단 계층, 자유도 0)          ← 확장창 [t0,t]             │
  │      → §6.3 통제회귀 잔차 = VAS      (섹터×월 FE + 애널 FE)  ← 확장창 [t0,t]             │
  │  커버리지 철회 분류 → V-DROP / H-EXIT / HANDOFF / M-EXIT / CENSORED-*                  │
  │      → AAR_pos (ω 가중 집계)  ·  AAR_neg (−Σw/로스터, 유계)                            │
  │      → AAR_total = z(pos) + λ·z(neg)      ★ 결측은 채우지 않고 유니버스를 제한          │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L3 백테스트 → L5 검정 → L6 리포트 ──────────────────────────────────────────────────┐
  │  5분위 → Q5 롱온리 동일가중 → AAR_neg 하위10% 배제 → 하한 20종목                       │
  │  익영업일 종가 체결 · 폐지 승계/전손 분기 · 연도별 거래세                               │
  │  H1~H5 (BH-FDR) → R1 부트스트랩 → R2 PBO → R3 DSR → R4 워크포워드                      │
  │  → R5 M-EXIT 플라시보⭐ → R6 CAR → R7 비용 → R8 누수 → R9 레짐 → R10 나이브⭐          │
  │  × 유니버스 2종 (전체 / 시총하위1000)                                                   │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f       # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML     # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")
