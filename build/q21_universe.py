

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
# ★★ 이름 규칙은 실존 소형주를 영구 삭제할 수 있다 — 경계를 반드시 붙인다 ★★
#   예전 `우(?:B|C)?$` 는 '연우'·'미래에셋대우' 처럼 '…우' 로 끝나는 보통주를 전부 우선주로
#   판정했고, `파워|마이다스|FOCUS|TREX` 는 접미 경계가 없어 '파워로직스'·'파워넷' 을
#   ETF 로 판정했다. 셋 다 정확히 §3.1 이 겨냥하는 하위 1000 구간 종목이다. 시점불변
#   삭제라 전 리밸런싱·전 실험에서 동일하게 빠지는 재현 가능한 편향이 된다.
#   → 우선주 이름 규칙은 '숫자+우' / '우B' / '우선주' 처럼 우선주에서만 나타나는 형태로
#     좁히고, 단독 '…우' 는 코드 6번째 자리 규칙에만 맡긴다(그쪽이 정확하다).
_PREF_NAME_RE = re.compile(r"\d+우(?:B|C)?$|[가-힣A-Za-z]우(?:B|C)$|우선주")
_SPAC_RE = re.compile(r"스팩|기업인수목적")
_REIT_RE = re.compile(r"리츠|위탁관리부동산투자|기업구조조정부동산투자|부동산투자회사")
# ETF/ETN 브랜드 접두는 뒤에 공백/숫자/영문 경계를 요구한다. '파워'·'마이다스'·'FOCUS'·
# 'TREX' 는 실존 사업회사 이름의 접두이기도 하므로 목록에서 뺀다(§3.3 에 없는 확장이기도 하다).
_FUND_RE = re.compile(r"^(KODEX|TIGER|KBSTAR|ARIRANG|KINDEX|HANARO|KOSEF|SOL|ACE|PLUS|RISE|"
                      r"미래에셋TIGER)(?=[\s\d]|$)|ETN$|ETF$|레버리지$|인버스$|선물\s*ETN")

# 구조적 제외로 걸러진 종목을 사후 검증할 수 있도록 명단을 남긴다(개수만 찍으면 확인 불가).
EXCLUSION_AUDIT: Dict[str, str] = {}


def is_preferred(code: str, name: str = "") -> bool:
    c = str(code or "")
    if len(c) == 6 and c[5] not in ("0",):
        # 신형 영숫자 코드는 6번째가 0/K/L/M/N 이고 0 만 보통주다. 구형은 0 이 보통주.
        return True
    # ★ 코드가 보통주(6번째='0')로 확정된 종목은 이름 규칙을 적용하지 않는다.
    #   코드 규칙이 이름 규칙보다 정확하며, 이름 규칙의 오탐은 전부 이 경로에서 나왔다.
    if len(c) == 6 and c[5] == "0":
        return bool(re.search(r"우선주$", str(name or "")))
    return bool(_PREF_NAME_RE.search(str(name or "")))


def classify_exclusion(code: str, name: str) -> str:
    """이름·코드만으로 판별 가능한 구조적 제외 사유. 없으면 빈 문자열."""
    nm = str(name or "").strip()
    why = ""
    if is_preferred(code, nm):
        why = "우선주"
    elif _SPAC_RE.search(nm):
        why = "스팩"
    elif _REIT_RE.search(nm):
        why = "리츠"
    elif _FUND_RE.search(nm):
        why = "ETF/ETN"
    if why:
        EXCLUSION_AUDIT[f"{code} {nm}"] = why
    return why


