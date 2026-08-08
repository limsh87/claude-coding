
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L4-B  사전등록 가설 H1~H5 검정  (SPEC §3)  — 변경 금지                                   ║
# ║                                                                                          ║
# ║  H1  확증군(리포트+자사창구 순매수 상위) 의 20영업일 이상수익률이 양(+)      기각: t < 2.0 ║
# ║  H2  페이드군(리포트+자사창구 순매도) 은 음(−) 이거나 H1 보다 유의하게 낮다   기각: Δt<2.0 ║
# ║  H3  효과는 중소형 증권사에서 더 강하다 (메커니즘 조건부 예측)                             ║
# ║      ★ 대형 리테일 창구에서 오히려 강하면 데이터마이닝 판정                                ║
# ║  H4  효과는 저유동성·소형주에서 더 강하다                                                  ║
# ║  H5  ★★ 자사 창구 플로우는 '리포트가 없는 날의 동일 창구 플로우' 보다 예측력이 높다        ║
# ║      이 전략의 존재 이유다. 통과 못 하면 '리포트 전략' 이 아니라 그냥 '플로우 전략' 이며,  ║
# ║      리포트 파트는 삭제하는 게 맞다.                                                       ║
# ║                                                                                          ║
# ║  다중검정 보정: BH-FDR (q=0.10)                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

H_HORIZON = 20            # SPEC §3: 20영업일


def _abnormal_returns(events: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                      horizon: int = H_HORIZON, entry_offset: int = 1) -> np.ndarray:
    """이벤트별 (entry_offset ~ entry_offset+horizon) 시장조정 누적수익.

    ★ entry_offset 은 최소 1 이다. 거래원/수급은 장 마감 후 공개되므로 발간일 종가
      진입은 SPEC §0.1 위반이다(산출물 전체 무효)."""
    if events is None or len(events) == 0 or not len(cal):
        return np.array([])
    entry_offset = max(1, int(entry_offset))
    R, cidx = _ret_matrix(px, cal)
    mkt = np.nanmean(R, axis=0)
    mkt = np.where(np.isfinite(mkt), mkt, 0.0)
    AR = R - mkt[None, :]
    day_pos = {d: i for i, d in enumerate(cal)}
    out = []
    for code, dt_ in zip(events["code"], events["date"]):
        ci, di = cidx.get(code), day_pos.get(pd.Timestamp(dt_))
        if ci is None or di is None:
            continue
        lo, hi = di + entry_offset, di + entry_offset + horizon
        if hi >= AR.shape[1]:
            continue
        seg = AR[ci, lo:hi]
        seg = seg[np.isfinite(seg)]
        if seg.size == 0:
            continue
        out.append(float(np.sum(seg)))
    return np.asarray(out, float)


