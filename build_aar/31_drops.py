

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  커버리지 철회의 인과 분해 — 이 전략의 차별점 (§6.5)                                 ║
# ║                                                                                          ║
# ║  한국 시장에서 음(−) 신호는 극히 희소하다. 매도의견이 사실상 0이고 공매도가 제약되므로     ║
# ║  "부정적 정보"가 관측 가능한 거의 유일한 경로가 **커버리지 철회**다.                       ║
# ║  그런데 철회에는 두 종류가 섞여 있다:                                                      ║
# ║    · 담당자가 퇴사·이직해서 끊긴 것    → 종목에 대한 정보가 아니다 (기계적)                 ║
# ║    · 재직 중인데 이 종목만 끊은 것     → 종목에 대한 판단이다 (자발적)                      ║
# ║  이 둘을 가르지 못하면 신호는 그냥 "커버리지 감소 = 소외주"의 재발견이다.                   ║
# ║                                                                                          ║
# ║  분류 (하우스의 커버 애널 수 변화 Δn 이라는 **단일 단조 규칙**에서 파생):                   ║
# ║    H-EXIT   잔여 0        → 가중 1.5   하우스 전체가 커버 중단                             ║
# ║    V-DROP   잔여>0, 감소  → 가중 1.0   하우스는 계속 커버하나 인원 감소 = 자발적 철회       ║
# ║    HANDOFF  불변(승계)    → 가중 0.0   주의 총량이 줄지 않았으므로 **철회가 아니다**        ║
# ║    M-EXIT   애널이 원소속에서 사라짐 → 분자 제외. **플라시보군** (여기서 효과가 나오면 실패) ║
# ║    CENSORED-* 판정 불가   → 분자·분모 모두 제외 (라벨을 억지로 붙이지 않는다)               ║
# ║                                                                                          ║
# ║  ★ PIT 봉인: knowledge_ym = t (침묵을 **관측한** 달). 마지막 리포트는 t-3 이므로 신호가     ║
# ║    3개월 지연되지만 t월 말 시점에 100% 관측 가능하다. t-3 을 이벤트일로 쓰면 3개월 선견이다.║
# ║                                                                                          ║
# ║  ★ 소스 단절 방어를 **분류보다 먼저** 한다. 증권사가 배포동의를 철회하거나 스크래퍼가       ║
# ║    막히면 그 달 소속 애널 전원이 동시에 '철회'로 위조된다. 오차가 iid 가 아니라 달력시간에  ║
# ║    군집하므로 t값이 아무 쪽으로나 유의해진다 — 통계적으로 가장 위험한 오염이다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

W_SIG = 3        # 신호용 침묵 판정창(개월). ContCov 가 '분기당 1건'을 요구하므로 그 최소 위반단위.
D_VER = 12       # 검증용 확정 지연(개월). **모든 클래스에 동일하게 강제**한다(§7-F11).
LAM_MIN = 0.5    # M-EXIT 자격 문턱: 사건 전 12M 월평균 발간량. 포아송 근거는 아래 표 참조.
SICK_RATIO = 0.2         # 직전 12M 중앙값 대비 이 비율 미만이면 소스 단절로 판정
MERGER_HALO_M = 3        # 합병 발효 전후 창


def _dense(idx_pairs: np.ndarray, idx_t: np.ndarray, vals: np.ndarray,
           n_pair: int, n_t: int) -> np.ndarray:
    M = np.zeros((n_pair, n_t), dtype=np.float32)
    np.add.at(M, (idx_pairs, idx_t), vals.astype(np.float32))
    return M


def _shift_right(M: np.ndarray, k: int) -> np.ndarray:
    """열 방향 k칸 지연 (t-k 값). 앞쪽은 0."""
    if k <= 0:
        return M
    out = np.zeros_like(M)
    if k < M.shape[1]:
        out[:, k:] = M[:, :-k]
    return out


def _roll_max(M: np.ndarray, w: int) -> np.ndarray:
    """최근 w개월 중 1건이라도 있으면 1."""
    acc = np.zeros_like(M)
    for k in range(w):
        acc = np.maximum(acc, _shift_right(M, k))
    return acc


def _roll_sum(M: np.ndarray, w: int, lag: int = 0) -> np.ndarray:
    acc = np.zeros_like(M)
    for k in range(lag, lag + w):
        acc = acc + _shift_right(M, k)
    return acc


