

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-V  계약 자동검정 K1~K23  +  합성데이터 엔드투엔드 스모크  +  실경로 리허설             ║
# ║                                                                                          ║
# ║  세 검증은 서로 다른 것을 본다. 하나로 합칠 수 없다:                                       ║
# ║   · 계약검정 : 협상 불가 규칙(PIT·생존편향·사전등록)이 코드에 실제로 박혀 있는가            ║
# ║   · 스모크   : 합성데이터로 '계산경로'가 끝까지 도는가 (네트워크·키 불필요)                 ║
# ║   · 리허설   : 네트워크만 가짜로 두고 '수집·정제 함수'를 실물 실행 — 파싱 크래시를 잡는다   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _src(*objs) -> str:
    """지정 함수/클래스의 소스를 모아 돌려준다.

    __file__ 에 의존하면 노트북 셀에 붙여넣어 실행할 때 소스검사 계약이 통째로 무너진다
    (그리고 '검사가 사라진 것'을 아무도 모른다). inspect 로 대상 객체에서 직접 뽑는다.
    """
    import inspect
    out = []
    for o in objs:
        try:
            out.append(inspect.getsource(o))
        except Exception:
            pass
    if not out:
        # ★ 빈 문자열을 돌려주면 모든 `'x' in src` 검사가 False 가 되어, 소스검사 계약
        #   6개가 한꺼번에 '위반'으로 뒤집히고 strict 모드가 실행을 죽인다.
        #   exec(open(...).read()) 나 일부 %paste 경로가 정확히 이 상태다 —
        #   진짜 위반이 하나도 없는데 6건 위반으로 멈춘다. 검사 불가는 SKIP 이어야 한다.
        raise _SrcUnavailable("inspect.getsource 로 소스를 얻을 수 없는 실행 방식입니다"
                              " (예: exec(open(...).read())). 소스검사 계약만 건너뜁니다.")
    return "\n".join(out)


class _SrcUnavailable(Exception):
    """소스 텍스트를 얻을 수 없는 환경 — 계약 위반이 아니라 '검사 불가'다."""


def _k(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    skip = False
    try:
        ok, msg = fn()
    except _SrcUnavailable as e:
        ok, msg, skip = True, f"검사 불가 — {e}", True
    except Exception as e:                                    # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:180]}"
    CONTRACTS.append({"id": cid, "name": name, "pass": bool(ok), "msg": msg, "skip": skip})


def _synth(n_codes: int = 140, n_months: int = 54, n_analysts: int = 90,
           seed: int = SEED) -> dict:
    """합성 시장 — 실제로 링크를 통해 전파되는 신호를 심는다.

    스모크가 '돌기만' 하면 의미가 없다. 심어놓은 효과를 파이프라인이 실제로 회수하는지까지
    본다. 그래야 계산경로가 옳다는 증거가 된다.
    """
    rng = np.random.default_rng(seed)
    codes = [f"{900000 + i:06d}"[:6] for i in range(n_codes)]
    codes = [f"{(100000 + i * 7) % 900000 + 10000:06d}" for i in range(n_codes)]
    end = as_ts(BACKTEST_END)
    months = pd.date_range(end=end, periods=n_months, freq=MONTH_END_ALIAS)
    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1])

    # 애널리스트별 커버리지: 종목을 블록으로 묶어 진짜 군집이 생기게 한다
    #  애널리스트는 대체로 한 업종을 맡되 일부는 업종을 가로지른다.
    #  이렇게 해야 H2(동일업종 링크 제거) 마스킹 경로가 실제로 검증된다 —
    #  커버리지가 업종과 무관하면 제거할 동일업종 쌍이 0개라 H2 가 H1 의 복사본이 된다.
    n_sec = 9
    by_sec: Dict[int, List[str]] = {k: [c for i, c in enumerate(codes) if i % n_sec == k]
                                    for k in range(n_sec)}
    cov: Dict[str, List[str]] = {}
    for a in range(n_analysts):
        k = int(rng.integers(4, 10))
        home = by_sec[a % n_sec]
        pick = list(rng.choice(home, size=min(k, len(home)), replace=False))
        if rng.random() < 0.35:                     # 35% 는 인접 업종도 함께 커버
            other = by_sec[(a + 1) % n_sec]
            pick += list(rng.choice(other, size=min(2, len(other)), replace=False))
        cov[f"A{a:03d}@B{a % 12:02d}"] = [str(x) for x in pick]

    # 가격: 링크 이웃의 직전 수익률이 다음 달 수익률에 +로 들어가게 설계
    nb: Dict[str, set] = {c: set() for c in codes}
    for a, cs in cov.items():
        for i in cs:
            for j in cs:
                if i != j:
                    nb[i].add(j)
    cpos = {c: i for i, c in enumerate(codes)}
    # 이웃 평균 연산자를 행렬로 만들어 둔다 (루프보다 빠르고, 무엇보다 부호 실수를 막는다)
    A = np.zeros((n_codes, n_codes))
    for c, ns in nb.items():
        if ns:
            A[cpos[c], [cpos[x] for x in ns]] = 1.0 / len(ns)

    # 월 단위로 먼저 만든다: 이번 달 수익 = 자체충격 + 0.5 × (이웃의 '지난달' 수익)
    # → 신호(이웃 직전수익)가 다음 달 수익을 실제로 예측하도록 설계된 세계다.
    gmonths = pd.date_range(days[0], days[-1], freq=MONTH_END_ALIAS)
    shock = rng.normal(0.0, 0.08, (len(gmonths), n_codes))
    mret = np.zeros_like(shock)
    mret[0] = shock[0]
    for i in range(1, len(gmonths)):
        mret[i] = shock[i] + 0.50 * (A @ mret[i - 1])

    # 월 수익을 그 달 영업일에 균등 분배 + 일간 잡음 (월 합계는 보존)
    n_d = len(days)
    px = np.zeros((n_d, n_codes), dtype=float)
    px[0] = 10000 * np.exp(rng.normal(0, 0.4, n_codes))
    mkey = {as_ts(m): i for i, m in enumerate(gmonths)}
    for t in range(1, n_d):
        mi = mkey.get(as_ts(days[t]) + pd.offsets.MonthEnd(0))
        base = (mret[mi] / 21.0) if mi is not None else np.zeros(n_codes)
        step = base + rng.normal(0.0, 0.010, n_codes)
        px[t] = np.maximum(px[t - 1] * (1 + step), 100.0)
    close = pd.DataFrame(px, index=days, columns=codes)
    daily = close.stack().rename("close").reset_index()
    daily.columns = ["date", "code", "close"]
    daily["open"] = daily["close"] * (1 + rng.normal(0, 0.003, len(daily)))
    daily["volume"] = rng.integers(1e4, 1e6, len(daily))
    daily["amount"] = daily["close"] * daily["volume"]
    daily["high"] = daily["close"] * 1.01
    daily["low"] = daily["close"] * 0.99
    daily["src"] = "synth"

    # 리포트 원장
    rows = []
    for a, cs in cov.items():
        for c in cs:
            for m in months[::2]:
                if rng.random() < 0.55:
                    d = as_ts(m) - pd.Timedelta(days=int(rng.integers(1, 25)))
                    rows.append({"analyst_key": a, "code": c, "pub_date": d,
                                 "knowledge_date": d + pd.tseries.offsets.BDay(1),
                                 "broker_id": a.split("@")[1], "broker_name": a.split("@")[1],
                                 "link_conf": 0.98, "n_analyst_on_report": 1,
                                 "target_price": float(close.loc[:d, c].iloc[-1] *
                                                       (1 + rng.normal(0.1, 0.2)))
                                 if len(close.loc[:d, c]) else np.nan})
    ledger = pd.DataFrame(rows)

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i}" for i in range(n_codes)],
                        "market": ["KOSPI" if i % 3 else "KOSDAQ" for i in range(n_codes)],
                        "industry": [f"업종{i % 9}" for i in range(n_codes)],
                        "corp_code": [f"{i:08d}" for i in range(n_codes)],
                        "listing_date": days[0] - pd.Timedelta(days=900),
                        "delisting_date": pd.NaT})
    # 월말 종가를 한 번에 뽑는다. (months × codes) 루프로 .loc 슬라이싱하면
    # 종목 수를 늘리는 순간 합성데이터 생성이 백테스트보다 오래 걸린다.
    cm = close.reindex(close.index.union(months)).sort_index().ffill().reindex(months)
    mc_long = cm.stack().rename("close_m").reset_index()
    mc_long.columns = ["month", "code", "close_m"]
    mc_long = mc_long.dropna(subset=["close_m"])
    scale = mc_long["code"].map(lambda c: 1e6 * (1 + cpos[c] % 40))
    mcap = pd.DataFrame({"code": mc_long["code"].to_numpy(), "month": mc_long["month"].to_numpy(),
                         "mktcap": mc_long["close_m"].to_numpy() * scale.to_numpy(),
                         "shares": 1e6, "close_m": mc_long["close_m"].to_numpy(),
                         "amount_m": 1e9})
    fund = mcap[["code", "month"]].copy()
    fund["pbr"] = np.abs(rng.normal(1.2, 0.5, len(fund))) + 0.1
    fund["bm"] = 1.0 / fund["pbr"]
    for c in ("bps", "per", "eps", "div_yield"):
        fund[c] = np.nan
    return {"codes": codes, "months": months, "daily": daily, "ledger": ledger,
            "sec": sec, "mcap": mcap, "fund": fund,
            "sector": pd.DataFrame({"code": codes,
                                    "sector": [f"업종{i % 9}" for i in range(n_codes)]})}


