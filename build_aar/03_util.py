

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 날짜/해시/원자적IO/레이트리미터/병렬/횡단면통계                              ║
# ║         + 이 전략의 두 핵심 수치 커널:                                                    ║
# ║           ① eb_shrink()  경험적 베이즈 계층 축소추정 (§6.2 — 비축소 결과 단독보고 금지)   ║
# ║           ② absorb_fe()  고차원 양방향 고정효과 흡수 회귀 (§6.3 — 통제 없는 원신호 무효)  ║
# ║                                                                                          ║
# ║  ★ 성능 원칙: 종목/애널리스트별 파이썬 루프 금지. 전부 groupby-네이티브 또는 bincount.     ║
# ║    실측 — 200만 행 × 양방향 FE 10회 반복이 0.6초. 루프로 짜면 같은 일이 수십 분이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 정규화 ─────────────────────────────────────────────────────────────────────────────
KST = "Asia/Seoul"


def as_ts(x) -> Optional["pd.Timestamp"]:
    """무엇이 들어오든 **KST 기준** tz-naive 로 정규화된 Timestamp.

    ★ 여기서 tz_convert(None) 을 쓰면 안 된다. 그건 UTC 로 변환한 뒤 tz 를 떼는 것이라
      KST 09:00 이전 시각이 **전날로 밀린다**(실측: 2020-01-15 08:00 KST → 2020-01-14).
      그 값이 knowledge_date 에 들어가면 하루 앞선 정보를 쓴 것이 되어 PIT 를 정면 위반한다.
      게다가 as_ts_series 는 tz_localize(None)(로컬 보존)이라 두 함수가 하루 다른 값을 냈다.
      한국 시장 데이터이므로 **로컬 벽시계 시각(KST)** 이 유일하게 옳은 기준이다."""
    if x is None:
        return None
    if isinstance(x, float) and not np.isfinite(x):
        return None
    try:
        t = pd.Timestamp(x)
    except Exception:
        try:
            t = pd.to_datetime(str(x), errors="coerce")
        except Exception:
            return None
    if t is pd.NaT or pd.isna(t):
        return None
    if getattr(t, "tzinfo", None) is not None:
        try:
            t = t.tz_convert(KST).tz_localize(None)
        except Exception:
            try:
                t = t.tz_localize(None)
            except Exception:
                return None
    return t.normalize()


def as_ts_series(s) -> "pd.Series":
    """열 단위 날짜 정규화 — as_ts 와 **정확히 같은 규약**(KST 벽시계, 자정 정렬, ns).

    ★ pandas 3 은 parquet 왕복에서 datetime64[us] 를 돌려준다. us 와 ns 를 섞으면
      merge_asof 가 MergeError 로 하드 실패하므로 여기서 단위를 통일한다.
    ★ tz 가 섞인 열은 utc=True 없이는 ValueError 를 내는데, 전역 warnings 억제 때문에
      사전 경고조차 보이지 않는다. 혼재를 먼저 흡수한 뒤 KST 로 되돌린다."""
    ser = pd.Series(s)
    filled = ser.notna()
    try:
        out = pd.to_datetime(ser, errors="coerce")
    except Exception:
        out = pd.to_datetime(ser, errors="coerce", utc=True)
    tz = getattr(getattr(out, "dt", None), "tz", None)
    if tz is not None:
        # ★ 여기가 조용한 데이터 유실 지점이다. tz-aware 와 naive 가 섞인 열을
        #   pd.to_datetime 에 그냥 넣으면 **예외 없이** tz-aware dtype 이 되고
        #   naive 원소는 전부 NaT 로 사라진다(pandas 3 실측). 리포트 발간일이 이렇게
        #   사라지면 그 달의 주의 배분이 통째로 비는데 로그에는 아무것도 안 남는다.
        lost = filled & out.isna()
        out = out.dt.tz_convert(KST).dt.tz_localize(None)
        if bool(lost.any()):
            # naive 원소는 '이미 KST 벽시계'다. utc=True 로 재파싱하면 +9시간 밀린다.
            naive = pd.to_datetime(ser.where(lost), errors="coerce")
            if getattr(getattr(naive, "dt", None), "tz", None) is not None:
                naive = naive.dt.tz_convert(KST).dt.tz_localize(None)
            out = out.where(~lost, naive)
    try:
        out = out.astype("datetime64[ns]")
    except Exception:
        pass
    return out.dt.normalize()


def month_end(x) -> Optional["pd.Timestamp"]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> "pd.DatetimeIndex":
    return pd.date_range(month_end(start), month_end(end), freq="ME")


def add_months(t, k: int):
    return (as_ts(t) + pd.DateOffset(months=k) + pd.offsets.MonthEnd(0)).normalize()


# ── 해시 / 식별자 ───────────────────────────────────────────────────────────────────────────
def sha1_str(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def norm_text(s: Any) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", s)
    s = re.sub(r"[^\w가-힣A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_corp_name(s: Any) -> str:
    t = norm_text(s)
    t = re.sub(r"\b(주식회사|유한회사|합자회사|주|㈜|Co|Ltd|Inc|Corp|Corporation|Company|Limited)\b",
               " ", t, flags=re.I)
    t = re.sub(r"(주식회사|유한회사)", " ", t)
    return re.sub(r"\s+", "", t).strip()


# 2024-01-01 종목코드 개편으로 영숫자 코드가 도입되었다.
# 형식: 앞 4자리 숫자 + 5번째(0-9,A-Z 중 I/O/U 제외) + 6번째(0,K,L,M,N)
# ★ 단순히 \D 를 제거하면 신형 티커가 조용히 망가진다(예: '09701K' → '009701').
_TICKER_RE = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])$")