def build_source_health(L: "pd.DataFrame", months: "pd.DatetimeIndex") -> set:
    """(broker_legal_id, month) 중 **소스 단절**로 판단되는 조합. 분류보다 먼저 계산한다."""
    if L is None or L.empty:
        return set()
    x = L.copy()
    x["month"] = as_ts_series(x["month"])
    g = (x.groupby(["broker_legal_id", "month"], observed=True)["report_uid"]
          .nunique().rename("n").reset_index())
    if g.empty:
        return set()
    full = pd.MultiIndex.from_product(
        [sorted(set(as_str_series(g["broker_legal_id"]))), list(months)],
        names=["broker_legal_id", "month"])
    g = (g.set_index(["broker_legal_id", "month"]).reindex(full, fill_value=0)
          .reset_index().sort_values(["broker_legal_id", "month"]))
    med = (g.groupby("broker_legal_id", observed=True)["n"]
            .transform(lambda s: s.rolling(12, min_periods=6).median().shift(1)))
    sick = g[(med.notna()) & (med > 0) & (g["n"] < SICK_RATIO * med)]
    out = set(zip(as_str_series(sick["broker_legal_id"]), sick["month"]))
    if out:
        LOG.warn(f"소스 단절 의심 (증권사×월) {len(out):,}건 — 직전 12개월 중앙값의 "
                 f"{SICK_RATIO:.0%} 미만으로 발간량이 급감한 구간입니다. 이 구간의 철회 사건은 "
                 f"라벨을 붙이지 않고 **전량 제외(CENSORED-SOURCE)** 합니다. "
                 f"배포동의 철회나 수집 차단이 철회를 대량 위조하는 것을 막기 위함입니다.")
        top = pd.Series([b for b, _ in out]).value_counts().head(5)
        nm = (L.drop_duplicates("broker_legal_id")
                .set_index("broker_legal_id")["broker_legal_name"].to_dict())
        LOG.info("  주요 단절: " + ", ".join(f"{nm.get(b, b)}({int(c)}개월)" for b, c in top.items()))
    return out


