# -*- coding: utf-8 -*-
"""Stage 2 — PIT 스냅샷 엔진 (§0-1, §18 Stage 2).

리밸런싱마다 원본 DataFrame 을 처음부터 필터링하면 40회 × 수백만 행이 된다.
대신 **한 번 정렬해 두고**, 각 시점은 마스크 한 번 + `np.maximum.at` 한 번으로 끝낸다.
(그룹별 파이썬 루프 없음 — §0-6)

이 파일이 지켜야 하는 단 하나의 규칙:
    시점 t 의 스냅샷에는 published_at <= t / actual_announced_at <= t 인 행만 들어간다.
    비교는 전부 '<=' 또는 '<' 이며, 미래 데이터를 만지는 경로가 아예 존재하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import contracts as C
from .config import SCGConfig
from .util import LOG

#  20영업일 수급 창에서 최소 이만큼은 실제 관측이 있어야 유효로 본다(재현 가정).
MIN_FLOW_OBS_IN_20D = 15
#  회계발표 지연 폴백(actuals 이력이 없는 종목에만 사용) — 한국 상장사 관행
QUARTER_REPORT_LAG_DAYS = 45
ANNUAL_REPORT_LAG_DAYS = 90


# ════════════════════════════════════════════════════════════════════════════════════════
#  거래 캘린더
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class TradingCalendar:
    days: np.ndarray                     # datetime64[ns] 오름차순 유니크

    @classmethod
    def from_prices(cls, prices: "pd.DataFrame") -> "TradingCalendar":
        d = np.sort(pd.unique(prices["date"].to_numpy()))
        return cls(days=d.astype("datetime64[ns]"))

    def pos_on_or_before(self, ts: Any) -> int:
        """ts 이하 마지막 거래일의 인덱스. 없으면 -1."""
        return int(np.searchsorted(self.days, np.datetime64(pd.Timestamp(ts)), side="right")) - 1

    def on_or_before(self, ts: Any) -> Optional["pd.Timestamp"]:
        i = self.pos_on_or_before(ts)
        return pd.Timestamp(self.days[i]) if i >= 0 else None

    def next_after(self, ts: Any) -> Optional["pd.Timestamp"]:
        i = int(np.searchsorted(self.days, np.datetime64(pd.Timestamp(ts)), side="right"))
        return pd.Timestamp(self.days[i]) if i < len(self.days) else None

    def shift(self, ts: Any, n: int) -> Optional["pd.Timestamp"]:
        """ts 이하 마지막 거래일에서 n 영업일 이동(음수 = 과거)."""
        i = self.pos_on_or_before(ts)
        if i < 0:
            return None
        j = i + n
        return pd.Timestamp(self.days[j]) if 0 <= j < len(self.days) else None

    def between(self, a: Any, b: Any) -> np.ndarray:
        lo = int(np.searchsorted(self.days, np.datetime64(pd.Timestamp(a)), side="left"))
        hi = int(np.searchsorted(self.days, np.datetime64(pd.Timestamp(b)), side="right"))
        return self.days[lo:hi]


def rebalance_dates(cal: TradingCalendar, cfg: SCGConfig) -> "pd.DataFrame":
    """§11 3/6/9/12월 말 시그널 + §12 다음 거래일 시가 체결.

    시그널 일자는 '해당 월말 종가까지 공개된 자료'라는 §12 정의에 맞춰
    캘린더 월말 이하 마지막 거래일로 확정한다.
    """
    if len(cal.days) == 0:
        return pd.DataFrame(columns=["signal_date", "exec_date", "exec_kind"])
    start = pd.Timestamp(cfg.backtest_start)
    end = pd.Timestamp(cfg.backtest_end)
    lo = max(start, pd.Timestamp(cal.days[0]))
    hi = min(end, pd.Timestamp(cal.days[-1]))
    rows = []
    for me in pd.date_range(lo - pd.offsets.MonthEnd(1), hi, freq="ME"):
        if me.month not in set(cfg.rebalance_months):
            continue
        sig = cal.on_or_before(me)
        if sig is None or sig < lo or sig > hi:
            continue
        nxt = cal.next_after(sig)
        rows.append({"signal_date": sig,
                     "exec_date": nxt if nxt is not None else pd.NaT,
                     "exec_kind": "NEXT_OPEN" if nxt is not None else "NO_NEXT_DAY"})
    out = pd.DataFrame(rows).drop_duplicates(subset=["signal_date"]).reset_index(drop=True)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
#  추정치 인덱스 — 한 번 정렬, 시점마다 O(N) 마스크 한 번
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class EstimateIndex:
    df: "pd.DataFrame"                   # (company, metric, fiscal_period, estimator) × published_at 정렬
    g: np.ndarray                        # 그룹코드
    ng: int
    pub: np.ndarray                      # published_at (int64 ns)
    gkey: "pd.DataFrame"                 # 그룹코드 → (company, metric, fiscal_period, estimator)

    @classmethod
    def build(cls, est: "pd.DataFrame") -> "EstimateIndex":
        keys = ["company_code", "metric", "fiscal_period", "estimator_id"]
        d = est.sort_values(keys + ["published_at", "report_id"], kind="mergesort").reset_index(drop=True)
        codes, uniq = pd.factorize(pd.MultiIndex.from_frame(d[keys]), sort=False)
        gkey = pd.DataFrame(list(uniq), columns=keys) if len(uniq) else pd.DataFrame(columns=keys)
        return cls(df=d, g=np.asarray(codes, dtype=np.int64), ng=int(len(uniq)),
                   pub=d["published_at"].to_numpy("datetime64[ns]").astype("int64"),
                   gkey=gkey)

    def latest_snapshot(self, asof: Any, window_days: int) -> "pd.DataFrame":
        """(t-W, t] 창 안에서 estimator 별 최신 1건 (§4, §5.2).

        정렬이 published_at 오름차순이므로 '그룹별 최대 인덱스'가 곧 최신 1건이다.
        동일 시점 다건은 정규화 단계에서 이미 report_id 결정적 정렬로 1건만 남아 있다.
        """
        if len(self.df) == 0:
            return self.df.head(0).copy()
        t = np.datetime64(pd.Timestamp(asof)).astype("datetime64[ns]").astype("int64")
        lo = np.datetime64(pd.Timestamp(asof) - pd.Timedelta(days=int(window_days))
                           ).astype("datetime64[ns]").astype("int64")
        mask = (self.pub <= t) & (self.pub > lo)
        if not mask.any():
            return self.df.head(0).copy()
        pos = np.nonzero(mask)[0]
        best = np.full(self.ng, -1, dtype=np.int64)
        np.maximum.at(best, self.g[pos], pos)
        sel = best[best >= 0]
        out = self.df.iloc[sel].copy()
        out["asof"] = pd.Timestamp(asof)
        out["age_days"] = (pd.Timestamp(asof) - out["published_at"]).dt.total_seconds() / 86400.0
        return out


# ════════════════════════════════════════════════════════════════════════════════════════
#  타깃 회계기간 해상 (FQ1 / FY1 / FY2)
# ════════════════════════════════════════════════════════════════════════════════════════
def _q_order(fp: str) -> Optional[int]:
    y, q = C.parse_fiscal_period(fp)
    return None if (y is None or q is None) else y * 4 + (q - 1)


def _q_from_order(o: int) -> str:
    return C.fp_quarter(o // 4, o % 4 + 1)


@dataclass
class TargetResolver:
    """시점 t 에서 종목별 FQ1/FY1/FY2 를 정한다.

    1순위: actuals 의 발표 이력 — 't 까지 발표된 마지막 기간의 다음 기간'.
    2순위: 발표 이력이 없으면 캘린더 폴백(분기 +45일, 연간 +90일).
    어느 쪽을 썼는지는 플래그로 남긴다(§1 재현 가정).
    """
    q_ann: Dict[str, np.ndarray] = field(default_factory=dict)   # code → (order, announced_ns) 정렬
    y_ann: Dict[str, np.ndarray] = field(default_factory=dict)
    fy_end_month: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def build(cls, actuals: "pd.DataFrame", metric: str = "EPS",
              fiscal_calendar: Optional["pd.DataFrame"] = None) -> "TargetResolver":
        r = cls()
        if fiscal_calendar is not None and len(fiscal_calendar):
            for c, m in zip(fiscal_calendar["company_code"], fiscal_calendar["fy_end_month"]):
                try:
                    r.fy_end_month[str(c)] = int(m)
                except (TypeError, ValueError):
                    pass
        a = actuals[actuals["metric"] == metric] if len(actuals) else actuals
        for code, grp in a.groupby("company_code", observed=True):
            qo, qt, yo, yt = [], [], [], []
            for fp, ann in zip(grp["fiscal_period"], grp["actual_announced_at"]):
                o = _q_order(fp)
                ts = pd.Timestamp(ann).value
                if o is not None:
                    qo.append(o); qt.append(ts)
                else:
                    y, _ = C.parse_fiscal_period(fp)
                    if y is not None:
                        yo.append(y); yt.append(ts)
            if qo:
                arr = np.array(sorted(zip(qt, qo)), dtype=np.int64)
                r.q_ann[str(code)] = arr          # (announced_ns, order) 오름차순
            if yo:
                arr = np.array(sorted(zip(yt, yo)), dtype=np.int64)
                r.y_ann[str(code)] = arr
        return r

    def _last_reported(self, table: Dict[str, np.ndarray], code: str, t_ns: int) -> Optional[int]:
        arr = table.get(code)
        if arr is None or not len(arr):
            return None
        i = int(np.searchsorted(arr[:, 0], t_ns, side="right"))
        if i == 0:
            return None
        return int(arr[:i, 1].max())          # 발표 순서가 뒤바뀌어도 '가장 늦은 기간'

    def resolve(self, codes: Sequence[str], asof: Any) -> "pd.DataFrame":
        t = pd.Timestamp(asof)
        t_ns = t.value
        rows = []
        # 캘린더 폴백 기준값(12월 결산 기준). 종목별 결산월이 다르면 개별 계산.
        for code in codes:
            code = str(code)
            fym = self.fy_end_month.get(code, 12)
            lq = self._last_reported(self.q_ann, code, t_ns)
            ly = self._last_reported(self.y_ann, code, t_ns)
            src_q, src_y = "ACTUALS", "ACTUALS"
            if lq is None:
                lq = _cal_last_quarter(t, fym)
                src_q = "CALENDAR_FALLBACK"
            if ly is None:
                ly = _cal_last_year(t, fym)
                src_y = "CALENDAR_FALLBACK"
            fq1 = _q_from_order(lq + 1)
            rows.append({
                "company_code": code,
                "fq1_period": fq1,
                "fq1_prev_year_period": C.prev_year_same_quarter(fq1),
                "fy1_period": C.fp_year(ly + 1),
                "fy2_period": C.fp_year(ly + 2),
                "fy_prev_period": C.fp_year(ly),
                "fy_end_month": fym,
                "target_source_q": src_q,
                "target_source_y": src_y,
            })
        out = pd.DataFrame(rows)
        out["asof"] = t
        return out


def _cal_last_quarter(t: "pd.Timestamp", fy_end_month: int) -> int:
    """t 까지 '발표되었을' 마지막 분기 order (분기말 +45일 규칙)."""
    ref = t - pd.Timedelta(days=QUARTER_REPORT_LAG_DAYS)
    y = ref.year
    offset = (12 - int(fy_end_month)) % 12
    m = ref.month + offset
    yy = y + (m - 1) // 12
    mm = (m - 1) % 12 + 1
    q = (mm - 1) // 3 + 1
    o = yy * 4 + (q - 1)
    # ref 가 해당 분기 말일 이전이면 아직 끝나지 않은 분기 → 하나 이전
    fp = _q_from_order(o)
    end = C.fiscal_period_end(fp, fy_end_month)
    if end is not None and ref < end:
        o -= 1
    return o


def _cal_last_year(t: "pd.Timestamp", fy_end_month: int) -> int:
    ref = t - pd.Timedelta(days=ANNUAL_REPORT_LAG_DAYS)
    y = ref.year
    end = C.fiscal_period_end(C.fp_year(y), fy_end_month)
    return y if (end is not None and ref >= end) else y - 1


# ════════════════════════════════════════════════════════════════════════════════════════
#  가격 / 수급 / 유니버스 패널 (피벗 후 벡터 조회)
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class MarketPanel:
    cal: TradingCalendar
    codes: np.ndarray
    code_pos: Dict[str, int]
    adj_close: np.ndarray            # (T, N)
    open_px: np.ndarray
    market_cap: np.ndarray
    listed: np.ndarray               # bool (T, N)
    inst_cum: Optional[np.ndarray] = None      # (T+1, N) 누적합
    fgn_cum: Optional[np.ndarray] = None
    flow_obs_cum: Optional[np.ndarray] = None  # 관측일수 누적
    open_is_close_fallback: Optional[np.ndarray] = None

    @classmethod
    def build(cls, prices: "pd.DataFrame", flows: Optional["pd.DataFrame"],
              cal: TradingCalendar) -> "MarketPanel":
        codes = np.array(sorted(pd.unique(prices["company_code"].astype(str))), dtype=object)
        code_pos = {c: i for i, c in enumerate(codes)}
        T, N = len(cal.days), len(codes)
        di = pd.Series(np.arange(T), index=pd.DatetimeIndex(cal.days))

        def _grid(df: "pd.DataFrame", col: str, fill: float = np.nan) -> np.ndarray:
            arr = np.full((T, N), fill, dtype=np.float64)
            ii = di.reindex(pd.DatetimeIndex(df["date"])).to_numpy()
            jj = df["company_code"].astype(str).map(code_pos).to_numpy()
            ok = np.isfinite(ii.astype(float)) & pd.notna(jj)
            arr[ii[ok].astype(int), jj[ok].astype(int)] = pd.to_numeric(
                df.loc[ok, col], errors="coerce").to_numpy(dtype=float)
            return arr

        p = prices
        adj = _grid(p, "adj_close")
        mcap = _grid(p, "market_cap")

        # ★ 수정종가와 원시 시가를 그대로 섞으면 배당락·액면분할 당일에 가짜 수익률이 생긴다.
        #   adj_open 이 있으면 그것을, 없으면 원시종가 대비 배율로 환산한다.
        #   둘 다 불가능하면 시가를 NaN 으로 두어 백테스트가 '종가 체결'로 낮추고 플래그를 남긴다.
        if "adj_open" in p.columns:
            opn = _grid(p, "adj_open")
        elif "open" in p.columns and "close_raw" in p.columns:
            raw_o = _grid(p, "open")
            raw_c = _grid(p, "close_raw")
            with np.errstate(invalid="ignore", divide="ignore"):
                factor = np.where(np.isfinite(raw_c) & (raw_c > 0), adj / raw_c, np.nan)
            opn = raw_o * factor
        elif "open" in p.columns:
            # 수정계수를 알 수 없다 → 시가 체결을 포기한다(조용히 섞지 않는다).
            opn = np.full((T, N), np.nan)
        else:
            opn = np.full((T, N), np.nan)
        lst = np.isfinite(adj)
        if "listed_flag" in p.columns:
            lf = _grid(p.assign(_lf=p["listed_flag"].astype(float)), "_lf", fill=np.nan)
            lst = lst & (np.nan_to_num(lf, nan=1.0) > 0.5)

        # 시가 결측 → 다음 가용 종가 체결 폴백을 위해 표식만 만들어 둔다(§12)
        open_fb = ~np.isfinite(opn) & np.isfinite(adj)

        panel = cls(cal=cal, codes=codes, code_pos=code_pos, adj_close=adj, open_px=opn,
                    market_cap=mcap, listed=lst, open_is_close_fallback=open_fb)

        if flows is not None and len(flows):
            inst = _grid(flows, "institution_net_buy_value", fill=np.nan)
            fgn = _grid(flows, "foreign_net_buy_value", fill=np.nan)
            obs = (np.isfinite(inst) | np.isfinite(fgn)).astype(np.float64)
            z = np.zeros((1, N))
            panel.inst_cum = np.vstack([z, np.nancumsum(np.nan_to_num(inst, nan=0.0), axis=0)])
            panel.fgn_cum = np.vstack([z, np.nancumsum(np.nan_to_num(fgn, nan=0.0), axis=0)])
            panel.flow_obs_cum = np.vstack([z, np.cumsum(obs, axis=0)])
        return panel

    # ── 시점 조회 ─────────────────────────────────────────────────────────────────────
    def row_index(self, ts: Any) -> int:
        return self.cal.pos_on_or_before(ts)

    def col_index(self, codes: Sequence[str]) -> np.ndarray:
        return np.array([self.code_pos.get(str(c), -1) for c in codes], dtype=np.int64)

    def values_at(self, arr: np.ndarray, ts: Any, codes: Sequence[str]) -> np.ndarray:
        i = self.row_index(ts)
        j = self.col_index(codes)
        out = np.full(len(codes), np.nan)
        ok = (j >= 0) & (i >= 0)
        if ok.any():
            out[ok] = arr[i, j[ok]]
        return out

    def flow_20d(self, ts: Any, codes: Sequence[str], n_days: int = 20
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(기관 20D 합, 외국인 20D 합, 관측일수). 창이 부족하면 NaN."""
        n = len(codes)
        nanv = np.full(n, np.nan)
        if self.inst_cum is None:
            return nanv, nanv, np.zeros(n)
        i = self.row_index(ts)
        if i < 0:
            return nanv, nanv, np.zeros(n)
        hi = i + 1
        lo = max(0, hi - int(n_days))
        j = self.col_index(codes)
        ok = j >= 0
        inst = np.full(n, np.nan); fgn = np.full(n, np.nan); obs = np.zeros(n)
        if ok.any():
            jj = j[ok]
            inst[ok] = self.inst_cum[hi, jj] - self.inst_cum[lo, jj]
            fgn[ok] = self.fgn_cum[hi, jj] - self.fgn_cum[lo, jj]
            obs[ok] = self.flow_obs_cum[hi, jj] - self.flow_obs_cum[lo, jj]
        short = obs < MIN_FLOW_OBS_IN_20D
        inst[short] = np.nan
        fgn[short] = np.nan
        return inst, fgn, obs


