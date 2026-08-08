

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  SCG 코어 — 명세 §5~§29 의 산식을 그대로 구현한다.                                     ║
# ║                                                                                          ║
# ║   analyst_forecast → Accuracy + Leadership → Shrinkage → Recency×Quality                  ║
# ║        → SmartConsensus → SmartGap → (+GapAcceleration)                                  ║
# ║                                                                                          ║
# ║  이 파일에는 네트워크·드라이브·전역상태가 없다. 순수 함수만 있다.                            ║
# ║  그래서 §35 의 TEST 1~9 를 합성데이터로 완전히 검정할 수 있다.                              ║
# ║                                                                                          ║
# ║  ★ 설계 원칙 3가지 (명세 §49)                                                             ║
# ║    1. 하드게이트를 넣지 않는다. 유일하게 허용된 게이트는 MIN_ANALYSTS=2 뿐이다.              ║
# ║    2. 이력이 없는 애널리스트를 탈락시키지 않는다. 중립값(0)으로 수축시킨다.                   ║
# ║    3. 모든 ACC*/LEAD* 는 signal date 마다 PIT 롤링 계산한다. 전체기간 점수 금지.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


@dataclass(frozen=True)
class SCGConfig:
    """§42 공식 V1 파라미터. 코드 어디에도 magic number 를 두지 않는다.

    frozen=True 인 이유: 강건성 검사(§41)가 `replace(SCG, FORECAST_HALFLIFE_DAYS=30)` 로
    변형본을 만들어 돌리는데, 가변 객체였다면 그 변형이 공식 설정에 새어 들어간다.
    민감도 표를 뽑다가 공식 파라미터가 바뀌는 사고를 타입으로 막는다.
    """
    # ── 표본 유지 ────────────────────────────────────────────────────────────────────
    MIN_ANALYSTS: int = 2                     # 유일하게 허용된 하드게이트 (§6.2)
    MAX_FORECAST_AGE_DAYS: int = 180          # stale 제거용. 알파 게이트가 아니다 (§6.1)

    # ── 최근성 ──────────────────────────────────────────────────────────────────────
    FORECAST_HALFLIFE_DAYS: float = 45.0      # §19

    # ── 애널리스트 이력 ──────────────────────────────────────────────────────────────
    ANALYST_HISTORY_YEARS: float = 5.0        # §9
    ACCURACY_HISTORY_HALFLIFE_DAYS: float = 365.0
    LEAD_HISTORY_HALFLIFE_DAYS: float = 365.0
    K_ACC: float = 6.0                        # §10 수축계수
    K_LEAD: float = 6.0                       # §17
    ACC_PRIOR: float = 0.0
    LEAD_PRIOR: float = 0.0

    # ── 정보력 종합 ─────────────────────────────────────────────────────────────────
    ACC_WEIGHT: float = 0.60                  # §18
    LEAD_WEIGHT: float = 0.40
    QUALITY_EXP_SCALE: float = 0.70           # §20
    QUALITY_MULTIPLIER_MIN: float = 0.50
    QUALITY_MULTIPLIER_MAX: float = 2.00

    # ── 이벤트 ──────────────────────────────────────────────────────────────────────
    LEAD_FORWARD_TRADING_DAYS: int = 20       # §13 — calendar day 가 아니라 거래일
    ACCEL_LOOKBACK_TRADING_DAYS: int = 20     # §25
    ACC_EVENT_CLIP: float = 2.0               # §8
    LEAD_EVENT_CLIP: float = 1.0              # §14
    #   Accuracy 계산에 쓸 전망의 최대 나이. §6.1 과 같은 'stale 제거' 목적이며
    #   알파 게이트가 아니다. 3년 묵은 전망을 실적과 비교하는 것을 막기 위한 위생 규칙.
    ACC_FORECAST_MAX_AGE_DAYS: int = 180

    # ── 갭 / 알파 ───────────────────────────────────────────────────────────────────
    SCG_LEVEL_WEIGHT: float = 0.75            # §28
    SCG_ACCEL_WEIGHT: float = 0.25
    NEUTRAL_ACCEL_RANK: float = 0.50          # §28 — accel 결측 시 중립 처리
    DENOM_FLOOR_RATIO: float = 0.10           # §24
    EPSILON: float = 1e-8
    WINSOR_LOWER: float = 0.01
    WINSOR_UPPER: float = 0.99
    MIN_CROSS_SECTION_FOR_WINSOR: int = 30


SCG = SCGConfig()

#  analyst_forecasts 표준 스키마 (§2.1). 이 컬럼 이름은 협상 대상이 아니다.
FORECAST_KEY = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric"]
FORECAST_COLS = FORECAST_KEY + ["broker_id", "report_id", "report_date", "forecast_value"]
GROUP_KEY = ["stock_id", "fiscal_period", "forecast_metric"]      # §5 분석 단위
#  같은 종목이라도 FY1 과 FQ1 은 절대 섞이지 않는다 — 그 보장이 이 튜플 하나에 걸려 있다.

STATUS_OK = "OK"
STATUS_INSUFFICIENT = "INSUFFICIENT_ANALYSTS"


# ══════════════════════════════════════════════════════════════════════════════════════
#  0. 공통 원시연산
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_halflife_weight(age_days, halflife: float) -> np.ndarray:
    """2^(-age/H). age 는 일수(float). 음수 age(미래)는 호출부에서 이미 걸러져야 한다."""
    a = np.asarray(age_days, dtype="float64")
    return np.exp2(-a / float(halflife))


def _scg_ns(s) -> pd.Series:
    """datetime 시리즈를 반드시 나노초 해상도로 통일한다.

    ★ pandas 2.x 는 입력에 따라 datetime64[us]/[s]/[ms] 를 그대로 유지한다.
      그 상태로 merge_asof 를 부르면
        MergeError: incompatible merge keys ... dtype('<M8[ns]') and dtype('<M8[us]')
      가 난다. 조인 키가 되는 모든 날짜는 여기를 통과시킨다.
    """
    return pd.to_datetime(as_ts_series(s), errors="coerce").astype("datetime64[ns]")


def _scg_trading_calendar(cal) -> np.ndarray:
    """거래일 캘린더를 정렬된 datetime64[ns] 배열로 정규화한다."""
    if cal is None:
        return np.array([], dtype="datetime64[ns]")
    if isinstance(cal, pd.DataFrame):
        c = cal
        if "is_trading_day" in c.columns:
            c = c[c["is_trading_day"].astype(bool)]
        s = as_ts_series(c["date"])
    elif isinstance(cal, pd.Series):
        s = as_ts_series(cal)
    else:
        s = pd.Series(pd.DatetimeIndex(cal))
    s = s.dropna().drop_duplicates().sort_values()
    return s.values.astype("datetime64[ns]")


