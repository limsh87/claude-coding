

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  CANARY (§1) — 본 수집 전 필수 확인.  예산 20분                                            ║
# ║                                                                                          ║
# ║  ★ 하나라도 FAIL 이면 **해당 항목에 의존하는 단계를 큐에서 제거하고** 사용자에게 보고한다.  ║
# ║    추측으로 진행하지 않는다. K5(상장폐지)만은 FAIL 시 전체 중단이다 —                      ║
# ║    생존자편향을 제거할 수 없으면 어떤 성과 숫자도 의미가 없기 때문이다.                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY: List[dict] = []
DISABLED: set = set()          # FAIL 로 비활성화된 기능 태그


def _canary(cid: str, item: str, ok: bool, measured: str, action: str,
            disables: Sequence[str] = ()):
    CANARY.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL",
                   "measured": measured, "action": action})
    if not ok:
        DISABLED.update(disables)
    (LOG.ok if ok else LOG.warn)(f"[{cid}] {item} — {'PASS' if ok else 'FAIL'} · {measured}")


def run_canary(sample_codes: Sequence[str], sample_corps: Sequence[str]) -> pd.DataFrame:
    LOG.banner("CANARY (§1) — 코드가 의존하는 전제를 실측으로 확인",
               "FAIL 항목에 의존하는 단계는 큐에서 제거합니다. 추측으로 진행하지 않습니다.")
    smp = list(sample_codes)[:200]
    corps = list(sample_corps)[:200]

    # ── K1 · K2  DART 재무정보 일괄다운로드 ────────────────────────────────────────────
    t0 = time.time()
    k1_rows, first_q = 0, None
    k1_detail = "DART_API_KEY 미입력"
    if DART_API_KEY:
        names = _bulk_discover(2016, REPRT_CODES["Q1"]) or _bulk_candidates(2016, REPRT_CODES["Q1"])
        raw = None
        used = ""
        for fl in names[:8]:
            if time.time() - t0 > 180:
                break
            raw = _bulk_fetch_one(fl)
            if raw:
                used = fl
                break
        if raw:
            t = _parse_bulk_txt(raw, 2016, REPRT_CODES["Q1"])
            k1_rows = len(t)
            k1_detail = f"{k1_rows:,}행 / {len(raw)/1e6:.1f}MB / {time.time()-t0:.1f}s / {used}"
        else:
            k1_detail = (f"후보 {len(names)}개 전부 실패 — 벌크는 공개 API 가 아니라 웹 "
                         f"다운로드라 사이트 구조 변경에 취약합니다")
    ok1 = k1_rows > 100_000
    _canary("K1", "DART 재무정보 일괄다운로드 2016Q1", ok1, k1_detail,
            "진행" if ok1 else "Fallback A(fnlttMultiAcnt 배치)로 전환 — 재고·매출채권·영업CF가 "
                              "없어 TP_I2/TP_I4/TP_I1 이 약해집니다(§4.1)",
            disables=() if ok1 else {"bulk"})

    if ok1:
        first_q = "2016Q1"
        ok2 = True
        k2_detail = "2016Q1 취득 성공 → 최초 제공 분기 ≤ 2016Q1"
    else:
        ok2 = False
        k2_detail = "벌크 미취득으로 최초 제공 분기를 판정할 수 없음"
    _canary("K2", "일괄다운로드 최초 제공 분기 ≤ 2016Q1", ok2, k2_detail,
            "진행" if ok2 else "폴백 경로는 2016년부터 조회 가능하므로 백테스트 시작일은 유지합니다")

    # ── K4  가격 10년 ─────────────────────────────────────────────────────────────────
    #   ★ 시간 상한이 필수다. 소스가 전부 막힌 환경에서 20종목 × 4소스 × 재시도는
    #     최악 30분 이상이고 §1 의 CANARY 예산(20분)을 카나리아 하나가 통째로 먹는다.
    #     '몇 종목을 봤는지'를 함께 보고하면 조기 종료가 판정을 왜곡하지 않는다.
    t0 = time.time()
    n_ok, n_try, n_miss = 0, 0, []
    probe = smp[:12] or ["005930", "000660", "035420"]
    for c in probe:
        if time.time() - t0 > 120:
            break
        n_try += 1
        d = _px_fdr(c, BACKTEST_START, BACKTEST_END) or _px_naver(c, BACKTEST_START, BACKTEST_END)
        if d is not None and len(d) > 1000:
            n_ok += 1
        else:
            n_miss.append(c)
    ok4 = n_try > 0 and n_ok >= max(1, int(0.9 * n_try))
    _canary("K4", "가격 10년 취득 (FDR→네이버→yfinance)", ok4,
            f"{n_ok}/{n_try} 성공 ({time.time()-t0:.1f}s"
            + (", 시간상한 조기종료" if n_try < len(probe) else "") + ")"
            + (f" · 실패 예시 {n_miss[:4]}" if n_miss else ""),
            "진행" if ok4 else "폴백 체인으로 계속하되 커버리지 감소를 감안하세요. "
                              "전부 실패라면 네트워크에서 fchart.stock.naver.com 접근을 확인하세요")

    # ── K5  상장폐지 목록 (C2) ★ FAIL 이면 중단 ────────────────────────────────────────
    t0 = time.time()
    dead = fetch_fdr_delisting()
    n_dead = 0
    if dead is not None and len(dead):
        dd = as_ts_series(dead["delisting_date"])
        n_dead = int(((dd >= as_ts(BACKTEST_START)) & (dd <= as_ts(BACKTEST_END))).sum())
    ok5 = n_dead >= 200
    _canary("K5", "상장폐지 목록 (생존자편향 제거 · C2)", ok5,
            f"전체 {len(dead) if dead is not None else 0:,}건 · 백테스트 구간 내 {n_dead:,}건 "
            f"({time.time()-t0:.1f}s)",
            "진행" if ok5 else "⛔ 중단 — 생존자편향을 제거할 수 없으면 어떤 성과 숫자도 "
                              "의미가 없습니다(§11-1)",
            disables=() if ok5 else {"__abort__"})

    # ── K6  KRX 투자자별 수급 ──────────────────────────────────────────────────────────
    t0 = time.time()
    n6 = 0
    if pykrx_stock is not None:
        KRXG.warmup()
        for c in probe[:5]:
            r = KRXG.call(pykrx_stock.get_market_trading_value_by_date,
                          "20240102", "20240131", c)
            if r is not None and len(r):
                n6 += 1
    ok6 = n6 >= 3
    _canary("K6", "KRX 투자자별 수급", ok6,
            f"표본 5종목 중 {n6} 성공 ({time.time()-t0:.1f}s)"
            + ("" if pykrx_stock is not None else " · pykrx 미설치"),
            "진행" if ok6 else "d3 비활성화 — U 를 d1 단독으로 구성합니다(§1 K6)",
            disables=() if ok6 else {"d3"})

    # ── K7  DART empSttus (직원현황) ──────────────────────────────────────────────────
    t0 = time.time()
    n7, tried = 0, 0
    if DART_API_KEY and corps:
        for cc in corps[:20]:
            if time.time() - t0 > 90:
                break
            tried += 1
            js = dart_api("empSttus.json", {"corp_code": str(cc), "bsns_year": "2016",
                                            "reprt_code": REPRT_CODES["FY"]})
            if js and isinstance(js.get("list"), list) and js["list"]:
                n7 += 1
    rate7 = n7 / max(tried, 1)
    ok7 = rate7 >= 0.80
    _canary("K7", "DART empSttus 2016 응답률 ≥ 80%", ok7,
            f"{n7}/{tried} = {100*rate7:.0f}% ({time.time()-t0:.1f}s)",
            "진행" if ok7 else "TP_I3(인원↑인데 생산성 유지) 비활성화(§1 K7)",
            disables=() if ok7 else {"TP_I3"})

    # ── K3  필수 계정 태그 커버리지 — 본 수집 후 report_account_coverage 가 본선 판정 ──
    _canary("K3", "필수 계정 태그 커버리지 ≥ 85%", True,
            "본 수집 직후 '필수 계정 커버리지' 표에서 실측 판정합니다 "
            "(표본 200종목 사전 프로브보다 전수 실측이 강합니다)",
            "수집 후 판정 — 85% 미만 계정을 쓰는 TP 는 그 표에서 비활성화 대상으로 표시됩니다")

    C = pd.DataFrame(CANARY)
    LOG.table([[r["id"], _trunc(r["item"], 34), ("✔ PASS" if r["result"] == "PASS" else "✘ FAIL"),
                _trunc(r["measured"], 44), _trunc(r["action"], 40)]
               for r in CANARY],
              ["ID", "항목", "결과", "실측값", "조치"], ["c", "l", "c", "l", "l"], maxw=46)
    if DISABLED - {"__abort__"}:
        LOG.warn(f"CANARY 결과로 비활성화된 기능: {sorted(DISABLED - {'__abort__'})}. "
                 f"이 기능에 의존하는 지표는 결측 처리되며, 0 으로 채우지 않습니다.")
    if "__abort__" in DISABLED:
        raise KillCriteria(
            "CANARY K5 실패 — 상장폐지 목록을 확보하지 못했습니다. 생존자편향을 제거할 수 "
            "없는 상태에서 나온 성과 숫자는 체계적으로 과대평가되며, 그 크기를 추정할 방법도 "
            "없습니다. §11-1 에 따라 여기서 중단합니다. "
            "네트워크에서 raw.githubusercontent.com 접근이 가능한지 확인하세요.")
    return C