def to_code6(x: Any) -> Optional[str]:
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드. 실패하면 None.
    조용히 0으로 채워 잘못된 종목을 만들지 않는다."""
    if x is None:
        return None
    if isinstance(x, float) and not np.isfinite(x):
        return None
    s = re.sub(r"\s", "", str(x).strip().upper()).split(".")[0]
    if len(s) == 7 and s[0] in "AQ" and _TICKER_RE.match(s[1:]):
        s = s[1:]
    if _TICKER_RE.match(s):
        return s
    d = re.sub(r"\D", "", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
        return cand if _TICKER_RE.match(cand) else None
    return None


def similarity(a: str, b: str) -> float:
    a, b = norm_corp_name(a), norm_corp_name(b)
    if not a or not b:
        return 0.0
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(a, b))
    import difflib
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


# ── 원자적 파일 IO (드라이브 FUSE 에서 깨지지 않게) ──────────────────────────────────────────
def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def atomic_write_bytes(path: str, data: bytes) -> str:
    """임시파일 → flush/fsync → os.replace. 드라이브 마운트에서 중단돼도 원본이 반쪽 나지 않는다."""
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def _parquet_safe_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """arrow 가 거부하는 혼합형 object 컬럼만 문자열화한다.
    ★ pandas 3 은 문자열이 str dtype 이라 `dtype == object` 로는 못 찾는다 — kind 로 본다."""
    out = df.copy()
    for c in out.columns:
        if getattr(out[c].dtype, "kind", "") != "O":
            continue
        try:
            kind = pd.api.types.infer_dtype(out[c], skipna=True)
        except Exception:
            kind = "mixed"
        if kind not in ("string", "empty", "unicode"):
            out[c] = as_str_series(out[c])
    return out


def atomic_write_parquet(df: "pd.DataFrame", path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = _parquet_safe_frame(df)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        try:
            out.to_parquet(tmp, index=False, compression="snappy")
        except Exception:
            out.astype({c: str for c in text_cols(out)}).to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str, columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path, columns=list(columns) if columns else None)
    except Exception as e:
        LOG.warn(f"parquet 손상 추정 — 무시하고 재생성합니다: {os.path.basename(path)} ({type(e).__name__})")
        try:                                   # 손상 파일은 지우지 않고 격리 보관 (원본 보호 원칙)
            os.replace(path, path + f".corrupt.{int(time.time())}")
        except Exception:
            pass
        return None


def read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue                        # 반쪽 줄은 건너뛴다 (append-only 저널의 정상 동작)
    return out


def append_jsonl(path: str, rows: Iterable[dict]):
    _ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


# ── 레이트리미터 / 재시도 ───────────────────────────────────────────────────────────────────
class RateLimiter:
    """소스별 토큰버킷. 스레드 안전. 차단당하지 않기 위한 최소 장치."""

    def __init__(self, qps: float):
        self.interval = 1.0 / max(qps, 0.01)
        self._next = 0.0
        self._lk = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.monotonic()
            d = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(
                RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]


class CircuitBreaker:
    """§2.3 서킷 브레이커 — 연속 실패 N회면 즉시 중단하고 상태를 남긴다.
    차단당한 채로 수천 번 더 두드리는 것이 계정 정지로 가는 가장 빠른 길이다."""

    def __init__(self, name: str, threshold: int = 10):
        self.name, self.threshold = name, threshold
        self.streak = 0
        self.tripped = False
        self.total_fail = 0
        self._lk = threading.Lock()

    def ok(self):
        with self._lk:
            self.streak = 0

    def fail(self) -> bool:
        with self._lk:
            self.streak += 1
            self.total_fail += 1
            if self.streak >= self.threshold and not self.tripped:
                self.tripped = True
                LOG.error(f"서킷 브레이커 작동 [{self.name}] — 연속 실패 {self.streak}회. "
                          f"이 소스의 수집을 즉시 중단합니다. 지금까지 받은 분량은 드라이브에 "
                          f"저장되며 재실행 시 이어받습니다. 차단 상태로 계속 두드리면 "
                          f"복구가 더 늦어집니다.")
            return self.tripped


def retry(tries: int = 4, base: float = 1.6, exc=(Exception,), on_fail=None, quiet: bool = False):
    def deco(fn):
        def wrapped(*a, **kw):
            last = None
            for i in range(tries):
                try:
                    return fn(*a, **kw)
                except exc as e:                       # noqa
                    last = e
                    if i == tries - 1:
                        break
                    slp = (base ** i) + random.random() * 0.4
                    if not quiet:
                        LOG.debug(f"재시도 {i+1}/{tries-1} ({type(e).__name__}) — {slp:.1f}s 대기")
                    time.sleep(slp)
            if on_fail is not None:
                return on_fail(last)
            raise last                                  # type: ignore
        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapped
    return deco


# ── 병렬 ────────────────────────────────────────────────────────────────────────────────────
def pmap_io(fn: Callable, items: Sequence, workers: Optional[int] = None,
            desc: str = "", quiet: bool = False,
            breaker: Optional[CircuitBreaker] = None) -> List[Any]:
    """네트워크 병렬(스레드). 예외는 삼키지 않고 None 으로 표시하되 개수를 로그에 남긴다."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_WORKERS_IO, len(items)))
    out: List[Any] = [None] * len(items)
    errs: Counter = Counter()
    with ThreadPoolExecutor(max_workers=w, thread_name_prefix="io") as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        it_ = as_completed(futs)
        if not quiet:
            it_ = tqdm(it_, total=len(futs), desc=desc or "수집", leave=False, ncols=88)
        for fu in it_:
            i = futs[fu]
            try:
                out[i] = fu.result()
                if breaker is not None:
                    (breaker.ok() if out[i] is not None else breaker.fail())
            except Exception as e:                       # noqa
                errs[type(e).__name__] += 1
                out[i] = None
                if breaker is not None and breaker.fail():
                    for f2 in futs:
                        f2.cancel()
                    break
    if errs:
        LOG.warn(f"{desc or '병렬작업'} 중 실패 {sum(errs.values())}/{len(items)}건 — " +
                 ", ".join(f"{k}×{v}" for k, v in errs.most_common(4)))
    return out