# ── 거래일 캘린더 / 리밸런싱 격자 ────────────────────────────────────────────────────────────
def fetch_trading_calendar(start: str, end: str) -> np.ndarray:
    """거래일 격자를 '지수 1종목' 으로 만든다. 전 종목 일봉이 필요 없다.

    ★★ 왜 필요한가 ★★
      예전 순서는 [전 종목 일봉 수집] → [거래일 확정] → [리밸 캘린더] → [시총 스냅샷] 이었다.
      즉 '하위 1000 종목이 누구인지' 를 알기도 전에 5,000종목이 넘는 일봉을 전부 받았다.
      시총 스냅샷은 날짜당 1~2호출로 전 종목 시총을 주므로, 순서만 뒤집으면 후보를
      먼저 확정하고 그 종목만 받을 수 있다. 그 순서 반전을 막고 있던 것이 이 순환 의존
      (캘린더 ← 일봉) 이었고, 지수 하나면 끊어진다.
    """
    lo = (as_ts(start) - pd.DateOffset(months=18)).strftime("%Y-%m-%d")
    hi = as_ts(end).strftime("%Y-%m-%d")
    for nm, fn in (("pykrx-index", lambda: (pykrx_stock.get_index_ohlcv(
                        lo.replace("-", ""), hi.replace("-", ""), "1001")
                        if pykrx_stock is not None else None)),
                   ("fdr-KS11", lambda: (fdr.DataReader("KS11", lo, hi)
                                         if fdr is not None else None))):
        try:
            d = fn()
        except Exception as e:                                      # noqa
            LOG.debug(f"거래일 격자 {nm} 실패({type(e).__name__})")
            continue
        if d is None or not len(d):
            continue
        idx = pd.DatetimeIndex(pd.to_datetime(d.index)).normalize()
        idx = idx[(idx >= as_ts(lo)) & (idx <= as_ts(hi))]
        if len(idx) > 200:
            LOG.ok(f"거래일 격자 {len(idx):,}일 확보 ({nm}, 호출 1회) — "
                   f"전 종목 일봉 없이 캘린더를 만든다")
            return np.sort(pd.unique(idx.values))
    LOG.warn("지수로 거래일 격자를 만들지 못했습니다 — 영업일(Mon-Fri) 격자로 폴백합니다. "
             "공휴일이 거래일로 잡히면 signal/exec 이 하루씩 어긋날 수 있으니 로그를 확인하세요.")
    return np.sort(pd.bdate_range(lo, hi).values)


def select_universe_candidates(caps: pd.DataFrame, signal_dates: Sequence[Any],
                               n_target: int = U1000_N,
                               buffer_mult: float = CANDIDATE_BUFFER_MULT) -> Tuple[List[str], dict]:
    """일봉을 받을 '후보' 종목만 고른다 = 각 신호일 시총 하위 K 의 합집합.

    ★ K = n_target × buffer_mult. 버퍼가 필요한 이유: §3.2/§3.3 게이트(유동성·구조제외·
      자본잠식)가 하위 종목을 걸러내므로, 적격 하위 1000 은 전체 하위 1000 보다 아래로
      더 내려간다. 버퍼가 모자랐는지는 build_u1000 이 실현 랭크로 검증해 보고한다.
    """
    if caps is None or not len(caps):
        return [], {"reason": "시총 스냅샷 없음"}
    c = caps.copy()
    c["snap_date"] = as_ts_series(c["snap_date"])
    c["mktcap"] = pd.to_numeric(c["mktcap"], errors="coerce")
    c = c.dropna(subset=["code", "snap_date", "mktcap"])
    c = c[c["mktcap"] > 0]
    k = int(max(n_target, round(n_target * float(buffer_mult))))
    want = {as_ts(d) for d in signal_dates}
    picked: set = set()
    per_date = []
    for d, g in c.groupby("snap_date", observed=True):
        if as_ts(d) not in want:
            continue
        gg = g.nsmallest(min(k, len(g)), "mktcap")
        picked.update(gg["code"].astype(str).tolist())
        per_date.append(len(g))
    info = {"K": k, "n_dates": len(per_date), "n_candidates": len(picked),
            "n_listed_avg": float(np.mean(per_date)) if per_date else float("nan")}
    return sorted(picked), info


def qvf_trading_days(px_daily: pd.DataFrame) -> np.ndarray:
    """전 종목 일봉에서 유도한 실제 거래일 배열. 공휴일 테이블을 따로 두지 않는다
    (테이블을 두면 그 테이블이 틀렸을 때 조용히 하루씩 밀린다)."""
    if px_daily is None or not len(px_daily):
        return np.array([], dtype="datetime64[ns]")
    d = as_ts_series(px_daily["date"]).dropna()
    return np.sort(pd.unique(d.values))


