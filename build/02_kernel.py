

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-B  커널 — 로깅 / 스테이지 / 데이터흐름 원장 / 에러 국소화 / 런타임 계측(C10)          ║
# ║                                                                                          ║
# ║  이 블록의 목적은 단 하나:  "어디서 터졌고, 무슨 데이터가 어디로 흘렀는가"를               ║
# ║  스크롤 없이 한 화면에서 보이게 만드는 것.                                                ║
# ║                                                                                          ║
# ║  · 모든 연산은 STAGE 컨텍스트 안에서만 수행한다.                                          ║
# ║  · 모든 데이터 입출력은 FLOW 원장에 기록한다. (행수·바이트·소스·PIT컬럼 유무)              ║
# ║  · 예외는 잡아서 "스테이지ID + 입출력 스냅샷 + 한글 진단 힌트"와 함께 재출력한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_T0_PROCESS = time.time()


def _dw(s: str) -> int:
    """한글/한자 폭 2칸을 반영한 표시 너비. 표 정렬이 깨지지 않게 하는 유일한 방법."""
    w = 0
    for ch in str(s):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _pad(s: str, n: int, align: str = "l") -> str:
    s = str(s)
    gap = max(0, n - _dw(s))
    if align == "r":
        return " " * gap + s
    if align == "c":
        return " " * (gap // 2) + s + " " * (gap - gap // 2)
    return s + " " * gap


def _trunc(s: str, n: int) -> str:
    s = str(s).replace("\n", " ")
    if _dw(s) <= n:
        return s
    out = ""
    for ch in s:
        if _dw(out) + _dw(ch) > n - 1:
            return out + "…"
        out += ch
    return out


class _Log:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self, min_level: str = "INFO"):
        self.min = self.LEVELS[min_level]
        self.ctx: List[str] = []
        self.buffer: List[str] = []
        self.lock = threading.RLock()

    def _emit(self, level: str, msg: str, icon: str = ""):
        if self.LEVELS[level] < self.min:
            return
        el = time.time() - _T0_PROCESS
        stamp = f"{int(el // 60):02d}:{el % 60:05.2f}"
        with self.lock:
            #  scope 도 잠금 안에서 읽는다 — 메인 스레드가 finally 에서 ctx.pop() 하는
            #  사이에 백그라운드 줄이 엉뚱한 스테이지 이름을 달고 나가면 안 된다.
            scope = ("/".join(self.ctx))[-34:]
            line = f"[{stamp}] {_pad(scope, 34)} {icon}{msg}"
            self.buffer.append(line)
            _safe_print(line, flush=True)

    def debug(self, m): self._emit("DEBUG", m, "· ")
    def info(self, m):  self._emit("INFO",  m, "  ")
    def ok(self, m):    self._emit("INFO",  m, "✔ ")
    def warn(self, m):  self._emit("WARN",  m, "⚠ ")
    def error(self, m): self._emit("ERROR", m, "✘ ")

    #  ★ rule/banner/table 은 '여러 줄이 한 덩어리' 다. 잠금 없이 찍으면 하트비트나
    #    다운로드 진행률 한 줄이 표의 행 사이에 끼어들어 정렬이 깨진다 — 오류 위치를
    #    한 화면에서 읽게 하려고 만든 커널인데 그 화면이 망가지는 것이다.
    def rule(self, title: str = "", ch: str = "─", width: int = 104):
        with self.lock:
            if title:
                pre = f"{ch * 3} {title} "
                _safe_print(pre + ch * max(0, width - _dw(pre)), flush=True)
            else:
                _safe_print(ch * width, flush=True)

    def banner(self, title: str, sub: str = "", width: int = 104):
        with self.lock:
            _safe_print("", flush=True)
            _safe_print("╔" + "═" * (width - 2) + "╗", flush=True)
            _safe_print("║ " + _pad(_trunc(title, width - 4), width - 4) + " ║", flush=True)
            if sub:
                _safe_print("║ " + _pad(_trunc(sub, width - 4), width - 4) + " ║", flush=True)
            _safe_print("╚" + "═" * (width - 2) + "╝", flush=True)

    def table(self, rows: List[Sequence[Any]], headers: Sequence[str],
              aligns: Optional[Sequence[str]] = None, maxw: int = 46, title: str = ""):
        """한글 폭 보정 표. 강건성/성과/감사 출력 전부 이걸 쓴다."""
        with self.lock:
            if title:
                _safe_print(f"\n▶ {title}", flush=True)
            if not rows:
                _safe_print("   (행 없음)", flush=True)
                return
            ncol = len(headers)
            aligns = list(aligns or ["l"] * ncol)
            cells = [[_trunc("" if c is None else c, maxw) for c in r] + [""] * (ncol - len(r))
                     for r in rows]
            widths = [max(_dw(headers[i]), *(_dw(r[i]) for r in cells)) for i in range(ncol)]
            head = "  " + " │ ".join(_pad(headers[i], widths[i], "c") for i in range(ncol))
            _safe_print(head, flush=True)
            _safe_print("  " + "─┼─".join("─" * widths[i] for i in range(ncol)), flush=True)
            for r in cells:
                _safe_print("  " + " │ ".join(_pad(r[i], widths[i], aligns[i])
                                              for i in range(ncol)), flush=True)