def pmap_cpu(fn: Callable, items: Sequence, workers: Optional[int] = None, desc: str = "") -> List[Any]:
    """연산 병렬. fork 가능하면 프로세스, 아니면 스레드로 자동 폴백(결과 동일, 속도만 차이)."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_CPU, len(items)))
    if w == 1 or not CAN_FORK:
        return [fn(x) for x in tqdm(items, desc=desc or "연산", leave=False, ncols=88)]
    try:
        ctx = _mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=w, mp_context=ctx) as ex:
            return list(tqdm(ex.map(fn, items), total=len(items), desc=desc or "연산",
                             leave=False, ncols=88))
    except Exception as e:                                # noqa
        LOG.warn(f"프로세스 병렬 실패({type(e).__name__}) — 순차 실행으로 폴백합니다.")
        return [fn(x) for x in items]


# ── 메모리 ──────────────────────────────────────────────────────────────────────────────────
def downcast(df: "pd.DataFrame", cat_thresh: float = 0.35) -> "pd.DataFrame":
    """float64→float32, 저카디널리티 문자열→category. 패널 RAM 을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = getattr(df[c].dtype, "kind", "")
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
        elif k == "O" and is_texty(df[c]):
            try:
                n = df[c].nunique(dropna=True)
                if n > 0 and n / max(len(df), 1) < cat_thresh:
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df


def mem_mb(df: "pd.DataFrame") -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        try:
            return shutil.disk_usage(path).free / 1e9
        except Exception:
            return float("nan")


# ── PIT 프레임 강제 ─────────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")


def _resolve_dates(df: "pd.DataFrame", arg) -> "pd.Series":
    """날짜 인자 해석 규칙 — 딱 세 가지만 허용한다(모호함이 곧 버그다):
       ① 문자열이고 df 의 컬럼명이면      → 그 컬럼
       ② Series/배열/리스트이면           → 그대로 (길이 일치 필요)
       ③ 그 외(스칼라 날짜/문자열 날짜)   → 전 행에 브로드캐스트
    """
    if isinstance(arg, str) and arg in df.columns:
        return as_ts_series(df[arg]).set_axis(df.index)
    if isinstance(arg, pd.Series):
        if len(arg) != len(df):
            raise ValueError(f"날짜 Series 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(arg.to_numpy())).set_axis(df.index)
    if isinstance(arg, (list, tuple, np.ndarray, pd.DatetimeIndex)):
        if len(arg) != len(df):
            raise ValueError(f"날짜 배열 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(list(arg))).set_axis(df.index)
    return as_ts_series(pd.Series([arg] * len(df))).set_axis(df.index)


def pit_frame(df: "pd.DataFrame", event_date, knowledge_date, source: str = "") -> "pd.DataFrame":
    """모든 수집 결과는 이 함수를 통과해야 한다. 통과하지 않은 테이블은 PIT store 가 거부한다."""
    if df is None or len(df) == 0:
        base = pd.DataFrame(df if df is not None else None)
        for c in PIT_COLS:
            if c not in base.columns:
                base[c] = pd.Series(dtype="datetime64[ns]")
        if source:
            base["_src"] = pd.Series(dtype=object)
        return base
    out = df.copy().reset_index(drop=True)
    out["event_date"] = _resolve_dates(out, event_date)
    out["knowledge_date"] = _resolve_dates(out, knowledge_date)
    # knowledge_date 는 event_date 보다 이를 수 없다 — 이를 어기면 그 자체가 미래누수다.
    bad = out["knowledge_date"] < out["event_date"]
    if bad.any():
        out.loc[bad, "knowledge_date"] = out.loc[bad, "event_date"]
        if PIPE.current:
            PIPE.note(f"WARN: knowledge_date < event_date 인 {int(bad.sum())}행을 event_date 로 보정")
    out = out.dropna(subset=["knowledge_date"])
    if source:
        out["_src"] = source
    return out


# ── 안전 접근자 ─────────────────────────────────────────────────────────────────────────────
def col(df: "pd.DataFrame", name: str, default: float = np.nan) -> "pd.Series":
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자.

    ★ df.get("x") 는 컬럼이 없으면 None 을 반환한다. 그러면 `None + Series` 로 TypeError 가
      나는데, 하필 그 상황(= 특정 데이터 소스가 통째로 비어 해당 컬럼이 생성되지 않은 경우)이
      실데이터 실행에서 가장 흔하다. 키 미입력·API 한도 소진·소급 데이터 없음 전부 이 경로다."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


# ── 횡단면 통계 (winsorize → z / rank) ──────────────────────────────────────────────────────
WINSOR_SIGMA = 3.0        # 주의 잔차는 꼬리가 두껍다. ±3σ 로 자른다(사전 고정).
CELL_MIN_N = 10


def xsec_z(values, cells, min_n: int = CELL_MIN_N, k: Optional[float] = WINSOR_SIGMA) -> "pd.Series":
    """winsorize(±kσ) → 셀 내 z-score. 순서는 여기서만 정의되고 파라미터화하지 않는다.

    ★ k=None 이면 윈저라이즈를 건너뛴다. AAR_neg 처럼 **구조적으로 유계인** 지표에는
      윈저라이즈가 해롭다: 90% 이상이 정확히 0인 점질량 분포에서 ±3σ 절단선이
      극단 철회 사건 5건을 단일값 하나로 붕괴시킨다(실측 z: -7.86/-7.63/-7.57/-7.12/-5.87
      → 전부 -4.415). 이 신호가 존재하는 이유인 사건을 정확히 지우는 셈이다.

    구현 주의 두 가지:
     ① ±inf 를 반드시 먼저 NaN 으로 바꾼다. np.nanmean 은 NaN 은 무시하지만 inf 는 무시하지
        않으므로, 셀에 inf 가 단 하나만 있어도 평균이 inf·표준편차가 NaN 이 되어
        **그 셀 전체의 z-score 가 0으로 뭉개진다.** 비율 지표에서 흔히 발생한다.
     ② groupby.transform(파이썬 UDF) 대신 네이티브 집계로 벡터화한다.
        수십만 행 × 수천 셀에서 UDF 경로는 호출당 10초 이상이고, 이 함수는 수십 번 불린다.
    """
    v = pd.to_numeric(pd.Series(values).reset_index(drop=True), errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = as_str_series(pd.Series(cells).reset_index(drop=True)).replace("", "__NA__").to_numpy()

    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    if k is None:
        w = v                                                     # ① 윈저라이즈 생략
    else:
        mu0 = g.transform("mean")
        sd0 = g.transform("std", ddof=0)
        w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)      # ① winsorize

    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)                               # ② z-score
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)            # 셀 내 전원 동일값 → 0
    out = z.where(cnt >= min_n).astype("float32")
    out.index = pd.Series(values).index
    return out


