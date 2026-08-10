
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 해시 / 원자적 IO / 재시도 / 레이트리미터 / 병렬 / 벡터화 통계               ║
# ║                                                                                          ║
# ║  · 횡단면 변환 순서(C5)는 여기서 단 한 번 하드코딩된다: winsorize → z → rank_pct          ║
# ║  · 롤링 회귀는 반드시 벡터화 (칼만 폐기, §3). 종목별 파이썬 루프 금지.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 정규화 ─────────────────────────────────────────────────────────────────────────────
def as_ts(x) -> Optional[pd.Timestamp]:
    """무엇이 들어오든 tz-naive 로 정규화된 Timestamp. tz 혼재는 이 프로젝트 최빈 버그였다."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
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
        t = t.tz_localize(None) if t.tz is None else t.tz_convert(None).tz_localize(None)
    return t.normalize()

def as_ts_series(s) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    return out.dt.normalize()

def month_end(x) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()

def month_range(start, end) -> pd.DatetimeIndex:
    return pd.date_range(month_end(start), month_end(end), freq="ME")

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
    """상호/애널리스트명/제목 정규화. 매칭 정확도의 8할이 여기서 결정된다."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", s)        # 괄호 안 제거
    s = re.sub(r"[^\w가-힣A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_corp_name(s: Any) -> str:
    """법인격 접미어 제거 — 사업장명↔법인명 매칭용."""
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
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드.
    실패하면 None. 조용히 0으로 채워 잘못된 종목을 만들지 않는다."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
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

# ── 원자적 파일 IO (드라이브 FUSE 에서 깨지지 않게) ──────────────────────────────────────────
def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)

def atomic_write_bytes(path: str, data: bytes) -> str:
    """임시파일 → flush/fsync → os.replace. 드라이브 마운트에서 중단돼도 원본이 반쪽 나지 않는다."""
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
    os.replace(tmp, path)
    return path

def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))

def atomic_write_parquet(df: pd.DataFrame, path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = df.copy()
    for c in out.columns:                       # object 컬럼은 arrow 가 종종 거부한다 → 문자열화
        if out[c].dtype == object:
            try:
                pd.api.types.infer_dtype(out[c], skipna=True)
            except Exception:
                out[c] = out[c].astype(str)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        out.to_parquet(tmp, index=False, compression="snappy")
    os.replace(tmp, path)
    return path

def pq_num_rows(path: str) -> int:
    """parquet 행 수를 **메타데이터만 읽어** 반환한다. 캐시 축소 감지용이라 전량 로드 금지."""
    try:
        import pyarrow.parquet as _pq                        # type: ignore
        return int(_pq.ParquetFile(path).metadata.num_rows)
    except Exception:
        pass
    try:
        return int(len(pd.read_parquet(path, columns=[])))
    except Exception:
        try:
            return int(len(pd.read_parquet(path)))
        except Exception:
            return -1

def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    """parquet 안전 읽기.

    ★ 읽기 실패를 곧바로 '파일 손상'으로 단정하면 안 된다. 구글드라이브 FUSE 의 OSError(5),
      스트리밍 마운트 미실체화, arrow 버전/코덱 문제도 전부 같은 예외로 온다. 예전에는
      그때마다 원본을 `.corrupt.<ts>` 로 개명했는데, get_table 은 `{name}.parquet` 만 찾고
      adopt_scan 의 확장자 필터에도 안 걸려 **영구 고아**가 됐다(= 삭제와 구분되지 않는다).
      → 짧은 백오프로 재시도하고, 그래도 실패하면 매직바이트를 확인해 진짜 손상일 때만
        격리하되 `.parquet` 확장자를 유지해 회수 가능하게 둔다.
    """
    if not os.path.exists(path):
        return None
    last = None
    for k in range(3):
        try:
            return pd.read_parquet(path)
        except Exception as e:                                      # noqa
            last = e
            if k < 2:
                time.sleep(0.4 * (k + 1))
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
    except Exception:
        magic = b""
    if magic == b"PAR1":
        LOG.warn(f"parquet 읽기 실패({type(last).__name__}) — 파일 자체는 정상(PAR1)입니다. "
                 f"드라이브 I/O 문제일 수 있어 **개명하지 않고** 그대로 둡니다: "
                 f"{os.path.basename(path)}")
        return None
    dst = f"{os.path.splitext(path)[0]}.corrupt-{int(time.time())}.parquet"
    try:
        os.replace(path, dst)
        LOG.warn(f"parquet 헤더가 손상되어 격리했습니다(.parquet 확장자 유지 — 회수 가능): "
                 f"{os.path.basename(dst)}")
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
            if now < self._next:
                d = self._next - now
            else:
                d = 0.0
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()

def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]

