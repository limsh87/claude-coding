
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B2  공공데이터포털 금융위원회_주식시세정보 — ★ KRX 없이 PIT 를 완성하는 축 ★          ║
# ║                                                                                          ║
# ║  엔드포인트: /1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo             ║
# ║  basDt(기준일자) 하나로 그날 '전 종목' 을 한 번에 준다. 이 성질이 결정적이다:              ║
# ║    · 10년 = 약 2,450 요청  (종목별로 긁으면 2,700종목 × 250페이지 = 67만 요청)             ║
# ║    · mrktTotAmt(시가총액) · lstgStCnt(상장주식수) 가 '그 시점 값' 으로 온다                ║
# ║      → PIT 시가총액이 근사가 아니라 정품이 된다. KRX 대체의 핵심.                          ║
# ║    · 그날 시세가 존재한 종목 목록 = 진짜 일별 상장 스냅샷                                  ║
# ║      → 생존편향 제거가 '상장/폐지일 추정' 이 아니라 '관측' 으로 확정된다.                  ║
# ║                                                                                          ║
# ║  함정 (전부 방어함):                                                                      ║
# ║   ① Encoding 키를 넣으면 이중 인코딩 → SERVICE_KEY_IS_NOT_REGISTERED. 자동 감지·교정.      ║
# ║   ② 오류 응답이 HTTP 200 + XML 로 온다. resultCode 를 반드시 본다.                         ║
# ║   ③ 휴장일은 정상적으로 0건이다. '수집 실패' 와 구분해서 기록해야 패널의 구멍을 나중에      ║
# ║      해석할 수 있다.                                                                       ║
# ║   ④ srtnCd 는 앞자리 0 이 날아간 정수로 오는 경우가 있다 → to_code6 로 복구.                ║
# ║   ⑤ 우선주·ETF·리츠가 섞여 온다. mrktCtg 와 종목코드 규칙으로 걸러야 유니버스가 오염되지 않는다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DGK_BASE = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
DGK_COLS = ["date", "code", "name", "market", "open", "high", "low", "close",
            "volume", "amount", "shares", "marcap"]


def _dgk_key() -> str:
    """Decoding 키를 돌려준다. 사용자가 Encoding 키를 붙여넣은 경우를 감지해 교정한다."""
    k = (DATA_GO_KR_KEY or "").strip()
    if not k:
        return ""
    if "%" in k and re.search(r"%[0-9A-Fa-f]{2}", k):
        from urllib.parse import unquote
        dec = unquote(k)
        if dec != k:
            LOG.warn("DATA_GO_KR_KEY 가 Encoding 키로 보입니다(%2B/%3D 포함). "
                     "Decoding 키로 자동 변환했습니다. 계속 401 이 나면 포털에서 "
                     "'일반 인증키(Decoding)' 값을 다시 복사해 넣으세요.")
            return dec
    return k


DGK_STATE_V = 3
_DGK_RC: Counter = Counter()          # resultCode 분포 — 실패 원인을 '추측' 하지 않기 위해 집계한다
_DGK_RC_LK = threading.Lock()

# ── 하루당 요청 수 — 여기가 전체 호출량을 결정한다 ────────────────────────────────────────────
#  ★ 2,700종목/일 을 numOfRows=1000 으로 받으면 하루 3요청 → 10년이면 약 7,400요청이다.
#    한 번에 다 받으면 하루 1요청 → 약 2,450요청. 같은 데이터를 3분의 1로 받는다.
#    이 API 는 numOfRows 상한이 넉넉하므로 굳이 쪼갤 이유가 없다.
DGK_ROWS_PER_REQ = 6000
DGK_MAX_PAGES = 3                     # 상한 초과 시의 안전장치일 뿐, 평시엔 1페이지로 끝난다


