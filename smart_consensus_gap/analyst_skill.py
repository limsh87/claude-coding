# -*- coding: utf-8 -*-
"""Stage 3 — 애널리스트 정확도 사전계산 (§5.3, §5.4, §18 Stage 3).

두 단계로 나뉜다.
  (1) 실현 예측오차 이벤트 원장  : 전 기간 1회 계산 후 캐시. 실적 발표 시점에 확정되는 사실.
  (2) 시점별 skill/bias 테이블   : 각 리밸런싱 t 에서 **actual_announced_at < t** 인 이벤트만.

★ 누수가 생기는 지점은 정확히 (2) 다. 같은 분기 실적을 미리 학습하면 smart consensus 가
  '미래를 아는 컨센서스'가 되어 SCG 전체가 무의미해진다. 그래서 이벤트 선택은 오직
  announced_ns < t_ns 마스크 한 줄로만 이뤄지고, 다른 경로가 존재하지 않는다.

성능: 시점마다 groupby 를 돌리지 않는다. 이벤트를 (estimator, 발표시각) 으로 한 번 정렬해
두면 '시점 t 이전' 이벤트는 각 그룹의 **접두부**가 되므로, bincount 한 번으로 그룹별 개수를
얻고 repeat/cumsum 으로 선택 인덱스를 만든다. 시점당 O(N) 벡터 연산 몇 번이 전부다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import BIAS_CLIP, EPS_NUMERIC_FLOOR, SKILL_CLIP_HI, SKILL_CLIP_LO, SCGConfig
from .util import LOG, fmt_table

EVENT_COLUMNS = ["estimator_id", "company_code", "metric", "fiscal_period", "announced_at",
                 "published_at", "estimate_value", "actual_value", "consensus_value",
                 "scale", "err", "n_estimators_at_event"]


# ════════════════════════════════════════════════════════════════════════════════════════
#  (1) 실현 예측오차 이벤트
# ════════════════════════════════════════════════════════════════════════════════════════
def build_realized_errors(estimates: "pd.DataFrame", actuals: "pd.DataFrame",
                          metric: str = "EPS", window_days: int = 90) -> "pd.DataFrame":
    """§5.3 — 실적 발표 직전 시점 기준의 estimator 별 최신 예측과 실적의 스케일 조정 오차."""
    est = estimates[estimates["metric"] == metric]
    act = actuals[actuals["metric"] == metric]
    if not len(est) or not len(act):
        return pd.DataFrame(columns=EVENT_COLUMNS)

    m = est.merge(
        act[["company_code", "metric", "fiscal_period", "actual_value", "actual_announced_at"]],
        on=["company_code", "metric", "fiscal_period"], how="inner", copy=False)
    if not len(m):
        return pd.DataFrame(columns=EVENT_COLUMNS)

    pub = m["published_at"].to_numpy("datetime64[ns]").astype("int64")
    ann = m["actual_announced_at"].to_numpy("datetime64[ns]").astype("int64")
    win = np.int64(window_days) * np.int64(86_400_000_000_000)
    ok = (pub < ann) & (pub >= ann - win)          # 발표 전 + 90일 이내
    m = m.loc[ok].copy()
    if not len(m):
        return pd.DataFrame(columns=EVENT_COLUMNS)

    # 이벤트(=company×period) 안에서 estimator 별 최신 1건
    m = m.sort_values(["company_code", "fiscal_period", "estimator_id", "published_at", "report_id"],
                      kind="mergesort")
    m = m.drop_duplicates(subset=["company_code", "fiscal_period", "estimator_id"], keep="last")

    # 발표 시점의 PIT 일반 컨센서스 = 위에서 고른 최신치들의 단순평균 (§4)
    grp = m.groupby(["company_code", "fiscal_period"], observed=True)["estimate_value"]
    m["consensus_value"] = grp.transform("mean")
    m["n_estimators_at_event"] = grp.transform("size").astype("int64")

    a = m["actual_value"].to_numpy(dtype=float)
    c = m["consensus_value"].to_numpy(dtype=float)
    e = m["estimate_value"].to_numpy(dtype=float)
    scale = np.maximum(np.maximum(np.abs(a), np.abs(np.nan_to_num(c, nan=0.0))), EPS_NUMERIC_FLOOR)
    m["scale"] = scale
    m["err"] = (e - a) / scale
    m["announced_at"] = m["actual_announced_at"]
    out = m[EVENT_COLUMNS].copy()
    out = out[np.isfinite(out["err"].to_numpy(dtype=float))]
    return out.sort_values(["estimator_id", "announced_at"], kind="mergesort").reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════════════════
#  (2) 시점별 skill / bias
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class SkillIndex:
    estimators: np.ndarray               # 유니크 estimator_id
    g: np.ndarray                        # 이벤트 → estimator 그룹코드 (정렬됨)
    ann: np.ndarray                      # 발표시각 int64 ns (그룹 내 오름차순)
    err: np.ndarray
    rank: np.ndarray                     # 그룹 내 순번 0..n-1
    gstart: np.ndarray                   # 그룹 시작 인덱스
    metric: str = "EPS"

    @classmethod
    def build(cls, events: "pd.DataFrame", metric: str = "EPS") -> "SkillIndex":
        ev = events[events["metric"] == metric] if len(events) else events
        ev = ev.sort_values(["estimator_id", "announced_at"], kind="mergesort").reset_index(drop=True)
        if not len(ev):
            return cls(np.array([], dtype=object), np.zeros(0, np.int64), np.zeros(0, np.int64),
                       np.zeros(0), np.zeros(0, np.int64), np.zeros(0, np.int64), metric)
        codes, uniq = pd.factorize(ev["estimator_id"].astype(str), sort=True)
        # factorize(sort=True) + 정렬된 프레임 → 그룹코드도 비내림차순이 된다
        g = np.asarray(codes, dtype=np.int64)
        n = len(g)
        gstart = np.searchsorted(g, np.arange(len(uniq)), side="left").astype(np.int64)
        rank = np.arange(n, dtype=np.int64) - gstart[g]
        return cls(np.asarray(uniq, dtype=object), g,
                   ev["announced_at"].to_numpy("datetime64[ns]").astype("int64"),
                   ev["err"].to_numpy(dtype=float), rank, gstart, metric)

    @property
    def n_estimators(self) -> int:
        return int(len(self.estimators))

    def at(self, asof: Any, cfg: SCGConfig) -> "pd.DataFrame":
        """시점 t 의 estimator 별 (n, bias_raw, bias, mse_raw, mse, skill).

        ★ announced < t 인 이벤트만. 등호를 쓰지 않는 것은 발표 당일 시그널이 그 발표를
          이미 반영했다는 보장이 없기 때문이며, §20 감사 항목(`actual_announced_at <
          signal_date` 100%)과도 일치한다.
        """
        ne = self.n_estimators
        cols = {"estimator_id": self.estimators, "metric": self.metric,
                "n_events": np.zeros(ne, dtype=np.int64),
                "bias_raw": np.zeros(ne), "bias": np.zeros(ne),
                "mse_raw": np.full(ne, np.nan), "mse": np.full(ne, np.nan),
                "skill": np.ones(ne), "global_mse": np.nan}
        if ne == 0:
            return pd.DataFrame({k: (v if isinstance(v, np.ndarray) else [])
                                 for k, v in cols.items()})

        t_ns = pd.Timestamp(asof).value
        mask = self.ann < t_ns
        cnt = np.bincount(self.g[mask], minlength=ne).astype(np.int64)
        K = int(cfg.accuracy_max_events)
        used = np.minimum(cnt, K)
        has = used > 0

        bias_raw = np.zeros(ne)
        mse_raw = np.full(ne, np.nan)
        if has.any():
            gi = np.nonzero(has)[0]
            u = used[gi]
            start = self.gstart[gi] + (cnt[gi] - u)
            total = int(u.sum())
            # repeat/cumsum 으로 flat 인덱스 생성 (그룹 루프 없음)
            rep_start = np.repeat(start, u)
            off_base = np.repeat(np.concatenate([[0], np.cumsum(u)[:-1]]), u)
            idx = rep_start + (np.arange(total, dtype=np.int64) - off_base)
            gg = np.repeat(gi, u)
            # 이벤트 반감기: 가장 최근 이벤트의 age=0
            age = np.repeat(cnt[gi] - 1, u) - self.rank[idx]
            w = np.power(0.5, age / float(cfg.accuracy_event_half_life))
            e = self.err[idx]
            sw = np.bincount(gg, weights=w, minlength=ne)
            swe = np.bincount(gg, weights=w * e, minlength=ne)
            with np.errstate(invalid="ignore", divide="ignore"):
                b = np.where(sw > 0, swe / sw, 0.0)
            dev = e - b[gg]
            swd = np.bincount(gg, weights=w * dev * dev, minlength=ne)
            with np.errstate(invalid="ignore", divide="ignore"):
                mraw = np.where(sw > 0, swd / sw, np.nan)
            bias_raw = np.where(has, b, 0.0)
            mse_raw = np.where(has, mraw, np.nan)

        # 글로벌 사전분포 (§5.3) — 동일 metric 전체 estimator 의 PIT 과거 오차
        fin = np.isfinite(mse_raw) & has
        if fin.sum() >= 5:
            global_mse = float(np.median(mse_raw[fin]))
        elif mask.any():
            global_mse = float(np.median(self.err[mask] ** 2))
        else:
            global_mse = float("nan")
        if not np.isfinite(global_mse) or global_mse <= 0:
            global_mse = float("nan")

        n = used.astype(float)                     # 실제로 사용한 이벤트 수 (§1 재현 가정)
        k = float(cfg.shrink_k)
        bias = np.where(has, (n / (n + k)) * bias_raw, 0.0)
        bias = np.clip(bias, -BIAS_CLIP, BIAS_CLIP)          # §5.4 안전장치
        if np.isfinite(global_mse):
            mse = np.where(fin, (n * np.nan_to_num(mse_raw, nan=0.0) + k * global_mse) / (n + k),
                           global_mse)
            skill = np.clip(global_mse / np.maximum(mse, 1e-8), SKILL_CLIP_LO, SKILL_CLIP_HI)
        else:
            mse = np.full(ne, np.nan)
            skill = np.ones(ne)
        skill = np.where(has, skill, 1.0)                     # n=0 → bias 0, skill 1

        return pd.DataFrame({
            "asof": pd.Timestamp(asof), "estimator_id": self.estimators, "metric": self.metric,
            "n_events_total": cnt, "n_events": used, "bias_raw": bias_raw, "bias": bias,
            "mse_raw": mse_raw, "mse": mse, "skill": skill, "global_mse": global_mse,
        })


def skill_table(events: "pd.DataFrame", asof_dates: Sequence[Any], cfg: SCGConfig,
                metric: str = "EPS") -> Tuple["pd.DataFrame", SkillIndex]:
    idx = SkillIndex.build(events, metric)
    frames = [idx.at(t, cfg) for t in asof_dates]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out, idx


def log_skill_summary(events: "pd.DataFrame", skills: "pd.DataFrame") -> None:
    if not len(events):
        LOG.warning("  ⚠ 실현 예측오차 이벤트 0건 — 모든 estimator 의 skill=1, bias=0 이 된다.")
        LOG.warning("    (이 상태의 smart consensus 는 사실상 '최신성 가중 컨센서스'다)")
        return
    LOG.info(f"  실현 이벤트 {len(events):,}건 / estimator {events['estimator_id'].nunique():,} / "
             f"종목 {events['company_code'].nunique():,}")
    LOG.info(f"  오차 분포: mean={events['err'].mean():.4f} med={events['err'].median():.4f} "
             f"sd={events['err'].std():.4f}")
    if len(skills):
        last = skills[skills["asof"] == skills["asof"].max()]
        cov = float((last["n_events"] > 0).mean()) if len(last) else 0.0
        LOG.info(f"  최종 시점 skill 산출 estimator {len(last):,}명 중 이력 보유 {cov:6.1%}")
        LOG.info(f"  skill 분위: " + ", ".join(
            f"p{int(q*100)}={last['skill'].quantile(q):.2f}" for q in (0.1, 0.5, 0.9)))


__all__ = ["build_realized_errors", "SkillIndex", "skill_table", "log_skill_summary",
           "EVENT_COLUMNS"]
