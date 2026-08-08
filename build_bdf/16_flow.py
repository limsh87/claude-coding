
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  플로우 수집 — 거래원(회원사) / 투자자별 순매수                                     ║
# ║                                                                                          ║
# ║  ★ 이 전략의 사활이 걸린 모듈이며, 동시에 가장 정직해야 하는 모듈이다.                     ║
# ║                                                                                          ║
# ║  세 갈래의 플로우가 있고 확보 난이도가 완전히 다르다:                                      ║
# ║                                                                                          ║
# ║   (A) 거래원 상위 5창구 — SPEC 원 가설의 신호                                              ║
# ║       네이버 거래원 탭은 '최종 거래일 1일치' 스냅샷 전용이다. 날짜 파라미터도               ║
# ║       페이지네이션도 없다(같은 종목 페이지의 일별시세·외국인기관 탭에는 &page= 가 있는데    ║
# ║       거래원 탭에만 없다 — 설계상 이력이 없다는 강한 신호다). 공공데이터포털에도 없고,      ║
# ║       증권사 OpenAPI 도 '현재가 기준' 스냅샷이거나 Windows COM 종속이라 소급 불가다.       ║
# ║       → 과거 10년 복원 불가. 오늘부터 쌓는 '전진 수집(B-1)' 만 가능하다.                    ║
# ║                                                                                          ║
# ║   (B) 외국인 순매수 — 소진율 차분으로 10년치를 종목당 1요청에 얻는다  ★주력★               ║
# ║       siseJson 응답 7번째 컬럼이 외국인소진율(%)이다. 보유주수 = 소진율 × 상장주식수 이고   ║
# ║       그 일별 차분이 곧 외국인 순매수(주)다. 이미 가격 수집 경로에 있어 추가 비용이 거의 0. ║
# ║                                                                                          ║
# ║   (C) 기관 순매수 — frgn.naver 페이지네이션. 페이지당 20행이라 10년이면 종목당 약 123요청.  ║
# ║       콜드 스타트가 가장 비싼 단계다. 시간예산·서킷브레이커·중단재개로 관리하고,            ║
# ║       못 받은 구간은 0 이 아니라 결측으로 남긴다.                                          ║
# ║                                                                                          ║
# ║  ★ 절단(censoring) 규칙 — 위반하면 가짜 알파가 생긴다                                      ║
# ║    거래원은 상위 5개만 공개된다. 매수 top5 에만 나온 창구의 '매도량' 은 0 이 아니라 미상이다.║
# ║    이를 0 으로 채우면 순매수가 체계적으로 과대추정되고, 대형 창구일수록 편향이 커져         ║
# ║    알파처럼 보이는 신호가 만들어진다. 반드시 NaN + 상한값(그날 5위 창구 거래량)으로 둔다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MEMBER_SNAP_COLS = ["captured_at", "trade_date", "code", "side", "rank",
                    "member_raw", "volume", "src_url", "parser_ver"]
FLOW_DAILY_COLS = ["code", "date", "actor", "actor_kind", "net_vol",
                   "censored", "upper_bound", "src"]
PARSER_VER = 2


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Phase 0 프로브 — "정말로 소급이 안 되는가" 를 코드가 직접 확인한다
# ══════════════════════════════════════════════════════════════════════════════════════════
def probe_member_window(code: str) -> dict:
    """거래원 탭의 과거 소급 가능성을 실제로 찔러본다.

    같은 URL 에 날짜 파라미터 후보를 붙여 응답이 '달라지는지' 를 본다.
    달라지지 않으면 = 파라미터가 무시된다 = 과거 조회 불가. 이것이 판정의 근거다."""
    base = "https://finance.naver.com/item/frame_trade.naver?code={c}"
    alt = "https://finance.naver.com/item/trade.naver?code={c}"
    out = {"code": code, "reachable": False, "url": "", "n_members": 0,
           "date_param_works": False, "tried": [], "sample": []}
    for u in (base, alt):
        html = http_get(u.format(c=code), source="naver_flow", force_enc="euc-kr",
                        tries=2, referer=f"https://finance.naver.com/item/main.naver?code={code}")
        if not html:
            continue
        tabs = safe_read_html(html)
        names = _extract_member_names(html)
        if names:
            out.update(reachable=True, url=u.format(c=code), n_members=len(names),
                       sample=names[:6])
            break
        if tabs:
            out.update(reachable=True, url=u.format(c=code), n_members=0)
    if not out["reachable"]:
        return out

    # 날짜 파라미터가 먹히는지: 명백히 과거인 날짜를 넣어 응답 해시가 바뀌는지 본다
    base_html = http_get(out["url"], source="naver_flow", force_enc="euc-kr", tries=1)
    h0 = sha1_str(_extract_member_names(base_html or ""))
    for pname in ("date", "trdDd", "day", "thisPage", "bizdate"):
        for val in ("20240102", "2024-01-02"):
            u2 = out["url"] + f"&{pname}={val}"
            h = http_get(u2, source="naver_flow", force_enc="euc-kr", tries=1)
            names = _extract_member_names(h or "")
            out["tried"].append(f"{pname}={val}")
            if names and sha1_str(names) != h0:
                out["date_param_works"] = True
                out["working_param"] = pname
                return out
    return out


