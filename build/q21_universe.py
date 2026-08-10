

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q1  분기 리밸런싱 캘린더 · PIT 시가총액 · U-1000 유니버스 (§3, §4)                      ║
# ║                                                                                          ║
# ║  시점 규약(§4)을 코드로 못박는다:                                                          ║
# ║    signal_date = 리밸런싱일(3/1·6/1·9/1·12/1) 직전 거래일  ← 가격/수급은 t-1 종가까지만     ║
# ║    exec_date   = 리밸런싱일 이후 첫 거래일의 '시가'로 체결                                  ║
# ║  둘을 분리하지 않으면 '오늘 종가를 보고 오늘 종가에 산다'가 되어 곧바로 미래누수다.          ║
# ║                                                                                          ║
# ║  시가총액은 반드시 PIT 여야 한다. 현재 시점 시총으로 과거 랭크를 만들면 (a) 그 사이 급등한  ║
# ║  종목이 과거에 대형주였던 것처럼 취급되고 (b) 폐지 종목은 시총이 없어 통째로 사라진다.      ║
# ║  → 두 번째가 곧 생존자편향이다. 그래서 폐지 종목의 시총도 '살아 있던 시점 기준'으로 만든다. ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 20_pit.Universe 가 읽는 시즈닝 상수를 헤더 설정과 일치시킨다(Universe 생성 전에 적용된다).
LISTING_SEASONING_DAYS = SEASONING_DAYS

# ── 키 컬럼은 절대 category 로 만들지 않는다 ────────────────────────────────────────────────
#  ★ 공용 downcast_q() 는 저카디널리티 object 컬럼을 category 로 바꿔 RAM 을 크게 줄인다.
#    그런데 category Series 에 .map() 을 걸면 결과도 category 로 나온다. 그 결과가 날짜라면
#    `ld >= dl - 15일` 같은 비교에서 "Unordered Categoricals can only compare equality" 로
#    죽고, 하필 그 코드가 '보유 중 상장폐지 처리'라 생존자편향 방어가 통째로 무너진다.
#    (실제로 계약 Q3 가 이 경로를 잡아냈다)
#    merge/merge_asof 의 결합키가 한쪽만 category 인 경우에도 조용히 어긋날 수 있다.
#    → 키·식별자 컬럼만 문자열로 되돌린다. 수치 컬럼의 다운캐스트 이득은 그대로 남는다.
_NEVER_CAT = ("code", "corp_code", "rcept_no", "report_uid", "analyst_id", "stock_code",
              "broker_id", "src_cap", "exit_kind", "flow_src", "parse_status")


def downcast_q(df: pd.DataFrame) -> pd.DataFrame:
    d = downcast(df)
    if d is None or d.empty:
        return d
    for c in _NEVER_CAT:
        if c in d.columns and str(d[c].dtype) == "category":
            d[c] = d[c].astype(str)
    return d

# ── §4 시점 규약: "공시는 rcept_dt + 1거래일부터 사용 가능" ──────────────────────────────────
#  ★ 공용 코어(12_ingest_dart_fin)는 knowledge_date = 접수일자(rcept_dt) 그대로 쓴다.
#    접수는 장중에도 일어나므로 '접수일 종가 기준 신호'에 그 공시를 쓰면 아주 작지만 실재하는
#    누수가 된다. QVF 는 규약대로 한 거래일을 더 민다. 캘린더 하루가 아니라 '거래일' 하루다 —
#    연휴 앞 금요일 접수분을 토요일부터 알 수 있다고 처리하면 결국 같은 누수가 남는다.
QVF_TRADING_DAYS: np.ndarray = np.array([], dtype="datetime64[ns]")


def set_trading_days(px_daily: pd.DataFrame):
    globals()["QVF_TRADING_DAYS"] = qvf_trading_days(px_daily)
    LOG.debug(f"거래일 캘린더 확정: {len(QVF_TRADING_DAYS):,}일")


def next_trading_day(x):
    """x 이후(초과) 첫 거래일. 거래일 배열이 아직 없으면 영업일(Mon-Fri) +1 로 폴백한다."""
    t = as_ts(x)
    if t is None:
        return None
    td = QVF_TRADING_DAYS
    if len(td):
        i = int(np.searchsorted(td, np.datetime64(t), side="right"))
        if i < len(td):
            return as_ts(td[i])
    return (t + pd.offsets.BDay(1)).normalize()


