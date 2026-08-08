

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 차단 회피          ║
# ║                                                                                          ║
# ║  한국 사이트 수집에서 실패의 9할은 세 가지다:                                              ║
# ║   ① User-Agent/Referer 없음 → 403   ② euc-kr 인데 utf-8로 디코드 → 글자 깨짐               ║
# ║   ③ 너무 빠른 요청 → 429/차단.  전부 여기서 한 번에 막는다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36",
]

_TLS = threading.local()
HTTP_STATS: Counter = Counter()
_HTTP_LK = threading.Lock()


def _session() -> "requests.Session":
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    s = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
            rt = Retry(total=0, connect=2, read=2, backoff_factor=0.5,
                       status_forcelist=(), raise_on_status=False)
        except Exception:
            rt = None
        ad = HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                         pool_maxsize=max(32, N_WORKERS_IO * 4),
                         max_retries=rt) if rt is not None else \
            HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                        pool_maxsize=max(32, N_WORKERS_IO * 4))
        s.mount("https://", ad)
        s.mount("http://", ad)
    except Exception:
        pass
    s.headers.update({
        "User-Agent": UA_POOL[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    _TLS.sess = s
    return s


_HANGUL = re.compile(r"[가-힣]")
_MOJI = re.compile(r"[¿½¶ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß]")


def _korean_score(t: str) -> float:
    """한글 가독성 점수. 네이버 금융은 body 가 EUC-KR 인데 meta 는 utf-8 이라고 '거짓말'한다.
    meta 를 믿으면 조용히 깨진 글자를 얻는다(예외가 안 난다) — 그래서 점수로 고른다."""
    s = t[:6000]
    if not s:
        return -1.0
    han = len(_HANGUL.findall(s))
    moji = len(_MOJI.findall(s))
    repl = s.count("�")
    return han - 3.0 * moji - 5.0 * repl


def _decode(content: bytes, resp_enc: Optional[str], url: str,
            force_enc: Optional[str] = None) -> str:
    # force_enc 는 '우선 후보'일 뿐 절대 지정이 아니다. 소스가 UTF-8 로 바뀌면
    # euc-kr 강제 디코딩은 예외 없이 깨진 글자를 돌려주므로, 점수로 검증한 뒤에만 채택한다.
    if force_enc:
        try:
            t = content.decode(force_enc, "replace")
            if _korean_score(t) > 30:
                return t
        except Exception:
            pass
    head = content[:4096].decode("ascii", "ignore").lower()
    m = re.search(r'charset\s*=\s*["\']?\s*([\w\-]+)', head)
    cands: List[str] = []
    if m:
        cands.append(m.group(1))
    if resp_enc:
        cands.append(resp_enc)
    cands += ["utf-8", "euc-kr", "cp949"]
    seen, best, best_s = set(), None, -1e18
    for enc in cands:
        e = (enc or "").lower().replace("ks_c_5601-1987", "cp949")
        if not e or e in seen:
            continue
        seen.add(e)
        try:
            t = content.decode(e)
        except Exception:
            continue
        sc = _korean_score(t)
        if sc > best_s:
            best, best_s = t, sc
        if sc > 30:                     # 충분히 한글다우면 더 볼 필요 없음
            return t
    return best if best is not None else content.decode("utf-8", "replace")


def euckr_q(s: str) -> str:
    """네이버/한경 레거시 경로의 한글 파라미터는 UTF-8이 아니라 EUC-KR 퍼센트인코딩이다.
    이걸 틀리면 예외 없이 '검색 결과 0건'이 나온다 — 최악의 조용한 실패."""
    try:
        return quote(str(s), encoding="euc-kr")
    except Exception:
        return quote(str(s))


class _TooBig(Exception):
    """응답이 상한을 넘었다 — 재시도해도 같은 결과다. 재시도 대상이 아니다."""


@contextmanager
def _deadline(resp, deadline_s: float, label: str):
    """응답 본문 읽기에 **전체 마감**을 건다.

    ★ requests 의 timeout= 은 연결과 '바이트 사이 간격' 에만 걸린다. 전체 다운로드
      마감이 아니다. 서버가 timeout 안쪽 간격으로 조금씩 흘려보내면 r.content 는
      몇 시간이든 매달리고 예외도 로그도 없다 — 파이프라인 전체가 조용히 잠긴다.
      실제로 OpenDART corpCode.xml(약 20MB)이 정확히 이 방식으로 무한정 멈췄다.

    ★ 그리고 resp.close() / resp.raw.close() 로는 못 푼다. 이미 recv() 에 블록된
      스레드는 그대로 남는다(재현 확인: 워치독은 발동하는데 프로세스는 계속 매달림).
      커널에게 FD 를 끊게 하는 socket.shutdown(SHUT_RDWR) 만이 블록된 recv() 를
      즉시 예외로 되돌린다. 그래서 이 가드는 소켓을 직접 끊는다.
    """
    sk = _resp_socket(resp)
    fired = {"v": False}

    def _kill():
        fired["v"] = True
        LOG.warn(f"    ↓ {label} 전체 마감 {deadline_s:.0f}s 초과 — 연결을 끊습니다")
        for fn in (lambda: sk.shutdown(_socket.SHUT_RDWR), lambda: sk.close(),
                   lambda: resp.raw.close(), lambda: resp.close()):
            try:
                fn()
            except Exception:
                pass

    killer = threading.Timer(deadline_s, _kill)
    killer.daemon = True
    killer.start()
    try:
        yield fired
    finally:
        killer.cancel()


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None, deadline_s: Optional[float] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    """단건 GET. **한 번의 시도는 deadline_s 안에 반드시 끝난다** (기본 timeout×3, 최소 60s).

    마감을 여기 계층에 둔 이유: 호출지점마다 따로 막으면 새 호출지점이 하나 생길 때마다
    같은 정체가 되살아난다. 감사 결과 실제로 그랬다 — corpCode 만 고쳤더니 marcap 파케이,
    fdr.DataReader, 리스트 크롤이 전부 같은 성질의 무한대기로 남아 있었다.
    """
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    dl = float(deadline_s) if deadline_s else max(60.0, float(timeout) * 3.0)
    label = url.split("/")[-1][:40] or source
    last_exc = None
    for attempt in range(tries):
        lim.wait()
        if on_attempt is not None:
            try:
                on_attempt()
            except Exception:
                pass
        try:
            s = _session()
            if attempt > 0:
                hdr["User-Agent"] = UA_POOL[attempt % len(UA_POOL)]
            #  stream=True + 가드 안에서 .content 를 읽는다. 본문 읽기가 마감에 걸리면
            #  소켓이 끊기면서 예외로 빠져나온다(무한대기 불가).
            r = s.get(url, params=params, headers=hdr, timeout=timeout, stream=True)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{r.status_code}"] += 1
            if r.status_code in allow_status:
                with _deadline(r, dl, label):
                    body = r.content
                return body if as_bytes else _decode(body, r.encoding, url, force_enc)
            if r.status_code in (429, 503):
                time.sleep(min(30.0, 2.0 * (2 ** attempt)) + random.random())
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            if r.status_code in (403, 401):
                time.sleep(1.5 * (attempt + 1))
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            last_exc = requests.HTTPError(f"{r.status_code} {url}")
        except Exception as e:                                # noqa
            last_exc = e
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(min(12.0, (1.7 ** attempt)) + random.random() * 0.3)
    if not quiet and last_exc:
        LOG.debug(f"GET 실패({source}) {url[:90]} — {type(last_exc).__name__}")
    with _HTTP_LK:
        HTTP_STATS[f"{source}:FAIL"] += 1
    return None


def _resp_socket(resp):
    """requests 응답에서 **진짜 소켓 객체**를 캐낸다.

    requests → urllib3.HTTPResponse(raw) → http.client.HTTPResponse(_fp)
    → socket 의 buffered reader(fp) → SocketIO(raw) → socket(_sock).
    urllib3 버전마다 경로가 조금씩 달라서 후보를 순서대로 시도한다.
    못 찾으면 None — 그러면 마감은 못 걸지만 나머지 동작은 그대로다.
    """
    for path in (lambda: resp.raw._connection.sock,
                 lambda: resp.raw._fp.fp.raw._sock,
                 lambda: resp.raw._fp.fp._sock,
                 lambda: resp.raw._original_response.fp.raw._sock):
        try:
            s = path()
            if s is not None:
                return s
        except Exception:
            continue
    return None



def http_get_stream(url: str, source: str = "generic", params: Optional[dict] = None,
                    headers: Optional[dict] = None, connect_timeout: int = 15,
                    read_timeout: int = 30, deadline_s: float = 300.0,
                    tries: int = 3, referer: Optional[str] = None,
                    max_bytes: int = 400 * 1024 * 1024,
                    desc: str = "") -> Optional[bytes]:
    """대용량 응답 전용 다운로더 — **전체 소요시간 상한**이 있다.

    ★ 왜 http_get 으로 충분하지 않은가 (실제로 겪은 사고다):
      requests 의 timeout 은 '연결' 과 '바이트 사이 간격' 에만 걸린다. 전체 다운로드
      마감이 아니다. 서버가 25초 안쪽 간격으로 조금씩 흘려보내면 r.content 는 몇 시간이든
      매달리고 예외도 나지 않는다 — 로그 한 줄 없이 파이프라인 전체가 잠긴다.
      실행 로그에서 OpenDART corpCode.xml(약 20MB)이 정확히 이 방식으로 무한정 멈췄다.

    → 그래서 여기서는 stream=True 로 청크를 받으면서 **경과시간을 직접 재고**,
      deadline_s 를 넘기면 그 자리에서 포기한다. 진행률도 찍으므로 침묵이 없다.
    """
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    label = desc or url.split("/")[-1][:40]
    for attempt in range(max(1, tries)):
        lim.wait()
        t0 = time.time()
        got = bytearray()
        total = 0
        prog_stop = threading.Event()
        try:
            s_ = _session()
            if attempt > 0:
                hdr["User-Agent"] = UA_POOL[attempt % len(UA_POOL)]
            r = s_.get(url, params=params, headers=hdr, stream=True,
                       timeout=(connect_timeout, read_timeout))
            #  ★ 전체 마감의 유일한 집행자: 워치독이 **소켓을 shutdown** 한다.
            #    - 청크 크기로는 못 막는다. chunk_size 를 크게 주면 그만큼 모일 때까지
            #      루프 본문이 안 돌고, chunk_size=None 은 urllib3 가 read(None) 으로
            #      본문 전체를 기다린다.
            #    - resp.raw.close()/resp.close() 로도 못 막는다. 이미 recv() 에 블록된
            #      스레드는 풀려나지 않는다 — 워치독은 발동하는데 다운로드는 그대로
            #      매달린다. 재현 테스트로 확인했다(t_min.py: 워치독 20.0s 발동 후에도
            #      프로세스가 살아남아 timeout 124 로 강제 종료됨).
            #    → 커널에게 FD 를 끊게 하는 socket.shutdown(SHUT_RDWR) 만이 블록된
            #      recv() 를 즉시 예외로 되돌린다. t_min2.py 로 20.0s 정확히 검증.
            def _progress():                # 15초마다 진행률 — 멈춰 있어도 로그가 난다
                while not prog_stop.wait(15.0):
                    n, el = len(got), time.time() - t0
                    pct = f" / {total/1e6:.0f}MB ({100*n/total:.0f}%)" if total else ""
                    LOG.info(f"    ↓ {label} {n/1e6:.1f}MB{pct} · {el:.0f}s"
                             f"{'  (수신 정체)' if n == 0 else ''}")
            threading.Thread(target=_progress, daemon=True,
                             name=f"dl-{label[:12]}").start()
            try:
                with _HTTP_LK:
                    HTTP_STATS[f"{source}:{r.status_code}"] += 1
                if r.status_code != 200:
                    raise requests.HTTPError(f"{r.status_code} {url}")
                #  Content-Length 가 중복 헤더로 오면 '123, 123' 이라 int() 가 터진다.
                #  그건 네트워크 실패가 아니므로 재시도로 낭비하지 않고 0 으로 둔다.
                try:
                    total = int(str(r.headers.get("Content-Length") or 0).split(",")[0])
                except Exception:
                    total = 0
                with _deadline(r, deadline_s, label):
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if not chunk:
                            continue
                        got.extend(chunk)
                        if len(got) > max_bytes:
                            raise _TooBig(f"응답이 {max_bytes/1e6:.0f}MB 를 넘었습니다")
            finally:
                prog_stop.set()
            if total and len(got) < total:
                raise IOError(f"불완전 수신 {len(got):,}/{total:,}B")
            if len(got):
                LOG.debug(f"↓ {label} 완료 {len(got)/1e6:.1f}MB · {time.time()-t0:.1f}s")
                return bytes(got)
            raise IOError("빈 응답")
        except _TooBig as e:
            prog_stop.set()
            LOG.warn(f"↓ {label} {e} — 같은 결과가 나올 것이므로 재시도하지 않습니다.")
            break
        except BaseException as e:      # noqa — 소켓 절단은 어떤 예외로도 올라올 수 있다
            prog_stop.set()
            if isinstance(e, KeyboardInterrupt):
                raise
            el = time.time() - t0
            kind = ("전체 마감 초과" if el >= deadline_s - 1 else f"{type(e).__name__}")
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            LOG.debug(f"↓ {label} 시도 {attempt+1}/{tries} 실패({kind}) · "
                      f"{len(got)/1e6:.1f}MB 수신 · {el:.0f}s")
            time.sleep(min(8.0, 1.7 ** attempt))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:FAIL"] += 1
    LOG.warn(f"↓ {label} 다운로드 실패 — 전체 마감 {deadline_s:.0f}s 안에 못 받았습니다. "
             f"이 호출은 여기서 포기하고 파이프라인은 계속 진행합니다.")
    return None


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None) -> Optional[Union[str, bytes]]:
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    for attempt in range(tries):
        lim.wait()
        try:
            r = _session().post(url, data=data, json=json_body, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:POST{r.status_code}"] += 1
            if r.status_code == 200:
                return r.content if as_bytes else _decode(r.content, r.encoding, url)
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    return None


def soup_of(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    for parser in ("lxml", "html.parser", "html5lib"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def http_json(url: str, source: str = "generic", **kw) -> Optional[Any]:
    t = http_get(url, source=source, **kw)
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None


def report_http():
    if not HTTP_STATS:
        return
    LOG.banner("HTTP 수집 감사", "소스별 응답 분포 — 403/429가 많으면 RATE_LIMIT_QPS 를 낮추세요")
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_STATS.items():
        src, _, code = k.partition(":")
        by_src[src][code] += v
    rows = []
    for src, c in sorted(by_src.items()):
        tot = sum(c.values())
        ok = c.get("200", 0) + c.get("POST200", 0)
        bad = sum(v for k, v in c.items() if k in ("403", "401", "429", "503", "FAIL", "POSTFAIL"))
        rows.append([src, f"{tot:,}", f"{ok:,}", f"{100 * ok / max(tot, 1):.1f}%", f"{bad:,}",
                     _trunc(", ".join(f"{k}×{v}" for k, v in c.most_common(5)), 44)])
    LOG.table(rows, ["소스", "요청", "성공", "성공률", "차단/실패", "상세"],
              ["l", "r", "r", "r", "r", "l"])
