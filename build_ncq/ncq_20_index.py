

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 1 — 리포트 인덱스 전수 수집 · 원장 병합 · 커버리지 완결성 진단                      ║
# ║                                                                                          ║
# ║  입력 : sec(종목마스터) · months · 드라이브 공용 캐시(research_report_master)               ║
# ║  출력 : REP(보고서 원장) · diag(완결성 진단표) · valid_start(유효 백테스트 시작월)          ║
# ║  실패 : 소스 하나가 죽어도 나머지로 계속한다. 전부 죽으면 캐시만으로 진행하고 그 사실을 명시.║
# ║                                                                                          ║
# ║  ★ 본문이 아니라 **메타데이터만** 받는다. 본문(PDF)은 Phase 3 에서 '이벤트로 판정된 건'만   ║
# ║    받는다. 이 순서가 이 전략의 비용 구조 전체를 결정한다(수만 건 → 수천 건).                ║
# ║  ★ 수집은 **최신 → 과거 역순**(명세 §6.2). 예산 초과로 중단돼도 최근 구간이 살아 있어야     ║
# ║    열화 L3(윈도우 축소)를 바로 적용할 수 있다. 과거부터 받으면 중단 시 전략이 무효가 된다.  ║
# ║  ★ 유니버스로 먼저 자르지 않는다(명세 §1.3). 시총 상위였다가 하위로 내려온 종목의 과거      ║
# ║    커버리지 이력이 사라지면 '가짜 신규 커버리지'가 대량 발생한다.                           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 한국IR협의회 — 기업리서치·기술분석보고서. 기업 신청/사업 기반이라 자발적 커버리지가 아니다.
# → is_sponsored=True 로 태깅하고 이벤트 서브그룹을 분리한다(명세 §7.2).
IRS_HOSTS = [
    "https://www.kirs.or.kr",
    "https://kirs.or.kr",
    "https://www.irsolution.or.kr",
    "https://irsolution.or.kr",
]
IRS_LIST_PATHS = [
    "/information/tech1.html",       # 기술분석보고서
    "/information/tech2.html",
    "/information/research1.html",   # 기업리서치
    "/board/list.html",
]


class NcqCircuit:
    """소스별 서킷 브레이커 (명세 §3.4).

    연속 실패 5회 → 60초 대기 후 '축소 모드'로 재시도 → 다시 5회 실패 → 영구 스킵.
    ★ 예외를 던지지 않는다. open() 이 True 면 호출측이 그 소스를 조용히 건너뛰되 로그는 남는다.
    """

    def __init__(self, name: str, threshold: int = 5, cooldown: float = 60.0):
        self.name, self.threshold, self.cooldown = name, threshold, cooldown
        self.fails = 0
        self.trips = 0
        self.dead = False

    def ok(self):
        self.fails = 0

    def fail(self) -> bool:
        """True 를 돌려주면 '이 소스는 이제 끝'이라는 뜻."""
        self.fails += 1
        if self.fails < self.threshold:
            return self.dead
        self.trips += 1
        self.fails = 0
        if self.trips == 1:
            LOG.warn(f"[{self.name}] 연속 {self.threshold}회 실패 — 서킷 브레이커 발동. "
                     f"{self.cooldown:.0f}초 대기 후 축소 모드(워커 2)로 재시도합니다.")
            time.sleep(self.cooldown)
            globals()["N_WORKERS_RESEARCH"] = 2
        else:
            self.dead = True
            LOG.error(f"[{self.name}] 재차 {self.threshold}회 실패 — 이 소스를 영구 스킵합니다. "
                      f"수집된 분량까지는 그대로 사용하고, 결손은 완결성 진단에 반영됩니다.")
            manifest_note(f"소스 영구 스킵: {self.name}")
        return self.dead


# ── IR협의회 ────────────────────────────────────────────────────────────────────────────────
_IRS_DATE_RE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_IRS_ENDPOINT_CACHE: Dict[str, Any] = {"url": None, "probed": False}


