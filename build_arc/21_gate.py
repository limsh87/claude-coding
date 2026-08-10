
# ────────────────────────────────────────────────────────────────────────────────────────
#  L1-H  Phase 0 — 데이터 실현가능성 게이트 (§2)
#  ★ 어떤 경우에도 예외를 던지지 않는다. 판정만 하고 돌려준다.
#  이 게이트의 목적은 '전략을 통과시키는 것'이 아니라 **어느 축이 성립 가능한지 먼저
# ────────────────────────────────────────────────────────────────────────────────────────

ARC_GATES = [
    ("GATE_1", "median(pair_count(q)) ≥ 150", "축 A 최소 표본 (분기 중앙값)"),
    ("GATE_2", "min(pair_count(q)) ≥ 80",     "최악 분기"),
    ("GATE_3", "text_extract_rate ≥ 0.70",    "리포트 본문 추출 성공률"),
    ("GATE_4", "dart_pair_rate ≥ 0.85",       "전년 동기 페어링 가능 비율 (D1 필수)"),
    ("GATE_5", "dart_parse_rate ≥ 0.80",      "정기보고서 기계판독 성공률"),
    ("GATE_6", "fs_cov ≥ 0.90",               "D2 산출 필요 재무항목 가용률"),
]
GATE_THRESHOLDS = {"GATE_1": 150.0, "GATE_2": 80.0, "GATE_3": 0.70,
                   "GATE_4": 0.85, "GATE_5": 0.80, "GATE_6": 0.90}
GATE_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

def _grec(gid: str, value, passed: Optional[bool], detail: str):
    GATE_RESULTS[gid] = {"id": gid, "value": value, "pass": passed, "detail": detail}

def _gate_pair_counts(rep: pd.DataFrame, uni_codes: Optional[set] = None) -> pd.Series:
    """분기 q 와 q−1 '양쪽 모두' 리포트 ≥1건인 종목 수 (§2.1 pair_count).

    ★ ΔTONE 은 양 분기 모두 리포트가 있어야 성립한다(§5.3). 그래서 커버리지가 아니라
      '페어 수'가 축 A 의 실질 표본이며, 이 값이 축 A 생존 여부를 결정한다.
    """
    if rep is None or rep.empty:
        return pd.Series(dtype=int)
    r = rep.dropna(subset=["stock_code"]).copy()
    r["pub_date"] = as_ts_series(r["pub_date"])
    r = r.dropna(subset=["pub_date"])
    if uni_codes:
        r = r[r["stock_code"].astype(str).isin(uni_codes)]
    if r.empty:
        return pd.Series(dtype=int)
    r["q"] = [qlabel(t) for t in r["pub_date"]]
    have = r.groupby("q")["stock_code"].apply(lambda s: set(s.astype(str)))
    qs = sorted(have.index)
    out = {}
    for i in range(1, len(qs)):
        prev, cur = qs[i - 1], qs[i]
        if qshift(cur, -1) != prev:
            continue                       # 분기가 끊긴 구간은 페어가 아니다
        out[cur] = len(have[cur] & have[prev])
    return pd.Series(out, dtype=int).sort_index()

def _gate_fs_cov(fin: pd.DataFrame, shares: Optional[pd.DataFrame]) -> Tuple[float, dict]:
    """D2 6개 지표 산출에 필요한 재무항목의 (법인×분기) 가용률."""
    need = ["net_income_ttm", "cfo_ttm", "assets", "liabilities", "cash",
            "receivable", "inventory", "revenue_ttm"]
    if fin is None or fin.empty:
        return (0.0, {c: 0.0 for c in need + ["shares_total"]})
    det = {}
    for c in need:
        v = col(fin, c)
        det[c] = float(v.notna().mean()) if len(fin) else 0.0
    if shares is not None and len(shares):
        det["shares_total"] = float(pd.to_numeric(shares.get("shares_total"),
                                                  errors="coerce").notna().mean())
    else:
        det["shares_total"] = 0.0
    # fs_cov = '핵심 항목이 모두 있는' 행 비율 (지표별 평균이 아니라 동시 가용성)
    ok = pd.Series(True, index=fin.index)
    for c in need:
        ok &= col(fin, c).notna()
    return (float(ok.mean()) if len(fin) else 0.0, det)