def _scg_shift_td(dates, k: int, cal: np.ndarray) -> np.ndarray:
    """각 날짜에서 거래일 k 세션 뒤(양수)/앞(음수)의 날짜. 범위를 벗어나면 NaT.

    앵커 규칙: t 가 거래일이 아니면 't 이상인 첫 거래일'을 0번 세션으로 본다.
    (§13 의 "20 trading days" 는 calendar day 가 아니다 — 여기가 그 유일한 구현 지점이다)
    """
    d = np.asarray(pd.DatetimeIndex(as_ts_series(pd.Series(dates))).values, dtype="datetime64[ns]")
    out = np.full(d.shape, np.datetime64("NaT"), dtype="datetime64[ns]")
    if cal.size == 0:
        return out
    pos = np.searchsorted(cal, d, side="left")          # t 이상인 첫 거래일의 위치
    tgt = pos + int(k)
    ok = (~pd.isna(d)) & (tgt >= 0) & (tgt < cal.size) & (pos < cal.size)
    out[ok] = cal[tgt[ok]]
    return out


_SCG_DAY0 = np.datetime64("1900-01-01", "D")     # 일자 인코딩 원점 (음수 방지)
_SCG_DAY_K = 200_000                             # gid 당 일자 슬롯 (2447년까지 안전)


def _scg_key(gid: np.ndarray, t: np.ndarray, shift_days: int = 0) -> np.ndarray:
    """(gid, 날짜) → 단조증가 int64 키. gid 블록 경계와 시간 순서를 한 축에 접는다.

    이렇게 접어 두면 '어느 gid 안에서 어느 시간 구간' 이라는 2차원 탐색이
    np.searchsorted 한 번으로 끝난다 — 질의마다 파이썬 루프를 돌 필요가 없다.
    day 는 1900-01-01 기준이라 항상 양수이므로 shift 를 빼도 옆 gid 로 새지 않는다.
    """
    day = (t.astype("datetime64[D]") - _SCG_DAY0).astype("int64")
    day = np.clip(day + int(shift_days), 0, _SCG_DAY_K - 1)
    return gid.astype("int64") * _SCG_DAY_K + day


def _scg_stab(iv_gid: np.ndarray, iv_start: np.ndarray, iv_end: np.ndarray,
              q_gid: np.ndarray, q_time: np.ndarray, max_span_days: int,
              chunk: int = 400_000) -> Tuple[np.ndarray, np.ndarray]:
    """구간 스태빙(interval stabbing): 질의점 (gid, t) 를 덮는 모든 구간을 찾는다.

    반환: (질의 인덱스, 구간 인덱스) 쌍의 배열 — "질의 q 를 구간 i 가 덮는다".

    ★ 이 함수 하나가 이 전략의 두 군데를 동시에 책임진다.
        · signal date 별 active forecast 선정 (§6)
        · Leadership 의 t0/t20 시점 peer 집합 (§13) — leave-one-out 의 모집단
      두 곳에서 '활성 전망 집합'의 정의가 미세하게 달라지면 §35 TEST 7 이 잡아내지
      못하는 조용한 불일치가 생긴다. 그래서 정의를 한 곳에만 둔다.

    ★ 성능의 핵심 두 가지
      1) 구간의 최대 길이가 max_span_days 로 유한하다 → start < t - span 인 구간은
         볼 필요조차 없다(end <= start+span < t). 후보가 질의당 수십 개로 묶인다.
      2) (gid, day) 를 int64 키 하나로 접는다 → 이진탐색이 완전 벡터화된다.
         (질의 60만 건에서 파이썬 루프 대비 수십 배 차이가 난다)
    """
    n_q = q_gid.size
    empty = (np.empty(0, dtype="int64"), np.empty(0, dtype="int64"))
    if n_q == 0 or iv_gid.size == 0:
        return empty

    iv_key = _scg_key(iv_gid, iv_start)
    order = np.argsort(iv_key, kind="stable")
    s_key = iv_key[order]
    s_end = iv_end[order]
    s_start = iv_start[order]

    qi_parts: List[np.ndarray] = []
    ii_parts: List[np.ndarray] = []
    for c0 in range(0, n_q, chunk):
        c1 = min(c0 + chunk, n_q)
        g, t = q_gid[c0:c1], q_time[c0:c1]
        # start ∈ [t - span, t] 인 구간만 후보 (양끝 모두 포함)
        lo = np.searchsorted(s_key, _scg_key(g, t, -int(max_span_days)), side="left")
        hi = np.searchsorted(s_key, _scg_key(g, t, 0) + 1, side="left")
        cnt = np.maximum(hi - lo, 0)
        tot = int(cnt.sum())
        if tot == 0:
            continue
        qi = np.repeat(np.arange(c0, c1, dtype="int64"), cnt)
        base = np.repeat(np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt)
        ii = np.repeat(lo, cnt) + (np.arange(tot, dtype="int64") - base)
        #  후보 선별은 '일' 단위로 했으므로, 최종 판정은 ns 정밀도로 다시 한다.
        #  (지금은 모든 시각이 자정이라 동일하지만, 장중 타임스탬프를 넘기는 호출자가
        #   생겼을 때 조용히 start > t 인 구간을 끌어들이는 것을 막는다)
        keep = (s_end[ii] >= q_time[qi]) & (s_start[ii] <= q_time[qi])
        if keep.any():
            qi_parts.append(qi[keep])
            ii_parts.append(order[ii[keep]])             # 원래 인덱스로 되돌린다

    if not qi_parts:
        return empty
    return (np.concatenate(qi_parts), np.concatenate(ii_parts))


def _scg_validity(f: pd.DataFrame, cfg: SCGConfig) -> pd.DataFrame:
    """각 전망의 '유효 구간' [start, end] 을 만든다 — §2.1 의 1인 1표 규칙의 구현.

    start = report_date
    end   = min( 같은 애널리스트의 다음 전망 직전,  report_date + MAX_FORECAST_AGE_DAYS )

    이렇게 구간을 미리 확정해 두면 "동일 (종목·애널·기간·메트릭)에서 활성 전망은 최대 1개"가
    자료구조 수준에서 보장된다. 즉 §35 TEST 8 은 사후 검사가 아니라 구성상 참이 된다.
    """
    f = f.sort_values(FORECAST_KEY + ["report_date", "report_id"], kind="mergesort")
    # 같은 키·같은 날짜에 두 건이면 report_id 가 큰(나중) 것만 남긴다 — 실행 간 재현 가능한 규칙
    f = f.drop_duplicates(subset=FORECAST_KEY + ["report_date"], keep="last")
    nxt = f.groupby(FORECAST_KEY, observed=True, sort=False)["report_date"].shift(-1)
    hard_end = f["report_date"] + pd.Timedelta(days=int(cfg.MAX_FORECAST_AGE_DAYS))
    repl_end = nxt - pd.Timedelta(1, "ns")
    f = f.copy()
    f["valid_start"] = f["report_date"]
    f["valid_end"] = np.where(repl_end.notna() & (repl_end < hard_end), repl_end, hard_end)
    f["valid_end"] = pd.to_datetime(f["valid_end"])
    return f