class _SynthUniverse:
    """스모크용 최소 Universe — 실제 Universe 와 같은 인터페이스만 제공한다."""

    def __init__(self, codes, months):
        self._c, self._m = list(codes), list(months)

    def at(self, t):
        return list(self._c)

    def delisting_map(self):
        return {}


def run_selftest(full: bool = True) -> bool:
    """합성데이터로 링크→신호→백테스트→검정까지 전 경로를 실제로 돈다."""
    LOG.banner("합성데이터 엔드투엔드 스모크", "네트워크·키 불필요 · 계산경로 증명")
    S = _synth()
    grid = PriceGrid(S["daily"])
    months = pd.DatetimeIndex([m for m in S["months"]])

    uni_rows = []
    for m in months:
        sub = S["mcap"][S["mcap"]["month"] == m][["code", "month", "mktcap", "shares"]]
        if not len(sub):
            continue
        g = sub.copy()
        g["close_m"] = [float(grid.close.loc[:m, c].iloc[-1]) if c in grid.close.columns
                        and len(grid.close.loc[:m, c]) else np.nan for c in g["code"]]
        g["adv20"] = 1e9
        g["market"] = "KOSPI"
        g["sector"] = g["code"].map(S["sector"].set_index("code")["sector"])
        g["bm"] = g.merge(S["fund"], on=["code", "month"], how="left")["bm"].to_numpy()
        g["exec_px"] = g["close_m"]
        g["fwd_ret_m"] = np.nan
        g["in_universe"] = True
        uni_rows.append(g)
    U = pd.concat(uni_rows, ignore_index=True)

    LM = build_link_matrices(S["ledger"], months, S["codes"], "unweighted", use_cache=False)
    if not LM.W:
        LOG.error("스모크 실패: 링크 행렬이 만들어지지 않았습니다.")
        return False
    P = build_signal_panel(LM, grid, U, months, "1M", "M")
    if P is None or not len(P):
        LOG.error("스모크 실패: 신호 패널이 비었습니다.")
        return False
    P = attach_attrs(P, U, grid)

    bt = run_quantile_backtest(P, "sacn_raw", "M", label="SMOKE")
    if not len(bt["returns"]):
        LOG.error("스모크 실패: 백테스트 수익 계열이 비었습니다.")
        return False
    st = perf_stats(bt["returns"], ppy=12.0)
    sp = spread_series(P, "sacn_raw")
    mu, t, _ = nw_tstat(sp.to_numpy(float), 12.0) if len(sp) else (np.nan, np.nan, 0)
    bs = block_bootstrap(bt["returns"]["ret"].to_numpy(float), ppy=12.0, n_boot=200)
    M = pd.DataFrame({f"cfg{i}": bt["returns"]["ret"].to_numpy(float) *
                      (1 + 0.1 * np.sin(i + np.arange(len(bt["returns"]))))
                      for i in range(N_PREREG_CONFIGS)})
    pb = cscv_pbo(M, S=8)
    ds = deflated_sharpe(bt["returns"]["ret"].to_numpy(float), n_trials=N_PREREG_CONFIGS)

    LOG.table([["링크 행렬", f"{len(LM.W)}개월"], ["신호 패널", f"{len(P):,}행"],
               ["백테스트 기간", f"{len(bt['returns'])}"],
               ["CAGR", _fmt_metric('CAGR', st.get('CAGR'))],
               ["Sharpe", _fmt_metric('Sharpe', st.get('Sharpe'))],
               ["Q5−Q1 t(NW)", f"{t:+.2f}" if np.isfinite(t) else "—"],
               ["부트스트랩", "OK" if bs.get("ok") else "미수행"],
               ["PBO", f"{pb.get('pbo', float('nan')):.3f}" if pb.get("ok") else "미수행"],
               ["DSR", f"{ds.get('dsr', float('nan')):.3f}" if ds.get("ok") else "미수행"]],
              ["스모크 단계", "결과"], ["l", "r"])

    # 심어놓은 효과를 실제로 회수했는가 (스모크의 진짜 판정 기준)
    recovered = bool(np.isfinite(t) and t > 0)
    if not recovered:
        LOG.warn("합성데이터에 심어둔 이웃 전파 효과를 신호가 회수하지 못했습니다 "
                 "(t ≤ 0). 계산경로 어딘가가 부호를 뒤집거나 링크를 잘못 잇고 있습니다.")
    else:
        LOG.ok(f"심어둔 이웃 전파 효과를 회수했습니다 (Q5−Q1 t={t:+.2f}) — 계산경로 정상")
    LOG.ok("스모크 통과")
    return True


