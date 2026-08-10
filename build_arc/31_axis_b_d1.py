

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B1  D1 — 텍스트 변화량 (Lazy Prices 방식) §6.1                                         ║
# ║                                                                                          ║
# ║  근거: Cohen·Malloy·Nguyen, "Lazy Prices", Journal of Finance 2020.                       ║
# ║  기업은 정기보고서를 기본적으로 전기 문서 복붙으로 작성한다. 따라서 '문서를 능동적으로       ║
# ║  고쳤다는 사실 자체'가 신호다.                                                             ║
# ║                                                                                          ║
# ║  ⚠ [방법론적 우려 — 반드시 유지]                                                           ║
# ║    이는 미국 10-K 결과다. 한국 사업보고서에 대한 직접 재현 증거는 확인된 바 없다.            ║
# ║    이 파일은 그것을 '검증해야 할 가설'로 취급하며, 성립을 전제하지 않는다.                   ║
# ║    부호 검증(report_d1_sign_check)이 그 판정을 담당하고, 역전이면 그대로 보고한다.           ║
# ║                                                                                          ║
# ║  ★ 부호를 사후에 뒤집어 성과를 맞추는 코드는 이 파일에 존재하지 않는다(§9.3-5).             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

D1_SECTION_WEIGHTS = dict(ARC_D1_WEIGHTS)       # 사전등록. 튜닝 금지(A13 계약검정이 감시).
D1_METRICS = tuple(ARC_D1_METRICS)

D1_SIM_COLS = ["corp_code", "rcept_dt", "bsns_year", "doc_type", "section",
               "cosine", "jaccard", "simple", "len_ratio"]
D1_VARIANT_COLS = (["D1_SCORE_equalw", "CHANGE_equalw"] +
                   [f"D1_SCORE_{m}" for m in ARC_D1_METRICS] +
                   [f"CHANGE_{m}" for m in ARC_D1_METRICS])
D1_OUT_COLS = (["corp_code", "event_date", "knowledge_date"] +
               [f"CH_{s}" for s in ARC_SECTIONS] +
               ["CHANGE_composite", "D1_SCORE", "STRUCT_FLAG", "n_sections"] +
               D1_VARIANT_COLS)


# ── 구조적 변화 (§6.1.6) ────────────────────────────────────────────────────────────────────
_STRUCT_PAT = (r"합병|분할|영업양수|영업양도|자산양수|자산양도|지주회사\s*(전환|설립)|"
               r"주식교환|주식이전|포괄적\s*교환|회사분할")


def build_struct_flags(dis: pd.DataFrame) -> pd.DataFrame:
    """§6.1.6 합병·분할·영업양수도·지주전환 → STRUCT_FLAG.

    ★ 이런 기업은 문서가 '기계적으로' 대폭 변한다. 신호가 아니라 노이즈다.
      기본 백테스트에서는 D1 을 결측 처리하고(0 이 아니다), 민감도 분석에서 포함/제외를 비교한다.
    """
    cols = ["corp_code", "event_date", "knowledge_date", "STRUCT_FLAG"]
    if dis is None or dis.empty or "report_nm" not in dis.columns:
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    hit = d["report_nm"].astype(str).str.contains(_STRUCT_PAT, regex=True, na=False)
    S = d.loc[hit, ["corp_code", "rcept_dt"]].dropna().drop_duplicates()
    if S.empty:
        LOG.info("구조적 변화(합병·분할·지주전환) 공시가 없습니다 — STRUCT_FLAG 전부 0.")
        return pd.DataFrame(columns=cols)
    S["STRUCT_FLAG"] = 1.0
    S = pit_frame(S, "rcept_dt", "rcept_dt", source="dart_struct")
    S = S.rename(columns={"rcept_dt": "_rd"})
    LOG.ok(f"구조적 변화 공시 {len(S):,}건 · {S['corp_code'].nunique():,}사 "
           f"(해당 종목-기간의 D1 은 결측 처리됩니다 — §6.1.6)")
    return S[[c for c in cols if c in S.columns]]


