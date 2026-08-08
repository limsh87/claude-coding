
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


def _dgk_day(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """하루치 전 종목. 실패는 None, 휴장(정상 0건)은 빈 DataFrame 으로 구분해서 돌려준다."""
    key = _dgk_key()
    if not key:
        return None
    bas = day.strftime("%Y%m%d")
    rows: List[dict] = []
    for page in range(1, 6):                     # 안전 상한 (하루 5,000행이면 충분)
        js = http_json(DGK_BASE, source="datagokr",
                       params={"serviceKey": key, "numOfRows": 1000, "pageNo": page,
                               "resultType": "json", "basDt": bas}, tries=3, timeout=30)
        if not isinstance(js, dict):
            return None                          # XML 오류응답 / 파싱 실패 → '수집 실패'
        body = (js.get("response") or {}).get("body") or {}
        hdr = (js.get("response") or {}).get("header") or {}
        rc = str(hdr.get("resultCode", "")).strip()
        if rc and rc not in ("00", "0", ""):
            LOG.debug(f"data.go.kr resultCode={rc} msg={hdr.get('resultMsg')} @{bas}")
            return None
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
    if not rows:
        return pd.DataFrame(columns=DGK_COLS)    # 휴장(정상 0건)

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
    return out.dropna(subset=["code", "date", "close"])


def fetch_datagokr_panel(cal_start: str, cal_end: str) -> pd.DataFrame:
    """일별 전 종목 패널. 캐시 우선 → 부족한 날짜만 → 드라이브 공용 인덱스에 재적재.

    ★ 수집 순서는 최근 → 과거 다. 차단당하거나 중단되어도 '최신 구간' 이 먼저 확보되어
      부분 결과로도 최근 몇 년 백테스트가 가능하다 (SPEC §2.3).
    ★ 휴장일은 'holiday' 로, 실패일은 'fail' 로 각각 기록한다. 이 둘을 섞으면 몇 달 뒤에
      패널의 구멍이 무엇이었는지 영영 알 수 없게 된다."""
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

    # 상태 저장(중단·재개): 이미 '휴장 확인' 된 날은 다시 때리지 않는다
    state_p = out_path("_dgk_state.json")
    state = {"holiday": [], "fail": []}
    _prev = read_json(state_p, default=None)
    if isinstance(_prev, dict):
        state.update(_prev)
    known_holiday = set(state.get("holiday", []))

    if not key:
        if frames:
            LOG.info("DATA_GO_KR_KEY 가 없어 신규 수집은 건너뛰고 캐시만 사용합니다.")
        else:
            LOG.warn("DATA_GO_KR_KEY 가 비어 있습니다 → PIT 시가총액/일별 상장 스냅샷을 "
                     "정품 경로로 만들 수 없습니다. 시총은 근사(T2~T4)로 강등되고, "
                     "유니버스는 상장일·폐지일 기반으로만 구성됩니다(그래도 동작합니다). "
                     "정확도를 크게 올리려면 상단 ②-b 안내대로 키를 발급받아 넣으세요.")
        return (pd.concat(frames, ignore_index=True) if frames
                else pd.DataFrame(columns=DGK_COLS))

    days = pd.bdate_range(s, e)                       # 주말 제외 (공휴일은 응답 0건으로 판별)
    todo = [d for d in days
            if d.strftime("%Y%m%d") not in have_days
            and d.strftime("%Y%m%d") not in known_holiday]
    todo = sorted(todo, reverse=True)                 # ★ 최근 → 과거 (SPEC §2.3)

    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 공공데이터 {len(todo):,}일 신규 수집을 건너뜁니다.")
        todo = []

    if todo:
        LOG.info(f"공공데이터 일별 전종목 수집 {len(todo):,}일 (최근→과거 · 하루 1~3요청)")
        got: List[pd.DataFrame] = []
        n_holiday = n_fail = 0
        streak = 0
        stop = False
        # 스레드 수를 낮게 유지한다 — 공공데이터포털은 순간 폭주에 민감하다.
        lk = threading.Lock()

        def _one(day: pd.Timestamp):
            nonlocal n_holiday, n_fail, streak, stop
            if stop:
                return None
            polite_sleep(0.05, 0.25)
            d = _dgk_day(day)
            with lk:
                if d is None:
                    n_fail += 1
                    streak += 1
                    state["fail"].append(day.strftime("%Y%m%d"))
                    if streak >= FLOW_CIRCUIT_BREAK_N:
                        stop = True
                        LOG.error(f"공공데이터 연속 실패 {streak}회 → 서킷 브레이커 작동. "
                                  f"여기까지 받은 분량은 캐시에 저장하고 중단합니다. "
                                  f"(키 오류이거나 일일 트래픽 한도 초과일 수 있습니다)")
                    return None
                streak = 0
                if len(d) == 0:
                    n_holiday += 1
                    state["holiday"].append(day.strftime("%Y%m%d"))
                    return None
            return d

        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="공공데이터 시세")
        got = [d for d in res if d is not None and len(d)]
        frames += got
        try:
            state["holiday"] = sorted(set(state["holiday"]))
            state["fail"] = sorted(set(state["fail"]))[-4000:]
            write_json(state_p, state)
        except Exception:
            pass
        LOG.ok(f"공공데이터 수집 완료 — 신규 {len(got):,}일 · 휴장 {n_holiday:,}일 · 실패 {n_fail:,}일")
        if n_fail > len(todo) * 0.3:
            LOG.warn(f"실패율이 {100*n_fail/max(len(todo),1):.0f}% 로 높습니다. "
                     f"인증키(Decoding) 와 일일 트래픽 한도를 확인하세요. "
                     f"실패한 날짜는 결측으로 남고 0으로 채우지 않습니다.")

    if not frames:
        return pd.DataFrame(columns=DGK_COLS)

    P = pd.concat(frames, ignore_index=True)
    P["date"] = as_ts_series(P["date"])
    P["code"] = P["code"].map(to_code6)
    P = (P.dropna(subset=["date", "code", "close"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))

    VAULT.put_table("dgk_stock_price_daily", P, scope="shared", domain="price",
                    source="data.go.kr:getStockPriceInfo",
                    extra={"note": "일별 전종목 시세+시총+상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "dgk_stock_price_daily", P, source="data.go.kr")
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
