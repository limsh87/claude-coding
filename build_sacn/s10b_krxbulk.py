# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-K  KRX 인증 + MDC 벌크 스냅샷 + 증권유형 분류                                          ║
# ║                                                                                          ║
# ║  ★ 이 조각이 새로 생긴 이유 (실측 로그의 연쇄 실패)                                        ║
# ║    사용자 환경(파이썬 3.14)에서 pykrx 설치가 실패했다. 그 순간 시가총액·PBR 스냅샷이       ║
# ║    통째로 사라졌고, 그 결과 ⓐ §5 시총하한 ⓑ §6.3 log(MktCap) ⓒ 시총하위1000 비교아암      ║
# ║    ⓓ BM 직교화가 전부 죽었다. 라이브러리 하나가 전략의 절반을 데려간 것이다.               ║
# ║                                                                                          ║
# ║    pykrx 가 하는 일은 결국 data.krx.co.kr 의 getJsonData.cmd 를 부르는 것뿐이다.           ║
# ║    그 호출을 우리가 직접 하면 pykrx 유무와 무관해진다. requests 만 있으면 된다.            ║
# ║                                                                                          ║
# ║  ★ 호출 축(axis)의 선택 — 여기가 설계의 핵심이다                                           ║
# ║    같은 데이터를 받는 방법이 둘 있다:                                                      ║
# ║      · 종목축: 종목 1개 = 1호출, 10년치 반환      → 5,398호출                              ║
# ║      · 날짜축: 날짜 1개 = 1호출, 전종목 반환      → 2,470호출(일별) / 120호출(월말)        ║
# ║    일별 전체가 필요하면 종목축이 낫고(반환량이 크다), 월말 스냅샷만 필요하면 날짜축이      ║
# ║    45배 싸다. 시총·PBR 은 월말만 필요하다 → 날짜축 120호출로 10년이 끝난다.                ║
# ║    이걸 종목축으로 짜면 같은 데이터에 5,398호출을 쓴다. 그게 '쓸데없는 반복'이다.          ║
# ║                                                                                          ║
# ║  ★ bld 식별자는 하드코딩하되 '후보 목록'으로 둔다. KRX 는 화면 개편 때 bld 를 바꾼다.       ║
# ║    하나를 믿고 죽는 대신, 후보를 순서대로 두드려 보고 성공한 것을 기억한다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


