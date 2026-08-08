# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  [0] 캐시 연결 → [1] 계약 → [2] 스모크 → [3] 리허설 → [4] CANARY → [5] 수집               ║
# ║  → [6] 원장감사 → [7] 패널/신호 → [8] 백테스트·성과 → [9] 강건성 → [10] 해석·산출물        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f                # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                        f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def preflight_estimate(n_codes: int, n_flow_targets: int, n_corps: int, n_years: int) -> None:
    """수집을 시작하기 '전에' 예상 소요시간을 계산해 보여준다(§9 — 추측 말고 계측).

    4시간 하드 제약을 넘길 것 같으면, 어떤 손잡이를 어떻게 돌려야 하는지까지 같이 출력한다.
    (실행을 2시간 하고 나서 '아 이거 안 끝나겠다'를 깨닫는 것이 가장 비싼 실패다)"""
    qps = lambda k: max(0.1, float(RATE_LIMIT_QPS.get(k, 3.0)))
    est = []
    px_req = n_codes                      # 종목당 1회(증분이면 그보다 적다)
    est.append(("가격 일봉", px_req, qps("naver"), px_req / qps("naver") / 60))
    fl_pages = n_flow_targets * 9         # 10년 ≈ pageSize 300 × 9페이지
    est.append(("투자자 수급(네이버)", fl_pages, qps("naver"), fl_pages / qps("naver") / 60))
    ds_req = min(DART_SHARES_MAX_CALLS or 10 ** 9, n_corps * n_years)
    est.append(("DART 주식총수", ds_req, qps("dart"), ds_req / qps("dart") / 60))
    total = sum(x[3] for x in est)
    LOG.table([[n, f"{r:,}", f"{q:.1f}/s", f"{m:.0f}분"] for n, r, q, m in est] +
              [["── 합계(캐시 미보유 최악)", "", "", f"{total:.0f}분"]],
              ["수집 단계", "예상 요청수", "속도상한", "예상 소요"], ["l", "r", "r", "r"],
              title="수집 프리플라이트 — 시작 전에 끝나는지 먼저 계산한다(§9)")
    if total > 210:
        LOG.warn(f"예상 {total:.0f}분으로 4시간 예산에 근접/초과합니다. 손잡이는 셋입니다: "
                 f"① FLOW_MAX_CODES 를 {max(200, n_flow_targets//2):,} 로 낮추기 "
                 f"② RATE_LIMIT_QPS['naver'] 를 올리기(차단 위험과 교환) "
                 f"③ 오늘은 여기까지 받고 재실행 — 캐시는 누적되므로 다음 실행이 그만큼 짧아집니다.")
    else:
        LOG.ok(f"예상 {total:.0f}분 — 4시간 예산 내입니다(캐시가 있으면 더 짧아집니다).")


