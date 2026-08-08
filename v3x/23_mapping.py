# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  HS 유니버스 큐레이션 + 매핑 4중 게이트                                                     ║
# ║                                                                                             ║
# ║  ★ 여기가 이 전략의 최대 자유도이자 최대 과적합 통로다(§15.2).                              ║
# ║    그래서 구조로 막는다:                                                                     ║
# ║      · 채택 기준은 넷뿐 — (연계표, 생산자 수, 단위 정합성, 커모디티 지표).                   ║
# ║        성과 정보는 어떤 형태로도 들어가지 않는다.                                            ║
# ║      · 확정된 목록은 `hs_universe_preregistered.csv` 로 **사전등록**되고,                    ║
# ║        다음 실행부터는 그 파일이 진실이다. 코드가 다시 고르지 않는다.                        ║
# ║      · 목록이 바뀌면 수정 이력이 파일에 남고, 리포트가 수정 전/후 성과를 **둘 다** 낸다.     ║
# ║                                                                                             ║
# ║  ★ C3 (PIT 라벨 고정): valid_from = 그 제품구성을 알 수 있게 된 사업보고서 접수일.           ║
# ║    2024년 사업보고서로 알게 된 구성을 2022년 백테스트에 쓰면 성과는 전부 가짜다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

PREREG_FILE = "hs_universe_preregistered.csv"

# HS 章(2자리) ↔ KSIC 대·중분류 개략 대응. **연계표를 못 구했을 때의 폴백이다.**
# 정밀 매핑이 아니라 '후보 집합을 만드는 1차 그물'이며, 실제 채택은 게이트 1~3 이 결정한다.
# 이 표를 쓰게 되면 CANARY X6 을 DEGRADED 로 보고하고 정밀도 저하를 명시한다.
HS2_KSIC_SEED: "dict[str, tuple]" = {
    "28": ("20",), "29": ("20",), "32": ("20",), "34": ("20",), "38": ("20",),
    "39": ("20", "22"), "40": ("22",),
    "30": ("21",), "33": ("20", "21"),
    "72": ("24",), "73": ("24", "25"), "74": ("24",), "75": ("24",), "76": ("24",),
    "78": ("24",), "79": ("24",), "80": ("24",), "81": ("24",), "82": ("25",), "83": ("25",),
    "84": ("29",), "85": ("26", "28"), "90": ("27",), "91": ("27",),
    "86": ("31",), "87": ("30",), "88": ("31",), "89": ("31",),
    "48": ("17",), "49": ("18",),
    "50": ("13",), "51": ("13",), "52": ("13",), "53": ("13",), "54": ("13",),
    "55": ("13",), "56": ("13",), "57": ("13",), "58": ("13",), "59": ("13",),
    "60": ("13",), "61": ("14",), "62": ("14",), "63": ("14",), "64": ("15",), "65": ("14",),
    "68": ("23",), "69": ("23",), "70": ("23",), "71": ("23", "33"),
    "94": ("32",), "95": ("32",), "96": ("32",),
    "16": ("10",), "17": ("10",), "18": ("10",), "19": ("10",), "20": ("10",),
    "21": ("10",), "22": ("11",),
    "27": ("19",),
}


def fetch_hs_ksic_concordance() -> Tuple[pd.DataFrame, str]:
    """CANARY X6 — HS ↔ KSIC 연계표를 확보한다.

    반환 (표, 상태) 이며 상태는 "OK" / "DEGRADED" / "FAIL".
    ★ 없는 것을 있는 척하지 않는다. 씨앗 표로 떨어지면 DEGRADED 로 보고하고
      매핑 정밀도가 낮아졌으므로 게이트 1~3 이 더 중요해졌음을 로그에 남긴다.
    """
    # ① 캐시(공용) — 다른 전략이 이미 받아 뒀을 수 있다
    for src in (lambda: VAULT.get_table("hs_ksic_concordance", scope="shared"),
                lambda: (FOREIGN.load("hs_map", "hs_ksic_concordance", "hs_ksic")
                         if FOREIGN is not None else None)):
        try:
            d = src()
        except Exception:                                               # noqa
            d = None
        if d is not None and len(d):
            cols = {c.lower(): c for c in d.columns}
            hc = next((cols[c] for c in ("hs", "hs_code", "hscd", "hs2", "hs6") if c in cols), None)
            kc = next((cols[c] for c in ("ksic", "ksic_code", "induty", "induty_code")
                       if c in cols), None)
            if hc and kc:
                out = pd.DataFrame({"hs": d[hc].astype(str), "ksic": d[kc].astype(str)})
                LOG.ok(f"HS–KSIC 연계표 캐시 재사용: {len(out):,}행")
                return out.dropna().drop_duplicates(), "OK"

    # ② 씨앗 표로 폴백
    rows = []
    for hs2, ks in HS2_KSIC_SEED.items():
        for k in ks:
            rows.append({"hs": hs2, "ksic": k})
    seed = pd.DataFrame(rows)
    LOG.warn("HS–KSIC 연계표를 외부에서 확보하지 못해 내장 씨앗표(章↔KSIC 중분류)로 진행합니다. "
             "매핑 정밀도가 낮아지므로 게이트1(합계정합성)·게이트2(자기공시)·게이트3(플라시보)의 "
             "판정이 그만큼 더 중요해집니다. CANARY X6 = DEGRADED 로 보고합니다.")
    return seed, "DEGRADED"