class KRXAuth:
    """KRX 데이터 마켓플레이스 인증. 실패해도 절대 죽지 않고 폴백으로 넘긴다.

    2026년 기준 경로 3가지:
      ① KRX Open API (data-dbg.krx.co.kr) — 인증키. ★단, 엔드포인트별로 '이용신청'이 따로 필요하고
         승인에 하루 정도 걸린다. 키만 있다고 바로 되는 게 아니다. 상장폐지 API 는 존재하지 않는다.
      ② 마켓플레이스 getJsonData.cmd (bld 기반). pykrx 가 쓰는 경로.
         ★ 대부분의 bld 는 비로그인으로도 응답한다. 로그인은 '되면 좋은 것'이지 전제가 아니다.
           예전 구현은 session_ok 가 아니면 즉시 None 을 돌려줘서, 로그인 정보를 안 넣은
           사용자는 KRX 경로를 통째로 못 쓰고 있었다 — 그래서 익명 시도를 먼저 한다.
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
        self.anon_ok: Optional[bool] = None      # None=미확인
        self.last_status = ""                    # 마지막 bld 응답 앞부분 (진단용)
        self._openapi_mode = "query"
        self._lk = threading.RLock()
        self._logged_in_once = False

    # ── 로그인 ──────────────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        if self.apikey:
            self.openapi_ok = self._probe_openapi()
            self.status = "OPENAPI_OK" if self.openapi_ok else "OPENAPI_KEY_UNAUTHORIZED"
            if not self.openapi_ok:
                LOG.warn("KRX Open API 키는 있으나 해당 엔드포인트 호출이 거부되었습니다. "
                         "KRX Open API 는 '엔드포인트별 이용신청'이 따로 필요하고 승인에 하루 정도 "
                         "걸립니다. 키 발급만으로는 즉시 사용할 수 없습니다. "
                         "→ 마켓플레이스 bld 경로로 계속 진행합니다(같은 데이터를 받습니다).")
        if not (self.user and self.pw):
            self.status = self.status if self.openapi_ok else "NO_CREDENTIALS"
            LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 익명 bld 경로를 먼저 시도합니다. "
                     "대부분의 통계 화면(전종목시세·PER/PBR)은 비로그인으로도 응답합니다.")
            return self.openapi_ok
        with self._lk:
            # ★ 실패도 기억한다. 예전엔 성공만 memoize 해서, 비밀번호가 틀리면
            #   bld 호출마다 워밍업 2 + 로그인 POST 2(각 내부 3회 재시도)를 2 QPS 로
            #   다시 돌았다. 120개월 × 8일 walk-back 이면 몇 시간이 순수 재로그인이고,
            #   KRX 쪽에는 실패 로그인 수천 건이 쌓인다.
            if self._logged_in_once:
                return self.session_ok or self.openapi_ok
            self._logged_in_once = True
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
                             "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 "
                             "종료됩니다. 두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                    continue
                if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                    self.session_ok = True
                    self.status = "LOGIN_OK"
                    LOG.ok("KRX 마켓플레이스 로그인 성공.")
                    return True
            self.status = "LOGIN_FAILED"
            LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                     "익명 bld / FDR / 네이버 경로로 폴백하며 백테스트는 정상 진행됩니다.")
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

    # ── bld 조회 ────────────────────────────────────────────────────────────────────────
    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회.

        ★ 익명 우선. 익명이 거부당하고 자격증명이 있으면 그때 로그인해서 한 번 더 시도한다.
          (예전 구현은 session_ok 가 아니면 시도조차 안 했다 — ID/PW 를 안 넣은 사용자에게
           KRX 경로가 통째로 없는 것과 같았다)
        """
        # ★ locale 을 빼면 MDC 가 빈 응답을 준다(가장 흔한 실패 원인). pykrx 도 항상 넣는다.
        body = {"bld": bld, "locale": "ko_KR", "share": "1", "money": "1",
                "csvxls_isNo": "false", **params}
        self.last_status = ""
        for attempt in (0, 1):
            txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is not None:
                self.last_status = str(txt)[:180].replace("\n", " ")
            if txt and str(txt).lstrip()[:1] in ("{", "["):
                try:
                    js = json.loads(txt)
                except Exception:
                    js = None
                if isinstance(js, dict):
                    if self.anon_ok is None and not self.session_ok:
                        self.anon_ok = True
                    return js
            # JSON 이 아니면 로그인 HTML 일 가능성이 크다 → 자격증명이 있으면 로그인 후 1회 재시도
            if attempt == 0 and self.user and self.pw and not self.session_ok:
                if self.anon_ok is None:
                    self.anon_ok = False
                    LOG.info("KRX 익명 bld 조회가 거부되었습니다 — 로그인 후 재시도합니다.")
                if not self.login():
                    return None
                continue
            return None
        return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY)


# ── MDC 벌크 스냅샷 ─────────────────────────────────────────────────────────────────────────
#   bld 후보. KRX 는 화면 개편 때 식별자를 바꾸므로 하나에 목숨을 걸지 않는다.
#   성공한 후보를 _KRX_BLD_OK 에 기억해 두 번째 호출부터는 곧장 그걸 쓴다.
KRX_BLD = {
    "allprice": ["dbms/MDC/STAT/standard/MDCSTAT01501",
                 "dbms/MDC/STAT/standard/MDCSTAT01502",
                 "dbms/MDC/STAT/standard/MDCSTAT00301"],
    "perpbr":   ["dbms/MDC/STAT/standard/MDCSTAT03501",
                 "dbms/MDC/STAT/standard/MDCSTAT03502"],
    "listed":   ["dbms/MDC/STAT/standard/MDCSTAT01901"],
}
# mktId 후보. 화면에 따라 ALL 을 안 받고 시장별만 받는 bld 가 있다.
KRX_MKT_CANDS = ["ALL", "STK", "KSQ"]
_KRX_BLD_OK: Dict[str, str] = {}
_KRX_BLD_DEAD: set = set()

