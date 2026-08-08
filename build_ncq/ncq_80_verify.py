

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-V  자가검정 계층 — 계약검정 N1~N11 · 카나리 C1~C7 · 실경로 리허설 · 합성 스모크        ║
# ║                                                                                          ║
# ║  입력 : 없음(합성데이터·픽스처). 카나리(B)만 네트워크가 필요하다.                           ║
# ║  출력 : LOG.table 판정표. run_canaries 는 결과 dict, 나머지는 bool.                        ║
# ║  실패 : strict=True 면 RuntimeError(계약검정은 KillCriteria). strict=False 면 False 반환.  ║
# ║                                                                                          ║
# ║  ── 네 검정은 서로 '다른 것'을 본다. 하나가 다른 하나를 대신하지 못한다 ────────────────    ║
# ║   (A) run_contract_tests  협상 불가 규칙(PIT·생존자편향·무기억성·동결·회계)을 테스트로 강제 ║
# ║   (B) run_canaries        외부 소스가 '지금 이 순간' 살아 있는가 (유일하게 네트워크 필요)   ║
# ║   (C) run_rehearsal       네트워크만 가짜, 수집·정제 '함수'는 실물 실행 (파싱·스키마 사고)  ║
# ║   (D) run_selftest        합성데이터로 유니버스→이벤트→텍스트→신호→백테스트 전 경로 관통   ║
# ║                                                                                          ║
# ║  왜 (C)가 따로 필요한가: (D)의 합성 스모크는 완성된 패널을 곧바로 주입하므로                ║
# ║  build_security_master · fetch_prices · naver_collect 같은 수집·정제 함수가 단 한 줄도      ║
# ║  실행되지 않는다. 실제로 그 공백 때문에 스모크를 전부 통과한 빌드가 실수집 2분 만에         ║
# ║  중복 컬럼 한 줄로 죽은 적이 있다. (C)는 그 구멍만을 겨냥한다.                              ║
# ║                                                                                          ║
# ║  ★★ 절대 원칙 ★★  이 계층은 사용자의 드라이브 캐시에 단 한 바이트도 쓰지 않는다.           ║
# ║   합성·픽스처 결과가 공용 인덱스에 섞이면 그 자체가 캐시 오염이고, 다른 전략까지 오염된다.  ║
# ║   그래서 (A)(C)(D)는 tempfile 로 만든 임시 Vault 로 전역 VAULT 를 교체하고,                 ║
# ║   finally 에서 반드시 원복 + 임시 디렉터리 삭제한다.                                       ║
# ║                                                                                          ║
# ║  ★ 스파인 모듈(ncq_40/50/70)이 아직 조립되지 않았을 수 있으므로 모든 호출은                 ║
# ║   `"fn" in globals()` 로 가드하고, 없으면 그 항목을 SKIP 으로 기록한다(하드 실패 금지).     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 공통 유틸 ───────────────────────────────────────────────────────────────────────────────
NCQ_VERIFY_SKIPPED: List[str] = []          # 스파인 미탑재로 건너뛴 항목 (최종 요약에 노출)


def ncq_has(*names: str) -> bool:
    """호출 대상 함수/클래스가 조립되어 있는가. 없으면 검정을 SKIP 으로 낮춘다."""
    G = globals()
    return all(n in G and G[n] is not None for n in names)


def ncq_v_num(v: Any, kind: str = "num", nd: int = 3) -> str:
    """수치 포맷. **결측은 반드시 '—'** — NaN 을 0으로 치환하면 없는 근거를 있다고 주장하는 것이다."""
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except Exception:
        return str(v)
    if not np.isfinite(f):
        return "—"
    if kind == "pct":
        return f"{f*100:+.2f}%"
    if kind == "pctp":
        return f"{f*100:+.3f}%p"
    if kind == "int":
        return f"{int(round(f)):,}"
    return f"{f:,.{nd}f}"


def ncq_tail_tb(n: int = 10) -> List[str]:
    """마지막 트레이스백 n줄. 실패 원인을 스크롤 없이 보이게 하는 최소 장치."""
    try:
        return [ln for ln in traceback.format_exc().rstrip().split("\n")[-n:]]
    except Exception:
        return []


def ncq_call_event_texts(EV, REP, extra=None):
    """collect_event_texts 호출 어댑터.

    ★ 계약 §4 의 시그니처는 (EV, REP) 뿐이다. 구현이 합성 본문 주입용 선택 인자
      (extra_text)를 추가로 받을 수도 있는데, 그 인자를 무조건 넘기면 계약대로 만든
      구현에서 TypeError 로 죽는다. 반대로 아예 안 넘기면 네트워크 없는 환경에서
      본문이 비어 doc_score 가 전부 0이 되고, 그 0 은 '스코어러 고장'과 '텍스트 없음'을
      구분하지 못한다. 그래서 **시그니처를 보고** 받을 수 있을 때만 넘긴다.
    """
    fn = globals().get("collect_event_texts")
    if fn is None:
        return None
    if extra is not None:
        try:
            import inspect as _isp                       # 지역 import (최상위 import 금지)
            if "extra_text" in _isp.signature(fn).parameters:
                return fn(EV, REP, extra_text=extra)
        except Exception:
            pass
    return fn(EV, REP)


@contextmanager
def ncq_tmp_vault(prefix: str = "ncq_verify_"):
    """임시 Vault 로 전역을 교체한다(캐시 무해성).

    ★ 이게 없으면 계약검정·리허설·스모크가 만든 합성 테이블이 사용자의 공용 인덱스에
      그대로 들어간다. 다른 전략이 그 테이블을 '진짜 데이터'로 재사용하면 조용한 오염이다.
    """
    G = globals()
    saved = G.get("VAULT")
    tmp = tempfile.mkdtemp(prefix=prefix)
    try:
        G["VAULT"] = Vault(tmp, "VERIFY")
        yield tmp
    finally:
        G["VAULT"] = saved
        shutil.rmtree(tmp, ignore_errors=True)


def ncq_lexicon_words() -> Tuple[List[str], List[str]]:
    """합성 텍스트에 섞을 어휘. 동결 렉시콘이 있으면 그 어휘를 그대로 쓴다.

    ★ 렉시콘 어휘를 쓰지 않으면 score_texts 가 전부 0점을 내고, 그러면 횡단면 z 가
      전 종목 동일값이 되어 스모크가 '통과'해도 아무것도 증명하지 못한다.
    """
    pos: List[str] = []
    neg: List[str] = []
    lex = globals().get("NCQ_LEXICON")
    if isinstance(lex, dict):
        def _walk(node, negative: bool):
            if isinstance(node, str):
                (neg if negative else pos).append(node)
            elif isinstance(node, (list, tuple, set)):
                for x in node:
                    _walk(x, negative)
            elif isinstance(node, dict):
                for k, v in node.items():
                    kk = str(k).lower()
                    _walk(v, negative or kk in ("n", "neg", "negative") or "neg" in kk)
        _walk(lex, False)
    pos = [w for w in dict.fromkeys(pos) if isinstance(w, str) and 1 < len(w) <= 20]
    neg = [w for w in dict.fromkeys(neg) if isinstance(w, str) and 1 < len(w) <= 20]
    if len(pos) < 6:
        pos = ["신규 수주", "양산 개시", "전방시장 진입", "생산능력 증설", "구조적 성장",
               "고객사 다변화", "사업구조 전환", "점유율 확대", "장기공급계약", "수직계열화",
               "신규 라인", "턴어라운드"]
    if len(neg) < 4:
        neg = ["일회성 요인", "기저효과", "단기 반등", "환율 효과", "재고 소진", "홍보성"]
    return pos, neg


