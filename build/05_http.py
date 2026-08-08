

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


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    if source == "krx" and krx_blocked():
        return None                       # 차단 중에는 요청 자체를 보내지 않는다(연장 방지)
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
                out = r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
                # ★ 차단은 200 OK 로 온다. 안내 페이지를 데이터로 착각하면 계속 때리게 된다.
                if _check_krx_block(source, out if isinstance(out, str) else
                                    (out[:4000].decode("utf-8", "ignore") if out else "")):
                    return None
                return out
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


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None) -> Optional[Union[str, bytes]]:
    if source == "krx" and krx_blocked():
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
                out = r.content if as_bytes else _decode(r.content, r.encoding, url)
                if _check_krx_block(source, out if isinstance(out, str) else ""):
                    return None
                return out
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    return None


# ── KRX 접속 차단 감지 ──────────────────────────────────────────────────────────────────────
#  ★ 실제 사고: 자동화 대량 조회로 판단되어 사용자 IP 가 1일 차단됐다.
#    KRX Data Marketplace 는 차단 시 200 OK 로 '이용 제한 안내' HTML 을 준다. 그래서
#    코드는 실패로 인식하지 못하고 계속 때렸고, 그게 차단을 연장시킬 수 있다.
#    → 차단 페이지를 감지하면 즉시 이번 실행의 KRX 경로를 전부 끄고, 마커를 남겨
#      다음 실행에서도 해제 시각까지 KRX 를 건드리지 않는다. 재시도는 하지 않는다.
_KRX_BLOCK_PAT = re.compile(
    r"이용\s*제한|비정상\s*대량\s*조회|ip-block-page|자동화\s*수단", re.I)
KRX_BLOCK = {"blocked": False, "until": 0.0, "logged": False}
KRX_BLOCK_HOURS = 24.0


def _krx_marker_path() -> Optional[str]:
    root = None
    try:
        v = globals().get("VAULT")
        root = getattr(v, "root", None) if v is not None else None
    except Exception:
        root = None
    root = root or globals().get("LOCAL_CACHE_ROOT")
    if not root:
        return None
    return os.path.join(str(root), "_locks", "krx_block.json")


def krx_block_load():
    """이전 실행에서 남긴 차단 마커를 읽는다. 해제 시각 전이면 이번에도 KRX 를 쓰지 않는다."""
    p = _krx_marker_path()
    if not p or not os.path.exists(p):
        return
    try:
        info = json.loads(open(p, encoding="utf-8").read() or "{}")
        until = float(info.get("until", 0))
    except Exception:
        return
    if until > time.time():
        KRX_BLOCK["blocked"], KRX_BLOCK["until"] = True, until
        LOG.warn(f"이전 실행에서 KRX 접속 제한이 감지되었습니다. 해제 예정 "
                 f"{_dt.datetime.fromtimestamp(until):%Y-%m-%d %H:%M} 까지 KRX 경로를 "
                 f"사용하지 않습니다. 유니버스·가격은 FDR/네이버 경로로 정상 동작합니다.")


def krx_mark_blocked():
    KRX_BLOCK["blocked"] = True
    KRX_BLOCK["until"] = time.time() + KRX_BLOCK_HOURS * 3600
    if not KRX_BLOCK["logged"]:
        KRX_BLOCK["logged"] = True
        LOG.error(
            "KRX 접속 제한 감지 — 이번 실행의 KRX 경로를 전부 중단합니다.\n"
            "   KRX Data Marketplace 가 '자동화 수단을 통한 비정상 대량 조회'로 판단해\n"
            "   해당 IP 를 약 1일간 제한했습니다(차단 시에도 HTTP 200 으로 안내 페이지를 줍니다).\n"
            "   · 이번 실행: 시총 스냅샷 등 KRX 의존 단계를 건너뛰고 FDR/네이버/DART 로 진행합니다.\n"
            "   · 다음 실행: 해제 시각까지 KRX 를 아예 건드리지 않습니다(마커 저장).\n"
            "   · 권장: KRX_MARKETPLACE_ID/PW 를 비우고 돌리거나, 공식 경로인\n"
            "     KRX Open API(openapi.krx.co.kr)의 인증키를 KRX_OPENAPI_KEY 에 넣으세요.")
    p = _krx_marker_path()
    if p:
        try:
            _ensure_dir(p)
            atomic_write_text(p, json.dumps({"until": KRX_BLOCK["until"],
                                             "at": _dt.datetime.now().isoformat()}))
        except Exception:
            pass


def krx_blocked() -> bool:
    if KRX_BLOCK["blocked"] and KRX_BLOCK["until"] > time.time():
        return True
    if KRX_BLOCK["blocked"] and KRX_BLOCK["until"] <= time.time():
        KRX_BLOCK["blocked"] = False
    return KRX_BLOCK["blocked"]


def _check_krx_block(source: str, text: Optional[str]) -> bool:
    """차단 안내 페이지인지 확인. 맞으면 True(=이 응답은 데이터가 아니다)."""
    if not text or source != "krx":
        return False
    head = text[:4000]
    if _KRX_BLOCK_PAT.search(head) and ("KRX" in head or "krx" in head):
        krx_mark_blocked()
        return True
    return False


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
