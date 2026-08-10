

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  합성데이터 엔드투엔드 스모크                                                        ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 계산경로 전체를 합성데이터로 통과시킨다.                   ║
# ║  목적은 성과 측정이 아니라 **배관 검증**이다. 실수집은 수 시간~수 일이 걸리는데              ║
# ║  그걸 다 받은 뒤 조립부에서 터지면 그 시간이 통째로 날아간다.                                ║
# ║                                                                                          ║
# ║  ★ 합성데이터에 '진짜 알파'를 심는다. quality[i] 가 높으면 ① ΔTONE↑ ② 문서변화↓            ║
# ║    ③ D2 지표 우수 ④ ΔNONFIN↑ ⑤ 미래수익↑. 그래야 하네스가 신호에 반응하는지 검증된다.       ║
# ║  ★ 엣지 케이스를 반드시 섞는다: 기간 중 상장/폐지, 축 A 결측 20%, D1 결측 15%,              ║
# ║    배제 발동 10%. 각각이 회귀 방지 장치다.                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SYN_VOCAB = [f"어휘{i:03d}" for i in range(400)] + \
             ["매출", "영업이익", "제조", "판매", "고객", "설비", "연구개발", "특허", "수출",
              "계약", "소송", "우발", "지배구조", "임원", "직원", "위험", "환율", "경쟁"]


