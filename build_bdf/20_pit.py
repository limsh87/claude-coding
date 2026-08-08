
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  PIT 유니버스 (일별) — 생존편향·미래참조 방어의 본체                                ║
# ║                                                                                          ║
# ║  이벤트 드리븐 전략이라 '월말 유니버스' 로는 부족하다. 이벤트가 발생한 그 날에             ║
# ║  그 종목이 실제로 거래 가능했는지를 (code, date) 쌍 단위로 벡터 판정한다.                  ║
# ║                                                                                          ║
# ║  멤버십 = 아래를 전부 만족                                                                 ║
# ║    ① 상장일 <= d           (상장 전 종목이 섞이면 그 자체로 미래참조)                      ║
# ║    ② 폐지일 > d 또는 없음  (폐지 종목을 빼면 생존편향 — 반대로 폐지 후를 넣으면 유령거래)  ║
# ║    ③ 상장 후 250거래일 시즈닝 (IPO 직후 구간의 이상수익률이 신호를 오염시킨다)             ║
# ║    ④ 보통주                (우선주·ETF·리츠·스팩은 리포트 이벤트와 매칭되지 않는다)        ║
# ║    ⑤ 그 날 실제 시세가 관측됨 (거래정지일에 진입하는 백테스트는 실행 불가능한 백테스트다)  ║
# ║                                                                                          ║
# ║  ★ ③ 시즈닝 앵커 주의 — 조용한 유니버스 붕괴의 원인                                        ║
# ║    searchsorted 는 '가격패널 시작일 이전 상장' 종목을 전부 index 0 으로 보낸다. 거기에      ║
# ║    +250 을 더하면 1990년 상장 종목조차 '패널 시작 후 250거래일' 에야 시즈닝이 끝난 것으로   ║
# ║    계산되어, 2016-08 시작 패널이면 2017년 중반까지 기존 상장사 전부가 빠진다. 에러도        ║
# ║    로그도 없이. → 앵커는 '패널 시작일' 이 아니라 '상장일' 이다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년
DELIST_HAIRCUT = -0.50                # 정리매매 관측이 없는 폐지 종목의 청산 가정 (감도분석 대상)


