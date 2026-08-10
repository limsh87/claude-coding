

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  축 A — 애널리스트 텍스트톤 (§5)                                                     ║
# ║                                                                                          ║
# ║  경제적 근거: 애널리스트는 정성적 판단을 서술문에 먼저 반영하고 목표주가·투자의견은          ║
# ║  지연 갱신한다(비동기적 업데이트). 저커버리지 소형주일수록 이 텍스트를 읽는 투자자가 적다.   ║
# ║                                                                                          ║
# ║  ★★ 이 축의 성립 조건은 '텍스트 톤이 컨센서스 수정과 독립적인 정보' 라는 것이다.            ║
# ║     아니면 이 전략은 '애널리스트 과소반응 전략'의 재포장에 불과하다.                        ║
# ║     그래서 직교화(§5.3)는 선택이 아니라 전략 성립의 필요조건이며, 여기서 강제된다.           ║
# ║                                                                                          ║
# ║  ★★ LLM API 호출 금지(§5.1). 토큰 비용 문제이자, 사전학습 코퍼스로 인한 룩어헤드 오염       ║
# ║     위험 때문이다. 2016년 리포트를 2024년까지 학습한 모델로 채점하면 그 자체가 미래정보다.   ║
# ║     이 파일은 TF-IDF + (NB | LogReg) 만 쓰며, A18 계약검정이 소스에서 이를 검사한다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 정형 텍스트 제거 사전 (§5.1) ────────────────────────────────────────────────────────────
#   ★ 왜 이게 필수인가: 면책조항·컴플라이언스 문구는 증권사마다 고정 문구다. 제거하지 않으면
#     분류기가 "이 문장 패턴 = 미래에셋" 을 학습하고, 결국 '증권사 식별자'로 톤을 예측하게 된다.
#     증권사는 커버 종목군과 상관되므로 이건 곧 종목 고정효과 누출이다.
TONE_BOILERPLATE_PAT = [
    r"본\s*(조사분석)?자료는[^.\n]{0,200}[.\n]",
    r"당사는[^.\n]{0,60}(이해관계|보유하고|계열회사|발행주식)[^.\n]{0,140}[.\n]",
    r"(동\s*)?자료는\s*투자자[^.\n]{0,160}[.\n]",
    r"본\s*자료에\s*게재된\s*내용[^.\n]{0,160}[.\n]",
    r"Compliance\s*Notice[^\n]{0,400}",
    r"준법감시인?\s*(확인|심사)[^\n]{0,120}",
    r"투자등급\s*(관련사항|정의|및\s*적용기준)[^\n]{0,400}",
    r"(Strong\s*)?Buy\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"(Marketperform|Hold|중립)\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"(Underperform|Sell|매도)\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"최근\s*[12]년간\s*투자등급[^\n]{0,300}",
    r"당사\s*리서치센터[^\n]{0,120}",
    r"기업\s*투자의견은[^\n]{0,200}",
    r"본\s*보고서는\s*고객[^\n]{0,200}",
    r"어떠한\s*경우에도\s*(고객|투자자)의[^\n]{0,160}",
    r"무단\s*(복제|전재|배포)[^\n]{0,120}",
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",          # 애널리스트 서명부 이메일
    r"(02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}",             # 전화번호
    r"[가-힣]{2,4}\s*(연구원|애널리스트|수석|책임|선임|팀장|센터장)\s*$",
]
_TONE_BP_RE = re.compile("|".join(TONE_BOILERPLATE_PAT), re.I | re.M)

# 표·차트 잔재 라인 (숫자 비중이 높은 줄). 문장이 아니므로 톤 학습에서 제외한다.
_TONE_NUMLINE_RE = re.compile(r"^[\s\d,.\-%()＋+~/|]+$")
_TONE_SENT_SPLIT = re.compile(r"(?<=[.。!?])\s+|(?<=[다요])\.\s+|\n{1,}")

TONE_REPORT_COLS = ["report_uid", "code", "pub_date", "TONE_report", "n_sent",
                    "event_date", "knowledge_date"]
TONE_Q_COLS = ["code", "asof", "q", "TONE", "n_reports_q"]