def qvf_rebal_calendar_from_days(start: str, end: str, shift_days: int = 0) -> pd.DataFrame:
    """이미 확정된 QVF_TRADING_DAYS 로 캘린더를 만든다(일봉 패널 없이)."""
    return qvf_rebal_calendar(pd.DataFrame({"date": pd.Series(QVF_TRADING_DAYS)}),
                              start, end, shift_days=shift_days)


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

    # ★★ rolling(60) 은 '시장 60거래일'이 아니라 '그 종목이 가진 60개 행' 이다 ★★
    #   거래정지·소스 누락으로 행이 빠지면 창이 조용히 늘어나고, 분모에서 무거래일이 빠져
    #   유동성이 과대평가된다. 과대 배수는 정확히 60/실거래일수다 — 20일만 거래된 종목은
    #   ADTV 가 3배로 잡혀 §3.2 의 1억 게이트를 통과한다. 즉 §3.3 이 빼라는 바로 그
    #   거래정지·초박형 종목이 U-1000 에 들어오고, 백테스트는 실제로 살 수 없는 종목을 산다.
    #   pykrx 는 정지일을 amount=0 행으로 주지만 naver/yfinance 폴백은 행 자체를 생략하므로
    #   §3.2 의 의미가 소스별로 달라진다.
    #   → 시장 거래일 격자에 reindex 하고 무거래일 거래대금을 0 으로 채운 뒤 rolling 한다.
    _tds = pd.DatetimeIndex(sorted(pd.unique(px["date"])), name="date")
    _amt = (px.pivot_table(index="date", columns="code", values="amount", aggfunc="last")
              .reindex(_tds))
    _amt.columns.name = "code"
    # 첫 상장 전 구간까지 0 으로 채우면 신규 상장주의 ADTV 가 부당하게 낮아진다.
    # 각 종목의 '최초 관측일 이후'만 0 으로 채운다(그 이전은 결측 유지).
    _seen = _amt.notna().cumsum() > 0
    _amt = _amt.where(~(_seen & _amt.isna()), 0.0)
    _adtv = _amt.rolling(int(window), min_periods=int(window)).mean()
    # ★ stack(dropna=) 은 pandas 3.x 에서 ValueError 로 제거됐다(같은 저장소의 p_x_customs 가
    #   이미 그 이유로 melt 를 쓴다). 여기만 남아 있어서 pandas 3 에서는 §3.2 유동성 게이트가
    #   통째로 죽는다 — L1.PANEL1 이 시작도 못 한다. 버전 안정적인 melt 로 바꾼다(결과 동일).
    _adtv = (_adtv.reset_index().melt(id_vars="date", var_name="code", value_name="adtv")
                  .dropna(subset=["adtv"]))
    _adtv.columns = ["date", "code", "adtv"]
    _adtv["code"] = _adtv["code"].astype(str)
    px["code"] = px["code"].astype(str)
    px = px.merge(_adtv, on=["date", "code"], how="left")
    _n_tight = int(px["adtv"].isna().sum())
    LOG.debug(f"ADTV: 시장 거래일 격자 {len(_tds):,}일 · min_periods={window} "
              f"(자기 행이 아니라 시장 거래일 기준) · 창 미충족 결측 {_n_tight:,}행")

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
        # ★ CS 는 2일 추정량이다. (t, t+1) 로 잡으면 signal_date 에서 읽는 스프레드가
        #   '체결일의 고저'를 포함하게 되어 비용 모델에 1일치 미래정보가 들어간다.
        #   (t-1, t) 로 잡으면 동일한 추정량이면서 t 까지의 정보만 쓴다.
        hl_n = g["high"].shift(1)
        lo_n = g["low"].shift(1)
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
    px["ret1d"] = g["close"].pct_change(fill_method=None)
    px["vol_d"] = px.groupby("code", observed=True)["ret1d"].transform(
        lambda s: s.rolling(INVVOL_WINDOW_DAYS, min_periods=max(20, INVVOL_WINDOW_DAYS // 3)).std())

    keep = px[["code", "date", "adtv", "cs_spread", "vol_d"]].dropna(subset=["date"])
    sig = cal[["rebal", "signal_date"]].drop_duplicates().copy()
    sig["signal_date"] = as_ts_series(sig["signal_date"])       # 결합키 단위 고정(as_ts 주석)
    sig = sig.sort_values("signal_date", kind="stable")
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
        # ★ 개수만 찍으면 사후 검증이 불가능하다. 이름 규칙의 오탐(실존 소형주가 ETF/우선주로
        #   판정되는 사고)은 명단을 봐야만 잡힌다. 사유별 표본을 반드시 남긴다.
        _samp = defaultdict(list)
        for k, v in struct.items():
            if v and len(_samp[v]) < 12:
                _samp[v].append(f"{k} {names.get(k, '')}".strip())
        LOG.table([[k, f"{by[k]:,}", _trunc(", ".join(_samp[k]), 78)] for k in by],
                  ["제외 사유", "건수", "표본(최대 12)"], ["l", "r", "l"], maxw=80,
                  title="구조적 제외 명단 (§3.3) — 이름 규칙의 오탐은 명단을 봐야만 잡힌다")

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
            "대안해석": int(alt["elig"].sum()) if len(alt) else 0,
            # §3.1 문언이 두 가지로 읽히는 지점이라 두 모집단의 규모·성격 차이를 남긴다.
            "채택_시총중앙": float(g.loc[g["in_u1000"], "mktcap"].median())
                              if int(g["in_u1000"].sum()) else np.nan,
            "채택_시총상한": float(g.loc[g["in_u1000"], "mktcap"].max())
                              if int(g["in_u1000"].sum()) else np.nan,
            "대안_시총중앙": float(alt.loc[alt["elig"], "mktcap"].median())
                              if len(alt) and int(alt["elig"].sum()) else np.nan,
            "대안_시총상한": float(alt.loc[alt["elig"], "mktcap"].max())
                              if len(alt) and int(alt["elig"].sum()) else np.nan,
            "겹침": (len(set(g.loc[g["in_u1000"], "code"]) &
                         set(alt.loc[alt["elig"], "code"])) /
                     max(1, int(g["in_u1000"].sum()))) if len(alt) else np.nan})

    # ★ 후보 버퍼가 실제로 충분했는지 검증한다. 후보를 K 로 잘랐는데 적격 하위 1000 이
    #   K 밖까지 내려가야 했다면, 그만큼의 종목이 '데이터가 없어서' 빠진 것이지
    #   '규칙에 걸려서' 빠진 것이 아니다. 그건 조용한 유니버스 손실이다.
    _K = int(max(U1000_N, round(U1000_N * float(CANDIDATE_BUFFER_MULT))))
    _bind = []
    for t, g in d.groupby("rebal", observed=True):
        gm = g[g["mktcap"].notna()]
        if not len(gm) or not int(g["in_u1000"].sum()):
            continue
        r_all = gm["mktcap"].rank(method="first", ascending=True)
        r_sel = r_all[g.loc[gm.index, "in_u1000"].to_numpy()]
        if len(r_sel) and float(r_sel.max()) >= _K * 0.95:
            _bind.append((t, int(r_sel.max()), int(g["in_u1000"].sum())))
    if _bind:
        LOG.warn(f"후보 버퍼(K={_K:,})가 빠듯한 분기 {len(_bind)}회 — "
                 + ", ".join(f"{as_ts(t):%Y-%m}:최대랭크 {r:,}" for t, r, _n in _bind[:6])
                 + (" …" if len(_bind) > 6 else "")
                 + ". CANDIDATE_BUFFER_MULT 를 올려 다시 실행하면 그만큼 종목이 더 들어옵니다. "
                   "지금 결과는 '데이터가 없어 빠진 종목'이 있을 수 있다는 뜻입니다.")
    else:
        LOG.debug(f"후보 버퍼 K={_K:,} 충분 — 전 분기에서 적격 하위 {U1000_N:,} 가 K 안에 들어옴")

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
             f"(적격 평균 {Aud['적격'].mean():,.0f} / 전체상장 평균 {Aud['전체상장'].mean():,.0f})")
    # ★★ §3.1 '하위 1000종목' 은 문언상 두 가지로 읽힌다 ★★
    #   (A) 채택: §3.2/§3.3 게이트를 통과한 종목 안에서 하위 1000
    #   (B) 대안: 전 종목에서 하위 1000 을 먼저 뽑고 그 안에서 게이트
    #   둘은 모집단 자체가 다르다 — (A)가 더 크고 유동성 좋은 종목을 포함하므로 비용이
    #   낮아지고, 1차필터 선택률이 낮아져 Score1 의 분산·알파가 기계적으로 커진다.
    #   즉 §10.2 의 "1차필터 기여 = 알파 창출" 주장이 이 해석 하나에 직접 의존한다.
    #   개수 한 줄만 찍고 넘어가면 안 되므로 규모·성격 차이를 표로 남긴다.
    _fmt_eok = lambda v: "—" if not np.isfinite(v) else f"{v/1e8:,.0f}억"
    LOG.table([
        ["종목수", f"{Aud['U1000'].mean():,.0f}", f"{Aud['대안해석'].mean():,.0f}"],
        ["시총 중앙값", _fmt_eok(Aud['채택_시총중앙'].mean()), _fmt_eok(Aud['대안_시총중앙'].mean())],
        ["시총 상한", _fmt_eok(Aud['채택_시총상한'].mean()), _fmt_eok(Aud['대안_시총상한'].mean())],
        ["채택 대비 겹침률", "100.0%", f"{100*Aud['겹침'].mean():.1f}%"],
    ], ["항목", "채택: 게이트 → 하위1000", "대안: 하위1000 → 게이트"], ["l", "r", "r"],
        title="§3.1 '하위 1000' 해석 비교 (전 분기 평균) — 명세 문언이 두 갈래로 읽히는 지점")
    globals()["U1000_INTERP_AUDIT"] = {
        "n_adopted": float(Aud["U1000"].mean()), "n_alt": float(Aud["대안해석"].mean()),
        "cap_med_adopted": float(Aud["채택_시총중앙"].mean()),
        "cap_med_alt": float(Aud["대안_시총중앙"].mean()),
        "cap_max_adopted": float(Aud["채택_시총상한"].mean()),
        "cap_max_alt": float(Aud["대안_시총상한"].mean()),
        "overlap": float(Aud["겹침"].mean())}
    if np.isfinite(Aud["겹침"].mean()) and Aud["겹침"].mean() < 0.90:
        LOG.warn(f"두 해석의 겹침률이 {100*Aud['겹침'].mean():.1f}% 입니다 — 사실상 다른 "
                 f"모집단입니다. 결과를 '하위 1000 전략'이라고 부를 때 어느 해석인지 반드시 "
                 f"명시하고, 전체 재실행으로 비교하려면 U1000_RANK_BEFORE_FILTER=True 로 "
                 f"두고 한 번 더 돌리십시오(§8.4 축으로 자동 병행하지는 않습니다 — 유니버스가 "
                 f"바뀌면 패널 전체를 다시 만들어야 해서 실행시간이 두 배가 됩니다).")
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