# ══════════════════════════════════════════════════════════════════════════════════════════
#  0. 합성 데이터 생성기 — (A)(D) 가 공유한다. 반드시 결정적(seed 고정).
# ══════════════════════════════════════════════════════════════════════════════════════════
def ncq_make_synthetic(n_codes: int = 180, n_months: int = 72, seed: int = SEED) -> dict:
    """네트워크·키 없이 전 경로를 돌리기 위한 합성 세계.

    반환: sec / px_daily / pxm / mcap / UNI / REP / TXT / months / uni_obj / snapshots / quality

    설계 의도(중요):
      · 종목을 세 무리로 나눈다.
          bg   (전체의 1/3) — 매달 꾸준히 커버리지가 있는 종목. **이벤트가 나오면 안 된다.**
                              동시에 월별 리포트 건수를 안정시켜 아카이브 결손 오판을 막는다.
          ev   (전체의 1/2) — 중간 어느 달에 처음 커버리지가 붙는 종목. 여기서 H1 이 나온다.
          dark (나머지)     — 끝까지 커버리지가 없는 종목. 유니버스 분모 역할.
      · ev 종목은 첫 커버리지 이후 28~34개월 뒤 두 번째 에피소드를 갖는다 → 이벤트 밀도를 올린다.
        그래도 월평균 이벤트는 의도적으로 NCQ_MIN_EVENTS_PER_MONTH 근방에 머문다.
        z 표본 부족 → pooled 경로가 실제로 발화해야 그 경로가 검증되기 때문이다.
      · 텍스트는 동결 렉시콘 어휘를 quality 에 비례해 섞는다 → score_texts 가 분산을 낸다.
      · quality 는 미래수익 드리프트에도 들어간다 → 스모크에서 '신호가 있는' 상황을 만든다.
        (성과 수치는 난수다. 절대 해석 대상이 아니다 — 배관 검증용이다.)
    """
    rng = np.random.default_rng(int(seed))
    end = as_ts(BACKTEST_END) or as_ts("2026-07-31")
    months = pd.date_range(end - pd.DateOffset(months=int(n_months) - 1), end, freq="ME")
    n_codes = int(n_codes)

    # 코드 끝자리를 0 으로 고정한다. 끝자리 5/7/9 는 ncq_is_preferred 가 우선주로 보므로
    # 합성 종목의 1/3 이 이유 없이 유니버스에서 빠져 표본이 조용히 줄어든다.
    codes = [f"{(i + 1) * 10:06d}" for i in range(n_codes)]
    inds = rng.choice(["화학", "전자부품", "기계", "소프트웨어", "제약", "건설"], n_codes)
    quality = rng.normal(size=n_codes)

    n_bg = max(4, n_codes // 3)
    n_ev = max(4, n_codes // 2)
    bg_idx = list(range(0, n_bg))
    ev_idx = list(range(n_bg, min(n_codes, n_bg + n_ev)))
    dark_idx = list(range(min(n_codes, n_bg + n_ev), n_codes))

    # ── 상장/폐지 (생존자편향 경로를 실제로 태운다) ────────────────────────────────────────
    listing = [months[0] - pd.DateOffset(years=int(rng.integers(3, 12))) for _ in codes]
    delist: List[Any] = [pd.NaT] * n_codes
    if n_months > 24:
        for i in rng.choice(n_codes, size=max(1, n_codes // 14), replace=False):
            listing[int(i)] = months[int(rng.integers(4, max(5, n_months - 14)))]
        for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
            delist[int(i)] = months[int(rng.integers(max(6, n_months // 3), n_months - 2))]

    names = [f"합성{i+1:03d}" for i in range(n_codes)]
    for k in range(min(3, n_codes)):                 # 스팩 제외 경로를 태우기 위한 소수 표본
        names[dark_idx[k] if k < len(dark_idx) else k] = f"합성스팩{k+1}호"

    sec = pd.DataFrame({
        "code": codes, "name": names,
        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
        "listing_date": listing, "delisting_date": delist,
        "industry": inds,
        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)],
        "src": "synthetic"})

    # ── 일봉 ──────────────────────────────────────────────────────────────────────────────
    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1] + pd.Timedelta(days=6))
    frames = []
    for i, c in enumerate(codes):
        drift = 0.0003 + 0.0015 * quality[i]
        r = rng.normal(drift, 0.024, len(days))
        p = float(np.exp(rng.normal(8.6, 0.6))) * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.2, 0.7, len(days))
        frames.append(pd.DataFrame({
            "code": c, "date": days,
            "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * 1.012, "low": p * 0.988, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(frames, ignore_index=True)
    keep = np.ones(len(px), dtype=bool)
    dcol = px["date"].to_numpy()
    ccol = px["code"].to_numpy()
    for i, c in enumerate(codes):
        m = (ccol == c)
        keep &= ~(m & (dcol < np.datetime64(as_ts(listing[i]))))
        if pd.notna(delist[i]):
            keep &= ~(m & (dcol > np.datetime64(as_ts(delist[i]))))
    px = px[keep].reset_index(drop=True)

    panel = build_price_panel(px, months)
    px_daily, pxm = panel["daily"], panel["monthly"]
    # ★ 여기가 비면 아래 전부가 KeyError 로 죽는다. 원인을 알아볼 수 있는 메시지로 바꾼다.
    if pxm is None or len(pxm) == 0 or "close" not in getattr(pxm, "columns", []):
        raise RuntimeError("합성 월간 패널이 비었습니다 — build_price_panel 이 일봉을 월말로 "
                           "접지 못했습니다(입력 일봉 %d행). 합성 세계를 만들 수 없습니다."
                           % (0 if px is None else len(px)))

    # ── 시가총액 (PIT 근사 — 합성이므로 주식수는 상수) ─────────────────────────────────────
    shares = pd.Series(np.exp(rng.normal(15.5, 0.7, n_codes)), index=codes)
    mcap = pxm[["code", "month", "close"]].copy()
    mcap["shares"] = mcap["code"].map(shares).astype(float)
    mcap["mcap"] = pd.to_numeric(mcap["close"], errors="coerce") * mcap["shares"]
    mcap["mcap_src"] = "synthetic"
    mcap = mcap[["code", "month", "close", "mcap", "shares", "mcap_src"]]

    # ── 픽스처 UNI (실제 build_ncq_universe 결과와 비교·대체용) ────────────────────────────
    U = pxm[["code", "month", "adv20"]].merge(mcap[["code", "month", "mcap"]],
                                              on=["code", "month"], how="left")
    U["excl"] = ""
    U["mcap_rank"] = U.groupby("month", observed=True)["mcap"].rank(method="first", ascending=True)
    U["in_uni"] = U["mcap_rank"] <= float(NCQ_UNIVERSE_BOTTOM_N)
    U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= float(NCQ_MIN_ADV))
    UNI = U[["month", "code", "mcap", "adv20", "mcap_rank", "in_uni", "liq_pass", "excl"]]

    # ── 리포트 원장 ───────────────────────────────────────────────────────────────────────
    brokers = (MAJOR_BROKERS[:8] + MINOR_BROKERS[:8]) if ncq_has("MAJOR_BROKERS", "MINOR_BROKERS") \
        else ["삼성증권", "KB증권", "NH투자증권", "신영증권", "유진투자증권", "하나증권"]
    hist0 = months[0] - pd.DateOffset(months=36)          # 룩백 이력을 위해 창보다 앞서 시작
    hist_months = pd.date_range(hist0, months[-1], freq="ME")
    pos_w, neg_w = ncq_lexicon_words()
    rows: List[dict] = []

    def _one(code: str, m: pd.Timestamp, broker: str, sponsored: bool):
        d = (m - pd.Timedelta(days=int(rng.integers(0, 26)))).normalize()
        uid = sha1_str("ncqsyn", code, str(m.date()), broker, int(rng.integers(0, 10 ** 9)))
        rows.append({
            "report_uid": uid, "source": "irs" if sponsored else
            ("naver" if rng.random() < 0.7 else "hankyung"),
            "src_report_id": uid[:12], "pub_date": d, "category": "company",
            "title": f"{code} 합성 리포트", "stock_code": code,
            "stock_name": f"합성{code}", "broker_raw": broker,
            "analyst_raw": f"애널{int(rng.integers(0, 40)):02d}",
            "target_price": float(np.exp(rng.normal(9.5, 0.4))), "opinion": "BUY",
            "pdf_url": None, "detail_url": None, "views": None,
            "is_sponsored": bool(sponsored), "event_date": d, "knowledge_date": d})

    # bg: 꾸준한 커버리지 (이벤트가 나오면 안 되는 대조군 + 월별 건수 안정화)
    for i in bg_idx:
        for m in hist_months:
            if rng.random() < 0.75:
                _one(codes[i], m, str(rng.choice(brokers)), False)

    # ev: 첫 커버리지 + (선택) 두 번째 에피소드
    ev_months: Dict[str, List[pd.Timestamp]] = {}
    for i in ev_idx:
        lo = 26                                   # burn-in 이후에 놓이도록 충분히 뒤로
        hi = max(lo + 1, len(hist_months) - 16)
        k0 = int(rng.integers(lo, hi))
        eps = [k0]
        k1 = k0 + int(rng.integers(28, 35))
        if k1 < len(hist_months) - 2:
            eps.append(k1)
        ev_months[codes[i]] = [hist_months[k] for k in eps]
        for k in eps:
            m = hist_months[k]
            sponsored = bool(rng.random() < 0.18)
            for _ in range(int(rng.integers(1, 4))):
                _one(codes[i], m, str(rng.choice(brokers)), sponsored)
            for step in (2, 4, 7):                # 후속 커버리지 (신규 판정에는 영향 없음)
                if k + step < len(hist_months) and rng.random() < 0.55:
                    _one(codes[i], hist_months[k + step], str(rng.choice(brokers)), False)

    REP = pd.DataFrame(rows)
    if len(REP):
        REP["broker_id"] = [normalize_broker(b)[0] for b in REP["broker_raw"]]
        REP["broker_name"] = [normalize_broker(b)[1] for b in REP["broker_raw"]]
        REP["dedup_key"] = REP["report_uid"]
        REP = REP.sort_values("pub_date").reset_index(drop=True)

    # ── 텍스트 (렉시콘 어휘를 quality 에 비례해 섞는다) ────────────────────────────────────
    trows: List[dict] = []
    qmap = {codes[i]: float(quality[i]) for i in range(n_codes)}
    for r in REP.itertuples(index=False):
        q = qmap.get(str(r.code) if hasattr(r, "code") else str(r.stock_code), 0.0)
        npos = int(rng.poisson(1.5 + 3.5 * max(q, 0.0)))
        nneg = int(rng.poisson(1.5 + 2.0 * max(-q, 0.0)))
        toks = [str(rng.choice(pos_w)) for _ in range(npos)] + \
               [str(rng.choice(neg_w)) for _ in range(nneg)]
        rng.shuffle(toks)
        body = ("동사는 소형 부품 전문업체입니다. " +
                " ".join(f"{t} 관련 언급이 확인됩니다." for t in toks) +
                " 투자의견과 목표주가는 별도 표기합니다. " * 3)
        trows.append({"report_uid": r.report_uid, "code": r.stock_code, "pub_date": r.pub_date,
                      "sec_title": f"{r.stock_code} 합성 리포트",
                      "sec_headline": (toks[0] if toks else "커버리지 개시"),
                      "sec_body": body, "n_chars": len(body), "n_pages": 6,
                      "extract_ok": True, "extract_method": "synthetic"})
    TXT = pd.DataFrame(trows, columns=["report_uid", "code", "pub_date", "sec_title",
                                       "sec_headline", "sec_body", "n_chars", "n_pages",
                                       "extract_ok", "extract_method"])

    snapshots = pd.DataFrame(columns=["snap_date", "code", "market"])
    uni_obj = Universe(sec, snapshots, px_daily)

    return {"months": months, "codes": codes, "sec": sec, "px_daily": px_daily, "pxm": pxm,
            "mcap": mcap, "UNI": UNI, "REP": REP, "TXT": TXT, "uni_obj": uni_obj,
            "snapshots": snapshots, "quality": quality, "event_months": ev_months,
            "hist_months": hist_months}


def ncq_toy_sig(W: dict, rng, top_k: int = 8, oracle: bool = False,
                months: Optional[pd.DatetimeIndex] = None) -> pd.DataFrame:
    """계약검정용 합성 SIG (계약 §3 스키마 그대로).

    oracle=True 면 **미래수익을 그대로 신호로 심는다**(고의 누수). N11 이 이걸 쓴다.
    """
    pxm = W["pxm"]
    ms = list(months if months is not None else W["months"])
    parts = []
    for m in ms:
        g = pxm[(pxm["month"] == m)].copy()
        g = g[pd.to_numeric(g["adv20"], errors="coerce").notna()]
        if g.empty:
            continue
        if oracle:
            score = pd.to_numeric(g["fwd_ret"], errors="coerce")
        else:
            score = pd.Series(rng.normal(size=len(g)), index=g.index)
        g["event_score"] = score.astype(float)
        # ★ oracle 모드의 마지막 달들은 fwd_ret 이 전부 NaN 이다. nanmean/nanstd 를 그대로
        #   부르면 All-NaN slice 경고 뒤 NaN 이 나오고, 그 NaN 이 아래 나눗셈으로 새어든다.
        #   유한값 개수를 먼저 세고, 분모가 0/NaN 이면 z 를 NaN 으로 남긴다(0으로 채우지 않는다).
        sv = pd.to_numeric(score, errors="coerce").to_numpy(dtype=float)
        fin = sv[np.isfinite(sv)]
        mu = float(fin.mean()) if fin.size else np.nan
        sd = float(fin.std()) if fin.size > 1 else np.nan
        g["z"] = (score - mu) / (sd if (np.isfinite(sd) and sd > 0) else np.nan)
        g["pooled"] = False
        g["pool_n"] = int(len(g))
        g["rank_pct"] = score.rank(pct=True)
        thr = g["event_score"].rank(ascending=False, method="first")
        g["selected"] = thr <= top_k
        g["placebo"] = False
        g["sponsor_group"] = "ORGANIC_ONLY"
        g["event_type"] = "H1"
        parts.append(g[["month", "code", "event_score", "z", "pooled", "pool_n", "rank_pct",
                        "selected", "placebo", "sponsor_group", "event_type",
                        "exec_px", "adv20", "fwd_ret"]])
    if not parts:
        return pd.DataFrame(columns=["month", "code", "event_score", "z", "pooled", "pool_n",
                                     "rank_pct", "selected", "placebo", "sponsor_group",
                                     "event_type", "exec_px", "adv20", "fwd_ret"])
    return pd.concat(parts, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (A) 계약 자동검정 N1~N11 — 주석과 관례는 무효. 테스트로만 강제한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_CONTRACTS: List[dict] = []


def ncq_c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    """검정 1건. 예외는 '실패'로 흡수한다 — 검정기가 죽어서 검정이 생략되면 안 된다.
    fn 은 (통과여부, 한글 상세) 를 돌려준다. 통과여부가 None 이면 SKIP 으로 기록한다."""
    t0 = time.time()
    tb = ""
    try:
        ok, msg = fn()
    except Exception as e:                                          # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:220]}"
        tb = "\n".join(ncq_tail_tb(10))
    # ★ 판정값을 파이썬 bool/None 으로 못 박는다. 검정 함수가 numpy.bool_ 을 돌려주면
    #   동일성(identity) 비교가 양쪽 다 거짓이 되어, 표에는 '실패'로 찍히는데 실패 목록에는
    #   들어가지 않는 상태가 된다 — 위반이 조용히 통과하는 가장 나쁜 형태다.
    #   아래 집계도 동일성 비교 대신 `None 여부 + bool()` 로만 판단한다.
    ok = None if ok is None else bool(ok)
    NCQ_CONTRACTS.append({"id": cid, "name": name, "pass": ok, "msg": str(msg),
                          "sec": time.time() - t0, "tb": tb})
    if ok is None:
        NCQ_VERIFY_SKIPPED.append(f"{cid} {name}")
    return bool(ok) if ok is not None else True


def run_contract_tests(strict: bool = True) -> bool:
    """계약검정 N1~N11. 실데이터를 한 바이트도 받기 전에 전부 통과해야 한다."""
    LOG.banner("① 계약 자동검정 N1~N11",
               "PIT · 생존자편향 · 무기억성 · 동결 · 표본가드 · 코호트회계 · 체결앵커 · "
               "폐지처리 · 캐시무해 · 결정성 · 누수민감도")
    NCQ_CONTRACTS.clear()
    rng = np.random.default_rng(SEED)

    # ── N1. PIT 강제 ──────────────────────────────────────────────────────────────────────
    def n1():
        d = pd.DataFrame({"code": ["000010", "000010", "000020"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15",
                                                            "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 절단이 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "★knowledge_date > as_of 인 행이 새어나왔습니다 = 미래누수"
        # PIT 컬럼이 없는 테이블은 반드시 KeyError 로 거부돼야 한다(우회 경로를 두지 않는다)
        for bad, why in ((pd.DataFrame({"x": [1]}), "PIT 컬럼 전무"),
                         (pd.DataFrame({"x": [1], "event_date": [as_ts("2020-01-01")]}),
                          "knowledge_date 만 누락")):
            try:
                st.register("bad", bad)
                return False, f"★PIT 컬럼 없는 테이블({why}) 등록이 거부되지 않았습니다"
            except KeyError:
                pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 KeyError 로 등록 거부 확인"

    ncq_c("N1", "PIT 강제 (PITStore)", n1)

    # ── N2. 생존자편향 ────────────────────────────────────────────────────────────────────
    def n2():
        sec = pd.DataFrame({
            "code": ["000010", "000020", "000030"],
            "name": ["기존", "미래상장", "폐지"], "market": ["KOSPI"] * 3,
            "industry": ["화학"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"])})
        days = pd.bdate_range("2009-01-01", "2026-08-01")
        px = pd.DataFrame({"date": days, "code": "000010"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        a16 = u.at("2016-08-31")
        if "000020" in a16:
            return False, "★2016년 유니버스에 2025년 상장 종목이 들어 있습니다(미래 정보 유입)"
        if "000030" not in a16:
            return False, ("★2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다. "
                           "이게 정확히 생존자편향입니다 — 폐지 종목은 폐지 전까지 남아야 합니다")
        if "000030" in u.at("2020-01-31"):
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지 전 포함 · 폐지 후 제외 3분기 전부 정상"

    ncq_c("N2", "생존자편향 제거 (Universe)", n2)

    # ── N3. 신규 커버리지 판정의 무기억성 ─────────────────────────────────────────────────
    def n3():
        if not ncq_has("build_coverage_events"):
            return None, "build_coverage_events 미탑재 — SKIP"
        ms = pd.date_range("2016-01-31", "2024-12-31", freq="ME")
        t = as_ts("2022-06-30") + pd.offsets.MonthEnd(0)
        code = "000010"
        broker = "삼성증권"

        def _rep(dates: Sequence[str]) -> pd.DataFrame:
            rr = []
            for k, ds in enumerate(dates):
                d = as_ts(ds)
                uid = sha1_str("n3", code, ds, k)
                rr.append({"report_uid": uid, "source": "naver", "src_report_id": uid[:10],
                           "pub_date": d, "category": "company", "title": f"{code} 리포트",
                           "stock_code": code, "stock_name": "합성", "broker_raw": broker,
                           "broker_id": normalize_broker(broker)[0],
                           "broker_name": normalize_broker(broker)[1],
                           "analyst_raw": "애널00", "target_price": 10000.0, "opinion": "BUY",
                           "pdf_url": None, "detail_url": None, "is_sponsored": False,
                           "event_date": d, "knowledge_date": d})
            return pd.DataFrame(rr)

        U = pd.DataFrame({"month": ms, "code": code})
        U["mcap"] = 5.0e10
        U["adv20"] = 5.0e8
        U["mcap_rank"] = 1.0
        U["in_uni"] = True
        U["liq_pass"] = True
        U["excl"] = ""

        # ① t-30M 과 t 에만 리포트 → 갭 30M > L(24M) → t 는 '신규'여야 한다
        A = _rep(["2019-12-10", "2022-06-10"])
        # ② 중간(t-12M)에 한 건 더 → 갭 12M ≤ L → t 는 '신규가 아니'어야 한다
        B = _rep(["2019-12-10", "2021-06-10", "2022-06-10"])
        with ncq_tmp_vault("ncq_n3_"):
            EA = build_coverage_events(A, U, ms, as_ts("2016-01-31"), lookback_m=24, burnin_m=24)
            EB = build_coverage_events(B, U, ms, as_ts("2016-01-31"), lookback_m=24, burnin_m=24)

        def _at(E):
            if E is None or len(E) == 0:
                return None
            m = (as_ts_series(E["month"]) == t) & (E["code"].astype(str) == code)
            return E[m]

        ra, rb = _at(EA), _at(EB)
        if ra is None or len(ra) == 0:
            return False, (f"★갭 30M(>L=24M) 인데 {t:%Y-%m} 이 신규로 판정되지 않았습니다. "
                           f"룩백 창이 무기억성을 잃었거나 burn-in 이 과하게 잘라냈습니다")
        if str(ra["event_type"].iloc[0]) != "H1":
            return False, f"신규로는 잡혔으나 event_type 이 H1 이 아닙니다: {ra['event_type'].iloc[0]}"
        if rb is not None and len(rb) > 0:
            return False, (f"★t-12M 에 리포트가 있는데도 {t:%Y-%m} 이 신규로 판정됐습니다. "
                           f"L=24M 룩백이 실제로 적용되지 않고 있습니다 — 가짜 신규가 대량 발생합니다")
        return True, ("갭 30M → 신규(H1), 갭 12M → 비신규. 판정이 룩백 창 안의 사실에만 "
                      "의존함(무기억성) 확인")

    ncq_c("N3", "신규 커버리지 무기억성 (L=24M)", n3)

    # ── N4. 렉시콘·사전등록 동결 ──────────────────────────────────────────────────────────
    def n4():
        if not ncq_has("NCQ_LEXICON", "NCQ_LEXICON_SHA"):
            return None, "NCQ_LEXICON / NCQ_LEXICON_SHA 미탑재 (ncq_40_text) — SKIP"
        sha = str(globals()["NCQ_LEXICON_SHA"] or "")
        # ★ NCQ_LEXICON_SHA 는 freeze_configs 가 채운다(모듈 로드 시점 초기값은 "").
        #   아직 동결 전이라면 그것은 '계약 위반'이 아니라 '동결이 아직 안 돌았다'이다.
        #   여기서 임시 디렉터리에 한 번 동결한 뒤 그 값으로 검정한다 — 그러지 않으면
        #   run_contract_tests 를 단독으로 부를 때마다 N4 가 가짜 위반을 내고,
        #   strict=True 면 파이프라인이 시작도 못 하고 죽는다.
        #   freeze_configs 조차 없는데 SHA 가 비어 있으면 그때가 진짜 위반이다.
        if (not sha or len(sha) < 8) and ncq_has("freeze_configs"):
            d0 = tempfile.mkdtemp(prefix="ncq_n4pre_")
            try:
                freeze_configs(d0)
            finally:
                shutil.rmtree(d0, ignore_errors=True)
            sha = str(globals()["NCQ_LEXICON_SHA"] or "")
        lex = globals()["NCQ_LEXICON"]
        if not sha or len(sha) < 8:
            return False, (f"NCQ_LEXICON_SHA 가 비었거나 너무 짧습니다: {sha!r} "
                           f"(freeze_configs 미탑재 — 동결 SHA 를 만들 경로가 없습니다)")

        # ① 결정성: freeze_configs 가 있으면 그 경로로 두 번 계산해 동일한지 본다
        if ncq_has("freeze_configs"):
            d1, d2 = tempfile.mkdtemp(prefix="ncq_n4a_"), tempfile.mkdtemp(prefix="ncq_n4b_")
            try:
                l1, s1, p1, ps1 = freeze_configs(d1)
                l2, s2, p2, ps2 = freeze_configs(d2)
            finally:
                shutil.rmtree(d1, ignore_errors=True)
                shutil.rmtree(d2, ignore_errors=True)
            if s1 != s2 or ps1 != ps2:
                return False, (f"★freeze_configs 가 호출마다 다른 SHA 를 냅니다 "
                               f"(lexicon {s1[:10]} vs {s2[:10]}). 동결이 성립하지 않습니다")
            if s1 != sha:
                return False, (f"★NCQ_LEXICON_SHA({sha[:12]}) 와 freeze_configs 재계산값"
                               f"({s1[:12]})이 다릅니다. 매니페스트의 SHA 가 실제 렉시콘을 "
                               f"가리키지 않습니다")
            ok_prereg = (not ncq_has("NCQ_PREREG_SHA")) or ps1 == str(globals()["NCQ_PREREG_SHA"])
            if not ok_prereg:
                return False, "NCQ_PREREG_SHA 가 freeze_configs 재계산값과 다릅니다"
            return True, (f"freeze_configs 2회 재계산 동일 · 전역 SHA 일치 "
                          f"(lex {s1[:10]} · prereg {ps1[:10]})")

        # ② freeze_configs 가 없으면 표준 정규화 후보들로 대조한다
        blob = json.dumps(lex, ensure_ascii=False, sort_keys=True, default=str)
        cands = {
            "json.sort_keys": hashlib.sha1(blob.encode("utf-8")).hexdigest(),
            "json.sort_keys.indent2": hashlib.sha1(
                json.dumps(lex, ensure_ascii=False, sort_keys=True, indent=2,
                           default=str).encode("utf-8")).hexdigest(),
            "sha1_str": sha1_str(blob),
            "sha256.sort_keys": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        }
        hit = [k for k, v in cands.items() if v[:len(sha)] == sha]
        if not hit:
            return False, ("★NCQ_LEXICON_SHA 가 어떤 표준 정규화로도 렉시콘 내용과 일치하지 "
                           "않습니다. 동결 SHA 가 내용을 증명하지 못하면 사후수정을 막을 수 없습니다")
        # 내용을 한 글자 바꾸면 SHA 가 변해야 한다(민감도)
        mut = json.loads(json.dumps(lex, ensure_ascii=False, default=str))
        mut["__ncq_probe__"] = "x"
        if hashlib.sha1(json.dumps(mut, ensure_ascii=False, sort_keys=True,
                                   default=str).encode("utf-8")).hexdigest()[:len(sha)] == sha:
            return False, "★렉시콘을 변경했는데도 SHA 가 그대로입니다(해시가 내용을 안 봅니다)"
        return True, f"내용해시 일치({hit[0]}) · 재계산 동일 · 변경 시 SHA 변동 확인"

    ncq_c("N4", "렉시콘·사전등록 동결(SHA)", n4)

    # ── N5. 횡단면 z 의 표본 가드 ─────────────────────────────────────────────────────────
    def n5():
        if not ncq_has("build_signal_panel"):
            return None, "build_signal_panel 미탑재 (ncq_40_text) — SKIP"
        W = ncq_make_synthetic(n_codes=40, n_months=30, seed=SEED)
        ms = W["months"][-8:-1]                      # fwd_ret 이 존재하는 구간만
        codes = W["codes"]
        big, small = list(ms[:-1]), [ms[-1]]
        ev_rows, sc_rows = [], []
        k = 0
        for m in list(big) + list(small):
            n_ev = 8 if m in big else 2              # 마지막 달만 표본 부족(<NCQ_ZPOOL_MIN_N)
            for j in range(n_ev):
                c = codes[(k + j) % len(codes)]
                uid = sha1_str("n5", str(m.date()), c)
                ev_rows.append({"month": m, "code": c, "event_type": "H1", "n_reports": 1,
                                "n_brokers": 1, "sources": "naver", "broker_ids": "b1",
                                "sponsor_group": "ORGANIC_ONLY", "report_uids": uid})
                sc_rows.append({"report_uid": uid, "code": c, "month": m,
                                "doc_raw": float(rng.normal()), "doc_score": float(rng.normal()),
                                "n_chars": 900, "g_A": 1.0, "g_B": 0.0, "g_C": 1.0,
                                "g_D": 0.0, "g_H": 0.0, "g_N": 0.0})
            k += 3
        EV, SCORE = pd.DataFrame(ev_rows), pd.DataFrame(sc_rows)
        with ncq_tmp_vault("ncq_n5_"):
            SIG = build_signal_panel(SCORE, EV, W["UNI"], W["pxm"], W["months"])
        if SIG is None or len(SIG) == 0:
            return False, "SIG 가 0행입니다 — 표본 가드 이전에 신호 산출 자체가 실패했습니다"
        for c in ("pooled", "pool_n"):
            if c not in SIG.columns:
                return False, f"★SIG 에 '{c}' 컬럼이 없습니다. 계약 §3 SIG 스키마 위반입니다"
        sm = SIG[as_ts_series(SIG["month"]) == small[0]]
        bg = SIG[as_ts_series(SIG["month"]).isin(list(big))]
        if len(sm) == 0:
            return False, f"표본 부족 달({small[0]:%Y-%m}) 의 신호가 통째로 사라졌습니다"
        if not bool(sm["pooled"].astype(bool).all()):
            return False, (f"★이벤트 {len(sm)}건(< {NCQ_ZPOOL_MIN_N}) 인 달인데 pooled=False 입니다. "
                           f"표본 2건으로 계산한 z 는 의미가 없습니다")
        pn = pd.to_numeric(sm["pool_n"], errors="coerce")
        if pn.isna().all() or float(pn.max()) <= len(sm):
            return False, (f"pool_n 이 기록되지 않았거나(결측) 풀이 확장되지 않았습니다 "
                           f"(pool_n={ncq_v_num(pn.max())}, 당월 {len(sm)}건)")
        if len(bg) and bool(bg["pooled"].astype(bool).all()):
            return False, "이벤트 8건인 달까지 pooled 로 넘어갔습니다 — 가드가 과하게 발동합니다"
        return True, (f"이벤트 {len(sm)}건 달 → pooled=True · pool_n={ncq_v_num(pn.max(),'int')} 기록, "
                      f"8건 달은 당월 z 유지 확인")

    ncq_c("N5", "횡단면 z 표본 가드 (pooled/pool_n)", n5)

    # ── N6. 오버랩 코호트 회계 ────────────────────────────────────────────────────────────
    def n6():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        H = int(NCQ_HOLD_MONTHS)
        W = ncq_make_synthetic(n_codes=40, n_months=H * 3, seed=SEED)
        SIG = ncq_toy_sig(W, np.random.default_rng(SEED + 1), top_k=6)
        with ncq_tmp_vault("ncq_n6_"):
            BT = run_overlap_backtest(SIG, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=H, label="N6")
        Hd = BT.get("holdings") if isinstance(BT, dict) else None
        if Hd is None or len(Hd) == 0:
            return False, "holdings 가 비었습니다 — 코호트 회계를 검증할 수 없습니다"
        if "cohort" not in Hd.columns or "weight" not in Hd.columns:
            return False, "holdings 에 cohort/weight 컬럼이 없습니다 (계약 §3 BT 스키마 위반)"
        g = Hd.groupby("month", observed=True)
        nc = g["cohort"].nunique()
        ws = g["weight"].sum()
        bad_c = nc[nc > H]
        bad_w = ws[ws > 1.0 + 1e-6]
        if len(bad_c):
            return False, (f"★활성 코호트가 H={H} 를 초과한 달 {len(bad_c)}개 "
                           f"(최대 {int(bad_c.max())}개). 오버랩 회계가 코호트를 청산하지 "
                           f"않고 있습니다 = 레버리지 자동 발생")
        if len(bad_w):
            return False, (f"★가중치 합이 1을 넘는 달 {len(bad_w)}개 (최대 {float(bad_w.max()):.4f}). "
                           f"1/H 배분이 깨졌습니다 — 성과가 그만큼 부풀려집니다")
        return True, (f"전 {int(nc.size)}개월에서 활성 코호트 ≤ {H} (최대 {int(nc.max())}) · "
                      f"가중치 합 ≤ 1 (최대 {float(ws.max()):.4f})")

    ncq_c("N6", "오버랩 코호트 회계 (≤H · Σw≤1)", n6)

    # ── N7. 체결 앵커 ─────────────────────────────────────────────────────────────────────
    def n7():
        days = pd.bdate_range("2022-01-03", "2023-06-30")
        r = np.random.default_rng(SEED + 7)
        parts = []
        for c in ("000010", "000020"):
            p = 10000 * np.exp(np.cumsum(r.normal(0.0003, 0.02, len(days))))
            parts.append(pd.DataFrame({
                "code": c, "date": days, "open": p * (1 + r.normal(0, 0.006, len(days))),
                "high": p * 1.01, "low": p * 0.99, "close": p,
                "volume": 100000.0, "amount": p * 100000.0, "src": "synthetic"}))
        px = pd.concat(parts, ignore_index=True)
        ms = pd.date_range("2022-02-28", "2023-05-31", freq="ME")
        panel = build_price_panel(px, ms)
        M, D = panel["monthly"], panel["daily"]
        if M.empty:
            return False, "월간 패널이 비었습니다"
        nn = M[M["next_date"].notna()]
        if len(nn) == 0:
            return False, "next_date 가 한 행도 채워지지 않았습니다 — 체결 앵커가 없습니다"
        if not bool((nn["next_date"] > nn["signal_date"]).all()):
            k = int((nn["next_date"] <= nn["signal_date"]).sum())
            return False, (f"★next_date <= signal_date 인 행 {k}건. 신호 산출일 당일(또는 이전) "
                           f"가격으로 체결하고 있습니다 = 명백한 미래누수")
        # exec_px 가 정말 '익영업일 시가'에서 오는지 원본 일봉과 대조한다
        key = D[["code", "date", "open"]].rename(columns={"date": "next_date",
                                                          "open": "open_next"})
        chk = nn.merge(key, on=["code", "next_date"], how="left")
        same = np.isclose(pd.to_numeric(chk["exec_px"], errors="coerce"),
                          pd.to_numeric(chk["open_next"], errors="coerce"),
                          rtol=1e-9, atol=1e-9, equal_nan=False)
        if len(chk) == 0:
            return False, "체결가 대조표가 비었습니다 — 일봉과 next_date 가 하나도 매칭되지 않습니다"
        frac = float(np.mean(same)) if len(chk) else 0.0
        if frac < 0.95:
            return False, (f"★exec_px 가 익영업일 시가와 일치하는 비율이 {100*frac:.1f}% 뿐입니다. "
                           f"종가 체결로 폴백한 행이 과다합니다(당일 종가 체결은 누수)")
        eq_close = float(np.mean(np.isclose(pd.to_numeric(chk["exec_px"], errors="coerce"),
                                            pd.to_numeric(chk["close"], errors="coerce"))))
        if eq_close > 0.5:
            return False, f"★exec_px 의 {100*eq_close:.0f}% 가 당월 종가와 같습니다 — 당일 종가 체결"
        return True, (f"월말 신호 → 익영업일 시가 체결 확인 (next_date>signal_date 100% · "
                      f"exec_px=익일시가 {100*frac:.1f}%)")

    ncq_c("N7", "체결 앵커 (월말 신호 → 익영업일 시가)", n7)

    # ── N8. 상장폐지 처리 ─────────────────────────────────────────────────────────────────
    def n8():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        hair = float(globals().get("NCQ_DELIST_HAIRCUT", -0.50))
        W = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED + 8)
        pxm, ms = W["pxm"].copy(), W["months"]

        # ★ 시드 운에 맡기지 않고 폐지를 '직접 만든다'. 폐지 종목이 없어 SKIP 되면
        #   이 계약은 사실상 검정되지 않은 채로 통과 표시가 남는다 — 그게 가장 나쁘다.
        alive = pxm.groupby("code", observed=True)["month"].nunique()
        alive = alive[alive >= len(ms) - 1]
        if len(alive) == 0:
            return False, "합성 세계에 전 구간 거래된 종목이 없습니다(가격 생성 확인 필요)"
        code = str(sorted(alive.index.astype(str))[0])
        di = len(ms) // 2
        dm = as_ts(ms[di])
        sec = W["sec"].copy()
        sec.loc[sec["code"].astype(str) == code, "delisting_date"] = dm
        # 폐지 이후엔 가격 자체가 없다 — 엔진이 '가격이 없어서 조용히 사라지는' 길을 못 타게 한다
        pxm = pxm[~((pxm["code"].astype(str) == code) & (as_ts_series(pxm["month"]) > dm))]
        px_daily = W["px_daily"]
        px_daily = px_daily[~((px_daily["code"].astype(str) == code) &
                              (as_ts_series(px_daily["date"]) > dm))]
        uni_obj = Universe(sec, W["snapshots"], px_daily)

        enter = as_ts(ms[max(0, di - 3)])
        SIG = ncq_toy_sig(W, np.random.default_rng(SEED + 9), top_k=6)
        SIG["selected"] = False
        sel = (as_ts_series(SIG["month"]) == enter)
        others = SIG.index[sel & (SIG["code"].astype(str) != code)][:4]
        SIG.loc[sel & (SIG["code"].astype(str) == code), "selected"] = True
        SIG.loc[others, "selected"] = True
        if not bool(SIG.loc[sel & (SIG["code"].astype(str) == code), "selected"].any()):
            return False, f"폐지 예정 종목 {code} 이 {enter:%Y-%m} 신호 패널에 없습니다"
        with ncq_tmp_vault("ncq_n8_"):
            BT = run_overlap_backtest(SIG, pxm, sec, uni_obj, ms, hold_months=12,
                                      cost_roundtrip=0.0, label="N8")
        Hd = BT.get("holdings") if isinstance(BT, dict) else None
        if Hd is None or len(Hd) == 0:
            return False, "holdings 가 비었습니다"
        h = Hd[Hd["code"].astype(str) == code].copy()
        if len(h) == 0:
            return False, f"폐지 종목 {code} 이 한 번도 보유되지 않았습니다(선정 로직 확인)"
        h["month"] = as_ts_series(h["month"])
        h = h.sort_values("month")
        # ★ 어느 '인덱스'에 손실이 찍혀야 하는가 — 수익률 인덱싱 규약에서 유도된다.
        #   fwd_ret(m) = exec_px(m)→exec_px(m+1) 이고 exec_px(m) 은 월 m 말일 다음 영업일
        #   시가이므로, **월 m 라벨의 수익은 달력 m+1 을 덮는다.** 따라서 달력 D 월에 일어난
        #   폐지는 fwd_ret(D-1) 창 안에서 실현된다. 라벨 D 에 찍으면 종목이 이미 사라진 달의
        #   수익으로 계상되고, 백테스트 창이 D 에서 끝나면 손실이 아예 사라진다(절단 누락).
        _mlist = [as_ts(x) for x in ms]
        _di = _mlist.index(dm)
        exp_m = _mlist[max(0, _di - 1)]
        at = h[h["month"] == exp_m]
        if len(at) == 0:
            return False, (f"★폐지({dm:%Y-%m})를 포함하는 선도수익 창 {exp_m:%Y-%m} 에 해당 종목의 "
                           f"보유 기록이 없습니다. 폐지 손실을 계상하지 않고 조용히 사라지면 "
                           f"성과가 부풀려집니다")
        got = float(pd.to_numeric(at["ret"], errors="coerce").iloc[0])
        if not np.isfinite(got) or abs(got - hair) > 1e-6:
            return False, (f"★폐지 창({exp_m:%Y-%m}) 수익이 {ncq_v_num(got,'pct')} 입니다. 명세 §10 은 "
                           f"{ncq_v_num(hair,'pct')}(폐지 직전가 -50% 후 현금화)를 요구합니다")
        # 해어컷은 정확히 한 번만 — 두 번 찍히면 손실이 이중 계상된다
        _n_hair = int((np.abs(pd.to_numeric(h["ret"], errors="coerce").to_numpy() - hair) < 1e-6).sum())
        if _n_hair != 1:
            return False, f"★폐지 해어컷이 {_n_hair}회 적용됐습니다(정확히 1회여야 합니다)"
        after = h[h["month"] > exp_m]
        # ★ 전부 NaN 이면 np.nanmax 가 All-NaN slice 경고와 함께 NaN 을 돌려주고,
        #   NaN > 1e-9 는 False 라 검정이 조용히 통과한다. 유한값만 남겨서 비교한다.
        av = pd.to_numeric(after["ret"], errors="coerce").to_numpy(dtype=float) \
            if len(after) else np.array([], dtype=float)
        av = av[np.isfinite(av)]
        if av.size and float(np.max(np.abs(av))) > 1e-9:
            return False, ("폐지 이후에도 해당 종목이 0 이 아닌 수익을 내고 있습니다 — "
                           "현금화되지 않았습니다")
        return True, (f"{code} 폐지월 {dm:%Y-%m} 수익 {ncq_v_num(got,'pct')} = 명세값 · "
                      f"이후 {len(after)}개월 현금(0%) 확인")

    ncq_c("N8", "상장폐지 처리 (-50% 후 현금화)", n8)

    # ── N9. 캐시 무해성 ───────────────────────────────────────────────────────────────────
    def n9():
        banned = re.compile(r"^(delete|del|remove|rm|drop|purge|clear|wipe|unlink|truncate|"
                            r"erase|reset|prune)", re.I)
        pub = [n for n in dir(Vault) if not n.startswith("_") and banned.match(n)]
        if pub:
            return False, (f"★Vault 에 삭제 계열 공개 메서드가 있습니다: {pub}. "
                           f"절대 1원칙은 '약속'이 아니라 '구조'로 지켜야 합니다 — "
                           f"삭제 API 는 존재 자체가 위험입니다")
        tmp = tempfile.mkdtemp(prefix="ncq_n9_")
        try:
            v = Vault(tmp, "VERIFY")
            d1 = pd.DataFrame({"a": [1, 2, 3]})
            d2 = pd.DataFrame({"a": [9, 9, 9, 9]})
            p1 = v.put_table("ncq_probe", d1, scope="shared")
            if not p1 or not os.path.exists(p1):
                return False, "put_table 이 파일을 만들지 못했습니다"
            p2 = v.put_table("ncq_probe", d2, scope="shared")
            bdir = os.path.join(v.ns["shared"], "index", "_backup")
            baks = [f for f in os.listdir(bdir)] if os.path.isdir(bdir) else []
            hit = [f for f in baks if f.startswith("ncq_probe.")]
            if not hit:
                return False, ("★기존 테이블을 백업 없이 교체했습니다. 실행 중 중단되면 "
                               "사용자의 기존 캐시가 그대로 소실됩니다")
            back = read_parquet_safe(os.path.join(bdir, hit[0]))
            if back is None or len(back) != len(d1):
                return False, f"백업 파일이 이전 내용을 담고 있지 않습니다({hit[0]})"
            cur = read_parquet_safe(p2 or p1)
            if cur is None or len(cur) != len(d2):
                return False, "교체 후 현재 파일이 새 내용이 아닙니다"
            return True, (f"삭제 계열 공개 API 없음 · put_table 재기록 시 백업 생성 확인"
                          f"({hit[0]} · {len(back)}행 보존)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    ncq_c("N9", "캐시 무해성 (삭제 API 부재 · 백업 후 교체)", n9)

    # ── N10. 결정성 (C8) ──────────────────────────────────────────────────────────────────
    def n10():
        A = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED)
        B = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED)
        for key in ("px_daily", "pxm", "REP"):
            a, b = A[key], B[key]
            if a.shape != b.shape:
                return False, f"★같은 시드인데 {key} 의 shape 가 다릅니다: {a.shape} vs {b.shape}"
            ha = sha1_str(key, pd.util.hash_pandas_object(a.reset_index(drop=True),
                                                          index=False).sum())
            hb = sha1_str(key, pd.util.hash_pandas_object(b.reset_index(drop=True),
                                                          index=False).sum())
            if ha != hb:
                return False, f"★같은 시드인데 {key} 내용 해시가 다릅니다 — 결정성 붕괴"
        detail = "합성 데이터 3종(px_daily·pxm·REP) 해시 동일"
        if ncq_has("run_overlap_backtest"):
            S1 = ncq_toy_sig(A, np.random.default_rng(SEED + 3), top_k=5)
            S2 = ncq_toy_sig(B, np.random.default_rng(SEED + 3), top_k=5)
            with ncq_tmp_vault("ncq_n10_"):
                B1 = run_overlap_backtest(S1, A["pxm"], A["sec"], A["uni_obj"], A["months"],
                                          hold_months=6, label="N10a")
                B2 = run_overlap_backtest(S2, B["pxm"], B["sec"], B["uni_obj"], B["months"],
                                          hold_months=6, label="N10b")
            r1 = pd.to_numeric(B1["returns"]["ret"], errors="coerce").to_numpy()
            r2 = pd.to_numeric(B2["returns"]["ret"], errors="coerce").to_numpy()
            if r1.shape != r2.shape or not np.allclose(np.nan_to_num(r1, nan=-9.0),
                                                       np.nan_to_num(r2, nan=-9.0),
                                                       rtol=0, atol=0):
                return False, "★같은 시드로 두 번 돌린 백테스트 월수익이 다릅니다 — 결정성 붕괴"
            detail += f" · 백테스트 월수익 {len(r1)}개월 완전 일치"
        else:
            NCQ_VERIFY_SKIPPED.append("N10 백테스트 결정성(run_overlap_backtest 미탑재)")
            detail += " · 백테스트 부분은 SKIP(run_overlap_backtest 미탑재)"
        return True, detail

    ncq_c("N10", "결정성 (동일 SEED → 동일 결과)", n10)

    # ── N11. 미래누수 하네스 민감도 ───────────────────────────────────────────────────────
    def n11():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        W = ncq_make_synthetic(n_codes=60, n_months=36, seed=SEED + 11)
        base = ncq_toy_sig(W, np.random.default_rng(SEED + 12), top_k=8, oracle=False)
        ora = ncq_toy_sig(W, np.random.default_rng(SEED + 12), top_k=8, oracle=True)
        with ncq_tmp_vault("ncq_n11_"):
            Bb = run_overlap_backtest(base, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=1, cost_roundtrip=0.0, adv_cap=False,
                                      label="N11_base")
            Bo = run_overlap_backtest(ora, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=1, cost_roundtrip=0.0, adv_cap=False,
                                      label="N11_oracle")

        def _cum(BT):
            s = pd.to_numeric(BT["returns"]["ret"], errors="coerce").fillna(0.0)
            return float((1.0 + s).prod() - 1.0), float(s.mean())

        cb, mb = _cum(Bb)
        co, mo = _cum(Bo)
        # ★ 월평균(mo/mb)까지 유한성을 확인한다. 수익률 시계열이 0행이면 mo 가 NaN 이 되는데,
        #   아래 `mo <= mb + 0.002` 는 NaN 에서 False 라 누수 민감도 검정이 그대로 '통과'한다.
        if not all(np.isfinite(x) for x in (co, cb, mo, mb)):
            return False, ("누적/월평균 수익이 계산되지 않았습니다(수익률 시계열이 비었거나 "
                           "전부 결측입니다 — 하네스 민감도를 판정할 수 없습니다)")
        n_pos = int(pd.to_numeric(Bo["returns"].get("n", pd.Series(dtype=float)),
                                  errors="coerce").fillna(0).sum())
        if n_pos <= 0:
            return False, ("오라클 백테스트에서 포지션이 한 건도 잡히지 않았습니다. "
                           "'하네스 둔감'이 아니라 '게이트가 전부 막았다'는 뜻이므로 "
                           "선정 게이트를 먼저 확인해야 합니다")
        if mo <= mb + 0.002:
            return False, (f"★미래수익을 그대로 신호로 심었는데도 성과가 개선되지 않습니다 "
                           f"(월평균 오라클 {ncq_v_num(mo,'pctp')} vs 기준 {ncq_v_num(mb,'pctp')}). "
                           f"백테스트 엔진이 신호에 반응하지 못하는 상태이므로 "
                           f"이 빌드의 모든 성과 수치는 무효입니다 — 체결·정렬·수익계산을 보세요")
        return True, (f"고의 누수 주입 시 월평균 {ncq_v_num(mb,'pctp')} → {ncq_v_num(mo,'pctp')} "
                      f"(누적 {ncq_v_num(cb,'pct')} → {ncq_v_num(co,'pct')}). 하네스가 누수에 반응함")

    ncq_c("N11", "미래누수 하네스 민감도", n11)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = []
    for r in NCQ_CONTRACTS:
        icon = "→ SKIP" if r["pass"] is None else ("✔ 통과" if bool(r["pass"]) else "✘ 실패")
        rows.append([r["id"], _trunc(r["name"], 34), icon, f"{r['sec']:.2f}s",
                     _trunc(r["msg"], 78)])
    LOG.table(rows, ["계약", "내용", "판정", "소요", "상세"], ["l", "l", "c", "r", "l"], maxw=82,
              title="계약 자동검정 N1~N11 (협상 대상이 아님 — 우회하지 말고 원인을 고치십시오)")

    failed = [r for r in NCQ_CONTRACTS if r["pass"] is not None and not bool(r["pass"])]
    skipped = [r for r in NCQ_CONTRACTS if r["pass"] is None]
    if skipped:
        LOG.warn(f"스파인 미탑재로 건너뛴 계약 {len(skipped)}건: " +
                 ", ".join(r["id"] for r in skipped) +
                 " — 해당 모듈이 조립되면 반드시 다시 돌려야 합니다.")
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        for r in failed[:3]:
            if r.get("tb"):
                LOG.banner(f"✘ 계약 실패: [{r['id']}] {r['name']}", _trunc(r["msg"], 96))
                for ln in str(r["tb"]).split("\n"):
                    _safe_print("   " + ln)
        if strict:
            raise KillCriteria(
                f"계약 위반 {len(failed)}건으로 파이프라인을 중단합니다. "
                f"이 규칙들은 결과의 유효성 그 자체이므로, 임계를 낮춰 통과시키지 말고 "
                f"원인을 고쳐야 합니다.")
        return False
    LOG.ok(f"계약 {len(NCQ_CONTRACTS) - len(skipped)}건 통과"
           + (f" (SKIP {len(skipped)}건)" if skipped else "") + ".")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (B) 네트워크 카나리 C1~C7 (명세 §13.3) — 유일하게 네트워크가 필요한 계층
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_CANARY: "OrderedDict[str, dict]" = OrderedDict()


def ncq_canary(cid: str, name: str, fn: Callable[[], Tuple[bool, str]],
               blocking: bool = False) -> dict:
    """카나리 1건. **예외를 절대 밖으로 내지 않는다** — 한 소스가 죽었다고 실행이 죽으면 안 된다."""
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:                                          # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
    rec = {"id": cid, "name": name, "ok": (None if ok is None else bool(ok)),
           "detail": str(detail), "sec": round(time.time() - t0, 2),
           "blocking": bool(blocking), "skipped": ok is None}
    NCQ_CANARY[cid] = rec
    return rec


def run_canaries(strict: bool = True) -> dict:
    """C1~C7. 실수집을 시작하기 전에 '외부 소스가 지금 살아 있는가'를 5분 안에 확인한다.

    ★ C3(36개월 전 아카이브)만 차단성이다. 과거 아카이브에 못 닿으면 10년 백테스트가
      성립하지 않으므로 즉시 멈추고 사용자에게 보고한다. 단 드라이브 캐시에 그 구간
      리포트가 이미 충분하면 '캐시로 대체 가능'으로 통과시킨다(캐시 우선 원칙).
    """
    LOG.banner("③ 네트워크 카나리 C1~C7 (명세 §13.3)",
               "외부 소스 가용성 사전 점검 — 여기서 막는 것이 몇 시간 뒤 P1 에서 죽는 것보다 싸다")
    NCQ_CANARY.clear()

    if RUN_MODE == "SMOKE":
        for cid, nm in (("C1", "IR협의회 최근 인덱스"), ("C2", "네이버 리서치 최근 인덱스"),
                        ("C3", "네이버 리서치 36개월 전 인덱스"), ("C4", "한경컨센서스 접근"),
                        ("C5", "PDF 다운로드·텍스트 추출"), ("C6", "FDR 유니버스 조회"),
                        ("C7", "pykrx 가격 조회")):
            NCQ_CANARY[cid] = {"id": cid, "name": nm, "ok": None, "skipped": True,
                               "detail": "RUN_MODE='SMOKE' — 네트워크를 쓰지 않습니다",
                               "sec": 0.0, "blocking": False}
        LOG.table([[r["id"], _trunc(r["name"], 30), "→ SKIP", r["detail"]]
                   for r in NCQ_CANARY.values()],
                  ["카나리", "대상", "판정", "상세"], ["l", "l", "c", "l"], maxw=70,
                  title="카나리 — SMOKE 모드에서는 전부 건너뜁니다")
        LOG.info("실데이터가 필요하면 RUN_MODE='FULL' 로 바꾸고 다시 실행하세요.")
        out = dict(NCQ_CANARY)
        out["_summary"] = {"ok": True, "skipped": True, "blocking_failed": []}
        return out

    today = as_ts(_dt.date.today()) or as_ts(BACKTEST_END)
    m_recent_hi = today
    m_recent_lo = (today - pd.DateOffset(days=31)).normalize()
    d36 = (today - pd.DateOffset(months=36)).normalize()
    m36_lo = d36.replace(day=1)
    m36_hi = (m36_lo + pd.offsets.MonthEnd(0))
    pdf_urls: List[str] = []

    def _collect_pdf_urls(d):
        try:
            if d is not None and len(d) and "pdf_url" in d.columns:
                for u in d["pdf_url"].dropna().astype(str).tolist():
                    if u.lower().endswith(".pdf") or "downpdf" in u.lower():
                        pdf_urls.append(u)
        except Exception:
            pass

    # ── C1. IR협의회 ──────────────────────────────────────────────────────────────────────
    def c1():
        if ncq_has("ncq_irs_fetch_index"):
            d = globals()["ncq_irs_fetch_index"](m_recent_lo.strftime("%Y-%m-%d"),
                                                 m_recent_hi.strftime("%Y-%m-%d"))
        elif ncq_has("ncq_irs_collect"):
            d = ncq_irs_collect(m_recent_lo.strftime("%Y-%m-%d"),
                                m_recent_hi.strftime("%Y-%m-%d"), max_pages=1)
        else:
            return None, "IR협의회 수집 함수 미탑재 — SKIP"
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            return False, ("IR협의회 인덱스 0건. 스폰서 리포트 소스가 빠지므로 "
                           "SPONSORED/ORGANIC 분리 검정(P3)의 표본이 줄어듭니다. "
                           "주가설 H1 자체는 ORGANIC_ONLY 로 그대로 검정됩니다")
        return True, f"최근 1개월 인덱스 1페이지 {n:,}건"

    ncq_canary("C1", "IR협의회 최근 인덱스", c1)

    # ── C2. 네이버 최근 ───────────────────────────────────────────────────────────────────
    def c2():
        if not ncq_has("naver_collect"):
            return None, "naver_collect 미탑재 — SKIP"
        d = naver_collect(m_recent_lo.strftime("%Y-%m-%d"), m_recent_hi.strftime("%Y-%m-%d"),
                          cats=("company",), max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            return False, ("네이버 리서치 최근 인덱스가 0건입니다. 주 소스가 죽으면 "
                           "이 전략의 인덱스 수집이 성립하지 않습니다 — 차단(403)/구조 변경을 "
                           "먼저 확인하세요")
        nc = int(d["stock_code"].notna().sum()) if "stock_code" in d.columns else -1
        return True, f"최근 1개월 1페이지 {n:,}건 (종목코드 보유 {ncq_v_num(nc,'int')})"

    ncq_canary("C2", "네이버 리서치 최근 인덱스", c2)

    # ── C3. ★네이버 36개월 전 (차단성) ───────────────────────────────────────────────────
    def _cached_reports_in(lo: pd.Timestamp, hi: pd.Timestamp) -> int:
        """드라이브 캐시에 해당 구간 리포트가 몇 건이나 이미 있는가."""
        V = globals().get("VAULT")
        if V is None:
            return -1
        names = ["research_report_master"]
        for y in {lo.year, hi.year}:
            for src in ("naver", "hankyung", "irs"):
                names.append(f"report_index_{src}_{y}")
        best = 0
        for nm in names:
            try:
                d = V.get_table(nm, scope="shared")
            except Exception:
                d = None
            if d is None or len(d) == 0 or "pub_date" not in d.columns:
                continue
            try:
                t = as_ts_series(d["pub_date"])
                best = max(best, int(((t >= lo) & (t <= hi)).sum()))
            except Exception:
                continue
        return best

    def c3():
        cached_n = _cached_reports_in(m36_lo, m36_hi)
        if RUN_MODE == "CACHED":
            return True, (f"RUN_MODE='CACHED' — 과거 아카이브 접근을 시도하지 않고 "
                          f"드라이브 캐시로 대체합니다 (해당 월 캐시 {ncq_v_num(cached_n,'int')}건)")
        if not ncq_has("naver_collect"):
            return None, "naver_collect 미탑재 — SKIP"
        d = naver_collect(m36_lo.strftime("%Y-%m-%d"), m36_hi.strftime("%Y-%m-%d"),
                          cats=("company",), max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n > 0:
            return True, f"{m36_lo:%Y-%m} 인덱스 1페이지 {n:,}건 — 과거 아카이브 접근 가능"
        if cached_n >= 30:
            LOG.warn(f"★C3: 네이버 {m36_lo:%Y-%m} 아카이브에 직접 닿지 못했지만, 드라이브 캐시에 "
                     f"해당 월 리포트가 {cached_n:,}건 있어 '캐시로 대체 가능'으로 통과시킵니다. "
                     f"캐시 우선 원칙에 따른 판정이며, 캐시가 없는 구간은 완결성 진단에서 "
                     f"결손으로 잡혀 백테스트 시작월이 뒤로 밀립니다.")
            return True, (f"직접 접근 실패 · 드라이브 캐시 {cached_n:,}건으로 대체 가능 "
                          f"(캐시 우선 원칙)")
        return False, (f"★{m36_lo:%Y-%m} 인덱스에 접근하지 못했고(0건) 드라이브 캐시에도 "
                       f"{ncq_v_num(cached_n,'int')}건뿐입니다. 네이버 리서치의 과거 "
                       f"페이지네이션 깊이 제한이 가장 흔한 원인입니다. 이 상태로는 10년 "
                       f"백테스트가 성립하지 않습니다")

    ncq_canary("C3", "네이버 리서치 36개월 전 인덱스", c3, blocking=True)

    # ── C4. 한경컨센서스 (실패 예상 — 조용히 degrade) ─────────────────────────────────────
    def c4():
        if "hankyung" not in list(RESEARCH_SOURCES):
            return None, "RESEARCH_SOURCES 에 hankyung 이 없습니다 — SKIP"
        if not ncq_has("hankyung_collect"):
            return None, "hankyung_collect 미탑재 — SKIP"
        d = hankyung_collect(m_recent_lo.strftime("%Y-%m-%d"), m_recent_hi.strftime("%Y-%m-%d"),
                             max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            if ncq_has("degrade"):
                try:
                    degrade("L1", "카나리 C4 실패 — 한경컨센서스 접근 불가")
                except Exception:                                    # noqa
                    pass
            return False, ("접근 불가 → 열화 L1(한경 소스 드롭) 적용. 명세 §2.1 상 한경 없이도 "
                           "전략은 성립합니다(애널리스트 원장 품질만 낮아집니다)")
        return True, f"최근 1개월 1페이지 {n:,}건 (작성자·적정가격 직접 제공 소스)"

    ncq_canary("C4", "한경컨센서스 접근", c4)

    # ── C5. PDF 1건 다운로드 + 텍스트 추출 ────────────────────────────────────────────────
    def c5():
        if not ncq_has("pdf_text"):
            return None, "pdf_text 미탑재 — SKIP"
        if not pdf_urls:
            return None, "C1~C4 에서 PDF 링크를 하나도 얻지 못해 시험할 대상이 없습니다 — SKIP"
        last_err = ""
        for u in pdf_urls[:5]:
            try:
                raw = http_get(u, source="naver" if "pstatic" in u else "generic",
                               as_bytes=True, tries=2, timeout=40,
                               referer="https://finance.naver.com/research/")
            except Exception as e:                                   # noqa
                last_err = f"{type(e).__name__}"
                continue
            if not raw or len(raw) < 2000:
                last_err = f"본문 {0 if not raw else len(raw)}바이트"
                continue
            txt = pdf_text(raw, max_pages=3) or ""
            if len(txt) > 500:
                return True, (f"{len(raw)/1024:.0f}KB PDF → 텍스트 {len(txt):,}자 추출 성공 "
                              f"({os.path.basename(u.split('?')[0])[:40]})")
            last_err = f"텍스트 {len(txt)}자 (스캔 이미지형 PDF 가능성)"
        return False, (f"PDF 텍스트 추출 실패 — {last_err}. pdfplumber/PyPDF2 설치 여부와 "
                       f"이미지형 PDF 비중을 확인하세요. 실패해도 인덱스 메타데이터만으로 "
                       f"이벤트 판정은 되지만, 텍스트 스코어(2차 압축)가 불가능해집니다")

    ncq_canary("C5", "PDF 다운로드·텍스트 추출", c5)

    # ── C6. FDR 유니버스 ──────────────────────────────────────────────────────────────────
    def c6():
        if not ncq_has("fetch_fdr_listing"):
            return None, "fetch_fdr_listing 미탑재 — SKIP"
        d = fetch_fdr_listing()
        n = 0 if d is None else len(d)
        if n <= 2000:
            return False, (f"상장 종목이 {n:,}건뿐입니다(기대 >2,000). KRX 전체 상장사는 "
                           f"2,600여 종목이므로, 이 상태면 유니버스 자체가 잘려 있습니다 — "
                           f"raw.githubusercontent.com 접근을 확인하세요")
        return True, f"현재 상장 {n:,}종목 (KRX 무관 정적 CSV 경로)"

    ncq_canary("C6", "FDR 유니버스 조회", c6)

    # ── C7. pykrx (실패해도 경고만) ───────────────────────────────────────────────────────
    def c7():
        if globals().get("pykrx_stock") is None:
            return None, "pykrx 비활성(NCQ_USE_KRX=False 또는 미설치) — 정상. KRX-free 경로로 진행"
        if not ncq_has("KRXG"):
            return None, "KRXG 게이트 미탑재 — SKIP"
        ok = bool(KRXG.warmup())
        if not ok:
            return False, ("KRX 세션을 확보하지 못했습니다(차단 또는 자격증명 문제). "
                           "가격·시총은 네이버 차트 + DART PIT 주식수로 폴백하므로 "
                           "치명적이지 않습니다 — 경고로만 처리합니다")
        return True, "KRX 세션 확보 (월말 스냅샷을 '검증·보강'으로만 사용합니다)"

    ncq_canary("C7", "pykrx 가격 조회 / 차단 여부", c7)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = []
    for r in NCQ_CANARY.values():
        icon = "→ SKIP" if r["ok"] is None else ("✔ 가용" if r["ok"] else
                                                 ("✘ 차단성 실패" if r["blocking"] else "⚠ 불가"))
        rows.append([r["id"], _trunc(r["name"], 28), icon, f"{r['sec']:.1f}s",
                     _trunc(r["detail"], 76)])
    LOG.table(rows, ["카나리", "대상", "판정", "소요", "상세"], ["l", "l", "c", "r", "l"], maxw=80,
              title="네트워크 카나리 C1~C7 — 실패는 그대로 표시합니다(좋아 보이게 만들지 않습니다)")

    blocking_failed = [r["id"] for r in NCQ_CANARY.values()
                       if r["blocking"] and r["ok"] is not None and not bool(r["ok"])]
    soft_failed = [r["id"] for r in NCQ_CANARY.values()
                   if (not r["blocking"]) and r["ok"] is not None and not bool(r["ok"])]
    if soft_failed:
        LOG.warn(f"비차단 카나리 실패: {', '.join(soft_failed)} — 해당 소스를 빼고 진행합니다. "
                 f"결손은 완결성 진단과 리포트 최상단에 그대로 표시됩니다.")
    if ncq_has("manifest_put"):
        manifest_put("canaries", {k: {"ok": v["ok"], "detail": v["detail"][:200]}
                                  for k, v in NCQ_CANARY.items()})

    out = dict(NCQ_CANARY)
    out["_summary"] = {"ok": not blocking_failed, "skipped": False,
                       "blocking_failed": blocking_failed, "soft_failed": soft_failed}
    if blocking_failed:
        c3r = NCQ_CANARY.get("C3", {})
        LOG.error("★ 과거 아카이브(36개월 전)에 접근하지 못했습니다 — " + str(c3r.get("detail", "")))
        LOG.error("이 상태로 수집을 진행하면 최근 구간만 모인 뒤 '유효 윈도우 부족'으로 몇 시간을 "
                  "버리게 됩니다. 지금 중단하고 사용자 판단을 요청합니다.\n"
                  "  선택지 ① 드라이브 캐시에 과거 리포트를 확보한 뒤 RUN_MODE='CACHED' 로 재현\n"
                  "         ② IR협의회 단독 + 짧은 윈도우로 재설계(검정력 감소를 명시)\n"
                  "         ③ 네트워크/차단 상태를 해소한 뒤 재시도")
        if strict:
            raise RuntimeError(
                f"차단성 카나리 실패({', '.join(blocking_failed)}) — 과거 아카이브에 접근할 수 "
                f"없어 10년 백테스트가 성립하지 않습니다. 수집을 시작하지 않습니다.")
    else:
        LOG.ok("차단성 카나리(C3) 통과 — 과거 아카이브 경로가 확보되었습니다.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (C) 실경로 리허설 — 네트워크만 가짜, 수집·정제 함수는 실물 실행
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_REHEARSAL: List[dict] = []


def ncq_rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    """리허설 1건. 예외는 실패. '정상 응답인데 0행'도 (기대했다면) 실패다 — 파싱이 죽은 것이다."""
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        NCQ_REHEARSAL.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0, "note": note,
            "err": "" if ok else "정상 픽스처를 줬는데 0행입니다(파싱 실패 가능성)", "tb": ""})
        return out
    except Exception as e:                                          # noqa
        NCQ_REHEARSAL.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0, "note": note,
            "err": f"{type(e).__name__}: {str(e)[:200]}",
            "tb": "\n".join(ncq_tail_tb(10))})
        return None


class NcqFixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크.

    mode:
      "ok"          정상 응답
      "empty"       빈 응답 (소스가 살아 있지만 데이터가 없는 상황)
      "broken"      깨진 응답 (로그인 페이지·오류 HTML·바이너리 쓰레기)
      "missingcol"  기대 컬럼이 빠진 응답 (업스트림 스키마 변경)

    ★ build/75 의 _FixtureNet 과 이름을 겹치지 않게 새로 만든다(조립 시 중복 정의 금지).
    """

    def __init__(self, mode: str = "ok"):
        self.mode = str(mode)
        self.hits: Counter = Counter()

    # -- 픽스처 -----------------------------------------------------------------------
    @staticmethod
    def fdr_listing_csv(n: int = 40) -> bytes:
        head = ",Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"
        rows = [head]
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(f"{i},{code},KR7{code}003,합성{i+1:03d},"
                        f"{'KOSPI' if i % 2 else 'KOSDAQ'},,10000,0.5,1000000000,100000,"
                        f"{'STK' if i % 2 else 'KSQ'}")
        return ("﻿" + "\n".join(rows)).encode("utf-8")

    @staticmethod
    def fdr_delisting_csv(n: int = 30) -> bytes:
        head = ("Symbol,Name,Market,SecuGroup,Kind,ListingDate,DelistingDate,Reason,"
                "Industry,ListingShares,ToSymbol,ToName")
        rows = [head]
        for i in range(n):
            # 뒤 10건은 비표준 코드(ETF/ELW/스팩) — 탈락 집계가 정상 동작하는지 함께 본다
            code = f"{900000 + i:06d}" if i < 20 else f"KR{i:08d}"
            rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,2005-03-02,"
                        f"{2017 + (i % 8)}-0{1 + (i % 9)}-15,상장폐지,화학,1000000,,")
        return ("﻿" + "\n".join(rows)).encode("utf-8")

    @staticmethod
    def kind_html(n: int = 40) -> bytes:
        # KIND 는 HTML 표이고 종목코드가 '정수'로 와서 앞자리 0 이 날아간다
        head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
                "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
        body = "".join(
            f"<tr><td>합성{i+1:03d}</td><td>{(i+1)*10}</td><td>화학</td><td>부품</td>"
            f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td><td>서울</td></tr>"
            for i in range(n))
        return (head + body + "</table>").encode("euc-kr")

    @staticmethod
    def naver_list_html(n: int = 12) -> str:
        hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
               "<th>작성일</th><th>조회수</th></tr>")
        rows = []
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td style='padding-left:10'><a class='stock_item' "
                f"href='/item/main.naver?code={code}' title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
                f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>구조적 성장 전망</a></td>"
                f"<td>{'KB증권' if i % 2 else '신한투자증권'}</td>"
                f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
                f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
                f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
        nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
               "<a href='/research/company_list.naver?&amp;page=3'>맨뒤</a></td></tr></table>")
        return (f"<div id='contentarea_left'><div class='box_type_m'>"
                f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")

    @staticmethod
    def hankyung_html(n: int = 12) -> str:
        hdr = ("<tr>" + "".join(f"<th>{h}</th>" for h in
               ["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
                "기업정보", "차트", "첨부"]) + "</tr>")
        rows = []
        for i in range(n):
            idx = 500000 + i
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td>2024-0{1+(i%9)}-15</td>"
                f"<td class='text_l'><a href='/analysis/downpdf?report_idx={idx}'>"
                f"합성{i+1:03d}({code}) 신규 라인 양산</a></td>"
                f"<td class='text_r'>{(i+5)*10000:,}</td><td>Buy</td>"
                f"<td>애널{i%7:02d}</td><td>{'미래에셋증권' if i % 2 else '하나증권'}</td>"
                f"<td>-</td><td>-</td>"
                f"<td><a href='/analysis/downpdf?report_idx={idx}'>PDF</a></td></tr>")
        return (f"<div id='contents'><div class='table_style01'>"
                f"<table>{hdr}{''.join(rows)}</table></div></div>")

    @staticmethod
    def irs_html(n: int = 10) -> str:
        rows = []
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td>합성{i+1:03d}</td>"
                f"<td><a href='/board/view.html?idx={7000+i}'>"
                f"합성{i+1:03d}({code}) 기술분석보고서</a></td>"
                f"<td>2024.0{1+(i%9)}.1{i%9}</td>"
                f"<td><a href='/download/tech_{7000+i}.pdf'>PDF</a></td></tr>")
        return ("<html><body><div class='board'><table>"
                "<tr><th>기업명</th><th>제목</th><th>등록일</th><th>첨부</th></tr>"
                + "".join(rows) + "</table></div>"
                + "안내문 " * 200 + "</body></html>")

    @staticmethod
    def sise_json(url: str) -> str:
        m = re.search(r"startTime=(\d{8}).*?endTime=(\d{8})", str(url))
        s = as_ts(m.group(1)) if m else as_ts(BACKTEST_START)
        e = as_ts(m.group(2)) if m else as_ts(BACKTEST_END)
        days = pd.bdate_range(s, e)
        if len(days) > 3000:
            days = days[-3000:]
        rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
        px = 10000.0
        for i, d in enumerate(days):
            px *= 1.0002
            rows.append(f"['{d:%Y%m%d}',{px*0.995:.0f},{px*1.01:.0f},{px*0.99:.0f},"
                        f"{px:.0f},{120000 + i},5.0]")
        return "[" + ",".join(rows) + "]"

    @staticmethod
    def pdf_bytes() -> bytes:
        return b"%PDF-1.4\n% ncq synthetic fixture\n%%EOF\n"

    # -- 라우팅 -----------------------------------------------------------------------
    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u = str(url)
        p = params or {}
        self.hits[source] += 1
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return (b"\x00\x01garbage" if as_bytes else
                    "<html><body>로그인이 필요합니다</body></html>")

        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                return self.fdr_delisting_csv()
            if self.mode == "missingcol":
                return "﻿,Foo,Bar\n0,1,2\n".encode("utf-8")
            return self.fdr_listing_csv()
        if "kind.krx.co.kr" in u:
            return self.kind_html()
        if "corpCode.xml" in u:
            buf = io.BytesIO()
            xml = "<result>" + "".join(
                f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
                f"<stock_code>{(i+1)*10:06d}</stock_code><modify_date>20240101</modify_date>"
                f"</list>" for i in range(40)) + "</result>"
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml", xml.encode("utf-8"))
            return buf.getvalue()
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                return self.pdf_bytes()
            page = int(p.get("now_page", 1) or 1)
            return self.hankyung_html() if page == 1 else "<td class='no_data'>데이터가 없습니다</td>"
        if "finance.naver.com/research" in u:
            page = int(p.get("page", 1) or 1)
            if page <= 3:
                return self.naver_list_html()
            return "<div id='contentarea_left'><table class='type_1'></table></div>"
        if "finance.naver.com/item/main" in u:
            return '<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>'
        if "stock.pstatic.net" in u:
            return self.pdf_bytes()
        if "siseJson" in u:
            return self.sise_json(u)
        if any(h in u for h in ("kirs.or.kr", "irsolution.or.kr")):
            return self.irs_html()
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        self.hits[f"json:{source}"] += 1
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "stockTotqySttus" in u:
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return {"status": "000", "message": "정상", "list": [
                {"rcept_no": f"{int(p.get('bsns_year', 2020))+1}0401000001",
                 "corp_code": p.get("corp_code", "C0000001"), "se": "합계",
                 "istc_totqy": "100,000"}]}
        if "stockSecurity/researches" in u:
            return []                      # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        return None

    def post(self, *a, **kw):
        return "" if self.mode != "broken" else "<html>오류</html>"


def run_rehearsal(strict: bool = True) -> bool:
    """수집·정제 함수를 픽스처로 전부 '실물 실행'한다. 네트워크·키 불필요, 수 초.

    ★ 이 검정만이 잡는 사고: 파싱 회귀·컬럼 중복·스키마 변경·인코딩·빈 응답 크래시.
      합성 스모크(D)는 완성 패널을 주입하므로 이 구간을 단 한 줄도 실행하지 않는다.
    """
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다 — 키 불필요")
    NCQ_REHEARSAL.clear()
    G = globals()
    keys = ("http_get", "http_json", "http_post", "fdr", "pykrx_stock", "yf",
            "RUN_MODE", "DART_API_KEY", "RESEARCH_COLLECT", "RESEARCH_SOURCES",
            "RESEARCH_DOWNLOAD_PDF", "N_WORKERS_RESEARCH", "UNIVERSE_SNAPSHOT_FREQ",
            "NCQ_USE_KRX")
    saved = {k: G.get(k) for k in keys}
    saved_vault = G.get("VAULT")
    # ★ IR협의회 엔드포인트 탐색 결과는 모듈 전역에 캐시된다. 픽스처로 탐색한 결과가 남으면
    #   이후 실수집이 가짜 URL 을 진짜로 믿는다. 반드시 원복한다.
    saved_irs = dict(globals().get("_IRS_ENDPOINT_CACHE", {})) \
        if "_IRS_ENDPOINT_CACHE" in G else None
    tmp = tempfile.mkdtemp(prefix="ncq_rehearsal_")
    months = pd.date_range(as_ts(BACKTEST_END) - pd.DateOffset(months=5),
                           as_ts(BACKTEST_END), freq="ME")

    try:
        net = NcqFixtureNet("ok")
        G["http_get"], G["http_json"], G["http_post"] = net.get, net.json, net.post
        G["fdr"] = None
        G["pykrx_stock"] = None            # KRX-free 경로가 진짜로 자립하는지 본다
        G["yf"] = None
        G["RUN_MODE"] = "FULL"
        G["DART_API_KEY"] = "REHEARSAL"
        G["RESEARCH_COLLECT"] = True
        G["RESEARCH_SOURCES"] = ["naver", "hankyung", "irs"]
        G["RESEARCH_DOWNLOAD_PDF"] = False       # 리허설에서 PDF 본문 수집은 대상이 아니다
        G["NCQ_USE_KRX"] = False
        G["UNIVERSE_SNAPSHOT_FREQ"] = "off"
        G["VAULT"] = Vault(tmp, "REHEARSAL")

        # ── ① 종목 마스터 ─────────────────────────────────────────────────────────────────
        snaps = pd.DataFrame(columns=["snap_date", "code", "market"])
        ncq_rh("fetch_fdr_listing", fetch_fdr_listing)
        ncq_rh("fetch_fdr_delisting", fetch_fdr_delisting,
               note="여기서 조용히 버려지는 종목이 그대로 생존자편향이 된다")
        ncq_rh("fetch_kind_listing", fetch_kind_listing)
        sec = ncq_rh("build_security_master", lambda: build_security_master(snaps),
                     note="중복 컬럼 → groupby.agg 폭발이 과거 실크래시 지점")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{(i+1)*10:06d}" for i in range(40)],
                                "name": [f"합성{i+1:03d}" for i in range(40)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(40)],
                                "listing_date": as_ts("2010-03-15"),
                                "delisting_date": pd.NaT, "src": "fx"})

        # ── ② 가격 · 시가총액 · 유니버스 ──────────────────────────────────────────────────
        codes = sec["code"].dropna().astype(str).tolist()[:10]
        px = ncq_rh("fetch_prices (네이버 차트 폴백)",
                    lambda: fetch_prices(codes, BACKTEST_START, BACKTEST_END),
                    note="pykrx/FDR/yfinance 없이 네이버 경로만으로 동작해야 한다")
        panel = None
        if px is not None and len(px):
            panel = ncq_rh("build_price_panel", lambda: build_price_panel(px, months))
        px_daily = panel["daily"] if isinstance(panel, dict) else pd.DataFrame(
            columns=["code", "date", "open", "high", "low", "close", "volume", "amount"])
        pxm = panel["monthly"] if isinstance(panel, dict) else pd.DataFrame(
            columns=["code", "month", "adv20", "exec_px", "fwd_ret"])

        if ncq_has("ncq_fdr_listing_full", "ncq_build_shares_history"):
            listing_now = ncq_rh("ncq_fdr_listing_full", ncq_fdr_listing_full)
            shares_hist = ncq_rh(
                "ncq_build_shares_history",
                lambda: ncq_build_shares_history(
                    sec, pd.DataFrame(columns=["corp_code", "shares", "knowledge_date",
                                               "bsns_year", "reprt_code"]),
                    listing_now if listing_now is not None else pd.DataFrame(
                        columns=["code", "shares"])),
                expect_rows=False)
        else:
            shares_hist = None
        if ncq_has("ncq_enrich_security_master"):
            sec2 = ncq_rh("ncq_enrich_security_master",
                          lambda: ncq_enrich_security_master(sec, px_daily),
                          note="상장일·폐지일을 다중소스로 채운다(근거 없어도 종목을 버리지 않음)")
            if sec2 is not None and len(sec2):
                sec = sec2

        mcap = None
        if ncq_has("build_marketcap_panel"):
            # ★ expect_rows=True 로 둔다. 픽스처는 상장주식수(Stocks)와 종가를 모두 주므로
            #   시가총액이 0행이면 그것은 '데이터가 없어서'가 아니라 **코드가 고장난 것**이다.
            #   여기를 관대하게 두면 하위 N 유니버스가 통째로 비는 사고가 조용히 통과한다.
            mcap = ncq_rh("build_marketcap_panel",
                          lambda: build_marketcap_panel(codes, months, px_daily, sec,
                                                        shares_hist),
                          note="주식수·종가가 모두 주어졌으므로 0행이면 코드 결함이다")
        uni_obj = Universe(sec, snaps, px_daily)
        UNI = None
        if ncq_has("build_ncq_universe"):
            UNI = ncq_rh("build_ncq_universe",
                         lambda: build_ncq_universe(
                             months, pxm,
                             mcap if mcap is not None else pd.DataFrame(columns=MCAP_COLS),
                             uni_obj, sec),
                         note="유니버스가 0행이면 하류 전 단계가 무의미해진다")

        # ── ③ 리서치 인덱스 ───────────────────────────────────────────────────────────────
        s0 = months[0].replace(day=1).strftime("%Y-%m-%d")
        s1 = months[-1].strftime("%Y-%m-%d")
        nv = ncq_rh("naver_collect", lambda: naver_collect(s0, s1, cats=("company",),
                                                           max_pages=3))
        hk = ncq_rh("hankyung_collect", lambda: hankyung_collect(s0, s1, max_pages=3))
        if ncq_has("ncq_irs_collect"):
            ncq_rh("ncq_irs_collect", lambda: ncq_irs_collect(s0, s1, max_pages=2),
                   expect_rows=False, note="IRS 는 못 찾으면 정상 스킵이어야 한다")
        frames = [f for f in (nv, hk) if f is not None and len(f)]
        rep = ncq_rh("build_report_master (다중소스 병합)",
                     lambda: build_report_master(frames, sec)) if frames else None
        REP = rep if (rep is not None and len(rep)) else pd.DataFrame(columns=REPORT_COLS)

        if len(REP):
            AL = ncq_rh("build_analyst_ledger", lambda: build_analyst_ledger(REP),
                        expect_rows=False)
            if AL is not None:
                A, L = AL
                ncq_rh("audit_linkage", lambda: (audit_linkage(REP, A, L) or [1]),
                       expect_rows=False)

        # collect_report_index 는 캐시·세션지속·연도샤딩·예산까지 한 번에 태우는 통합 경로다.
        # 월 3개만 준다(소스별 연속 실패 5회 → 60초 서킷 대기를 유발하지 않기 위함).
        if ncq_has("collect_report_index"):
            def _cri():
                try:
                    return collect_report_index(months[-3:], sec)
                except TypeError:
                    return collect_report_index(months[-3:])
            REP2 = ncq_rh("collect_report_index (캐시+수집+샤딩 통합)", _cri, expect_rows=False)
            if REP2 is not None and len(REP2):
                REP = REP2

        # ── ④ 완결성 · 이벤트 · 텍스트 · 신호 · 백테스트 ─────────────────────────────────
        valid_start = as_ts(BACKTEST_START)
        if ncq_has("coverage_completeness"):
            dg = ncq_rh("coverage_completeness", lambda: coverage_completeness(REP, months),
                        expect_rows=False)
            if isinstance(dg, tuple) and len(dg) == 2 and dg[1] is not None:
                valid_start = as_ts(dg[1])
        EV = None
        if ncq_has("build_coverage_events"):
            EV = ncq_rh("build_coverage_events",
                        lambda: build_coverage_events(
                            REP, UNI if UNI is not None else pd.DataFrame(columns=UNI_COLS),
                            months, valid_start), expect_rows=False,
                        note="6개월 창이라 burn-in 에 전부 걸려 0건이 정상 — 예외만 없으면 통과")
        EV = EV if EV is not None else pd.DataFrame(columns=EV_COLS)
        TXT = None
        if ncq_has("collect_event_texts"):
            TXT = ncq_rh("collect_event_texts", lambda: ncq_call_event_texts(EV, REP),
                         expect_rows=False)
        if ncq_has("score_texts"):
            SCORE = ncq_rh("score_texts",
                           lambda: score_texts(TXT if TXT is not None else pd.DataFrame(
                               columns=["report_uid", "code", "sec_body"])), expect_rows=False)
        else:
            SCORE = None
        if ncq_has("build_signal_panel"):
            SIG = ncq_rh("build_signal_panel",
                         lambda: build_signal_panel(
                             SCORE if SCORE is not None else pd.DataFrame(),
                             EV, UNI if UNI is not None else pd.DataFrame(columns=UNI_COLS),
                             pxm, months), expect_rows=False)
        else:
            SIG = None
        if ncq_has("run_overlap_backtest") and SIG is not None:
            ncq_rh("run_overlap_backtest",
                   lambda: run_overlap_backtest(SIG, pxm, sec, uni_obj, months,
                                                label="REHEARSAL"), expect_rows=False)

        # ── ⑤ 이상 응답 내성 (빈 / 깨짐 / 컬럼누락) ──────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = NcqFixtureNet(mode)
            G["http_get"], G["http_json"], G["http_post"] = bad.get, bad.json, bad.post
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"ncq_rh_{mode}_"), "REHEARSAL")
            if "_IRS_ENDPOINT_CACHE" in G:
                G["_IRS_ENDPOINT_CACHE"].update({"url": None, "probed": False})
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing)):
                ncq_rh(f"[{label}] {fname}", fn, expect_rows=False,
                       note="예외 없이 빈 결과를 돌려줘야 한다")
            ncq_rh(f"[{label}] naver_collect",
                   lambda: naver_collect(s0, s1, cats=("company",), max_pages=1),
                   expect_rows=False)
            ncq_rh(f"[{label}] hankyung_collect",
                   lambda: hankyung_collect(s0, s1, max_pages=1), expect_rows=False)
            if ncq_has("ncq_irs_collect"):
                ncq_rh(f"[{label}] ncq_irs_collect",
                       lambda: ncq_irs_collect(s0, s1, max_pages=1), expect_rows=False)
            ncq_rh(f"[{label}] build_report_master(빈 입력)",
                   lambda: build_report_master([], sec), expect_rows=False)
            if ncq_has("build_coverage_events"):
                ncq_rh(f"[{label}] build_coverage_events(빈 원장)",
                       lambda: build_coverage_events(
                           pd.DataFrame(columns=REPORT_COLS),
                           pd.DataFrame(columns=UNI_COLS), months, valid_start),
                       expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"] = saved_vault
        if saved_irs is not None and "_IRS_ENDPOINT_CACHE" in G:
            G["_IRS_ENDPOINT_CACHE"].clear()
            G["_IRS_ENDPOINT_CACHE"].update(saved_irs)
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in NCQ_REHEARSAL if r["ok"])
    LOG.table([[_trunc(r["name"], 44), "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 60)]
               for r in NCQ_REHEARSAL],
              ["실경로 함수", "판정", "결과", "소요", "비고"], ["l", "c", "r", "r", "l"], maxw=62,
              title="실경로 리허설 — 정상/빈/깨짐/컬럼누락 4종 응답에 대한 내성")
    fails = [r for r in NCQ_REHEARSAL if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(NCQ_REHEARSAL)}건 실패")
        for r in fails[:4]:
            LOG.banner(f"✘ 리허설 실패: {_trunc(r['name'], 60)}", _trunc(r["err"], 96))
            for ln in str(r.get("tb", "")).split("\n"):
                if ln.strip():
                    _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"이 검사는 '수집 함수가 진짜 데이터 모양에서 도는지'를 보는 것이라, "
                f"여기서 막는 것이 몇 시간 뒤 P1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(NCQ_REHEARSAL)}건 통과 — 수집·정제 함수가 실제 데이터 "
           f"모양과 이상 응답 모두에서 정상 동작합니다.")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (D) 합성 데이터 엔드투엔드 스모크
# ══════════════════════════════════════════════════════════════════════════════════════════
def run_selftest(full_chain: bool = False) -> bool:
    """네트워크·키 없이 유니버스→이벤트→텍스트→신호→백테스트→성과 전 경로를 실제로 돌린다.

    목적은 성과 측정이 아니라 **배관 검증**이다. 출력되는 모든 성과 수치는 합성 난수이며
    전략의 실제 성과가 아니다. 절대 해석하지 말 것.

    full_chain=True 면 강건성·해석표·리포트까지 예행연습한다(RUN_MODE='SMOKE' 의 목적).
    """
    LOG.banner("④ 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수 초)"
               + (" · full_chain: 강건성·리포트까지" if full_chain else ""))
    t0 = time.time()
    stage = {"name": "초기화"}
    missing: List[str] = []
    result: Dict[str, Any] = {}

    def _step(name: str, fn: Callable, required: Optional[Sequence[str]] = None):
        """단계 실행. 어디서 죽었는지가 스크롤 없이 보여야 한다."""
        if required and not ncq_has(*required):
            missing.extend([r for r in required if not ncq_has(r)])
            LOG.warn(f"[{name}] 건너뜀 — 미탑재: {', '.join(r for r in required if not ncq_has(r))}")
            return None
        stage["name"] = name
        LOG.info(f"▷ {name}")
        return fn()

    try:
        with ncq_tmp_vault("ncq_selftest_"):
            S = _step("합성 데이터 생성", lambda: ncq_make_synthetic())
            months, sec, pxm = S["months"], S["sec"], S["pxm"]
            px_daily, uni_obj = S["px_daily"], S["uni_obj"]
            LOG.info(f"합성 세계 — 종목 {len(sec):,} · 월 {len(months)} · "
                     f"일봉 {len(px_daily):,} · 리포트 {len(S['REP']):,} · 텍스트 {len(S['TXT']):,}")

            UNI = _step("PIT 유니버스 (build_ncq_universe)",
                        lambda: build_ncq_universe(months, pxm, S["mcap"], uni_obj, sec),
                        ["build_ncq_universe"])
            if UNI is None or len(UNI) == 0:
                UNI = S["UNI"]
                LOG.warn("build_ncq_universe 가 빈 결과를 돌려줘 픽스처 UNI 로 대체합니다.")

            dg = _step("커버리지 완결성 진단",
                       lambda: coverage_completeness(S["REP"], months), ["coverage_completeness"])
            valid_start = as_ts(dg[1]) if isinstance(dg, tuple) and len(dg) == 2 else months[0]

            EV = _step("신규 커버리지 이벤트 판정",
                       lambda: build_coverage_events(S["REP"], UNI, months, valid_start),
                       ["build_coverage_events"])
            if EV is None:
                EV = pd.DataFrame(columns=globals().get("EV_COLS", ["month", "code"]))
            if ncq_has("audit_events") and len(EV):
                _step("이벤트 감사", lambda: audit_events(EV, S["REP"]), ["audit_events"])
            if len(EV) == 0:
                LOG.error("합성 세계에서 이벤트가 0건입니다 — 신규 커버리지 판정 경로를 "
                          "증명하지 못했습니다. 위 퍼널에서 어느 게이트가 원인인지 보세요.")
                result["events"] = 0

            # 텍스트: 실 경로(PDF)가 없으므로 합성 본문을 extra_text 로 주입해 '본문이 있는
            # 상태'를 재현한다. 이렇게 해야 섹션 가중·부정어미 무효화·길이 정규화까지 전부
            # 실제 코드로 검증된다. (주입 없이 돌리면 제목만 남아 doc_score 가 전부 0이 되고,
            # 그 0 은 '스코어러가 고장났다'와 '텍스트가 없다'를 구분하지 못한다)
            TXT = _step("이벤트 본문 수집 (collect_event_texts)",
                        lambda: ncq_call_event_texts(EV, S["REP"], extra=S["TXT"]),
                        ["collect_event_texts"])
            if TXT is None or len(TXT) == 0:
                uids = set()
                if "report_uids" in getattr(EV, "columns", []):
                    for v in EV["report_uids"].dropna().astype(str):
                        uids.update([x for x in v.split("|") if x])
                T = S["TXT"]
                TXT = T[T["report_uid"].isin(uids)] if uids else T
                LOG.warn(f"PDF 원문이 없어 합성 TXT {len(TXT):,}행으로 대체합니다 "
                         f"(네트워크 없는 환경의 정상 폴백 — 스코어링 경로는 그대로 검증됩니다).")

            SCORE = _step("텍스트 스코어링 (score_texts)", lambda: score_texts(TXT),
                          ["score_texts"])
            if SCORE is not None and len(SCORE) and "doc_score" not in SCORE.columns:
                LOG.error("★SCORE 에 doc_score 컬럼이 없습니다 — 계약 §3 의 SCORE 스키마 위반입니다. "
                          "이 상태에서는 신호 산출이 성립하지 않습니다.")
                result["score_variance_zero"] = True
            elif SCORE is not None and len(SCORE):
                ds = pd.to_numeric(SCORE["doc_score"], errors="coerce").dropna()
                sd = float(ds.std()) if len(ds) > 1 else float("nan")
                if not np.isfinite(sd) or sd <= 1e-12:
                    LOG.error("★doc_score 의 표준편차가 0입니다(또는 유효값이 1건 이하) — "
                              "렉시콘이 텍스트에서 아무것도 "
                              "잡지 못했습니다. 이 상태에서는 횡단면 z 가 전부 동일값이 되어 "
                              "편입 종목이 0건이 됩니다. 스코어러(정규식 컴파일·섹션 분할)나 "
                              "본문 전달 경로를 먼저 고쳐야 합니다.")
                    result["score_variance_zero"] = True

            SIG = _step("신호 패널 (build_signal_panel)",
                        lambda: build_signal_panel(SCORE, EV, UNI, pxm, months),
                        ["build_signal_panel"])
            BT = _step("오버랩 코호트 백테스트",
                       lambda: run_overlap_backtest(SIG, pxm, sec, uni_obj, months,
                                                    label=f"{STRATEGY_ID} (합성)"),
                       ["run_overlap_backtest"])
            st = _step("성과 통계 (perf_stats)",
                       lambda: perf_stats(BT["returns"]), ["perf_stats"]) if BT else None
            if ncq_has("universe_funnel"):
                _step("3단 퍼널", lambda: universe_funnel(UNI, EV), ["universe_funnel"])

            dur = time.time() - t0
            n_ret = len(BT["returns"]) if isinstance(BT, dict) and "returns" in BT else 0
            rows = [
                ["합성 종목수", ncq_v_num(len(sec), "int")],
                ["유니버스 행수", ncq_v_num(len(UNI) if UNI is not None else None, "int")],
                ["신규 커버리지 이벤트", ncq_v_num(len(EV), "int")],
                ["이벤트 텍스트", ncq_v_num(len(TXT) if TXT is not None else None, "int")],
                ["스코어 행수", ncq_v_num(len(SCORE) if SCORE is not None else None, "int")],
                ["신호 행수 / 선정", (ncq_v_num(len(SIG) if SIG is not None else None, "int") + " / " +
                                 ncq_v_num(int(SIG["selected"].sum())
                                         if (SIG is not None and "selected" in SIG.columns)
                                         else None, "int"))],
                ["백테스트 월수", ncq_v_num(n_ret, "int")],
                ["합성 CAGR", ncq_v_num((st or {}).get("CAGR"), "pct")],
                ["합성 Sharpe", ncq_v_num((st or {}).get("Sharpe"))],
                ["소요시간", f"{dur:.2f}초"],
            ]
            LOG.table(rows, ["항목", "값"], ["l", "r"],
                      title="스모크 결과 (성과 수치는 합성 난수 — 배관 검증용이며 해석 대상이 아님)")

            ok = bool(UNI is not None and len(UNI) > 0 and len(EV) > 0 and
                      SCORE is not None and len(SCORE) > 0 and
                      SIG is not None and len(SIG) > 0 and n_ret > 0)
            if missing:
                uniq = list(dict.fromkeys(missing))
                LOG.error("아직 조립되지 않은 스파인 함수가 있어 전 경로를 증명하지 못했습니다: "
                          + ", ".join(uniq) + "\n"
                          "  → 해당 모듈(ncq_40_text / ncq_50_backtest 등)을 조립한 뒤 "
                          "반드시 스모크를 다시 돌리십시오.")
                NCQ_VERIFY_SKIPPED.extend(uniq)
                return False
            if not ok:
                LOG.error("스모크 실패 — 실데이터를 수집하기 전에 계산경로를 먼저 고쳐야 합니다. "
                          "위 표에서 어느 단계가 0행인지 보세요(그 직전 단계가 원인입니다).")
                return False
            LOG.ok(f"스모크 통과 ({dur:.2f}초) — 네트워크·키 없이 유니버스→이벤트→텍스트→신호→"
                   f"백테스트→성과 전 경로에서 출력물이 생성됩니다.")

            if not full_chain:
                return True

            # ── 최종 출력물 예행연습 ─────────────────────────────────────────────────────
            LOG.warn("아래 성과·강건성 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 "
                     "아니라 '출력물이 제대로 나오는지'를 보여주는 예행연습입니다. "
                     "절대 해석하지 마세요.")
            benches: Dict[str, pd.Series] = {}
            ew = None
            if ncq_has("bench_universe_ew"):
                try:
                    ew = bench_universe_ew(UNI, pxm, months, uni_obj)
                except Exception as e:                              # noqa
                    LOG.warn(f"합성 벤치마크 생성 실패({type(e).__name__}) — 폴백을 씁니다.")
            if ew is None or len(ew) == 0:
                # ★ 벤치가 없으면 P1/P3(초과수익) 이 전부 '판정불가'로 떨어져 예행연습이
                #   정작 봐야 할 경로를 하나도 안 밟는다. 유니버스 동일가중을 직접 만들어
                #   그 경로를 반드시 태우고, '폴백을 썼다'는 사실을 로그에 남긴다.
                u = UNI[UNI["liq_pass"].astype(bool)][["month", "code"]] \
                    if "liq_pass" in UNI.columns else UNI[["month", "code"]]
                b = u.merge(pxm[["month", "code", "fwd_ret"]], on=["month", "code"], how="left")
                ew = (b.groupby("month", observed=True)["fwd_ret"].mean()
                        .reindex(months))
                LOG.warn("bench_universe_ew 미탑재/빈 결과 — 유니버스 동일가중 폴백 벤치를 "
                         "직접 계산했습니다(예행연습 전용, 본선에서는 쓰이지 않습니다).")
            benches["Bottom-N 동일가중"] = ew

            def _run(sig, label="smoke", **kw):
                return run_overlap_backtest(sig, pxm, sec, uni_obj, months, label=label, **kw)

            def _build_sig(top_pct=None, min_adv=None):
                """민감도 축(ADV/tercile)이 신호를 다시 만드는 경로까지 실제로 태운다."""
                U2 = UNI
                if min_adv is not None and ncq_has("build_ncq_universe"):
                    U2 = build_ncq_universe(months, pxm, S["mcap"], uni_obj, sec,
                                            min_adv=min_adv)
                E2 = EV
                if U2 is not UNI and ncq_has("build_coverage_events"):
                    E2 = build_coverage_events(S["REP"], U2, months, valid_start)
                return build_signal_panel(SCORE, E2, U2, pxm, months, top_pct=top_pct)

            with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
                if ncq_has("report_performance"):
                    report_performance(BT, benches, label=f"{STRATEGY_NAME} (합성 예행연습)")
                if hasattr(uni_obj, "report_attrition"):
                    uni_obj.report_attrition()
                if ncq_has("report_coverage_diagnostics") and isinstance(dg, tuple):
                    report_coverage_diagnostics(dg[0], S["REP"], EV)

            keep_kill = STOP_ON_KILL_CRITERIA
            globals()["STOP_ON_KILL_CRITERIA"] = False   # 예행연습은 킬로 멈추지 않는다
            try:
                with PIPE.stage("SMOKE.ROBUST", "[합성] 사전등록·강건성", "L5",
                                budget_s=900, critical=False):
                    ctx = {"SIG": SIG, "BT": BT, "bench_ew": ew, "EV": EV, "UNI": UNI,
                           "SCORE": SCORE, "REP": S["REP"], "sec": sec, "pxm": pxm,
                           "uni_obj": uni_obj, "months": months, "valid_start": valid_start}
                    if ncq_has("run_prereg_tests"):
                        run_prereg_tests(SIG, BT, ew, pxm, sec, uni_obj, months, _run)
                    if ncq_has("run_sensitivity"):
                        # 민감도는 신호 재생성까지 도는 가장 무거운 경로다. 예행연습에서
                        # 실패해도 나머지 출력물을 잃지 않도록 여기서만 예외를 흡수한다.
                        try:
                            run_sensitivity(ctx, months, _build_sig, _run)
                        except Exception as e:                       # noqa
                            LOG.warn(f"[합성] 민감도 예행연습 실패({type(e).__name__}: {e}) — "
                                     f"S6(Holm)는 판정불가로 남습니다.")
                    if ncq_has("run_stat_suite"):
                        run_stat_suite(BT, ew, SIG, months, _run, n_trials=9)
                    if ncq_has("report_structural_risks"):
                        report_structural_risks(ctx)
                    if ncq_has("report_robustness"):
                        report_robustness()
            finally:
                globals()["STOP_ON_KILL_CRITERIA"] = keep_kill

            with PIPE.stage("SMOKE.REPORT", "[합성] 진단·해석표", "L6",
                            budget_s=180, critical=False):
                if ncq_has("report_diagnostics"):
                    report_diagnostics(SIG, EV, BT, UNI, sec, benches)
                if ncq_has("report_interpretation"):
                    report_interpretation(SIG, EV, SCORE)
                if ncq_has("report_dataflow_map"):
                    report_dataflow_map()
            LOG.ok("full_chain 예행연습 완료 — 백테스트·성과·강건성·진단·해석표가 모두 "
                   "정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 같은 출력이 실데이터로 나옵니다.")
            if ncq_has("NCQ_ROBUST"):
                try:
                    globals()["NCQ_ROBUST"].clear()   # 예행연습 결과가 실행 결과로 새지 않게
                except Exception:
                    pass
            return True

    except Exception as e:                                          # noqa
        LOG.error(f"스모크가 [{stage['name']}] 단계에서 중단됐습니다 — {type(e).__name__}: {e}")
        LOG.info("진단: " + diagnose(e, extra=f"selftest stage={stage['name']}"))
        for ln in ncq_tail_tb(10):
            _safe_print("   " + ln)
        return False