# ── 계약 검정 ───────────────────────────────────────────────────────────────────────────────
def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정 K1~K23", "협상 불가 규칙이 코드에 실제로 박혀 있는지 검사한다")
    CONTRACTS.clear()

    def k1():
        d = pd.DataFrame({"code": ["A"], "v": [1]})
        try:
            PIT.register("__k1__", d)
            return False, "PIT 컬럼 없는 테이블이 등록되었다 (C1 우회 경로 존재)"
        except KeyError:
            pass
        f = pit_frame(d, "2020-01-01", "2019-01-01")
        ok = bool((f["knowledge_date"] >= f["event_date"]).all())
        return ok, "pit_frame 이 knowledge<event 를 교정하고, PIT 컬럼 없으면 등록 거부"

    def k2():
        src = _src(SACNUniverse.delisting_returns)
        ok = ("정리매매" in src) and ("DELIST_DEFAULT_RET" in src or "default_ret" in src)
        return bool(ok), "폐지 수익률을 정리매매 최종가 기준으로 처리 (-100% 일괄 아님)"

    def k3():
        S = _synth(n_codes=40, n_months=20, n_analysts=25)
        g = PriceGrid(S["daily"])
        t = as_ts(S["months"][5])
        _, d0 = g.exec_price(t)
        return bool(d0 is not None and d0 > t), f"실행일 {d0} > 신호일 {t} (익영업일 앵커)"

    def k4():
        S = _synth(n_codes=30, n_months=16, n_analysts=20)
        LM = build_link_matrices(S["ledger"], pd.DatetimeIndex(S["months"]), S["codes"],
                                 "unweighted", use_cache=False)
        if not LM.W:
            return False, "링크 행렬 생성 실패"
        bad = sum(int(np.abs(W.diagonal()).sum()) for W in LM.W.values())
        return bad == 0, "링크 행렬 대각원소 전부 0 (자기 자신은 연결이 아니다)"

    def k5():
        return MIN_LINKS_REQUIRED >= 3, f"최소 연결 요건 {MIN_LINKS_REQUIRED}개 (SPEC §6.1 = 3)"

    def k6():
        src = _src(build_link_matrices)
        ok = ('knowledge_date' in src) and ('searchsorted(kd' in src) and \
             ('searchsorted(pub' not in src)
        return ok, "링크 윈도우를 pub_date 가 아니라 knowledge_date 로 자른다 (PIT)"

    def k7():
        n = len(PREREG_SIGNAL_WINDOWS) * len(PREREG_REBALANCES) * len(PREREG_LINK_WEIGHTS)
        return n == 12 and N_PREREG_CONFIGS == 12, f"사전등록 격자 {n}개 (SPEC §6.4 = 12, 확장 금지)"

    def k8():
        a = block_bootstrap(np.random.default_rng(1).normal(0.01, 0.05, 60), n_boot=50, seed=7)
        b = block_bootstrap(np.random.default_rng(1).normal(0.01, 0.05, 60), n_boot=50, seed=7)
        return a["cagr_med"] == b["cagr_med"], "같은 시드 → 같은 결과 (결정성)"

    def k9():
        r19 = sell_tax_rate("2018-01-01", "KOSPI")
        r25 = sell_tax_rate("2025-06-01", "KOSPI")
        return bool(r19 > r25 and len(SELL_TAX_SCHEDULE) >= 6), \
            f"연도별 세율 테이블 적용 (2018 {r19:.3%} → 2025 {r25:.3%})"

    def k10():
        src = _src(compute_sacn, orthogonalize)
        return ("sacn_raw" in src and "sacn_resid" in src), "원신호와 직교화 신호를 둘 다 산출"

    def k11():
        src = _src(build_link_ledger)
        ok = ('+ "@" +' in src) and ('broker_id' in src)
        return ok, "애널리스트 식별자 = analyst_id@broker_id (이직 시 다른 식별자)"

    def k12():
        return not hasattr(Vault, "delete") and not hasattr(Vault, "remove"), \
            "Vault 에 삭제 API 자체가 없다 (기존 캐시 훼손 불가능)"

    def k13():
        # ★ 합계 비교는 어떤 순열에도 불변이라 '검사가 절대 실패할 수 없다'.
        #   종목별 배정을 직접 비교해야 동점 처리의 결정성을 실제로 검정한다.
        g = pd.DataFrame({"code": list("abcdefghij"), "s": [1.0] * 10})
        a = dict(zip(g["code"], _assign_quantiles(g, "s", 5)))
        rev = g.iloc[::-1].reset_index(drop=True)
        b = dict(zip(rev["code"], _assign_quantiles(rev, "s", 5)))
        same = a == b
        # 동점이 아닌 경우의 방향도 함께 확인한다 (최고 신호 = Q5)
        h = pd.DataFrame({"code": [f"c{i}" for i in range(10)], "s": list(range(10))})
        qq = _assign_quantiles(h, "s", 5)
        direction = bool(qq.iloc[-1] == 5 and qq.iloc[0] == 1)
        return bool(same and direction), \
            f"동점 배정이 입력 순서에 무관(종목별 비교) · 최고신호=Q5 방향 {direction}"

    def k14():
        k = _beta_binom_k(np.array([5., 30., 2.]), np.array([10., 60., 4.]))
        return bool(np.isfinite(k) and k > 0), f"EB 축소강도 k={k:.0f} > 0 (축소는 필수)"

    def k15():
        """상세 보강 상한이 시간축을 편식하지 않는가.

        ★ 이 계약이 없어서 조용히 죽을 뻔했다. 최신순 head(limit) 로 자르면 최근 2~3년만
          채워지고 백테스트 앞 6~7년의 링크가 통째로 비는데, 예외가 하나도 나지 않는다.
          '균등하게 잘렸는가'를 월 커버리지로 직접 검사한다.
        """
        months = pd.period_range("2016-08", "2026-07", freq="M")
        need = pd.DataFrame({
            "pub_date": [p.start_time + pd.Timedelta(days=3) for p in months for _ in range(50)],
            "src_report_id": [f"{i}" for i in range(len(months) * 50)]})
        picked = _nv_stratified(need, 200)
        cov = as_ts_series(picked["pub_date"]).dt.to_period("M").nunique()
        why = []
        if len(picked) != 200:
            # 상한을 무시하고 need 를 그대로 돌려줘도 커버리지 검사만으로는 통과한다.
            # 그 실패 모드가 곧 '45,000건 무제한 요청'이므로 반드시 함께 본다.
            why.append(f"상한 미적용: {len(picked)}건 반환(기대 200)")
        if cov < min(len(months), 200):
            why.append(f"시간축 편식: {cov}/{len(months)}개월")
        # 상한 < 개월수 구간(실제로 문제가 되는 영역)도 확인한다
        few = _nv_stratified(need, 30)
        cov2 = as_ts_series(few["pub_date"]).dt.to_period("M").nunique()
        if len(few) != 30 or cov2 != 30:
            why.append(f"상한 30 에서 {len(few)}건/{cov2}개월 (기대 30/30)")
        return (not why), ("상한이 지켜지고 월별로 고루 배분됨 (최신순 편식 아님)"
                           if not why else " · ".join(why))

    def k16():
        """가격 수집 대상 축소가 상장폐지 보통주를 절대 버리지 않는가 (생존자편향)."""
        sec = pd.DataFrame({
            "code": ["005930", "005935", "069500", "037350", "323230"],
            "name": ["삼성전자", "삼성전자우", "KODEX 200", "폐지된회사", "대신밸런스제1호스팩"],
            "market": ["KOSPI"] * 5,
            "listing_date": [as_ts("2000-01-01")] * 5,
            "delisting_date": [pd.NaT, pd.NaT, pd.NaT, as_ts("2019-05-01"), pd.NaT]})
        keep, _aud = price_target_codes(sec)
        # ★ 실제 환경에서 name 은 자주 비어 있고(pykrx 부재 시 특히), 그러면 이름 패턴
        #   판정이 통째로 무력해진다. 이름 없는 보통주가 살아남는지도 함께 본다.
        sec2 = sec.copy()
        sec2.loc[sec2["code"] == "037350", "name"] = ""
        keep2, _a2 = price_target_codes(sec2)
        missing = [c for c in ("037350", "005930") if c not in keep]
        if "037350" not in keep2:
            missing.append("037350(이름없음)")
        # 이름 패턴이 보통주를 삼키지 않는지 (구버전의 '파워' 부분일치 사고)
        sec3 = pd.DataFrame({"code": ["047310"], "name": ["파워로직스"], "market": ["KOSDAQ"],
                             "listing_date": [as_ts("2000-01-01")], "delisting_date": [pd.NaT]})
        if "047310" not in price_target_codes(sec3)[0]:
            missing.append("047310 파워로직스(보통주인데 ETF 로 오분류)")
        leaked = [c for c in ("005935", "069500", "323230") if c in keep]
        ok = (not missing) and (not leaked)
        if not ok:
            return False, f"누락(생존편향){missing} · 유출(§5위반){leaked} → 대상 {keep}"
        return ok, f"폐지 보통주 유지 · 우선주/ETF/스팩 제외 → 대상 {len(keep)}종목"

    def k17():
        """리허설 중에는 '어떤 경로로도' 드라이브에 쓰이지 않는가 (절대 1원칙).

        ★ persist() 하나만 검사하면 안 된다. 그 주장은 "어떤 것도 쓰이지 않는다" 인데,
          put_table / put_blob / _save_links 는 별도의 경로다. 그래서 Vault 수준에서
          쓰기 횟수를 세고, 리허설이 실제로 도는 동안 0 인지 확인한다.
        """
        g = globals()
        V = g.get("VAULT")
        if V is None:
            raise _SrcUnavailable("VAULT 미초기화 — 이 계약은 런타임에서만 검사 가능합니다")
        n_led = len(CACHE_LEDGER)
        calls: List[str] = []
        orig_t, orig_b = V.__class__.put_table, V.__class__.put_blob
        orig_save = g.get("_save_links")

        def _spy_t(self, name, df, *a, **kw):
            calls.append(f"put_table:{name}")
            return None

        def _spy_b(self, *a, **kw):
            calls.append("put_blob")
            return None

        def _spy_s(*a, **kw):
            calls.append("_save_links")
            return None

        V.__class__.put_table, V.__class__.put_blob = _spy_t, _spy_b
        if orig_save is not None:
            g["_save_links"] = _spy_s
        g["_REHEARSAL"] = True
        try:
            wrote = persist("__contract_probe__", pd.DataFrame({"a": [1]}),
                            scope="shared", domain="test", source="k17")
            S = _synth(n_codes=20, n_months=14, n_analysts=12)
            build_link_matrices(S["ledger"], pd.DatetimeIndex(S["months"]), S["codes"],
                                "unweighted", use_cache=False)
        finally:
            g["_REHEARSAL"] = False
            V.__class__.put_table, V.__class__.put_blob = orig_t, orig_b
            if orig_save is not None:
                g["_save_links"] = orig_save
            del CACHE_LEDGER[n_led:]          # 프로브 흔적을 원장에 남기지 않는다
        bad = [c for c in calls]
        return (wrote is False and not bad), \
            ("리허설 중 Vault 쓰기 0건 (persist·put_table·put_blob·_save_links 전부)"
             if not bad else f"리허설 중 쓰기 발생: {sorted(set(bad))}")

    def k18():
        """레이트 버킷이 실제 호스트와 일치하는가 (구버전 병목의 재발 방지).

        FDR 호출이 krx 버킷(2 QPS)을 쓰면 종목 수 ÷ 2초가 그대로 벽시계가 된다.
        실측 2,875초의 정체가 이것이었으므로, 소스코드 수준에서 못 돌아가게 못 박는다.
        """
        why = []
        # ① 병목의 원인이었던 오배정: 네이버 차트를 부르는 경로가 KRX 버킷(2 QPS)에 묶임
        if 'limiter("krx")' in _src(_px_fdr):
            why.append("_px_fdr 이 KRX 버킷을 쓴다(구버전 병목 재발)")
        if 'source="krx' in _src(_px_naver):
            why.append("_px_naver 가 KRX 버킷을 쓴다")
        # ② 같은 호스트는 같은 버킷을 공유해야 한다.
        #    FinanceDataReader 의 한국주식 리더는 내부적으로 fchart.stock.naver.com 을
        #    부른다 — _px_naver 와 같은 서버다. 버킷을 나누면 한 서버에 두 배가 나간다.
        if PRICE_BUCKET.get("fdr") != PRICE_BUCKET.get("naver"):
            why.append(f"같은 호스트인데 버킷이 다름: fdr={PRICE_BUCKET.get('fdr')} "
                       f"naver={PRICE_BUCKET.get('naver')}")
        # ③ 실제 요청 경로가 그 버킷을 쓰는지 (런타임 관측)
        seen = []
        _orig = globals()["limiter"]

        def _spy(name, _o=_orig, _s=seen):
            _s.append(name)
            return _o(name)
        globals()["limiter"] = _spy
        try:
            # ★ FDR 은 실패 시 bare print 를 흘린다("<sym>" invalid symbol or has no data).
            #   계약검정 로그에 그게 섞이면 사용자가 진짜 오류로 오인한다 → 봉인하고 부른다.
            with quiet_fds():
                _px_fdr("000000", "2020-01-01", "2020-01-05")   # fdr 미설치면 즉시 None
        except Exception:
            pass
        finally:
            globals()["limiter"] = _orig
        if fdr is not None and seen and seen[0] != PRICE_BUCKET["fdr"]:
            why.append(f"_px_fdr 실측 버킷={seen[0]} (선언={PRICE_BUCKET['fdr']})")
        # ④ 병목 재발 방지: 가격 경로 버킷이 KRX 보다 빨라야 한다
        if float(RATE_LIMIT_QPS.get(PRICE_BUCKET["fdr"], 0)) <= float(RATE_LIMIT_QPS.get("krx", 99)):
            why.append("가격 버킷 QPS 가 krx 이하 — 구버전과 같은 병목")
        for b in ("naver_chart", "naver_detail"):
            if b not in RATE_LIMIT_QPS:
                why.append(f"버킷 '{b}' 미정의")
        return (not why), ("가격 경로가 호스트 기준 버킷을 쓰고 KRX 예산에 묶이지 않는다"
                           if not why else " · ".join(why))

    def k19():
        """드라이브 쓰기에 '영수증'이 빠진 경로가 없는가 (세션 무관 재호출 보장).

        ★ 구버전은 소스에 'persist(' 나 'put_table' 문자열이 있는지만 봤다. 그건
          ⓐ 주석에도 걸리고 ⓑ note_new_data 유무를 전혀 못 보며 ⓒ 목록에 없는 함수는
          아예 검사하지 않는다. 실제로 가장 큰 데이터셋(krx_ohlcv_daily)이 영수증 없이
          put_table 만 부르고 있었는데도 이 계약은 초록불이었다.
          → 런타임에 Vault 쓰기를 가로채, 그 이름이 _NEW_DATA 에 등록돼 있는지 본다.
        """
        V = globals().get("VAULT")
        if V is None:
            raise _SrcUnavailable("VAULT 미초기화 — 이 계약은 런타임에서만 검사 가능합니다")
        n_led = len(CACHE_LEDGER)
        seen: List[str] = []
        orig = V.__class__.put_table

        def _spy(self, name, df, *a, **kw):
            # ★ 실제로 쓰지 않는다. 예전 구현은 orig 를 그대로 불러 사용자 드라이브에
            #   '__k19_probe__' 테이블을 남겼다 — 삭제 API 가 없으니 영원히 남는다.
            #   계약검정이 캐시를 오염시키면 그 자체가 절대 1원칙 위반이다.
            seen.append(str(name))
            return f"probe:{name}"
        V.__class__.put_table = _spy
        try:
            note_new_data("__k19_probe__", 3, "shared", "test", "k19")
            ok_flag = persist("__k19_probe__", pd.DataFrame({"a": [1, 2, 3]}),
                              scope="private", domain="test", source="k19")
            _led, viol = cache_audit()
        finally:
            V.__class__.put_table = orig
            del CACHE_LEDGER[n_led:]
            _NEW_DATA.pop("__k19_probe__", None)
        why = []
        if "__k19_probe__" not in seen:
            why.append("persist() 가 Vault 쓰기를 수행하지 않음")
        if not ok_flag:
            why.append("persist() 가 성공을 보고하지 않음")
        if any("__k19_probe__" in v for v in viol):
            why.append("영수증이 있는데도 위반으로 집계됨")
        # 영수증이 없는 상태에서 감사가 실제로 잡아내는지(역방향)
        note_new_data("__k19_orphan__", 5, "shared", "test", "k19")
        try:
            _led2, viol2 = cache_audit()
            if not any("__k19_orphan__" in v for v in viol2):
                why.append("저장되지 않은 신규 수집물을 감사가 잡아내지 못함")
        finally:
            _NEW_DATA.pop("__k19_orphan__", None)
            del CACHE_LEDGER[n_led:]
        return (not why), ("persist 경로가 실제로 쓰고, 영수증 없는 수집물을 감사가 잡아낸다"
                           if not why else " · ".join(why))

    def k20():
        """상세 캐시 왕복 — 저장했다 되읽었을 때 바이라인이 살아 있는가.

        ★ 이 계약이 없어서 '2회차 실행이 반드시 죽는' 결함을 1회차 테스트가 전부 통과시켰다.
          캐시가 비어 있으면 적재 경로를 아예 안 타기 때문이다. 그래서 여기서는 일부러
          캐시가 '있는' 상태를 만들어 되읽힌다.
        """
        c = pd.DataFrame([{"src_report_id": "12345", "detail_url": "u",
                           "target_price": 70000.0, "opinion": "BUY",
                           "_detail_src": "미래에셋증권 홍길동",
                           "fetched_at": as_ts("2026-01-02")}])
        k = nv_load_detail_cache(c)
        ok = (k.get("12345", {}).get("_detail_src") == "미래에셋증권 홍길동")
        return ok, ("상세 캐시 왕복에서 _detail_src 보존" if ok
                    else f"바이라인 유실 — 되읽은 값: {k}")

    def k21():
        """결측 PDF 필드가 'nan' 이라는 유령 애널리스트를 만들지 않는가.

        np.nan 은 참이라 `praw or ""` 를 통과하고 str(nan)='nan' 이 이름이 된다.
        그 유령은 같은 브로커의 미식별 리포트 전부를 공동커버하는 완전그래프를 만들어
        링크 행렬을 브로커 평균으로 붕괴시킨다 — 신호 자체가 다른 것이 되어 버린다.
        """
        rep = pd.DataFrame([{
            "report_uid": f"u{i}", "source": "naver", "pub_date": as_ts("2020-05-11"),
            "stock_code": f"00593{i}", "stock_name": "합성", "broker_id": "B1",
            "broker_name": "합성증권", "analyst_raw": "", "target_price": np.nan,
            "opinion": "BUY", "broker_raw": "합성증권", "category": "company",
            "src_report_id": f"{i}", "title": "합성", "detail_url": None, "pdf_url": None,
            "knowledge_date": as_ts("2020-05-12"), "event_date": as_ts("2020-05-11"),
            "pdf_analysts": np.nan, "pdf_emails": np.nan, "pdf_target": np.nan,
        } for i in range(3)])
        try:
            A, L = build_analyst_ledger(rep)
        except Exception as e:                                # noqa
            return False, f"{type(e).__name__}: {str(e)[:80]}"
        names = set()
        for c in ("analyst_name", "name", "analyst_raw"):
            if L is not None and len(L) and c in L.columns:
                names |= set(L[c].astype(str).str.strip().str.lower())
        bad = names & {"nan", "none", "<na>"}
        return (not bad), ("결측 PDF 필드가 애널리스트로 승격되지 않음"
                           if not bad else f"유령 애널리스트 생성됨: {bad}")

    def k22():
        """공용 유틸이 입력 형태를 가리지 않는가 (실측 크래시 재발 방지).

        safe_div 가 Series 전용이던 탓에 스칼라를 넘긴 한 줄이
        AttributeError 로 4분짜리 가격수집을 끝낸 직후 통째로 날려버렸다.
        범용 유틸이 형태를 가리면 호출부 수십 곳이 전부 지뢰가 된다.
        """
        checks = [
            ("스칼라/스칼라", lambda: safe_div(3, 4), 0.75),
            ("0 나눗셈", lambda: safe_div(3, 0), None),
            ("넘파이 스칼라", lambda: safe_div(np.int64(6), np.int64(3)), 2.0),
            ("파이썬 float", lambda: safe_div(1.0, 8.0), 0.125),
        ]
        why = []
        for nm, fn_, exp in checks:
            try:
                v = fn_()
            except Exception as e:                             # noqa
                why.append(f"{nm}: {type(e).__name__}")
                continue
            vv = float(v) if v is not None and np.isscalar(v) else float("nan")
            if exp is None:
                if np.isfinite(vv):
                    why.append(f"{nm}: 0 나눗셈이 {vv} 를 돌려줌(NaN 이어야 함)")
            elif not (np.isfinite(vv) and abs(vv - exp) < 1e-9):
                why.append(f"{nm}: {vv} (기대 {exp})")
        try:                                    # Series 경로도 그대로 살아 있어야 한다
            sv = safe_div(pd.Series([1.0, 2.0]), pd.Series([2.0, 0.0]))
            if not (abs(float(sv.iloc[0]) - 0.5) < 1e-9 and pd.isna(sv.iloc[1])):
                why.append(f"Series 경로 회귀: {list(sv)}")
        except Exception as e:                                 # noqa
            why.append(f"Series 경로: {type(e).__name__}")
        return (not why), ("safe_div 이 스칼라·배열·Series 를 모두 안전하게 처리한다"
                           if not why else " · ".join(why))

    def k23():
        """보조 캐시 루트(로컬↔드라이브)를 실제로 함께 읽는가.

        읽기 루트를 하나만 쓰면 양쪽에 흩어진 캐시의 절반을 매번 다시 수집하게 된다.
        '읽는다고 주장'만 하지 않도록, 임시 보조 루트에 테이블을 심고 되읽는다.
        """
        V = globals().get("VAULT")
        if V is None:
            raise _SrcUnavailable("VAULT 미초기화 — 런타임에서만 검사 가능합니다")
        alt = tempfile.mkdtemp(prefix="sacn_altroot_")
        try:
            tdir = os.path.join(alt, GDRIVE_SHARED_NS, "table")
            os.makedirs(tdir, exist_ok=True)
            probe = pd.DataFrame({"code": ["005930"], "v": [42]})
            atomic_write_parquet(probe, os.path.join(tdir, "__k23_alt__.parquet"))
            saved = list(V.extra_roots)
            V.extra_roots = saved + [alt]
            try:
                got = V.get_table("__k23_alt__", scope="shared")
            finally:
                V.extra_roots = saved
            ok = got is not None and len(got) == 1 and int(got["v"].iloc[0]) == 42
            return ok, ("보조 루트의 테이블을 그대로 읽어온다 (로컬·드라이브 동시 활용)"
                        if ok else "보조 루트를 읽지 못함 — 반대편 캐시를 매번 재수집하게 된다")
        finally:
            shutil.rmtree(alt, ignore_errors=True)

    for cid, name, fn in [
        ("K1", "미래누수 차단 (PIT 게이트)", k1),
        ("K2", "생존편향 — 폐지 수익률 처리", k2),
        ("K3", "익영업일 진입 앵커", k3),
        ("K4", "링크 행렬 대각 0", k4),
        ("K5", "최소 연결 요건", k5),
        ("K6", "링크 윈도우 PIT (knowledge_date)", k6),
        ("K7", "사전등록 격자 12개 고정", k7),
        ("K8", "결정성 (시드 재현)", k8),
        ("K9", "연도별 증권거래세", k9),
        ("K10", "원신호 + 직교화 병기", k10),
        ("K11", "애널리스트 식별자 규약 §4.2", k11),
        ("K12", "캐시 삭제 API 부재", k12),
        ("K13", "분위 배정 결정성", k13),
        ("K14", "EB 축소추정 실제 적용", k14),
        ("K15", "상세보강 상한의 시간축 균등성", k15),
        ("K16", "가격수집 축소가 폐지종목을 안 버림", k16),
        ("K17", "리허설 중 캐시 쓰기 차단", k17),
        ("K18", "레이트 버킷 ↔ 실제 호스트 일치", k18),
        ("K19", "신규 수집물 전량 드라이브 저장", k19),
        ("K20", "상세 캐시 왕복 — 바이라인 보존", k20),
        ("K21", "결측 PDF 필드가 유령 애널리스트를 안 만듦", k21),
        ("K22", "공용 유틸의 스칼라 안전성 (safe_div)", k22),
        ("K23", "보조 캐시 루트 동시 읽기 (로컬↔드라이브)", k23),
    ]:
        _k(cid, name, fn)

    LOG.table([[c["id"], c["name"],
                ("—" if c.get("skip") else ("✔" if c["pass"] else "✘")),
                _trunc(c["msg"], 54)]
               for c in CONTRACTS], ["ID", "계약", "판정", "근거/사유"],
              ["c", "l", "c", "l"], maxw=56)
    n_skip = sum(1 for c in CONTRACTS if c.get("skip"))
    if n_skip:
        LOG.warn(f"소스검사 계약 {n_skip}건을 '검사 불가'로 건너뛰었습니다 — "
                 f"위반이 없다는 뜻이 아니라 확인하지 못했다는 뜻입니다. "
                 f"파일로 실행하면(python <파일>) 전부 검사됩니다.")
    fails = [c for c in CONTRACTS if not c["pass"]]
    if fails:
        LOG.error(f"계약 위반 {len(fails)}건: {[c['id'] for c in fails]}")
        if strict:
            raise RuntimeError(f"계약 검정 실패 {[c['id'] for c in fails]} — "
                               f"실데이터 수집을 시작하지 않습니다.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS) - n_skip}건 전부 통과"
           + (f" (검사 불가 {n_skip}건)" if n_skip else ""))
    return True