# ── 병렬 ────────────────────────────────────────────────────────────────────────────────────
def pmap_io(fn: Callable, items: Sequence, workers: Optional[int] = None,
            desc: str = "", quiet: bool = False) -> List[Any]:
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
            except Exception as e:                       # noqa
                errs[type(e).__name__] += 1
                out[i] = None
    if errs:
        LOG.warn(f"{desc or '병렬작업'} 중 실패 {sum(errs.values())}/{len(items)}건 — " +
                 ", ".join(f"{k}×{v}" for k, v in errs.most_common(4)))
    return out

# ── 메모리 ──────────────────────────────────────────────────────────────────────────────────
def downcast(df: pd.DataFrame, cat_thresh: float = 0.35) -> pd.DataFrame:
    """float64→float32, 저카디널리티 object→category. 10년 패널 RAM을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = df[c].dtype.kind
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
        elif k == "O":
            try:
                n = df[c].nunique(dropna=True)
                if n > 0 and n / max(len(df), 1) < cat_thresh:
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df

def mem_mb(df: pd.DataFrame) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0

# ── PIT 프레임 강제 (C1) ────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")

def _resolve_dates(df: pd.DataFrame, arg) -> pd.Series:
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

def pit_frame(df: pd.DataFrame, event_date, knowledge_date, source: str = "") -> pd.DataFrame:
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

# ── 벡터화 횡단면 통계 (C5 순서 고정) ───────────────────────────────────────────────────────
WINSOR_SIGMA = 2.0
CELL_MIN_N = 8

def xsec_z(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N,
           k: float = WINSOR_SIGMA) -> pd.Series:
    """C5: winsorize(±2σ) → 셀 내 z-score.  순서는 여기서만 정의되고 파라미터화하지 않는다."""
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()

    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    mu0 = g.transform("mean")
    sd0 = g.transform("std", ddof=0)
    w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)          # ① winsorize

    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)                               # ② z-score
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)            # 셀 내 전원 동일값 → 0
    return z.where(cnt >= min_n).astype("float32")

def xsec_rank_pct(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 백분위 랭크 [0,1]. 표본 부족 셀은 NaN (0으로 채우지 않는다)."""
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    r = g.rank(pct=True, method="average")
    return r.where(cnt >= min_n).astype("float32")


CELL_LADDER = ("cell", "cell_l2", "cell_l3")

