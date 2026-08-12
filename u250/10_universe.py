# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §1 유니버스 — 동결. 수정 금지.                                                           ║
# ║                                                                                          ║
# ║  적격성 게이트: 거래대금 ≥ 1억원 · 보통주 · 비스팩/비리츠 · 상장 ≥ 180일 ·                 ║
# ║                비자본잠식 · 재무 비결측                                                   ║
# ║  유니버스     : 적격 통과 종목 중 시총 하위 250(주) / 하위 500(보조)                       ║
# ║  비중         : 동일가중(EW)                                                              ║
# ║                                                                                          ║
# ║  ★ 이 게이트는 탐색 대상이 아니다(명세서 §1 주의). 임계값을 건드리는 코드 경로가           ║
# ║    아예 없도록 SPEC_UNIV 에서만 읽는다.                                                    ║
# ║  ★ 원본 KR_QUANT_SUITE_V1.py 가 있으면 4380–4394행을 파싱해 상수를 대조하고,               ║
# ║    불일치는 조용히 넘기지 않고 표로 출력한다.                                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 스팩·리츠·기타 비적격 법적 형태 (상호에 남는다)
_EXCL_NAME_PAT = re.compile(
    r"(스팩|기업인수목적|제\d+호\s*기업인수|리츠|위탁관리부동산투자|자기관리부동산투자|"
    r"기업구조조정부동산투자|리얼티|투자회사|뮤추얼펀드|사모투자|선박투자|인프라투자)")
# 우선주 (보통주만 남긴다)
_PREF_NAME_PAT = re.compile(r"(\d?우[BC]?$|우선주$|\(전환\)$|우\(전환\)$|우\d*$)")


def gate_crosscheck() -> None:
    """원본 파일이 있으면 게이트 상수를 실제로 읽어 대조한다. 없으면 그 사실을 남긴다."""
    p = os.path.expanduser(GATE_SOURCE_FILE or "")
    if not p or not os.path.exists(p):
        LOG.info(f"게이트 원본({GATE_SOURCE_FILE}) 미발견 — 명세서 §1 표의 상수로 재현합니다: "
                 f"거래대금 ≥ {SPEC_UNIV['min_amount_krw']:,}원 · 상장 ≥ "
                 f"{SPEC_UNIV['min_listing_days']}일 · 하위 {SPEC_UNIV['main_n']}/{SPEC_UNIV['aux_n']}. "
                 f"원본을 이 경로에 두면 자동 대조합니다.")
        RUNLOG["gate_source"] = "spec_table"
        return
    try:
        src = open(p, encoding="utf-8", errors="replace").read().split("\n")
        seg = "\n".join(src[4379:4394])                      # 4380–4394행 (1-based)
        nums = [int(x.replace("_", "").replace(",", ""))
                for x in re.findall(r"\b\d[\d_,]{2,}\b", seg)]
        LOG.info(f"게이트 원본 4380–4394행을 읽었습니다 ({len(seg)}자). 발견 상수: {nums[:12]}")
        miss = []
        for label, want in (("거래대금 하한", SPEC_UNIV["min_amount_krw"]),
                            ("상장일수 하한", SPEC_UNIV["min_listing_days"]),
                            ("주 유니버스 N", SPEC_UNIV["main_n"]),
                            ("보조 유니버스 N", SPEC_UNIV["aux_n"])):
            if want not in nums:
                miss.append([label, f"{want:,}", "원본 구간에서 발견되지 않음"])
        if miss:
            LOG.table(miss, ["항목", "명세서 값", "대조 결과"], ["l", "r", "l"],
                      title="⚠ 게이트 상수 대조 — 불일치(추측으로 채우지 않고 명세서 값으로 진행)")
        else:
            LOG.ok("게이트 상수 4종이 원본과 일치합니다.")
        RUNLOG["gate_source"] = f"{p}#4380-4394"
        RUNLOG["gate_sha256"] = hashlib.sha256(seg.encode("utf-8")).hexdigest()[:16]
    except Exception as e:                                   # noqa
        LOG.warn(f"게이트 원본 파싱 실패({type(e).__name__}) — 명세서 값으로 진행합니다.")
        RUNLOG["gate_source"] = "spec_table(parse_failed)"


