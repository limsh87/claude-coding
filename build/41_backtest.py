

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델                                                             ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 '다음 거래일 시가'. 당일 종가 체결 금지(미래누수).   ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(누락 = 생존자편향).         ║
# ║  · 롱온리 (공매도 불가) — 음의 신호는 청산 게이트로만 쓴다.                                 ║
# ║  · 청산 규칙이 진입 논리와 같은 언어를 쓴다: Δlog M 이 Δlog E 수준까지 확장 완료 시 청산.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5          # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10             # 제곱근 충격 계수

# 보유 중 패널에서 사라진 종목을 '폐지 진행'으로 볼 최대 대기 기간.
#   KRX 는 매매거래정지 → 개선기간 → 정리매매 → 상장폐지 경로가 흔히 3~24개월이다.
#   거래가 정지되면 그 달부터 패널에 행이 생기지 않으므로, 폐지일이 '다음 달 안'일 때만
#   -100% 를 물리면 이 경로가 통째로 0% 청산으로 빠져나간다(생존자편향).
DELIST_VANISH_HORIZON_M = 24


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격. 참여율이 높을수록 급격히 비싸진다 — 소형주 가중이 여기서 나온다."""
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(SLIPPAGE_K * math.sqrt(part))


def exit_gate(dm, de) -> bool:
    """청산 판단: '진입 시의 목표상태'를 벗어났는가.

    진입 조건(axis_D)은 ΔlogE > 0 AND 시장이 아직 자본화를 안 함(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다. 알파 소진(원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다. 논거 무효

    ★ 예전엔 `dm >= de and de > 0` 이었다. 앞 조건이 참이면 뒤 조건도 거의 항상 참이라
      보이지만, 실제로 걸러지는 건 'de <= 0' 인 전 구간 — 즉 논거가 깨진 종목을 청산하는
      경로가 통째로 닫혀 있었다. 그 종목들은 보유상한(24개월)까지 자리를 차지했다.
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 종목 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '데이터프레임에 먼저 나온 행'을 고른다. 패널은
      ["code","month"] 로 정렬되어 있으므로 그건 곧 '종목코드가 작은 순'이다. 동점이 드물면
      무해하지만, 실측상 월 보유종목의 상당수가 동점 구간에서 결정됐고 행 순서를 섞으면
      포트폴리오가 통째로 바뀌었다 — 즉 보유종목이 데이터가 아니라 정렬의 함수였다.
      그래서 ① 1차 키는 signal_col, ② 2차 키는 랭크 이전의 원 Signal(정보량이 더 많다),
      ③ 최후에만 code 로 깬다. 이러면 동점 처리가 결정적이면서 '왜 그 종목인가'가 설명된다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "code") if c in df.columns and c != signal_col]
    asc = [False] + [False if c == "Signal" else True for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중(§8.5).
    비중 상한은 코드 상수로 이미 못박혀 있다 — 드로다운 한가운데서 정하지 않는다."""
    s = sub["Signal_rank"].fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    lo, hi = float(np.min(s)), float(np.max(s))
    if spread < 1e-6 or (hi - lo) < 1e-12:
        w = np.full(len(s), 1.0 / len(s))
    else:
        # ★ 예전엔 raw = clip(s - median, 0, None) + 1e-9 였다. 그러면 **선정된 종목의 정확히
        #   절반**(중앙값 이하)이 raw=1e-9 로 깔려 비중이 사실상 0 이 된다 — 25종목을 골랐다고
        #   로그에 찍으면서 실제로는 12~13종목만 보유하는 셈이고, '평균종목수' 지표가 실효
        #   보유수의 2배 넘게 부풀려진다. 분산 효과도 그만큼 과대평가된다.
        #   선정집합 내부 순위로 바꾸면 모든 선정 종목이 양(+)의 비중을 갖고,
        #   집중도는 conc 하나로만 조절된다(문서화된 의도 그대로).
        r = pd.Series(s).rank(method="average").to_numpy(dtype=float)   # 1..n
        conc = min(2.0, 0.5 + spread * 8.0)          # 격차 클수록 집중
        w = (r / r.sum()) ** conc
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    # 종목별 상한 = min(정책 상한, 유동성 상한). 유동성 상한은 20일 평균거래대금의 X%.
    adv = sub["adv20"].fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                       POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))

    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다(합이 1보다 작아지면 전부 커진다).
    #   상한에 걸린 종목은 고정하고 나머지에만 잔여 비중을 재배분하는 water-filling 으로 강제한다.
    w = np.clip(w, 0.0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    free = np.ones(len(w), dtype=bool)
    for _ in range(24):
        over = free & (w > cap)
        if not over.any():
            break
        w[over] = cap[over]
        free &= ~over
        rem = 1.0 - w[~free].sum()
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem) if pool > 1e-12 else (rem / free.sum())
    if w.sum() > 1.0 + 1e-9:                 # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 종목수가 적으면 이 함수는 조용히 '현금 70% 펀드'를 만든다 ★★
    #    cap 은 실질적으로 언제나 POS_MAX_WEIGHT(0.12) 다. liq_cap = adv×0.10/3천만원 인데
    #    패널에 남으려면 adv ≥ 3억이므로 liq_cap ≥ 1.0 — 유동성 상한은 전 구간 사문화다.
    #    그래서 종목이 n 개면 Σw ≤ 0.12n 이고, n=3 이면 **자동으로 현금 64%** 가 된다.
    #    7회차 스몰캡 팔이 월평균 2.5종목이었다 → 사실상 현금 70% 포트폴리오였는데,
    #    그것을 100% 투자된 전체 팔과 나란히 놓고 "차이는 규모 대역 하나" 라고 보고했다.
    #    현금 비중이 성과 차이의 지배적 원인인데 표 어디에도 그 말이 없었다.
    #  → 현금 비중을 **명시적으로 계산해 돌려준다.** 임의로 채워 넣지 않는다(그건 상한을
    #    뚫는 것이다). 대신 호출자가 이 사실을 표에 쓰게 만든다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    out = sub.assign(weight=w)
    out.attrs["cash"] = float(max(0.0, 1.0 - float(np.nansum(w))))
    return out


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                 sec: pd.DataFrame, signal_col: str = "Signal_rank",
                 top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                 label: str = "TCD", audit: bool = True) -> dict:
    # ★ audit=False 는 강건성 스위트의 재실행용이다. 같은 달을 10여 번 다시 세면
    #   감쇠 원장의 min/max·관측월이 무의미해지고, 팔 태그까지 뒤섞인다(잔존율 113.7%).
    #   본선·비교팔만 원장에 남긴다.
    _audit_saved = getattr(uni, "audit_on", True)
    if not audit:
        uni.audit_on = False
    try:
        # ★ 진단 경고는 **본선·비교팔에서만** 낸다. 강건성 스위트는 같은 엔진을 20여 회
        #   재실행하므로, 그대로 두면 같은 경고가 20번 반복되어 정작 읽어야 할 표가
        #   스크롤 밖으로 밀려난다. 로그가 시끄러우면 아무도 읽지 않고, 안 읽히는 경고는
        #   없는 경고와 같다. 재실행분은 DEBUG 로 내린다(사실은 그대로 남는다).
        return _run_backtest_inner(P, months, uni, sec, signal_col, top_pct,
                                   apply_costs, label, verbose=bool(audit))
    finally:
        uni.audit_on = _audit_saved


def _run_backtest_inner(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                        sec: pd.DataFrame, signal_col: str = "Signal_rank",
                        top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                        label: str = "TCD", verbose: bool = True) -> dict:
    _say = LOG.warn if verbose else LOG.debug
    _tbl = LOG.table if verbose else (lambda *a, **k: None)
    mkt = sec.set_index("code")["market"].astype(str).to_dict()
    delist = uni.delisting_map()
    # 폐지 '유형' — 흡수합병·스팩해산은 -100% 가 아니다. 없으면 전부 -100%(종전 동작).
    dkind = uni.delist_kind_map() if hasattr(uni, "delist_kind_map") else {}
    hold: Dict[str, dict] = {}
    rows, trades, holdings_log = [], [], []
    prev_w: Dict[str, float] = {}
    # 폐지 손실을 이미 반영한 종목 — 같은 종목에 -100% 를 두 번 물리지 않기 위한 장부
    delist_realized: set = set()
    vanished_delisted = vanished_other = vanished_transfer = 0
    unknown_ret_n, unknown_ret_w = 0, 0.0        # 수익을 알 수 없어 보유하지 않은 것으로 둔 건수
    # 종목별 '패널에 마지막으로 등장한 달'. 사라진 종목이 나중에 돌아오는지(유동성 회복 등)를
    # 판별해야 '거래정지→폐지'와 '일시적 유니버스 이탈'을 가를 수 있다.
    _pm = P[P["month"].isin(months)] if len(P) else P
    last_seen = (_pm.groupby("code", observed=True)["month"].max().to_dict()
                 if len(_pm) else {})

    for i, m in enumerate(months):
        sub = P[(P["month"] == m)].copy()
        if sub.empty:
            rows.append({"month": m, "ret": 0.0, "n": 0, "turnover": 0.0, "cost": 0.0})
            continue
        elig = sub[(sub["VETO"] == 1) & (sub["FLOOR"] == 1) & sub[signal_col].notna() &
                   sub["exec_px"].notna()]
        # ★ 감쇠 감사는 '누적 교집합'으로 기록한다. 게이트별 독립 집계를 깔때기처럼 보여주면
        #   잔존율이 100%를 넘는 무의미한 숫자가 나온다(게이트가 서로 포함관계가 아니므로).
        g_liq = sub[sub["V6"] == 1]
        g_veto = g_liq[g_liq["VETO"] == 1]
        g_floor = g_veto[g_veto["FLOOR"] == 1]
        uni.audit_row("유동성필터", m, g_liq["code"].tolist())
        uni.audit_row("거부권통과", m, g_veto["code"].tolist())
        uni.audit_row("하한선통과", m, g_floor["code"].tolist())

        # 종목별 조회를 dict 로 미리 만든다. sub[sub.code==c] 를 종목마다 돌리면
        # 백테스트가 강건성 스위트에서 10여 회 재실행될 때 그 비용이 그대로 곱해진다.
        need_cols = [c for c in ("adv20", "fwd_ret", "VETO", "dlog_M", "dlog_E", signal_col)
                     if c in sub.columns]
        rec: Dict[str, dict] = {}
        for _c, *_v in sub[["code"] + need_cols].itertuples(index=False, name=None):
            rec[_c] = dict(zip(need_cols, _v))

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, k, signal_col)
        uni.audit_row("최종선정", m, pick["code"].tolist())

        # 청산 게이트: Δlog M 이 Δlog E 수준까지 확장 완료 / 보유상한 / 거부권
        keep = []
        vanished_w = 0.0          # 이달 상각(회수 불가)된 자본 비중 — 장부에서 자리를 차지한다
        for c, h in list(hold.items()):
            r0 = rec.get(c)
            if r0 is None:
                # ★★ 패널에서 사라진 보유 종목 (C2 생존자편향의 마지막 구멍) ★★
                #   예전엔 그냥 continue 였다. 그러면 '거래정지 → 몇 달 뒤 상장폐지' 경로가
                #   손실 0%로 조용히 청산된다. 거래가 끊긴 종목은 월 패널에 행이 생기지 않으므로
                #   아래 fwd_ret 기반 -100% 규칙이 **한 번도 발동하지 못한다.**
                #   실제로는 정리매매가 없으면 -100% 다. 사라진 이유를 갈라서 처리한다:
                #     · 폐지가 임박/진행 중  → -100% (이미 반영한 종목은 제외)
                #     · 그 외(유니버스 이탈) → 직전가로 청산, 그 달 수익 0% (로그로 드러냄)
                #   ★ 창을 '다음 달까지'로 잡으면 안 된다. 거래가 정지되면 그 달부터 패널에
                #     행이 없어지는데, 실제 폐지일은 3~24개월 뒤다. 그래서 '이 달 이후 패널에
                #     다시 나타나지 않는가(=영구 이탈)' + '폐지일이 그 안에 있는가'로 판정한다.
                dl = delist.get(c)
                w_prev = prev_w.get(c, 0.0)
                never_back = m > last_seen.get(c, m)
                terminal = (dl is not None and pd.notna(dl) and never_back
                            and dl <= m + pd.DateOffset(months=DELIST_VANISH_HORIZON_M))
                if w_prev > 0 and terminal and c not in delist_realized:
                    # ★ 폐지 유형에 따라 청산가가 다르다. 흡수합병·완전자회사화·스팩해산은
                    #   전액손실이 아니다(대가로 인수기업 주식 또는 예치금을 받는다).
                    #   그런 건을 -100% 로 계상하면 없는 손실을 매년 지어낸다.
                    #   모르는 사유('unknown')는 보수적으로 -100% 를 유지한다.
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        vanished_transfer += 1      # 직전가 청산 = 그 달 수익 0%
                    else:
                        vanished_w += float(w_prev)     # 전액손실 — 그만큼의 자본이 사라진다
                        vanished_delisted += 1
                        holdings_log.append({"month": m, "code": c, "weight": float(w_prev),
                                             "ret": -1.0, "signal": np.nan,
                                             "event": "delist_vanished"})
                    delist_realized.add(c)
                elif w_prev > 0:
                    vanished_other += 1
                continue
            dm, de = r0.get("dlog_M"), r0.get("dlog_E")
            exited = False
            if r0.get("VETO", 1) == 0:
                exited = True                                    # 거부권 발동 시 즉시 강제청산
            elif h["months"] >= HOLD_MAX_MONTHS:
                exited = True
            elif exit_gate(dm, de):
                exited = True                        # 목표상태 이탈 (재분류 완료 또는 논거 무효)
            if not exited:
                keep.append(c)
        target = pd.concat([pick, sub[sub["code"].isin(keep) & ~sub["code"].isin(pick["code"])]],
                           ignore_index=True) if len(keep) else pick
        if len(target) > PORTFOLIO_MAX_NAMES:
            target = _top_n(target, PORTFOLIO_MAX_NAMES, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}
        cash_w = float(target.attrs.get("cash", 0.0)) if len(target) else 1.0
        # ★ 이미 -100% 로 상각한 종목(=체결 자체가 불가능하다)에 매도비용을 다시 물리지 않는다.
        #   prev_w 에는 남아 있으므로 비용 루프가 '매도'로 잡고, rec 에 행이 없어 adv=0 →
        #   기본 슬리피지 2% + 증권거래세까지 부과했다. 존재하지 않는 거래에 대한 비용이다.
        _no_trade = {c for c in prev_w if c not in w_new and c in delist_realized}
        _cost_codes = (set(w_new) | set(prev_w)) - _no_trade
        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in _cost_codes)

        cost = 0.0
        if apply_costs:
            for c in _cost_codes:
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                c_bps = COMMISSION_BPS / 1e4
                sl = slippage(notional, adv)
                tx = sell_tax(m, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (c_bps + sl + tx)

        # ══════════════════════════════════════════════════════════════════════════════════
        #  다음 달 수익 — **비중 장부가 하나로 닫혀야 한다**
        #
        #  ★★ 예전 구조의 결함 ★★  ret 은 w_new(합 ≈ 1) 위에서 계산한 뒤,
        #    `ret += vanished_loss` 로 지난달 비중 w_prev 기반 손실을 **덧붙였다.**
        #    그 달의 총노출이 1 + Σw_van 이 되어, 폐지가 난 달마다 없는 자본으로 손실을
        #    추가로 낸 셈이다. 상각된 종목의 자본은 이미 사라졌으므로 신규 배분의 분모에서
        #    빠져야 한다 — 더하는 것이 아니라 **자리를 차지해야** 한다.
        #  → 장부를 하나로 닫는다:  1 = Σ(폐지상각분) + (1−Σ폐지상각분) × [Σw_new + 현금]
        # ══════════════════════════════════════════════════════════════════════════════════
        w_van = float(min(1.0, max(0.0, vanished_w)))     # 이달 상각된(회수 불가) 자본 비중
        alive = max(0.0, 1.0 - w_van)
        ret_alive = 0.0
        unknown_w_m = 0.0                      # 수익을 몰라 보유하지 않은 자본(현금으로 남는다)
        _is_last = (i == len(months) - 1)      # 마지막 달의 fwd_ret 결측은 결함이 아니다
        for c, w in w_new.items():
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            dl = delist.get(c)
            _ev = ""
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                # ★ 상장폐지: 정리매매 최종가가 있으면 그것을 쓴다. 없을 때만 유형을 본다.
                #   부실·사유불명 → -100%(C2 원칙7). 합병·스팩해산 → 직전가 청산(0%).
                if not np.isfinite(fr):
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        fr = 0.0
                        vanished_transfer += 1
                    else:
                        fr = -1.0
                delist_realized.add(c)      # 이 종목의 폐지 손익은 여기서 확정 — 재차감 금지
                _ev = "delist"
            if not np.isfinite(fr):
                # ★★ '수익을 모른다'와 '수익이 0%'는 다른 사실이다 ★★
                #   여기 걸리는 행은 ① 무결성 게이트가 버린 가격제한 밖 관측 ② 월 연속성이
                #   끊긴 구간 ③ 체결가 결측이다. 셋 다 **그 달 그 종목을 보유했다고 말할 수
                #   없는** 상태다. 0% 로 덮으면 우측꼬리 의존 전략에서 가장 큰 상승·하락이
                #   정확히 사라지고, 그 자리에 '무사고'라는 없는 사실이 들어간다.
                #   → 보유하지 않은 것으로 처리하고(비중 0) 그 자본은 현금으로 남긴다.
                #     지어내지 않고, 조용히 0 으로 만들지도 않는다. 건수는 아래에서 보고한다.
                # ★ 마지막 달은 '다음 달'이 존재하지 않으므로 fwd_ret 이 결측인 것이 정상이다.
                #   그것을 데이터 결함처럼 세면 매 실행 마지막 달의 전 종목이 경고에 잡힌다.
                if not _is_last:
                    unknown_ret_n += 1
                    unknown_ret_w += float(w)
                unknown_w_m += float(w)          # 이 달의 미투자 자본(현금으로 남는다)
                holdings_log.append({"month": m, "code": c, "weight": 0.0, "ret": np.nan,
                                     "signal": np.nan, "event": "ret_unknown"})
                continue
            ret_alive += w * fr
            _s = _r.get(signal_col)
            holdings_log.append({"month": m, "code": c, "weight": w * alive, "ret": fr,
                                 "signal": float(_s) if _s is not None and pd.notna(_s) else np.nan,
                                 "event": _ev})
        # 상각분은 -100%. 살아남은 자본만 신규 배분의 수익을 받는다.
        ret = alive * ret_alive + w_van * (-1.0)
        # ★ 롱온리 한 달 손실의 하한은 −100% 다(장부가 닫혀 있으면 구조적으로 성립하지만,
        #   부동소수점·데이터 이상까지 감안해 마지막 방어선을 남긴다).
        ret = max(-1.0, float(ret)) if np.isfinite(ret) else 0.0
        ret_net = ret - cost
        rows.append({"month": m, "ret": ret_net, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost,
                     # ★ 현금 비중을 반드시 기록한다. 종목이 9개 미만이면 상한(0.12) 때문에
                     #   자동으로 현금이 생기는데, 그 사실이 표에 없으면 '규모 대역 차이'로
                     #   읽히는 것이 실은 '현금 70% vs 현금 0%' 의 차이가 된다.
                     # cash 는 ① 비중상한 때문에 못 채운 몫 ② 수익을 몰라 보유하지 않은 몫
                     #   둘을 합친 값이다. ②를 빼놓으면 "현금으로 남겼다"는 로그와 표가
                     #   서로 다른 말을 하게 된다.
                     "cash": float(min(1.0, max(0.0, cash_w + unknown_w_m))),
                     "invested": float(alive * max(0.0, 1.0 - cash_w - unknown_w_m))})
        for c in list(hold):
            if c in w_new:
                hold[c]["months"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"months": 0})
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0).clip(lower=-1.0)).cumprod()
    H = pd.DataFrame(holdings_log)
    if vanished_delisted or vanished_other or vanished_transfer:
        (LOG.info if verbose else LOG.debug)(f"[{label}] 보유 중 청산된 종목 — 부실·사유불명 폐지 {vanished_delisted}건은 "
                 f"-100%, 합병·완전자회사화·스팩해산 {vanished_transfer}건은 직전가 청산(0%), "
                 f"그 외 유니버스 이탈 {vanished_other}건도 직전가 청산. "
                 f"조용히 사라지게 두지 않습니다(C2).")
        # ★★ 이 경고는 3년 내내 침묵하고 있었다 ★★
        #   `if not dkind` 는 **컬럼이 없을 때**만 참이다. 그런데 종목마스터 수집부는
        #   원본에 사유가 없어도 delist_reason 을 **빈 문자열 컬럼으로 항상 만든다**
        #   (10_ingest_universe.py:324). 그러면 dkind = {코드: "unknown"} 로 채워져
        #   비어 있지 않고, 모든 폐지가 조용히 -100% 로 계상되면서 경고는 뜨지 않는다.
        #   → 사유가 실제로 분류됐는지를 **값으로** 판정한다.
        _kinds = Counter(dkind.values()) if dkind else Counter()
        _unk = _kinds.get("unknown", 0)
        _tot = max(1, sum(_kinds.values()))
        if _kinds:
            _tbl([[k, f"{v:,}", f"{100*v/_tot:.0f}%",
                        "직전가 청산(0%)" if k in DELIST_NOT_WIPEOUT else "전액손실(-100%)"]
                       for k, v in _kinds.most_common()],
                      ["폐지 유형", "종목수", "비율", "청산 처리"], ["l", "r", "r", "l"],
                      title=f"[{label}] 상장폐지 사유 분류 — 청산가를 가르는 유일한 근거")
        if (not dkind) or _unk / _tot > 0.30:
            _say(f"[{label}] 폐지 사유를 분류하지 못한 종목이 {_unk:,}/{_tot:,}"
                     f"({100*_unk/_tot:.0f}%)이라 그만큼을 **전액손실(-100%)** 로 계상했습니다. "
                     f"실측상 폐지의 절반가량(흡수합병·스팩해산)은 전액손실이 아니므로 "
                     f"성과가 **과소평가**됩니다(U-MID 대역 기준 연 -2%p 안팎). "
                     f"종목마스터의 delist_reason 이 빈 문자열이 아닌지 확인하세요 — "
                     f"컬럼은 항상 만들어지므로 '컬럼 존재'만으로는 판정할 수 없습니다.")
    if unknown_ret_n:
        _say(f"[{label}] 다음 달 수익을 알 수 없는 보유 {unknown_ret_n:,}건"
                 f"(비중 합계 {unknown_ret_w:.2f})을 **보유하지 않은 것으로** 처리했습니다. "
                 f"가격 무결성 게이트가 버린 관측·월 연속성 단절·체결가 결측이 원인입니다. "
                 f"0% 로 덮으면 '무사고'라는 없는 사실이 장부에 들어갑니다 — "
                 f"그 자본은 현금으로 남겼고, 이 사실은 성과표의 현금비중에 반영됩니다.")
    _cash = float(R["cash"].mean()) if "cash" in R.columns and len(R) else 0.0
    if _cash > 0.05:
        _say(f"[{label}] 월평균 현금 비중이 {_cash:.0%} 입니다. 종목별 비중 상한"
                 f"(POS_MAX_WEIGHT={POS_MAX_WEIGHT:.0%})과 선정 종목수의 곱이 1 에 못 미치면 "
                 f"나머지는 자동으로 현금이 됩니다 — 종목이 "
                 f"{math.ceil(1/POS_MAX_WEIGHT)}개 미만인 달이 그렇습니다. "
                 f"이 팔의 성과를 다른 팔과 비교할 때 **현금 비중 차이**를 먼저 보세요. "
                 f"규모 대역의 효과로 읽으면 틀립니다.")
    return {"returns": R, "holdings": H, "label": label,
            "vanished_delisted": vanished_delisted, "vanished_other": vanished_other,
            "unknown_ret_n": unknown_ret_n, "cash_mean": _cash,
            "delist_kinds": dict(Counter(dkind.values()) if dkind else Counter())}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 이 함수가 nan 을 돌려주면 강건성 판정이 '조용히 FAIL' 로 떨어진다 ★★
    #    R0 은 `isfinite(cal_s) and isfinite(cal_b) and cal_s > cal_b` 로 판정한다.
    #    벤치마크가 nan 이면 세 조건 중 둘째가 거짓이라 **'Calmar 미달 — 폐기 대상'** 이
    #    출력된다. 실제로는 비교조차 못 한 것인데 '졌다'고 보고한 셈이다(7회차).
    #    → 여기서 세 가지를 강제한다:
    #      ① 비유한 수익률은 계산에서 제외한다(0 으로 바꾸지 않는다 — 그건 '수익 0'이라는
    #         없는 사실을 만든다). 몇 개를 제외했는지 반환값에 남긴다.
    #      ② 롱온리 월수익의 하한은 −100% 다. 보유분을 전부 잃어도 그 이상은 잃을 수 없다.
    #         (폐지 −100% 를 여러 종목에 동시에 물리면 합계가 −1 밑으로 내려가 자본이
    #          음수가 되고, 그 뒤 복리·MDD 가 전부 무의미해진다)
    #      ③ 자본이 0 이하로 떨어지면 CAGR 은 nan 이 아니라 **−100%** 다. 전액손실은
    #         '알 수 없음'이 아니라 확정된 사실이다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 선택 컬럼을 필수처럼 읽지 않는다 (R10 이 100% 확률로 오판정하던 자리) ★★
    #    반환 dict 리터럴이 `float(R["n"].mean())` 을 **무조건** 평가했다. 그런데 호출자
    #    중에는 수익률만 가진 프레임을 넘기는 곳이 있다 — R10 의 정책제외 구간 통계가
    #    그렇다(build_v3/50_robust.py). 그러면 KeyError 가 나고, 호출부의 넓은 except 가
    #    그것을 삼켜 off=nan 이 된다. 그 nan 은 `ok = isfinite(off) and ...` 에서 False 가
    #    되어 **"정책 구간을 빼면 알파가 사라짐 — TP_N1 폐기 대상"** 으로 출력됐다.
    #    측정에 실패한 것을 확정된 반증으로 보고한 것이고, 데이터와 무관하게 항상 그랬다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    def _opt(colname: str) -> float:
        try:
            return float(pd.to_numeric(R[colname], errors="coerce").mean())
        except Exception:                                        # noqa
            return np.nan
    raw = pd.to_numeric(R["ret"], errors="coerce").to_numpy(dtype=float)
    n_bad = int((~np.isfinite(raw)).sum())
    r = np.where(np.isfinite(raw), raw, 0.0)
    r = np.clip(r, -1.0, None)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1 + r)
    # 자본이 한 번 0 이하가 되면 그 뒤는 존재하지 않는다 — 0 으로 고정해 복리를 끊는다.
    if (eq <= 0).any():
        first = int(np.argmax(eq <= 0))
        eq[first:] = 0.0
    eq = np.where(np.isfinite(eq), eq, 0.0)
    years = n / 12.0
    if years <= 0:
        cagr = np.nan
    elif eq[-1] > 0:
        cagr = eq[-1] ** (1 / years) - 1
    else:
        cagr = -1.0                       # 전액손실 — 판정 유보가 아니라 확정된 사실
    vol = r.std(ddof=1) * math.sqrt(12) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(12) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    # peak 가 0 이 될 수 있다(첫 달 −100%). 0 나눗셈은 nan 을 만들고 MDD 가 통째로 사라진다.
    dd = np.where(peak > 0, eq / np.where(peak > 0, peak, 1.0) - 1.0, -1.0)
    mdd = float(np.nanmin(dd)) if n else np.nan
    if not np.isfinite(mdd):
        mdd = np.nan
    uw, mx, cur = 0, 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    _cal = (cagr / abs(mdd)) if (np.isfinite(cagr) and np.isfinite(mdd) and mdd < 0) else np.nan
    out = {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": ((cagr - rf) / vol if np.isfinite(cagr) and vol and np.isfinite(vol)
                   and vol > 0 else np.nan),
        "Sortino": ((cagr - rf) / dvol if np.isfinite(cagr) and dvol and np.isfinite(dvol)
                    and dvol > 0 else np.nan),
        "MDD": mdd, "Calmar": _cal,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1), "평균종목수": _opt("n"),
        "월평균회전율": _opt("turnover"), "월평균비용": _opt("cost"),
        # ★ 현금 비중은 선택 지표가 아니라 **비교의 전제**다. 종목수가 적으면 비중 상한
        #   때문에 자동으로 현금이 쌓이는데, 그 사실 없이 두 팔의 CAGR 을 나란히 놓으면
        #   '규모 대역의 효과'로 읽히는 것이 실은 '투자비중의 차이'가 된다.
        "월평균현금비중": _opt("cash"),
    }
    # ★ 몇 개를 제외했는지 숨기지 않는다. 0 이 아니면 그 시계열은 이미 손상된 것이고,
    #   그 사실이 지표보다 먼저 읽혀야 한다.
    if n_bad:
        out["비유한수익률제외"] = n_bad
    return out


def right_tail_contribution(bt: dict) -> dict:
    """★ 이 전략은 IR 이 아니라 우측 꼬리에 의존한다. 상위 종목 제외 시 성과가 사라지는지
    반드시 측정하고 리포트에 명시한다(§10.2)."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    # ★ 분모(총기여)가 실제 누적수익과 다르면 '상위 5%가 총기여의 180%' 같은 수치가 나온다.
    #   두 가지를 맞춘다: ① 폐지 상각(-100%)도 보유 기록에 들어가 있어야 한다
    #   (delist_vanished 이벤트로 append 하도록 고쳤다) ② 수익을 알 수 없어 보유하지 않은
    #   것으로 처리한 행(ret_unknown)은 비중 0·수익 NaN 이므로 기여에서 자동 제외된다.
    H = H[pd.to_numeric(H["ret"], errors="coerce").notna()]
    if H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {}
    base = float(contrib.sum())
    for q, lab in ((0.05, "상위5%"), (0.10, "상위10%"), (0.01, "상위1%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후 총기여"] = base - float(contrib.iloc[:k].sum())
    out["총기여"] = base
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


INDEX_TABLE = "index_ohlcv_daily"          # 공용 인덱스 — 다른 전략도 그대로 재사용한다


def _index_daily(sym: str, lo: pd.Timestamp, hi: pd.Timestamp) -> Optional[pd.DataFrame]:
    """지수 일봉을 **공용 캐시 우선**으로 확보한다.

    ★★ 절대1원칙 ★★ 신규로 수집되는 데이터는 예외 없이 구글드라이브 공용/전용 인덱스에
      저장돼 재호출 가능해야 한다. 예전 이 함수는 매 실행 FDR 에서 KS11/KQ11 을 새로 받고
      **어디에도 저장하지 않았다** — 이 모듈에는 VAULT 참조가 한 줄도 없었다.
      강건성 스위트가 R0 을 부를 때마다 같은 네트워크 왕복이 반복됐고,
      네트워크가 막힌 환경에서는 지수 벤치마크가 통째로 사라졌다(그리고 조용히 넘어갔다).
    """
    cached = None
    try:
        cached = VAULT.get_table(INDEX_TABLE, scope="shared")
    except Exception:                                            # noqa
        cached = None
    have = None
    if cached is not None and len(cached) and "symbol" in cached.columns:
        have = cached[cached["symbol"].astype(str) == sym].copy()
        if len(have):
            have["date"] = as_ts_series(have["date"])
            have = have.dropna(subset=["date"])
            if len(have) and have["date"].min() <= lo and have["date"].max() >= hi:
                return have.sort_values("date")                  # 캐시가 구간을 덮는다 → 호출 없음
    fresh = None
    if fdr is not None:
        try:
            limiter("naver").wait()
            r = fdr.DataReader(sym, lo, hi)
            if r is not None and len(r):
                r = r.reset_index()
                r.columns = [str(c).lower() for c in r.columns]
                r["date"] = as_ts_series(r[r.columns[0]])
                r["symbol"] = sym
                fresh = r[["symbol", "date"] + [c for c in ("open", "high", "low", "close",
                                                            "volume") if c in r.columns]]
        except Exception as e:                                   # noqa
            LOG.debug(f"지수 {sym} 수집 실패({type(e).__name__}) — 캐시분으로 진행합니다.")
    if fresh is None or not len(fresh):
        return have if (have is not None and len(have)) else None
    # 캐시와 합쳐 **넓어지는 방향으로만** 저장한다(좁혀 덮어쓰기 금지 — 절대1원칙).
    parts = [p for p in (cached, fresh) if p is not None and len(p)]
    merged = pd.concat(parts, ignore_index=True)
    merged["date"] = as_ts_series(merged["date"])
    merged = (merged.dropna(subset=["date", "symbol"])
                    .drop_duplicates(["symbol", "date"], keep="last")
                    .sort_values(["symbol", "date"]).reset_index(drop=True))
    try:
        VAULT.put_table(INDEX_TABLE, merged, scope="shared", domain="price",
                        source="fdr: KS11/KQ11 지수 일봉 (R0 벤치마크 · 타 전략 재사용 가능)")
    except Exception as e:                                       # noqa
        LOG.debug(f"지수 캐시 저장 실패({type(e).__name__}) — 계산에는 영향 없음")
    return merged[merged["symbol"].astype(str) == sym]


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    # ★ 끝을 2개월 늘린다. 아래 shift(-1) 때문에 마지막 달이 NaN 이 되면
    #   비교표의 dropna 에서 그 달이 조용히 빠진다.
    _lo = months[0] - pd.offsets.MonthEnd(2)
    _hi = months[-1] + pd.offsets.MonthEnd(2)
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = _index_daily(sym, _lo, _hi)
        if d is None or len(d) == 0:
            continue
        d = d.copy()
        d["date"] = as_ts_series(d["date"])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        # ★★ 위상 정렬 ★★ 전략 수익률은 '월 m 행 = 월 m+1 에 실현된 수익'(fwd_ret) 규약이다.
        #   지수를 pct_change() 그대로 두면 한 달 어긋난 채로 차분되어, 시장요인이 상쇄되기는
        #   커녕 두 배로 들어간다. 초과수익의 t통계량이 절반 수준으로 눌린다.
        s = d.groupby("month")["close"].last().pct_change().shift(-1)
        out[name] = s.reindex(months)
    return out
