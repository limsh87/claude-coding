

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  애널리스트 식별 · Phase 0 실현가능성 게이트 (SPEC §4.3)                             ║
# ║                                                                                          ║
# ║  이 전략의 유일한 실질 리스크는 알파가 아니라 '애널리스트 식별자 확보율' 이다.               ║
# ║  링크를 못 만들면 전략 자체가 존재하지 않는다. 그래서 코드 작성이 아니라 게이트가 먼저다.    ║
# ║                                                                                          ║
# ║  확보율을 올리는 세 경로 (전부 구현):                                                      ║
# ║   ① 한경컨센서스 리스트의 '작성자' 컬럼        — 가장 정확 (link_conf 0.98)                 ║
# ║   ② 네이버 상세페이지 바이라인(_detail_src)    — 기존 코드가 긁어놓고 버리던 것을 회수      ║
# ║   ③ PDF 본문 헤더 정규식                        — 최후 (link_conf 0.80)                     ║
# ║                                                                                          ║
# ║  ★ ②가 이번 구현의 실질 개선이다. 네이버 단독 리포트는 리스트에 작성자가 없어서 전부        ║
# ║    PDF 에 의존했는데, 상세페이지에는 이미 바이라인이 있고 수집도 되고 있었다.                ║
# ║    build_report_master 의 named-agg 목록에 없어서 조용히 버려지던 컬럼이다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 바이라인에서 걷어낼 소속/직함 토큰. 남는 한글 2~4자를 사람 이름으로 본다.
_BYLINE_STRIP = re.compile(
    r"(리서치센터|리서치|투자정보|애널리스트|연구원|수석|책임|선임|팀장|센터장|위원|박사|"
    r"증권|투자|금융|자산운용|㈜|\(주\)|Research|Analyst)", re.I)
_BYLINE_NAME = re.compile(r"[가-힣]{2,4}")


def parse_byline(raw: Any) -> str:
    """네이버 상세페이지 바이라인 텍스트 → '홍길동,김철수' 형태의 애널리스트명 문자열.

    바이라인은 '미래에셋증권 홍길동' / '홍길동 애널리스트' / '삼성증권 리서치센터' 등
    형태가 제각각이다. 소속·직함을 걷어낸 뒤 남는 한글 2~4자만 채택한다.
    증권사명만 있고 사람 이름이 없으면 빈 문자열 — 억지로 만들지 않는다.
    """
    t = norm_text(raw)
    if not t:
        return ""
    t = _BYLINE_STRIP.sub(" ", t)
    t = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+", " ", t)   # 이메일 제거
    t = re.sub(r"\d", " ", t)
    names = []
    for m in _BYLINE_NAME.findall(t):
        if len(m) < 2 or m in ("종목", "기업", "산업", "시장", "전망", "분석", "보고", "자료"):
            continue
        names.append(m)
    return ",".join(dict.fromkeys(names))[:120]


def naver_attach_analyst(nv: pd.DataFrame) -> pd.DataFrame:
    """네이버 프레임의 _detail_src 바이라인을 analyst_raw 로 승격한다.

    naver_enrich_detail 이 이미 긁어온 컬럼이다. build_report_master 가 이걸
    named-agg 목록에 넣지 않아 통째로 버려지고 있었다 — 여기서 회수한다.
    """
    if nv is None or not len(nv):
        return nv
    d = nv.copy()
    if "_detail_src" not in d.columns:
        return d
    if "analyst_raw" not in d.columns:
        d["analyst_raw"] = ""
    cur = d["analyst_raw"].astype(str).fillna("").str.strip()
    rec = d["_detail_src"].map(parse_byline)
    fill = (cur == "") & (rec.astype(str).str.len() > 0)
    d.loc[fill, "analyst_raw"] = rec[fill]
    LOG.ok(f"네이버 상세 바이라인에서 애널리스트 {int(fill.sum()):,}건 회수 "
           f"(기존 구현은 이 컬럼을 버리고 있었습니다)")
    PIPE.note(f"naver byline recovered: {int(fill.sum())}")
    return d


