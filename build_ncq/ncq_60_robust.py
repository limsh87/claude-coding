

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  ARC-NCQ 강건성·통계검증 계층 (§11)                                                   ║
# ║                                                                                          ║
# ║  목적 : "이 성과가 우연·과적합·비용무시·소스편향의 산물이 아님"을 사전등록된 순서로        ║
# ║         정면 검정한다. 사전등록 가설 P1~P4 → BH-FDR → 부트스트랩/순열/워크포워드/        ║
# ║         PBO/DSR/Holm → 민감도 9조합 → 구조적 리스크 R1~R6.                               ║
# ║                                                                                          ║
# ║  입력 : SIG(신호패널) · BT(백테스트 결과 dict) · bench_ew(Bottom-N 동일가중 월수익)       ║
# ║         months(월말 DatetimeIndex) · ctx(파이프라인 산출물 모음: dict 또는 객체)          ║
# ║         run_fn(SIG, hold_months=, cost_roundtrip=, sel_col=, label=) -> BT   ← 스파인 주입 ║
# ║         build_sig_fn(top_pct=, min_adv=) -> SIG                              ← 스파인 주입 ║
# ║  출력 : NCQ_ROBUST 원장(OrderedDict) + LOG.table 표 + 사전등록/민감도 DataFrame           ║
# ║                                                                                          ║
# ║  실패 시 동작 :                                                                           ║
# ║    · 표본 부족(월수<12, 이벤트<50 …)·콜백 부재·백테스트 실패 → 예외가 아니라              ║
# ║      passed=None(판정불가) + 사유 문자열. 없는 결론을 만들어내지 않는다.                   ║
# ║    · 사전등록 채택 기준 미충족 → ⭐킬 게이트. 다만 반환 dict 를 NCQ_PREREG_RESULT 전역에   ║
# ║      먼저 저장한 뒤 올리므로, 호출부가 KillCriteria 를 잡아도 근거는 사라지지 않는다.      ║
# ║                                                                                          ║
# ║  ★ 원칙 : 나쁜 결과를 좋게 보이게 만들지 않는다. 실패·판정불가는 그대로 출력한다.          ║
# ║           결측은 "—" 로 표기하고 절대 0 으로 치환하지 않는다.                              ║
# ║           없는 최적화를 있는 척하지 않는다(워크포워드 주석 참조).                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 원장 / 모듈 상태 ────────────────────────────────────────────────────────────────────────
NCQ_ROBUST: "OrderedDict[str, dict]" = OrderedDict()

# 민감도 실행이 남기는 부산물. run_stat_suite 의 PBO(CSCV)·Holm 이 인자 없이도 이걸 주워 쓴다.
# (성과 벡터가 1개뿐이면 PBO 는 '근사'가 되므로, 민감도 9조합 곡선이 있으면 정식 CSCV 가 된다)
NCQ_SENS_CURVES: "OrderedDict[str, pd.Series]" = OrderedDict()
NCQ_SENS_TABLE = None                 # 마지막 run_sensitivity 반환 표 (Holm 입력)
NCQ_PREREG_RESULT = None              # 킬 게이트 발동 전에 저장되는 사전등록 결과

# 검정 상수 (사전등록 값 — 결과를 보고 바꾸지 말 것)
NCQ_FDR_Q = 0.10                      # BH-FDR α (P1~P4 전체에 적용)
NCQ_HAC_LAG = 12                      # Newey-West lag (보유 12개월 오버랩과 맞춤)
NCQ_BOOT_BLOCK = 12                   # 블록 부트스트랩 블록 길이(개월)
NCQ_BOOT_ITER = 1000
NCQ_PERM_ITER = 1000
NCQ_CSCV_S = 16                       # PBO 분할 수
NCQ_CSCV_MAX_COMBOS = 2000            # 조합 폭발 시 무작위 표본 상한
NCQ_WF_IS_M = 60                      # 워크포워드 IS 5년
NCQ_WF_OOS_M = 12                     # OOS 롤링 1년
NCQ_WF_STEP_M = 12                    # 1년 스텝
NCQ_HOLM_ALPHA = 0.05
NCQ_COST_STRESS = 0.030               # 채택 조건의 왕복비용 스트레스 시나리오
NCQ_MIN_MONTHS = 12                   # 이보다 짧으면 HAC t 자체가 정의되지 않는다
NCQ_MIN_EVENTS_SUB = 50               # 서브그룹 검정 최소 이벤트 수


# ══════════════════════════════════════════════════════════════════════════════════════════
#  0. 공용 유틸 — 정렬·포맷·안전 접근
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_cfg(name: str, default):
    """헤더 상수를 안전하게 읽는다. 조립 순서가 바뀌거나 헤더가 축약돼도 이 계층은 죽지 않는다."""
    v = globals().get(name, None)
    return default if v is None else v


