

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 0 — PIT 월간 유니버스 (시총 하위 N + 유동성)                                        ║
# ║                                                                                          ║
# ║  입력 : sec(종목마스터) · px_daily(일봉) · pxm(월말 패널) · Universe(상장/폐지 기반 멤버십) ║
# ║  출력 : MCAP(code,month,mcap,shares,mcap_src) · UNI(month,code,...,in_uni,liq_pass,excl)   ║
# ║  실패 : 예외를 던지지 않고 '무엇을 못 구했는지'를 감사표로 노출한 뒤 폴백 경로로 계속한다.  ║
# ║                                                                                          ║
# ║  ★ 이 전략의 성패는 "하위 1000" 경계의 PIT 정확도에 달려 있다. 현재 시총으로 과거를 자르면 ║
# ║    그 자체가 미래누수다(지금 대형주인 종목이 2016년엔 소형주였다). 그래서 시가총액은        ║
# ║    ① KRX 월말 스냅샷(pykrx, 상장주식수 포함) 을 1순위로 쓰고,                              ║
# ║    ② 실패 시 '현재 주식수 × 과거 종가' 근사로 낮추되 그 사실을 감사표와 매니페스트에 남긴다.║
# ║    ②는 유상증자·액면분할이 잦은 소형주에서 오차가 크다 — 숨기지 않고 표기한다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 명세 §5.1-3: "상장 후 6개월 미만" 제외. TCD 코어의 기본값(250거래일 ≈ 1년)보다 완화된 기준이라
# Universe 를 만들기 전에 전역을 바꿔 둔다. (Universe.__init__ 이 이 값을 읽어 시즈닝을 확정한다)
LISTING_SEASONING_DAYS = 120

MCAP_COLS = ["code", "month", "close", "mcap", "shares", "mcap_src"]
UNI_COLS = ["month", "code", "mcap", "adv20", "mcap_rank", "in_uni", "liq_pass", "excl"]

# 제외 사유 라벨 — 퍼널 표에서 그대로 쓰인다
EXCL_NONE = ""
EXCL_PREF = "우선주"
EXCL_SPAC = "스팩"
EXCL_REIT = "리츠"
EXCL_NEW = "상장6개월미만"
EXCL_HALT = "거래정지추정"
EXCL_NOMCAP = "시총결측"
EXCL_ETF = "ETF/ETN/펀드"

_PREF_NAME_RE = re.compile(r"(우[BC]?|우선주)$")
_SPAC_RE = re.compile(r"(스팩|기업인수목적)")
_REIT_RE = re.compile(r"(리츠|부동산투자회사|리얼티)")
_FUND_RE = re.compile(r"(ETN|ETF|レ|인버스|레버리지|선물|KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE )")


def ncq_ns(s) -> pd.Series:
    """어떤 시간 해상도로 들어오든 datetime64[ns] 로 통일한다.

    ★ pandas 2.x 는 해상도를 값에서 추론한다: pd.Timestamp("1990-01-01") 를 대입하면
      datetime64[s], pd.to_datetime(...) 는 datetime64[ns] 가 되기 쉽다. 두 계열이 섞이면
      merge_asof / 비교 연산이 조용히 실패하거나 엉뚱한 예외를 던진다. 경계에서 못박는다.
    """
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    try:
        return out.astype("datetime64[ns]")
    except Exception:
        return out


def ncq_is_preferred(code: str, name: str) -> bool:
    """우선주 판정. 코드 끝자리(5/7/9)와 종목명을 **둘 다** 본다.

    ★ 2024-01 종목코드 개편으로 영숫자 코드가 도입되어 '끝자리 숫자' 규칙만으로는 오탐이 난다.
      그래서 '앞 5자리가 숫자이고 6번째가 5/7/9' 인 고전 형식일 때만 코드 규칙을 적용하고,
      나머지는 종목명 규칙에 맡긴다.
    """
    c = str(code or "")
    n = str(name or "").strip()
    if _PREF_NAME_RE.search(n):
        return True
    if len(c) == 6 and c[:5].isdigit() and c[5] in ("5", "7", "9"):
        # 보통주 중에도 6번째가 0인 것이 원칙이므로 5/7/9 는 우선주 계열로 본다.
        return True
    return False