def _scg_price_matrix(px: pd.DataFrame, cal: np.ndarray, value_col: str = "close_adj"
                      ) -> Tuple[np.ndarray, Dict[str, int], np.ndarray]:
    """(거래일 × 종목) 가격 행렬. 이후의 모든 수익률·시가총액 계산이 이 행렬 하나에서 나온다.

    ★ 왜 행렬인가: signal date × 종목 × 여러 지평의 전방수익률을 groupby 로 만들면
      수백만 번의 파이썬 호출이 된다. 행렬 + searchsorted 로 바꾸면 전부 벡터 인덱싱이다.
    ★ 결측 처리: 거래정지 등으로 비는 날은 직전가로 채운다(ffill). 다만 **상장 전**과
      **폐지 후**로는 절대 번지지 않게 한다 — 번지면 없는 종목에 가격이 생겨
      생존자편향의 정반대 방향으로 표본을 오염시킨다.
    """
    if px is None or px.empty or value_col not in px.columns:
        return np.zeros((0, 0)), {}, np.array([], dtype="datetime64[ns]")
    p = px[["code", "date", value_col]].dropna(subset=["code", "date"]).copy()
    p["date"] = as_ts_series(p["date"])
    p = p.dropna(subset=["date"])
    wide = p.pivot_table(index="date", columns="code", values=value_col, aggfunc="last")
    if wide.empty:
        return np.zeros((0, 0)), {}, np.array([], dtype="datetime64[ns]")
    idx = pd.DatetimeIndex(cal) if len(cal) else wide.index
    wide = wide.reindex(idx.union(wide.index)).sort_index().reindex(idx)
    first = wide.notna().cummax()                       # 첫 거래일 이후만 True
    last = wide.notna()[::-1].cummax()[::-1]            # 마지막 거래일 이전만 True
    wide = wide.ffill().where(first & last)
    codes = {c: i for i, c in enumerate(wide.columns)}
    return wide.to_numpy("float64"), codes, wide.index.values.astype("datetime64[ns]")


def _scg_gid(df: pd.DataFrame, cats: Optional[pd.Index] = None
             ) -> Tuple[np.ndarray, pd.Index]:
    """(stock_id, fiscal_period, forecast_metric) → 정수 gid. §5 분석 단위의 유일한 인코딩."""
    key = (df["stock_id"].astype(str) + "\x1f" +
           df["fiscal_period"].astype(str) + "\x1f" +
           df["forecast_metric"].astype(str))
    if cats is None:
        cats = pd.Index(pd.unique(key))
    codes = cats.get_indexer(key.values)
    return codes.astype("int64"), cats


# ══════════════════════════════════════════════════════════════════════════════════════
#  1. Active forecasts (§6) — signal date 별 1인 1표 전망 집합
# ══════════════════════════════════════════════════════════════════════════════════════

def build_active_forecasts(forecasts: pd.DataFrame, signal_dates, cfg: SCGConfig = SCG
                           ) -> pd.DataFrame:
    """§6 — 각 signal date T 에서 유효한 전망만 남긴다.

    규칙: report_date <= T  및  0 <= T - report_date <= MAX_FORECAST_AGE_DAYS,
          동일 (종목·애널·회계기간·메트릭)에서는 가장 최근 1건만.

    ★ PIT: report_date > T 인 전망은 구조적으로 들어올 수 없다(구간 start = report_date).
      report_date 가 미래(수집 시점 기준)인 행은 §32 에 따라 즉시 오류로 처리한다.
    """
    need = set(FORECAST_COLS)
    miss = need - set(forecasts.columns)
    if miss:
        raise KeyError(f"analyst_forecasts 필수 컬럼 누락: {sorted(miss)} "
                       f"(있는 컬럼: {sorted(forecasts.columns)})")

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    n0 = len(f)
    f = f.dropna(subset=["report_date", "forecast_value", "stock_id", "analyst_id"])
    #  §32: forecast 값 NaN → 해당 row 만 제외 (애널리스트를 제거하지 않는다)
    if len(f) < n0:
        LOG.debug(f"전망값/발간일 결측으로 {n0-len(f):,}행 제외 (해당 행만, 애널리스트는 유지)")

    sd = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(signal_dates))).dropna().unique()))
    if len(sd) == 0 or f.empty:
        return pd.DataFrame(columns=["signal_date"] + FORECAST_COLS + ["forecast_age_days"])

    #  §32: report_date 가 마지막 signal date 를 넘어서면 '미래 리포트' — 즉시 오류
    horizon = sd[-1] + pd.Timedelta(days=1)
    future = f["report_date"] > horizon
    if bool(future.any()):
        bad = f.loc[future, ["stock_id", "analyst_id", "report_date"]].head(5)
        raise ValueError(
            f"report_date 가 마지막 signal date({sd[-1].date()}) 이후인 전망이 "
            f"{int(future.sum()):,}건 있습니다 (§32 즉시 오류). 예:\n{bad.to_string(index=False)}")

    v = _scg_validity(f, cfg)
    gid, _ = _scg_gid(v)
    sd_vals = sd.values.astype("datetime64[ns]")

    # 각 전망 구간이 덮는 signal date 들을 한 번에 전개한다 (§6 을 반복문 없이)
    lo = np.searchsorted(sd_vals, v["valid_start"].values.astype("datetime64[ns]"), side="left")
    hi = np.searchsorted(sd_vals, v["valid_end"].values.astype("datetime64[ns]"), side="right")
    cnt = np.maximum(hi - lo, 0)
    total = int(cnt.sum())
    if total == 0:
        return pd.DataFrame(columns=["signal_date"] + FORECAST_COLS + ["forecast_age_days"])

    row = np.repeat(np.arange(len(v), dtype="int64"), cnt)
    off = np.arange(total, dtype="int64") - np.repeat(
        np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt)
    dcol = np.repeat(lo, cnt) + off

    out = pd.DataFrame({
        "signal_date": sd_vals[dcol],
        "stock_id": v["stock_id"].values[row],
        "analyst_id": v["analyst_id"].values[row],
        "broker_id": v["broker_id"].values[row],
        "report_id": v["report_id"].values[row],
        "fiscal_period": v["fiscal_period"].values[row],
        "forecast_metric": v["forecast_metric"].values[row],
        "report_date": v["report_date"].values[row],
        "forecast_value": v["forecast_value"].values[row],
    })
    out["forecast_age_days"] = (out["signal_date"] - out["report_date"]).dt.days.astype("int32")
    #  구성상 보장되지만, 조립 실수를 조용히 넘기지 않기 위해 한 번 더 확인한다
    if bool((out["forecast_age_days"] < 0).any()):
        raise AssertionError("active forecast 에 미래 전망이 섞였습니다 (age < 0) — PIT 위반")
    LOG.debug(f"active forecasts {len(out):,}행 "
              f"({out['signal_date'].nunique()}개 시점 × {out['stock_id'].nunique():,}종목)")
    return out


