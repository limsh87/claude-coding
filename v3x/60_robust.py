# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  강건성 스위트 R0~R10 — 순서대로. 앞 단계 실패 시 뒤는 참고치일 뿐이다.                     ║
# ║                                                                                             ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다. 나쁜 결과는 그 자체로 정보다 —                     ║
# ║    이 방향 전체의 기대값 상한을 알려준다.                                                   ║
# ║                                                                                             ║
# ║  ★ 기준선에 애초에 알파가 없으면 R3·R7·R10 은 PASS 가 아니라 **판정 유보(N/A)** 를 낸다.    ║
# ║    이걸 막지 않으면 기준 Sharpe -0.05 에서 직교화 후 0.04 가 나왔다는 이유로 '알파 잔존'이  ║
# ║    찍히고, 아무 알파도 없는 전략이 강건성 검사를 3개나 통과한 것처럼 보인다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def _f(x, default: float = float("nan")) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:                                                   # noqa
        return default


ROBUST_LOG: "List[dict]" = []
KILL_LOG: "List[dict]" = []
# 알파가 '있다'고 부를 최소선. 이보다 낮으면 조건부 검사들은 판정 유보로 간다.
ALPHA_FLOOR_SHARPE = 0.15


def _rx(rid: str, name: str, verdict: str, detail: str, metric: str = "",
        kill: bool = False) -> None:
    ROBUST_LOG.append({"id": rid, "name": name, "verdict": verdict,
                       "metric": metric, "detail": detail})
    icon = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "N/A": "—", "INFO": "·"}.get(verdict, "·")
    LOG.info(f"  {icon} [{rid}] {name}: {verdict}  {metric}  {detail[:100]}")
    if kill and verdict == "FAIL":
        KILL_LOG.append({"id": rid, "name": name, "detail": detail})
        if STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"[{rid}] {name} — {detail}")


# ★ run_backtest 는 {"returns","holdings","gates","label"} 만 돌려준다 — "stats" 키가 없다.
#   그리고 perf_stats 의 키는 **한글**이다("Sharpe","CAGR","MDD","Calmar").
#   영문 소문자 키로 읽으면 전 항목이 조용히 NaN 이 되어 모든 판정이 N/A 로 무너진다.
_STAT_ALIAS = {"sharpe": "Sharpe", "cagr": "CAGR", "mdd": "MDD", "calmar": "Calmar",
               "sortino": "Sortino", "turnover": "월평균회전율", "cost": "월평균비용",
               "tstat": "t통계량(HAC)", "n_months": "월수"}


def _stat(bt: dict, key: str, default: float = float("nan")) -> float:
    if not bt:
        return default
    st = bt.get("_stats")
    if st is None:
        R = bt.get("returns")
        if R is None or not len(R):
            return default
        try:
            st = perf_stats(R)
        except Exception:                                               # noqa
            return default
        bt["_stats"] = st                       # 같은 백테스트를 두 번 재계산하지 않는다
    v = st.get(_STAT_ALIAS.get(key, key), default)
    try:
        return float(v)
    except Exception:                                                   # noqa
        return default


def _has_alpha(bt: dict) -> bool:
    return _stat(bt, "sharpe") >= ALPHA_FLOOR_SHARPE


# ═══════════════════════════════════════════════════════════════════════════════════════════════

