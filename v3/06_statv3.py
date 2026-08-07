

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  v3 통계 원시연산 — TP 조립 / 셀 정규화 / 롤링 적률 / 런타임 계측                    ║
# ║                                                                                          ║
# ║  이 블록은 v3 에서 **바뀐 것만** 담는다. 바뀐 이유가 전부 실측 사고이므로 주석에          ║
# ║  "무엇이 어떻게 터졌는가"를 남긴다.                                                       ║
# ║    §6.5  TP 부호버그 → clip(z,0) 강제                                                     ║
# ║    §7    groupby.apply 금지 → 이중계산 폴백                                               ║
# ║    §6.4  스트라이드 창 쌓기 금지 → 롤링 적률 닫힌해                                        ║
# ║    §2    모든 단계를 계측한다. 추측 금지(C10).                                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── §2 런타임 계측 (C10) ────────────────────────────────────────────────────────────────────
RUNTIME_LOG: List[dict] = []
_RUNTIME_LK = threading.RLock()


@contextmanager
def Stage(name: str, budget_min: Optional[float] = None):
    """with Stage("M0.ingest_bulk"): ... 형태. 종료 시 RUNTIME_LOG 에 append.

    PIPE.stage 와 역할이 다르다. PIPE.stage 는 '실패 지점 국소화'가 목적이고,
    이건 '§2 예산표 대비 실측'이 목적이다. 둘 다 필요하다 — 어느 단계가 예산의 몇 배를
    썼는지는 실패와 무관하게 알아야 하고, 그게 v2 가 16~40시간으로 폭발한 뒤 얻은 교훈이다.
    """
    t0 = time.time()
    rss0 = _rss_mb()
    err = ""
    try:
        yield
    except BaseException as e:                                  # noqa
        err = f"{type(e).__name__}: {str(e)[:120]}"
        raise
    finally:
        dt = time.time() - t0
        rec = {"stage": name, "sec": dt, "min": dt / 60.0,
               "budget_min": budget_min, "rss_mb": _rss_mb(), "d_rss_mb": _rss_mb() - rss0,
               "err": err}
        with _RUNTIME_LK:
            RUNTIME_LOG.append(rec)
        if budget_min and dt / 60.0 > budget_min * 1.5:
            LOG.warn(f"[C10] '{name}' 이 예산 {budget_min:.0f}분의 "
                     f"{dt/60.0/budget_min:.1f}배({dt/60.0:.1f}분)를 썼습니다. "
                     f"중단하지 않고 계속 진행합니다 — 마지막 런타임 표에서 확인하세요.")


def _rss_mb() -> float:
    """상주 메모리(MB). 리눅스·macOS·Windows 전부에서 동작한다.

    ★ 예전엔 /proc 과 resource 에만 의존해 **Windows 에서 전부 NaN** 이었다. 런타임 표의
      RSS 열이 통째로 '-' 로 나와 메모리 감사가 무의미해진다 — 하필 Colab 아닌 로컬
      주피터가 메모리 압박을 가장 먼저 받는 환경이다. psutil 은 선택 의존이므로
      없어도 되는 경로를 셋 다 갖춘다.
    """
    try:
        with open("/proc/self/statm") as f:                       # Linux
            return int(f.read().split()[1]) * (os.sysconf("SC_PAGE_SIZE") / 1e6)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:                                                       # Windows: PSAPI
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = _PMC()
            c.cb = ctypes.sizeof(_PMC)
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.WorkingSetSize / 1e6
        except Exception:
            pass
    try:
        import psutil                                              # 있으면 가장 정확
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        pass
    try:
        import resource                                            # macOS/BSD 폴백(최대치)
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / 1e6 if sys.platform == "darwin" else ru / 1e3
    except Exception:
        return float("nan")


