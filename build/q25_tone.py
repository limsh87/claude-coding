

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q4  애널리스트 텍스트 TONE — 결측 허용 오버레이 (§6.2)  ·  인과 순서 점검 (§6.4)       ║
# ║                                                                                          ║
# ║  TONE(report) = (긍정문장 − 부정문장) / 전체문장,  ΔTONE(f,q) = TONE(f,q) − TONE(f,q−1)    ║
# ║  분류기: TF-IDF + Naive Bayes / Logistic Regression.  ★ LLM 사용 금지.                     ║
# ║  라벨: 발간일 2일 CAR 의 부호.  확장윈도우: 시점 t 예측에는 t 이전 데이터로만 학습한 모델.  ║
# ║                                                                                          ║
# ║  ★ 이 모듈에서 조용히 틀리기 가장 쉬운 세 곳 ────────────────────────────────────────      ║
# ║   ① 면책조항·컴플라이언스 문구를 안 지우면 그게 증권사 지문이 되어, 분류기가 감성이 아니라 ║
# ║      '어느 증권사인가'를 학습한다. 지웠는지 믿지 말고 '증권사 분류기 정확도가 기저율로     ║
# ║      무너지는지' 를 직접 측정해서 출력한다. 그 검증이 이 설계의 전부다.                     ║
# ║   ② 확장윈도우를 '연 단위로 한 번 학습'까지는 다들 하는데, 라벨(2일 CAR)이 미래를 보므로   ║
# ║      학습 표본의 컷오프는 '발간일 < 경계' 가 아니라 '발간일 + 2거래일 < 경계' 여야 한다.    ║
# ║   ③ 리포트 없는 종목의 ΔTONE_resid = 0 을 z-score '이전'에 주입하면, 결측이 다수인 구간의  ║
# ║      평균이 0 쪽으로 끌려가 리포트 보유 종목의 z 가 통째로 왜곡된다. 반드시 관측치만으로   ║
# ║      z 를 만든 뒤 결측에 0 을 넣는다.                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SK: Dict[str, Any] = {}


def ensure_sklearn() -> bool:
    """sklearn 지연 로드. 없으면 설치를 시도하고, 그래도 없으면 TONE 축만 비활성화한다
    (전략 전체는 중단하지 않는다 — §6.2 애널리스트 축은 결측 허용 오버레이다)."""
    if "ok" in _SK:
        return _SK["ok"]
    for attempt in (0, 1):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer      # type: ignore
            from sklearn.linear_model import LogisticRegression              # type: ignore
            from sklearn.naive_bayes import MultinomialNB                    # type: ignore
            from sklearn.model_selection import cross_val_score              # type: ignore
            _SK.update({"ok": True, "Tfidf": TfidfVectorizer, "LR": LogisticRegression,
                        "NB": MultinomialNB, "cvs": cross_val_score})
            return True
        except Exception:
            if attempt == 0:
                LOG.info("scikit-learn 설치 중 (TONE 분류기용, 1~2분)…")
                _pip_install(["scikit-learn"])
                try:
                    import importlib
                    importlib.invalidate_caches()
                except Exception:
                    pass
    _SK["ok"] = False
    LOG.warn("scikit-learn 을 쓸 수 없어 TONE 축을 비활성화합니다. §6.2 설계상 애널리스트 축은 "
             "'있으면 가점, 없으면 중립'이므로 ΔTONE_resid 는 전부 0(중립)이 되고 파이프라인은 "
             "정상 진행됩니다. Score2 는 사실상 ΔNONFIN 단독이 됩니다.")
    return False


# ── 정형 텍스트(면책조항/서명부) 제거 ───────────────────────────────────────────────────────
# ★ 패턴은 반드시 '문장 경계'에서 멈춰야 한다. [^\n]{0,400} 처럼 잡으면 PDF 추출 텍스트에
#   줄바꿈이 드물기 때문에 면책조항 한 줄이 뒤따르는 실제 분석 문장까지 통째로 지워버린다.
#   (리허설이 이 버그를 잡았다: 테스트 문장이 통째로 사라져 반환 길이가 0 이었다)
#   → 마침표/물음표/줄바꿈 앞까지만 소비한다.
_S = r"[^.。!?\n]{0,200}[.。!?]?"
_BOILER_PATTERNS = [
    r"본\s*자료는" + _S,
    r"동\s*자료는" + _S,
    r"당사는[^.。!?\n]{0,120}(?:책임|보증)" + _S,
    r"투자\s*판단의?\s*최종\s*책임" + _S,
    r"어떠한\s*경우에도" + _S,
    r"본\s*조사분석자료" + _S,
    r"compliance\s*notice" + _S,
    r"이\s*보고서는[^.。!?\n]{0,150}(?:작성|배포)" + _S,
    r"(?:기업|산업|시장)?\s*투자의견\s*분류" + _S,
    r"(?:Buy|Hold|Sell|매수|중립|매도)\s*[:：]\s*향후\s*\d+개월" + _S,
    r"자료\s*작성\s*일\s*현재" + _S,
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",           # 이메일(=애널리스트 지문)
    r"\(?\s*0\d{1,2}\s*\)?\s*[-\s.]?\d{3,4}[-\s.]?\d{4}",          # 전화번호
    r"[가-힣]{2,4}\s*(?:연구원|애널리스트|수석연구원|책임연구원|팀장|센터장)",
    r"(?:https?://|www\.)\S+",
    r"\d{4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}",                 # 날짜(발간일 지문화 방지)
]
_BOILER_RE = re.compile("|".join(_BOILER_PATTERNS), re.I)
# 증권사 사명 자체도 지운다 — 남겨두면 분류기가 감성 대신 사명을 학습한다.
_BROKER_TOKEN_RE = re.compile(
    "|".join(sorted({re.escape(n) for _p, n in BROKER_CANON}, key=len, reverse=True)) +
    r"|증권|리서치센터|리서치본부")


