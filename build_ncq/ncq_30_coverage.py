

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 2 — 신규 커버리지 판정 (H1 de novo / H2 broker-new) · 스폰서 분리                   ║
# ║                                                                                          ║
# ║  입력 : REP(보고서 원장) · UNI(PIT 유니버스) · valid_start(완결성 진단 결과)                ║
# ║  출력 : EV[month,code,event_type,n_reports,n_brokers,sources,broker_ids,                  ║
# ║           sponsor_group,report_uids,first_broker,analyst_new]                             ║
# ║  실패 : 이벤트가 0건이면 예외가 아니라 '왜 0건인지'(어느 게이트에서 죽었는지)를 표로 낸다.  ║
# ║                                                                                          ║
# ║  ★ 이 단계가 비용 구조의 분기점이다. 여기서 수만 건이 수천 건으로 압축되고, Phase 3 는      ║
# ║    그 수천 건의 PDF 만 받는다. 판정이 헐거우면 PDF 비용이 폭발하고, 빡빡하면 표본이 죽는다. ║
# ║  ★ 브로커 합병은 PIT 로 다룬다. 합병 후 ID 로 과거를 소급 통합하면 '신규'가 조용히 사라진다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 유동성 게이트 이전(유니버스 통과분) 이벤트 집합 — 민감도 ADV 축이 이걸 다시 거른다.
NCQ_EV_UNGATED: Optional[pd.DataFrame] = None

EV_COLS = ["month", "code", "event_type", "n_reports", "n_brokers", "sources", "broker_ids",
           "sponsor_group", "report_uids", "first_broker", "analyst_new", "is_denovo"]

# 실제 '합병'(서로 다른 두 법인의 결합)만 PIT 로 분리한다. 단순 사명변경은 동일 법인이므로
# 소급 통합이 오히려 정확하다(같은 브로커가 커버리지를 이어간 것).
#   (합병 후 정식명, 합병 전 별칭 정규식, 합병 전 표시명, 발효일)
NCQ_BROKER_MERGERS: List[Tuple[str, str, str, str]] = [
    ("미래에셋증권", r"(대우증권|KDB대우|KDB\s*대우)", "대우증권", "2016-12-29"),
    ("KB증권",       r"현대증권",                        "현대증권", "2017-01-01"),
    ("NH투자증권",   r"(우리투자증권|NH농협증권)",       "우리투자증권", "2014-12-31"),
    ("유안타증권",   r"동양증권",                        "동양증권", "2014-10-01"),
]
_NCQ_MERGE_RE = [(post, re.compile(pat), pre, as_ts(eff))
                 for post, pat, pre, eff in NCQ_BROKER_MERGERS]


def ncq_pit_broker_id(broker_raw: Any, pub_date: Any) -> Tuple[str, str]:
    """PIT 브로커 ID. 합병 발효일 **이전** 리포트는 합병 전 법인 ID 를 유지한다.

    ★ 왜 필요한가: 대우증권이 2015년에 A사를 커버했고 미래에셋이 2018년에 A사를 처음 커버했다면,
      2018년은 '미래에셋 입장에서 신규'다. 그런데 두 법인을 하나로 소급 통합하면 2015년 커버리지가
      미래에셋의 것으로 계상되어 2018년 이벤트가 사라진다. 반대로 사명만 바뀐 경우(하나금투→
      하나증권)는 같은 법인이므로 통합이 맞다. 이 둘을 구분하지 않으면 이벤트 수가 조용히 틀어진다.
    """
    bid, canon = normalize_broker(broker_raw)
    if not canon:
        return ("", "")
    t = as_ts(pub_date)
    if t is None:
        return (bid, canon)
    raw = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(broker_raw or "")))
    for post, rx, pre, eff in _NCQ_MERGE_RE:
        if canon == post and eff is not None and t < eff and rx.search(raw):
            return (sha1_str("broker", pre)[:12], pre)
    return (bid, canon)