# ═══ CANARY (§2) ════════════════════════════════════════════════════════════════════════════
def run_canary(sec: pd.DataFrame, delisted: pd.DataFrame, sample_n: int = 200) -> None:
    """코드가 아니라 '데이터의 등급'을 먼저 확정한다. 여기서 실패한 것은 나중에도 실패한다.

    ★ 표본 수집물은 전부 공용 인덱스 캐시를 통과하므로, 본 수집 단계에서 그대로 재사용된다
      (카나리 때문에 같은 데이터를 두 번 받지 않는다)."""
    codes = sec["code"].dropna().tolist()
    sample = codes[:sample_n]

    # K5 — 상장폐지 목록 (이 전략의 생명선)
    n_del = int(delisted["delisting_date"].notna().sum()) if len(delisted) else 0
    in_range = 0
    if len(delisted):
        d = as_ts_series(delisted["delisting_date"])
        in_range = int(((d >= as_ts(BACKTEST_START)) & (d <= as_ts(BACKTEST_END))).sum())
    prov = ""
    if len(delisted) and "delisting_src" in delisted.columns:
        vc = delisted["delisting_src"].value_counts().to_dict()
        prov = " · 근거=" + ", ".join(f"{k}:{v:,}" for k, v in vc.items())
    canary("K5", "상장폐지 목록 (생존자편향 제거)", n_del > 0 and in_range > 50,
           f"폐지일 보유 {n_del:,}종목 · 백테스트 구간 내 폐지 {in_range:,}건{prov}",
           "" if in_range > 50 else "§11-1 킬 기준 — 상폐를 못 넣으면 이 전략의 성과는 무효")

    # K4 — 가격
    px_have = 0
    cached_px = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if cached_px is not None and len(cached_px):
        px_have = int(cached_px["code"].nunique())
    canary("K4", "10년 일봉 (FDR/pykrx/네이버/yf 체인)", px_have > 0,
           f"공용 캐시 보유 {px_have:,}종목" + ("" if px_have else " — 이번 실행에서 신규 수집"),
           "" if px_have else "가격 체인이 전부 실패하면 실행 자체가 불가")

    # F2 — 투자자유형별 순매수
    fl = VAULT.get_table("krx_investor_flows_daily", scope="shared")
    n_fl = int(fl["code"].nunique()) if fl is not None and len(fl) else 0
    has_retail = bool(fl is not None and len(fl) and "retail_net" in fl.columns
                      and fl["retail_net"].notna().any())
    if n_fl == 0 and RUN_MODE != "CACHED":
        probe = fetch_investor_flows_daily(sample[:20], BACKTEST_START, BACKTEST_END)
        n_fl = int(probe["code"].nunique()) if len(probe) else 0
        has_retail = bool(len(probe) and probe["retail_net"].notna().any())
    canary("F2", "투자자유형별 일별 순매수 (개인/기관/외국인)", n_fl > 0 and has_retail,
           f"{n_fl:,}종목 · 개인 분해 {'있음' if has_retail else '없음'}",
           "" if (n_fl and has_retail) else "§11-2 킬 기준 — 소유권 이전 관측 불가")

    # F1 — 신용융자잔고 (등급은 수집 단계에서 확정되지만, 가용성은 여기서 미리 본다)
    cr = VAULT.get_table("krx_credit_balance_daily", scope="shared")
    n_cr = int(cr["code"].nunique()) if cr is not None and len(cr) else 0
    manual_dirs = [d for d in CREDIT_MANUAL_DIRS if d and os.path.isdir(d)]
    canary("F1", "종목별 신용융자잔고 ★이 전략의 핵심", n_cr > 0 or bool(manual_dirs) or KRX.session_ok,
           f"캐시 {n_cr:,}종목 · 수동폴더 {len(manual_dirs)}개 · KRX모드 {KRX_MODE} · "
           f"세션 {'있음' if KRX.session_ok else '없음'}",
           "없으면 Fallback A(주간) → B(프록시). B는 리포트에 반드시 명시")

    # F3 — 단위·정의
    unit = "미확인"
    if cr is not None and len(cr):
        med = float(pd.to_numeric(cr["credit_bal"], errors="coerce").median())
        unit = ("금액(원)" if med > 1e6 else "수량(주) 의심")
        canary("F3", "신용잔고 단위·정의 (금액 vs 수량)", med > 1e6,
               f"중앙값 {med:,.0f} → {unit}",
               "" if med > 1e6 else "수량이면 시총 대비 비율이 왜곡됨 — 단가 곱셈 필요")
    else:
        canary("F3", "신용잔고 단위·정의", None, "잔고 미확보로 판정 보류", "수집 후 자동 재판정")

    # K1 — DART 재무
    fin = VAULT.get_table("dart_financials", scope="shared")
    n_fin = len(fin) if fin is not None else 0
    canary("K1", "DART 재무 (방화벽 입력)", bool(DART_API_KEY) or n_fin > 0,
           f"키 {'있음' if DART_API_KEY else '없음'} · 캐시 {n_fin:,}행",
           "" if (DART_API_KEY or n_fin) else "방화벽 대부분 비활성 — 단일 실패모드 노출")

    # K6 — 관리종목·거래정지
    wl = VAULT.get_table("krx_watchlist_events", scope="shared")
    canary("K6", "관리종목·투자주의·거래정지", wl is not None and len(wl) > 0,
           f"캐시 {0 if wl is None else len(wl):,}행",
           "없으면 방화벽 해당 조항만 비활성화하고 로깅")

    # F4 — 전환청구권행사 공시 (M3 선택)
    dis = VAULT.get_table("dart_disclosures", scope="shared")
    n_cb = 0
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        n_cb = int(dis["report_nm"].astype(str).str.contains("전환청구권|전환가액").sum())
    canary("F4", "전환청구권행사 공시 (M3 이벤트)", n_cb > 0,
           f"캐시 내 {n_cb:,}건", "없으면 M3 이벤트 트리거 비활성 (전략 본체는 정상 동작)")

    report_canary()

    if STOP_ON_KILL_CRITERIA:
        if CANARY.get("K5", {}).get("pass") is False:
            raise KillCriteria("K5 FAIL — 상장폐지 목록 미확보. 이 전략에서 C2 위반은 치명적입니다(§11-1). "
                               "생존자편향이 남은 성과는 전부 무효이므로 여기서 중단합니다.")
        if CANARY.get("F2", {}).get("pass") is False:
            raise KillCriteria("F2 FAIL — 투자자유형별 순매수 미취득. '소유권 이전'을 관측할 수 "
                               "없으므로 이 전략의 절반이 성립하지 않습니다(§11-2).")