def strip_boilerplate(text: str) -> str:
    if not text:
        return ""
    t = _BOILER_RE.sub(" ", text)
    t = _BROKER_TOKEN_RE.sub(" ", t)
    t = re.sub(r"[^\w가-힣.!?%\s]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_KSENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=다)\s{1,}(?=[가-힣A-Z])|\n+")


def split_sentences_ko(text: str, max_sent: int = 400) -> List[str]:
    """한국어 문장 분리. 형태소 분석기 의존 없이 종결어미+구두점 휴리스틱으로 자른다.
    (konlpy/mecab 은 설치 실패율이 높고 Colab/윈도우에서 특히 취약해 의존하지 않는다)"""
    if not text:
        return []
    out = []
    for s in _KSENT_SPLIT.split(text):
        s = s.strip()
        if 8 <= len(s) <= 400:
            out.append(s)
        if len(out) >= max_sent:
            break
    return out


# ── 리포트 본문 테이블 ──────────────────────────────────────────────────────────────────────
TEXT_TRUNC = 4000          # 리포트당 저장 글자수 상한 (앞부분에 요약·투자포인트가 몰려 있다)
TRAIN_CAP_PER_YEAR = 8000  # 학습 코퍼스 상한(연). 전량을 다 쓰면 캐시가 수 GB 가 된다.


def build_report_text_table(rep: pd.DataFrame, need_codes: Optional[set] = None
                            ) -> pd.DataFrame:
    """리포트 PDF blob → 정제 본문 테이블. 한 번 만들면 재학습 때마다 재추출하지 않는다.

    수집 대상 = ① 학습 코퍼스(연도별 상한 표본, 전 종목 — §6.2 '학습 코퍼스는 국내 리포트 전량')
                 ② 채점 대상(U-200 합집합 종목의 전체 리포트)
    """
    cols = ["report_uid", "pub_date", "broker_id", "stock_code", "text", "n_sent", "is_irc"]
    if rep is None or rep.empty:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("research_report_text", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(cached["report_uid"].astype(str))
        LOG.info(f"캐시에서 리포트 본문 {len(cached):,}건 재사용 (재추출하지 않습니다)")

    R = rep.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["report_uid", "pub_date"])
    R["_y"] = R["pub_date"].dt.year

    # ① 학습 표본 — 연도별 결정적 샘플링(uid 해시 순). 실행마다 같은 표본이 나온다.
    R["_h"] = R["report_uid"].astype(str).map(lambda u: int(u[:8], 16) if len(str(u)) >= 8 else 0)
    train_pick = (R.sort_values(["_y", "_h"], kind="stable")
                   .groupby("_y", observed=True).head(TRAIN_CAP_PER_YEAR))
    want = set(train_pick["report_uid"].astype(str))
    # ② 채점 대상
    if need_codes:
        want |= set(R.loc[R["stock_code"].isin(need_codes), "report_uid"].astype(str))
    todo = R[R["report_uid"].astype(str).isin(want - done)]

    rows: List[dict] = []
    if len(todo) and (fitz is not None or pdfplumber is not None):
        idx = VAULT.load_index("shared")
        blob_uid: Dict[str, str] = {}
        if len(idx) and "domain" in idx.columns:
            sub = idx[(idx["domain"].astype(str) == "research") &
                      (idx["subtype"].astype(str) == "report_pdf")]
            blob_uid = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
        LOG.info(f"리포트 본문 추출 대상 {len(todo):,}건 "
                 f"(드라이브/로컬 blob 보유 {sum(1 for u in todo['report_uid'].astype(str) if u in blob_uid):,}건)")

        def _one(rec):
            uid, pdt, bid, code, title, irc = rec
            data = None
            bu = blob_uid.get(str(uid))
            if bu:
                data = VAULT.get_blob(bu, "shared")
            if not data:
                return None
            raw = pdf_text(data, max_pages=4)
            del data
            if not raw or len(raw) < 200:
                return None
            clean = strip_boilerplate(raw)[:TEXT_TRUNC]
            if len(clean) < 120:
                return None
            return {"report_uid": uid, "pub_date": pdt, "broker_id": bid, "stock_code": code,
                    "text": clean, "n_sent": len(split_sentences_ko(clean)), "is_irc": irc}

        irc_re = re.compile(IRC_TAG_PATTERN)
        jobs = list(zip(todo["report_uid"].astype(str), todo["pub_date"],
                        todo.get("broker_id", pd.Series([""] * len(todo))).astype(str),
                        todo["stock_code"],
                        todo.get("title", pd.Series([""] * len(todo))).astype(str),
                        (todo.get("broker_raw", pd.Series([""] * len(todo))).astype(str)
                         + " " + todo.get("title", pd.Series([""] * len(todo))).astype(str))
                        .map(lambda s: float(bool(irc_re.search(s))))))
        CHUNK = 4000
        for k0 in range(0, len(jobs), CHUNK):
            res = pmap_io(_one, jobs[k0:k0 + CHUNK], workers=min(N_WORKERS_IO, 8),
                          desc=f"리포트 본문 {k0//CHUNK+1}/{(len(jobs)-1)//CHUNK+1}")
            rows.extend([r for r in res if r])
            del res
            gc.collect()
    elif len(todo):
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 리포트 본문을 추출할 수 없습니다 — "
                 "TONE 축은 전부 중립(0)이 됩니다.")

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    T = pd.concat(frames, ignore_index=True).drop_duplicates("report_uid", keep="last")
    T["pub_date"] = as_ts_series(T["pub_date"])
    for c in cols:
        if c not in T.columns:
            T[c] = np.nan
    if rows:
        VAULT.put_table("research_report_text", T[cols], scope="shared", domain="research",
                        source="pdf text + boilerplate strip",
                        extra={"trunc": TEXT_TRUNC, "note": "정제 본문 — 전 전략 공용"})
    LOG.ok(f"리포트 본문 테이블 {len(T):,}건 "
           f"(평균 {pd.to_numeric(T['n_sent'], errors='coerce').mean():.0f}문장 · "
           f"IR협의회 태깅 {int(pd.to_numeric(T['is_irc'], errors='coerce').fillna(0).sum()):,}건)")
    PIPE.io("OUT", "DRIVE", "research_report_text", T, source="pdf")
    return T[cols]