def rebalance_dates(panel_dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """리밸런싱 시점 = 거래일 격자에 스냅된 주기 말일. (§1 기존 구현과 동일 주기 유지)"""
    d = pd.DatetimeIndex(sorted(pd.unique(panel_dates)))
    if len(d) == 0:
        return d
    if REBAL_FREQ.upper().startswith("M"):
        key = d.to_period("M")
    else:
        key = d.to_period("W-FRI")
    s = pd.Series(d, index=key)
    out = pd.DatetimeIndex(s.groupby(level=0).last().values)
    LOG.info(f"리밸런싱 주기 = {REBAL_FREQ} → 시점 {len(out):,}개 "
             f"({out[0]:%Y-%m-%d} ~ {out[-1]:%Y-%m-%d}). "
             f"'기존 구현과 동일 주기 유지'(§1) 를 이 상수로 고정했습니다.")
    return out


def build_daily_panel(px: pd.DataFrame) -> pd.DataFrame:
    """일별 패널 정규화 — 수익률·ADV·ILLIQ 원재료를 여기서 한 번만 만든다."""
    need = ["code", "date", "close"]
    for c in need:
        if c not in px.columns:
            raise StageFailure(f"가격 패널에 '{c}' 컬럼이 없습니다. 캐시 지문 판별을 확인하세요.")
    d = px.copy()
    d["code"] = d["code"].map(to_code6)
    d["date"] = as_ts_series(d["date"])
    for c in ("open", "high", "low", "close", "volume", "amount", "market_cap", "shares"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["code", "date", "close"])
    d = d[d["close"] > 0]
    d = d.sort_values(["code", "date"]).drop_duplicates(["code", "date"], keep="last")

    if "amount" not in d.columns or d["amount"].isna().all():
        if "volume" in d.columns:
            d["amount"] = d["close"] * d["volume"]
            LOG.warn("거래대금 컬럼이 없어 종가×거래량으로 근사했습니다 — 게이트(1억원)가 "
                     "그만큼 느슨해집니다(과대추정 방향). 감사표에 명시됩니다.")
        else:
            raise StageFailure("거래대금도 거래량도 없습니다 — 유동성 게이트를 걸 수 없습니다.")
    if "market_cap" not in d.columns or d["market_cap"].isna().all():
        if "shares" in d.columns and d["shares"].notna().any():
            d["market_cap"] = d["close"] * d["shares"]
            LOG.info("시가총액을 종가×상장주식수로 산출했습니다.")
        else:
            raise StageFailure("시가총액도 상장주식수도 없습니다 — 시총 하위 250 을 정의할 수 없습니다.")

    g = d.groupby("code", observed=True)
    d["ret1d"] = g["close"].pct_change()
    #   게이트의 '거래대금'은 단일일 값이 아니라 20세션 중앙값을 쓴다.
    #   하루치로 재면 상한가 하루가 종목을 통과시켜 유니버스가 그날그날 요동친다.
    d["adv20"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=10).median())
    d["adv20_mean"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    LOG.ok(f"일별 패널 {len(d):,}행 · 종목 {d['code'].nunique():,}개 · "
           f"{d['date'].min():%Y-%m-%d} ~ {d['date'].max():%Y-%m-%d}")
    PIPE.io("OUT", "MEM", "daily_panel", d)
    return downcast(d)


def _is_common(code: str, name: str) -> bool:
    """보통주 판별. 코드 끝자리(신형우선주는 K/L/M)와 상호를 함께 본다."""
    c, n = str(code), str(name or "")
    if not c or len(c) != 6:
        return False
    if c[-1] not in "0":                     # 우선주 5/7/9, 신형우선주 K·L·M
        return False
    return not bool(_PREF_NAME_PAT.search(n.strip()))


def build_eligibility(daily: pd.DataFrame, sec: pd.DataFrame, fin: pd.DataFrame,
                      rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """리밸런싱 시점 × 종목 적격성 패널. 게이트 6종을 각각 컬럼으로 남겨 감쇠를 감사한다."""
    snap = daily[daily["date"].isin(rebals)][
        ["code", "date", "close", "amount", "adv20", "adv20_mean", "market_cap"]].copy()
    snap = snap.rename(columns={"date": "rebal"})
    #   daily 는 메모리를 아끼려고 code 를 categorical 로 두지만, 이 스냅샷부터는
    #   merge_asof·map 이 dtype 일치를 요구하므로 문자열로 확정한다.
    snap["code"] = snap["code"].astype(str)
    if not len(snap):
        raise StageFailure("리밸런싱 시점에 해당하는 가격 스냅샷이 없습니다.")

    s = sec.drop_duplicates("code").set_index("code")
    #   downcast 로 code 가 categorical 이 되어 있으면 map 결과도 categorical 이 되고,
    #   그 뒤의 fillna("")·str.contains 가 조용히가 아니라 요란하게 터진다. 문자열로 못박는다.
    _codes = snap["code"].astype(str)
    snap["name"] = (_codes.map(s["name"]).astype(object).fillna("").astype(str)
                    if "name" in s.columns else "")
    for c in ("listing_date", "delisting_date"):
        snap[c] = (pd.to_datetime(_codes.map(s[c]).astype(object), errors="coerce")
                   if c in s.columns else pd.NaT)

    # ── 게이트 6종 ─────────────────────────────────────────────────────────────────────
    snap["g_amount"] = snap["adv20"] >= SPEC_UNIV["min_amount_krw"]
    snap["g_common"] = [_is_common(c, n) for c, n in zip(_codes, snap["name"])]
    snap["g_form"] = ~snap["name"].str.contains(_EXCL_NAME_PAT)
    age = (snap["rebal"] - snap["listing_date"]).dt.days
    #   상장일을 모르는 종목을 통과시키면 신규상장이 섞이고, 막으면 오래된 종목이 사라진다.
    #   후자가 선택편향으로 덜 위험하므로 '모르면 탈락'으로 두고 그 건수를 로그에 남긴다.
    snap["g_age"] = age.notna() & (age >= SPEC_UNIV["min_listing_days"])
    n_noage = int(age.isna().sum())

    # 자본잠식·재무결측 — PIT(공시 접수일 기준) 로 붙인다
    snap = attach_pit_financials(snap, fin)
    eq, cap = snap.get("equity"), snap.get("capital")
    if eq is None:
        snap["g_solvent"], snap["g_fin"] = True, False
        LOG.warn("재무(자본총계)를 붙이지 못해 자본잠식 게이트가 무력화됩니다 — "
                 "유니버스가 명세와 달라집니다. 캐시의 재무 테이블을 확인하세요.")
    else:
        impaired_full = eq <= 0
        impaired_part = (cap.notna() & (eq < cap)) if cap is not None else pd.Series(False, index=eq.index)
        snap["g_solvent"] = ~(impaired_full | impaired_part).fillna(False)
        snap["g_fin"] = eq.notna() & snap.get("revenue", pd.Series(np.nan, index=eq.index)).notna()
        RUNLOG["impair_full_only_delta"] = int((impaired_part & ~impaired_full).sum())
        LOG.info(f"자본잠식 = 자본총계 ≤ 0(완전) 또는 자본총계 < 자본금(부분). "
                 f"부분잠식만으로 탈락한 (종목×시점) {RUNLOG['impair_full_only_delta']:,}건 — "
                 f"완전잠식만 적용했다면 이만큼 더 남았을 것입니다(진단용, 대안 백테스트 아님).")

    gates = ["g_amount", "g_common", "g_form", "g_age", "g_solvent", "g_fin"]
    snap["eligible"] = snap[gates].all(axis=1)

    # ── 유니버스 감쇠 감사 ─────────────────────────────────────────────────────────────
    tot = len(snap)
    rows, alive = [], pd.Series(True, index=snap.index)
    for g, label in zip(gates, ["거래대금 ≥ 1억", "보통주", "비스팩/비리츠", "상장 ≥ 180일",
                                "비자본잠식", "재무 비결측"]):
        before = int(alive.sum())
        alive &= snap[g]
        rows.append([label, f"{before:,}", f"{int(alive.sum()):,}",
                     f"−{before - int(alive.sum()):,}",
                     f"{100*(before-int(alive.sum()))/max(before,1):.1f}%"])
    LOG.table(rows, ["게이트", "적용 전", "적용 후", "탈락", "탈락률"], ["l", "r", "r", "r", "r"],
              title=f"유니버스 감쇠 감사 — (종목×리밸) {tot:,}셀 중 적격 {int(snap['eligible'].sum()):,}셀")
    if n_noage:
        LOG.info(f"상장일 미상으로 탈락한 셀 {n_noage:,}건 (신규상장 혼입 방지를 위한 보수 처리).")
    PIPE.io("OUT", "MEM", "eligibility", snap)
    return snap


def build_universe(elig: pd.DataFrame) -> pd.DataFrame:
    """적격 종목 중 시총 하위 N. as-of 리밸런싱 시점마다 새로 뽑는다."""
    e = elig[elig["eligible"] & elig["market_cap"].notna() & (elig["market_cap"] > 0)].copy()
    e = e.sort_values(["rebal", "market_cap"])
    e["cap_rank"] = e.groupby("rebal", observed=True)["market_cap"].rank(method="first")
    e["u250"] = e["cap_rank"] <= SPEC_UNIV["main_n"]
    e["u500"] = e["cap_rank"] <= SPEC_UNIV["aux_n"]
    cnt = e.groupby("rebal")["u250"].sum()
    short = int((cnt < SPEC_UNIV["main_n"]).sum())
    LOG.ok(f"유니버스 구성 완료 — U250 리밸당 평균 {cnt.mean():.1f}종목 "
           f"(최소 {int(cnt.min())}, 최대 {int(cnt.max())})")
    if short:
        LOG.warn(f"적격 종목이 {SPEC_UNIV['main_n']}개에 못 미친 리밸 시점 {short:,}개 — "
                 f"그 시점은 있는 만큼만 담습니다(빈자리를 부적격으로 채우지 않습니다).")
    RUNLOG["u250_mean_count"] = float(cnt.mean())
    PIPE.io("OUT", "MEM", "universe", e)
    return e