def compute_equal_consensus(active: pd.DataFrame, cfg: SCGConfig = SCG) -> pd.DataFrame:
    """§6.3 consensus_equal_weight — 단순 산술평균. 비교 기준선이자 SCG 의 분모."""
    if active.empty:
        return pd.DataFrame(columns=["signal_date"] + GROUP_KEY +
                                    ["consensus_equal_weight", "analyst_count", "status"])
    g = active.groupby(["signal_date"] + GROUP_KEY, observed=True, sort=False)
    c = g.agg(consensus_equal_weight=("forecast_value", "mean"),
              analyst_count=("analyst_id", "nunique")).reset_index()
    c["status"] = np.where(c["analyst_count"] >= cfg.MIN_ANALYSTS,
                           STATUS_OK, STATUS_INSUFFICIENT)
    return c


# ══════════════════════════════════════════════════════════════════════════════════════
#  2. Accuracy Event (§7~§8)
# ══════════════════════════════════════════════════════════════════════════════════════

def build_accuracy_events(forecasts: pd.DataFrame, actuals: pd.DataFrame,
                          calendar=None, cfg: SCGConfig = SCG) -> pd.DataFrame:
    """§7~§8 — 각 실적 사건에서 애널리스트가 당시 컨센서스보다 정확했는가.

    ACC_EVENT = clip( log( (NE_C + eps) / (NE_j + eps) ), -2, +2 )
      NE_j = |F_j - A| / Scale,   NE_C = |C - A| / Scale
      Scale = max(|A|, median_j |F_j|, eps)          ← EPS 0 근처 폭발 방지 (§8.1)

    ★ PIT 의 근거는 actual_announcement_date 다. 이 사건은 그 날짜에 '완성'되며,
      §9 는 T 시점에 A_date < T 인 사건만 쓰게 되어 있다. 그 필터는 build_analyst_scores
      에 있고, 여기서는 사건 자체만 만든다.
    ★ §45.3: 공식 V1 의 C 는 자기 자신을 포함한 전체 equal consensus 다.
      leave-one-out 판은 보조 진단(acc_event_loo)으로만 함께 낸다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "actual_announcement_date", "actual_value", "forecast_value",
            "consensus_at_event", "n_analysts", "scale", "ne_analyst", "ne_consensus",
            "acc_event", "acc_event_loo", "report_date", "forecast_age_days"]
    if forecasts is None or forecasts.empty or actuals is None or actuals.empty:
        return pd.DataFrame(columns=cols)

    a = actuals.copy()
    a["actual_announcement_date"] = as_ts_series(a["actual_announcement_date"])
    a["actual_value"] = pd.to_numeric(a["actual_value"], errors="coerce")
    a = a.dropna(subset=["actual_announcement_date", "actual_value"])
    a = a.sort_values("actual_announcement_date").drop_duplicates(
        subset=GROUP_KEY, keep="first")            # 최초 발표만 — 정정공시로 과거를 바꾸지 않는다
    if a.empty:
        return pd.DataFrame(columns=cols)

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    f = f.dropna(subset=["report_date", "forecast_value"])

    m = f.merge(a[GROUP_KEY + ["actual_value", "actual_announcement_date"]],
                on=GROUP_KEY, how="inner")
    if m.empty:
        return pd.DataFrame(columns=cols)

    #  §7 — 실적 발표 '전'에 존재하던 마지막 전망. 발표 당일 전망은 쓰지 않는다(누수).
    age = (m["actual_announcement_date"] - m["report_date"]).dt.days
    m = m[(age > 0) & (age <= int(cfg.ACC_FORECAST_MAX_AGE_DAYS))]
    if m.empty:
        return pd.DataFrame(columns=cols)
    m = m.sort_values(FORECAST_KEY + ["report_date", "report_id"], kind="mergesort")
    m = m.drop_duplicates(subset=FORECAST_KEY, keep="last")     # 애널리스트당 1건 (§2.1)

    g = m.groupby(GROUP_KEY, observed=True, sort=False)["forecast_value"]
    m["n_analysts"] = g.transform("size").astype("int32")
    m["_sum"] = g.transform("sum")
    m["consensus_at_event"] = g.transform("mean")
    m["_median_abs"] = m.groupby(GROUP_KEY, observed=True, sort=False)["forecast_value"] \
                        .transform(lambda s: s.abs().median())

    #  §6.2 와 같은 근거의 유일한 게이트. 1명뿐이면 C == F_j 라 ACC_EVENT 가 항상 0 이고,
    #  그 0 이 n^acc 만 부풀려 λ 를 1 로 밀어올린다(정보 없는 애널이 확신을 얻는 역효과).
    n_pre = len(m)
    m = m[m["n_analysts"] >= cfg.MIN_ANALYSTS]
    if len(m) < n_pre:
        LOG.debug(f"Accuracy: 애널리스트 {cfg.MIN_ANALYSTS}명 미만 사건 {n_pre-len(m):,}건 제외 "
                  f"(§6.2 와 동일 근거. 애널리스트를 제거하는 것이 아니라 사건만 제외)")
    if m.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    A = m["actual_value"].to_numpy("float64")
    F = m["forecast_value"].to_numpy("float64")
    C = m["consensus_at_event"].to_numpy("float64")
    scale = np.maximum.reduce([np.abs(A), m["_median_abs"].to_numpy("float64"),
                               np.full(A.shape, eps)])
    ne_j = np.abs(F - A) / scale
    ne_c = np.abs(C - A) / scale
    m["scale"] = scale
    m["ne_analyst"] = ne_j
    m["ne_consensus"] = ne_c
    m["acc_event"] = np.clip(np.log((ne_c + eps) / (ne_j + eps)),
                             -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)

    #  보조 진단 (§45.3): 자기 자신을 뺀 컨센서스 기준 정확도. 공식 산식은 위쪽이다.
    n = m["n_analysts"].to_numpy("float64")
    c_loo = np.where(n > 1, (m["_sum"].to_numpy("float64") - F) / np.maximum(n - 1, 1), np.nan)
    ne_c_loo = np.abs(c_loo - A) / scale
    m["acc_event_loo"] = np.clip(np.log((ne_c_loo + eps) / (ne_j + eps)),
                                 -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)
    m["forecast_age_days"] = (m["actual_announcement_date"] - m["report_date"]).dt.days.astype("int32")

    out = m[cols].reset_index(drop=True)
    LOG.debug(f"Accuracy 이벤트 {len(out):,}건 "
              f"({out['analyst_id'].nunique():,}명 · 평균 {out['acc_event'].mean():+.3f})")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
#  3. Leadership Event (§11~§16)
# ══════════════════════════════════════════════════════════════════════════════════════

def build_leadership_events(forecasts: pd.DataFrame, calendar, cfg: SCGConfig = SCG
                            ) -> pd.DataFrame:
    """§12~§16 — 내가 전망을 고친 뒤, '나를 뺀' 다른 애널리스트들이 같은 방향으로 따라왔는가.

    LEAD_EVENT = clip( sign(ΔF_j) × ΔC^{-j} / Scale_C , -1, +1 )
      ΔC^{-j} = C^{-j}(t20) - C^{-j}(t0)          ← t20 은 20 '거래일' 후 (§13)
      Scale_C = max( |C^{-j}(t0)|, median|F| at t0, eps )

    ★ leave-one-out 이 이 지표의 전부다 (§13). 자기 전망이 peer consensus 에 남아 있으면
      "내가 올렸으니 컨센서스가 올랐다"는 기계적 자기상관을 측정하게 된다.
      그래서 peer 집합에서 j 를 뺀 근거를 행마다 남긴다(self_in_peer_t0/t20 = False 여야 함).
      §35 TEST 7 은 이 컬럼이 하나라도 True 면 실패시킨다.
    ★ PIT: 이 사건의 '완성 시점'은 t20 이다. §16 에 따라 t20 < T 인 사건만 점수에 쓴다.
      그 필터는 build_analyst_scores 에 있다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "event_date", "outcome_date", "prev_forecast", "new_forecast",
            "revision", "direction", "peer_consensus_t0", "peer_consensus_t20",
            "peer_count_t0", "peer_count_t20", "follow_move", "lead_event",
            "self_in_peer_t0", "self_in_peer_t20"]
    if forecasts is None or forecasts.empty:
        return pd.DataFrame(columns=cols)

    cal = _scg_trading_calendar(calendar)
    if cal.size == 0:
        LOG.warn("거래일 캘린더가 비어 Leadership 이벤트를 만들 수 없습니다 — LEAD* 는 전부 0 "
                 "으로 수축됩니다(애널리스트는 유지). SCG_LS 는 사실상 SCG_0 와 같아집니다.")
        return pd.DataFrame(columns=cols)

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    f = f.dropna(subset=["report_date", "forecast_value"])
    if f.empty:
        return pd.DataFrame(columns=cols)

    v = _scg_validity(f, cfg).reset_index(drop=True)
    gid, cats = _scg_gid(v)
    v["_gid"] = gid

    # ── 리비전 사건: 같은 (종목·애널·기간·메트릭)의 연속된 두 전망 (§12) ──────────────
    v = v.sort_values(FORECAST_KEY + ["report_date"], kind="mergesort").reset_index(drop=True)
    grp = v.groupby(FORECAST_KEY, observed=True, sort=False)["forecast_value"]
    v["prev_forecast"] = grp.shift(1)
    ev = v[v["prev_forecast"].notna()].copy()
    #  §12: 변화가 완전히 0 이면 사건을 만들지 않는다. 크기 하한(5%,10%)은 두지 않는다 —
    #  미세한 리비전은 산식에서 자연스럽게 영향력이 작아진다.
    ev = ev[ev["forecast_value"] != ev["prev_forecast"]]
    if ev.empty:
        return pd.DataFrame(columns=cols)

    ev["event_date"] = ev["report_date"]
    ev["outcome_date"] = _scg_shift_td(ev["event_date"], int(cfg.LEAD_FORWARD_TRADING_DAYS), cal)
    ev = ev[ev["outcome_date"].notna()].copy()          # 캘린더 끝을 넘으면 결과 관측 불가
    if ev.empty:
        return pd.DataFrame(columns=cols)

    # ── t0 / t20 시점의 활성 전망 집합 (§13) ────────────────────────────────────────
    iv_gid = v["_gid"].to_numpy("int64")
    iv_s = v["valid_start"].values.astype("datetime64[ns]")
    iv_e = v["valid_end"].values.astype("datetime64[ns]")
    iv_val = v["forecast_value"].to_numpy("float64")
    iv_ana = v["analyst_id"].astype(str).to_numpy()

    n_ev = len(ev)
    q_gid = np.concatenate([ev["_gid"].to_numpy("int64")] * 2)
    q_time = np.concatenate([ev["event_date"].values.astype("datetime64[ns]"),
                             ev["outcome_date"].values.astype("datetime64[ns]")])
    q_owner = np.concatenate([ev["analyst_id"].astype(str).to_numpy()] * 2)

    qi, ii = _scg_stab(iv_gid, iv_s, iv_e, q_gid, q_time,
                       max_span_days=int(cfg.MAX_FORECAST_AGE_DAYS) + 1)
    if qi.size == 0:
        return pd.DataFrame(columns=cols)

    #  ★ leave-one-out 의 실행 지점: 소유자 j 의 전망을 peer 집합에서 물리적으로 제거한다.
    is_self = (iv_ana[ii] == q_owner[qi])
    peer = ~is_self
    qp, ip = qi[peer], ii[peer]

    n_q = q_gid.size
    peer_cnt = np.bincount(qp, minlength=n_q).astype("float64")
    peer_sum = np.bincount(qp, weights=iv_val[ip], minlength=n_q)
    with np.errstate(invalid="ignore", divide="ignore"):
        peer_mean = np.where(peer_cnt > 0, peer_sum / peer_cnt, np.nan)

    #  Scale_C 의 median|F| (§14) — peer 집합 기준. 정확한 중앙값을 쓴다(평균 대체 금지).
    med_abs = np.full(n_q, np.nan)
    if ip.size:
        dfm = pd.DataFrame({"q": qp, "av": np.abs(iv_val[ip])})
        mm = dfm.groupby("q", sort=True)["av"].median()
        med_abs[mm.index.to_numpy()] = mm.to_numpy()

    #  자기 전망이 정말로 빠졌는지의 증거 (§35 TEST 7 이 읽는 컬럼)
    self_cnt = np.bincount(qi[is_self], minlength=n_q)

    t0s, t20s = slice(0, n_ev), slice(n_ev, 2 * n_ev)
    ev["peer_consensus_t0"] = peer_mean[t0s]
    ev["peer_consensus_t20"] = peer_mean[t20s]
    ev["peer_count_t0"] = peer_cnt[t0s].astype("int32")
    ev["peer_count_t20"] = peer_cnt[t20s].astype("int32")
    ev["self_in_peer_t0"] = False                      # 위에서 물리적으로 제거했으므로 항상 False
    ev["self_in_peer_t20"] = False
    ev["_self_seen_t0"] = self_cnt[t0s]                # 진단용: j 가 그 시점에 활성이었는가
    ev["_self_seen_t20"] = self_cnt[t20s]
    med0 = med_abs[t0s]

    #  §15 — t0/t20 양쪽에서 peer 가 최소 1명. 미충족이면 그 사건만 버린다(애널은 유지).
    n_pre = len(ev)
    ok = (ev["peer_count_t0"] >= 1) & (ev["peer_count_t20"] >= 1) & \
         ev["peer_consensus_t0"].notna() & ev["peer_consensus_t20"].notna()
    med0 = med0[ok.to_numpy()]
    ev = ev[ok].copy()
    if len(ev) < n_pre:
        LOG.debug(f"Leadership: peer 부족(§15)으로 사건 {n_pre-len(ev):,}건 제외 "
                  f"— 애널리스트는 유지됩니다")
    if ev.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    c0 = ev["peer_consensus_t0"].to_numpy("float64")
    c20 = ev["peer_consensus_t20"].to_numpy("float64")
    med0 = np.nan_to_num(med0, nan=0.0)
    scale_c = np.maximum.reduce([np.abs(c0), med0, np.full(c0.shape, eps)])

    fnew = ev["forecast_value"].to_numpy("float64")
    fold = ev["prev_forecast"].to_numpy("float64")
    scale_r = np.maximum.reduce([np.abs(fold), med0, np.full(fold.shape, eps)])

    ev["revision"] = (fnew - fold) / scale_r           # §12 (진단용 — 게이트로 쓰지 않는다)
    ev["direction"] = np.sign(fnew - fold)
    ev["follow_move"] = (c20 - c0) / scale_c
    ev["lead_event"] = np.clip(ev["direction"].to_numpy("float64") * ev["follow_move"].to_numpy("float64"),
                               -cfg.LEAD_EVENT_CLIP, cfg.LEAD_EVENT_CLIP)
    ev["new_forecast"] = fnew

    out = ev[cols].reset_index(drop=True)
    LOG.debug(f"Leadership 이벤트 {len(out):,}건 "
              f"({out['analyst_id'].nunique():,}명 · 평균 {out['lead_event'].mean():+.4f})")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