# ════════════════════════════════════════════════════════════════════════════════════════
#  유니버스 (§10) — 과거 시점 구성종목만
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class UniverseIndex:
    dates: np.ndarray                    # 유니버스 스냅샷 일자(오름차순)
    members: Dict[int, List[str]]        # 스냅샷 인덱스 → 종목 리스트
    universe_id: str

    @classmethod
    def build(cls, um: "pd.DataFrame", universe_id: str) -> "UniverseIndex":
        d = um[(um["universe_id"].astype(str) == universe_id) & (um["is_member"].astype(bool))]
        if not len(d):
            return cls(dates=np.array([], dtype="datetime64[ns]"), members={}, universe_id=universe_id)
        dates = np.sort(pd.unique(d["date"].to_numpy())).astype("datetime64[ns]")
        pos = {pd.Timestamp(x): i for i, x in enumerate(dates)}
        members: Dict[int, List[str]] = {i: [] for i in range(len(dates))}
        for dt_, grp in d.groupby("date", observed=True):
            members[pos[pd.Timestamp(dt_)]] = sorted(grp["company_code"].astype(str).unique().tolist())
        return cls(dates=dates, members=members, universe_id=universe_id)

    def at(self, ts: Any) -> List[str]:
        """t 이하 마지막 스냅샷의 구성종목. 미래 스냅샷을 절대 보지 않는다(§10, §27)."""
        if not len(self.dates):
            return []
        i = int(np.searchsorted(self.dates, np.datetime64(pd.Timestamp(ts)), side="right")) - 1
        return list(self.members.get(i, [])) if i >= 0 else []

    def snapshot_date(self, ts: Any) -> Optional["pd.Timestamp"]:
        if not len(self.dates):
            return None
        i = int(np.searchsorted(self.dates, np.datetime64(pd.Timestamp(ts)), side="right")) - 1
        return pd.Timestamp(self.dates[i]) if i >= 0 else None


def covered_universe(est_index: EstimateIndex, panel: MarketPanel, asof: Any,
                     window_days: int, min_estimators: int) -> List[str]:
    """§10 SENSITIVITY — 해당 시점 상장 + 애널리스트 커버리지 존재 종목."""
    snap = est_index.latest_snapshot(asof, window_days)
    if not len(snap):
        return []
    cnt = snap.groupby("company_code", observed=True)["estimator_id"].nunique()
    cand = [str(c) for c, n in cnt.items() if n >= min_estimators]
    i = panel.row_index(asof)
    if i < 0:
        return []
    return sorted([c for c in cand
                   if panel.code_pos.get(c) is not None and panel.listed[i, panel.code_pos[c]]])


__all__ = [n for n in dir() if not n.startswith("_")]