def RX0_benchmark(bt: dict, bench: "Dict[str, pd.Series]", months) -> None:
    """R0 — 자체측정 벤치마크 대비. ⭐

    ★ 벤치마크 수치를 하드코딩하지 않는다. 이 실행이 직접 측정한 값만 쓴다(원칙 7).
      과거 인용된 "10년 CAGR 17%" 가 오류로 확인된 바 있다.
    """
    if not bt or not bench:
        _rx("R0", "자체측정 벤치마크 대비", "N/A", "벤치마크를 측정하지 못했습니다.")
        return
    mine = _stat(bt, "calmar")
    rows, beat = [], True
    for nm, s in bench.items():
        b = perf_stats(pd.DataFrame({"ret": pd.to_numeric(s, errors="coerce").fillna(0.0)}))
        c = float(b.get("Calmar", float("nan")))
        rows.append([nm, f"{_f(b.get('CAGR'))*100:6.2f}%",
                     f"{_f(b.get('MDD'))*100:6.2f}%", f"{c:6.3f}"])
        if np.isfinite(c) and np.isfinite(mine) and mine <= c:
            beat = False
    LOG.table(rows + [["★ XCB 전략", f"{_stat(bt,'cagr')*100:6.2f}%",
                       f"{_stat(bt,'mdd')*100:6.2f}%", f"{mine:6.3f}"]],
              ["대상", "CAGR", "MDD", "Calmar"])
    _rx("R0", "자체측정 벤치마크 대비", "PASS" if beat else "FAIL",
        "모든 벤치마크를 Calmar 기준 상회" if beat else
        "벤치마크를 Calmar 기준으로 이기지 못했습니다 — 이 전략을 할 이유가 없습니다.",
        metric=f"Calmar {mine:.3f}", kill=True)


def RX1_leakage(P, months, sec, runner, base_bt: dict) -> None:
    """R1 — 누수 자가검정. 대조군이 **2개**여야 하는 이유가 있다.

    DART 공시는 결산기준일 대비 이미 45~90일 후행한다. -30일 앞당김으로는 여전히 결산일
    이후라 성과가 개선되지 않고, 구현자가 **정상 하네스를 고장났다고 오판**한다.
    그래서 -120일 앞당김과 미래수익률 직접 주입 **둘 다** 본다.

    ★ 판정 근거는 '미래수익률 주입' 하나로 한정한다. 신호 앞당김이 성과를 못 올리는 것은
      하네스 결함이 아니라 '신호에 지속성이 없다'는 별개의 사실이므로, 둘을 한 판정에 묶으면
      두 사건을 구별할 수 없게 된다.
    """
    base = _stat(base_bt, "sharpe")

    # (a) 고의 오염: 미래 3개월 수익률을 신호에 직접 주입 → 반드시 크게 좋아져야 한다
    Q = P.copy()
    fwd = pd.to_numeric(Q.get("fwd_ret"), errors="coerce")
    fwd3 = fwd.groupby(Q["code"], observed=True).shift(-2).fillna(0.0) + fwd.fillna(0.0)
    Q["Signal_rank"] = fwd3.groupby(Q["ym"], observed=True).rank(pct=True)
    bt_leak = runner(Q, label="R1a-미래주입")
    s_leak = _stat(bt_leak, "sharpe")
    ok_a = np.isfinite(s_leak) and np.isfinite(base) and (s_leak > base + 0.5)
    _rx("R1a", "미래수익률 주입(하네스 검정)", "PASS" if ok_a else "FAIL",
        f"주입 Sharpe {s_leak:.3f} vs 기준 {base:.3f} — "
        + ("하네스가 미래정보에 반응합니다(정상)." if ok_a else
           "미래를 알려줘도 성과가 오르지 않습니다. 백테스트 엔진이 고장났고 "
           "이 실행의 **모든 결과가 무효**입니다."),
        metric=f"Δ{s_leak-base:+.3f}", kill=True)

    # (b) 참고: 신호를 120일 앞당김
    Q2 = P.copy()
    Q2["Signal_rank"] = Q2.groupby("code", observed=True)["Signal_rank"].shift(-4)
    bt_adv = runner(Q2, label="R1b-120일선행")
    s_adv = _stat(bt_adv, "sharpe")
    _rx("R1b", "신호 120일 앞당김(참고)", "INFO",
        f"앞당김 Sharpe {s_adv:.3f} vs 기준 {base:.3f}. "
        f"개선이 없다면 '하네스 고장'이 아니라 '신호에 지속성이 없다'는 뜻입니다.",
        metric=f"Δ{s_adv-base:+.3f}")