# ── 유사도 4종 (§6.1.4) ─────────────────────────────────────────────────────────────────────
def _d1_load(js: Any) -> Dict[str, float]:
    if not js or (isinstance(js, float) and not np.isfinite(js)):
        return {}
    if isinstance(js, dict):
        return {str(k): float(v) for k, v in js.items()}
    try:
        d = json.loads(js)
        return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def _d1_pair_metrics(cur: Dict[str, float], prev: Dict[str, float],
                     cur_bg: Dict[str, float], prev_bg: Dict[str, float],
                     idf: Dict[str, float], tok_len_c: float, tok_len_p: float) -> Tuple:
    """한 쌍의 4종 유사도. 벡터 전개 없이 dict 교집합만으로 계산한다(어휘가 수만 개라 밀집화 금지)."""
    # cosine: TF-IDF (unigram + bigram)
    a: Dict[str, float] = {}
    b: Dict[str, float] = {}
    for k, v in cur.items():
        a[k] = (1.0 + math.log(v)) * idf.get(k, 1.0)
    for k, v in cur_bg.items():
        a["#" + k] = (1.0 + math.log(v)) * idf.get("#" + k, 1.0)
    for k, v in prev.items():
        b[k] = (1.0 + math.log(v)) * idf.get(k, 1.0)
    for k, v in prev_bg.items():
        b["#" + k] = (1.0 + math.log(v)) * idf.get("#" + k, 1.0)
    if not a or not b:
        return (np.nan, np.nan, np.nan, np.nan)
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    num = 0.0
    for k, v in small.items():
        w = big.get(k)
        if w is not None:
            num += v * w
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    cos = float(num / (na * nb)) if na > 0 and nb > 0 else np.nan

    # jaccard: 토큰 집합
    sa, sb = set(cur), set(prev)
    inter = len(sa & sb)
    union = len(sa | sb)
    jac = float(inter / union) if union else np.nan

    # simple: 공통 토큰 수 / 두 문서 평균 토큰 종수
    avg = (len(sa) + len(sb)) / 2.0
    simple = float(inter / avg) if avg > 0 else np.nan

    # len_ratio: 분량 급변 탐지
    lc, lp = float(tok_len_c or 0), float(tok_len_p or 0)
    lr = float(min(lc, lp) / max(lc, lp)) if max(lc, lp) > 0 else np.nan
    return (cos, jac, simple, lr)