def curate_hs_universe(cx: pd.DataFrame, sec: pd.DataFrame, conc: pd.DataFrame,
                       max_firms: int = HS_OLIGOPOLY_MAX_FIRMS,
                       digits: int = HS_DIGIT_LEVEL,
                       min_months: int = HS_MIN_MONTHS) -> pd.DataFrame:
    """§5.2 큐레이션. 사전등록 파일이 있으면 **무조건 그것을 따른다**.

    반환: hs, n_firms, months, cv_dest, adopted, reason
    """
    prereg_path = os.path.join(VAULT.table_dir("private"), PREREG_FILE)
    if os.path.exists(prereg_path):
        try:
            pre = pd.read_csv(prereg_path, dtype={"hs": str})
            _n_pre = int(pd.to_numeric(pre.get("adopted"), errors="coerce").fillna(0).sum())
            # ★★ 실패한 실행을 영구 고정하지 않는다 ★★
            #   사전등록의 목적은 '성과를 보고 목록을 고치는 것'을 막는 것이지,
            #   **버그로 0개가 나온 실행을 영원히 박제하는 것**이 아니다.
            #   실제로 첫 실행이 induty_code 결함으로 0개를 등록했고, 그 뒤로는 무엇을 고쳐도
            #   이 파일 때문에 계속 0개가 됐다. 사용자가 파일을 지우지 않는 한 회복 불가였다.
            if _n_pre <= 0:
                bak = prereg_path + f".empty.{_dt.datetime.now():%Y%m%d_%H%M%S}"
                try:
                    shutil.copy2(prereg_path, bak)
                except Exception:                                       # noqa
                    pass
                LOG.warn(f"사전등록 파일의 채택 HS 가 0개입니다 — 실패한 실행이 박제된 상태로 "
                         f"판단하고 **무시하고 다시 산출**합니다 "
                         f"(원본은 {os.path.basename(bak)} 로 보존).")
            else:
                LOG.ok(f"사전등록 HS 유니버스를 따릅니다: {prereg_path} "
                       f"({_n_pre:,}개 채택) — 성과를 보고 이 파일을 고치지 마세요(§15.2).")
                return pre
        except Exception as e:                                          # noqa
            # ★ 읽기 실패는 '파일이 잘못됐다'는 뜻이 아니라 인코딩·pandas 버전 문제일 수 있다.
            #   그대로 덮어쓰면 사전등록의 존재 이유(사후 변경 방지)가 무너진다. 백업부터 한다.
            bak = prereg_path + f".unreadable.{_dt.datetime.now():%Y%m%d_%H%M%S}"
            try:
                shutil.copy2(prereg_path, bak)
                LOG.warn(f"사전등록 파일을 읽지 못했습니다({type(e).__name__}) — "
                         f"{os.path.basename(bak)} 로 보존한 뒤 새로 생성합니다.")
            except Exception:                                           # noqa
                LOG.error(f"사전등록 파일을 읽지도 백업하지도 못했습니다({type(e).__name__}). "
                          f"덮어쓰지 않고 이번 실행에서만 임시 목록을 씁니다.")
                prereg_path = prereg_path + f".tmp{_dt.datetime.now():%H%M%S}"

    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "n_firms", "months", "cv_dest", "adopted", "reason"])

    d = cx.copy()
    d["hs"] = d["hs"].astype(str)
    # ★ HS 는 **좌측 정렬 계층코드**다. zfill 은 왼쪽을 채워 "85"→"000085" 로 만들고
    #   그러면 章이 "00" 이 되어 매핑이 통째로 0건이 된다. 절대 zfill 하지 않는다.
    d["hs_k"] = d["hs"].str.slice(0, digits)

    # 관측 개월수 — 롤링 36M OLS 가 돌 수 있어야 한다.
    obs = d.groupby("hs_k", observed=True)["ym"].nunique().rename("months").reset_index()

    # 후보 상장사 수: KSIC 경유로 HS 章 → 상장사 집합
    ind = sec.copy()
    ind["ksic2"] = ind.get("induty_code", pd.Series("", index=ind.index)).astype(str).str[:2]
    cmap = conc.copy()
    cmap["hs2"] = cmap["hs"].astype(str).str.zfill(2).str[:2]
    cmap["ksic2"] = cmap["ksic"].astype(str).str.zfill(2).str[:2]
    link = cmap.merge(ind[["code", "ksic2"]], on="ksic2", how="inner")
    nfirm = link.groupby("hs2", observed=True)["code"].nunique().rename("n_firms").reset_index()

    out = obs.copy()
    out["hs2"] = out["hs_k"].str[:2]
    out = out.merge(nfirm, on="hs2", how="left")
    out["n_firms"] = out["n_firms"].fillna(0).astype(int)

    cvd = customs_cv_dest(d.assign(hs=d["hs_k"]))
    out = out.merge(cvd.rename(columns={"hs": "hs_k"}), on="hs_k", how="left")

    # ── 채택 규칙 — 기준은 넷뿐이고 성과는 보지 않는다.
    #   ★ 다만 '생산자 1~3개'는 **연계표가 세밀할 때만** 성립하는 기준이다.
    #     씨앗표(章↔KSIC 중분류)로 떨어지면 한 章에 상장사가 수백 개씩 잡혀 아무도 통과하지
    #     못하고 유니버스가 0 이 된다(실측: 채택 0/924).
    #     명세 §12.2 가 "과점 기준 완화 후 재측정"을 명시했으므로, 완화를 **사다리로 자동화하고
    #     어느 칸을 썼는지 표로 남긴다.** 조용히 완화하면 그게 곧 과적합 통로다.
    m2 = out["months"] >= min_months
    ladder, chosen, note = [], None, ""
    for cap in (max_firms, 5, 10, 20, 40, 80):
        if cap < max_firms:
            continue
        n_ok = int((out["n_firms"].between(1, cap) & m2).sum())
        ladder.append([f"생산자 1~{cap}개", f"{n_ok:,}"])
        if chosen is None and n_ok >= 20:
            chosen, note = cap, ("사양 기준" if cap == max_firms else
                                 f"§12.2 완화 적용 (원 기준 1~{max_firms})")
    if chosen is None:
        # 절대 기준으로는 표본이 안 나온다 → **상대 기준**(생산자 수 하위 1/3)으로 내려간다.
        thr = float(out.loc[m2, "n_firms"].replace(0, np.nan).quantile(0.33)) \
            if int(m2.sum()) else np.nan
        chosen = int(thr) if np.isfinite(thr) and thr >= 1 else 0
        note = (f"절대 기준으로 표본 부족 → **상대 기준**(생산자 수 하위 1/3, 임계 {chosen}개)으로 "
                f"전환. 이는 사양의 '과점'이 아니라 '상대적 저경쟁'이며, 매핑 귀속력이 그만큼 약합니다.")
        ladder.append([f"상대기준 하위1/3 (≤{chosen}개)",
                       f"{int((out['n_firms'].between(1, max(chosen, 1)) & m2).sum()):,}"])

    m1 = out["n_firms"].between(1, max(chosen, 1))
    # ★ f-string 안에 Series 를 넣으면 **모든 행에 Series 전체 repr** 이 박힌다(칸당 수천 자).
    #   사유는 행마다 달라야 하므로 벡터 연결로 만든다.
    reason = pd.Series("", index=out.index, dtype=object)
    reason = reason.where(m1, reason + "생산자수 " + out["n_firms"].astype(str)
                          + f" ∉ [1,{chosen}]; ")
    reason = reason.where(m2, reason + "관측개월 " + out["months"].astype(str)
                          + f"<{min_months}; ")
    ok = m1 & m2
    out["adopted"] = ok.astype(int)
    out["reason"] = reason.where(~ok, "채택")
    out["n_firms_cap"] = chosen

    # ★ 사다리는 생산자 수만 흔든다. 관측개월이 걸린 경우에도 전부 0 이 찍혀
    #   '무엇 때문에 0인지' 알 수 없다 → 기준별 단독 통과 수를 함께 낸다.
    LOG.table([["관측개월 ≥ %d" % min_months, f"{int(m2.sum()):,} / {len(out):,}"],
               ["생산자 수 1개 이상", f"{int((out['n_firms'] >= 1).sum()):,} / {len(out):,}"],
               ["생산자 수 중앙값", f"{float(out['n_firms'].median()):.0f}"],
               ["관측개월 중앙값", f"{float(out['months'].median()):.0f}"]],
              ["단독 기준", "통과"])
    if int(m2.sum()) == 0:
        LOG.error(f"관측개월 {min_months}개월 이상인 HS 가 **하나도 없습니다** — 생산자 기준을 아무리 "
                  f"완화해도 채택은 0 입니다. 통관 수집 구간이 짧거나(HS_MIN_MONTHS={min_months}) "
                  f"수집이 실패한 것입니다. 관측개월 중앙값 "
                  f"{float(out['months'].median()):.0f}개월을 먼저 확인하세요.")
    if int((out["n_firms"] >= 1).sum()) == 0:
        LOG.error("생산자(상장사)가 연결된 HS 가 **하나도 없습니다** — KSIC 업종코드(induty_code)를 "
                  "확보하지 못했거나 연계표가 비어 있습니다. DART_API_KEY 와 CANARY X6 을 확인하세요.")
    LOG.banner("HS 채택 기준 사다리 (§12.2 완화 이력)",
               f"채택 {int(ok.sum()):,}개 · 적용 기준 '생산자 1~{chosen}개' — {note}")
    LOG.table(ladder, ["기준", "채택 가능 HS"])
    if chosen > max_firms:
        LOG.warn(f"과점 기준을 {max_firms} → {chosen} 으로 완화했습니다. HS 하나에 상장사가 여럿이면 "
                 f"통관 신호를 특정 기업에 귀속시키기 어려워집니다 — 매핑 가중치를 1/n_firms 로 "
                 f"낮추고, 게이트3(플라시보)이 실제로 이 매핑을 지지하는지 반드시 확인하세요. "
                 f"연계표(X6)를 세밀한 것으로 교체하면 이 완화가 필요 없어집니다.")
    out = out.rename(columns={"hs_k": "hs"})[
        ["hs", "n_firms", "months", "cv_dest", "adopted", "reason"]]

    # 사전등록 — 이후 실행에서 이 파일이 진실이 된다.
    try:
        _ensure_dir(prereg_path)
        out.assign(preregistered_at=_dt.datetime.now().isoformat(timespec="seconds"),
                   build=BUILD_VERSION).to_csv(prereg_path, index=False, encoding="utf-8-sig")
        LOG.ok(f"HS 유니버스를 사전등록했습니다 → {prereg_path} "
               f"(채택 {int(out['adopted'].sum())}/{len(out)}). "
               f"이후 실행은 이 파일을 따르며, 수정 시 이력이 남습니다.")
    except Exception as e:                                              # noqa
        LOG.warn(f"사전등록 파일 저장 실패({type(e).__name__}) — 이번 실행에만 유효합니다.")
    return out