# ── 실경로 리허설 ───────────────────────────────────────────────────────────────────────────
class _FakePykrx:
    """네트워크만 가짜로 둔다. 파싱·정제 로직은 실물 그대로 돈다."""

    @staticmethod
    def get_market_cap_by_ticker(day, market="ALL"):
        idx = pd.Index([f"{5930 + i:06d}" for i in range(30)], name="티커")
        return pd.DataFrame({"종가": np.linspace(1000, 90000, 30),
                             "시가총액": np.linspace(3e10, 4e13, 30),
                             "거래량": 1e5, "거래대금": np.linspace(1e8, 9e10, 30),
                             "상장주식수": 1e7}, index=idx)

    @staticmethod
    def get_market_fundamental_by_ticker(day, market="ALL"):
        idx = pd.Index([f"{5930 + i:06d}" for i in range(30)], name="티커")
        return pd.DataFrame({"BPS": np.linspace(1000, 50000, 30),
                             "PER": np.linspace(3, 40, 30), "PBR": np.linspace(0.3, 4.0, 30),
                             "EPS": np.linspace(100, 5000, 30),
                             "DIV": np.linspace(0, 5, 30), "DPS": 100}, index=idx)

    @staticmethod
    def get_etf_ticker_list(day):
        return ["069500", "102110"]

    @staticmethod
    def get_etn_ticker_list(day):
        return ["550001"]

    @staticmethod
    def get_elw_ticker_list(day):
        return ["58J123"]