def shares_from_cap_snapshots(snaps: Optional[pd.DataFrame],
                              sec: pd.DataFrame) -> pd.DataFrame:
    """KRX 시총 스냅샷의 '상장주식수'로 DART 주식총수 테이블과 같은 모양을 만든다.

    왜 이게 대체재가 아니라 상위 호환인가:
      · DART stockTotqySttus 는 (회사 × 연도)마다 1호출이다. 후보 2,000사 × 11년 = 22,000회로
        그것 하나가 하루 한도를 태운다. 반면 상장주식수는 시총 스냅샷 호출에 이미 실려 온다(0원).
      · DART 는 분기 공시 시차가 있지만 스냅샷은 '그 날 실제 주식수'라 정의상 PIT 이다.
      · 스냅샷 격자 = 분기 신호일이므로 share_growth3y 의 shift(12) 가 정확히 3년 전을 가리킨다.

    자기주식(shares_treasury)만은 KRX 가 주지 않으므로 결측으로 둔다 — 유동시총이 자기주식
    미차감 근사가 된다는 뜻이고, 그 사실은 호출부가 로그로 밝힌다.
    """
    cols = ["corp_code", "knowledge_date", "shares_issued", "shares_treasury", "period_end"]
    if snaps is None or not len(snaps) or sec is None or not len(sec):
        return pd.DataFrame(columns=cols)
    m = (sec[["code", "corp_code"]].dropna().astype(str).drop_duplicates("code"))
    S = snaps.copy()
    S["code"] = S["code"].astype(str)
    S = S.merge(m, on="code", how="inner")
    S["knowledge_date"] = as_ts_series(S["snap_date"])
    S = S.dropna(subset=["corp_code", "knowledge_date", "shares"])
    S = S[pd.to_numeric(S["shares"], errors="coerce") > 0]
    if not len(S):
        return pd.DataFrame(columns=cols)
    S["shares_issued"] = pd.to_numeric(S["shares"], errors="coerce")
    S["shares_treasury"] = np.nan          # KRX 미제공 — 0 으로 채우면 자기주식 0 이라 우기는 셈
    S["period_end"] = S["knowledge_date"]
    S = (S.sort_values(["corp_code", "knowledge_date"], kind="stable")
          .drop_duplicates(["corp_code", "knowledge_date"], keep="last"))
    return S[cols].reset_index(drop=True)


