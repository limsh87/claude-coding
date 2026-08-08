

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-L  공동커버리지 링크 행렬 (SPEC §6.1) + 애널리스트 스킬 (SPEC §6.4)                    ║
# ║                                                                                          ║
# ║   covered(a,i) = 1  if 애널리스트 a 가 [t-12M, t] 에 종목 i 리포트를 1건 이상 발간          ║
# ║   w_ij(t)      = Σ_a covered(a,i)·covered(a,j)   (i≠j)     # 공유 애널리스트 수            ║
# ║                                                                                          ║
# ║  구현 원칙                                                                                ║
# ║   · 밀집행렬 금지. C(애널 × 종목) 희소행렬을 만들고 W = CᵀC 로 한 번에 얻는다.              ║
# ║     2,500종목 밀집이면 월당 50MB × 120개월 = 6GB — 애초에 성립하지 않는다.                  ║
# ║   · 대각원소 0 강제 (자기 자신은 연결이 아니다).                                            ║
# ║   · PIT: 윈도우 필터는 pub_date 가 아니라 knowledge_date 로 건다.                           ║
# ║   · 월별 CSR 을 전용 인덱스에 직렬화한다. 재실행 시 재계산하지 않는다(§8.1 재실행 45분).     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

try:
    import scipy.sparse as _sp
    from scipy.sparse import csr_matrix as _csr
except Exception:                                            # pragma: no cover
    _sp = None
    _csr = None


class LinkMatrices:
    """월별 링크 행렬 보관소. 가중 방식별로 따로 만든다 (SPEC §6.4 의 3가지)."""

    def __init__(self, weight_mode: str = "unweighted"):
        self.mode = weight_mode
        self.codes: List[str] = []
        self.cidx: Dict[str, int] = {}
        self.W: "OrderedDict[pd.Timestamp, Any]" = OrderedDict()
        self.stats: List[dict] = []

    def n_links(self, m) -> np.ndarray:
        w = self.W.get(as_ts(m))
        if w is None:
            return np.zeros(len(self.codes))
        return np.asarray((w > 0).sum(axis=1)).ravel()

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame(self.stats)


def _cache_key(mode: str, codes: Sequence[str], lookback_m: int,
               ledger: Optional[pd.DataFrame]) -> str:
    """캐시 키에 결과를 바꾸는 입력을 '전부' 넣는다.

    이전엔 파일명이 mode 하나뿐이라, 종목 목록·룩백·링크 단위(analyst vs
    broker×sector_team)·원장 내용이 달라져도 같은 파일을 조용히 재사용했다.
    LM.codes 는 신호를 받을 종목 집합 그 자체이므로, 이 오재사용은 곧 결과 오염이다.
    """
    n = len(ledger) if ledger is not None else 0
    kmax = ""
    try:
        if ledger is not None and len(ledger):
            kmax = str(as_ts_series(ledger["knowledge_date"]).max())
            uni_keys = int(ledger["analyst_key"].nunique())
        else:
            uni_keys = 0
    except Exception:
        uni_keys = 0
    return sha1_str(mode, str(lookback_m), str(len(codes)),
                    sha1_str(",".join(map(str, codes))), str(n), kmax, str(uni_keys))[:16]


def _cache_path(mode: str, key: str = "") -> str:
    d = os.path.join(VAULT.ns["private"], "features", "linkmat")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"link_{mode}_{key}.npz" if key else f"link_{mode}.npz")


def _save_links(LM: LinkMatrices, key: str = ""):
    if _sp is None or not LM.W:
        return
    try:
        payload: Dict[str, Any] = {"__codes__": np.array(LM.codes, dtype=object),
                                   "__months__": np.array([str(m.date()) for m in LM.W], dtype=object)}
        for m, w in LM.W.items():
            k = f"m{m:%Y%m}"
            c = w.tocoo()
            payload[k + "_r"] = c.row.astype(np.int32)
            payload[k + "_c"] = c.col.astype(np.int32)
            payload[k + "_v"] = c.data.astype(np.float32)
        # ★ np.savez_compressed 는 파일명이 .npz 로 끝나지 않으면 '.npz' 를 덧붙인다.
        #   tmp 를 ".tmp" 로 두면 실제 파일은 ".tmp.npz" 가 되고 os.replace 가 매번 실패한다
        #   (그리고 예외를 삼키므로 '캐시가 조용히 전혀 안 되는' 상태가 된다).
        tmp = _cache_path(LM.mode, key) + ".tmp.npz"
        np.savez_compressed(tmp, **payload)
        os.replace(tmp, _cache_path(LM.mode, key))
        LOG.debug(f"링크 행렬 직렬화: {LM.mode} ({len(LM.W)}개월)")
    except Exception as e:                                    # noqa
        LOG.debug(f"링크 행렬 저장 실패({type(e).__name__}) — 재계산으로 진행합니다.")


