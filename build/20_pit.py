

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
                        .sort_values("knowledge_date", kind="stable"))
        L = panel.copy()
        L["_ord"] = np.arange(len(L))
        L = L.dropna(subset=[left_time, by]).sort_values(left_time, kind="stable")
        if L.empty or R.empty:
            return panel
        R[by] = R[by].astype(str)
        L[by] = L[by].astype(str)
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", suffix or "_r"))
        except Exception as e:                                     # noqa
            LOG.warn(f"asof_join 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다. "
                     f"대개 정렬/타입 문제입니다.")
            return panel
        M = M.sort_values("_ord").drop(columns=["_ord"])
        M.index = panel.index[:len(M)] if len(M) == len(panel) else range(len(M))
        return M

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
    def __init__(self, sec: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame):
        self.sec = sec.copy()
        self.snap = snapshots
        self.attrition: List[dict] = []
        self._trading_days = np.sort(px_daily["date"].unique()) if len(px_daily) else np.array([])
        self._snap_by_month: Dict[pd.Timestamp, set] = {}
        if len(snapshots):
            for d, g in snapshots.groupby("snap_date"):
                self._snap_by_month[as_ts(d)] = set(g["code"])
        self.sec["listing_date"] = as_ts_series(self.sec["listing_date"])
        self.sec["delisting_date"] = as_ts_series(self.sec["delisting_date"])
        self._seasoned = {}
        for r in self.sec.itertuples(index=False):
            ld = r.listing_date
            if pd.isna(ld) or len(self._trading_days) == 0:
                self._seasoned[r.code] = ld
            else:
                i = int(np.searchsorted(self._trading_days, np.datetime64(ld), side="left"))
                j = min(i + LISTING_SEASONING_DAYS, len(self._trading_days) - 1)
                self._seasoned[r.code] = as_ts(self._trading_days[j])

    def at(self, t) -> List[str]:
        """시점 t 의 유니버스. t 이후 상장 종목이 하나라도 섞이면 그 자체로 C2 위반이다."""
        t = as_ts(t)
        # ① 스냅샷이 있으면 그것이 최우선 진실 (그 날 실제로 상장돼 있던 종목)
        key = min(self._snap_by_month, key=lambda d: abs((d - t).days)) if self._snap_by_month else None
        base = None
        if key is not None and abs((key - t).days) <= 45:
            base = set(self._snap_by_month[key])
        if base is None:
            base = set()
            for r in self.sec.itertuples(index=False):
                ld, dd = r.listing_date, r.delisting_date
                if pd.notna(ld) and ld > t:
                    continue
                if pd.notna(dd) and dd <= t:
                    continue
                if pd.isna(ld) and pd.isna(dd):
                    continue                          # 근거 없는 종목은 넣지 않는다
                base.add(r.code)
        # ② 상장 후 250거래일 시즈닝
        out = []
        for c in base:
            s = self._seasoned.get(c)
            if s is not None and pd.notna(s) and s > t:
                continue
            out.append(c)
        return sorted(out)

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
    p["cell"] = (p["month"].dt.strftime("%Y%m") + "|" + p["industry"] + "|" + p["size_bucket"])

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    if n_small:
        p.loc[small, "cell"] = (p.loc[small, "month"].dt.strftime("%Y%m") + "|" +
                                p.loc[small, "industry_l1"] + "|ALL")
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "month"].dt.strftime("%Y%m") + "|ALL|ALL"
        LOG.info(f"셀 폴백 발생: 1차 {n_small:,}행(산업 상위단위로) / 2차 {int(still.sum()):,}행(전체로). "
                 f"C11 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    p["cell"] = p["cell"].astype("category")
    return p