def classify_coverage_drops(L: "pd.DataFrame", A: "pd.DataFrame", months: "pd.DatetimeIndex",
                            sec: "pd.DataFrame", uni: "pd.DataFrame") -> Dict[str, "pd.DataFrame"]:
    """신호용(3M) · 검증용(12M) · 하우스 그레인 3종 이벤트 테이블을 만든다."""
    empty = pd.DataFrame(columns=["person_id", "analyst_id", "broker_legal_id", "code",
                                  "last_report_month", "month", "klass", "w",
                                  "sole_coverer", "event_date", "knowledge_date"])
    if L is None or L.empty:
        return {"signal": empty, "verify": empty.copy(), "house": empty.copy()}

    x = L.copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"]).replace("", np.nan)
    x = x.dropna(subset=["month", "analyst_id"])
    pid_map = (A.set_index("analyst_id")["analyst_person_id"].to_dict()
               if A is not None and "analyst_person_id" in A.columns else {})
    unclass = set(A.loc[A.get("person_unclassified", False) == True, "analyst_id"]) \
        if A is not None and "person_unclassified" in A.columns else set()
    x["person_id"] = as_str_series(x["analyst_id"]).map(pid_map).fillna(x["analyst_id"])

    all_m = pd.DatetimeIndex(sorted(set(months) | set(x["month"].unique())))
    mpos = {m: i for i, m in enumerate(all_m)}
    T = len(all_m)

    xs = x.dropna(subset=["code"])
    if xs.empty:
        return {"signal": empty, "verify": empty.copy(), "house": empty.copy()}

    # ── (person, code) 그레인 ─────────────────────────────────────────────────────────
    ps_key = as_str_series(xs["person_id"]) + "\x1f" + as_str_series(xs["code"])
    ps_codes, ps_k = factorize_codes(ps_key)
    ti = xs["month"].map(mpos).to_numpy(dtype=np.int64)
    R = _dense(ps_codes, ti, np.ones(len(xs)), ps_k, T)          # r[p,s,t]
    lut = (pd.DataFrame({"_p": ps_codes, "person_id": xs["person_id"].to_numpy(),
                         "code": xs["code"].to_numpy(),
                         "analyst_id": xs["analyst_id"].to_numpy(),
                         "broker_legal_id": xs["broker_legal_id"].to_numpy()})
           .drop_duplicates("_p").set_index("_p").sort_index())

    # ContCov — 명세 문언 "직전 4개 분기 연속" 을 그대로 구현한다
    H = (R > 0).astype(np.float32)
    q = _roll_max(H, 3)
    ContCov = ((q > 0) & (_shift_right(q, 3) > 0) &
               (_shift_right(q, 6) > 0) & (_shift_right(q, 9) > 0))

    silent3 = (_roll_sum(H, 3, lag=0) == 0)                       # t-2..t 무발간
    silent3_1 = (_roll_sum(H, 3, lag=1) == 0)                     # t-3..t-1 무발간
    event = _shift_right(ContCov.astype(np.float32), 3) > 0
    event &= silent3 & (~silent3_1)

    # ── 애널리스트 가용성 (종목 무관, person 그레인) ──────────────────────────────────
    #   ★ 여기서 필요한 것은 '코드 배열'이 아니라 '키 → 행 인덱스' 사전이다.
    #     pd.factorize 의 uniques 로 사전을 만들어야 사건 순회에서 O(1) 로 찾을 수 있다.
    p_ser = as_str_series(x["person_id"])
    p_codes, p_uniq = pd.factorize(p_ser)
    p_index = {k: i for i, k in enumerate(p_uniq)}
    Pall = _dense(np.asarray(p_codes, dtype=np.int64),
                  x["month"].map(mpos).to_numpy(dtype=np.int64),
                  np.ones(len(x)), len(p_uniq), T)

    pb_ser = p_ser + "\x1f" + as_str_series(x["broker_legal_id"])
    pb_codes, pb_uniq = pd.factorize(pb_ser)
    pb_index = {k: i for i, k in enumerate(pb_uniq)}
    Pb = _dense(np.asarray(pb_codes, dtype=np.int64),
                x["month"].map(mpos).to_numpy(dtype=np.int64),
                np.ones(len(x)), len(pb_uniq), T)

    Pall_3 = _roll_sum(Pall, 3, 0)
    Pb_3 = _roll_sum(Pb, 3, 0)
    Lam12 = _roll_sum(Pall, 12, 1) / 12.0

    # ── 하우스 축: (broker_legal, code) 별 커버 애널 수 ───────────────────────────────
    bs = xs.drop_duplicates(["broker_legal_id", "code", "month", "person_id"])
    bs_key = as_str_series(bs["broker_legal_id"]) + "\x1f" + as_str_series(bs["code"])
    bs_codes, bs_k = factorize_codes(bs_key)
    HB = _dense(bs_codes, bs["month"].map(mpos).to_numpy(dtype=np.int64),
                np.ones(len(bs)), bs_k, T)
    bs_lut = (pd.DataFrame({"_b": bs_codes, "broker_legal_id": bs["broker_legal_id"].to_numpy(),
                            "code": bs["code"].to_numpy()})
              .drop_duplicates("_b").set_index("_b").sort_index())
    bs_index = {(b, c): i for i, (b, c) in enumerate(zip(bs_lut["broker_legal_id"],
                                                        bs_lut["code"]))}
    HB_after = _roll_sum(HB, 3, 0)          # t-2..t
    HB_before = _roll_sum(HB, 12, 3)        # t-14..t-3

    # ── 시장 전체 커버 (H-EXIT-MARKET 판정용) ────────────────────────────────────────
    ms = xs.drop_duplicates(["code", "month", "person_id"])
    m_codes, m_k = factorize_codes(ms["code"])
    MK = _dense(m_codes, ms["month"].map(mpos).to_numpy(dtype=np.int64), np.ones(len(ms)), m_k, T)
    MK_after = _roll_sum(MK, 3, 0)
    mk_lut = (pd.DataFrame({"_m": m_codes, "code": ms["code"].to_numpy()})
              .drop_duplicates("_m").set_index("_m").sort_index())
    mk_index = {c: i for i, c in enumerate(mk_lut["code"])}

    # ── 검열 정보 ─────────────────────────────────────────────────────────────────────
    sick = build_source_health(L, all_m)
    dl = dict(zip(as_str_series(sec["code"]), as_ts_series(sec["delisting_date"]))) \
        if sec is not None and len(sec) else {}
    listed = set()
    if uni is not None and len(uni):
        listed = set(zip(as_str_series(uni["code"]), uni["month"]))
    merger_months: set = set()
    for _pat, _new, eff in BROKER_MERGERS:
        e = as_ts(eff)
        if e is None:
            continue
        for k in range(-MERGER_HALO_M, MERGER_HALO_M + 1):
            merger_months.add((e + pd.DateOffset(months=k) + pd.offsets.MonthEnd(0)).normalize())

    # ── 사건 순회 ─────────────────────────────────────────────────────────────────────
    ev_p, ev_t = np.where(event)
    LOG.info(f"철회 사건 후보 {len(ev_p):,}건 (ContCov 4분기 연속 후 {W_SIG}개월 침묵 최초 발생)")
    rows: List[dict] = []
    tally: Counter = Counter()
    for k in range(len(ev_p)):
        pi, tt = int(ev_p[k]), int(ev_t[k])
        m = all_m[tt]
        meta = lut.loc[pi]
        code = str(meta["code"])
        bl = str(meta["broker_legal_id"])
        aid = str(meta["analyst_id"])
        pid = str(meta["person_id"])

        # 0) 검열 가드 — 라벨이 아니라 '제외'를 낸다. 최우선.
        if (bl, m) in sick:
            tally["CENSORED-SOURCE"] += 1
            continue
        if any(((m - pd.DateOffset(months=j)) + pd.offsets.MonthEnd(0)).normalize()
               in merger_months for j in range(0, W_SIG)):
            tally["CENSORED-MA"] += 1
            continue
        d_ = dl.get(code)
        if pd.notna(d_) and d_ is not None and d_ <= m + pd.offsets.MonthEnd(1):
            tally["CENSORED-DELIST"] += 1
            continue
        if listed and (code, m) not in listed:
            tally["CENSORED-DELIST"] += 1
            continue
        if aid in unclass:
            tally["CENSORED-PERSON"] += 1
            continue

        mi = mk_index.get(code)
        if mi is not None and MK_after[mi, tt] == 0:
            tally["H-EXIT-MARKET"] += 1        # 시장 전체가 커버를 끊음 — 별도로 본다
            continue

        # 1) 애널리스트 가용성 — 종목이 아니라 '아무 종목이라도' 기준이라 문턱이 낮다
        pbi = pb_index.get(pid + "\x1f" + bl)
        pi_all = p_index.get(pid)
        n_self_b3 = float(Pb_3[pbi, tt]) if pbi is not None else 0.0
        n_all3 = float(Pall_3[pi_all, tt]) if pi_all is not None else 0.0
        n_other = max(0.0, n_all3 - n_self_b3)          # 다른 법인에서의 발간 = 이직 증거
        lam = float(Lam12[pi_all, tt]) if pi_all is not None else 0.0

        if n_other >= 1:
            avail = "MOVED"
        elif n_self_b3 >= 1:
            avail = "AVAILABLE"
        elif lam >= LAM_MIN:
            avail = "SILENT"
        else:
            tally["UNCLASSIFIED-LOWPROD"] += 1
            continue

        # 2) 하우스 축
        bi = bs_index.get((bl, code))
        n_after = float(HB_after[bi, tt]) if bi is not None else 0.0
        n_before = float(HB_before[bi, tt]) if bi is not None else 0.0

        # 3) 라벨 + 가중
        if avail in ("MOVED", "SILENT"):
            klass, w = "M-EXIT", 0.0
        elif n_after <= 0:
            klass, w = "H-EXIT", NEG_W_HEXIT
        elif n_after < n_before:
            klass, w = "V-DROP", NEG_W_VDROP
        else:
            klass, w = "HANDOFF", 0.0
        tally[klass] += 1
        rows.append({
            "person_id": pid, "analyst_id": aid, "broker_legal_id": bl, "code": code,
            "last_report_month": all_m[max(0, tt - W_SIG)], "month": m,
            "klass": klass, "w": w, "avail": avail,
            "n_house_before": n_before, "n_house_after": n_after,
            "sole_coverer": bool(n_before <= 1), "lam_pre": lam,
        })

    S = pd.DataFrame(rows)
    if len(S):
        S["event_date"] = S["month"]
        S["knowledge_date"] = S["month"]      # 침묵을 관측한 달 = 알 수 있는 시점
        S = pit_frame(S, "event_date", "knowledge_date", source="drops")

    order = ["V-DROP", "H-EXIT", "HANDOFF", "M-EXIT", "H-EXIT-MARKET",
             "CENSORED-SOURCE", "CENSORED-MA", "CENSORED-DELIST", "CENSORED-PERSON",
             "UNCLASSIFIED-LOWPROD"]
    tot = sum(tally.values())
    LOG.table([[k, f"{tally.get(k, 0):,}", f"{100*tally.get(k, 0)/max(tot, 1):.1f}%",
                {"V-DROP": f"자발적 철회 · 가중 {NEG_W_VDROP}",
                 "H-EXIT": f"하우스 전체 철회 · 가중 {NEG_W_HEXIT}",
                 "HANDOFF": "승계(인원 불변) · 가중 0 — 철회가 아님",
                 "M-EXIT": "★플라시보군 — 여기서 효과가 나오면 인과분해 실패",
                 "H-EXIT-MARKET": "시장 전체 커버 소멸 (별도 관측)",
                 "CENSORED-SOURCE": "소스 단절 — 라벨 없이 제외",
                 "CENSORED-MA": "증권사 합병 창 — 제외",
                 "CENSORED-DELIST": "폐지·거래정지 — 제외",
                 "CENSORED-PERSON": "동일인 판정 불가 — 제외",
                 "UNCLASSIFIED-LOWPROD": f"사건 전 12M 월평균 발간 < {LAM_MIN} — 제외"}.get(k, "")]
               for k in order],
              ["분류", "건수", "비중", "의미"], ["l", "r", "r", "l"],
              title=f"§6.5 커버리지 철회 인과분해 (신호용 · 침묵창 {W_SIG}개월 · PIT 봉인)")
    LOG.info(f"포아송 근거 — 월평균 발간 λ=0.15 이면 3개월 무발간이 우연히 63.8% 확률로 "
             f"발생한다. λ≥{LAM_MIN} 이면 22.3% 로 떨어진다. 그래서 저생산 애널의 침묵은 "
             f"철회로 보지 않고 제외한다(오분류가 신호를 희석하기 때문).")
    PIPE.io("OUT", "MEM", "drop_events_signal", S)
    return {"signal": S if len(S) else empty,
            "verify": _classify_verify(S, all_m),
            "house": _house_grain(HB, bs_lut, all_m)}


