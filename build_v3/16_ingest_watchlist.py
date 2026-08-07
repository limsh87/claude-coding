

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-W  관리종목 · 투자주의환기 · 감사의견 · 매매거래정지  (S1_FIREWALL 의 하드 입력)       ║
# ║                                                                                          ║
# ║  ★ PIT 로 만드는 방법 ────────────────────────────────────────────────────────────────  ║
# ║    "지금 관리종목인 목록"(FDR KRX-ADMINISTRATIVE)을 과거에 적용하면 그 자체가 미래누수다. ║
# ║    2019년에 관리종목이었다가 2021년에 해제된 기업을 2016년부터 제외해 버리기 때문이다.    ║
# ║    → 지정/해제 '이벤트'를 모아 계단함수로 복원한다. 이벤트의 knowledge_date 는 공시일.    ║
# ║                                                                                          ║
# ║  소스: OpenDART 공시목록                                                                  ║
# ║        pblntf_ty="I" (거래소공시) → 관리종목 지정/해제 · 투자주의환기 · 매매거래정지      ║
# ║        pblntf_ty="F" (외부감사관련) → 감사보고서 제출 · 감사의견 비적정                    ║
# ║  보강: FDR KRX-ADMINISTRATIVE (현재 시점 목록) — ★비PIT 이므로 '현재 상태' 확인용으로만   ║
# ║        쓰고 과거에 소급 적용하지 않는다. 커버리지 비교용으로 표에만 남긴다.                ║
# ║                                                                                          ║
# ║  ★ K6 규칙: 이 소스를 한 건도 못 얻으면 해당 방화벽 조항을 '비활성'으로 두고 로깅한다.     ║
# ║    데이터가 없는데 전부 '적정'으로 간주해 통과시키는 것도, 전부 배제하는 것도 거짓이다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ★ 순서가 중요하다. '해제'를 먼저 검사하지 않으면 "관리종목 지정 해제"가 '지정'으로 잡힌다.
MARKET_ACTION_PATTERNS: List[Tuple[str, str]] = [
    ("watch_off",  r"관리종목.*(지정\s*)?해제|관리종목에서\s*해제"),
    ("watch_on",   r"관리종목\s*지정"),
    ("alert_off",  r"투자주의\s*환기종목.*해제"),
    ("alert_on",   r"투자주의\s*환기종목\s*지정"),
    ("halt_off",   r"매매거래\s*정지\s*해제|거래정지\s*해제"),
    ("halt_on",    r"매매거래\s*정지|거래정지"),
    ("audit_bad",  r"감사의견\s*(거절|한정|부적정)|의견거절|비적정\s*감사의견"),
    ("audit_rpt",  r"감사보고서\s*제출|^감사보고서"),
    ("delist_risk", r"상장폐지\s*사유|상장적격성\s*실질심사"),
]

WATCH_FLAG_COLS = ["is_watchlist", "is_alert", "is_trading_halted", "audit_bad", "delist_risk"]