def ncq_f(v, kind: str = "num", nd: int = 3) -> str:
    """결측/비유한은 항상 '—'. NaN 을 0 으로 치환하지 않는다(계약 §3)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(x):
        return "—"
    if kind == "pct":
        return f"{x * 100:+.2f}%"
    if kind == "pctp":
        return f"{x * 100:+.3f}%p"
    if kind == "pct0":
        return f"{x * 100:.1f}%"
    if kind == "p":
        return f"{x:.4f}"
    if kind == "t":
        return f"{x:+.2f}"
    if kind == "int":
        return f"{int(round(x)):,}"
    return f"{x:,.{nd}f}"


def ncq_mark(passed) -> str:
    """True/False/None → 표에 쓰는 판정 아이콘. None 은 '실패'가 아니라 '판정불가'다."""
    if passed is None:
        return "— 판정불가"
    return "✔ 통과" if bool(passed) else "✘ 실패"


def ncq_is_pass(v) -> bool:
    """'명시적 통과'인가. 판정불가(None)는 통과가 아니다.

    ★ `v is True` 로 쓰면 안 된다 — np.True_ is True 는 False 라서, numpy bool 이 한 번이라도
      섞이면 통과 분기가 조용히 죽는다(판정이 전부 '실패'로 보이는 사고). 여기로만 통과시킨다.
    """
    return v is not None and bool(v)


def ncq_is_fail(v) -> bool:
    """'명시적 실패'인가. 판정불가(None)는 실패가 아니다(킬 게이트를 발동시키지 않는다).

    ★ `v is False` 금지 — np.False_ is False 가 False 라 킬 게이트가 발동하지 않는 사고가 났다.
    """
    return v is not None and not bool(v)


def ncq_ctx_get(ctx, key: str, default=None):
    """ctx 가 dict 이든 네임스페이스 객체이든 동일하게 꺼낸다. 없으면 default."""
    if ctx is None:
        return default
    try:
        if isinstance(ctx, dict):
            v = ctx.get(key, None)
            return default if v is None else v
    except Exception:
        pass
    v = getattr(ctx, key, None)
    return default if v is None else v


def ncq_boolmask(s) -> pd.Series:
    """selected/placebo 같은 이진 컬럼 → bool 마스크. NaN 은 False(=선택 안 됨)로 본다.

    ★ .astype(bool) 을 그냥 쓰면 NaN 이 True 가 되어 '선택되지 않은 종목이 조용히 편입'된다.
    """
    if s is None:
        return pd.Series(dtype=bool)
    x = pd.Series(s)
    if x.dtype == bool:
        return x
    if x.dtype.kind in "iufb":
        return (pd.to_numeric(x, errors="coerce").fillna(0) != 0)
    return x.map(lambda v: bool(v) if (v is not None and v == v) else False).astype(bool)


def ncq_month_series(x, col: str = "ret") -> pd.Series:
    """무엇이 들어오든 'month(DatetimeIndex) → 값' Series 로 정규화한다.

    ★ 두 팔의 시계열을 뺄 때 위치 기반(iloc) 뺄셈은 금지다. 길이가 하루라도 다르면
      조용히 다른 달끼리 빼면서 그럴듯한 숫자를 만든다. 모든 시계열은 이 관문을 통과시킨 뒤
      ncq_align_diff 로만 뺀다.
    """
    if x is None:
        return pd.Series(dtype="float64")
    if isinstance(x, dict):                       # BT dict
        x = x.get("returns")
    if isinstance(x, pd.DataFrame):
        if x.empty or "month" not in x.columns:
            return pd.Series(dtype="float64")
        use = col if col in x.columns else ("ret" if "ret" in x.columns else None)
        if use is None:
            return pd.Series(dtype="float64")
        vals = pd.to_numeric(x[use], errors="coerce").to_numpy(dtype="float64")
        idx = pd.to_datetime(pd.Series(x["month"]), errors="coerce")
    elif isinstance(x, pd.Series):
        vals = pd.to_numeric(x, errors="coerce").to_numpy(dtype="float64")
        idx = pd.to_datetime(pd.Series(x.index), errors="coerce")
    else:
        return pd.Series(dtype="float64")
    try:
        idx = pd.DatetimeIndex(idx).normalize()
    except Exception:
        return pd.Series(dtype="float64")
    s = pd.Series(vals, index=idx, name=col)
    s = s[~s.index.isna()]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def ncq_align_diff(a: pd.Series, b: pd.Series) -> pd.Series:
    """month 인덱스 교집합에서만 뺀다. 교집합이 비면 빈 Series(길이 0)."""
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return pd.Series(dtype="float64")
    idx = a.index.intersection(b.index)
    if len(idx) == 0:
        return pd.Series(dtype="float64")
    return (a.reindex(idx) - b.reindex(idx)).dropna().sort_index()


def ncq_cum_return(s) -> float:
    """누적수익 = ∏(1+r)-1. 결측은 계산에서 제외(0으로 채우지 않는다)."""
    x = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    if x.empty:
        return float("nan")
    return float(np.prod(1.0 + x.to_numpy(dtype="float64")) - 1.0)


def ncq_sharpe(BT) -> float:
    """BT 의 연율 Sharpe. perf_stats(스파인) 우선, 실패하면 월수익 기반으로 직접 계산."""
    R = BT.get("returns") if isinstance(BT, dict) else BT
    if not isinstance(R, pd.DataFrame) or R.empty or "ret" not in R.columns:
        return float("nan")
    try:
        st = perf_stats(R)                                    # noqa — ncq_50_backtest 제공
        if st:
            v = st.get("Sharpe", None)
            if v is not None and np.isfinite(float(v)):
                return float(v)
    except Exception:
        pass
    r = pd.to_numeric(R["ret"], errors="coerce").dropna().to_numpy(dtype="float64")
    if len(r) < 2:
        return float("nan")
    sd = float(r.std(ddof=1))
    return float(r.mean() / sd * math.sqrt(12.0)) if sd > 0 else float("nan")


def ncq_norm_cdf(z) -> float:
    """표준정규 CDF. scipy 없이도 되게 math.erfc 로 계산한다(부트스트랩 환경 편차 방지)."""
    try:
        x = float(z)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x):
        return float("nan")
    return float(0.5 * math.erfc(-x / math.sqrt(2.0)))


def ncq_p_onesided(t) -> float:
    """방향 가설(> 0)의 단측 p = 1 - Φ(t). 양측을 반으로 나누지 않고 정의대로 계산한다."""
    try:
        x = float(t)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x):
        return float("nan")
    return float(1.0 - ncq_norm_cdf(x))


def ncq_hac(x, lags: int = None):
    """(월평균, HAC t). 표본이 12개월 미만이면 (nan, nan) — 억지로 t 를 만들지 않는다."""
    if isinstance(x, pd.Series):
        x = x.to_numpy(dtype="float64")
    arr = np.asarray(x, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if len(arr) < NCQ_MIN_MONTHS:
        return (float("nan"), float("nan"))
    L = NCQ_HAC_LAG if lags is None else int(lags)
    try:
        mu, t = hac_tstat(arr, lags=L)
        return (float(mu), float(t))
    except Exception:
        return (float("nan"), float("nan"))


def ncq_bh_adjusted(pvals) -> np.ndarray:
    """BH 보정 p값(step-up). bh_fdr 은 통과여부만 주므로 '얼마나 아슬아슬한지'를 같이 보인다."""
    p = np.asarray(pvals, dtype="float64")
    out = np.full(p.shape, np.nan, dtype="float64")
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.clip(adj, 0.0, 1.0)
    return out


def ncq_holm(pvals, alpha: float = None) -> np.ndarray:
    """Holm-Bonferroni step-down. 첫 미기각에서 즉시 멈춘다(절차 정의 그대로)."""
    a = NCQ_HOLM_ALPHA if alpha is None else float(alpha)
    p = np.asarray(pvals, dtype="float64")
    out = np.zeros(p.shape, dtype=bool)
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    for i, j in enumerate(order):
        if p[j] <= a / max(m - i, 1):
            out[j] = True
        else:
            break
    return out


def ncq_moments(x):
    """(왜도, 첨도[정규=3]). scipy 있으면 scipy, 없으면 직접 계산."""
    arr = np.asarray(x, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if len(arr) < 4:
        return (float("nan"), float("nan"))
    try:
        from scipy import stats as _st
        return (float(_st.skew(arr)), float(_st.kurtosis(arr, fisher=False)))
    except Exception:
        mu = arr.mean()
        sd = arr.std(ddof=0)
        if not np.isfinite(sd) or sd <= 0:
            return (float("nan"), float("nan"))
        z = (arr - mu) / sd
        return (float(np.mean(z ** 3)), float(np.mean(z ** 4)))


def ncq_run(run_fn, label: str, SIG, extra=None, **kw):
    """run_fn 호출 래퍼. 실패는 삼키지 않고 **None 을 돌려주고 사유를 로그에 남긴다.**

    반환 None 을 받은 검정은 반드시 passed=None(판정불가)으로 기록한다 —
    실패한 팔을 조용히 건너뛰면 '통과'로 오해되기 때문이다.
    extra: run_fn 이 (SIG, pxm, sec, uni_obj, months) 를 직접 받는 형태일 때의 추가 위치인자.
    """
    if run_fn is None:
        LOG.warn(f"[{label}] run_fn 이 주입되지 않아 실행할 수 없습니다.")
        return None
    try:
        return run_fn(SIG, label=label, **kw)
    except TypeError as e:
        if extra:
            try:
                return run_fn(SIG, *extra, label=label, **kw)
            except Exception as e2:                                   # noqa
                LOG.error(f"[{label}] run_fn 재호출 실패 — {type(e2).__name__}: {e2}")
                return None
        LOG.error(f"[{label}] run_fn 인자 불일치 — {e}. 이 팔은 판정에서 제외합니다.")
        return None
    except Exception as e:                                            # noqa
        LOG.error(f"[{label}] 백테스트 실패 — {type(e).__name__}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  1. 원장 기록기
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_record(rid: str, name: str, passed, detail: str,
               kill: bool = False, metrics: Optional[dict] = None) -> None:
    """검정 결과를 NCQ_ROBUST 에 남기고 즉시 한 줄 출력한다.

    passed 는 True(통과) / False(실패) / None(판정불가) 세 가지다.
    ★ numpy bool 주의: `np.False_ is False` 는 False 다. `is False` 분기가 조용히 안 먹어서
      킬 게이트가 발동하지 않는 사고가 실제로 있었다. 여기서 파이썬 bool 로 강제 변환하고,
      이후 분기는 전부 ncq_is_pass / ncq_is_fail 로만 판단한다(항등비교 금지).
    """
    passed = None if passed is None else bool(passed)
    NCQ_ROBUST[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                       "kill": bool(kill), "metrics": dict(metrics or {})}
    icon = ncq_mark(passed)
    emit = LOG.warn if passed is None else (LOG.ok if passed else LOG.error)
    emit(f"[{rid}] {name} → {icon} · {detail}")
    if ncq_is_fail(passed) and kill and ncq_cfg("STOP_ON_KILL_CRITERIA", True):
        raise KillCriteria(f"[{rid}] {name} — {detail}")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  2. §11.1 사전등록 가설 P1~P4 + BH-FDR + 채택 기준
# ══════════════════════════════════════════════════════════════════════════════════════════

def run_prereg_tests(SIG, BT, bench_ew, pxm, sec, uni_obj, months, run_fn) -> dict:
    """사전등록 가설 P1~P4 를 검정하고 BH-FDR(α=0.10)을 P1~P4 **전체**에 적용한다.

      P1  전략(신규커버리지 × 텍스트 z 상위 tercile) 월별 초과수익(vs Bottom-N 동일가중) > 0
      P2  z 상위 tercile − z 하위 tercile(placebo) 롱숏 스프레드 > 0
      P3  ORGANIC_ONLY 서브그룹만으로 P1 재검정 (스폰서 리포트가 만든 것이 아님을 확인)
      P4  전 이벤트 동일가중(선정 없이 이벤트 전부 보유) 대비 z 상위 스프레드 > 0
          = 텍스트 점수의 '증분' 정보. 이벤트 발생 자체의 효과와 분리한다.

    채택(§11.1) = P1·P3 가 BH-FDR 통과  AND  왕복비용 3.0% 에서도 초과수익>0
                  AND  placebo 대비 스프레드>0.

    반환: {"table": DataFrame[id,hypothesis,stat,t,p,p_bh,pass], "adopt": bool, "detail": {...}}
    표본 부족·콜백 부재는 예외 대신 passed=None + 사유. 채택 미충족은 ⭐킬 게이트이며,
    반환 dict 는 그 전에 NCQ_PREREG_RESULT 전역에 저장된다.
    """
    global NCQ_PREREG_RESULT
    LOG.banner("사전등록 검정 P1~P4 (§11.1)",
               "가설은 수익률을 보기 전에 동결되었다 · BH-FDR α=0.10 · HAC lag=12 · 단측")

    bench = ncq_month_series(bench_ew)
    strat = ncq_month_series(BT)
    if len(bench) == 0:
        LOG.warn("Bottom-N 동일가중 벤치마크가 비었습니다 — 초과수익 검정(P1·P3)은 판정불가가 됩니다.")

    S = SIG if isinstance(SIG, pd.DataFrame) else pd.DataFrame()
    has_sig = (not S.empty) and {"month", "code"}.issubset(set(S.columns))
    detail: Dict[str, Any] = {"n_month_strategy": int(len(strat)), "n_month_bench": int(len(bench))}
    rows = []                       # (id, hypothesis, stat, t, p, note)

    # ── P1 ────────────────────────────────────────────────────────────────────────────────
    ex1 = ncq_align_diff(strat, bench)
    mu1, t1 = ncq_hac(ex1)
    p1 = ncq_p_onesided(t1)
    note1 = (f"공통 {len(ex1)}개월" if len(ex1) >= NCQ_MIN_MONTHS
             else f"공통 {len(ex1)}개월 — {NCQ_MIN_MONTHS}개월 미만이라 판정불가")
    rows.append(["P1", "전략 초과수익(vs Bottom-N EW) > 0", mu1, t1, p1, note1])
    detail["P1"] = {"months": int(len(ex1)), "mu": mu1, "t": t1, "p": p1}

    # ── P2 : placebo(하위 tercile) 팔을 실제로 돌린다 ──────────────────────────────────────
    #   z 상위 팔은 본선 BT 를 그대로 쓴다(동일 설정). 불필요한 재계산을 하지 않는다.
    bt_pl = None
    if has_sig and "placebo" in S.columns and int(ncq_boolmask(S["placebo"]).sum()) > 0:
        bt_pl = ncq_run(run_fn, "P2_placebo_bottom", S, extra=(pxm, sec, uni_obj, months),
                        sel_col="placebo")
    else:
        LOG.warn("SIG 에 placebo(하위 tercile) 표식이 없거나 비어 있어 P2 를 돌릴 수 없습니다.")
    pl = ncq_month_series(bt_pl)
    d2 = ncq_align_diff(strat, pl)
    mu2, t2 = ncq_hac(d2)
    p2 = ncq_p_onesided(t2)
    note2 = (f"공통 {len(d2)}개월 · placebo 월평균 "
             f"{ncq_f(pl.mean() if len(pl) else np.nan, 'pctp')}"
             if len(d2) >= NCQ_MIN_MONTHS else
             ("placebo 팔 실행 실패 — 판정불가" if bt_pl is None
              else f"공통 {len(d2)}개월 — 표본 부족으로 판정불가"))
    rows.append(["P2", "z상위 − z하위(placebo) 스프레드 > 0", mu2, t2, p2, note2])
    detail["P2"] = {"months": int(len(d2)), "mu": mu2, "t": t2, "p": p2,
                    "arm_ok": bt_pl is not None}

    # ── P3 : ORGANIC_ONLY 서브그룹 재검정 ─────────────────────────────────────────────────
    #   ★ tercile 소속은 '전체 횡단면에서 매긴 순위'를 그대로 물려받는다. 유기적 리포트만
    #     따로 모아 다시 순위를 매기면, 실제 운용 시점에 알 수 없는 정보로 재선별하는 셈이라
    #     그 자체가 미래참조가 된다. 여기서는 '이미 선정된 것 중 유기적인 것만' 본다.
    bt_org = None
    n_org = 0
    reason3 = ""
    if has_sig and "sponsor_group" in S.columns:
        org_mask = S["sponsor_group"].astype(str).str.upper().eq("ORGANIC_ONLY")
        sel_mask = ncq_boolmask(S["selected"]) if "selected" in S.columns else pd.Series(
            True, index=S.index)
        n_org = int((org_mask & sel_mask).sum())
        n_org_m = int(S.loc[org_mask & sel_mask, "month"].nunique()) if n_org else 0
        if n_org < NCQ_MIN_EVENTS_SUB or n_org_m < NCQ_MIN_MONTHS:
            reason3 = (f"ORGANIC_ONLY 선정 이벤트 {n_org}건 / {n_org_m}개월 — "
                       f"기준({NCQ_MIN_EVENTS_SUB}건·{NCQ_MIN_MONTHS}개월) 미달이라 판정불가")
            LOG.warn("P3 표본 부족 — " + reason3)
        else:
            bt_org = ncq_run(run_fn, "P3_organic_only", S[org_mask].copy(),
                             extra=(pxm, sec, uni_obj, months))
            if bt_org is None:
                reason3 = "ORGANIC_ONLY 백테스트 실행 실패"
    else:
        reason3 = "SIG 에 sponsor_group 컬럼이 없어 스폰서 분리가 불가능"
        LOG.warn("P3 — " + reason3)
    ex3 = ncq_align_diff(ncq_month_series(bt_org), bench)
    mu3, t3 = ncq_hac(ex3)
    p3 = ncq_p_onesided(t3)
    note3 = reason3 or f"유기적 이벤트 {n_org:,}건 · 공통 {len(ex3)}개월"
    rows.append(["P3", "ORGANIC_ONLY 서브그룹 초과수익 > 0", mu3, t3, p3, note3])
    detail["P3"] = {"months": int(len(ex3)), "mu": mu3, "t": t3, "p": p3,
                    "n_events": n_org, "reason": reason3}

    # ── P4 : 전 이벤트 동일가중 대비 증분 ─────────────────────────────────────────────────
    bt_all = None
    if has_sig:
        S_all = S.copy()
        S_all["ncq_all_ev"] = True          # 선정하지 않고 이벤트를 전부 보유하는 팔
        bt_all = ncq_run(run_fn, "P4_all_events", S_all, extra=(pxm, sec, uni_obj, months),
                         sel_col="ncq_all_ev")
    all_s = ncq_month_series(bt_all)          # ★ DataFrame 을 if 로 평가하면 ValueError 가 난다
    d4 = ncq_align_diff(strat, all_s)
    mu4, t4 = ncq_hac(d4)
    p4 = ncq_p_onesided(t4)
    note4 = (f"공통 {len(d4)}개월 · 전이벤트 팔 월평균 "
             f"{ncq_f(all_s.mean() if len(all_s) else np.nan, 'pctp')}"
             if len(d4) >= NCQ_MIN_MONTHS else
             ("전 이벤트 팔 실행 실패 — 판정불가" if bt_all is None
              else f"공통 {len(d4)}개월 — 표본 부족으로 판정불가"))
    rows.append(["P4", "z상위 − 전이벤트 EW 스프레드 > 0 (텍스트 증분)", mu4, t4, p4, note4])
    detail["P4"] = {"months": int(len(d4)), "mu": mu4, "t": t4, "p": p4,
                    "arm_ok": bt_all is not None}

    # ── BH-FDR (P1~P4 전체) ───────────────────────────────────────────────────────────────
    pv = np.array([r[4] for r in rows], dtype="float64")
    try:
        fdr_pass = bh_fdr(pv, q=NCQ_FDR_Q)
    except Exception:
        fdr_pass = np.zeros(len(pv), dtype=bool)
    p_bh = ncq_bh_adjusted(pv)

    tbl = pd.DataFrame({
        "id": [r[0] for r in rows],
        "hypothesis": [r[1] for r in rows],
        "stat": [float(r[2]) if r[2] is not None else np.nan for r in rows],
        "t": [float(r[3]) if r[3] is not None else np.nan for r in rows],
        "p": pv,
        "p_bh": p_bh,
        "pass": [(None if not np.isfinite(pv[i]) else bool(fdr_pass[i])) for i in range(len(rows))],
    })
    tbl["note"] = [r[5] for r in rows]

    LOG.table(
        [[tbl.at[i, "id"], _trunc(tbl.at[i, "hypothesis"], 42),
          ncq_f(tbl.at[i, "stat"], "pctp"), ncq_f(tbl.at[i, "t"], "t"),
          ncq_f(tbl.at[i, "p"], "p"), ncq_f(tbl.at[i, "p_bh"], "p"),
          ncq_mark(tbl.at[i, "pass"]), _trunc(tbl.at[i, "note"], 44)] for i in tbl.index],
        ["ID", "가설", "월평균", "HAC t", "p(단측)", "p(BH)", "FDR 판정", "비고"],
        ["c", "l", "r", "r", "r", "r", "c", "l"], maxw=46,
        title=f"사전등록 가설 검정 (BH-FDR α={NCQ_FDR_Q:.2f}, P1~P4 동시 보정)")

    for i in tbl.index:
        rid = tbl.at[i, "id"]
        ncq_record(rid, tbl.at[i, "hypothesis"], tbl.at[i, "pass"],
                   f"월평균 {ncq_f(tbl.at[i,'stat'],'pctp')} · HAC t={ncq_f(tbl.at[i,'t'],'t')} · "
                   f"p={ncq_f(tbl.at[i,'p'],'p')} → BH p={ncq_f(tbl.at[i,'p_bh'],'p')}. "
                   f"{tbl.at[i,'note']}",
                   kill=False,
                   metrics={"mu": float(tbl.at[i, "stat"]), "t": float(tbl.at[i, "t"]),
                            "p": float(tbl.at[i, "p"]), "p_bh": float(tbl.at[i, "p_bh"])})

    # ── 채택 조건 3종 (§11.1) ─────────────────────────────────────────────────────────────
    # 조건 ①  P1·P3 BH-FDR 동시 통과
    def _verdict_of(hid):
        """행 순서에 의존하지 않고 id 로 판정을 꺼낸다. None(판정불가)을 False 로 뭉개지 않는다."""
        sel = tbl.loc[tbl["id"] == hid, "pass"]
        if len(sel) == 0:
            return None
        v = sel.iloc[0]
        return None if v is None else bool(v)

    c1_p1, c1_p3 = _verdict_of("P1"), _verdict_of("P3")
    c1 = None if (c1_p1 is None or c1_p3 is None) else bool(c1_p1 and c1_p3)
    c1_txt = (f"P1 {ncq_mark(c1_p1)} · P3 {ncq_mark(c1_p3)}"
              + (f" ({reason3})" if reason3 else ""))

    # 조건 ②  왕복비용 3.0% 스트레스에서도 초과수익 > 0 (직접 돌린다 — 추정하지 않는다)
    bt_cost = None
    if has_sig:
        bt_cost = ncq_run(run_fn, "ADOPT_cost300bp", S, extra=(pxm, sec, uni_obj, months),
                          cost_roundtrip=NCQ_COST_STRESS)
    ex_c = ncq_align_diff(ncq_month_series(bt_cost), bench)
    mu_c, t_c = ncq_hac(ex_c)
    c2 = None if not np.isfinite(mu_c) else bool(mu_c > 0)
    c2_txt = (f"왕복 {NCQ_COST_STRESS*100:.1f}% 시 월평균 초과 {ncq_f(mu_c,'pctp')} "
              f"(HAC t={ncq_f(t_c,'t')}, {len(ex_c)}개월)" if np.isfinite(mu_c)
              else f"왕복 {NCQ_COST_STRESS*100:.1f}% 시나리오 실행 실패/표본 부족 — 판정불가")
    detail["cost_stress"] = {"cost": NCQ_COST_STRESS, "mu": mu_c, "t": t_c,
                             "months": int(len(ex_c))}

    # 조건 ③  placebo 대비 스프레드 > 0 (P2 의 부호 조건 — 유의성이 아니라 부호를 본다)
    c3 = None if not np.isfinite(mu2) else bool(mu2 > 0)
    c3_txt = (f"placebo 대비 월평균 스프레드 {ncq_f(mu2,'pctp')} (HAC t={ncq_f(t2,'t')})"
              if np.isfinite(mu2) else "placebo 팔 부재 — 판정불가")

    # ★ '검정해서 떨어진 것'과 '검정 자체를 못 한 것'을 구분한다.
    #   하나라도 명시적 False → 채택 실패(킬 게이트 발동 대상).
    #   False 는 없는데 판정불가가 섞임 → passed=None. 데이터가 없어서 결론을 못 냈을 뿐인데
    #   킬 기준으로 파이프라인을 끊으면, 정작 원인(구조적 리스크 표)을 못 보게 된다.
    conds = [c1, c2, c3]
    if any(ncq_is_fail(c) for c in conds):
        adopt_verdict = False
    elif any(c is None for c in conds):
        adopt_verdict = None
    else:
        adopt_verdict = True
    adopt = ncq_is_pass(adopt_verdict)           # 채택은 세 조건이 '모두 명시적 통과'일 때만
    LOG.table(
        [["①", "P1·P3 BH-FDR 동시 통과", ncq_mark(c1), _trunc(c1_txt, 60)],
         ["②", f"왕복비용 {NCQ_COST_STRESS*100:.1f}% 에서도 초과수익 > 0", ncq_mark(c2),
          _trunc(c2_txt, 60)],
         ["③", "placebo(하위 tercile) 대비 스프레드 > 0", ncq_mark(c3), _trunc(c3_txt, 60)],
         ["=", "최종 채택 여부",
          ("✔ 채택" if adopt else ("✘ 미채택" if ncq_is_fail(adopt_verdict) else "— 판정불가")),
          "세 조건이 모두 명시적으로 충족돼야 채택한다"]],
        ["", "조건 (§11.1)", "판정", "관측"], ["c", "l", "c", "l"], maxw=62,
        title="사전등록 채택 기준 — 하나라도 미충족이면 채택하지 않는다")

    detail["conditions"] = {"c1_fdr_p1_p3": c1, "c2_cost300bp": c2, "c3_placebo_spread": c3}
    out = {"table": tbl, "adopt": adopt, "detail": detail}
    NCQ_PREREG_RESULT = out               # ★ 킬 게이트로 예외가 올라가도 근거는 남긴다

    if ncq_is_fail(adopt_verdict):
        LOG.banner("⛔ 사전등록 채택 기준 미충족",
                   "파라미터를 바꿔 통과시키지 마십시오 — 미채택도 결론입니다(§16.3)")
    elif adopt_verdict is None:
        LOG.warn("사전등록 채택 여부를 판정할 수 없습니다(입력·표본 부족). "
                 "'판정불가'는 '통과'가 아니며, 이 상태의 성과 수치를 근거로 삼으면 안 됩니다.")
    ncq_record("ADOPT", "사전등록 채택 기준 (§11.1)", adopt_verdict,
               f"① {ncq_mark(c1)} / ② {ncq_mark(c2)} / ③ {ncq_mark(c3)}. "
               f"{c1_txt} | {c2_txt} | {c3_txt}",
               kill=True,
               metrics={"c1": c1, "c2": c2, "c3": c3, "adopt": adopt,
                        "mu_cost300bp": mu_c, "mu_placebo_spread": mu2})
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  3. §11.2 통계 스위트 — 부트스트랩 / 순열 / 워크포워드 / PBO / DSR / Holm
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_block_bootstrap(x, block: int = None, n_iter: int = None, seed=None):
    """원형(circular) 블록 부트스트랩. 반환 (경험적 p(평균≤0), 부트평균 배열, 실제평균).

    자기상관이 있는 월별 초과수익에 iid 부트스트랩을 쓰면 p 값이 과소평가된다.
    12개월 오버랩 보유 구조상 블록 12개월이 자연스러운 선택이다.
    """
    # 0/음수가 들어오면 math.ceil(n/b) 에서 ZeroDivisionError, 빈 재표집에서 nan 경고가 난다.
    b = max(1, int(NCQ_BOOT_BLOCK if block is None else block))
    n_it = max(1, int(NCQ_BOOT_ITER if n_iter is None else n_iter))
    arr = np.asarray(pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(), dtype="float64")
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < max(NCQ_MIN_MONTHS, b):
        return (float("nan"), np.array([], dtype="float64"), float("nan"))
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    nb = int(math.ceil(n / b))
    starts = rng.integers(0, n, size=(n_it, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]) % n          # 원형 wrap
    idx = idx.reshape(n_it, nb * b)[:, :n]
    means = arr[idx].mean(axis=1)
    return (float((means <= 0.0).mean()), means, float(arr.mean()))


def ncq_permutation_spread(SIG, n_iter: int = None, pool_df=None,
                           sel_col: str = "selected", seed=None):
    """월별 fwd_ret 기반 '근사 스프레드'의 순열 검정. 반환 dict.

    ★ 근사임을 숨기지 않는다:
      ① 백테스트(12개월 오버랩 보유)를 1000회 돌릴 수 없으므로, 월별 1개월 fwd_ret 로
         (선택군 평균 − 풀 평균) 스프레드를 계산한다. 절대 수준은 백테스트와 다르다.
      ② 재배치 풀은 pool_df(유니버스×fwd_ret)가 주어지면 유니버스, 없으면 '그 달의 이벤트 풀'.
         후자면 이 검정이 반증하는 것은 "텍스트 z 가 이벤트 중에서 고르는 능력"이지
         "이벤트 발생 자체의 정보"가 아니다.
      ③ 재배치는 '같은 달, 같은 개수'를 유지한다(월별 표본수 차이가 결과를 만들지 않게).
    """
    # n_it 이 0 이면 귀무분포가 빈 배열이 되어 np.quantile 이 예외를 던진다.
    n_it = max(1, int(NCQ_PERM_ITER if n_iter is None else n_iter))
    out = {"real": float("nan"), "p": float("nan"), "q95": float("nan"),
           "n_month": 0, "pool_src": "—", "null": np.array([], dtype="float64")}
    if not isinstance(SIG, pd.DataFrame) or SIG.empty:
        return out
    if not {"month", "fwd_ret"}.issubset(set(SIG.columns)) or sel_col not in SIG.columns:
        return out

    S = SIG[["month", "fwd_ret", sel_col]].copy()
    S["fwd_ret"] = pd.to_numeric(S["fwd_ret"], errors="coerce")
    S["_sel"] = ncq_boolmask(S[sel_col]).to_numpy()

    use_uni = (isinstance(pool_df, pd.DataFrame) and not pool_df.empty
               and {"month", "fwd_ret"}.issubset(set(pool_df.columns)))
    if use_uni:
        P = pool_df[["month", "fwd_ret"]].copy()
        P["fwd_ret"] = pd.to_numeric(P["fwd_ret"], errors="coerce")
        out["pool_src"] = "유니버스(pool_df 제공)"
    else:
        P = S[["month", "fwd_ret"]].copy()
        out["pool_src"] = "그 달의 이벤트 풀 (유니버스 수익 미제공)"

    pools = {m: g["fwd_ret"].dropna().to_numpy(dtype="float64")
             for m, g in P.groupby("month", observed=True)}
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    real_acc: List[float] = []
    null_acc = np.zeros(n_it, dtype="float64")
    used = 0
    for m, g in S.groupby("month", observed=True):
        sel = g.loc[g["_sel"] & g["fwd_ret"].notna(), "fwd_ret"].to_numpy(dtype="float64")
        k = len(sel)
        pool = pools.get(m, np.array([], dtype="float64"))
        if k < 1 or len(pool) < k + 5:            # 풀이 선택군과 사실상 같으면 재배치가 무의미
            continue
        pm = float(pool.mean())
        real_acc.append(float(sel.mean()) - pm)
        r = rng.random((n_it, len(pool)))
        idx = np.argpartition(r, k - 1, axis=1)[:, :k]
        null_acc += pool[idx].mean(axis=1) - pm
        used += 1
    if used == 0:
        return out
    null = null_acc / float(used)
    real = float(np.mean(real_acc))
    out.update({"real": real, "null": null, "n_month": used,
                "p": float((null >= real).mean()),
                "q95": float(np.quantile(null, 0.95))})
    return out


def ncq_walk_forward(ex: pd.Series, is_m: int = None, oos_m: int = None, step_m: int = None):
    """롤링 워크포워드. 반환 (행 리스트, 요약 dict).

    ★ 이 전략에는 최적화할 파라미터가 없다(렉시콘·tercile·보유기간 모두 사전등록 동결).
      따라서 IS 구간은 '학습'이 아니라 **관측만** 하고, OOS 성과를 그대로 보고한다.
      없는 최적화를 있는 척하지 않기 위해 이 사실을 표 제목과 로그에 명시한다.
    """
    # ★ step 이 0/음수면 while 루프가 영원히 돌면서 파이프라인이 멈춘 것처럼 보인다. 반드시 ≥1.
    I = max(1, int(NCQ_WF_IS_M if is_m is None else is_m))
    O = max(1, int(NCQ_WF_OOS_M if oos_m is None else oos_m))
    T_ = max(1, int(NCQ_WF_STEP_M if step_m is None else step_m))
    e = pd.to_numeric(pd.Series(ex), errors="coerce").dropna().sort_index()
    n = len(e)
    rows: List[dict] = []
    if n < I + O:
        return (rows, {"n_win": 0, "reason": f"{n}개월 — IS {I} + OOS {O} 개월에 못 미침"})
    s = I
    while s + O <= n:
        is_x = e.iloc[s - I:s].to_numpy(dtype="float64")
        oo = e.iloc[s:s + O]
        oo_x = oo.to_numpy(dtype="float64")
        # OOS 가 12개월뿐이라 lag=12 는 자유도를 다 먹는다. 표본에 맞춰 lag 를 줄인다(n//4).
        lag = max(1, min(NCQ_HAC_LAG, len(oo_x) // 4))
        mu_o, t_o = ncq_hac(oo_x, lags=lag)
        rows.append({
            "구간": f"{pd.Timestamp(oo.index[0]).strftime('%Y-%m')}~"
                    f"{pd.Timestamp(oo.index[-1]).strftime('%Y-%m')}",
            "IS월수": int(len(is_x)),
            # 전부 NaN 인 구간에서 np.nanmean 은 경고를 뿜는다 — 유한값만 남기고 없으면 NaN.
            "IS월평균": (float(is_x[np.isfinite(is_x)].mean())
                        if np.isfinite(is_x).any() else float("nan")),
            "OOS월수": int(len(oo_x)), "OOS월평균": mu_o, "OOS_t": t_o,
            "OOS누적": ncq_cum_return(oo),
        })
        s += T_
    pos = sum(1 for r in rows if np.isfinite(r["OOS월평균"]) and r["OOS월평균"] > 0)
    allo = np.array([r["OOS월평균"] for r in rows], dtype="float64")
    allo = allo[np.isfinite(allo)]
    summ = {"n_win": len(rows), "n_pos": pos,
            "mu_all": float(allo.mean()) if len(allo) else float("nan"),
            "hac_lag": max(1, min(NCQ_HAC_LAG, O // 4))}
    return (rows, summ)


def ncq_pbo_cscv(M, S: int = None, max_combos: int = None, seed=None):
    """CSCV 기반 PBO. 반환 (pbo, n_combos, approx, note).

    성과 벡터가 2개 이상(민감도 조합 곡선)이면 정식 CSCV:
      IS 에서 최고인 조합을 고르고, 그 조합의 OOS 상대순위 로짓이 ≤0 인 비율이 PBO.
    벡터가 1개뿐이면 '전략 선택' 자체가 없으므로 정식 CSCV 가 성립하지 않는다.
      이때는 시계열 분할 근사(IS 평균>0 인데 OOS 평균≤0 인 비율)를 쓰고 approx=True 로 표시한다.
    """
    import itertools
    s_n = int(NCQ_CSCV_S if S is None else S)
    cap = int(NCQ_CSCV_MAX_COMBOS if max_combos is None else max_combos)
    if not isinstance(M, pd.DataFrame) or M.empty:
        return (float("nan"), 0, True, "성과 행렬이 비어 계산 불가")
    A = M.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    A = A.dropna(axis=1, how="all")
    if A.empty:
        return (float("nan"), 0, True, "유효 성과 벡터 없음")
    X = A.to_numpy(dtype="float64")
    T, N = X.shape
    if s_n % 2 == 1:                       # 짝수 분할이어야 IS/OOS 를 반씩 나눌 수 있다
        s_n -= 1
    if s_n < 2:                            # ★ 0 이면 np.array_split 이 ValueError 를 던진다
        return (float("nan"), 0, True, f"분할 수 S={s_n} — 2 미만이라 CSCV 불가")
    if T < s_n * 3:
        return (float("nan"), 0, True, f"관측 {T}개월 < 분할 {s_n}×3 — 분할 불가")
    blocks = np.array_split(np.arange(T), s_n)
    combos = list(itertools.combinations(range(s_n), s_n // 2))
    n_total = len(combos)
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    sampled = False
    if n_total > cap:
        pick = rng.choice(n_total, size=cap, replace=False)
        combos = [combos[i] for i in sorted(pick.tolist())]
        sampled = True
    # 표본추출 사실을 반드시 남긴다 — 전수 계산인 척하면 PBO 의 신뢰구간을 오해하게 된다.
    note = (f"C({s_n},{s_n//2})={n_total:,} 조합 중 {len(combos):,}개를 무작위 표본추출"
            if sampled else f"C({s_n},{s_n//2})={n_total:,} 조합 전수")

    def _sr(a: np.ndarray) -> np.ndarray:
        mu = np.nanmean(a, axis=0)
        sd = np.nanstd(a, axis=0, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = np.where(sd > 0, mu / np.where(sd > 0, sd, np.nan), np.nan)
        return np.where(np.isfinite(v), v, -np.inf)

    losses = 0
    valid = 0
    approx = (N < 2)
    for cb in combos:
        is_idx = np.concatenate([blocks[j] for j in cb])
        oos_idx = np.concatenate([blocks[j] for j in range(s_n) if j not in cb])
        if len(is_idx) < 6 or len(oos_idx) < 6:
            continue
        Xi, Xo = X[is_idx, :], X[oos_idx, :]
        if approx:
            mi, mo = float(np.nanmean(Xi)), float(np.nanmean(Xo))
            if not (np.isfinite(mi) and np.isfinite(mo)):
                continue
            valid += 1
            losses += int(mi > 0 and mo <= 0)
            continue
        sr_i, sr_o = _sr(Xi), _sr(Xo)
        if not np.isfinite(sr_i).any():
            continue
        best = int(np.argmax(sr_i))
        # 동점은 argsort 로 임의 해소된다(순위 자체가 아니라 분포의 위치만 쓰므로 영향 미미).
        rank = int(np.argsort(np.argsort(sr_o))[best]) + 1
        w = rank / float(N + 1)
        w = min(max(w, 1e-9), 1 - 1e-9)
        valid += 1
        losses += int(math.log(w / (1.0 - w)) <= 0.0)
    if valid == 0:
        return (float("nan"), 0, approx, note + " · 유효 분할 없음")
    return (losses / float(valid), valid, approx, note)


def ncq_dsr(sharpe, n: int, skew, kurt, n_trials: int) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado).

    n_trials 는 **실제 실행한 파라미터 조합 수**여야 한다. 작게 적으면 DSR 이 부풀려진다 —
    이 프로젝트에서는 민감도 실행 수(기본 9)를 그대로 넣는다.
    sharpe 는 월별(비연율) Sharpe.
    """
    try:
        sr = float(sharpe)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(sr) or n is None or int(n) < NCQ_MIN_MONTHS:
        return float("nan")
    n = int(n)
    N = max(int(n_trials), 2)
    e = 0.5772156649015329
    sr0 = (math.sqrt(2.0 * math.log(N)) * (1.0 - e) +
           e * math.sqrt(2.0 * math.log(N * math.e))) / math.sqrt(n)
    sk = float(skew) if (skew is not None and np.isfinite(skew)) else 0.0
    ku = float(kurt) if (kurt is not None and np.isfinite(kurt)) else 3.0
    denom = math.sqrt(max(1e-12, 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2))
    return ncq_norm_cdf((sr - sr0) * math.sqrt(max(n - 1, 1)) / denom)


