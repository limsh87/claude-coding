

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]

# 전 소스에서 실패한 종목을 며칠간 다시 묻지 않을 것인가.
RETRY_AFTER_DAYS = 30
# ★ 만료된 종목이 한꺼번에 되살아나 한 실행이 폭발하지 않도록 실행당 재시도 상한을 둔다.
#   예전엔 이 상한이 없었고, 시계마저 상수라 만료 자체가 일어나지 않아 문제가 가려져 있었다.
#   시계를 실제 날짜로 고치는 순간 1,000종목이 동시에 만료될 수 있다(≈28분).
PRICE_RETRY_BUDGET_PER_RUN = 200

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★★ 수익률 무결성 (7회차 실행에서 두 개의 증상으로 동시에 드러난 하나의 결함) ★★
#
#  증상 ①  R0 벤치마크가 CAGR inf% / MDD nan% 를 출력했다.
#  증상 ②  보유종목 상위 5%(20종목)가 총기여의 180% 를 만들었다.
#
#  두 증상의 원인은 같다 — fwd_ret 에 **가격으로는 불가능한 값**이 섞여 있었다.
#    fwd_ret = 다음달 체결가 / 이번달 체결가 − 1
#  분모(exec_px)는 next_open 이 없으면 close 로 폴백하는데, 소스가 0 이나 결측을 0 으로
#  준 종목에서 이 값이 **0** 이 된다. 0 으로 나누면 +inf 다. inf 한 개가 월 평균에
#  들어가면 동일가중 벤치마크의 cumprod 가 그 달에 inf 로 발산하고, 그 다음부터
#  eq/peak = inf/inf = nan 이라 MDD·Calmar 가 통째로 nan 이 된다. 판정식은
#  isfinite(nan)=False 라 **조용히 FAIL** 로 떨어진다 — 벤치마크가 없는데 '벤치마크에
#  졌다'고 보고하는 최악의 형태다.
#
#  분모가 0 이 아니어도 문제는 남는다. 이 파이프라인은 pykrx·FDR·네이버·yfinance 를
#  종목 단위로 섞어 쓰고(캐시도 여러 실행에 걸쳐 섞인다), 소스마다 수정주가 기준이
#  다르다. 액면분할·감자가 한쪽에만 반영돼 있으면 경계 달에서 ±90% 나 +900% 같은
#  '수익률'이 만들어진다. 그 종목이 우연히 선정되면 그 한 종목이 10년 성과를 만든다.
#
#  ▶ 방어는 두 겹이다. 지어내지 않고, 조용히 버리지도 않는다.
#    ① 불가능 판정 — KRX 가격제한(±30%/일)상 물리적으로 나올 수 없는 배율은
#       가격 움직임이 아니라 기업행위(분할·병합·감자) 또는 데이터 오류다. 결측 처리하고
#       **몇 건을 왜 버렸는지 표로 남긴다.** 임계는 실제 거래일 간격으로 계산한다.
#    ② 나머지 꼬리는 절대 손대지 않는다. 대신 상위 |수익률| 분포를 표로 출력해
#       "이 성과가 몇 종목·몇 달에 의존하는가"를 사용자가 직접 보게 한다.
#
#  ★ 벤치마크(R0)만은 절사평균을 함께 쓴다. 1,500종목 동일가중에서 한 종목의
#    +900% 는 월 +0.6%p 를 만든다 — 실제로 담을 수 없는 수익이 기준선을 밀어 올린다.
#    전략 수익률에는 절사를 적용하지 않는다(그건 성과를 지어내는 것이다).
# ══════════════════════════════════════════════════════════════════════════════════════════
KRX_DAILY_LIMIT = 0.30        # KRX 일일 가격제한폭 (2015-06-15 이후 ±30%)
RET_LIMIT_SLACK = 1.10        # 시가 갭·정리매매·거래일 계산 오차 여유
RET_SANITY_LEDGER: List[dict] = []     # 무엇을 왜 버렸는지 — 표로 출력하고 드라이브에 남긴다