def build_mapping_table(hs_uni: pd.DataFrame, sec: pd.DataFrame, conc: pd.DataFrame,
                        seg: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """매핑표 (code, hs, weight, valid_from, valid_to, match_score).

    valid_from 은 **사업보고서 접수일(rcept_dt)** 이다 — 그 제품구성을 알 수 있게 된 날.
    사업보고서 제품 정보가 없으면 상장일 + 1년(첫 사업보고서 제출 시점의 보수적 하한)으로 둔다.
    """
    cols = ["code", "hs", "weight", "valid_from", "valid_to", "match_score"]
    if hs_uni is None or not len(hs_uni):
        return pd.DataFrame(columns=cols)
    ad = hs_uni[hs_uni["adopted"] == 1].copy()
    if not len(ad):
        return pd.DataFrame(columns=cols)

    ind = sec.copy()
    ind["ksic2"] = ind.get("induty_code", pd.Series("", index=ind.index)).astype(str).str[:2]
    cmap = conc.copy()
    cmap["hs2"] = cmap["hs"].astype(str).str.zfill(2).str[:2]
    cmap["ksic2"] = cmap["ksic"].astype(str).str.zfill(2).str[:2]
    ad["hs2"] = ad["hs"].astype(str).str[:2]

    j = (ad[["hs", "hs2"]]
         .merge(cmap[["hs2", "ksic2"]].drop_duplicates(), on="hs2", how="inner")
         .merge(ind[["code", "ksic2", "listing_date"]], on="ksic2", how="inner"))
    if not len(j):
        return pd.DataFrame(columns=cols)

    # 한 종목이 같은 章의 여러 HS 에 붙으면 가중치를 나눈다(합=1).
    j["weight"] = 1.0
    j["weight"] = j["weight"] / j.groupby("code", observed=True)["hs"].transform("size")
    j["match_score"] = 0.5                        # 연계표 경유의 기본 신뢰도

    # ── C3: PIT 유효 시작일
    ld = as_ts_series(j.get("listing_date"))
    j["valid_from"] = (ld + pd.DateOffset(years=1)).fillna(pd.Timestamp(BACKTEST_START))
    if seg is not None and len(seg):
        # 사업보고서 품목표가 있으면 그 접수일이 더 정확하다(그리고 더 보수적일 수 있다).
        s = seg.groupby("code", observed=True)["knowledge_date"].min().rename("seg_from").reset_index()
        j = j.merge(s, on="code", how="left")
        j["valid_from"] = np.maximum(as_ts_series(j["valid_from"]).to_numpy(),
                                     as_ts_series(j["seg_from"]).fillna(
                                         as_ts_series(j["valid_from"])).to_numpy())
        j["valid_from"] = as_ts_series(j["valid_from"])
        j["match_score"] = np.where(j["seg_from"].notna(), 0.7, j["match_score"])
    j["valid_to"] = pd.Timestamp("2262-01-01")
    out = j[cols].drop_duplicates(["code", "hs"]).reset_index(drop=True)
    LOG.ok(f"매핑표: 종목 {out['code'].nunique():,}개 × HS {out['hs'].nunique():,}개 = "
           f"{len(out):,}쌍 (valid_from 중앙값 {as_ts_series(out['valid_from']).median():%Y-%m})")
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  매핑 검증 4중 게이트 (§5.3)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def gate1_coverage(mapping: pd.DataFrame, cx: pd.DataFrame, fin: pd.DataFrame,
                   band: Tuple[float, float] = COVERAGE_BAND,
                   cv_max: float = COVERAGE_CV_MAX) -> pd.DataFrame:
    """게이트 1 — 합계 정합성. 회계 항등식에 가까우므로 R² 보다 근본적이다.

        Coverage_HS = Σ_i (기업_i 별도 수출매출) / 해당 HS 총 수출액 ∈ [0.85, 1.15]
        + 시간 안정성: 이 비율의 변동계수 < 0.25
    """
    cols = ["hs", "coverage", "cov_cv", "gate1"]
    if mapping is None or not len(mapping) or cx is None or not len(cx):
        return pd.DataFrame(columns=cols)
    if fin is None or not len(fin) or "export_rev_sep" not in fin.columns:
        LOG.warn("게이트1: 별도 수출매출을 확보하지 못해 합계정합성을 검정할 수 없습니다. "
                 "이 게이트는 '판정 유보'로 두고 게이트2·3 으로 판단합니다.")
        hs = mapping["hs"].astype(str).unique()
        return pd.DataFrame({"hs": hs, "coverage": np.nan, "cov_cv": np.nan, "gate1": 1})

    # HS 총 수출액(연도)
    c = cx.copy()
    c["hs"] = c["hs"].astype(str)
    c["year"] = as_ts_series(c["ym"]).dt.year
    hs_year = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()

    f = fin.copy()
    # tidy_financials 는 'period_end' 를 낸다. 'period' 는 존재하지 않는다(KeyError).
    f["year"] = as_ts_series(f["period_end"]).dt.year
    fy = f.groupby(["code", "year"], observed=True)["export_rev_sep"].max().reset_index()

    j = mapping[["code", "hs", "weight"]].merge(fy, on="code", how="inner")
    j = j.merge(hs_year, on=["hs", "year"], how="inner")
    if not len(j):
        return pd.DataFrame({"hs": mapping["hs"].astype(str).unique(),
                             "coverage": np.nan, "cov_cv": np.nan, "gate1": 1})
    j["firm_share"] = pd.to_numeric(j["export_rev_sep"], errors="coerce") * j["weight"]
    g = j.groupby(["hs", "year"], observed=True).agg(
        num=("firm_share", "sum"), den=("exp_usd", "first")).reset_index()
    g["cov"] = safe_div(g["num"], g["den"])
    agg = g.groupby("hs", observed=True)["cov"].agg(
        coverage="median", _sd="std", _mu="mean").reset_index()
    agg["cov_cv"] = safe_div(agg["_sd"], agg["_mu"]).abs()
    agg["gate1"] = ((agg["coverage"] >= band[0]) & (agg["coverage"] <= band[1]) &
                    (agg["cov_cv"] < cv_max)).astype(int)
    n_pass = int(agg["gate1"].sum())
    LOG.info(f"게이트1 합계정합성: {n_pass}/{len(agg)} HS 통과 "
             f"(허용 {band[0]:.2f}~{band[1]:.2f}, 변동계수<{cv_max})")
    return agg[cols]


def gate2_selfdisclosure(mapping: pd.DataFrame, cx: pd.DataFrame, seg: pd.DataFrame,
                         corr_min: float = SELFDISC_CORR_MIN) -> pd.DataFrame:
    """게이트 2 — 기업 자기공시 대조.

    사업보고서「매출 및 수주상황」의 품목별 매출 증가율 vs 매핑된 HS 의 수출액 증가율.
    매핑을 '추정'이 아니라 **기업 자신의 진술**로 검증한다. 상관 < 0.4 이면 매핑 폐기.
    """
    cols = ["code", "selfdisc_corr", "gate2"]
    if seg is None or not len(seg) or mapping is None or not len(mapping):
        if mapping is not None and len(mapping):
            LOG.warn("게이트2: 사업보고서 품목별 매출을 확보하지 못했습니다 — 판정 유보(통과 처리)하고 "
                     "그 사실을 매핑 게이트 리포트에 명시합니다.")
            return pd.DataFrame({"code": mapping["code"].unique(),
                                 "selfdisc_corr": np.nan, "gate2": 1})
        return pd.DataFrame(columns=cols)

    c = cx.copy()
    c["hs"] = c["hs"].astype(str)
    c["year"] = as_ts_series(c["ym"]).dt.year
    hs_year = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()
    hs_year = hs_year.sort_values(["hs", "year"])
    hs_year["hs_g"] = hs_year.groupby("hs", observed=True)["exp_usd"].pct_change()

    s = seg.copy()
    s["year"] = as_ts_series(s["knowledge_date"]).dt.year
    s = s.groupby(["code", "year"], observed=True)["seg_amount"].sum().reset_index()
    s = s.sort_values(["code", "year"])
    s["firm_g"] = s.groupby("code", observed=True)["seg_amount"].pct_change()

    j = (mapping[["code", "hs", "weight"]]
         .merge(hs_year[["hs", "year", "hs_g"]], on="hs", how="inner")
         .merge(s[["code", "year", "firm_g"]], on=["code", "year"], how="inner"))
    j = j.replace([np.inf, -np.inf], np.nan).dropna(subset=["hs_g", "firm_g"])
    if not len(j):
        return pd.DataFrame({"code": mapping["code"].unique(),
                             "selfdisc_corr": np.nan, "gate2": 1})
    # 종목별 시계열 상관 — groupby.apply 금지(원칙 3). 적률 합으로 벡터화한다.
    j["_n"] = 1.0
    j["_xx"] = j["hs_g"] ** 2
    j["_yy"] = j["firm_g"] ** 2
    j["_xy"] = j["hs_g"] * j["firm_g"]
    g = j.groupby("code", observed=True)
    n = g["_n"].sum()
    sx, sy = g["hs_g"].sum(), g["firm_g"].sum()
    sxx, syy, sxy = g["_xx"].sum(), g["_yy"].sum(), g["_xy"].sum()
    num = n * sxy - sx * sy
    den = np.sqrt((n * sxx - sx ** 2).clip(lower=0)) * np.sqrt((n * syy - sy ** 2).clip(lower=0))
    corr = safe_div(num, den).where(n >= 4)
    out = corr.rename("selfdisc_corr").reset_index()
    out["gate2"] = ((out["selfdisc_corr"] >= corr_min) | out["selfdisc_corr"].isna()).astype(int)
    LOG.info(f"게이트2 자기공시 대조: {int(out['gate2'].sum())}/{len(out)} 종목 통과 "
             f"(상관 하한 {corr_min}, 관측부족은 유보)")
    return out[cols]


def gate3_placebo(mapping: pd.DataFrame, a_hs: pd.DataFrame, fin: pd.DataFrame,
                  n_shuffle: int = PLACEBO_N, alpha: float = PLACEBO_ALPHA,
                  seed: int = SEED) -> dict:
    """게이트 3 — 플라시보 매핑. **회귀 재적합 금지, 행렬곱만.**

    무작위 HS 배정 n회로 적합도 귀무분포를 만들고, 실제 매핑이 상위 5% 밖이면 탈락.
    ⚠ 회귀를 1,000번 재적합하면 250시간이다. 롤링 적률(=이미 계산된 a1)을 재사용하고
      매핑 행렬만 셔플하면 행렬곱 1,000회 = 수십 초다(원칙 5).
    """
    out = {"stat": float("nan"), "p": float("nan"), "pass": 0, "n": 0, "detail": ""}
    if (mapping is None or not len(mapping) or a_hs is None or not len(a_hs)
            or fin is None or not len(fin)):
        out["detail"] = "입력 부족 — 판정 유보"
        out["pass"] = 1
        return out

    # HS × 연도 물량 증가율 행렬
    A = a_hs.copy()
    A["year"] = as_ts_series(A["ym"]).dt.year
    hs_y = A.groupby(["hs", "year"], observed=True)["a1"].mean().reset_index()
    Hm = hs_y.pivot_table(index="hs", columns="year", values="a1")
    # 종목 × 연도 매출 증가율 행렬
    F = fin.copy()
    F["year"] = as_ts_series(F["period_end"]).dt.year
    fy = F.groupby(["code", "year"], observed=True)["b1"].mean().reset_index() \
        if "b1" in F.columns else None
    if fy is None or not len(fy):
        out["detail"] = "기업 매출증가율 부재 — 판정 유보"
        out["pass"] = 1
        return out
    Fm = fy.pivot_table(index="code", columns="year", values="b1")

    years = sorted(set(Hm.columns) & set(Fm.columns))
    if len(years) < 4:
        out["detail"] = f"공통 연도 {len(years)}개 — 판정 유보"
        out["pass"] = 1
        return out
    Hm = Hm.reindex(columns=years)
    Fm = Fm.reindex(columns=years)

    hs_idx = {h: i for i, h in enumerate(Hm.index.astype(str))}
    cd_idx = {c: i for i, c in enumerate(Fm.index.astype(str))}
    mp = mapping[mapping["hs"].astype(str).isin(hs_idx) &
                 mapping["code"].astype(str).isin(cd_idx)]
    if not len(mp):
        out["detail"] = "매핑과 행렬의 교집합 없음 — 판정 유보"
        out["pass"] = 1
        return out

    n_f, n_h = len(cd_idx), len(hs_idx)
    rows = mp["code"].astype(str).map(cd_idx).to_numpy()
    cols_ = mp["hs"].astype(str).map(hs_idx).to_numpy()
    w = pd.to_numeric(mp["weight"], errors="coerce").fillna(1.0).to_numpy()

    H = np.nan_to_num(Hm.to_numpy(dtype=float))
    Y = Fm.to_numpy(dtype=float)
    ok = np.isfinite(Y)

    def _fit(cc: np.ndarray) -> float:
        M = np.zeros((n_f, n_h), dtype=float)
        np.add.at(M, (rows, cc), w)
        rs = M.sum(axis=1, keepdims=True)
        M = np.divide(M, rs, out=np.zeros_like(M), where=rs > 0)
        P = M @ H                                       # (n_f, T) 예측
        # 시계열 상관의 평균 — 행렬곱 한 번이면 끝난다.
        Pm = np.where(ok, P, np.nan)
        Ym = np.where(ok, Y, np.nan)
        pc = Pm - np.nanmean(Pm, axis=1, keepdims=True)
        yc = Ym - np.nanmean(Ym, axis=1, keepdims=True)
        num = np.nansum(pc * yc, axis=1)
        den = np.sqrt(np.nansum(pc ** 2, axis=1) * np.nansum(yc ** 2, axis=1))
        r = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
        return float(np.nanmean(r)) if np.isfinite(r).any() else float("nan")

    real = _fit(cols_)
    rng = np.random.default_rng(seed)
    null = np.empty(n_shuffle, dtype=float)
    for i in range(n_shuffle):
        # ★ rng.integers 는 **복원추출**이라 '한 HS 에 몰림'이 실제 매핑보다 흔해지고
        #   귀무분포가 왜곡된다. 실제 배정을 **순열**하면 어느 HS 가 몇 번 쓰였는지(주변분포)를
        #   보존한 채 '누가 어디에 붙었는가'만 무작위가 된다 — 검정하려는 게 정확히 그것이다.
        null[i] = _fit(rng.permutation(cols_))
    null = null[np.isfinite(null)]
    if not np.isfinite(real) or not len(null):
        out["detail"] = "적합도 산출 불가 — 판정 유보"
        out["pass"] = 1
        return out
    p = float((null >= real).mean())
    # ★ 검정력을 함께 보고한다. 이 게이트의 탈락은 V12 를 통해 **A축 전체를 끈다** —
    #   전략의 존재 이유를 없애는 결정이다. 그런데 표본이 22종목·5개 HS 수준이면
    #   상관 추정 자체가 잡음이라 PASS 든 FAIL 이든 신뢰할 수 없다.
    #   그래도 FAIL 을 통과로 바꾸지는 않는다(fail-open 이 더 나쁘다). 대신 그 판정이
    #   무엇에 근거했는지를 숫자로 남겨 사람이 판단할 수 있게 한다.
    low_power = (n_f < 30) or (n_h < 10) or (len(years) < 6)
    out.update(stat=real, p=p, n=int(len(null)), n_firms=int(n_f), n_hs=int(n_h),
               n_years=int(len(years)), low_power=bool(low_power),
               **{"pass": int(p < alpha)},
               detail=f"실제 {real:+.4f} vs 귀무 평균 {np.mean(null):+.4f} "
                      f"(셔플 {len(null)}회, p={p:.4f} · 종목 {n_f} × HS {n_h} × "
                      f"연도 {len(years)})")
    LOG.info(f"게이트3 플라시보: {out['detail']} → "
             f"{'통과' if out['pass'] else '탈락(매핑이 무작위와 구분 안 됨)'}")
    if low_power:
        LOG.warn(
            f"게이트3 검정력 부족: 종목 {n_f}개 × HS {n_h}개 × 연도 {len(years)}개.\n"
            f"    이 규모에서는 상관 추정이 잡음이라 통과든 탈락이든 신뢰 구간이 매우 넓습니다.\n"
            f"    그런데 이 게이트의 탈락은 V12 를 통해 **A축(통관) 전체를 끕니다** — "
            f"전략의 존재 이유가 사라집니다.\n"
            f"    → 판정을 뒤집지는 않습니다(통과시키면 검증 없이 매핑을 믿는 셈). "
            f"대신 HS↔KSIC 연계표(CANARY X6)를 개선해 표본을 키운 뒤 재측정하세요.")
    return out


def apply_mapping_gates(mapping: pd.DataFrame, cx: pd.DataFrame, fin: pd.DataFrame,
                        seg: Optional[pd.DataFrame], a_hs: pd.DataFrame
                        ) -> Tuple[pd.DataFrame, dict]:
    """게이트 1·2·3 을 적용해 매핑표를 걸러내고, 결과 요약을 함께 반환한다.

    게이트 4(PIT 라벨 고정)는 build_mapping_table 이 구조로 보장하므로 별도 검정이 아니다.
    """
    info: dict = {}
    if mapping is None or not len(mapping):
        return mapping, {"n_before": 0, "n_after": 0}
    n0 = mapping["code"].nunique()

    g1 = gate1_coverage(mapping, cx, fin)
    g2 = gate2_selfdisclosure(mapping, cx, seg)
    g3 = gate3_placebo(mapping, a_hs, fin)

    m = mapping.copy()
    if len(g1):
        m = m.merge(g1[["hs", "gate1", "coverage", "cov_cv"]], on="hs", how="left")
        m["gate1"] = m["gate1"].fillna(1)
    else:
        m["gate1"] = 1
    if len(g2):
        m = m.merge(g2[["code", "gate2", "selfdisc_corr"]], on="code", how="left")
        m["gate2"] = m["gate2"].fillna(1)
    else:
        m["gate2"] = 1
    m["gate3"] = int(g3.get("pass", 1))
    m["map_gate_fail"] = (1 - (m["gate1"] * m["gate2"] * m["gate3"])).clip(0, 1)

    # ★ 실패분을 **삭제하지 않는다.** 사양 §9 의 V12 는 '전면 제외'가 아니라 'A축 무효화'다.
    #   지워 버리면 그 종목은 B·C축 신호까지 잃고 유니버스에서 사라져 표본이 이중으로 줄고,
    #   V12 는 발동할 대상이 없어 구조적으로 죽은 거부권이 된다.
    #   플래그만 실어 보내고 실제 무효화는 disable_axes 가 한다.
    kept = m.copy()
    n1 = int(m.loc[m["map_gate_fail"] == 0, "code"].nunique())
    info = {"n_before": int(n0), "n_after": int(n1), "gate3": g3,
            "g1_pass": int(g1["gate1"].sum()) if len(g1) else 0,
            "g1_total": int(len(g1)),
            "g2_pass": int(g2["gate2"].sum()) if len(g2) else 0,
            "g2_total": int(len(g2))}
    # ★ '판정 유보'를 '통과'처럼 보이게 하면 안 된다.
    #   입력이 없어 검정을 못 한 게이트는 coverage/selfdisc_corr 가 전부 NaN 인 채로
    #   gate=1(통과 처리)이 된다. 그걸 "58/58 HS 통과"로 찍으면 **검증된 적 없는 매핑이
    #   3중 게이트를 통과한 것처럼** 읽힌다 — 이 전략에서 가장 위험한 오해다.
    g1_held = bool(len(g1)) and not g1["coverage"].notna().any()
    g2_held = bool(len(g2)) and not g2["selfdisc_corr"].notna().any()
    g3_held = "유보" in str(g3.get("detail", ""))
    n_held = sum([g1_held, g2_held, g3_held])
    LOG.banner("매핑 게이트 결과",
               f"종목 {n0:,} → {n1:,}" + (f" · ⚠ {n_held}개 게이트가 판정 유보" if n_held else ""))
    LOG.table([
        ["게이트1 합계정합성",
         "판정 유보" if g1_held else f"{info['g1_pass']}/{info['g1_total']} HS",
         "별도 수출매출 부재 — 검정 못 함" if g1_held else
         f"허용 {COVERAGE_BAND[0]:.2f}~{COVERAGE_BAND[1]:.2f} · 변동계수<{COVERAGE_CV_MAX}"],
        ["게이트2 자기공시상관",
         "판정 유보" if g2_held else f"{info['g2_pass']}/{info['g2_total']} 종목",
         "품목별 매출 부재 — 검정 못 함" if g2_held else f"상관 하한 {SELFDISC_CORR_MIN}"],
        ["게이트3 플라시보",
         "판정 유보" if g3_held else ("통과" if g3.get("pass") else "탈락"),
         g3.get("detail", "")[:60]],
        ["게이트4 PIT 라벨(C3)", "구조 보장", "valid_from = 사업보고서 접수일"],
    ], ["게이트", "결과", "기준"])
    info["n_held"] = n_held
    if n_held >= 2:
        LOG.error(
            f"매핑 4중 게이트 중 {n_held}개가 **판정 유보**입니다 — 통과가 아니라 "
            f"'검증하지 못했다'는 뜻입니다.\n"
            f"    HS↔상장사 매핑이 실질적으로 검증되지 않은 상태이며, A축(통관) 신호의 "
            f"기업 귀속을 신뢰할 근거가 없습니다.\n"
            f"    → 이 상태의 백테스트 결과는 '매핑이 맞다면'이라는 큰 가정 위에 있습니다. "
            f"R4(플라시보)와 R5(A축 절제) 결과를 반드시 함께 보세요.")

    if n1 < MAPPING_MIN_NAMES:
        LOG.warn(f"[킬 기준 4] 매핑 게이트 통과 종목 {n1} < {MAPPING_MIN_NAMES} — "
                 f"통계 검정이 불가능한 표본입니다. 과점 기준을 완화해 재측정하거나, "
                 f"그래도 미달이면 이 방향을 폐기해야 합니다. 결과를 그대로 보고합니다.")
    return kept, info
