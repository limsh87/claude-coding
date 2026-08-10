#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main() 전 구간 드라이런 — pandas 필요.

시장(pykrx/KRX Open API)과 DART, 상장목록 폴백 소스를 바깥에서 가짜로 갈아끼워
오케스트레이션·판정표·산출물 생성까지 돌린다. 배포 파일 안에는 합성 경로가 없다
(P0_LIVE_ONLY) — 주입은 전적으로 이 테스트 쪽에서 한다.

가장 중요한 시나리오는 [17]: pykrx 가 완전히 죽은 상태에서도(실제로 보고된 크래시)
KRX Open API + 다중소스 유니버스 폴백만으로 측정이 끝까지 완주되는가다.
"""
import datetime as _dt
import importlib.util
import json
import random
import sys
import tempfile
from pathlib import Path

import pandas as pd

SRC = str(Path(__file__).with_name("axis_a_delta_v13.py"))
spec = importlib.util.spec_from_file_location("axd", SRC)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

TMP = Path(tempfile.mkdtemp())
FAIL, N = [], 0


def check(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append(f"{name}: got={got!r} want={want!r}")
        print(f"  ✗ {name}: got={got!r} want={want!r}")
    else:
        print(f"  ✓ {name}")


def reset_module_state():
    """스냅샷 캐시류의 모듈 전역을 테스트 섹션 간 오염 없이 리셋한다."""
    M._MCAP_CACHE = {}
    M._SECURITY_MASTER_CACHE = None
    M.PYKRX_AVAILABLE = False
    M.PYKRX_DIAGNOSTIC = ""
    M.KRX_OPENAPI_OK = False
    M.KRX_OPENAPI_MODE = ""
    M.FDR_AVAILABLE = False
    M.stock = None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  공용 픽스처 — 1,400종목 합성 시장 (테스트 규모)
# ══════════════════════════════════════════════════════════════════════════════════════════
NCO = 1400
CODES = [f"{i:06d}" for i in range(1, NCO + 1)]
CORPS = {c: f"{int(c):08d}" for c in CODES}       # 종목코드 → corp_code
CAPS = {c: (i + 1) * 1e8 for i, c in enumerate(CODES)}   # 하위 1,000 = 앞의 1,000개
TRADING = {"20250630", "20250930", "20251230", "20260331"}   # 20251231 은 휴장


def _boot():
    M.ROOT = M.resolve_project_root(M.PROJECT_ROOT)
    M.DIR_CACHE_RAW = M.ROOT / "cache" / "raw" / "dart_exctv"
    M.DIR_CACHE_META = M.ROOT / "cache" / "meta"
    M.DIR_STATE = M.ROOT / "cache" / "state"
    M.DIR_REPORTS = M.ROOT / "reports"
    for d in (M.DIR_CACHE_RAW, M.DIR_CACHE_META, M.DIR_STATE, M.DIR_REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    M._LOG_FH = open(M.DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")
    M.pd = pd
    M.stock = FakeStock
    M.PYKRX_AVAILABLE = True


def _boot_pykrx_dead():
    """[17] 전용: _boot() 과 동일하지만 pykrx 를 살려내지 않는다 — 실제 크래시 이후 상태를
    main() 안에서(=_bootstrap 호출 시점에) 그대로 재현하기 위함. 이게 없으면 main() 이
    호출하는 _bootstrap() 이 매번 PYKRX_AVAILABLE=True 로 되돌려 시나리오가 무의미해진다."""
    M.ROOT = M.resolve_project_root(M.PROJECT_ROOT)
    M.DIR_CACHE_RAW = M.ROOT / "cache" / "raw" / "dart_exctv"
    M.DIR_CACHE_META = M.ROOT / "cache" / "meta"
    M.DIR_STATE = M.ROOT / "cache" / "state"
    M.DIR_REPORTS = M.ROOT / "reports"
    for d in (M.DIR_CACHE_RAW, M.DIR_CACHE_META, M.DIR_STATE, M.DIR_REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    M._LOG_FH = open(M.DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")
    M.pd = pd
    M.stock = None
    M.PYKRX_AVAILABLE = False
    M.PYKRX_DIAGNOSTIC = ("JSONDecodeError: Expecting value: line 13 column 1 (char 25) "
                          "(시뮬레이션 — 실제 보고된 크래시)")


class FakeStock:
    @staticmethod
    def get_market_ticker_list(date, market="ALL"):
        if date not in TRADING:
            return []
        return {"KOSPI": CODES[:400], "KOSDAQ": CODES[400:], "KONEX": [],
                "ALL": CODES}.get(market, CODES)

    @staticmethod
    def get_market_cap_by_ticker(date_c, market="ALL", **kw):
        return None                      # 이 시나리오에선 _mcap_frame 을 직접 스텁한다


M._bootstrap = lambda: _boot()


def fake_mcap(date_c):
    caps = [CAPS[c] if date_c in TRADING else 0 for c in CODES]
    df = pd.DataFrame({"시가총액": caps}, index=CODES)
    M._MCAP_CACHE[date_c] = (df if date_c in TRADING else df, "pykrx(test-stub)")
    return df


_REAL_MCAP_FRAME = M._mcap_frame     # [17] 에서 진짜 KRX-OpenAPI→pykrx 폭포 로직을 태우려면 필요
M._mcap_frame = fake_mcap

# corpCode 파싱 결과 캐시를 미리 심어 둔다 → XML 을 열지 않는 경로를 탄다
_boot()
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")

SPEC = {s[0]: (s[3], s[4], s[5]) for s in M.SNAPSHOT_SPEC}
LOOKAHEAD = {"S1": "20260731000001", "S2": "20260215000001",
             "S3": "20260731000001", "S4": "20260801000001"}


def seed_officer_cache():
    """임원 캐시를 원본 응답 형태로 심는다. 스냅샷마다 겸직 구조를 조금씩 바꿔 born/died 를 만든다."""
    for si, (sid, (yy, rc, as_of)) in enumerate(SPEC.items()):
        ok_no = M.compact(as_of)[:8] + "000001"
        for i, code in enumerate(CODES):
            rows = [{"nm": f"임원{i}_{k}", "birth_ym": f"19{60 + k}년 0{(k % 9) + 1}월",
                     "corp_code": CORPS[code], "rcept_no": ok_no} for k in range(3)]
            if i % 7 == si % 7 and i + 1 < NCO:
                rows.append({"nm": "겸직인", "birth_ym": f"1955년 {(i % 12) + 1:02d}월",
                             "corp_code": CORPS[code], "rcept_no": ok_no})
            if i % 7 == (si + 1) % 7 and i + 1 < NCO:
                rows.append({"nm": "겸직인", "birth_ym": f"1955년 {((i - 1) % 12) + 1:02d}월",
                             "corp_code": CORPS[code], "rcept_no": ok_no})
            if i % 50 == 0:
                rows.append({"nm": f"정정임원{i}", "birth_ym": "1966년 06월",
                             "corp_code": CORPS[code], "rcept_no": LOOKAHEAD[sid]})
            if i % 300 == 0:
                rows.append({"nm": f"불량{i}", "birth_ym": "1966년 06월",
                             "corp_code": CORPS[code], "rcept_no": ""})
            M.write_json(M.cache_path(CORPS[code], yy, rc),
                         {"as_of": "2026-08-10", "pit_filtered": True,
                          "response": {"status": "000", "message": "정상", "list": rows}})


# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[15] 수집 중단 시 resume_todo 회계")
M.PROJECT_ROOT = str(TMP / "proj15")
_boot()
col = M.Collector("k")
jobs = [(f"{i:08d}", "2025", "11012") for i in range(60)]
calls = {"n": 0}


def fake_fetch(cp, y, r):
    calls["n"] += 1
    if calls["n"] > 20:
        col.halt = "BUDGET_STOP_DAILY"
        return "HALT"
    return "000"


col.fetch = fake_fetch
done, remaining = col.run(jobs, "T")
check("성공 20건", done, 20)
check("성공+잔여 = 전체 (누락도 중복도 없다)", done + len(remaining), len(jobs))
check("잔여에 중복 없음", len(remaining), len(set(remaining)))
check("성공한 건은 잔여에 없다", len(set(remaining)) + done, 60)

col2 = M.Collector("k")
col2.fetch = lambda cp, y, r: "013"
d2, r2 = col2.run([("x", "2025", "11012")], "T")
check("013 은 성공으로 계상(재호출 안 함)", (d2, r2), (1, []))

col3 = M.Collector("k")
col3.fetch = lambda cp, y, r: 1 / 0
d3, r3 = col3.run([("x", "2025", "11012")], "T")
check("예외 발생 건은 잔여로", (d3, len(r3)), (0, 1))

# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[16] main() 전 구간 드라이런 (pykrx 정상 — 기존 경로)")
M.PROJECT_ROOT = str(TMP / "proj16")
M.DART_API_KEY = "x" * 40
M.GDRIVE_ROOT = str(TMP / "drive16")
M.CONFIRM_LARGE_COLLECTION = True
M.INCLUDE_KONEX = False
M.KRX_OPENAPI_KEY = ""
_boot()
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")
seed_officer_cache()

V = M.main()

print()
check("run_mode LIVE", V["run_mode"], "LIVE")
check("정렬 A", V["alignment"], "A_OBSERVATION_TIME")
check("스냅샷 4개", len(V["snapshots"]), 4)
check("전이 3개", len(V["transitions"]), 3)
check("신규 API 호출 0건 (전량 캐시 히트)", V["cache"]["actual_new_calls"], 0)
check("data_sources.pykrx_available True", V["data_sources"]["pykrx_available"], True)

s = {x["id"]: x for x in V["snapshots"]}
check("S3 휴장일 스냅 12-31→12-30", (s["S3"]["date_nominal"], s["S3"]["date"]),
      ("2025-12-31", "2025-12-30"))
check("S1 기준일 이동 없음", s["S1"]["date"], "2025-06-30")
for sid in ("S1", "S2", "S3", "S4"):
    check(f"{sid} 상태 OK", s[sid]["status"], "OK")
    check(f"{sid} PIT 폐기 ≠ 0", s[sid]["pit_dropped"] > 0, True)
    check(f"{sid} 룩어헤드 폐기 ≠ 0", s[sid]["pit_dropped_lookahead"] > 0, True)
    check(f"{sid} 최종접수일 ≤ as_of",
          s[sid]["last_rcept_dt"] <= M.compact(s[sid]["as_of"]), True)
    check(f"{sid} 노드 {NCO}종목", s[sid]["nodes"], NCO)
    check(f"{sid} 엣지 > 0", s[sid]["edges"] > 0, True)
    check(f"{sid} universe_source = pykrx", s[sid]["universe_source"], "pykrx")
check("S1 최종접수일이 20260731 이 아니다", s["S1"]["last_rcept_dt"] != "20260731", True)
check("S1 최종접수일 = as_of 당일 접수분", s["S1"]["last_rcept_dt"], "20250814")

t = V["transitions"]
check("전이 모두 OK", [x["status"] for x in t], ["OK"] * 3)
check("교집합 1000종목", [x["intersect"] for x in t], [1000] * 3)
check("edge_born 산출", all(isinstance(x["edge_born"], int) for x in t), True)
check("edge_died 산출", all(isinstance(x["edge_died"], int) for x in t), True)
check("born/died 를 합산하지 않았다", all("edge_total" not in x for x in t), True)
check("born > 0", all(x["edge_born"] > 0 for x in t), True)

check("성공조건 ① PIT 증거", V["success_conditions"]["pit_evidence"], True)
check("성공조건 룩어헤드 증거", V["success_conditions"]["lookahead_evidence"], True)
check("성공조건 ② Δ 측정", V["success_conditions"]["delta_measured"], True)
check("이번 실행 성공", V["success_conditions"]["overall"], True)
check("AΔ-3 4/4", [g for g in V["gates"] if g["id"] == "AΔ-3"][0]["status"], "PASS")
check("임계 해시 유지", V["thresholds_sha256"], M.GATE_THRESHOLDS_SHA256)
check("임계값 불변", V["thresholds"], {"AD1_born_ratio_mean": 0.05,
                                       "AD2_born_total_median": 50, "A5_legacy": 600})
check("스몰캡 백테스트 비교가 SKIPPED_BY_SCOPE 로 명시됨(P0_NO_STRATEGY 충돌)",
      any(x["axis"] == "스몰캡 백테스트 비교" for x in V["skipped"]), True)
check("known_limitations 첫 문장 고정", V["known_limitations"][0],
      "AΔ-1=0.05, AΔ-2=50, A-5=600 은 경험적 근거 없이 설정된 임계값이다.")

R = M.DIR_REPORTS
for f in ("phase0_verdict_v13.json", "phase0_verdict_v13.csv", "phase0_summary_v13.md",
          "diag_edge_events.csv", "diag_pit_dropped_delta.csv", "cache_inventory.json",
          "run_log.txt"):
    check(f"{f} 생성", (R / f).exists(), True)
ee = pd.read_csv(R / "diag_edge_events.csv", dtype=str)
check("diag_edge_events 3,000행 (전이3 × 교집합1000)", len(ee), 3000)
pdrop = pd.read_csv(R / "diag_pit_dropped_delta.csv", dtype=str)
check("PIT 폐기 분포에 4개 스냅샷 모두", sorted(pdrop["snapshot"].unique()),
      ["S1", "S2", "S3", "S4"])
la = pdrop[pdrop["reason"] == "LOOKAHEAD"]
check("S1 룩어헤드 접수월 = 2026-07 (실제 오염과 동일 패턴)",
      sorted(la[la["snapshot"] == "S1"]["rcept_ym"].unique()), ["202607"])
md = (R / "phase0_summary_v13.md").read_text(encoding="utf-8")
check("요약에 전이표", "edge_born" in md, True)
check("요약에 데이터소스 가용성 표기", "pykrx=" in md, True)
check("요약에 해석·전략 제안 없음",
      any(w in md for w in ("추천", "전략을 제안", "매수", "포트폴리오 구성")), False)

# ── 재실행 — 결정성 확인 (tar.gz 일괄 백업이 아니라 개별 blob 증분 동기화다) ──────────────
V2 = M.main()
check("2회차도 신규 호출 0건", V2["cache"]["actual_new_calls"], 0)
check("2회차 결과 동일 (결정적)",
      [x["edge_born"] for x in V2["transitions"]], [x["edge_born"] for x in t])
n_synced_blobs = sum(1 for _ in (Path(M.GDRIVE_ROOT) / M.GDRIVE_SHARED_NS / "blob" / "dart"
                                 / "exctv").rglob("*.json"))
check("드라이브에 임원 blob 이 증분 동기화되어 있다(스냅샷 단위, 종료 대기 없이)",
      n_synced_blobs > 0, True)
# dart_corpcode 공용 게시는 여기서 다시 확인하지 않는다 — 이 섹션은 로컬 corpCode 캐시를
# 미리 심어 두므로 load_corpcode() 가 캐시히트 경로로 조기 반환해 게시 분기를 타지 않는다
# (신선 파싱 시에만 게시한다). 게시 자체는 verify_logic.py [13]에서 직접 검증한다.

# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[17] pykrx 완전 사용불가 → KRX Open API + 다중소스 유니버스 폴백으로 완주")
print("     (실제 보고된 크래시를 시뮬레이션한다: PYKRX_AVAILABLE=False)")
reset_module_state()
M.PROJECT_ROOT = str(TMP / "proj17")
M.GDRIVE_ROOT = ""
M.KRX_OPENAPI_KEY = "fakekey"
M.KRX_ID = M.KRX_PW = ""
M._mcap_frame = _REAL_MCAP_FRAME          # 진짜 폭포 로직을 태운다(KRX OpenAPI → pykrx)
# main() 은 첫 줄에서 _bootstrap() 을 호출한다 — 그게 그냥 _boot() 이면 매번 다시
# PYKRX_AVAILABLE=True 로 되돌려 이 시나리오 자체가 무의미해진다. 전용 픽스처로 바꾼다.
M._bootstrap = lambda: _boot_pykrx_dead()
_boot_pykrx_dead()                        # corpCode 캐시를 심어 둘 디렉터리를 미리 만든다
# KRX_OPENAPI_OK/MODE 는 여기서 미리 정하지 않는다 — main() 이 §1 에서 probe_krx_openapi() 를
# 실제로 다시 돌리기 때문에(진짜 프로브 로직 자체를 이 테스트로 검증한다), 그 결과가 그대로
# 쓰이게 둔다. 대신 아래 가짜 requests 가 프로브 날짜에도 유효 응답을 주도록 맞춰 놨다.

pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")
seed_officer_cache()


class _FakeOpenApiResp:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"OutBlock_1": self._rows}


def _openapi_probe_date_str():
    """probe_krx_openapi() 가 실제로 찌르는 날짜(오늘-7일, 직전 평일)와 동일한 계산.
    main() 은 §1 에서 이 probe 를 다시 돌리므로, 그 날짜도 유효 응답으로 처리해야
    KRX_OPENAPI_OK 사전설정이 main() 내부에서 뒤집히지 않는다."""
    d = _dt.date.today() - _dt.timedelta(days=7)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d.strftime("%Y%m%d")


_OPENAPI_VALID_DATES = TRADING | {_openapi_probe_date_str()}


class _FakeRequestsForOpenApi:
    """KRX Open API 호출만 흉내낸다. 다른 URL 이 오면 이 시나리오 설계가 틀렸다는 뜻이므로 터진다."""
    @staticmethod
    def get(url, timeout=None, **kw):
        if url != M.KRX_OPENAPI_URL:
            raise AssertionError(f"pykrx 가 죽은 시나리오에서 예상 밖의 URL 호출: {url}")
        d = (kw.get("params") or {}).get("basDd")
        if d not in _OPENAPI_VALID_DATES:
            return _FakeOpenApiResp([])
        return _FakeOpenApiResp([{"ISU_SRT_CD": c, "MKTCAP": str(int(CAPS[c]))} for c in CODES])


_real_requests = M.requests                    # 복원용 — 다른 섹션은 이 시점까지 손댄 적 없다(None)
_real_fetch_fdr_listing = M.fetch_fdr_listing
_real_fetch_kind_listing = M.fetch_kind_listing
_real_fetch_fdr_delisting = M.fetch_fdr_delisting
M.requests = _FakeRequestsForOpenApi

# 상장유니버스 폴백(FDR+KIND+DART)도 네트워크 없이 — 병합 로직 자체는 실제로 태운다
M.fetch_fdr_listing = lambda: pd.DataFrame({
    "code": CODES, "listing_date": pd.Timestamp("2000-01-01"),
    "delisting_date": pd.NaT, "market": ""}).reindex(columns=M._LISTING_COLS)
M.fetch_kind_listing = lambda: pd.DataFrame(columns=M._LISTING_COLS)
M.fetch_fdr_delisting = lambda: pd.DataFrame(columns=["code", "delisting_date"])

V3 = M.main()

check("pykrx 없이도 성공적으로 완주(예외로 죽지 않음)", V3["success_conditions"]["overall"], True)
check("data_sources.pykrx_available False (실제 크래시 상태 반영)",
      V3["data_sources"]["pykrx_available"], False)
check("data_sources.krx_openapi_available True (폴백이 실제로 동작)",
      V3["data_sources"]["krx_openapi_available"], True)
s3 = {x["id"]: x for x in V3["snapshots"]}
for sid in ("S1", "S2", "S3", "S4"):
    check(f"{sid} 상태 OK (pykrx 없이도)", s3[sid]["status"], "OK")
    check(f"{sid} mcap_source = krx_openapi", s3[sid]["mcap_source"], "krx_openapi")
    check(f"{sid} universe_source = fallback_multi_source (FDR+KIND+DART 병합)",
          s3[sid]["universe_source"], "fallback_multi_source")
    check(f"{sid} 노드 {NCO}종목 (폴백 유니버스도 전체를 살렸다)", s3[sid]["nodes"], NCO)
t3 = V3["transitions"]
check("전이 3개 모두 OK (pykrx 없이도 §0 질문에 답이 나온다)",
      [x["status"] for x in t3], ["OK"] * 3)
check("edge_born/edge_died 산출됨", all(x["edge_born"] is not None for x in t3), True)

# [17] 전용 픽스처를 원상복구 — 이후 섹션은 정상 pykrx 경로를 기대한다
M._bootstrap = lambda: _boot()
M._mcap_frame = fake_mcap
M.requests = _real_requests
M.fetch_fdr_listing = _real_fetch_fdr_listing
M.fetch_kind_listing = _real_fetch_kind_listing
M.fetch_fdr_delisting = _real_fetch_fdr_delisting

# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[18] S3 전면 휴장 → UNVERIFIED, 수집 진입 금지")
reset_module_state()
M.PROJECT_ROOT = str(TMP / "proj18")
M.GDRIVE_ROOT = ""
M.KRX_OPENAPI_KEY = ""
_boot()
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")
seed_officer_cache()

DEAD = TRADING - {"20251230"}


def mcap_s3_dead(date_c):
    d = _dt.date.fromisoformat(f"{date_c[:4]}-{date_c[4:6]}-{date_c[6:]}")
    alive = date_c in DEAD and not (d.year == 2025 and d.month == 12)
    df = pd.DataFrame({"시가총액": [CAPS[c] if alive else 0 for c in CODES]}, index=CODES)
    M._MCAP_CACHE[date_c] = (df, "pykrx(test-stub)")
    return df


M._mcap_frame = mcap_s3_dead
V4 = M.main()
s4 = {x["id"]: x for x in V4["snapshots"]}
check("S3 UNVERIFIED", s4["S3"]["status"], "UNVERIFIED")
check("S3 사유 EMPTY_UNIVERSE", s4["S3"]["status_reason"], "EMPTY_UNIVERSE")
check("S3 수집 진입 안 함 (신규호출 0)", s4["S3"]["api_new"], 0)
check("S3 엣지 0", s4["S3"]["edges"], 0)
check("S1/S2/S4 는 정상", [s4[k]["status"] for k in ("S1", "S2", "S4")], ["OK"] * 3)
t4 = {f"{x['from']}->{x['to']}": x for x in V4["transitions"]}
check("S2→S3 UNVERIFIED", t4["S2->S3"]["status"], "UNVERIFIED")
check("S3→S4 UNVERIFIED", t4["S3->S4"]["status"], "UNVERIFIED")
check("S1→S2 는 정상 산출", t4["S1->S2"]["status"], "OK")
check("UNVERIFIED 전이는 0 이 아니라 None", t4["S2->S3"]["edge_born"], None)
g4 = {g["id"]: g for g in V4["gates"]}
check("AΔ-1 UNVERIFIED (FAIL 로 위장하지 않음)", g4["AΔ-1"]["status"], "UNVERIFIED")
check("AΔ-3 FAIL (4/4 미달)", g4["AΔ-3"]["status"], "FAIL")
check("성공조건 미충족", V4["success_conditions"]["overall"], False)
M._mcap_frame = fake_mcap

# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[19] 신규 호출 5,000건 초과 → 수집 전 정지 (DART 호출 0건인 채로)")
reset_module_state()
M.PROJECT_ROOT = str(TMP / "proj19")
M.GDRIVE_ROOT = ""
M.KRX_OPENAPI_KEY = ""
M.CONFIRM_LARGE_COLLECTION = False
_boot()
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")
# 임원 캐시는 심지 않는다 — 전량 신규 호출 대상으로 만든다

V5 = M.main()
check("확인 대기 상태로 반환", V5["status"], "AWAITING_USER_CONFIRMATION")
check("정확한 예정 호출수 보고", V5["planned_calls"], 4 * NCO)
check("5,000 초과", V5["planned_calls"] > 5000, True)
budget_files = list((Path(M.PROJECT_ROOT).expanduser() / "cache" / "state").glob("call_budget_*.json"))
check("DART 호출 0건 (예산 파일조차 없음)", budget_files, [])
check("임원 캐시 디렉터리 비어 있음", list(M.DIR_CACHE_RAW.rglob("*.json")), [])
M.CONFIRM_LARGE_COLLECTION = True

print("\n" + "=" * 70)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
