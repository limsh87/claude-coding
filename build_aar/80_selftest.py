

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  합성데이터 엔드투엔드 스모크 — 실데이터를 건드리기 전에 '계산 경로'를 증명한다             ║
# ║                                                                                          ║
# ║  검정하는 것:                                                                             ║
# ║   ① 주의패널 → 축소 → 통제회귀 → VAS → AAR → 백테스트가 예외 없이 끝까지 도는가            ║
# ║   ② **심어둔 신호를 실제로 탐지하는가** (하네스 민감도). 이게 없으면 실데이터에서           ║
# ║      "신호 없음"이 나와도 그게 전략 탓인지 배관 탓인지 구분할 수 없다.                      ║
# ║   ③ 무정보 난수에서는 신호를 만들어내지 않는가 (거짓양성 방어)                              ║
# ║                                                                                          ║
# ║  ★ 격리 원칙: 합성 종목코드는 'ZZ' 로 시작해 **실제 티커 공간과 충돌하지 않는다.**          ║
# ║    과거에 합성 '000001' 이 전역 PIT 에 남아 실데이터를 오염시킨 사고가 있었다.              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SYNTH_PREFIX = "ZZ"


def make_synthetic(n_analyst: int = 150, n_stock: int = 300, n_month: int = 84,
                   signal_strength: float = 0.0, seed: int = SEED
                   ) -> Dict[str, "pd.DataFrame"]:
    """합성 리포트 원장 + 가격 패널. signal_strength>0 이면 '주의 증가 → 다음달 수익'을 심는다.

    ★ 심는 방식이 중요하다. 애널리스트마다 **독립적으로** 무작위 종목을 밀어주면,
      종목 단위로 집계(AAR_pos)하는 순간 커버 애널 수만큼 희석되어 하네스가 탐지할 수
      없는 크기가 된다. 실제 현상도 그렇지 않다 — 좋은 소식은 여러 애널리스트의 주의를
      **동시에** 끈다. 그래서 매월 소수의 '주목 종목'을 뽑고 그 종목을 커버하는
      애널리스트들이 함께 주의를 늘리는 구조로 심는다.
    """
    rng = np.random.default_rng(seed)
    months = pd.date_range("2016-01-31", periods=n_month, freq="ME")
    codes = [f"{SYNTH_PREFIX}{i:04d}" for i in range(n_stock)]
    analysts = [f"AN{i:03d}" for i in range(n_analyst)]
    brokers = [f"BR{i%12:02d}" for i in range(n_analyst)]
    sectors = {c: f"SEC{i % 8}" for i, c in enumerate(codes)}

    # 각 애널리스트는 15~25종목을 커버한다 (명세의 현실적 가정)
    cover = {a: list(rng.choice(codes, size=int(rng.integers(15, 26)), replace=False))
             for a in analysts}
    # 매월 '주목 종목' 집합 — 이것이 심어둔 신호의 원천이다
    hot = {m: set(rng.choice(codes, size=max(4, n_stock // 25), replace=False))
           for m in months} if signal_strength > 0 else {m: set() for m in months}
    rows = []
    rid = 0
    attn: Dict[Tuple[str, Any], int] = {}
    for a, br in zip(analysts, brokers):
        for m in months:
            k = int(rng.poisson(6)) + 2                       # 월 발간량
            picks = list(rng.choice(cover[a], size=min(k, len(cover[a])), replace=True))
            # 커버 중인 주목 종목이 있으면 높은 확률로 주의를 몰아준다
            for c in cover[a]:
                if c in hot[m] and rng.random() < 0.75:
                    picks += [c] * 4
                    attn[(str(c), m)] = attn.get((str(c), m), 0) + 1
            for c in picks:
                rid += 1
                rows.append({"report_uid": f"R{rid:07d}", "analyst_id": a,
                             "broker_id": br, "broker_legal_id": br,
                             "broker_name": br, "broker_legal_name": br,
                             "code": str(c), "month": m, "pub_date": m,
                             "category": "기업",
                             "target_price": float(rng.integers(8000, 90000)),
                             "opinion": "BUY", "link_method": "list_field", "link_conf": 0.98})
            # 산업리포트 (종목 없음) — N(a,t) 분모에 들어가야 한다
            if rng.random() < 0.3:
                rid += 1
                rows.append({"report_uid": f"R{rid:07d}", "analyst_id": a,
                             "broker_id": br, "broker_legal_id": br,
                             "broker_name": br, "broker_legal_name": br,
                             "code": np.nan, "month": m, "pub_date": m,
                             "category": "산업", "target_price": np.nan, "opinion": None,
                             "link_method": "list_field", "link_conf": 0.98})
    L = pd.DataFrame(rows)
    L["analyst_person_id"] = L["analyst_id"]

    # 가격: 랜덤워크 + 심어둔 신호
    prow = []
    for c in codes:
        px = 10000.0
        for m in months:
            r = float(rng.normal(0.005, 0.09))
            if signal_strength > 0 and attn.get((c, m - pd.offsets.MonthEnd(1)), 0) > 0:
                r += signal_strength
            px *= (1 + r)
            prow.append({"code": c, "month": m, "adj_close": px, "exec_px": px,
                         "marcap": px * 1e6 * (1 + (hash(c) % 100) / 20.0),
                         "adv20": 5e8 + (hash(c) % 97) * 1e7,
                         "market": "KOSPI" if (hash(c) % 3) else "KOSDAQ",
                         "signal_date": m, "next_date": m + pd.Timedelta(days=1),
                         "next_close": px, "amount": 5e8, "volume": 1e5,
                         "stocks": 1e6, "dept": "", "name": c, "Close": px})
    P = pd.DataFrame(prow).sort_values(["code", "month"]).reset_index(drop=True)
    g = P.groupby("code", observed=True)
    for k in (1, 2, 3):
        P[f"fwd_ret{k}"] = g["exec_px"].shift(-k) / P["exec_px"] - 1.0
    P["fwd_ret"] = P["fwd_ret1"]

    sec = pd.DataFrame({"code": codes, "name": codes,
                        "sector": [sectors[c] for c in codes],
                        "industry": [sectors[c] for c in codes],
                        "market": "KOSPI", "listing_date": months[0] - pd.Timedelta(days=800),
                        "delisting_date": pd.NaT, "delist_reason": "", "delist_to": None})
    uni = P[["code", "month", "marcap", "market"]].copy()
    uni["size_rank"] = uni.groupby("month", observed=True)["marcap"].rank(method="first")
    uni["size_pct"] = uni.groupby("month", observed=True)["marcap"].rank(pct=True)
    ctrl = pd.DataFrame([{"code": c, "month": m,
                          "earnings_month": 1.0 if m.month in (3, 5, 8, 11) else 0.0,
                          "log_disclosure": float(np.log1p(rng.integers(0, 8)))}
                         for c in codes for m in months])
    return {"links": L, "panel": P, "sec": sec, "uni": uni, "ctrl": ctrl,
            "months": pd.DatetimeIndex(months), "analysts": pd.DataFrame(
                {"analyst_id": analysts, "analyst_person_id": analysts,
                 "person_unclassified": False, "broker_legal_id": brokers,
                 "broker_legal_name": brokers, "name": analysts,
                 "first_seen": months[0], "last_seen": months[-1]})}


def _synth_pipeline(S: Dict[str, "pd.DataFrame"]) -> Tuple["pd.DataFrame", dict]:
    """합성 데이터로 신호까지 만든다 (전역 PIT 를 건드리지 않는다)."""
    months = S["months"]
    P = build_attention_panel(S["links"], months, S["sec"], unit_mode="ANALYST")
    if P.empty:
        return pd.DataFrame(), {}
    P = attach_controls(P, S["ctrl"], S["uni"])
    V, _, _ = compute_vas(P, months)
    pos = build_aar_pos(V, "uw")
    drops = classify_coverage_drops(S["links"], S["analysts"], months, S["sec"], S["uni"])
    neg = build_aar_neg(drops["signal"], S["links"], months)
    sig = assemble_signal(pos, neg, S["uni"], lam=1.0)
    return sig, {"panel": P, "vas": V, "drops": drops}


def run_selftest(full_chain: bool = False) -> bool:
    LOG.banner("합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산 경로와 '신호 탐지 능력'을 증명한다")
    ok_all = True
    t0 = time.time()

    # ── ① 무신호 데이터에서 파이프라인이 도는가 ────────────────────────────────────────
    S0 = make_synthetic(signal_strength=0.0, seed=SEED)
    try:
        sig0, aux0 = _synth_pipeline(S0)
    except Exception as e:                                        # noqa
        LOG.error(f"무신호 합성 파이프라인 실패: {type(e).__name__}: {e}")
        for ln in traceback.format_exc().split("\n")[-10:]:
            _safe_print("   " + ln)
        return False
    if sig0.empty:
        LOG.error("합성 신호가 비었습니다 — 주의패널부터 신호까지의 경로가 끊겨 있습니다.")
        return False
    bt0 = run_backtest(sig0, S0["panel"], S0["months"], S0["sec"], hold=1, label="SMOKE_null")
    s0 = perf_stats(bt0["returns"])

    # ── ② 신호를 심으면 탐지하는가 (하네스 민감도) ────────────────────────────────────
    S1 = make_synthetic(signal_strength=0.05, seed=SEED + 1)
    sig1, aux1 = _synth_pipeline(S1)
    bt1 = run_backtest(sig1, S1["panel"], S1["months"], S1["sec"], hold=1, label="SMOKE_signal")
    s1 = perf_stats(bt1["returns"])

    sp0 = quantile_spread(sig0, S0["panel"], S0["months"], hold=1)
    sp1 = quantile_spread(sig1, S1["panel"], S1["months"], hold=1)
    m0, t0s = hac_tstat(sp0["spread"].to_numpy()) if len(sp0) > 12 else (np.nan, np.nan)
    m1, t1s = hac_tstat(sp1["spread"].to_numpy()) if len(sp1) > 12 else (np.nan, np.nan)

    LOG.table([["합성 리포트", f"{len(S0['links']):,}건"],
               ["주의패널 행수", f"{len(aux0.get('panel', [])):,}"],
               ["VAS 산출", f"{int(aux0['vas']['VAS'].notna().sum()):,}" if aux0 else "—"],
               ["철회 사건", f"{len(aux0['drops']['signal']):,}" if aux0 else "—"],
               ["신호 종목-월", f"{len(sig0):,}"],
               ["── 무신호 ──", ""],
               ["Q5−Q1 스프레드", f"{m0*100:+.3f}%p (t={t0s:.2f})"],
               ["백테스트 Sharpe", f"{s0.get('Sharpe', np.nan):.3f}"],
               ["── 신호 주입(+5%/월) ──", ""],
               ["Q5−Q1 스프레드", f"{m1*100:+.3f}%p (t={t1s:.2f})"],
               ["백테스트 Sharpe", f"{s1.get('Sharpe', np.nan):.3f}"],
               ["평균 보유종목", f"{s1.get('평균종목수', np.nan):.1f}"]],
              ["항목", "값"], ["l", "r"], title="스모크 결과")

    sensitive = bool(np.isfinite(t1s) and np.isfinite(t0s) and (t1s - t0s) > 1.0
                     and m1 > m0)
    if not sensitive:
        LOG.error("★ 하네스 민감도 실패 — 신호를 명시적으로 심었는데도 탐지하지 못했습니다. "
                  "체결 정렬·수익 계산·신호 결합 중 하나가 고장난 것이며, 이 상태에서 "
                  "실데이터를 돌리면 '알파 없음'이 전략 탓인지 배관 탓인지 구분할 수 없습니다.")
        ok_all = False
    else:
        LOG.ok(f"하네스 민감도 확인 — 심어둔 신호에 t 가 {t0s:.2f} → {t1s:.2f} 로 반응합니다. "
               f"이제 실데이터 결과를 신뢰할 근거가 생겼습니다.")

    if np.isfinite(t0s) and abs(t0s) > 2.5:
        LOG.warn(f"무신호 데이터에서 t={t0s:.2f} 가 나왔습니다 — 거짓양성 가능성이 있습니다. "
                 f"우연일 수 있으나(시드 1개) 실데이터 결과를 그만큼 할인해 읽으십시오.")

    # ── ③ 전역 상태 오염 검사 ─────────────────────────────────────────────────────────
    leaked = [n for n in PIT.names() if not PIT._meta.get(n, {}).get("empty", True)]
    if leaked:
        LOG.warn(f"스모크 후 전역 PIT 에 테이블이 남아 있습니다: {leaked}. "
                 f"합성 코드는 'ZZ' 접두라 실제 티커와 충돌하지 않지만, "
                 f"등록 자체를 하지 않는 것이 원칙입니다.")
    LOG.ok(f"스모크 완료 {time.time()-t0:.1f}s — "
           f"{'전부 통과' if ok_all else '★ 민감도 검정 실패'}")
    return ok_all
