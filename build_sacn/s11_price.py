# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금  (전면 재작성)                                                     ║
# ║                                                                                          ║
# ║  ■ 실측(사용자 실행 로그)에서 무슨 일이 있었나                                             ║
# ║      L1.PX  2,875초 / 예산 2,400초 초과 · 5,398종목 · 실패 1,901종목 · pykrx 0건           ║
# ║                                                                                          ║
# ║  ■ 원인 3개 — 전부 '느린 네트워크'가 아니었다                                              ║
# ║   ① 레이트 버킷 오배정.  _px_fdr 이 limiter("krx") 를 썼다. FDR 은 KRX 서버를 부르지도     ║
# ║      않는데 KRX 용 2 QPS 버킷에 묶였다. 워커 12개를 줘도 전역 토큰버킷이 초당 2건으로      ║
# ║      제한한다.  5,398 ÷ 2.0 = 2,699초 ≈ 실측 2,875초. 숫자가 정확히 들어맞는다.            ║
# ║   ② 죽은 소스 헛돌리기.  실패 종목마다 pykrx→fdr→naver→yfinance 를 전부 시도했다.          ║
# ║      pykrx 는 설치조차 안 됐고 yfinance 는 0건이었다. 1,901 × 4 = 7,604번의 헛수고.        ║
# ║      yfinance 는 .KS/.KQ 두 번씩 두드리므로 실제로는 그 이상이고, 실패마다 stderr 로       ║
# ║      3~4줄을 뱉어 주피터 IOPub 한도를 터뜨렸다(출력 정지 = 사용자에겐 '멈춤').             ║
# ║   ③ 받을 필요가 없는 것을 받았다.  우선주·ETF·ETN·스팩·ELW·KONEX 는 §5 에서 어차피 전부    ║
# ║      제외되는데 가격을 받으려 했다. 실패 1,901종목의 큰 덩어리가 바로 이들이다.            ║
# ║                                                                                          ║
# ║  ■ 재작성 원칙                                                                            ║
# ║   · 요청 수를 줄인다  : §5 에서 죽을 종목은 애초에 요청하지 않는다 (price_target_codes)    ║
# ║   · 요청당 수확을 늘린다: 한 종목 = 한 요청 = 10년치. 월별·연도별 쪼개기 금지.             ║
# ║   · 버킷을 실제 호스트에 맞춘다: fdr/naver_chart/krx 를 분리                               ║
# ║   · 죽은 소스는 끊는다  : 사전 프로브로 순서를 정하고, 실행 중 연속실패는 회로차단          ║
# ║   · 실패를 기억한다    : 지수 백오프 음성캐시 (30·60·120·240·365일)                        ║
# ║   · 중간에 끊겨도 잃지 않는다: 청크 단위 영속화                                            ║
# ║   · 서드파티 수다는 봉인한다: yfinance 는 별도 패스로 분리해 통째로 fd 봉인               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]
PRICE_ATTEMPT_COLS = ["code", "requested_from", "attempted_at", "fail_n", "last_error"]

# 소스별 재시도 백오프(일). 실패가 반복될수록 길어진다.
#   ★ 왜 필요한가: 2017년에 상장폐지된 종목은 어떤 소스에도 영원히 없다. 30일 고정 백오프면
#     한 달에 한 번씩 영원히 헛돈다. 백테스트 기간이 길수록 그 수는 단조 증가한다.
#     지수 백오프는 '영구 포기'가 아니다 — 소스가 복구되면 최대 1년 안에 반드시 다시 본다.
PRICE_RETRY_DAYS = [30, 60, 120, 240, 365]


def _price_backoff_days(fail_n: int) -> int:
    i = max(0, min(int(fail_n or 1) - 1, len(PRICE_RETRY_DAYS) - 1))
    return PRICE_RETRY_DAYS[i]