LOG = _Log("DEBUG" if VERBOSE else "INFO")


# ── 데이터 흐름 원장 ────────────────────────────────────────────────────────────────────────
@dataclass
class IOEvent:
    stage: str
    direction: str          # IN / OUT
    kind: str               # HTTP / DRIVE / PARQUET / MEM / SQLITE / SYNTH
    name: str
    rows: int = -1
    cols: int = -1
    bytes_: int = -1
    source: str = ""
    ok: bool = True
    note: str = ""
    pit_cols: str = ""      # knowledge_date 계열 컬럼 존재 여부 — C1 감사에 쓰인다


@dataclass
class StageRecord:
    sid: str
    name: str
    layer: str
    status: str = "PENDING"       # PENDING / RUNNING / OK / WARN / FAIL / SKIP
    t_start: float = 0.0
    t_end: float = 0.0
    budget_s: Optional[float] = None
    rows_in: int = 0
    rows_out: int = 0
    err_type: str = ""
    err_msg: str = ""
    err_tb: str = ""
    hint: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def dur(self) -> float:
        return (self.t_end or time.time()) - self.t_start


class KillCriteria(Exception):
    """§15 킬 기준 위반. 우회하지 말고 사용자에게 보고하고 멈춘다."""


class StageFailure(Exception):
    pass