def col(df: pd.DataFrame, name: str, default: float = np.nan) -> pd.Series:
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자.

    ★ df.get("x") 는 컬럼이 없으면 None 을 반환한다. 그러면 `None + Series` 나 `None.abs()`
      로 TypeError/AttributeError 가 나는데, 하필 그 상황(= 특정 데이터 소스가 통째로 비어
      해당 계정 컬럼이 아예 생성되지 않은 경우)은 실데이터 실행에서 가장 흔하다.
      키 미입력·API 한도 소진·소급 데이터 없음 전부 이 경로로 들어온다.
      그래서 피처 계산부는 df.get 대신 반드시 이 함수를 쓴다.
    """
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")

def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)

def nanmean_cols(df: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    """가용 축만으로 평균. 결측을 0으로 채우지 않는다 (§7.3 지시)."""
    use = [c for c in cols if c in df.columns]
    if not use:
        return pd.Series(np.nan, index=df.index)
    return df[use].astype("float64").mean(axis=1, skipna=True)

def hac_tstat(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량. 월간 초과수익 시계열의 유의성에 쓴다(R2/R3)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return (np.nan, np.nan)
    mu = x.mean()
    e = x - mu
    L = lags if lags is not None else int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    L = max(0, min(L, n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    se = math.sqrt(var / n)
    return (float(mu), float(mu / se))

def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg. 강건성 검정을 여러 번 돌리면 다중검정 보정이 필요하다."""
    p = np.asarray(pvals, dtype=float)
    ok = np.isfinite(p)
    out = np.zeros_like(p, dtype=bool)
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[order[:kmax + 1]] = True
    return out

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C+  ARC 전용 헬퍼 — 분기 시간축 / 횡단면 직교화 / IC                                  ║
# ║                                                                                          ║
# ║  ARC-TXT 의 기본 시간 단위는 '월'이 아니라 '분기'다. 이 블록이 그 축을 정의한다.           ║
# ║  월 기준 헬퍼(month_range 등)를 실수로 쓰면 리밸런싱 횟수가 3배가 되고 회전율·비용이       ║
# ║  전부 틀어지므로, 분기 함수는 이름을 완전히 다르게 지어 혼동을 원천 차단한다.              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def rebal_dates(start, end) -> pd.DatetimeIndex:
    """§4 리밸런싱일: 매년 3/1, 6/1, 9/1, 12/1 중 백테스트 구간 안쪽만.

    ★ 달력일 그대로 둔다. '직전 거래일로 당기기'는 가격 패널이 있어야 가능한데,
      유니버스 구축이 가격보다 먼저 필요하므로 여기서는 달력일을 기준점으로 삼고
      체결가만 '해당일 이후 첫 거래일의 시가'로 잡는다(41_backtest).
    """
    s, e = as_ts(start), as_ts(end)
    if s is None or e is None:
        return pd.DatetimeIndex([])
    out = []
    for y in range(s.year - 1, e.year + 2):
        for m in ARC_REBAL_MONTHS:
            t = pd.Timestamp(year=y, month=m, day=1)
            if s <= t <= e:
                out.append(t)
    return pd.DatetimeIndex(sorted(out))

def qlabel(ts) -> str:
    """Timestamp → 'YYYYQn'. 분기 라벨은 문자열로만 다룬다(정수 인코딩은 연말 경계에서 깨진다)."""
    t = as_ts(ts)
    if t is None:
        return ""
    return f"{t.year}Q{(t.month - 1) // 3 + 1}"

def qshift(qs: str, k: int) -> str:
    """'2019Q3', -1 → '2019Q2' / '2019Q3', -4 → '2018Q3'."""
    m = re.match(r"^(\d{4})Q([1-4])$", str(qs or ""))
    if not m:
        return ""
    y, q = int(m.group(1)), int(m.group(2))
    n = y * 4 + (q - 1) + k
    return f"{n // 4}Q{n % 4 + 1}"

def prev_quarter_of(asof) -> str:
    """리밸일 시점에 '이미 종료된' 직전 분기 라벨.

    ★ 3/1 리밸일에 2019Q1(1~3월) 을 쓰면 아직 끝나지 않은 분기를 쓰는 것이므로 미래누수다.
      3/1 → 2018Q4, 6/1 → 2019Q1, 9/1 → 2019Q2, 12/1 → 2019Q3.
    """
    t = as_ts(asof)
    if t is None:
        return ""
    return qlabel(t - pd.offsets.QuarterEnd(1)) if t.day <= 15 else qlabel(t)