#   응답 필드명 → 우리 스키마. KRX 는 영문 코드명을 쓰지만 화면/버전에 따라 한글이 오기도 한다.
_KRX_FIELD = {
    "code":     ("ISU_SRT_CD", "ISU_CD", "단축코드", "종목코드"),
    "name":     ("ISU_ABBRV", "ISU_NM", "종목명"),
    "market":   ("MKT_NM", "MKT_ID", "시장구분"),
    "close":    ("TDD_CLSPRC", "종가"),
    "open":     ("TDD_OPNPRC", "시가"),
    "high":     ("TDD_HGPRC", "고가"),
    "low":      ("TDD_LWPRC", "저가"),
    "volume":   ("ACC_TRDVOL", "거래량"),
    "amount":   ("ACC_TRDVAL", "거래대금"),
    "mktcap":   ("MKTCAP", "시가총액"),
    "shares":   ("LIST_SHRS", "상장주식수"),
    "eps":      ("EPS",), "per": ("PER",), "bps": ("BPS",), "pbr": ("PBR",),
    "dps":      ("DPS",), "div_yield": ("DVD_YLD", "배당수익률"),
}


def _krx_num(x: Any) -> float:
    """'1,234,567' / '-' / '' → float. KRX 는 숫자를 콤마 문자열로 준다."""
    s = str(x if x is not None else "").strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "N/A", "NaN"):
        return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _krx_rows(js: Optional[dict]) -> List[dict]:
    if not isinstance(js, dict):
        return []
    for k in ("OutBlock_1", "output", "block1", "OutBlock_2"):
        v = js.get(k)
        if isinstance(v, list) and v:
            return [r for r in v if isinstance(r, dict)]
    # 키 이름을 모르면 '리스트[dict] 중 가장 긴 것'을 택한다
    best: List[dict] = []
    for v in js.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) > len(best):
            best = v
    return best


def _krx_map_frame(rows: List[dict], want: Sequence[str]) -> pd.DataFrame:
    """응답 dict 리스트를 우리 스키마로 접는다. 없는 필드는 NaN 으로 남긴다."""
    if not rows:
        return pd.DataFrame(columns=list(want))
    # ★ 첫 행 하나로 키 집합을 정하면 요약행·부분행 하나에 매핑 전체가 무너진다.
    #   앞쪽 여러 행의 합집합을 쓴다.
    keys: set = set()
    for r in rows[:50]:
        keys |= set(r.keys())
    pick: Dict[str, str] = {}
    for tgt in want:
        for cand in _KRX_FIELD.get(tgt, ()):
            if cand in keys:
                pick[tgt] = cand
                break
    if "code" not in pick:
        return pd.DataFrame(columns=list(want))
    out: Dict[str, Any] = {}
    for tgt in want:
        src = pick.get(tgt)
        col = [r.get(src) for r in rows] if src else [None] * len(rows)
        if tgt in ("code", "name", "market"):
            out[tgt] = [str(v or "").strip() for v in col]
        else:
            out[tgt] = [_krx_num(v) for v in col]
    d = pd.DataFrame(out)
    d["code"] = d["code"].map(to_code6)
    return d.dropna(subset=["code"])


def _krx_bld_call(kind: str, **params) -> List[dict]:
    """bld 후보를 순서대로 두드려 첫 성공을 쓴다. 성공한 후보는 기억한다."""
    if kind in _KRX_BLD_DEAD:
        return []
    cands = ([_KRX_BLD_OK[kind]] if kind in _KRX_BLD_OK else list(KRX_BLD.get(kind, [])))
    for bld in cands:
        rows = _krx_rows(KRX.json_data(bld, **params))
        if rows:
            _KRX_BLD_OK[kind] = bld
            return rows
    return []


def _prev_bizday(ts: Any, back: int = 0) -> _dt.date:
    try:
        base = as_ts(ts).date()
    except Exception:
        base = _dt.date.today()          # 파싱 불가한 값 하나로 스테이지를 죽이지 않는다
    d = base - _dt.timedelta(days=int(back))
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d


