# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-P  런타임 위생 — 출력 폭주 차단 · 소스 건강도 · 진행률 스로틀 · 디스크                 ║
# ║                                                                                          ║
# ║  실측 로그에서 확인된 두 가지 '조용한 살인자'를 여기서 구조적으로 막는다.                  ║
# ║                                                                                          ║
# ║  ① IOPub message rate exceeded                                                           ║
# ║     yfinance 는 실패할 때마다 stderr 로 3~4줄을 뱉는다("possibly delisted", "1 Failed      ║
# ║     download", "no timezone found"). 실패 1,901종목 × 2접미사(.KS/.KQ) × 3줄 ≈ 1.1만 줄.  ║
# ║     주피터 커널은 초당 메시지 수를 제한하므로 출력이 통째로 정지하고, 그 뒤로는 진행상황을 ║
# ║     볼 수 없게 된다. 로그가 안 보이는 것보다 나쁜 건, 사용자가 '멈췄다'고 판단해 커널을    ║
# ║     죽이는 것이다. → 서드파티 출력을 OS 파일디스크립터 수준에서 봉인한다.                  ║
# ║     (logging 레벨 조정만으로는 못 막는다. C 확장과 print() 는 logging 을 거치지 않는다)    ║
# ║                                                                                          ║
# ║  ② 죽은 소스에 계속 요청하기                                                              ║
# ║     소스가 통째로 죽었는데도 종목마다 4개 소스를 전부 시도하면, 실패 1,901종목이           ║
# ║     7,604번의 헛된 왕복이 된다. → 연속 실패를 세어 소스 단위로 회로를 끊는다.              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TQDM_MININTERVAL = 1.0          # 진행률 갱신 최소 간격(초). 주피터 IOPub 보호.
_QUIET_LOCK = threading.Lock()

# ★ 리허설(가짜 네트워크) 중에는 캐시에 절대 쓰지 않는다.
#   이 플래그가 없으면 리허설이 만들어낸 합성 데이터가 공용 인덱스에 저장되고,
#   이후 실수집이 "그 달은 이미 있다"며 영원히 건너뛴다. 기존 캐시 훼손과 같으므로
#   (절대 1원칙 위반) persist() 안에서 구조로 막는다. run_rehearsal() 이 켜고 끈다.
_REHEARSAL = False


def silence_thirdparty() -> None:
    """서드파티 라이브러리의 수다를 끈다. 한 번만 부르면 된다(멱등).

    끄는 대상과 이유:
      · yfinance      : 실패마다 stderr 3~4줄. 우리는 실패를 표로 집계하므로 원문이 필요 없다.
      · urllib3       : 재시도·SSL 경고. http_get 이 이미 재시도를 관리한다.
      · pymupdf/fitz  : 'Could not get FontBBox' 같은 폰트 경고를 PDF 페이지마다 뱉는다.
      · pandas        : FutureWarning 이 수집 루프 안에서 반복 출력된다.
    끄지 않는 것: 우리 코드의 LOG. 진단 정보는 전부 살아 있어야 한다.
    """
    if globals().get("_SILENCED"):
        return
    globals()["_SILENCED"] = True
    try:
        import logging as _lg
        for nm in ("yfinance", "urllib3", "urllib3.connectionpool", "requests",
                   "peewee", "fitz", "pdfminer", "pdfplumber", "PIL", "matplotlib",
                   "charset_normalizer", "asyncio", "fsspec"):
            lg = _lg.getLogger(nm)
            lg.setLevel(_lg.CRITICAL)
            lg.propagate = False
    except Exception:
        pass
    try:
        warnings.filterwarnings("ignore")
    except Exception:
        pass
    try:                                     # urllib3 의 InsecureRequestWarning 등
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
    # pymupdf 는 로거가 아니라 C 레벨에서 stderr 로 직접 쓴다 → 전역 스위치가 따로 있다
    try:
        import fitz as _fz
        if hasattr(_fz, "TOOLS") and hasattr(_fz.TOOLS, "mupdf_display_errors"):
            _fz.TOOLS.mupdf_display_errors(False)
        if hasattr(_fz, "TOOLS") and hasattr(_fz.TOOLS, "mupdf_display_warnings"):
            _fz.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    os.environ.setdefault("PYTHONWARNINGS", "ignore")