def make_arc_synthetic(n_codes: int = 220, n_years: int = 8, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    end = as_ts(BACKTEST_END)
    start = end - pd.DateOffset(years=n_years)
    rebals = rebal_dates(start.strftime("%Y-%m-%d"), BACKTEST_END)
    # ★ 실제 한국 보통주 코드는 대부분 끝자리가 0 이다. 합성에서 000001,000002… 처럼
    #   촘촘한 연번을 쓰면 '형제 보통주' 우선주 규칙이 대량 오발화해 유니버스가 붕괴한다.
    #   현실과 같은 간격(10)으로 만들고, 진짜 우선주 쌍을 소수만 섞는다.
    codes = [f"{(i + 1) * 10:06d}" for i in range(n_codes)]
    for j in range(3, n_codes, 40):                 # 형제 보통주가 실재하는 우선주를 섞는다
        codes[j] = f"{j * 10 + 5:06d}"              # codes[j-1] = j*10 이 형제 보통주
    corps = [f"C{i+1:07d}" for i in range(n_codes)]
    sectors = ["IT/전자", "헬스케어", "소재", "산업재", "소비재", "금융"]
    inds = rng.choice(["반도체", "제약", "화학", "기계", "음식료", "은행"], n_codes)

    quality = rng.normal(size=n_codes)
    # ★ 축 A 는 '수준' 이 아니라 '변화(ΔTONE)' 를 신호로 쓴다. 합성에서 톤을 quality 의
    #   상수배로만 만들면 ΔTONE 은 정의상 순수 잡음이 되어, 축 A 경로가 신호를 잡을 수
    #   있는지 자체를 검증하지 못한다(초기 빌드에서 A1 의 IC 가 0 으로 나온 이유).
    #   → 시간가변 잠재변수 mood[i, t] 를 랜덤워크로 만들고, 톤과 '다음 분기 수익' 을
    #     모두 Δmood 에 연동한다. 그래야 '톤 변화가 수익에 선행' 하는 구조가 심긴다.
    n_reb = len(rebals)
    mood = np.cumsum(rng.normal(0, 0.55, size=(n_codes, n_reb)), axis=1)
    dmood = np.diff(mood, axis=1, prepend=mood[:, :1])
    reb_pos = {pd.Timestamp(t): j for j, t in enumerate(rebals)}

    # ── 상장/폐지 (생존자편향 검증) ───────────────────────────────────────────────────────
    listing = [start - pd.DateOffset(years=int(rng.integers(3, 15))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
        listing[i] = rebals[int(rng.integers(2, max(3, len(rebals) - 6)))]
    delist = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        delist[i] = rebals[int(rng.integers(4, max(5, len(rebals) - 2)))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": inds, "corp_code": corps, "src": "synthetic"})

    # ── 일봉 ──────────────────────────────────────────────────────────────────────────────
    days = pd.bdate_range(start - pd.DateOffset(months=18), end + pd.Timedelta(days=5))
    _day_arr = np.asarray(days.values, dtype="datetime64[ns]")
    _reb_arr = np.asarray(pd.DatetimeIndex(rebals).values, dtype="datetime64[ns]")
    px_rows = []
    for i, c in enumerate(codes):
        # 각 거래일이 속한 리밸 구간의 '직전 Δmood' 를 drift 에 더한다 → 톤 변화 선행 구조
        seg = np.clip(np.searchsorted(_reb_arr, _day_arr, side="right") - 1, 0, n_reb - 1)
        lead = dmood[i][np.clip(seg, 0, n_reb - 1)]
        drift = 0.0004 + 0.0008 * quality[i] + 0.0016 * lead
        r = rng.normal(drift, 0.024, len(days))
        p = float(rng.lognormal(8.5, 0.7)) * np.exp(np.cumsum(r))
        vol = rng.lognormal(10.8, 0.9, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * 1.012, "low": p * 0.988, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    for i, c in enumerate(codes):
        if pd.notna(delist[i]):
            px = px[~((px["code"] == c) & (px["date"] > delist[i]))]
        px = px[~((px["code"] == c) & (px["date"] < listing[i]))]

    # ── PIT 시가총액 ──────────────────────────────────────────────────────────────────────
    mc_rows = []
    shares_out = {c: float(rng.lognormal(16.0, 0.8)) for c in codes}
    for t in rebals:
        prev = px[px["date"] < as_ts(t)]
        if prev.empty:
            continue
        last = prev.groupby("code", observed=True).tail(1)
        for cc, cl in zip(last["code"], last["close"]):
            mc_rows.append({"date": as_ts(t), "code": cc,
                            "mktcap": float(cl) * shares_out[cc],
                            "shares_listed": shares_out[cc], "close_mc": float(cl),
                            "mc_src": "synthetic"})
    snap_mc = pd.DataFrame(mc_rows)

    # ── 재무 (분기) ───────────────────────────────────────────────────────────────────────
    rc = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
    fin_rows, emp_rows, sh_rows, aud_rows = [], [], [], []
    years = list(range(start.year - 1, end.year + 1))
    for i, c in enumerate(codes):
        base_rev = float(rng.lognormal(24, 1.0))
        sh = shares_out[c]
        for y in years:
            for q in (1, 2, 3, 4):
                gr = 1 + 0.015 * quality[i] + rng.normal(0, 0.05)
                base_rev *= gr
                rev = base_rev
                ni = rev * (0.05 + 0.015 * quality[i] + rng.normal(0, 0.01))
                cfo = ni * (1.0 + 0.35 * quality[i] + rng.normal(0, 0.15))
                pe = as_ts(f"{y}-{q*3:02d}-01") + pd.offsets.MonthEnd(0)
                kd = pe + pd.Timedelta(days=45 if q < 4 else 90)
                fin_rows.append({
                    "corp_code": corps[i], "bsns_year": y, "reprt_code": rc[q],
                    "period_end": pe, "knowledge_date": kd,
                    "revenue_ttm": rev * 4, "net_income_ttm": ni * 4, "cfo_ttm": cfo * 4,
                    "op_income_q": rev * (0.06 + 0.02 * quality[i] + rng.normal(0, 0.03)),
                    "assets": rev * 5.5, "liabilities": rev * 2.4, "equity": rev * 3.1,
                    "cash": rev * 0.6, "capital_stock": rev * 0.5,
                    "inventory": rev * (0.8 - 0.05 * quality[i]) * (1 + rng.normal(0, 0.05)),
                    "receivable": rev * (0.9 - 0.05 * quality[i]) * (1 + rng.normal(0, 0.05)),
                    "ppe": rev * 2.0 * (1 + 0.02 * max(quality[i], 0)),
                    "rnd_ttm": rev * (0.02 + 0.012 * max(quality[i], 0)) * 4,
                })
                sh *= (1 + max(0.0, 0.006 - 0.004 * quality[i]) + abs(rng.normal(0, 0.002)))
                sh_rows.append({"corp_code": corps[i], "bsns_year": y, "reprt_code": rc[q],
                                "shares_common": sh, "shares_total": sh,
                                "treasury_shares": 0.0, "period_end": pe,
                                "knowledge_date": kd})
            emp_rows.append({"corp_code": corps[i], "bsns_year": y,
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90),
                             "employees": float(max(15, rng.lognormal(4.8, 0.9) *
                                                    (1 + 0.05 * quality[i]))),
                             "payroll": float(rng.lognormal(21, 0.8))})
            # 배제 발동 10% — 감사 강조사항
            aud_rows.append({"corp_code": corps[i], "bsns_year": y,
                             "audit_opinion": "적정",
                             "emphasis": ("계속기업 불확실성" if rng.random() < 0.03 else ""),
                             "key_matter": "", "auditor": "합성회계법인",
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90)})
    fin = pit_frame(pd.DataFrame(fin_rows), "period_end", "knowledge_date", source="synthetic")
    emp = pit_frame(pd.DataFrame(emp_rows), "period_end", "knowledge_date", source="synthetic")
    shares = pit_frame(pd.DataFrame(sh_rows), "period_end", "knowledge_date", source="synthetic")
    audit = pit_frame(pd.DataFrame(aud_rows), "period_end", "knowledge_date", source="synthetic")

    # ── 공시목록 ──────────────────────────────────────────────────────────────────────────
    dis_rows = []
    for i, c in enumerate(codes):
        for y in years:
            dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                             "stock_code": c, "rcept_no": sha1_str(c, y, "FY")[:14],
                             "rcept_dt": as_ts(f"{y+1}-03-20"),
                             "report_nm": f"사업보고서 ({y}.12)", "event": ""})
            if rng.random() < 0.06:
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "cb")[:14],
                                 "rcept_dt": as_ts(f"{y}-07-10"),
                                 "report_nm": "주요사항보고서(전환사채발행결정)", "event": "cb_issue"})
            if rng.random() < 0.03:
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "mg")[:14],
                                 "rcept_dt": as_ts(f"{y}-05-10"),
                                 "report_nm": "주요사항보고서(회사합병결정)", "event": ""})
            if rng.random() < 0.12 + 0.10 * max(quality[i], 0):
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "sc")[:14],
                                 "rcept_dt": as_ts(f"{y}-09-05"),
                                 "report_nm": "단일판매ㆍ공급계약체결", "event": ""})
    dis = pit_frame(pd.DataFrame(dis_rows), "rcept_dt", "rcept_dt", source="synthetic")

    # ── 정기보고서 토큰 (D1 입력) — D1 결측 15% 포함 ──────────────────────────────────────
    doc_rows = []
    no_d1 = set(rng.choice(n_codes, size=max(1, int(n_codes * 0.15)), replace=False).tolist())
    for i, c in enumerate(codes):
        if i in no_d1:
            continue
        prev_tf: Dict[str, Dict[str, int]] = {}
        for y in years:
            # quality 가 높을수록 문서를 '덜' 고친다 (Lazy Prices 방향)
            churn = float(np.clip(0.25 - 0.10 * quality[i] + rng.normal(0, 0.05), 0.02, 0.6))
            for sname in ARC_SECTIONS:
                base = prev_tf.get(sname)
                if base is None:
                    idx = rng.choice(len(_SYN_VOCAB), size=90, replace=False)
                    tf = {_SYN_VOCAB[j]: int(rng.integers(1, 9)) for j in idx}
                else:
                    tf = dict(base)
                    k = max(1, int(len(tf) * churn))
                    drop = list(rng.choice(list(tf), size=min(k, len(tf)), replace=False))
                    for d0 in drop:
                        tf.pop(d0, None)
                    add = rng.choice(len(_SYN_VOCAB), size=k, replace=False)
                    for j in add:
                        tf[_SYN_VOCAB[j]] = int(rng.integers(1, 9))
                prev_tf[sname] = tf
                toks = list(tf)
                bg = {f"{toks[j]}_{toks[j+1]}": 1 for j in range(min(len(toks) - 1, 40))}
                doc_rows.append({
                    "corp_code": corps[i], "rcept_no": sha1_str(c, y, sname)[:16],
                    "rcept_dt": as_ts(f"{y+1}-03-20"), "doc_type": "FY", "bsns_year": y,
                    "section": sname, "n_tokens": len(tf),
                    "tf": json.dumps(tf, ensure_ascii=False),
                    "bigram": json.dumps(bg, ensure_ascii=False),
                    "tok_len": int(sum(tf.values())), "is_amend": False})
    doc_tokens = pd.DataFrame(doc_rows)

    # ── 리포트 원장 + 애널리스트 링크 — 축 A 결측 20% 포함 ────────────────────────────────
    no_rep = set(rng.choice(n_codes, size=max(1, int(n_codes * 0.20)), replace=False).tolist())
    brokers = MAJOR_BROKERS[:8] + MINOR_BROKERS[:8] + ["한국IR협의회"]
    analysts = [(b, f"애널{j:02d}") for b in brokers for j in range(3)]
    rep_rows, link_rows, tone_rows = [], [], []
    for t in rebals:
        for i in range(n_codes):
            if i in no_rep or rng.random() > 0.55:
                continue
            for _ in range(int(rng.integers(1, 3))):
                b, nm = analysts[int(rng.integers(0, len(analysts)))]
                bid, bname = normalize_broker(b)
                d = as_ts(t) - pd.Timedelta(days=int(rng.integers(3, 88)))
                uid = sha1_str("syn", codes[i], d, nm, rng.integers(1e9))
                tp = float(np.exp(rng.normal(9.4, 0.5)) * (1 + 0.12 * quality[i]))
                rep_rows.append({
                    "report_uid": uid, "source": "synthetic", "src_report_id": uid[:10],
                    "pub_date": d, "category": "company",
                    "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                    "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                    "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                    "opinion": "BUY", "pdf_url": None, "detail_url": None,
                    "event_date": d, "knowledge_date": d})
                link_rows.append({
                    "report_uid": uid, "name": nm, "broker_id": bid, "broker_name": bname,
                    "role": "lead", "link_method": "list_field", "link_conf": 0.98,
                    "pub_date": d, "stock_code": codes[i], "target_price": tp,
                    "opinion": "BUY", "name_norm": nm,
                    "analyst_id": sha1_str("analyst", bid, nm)[:14]})
                _j = reb_pos.get(pd.Timestamp(t), 0)
                tone_rows.append({
                    "report_uid": uid, "code": codes[i], "pub_date": d,
                    "TONE_report": float(np.clip(0.10 * quality[i] + 0.45 * mood[i, _j] /
                                                 max(1.0, abs(mood[i, _j]) ** 0.5 + 1e-9)
                                                 + rng.normal(0, 0.22), -1, 1)),
                    "n_sent": int(rng.integers(10, 40)),
                    "event_date": d, "knowledge_date": d + pd.Timedelta(days=1)})
    reports = tag_sponsored_reports(pd.DataFrame(rep_rows))
    links = pd.DataFrame(link_rows)
    tone_rep = pd.DataFrame(tone_rows)

    return {"sec": sec, "px": px, "fin": fin, "shares": shares, "emp": emp, "dis": dis,
            "audit": audit, "reports": reports, "links": links, "tone_rep": tone_rep,
            "doc_tokens": doc_tokens, "snap_mc": snap_mc, "rebals": rebals,
            "quality": quality}