#  4. 애널리스트 PIT 점수 (§9~§10, §17~§18)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_roll_scores(ev: pd.DataFrame, date_col: str, val_col: str,
                     signal_dates: pd.DatetimeIndex, halflife: float,
                     lookback_years: float, K: float, prior: float,
                     tag: str) -> pd.DataFrame:
    """signal date 마다 '그 시점 이전에 완성된' 사건만으로 시간가중 평균 + 수축을 계산한다.

    ★ 여기가 §45.5(전체기간 점수 금지)의 실행 지점이다. 전 구간 평균을 한 번 구해
      모든 시점에 뿌리는 구현은 미래누수이며, 이 함수는 구조적으로 그것을 할 수 없다:
      사건을 완료일로 정렬해 두고, 각 T 마다 [T-lookback, T) **슬라이스만** 본다.
      슬라이스의 오른쪽 끝이 searchsorted(..., side="left") 이므로 T 당일 사건도 빠진다.

    반환 컬럼: signal_date, analyst_id, {tag}_raw, {tag}_n, {tag}_lambda, {tag}_star
    """
    cols = ["signal_date", "analyst_id", f"{tag}_raw", f"{tag}_n",
            f"{tag}_lambda", f"{tag}_star"]
    if ev is None or ev.empty or len(signal_dates) == 0:
        return pd.DataFrame(columns=cols)
    e = ev[[date_col, val_col, "analyst_id"]].dropna()
    if e.empty:
        return pd.DataFrame(columns=cols)

    e = e.sort_values(date_col, kind="mergesort")
    d = e[date_col].values.astype("datetime64[ns]")
    x = e[val_col].to_numpy("float64")
    acodes, auniq = pd.factorize(e["analyst_id"].astype(str), sort=True)
    n_a = len(auniq)
    day = d.astype("datetime64[D]").astype("int64").astype("float64")
    lb = int(round(365.25 * float(lookback_years)))

    parts: List[pd.DataFrame] = []
    for T in signal_dates:
        lo = int(np.searchsorted(d, np.datetime64(T - pd.Timedelta(days=lb), "ns"), side="left"))
        hi = int(np.searchsorted(d, np.datetime64(T, "ns"), side="left"))   # 엄격히 T 이전
        if hi <= lo:
            continue
        t_day = float(np.datetime64(T, "D").astype("int64"))
        #  w = 2^(-age/H). 슬라이스 안에서만 계산하므로 미래 사건은 존재 자체가 불가능하다.
        w = np.exp2(-(t_day - day[lo:hi]) / float(halflife))
        ac = acodes[lo:hi]
        nn = np.bincount(ac, minlength=n_a)
        act = np.nonzero(nn)[0]
        if act.size == 0:
            continue
        sw = np.bincount(ac, weights=w, minlength=n_a)[act]
        swx = np.bincount(ac, weights=w * x[lo:hi], minlength=n_a)[act]
        n_act = nn[act].astype("float64")
        raw = np.where(sw > 0, swx / np.where(sw > 0, sw, 1.0), 0.0)
        lam = n_act / (n_act + float(K))
        parts.append(pd.DataFrame({
            "signal_date": np.repeat(np.datetime64(T, "ns"), act.size),
            "analyst_id": auniq[act],
            f"{tag}_raw": raw,
            f"{tag}_n": n_act.astype("int32"),
            f"{tag}_lambda": lam,
            f"{tag}_star": lam * raw + (1.0 - lam) * float(prior),
        }))
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat(parts, ignore_index=True)[cols]