# ═══ 수집 ═══════════════════════════════════════════════════════════════════════════════════
def collect_all(weeks: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}
    months = pd.date_range(as_ts(BACKTEST_START) - pd.DateOffset(months=15),
                           as_ts(BACKTEST_END), freq="ME")

    with PIPE.stage("L1.UNI", "종목 마스터 · 다중소스 발굴 (C2)", "L1", budget_s=900):
        snaps = fetch_listing_snapshots_guarded(months)
        sec = build_security_master(snaps)
        # ★ KRX 가 막혀도 유니버스가 얇아지지 않도록 코드 발굴을 다중소스 합집합으로 넓힌다
        sec = discover_codes_multi(sec)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금 (M0)", "L1", budget_s=2700):
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px

    with PIPE.stage("L1.UNIFIX", "상장/폐지 창 재구성 (KRX 없이 C2 성립)", "L1", budget_s=300):
        # 거래가 있었다는 사실 자체가 상장의 증거다. 명부가 없으면 가격이력으로 창을 복원한다.
        ctx["sec"] = reconstruct_listing_windows(ctx["sec"], ctx["px"], BACKTEST_END)
        ctx["delisted"] = (ctx["sec"][["code", "name", "delisting_date", "delisting_src"]]
                           .dropna(subset=["delisting_date"]))
        ctx["surv_cov"] = audit_survivorship_coverage(ctx["sec"], ctx["px"],
                                                      BACKTEST_START, BACKTEST_END)
        VAULT.put_table("security_master_pit", ctx["sec"], scope="shared", domain="universe",
                        source="multi-source + price reconstruction",
                        extra={"note": "상장/폐지 창 + 출처(provenance) — 전 전략 공용"})

    with PIPE.stage("L0.CANARY", "CANARY F1~F4 · K1~K6 (§2)", "L0", budget_s=1500):
        if krx_allowed():
            KRX.login()
        run_canary(ctx["sec"], ctx["delisted"])

    with PIPE.stage("L1.FLOW", "투자자유형별 일별 순매수 (M0)", "L1", budget_s=2400, critical=False):
        targets = select_flow_targets(ctx["px"], BACKTEST_START, BACKTEST_END)
        ctx["flow_targets"] = targets
        _yrs = max(1, as_ts(BACKTEST_END).year - as_ts(BACKTEST_START).year + 3)
        preflight_estimate(len(ctx["sec"]), len(targets),
                           int(ctx["sec"]["corp_code"].notna().sum()), _yrs)
        ctx["flows"] = fetch_investor_flows_daily(targets or ctx["sec"]["code"].tolist(),
                                                  BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.SHARES", "상장주식수 (DART 주식총수 우선 · PIT)", "L1", budget_s=1200,
                    critical=False):
        # 유동성 순으로 우선순위를 준다 — 호출 상한에 걸려도 '살 수 있는 종목'부터 채워진다
        _years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        _amt = (ctx["px"].groupby("code", observed=True)["amount"].median()
                .sort_values(ascending=False))
        _c2c = (ctx["sec"].dropna(subset=["corp_code"])
                .set_index("code")["corp_code"].astype(str).to_dict())
        _corps = [_c2c[c] for c in _amt.index if c in _c2c]
        _corps += [c for c in ctx["sec"]["corp_code"].dropna().astype(str).unique()
                   if c not in set(_corps)]
        if DART_SHARES_MAX_CALLS and len(_corps) * len(_years) > DART_SHARES_MAX_CALLS:
            keep_n = max(1, DART_SHARES_MAX_CALLS // max(len(_years), 1))
            LOG.warn(f"DART 주식총수 호출 예상 {len(_corps)*len(_years):,}건이 상한 "
                     f"{DART_SHARES_MAX_CALLS:,}건을 초과 → 유동성 상위 {keep_n:,}사만 받습니다. "
                     f"나머지 종목의 시총 분모는 '거래대금 20일합' 대리로 대체되며, "
                     f"f_cr 은 자기이력 백분위라 스케일 차이에 둔감합니다.")
            _corps = _corps[:keep_n]
        ctx["dart_shares"] = fetch_dart_shares(_corps, _years)
        ctx["shares"] = fetch_shares_outstanding(months, sec=ctx["sec"],
                                                 dart_shares=ctx.get("dart_shares"))

    with PIPE.stage("L1.CREDIT", "신용융자잔고 ★핵심 (M1)", "L1", budget_s=2400, critical=False):
        ctx["credit"] = fetch_credit_balance(ctx["px"], ctx.get("flows", pd.DataFrame()),
                                             BACKTEST_START, BACKTEST_END)
        # F1/F3 카나리를 실측으로 갱신한다(추측 금지)
        canary("F1", "종목별 신용융자잔고 ★이 전략의 핵심",
               CREDIT_GRADE in ("PRIMARY_DAILY", "FALLBACK_A_WEEKLY"),
               f"등급 {CREDIT_GRADE} · {CREDIT_SOURCE_NOTE}",
               "PRIMARY 아니면 결과 해석 시 신뢰도 하향")

    with PIPE.stage("L1.DART", "DART 재무 · 공시 (M2 방화벽)", "L1", budget_s=2400, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        if corps and DART_API_KEY:
            multi = fetch_dart_multi_accounts(corps, years)
            fs = fetch_dart_financials(corps, years)
            fin = tidy_financials(merge_financial_tiers(fs, multi))
            if len(fin):
                PIT.register("dart_financials", fin, key_cols=["corp_code"])
            ctx["fin"] = fin
            ctx["disclosures"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        else:
            # ★ 키가 없다고 '드라이브에 이미 있는 DART 캐시'까지 버리면 안 된다.
            #   v2 전략들이 공용 인덱스에 쌓아둔 재무·공시가 그대로 재사용 가능하다.
            #   (수집 함수는 키 검사에서 먼저 빠져나가므로 여기서 직접 읽는다)
            cf = VAULT.get_table("dart_financials", scope="shared")
            cd = VAULT.get_table("dart_disclosures", scope="shared")
            if cf is not None and len(cf):
                need_pit = [c for c in ("event_date", "knowledge_date") if c not in cf.columns]
                if not need_pit:
                    PIT.register("dart_financials", cf, key_cols=["corp_code"])
                    LOG.ok(f"★ DART 키가 없지만 공용 인덱스의 재무 캐시 {len(cf):,}행을 "
                           f"재사용합니다 — 방화벽이 살아납니다.")
                else:
                    LOG.warn(f"공용 재무 캐시에 PIT 컬럼 {need_pit} 이 없어 사용할 수 없습니다.")
            if cd is not None and len(cd):
                LOG.ok(f"★ 공용 인덱스의 공시 캐시 {len(cd):,}행 재사용 — V1 거부권이 살아납니다.")
            ctx["fin"] = cf if cf is not None else pd.DataFrame()
            ctx["disclosures"] = cd if cd is not None else pd.DataFrame()
            if (cf is None or not len(cf)) and (cd is None or not len(cd)):
                LOG.warn("DART_API_KEY 미입력 + 공용 캐시도 비어 있음 — 방화벽(자본잠식·영업CF)과 "
                         "V1/V3 거부권이 비활성화됩니다. 이 전략의 단일 실패모드가 그대로 "
                         "노출되므로 키 입력을 강력히 권합니다.")

    with PIPE.stage("L1.WATCH", "관리종목 · 거래정지 (K6)", "L1", budget_s=300, critical=False):
        ctx["watch"] = fetch_watchlist_halt(ctx["sec"])

    # ※ PIPE.stage(skip_if=...) 는 스테이지를 SKIP 으로 기록하지만 본문 실행까지 막지는
    #    못한다(컨텍스트매니저가 yield 하므로 with 본문은 그대로 돈다).
    #    그래서 '끄기'는 반드시 호출부의 조건 분기로 구현한다.
    if RESEARCH_USE:
        with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장 (한경/네이버)", "L1",
                        budget_s=3600, critical=False):
            LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                     "지시에 따라 수집하되 보수적 속도로 제한합니다. 원문은 로컬 분석 용도로만.")
            cached = VAULT.get_table("research_report_master", scope="shared")
            frames = []
            if cached is not None and len(cached):
                LOG.ok(f"★ 구글드라이브 공용 인덱스에서 리포트 원장 {len(cached):,}건 재사용 "
                       f"(재수집하지 않습니다)")
                frames.append(cached)
            if RUN_MODE == "FULL" and RESEARCH_COLLECT:
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
                if "naver" in RESEARCH_SOURCES:
                    nv = naver_collect(BACKTEST_START, BACKTEST_END)
                    frames.append(naver_enrich_detail(nv))
            rep = build_report_master(frames, ctx["sec"])
            if len(rep):
                if RESEARCH_DOWNLOAD_PDF:
                    rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
                VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                                source="hankyung+naver")
            A, L = build_analyst_ledger(rep)
            if len(A):
                VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                                source="entity_resolution")
                VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                                source="entity_resolution")
            ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    else:
        LOG.warn("RESEARCH_USE=False — 애널리스트 리포트 오버레이(V_RS 거부권·해석표 커버리지)를 "
                 "사용하지 않습니다. 드라이브에 캐시가 있어도 읽지 않습니다.")
    # ★ 비필수(critical=False) 스테이지가 실패하면 그 산출물 키가 없다. 하류에서
    #   ctx["flows"] 로 읽으면 '수급 실패'가 엉뚱하게 '신용잔고 스테이지의 KeyError' 로
    #   보고된다 — 실패 지점이 흐려지는 것이 가장 나쁘다. 여기서 한 번에 기본값을 못박는다.
    for _k in ("flows", "shares", "credit", "watch", "disclosures", "fin", "dart_shares",
               "reports", "analysts", "links"):
        ctx.setdefault(_k, pd.DataFrame())
    return ctx