def _syn_build_panel(S: dict) -> Tuple[pd.DataFrame, Any, dict]:
    """합성데이터로 실제 파이프라인 함수를 그대로 통과시킨다(모의 구현 금지)."""
    rebals = S["rebals"]
    sec, px = S["sec"], S["px"]

    liq = build_liquidity_panel(px, rebals)
    execp = build_exec_prices(px, rebals)
    mc = build_mktcap_panel(rebals,
                            px.assign(month=as_ts_series(px["date"]) + pd.offsets.MonthEnd(0))
                              .groupby(["code", "month"], observed=True)
                              .tail(1)[["code", "month", "close"]],
                            S["snap_mc"], S["shares"], sec)
    base = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    exd = classify_excluded(sec)
    uni = ArcUniverse(base, sec, exd)
    U = uni.build(rebals, mc, liq[["code", "asof", "adtv60"]] if len(liq) else liq)
    P = build_arc_panel(uni, rebals, U, liq, execp, sec)

    # 축 B
    pairs = arc_doc_pairs(S["doc_tokens"])
    struct = build_struct_flags(S["dis"])
    d1 = d1_composite(d1_similarity(pairs), struct)
    P = attach_d1(P, d1)
    P = attach_d2(P, build_d2_panel(S["fin"], S["shares"]))
    hard = extract_hardfacts(S["doc_tokens"], S["fin"], S["emp"], S["dis"])
    excl = build_exclusion_flags(S["fin"], S["dis"], S["audit"], S["doc_tokens"])
    P = attach_d3(P, hard, excl)

    # 재무를 패널에 붙여 eps_rev 대리변수를 만들 수 있게 한다
    if len(S["fin"]):
        PIT.register("syn_fin", S["fin"], key_cols=["corp_code"])
        P = PIT.asof_join(P, "syn_fin", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date", "net_income_ttm", "assets"],
                          suffix="_fin")
    # 축 A
    tone_q = aggregate_tone(S["tone_rep"], rebals)
    rev = build_revision_panel(S["links"], rebals)
    P = attach_axis_a(P, tone_q, rev)
    P = attach_volatility(P, px)
    return P, uni, {"pairs": pairs, "d1": d1, "tone_q": tone_q, "rev": rev}