def build_analyst_scores(signal_dates, accuracy_events: pd.DataFrame,
                         leadership_events: pd.DataFrame, cfg: SCGConfig = SCG
                         ) -> pd.DataFrame:
    """§9~§10, §17~§18 — signal date 별 ACC*, LEAD*, Q. §33 analyst_score_history 그대로.

    이력이 없는 애널리스트는 여기에 행이 없고, 하류에서 0 으로 채워진다(§32).
    "행이 없다 = 탈락"이 아니라 "행이 없다 = 중립"이다. 이 구분이 이 전략의 전부다.
    """
    cols = ["signal_date", "analyst_id", "acc_raw", "acc_n", "acc_lambda", "acc_star",
            "lead_raw", "lead_n", "lead_lambda", "lead_star", "quality_score_ls",
            "quality_score_scg0"]
    sd = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(signal_dates))).dropna().unique()))
    if len(sd) == 0:
        return pd.DataFrame(columns=cols)

    #  ★ PIT 의 두 근거 날짜가 서로 다르다는 점이 중요하다.
    #     Accuracy   → actual_announcement_date (실적이 발표된 날 사건이 완성된다)
    #     Leadership → outcome_date = t20        (20거래일 뒤 추종 여부가 확정된다)
    acc = _scg_roll_scores(accuracy_events, "actual_announcement_date", "acc_event", sd,
                           cfg.ACCURACY_HISTORY_HALFLIFE_DAYS, cfg.ANALYST_HISTORY_YEARS,
                           cfg.K_ACC, cfg.ACC_PRIOR, tag="acc")
    lead = _scg_roll_scores(leadership_events, "outcome_date", "lead_event", sd,
                            cfg.LEAD_HISTORY_HALFLIFE_DAYS, cfg.ANALYST_HISTORY_YEARS,
                            cfg.K_LEAD, cfg.LEAD_PRIOR, tag="lead")
    if acc.empty and lead.empty:
        return pd.DataFrame(columns=cols)

    #  outer join — Accuracy 만 있거나 Leadership 만 있는 애널리스트도 남긴다 (§32).
    #  없는 쪽은 0 으로 채운다: "이력 없음 = 중립" 이지 "탈락" 이 아니다.
    S = acc.merge(lead, on=["signal_date", "analyst_id"], how="outer")
    for c, v in (("acc_raw", 0.0), ("acc_n", 0), ("acc_lambda", 0.0), ("acc_star", 0.0),
                 ("lead_raw", 0.0), ("lead_n", 0), ("lead_lambda", 0.0), ("lead_star", 0.0)):
        if c not in S.columns:
            S[c] = v
        S[c] = S[c].fillna(v)
    S["quality_score_ls"] = cfg.ACC_WEIGHT * S["acc_star"] + cfg.LEAD_WEIGHT * S["lead_star"]
    S["quality_score_scg0"] = S["acc_star"]              # §21 — Leadership 미사용
    LOG.debug(f"애널리스트 점수 {len(S):,}행 ({S['analyst_id'].nunique():,}명 × {len(sd)}시점)")
    return S[cols]