def krx_all_price(day: Any, market: str = "", walk_back: int = 7) -> Optional[pd.DataFrame]:
    """전종목 시세 스냅샷 — 날짜 1개 = 1호출. 종가·시가·고저·거래량·거래대금·시총·상장주식수.

    휴장일이면 빈 응답이 오므로 직전 영업일로 최대 walk_back 일 당겨본다.
    (이 한 함수가 pykrx 의 get_market_ohlcv_by_ticker + get_market_cap_by_ticker 를 대체한다)
    """
    want = ["code", "name", "market", "close", "open", "high", "low",
            "volume", "amount", "mktcap", "shares"]
    market = market or globals().get("_KRX_MKT_OK") or "ALL"
    seen_days: set = set()
    for back in range(walk_back + 1):
        d = _prev_bizday(day, back)
        if d in seen_days:          # 주말이면 back=0,1,2 가 같은 금요일을 가리킨다
            continue
        seen_days.add(d)
        rows = _krx_bld_call("allprice", mktId=market, trdDd=d.strftime("%Y%m%d"))
        if not rows:
            continue
        f = _krx_map_frame(rows, want)
        if len(f):
            # ★ 단위 검증. KRX 가 시총 단위를 원→백만원으로 바꾸면 값이 1e-6 이 되고,
            #   §5 하한(500억)이 매달 유니버스를 통째로 비운다. 값이 '있으므로'
            #   결측 가드도 안 걸린다. 같은 응답 안의 상장주식수×종가로 교차검증한다.
            try:
                chk = (pd.to_numeric(f["mktcap"], errors="coerce") /
                       (pd.to_numeric(f["shares"], errors="coerce") *
                        pd.to_numeric(f["close"], errors="coerce")))
                med = float(np.nanmedian(chk.replace([np.inf, -np.inf], np.nan)))
                if np.isfinite(med) and not (0.5 <= med <= 2.0):
                    LOG.error(f"KRX 시총 단위 이상 — 시총/(주식수×종가) 중앙값 {med:.3g} "
                              f"(정상 1.0). 단위가 바뀐 것으로 보고 이 스냅샷을 버립니다.")
                    return None
            except Exception:
                pass
            f["date"] = pd.Timestamp(d)
            return f
    return None


def krx_all_perpbr(day: Any, market: str = "", walk_back: int = 7) -> Optional[pd.DataFrame]:
    """전종목 PER/PBR/BPS/배당 스냅샷 — 날짜 1개 = 1호출. §6.3 직교화의 BM 원천."""
    want = ["code", "name", "close", "eps", "per", "bps", "pbr", "dps", "div_yield"]
    market = market or globals().get("_KRX_MKT_OK") or "ALL"
    seen_days: set = set()
    for back in range(walk_back + 1):
        d = _prev_bizday(day, back)
        if d in seen_days:
            continue
        seen_days.add(d)
        rows = _krx_bld_call("perpbr", mktId=market, trdDd=d.strftime("%Y%m%d"), searchType="1")
        if not rows:
            continue
        f = _krx_map_frame(rows, want)
        if len(f):
            f["date"] = pd.Timestamp(d)
            return f
    return None