# ── 라벨: 발간일 2일 시장조정 CAR ───────────────────────────────────────────────────────────
def build_car_labels(T: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """라벨 = 발간 직후 2거래일 시장조정 누적수익의 부호.

    ★ 시장조정을 '당일 횡단면 중앙값'으로 한다. 지수 데이터를 따로 받지 않아도 되고,
      같은 날 정보만 쓰므로 미래누수가 원천적으로 없다. 지수를 쓰면 KOSPI/KOSDAQ 소속을
      PIT 로 알아야 하는데 그 자체가 또 하나의 누수 표면이 된다.
    """
    if T is None or T.empty or px_daily is None or not len(px_daily):
        return pd.DataFrame(columns=["report_uid", "car2", "label"])
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"], kind="stable")
    g = px.groupby("code", observed=True)["close"]
    px["r2"] = g.shift(-2) / px["close"] - 1.0          # 발간 시점 t 종가 → t+2 종가
    px["mkt"] = px.groupby("date", observed=True)["r2"].transform("median")
    px["car2"] = px["r2"] - px["mkt"]
    px["label_date"] = px["date"]

    L = T[["report_uid", "pub_date", "stock_code"]].dropna(subset=["stock_code"]).copy()
    L = L.rename(columns={"stock_code": "code"})
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"]).sort_values("pub_date", kind="stable")
    R = px[["code", "date", "car2"]].rename(columns={"date": "px_date"}) \
          .sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="pub_date", right_on="px_date", by="code",
                      direction="forward", tolerance=pd.Timedelta(days=7))
    M = M.dropna(subset=["car2"])
    M["label"] = (M["car2"] > 0).astype(int)
    # 라벨이 실제로 확정되는 날 = 발간 매칭일 + 2거래일. 확장윈도우 컷오프는 이 날짜로 잰다.
    M["label_ready"] = next_trading_day_series(next_trading_day_series(M["px_date"]))
    LOG.ok(f"TONE 라벨 {len(M):,}건 (2일 시장조정 CAR · 양(+) 비율 {100*M['label'].mean():.1f}%)")
    return M[["report_uid", "car2", "label", "px_date", "label_ready"]]