# ── 예외 → 한글 진단 힌트 ───────────────────────────────────────────────────────────────────
_DIAG_RULES: List[Tuple[str, str]] = [
    (r"SERVICE_KEY_IS_NOT_REGISTERED|SERVICEKEY",
     "공공데이터포털 인증키 문제입니다. ① 해당 API에 '활용신청'이 승인됐는지 ② DATA_GO_KR_KEY 에 "
     "Decoding(일반) 키를 넣었는지 확인하세요. Encoding 키를 넣으면 이중 인코딩으로 항상 실패합니다."),
    (r"LIMITED_NUMBER_OF_SERVICE_REQUESTS",
     "공공데이터포털 일일 호출한도 초과입니다. 내일 재시도하거나 트래픽 증가 신청을 하세요. "
     "이미 받은 분량은 드라이브 캐시에 남아 있으므로 재실행 시 이어서 받습니다."),
    (r"opendart|dart.*(013|020|100|800|900)|status.*'0(13|20)'",
     "DART API 응답 코드 오류. 013=조회 데이터 없음(정상일 수 있음), 020=일일한도 초과, "
     "100=필드 부적절, 800=시스템 점검, 900=정의되지 않은 오류. DART_API_KEY 를 확인하세요."),
    (r"HTTPError.*40[13]|Forbidden|403",
     "403 차단입니다. RATE_LIMIT_QPS 를 절반으로 낮추고 N_WORKERS_IO 를 8 이하로 줄이세요. "
     "네이버/한경은 User-Agent 와 Referer 헤더가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests",
     "요청이 너무 빠릅니다. RATE_LIMIT_QPS 를 낮추세요. 코드가 지수백오프로 재시도하지만 한계가 있습니다."),
    (r"ConnectionError|Timeout|Max retries|NameResolution|SSLError|ProxyError",
     "네트워크 도달 실패입니다. 방화벽/프록시 환경이면 해당 도메인이 막혀 있을 수 있습니다. "
     "RUN_MODE='CACHED' 로 두고 드라이브 캐시만으로 백테스트할 수 있습니다."),
    (r"No such file or directory.*drive|MyDrive|drive/MyDrive",
     "구글드라이브가 마운트되지 않았습니다. Colab이면 셀 실행 시 뜨는 인증 팝업을 승인하세요. "
     "JupyterLab이면 자동으로 LOCAL_CACHE_ROOT 를 사용합니다(정상)."),
    (r"No space left on device|Disk quota",
     "디스크/드라이브 용량 부족입니다. RESEARCH_DOWNLOAD_PDF=False 로 두면 PDF 원문을 받지 않고 "
     "리스트 메타데이터만으로도 목표주가·애널리스트 연결이 가능합니다."),
    (r"Can't pickle|pickle.*__main__|PicklingError|BrokenProcessPool",
     "프로세스 병렬화 실패(노트북의 고질적 문제). 코드가 자동으로 스레드 병렬로 폴백합니다. "
     "성능만 떨어지고 결과는 동일합니다."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족입니다. MEM_BUDGET_GB 를 낮추고 RESEARCH_DOWNLOAD_PDF=False, "
     "N_WORKERS_CPU=2 로 두세요. 패널은 float32/category 로 이미 축소되어 있습니다."),
    (r"pyarrow|parquet|ArrowInvalid|ArrowIOError",
     "parquet 읽기/쓰기 실패입니다. 드라이브 FUSE 마운트에서 쓰기가 중단되면 파일이 깨질 수 있습니다. "
     "코드는 임시파일→원자적 rename 으로 쓰므로, 깨진 건 이전 실행 잔재입니다. "
     "해당 파일만 지우고(원본 아님, 캐시임) 재실행하세요."),
    (r"'DataFrame' object has no attribute 'name'|_wrap_agged_manager",
     "중복 컬럼입니다. DataFrame 에 같은 이름의 컬럼이 두 개 있으면 df[col] 이 Series 가 아니라 "
     "DataFrame 이 되고, groupby(...).agg() 가 pandas 내부에서 이 예외로 터집니다. "
     "직전에 concat/reindex(columns=...)/merge 로 컬럼을 합친 곳을 보세요 — "
     "리스트를 이어붙일 때(예: COLS + ['x'] 인데 COLS 에 이미 'x' 가 있는 경우) 가장 흔합니다. "
     "assert_no_dup_cols() 로 발생 지점을 앞당겨 잡을 수 있습니다."),
    (r"Expecting value: line \d+ column 1|JSONDecodeError|Error occurred in get_market",
     "JSON 대신 HTML(대개 로그인/에러 페이지)을 받았습니다. KRX 계열이면 세션이 끊긴 것입니다. "
     "pykrx 는 스레드마다 재로그인하며 KRX 는 중복 로그인 시 이전 세션을 끊습니다 — "
     "모든 pykrx 호출은 KRXG.call() 게이트로 직렬화해야 합니다. "
     "KRX ID/PW 를 다른 브라우저 탭에서 동시에 쓰고 있지 않은지도 확인하세요."),
    (r"UnicodeEncodeError|cp949|charmap",
     "콘솔 인코딩 문제입니다(윈도우 기본 cp949 는 罫線문자 ╔═║ 와 ✔✘ 를 못 씁니다). "
     "코드가 stdout 을 UTF-8 로 재설정하고 실패 시 ASCII 로 낮추지만, 직접 출력을 추가했다면 "
     "print 대신 _safe_print 를 쓰세요. 또는 실행 전 `chcp 65001` 을 하세요."),
    (r"statvfs|WinError",
     "윈도우 전용 이슈입니다. os.statvfs 는 윈도우에 없고(용량 표시만 생략됩니다), "
     "파일 잠금·경로 구분자도 다릅니다. 기능에는 영향이 없어야 하며, 있다면 버그입니다."),
    (r"KeyError: 'knowledge_date'|knowledge_date",
     "PIT 컬럼 누락입니다. 모든 테이블은 event_date/knowledge_date 를 가져야 합니다(C1). "
     "새 수집 함수를 추가했다면 pit_frame() 으로 감싸주세요."),
    (r"empty|EmptyDataError|No objects to concatenate|zero-size",
     "수집 결과가 비었습니다. 대개 ① 키 미입력 ② 조회구간에 데이터 없음 ③ 소스 구조 변경입니다. "
     "바로 위 FLOW 원장에서 어느 소스가 0행을 반환했는지 확인하세요."),
    (r"ModuleNotFoundError|ImportError",
     "패키지 누락입니다. 위 부트스트랩 로그에서 어떤 설치가 실패했는지 확인하고 수동 설치하세요."),
    (r"tz-aware|tz-naive|Cannot compare",
     "타임존이 섞인 날짜 비교입니다. 이 코드는 모든 날짜를 tz-naive Timestamp 로 정규화합니다(as_ts). "
     "새로 추가한 소스가 tz-aware 를 반환했을 가능성이 큽니다."),
]