def ncq_irs_probe() -> Optional[str]:
    """IR협의회 리스트 엔드포인트를 한 번만 탐색한다. 못 찾으면 None(정상 스킵)."""
    if _IRS_ENDPOINT_CACHE["probed"]:
        return _IRS_ENDPOINT_CACHE["url"]
    _IRS_ENDPOINT_CACHE["probed"] = True
    for host in IRS_HOSTS:
        for path in IRS_LIST_PATHS:
            url = host + path
            html = http_get(url, source="irs", tries=1, timeout=20, referer=host + "/")
            if not html or len(html) < 800:
                continue
            s = soup_of(html)
            if s is None:
                continue
            # 표 안에 날짜 + PDF 링크(또는 상세 링크)가 함께 있으면 리스트 페이지로 본다
            if s.find("table") is not None and _IRS_DATE_RE.search(html):
                _IRS_ENDPOINT_CACHE["url"] = url
                LOG.ok(f"IR협의회 리스트 엔드포인트 확인: {url}")
                return url
    LOG.info("IR협의회 리스트 페이지를 찾지 못했습니다 — 이 소스는 건너뜁니다. "
             "명세상 IRS 는 스폰서 리포트(비자발적 커버리지)이므로, 없어도 주가설 H1 은 "
             "'ORGANIC_ONLY' 로 그대로 검정됩니다.")
    return None


def ncq_irs_collect(start: str, end: str, max_pages: int = 40) -> pd.DataFrame:
    """IR협의회 인덱스 수집(베스트에포트). 실패는 예외가 아니라 빈 DataFrame 이다."""
    base = ncq_irs_probe()
    if not base:
        return pd.DataFrame(columns=REPORT_COLS)
    lo, hi = as_ts(start), as_ts(end)
    rows: List[dict] = []
    for page in range(1, max_pages + 1):
        html = http_get(base, source="irs", tries=2, timeout=25, referer=base,
                        params={"page": page, "pageIndex": page,
                                "sdate": lo.strftime("%Y-%m-%d"), "edate": hi.strftime("%Y-%m-%d")})
        if not html:
            break
        s = soup_of(html)
        if s is None:
            break
        got = 0
        for tr in s.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            txt = " ".join(_clean_cell(td.get_text(" ")) for td in tds)
            m = _IRS_DATE_RE.search(txt)
            if not m:
                continue
            d = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            dt = as_ts(d)
            if dt is None or dt < lo or dt > hi:
                continue
            a = tr.find("a", href=True)
            href = urljoin(base, a["href"]) if a is not None else None
            title = _clean_cell(a.get_text(" ")) if a is not None else \
                _clean_cell(tds[1].get_text(" "))
            pdf = None
            for aa in tr.find_all("a", href=True):
                if ".pdf" in aa["href"].lower() or "download" in aa["href"].lower():
                    pdf = urljoin(base, aa["href"])
                    break
            name = _clean_cell(tds[0].get_text(" "))
            if len(name) > 20 or not name:
                name = name_from_title(title)
            rid = sha1_str("irs", href or title, d)[:16]
            rows.append({
                "source": "irs", "src_report_id": rid, "category": "company",
                "pub_date": d, "title": title,
                "stock_code": code_from_title(title),
                "stock_name": name,
                "broker_raw": "한국IR협의회", "analyst_raw": "",
                "target_price": None, "opinion": None,
                "pdf_url": pdf, "detail_url": href, "views": None,
            })
            got += 1
        if got == 0:
            break
    d = pd.DataFrame(rows)
    if len(d):
        d = d.drop_duplicates("src_report_id")
        LOG.ok(f"IR협의회 {len(d):,}건 (스폰서 리포트로 태깅됩니다)")
    return d if len(d) else pd.DataFrame(columns=REPORT_COLS)