# ── 정형문구 누출 검증 ──────────────────────────────────────────────────────────────────────
def verify_boilerplate_leak(T: pd.DataFrame, sample: int = 6000) -> dict:
    """정제 텍스트로 '증권사 맞히기' 분류기를 학습시켜 본다.

    정확도가 기저율(최빈 증권사 비율) 근처로 무너져야 정상이다. 높게 나오면 아직 증권사
    지문이 남아 있다는 뜻이고, 그 상태의 TONE 은 감성이 아니라 증권사 더미를 학습한 것이다.
    """
    if not ensure_sklearn() or T is None or len(T) < 500:
        return {}
    d = T.dropna(subset=["text", "broker_id"])
    d = d[d["broker_id"].astype(str).str.len() > 0]
    if len(d) < 500:
        return {}
    vc = d["broker_id"].value_counts()
    keep = vc[vc >= 40].index
    d = d[d["broker_id"].isin(keep)]
    if d["broker_id"].nunique() < 3 or len(d) < 500:
        return {}
    if len(d) > sample:
        d = d.sample(sample, random_state=SEED)
    base = float(d["broker_id"].value_counts(normalize=True).max())
    try:
        vec = _SK["Tfidf"](analyzer="char_wb", ngram_range=(2, 4), min_df=5,
                           max_features=60000, sublinear_tf=True)
        X = vec.fit_transform(d["text"].astype(str))
        y = d["broker_id"].astype(str).to_numpy()
        acc = float(np.mean(_SK["cvs"](_SK["LR"](max_iter=400, C=1.0), X, y, cv=3,
                                       scoring="accuracy")))
    except Exception as e:                                     # noqa
        LOG.warn(f"정형문구 누출 검증 실패({type(e).__name__}) — 검증 없이 진행하지만, "
                 f"TONE 결과 해석 시 증권사 지문 잔존 가능성을 감안하세요.")
        return {}
    verdict = ("✔ 기저율 수준 — 증권사 지문이 사실상 제거됨" if acc < base + 0.10 else
               "❗ 지문 잔존 — 분류기가 감성 대신 증권사를 학습할 위험")
    LOG.table([["증권사 수", f"{d['broker_id'].nunique()}"],
               ["표본", f"{len(d):,}"],
               ["기저율(최빈 증권사 비율)", f"{100*base:.1f}%"],
               ["증권사 분류 정확도(3-fold)", f"{100*acc:.1f}%"],
               ["판정", verdict]],
              ["항목", "값"], ["l", "r"],
              title="정형문구 제거 검증 (§6.2) — 이 검증이 없으면 TONE 은 증권사 더미일 수 있다")
    if acc >= base + 0.10:
        PIPE.note("WARN: 정형문구 누출 잔존 의심 — TONE 해석 주의")
    return {"base_rate": base, "broker_acc": acc, "n": int(len(d))}


# ── 확장윈도우 학습 + TONE 산출 ─────────────────────────────────────────────────────────────
#  ▸ 문장 채점 판정 여백. 확률이 0.5±이 값 밖일 때만 긍정/부정으로 '투표'하고, 안쪽은
#    중립으로 기권한다. 0 으로 두면 예전 동작(모든 문장이 강제 투표)으로 돌아가며,
#    그러면 중립 문장이 신호 문장을 묻어 축이 무의미해진다(실측 상관 -0.008).
TONE_SENT_MARGIN = 0.15

TONE_TRAIN_LOG: List[dict] = []