def run_phase0_gates(ctx: dict, rebals: pd.DatetimeIndex) -> dict:
    """§2 게이트 6종 실측 + 판정. 예외를 던지지 않는다."""
    GATE_RESULTS.clear()
    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§2)",
               "어느 축이 성립 가능한지 먼저 확정한다. 실패해도 전략을 폐기하지 않고 축만 끈다")

    rep = ctx.get("reports")
    rep_text = ctx.get("report_text")
    T = ctx.get("doc_tokens")
    pairs = ctx.get("doc_pairs")
    fin = ctx.get("fin")
    shares = ctx.get("shares")
    links = ctx.get("links")
    P0 = ctx.get("panel_base")

    uni_codes = set(P0["code"].astype(str)) if P0 is not None and len(P0) else None
    metrics: Dict[str, Any] = {}

    # ── GATE_1 / GATE_2 : pair_count ─────────────────────────────────────────────────────
    pc = _gate_pair_counts(rep, uni_codes)
    if len(pc) == 0:
        _grec("GATE_1", np.nan, None, "리포트 원장이 비어 pair_count 를 셀 수 없습니다.")
        _grec("GATE_2", np.nan, None, "동일")
    else:
        recent = pc.tail(12)               # §2.1 '최근 12분기'
        med, mn = float(recent.median()), float(recent.min())
        metrics["pair_count_median"] = med
        metrics["pair_count_min"] = mn
        _grec("GATE_1", med, bool(med >= GATE_THRESHOLDS["GATE_1"]),
              f"최근 12분기 중앙값 {med:,.0f}종목 (기준 150)")
        _grec("GATE_2", mn, bool(mn >= GATE_THRESHOLDS["GATE_2"]),
              f"최악 분기 {mn:,.0f}종목 (기준 80)")

    # ── GATE_3 : 본문 추출률 ──────────────────────────────────────────────────────────────
    if rep is None or rep.empty:
        _grec("GATE_3", np.nan, None, "리포트 원장 없음")
    else:
        n_rep = int(len(rep))
        n_txt = int(len(rep_text)) if rep_text is not None else 0
        rate = n_txt / max(n_rep, 1)
        metrics["text_extract_rate"] = rate
        _grec("GATE_3", rate, bool(rate >= GATE_THRESHOLDS["GATE_3"]),
              f"본문 확보 {n_txt:,} / 원장 {n_rep:,} = {100*rate:.1f}% (기준 70%)")

    # ── GATE_4 : DART 페어링 가능 비율 ────────────────────────────────────────────────────
    if T is None or len(T) == 0:
        _grec("GATE_4", np.nan, None, "정기보고서 토큰 없음 — D1 구동 불가")
    else:
        docs = T[["corp_code", "doc_type", "bsns_year"]].drop_duplicates()
        n_doc = len(docs)
        n_pair = (pairs[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
                  if pairs is not None and len(pairs) else 0)
        rate = n_pair / max(n_doc, 1)
        metrics["dart_pair_rate"] = rate
        _grec("GATE_4", rate, bool(rate >= GATE_THRESHOLDS["GATE_4"]),
              f"페어 가능 {n_pair:,} / 문서 {n_doc:,} = {100*rate:.1f}% (기준 85%)")

    # ── GATE_5 : 기계판독 성공률 ──────────────────────────────────────────────────────────
    fail = int(sum(_ARC_DOC_FAIL.values())) if "_ARC_DOC_FAIL" in globals() else 0
    n_doc_ok = int(T["rcept_no"].nunique()) if T is not None and len(T) else 0
    tried = ctx.get("doc_attempted", n_doc_ok + fail)
    if tried <= 0:
        _grec("GATE_5", np.nan, None, "이번 실행에서 새로 시도한 원문이 없습니다 "
                                      "(전량 캐시 재사용이면 정상).")
    else:
        rate = n_doc_ok / max(tried, 1)
        metrics["dart_parse_rate"] = rate
        _grec("GATE_5", rate, bool(rate >= GATE_THRESHOLDS["GATE_5"]),
              f"판독 성공 {n_doc_ok:,} / 시도 {tried:,} = {100*rate:.1f}% (기준 80%)")

    # ── GATE_6 : 재무항목 가용률 ──────────────────────────────────────────────────────────
    cov, det = _gate_fs_cov(fin, shares)
    metrics["fs_cov"] = cov
    metrics["fs_cov_detail"] = det
    if fin is None or fin.empty:
        _grec("GATE_6", 0.0, False, "재무 데이터 없음 — D2 구동 불가 (심각)")
    else:
        _grec("GATE_6", cov, bool(cov >= GATE_THRESHOLDS["GATE_6"]),
              f"D2 필수항목 동시 가용 {100*cov:.1f}% (기준 90%)")

    # ── 판정표 ────────────────────────────────────────────────────────────────────────────
    rows = []
    for gid, cond, why in ARC_GATES:
        r = GATE_RESULTS.get(gid, {})
        v = r.get("value")
        p = r.get("pass")
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[p]
        vs = ("—" if v is None or (isinstance(v, float) and not np.isfinite(v))
              else (f"{v:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*float(v):.1f}%"))
        rows.append([gid, cond, why, vs, icon, _trunc(r.get("detail", ""), 46)])
    LOG.table(rows, ["게이트", "조건", "의미", "실측", "판정", "상세"],
              ["l", "l", "l", "r", "c", "l"], maxw=48)

    # ── 분기별 추이 표 ────────────────────────────────────────────────────────────────────
    if len(pc):
        cov_q = {}
        if rep is not None and len(rep) and uni_codes:
            r = rep.dropna(subset=["stock_code"]).copy()
            r["pub_date"] = as_ts_series(r["pub_date"])
            r = r.dropna(subset=["pub_date"])
            r["q"] = [qlabel(t) for t in r["pub_date"]]
            r = r[r["stock_code"].astype(str).isin(uni_codes)]
            n_uni = max(len(uni_codes), 1)
            cov_q = (r.groupby("q")["stock_code"].nunique() / n_uni).to_dict()
        tail = pc.tail(16)
        LOG.table([[q, f"{int(n):,}", f"{100*cov_q.get(q, float('nan')):.1f}%"
                    if q in cov_q else "—"] for q, n in tail.items()],
                  ["분기", "pair_count", "cov_rate"], ["c", "r", "r"],
                  title="분기별 축 A 표본 추이 (최근 16분기)")

    # ── report_dist 히스토그램 ────────────────────────────────────────────────────────────
    if rep is not None and len(rep):
        r = rep.dropna(subset=["stock_code"]).copy()
        r["pub_date"] = as_ts_series(r["pub_date"])
        r = r.dropna(subset=["pub_date"])
        r["q"] = [qlabel(t) for t in r["pub_date"]]
        cnt = r.groupby(["q", "stock_code"]).size()
        if uni_codes:
            allq = sorted(set(r["q"]))
            n_zero = sum(max(0, len(uni_codes) - cnt.loc[q].shape[0]) for q in allq
                         if q in cnt.index.get_level_values(0))
        else:
            n_zero = 0
        bins = {"0건": n_zero, "1건": int((cnt == 1).sum()), "2건": int((cnt == 2).sum()),
                "3건": int((cnt == 3).sum()), "4건": int((cnt == 4).sum()),
                "5건+": int((cnt >= 5).sum())}
        tot = max(sum(bins.values()), 1)
        LOG.table([[k, f"{v:,}", f"{100*v/tot:.1f}%"] for k, v in bins.items()],
                  ["종목-분기 리포트 건수", "빈도", "비중"], ["l", "r", "r"],
                  title="report_dist — 커버리지 희소성 (0건이 지배적이면 축 A 는 소수 종목만 커버)")

    # ── analyst_id_rate ───────────────────────────────────────────────────────────────────
    if rep is not None and len(rep):
        linked = set(links["report_uid"].astype(str)) if links is not None and len(links) else set()
        rate = (float(rep["report_uid"].astype(str).isin(linked).mean()) if linked else 0.0)
        metrics["analyst_id_rate"] = rate
        LOG.info(f"analyst_id@broker_id 추출 성공률 {100*rate:.1f}% (측정 항목 — 게이트 아님). "
                 f"낮으면 직교화 통제변수(목표주가 수정률)의 신뢰도가 떨어집니다.")

    # ── §2.3 실패 시 행동 ─────────────────────────────────────────────────────────────────
    def _p(gid):
        return GATE_RESULTS.get(gid, {}).get("pass")

    axis_a = not (_p("GATE_1") is False or _p("GATE_2") is False or _p("GATE_3") is False)
    if _p("GATE_1") is None and _p("GATE_3") is None:
        axis_a = False
    d1 = not (_p("GATE_4") is False or _p("GATE_5") is False)
    if _p("GATE_4") is None and (T is None or len(T) == 0):
        d1 = False
    d2 = _p("GATE_6") is not False

    mode = "FULL (축 A + 축 B)"
    if not axis_a:
        mode = "DART-ONLY 폴백 (축 A 비활성화)"
        LOG.banner("⚠ 축 A 비활성화 — 전략명을 'DART-ONLY 폴백' 으로 보고합니다 (§2.3)",
                   "GATE_1/2/3 중 하나 이상 실패. v2.0 은 축 B 가 독립 작동하므로 전략을 "
                   "폐기하지 않습니다")
    if not d1:
        LOG.banner("⚠ D1 비활성화 (§2.3)", "사유를 아래 표로 분해합니다")
        _gate_d1_failure_breakdown(T, pairs, ctx)
    if not d2:
        LOG.banner("⛔ D2 비활성화 — 심각 이슈 (§2.3)",
                   "D2 는 D1 보다 대체 불가합니다. 재무 수집 상태를 먼저 해결해야 합니다")

    fails = [g for g in ("GATE_4", "GATE_5", "GATE_6") if _p(g) is False]
    if len(fails) == 3:
        LOG.error("§9.3-1 폐기 조건: GATE_4·5·6 이 모두 실패 → 축 B 성립 불가. "
                  "이 경우 전략 폐기가 사전등록된 판정입니다.")

    LOG.table([["축 A (애널리스트 텍스트톤)", "활성" if axis_a else "비활성"],
               ["축 B D1 (텍스트 변화량)", "활성" if d1 else "비활성"],
               ["축 B D2 (재무 이상현상)", "활성" if d2 else "비활성"],
               ["축 B D3 (하드팩트)", "활성 (가점)"],
               ["배제 플래그", "활성 (하드 제외)"],
               ["실행 모드", mode]],
              ["구성", "상태"], ["l", "l"], title="Phase 0 확정 — 이 구성으로 이후 단계가 진행됩니다")

    return {"axis_a": bool(axis_a), "d1": bool(d1), "d2": bool(d2),
            "mode": mode, "metrics": metrics}

def _gate_d1_failure_breakdown(T, pairs, ctx):
    """GATE_4/5 실패 사유 분해 — PDF 스캔본 / 서식변경 / 전년동기 부재 / 기타."""
    rows = []
    fails = dict(_ARC_DOC_FAIL) if "_ARC_DOC_FAIL" in globals() else {}
    for k, v in sorted(fails.items(), key=lambda x: -x[1]):
        why = {
            "ZIP아님(스캔본/오류)": "구형 공시의 PDF 스캔본 — 기계판독 불가 (§0.4 알려진 함정)",
            "본문없음": "zip 은 받았으나 텍스트 엔트리가 비어 있음",
            "섹션0개": "목차 표제를 못 찾음 — 서식 개정으로 표제어가 바뀌었을 가능성",
            "토큰부족": "섹션은 찾았으나 토큰이 최소치 미만",
            "호출한도": "DART 일일 호출 예산 소진 — 내일 이어받으면 해소",
            "응답없음/과소": "네트워크 실패 또는 빈 응답",
        }.get(k, "기타")
        rows.append([k, f"{v:,}", why])
    if T is not None and len(T) and pairs is not None:
        n_doc = T[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
        n_pair = (pairs[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
                  if len(pairs) else 0)
        rows.append(["전년동기 부재", f"{max(0, n_doc - n_pair):,}",
                     "상장 24개월 미만이거나 전년 문서 수집이 아직 안 된 경우"])
    if not rows:
        rows = [["(분해 불가)", "—", "이번 실행에서 신규 수집이 없어 실패 원장이 비었습니다"]]
    LOG.table(rows, ["사유", "건수", "설명"], ["l", "r", "l"], maxw=64,
              title="D1 비활성화 사유 분해 (§2.3)")
    LOG.info("조치 우선순위: ① DART 예산 소진이면 내일 재실행(이어받기) "
             "② 섹션0개가 많으면 ARC_SECTION_PAT 표제어 정규식 점검 "
             "③ 스캔본이 많으면 그 구간은 구조적으로 D1 결측 — 정상입니다.")

def report_gate_table() -> None:
    """§9.2-(1) 최종 산출물용 재출력."""
    if not GATE_RESULTS:
        LOG.warn("Phase 0 게이트가 실행되지 않았습니다.")
        return
    LOG.banner("[산출물 1] Phase 0 게이트 결과표 (§9.2-1)", "6개 게이트 실측치 + 통과/실패")
    rows = []
    for gid, cond, why in ARC_GATES:
        r = GATE_RESULTS.get(gid, {})
        v, p = r.get("value"), r.get("pass")
        vs = ("—" if v is None or (isinstance(v, float) and not np.isfinite(v))
              else (f"{v:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*float(v):.1f}%"))
        thr = GATE_THRESHOLDS[gid]
        ts = f"{thr:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*thr:.0f}%"
        rows.append([gid, cond, vs, ts,
                     {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[p]])
    LOG.table(rows, ["게이트", "조건", "실측치", "기준", "판정"], ["l", "l", "r", "r", "c"])
