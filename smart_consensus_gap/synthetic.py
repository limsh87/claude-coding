# -*- coding: utf-8 -*-
"""합성 픽스처 — 실데이터 없이 계산경로 전체를 증명하기 위한 리허설 입력.

왜 필요한가: 실데이터(FnGuide/Quantiwise/한경/KRX)는 이 저장소에 들어올 수 없다.
그렇다고 "코드는 썼는데 한 번도 안 돌려봤다"로 끝낼 수는 없다. 그래서 계약과 동일한
형태의 합성 원장을 만들어 **정규화 → PIT → skill → 컨센서스 → 팩터 → 백테스트 → 감사**
전 구간을 실제로 통과시킨다.

★ 여기서 나온 성과 수치는 성과가 아니다. 합성 데이터에는 설계자가 넣은 신호가 들어 있고,
  그것을 되찾는 것은 파이프라인이 배선되어 있다는 증거일 뿐이다. 모든 산출물은
  run_manifest.synthetic=true 로 표시되며 해석 문서가 이 사실을 먼저 말한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import contracts as C

BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권", "신한투자증권",
           "하나증권", "키움증권", "메리츠증권", "대신증권", "IBK투자증권", "신영증권"]
#  ★ estimator 이름 풀은 넉넉해야 한다. 이름이 겹치면 서로 다른 estimator 가 같은
#    estimator_id 로 뭉쳐 '같은 시점 중복'으로 정리되어 버리고, 표본이 조용히 줄어든다.
#    (그 정리 자체는 §3.1 규칙대로 올바른 동작이므로 픽스처 쪽을 고쳐야 한다)
_SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
             "한", "오", "서", "신", "권", "황", "안", "송", "전", "홍"]
_GIVEN = ["철수", "영희", "민수", "지훈", "수연", "동원", "서준", "하늘",
          "세훈", "지민", "지우", "현정", "도윤", "예은", "시우", "서연"]
ANALYSTS = [s + g for g in _GIVEN for s in _SURNAMES]


@dataclass
class SyntheticSpec:
    n_companies: int = 60
    n_estimators: int = 12
    start: str = "2015-01-01"
    end: str = "2026-06-30"
    universe_size: int = 40
    n_delistings: int = 3
    seed: int = 20260810
    with_vendor: bool = False
    surprise_alpha: float = 0.030      # 분기당 서프라이즈 1σ 가 만드는 초과수익
    surprise_kappa: float = 0.18       # 실적의 몇 %가 '아무도 모르는 부분'인가
    max_analyst_insight: float = 0.60  # 최고 실력 애널리스트가 그중 몇 %를 미리 보는가


def _quarters(start: pd.Timestamp, end: pd.Timestamp) -> List[str]:
    out = []
    y, q = start.year, (start.month - 1) // 3 + 1
    while True:
        fp = C.fp_quarter(y, q)
        e = C.fiscal_period_end(fp, 12)
        #  표본 끝에서도 FY2(=다음다음 회계연도) 추정치가 존재해야 12MF 합성이 살아 있다.
        #  실제 애널리스트도 늘 앞을 보고 추정하므로 구간 끝을 넉넉히 잡는다.
        if e is None or e > end + pd.Timedelta(days=800):
            break
        out.append(fp)
        q += 1
        if q > 4:
            q, y = 1, y + 1
    return out


def generate(spec: SyntheticSpec) -> Dict[str, "pd.DataFrame"]:
    rng = np.random.default_rng(spec.seed)
    start, end = pd.Timestamp(spec.start), pd.Timestamp(spec.end)
    days = pd.bdate_range(start, end)
    T = len(days)
    N = spec.n_companies
    codes = [f"{i + 1:06d}" for i in range(N)]
    names = [f"합성{i + 1:03d}" for i in range(N)]
    quarters = _quarters(start, end)
    Q = len(quarters)

    # ── 1) 실적(EPS) 잠재 경로 ──────────────────────────────────────────────────────
    #  실적을 두 조각으로 나눈다:
    #    eps_base   — 원리상 예측 가능한 부분. 모든 애널리스트가 노이즈를 안고 본다.
    #    surprise   — 발표 전까지 아무도 완전히 모르는 부분. 실력 있는 애널리스트만 일부 본다.
    #  이렇게 해야 (a) 스마트 컨센서스가 일반 컨센서스보다 실제에 가깝고 (b) 그 차이(SCG)가
    #  선행수익률을 예측한다는 '심어 둔 신호'가 생긴다. 파이프라인이 이걸 되찾는지 보는 것이
    #  리허설의 목적이다.
    level = rng.lognormal(mean=np.log(1500.0), sigma=0.8, size=N)
    growth = rng.normal(0.015, 0.04, size=N)
    shock = rng.normal(0.0, 0.22, size=(N, Q))
    seasonal = np.tile(np.array([0.95, 1.02, 1.05, 0.98]), Q // 4 + 1)[:Q]
    eps_base = np.empty((N, Q))
    for k in range(Q):
        eps_base[:, k] = level * ((1 + growth) ** k) * seasonal[k] * np.exp(shock[:, k])
    # 일부 종목은 적자/흑자전환 경로를 갖게 해 §7.1 분기 처리를 실제로 밟게 한다
    loss_idx = rng.choice(N, size=max(1, N // 10), replace=False)
    for i in loss_idx:
        k0 = int(rng.integers(0, max(1, Q - 8)))
        eps_base[i, k0:k0 + 6] *= -0.35

    surprise = np.clip(rng.normal(0.0, 1.0, size=(N, Q)), -3.0, 3.0)
    kappa = float(spec.surprise_kappa)
    eps = eps_base * (1.0 + kappa * surprise)

    q_end = np.array([C.fiscal_period_end(fp, 12).value for fp in quarters], dtype="int64")
    q_end_ts = pd.to_datetime(q_end)
    announce = q_end_ts + pd.Timedelta(days=45)

    actuals_rows = []
    for i, c in enumerate(codes):
        for k, fp in enumerate(quarters):
            if announce[k] > end:
                continue
            actuals_rows.append({"company_code": c, "metric": "EPS", "fiscal_period": fp,
                                 "actual_value": float(eps[i, k]),
                                 "actual_announced_at": announce[k], "source": "SYNTHETIC"})
    # 연간 실적 = 4개 분기 합, 사업보고서는 결산 +90일
    for i, c in enumerate(codes):
        for y in sorted({int(fp[:4]) for fp in quarters}):
            ks = [k for k, fp in enumerate(quarters) if int(fp[:4]) == y]
            if len(ks) < 4:
                continue
            ann = pd.Timestamp(year=y, month=12, day=31) + pd.Timedelta(days=90)
            if ann > end:
                continue
            actuals_rows.append({"company_code": c, "metric": "EPS",
                                 "fiscal_period": C.fp_year(y),
                                 "actual_value": float(eps[i, ks].sum()),
                                 "actual_announced_at": ann, "source": "SYNTHETIC"})
    actuals = pd.DataFrame(actuals_rows)

    # ── 2) 애널리스트 추정치 ────────────────────────────────────────────────────────
    E = spec.n_estimators
    est_sigma = rng.uniform(0.05, 0.40, size=E)          # 정확도 차이 (skill 의 원천)
    est_bias = rng.uniform(-0.15, 0.15, size=E)          # 지속적 낙관/비관
    #  통찰력: 노이즈가 작은 애널리스트일수록 서프라이즈를 더 많이 미리 본다
    _rank = (est_sigma.max() - est_sigma) / max(est_sigma.max() - est_sigma.min(), 1e-9)
    est_insight = spec.max_analyst_insight * _rank
    #  각 estimator 가 '보는' 실적 = 예측가능 부분 + 자기가 간파한 서프라이즈 일부
    eps_view = eps_base[None, :, :] * (1.0 + kappa * est_insight[:, None, None] * surprise[None, :, :])
    if E > len(ANALYSTS):
        raise ValueError(f"n_estimators={E} 가 이름 풀({len(ANALYSTS)})보다 크다 — "
                         "estimator_id 충돌이 생긴다")
    est_broker = [BROKERS[e % len(BROKERS)] for e in range(E)]
    est_analyst = [ANALYSTS[e] for e in range(E)]

    rows: List[Dict[str, Any]] = []
    rid = 0
    for k, fp in enumerate(quarters):
        ann_k = announce[k]
        # 각 estimator 는 발표 전 90일 안에서 1~3회 갱신한다
        for e in range(E):
            n_rep = int(rng.integers(1, 4))
            offs = np.sort(rng.integers(3, 89, size=n_rep))[::-1]
            for off in offs:
                pub = ann_k - pd.Timedelta(days=int(off))
                if pub < start or pub > end:
                    continue
                # 커버리지: estimator 마다 종목의 일부만 담당
                cover = rng.random(N) < 0.62
                idx = np.nonzero(cover)[0]
                if not len(idx):
                    continue
                noise = rng.normal(0.0, est_sigma[e], size=len(idx))
                val = eps_view[e, idx, k] * (1.0 + est_bias[e] + noise)
                for j, i in enumerate(idx):
                    rid += 1
                    rows.append({"published_at": pub, "report_id": f"R{rid:08d}",
                                 "company_code": codes[i], "company_name": names[i],
                                 "broker_name_raw": est_broker[e],
                                 "analyst_name_raw": est_analyst[e],
                                 "metric": "EPS", "fiscal_period": fp, "horizon": "FQ1",
                                 "estimate_value": float(val[j]), "source": "SYNTHETIC",
                                 "source_url_or_file": "synthetic://", "parse_confidence": 1.0})
    # 연간 추정치 — 실제 리포트는 한 번에 FY1 과 FY2 를 함께 제시한다. 이걸 빠뜨리면
    # 12MF 합성(FY1·FY2 잔여월 가중)이 영원히 결측이 되어 6팩터가 통째로 죽는다.
    years = sorted({int(fp[:4]) for fp in quarters})
    fy_true: Dict[int, np.ndarray] = {}          # 실제 연간 실적
    fy_view: Dict[int, np.ndarray] = {}          # estimator 별로 '보이는' 연간 실적 (E, N)
    for y in years:
        ks = [k for k, fp in enumerate(quarters) if int(fp[:4]) == y]
        if len(ks) == 4:
            fy_true[y] = eps[:, ks].sum(axis=1)
            fy_view[y] = eps_view[:, :, ks].sum(axis=2)
    for y in years:
        for e in range(E):
            for month in range(1, 13):
                pub = pd.Timestamp(year=y, month=month, day=15)
                if pub < start or pub > end:
                    continue
                cover = rng.random(N) < 0.62
                idx = np.nonzero(cover)[0]
                if not len(idx):
                    continue
                for hz, ty in (("FY1", y), ("FY2", y + 1)):
                    tv = fy_view.get(ty)
                    if tv is None:
                        continue
                    # 먼 기간일수록 오차가 커진다
                    sig = est_sigma[e] * (0.8 if hz == "FY1" else 1.15)
                    noise = rng.normal(0.0, sig, size=len(idx))
                    val = tv[e, idx] * (1.0 + est_bias[e] + noise)
                    for j, i in enumerate(idx):
                        rid += 1
                        rows.append({"published_at": pub, "report_id": f"R{rid:08d}",
                                     "company_code": codes[i], "company_name": names[i],
                                     "broker_name_raw": est_broker[e],
                                     "analyst_name_raw": est_analyst[e],
                                     "metric": "EPS", "fiscal_period": C.fp_year(ty),
                                     "horizon": hz, "estimate_value": float(val[j]),
                                     "source": "SYNTHETIC", "source_url_or_file": "synthetic://",
                                     "parse_confidence": 1.0})
    estimates = pd.DataFrame(rows)

    # ── 3) 가격 — 다가올 분기 서프라이즈가 사전에 일부 반영된다 ────────────────────────
    day_ns = days.values.astype("datetime64[ns]").astype("int64")
    #  실현 드리프트를 설계값으로 고정한다. 그러지 않으면 12년 표본에서 시장·개별 노이즈의
    #  표본평균만으로 지수가 90% 빠지는 시드가 나오고, 리허설 출력이 읽기 어려워진다.
    mkt = rng.normal(0.0, 0.011, size=T)
    mkt += 0.0003 - mkt.mean()
    idio = rng.normal(0.0, 0.019, size=(T, N))
    idio -= idio.mean(axis=0, keepdims=True)
    beta = rng.uniform(0.6, 1.4, size=N)
    drift = np.zeros((T, N))
    #  가격에 심는 신호는 §1 의 '아무도 모르는 부분' 그 자체다. 표준정규이므로 종목별
    #  누적 드리프트는 평균 0, 표준편차 alpha*sqrt(Q) ≈ 20% 수준에 머문다.
    #  (이전 판은 서프라이즈를 상수로 만들어 전 종목을 −98% 로 끌어내렸다)
    sur = surprise
    for k in range(Q):
        a1 = int(np.searchsorted(day_ns, np.datetime64(announce[k]).astype("datetime64[ns]").astype("int64")))
        a0 = max(0, a1 - 60)
        if a1 <= a0:
            continue
        drift[a0:a1, :] += (spec.surprise_alpha * sur[:, k])[None, :] / (a1 - a0)
    ret = mkt[:, None] * beta[None, :] + idio + drift
    px = 10000.0 * np.exp(np.cumsum(ret, axis=0))
    shares = rng.lognormal(np.log(5e7), 0.55, size=N)
    mcap = px * shares[None, :]

    listed = np.ones((T, N), dtype=bool)
    if spec.n_delistings > 0:
        for i in rng.choice(N, size=min(spec.n_delistings, N), replace=False):
            d0 = int(rng.integers(int(T * 0.4), int(T * 0.92)))
            listed[d0:, i] = False

    open_ratio = np.exp(rng.normal(0.0, 0.004, size=(T, N)))
    price_rows = []
    for i in range(N):
        m = listed[:, i]
        if not m.any():
            continue
        price_rows.append(pd.DataFrame({
            "date": days[m], "company_code": codes[i], "adj_close": px[m, i],
            "open": px[m, i] * open_ratio[m, i], "adj_open": px[m, i] * open_ratio[m, i],
            "close_raw": px[m, i], "market_cap": mcap[m, i],
            "volume": rng.lognormal(11, 1.0, size=int(m.sum())), "listed_flag": True}))
    prices = pd.concat(price_rows, ignore_index=True)

    # ── 4) 수급 — 미래수익과 약한 양의 상관 ─────────────────────────────────────────
    fwd = np.vstack([ret[1:], np.zeros((1, N))])
    inst = (rng.normal(0, 1, size=(T, N)) + 0.5 * fwd / 0.02) * mcap * 0.0008
    fgn = (rng.normal(0, 1, size=(T, N)) + 0.4 * fwd / 0.02) * mcap * 0.0006
    flow_rows = []
    for i in range(N):
        m = listed[:, i]
        if not m.any():
            continue
        flow_rows.append(pd.DataFrame({
            "date": days[m], "company_code": codes[i],
            "institution_net_buy_value": inst[m, i], "foreign_net_buy_value": fgn[m, i]}))
    flows = pd.concat(flow_rows, ignore_index=True)

    # ── 5) 유니버스 — 분기 말 시총 상위 K (시점마다 구성이 달라져야 PIT 검정이 의미를 갖는다)
    uni_rows = []
    for me in pd.date_range(start, end, freq="ME"):
        if me.month not in (3, 6, 9, 12):
            continue
        i = int(np.searchsorted(day_ns, np.datetime64(me).astype("datetime64[ns]").astype("int64"),
                                side="right")) - 1
        if i < 0:
            continue
        mc = np.where(listed[i], mcap[i], np.nan)
        order = np.argsort(np.where(np.isfinite(mc), -mc, np.inf))
        sel = [codes[j] for j in order[:spec.universe_size] if listed[i, j]]
        for c in sel:
            uni_rows.append({"date": days[i], "company_code": c,
                             "universe_id": "KOSPI200_PIT", "is_member": True})
    universe = pd.DataFrame(uni_rows)

    out = {"analyst_estimates": estimates, "actuals": actuals, "prices": prices,
           "flows": flows, "universe_membership": universe}

    # ── 6) 벤치마크 ────────────────────────────────────────────────────────────────
    bidx = 1000.0 * np.exp(np.cumsum(mkt))
    out["benchmark"] = pd.DataFrame({"date": days, "benchmark_id": "KOSPI200",
                                     "close": bidx})

    # ── 7) (옵션) 벤더 컨센서스 — ORIGINAL_EXACT 경로 점검용 ─────────────────────────
    if spec.with_vendor:
        vrows = []
        for me in pd.date_range(start, end, freq="ME"):
            i = int(np.searchsorted(day_ns, np.datetime64(me).astype("datetime64[ns]").astype("int64"),
                                    side="right")) - 1
            if i < 0:
                continue
            k = int(np.searchsorted(q_end, np.datetime64(me).astype("datetime64[ns]").astype("int64")))
            if k >= Q:
                continue
            gc = eps_view.mean(axis=0)[:, k] * (1.0 + est_bias.mean())
            sc = gc + 0.35 * (eps[:, k] - gc)
            for j, c in enumerate(codes):
                vrows.append({"date": days[i], "company_code": c, "metric": "EPS",
                              "fiscal_period": quarters[k], "general_consensus": float(gc[j]),
                              "smart_consensus": float(sc[j]),
                              "surprise_probability": float(1 / (1 + np.exp(-sur[j, k]))),
                              "vendor": "SYNTHETIC_VENDOR"})
        out["vendor_consensus"] = pd.DataFrame(vrows)

    return out


__all__ = ["SyntheticSpec", "generate", "BROKERS", "ANALYSTS"]
