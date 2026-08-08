
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  이벤트 정의 — '매수성 리포트'  (SPEC §6.1)                                         ║
# ║                                                                                          ║
# ║  리포트 이벤트 (B, i, d) 중 아래 하나라도 만족하면 매수성으로 본다:                        ║
# ║    ① 투자의견이 매수/강력매수 계열, 또는                                                  ║
# ║    ② 목표주가 상향폭 ≥ +3% (★ 직전 '동일 증권사' 목표가 대비), 또는                        ║
# ║    ③ 신규 커버리지 개시                                                                    ║
# ║  한국은 매도의견 비중이 사실상 0이라 의견 등급만으로는 변별력이 없다. 목표가 변화가 실질.  ║
# ║                                                                                          ║
# ║  ★ 조용히 틀리는 지점들 — 전부 방어한다                                                   ║
# ║   · 목표가 "0" / "-" 는 '목표주가 없음' 이다. 0 으로 넣으면 리비전이 -100% 가 되어         ║
# ║     모든 종목이 '하향' 으로 분류된다. (13_ingest_research 의 parse_target_price 가 처리)   ║
# ║   · '직전 목표가' 는 반드시 pub_date 미만이어야 한다. 같은 날 두 건이면 순서가 없으므로     ║
# ║     같은 날은 비교 대상에서 제외한다(<= 로 두면 자기 자신과 비교해 항상 0% 가 된다).        ║
# ║   · '신규 커버리지' 를 '데이터상 첫 등장' 으로 정의하면 데이터 시작 시점에 전 종목이        ║
# ║     신규 커버리지가 되어 2016년에 이벤트가 폭발한다 → 워밍업 구간을 둔다.                  ║
# ║   · 리포트 발간 시각은 대개 장 시작 전이지만 보장할 수 없다. knowledge_date 는 pub_date 로  ║
# ║     두되, 진입은 플로우 관측 이후(d+1 이상)이므로 이 불확실성이 수익에 새지 않는다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EVENT_COLS = ["event_uid", "broker", "broker_tier", "code", "pub_date",
              "opinion", "target_price", "prev_target", "tp_rev", "is_new_cov",
              "buyish_reason", "source", "report_uid"]

TP_REVISION_THRESHOLD = 0.03          # SPEC §6.1: +3%
NEW_COVERAGE_WARMUP_DAYS = 365        # 데이터 시작 직후를 '신규 커버리지' 로 오인하지 않기 위한 워밍업


