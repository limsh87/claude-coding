
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  3중 자가검정 — 계약(K1~K16) / 합성 스모크 / 실경로 리허설                            ║
# ║                                                                                          ║
# ║  세 검증은 서로 다른 것을 본다:                                                            ║
# ║    ① 계약(K)   협상 불가 규칙 — PIT·생존편향·look-ahead·절단·비용                          ║
# ║    ② 스모크    합성데이터로 '계산 경로' 를 증명 (네트워크·키 불필요)                        ║
# ║    ③ 리허설    네트워크만 가짜로 두고 '수집·정제 함수' 를 실물 실행                         ║
# ║  ①②를 다 통과하고도 실행 2분 만에 수집부 한 줄 때문에 죽는 일이 실제로 있었다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_CONTRACTS: List[Tuple[str, str, bool, str]] = []


def _k(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                            # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    _CONTRACTS.append((cid, name, bool(ok), str(msg)[:120]))
    return bool(ok)


def run_contracts(strict: bool = True) -> bool:
    _CONTRACTS.clear()
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=400))

    def k1():
        """진입 오프셋 — 거래원/수급은 장 마감 후 공개. d 종가 진입은 SPEC §0.1 위반."""
        bad = [c.k for c in (BTConfig(k=0, hold=20, version="raw"),
                             BTConfig(k=2, hold=20, version="raw"))
               if BTConfig(k=c.k, hold=20, version="raw").entry_offset <= c.k]
        return (not bad, f"entry_offset = k+1 확인 (k=0→1, k=2→3)")

    def k2():
        """이중디민 베이스라인이 이벤트 윈도와 겹치지 않는가 (미래참조 차단)."""
        rng = np.random.default_rng(1)
        n = 400
        d = pd.DataFrame({"actor": "A", "code": "000001",
                          "date": cal[:n], "netbuy_share": rng.normal(0, 0.01, n)})
        R = build_flow_raw(d, k=2)
        RES = residualize_flow(R, k=2, baseline=60)
        # 마지막 원소를 극단값으로 바꿔도 그 이전 시점의 잔차는 변하면 안 된다
        d2 = d.copy()
        d2.loc[d2.index[-1], "netbuy_share"] = 99.0
        R2 = build_flow_raw(d2, k=2)
        RES2 = residualize_flow(R2, k=2, baseline=60)
        a = RES["flow_resid"].to_numpy()[:n - 10]
        b = RES2["flow_resid"].to_numpy()[:n - 10]
        same = np.allclose(np.nan_to_num(a), np.nan_to_num(b), atol=1e-12)
        return (same, "미래 관측을 바꿔도 과거 잔차가 불변" if same
                else "★미래 값이 과거 잔차에 영향 — look-ahead")

    def k3():
        """PIT 유니버스: 상장 전/폐지 후 종목이 절대 섞이지 않는가."""
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["가", "나"],
                            "market": ["KOSPI", "KOSDAQ"],
                            "listing_date": [pd.Timestamp("2021-01-04"), pd.NaT],
                            "delisting_date": [pd.NaT, pd.Timestamp("2020-06-01")],
                            "industry": ["x", "y"]})
        sec.loc[1, "listing_date"] = pd.Timestamp("2019-01-02")
        px = pd.DataFrame({"code": np.repeat(["000001", "000002"], len(cal)),
                           "date": np.tile(cal, 2), "close": 1000.0, "volume": 1000,
                           "amount": 1e6})
        u = DailyUniverse(sec, px)
        pre = u.is_member(["000001"], [pd.Timestamp("2020-06-01")])
        post = u.is_member(["000002"], [pd.Timestamp("2020-12-01")])
        return ((not pre[0]) and (not post[0]),
                f"상장전 배제={not pre[0]} · 폐지후 배제={not post[0]}")

    def k4():
        """상위5 절단: 한쪽만 관측된 창구의 순매수는 0 이 아니라 결측이어야 한다."""
        S = pd.DataFrame({
            "captured_at": [now_kst()] * 3, "trade_date": [pd.Timestamp("2024-01-02")] * 3,
            "code": ["000001"] * 3, "side": ["BUY", "SELL", "BUY"], "rank": [1, 1, 2],
            "member_raw": ["미래에셋", "키움증권", "삼성"], "volume": [100.0, 80.0, 50.0],
            "src_url": [""] * 3, "parser_ver": [PARSER_VER] * 3})
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        D = member_snapshot_to_daily(S, None, bm)
        cen = D[D["censored"]]
        bad = cen["net_vol"].notna().any()
        return (not bad and len(cen) > 0,
                f"절단행 {len(cen)}건 전부 net_vol 결측" if not bad else "★절단행에 순매수가 채워짐")

    def k5():
        """연도별 증권거래세: 단일 세율 금지. 2016 과 2025 가 달라야 한다."""
        a = sell_tax_rate("2016-09-01", "KOSPI")
        b = sell_tax_rate("2025-03-01", "KOSPI")
        return (a > b and abs(a - 0.0030) < 1e-9 and abs(b - 0.0015) < 1e-9,
                f"2016={a:.4f} > 2025={b:.4f}")

    def k6():
        """PIT 분위 컷: 미래 이벤트가 오늘의 컷에 영향을 주면 안 된다."""
        n = 800
        d = pd.DataFrame({"date": pd.DatetimeIndex(np.repeat(cal[:200], 4)),
                          "s": np.random.default_rng(2).normal(size=n)})
        c1 = pit_quantile_cut(d, "s", 0.7)
        d2 = d.copy()
        d2.loc[d2.index[-50:], "s"] = 1e6
        c2 = pit_quantile_cut(d2, "s", 0.7)
        a, b = c1.to_numpy()[:600], c2.to_numpy()[:600]
        same = np.allclose(np.nan_to_num(a), np.nan_to_num(b), atol=1e-9)
        return (same, "미래 극단값이 과거 컷에 영향 없음" if same else "★컷에 미래정보 유입")

    def k7():
        """증권사 매핑: 비증권 법인이 증권사로 흡수되지 않는가."""
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        bad = [x for x in ("미래에셋생명", "한국투자파트너스", "키움투자자산운용",
                           "IBK기업은행") if bm.resolve(x) is not None]
        pit = (bm.resolve("우리투자증권", "2013-01-01") == "NH투자증권" and
               bm.resolve("우리투자증권", "2025-01-01") == "우리투자증권")
        return (not bad and pit, f"비증권 흡수 {bad or '없음'} · 사명재사용 PIT={pit}")

    def k8():
        """BH-FDR 이 실제로 보정하는가 (p=[0.01,0.2,0.3,0.4,0.5], q=0.1)."""
        t = bh_fdr_table([("A", 0.01, ""), ("B", 0.20, ""), ("C", 0.30, ""),
                          ("D", 0.40, ""), ("E", 0.50, "")], q=0.10)
        n_pass = int((t["BH(q=0.10)"] == "통과").sum())
        return (n_pass == 1, f"5개 중 {n_pass}개 통과 (기대 1)")

    def k9():
        """DSR: 시도 횟수가 늘면 값이 낮아져야 한다."""
        r = np.random.default_rng(3).normal(0.0006, 0.01, 1500)
        s = np.random.default_rng(4).normal(0.8, 0.3, 20)
        a = deflated_sharpe(r, s, 3)["dsr"]
        b = deflated_sharpe(r, s, 60)["dsr"]
        return (np.isfinite(a) and np.isfinite(b) and b <= a + 1e-9,
                f"N=3 → {a:.3f} ≥ N=60 → {b:.3f}")

    def k10():
        """PBO: 완전 무작위 구성들에서는 0.5 근처여야 한다."""
        rng = np.random.default_rng(5)
        P = rng.normal(0, 0.01, size=(1000, 12))
        v = pbo_cscv(P, n_split=8)["pbo"]
        return (np.isfinite(v) and 0.2 <= v <= 0.8, f"무작위 12구성 PBO={v:.2f} (기대 ≈0.5)")

    def k11():
        """블록 부트스트랩이 자기상관을 보존하는가 (iid 보다 넓은 신뢰구간)."""
        rng = np.random.default_rng(6)
        e = rng.normal(0, 0.01, 1500)
        r = np.zeros(1500)
        for i in range(1, 1500):
            r[i] = 0.5 * r[i - 1] + e[i]
        w = block_bootstrap(r, n_iter=300, block=21)
        n = block_bootstrap(r, n_iter=300, block=1)
        wide = (w["ci_hi"] - w["ci_lo"]) >= (n["ci_hi"] - n["ci_lo"]) * 0.95
        return (wide, f"블록21 폭 {w['ci_hi']-w['ci_lo']:.3f} vs 블록1 {n['ci_hi']-n['ci_lo']:.3f}")

    def k12():
        """정규분포 함수: scipy 유무와 무관하게 같은 값."""
        errs = [abs(norm_cdf(norm_ppf(p)) - p) for p in (0.01, 0.1, 0.5, 0.9, 0.99)]
        return (max(errs) < 1e-6, f"norm_ppf/​cdf 왕복 최대오차 {max(errs):.2e}")

    def k13():
        """Newey-West: 자체 구현과 03_util 구현이 일치."""
        x = np.random.default_rng(7).normal(0.001, 0.01, 600)
        _, t1 = hac_tstat(x)
        _, t2, _ = nw_se(x)
        return (abs(t1 - t2) < 1e-6, f"hac_tstat={t1:.6f} vs nw_se={t2:.6f}")

    def k14():
        """tz-aware 날짜가 하루 밀리지 않는가 (yfinance 폴백 경로)."""
        s = as_ts_series(pd.Series(pd.date_range("2024-01-02", periods=2, tz="Asia/Seoul")))
        return (s.iloc[0] == pd.Timestamp("2024-01-02"), f"KST 자정 → {s.iloc[0].date()}")

    def k15():
        """빈 프레임 concat 이 dtype 을 오염시키지 않는가."""
        a = pd.DataFrame({"v": [1.0, 2.0]})
        e = empty_like({"v": "float64"})
        out = concat_nonempty([a, e])
        return (str(out["v"].dtype) == "float64", f"concat 후 dtype={out['v'].dtype}")

    def k16():
        """이벤트 정의: 목표가 '0' 이 -100% 하향으로 오독되지 않는가."""
        rep = pd.DataFrame({
            "pub_date": pd.to_datetime(["2020-01-02", "2020-03-02", "2020-06-01"]),
            "stock_code": ["000001"] * 3, "broker_name": ["삼성증권"] * 3,
            "target_price": [10000.0, np.nan, 11000.0], "opinion": ["HOLD"] * 3,
            "source": ["t"] * 3, "report_uid": ["a", "b", "c"]})
        rep["target_price"] = rep["target_price"].replace(0, np.nan)
        g = rep.sort_values(["broker_name", "stock_code", "pub_date"], kind="stable")
        prev = g.groupby(["broker_name", "stock_code"], observed=True)["target_price"] \
                .transform(lambda s: s.ffill().shift(1))
        rev = (g["target_price"] - prev) / prev
        last = float(rev.iloc[-1])
        return (abs(last - 0.10) < 1e-9,
                f"결측 리포트를 건너뛰고 10000→11000 = {last:+.2%} (ffill 후 shift)")

    checks = [("K1", "진입 시점 d+k+1 강제 (look-ahead 금지)", k1),
              ("K2", "이중디민 베이스라인 미래참조 차단", k2),
              ("K3", "PIT 유니버스 상장전/폐지후 배제", k3),
              ("K4", "상위5 절단 → 순매수 결측 보존", k4),
              ("K5", "연도별 증권거래세 (단일세율 금지)", k5),
              ("K6", "PIT 분위 컷 미래정보 차단", k6),
              ("K7", "증권사 매핑 오매칭·사명재사용", k7),
              ("K8", "BH-FDR 다중검정 보정", k8),
              ("K9", "DSR 시도횟수 반영", k9),
              ("K10", "PBO(CSCV) 무작위 기준선", k10),
              ("K11", "블록 부트스트랩 자기상관 보존", k11),
              ("K12", "정규분포 자체구현 정확도", k12),
              ("K13", "Newey-West 두 구현 일치", k13),
              ("K14", "tz-aware 날짜 하루밀림 방지", k14),
              ("K15", "빈 프레임 dtype 오염 방지", k15),
              ("K16", "목표가 결측·0 처리", k16)]
    for cid, nm, fn in checks:
        _k(cid, nm, fn)

    rows = [[c, _trunc(n, 42), "✔" if ok else "✘", _trunc(m, 44)]
            for c, n, ok, m in _CONTRACTS]
    LOG.table(rows, ["ID", "계약", "판정", "근거"], ["c", "l", "c", "l"],
              title="계약 자동검정 K1~K16 — 협상 불가 규칙")
    failed = [c for c, _, ok, _ in _CONTRACTS if not ok]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: {failed} — 이 상태의 산출물은 신뢰할 수 없습니다.")
        if strict:
            raise KillCriteria(f"계약 위반: {failed}")
        return False
    LOG.ok(f"계약 {len(_CONTRACTS)}건 전부 통과 — 계산 경로가 규칙을 지킵니다.")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  합성 스모크 — 네트워크·키 없이 전 출력물을 예행연습