def fetch_market_actions(start: str, end: str) -> pd.DataFrame:
    """거래소공시(I) · 외부감사관련(F) 공시목록 → 시장조치 이벤트.

    반환: corp_code, rcept_dt(=knowledge_date), report_nm, action
    """
    empty = pd.DataFrame(columns=["corp_code", "rcept_dt", "report_nm", "action"])
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 가 없어 관리종목·감사의견 이력을 수집할 수 없습니다. "
                 "S1_FIREWALL 의 해당 조항은 K6 규칙에 따라 '비활성'으로 두고 진행합니다.")
        return empty

    cached = VAULT.get_table("krx_market_actions", scope="shared")
    have_months: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.ok(f"공용 캐시에서 시장조치 공시 {len(cached):,}행 재사용 "
               f"({len(have_months)}개월분 — 다른 전략과 공유)")

    # ★ '행이 하나라도 있으면 완료'로 보면 반쪽짜리 달이 영구히 굳는다.
    #   완료 여부는 별도 원장에 명시적으로 기록한다(없으면 미완료로 간주 = 재수집).
    done_ledger = VAULT.get_table("krx_market_actions_months", scope="shared")
    done_months = set()
    if done_ledger is not None and len(done_ledger) and "month" in done_ledger.columns:
        done_months = set(done_ledger.loc[
            done_ledger.get("complete", True).astype(bool), "month"].astype(str))
    have_months = have_months & done_months if done_months else set()

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 미확보 {len(todo)}개월은 신규 수집하지 않습니다.")
        todo = []

    def _one(m):
        """반환: (rows, complete). complete=False 면 그 달은 '완료'로 기록하지 않는다.

        ★ 페이지 중간 실패를 '데이터 끝'으로 착각하면 안 된다.
          dart_api 는 일일한도 초과·5xx·타임아웃에서 None 을 돌려주는데, 그걸 그대로
          break 하면 12페이지 중 3페이지만 받고 끝난 달이 만들어진다. 그 달은 행이
          있으므로 다음 실행의 have_months 에 '완료'로 잡혀 **영구히 반쪽짜리로 굳는다.**
          그 구간의 관리종목·감사의견 이벤트가 통째로 비고, 방화벽은 조용히 약해진다.
        """
        rows, complete = [], True
        for ty in ("I", "F"):
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})
                if js is None:
                    complete = False               # 호출 자체가 실패 → 미완료
                    break
                if not isinstance(js.get("list"), list) or not js["list"]:
                    # status 013(데이터 없음)은 정상적인 끝이다.
                    if str(js.get("status", "")) not in ("000", "013"):
                        complete = False
                    break
                rows.extend(js["list"])
                total = int(js.get("total_page", 1) or 1)
                if page >= total:
                    break
                page += 1
            else:
                complete = False                   # 100페이지 상한에 걸림 = 아직 남았다
        return rows, complete

    new: List[dict] = []
    incomplete: List[str] = []
    if todo:
        LOG.info(f"거래소공시·외부감사 공시목록 {len(todo)}개월 수집")
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="시장조치 공시")
        for m, out in zip(todo, res):
            if not out:
                incomplete.append(str(m))
                continue
            rows, complete = out
            if rows:
                new.extend(rows)
            if not complete:
                incomplete.append(str(m))
        if incomplete:
            LOG.warn(f"{len(incomplete)}개월이 페이지 중간에 끊겼습니다({incomplete[:4]}...). "
                     f"받은 행은 저장하되 '완료'로 기록하지 않아 다음 실행에서 다시 받습니다.")

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no",
                            "rcept_dt", "report_nm") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        LOG.warn("시장조치 공시를 한 건도 얻지 못했습니다 — 방화벽의 관리종목·감사의견 조항을 "
                 "비활성화하고 진행합니다(K6).")
        return empty

    D = pd.concat(frames, ignore_index=True)
    if "rcept_no" in D.columns:
        D = D.drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D = D.dropna(subset=["rcept_dt", "corp_code"])

    D["action"] = ""
    for act, pat in MARKET_ACTION_PATTERNS:
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["action"] == "")
        D.loc[hit, "action"] = act
    D = D[D["action"] != ""].copy()

    if new or incomplete:
        _prev = done_ledger if done_ledger is not None and len(done_ledger) else None
        _rows = [{"month": str(m), "complete": str(m) not in incomplete} for m in todo]
        _led = pd.DataFrame(_rows)
        if _prev is not None:
            _led = pd.concat([_prev, _led], ignore_index=True)
        _led = _led.drop_duplicates("month", keep="last")
        VAULT.put_table("krx_market_actions_months", _led, scope="shared", domain="krx",
                        source="fetch_market_actions:completeness")
    if new:
        VAULT.put_table("krx_market_actions", D, scope="shared", domain="krx",
                        source="opendart list.json (pblntf_ty=I,F)",
                        extra={"note": "관리종목·투자주의환기·거래정지·감사의견 이벤트 — 전 전략 공용"})
    LOG.ok(f"시장조치 이벤트 {len(D):,}건 — " +
           ", ".join(f"{a}={int((D['action'] == a).sum()):,}"
                     for a, _ in MARKET_ACTION_PATTERNS if (D["action"] == a).any()))
    PIPE.io("OUT", "DRIVE", "krx_market_actions", D, source="opendart")
    return D[["corp_code", "rcept_dt", "report_nm", "action"]]