def xsec_z_arc(P: pd.DataFrame, name_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    """ARC 셀 사다리(cell → cell_all)를 적용한 횡단면 z-score.

    ★ 왜 사다리가 필요한가: 섹터에 종목이 30개 있어도 '그 지표를 실제로 관측한' 종목은
      5개뿐일 수 있다(D1 은 문서 파싱 실패, D3 는 섹터 편향). 셀 크기만 보고 판단하면
      z 가 전부 NaN 이 되고, 그 축은 아무 신호도 못 내면서 로그에는 아무것도 남지 않는다.
    """
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(pd.Series(name_or_series), errors="coerce")
    v = pd.Series(np.asarray(v, dtype="float64"), index=P.index)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    if "cell_all" in P.columns and z.isna().any():
        z = z.where(z.notna(), xsec_z(v, P["cell_all"], min_n))
    return z.astype("float32")

def winsor_series(s, p: float = 0.01) -> pd.Series:
    """백분위 기준 상하위 p 윈저라이즈. ±inf 를 먼저 NaN 으로 바꾼다(§C5 와 동일한 이유)."""
    v = pd.to_numeric(pd.Series(s), errors="coerce").replace([np.inf, -np.inf], np.nan)
    if v.notna().sum() < 5 or not (0 < p < 0.5):
        return v
    lo, hi = v.quantile(p), v.quantile(1 - p)
    return v.clip(lower=lo, upper=hi)


OLS_MIN_OBS_PER_PARAM = 5      # 횡단면 회귀 자유도 하한 (관측수 / 파라미터수)

def ols_resid_np(y: np.ndarray, X: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    """단일 횡단면 OLS 잔차. 절편은 호출자가 넣지 않아도 여기서 붙인다.

    ★ 섹터 더미까지 넣으면 X 가 특이행렬이 되기 쉽다(완전공선성). lstsq 는 조용히
      이상한 계수를 낼 수 있으므로 ridge 를 아주 작게 걸어 수치적으로 안정화한다.
      ridge 는 잔차를 거의 바꾸지 않는다(1e-8 은 스케일 대비 무시 가능).
    """
    y = np.asarray(y, dtype=np.float64).ravel()
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    n = len(y)
    if n == 0:
        return np.full(0, np.nan)
    A = np.column_stack([np.ones(n), X])
    ok = np.isfinite(y) & np.isfinite(A).all(axis=1)
    out = np.full(n, np.nan)
    #   (상세 근거는 커밋 로그 참조)
    if ok.sum() < max(A.shape[1] + 3, OLS_MIN_OBS_PER_PARAM * A.shape[1]):
        return out
    Ao, yo = A[ok], y[ok]
    G = Ao.T @ Ao
    G = G + ridge * np.maximum(1.0, np.trace(G) / max(G.shape[0], 1)) * np.eye(G.shape[0])
    try:
        beta = np.linalg.solve(G, Ao.T @ yo)
    except np.linalg.LinAlgError:
        beta = np.linalg.pinv(G) @ (Ao.T @ yo)
    out[ok] = yo - Ao @ beta
    return out


XSEC_RESID_DOF: List[dict] = []      # 직교화 자유도 진단(셀별 관측수/파라미터수)

def xsec_resid(y, X: pd.DataFrame, cells) -> pd.Series:
    """셀(=기간)별 횡단면 OLS 잔차. §5.3 직교화의 실행부.

    ★ 결측 처리 규칙이 중요하다. 통제변수가 결측이면 그 행은 '직교화되지 않은 원값'이
      되어선 안 된다 — 그러면 통제 안 된 알파가 그대로 섞인다. 통제변수 결측은
      호출자가 기간 중앙값으로 대체한 뒤 넘기고, y 가 결측인 행만 NaN 으로 남긴다.
    """
    yv = pd.to_numeric(pd.Series(y), errors="coerce").replace([np.inf, -np.inf], np.nan)
    idx = yv.index
    Xv = X.reindex(idx).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    g = pd.Series(cells).reindex(idx).astype(object).fillna("__NA__")
    out = pd.Series(np.nan, index=idx, dtype="float64")
    # ★ 셀 가드는 '셀 전체 행수'가 아니라 **y 가 실제로 관측된 행수**로 봐야 한다.
    #   전자는 분기 총 행수(≈1000)라 항상 통과하고, 실제 회귀는 dTONE 이 있는 20~60행으로
    #   돌아간다. 진단용으로 셀별 (관측수/파라미터수) 비를 남긴다.
    XSEC_RESID_DOF.clear()
    n_par = int(Xv.shape[1]) + 1
    for gk, pos in g.groupby(g, observed=True).groups.items():
        sl = list(pos)
        n_obs = int((yv.loc[sl].notna() & Xv.loc[sl].notna().all(axis=1)).sum())
        XSEC_RESID_DOF.append({"cell": str(gk), "n_obs": n_obs, "n_param": n_par,
                               "ratio": (n_obs / n_par) if n_par else np.nan})
        if len(sl) < 12:                     # 표본이 너무 적으면 회귀가 잡음을 학습한다
            continue
        out.loc[sl] = ols_resid_np(yv.loc[sl].to_numpy(), Xv.loc[sl].to_numpy())
    _thin = [d for d in XSEC_RESID_DOF if 0 < d["n_obs"] and d["ratio"] < OLS_MIN_OBS_PER_PARAM]
    if _thin:
        LOG.warn(f"직교화 자유도 부족으로 잔차를 만들지 못한 셀 {len(_thin)}개 "
                 f"(관측/파라미터 비 < {OLS_MIN_OBS_PER_PARAM}). 해당 기간의 ΔTONE_resid 는 "
                 f"결측입니다 — 적합오차를 신호로 쓰지 않기 위한 의도된 결측입니다. "
                 f"최소 비율 {min(d['ratio'] for d in _thin):.1f} · 파라미터 {n_par}개")
    return out.astype("float32")

def measurable_ret(R: pd.DataFrame, key: str = "ret") -> pd.Series:
    """성과·유의성 계산에 쓸 수익률 시계열. **측정 불가 분기를 일관되게 제외한다.**

    ★ perf_stats 는 R[R["measurable"]] 로 마지막 리밸일(전 종목 fwd_ret 결측)을 빼는데,
      어블레이션의 초과수익·p(HAC)·§9.2-(8) BH-FDR 판정은 원본 R 을 그대로 썼다. 그러면
      §9.2-(6) 표의 '초과수익·p(HAC)' 열과 성과표(CAGR/Sharpe)가 서로 다른 39 vs 40 분기
      표본에서 나온다. 사전등록된 유의성 판정이 정의와 어긋나면 안 되므로 한 곳으로 모은다.
    """
    if R is None or len(R) == 0:
        return pd.Series(dtype="float64")
    Rm = R[R["measurable"].astype(bool)] if "measurable" in R.columns else R
    if len(Rm) == 0:
        Rm = R
    return Rm.set_index("asof")[key]

def newey_west_p(x, lags: Optional[int] = None) -> float:
    """HAC t → 양측 p-value. scipy 가 없으면 정규근사로 폴백한다."""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 8:
        return float("nan")
    _, t = hac_tstat(a, lags=lags)
    if not np.isfinite(t):
        return float("nan")
    try:
        from scipy import stats as _st
        return float(2.0 * (1.0 - _st.t.cdf(abs(t), df=max(1, len(a) - 1))))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2.0)))

