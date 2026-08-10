

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  PIT 저장소 / 유니버스 / 셀  (계약 C1·C2·C3·C4·C11)                                 ║
# ║                                                                                          ║
# ║  C1: 모든 데이터 접근은 PIT.get(table, as_of) 한 곳만 통과한다.                            ║
# ║      DataFrame 직접 슬라이싱 금지. 우회 파라미터를 만들지 않는다.                          ║
# ║  C2: 유니버스는 상장폐지 종목을 포함한다. 정리매매가 없으면 -100%.                          ║
# ║  C11: 셀 = (date, industry, size_bucket). 다른 그룹키 금지.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, pd.DataFrame] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: pd.DataFrame, key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            LOG.debug(f"PIT 등록(빈 테이블): {name}")
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[C1 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        d = d.reset_index(drop=True)
        self._t[name] = d
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """시점 as_of 에서 '알 수 있었던' 행만 반환.
        latest_by 를 주면 그 키별 최신 1행(=당시 최신 관측)만 남긴다."""
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        t = as_ts(as_of)
        d = self._t[name]
        if d.empty:
            return d
        # knowledge_date 정렬되어 있으므로 searchsorted 로 O(log n) 절단
        pos = int(np.searchsorted(d["knowledge_date"].values, np.datetime64(t), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def asof_join(self, panel: pd.DataFrame, name: str, by: str,
                  left_time: str = "month", cols: Optional[Sequence[str]] = None,
                  suffix: str = "") -> pd.DataFrame:
        """get() 의 벡터화 등가물. 패널 전체에 대해 한 번에 as-of 결합한다.

        merge_asof(direction='backward') 는 knowledge_date <= month 인 마지막 행만 붙이므로
        C1 과 정확히 동일한 의미를 갖는다. 루프로 get() 을 3만 번 부르는 대신 이걸 쓴다.
        """
        self.access_log[name] += 1
        if name not in self._t or self._t[name].empty or panel.empty:
            return panel
        right = self._t[name]
        if by not in right.columns or by not in panel.columns:
            LOG.debug(f"asof_join 건너뜀: '{name}' 에 결합키 '{by}' 없음")
            return panel
        use = [c for c in (cols or [c for c in right.columns
                                    if c not in ("event_date", "_src")]) if c in right.columns]
        for c in (by, "knowledge_date"):
            if c not in use:
                use.append(c)
        R = (right[use].dropna(subset=["knowledge_date", by])
                        .sort_values("knowledge_date", kind="stable")).copy()
        if R.empty:
            return panel

        # ★★ 결합키가 결측인 패널 행을 '떨어뜨리면' 안 된다. ★★
        #   attach_fundamentals 에서 corp_code 가 없는 종목(대개 상장폐지·신규상장·비DART)이
        #   통째로 사라지면 그게 곧 생존자편향 재유입이다(C2 위반). merge_asof 는 by 키에
        #   NaN 이 있으면 다루지 못하므로, 유효키 부분만 결합한 뒤 전체 패널에 되붙인다.
        base = panel.copy()
        base["_ord"] = np.arange(len(base))
        mask = base[left_time].notna() & base[by].notna()
        n_drop = int((~mask).sum())
        if n_drop:
            LOG.debug(f"asof_join '{name}': 결합키 결측 {n_drop:,}행은 결측값으로 보존합니다"
                      f"(행을 버리지 않습니다 — C2).")
        L = base[mask].copy()
        if L.empty:
            LOG.warn(f"asof_join '{name}': 결합 가능한 행이 없습니다. 결합을 건너뜁니다.")
            return panel
        R[by] = R[by].astype(str)
        L[by] = L[by].astype(str)
        L = L.sort_values(left_time, kind="stable")
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", suffix or "_r"))
        except Exception as e:                                     # noqa
            LOG.warn(f"asof_join 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다. "
                     f"대개 정렬/타입 문제입니다.")
            return panel
        new_cols = [c for c in M.columns if c not in base.columns]
        if not new_cols:
            return panel
        add = M.set_index("_ord")[new_cols]
        out = base.set_index("_ord")
        out = out.join(add, how="left")            # 결합 실패 행은 NaN 으로 남고, 행은 유지된다
        out = out.sort_index().reset_index(drop=True)
        out.index = panel.index
        return out

    def report(self):
        rows = []
        for n, m in self._meta.items():
            rows.append([n, f"{m['rows']:,}",
                         str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                         ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n,0):,}"])
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (C1 — 모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()


# ── 유니버스 (C2) ───────────────────────────────────────────────────────────────────────────
LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    def __init__(self, sec: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame,
                 snap_window_days: int = 100):
        self.sec = sec.copy()
        self.snap = snapshots
        self.attrition: List[dict] = []
        self._cache_at: Dict[pd.Timestamp, List[str]] = {}
        # 스냅샷 주기가 분기면 ±45일 창으로는 대부분의 달이 스냅샷을 못 만난다 → 창을 넓힌다.
        self._snap_window_days = snap_window_days
        self._trading_days = (np.sort(pd.unique(as_ts_series(px_daily["date"]).values))
                              if px_daily is not None and len(px_daily) else
                              np.array([], dtype="datetime64[ns]"))
        self._snap_by_month: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            for d, g in snapshots.groupby("snap_date"):
                self._snap_by_month[as_ts(d)] = set(g["code"])

        self.sec["listing_date"] = as_ts_series(self.sec["listing_date"])
        self.sec["delisting_date"] = as_ts_series(self.sec["delisting_date"])
        self.sec = self.sec.drop_duplicates("code").reset_index(drop=True)

        # 벡터화용 배열 (at() 이 매월 3,500행 itertuples 를 도는 것을 없앤다)
        self._codes_arr = self.sec["code"].to_numpy(dtype=object)
        self._ld_arr = self.sec["listing_date"].to_numpy(dtype="datetime64[ns]")
        self._dd_arr = self.sec["delisting_date"].to_numpy(dtype="datetime64[ns]")
        self._delist = {c: d for c, d in zip(self._codes_arr, self.sec["delisting_date"])
                        if pd.notna(d)}

        # 상장 후 250거래일 시즈닝 — 거래일 배열에 대한 searchsorted 를 한 번에 벡터화
        #
        # ★ 앵커 주의 (조용한 유니버스 붕괴의 원인) ─────────────────────────────────────
        #   searchsorted 는 '가격패널 시작일 이전에 상장한' 종목을 전부 index 0 으로 보낸다.
        #   거기에 +250 을 더하면 1990년 상장 종목조차 "패널 시작 후 250거래일"에야 시즈닝이
        #   끝난 것으로 계산된다. 2016-08 시작 패널이면 2017년 중반까지 삼성전자를 포함한
        #   기존 상장사 전부가 유니버스에서 빠진다. 에러 없이, 로그도 없이.
        #   → 시즈닝의 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은
        #     이미 오래전에 시즈닝이 끝난 것으로 확정한다.
        self._seasoned: Dict[str, Any] = {}
        _FAR = pd.Timestamp("2100-01-01")     # 패널 안에서 시즈닝이 끝나지 않는 신규 상장
        if len(self._trading_days):
            t0 = self._trading_days[0]
            idx = np.searchsorted(self._trading_days, self._ld_arr, side="left")
            idx_s = idx + LISTING_SEASONING_DAYS
            n_td = len(self._trading_days)
            inside = idx_s < n_td
            seas = np.where(inside,
                            self._trading_days[np.minimum(idx_s, n_td - 1)],
                            np.datetime64(_FAR.isoformat(), "ns"))
            # 패널 시작 전 상장 → 달력 1년으로 확정(패널 시작보다 앞서므로 사실상 제약이 아님)
            pre = (~np.isnat(self._ld_arr)) & (self._ld_arr < t0)
            for c, ld, s, p in zip(self._codes_arr, self._ld_arr, seas, pre):
                if np.isnat(ld):
                    self._seasoned[c] = pd.NaT
                elif p:
                    self._seasoned[c] = as_ts(ld) + pd.Timedelta(days=365)
                else:
                    self._seasoned[c] = as_ts(s)
        else:
            for c, ld in zip(self._codes_arr, self._ld_arr):
                self._seasoned[c] = pd.NaT if np.isnat(ld) else as_ts(ld) + pd.Timedelta(days=365)

    def at(self, t) -> List[str]:
        """시점 t 의 유니버스. t 이후 상장 종목이 하나라도 섞이면 그 자체로 C2 위반이다."""
        t = as_ts(t)
        if t in self._cache_at:
            return self._cache_at[t]

        # ① 상장일·폐지일로 유도한 집합이 '기준선'이다. 이건 항상 성립해야 한다.
        base = set(self._codes_dated_at(t))

        # ② 스냅샷은 '보강'이다. 대체가 아니다.
        #    ★ 과거 스냅샷만 쓴다(미래 스냅샷을 고르면 그 자체가 누수).
        #    ★ 교집합이 아니라 합집합이다. 부분 응답 스냅샷으로 기준선을 깎으면
        #      그 달 유니버스가 조용히 줄어 곧바로 선택편향이 된다. 늘리기만 한다.
        past = [d for d in self._snap_by_month if d <= t]
        if past:
            key = max(past)
            if (t - key).days <= self._snap_window_days:
                base |= set(self._snap_by_month[key])

        # ③ 폐지 이후 종목은 어떤 경로로 들어왔든 반드시 제외한다.
        base -= {c for c, dd in self._delist.items() if pd.notna(dd) and dd <= t}

        # ④ 상장 후 250거래일 시즈닝
        out = [c for c in base
               if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]
        out = sorted(out)
        self._cache_at[t] = out
        return out

    def _codes_dated_at(self, t: pd.Timestamp) -> List[str]:
        """상장일/폐지일 기반 멤버십. itertuples 루프를 매월 도는 대신 벡터화한다
        (종목 3,500 × 120개월 = 42만 회 파이썬 루프였다)."""
        ld, dd = self._ld_arr, self._dd_arr
        tt = np.datetime64(t)
        ok = ~((~np.isnat(ld)) & (ld > tt)) & ~((~np.isnat(dd)) & (dd <= tt))
        ok &= ~(np.isnat(ld) & np.isnat(dd))        # 근거가 전혀 없는 종목은 넣지 않는다
        return self._codes_arr[ok].tolist()

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "PIT유니버스", "가격보유", "유동성필터", "거부권통과",
                 "하한선통과", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max", "size"])
        rows = []
        prev = None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/prev:.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§10.4) — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < 5:
            LOG.warn("최종 선정 종목이 월평균 5개 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 어느 게이트가 원인인지 위 표에서 먼저 확인하세요.")


# ── 셀 (C11) ────────────────────────────────────────────────────────────────────────────────
SIZE_BUCKETS = [(0, 50, "<50"), (50, 100, "50-99"), (100, 300, "100-299"),
                (300, 1000, "300-999"), (1000, 10 ** 9, "1000+")]


def size_bucket(n_emp: float) -> str:
    if n_emp is None or not np.isfinite(n_emp) or n_emp <= 0:
        return "미상"
    for lo, hi, lab in SIZE_BUCKETS:
        if lo <= n_emp < hi:
            return lab
    return "1000+"


def build_cells(panel: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell_key = (date, industry, size_bucket). 규모를 넣는 이유는 §5.6-② 참조:
    정부 지원제도 요건 대부분이 기업 규모에 연동되므로 정책효과가 셀 내 공통충격으로 흡수된다.
    비용 0의 오염 제거."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict()
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["industry_l1"] = p["industry"].str.slice(0, 4)                 # 폴백용 상위 단위
    p["size_bucket"] = p["employees"].map(size_bucket) if "employees" in p.columns else "미상"
    ym = p["month"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["industry"] + "|" + p["size_bucket"]
    # 폴백 사다리를 컬럼으로 미리 만들어 둔다. 센서별로 유효 관측이 부족할 때
    # xsec_z_l 이 이 사다리를 타고 내려간다(C11 "산업 상위 단위로 폴백").
    p["cell_l2"] = ym + "|" + p["industry_l1"] + "|ALL"
    p["cell_l3"] = ym + "|ALL|ALL"

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    still_n = 0
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        still_n = int(still.sum())
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백 발생: 1차 {n_small:,}행(산업 상위단위로) / 2차 {still_n:,}행(전체로). "
                 f"C11 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 1단계 {p['cell'].nunique():,}개 · 2단계 {p['cell_l2'].nunique():,}개 · "
              f"3단계 {p['cell_l3'].nunique():,}개")
    return p


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F+  ARC — U-1000 유니버스 (§3) + 분기 패널 조립                                        ║
# ║                                                                                          ║
# ║  §3.1  PIT 시가총액 랭크 '하위 1000종목' (KOSPI+KOSDAQ). 매 리밸일 스냅샷으로 재구성.       ║
# ║  §3.2  직전 60거래일 ADTV ≥ 1억원                                                          ║
# ║  §3.3  관리종목·환기·거래정지·스팩·우선주·리츠·완전자본잠식·상장12개월미만 제외             ║
# ║  §3.4  ★상장폐지 종목을 PIT 스냅샷에 반드시 포함. 정리매매 없으면 -100%.                    ║
# ║                                                                                          ║
# ║  ★ 이 전략에서 가장 치명적인 편향 지점은 "현재 시총 랭크를 과거에 적용" 이다.                ║
# ║    지금 소형주인 종목은 정의상 '지난 10년간 주가가 하락한' 종목이므로, 그 명단으로            ║
# ║    2016년 유니버스를 만들면 하락할 종목만 골라 담은 셈이 된다. 그래서 랭크는 반드시           ║
# ║    그 시점에 관측된 시총(mc_panel)으로만 매긴다. A3 계약검정이 이걸 실제로 검사한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 우선주 코드 규칙: 구형 6자리는 끝자리가 5/7/9 (1우/2우B/3우 등),
# 2024 영숫자 체계는 6번째 자리가 K/L/M/N.
_PREF_RE = re.compile(r"^\d{5}[5-9]$|^\d{4}[0-9A-HJ-NP-TV-Z][KLMN]$")
_SPAC_RE = re.compile(r"스팩|기업인수목적")
_REIT_RE = re.compile(r"리츠|리 츠|REIT", re.I)
_PREF_NAME_RE = re.compile(r"(\d?\s*우(?:B|C)?)$|우선주")


def is_preferred(code: str, name: str = "") -> bool:
    """우선주 판정. 코드 규칙 + 종목명 접미 규칙을 함께 본다.

    ★ 코드 규칙만 쓰면 신형 티커에서 새고, 이름 규칙만 쓰면 '대우' 같은 정상 사명이 걸린다.
      둘 중 하나라도 확실하면 우선주로 본다(보수적 제외 — 우선주가 남는 것보다 낫다).
    """
    c = str(code or "")
    if _PREF_RE.match(c):
        return True
    n = re.sub(r"\s+", "", str(name or ""))
    return bool(n and _PREF_NAME_RE.search(n) and not n.endswith("대우"))


def classify_excluded(sec: pd.DataFrame) -> pd.DataFrame:
    """§3.3 종목 속성 기반 상시 제외 판정. 반환: code, ex_spac, ex_pref, ex_reit, ex_static.

    [방법론적 한계] 관리종목·투자주의환기종목·거래정지의 '지정일 이력'은 공개 API 로
    과거 전 구간을 복원할 수 없다. 이 코드는 ① 종목 속성(스팩/우선주/리츠)은 정확히 제외하고,
    ② 관리종목 지정의 주된 사유(자본잠식·4분기 연속 영업적자·감사의견 비적정)는 §6.4
    배제 플래그가 잡으며, ③ 거래정지는 '유동성 하한 미달'로 자연 탈락한다.
    이 근사는 리포트에 명시한다 — 숨기지 않는다.
    """
    cols = ["code", "ex_spac", "ex_pref", "ex_reit", "ex_static"]
    if sec is None or sec.empty:
        return pd.DataFrame(columns=cols)
    S = sec.copy()
    S["code"] = S["code"].astype(str)
    nm = S.get("name", pd.Series("", index=S.index)).astype(str)
    S["ex_spac"] = nm.str.contains(_SPAC_RE, na=False).astype("int8")
    S["ex_reit"] = nm.str.contains(_REIT_RE, na=False).astype("int8")
    S["ex_pref"] = [1 if is_preferred(c, n) else 0 for c, n in zip(S["code"], nm)]
    S["ex_static"] = ((S["ex_spac"] + S["ex_reit"] + S["ex_pref"]) > 0).astype("int8")
    n = int(S["ex_static"].sum())
    LOG.info(f"§3.3 상시 제외 {n:,}종목 — 스팩 {int(S['ex_spac'].sum()):,} · "
             f"우선주 {int(S['ex_pref'].sum()):,} · 리츠 {int(S['ex_reit'].sum()):,}")
    return S[cols]


class ArcUniverse:
    """U-1000 PIT 유니버스. 기존 Universe(상장/폐지 근거)를 감싸 랭크·유동성·제외를 얹는다."""

    def __init__(self, base: "Universe", sec: pd.DataFrame, exdf: pd.DataFrame):
        self.base = base
        self.sec = sec
        self.attrition: List[dict] = []
        self._ex = set(exdf.loc[exdf["ex_static"] == 1, "code"].astype(str)) if len(exdf) else set()
        self._delist = base.delisting_map()
        self._members: Dict[pd.Timestamp, List[str]] = {}

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return self._delist

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"asof": as_ts(t), "stage": stage, "n": len(codes)})

    def build(self, rebals: pd.DatetimeIndex, mc: pd.DataFrame, liq: pd.DataFrame) -> pd.DataFrame:
        """리밸일별 U-1000 멤버십을 만든다. 반환: code, asof, mktcap, adtv60, uni_rank."""
        mcx = (mc.set_index(["code", "asof"])["mktcap"]
               if mc is not None and len(mc) else pd.Series(dtype=float))
        lqx = (liq.set_index(["code", "asof"])["adtv60"]
               if liq is not None and len(liq) else pd.Series(dtype=float))
        out = []
        for t in rebals:
            t = as_ts(t)
            listed = self.base.at(t)                       # 상장·폐지·시즈닝 반영 (C2)
            self.audit_row("전체상장", t, listed)
            cand = [c for c in listed if c not in self._ex]
            self.audit_row("상시제외후", t, cand)
            if not cand:
                continue
            idx = pd.MultiIndex.from_product([cand, [t]], names=["code", "asof"])
            m = mcx.reindex(idx).to_numpy(dtype="float64") if len(mcx) else np.full(len(cand), np.nan)
            a = lqx.reindex(idx).to_numpy(dtype="float64") if len(lqx) else np.full(len(cand), np.nan)
            df = pd.DataFrame({"code": cand, "asof": t, "mktcap": m, "adtv60": a})
            df = df[np.isfinite(df["mktcap"]) & (df["mktcap"] > 0)]
            self.audit_row("시총보유", t, df["code"].tolist())
            if df.empty:
                continue
            # §3.1 하위 1000 — 시총 오름차순(작은 것부터) 상위 N
            df = df.sort_values(["mktcap", "code"], kind="mergesort").head(ARC_UNIVERSE_N).copy()
            df["uni_rank"] = np.arange(1, len(df) + 1)
            self.audit_row("U-1000", t, df["code"].tolist())
            # §3.2 유동성 하한
            df = df[df["adtv60"].fillna(0) >= ARC_MIN_ADTV_KRW]
            self.audit_row("유동성필터", t, df["code"].tolist())
            out.append(df)
        if not out:
            LOG.error("U-1000 유니버스가 비었습니다. PIT 시가총액이 확보되지 않았을 가능성이 큽니다 "
                      "(위 '시총 출처 감사' 표를 확인하세요).")
            return pd.DataFrame(columns=["code", "asof", "mktcap", "adtv60", "uni_rank"])
        U = pd.concat(out, ignore_index=True)
        n_by = U.groupby("asof")["code"].size()
        LOG.ok(f"U-1000 유니버스 {len(U):,}행 · 리밸일 {U['asof'].nunique()}개 · "
               f"시점당 평균 {n_by.mean():.0f}종목 (최소 {n_by.min():,} / 최대 {n_by.max():,})")
        if n_by.mean() < 300:
            LOG.warn(f"시점당 평균 종목이 {n_by.mean():.0f}개로 적습니다. 유동성 하한(1억) 또는 "
                     f"시총 결측이 원인일 수 있습니다 — 아래 감쇠 감사표에서 확인하세요.")
        return U

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "상시제외후", "시총보유", "U-1000", "유동성필터",
                 "배제플래그통과", "신호보유", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max"])
        rows, prev = [], None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/max(prev,1e-9):.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "시점평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < ARC_TOP_N_MIN:
            LOG.warn(f"최종 단계 종목이 목표 보유수({ARC_TOP_N_MIN}~{ARC_TOP_N_MAX})보다 적습니다. "
                     f"임계값을 낮추기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")


# ── 셀 (횡단면 표준화 단위) ─────────────────────────────────────────────────────────────────
_SECTOR_MAP = [
    (r"반도체|전자|디스플레이|IT|정보기술|통신장비|컴퓨터|소프트|인터넷|게임|미디어|콘텐츠",
     "IT/전자"),
    (r"제약|바이오|의료|헬스|생명과학|화장품", "헬스케어"),
    (r"화학|정유|에너지|가스|비금속|시멘트|철강|금속|섬유|종이|목재", "소재"),
    (r"기계|조선|자동차|운송장비|항공|우주|전기장비|건설|건축|엔지니어링", "산업재"),
    (r"음식료|담배|유통|도매|소매|백화점|섬유의복|가구|생활용품|교육|여행|레저|호텔",
     "소비재"),
    (r"은행|증권|보험|금융|캐피탈|지주|투자", "금융"),
    (r"전기|수도|유틸리티|발전", "유틸리티"),
    (r"운수|물류|창고|해운|항만", "운송"),
]
_SECTOR_RE = [(re.compile(p), s) for p, s in _SECTOR_MAP]


def to_sector(industry: Any) -> str:
    """세부 업종 문자열 → 8개 상위 섹터. 횡단면 셀이 너무 잘게 쪼개지는 것을 막는다.

    ★ 업종을 그대로 셀로 쓰면 셀당 종목이 3~5개가 되어 z-score 가 전부 NaN 이 된다.
      (U-1000 은 이미 소형주만 남긴 집합이라 더 그렇다)
    """
    s = str(industry or "")
    for rx, lab in _SECTOR_RE:
        if rx.search(s):
            return lab
    return "기타"


def build_arc_cells(P: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell = (분기, 섹터). 폴백 = (분기, ALL).

    ★ 규모 버킷을 셀에 넣지 않는다. U-1000 은 이미 규모로 잘라낸 집합이라 규모를 또 넣으면
      셀당 종목이 급감하고, 그 자체가 '소형주 안에서 더 소형' 이라는 다른 축을 몰래 넣는 셈이다.
    """
    ind = (sec.drop_duplicates("code").set_index("code")["industry"].astype(str).to_dict()
           if sec is not None and len(sec) and "industry" in sec.columns else {})
    p = P.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["sector"] = p["industry"].map(to_sector).astype(str)
    qs = p["q"].astype(str)
    p["cell"] = qs + "|" + p["sector"]
    p["cell_all"] = qs + "|ALL"
    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    if small.any():
        p.loc[small, "cell"] = p.loc[small, "cell_all"]
        LOG.info(f"셀 폴백 {int(small.sum()):,}행 (섹터 셀 표본 {min_n}개 미만 → 전체 셀로). "
                 f"조용히 넘기지 않고 기록합니다.")
        PIPE.note(f"셀 폴백 {int(small.sum()):,}행")
    for c in ("cell", "cell_all"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 섹터셀 {p['cell'].nunique():,}개 · 전체셀 {p['cell_all'].nunique():,}개")
    return p


# ── 분기 패널 조립 ──────────────────────────────────────────────────────────────────────────
ARC_PANEL_BASE_COLS = ["code", "asof", "q", "corp_code", "market", "industry", "sector",
                       "mktcap", "adtv60", "uni_rank", "close", "exec_px",
                       "fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q", "listing_months",
                       "mom_12_1", "log_mktcap", "log_adtv", "cell", "cell_all"]


def build_liquidity_panel(px_daily: pd.DataFrame, rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """리밸일 시점의 (직전 60거래일 ADTV, 직전 종가, 12-1 모멘텀). 전부 t 이전 관측만 쓴다.

    ★ '직전' 의 정의가 중요하다. 리밸일 당일 데이터를 쓰면 §4 의 't-1 종가까지만' 규약 위반이다.
      merge_asof(direction='backward', allow_exact_matches=False) 로 강제한다.
    """
    cols = ["code", "asof", "adtv60", "close", "mom_12_1"]
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    d = px_daily[["code", "date", "close", "amount"]].dropna(subset=["code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    g = d.groupby("code", observed=True)
    d["adtv60"] = g["amount"].transform(
        lambda s: s.rolling(ARC_ADTV_WINDOW, min_periods=max(10, ARC_ADTV_WINDOW // 3)).mean())
    # 12-1 모멘텀: 12개월 전 ~ 1개월 전 (직전 1개월 제외 — 단기 반전 제거)
    d["px_1m"] = g["close"].shift(21)
    d["px_12m"] = g["close"].shift(252)
    d["mom_12_1"] = safe_div(d["px_1m"], d["px_12m"]) - 1.0

    R = pd.DataFrame({"asof": pd.DatetimeIndex(rebals)})
    frames = []
    right = d[["code", "date", "adtv60", "close", "mom_12_1"]].dropna(subset=["date"])
    for t in R["asof"]:
        sub = right[right["date"] < as_ts(t)]
        if sub.empty:
            continue
        last = sub.groupby("code", observed=True).tail(1).copy()
        last["asof"] = as_ts(t)
        frames.append(last[["code", "asof", "adtv60", "close", "mom_12_1"]])
    if not frames:
        return pd.DataFrame(columns=cols)
    L = pd.concat(frames, ignore_index=True)
    PIPE.io("OUT", "MEM", "liquidity_panel", L)
    return downcast(L)


def build_exec_prices(px_daily: pd.DataFrame, rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """체결가 = 리밸일 '이후 첫 거래일의 시가'. §4 룩어헤드 금지의 실행부.

    ★ 시가가 없거나(거래정지) 첫 거래일이 10일 넘게 떨어져 있으면 그 가격으로 체결했다고
      가정할 수 없다 → 직전 종가로 폴백하고 그 사실을 세어 보고한다.
    """
    cols = ["code", "asof", "exec_px", "exec_date", "exec_src"]
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    d = px_daily[["code", "date", "open", "close"]].dropna(subset=["code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    frames = []
    for t in rebals:
        t = as_ts(t)
        fwd = d[(d["date"] >= t) & (d["date"] <= t + pd.Timedelta(days=10))]
        if len(fwd):
            first = fwd.groupby("code", observed=True).head(1).copy()
            first["exec_px"] = pd.to_numeric(first["open"], errors="coerce")
            first["exec_src"] = "익영업일시가"
            bad = ~np.isfinite(first["exec_px"]) | (first["exec_px"] <= 0)
            first.loc[bad, "exec_px"] = pd.to_numeric(first.loc[bad, "close"], errors="coerce")
            first.loc[bad, "exec_src"] = "동일일종가(시가없음)"
            first["asof"] = t
            frames.append(first.rename(columns={"date": "exec_date"})[cols])
    if not frames:
        return pd.DataFrame(columns=cols)
    E = pd.concat(frames, ignore_index=True)
    E = E[np.isfinite(E["exec_px"]) & (E["exec_px"] > 0)]
    n_fb = int((E["exec_src"] != "익영업일시가").sum())
    if n_fb:
        LOG.info(f"체결가 폴백 {n_fb:,}건 (시가 결측 → 동일일 종가). 전체의 "
                 f"{100*n_fb/max(len(E),1):.2f}%")
    return downcast(E)


def build_arc_panel(uni: "ArcUniverse", rebals: pd.DatetimeIndex, U: pd.DataFrame,
                    liq: pd.DataFrame, execp: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """U-1000 멤버십 + 유동성 + 체결가 + 전방수익률 → 기본 패널 P.

    ★ 전방수익률은 '바로 다음 리밸일'과만 짝지어야 한다. 중간 리밸일이 패널에서 빠지면
      shift(-1) 이 두 분기 뒤 가격을 끌어와 한 분기 수익으로 둔갑시킨다(수익 과대계상).
    """
    if U is None or U.empty:
        raise RuntimeError(
            "U-1000 유니버스가 비어 패널을 만들 수 없습니다.\n"
            "  진단: ① PIT 시가총액이 하나도 확보되지 않았는지(위 '시총 출처 감사' 표)\n"
            "        ② 가격 일봉이 수집되었는지\n"
            "        ③ RUN_MODE='CACHED' 인데 캐시가 비어 있지 않은지\n"
            "  RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")

    P = U.copy()
    P["asof"] = as_ts_series(P["asof"])
    P["q"] = [prev_quarter_of(t) for t in P["asof"]]

    if liq is not None and len(liq):
        P = P.merge(liq[["code", "asof", "close", "mom_12_1"]], on=["code", "asof"], how="left")
    else:
        P["close"] = np.nan
        P["mom_12_1"] = np.nan
    if execp is not None and len(execp):
        P = P.merge(execp[["code", "asof", "exec_px", "exec_date"]],
                    on=["code", "asof"], how="left")
    else:
        P["exec_px"] = np.nan
        P["exec_date"] = pd.NaT

    meta_cols = [c for c in ("code", "corp_code", "market", "industry", "name", "listing_date")
                 if c in (sec.columns if sec is not None else [])]
    if sec is not None and len(sec) and meta_cols:
        P = P.merge(sec[meta_cols].drop_duplicates("code"), on="code", how="left")
    for c in ("corp_code", "market", "industry", "name"):
        if c not in P.columns:
            P[c] = ""
    if "listing_date" not in P.columns:
        P["listing_date"] = pd.NaT
    P["listing_date"] = as_ts_series(P["listing_date"])
    P["listing_months"] = ((P["asof"] - P["listing_date"]).dt.days / 30.44).astype("float32")

    # §3.3 상장 12개월 미만 제외 (상장일이 없으면 제외하지 않는다 — 근거 없는 제외 금지)
    young = P["listing_months"].notna() & (P["listing_months"] < ARC_MIN_LISTING_M)
    if young.any():
        LOG.info(f"상장 {ARC_MIN_LISTING_M}개월 미만 {int(young.sum()):,}행 제외 (§3.3)")
        P = P[~young]

    # ── 전방수익률 (1Q / 2Q / 4Q) ─────────────────────────────────────────────────────────
    P = P.sort_values(["code", "asof"], kind="stable").reset_index(drop=True)
    g = P.groupby("code", observed=True)
    delist = uni.delisting_map()
    dl = P["code"].map(lambda c: delist.get(c)).astype("datetime64[ns]")
    for k, lab in ((1, "fwd_ret_1q"), (2, "fwd_ret_2q"), (4, "fwd_ret_4q")):
        nxt_px = g["exec_px"].shift(-k)
        nxt_as = g["asof"].shift(-k)
        # 인접성: k 분기 뒤 리밸일이 정확히 k×3개월 뒤여야 한다
        gap_m = ((nxt_as.dt.year - P["asof"].dt.year) * 12 +
                 (nxt_as.dt.month - P["asof"].dt.month))
        adjacent = gap_m == (3 * k)
        r = (nxt_px / P["exec_px"] - 1.0).where(adjacent)
        # ★ §3.4 상장폐지: 보유 구간 안에 폐지일이 들어오면 -100%. 결측으로 두면 생존자편향이다.
        horizon_end = P["asof"] + pd.DateOffset(months=3 * k)
        died = dl.notna() & (dl > P["asof"]) & (dl <= horizon_end)
        r = r.mask(died & r.isna(), -1.0)
        P[lab] = r.astype("float32")
    n_died = int((dl.notna() & (dl > P["asof"]) &
                  (dl <= P["asof"] + pd.DateOffset(months=3))).sum())
    LOG.info(f"보유 구간 내 상장폐지 관측 {n_died:,}건 → 정리매매가 없으면 -100% 로 반영 (§3.4)")

    P["log_mktcap"] = np.log(pd.to_numeric(P["mktcap"], errors="coerce").where(lambda s: s > 0))
    P["log_adtv"] = np.log(pd.to_numeric(P["adtv60"], errors="coerce").where(lambda s: s > 0))
    P = build_arc_cells(P, sec)
    P = ensure_cols(P, ARC_PANEL_BASE_COLS)
    assert_no_dup_cols_arc(P, "build_arc_panel")
    P = downcast(P)
    LOG.ok(f"기본 패널 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB "
           f"({P['code'].nunique():,}종목 × {P['asof'].nunique()}시점)")
    PIPE.io("OUT", "MEM", "arc_panel_base", P)
    return P