def _step_state(ev: pd.DataFrame, on_act: str, off_act: str, key: str) -> pd.DataFrame:
    """지정/해제 이벤트 → 시점별 상태(계단함수).

    반환: key, knowledge_date, state (0/1) — merge_asof(backward) 로 패널에 실어 나른다.

    ★ 상태는 '가장 최근 이벤트의 종류'다. 누적합(cumsum)이 아니다. ───────────────────
      한때 지정=+1 / 해제=-1 을 cumsum 하고 clip(lower=0) 했었다. 그러면 이렇게 깨진다:
        공시 수집 구간이 2016-08 부터라, 2016-05 에 지정된 종목은 'on' 이 수집되지 않고
        2017-03 의 'off'(-1) 만 잡힌다 → 누적합 -1. 이후 2018-06 에 진짜 '관리종목 지정'
        (+1)이 와도 누적합은 0 → clip → state=0. 즉 그 종목은 **영구히 관리종목이 아닌
        것으로 읽힌다.** 방화벽 조항이 그 종목에 대해 통째로 무력화된다.
      가장 최근 이벤트만 보면 이력 시작 이전 상태를 몰라도 항상 올바르게 복원된다.
    """
    on = ev[ev["action"] == on_act][[key, "rcept_dt"]].assign(state=np.int8(1))
    off = ev[ev["action"] == off_act][[key, "rcept_dt"]].assign(state=np.int8(0))
    E = pd.concat([on, off], ignore_index=True)
    if E.empty:
        return pd.DataFrame(columns=[key, "knowledge_date", "state"])
    E = E.dropna(subset=[key, "rcept_dt"]).sort_values([key, "rcept_dt"], kind="stable")
    # 같은 날 지정과 해제가 같이 오면 '해제'를 뒤로 보내 마지막 값이 되게 한다(보수적).
    E = E.sort_values([key, "rcept_dt", "state"], kind="stable")
    E = E.drop_duplicates([key, "rcept_dt"], keep="first")
    return E.rename(columns={"rcept_dt": "knowledge_date"})[[key, "knowledge_date", "state"]]


def _one_shot_state(ev: pd.DataFrame, act: str, key: str, valid_days: int = 400) -> pd.DataFrame:
    """해제 이벤트가 없는 단발 사건(감사의견 비적정 등)을 유효기간 동안 켜 둔다.

    ★ 만료는 '누적 최댓값'이어야 한다. 사건마다 (on, on+400일) 쌍을 독립적으로 찍으면
      2019-03 과 2020-03 에 각각 비적정이 났을 때 2019 건의 만료행(2020-04)이 2020 건의
      효력을 꺼 버린다 — 더 최근에 더 나쁜 사건이 있는데 상태가 정상으로 읽힌다.
    """
    on = ev[ev["action"] == act][[key, "rcept_dt"]].dropna()
    if on.empty:
        return pd.DataFrame(columns=[key, "knowledge_date", "state"])
    on = on.sort_values([key, "rcept_dt"], kind="stable").copy()
    exp = on["rcept_dt"] + pd.Timedelta(days=valid_days)
    # 종목별 만료시점의 누적 최댓값 → 나중 사건이 앞선 사건의 만료를 항상 밀어낸다
    on["_exp"] = exp.groupby(on[key], observed=True).cummax()
    # 만료행은 그 종목의 '마지막 만료'만 남긴다(중간 만료행이 켜진 상태를 끄지 않도록)
    last_exp = on.groupby(key, observed=True)["_exp"].max().reset_index()
    rows = [on.assign(knowledge_date=on["rcept_dt"], state=np.int8(1))[[key, "knowledge_date", "state"]],
            last_exp.rename(columns={"_exp": "knowledge_date"}).assign(state=np.int8(0))]
    E = pd.concat(rows, ignore_index=True)[[key, "knowledge_date", "state"]]
    return (E.sort_values([key, "knowledge_date"], kind="stable")
             .drop_duplicates([key, "knowledge_date"], keep="last"))