# ══════════════════════════════════════════════════════════════════════════════════════
#  5. Smart Consensus (§19~§23)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_multiplier(q: np.ndarray, cfg: SCGConfig) -> np.ndarray:
    """§20 — clip(exp(0.7·Q), 0.5, 2.0). 어떤 애널리스트도 weight=0 이 되지 않는다."""
    return np.clip(np.exp(cfg.QUALITY_EXP_SCALE * q),
                   cfg.QUALITY_MULTIPLIER_MIN, cfg.QUALITY_MULTIPLIER_MAX)


def compute_smart_consensus(active_forecasts: pd.DataFrame, analyst_scores: pd.DataFrame,
                            cfg: SCGConfig = SCG) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§19~§23 — Recency × Quality 로 가중한 자체 컨센서스.

    반환: (smart_consensus, analyst_forecast_weights)  ← §33 의 두 산출물 그대로
    """
    wcols = ["signal_date", "stock_id", "fiscal_period", "forecast_metric", "analyst_id",
             "forecast_value", "report_date", "forecast_age_days", "recency_weight",
             "acc_star", "lead_star", "quality_score_scg0", "quality_score_ls",
             "quality_multiplier_scg0", "quality_multiplier_ls", "weight_scg0", "weight_ls"]
    ccols = ["signal_date"] + GROUP_KEY + ["analyst_count", "consensus_equal_weight",
             "smart_consensus_scg0", "smart_consensus_ls", "status"]
    if active_forecasts is None or active_forecasts.empty:
        return pd.DataFrame(columns=ccols), pd.DataFrame(columns=wcols)

    W = active_forecasts.copy()
    if analyst_scores is not None and len(analyst_scores):
        W = W.merge(analyst_scores[["signal_date", "analyst_id", "acc_star", "lead_star"]],
                    on=["signal_date", "analyst_id"], how="left")
    else:
        W["acc_star"] = np.nan
        W["lead_star"] = np.nan
    #  §32 — 이력이 없으면 0. 결측을 '없음'이 아니라 '중립'으로 읽는다. 탈락시키지 않는다.
    W["acc_star"] = W["acc_star"].fillna(0.0)
    W["lead_star"] = W["lead_star"].fillna(0.0)

    W["recency_weight"] = _scg_halflife_weight(W["forecast_age_days"].to_numpy(),
                                               cfg.FORECAST_HALFLIFE_DAYS)
    W["quality_score_scg0"] = W["acc_star"]                                    # §21
    W["quality_score_ls"] = cfg.ACC_WEIGHT * W["acc_star"] + cfg.LEAD_WEIGHT * W["lead_star"]  # §22
    W["quality_multiplier_scg0"] = _scg_multiplier(W["quality_score_scg0"].to_numpy("float64"), cfg)
    W["quality_multiplier_ls"] = _scg_multiplier(W["quality_score_ls"].to_numpy("float64"), cfg)
    W["weight_scg0"] = W["recency_weight"] * W["quality_multiplier_scg0"]
    W["weight_ls"] = W["recency_weight"] * W["quality_multiplier_ls"]

    W["_v0"] = W["weight_scg0"] * W["forecast_value"]
    W["_vls"] = W["weight_ls"] * W["forecast_value"]
    g = W.groupby(["signal_date"] + GROUP_KEY, observed=True, sort=False)
    C = g.agg(analyst_count=("analyst_id", "nunique"),
              consensus_equal_weight=("forecast_value", "mean"),
              _w0=("weight_scg0", "sum"), _wls=("weight_ls", "sum"),
              _v0=("_v0", "sum"), _vls=("_vls", "sum")).reset_index()

    eps = float(cfg.EPSILON)
    C["smart_consensus_scg0"] = C["_v0"] / C["_w0"].where(C["_w0"].abs() > eps)
    C["smart_consensus_ls"] = C["_vls"] / C["_wls"].where(C["_wls"].abs() > eps)
    C["status"] = np.where(C["analyst_count"] >= cfg.MIN_ANALYSTS, STATUS_OK, STATUS_INSUFFICIENT)
    C = C.drop(columns=["_w0", "_wls", "_v0", "_vls"])
    W = W.drop(columns=["_v0", "_vls"])
    return C[ccols], W[wcols]


# ══════════════════════════════════════════════════════════════════════════════════════
#  6. Smart Gap · Acceleration · Rank (§24~§29)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_winsorize(s: pd.Series, lo: float, hi: float, min_n: int) -> pd.Series:
    """§24 — 단면 1%/99% 윈저라이즈. 표본이 작으면 손대지 않는다(작은 단면에서의
    분위수는 극단치 제거가 아니라 그냥 데이터 파괴다)."""
    v = s.dropna()
    if len(v) < min_n:
        return s
    a, b = v.quantile(lo), v.quantile(hi)
    return s.clip(lower=a, upper=b)


def build_scg_signals(smart_consensus: pd.DataFrame, calendar, cfg: SCGConfig = SCG
                      ) -> pd.DataFrame:
    """§24~§29 — SCG, Acceleration, BASE_REV, 단면 rank, 최종 알파.

    ★ 분모 안정화(§24)가 이 전략의 숨은 급소다. EPS 는 0 을 자유롭게 통과하므로
      단순 |C| 분모는 적자↔흑자 전환 종목에서 갭을 무한대로 날려보낸다.
      단면 median|C| 의 10% 를 바닥으로 깔아 그 폭발을 막는다.
    ★ §30: 네 전략(BASE_REV / SCG_0 / SCG_LS / SCG_LSA)은 같은 행에서 나란히 나온다.
      universe 를 전략별로 다르게 만들 여지 자체를 두지 않는다.
    """
    ocols = ["signal_date"] + GROUP_KEY + [
        "analyst_count", "status", "consensus_equal_weight",
        "smart_consensus_scg0", "smart_consensus_ls",
        "denominator", "scg0", "scg_ls", "scg_accel_20d", "base_revision_20d",
        "rank_base_rev", "rank_scg0", "rank_scg_ls", "rank_scg_accel",
        "alpha_ls", "alpha_lsa"]
    if smart_consensus is None or smart_consensus.empty:
        return pd.DataFrame(columns=ocols)

    D = smart_consensus.copy()
    D["signal_date"] = as_ts_series(D["signal_date"])
    #  §6.2 — 2명 미만은 Smart Gap 을 계산하지 않는다. 행은 남기되 값은 NaN 이다
    #  (조용히 사라지면 §35 TEST 9 표본보존 검사가 무의미해진다).
    ok = D["status"].eq(STATUS_OK)
    eps = float(cfg.EPSILON)

    #  단면 floor: 같은 (시점 · 회계기간 · 메트릭) 안에서만 비교한다 (§45.2)
    xs = ["signal_date", "fiscal_period", "forecast_metric"]
    med_abs = (D.loc[ok].assign(_a=D.loc[ok, "consensus_equal_weight"].abs())
                 .groupby(xs, observed=True)["_a"].median().rename("_med_abs"))
    D = D.merge(med_abs, on=xs, how="left")
    floor = cfg.DENOM_FLOOR_RATIO * D["_med_abs"].fillna(0.0)
    D["denominator"] = np.maximum.reduce([
        D["consensus_equal_weight"].abs().to_numpy("float64"),
        floor.to_numpy("float64"), np.full(len(D), eps)])

    D["scg0"] = np.where(ok, (D["smart_consensus_scg0"] - D["consensus_equal_weight"]) / D["denominator"], np.nan)
    D["scg_ls"] = np.where(ok, (D["smart_consensus_ls"] - D["consensus_equal_weight"]) / D["denominator"], np.nan)

    #  §24 극단치 처리 — 단면별 윈저라이즈
    for c in ("scg0", "scg_ls"):
        D[c] = D.groupby(xs, observed=True, sort=False)[c].transform(
            lambda s: _scg_winsorize(s, cfg.WINSOR_LOWER, cfg.WINSOR_UPPER,
                                     cfg.MIN_CROSS_SECTION_FOR_WINSOR))

    # ── 20거래일 전 값 참조 (§25 accel, §29 BASE_REV) ────────────────────────────────
    #  달력일이 아니라 거래일이므로, 캘린더에서 t-20 세션 날짜를 구한 뒤
    #  그 이하의 가장 가까운 signal date 를 asof 로 붙인다. (월말 그리드면 보통 전월말)
    cal = _scg_trading_calendar(calendar)
    sd = pd.DatetimeIndex(sorted(D["signal_date"].dropna().unique()))
    back = _scg_shift_td(sd, -int(cfg.ACCEL_LOOKBACK_TRADING_DAYS), cal)
    sdv = sd.values.astype("datetime64[ns]")
    #  ★ '가장 가까운' signal date 를 쓴다. '이하 중 최대' 로 하면 거래일이 21일 미만인
    #    달에서 t-20 이 직전 시점보다 살짝 앞서 두 칸 전으로 미끄러지고, 그 달의
    #    accel 과 BASE_REV 가 조용히 40거래일 변화가 된다(값은 나오는데 정의가 다르다).
    lo = np.searchsorted(sdv, back, side="right") - 1
    hi = np.minimum(lo + 1, len(sdv) - 1)
    lo_c = np.clip(lo, 0, len(sdv) - 1)
    d_lo = np.abs(sdv[lo_c].astype("int64") - back.astype("datetime64[ns]").astype("int64"))
    d_hi = np.abs(sdv[hi].astype("int64") - back.astype("datetime64[ns]").astype("int64"))
    pick = np.where((lo >= 0) & (d_lo <= d_hi), lo_c, hi)
    prev_map = pd.Series(
        [sd[p] if (not pd.isna(b)) else pd.NaT for p, b in zip(pick, back)],
        index=sd, name="_prev_sd")
    #  자기 자신을 가리키면(캘린더가 짧아 t-20 이 t 이후로 계산되는 경우) 무효 처리
    prev_map = prev_map.where(prev_map < pd.Series(sd, index=sd))

    D["_prev_sd"] = D["signal_date"].map(prev_map)
    prev = D[["signal_date"] + GROUP_KEY + ["scg_ls", "consensus_equal_weight", "denominator"]].rename(
        columns={"signal_date": "_prev_sd", "scg_ls": "_scg_ls_prev",
                 "consensus_equal_weight": "_c_prev", "denominator": "_den_prev"})
    D = D.merge(prev, on=["_prev_sd"] + GROUP_KEY, how="left")

    D["scg_accel_20d"] = D["scg_ls"] - D["_scg_ls_prev"]      # §25 — 없으면 NaN (종목은 유지)
    den_prev = np.maximum.reduce([
        D["_c_prev"].abs().to_numpy("float64"),
        D["_den_prev"].fillna(0.0).to_numpy("float64"),
        np.full(len(D), eps)])
    D["base_revision_20d"] = np.where(
        D["_c_prev"].notna() & ok,
        (D["consensus_equal_weight"] - D["_c_prev"]) / den_prev, np.nan)   # §29

    # ── §26 단면 percentile rank ────────────────────────────────────────────────────
    def _rank(col: str) -> pd.Series:
        return D.groupby(xs, observed=True, sort=False)[col].rank(method="average", pct=True)

    D["rank_base_rev"] = _rank("base_revision_20d")
    D["rank_scg0"] = _rank("scg0")
    D["rank_scg_ls"] = _rank("scg_ls")
    D["rank_scg_accel"] = _rank("scg_accel_20d")

    D["alpha_ls"] = D["rank_scg_ls"]                                          # §27
    accel_r = D["rank_scg_accel"].fillna(cfg.NEUTRAL_ACCEL_RANK)              # §28 중립 처리
    D["alpha_lsa"] = np.where(
        D["rank_scg_ls"].notna(),
        cfg.SCG_LEVEL_WEIGHT * D["rank_scg_ls"] + cfg.SCG_ACCEL_WEIGHT * accel_r,
        np.nan)

    LOG.debug(f"SCG 신호 {len(D):,}행 · 유효 {int(ok.sum()):,}행 "
              f"({D.loc[ok, 'signal_date'].nunique()}시점)")
    return D[ocols]


#  §30 — 네 전략의 알파 점수 컬럼. universe 는 하나이고 컬럼만 다르다.
STRATEGY_ALPHA_COLS = {
    "BASE_REV": "rank_base_rev",
    "SCG_0":    "rank_scg0",
    "SCG_LS":   "alpha_ls",
    "SCG_LSA":  "alpha_lsa",
}