def _price_limit_envelope(n_days: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """n 거래일 동안 가격제한만으로 도달 가능한 배율의 [하한, 상한].

    n 이 결측이면 한 달치(20거래일)로 본다. 이 봉투는 매우 관대하다(20일이면 [8e-4, 190]) —
    의도적이다. 실제 수익을 자르는 것이 아니라 **물리적으로 불가능한 값만** 걷어내는 것이
    목적이다. 좁히고 싶다면 그건 별개의 결정이며 리포트에 명시해야 한다.
    """
    n = pd.to_numeric(n_days, errors="coerce").fillna(20.0).clip(lower=1.0, upper=45.0)
    up = np.power(1.0 + KRX_DAILY_LIMIT, n) * RET_LIMIT_SLACK
    dn = np.power(1.0 - KRX_DAILY_LIMIT, n) / RET_LIMIT_SLACK
    return dn, up


def price_cache_floor() -> str:
    """일봉 수집 하한일. **v2·v3 가 반드시 같은 값을 써야 한다.**

    ★★ 예전엔 v2 가 BACKTEST_START−15개월, v3 가 −18개월이었다. 89일 차이가
      계획 루프의 10일 임계를 넘으므로, **v2 가 채운 캐시는 v3 에서 전부 '앞 구간 결손'
      으로 판정되고 그 반대도 마찬가지**였다. 두 전략을 번갈아 돌리면 서로가 서로의
      캐시를 매 실행 재수집 대상으로 만든다 — 1,834종목 × 0.5초 = 917초로
      관측치 916.7초와 정확히 일치한다.
      캐시는 공용이다. 공용 자원의 경계값은 한 곳에서만 정의한다.
    """
    return (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d")


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
    if pykrx_stock is None:
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_ohlcv(start.replace("-", ""), end.replace("-", ""), code)
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
    # ★ 이름은 FDR 이지만 6자리 KRX 코드는 FinanceDataReader 내부에서 NaverDailyReader 로
    #   라우팅된다(fchart.stock.naver.com). 즉 KRX 가 아니라 네이버다. 그런데 예전엔
    #   krx 버킷(2.0 qps)의 토큰을 먹었다. RateLimiter 는 소스당 전역 단일 간격이라
    #   12스레드가 0.5초 슬롯 하나를 나눠 쓰게 되고, 실효 동시성이 1로 떨어진다.
    #   실측: 1,833건 × 0.5초 = 916.5초 ≈ 관측 916.7초 — 수집 시간의 100%가 이 대기였다.
    if fdr is None:
        return None
    try:
        limiter("naver").wait()
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


# 코드 → 야후 접미사 힌트. fetch_prices 가 상장정보(sec)로 채워 넣는다.
# 비어 있으면 종전대로 .KS → .KQ 양쪽을 시도한다(동작은 같고, 채워지면 호출이 절반이 된다).
YF_SUFFIX_HINT: Dict[str, str] = {}


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    hint = YF_SUFFIX_HINT.get(code)
    sufs = ((hint, ".KQ" if hint == ".KS" else ".KS") if hint else (".KS", ".KQ"))
    for suf in sufs:
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
                 sec: Optional[pd.DataFrame] = None,
                 market_last_day=None) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. 캐시 증분 갱신. 공용 인덱스에 저장.

    market_last_day: 시장의 마지막 영업일(유니버스 스냅샷에서 받는다). 증분 종료 판정의
      앵커다. 없으면 end 를 쓰지만, 그러면 BACKTEST_END 가 연휴 뒤에 놓일 때
      존재하지 않는 구간을 전 종목에 한꺼번에 묻게 된다(실측 ≈83분).
    """
    codes = sorted({c for c in map(to_code6, codes) if c})
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
    # ★★ 시계 ★★ 예전엔 `_today = as_ts(end)` 였다. end 는 BACKTEST_END **상수**다.
    #   그래서 attempted_at 도 전 행 같은 값으로 기록됐고 `(_today - at).days` 가 항상 0 —
    #   음성캐시가 **영원히 만료되지 않았고** RETRY_AFTER_DAYS 는 죽은 상수였다.
    #   더 나쁜 것은 병합이다: 전 행이 동률이라 `sort_values(1키).drop_duplicates(keep="last")`
    #   가 사실상 무작위가 되어, 새 기록이 확정적으로 살아남지 못했다.
    #   → 실제 시각으로 기록한다. 다만 **생략 판정의 1차 근거는 시계가 아니라 사실**이다
    #     (폐지일 · 워터마크 · 상장일). 시계 만료는 보조이며, 만료가 한꺼번에 터져
    #     한 실행이 폭발하지 않도록 실행당 재시도 예산을 둔다.
    _today = as_ts(_dt.datetime.now().date())
    attempts: Dict[Tuple[str, str], dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att = _att.copy()
        _att["attempted_at"] = as_ts_series(_att["attempted_at"])
        _att["requested_from"] = as_ts_series(_att["requested_from"])
        # 레거시 행에는 kind 가 없다 — 최초 수집 실패로 간주한다(그 시절 유일한 기록 경로).
        if "kind" not in _att.columns:
            _att["kind"] = "init"
        _att["kind"] = _att["kind"].fillna("init").astype(str)
        # ★ 정렬 안정성에 기대지 않는다. (code, kind) 별로 **가장 최근 시각**을 명시 선택.
        _idx = _att.groupby(["code", "kind"])["attempted_at"].idxmax()
        _att = _att.loc[_idx]
        attempts = {(str(r.code), str(r.kind)): {"at": r.attempted_at, "frm": r.requested_from}
                    for r in _att.itertuples(index=False)}
    _retry_budget = [PRICE_RETRY_BUDGET_PER_RUN]

    def _recently_failed(c: str, want_from: pd.Timestamp, kind: str) -> bool:
        """이 종목의 **이 방향** 요청이 최근에 실패했는가.

        ★ 예전엔 kind 구분이 없어서, '최초 수집'이 한 번 실패한 종목(frm=가능한 최소값)이
          이후 **어떤 증분 요청도 받지 못하고 영구히 얼어붙었다.** 그 종목은 다른 전략이
          캐시해 둔 시점에 동결되어 최근 구간 봉이 통째로 결측이 된다 — 시간을 아끼는 게
          아니라 결과를 왜곡하는 경로다.
        """
        p = attempts.get((c, kind))
        if p is None or pd.isna(p["at"]):
            return False
        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 되지 않는다(같은 kind 안에서만).
        if pd.notna(p["frm"]) and p["frm"] > want_from:
            return False
        if (_today - p["at"]).days >= RETRY_AFTER_DAYS:
            # 만료됐다 — 다시 시도할 수 있다. 단 한 실행에서 몰아치지 않게 예산을 쓴다.
            if _retry_budget[0] <= 0:
                return True
            _retry_budget[0] -= 1
            return False
        return True

    # ── 전 구간 재수집을 막는 두 가지 하한 ──────────────────────────────────────────────
    #   ① 상장일 — 그 이전 봉은 존재하지 않는다.
    #   ② 워터마크 — 전 구간을 요청했는데도 더 이전이 안 온 지점. 소스에 없다는 뜻이다.
    listing_of: Dict[str, pd.Timestamp] = {}
    delist_of: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        try:
            _s = sec.dropna(subset=["code"]).drop_duplicates("code")
            _cd = _s["code"].astype(str)
            if "listing_date" in _s.columns:
                listing_of = dict(zip(_cd, as_ts_series(_s["listing_date"])))
            if "delisting_date" in _s.columns:
                delist_of = dict(zip(_cd, as_ts_series(_s["delisting_date"])))
        except Exception:
            listing_of, delist_of = {}, {}
    watermark: Dict[str, pd.Timestamp] = {}
    _wm = VAULT.get_table("price_earliest_available", scope="shared")
    if _wm is not None and len(_wm):
        try:
            watermark = dict(zip(_wm["code"].astype(str), as_ts_series(_wm["earliest"])))
        except Exception:
            watermark = {}

    # ★ 증분 종료 앵커. 예전엔 `end_ts - 5일` 이었는데, BACKTEST_END 가 5일 넘는 연휴 뒤에
    #   놓이면 **생존 종목 전체**에 대해 동시에 참이 되어 존재하지도 않는 하루짜리 구간을
    #   3,000여 종목에 한꺼번에 요청했다(네이버 버킷 전역 하한으로 ≈83분).
    #   → 시장 달력(유니버스 스냅샷의 마지막 영업일)을 앵커로 쓴다. 캐시 자신을 앵커로
    #     쓰면 '캐시가 스스로를 인증하는' 순환이 되어 정당한 증분까지 억제되므로 금지한다.
    mkt_last = as_ts(market_last_day) if market_last_day else end_ts
    if pd.isna(mkt_last):
        mkt_last = end_ts
    mkt_last = min(mkt_last, end_ts)

    todo: List[Tuple[str, str, str, str]] = []
    n_back = n_fwd = n_skip = n_done = 0
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, start_ts, "init"):
                n_skip += 1
                continue
            todo.append((c, start, end, "init"))
            continue
        # ★ 과거 방향 백필을 반드시 함께 본다.
        #   앞선 실행이 최근 구간만 캐시했다면(예: 캐시가 2023~2026 뿐),
        #   max 만 보고 판단하면 2016~2022 를 영원히 못 받는다.
        #   → 10년 백테스트인데 앞 7년이 조용히 비는 사고가 된다.
        #
        #   ★★ 다만 '요청 시작일'을 그대로 기준으로 삼으면 안 된다. 2021년에 상장한 종목은
        #   2015년 봉이 **존재할 수 없으므로** 조건이 영원히 참이고, 매 실행 전 구간을 다시
        #   받는다. 실측: 캐시 3,517종목 중 1,487종목(42%)이 매번 재수집 대상이 되어
        #   가격 단계 992초 중 916초를 이미 갖고 있는 데이터를 다시 받는 데 썼다.
        #   → 상장일과 '이 종목에서 실제로 받아진 최소일' 워터마크로 하한을 올린다.
        want = start_ts
        _ld = listing_of.get(c)
        if _ld is not None and pd.notna(_ld):
            want = max(want, as_ts(_ld))
        _wm = watermark.get(c)
        if _wm is not None and pd.notna(_wm):
            want = max(want, _wm)          # 이미 '더 이전은 없다'가 확인된 지점
        # ★ 증분(앞으로) 방향에도 종료 조건이 필요하다.
        #   폐지 종목의 mx 는 '마지막 거래일'이라 mx < end_ts - 5d 가 **영원히 참**이다.
        #   그래서 매 실행 존재하지도 않는 구간(mx+1 ~ 오늘)을 4개 소스에 물었고,
        #   637종목이 100% 실패하며 640초를 태웠다 — 그것도 매번.
        #   음성캐시는 'mx is None' 가지에서만 조회되므로 이 population 을 못 본다.
        #   → 폐지일이 있으면 그 이후는 애초에 요청하지 않는다. 사실이지 기억이 아니다.
        _dd = delist_of.get(c)
        _closed = (_dd is not None and pd.notna(_dd)
                   and mx >= as_ts(_dd) - pd.Timedelta(days=5))
        # ★★ 분기 **순서**가 결함이었다 ★★
        #   예전엔 n_back 판정이 _closed 보다 **먼저** 평가됐다. 그래서 폐지가 확정된 종목이
        #   유일한 사실기반 가드를 우회해 매 실행 (c, start) = 11.5년 전 구간을 통째로
        #   다시 요청했고, 그것도 _recently_failed 가드조차 없었다. 관측된 640초가 이것이다.
        #   → 백필이 정말 필요한지를 먼저 계산하고, 필요 없으면 폐지 종료조건이 이긴다.
        back_need = (mn is not None and mn > want + pd.Timedelta(days=10))
        if _closed and not back_need:
            n_done += 1                      # 폐지까지 이미 다 받음 — 더 받을 것이 없다
        elif back_need and not _recently_failed(c, want, "back"):
            # ★ **결손 구간만** 요청한다. 예전엔 (c, start) 로 전 구간을 다시 받았다 —
            #   이미 갖고 있는 2,800여 봉을 다시 받느라 종목당 수 초를 태웠고, 게다가
            #   keep="last" 병합 때문에 pykrx 의 실제 거래대금이 네이버 근사(종가×거래량)로
            #   덮이는 데이터 열화까지 일어났다.
            todo.append((c, want.strftime("%Y-%m-%d"),
                         (mn - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "back"))
            n_back += 1
        elif (not _closed) and mx < mkt_last - pd.Timedelta(days=5) and not _recently_failed(
                c, mx + pd.Timedelta(days=1), "fwd"):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), end, "fwd"))
            n_fwd += 1
        else:
            n_skip += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목의 **결손 구간만** 받습니다 "
                 f"(캐시 최소일이 요청 시작일보다 늦음 = 앞 구간 결손). "
                 f"전 구간을 다시 받지 않습니다.")
    if n_done:
        LOG.info(f"폐지일까지 이미 확보된 {n_done:,}종목은 증분 요청을 보내지 않습니다 "
                 f"(폐지 이후 구간은 존재하지 않습니다 — 예전엔 이걸 매 실행 4개 소스에 "
                 f"물어 전량 실패하며 시간을 태웠습니다).")
    if n_skip:
        LOG.info(f"최근 {RETRY_AFTER_DAYS}일 내 전 소스에서 실패한 {n_skip:,}종목은 이번엔 "
                 f"건너뜁니다 (대부분 상장폐지분). {RETRY_AFTER_DAYS}일 뒤 자동 재시도합니다.")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    if todo:
        LOG.info(f"일봉 신규/증분 수집 대상 {len(todo):,}종목")

        def _one(job):
            code, st, en, _kind = job
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, en)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        failed, wm_rows = [], []
        for (c, st, en, kind), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
                # ★ 과거 방향으로 '있는 만큼 다' 요청했는데 이만큼만 왔다면 그 이전은 소스에 없다.
                #   이 워터마크가 없으면 2021년 상장 종목은 2015년 봉이 영영 안 오므로
                #   '앞 구간 결손'으로 판정되어 **매 실행 전 구간을 다시 받는다.**
                #   ★ 조건을 start_ts 가 아니라 want(=이번에 요청한 하한)로 잡는다 —
                #     결손 구간만 요청하도록 바뀌었으므로 start_ts 기준이면 영영 기록되지 않는다.
                if kind in ("init", "back"):
                    _mn = as_ts_series(d["date"]).min()
                    if pd.notna(_mn):
                        wm_rows.append({"code": c, "earliest": _mn,
                                        "requested_from": as_ts(st), "checked_at": _today})
            else:
                failed.append({"code": c, "kind": kind,
                               "requested_from": as_ts(st), "attempted_at": _today})
        if wm_rows:
            _wprev = VAULT.get_table("price_earliest_available", scope="shared")
            _wall = pd.concat([_wprev, pd.DataFrame(wm_rows)], ignore_index=True) \
                if _wprev is not None and len(_wprev) else pd.DataFrame(wm_rows)
            # ★★ 병합을 정렬 안정성에 맡기지 않는다 ★★
            #   예전엔 sort_values("checked_at").drop_duplicates(keep="last") 였는데
            #   checked_at 이 전 행 동률이라 **새 관측이 확정적으로 살아남지 못했다.**
            #   그리고 keep="last" 는 '가장 최근에 본 최소일'을 남겨, 이력이 짧은 소스가
            #   응답한 실행이 이력이 긴 소스의 결과를 덮어 바닥을 영구히 올렸다 —
            #   그 종목의 앞 몇 년이 조용히 빈 채 결과가 나온다.
            #   → 워터마크는 **내려갈 수만 있다**(관측된 최소일의 min). 명시 집계로 못박는다.
            _agg = {"earliest": ("earliest", "min"), "checked_at": ("checked_at", "max")}
            if "requested_from" in _wall.columns:
                _agg["requested_from"] = ("requested_from", "min")
            _wall = (_wall.dropna(subset=["code", "earliest"])
                          .groupby("code", as_index=False).agg(**_agg))
            if VAULT.put_table("price_earliest_available", _wall, scope="shared", domain="price",
                               source="fetch_prices: 소스가 보유한 최초 관측일 워터마크") is None:
                LOG.error("워터마크 저장에 실패했습니다 — 다음 실행이 같은 종목의 앞 구간을 "
                          "다시 받습니다(실측 900초대). 드라이브 용량·권한을 확인하세요.")
            else:
                LOG.info(f"최초 관측일 워터마크 {len(wm_rows):,}종목 기록 — 다음 실행부터 "
                         f"이 종목들의 앞 구간 재수집을 건너뜁니다"
                         f"(상장 이전 구간은 존재하지 않습니다).")
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.
            _prev = VAULT.get_table("price_fetch_attempts", scope="shared")
            _new = pd.DataFrame(failed)
            _all = (pd.concat([_prev, _new], ignore_index=True)
                    if _prev is not None and len(_prev) else _new)
            if "kind" not in _all.columns:
                _all["kind"] = "init"
            _all["kind"] = _all["kind"].fillna("init").astype(str)
            _all["attempted_at"] = as_ts_series(_all["attempted_at"])
            # ★ 병합 키에 kind 를 포함한다. 예전엔 code 단독이라 'init 실패' 한 줄이
            #   그 종목의 fwd·back 기록을 덮어 **어떤 증분 요청도 못 받게** 만들었다.
            #   정렬 안정성 대신 idxmax 로 명시 선택한다(attempted_at 이 동률이어도 결정적).
            _all = _all.dropna(subset=["code"])
            _all = _all.loc[_all.groupby(["code", "kind"])["attempted_at"].idxmax()] \
                       .reset_index(drop=True)
            if VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                               source="fetch_prices:negative_cache") is None:
                LOG.error("시도 원장 저장에 실패했습니다 — 다음 실행이 같은 헛수고를 반복합니다.")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 받을 것이 없으면 아무 일도 하지 않는다 ★★
    #    예전엔 todo 가 비어 있어도(=신규 심볼 0개) 아래 무조건 경로를 통과했다:
    #      concat(700만 행) → code.map(to_code6)(행마다 파이썬 함수 + 정규식 2회)
    #      → to_numeric ×6 → sort_values(2키) → drop_duplicates(2키)
    #    실측 51.6초. **한 종목도 새로 받지 않은 실행에서** 매번 그만큼 태웠다.
    #    캐시는 바로 이 함수가 정규화해서 쓴 것이므로 다시 정규화할 이유가 없다.
    if not new_frames and cached is not None and len(cached):
        px = cached
        win = (px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)
        px_out = px[win]
        LOG.ok(f"일봉 신규 수집 0건 — 공용 캐시 {len(px):,}행을 그대로 재사용합니다 "
               f"(재정규화·재정렬·재저장 없음). 창 적용 후 {len(px_out):,}행.")
        PIPE.io("IN", "DRIVE", "krx_ohlcv_daily", px_out, source="cache only (no refetch)")
        return downcast(px_out)

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
    # ★★ 정규화는 **신규분에만** 적용한다 ★★
    #   캐시 7.09M 행은 직전 실행에서 바로 이 파이프라인을 통과해 저장된 것이므로,
    #   다시 거는 것은 항등변환이다. 실측으로 `code.map(to_code6)` 6.3~8.4초,
    #   dropna/to_numeric/sort/dedup 을 합쳐 24.4초가 매 실행 순낭비였다.
    #   그리고 to_code6 은 행마다 파이썬 함수 + 정규식 2회다 → **고유값 사전**으로 대체한다.
    if new_frames:
        nf = pd.concat(new_frames, ignore_index=True)
        nf["date"] = as_ts_series(nf["date"])
        _s = nf["code"].astype(object)
        _m = {k: to_code6(k) for k in pd.unique(_s)}
        nf["code"] = _s.map(_m)
        nf = nf.dropna(subset=["code", "date", "close"])
        for c in ("open", "high", "low", "close", "volume", "amount"):
            nf[c] = pd.to_numeric(nf[c], errors="coerce")
    else:
        nf = None
    _parts = ([cached] if cached is not None and len(cached) else []) + \
             ([nf] if nf is not None and len(nf) else [])
    px = pd.concat(_parts, ignore_index=True) if len(_parts) > 1 else _parts[0]
    # ★ 중복 제거 방향에 주의. keep="last" 는 '나중 프레임이 이긴다'인데, 신규분이
    #   네이버(거래대금 = 종가×거래량 근사)이고 캐시분이 pykrx(실제 거래대금)이면
    #   **정확한 값이 근사로 덮인다.** 겹치는 (code,date) 는 캐시를 우선한다.
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="first"))
    # ★★ 공용 캐시 보존 (절대 1원칙) ★★
    #   반환값은 이번 백테스트 창(+400일 워밍업)으로 자르는 게 맞지만, **그 잘린 프레임을
    #   공용 테이블에 그대로 써버리면** 창 밖의 과거가 활성 parquet 에서 영구히 사라진다.
    #   put_table 은 백업을 남기지만 get_table 은 활성 파일만 읽으므로, 다른 전략(또는 더 이른
    #   시작일로 도는 다음 실행)이 보기에 캐시가 통째로 파괴된 것과 같다.
    #   → 저장은 '기존 캐시 ∪ 신규'로 하고, 반환만 창으로 자른다.
    # 창이 캐시 전체를 덮으면(현 설정에서는 보통 그렇다) 마스킹 자체가 무의미하다 — 단락한다.
    _lo = as_ts(start) - pd.Timedelta(days=400)
    if len(px) and px["date"].min() >= _lo and px["date"].max() <= end_ts:
        px_out = px
    else:
        px_out = px[(px["date"] >= _lo) & (px["date"] <= end_ts)]

    if new_frames:
        # ★ px 는 이미 '기존 캐시 ∪ 신규' 다(위에서 cached 를 통째로 넣었다). 창으로 자른
        #   px_out 이 아니라 px 를 저장한다 — 창 밖의 과거를 잘라 덮어쓰면 다른 전략이
        #   보기에 캐시가 파괴된 것과 같다(절대 1원칙).
        if VAULT.put_table(
                "krx_ohlcv_daily", px, scope="shared", domain="price",
                source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common())) is None:
            LOG.error("일봉 공용 캐시 저장에 실패했습니다 — 이번 실행에서 받은 "
                      f"{sum(len(f) for f in new_frames):,}행이 디스크에 남지 않습니다. "
                      f"다음 실행이 같은 종목을 처음부터 다시 받습니다.")
    px = px_out
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if any(src_used.get(k, 0) for k in ("naver", "yfinance", "fdr")):
            LOG.warn("네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "V6 유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향).")
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
    # ★ groupby(...).tail(1) 은 7.09M 행에서 실측 4.16초. 바로 위 sort_values 로
    #   (code, date) 정렬이 끝나 있고 fetch_prices 가 (code,date) 중복을 이미 제거했으므로
    #   '그룹의 마지막 행' = '다음 행과 (code,ym) 이 다른 행' 이다 — 같은 집합·같은 순서.
    last = px.loc[~px[["code", "ym"]].duplicated(keep="last")].copy()
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

    # 월간 수익률(체결가→체결가). 상장폐지 처리는 backtest 엔진에서 -100% 로 강제한다.
    monthly = monthly.sort_values(["code", "month"])
    # 체결가 = 신호 산출일의 '다음 거래일 시가'. 그 다음 거래일이 너무 멀면(거래정지·상폐 직전)
    # 그 가격으로 체결했다고 가정할 수 없으므로 종가로 폴백한다.
    gap = (monthly["next_date"] - monthly["signal_date"]).dt.days
    monthly["exec_px"] = monthly["next_open"].where(gap.notna() & (gap <= 10))
    monthly["exec_px"] = monthly["exec_px"].fillna(monthly["close"])
    # ★★ 분모 위생 ★★ 0 이나 음수, ±inf 는 '가격'이 아니라 소스가 결측을 0 으로 준 것이다.
    #   이걸 그대로 두면 아래 나눗셈이 +inf 를 만들고, 그 inf 한 개가 벤치마크의 복리를
    #   통째로 발산시킨다(7회차의 CAGR inf% / MDD nan%). 값을 지어내지 않고 결측으로 둔다.
    _px_bad = int((~np.isfinite(monthly["exec_px"].to_numpy(dtype="float64"))
                   ) .sum() + int((monthly["exec_px"] <= 0).sum()))
    monthly["exec_px"] = monthly["exec_px"].replace([np.inf, -np.inf], np.nan)
    monthly["exec_px"] = monthly["exec_px"].where(monthly["exec_px"] > 0)

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    _g = monthly.groupby("code", observed=True)
    nxt_px = _g["exec_px"].shift(-1)
    nxt_m = _g["month"].shift(-1)
    nxt_sd = _g["signal_date"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    ratio = safe_div(nxt_px, monthly["exec_px"])
    monthly["fwd_ret"] = (ratio - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")

    # ── 무결성 게이트 ────────────────────────────────────────────────────────────────────
    #  ① 비유한값 : inf/-inf/NaN 배율. 분모 위생을 거쳤어도 소스가 이상값을 주면 남는다.
    #  ② 가격제한 불가능 : 실제 거래일 간격으로 계산한 봉투 밖. 분할·감자·데이터 오류다.
    fr = monthly["fwd_ret"]
    n_td = _trading_day_gap(px, monthly["signal_date"], nxt_sd)
    lo_env, hi_env = _price_limit_envelope(n_td)
    bad_inf = fr.notna() & ~np.isfinite(fr.to_numpy(dtype="float64"))
    bad_env = fr.notna() & np.isfinite(fr.to_numpy(dtype="float64")) & (
        (ratio > hi_env) | (ratio < lo_env))
    n_inf, n_env = int(bad_inf.sum()), int(bad_env.sum())
    if n_inf or n_env:
        monthly.loc[bad_inf | bad_env, "fwd_ret"] = np.nan
        _ex = monthly.loc[bad_env, ["code", "month"]].copy()
        _ex["ratio"] = ratio[bad_env].to_numpy()
        _ex["n_days"] = n_td[bad_env].to_numpy()
        RET_SANITY_LEDGER.extend(_ex.head(500).to_dict("records"))
        LOG.warn(
            f"★ 수익률 무결성 게이트 — 비유한 {n_inf:,}건 · 가격제한상 불가능 {n_env:,}건을 "
            f"결측 처리했습니다(총 {n_inf+n_env:,}/{int(fr.notna().sum()):,}행). "
            f"이 값들은 주가 움직임이 아니라 **기업행위(액면분할·병합·감자) 미반영 또는 "
            f"소스 혼용에 따른 수정주가 불일치**입니다. 그대로 두면 벤치마크 복리가 발산하고"
            f"(7회차 CAGR inf%), 그 종목 하나가 10년 성과를 만듭니다.")
        if n_env:
            _t = _ex.reindex(_ex["ratio"].abs().sort_values(ascending=False).index).head(10)
            LOG.table([[r.code, f"{as_ts(r.month):%Y-%m}", f"{r.ratio:,.1f}배",
                        f"{int(r.n_days)}일" if np.isfinite(r.n_days) else "-",
                        f"{(1.0+KRX_DAILY_LIMIT)**max(int(r.n_days),1):,.0f}배"
                        if np.isfinite(r.n_days) else "-"]
                       for r in _t.itertuples(index=False)],
                      ["종목", "달", "관측 배율", "거래일", "가격제한상 최대"],
                      ["c", "c", "r", "r", "r"],
                      title="버려진 관측 상위 10건 — 왜 '수익률'이 아닌지 근거")
    if _px_bad:
        LOG.warn(f"체결가가 0 이하이거나 비유한값인 {_px_bad:,}행을 결측 처리했습니다 "
                 f"(소스가 결측을 0 으로 반환한 경우). 0 으로 나눈 +inf 가 하류로 흐르는 "
                 f"경로를 여기서 끊습니다.")

    # ③ 남은 꼬리는 **자르지 않는다.** 대신 보이게 만든다 — 성과가 몇 건에 의존하는지를
    #    사용자가 직접 판단해야 한다. 조용히 winsorize 하면 그건 성과를 지어내는 것이다.
    _report_return_tail(monthly)
    # ★ 원장은 공용 인덱스에 남긴다(절대1원칙: 신규 산출물도 반드시 캐시·재호출 가능).
    if RET_SANITY_LEDGER:
        try:
            VAULT.put_table("price_return_sanity_ledger", pd.DataFrame(RET_SANITY_LEDGER),
                            scope="shared", domain="price",
                            source="build_price_panel: 가격제한 초과·비유한 수익률 폐기 원장")
        except Exception as e:                                       # noqa
            LOG.debug(f"수익률 무결성 원장 저장 실패({type(e).__name__}) — 계산에는 영향 없음")

    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def _trading_day_gap(px: pd.DataFrame, d0: pd.Series, d1: pd.Series) -> pd.Series:
    """두 날짜 사이의 **실제 거래일 수**. 달력일이 아니라 거래일이어야 가격제한 봉투가 맞다.

    시장 전체의 거래일 배열에 searchsorted 를 두 번 하면 끝난다 — 종목 루프 없음(원칙 3).
    """
    try:
        td = np.sort(pd.unique(as_ts_series(px["date"]).values))
        if not len(td):
            return pd.Series(np.nan, index=d0.index, dtype="float64")
        a = np.searchsorted(td, as_ts_series(d0).values, side="left")
        b = np.searchsorted(td, as_ts_series(d1).values, side="left")
        out = (b - a).astype("float64")
        out[~np.isfinite(pd.to_numeric(as_ts_series(d1), errors="coerce").to_numpy())] = np.nan
        return pd.Series(out, index=d0.index)
    except Exception:                                                # noqa
        return pd.Series(np.nan, index=d0.index, dtype="float64")


def _report_return_tail(monthly: pd.DataFrame) -> None:
    """월수익 분포의 꼬리를 표로 남긴다. 자르지 않고 **보이게** 하는 것이 목적이다."""
    r = pd.to_numeric(monthly.get("fwd_ret"), errors="coerce").dropna()
    if len(r) < 100:
        return
    qs = [0.001, 0.01, 0.05, 0.50, 0.95, 0.99, 0.999]
    v = r.quantile(qs)
    LOG.table([[f"{q*100:g}%", f"{v.loc[q]:+.1%}"] for q in qs] +
              [["최소", f"{r.min():+.1%}"], ["최대", f"{r.max():+.1%}"],
               [">+100% 건수", f"{int((r > 1.0).sum()):,}"],
               ["<-50% 건수", f"{int((r < -0.5).sum()):,}"]],
              ["분위", "월수익률"], ["c", "r"],
              title=f"월수익률 분포 ({len(r):,}행) — 극단 꼬리가 성과를 만드는지 확인용")


def fetch_investor_flows(codes: Sequence[str], start: str, end: str,
                         sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다.

    ★ 증분 계획은 가격과 **같은 규칙**을 쓴다. 예전에는 여기에만 상장일 하한도,
      폐지 종료조건도, 음성 원장도 없어서 BACKTEST_START 이후 상장한 종목은
      `lo_c > need_lo + 10d` 가 영원히 참이라 매 실행 전 구간을 백필했다.
    """
    need_lo, need_hi = as_ts(start), as_ts(end)
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    have_hi: Dict[str, pd.Timestamp] = {}
    have_lo: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached = cached.copy()                      # 공용 캐시 객체를 제자리에서 고치지 않는다
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        lo, hi = cached["date"].min(), cached["date"].max()
        _g = cached.groupby("code")["date"]
        have_hi, have_lo = _g.max().to_dict(), _g.min().to_dict()
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용 "
                 f"({lo:%Y-%m} ~ {hi:%Y-%m} · {cached['code'].nunique():,}종목)")
    if pykrx_stock is None or RUN_MODE == "CACHED":
        if cached is not None and len(cached):
            _lo, _hi = cached["date"].min(), cached["date"].max()
            if pd.notna(_lo) and pd.notna(_hi) and (_lo > need_lo + pd.Timedelta(days=45) or
                                                    _hi < need_hi - pd.Timedelta(days=45)):
                LOG.warn(f"수급 캐시가 요청 구간({need_lo:%Y-%m}~{need_hi:%Y-%m})을 다 덮지 "
                         f"못하고, 이번 실행에서는 넓힐 수단이 없습니다"
                         f"(pykrx 미설치 또는 CACHED 모드) — 덮이지 않는 달의 d3 는 결측이 되고 "
                         f"U 는 d1 단독으로 계산됩니다. 0으로 채우지 않습니다.")
            return cached
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})
    # ★★ 증분 수집 ★★
    #   예전엔 캐시가 있으면 **무조건 통째로 반환**하고 끝이었다. 그래서 다른 전략이 더 짧은
    #   구간으로 만들어 둔 캐시를 물려받으면 요청 구간의 뒷부분 d3 가 조용히 전부 결측이 됐고,
    #   넓히려면 전체를 다시 받는 수밖에 없었다(그래서 아무도 안 넓혔다).
    #   → 종목별로 '캐시가 못 덮는 구간'만 받는다. 캐시는 그대로 두고 합집합으로 저장한다.
    # 가격과 같은 하한/종료조건을 쓴다 — 상장 이전 구간과 폐지 이후 구간은 존재하지 않는다.
    f_listing: Dict[str, pd.Timestamp] = {}
    f_delist: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        try:
            _s = sec.dropna(subset=["code"]).drop_duplicates("code")
            _cd = _s["code"].astype(str)
            if "listing_date" in _s.columns:
                f_listing = dict(zip(_cd, as_ts_series(_s["listing_date"])))
            if "delisting_date" in _s.columns:
                f_delist = dict(zip(_cd, as_ts_series(_s["delisting_date"])))
        except Exception:                                           # noqa
            f_listing, f_delist = {}, {}
    # 음성 원장 — 빈 응답이 got 필터에서 조용히 사라져 다음 실행이 같은 구간을 재요청했다.
    _fatt = VAULT.get_table("flow_fetch_attempts", scope="shared")
    f_skip: set = set()
    if _fatt is not None and len(_fatt):
        try:
            _fatt = _fatt.copy()
            _fatt["attempted_at"] = as_ts_series(_fatt["attempted_at"])
            _age = (as_ts(_dt.datetime.now().date()) - _fatt["attempted_at"]).dt.days
            f_skip = set(zip(_fatt.loc[_age.fillna(10 ** 6) < RETRY_AFTER_DAYS, "code"].astype(str),
                             _fatt.loc[_age.fillna(10 ** 6) < RETRY_AFTER_DAYS, "kind"].astype(str)))
        except Exception:                                           # noqa
            f_skip = set()

    jobs: List[Tuple[str, str, str, str]] = []
    for c in codes:
        hi_c, lo_c = have_hi.get(c), have_lo.get(c)
        want = need_lo
        _ld = f_listing.get(c)
        if _ld is not None and pd.notna(_ld):
            want = max(want, as_ts(_ld))
        _dd = f_delist.get(c)
        if hi_c is None:
            if (c, "init") not in f_skip:
                jobs.append((c, want.strftime("%Y-%m-%d"), end, "init"))
            continue
        _closed = (_dd is not None and pd.notna(_dd)
                   and hi_c >= as_ts(_dd) - pd.Timedelta(days=5))
        if lo_c is not None and lo_c > want + pd.Timedelta(days=10) and (c, "back") not in f_skip:
            jobs.append((c, want.strftime("%Y-%m-%d"),
                         (lo_c - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "back"))
        if (not _closed) and hi_c < need_hi - pd.Timedelta(days=10) and (c, "fwd") not in f_skip:
            jobs.append((c, (hi_c + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), end, "fwd"))
    if not jobs:
        LOG.ok(f"수급 신규 수집 0건 — 공용 캐시가 요청 구간을 전부 덮습니다({len(cached):,}행).")
        return downcast(cached) if cached is not None else pd.DataFrame(
            columns=["code", "date", "inst_net", "foreign_net"])
    LOG.info(f"수급 증분 수집 {len(jobs):,}건 (전 종목 재수집이면 {len(codes):,}건)")

    def _one(job):
        code, st, en, _kind = job
        try:
            limiter("krx").wait()
            d = pykrx_stock.get_market_trading_value_by_date(
                as_ts(st).strftime("%Y%m%d"), as_ts(en).strftime("%Y%m%d"), code)
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

    res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="수급 증분 수집")
    got = [d for d in res if d is not None and len(d)]
    # ★ 빈 응답을 기억한다. 예전엔 got 필터에서 조용히 사라져 다음 실행이 같은 구간을
    #   그대로 다시 요청했다 — '수집 실패'와 '원래 자료가 없음'을 구별하지 못했다.
    _fail = [{"code": j[0], "kind": j[3], "requested_from": as_ts(j[1]),
              "attempted_at": as_ts(_dt.datetime.now().date())}
             for j, d in zip(jobs, res) if d is None or not len(d)]
    if _fail:
        try:
            _fp = VAULT.get_table("flow_fetch_attempts", scope="shared")
            _fa = (pd.concat([_fp, pd.DataFrame(_fail)], ignore_index=True)
                   if _fp is not None and len(_fp) else pd.DataFrame(_fail))
            _fa["attempted_at"] = as_ts_series(_fa["attempted_at"])
            _fa = _fa.loc[_fa.groupby(["code", "kind"])["attempted_at"].idxmax()] \
                     .reset_index(drop=True)
            VAULT.put_table("flow_fetch_attempts", _fa, scope="shared", domain="flow",
                            source="fetch_investor_flows:negative_cache")
            LOG.info(f"수급 미수신 {len(_fail):,}건을 시도 원장에 기록했습니다 — "
                     f"{RETRY_AFTER_DAYS}일간 다시 묻지 않습니다.")
        except Exception as e:                                      # noqa
            LOG.warn(f"수급 시도 원장 저장 실패({type(e).__name__}).")
    if not got:
        LOG.warn("수급 신규분을 받지 못했습니다 — 캐시분만 사용합니다(d3 부분 결측).")
        return downcast(cached) if cached is not None and len(cached) else pd.DataFrame(
            columns=["code", "date", "inst_net", "foreign_net"])
    # ★ 저장은 '기존 캐시 ∪ 신규'. 잘라서 덮어쓰면 다른 전략이 쌓아 둔 과거가 사라진다(절대1원칙).
    fl = pd.concat(([cached] if cached is not None and len(cached) else []) + got,
                   ignore_index=True)
    fl["date"] = as_ts_series(fl["date"])
    fl = (fl.dropna(subset=["code", "date"])
            .sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)
