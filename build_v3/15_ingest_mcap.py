

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-M  시가총액 · 상장주식수  (U-MICRO 유니버스의 정의 입력 · PBR/PER 의 분모)             ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 없으면 이 전략은 성립하지 않는다.                                            ║
# ║    U-MICRO 는 "시총 랭크 1400위 밖"으로 정의되고, 방화벽의 딥밸류 조항은 PBR·PER 을        ║
# ║    쓴다. 둘 다 '그 시점의' 시가총액을 요구한다.                                            ║
# ║                                                                                          ║
# ║  ★ C13 (유니버스는 PIT) 을 지키는 유일한 방법 ─────────────────────────────────────────  ║
# ║    현재 시총을 과거에 그대로 적용하면 "지금 소형주인 기업"만 과거 유니버스가 되어          ║
# ║    소형→중형 전환에 성공한 종목이 정의상 사라진다. 그게 바로 이 전략이 찾는 대상이므로     ║
# ║    성공 사례만 골라 지우는 꼴이 된다.                                                     ║
# ║    → 시총은 '스냅샷 상장주식수(as-of)' × '그날 종가' 로 매 시점 재구성한다.                 ║
# ║      상장주식수는 느리게 변하므로 as-of 캐리가 타당하고, 종가는 일별로 정확하다.           ║
# ║                                                                                          ║
# ║  소스 우선순위 (앞에서 실패하면 다음으로, 무엇이 쓰였는지 전부 표로 출력)                   ║
# ║    ① 드라이브 공용 캐시 (다른 전략이 모아둔 것도 그대로 재사용)                             ║
# ║    ② pykrx 시가총액 스냅샷      — KRXG 게이트로 직렬화 (CD011 방지)                        ║
# ║    ③ KRX 마켓플레이스 bld 조회  — 로그인 세션이 있을 때                                    ║
# ║    ④ DART 주식총수 현황         — 접수일자 기준이라 PIT 로 정확. 잔여 종목만 한도 내에서    ║
# ║    ⑤ FDR 현재 상장주식수        — ★비PIT. 최후수단이며 감사표에 '근사'로 명시한다          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MCAP_SNAP_COLS = ["snap_date", "code", "shares", "mcap", "src"]

# KRX 마켓플레이스 '전종목 시세' bld — 시가총액·상장주식수를 한 번에 준다.
KRX_BLD_ALLPRICE = "dbms/MDC/STAT/standard/MDCSTAT01501"


def _mcap_from_pykrx(days: Sequence[pd.Timestamp]) -> List[dict]:
    """pykrx 시가총액 스냅샷. 전부 KRXG 게이트를 통과시켜 직렬화한다."""
    if pykrx_stock is None or not days:
        return []
    rows: List[dict] = []
    bad_streak = 0
    for d in tqdm(days, desc="시총 스냅샷(pykrx)", ncols=88, leave=False):
        bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                       d.strftime("%Y%m%d"), prev=True) or d.strftime("%Y%m%d")
        got = False
        for mkt in ("KOSPI", "KOSDAQ"):
            t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
            if t is None or len(t) == 0:
                continue
            t = t.reset_index()
            ren = {"티커": "code", "시가총액": "mcap", "상장주식수": "shares"}
            t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
            if "code" not in t.columns:
                t = t.rename(columns={t.columns[0]: "code"})
            if "mcap" not in t.columns and "shares" not in t.columns:
                continue
            got = True
            for r in t.itertuples(index=False):
                c = to_code6(getattr(r, "code", None))
                if not c:
                    continue
                rows.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                             "shares": float(getattr(r, "shares", np.nan) or np.nan),
                             "mcap": float(getattr(r, "mcap", np.nan) or np.nan),
                             "src": "pykrx"})
        bad_streak = 0 if got else bad_streak + 1
        if bad_streak >= 5:
            LOG.warn("시총 스냅샷이 연속 5회 비었습니다 — KRX 세션이 끊겼거나 차단된 상태입니다. "
                     "다음 소스로 폴백합니다(정상 동작).")
            break
    return rows


def _mcap_from_krx_marketplace(days: Sequence[pd.Timestamp]) -> List[dict]:
    """KRX 마켓플레이스 bld 조회. 세션이 없으면 json_data 가 None 을 돌려주므로 조용히 빈 목록."""
    if not getattr(KRX, "session_ok", False) or not days:
        return []
    rows: List[dict] = []
    bad_streak = 0
    for d in tqdm(days, desc="시총 스냅샷(KRX)", ncols=88, leave=False):
        js = KRX.json_data(KRX_BLD_ALLPRICE, mktId="ALL", trdDd=d.strftime("%Y%m%d"))
        blk = (js or {}).get("OutBlock_1") or (js or {}).get("output") or []
        if not blk:
            bad_streak += 1
            if bad_streak >= 5:
                LOG.warn("KRX 마켓플레이스 시총 조회가 연속 5회 비었습니다 — 중단하고 폴백합니다.")
                break
            continue
        bad_streak = 0
        for r in blk:
            c = to_code6(r.get("ISU_SRT_CD"))
            if not c:
                continue
            rows.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                         "shares": _num(r.get("LIST_SHRS")), "mcap": _num(r.get("MKTCAP")),
                         "src": "krx_mp"})
    return rows