def candidate_year_span(snaps: Optional[pd.DataFrame], sec: pd.DataFrame,
                        signal_dates: Sequence[pd.Timestamp], n_target: int,
                        buffer_mult: float, lookback_years: int = 3) -> Dict[str, set]:
    """corp_code → 실제로 재무가 필요한 회계연도 집합.

    ★ 왜 필요한가: 예전에는 (후보 전체) × (전 기간 연도)의 데카르트 곱을 요청했다.
      2,980사 × 15년 × 4보고서 = 178,800회 — 회사별 API 로는 9일이 걸린다. 그런데 어떤
      회사가 2018~2021 에만 시총 하위권이었다면 2012년이나 2026년 재무는 어디에도 쓰이지
      않는다. 그 회사가 '후보였던 기간'과 3년 소급(roic_std3y·share_growth3y·TTM)만 받는다.

    반환: {corp_code: {연도, ...}}
    """
    out: Dict[str, set] = {}
    if snaps is None or not len(snaps) or sec is None or not len(sec):
        return out
    m = sec[["code", "corp_code"]].dropna().astype(str).drop_duplicates("code")
    c2corp = dict(zip(m["code"], m["corp_code"]))
    S = snaps.copy()
    S["code"] = S["code"].astype(str)
    S["snap_date"] = as_ts_series(S["snap_date"])
    S["mktcap"] = pd.to_numeric(S["mktcap"], errors="coerce")
    S = S.dropna(subset=["code", "snap_date", "mktcap"])
    K = int(max(n_target, round(n_target * float(buffer_mult))))
    span: Dict[str, List[int]] = {}
    for d in sorted({as_ts(x) for x in signal_dates}):
        g = S[S["snap_date"] == d]
        if not len(g):
            # 그 날짜 스냅샷이 없으면 가장 가까운 과거 스냅샷을 쓴다(없으면 건너뜀).
            prev = S[S["snap_date"] <= d]
            if not len(prev):
                continue
            d2 = prev["snap_date"].max()
            g = S[S["snap_date"] == d2]
        sel = g.nsmallest(K, "mktcap")["code"]
        y = int(as_ts(d).year)
        for c in sel:
            cc = c2corp.get(str(c))
            if not cc:
                continue
            r = span.get(cc)
            if r is None:
                span[cc] = [y, y]
            else:
                if y < r[0]:
                    r[0] = y
                if y > r[1]:
                    r[1] = y
    for cc, (y0, y1) in span.items():
        out[cc] = set(range(y0 - int(lookback_years), y1 + 1))
    return out


