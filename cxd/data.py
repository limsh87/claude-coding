# -*- coding: utf-8 -*-
"""데이터 계층 — 캐시 최우선, 신규 수집은 예외.

우선순위:  ① 로컬/저장소 캐시  →  ② 구글드라이브 캐시  →  ③ 신규 수집(키 필요)
실데이터 어댑터는 **없는 데이터를 조용히 지어내지 않는다.** 도달 불가·키 부재는
DataUnavailable 로 명시적으로 실패하고, 무엇이 왜 막혔는지 한글로 남긴다.

합성 패널(SyntheticWorld)은 계산경로 증명 전용이다. 기본 레짐은 **귀무(NULL)** 이며,
수익률에는 어떤 알파도 심지 않는다 — 파이프라인이 합성에서 알파를 만들어내면 그것은
데이터가 아니라 **버그**라는 뜻이고, 그 사실이 드러나는 것이 이 하네스의 목적이다.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .spec import FRAME, CXD


class DataUnavailable(RuntimeError):
    """실데이터에 도달할 수 없음. 대체·추정으로 메우지 않는다."""


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  캐시 레이크 — adopt-by-reference. 기존 캐시를 옮기지도 지우지도 덮어쓰지도 않는다.
# ═══════════════════════════════════════════════════════════════════════════════════════════
ROLE_FINGERPRINT = {
    # role: (필수 컬럼 후보군, 파일명 힌트)
    "customs_monthly": ({"exp_usd", "expdlr", "수출금액"}, ("customs", "hs_monthly", "trade")),
    "hs_cell_map":     ({"hs", "hsk", "cell"}, ("hs", "sinsung", "연계", "cell")),
    "ksic_cell_map":   ({"ksic", "induty_code", "cell"}, ("ksic", "istans", "map")),
    "universe":        ({"rebal", "code"}, ("universe", "u250", "univ")),
    "revenue":         ({"code", "rev_ttm"}, ("rev", "fnltt", "dart", "sales")),
    "resc":            ({"code", "p_rs", "p_eg"}, ("resc", "factor", "score")),
    "prices":          ({"code", "close"}, ("ohlcv", "price", "krx")),
}

ALIAS = {
    "종목코드": "code", "Symbol": "code", "ticker": "code", "corp_code": "code",
    "날짜": "date", "Date": "date", "일자": "date", "기준일": "date",
    "수출금액": "exp_usd", "expDlr": "exp_usd", "expdlr": "exp_usd",
    "매출액": "revenue", "시가총액": "mktcap", "market_cap": "mktcap",
}


@dataclass
class CacheEntry:
    role: str
    path: str
    rows: Optional[int]
    cols: List[str]
    score: float


class CacheLake:
    """세 곳(로컬·저장소·드라이브 동기화 폴더)을 훑어 역할별 최적 캐시를 고른다.

    파케이는 **푸터 메타데이터만** 읽어 판별하므로 수 GB 파일도 수 ms 다.
    애매하면 채택하지 않는다 — 잘못 채택한 캐시는 없는 캐시보다 나쁘다.
    """

    def __init__(self, roots: List[str], budget_s: float = 120.0, max_depth: int = 6):
        self.roots = [os.path.expanduser(r) for r in roots]
        self.budget_s = float(budget_s)
        self.max_depth = int(max_depth)
        self.found: Dict[str, List[CacheEntry]] = {}
        self.scanned = 0
        self.notes: List[str] = []

    def _cols_of(self, path: str) -> Optional[List[str]]:
        try:
            if path.endswith(".parquet"):
                import pyarrow.parquet as pq
                return [str(c) for c in pq.ParquetFile(path).schema.names]
            if path.endswith((".csv", ".csv.gz", ".tsv")):
                return [str(c) for c in pd.read_csv(path, nrows=0).columns]
        except Exception:
            return None
        return None

    def scan(self) -> "CacheLake":
        for root in self.roots:
            if not os.path.isdir(root):
                continue
            t0, base_depth = time.time(), root.rstrip(os.sep).count(os.sep)
            for dirpath, dirnames, filenames in os.walk(root):
                if time.time() - t0 > self.budget_s:
                    self.notes.append(f"스캔 예산 초과로 중단: {root}")
                    break
                if dirpath.count(os.sep) - base_depth >= self.max_depth:
                    dirnames[:] = []
                for fn in filenames:
                    if not fn.endswith((".parquet", ".csv", ".csv.gz", ".tsv")):
                        continue
                    p = os.path.join(dirpath, fn)
                    self.scanned += 1
                    cols = self._cols_of(p)
                    if not cols:
                        continue
                    norm = {ALIAS.get(c, c).lower() for c in cols}
                    for role, (need, hints) in ROLE_FINGERPRINT.items():
                        hit = len(norm & {n.lower() for n in need})
                        if not hit:
                            continue
                        s = hit / max(1, len(need)) + (0.5 if any(h in fn.lower() for h in hints) else 0.0)
                        if s >= 0.5:
                            self.found.setdefault(role, []).append(
                                CacheEntry(role, p, None, cols, round(s, 3)))
        for role in self.found:
            self.found[role].sort(key=lambda e: -e.score)
        return self

    def best(self, role: str) -> Optional[CacheEntry]:
        v = self.found.get(role) or []
        return v[0] if v else None

    def table(self) -> pd.DataFrame:
        rows = [dict(role=r, path=e.path, score=e.score, n_cols=len(e.cols))
                for r, v in self.found.items() for e in v[:3]]
        return pd.DataFrame(rows or [{"role": "(없음)", "path": "", "score": 0, "n_cols": 0}])


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  실데이터 어댑터 — 도달 불가 시 명시적 실패 (지어내지 않는다)
# ═══════════════════════════════════════════════════════════════════════════════════════════
CUSTOMS_ENDPOINT = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
DART_ENDPOINT = "https://opendart.fss.or.kr/api"
ISTANS_URL = "https://www.istans.or.kr"


def probe_endpoints(hosts: Dict[str, str], timeout: float = 20.0) -> pd.DataFrame:
    """카나리 사전점검 — 실제로 한 번 찔러 status 를 기록한다. 추측으로 채우지 않는다."""
    import requests
    rows = []
    for name, url in hosts.items():
        t0 = time.time()
        try:
            r = requests.get(url, timeout=timeout)
            rows.append(dict(source=name, url=url, status=str(r.status_code),
                             ok=r.status_code < 400, ms=int((time.time() - t0) * 1000),
                             detail=r.text[:120].replace("\n", " ")))
        except Exception as e:
            msg = str(e)
            blocked = "403" in msg or "ProxyError" in type(e).__name__ or "ProxyError" in msg
            rows.append(dict(source=name, url=url,
                             status="EGRESS_BLOCKED" if blocked else type(e).__name__,
                             ok=False, ms=int((time.time() - t0) * 1000), detail=msg[:120]))
    return pd.DataFrame(rows)


def fetch_customs_monthly(months: pd.DatetimeIndex, service_key: str,
                          cell_axis: str = None) -> pd.DataFrame:
    """관세청 신성질별 월별 수출액. 키·망 없이는 호출하지 않는다."""
    if not service_key:
        raise DataUnavailable(
            "공공데이터포털 서비스키(DATA_GO_KR_KEY)가 없습니다. "
            "발급: https://www.data.go.kr → 로그인 → 관세청 수출입무역통계 API → [활용신청] → "
            "★반드시 '일반 인증키(Decoding)'. Encoding 키(%2B,%3D)를 넣으면 이중 인코딩 오류가 납니다.")
    raise DataUnavailable(
        f"{CUSTOMS_ENDPOINT} 로의 아웃바운드가 조직 egress 정책에서 차단되어 있습니다(CONNECT 403). "
        f"키가 있어도 이 환경에서는 호출이 성립하지 않습니다. "
        f"환경 설정에서 apis.data.go.kr 을 허용 목록에 추가하거나, 캐시를 제공해 주세요.")


def fetch_dart_revenue(codes: List[str], api_key: str) -> pd.DataFrame:
    if not api_key:
        raise DataUnavailable(
            "DART_API_KEY 가 없습니다. 발급: https://opendart.fss.or.kr → [인증키 신청/관리]. "
            "무료, 일 20,000건 호출 제한.")
    raise DataUnavailable(
        f"{DART_ENDPOINT} 로의 아웃바운드가 조직 egress 정책에서 차단되어 있습니다(CONNECT 403).")


def load_hs_cell_linkage(lake: CacheLake) -> pd.DataFrame:
    """G-C0 — HSK↔신성질별 연계표. 자체 재구성 금지(연구자 재량이 되어 사전등록을 훼손)."""
    e = lake.best("hs_cell_map")
    if e is None:
        raise DataUnavailable(
            "HSK↔신성질별 연계표를 찾지 못했습니다(G-C0). 관세청 공개 연계표가 필요하며 "
            "자체 재구성은 명세서 §3.1 에서 금지되어 있습니다(연구자 재량 → 사전등록 훼손).")
    return pd.read_parquet(e.path) if e.path.endswith(".parquet") else pd.read_csv(e.path)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  합성 세계 — 계산경로 증명 전용
# ═══════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class SyntheticWorld:
    """구조적으로 충실하되 알파는 심지 않은 합성 패널.

    regime:
      "NULL"        기제 없음·알파 없음 → G-C3 가 실패해 KILL-1 이 발동해야 정상
      "MECHANISM"   R-07 연결(IEG↔매출)·R-04 SNR 구조는 심되 **수익률은 순수 잡음**
                    → 게이트는 통과하고 백테스트는 0 근처를 내야 정상
      "ALPHA_PLANT" 양성 대조군. 수익률에 신호를 고의 주입 → 백테스트가 잡아내야 정상
    """
    regime: str = "MECHANISM"
    seed: int = 20260816
    n_cells: int = 120
    n_codes: int = 900
    u250_n: int = 250

    def build(self) -> Dict[str, pd.DataFrame]:
        rng = np.random.default_rng(self.seed)
        rebals = pd.date_range(FRAME["research_start"], FRAME["research_end"], freq="QE")
        rebals = pd.DatetimeIndex(rebals[:FRAME["n_rebalances"]])
        # 60M TREND 를 첫 리밸에서 계산하려면 5년 앞선 이력이 필요하다 (PART 6 STEP 3 주의)
        months = pd.date_range(pd.Timestamp(FRAME["research_start"]) - pd.DateOffset(years=5),
                               FRAME["research_end"], freq="ME")
        cells = [f"C{i:03d}" for i in range(self.n_cells)]
        codes = [f"{100000 + i:06d}" for i in range(self.n_codes)]

        # ── 산업 수출: 공통 수출 사이클 + 셀 고유 추세/순환 ────────────────────────────
        T, NC = len(months), len(cells)
        t = np.arange(T)
        common = 0.18 * np.sin(2 * np.pi * t / 42.0) + 0.09 * rng.standard_normal(T).cumsum() / np.sqrt(T)
        cell_trend = rng.normal(0.02, 0.06, NC)           # 일부 셀은 구조적 쇠퇴(TREND<0)
        cell_cyc_ph = rng.uniform(0, 2 * np.pi, NC)
        lvl = rng.normal(16.0, 1.4, NC)
        logE = (lvl[:, None] + cell_trend[:, None] * (t[None, :] / 12.0)
                + common[None, :]
                + 0.22 * np.sin(2 * np.pi * t[None, :] / 30.0 + cell_cyc_ph[:, None])
                + rng.normal(0, 0.11, (NC, T)))
        E = np.exp(logE)
        customs = pd.DataFrame({
            "cell": np.repeat(cells, T), "month": np.tile(months.to_numpy(), NC),
            "exp_usd": E.reshape(-1)})

        # ── 셀 배정 + 사명변경(사업전환 대리변수) ──────────────────────────────────────
        cell_of = rng.integers(0, NC, len(codes))
        is_service = rng.random(len(codes)) < 0.22           # 서비스·금융·지주 → 셀 결측
        renamed = rng.random(len(codes)) < 0.14
        sec = pd.DataFrame({"code": codes,
                            "cell": [cells[c] for c in cell_of],
                            "renamed": renamed,
                            "has_goodwill": rng.random(len(codes)) < 0.78})
        sec.loc[is_service, "cell"] = np.nan

        # ── 분기 매출(TTM) ────────────────────────────────────────────────────────────
        qends = pd.date_range(months[0], months[-1], freq="QE")
        NQ, NCd = len(qends), len(codes)
        cell_idx = np.array([cells.index(c) if isinstance(c, str) else -1 for c in sec["cell"]])
        # 셀 IEG 를 분기로 내려 기업 매출에 연결한다 (R-07: 2·3차 벤더의 최종수요)
        ieg_m = np.full((NC, T), np.nan)
        A = np.where(np.isfinite(E), E, 0.0)
        C = np.concatenate([np.zeros((NC, 1)), np.cumsum(A, axis=1)], axis=1)
        S12 = C[:, 12:] - C[:, :-12]
        ieg_m[:, 11:] = np.log(S12)
        ieg_m[:, 23:] = ieg_m[:, 23:] - ieg_m[:, 11:-12]
        ieg_m[:, :23] = np.nan
        qpos = np.searchsorted(months, qends)
        qpos = np.clip(qpos, 0, T - 1)
        ieg_q = ieg_m[:, qpos]                                # (NC, NQ)

        link = 0.0 if self.regime == "NULL" else 0.55         # R-07 통관-매출 연결 강도
        beta_i = rng.normal(link, 0.25 if link else 0.05, NCd)
        # R-04: 저-IEG 국면일수록 기업 고유 성분의 분산이 크고 지속적이다
        idio = rng.standard_normal((NCd, NQ)) * 0.06
        if self.regime != "NULL":
            snr = np.zeros((NCd, NQ))
            phi = 0.55
            for q in range(1, NQ):
                lowness = np.where(cell_idx >= 0, -np.nan_to_num(ieg_q[cell_idx, q]), 0.0)
                amp = 0.05 + 0.16 * np.clip(lowness, -1, 1)
                snr[:, q] = phi * snr[:, q - 1] + rng.standard_normal(NCd) * np.maximum(amp, 0.01)
            idio = idio + snr
        #   ★ 워밍업 구간의 NaN 을 그대로 두면 cumsum 이 이후 전 구간을 NaN 으로 오염시킨다
        #     (셀이 배정된 기업의 매출이 통째로 사라져 DIV 가 정의되지 않는다).
        g_ind = np.where(cell_idx[:, None] >= 0,
                         np.nan_to_num(ieg_q[np.clip(cell_idx, 0, NC - 1)]), 0.0)
        gq = beta_i[:, None] * g_ind + idio
        rev0 = np.exp(rng.normal(np.log(4.0e10), 0.9, NCd))
        rev = rev0[:, None] * np.exp(np.cumsum(gq / 4.0, axis=1))
        # 초소형주다운 매출 붕괴 이벤트 (붕괴 배제 게이트가 실제로 걸리도록)
        shock = rng.random((NCd, NQ)) < 0.010
        rev = rev * np.where(shock, rng.uniform(0.35, 0.55, (NCd, NQ)), 1.0)
        revdf = pd.DataFrame({
            "code": np.repeat(codes, NQ), "qend": np.tile(qends.to_numpy(), NCd),
            "rev_ttm": rev.reshape(-1)})
        # PIT: 분기말 + 45일 (rcept_dt 근사) + 1 거래일
        revdf["knowledge_date"] = (pd.to_datetime(revdf["qend"]) + pd.Timedelta(days=45)
                                   + pd.offsets.BDay(1))

        # ── 유니버스 / C1 / RESC / 가격 ───────────────────────────────────────────────
        mc = np.exp(rng.normal(np.log(6.0e10), 0.8, (NCd, len(rebals))))
        rows = []
        for j, rb in enumerate(rebals):
            order = np.argsort(mc[:, j])            # 시총 하위 250 = U250
            u250 = set(order[:self.u250_n].tolist())
            f1 = set(rng.choice(list(u250), size=int(len(u250) * 0.316), replace=False).tolist())
            for i in u250:
                rows.append((rb, codes[i], mc[i, j], i not in f1))
        univ = pd.DataFrame(rows, columns=["rebal", "code", "mktcap", "in_C1"])
        univ["P_RS"] = rng.standard_normal(len(univ))          # RESC 성분
        univ["P_EG"] = rng.standard_normal(len(univ))
        univ["RET_12M"] = rng.normal(0.02, 0.45, len(univ))
        univ["IDR"] = rng.standard_normal(len(univ))           # F-08 상관감사용
        univ["RCV"] = rng.standard_normal(len(univ))           # F-09 상관감사용
        univ["RESC"] = 0.6 * univ["P_RS"] + 0.6 * univ["P_EG"] + rng.standard_normal(len(univ)) * 0.5

        # ── 미래수익률 — 봉인 대상. 기본 레짐에서는 순수 잡음(알파 0) ──────────────────
        fwd = (rng.normal(0.012, 0.24, len(univ))
               + rng.standard_t(4, len(univ)) * 0.05)          # 초소형주 팻테일
        univ["fwd_ret_q"] = fwd
        univ.attrs["alpha_planted"] = False

        if self.regime == "ALPHA_PLANT":
            #   양성 대조군 — 하네스가 '있는 알파를 실제로 잡아내는가'를 증명하기 위한 오염본.
            #   가설된 잠재 구동인(기업 고유 성장 × 저-IEG)에 비례해 수익률을 주입한다.
            #   ★ 이 경로는 진단 전용이며 본안(A~D) 판정에는 절대 쓰이지 않는다.
            ci = np.array([codes.index(c) for c in univ["code"]])
            qi = np.searchsorted(qends, pd.DatetimeIndex(univ["rebal"]))
            qi = np.clip(qi, 0, NQ - 1)
            lat_id = idio[ci, qi]
            cidx = cell_idx[ci]
            lat_ie = np.where(cidx >= 0, ieg_q[np.clip(cidx, 0, NC - 1), qi], np.nan)
            tmp = pd.DataFrame({"rebal": univ["rebal"].to_numpy(),
                                "a": lat_id, "b": lat_ie})
            zz = lambda s: (s - s.groupby(tmp["rebal"]).transform("mean")) / \
                           s.groupby(tmp["rebal"]).transform("std").replace(0, np.nan)
            latent = (zz(tmp["a"]) * (-zz(tmp["b"]))).fillna(0.0).to_numpy()
            univ["fwd_ret_q"] = fwd + 0.030 * latent
            univ.attrs["alpha_planted"] = True

        return dict(customs=customs, sec=sec, rev=revdf, univ=univ,
                    rebals=rebals, months=months, cells=cells,
                    hs_cell_map=pd.DataFrame({"hs": cells, "cell": cells}),
                    regime=self.regime)