def _num(x) -> float:
    """'1,234,567' · '-' · None 을 안전하게 float 로. 콤마를 안 지우면 전부 NaN 이 된다."""
    try:
        s = str(x).replace(",", "").replace(" ", "")
        if s in ("", "-", "None", "nan"):
            return float("nan")
        return float(s)
    except Exception:
        return float("nan")


def _shares_from_dart(corp_codes: Sequence[str], years: Sequence[int],
                      cap_calls: int = 4000) -> pd.DataFrame:
    """DART 주식총수 현황(stockTotqySttus). 접수일자가 knowledge_date 라 PIT 로 정확하다.

    잔여 종목(스냅샷에 한 번도 안 잡힌 코드)에만 쓴다. 전 종목×전 분기로 돌리면
    일일 호출한도(20,000)를 그대로 태우므로 연 1회(사업보고서)로 제한한다.
    """
    if not DART_API_KEY or not len(corp_codes):
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "shares_dart"])
    jobs = [(cc, y) for cc in corp_codes for y in years][:cap_calls]
    if not jobs:
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "shares_dart"])
    LOG.info(f"DART 주식총수 현황 {len(jobs):,}건 조회 (스냅샷 미확보 종목 보강 · 연 1회 기준)")

    def _one(job):
        cc, y = job
        js = dart_api("stockTotqySttus", {"corp_code": cc, "bsns_year": str(y),
                                          "reprt_code": REPRT_CODES["FY"]})
        if not js or js.get("status") != "000":
            return None
        out = []
        for r in js.get("list", []) or []:
            # se(구분)가 '합계'인 행이 발행주식총수. 보통주/우선주 행을 더하면 이중계상된다.
            se = str(r.get("se", ""))
            if "합계" not in se:
                continue
            q = _num(r.get("istc_totqy"))
            tr = _num(r.get("tesstk_co"))          # 자기주식 수 (있으면 차감이 더 정확)
            if not np.isfinite(q) or q <= 0:
                continue
            rc = str(r.get("rcept_no") or "")
            kd = as_ts(rc[:8]) if len(rc) >= 8 else None
            if kd is None:
                continue
            out.append({"corp_code": cc, "knowledge_date": kd,
                        "shares_dart": q - (tr if np.isfinite(tr) else 0.0)})
        return out or None

    res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
    rows = [x for sub in res if sub for x in sub]
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["corp_code", "knowledge_date", "shares_dart"])


def _shares_from_fdr() -> pd.DataFrame:
    """FDR 상장목록의 현재 상장주식수/시총. ★현재 시점 값이므로 PIT 가 아니다.
    최후수단이며, 쓰였다는 사실을 감사표에 반드시 남긴다."""
    if fdr is None:
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    try:
        d = fdr.StockListing("KRX")
    except Exception as e:                                             # noqa
        LOG.debug(f"FDR StockListing 실패: {type(e).__name__}")
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    if d is None or len(d) == 0:
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    lm = {str(c).lower(): c for c in d.columns}
    ccol = lm.get("code") or lm.get("symbol")
    scol = lm.get("stocks") or lm.get("shares")
    mcol = lm.get("marcap") or lm.get("markatcap") or lm.get("marketcap")
    if not ccol:
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    out = pd.DataFrame({"code": d[ccol].map(to_code6)})
    out["shares_now"] = pd.to_numeric(d[scol], errors="coerce") if scol else np.nan
    out["mcap_now"] = pd.to_numeric(d[mcol], errors="coerce") if mcol else np.nan
    return out.dropna(subset=["code"]).drop_duplicates("code")