# ── 시가총액 폴백: pykrx 없이도 PIT 시총을 만든다 ──────────────────────────────────────────
def _normalize_shares_table(d: Optional[pd.DataFrame], name: str) -> Optional[pd.DataFrame]:
    """다른 전략/이전 버전이 남긴 주식수 테이블을 이 코드가 쓰는 스키마로 맞춘다.

    ★★ 공용 캐시는 전략 간에 공유된다 — 이름이 같아도 컬럼은 다를 수 있다 ★★
      실측: D:/tcd_cache 의 naver_shares_snapshot(4,020행)에는 'shares_now' 가 없어서
      dropna(subset=["code","shares_now"]) 가 KeyError 로 죽었다. 캐시를 '있다/없다'로만
      보고 스키마를 확인하지 않은 것이 원인이다. 재사용하려면 관대하게 읽어야 한다.
    ★ 맞출 수 없으면 None 을 돌려 신규 수집으로 넘긴다. 남의 캐시는 절대 건드리지 않는다.
    """
    if d is None or not len(d):
        return None
    d = d.copy()
    low = {str(c).strip().lower(): c for c in d.columns}
    c_code = next((low[k] for k in ("code", "종목코드", "ticker", "symbol", "티커") if k in low), None)
    c_sh = next((low[k] for k in ("shares_now", "shares", "상장주식수", "listed_shares",
                                  "shares_issued", "listed_stock_cnt", "발행주식수") if k in low), None)
    if c_code is None or c_sh is None:
        LOG.warn(f"{name} 캐시에 필요한 컬럼이 없어(가진 컬럼: {list(d.columns)[:8]}) "
                 f"재사용하지 않고 새로 수집합니다. 기존 캐시는 그대로 둡니다.")
        return None
    out = pd.DataFrame({"code": d[c_code].map(to_code6),
                        "shares_now": pd.to_numeric(d[c_sh], errors="coerce")})
    if "market" in low:
        out["market"] = d[low["market"]].astype(str)
    out = out.dropna(subset=["code", "shares_now"])
    out = out[out["shares_now"] > 0].drop_duplicates("code", keep="last").reset_index(drop=True)
    if not len(out):
        LOG.warn(f"{name} 캐시를 정규화했으나 유효행이 0 입니다 — 새로 수집합니다.")
        return None
    if c_sh != "shares_now" or c_code != "code":
        LOG.info(f"{name} 캐시 스키마를 맞췄습니다: '{c_code}'→code · '{c_sh}'→shares_now "
                 f"({len(out):,}행) — 다른 전략이 남긴 캐시를 그대로 재활용합니다.")
    return out


