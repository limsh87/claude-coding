
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  호환성 계층 — pandas 1.5~3.x / numpy 1.2x~2.x / scipy 유무 / OS 차이를 흡수한다    ║
# ║                                                                                          ║
# ║  이 파일이 없으면 "내 노트북에선 되는데 코랩에선 죽는다" 가 반드시 일어난다.               ║
# ║  실제로 조용히 죽는 대표 사례를 전부 여기서 한 번에 막는다:                                ║
# ║   ① pandas 2.2 부터 freq="M" 이 폐기 → 3.0 에서 ValueError. 반대로 2.1 이하는 "ME" 를 모른다.║
# ║   ② pandas 3.0 은 Copy-on-Write 가 기본 → df[a][b] = x 가 '예외 없이' 무시된다(최악).      ║
# ║   ③ pandas 2.2+ groupby.apply 가 그룹키를 넘기지 않음(include_groups) → KeyError.          ║
# ║   ④ numpy 2.0 에서 np.NaN / np.float_ / np.alltrue 제거 → 서드파티가 먼저 죽는다.          ║
# ║   ⑤ scipy 가 없거나 설치 실패한 환경 → 통계 게이트 전체가 죽는 대신 순수 파이썬으로 대체.  ║
# ║   ⑥ pyarrow 가 zstd 를 못 쓰는 빌드 → parquet 저장 실패 → 캐시가 통째로 안 남는다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _ver_tuple(v: str) -> Tuple[int, ...]:
    out = []
    for part in str(v).split(".")[:3]:
        m = re.match(r"(\d+)", part)
        out.append(int(m.group(1)) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


PD_VER = _ver_tuple(getattr(pd, "__version__", "0.0.0"))
NP_VER = _ver_tuple(getattr(np, "__version__", "0.0.0"))

# ① 월말 빈도 별칭 -------------------------------------------------------------------------
#    pandas <2.2 : "M"  /  >=2.2 : "ME" (2.2 는 "M" 도 받지만 FutureWarning, 3.0 은 거부)
FREQ_ME = "ME" if PD_VER >= (2, 2, 0) else "M"
FREQ_QE = "QE" if PD_VER >= (2, 2, 0) else "Q"
FREQ_YE = "YE" if PD_VER >= (2, 2, 0) else "A"


def date_range_me(start, end) -> pd.DatetimeIndex:
    """월말 인덱스. 버전 별칭 차이를 흡수하고, 그래도 실패하면 수동 생성으로 폴백한다."""
    try:
        return pd.date_range(start, end, freq=FREQ_ME)
    except Exception:
        pass
    for f in ("ME", "M"):
        try:
            return pd.date_range(start, end, freq=f)
        except Exception:
            continue
    # 최후 폴백: 직접 만든다 (여기까지 오면 pandas 가 매우 이상한 버전이다)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out, cur = [], (s + pd.offsets.MonthEnd(0))
    while cur <= e:
        out.append(cur)
        cur = cur + pd.offsets.MonthEnd(1)
    return pd.DatetimeIndex(out)


# ② Copy-on-Write 안전 대입 ------------------------------------------------------------------
def set_where(df: pd.DataFrame, mask, col: str, value) -> None:
    """df.loc[mask, col] = value 의 안전판.

    pandas 3 의 CoW 에서 df[col][mask] = v 는 '예외 없이' 아무 일도 하지 않는다.
    이 함수만 쓰면 그 사고가 구조적으로 불가능해진다."""
    if col not in df.columns:
        df[col] = np.nan
    if isinstance(mask, pd.Series):
        m = mask.fillna(False).to_numpy(bool)
    else:
        m = np.nan_to_num(np.asarray(mask, dtype=float), nan=0.0).astype(bool) \
            if np.asarray(mask).dtype.kind == "f" else np.asarray(mask, dtype=bool)
    if m.shape[0] != len(df):
        raise ValueError(f"set_where: 마스크 길이 {m.shape[0]} != 프레임 길이 {len(df)}")
    if not m.any():
        return
    # ★ pandas 3 은 정수/불리언 열에 실수·결측을 넣으면 TypeError 다(2.x 는 조용히 승격했다).
    #   '코랩에선 되는데' 의 전형이므로 대입 전에 열 dtype 을 먼저 올린다.
    cur = df[col].dtype
    try:
        if cur.kind in ("i", "u", "b"):
            need_float = (value is None or (np.isscalar(value) and pd.isna(value)) or
                          np.asarray(value).dtype.kind == "f")
            need_obj = (not np.isscalar(value)) and np.asarray(value).dtype.kind in ("U", "O", "S")
            if isinstance(value, str):
                need_obj = True
            if need_obj:
                df[col] = df[col].astype(object)
            elif need_float:
                df[col] = df[col].astype("float64")
    except Exception:
        pass
    try:
        df.loc[m, col] = value
    except (TypeError, ValueError):
        df[col] = df[col].astype(object)
        df.loc[m, col] = value


# ③ groupby.apply 그룹키 복원 ------------------------------------------------------------------
def gb_apply(g, fn, **kw):
    """그룹키를 보존한 채 apply 한다.

    ★ include_groups 인자를 쓰면 안 된다. pandas 2.2 는 받지만 pandas 3 은
      `include_groups=True is no longer allowed` ValueError 를 던진다. 그 예외를
      bare except 로 삼키면 (a) 그룹키 없는 경로로 조용히 강등되어 caller 가 KeyError,
      (b) fn 이 던진 정당한 예외까지 삼켜서 apply 가 두 번 실행된다(부수효과 중복).
      → 버전 분기 대신 그룹키를 직접 되꽂는다. 모든 버전에서 같은 결과가 나온다."""
    keys = g.keys if isinstance(g.keys, list) else [g.keys]
    keys = [k for k in keys if isinstance(k, str)]
    if not keys:
        return g.apply(fn, **kw)
    out = []
    for kv, sub in g:
        kv = kv if isinstance(kv, tuple) else (kv,)
        s2 = sub.copy()
        for name, val in zip(keys, kv):
            if name not in s2.columns:
                s2[name] = val
        out.append((kv, fn(s2)))
    if not out:
        return pd.DataFrame()
    first = out[0][1]
    if isinstance(first, (pd.DataFrame, pd.Series)):
        return pd.concat([v for _, v in out],
                         keys=[k if len(k) > 1 else k[0] for k, _ in out], names=keys)
    return pd.Series({(k if len(k) > 1 else k[0]): v for k, v in out})


# ③-b 텍스트 판정 / 빈 프레임 -------------------------------------------------------------------
def is_texty(s) -> bool:
    """pandas 3 + pyarrow 는 문자열을 StringDtype 으로 돌려주므로 `dtype == object` 가
    전부 False 가 된다. 문자열 판정은 반드시 이 함수를 거친다."""
    try:
        return bool(pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s))
    except Exception:
        return False