class DgkQuota:
    """일일 호출 한도를 '미리 정해두지 않고' 실시간으로 관측한다.

    ★ 상한값을 코드에 박아 넣는 것은 두 방향 모두로 틀린다 —
      낮게 잡으면 남은 할당량을 놔두고 멈추고, 높게 잡으면 한도 초과 응답을 수백 번 받는다.
      포털은 잔여량을 응답 헤더로 주지 않으므로, 유일하게 정확한 신호는
      'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR(22)' 응답 그 자체다.
      그래서 ① 오늘 몇 번 썼는지 세고 ② 한도 응답이 오는 순간의 카운트를 '관측된 실제 한도'로
      기록해 상태 파일에 남긴다. 다음 실행은 그 관측값을 알고 시작한다(추측이 아니라 실측)."""

    def __init__(self, state: dict):
        self._lk = threading.Lock()
        self.day = as_ts(now_kst()).normalize().strftime("%Y%m%d")
        q = state.get("quota") or {}
        self.used = int(q.get("used", 0)) if q.get("day") == self.day else 0
        self.observed = int(q.get("observed_limit", 0) or 0)   # 0 = 아직 한도를 본 적 없음
        self.exhausted = bool(q.get("day") == self.day and q.get("exhausted"))

    def note(self, n: int = 1) -> None:
        with self._lk:
            self.used += int(n)

    def hit_limit(self) -> None:
        with self._lk:
            self.exhausted = True
            self.observed = max(self.observed, self.used)

    def dump(self) -> dict:
        return {"day": self.day, "used": int(self.used),
                "observed_limit": int(self.observed), "exhausted": bool(self.exhausted)}

    def remaining_hint(self) -> str:
        if self.exhausted:
            return f"오늘 한도 소진(관측된 실제 한도 {self.observed:,}회)"
        if self.observed:
            return f"오늘 {self.used:,}회 사용 · 관측된 한도 {self.observed:,}회 → 잔여 약 {max(0, self.observed - self.used):,}회"
        return f"오늘 {self.used:,}회 사용 · 한도는 아직 관측되지 않음(한도 응답이 올 때까지 계속 씁니다)"


DGK_QUOTA: Optional["DgkQuota"] = None


def _dgk_day(day: pd.Timestamp, tries: int = 3) -> Tuple[Optional[pd.DataFrame], str]:
    """하루치 전 종목.

    반환은 (데이터, 사유) 다. 사유를 같이 돌려주는 것이 이 함수의 요점이다 —
    이전 판은 실패를 전부 None 으로 뭉개서, 2,895일 중 15일이 실패했을 때 그것이
    '인증키 오류' 인지 '일시적 네트워크' 인지 알 수 없었고, 결국 서킷 브레이커가
    잘못 발동해 수집량이 0 이 되었다.
      · (DataFrame, "ok")       정상
      · (빈 DataFrame, "holiday") 휴장 — 정상적인 0건
      · (None, "key:...")       인증키 문제 → 즉시 전체 중단이 옳다
      · (None, "quota")         일일 트래픽 초과 → 즉시 전체 중단이 옳다
      · (None, "net")           일시적 실패 → 재시도 큐로. 절대 전체를 멈추지 않는다
    """
    key = _dgk_key()
    if not key:
        return None, "nokey"
    bas = day.strftime("%Y%m%d")
    rows: List[dict] = []
    for page in range(1, DGK_MAX_PAGES + 1):
        if DGK_QUOTA is not None:
            if DGK_QUOTA.exhausted:
                return None, "quota"
            DGK_QUOTA.note(1)
        js = http_json(DGK_BASE, source="datagokr",
                       params={"serviceKey": key, "numOfRows": DGK_ROWS_PER_REQ, "pageNo": page,
                               "resultType": "json", "basDt": bas}, tries=tries, timeout=45)
        if not isinstance(js, dict):
            with _DGK_RC_LK:
                _DGK_RC["응답없음/XML오류"] += 1
            return None, "net"
        hdr = (js.get("response") or {}).get("header") or {}
        body = (js.get("response") or {}).get("body") or {}
        rc = str(hdr.get("resultCode", "")).strip()
        msg = str(hdr.get("resultMsg", "")).strip()
        if rc and rc not in ("00", "0", ""):
            with _DGK_RC_LK:
                _DGK_RC[f"{rc} {msg}"[:60]] += 1
            up = (rc + " " + msg).upper()
            if any(t in up for t in ("SERVICE_KEY", "SERVICEKEY", "NOT_REGISTERED",
                                     "UNREGISTERED", "APPLICATION_ERROR", "30", "31")):
                return None, f"key:{rc} {msg}"[:80]
            if "LIMITED_NUMBER" in up or "TRAFFIC" in up or rc == "22":
                if DGK_QUOTA is not None:
                    DGK_QUOTA.hit_limit()
                return None, "quota"
            return None, "net"
        items = (body.get("items") or {})
        it = items.get("item") if isinstance(items, dict) else items
        if it is None:
            break
        if isinstance(it, dict):
            it = [it]
        rows.extend(it)
        tot = int(body.get("totalCount") or 0)
        if len(rows) >= tot or len(it) == 0:
            break
    with _DGK_RC_LK:
        _DGK_RC["00 정상"] += 1
    if not rows:
        return pd.DataFrame(columns=DGK_COLS), "holiday"    # 휴장(정상 0건)

    d = pd.DataFrame(rows)
    g = lambda c: pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    out = pd.DataFrame({
        "date": pd.to_datetime(d.get("basDt"), format="%Y%m%d", errors="coerce"),
        "code": d.get("srtnCd", pd.Series(dtype=object)).map(to_code6),
        "name": d.get("itmsNm", "").astype(str).str.strip(),
        "market": d.get("mrktCtg", "").astype(str).str.strip(),
        "open": g("mkp"), "high": g("hipr"), "low": g("lopr"), "close": g("clpr"),
        "volume": g("trqu"), "amount": g("trPrc"),
        "shares": g("lstgStCnt"), "marcap": g("mrktTotAmt"),
    })
    return out.dropna(subset=["code", "date", "close"]), "ok"