def RX2_tp_vs_naive(P, months, sec, runner, base_bt: dict) -> None:
    """R2 — 이 시스템의 존재 이유를 정면으로 검정한다. ⭐⭐

        A. clip(z(a1),0) 단독          물량만
        B. clip(z(a2),0) 단독          단가만
        C. TP_X1 = clip × clip         트레이드오프
        D. E 전체 (9개 TP)

    C ≈ max(A,B) 이면 트레이드오프 논리 전체가 불필요한 복잡도다.
    ★ 유리하게 해석 금지. 있는 그대로 보고한다.
    """
    def _run(sig: pd.Series, label: str) -> float:
        Q = P.copy()
        Q["Signal_rank"] = pd.to_numeric(sig, errors="coerce").groupby(
            Q["ym"], observed=True).rank(pct=True)
        return _stat(runner(Q, label=label), "sharpe")

    a1r = xsec_rank_pct_l(P, "a1")
    a2r = xsec_rank_pct_l(P, "a2")
    sA = _run(np.maximum(a1r - 0.5, 0.0), "R2-A-물량단독")
    sB = _run(np.maximum(a2r - 0.5, 0.0), "R2-B-단가단독")
    sC = _run(P["TP_X1"] if "TP_X1" in P.columns else pd.Series(np.nan, index=P.index),
              "R2-C-TP_X1")
    sD = _stat(base_bt, "sharpe")

    LOG.table([["A 물량 단독 clip(z(a1),0)", f"{sA:.3f}"],
               ["B 단가 단독 clip(z(a2),0)", f"{sB:.3f}"],
               ["C TP_X1 = clip × clip", f"{sC:.3f}"],
               ["D E 전체 (9개 TP)", f"{sD:.3f}"]], ["구성", "Sharpe"])
    best_single = np.nanmax([sA, sB])
    if not np.isfinite(sC) or not np.isfinite(best_single):
        _rx("R2", "TP vs 나이브", "N/A", "표본 부족으로 비교가 불가능합니다.")
        return
    margin = sC - best_single
    ok = margin > 0.10
    _rx("R2", "TP vs 나이브 ⭐⭐", "PASS" if ok else "FAIL",
        f"TP_X1 {sC:.3f} vs max(단독) {best_single:.3f} (Δ{margin:+.3f}). "
        + ("트레이드오프 쌍이 단독 지표를 유의하게 이깁니다." if ok else
           "트레이드오프가 단독 지표를 이기지 못합니다 — "
           "이 전략의 패러다임 근거가 소멸했습니다. 복잡도를 정당화할 수 없습니다."),
        metric=f"Δ{margin:+.3f}", kill=True)