def build_tone_scores(T: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """리포트별 TONE. 시점 t 의 리포트는 't 이전에 라벨이 확정된' 표본으로만 학습한 모델로 채점.

    반환: report_uid · pub_date · stock_code · tone · n_sent · model_epoch
    """
    out_cols = ["report_uid", "pub_date", "stock_code", "tone", "n_sent", "model_epoch"]
    # ★★ 예전엔 여기서 조용히 빈 프레임을 돌려줬다 ★★
    #   TONE 은 이 전략의 유일한 머신러닝 구성요소(TF-IDF + 로지스틱 회귀)인데,
    #   sklearn 이 없으면 아무 말 없이 사라졌다. 사용자는 로그 어디에서도 '학습이
    #   일어났는지' 알 수 없었고, ΔTONE 이 전부 결측이 되어 Score2 가 ΔNONFIN 단독이
    #   되는데도 그 사실이 드러나지 않았다. 무엇이 왜 없는지 반드시 말한다.
    if not ensure_sklearn():
        LOG.warn("scikit-learn 을 쓸 수 없어 TONE 분류기(TF-IDF + 로지스틱 회귀)를 학습하지 "
                 "못했습니다 — ΔTONE 이 전부 결측이 되고 Score2 는 ΔNONFIN 단독이 됩니다. "
                 "`pip install scikit-learn` 후 재실행하면 이 축이 살아납니다.")
        return pd.DataFrame(columns=out_cols)
    if T is None or T.empty or labels is None or labels.empty:
        LOG.warn(f"TONE 학습 입력이 비었습니다 (본문 {0 if T is None else len(T):,}건 · "
                 f"라벨 {0 if labels is None else len(labels):,}건) — ΔTONE 결측 처리.")
        return pd.DataFrame(columns=out_cols)
    D = T.merge(labels, on="report_uid", how="left")
    D["pub_date"] = as_ts_series(D["pub_date"])
    D = D.dropna(subset=["pub_date", "text"]).sort_values("pub_date", kind="stable")
    D["label_ready"] = as_ts_series(D["label_ready"])

    freq = "YS" if str(TONE_RETRAIN_FREQ).upper().startswith("Y") else "QS"
    edges = pd.date_range(D["pub_date"].min().normalize(), D["pub_date"].max() + pd.offsets.YearEnd(1),
                          freq=freq)
    edges = [as_ts(e) for e in edges]
    if not edges or edges[0] > D["pub_date"].min():
        edges = [as_ts(D["pub_date"].min())] + edges

    scored: List[pd.DataFrame] = []
    trained = 0
    for i, e in enumerate(edges):
        nxt = edges[i + 1] if i + 1 < len(edges) else (D["pub_date"].max() + pd.Timedelta(days=1))
        apply_mask = (D["pub_date"] >= e) & (D["pub_date"] < nxt)
        if not apply_mask.any():
            continue
        # ★ 학습 표본: '라벨이 e 이전에 확정된' 것만. 발간일 기준으로 자르면 경계 직전 리포트의
        #   2일 CAR 이 경계 이후를 보게 되어 그만큼 미래를 학습한다.
        tr = D[D["label_ready"].notna() & (D["label_ready"] < e) & D["label"].notna()]
        sub = D[apply_mask]
        if len(tr) < TONE_MIN_TRAIN_DOCS or tr["label"].nunique() < 2:
            LOG.debug(f"  {e:%Y-%m}: 학습표본 {len(tr):,}건 < 최소 {TONE_MIN_TRAIN_DOCS} — "
                      f"이 구간 TONE 은 결측(0 으로 채우지 않음)")
            continue
        try:
            # ★★ 라벨이 '문서' 단위이므로 학습도 채점도 문서 단위여야 한다 ★★
            #   두 번의 실패로 확인했다(합성 · 라벨잡음 25%):
            #    ① 문서 학습 → 문장 채점 : CV 0.77 인데 tone↔진짜부호 상관 -0.008.
            #       중립 문장이 사전확률로 쏠려 신호 문장을 표로 눌렀다.
            #    ② 문장 학습(문서 라벨 상속) → 문장 채점 : CV 0.52. 중립 문장 9/12 가
            #       라벨을 잡음으로 물려받아 학습 자체가 희석됐다.
            #   → 문서로 학습하고 문서로 채점한다. tone = 2·P(긍정) − 1 로 [-1,+1] 이다.
            #   ※ §6.2 문언은 '(긍정문장 − 부정문장)/전체문장' 이지만, 우리가 가진 라벨은
            #     문서 단위(2일 CAR)뿐이라 문장 라벨이 존재하지 않는다. 문장 채점은 위
            #     실측대로 축을 무의미하게 만든다. 같은 [-1,+1] 척도의 문서 확률로 대체하며,
            #     이 편차는 §10.1 한계로 명시한다.
            vec = _SK["Tfidf"](analyzer="char_wb", ngram_range=(2, 4), min_df=3,
                               max_features=120000, sublinear_tf=True)
            Xtr = vec.fit_transform(tr["text"].astype(str))
            _ytr = tr["label"].astype(int).to_numpy()
            clf = _SK["LR"](max_iter=600, C=0.5)
            clf.fit(Xtr, _ytr)
        except Exception as ex:                                # noqa
            LOG.warn(f"  {e:%Y-%m}: TONE 모델 학습 실패({type(ex).__name__}) — 이 구간은 결측 처리")
            continue
        trained += 1
        # ★ 학습이 '실제로 일어났는지'를 표로 남긴다. 예전에는 모델 개수 한 줄뿐이라
        #   표본 크기·판별력을 알 수 없었다. 3-fold 교차검증 정확도를 같이 기록한다
        #   (학습 표본 안에서만 계산 — 채점 대상은 보지 않으므로 미래누수가 없다).
        _acc = float("nan")
        try:
            if len(tr) >= 60:
                _acc = float(np.mean(_SK["cvs"](_SK["LR"](max_iter=400, C=0.5), Xtr, _ytr,
                                                cv=3, scoring="accuracy")))
        except Exception:
            pass
        TONE_TRAIN_LOG.append({"구간": f"{e:%Y-%m}", "학습표본": len(tr),
                               "양(+)비율": f"{100*float(_ytr.mean()):.1f}%",
                               "특징수": int(Xtr.shape[1]),
                               "CV정확도(3-fold)": "—" if not np.isfinite(_acc) else f"{_acc:.3f}",
                               "채점대상": int(apply_mask.sum())})

        # 문장 단위 채점 → TONE = (긍정문장 − 부정문장) / 전체문장
        recs = []
        sents_all: List[str] = []
        owner: List[int] = []
        for j, (uid, txt) in enumerate(zip(sub["report_uid"].astype(str), sub["text"].astype(str))):
            ss = split_sentences_ko(txt)
            if not ss:
                continue
            sents_all.extend(ss)
            owner.extend([j] * len(ss))
        if not sents_all:
            continue
        try:
            _pd_ = clf.predict_proba(vec.transform(sub["text"].astype(str)))[:, 1]
        except Exception:
            continue
        tone = 2.0 * _pd_ - 1.0                  # [-1, +1]
        tot = sub["n_sent"].astype(float).to_numpy() if "n_sent" in sub.columns \
            else np.ones(len(sub))
        recs = sub[["report_uid", "pub_date", "stock_code"]].copy()
        recs["tone"] = tone
        recs["n_sent"] = tot
        recs["model_epoch"] = e
        scored.append(recs)
        del _pd_

    if not scored:
        LOG.warn("TONE 을 산출한 구간이 없습니다 (학습표본 부족). ΔTONE_resid 는 전부 중립(0)이 "
                 "되고 Score2 는 사실상 ΔNONFIN 단독이 됩니다 — §6.2 설계상 허용됩니다.")
        return pd.DataFrame(columns=out_cols)
    S = pd.concat(scored, ignore_index=True).dropna(subset=["tone"])
    if TONE_TRAIN_LOG:
        LOG.table([[r["구간"], f"{r['학습표본']:,}", r["양(+)비율"], f"{r['특징수']:,}",
                    r["CV정확도(3-fold)"], f"{r['채점대상']:,}"] for r in TONE_TRAIN_LOG],
                  ["학습 구간", "학습표본", "양(+)비율", "특징수", "CV정확도", "채점대상"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="TONE 분류기 학습 이력 (TF-IDF char 2~4gram + 로지스틱 회귀 · 확장윈도우)")
        _accs = [float(r["CV정확도(3-fold)"]) for r in TONE_TRAIN_LOG
                 if r["CV정확도(3-fold)"] != "—"]
        if _accs:
            LOG.info(f"CV 정확도 중앙값 {float(np.median(_accs)):.3f} — 0.5 는 무작위와 같습니다. "
                     f"0.55 를 밑돌면 이 축의 신호는 사실상 잡음이므로 §9-C5 해석에 반영하십시오.")
    LOG.ok(f"TONE 산출 {len(S):,}건 · 확장윈도우 모델 {trained}개 "
           f"(각 모델은 자기 구간 '이전에 라벨이 확정된' 표본으로만 학습)")
    VAULT.put_table("qvf_report_tone", S, scope="private", domain="research",
                    source="expanding-window TFIDF+LR")
    return S


def build_tone_panel(S: pd.DataFrame, G: pd.DataFrame, cal: pd.DataFrame,
                     exclude_irc: bool = False, T: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """리포트별 TONE → (code, rebal) 의 TONE / ΔTONE / 리포트 건수.

    구간 정의: 직전 리밸런싱 이후 ~ signal_date 까지 발간된 리포트의 TONE 평균.
    ΔTONE = 이번 구간 TONE − 직전 구간 TONE (직전 구간이 없으면 결측).
    """
    base = G[["code", "rebal", "signal_date"]].drop_duplicates()
    if S is None or S.empty:
        base["tone_q"] = np.nan
        base["dTONE"] = np.nan
        base["n_reports"] = 0.0
        return base
    R = S.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["pub_date", "stock_code", "tone"])
    if exclude_irc and T is not None and len(T):
        irc = set(T.loc[pd.to_numeric(T["is_irc"], errors="coerce").fillna(0) > 0,
                        "report_uid"].astype(str))
        n0 = len(R)
        R = R[~R["report_uid"].astype(str).isin(irc)]
        LOG.info(f"한국IR협의회 기업의뢰형 리포트 {n0-len(R):,}건 제외 (§8.4 민감도 분기)")
    R = R.rename(columns={"stock_code": "code"})
    # §4 — 발간일 + 1거래일부터 사용 가능
    R["usable"] = next_trading_day_series(R["pub_date"])

    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        # ★ 왼쪽 끝은 '직전 분기의 signal_date' 여야 한다. 명목 리밸일(reb[i-1])로 잡으면
        #   signal_date_{i-1} < rebal_{i-1} 이므로 (signal_{i-1}, rebal_{i-1}] 구간이
        #   어느 창에도 속하지 않는다 — 명목일이 거래일인 분기마다 정확히 1거래일의
        #   공시·리포트·목표주가 수정이 조용히 사라진다.
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        if lo is None:
            lo = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = R[(R["usable"] > lo) & (R["usable"] <= hi)]
        if w.empty:
            continue
        a = w.groupby("code", observed=True).agg(tone_q=("tone", "mean"),
                                                 n_reports=("report_uid", "nunique")).reset_index()
        a["rebal"] = as_ts(t)
        parts.append(a)
    if not parts:
        base["tone_q"] = np.nan
        base["dTONE"] = np.nan
        base["n_reports"] = 0.0
        return base
    A = pd.concat(parts, ignore_index=True).sort_values(["code", "rebal"], kind="stable")
    # ΔTONE 은 '직전 분기'와만 짝지어야 한다. 중간 분기가 비면 결측이다.
    A["_i"] = A.groupby("code", observed=True).cumcount()
    A["_rank"] = A["rebal"].map({t: k for k, t in enumerate(reb)})
    prev_tone = A.groupby("code", observed=True)["tone_q"].shift(1)
    prev_rank = A.groupby("code", observed=True)["_rank"].shift(1)
    A["dTONE"] = (A["tone_q"] - prev_tone).where((A["_rank"] - prev_rank) == 1)
    out = base.merge(A[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                     on=["code", "rebal"], how="left")
    out["n_reports"] = pd.to_numeric(out["n_reports"], errors="coerce").fillna(0.0)
    cov = float((out["n_reports"] > 0).mean())
    LOG.ok(f"TONE 패널 {len(out):,}행 · 리포트 보유 {100*cov:.1f}% · "
           f"ΔTONE 관측 {int(out['dTONE'].notna().sum()):,}행 "
           f"({100*out['dTONE'].notna().mean():.1f}%)")
    return out


def orthogonalize_tone(P: pd.DataFrame) -> pd.DataFrame:
    """ΔTONE 을 목표주가 수정률·12-1 모멘텀·log(시총)·섹터 더미에 회귀한 잔차(§6.2).

    ★ 회귀는 반드시 '리밸런싱 시점별 횡단면'으로 적합한다. 전 기간을 풀링해서 적합하면
      계수가 미래 관측까지 보고 정해지므로 잔차에 미래정보가 섞인다.
    ★ EPS 컨센서스 수정률은 과거 시계열 복원이 불가능하다(국내 무료 경로 부재). 대신 확보
      가능한 목표주가 수정률을 쓰고, 이 대체 사실을 로그에 명시한다.
    """
    d = P.copy()
    d["dTONE_resid"] = np.nan
    if "dTONE" not in d.columns or d["dTONE"].notna().sum() < 30:
        LOG.warn("ΔTONE 관측이 부족해 직교화를 건너뜁니다 — ΔTONE_resid 는 전부 중립(0)이 됩니다.")
        d["dTONE_resid"] = np.nan
        return d

    feats = [c for c in ("tp_revision", "mom12_1", "log_cap") if c in d.columns]
    if "log_cap" not in d.columns:
        d["log_cap"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").where(lambda s: s > 0))
        feats = [c for c in ("tp_revision", "mom12_1", "log_cap") if c in d.columns]

    resid = pd.Series(np.nan, index=d.index, dtype="float64")
    n_fit = 0
    for t, g in d.groupby("rebal", observed=True):
        m = g["dTONE"].notna()
        if int(m.sum()) < 20:
            continue
        gg = g[m]
        y = pd.to_numeric(gg["dTONE"], errors="coerce").to_numpy(dtype="float64")
        Xparts = [np.ones((len(gg), 1))]
        for c in feats:
            v = pd.to_numeric(gg[c], errors="coerce")
            v = v.fillna(v.median())
            if v.std(ddof=0) > 0:
                Xparts.append(((v - v.mean()) / v.std(ddof=0)).to_numpy().reshape(-1, 1))
        # 섹터 더미 (관측 20건 이상인 섹터만; 나머지는 절편에 흡수 → 랭크 결손 방지)
        sec_s = gg["sector"].astype(str)
        big = sec_s.value_counts()
        big = big[big >= 20].index.tolist()[:40]
        for s in big[1:]:                       # 첫 섹터는 기준집단(더미 트랩 회피)
            Xparts.append((sec_s == s).to_numpy(dtype="float64").reshape(-1, 1))
        X = np.hstack(Xparts)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if ok.sum() < max(20, X.shape[1] + 5):
            continue
        try:
            beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
            r = y - X @ beta
        except Exception:
            continue
        resid.loc[gg.index[ok]] = r[ok]
        n_fit += 1
    d["dTONE_resid"] = resid.astype("float32")
    LOG.ok(f"ΔTONE 직교화 완료 — 횡단면 회귀 {n_fit}개 시점 · 잔차 {int(d['dTONE_resid'].notna().sum()):,}행 "
           f"(설명변수: {', '.join(feats)} + 섹터더미)")
    LOG.info("한계 명시(§10.1): EPS 컨센서스 수정률의 과거 시계열은 국내 무료 경로로 복원이 "
             "불가능해 직교화 설명변수에서 제외했습니다. 목표주가 수정률로 일부 대체했으나 "
             "동일하지 않으며, 그만큼 ΔTONE_resid 에 컨센서스 성분이 남아 있을 수 있습니다.")
    return d


def build_tp_revision(links: pd.DataFrame, G: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """목표주가 수정률 — 같은 애널리스트가 같은 종목에 직전에 제시한 목표주가 대비 변화율.
    애널리스트 원장이 없으면 만들 수 없는 지표다(원장이 장식이 아닌 이유)."""
    base = G[["code", "rebal", "signal_date"]].drop_duplicates()
    if links is None or links.empty or "target_price" not in links.columns:
        base["tp_revision"] = np.nan
        return base
    L = links.dropna(subset=["stock_code", "target_price"]).copy()
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"]).sort_values(["stock_code", "analyst_id", "pub_date"],
                                                  kind="stable")
    prev = L.groupby(["stock_code", "analyst_id"], observed=True)["target_price"].shift(1)
    L["rev"] = safe_div(pd.to_numeric(L["target_price"], errors="coerce"), prev) - 1.0
    L["usable"] = next_trading_day_series(L["pub_date"])
    L = L.rename(columns={"stock_code": "code"}).dropna(subset=["rev"])
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        # ★ 왼쪽 끝은 '직전 분기의 signal_date' 여야 한다. 명목 리밸일(reb[i-1])로 잡으면
        #   signal_date_{i-1} < rebal_{i-1} 이므로 (signal_{i-1}, rebal_{i-1}] 구간이
        #   어느 창에도 속하지 않는다 — 명목일이 거래일인 분기마다 정확히 1거래일의
        #   공시·리포트·목표주가 수정이 조용히 사라진다.
        lo = sig.get(as_ts(reb[i - 1])) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        if lo is None:
            lo = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = L[(L["usable"] > lo) & (L["usable"] <= hi)]
        if w.empty:
            continue
        a = w.groupby("code", observed=True)["rev"].mean().reset_index(name="tp_revision")
        a["rebal"] = as_ts(t)
        parts.append(a)
    if not parts:
        base["tp_revision"] = np.nan
        return base
    A = pd.concat(parts, ignore_index=True)
    out = base.merge(A, on=["code", "rebal"], how="left")
    LOG.info(f"목표주가 수정률 {int(out['tp_revision'].notna().sum()):,}행 확보 "
             f"(애널리스트 원장 기반 — 동일 애널리스트의 직전 제시가 대비)")
    return out


# ── §6.4 인과 순서 점검 ─────────────────────────────────────────────────────────────────────
def check_causal_order(rep: pd.DataFrame, dis: pd.DataFrame, P: pd.DataFrame) -> dict:
    """리포트가 DART 공시를 '보고 쓴 것'이라면 ΔNONFIN 과 ΔTONE 은 독립 확증이 아니라
    같은 정보의 중복 카운팅이다. 선후관계 분포와 두 신호의 상관을 산출해 보고한다.
    ★ 자동으로 가중치를 조정하지 않는다(§6.4) — 보고만 한다."""
    LOG.banner("인과 순서 점검 (§6.4)",
               "리포트 발간이 DART 공시 뒤에 몰려 있다면 두 신호는 독립 확증이 아니다")
    out: Dict[str, Any] = {}
    if rep is None or rep.empty or dis is None or dis.empty:
        LOG.warn("리포트 또는 공시 원장이 비어 인과 순서 점검을 수행할 수 없습니다.")
        return out
    R = rep[["stock_code", "pub_date"]].dropna().copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna().rename(columns={"stock_code": "code"}).sort_values("pub_date", kind="stable")
    D = dis.copy()
    if "code" not in D.columns:
        D["code"] = D.get("stock_code", pd.Series([None] * len(D))).map(to_code6)
    D = D.dropna(subset=["code"])
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"]).sort_values("rcept_dt", kind="stable")
    if R.empty or D.empty:
        LOG.warn("종목코드가 붙은 리포트/공시가 부족해 점검을 건너뜁니다.")
        return out

    M = pd.merge_asof(R, D[["code", "rcept_dt"]].rename(columns={"rcept_dt": "prev_disc"}),
                      left_on="pub_date", right_on="prev_disc", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=90))
    lag = (M["pub_date"] - M["prev_disc"]).dt.days.dropna()
    if len(lag):
        bins = [(0, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 90)]
        rows = [[f"{a}~{b}일", f"{int(((lag>=a)&(lag<=b)).sum()):,}",
                 f"{100*float(((lag>=a)&(lag<=b)).mean()):.1f}%"] for a, b in bins]
        rows.append(["공시 없음(90일 내)", f"{int(M['prev_disc'].isna().sum()):,}",
                     f"{100*float(M['prev_disc'].isna().mean()):.1f}%"])
        LOG.table(rows, ["직전 공시 이후 경과", "리포트 수", "비중"], ["l", "r", "r"],
                  title="리포트 발간일 − 직전 DART 공시일 분포")
        within7 = float(((lag >= 0) & (lag <= 7)).mean())
        out["within7"] = within7
        out["median_lag"] = float(lag.median())
        LOG.info(f"직전 공시 후 7일 내 발간 비율 {100*within7:.1f}% · 중앙 시차 {lag.median():.0f}일")

    if P is not None and {"dNONFIN", "dTONE_resid"} <= set(P.columns):
        sub = P[["dNONFIN", "dTONE_resid"]].dropna()
        if len(sub) > 50:
            c = float(sub.corr(method="spearman").iloc[0, 1])
            out["corr"] = c
            LOG.table([["관측 쌍", f"{len(sub):,}"], ["Spearman 상관", f"{c:+.3f}"]],
                      ["항목", "값"], ["l", "r"],
                      title="ΔNONFIN ↔ ΔTONE_resid 상관 (중복 카운팅 여부)")
            if abs(c) > 0.30:
                LOG.warn(f"두 신호의 상관이 {c:+.3f} 로 높습니다. §6.3 의 2:1 결합 가중치는 "
                         f"'커버리지 비대칭'을 근거로 한 사전등록 값인데, 두 신호가 같은 정보를 "
                         f"세고 있다면 그 근거가 약해집니다. §6.4 지시대로 자동 조정하지 않고 "
                         f"재검토 대상으로만 보고합니다.")
            else:
                LOG.ok(f"상관 {c:+.3f} — 두 신호가 대체로 독립적인 정보를 담고 있습니다.")
        else:
            LOG.warn("두 신호가 동시에 관측된 행이 부족해 상관을 산출하지 못했습니다.")
    return out