def info_coef(sig, fwd, groups) -> Tuple[float, float, int]:
    """기간별 Spearman IC 의 (평균, IC-IR, 기간수).

    ★ 전체를 한 번에 상관내면 안 된다. 기간 간 수준 차이가 상관을 만들어내기 때문이다
      (예: 특정 분기에 전 종목 신호와 수익이 동시에 높으면 가짜 IC 가 생긴다).
      횡단면 IC 를 기간별로 구한 뒤 시계열 평균/표준편차로 IR 을 만든다.
    """
    s = pd.to_numeric(pd.Series(sig), errors="coerce")
    f = pd.to_numeric(pd.Series(fwd), errors="coerce").reindex(s.index)
    g = pd.Series(groups).reindex(s.index).astype(object)
    ics = []
    for _, pos in g.groupby(g, observed=True).groups.items():
        sl = list(pos)
        a, b = s.loc[sl], f.loc[sl]
        m = a.notna() & b.notna()
        if int(m.sum()) < 20:
            continue
        try:
            r = float(a[m].rank().corr(b[m].rank()))
        except Exception:
            continue
        if np.isfinite(r):
            ics.append(r)
    if len(ics) < 3:
        return (float("nan"), float("nan"), len(ics))
    arr = np.asarray(ics, dtype=float)
    mu = float(arr.mean())
    sd = float(arr.std(ddof=1))
    # ★ 반환 2번째 값은 **t통계량**이다(IR × √n). IC-IR 의 표준 정의는 mean/std 이므로
    #   같은 숫자를 'IC-IR' 로 표기하면 분기 40개에서 √40 = 6.32배 부풀려진 값을 읽게 된다
    #   (진짜 IR 0.25 → 표에 1.58). 기간 수가 다른 팔끼리는 부풀림 배수까지 달라져 순위가
    #   뒤집힌다. 소비 측은 info_coef_full() 로 IR 과 t 를 분리해 받는다.
    return (mu, (mu / sd * math.sqrt(len(arr))) if sd > 0 else float("nan"), len(arr))