def run_stat_suite(BT, bench_ew, SIG, months, run_fn, n_trials: int = 9,
                   perf_matrix: Optional[pd.DataFrame] = None,
                   sens: Optional[pd.DataFrame] = None,
                   pool_df: Optional[pd.DataFrame] = None) -> dict:
    """§11.2 통계 스위트. 각 검정을 ncq_record 로 기록하고 dict 로도 반환한다.

    perf_matrix : 행=월, 열=성과벡터(민감도 조합) 인 수익 행렬. 없으면 NCQ_SENS_CURVES 를 쓰고,
                  그것도 없으면 단일 시계열 분할 '근사'로 PBO 를 계산하고 근사임을 명시한다.
    sens        : run_sensitivity 반환 표(Holm 입력). 없으면 NCQ_SENS_TABLE 을 쓴다.
    pool_df     : 순열 검정 재배치 풀(month,fwd_ret). 없으면 이벤트 풀로 근사한다.
    표본 부족은 예외가 아니라 passed=None + 사유.
    """
    LOG.banner("통계 스위트 (§11.2)",
               "블록부트스트랩 · 순열 · 워크포워드 · PBO(CSCV) · DSR · Holm-Bonferroni")
    try:                                   # 호출부가 None/문자열을 넘겨도 DSR 이 죽지 않게
        n_trials = max(1, int(n_trials))
    except (TypeError, ValueError):
        LOG.warn(f"n_trials={n_trials!r} 를 정수로 읽을 수 없어 기본값 9 를 씁니다.")
        n_trials = 9
    bench = ncq_month_series(bench_ew)
    strat = ncq_month_series(BT)
    ex = ncq_align_diff(strat, bench)
    out: Dict[str, Any] = {"n_month": int(len(ex))}

    # ── S1. 블록 부트스트랩 ───────────────────────────────────────────────────────────────
    p_b, boots, real_mu = ncq_block_bootstrap(ex)
    if not np.isfinite(p_b):
        ncq_record("S1", f"블록 부트스트랩 (블록 {NCQ_BOOT_BLOCK}개월 × {NCQ_BOOT_ITER:,}회)", None,
                   f"초과수익 표본 {len(ex)}개월 — 블록 {NCQ_BOOT_BLOCK}개월/최소 "
                   f"{NCQ_MIN_MONTHS}개월 요건에 미달하여 판정불가")
    else:
        ncq_record("S1", f"블록 부트스트랩 (블록 {NCQ_BOOT_BLOCK}개월 × {NCQ_BOOT_ITER:,}회)",
                   bool(p_b < 0.05),
                   f"실제 월평균 초과 {ncq_f(real_mu,'pctp')} · 재표집 평균 "
                   f"{ncq_f(float(np.mean(boots)),'pctp')} · 경험적 p(평균≤0)={ncq_f(p_b,'p')} "
                   f"({len(ex)}개월). " +
                   ("자기상관을 보정해도 평균이 0보다 큽니다."
                    if p_b < 0.05 else
                    "★ 자기상관 보정 재표집에서 평균>0 이 유의하지 않습니다."),
                   metrics={"p": p_b, "mu": real_mu, "n": int(len(ex))})
    out["bootstrap"] = {"p": p_b, "mu": real_mu, "n": int(len(ex))}

    # ── S2. 순열 검정 ─────────────────────────────────────────────────────────────────────
    LOG.info("순열 검정은 계산량을 줄이기 위해 백테스트 대신 **월별 fwd_ret 기반 근사 스프레드**"
             "(선택군 평균 − 풀 평균)를 사용합니다. 절대 수준은 백테스트 수치와 다릅니다.")
    perm = ncq_permutation_spread(SIG, n_iter=NCQ_PERM_ITER, pool_df=pool_df)
    LOG.info(f"순열 재배치 풀 = {perm['pool_src']} · '같은 달, 같은 개수' 유지 · "
             f"유효 {perm['n_month']}개월")
    if not np.isfinite(perm["real"]) or perm["n_month"] < NCQ_MIN_MONTHS:
        ncq_record("S2", f"순열 검정 (월내 재배치 {NCQ_PERM_ITER:,}회)", None,
                   f"유효 {perm['n_month']}개월 — 재배치 가능한 월이 부족하여 판정불가 "
                   f"(풀: {perm['pool_src']})")
    else:
        passed = bool(perm["real"] > perm["q95"])
        ncq_record("S2", f"순열 검정 (월내 재배치 {NCQ_PERM_ITER:,}회)", passed,
                   f"실제 근사 스프레드 {ncq_f(perm['real'],'pctp')} vs 귀무 95%ile "
                   f"{ncq_f(perm['q95'],'pctp')} (p={ncq_f(perm['p'],'p')}, "
                   f"{perm['n_month']}개월, 풀={perm['pool_src']}). " +
                   ("무작위 선택과 구분됩니다." if passed else
                    "★ 무작위 선택과 통계적으로 구분되지 않습니다 — 텍스트 z 의 선별력 근거가 약합니다."),
                   metrics={"real": perm["real"], "q95": perm["q95"], "p": perm["p"],
                            "n_month": perm["n_month"]})
    out["permutation"] = {k: perm[k] for k in ("real", "p", "q95", "n_month", "pool_src")}

    # ── S3. 워크포워드 ────────────────────────────────────────────────────────────────────
    wf_rows, wf_sum = ncq_walk_forward(ex)
    LOG.info("워크포워드 주의 — 이 전략에는 최적화되는 파라미터가 없습니다(렉시콘·tercile·보유기간 "
             "모두 사전등록 동결). 따라서 IS 는 '관측만' 하고 OOS 성과를 그대로 보고합니다. "
             "없는 최적화를 있는 척하지 않습니다.")
    if wf_rows:
        LOG.table([[r["구간"], f"{r['IS월수']}", ncq_f(r["IS월평균"], "pctp"),
                    f"{r['OOS월수']}", ncq_f(r["OOS월평균"], "pctp"), ncq_f(r["OOS_t"], "t"),
                    ncq_f(r["OOS누적"], "pct")] for r in wf_rows],
                  ["OOS 구간", "IS월", "IS월평균(참고)", "OOS월", "OOS월평균", "OOS HAC t", "OOS누적"],
                  ["l", "r", "r", "r", "r", "r", "r"],
                  title=f"워크포워드 — IS {NCQ_WF_IS_M//12}년 관측 / OOS 롤링 {NCQ_WF_OOS_M//12}년 "
                        f"({NCQ_WF_STEP_M//12}년 스텝, OOS HAC lag={wf_sum.get('hac_lag','—')})")
        passed = bool(wf_sum["n_pos"] * 2 > wf_sum["n_win"] and
                      np.isfinite(wf_sum["mu_all"]) and wf_sum["mu_all"] > 0)
        ncq_record("S3", "워크포워드 (OOS 롤링)", passed,
                   f"OOS 구간 {wf_sum['n_win']}개 중 {wf_sum['n_pos']}개가 양(+) · "
                   f"전 OOS 월평균 {ncq_f(wf_sum['mu_all'],'pctp')}. " +
                   ("OOS 에서 성과가 과반 구간 유지됩니다." if passed else
                    "★ OOS 구간 과반에서 초과수익이 유지되지 않습니다."),
                   metrics=wf_sum)
    else:
        ncq_record("S3", "워크포워드 (OOS 롤링)", None,
                   f"판정불가 — {wf_sum.get('reason','표본 부족')}")
    out["walk_forward"] = {"rows": wf_rows, "summary": wf_sum}

    # ── S4. PBO (CSCV) ────────────────────────────────────────────────────────────────────
    M = perf_matrix
    src_note = "호출부가 제공한 성과 행렬"
    if not isinstance(M, pd.DataFrame) or M.empty:
        if NCQ_SENS_CURVES:
            M = pd.DataFrame(dict(NCQ_SENS_CURVES)).sort_index()
            src_note = f"민감도 {M.shape[1]}조합 곡선(NCQ_SENS_CURVES)"
        else:
            M = ex.to_frame("base") if len(ex) else pd.DataFrame()
            src_note = "단일 전략 시계열 — 정식 CSCV 불가"
    pbo, n_cb, approx, cb_note = ncq_pbo_cscv(M, S=NCQ_CSCV_S, max_combos=NCQ_CSCV_MAX_COMBOS)
    LOG.info(f"PBO 입력 = {src_note} · {cb_note}" + (" · ★근사 경로" if approx else ""))
    if not np.isfinite(pbo):
        ncq_record("S4", f"PBO (CSCV, S={NCQ_CSCV_S})", None,
                   f"판정불가 — {cb_note} ({src_note})")
    else:
        ncq_record("S4", f"PBO (CSCV, S={NCQ_CSCV_S})", bool(pbo < 0.5),
                   f"PBO={ncq_f(pbo)} (<0.5 권장) · 유효 분할 {n_cb:,} · 입력: {src_note}"
                   + ("  ★성과 벡터가 1개뿐이라 정식 CSCV 대신 시계열 분할 **근사**입니다 — "
                      "이 값은 '조합 선택 과적합'이 아니라 '구간 불안정성'을 잰 것입니다."
                      if approx else "") + ". "
                   + ("과적합 위험이 낮습니다." if pbo < 0.5 else
                      "★ 과적합 위험이 낮지 않습니다."),
                   metrics={"pbo": pbo, "n_combos": n_cb, "approx": approx, "source": src_note})
    out["pbo"] = {"pbo": pbo, "n_combos": n_cb, "approx": approx, "source": src_note,
                  "note": cb_note}

    # ── S5. DSR ───────────────────────────────────────────────────────────────────────────
    r = pd.to_numeric(pd.Series(strat), errors="coerce").dropna().to_numpy(dtype="float64")
    if len(r) < NCQ_MIN_MONTHS:
        ncq_record("S5", f"DSR (Deflated Sharpe, 시행 {int(n_trials)}회)", None,
                   f"월수 {len(r)} — {NCQ_MIN_MONTHS}개월 미만이라 판정불가")
        dsr = float("nan")
        sr_m = float("nan")
    else:
        sd = float(r.std(ddof=1))
        sr_m = float(r.mean() / sd) if sd > 0 else float("nan")
        sk, ku = ncq_moments(r)
        dsr = ncq_dsr(sr_m, len(r), sk, ku, int(n_trials))
        ncq_record("S5", f"DSR (Deflated Sharpe, 시행 {int(n_trials)}회)",
                   (None if not np.isfinite(dsr) else bool(dsr > 0.95)),
                   f"월Sharpe {ncq_f(sr_m)} (왜도 {ncq_f(sk)}, 첨도 {ncq_f(ku)}) · "
                   f"DSR={ncq_f(dsr)} (>0.95 권장) · 시행횟수는 실제 실행한 민감도 조합 수 "
                   f"{int(n_trials)} 를 그대로 넣었습니다(작게 적으면 DSR 이 부풀려집니다). " +
                   ("" if not np.isfinite(dsr) else
                    ("다중시행을 감안해도 Sharpe 가 유의합니다." if dsr > 0.95 else
                     "★ 다중시행 보정 후 Sharpe 의 유의성이 남지 않습니다.")),
                   metrics={"dsr": dsr, "sharpe_m": sr_m, "n_trials": int(n_trials)})
    out["dsr"] = {"dsr": dsr, "sharpe_m": sr_m, "n_trials": int(n_trials)}

    # ── S6. Holm-Bonferroni (민감도 스윕) ─────────────────────────────────────────────────
    T = sens if isinstance(sens, pd.DataFrame) else NCQ_SENS_TABLE
    if not isinstance(T, pd.DataFrame) or T.empty or "HAC t" not in T.columns:
        ncq_record("S6", "Holm-Bonferroni (민감도 스윕 다중검정)", None,
                   "판정불가 — 민감도 표가 아직 없습니다(run_sensitivity 를 먼저 실행하세요).")
        out["holm"] = {"n": 0}
    else:
        tv = pd.to_numeric(T["HAC t"], errors="coerce").to_numpy(dtype="float64")
        pv = np.array([ncq_p_onesided(x) for x in tv], dtype="float64")
        rej = ncq_holm(pv, NCQ_HOLM_ALPHA)
        labels = (T["combo"].astype(str).tolist() if "combo" in T.columns
                  else [f"C{i}" for i in range(len(T))])
        axis = (T["축"].astype(str).tolist() if "축" in T.columns else ["—"] * len(T))
        val = (T["값"].astype(str).tolist() if "값" in T.columns else ["—"] * len(T))
        LOG.table([[labels[i], axis[i], val[i], ncq_f(tv[i], "t"), ncq_f(pv[i], "p"),
                    ("✔ 기각" if rej[i] else ("—" if not np.isfinite(pv[i]) else "✘ 미기각"))]
                   for i in range(len(T))],
                  ["조합", "축", "값", "HAC t", "p(단측)", f"Holm α={NCQ_HOLM_ALPHA:.2f}"],
                  ["l", "l", "r", "r", "r", "c"],
                  title="Holm-Bonferroni — 민감도 조합 전체에 대한 다중검정 보정")
        n_ok = int(rej.sum())
        n_val = int(np.isfinite(pv).sum())
        ncq_record("S6", "Holm-Bonferroni (민감도 스윕 다중검정)",
                   (None if n_val == 0 else bool(n_ok > 0)),
                   (f"유효 {n_val}조합 중 {n_ok}개가 Holm(α={NCQ_HOLM_ALPHA:.2f}) 하에서 기각. "
                    + ("가장 보수적인 보정에서도 살아남는 조합이 있습니다." if n_ok > 0 else
                       "★ Holm 보정 후 살아남는 조합이 하나도 없습니다 — 민감도 전반이 약합니다."))
                   if n_val else "유효한 t 통계량이 없어 판정불가",
                   metrics={"n_reject": n_ok, "n_valid": n_val})
        out["holm"] = {"n": n_val, "n_reject": n_ok,
                       "p": pv.tolist(), "reject": rej.tolist()}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  4. §15-5 민감도 — 81조합 전수 금지. 기본값 1 + 각 축 단독 변동 8 = 9조합