def fetch_mcap_snapshots(months: pd.DatetimeIndex, sec: Optional[pd.DataFrame] = None
                         ) -> pd.DataFrame:
    """월/분기 격자의 (code, shares, mcap) 스냅샷. 캐시 우선 · 다중소스 폴백.

    반환: snap_date, code, shares, mcap, src   (전 소스 통합, 중복 제거)
    """
    cached = VAULT.get_table("krx_mcap_snapshots", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        c["snap_date"] = as_ts_series(c["snap_date"])
        c = c.dropna(subset=["snap_date", "code"])
        for col_ in ("shares", "mcap"):
            if col_ not in c.columns:
                c[col_] = np.nan
        if "src" not in c.columns:
            c["src"] = "cache"
        have = set(c["snap_date"].dt.strftime("%Y-%m-%d"))
        frames.append(c[MCAP_SNAP_COLS])
        LOG.ok(f"공용 캐시에서 시총 스냅샷 {len(have)}개 시점 · {len(c):,}행 재사용 "
               f"(다른 전략이 모아둔 것도 그대로 씁니다)")

    grid = _snapshot_grid(months)
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 미확보 {len(todo)}개 시점은 신규 수집하지 않습니다.")
        todo = []

    new_rows: List[dict] = []
    if todo:
        KRXG.warmup()
        new_rows += _mcap_from_pykrx(todo)
        done = {r["snap_date"] for r in new_rows}
        rest = [d for d in todo if d.strftime("%Y-%m-%d") not in done]
        if rest:
            new_rows += _mcap_from_krx_marketplace(rest)

    if new_rows:
        frames.append(pd.DataFrame(new_rows))

    if not frames:
        LOG.warn("시총 스냅샷을 한 건도 확보하지 못했습니다. FDR 현재값으로 근사하며, "
                 "이 경우 유니버스 랭크는 '현재 시총 기준 근사'가 되어 C13 이 부분적으로만 "
                 "충족됩니다. 감사표에 그대로 표시합니다.")
        return pd.DataFrame(columns=MCAP_SNAP_COLS)

    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap["code"] = snap["code"].map(to_code6)
    snap = snap.dropna(subset=["snap_date", "code"])
    # shares 가 없고 mcap 만 있는 소스가 섞일 수 있다 — 둘 다 없는 행만 버린다.
    snap = snap[snap["shares"].notna() | snap["mcap"].notna()]
    snap = (snap.sort_values(["snap_date", "code", "src"])
                .drop_duplicates(["snap_date", "code"], keep="first")[MCAP_SNAP_COLS])

    # 부분 응답 방어 — 이웃 시점 대비 급감한 스냅샷은 진실이 아니라 사고다(유니버스 축소 → 선택편향).
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"시총 스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만이라 "
                     f"부분 응답으로 판단하고 폐기합니다.")
            snap = snap[~snap["snap_date"].isin(bad.index)]

    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_mcap_snapshots", out, scope="shared", domain="universe",
                        source="pykrx|krx_mp",
                        extra={"note": "시가총액·상장주식수 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_mcap_snapshots", snap, source="pykrx|krx_mp")
    LOG.ok(f"시총 스냅샷 {len(snap):,}행 · {snap['snap_date'].nunique()}개 시점 · "
           f"{snap['code'].nunique():,}종목")
    return snap


