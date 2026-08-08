

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]


class KRXAuth:
    """KRX 데이터 마켓플레이스 인증(2025-12 변경 대응). 실패해도 절대 죽지 않고 폴백으로 넘긴다.

    2026년 기준 경로 3가지:
      ① KRX Open API (data-dbg.krx.co.kr) — 인증키. ★단, 엔드포인트별로 '이용신청'이 따로 필요하고
         승인에 하루 정도 걸린다. 키만 있다고 바로 되는 게 아니다. 상장폐지 API 는 존재하지 않는다.
      ② 마켓플레이스 세션 로그인 → getJsonData.cmd (bld 기반). pykrx 가 쓰는 경로.
      ③ 레거시 OTP 파일다운로드 — 2026년에는 세션 없이 빈 데이터/로그아웃 오류가 잦다. 의존 금지.
    """

    LOGIN_WARM1 = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    LOGIN_WARM2 = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    JSONDATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
    OPENAPI = "https://data-dbg.krx.co.kr/svc/apis/{cat}/{ep}"

    def __init__(self, user: str, pw: str, apikey: str = ""):
        self.user, self.pw, self.apikey = (user or "").strip(), (pw or "").strip(), (apikey or "").strip()
        self.status = "NOT_ATTEMPTED"
        self.session_ok = False
        self.openapi_ok = False

    def login(self) -> bool:
        if self.apikey:
            self.openapi_ok = self._probe_openapi()
            self.status = "OPENAPI_OK" if self.openapi_ok else "OPENAPI_KEY_UNAUTHORIZED"
            if not self.openapi_ok:
                LOG.warn("KRX Open API 키는 있으나 해당 엔드포인트 호출이 거부되었습니다. "
                         "KRX Open API 는 '엔드포인트별 이용신청'이 따로 필요하고 승인에 하루 정도 "
                         "걸립니다. 키 발급만으로는 즉시 사용할 수 없습니다.")
        if not (self.user and self.pw):
            if not self.openapi_ok:
                self.status = "NO_CREDENTIALS"
                LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 불필요 경로로 진행합니다. "
                         "(FDR GitHub 캐시 → 네이버 차트 → yfinance). "
                         "백테스트는 정상 동작하며, 어느 소스가 쓰였는지는 감사표에 나옵니다.")
            return self.openapi_ok
        # 워밍업 없이 바로 POST 하면 세션 쿠키가 없어 항상 실패한다
        http_get(self.LOGIN_WARM1, source="krx", tries=1)
        http_get(self.LOGIN_WARM2, source="krx", tries=1, referer=self.LOGIN_WARM1)
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                continue
            if re.search(r"CD011|중복\s*로그인", str(txt)):
                LOG.warn("KRX 중복 로그인(CD011) 감지 — 같은 계정이 브라우저나 다른 노트북에서 "
                         "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 종료됩니다. "
                         "두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                 "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
        return self.openapi_ok

    def _probe_openapi(self) -> bool:
        """AUTH_KEY 를 쿼리로 보내는 구현과 헤더로 보내는 공식 샘플이 공존한다 — 둘 다 시도."""
        d = (_dt.date.today() - _dt.timedelta(days=7))
        while d.weekday() >= 5:
            d -= _dt.timedelta(days=1)
        url = self.OPENAPI.format(cat="sto", ep="stk_bydd_trd")
        for mode in ("query", "header"):
            kw = ({"params": {"AUTH_KEY": self.apikey, "basDd": d.strftime("%Y%m%d")}}
                  if mode == "query" else
                  {"params": {"basDd": d.strftime("%Y%m%d")},
                   "headers": {"AUTH_KEY": self.apikey}})
            js = http_json(url, source="krx", tries=1, **kw)
            if isinstance(js, dict) and (js.get("OutBlock_1") or js.get("output")):
                LOG.ok(f"KRX Open API 사용 가능 (AUTH_KEY 전달 방식: {mode})")
                self._openapi_mode = mode
                return True
        return False

    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회. 세션이 없으면 JSON 대신 로그인 HTML 이 와서
        엉뚱한 곳에서 JSONDecodeError 가 난다 → 여기서 미리 막는다."""
        if not self.session_ok:
            return None
        body = {"bld": bld, "share": "1", "money": "1", "csvxls_isNo": "false", **params}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if not txt or txt.lstrip()[:1] not in ("{", "["):
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY)


# ── 개별 소스 ───────────────────────────────────────────────────────────────────────────────
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """★ 반드시 KRXG.call 을 통과시킨다. 이 파일 상단 KRXGate 독스트링이 금지하는 바로 그
    상황이었다 — pykrx 의 get_auth_session() 은 락 없이 검사-후-생성을 하므로, 12스레드가
    동시에 이 함수를 부르면 각자 로그인하고 KRX 가 중복로그인(CD011)으로 앞 세션을 끊는다.
    살아남는 건 마지막 하나뿐이고 나머지는 죽은 쿠키로 요청해 JSON 대신 로그인 HTML 을 받는다.
    → pykrx 가 설치되고 인증까지 된 **실환경에서만** 대량 실패가 나므로 개발 중엔 안 보인다.
    """
    if pykrx_stock is None:
        return None
    d = KRXG.call(pykrx_stock.get_market_ohlcv,
                  start.replace("-", ""), end.replace("-", ""), code)
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
    if fdr is None:
        return None
    try:
        limiter("krx").wait()
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
    """네이버 차트 API. 폴백 중에서는 가장 안정적이지만 거래대금이 없다."""
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
        # 응답이 파이썬 리터럴에 가까운 준-JSON 이다: 홑따옴표 + 따옴표 없는 키워드
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast
                arr = ast.literal_eval(t.strip())
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
    # ★ 이 rename 이 오랫동안 아무 일도 하지 않고 있었다.
    #   {**ren, **{c: c for c in d.columns}} 는 두 번째 dict 가 첫 번째를 덮어써서
    #   '날짜'→'날짜' 가 '날짜'→'date' 를 이긴다. 결과적으로 컬럼명이 한글로 남고
    #   d.get("close") 가 None 이 되어 None*None TypeError 로 죽는다.
    #   (pykrx/FDR 이 둘 다 없는 환경에서만 드러나므로 오래 숨어 있었다)
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


_YF_QUIET = False


def _hush_yfinance():
    """yfinance 의 'invalid symbol' 수다를 끈다.

    버전마다 경로가 다르다 — 자체 로거(get_yf_logger), 'yfinance' 이름의 표준 로거,
    그리고 일부 버전은 그냥 print 다. 앞의 둘을 막고, print 경로는 애초에 호출하지
    않는 것(_no_yf)으로 처리한다. 로그 억제만으로는 print 를 막을 수 없기 때문이다.
    """
    global _YF_QUIET
    if _YF_QUIET or yf is None:
        return
    _YF_QUIET = True
    try:
        import yfinance.utils as _yu
        lg = _yu.get_yf_logger()
        lg.disabled = True
        lg.setLevel(logging.CRITICAL)
        lg.propagate = False
    except Exception:                                            # noqa
        pass
    for nm in ("yfinance", "yfinance.data", "yfinance.ticker", "peewee"):
        lg = logging.getLogger(nm)
        lg.disabled = True
        lg.setLevel(logging.CRITICAL)
        lg.propagate = False


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    _hush_yfinance()
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


PRICE_CHAIN = [("pykrx", _px_pykrx), ("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf)]


def fetch_prices(codes: Sequence[str], start: str, end: str,
                 sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. 캐시 증분 갱신. 공용 인덱스에 저장.

    ★ sec(종목 마스터)를 받으면 상장일·폐지일을 알고 계획을 세운다. 이게 없으면
      "2018년 상장 종목의 2015년치가 캐시에 없다"를 **결손**으로 오해해서 매 실행
      백필을 반복한다. 없는 데이터를 찾아 헤매는 건 영원히 끝나지 않는다.
    """
    codes = sorted({c for c in map(to_code6, codes) if c})

    # ── 종목별 '데이터가 존재할 수 있는 구간' ──────────────────────────────────────
    listing: Dict[str, pd.Timestamp] = {}
    delist: Dict[str, pd.Timestamp] = {}
    if nonempty(sec):
        _s = sec.copy()
        _s["code"] = _s["code"].map(to_code6)
        if "listing_date" in _s.columns:
            _l = _s.dropna(subset=["code"]).assign(d=as_ts_series(_s["listing_date"]))
            listing = {r.code: r.d for r in _l.dropna(subset=["d"]).itertuples(index=False)}
        if "delisting_date" in _s.columns:
            _d = _s.dropna(subset=["code"]).assign(d=as_ts_series(_s["delisting_date"]))
            delist = {r.code: r.d for r in _d.dropna(subset=["d"]).itertuples(index=False)}
    cached = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        g = cached.groupby("code")["date"]
        have_max, have_min = g.max().to_dict(), g.min().to_dict()
        LOG.info(f"공용 캐시에서 일봉 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    start_ts, end_ts = as_ts(start), as_ts(end)

    # ── 시도 원장 (음성 캐시) ─────────────────────────────────────────────────────────────
    #  ★ 폐지 종목과 '어느 소스에도 없는 종목'은 매 실행마다 전 소스 체인을 헛돌게 만든다.
    #    성공한 종목만 캐시에 남으므로 실패는 영원히 기억되지 않고, 그 수는 백테스트 기간이
    #    길어질수록 단조 증가한다. 실측상 완전 캐시 상태의 실행에서도 13~15분을 여기서 쓴다.
    #    → '언제 무엇을 시도했는지'를 남겨 30일간 재시도하지 않는다. 소스가 복구되면
    #      30일 뒤 자동으로 다시 시도하므로 영구 포기가 아니다.
    RETRY_AFTER_DAYS = 30
    # ★ 여기에 as_ts(end)(=BACKTEST_END, 고정 문자열)를 쓰면 attempted_at 이 매 실행 같은 값이
    #   되어 (_today - p["at"]).days 가 영원히 0 이다 → 재시도 만료가 영영 오지 않는다.
    #   즉 한 번 실패한 종목은 소스가 복구돼도 두 번 다시 시도되지 않는 '영구 포기'가 된다.
    #   음성 캐시는 반드시 실제 벽시계로 늙어야 한다.
    _today = pd.Timestamp.today().normalize()
    attempts: Dict[str, dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att["attempted_at"] = as_ts_series(_att["attempted_at"])
        _att["requested_from"] = as_ts_series(_att["requested_from"])
        _att = _att.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from}
                    for r in _att.itertuples(index=False)}

    def _asked_before(c: str, want_from: pd.Timestamp) -> bool:
        """★ 이미 이 구간(또는 더 이른 구간)을 요청해 봤는가.

        예전엔 **실패한 종목만** 원장에 남겼다. 그래서 2018년에 상장한 종목처럼
        '소스가 줄 수 있는 최초일'이 요청 시작일보다 늦은 경우, 캐시에 데이터가 멀쩡히
        있는데도 mn(2018) > start(2015-02) 조건에 걸려 **매 실행마다 영원히 재수집**했다.
        실측: 캐시 697만행을 갖고도 3,497종목을 처음부터 다시 받아 17.5분을 태웠다.
        → 성공·실패를 가리지 않고 '무엇을 언제 어디서부터 요청했는지'를 남긴다.
          소스가 더 과거를 줄 수 있게 되면 RETRY_AFTER_DAYS 뒤 자동 재시도된다.
        """
        p = attempts.get(c)
        if p is None or pd.isna(p["at"]):
            return False
        if pd.notna(p["frm"]) and p["frm"] > want_from + pd.Timedelta(days=10):
            return False            # 이번엔 더 이른 구간을 원한다 → 재시도할 이유가 있다
        return (_today - p["at"]).days < RETRY_AFTER_DAYS

    todo, n_back, n_fwd, n_skip, n_neg, n_life = [], 0, 0, 0, 0, 0
    n_new, n_gap = 0, 0            # 신규(캐시 없음) vs 갭백필(캐시가 늦게 시작)
    gap_sample: List[str] = []
    GRACE = pd.Timedelta(days=10)
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        # 이 종목의 데이터가 존재할 수 있는 구간 [want_from, want_to]
        ld, dd = listing.get(c), delist.get(c)
        want_from = max(start_ts, ld) if pd.notna(ld) else start_ts
        want_to = min(end_ts, dd) if pd.notna(dd) else end_ts
        if want_from > want_to:
            n_life += 1                  # 백테스트 구간과 상장기간이 겹치지 않는다
            continue
        asked = _asked_before(c, want_from)
        if mx is None:
            if asked:
                n_neg += 1               # 캐시도 없고 최근에 물어봤다 → 음성 캐시
                continue
            todo.append((c, want_from.strftime("%Y-%m-%d")))
            n_back += 1
            n_new += 1
            continue
        # 과거 방향 백필. 단 **상장일 이전은 애초에 존재하지 않으므로 요청하지 않는다**.
        # 그리고 이미 그 구간을 요청해 본 적이 있으면 다시 묻지 않는다 — 그때 못 받은 건
        # 소스가 그 이전을 갖고 있지 않다는 뜻이다.
        if mn is not None and mn > want_from + GRACE and not asked:
            todo.append((c, want_from.strftime("%Y-%m-%d")))
            n_back += 1
            n_gap += 1
            if len(gap_sample) < 5:
                gap_sample.append(f"{c}(캐시시작 {mn:%Y-%m} · 요청 {want_from:%Y-%m}"
                                  f"{' · 상장일없음' if pd.isna(ld) else f' · 상장 {ld:%Y-%m}'})")
        elif mx < want_to - pd.Timedelta(days=5):
            # 폐지 종목은 폐지일까지만 있으면 완결이다. 그 뒤를 매달 다시 묻지 않는다.
            frm = mx + pd.Timedelta(days=1)
            if _asked_before(c, frm):
                n_skip += 1
            else:
                todo.append((c, frm.strftime("%Y-%m-%d")))
                n_fwd += 1
        else:
            n_skip += 1
    LOG.table([["신규(캐시 없음)", f"{n_new:,}", "이 종목의 일봉이 캐시에 아예 없다"],
               ["갭 백필", f"{n_gap:,}",
                "캐시가 요청 시작일보다 늦게 시작 → 앞 구간을 한 번 더 물어본다"],
               ["증분", f"{n_fwd:,}", "마지막 캐시일 다음날부터만 받는다"],
               ["캐시 충분", f"{n_skip:,}", "상장~폐지 구간이 이미 다 차 있음 → 요청 안 함"],
               ["음성 캐시", f"{n_neg:,}", f"최근 {RETRY_AFTER_DAYS}일 내 전 소스 실패 → 재시도 안 함"],
               ["기간 밖", f"{n_life:,}", "상장기간이 백테스트 구간과 겹치지 않음 → 요청 안 함"],
               ["── 합계 ──", f"{len(codes):,}", f"이번에 실제 요청 {len(todo):,}종목"]],
              ["일봉 수집 계획", "종목수", "근거"], ["l", "r", "l"],
              title="가격 수집 계획 — 없는 데이터를 찾아 헤매지 않는다 "
                    "(상장일·폐지일로 존재 가능 구간을 먼저 자릅니다)")
    if n_gap:
        LOG.warn(f"갭 백필 {n_gap:,}종목 — 캐시가 요청 시작일보다 늦게 시작합니다. "
                 f"소스가 그 이전을 못 주는 것이면 이번 한 번만 묻고 시도원장에 기록되어 "
                 f"{RETRY_AFTER_DAYS}일간 다시 묻지 않습니다. 예: {gap_sample}. "
                 f"이 숫자가 매 실행 크게 남으면 상장일 결측(현재 "
                 f"{100*(1-len(listing)/max(len(codes),1)):.0f}%)이 원인입니다 — "
                 f"상장일을 모르면 '2015년부터 있어야 한다'고 가정할 수밖에 없습니다.")
    if not todo:
        LOG.ok("새로 받을 일봉이 없습니다 — 캐시만으로 충분합니다.")
    if n_neg:
        LOG.info(f"최근 {RETRY_AFTER_DAYS}일 내 전 소스에서 데이터를 못 받은 {n_neg:,}종목은 "
                 f"이번엔 건너뜁니다 (대부분 상장폐지분). {RETRY_AFTER_DAYS}일 뒤 자동 재시도합니다.")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    if todo:
        LOG.info(f"일봉 신규/증분 수집 대상 {len(todo):,}종목")

        # ── 적응형 소스 체인 ────────────────────────────────────────────────────────
        #  ★ 병목의 정체: 체인이 고정 순서라 **죽은 소스의 비용을 2,600종목 전부가 지불**한다.
        #    pykrx 가 인증 실패로 못 쓰는 상태면 종목마다 pykrx 를 먼저 때리고 실패한 뒤
        #    다음으로 넘어간다. 종목당 몇 초 × 2,600 = 수십 분이 통째로 낭비된다.
        #    → 소스별 연속 실패를 세어 임계치를 넘으면 그 소스를 이번 실행에서 내린다.
        #      한 번이라도 성공하면 카운터가 0 으로 돌아가므로 일시적 실패로 내려가지 않는다.
        #    → 그리고 최근 성공한 소스를 앞으로 당긴다(대부분의 종목이 같은 소스에서 나온다).
        _dead_after = 40
        _fail = Counter()
        _ok = Counter()
        _lk = threading.Lock()

        def _chain_order():
            with _lk:
                alive = [(nm, fn) for nm, fn in PRICE_CHAIN if _fail[nm] < _dead_after]
                return sorted(alive, key=lambda x: -_ok[x[0]])

        # ★ 해외 소스(yfinance)는 국내 상장폐지 종목을 **구조적으로** 갖고 있지 않다.
        #   지난 실행에서 전 소스 실패 1,499종목이 거의 전부 폐지분이었고, 그 전부가
        #   yfinance 를 두 번씩(.KS/.KQ) 때리며 종목당 한 줄씩 표준출력을 뱉었다.
        #   그 출력 폭탄이 Jupyter 의 IOPub 한도를 터뜨려 실행 자체를 방해했다.
        #   못 줄 게 확실한 소스에 묻지 않는 것이 로그 억제보다 근본적이다.
        _no_yf = {c for c, d in delist.items() if pd.notna(d)}

        def _one(job):
            code, st = job
            for nm, fn in _chain_order():
                if nm == "yfinance" and code in _no_yf:
                    continue
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if nonempty(d):
                    d = d.dropna(subset=["date"])
                    if nonempty(d):
                        with _lk:
                            _ok[nm] += 1
                            _fail[nm] = 0
                        return d
                with _lk:
                    _fail[nm] += 1
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        _dropped = [nm for nm, _fn in PRICE_CHAIN if _fail[nm] >= _dead_after]
        if _dropped:
            LOG.warn(f"연속 {_dead_after}회 실패로 이번 실행에서 내린 가격 소스: {_dropped}. "
                     f"(고정 순서로 두면 죽은 소스의 비용을 전 종목이 지불합니다) "
                     f"성공 분포: {dict(_ok)}")
        failed, tried_all = [], []
        for (c, st), d in zip(todo, res):
            # ★ 성공도 반드시 기록한다. 실패만 남기면 '소스가 줄 수 있는 최초일'을 배우지
            #   못해 다음 실행이 같은 백필을 무한히 반복한다(이번 17.5분의 정체).
            tried_all.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
        if tried_all:
            _prev = _att if _att is not None and len(_att) else None
            _all = pd.concat([_prev, pd.DataFrame(tried_all)], ignore_index=True) \
                if _prev is not None else pd.DataFrame(tried_all)
            _all = (_all.sort_values("attempted_at")
                        .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                            source="fetch_prices:attempt_ledger")
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.


    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        avail = [nm for nm, _fn in PRICE_CHAIN
                 if (nm != "pykrx" or pykrx_stock is not None)
                 and (nm != "fdr" or fdr is not None)
                 and (nm != "yfinance" or yf is not None)]
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            f"  · 시도한 소스 체인 : {', '.join(nm for nm, _ in PRICE_CHAIN)}\n"
            f"  · 이번 실행에서 사용 가능했던 소스 : {', '.join(avail) or '없음'}\n"
            f"  · 대상 종목 {len(codes):,}개 / 신규 수집 시도 {len(todo):,}개\n"
            "  진단: ① 네트워크에서 fchart.stock.naver.com 접근이 되는지\n"
            "        ② FinanceDataReader / pykrx 가 설치돼 있는지\n"
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
    px = px[(px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)]

    if new_frames:
        # ★ 전체 재기록 금지. 실측: 697만 행 캐시에 58종목을 더하려고 350MB 를 통째로
        #   다시 쓰고(2.7초) 백업까지 복사했다(2.9초). 매 실행 반복되는 순수 낭비다.
        #   새로 받은 것만 조각으로 덧붙이면 0.04초다. 본체는 손대지 않는다.
        _new = pd.concat(new_frames, ignore_index=True)
        _new["date"] = as_ts_series(_new["date"])
        _new["code"] = _new["code"].map(to_code6)
        _new = _new.dropna(subset=["code", "date", "close"])
        for _c in ("open", "high", "low", "close", "volume", "amount"):
            if _c in _new.columns:
                _new[_c] = pd.to_numeric(_new[_c], errors="coerce")
        _new = (_new.sort_values(["code", "date"])
                    .drop_duplicates(["code", "date"], keep="last").reset_index(drop=True))
        VAULT.append_table("krx_ohlcv_daily", downcast(_new), scope="shared", domain="price",
                           source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common()))
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if src_used.get("naver", 0) or src_used.get("yfinance", 0):
            LOG.warn("네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "V6 유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향).")
    PIPE.io("OUT", "DRIVE", "krx_ohlcv_daily", px, source="price chain")
    return downcast(px)