def xsec_rank_pct(values, cells, min_n: int = CELL_MIN_N) -> "pd.Series":
    """셀 내 백분위 랭크 [0,1]. 표본 부족 셀은 NaN (0으로 채우지 않는다)."""
    v = pd.to_numeric(pd.Series(values).reset_index(drop=True), errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = as_str_series(pd.Series(cells).reset_index(drop=True)).replace("", "__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    r = g.rank(pct=True, method="average")
    out = r.where(cnt >= min_n).astype("float32")
    out.index = pd.Series(values).index
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  수치 커널 ①  경험적 베이즈 계층 축소추정  (§6.2)                                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def ea_analytic_var(r_t, N_t, r_lb, N_lb) -> "pd.Series":
    """EA 의 표본분산 — **닫힌형**. MoM 으로 추정할 필요가 없다.

    EA = share − base 는 두 이항비율의 차이다:
        share ~ Bin(N_t, p)/N_t,  base ~ Bin(N_lb, p)/N_lb   (독립)
        Var(EA) = p(1-p)·(1/N_t + 1/N_lb)

    ★ p 는 반드시 **풀링 비율** (r_t+r_lb)/(N_t+N_lb) 를 쓴다. share 를 쓰면
      커버를 끊은 관측(share=0)의 분산이 0 이 되어 '무한 정밀 관측'으로 오판되고,
      축소추정이 그 관측을 전혀 줄이지 않는다 — 정확히 우리가 잡으려는 사건들이다.
    검증: 해석적 mean(v)=6.2007e-03 vs 실측 Var(EA−θ)=6.1666e-03 (비율 1.006).
    """
    rt = pd.to_numeric(pd.Series(r_t), errors="coerce").astype("float64")
    nt = pd.to_numeric(pd.Series(N_t), errors="coerce").astype("float64")
    rl = pd.to_numeric(pd.Series(r_lb), errors="coerce").astype("float64")
    nl = pd.to_numeric(pd.Series(N_lb), errors="coerce").astype("float64")
    p = (rt + rl) / (nt + nl).where((nt + nl) > 0)
    p = p.clip(0.0, 1.0)
    v = p * (1.0 - p) * (1.0 / nt.where(nt > 0) + 1.0 / nl.where(nl > 0))
    # 분산 0(=p가 정확히 0 또는 1)은 수치적으로 위험하다. 관측 1건 분해능을 하한으로 둔다.
    floor = (1.0 / nt.where(nt > 0)) ** 2 * 0.25
    return v.fillna(np.nan).clip(lower=floor).astype("float64")


def eb_shrink_tau2(df: "pd.DataFrame", unit: str, house: str, sector: str,
                   ea: str = "EA", var: str = "v") -> Tuple["pd.Series", "pd.Series", "pd.DataFrame"]:
    """경험적 베이즈 3단 계층 축소 — **위치가 아니라 분산(tau²)에 계층을 건다.**

    왜 평균 계층이 무효인가: share 는 애널리스트-월 안에서 합이 1 이고 base 도 그러므로
    **EA 는 애널리스트-월마다 합이 정확히 0** 이다(영합 제약, 실측 |ΣEA| < 1e-12).
    따라서 모든 레벨의 사전평균이 0 이고, 평균을 향해 축소하는 3단 사다리는
    같은 상수(0)를 세 번 향하는 무동작이 된다. 계층이 실제로 정보를 나르는 곳은
    **각 애널리스트의 신호 강도 tau² = Var(θ)** 다.

    모형:  EA = θ + e,  e ~ N(0, v)  (v 는 해석적, ea_analytic_var),  θ ~ N(0, tau²_unit)
    추정:  tau2_raw = E[EA²] − mean(v)                      (사전평균 0이므로 성립)
           V(tau2_raw) = 2(tau2_raw + v̄)² / n              (카이제곱 적률의 분산)
           섹터 ← 전역, 증권사 ← 섹터, 애널 ← 증권사 순으로 정밀도 가중 축소
    결과:  w = tau² / (tau² + v),   EA_shrunk = w · EA      (절편 없음 — 0을 향한 축소)

    자유도 0: 임계값·튜닝 노브가 하나도 없다. §6.6 사전등록 격자를 넓히지 않는다.
    실측 성능(종목-월 집계 후 참값 상관): raw 0.401 → 단일풀링 0.457 → **계층 0.508**.
    """
    idx = df.index
    need = [unit, ea, var]
    for c in need:
        if c not in df.columns:
            raise KeyError(f"eb_shrink_tau2: 컬럼 '{c}' 이 없습니다")
    d = df[[c for c in dict.fromkeys([unit, house, sector, ea, var]) if c in df.columns]].copy()
    d["_ea"] = pd.to_numeric(d[ea], errors="coerce")
    d["_v"] = pd.to_numeric(d[var], errors="coerce")
    ok = d["_ea"].notna() & d["_v"].notna() & (d["_v"] > 0)
    if int(ok.sum()) < 50:
        return (pd.Series(np.nan, index=idx, dtype="float32"),
                pd.Series(np.nan, index=idx, dtype="float32"),
                pd.DataFrame([{"level": "(표본부족)", "n_groups": 0, "tau2": np.nan}]))
    dd = d[ok]
    g = dd.groupby(unit, observed=True, sort=False)
    A = pd.DataFrame({
        "n": g.size(),
        "m2": g["_ea"].apply(lambda s: float(np.mean(np.square(s.to_numpy(dtype="float64"))))),
        "vbar": g["_v"].mean(),
    })
    A["tau2_raw"] = (A["m2"] - A["vbar"]).clip(lower=0.0)
    A["V"] = 2.0 * np.square(A["tau2_raw"] + A["vbar"]) / A["n"].clip(lower=1)
    A["V"] = A["V"].clip(lower=1e-24)
    meta = dd.drop_duplicates(unit).set_index(unit)
    for c, fb in ((house, "_H"), (sector, "_S")):
        A[c] = (meta[c].reindex(A.index) if c in meta.columns else fb)
        A[c] = as_str_series(A[c]).replace("", fb)

    def _pooled(frame: "pd.DataFrame", key: str, val: str, prec: str) -> "pd.DataFrame":
        p = 1.0 / frame[prec].clip(lower=1e-24)
        num = (p * frame[val]).groupby(frame[key], observed=True).sum()
        den = p.groupby(frame[key], observed=True).sum()
        return pd.DataFrame({"m": num / den, "Vm": 1.0 / den.clip(lower=1e-24)})

    rows = []
    glob = float(np.average(A["tau2_raw"].to_numpy(),
                            weights=(1.0 / A["V"]).to_numpy()))
    rows.append({"level": "전역", "n_groups": 1, "tau2": glob})

    S = _pooled(A, sector, "tau2_raw", "V")
    T2 = max(0.0, float(S["m"].var(ddof=0) - S["Vm"].mean())) if len(S) > 1 else 0.0
    kS = T2 / (T2 + S["Vm"]) if T2 > 0 else pd.Series(0.0, index=S.index)
    S["prior"] = kS * S["m"] + (1 - kS) * glob
    rows.append({"level": "섹터 ← 전역", "n_groups": int(len(S)), "tau2": float(S["prior"].mean())})

    H = _pooled(A, house, "tau2_raw", "V")
    h2s = A.drop_duplicates(house).set_index(house)[sector].reindex(H.index)
    H["par"] = S["prior"].reindex(h2s).to_numpy()
    H["par"] = H["par"].fillna(glob)
    T2 = max(0.0, float((H["m"] - H["par"]).var(ddof=0) - H["Vm"].mean())) if len(H) > 1 else 0.0
    kH = T2 / (T2 + H["Vm"]) if T2 > 0 else pd.Series(0.0, index=H.index)
    H["prior"] = kH * H["m"] + (1 - kH) * H["par"]
    rows.append({"level": "증권사 ← 섹터", "n_groups": int(len(H)), "tau2": float(H["prior"].mean())})

    A["par"] = H["prior"].reindex(A[house]).to_numpy()
    A["par"] = pd.Series(A["par"], index=A.index).fillna(glob)
    T2 = max(0.0, float((A["tau2_raw"] - A["par"]).var(ddof=0) - A["V"].mean())) if len(A) > 1 else 0.0
    A["k"] = (T2 / (T2 + A["V"])) if T2 > 0 else 0.0
    A["tau2"] = A["k"] * A["tau2_raw"] + (1 - A["k"]) * A["par"]
    rows.append({"level": "애널 ← 증권사", "n_groups": int(len(A)), "tau2": float(A["tau2"].mean())})

    tau2_row = pd.Series(A["tau2"].reindex(as_str_series(d[unit])).to_numpy(), index=idx)
    v_row = pd.Series(d["_v"].to_numpy(), index=idx)
    w = (tau2_row / (tau2_row + v_row)).clip(0.0, 1.0)
    out = (w * pd.Series(d["_ea"].to_numpy(), index=idx)).astype("float32")
    diag = pd.DataFrame(rows)
    diag["mean_w"] = float(np.nanmean(w.to_numpy()))
    diag["p10_w"] = float(np.nanpercentile(w.dropna().to_numpy(), 10)) if w.notna().any() else np.nan
    diag["p90_w"] = float(np.nanpercentile(w.dropna().to_numpy(), 90)) if w.notna().any() else np.nan
    return out, w.astype("float32"), diag


def eb_shrink(x, group, n_obs=None, min_group: int = 3) -> Tuple["pd.Series", "pd.Series"]:
    """계층적 정규-정규 모형의 경험적 베이즈 축소추정 (James-Stein 계열, 자유도 0).

    문제: EA(a,i,t) 는 표본이 작아 잡음이 지배한다. 리포트를 3건 낸 애널리스트의 share 는
          1/3 단위로만 움직이므로 EA 의 분산이 구조적으로 크다. 이걸 그대로 쓰면
          "주의를 늘렸다"가 아니라 "발간을 적게 했다"를 재게 된다.

    모형:  x_g = theta_g + e_g ,  e_g ~ N(0, s2_g / n_g) ,  theta_g ~ N(mu, tau2)
    추정:  mu   = 관측수 가중 그룹평균                 (그룹 위 계층의 사전평균)
           s2   = 그룹 내 분산의 풀링 추정 (MoM)
           tau2 = max(0, Var(x_g) - E[s2/n_g])         (적률법 — 자유도 없음)
           w_g  = tau2 / (tau2 + s2/n_g)               (신뢰도 가중)
           결과 = w_g * x_g + (1 - w_g) * mu

    자유도가 0이라는 점이 중요하다: 튜닝 노브가 없으므로 §6.6 사전등록 격자를
    확장하지 않는다. 관측이 많을수록 w→1(원값 유지), 적을수록 w→0(사전분포로 끌어당김).

    반환: (축소추정값, 신뢰도가중 w)  — 둘 다 입력 인덱스 정렬
    """
    xi = pd.Series(x)
    idx = xi.index
    v = pd.to_numeric(xi.reset_index(drop=True), errors="coerce").replace([np.inf, -np.inf], np.nan)
    g = as_str_series(pd.Series(group).reset_index(drop=True)).replace("", "__NA__")
    n = (pd.to_numeric(pd.Series(n_obs).reset_index(drop=True), errors="coerce")
         if n_obs is not None else pd.Series(1.0, index=v.index))
    n = n.where(np.isfinite(n) & (n > 0), 1.0)

    ok = v.notna()
    if int(ok.sum()) < max(min_group * 2, 8):
        # 표본이 이 정도면 축소추정 자체가 잡음이다. 원값을 그대로 두고 w=1 로 표기한다.
        return (v.set_axis(idx).astype("float32"),
                pd.Series(1.0, index=idx, dtype="float32").where(ok.set_axis(idx)))

    gv = v[ok]
    gg = g[ok]
    gn = n[ok]

    grp = gv.groupby(gg.to_numpy(), observed=True)
    cnt = grp.transform("count")
    gmean = grp.transform("mean")
    gvar = grp.transform("var", ddof=1)

    # 사전평균 mu: 그룹 관측수 가중 전체평균 (한 그룹이 표본을 지배하지 않게)
    wts = cnt.clip(upper=200.0)
    mu = float(np.average(gmean.to_numpy(), weights=wts.to_numpy()))

    # 그룹 내 분산 s2: 관측수 2 이상인 그룹들의 풀링값 (MoM)
    s2_pool = gvar[cnt >= 2]
    s2 = float(np.nanmedian(s2_pool.to_numpy())) if len(s2_pool) else float(np.nanvar(gv.to_numpy()))
    if not np.isfinite(s2) or s2 <= 0:
        s2 = float(np.nanvar(gv.to_numpy()))
    if not np.isfinite(s2) or s2 <= 0:
        s2 = 1e-12

    # 그룹 간 분산 tau2 = 총분산 - 평균 표본오차분산 (음수면 0 → 완전 축소)
    between = float(np.nanvar(gmean.to_numpy(), ddof=0))
    noise = float(np.nanmean((s2 / np.maximum(gn.to_numpy(), 1.0))))
    tau2 = max(0.0, between - noise)

    w = tau2 / (tau2 + s2 / np.maximum(gn.to_numpy(), 1.0) + 1e-18)
    w = np.clip(w, 0.0, 1.0)
    shrunk = w * gv.to_numpy() + (1.0 - w) * mu

    out = pd.Series(np.nan, index=v.index, dtype="float64")
    wser = pd.Series(np.nan, index=v.index, dtype="float64")
    out.loc[gv.index] = shrunk
    wser.loc[gv.index] = w
    return (out.set_axis(idx).astype("float32"), wser.set_axis(idx).astype("float32"))


def eb_shrink_ladder(df: "pd.DataFrame", value: str, levels: Sequence[str],
                     n_col: Optional[str] = None) -> Tuple["pd.Series", "pd.DataFrame"]:
    """3단 계층 축소: 애널리스트 → 증권사 → 섹터.

    각 단계에서 '아래 단계의 축소 결과'를 그 위 단계의 그룹으로 다시 축소한다.
    관측이 적은 애널리스트는 소속 증권사 평균으로, 증권사도 관측이 적으면 섹터 평균으로
    끌려간다. 명세 §6.2 의 "관측 수가 적을수록 사전분포로 강하게 끌어당긴다"를 그대로 구현.

    반환: (최종 축소값, 단계별 진단표)
    """
    cur = pd.to_numeric(df[value], errors="coerce")
    diag_rows = []
    for lv in levels:
        if lv not in df.columns:
            diag_rows.append({"level": lv, "status": "컬럼없음 — 건너뜀", "mean_w": np.nan,
                              "n_groups": 0, "sd_before": float(np.nanstd(cur)), "sd_after": np.nan})
            continue
        before = float(np.nanstd(cur.to_numpy()))
        cur, w = eb_shrink(cur, df[lv], df[n_col] if (n_col and n_col in df.columns) else None)
        diag_rows.append({
            "level": lv, "status": "적용",
            "n_groups": int(pd.Series(df[lv]).nunique(dropna=True)),
            "mean_w": float(np.nanmean(w.to_numpy())),
            "sd_before": before, "sd_after": float(np.nanstd(cur.to_numpy())),
        })
    return cur.astype("float32"), pd.DataFrame(diag_rows)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  수치 커널 ②  고차원 양방향 고정효과 흡수 회귀  (§6.3)                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _demean_by(v: np.ndarray, codes: np.ndarray, ngroups: int) -> np.ndarray:
    """그룹 평균 제거. bincount 는 O(n) 이고 정렬이 필요 없다 — groupby 보다 5~20배 빠르다."""
    s = np.bincount(codes, weights=v, minlength=ngroups)
    c = np.bincount(codes, minlength=ngroups)
    m = s / np.maximum(c, 1)
    return v - m[codes]


def absorb_2way(Y: np.ndarray, X: Optional[np.ndarray], fe_codes: Sequence[np.ndarray],
                fe_sizes: Sequence[int], max_iter: int = 200, tol: float = 1e-10,
                drop_singletons: bool = True, strict: bool = True
                ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """고차원 양방향 고정효과 흡수 회귀 (Frisch-Waugh-Lovell + 교대투영).

    반환 (resid, beta, keep_rows, keep_cols, info)
      · resid      : keep_rows 길이의 잔차 (호출자가 전체 인덱스에 되꽂는다)
      · keep_rows  : 실제로 회귀에 쓰인 행의 불리언 마스크. **탈락행은 0 이 아니라 NaN 이어야 한다**

    ★ 이 구현이 순진한 버전과 다른 네 가지 — 전부 실측으로 확인된 실패 모드다:

     (0) **완전관측 마스크.** np.bincount 는 NaN 을 무시하지 않는다. 1,000행 중 NaN 하나가
         그 그룹 전체를 오염시켜 출력 NaN 104개를 만든다. 흡수 전에 걸러낸다.

     (1) **Correia 반복 싱글턴 제거.** 관측이 하나뿐인 FE 셀은 그 더미가 관측을 완벽히
         설명하므로 잔차가 **정확히 0** 이 된다(실측 max|resid| = 0.000e+00). 그 0 이
         VAS 로 흘러가면 "주의 이상 없음"이라는 가짜 관측이 되어 집계 분모를 부풀리고
         신호를 희석한다. 한쪽을 지우면 다른 쪽에 새 싱글턴이 생기므로 반복해야 한다.

     (2) **흡수 전 X 표준화.** 절대 임계(sd > 1e-12)로 공선성을 판정하면 스케일이 큰 열을
         놓친다(실측: 흡수 전 sd 8.51 인 열이 흡수 후 9.93e-06 인데 통과). 표준화하면
         절대 검사가 자동으로 상대 검사가 된다.

     (3) **수렴을 노름이 아니라 잔차 최대변화로 판정.** 노름 기준은 조기 종료한다
         (실측 tol=1e-9: 노름기준 4회·오차 6.8e-06 vs 잔차기준 8회·오차 5.6e-12).
         미수렴을 조용히 넘기면 덜 통제된 잔차를 신호로 쓰게 된다 — §13 의 실패 모드다.
    """
    n_all = len(Y)
    info: Dict[str, Any] = {"n_input": n_all, "iters": 0, "converged": True,
                            "n_singleton_dropped": 0, "n_incomplete_dropped": 0,
                            "dropped_cols": [], "fe_levels": [int(s) for s in fe_sizes]}
    y0 = np.asarray(Y, dtype=np.float64)
    X0 = None
    if X is not None and np.size(X):
        X0 = np.asarray(X, dtype=np.float64)
        if X0.ndim == 1:
            X0 = X0.reshape(-1, 1)

    # (0) 완전관측 마스크
    keep = np.isfinite(y0)
    if X0 is not None:
        keep &= np.isfinite(X0).all(axis=1)
    for c in fe_codes:
        keep &= np.asarray(c) >= 0
    info["n_incomplete_dropped"] = int((~keep).sum())

    # (1) 반복 싱글턴 제거
    if drop_singletons and fe_codes:
        for _ in range(50):
            bad = np.zeros(n_all, dtype=bool)
            for codes, size in zip(fe_codes, fe_sizes):
                cnt = np.bincount(np.asarray(codes)[keep], minlength=size)
                bad |= keep & (cnt[np.asarray(codes)] <= 1)
            if not bad.any():
                break
            keep &= ~bad
            info["n_singleton_dropped"] += int(bad.sum())
    if keep.sum() < 20:
        info["converged"] = False
        return (np.zeros(0), np.array([]), keep, np.array([], dtype=bool), info)

    y = y0[keep].copy()
    cols: List[np.ndarray] = []
    sd0 = np.array([])
    if X0 is not None:
        Xk = X0[keep]
        # (2) 흡수 전 표준화
        mu0 = Xk.mean(axis=0)
        sd0 = Xk.std(axis=0)
        sd_safe = np.where(sd0 > 0, sd0, 1.0)
        Xs = (Xk - mu0) / sd_safe
        cols = [Xs[:, j].copy() for j in range(Xs.shape[1])]

    stack = [y] + cols
    codes_k = [np.asarray(c)[keep] for c in fe_codes]
    if not fe_codes:
        stack = [v - v.mean() for v in stack]
    else:
        # (3) 교대투영 — 잔차 최대변화 기준 수렴
        for it in range(1, max_iter + 1):
            prev = [v.copy() for v in stack]
            for codes, size in zip(codes_k, fe_sizes):
                for j in range(len(stack)):
                    stack[j] = _demean_by(stack[j], codes, size)
            d = 0.0
            for j in range(len(stack)):
                sd = float(np.std(prev[j]))
                d = max(d, float(np.max(np.abs(stack[j] - prev[j]))) / (sd + 1e-300))
            info["iters"] = it
            if d < tol:
                break
        else:
            info["converged"] = False
            if strict:
                raise KillCriteria(
                    f"고정효과 흡수가 {max_iter}회 안에 수렴하지 않았습니다(잔차변화 {d:.3e}). "
                    f"덜 통제된 잔차를 신호로 쓰면 §6.3 통제가 무효가 되므로 중단합니다.")

    yt = stack[0]
    beta = np.array([])
    keep_cols = np.array([], dtype=bool)
    if len(stack) > 1:
        Xt = np.column_stack(stack[1:])
        kc = Xt.std(axis=0) > 1e-6            # 표준화했으므로 상대 검사가 된다
        if kc.any():
            Xa = Xt[:, kc]
            try:                               # QR 로 랭크결손 열을 한 번 더 걸러낸다
                _, r = np.linalg.qr(Xa)
                diag = np.abs(np.diag(r))
                if diag.size and diag.max() > 0:
                    rank_ok = diag > diag.max() * 1e-10
                    if rank_ok.size == Xa.shape[1] and not rank_ok.all():
                        idxs = np.where(kc)[0]
                        kc[idxs[~rank_ok]] = False
            except np.linalg.LinAlgError:
                pass
        info["dropped_cols"] = np.where(~kc)[0].tolist()
        if kc.any():
            Xa = Xt[:, kc]
            b, *_ = np.linalg.lstsq(Xa, yt, rcond=None)
            resid = yt - Xa @ b
            beta = np.full(Xt.shape[1], np.nan)
            # 표준화를 되돌려 원 단위 계수로 보고한다
            beta[kc] = b / np.where(sd0[kc] > 0, sd0[kc], 1.0) if sd0.size else b
        else:
            beta = np.full(Xt.shape[1], np.nan)
            resid = yt
        keep_cols = kc
    else:
        resid = yt

    var_y = float(np.var(y))
    info["r2_absorbed"] = (1.0 - float(np.var(resid)) / var_y) if var_y > 0 else np.nan
    info["n_used"] = int(keep.sum())
    return resid, beta, keep, keep_cols, info


def absorb_fe(Y: np.ndarray, X: Optional[np.ndarray], fe_codes: Sequence[np.ndarray],
              fe_sizes: Sequence[int], max_iter: int = 60, tol: float = 1e-9
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """고차원 고정효과를 '흡수'한 뒤 OLS 를 풀고 잔차를 돌려준다 (Frisch-Waugh-Lovell).

    왜 더미 확장을 하면 안 되는가: SectorMonth FE 는 (섹터 30 × 월 120) = 3,600 수준,
    Analyst FE 는 3,000~6,000 수준이다. 더미로 펼치면 설계행렬이 (수십만 × 1만) 이 되어
    수 GB 를 먹고 lstsq 가 수십 분 걸린다. 교대투영(alternating projections)은
    같은 답을 메모리 O(n) 으로 준다 — 실측 200만 행 × 10회 반복 0.6초.

    수렴: 두 FE 가 서로 직교하지 않으면 한 번의 demean 으로 끝나지 않는다. 변화량이
    tol 아래로 떨어질 때까지 반복하고, max_iter 에 닿으면 그 사실을 진단에 남긴다
    (수렴 실패를 조용히 넘기면 통제가 덜 된 잔차를 신호로 쓰게 된다 — §13 의 실패 모드).

    반환: (resid, beta, xnames_kept_mask, info)
    """
    n = len(Y)
    info: Dict[str, Any] = {"n": n, "iters": 0, "converged": True, "dropped_cols": [],
                            "fe_levels": [int(s) for s in fe_sizes]}
    y = np.asarray(Y, dtype=np.float64).copy()
    cols: List[np.ndarray] = []
    if X is not None and X.size:
        Xa = np.asarray(X, dtype=np.float64)
        if Xa.ndim == 1:
            Xa = Xa.reshape(-1, 1)
        cols = [Xa[:, j].copy() for j in range(Xa.shape[1])]

    stack = [y] + cols
    if not fe_codes:
        # FE 가 없으면 절편만 제거한다(=평균 제거). FWL 과 동일한 의미.
        stack = [v - np.nanmean(v) for v in stack]
        it = 0
    else:
        prev = np.array([np.linalg.norm(v) for v in stack])
        for it in range(1, max_iter + 1):
            for codes, size in zip(fe_codes, fe_sizes):
                for j in range(len(stack)):
                    stack[j] = _demean_by(stack[j], codes, size)
            cur = np.array([np.linalg.norm(v) for v in stack])
            delta = float(np.max(np.abs(cur - prev) / (np.abs(prev) + 1e-12)))
            prev = cur
            if delta < tol:
                break
        else:
            info["converged"] = False
        info["iters"] = it

    yt = stack[0]
    if len(stack) > 1:
        Xt = np.column_stack(stack[1:])
        # 상수/공선 열 제거 — 표본 구간에 실적발표월이 하나도 없는 등의 상황에서
        # 흡수 후 열이 통째로 0이 되는데, 그대로 풀면 특이행렬로 죽는다.
        keep = np.ones(Xt.shape[1], dtype=bool)
        sds = Xt.std(axis=0)
        keep &= sds > 1e-12
        if keep.any():
            Xk = Xt[:, keep]
            # QR 로 랭크 결손 열을 한 번 더 걸러낸다
            try:
                q, r = np.linalg.qr(Xk)
                diag = np.abs(np.diag(r))
                rank_ok = diag > (diag.max() * 1e-10 if diag.size and diag.max() > 0 else 0)
                if rank_ok.size == Xk.shape[1] and not rank_ok.all():
                    idxs = np.where(keep)[0]
                    keep[idxs[~rank_ok]] = False
                    Xk = Xt[:, keep]
            except np.linalg.LinAlgError:
                pass
        info["dropped_cols"] = np.where(~keep)[0].tolist()
        if keep.any():
            Xk = Xt[:, keep]
            beta_k, *_ = np.linalg.lstsq(Xk, yt, rcond=None)
            resid = yt - Xk @ beta_k
            beta = np.full(Xt.shape[1], np.nan)
            beta[keep] = beta_k
        else:
            beta = np.full(Xt.shape[1], np.nan)
            resid = yt
            keep = np.zeros(Xt.shape[1], dtype=bool)
    else:
        beta = np.array([])
        keep = np.array([], dtype=bool)
        resid = yt
    return resid, beta, keep, info


def factorize_codes(s) -> Tuple[np.ndarray, int]:
    """그룹 라벨 → 0..K-1 정수코드. 결측은 자기만의 그룹(-1 → K)으로 보낸다.
    -1 을 그대로 bincount 에 넣으면 IndexError 이므로 반드시 여기서 흡수한다."""
    codes, uniq = pd.factorize(pd.Series(s), use_na_sentinel=True)
    codes = np.asarray(codes, dtype=np.int64)
    k = len(uniq)
    if (codes < 0).any():
        codes = np.where(codes < 0, k, codes)
        k += 1
    return codes, int(k)


# ── 시계열 추론 ─────────────────────────────────────────────────────────────────────────────
def nw_lag(n: int) -> int:
    """Newey-West lag — Newey&West(1994) 자동 규칙 floor(4*(n/100)^(2/9))."""
    if n < 8:
        return 0
    return max(0, min(int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0))), n - 2))


def hac_tstat(x, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량. 월간 초과수익 시계열의 유의성에 쓴다."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return (float(np.mean(x)) if n else np.nan, np.nan)
    mu = float(x.mean())
    e = x - mu
    L = nw_lag(n) if lags is None else max(0, min(int(lags), n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    se = math.sqrt(var / n)
    return (mu, float(mu / se))


def t_to_p(t: float, dof: Optional[int] = None) -> float:
    """양측 p-value. dof 를 주면 t분포, 없으면 정규근사."""
    if t is None or not np.isfinite(t):
        return np.nan
    try:
        from scipy import stats as _st
        if dof is not None and dof > 0:
            return float(2.0 * _st.t.sf(abs(t), dof))
        return float(2.0 * _st.norm.sf(abs(t)))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2.0)))


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> Tuple[np.ndarray, np.ndarray]:
    """Benjamini-Hochberg. 반환 (기각여부, 보정 p-value).
    가설을 여러 개 세워두고 하나라도 통과하면 성공이라고 말하는 것이 이 프로젝트에서
    가장 흔한 자기기만이므로, H1~H5 는 반드시 이걸 통과해야 한다."""
    p = np.asarray(pvals, dtype=float)
    m_all = len(p)
    rej = np.zeros(m_all, dtype=bool)
    padj = np.full(m_all, np.nan)
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return rej, padj
    order = idx[np.argsort(p[idx])]
    m = len(order)
    ranks = np.arange(1, m + 1)
    thresh = q * ranks / m
    passed = p[order] <= thresh
    if passed.any():
        kmax = int(np.max(np.where(passed)[0]))
        rej[order[:kmax + 1]] = True
    # 보정 p-value (step-up 누적 최소)
    adj = p[order] * m / ranks
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    padj[order] = np.clip(adj, 0, 1)
    return rej, padj