NAVER_SUM = "https://finance.naver.com/sise/sise_market_sum.naver"


def fetch_naver_shares() -> pd.DataFrame:
    """네이버 시가총액 페이지에서 전 종목 '상장주식수'를 받는다. 반환: code · shares_now

    ★ 왜 필요한가: 시총을 pykrx 단일 경로에 묶어 둔 것이 설계 오류였다. pykrx import 가
      깨지자(윈도우 인코딩) U-1000 자체를 만들 수 없어 실행이 통째로 멈췄다. 유니버스는
      여러 소스로 서야 한다.
    ★ 비용: 시장 2개 × 약 33페이지 = 약 66요청. 전 종목 주식수를 이 값으로 확보한다.
    ★ 한계: '현재' 주식수다. 과거 시총은 이 주식수를 과거로 이월해 종가와 곱해 근사한다
      (증자·분할이 있었으면 그만큼 오차). 그래서 cap_src 를 'naver_shares_x_close' 로
      남겨 §3 시총 소스 감사표에 그대로 드러나게 한다 — 숨기지 않는다.
    """
    cached = _normalize_shares_table(VAULT.get_table("naver_shares_snapshot", scope="shared"),
                                     "naver_shares_snapshot")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 상장주식수 {len(cached):,}종목 재사용")
        return cached
    rows: List[dict] = []
    for sosok, mkt in ((0, "KOSPI"), (1, "KOSDAQ")):
        for page in range(1, 45):
            html = http_get(NAVER_SUM, source="naver", force_enc="euc-kr", tries=2,
                            params={"sosok": sosok, "page": page,
                                    "fieldIds": "listed_stock_cnt", "menu": "market_sum"})
            if not html:
                break
            s = soup_of(html)
            if s is None:
                break
            n0 = len(rows)
            for tr in s.select("table.type_2 tr"):
                a = tr.select_one("a.tltle") or tr.select_one("td a[href*='code=']")
                if a is None:
                    continue
                m = re.search(r"code=(\d{6})", a.get("href", ""))
                if not m:
                    continue
                tds = [td.get_text(strip=True).replace(",", "") for td in tr.select("td")]
                sh = next((v for v in reversed(tds) if v.isdigit() and len(v) >= 5), None)
                if sh:
                    rows.append({"code": m.group(1), "shares_now": float(sh), "market": mkt})
            if len(rows) == n0:                 # 더 이상 종목이 없다 = 마지막 페이지
                break
    if not rows:
        LOG.warn("네이버 상장주식수를 받지 못했습니다 (차단 또는 페이지 구조 변경).")
        return pd.DataFrame(columns=["code", "shares_now", "market"])
    S = pd.DataFrame(rows).drop_duplicates("code", keep="first").reset_index(drop=True)
    VAULT.put_table("naver_shares_snapshot", S, scope="shared", domain="universe",
                    source="naver:sise_market_sum")
    PIPE.io("OUT", "DRIVE", "naver_shares_snapshot", S, source="naver")
    LOG.ok(f"네이버 상장주식수 {len(S):,}종목 확보 (요청 약 {len(S)//50 + 2}회) — "
           f"pykrx 없이도 시총 랭크를 만들 수 있습니다.")
    return S