def build_price_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 기준 가격 패널 + 익월 시가 체결가 + 20일 평균거래대금(ADV).

    체결은 '신호 산출일 다음 거래일 시가'(§10.1). 당일 종가 체결은 미래누수다.
    """
    # ══════════════════════════════════════════════════════════════════════════════
    #  월 패널 캐시 — 일봉이 안 바뀌었으면 다시 계산하지 않는다
    #
    #  ★ 실측: 700만 행에서 이 함수가 36.4초를 쓴다(rolling(20) + groupby tail + shift).
    #    일봉 캐시가 그대로인 재실행에서도 매번 전액을 다시 낸다. 지문이 같으면 건너뛴다.
    #    지문 = (행수, 종목수, 최종일, 최초일, 월격자 범위). 일봉이 한 행이라도 늘면
    #    행수가 달라지므로 지문이 깨지고 자동으로 재계산된다 — 낡은 값이 남을 수 없다.
    # ══════════════════════════════════════════════════════════════════════════════
    _fp = ""
    try:
        _d = as_ts_series(px["date"])
        _fp = sha1_str("pxpanel_v2", str(len(px)), str(px["code"].nunique()),
                       str(_d.min()), str(_d.max()),
                       str(months.min()), str(months.max()), str(len(months)))
        _cm = VAULT.get_table(f"price_panel_monthly_{_fp[:12]}", scope="shared")
        if nonempty(_cm):
            for _c in ("month", "signal_date", "next_date"):
                if _c in _cm.columns:
                    _cm[_c] = as_ts_series(_cm[_c])
            # ★ parquet 왕복은 datetime64[ns] 를 [ms] 로 바꿔 놓는다. 값은 같지만 dtype 이
            #   다르면 하류 merge 가 **예외 없이 0행 매칭**을 낼 수 있다 — PIT 시총이
            #   정확히 그렇게 죽었다. 계산 경로와 똑같이 downcast 를 태워 dtype 을 못박는다.
            _cm = downcast(_cm)
            LOG.ok(f"월 패널 캐시 적중 — 일봉이 그대로라 재계산을 건너뜁니다 "
                   f"({len(_cm):,}행 · 실측 36초 절약). 일봉이 한 행이라도 늘면 "
                   f"지문이 달라져 자동으로 다시 계산합니다.")
            PIPE.io("OUT", "MEM", "price_panel_monthly", _cm, source="cache")
            return {"daily": px, "monthly": _cm}
    except Exception as e:                                       # noqa
        LOG.debug(f"월 패널 캐시 조회 건너뜀({type(e).__name__})")

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

    # ★ volume 을 반드시 실어 보낸다. 없으면 V6 의 '거래정지' 판정이 col(p,"volume") 에서
    #   전부 NaN 이 되어 halted 가 항상 False → 거래정지 종목이 그대로 매수 후보에 남는다.
    #   예외는 안 나고 거부권 절반이 조용히 죽는다.
    monthly = last[["code", "month", "date", "close", "adv20", "volume",
                    "next_open", "next_date"]].copy()
    monthly = monthly.rename(columns={"date": "signal_date"})
    monthly = monthly[monthly["month"].isin(months)]

    # 월간 수익률(체결가→체결가). 상장폐지 처리는 backtest 엔진에서 -100% 로 강제한다.
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
    # ★ 체결가가 0 이면 나눗셈이 ±inf 를 낸다. 실측 재현: 한 달 종가가 0(데이터 오류·정리매매)
    #   인 종목이 다음 달 정상가로 돌아오면 fwd_ret = +inf 다. 가드가 코드 어디에도 없었고,
    #   그 값이 그대로 포트폴리오 수익률로 들어가면 CAGR·Sharpe 가 통째로 무의미해진다.
    #   실제로 R3 직교화가 이 inf 때문에 LinAlgError 로 죽었다(회귀행렬에 inf).
    #   → 0/음수 체결가는 '가격을 모른다'로 처리한다. 0으로 채우지 않는다(그건 -100% 라는
    #     주장이고, 상장폐지 처리는 백테스트 엔진이 따로 -100% 로 강제한다).
    _px_ok = pd.to_numeric(monthly["exec_px"], errors="coerce") > 0
    monthly["exec_px"] = monthly["exec_px"].where(_px_ok)
    _n_bad_px = int((~_px_ok).sum())
    monthly["fwd_ret"] = (nxt_px / monthly["exec_px"] - 1.0).where(adjacent)
    _fr = pd.to_numeric(monthly["fwd_ret"], errors="coerce")
    _n_inf = int(np.isinf(_fr).sum())
    monthly["fwd_ret"] = _fr.replace([np.inf, -np.inf], np.nan)
    # 극단값도 보고한다. 월 +2000% 는 대개 액면분할·병합 미조정이지 실수익이 아니다.
    _n_wild = int((monthly["fwd_ret"].abs() > 20.0).sum())
    if _n_bad_px or _n_inf or _n_wild:
        LOG.warn(f"체결가 이상 {_n_bad_px:,}행(0 또는 음수) · fwd_ret ±inf {_n_inf:,}행 · "
                 f"|월수익| > 2000% {_n_wild:,}행 을 결측 처리했습니다. 0 으로 채우지 "
                 f"않습니다 — 그건 '-100% 였다'는 주장이고, 상장폐지는 백테스트 엔진이 "
                 f"따로 -100% 로 강제합니다. (inf 가 남으면 성과지표와 회귀가 통째로 "
                 f"무의미해집니다)")
        monthly.loc[monthly["fwd_ret"].abs() > 20.0, "fwd_ret"] = np.nan
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    monthly = downcast(monthly)
    if _fp:
        try:
            VAULT.put_table(f"price_panel_monthly_{_fp[:12]}", monthly, scope="shared",
                            domain="price", source="build_price_panel",
                            extra={"note": "일봉 지문별 월패널 캐시 — 일봉이 바뀌면 자동 무효화"})
        except Exception as e:                                   # noqa
            LOG.debug(f"월 패널 캐시 저장 건너뜀({type(e).__name__})")
    return {"daily": px, "monthly": monthly}


def fetch_investor_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다."""
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용")
        cached["date"] = as_ts_series(cached["date"])
        return cached
    if pykrx_stock is None or RUN_MODE == "CACHED":
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})

    def _one(code: str):
        # ★ 여기도 KRXG 게이트를 통과시킨다. 8스레드가 pykrx 를 직접 때리면 CD011 폭풍으로
        #   d3(수급)가 대량 실패한다 — 게이트가 직렬화하므로 느리지만 실제로 데이터가 온다.
        d = KRXG.call(pykrx_stock.get_market_trading_value_by_date,
                      as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
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

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 8), desc="수급 수집")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.warn("수급 데이터를 받지 못했습니다 — d3 결측 처리.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])
    fl = pd.concat(got, ignore_index=True)
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)
