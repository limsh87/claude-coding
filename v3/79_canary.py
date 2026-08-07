

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


@contextmanager
def _probe(cid: str, item: str, disables: Sequence[str] = ()):
    """★ 프로브 하나의 예외가 CANARY 전체를 죽이지 않게 격리한다.

    §1 의 설계는 "FAIL 항목에 의존하는 단계를 큐에서 제거하고 진행" 이다. 그런데 프로브가
    예외를 던지면 스테이지가 critical 이라 실행 전체가 중단되어 설계와 정면으로 어긋난다.
    실제로 K4 의 DataFrame truthiness 예외 하나가 CANARY 를 통째로 죽이고 사용자의
    10년 백테스트를 시작조차 못 하게 만들었다.

    예외는 삼키지 않는다 — FAIL 로 기록하고 예외 종류를 실측값에 남긴다. 즉 '조용히 넘어감'이
    아니라 '이 항목은 실패했고 이유는 코드 예외'로 보고된다.
    """
    try:
        yield
    except KillCriteria:
        raise                                   # K5 중단은 그대로 위로 올린다
    except Exception as e:                      # noqa
        _canary(cid, item, False,
                f"프로브 예외 {type(e).__name__}: {str(e)[:80]}",
                "이 항목에 의존하는 단계를 비활성화하고 진행합니다 (코드 결함일 수 있으니 "
                "위 트레이스백 없이도 종류가 남도록 기록합니다)", disables)
        LOG.debug(traceback.format_exc()[-800:])


def run_canary(sample_codes: Sequence[str], sample_corps: Sequence[str]) -> pd.DataFrame:
    LOG.banner("CANARY (§1) — 코드가 의존하는 전제를 실측으로 확인",
               "FAIL 항목에 의존하는 단계는 큐에서 제거합니다. 추측으로 진행하지 않습니다.")
    smp = list(sample_codes)[:200]
    corps = list(sample_corps)[:200]
    # ★ 프로브 간 공유 변수는 반드시 _probe 바깥에서 정의한다. 안에서 정의하면 그 프로브가
    #   예외로 중단됐을 때 뒤 프로브가 NameError 를 내고, 격리의 의미가 사라진다.
    probe = smp[:12] or ["005930", "000660", "035420"]
    ok1 = False
    # ── K1 · K2  DART 재무정보 일괄다운로드 ────────────────────────────────────────────
    with _probe("K1", "DART 재무정보 일괄다운로드 2016Q1", {"bulk"}):
        t0 = time.time()
        k1_rows = 0
        k1_detail = "DART_API_KEY 미입력"
        if DART_API_KEY:
            names, diag = _bulk_discover(2016, REPRT_CODES["Q1"])
            if not names:
                names = _bulk_candidates(2016, REPRT_CODES["Q1"])
            raw, used = None, ""
            for fl in names[:8]:
                if time.time() - t0 > 180:
                    break
                raw = _bulk_fetch_one(fl)
                if raw:
                    used = fl
                    break
            if raw:
                k1_rows = len(_parse_bulk_txt(raw, 2016, REPRT_CODES["Q1"]))
                k1_detail = f"{k1_rows:,}행 / {len(raw)/1e6:.1f}MB / {time.time()-t0:.1f}s / {used}"
            else:
                # ★ "후보 N개 전부 실패" 만으로는 아무것도 고칠 수 없다. 페이지가 실제로
                #   무엇을 돌려줬는지(상태·길이·로그인 여부·발견된 링크)를 남겨야
                #   다음 실행 로그만 보고도 원인을 특정할 수 있다.
                k1_detail = f"후보 {len(names)}개 실패 · {diag}"
        _canary("K1", "DART 재무정보 일괄다운로드 2016Q1", k1_rows > 100_000, k1_detail,
                "진행" if k1_rows > 100_000 else
                "Fallback A(fnlttMultiAcnt 배치) → Fallback B(fnlttSinglAcntAll 이어받기)로 전환. "
                "A 만으로는 재고·매출채권·영업CF가 없어 TP_I2/TP_I4/TP_I1 이 죽습니다(§4.1)",
                disables=() if k1_rows > 100_000 else {"bulk"})
        ok1 = k1_rows > 100_000

    with _probe("K2", "일괄다운로드 최초 제공 분기 ≤ 2016Q1"):
        _canary("K2", "일괄다운로드 최초 제공 분기 ≤ 2016Q1", ok1,
                "2016Q1 취득 성공 → 최초 제공 분기 ≤ 2016Q1" if ok1
                else "벌크 미취득으로 최초 제공 분기를 판정할 수 없음",
                "진행" if ok1 else "폴백 경로는 2016년부터 조회 가능하므로 백테스트 시작일은 유지합니다")

    # ── K4  가격 10년 ─────────────────────────────────────────────────────────────────
    with _probe("K4", "가격 10년 취득"):
        #   ★ 시간 상한이 필수다. 소스가 전부 막힌 환경에서 20종목 × 4소스 × 재시도는
        #     최악 30분 이상이고 §1 의 CANARY 예산(20분)을 카나리아 하나가 통째로 먹는다.
        #     '몇 종목을 봤는지'를 함께 보고하면 조기 종료가 판정을 왜곡하지 않는다.
        t0 = time.time()
        n_ok, n_try, n_miss = 0, 0, []
        for c in probe:
            if time.time() - t0 > 120:
                break
            n_try += 1
            # ★ `_px_fdr(...) or _px_naver(...)` 로 쓰면 안 된다. DataFrame 에 or 를 걸면
            #   __bool__ 이 호출되어 ValueError 로 죽는데, FDR 이 막힌 환경에서는 None 이 돌아와
            #   `None or x` 로 조용히 통과한다 — 소스가 살아 있는 실환경에서만 터진다.
            d = first_nonempty(lambda: _px_fdr(c, BACKTEST_START, BACKTEST_END),
                               lambda: _px_naver(c, BACKTEST_START, BACKTEST_END),
                               lambda: _px_yf(c, BACKTEST_START, BACKTEST_END))
            if nonempty(d) and len(d) > 1000:
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
    with _probe("K5", "상장폐지 목록 (C2)"):
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
    with _probe("K6", "KRX 투자자별 수급", {"d3"}):
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
    with _probe("K7", "DART empSttus", {"TP_I3"}):
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