def build_event_panel(rep: pd.DataFrame, bm: "BrokerMap", uni: "DailyUniverse",
                      cal: pd.DatetimeIndex) -> pd.DataFrame:
    """리포트 원장 → 매수성 이벤트 패널. 각 게이트의 탈락 건수를 전부 남긴다."""
    if rep is None or len(rep) == 0:
        LOG.warn("리포트 원장이 비어 이벤트를 만들 수 없습니다.")
        return pd.DataFrame(columns=EVENT_COLS)

    d = rep.copy()
    n0 = len(d)
    uni.audit("리포트 원장 전체", n0)

    d["pub_date"] = as_ts_series(d["pub_date"])
    d["code"] = d["stock_code"].map(to_code6) if "stock_code" in d.columns else np.nan
    d = d.dropna(subset=["pub_date", "code"])
    uni.audit("종목코드·발간일 보유", len(d), f"탈락 {n0-len(d):,}")

    # ── 증권사 정규화 (거래원 매핑과 같은 사전을 쓴다 — 두 축이 같은 이름 공간이어야 조인된다)
    raw_col = "broker_name" if "broker_name" in d.columns else "broker_raw"
    d["broker"] = d[raw_col].map(lambda x: bm.resolve(x))
    n_unmapped = int(d["broker"].isna().sum())
    if n_unmapped:
        LOG.info(f"증권사 미매핑 리포트 {n_unmapped:,}건 — 버리지 않고 broker='UNMAPPED' 로 "
                 f"남겨 감사에 노출합니다(SPEC §5).")
        set_where(d, d["broker"].isna(), "broker", "UNMAPPED")
    d["broker_tier"] = d["broker"].map(bm.tier)

    # ── 리포트 단위 정렬. 같은 (증권사, 종목, 날짜) 복수건은 1건으로 합친다 ────────────────
    d["target_price"] = pd.to_numeric(d.get("target_price"), errors="coerce")
    set_where(d, (d["target_price"] <= 0), "target_price", np.nan)     # "0"/"-" 는 '없음'
    d["opinion"] = d.get("opinion", pd.Series(index=d.index, dtype=object)).astype(str)

    d = (d.sort_values(["broker", "code", "pub_date"], kind="stable")
           .drop_duplicates(["broker", "code", "pub_date"], keep="last"))
    uni.audit("증권사×종목×일 중복 제거", len(d))

    # ── ② 목표가 리비전: 직전 '동일 증권사' 목표가 (strictly before) ──────────────────────
    g = d.groupby(["broker", "code"], observed=True)
    d["prev_target"] = g["target_price"].transform(lambda s: s.ffill().shift(1))
    d["tp_rev"] = safe_div(d["target_price"] - d["prev_target"], d["prev_target"])
    set_where(d, d["prev_target"].isna() | (d["prev_target"] <= 0), "tp_rev", np.nan)

    # ── ③ 신규 커버리지: (증권사, 종목) 첫 등장 + 워밍업 이후 ─────────────────────────────
    first = g["pub_date"].transform("min")
    t_start = d["pub_date"].min()
    d["is_new_cov"] = ((d["pub_date"] == first) &
                       (d["pub_date"] > t_start + pd.Timedelta(days=NEW_COVERAGE_WARMUP_DAYS)))

    # ── ① 매수성 의견 ─────────────────────────────────────────────────────────────────────
    op = d["opinion"].str.upper().str.strip()
    is_buy_op = op.isin(["BUY", "STRONGBUY", "STRONG_BUY"]) | \
        d["opinion"].astype(str).str.contains("매수|적극매수|비중확대|OUTPERFORM|OVERWEIGHT",
                                              case=False, na=False)

    is_up = d["tp_rev"] >= TP_REVISION_THRESHOLD
    buyish = is_buy_op | is_up.fillna(False) | d["is_new_cov"]

    d["buyish_reason"] = np.select(
        [is_up.fillna(False), d["is_new_cov"], is_buy_op],
        ["목표가상향", "신규커버리지", "매수의견"], default="")
    ev = d[buyish].copy()
    uni.audit("매수성 리포트", len(ev),
              f"의견 {int(is_buy_op.sum()):,} · 상향 {int(is_up.fillna(False).sum()):,} · "
              f"신규 {int(d['is_new_cov'].sum()):,}")

    if not len(ev):
        LOG.warn("매수성 리포트가 0건입니다. opinion/target_price 파싱을 확인하세요.")
        return pd.DataFrame(columns=EVENT_COLS)

    # ── 발간일을 거래일로 스냅 (휴일 발간분은 다음 거래일로) ──────────────────────────────
    if len(cal):
        cal_np = cal.to_numpy(DT64)
        pos = np.searchsorted(cal_np, ev["pub_date"].to_numpy(DT64), side="left")
        inside = pos < len(cal_np)
        snapped = np.where(inside, cal_np[np.minimum(pos, len(cal_np) - 1)],
                           np.datetime64("NaT"))
        n_moved = int((snapped != ev["pub_date"].to_numpy(DT64)).sum())
        ev["pub_date"] = pd.to_datetime(snapped)
        ev = ev.dropna(subset=["pub_date"])
        if n_moved:
            LOG.info(f"휴일·장외 발간 {n_moved:,}건을 다음 거래일로 스냅했습니다 "
                     f"(존재하지 않는 날에 진입하는 사고 방지).")
    uni.audit("거래일 스냅", len(ev))

    # ── PIT 유니버스 필터 ─────────────────────────────────────────────────────────────────
    ok = uni.is_member(ev["code"].tolist(), ev["pub_date"].tolist(), require_observed=True)
    n_drop = int((~ok).sum())
    ev = ev[ok].copy()
    uni.audit("PIT 유니버스 통과", len(ev),
              f"상장전/폐지후/시즈닝/우선주/미관측 {n_drop:,}건 제외")

    ev["event_uid"] = [sha1_str("ev", b, c, str(pd.Timestamp(p).date()))[:16]
                       for b, c, p in zip(ev["broker"], ev["code"], ev["pub_date"])]
    ev["source"] = ev.get("source", "")
    ev["report_uid"] = ev.get("report_uid", "")
    E = ev.reindex(columns=EVENT_COLS).reset_index(drop=True)

    # ── 구성 요약 ─────────────────────────────────────────────────────────────────────────
    yr = E.groupby(E["pub_date"].dt.year, observed=True).agg(
        이벤트=("event_uid", "size"), 종목=("code", "nunique"), 증권사=("broker", "nunique"),
        목표가상향=("buyish_reason", lambda s: int((s == "목표가상향").sum())),
        신규커버=("buyish_reason", lambda s: int((s == "신규커버리지").sum())))
    LOG.table([[str(i)] + [f"{v:,}" for v in r] for i, r in zip(yr.index, yr.to_numpy())],
              ["연도", "이벤트", "종목", "증권사", "목표가상향", "신규커버"],
              ["c", "r", "r", "r", "r", "r"], title="매수성 리포트 이벤트 구성 (SPEC §6.1)")

    tier = E["broker_tier"].value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/max(len(E),1):.1f}%"] for k, v in tier.items()],
              ["증권사 구분", "이벤트", "비중"], ["l", "r", "r"],
              title="이벤트의 증권사 구성 (H3 검정의 기반)")
    if tier.get("MID", 0) < 200:
        LOG.warn("중소형(MID) 증권사 이벤트가 200건 미만입니다 — H3(중소형사 강세) 검정의 "
                 "검정력이 매우 낮습니다. 결과가 '기각' 으로 나와도 효과 부재의 증거가 아닙니다.")

    PIPE.io("OUT", "MEM", "event_panel", E)
    return E


def attach_matched_actor(E: pd.DataFrame, mode: str) -> pd.DataFrame:
    """이벤트마다 '어떤 행위자의 플로우를 볼 것인가' 를 붙인다.

    mode="MEMBER" : 발행 증권사 본인의 창구           (원 가설 · FULL10/PARTIAL 분기)
    mode="PROXY"  : 발행사 계열 정합                  (PROXY 분기)
                    외국계 하우스 → FOREIGN / 국내 하우스 → INST
                    ★ 이것은 원 가설의 대리 검증이 아니다. 창구 정체성이 주체 정체성으로
                      강등되며, 그 사실이 모든 산출물에 표기된다.
    """
    if E is None or len(E) == 0:
        return E
    e = E.copy()
    if mode == "MEMBER":
        e["actor"] = e["broker"]
        e["actor_kind"] = "MEMBER"
    else:
        e["actor"] = np.where(e["broker_tier"].astype(str) == "FOREIGN", "FOREIGN", "INST")
        e["actor_kind"] = e["actor"]
    return e
