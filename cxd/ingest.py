# -*- coding: utf-8 -*-
"""실데이터 수집 — 관세청(공공데이터포털) · DART.

규약
  · 엔드포인트를 코드에 박아두고 **믿지 않는다.** 실행 시각에 실제로 한 번 찔러
    status 와 실제 응답 필드명을 기록한 뒤, 검증된 것만 쓴다. 없는 필드를 이름만 보고
    채우는 경로는 만들지 않는다.
  · 자격증명은 **환경변수에서만** 읽는다. 저장소에 커밋하지 않는다.
  · 3층 캐시 분리(OPS-C3): raw/customs/vintage_{YYYYMM}/ 는 immutable — 개정 추적용.
  · 서킷브레이커 + 랜덤지연 + 지수백오프(OPS-C2). 관세청은 보수적으로 친다.
"""
from __future__ import annotations

import io
import json
import os
import random
import threading
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

from .data import DataUnavailable

DART_KEY = os.environ.get("DART_API_KEY", "")
GOKR_KEY = os.environ.get("DATA_GO_KR_KEY", "")

CUSTOMS_BASE = "https://apis.data.go.kr/1220000"
DART_BASE = "https://opendart.fss.or.kr/api"

# 관세청 후보 오퍼레이션 — 실행 시각에 검증한다. 신성질별 전용 엔드포인트는
# 문서에서 확인되지 않으면 쓰지 않고, HS 품목별 + HSK↔신성질별 연계표로 집계한다.
CUSTOMS_OPS = [
    ("itemtrade", "getItemtradeList", "품목별 수출입실적 (HS)"),
    ("nitemtrade", "getNitemtradeList", "품목별 국가별 수출입실적 (HS×국가)"),
]


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  HTTP — 레이트리밋 · 백오프 · 서킷브레이커
# ═══════════════════════════════════════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, qps: float):
        self.interval = 1.0 / max(qps, 0.01)
        self._lock, self._next = threading.Lock(), 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval * (0.85 + 0.3 * random.random())


class CircuitBreaker:
    """연속 실패가 임계를 넘으면 그 소스를 연다. 막힌 API 를 수천 번 두드리지 않는다."""

    def __init__(self, threshold: int = 12):
        self.threshold, self.fails, self.open = threshold, 0, False
        self._lock = threading.Lock()

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.fails = 0
            else:
                self.fails += 1
                if self.fails >= self.threshold:
                    self.open = True

    def check(self, src: str) -> None:
        if self.open:
            raise DataUnavailable(f"[{src}] 서킷브레이커 개방 — 연속 실패 {self.fails}회. "
                                  f"키·망·쿼터를 확인하세요.")


@dataclass
class HttpAudit:
    rows: List[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, source: str, status: str, ms: int, note: str = "") -> None:
        with self._lock:
            self.rows.append(dict(source=source, status=status, ms=ms, note=note[:160]))

    def frame(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=["source", "n", "ok율", "주요상태"])
        D = pd.DataFrame(self.rows)
        g = D.groupby("source", observed=True)
        return pd.DataFrame({
            "n": g.size(),
            "ok율": g["status"].apply(lambda s: (s == "200").mean()),
            "주요상태": g["status"].apply(lambda s: s.value_counts().index[0]),
            "중앙ms": g["ms"].median().astype(int),
        }).reset_index()


AUDIT = HttpAudit()
LIMITS = {"customs": RateLimiter(3.0), "dart": RateLimiter(8.0)}
BREAKERS = {"customs": CircuitBreaker(), "dart": CircuitBreaker()}


def http_json(url: str, params: dict, source: str, tries: int = 4,
              timeout: float = 40.0) -> Optional[dict]:
    BREAKERS[source].check(source)
    last = ""
    for a in range(tries):
        LIMITS[source].wait()
        t0 = time.monotonic()
        try:
            r = requests.get(url, params=params, timeout=timeout)
            ms = int((time.monotonic() - t0) * 1000)
            AUDIT.log(source, str(r.status_code), ms)
            if r.status_code == 200:
                txt = r.text.strip()
                if txt.startswith("<") and "OpenAPI_ServiceResponse" in txt:
                    # 공공데이터포털은 키 오류도 200 + XML 로 준다 — 조용히 통과시키면 안 된다
                    BREAKERS[source].record(False)
                    last = txt[:200]
                    continue
                BREAKERS[source].record(True)
                try:
                    return r.json()
                except Exception:
                    return {"_raw": txt}
            last = f"HTTP {r.status_code}"
            BREAKERS[source].record(r.status_code < 500)
        except Exception as e:
            AUDIT.log(source, type(e).__name__, int((time.monotonic() - t0) * 1000), str(e))
            BREAKERS[source].record(False)
            last = f"{type(e).__name__}: {e}"
        if a < tries - 1:
            time.sleep((2 ** a) * (0.8 + 0.4 * random.random()))
    AUDIT.log(source, "GIVEUP", 0, last)
    return None