def probe_frgn_depth(code: str, max_probe_page: int = 200) -> dict:
    """frgn.naver(기관·외국인) 가 몇 년까지 소급되는지 이분탐색으로 실측한다.
    ★ 추측하지 않는다. 이 숫자가 Phase 0 판정을 좌우한다."""
    out = {"code": code, "ok": False, "max_page": 0, "oldest_date": None, "rows_per_page": 0}

    def _page(n: int) -> Optional[pd.DataFrame]:
        html = http_get("https://finance.naver.com/item/frgn.naver", source="naver_flow",
                        params={"code": code, "page": n}, force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/frgn.naver?code={code}")
        return _parse_frgn_table(html)

    d1 = _page(1)
    if d1 is None or not len(d1):
        return out
    out["ok"] = True
    out["rows_per_page"] = len(d1)
    lo, hi = 1, 2
    while hi <= max_probe_page:
        d = _page(hi)
        if d is None or not len(d):
            break
        lo = hi
        hi *= 2
    hi = min(hi, max_probe_page)
    while lo + 1 < hi:                       # 이분탐색
        mid = (lo + hi) // 2
        d = _page(mid)
        if d is not None and len(d):
            lo = mid
        else:
            hi = mid
    last = _page(lo)
    out["max_page"] = lo
    if last is not None and len(last):
        out["oldest_date"] = str(pd.Timestamp(last["date"].min()).date())
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  파서
# ══════════════════════════════════════════════════════════════════════════════════════════
_MEMBER_ROW = re.compile(
    r"<td[^>]*>\s*(?:<[^>]+>\s*)*([가-힣A-Za-z0-9\.\&\-\s]{2,20}?)\s*(?:</[^>]+>\s*)*</td>\s*"
    r"<td[^>]*class=\"?tah[^\"]*\"?[^>]*>\s*([\d,]+)\s*</td>", re.I)


def _extract_member_names(html: str) -> List[str]:
    if not html:
        return []
    names = [m.group(1).strip() for m in _MEMBER_ROW.finditer(html)]
    return [n for n in names if n and not re.fullmatch(r"[\d,\.]+", n)]


def parse_member_page(html: str, code: str, url: str) -> pd.DataFrame:
    """거래원 페이지 → (side, rank, member_raw, volume).

    ★ 매도상위 표와 매수상위 표가 좌우로 나란히 오는 레이아웃이라 컬럼 인덱스를 믿으면 안 된다.
      표 단위로 나눠 헤더 텍스트('매도상위'/'매수상위')로 판정하고, 헤더가 없으면
      '왼쪽=매도, 오른쪽=매수' 관례를 쓰되 그 사실을 로그에 남긴다."""
    rows: List[dict] = []
    if not html:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    soup = soup_of(html)
    if soup is None:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    now = now_kst()
    tables = soup.find_all("table")
    layout_guessed = False
    for tb in tables:
        txt = tb.get_text(" ", strip=True)
        if "매도상위" in txt and "매수상위" in txt:
            # 한 표에 두 블록이 다 있는 경우: 행마다 좌(매도) / 우(매수)
            for tr in tb.find_all("tr"):
                tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                tds = [t for t in tds if t not in ("", "\xa0")]
                if len(tds) >= 4:
                    for off, side in ((0, "SELL"), (2, "BUY")):
                        nm, vol = tds[off], tds[off + 1]
                        v = re.sub(r"[^\d]", "", vol)
                        if nm and v and not re.fullmatch(r"[\d,\.%]+", nm):
                            rows.append({"side": side, "member_raw": nm, "volume": float(v)})
            continue
        side = None
        if "매도상위" in txt:
            side = "SELL"
        elif "매수상위" in txt:
            side = "BUY"
        if side is None:
            continue
        for tr in tb.find_all("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            tds = [t for t in tds if t not in ("", "\xa0")]
            if len(tds) >= 2:
                nm, v = tds[0], re.sub(r"[^\d]", "", tds[1])
                if nm and v and not re.fullmatch(r"[\d,\.%]+", nm):
                    rows.append({"side": side, "member_raw": nm, "volume": float(v)})

    if not rows:            # 폴백: 정규식으로 이름·수량 쌍만 뽑고 좌우 관례를 적용
        pairs = [(m.group(1).strip(), float(re.sub(r"[^\d]", "", m.group(2))))
                 for m in _MEMBER_ROW.finditer(html)]
        for i, (nm, v) in enumerate(pairs[:10]):
            rows.append({"side": "SELL" if i % 2 == 0 else "BUY",
                         "member_raw": nm, "volume": v})
        layout_guessed = bool(rows)

    if not rows:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    d = pd.DataFrame(rows)
    d["rank"] = d.groupby("side", observed=True).cumcount() + 1
    d = d[d["rank"] <= 5]
    d["code"] = code
    d["captured_at"] = now
    # ★ 거래일은 페이지에서 직접 읽히지 않는 경우가 많다. '캡처 시각 기준 최근 거래일' 로
    #   추론하되, 어떻게 추론했는지를 parser_ver 와 함께 남긴다(나중에 소급 교정 가능하도록).
    td = now.normalize()
    if now.hour < 16:                    # 장 마감 전이면 전 거래일 확정치일 가능성이 높다
        td = td - pd.Timedelta(days=1)
    while td.weekday() >= 5:
        td = td - pd.Timedelta(days=1)
    d["trade_date"] = td
    d["src_url"] = url
    d["parser_ver"] = PARSER_VER
    if layout_guessed:
        LOG.debug(f"거래원 레이아웃을 헤더로 판정하지 못해 좌우 관례를 적용했습니다 ({code}).")
    return d.reindex(columns=MEMBER_SNAP_COLS)


def _parse_frgn_table(html: Optional[str]) -> Optional[pd.DataFrame]:
    """frgn.naver 표 → date / inst_net / foreign_net / volume."""
    if not html:
        return None
    tabs = safe_read_html(html)
    if not tabs:
        return None
    best = None
    for t in tabs:
        cols = [str(c) for c in np.ravel(t.columns.to_list())]
        joined = " ".join(cols)
        if "날짜" in joined and ("기관" in joined or "외국인" in joined):
            best = t
            break
    if best is None:
        best = max(tabs, key=len)
    d = best.copy()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = [" ".join(str(x) for x in c if str(x) != "nan").strip() for c in d.columns]
    cmap = {str(c): str(c) for c in d.columns}
    def _find(*keys):
        for c in cmap:
            if all(k in c for k in keys):
                return c
        return None
    c_date = _find("날짜")
    c_inst = _find("기관")
    c_forg = _find("외국인", "순매매") or _find("외국인")
    c_vol = _find("거래량")
    if c_date is None:
        return None
    out = pd.DataFrame({
        "date": pd.to_datetime(d[c_date].astype(str).str.replace(".", "-", regex=False),
                               errors="coerce"),
        "inst_net": pd.to_numeric(
            d[c_inst].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_inst else np.nan,
        "foreign_net": pd.to_numeric(
            d[c_forg].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_forg else np.nan,
        "volume": pd.to_numeric(
            d[c_vol].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_vol else np.nan,
    }).dropna(subset=["date"])
    return out if len(out) else None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (B) 외국인 플로우 — 소진율 차분.  종목당 1요청으로 10년치.  ★주력 경로★
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_foreign_ratio(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """siseJson 의 7번째 컬럼(외국인소진율 %)을 종목별 1요청으로 전 구간 확보한다."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    s, e = as_ts(start), as_ts(end)
    cols = ["code", "date", "frgn_ratio"]
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("naver_foreign_ratio", scope="shared")
    frames: List[pd.DataFrame] = []
    have: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["code", "date"])
        if len(c):
            frames.append(c.reindex(columns=cols))
            cov = c.groupby("code", observed=True)["date"].agg(["min", "max"])
            pad = pd.Timedelta(days=16)
            have = set(cov.index[(cov["min"] <= s + pad) & (cov["max"] >= e - pad)])
            LOG.info(f"공용 캐시에서 외국인소진율 {len(c):,}행 / {len(have):,}종목 재사용")

    todo = [c for c in codes if c not in have]
    if RUN_MODE == "CACHED":
        todo = []

    def _one(code: str) -> Optional[pd.DataFrame]:
        txt = http_get(_NAVER_SISE_JSON, source="naver",
                       params={"symbol": code, "requestType": 1,
                               "startTime": s.strftime("%Y%m%d"), "endTime": e.strftime("%Y%m%d"),
                               "timeframe": "day"},
                       referer=f"https://finance.naver.com/item/frgn.naver?code={code}", tries=3)
        if not txt:
            return None
        rows = re.findall(r"\[([^\[\]]+)\]", txt)
        out = []
        for r in rows:
            parts = [p.strip().strip("'\"") for p in r.split(",")]
            if len(parts) < 7 or not re.fullmatch(r"\d{8}", parts[0]):
                continue
            try:
                out.append((parts[0], float(parts[6])))
            except Exception:
                continue
        if not out:
            return None
        d = pd.DataFrame(out, columns=["date", "frgn_ratio"])
        d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
        d["code"] = code
        return d.dropna(subset=["date"])[cols]

    if todo:
        LOG.info(f"외국인소진율 수집 {len(todo):,}종목 (종목당 1요청 · 10년치를 한 번에)")
        res = pmap_io(_one, todo, workers=min(FLOW_WORKERS + 2, N_WORKERS_IO), desc="외국인소진율")
        frames += [d for d in res if d is not None and len(d)]

    if not frames:
        return pd.DataFrame(columns=cols)
    F = pd.concat(frames, ignore_index=True)
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))
    if todo:
        VAULT.put_table("naver_foreign_ratio", F, scope="shared", domain="flow",
                        source="naver:siseJson",
                        extra={"note": "일별 외국인소진율(%) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_foreign_ratio", F, source="naver:siseJson")
    return downcast(F)


def foreign_net_from_ratio(fr: pd.DataFrame, mc: pd.DataFrame) -> pd.DataFrame:
    """소진율 차분 × 상장주식수 = 외국인 순매수(주).

    ★ 함정: 무상증자·액면분할로 상장주식수가 바뀌는 날은 보유주수가 기계적으로 점프한다.
      그 날의 차분은 순매수가 아니므로 결측 처리한다(0 으로 두면 가짜 대량매수가 된다)."""
    if fr is None or len(fr) == 0:
        return pd.DataFrame(columns=["code", "date", "foreign_net", "shares_used"])
    d = fr.copy()
    if mc is not None and len(mc) and "shares" in mc.columns:
        sh = mc[["code", "date", "shares"]].dropna()
        d = d.merge(sh, on=["code", "date"], how="left")
    else:
        d["shares"] = np.nan
    # 주식수가 없는 종목은 종목별 중앙값으로 대체(랭크·정규화에만 쓰이므로 무해)
    d["shares"] = d.groupby("code", observed=True)["shares"].transform(
        lambda s: s.ffill().bfill())
    d = d.sort_values(["code", "date"], kind="stable")
    g = d.groupby("code", observed=True)
    hold = d["frgn_ratio"] / 100.0 * d["shares"]
    d["foreign_net"] = hold.groupby(d["code"], observed=True).diff()
    sh_chg = g["shares"].diff().abs() > (d["shares"].abs() * 1e-6)
    n_bad = int((sh_chg & d["foreign_net"].notna()).sum())
    set_where(d, sh_chg.fillna(False), "foreign_net", np.nan)
    if n_bad:
        LOG.info(f"상장주식수가 변동한 {n_bad:,}건의 외국인 순매수를 결측 처리했습니다 "
                 f"(증자·분할로 인한 기계적 점프를 매수로 계상하지 않기 위함).")
    return d[["code", "date", "foreign_net", "shares"]].rename(columns={"shares": "shares_used"})


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (C) 기관 플로우 — frgn.naver 페이지네이션.  시간예산 + 서킷브레이커 + 중단재개
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_investor_flow_paged(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """기관/외국인 순매매(주). 페이지당 20행이라 콜드 스타트가 비싸다.

    설계:
      · 종목 처리 순서 = 이벤트 수가 많은 종목 우선 (예산이 끊겨도 쓸모 있는 쪽부터)
      · 페이지는 1(최근) → N(과거) 순  ⇒ 중단돼도 최신 구간이 먼저 완성된다 (SPEC §2.3)
      · 연속 실패 FLOW_CIRCUIT_BREAK_N 회 → 즉시 전체 중단 + 상태 저장
      · 시간예산 초과 → '실패' 가 아니라 '여기까지 저장하고 정상 종료'
      · 못 받은 구간은 0 이 아니라 결측이다."""
    cols = ["code", "date", "inst_net", "foreign_net", "volume"]
    codes = [c for c in map(to_code6, codes) if c]
    s, e = as_ts(start), as_ts(end)
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("naver_investor_flow", scope="shared")
    frames: List[pd.DataFrame] = []
    done: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["code", "date"])
        if len(c):
            frames.append(c.reindex(columns=cols))
            cov = c.groupby("code", observed=True)["date"].min()
            done = set(cov.index[cov <= s + pd.Timedelta(days=20)])
            LOG.info(f"공용 캐시에서 투자자별 수급 {len(c):,}행 재사용 "
                     f"(전 구간 완료 {len(done):,}종목)")

    if not FLOW_INSTITUTION_ENABLE:
        LOG.info("FLOW_INSTITUTION_ENABLE=False — 기관 플로우 신규 수집을 건너뜁니다. "
                 "외국인 플로우(소진율 차분)만으로 전 구간이 완성됩니다.")
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols))
    if RUN_MODE == "CACHED":
        LOG.info("CACHED 모드 — 투자자별 수급 신규 수집을 건너뜁니다.")
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols))

    todo = [c for c in dict.fromkeys(codes) if c not in done]
    if not todo:
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)

    t0 = time.time()
    budget_s = float(FLOW_TIME_BUDGET_MIN) * 60.0
    lk = threading.Lock()
    st = {"fail_streak": 0, "stop": False, "reason": "", "n_req": 0, "n_code_done": 0}

    LOG.info(f"기관/외국인 수급 수집 {len(todo):,}종목 · 시간예산 {FLOW_TIME_BUDGET_MIN}분 · "
             f"동시 {FLOW_WORKERS} · 요청간 {FLOW_DELAY_RANGE[0]}~{FLOW_DELAY_RANGE[1]}초 "
             f"(차단 방지 · SPEC §2.3)")

    def _one(code: str) -> Optional[pd.DataFrame]:
        if st["stop"]:
            return None
        got: List[pd.DataFrame] = []
        for page in range(1, 400):
            with lk:
                if st["stop"]:
                    return pd.concat(got, ignore_index=True) if got else None
                if time.time() - t0 > budget_s:
                    st["stop"] = True
                    st["reason"] = "TIME_BUDGET"
                    return pd.concat(got, ignore_index=True) if got else None
                st["n_req"] += 1
            polite_sleep()
            html = http_get("https://finance.naver.com/item/frgn.naver", source="naver_flow",
                            params={"code": code, "page": page}, force_enc="euc-kr", tries=3,
                            referer=f"https://finance.naver.com/item/frgn.naver?code={code}")
            d = _parse_frgn_table(html)
            with lk:
                if d is None or not len(d):
                    st["fail_streak"] += 1
                    if st["fail_streak"] >= FLOW_CIRCUIT_BREAK_N:
                        st["stop"] = True
                        st["reason"] = "CIRCUIT_BREAKER"
                    break
                st["fail_streak"] = 0
            d["code"] = code
            got.append(d)
            if pd.Timestamp(d["date"].min()) <= s:
                break
        if not got:
            return None
        out = pd.concat(got, ignore_index=True)
        out = out[(out["date"] >= s) & (out["date"] <= e)]
        with lk:
            st["n_code_done"] += 1
        return out.reindex(columns=cols) if len(out) else None

    res = pmap_io(_one, todo, workers=FLOW_WORKERS, desc="투자자별 수급")
    new = [d for d in res if d is not None and len(d)]
    frames += new
    el = (time.time() - t0) / 60.0

    if st["stop"]:
        if st["reason"] == "CIRCUIT_BREAKER":
            LOG.error(f"연속 실패 {FLOW_CIRCUIT_BREAK_N}회 → 서킷 브레이커 작동. "
                      f"여기까지 받은 {len(new):,}종목분을 저장하고 중단합니다. "
                      f"잠시 후(수십 분~수 시간) 다시 실행하면 이어서 받습니다. "
                      f"차단이 의심되면 FLOW_WORKERS 를 3 으로, "
                      f"FLOW_DELAY_RANGE 를 (0.8, 2.0) 으로 낮추세요.")
        else:
            LOG.warn(f"시간예산 {FLOW_TIME_BUDGET_MIN}분을 소진했습니다 — 여기까지 저장하고 "
                     f"정상 종료합니다. 다음 실행이 이어서 받습니다(최근→과거 순이라 "
                     f"최신 구간부터 완성됩니다). 완료 {st['n_code_done']:,}/{len(todo):,}종목.")
    else:
        LOG.ok(f"투자자별 수급 수집 완료 — {st['n_code_done']:,}종목 · "
               f"{st['n_req']:,}요청 · {el:.1f}분")

    if not frames:
        return pd.DataFrame(columns=cols)
    F = pd.concat(frames, ignore_index=True)
    F["date"] = as_ts_series(F["date"])
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))
    if new:
        VAULT.put_table("naver_investor_flow", F, scope="shared", domain="flow",
                        source="naver:frgn",
                        extra={"note": "일별 기관·외국인 순매매(주) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_investor_flow", F, source="naver:frgn")
    return downcast(F)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (A) 거래원 전진 수집 (B-1) — 과거는 못 만들지만 오늘부터는 쌓을 수 있다
# ══════════════════════════════════════════════════════════════════════════════════════════
def collect_member_snapshot(codes: Sequence[str], limit: int = 0) -> pd.DataFrame:
    """오늘자 거래원 상위 5창구 스냅샷을 공용 인덱스에 append 한다.

    ★ member_raw 는 절대 정규화해서 저장하지 않는다. 원문을 영구 보존해야
      나중에 매핑 오류를 소급 수정할 수 있다(정규화는 파생 단계에서 한다)."""
    codes = [c for c in map(to_code6, codes) if c]
    if limit:
        codes = codes[:limit]
    if not codes or RUN_MODE in ("CACHED", "SMOKE") or not FLOW_MEMBER_FORWARD:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)

    st = {"fail": 0, "stop": False}
    lk = threading.Lock()

    def _one(code: str) -> Optional[pd.DataFrame]:
        if st["stop"]:
            return None
        polite_sleep()
        url = f"https://finance.naver.com/item/frame_trade.naver?code={code}"
        html = http_get(url, source="naver_flow", force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/main.naver?code={code}")
        d = parse_member_page(html or "", code, url)
        with lk:
            if d is None or not len(d):
                st["fail"] += 1
                if st["fail"] >= FLOW_CIRCUIT_BREAK_N:
                    st["stop"] = True
                    LOG.warn("거래원 스냅샷 연속 실패 — 서킷 브레이커 작동(전진수집만 중단). "
                             "백테스트 경로에는 영향이 없습니다.")
                return None
            st["fail"] = 0
        return d

    res = pmap_io(_one, codes, workers=FLOW_WORKERS, desc="거래원 스냅샷(전진수집)")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.info("거래원 스냅샷을 받지 못했습니다 — 전진수집만 건너뜁니다(백테스트 무관).")
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)

    S = pd.concat(got, ignore_index=True)
    prev = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
    if prev is not None and len(prev):
        prev = prev.reindex(columns=MEMBER_SNAP_COLS)
        S = pd.concat([prev, S], ignore_index=True)
    S["trade_date"] = as_ts_series(S["trade_date"])
    S["captured_at"] = as_ts_series(S["captured_at"])
    S = S.drop_duplicates(["trade_date", "code", "side", "rank", "member_raw"], keep="last")
    VAULT.put_table("naver_member_flow_snapshot", S, scope="shared", domain="flow",
                    source="naver:trade",
                    extra={"note": "거래원 상위5창구 일별 스냅샷(전진수집) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_member_flow_snapshot", S, source="naver:trade")
    LOG.ok(f"거래원 전진수집 — 이번 회차 {len(pd.concat(got)):,}행 · 누적 {len(S):,}행 "
           f"({S['trade_date'].nunique():,}거래일). 과거는 만들 수 없지만 오늘부터는 쌓입니다.")
    return S


def member_snapshot_to_daily(S: pd.DataFrame, px: pd.DataFrame,
                             bm: "BrokerMap") -> pd.DataFrame:
    """거래원 스냅샷 → 일별 창구 순매수. ★ 절단(censoring)을 명시적으로 보존한다.

    매수 top5 에만 있는 창구의 매도량은 0 이 아니라 '미상' 이다.
    NaN 으로 두고 상한(그날 매도 5위 창구의 거래량)을 함께 남겨 구간추정으로 다룬다."""
    cols = FLOW_DAILY_COLS + ["top5_coverage", "buy_vol", "sell_vol"]
    if S is None or len(S) == 0:
        return pd.DataFrame(columns=cols)
    d = S.copy()
    d["trade_date"] = as_ts_series(d["trade_date"])
    d["member_key"] = d["member_raw"].map(lambda x: bm.resolve(x) or f"UNMAPPED:{x}")
    piv = (d.pivot_table(index=["code", "trade_date", "member_key"], columns="side",
                         values="volume", aggfunc="sum").reset_index())
    for c in ("BUY", "SELL"):
        if c not in piv.columns:
            piv[c] = np.nan
    piv = piv.rename(columns={"BUY": "buy_vol", "SELL": "sell_vol", "trade_date": "date"})

    # 절단 상한 = 그날 각 side 의 5위(=최소) 공개 거래량
    lo = (d.groupby(["code", "trade_date", "side"], observed=True)["volume"].min()
            .unstack("side").rename(columns={"BUY": "buy_lb", "SELL": "sell_lb"})
            .reset_index().rename(columns={"trade_date": "date"}))
    piv = piv.merge(lo, on=["code", "date"], how="left")

    piv["censored"] = piv["buy_vol"].isna() | piv["sell_vol"].isna()
    # 미상 쪽의 상한: 공개된 5위 거래량. 그보다 클 수는 없다.
    piv["upper_bound"] = np.where(piv["sell_vol"].isna(), piv.get("sell_lb", np.nan),
                                  np.where(piv["buy_vol"].isna(), piv.get("buy_lb", np.nan), 0.0))
    # ★ net_vol 은 양쪽이 다 관측된 경우에만 확정값이다. 아니면 결측으로 둔다(0 채움 금지).
    piv["net_vol"] = np.where(piv["censored"], np.nan,
                              piv["buy_vol"].fillna(0) - piv["sell_vol"].fillna(0))

    if px is not None and len(px):
        v = px[["code", "date", "volume"]].rename(columns={"volume": "tot_vol"})
        piv = piv.merge(v, on=["code", "date"], how="left")
        tot5 = (piv.groupby(["code", "date"], observed=True)[["buy_vol", "sell_vol"]].sum().sum(axis=1)
                   .rename("t5").reset_index())
        piv = piv.merge(tot5, on=["code", "date"], how="left")
        piv["top5_coverage"] = safe_div(piv["t5"], 2.0 * piv["tot_vol"])
        piv = piv.drop(columns=[c for c in ("t5", "tot_vol") if c in piv.columns])
    else:
        piv["top5_coverage"] = np.nan

    piv["actor"] = piv["member_key"]
    piv["actor_kind"] = "MEMBER"
    piv["src"] = "naver:trade"
    n_cens = int(piv["censored"].sum())
    if n_cens:
        LOG.info(f"거래원 일별화: {len(piv):,}행 중 {n_cens:,}행이 상위5 절단으로 "
                 f"순매수 미확정입니다 → 0 으로 채우지 않고 결측 + 상한으로 보존했습니다. "
                 f"(0 으로 채우면 대형 창구일수록 순매수가 과대추정되어 가짜 알파가 생깁니다)")
    return piv.reindex(columns=cols + ["member_key"])


# ══════════════════════════════════════════════════════════════════════════════════════════
#  통합: 이벤트에 쓸 '행위자별 일별 순매수' 패널
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_flow_panel(inv: pd.DataFrame, fnet: pd.DataFrame, mem_daily: pd.DataFrame,
                     px: pd.DataFrame) -> pd.DataFrame:
    """(code, date, actor, actor_kind, netbuy_share) 로 통일한다.

    actor_kind:
      MEMBER  = 실제 거래원 창구 (전진수집분만 존재)
      INST    = 기관 합계        (PROXY 축)
      FOREIGN = 외국인 합계      (PROXY 축)
    netbuy_share = 순매수(주) / 그날 총거래량   ← SPEC §6.2 정의
    """
    parts: List[pd.DataFrame] = []
    vol = (px[["code", "date", "volume"]].copy() if px is not None and len(px)
           else pd.DataFrame(columns=["code", "date", "volume"]))
    vol["date"] = as_ts_series(vol["date"])

    def _mk(df: pd.DataFrame, col: str, actor: str, kind: str, src: str):
        if df is None or len(df) == 0 or col not in df.columns:
            return
        t = df[["code", "date", col]].dropna(subset=["code", "date"]).copy()
        t["date"] = as_ts_series(t["date"])
        t = t.rename(columns={col: "net_vol"})
        t["actor"], t["actor_kind"], t["src"] = actor, kind, src
        t["censored"], t["upper_bound"] = False, np.nan
        parts.append(t)

    _mk(inv, "inst_net", "INST", "INST", "naver:frgn")
    if inv is not None and len(inv) and "foreign_net" in inv.columns:
        _mk(inv, "foreign_net", "FOREIGN", "FOREIGN", "naver:frgn")
    if fnet is not None and len(fnet):
        f = fnet.copy()
        # frgn 페이지에서 이미 외국인을 받은 (code,date) 는 그쪽을 우선한다(직접 관측값)
        if parts:
            seen = pd.concat([p[p["actor"] == "FOREIGN"][["code", "date"]] for p in parts
                              if (p["actor"] == "FOREIGN").any()], ignore_index=True) \
                if any((p["actor"] == "FOREIGN").any() for p in parts) else None
            if seen is not None and len(seen):
                f = f.merge(seen.assign(_seen=1), on=["code", "date"], how="left")
                f = f[f["_seen"].isna()].drop(columns=["_seen"])
        _mk(f, "foreign_net", "FOREIGN", "FOREIGN", "naver:siseJson-ratio")

    if mem_daily is not None and len(mem_daily):
        m = mem_daily[["code", "date", "actor", "actor_kind", "net_vol",
                       "censored", "upper_bound", "src"]].copy()
        m["date"] = as_ts_series(m["date"])
        parts.append(m)

    if not parts:
        LOG.warn("플로우 패널이 비었습니다 — 신호를 만들 수 없습니다. "
                 "네트워크/캐시 상태를 확인하세요.")
        return pd.DataFrame(columns=FLOW_DAILY_COLS + ["netbuy_share"])

    F = pd.concat([p.reindex(columns=FLOW_DAILY_COLS) for p in parts], ignore_index=True)
    F = F.dropna(subset=["code", "date", "actor"])
    F = F.merge(vol, on=["code", "date"], how="left")
    F["netbuy_share"] = safe_div(F["net_vol"], F["volume"])
    # 거래량이 0/결측인 날은 비율이 정의되지 않는다 → 0 이 아니라 결측
    set_where(F, (~np.isfinite(F["netbuy_share"].to_numpy(dtype=float))), "netbuy_share", np.nan)
    F = F.drop(columns=["volume"])
    F = F.drop_duplicates(["code", "date", "actor"], keep="last").reset_index(drop=True)

    stat = (F.groupby("actor_kind", observed=True)
              .agg(행=("code", "size"), 종목=("code", "nunique"),
                   시작=("date", "min"), 종료=("date", "max"),
                   유효비율=("netbuy_share", lambda s: float(s.notna().mean())))
              .reset_index())
    LOG.table([[r.actor_kind, f"{r.행:,}", f"{r.종목:,}",
                f"{pd.Timestamp(r.시작):%Y-%m}", f"{pd.Timestamp(r.종료):%Y-%m}",
                f"{100*r.유효비율:.1f}%"] for r in stat.itertuples()],
              ["행위자", "행수", "종목수", "시작", "종료", "유효비율"],
              ["l", "r", "r", "c", "c", "r"], title="플로우 패널 구성")
    PIPE.io("OUT", "MEM", "flow_panel", F)
    return downcast(F)