class DailyUniverse:
    """(code, date) 쌍에 대한 벡터화 PIT 멤버십 판정기."""

    def __init__(self, sec: pd.DataFrame, px: pd.DataFrame, dgk: Optional[pd.DataFrame] = None,
                 snapshots: Optional[pd.DataFrame] = None):
        s = sec.drop_duplicates("code").copy()
        s["listing_date"] = as_ts_series(s["listing_date"])
        s["delisting_date"] = as_ts_series(s["delisting_date"])
        s["name"] = s["name"].astype(str)
        s["market"] = s.get("market", "").astype(str)
        self.sec = s.reset_index(drop=True)

        self.codes = self.sec["code"].to_numpy(dtype=object)
        self._pos = {c: i for i, c in enumerate(self.codes)}
        self._ld = self.sec["listing_date"].to_numpy(DT64)
        self._dd = self.sec["delisting_date"].to_numpy(DT64)
        self._common = np.array([is_common_stock(c, n, m) for c, n, m in
                                 zip(self.codes, self.sec["name"], self.sec["market"])], bool)

        self.cal = build_trading_calendar(px)
        self._cal = self.cal.to_numpy(DT64) if len(self.cal) else \
            np.array([], dtype=DT64)

        # ── 시즈닝 만료일 (상장일 앵커) ─────────────────────────────────────────────────
        FAR = np.datetime64("2100-01-01", DT64_UNIT)
        seas = np.full(len(self.codes), FAR, dtype=DT64)
        if len(self._cal):
            t0 = self._cal[0]
            idx = np.searchsorted(self._cal, self._ld, side="left") + LISTING_SEASONING_DAYS
            inside = idx < len(self._cal)
            seas = np.where(inside, self._cal[np.minimum(idx, len(self._cal) - 1)], FAR)
            pre = (~np.isnat(self._ld)) & (self._ld < t0)      # 패널 시작 전 상장 → 달력 1년
            seas = np.where(pre, self._ld + np.timedelta64(365, "D"), seas)
        else:
            seas = np.where(np.isnat(self._ld), FAR, self._ld + np.timedelta64(365, "D"))
        seas = np.where(np.isnat(self._ld), FAR, seas)          # 상장일 미상 = 판단 불가 → 배제
        self._seas = seas

        # ── 그날 시세가 관측된 (code, date) 집합 ───────────────────────────────────────
        obs = px[["code", "date"]].dropna() if px is not None and len(px) else pd.DataFrame()
        if dgk is not None and len(dgk):
            obs = pd.concat([obs, dgk[["code", "date"]].dropna()], ignore_index=True)
        self._obs: set = set()
        if len(obs):
            o = obs.copy()
            o["date"] = as_ts_series(o["date"])
            o = o.dropna()
            self._obs = set(zip(o["code"].to_numpy(dtype=object),
                                o["date"].to_numpy(DT64)))

        # ── 스냅샷 보강 (합집합으로만 — 교집합은 절대 금지) ────────────────────────────
        self._snap: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            sn = snapshots.copy()
            sn["snap_date"] = as_ts_series(sn["snap_date"])
            for dt_, g in sn.dropna(subset=["snap_date"]).groupby("snap_date", observed=True):
                self._snap[as_ts(dt_)] = set(g["code"])

        self.attrition: List[dict] = []
        LOG.ok(f"PIT 유니버스 준비 — 종목 {len(self.codes):,} "
               f"(보통주 {int(self._common.sum()):,}) · 거래일 {len(self.cal):,} · "
               f"관측 {len(self._obs):,}쌍 · 폐지이력 {int(pd.notna(self.sec['delisting_date']).sum()):,}")

    # ── 벡터 멤버십 ────────────────────────────────────────────────────────────────────
    def is_member(self, codes: Sequence[str], dates: Sequence[Any],
                  require_observed: bool = True) -> np.ndarray:
        """(code, date) 쌍별 PIT 멤버십. 길이가 같은 두 배열을 받아 bool 배열을 돌려준다."""
        n = len(codes)
        if n == 0:
            return np.zeros(0, bool)
        idx = np.array([self._pos.get(c, -1) for c in codes], dtype=np.int64)
        ok = idx >= 0
        d = pd.to_datetime(pd.Series(list(dates)), errors="coerce").to_numpy(DT64)
        safe = np.where(ok, idx, 0)
        ld, dd, se, cm = self._ld[safe], self._dd[safe], self._seas[safe], self._common[safe]
        ok &= ~np.isnat(d)
        ok &= (~np.isnat(ld)) & (ld <= d)                      # ① 상장 이후
        ok &= np.isnat(dd) | (dd > d)                          # ② 폐지 이전
        ok &= (se <= d)                                        # ③ 시즈닝
        ok &= cm                                               # ④ 보통주
        if require_observed and self._obs:
            obs = np.array([(c, dd_) in self._obs for c, dd_ in zip(codes, d)], bool)
            ok &= obs                                          # ⑤ 그날 시세 관측
        return ok

    def at(self, t) -> List[str]:
        """시점 t 의 전체 유니버스 (비교전략의 시총 랭킹 등에 쓴다)."""
        t = as_ts(t)
        td = np.datetime64(t)
        ok = ((~np.isnat(self._ld)) & (self._ld <= td) &
              (np.isnat(self._dd) | (self._dd > td)) & (self._seas <= td) & self._common)
        base = set(self.codes[ok].tolist())
        past = [d for d in self._snap if d <= t]
        if past:                                   # 스냅샷은 합집합으로만 (표본을 깎지 않는다)
            key = max(past)
            if (t - key).days <= 100:
                base |= {c for c in self._snap[key] if c in self._pos}
        base -= {c for c, i in self._pos.items()
                 if not np.isnat(self._dd[i]) and self._dd[i] <= td}
        return sorted(base)

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit(self, stage: str, n: int, note: str = ""):
        self.attrition.append({"stage": stage, "n": int(n), "note": note})

    def report_attrition(self):
        if not self.attrition:
            return
        rows, prev = [], None
        for a in self.attrition:
            keep = "" if prev in (None, 0) else f"{100*a['n']/prev:.1f}%"
            rows.append([a["stage"], f"{a['n']:,}", keep, a.get("note", "")])
            prev = a["n"]
        LOG.table(rows, ["게이트", "잔존 이벤트/종목", "직전 대비", "비고"],
                  ["l", "r", "r", "l"],
                  title="유니버스·이벤트 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and int(str(rows[-1][1]).replace(",", "")) < 100:
            LOG.warn("최종 이벤트가 100건 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")


# ── 사이즈 / 업종 셀 ────────────────────────────────────────────────────────────────────────
SIZE_LABELS = ["대형", "중형", "소형"]


def assign_size_bucket(mc: pd.DataFrame) -> pd.DataFrame:
    """그날의 시가총액 횡단면 백분위로 대형/중형/소형을 나눈다.

    ★ 절대 기준(예: 1조원 이상=대형)을 쓰면 10년간의 인플레이션·지수상승이 그대로
      '시간에 따른 대형주 증가' 로 들어와 사이즈 효과와 시계열 추세가 뒤섞인다.
      반드시 그 시점의 횡단면 랭크로 나눈다."""
    if mc is None or len(mc) == 0:
        return mc
    d = mc.copy()
    r = d.groupby("date", observed=True)["marcap"].rank(pct=True, ascending=False)
    d["size_pct"] = r
    d["size_bucket"] = np.select(
        [r <= 0.20, r <= 0.60], ["대형", "중형"], default="소형")
    set_where(d, r.isna(), "size_bucket", "중형")     # 시총 미상은 중형으로(중립)
    return d


def smallcap_universe(mc: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    """★ 비교전략용: 그 시점 시가총액 '하위 n 종목' 멤버십 (PIT).

    각 거래일마다 그날 시총 오름차순 n개를 고른다. 오늘의 시총으로 과거를 자르면
    look-ahead 이므로, 반드시 그날의 횡단면에서 고른다."""
    if mc is None or len(mc) == 0:
        return pd.DataFrame(columns=["code", "date", "in_small"])
    d = mc[["code", "date", "marcap"]].dropna(subset=["date"]).copy()
    r = d.groupby("date", observed=True)["marcap"].rank(method="first", ascending=True)
    d["in_small"] = (r <= n) & d["marcap"].notna()
    cov = d.groupby("date", observed=True)["in_small"].sum()
    LOG.info(f"시총 하위 {n:,} 유니버스: 일평균 {cov.mean():,.0f}종목 "
             f"(최소 {cov.min():,.0f} · 최대 {cov.max():,.0f}) — 매 거래일 횡단면에서 재선정(PIT)")
    return d[["code", "date", "in_small"]]


def attach_industry(panel: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """업종 더미용 컬럼. 업종이 시점에 따라 바뀌는 경우는 무시하고 최신값을 쓴다
    (업종 재분류는 드물고, 통제변수로만 쓰이므로 영향이 미미하다 — 그 사실을 명시)."""
    if panel is None or len(panel) == 0:
        return panel
    ind = sec.drop_duplicates("code").set_index("code")["industry"] \
        if "industry" in sec.columns else pd.Series(dtype=object)
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    # 카디널리티가 너무 크면 더미가 폭발한다 → 상위 30개만 유지하고 나머지는 '기타'
    top = p["industry"].value_counts().head(30).index
    set_where(p, ~p["industry"].isin(top), "industry", "기타")
    return p