# ── 개별 소스 ───────────────────────────────────────────────────────────────────────────────
#   전부 '한 종목 = 한 요청 = 요청구간 전체' 다. 반환 스키마도 전부 PRICE_COLS 로 통일한다.
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    try:
        limiter("krx").wait()
        d = KRXG.call(pykrx_stock.get_market_ohlcv,
                      as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "거래대금": "amount"}
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    d["code"], d["src"] = code, "pykrx"
    return d.reindex(columns=PRICE_COLS)


def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """FinanceDataReader. ★ 버킷을 'fdr' 로 바꾼 것이 이번 재작성의 최대 성능 변경점이다."""
    if fdr is None:
        return None
    try:
        limiter("fdr").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    if "amount" not in d.columns:
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")      # 근사 — 감사표에 명시된다
    d["code"], d["src"] = code, "fdr"
    return d.reindex(columns=PRICE_COLS)


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 차트 API. 한 요청에 10년치가 통째로 온다. 폐지 종목도 한동안 남아 있다."""
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver_chart", tries=2,
                     referer="https://finance.naver.com/")
        if not t:
            continue
        # 응답이 파이썬 리터럴에 가까운 준-JSON 이다: 홑따옴표 + 따옴표 없는 키워드
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast as _ast
                arr = _ast.literal_eval(t.strip())
            except Exception:
                arr = None
        if isinstance(arr, list) and len(arr) >= 2:
            break
        arr = None
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    hdr = [str(x).strip().lower() for x in arr[0]]
    rows = [r for r in arr[1:] if isinstance(r, (list, tuple)) and len(r) == len(hdr)]
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=hdr)
    # ★ 이 rename 이 오랫동안 아무 일도 하지 않고 있었다(구버전 버그):
    #   {**ren, **{c: c for c in d.columns}} 는 두 번째 dict 가 첫 번째를 덮어써서
    #   '날짜'→'날짜' 가 '날짜'→'date' 를 이겼다. 결과적으로 컬럼명이 한글로 남고
    #   d.get("close") 가 None 이 되어 None*None TypeError 로 죽었다.
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "외국인소진율": "foreign_ratio"}
    d = d.rename(columns=ren)
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["amount"] = d["close"] * d["volume"]          # 네이버는 거래대금을 안 준다 → 근사(감사표에 명시)
    d["code"], d["src"] = code, "naver"
    d = d.dropna(subset=["close"])
    return d.reindex(columns=PRICE_COLS) if len(d) else None


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """yfinance — 기본 비활성. 실측에서 0건이었고 실패마다 stderr 를 3~4줄 뱉는다.

    ★ 호출부가 반드시 quiet_fds() 로 통째로 감싼 뒤 부른다. 스레드마다 fd 를 바꾸면
      경합이 나므로 개별 호출에서는 절대 봉인하지 않는다(별도 패스로 분리한 이유).
    ★ 한국 종목은 .KS/.KQ 접미사를 붙여야 하고, 상장폐지분은 어느 쪽으로도 없다.
      그래서 실패 1건당 요청 2건이 나간다 — 마지막 수단으로만 쓴다.
    """
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            limiter("generic").wait()
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [str(c[0]).lower() for c in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]
        d = d.reset_index()
        d = d.rename(columns={"index": "date"})
        if "date" not in d.columns:
            d = d.rename(columns={d.columns[0]: "date"})
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")
        d["code"], d["src"] = code, "yfinance"
        return d.reindex(columns=PRICE_COLS)
    return None


PRICE_FN = {"pykrx": _px_pykrx, "fdr": _px_fdr, "naver": _px_naver, "yfinance": _px_yf}
PRICE_BUCKET = {"pykrx": "krx", "fdr": "fdr", "naver": "naver_chart", "yfinance": "generic"}


def _px_available(src: str) -> bool:
    if src == "pykrx":
        return pykrx_stock is not None
    if src == "fdr":
        return fdr is not None
    if src == "yfinance":
        return yf is not None
    return True


def price_probe(codes: Sequence[str], start: str, end: str,
                n: int = 8) -> Tuple[List[str], pd.DataFrame]:
    """본 수집 전에 소스를 실측한다. 8종목 × 소스수 만큼만 쓴다(수백 초를 아끼는 수십 초).

    ★ 왜 필요한가: 어떤 소스가 살아 있는지는 '실행해 봐야' 안다. pykrx 는 설치 실패로,
      KRX 는 로그인 정책으로, 네이버는 차단으로 각각 다른 날 죽는다. 죽은 소스를 체인
      맨 앞에 두면 전 종목이 그 소스의 타임아웃을 한 번씩 물고 간다.
      프로브는 성공률과 지연을 재서 '살아 있는 소스만, 빠른 순으로' 체인을 만든다.

    표본 추출은 결정적(seed 고정)이며 목록 앞/중간/뒤에서 고르게 뽑는다 —
    앞쪽만 뽑으면 코드번호가 작은 오래된 대형주만 보게 되어 판단이 낙관 편향된다.
    """
    pool = [c for c in codes if c]
    if not pool:
        return [], pd.DataFrame(columns=["소스", "성공", "시도", "평균지연", "판정"])
    step = max(1, len(pool) // max(1, n))
    sample = pool[::step][:n]
    order = [s for s in PRICE_SOURCES if _px_available(s)]
    rows, ranked = [], []
    for src in order:
        fn = PRICE_FN[src]
        t0, ok = time.time(), 0
        with quiet_fds(enabled=(src == "yfinance")):
            for c in sample:
                try:
                    d = fn(c, start, end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    ok += 1
        lat = (time.time() - t0) / max(1, len(sample))
        alive = ok > 0
        rows.append([src, f"{ok}/{len(sample)}", f"{len(sample)}", f"{lat:.2f}s",
                     "사용" if alive else "제외(0건)"])
        if alive:
            ranked.append((-(ok / len(sample)), lat, src))
    chain = [s for _, _, s in sorted(ranked)]
    skipped = [s for s in PRICE_SOURCES if not _px_available(s)]
    for s in skipped:
        rows.append([s, "-", "-", "-", "제외(미설치)"])
    return chain, pd.DataFrame(rows, columns=["소스", "성공", "시도", "평균지연", "판정"])


def _load_price_attempts() -> Tuple[Dict[str, dict], Optional[pd.DataFrame]]:
    """음성 캐시 적재. 구버전 스키마(fail_n 없음)와 호환된다 — 없으면 1로 본다."""
    att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if att is None or not len(att):
        return {}, None
    a = att.copy()
    for c in ("attempted_at", "requested_from"):
        if c in a.columns:
            a[c] = as_ts_series(a[c])
        else:
            a[c] = pd.NaT
    if "fail_n" not in a.columns:
        a["fail_n"] = 1
    a["fail_n"] = pd.to_numeric(a["fail_n"], errors="coerce").fillna(1).astype(int)
    a = a.sort_values("attempted_at").drop_duplicates("code", keep="last")
    return ({str(r.code): {"at": r.attempted_at, "frm": r.requested_from, "n": int(r.fail_n)}
             for r in a.itertuples(index=False)}, a)


def _price_windows(codes: Sequence[str], start: str, end: str,
                   sec: Optional[pd.DataFrame]) -> Dict[str, Tuple[str, str]]:
    """종목별 실제 요청 구간. 상장 전·폐지 후를 요청하지 않는다.

    ★ 이것도 '쓸데없는 반복'의 하나다. 2021년 상장 종목에 2015년부터 달라고 하면
      소스에 따라 빈 응답이 오고, 그걸 '실패'로 오인해 다음 소스로 넘어가 또 요청한다.
      상장일 기준으로 창을 좁히면 요청 1건으로 정확히 있는 만큼만 받는다.
    """
    lo_all, hi_all = as_ts(start), as_ts(end)
    win = {c: (start, end) for c in codes}
    if sec is None or not len(sec):
        return win
    s = sec.copy()
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    li = as_ts_series(s["listing_date"]) if "listing_date" in s.columns else pd.Series(pd.NaT, index=s.index)
    dl = as_ts_series(s["delisting_date"]) if "delisting_date" in s.columns else pd.Series(pd.NaT, index=s.index)
    for c, l, d in zip(s["code"], li, dl):
        if c not in win:
            continue
        lo = lo_all if pd.isna(l) else max(lo_all, as_ts(l) - pd.Timedelta(days=10))
        hi = hi_all if pd.isna(d) else min(hi_all, as_ts(d) + pd.Timedelta(days=10))
        if hi <= lo:
            hi = lo + pd.Timedelta(days=30)
        win[c] = (lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))
    return win


def fetch_prices(codes: Sequence[str], start: str, end: str,
                 sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """다중소스 일봉 수집. 캐시 증분 · 요청 최소화 · 회로차단 · 청크 영속화."""
    silence_thirdparty()
    codes = sorted({c for c in map(to_code6, codes) if c})
    start_ts, end_ts = as_ts(start), as_ts(end)

    # ── ① 캐시 ─────────────────────────────────────────────────────────────────────────
    cached = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached["code"] = cached["code"].map(to_code6)
        cached = cached.dropna(subset=["date", "code"])
        g = cached.groupby("code")["date"]
        have_max, have_min = g.max().to_dict(), g.min().to_dict()
        LOG.info(f"공용 캐시에서 일봉 {len(cached):,}행 재사용 ({len(have_max):,}종목) — "
                 f"이 종목들은 다시 조회하지 않습니다.")

    attempts, att_prev = _load_price_attempts()
    windows = _price_windows(codes, start, end, sec)
    today = as_ts(end)

    def _recently_failed(c: str, want_from: pd.Timestamp) -> bool:
        p = attempts.get(c)
        if p is None or pd.isna(p["at"]):
            return False
        if pd.notna(p["frm"]) and p["frm"] > want_from:
            return False        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 아니다
        return (today - p["at"]).days < _price_backoff_days(p["n"])

    # ── ② 할 일 산정 ────────────────────────────────────────────────────────────────────
    todo: List[Tuple[str, str, str]] = []
    n_back = n_fwd = n_skip = n_hit = 0
    for c in codes:
        w_lo, w_hi = windows.get(c, (start, end))
        w_lo_ts, w_hi_ts = as_ts(w_lo), as_ts(w_hi)
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, w_lo_ts):
                n_skip += 1
                continue
            todo.append((c, w_lo, w_hi))
            continue
        # ★ 과거 방향 백필을 반드시 함께 본다. max 만 보면 앞 7년이 조용히 빈다.
        #   단, 비교 기준은 '요청 구간'이 아니라 '그 종목이 존재할 수 있었던 구간'이다.
        #   2021년 상장 종목의 캐시 최소일이 2021년인 것은 결손이 아니라 정상이다.
        if mn is not None and mn > w_lo_ts + pd.Timedelta(days=10):
            if _recently_failed(c, w_lo_ts):
                n_skip += 1
                continue
            todo.append((c, w_lo, w_hi))
            n_back += 1
        elif mx < w_hi_ts - pd.Timedelta(days=5):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), w_hi))
            n_fwd += 1
        else:
            n_hit += 1
    LOG.table([["대상 종목", f"{len(codes):,}"],
               ["캐시 충족 (재조회 안 함)", f"{n_hit:,}"],
               ["과거구간 결손 → 전체 재수집", f"{n_back:,}"],
               ["최근구간 증분", f"{n_fwd:,}"],
               ["백오프로 이번엔 생략", f"{n_skip:,}"],
               ["── 실제 요청", f"{len(todo):,}"]],
              ["항목", "종목수"], ["l", "r"], title="가격 수집 계획 (요청 수 최소화)")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    failed: List[dict] = []

    if todo:
        # ── ③ 프로브 → 체인 확정 ────────────────────────────────────────────────────────
        chain, ptab = price_probe([c for c, _, _ in todo], start, end)
        LOG.table(ptab.values.tolist(), list(ptab.columns), ["l", "r", "r", "r", "l"],
                  title="가격 소스 사전 프로브 (실측 성공률 순으로 체인 구성)")
        chain = [s for s in chain if s != "yfinance"]        # yfinance 는 별도 패스
        if not chain and "yfinance" not in PRICE_SOURCES:
            LOG.error("살아 있는 가격 소스가 없습니다 — 캐시만으로 진행합니다.")

        health = SourceHealth()
        n_workers = max(_resolve_workers(PRICE_BUCKET.get(s, "generic")) for s in chain) if chain else 4

        def _one(job):
            code, st, en = job
            for nm in chain:
                if not health.alive(nm):
                    continue
                try:
                    d = PRICE_FN[nm](code, st, en)
                except Exception:
                    d = None
                good = d is not None and len(d) > 0
                health.mark(nm, good)
                if good:
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d
            return None

        # ── ④ 청크 실행 ──────────────────────────────────────────────────────────────────
        #   전량을 한 번에 던지면 결과 DataFrame 이 전부 RAM 에 남고, 중간에 끊기면 통째로
        #   잃는다. 청크마다 접어서 downcast 하고 캐시에 반영한다.
        CHUNK = 1500
        pending: List[Tuple[str, str, str]] = []
        for k0 in range(0, len(todo), CHUNK):
            part = todo[k0:k0 + CHUNK]
            tag = f"일봉 {k0 // CHUNK + 1}/{(len(todo) - 1) // CHUNK + 1}"
            res = pmap_io(_one, part, workers=n_workers, desc=tag)
            got = []
            for (c, st, en), d in zip(part, res):
                if d is not None and len(d):
                    got.append(d)
                    src_used[str(d["src"].iloc[0])] += 1
                else:
                    pending.append((c, st, en))
            if got:
                new_frames.append(downcast(pd.concat(got, ignore_index=True)))
            del res, got
            if health.tripped:
                LOG.warn("회로차단 발동 — " + ", ".join(
                    f"{k}(연속실패)" for k in health.tripped) +
                    " 소스를 이번 실행에서 제외합니다. 남은 종목은 다른 소스로 진행합니다.")

        # ── ⑤ yfinance 마무리 패스 (기본 비활성) ─────────────────────────────────────────
        if pending and "yfinance" in PRICE_SOURCES and yf is not None:
            LOG.info(f"yfinance 마무리 패스 {len(pending):,}종목 — 서드파티 출력을 통째로 "
                     f"봉인하고 실행합니다(진행률이 보이지 않는 것이 정상입니다). "
                     f"완료 후 결과만 출력됩니다.")
            t0 = time.time()
            with quiet_fds():
                yres = pmap_io(lambda j: _px_yf(j[0], j[1], j[2]), pending,
                               workers=min(8, N_WORKERS_IO), desc="", quiet=True)
            still: List[Tuple[str, str, str]] = []
            got = []
            for job, d in zip(pending, yres):
                if d is not None and len(d):
                    got.append(d)
                    src_used["yfinance"] += 1
                else:
                    still.append(job)
            if got:
                new_frames.append(downcast(pd.concat(got, ignore_index=True)))
            LOG.ok(f"yfinance 마무리 — {len(got):,}/{len(pending):,}종목 확보 "
                   f"({time.time() - t0:.0f}초)")
            pending = still
        elif pending and "yfinance" in PRICE_SOURCES and yf is None:
            LOG.info("yfinance 미설치 — 마무리 패스를 건너뜁니다.")

        # ── ⑥ 실패 원장 (지수 백오프) ────────────────────────────────────────────────────
        #  ★ '진짜 없는 종목'과 '이번 환경이 고장난 것'을 반드시 구분한다.
        #    소스가 하나도 안 살아 있었거나 전부 회로차단으로 끊긴 상태에서 실패를 기록하면,
        #    다음 실행에서 FDR 을 설치해 놓고도 그 종목들을 30일간 건너뛴다.
        #    환경 문제로 음성 캐시를 오염시키는 것은 데이터를 잃는 것과 같다.
        live_at_end = [s for s in chain if health.alive(s)]
        if pending and not live_at_end:
            LOG.error(
                f"살아 있는 가격 소스가 없는 상태로 {len(pending):,}종목이 미수집으로 남았습니다. "
                f"이것은 '데이터가 없다'가 아니라 '이번 실행 환경이 소스에 닿지 못했다'는 뜻이므로 "
                f"실패로 기록하지 않습니다(다음 실행에서 정상 재시도).\n"
                f"  확인: ① pip install finance-datareader ② fchart.stock.naver.com 접근 "
                f"③ 프록시/방화벽 ④ RATE_LIMIT_QPS 를 낮춰 차단 해제 대기")
        for c, st, _en in (pending if live_at_end else []):
            prev = attempts.get(c, {})
            failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": today,
                           "fail_n": int(prev.get("n", 0)) + 1,
                           "last_error": "all_sources_empty"})
        if failed:
            nxt = Counter(_price_backoff_days(f["fail_n"]) for f in failed)
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 살아 있는 전 소스에서 데이터가 "
                     f"없었습니다. 상장폐지 종목이 소스에서 조회되지 않는 것은 정상입니다. "
                     f"다음 재시도까지: " +
                     ", ".join(f"{d}일×{n:,}종목" for d, n in sorted(nxt.items())))
            _new = pd.DataFrame(failed)
            _all = pd.concat([att_prev, _new], ignore_index=True) if att_prev is not None else _new
            _all = (_all.reindex(columns=PRICE_ATTEMPT_COLS)
                        .sort_values("attempted_at")
                        .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                            source="fetch_prices:negative_cache")
        hrows = health.rows()
        if hrows:
            LOG.table(hrows, ["소스", "성공", "실패", "성공률", "상태"],
                      ["l", "r", "r", "r", "l"], title="가격 소스 실행중 건강도")

    # ── ⑦ 병합 ─────────────────────────────────────────────────────────────────────────
    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        avail = [s for s in PRICE_SOURCES if _px_available(s)]
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            f"  · 설정된 소스 : {', '.join(PRICE_SOURCES)}\n"
            f"  · 이번 실행에서 사용 가능했던 소스 : {', '.join(avail) or '없음'}\n"
            f"  · 대상 종목 {len(codes):,}개 / 신규 수집 시도 {len(todo):,}개\n"
            "  진단: ① 네트워크에서 fchart.stock.naver.com 접근이 되는지\n"
            "        ② FinanceDataReader 가 설치돼 있는지 (pip install finance-datareader)\n"
            "        ③ 드라이브 캐시(krx_ohlcv_daily)가 비어 있지 않은지\n"
            "  임시 우회: RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    for c in ("open", "high", "low", "close", "volume", "amount"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    px = px[(px["date"] >= start_ts - pd.Timedelta(days=400)) & (px["date"] <= end_ts)]

    if new_frames:
        VAULT.put_table("krx_ohlcv_daily", px, scope="shared", domain="price",
                        source="chain:" + ",".join(f"{k}x{v}" for k, v in src_used.most_common()))
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if src_used.get("naver", 0) or src_used.get("yfinance", 0) or src_used.get("fdr", 0):
            LOG.warn("FDR/네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향). "
                     "KRX 벌크가 살아 있으면 월말 거래대금은 실측치로 덮어씁니다.")
    PIPE.io("OUT", "DRIVE", "krx_ohlcv_daily", px, source="price chain")
    return downcast(px)


def build_price_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 기준 가격 패널 + 익월 시가 체결가 + 20일 평균거래대금(ADV).

    체결은 '신호 산출일 다음 거래일 시가'(§10.1). 당일 종가 체결은 미래누수다.
    """
    px = px.sort_values(["code", "date"])
    px["adv20"] = (px.groupby("code", observed=True)["amount"]
                     .transform(lambda s: s.rolling(20, min_periods=10).mean()))
    px["ret1d"] = px.groupby("code", observed=True)["close"].pct_change()

    # 월말 스냅샷
    px["ym"] = px["date"].values.astype("datetime64[M]")
    last = px.groupby(["code", "ym"], observed=True).tail(1).copy()
    last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)

    # 다음 거래일 시가 = 체결가
    nxt = px.copy()
    nxt["next_open"] = nxt.groupby("code", observed=True)["open"].shift(-1)
    nxt["next_date"] = nxt.groupby("code", observed=True)["date"].shift(-1)
    keep = nxt[["code", "date", "next_open", "next_date"]]
    last = last.merge(keep, on=["code", "date"], how="left")

    monthly = last[["code", "month", "date", "close", "adv20", "next_open", "next_date"]].copy()
    monthly = monthly.rename(columns={"date": "signal_date"})
    monthly = monthly[monthly["month"].isin(months)]

    monthly = monthly.sort_values(["code", "month"])
    # 체결가 = 신호 산출일의 '다음 거래일 시가'. 그 다음 거래일이 너무 멀면(거래정지·상폐 직전)
    # 그 가격으로 체결했다고 가정할 수 없으므로 종가로 폴백한다.
    gap = (monthly["next_date"] - monthly["signal_date"]).dt.days
    monthly["exec_px"] = monthly["next_open"].where(gap.notna() & (gap <= 10))
    monthly["exec_px"] = monthly["exec_px"].fillna(monthly["close"])

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    nxt_px = monthly.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_m = monthly.groupby("code", observed=True)["month"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    monthly["fwd_ret"] = (nxt_px / monthly["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def fetch_investor_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """투자자별 순매수. SACN 본선에는 쓰이지 않고 H3(개인비중) 보조 지표로만 쓴다.

    ★ 종목축 루프라 비싸다(종목당 1호출). 캐시가 없고 pykrx 도 없으면 아예 시도하지 않는다 —
      없어도 전략은 성립하고, 있으면 해석표가 풍부해질 뿐이다.
    """
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용")
        cached["date"] = as_ts_series(cached["date"])
        return cached
    if pykrx_stock is None or RUN_MODE == "CACHED" or not COLLECT_INVESTOR_FLOWS:
        LOG.info("수급 데이터 미수집 (pykrx 없음 / CACHED 모드 / 설정 off) — "
                 "해석표의 수급 항목만 비고, 신호·백테스트에는 영향이 없습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})

    def _one(code: str):
        try:
            limiter("krx").wait()
            d = KRXG.call(pykrx_stock.get_market_trading_value_by_date,
                          as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
        except Exception:
            return None
        if d is None or len(d) == 0:
            return None
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "date"})
        inst = next((c for c in d.columns if "기관" in str(c)), None)
        forg = next((c for c in d.columns if "외국" in str(c)), None)
        if inst is None and forg is None:
            return None
        return pd.DataFrame({"code": code, "date": as_ts_series(d["date"]),
                             "inst_net": pd.to_numeric(d[inst], errors="coerce") if inst else np.nan,
                             "foreign_net": pd.to_numeric(d[forg], errors="coerce") if forg else np.nan})

    res = pmap_io(_one, codes, workers=_resolve_workers("krx"), desc="수급 수집")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.warn("수급 데이터를 받지 못했습니다 — 해석표의 수급 항목만 비웁니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])
    fl = pd.concat(got, ignore_index=True)
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)
