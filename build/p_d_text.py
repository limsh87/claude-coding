

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-D  공시 텍스트 경직성  (주로 V7 거부권)                                              ║
# ║                                                                                          ║
# ║  근거: Cohen·Malloy·Nguyen, "Lazy Prices", Journal of Finance 2020.                       ║
# ║  공시 문서는 기본적으로 전년 문안을 복사한다. 바뀌었다는 것 자체가 신호이며,                ║
# ║  변경은 부정적 정보와 비대칭적으로 연결된다.                                                ║
# ║                                                                                          ║
# ║  ★ 단독 전략으로 세우지 말 것. 이건 주로 음(-)의 신호이고, 롱온리 소액계좌에서              ║
# ║    음의 신호는 알파 원천이 아니라 회피 장치다.                                              ║
# ║  ★ 정규화 필수: 서식 개정·법령 변경으로 전 기업이 일괄 변경되는 해가 있다.                  ║
# ║    연도별 전체 유사도 분포의 중앙값으로 정규화해 공통충격을 제거한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_D_SECTIONS = ["사업의 내용", "위험요인", "이사의 경영진단", "우발부채", "특수관계자"]
PACK_D_SECTION_PAT = {
    "사업의내용": r"(사업의\s*내용|II\.\s*사업의\s*내용)",
    "위험요인": r"(위험요인|투자위험|주요\s*위험)",
    "경영진단": r"(이사의\s*경영진단|경영진단\s*및\s*분석)",
    "우발부채": r"(우발부채|우발채무|중요한\s*소송|계류\s*중인\s*소송)",
    "특수관계자": r"(특수관계자|특수\s*관계자\s*거래)",
}

PACK_D_POLICY = [
    {"policy_id": "DART_FORM_REVISION", "name": "기업공시서식 작성기준 개정(전 기업 일괄 문안 변경)",
     "start": "2019-01-01", "end": None, "pack": "D", "req_type": "없음", "req_value": ""},
    {"policy_id": "KIFRS_AMEND", "name": "K-IFRS 개정에 따른 주석 서식 변경", "start": "2018-01-01",
     "end": None, "pack": "D", "req_type": "없음", "req_value": ""},
    {"policy_id": "ESG_DISCLOSURE", "name": "ESG/지속가능성 공시 의무화 단계 도입", "start": "2025-01-01",
     "end": None, "pack": "D", "req_type": "기업규모", "req_value": "자산 2조 이상 단계 적용"},
]

PACK_D_INTERP = [
    ("TP_D1", "문안이 안정적 — 숨은 악재 정황 없음", "위험요인/우발부채 문단 급변 → V7 거부권 발동"),
]


def _tokenize_ko(t: str) -> Counter:
    """bag-of-words. NLP 임베딩은 콜드빌드 수일 + 재계산 불가라 §3에서 폐기됐다."""
    t = re.sub(r"[^가-힣A-Za-z0-9 ]", " ", str(t or ""))
    toks = [w for w in t.split() if len(w) >= 2]
    return Counter(toks)


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return np.nan
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return float(num / (da * db)) if da and db else np.nan