def d1_similarity(pairs: pd.DataFrame,
                  df_state: Optional[dict] = None) -> pd.DataFrame:
    """§6.1.4 4종 유사도 산출.

    ★ IDF 누수 방지: 전체 기간 문서로 IDF 를 만들면 '미래에 흔해질 단어'의 가중치가
      과거 계산에 들어간다. 그 자체가 미래누수다. 여기서는 rcept_dt 오름차순으로 문서빈도를
      누적하면서, 각 문서 계산 시점에는 '그때까지 관측된' df 만 쓴다(expanding IDF).
      초기 표본이 얇을 때는 smoothing 이 커져 IDF 가 1 에 수렴하므로 안전하다.
    """
    if pairs is None or pairs.empty:
        LOG.warn("페어가 없어 D1 유사도를 만들 수 없습니다.")
        return pd.DataFrame(columns=D1_SIM_COLS)

    P = pairs.copy()
    P["rcept_dt"] = as_ts_series(P["rcept_dt"])
    P = P.dropna(subset=["rcept_dt", "corp_code", "section"]).sort_values(
        ["rcept_dt", "corp_code", "section"], kind="stable").reset_index(drop=True)

    # ★ 확장 IDF 상태. 연도별 스트리밍 호출에서도 '그때까지 관측된 문서' 만 반영되도록
    #   호출자가 상태를 넘겨 이어갈 수 있게 한다(넘기지 않으면 호출 내에서만 누적).
    if df_state is None:
        df_state = {"df": Counter(), "n": 0}
    df_cnt: "Counter" = df_state.setdefault("df", Counter())
    n_docs = int(df_state.get("n", 0))
    out_rows: List[dict] = []
    t0 = time.time()

    # 같은 접수일 묶음 단위로 처리: 묶음 안에서는 동일 IDF 를 쓰고, 묶음이 끝난 뒤 df 를 갱신한다
    # (같은 날 제출된 문서끼리 서로의 df 를 참조하지 않게 — 미세하지만 누수 방향이다).
    for _, grp in tqdm(P.groupby(P["rcept_dt"].dt.to_period("M"), observed=True),
                       desc="D1 유사도", ncols=88, leave=False):
        idf: Dict[str, float] = {}
        if n_docs >= 50:
            ln = math.log(n_docs + 1.0)
            idf = {k: (ln - math.log(v + 1.0) + 1.0) for k, v in df_cnt.items() if v >= 2}
        add: "Counter" = Counter()
        for r in grp.itertuples(index=False):
            cur = _d1_load(getattr(r, "tf", None))
            prv = _d1_load(getattr(r, "prev_tf", None))
            cbg = _d1_load(getattr(r, "bigram", None))
            pbg = _d1_load(getattr(r, "prev_bigram", None))
            if not cur or not prv:
                continue
            cos, jac, sim, lr = _d1_pair_metrics(
                cur, prv, cbg, pbg, idf,
                getattr(r, "tok_len", np.nan), getattr(r, "prev_tok_len", np.nan))
            out_rows.append({
                "corp_code": r.corp_code, "rcept_dt": r.rcept_dt,
                "bsns_year": int(getattr(r, "bsns_year", 0) or 0),
                "doc_type": str(getattr(r, "doc_type", "")), "section": str(r.section),
                "cosine": cos, "jaccard": jac, "simple": sim, "len_ratio": lr})
            for k in cur:
                add[k] += 1
            for k in cbg:
                add["#" + k] += 1
            n_docs += 1
        df_cnt.update(add)
        df_state["n"] = n_docs

    if not out_rows:
        LOG.warn("유사도를 한 건도 계산하지 못했습니다 (토큰이 비었을 가능성).")
        return pd.DataFrame(columns=D1_SIM_COLS)
    S = pd.DataFrame(out_rows)
    LOG.ok(f"D1 유사도 {len(S):,}행 · 문서 {n_docs:,}건 · 소요 {time.time()-t0:.1f}초 "
           f"(cosine 평균 {S['cosine'].mean():.3f} · jaccard 평균 {S['jaccard'].mean():.3f})")
    if S["cosine"].mean() < 0.3:
        LOG.warn(f"코사인 유사도 평균이 {S['cosine'].mean():.3f} 로 매우 낮습니다. "
                 f"정상적인 정기보고서는 전년 대비 0.7~0.95 가 일반적입니다. "
                 f"★ 정규화가 제대로 되지 않아 가짜 변화가 지배하고 있을 가능성이 큽니다 — "
                 f"위 '정규화 육안 검증 샘플' 을 반드시 확인하세요.")
        PIPE.note("WARN: D1 코사인 평균 과소 — 정규화 점검 필요")
    PIPE.io("OUT", "MEM", "d1_similarity", S)
    return S