class quiet_fds:
    """stdout/stderr 를 OS 파일디스크립터 수준에서 /dev/null 로 돌린다.

    ★ contextlib.redirect_stderr 로는 부족하다. 그건 파이썬의 sys.stderr 객체만 바꾸므로
      C 확장(pymupdf), 서브프로세스, os.write(2, ...) 는 그대로 통과한다. yfinance 는
      내부적으로 print 와 logging 을 섞어 쓰고 멀티스레드 다운로더가 따로 뱉는다.
      fd 를 통째로 갈아끼우는 것만이 확실하다.

    ★ 우리 LOG 는 봉인 구간 밖에서만 쓴다. 봉인 중에는 진행률(tqdm)도 안 보이므로
      호출부는 '한 덩어리 작업'만 감싸고, 결과 요약은 반드시 밖에서 출력한다.

    비활성 조건: SACN_NO_QUIET=1 (디버깅용 탈출구) 또는 fd 복제가 불가능한 환경.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = bool(enabled) and not os.environ.get("SACN_NO_QUIET")
        self._saved: List[Tuple[int, int]] = []
        self._null = -1

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        try:
            self._null = os.open(os.devnull, os.O_WRONLY)
            for fd in (1, 2):
                self._saved.append((fd, os.dup(fd)))
                os.dup2(self._null, fd)
        except Exception:
            self._restore()                  # 반쯤 성공한 상태를 남기지 않는다
            self.enabled = False
        return self

    def _restore(self):
        for fd, saved in self._saved:
            try:
                os.dup2(saved, fd)
                os.close(saved)
            except Exception:
                pass
        self._saved = []
        if self._null >= 0:
            try:
                os.close(self._null)
            except Exception:
                pass
            self._null = -1

    def __exit__(self, *exc):
        self._restore()
        return False


def free_gb_safe(path: str) -> float:
    """윈도우에는 os.statvfs 가 없다. shutil.disk_usage 는 3개 OS 전부에서 동작한다.

    (실측 로그의 '여유 공간 nan GB' 가 이것이다. 표시만 깨진 게 아니라,
     PDF 수집 전 용량 점검이 무력화되어 디스크가 꽉 찰 때까지 못 멈춘다.)
    """
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        try:
            p = os.path.dirname(os.path.abspath(path)) or "."
            return shutil.disk_usage(p).free / 1e9
        except Exception:
            return float("nan")


class SourceHealth:
    """소스 단위 회로차단기. 죽은 소스에 계속 두드리는 것을 구조로 막는다.

    실측: 가격 1,901종목이 전 소스 실패 → 종목마다 pykrx→fdr→naver→yfinance 를
    다 돌았다. pykrx 는 애초에 설치조차 안 됐고 yfinance 는 0건이었는데도.
    연속 실패가 임계치를 넘으면 그 소스는 이번 실행에서 은퇴시킨다(다음 실행에서 부활).
    """

    def __init__(self, threshold: int = 0):
        self.threshold = int(threshold or CIRCUIT_BREAKER_FAILS)
        self._lk = threading.Lock()
        self.ok: Counter = Counter()
        self.bad: Counter = Counter()
        self.streak: Counter = Counter()
        self.tripped: Dict[str, int] = {}

    def alive(self, src: str) -> bool:
        return src not in self.tripped

    def mark(self, src: str, good: bool) -> None:
        with self._lk:
            if good:
                self.ok[src] += 1
                self.streak[src] = 0
            else:
                self.bad[src] += 1
                self.streak[src] += 1
                if self.streak[src] >= self.threshold and src not in self.tripped:
                    self.tripped[src] = self.bad[src]

    def live_sources(self, order: Sequence[str]) -> List[str]:
        return [s for s in order if self.alive(s)]

    def rows(self) -> List[List[str]]:
        out = []
        for s in sorted(set(list(self.ok) + list(self.bad))):
            n_ok, n_bad = self.ok[s], self.bad[s]
            rate = safe_div(n_ok, n_ok + n_bad, 0.0)
            out.append([s, f"{n_ok:,}", f"{n_bad:,}", f"{rate:.0%}",
                        "차단됨" if s in self.tripped else "정상"])
        return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  절대원칙 — 신규 수집물은 예외 없이 드라이브 캐시에 남고, 세션과 무관하게 재호출된다       ║
# ║                                                                                          ║
# ║  "다음부터 잘 하겠다"는 규율로는 지켜지지 않는다. 저장 경로를 하나로 강제하고,             ║
# ║  '받았는데 저장 안 된 것'을 실행 끝에 기계적으로 찾아내야 지켜진다.                        ║
# ║                                                                                          ║
# ║   note_new_data(...)  네트워크에서 새로 받은 순간 등록한다 (영수증)                        ║
# ║   persist(...)        유일한 저장 경로. 공용/전용 인덱스에 쓰고 원장에 기록한다            ║
# ║   cache_audit()       등록됐는데 저장 안 된 것을 찾아낸다 → 경고가 아니라 실패로 취급       ║
# ║   cache_manifest()    다음 세션이 '이름을 몰라도' 찾을 수 있게 목록을 남긴다               ║
# ║                                                                                          ║
# ║  ★ 리허설(가짜 네트워크) 중에는 저장을 금지한다. 합성 데이터가 공용 인덱스에 섞이면        ║
# ║    이후 실수집이 "그 달은 이미 있다"며 영원히 건너뛴다 — 기존 캐시 훼손과 같다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
CACHE_LEDGER: List[dict] = []
_NEW_DATA: Dict[str, dict] = {}
_CACHE_LK = threading.Lock()


def note_new_data(name: str, n_rows: int, scope: str = "shared",
                  domain: str = "", source: str = "") -> None:
    """'방금 네트워크에서 새로 받았다'를 등록한다. 저장 의무가 여기서 발생한다.

    ★ 리허설 중에는 등록하지 않는다. 리허설은 가짜 데이터를 만들고 persist() 가 그것의
      저장을 '의도적으로' 거부하므로, 등록해 두면 감사가 매번 위반을 외친다. 진짜 위반과
      구분되지 않는 경고는 곧 무시되는 경고이고, 그러면 감사 자체가 무력해진다.
      (리허설이 무엇을 만들었는지는 CACHE_LEDGER 의 '리허설-저장금지' 행에 그대로 남는다)
    """
    if not n_rows or globals().get("_REHEARSAL"):
        return
    with _CACHE_LK:
        cur = _NEW_DATA.setdefault(name, {"name": name, "scope": scope, "domain": domain,
                                          "source": source, "rows": 0, "persisted": False})
        cur["rows"] += int(n_rows)


def persist(name: str, df: Any, *, scope: str = "shared", domain: str = "",
            source: str = "", note: str = "") -> bool:
    """모든 신규 수집물의 유일한 저장 경로. 성공 여부를 돌려주고 원장에 남긴다.

    scope="shared"  → 다른 전략·다른 세션이 그대로 재사용 (가격·리포트원장·애널리스트원장…)
    scope="private" → 이 전략 고유 (링크행렬·신호·백테스트 산출)
    """
    rows = int(len(df)) if hasattr(df, "__len__") else 0
    if globals().get("_REHEARSAL"):
        with _CACHE_LK:
            CACHE_LEDGER.append({"dataset": name, "scope": scope, "rows": rows,
                                 "action": "리허설-저장금지", "note": note or "합성데이터"})
        return False
    V = globals().get("VAULT")
    if V is None or rows == 0:
        with _CACHE_LK:
            CACHE_LEDGER.append({"dataset": name, "scope": scope, "rows": rows,
                                 "action": "건너뜀", "note": note or
                                 ("빈 결과" if rows == 0 else "VAULT 미초기화")})
        return False
    ok = True
    try:
        V.put_table(name, df, scope=scope, domain=domain or "misc", source=source or name)
    except Exception as e:                                   # noqa
        ok = False
        LOG.error(f"캐시 저장 실패 [{scope}/{name}] {type(e).__name__}: {e} — "
                  f"이번 실행에서 받은 데이터가 드라이브에 남지 않습니다. "
                  f"디스크 여유({free_gb_safe(getattr(V, 'root', '.')):.1f}GB)와 "
                  f"드라이브 동기화 상태를 확인하세요.")
    with _CACHE_LK:
        CACHE_LEDGER.append({"dataset": name, "scope": scope, "rows": rows,
                             "action": "저장" if ok else "저장실패", "note": note or source})
        if name in _NEW_DATA:
            _NEW_DATA[name]["persisted"] = ok
    if ok:
        PIPE.io("OUT", "DRIVE", f"{scope}/{name}", df, source=source or name)
    return ok


def cache_recall(name: str, scope: str = "shared") -> Optional[pd.DataFrame]:
    """세션 무관 재호출. 지정 스코프에 없으면 반대 스코프까지 찾아본다.

    (Vault.get_table 이 이미 교차 스코프 폴백을 하지만, 여기서 원장에 '재사용'을 남긴다 —
     그래야 '이번 실행이 무엇을 새로 받았고 무엇을 재사용했는지'가 표 하나로 증명된다)
    """
    V = globals().get("VAULT")
    if V is None:
        return None
    try:
        d = V.get_table(name, scope=scope)
    except Exception:
        d = None
    n = int(len(d)) if d is not None else 0
    with _CACHE_LK:
        CACHE_LEDGER.append({"dataset": name, "scope": scope, "rows": n,
                             "action": "재사용" if n else "캐시없음", "note": "recall"})
    return d if n else None


def cache_audit() -> Tuple[pd.DataFrame, List[str]]:
    """등록됐는데 저장되지 않은 신규 수집물을 찾아낸다. (원장표, 위반목록)"""
    with _CACHE_LK:
        led = pd.DataFrame(CACHE_LEDGER) if CACHE_LEDGER else pd.DataFrame(
            columns=["dataset", "scope", "rows", "action", "note"])
        viol = [f"{v['scope']}/{k} ({v['rows']:,}행)"
                for k, v in _NEW_DATA.items() if not v["persisted"] and v["rows"]]
    return led, viol


def cache_manifest() -> Dict[str, Any]:
    """다음 세션이 이름을 몰라도 찾을 수 있도록 캐시 목록을 남긴다.

    ★ '재호출 가능'을 말로만 두지 않는다. 공용/전용 인덱스에 무엇이 몇 행 있는지,
      어떤 컬럼인지, 언제 갱신됐는지를 매니페스트로 박아 둔다. 다른 전략은 이 파일만
      읽으면 VAULT.get_table(name, scope) 로 그대로 꺼내 쓸 수 있다.
    """
    V = globals().get("VAULT")
    out: Dict[str, Any] = {"strategy": STRATEGY_ID, "build": BUILD_VERSION,
                           "root": getattr(V, "root", ""), "datasets": []}
    if V is None:
        return out
    # ★ 반드시 flush 후 강제 재적재한다. 인덱스는 지연 캐시라, 그냥 load_index() 하면
    #   '이번 실행이 저장한 것'이 하나도 안 보인다. 그러면 매니페스트가 빈 채로 나가고
    #   다음 세션은 "캐시에 아무것도 없다"고 오해한다 — 재호출 보장이 통째로 무너진다.
    try:
        V.flush()
    except Exception:
        pass
    for scope in ("shared", "private"):
        try:
            idx = V.load_index(scope, force=True)
        except Exception:
            try:
                idx = V.load_index(scope)
            except Exception:
                continue
        if idx is None or not len(idx) or "key" not in idx.columns:
            continue
        # ★ 실제 인덱스 스키마에 맞춘다. 'kind'/'rows' 같은 컬럼은 존재하지 않는다 —
        #   그 이름으로 읽으면 매니페스트가 조용히 0행짜리 껍데기가 되고, 다음 세션은
        #   "캐시에 아무것도 없다"고 오해한다. 행수는 extra(JSON) 안에 들어 있다.
        sub = idx.copy()
        if "subtype" in sub.columns:
            sub = sub[sub["subtype"].astype(str) == "table"]
        if "key" not in sub.columns or not len(sub):
            continue
        # 같은 테이블이 여러 번 갱신됐으면 마지막 등록만 남긴다
        ts_col = next((c for c in ("collected_at", "ts", "updated") if c in sub.columns), None)
        if ts_col:
            sub = sub.sort_values(ts_col)
        sub = sub.drop_duplicates("key", keep="last")
        for r in sub.to_dict("records"):
            rows, cols = 0, []
            ex = r.get("extra")
            if isinstance(ex, str) and ex.strip().startswith("{"):
                try:
                    j = json.loads(ex)
                    rows = int(pd.to_numeric(j.get("rows", 0), errors="coerce") or 0)
                    cols = list(j.get("cols", []))[:40]
                except Exception:
                    pass
            elif isinstance(ex, dict):
                rows = int(pd.to_numeric(ex.get("rows", 0), errors="coerce") or 0)
                cols = list(ex.get("cols", []))[:40]
            key = str(r.get("key", ""))
            out["datasets"].append({
                "name": key, "scope": scope, "domain": str(r.get("domain", "")),
                "rows": rows, "cols": cols,
                "bytes": int(pd.to_numeric(r.get("bytes", 0), errors="coerce") or 0),
                "updated": str(r.get(ts_col, "")) if ts_col else "",
                "source": str(r.get("source", "")),
                "recall": f'VAULT.get_table("{key}", scope="{scope}")',
            })
    out["n_datasets"] = len(out["datasets"])
    out["how_to_recall"] = (
        "다른 세션/다른 전략에서 이 캐시를 그대로 쓰려면: 같은 루트를 GDRIVE_ROOT 로 지정하고 "
        "VAULT.get_table(name, scope) 를 호출하면 됩니다. 이름은 위 datasets[].name 그대로입니다.")
    return out


def report_cache_ledger() -> pd.DataFrame:
    """실행이 무엇을 재사용하고 무엇을 새로 저장했는지 한 표로 증명한다."""
    led, viol = cache_audit()
    if len(led):
        agg = (led.groupby(["action", "scope"], as_index=False)
                  .agg(datasets=("dataset", "nunique"), rows=("rows", "sum")))
        LOG.table([[r.action, r.scope, f"{int(r.datasets):,}", f"{int(r.rows):,}"]
                   for r in agg.itertuples(index=False)],
                  ["동작", "인덱스", "데이터셋", "행수"], ["l", "l", "r", "r"],
                  title="드라이브 캐시 원장 (절대원칙: 신규 수집물은 전부 저장·재호출 가능)")
        saved = led[led["action"] == "저장"]
        if len(saved):
            LOG.table([[r.dataset, r.scope, f"{int(r.rows):,}"]
                       for r in saved.sort_values("rows", ascending=False)
                                     .head(25).itertuples(index=False)],
                      ["저장된 데이터셋", "인덱스", "행수"], ["l", "l", "r"],
                      title="이번 실행에서 드라이브에 새로 저장된 것")
    if viol:
        LOG.error("절대원칙 위반 — 새로 수집했는데 드라이브에 저장되지 않은 데이터가 있습니다:\n  · "
                  + "\n  · ".join(viol) +
                  "\n  이 데이터는 다음 세션에서 재호출할 수 없습니다. "
                  "디스크 여유·드라이브 동기화·쓰기 권한을 확인하세요.")
    else:
        LOG.ok("절대원칙 점검 통과 — 이번 실행의 신규 수집물이 전부 인덱스에 등록되었습니다.")
    return led


def _resolve_workers(source: str, hard_cap: int = 24) -> int:
    """QPS 상한을 못 넘길 워커 수를 계산한다.

    ★ 실측 병목의 정체: RATE_LIMIT_QPS['krx']=2.0 인데 FDR 호출이 limiter('krx') 를
      썼다. FDR 은 KRX 서버를 부르지도 않는다. 워커를 12개로 늘려도 전역 토큰버킷이
      초당 2건으로 묶으므로 5,398종목 ÷ 2 = 2,699초. 실측 2,875초와 정확히 일치한다.
      워커 수는 병목이 아니었고 버킷 배정이 병목이었다.
      → 버킷은 '실제로 때리는 호스트' 기준으로 나누고, 워커는 그 QPS 를 채울 만큼만 둔다.
      요청 1건의 왕복을 평균 0.7초로 보면 필요한 워커 ≈ QPS × 0.7 (최소 2).
    """
    qps = float(RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
    want = int(math.ceil(qps * 0.9)) + 1
    return max(2, min(hard_cap, want, max(2, N_WORKERS_IO * 3)))