def cap_snapshots_from_prices(px: pd.DataFrame, shares: pd.DataFrame,
                              signal_dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """주식수 × 신호일 직전 종가 = PIT 근사 시가총액. pykrx·KRX 로그인이 모두 죽어도 선다.

    종가는 이미 캐시에 있는 일봉을 그대로 쓰므로 신규 호출이 0 이다.
    """
    cols = ["code", "snap_date", "mktcap", "shares"]
    if px is None or not len(px) or shares is None or not len(shares):
        return pd.DataFrame(columns=cols)
    P = px[["code", "date", "close"]].copy()
    P["code"] = P["code"].astype(str)
    P["date"] = as_ts_series(P["date"])
    P = P.dropna(subset=["code", "date", "close"]).sort_values("date", kind="stable")
    sh = _normalize_shares_table(shares, "shares")
    if sh is None or not len(sh):
        LOG.warn("주식수 표를 이 코드가 쓰는 스키마로 맞추지 못해 시총 폴백을 건너뜁니다.")
        return pd.DataFrame(columns=cols)
    sh["code"] = sh["code"].astype(str)
    grid = (pd.DataFrame({"snap_date": sorted({as_ts(d) for d in signal_dates})})
            .merge(sh[["code"]], how="cross").sort_values("snap_date", kind="stable"))
    M = pd.merge_asof(grid, P.rename(columns={"date": "px_date"}),
                      left_on="snap_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=15))
    M = M.dropna(subset=["close"]).merge(sh[["code", "shares_now"]], on="code", how="left")
    M["mktcap"] = pd.to_numeric(M["close"], errors="coerce") * M["shares_now"]
    M["shares"] = M["shares_now"]
    M = M.dropna(subset=["mktcap"])
    LOG.ok(f"시총 폴백 산출 {len(M):,}행 ({M['code'].nunique():,}종목 × "
           f"{M['snap_date'].nunique()}시점) — 주식수 × 종가. 신규 네트워크 호출 0회.")
    LOG.warn("이 경로의 주식수는 '현재' 값을 과거로 이월한 근사입니다 — 증자·분할이 있었던 "
             "종목은 과거 시총이 과대추정됩니다. §3 시총 소스 감사표에서 비중을 확인하세요.")
    return M[cols].reset_index(drop=True)