# ── 세션 지속성 (_done.jsonl) ───────────────────────────────────────────────────────────────
def ncq_done_path(phase: str) -> str:
    p = os.path.join(VAULT.ns["private"], "index", f"ncq_{phase}_done.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def ncq_done_load(phase: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for r in read_jsonl(ncq_done_path(phase)):
        k = str(r.get("key", ""))
        if k:
            out[k] = r
    return out


def ncq_done_mark(phase: str, key: str, **info):
    append_jsonl(ncq_done_path(phase), [{"key": key, "at": _dt.datetime.now().isoformat(
        timespec="seconds"), **info}])


# ── 월 단위 역순 수집 ───────────────────────────────────────────────────────────────────────
_SOURCE_FN = {
    "naver": lambda s, e: naver_collect(s, e, cats=("company",)),
    "hankyung": lambda s, e: hankyung_collect(s, e),
    "irs": lambda s, e: ncq_irs_collect(s, e),
}


def ncq_collect_source_by_month(source: str, months: pd.DatetimeIndex,
                                budget: "PhaseBudget") -> pd.DataFrame:
    """한 소스를 **최신 → 과거 역순**으로 월 단위 수집한다. 월 1개 = 청크 1개.

    · 이미 처리한 월은 _done.jsonl 로 건너뛴다(재실행 시 이어받기).
    · 청크마다 연도별 parquet 으로 공용 인덱스에 저장한다(단일 거대 parquet 금지).
    · 예산 초과 시 예외 없이 루프를 정상 종료하고 부분 결과를 돌려준다.
    """
    fn = _SOURCE_FN.get(source)
    if fn is None:
        return pd.DataFrame(columns=REPORT_COLS)
    done = ncq_done_load(f"p1_{source}")
    cb = NcqCircuit(source)
    frames: List[pd.DataFrame] = []
    n_skip = n_new = 0

    todo = [m for m in reversed(list(months))]
    bar = tqdm(todo, desc=f"P1 {source}", ncols=88, leave=False)
    for m in bar:
        ym = m.strftime("%Y-%m")
        if ym in done:
            n_skip += 1
            continue
        if cb.dead:
            break
        if not budget.check():
            LOG.warn(f"[P1/{source}] 예산 소진 — {ym} 이전 구간은 수집하지 않습니다. "
                     f"최신 구간부터 받았으므로 확보된 구간만으로 백테스트가 가능합니다.")
            break
        s = m.replace(day=1).strftime("%Y-%m-%d")      # 그 달 1일
        e = m.strftime("%Y-%m-%d")                     # 그 달 말일 (month_end 이므로 그대로)
        try:
            d = fn(s, e)
        except Exception as ex:                                  # noqa
            LOG.debug(f"[{source}] {ym} 수집 예외 {type(ex).__name__}: {ex}")
            d = None
        if d is None or len(d) == 0:
            if cb.fail():
                break
            ncq_done_mark(f"p1_{source}", ym, n=0, note="empty")
            continue
        cb.ok()
        d = d.copy()
        d["_ym"] = ym
        frames.append(d)
        n_new += len(d)
        ncq_done_mark(f"p1_{source}", ym, n=int(len(d)))
        # 연 단위 샤딩 저장 (공용 — 다른 전략도 그대로 재사용)
        if m.month == 1 or m == todo[-1] or len(frames) % 12 == 0:
            _ncq_flush_index_shard(source, frames)
    try:
        bar.close()
    except Exception:
        pass
    _ncq_flush_index_shard(source, frames, final=True)
    LOG.ok(f"[P1/{source}] 신규 {n_new:,}건 · 캐시 스킵 {n_skip}개월 · "
           f"소요 {budget.elapsed()/60:.1f}분")
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    return pd.concat(frames, ignore_index=True)


def _ncq_flush_index_shard(source: str, frames: List[pd.DataFrame], final: bool = False):
    """연도별 샤드로 공용 인덱스에 저장. 기존 샤드와 합집합 병합(정보를 버리지 않는다)."""
    if not frames:
        return
    d = pd.concat(frames, ignore_index=True)
    if "pub_date" not in d.columns:
        return
    yr = as_ts_series(d["pub_date"]).dt.year
    for y, g in d.groupby(yr):
        if not np.isfinite(y):
            continue
        name = f"report_index_{source}_{int(y)}"
        old = VAULT.get_table(name, scope="shared")
        merged = g
        if old is not None and len(old):
            cols = list(dict.fromkeys(list(old.columns) + list(g.columns)))
            merged = pd.concat([old.reindex(columns=cols), g.reindex(columns=cols)],
                               ignore_index=True)
            if "src_report_id" in merged.columns:
                merged = merged.drop_duplicates(["source", "src_report_id"], keep="last")
        VAULT.put_table(name, merged, scope="shared", domain="research",
                        source=f"{source} index shard",
                        extra={"note": "리포트 인덱스 연도 샤드 — 전 전략 공용"})
    if final:
        VAULT.flush("shared")


def ncq_load_cached_index() -> List[pd.DataFrame]:
    """드라이브 공용 인덱스에 이미 있는 리포트 원장/샤드를 전부 끌어온다.

    ★ 사용자의 기존 캐시(다른 전략이 만든 research_report_master 포함)를 **적극 재활용**한다.
      이게 있으면 네트워크가 막혀도 백테스트가 성립한다.
    """
    out: List[pd.DataFrame] = []
    master = VAULT.get_table("research_report_master", scope="shared")
    if master is not None and len(master):
        LOG.ok(f"공용 캐시 재활용 — 보고서 원장 {len(master):,}건 "
               f"(다른 전략이 수집한 것도 그대로 씁니다)")
        out.append(master)
    idx = VAULT.load_index("shared")
    if idx is not None and len(idx) and "key" in idx.columns:
        shard_keys = sorted({str(k) for k in idx["key"].astype(str)
                             if k.startswith("report_index_")})
        for k in shard_keys:
            d = VAULT.get_table(k, scope="shared")
            if d is not None and len(d):
                out.append(d)
        if shard_keys:
            LOG.info(f"공용 캐시 연도 샤드 {len(shard_keys)}개 재활용")
    return out


# ── 통합 수집 ───────────────────────────────────────────────────────────────────────────────
def collect_report_index(months: pd.DatetimeIndex, sec: pd.DataFrame) -> pd.DataFrame:
    """Phase 1 전체. 캐시 우선 → 부족분만 신규 수집 → 다중소스 병합 → 공용/전용 인덱스 저장."""
    frames = ncq_load_cached_index()
    n_cached = int(sum(len(f) for f in frames))

    if RESEARCH_COLLECT and RUN_MODE != "CACHED":
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도(소스별 QPS 상한·워커 4 이하)로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        with PhaseBudget("P1", NCQ_PHASE_BUDGET_S["P1"], on_exceed="L3") as B:
            for src in list(RESEARCH_SOURCES):
                if not B.check():
                    break
                d = ncq_collect_source_by_month(src, months, B)
                if d is not None and len(d):
                    frames.append(d)
    else:
        LOG.info(f"신규 수집을 하지 않습니다 (RUN_MODE={RUN_MODE}, "
                 f"RESEARCH_COLLECT={RESEARCH_COLLECT}) — 캐시만 사용합니다.")

    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.error("리포트를 한 건도 확보하지 못했습니다. 캐시도 비어 있고 신규 수집도 실패했습니다. "
                  "이 상태에서는 신규 커버리지 이벤트가 정의될 수 없으므로 백테스트를 진행하지 않습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    REP = build_report_master(frames, sec)
    if REP.empty:
        return REP

    # 스폰서 태깅 — 병합 후 source 는 "naver+hankyung" 같은 합성 토큰이 될 수 있다.
    src_s = REP["source"].astype(str)
    REP["is_sponsored"] = src_s.str.contains("irs", case=False, na=False)

    # 매핑 실패율 (명세 §6.3 — 실패 건을 버리지 않고 결손율로 노출)
    n_all = len(REP)
    n_nocode = int(REP["stock_code"].isna().sum())
    fail_rate = n_nocode / max(n_all, 1)
    manifest_put("ticker_map_fail_rate", round(fail_rate, 4))
    manifest_put("report_index_total", int(n_all))
    manifest_put("report_index_cached_reused", int(n_cached))
    if fail_rate > NCQ_MAP_FAIL_WARN_FRAC:
        LOG.warn(f"종목명→티커 매핑 실패율 {100*fail_rate:.1f}% (> {100*NCQ_MAP_FAIL_WARN_FRAC:.0f}%). "
                 f"사명 변경 이력이 반영되지 않은 구간이 있을 수 있습니다. 실패 건은 버리지 않고 "
                 f"ticker=NULL 로 보존되며, 커버리지 이력에서 빠지므로 '가짜 신규'를 만들 수 있습니다.")
    else:
        LOG.ok(f"종목명→티커 매핑 실패율 {100*fail_rate:.2f}% ({n_nocode:,}/{n_all:,}건)")

    VAULT.put_table("research_report_master", REP, scope="shared", domain="research",
                    source="+".join(RESEARCH_SOURCES))
    VAULT.put_table(f"report_index_{STRATEGY_ID}", REP, scope="private", domain="research",
                    source="strategy view")
    VAULT.flush()
    PIPE.io("OUT", "DRIVE", "research_report_master", REP, source="naver+hankyung+irs")
    return REP


# ── 커버리지 완결성 진단 (명세 §6.4 — 이 전략의 생사를 가름) ────────────────────────────────
def coverage_completeness(REP: pd.DataFrame, months: pd.DatetimeIndex
                          ) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """월별 리포트 건수의 계단형 하락을 아카이브 결손으로 판정하고, 유효 백테스트 시작월을 정한다.

    판정 규칙(§6.4-3): 특정 월의 총 건수가 **직후 12개월 중앙값의 40% 미만**이면 결손.
    확정 규칙(§6.4-4): **연속 3개월 이상 결손인 구간 이전은 백테스트 시작점에서 배제**한다.

    ★ '직후 12개월'을 쓰는 이유: 과거로 갈수록 아카이브가 얕아지는 것이 결손의 전형적 형태라,
      직전 구간과 비교하면 결손이 결손을 정상으로 만들어 버린다. 미래 방향 기준선이 필요하다.
      이 기준선은 **진단 전용**이며 신호 산출에는 절대 쓰이지 않는다(누수 아님).
    """
    cols = ["month", "n_reports", "n_codes", "n_brokers", "base12", "ratio", "archive_incomplete"]
    if REP is None or REP.empty:
        LOG.error("보고서 원장이 비어 완결성 진단을 할 수 없습니다.")
        return pd.DataFrame(columns=cols), as_ts(BACKTEST_START)

    r = REP.copy()
    r["month"] = as_ts_series(r["pub_date"]) + pd.offsets.MonthEnd(0)
    r = r.dropna(subset=["month"])
    g = r.groupby("month", observed=True)
    D = pd.DataFrame({
        "n_reports": g["report_uid"].nunique(),
        "n_codes": g["stock_code"].nunique(),
        "n_brokers": g["broker_id"].nunique(),
    }).reindex(months).fillna(0).reset_index().rename(columns={"index": "month"})
    if "month" not in D.columns:
        D = D.rename(columns={D.columns[0]: "month"})

    n = D["n_reports"].to_numpy(dtype=float)
    base = np.full(len(n), np.nan)
    for i in range(len(n)):
        fut = n[i + 1: i + 13]
        if len(fut) >= 6:
            base[i] = float(np.median(fut))
    D["base12"] = base
    D["ratio"] = np.where(np.isfinite(base) & (base > 0), n / base, np.nan)
    D["archive_incomplete"] = np.isfinite(D["ratio"]) & (D["ratio"] < NCQ_ARCHIVE_DEFICIT_FRAC)

    # 연속 결손 구간 탐지 → 마지막 결손 런의 끝 다음 달이 유효 시작월
    flags = D["archive_incomplete"].to_numpy()
    valid_idx = 0
    runs = []
    i = 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            if (j - i + 1) >= NCQ_ARCHIVE_RUN_MONTHS:
                runs.append((i, j))
                valid_idx = max(valid_idx, j + 1)
            i = j + 1
        else:
            i += 1

    valid_idx = min(valid_idx, len(D) - 1) if len(D) else 0
    valid_start = as_ts(D["month"].iloc[valid_idx]) if len(D) else as_ts(BACKTEST_START)

    n_bad = int(flags.sum())
    LOG.banner("커버리지 완결성 진단 (§6.4)",
               "아카이브 결손 = 가짜 신규 커버리지의 최대 원인. 이 진단이 유일한 방어선이다.")
    LOG.info(f"결손 판정 월 {n_bad}/{len(D)}개 · 연속 {NCQ_ARCHIVE_RUN_MONTHS}개월 이상 결손 구간 "
             f"{len(runs)}개")
    for a, b in runs[:8]:
        LOG.warn(f"  결손 구간: {D['month'].iloc[a]:%Y-%m} ~ {D['month'].iloc[b]:%Y-%m} "
                 f"({b-a+1}개월, 직후12M 중앙값 대비 "
                 f"{100*np.nanmean(D['ratio'].iloc[a:b+1]):.0f}%)")
    yrs = (as_ts(BACKTEST_END) - valid_start).days / 365.25
    LOG.ok(f"유효 백테스트 시작월 확정: {valid_start:%Y-%m} → 유효 윈도우 {yrs:.1f}년")
    manifest_put("archive_incomplete_months", int(n_bad))
    manifest_put("archive_deficit_runs", [[str(D['month'].iloc[a].date()),
                                           str(D['month'].iloc[b].date())] for a, b in runs])
    manifest_put("valid_backtest_start", str(valid_start.date()))
    manifest_put("valid_backtest_years", round(float(yrs), 2))

    if yrs < NCQ_MIN_VALID_YEARS:
        LOG.error(f"유효 윈도우가 {yrs:.1f}년으로 최소 기준 {NCQ_MIN_VALID_YEARS:.0f}년 미만입니다. "
                  f"명세 §15-2 에 따라 백테스트를 진행하지 않고 사용자 판단을 요청합니다. "
                  f"원인은 대개 네이버 리서치의 과거 페이지네이션 깊이 제한입니다. "
                  f"드라이브 캐시에 과거 리포트를 더 확보하거나, IR협의회 단독 + 짧은 윈도우로 "
                  f"재설계해야 합니다.")
    VAULT.put_table(f"coverage_diagnostics_{STRATEGY_ID}", D, scope="private",
                    domain="diagnostics", source="coverage_completeness")
    PIPE.io("OUT", "MEM", "coverage_diagnostics", D)
    return D, valid_start