def krx_bulk_available() -> bool:
    """MDC 벌크 경로가 이 실행에서 실제로 동작하는지 1회 확인하고 기억한다."""
    # 리허설·스모크는 네트워크를 쓰지 않는다. 여기서 실제 프로브를 날리면 오프라인
    # 환경에서 검증 단계가 타임아웃으로 늘어지고, 최악의 경우 리허설이 실측 응답을
    # 캐시처럼 취급하게 된다. 검증 단계는 반드시 네트워크 없이 끝나야 한다.
    if globals().get("_REHEARSAL") or RUN_MODE == "SMOKE":
        return False
    cur = globals().get("_KRX_BULK_OK")
    if cur is not None:
        return bool(cur)
    probe = None
    for mkt in KRX_MKT_CANDS:
        probe = krx_all_price(_dt.date.today() - _dt.timedelta(days=3), market=mkt, walk_back=9)
        if probe is not None and len(probe) > 100:
            globals()["_KRX_MKT_OK"] = mkt
            break
        probe = None
    ok = probe is not None
    globals()["_KRX_BULK_OK"] = ok
    if ok:
        LOG.ok(f"KRX MDC 벌크 스냅샷 사용 가능 — 전종목 {len(probe):,}건/1호출 "
               f"(bld={_KRX_BLD_OK.get('allprice', '?')}, mktId={globals().get('_KRX_MKT_OK')}). "
               f"pykrx 없이도 시총·PBR 을 받습니다.")
    else:
        _KRX_BLD_DEAD.add("allprice")
        # ★ '응답 없음' 한 줄로 끝내면 아무도 고칠 수 없다. 무엇을 보냈고 무엇이 왔는지 남긴다.
        LOG.table([["시도한 bld", " / ".join(KRX_BLD["allprice"])],
                   ["시도한 mktId", " / ".join(KRX_MKT_CANDS)],
                   ["로그인 상태", KRX.status],
                   ["세션 확보", "예" if KRX.session_ok else "아니오"],
                   ["익명 조회 가능", {True: "예", False: "아니오"}.get(KRX.anon_ok, "미확인")],
                   ["마지막 응답 앞부분", (KRX.last_status or "(응답 없음/네트워크 실패)")[:110]]],
                  ["KRX 벌크 진단", "값"], ["l", "l"],
                  title="KRX MDC 벌크 실패 진단 (시총·PBR 의 1순위 경로)")
        LOG.warn("KRX MDC 벌크 스냅샷을 쓸 수 없습니다 — 시총/BM 은 파생계산(상장주식수×종가)과 "
                 "DART 폴백으로 대체합니다. 유니버스 시총하한이 그만큼 근사가 되고, "
                 "시총하위1000 아암은 '근사 순위' 기준이 됩니다. "
                 "위 표의 '마지막 응답 앞부분'이 로그인 HTML 이면 ID/PW 를, "
                 "빈 JSON 이면 bld/mktId 가 개편된 것입니다.")
    return ok