def _mean_t(x: np.ndarray) -> Tuple[float, float, float, int]:
    """평균, t, p(양측), n.  ★ 이벤트 보유구간이 겹쳐 상관이 있으므로 단순 t 는 과대추정된다.
    여기서는 '이벤트 횡단면' 통계로 쓰고, 시계열 유의성은 캘린더타임 포트폴리오의
    Newey-West t 로 따로 본다(둘을 함께 보고한다)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 10:
        return (np.nan, np.nan, np.nan, n)
    mu = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(n))
    t = mu / se if se > 0 else np.nan
    p = t_sf(t, n - 1) if np.isfinite(t) else np.nan
    return (mu, t, p, n)


def _welch(a: np.ndarray, b: np.ndarray) -> Tuple[float, float, float]:
    """두 군 평균 차이의 Welch t (분산이 다른 것이 정상이다)."""
    a = np.asarray(a, float)[np.isfinite(a)]
    b = np.asarray(b, float)[np.isfinite(b)]
    if a.size < 10 or b.size < 10:
        return (np.nan, np.nan, np.nan)
    va, vb = a.var(ddof=1) / a.size, b.var(ddof=1) / b.size
    d = float(a.mean() - b.mean())
    se = math.sqrt(va + vb)
    if se <= 0:
        return (d, np.nan, np.nan)
    t = d / se
    dof = (va + vb) ** 2 / max(va ** 2 / (a.size - 1) + vb ** 2 / (b.size - 1), 1e-300)
    return (d, t, t_sf(t, dof))


def test_hypotheses(groups: Dict[str, pd.DataFrame], S: pd.DataFrame, px: pd.DataFrame,
                    cal: pd.DatetimeIndex, bm: "BrokerMap", mode: str,
                    entry_offset: int = 1) -> dict:
    """H1~H5 를 계산하고 BH-FDR 을 적용한다. 반환: 결과 딕셔너리(리포트/판정에서 사용)."""
    res: Dict[str, Any] = {"mode": mode, "entry_offset": entry_offset, "rows": [],
                           "pvals": [], "detail": {}}

    conf = groups.get("확증군(리포트+순매수상위30%)")
    fade = groups.get("페이드군(리포트+순매도하위30%)")
    ctrl = groups.get("무플로우대조군(리포트+중간40%)")
    nore = groups.get("무리포트대조군(플로우만 상위30%)")

    ar_conf = _abnormal_returns(conf, px, cal, H_HORIZON, entry_offset)
    ar_fade = _abnormal_returns(fade, px, cal, H_HORIZON, entry_offset)
    ar_ctrl = _abnormal_returns(ctrl, px, cal, H_HORIZON, entry_offset)
    ar_nore = _abnormal_returns(nore, px, cal, H_HORIZON, entry_offset)
    res["detail"]["ar"] = {"확증": ar_conf, "페이드": ar_fade,
                           "무플로우": ar_ctrl, "무리포트": ar_nore}

    # ── H1 ───────────────────────────────────────────────────────────────────────────────
    mu1, t1, p1, n1 = _mean_t(ar_conf)
    res["rows"].append(["H1", "확증군 20일 CAR > 0", f"{mu1*100:+.2f}%" if np.isfinite(mu1) else "-",
                        f"{t1:+.2f}" if np.isfinite(t1) else "-", f"{n1:,}",
                        "통과" if (np.isfinite(t1) and t1 >= 2.0) else "기각"])
    res["pvals"].append(("H1", p1 / 2 if np.isfinite(p1) and np.isfinite(t1) and t1 > 0 else p1,
                         "확증군 CAR(+20) > 0"))
    res["H1_pass"] = bool(np.isfinite(t1) and t1 >= 2.0)

    # ── H2 ───────────────────────────────────────────────────────────────────────────────
    d2, t2, p2 = _welch(ar_conf, ar_fade)
    mu_f = float(np.nanmean(ar_fade)) if ar_fade.size else np.nan
    res["rows"].append(["H2", "확증군 − 페이드군 > 0",
                        f"{d2*100:+.2f}%p" if np.isfinite(d2) else "-",
                        f"{t2:+.2f}" if np.isfinite(t2) else "-",
                        f"{ar_fade.size:,}",
                        "통과" if (np.isfinite(t2) and t2 >= 2.0) else "기각"])
    res["pvals"].append(("H2", p2 / 2 if np.isfinite(p2) and np.isfinite(t2) and t2 > 0 else p2,
                         f"확증 vs 페이드 차이 (페이드 평균 {mu_f*100:+.2f}%)"))
    res["H2_pass"] = bool(np.isfinite(t2) and t2 >= 2.0)

    # ── H3 (메커니즘 조건부 예측) ─────────────────────────────────────────────────────────
    if conf is not None and len(conf) and "broker_tier" in conf.columns:
        small = conf[conf["broker_tier"].isin(H3_SMALL_TIERS)]
        large = conf[conf["broker_tier"].isin(H3_LARGE_TIERS)]
        a_s = _abnormal_returns(small, px, cal, H_HORIZON, entry_offset)
        a_l = _abnormal_returns(large, px, cal, H_HORIZON, entry_offset)
        d3, t3, p3 = _welch(a_s, a_l)
        res["detail"]["H3"] = {"small_n": a_s.size, "large_n": a_l.size,
                               "small_mu": float(np.nanmean(a_s)) if a_s.size else np.nan,
                               "large_mu": float(np.nanmean(a_l)) if a_l.size else np.nan}
        reversed_ = bool(np.isfinite(t3) and t3 <= -2.0)
        res["rows"].append(["H3", "중소형사 > 대형/리테일",
                            f"{d3*100:+.2f}%p" if np.isfinite(d3) else "-",
                            f"{t3:+.2f}" if np.isfinite(t3) else "-",
                            f"{a_s.size:,}/{a_l.size:,}",
                            "통과" if (np.isfinite(t3) and t3 >= 2.0)
                            else ("★역전(데이터마이닝 의심)" if reversed_ else "기각")])
        res["pvals"].append(("H3", p3 / 2 if np.isfinite(p3) and np.isfinite(t3) and t3 > 0 else p3,
                             "중소형 증권사 조건부 강화"))
        res["H3_pass"] = bool(np.isfinite(t3) and t3 >= 2.0)
        res["H3_reversed"] = reversed_
    else:
        res["rows"].append(["H3", "중소형사 > 대형/리테일", "-", "-", "0", "검정불가"])
        res["pvals"].append(("H3", np.nan, "증권사 구분 정보 없음"))
        res["H3_pass"] = False
        res["H3_reversed"] = False

    if mode == "PROXY":
        res["rows"][-1][-1] = "★검정불가(PROXY: 창구 정체성 소실)"
        res["H3_pass"] = False
        res["H3_testable"] = False
    else:
        res["H3_testable"] = True

    # ── H4 (사이즈/유동성 조건부) ─────────────────────────────────────────────────────────
    if conf is not None and len(conf) and "size_bucket" in conf.columns:
        sm = conf[conf["size_bucket"] == "소형"]
        lg = conf[conf["size_bucket"] == "대형"]
        a_s = _abnormal_returns(sm, px, cal, H_HORIZON, entry_offset)
        a_l = _abnormal_returns(lg, px, cal, H_HORIZON, entry_offset)
        d4, t4, p4 = _welch(a_s, a_l)
        res["rows"].append(["H4", "소형주 > 대형주",
                            f"{d4*100:+.2f}%p" if np.isfinite(d4) else "-",
                            f"{t4:+.2f}" if np.isfinite(t4) else "-",
                            f"{a_s.size:,}/{a_l.size:,}",
                            "통과" if (np.isfinite(t4) and t4 >= 2.0) else "기각"])
        res["pvals"].append(("H4", p4 / 2 if np.isfinite(p4) and np.isfinite(t4) and t4 > 0 else p4,
                             "소형·저유동성 조건부 강화"))
        res["H4_pass"] = bool(np.isfinite(t4) and t4 >= 2.0)
    else:
        res["rows"].append(["H4", "소형주 > 대형주", "-", "-", "0", "검정불가"])
        res["pvals"].append(("H4", np.nan, "사이즈 구분 정보 없음"))
        res["H4_pass"] = False

    # ── H5 (★ 이 전략의 존재 이유) ────────────────────────────────────────────────────────
    d5, t5, p5 = _welch(ar_conf, ar_nore)
    res["rows"].append(["H5", "★리포트 조건부 우위 (확증군 > 무리포트 플로우)",
                        f"{d5*100:+.2f}%p" if np.isfinite(d5) else "-",
                        f"{t5:+.2f}" if np.isfinite(t5) else "-",
                        f"{ar_nore.size:,}",
                        "통과" if (np.isfinite(t5) and t5 >= 2.0) else "기각"])
    res["pvals"].append(("H5", p5 / 2 if np.isfinite(p5) and np.isfinite(t5) and t5 > 0 else p5,
                         "리포트가 조건부로 의미를 더하는가"))
    res["H5_pass"] = bool(np.isfinite(t5) and t5 >= 2.0)

    LOG.table(res["rows"], ["ID", "가설", "효과크기", "t", "표본(n)", "판정"],
              ["c", "l", "r", "r", "r", "c"],
              title=f"사전등록 가설 검정 H1~H5 (기각선 t=2.0 · 20영업일 CAR · 진입 d+{entry_offset})")

    # ── BH-FDR ────────────────────────────────────────────────────────────────────────────
    fdr = bh_fdr_table(res["pvals"], q=0.10)
    res["fdr"] = fdr
    # ★ 컬럼명에 괄호가 있어 itertuples 의 속성명이 _5 처럼 바뀐다 → 위치 접근 금지, dict 로 읽는다
    LOG.table([[row["가설"],
                f"{row['p값']:.4f}" if np.isfinite(row["p값"]) else "-",
                str(row["순위"]), f"{row['BH임계']:.4f}",
                row["BH(q=0.10)"], row["BY(보수)"], _trunc(row["설명"], 34)]
               for _, row in fdr.iterrows()],
              ["가설", "p값", "순위", "BH임계", "BH(q=.10)", "BY(보수)", "설명"],
              ["c", "r", "c", "r", "c", "c", "l"],
              title="다중검정 보정 — Benjamini-Hochberg FDR q=0.10 (BY 는 임의의존 가정 하 보수적 기준)")
    passed = set(fdr.loc[fdr["BH(q=0.10)"] == "통과", "가설"])
    for h in ("H1", "H2", "H3", "H4", "H5"):
        res[f"{h}_fdr"] = h in passed
    return res


def report_mechanism(res: dict, mode: str) -> str:
    """H3/H4 조건부 예측 해석표 (mechanism_tests.md 용 본문 생성)."""
    lines = ["# 메커니즘 조건부 예측 검정 (H3 / H4)", "",
             f"- 실행 모드: **{mode}**", ""]
    d3 = res.get("detail", {}).get("H3", {})
    if mode == "PROXY":
        lines += [
            "## H3 — 중소형 증권사에서 더 강한가",
            "",
            "**검정 불가.** PROXY 분기에서는 신호가 '증권사 창구' 가 아니라 '투자 주체(기관/외국인)' 다.",
            "창구 정체성이 사라지므로 중소형사와 대형사를 구분하는 축 자체가 존재하지 않는다.",
            "이 항목을 '기각' 으로 읽어서는 안 된다 — 데이터가 없어서 못 한 것이다.",
            "",
            "참고로 발행사 tier 별 하위표본 비교는 아래에 싣되, 이것은 H3 의 검정이 아니라",
            "'어떤 하우스의 리포트가 기관/외국인 수급과 더 잘 붙는가' 라는 다른 질문의 답이다.",
            "",
        ]
    else:
        lines += [
            "## H3 — 중소형 증권사에서 더 강한가",
            "",
            f"- 중소형(MID) 표본 {d3.get('small_n', 0):,}건, 평균 CAR "
            f"{100*d3.get('small_mu', float('nan')):+.2f}%",
            f"- 대형/리테일(MAJOR·RETAIL) 표본 {d3.get('large_n', 0):,}건, 평균 CAR "
            f"{100*d3.get('large_mu', float('nan')):+.2f}%",
            "",
            "**판정:** " + ("통과 — 메커니즘(리서치 배포강도가 창구에 드러난다)과 정합적."
                          if res.get("H3_pass") else
                          ("★역전 — 대형 리테일 창구에서 오히려 강하다. SPEC §3 에 따라 "
                           "데이터마이닝으로 판정한다. 리테일 창구는 주문 구성이 리서치 배포와 "
                           "무관하므로, 여기서 효과가 나온다면 그것은 메커니즘이 아니라 "
                           "다른 무언가를 잡고 있다는 뜻이다."
                           if res.get("H3_reversed") else
                           "기각 — 중소형 우위가 유의하지 않다. 표본이 작아 검정력이 낮을 수 있다.")),
            "",
        ]
    lines += [
        "## H4 — 저유동성·소형주에서 더 강한가",
        "",
        "**판정:** " + ("통과" if res.get("H4_pass") else "기각"),
        "",
        "소형주에서 강하다면 (a) 정보 확산이 느리고 (b) 창구 플로우가 유동성 대비 크기 때문에",
        "신호 대 잡음비가 높다는 해석과 정합적이다. 다만 소형주는 슬리피지가 3.5배(35bp vs 10bp)",
        "이므로, 비용 반영 후에도 남는지는 비용 민감도표에서 별도로 확인해야 한다.",
        "",
        "> 시가총액은 이 파이프라인에서 랭크·버킷으로만 사용된다. PIT 시총 사다리가 T2~T4 로",
        "> 강등된 구간에서는 사이즈 분류에 근사가 섞이므로 H4 해석 시 그 비율을 함께 볼 것.",
    ]
    return "\n".join(lines) + "\n"