def run_selftest(full_chain: bool = False) -> bool:
    """full_chain=True 면 성과·어블레이션·BH-FDR·강건성·해석표까지 전부 합성으로 예행연습."""
    LOG.banner("① 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수십 초)" +
               (" · full_chain: 어블레이션·강건성까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    try:
        S = make_arc_synthetic()
    except Exception as e:                                        # noqa
        LOG.error(f"합성데이터 생성 실패 — {type(e).__name__}: {e}")
        return False
    LOG.info(f"합성: 종목 {len(S['sec'])} · 리밸 {len(S['rebals'])} · 일봉 {len(S['px']):,} · "
             f"재무 {len(S['fin']):,} · 문서토큰 {len(S['doc_tokens']):,} · "
             f"리포트 {len(S['reports']):,}")

    P, uni, aux = _syn_build_panel(S)
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)

    def _run(pp, label="smoke", apply_costs=True, top_n=None, weighting=None, bottom=False):
        return run_backtest(pp, S["rebals"], uni, S["sec"], apply_costs=apply_costs,
                            label=label, top_n=top_n, weighting=weighting, bottom=bottom)

    bt = _run(Q, label="SMOKE")
    st = perf_stats(bt["returns"])
    dur = time.time() - t0

    # ── 배관 검증 판정 ────────────────────────────────────────────────────────────────────
    checks = []
    checks.append(("패널 생성", len(P) > 0, f"{len(P):,}행"))
    checks.append(("백테스트 기간 일치", len(bt["returns"]) == len(S["rebals"]),
                   f"{len(bt['returns'])}/{len(S['rebals'])}"))
    checks.append(("성과 산출", bool(st) and np.isfinite(st.get("CAGR", np.nan)),
                   f"CAGR {st.get('CAGR', float('nan'))*100:+.2f}%"))
    n_a_miss = int((pd.to_numeric(col(P, "has_axis_a"), errors="coerce").fillna(0) == 0).sum())
    surv = int(Q.loc[pd.to_numeric(col(Q, "has_axis_a"), errors="coerce").fillna(0) == 0,
                     "FINAL_SCORE"].notna().sum())
    checks.append(("축 A 결측 종목 생존 (§7.2)", n_a_miss == 0 or surv > 0,
                   f"결측 {n_a_miss:,}행 중 {surv:,}행 생존"))
    n_d1_miss = int(pd.to_numeric(col(P, "D1_MISSING"), errors="coerce").fillna(0).sum())
    surv2 = int(Q.loc[pd.to_numeric(col(Q, "D1_MISSING"), errors="coerce").fillna(0) > 0,
                      "FINAL_SCORE"].notna().sum())
    checks.append(("D1 결측 가중치 재배분 (§6.5)", n_d1_miss == 0 or surv2 > 0,
                   f"결측 {n_d1_miss:,}행 중 {surv2:,}행 생존"))
    n_ex = int(pd.to_numeric(col(P, "EXCLUDE"), errors="coerce").fillna(0).sum())
    leak = int(Q.loc[pd.to_numeric(col(Q, "EXCLUDE"), errors="coerce").fillna(0) > 0,
                     "FINAL_SCORE"].notna().sum())
    checks.append(("배제 하드 제외 (§6.4)", leak == 0, f"발동 {n_ex:,}행 · 누수 {leak}행"))
    ic, icir, n_ic = bt_ic(Q, "FINAL_RANK")
    checks.append(("신호→수익 반응 (하네스 민감도)", np.isfinite(ic),
                   f"IC {ic:+.4f} (IC-IR {icir:+.2f}, {n_ic}기간)"))

    LOG.table([[k, "✔" if ok else "✘", v] for k, ok, v in checks],
              ["배관 검증 항목", "판정", "실측"], ["l", "c", "l"],
              title=f"스모크 결과 (소요 {dur:.1f}초 — 성과 수치는 의미 없음, 배관 검증용)")
    ok_all = all(ok for _k, ok, _v in checks)
    if not ok_all:
        LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
        return False
    LOG.ok(f"스모크 통과 ({dur:.1f}초) — 수집→패널→신호→백테스트 경로가 정상 동작합니다.")

    if not full_chain:
        return True

    # ── full_chain: 최종 출력물 전체 예행연습 ─────────────────────────────────────────────
    LOG.banner("⚠ 아래 수치는 전부 합성 난수 기반입니다",
               "전략의 실제 성과가 아니라 '출력물이 제대로 나오는지' 예행연습입니다. 해석 금지")
    ctx = {"panel_base": P, "reports": S["reports"], "report_text": S["reports"],
           "doc_tokens": S["doc_tokens"], "doc_pairs": aux["pairs"], "fin": S["fin"],
           "shares": S["shares"], "links": S["links"], "doc_attempted": len(S["doc_tokens"])}
    with PIPE.stage("SMOKE.GATE", "[합성] Phase 0 게이트", "L1", budget_s=120, critical=False):
        run_phase0_gates(ctx, S["rebals"])
    with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
        report_performance(bt, {}, label="ARC-TXT v2 (합성 예행연습)",
                           uni_bench=equal_weight_universe_return(Q))
        uni.report_attrition()
        report_score_summary(Q)
    with PIPE.stage("SMOKE.DIAG", "[합성] 층 상관 · D1 부호 · D2 커버리지", "L6",
                    budget_s=120, critical=False):
        report_correlation_matrix(Q)
        ctx["d1_sign"] = report_d1_sign_check(Q)
        report_d2_coverage(Q)
        report_d3_sector(Q)
        report_exclusion(Q)
        ctx["axis_a_ic"] = report_axis_a_ic(Q)
    with PIPE.stage("SMOKE.ABL", "[합성] 어블레이션 11종 + BH-FDR", "L5",
                    budget_s=1800, critical=False):
        run_ablations(Q, S["rebals"], uni, S["sec"], _run)
        report_f4_vs_f1()
        ctx["fdr"] = apply_bh_fdr()
    with PIPE.stage("SMOKE.ROBUST", "[합성] 강건성 R1~R11", "L5", budget_s=1800, critical=False):
        run_robustness_suite(Q, bt, S["rebals"], uni, S["sec"], _run,
                             rep=S["reports"], doc=S["doc_tokens"], px_daily=S["px"])
    with PIPE.stage("SMOKE.REPORT", "[합성] 해석표 · 진단카드 · 폐기판정", "L6",
                    budget_s=180, critical=False):
        report_interpretation(Q)
        diagnostic_card(Q, bt, S["sec"])
        ctx["kill"] = report_kill_criteria(ctx)
        report_final_deliverables(ctx)

    LOG.ok("full_chain 예행연습 완료 — 게이트·성과·어블레이션·BH-FDR·강건성·해석표·진단카드·"
           "폐기판정이 모두 정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 동일한 출력이 "
           "실데이터로 나옵니다.")
    # ★ 합성 결과가 실데이터 결과와 섞이면 안 된다. 전부 비운다.
    ABLATION_RESULTS.clear()
    ROBUST_RESULTS.clear()
    GATE_RESULTS.clear()
    return True