# ══════════════════════════════════════════════════════════════════════════════════════════

def run_sensitivity(ctx, months, build_sig_fn, run_fn) -> pd.DataFrame:
    """민감도 9조합. 축을 동시에 흔들지 않는다(§15-5: 81조합 전수 금지).

    축: ADV(NCQ_SENS_ADV) / tercile(NCQ_SENS_TOPPCT) / 보유기간(NCQ_SENS_HOLD) / 비용(NCQ_SENS_COST)
    기본값과 같은 값은 건너뛰어 정확히 9조합(= 1 + 2×4)이 되게 한다.

    ★ 재계산 최소화: ADV·tercile 축은 **신호를 다시 만들어야 하고**, 보유기간·비용 축은
      **백테스트만 다시 돌리면 된다.** (top_pct, min_adv) 를 키로 SIG 를 캐시하고,
      ctx 에 본선 SIG 가 있으면 기본 조합의 신호 생성은 아예 건너뛴다.

    반환: DataFrame[combo,축,값,월수,월평균초과,HAC t,Sharpe,누적,판정]
          (수치 컬럼은 float 로 유지 — Holm 이 'HAC t' 를 그대로 읽는다.
           실제 실행 수는 df.attrs 와 로그에 남긴다.)
    """
    global NCQ_SENS_TABLE
    LOG.banner("민감도 검사 (§15-5)",
               "기본값 1조합 + 각 축 단독 변동 8조합 = 9조합 · 축 동시 변동(81조합)은 금지")

    base = {"adv": float(ncq_cfg("NCQ_MIN_ADV", 100_000_000)),
            "top": float(ncq_cfg("NCQ_TERCILE", 1.0 / 3.0)),
            "hold": int(ncq_cfg("NCQ_HOLD_MONTHS", 12)),
            "cost": float(ncq_cfg("NCQ_COST_ROUNDTRIP", 0.018))}
    axes = [("ADV", "adv", list(ncq_cfg("NCQ_SENS_ADV", [base["adv"]])),
             lambda v: f"{float(v)/1e8:.1f}억원"),
            ("tercile", "top", list(ncq_cfg("NCQ_SENS_TOPPCT", [base["top"]])),
             lambda v: f"상위 {float(v)*100:.1f}%"),
            ("보유기간", "hold", list(ncq_cfg("NCQ_SENS_HOLD", [base["hold"]])),
             lambda v: f"{int(v)}개월"),
            ("비용", "cost", list(ncq_cfg("NCQ_SENS_COST", [base["cost"]])),
             lambda v: f"왕복 {float(v)*100:.1f}%")]

    plans: List[Tuple[str, str, str, dict]] = [("C0", "기본값", "—", dict(base))]
    for ax_name, key, vals, fmt in axes:
        for v in vals:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if abs(fv - float(base[key])) <= 1e-12:      # 기본값과 같은 값은 건너뛴다
                continue
            p = dict(base)
            p[key] = int(round(fv)) if key == "hold" else fv
            plans.append((f"C{len(plans)}", ax_name, fmt(fv), p))
    if len(plans) != 9:
        LOG.warn(f"민감도 조합이 {len(plans)}개입니다(설계값 9). NCQ_SENS_* 목록에 기본값이 "
                 f"포함되어 있는지 확인하세요 — 개수를 억지로 맞추지 않고 실제 값을 그대로 씁니다.")

    bench = ncq_month_series(ncq_ctx_get(ctx, "bench_ew"))
    if len(bench) == 0:
        LOG.warn("ctx 에 bench_ew 가 없습니다 — '월평균초과'는 벤치마크 차감 없는 절대수익입니다. "
                 "표의 의미가 달라지므로 그대로 표기합니다.")

    # run_fn 이 (SIG, pxm, sec, uni_obj, months) 를 직접 받는 형태여도 돌아가게 위치인자를 준비.
    bt_extra = (ncq_ctx_get(ctx, "pxm"), ncq_ctx_get(ctx, "sec"),
                ncq_ctx_get(ctx, "uni_obj"), months)

    sig_cache: Dict[Tuple[float, float], Any] = {}
    SIG0 = ncq_ctx_get(ctx, "SIG")
    if isinstance(SIG0, pd.DataFrame) and not SIG0.empty:
        sig_cache[(round(base["top"], 8), float(base["adv"]))] = SIG0
        LOG.info("기본 조합의 신호는 ctx 의 본선 SIG 를 재사용합니다(신호 재생성 1회 절약).")

    NCQ_SENS_CURVES.clear()
    recs: List[dict] = []
    n_sig = 0
    n_bt = 0
    for i, (cid, ax_name, val_txt, p) in enumerate(plans):
        key = (round(float(p["top"]), 8), float(p["adv"]))
        SIGp = sig_cache.get(key)
        if SIGp is None:
            if build_sig_fn is None:
                LOG.error(f"[{cid}] build_sig_fn 이 주입되지 않아 신호를 만들 수 없습니다 — 건너뜁니다.")
                recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                             "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                             "Sharpe": np.nan, "누적": np.nan, "판정": "— 실행불가(신호 콜백 없음)"})
                continue
            try:
                SIGp = build_sig_fn(top_pct=p["top"], min_adv=p["adv"])
                n_sig += 1
            except Exception as e:                                    # noqa
                LOG.error(f"[{cid}] 신호 생성 실패 — {type(e).__name__}: {e}")
                recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                             "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                             "Sharpe": np.nan, "누적": np.nan,
                             "판정": f"— 신호 생성 실패({type(e).__name__})"})
                continue
            sig_cache[key] = SIGp
        if not isinstance(SIGp, pd.DataFrame) or SIGp.empty:
            LOG.warn(f"[{cid}] 신호 패널이 비어 백테스트를 돌리지 않습니다 — 판정불가로 남깁니다.")
            recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                         "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                         "Sharpe": np.nan, "누적": np.nan, "판정": "— 신호 패널 비어 있음"})
            continue
        BTp = ncq_run(run_fn, cid, SIGp, extra=bt_extra,
                      hold_months=p["hold"], cost_roundtrip=p["cost"])
        n_bt += 1
        if BTp is None:
            recs.append({"combo": cid, "축": ax_name, "값": val_txt,
                         "실행": f"{n_bt}/{len(plans)}", "월수": 0, "월평균초과": np.nan,
                         "HAC t": np.nan, "Sharpe": np.nan, "누적": np.nan,
                         "판정": "— 백테스트 실패"})
            continue
        rs = ncq_month_series(BTp)
        exc = ncq_align_diff(rs, bench) if len(bench) else rs
        mu, t = ncq_hac(exc)
        NCQ_SENS_CURVES[cid] = exc
        if not np.isfinite(mu):
            verdict = f"— 판정불가({len(exc)}개월)"
        elif mu <= 0:
            verdict = "✘ 소멸"
        elif np.isfinite(t) and t >= 1.65:
            verdict = "✔ 유지"
        else:
            verdict = "△ 약함(t<1.65)"
        recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"{n_bt}/{len(plans)}",
                     "월수": int(len(exc)), "월평균초과": mu, "HAC t": t,
                     "Sharpe": ncq_sharpe(BTp), "누적": ncq_cum_return(rs), "판정": verdict})

    df = pd.DataFrame(recs, columns=["combo", "축", "값", "실행", "월수", "월평균초과",
                                     "HAC t", "Sharpe", "누적", "판정"])
    df.attrs["n_sig_builds"] = n_sig
    df.attrs["n_bt_runs"] = n_bt
    df.attrs["n_plans"] = len(plans)

    LOG.table([[r["combo"], r["축"], r["값"], r["실행"], f"{int(r['월수']):,}",
                ncq_f(r["월평균초과"], "pctp"), ncq_f(r["HAC t"], "t"),
                ncq_f(r["Sharpe"]), ncq_f(r["누적"], "pct"), r["판정"]]
               for _, r in df.iterrows()],
              ["조합", "축", "값", "실행", "월수", "월평균초과", "HAC t", "Sharpe", "누적", "판정"],
              ["l", "l", "r", "c", "r", "r", "r", "r", "r", "l"], maxw=24,
              title=f"민감도 9조합 — 실제 실행: 신호 재생성 {n_sig}회 · 백테스트 {n_bt}회 "
                    f"(계획 {len(plans)}조합)")
    LOG.info(f"민감도 실행 회계 — 계획 {len(plans)}조합 / 신호 재생성 {n_sig}회 / 백테스트 {n_bt}회. "
             f"ADV·tercile 축만 신호를 다시 만들고, 보유기간·비용 축은 백테스트만 다시 돌립니다.")

    ok = int((pd.to_numeric(df["월평균초과"], errors="coerce") > 0).sum())
    val = int(pd.to_numeric(df["월평균초과"], errors="coerce").notna().sum())
    ncq_record("S7", "민감도 9조합 (§15-5)",
               (None if val == 0 else bool(ok * 2 > val)),
               (f"유효 {val}조합 중 {ok}개에서 월평균 초과수익 > 0 "
                f"(신호 재생성 {n_sig}회 · 백테스트 {n_bt}회). "
                + ("과반 조합에서 부호가 유지됩니다." if ok * 2 > val else
                   "★ 과반 조합에서 초과수익 부호가 유지되지 않습니다 — 특정 설정에만 의존합니다."))
               if val else "실행 가능한 조합이 없어 판정불가",
               metrics={"n_plans": len(plans), "n_sig": n_sig, "n_bt": n_bt,
                        "n_pos": ok, "n_valid": val})
    NCQ_SENS_TABLE = df
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════
#  5. 요약 리포트 + §12 구조적 리스크 R1~R6
# ══════════════════════════════════════════════════════════════════════════════════════════