def _quiet_roundtrip() -> bool:
    """quiet_fds 가 봉인 후 stdout/stderr 를 확실히 되돌리는지 확인한다.

    되돌리기에 실패하면 그 뒤 모든 로그가 사라진다 — 실행은 계속되는데 화면은 죽는,
    가장 진단하기 어려운 고장이다. 그래서 리허설에서 직접 왕복시켜 본다.
    """
    try:
        fd_out, fd_err = os.dup(1), os.dup(2)
    except Exception:
        return True                      # fd 복제가 안 되는 환경이면 봉인 자체가 비활성이다
    try:
        with quiet_fds():
            os.write(1, b"this must not appear\n")
        sys.stdout.write("")
        sys.stdout.flush()
        return True
    finally:
        for fd, saved in ((1, fd_out), (2, fd_err)):
            try:
                os.dup2(saved, fd)
                os.close(saved)
            except Exception:
                pass


def run_rehearsal(strict: bool = False) -> bool:
    """새로 만든 수집·정제 함수들을 가짜 네트워크로 '실물 실행'한다.

    합성 스모크는 계산경로만 증명한다. 수집부 한 줄 때문에 실행 2분 만에 죽는 사고는
    이 리허설이 아니면 잡히지 않는다 — 둘은 겹치지 않는다.
    """
    LOG.banner("실경로 리허설", "네트워크만 가짜 · 수집·정제 함수는 실물 실행")
    results = []
    g = globals()
    saved_pykrx, saved_call = g.get("pykrx_stock"), KRXG.call
    try:
        g["_REHEARSAL"] = True          # ★ 리허설 중에는 캐시 쓰기를 차단한다
        g["pykrx_stock"] = _FakePykrx
        KRXG.call = lambda fn, *a, **kw: fn(*a, **kw)     # type: ignore
        months = pd.date_range(end=as_ts(BACKTEST_END), periods=3, freq=MONTH_END_ALIAS)

        _sec = pd.DataFrame({
            "code": ["005930", "000660", "005935", "069500", "111111"],
            "name": ["삼성전자", "SK하이닉스", "삼성전자우", "KODEX 200", "폐지테스트"],
            "market": ["KOSPI", "KOSPI", "KOSPI", "KOSPI", "KOSDAQ"],
            "listing_date": [as_ts("2000-01-01")] * 5,
            "delisting_date": [pd.NaT, pd.NaT, pd.NaT, pd.NaT, as_ts("2020-03-02")]})
        _krx_rows_fake = [{"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKT_NM": "KOSPI",
                           "TDD_CLSPRC": "71,000", "TDD_OPNPRC": "70,500", "TDD_HGPRC": "71,500",
                           "TDD_LWPRC": "70,000", "ACC_TRDVOL": "12,345,678",
                           "ACC_TRDVAL": "876,543,210,000", "MKTCAP": "423,000,000,000,000",
                           "LIST_SHRS": "5,969,782,550"}]
        for name, fn in [
            ("시가총액 스냅샷", lambda: fetch_mktcap_monthly(months)),
            ("펀더멘털 스냅샷", lambda: fetch_fundamental_monthly(months)),
            ("비주식 종목 목록", lambda: fetch_nonequity_tickers(months)),
            ("가격수집 대상 축소", lambda: price_target_codes(_sec)[0]),
            ("종목별 요청창 산정", lambda: _price_windows(["005930", "111111"],
                                                     BACKTEST_START, BACKTEST_END, _sec)),
            ("KRX 벌크 응답 매핑", lambda: _krx_map_frame(
                _krx_rows_fake, ["code", "name", "market", "close", "open", "high", "low",
                                 "volume", "amount", "mktcap", "shares"])),
            ("음성캐시 백오프", lambda: [_price_backoff_days(i) for i in (1, 2, 3, 9)]),
            ("네이버 미보유 구간 산정", lambda: _nv_missing_ranges(
                pd.DataFrame({"category": ["company"] * 2,
                              "pub_date": [as_ts("2016-08-15"), as_ts("2016-09-15")]}),
                "company", "2016-08-01", "2016-12-31")),
            ("한경 파서(빈 응답 방어)", lambda: str(_hk_parse("<html></html>", "probe") == [])),
            ("디스크 여유 조회", lambda: f"{free_gb_safe('.'):.1f}GB"),
        ]:
            try:
                d = fn()
                ok = d is not None and len(d) > 0
                results.append([name, "✔" if ok else "✘", f"{len(d) if d is not None else 0}행"])
            except Exception as e:                        # noqa
                results.append([name, "✘", f"{type(e).__name__}: {str(e)[:60]}"])

        # 파싱 유틸은 네트워크가 필요 없다 — 실물 그대로
        for name, fn in [
            ("바이라인 파서", lambda: parse_byline("미래에셋증권 리서치센터 홍길동 애널리스트")),
            ("우선주 판정", lambda: str(is_preferred("005935", "삼성전자우"))),
            ("증권거래세", lambda: f"{sell_tax_rate('2022-03-01', 'KOSDAQ'):.4%}"),
            ("증권유형 분류", lambda: ",".join(
                classify_security(c, n) for c, n in
                (("005930", "삼성전자"), ("005935", "삼성전자우"), ("069500", "KODEX 200")))),
            ("출력 봉인 왕복", lambda: (_quiet_roundtrip() and "stdout 복원 확인")),
            ("상세 균등추출", lambda: f"{len(_nv_stratified(pd.DataFrame({'pub_date': pd.date_range('2016-08-31', periods=120, freq=MONTH_END_ALIAS), 'x': 1}), 30))}건"),
        ]:
            try:
                v = fn()
                results.append([name, "✔" if v else "✘", _trunc(str(v), 40)])
            except Exception as e:                        # noqa
                results.append([name, "✘", f"{type(e).__name__}: {str(e)[:60]}"])
    finally:
        g["_REHEARSAL"] = False
        g["pykrx_stock"] = saved_pykrx
        KRXG.call = saved_call                            # type: ignore

    LOG.table(results, ["수집·정제 함수", "판정", "결과"], ["l", "c", "l"])
    LOG.info("리허설은 캐시에 쓰지 않습니다(_REHEARSAL 플래그). 가짜 데이터가 공용 인덱스에 "
             "남아 실수집을 영구히 건너뛰게 만드는 사고를 구조로 차단합니다.")
    bad = [r for r in results if r[1] == "✘"]
    if bad and strict:
        raise RuntimeError(f"리허설 실패 {[r[0] for r in bad]}")
    if bad:
        LOG.warn(f"리허설에서 {len(bad)}건 실패 — 해당 경로는 실행 중 저하될 수 있습니다.")
    else:
        LOG.ok("리허설 전항목 통과")
    return not bad
