

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-Q1  1차 필터 — U-1000 → U-200, 3변형 비교 (§5.5, §5.6)                                 ║
# ║                                                                                          ║
# ║  이 전략의 핵심 실험은 "수급 축이 실제로 다른 종목을 뽑는가" 다.                            ║
# ║  세 변형을 끝까지 독립 실행하고, 중복률·특성·회전율을 나란히 놓고 판단한다(§9).             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def score1(P: pd.DataFrame, variant: str) -> pd.Series:
    """Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F  (§5.5 사전등록 가중치, 튜닝 금지)

    ★ 결측 축 처리: 가중치는 고정이지만 축 자체가 결측인 행이 있다. 결측을 0(=셀 평균)으로
      채우면 그 종목이 '평균적인 종목'으로 둔갑해 분산이 압축되고, 결측이 많은 초소형주가
      일제히 중앙으로 몰린다. 대신 '가용 축에 대해 가중치를 재정규화'하고, 재정규화가
      일어난 비율을 반드시 로그로 남긴다(수급 축이 사실상 죽어 있으면 여기서 드러난다).
    """
    if variant not in VARIANT_W:
        raise KeyError(f"알 수 없는 변형: {variant} (가능: {list(VARIANT_W)})")
    wv, wq, wf = VARIANT_W[variant]
    parts = [(col(P, "Z_V"), wv), (col(P, "Z_Q"), wq), (col(P, "Z_F"), wf)]
    parts = [(z, w) for z, w in parts if w > 0]
    num = pd.Series(0.0, index=P.index)
    den = pd.Series(0.0, index=P.index)
    for z, w in parts:
        ok = z.notna()
        num = num.add((z.fillna(0.0) * w).where(ok, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(ok, w, 0.0), index=P.index), fill_value=0.0)
    s = (num / den.where(den > 0)).astype("float32")
    full_w = sum(w for _z, w in parts)
    renorm = float(((den > 0) & (den < full_w - 1e-9)).mean())
    if renorm > 0.01:
        LOG.info(f"  [{variant}] 축 결측으로 가중치 재정규화된 행 {100*renorm:.1f}% "
                 f"(0 으로 채우지 않고 가용 축만으로 계산)")
    return s


def _rank_pick(g: pd.DataFrame, n: int, score_col: str) -> pd.Index:
    """상위 n 선정. 동점은 명시적 키로 깬다 — 행 순서(=대개 종목코드 오름차순)로 깨면
    포트폴리오가 데이터가 아니라 정렬의 함수가 된다."""
    keys = [score_col] + [c for c in ("Z_V", "mktcap", "code") if c in g.columns]
    asc = [False] + [False if c in ("Z_V",) else True for c in keys[1:]]
    return g.sort_values(keys, ascending=asc, kind="mergesort").head(n).index


def build_u200(P: pd.DataFrame, variants: Sequence[str] = VARIANTS,
               n: int = U200_N) -> pd.DataFrame:
    """각 변형별 Score1 과 U-200 소속 플래그를 패널에 추가한다.

    반환 패널에 추가되는 컬럼:  score1_<V>  ·  u200_<V> (bool)
    """
    d = P.copy()
    for v in variants:
        d[f"score1_{v}"] = score1(d, v)
    for v in variants:
        sc = f"score1_{v}"
        flag = pd.Series(False, index=d.index)
        for _t, g in d.groupby("rebal", observed=True):
            gg = g[g[sc].notna()]
            if gg.empty:
                continue
            flag.loc[_rank_pick(gg, min(n, len(gg)), sc)] = True
        d[f"u200_{v}"] = flag
    rows = []
    for v in variants:
        cnt = d.groupby("rebal", observed=True)[f"u200_{v}"].sum()
        rows.append([v, f"{cnt.mean():,.0f}", f"{cnt.min():,.0f}", f"{cnt.max():,.0f}",
                     f"{int(d[f'score1_{v}'].notna().sum()):,}"])
    LOG.table(rows, ["변형", "U-200 평균", "최소", "최대", "Score1 산출행"],
              ["c", "r", "r", "r", "r"],
              title=f"1차 필터 결과 (§5.5 사전등록 가중치 · 목표 상위 {n}종목)")
    return d


# ── §5.6 필수 보고 항목 ─────────────────────────────────────────────────────────────────────
def _jaccard(a: set, b: set) -> float:
    u = a | b
    return float(len(a & b) / len(u)) if u else float("nan")