def _classify_verify(S: "pd.DataFrame", all_m) -> "pd.DataFrame":
    """검증용 라벨 (D_VER=12개월). **모든 클래스에 동일한 지연을 강제**한다.

    ★ 클래스별로 판정 지연이 다르면 M-EXIT 과 V-DROP 이 서로 다른 이벤트 호라이즌을
      비교하게 되어 대비가 '지연 효과'와 교란된다. 검정력을 잃더라도 동일 지연이 옳다.
    ★ 우측절단: t* + 12 가 표본 끝을 넘는 사건은 **전량 제외**한다. 넣으면 표본 끝이
      전부 가짜 드롭으로 보인다.
    """
    if S is None or S.empty:
        return S if S is not None else pd.DataFrame()
    end = all_m[-1]
    V = S[S["month"] + pd.DateOffset(months=D_VER) <= end].copy()
    if V.empty:
        LOG.warn(f"검증용 라벨 대상이 없습니다 — 표본 끝에서 {D_VER}개월 여유가 필요합니다.")
        return V
    V["knowledge_date"] = (V["month"] + pd.DateOffset(months=D_VER) +
                           pd.offsets.MonthEnd(0)).values
    V["event_date"] = V["month"]
    V["klass_ver"] = V["klass"]
    LOG.info(f"검증용 라벨 {len(V):,}건 (신호용 {len(S):,}건 중 우측절단 {len(S)-len(V):,}건 제외). "
             f"확정 지연 {D_VER}개월을 전 클래스에 동일 적용 — 표본 끝 "
             f"{D_VER}개월은 검증 분석에서 구조적으로 빠집니다.")
    try:
        ct = pd.crosstab(V["klass"], V["klass_ver"], normalize="index")
        diag = float(np.mean([ct.loc[i, i] for i in ct.index if i in ct.columns]))
        if diag < 0.7:
            LOG.warn(f"신호용→검증용 라벨 전이 대각비율이 {diag:.2f} 로 낮습니다 — "
                     f"신호 라벨에 잡음이 많다는 뜻입니다.")
    except Exception:
        pass
    return V