def _ncq_mi(months_like) -> pd.Series:
    """월 인덱스(연*12+월)를 정수로. 개월 차이를 뺄셈 한 번으로 구하기 위한 표준화."""
    t = as_ts_series(months_like)
    return (t.dt.year.astype("float") * 12 + t.dt.month.astype("float"))


def build_coverage_events(REP: pd.DataFrame, UNI: pd.DataFrame, months: pd.DatetimeIndex,
                          valid_start: Optional[pd.Timestamp] = None,
                          lookback_m: Optional[int] = None,
                          burnin_m: Optional[int] = None,
                          links: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """신규 커버리지 이벤트 원장.

    H1 (주 정의) denovo(i,t) : [t-L, t) 에 **어떤 브로커의 리포트도 없음** AND 월 t 에 ≥1건
    H2 (부 정의) broker_new  : [t-L, t) 에 **브로커 b 의 리포트 없음**   AND 월 t 에 b 의 리포트 ≥1건

    ★ 커버리지 이력 판정에는 유니버스 필터를 걸지 않는다(명세 §1.3). 유니버스는 마지막에
      '이벤트를 신호로 채택할지'에만 적용한다. 먼저 자르면 과거 커버리지가 소실되어
      가짜 신규가 대량 발생한다.
    """
    L = int(lookback_m or NCQ_LOOKBACK_M)
    B = int(burnin_m or NCQ_BURNIN_M)
    if REP is None or REP.empty:
        LOG.error("보고서 원장이 비어 신규 커버리지를 판정할 수 없습니다.")
        return pd.DataFrame(columns=EV_COLS)

    r = REP.copy()
    r["code"] = r["stock_code"].map(to_code6)
    n_all = len(r)
    r = r.dropna(subset=["code"])
    n_code = len(r)
    r["pub_date"] = as_ts_series(r["pub_date"])
    r = r.dropna(subset=["pub_date"])
    r["month"] = r["pub_date"] + pd.offsets.MonthEnd(0)
    r["mi"] = _ncq_mi(r["month"])

    # PIT 브로커 ID 재계산 (원장의 broker_id 는 비-PIT 통합본이라 그대로 쓰면 안 된다)
    pit = [ncq_pit_broker_id(b, d) for b, d in zip(r["broker_raw"].fillna(r.get("broker_name", "")),
                                                   r["pub_date"])]
    r["pit_broker_id"] = [p[0] for p in pit]
    r["pit_broker_name"] = [p[1] for p in pit]
    n_nobroker = int((r["pit_broker_id"].astype(str) == "").sum())
    if n_nobroker:
        # 브로커를 알 수 없는 건은 H2 판정에서 제외하되 H1(종목 단위)에는 남긴다.
        LOG.warn(f"증권사를 식별하지 못한 리포트 {n_nobroker:,}건 — H2(브로커 단위) 판정에서만 "
                 f"제외하고 H1(종목 단위)에는 포함합니다.")
    if "is_sponsored" not in r.columns:
        r["is_sponsored"] = r["source"].astype(str).str.contains("irs", case=False, na=False)

    # ── H1: 종목 단위 de novo ─────────────────────────────────────────────────────────────
    cm = (r.groupby(["code", "mi"], observed=True)
            .agg(n_reports=("report_uid", "nunique"))
            .reset_index()
            .sort_values(["code", "mi"]))
    cm["prev_mi"] = cm.groupby("code", observed=True)["mi"].shift(1)
    cm["gap"] = cm["mi"] - cm["prev_mi"]
    cm["is_denovo"] = cm["prev_mi"].isna() | (cm["gap"] > L)

    # ── H2: (종목, 브로커) 단위 신규 ──────────────────────────────────────────────────────
    rb = r[r["pit_broker_id"].astype(str) != ""]
    if len(rb):
        cb = (rb.groupby(["code", "pit_broker_id", "mi"], observed=True)
                .size().rename("n").reset_index()
                .sort_values(["code", "pit_broker_id", "mi"]))
        cb["prev_mi"] = cb.groupby(["code", "pit_broker_id"], observed=True)["mi"].shift(1)
        cb["gap"] = cb["mi"] - cb["prev_mi"]
        cb["broker_new"] = cb["prev_mi"].isna() | (cb["gap"] > L)
        bn = (cb[cb["broker_new"]].groupby(["code", "mi"], observed=True)
                .agg(n_new_brokers=("pit_broker_id", "nunique")).reset_index())
    else:
        bn = pd.DataFrame(columns=["code", "mi", "n_new_brokers"])

    E = cm.merge(bn, on=["code", "mi"], how="left")
    E["n_new_brokers"] = E["n_new_brokers"].fillna(0).astype(int)
    E = E[E["is_denovo"] | (E["n_new_brokers"] > 0)].copy()
    E["event_type"] = np.where(E["is_denovo"], "H1", "H2")

    # ── 월 단위 부가정보 결합 ─────────────────────────────────────────────────────────────
    meta = (r.groupby(["code", "mi"], observed=True)
             .agg(n_brokers=("pit_broker_id", lambda s: int(pd.Series(s).astype(str)
                                                            .replace("", np.nan).nunique())),
                  sources=("source", lambda s: "+".join(sorted({t for v in s
                                                                for t in str(v).split("+") if t}))),
                  broker_ids=("pit_broker_id", lambda s: "|".join(sorted({str(v) for v in s if v}))),
                  first_broker=("pit_broker_name", lambda s: sorted({str(v) for v in s if v})[:1]),
                  report_uids=("report_uid", lambda s: "|".join(sorted(map(str, set(s))))[:4000]),
                  n_sponsored=("is_sponsored", "sum"),
                  n_tot=("is_sponsored", "size"))
             .reset_index())
    meta["first_broker"] = meta["first_broker"].map(lambda x: x[0] if isinstance(x, list) and x else "")
    E = E.merge(meta, on=["code", "mi"], how="left")

    # 스폰서 그룹 (명세 §7.2)
    ns, nt = E["n_sponsored"].fillna(0).to_numpy(), E["n_tot"].fillna(0).to_numpy()
    grp = np.where(nt <= 0, "UNKNOWN",
                   np.where(ns >= nt, "SPONSORED_ONLY",
                            np.where(ns <= 0, "ORGANIC_ONLY", "MIXED")))
    E["sponsor_group"] = grp

    # 애널리스트 단위 신규 (보조 지표 — PDF/리스트에서 애널리스트를 식별한 부분집합에서만)
    E["analyst_new"] = np.nan
    if links is not None and len(links):
        try:
            E = _ncq_attach_analyst_new(E, links, L)
        except Exception as e:                                    # noqa
            LOG.warn(f"애널리스트 단위 보조 판정을 건너뜁니다({type(e).__name__}) — "
                     f"주 판정(H1/H2)에는 영향 없습니다.")

    # ── 월 복원 · burn-in · 유니버스 게이트 ───────────────────────────────────────────────
    # mi = y*12 + m 이므로 단순 나머지 연산은 12월에서 0 이 된다. -1 보정 후 복원한다.
    yy = ((E["mi"] - 1) // 12).astype(int)
    mm = (E["mi"] - yy * 12).astype(int)
    E["month"] = pd.to_datetime(dict(year=yy, month=mm, day=1), errors="coerce") + \
        pd.offsets.MonthEnd(0)
    E = E.dropna(subset=["month"])

    n_before_gate = len(E)
    vs = as_ts(valid_start) if valid_start is not None else as_ts(BACKTEST_START)
    burn_end = (vs + pd.DateOffset(months=max(L, B))) + pd.offsets.MonthEnd(0)
    E = E[E["month"] >= burn_end]
    n_after_burn = len(E)

    E = E[E["month"].isin(months)]
    n_after_win = len(E)

    if UNI is not None and len(UNI):
        u = UNI[["month", "code", "in_uni", "liq_pass", "mcap", "adv20"]]
        E = E.merge(u, on=["month", "code"], how="left")
        E["in_uni"] = E["in_uni"].fillna(False).astype(bool)
        E["liq_pass"] = E["liq_pass"].fillna(False).astype(bool)
        n_uni = int(E["in_uni"].sum())
        # ★★ 유동성 게이트 **이전** 집합을 따로 보존한다.
        #   민감도의 ADV 축은 이 집합에서 다시 걸러야 의미가 있다. 게이트가 이미 적용된
        #   EV 에서 ADV 를 낮추면 상위집합이라 아무것도 바뀌지 않아(no-op) 기본 조합과
        #   비트 단위로 같은 결과가 '독립 시행'으로 계상되고, 그게 Holm/PBO/DSR 의 시행
        #   횟수를 오염시킨다. ADV 완화 강건성이 한 번도 검정되지 않는 셈이다.
        globals()["NCQ_EV_UNGATED"] = E[E["in_uni"]].copy()
        E = E[E["liq_pass"]]
    else:
        n_uni = len(E)
        E["in_uni"] = True
        E["liq_pass"] = True

    LOG.table([["리포트 원장 전체", f"{n_all:,}"],
               ["종목코드 매핑 성공", f"{n_code:,}"],
               ["(종목,월) 관측", f"{len(cm):,}"],
               [f"신규 커버리지 후보 (L={L}M)", f"{n_before_gate:,}"],
               [f"burn-in {max(L,B)}M 통과 (≥{burn_end:%Y-%m})", f"{n_after_burn:,}"],
               ["백테스트 윈도우 내", f"{n_after_win:,}"],
               [f"시총 하위 {NCQ_UNIVERSE_BOTTOM_N} 유니버스", f"{n_uni:,}"],
               ["유동성 필터 통과 = 최종 이벤트", f"{len(E):,}"]],
              ["게이트", "잔존"], ["l", "r"],
              title="신규 커버리지 판정 퍼널 — 어느 게이트에서 표본이 줄었는지")

    if E.empty:
        LOG.error("최종 이벤트가 0건입니다. 위 퍼널에서 어느 게이트가 원인인지 먼저 확인하세요. "
                  "가장 흔한 원인은 ① 리포트 원장의 종목코드 매핑 실패 ② 유동성 필터가 소형주를 "
                  "전부 걸러냄 ③ 아카이브 결손으로 burn-in 이 너무 늦게 끝남 입니다.")
        return pd.DataFrame(columns=EV_COLS)

    E = E.sort_values(["month", "code"]).reset_index(drop=True)
    out = E[[c for c in EV_COLS if c in E.columns] +
            [c for c in ("in_uni", "liq_pass", "mcap", "adv20", "n_new_brokers") if c in E.columns]]
    PIPE.io("OUT", "MEM", "coverage_events", out, source="H1/H2 판정")
    VAULT.put_table(f"event_log_{STRATEGY_ID}", out, scope="private", domain="events",
                    source="build_coverage_events",
                    extra={"lookback_m": L, "burnin_m": B, "valid_start": str(vs.date())})
    return out


def _ncq_attach_analyst_new(E: pd.DataFrame, links: pd.DataFrame, L: int) -> pd.DataFrame:
    """애널리스트 단위 신규 여부(보조 지표). 애널리스트를 식별한 부분집합에서만 값이 채워진다."""
    x = links.dropna(subset=["stock_code"]).copy()
    if x.empty:
        return E
    x["code"] = x["stock_code"].map(to_code6)
    x = x.dropna(subset=["code"])
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    x["mi"] = _ncq_mi(x["pub_date"] + pd.offsets.MonthEnd(0))
    a = (x.groupby(["code", "analyst_id", "mi"], observed=True).size().rename("n").reset_index()
          .sort_values(["code", "analyst_id", "mi"]))
    a["prev_mi"] = a.groupby(["code", "analyst_id"], observed=True)["mi"].shift(1)
    a["new"] = a["prev_mi"].isna() | ((a["mi"] - a["prev_mi"]) > L)
    an = (a[a["new"]].groupby(["code", "mi"], observed=True)
            .agg(analyst_new=("analyst_id", "nunique")).reset_index())
    E = E.drop(columns=["analyst_new"], errors="ignore").merge(an, on=["code", "mi"], how="left")
    cov = float(E["analyst_new"].notna().mean()) if len(E) else 0.0
    LOG.info(f"애널리스트 단위 보조 판정 커버리지 {100*cov:.1f}% — 네이버 단독 건은 리스트에 "
             f"작성자가 없어 PDF 추출에 의존하므로 낮게 나오는 것이 정상입니다.")
    return E


def audit_events(EV: pd.DataFrame, REP: pd.DataFrame) -> dict:
    """이벤트 원장 감사 — 명세 §12 의 R2·R3 경고를 여기서 낸다."""
    out: Dict[str, Any] = {}
    if EV is None or EV.empty:
        LOG.warn("이벤트가 없어 감사를 수행할 수 없습니다.")
        return {"n_events": 0}
    n = len(EV)
    n_m = max(EV["month"].nunique(), 1)
    per_m = n / n_m
    grp = Counter(EV["sponsor_group"].astype(str))
    typ = Counter(EV["event_type"].astype(str))
    irs_share = (grp.get("SPONSORED_ONLY", 0) + 0.5 * grp.get("MIXED", 0)) / max(n, 1)

    LOG.table([["총 이벤트", f"{n:,}"],
               ["관측 월수", f"{n_m}"],
               ["월평균 이벤트", f"{per_m:.1f}"],
               ["H1 de novo", f"{typ.get('H1',0):,} ({100*typ.get('H1',0)/n:.0f}%)"],
               ["H2 broker-new", f"{typ.get('H2',0):,} ({100*typ.get('H2',0)/n:.0f}%)"],
               ["ORGANIC_ONLY", f"{grp.get('ORGANIC_ONLY',0):,} ({100*grp.get('ORGANIC_ONLY',0)/n:.0f}%)"],
               ["SPONSORED_ONLY", f"{grp.get('SPONSORED_ONLY',0):,} ({100*grp.get('SPONSORED_ONLY',0)/n:.0f}%)"],
               ["MIXED", f"{grp.get('MIXED',0):,} ({100*grp.get('MIXED',0)/n:.0f}%)"],
               ["고유 종목", f"{EV['code'].nunique():,}"]],
              ["항목", "값"], ["l", "r"], title="신규 커버리지 이벤트 감사")

    if per_m < NCQ_MIN_EVENTS_PER_MONTH:
        LOG.warn(f"★ 월평균 이벤트가 {per_m:.1f}건으로 기준({NCQ_MIN_EVENTS_PER_MONTH}건) 미만입니다. "
                 f"횡단면 z-score 가 불안정해지고 통계 검정력이 부족합니다. 리포트 최상단에 "
                 f"경고로 표시됩니다(명세 §5.2).")
    if n < NCQ_MIN_TOTAL_EVENTS:
        LOG.warn(f"★ 총 이벤트 {n:,}건이 기준({NCQ_MIN_TOTAL_EVENTS:,}건) 미만입니다. "
                 f"어떤 결과도 강한 결론으로 취급하지 마십시오(명세 §12 R3).")
    if irs_share > NCQ_SPONSOR_WARN_FRAC:
        LOG.warn(f"★ 스폰서(IR협의회) 비중이 {100*irs_share:.0f}% 로 기준"
                 f"({100*NCQ_SPONSOR_WARN_FRAC:.0f}%)을 넘습니다. 이 전략은 '신규 커버리지 알파'가 "
                 f"아니라 'IR 활동 팩터'일 가능성이 큽니다(명세 §12 R2). P3(ORGANIC_ONLY 유지) "
                 f"검정 결과를 헤드라인보다 우선해서 보십시오.")

    out = {"n_events": int(n), "months": int(n_m), "per_month": float(per_m),
           "type_mix": {k: int(v) for k, v in typ.items()},
           "sponsor_mix": {k: int(v) for k, v in grp.items()},
           "irs_share": float(irs_share), "n_codes": int(EV["code"].nunique())}
    manifest_put("events", out)
    return out