def _load_links(mode: str, months: pd.DatetimeIndex, key: str,
                expect_codes: Sequence[str]) -> Optional[LinkMatrices]:
    p = _cache_path(mode, key)
    if _sp is None or not os.path.exists(p):
        return None
    try:
        z = np.load(p, allow_pickle=True)
        codes = [str(x) for x in z["__codes__"]]
        # 키가 같아도 좌표계는 반드시 재확인한다 (해시 충돌·부분 기록 방어)
        if list(codes) != [str(c) for c in expect_codes]:
            return None
        have = {str(x) for x in z["__months__"]}
        want = {str(as_ts(m).date()) for m in months}
        if not want.issubset(have):
            return None
        LM = LinkMatrices(mode)
        LM.codes = codes
        LM.cidx = {c: i for i, c in enumerate(codes)}
        n = len(codes)
        for m in months:
            m = as_ts(m)
            k = f"m{m:%Y%m}"
            if k + "_r" not in z:
                return None
            LM.W[m] = _csr((z[k + "_v"], (z[k + "_r"], z[k + "_c"])), shape=(n, n))
        LOG.ok(f"링크 행렬 캐시 적중: {mode} ({len(LM.W)}개월) — 재계산 생략")
        return LM
    except Exception:
        return None


def build_link_matrices(ledger: pd.DataFrame, months: pd.DatetimeIndex,
                        codes: Sequence[str], weight_mode: str = "unweighted",
                        skill: Optional[pd.DataFrame] = None,
                        lookback_m: int = LINK_LOOKBACK_M,
                        use_cache: bool = True) -> LinkMatrices:
    """월별 공동커버리지 행렬 W(t) 를 만든다.

    weight_mode
      "unweighted" : covered = 1  (SPEC 기본)
      "freq"       : covered = 해당 윈도우 내 발간 건수 (발간빈도 가중)
      "highskill"  : 고스킬 애널리스트(상위 40%)만 사용, covered = 1
    """
    ck = _cache_key(weight_mode, codes, lookback_m, ledger)
    if use_cache:
        cached = _load_links(weight_mode, months, ck, [str(c) for c in dict.fromkeys(codes)])
        if cached is not None:
            return cached

    LM = LinkMatrices(weight_mode)
    LM.codes = [str(c) for c in dict.fromkeys(codes)]
    LM.cidx = {c: i for i, c in enumerate(LM.codes)}
    n = len(LM.codes)
    if _sp is None:
        LOG.error("scipy.sparse 를 쓸 수 없습니다 — 밀집행렬로는 이 전략을 돌리지 않습니다.")
        return LM
    if ledger is None or not len(ledger) or n == 0:
        LOG.warn("링크 원장 또는 종목 목록이 비어 링크 행렬을 만들 수 없습니다.")
        return LM

    d = ledger.copy()
    d["code"] = d["code"].astype(str)
    d = d[d["code"].isin(LM.cidx)]
    d["knowledge_date"] = as_ts_series(d["knowledge_date"])
    d = d.dropna(subset=["knowledge_date"])
    if not len(d):
        LOG.warn("유니버스 종목과 겹치는 리포트가 없습니다.")
        return LM

    # 고스킬 한정 모드: 월별로 자격 애널리스트가 달라지므로 (month, analyst_key) 집합을 미리 만든다
    hs: Dict[pd.Timestamp, set] = {}
    if weight_mode == "highskill":
        if skill is None or not len(skill):
            LOG.warn("스킬 테이블이 없어 'highskill' 구성을 비가중과 동일하게 처리합니다. "
                     "이 사실은 결과표에 표시됩니다.")
        else:
            s = skill.copy()
            s["month"] = as_ts_series(s["month"])
            for m, g in s[s["is_high"]].groupby("month"):
                hs[as_ts(m)] = set(g["analyst_key"].astype(str))

    d["_ci"] = d["code"].map(LM.cidx).astype(np.int32)
    akeys = pd.Index(sorted(d["analyst_key"].astype(str).unique()))
    aidx = {a: i for i, a in enumerate(akeys)}
    d["_ai"] = d["analyst_key"].astype(str).map(aidx).astype(np.int32)
    d = d.sort_values("knowledge_date", kind="stable").reset_index(drop=True)
    kd = d["knowledge_date"].to_numpy("datetime64[ns]")

    t0 = time.time()
    no_skill_months: List[pd.Timestamp] = []
    for m in tqdm(months, desc=f"링크행렬[{weight_mode}]", disable=not VERBOSE):
        m = as_ts(m)
        lo = m - pd.DateOffset(months=lookback_m)
        # PIT: knowledge_date 로 자른다. 정렬돼 있으므로 O(log n).
        i0 = int(np.searchsorted(kd, np.datetime64(lo), side="left"))
        i1 = int(np.searchsorted(kd, np.datetime64(m), side="right"))
        win = d.iloc[i0:i1]
        if weight_mode == "highskill" and hs:
            # '그 달에 스킬 표본이 없음'과 '자격 애널리스트가 0명'은 다른 사건이다.
            # 전자를 후자로 처리하면 초기 24개월이 통째로 빈 행렬이 되고, H4 비교에서
            # 그 구간이 조용히 빠진다. 표본이 없으면 비가중과 동일하게 둔다.
            if m in hs:
                allow = hs[m]
                win = win[win["analyst_key"].astype(str).isin(allow)] if allow else win.iloc[0:0]
            else:
                no_skill_months.append(m)
        if not len(win):
            LM.W[m] = _csr((n, n), dtype=np.float32)
            LM.stats.append({"month": m, "n_analyst": 0, "n_pair": 0, "n_covered": 0,
                             "median_links": 0.0})
            continue

        if weight_mode == "freq":
            g = win.groupby(["_ai", "_ci"], observed=True).size().reset_index(name="v")
            vals = g["v"].to_numpy(np.float32)
        else:
            g = win[["_ai", "_ci"]].drop_duplicates()
            vals = np.ones(len(g), dtype=np.float32)
        C = _csr((vals, (g["_ai"].to_numpy(np.int32), g["_ci"].to_numpy(np.int32))),
                 shape=(len(akeys), n))
        W = (C.T @ C).tocsr()
        W.setdiag(0)                       # ★ 자기 자신은 연결이 아니다
        W.eliminate_zeros()
        LM.W[m] = W.astype(np.float32)
        deg = np.asarray((W > 0).sum(axis=1)).ravel()
        LM.stats.append({"month": m, "n_analyst": int(win["_ai"].nunique()),
                         "n_pair": int(W.nnz // 2), "n_covered": int((deg > 0).sum()),
                         "median_links": float(np.median(deg[deg > 0])) if (deg > 0).any() else 0.0})

    LOG.ok(f"링크 행렬 {len(LM.W)}개월 생성 [{weight_mode}] — {time.time()-t0:.1f}s")
    if no_skill_months:
        LOG.warn(f"[highskill] 스킬 표본이 없는 {len(no_skill_months)}개월은 비가중과 동일하게 "
                 f"처리했습니다 (예: {no_skill_months[0]:%Y-%m} ~ {no_skill_months[-1]:%Y-%m}). "
                 f"H4 비교 시 이 구간은 두 구성이 같습니다.")
    S = LM.summary()
    if len(S):
        LOG.table([[f"{r['month']:%Y-%m}", f"{int(r['n_analyst']):,}", f"{int(r['n_covered']):,}",
                    f"{int(r['n_pair']):,}", f"{r['median_links']:.0f}"]
                   for _, r in S.iloc[::max(1, len(S) // 8)].iterrows()],
                  ["월", "활동 애널", "연결보유 종목", "링크쌍", "종목당 연결(중위)"],
                  ["l", "r", "r", "r", "r"],
                  title=f"링크 행렬 요약 [{weight_mode}] — 표본 8개월")
    _save_links(LM, ck)
    return LM


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  애널리스트 스킬 — 경험적 베이즈 축소추정 (SPEC §6.4, 선택이 아니라 필수)
# ═══════════════════════════════════════════════════════════════════════════════════════════
SKILL_LOOKBACK_M = 24        # 직전 24개월 목표주가 개정
SKILL_HORIZON_M = 3          # 이후 3개월 수익률과 부호 일치
SKILL_TOP_PCT = 0.40         # 상위 40% = 고스킬


def _beta_binom_k(hits: np.ndarray, n: np.ndarray) -> float:
    """적률법으로 베타-이항 사전강도 k 를 추정한다.

    k 가 클수록 사전분포로 강하게 끌어당긴다. 애널리스트 1인당 유효 개정 건수가
    연 40~80건뿐이라 비축소 추정은 거의 전부 잡음이다 — 그래서 이 축소는 필수다.
    """
    ok = (n > 0) & np.isfinite(hits) & np.isfinite(n)
    if ok.sum() < 8:
        return 20.0
    p = hits[ok] / n[ok]
    nb = n[ok]
    mu = float(np.average(p, weights=nb))
    if not (0 < mu < 1):
        return 20.0
    var = float(np.average((p - mu) ** 2, weights=nb))
    within = mu * (1 - mu) * float(np.average(1.0 / nb, weights=nb))
    between = var - within
    if between <= 1e-9:
        return 200.0                      # 개인차가 관측되지 않음 → 거의 전부 사전으로
    k = mu * (1 - mu) / between - 1.0
    return float(np.clip(k, 5.0, 500.0))


def build_analyst_skill(ledger: pd.DataFrame, price_m: pd.DataFrame,
                        months: pd.DatetimeIndex, sector: pd.DataFrame) -> pd.DataFrame:
    """월별 애널리스트 스킬 (PIT). 반환: analyst_key, month, n_rev, hit_raw, skill, is_high

    정의(SPEC §6.4): 직전 24개월 목표주가 개정의 부호가 이후 3개월 수익률과 일치한 비율.
    축소추정: 증권사 평균 → 섹터 평균 순으로 shrink. 관측 수가 적을수록 강하게 끌어당긴다.

    ★ PIT 주의: 시점 t 에서 쓸 수 있는 개정은 s + 3개월 ≤ t 인 것뿐이다.
      (개정 시점의 '이후 3개월 수익률'을 알아야 적중 여부가 정해지므로)
    """
    cols = ["analyst_key", "month", "n_rev", "hit_raw", "skill", "is_high"]
    if ledger is None or not len(ledger) or "target_price" not in ledger.columns:
        LOG.warn("목표주가가 없어 애널리스트 스킬을 계산할 수 없습니다 — "
                 "'highskill' 구성은 비가중과 동일해집니다.")
        return pd.DataFrame(columns=cols)

    d = ledger.dropna(subset=["target_price"]).copy()
    if not len(d):
        LOG.warn("유효 목표주가가 0건입니다 — 스킬 계산 불가.")
        return pd.DataFrame(columns=cols)
    d["knowledge_date"] = as_ts_series(d["knowledge_date"])
    d["month"] = d["knowledge_date"] + pd.offsets.MonthEnd(0)
    d = d.sort_values(["analyst_key", "code", "knowledge_date"], kind="stable")

    # ① 같은 애널리스트가 같은 종목에 이전에 제시한 목표주가 대비 개정 부호
    g = d.groupby(["analyst_key", "code"], observed=True)["target_price"]
    d["tp_prev"] = g.shift(1)
    d = d[d["tp_prev"].notna() & (d["tp_prev"] > 0)]
    if not len(d):
        LOG.warn("직전 목표주가와 비교 가능한 개정이 없습니다 (동일 애널×종목 재방문 부족).")
        return pd.DataFrame(columns=cols)
    d["rev_sign"] = np.sign(d["target_price"] - d["tp_prev"])
    d = d[d["rev_sign"] != 0]

    # ② 개정 시점 이후 3개월 수익률
    pm = price_m[["code", "month", "close"]].copy()
    pm["code"] = pm["code"].astype(str)
    pm["month"] = as_ts_series(pm["month"])
    pm = pm.dropna(subset=["close"]).sort_values(["code", "month"])
    pm["close_fwd3"] = pm.groupby("code", observed=True)["close"].shift(-SKILL_HORIZON_M)
    pm["mfwd"] = pm.groupby("code", observed=True)["month"].shift(-SKILL_HORIZON_M)
    okgap = (((pm["mfwd"].dt.year - pm["month"].dt.year) * 12
              + (pm["mfwd"].dt.month - pm["month"].dt.month)) == SKILL_HORIZON_M)
    pm["ret3"] = np.where(okgap, safe_div(pm["close_fwd3"], pm["close"]) - 1.0, np.nan)

    d["code"] = d["code"].astype(str)
    d = d.merge(pm[["code", "month", "ret3"]], on=["code", "month"], how="left")
    d = d.dropna(subset=["ret3"])
    if not len(d):
        LOG.warn("개정 시점과 이후 3개월 수익률을 맞출 수 없습니다 — 스킬 계산 불가.")
        return pd.DataFrame(columns=cols)
    d["hit"] = (np.sign(d["ret3"]) == d["rev_sign"]).astype(float)
    # 적중 여부를 '알 수 있게 되는' 시점 = 개정월 + 3개월 (미래누수 차단의 핵심)
    d["known_month"] = d["month"] + pd.offsets.MonthEnd(SKILL_HORIZON_M)

    smap = (sector.set_index("code")["sector"].to_dict()
            if sector is not None and len(sector) else {})
    d["sector"] = d["code"].map(lambda c: smap.get(c, "미분류"))

    # ③ 월별 롤링 24개월 집계 + EB 축소
    d = d.sort_values("known_month", kind="stable")
    km = d["known_month"].to_numpy("datetime64[ns]")
    out = []
    for m in months:
        m = as_ts(m)
        lo = m - pd.DateOffset(months=SKILL_LOOKBACK_M)
        i0 = int(np.searchsorted(km, np.datetime64(lo), side="left"))
        i1 = int(np.searchsorted(km, np.datetime64(m), side="right"))
        w = d.iloc[i0:i1]
        if len(w) < 20:
            continue
        a = w.groupby("analyst_key", observed=True).agg(
            n_rev=("hit", "size"), hits=("hit", "sum"),
            broker=("broker_id", "first"), sector=("sector", lambda s: s.mode().iat[0]
                                                    if len(s.mode()) else "미분류")).reset_index()
        # 사전분포: 증권사 평균 → (표본 부족 시) 섹터 평균 → 전체 평균
        gm = float(w["hit"].mean())
        bro = w.groupby("broker_id", observed=True)["hit"].agg(["mean", "size"])
        sec_ = w.groupby("sector", observed=True)["hit"].agg(["mean", "size"])
        prior = []
        for _, r in a.iterrows():
            b = bro.loc[r["broker"]] if r["broker"] in bro.index else None
            if b is not None and b["size"] >= 30:
                prior.append(float(b["mean"]))
                continue
            s_ = sec_.loc[r["sector"]] if r["sector"] in sec_.index else None
            if s_ is not None and s_["size"] >= 30:
                prior.append(float(s_["mean"]))
                continue
            prior.append(gm)
        a["prior"] = prior
        k = _beta_binom_k(a["hits"].to_numpy(float), a["n_rev"].to_numpy(float))
        a["skill"] = (a["hits"] + k * a["prior"]) / (a["n_rev"] + k)
        a["hit_raw"] = safe_div(a["hits"], a["n_rev"])
        thr = a["skill"].quantile(1.0 - SKILL_TOP_PCT)
        a["is_high"] = a["skill"] >= thr
        a["month"] = m
        a["k_shrink"] = k
        out.append(a[["analyst_key", "month", "n_rev", "hit_raw", "skill", "is_high", "k_shrink"]])

    if not out:
        LOG.warn("스킬 산출 가능한 월이 없습니다 (개정 표본 부족).")
        return pd.DataFrame(columns=cols)
    S = pd.concat(out, ignore_index=True)
    med_n = float(S["n_rev"].median())
    LOG.table([["산출 월수", f"{S['month'].nunique()}"],
               ["애널리스트 수(연인원)", f"{len(S):,}"],
               ["1인당 유효 개정(중위)", f"{med_n:.0f}"],
               ["축소강도 k (중위)", f"{S['k_shrink'].median():.0f}"],
               ["원시 적중률(중위)", f"{S['hit_raw'].median():.1%}"],
               ["축소 후 스킬(중위)", f"{S['skill'].median():.1%}"],
               ["고스킬 판정 비율", f"{S['is_high'].mean():.1%}"]],
              ["항목", "값"], ["l", "r"],
              title="애널리스트 스킬 — 경험적 베이즈 축소추정 (SPEC §6.4)")
    if med_n < 10:
        LOG.warn(f"1인당 유효 개정이 중위 {med_n:.0f}건뿐입니다. 축소추정이 사전분포를 "
                 f"거의 그대로 돌려주므로 'highskill' 구성은 사실상 증권사/섹터 평균 분류에 "
                 f"가깝습니다. 이 한계를 결과표에 명시합니다.")
        open_question("OQ-03", "고스킬 애널리스트 정의",
                      f"1인당 유효 목표주가 개정이 중위 {med_n:.0f}건으로 매우 적다.",
                      "EB 축소를 필수 적용하고, highskill 구성의 해석 한계를 결과표에 명시.",
                      "highskill 아암의 결과는 개인 스킬이 아니라 하우스/섹터 효과일 수 있음.")
    return S