def dgk_preflight() -> Tuple[bool, str]:
    """수집을 시작하기 전에 최근 영업일 한 건으로 키를 검증한다.

    ★ 이것이 없어서 이전 판은 잘못된 키로 2,895일을 요청했다. 한 번의 요청으로 알 수 있는 것을
      2,895번 확인하지 않는다(사용자 요구: 쓸데없는 반복 수집 금지)."""
    if not _dgk_key():
        return False, "nokey"
    probe = as_ts(now_kst()).normalize() - pd.Timedelta(days=1)
    for _ in range(8):                       # 최근 영업일을 찾을 때까지 최대 8일 거슬러 올라감
        while probe.weekday() >= 5:
            probe -= pd.Timedelta(days=1)
        d, why = _dgk_day(probe, tries=2)
        if why == "ok":
            return True, f"정상 — {probe:%Y-%m-%d} {len(d):,}종목 응답"
        if why.startswith("key:"):
            return False, why
        if why == "quota":
            return False, "일일 트래픽 한도 초과"
        probe -= pd.Timedelta(days=1)
    return False, "net"


def fetch_datagokr_panel(cal_start: str, cal_end: str) -> pd.DataFrame:
    """일별 전 종목 패널. 캐시 우선 → 부족한 날짜만 → 드라이브 공용 인덱스에 재적재.

    ★ 수집 순서는 최근 → 과거 다. 차단당하거나 중단되어도 '최신 구간' 이 먼저 확보되어
      부분 결과로도 최근 몇 년 백테스트가 가능하다 (SPEC §2.3).
    ★ 휴장일은 'holiday' 로, 실패일은 'fail' 로 각각 기록한다. 이 둘을 섞으면 몇 달 뒤에
      패널의 구멍이 무엇이었는지 영영 알 수 없게 된다.
    ★ 서킷 브레이커는 '치명적 사유'(키·한도) 에만 즉시 반응한다. 일시적 네트워크 실패는
      재시도 큐로 보내고 계속 간다 — 2,895일 중 15일 실패로 전체를 죽이지 않는다."""
    key = _dgk_key()
    s, e = as_ts(cal_start), as_ts(cal_end)
    if s is None or e is None:
        return pd.DataFrame(columns=DGK_COLS)

    cached = VAULT.get_table("dgk_stock_price_daily", scope="shared")
    have_days: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["date", "code"])
        if len(c):
            frames.append(c.reindex(columns=DGK_COLS))
            have_days = set(c["date"].dt.strftime("%Y%m%d"))
            LOG.info(f"공용 캐시에서 공공데이터 시세 {len(c):,}행 / {len(have_days):,}일 재사용")

    # 중단·재개 스테이징: 이번 실행에서 받은 날들을 즉시 로컬에 떨궈 둔다
    stage_p = state_path("_dgk_stage.parquet")
    stg = read_parquet_safe(stage_p) if os.path.exists(stage_p) else None
    if stg is not None and len(stg):
        stg = stg.copy()
        stg["date"] = as_ts_series(stg["date"])
        stg["code"] = stg["code"].map(to_code6)
        stg = stg.dropna(subset=["date", "code"])
        if len(stg):
            frames.append(stg.reindex(columns=DGK_COLS))
            have_days |= set(stg["date"].dt.strftime("%Y%m%d"))
            LOG.ok(f"직전 중단 지점의 공공데이터 스테이징 {stg['date'].nunique():,}일을 이어받았습니다.")

    # 상태 저장(중단·재개): 이미 '휴장 확인' 된 날은 다시 때리지 않는다
    state_p = state_path("_dgk_state.json")
    state = {"_v": DGK_STATE_V, "holiday": [], "fail": {}}
    _prev = read_json(state_p, default=None)
    if isinstance(_prev, dict) and int(_prev.get("_v", 0)) == DGK_STATE_V:
        state.update(_prev)
        if not isinstance(state.get("fail"), dict):
            state["fail"] = {}
    known_holiday = set(state.get("holiday", []))
    global DGK_QUOTA
    DGK_QUOTA = DgkQuota(state)
    # 3회 이상 실패한 날은 '그 날짜에 데이터가 없는 것' 으로 보고 더 시도하지 않는다.
    # (공공데이터는 아주 오래된 구간에서 간헐적으로 비어 있다 — 매 실행 재시도는 낭비다)
    give_up = {k for k, v in state.get("fail", {}).items() if int(v or 0) >= 3}

    if not key:
        if frames:
            LOG.info("DATA_GO_KR_KEY 가 없어 신규 수집은 건너뛰고 캐시만 사용합니다.")
        else:
            LOG.warn("DATA_GO_KR_KEY 가 비어 있습니다 → PIT 시가총액/일별 상장 스냅샷을 "
                     "정품 경로로 만들 수 없습니다. 시총은 근사(T2~T4)로 강등되고, "
                     "유니버스는 상장일·폐지일 기반으로만 구성됩니다(그래도 동작합니다). "
                     "정확도를 크게 올리려면 상단 ②-b 안내대로 키를 발급받아 넣으세요.")
        return _dgk_finalize(frames, wrote=False)

    days = pd.bdate_range(s, e)                       # 주말 제외 (공휴일은 응답 0건으로 판별)
    todo = [d for d in days
            if d.strftime("%Y%m%d") not in have_days
            and d.strftime("%Y%m%d") not in known_holiday
            and d.strftime("%Y%m%d") not in give_up]
    todo = sorted(todo, reverse=True)                 # ★ 최근 → 과거 (SPEC §2.3)

    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 공공데이터 {len(todo):,}일 신규 수집을 건너뜁니다.")
        todo = []

    if todo:
        ok, why = dgk_preflight()
        if not ok:
            _dgk_key_help(why)
            return _dgk_finalize(frames, wrote=False)
        LOG.ok(f"공공데이터 인증키 사전점검 통과 — {why}")

    if todo:
        LOG.info(f"공공데이터 일별 전종목 수집 {len(todo):,}일 — "
                 f"하루 1요청(numOfRows={DGK_ROWS_PER_REQ:,}) 설계이므로 예상 호출량은 "
                 f"약 {len(todo):,}회입니다. {DGK_QUOTA.remaining_hint()}. "
                 f"호출 한도는 미리 정하지 않고, 포털이 한도 초과를 응답하는 순간에만 멈춥니다.")
        if DGK_QUOTA.exhausted:
            LOG.warn("오늘 이미 한도를 소진한 기록이 있습니다 — 신규 수집을 건너뛰고 캐시만 씁니다. "
                     "내일 다시 실행하면 남은 구간을 이어받습니다(최근→과거라 최신 구간부터 완성).")
            todo = []
        got: List[pd.DataFrame] = []
        n_holiday = 0
        fatal = {"why": ""}
        lk = threading.Lock()

        def _one(day: pd.Timestamp):
            if fatal["why"]:
                return None
            polite_sleep(0.05, 0.25)
            d, why = _dgk_day(day)
            ds = day.strftime("%Y%m%d")
            with lk:
                if why in ("holiday",):
                    state["holiday"].append(ds)
                    return "holiday"
                if why == "ok":
                    state["fail"].pop(ds, None)
                    return d
                # 실패 — 치명적 사유만 전체를 멈춘다
                state["fail"][ds] = int(state["fail"].get(ds, 0)) + 1
                if (why.startswith("key:") or why == "quota") and not fatal["why"]:
                    fatal["why"] = why
                return None

        def _on_result(i, day, r):
            nonlocal n_holiday
            with lk:
                if r is None or isinstance(r, str):
                    if r == "holiday":
                        n_holiday += 1
                    return
                got.append(r)
                n = len(got)
            if n and n % DGK_FLUSH_EVERY == 0:
                _dgk_flush(frames, got, stage_p, state, state_p)

        pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="공공데이터 시세",
                budget_s=DGK_BUDGET_MIN * 60.0, on_result=_on_result,
                should_stop=lambda: bool(fatal["why"]))
        _dgk_flush(frames, got, stage_p, state, state_p)
        frames += got

        n_fail = sum(1 for d in todo
                     if d.strftime("%Y%m%d") in state["fail"]
                     and d.strftime("%Y%m%d") not in {x for x in state["holiday"]})
        LOG.ok(f"공공데이터 수집 완료 — 신규 {len(got):,}일 · 휴장 {n_holiday:,}일 · 실패 {n_fail:,}일")
        LOG.info(f"공공데이터 호출량 — {DGK_QUOTA.remaining_hint()} "
                 f"(수집일수 {len(got)+n_holiday:,}일당 요청 "
                 f"{DGK_QUOTA.used / max(len(got)+n_holiday+n_fail, 1):.2f}회)")
        if _DGK_RC:
            LOG.table([[k, f"{v:,}"] for k, v in _DGK_RC.most_common(8)],
                      ["resultCode / 사유", "건수"], ["l", "r"],
                      title="공공데이터 응답 코드 분포")
        if fatal["why"]:
            _dgk_key_help(fatal["why"])
        elif n_fail > max(20, len(todo) * 0.3):
            LOG.warn(f"실패율이 {100 * n_fail / max(len(todo), 1):.0f}% 로 높습니다. "
                     f"실패한 날짜는 결측으로 남기고 0으로 채우지 않습니다. "
                     f"다음 실행에서 자동으로 재시도합니다(3회 실패 시 영구 제외).")

    return _dgk_finalize(frames, wrote=True)