def diagnose(exc: BaseException, extra: str = "") -> str:
    blob = f"{type(exc).__name__}: {exc}\n{extra}\n{traceback.format_exc()}"
    for pat, hint in _DIAG_RULES:
        if re.search(pat, blob, re.I):
            return hint
    return ("알려진 패턴에 해당하지 않는 오류입니다. 아래 트레이스백의 마지막 프레임과 "
            "그 직전 FLOW 원장 행을 함께 보면 원인 구간이 좁혀집니다.")


# ── 파이프라인 ──────────────────────────────────────────────────────────────────────────────
class Pipeline:
    """스테이지 실행기. 모든 계산은 이 안에서만 돈다."""

    def __init__(self):
        self.stages: "OrderedDict[str, StageRecord]" = OrderedDict()
        self.flow: List[IOEvent] = []
        self.current: Optional[StageRecord] = None
        self.failed: List[str] = []
        self.artifacts: Dict[str, Any] = {}
        self._lock = threading.RLock()

    # -- I/O 원장 -------------------------------------------------------------------------
    def io(self, direction: str, kind: str, name: str, obj: Any = None,
           source: str = "", ok: bool = True, note: str = "", bytes_: int = -1):
        rows = cols = -1
        pit = ""
        try:
            if isinstance(obj, pd.DataFrame):
                rows, cols = int(obj.shape[0]), int(obj.shape[1])
                have = [c for c in ("event_date", "knowledge_date") if c in obj.columns]
                pit = "+".join(h[0].upper() for h in have) if have else "—"
            elif isinstance(obj, (list, tuple, set, dict)):
                rows = len(obj)
            elif isinstance(obj, (int, float)):
                rows = int(obj)
        except Exception:
            pass
        ev = IOEvent(stage=self.current.sid if self.current else "-", direction=direction,
                     kind=kind, name=name, rows=rows, cols=cols, bytes_=bytes_,
                     source=source, ok=ok, note=note, pit_cols=pit)
        with self._lock:
            self.flow.append(ev)
            if self.current:
                if direction == "IN" and rows > 0:
                    self.current.rows_in += rows
                if direction == "OUT" and rows > 0:
                    self.current.rows_out += rows
        return obj

    def note(self, msg: str):
        if self.current:
            self.current.notes.append(msg)

    # -- 스테이지 ------------------------------------------------------------------------
    @contextmanager
    def stage(self, sid: str, name: str, layer: str = "L?",
              budget_s: Optional[float] = None, critical: bool = True,
              skip_if: bool = False, skip_reason: str = ""):
        rec = StageRecord(sid=sid, name=name, layer=layer, budget_s=budget_s)
        self.stages[sid] = rec
        prev, self.current = self.current, rec
        LOG.ctx.append(sid)
        if skip_if:
            rec.status, rec.t_start, rec.t_end = "SKIP", time.time(), time.time()
            rec.notes.append(skip_reason or "조건 미충족")
            LOG.warn(f"건너뜀 — {skip_reason}")
            LOG.ctx.pop(); self.current = prev
            yield rec
            return
        rec.status = "RUNNING"
        rec.t_start = time.time()
        LOG.info(f"▷ {name}")
        #  ★ 무출력 정체 방지 하트비트. budget_s 는 스테이지가 '끝난 뒤'에만 검사되므로
        #    스테이지가 통째로 멈추면 그 자체를 감지할 방법이 없었다 — 실제로 30분간
        #    로그 한 줄 없이 멈춘 사고가 있었다. 60초마다 경과시간만 찍어 침묵을 없앤다.
        #    데몬 스레드라 프로세스 종료를 막지 않고, finally 에서 반드시 멈춘다.
        _hb_stop = threading.Event()

        def _heartbeat():
            while not _hb_stop.wait(60.0):
                #  ★ 깨어난 뒤 잠금 안에서 다시 확인한다. wait() 가 돌아오는 순간과
                #    finally 사이에 스테이지가 끝날 수 있고, 그러면 이미 끝난 스테이지의
                #    '진행 중' 이 다음 스테이지 출력이나 최종 요약표 한가운데에 찍힌다.
                with LOG.lock:
                    if _hb_stop.is_set():
                        return
                    el = time.time() - rec.t_start
                    if budget_s is not None and el > budget_s:
                        LOG.warn(f"    …[{sid}] {el/60:.1f}분 경과 — 예산 {budget_s:.0f}s 를 "
                                 f"넘겼는데도 응답이 없습니다. 정체를 의심하세요.")
                    else:
                        LOG.info(f"    …[{sid}] 진행 중 · {el/60:.1f}분 경과")

        _hb_thread = threading.Thread(target=_heartbeat, daemon=True, name=f"hb-{sid}")
        _hb_thread.start()
        try:
            yield rec
            rec.t_end = time.time()
            rec.status = "WARN" if any("WARN:" in n for n in rec.notes) else "OK"
            over = budget_s and rec.dur > budget_s
            msg = f"완료 {rec.dur:6.2f}s  in={rec.rows_in:,} out={rec.rows_out:,}"
            if over:
                rec.notes.append(f"WARN: 런타임 예산 {budget_s:.0f}s 초과")
                LOG.warn(msg + f"  ← 예산 {budget_s:.0f}s 초과 (C10)")
            else:
                LOG.ok(msg)
        except KillCriteria as e:
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = "KillCriteria"; rec.err_msg = str(e)
            rec.err_tb = traceback.format_exc()
            rec.hint = "§15 킬 기준입니다. 파라미터를 조정해 통과시키지 마세요. 결과를 그대로 보고합니다."
            self.failed.append(sid)
            LOG.error(f"킬 기준 발동 — {e}")
            raise
        except BaseException as e:                                   # noqa
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = type(e).__name__; rec.err_msg = str(e)[:600]
            rec.err_tb = traceback.format_exc()
            rec.hint = diagnose(e, extra=f"stage={sid} name={name}")
            self.failed.append(sid)
            self._print_failure(rec)
            if critical:
                raise StageFailure(f"[{sid}] {name} 실패: {rec.err_type}: {rec.err_msg}") from e
            rec.status = "WARN"
            rec.notes.append(f"WARN: 비필수 스테이지 실패 — {rec.err_type}")
        finally:
            with LOG.lock:
                _hb_stop.set()
            _hb_thread.join(timeout=2.0)   # 늦은 한 줄이 다음 스테이지로 새지 않게
            LOG.ctx.pop()
            self.current = prev

    def _print_failure(self, rec: StageRecord):
        LOG.banner(f"✘ 실패 지점: [{rec.sid}] {rec.name}", f"계층 {rec.layer} · 경과 {rec.dur:.2f}s")
        _safe_print(f"  예외      : {rec.err_type}: {rec.err_msg}")
        _safe_print(f"  진단      : {rec.hint}")
        recent = [e for e in self.flow if e.stage == rec.sid][-8:]
        if recent:
            LOG.table(
                [[e.direction, e.kind, _trunc(e.name, 34), f"{e.rows:,}" if e.rows >= 0 else "-",
                  e.pit_cols, "OK" if e.ok else "ERR", _trunc(e.source or e.note, 26)] for e in recent],
                ["방향", "종류", "대상", "행수", "PIT", "상태", "소스/비고"],
                ["c", "l", "l", "r", "c", "c", "l"],
                title="이 스테이지의 직전 입출력 (여기서 무엇이 비었는지 보세요)")
        _safe_print("\n  ── 트레이스백 (마지막 12줄) " + "─" * 60)
        for ln in rec.err_tb.rstrip().split("\n")[-12:]:
            _safe_print("   " + ln)
        _safe_print("  " + "─" * 86)

    # -- 리포트 --------------------------------------------------------------------------
    def report_stages(self):
        LOG.banner("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수 · 런타임 예산(C10)")
        rows = []
        for r in self.stages.values():
            icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUNNING": "…"}.get(r.status, "?")
            bud = "-" if r.budget_s is None else (f"{r.budget_s:.0f}s" + ("❗" if r.dur > r.budget_s else ""))
            rows.append([r.layer, r.sid, _trunc(r.name, 40), f"{icon}{r.status}",
                         f"{r.dur:8.2f}", f"{r.rows_in:,}", f"{r.rows_out:,}", bud,
                         _trunc("; ".join(r.notes), 40)])
        LOG.table(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "예산", "비고"],
                  ["c", "l", "l", "c", "r", "r", "r", "c", "l"], maxw=44)

    def report_flow(self, only_kinds: Optional[Sequence[str]] = None, limit: int = 200):
        LOG.banner("데이터 흐름 원장 (I/O LEDGER)",
                   "어떤 스테이지가 어디서 몇 행을 읽고 어디에 몇 행을 썼는가 · PIT=E(event)/K(knowledge)")
        evs = [e for e in self.flow if (not only_kinds or e.kind in only_kinds)]
        if len(evs) > limit:
            LOG.warn(f"원장 {len(evs)}건 중 최근 {limit}건만 출력합니다.")
            evs = evs[-limit:]
        LOG.table(
            [[e.stage, e.direction, e.kind, _trunc(e.name, 38),
              f"{e.rows:,}" if e.rows >= 0 else "-",
              f"{e.cols}" if e.cols >= 0 else "-",
              e.pit_cols or "—", "OK" if e.ok else "ERR", _trunc(e.source or e.note, 30)] for e in evs],
            ["스테이지", "방향", "종류", "대상", "행수", "열수", "PIT", "상태", "소스/비고"],
            ["l", "c", "l", "l", "r", "r", "c", "c", "l"], maxw=40)

    def report_runtime(self):
        """C10 런타임 감사 — 추측하지 말고 측정한다."""
        LOG.banner("런타임 감사 (C10)", "계층별 실측 소요시간 vs 계약 예산")
        budgets = {"L1": 30 * 60, "L2": 2 * 60, "L3": 3 * 60, "L5": 4 * 3600}
        agg: Dict[str, float] = defaultdict(float)
        for r in self.stages.values():
            agg[r.layer] += r.dur
        rows = []
        for layer in sorted(agg):
            spent = agg[layer]
            bud = budgets.get(layer)
            verdict = "—"
            if bud:
                verdict = "✔ 예산 내" if spent <= bud else f"❗ 초과 ({spent / bud:.1f}배)"
            rows.append([layer, f"{spent:8.2f}s", f"{spent / 60:6.2f}분",
                         (f"{bud / 60:.0f}분" if bud else "-"), verdict])
        rows.append(["합계", f"{sum(agg.values()):8.2f}s", f"{sum(agg.values()) / 60:6.2f}분", "4시간",
                     "✔ 예산 내" if sum(agg.values()) <= 4 * 3600 else "❗ 초과 — 아키텍처 수정 필요"])
        LOG.table(rows, ["계층", "실측(초)", "실측(분)", "계약예산", "판정"], ["c", "r", "r", "r", "l"])
        LOG.info("계층 정의 — L0:부트/캐시  L1:수집·피처패널  L2:스코어  L3:백테스트  L5:강건성  L6:리포트")


PIPE = Pipeline()