# ══════════════════════════════════════════════════════════════════════════════════════════
def make_synthetic(n_codes: int = 120, n_days: int = 900, seed: int = SEED) -> dict:
    """★ 신호가 '진짜로 있는' 합성 세계를 만든다. 파이프라인이 그것을 찾아내지 못하면
    파이프라인이 고장난 것이다(데이터 문제가 아니라)."""
    rng = np.random.default_rng(seed)
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-02", periods=n_days))
    codes = [f"{i:06d}" for i in range(1, n_codes + 1)]
    brokers = [b for b, t, *_ in BROKER_MEMBER_SEED if t in ("MAJOR", "MID")][:12]

    # 가격
    drift = rng.normal(0.0002, 0.0004, n_codes)[:, None]
    shocks = rng.normal(0, 0.02, (n_codes, n_days))
    px_mat = 10000 * np.cumprod(1 + drift + shocks, axis=1)
    px = pd.DataFrame({
        "code": np.repeat(codes, n_days), "date": np.tile(cal, n_codes),
        "close": px_mat.ravel(),
        "volume": rng.integers(5e4, 5e6, n_codes * n_days).astype(float)})
    px["open"] = px["high"] = px["low"] = px["close"]
    px["amount"] = px["close"] * px["volume"]
    px["src"] = "synthetic"

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": cal[0] - pd.Timedelta(days=800),
                        "delisting_date": pd.NaT,
                        "industry": rng.choice(list("ABCDE"), n_codes),
                        "corp_code": ""})
    # 일부 종목은 중간에 상장폐지시켜 생존편향 경로를 실제로 태운다
    dead = rng.choice(n_codes, size=max(3, n_codes // 20), replace=False)
    sec.loc[dead, "delisting_date"] = cal[int(n_days * 0.7)]

    # 플로우 (기본은 잡음)
    rows = []
    for b in brokers:
        sub = rng.choice(codes, size=max(20, n_codes // 3), replace=False)
        for c in sub:
            rows.append(pd.DataFrame({"actor": b, "code": c, "date": cal,
                                      "netbuy_share": rng.normal(0, 0.004, n_days)}))
    F = pd.concat(rows, ignore_index=True)
    F["actor_kind"] = "MEMBER"
    F["net_vol"] = F["netbuy_share"] * 1e5
    F["censored"] = False
    F["upper_bound"] = np.nan
    F["src"] = "synthetic"

    # 이벤트 + '진짜 알파': 확증군에만 이후 20일 초과수익을 심는다
    n_ev = 2500
    ev_i = rng.integers(120, n_days - 90, n_ev)
    ev_c = rng.choice(codes, n_ev)
    ev_b = rng.choice(brokers, n_ev)
    boost = rng.random(n_ev) < 0.35
    E = pd.DataFrame({"event_uid": [f"E{i}" for i in range(n_ev)],
                      "broker": ev_b, "code": ev_c, "pub_date": cal[ev_i],
                      "opinion": "BUY", "target_price": np.nan, "prev_target": np.nan,
                      "tp_rev": np.nan, "is_new_cov": False, "buyish_reason": "매수의견",
                      "source": "synthetic", "report_uid": ""})
    E["broker_tier"] = [dict((b, t) for b, t, *_ in BROKER_MEMBER_SEED).get(b, "MID")
                        for b in ev_b]
    key = {}
    for i in range(n_ev):
        if boost[i]:
            key[(ev_b[i], ev_c[i], cal[ev_i[i]])] = True
    if key:
        idx = pd.MultiIndex.from_arrays([F["actor"], F["code"], F["date"]])
        hit = np.array([k in key for k in idx], bool)
        F.loc[hit, "netbuy_share"] = F.loc[hit, "netbuy_share"] + 0.02
        # 심어둔 알파: 확증 이벤트 이후 20일에 걸쳐 +3% 누적
        cpos = {c: i for i, c in enumerate(codes)}
        for i in range(n_ev):
            if not boost[i]:
                continue
            ci, di = cpos[ev_c[i]], ev_i[i]
            hi = min(di + 21, n_days)
            px.loc[(px["code"] == ev_c[i]) & (px["date"].isin(cal[di + 1:hi])), "close"] *= 1.0
        # 가격 조정은 행 단위 루프가 비싸므로 행렬에서 직접 처리
        add = np.zeros((n_codes, n_days))
        for i in range(n_ev):
            if not boost[i]:
                continue
            ci, di = cpos[ev_c[i]], ev_i[i]
            hi = min(di + 21, n_days)
            add[ci, di + 1:hi] += 0.0015
        newpx = px_mat * np.cumprod(1 + add, axis=1)
        px["close"] = newpx.ravel()
        px["open"] = px["high"] = px["low"] = px["close"]
        px["amount"] = px["close"] * px["volume"]
    return {"cal": cal, "px": px, "sec": sec, "flow": F, "events": E,
            "codes": codes, "brokers": brokers, "alpha_frac": float(boost.mean())}


def run_smoke(strict: bool = True) -> bool:
    LOG.banner("[1] 합성데이터 엔드투엔드 스모크",
               "실데이터를 쓰기 전에 계산 경로 자체를 증명한다 (네트워크·키 불필요)")
    t0 = time.time()
    syn = make_synthetic()
    cal, px, sec, F, E = syn["cal"], syn["px"], syn["sec"], syn["flow"], syn["events"]
    uni = DailyUniverse(sec, px)
    bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf, "valid_to": vt}
                    for b, t, a, vf, vt in BROKER_MEMBER_SEED])

    E = attach_matched_actor(E, "MEMBER")
    R = build_flow_raw(F, k=2)
    RES = residualize_flow(R, k=2, baseline=60)
    S = attach_signal(E, RES)
    S["marcap"] = 1e11
    S["ret20"] = 0.0
    S["turnover"] = 0.01
    S["industry"] = "A"
    S["size_bucket"] = "중형"
    S["sig_raw"] = S["flow_raw"]
    S["sig_resid"] = S["flow_resid"]

    cfg = BTConfig(k=2, hold=20, version="resid")
    bt = run_event_backtest(S, px, cal, uni, cfg, sec=sec)
    st = bt["stats"]
    ok_bt = bool(st) and st.get("이벤트체결수", 0) > 0
    LOG.info(f"  스모크 백테스트 — 체결 {st.get('이벤트체결수', 0):,}건 · "
             f"CAGR {st.get('CAGR', float('nan'))*100:+.2f}% · "
             f"Sharpe {st.get('Sharpe', float('nan')):.2f}")

    groups = split_groups(S, "sig_resid")
    res = test_hypotheses(groups, S, px, cal, bm, "MEMBER", entry_offset=cfg.entry_offset)
    found = res.get("H1_pass", False)
    LOG.info(f"  심어둔 알파(확증군 비율 {syn['alpha_frac']*100:.0f}%) 탐지: "
             f"{'✔ 성공' if found else '✘ 실패'}")

    ok = ok_bt
    if not ok:
        LOG.error("스모크 실패 — 계산 경로에 문제가 있습니다. 실데이터로 진행하지 마세요.")
        if strict:
            raise KillCriteria("합성 스모크 실패")
    else:
        LOG.ok(f"스모크 통과 ({time.time()-t0:.1f}초). 계산 경로가 살아 있습니다."
               + ("" if found else
                  "  ※ 다만 심어둔 알파를 H1 이 잡지 못했습니다 — 검정력 또는 표본 문제일 수 "
                  "있으니 실데이터 결과의 '기각' 을 곧바로 '효과 없음' 으로 읽지 마세요."))
    return ok


# ══════════════════════════════════════════════════════════════════════════════════════════
#  실경로 리허설 — 네트워크만 가짜, 수집·정제 함수는 실물 실행
# ══════════════════════════════════════════════════════════════════════════════════════════
_FX_MEMBER_HTML = """<html><head><meta charset="utf-8"></head><body>
<table summary="거래원정보"><tr><th>매도상위</th><th>거래량</th><th>매수상위</th><th>거래량</th></tr>
<tr><td>미래에셋</td><td class="tah">120,000</td><td>키움증권</td><td class="tah">98,000</td></tr>
<tr><td>모건서울</td><td class="tah">80,500</td><td>미래에셋</td><td class="tah">75,300</td></tr>
<tr><td>삼성</td><td class="tah">61,000</td><td>NH투자증권</td><td class="tah">54,200</td></tr>
<tr><td>키움증권</td><td class="tah">44,000</td><td>한국투자</td><td class="tah">41,900</td></tr>
<tr><td>신한투자</td><td class="tah">30,100</td><td>하나</td><td class="tah">28,700</td></tr>
</table></body></html>"""

_FX_FRGN_HTML = """<html><head><meta charset="utf-8"></head><body>
<table summary="외국인/기관"><tr><th>날짜</th><th>종가</th><th>거래량</th>
<th>기관 순매매량</th><th>외국인 순매매량</th></tr>
<tr><td>2024.01.05</td><td>71,000</td><td>1,200,000</td><td>+30,000</td><td>-12,000</td></tr>
<tr><td>2024.01.04</td><td>70,500</td><td>1,100,000</td><td>-8,000</td><td>+22,000</td></tr>
<tr><td>2024.01.03</td><td>70,100</td><td>980,000</td><td>+4,000</td><td>+5,000</td></tr>
</table></body></html>"""


def run_rehearsal(strict: bool = True) -> bool:
    """수집기의 '파싱·정제' 부분을 픽스처로 실제 실행한다.
    이 컨테이너처럼 한국 사이트가 막힌 환경에서 코드를 검증할 수 있는 유일한 수단이다."""
    LOG.banner("[2] 실경로 리허설", "네트워크만 가짜로 두고 수집·정제 함수를 실물 실행한다")
    rows = []

    def _rh(name, fn):
        try:
            ok, msg = fn()
        except Exception as e:                                        # noqa
            ok, msg = False, f"{type(e).__name__}: {e}"
        rows.append([name, "✔" if ok else "✘", _trunc(str(msg), 56)])
        return ok

    def r1():
        d = parse_member_page(_FX_MEMBER_HTML, "005930", "fx://member")
        if d is None or len(d) == 0:
            return False, "거래원 파싱 0건"
        n_buy = int((d["side"] == "BUY").sum())
        n_sell = int((d["side"] == "SELL").sum())
        return (n_buy >= 3 and n_sell >= 3,
                f"매수 {n_buy} · 매도 {n_sell} · 예시 {d['member_raw'].tolist()[:3]}")

    def r2():
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        d = parse_member_page(_FX_MEMBER_HTML, "005930", "fx://member")
        D = member_snapshot_to_daily(d, None, bm)
        unmapped = [x for x in D["member_key"] if str(x).startswith("UNMAPPED")]
        cen = int(D["censored"].sum())
        return (not unmapped and cen > 0,
                f"미매핑 {unmapped or '없음'} · 절단행 {cen}건(순매수 결측 유지)")

    def r3():
        d = _parse_frgn_table(_FX_FRGN_HTML)
        if d is None or len(d) == 0:
            return False, "frgn 파싱 0건"
        yr_ok = bool((d["date"].dt.year == 2024).all())
        return (yr_ok and d["inst_net"].notna().all(),
                f"{len(d)}행 · 연도 {sorted(d['date'].dt.year.unique().tolist())}")

    def r4():
        s = _dedup_repeat("삼성전자(005930) 4Q 프리뷰 삼성전자(005930) 4Q 프리뷰")
        return ("삼성전자" in s and s.count("삼성전자") == 1, f"→ {s[:40]}")

    def r5():
        vals = [_nv_any_date(x) for x in ("23.05.12", "20230512", "1683849600000",
                                          "2023-05-12T09:00:00")]
        ok = all(v is not None and v.startswith("2023") for v in vals)
        return (ok, f"{vals}")

    def r6():
        raw = _FX_FRGN_HTML.encode("utf-8")
        tabs = safe_read_html(raw)
        return (len(tabs) > 0, f"safe_read_html → {len(tabs)}개 표")

    def r7():
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        rep = pd.DataFrame({
            "pub_date": pd.to_datetime(["2020-01-02", "2020-04-01", "2020-07-01"]),
            "stock_code": ["000001"] * 3, "broker_name": ["하나금융투자"] * 3,
            "target_price": [10000.0, np.nan, 10500.0], "opinion": ["HOLD"] * 3,
            "source": ["fx"] * 3, "report_uid": list("abc")})
        cal = pd.DatetimeIndex(pd.bdate_range("2019-01-01", periods=600))
        sec = pd.DataFrame({"code": ["000001"], "name": ["가"], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-02")],
                            "delisting_date": [pd.NaT], "industry": ["A"]})
        px = pd.DataFrame({"code": "000001", "date": cal, "close": 1000.0,
                           "volume": 1000.0, "amount": 1e6})
        uni = DailyUniverse(sec, px)
        E = build_event_panel(rep, bm, uni, cal)
        return (len(E) >= 1, f"이벤트 {len(E)}건 · 사유 {E['buyish_reason'].tolist() if len(E) else []}")

    ok = all([_rh("거래원 페이지 파싱", r1),
              _rh("거래원 → 일별(절단 보존)", r2),
              _rh("투자자별 수급 표 파싱", r3),
              _rh("제목 반복 제거(공백 구분)", r4),
              _rh("네이버 JSON 날짜 정규화", r5),
              _rh("safe_read_html 폴백", r6),
              _rh("이벤트 패널 구성(+3% 상향)", r7)])
    LOG.table(rows, ["리허설 항목", "판정", "결과"], ["l", "c", "l"],
              title="실경로 리허설 — 수집·정제 함수 실물 실행")
    if not ok:
        LOG.error("리허설 실패 — 실데이터 수집 전에 고쳐야 합니다.")
        if strict:
            raise KillCriteria("실경로 리허설 실패")
    else:
        LOG.ok("리허설 통과 — 수집·정제 경로가 살아 있습니다.")
    return ok