def next_trading_day_series(s) -> pd.Series:
    """벡터화판. 40만 행에 파이썬 루프를 돌리지 않기 위해 searchsorted 를 한 번만 쓴다."""
    v = as_ts_series(s)
    td = QVF_TRADING_DAYS
    if not len(td):
        return (v + pd.offsets.BDay(1)).dt.normalize()
    arr = v.to_numpy(dtype="datetime64[ns]")
    idx = np.searchsorted(td, arr, side="right")
    inside = (idx < len(td)) & ~pd.isna(v).to_numpy()
    out = np.full(len(v), np.datetime64("NaT"), dtype="datetime64[ns]")
    out[inside] = td[idx[inside]]
    res = pd.Series(out, index=v.index)
    # 배열 끝을 넘어선 최근 공시는 영업일 +1 로 보수적으로 처리한다.
    tail = v.notna() & res.isna()
    if tail.any():
        res.loc[tail] = (v[tail] + pd.offsets.BDay(1)).dt.normalize()
    return res


def dart_knowledge_date(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """접수일자 → 사용가능일(= 접수일 다음 거래일). §4 규약."""
    return next_trading_day(_knowledge_from_rcept(rcept_no, reprt_code, int(year)))


def apply_t_plus_1(df: pd.DataFrame, label: str = "") -> pd.DataFrame:
    """공용 코어가 만든 PIT 테이블의 knowledge_date 를 §4 규약(+1거래일)으로 민다.

    ★ event_date 는 건드리지 않는다. 밀어야 하는 것은 '언제 알 수 있었나' 뿐이다.
    """
    if df is None or not len(df) or "knowledge_date" not in df.columns:
        return df
    d = df.copy()
    before = as_ts_series(d["knowledge_date"])
    d["knowledge_date"] = next_trading_day_series(before)
    moved = int((d["knowledge_date"] > before).sum())
    if moved:
        LOG.debug(f"§4 규약 적용({label}): knowledge_date 를 +1거래일 이동 {moved:,}행")
    return d

# 우선주 / 스팩 / 리츠 / ETF·ETN 판별 ------------------------------------------------------
#  ★ 종목코드 6번째 자리 규칙: 보통주는 '0'. 구형 우선주는 5/7/9, 2024 개편 신형은 K/L/M/N.
#    이름만으로 거르면 '삼성전자우' 는 잡아도 '현대차2우B' 같은 변형에서 새고,
#    코드만으로 거르면 6자리 영숫자 신형에서 샌다. 둘을 OR 로 묶는다.
_PREF_NAME_RE = re.compile(r"우(?:B|C)?$|\d+우(?:B|C)?$|우선주")
_SPAC_RE = re.compile(r"스팩|기업인수목적")
_REIT_RE = re.compile(r"리츠|위탁관리부동산투자|기업구조조정부동산투자|부동산투자회사")
_FUND_RE = re.compile(r"^(KODEX|TIGER|KBSTAR|ARIRANG|KINDEX|HANARO|SOL |ACE |PLUS |RISE |"
                      r"KOSEF|TREX|FOCUS|마이다스|파워|미래에셋TIGER)|ETN$|ETF$|"
                      r"레버리지$|인버스$|선물\s*ETN")


def is_preferred(code: str, name: str = "") -> bool:
    c = str(code or "")
    if len(c) == 6 and c[5] not in ("0",):
        # 신형 영숫자 코드는 6번째가 0/K/L/M/N 이고 0 만 보통주다. 구형은 0 이 보통주.
        return True
    return bool(_PREF_NAME_RE.search(str(name or "")))


def classify_exclusion(code: str, name: str) -> str:
    """이름·코드만으로 판별 가능한 구조적 제외 사유. 없으면 빈 문자열."""
    nm = str(name or "").strip()
    if is_preferred(code, nm):
        return "우선주"
    if _SPAC_RE.search(nm):
        return "스팩"
    if _REIT_RE.search(nm):
        return "리츠"
    if _FUND_RE.search(nm):
        return "ETF/ETN"
    return ""


# ── 거래일 캘린더 / 리밸런싱 격자 ────────────────────────────────────────────────────────────
def qvf_trading_days(px_daily: pd.DataFrame) -> np.ndarray:
    """전 종목 일봉에서 유도한 실제 거래일 배열. 공휴일 테이블을 따로 두지 않는다
    (테이블을 두면 그 테이블이 틀렸을 때 조용히 하루씩 밀린다)."""
    if px_daily is None or not len(px_daily):
        return np.array([], dtype="datetime64[ns]")
    d = as_ts_series(px_daily["date"]).dropna()
    return np.sort(pd.unique(d.values))


def qvf_rebal_calendar(px_daily: pd.DataFrame, start: str, end: str,
                       shift_days: int = 0) -> pd.DataFrame:
    """분기 리밸런싱 캘린더.

    shift_days: 강건성(§8.4 '리밸런싱 시점 ±5거래일')용. 거래일 기준으로 민다.
    반환 컬럼: rebal(명목일) · signal_date(직전 거래일) · exec_date(체결 거래일)
    """
    td = qvf_trading_days(px_daily)
    if not len(td):
        raise RuntimeError("거래일을 하나도 만들 수 없습니다 — 일봉 패널이 비었습니다.")
    s, e = as_ts(start), as_ts(end)
    nominal = [as_ts(f"{y}-{m:02d}-{REBAL_DAY:02d}")
               for y in range(s.year, e.year + 1) for m in REBAL_MONTHS]
    nominal = [d for d in nominal if s <= d <= e]

    rows = []
    n_td = len(td)
    for d in nominal:
        dd = np.datetime64(d)
        # 체결일 = 명목일 이후(포함) 첫 거래일
        i_exec = int(np.searchsorted(td, dd, side="left"))
        if i_exec >= n_td:
            continue                      # 패널 끝을 넘어선 리밸런싱은 만들지 않는다
        i_exec = max(0, min(n_td - 1, i_exec + int(shift_days)))
        # 신호일 = 체결일 '직전' 거래일. 반드시 strictly before 여야 한다(t-1 종가 규약).
        i_sig = i_exec - 1
        if i_sig < 0:
            continue
        rows.append({"rebal": d, "signal_date": as_ts(td[i_sig]), "exec_date": as_ts(td[i_exec])})
    cal = pd.DataFrame(rows)
    if cal.empty:
        raise RuntimeError("리밸런싱 캘린더가 비었습니다 — 백테스트 구간과 일봉 구간이 겹치지 않습니다.")
    # 방어: 신호일이 체결일보다 늦거나 같으면 그 자체로 미래누수다. 여기서 세운다.
    bad = cal["signal_date"] >= cal["exec_date"]
    if bad.any():
        raise RuntimeError(f"[시점규약 위반] signal_date >= exec_date 인 리밸런싱이 "
                           f"{int(bad.sum())}건 있습니다. 캘린더 구성이 잘못되었습니다.")
    LOG.ok(f"분기 리밸런싱 캘린더 {len(cal)}개 시점 "
           f"({cal['rebal'].min():%Y-%m} ~ {cal['rebal'].max():%Y-%m}"
           + (f", {shift_days:+d}거래일 이동" if shift_days else "") + ") — "
           f"신호는 직전 거래일 종가까지, 체결은 익 거래일 시가")
    return cal


# ── PIT 시가총액 / 상장주식수 ───────────────────────────────────────────────────────────────
def fetch_krx_cap_snapshots(dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """★1순위: pykrx 전종목 시총 스냅샷. 날짜당 1~2호출로 전 종목을 받으므로 가장 싸고,
    '그 날 실제 시총'이라 정의상 PIT 이다.

    반환: code · snap_date · mktcap · shares
    """
    cols = ["code", "snap_date", "mktcap", "shares"]
    cached = VAULT.get_table("krx_marketcap_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"캐시에서 시가총액 스냅샷 {len(have)}개 시점 재사용")

    todo = [d for d in dates if as_ts(d).strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []
    if todo and pykrx_stock is None:
        LOG.warn("pykrx 가 없어 시총 스냅샷을 받지 못합니다 — DART 주식총수 경로로 폴백합니다.")
        todo = []
    if todo:
        KRXG.warmup()

    new_rows: List[dict] = []
    if todo:
        LOG.info(f"KRX 전종목 시가총액 스냅샷 {len(todo)}개 시점 수집 (직렬 — 세션 충돌 방지)")
        streak = 0
        for d in tqdm(todo, desc="시총 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           as_ts(d).strftime("%Y%m%d"), prev=True) or as_ts(d).strftime("%Y%m%d")
            got = False
            for mkt in ("ALL", "KOSPI", "KOSDAQ"):
                t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
                if t is None or not len(t):
                    continue
                t = t.reset_index()
                ren = {"티커": "code", "시가총액": "mktcap", "상장주식수": "shares"}
                t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
                if "code" not in t.columns:
                    t = t.rename(columns={t.columns[0]: "code"})
                if "mktcap" not in t.columns:
                    continue
                t["code"] = t["code"].map(to_code6)
                t = t.dropna(subset=["code"])
                for c in ("mktcap", "shares"):
                    if c not in t.columns:
                        t[c] = np.nan
                    t[c] = pd.to_numeric(t[c], errors="coerce")
                t = t[["code", "mktcap", "shares"]]
                t["snap_date"] = as_ts(d)
                new_rows.extend(t.to_dict("records"))
                got = True
                if mkt == "ALL":
                    break
            streak = 0 if got else streak + 1
            if streak >= 5:
                LOG.warn("시총 스냅샷이 연속 5회 비었습니다(세션 만료/차단 추정) — "
                         "수집을 중단하고 DART 주식총수 경로로 폴백합니다.")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True)
    S["snap_date"] = as_ts_series(S["snap_date"])
    S = (S.dropna(subset=["code", "snap_date"])
          .drop_duplicates(["code", "snap_date"], keep="last")
          .reindex(columns=cols))
    if new_rows:
        out = S.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_snapshots", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "PIT 시가총액·상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_marketcap_snapshots", S, source="pykrx")
    return S


def fetch_dart_share_counts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """★2순위 겸 Q축 필수 입력: DART '주식의 총수 현황'(stockTotqySttus.json).

    두 가지 역할을 동시에 한다:
      ① 시가총액 폴백 — 발행주식수 × 주가 (knowledge_date = 접수일자라 PIT 가 성립한다)
      ② §5.3 '주식수 증가율(3년)' 의 원천 — 이게 없으면 퀄리티 축이 소형주에서 오작동한다
    반환: corp_code · bsns_year · reprt_code · shares_issued · shares_treasury ·
          period_end · knowledge_date
    """
    cols = ["corp_code", "bsns_year", "reprt_code", "shares_issued", "shares_treasury",
            "period_end", "knowledge_date"]
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 주식총수(주식수 증가율 Q축)를 받을 수 없습니다. "
                 "해당 지표는 결측 처리되고 Q축은 가용 지표 평균으로 축소됩니다(0으로 채우지 않음).")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_share_counts", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"캐시에서 DART 주식총수 {len(cached):,}행 재사용")

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    jobs = [(str(c), int(y), r) for y in sorted(years, reverse=True)
            for c in corp_codes for r in reprts
            if (str(c), int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, y, r = job
        js = dart_api("stockTotqySttus.json",
                      {"corp_code": corp, "bsns_year": str(y), "reprt_code": r})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        num = lambda s: pd.to_numeric(
            pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
        # se(구분) 가 '합계' 인 행이 발행주식 총수. 종류주식별 행을 다 더하면 이중계상이 난다.
        se = d["se"].astype(str).str.replace(r"\s+", "", regex=True) if "se" in d.columns else pd.Series([""] * len(d))
        tot = d[se.str.contains("합계|총계", na=False)]
        src = tot if len(tot) else d
        issued = float(num(src.get("istc_totqy", pd.Series(dtype=object))).sum(skipna=True)) \
            if "istc_totqy" in src.columns else np.nan
        tre = float(num(src.get("tesstk_co", pd.Series(dtype=object))).sum(skipna=True)) \
            if "tesstk_co" in src.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        if not np.isfinite(issued) or issued <= 0:
            return None
        return {"corp_code": corp, "bsns_year": int(y), "reprt_code": str(r),
                "shares_issued": issued, "shares_treasury": tre, "rcept_no": rn}

    got = []
    if jobs:
        LOG.info(f"DART 주식총수 신규 수집 대상 {len(jobs):,}건 "
                 f"(남은 호출량: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 10),
                                  desc="DART 주식총수") if r]

    frames = [cached] if cached is not None and len(cached) else []
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    W = pd.concat(frames, ignore_index=True)
    W = W.drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
    if "rcept_no" not in W.columns:
        W["rcept_no"] = ""
    W["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12, 31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12, 31))[1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [dart_knowledge_date(rn, str(r), int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]
    if got:
        VAULT.put_table("dart_share_counts", W, scope="shared", domain="dart",
                        source="opendart stockTotqySttus")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 주식총수 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(시총 폴백 + 주식수 증가율 Q축 원천)")
    PIPE.io("OUT", "DRIVE", "dart_share_counts", W, source="opendart stockTotqySttus")
    return downcast_q(W)


def build_cap_panel(cal: pd.DataFrame, px_daily: pd.DataFrame, snaps: pd.DataFrame,
                    shares_dart: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """리밸런싱 시점별 PIT 시가총액. 3단 폴백을 쓰고 어느 경로가 쓰였는지 행마다 기록한다.

      ① KRX 스냅샷의 그 시점 시총                          (최우선 — 정의상 PIT)
      ② DART 발행주식수(as-of, 접수일 기준) × 신호일 종가   (PIT 성립)
      ③ 마지막으로 관측된 주식수 이월 × 신호일 종가         (근사 — 감사표에 표시)

    ★ ①만 쓰면 폐지 종목·비상장 이력 구간이 통째로 빠져 생존자편향이 되고,
      ③만 쓰면 증자·감자가 반영되지 않아 시총이 조용히 틀어진다. 셋을 순서대로 쓴다.
    """
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values(["date", "code"], kind="stable")

    sig = cal[["rebal", "signal_date"]].copy()
    # 신호일 종가 (그 날 거래가 없으면 직전 거래일 종가로 backward as-of)
    L = (sig.assign(_k=1).merge(pd.DataFrame({"code": sorted(px["code"].unique()), "_k": 1}),
                                on="_k").drop(columns="_k"))
    L = L.sort_values("signal_date", kind="stable")
    R = px.rename(columns={"date": "px_date"}).sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="signal_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=20))
    M = M.dropna(subset=["close"])
    M["src_cap"] = ""
    M["mktcap"] = np.nan
    M["shares"] = np.nan

    # ① KRX 스냅샷 — signal_date 이하의 가장 최근 스냅샷 (미래 스냅샷 사용 금지)
    if snaps is not None and len(snaps):
        S = snaps.copy()
        S["snap_date"] = as_ts_series(S["snap_date"])
        S = S.dropna(subset=["code", "snap_date"]).sort_values("snap_date", kind="stable")
        M = M.sort_values("signal_date", kind="stable")
        M = pd.merge_asof(M, S.rename(columns={"mktcap": "cap_krx", "shares": "sh_krx"}),
                          left_on="signal_date", right_on="snap_date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=100))
        hit = M["cap_krx"].notna() & (M["cap_krx"] > 0)
        M.loc[hit, "mktcap"] = M.loc[hit, "cap_krx"]
        M.loc[hit, "shares"] = M.loc[hit, "sh_krx"]
        M.loc[hit, "src_cap"] = "krx_snapshot"

    # ② DART 발행주식수 × 신호일 종가
    c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
              .set_index("code")["corp_code"].astype(str).to_dict()) if "corp_code" in sec.columns else {}
    M["corp_code"] = M["code"].map(c2c)
    if shares_dart is not None and len(shares_dart):
        D = shares_dart[["corp_code", "knowledge_date", "shares_issued"]].copy()
        D["knowledge_date"] = as_ts_series(D["knowledge_date"])
        D = (D.dropna(subset=["corp_code", "knowledge_date", "shares_issued"])
              .sort_values("knowledge_date", kind="stable"))
        base = M.copy()
        base["_ord"] = np.arange(len(base))
        okm = base["corp_code"].notna() & base["signal_date"].notna()
        if okm.any():
            Lp = base[okm].sort_values("signal_date", kind="stable").copy()
            Lp["corp_code"] = Lp["corp_code"].astype(str)
            D["corp_code"] = D["corp_code"].astype(str)
            J = pd.merge_asof(Lp, D, left_on="signal_date", right_on="knowledge_date",
                              by="corp_code", direction="backward")
            add = J.set_index("_ord")[["shares_issued"]]
            base = base.set_index("_ord").join(add, how="left").sort_index().reset_index(drop=True)
            M = base
        else:
            M["shares_issued"] = np.nan
    else:
        M["shares_issued"] = np.nan

    need = M["mktcap"].isna() & M["shares_issued"].notna() & (M["shares_issued"] > 0)
    M.loc[need, "mktcap"] = M.loc[need, "shares_issued"] * M.loc[need, "close"]
    M.loc[need, "shares"] = M.loc[need, "shares_issued"]
    M.loc[need, "src_cap"] = "dart_shares_x_close"

    # ③ 마지막 관측 주식수 이월 × 종가
    M = M.sort_values(["code", "signal_date"], kind="stable")
    carry = M.groupby("code", observed=True)["shares"].ffill()
    need2 = M["mktcap"].isna() & carry.notna() & (carry > 0)
    M.loc[need2, "mktcap"] = carry[need2] * M.loc[need2, "close"]
    M.loc[need2, "shares"] = carry[need2]
    M.loc[need2, "src_cap"] = "carried_shares_x_close"

    out = M[["code", "rebal", "signal_date", "close", "mktcap", "shares", "src_cap"]].copy()
    out = out[out["mktcap"].notna() & (out["mktcap"] > 0)]
    cnt = out["src_cap"].value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/max(len(out),1):.1f}%"] for k, v in cnt.items()],
              ["시총 산출 경로", "행수", "비중"], ["l", "r", "r"],
              title="PIT 시가총액 소스 감사 (①KRX스냅샷 ②DART주식수×종가 ③주식수이월×종가)")
    if cnt.get("carried_shares_x_close", 0) > 0.35 * max(len(out), 1):
        LOG.warn("시총의 35% 이상이 '주식수 이월' 근사입니다. 증자·감자가 반영되지 않으므로 "
                 "그만큼 시총 랭크가 부정확합니다. pykrx 인증(KRX ID/PW) 또는 DART_API_KEY 를 "
                 "넣으면 크게 개선됩니다.")
    PIPE.io("OUT", "MEM", "cap_panel", out)
    return downcast_q(out)


def build_adtv_panel(cal: pd.DataFrame, px_daily: pd.DataFrame,
                     window: int = ADTV_WINDOW_DAYS) -> pd.DataFrame:
    """직전 `window` 거래일 평균 거래대금(§3.2). 종목별 파이썬 루프 없이 한 번에 계산한다."""
    px = px_daily[["code", "date", "amount", "close", "high", "low"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"]).sort_values(["code", "date"], kind="stable")
    g = px.groupby("code", observed=True)
    px["adtv"] = g["amount"].transform(lambda s: s.rolling(window, min_periods=max(10, window // 3)).mean())

    # ── 실측 호가스프레드 추정: Corwin-Schultz(2012) 고가/저가 추정량 ─────────────────────
    #  §8.1 은 '실측 호가스프레드 기반 슬리피지'를 요구한다. 과거 호가(bid/ask) 시계열은
    #  공개 경로로 확보되지 않으므로, 고가·저가만으로 스프레드를 복원하는 CS 추정량을 쓴다.
    #  한계: 변동성이 큰 초소형주에서 상향 편의가 있고 음수 추정치가 자주 나온다(0 으로 절단).
    #  대안(Amihud)은 스프레드가 아니라 충격계수라 §8.1 의 요구와 맞지 않는다.
    _K = 3.0 - 2.0 * math.sqrt(2.0)
    with np.errstate(all="ignore"):
        hi_ = px["high"].where(px["high"] > 0)
        lo_ = px["low"].where(px["low"] > 0)
        hl = np.log(hi_ / lo_)
        hl_n = g["high"].shift(-1)
        lo_n = g["low"].shift(-1)
        hl2 = np.log(hl_n.where(hl_n > 0) / lo_n.where(lo_n > 0))
        beta = hl ** 2 + hl2 ** 2
        h2 = pd.concat([hi_, hl_n.where(hl_n > 0)], axis=1).max(axis=1)
        l2 = pd.concat([lo_, lo_n.where(lo_n > 0)], axis=1).min(axis=1)
        gam = np.log(h2 / l2) ** 2
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _K - np.sqrt(gam / _K)
        s_cs = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    px["_cs"] = pd.Series(s_cs, index=px.index).replace([np.inf, -np.inf], np.nan).clip(lower=0.0)
    px["cs_spread"] = (px.groupby("code", observed=True)["_cs"]
                         .transform(lambda s: s.rolling(window, min_periods=max(10, window // 3)).mean()))
    px["ret1d"] = g["close"].pct_change()
    px["vol_d"] = px.groupby("code", observed=True)["ret1d"].transform(
        lambda s: s.rolling(INVVOL_WINDOW_DAYS, min_periods=max(20, INVVOL_WINDOW_DAYS // 3)).std())

    keep = px[["code", "date", "adtv", "cs_spread", "vol_d"]].dropna(subset=["date"])
    sig = cal[["rebal", "signal_date"]].drop_duplicates().sort_values("signal_date", kind="stable")
    L = (sig.assign(_k=1).merge(pd.DataFrame({"code": sorted(keep["code"].unique()), "_k": 1}),
                                on="_k").drop(columns="_k")).sort_values("signal_date", kind="stable")
    R = keep.rename(columns={"date": "px_date"}).sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="signal_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=20))
    out = M[["code", "rebal", "adtv", "cs_spread", "vol_d"]].dropna(subset=["adtv"])
    PIPE.io("OUT", "MEM", "adtv_panel", out)
    return downcast_q(out)


# ── U-1000 ──────────────────────────────────────────────────────────────────────────────────
#  랭크 순서 정책. False = 제외·유동성 게이트를 먼저 통과시킨 뒤 그 안에서 하위 1000.
#  True 로 두면 '전 종목 중 하위 1000'을 먼저 뽑고 그 안에서 게이트를 적용해 N 이 크게 줄어든다.
#  §3 은 세 조건을 유니버스의 구성요건으로 나란히 서술하므로 False 가 자연스러운 해석이며,
#  두 해석의 결과 종목수를 모두 로그에 남겨 판단 근거를 남긴다.
U1000_RANK_BEFORE_FILTER = False


def build_universe_grid(uni: "Universe", cal: pd.DataFrame, cap: pd.DataFrame,
                        adtv: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """전 종목 × 전 리밸런싱 격자. U-1000 선정 '이전' 단계다.

    ★ 왜 격자를 먼저 만드는가: 완전자본잠식 판정에는 PIT 재무가 필요한데, 재무를 U-1000
      선정 뒤에 붙이면 '잠식 종목을 U-1000 에 넣은 채로' 랭크가 끝나 버린다. 순서를 뒤집으면
      재무를 두 번 붙여야 하고 두 번째가 첫 번째와 미세하게 달라질 여지가 생긴다.
      격자를 먼저 만들고 → 재무 as-of 결합 → 게이트 적용 순서면 결합이 정확히 한 번이다.
    """
    names = sec.set_index("code")["name"].astype(str).to_dict() if len(sec) else {}
    mkts = sec.set_index("code")["market"].astype(str).to_dict() if len(sec) else {}
    sects = sec.set_index("code")["industry"].astype(str).to_dict() if len(sec) else {}
    struct = {c: classify_exclusion(c, names.get(c, "")) for c in sec["code"]} if len(sec) else {}
    n_struct = sum(1 for v in struct.values() if v)
    if n_struct:
        by = Counter(v for v in struct.values() if v)
        LOG.info(f"구조적 제외 종목 {n_struct:,}건 (시점 불변) — " +
                 ", ".join(f"{k} {v:,}" for k, v in by.most_common()))

    parts = []
    for r in cal.itertuples(index=False):
        codes = uni.at(r.signal_date)      # ★ 신호일 기준 상장 종목 (폐지 반영 · 시즈닝 적용)
        if not codes:
            continue
        d = pd.DataFrame({"code": codes})
        d["rebal"], d["signal_date"], d["exec_date"] = r.rebal, r.signal_date, r.exec_date
        parts.append(d)
    if not parts:
        raise RuntimeError("유니버스 격자가 비었습니다 — 상장일·폐지일 정보를 확인하세요.")
    G = pd.concat(parts, ignore_index=True)
    G["excl_struct"] = G["code"].map(lambda c: struct.get(c, "")).fillna("")
    G["sector"] = G["code"].map(sects).fillna("미분류").replace("", "미분류")
    G["market"] = G["code"].map(mkts).fillna("OTHER")

    if cap is not None and len(cap):
        G = G.merge(cap[["code", "rebal", "mktcap", "shares", "close", "src_cap"]],
                    on=["code", "rebal"], how="left")
    else:
        for c in ("mktcap", "shares", "close", "src_cap"):
            G[c] = np.nan
    if adtv is not None and len(adtv):
        G = G.merge(adtv[["code", "rebal", "adtv", "cs_spread", "vol_d"]],
                    on=["code", "rebal"], how="left")
    else:
        for c in ("adtv", "cs_spread", "vol_d"):
            G[c] = np.nan
    assert_no_dup_cols(G, "universe_grid")
    LOG.ok(f"유니버스 격자 {len(G):,}행 ({G['code'].nunique():,}종목 × {G['rebal'].nunique()}분기) · "
           f"시총 보유 {100*G['mktcap'].notna().mean():.1f}% · "
           f"거래대금 보유 {100*G['adtv'].notna().mean():.1f}%")
    PIPE.io("OUT", "MEM", "universe_grid", G)
    return downcast_q(G)


def select_u1000(G: pd.DataFrame) -> pd.DataFrame:
    """격자 → U-1000. 각 게이트의 탈락 수를 전부 기록한다(§3 감쇠 감사).

    입력 G 에는 이미 PIT 재무(equity 등)가 결합되어 있어야 한다.
    """
    d = G.copy()
    d["liq_ok"] = d["adtv"].notna() & (d["adtv"] >= MIN_ADTV_KRW)
    eq = col(d, "equity")
    # ★ 자기자본을 '모르는' 것과 '음수인' 것은 다르다. 모르는 것을 잠식으로 처리하면
    #   재무 결측이 많은 초소형주가 통째로 사라져 그대로 선택편향이 된다.
    d["erosion"] = eq.notna() & (eq <= 0)
    d["elig"] = (d["excl_struct"] == "") & d["mktcap"].notna() & d["liq_ok"] & ~d["erosion"]

    if U1000_RANK_BEFORE_FILTER:
        pre_rank = d[d["mktcap"].notna()].groupby("rebal", observed=True)["mktcap"] \
                    .rank(method="first", ascending=True)
        d["_prerank"] = pre_rank.reindex(d.index)
        d["in_u1000"] = (d["_prerank"] <= U1000_N) & d["elig"]
    else:
        r = d.where(d["elig"]).groupby("rebal", observed=True)["mktcap"] \
              .rank(method="first", ascending=True)
        d["in_u1000"] = d["elig"] & (r <= U1000_N)

    audit = []
    for t, g in d.groupby("rebal", observed=True):
        n_cap_ok = g[g["mktcap"].notna()]
        alt_rank = n_cap_ok["mktcap"].rank(method="first", ascending=True)
        alt = n_cap_ok[alt_rank <= U1000_N]
        audit.append({
            "rebal": t, "전체상장": len(g),
            "구조제외후": int((g["excl_struct"] == "").sum()),
            "시총보유": int(g["mktcap"].notna().sum()),
            "유동성통과": int(g["liq_ok"].sum()),
            "자본잠식제외": int(g["erosion"].sum()),
            "적격": int(g["elig"].sum()),
            "U1000": int(g["in_u1000"].sum()),
            "대안해석": int(alt["elig"].sum()) if len(alt) else 0})

    U = d[d["in_u1000"]].drop(columns=[c for c in ("_prerank",) if c in d.columns]).copy()
    if U.empty:
        raise RuntimeError("U-1000 이 전 시점에서 비었습니다. 위 감쇠 감사에서 어느 게이트가 "
                           "원인인지 확인하세요(대개 시총 결측 또는 유동성 하한).")
    Aud = pd.DataFrame(audit).sort_values("rebal")
    LOG.table([[f"{r.rebal:%Y-%m}", f"{r.전체상장:,}", f"{r.구조제외후:,}", f"{r.시총보유:,}",
                f"{r.유동성통과:,}", f"{r.자본잠식제외:,}", f"{r.적격:,}", f"{r.U1000:,}"]
               for r in Aud.tail(12).itertuples(index=False)],
              ["리밸런싱", "전체상장", "구조제외후", "시총보유", "유동성통과", "자본잠식", "적격", "U-1000"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title="U-1000 감쇠 감사 (최근 12분기) — 어느 게이트에서 표본이 줄어드는지")
    LOG.info(f"U-1000 평균 {Aud['U1000'].mean():,.0f}종목 "
             f"(적격 평균 {Aud['적격'].mean():,.0f} / 전체상장 평균 {Aud['전체상장'].mean():,.0f}) · "
             f"랭크순서 해석 대안값 평균 {Aud['대안해석'].mean():,.0f}종목")
    if Aud["U1000"].mean() < U1000_N * 0.5:
        LOG.warn(f"U-1000 이 목표 {U1000_N} 의 절반에 못 미칩니다. 위 감쇠 감사표에서 어느 게이트가 "
                 f"원인인지 먼저 확인하세요(대개 시총 결측 또는 유동성 하한).")

    LOG.warn("PIT 관리종목·투자주의환기종목·거래정지 이력은 공개 API 로 소급 조회가 불가능합니다. "
             "현재 시점 명단을 과거에 적용하면 그 자체가 미래누수이므로 적용하지 않았습니다. "
             "대신 PIT 로 확인 가능한 완전자본잠식·4분기연속영업적자·감사의견 강조사항을 "
             "3-A 규칙(§7.2)에서 배제 사유로 사용합니다 — 이는 근사이며 동일하지 않습니다.")
    PIPE.note("PIT 관리종목 이력 미적용(소급 불가) — 3-A 재무기준으로 근사")
    PIPE.io("OUT", "MEM", "U1000", U)
    return downcast_q(U)


def build_sector_cells(P: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """§5.2/5.3 '섹터 중립' 의 셀. cell = (리밸런싱일, 섹터).
    표본이 부족한 섹터는 상위 단위 → 전체 순으로 폴백하고 그 사실을 로깅한다
    (폴백하지 않으면 소형 섹터의 z-score 가 통째로 NaN 이 되어 조용히 사라진다)."""
    p = P.copy()
    p["sector"] = p["sector"].astype(str).fillna("미분류").replace("", "미분류")
    p["sector_l1"] = p["sector"].str.slice(0, 4)
    ym = p["rebal"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["sector"]
    p["cell_l2"] = ym + "|" + p["sector_l1"]
    p["cell_l3"] = ym + "|ALL"
    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    if small.any():
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"섹터 셀 폴백: 1차 {int(small.sum()):,}행(섹터 상위단위) / "
                 f"2차 {int(still.sum()):,}행(전체). 표본 부족 셀을 NaN 으로 버리지 않습니다.")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    return p