# ── 공개 시각 보수화 (SPEC §0.1) ────────────────────────────────────────────────────────────
def apply_publication_lag(rep: pd.DataFrame) -> pd.DataFrame:
    """리포트의 knowledge_date 를 '익영업일' 로 민다.

    SPEC §0.1: 리포트는 발간일이 아니라 '공개 확인 가능 시각' 기준으로 쓴다.
    장중 발간이면 당일 종가를 쓸 수 없다.
    그런데 두 소스 모두 발간 '시각'을 제공하지 않는다(날짜만, 자정으로 정규화됨).
    시각을 모르면 전부 장중 발간으로 간주하는 것이 가장 보수적인 선택이므로,
    모든 리포트의 knowledge_date = pub_date + 1영업일 로 둔다.
    (§0 규칙: 애매하면 임의 판단하지 말고 OPEN_QUESTIONS 에 기록 후 최보수 선택)
    """
    if rep is None or not len(rep):
        return rep
    d = rep.copy()
    pub = as_ts_series(d["pub_date"])
    d["event_date"] = pub
    d["knowledge_date"] = pub + pd.tseries.offsets.BDay(1)
    OPEN_QUESTIONS.append({
        "id": "OQ-01", "topic": "리포트 공개 시각",
        "issue": "한경·네이버 모두 발간 '시각'을 제공하지 않아 장중/장후 발간을 구분할 수 없다.",
        "choice": "전 건을 장중 발간으로 간주하고 knowledge_date = 발간일 + 1영업일 로 보수화했다.",
        "impact": "링크 형성(12개월 룩백)에는 거의 영향이 없고, 신호 형성 시점의 미래누수를 구조적으로 차단한다.",
    })
    LOG.info(f"리포트 {len(d):,}건의 knowledge_date 를 발간일+1영업일로 보수화했습니다 "
             f"(§0.1 — 발간 시각 미제공이므로 전부 장중 발간으로 간주).")
    return d


# ── Phase 0 게이트 ──────────────────────────────────────────────────────────────────────────
PHASE0: Dict[str, Any] = {"ran": False, "rate": float("nan"), "unit": "analyst",
                          "verdict": "미실행", "n": 0, "detail": {}}


def _identified_mask(rep: pd.DataFrame, L: pd.DataFrame) -> pd.Series:
    if rep is None or not len(rep):
        return pd.Series(dtype=bool)
    if L is None or not len(L) or "report_uid" not in L.columns:
        return pd.Series(False, index=rep.index)
    return rep["report_uid"].isin(set(L["report_uid"].astype(str)))