def krx_listing_snapshots(months: pd.DatetimeIndex, freq_q: bool = True) -> pd.DataFrame:
    """분기말 '그 날 상장돼 있던 종목' 스냅샷 — pykrx 없이 PIT 검증 입력을 복원한다.

    ★ 왜 필요한가: 이 스냅샷은 생존자편향 제거의 '검증' 입력이다(§C2). pykrx 가 없으면
      기존 경로는 통째로 건너뛰고 유니버스가 상장일·폐지일만으로 구성된다. 그 자체는
      설계상 정상 경로지만, 폐지목록이 놓친 종목을 잡아낼 교차검증 수단이 사라진다.
      전종목 시세 스냅샷은 정의상 '그 날 거래된 종목 전체'이므로 같은 역할을 한다.
      분기말 40개 시점 × 1호출 = 40호출로 10년치가 끝난다.

    ★ 저장 테이블 이름을 기존 경로와 똑같이 쓴다(krx_listing_snapshots). 그래야 다른 전략과
      다음 세션이 출처를 신경 쓰지 않고 그대로 재사용한다(공용 인덱스 호환).
    """
    cols = ["snap_date", "code", "market"]
    if not krx_bulk_available():
        return pd.DataFrame(columns=cols)
    cached = cache_recall("krx_listing_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        have = set(as_ts_series(cached["snap_date"]).dt.strftime("%Y-%m-%d").dropna())
    grid = [as_ts(m) for m in months if (not freq_q) or as_ts(m).month in (3, 6, 9, 12)]
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if not todo or RUN_MODE == "CACHED":
        return cached if cached is not None else pd.DataFrame(columns=cols)

    LOG.info(f"KRX 벌크로 상장 스냅샷 {len(todo)}개 시점 복원 (1시점 = 1호출)")
    rows, miss = [], 0
    for d in tqdm(todo, desc="상장 스냅샷", disable=not VERBOSE, mininterval=TQDM_MININTERVAL):
        f = krx_all_price(d)
        if f is None or not len(f):
            miss += 1
            if miss >= CIRCUIT_BREAKER_FAILS:
                LOG.warn("연속 실패 — 상장 스냅샷 복원을 중단합니다.")
                break
            continue
        miss = 0
        mk = f["market"].astype(str).str.upper() if "market" in f.columns else ""
        rows.append(pd.DataFrame({"snap_date": d.strftime("%Y-%m-%d"), "code": f["code"],
                                  "market": np.where(pd.Series(mk).str.contains("KOSDAQ|KSQ"),
                                                     "KOSDAQ", "KOSPI")}))
    if not rows:
        return cached if cached is not None else pd.DataFrame(columns=cols)
    out = pd.concat(rows, ignore_index=True)
    n_new = len(out)
    if cached is not None and len(cached):
        out = pd.concat([cached.reindex(columns=cols), out], ignore_index=True)
    out = out.drop_duplicates(["snap_date", "code"], keep="last").reset_index(drop=True)
    note_new_data("krx_listing_snapshots", n_new, "shared", "universe", "krx_bulk")
    persist("krx_listing_snapshots", out, scope="shared", domain="universe",
            source="krx MDC all-price snapshot")
    LOG.ok(f"상장 스냅샷 {out['snap_date'].nunique()}개 시점 × "
           f"{out['code'].nunique():,}종목 = {len(out):,}행 (생존자편향 교차검증 입력)")
    return out


# ── 증권유형 분류 (가격수집 대상 축소 + §5 제외규칙의 공통 기반) ─────────────────────────────
#   ★ 왜 여기 있나: 가격을 '전 종목'에 받으면 안 된다. 우선주·ETF·ETN·ELW·스팩은 §5 에서
#     어차피 전부 제외된다. 실측 5,398종목 중 이런 것들이 1,000종목 넘게 섞여 있었고,
#     그 대부분이 '전 소스 실패 1,901종목'의 정체다. 받지 않아도 되는 것을 받으려다
#     실패하고, 실패했으니 4개 소스를 다 돌린 것이다.
# 우선주 말자리는 KRX 규약상 5(1우) · 7(2우) · 9(3우) · K/L/M(신형우선주) 뿐이다.
# ★ 구버전은 여기에 '6' 이 섞여 있었다. 6 은 우선주 말자리가 아니며, 6 으로 끝나는 보통주
#   (선박투자회사·일부 코스닥 종목 등)를 통째로 유니버스에서 지워 버린다. 조용히 표본이
#   줄고 그만큼 결과가 바뀌는데 아무 로그도 남지 않는다 — 계약검정 K16 이 이걸 잡았다.
_PREF_TAIL = set("579KLMklm")
_SPAC_PAT = re.compile(r"스팩|기업인수목적")
_REIT_PAT = re.compile(r"리츠|위탁관리부동산|기업구조조정부동산")
# ★ ETP 판정은 '앞머리 브랜드'로만 한다. 부분일치로 두면 보통주를 삼킨다:
#   구버전의 '파워' 는 파워로직스(047310)·파워넷·한국파워트레인 같은 멀쩡한 코스닥
#   보통주를 ETF 로 분류해 가격 수집에서 빼고 §5 로 제외했다. 시가총액 수천억 종목이
#   10년 내내 유니버스에서 사라지는데, 감사표에는 'ETF/ETN 제외' 한 줄로만 남는다.
#   '레버리지·인버스'도 상품명 어디에나 붙을 수 있어 앞머리에서만 인정한다.
_ETF_BRANDS = (r"KODEX|TIGER|KBSTAR|ARIRANG|HANARO|KOSEF|TIMEFOLIO|SOL|ACE|PLUS|RISE|"
               r"KINDEX|KTOP|FOCUS|마이다스|네비게이터")
_ETF_PAT = re.compile(rf"^\s*(?:{_ETF_BRANDS})\b|(?:^|\s)(?:ETN|ETF)(?:\s|$)|"
                      rf"^\s*(?:레버리지|인버스)\b", re.I)
_ELW_PAT = re.compile(r"콜\d|풋\d|ELW|워런트|신주인수권", re.I)


def is_preferred(code: str, name: str = "") -> bool:
    """우선주 판정. 코드 말자리(구형 5/7/9, 신형 K/L/M)와 종목명 '우/우B/2우B' 를 함께 본다."""
    c = str(code or "")
    if len(c) == 6 and c[-1] in _PREF_TAIL:      # '0' 은 _PREF_TAIL 에 없다 (가드 불필요)
        return True
    n = str(name or "").strip()
    return bool(re.search(r"(\d?우[BC]?)$|우선주$", n))


def classify_security(code: str, name: str = "", market: str = "") -> str:
    """'common' | 'preferred' | 'etp' | 'spac' | 'reit' | 'elw' | 'konex'.

    보통주(common)만 백테스트 유니버스의 후보다. 나머지는 가격조차 받지 않는다.
    ★ 리츠는 여기서 'reit' 로 라벨만 붙이고 가격은 받는다. 실제 제외는 §5 의
      build_exclusion_flags 가 담당한다(is_reit → excluded). 즉 리츠는 가격을 받고
      유니버스에서 빠진다 — 소량이라 그대로 두지만, 두 곳의 정책이 다르다는 사실을
      여기 적어 둔다(주석과 코드가 어긋나 있던 부분).
    """
    c, n = str(code or ""), str(name or "")
    mk = str(market or "").upper()
    if "KONEX" in mk or "KNX" in mk:
        return "konex"
    if _ELW_PAT.search(n):
        return "elw"
    if _ETF_PAT.search(n):
        return "etp"
    if _SPAC_PAT.search(n):
        return "spac"
    if is_preferred(c, n):
        return "preferred"
    if _REIT_PAT.search(n):
        return "reit"
    return "common"


def price_target_codes(sec: pd.DataFrame) -> Tuple[List[str], pd.DataFrame]:
    """가격을 실제로 받아야 하는 종목만 추린다. (코드목록, 축소감사표) 를 돌려준다.

    ★ 이것이 '쓸데없는 가격조회'를 없애는 가장 큰 한 방이다. 요청 수 자체를 줄인다.
      제외 근거는 전부 §5 이거나(우선주·ETP·스팩·ELW·KONEX) 백테스트 구간 밖이다(상폐/상장일).
      근거 없는 축소는 하지 않는다 — 상장폐지 종목은 반드시 남긴다(생존자편향).
    """
    if sec is None or not len(sec):
        return [], pd.DataFrame(columns=["사유", "종목수"])
    s = sec.copy()
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    nm = s["name"].astype(str) if "name" in s.columns else pd.Series("", index=s.index)
    mk = s["market"].astype(str) if "market" in s.columns else pd.Series("", index=s.index)
    s["_kind"] = [classify_security(c, n, m) for c, n, m in zip(s["code"], nm, mk)]

    reasons: List[List[str]] = []
    keep = pd.Series(True, index=s.index)
    for kind, label in (("preferred", "우선주 (§5 제외)"), ("etp", "ETF/ETN (§5 제외)"),
                        ("spac", "스팩 (§5 제외)"), ("elw", "ELW/신주인수권 (§5 제외)"),
                        ("konex", "KONEX (UNI_MARKETS 밖)")):
        m = (s["_kind"] == kind) & keep
        if int(m.sum()):
            reasons.append([label, f"{int(m.sum()):,}"])
        keep &= ~m

    # 백테스트 구간과 겹치지 않는 종목 (상장 전 폐지 / 구간 시작 전 폐지)
    win_lo = as_ts(BACKTEST_START) - pd.DateOffset(months=LINK_LOOKBACK_M + 3)
    win_hi = as_ts(BACKTEST_END)
    if "delisting_date" in s.columns:
        dl = as_ts_series(s["delisting_date"])
        m = dl.notna() & (dl < win_lo) & keep
        if int(m.sum()):
            reasons.append(["백테스트 구간 시작 전 상장폐지", f"{int(m.sum()):,}"])
        keep &= ~m
    if "listing_date" in s.columns:
        li = as_ts_series(s["listing_date"])
        m = li.notna() & (li > win_hi) & keep
        if int(m.sum()):
            reasons.append(["백테스트 구간 종료 후 상장", f"{int(m.sum()):,}"])
        keep &= ~m

    codes = sorted(s.loc[keep, "code"].tolist())
    reasons.append(["── 가격 수집 대상", f"{len(codes):,}"])
    audit = pd.DataFrame(reasons, columns=["사유", "종목수"])
    return codes, audit