def report_runtime_v3(total_budget_min: float = 240.0):
    if not RUNTIME_LOG:
        return
    LOG.banner("런타임 감사 (C10) — §2 예산표 대비 실측",
               "추측하지 않는다. 어느 단계가 예산을 얼마나 썼는지 실측으로만 판정한다.")
    rows, tot = [], 0.0
    for r in RUNTIME_LOG:
        tot += r["sec"]
        bud = r.get("budget_min")
        verdict = "—"
        if bud:
            ratio = (r["min"] / bud) if bud > 0 else 0
            verdict = "✔ 예산 내" if ratio <= 1.0 else f"❗ {ratio:.1f}배 초과"
        rows.append([_trunc(r["stage"], 34), f"{r['sec']:8.2f}", f"{r['min']:6.2f}",
                     (f"{bud:.0f}분" if bud else "-"), verdict,
                     f"{r['rss_mb']:,.0f}" if np.isfinite(r["rss_mb"]) else "-",
                     f"{r['d_rss_mb']:+,.0f}" if np.isfinite(r["d_rss_mb"]) else "-",
                     _trunc(r["err"], 26)])
    rows.append(["── 합계 ──", f"{tot:8.2f}", f"{tot/60:6.2f}",
                 f"{total_budget_min:.0f}분",
                 "✔ 예산 내" if tot / 60 <= total_budget_min
                 else "❗ 초과 — 검사를 줄이지 말고 구조를 고칠 것(§11-8)", "", "", ""])
    LOG.table(rows, ["단계", "실측(초)", "실측(분)", "예산", "판정", "RSS(MB)", "ΔRSS", "예외"],
              ["l", "r", "r", "r", "l", "r", "r", "l"])


# ── 셀 폴백 사다리를 탄 z-score ─────────────────────────────────────────────────────────────
def xsec_z_fb(v: pd.Series, cells: pd.Series, cells_fb: Optional[Sequence[pd.Series]] = None,
              min_n: int = CELL_MIN_N, tag: str = "") -> pd.Series:
    """셀 내 z. 표본이 부족한 셀은 상위 셀로 내려간다.

    ★ 이 폴백이 없으면 조용히, 그리고 치명적으로 망가진다. 셀 = (연월 × 산업중분류 × 규모3단계)
      는 실데이터에서 셀당 중앙 크기가 한 자릿수인 구간이 많다. min_n 미달 셀을 전부 NaN 으로
      떨어뜨리면 **TP 와 U 가 거의 전부 결측**이 되고, 그러면 E 는 소수 종목만 남긴 채로
      계산되며 백테스트는 아무 예외 없이 '보유 1종목' 포트폴리오를 만든다.
      (실측: 폴백 없이 합성 80종목×36개월에서 TP 유효 관측이 2,880행 중 114행이었다)
    """
    out = xsec_z(v, cells, min_n=min_n)
    fine_ok = out.notna()
    for fb in (cells_fb or []):
        if not out.isna().any():
            break
        out = out.where(out.notna(), xsec_z(v, fb, min_n=min_n))
    if tag:
        obs = pd.to_numeric(v, errors="coerce").notna()
        n_obs = int(obs.sum())
        if n_obs:
            # 폴백 사용 = 관측은 있는데 1단계 셀에서는 못 냈고 상위 셀에서 냈다
            CELL_FALLBACK_STATS[f"z:{tag}"] += int((obs & ~fine_ok & out.notna()).sum())
            CELL_FALLBACK_STATS[f"z:{tag}__n"] += n_obs
    return out