def _dgk_key_help(why: str) -> None:
    """키 문제는 조용히 넘기면 안 된다 — 사용자가 5초 만에 고칠 수 있는 문제이기 때문이다."""
    if why == "quota":
        obs = DGK_QUOTA.observed if DGK_QUOTA is not None else 0
        LOG.error(f"공공데이터포털 일일 호출 한도에 도달했습니다"
                  f"{f' — 관측된 실제 한도 {obs:,}회' if obs else ''}. "
                  f"미리 정한 상한이 아니라 포털이 직접 알려준 시점에 멈춘 것입니다. "
                  f"여기까지 받은 분량은 캐시에 저장되어 다음 실행이 이어받습니다"
                  f"(최근→과거 순이므로 최신 구간부터 완성됩니다). "
                  f"더 필요하면 포털 마이페이지 → 활용신청 상세 → '트래픽 증가 신청' 을 하세요.")
        return
    if why == "nokey":
        return
    LOG.error(f"공공데이터포털 인증키가 거부되었습니다 ({why}). 수집을 시작하지 않고 중단합니다 "
              f"— 잘못된 키로 수천 건을 요청하는 낭비를 막기 위함입니다.\n"
              f"   확인 순서: ① data.go.kr → 마이페이지 → 활용신청 현황에서 "
              f"'금융위원회_주식시세정보' 가 '승인' 인지\n"
              f"             ② 승인 직후라면 반영에 최대 1시간이 걸립니다\n"
              f"             ③ 상단 DATA_GO_KR_KEY 에 'Encoding' 이 아니라 "
              f"'Decoding' 일반 인증키를 넣었는지")


