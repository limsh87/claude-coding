

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 응답 영속 캐시      ║
# ║                                                                                          ║
# ║  한국 사이트 수집에서 실패의 9할은 세 가지다:                                              ║
# ║   ① User-Agent/Referer 없음 → 403   ② euc-kr 인데 utf-8로 디코드 → 글자 깨짐               ║
# ║   ③ 너무 빠른 요청 → 429/차단.  전부 여기서 한 번에 막는다.                                ║
# ║                                                                                          ║
# ║  ★ 그리고 네 번째, 가장 비싼 실패: **같은 것을 또 받는 것.**                                ║
# ║    모든 GET 응답은 내용해시 blob 으로 드라이브에 남고, 같은 URL+파라미터는 두 번 다시       ║
# ║    네트워크에 나가지 않는다. 과거 구간 조회는 TTL 무시하고 영구 재사용한다                  ║
# ║    (2017년 리포트 목록이 지금 와서 바뀔 리 없다). 전략을 몇 번을 돌리든 스크레이핑은        ║
# ║    최초 1회다.                                                                            ║
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
BREAKERS: Dict[str, CircuitBreaker] = {}


def breaker(source: str) -> CircuitBreaker:
    with _HTTP_LK:
        if source not in BREAKERS:
            BREAKERS[source] = CircuitBreaker(source, threshold=10)
        return BREAKERS[source]


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
        kw = dict(pool_connections=max(16, N_WORKERS_IO * 2),
                  pool_maxsize=max(32, N_WORKERS_IO * 4))
        ad = HTTPAdapter(max_retries=rt, **kw) if rt is not None else HTTPAdapter(**kw)
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
    return len(_HANGUL.findall(s)) - 3.0 * len(_MOJI.findall(s)) - 5.0 * s.count("�")


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


def _cache_ttl_for(params: Optional[dict], source: str) -> Optional[float]:
    """조회 구간이 충분히 과거면 TTL 을 무시하고 영구 재사용한다.

    ★ 이 규칙 하나가 10년 백테스트 재실행 시간을 지배한다. 리스트 페이지 스크레이핑은
      건수로는 수만 요청인데, 그 99%가 '이미 끝난 과거 구간' 이라 다시 받을 이유가 없다."""
    if not params:
        return None
    try:
        best = None
        for k, v in params.items():
            if not re.search(r"(date|dt|de|day|sdate|edate|end|to|until)", str(k), re.I):
                continue
            t = as_ts(re.sub(r"[^0-9\-]", "", str(v))[:10]) if str(v) else None
            if t is None:
                continue
            best = t if best is None else max(best, t)
        if best is not None:
            age_days = (pd.Timestamp.today().normalize() - best).days
            if age_days >= HTTP_CACHE_IMMUTABLE_DAYS:
                return 0.0          # 0 = 무기한
    except Exception:
        pass
    return None


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None, use_cache: bool = True,
             cache_ttl_days: Optional[float] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    """캐시 우선 GET. 캐시에 있으면 네트워크에 나가지 않는다."""
    # ── ① 응답 캐시 ─────────────────────────────────────────────────────────────────
    if use_cache and VAULT is not None and CACHE_EVERYTHING:
        ttl = cache_ttl_days if cache_ttl_days is not None else _cache_ttl_for(params, source)
        hit = VAULT.get_http(url, params, source, ttl_days=ttl)
        if hit is not None:
            with _HTTP_LK:
                HTTP_STATS[f"{source}:CACHE"] += 1
            return hit if as_bytes else _decode(hit, None, url, force_enc)

    br = breaker(source)
    if br.tripped:
        return None

    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
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
            r = s.get(url, params=params, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{r.status_code}"] += 1
            if r.status_code in allow_status:
                br.ok()
                if use_cache and VAULT is not None and CACHE_EVERYTHING and r.content:
                    VAULT.put_http(url, params, source, r.content)
                return r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
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
    br.fail()
    return None


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None,
              use_cache: bool = True) -> Optional[Union[str, bytes]]:
    """POST 도 캐시한다. 조회용 POST(한경/금투협 검색 폼)가 대부분이라 멱등하다.
    ★ 부작용이 있는 POST(로그인 등)는 use_cache=False 로 호출할 것."""
    ckey = {"_post": True, **(data or {}), **({"_json": json.dumps(json_body, sort_keys=True)}
                                              if json_body else {})}
    if use_cache and VAULT is not None and CACHE_EVERYTHING:
        hit = VAULT.get_http(url, ckey, source, ttl_days=_cache_ttl_for(data, source))
        if hit is not None:
            with _HTTP_LK:
                HTTP_STATS[f"{source}:CACHE"] += 1
            return hit if as_bytes else _decode(hit, None, url)
    br = breaker(source)
    if br.tripped:
        return None
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
                br.ok()
                if use_cache and VAULT is not None and CACHE_EVERYTHING and r.content:
                    VAULT.put_http(url, ckey, source, r.content)
                return r.content if as_bytes else _decode(r.content, r.encoding, url)
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    br.fail()
    return None


def soup_of(html: Optional[str]) -> Optional["BeautifulSoup"]:
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
    if isinstance(t, bytes):
        t = t.decode("utf-8", "replace")
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
    LOG.banner("HTTP 수집 감사",
               "소스별 응답 분포 — CACHE 가 많을수록 재실행이 빠릅니다 · 403/429가 많으면 QPS 를 낮추세요")
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_STATS.items():
        src, _, code = k.partition(":")
        by_src[src][code] += v
    rows = []
    for src, c in sorted(by_src.items()):
        tot = sum(c.values())
        cache = c.get("CACHE", 0)
        net = tot - cache
        ok = c.get("200", 0) + c.get("POST200", 0)
        bad = sum(v for k, v in c.items() if k in ("403", "401", "429", "503", "FAIL", "POSTFAIL"))
        rows.append([src, f"{tot:,}", f"{cache:,}", f"{100*cache/max(tot,1):.1f}%",
                     f"{net:,}", f"{ok:,}", f"{bad:,}",
                     _trunc(", ".join(f"{k}×{v}" for k, v in c.most_common(4)), 38)])
    LOG.table(rows, ["소스", "요청", "캐시적중", "적중률", "실제망", "성공", "차단/실패", "상세"],
              ["l", "r", "r", "r", "r", "r", "r", "l"])
    trip = [b.name for b in BREAKERS.values() if b.tripped]
    if trip:
        LOG.warn(f"서킷 브레이커가 작동한 소스: {trip} — 해당 소스는 이번 실행에서 중단되었습니다. "
                 f"받은 분량은 캐시에 남아 있으니 잠시 후 재실행하면 이어받습니다.")