_TONE_STATE: Dict[str, Any] = {"fits": 0, "backend": "", "warned": False}


def tone_clean_report_text(txt: str) -> str:
    """정형 텍스트 제거 + 표 잔재 제거. 제거하지 않으면 증권사 식별자로 누출된다."""
    if not txt:
        return ""
    t = unicodedata.normalize("NFKC", str(txt))
    t = _TONE_BP_RE.sub(" ", t)
    keep = []
    for ln in t.split("\n"):
        s = ln.strip()
        if not s or len(s) < 8:
            continue
        if _TONE_NUMLINE_RE.match(s):
            continue
        # 숫자·기호 비중이 과반이면 표의 잔재로 본다
        d = sum(1 for ch in s if ch.isdigit() or ch in ",.%()-+|/")
        if d / max(len(s), 1) > 0.45:
            continue
        keep.append(s)
    return "\n".join(keep)


def tone_sentences(txt: str) -> List[str]:
    """한국어 문장 분리. 8~400자만 채택."""
    if not txt:
        return []
    out = []
    for s in _TONE_SENT_SPLIT.split(txt):
        s = re.sub(r"\s+", " ", str(s)).strip()
        if 8 <= len(s) <= 400 and re.search(r"[가-힣]{2,}", s):
            out.append(s)
    return out


