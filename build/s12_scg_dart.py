

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 실적 실측치(A) · 주식총수 · 정기공시 접수일                                   ║
# ║                                                                                          ║
# ║  ★ 호출량 정책 — v1 의 "19,000 하드코딩" 을 제거했다.                                       ║
# ║    · 사전 상한 없음. 한도 판정 권한은 오직 DART 응답 status="020" 에 있다.                  ║
# ║    · 남은 호출량을 실시간으로 추적해 진행률과 함께 출력한다.                                 ║
# ║    · 하루 경계는 **KST 자정**. Colab VM 은 보통 UTC 라 이걸 안 맞추면 9시간 어긋나           ║
# ║      "남았는데 멈추거나 / 없는데 계속 때리는" 사고가 난다.                                   ║
# ║    · 카운터는 100회마다 + 종료 시 + 소진 시 저장한다(중간에 죽어도 다음 실행이 이어받음).     ║
# ║                                                                                          ║
# ║  ★ 그리고 애초에 적게 쓴다 — 설계로. 실행 로그의 [DART 호출 예산] 표에 산술이 그대로 나온다: ║
# ║      순진한 방식: 2,800사 × 12년 × 4분기 단건 = 134,400 호출 (7일)                          ║
# ║      이 코드   : 공시 날짜스윕 1,200 + 다중회사 배치 336 + 주식총수 12,000 ≈ 13,500 (1일)   ║
# ║      그리고 전부 드라이브 캐시에 남아 두 번째 실행부터는 0 호출이다.                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_DART_BASE = "https://opendart.fss.or.kr/api/"
SCG_DART_MULTI_BATCH = 100          # fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개
SCG_REPRT_ANNUAL = "11011"          # 사업보고서
SCG_KST = _dt.timezone(_dt.timedelta(hours=9))