def ncq_static_exclusion(sec: pd.DataFrame) -> pd.DataFrame:
    """종목 단위 정적 제외 사유(우선주/스팩/리츠/ETF)를 한 번에 계산한다."""
    d = sec[["code", "name", "industry"]].copy() if len(sec) else \
        pd.DataFrame(columns=["code", "name", "industry"])
    if d.empty:
        d["excl_static"] = pd.Series(dtype=object)
        return d
    d["name"] = d["name"].astype(str).fillna("")
    d["industry"] = d["industry"].astype(str).fillna("")
    ex = np.full(len(d), EXCL_NONE, dtype=object)
    nm, ind, cd = d["name"].to_numpy(), d["industry"].to_numpy(), d["code"].astype(str).to_numpy()
    for i in range(len(d)):
        if _SPAC_RE.search(nm[i]):
            ex[i] = EXCL_SPAC
        elif _REIT_RE.search(nm[i]) or _REIT_RE.search(ind[i]):
            ex[i] = EXCL_REIT
        elif _FUND_RE.search(nm[i]):
            ex[i] = EXCL_ETF
        elif ncq_is_preferred(cd[i], nm[i]):
            ex[i] = EXCL_PREF
    d["excl_static"] = ex
    n_ex = int((d["excl_static"] != EXCL_NONE).sum())
    LOG.info(f"정적 제외 대상 {n_ex:,}종목 — " +
             ", ".join(f"{k}×{v:,}" for k, v in
                       Counter(d.loc[d['excl_static'] != EXCL_NONE, 'excl_static']).most_common()))
    return d[["code", "excl_static"]]


# ── 시가총액 (PIT) ──────────────────────────────────────────────────────────────────────────
def _ncq_mcap_from_pykrx(month_ends: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """(선택) KRX 월말 스냅샷 — 시가총액·상장주식수의 '그 시점 값'.

    ⚠ KRX 차단 환경에서는 호출되지 않는다(ncq_krx_enabled() 가 False). 이 함수는 **보강**이지
      의존 대상이 아니다. KRX 없이도 DART PIT 주식수 × 수정종가로 시가총액이 완성된다.
    ★ 전부 KRXG 게이트를 통해 직렬 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), JSON 대신 로그인 HTML 을 받아 대량 실패한다.
    ★ 1회 호출이 전 종목을 돌려주므로 120개월이면 120회면 끝난다. 종목별 루프 금지.
    """
    if not ncq_krx_enabled():
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    if pykrx_stock is None or not month_ends:
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    if not KRXG.warmup():
        LOG.info("KRX 세션이 없어 월말 시가총액 스냅샷을 건너뜁니다 — 근사 경로로 폴백합니다.")
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])

    rows: List[pd.DataFrame] = []
    bad_streak = 0
    for m in tqdm(list(month_ends), desc="KRX 월말 시가총액", ncols=88, leave=False):
        bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                       m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
        d = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market="ALL")
        if d is None or len(d) == 0:
            bad_streak += 1
            if bad_streak >= 5:
                LOG.warn("KRX 시가총액 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 "
                         "상태입니다. 수집을 중단하고 근사 경로로 폴백합니다(정상 폴백).")
                break
            continue
        bad_streak = 0
        t = d.reset_index()
        ren = {"티커": "code", "종가": "close", "시가총액": "mcap", "상장주식수": "shares"}
        t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
        if "code" not in t.columns:
            t = t.rename(columns={t.columns[0]: "code"})
        for c in ("close", "mcap", "shares"):
            if c not in t.columns:
                t[c] = np.nan
        t["code"] = t["code"].map(to_code6)
        t["date"] = m
        rows.append(t[["date", "code", "close", "mcap", "shares"]].dropna(subset=["code"]))
    if not rows:
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    out = pd.concat(rows, ignore_index=True)
    LOG.ok(f"KRX 월말 시가총액 스냅샷 {out['date'].nunique()}개월 × 평균 "
           f"{len(out)/max(out['date'].nunique(),1):,.0f}종목 확보 (진짜 PIT 경로)")
    return out