def report_variant_comparison(P: pd.DataFrame, variants: Sequence[str] = VARIANTS,
                              rep_cov: Optional[pd.DataFrame] = None) -> dict:
    """§5.6 — 세 변형이 실질적으로 다른 종목을 뽑는지 확인한다. [5] 완료 시점의 중간 보고."""
    LOG.banner("① 1차필터 3변형 비교 (§5.6)",
               "변형들이 실제로 다른 종목을 뽑는가 · 수급 축이 유동성/커버리지 편향을 만드는가")

    sets: Dict[str, Dict[pd.Timestamp, set]] = {}
    for v in variants:
        sets[v] = {t: set(g.loc[g[f"u200_{v}"], "code"])
                   for t, g in P.groupby("rebal", observed=True)}

    # (1) 변형 간 중복률
    ov_rows, ov = [], {}
    for i, a in enumerate(variants):
        for b in variants[i + 1:]:
            vals = [_jaccard(sets[a].get(t, set()), sets[b].get(t, set()))
                    for t in sorted(set(sets[a]) | set(sets[b]))]
            vals = [x for x in vals if np.isfinite(x)]
            m = float(np.mean(vals)) if vals else float("nan")
            ov[f"{a}~{b}"] = m
            ov_rows.append([f"{a} ∩ {b}", f"{m:.3f}",
                            f"{np.min(vals):.3f}" if vals else "—",
                            f"{np.max(vals):.3f}" if vals else "—",
                            "실질적으로 동일" if m >= 0.85 else "충분히 다름"])
    LOG.table(ov_rows, ["변형 쌍", "평균 중복률(교집합/합집합)", "최소", "최대", "판정(§9-C3 기준 0.85)"],
              ["l", "r", "r", "r", "l"],
              title="변형 간 U-200 중복률 — 이 값이 0.85 이상이면 변형 비교 자체가 무의미해진다")

    # (2) 변형별 특성 (시총 · 유동성 · 섹터 집중도)
    ch_rows = []
    for v in variants:
        sub = P[P[f"u200_{v}"]]
        if sub.empty:
            ch_rows.append([v, "—", "—", "—", "—", "—"])
            continue
        cap_med = float(pd.to_numeric(sub["mktcap"], errors="coerce").median())
        adtv_med = float(pd.to_numeric(sub["adtv"], errors="coerce").median())
        # 섹터 집중도(HHI): 1 에 가까울수록 한 섹터 쏠림
        sh = sub.groupby("sector", observed=True).size() / len(sub)
        hhi = float((sh ** 2).sum())
        n_sec = int(sub["sector"].nunique())
        ch_rows.append([v, f"{cap_med/1e8:,.0f}억", f"{adtv_med/1e8:,.2f}억",
                        f"{n_sec}", f"{hhi:.3f}", f"{len(sub):,}"])
    LOG.table(ch_rows, ["변형", "시총 중앙값", "60일 ADTV 중앙값", "섹터 수", "섹터 HHI", "총 관측"],
              ["c", "r", "r", "r", "r", "r"],
              title="변형별 U-200 특성 — 수급 축 추가가 유동성 편향을 만드는지")

    # (3) 리포트 커버리지 (§5.6 — 수급 축이 '커버리지 프록시'에 불과한지 판별)
    cov = {}
    if rep_cov is not None and len(rep_cov):
        C = rep_cov[["code", "rebal", "n_reports"]].copy()
        cov_rows = []
        for v in variants:
            sub = P[P[f"u200_{v}"]][["code", "rebal"]].merge(C, on=["code", "rebal"], how="left")
            r = float((pd.to_numeric(sub["n_reports"], errors="coerce").fillna(0) > 0).mean()) \
                if len(sub) else float("nan")
            cov[v] = r
            cov_rows.append([v, f"{100*r:.1f}%" if np.isfinite(r) else "—", f"{len(sub):,}"])
        LOG.table(cov_rows, ["변형", "리포트 ≥1건 종목 비율", "관측"], ["c", "r", "r"],
                  title="변형별 U-200 리포트 커버리지 (§9-C5 판정 입력)")
        if np.isfinite(cov.get("VQF", np.nan)) and np.isfinite(cov.get("VQ", np.nan)):
            gap = cov["VQF"] - cov["VQ"]
            LOG.info(f"VQF − VQ 커버리지 격차 {100*gap:+.1f}%p — "
                     + ("격차가 크면 수급 축은 '기관이 보는 종목=리포트 있는 종목' 을 재발견한 "
                        "커버리지 프록시일 뿐입니다." if gap > 0.10 else
                        "격차가 작아 수급 축이 커버리지의 단순 대리변수는 아닙니다."))
    else:
        LOG.warn("리포트 커버리지 입력이 없어 §5.6 커버리지 비교를 생략합니다 "
                 "(§9-C5 는 '판정 불가'로 보고됩니다).")

    # (4) 변형별 U-200 회전율
    tn_rows, turn = [], {}
    for v in variants:
        ts = sorted(sets[v])
        vals = []
        for a, b in zip(ts, ts[1:]):
            sa, sb = sets[v][a], sets[v][b]
            if not sa and not sb:
                continue
            vals.append(len(sb - sa) / max(len(sb), 1))
        m = float(np.mean(vals)) if vals else float("nan")
        turn[v] = m
        tn_rows.append([v, f"{100*m:.1f}%" if np.isfinite(m) else "—"])
    LOG.table(tn_rows, ["변형", "분기 평균 U-200 교체율"], ["c", "r"],
              title="변형별 회전율 — 수급 축은 60일 창이라 회전율을 크게 높일 수 있다(비용에 직결)")

    LOG.info("§11 중간 보고 지점입니다. 위 중복률이 0.85 이상이면 이후 실험의 의미가 축소되며, "
             "그 사실을 §9 판정(C3)에 그대로 반영합니다. 자동으로 중단하지 않고 계속 진행합니다.")
    return {"overlap": ov, "coverage": cov, "turnover": turn,
            "sets": {v: {str(t): sorted(s) for t, s in sets[v].items()} for v in variants}}