SCG_DART_STATUS = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class ScgDartQuota:
    """DART 일일 호출량 관리자 — 한도를 '추측'하지 않고 '관측'한다.

    OpenDART 에는 잔여 호출량을 알려주는 엔드포인트가 없다(확인함). 그래서:
      · 우리가 오늘 쓴 횟수는 정확히 센다 (드라이브에 KST 날짜와 함께 영속)
      · '남은 양'은 공식 한도 20,000 에서 뺀 **추정치**로만 표시한다
      · 실제 중단 판정은 오직 status="020" 이다. 추정치가 남았다고 계속 때리지 않고,
        추정치가 0 이라고 미리 멈추지도 않는다 (DART_DAILY_LIMIT=None 기본값)
    """
    OFFICIAL_LIMIT = 20_000

    def __init__(self):
        self.today = _dt.datetime.now(SCG_KST).date().isoformat()   # ★ KST 기준
        self.n = 0
        self.exhausted = False
        self.n_020 = 0
        self._lk = threading.Lock()
        self._dirty = 0
        self._load()

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_quota.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
                self.exhausted = bool(j.get("exhausted", False))
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘(KST {self.today}) 이미 사용한 DART 호출 {self.n:,}건 — 이어서 진행합니다."
                     + ("  ※ 이미 한도 소진 상태로 기록되어 있습니다." if self.exhausted else ""))

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n, "exhausted": self.exhausted}))
            self._dirty = 0
        except Exception:
            pass

    def est_remaining(self) -> int:
        cap = DART_DAILY_LIMIT if DART_DAILY_LIMIT else self.OFFICIAL_LIMIT
        return max(0, int(cap) - self.n - int(DART_RESERVE_CALLS or 0))

    def take(self, k: int = 1) -> bool:
        """호출 예약. 최악(재시도 포함)을 먼저 잡고 실제 시도 후 차액을 환급한다."""
        with self._lk:
            if self.exhausted:
                return False
            #  사용자가 명시적으로 상한을 정한 경우에만 사전 차단한다. 기본(None)은 무제한.
            if DART_DAILY_LIMIT is not None and \
               self.n + k > int(DART_DAILY_LIMIT) - int(DART_RESERVE_CALLS or 0):
                if not self.exhausted:
                    self.exhausted = True
                    self._save()
                    LOG.warn(f"사용자 지정 상한 DART_DAILY_LIMIT={DART_DAILY_LIMIT:,} 에 도달했습니다. "
                             f"(DART 서버가 막은 것이 아닙니다 — None 으로 두면 서버가 020 을 줄 "
                             f"때까지 씁니다)")
                return False
            self.n += k
            self._dirty += k
            if self._dirty >= 100:
                self._save()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def hit_limit(self):
        """DART 가 020 을 반환했다 — 이것이 유일한 진짜 한도 신호다."""
        with self._lk:
            self.n_020 += 1
            if not self.exhausted:
                self.exhausted = True
                self._save()
                LOG.warn(f"DART 가 요청제한(020)을 반환했습니다. 오늘 사용량 {self.n:,}건. "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일(KST 자정 이후) "
                         f"같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")

    def close(self):
        self._save()

    def report(self):
        cap = DART_DAILY_LIMIT if DART_DAILY_LIMIT else self.OFFICIAL_LIMIT
        LOG.table([["오늘 날짜 (KST)", self.today],
                   ["사용한 호출", f"{self.n:,}"],
                   ["공식 일일 한도", f"{self.OFFICIAL_LIMIT:,}"],
                   ["사용자 지정 상한", f"{DART_DAILY_LIMIT:,}" if DART_DAILY_LIMIT else "없음(자동)"],
                   ["남은 호출 (추정)", f"{self.est_remaining():,}"],
                   ["020 응답 횟수", f"{self.n_020:,}"],
                   ["상태", "소진 — 내일 이어받기" if self.exhausted else "여유"]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출 예산 — 잔여량은 추정치이고, 중단 판정은 서버의 020 응답이 합니다")


SCG_QUOTA: Optional[ScgDartQuota] = None


def scg_dart_api(endpoint: str, params: dict, tries: int = 2) -> Optional[dict]:
    """DART 호출 1회. 예산 예약 → 실제 시도 → 차액 환급 → status 해석."""
    if not DART_API_KEY:
        return None
    q = SCG_QUOTA
    if q is not None and not q.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    att = {"n": 0}
    js = http_json(SCG_DART_BASE + endpoint, source="dart", params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: att.__setitem__("n", att["n"] + 1))
    if q is not None:
        q.refund(max(0, tries - max(1, att["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "020":
            if q is not None:
                q.hit_limit()
        elif st == "021":
            #  021 = '조회 가능한 회사 개수 초과' — 배치 크기 문제이지 일일 한도가 아니다.
            #  이걸 소진으로 처리하면 그 순간부터 모든 DART 수집이 조용히 꺼진다.
            LOG.warn(f"DART status=021 (조회 가능한 회사 개수 초과) — 배치 크기를 줄이세요 "
                     f"(SCG_DART_MULTI_BATCH={SCG_DART_MULTI_BATCH}). 일일 한도와 무관합니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({SCG_DART_STATUS.get(st,'?')}). "
                      f"DART_API_KEY 를 확인하세요 — https://opendart.fss.or.kr 에서 재발급 가능합니다.")
            if q is not None:
                q.exhausted = True
        elif st != "013":
            LOG.debug(f"DART status={st} ({SCG_DART_STATUS.get(st,'?')}) ep={endpoint}")
        return None
    return js


def _scg_rcept_date(rcept_no: Any) -> Optional[pd.Timestamp]:
    """rcept_no 앞 8자리 = 접수일자. PIT 의 근거는 결산일이 아니라 이 날짜다."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    return None


# ── ① 정기공시 날짜 스윕 — 실적 '발표일' 의 원천 ────────────────────────────────────────────
_SCG_ANNUAL_RE = re.compile(r"사업보고서")
_SCG_YEAR_IN_NM = re.compile(r"\((\d{4})\.\d{2}\)")


def scg_fetch_periodic_disclosures(start: str, end: str) -> pd.DataFrame:
    """list.json 을 **날짜로 스윕**한다 — 회사별로 도는 것보다 수십 배 싸다.

    10년치 정기공시 ≈ 11만 건 = 100건/페이지 → 약 1,100 호출. 회사별이면 134,400 호출이다.
    ★ 여기서 얻는 rcept_dt 가 곧 actual_announcement_date 이고, PIT 의 유일한 근거다.
    """
    cols = ["corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm", "bsns_year"]
    cached = VAULT.get_table("dart_periodic_disclosures", scope="shared")
    have_to = None
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have_to = cached["rcept_dt"].max()
        LOG.info(f"공용 캐시에서 정기공시 {len(cached):,}건 재사용 (~{have_to.date()})")
        if have_to >= as_ts(end) - pd.Timedelta(days=7):
            return cached.reindex(columns=cols)
    if not DART_API_KEY:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    bgn = (have_to + pd.Timedelta(days=1)) if have_to is not None else as_ts(start)
    fin = as_ts(end)
    rows: List[dict] = []
    #  분기별로 끊어 요청한다 (한 구간의 total_page 가 너무 커지지 않도록)
    #  ★ date_range(freq="QS") 는 bgn 이 분기 중간이면 '다음 분기 시작'부터 시작한다.
    #    그러면 이어받기 지점과 그 분기 시작 사이의 공시가 영구히 누락된다
    #    (다음 실행은 더 늦은 지점부터 시작하므로 영영 메워지지 않는다). bgn 을 앞에 붙인다.
    periods = pd.date_range(bgn, fin, freq="QS").tolist()
    if not periods or periods[0] > bgn:
        periods.insert(0, bgn)
    if periods[-1] < fin:
        periods.append(fin)
    for i in range(len(periods) - 1 if len(periods) > 1 else 1):
        b = periods[i]
        e = min(periods[i + 1] - pd.Timedelta(days=1) if len(periods) > 1 else fin, fin)
        if b > e:
            continue
        page = 1
        while True:
            js = scg_dart_api("list.json", {
                "bgn_de": b.strftime("%Y%m%d"), "end_de": e.strftime("%Y%m%d"),
                "pblntf_ty": "A", "page_no": str(page), "page_count": "100"})
            if not js or not isinstance(js.get("list"), list):
                break
            for r in js["list"]:
                rows.append({"corp_code": r.get("corp_code"),
                             "stock_code": to_code6(r.get("stock_code")),
                             "rcept_no": r.get("rcept_no"), "rcept_dt": r.get("rcept_dt"),
                             "report_nm": r.get("report_nm")})
            tp = int(js.get("total_page", 1) or 1)
            if page >= tp or page >= 200:
                break
            page += 1
            if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
                break
        if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
            LOG.warn("일일 한도로 정기공시 스윕을 중단합니다 — 받은 만큼 저장하고 이어받습니다.")
            break

    if rows:
        new = pd.DataFrame(rows)
        new["rcept_dt"] = as_ts_series(new["rcept_dt"])
        yr = new["report_nm"].astype(str).str.extract(_SCG_YEAR_IN_NM)[0]
        new["bsns_year"] = pd.to_numeric(yr, errors="coerce")
        allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
        allr = allr.dropna(subset=["rcept_no"]).drop_duplicates("rcept_no", keep="last")
        VAULT.put_table("dart_periodic_disclosures", allr, scope="shared", domain="dart",
                        source="opendart list.json sweep")
        VAULT.flush("shared")
        PIPE.io("OUT", "DRIVE", "dart_periodic_disclosures", allr, source="opendart list.json")
        LOG.ok(f"정기공시 {len(allr):,}건 확보 (신규 {len(new):,}건)")
        return allr.reindex(columns=cols)
    return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)


def scg_annual_report_dates(dis: pd.DataFrame) -> Dict[Tuple[str, int], pd.Timestamp]:
    """(종목코드, 사업연도) → 사업보고서 접수일. EPS 의 '실적/추정' 판정과 A_date 의 근거."""
    if dis is None or dis.empty:
        return {}
    d = dis[dis["report_nm"].astype(str).str.contains(_SCG_ANNUAL_RE, na=False)].copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt", "stock_code"])
    if "bsns_year" not in d.columns or d["bsns_year"].isna().all():
        #  보고서명에서 연도를 못 뽑았으면 접수연도-1 로 본다(3월 제출이 통례)
        d["bsns_year"] = d["rcept_dt"].dt.year - 1
    d["bsns_year"] = pd.to_numeric(d["bsns_year"], errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    #  같은 (종목,연도)에 정정공시가 여러 건이면 **최초 접수일**을 쓴다 (보수적 = PIT 안전)
    d = d.sort_values("rcept_dt").drop_duplicates(["stock_code", "bsns_year"], keep="first")
    return {(str(c), int(y)): t for c, y, t in
            zip(d["stock_code"], d["bsns_year"], d["rcept_dt"])}


# ── ② 다중회사 주요계정 — 순이익·자본금을 100사/호출로 ────────────────────────────────────
def scg_fetch_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """fnlttMultiAcnt — 100사를 한 번에. 순진한 단건 호출 대비 100배 싸다."""
    cols = ["corp_code", "bsns_year", "fs_div", "account_nm", "thstrm_amount", "rcept_no"]
    cached = VAULT.get_table("dart_multi_annual", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str),
                       pd.to_numeric(cached["bsns_year"], errors="coerce").fillna(0).astype(int)))
        LOG.info(f"공용 캐시에서 다중회사 주요계정 {len(cached):,}행 재사용")
    if not DART_API_KEY:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    corps = [str(c) for c in pd.unique(pd.Series(list(corp_codes))) if c and str(c) != "nan"]
    jobs = []
    for y in sorted(years, reverse=True):            # 최근 연도부터 — 끊겨도 최신이 먼저 완성
        todo = [c for c in corps if (c, int(y)) not in done]
        for k in range(0, len(todo), SCG_DART_MULTI_BATCH):
            jobs.append((todo[k:k + SCG_DART_MULTI_BATCH], int(y)))
    if not jobs:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    LOG.info(f"다중회사 주요계정: {len(jobs):,} 호출 예정 "
             f"(오늘 남은 호출 추정 {SCG_QUOTA.est_remaining():,}건)" if SCG_QUOTA else "")

    def _one(job):
        batch, y = job
        js = scg_dart_api("fnlttMultiAcnt.json",
                          {"corp_code": ",".join(batch), "bsns_year": str(y),
                           "reprt_code": SCG_REPRT_ANNUAL})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        for c in cols:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        return d[cols]

    out = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(100사/호출)")
    frames = [f for f in out if f is not None and len(f)]
    if not frames:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    new = pd.concat(frames, ignore_index=True)
    allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
    allr = allr.drop_duplicates(["corp_code", "bsns_year", "fs_div", "account_nm"], keep="last")
    VAULT.put_table("dart_multi_annual", allr, scope="shared", domain="dart",
                    source="opendart fnlttMultiAcnt")
    VAULT.flush("shared")
    LOG.ok(f"다중회사 주요계정 {len(allr):,}행 (신규 {len(new):,}행 · 호출 {len(jobs):,}회)")
    return allr.reindex(columns=cols)


_SCG_NI_RE = re.compile(r"당기순이익")
_SCG_CAP_RE = re.compile(r"자본금")


def scg_tidy_multi(multi: pd.DataFrame) -> pd.DataFrame:
    """주요계정 → (corp_code, bsns_year) × {net_income, capital_stock, knowledge_date}."""
    cols = ["corp_code", "bsns_year", "net_income", "capital_stock", "knowledge_date"]
    if multi is None or multi.empty:
        return pd.DataFrame(columns=cols)
    d = multi.copy()
    #  ★ 연결(CFS)과 별도(OFS)를 한 회사·한 해에 섞으면 순이익이 두 기준으로 뒤섞여
    #    EPS 실측치가 조용히 틀어진다. 연결이 있으면 연결만, 없으면 별도만 쓴다.
    if "fs_div" in d.columns and d["fs_div"].notna().any():
        pref = d.assign(_p=np.where(d["fs_div"].astype(str).str.upper().eq("CFS"), 0, 1))
        best = pref.groupby(["corp_code", "bsns_year"], observed=True)["_p"].transform("min")
        n0 = len(d)
        d = pref[pref["_p"] == best].drop(columns=["_p"])
        if len(d) < n0:
            LOG.debug(f"연결/별도 혼합 제거: {n0:,} → {len(d):,}행 (회사·연도별 연결 우선)")
    d["amt"] = pd.to_numeric(d["thstrm_amount"].astype(str).str.replace(",", "", regex=False),
                             errors="coerce")
    nm = d["account_nm"].astype(str)
    d["_ni"] = np.where(nm.str.contains(_SCG_NI_RE, na=False), d["amt"], np.nan)
    d["_cap"] = np.where(nm.str.contains(_SCG_CAP_RE, na=False), d["amt"], np.nan)
    g = d.groupby(["corp_code", "bsns_year"], observed=True, sort=False)
    out = g.agg(net_income=("_ni", "max"), capital_stock=("_cap", "max"),
                rcept_no=("rcept_no", "min")).reset_index()
    out["knowledge_date"] = out["rcept_no"].map(_scg_rcept_date)
    #  접수번호가 없으면 사업보고서 법정기한(결산 후 90일)으로 보수적 추정 — 늦게 아는 방향이라
    #  미래누수를 만들지 않는다
    miss = out["knowledge_date"].isna()
    if miss.any():
        out.loc[miss, "knowledge_date"] = pd.to_datetime(
            out.loc[miss, "bsns_year"].astype(int).astype(str) + "-12-31") + pd.Timedelta(days=90)
    return out[cols]


# ── ③ 주식총수 — PIT 시가총액의 필수 입력 ────────────────────────────────────────────────
def scg_fetch_shares(corp_map: pd.DataFrame, years: Sequence[int],
                     priority_codes: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """stockTotqySttus — 보통주 발행주식총수. 회사×연도 단건이라 비싸므로 우선순위를 둔다.

    ★ 끊겨도 쓸모 있게 순서를 잡는다: (애널리스트 커버리지 있는 종목) → (최근 연도) 순.
      일일 한도로 중간에 멈춰도 '분석에 실제로 쓰이는 종목의 최신 데이터'가 먼저 채워진다.
    ★ 못 채운 회사는 자본금/액면가 로 역산해 메운다(scg_shares_panel).
    """
    cols = ["corp_code", "code", "bsns_year", "shares", "par_value", "knowledge_date"]
    cached = VAULT.get_table("dart_shares_outstanding", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str),
                       pd.to_numeric(cached["bsns_year"], errors="coerce").fillna(0).astype(int)))
        LOG.info(f"공용 캐시에서 주식총수 {len(cached):,}행 재사용")
    if not DART_API_KEY or corp_map is None or corp_map.empty:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
    prio = set(str(c) for c in (priority_codes or []))
    cm = cm.assign(_p=cm["code"].astype(str).isin(prio).astype(int))
    cm = cm.sort_values("_p", ascending=False)
    jobs = [(str(r.corp_code), str(r.code), int(y))
            for y in sorted(years, reverse=True)
            for r in cm.itertuples(index=False)
            if (str(r.corp_code), int(y)) not in done]
    if not jobs:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    est = SCG_QUOTA.est_remaining() if SCG_QUOTA else 0
    LOG.info(f"주식총수: 미확보 {len(jobs):,}건 · 오늘 남은 호출 추정 {est:,}건. "
             f"{'오늘 안에 끝납니다.' if len(jobs) <= est else '오늘 다 못 받으면 내일 이어받습니다(캐시 보존).'}")

    def _one(job):
        corp, code, y = job
        js = scg_dart_api("stockTotqySttus.json",
                          {"corp_code": corp, "bsns_year": str(y),
                           "reprt_code": SCG_REPRT_ANNUAL})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        tot = par = None
        rc = None
        for r in js["list"]:
            se = str(r.get("se", ""))
            rc = rc or r.get("rcept_no")
            if "보통주" not in se and "합계" not in se:
                continue
            v = pd.to_numeric(str(r.get("istc_totqy", "")).replace(",", ""), errors="coerce")
            if pd.notna(v) and v > 0 and ("보통주" in se or tot is None):
                tot = float(v)
                p = pd.to_numeric(str(r.get("stlm_dt", "")).replace(",", ""), errors="coerce")
                par = float(p) if pd.notna(p) else par
                if "보통주" in se:
                    break
        if not tot:
            return None
        return {"corp_code": corp, "code": code, "bsns_year": int(y), "shares": tot,
                "par_value": par, "knowledge_date": _scg_rcept_date(rc)}

    rows: List[dict] = []
    CH = 3000
    for k0 in range(0, len(jobs), CH):
        part = jobs[k0:k0 + CH]
        out = pmap_io(_one, part, workers=min(N_WORKERS_IO, 8),
                      desc=f"DART 주식총수 {k0//CH+1}/{(len(jobs)-1)//CH+1}")
        rows += [r for r in out if r]
        if rows:
            new = pd.DataFrame(rows)
            allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
            allr = allr.drop_duplicates(["corp_code", "bsns_year"], keep="last")
            VAULT.put_table("dart_shares_outstanding", allr, scope="shared", domain="dart",
                            source="opendart stockTotqySttus")
            VAULT.flush("shared")
            cached, rows = allr, []
        if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
            LOG.warn("일일 한도로 주식총수 수집을 중단합니다 — 캐시는 보존되며 내일 이어받습니다.")
            break
    res = cached if cached is not None else pd.DataFrame(columns=cols)
    LOG.ok(f"주식총수 {len(res):,}행 확보")
    return res.reindex(columns=cols)


def scg_shares_panel(shares: pd.DataFrame, tidy_multi: pd.DataFrame,
                     corp_map: pd.DataFrame) -> pd.DataFrame:
    """주식총수 패널 — 직접 조회분 + 자본금/액면가 역산분.

    ★ 역산이 왜 정당한가: 자본금 = 발행주식수 × 액면가 는 회계 항등식이다.
      액면가는 회사별로 거의 불변이므로, 직접 조회된 연도에서 액면가를 구해
      나머지 연도의 자본금에 나누면 주식수가 복원된다. 액면분할이 있으면
      액면가가 바뀌므로, 연도별로 가장 가까운 관측 액면가를 쓴다.
    """
    cols = ["code", "bsns_year", "shares", "knowledge_date", "src"]
    parts = []
    if shares is not None and len(shares):
        s = shares.dropna(subset=["code", "shares"]).copy()
        s["src"] = "dart_stockTotqySttus"
        parts.append(s.reindex(columns=cols))
        #  액면가 = 자본금 / 주식수 (직접 관측된 연도에서 산출)
        par = None
        if tidy_multi is not None and len(tidy_multi):
            j = s.merge(tidy_multi, on=["corp_code", "bsns_year"], how="inner")
            j["par_est"] = j["capital_stock"] / j["shares"].replace(0, np.nan)
            par = (j[np.isfinite(j["par_est"]) & (j["par_est"] > 0)]
                   .groupby("corp_code")["par_est"].median())
        if par is not None and len(par) and tidy_multi is not None and len(tidy_multi):
            cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
            t = tidy_multi.merge(cm[["corp_code", "code"]], on="corp_code", how="inner")
            t["_par"] = t["corp_code"].map(par)
            have = set(zip(s["corp_code"].astype(str),
                           s["bsns_year"].astype(int))) if "corp_code" in s.columns else set()
            t = t[~t.apply(lambda r: (str(r["corp_code"]), int(r["bsns_year"])) in have, axis=1)]
            t = t[t["_par"].notna() & (t["_par"] > 0) & t["capital_stock"].notna()]
            if len(t):
                t["shares"] = t["capital_stock"] / t["_par"]
                t["src"] = "derived_capital/par"
                parts.append(t.reindex(columns=cols))
                LOG.info(f"자본금/액면가 역산으로 주식총수 {len(t):,}행 추가 확보 "
                         f"(DART 호출 0회 — 이미 받은 주요계정을 재활용)")
    if not parts:
        return pd.DataFrame(columns=cols)
    P = pd.concat(parts, ignore_index=True).dropna(subset=["code", "shares", "knowledge_date"])
    P = P.sort_values(["code", "knowledge_date"]).drop_duplicates(
        ["code", "bsns_year"], keep="last")
    return P.reindex(columns=cols)


# ── ④ EPS 실측치 ─────────────────────────────────────────────────────────────────────────
def scg_build_eps_actuals(tidy_multi: pd.DataFrame, shares_panel: pd.DataFrame,
                          corp_map: pd.DataFrame, annual_dates: Dict[Tuple[str, int], pd.Timestamp]
                          ) -> pd.DataFrame:
    """실적 실측치 A = 당기순이익 / 발행주식수 (§3 actuals 테이블).

    ★ actual_announcement_date 는 결산일이 아니라 **사업보고서 접수일**이다.
      이걸 결산일(12/31)로 두면 3월에야 알 수 있었던 실적을 1월부터 알았던 것이 되어
      §35 TEST 6(미래누수)이 즉시 깨진다.
    """
    cols = ["stock_id", "fiscal_period", "forecast_metric",
            "actual_value", "actual_announcement_date"]
    if tidy_multi is None or tidy_multi.empty or shares_panel is None or shares_panel.empty:
        LOG.warn("순이익 또는 주식총수가 없어 EPS 실측치를 만들 수 없습니다 → "
                 "EPS 트랙의 ACC* 는 전부 0 으로 수축됩니다(애널리스트는 유지).")
        return pd.DataFrame(columns=cols)
    cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
    t = tidy_multi.merge(cm[["corp_code", "code"]], on="corp_code", how="inner")
    s = shares_panel[["code", "bsns_year", "shares"]].drop_duplicates(["code", "bsns_year"])
    t = t.merge(s, on=["code", "bsns_year"], how="inner")
    t = t[t["net_income"].notna() & t["shares"].notna() & (t["shares"] > 0)]
    if t.empty:
        return pd.DataFrame(columns=cols)
    t["eps"] = t["net_income"] / t["shares"]

    #  발표일: 사업보고서 접수일 → 없으면 주요계정 rcept 기반 knowledge_date
    key = list(zip(t["code"].astype(str), t["bsns_year"].astype(int)))
    ad = pd.Series([annual_dates.get(k, pd.NaT) for k in key], index=t.index)
    t["actual_announcement_date"] = ad.fillna(as_ts_series(t["knowledge_date"]))
    t = t.dropna(subset=["actual_announcement_date"])
    out = pd.DataFrame({
        "stock_id": t["code"].astype(str),
        "fiscal_period": t["bsns_year"].astype(int).astype(str) + "-12",
        "forecast_metric": "EPS",
        "actual_value": t["eps"].astype("float64"),
        "actual_announcement_date": t["actual_announcement_date"],
    })
    out = out.drop_duplicates(["stock_id", "fiscal_period"], keep="first")
    LOG.ok(f"EPS 실측치 {len(out):,}건 ({out['stock_id'].nunique():,}종목) — "
           f"발표일은 사업보고서 접수일 기준")
    return out.reset_index(drop=True)


def scg_report_dart_plan(n_corps: int, n_years: int, n_covered: int):
    """★ 사용자가 요구한 '호출량 산술' 을 그대로 표로 낸다."""
    naive = n_corps * n_years * 4
    sweep = max(1, int(n_corps * n_years * 4 / 100))
    multi = max(1, int(np.ceil(n_corps / SCG_DART_MULTI_BATCH)) * n_years)
    shr = n_covered * n_years
    LOG.table([
        ["① corpCode.xml (1회)", "1", "회사 ↔ 종목코드 매핑"],
        ["② 정기공시 날짜스윕 (100건/페이지)", f"~{sweep:,}", "실적 발표일 — 회사별 호출 대비 100배 절약"],
        ["③ 다중회사 주요계정 (100사/호출)", f"~{multi:,}", "순이익·자본금 — 단건 대비 100배 절약"],
        ["④ 주식총수 (회사×연도)", f"~{shr:,}", "커버리지 있는 종목 우선 · 자본금/액면가 역산으로 보완"],
        ["합계 (최초 콜드빌드)", f"~{1+sweep+multi+shr:,}", "일 20,000 한도 기준 1~2일"],
        ["순진한 방식이었다면", f"~{naive:,}", "회사×연도×분기 단건 호출 = 7일"],
        ["두 번째 실행부터", "0", "전부 드라이브 공용 캐시에서 재사용"],
    ], ["항목", "호출 수", "설명"], ["l", "r", "l"],
        title="DART 호출 예산 산술 — 상한을 미리 정하지 않고, 설계로 호출을 줄인다")