# ── §6.5 TP 조립 — 부호버그 수정 (v3 최우선 교정) ───────────────────────────────────────────
def tp(a: pd.Series, b: pd.Series, cells: pd.Series,
       cells_fb: Optional[Sequence[pd.Series]] = None, min_n: int = CELL_MIN_N) -> pd.Series:
    """트레이드오프 쌍 = max(z(개선),0) × max(z(대가회피),0).

    ★ v2 사양은 z(a)*z(b) 였다. 횡단면 z 이므로 유니버스의 약 25%가 양쪽 음수이고,
      그 종목들이 음수×음수=양수로 상위 분위를 차지했다. 즉 '매출 급감 + 회전 악화'가
      '매출 증가 + 회전 유지'와 같은 점수를 받았다. 예외는 나지 않는다 — 순위만 조용히 틀린다.

    v3 의 의미론: 개선이 없거나(za<=0) 대가를 치렀으면(zb<=0) 정확히 0.
      "제약이 풀렸다"는 주장은 두 조건이 동시에 성립할 때만 참이므로 이게 정의에 맞다.

    ★ 결측 전파 규칙: 한쪽이라도 NaN 이면 결과도 NaN 이다. 0 으로 채우면
      "대가를 안 치렀다"는 거짓 주장이 된다(관측이 없는 것과 대가가 0인 것은 다르다).
      clip 은 NaN 을 보존하므로 아래 구현은 자동으로 이 규칙을 만족한다.
    """
    za = xsec_z_fb(a, cells, cells_fb, min_n=min_n)
    zb = xsec_z_fb(b, cells, cells_fb, min_n=min_n)
    out = za.clip(lower=0.0) * zb.clip(lower=0.0)
    return out.astype("float32")


def tp_rank(a: pd.Series, b: pd.Series, cells: pd.Series,
            cells_fb: Optional[Sequence[pd.Series]] = None,
            min_n: int = CELL_MIN_N) -> pd.Series:
    """대안 정의: rank_pct(a) × rank_pct(b).  [0,1] 구간이라 부호 문제가 정의상 소멸한다.

    §6.5 는 둘 중 무엇을 쓰든 R5 절제에서 두 방식을 비교해 리포트에 명시하라고 요구한다.
    clip 방식과 다른 점: clip 은 '평균 이하'를 전부 0 으로 뭉개지만 rank 는 순서를 보존한다.
    → clip 은 더 선택적(상위 25%만 양수), rank 는 더 연속적. 어느 쪽이 옳은지는 실측 문제다.
    """
    def _r(v):
        out = xsec_rank_pct(v, cells, min_n=min_n)
        for fb in (cells_fb or []):
            if not out.isna().any():
                break
            out = out.where(out.notna(), xsec_rank_pct(v, fb, min_n=min_n))
        return out
    return (_r(a) * _r(b)).astype("float32")


def tp_dispatch(mode: str, a: pd.Series, b: pd.Series, cells: pd.Series,
                cells_fb: Optional[Sequence[pd.Series]] = None,
                min_n: int = CELL_MIN_N) -> pd.Series:
    if mode == "rank":
        return tp_rank(a, b, cells, cells_fb, min_n)
    if mode == "signed":
        # R5 전용 — v2 의 부호버그를 그대로 재현해 '무슨 일이 벌어졌는가'를 실측으로 보여준다
        return tp_signed_product(xsec_z_fb(a, cells, cells_fb, min_n),
                                 xsec_z_fb(b, cells, cells_fb, min_n))
    return tp(a, b, cells, cells_fb, min_n)


# ── §7 셀 정규화 — 벡터화 폴백 ──────────────────────────────────────────────────────────────
CELL_FALLBACK_STATS: Counter = Counter()