def ncq_month_end_close(px_daily: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 수정종가 패널 [code, month, close]. 시가총액의 '분자'."""
    if px_daily is None or len(px_daily) == 0:
        return pd.DataFrame(columns=["code", "month", "close"])
    p = px_daily[["code", "date", "close"]].dropna(subset=["date", "close"]).copy()
    p["month"] = as_ts_series(p["date"]) + pd.offsets.MonthEnd(0)
    out = (p.sort_values("date").groupby(["code", "month"], observed=True)
             .tail(1)[["code", "month", "close"]])
    return out[out["month"].isin(months)].reset_index(drop=True)


def ncq_shares_asof(px_m: pd.DataFrame, shares_hist: pd.DataFrame) -> pd.DataFrame:
    """월말 시점에 '알 수 있었던' 상장주식수를 as-of 결합한다 (C1 과 동일한 의미론).

    ★ merge_asof(direction="backward") 는 knowledge_date <= month 인 마지막 행만 붙인다.
      결산일이 아니라 **접수일자**를 knowledge_date 로 썼기 때문에, 아직 공시되지 않은
      주식수가 과거 시점으로 새어 들어오지 않는다.
    ★ by="code" 결합키가 결측이면 merge_asof 가 다루지 못하므로 유효 행만 결합하고
      나머지는 NaN 으로 되붙인다. 행을 버리면 그게 곧 생존자편향이다.
    """
    if px_m is None or px_m.empty:
        return pd.DataFrame(columns=["code", "month", "close", "shares", "shares_src"])
    L = px_m.dropna(subset=["code", "month"]).copy()
    if shares_hist is None or len(shares_hist) == 0:
        L["shares"] = np.nan
        L["shares_src"] = ""
        return L
    R = shares_hist.dropna(subset=["code", "knowledge_date"]).copy()
    # ★★ merge_asof 는 좌·우 키의 **dtype 이 정확히 같아야** 한다. pandas 2.x 는 스칼라
    #    Timestamp 로 만든 컬럼을 datetime64[s] 로, to_datetime 결과를 datetime64[ns] 로
    #    만들기 때문에 두 경로가 섞이면 MergeError 가 난다. 예외 메시지가 "keys must be
    #    sorted" 류라 정렬 문제로 오인하기 딱 좋다 — 실제로 그렇게 한 시간을 날린 버그다.
    #    양쪽을 ns 로 못박고, 카테고리 dtype 인 code 도 문자열로 통일한다.
    R["code"] = R["code"].astype(str)
    L["code"] = L["code"].astype(str)
    R["knowledge_date"] = ncq_ns(R["knowledge_date"])
    L["month"] = ncq_ns(L["month"])
    L = L.sort_values("month", kind="stable")
    R = R.sort_values("knowledge_date", kind="stable")
    try:
        _rcols = ["code", "knowledge_date", "shares", "shares_src"]
        if "shares_eff" in R.columns:
            _rcols.append("shares_eff")
        M = pd.merge_asof(L, R[_rcols],
                          left_on="month", right_on="knowledge_date",
                          by="code", direction="backward")
    except Exception as e:                                        # noqa
        LOG.warn(f"상장주식수 as-of 결합 실패({type(e).__name__}: {e}) — 시가총액을 만들 수 "
                 f"없습니다. 좌={L['month'].dtype} 우={R['knowledge_date'].dtype} "
                 f"(두 dtype 이 다르면 merge_asof 는 정렬 오류처럼 보이는 예외를 냅니다).")
        L["shares"] = np.nan
        L["shares_src"] = ""
        return L
    M = M.drop(columns=[c for c in ("knowledge_date",) if c in M.columns])
    M["shares_src"] = M["shares_src"].fillna("")
    # ★ 시가총액에는 '수정주가와 단위를 맞춘' shares_eff 를 쓴다(액면분할 보정).
    #   보정이 없는 소스는 shares 를 그대로 쓴다.
    if "shares_eff" not in M.columns:
        M["shares_eff"] = np.nan
    M["shares_eff"] = pd.to_numeric(M["shares_eff"], errors="coerce").where(
        pd.to_numeric(M["shares_eff"], errors="coerce").notna(),
        pd.to_numeric(M["shares"], errors="coerce"))
    return M


def build_marketcap_panel(codes: Sequence[str], months: pd.DatetimeIndex,
                          px_daily: pd.DataFrame, sec: pd.DataFrame,
                          shares_hist: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """PIT 월말 시가총액 패널. 공용 인덱스에 캐시하여 다른 전략도 그대로 재사용한다.

    시가총액 = PIT 상장주식수(DART 접수일자 기준) × 그 시점 수정종가.
    KRX 월말 스냅샷이 있으면(선택) 그 값을 우선하고, 없으면 위 식으로 만든다.

    반환: MCAP[code, month, close, mcap, shares, mcap_src]
    """
    cached = VAULT.get_table("krx_marketcap_monthly", scope="shared")
    have_dates: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        # 과거 버전이 'month' 로 저장했을 수도 있다. 둘 다 없으면 이 캐시는 쓸 수 없다.
        _dc = "date" if "date" in c.columns else ("month" if "month" in c.columns else None)
        if _dc is None:
            LOG.warn("시가총액 캐시에 날짜 컬럼이 없습니다 — 이 캐시는 건너뜁니다(원본 보존).")
            c = pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
        else:
            c["date"] = as_ts_series(c[_dc])
        for _c in ("close", "mcap", "shares"):
            if _c not in c.columns:
                c[_c] = np.nan
        c = c.dropna(subset=["date", "code"])
        have_dates = set(c["date"].dt.strftime("%Y-%m"))
        frames.append(c[["date", "code", "close", "mcap", "shares"]])
        LOG.info(f"공용 캐시에서 월말 시가총액 {len(c):,}행 재사용 ({len(have_dates)}개월)")

    todo = [m for m in months if m.strftime("%Y-%m") not in have_dates]
    if RUN_MODE == "CACHED" and todo:
        LOG.warn(f"CACHED 모드 — 미수집 {len(todo)}개월의 시가총액 스냅샷을 건너뜁니다.")
        todo = []
    new = _ncq_mcap_from_pykrx(todo) if todo else pd.DataFrame(
        columns=["date", "code", "close", "mcap", "shares"])
    if len(new):
        frames.append(new)
        out = pd.concat(frames, ignore_index=True)
        out = out.dropna(subset=["date", "code"]).drop_duplicates(["date", "code"], keep="last")
        save = out.copy()
        save["date"] = as_ts_series(save["date"]).dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_monthly", save, scope="shared", domain="universe",
                        source="pykrx:get_market_cap_by_ticker",
                        extra={"note": "월말 시가총액·상장주식수 — 전 전략 공용 PIT 입력"})

    M = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "code", "close", "mcap", "shares"])
    if len(M):
        M["date"] = as_ts_series(M["date"])
        M = M.dropna(subset=["date", "code"]).drop_duplicates(["date", "code"], keep="last")
        M["month"] = M["date"] + pd.offsets.MonthEnd(0)
        M = M[["code", "month", "close", "mcap", "shares"]]
        M["mcap_src"] = "krx_snapshot"
    else:
        M = pd.DataFrame(columns=MCAP_COLS)

    # ── KRX-free 주 경로: PIT 상장주식수 × 월말 수정종가 ──────────────────────────────────
    px_m = ncq_month_end_close(px_daily, months)
    if len(px_m):
        base = ncq_shares_asof(px_m, shares_hist)
        if len(M):
            # 스냅샷이 이미 채운 (code, month) 는 그대로 둔다(그 시점 관측이 더 정확하다).
            key_have = set(zip(M["code"].astype(str), M["month"].values))
            keep = [(c, mm) not in key_have
                    for c, mm in zip(base["code"].astype(str), base["month"].values)]
            base = base[pd.Series(keep, index=base.index)]
        base = base.dropna(subset=["shares"])
        if len(base):
            # 수정종가 × '수정주가 단위로 환산한' 주식수. 두 계열의 단위가 어긋나면
            # 액면분할 종목의 시총이 배수만큼 틀리고 하위 N 경계가 통째로 오염된다.
            _sh = pd.to_numeric(base.get("shares_eff"), errors="coerce")
            _sh = _sh.where(_sh.notna(), pd.to_numeric(base["shares"], errors="coerce"))
            base["mcap"] = pd.to_numeric(base["close"], errors="coerce") * _sh
            base["mcap_src"] = base["shares_src"].replace("", "unknown")
            M = pd.concat([M, base[MCAP_COLS]], ignore_index=True)

    if M.empty:
        LOG.error("시가총액을 한 행도 만들지 못했습니다. 'KRX 스냅샷'도 '주식수 폴백'도 실패했습니다. "
                  "하위 N 유니버스를 구성할 수 없으므로 이 상태의 결과는 무효입니다.")
        return pd.DataFrame(columns=MCAP_COLS)

    M = M.dropna(subset=["code", "month"]).drop_duplicates(["code", "month"], keep="first")
    M = M[M["month"].isin(months)]
    M["mcap"] = pd.to_numeric(M["mcap"], errors="coerce")
    M = M[M["mcap"] > 0]

    _MCAP_SRC_DESC = {
        "krx_snapshot": "KRX 월말 스냅샷 — 그 시점 주식수 (진짜 PIT)",
        "dart_pit": "DART 주식총수현황 — 접수일자 기준 (진짜 PIT · KRX 무관)",
        "delist_registry": "폐지원장 상장주식수 — 그 종목 생애 상수로 사용",
        "approx_const_shares": "근사 — 현재 주식수 × 과거 종가 (증자·분할 미반영)",
    }
    cnt = Counter(M["mcap_src"])
    tot = max(len(M), 1)
    LOG.table([[k, f"{v:,}", f"{100*v/tot:.1f}%", _MCAP_SRC_DESC.get(k, "미상")]
               for k, v in cnt.most_common()],
              ["시총 소스", "행수", "비중", "성질"], ["l", "r", "r", "l"],
              title="시가총액 소스 감사 — 근사 비중이 크면 '하위 N' 경계가 그만큼 흐려집니다")
    manifest_put("mcap_source_mix", {k: int(v) for k, v in cnt.items()})
    pit_share = (cnt.get("krx_snapshot", 0) + cnt.get("dart_pit", 0)) / tot
    approx = cnt.get("approx_const_shares", 0) / tot
    manifest_put("mcap_pit_share", round(float(pit_share), 4))
    if approx > 0.5:
        LOG.warn(f"시가총액의 {100*approx:.0f}% 가 근사 경로(현재 주식수 × 과거 종가)입니다. "
                 f"유상증자가 잦은 소형주 구간이라 '하위 {NCQ_UNIVERSE_BOTTOM_N}' 경계가 흔들립니다.\n"
                 f"    개선 순서: ① DART_API_KEY 입력(무료·즉시, KRX 무관 — 가장 효과적)\n"
                 f"               ② 차단이 풀렸다면 NCQ_USE_KRX=True + KRX ID/PW")
        PIPE.note("WARN: 시가총액 근사 비중 과다")
    else:
        LOG.ok(f"시가총액의 {100*pit_share:.0f}% 가 진짜 PIT 경로입니다.")
    PIPE.io("OUT", "MEM", "marketcap_monthly", M, source="pykrx+fdr")
    return downcast(M)


# ── 유니버스 ────────────────────────────────────────────────────────────────────────────────
def build_ncq_universe(months: pd.DatetimeIndex, pxm: pd.DataFrame, mcap: pd.DataFrame,
                       uni_obj: "Universe", sec: pd.DataFrame,
                       bottom_n: Optional[int] = None,
                       min_adv: Optional[float] = None) -> pd.DataFrame:
    """월말 기준 PIT 유니버스. 명세 §5.1 의 제외조건 → 시총 오름차순 하위 N → 유동성 필터.

    ★ 제외된 종목을 **버리지 않고** excl 사유와 함께 전부 남긴다. 그래야 퍼널에서 어느 게이트가
      표본을 붕괴시켰는지 보인다. in_uni / liq_pass 두 불리언으로 단계를 구분한다.
    """
    bottom_n = int(bottom_n or NCQ_UNIVERSE_BOTTOM_N)
    min_adv = float(min_adv if min_adv is not None else NCQ_MIN_ADV)

    # ① 상장/폐지 기반 PIT 멤버십 (상장폐지 종목 포함 — 생존자편향 방지)
    parts = []
    for m in months:
        cs = uni_obj.at(m)
        if cs:
            parts.append(pd.DataFrame({"month": m, "code": cs}))
        uni_obj.audit_row("전체상장", m, cs)
    if not parts:
        LOG.error("PIT 멤버십이 비었습니다 — 상장일·폐지일 소스를 확보하지 못했습니다.")
        return pd.DataFrame(columns=UNI_COLS)
    U = pd.concat(parts, ignore_index=True)

    # ② 시총·유동성 결합
    if mcap is not None and len(mcap):
        U = U.merge(mcap[["code", "month", "mcap"]], on=["code", "month"], how="left")
    else:
        U["mcap"] = np.nan
    if pxm is not None and len(pxm):
        U = U.merge(pxm[["code", "month", "adv20"]], on=["code", "month"], how="left")
    else:
        U["adv20"] = np.nan

    # ③ 정적 제외 (우선주/스팩/리츠/ETF)
    st = ncq_static_exclusion(sec)
    U = U.merge(st, on="code", how="left")
    U["excl"] = U["excl_static"].fillna(EXCL_NONE)
    U = U.drop(columns=["excl_static"])

    # ④ 상장 6개월 미만 — Universe 의 시즈닝(120거래일)이 1차 방어, 여기서 달력 기준 2차 확인
    # ★ sec 에 같은 코드가 두 번 있으면 reindex 가 InvalidIndexError 로 죽는다. 먼저 유일화한다.
    _sec1 = sec.drop_duplicates("code") if (sec is not None and len(sec)) else pd.DataFrame(
        columns=["code", "listing_date"])
    ld = (_sec1.set_index("code")["listing_date"] if "listing_date" in _sec1.columns
          else pd.Series(dtype="datetime64[ns]"))
    ld = as_ts_series(ld.reindex(U["code"].to_numpy())).to_numpy()
    too_new = (~pd.isna(ld)) & (U["month"].to_numpy() < (ld + np.timedelta64(182, "D")))
    U.loc[(U["excl"] == EXCL_NONE) & too_new, "excl"] = EXCL_NEW

    # ⑤ 거래정지 추정 — 그 달 거래대금이 0/결측이면 체결 자체가 불가능하다.
    #    관리종목·투자주의환기종목 지정 이력은 PIT 확보가 어려워 대용 지표를 쓴다(한계로 명시).
    halted = (~(U["adv20"] > 0)) & U["adv20"].notna()
    U.loc[(U["excl"] == EXCL_NONE) & halted, "excl"] = EXCL_HALT
    U.loc[(U["excl"] == EXCL_NONE) & U["mcap"].isna(), "excl"] = EXCL_NOMCAP

    # ⑥ 시총 오름차순 하위 N
    elig = U["excl"] == EXCL_NONE
    U["mcap_rank"] = np.nan
    U.loc[elig, "mcap_rank"] = (U.loc[elig].groupby("month", observed=True)["mcap"]
                                .rank(method="first", ascending=True))
    U["in_uni"] = elig & (U["mcap_rank"] <= bottom_n)
    U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= min_adv)

    for m, g in U.groupby("month", observed=True):
        uni_obj.audit_row("PIT유니버스", m, g.loc[g["in_uni"], "code"].tolist())
        uni_obj.audit_row("유동성필터", m, g.loc[g["liq_pass"], "code"].tolist())

    n_uni = int(U["in_uni"].sum())
    n_liq = int(U["liq_pass"].sum())
    n_m = max(U["month"].nunique(), 1)
    LOG.ok(f"PIT 유니버스 구성 완료 — 월평균 상장 {len(U)/n_m:,.0f}종목 → "
           f"하위 {bottom_n} {n_uni/n_m:,.0f}종목 → 유동성(ADV≥{min_adv/1e8:.1f}억) "
           f"{n_liq/n_m:,.0f}종목")
    if n_liq / n_m < 50:
        LOG.warn(f"유동성 통과 종목이 월평균 {n_liq/n_m:,.0f}개뿐입니다. 하위 소형주 구간이라 "
                 f"당연한 결과일 수 있으나, 이벤트 표본이 그만큼 줄어 검정력이 낮아집니다. "
                 f"NCQ_MIN_ADV 민감도(5천만/1억/3억)를 반드시 함께 보세요.")
    manifest_put("universe_monthly_avg", {"listed": round(len(U)/n_m, 1),
                                          "bottom_n": round(n_uni/n_m, 1),
                                          "liquid": round(n_liq/n_m, 1)})
    PIPE.io("OUT", "MEM", "ncq_universe", U, source="PIT membership + mcap + adv")
    return downcast(U[UNI_COLS])


def universe_funnel(UNI: pd.DataFrame, EV: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """명세 §5.2 필수 산출물 — 월별 3단 퍼널 (유니버스 → 유동성통과 → 신규커버리지 이벤트)."""
    if UNI is None or UNI.empty:
        return pd.DataFrame(columns=["month", "listed", "in_uni", "liq_pass", "events"])
    g = UNI.groupby("month", observed=True)
    F = pd.DataFrame({
        "listed": g["code"].size(),
        "in_uni": g["in_uni"].sum(),
        "liq_pass": g["liq_pass"].sum(),
    }).reset_index()
    if EV is not None and len(EV):
        ev = EV.groupby("month", observed=True)["code"].nunique().rename("events").reset_index()
        F = F.merge(ev, on="month", how="left")
    else:
        F["events"] = np.nan
    F["events"] = F["events"].fillna(0).astype(int)
    F["conv_uni"] = F["in_uni"] / F["listed"].replace(0, np.nan)
    F["conv_liq"] = F["liq_pass"] / F["in_uni"].replace(0, np.nan)
    F["conv_ev"] = F["events"] / F["liq_pass"].replace(0, np.nan)
    return F