def build_signal_panel(ctx: dict, weeks: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe"]:
    with PIPE.stage("L2.PANEL", "일별 센서 → 주간 패널 → 국면 → TP → 신호", "L2", budget_s=2400):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
            columns=["snap_date", "code", "market"])), ctx["px"])
        P = build_flp_panel(ctx["px"], ctx.get("credit", pd.DataFrame()),
                            ctx.get("flows", pd.DataFrame()), ctx.get("shares", pd.DataFrame()),
                            weeks, uni)
        if P.empty:
            raise RuntimeError("주간 패널이 비었습니다 — 가격 또는 유니버스 수집을 확인하세요.")
        P = apply_universe_bands(P)
        P = build_cells_flp(P, ctx["sec"])
        P = classify_phase(P)
        P = attach_fundamentals_flp(P, ctx["sec"])
        P = apply_firewall(P, ctx.get("watch", pd.DataFrame()), ctx)
        ctx["research_panel"] = build_research_panel(ctx.get("links", pd.DataFrame()), P, weeks)
        P = apply_vetoes(P, ctx)
        P = build_tps(P)
        P = assemble_score(P)
        P = downcast(P)
        audit_research_wiring(ctx.get("reports", pd.DataFrame()),
                              ctx.get("analysts", pd.DataFrame()),
                              ctx.get("links", pd.DataFrame()), P)
    return P, uni


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 · 전략 8 — {STRATEGY_NAME}",
               f"{BACKTEST_START}~{BACKTEST_END} · 주 1회 리밸런싱 · 빌드 {BUILD_VERSION}")
    LOG.info("이 전략은 알파가 아니라 '위험 프리미엄'입니다(§0). 위기 국면에 전 포지션이 "
             "동시에 손실납니다 — R12 에서 그 크기를 직접 측정합니다.")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["KRX 모드", f"{KRX_MODE} " + ("(차단 대응: 비KRX 스파인 사용)"
                                             if KRX_MODE.upper() == "OFF" else "")],
               ["KRX 자격증명", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW) else "미입력"],
               ["DART 키", "입력됨" if DART_API_KEY else "미입력"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root} (모드 {mode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유 (가격·수급·신용·리포트)")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유 (패널·신호·백테스트)")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
        VAULT.load_index("shared"); VAULT.load_index("private")
        # ★ 흡수 경로 자동 확장: 설정값이 다른 OS 의 경로(/content/...)뿐이면 아무것도 못 찾고
        #   "경로를 확인하세요" 경고만 남는다. 실제로 존재하는 경로만 추리고, 하나도 없으면
        #   캐시 루트 자신과 그 상위의 흔한 리포트 폴더를 후보로 넣는다.
        _adopt = [d for d in GDRIVE_ADOPT_DIRS if d and os.path.isdir(d)]
        _extra = [VAULT.root, os.path.join(VAULT.root, "reports"),
                  os.path.join(VAULT.root, "research"),
                  os.path.join(os.path.dirname(VAULT.root), "research"),
                  os.path.join(os.path.dirname(VAULT.root), "reports")]
        for _d in _extra:
            if os.path.isdir(_d) and _d not in _adopt:
                _adopt.append(_d)
        if _adopt:
            LOG.info(f"기존 파일 흡수 대상 {len(_adopt)}개 경로: "
                     + ", ".join(os.path.basename(d) or d for d in _adopt[:5]))
        VAULT.adopt_scan(_adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=600,
                    critical=False):
        run_rehearsal(strict=False)

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(pd.DatetimeIndex([]))
    weeks = week_grid(BACKTEST_START, BACKTEST_END, ctx["px"])
    LOG.ok(f"주간 신호 격자 {len(weeks):,}주 ({weeks[0]:%Y-%m-%d} ~ {weeks[-1]:%Y-%m-%d})"
           if len(weeks) else "주간 격자 생성 실패")

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (리포트↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    P, uni = build_signal_panel(ctx, weeks)

    def _run(pp, label="run", apply_costs=True, slip_k=SLIPPAGE_K, audit=False):
        return run_backtest_w(pp, weeks, uni, ctx["sec"], apply_costs=apply_costs,
                              slip_k=slip_k, label=label, audit=audit)

    universes = OrderedDict([("전체 유니버스(상위250 제외)", "in_band")])
    if RUN_SMALLCAP_COMPARE and "in_band_small" in P.columns:
        universes[f"스몰캡(시총 하위 {SMALLCAP_BOTTOM_N})"] = "in_band_small"

    runs: "OrderedDict[str, dict]" = OrderedDict()
    with PIPE.stage("L3.BT", "주간 백테스트 (유니버스별)", "L3", budget_s=900):
        for lab, band in universes.items():
            PP = P if band == "in_band" else assemble_score(slim_panel(P), band_col=band)
            b = _run(PP, label=f"{STRATEGY_ID}:{band}", audit=(band == "in_band"))
            runs[lab] = {"panel": PP, "bt": b, "band": band,
                         "stat": perf_stats_w(b["returns"])}
            LOG.ok(f"[{lab}] 백테스트 완료 — 평균 {runs[lab]['stat'].get('평균종목수', 0):.1f}종목")
    bt = runs[list(runs)[0]]["bt"]

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300):
        report_grade_banner()
        bench = benchmark_returns_w(weeks, P)
        base_stat = report_performance(bt, bench)
        for lab in list(runs)[1:]:
            report_performance(runs[lab]["bt"], bench, label=f"({lab})")
        report_universe_compare(runs, bench)
        uni.report_attrition()

    r2f, r12, abl, dist = {}, {}, pd.DataFrame(), pd.DataFrame()
    with PIPE.stage("L5.ROBUST", "강건성 R2-F · R0 · R1 · R12 · R3 · R5 · R7 · R9", "L5",
                    budget_s=3600, critical=False):
        try:
            r2f = R2F_exhaustion_vs_drawdown(P, _run)     # ★ 최우선
            for lab in list(runs)[1:]:
                LOG.rule(f"R2-F · {lab}")
                R2F_exhaustion_vs_drawdown(P, _run, band_col=runs[lab]["band"])
            R0_benchmark(bt, bench)
            R1_leakage(P, _run, base_stat)
            r12 = R12_tail_correlation(bt, bench, P)
            for lab in list(runs)[1:]:
                LOG.rule(f"R12 · {lab}")
                R12_tail_correlation(runs[lab]["bt"], bench, runs[lab]["panel"])
            R3_orthogonal(bt, P)
            abl = R5_ablation(P, _run, base_stat)
            R7_regime(bt, bench)
            R9_capacity(P, _run)
            dist = check_phase_sample(P)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다 — 결과를 그대로 보고합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드 · 데이터 흐름", "L6", budget_s=300,
                    critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])
        report_dataflow_map()

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = persist_outputs(P, bt, r2f, r12, abl, dist, uni)
        for lab, r in list(runs.items())[1:]:
            tag = "smallcap"
            VAULT.put_table(f"backtest_returns_{STRATEGY_ID}_{tag}", r["bt"]["returns"],
                            scope="private", domain="backtest", source=f"{STRATEGY_ID}:{lab}")
            _p = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID,
                              f"returns_{tag}_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv")
            os.makedirs(os.path.dirname(_p), exist_ok=True)
            r["bt"]["returns"].to_csv(_p, index=False, encoding="utf-8-sig")
            outs.append(_p)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    PIPE.report_runtime()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info(f"한계 명시 — 신용잔고 등급 {CREDIT_GRADE}. "
             f"이자보상배율은 이자비용 계정이 DART 정형 매핑에 없어 '부채×5%' 대리를 씁니다. "
             f"관리종목/거래정지는 이력이 아닌 스냅샷이면 현재 시점 이후로만 적용합니다"
             f"(과거 구간 오염 방지).")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_RESULTS,
            "r2f": r2f, "r12": r12}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
        try:
            report_canary(); report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브 공용 인덱스에 저장되어 있으며 "
                 "재실행 시 그대로 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