def report_robustness() -> None:
    """NCQ_ROBUST 전체를 표로 요약한다. 킬 게이트는 ⭐. 실패는 그대로 남긴다."""
    LOG.banner("ARC-NCQ 강건성 검사 요약 (§11)",
               "킬 게이트는 ⭐ 표시 · 실패와 판정불가는 그대로 보고한다")
    if not NCQ_ROBUST:
        LOG.warn("기록된 강건성 검사가 없습니다 — 이 계층이 실행되지 않았습니다.")
        return
    rows = []
    for r in NCQ_ROBUST.values():
        rows.append([r["id"] + ("⭐" if r["kill"] else ""), _trunc(r["name"], 34),
                     ncq_mark(r["pass"]), _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)

    fails = [r for r in NCQ_ROBUST.values() if ncq_is_fail(r["pass"])]
    unk = [r for r in NCQ_ROBUST.values() if r["pass"] is None]
    kills = [r for r in fails if r["kill"]]
    LOG.info(f"집계 — 통과 {sum(1 for r in NCQ_ROBUST.values() if ncq_is_pass(r['pass']))}건 · "
             f"실패 {len(fails)}건 · 판정불가 {len(unk)}건 (총 {len(NCQ_ROBUST)}건)")
    if unk:
        LOG.warn("판정불가 " + ", ".join(r["id"] for r in unk) +
                 " — '통과'가 아닙니다. 표본이나 입력이 모자라 결론을 낼 수 없었다는 뜻입니다.")
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§15 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("기록된 강건성 검사에서 실패가 없습니다(판정불가 항목은 위를 참고하세요).")


def ncq_right_tail_share(BT):
    """(상위5% 기여비중, 상위5% 제외 후 총기여). 보유이력이 없으면 (nan, nan).

    이 전략은 정보비율이 아니라 소수 종목의 우측 꼬리에 의존할 가능성이 크다(§12 R6).
    그 사실을 감추지 않기 위해 항상 같이 보고한다.
    """
    H = BT.get("holdings") if isinstance(BT, dict) else None
    if not isinstance(H, pd.DataFrame) or H.empty or not {"code", "weight", "ret"} <= set(H.columns):
        return (float("nan"), float("nan"))
    w = pd.to_numeric(H["weight"], errors="coerce")
    r = pd.to_numeric(H["ret"], errors="coerce")
    contrib = (w * r).groupby(H["code"].astype(str)).sum().sort_values(ascending=False)
    contrib = contrib[np.isfinite(contrib.to_numpy(dtype="float64"))]
    n = len(contrib)
    if n == 0:
        return (float("nan"), float("nan"))
    total = float(contrib.sum())
    k = max(1, int(round(n * 0.05)))
    top = float(contrib.iloc[:k].sum())
    share = (top / total) if abs(total) > 1e-12 else float("nan")
    return (share, total - top)


def report_structural_risks(ctx) -> None:
    """§12 구조적 리스크 R1~R6 을 **이번 실행에서 실제 관측된 수치**와 함께 출력한다.

    가정이나 설계 의도가 아니라 관측치를 적는다. 관측할 수 없었던 항목은 "—" 로 두고
    '측정하지 못함'이라고 쓴다 — 측정하지 않은 것을 안전하다고 쓰지 않는다.
    ctx 는 dict/객체 모두 허용하며, 없는 키는 조용히 "—" 가 된다.
    """
    LOG.banner("구조적 리스크 R1~R6 (§12)",
               "설계상의 위험이 이번 실행에서 실제로 얼마나 실현됐는가")

    REP = ncq_ctx_get(ctx, "REP")
    EV = ncq_ctx_get(ctx, "EV")
    TXT = ncq_ctx_get(ctx, "TXT")
    BT = ncq_ctx_get(ctx, "BT")
    diag = ncq_ctx_get(ctx, "diag")
    months = ncq_ctx_get(ctx, "months")
    n_months = 0
    try:
        n_months = int(len(months)) if months is not None else 0
    except Exception:
        n_months = 0

    min_total = int(ncq_cfg("NCQ_MIN_TOTAL_EVENTS", 800))
    min_per_m = float(ncq_cfg("NCQ_MIN_EVENTS_PER_MONTH", 5))

    # R1 — 아카이브 결손 구간 수 (리포트 인덱스가 비어 있는 달)
    n_gap = float("nan")
    if isinstance(diag, pd.DataFrame) and not diag.empty:
        cnt_col = next((c for c in ("n_reports", "n", "건수", "reports", "cnt")
                        if c in diag.columns), None)
        if cnt_col is not None:
            v = pd.to_numeric(diag[cnt_col], errors="coerce")
            n_gap = float((v.fillna(0) <= 0).sum())
    elif isinstance(REP, pd.DataFrame) and not REP.empty and "pub_date" in REP.columns and n_months:
        mm = pd.to_datetime(REP["pub_date"], errors="coerce").dt.to_period("M").nunique()
        n_gap = float(max(0, n_months - int(mm)))

    # R2 — IRS 단일 소스 의존도
    irs_share = float("nan")
    if isinstance(REP, pd.DataFrame) and not REP.empty and "source" in REP.columns:
        src = REP["source"].astype(str).str.lower()
        if len(src) > 0:
            irs_share = float(src.str.contains("irs").mean())

    # R3 — 표본 규모
    n_ev = float(len(EV)) if isinstance(EV, pd.DataFrame) else float("nan")
    ev_per_m = (n_ev / n_months) if (np.isfinite(n_ev) and n_months > 0) else float("nan")

    # R4 — 종목 매핑 실패율 (stock_code 를 붙이지 못한 리포트 비중)
    map_fail = float("nan")
    if isinstance(REP, pd.DataFrame) and not REP.empty and "stock_code" in REP.columns:
        sc = REP["stock_code"].astype(str).str.strip()
        bad = sc.isin(["", "none", "None", "nan", "NaN", "<NA>"]) | REP["stock_code"].isna()
        map_fail = float(bad.mean())

    # R5 — PDF 텍스트 추출 실패율
    pdf_fail = float("nan")
    if isinstance(TXT, pd.DataFrame) and not TXT.empty and "extract_ok" in TXT.columns:
        okm = ncq_boolmask(TXT["extract_ok"])
        if len(okm) > 0:
            pdf_fail = float(1.0 - okm.mean())

    # R6 — 우측 꼬리 의존도
    tail_share, tail_ex = ncq_right_tail_share(BT)

    def _verdict(val, limit, worse_is_high=True, fmt="pct0"):
        if val is None or not np.isfinite(val):
            return ("—", "측정하지 못함")
        bad = (val > limit) if worse_is_high else (val < limit)
        return (("❗ 기준 초과" if bad else "✔ 기준 내"), ncq_f(val, fmt))

    v2, s2 = _verdict(irs_share, 0.70, True, "pct0")
    v3a = ("❗ 미달" if (np.isfinite(n_ev) and n_ev < min_total)
           else ("✔ 충족" if np.isfinite(n_ev) else "—"))
    v3b = ("❗ 미달" if (np.isfinite(ev_per_m) and ev_per_m < min_per_m)
           else ("✔ 충족" if np.isfinite(ev_per_m) else "—"))
    v4, s4 = _verdict(map_fail, 0.10, True, "pct0")

    rows = [
        ["R1", "아카이브 결손 — 리포트 인덱스가 비는 구간",
         (ncq_f(n_gap, "int") + "개월") if np.isfinite(n_gap) else "—",
         "0개월 권장", ("✔ 없음" if (np.isfinite(n_gap) and n_gap == 0)
                      else ("❗ 존재" if np.isfinite(n_gap) else "—")),
         "결손 구간은 커버리지 '신규' 판정을 거짓 양성으로 만든다"],
        ["R2", "IRS 단일 소스 의존", s2, "≤ 70%", v2,
         "IRS 만으로 커버리지를 판정하면 소스 정책 변화가 곧 신호가 된다"],
        ["R3", "총 이벤트 표본", ncq_f(n_ev, "int") + ("건" if np.isfinite(n_ev) else ""),
         f"≥ {min_total:,}건", v3a, "표본이 모자라면 이후 모든 t 통계량이 무의미"],
        ["R3b", "월평균 이벤트", ncq_f(ev_per_m) + ("건/월" if np.isfinite(ev_per_m) else ""),
         f"≥ {min_per_m:.0f}건/월", v3b, "월별 포트폴리오가 소수 종목에 쏠린다"],
        ["R4", "종목코드 매핑 실패율", s4, "≤ 10%", v4,
         "매핑 실패는 무작위가 아니라 소형·신규 종목에 몰린다(선택편향)"],
        ["R5", "PDF 본문 추출 실패율",
         ncq_f(pdf_fail, "pct0"), "낮을수록 좋음(하드 기준 없음)",
         ("—" if not np.isfinite(pdf_fail) else ("❗ 30% 초과" if pdf_fail > 0.30 else "✔ 양호")),
         "추출 실패분은 텍스트 점수가 결측 — 0 으로 채우지 않는다"],
        ["R6", "우측 꼬리 의존 (상위5% 종목 기여비중)",
         ncq_f(tail_share, "pct0"), "참고치(제외 후 총기여 > 0)",
         ("—" if not np.isfinite(tail_share)
          else ("❗ 꼬리 의존" if (np.isfinite(tail_ex) and tail_ex <= 0) else "✔ 분산")),
         f"상위5% 제외 후 총기여 {ncq_f(tail_ex)}"],
    ]
    LOG.table(rows, ["ID", "구조적 리스크", "관측치", "기준", "판정", "왜 위험한가"],
              ["c", "l", "r", "l", "c", "l"], maxw=52)

    # ── 기준 초과 경고 (수치를 그대로 말한다) ─────────────────────────────────────────────
    if np.isfinite(irs_share) and irs_share > 0.70:
        LOG.warn(f"R2 — 리포트의 {irs_share*100:.1f}% 가 IRS 단일 소스입니다(기준 70%). "
                 f"이 상태에서 '신규 커버리지'는 기업 사건이 아니라 소스 수록 정책의 변화를 "
                 f"반영할 수 있습니다. 소스별 하위표본 성과를 반드시 함께 보십시오.")
    if np.isfinite(n_ev) and n_ev < min_total:
        LOG.warn(f"R3 — 총 이벤트가 {int(n_ev):,}건으로 최소 요건 {min_total:,}건에 미달합니다. "
                 f"검정력이 부족하므로 위 모든 t 통계량과 p 값을 그만큼 할인해서 읽어야 합니다.")
    if np.isfinite(ev_per_m) and ev_per_m < min_per_m:
        LOG.warn(f"R3b — 월평균 이벤트가 {ev_per_m:.2f}건으로 최소 {min_per_m:.0f}건에 미달합니다. "
                 f"월별 포트폴리오가 1~2종목에 좌우되어 성과가 사실상 개별 종목 베팅이 됩니다.")
    if np.isfinite(map_fail) and map_fail > 0.10:
        LOG.warn(f"R4 — 종목코드 매핑 실패율이 {map_fail*100:.1f}% 로 기준 10% 를 넘습니다. "
                 f"실패는 무작위가 아니라 소형·신규 상장에 몰리므로 유니버스가 조용히 왜곡됩니다.")
    if np.isfinite(tail_ex) and tail_ex <= 0 and np.isfinite(tail_share):
        LOG.warn(f"R6 — 상위 5% 종목을 제외하면 총기여가 {ncq_f(tail_ex)} 로 0 이하가 됩니다. "
                 f"성과가 소수 종목에 전적으로 의존하므로, 실전에서 그 종목을 놓치면 전략 전체가 "
                 f"실패합니다. 사이징과 기대치를 여기에 맞추십시오.")

    ncq_record("R12", "구조적 리스크 R1~R6 관측 (§12)", None,
               f"IRS 비중 {ncq_f(irs_share,'pct0')} · 총이벤트 {ncq_f(n_ev,'int')} · "
               f"월평균 {ncq_f(ev_per_m)} · 매핑실패 {ncq_f(map_fail,'pct0')} · "
               f"PDF실패 {ncq_f(pdf_fail,'pct0')} · 결손 {ncq_f(n_gap,'int')}개월 · "
               f"상위5% 기여 {ncq_f(tail_share,'pct0')}  (판정이 아니라 관측 기록입니다)",
               kill=False,
               metrics={"irs_share": irs_share, "n_events": n_ev, "ev_per_month": ev_per_m,
                        "map_fail": map_fail, "pdf_fail": pdf_fail, "archive_gap_m": n_gap,
                        "tail_top5_share": tail_share, "tail_ex_total": tail_ex})