def fetch_dart_documents(dis: pd.DataFrame, sec: pd.DataFrame,
                         max_docs: int = 40000) -> pd.DataFrame:
    """사업보고서 원문(document.xml, zip) 수집 → 섹션별 bag-of-words 저장.
    원문은 공용 인덱스에 blob 으로, 토큰 카운트는 전용 인덱스에 테이블로 남긴다."""
    if not dart_has_key():
        LOG.warn("DART_API_KEY 미입력 — PACK-D(공시텍스트)를 구동할 수 없습니다.")
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "section", "tokens"])
    cached = VAULT.get_table("dart_doc_tokens", scope="private")
    have = set(cached["rcept_no"].astype(str)) if cached is not None and len(cached) else set()
    if cached is not None and len(cached):
        LOG.info(f"전용 캐시에서 공시 토큰 {len(cached):,}행 재사용")

    if dis is None or dis.empty:
        return cached if cached is not None else pd.DataFrame()
    ann = dis[dis["report_nm"].astype(str).str.contains("사업보고서", na=False)].copy()
    ann = ann[~ann["rcept_no"].astype(str).isin(have)]
    if RUN_MODE == "CACHED":
        ann = ann.iloc[0:0]
    if len(ann) > max_docs:
        LOG.warn(f"사업보고서 원문 {len(ann):,}건 중 {max_docs:,}건만 수집합니다 "
                 f"(콜드빌드 시간 제한). 나머지는 다음 실행에서 이어받습니다.")
        ann = ann.sort_values("rcept_dt", ascending=False).head(max_docs)

    def _one(row):
        rn = str(row)
        raw = http_get(DART_BASE + "document.xml", source="dart", as_bytes=True, tries=2,
                       params={"crtfc_key": DART_API_KEY, "rcept_no": rn})
        if not raw or len(raw) < 500:
            return None
        # ★ ZIP 엔드포인트는 오류일 때도 content-type 을 zip 으로 광고하면서 JSON 본문을 준다.
        #   PK 매직바이트를 먼저 확인해야 정체불명의 unzip 예외 대신 진짜 status 를 볼 수 있다.
        if raw[:2] not in (b"PK",):
            LOG.debug(f"document.xml 이 ZIP 이 아님 (rcept_no={rn}): "
                      f"{raw[:120].decode('utf-8', 'ignore')}")
            return None
        chunks = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            # ★ 원문 zip 안에는 본 보고서 + 감사보고서 + 첨부 재무제표가 여러 엔트리로 들어있다.
            #   첫 엔트리만 읽으면 내용 대부분이 조용히 사라진다.
            for nm in zf.namelist():
                if not nm.lower().endswith((".xml", ".html", ".htm", ".txt")):
                    continue
                b = zf.read(nm)
                # ★ DART 원문은 EUC-KR 인 경우가 많다. XML 선언의 encoding 을 읽어야 한다.
                enc = None
                m_enc = re.search(rb'encoding\s*=\s*["\']([\w\-]+)["\']', b[:400], re.I)
                if m_enc:
                    enc = m_enc.group(1).decode("ascii", "ignore")
                chunks.append(_decode(b, enc, "dart_doc"))
                if sum(len(c) for c in chunks) > 3_000_000:
                    break
        except Exception:
            chunks = [_decode(raw, None, "dart_doc")]
        txt = re.sub(r"<[^>]+>", " ", "\n".join(chunks))
        out = []
        for sec_name, pat in PACK_D_SECTION_PAT.items():
            m = re.search(pat, txt)
            if not m:
                continue
            seg = txt[m.start(): m.start() + 60000]
            out.append({"rcept_no": rn, "section": sec_name,
                        "tokens": json.dumps(dict(_tokenize_ko(seg).most_common(400)),
                                             ensure_ascii=False)})
        return out

    got: List[dict] = []
    if len(ann):
        res = pmap_io(_one, ann["rcept_no"].astype(str).tolist(),
                      workers=min(N_WORKERS_IO, 8), desc="DART 사업보고서 원문")
        for r in res:
            if r:
                got.extend(r)
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        G = pd.DataFrame(got).merge(
            ann[["rcept_no", "corp_code", "rcept_dt"]].astype({"rcept_no": str}),
            on="rcept_no", how="left")
        frames.append(G)
    if not frames:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "section", "tokens"])
    T = pd.concat(frames, ignore_index=True).drop_duplicates(["rcept_no", "section"], keep="last")
    if got:
        VAULT.put_table("dart_doc_tokens", T, scope="private", domain="dart_text",
                        source="opendart document.xml")
    LOG.ok(f"공시 텍스트 토큰 {len(T):,}행 · {T['corp_code'].nunique():,}사")
    return T