def cell_rank(df: pd.DataFrame, col_or_series, keys: Sequence[str],
              fallback_keys: Sequence[str], min_n: int = CELL_MIN_N,
              tag: str = "") -> pd.Series:
    """셀 내 백분위 랭크. 표본이 부족한 셀은 상위 셀로 폴백한다.

    ★ 이중계산이 조건분기보다 100배 빠르다. groupby.apply 로 셀마다 파이썬 함수를 부르면
      v2 에서 720,000회 호출에 24분이 걸렸다. fine/coarse 를 둘 다 통째로 계산한 뒤
      np.where 로 고르는 게 총 연산량은 두 배지만 전부 C 레벨이라 압도적으로 싸다.

    ★ 판정 기준은 '셀 크기'가 아니라 '그 센서의 유효 관측 수'다. 셀에 종목이 30개 있어도
      그 센서를 관측한 종목은 5개뿐일 수 있고(신규상장·비DART·계정 미매칭), 그때
      크기만 보고 통과시키면 5개짜리 랭크가 만들어져 백분위가 무의미해진다.
    """
    v = (pd.to_numeric(df[col_or_series], errors="coerce") if isinstance(col_or_series, str)
         else pd.to_numeric(col_or_series, errors="coerce"))
    v = v.replace([np.inf, -np.inf], np.nan)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=df.index, dtype="float32")

    def _key(ks):
        # 카테고리 dtype 을 그대로 groupby 하면 observed=False 기본값에서 카티션 폭발이 난다.
        # (date × industry × size 조합이 미관측분까지 전부 만들어져 메모리를 먹는다)
        s = None
        for k in ks:
            c = df[k].astype(str) if k in df.columns else pd.Series("NA", index=df.index)
            s = c if s is None else (s + "\x1f" + c)
        return (s if s is not None else pd.Series("ALL", index=df.index)).to_numpy()

    kf, kc = _key(keys), _key(fallback_keys)
    gf = v.groupby(kf, observed=True, dropna=False)
    gc = v.groupby(kc, observed=True, dropna=False)
    fine = gf.rank(pct=True, method="average")
    coarse = gc.rank(pct=True, method="average")
    n_fine = gf.transform("count")
    n_coarse = gc.transform("count")

    out = np.where(n_fine.to_numpy() >= min_n, fine.to_numpy(), coarse.to_numpy())
    out = np.where(n_coarse.to_numpy() >= min_n, out, np.nan)   # 상위 셀조차 부족하면 결측
    used_fallback = int(((n_fine < min_n) & (n_coarse >= min_n) & v.notna()).sum())
    n_obs = int(v.notna().sum())
    if n_obs:
        CELL_FALLBACK_STATS[tag or "?"] += used_fallback
        CELL_FALLBACK_STATS[f"{tag or '?'}__n"] += n_obs
    return pd.Series(out, index=df.index, dtype="float32")


def report_cell_fallback(threshold: float = 0.30):
    """§7: 폴백 발생 비율을 로깅하고 30%를 넘으면 셀 정의를 재검토한다."""
    tags = sorted({k[:-3] for k in CELL_FALLBACK_STATS if k.endswith("__n")})
    if not tags:
        return
    rows, worst = [], 0.0
    for t in tags:
        n = CELL_FALLBACK_STATS.get(f"{t}__n", 0)
        f = CELL_FALLBACK_STATS.get(t, 0)
        r = f / max(n, 1)
        worst = max(worst, r)
        rows.append([t, f"{n:,}", f"{f:,}", f"{100*r:.1f}%",
                     "✔" if r <= threshold else "❗ 셀 정의 재검토"])
    LOG.table(rows, ["센서", "유효관측", "폴백 사용", "폴백률", "판정"],
              ["l", "r", "r", "r", "l"],
              title=f"셀 폴백 감사 (§7) — 폴백률 {threshold:.0%} 초과 시 셀 정의를 재검토")
    if worst > threshold:
        LOG.warn(f"최대 폴백률 {100*worst:.0f}% 가 기준({threshold:.0%})을 넘습니다. "
                 f"셀이 너무 잘게 쪼개져 있다는 뜻입니다 — 산업 분류 단위를 넓히거나 "
                 f"size_bucket 단계를 줄이세요. 지금 상태로는 '셀 내 정규화'가 "
                 f"사실상 '전체 정규화'로 퇴화한 종목이 그만큼 됩니다.")


