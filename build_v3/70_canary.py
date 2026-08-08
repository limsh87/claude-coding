

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-K  CANARY K1~K6 (§2)                                                                  ║
# ║                                                                                          ║
# ║  본 수집을 시작하기 전에 '작은 표본'으로 각 데이터원이 살아 있는지 실측한다.               ║
# ║  하나라도 FAIL 이면 그 항목에 의존하는 단계를 제거하고, 무엇을 어떻게 조치했는지           ║
# ║  표 상단에 먼저 출력한다. 조용히 넘어가지 않는다.                                          ║
# ║                                                                                          ║
# ║  ★ K5(상장폐지 목록) 실패는 킬 기준이다 — C2(생존자편향 제거)가 불가능해지기 때문이다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY: List[dict] = []


def _k(kid: str, item: str, passed: Optional[bool], measured: str, action: str = ""):
    CANARY.append({"id": kid, "item": item, "passed": passed,
                   "measured": measured, "action": action})
    icon = "—" if passed is None else ("PASS" if passed else "FAIL")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.warn))(
        f"[{kid}] {icon} {item} — {measured}" + (f" → {action}" if action else ""))


def run_canary(sec: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, bool]:
    """K1~K6 실측. 반환: 기능별 활성 여부 딕셔너리."""
    LOG.banner("CANARY K1~K6", "본 수집 전 소표본 실측 — FAIL 항목은 의존 단계를 제거하고 보고한다")
    CANARY.clear()
    caps = {"dart_fin": False, "dart_bulk": False, "price": False,
            "delisting": False, "watchlist": False}

    codes = [c for c in sec["code"].dropna().astype(str).tolist()][:200] if len(sec) else []
    ccs = (sec.dropna(subset=["corp_code"])["corp_code"].astype(str).tolist()[:60]
           if "corp_code" in sec.columns else [])

    # ── K1 · K2 : DART 재무 취득 가능성과 최초 제공 분기 ──────────────────────────────────
    if not DART_API_KEY:
        _k("K1", "DART 재무 취득", False, "DART_API_KEY 미입력",
           "재무 의존 항목(E층·방화벽 재무조항) 전면 비활성. 드라이브 캐시가 있으면 그것만 사용")
        _k("K2", "최초 제공 분기", None, "K1 미충족으로 미검사")
        _k("K3", "필수 계정 커버리지", None, "K1 미충족으로 미검사")
    else:
        smp = ccs[:12]
        got = pd.DataFrame()
        try:
            got = fetch_dart_financials(smp, [2016]) if smp else pd.DataFrame()
        except Exception as e:                                         # noqa
            LOG.debug(f"K1 표본 조회 실패: {type(e).__name__}")
        n1 = len(got)
        ok1 = n1 > 0
        caps["dart_fin"] = ok1
        _k("K1", "DART 재무 2016 표본 취득", ok1,
           f"표본 {len(smp)}사 → {n1:,}행",
           "" if ok1 else "fnlttMultiAcnt 배치 폴백으로 전환 (코드가 자동 처리)")

        # K2 — 2016Q1 이전 데이터가 실제로 오는지
        if ok1 and "bsns_year" in got.columns:
            yrs = pd.to_numeric(got["bsns_year"], errors="coerce").dropna()
            ymin = int(yrs.min()) if len(yrs) else 9999
            ok2 = ymin <= 2016
            _k("K2", "최초 제공 연도 ≤ 2016", ok2, f"실측 최초 연도 {ymin}",
               "" if ok2 else f"백테스트 시작을 {ymin}년으로 상향해야 합니다")
        else:
            _k("K2", "최초 제공 연도 ≤ 2016", None, "표본 없음")

        # K3 — 필수 계정 커버리지
        if ok1:
            try:
                W = tidy_financials(got)
                need = {"revenue": "매출", "cogs": "매출원가", "inventory": "재고",
                        "receivable": "매출채권", "cfo": "영업CF",
                        "tax_expense": "법인세비용", "interest_expense": "이자비용"}
                rows, bad = [], []
                for k, nm in need.items():
                    covg = float(W[k].notna().mean()) if k in W.columns and len(W) else 0.0
                    rows.append([nm, f"{100*covg:.0f}%", "PASS" if covg >= 0.80 else "FAIL"])
                    if covg < 0.80:
                        bad.append(nm)
                LOG.table(rows, ["계정", "커버리지", "판정"], ["l", "r", "c"],
                          title="K3 — 필수 계정 커버리지 (표본 기준)")
                _k("K3", "필수 계정 커버리지 ≥80%", len(bad) == 0,
                   f"미달 {len(bad)}개: {bad[:5]}" if bad else "전 계정 충족",
                   "미달 계정을 쓰는 지표는 결측으로 남습니다(0 으로 채우지 않음)" if bad else "")
            except Exception as e:                                     # noqa
                _k("K3", "필수 계정 커버리지", None, f"정제 실패 {type(e).__name__}")

    # ── K4 : 가격 취득 ────────────────────────────────────────────────────────────────────
    smp_px = codes[:25]
    px = pd.DataFrame()
    if smp_px and RUN_MODE != "CACHED":
        try:
            px = fetch_prices(smp_px, BACKTEST_START, BACKTEST_END)
        except Exception as e:                                         # noqa
            LOG.debug(f"K4 표본 가격 실패: {type(e).__name__}")
    n_ok = int(px["code"].nunique()) if len(px) else 0
    ok4 = n_ok >= max(1, int(0.6 * len(smp_px)))
    caps["price"] = ok4 or RUN_MODE == "CACHED"
    _k("K4", "가격 10년 취득", ok4 if smp_px else None,
       f"표본 {len(smp_px)}종목 중 {n_ok}종목 성공" if smp_px else "표본 없음",
       "" if ok4 else "FDR→네이버→yfinance→캐시 순으로 자동 폴백합니다")

    # ── K5 : 상장폐지 목록 (킬 기준) ──────────────────────────────────────────────────────
    n_del = int(sec["delisting_date"].notna().sum()) if "delisting_date" in sec.columns else 0
    ok5 = n_del > 0
    caps["delisting"] = ok5
    _k("K5", "상장폐지 목록 확보 ⭐", ok5, f"폐지일 보유 {n_del:,}종목",
       "" if ok5 else "C2(생존자편향 제거) 불가 — 킬 기준")
    if not ok5 and STOP_ON_KILL_CRITERIA and RUN_MODE == "FULL":
        raise KillCriteria(
            "상장폐지 목록을 확보하지 못했습니다(K5). 생존자편향을 제거할 수 없으므로 "
            "중단합니다(§12-1). 살아남은 종목만으로 낸 수익률은 실제로 달성 불가능한 값입니다.")

    # ── K6 : 관리종목·감사의견 이력 ──────────────────────────────────────────────────────
    ok6 = None
    if DART_API_KEY and RUN_MODE != "CACHED":
        try:
            probe_start = str(pd.Timestamp(BACKTEST_END) - pd.DateOffset(months=2))[:10]
            act = fetch_market_actions(probe_start, BACKTEST_END)
            ok6 = len(act) > 0
            caps["watchlist"] = bool(ok6)
            _k("K6", "관리종목·감사의견 이력", ok6, f"최근 2개월 이벤트 {len(act):,}건",
               "" if ok6 else "방화벽의 관리종목/감사의견/거래정지 조항을 비활성화하고 진행")
        except Exception as e:                                         # noqa
            _k("K6", "관리종목·감사의견 이력", False, f"조회 실패 {type(e).__name__}",
               "해당 방화벽 조항 비활성화")
    else:
        _k("K6", "관리종목·감사의견 이력", None,
           "DART 키 미입력 또는 CACHED 모드", "캐시에 있으면 사용합니다")

    # ── 요약표 (FAIL 을 맨 위로) ──────────────────────────────────────────────────────────
    order = sorted(CANARY, key=lambda r: (r["passed"] is not False, r["id"]))
    LOG.table([[r["id"], _trunc(r["item"], 30),
                "—" if r["passed"] is None else ("PASS" if r["passed"] else "★FAIL"),
                _trunc(r["measured"], 34), _trunc(r["action"], 40)] for r in order],
              ["ID", "확인 항목", "판정", "실측", "FAIL 시 조치"],
              ["c", "l", "c", "l", "l"], maxw=44,
              title="CANARY 실측 결과 (FAIL 항목을 위로 정렬)")
    n_fail = sum(1 for r in CANARY if r["passed"] is False)
    if n_fail:
        LOG.warn(f"CANARY {n_fail}건 FAIL — 위 '조치' 열대로 해당 단계를 제거하고 진행합니다. "
                 f"임계를 낮춰 통과시키지 않습니다.")
    else:
        LOG.ok("CANARY 전 항목 통과.")
    return caps


def write_canary_report(path: str) -> Optional[str]:
    if not CANARY:
        return None
    lines = ["# CANARY 실측 보고 (TCD v3 · MICRO-FW)", "",
             f"- 생성: {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
             f"- 백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
             "| ID | 확인 항목 | 판정 | 실측 | 조치 |", "|---|---|---|---|---|"]
    for r in sorted(CANARY, key=lambda x: (x["passed"] is not False, x["id"])):
        v = "—" if r["passed"] is None else ("PASS" if r["passed"] else "**FAIL**")
        lines.append(f"| {r['id']} | {r['item']} | {v} | {r['measured']} | {r['action']} |")
    try:
        atomic_write_text(path, "\n".join(lines) + "\n")
        return path
    except Exception:
        return None