# ── 합성 (§6.1.5 공통충격 제거 → §6.1.7 섹션 가중) ──────────────────────────────────────────
def d1_composite(S: pd.DataFrame, struct: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """기간×섹션 횡단면 z → 지표 동일가중 → 섹션 가중합성 → D1_SCORE.

    ★ §6.1.5: DART 공시서식이 개정된 시기에는 전 종목이 동시에 문서를 바꾼다. 기업 고유
      신호가 아니다. 절대 유사도를 그대로 쓰면 그 해 전체가 '변경 기업'이 된다.
      기간별 횡단면 z-score 로 공통충격을 평균에 흡수시킨다.
      기간 = (사업연도 × 문서유형) — 같은 유형·같은 해 제출분끼리만 비교해야 한다.
    """
    if S is None or S.empty:
        return pd.DataFrame(columns=D1_OUT_COLS)
    d = S.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt", "corp_code", "section"])
    d["_per"] = (d["bsns_year"].astype(str) + "|" + d["doc_type"].astype(str) + "|" +
                 d["section"].astype(str))

    # CHANGE = 1 − similarity, 지표별 기간 횡단면 z, 동일가중 평균
    zs = []
    for m in D1_METRICS:
        if m not in d.columns:
            continue
        ch = 1.0 - pd.to_numeric(d[m], errors="coerce")
        z = xsec_z(ch, d["_per"], min_n=CELL_MIN_N)
        # 표본이 얇은 기간은 전체 기간(연도) 셀로 폴백
        if z.isna().any():
            z = z.where(z.notna(), xsec_z(ch, d["bsns_year"].astype(str) + "|" +
                                          d["section"].astype(str), min_n=CELL_MIN_N))
        d[f"z_{m}"] = z
        zs.append(f"z_{m}")
    if not zs:
        return pd.DataFrame(columns=D1_OUT_COLS)
    d["CH_sec"] = nanmean_cols(d, zs)

    # 섹션 → 문서 단위 피벗. 합성 지표와 4개 개별 지표를 모두 만든다
    # (개별 지표는 §8.4 '유사도 4종 각각 단독 사용 시 성과' 강건성 검사에 필요하다).
    def _pivot(valcol: str, prefix: str) -> pd.DataFrame:
        pv = d.pivot_table(index=["corp_code", "rcept_dt"], columns="section",
                           values=valcol, aggfunc="mean")
        pv = pv.reindex(columns=ARC_SECTIONS)
        pv.columns = [f"{prefix}{s}" for s in ARC_SECTIONS]
        return pv.reset_index()

    W = _pivot("CH_sec", "CH_")
    wvec = np.array([D1_SECTION_WEIGHTS.get(s, 0.0) for s in ARC_SECTIONS], dtype="float64")

    def _weighted(pv: pd.DataFrame, prefix: str, wv: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """★ 결측 섹션 가중치를 나머지에 '비례 재배분'. 가중치 합은 항상 1이어야 한다.
        이걸 틀리면 섹션이 적게 파싱된 종목이 구조적으로 유리/불리해진다."""
        V = pv[[f"{prefix}{s}" for s in ARC_SECTIONS]].to_numpy(dtype="float64")
        msk = np.isfinite(V)
        wm = np.where(msk, wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        c = np.where(ws > 0,
                     np.nansum(np.where(msk, V, 0.0) * wm, axis=1) / np.where(ws > 0, ws, 1.0),
                     np.nan)
        return c, msk.sum(axis=1)

    comp, nsec = _weighted(W, "CH_", wvec)
    W["CHANGE_composite"] = comp
    W["n_sections"] = nsec
    # 섹션 가중치 균등배분 버전 (§8.4 강건성 — 사전등록 가중치의 타당성 검증용)
    W["CHANGE_equalw"], _ = _weighted(W, "CH_", np.ones(len(ARC_SECTIONS), dtype="float64"))
    # 지표 4종 각각 단독
    for m in D1_METRICS:
        if f"z_{m}" not in d.columns:
            continue
        pm = _pivot(f"z_{m}", f"_m{m}_")
        cm, _ = _weighted(pm, f"_m{m}_", wvec)
        pm2 = pm[["corp_code", "rcept_dt"]].copy()
        pm2[f"CHANGE_{m}"] = cm
        W = W.merge(pm2, on=["corp_code", "rcept_dt"], how="left")

    # 섹션이 1개(S_ALL)뿐이면 가중합성이 사실상 S_ALL 단독이다. 신호로 쓰되 표시해 둔다.
    n_thin = int((W["n_sections"] <= 1).sum())
    if n_thin:
        LOG.info(f"섹션이 1개 이하로 파싱된 문서 {n_thin:,}건 — S_ALL 단독으로 합성됩니다 "
                 f"(가중치 비례 재배분 적용, 탈락시키지 않음).")

    # D1_SCORE = −z(CHANGE_composite). 변화가 클수록 낮은 점수(§6.1.7).
    W["_yr"] = as_ts_series(W["rcept_dt"]).dt.year.astype(str)
    W["D1_SCORE"] = -xsec_z(W["CHANGE_composite"], W["_yr"], min_n=CELL_MIN_N)
    W["D1_SCORE_equalw"] = -xsec_z(W["CHANGE_equalw"], W["_yr"], min_n=CELL_MIN_N)
    for m in D1_METRICS:
        if f"CHANGE_{m}" in W.columns:
            W[f"D1_SCORE_{m}"] = -xsec_z(W[f"CHANGE_{m}"], W["_yr"], min_n=CELL_MIN_N)
    W = W.drop(columns=["_yr"])

    # §6.1.6 구조적 변화 종목-기간은 결측 처리 (0 이 아니다)
    W["STRUCT_FLAG"] = 0.0
    if struct is not None and len(struct):
        st = struct.copy()
        st["knowledge_date"] = as_ts_series(st["knowledge_date"])
        st = st.dropna(subset=["corp_code", "knowledge_date"])
        if len(st):
            key = st.groupby(st["corp_code"].astype(str))["knowledge_date"].apply(list).to_dict()
            flags = []
            for cc, rd in zip(W["corp_code"].astype(str), as_ts_series(W["rcept_dt"])):
                ds = key.get(cc)
                # 문서 접수일 기준 ±1년 안에 구조적 변화 공시가 있으면 그 문서는 노이즈
                hit = bool(ds) and any(abs((rd - d0).days) <= 365 for d0 in ds if pd.notna(d0))
                flags.append(1.0 if hit else 0.0)
            W["STRUCT_FLAG"] = flags
            n_s = int(W["STRUCT_FLAG"].sum())
            if n_s:
                LOG.info(f"STRUCT_FLAG 발동 {n_s:,}건 — 해당 문서의 D1 을 결측 처리합니다 "
                         f"(민감도 분석에서 포함 버전과 비교됩니다).")
                _nan_cols = [c for c in (["CHANGE_composite", "D1_SCORE"] + D1_VARIANT_COLS)
                             if c in W.columns]
                W.loc[W["STRUCT_FLAG"] == 1.0, _nan_cols] = np.nan

    W["event_date"] = as_ts_series(W["rcept_dt"])
    # §4 DART 공시는 접수일 + 1거래일부터 사용 가능
    W["knowledge_date"] = W["event_date"] + pd.Timedelta(days=ARC_DART_LAG_DAYS)
    W = pit_frame(W, "event_date", "knowledge_date", source="dart_d1")
    W = ensure_cols(W, D1_OUT_COLS)
    LOG.ok(f"D1 합성 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(섹션 평균 {W['n_sections'].mean():.1f}개 · "
           f"D1_SCORE 유효 {int(W['D1_SCORE'].notna().sum()):,})")
    PIPE.io("OUT", "MEM", "d1_composite", W)
    return W[D1_OUT_COLS]


def attach_d1(P: pd.DataFrame, d1: Optional[pd.DataFrame]) -> pd.DataFrame:
    """패널에 D1 결합 + D1_MISSING 판정 (§3.3 상장 24개월 미만 / §6.1.6 / 파싱 실패)."""
    P = P.copy()
    add = ([f"CH_{s}" for s in ARC_SECTIONS] +
           ["CHANGE_composite", "D1_SCORE", "STRUCT_FLAG", "n_sections"] + D1_VARIANT_COLS)
    if d1 is not None and len(d1) and "corp_code" in P.columns:
        PIT.register("arc_d1", d1, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d1", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + add, suffix="_d1")
    # ★ 결합 이후에 채운다. 먼저 만들면 merge_asof 가 실제 데이터에 접미사를 붙여 흘려버린다.
    P = ensure_cols(P, add)
    P["STRUCT_FLAG"] = pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0.0)

    young = (pd.to_numeric(P.get("listing_months"), errors="coerce") < ARC_D1_MIN_LISTING_M)
    if young.any():
        _nc = [c for c in (["D1_SCORE", "CHANGE_composite"] + D1_VARIANT_COLS) if c in P.columns]
        P.loc[young.fillna(False), _nc] = np.nan
        LOG.info(f"상장 {ARC_D1_MIN_LISTING_M}개월 미만 {int(young.fillna(False).sum()):,}행은 "
                 f"D1 만 결측 처리합니다 (전년 동기 문서 부재 — §3.3). "
                 f"축 A·D2·D3 에는 그대로 잔류합니다.")
    P["D1_MISSING"] = P["D1_SCORE"].isna().astype("float32")
    rate = float(P["D1_MISSING"].mean()) if len(P) else 1.0
    LOG.ok(f"D1 결합 완료 — 결측률 {100*rate:.1f}% "
           f"(결측분은 §6.5 에 따라 D2·D3 로 가중치가 비례 재배분되며 종목은 탈락하지 않습니다)")
    return P


def report_d1_sign_check(P: pd.DataFrame) -> dict:
    """§9.2-(4) D1 부호 검증 — 한국 데이터에서 '변화 = 악재' 가 성립하는가.

    ★ 원논문에서 변화의 대다수가 부정적 감성이었기에 '변화=악재' 방향이 나왔다. 그러나
      이론적으로 방향은 사전에 확정되지 않는다. 역전이면 그 사실을 그대로 보고하고
      D1 을 '검증 실패' 로 처리해야 한다(§9.3-5). 부호를 뒤집어 성과를 맞추지 않는다.
    """
    LOG.banner("D1 부호 검증 (§9.2-4)",
               "'문서를 많이 바꾼 기업이 나쁜가' 를 한국 데이터로 직접 검정한다")
    out = {"monotone": None, "spread": np.nan, "sign_ok": None, "verdict": "", "n": 0}
    if P is None or P.empty or "CHANGE_composite" not in P.columns:
        LOG.warn("CHANGE_composite 가 없어 부호 검증을 할 수 없습니다.")
        out["verdict"] = "판정불가 — D1 미산출"
        return out
    d = P[["CHANGE_composite", "fwd_ret_1q", "q"]].dropna()
    if len(d) < 200:
        LOG.warn(f"표본 {len(d):,}행으로는 부호 검증이 불가능합니다.")
        out["verdict"] = f"판정불가 — 표본 부족({len(d):,}행)"
        return out
    d = d.copy()
    try:
        d["quint"] = d.groupby("q", observed=True)["CHANGE_composite"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop"))
    except Exception:
        d["quint"] = pd.qcut(d["CHANGE_composite"].rank(method="first"), 5,
                             labels=False, duplicates="drop")
    g = d.dropna(subset=["quint"]).groupby("quint")["fwd_ret_1q"]
    mu = g.mean()
    rows = [[f"Q{int(k)+1} ({'변화 최소' if k == 0 else ('변화 최대' if k == mu.index.max() else '')})",
             f"{int(g.size()[k]):,}", f"{v*100:+.2f}%"] for k, v in mu.items()]
    LOG.table(rows, ["CHANGE 5분위", "표본", "평균 1Q 수익률"], ["l", "r", "r"])
    if len(mu) >= 2:
        lo, hi = float(mu.iloc[0]), float(mu.iloc[-1])
        spread = lo - hi                      # 변화 적은 쪽 − 변화 많은 쪽
        out["spread"] = spread
        out["n"] = int(len(d))
        diffs = np.diff(mu.to_numpy())
        out["monotone"] = bool(np.all(diffs <= 0) or np.all(diffs >= 0))
        out["sign_ok"] = bool(spread > 0)
        LOG.info(f"변화 최소분위 {lo*100:+.2f}%  vs  변화 최대분위 {hi*100:+.2f}%  → "
                 f"스프레드 {spread*100:+.2f}%p (단조성 {'있음' if out['monotone'] else '없음'})")
        if out["sign_ok"]:
            out["verdict"] = ("미국 10-K 결과와 같은 방향(변화 = 악재)이 한국 데이터에서도 "
                              "관측됩니다. 단, 유의성은 어블레이션 B1 과 BH-FDR 판정을 보십시오.")
            LOG.ok(out["verdict"])
        else:
            out["verdict"] = ("★ 부호 역전: 한국 데이터에서는 '문서를 많이 바꾼 기업'의 수익이 "
                              "더 높습니다. §9.3-5 에 따라 부호를 뒤집지 않고 D1 을 '검증 실패' 로 "
                              "처리하며, D1 제외 버전(F2)을 주 결과로 삼는 것을 권고합니다.")
            LOG.error(out["verdict"])
    return out


def build_d1_streaming(struct: Optional[pd.DataFrame] = None,
                       years: Optional[Sequence[int]] = None,
                       T_manifest: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """연도 2개씩만 메모리에 올려 D1 을 만든다. 상주량이 문서 수와 무관하게 평평해진다.

    ★ 확장 IDF 상태(df_state)를 연도 간에 이어받으므로, 한 번에 다 올려 계산한 것과
      동일한 '그 시점까지 관측된 문서로만' 성질을 유지한다(미래누수 없음).
    """
    ys = list(years) if years else arc_doc_years(T_manifest)
    if not ys:
        LOG.warn("정기보고서 토큰 샤드가 없어 D1 을 만들 수 없습니다.")
        return pd.DataFrame(columns=D1_OUT_COLS)
    df_state = {"df": Counter(), "n": 0}
    sims: List[pd.DataFrame] = []
    peak = 0.0
    for y in sorted(ys):
        if (y - 1) not in ys:
            continue                       # 전년 문서가 없으면 페어가 만들어지지 않는다
        T2 = arc_doc_load_years([y - 1, y])
        if T2.empty:
            continue
        pr = arc_doc_pairs(T2)
        del T2
        gc.collect()
        if pr is None or pr.empty:
            continue
        peak = max(peak, mem_mb(pr))
        # ★ 월 단위로 잘라 넘긴다. d1_similarity 는 내부적으로 월 배치로 IDF 를 고정하므로
        #   한 달씩 주는 것과 한 해를 통째로 주는 것이 수치적으로 동일하고, 상주량만 줄어든다.
        pr["_m"] = as_ts_series(pr["rcept_dt"]).dt.to_period("M")
        for _mk in sorted(pr["_m"].dropna().unique()):
            chunk = pr[pr["_m"] == _mk].drop(columns=["_m"])
            if chunk.empty:
                continue
            s1 = d1_similarity(chunk, df_state=df_state)
            del chunk
            if s1 is not None and len(s1):
                sims.append(s1)
        del pr
        gc.collect()
    if not sims:
        LOG.warn("연도 스트리밍 D1 에서 유사도를 한 건도 만들지 못했습니다.")
        return pd.DataFrame(columns=D1_OUT_COLS)
    S = pd.concat(sims, ignore_index=True)
    del sims
    LOG.ok(f"D1 연도 스트리밍 완료 — 유사도 {len(S):,}행 · 연도 {len(ys)}개 · "
           f"페어 프레임 최대 상주 {peak:,.0f}MB (연도 2개 + 월 단위 청크)")
    _bud = float(globals().get("MEM_BUDGET_GB", 6.0)) * 1000.0
    if peak > _bud * 0.5:
        LOG.warn(f"D1 페어 프레임이 {peak:,.0f}MB 로 메모리 예산({_bud:,.0f}MB)의 절반을 "
                 f"넘었습니다. ARC_DOC_TF_TOP 을 낮추면(현재 {ARC_DOC_TF_TOP}) 선형으로 "
                 f"줄어듭니다 — 유사도 정확도는 거의 변하지 않습니다.")
    return d1_composite(S, struct)