def _house_grain(HB, bs_lut, all_m) -> "pd.DataFrame":
    """(증권사, 종목) 그레인의 하우스 철회 패널.

    ★ (애널, 종목) 패널과 **배타가 아니라 중첩**이다. 한국 증권사는 섹터 1인 전담이
      일반적이라 단독 커버 애널의 철회는 정의상 하우스 철회이기도 하다. 교차항
      (V-DROP ∧ H-EXIT) 이 최강 신호이므로 강건성 분할에서 이 중첩을 이용한다."""
    after = _roll_sum(HB, 3, 0)
    before = _roll_sum(HB, 12, 3)
    stop = (before > 0) & (after == 0)
    bi, ti = np.where(stop)
    if not len(bi):
        return pd.DataFrame(columns=["broker_legal_id", "code", "month", "klass"])
    out = pd.DataFrame({
        "broker_legal_id": bs_lut.loc[bi, "broker_legal_id"].to_numpy(),
        "code": bs_lut.loc[bi, "code"].to_numpy(),
        "month": all_m.to_numpy()[ti], "klass": "H-EXIT",
    })
    out["event_date"] = out["month"]
    out["knowledge_date"] = out["month"]
    return pit_frame(out, "event_date", "knowledge_date", source="drops_house")


def build_aar_neg(S: "pd.DataFrame", L: "pd.DataFrame", months: "pd.DatetimeIndex"
                  ) -> "pd.DataFrame":
    """AAR_neg(i,t) = −[Σ w(event)] / |직전 정착 커버 로스터|.

    치역이 [−1.5, 0] 으로 **구조적으로 유계**다. 이 사실이 윈저라이즈를 금지하는 근거다
    (§7-F17 — 윈저라이즈하면 최악의 철회 5건이 단일값 하나로 붕괴한다).
    num>0 이면 den>0 이 논리적으로 보장되므로 0/0 이 발생하지 않는다.
    """
    cols = ["code", "month", "aar_neg", "n_drop", "n_roster"]
    if S is None or S.empty or L is None or L.empty:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    # 직전 정착 커버 로스터: t-1 기준 최근 12개월에 발간 이력이 있는 애널 수
    #   ★ DataFrame.rolling(axis=1) 은 pandas 3 에서 제거되었다. 조밀 행렬 + 이동최대로 푼다.
    roster = (x.groupby(["code", "month"], observed=True)["analyst_id"]
               .nunique().rename("n").reset_index())
    all_m2 = pd.DatetimeIndex(sorted(set(roster["month"].unique()) | set(months)))
    mp2 = {m: i for i, m in enumerate(all_m2)}
    c_codes, c_uniq = pd.factorize(as_str_series(roster["code"]))
    RM = np.zeros((len(c_uniq), len(all_m2)), dtype=np.float32)
    np.add.at(RM, (np.asarray(c_codes, dtype=np.int64),
                   roster["month"].map(mp2).to_numpy(dtype=np.int64)),
              roster["n"].to_numpy(dtype=np.float32))
    ROS = _shift_right(_roll_max(RM, COVER_WINDOW_M), 1)      # t-1 기준 최근 12M 최대
    ci, ti = np.where(ROS > 0)
    ros = pd.DataFrame({"code": np.asarray(c_uniq)[ci],
                        "month": all_m2.to_numpy()[ti],
                        "n_roster": ROS[ci, ti].astype("float64")})

    num = (S[S["w"] > 0].groupby(["code", "month"], observed=True)
             .agg(n_drop=("w", "size"), wsum=("w", "sum")).reset_index())
    if num.empty:
        return pd.DataFrame(columns=cols)
    out = num.merge(ros, on=["code", "month"], how="left")
    out["n_roster"] = pd.to_numeric(out["n_roster"], errors="coerce").fillna(0.0)
    out["n_roster"] = out["n_roster"].where(out["n_roster"] > 0, out["n_drop"])
    out["aar_neg"] = -(out["wsum"] / out["n_roster"]).clip(upper=NEG_W_HEXIT)
    out = out[out["month"].isin(months)]
    LOG.ok(f"AAR_neg {len(out):,}건 (종목×월) · 평균 {float(out['aar_neg'].mean()):.4f} · "
           f"최저 {float(out['aar_neg'].min()):.4f} (치역 [-{NEG_W_HEXIT}, 0] 유계)")
    return out[cols]