def _dgk_flush(frames, got, stage_p, state, state_p) -> None:
    """증분 저장. 중간에 끊겨도 여기까지는 다음 실행이 이어받는다."""
    try:
        if got:
            atomic_write_parquet(pd.concat(got, ignore_index=True), stage_p)
    except Exception as ex:                                     # noqa
        LOG.debug(f"공공데이터 스테이징 저장 실패({type(ex).__name__})")
    try:
        state["holiday"] = sorted(set(state.get("holiday", [])))
        if DGK_QUOTA is not None:
            state["quota"] = DGK_QUOTA.dump()
        write_json(state_p, state)
    except Exception:
        pass


def _dgk_finalize(frames: List[pd.DataFrame], wrote: bool) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=DGK_COLS)
    P = pd.concat(frames, ignore_index=True)
    P["date"] = as_ts_series(P["date"])
    P["code"] = P["code"].map(to_code6)
    P = (P.dropna(subset=["date", "code", "close"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))
    if wrote and len(P):
        VAULT.put_table("dgk_stock_price_daily", P, scope="shared", domain="price",
                        source="data.go.kr:getStockPriceInfo",
                        extra={"note": "일별 전종목 시세+시총+상장주식수 — 전 전략 공용"})
        try:
            sp = state_path("_dgk_stage.parquet")
            if os.path.exists(sp):
                os.remove(sp)
        except Exception:
            pass
    PIPE.io("OUT", "DRIVE", "dgk_stock_price_daily", P, source="data.go.kr")
    if len(P):
        LOG.ok(f"공공데이터 패널 확정 — {len(P):,}행 · {P['code'].nunique():,}종목 · "
               f"{P['date'].nunique():,}거래일 "
               f"({P['date'].min():%Y-%m-%d} ~ {P['date'].max():%Y-%m-%d})")
    return downcast(P)


def dgk_listing_snapshots(P: pd.DataFrame, freq_days: int = 21) -> pd.DataFrame:
    """공공데이터 패널에서 '진짜 일별 상장 스냅샷' 을 뽑는다.

    ★ 이것이 KRX 스냅샷을 완전히 대체한다. 그날 시세가 관측된 종목 = 그날 상장된 종목.
      추정이 아니라 관측이므로 생존편향 제거의 근거가 훨씬 강하다.
      (전 거래일을 다 쓰면 스냅샷 테이블이 과도하게 커지므로 월 1회로 솎되,
       '유니버스 멤버십' 자체는 별도 함수에서 일별 관측을 그대로 쓴다)"""
    if P is None or len(P) == 0:
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    days = np.sort(P["date"].unique())
    pick = set(pd.DatetimeIndex(days[::max(1, freq_days)]))
    pick |= set(pd.DatetimeIndex(days).to_series().groupby(
        [pd.DatetimeIndex(days).year, pd.DatetimeIndex(days).month], observed=True).max())
    snap = P[P["date"].isin(pick)][["date", "code", "market"]].copy()
    snap = snap.rename(columns={"date": "snap_date"}).drop_duplicates(["snap_date", "code"])
    LOG.ok(f"공공데이터 기반 상장 스냅샷 {snap['snap_date'].nunique():,}개 시점 생성 "
           f"— KRX 없이 '관측된' 유니버스입니다(추정 아님)")
    out = snap.copy()
    out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
    VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                    source="data.go.kr", extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    return snap


# ── 우선주 / 비보통주 배제 ────────────────────────────────────────────────────────────────────
_PREF_SUFFIX = re.compile(r"(우[BC]?$|우선주|\d우$)")


def is_common_stock(code: str, name: str = "", market: str = "") -> bool:
    """보통주만 남긴다. 우선주·ETF·ETN·리츠·스팩을 유니버스에 섞으면 이벤트 매칭이 오염된다.

    ★ 종목코드 끝자리 규칙: 보통주는 0 으로 끝나는 것이 관례지만 예외가 많다.
      이름 규칙과 병용하고, 애매하면 '남긴다'(보수적으로 표본을 지키는 쪽)."""
    c = to_code6(code) or ""
    n = str(name or "")
    m = str(market or "").upper()
    if not c:
        return False
    if _PREF_SUFFIX.search(n):
        return False
    if re.search(r"(스팩|SPAC|[0-9]+호$)", n):
        return False
    if re.search(r"(KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE |PLUS |RISE |KOSEF|TIMEFOLIO|"
                 r"ETN$|ETF$|리츠$|REIT)", n, re.I):
        return False
    if "ETF" in m or "ETN" in m or "KONEX" in m:
        return False
    return True