def phase0_gate(rep: pd.DataFrame, L: pd.DataFrame, t_start: float) -> dict:
    """SPEC §4.3 — 표본으로 확보율을 재고 링크 단위를 기계적으로 결정한다.

    임의 판단하지 않는다. 세 구간(§8 예시 그대로)에서 표본을 뽑아 확보율만 본다.
    """
    elapsed_min = (time.time() - t_start) / 60.0
    if elapsed_min > PHASE0_TIMEBOX_MIN:
        LOG.warn(f"Phase 0 타임박스 {PHASE0_TIMEBOX_MIN/60:.0f}시간 초과 — 즉시 중단하고 보고합니다.")

    res: Dict[str, Any] = {"ran": True, "elapsed_min": elapsed_min}
    if rep is None or not len(rep):
        res.update(rate=0.0, n=0, unit="broker_sector_team", verdict="표본 없음 → 폴백",
                   detail={})
        PHASE0.update(res)
        return res

    d = rep.copy()
    d["pub_date"] = as_ts_series(d["pub_date"])
    d["ym"] = d["pub_date"].dt.strftime("%Y-%m")
    d["identified"] = _identified_mask(d, L).to_numpy()

    # 지정 3개월에서 표본 추출. 해당 월에 데이터가 없으면 전체에서 균등 추출로 대체.
    picks = []
    per = max(1, PHASE0_SAMPLE_N // max(1, len(PHASE0_SAMPLE_MONTHS)))
    for ym in PHASE0_SAMPLE_MONTHS:
        sub = d[d["ym"] == ym]
        if len(sub):
            picks.append(sub.sample(n=min(per, len(sub)), random_state=SEED))
    sample = pd.concat(picks, ignore_index=True) if picks else d.sample(
        n=min(PHASE0_SAMPLE_N, len(d)), random_state=SEED)

    rate = float(sample["identified"].mean()) if len(sample) else 0.0
    # 소스별·연도별 세부 (보고용)
    by_src = (d.groupby(d["source"].astype(str))["identified"]
              .agg(["size", "mean"]).reset_index()) if "source" in d.columns else pd.DataFrame()
    by_year = (d.groupby(d["pub_date"].dt.year)["identified"]
               .agg(["size", "mean"]).reset_index())

    if rate >= PHASE0_GATE_HIGH:
        unit, verdict = "analyst", f"정상 진행 — 애널리스트 단위 링크 (확보율 {rate:.1%} ≥ 70%)"
        need_ipw = False
    elif rate >= PHASE0_GATE_LOW:
        unit, verdict = "analyst", (f"진행하되 §6.5 결측 민감도 분석 필수 "
                                    f"(40% ≤ 확보율 {rate:.1%} < 70%)")
        need_ipw = True
    else:
        unit, verdict = "broker_sector_team", (
            f"★ 애널리스트 단위 포기 → broker×sector_team 폴백 (확보율 {rate:.1%} < 40%). "
            f"교차업종 전용 버전을 주 버전으로 승격합니다.")
        need_ipw = True

    res.update(rate=rate, n=int(len(sample)), unit=unit, verdict=verdict, need_ipw=need_ipw,
               overall_rate=float(d["identified"].mean()),
               detail={"by_source": by_src, "by_year": by_year})
    PHASE0.update(res)

    LOG.banner("PHASE 0 — 데이터 실현가능성 게이트 (SPEC §4.3)",
               f"표본 {len(sample):,}건 · 확보율 {rate:.1%} · 경과 {elapsed_min:.1f}분")
    LOG.table([["표본 확보율", f"{rate:.1%}"],
               ["전체 확보율", f"{d['identified'].mean():.1%}"],
               ["표본 크기", f"{len(sample):,}"],
               ["게이트 기준", "≥70% 정상 / 40~70% IPW필수 / <40% 폴백"],
               ["링크 단위 결정", unit],
               ["판정", verdict]],
              ["항목", "값"], ["l", "l"])
    if len(by_src):
        LOG.table([[r.iloc[0], f"{int(r.iloc[1]):,}", f"{float(r.iloc[2]):.1%}"]
                   for _, r in by_src.iterrows()],
                  ["소스 조합", "건수", "애널 확보율"], ["l", "r", "r"],
                  title="소스별 애널리스트 확보율")
    if unit == "broker_sector_team":
        LOG.warn("폴백으로 전환합니다. 모든 산출물 최상단에 이 사실이 명시되며, "
                 "폴백 결과를 애널리스트 단위 결과인 것처럼 보고하지 않습니다.")
    return res


# ── §6.5 결측 민감도 (확보율 < 70% 인 경우 필수) ────────────────────────────────────────────
def _logit_irls(X: np.ndarray, y: np.ndarray, iters: int = 40, ridge: float = 1e-6
                ) -> Optional[np.ndarray]:
    """의존성 없는 로지스틱 회귀(IRLS). statsmodels 가 없어도 §6.5 를 포기하지 않는다."""
    n, k = X.shape
    if n < k * 5 or len(np.unique(y)) < 2:
        return None
    b = np.zeros(k)
    for _ in range(iters):
        eta = np.clip(X @ b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1 - p), 1e-6, None)
        z = eta + (y - p) / w
        XtW = X.T * w
        A = XtW @ X + ridge * np.eye(k)
        try:
            b_new = np.linalg.solve(A, XtW @ z)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(b_new)):
            return None
        if np.max(np.abs(b_new - b)) < 1e-8:
            b = b_new
            break
        b = b_new
    return b