def info_coef_full(sig, fwd, groups) -> Tuple[float, float, float, int]:
    """(평균 IC, IC-IR = mean/std, t통계량 = IR×√n, 기간수). 표에 쓸 때는 이쪽을 쓴다."""
    mu, tstat, n = info_coef(sig, fwd, groups)
    ir = (tstat / math.sqrt(n)) if (n > 0 and np.isfinite(tstat)) else float("nan")
    return (mu, ir, tstat, n)

def assert_no_dup_cols_arc(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 에서 예외 없이 의미가 바뀐다(df[c] 가 DataFrame 이 된다).
    조용히 지나가면 최악이므로 발생 지점에서 즉시 세운다."""
    if df is None or len(df) == 0:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — "
                           f"pandas 연산의 의미가 바뀌므로 여기서 중단합니다.")
    return df

def ensure_cols(df: pd.DataFrame, cols: Sequence[str], fill=np.nan) -> pd.DataFrame:
    """계약 컬럼 보장. 수집이 얼마나 실패하든 패널의 컬럼 집합은 항상 같아야 한다.

    ★ 그래야 '어떤 실행에선 있고 어떤 실행엔 없는' 축이 사라지고, 결측이 조용히가 아니라
      표로 드러난다. 하류에서 KeyError 로 죽는 대신 결측률이 보고된다.
    """
    for c in cols:
        if c not in df.columns:
            df[c] = fill
    return df

def arc_kd_lag(df: pd.DataFrame, days: int = None) -> pd.DataFrame:
    """§4 시점 규약 — DART 파생 테이블의 knowledge_date 에 T+거래일 지연을 적용한다.
    ★ 왜 필요한가: `_knowledge_from_rcept` 는 접수일자(rcept_dt) 를 그대로 knowledge_date 로
    """
    d = int(days if days is not None else globals().get("ARC_DART_LAG_DAYS", 1))
    if df is None or len(df) == 0 or "knowledge_date" not in getattr(df, "columns", []):
        return df
    out = df.copy()
    out["knowledge_date"] = as_ts_series(out["knowledge_date"]) + pd.Timedelta(days=d)
    return out