def build_mcap_panel(price_m: pd.DataFrame, snap: pd.DataFrame, sec: pd.DataFrame,
                     months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 (code, month) → shares/mcap/mcap_rank.

    시총 = as-of 상장주식수 × 월말 종가.  스냅샷이 분기라도 월별로 정확히 복원된다.
    ★ merge_asof 단일 패스 (원칙 #1). 종목×시점 루프 금지.
    """
    base = price_m[["code", "month", "close"]].copy()
    base["code"] = base["code"].astype(str)
    # ★ 타입 방어. snap_date/month 가 문자열로 들어오면 merge_asof 는 MergeError 로 죽고,
    #   상위에서 잡아 폴백하면 시총이 통째로 결측이 되어 유니버스가 조용히 비어 버린다.
    #   (실제로 이 경로에서 U-MICRO 0종목 사고가 났다 — 여기서 원천 차단한다)
    base["month"] = as_ts_series(base["month"])
    base = base.dropna(subset=["month"])
    base["_ord"] = np.arange(len(base))
    src_used: Counter = Counter()

    shares = pd.Series(np.nan, index=base.index, dtype="float64")
    mcap_snap = pd.Series(np.nan, index=base.index, dtype="float64")

    # ① 스냅샷 as-of 결합 (backward = 그 시점에 알 수 있었던 마지막 스냅샷)
    if snap is not None and len(snap):
        R = snap.copy()
        R["snap_date"] = as_ts_series(R["snap_date"])
        R["code"] = R["code"].astype(str)
        for _c in ("shares", "mcap"):
            R[_c] = pd.to_numeric(R[_c], errors="coerce") if _c in R.columns else np.nan
        R = R.dropna(subset=["snap_date", "code"]).sort_values("snap_date", kind="stable")
        L = base.dropna(subset=["month"]).sort_values("month", kind="stable")
        try:
            M = pd.merge_asof(L, R[["snap_date", "code", "shares", "mcap"]],
                              left_on="month", right_on="snap_date", by="code",
                              direction="backward")
            M = M.set_index("_ord")
            shares = M["shares"].reindex(base["_ord"]).to_numpy()
            mcap_snap = M["mcap"].reindex(base["_ord"]).to_numpy()
            shares = pd.Series(shares, index=base.index)
            mcap_snap = pd.Series(mcap_snap, index=base.index)
            src_used["스냅샷(PIT)"] = int(pd.notna(shares).sum())
        except Exception as e:                                         # noqa
            LOG.warn(f"시총 스냅샷 as-of 결합 실패({type(e).__name__}) — 폴백으로 진행합니다.")

    # ② DART 주식총수 (PIT) — 스냅샷이 못 채운 종목만
    miss_codes = sorted(set(base.loc[shares.isna(), "code"]))
    if miss_codes and DART_API_KEY and RUN_MODE == "FULL":
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict())
        ccs = [c2c[c] for c in miss_codes if c in c2c][:1200]
        yrs = sorted({int(m.year) for m in months})
        D = _shares_from_dart(ccs, yrs)
        if len(D):
            inv = {v: k for k, v in c2c.items()}
            D["code"] = D["corp_code"].map(inv)
            D = D.dropna(subset=["code", "knowledge_date"]).sort_values("knowledge_date")
            L2 = base.loc[shares.isna(), ["code", "month", "_ord"]].dropna(subset=["month"])
            L2 = L2.sort_values("month", kind="stable")
            try:
                M2 = pd.merge_asof(L2, D[["knowledge_date", "code", "shares_dart"]],
                                   left_on="month", right_on="knowledge_date", by="code",
                                   direction="backward")
                fill = M2.set_index("_ord")["shares_dart"]
                idx = base.set_index("_ord").index
                add = fill.reindex(idx).to_numpy()
                add = pd.Series(add, index=base.index)
                n_before = int(shares.notna().sum())
                shares = shares.where(shares.notna(), add)
                src_used["DART 주식총수(PIT)"] = int(shares.notna().sum()) - n_before
            except Exception as e:                                     # noqa
                LOG.debug(f"DART 주식총수 결합 실패: {type(e).__name__}")

    # ③ FDR 현재 상장주식수 — ★비PIT 최후수단
    if shares.isna().any():
        F = _shares_from_fdr()
        if len(F):
            m = base["code"].map(F.set_index("code")["shares_now"].to_dict())
            n_before = int(shares.notna().sum())
            shares = shares.where(shares.notna(), m)
            n_add = int(shares.notna().sum()) - n_before
            if n_add:
                src_used["FDR 현재값(비PIT 근사)"] = n_add

    mcap = shares * base["close"]
    # 스냅샷이 mcap 을 직접 준 행은 그 값을 신뢰한다(우선주 등 복수종목 합산 이슈 회피).
    mcap = mcap_snap.where(mcap_snap.notna() & (mcap_snap > 0), mcap)

    out = base[["code", "month"]].copy()
    out["shares"] = shares.to_numpy()
    out["mcap"] = mcap.to_numpy()
    # ★ 랭크는 매 시점 재산출한다(C13-a). 1=최대 시총.
    out["mcap_rank"] = out.groupby("month", observed=True)["mcap"].rank(
        ascending=False, method="first")
    out["mcap_pctl"] = out.groupby("month", observed=True)["mcap"].rank(
        ascending=False, pct=True)

    cov = float(out["mcap"].notna().mean()) if len(out) else 0.0
    rows = [[k, f"{v:,}", f"{100*v/max(len(out),1):.1f}%"] for k, v in src_used.items()]
    rows.append(["결측(시총 미상)", f"{int(out['mcap'].isna().sum()):,}",
                 f"{100*out['mcap'].isna().mean() if len(out) else 0:.1f}%"])
    LOG.table(rows, ["상장주식수 출처", "행수", "비중"], ["l", "r", "r"],
              title="시가총액 구성 출처 (C13 — '비PIT 근사'가 크면 유니버스 정의가 흔들립니다)")
    if src_used.get("FDR 현재값(비PIT 근사)", 0) > 0.30 * max(len(out), 1):
        LOG.warn("시총의 30% 이상이 '현재 상장주식수' 근사로 채워졌습니다. 상장주식수는 느리게 "
                 "변하므로 랭크 왜곡은 제한적이지만, 무상증자·액면분할이 잦았던 종목에서 "
                 "과거 시총이 과대평가될 수 있습니다. KRX ID/PW 를 넣으면 PIT 스냅샷으로 대체됩니다.")
    if cov < 0.50:
        LOG.warn(f"시총 커버리지가 {100*cov:.0f}% 로 낮습니다. U-MICRO 정의가 시총 랭크에 "
                 f"의존하므로, 커버리지가 낮으면 유니버스가 좁아집니다. "
                 f"§6 감쇠 감사표에서 어느 게이트가 깎는지 확인하세요.")
    PIPE.io("OUT", "MEM", "mcap_panel", out)
    return downcast(out)