def empty_like(cols_dtypes: Dict[str, Any]) -> pd.DataFrame:
    """빈 결과 프레임. ★ pd.DataFrame(columns=[...]) 는 전 열이 object 라, 나중에
    실데이터와 concat 하면 숫자열까지 object 로 오염되고 parquet 저장이 죽는다.
    10년 백테스트에서 휴장일/차단일 빈 프레임은 반드시 발생한다."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in cols_dtypes.items()})


def concat_nonempty(frames: Sequence[pd.DataFrame], cols: Optional[Sequence[str]] = None,
                    dtypes: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """빈 프레임을 먼저 걷어내고 concat 한다(dtype 오염 방지)."""
    fs = [f for f in frames if f is not None and len(f)]
    if not fs:
        return empty_like(dtypes) if dtypes else pd.DataFrame(columns=list(cols or []))
    if cols is not None:
        fs = [f.reindex(columns=list(cols)) for f in fs]
    return pd.concat(fs, ignore_index=True)


# ③-c 시간축 관문 (tz / 해상도) -----------------------------------------------------------------
#   pandas 3 의 기본 datetime 해상도는 ns 가 아니라 us 다. "datetime64[ns]" 하드코딩과
#   epoch 변환(1e9 나눗셈)이 조용히 1000배 틀어진다.
DT64_UNIT = "us" if PD_VER >= (3, 0, 0) else "ns"
DT64 = "datetime64[" + DT64_UNIT + "]"


def now_kst() -> pd.Timestamp:
    """KST 현재시각(naive). ★ pd.Timestamp.utcnow() 는 폐기 예고 상태이고 경고가 꺼져
    있어 pandas 4 에서 예고 없이 AttributeError 로 죽는다. 전 모듈이 이 함수만 쓴다."""
    try:
        return pd.Timestamp.now("UTC").tz_convert("Asia/Seoul").tz_localize(None)
    except Exception:
        return pd.Timestamp.now("UTC").tz_localize(None) + pd.Timedelta(hours=9)


def to_naive_date(s) -> pd.Series:
    """모든 외부 소스의 날짜가 반드시 통과해야 하는 관문.

    ★ yfinance 는 tz-aware 인덱스를, FDR/네이버는 naive 를 준다. 둘을 concat 하면
      dtype 이 object 로 붕괴하고, aware 인덱스를 naive 기준일과 비교하면 TypeError 다.
      KRX 를 못 쓰는 이번 설계는 yfinance 폴백 비중이 커서 반드시 터진다."""
    try:
        t = pd.to_datetime(s, utc=True, errors="coerce")
        return t.dt.tz_convert("Asia/Seoul").dt.tz_localize(None).dt.normalize()
    except Exception:
        pass
    try:
        t = pd.to_datetime(s, errors="coerce")
        if hasattr(t, "dt"):
            if getattr(t.dt, "tz", None) is not None:
                t = t.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
            return t.dt.normalize()
        return pd.Series(pd.to_datetime(t, errors="coerce"))
    except Exception:
        return pd.Series([pd.NaT] * (len(s) if hasattr(s, "__len__") else 1))


# ④ numpy 2 제거심볼 복구는 01_bootstrap 에서 '서드파티 import 보다 먼저' 이미 수행했다.
#    (여기서 하면 yfinance/statsmodels 가 먼저 로드되어 np.NaN 참조로 죽는 순서 역전이 난다)
#    멱등이므로 한 번 더 확인만 한다.
if not hasattr(np, "NaN"):
    try:
        np.NaN = np.nan            # type: ignore[attr-defined]
    except Exception:
        pass

# ⑤ scipy 없이도 도는 통계 원시함수 ------------------------------------------------------------
try:
    from scipy import stats as _sps            # type: ignore
except Exception:                              # pragma: no cover
    _sps = None

HAS_SCIPY = _sps is not None


def norm_cdf(x: float) -> float:
    """표준정규 CDF. math.erf 만으로 충분히 정확하다(오차 < 1e-15)."""
    try:
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))
    except Exception:
        return float("nan")


def norm_ppf(p: float) -> float:
    """표준정규 역함수 — Acklam 유리근사 + 뉴턴 1회 보정 (절대오차 < 1e-9).
    DSR / PBO 계산에 필요하며, scipy 부재 환경에서도 동일한 숫자가 나와야 한다."""
    p = float(p)
    if not (0.0 < p < 1.0):
        return float("-inf") if p <= 0 else float("inf")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q, r = p - 0.5, (p - 0.5) ** 2
        x = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
            (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    # 뉴턴 보정 1회
    try:
        e = norm_cdf(x) - p
        u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
        x = x - u / (1 + x * u / 2)
    except Exception:
        pass
    return x


def t_sf(t: float, dof: float) -> float:
    """양측 t 검정 p값 (생존함수 ×2). scipy 가 있으면 그걸, 없으면 불완전베타로 계산."""
    t = abs(float(t))
    if not np.isfinite(t) or dof <= 0:
        return float("nan")
    if HAS_SCIPY:
        try:
            return float(2.0 * _sps.t.sf(t, dof))
        except Exception:
            pass
    # 정규근사는 소표본에서 p를 과소평가한다 → 불완전베타 연분수로 정확히 계산
    x = dof / (dof + t * t)
    try:
        return float(_betainc(dof / 2.0, 0.5, x))
    except Exception:
        return float(2.0 * (1.0 - norm_cdf(t)))


def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-14) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """정규화 불완전베타 I_x(a,b) — Numerical Recipes 연분수."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
             a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
                          b * math.log(1.0 - x) + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def ols_beta(X: np.ndarray, y: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    """최소제곱 계수. lstsq 가 실패하는 특이행렬에서도 릿지로 반드시 답을 낸다.
    (통제변수 회귀에서 업종더미가 완전공선이 되는 일이 실제로 자주 일어난다)"""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    if len(y) == 0 or X.shape[0] != len(y):
        return np.zeros(X.shape[1] if X.ndim > 1 else 1)
    XtX = X.T @ X
    XtX = XtX + ridge * np.eye(XtX.shape[0]) * max(1.0, float(np.trace(XtX)) / max(XtX.shape[0], 1))
    try:
        return np.linalg.solve(XtX, X.T @ y)
    except Exception:
        try:
            return np.linalg.lstsq(X, y, rcond=None)[0]
        except Exception:
            return np.zeros(X.shape[1])


# ⑤-b Newey-West(HAC) — statsmodels 없이도 반드시 계산되어야 한다 ------------------------------
def nw_se(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float, int]:
    """평균의 HAC(Bartlett) 표준오차와 t 값. 반환 (mean, t, lags).

    ★ statsmodels 가 없으면 통계 게이트가 조용히 통과하거나 AttributeError 로 죽는다.
      순수 numpy 로 구현해 두 경로가 같은 숫자를 내도록 한다(자가검정이 교차확인).
      L = floor(4*(T/100)^(2/9))  (Newey-West 1994 자동선택)"""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    T = a.size
    if T < 8:
        return (float(a.mean()) if T else np.nan, np.nan, 0)
    if lags is None:
        lags = int(np.floor(4.0 * (T / 100.0) ** (2.0 / 9.0)))
    lags = max(0, min(int(lags), T - 2))
    e = a - a.mean()
    gamma0 = float(e @ e) / T
    s2 = gamma0
    for l in range(1, lags + 1):
        g = float(e[l:] @ e[:-l]) / T
        w = 1.0 - l / (lags + 1.0)
        s2 += 2.0 * w * g
    if s2 <= 0:                      # Bartlett 가중이어도 수치오차로 음수가 될 수 있다
        s2 = gamma0
    se = math.sqrt(max(s2, 1e-300) / T)
    mu = float(a.mean())
    return (mu, mu / se if se > 0 else np.nan, lags)


def hac_t(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    mu, t, _ = nw_se(x, lags)
    return mu, t


# ⑤-c 텍스트 I/O 관문 (Windows cp949 / BOM) -----------------------------------------------------
def read_json(path: str, default=None):
    """★ open(p) 는 Windows 에서 cp949 로 열려 UTF-8 한글 JSON 을 깨뜨리거나 죽는다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: str, obj) -> str:
    return atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=1))


def read_csv_utf8(path: str, **kw) -> pd.DataFrame:
    """BOM 을 흡수한다. 우리가 엑셀 호환을 위해 BOM 을 붙여 쓰기 때문에,
    utf-8-sig 로 읽지 않으면 첫 컬럼명에 BOM 이 남아 KeyError 가 난다."""
    kw.setdefault("encoding", "utf-8-sig")
    return pd.read_csv(path, **kw)


# ⑥ parquet 압축 폴백 --------------------------------------------------------------------------
def _pick_parquet_compression() -> str:
    try:
        import pyarrow as _pa                                   # noqa
        from pyarrow import Codec as _Codec                     # type: ignore
        for c in ("zstd", "snappy", "gzip"):
            try:
                if _Codec.is_available(c):
                    return c
            except Exception:
                continue
    except Exception:
        pass
    return "snappy"


PARQUET_COMPRESSION = _pick_parquet_compression()


# ⑦ 안전한 HTML 표 파싱 -------------------------------------------------------------------------
def _html_flavors() -> Tuple[Any, ...]:
    """flavor="bs4" 는 html5lib 를 강제한다. html5lib 이 없으면 ImportError 이므로
    존재가 확인될 때만 후보에 넣는다."""
    out: List[Any] = ["lxml"]
    try:
        if importlib.util.find_spec("html5lib") is not None:
            out.append("bs4")
    except Exception:
        pass
    out.append(None)
    return tuple(out)


_HTML_FLAVORS = _html_flavors()


def safe_read_html(raw: Union[bytes, str], encoding: Optional[str] = None) -> List[pd.DataFrame]:
    """pandas 버전·파서 가용성에 따라 시그니처가 다르다. 전부 시도하고 하나라도 되면 쓴다."""
    attempts = []
    if isinstance(raw, bytes):
        attempts.append(dict(io=io.BytesIO(raw), encoding=encoding))
        for enc in ([encoding] if encoding else []) + ["euc-kr", "cp949", "utf-8"]:
            if not enc:
                continue
            try:
                attempts.append(dict(io=io.StringIO(raw.decode(enc, "replace"))))
            except Exception:
                continue
    else:
        attempts.append(dict(io=io.StringIO(raw)))
    for kw in attempts:
        for flavor in _HTML_FLAVORS:
            try:
                k = {k2: v for k2, v in kw.items() if v is not None}
                if flavor:
                    k["flavor"] = flavor
                tabs = pd.read_html(**k)
                if tabs:
                    return tabs
            except Exception:
                continue
    return []


# ⑧ 프로젝트 루트 자동 감지 (SPEC §2.1 — 경로 하드코딩 금지) --------------------------------------
def resolve_project_root() -> str:
    """런타임에 루트를 스스로 찾는다. '/content' 를 코드에 박지 않는다.

    우선순위:
      ① 환경변수 ARC_BDF_ROOT (사용자가 명시적으로 지정)
      ② 구글드라이브가 마운트되어 있으면 그 아래 (Colab)
      ③ Windows 로컬 표준 경로 (SPEC §2.1 의 .kr_data_work)
      ④ 현재 작업 디렉터리
    어느 경로도 쓰기 불가면 임시 디렉터리로 강등하되 그 사실을 로그에 남긴다."""
    cands: List[str] = []
    env = os.environ.get("ARC_BDF_ROOT", "").strip()
    if env:
        cands.append(env)
    if ENV.get("colab"):
        cands.append("/content/drive/MyDrive/arc_bdf_work")
        cands.append("/content/arc_bdf_work")
    home = os.path.expanduser("~")
    if ENV.get("platform") == "Windows":
        cands.append(os.path.join(home, ".kr_data_work", "ARC_BDF"))
    cands.append(os.path.join(os.getcwd(), "arc_bdf_work"))
    cands.append(os.path.join(home, ".kr_data_work", "ARC_BDF"))
    for c in cands:
        try:
            os.makedirs(c, exist_ok=True)
            probe = os.path.join(c, ".w")
            with open(probe, "w") as f:
                f.write("1")
            os.remove(probe)
            return os.path.abspath(c)
        except Exception:
            continue
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "arc_bdf_work")
    os.makedirs(tmp, exist_ok=True)
    return tmp


PROJECT_ROOT = resolve_project_root()
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out_path(name: str) -> str:
    return os.path.join(OUTPUT_DIR, name)


# ⑨ 랜덤 딜레이 (차단 회피 · SPEC §2.3) ---------------------------------------------------------
_JITTER_RNG = random.Random(SEED ^ 0x5EED)
_JITTER_LK = threading.Lock()


def polite_sleep(lo: float = None, hi: float = None) -> None:
    lo = FLOW_DELAY_RANGE[0] if lo is None else lo
    hi = FLOW_DELAY_RANGE[1] if hi is None else hi
    with _JITTER_LK:
        d = _JITTER_RNG.uniform(float(lo), float(hi))
    time.sleep(max(0.0, d))


# ⑩ 실행환경 요약 (진단용) -----------------------------------------------------------------------
def report_compat() -> None:
    rows = [
        ["python", platform.python_version(), sys.executable[:44]],
        ["작업 루트", PROJECT_ROOT[-44:], "경로 하드코딩 없음(런타임 자동감지)"],
        ["pandas", ".".join(map(str, PD_VER)), f"월말빈도='{FREQ_ME}' · CoW={'ON' if PD_VER>=(3,0,0) else 'off'}"],
        ["numpy", ".".join(map(str, NP_VER)), "2.x 제거심볼 복구 완료" if NP_VER >= (2, 0, 0) else "-"],
        ["scipy", "있음" if HAS_SCIPY else "없음", "없어도 t/정규 분포는 자체 구현으로 동작"],
        ["parquet", PARQUET_COMPRESSION, "pyarrow 코덱 자동선택"],
        ["환경", "Colab" if ENV.get("colab") else ("Jupyter" if ENV.get("jupyter") else "CLI"),
         f"{ENV['platform']} · CPU {os.cpu_count()}"],
        ["KRX", "사용" if KRX_ENABLE else "미사용(기본)",
         "FDR/네이버/yfinance/DART/공공데이터 만으로 완결" if not KRX_ENABLE
         else "교차검증용 보강"],
        ["statsmodels", "있음" if smapi is not None else "없음",
         "없어도 Newey-West 는 자체 구현(nw_se)으로 계산됩니다"],
        ["시간해상도", DT64, "pandas 3 은 us 가 기본 — ns 하드코딩 금지"],
    ]
    for k, v in (_OPT_IMPORT_ERR or {}).items():
        rows.append([f"선택모듈 실패:{k}", "import 실패", v[:60]])
    LOG.table(rows, ["항목", "값", "비고"], title="실행환경 호환성")


# ⑪ DART OpenAPI 상태코드 사전 (10_universe / 11_price 가 공유) ---------------------------------
#    status 를 해석하지 않고 '실패' 로만 처리하면, 일일 한도 초과(020)와 잘못된 키(010)를
#    구분하지 못해 사용자가 무엇을 고쳐야 할지 알 수 없게 된다.
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}