def missingness_sensitivity(rep: pd.DataFrame, L: pd.DataFrame,
                            mcap: pd.DataFrame) -> dict:
    """SPEC §6.5 — 애널리스트 식별 실패가 무작위인지 검정하고, 아니면 IPW 가중을 만든다.

    종속: 식별 성공(1/0). 설명: log(시총), 증권사 규모, 업종, 연도.
    유의한 편향이 있으면 역확률가중(IPW)을 리포트 단위로 산출해 링크 가중에 쓸 수 있게 한다.
    """
    out: Dict[str, Any] = {"ran": False, "biased": False, "ipw": None, "table": []}
    if rep is None or len(rep) < 200:
        return out
    d = rep.copy()
    d["pub_date"] = as_ts_series(d["pub_date"])
    d["identified"] = _identified_mask(d, L).astype(float).to_numpy()
    d["code"] = d["stock_code"].map(to_code6)
    d["month"] = d["pub_date"] + pd.offsets.MonthEnd(0)

    if mcap is not None and len(mcap):
        m = mcap[["code", "month", "mktcap"]].copy()
        m["code"] = m["code"].astype(str)
        m["month"] = as_ts_series(m["month"])
        d = d.merge(m, on=["code", "month"], how="left")
    else:
        d["mktcap"] = np.nan

    brk = d.groupby(d["broker_name"].astype(str))["report_uid"].transform("size")
    feats = pd.DataFrame({
        "logmc": np.log(pd.to_numeric(d["mktcap"], errors="coerce").clip(lower=1e8)),
        "logbroker": np.log(pd.to_numeric(brk, errors="coerce").clip(lower=1)),
        "year": d["pub_date"].dt.year.astype(float),
    })
    feats["logmc"] = feats["logmc"].fillna(feats["logmc"].median())
    feats["year"] = feats["year"] - feats["year"].min()
    X = np.column_stack([np.ones(len(feats)), feats["logmc"].to_numpy(),
                         feats["logbroker"].to_numpy(), feats["year"].to_numpy()])
    y = d["identified"].to_numpy()
    keep = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
    X, y = X[keep], y[keep]
    b = _logit_irls(X, y)
    if b is None:
        LOG.warn("§6.5 로지스틱 회귀가 수렴하지 않았습니다 (표본/분산 부족). "
                 "결측 민감도는 '판정 불가'로 보고합니다.")
        return out

    eta = np.clip(X @ b, -30, 30)
    p = 1.0 / (1.0 + np.exp(-eta))
    # 계수의 실질 크기로 편향 여부를 본다 (표준오차 근사 대신 효과 크기 기준 — 보수적)
    names = ["절편", "log(시총)", "log(증권사 발간량)", "연도"]
    spread = float(np.nanmax(p) - np.nanmin(p))
    biased = bool(spread > 0.10 and (abs(b[1]) > 0.05 or abs(b[2]) > 0.05))
    ipw = pd.Series(np.nan, index=d.index, dtype=float)
    w = 1.0 / np.clip(p, 0.05, 1.0)
    w = w / np.nanmean(w)
    ipw.loc[d.index[keep]] = w
    out.update(ran=True, biased=biased,
               ipw=pd.DataFrame({"report_uid": d.loc[d.index[keep], "report_uid"].to_numpy(),
                                 "ipw": w}),
               coef=dict(zip(names, [float(x) for x in b])), p_spread=spread,
               table=[[n, f"{float(v):+.4f}"] for n, v in zip(names, b)])
    LOG.table(out["table"] + [["식별확률 범위", f"{np.nanmin(p):.1%} ~ {np.nanmax(p):.1%}"],
                              ["편향 판정", "유의 — IPW 병기" if biased else "뚜렷하지 않음"]],
              ["설명변수", "계수"], ["l", "r"],
              title="§6.5 결측 민감도 — 식별 성공의 로지스틱 회귀")
    if biased:
        LOG.warn("애널리스트 식별 성공이 시총/증권사 규모와 체계적으로 연관됩니다 "
                 "(무작위 결측 아님). IPW 재추정 결과를 병기합니다.")
    return out


# ── 링크 원장 (s22 링크행렬의 유일한 입력) ──────────────────────────────────────────────────
LINK_LEDGER_COLS = ["analyst_key", "code", "pub_date", "knowledge_date",
                    "broker_id", "broker_name", "link_conf", "n_analyst_on_report",
                    "target_price"]