def pmap(fn: Callable, jobs: Sequence, workers: int = 8, desc: str = "") -> List:
    import concurrent.futures as cf
    out, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(fn, jobs):
            out.append(r)
            done += 1
            if desc and (done % 50 == 0 or done == len(jobs)):
                print(f"  {desc}: {done:,}/{len(jobs):,}", flush=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  엔드포인트 검증 — 추측으로 채우지 않는다
# ═══════════════════════════════════════════════════════════════════════════════════════════
def verify_customs_ops(sample_ym: str = "202401", sample_hs: str = "8542") -> pd.DataFrame:
    """후보 오퍼레이션을 실제로 한 번씩 찔러 status 와 **실제 응답 필드명**을 기록한다."""
    if not GOKR_KEY:
        raise DataUnavailable("DATA_GO_KR_KEY 환경변수가 비어 있습니다.")
    rows = []
    for path, op, label in CUSTOMS_OPS:
        js = http_json(f"{CUSTOMS_BASE}/{path}/{op}", source="customs", tries=2,
                       params={"serviceKey": GOKR_KEY, "strtYymm": sample_ym,
                               "endYymm": sample_ym, "hsSgn": sample_hs, "type": "json"})
        items, fields = _customs_items(js), []
        if items:
            fields = sorted(items[0].keys())
        rows.append(dict(op=f"{path}/{op}", label=label, ok=bool(items),
                         n_items=len(items), fields=",".join(fields)[:300]))
    return pd.DataFrame(rows)


def _customs_items(js: Optional[dict]) -> List[dict]:
    if not isinstance(js, dict):
        return []
    body = (js.get("response", {}) or {}).get("body") or {}
    items = body.get("items") or {}
    it = items.get("item") if isinstance(items, dict) else items
    if isinstance(it, dict):
        it = [it]
    return [x for x in (it or []) if isinstance(x, dict)]


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  관세청 — HS 품목별 월별 수출액
# ═══════════════════════════════════════════════════════════════════════════════════════════
def fetch_customs_hs_monthly(months: Sequence[str], hs_list: Sequence[str],
                             op: str = "itemtrade/getItemtradeList",
                             cache_dir: str = "cache/raw/customs",
                             workers: int = 6) -> pd.DataFrame:
    """월×HS 수출액. 참조월별 **vintage 스냅샷을 immutable 로** 남긴다(R-06b·OPS-C3).

    반환 컬럼: ym, hs, exp_usd, exp_wgt
    """
    if not GOKR_KEY:
        raise DataUnavailable("DATA_GO_KR_KEY 환경변수가 비어 있습니다.")
    os.makedirs(cache_dir, exist_ok=True)
    jobs = [(ym, hs) for ym in months for hs in hs_list]
    print(f"  관세청 수집 대상 {len(jobs):,}건 (월 {len(months)} × HS {len(hs_list)})", flush=True)

    def one(job):
        ym, hs = job
        js = http_json(f"{CUSTOMS_BASE}/{op}", source="customs",
                       params={"serviceKey": GOKR_KEY, "strtYymm": ym, "endYymm": ym,
                               "hsSgn": hs, "type": "json"})
        rows = []
        for r in _customs_items(js):
            rows.append(dict(ym=ym, hs=str(hs),
                             exp_usd=pd.to_numeric(r.get("expDlr"), errors="coerce"),
                             exp_wgt=pd.to_numeric(r.get("expWgt"), errors="coerce")))
        return rows

    res = pmap(one, jobs, workers=workers, desc="관세청 통관")
    flat = [r for rs in res if rs for r in rs]
    if not flat:
        raise DataUnavailable("관세청에서 한 행도 받지 못했습니다. 키·쿼터·엔드포인트를 확인하세요.")
    D = (pd.DataFrame(flat)
         .groupby(["ym", "hs"], as_index=False)
         .agg(exp_usd=("exp_usd", "sum"), exp_wgt=("exp_wgt", "sum")))
    snap = os.path.join(cache_dir, f"vintage_{time.strftime('%Y%m')}")
    os.makedirs(snap, exist_ok=True)
    p = os.path.join(snap, "customs_hs_monthly.parquet")
    if not os.path.exists(p):                       # immutable — 기존 vintage 를 덮지 않는다
        D.to_parquet(p, index=False)
    return D


def customs_to_cells(hs_monthly: pd.DataFrame, linkage: pd.DataFrame,
                     hs_col: str = "hs", cell_col: str = "cell") -> pd.DataFrame:
    """HS 월별 → 신성질별 셀 월별. 연계표는 관세청 공개본을 그대로 쓴다(자체 재구성 금지)."""
    L = linkage[[hs_col, cell_col]].dropna().drop_duplicates()
    L[hs_col] = L[hs_col].astype(str)
    H = hs_monthly.copy()
    H[hs_col] = H[hs_col].astype(str)
    M = H.merge(L, on=hs_col, how="inner")
    if not len(M):
        raise DataUnavailable("HS↔신성질별 연계에서 교집합이 0입니다. HS 자릿수 정합을 확인하세요.")
    M["month"] = pd.to_datetime(M["ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    return (M.groupby([cell_col, "month"], as_index=False)
            .agg(exp_usd=("exp_usd", "sum"), exp_wgt=("exp_wgt", "sum"))
            .rename(columns={cell_col: "cell"}))


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  DART
# ═══════════════════════════════════════════════════════════════════════════════════════════
def dart_corp_codes(cache: str = "cache/raw/dart/corpCode.parquet") -> pd.DataFrame:
    """전 종목 corp_code ↔ stock_code 매핑 (zip/xml)."""
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    if not DART_KEY:
        raise DataUnavailable("DART_API_KEY 환경변수가 비어 있습니다.")
    LIMITS["dart"].wait()
    r = requests.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": DART_KEY}, timeout=90)
    AUDIT.log("dart", str(r.status_code), 0, "corpCode.xml")
    if r.status_code != 200 or not r.content[:2] == b"PK":
        raise DataUnavailable(f"corpCode.xml 응답이 zip 이 아닙니다 (status {r.status_code}). "
                              f"키를 확인하세요: {r.text[:160]}")
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xml = z.read(z.namelist()[0])
    rows = [{c.tag: (c.text or "").strip() for c in el}
            for el in ET.fromstring(xml).findall("list")]
    D = pd.DataFrame(rows)
    D = D[D["stock_code"].astype(str).str.strip().str.len() == 6].reset_index(drop=True)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    D.to_parquet(cache, index=False)
    return D


def dart_company(corp_codes: Sequence[str], workers: int = 8) -> pd.DataFrame:
    """company.json — induty_code(KSIC). ★현재 시점 값만 존재한다(PIT vintage 없음, R-05)."""
    def one(cc):
        js = http_json(f"{DART_BASE}/company.json", source="dart",
                       params={"crtfc_key": DART_KEY, "corp_code": cc})
        if not isinstance(js, dict) or js.get("status") != "000":
            return None
        return dict(corp_code=cc, stock_code=js.get("stock_code"),
                    corp_name=js.get("corp_name"), induty_code=js.get("induty_code"))
    return pd.DataFrame([r for r in pmap(one, list(corp_codes), workers, "DART company") if r])


def dart_name_history(corp_codes: Sequence[str], bgn: str, end: str,
                      workers: int = 8) -> pd.DataFrame:
    """list.json 은 **각 공시 시점의 corp_name** 을 준다 → 사명 변경 이력이 추가비용 0으로 복원된다.

    사명 변경은 사업 전환의 강한 대리변수이며 G-C2 의 입력이다(R-05b).
    """
    def one(cc):
        out, page = [], 1
        while page <= 20:
            js = http_json(f"{DART_BASE}/list.json", source="dart",
                           params={"crtfc_key": DART_KEY, "corp_code": cc, "bgn_de": bgn,
                                   "end_de": end, "page_no": page, "page_count": 100})
            if not isinstance(js, dict) or js.get("status") != "000":
                break
            for r in js.get("list", []) or []:
                out.append(dict(corp_code=cc, rcept_dt=r.get("rcept_dt"),
                                corp_name=r.get("corp_name")))
            if page >= int(js.get("total_page", 1) or 1):
                break
            page += 1
        return out
    res = pmap(one, list(corp_codes), workers, "DART 공시목록")
    D = pd.DataFrame([r for rs in res if rs for r in rs])
    if not len(D):
        return pd.DataFrame(columns=["corp_code", "renamed", "n_names"])
    g = D.groupby("corp_code", observed=True)["corp_name"].nunique()
    return pd.DataFrame(dict(corp_code=g.index, n_names=g.to_numpy(),
                             renamed=(g > 1).to_numpy()))


REV_TAGS = ("ifrs-full_Revenue", "ifrs_Revenue", "revenue")
REV_NAMES = ("매출액", "수익(매출액)", "영업수익")


def dart_revenue(corp_codes: Sequence[str], years: Sequence[int],
                 fs_div: str = "OFS", workers: int = 8) -> pd.DataFrame:
    """fnlttSinglAcntAll.json → 분기 매출.

    ★ fs_div="OFS"(별도)가 기본이다. 통관은 '대한민국 관세영역 반출'이므로 대응 회계항목은
      연결이 아니라 별도다. 해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.
    """
    REPRT = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}   # 1Q·반기·3Q·사업보고서
    jobs = [(cc, y, rc) for cc in corp_codes for y in years for rc in REPRT]

    def one(job):
        cc, y, rc = job
        js = http_json(f"{DART_BASE}/fnlttSinglAcntAll.json", source="dart",
                       params={"crtfc_key": DART_KEY, "corp_code": cc, "bsns_year": str(y),
                               "reprt_code": rc, "fs_div": fs_div})
        if not isinstance(js, dict) or js.get("status") != "000":
            return None
        for r in js.get("list", []) or []:
            if r.get("sj_div") != "IS" and r.get("sj_div") != "CIS":
                continue
            nm = (r.get("account_nm") or "").replace(" ", "")
            tag = (r.get("account_id") or "")
            if tag in REV_TAGS or nm in REV_NAMES:
                v = pd.to_numeric(str(r.get("thstrm_add_amount") or
                                      r.get("thstrm_amount") or "").replace(",", ""),
                                  errors="coerce")
                if pd.notna(v):
                    return dict(corp_code=cc, year=y, q=REPRT[rc], rev_cum=float(v),
                                rcept_no=js.get("list", [{}])[0].get("rcept_no"))
        return None

    rows = [r for r in pmap(one, jobs, workers, "DART 재무") if r]
    if not rows:
        raise DataUnavailable("DART 에서 매출 한 건도 받지 못했습니다.")
    D = pd.DataFrame(rows).sort_values(["corp_code", "year", "q"])
    # 누적 → 분기 단건 → TTM
    D["rev_q"] = D.groupby(["corp_code", "year"], observed=True)["rev_cum"].diff()
    D["rev_q"] = D["rev_q"].where(D["q"] > 1, D["rev_cum"])
    D["qend"] = pd.to_datetime(D["year"].astype(str) + "-" + (D["q"] * 3).astype(str)) \
        + pd.offsets.MonthEnd(0)
    D = D.sort_values(["corp_code", "qend"])
    D["rev_ttm"] = (D.groupby("corp_code", observed=True)["rev_q"]
                    .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    # PIT: 접수일자 + 1 거래일. rcept_no 앞 8자리가 접수일이다(결산일 아님).
    rd = pd.to_datetime(D["rcept_no"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    D["knowledge_date"] = rd.fillna(D["qend"] + pd.Timedelta(days=45)) + pd.offsets.BDay(1)
    return D


def dart_goodwill_coverage(corp_codes: Sequence[str], year: int,
                           workers: int = 8) -> float:
    """G-C8 — 영업권 계정 존재율만 측정한다(도입 여부는 게이트가 정한다)."""
    def one(cc):
        js = http_json(f"{DART_BASE}/fnlttSinglAcntAll.json", source="dart",
                       params={"crtfc_key": DART_KEY, "corp_code": cc, "bsns_year": str(year),
                               "reprt_code": "11011", "fs_div": "CFS"})
        if not isinstance(js, dict) or js.get("status") != "000":
            return None
        return any("영업권" in (r.get("account_nm") or "") or
                   "Goodwill" in (r.get("account_id") or "")
                   for r in js.get("list", []) or [])
    vals = [v for v in pmap(one, list(corp_codes), workers, "DART 영업권") if v is not None]
    return float(np.mean(vals)) if vals else float("nan")