# ── 라벨: 발간일 기준 2일 CAR (시장수익률 차감) 의 부호 ─────────────────────────────────────
def _tone_market_excess(px_daily: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """일별 초과수익(종목 - 해당 시장 동일가중 평균) 과 2일 누적 전방 초과수익.

    ★ 시장수익률로 지수(KOSPI/KOSDAQ)를 쓰지 않고 '해당 시장 상장종목의 동일가중 평균'을 쓴다.
      지수는 시총가중이라 대형주 움직임이 지배하는데, 우리 표본은 소형주다. 소형주 리포트의
      2일 반응을 대형주 지수로 차감하면 시장 전체가 오른 날의 소형주 리포트가 전부
      '부정' 라벨을 받는다(라벨 노이즈가 아니라 라벨 편향이다).
    """
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=["code", "date", "car2"])
    d = px_daily[["code", "date", "close"]].dropna(subset=["code", "date", "close"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    d["ret1"] = d.groupby("code", observed=True)["close"].pct_change()
    d = d[np.isfinite(d["ret1"]) & (d["ret1"].abs() < 0.9)]     # 액면분할 등 이상치 제거
    mk = (sec.drop_duplicates("code").set_index("code")["market"].astype(str).to_dict()
          if sec is not None and len(sec) and "market" in sec.columns else {})
    d["market"] = d["code"].map(mk).fillna("KOSPI").astype(str)
    mret = d.groupby(["market", "date"], observed=True)["ret1"].transform("mean")
    d["exc"] = d["ret1"] - mret
    g = d.groupby("code", observed=True)["exc"]
    # 발간 다음 거래일부터 2거래일 누적 (발간 당일은 이미 반영됐을 수 있어 제외)
    d["car2"] = g.shift(-1).fillna(0) + g.shift(-2).fillna(0)
    d["car2"] = d["car2"].where(g.shift(-2).notna())
    return d[["code", "date", "car2"]]


def build_tone_training(rep_text: pd.DataFrame, px_daily: pd.DataFrame,
                        sec: pd.DataFrame, max_sent_per_report: int = 22,
                        max_total: int = 400_000) -> pd.DataFrame:
    """문장 단위 학습표본. 라벨 = 발간일 기준 2일 CAR(시장 차감)의 부호.

    ★ 학습 데이터는 U-1000 한정이 아니다(§5.1). 대형주 리포트도 쓴다 — 문장-톤 사전을
      배우는 것이 목적이지 종목 선택이 목적이 아니기 때문이다. 표본을 소형주로 좁히면
      문장 수가 급감해 분류기가 학습되지 않는다.
    """
    cols = ["sentence", "label", "pub_date", "report_uid", "code"]
    if rep_text is None or rep_text.empty:
        LOG.warn("리포트 본문이 없어 TONE 학습표본을 만들 수 없습니다 — 축 A 비활성화 대상입니다.")
        return pd.DataFrame(columns=cols)

    car = _tone_market_excess(px_daily, sec)
    if car.empty:
        LOG.warn("가격 데이터가 없어 CAR 라벨을 만들 수 없습니다 — 축 A 비활성화 대상입니다.")
        return pd.DataFrame(columns=cols)

    R = rep_text[["report_uid", "code", "pub_date", "text"]].dropna(subset=["pub_date"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R["code"] = R["code"].map(to_code6)
    R = R.dropna(subset=["code"])
    if R.empty:
        LOG.warn("본문이 있는 리포트 중 종목코드가 붙은 건이 없습니다 — 라벨을 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)

    # 발간일 → 그 이후 첫 거래일의 car2 를 as-of 결합 (forward)
    R = R.sort_values("pub_date", kind="stable")
    C = car.dropna(subset=["car2"]).sort_values("date", kind="stable")
    R["code"] = R["code"].astype(str)
    C["code"] = C["code"].astype(str)
    try:
        M = pd.merge_asof(R, C, left_on="pub_date", right_on="date", by="code",
                          direction="forward", tolerance=pd.Timedelta(days=7))
    except Exception as e:                                        # noqa
        LOG.warn(f"CAR 결합 실패({type(e).__name__}) — 축 A 를 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    M = M.dropna(subset=["car2"])
    if M.empty:
        LOG.warn("CAR 을 붙일 수 있는 리포트가 없습니다(가격 구간 불일치).")
        return pd.DataFrame(columns=cols)
    M["label"] = (M["car2"] > 0).astype("int8")

    rng = np.random.default_rng(SEED)
    rows: List[dict] = []
    for uid, code, pdte, txt, lab in zip(M["report_uid"], M["code"], M["pub_date"],
                                         M["text"], M["label"]):
        sents = tone_sentences(tone_clean_report_text(str(txt)))
        if len(sents) < ARC_TONE_MIN_SENT:
            continue
        if len(sents) > max_sent_per_report:
            idx = rng.choice(len(sents), size=max_sent_per_report, replace=False)
            sents = [sents[i] for i in sorted(idx)]
        for s in sents:
            rows.append({"sentence": s, "label": int(lab), "pub_date": pdte,
                         "report_uid": uid, "code": code})
    if not rows:
        LOG.warn("문장을 한 개도 추출하지 못했습니다 — PDF 텍스트 레이어가 없는 스캔본일 수 있습니다.")
        return pd.DataFrame(columns=cols)
    T = pd.DataFrame(rows)
    if len(T) > max_total:
        # 최근 표본을 우선 남긴다(확장윈도우에서 어차피 과거는 다 쓰이고, RAM 은 유한하다)
        T = T.sort_values("pub_date", kind="stable").tail(max_total)
    pos = float(T["label"].mean())
    LOG.ok(f"TONE 학습표본 {len(T):,}문장 · 리포트 {T['report_uid'].nunique():,}건 · "
           f"양(+) 라벨 비중 {100*pos:.1f}%")
    if not (0.30 <= pos <= 0.70):
        LOG.warn(f"라벨 불균형이 큽니다(양 라벨 {100*pos:.1f}%). 분류기가 다수 클래스로 쏠려 "
                 f"TONE 이 상수에 가까워질 수 있습니다 — class_weight 로 보정합니다.")
    PIPE.io("OUT", "MEM", "tone_training", T)
    return T


# ── 순수 numpy Multinomial NB (sklearn 부재 시 폴백) ────────────────────────────────────────
class _ToneNaiveBayes:
    """해시 기반 bag-of-words + Multinomial NB. sklearn 이 없어도 축 A 가 죽지 않게 한다.

    ★ 해싱을 쓰는 이유: 어휘 사전을 유지하면 확장윈도우 재학습마다 사전이 달라져
      과거 모델과 현재 모델의 피처 공간이 어긋난다. 해싱은 항상 같은 공간을 준다.
    """

    def __init__(self, n_features: int = 2 ** 18, alpha: float = 0.2):
        self.D = int(n_features)
        self.alpha = float(alpha)
        self.logp: Optional[np.ndarray] = None
        self.prior = np.array([0.5, 0.5])

    @staticmethod
    def _toks(s: str) -> List[str]:
        return [w for w in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", str(s))]

    @staticmethod
    def _h(w: str) -> int:
        """★ 파이썬 내장 hash() 를 쓰면 안 된다. CPython 의 문자열 해시는 PYTHONHASHSEED
        기반으로 **프로세스마다 랜덤화**되므로, 같은 코드·같은 SEED·같은 캐시로 두 번 돌리면
        해시 충돌 패턴이 달라져 문장 라벨 → TONE_report → dTONE → FINAL_RANK → 보유 종목까지
        전부 달라진다. random.seed / np.random.seed 는 여기에 영향을 주지 않고, 계약검정
        A14(결정성)는 동일 프로세스 안에서 돌아 이 문제를 절대 잡지 못한다."""
        return int.from_bytes(hashlib.blake2b(w.encode("utf-8", "ignore"),
                                              digest_size=8).digest(), "little")

    def _idx(self, s: str) -> np.ndarray:
        t = self._toks(s)
        if not t:
            return np.empty(0, dtype=np.int64)
        return np.fromiter((self._h(w) % self.D for w in t), dtype=np.int64, count=len(t))

    def fit(self, X: Sequence[str], y: Sequence[int]):
        cnt = np.zeros((2, self.D), dtype=np.float64)
        n = np.zeros(2, dtype=np.float64)
        for s, lab in zip(X, y):
            i = int(lab)
            n[i] += 1
            ids = self._idx(s)
            if len(ids):
                np.add.at(cnt[i], ids, 1.0)
        cnt += self.alpha
        self.logp = np.log(cnt / cnt.sum(axis=1, keepdims=True))
        tot = max(n.sum(), 1.0)
        self.prior = np.log(np.maximum(n, 1.0) / tot)
        return self

    def predict(self, X: Sequence[str]) -> np.ndarray:
        if self.logp is None:
            return np.zeros(len(X), dtype=np.int8)
        out = np.zeros(len(X), dtype=np.int8)
        for k, s in enumerate(X):
            ids = self._idx(s)
            if len(ids) == 0:
                out[k] = 1
                continue
            sc = self.prior + np.array([self.logp[0][ids].sum(), self.logp[1][ids].sum()])
            out[k] = int(sc[1] > sc[0])
        return out


def fit_tone_expanding(train: pd.DataFrame, cut) -> Optional[Tuple[Any, Any]]:
    """cut '이전' 데이터로만 학습한 (vectorizer, model). 표본 부족이면 None.

    ★ 확장윈도우가 이 전략의 룩어헤드 방어선이다. 전체 기간 단일 학습은 2016년 문장을
      2026년 사전으로 채점하는 것이며, 그것만으로 IC 가 크게 부풀려진다.
    """
    if train is None or train.empty:
        return None
    c = as_ts(cut)
    sub = train[as_ts_series(train["pub_date"]) < c]
    if len(sub) < ARC_TONE_MIN_TRAIN or sub["label"].nunique() < 2:
        return None
    X = sub["sentence"].astype(str).tolist()
    y = sub["label"].astype(int).to_numpy()

    kind = str(globals().get("ARC_TONE_MODEL", "logreg")).lower()
    if sk_tfidf is not None and (sk_logreg is not None or sk_nb is not None):
        try:
            vec = sk_tfidf(analyzer="word", token_pattern=r"[가-힣]{2,}|[A-Za-z]{3,}",
                           ngram_range=(1, 2), min_df=3,
                           max_features=int(ARC_TONE_MAX_FEATURES), sublinear_tf=True)
            Xm = vec.fit_transform(X)
            if kind == "lgbm" and lgbm is not None:
                mdl = lgbm.LGBMClassifier(n_estimators=200, num_leaves=31, learning_rate=0.08,
                                          verbose=-1, random_state=SEED)
                mdl.fit(Xm, y)
            elif kind == "nb" and sk_nb is not None:
                mdl = sk_nb(alpha=0.3).fit(Xm, y)
            else:
                mdl = sk_logreg(max_iter=300, C=1.0, solver="liblinear",
                                class_weight="balanced", random_state=SEED).fit(Xm, y)
            _TONE_STATE["backend"] = f"sklearn/{kind}"
            _TONE_STATE["fits"] += 1
            return (vec, mdl)
        except Exception as e:                                    # noqa
            LOG.debug(f"sklearn TONE 학습 실패({type(e).__name__}) — 순수 numpy NB 로 폴백")
    mdl = _ToneNaiveBayes().fit(X, y)
    _TONE_STATE["backend"] = "numpy/NB(해싱)"
    _TONE_STATE["fits"] += 1
    if not _TONE_STATE["warned"]:
        _TONE_STATE["warned"] = True
        LOG.warn("scikit-learn 이 없어 순수 numpy Multinomial NB 로 톤을 분류합니다. "
                 "실행은 정상이나 분류 성능이 열화되며, 그만큼 축 A 의 IC 가 낮게 나옵니다. "
                 "이 사실을 결과 해석에 반드시 반영하세요.")
    return (None, mdl)


def _tone_predict(fit: Tuple[Any, Any], sents: Sequence[str]) -> np.ndarray:
    vec, mdl = fit
    if vec is not None:
        try:
            return np.asarray(mdl.predict(vec.transform(list(sents)))).astype(int)
        except Exception:
            return np.ones(len(sents), dtype=int)
    return np.asarray(mdl.predict(list(sents))).astype(int)


def score_tone_reports(rep_text: pd.DataFrame, train: pd.DataFrame,
                       rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """§5.1 확장윈도우 재학습 + §5.2 리포트 단위 TONE.

    TONE(report) = (긍정문장 수 − 부정문장 수) / 전체문장 수  ∈ [-1, +1]

    ★ 성능: 리밸일마다 매번 재학습하면 40회 × 수십 초다. 학습표본이 직전 학습 대비
      15% 이상 늘었을 때만 재학습하고 그 외에는 직전 모델을 재사용한다.
      재사용해도 '그 시점 이전 데이터로만 학습된 모델' 이라는 성질은 그대로 유지된다
      (더 오래된 모델을 쓰는 것이므로 오히려 보수적이다).
    """
    if rep_text is None or rep_text.empty or train is None or train.empty:
        return pd.DataFrame(columns=TONE_REPORT_COLS)

    R = rep_text[["report_uid", "code", "pub_date", "text"]].dropna(subset=["pub_date"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R["code"] = R["code"].map(to_code6)
    R = R.dropna(subset=["code"]).sort_values("pub_date", kind="stable")

    cuts = [as_ts(t) for t in rebals]
    if not cuts:
        return pd.DataFrame(columns=TONE_REPORT_COLS)

    rows: List[dict] = []
    fit = None
    last_n = 0
    tr_dates = as_ts_series(train["pub_date"])
    t0 = time.time()
    for i, cut in enumerate(tqdm(cuts, desc="TONE 확장윈도우", ncols=88, leave=False)):
        n_avail = int((tr_dates < cut).sum())
        if fit is None or n_avail > last_n * 1.15:
            f = fit_tone_expanding(train, cut)
            if f is not None:
                fit, last_n = f, n_avail
        if fit is None:
            continue
        hi = cuts[i + 1] if i + 1 < len(cuts) else (as_ts(BACKTEST_END) + pd.Timedelta(days=1))
        win = R[(R["pub_date"] >= cut) & (R["pub_date"] < hi)]
        if win.empty:
            continue
        for uid, code, pdte, txt in zip(win["report_uid"], win["code"],
                                        win["pub_date"], win["text"]):
            sents = tone_sentences(tone_clean_report_text(str(txt)))
            if len(sents) < ARC_TONE_MIN_SENT:
                continue
            yp = _tone_predict(fit, sents)
            n = len(yp)
            tone = float((int((yp == 1).sum()) - int((yp == 0).sum())) / max(n, 1))
            rows.append({"report_uid": uid, "code": code, "pub_date": pdte,
                         "TONE_report": tone, "n_sent": n})

    # ★ 첫 리밸일 이전에 발간된 리포트는 '그 시점 이전 데이터'가 없어 채점할 수 없다.
    #   억지로 채점하면 미래 모델로 과거를 채점하는 것이 되므로 결측으로 남긴다.
    if not rows:
        LOG.warn("확장윈도우로 채점된 리포트가 없습니다 (학습 표본 부족). 축 A 는 결측 처리됩니다.")
        return pd.DataFrame(columns=TONE_REPORT_COLS)
    T = pd.DataFrame(rows)
    T["event_date"] = T["pub_date"]
    # §4 리포트는 발간일 + 1거래일부터 사용 가능
    T["knowledge_date"] = T["pub_date"] + pd.Timedelta(days=ARC_REPORT_LAG_DAYS)
    LOG.ok(f"TONE 채점 {len(T):,}건 · 모델 재학습 {_TONE_STATE['fits']}회 "
           f"({_TONE_STATE['backend']}) · 소요 {time.time()-t0:.1f}초 · "
           f"TONE 평균 {T['TONE_report'].mean():+.3f} 표준편차 {T['TONE_report'].std():.3f}")
    PIPE.io("OUT", "MEM", "tone_reports", T)
    return T


def aggregate_tone(tone_rep: pd.DataFrame, rebals: pd.DatetimeIndex,
                   half_life_days: Optional[float] = None) -> pd.DataFrame:
    """§5.2 분기 집계 — 최신성 가중평균. 가중치 = exp(−λ·경과일수), 반감기 30일 고정.

    ★ 창은 '리밸일 직전 1개 분기'. 리밸일 당일 발간분은 T+1 규약상 아직 못 쓴다.
    """
    hl = float(half_life_days or ARC_TONE_HALFLIFE_D)
    lam = math.log(2.0) / max(hl, 1e-6)
    if tone_rep is None or tone_rep.empty:
        return pd.DataFrame(columns=TONE_Q_COLS)
    X = tone_rep.dropna(subset=["code", "TONE_report"]).copy()
    X["knowledge_date"] = as_ts_series(X["knowledge_date"])
    X = X.dropna(subset=["knowledge_date"])
    out = []
    for t in rebals:
        t = as_ts(t)
        lo = t - pd.DateOffset(months=3)
        w = X[(X["knowledge_date"] > lo) & (X["knowledge_date"] <= t)].copy()
        if w.empty:
            continue
        age = (t - w["knowledge_date"]).dt.days.clip(lower=0).to_numpy(dtype=float)
        w["_wt"] = np.exp(-lam * age)
        w["_num"] = w["_wt"] * pd.to_numeric(w["TONE_report"], errors="coerce")
        g = w.groupby("code", observed=True)
        agg = pd.DataFrame({"TONE": g["_num"].sum() / g["_wt"].sum(),
                            "n_reports_q": g["report_uid"].nunique()}).reset_index()
        agg["asof"] = t
        agg["q"] = prev_quarter_of(t)
        out.append(agg)
    if not out:
        return pd.DataFrame(columns=TONE_Q_COLS)
    Q = pd.concat(out, ignore_index=True)[TONE_Q_COLS]
    LOG.ok(f"분기 TONE 집계 {len(Q):,}행 ({Q['code'].nunique():,}종목 × {Q['asof'].nunique()}시점) "
           f"· 반감기 {hl:.0f}일 최신성 가중")
    return downcast(Q)


# ── §5.3 ΔTONE + 직교화 ─────────────────────────────────────────────────────────────────────
AXIS_A_COLS = ["TONE", "TONE_prev", "dTONE", "dTONE_resid", "n_reports_q", "has_axis_a"]


def attach_axis_a(P: pd.DataFrame, tone_q: pd.DataFrame,
                  rev: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """ΔTONE 산출 → 직교화 → dTONE_resid. §7.2 에 따라 축 A 결측 종목을 탈락시키지 않는다.

    통제변수(§5.3 표): EPS 컨센 수정률 / 목표주가 수정률 / 투자의견 변경 더미 /
                      12-1 모멘텀 / log(시총) / log(ADTV) / 섹터 더미
    """
    P = P.copy()
    if tone_q is None or tone_q.empty:
        LOG.warn("분기 TONE 이 없어 축 A 를 결측 처리합니다 (종목은 탈락시키지 않습니다 — §7.2).")
        P = ensure_cols(P, AXIS_A_COLS)
        P["has_axis_a"] = 0.0
        P["dTONE_resid"] = np.nan
        return P

    Q = tone_q[["code", "asof", "TONE", "n_reports_q"]].copy()
    Q["asof"] = as_ts_series(Q["asof"])
    P = P.merge(Q, on=["code", "asof"], how="left")

    # ΔTONE: 직전 리밸 시점 대비. 양 시점 모두 리포트 ≥1건일 때만 성립(§5.3).
    P = P.sort_values(["code", "asof"], kind="stable")
    g = P.groupby("code", observed=True)
    P["TONE_prev"] = g["TONE"].shift(1)
    prev_asof = g["asof"].shift(1)
    gap_m = ((P["asof"].dt.year - prev_asof.dt.year) * 12 +
             (P["asof"].dt.month - prev_asof.dt.month))
    adjacent = gap_m == 3
    prev_n = g["n_reports_q"].shift(1)
    ok = (adjacent & P["TONE"].notna() & P["TONE_prev"].notna() &
          (P["n_reports_q"].fillna(0) >= 1) & (prev_n.fillna(0) >= 1))
    P["dTONE"] = (P["TONE"] - P["TONE_prev"]).where(ok).astype("float32")
    P["has_axis_a"] = P["dTONE"].notna().astype("float32")

    # ── 통제변수 준비 ─────────────────────────────────────────────────────────────────────
    if rev is not None and len(rev):
        rv = rev[[c for c in ("code", "asof", "tp_rev", "opin_chg") if c in rev.columns]].copy()
        rv["asof"] = as_ts_series(rv["asof"])
        P = P.merge(rv, on=["code", "asof"], how="left")
    P = ensure_cols(P, ["tp_rev", "opin_chg", "eps_rev"])

    # eps_rev 대리변수 — [방법론적 한계] 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하다.
    # PIT 실적(TTM 순이익/자산)의 분기 변화율로 대리한다. '컨센서스 수정'이 아니라 '실현 실적
    # 변화'이므로 통제력이 약하다. 이 한계는 리포트에 명시된다(§9.1).
    if P["eps_rev"].isna().all() and "net_income_ttm" in P.columns:
        ni = safe_div(col(P, "net_income_ttm"), col(P, "assets"))
        P["eps_rev"] = (ni - ni.groupby(P["code"].astype(str)).shift(1)).astype("float32")
        LOG.info("EPS 컨센서스 시계열이 없어 PIT 실적(TTM 순이익/자산) 변화율을 대리변수로 씁니다 "
                 "[방법론적 한계 — 통제력이 컨센서스 수정률보다 약합니다].")

    ctrl = [c for c in ARC_TONE_CONTROLS if c in P.columns]
    # 섹터 더미 (원핫). 기간 내 단일 섹터면 특이행렬이 되므로 첫 섹터를 기준으로 뺀다.
    sec_d = pd.get_dummies(P["sector"].astype(str), prefix="sec", drop_first=True, dtype=float) \
        if "sector" in P.columns else pd.DataFrame(index=P.index)

    X = P[ctrl].apply(pd.to_numeric, errors="coerce")
    # ★ 통제변수 결측을 0 으로 두면 직교화가 그 행에서 무력화되어 통제 안 된 알파가 섞인다.
    #   기간 중앙값으로 대체하고 대체율을 로그로 남긴다.
    n_before = int(X.isna().sum().sum())
    for c in ctrl:
        med = X.groupby(P["q"].astype(str))[c].transform("median")
        X[c] = X[c].where(X[c].notna(), med)
        X[c] = X[c].where(X[c].notna(), X[c].median())
    n_after = int(X.isna().sum().sum())
    if n_before:
        LOG.info(f"직교화 통제변수 결측 {n_before:,}칸 중 {n_before - n_after:,}칸을 "
                 f"기간 중앙값으로 대체했습니다 (잔여 결측 {n_after:,}칸). "
                 f"대체율이 높으면 직교화 통제력이 약해집니다.")
    X = pd.concat([X, sec_d], axis=1).fillna(0.0)

    P["dTONE_resid"] = xsec_resid(P["dTONE"], X, P["q"].astype(str))
    n_ok = int(P["dTONE_resid"].notna().sum())
    n_raw = int(P["dTONE"].notna().sum())
    LOG.ok(f"ΔTONE 직교화 완료 — 원신호 {n_raw:,}행 → 잔차 {n_ok:,}행 "
           f"(통제변수 {len(ctrl)}개 + 섹터더미 {sec_d.shape[1]}개)")
    if n_raw and n_ok / max(n_raw, 1) < 0.7:
        LOG.warn(f"잔차 산출률이 {100*n_ok/max(n_raw,1):.0f}% 로 낮습니다. 기간별 표본이 12개 "
                 f"미만인 분기가 많다는 뜻이며, 그 분기의 축 A 는 통째로 결측입니다.")
    P = ensure_cols(P, AXIS_A_COLS)
    return P


def report_axis_a_ic(P: pd.DataFrame) -> dict:
    """§5.3 중간 검증 — 직교화 전/후 IC 를 나란히 보고한다. 이게 축 A 존속의 판정 근거다."""
    LOG.banner("축 A 중간 검증 — 직교화 전/후 IC (§5.3)",
               "차이가 크다면 알파 대부분이 기존 팩터(컨센 수정·모멘텀·사이즈)에서 온 것이다")
    out = {"ic_raw": np.nan, "icir_raw": np.nan, "ic_resid": np.nan, "icir_resid": np.nan,
           "n": 0, "verdict": ""}
    if P is None or P.empty or "fwd_ret_1q" not in P.columns:
        LOG.warn("패널이 비어 IC 를 계산할 수 없습니다.")
        out["verdict"] = "판정불가 — 표본 없음"
        return out
    rows = []
    for lab, cname in (("직교화 전 ΔTONE", "dTONE"), ("직교화 후 ΔTONE_resid", "dTONE_resid")):
        if cname not in P.columns:
            rows.append([lab, "—", "—", "—", "컬럼 없음"])
            continue
        ic, icir, n = info_coef(P[cname], P["fwd_ret_1q"], P["q"].astype(str))
        tstat = (icir if np.isfinite(icir) else np.nan)
        rows.append([lab, f"{ic:+.4f}" if np.isfinite(ic) else "—",
                     f"{icir:+.2f}" if np.isfinite(icir) else "—", f"{n}",
                     "유의" if np.isfinite(tstat) and abs(tstat) > 2 else "0과 구분 불가"])
        if cname == "dTONE":
            out["ic_raw"], out["icir_raw"] = ic, icir
        else:
            out["ic_resid"], out["icir_resid"], out["n"] = ic, icir, n
    LOG.table(rows, ["신호", "IC(기간평균 Spearman)", "IC-IR(≈t)", "기간수", "판정"],
              ["l", "r", "r", "r", "l"])

    ir, rr = out["ic_raw"], out["ic_resid"]
    if np.isfinite(ir) and np.isfinite(rr) and abs(ir) > 1e-9:
        shrink = 1.0 - (abs(rr) / abs(ir))
        LOG.info(f"직교화로 IC 의 {100*shrink:+.1f}% 가 사라졌습니다. "
                 f"이 비율이 크면 축 A 의 알파 상당 부분이 기존 팩터에서 온 것입니다.")
        out["shrink"] = float(shrink)
    if not np.isfinite(out["icir_resid"]) or abs(out["icir_resid"]) < 2.0:
        out["verdict"] = ("축 A 비활성화 권고 — 직교화 후 IC 가 0과 구분되지 않습니다. "
                          "§5.3 에 따라 축 B 단독(DART-ONLY) 모드를 주 결과로 삼는 것을 "
                          "검토해야 합니다. (자동으로 끄지 않고 보고만 합니다)")
        LOG.warn(out["verdict"])
    else:
        out["verdict"] = ("직교화 후에도 유의한 IC 가 남습니다 — 텍스트 고유 정보가 존재한다는 "
                          "이 백테스트의 실증 근거입니다.")
        LOG.ok(out["verdict"])
    return out