def RX3_orthogonal(P: pd.DataFrame, bt: dict) -> None:
    """R3 — 표준 퀄리티/수익성/모멘텀에 직교화한 뒤에도 알파가 남는가."""
    if not _has_alpha(bt):
        _rx("R3", "퀄리티 팩터 직교화", "N/A",
            f"기준 Sharpe {_stat(bt,'sharpe'):.3f} < {ALPHA_FLOOR_SHARPE} — "
            f"직교화할 알파가 애초에 없습니다. 통과로 기록하지 않습니다.")
        return
    R = bt.get("returns")
    if R is None or not len(R):
        _rx("R3", "퀄리티 팩터 직교화", "N/A", "수익률 시계열이 없습니다.")
        return
    y = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy()
    facs = {}
    for nm, col_ in (("quality", "roic"), ("profit", "gpm"), ("mom", "mom12")):
        if col_ in P.columns:
            f = (P.assign(_v=xsec_rank_pct_l(P, col_))
                   .groupby("ym", observed=True)["_v"].mean())
            facs[nm] = f.reindex(pd.DatetimeIndex(R["month"])).to_numpy()
    if not facs:
        _rx("R3", "퀄리티 팩터 직교화", "N/A", "직교화할 팩터를 만들지 못했습니다.")
        return
    X = np.column_stack([np.ones(len(y))] + [np.nan_to_num(v) for v in facs.values()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    # ★★ 절편이 있는 OLS 의 잔차는 **정의상 평균이 정확히 0** 이다.
    #    잔차의 평균을 알파로 재면 항상 0.000% / t=0.00 이 나와 R3 은 **구조적으로
    #    영원히 FAIL** 한다(실측: mu=-0.000%, t=-0.00, p=1.000).
    #    직교화 알파는 잔차 평균이 아니라 **절편 계수 β₀** 다.
    #    HAC 로 자기상관을 보정하려면 '절편을 되돌린 잔차' 시계열의 평균을 검정한다.
    alpha_t = beta[0] + (y - X @ beta)       # 평균 = β₀, 변동 = 잔차
    mu_r, t_r = hac_tstat(alpha_t)
    # 양측 정규근사 p값 (statsmodels 없이도 성립)
    p_r = float(math.erfc(abs(t_r) / math.sqrt(2.0))) if np.isfinite(t_r) else float("nan")
    ok = np.isfinite(p_r) and p_r < 0.10 and mu_r > 0
    _rx("R3", "퀄리티 팩터 직교화", "PASS" if ok else "FAIL",
        f"직교화 후 알파(절편) 월 {mu_r*100:.3f}% (t={t_r:.2f}, p={p_r:.3f}) "
        f"· 통제 {list(facs)}",
        metric=f"t={t_r:.2f}", kill=True)


def RX4_placebo(gate3: dict) -> None:
    """R4 — 플라시보 매핑. 게이트3 결과를 그대로 승계한다(재계산하지 않는다).

    ⚠ 회귀를 1,000번 재적합하면 250시간이다. 게이트3 이 이미 롤링 적률을 재사용하고
      매핑 행렬만 셔플해 행렬곱 1,000회로 끝냈다 — 그 결과를 두 번 계산할 이유가 없다.
    """
    if not gate3 or not np.isfinite(gate3.get("p", float("nan"))):
        _rx("R4", "플라시보 매핑", "N/A", gate3.get("detail", "판정 불가"))
        return
    ok = bool(gate3.get("pass"))
    _rx("R4", "플라시보 매핑(행렬 셔플)", "PASS" if ok else "FAIL",
        gate3.get("detail", ""), metric=f"p={gate3.get('p'):.4f}", kill=True)


# 정책 캘린더 (§10). 시행일은 공개되어 있고 정확하므로 자연실험 설계가 가능하다.
# ★ 원문 확인 대상이며 추측으로 늘리지 않는다. 각 항목의 근거 URL 을 함께 보관한다.
XCB_POLICY_CALENDAR: "List[dict]" = [
    {"date": "2015-12-20", "name": "한·중 FTA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/cn/"},
    {"date": "2015-12-20", "name": "한·베트남 FTA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/vn/"},
    {"date": "2016-07-01", "name": "대중국 사드 배치 발표(한한령 시발)", "kind": "TRADE_SHOCK",
     "url": "https://www.mofa.go.kr/"},
    {"date": "2019-01-01", "name": "한·미 FTA 개정의정서 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/us/"},
    {"date": "2019-07-04", "name": "일본 대한 수출규제(반도체·디스플레이 3품목)",
     "kind": "EXPORT_CONTROL", "url": "https://www.motie.go.kr/"},
    {"date": "2020-03-11", "name": "COVID-19 팬데믹 선언", "kind": "SHOCK",
     "url": "https://www.who.int/"},
    {"date": "2022-02-01", "name": "RCEP 발효(한국)", "kind": "FTA",
     "url": "https://www.fta.go.kr/rcep/"},
    {"date": "2022-03-01", "name": "대러시아 수출통제", "kind": "EXPORT_CONTROL",
     "url": "https://www.motie.go.kr/"},
    {"date": "2022-08-16", "name": "미국 IRA 발효", "kind": "FOREIGN_POLICY",
     "url": "https://www.congress.gov/bill/117th-congress/house-bill/5376"},
    {"date": "2022-10-07", "name": "미국 대중 반도체 수출통제", "kind": "EXPORT_CONTROL",
     "url": "https://www.bis.doc.gov/"},
    {"date": "2023-01-01", "name": "한·인도네시아 CEPA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/id/"},
    {"date": "2024-01-01", "name": "한·이스라엘 FTA 발효(2022-12) 후속 관세 인하",
     "kind": "FTA", "url": "https://www.fta.go.kr/il/"},
]


def RX10_policy(P, months, sec, runner, base_bt: dict) -> None:
    """R10 — 정책 반증. ⭐  정책 이벤트 ±6M 을 전부 빼도 알파가 남는가.

    ★ 정책 시행일은 공개되어 있고 정확하다. 그래서 이 오염은 다른 대체데이터 오염과 달리
      **자연실험 설계가 가능**하다. 필터를 쌓는 것보다 반증 검정이 우선이다.
    """
    if not _has_alpha(base_bt):
        _rx("R10", "정책 반증", "N/A",
            f"기준 Sharpe {_stat(base_bt,'sharpe'):.3f} < {ALPHA_FLOOR_SHARPE} — "
            f"제거할 알파가 없어 판정하지 않습니다.")
        return
    ev = pd.DataFrame(XCB_POLICY_CALENDAR)
    ev["date"] = as_ts_series(ev["date"])
    mask = pd.Series(False, index=pd.DatetimeIndex(months))
    for dt0 in ev["date"].dropna():
        mask |= (mask.index >= dt0 - pd.DateOffset(months=6)) & \
                (mask.index <= dt0 + pd.DateOffset(months=6))
    keep = pd.DatetimeIndex(mask.index[~mask])
    if len(keep) < 24:
        _rx("R10", "정책 반증", "N/A",
            f"정책 구간을 제외하면 {len(keep)}개월만 남아 검정이 불가능합니다.")
        return
    Q = P[P["ym"].isin(keep)].copy()
    bt = runner(Q, months=keep, label="R10-정책제외")
    s0, s1 = _stat(base_bt, "sharpe"), _stat(bt, "sharpe")
    ok = np.isfinite(s1) and s1 >= max(0.0, s0 * 0.5)
    _rx("R10", "정책 반증 ⭐", "PASS" if ok else "FAIL",
        f"정책 ±6M {len(months)-len(keep)}개월 제외 → Sharpe {s1:.3f} (기준 {s0:.3f}). "
        + ("정책 구간을 빼도 알파가 유지됩니다." if ok else
           "정책 구간을 빼면 알파가 사라집니다 — 이 전략은 정책 베팅에 불과합니다. A축 폐기."),
        metric=f"{s1:.3f}/{s0:.3f}", kill=True)


def RX5_ablation(P, months, sec, runner, base_bt: dict, rescore) -> pd.DataFrame:
    """R5 — 절제. 무엇이 실제로 기여하는지 귀속한다.

    ★ A축 제거로 성과가 안 떨어지면 이 전략의 근거가 소멸한다 → 리포트 최상단에 둔다.
    """
    base = _stat(base_bt, "sharpe")
    rows = []

    def _try(label: str, **kw):
        try:
            Q = rescore(**kw)
            s = _stat(runner(Q, label=f"R5-{label}"), "sharpe")
        except Exception as e:                                          # noqa
            LOG.debug(f"R5 {label} 실패: {type(e).__name__}")
            s = float("nan")
        rows.append({"항목": label, "Sharpe": s, "Δ vs 기준": s - base})

    for ax in ("A", "B", "C", "D"):
        _try(f"축제거:{ax}", drop_axes=[ax])
    for t in XCB_TP_COLS:
        _try(f"TP제거:{t}", drop_tps=[t])
    for m in ("zclip", "rankprod", "signed"):
        _try(f"TP방식:{m}", tp_mode=m)
    _try("θ_X 미가중", use_theta=False)
    for cv in (0.15, 0.35):
        _try(f"커모디티임계:{int(cv*100)}%", cv_thresh_pct=cv)
    for bf in (0.0, 0.6):
        _try(f"하한선:{bf:.1f}", breadth_floor=bf)

    A = pd.DataFrame(rows).sort_values("Δ vs 기준")
    # A축 제거 결과를 맨 위로 — 이 전략의 존재 근거이므로.
    A["_k"] = np.where(A["항목"] == "축제거:A", 0, 1)
    A = A.sort_values(["_k", "Δ vs 기준"]).drop(columns=["_k"]).reset_index(drop=True)
    LOG.banner("R5 절제 — A축 제거 결과가 맨 위", f"기준 Sharpe {base:.3f}")
    LOG.table([[r["항목"], f"{r['Sharpe']:.3f}", f"{r['Δ vs 기준']:+.3f}"]
               for _, r in A.head(20).iterrows()], ["절제 항목", "Sharpe", "Δ"])
    a_row = A[A["항목"] == "축제거:A"]
    if len(a_row):
        d = float(a_row["Δ vs 기준"].iloc[0])
        ok = d < -0.05
        _rx("R5", "절제 — A축(통관) 기여", "PASS" if ok else "FAIL",
            f"A축 제거 시 Sharpe {d:+.3f}. "
            + ("통관 축이 실제로 기여합니다." if ok else
               "통관을 빼도 성과가 그대로입니다 — 이 전략을 할 이유가 없습니다."),
            metric=f"Δ{d:+.3f}", kill=True)
    return A


def RX6_pbo(abl: pd.DataFrame) -> None:
    """R6 — PBO/DSR. R5 가 만든 구성집합 위에서 CSCV. 백테스트 **재실행 0회**."""
    if abl is None or len(abl) < 6:
        _rx("R6", "PBO / DSR", "N/A", "구성집합이 부족합니다.")
        return
    s = pd.to_numeric(abl["Sharpe"], errors="coerce").dropna().to_numpy()
    if len(s) < 6:
        _rx("R6", "PBO / DSR", "N/A", "유효 구성이 부족합니다.")
        return
    # 구성 간 성과 산포로 과적합 확률을 근사한다(구성 수가 적어 CSCV 정식은 과하다).
    rank_best = float((s < s.max()).mean())
    dsr = float((s.mean()) / (s.std(ddof=1) + 1e-9))
    _rx("R6", "PBO / DSR", "INFO",
        f"구성 {len(s)}개 · 최고 구성의 상대순위 {rank_best:.2f} · 구성간 Sharpe "
        f"평균 {s.mean():.3f} 표준편차 {s.std(ddof=1):.3f} (DSR 근사 {dsr:.2f}). "
        f"파라미터 수를 줄일수록 이 값이 안정됩니다.", metric=f"DSR≈{dsr:.2f}")


def RX7_regime(bt: dict, bench: "Dict[str, pd.Series]") -> None:
    """R7 — 레짐 분할. 의존성을 숨기지 않고 공개한다."""
    R = (bt or {}).get("returns")
    if R is None or not len(R):
        _rx("R7", "레짐 분할", "N/A", "수익률 시계열이 없습니다.")
        return
    d = R.copy()
    d["month"] = as_ts_series(d["month"])
    segs = [("2016~2018", "2016-01-01", "2018-12-31"),
            ("2019~2020 (일본수출규제·COVID)", "2019-01-01", "2020-12-31"),
            ("2021~2022 (공급망·인플레)", "2021-01-01", "2022-12-31"),
            ("2023~2026", "2023-01-01", "2026-12-31")]
    rows = []
    for nm, a, b in segs:
        sub = d[(d["month"] >= a) & (d["month"] <= b)]
        if len(sub) < 6:
            rows.append([nm, "표본부족", "", ""])
            continue
        st = perf_stats(sub)
        rows.append([nm, f"{_f(st.get('CAGR'))*100:6.2f}%",
                     f"{_f(st.get('MDD'))*100:6.2f}%",
                     f"{_f(st.get('Sharpe')):6.3f}"])
    LOG.table(rows, ["레짐", "CAGR", "MDD", "Sharpe"])
    _rx("R7", "레짐 분할", "INFO", "구간별 성과를 공개합니다. 특정 레짐 의존이면 위 표에 드러납니다.")


def RX9_capacity(P, months, sec, runner, base_bt: dict) -> None:
    """R9 — 회전율·비용 3시나리오. 비관에서도 살아남아야 실행 가능하다."""
    rows = []
    base = _stat(base_bt, "sharpe")
    scen = [("낙관 왕복 0.35%", 0.0035), ("기준 0.80%", 0.0080), ("비관 1.50%", 0.0150)]
    worst = float("nan")
    for nm, cost in scen:
        try:
            bt = runner(P, label=f"R9-{nm}", cost_override=cost)
            s, c = _stat(bt, "sharpe"), _stat(bt, "cagr")
            rows.append([nm, f"{c*100:6.2f}%", f"{s:6.3f}",
                         f"{_stat(bt,'turnover')*100:5.1f}%"])
            if "비관" in nm:
                worst = s
        except Exception as e:                                          # noqa
            rows.append([nm, "실패", type(e).__name__, ""])
    LOG.table(rows, ["시나리오", "CAGR", "Sharpe", "월회전율"])
    ok = np.isfinite(worst) and worst > 0.0
    _rx("R9", "회전율·비용 3시나리오", "PASS" if ok else "FAIL",
        f"비관(왕복 1.50% + 거래대금 참여 {POS_ADV_PARTICIPATION*100:.0f}% 상한) Sharpe {worst:.3f}. "
        + ("비용을 비관적으로 잡아도 성과가 남습니다." if ok else
           "비관 시나리오에서 성과가 소멸합니다 — 소액계좌라도 실행 불가입니다."),
        metric=f"{worst:.3f}", kill=True)
    _rx("R9b", "우측꼬리 의존", "INFO", _tail_note(base_bt), metric="")


def _tail_note(bt: dict) -> str:
    """§15.1 — 상위 5% 종목을 빼면 성과가 사라지는지. 리포트 첫 페이지에 명시할 값."""
    try:
        rt = right_tail_contribution(bt)
        return (f"원본 CAGR {_f(rt.get('원본 CAGR'))*100:.2f}% → "
                f"상위1% 제외 {_f(rt.get('상위1% 제외 CAGR'))*100:.2f}% · "
                f"상위5% 제외 {_f(rt.get('상위5% 제외 CAGR'))*100:.2f}% "
                f"(Sharpe {_f(rt.get('상위5% 제외 Sharpe')):.3f}). "
                f"유니버스가 얇아 우측 꼬리 의존이 큽니다 — 리포트 첫 페이지에 둡니다.")
    except Exception:                                                   # noqa
        return "우측꼬리 기여도를 계산하지 못했습니다."


def report_robustness_xcb() -> None:
    LOG.banner("강건성 검사 결과 R0~R10",
               "킬 기준(⭐)은 통과시키지 않는다. 나쁜 결과는 그 자체로 정보다.")
    LOG.table([[r["id"], r["name"][:26], r["verdict"], r["metric"][:16], r["detail"][:56]]
               for r in ROBUST_LOG], ["ID", "검사", "판정", "지표", "내용"])
    if KILL_LOG:
        LOG.banner("★ 킬 기준 발동", f"{len(KILL_LOG)}건 — 파라미터로 통과시키지 않습니다")
        for k in KILL_LOG:
            LOG.error(f"[{k['id']}] {k['name']} — {k['detail'][:150]}")
    else:
        LOG.ok("킬 기준 위반 없음.")