def build_text_similarity(T: pd.DataFrame) -> pd.DataFrame:
    """전년 동기 대비 섹션별 코사인 유사도 + 연도별 중앙값 정규화(공통충격 제거)."""
    if T is None or T.empty:
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "sim_risk", "sim_all"])
    d = T.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt", "corp_code"])
    d["year"] = d["rcept_dt"].dt.year
    d = d.sort_values(["corp_code", "section", "year"])
    rows = []
    for (corp, sec_name), g in d.groupby(["corp_code", "section"], observed=True):
        prev_tok, prev_year = None, None
        for r in g.itertuples(index=False):
            try:
                cur = Counter(json.loads(r.tokens))
            except Exception:
                continue
            if prev_tok is not None and r.year - prev_year <= 2:
                rows.append({"corp_code": corp, "section": sec_name, "year": r.year,
                             "rcept_dt": r.rcept_dt, "sim": _cosine(cur, prev_tok)})
            prev_tok, prev_year = cur, r.year
    if not rows:
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "sim_risk", "sim_all"])
    S = pd.DataFrame(rows).sort_values("rcept_dt")
    # ★ 섹션별 중앙값으로 정규화 — 서식 개정 해의 '전 기업 일괄 변경' 공통충격을 제거한다.
    #   단, 같은 해 전체(=아직 제출되지 않은 미래 공시 포함) 중앙값을 쓰면 그 자체가 미래누수다.
    #   → 그 시점까지 '이미 접수된' 공시들만으로 확장(expanding) 중앙값을 만든다.
    #   사업보고서는 3월에 몰리므로 초반 표본이 얇다 → 최소 30건 이상일 때만 정규화한다.
    S["_med"] = (S.groupby("section", observed=True)["sim"]
                  .transform(lambda s: s.shift(1).expanding(min_periods=30).median()))
    S["sim_norm"] = S["sim"] - S["_med"]
    unnorm = int(S["_med"].isna().sum())
    if unnorm:
        LOG.info(f"공시 유사도 {unnorm:,}건은 과거 표본 부족으로 정규화 없이 원값을 씁니다 "
                 f"(미래 표본으로 정규화하면 그 자체가 누수이므로 확장 중앙값만 사용).")
        S["sim_norm"] = S["sim_norm"].fillna(S["sim"] - S["sim"].expanding().median())
    W = S.pivot_table(index=["corp_code", "rcept_dt"], columns="section",
                      values="sim_norm", aggfunc="mean").reset_index()
    W["sim_risk"] = nanmean_cols(W, ["위험요인", "우발부채"])
    W["sim_all"] = nanmean_cols(W, [c for c in W.columns if c in PACK_D_SECTION_PAT])
    W = pit_frame(W, "rcept_dt", "rcept_dt", source="dart_text")
    LOG.ok(f"공시 유사도 {len(W):,}행 (연도×섹션 중앙값 정규화 적용)")
    return W


def pack_d_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    sim = ctx.get("text_sim")
    if sim is not None and len(sim):
        PIT.register("dart_text_sim", sim, key_cols=["corp_code"])
        P = PIT.asof_join(P, "dart_text_sim", by="corp_code", left_time="month",
                          cols=["corp_code", "knowledge_date", "sim_risk", "sim_all"],
                          suffix="_txt")
    # 결합 이후에 채운다 (먼저 만들면 merge_asof 가 실제 데이터에 접미사를 붙여 흘려버린다)
    for c in ("sim_risk", "sim_all"):
        if c not in P.columns:
            P[c] = np.nan
    # V7 입력: 위험요인·우발부채 유사도가 셀 내 하위 5%
    P["sim_risk_pct"] = xsec_rank_pct_l(P, "sim_risk")
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    # 양(+)의 기여는 '문안이 안정적'인 경우에만. 주 용도는 어디까지나 거부권이다.
    P["TP_D1"] = z("sim_all")
    P["E_D"] = P["TP_D1"]
    return P


def pack_d_ingest(ctx: dict, months: pd.DatetimeIndex) -> None:
    """PACK-D 전용 수집. 공시목록(ctx["disclosures"])에서 사업보고서 원문을 받아 유사도를 만든다."""
    ctx["text_sim"] = build_text_similarity(
        fetch_dart_documents(ctx.get("disclosures"), ctx.get("sec")))


register_pack(
    pid="D", name="공시텍스트 경직성", tp_cols=["TP_D1"],
    features_fn=pack_d_features, policy=PACK_D_POLICY, interp=PACK_D_INTERP,
    ingest_fn=pack_d_ingest,
    notes="주 용도는 V7 거부권. 다른 팩이 매수 신호를 냈는데 위험요인/우발부채 문단이 "
          "대폭 확대되었다면 센서가 못 본 무언가가 있다는 뜻.")