def build_watchlist_panel(P: pd.DataFrame, actions: pd.DataFrame,
                          sec: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, bool]]:
    """(code, month) 패널에 방화벽 플래그를 as-of 결합한다.

    반환: (패널, 조항별 활성여부)   — 활성여부가 False 인 조항은 방화벽에서 제외되고 그 사실이
          로그·표에 남는다(K6). 데이터가 없는데 '전부 적정'으로 간주해 통과시키지 않는다.
    """
    P = P.copy()
    for c in WATCH_FLAG_COLS:
        if c not in P.columns:
            P[c] = np.nan          # NaN = '알 수 없음'. 0(정상)과 구분한다.

    active = {"watchlist": False, "alert": False, "halt": False, "audit": False,
              "delist_risk": False}
    if actions is None or len(actions) == 0:
        LOG.warn("시장조치 이벤트가 없어 방화벽의 관리종목/감사의견/거래정지 조항을 "
                 "전부 비활성화합니다(K6). 방화벽은 자본잠식·영업CF·유동성·밸류 조항만으로 "
                 "동작하며, 그 사실이 R5-M 절제표에 그대로 드러납니다.")
        return P, active

    # corp_code → code 매핑.
    # ★ 1:N 이다. 한 법인(corp_code)이 보통주·우선주 등 여러 종목코드를 가진다.
    #   set_index("corp_code")["code"].to_dict() 로 만들면 중복 인덱스에서 **마지막 하나만**
    #   살아남는다. sec 가 code 오름차순이라 살아남는 건 대개 우선주(001685)이고,
    #   그러면 관리종목·감사의견·거래정지 플래그가 보통주(001680)에는 전혀 안 붙는다.
    #   실제 백테스트가 거래하는 건 보통주이므로 방화벽이 조용히 새는 통로가 된다.
    #   → 매핑을 접지 말고 펼친다(explode). 한 법인의 이벤트는 그 법인의 전 종목에 적용된다.
    link = (sec.dropna(subset=["corp_code"])[["code", "corp_code"]].copy()
               .assign(corp_code=lambda d: d["corp_code"].astype(str),
                       code=lambda d: d["code"].astype(str))
               .drop_duplicates())
    ev = actions.copy()
    ev["corp_code"] = ev["corp_code"].astype(str)
    n_before = len(ev)
    ev = ev.merge(link, on="corp_code", how="left")
    n_unmapped = int(ev["code"].isna().sum())
    ev = ev.dropna(subset=["code", "rcept_dt"])
    n_fan = len(ev) - (n_before - n_unmapped)
    if n_fan > 0:
        LOG.debug(f"시장조치 이벤트 {n_fan:,}건이 복수 상장(보통주/우선주)으로 확장되었습니다.")
    if n_unmapped:
        LOG.info(f"시장조치 이벤트 {n_unmapped:,}건은 corp_code↔종목코드 매핑이 없어 제외했습니다 "
                 f"(비상장·합병소멸 법인이 대부분입니다).")

    specs = [
        ("is_watchlist",      _step_state(ev, "watch_on", "watch_off", "code"), "watchlist"),
        ("is_alert",          _step_state(ev, "alert_on", "alert_off", "code"), "alert"),
        ("is_trading_halted", _step_state(ev, "halt_on", "halt_off", "code"), "halt"),
        ("audit_bad",         _one_shot_state(ev, "audit_bad", "code", 400), "audit"),
        ("delist_risk",       _one_shot_state(ev, "delist_risk", "code", 400), "delist_risk"),
    ]

    base = P[["code", "month"]].copy()
    base["code"] = base["code"].astype(str)
    base["_ord"] = np.arange(len(base))
    L = base.dropna(subset=["month"]).sort_values("month", kind="stable")

    for colname, S, key in specs:
        if S is None or S.empty:
            continue
        S = S.copy()
        S["code"] = S["code"].astype(str)
        S = S.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        try:
            M = pd.merge_asof(L, S, left_on="month", right_on="knowledge_date",
                              by="code", direction="backward")
        except Exception as e:                                          # noqa
            LOG.warn(f"{colname} as-of 결합 실패({type(e).__name__}) — 이 조항을 비활성화합니다.")
            continue
        vals = M.set_index("_ord")["state"].reindex(base["_ord"]).to_numpy()
        # 이벤트가 한 번도 없던 종목은 NaN → '해당 조치 없음'(=0) 으로 본다.
        # 소스 자체는 확보됐으므로 '알 수 없음'이 아니라 '해당 없음'이 맞다.
        P[colname] = np.nan_to_num(vals.astype("float64"), nan=0.0)
        active[key] = True

    on_rows = [[c, f"{int(pd.to_numeric(P[c], errors='coerce').fillna(0).sum()):,}",
                f"{100*pd.to_numeric(P[c], errors='coerce').fillna(0).mean():.2f}%",
                "활성" if active[k] else "비활성(K6)"]
               for c, _, k in [(a, b, d) for a, b, d in specs]]
    LOG.table(on_rows, ["방화벽 플래그", "발동 행수", "패널 비중", "조항 상태"],
              ["l", "r", "r", "c"],
              title="관리종목·감사의견·거래정지 (PIT 계단함수로 복원 — 현재 목록의 소급적용 아님)")
    return P, active