# ── §6.4 롤링 회귀 — 적률 방식 ──────────────────────────────────────────────────────────────
def rolling_ols_moment(Y: np.ndarray, X: np.ndarray, window: int,
                       ridge: float = 1e-8) -> np.ndarray:
    """(N,T) y 와 (N,T,K) X 에 대해 길이 W 롤링 OLS 의 '창 마지막 시점 잔차'를 반환.

    ★ §6.4 가 금지하는 것: np.lib.stride_tricks 로 창을 쌓는 방식. (N, T-W+1, W, K) 배열이
      실체화되면서 2,600종목 × 2,400일 × 120창 × 2변수 = 8GB 를 잡아 OOM 으로 죽는다.
    ★ §6.4 가 금지하는 것 ②: rolling(W).apply(파이썬 콜백). 종목·시점마다 파이썬 호출이라
      15분짜리가 3시간이 된다.
    ★ v3 방식: 교차곱 컬럼을 먼저 만들고 rolling sum 으로 XtX/Xty 원소를 직접 누적한다.
      메모리는 O(N·T·K²) 가 아니라 창을 실체화하지 않으므로 O(N·T·K²) 의 '누적합' 뿐이고,
      역행렬은 K×K(보통 2×2) 소행렬 배치라 사실상 공짜다.

    반환: (N, T) 잔차. 창이 안 차거나 결측이 섞이면 NaN.
    """
    Y = np.asarray(Y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    N, T = Y.shape
    K = X.shape[2]
    out = np.full((N, T), np.nan, dtype=np.float64)
    if T < window or window < K + 2:
        return out

    ok = np.isfinite(Y) & np.isfinite(X).all(axis=2)          # (N,T)
    Yc = np.where(ok, Y, 0.0)
    Xc = np.where(ok[:, :, None], X, 0.0)

    def _rsum(A):
        """마지막 축 T 에 대한 길이 window 이동합. 누적합 차분 — O(N·T) 이고 창을 안 만든다."""
        cs = np.cumsum(A, axis=1)
        r = np.empty_like(cs)
        r[:, :window - 1] = np.nan
        r[:, window - 1] = cs[:, window - 1]
        r[:, window:] = cs[:, window:] - cs[:, :-window]
        return r

    n_ok = _rsum(ok.astype(np.float64))                        # (N,T) 창 내 유효 관측 수
    XtX = np.empty((N, T, K, K), dtype=np.float64)
    for i in range(K):
        for j in range(i, K):
            s = _rsum(Xc[:, :, i] * Xc[:, :, j])
            XtX[:, :, i, j] = s
            if j != i:
                XtX[:, :, j, i] = s
    Xty = np.empty((N, T, K), dtype=np.float64)
    for i in range(K):
        Xty[:, :, i] = _rsum(Xc[:, :, i] * Yc)

    full = (n_ok >= window - 1e-9)                             # 창 전체가 유효할 때만 푼다
    # 정규방정식은 조건수가 원 설계행렬의 제곱이다. 스케일에 비례하는 리지를 반드시 넣는다.
    tr = np.einsum("ntkk->nt", XtX)
    lam = ridge * np.maximum(1.0, np.abs(tr) / max(K, 1))
    XtX = XtX + lam[:, :, None, None] * np.eye(K)[None, None]

    A = np.where(full[:, :, None, None], XtX, np.eye(K)[None, None])
    b = np.where(full[:, :, None], Xty, 0.0)
    try:
        beta = np.linalg.solve(A, b[..., None])[..., 0]        # (N,T,K)
    except np.linalg.LinAlgError:
        beta = np.einsum("ntkl,ntl->ntk", np.linalg.pinv(A), b)
    resid = Yc - np.einsum("ntk,ntk->nt", Xc, beta)
    out = np.where(full & ok, resid, np.nan)
    return out


def rolling_sum_min_valid(s: pd.Series, window: int, min_valid: int) -> pd.Series:
    """rolling(window).sum() 인데 '유효 관측이 min_valid 미만이면 NaN'.

    pandas 의 min_periods 는 '창 안의 non-NaN 개수'를 세지만, 우리가 원하는 건
    '창이 실제로 window 만큼 채워졌는가'다. 상장 직후나 거래정지 구간에서
    3개짜리 합을 120일 누적으로 부르면 d3 가 그 종목만 체계적으로 작아진다.
    """
    v = pd.to_numeric(s, errors="coerce")
    tot = v.rolling(window, min_periods=1).sum()
    cnt = v.notna().rolling(window, min_periods=1).sum()
    return tot.where(cnt >= min_valid)