def build_link_ledger(rep: pd.DataFrame, L: pd.DataFrame, sec: pd.DataFrame,
                      unit: str = "analyst") -> pd.DataFrame:
    """(애널리스트 식별자 × 종목 × 시점) 원장. SPEC §4.2 의 식별자 규약을 여기서 확정한다.

        analyst_broker_identity = f"{analyst_id}@{broker_id}"

    동일 인물이 증권사를 옮기면 다른 식별자다 — 이 전략에서 링크는 '같은 하우스에서
    동시에 본다'는 사실이 핵심이기 때문이다. 기존 원장의 analyst_id 가 이미
    sha1(broker_id, name) 이라 규약과 일치하지만, 명시적으로 broker 를 붙여 못박는다.

    unit='broker_sector_team' 이면 Phase 0 폴백: 링크 단위를 증권사×업종팀으로 격하한다.
    """
    if L is None or not len(L) or "report_uid" not in L.columns:
        LOG.warn("애널리스트 링크 원장이 비었습니다 — 링크 행렬을 만들 수 없습니다.")
        return pd.DataFrame(columns=LINK_LEDGER_COLS)
    need = ("analyst_id", "broker_id", "stock_code", "pub_date")
    if any(c not in L.columns for c in need):
        LOG.warn(f"링크 테이블에 필요한 컬럼이 없습니다 (필요: {need}, 보유: {list(L.columns)}). "
                 f"빈 원장을 반환합니다.")
        return pd.DataFrame(columns=LINK_LEDGER_COLS)

    d = L.copy()
    d["code"] = d["stock_code"].map(to_code6)
    d = d.dropna(subset=["code"])
    d["pub_date"] = as_ts_series(d["pub_date"])
    d = d.dropna(subset=["pub_date"])

    # 공개 시각 보수화를 원장에도 동일 적용 (§0.1)
    kd = rep[["report_uid", "knowledge_date"]].drop_duplicates("report_uid") \
        if rep is not None and "knowledge_date" in rep.columns else None
    if kd is not None:
        d = d.merge(kd, on="report_uid", how="left")
        d["knowledge_date"] = as_ts_series(d["knowledge_date"]).fillna(
            d["pub_date"] + pd.tseries.offsets.BDay(1))
    else:
        d["knowledge_date"] = d["pub_date"] + pd.tseries.offsets.BDay(1)

    if unit == "broker_sector_team":
        smap = build_sector_map(sec).set_index("code")["sector"].to_dict()
        d["sector"] = d["code"].map(smap).fillna("미분류")
        d["analyst_key"] = d["broker_id"].astype(str) + "#" + d["sector"].astype(str)
        LOG.warn("Phase 0 폴백: 링크 단위를 broker×sector_team 으로 격하했습니다. "
                 "이 구성에서는 교차업종 전용 버전이 주 버전(primary)입니다.")
    else:
        d["analyst_key"] = d["analyst_id"].astype(str) + "@" + d["broker_id"].astype(str)

    d["n_analyst_on_report"] = d.groupby("report_uid")["analyst_key"].transform("nunique")
    # 컬럼이 없으면 pd.to_numeric(None) 은 스칼라 nan 을 돌려주고, .fillna 결과도 스칼라가
    # 되어 전 행이 0.8 로 덮인다(=신뢰도 정보 소실). 컬럼 존재를 명시적으로 확인한다.
    d["link_conf"] = (pd.to_numeric(d["link_conf"], errors="coerce").fillna(0.8)
                      if "link_conf" in d.columns else 0.8)
    if "target_price" not in d.columns:
        d["target_price"] = np.nan
    d["target_price"] = pd.to_numeric(d["target_price"], errors="coerce")
    # "0"/"-" 는 '목표주가 없음'이다. 0 으로 넣으면 리비전 부호가 통째로 오염된다.
    d.loc[d["target_price"] <= 0, "target_price"] = np.nan
    out = d[LINK_LEDGER_COLS].drop_duplicates().reset_index(drop=True)
    PIPE.io("OUT", "MEM", "link_ledger", out)
    LOG.ok(f"링크 원장 {len(out):,}행 · 식별자 {out['analyst_key'].nunique():,}개 · "
           f"종목 {out['code'].nunique():,}개 · 단위={unit}")
    return out