def derive_halt_from_price(px_daily: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    """가격 데이터에서 거래정지를 보강 추정한다(공시 누락 대비).

    월말 직전 20거래일 중 거래량 0 인 날이 10일 이상이면 사실상 거래가 없는 종목이다.
    공시 기반 플래그와 OR 로 결합한다 — 방화벽은 fail-closed 가 안전한 쪽이다.
    """
    if px_daily is None or len(px_daily) == 0 or "volume" not in px_daily.columns:
        return P
    d = px_daily[["code", "date", "volume"]].copy()
    d = d.sort_values(["code", "date"], kind="stable")
    d["_zero"] = (pd.to_numeric(d["volume"], errors="coerce").fillna(0) <= 0).astype("int8")
    d["_z20"] = (d.groupby("code", observed=True)["_zero"]
                  .transform(lambda s: s.rolling(20, min_periods=5).sum()))
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    m = (d.groupby(["code", "month"], observed=True)["_z20"].last().reset_index()
          .rename(columns={"_z20": "zero_days20"}))
    out = P.merge(m, on=["code", "month"], how="left")
    halt_px = (pd.to_numeric(out["zero_days20"], errors="coerce").fillna(0) >= 10).astype("float64")
    prev = pd.to_numeric(out.get("is_trading_halted"), errors="coerce").fillna(0.0)
    out["is_trading_halted"] = np.maximum(prev.to_numpy(), halt_px.to_numpy())
    n_add = int((halt_px.to_numpy() > prev.to_numpy()).sum())
    if n_add:
        LOG.info(f"거래량 기준으로 거래정지 {n_add:,}행을 추가 식별했습니다 "
                 f"(공시 누락 보강 — 20거래일 중 10일 이상 거래량 0).")
    return out
