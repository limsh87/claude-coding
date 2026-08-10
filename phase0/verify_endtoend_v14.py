#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main() 전 구간 드라이런 — pandas 필요, 네트워크·자격증명 불필요.

시장 데이터 소스(3단 사다리)와 DART 를 **바깥에서** 가짜로 갈아끼워 오케스트레이션·판정표·
산출물 생성까지 돌린다. 배포 파일 안에는 합성 경로가 없다(P0_LIVE_ONLY) — 주입은 전적으로
이 테스트 쪽에서 한다.

시나리오
  [1] Plan A 성공 — 4스냅샷 · 3전이 · 산출물 9종
  [2] Plan A 실패 → Plan B 성공 (사다리 순서와 '성공하면 건너뛴다'가 실제로 지켜지는가)
  [3] Plan A·B 실패 → Plan C 성공 — 주식총수×종가 재구성 벌크 + S4 실측 대비 순위상관
  [4] 3단 모두 실패 (§2.4) — 전 스냅샷 UNVERIFIED, DART 임원 호출 0건
  [5] DART 진단이 '코드로 해결 불가' (§3.4) — 수집 진입 없이 캐시분으로만 측정
  [6] 예상 신규 호출 5,000 초과 (P0_CACHE_FIRST) — DART 호출 0건인 채로 정지
  [7] 휴장일 스냅 (2025-12-31 → 직전 거래일)
  [8] PIT 필터 무력화 시 즉시 중단 (P0_PIT_STRICT_DELTA)
  [9] 누적 12,000 도달 → resume_todo.json (§4.3)

    python phase0/verify_endtoend_v14.py
"""
import datetime as _dt
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

SRC = str(Path(__file__).with_name("axis_a_delta_v14.py"))
spec = importlib.util.spec_from_file_location("axd14e", SRC)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

TMP = Path(tempfile.mkdtemp())
FAIL, N = [], 0


def check(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append(f"{name}: got={got!r} want={want!r}")
        print(f"  x {name}: got={got!r} want={want!r}")
    else:
        print(f"  . {name}")


def truthy(name, got):
    check(name, bool(got), True)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  픽스처 — 합성 시장 / 합성 DART
# ══════════════════════════════════════════════════════════════════════════════════════════
N_STK, N_KSQ, N_KNX = 420, 830, 50            # 코넥스 제외 상장사 1,250
CODES = ([f"{i:06d}" for i in range(1, N_STK + N_KSQ + 1)] +
         [f"{i:06d}" for i in range(900001, 900001 + N_KNX)])
MKTS = ["STK"] * N_STK + ["KSQ"] * N_KSQ + ["KNX"] * N_KNX
NCO = N_STK + N_KSQ
CAPS = {c: (i + 1) * 1e8 for i, c in enumerate(CODES)}
CORPS = {c: f"{i + 1:08d}" for i, c in enumerate(CODES)}
CORP2CODE = {v: k for k, v in CORPS.items()}
SID_IDX = {"S1": 0, "S2": 1, "S3": 2, "S4": 3}

HOLIDAYS = {"2025-12-31"}                      # 분기말 휴장 — 이게 잡히는지가 핵심 검증 하나
_market_calls = []


def _is_trading(date_iso: str) -> bool:
    d = _dt.date.fromisoformat(date_iso)
    return d.weekday() < 5 and date_iso not in HOLIDAYS


def stub_snap(date_iso: str):
    """Plan A/B 가 이겼을 때 날짜당 1회 불리는 스냅샷 provider 의 대역."""
    _market_calls.append(date_iso)
    if not _is_trading(date_iso):
        return None, "휴장일"
    df = pd.DataFrame({"cap": [CAPS[c] for c in CODES], "mkt": MKTS}, index=CODES)
    return df, f"{len(df):,}종목"


def seed_corpcode(codes=None):
    cs = codes if codes is not None else CODES
    return pd.DataFrame({"corp_code": [CORPS[c] for c in cs], "corp_name": [f"회사{c}" for c in cs],
                         "code": list(cs), "modify_date": ["20260101"] * len(cs)})


def _officer_rows(corp_code: str, as_of: str, sid: str):
    """(성명, 출생년월) 겸직이 스냅샷마다 옮겨 다니도록 만든다 — born/died 가 둘 다 생긴다."""
    code = CORP2CODE.get(corp_code)
    if code is None:
        return []
    i = CODES.index(code)
    s = SID_IDX[sid]
    base = _dt.date.fromisoformat(as_of)
    # 20종목당 1곳은 as_of 이후 정정공시 → PIT 룩어헤드 폐기가 반드시 생긴다
    late = (i % 20 == 0)
    rc = (base + _dt.timedelta(days=5)) if late else (base - _dt.timedelta(days=10))
    rcept = f"{rc:%Y%m%d}{i:06d}"
    rows = [{"rcept_no": rcept, "corp_code": corp_code, "corp_name": f"회사{code}",
             "nm": f"고유{i}", "birth_ym": "1975년 05월", "ofcps": "대표이사"},
            {"rcept_no": rcept, "corp_code": corp_code, "corp_name": f"회사{code}",
             "nm": f"무생년{i}", "birth_ym": "", "ofcps": "사외이사"}]
    # 쌍 (j, j+1) 은 (j + s) % 5 == 0 인 스냅샷에서만 같은 사람을 공유한다
    for j in (i - 1, i):
        if j < 0 or j + 1 >= len(CODES):
            continue
        if (j + s) % 5 == 0:
            rows.append({"rcept_no": rcept, "corp_code": corp_code, "corp_name": f"회사{code}",
                         "nm": f"공유{j}", "birth_ym": "1970년 01월", "ofcps": "기타비상무이사"})
    return rows


_fetch_log = []


def stub_fetch(self, kind, corp_code, year, reprt):
    """Collector.fetch 대역 — 실제 캐시 파일까지 쓴다(캐시 재사용 경로도 함께 검증된다)."""
    _fetch_log.append((kind, corp_code, year, reprt))
    if not self._reserve():
        return "HALT"
    if kind == "exctv":
        as_of = next(a for _s, _n, _p, y, r, a, _q in M.SNAPSHOT_SPEC if y == year and r == reprt)
        sid = next(s for s, _n, _p, y, r, _a, _q in M.SNAPSHOT_SPEC if y == year and r == reprt)
        js = {"status": "000", "message": "정상", "list": _officer_rows(corp_code, as_of, sid)}
    else:
        code = CORP2CODE.get(corp_code, "")
        i = CODES.index(code) if code in CODES else 0
        mkt = MKTS[i] if i < len(MKTS) else "STK"
        cls = {"STK": "Y", "KSQ": "K", "KNX": "N"}[mkt]
        shares = (i + 1) * 1000
        js = {"status": "000", "message": "정상", "list": [
            {"rcept_no": "20260101000001", "corp_cls": cls, "corp_code": corp_code, "se": "보통주",
             "isu_stock_totqy": "999,999,999", "istc_totqy": f"{shares:,}",
             "tesstk_co": "0", "distb_stock_co": f"{shares:,}"},
            {"rcept_no": "20260101000001", "corp_cls": cls, "corp_code": corp_code, "se": "우선주",
             "istc_totqy": "1,000", "tesstk_co": "0"}]}
    M.write_json(self.path_for(kind, corp_code, year, reprt), js)
    self._on_call_ok()
    self.stat["dart_000"] += 1
    return "000"


def stub_price_fetch(self, ticker):
    """PriceStore._fetch 대역 — 종가 시계열을 합성한다. 캐시·커버리지 로직은 진짜가 돈다."""
    if ticker not in CAPS:
        return None, "미상장"
    i = CODES.index(ticker)
    out = {}
    d = _dt.date(2025, 1, 1)
    while d <= _dt.date(2026, 8, 10):
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out[d.isoformat()] = float(1000 + i)     # 시총 = 주식수 × 종가 가 코드순 단조가 되게
        d += _dt.timedelta(days=1)
    return out, f"{len(out)}일"


def _boot(sub: str, preflight_ok=True, code_fixable=True):
    root = TMP / sub
    M.PROJECT_ROOT = str(root)
    M.ROOT = M.resolve_project_root(M.PROJECT_ROOT)
    M.DIR_CACHE_RAW = M.ROOT / "cache" / "raw" / "dart_exctv"
    M.DIR_CACHE_SHARES = M.ROOT / "cache" / "raw" / "dart_shares"
    M.DIR_CACHE_PX = M.ROOT / "cache" / "raw" / "px"
    M.DIR_CACHE_META = M.ROOT / "cache" / "meta"
    M.DIR_STATE = M.ROOT / "cache" / "state"
    M.DIR_REPORTS = M.ROOT / "reports"
    M.DIR_CACHE_MARKET = M.ROOT / "cache" / "market"
    for d in (M.DIR_CACHE_RAW, M.DIR_CACHE_SHARES, M.DIR_CACHE_PX, M.DIR_CACHE_META,
              M.DIR_STATE, M.DIR_REPORTS, M.DIR_CACHE_MARKET):
        d.mkdir(parents=True, exist_ok=True)
    M._LOG_FH = open(M.DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")
    M.pd = pd
    import requests as _rq
    M.requests = _rq
    M.FDR_AVAILABLE = True
    M._check_parquet()
    # 실행 간 상태 초기화
    M._SNAP_MEM.clear()
    M.COLLECTOR = None
    M.PRICE_STORE = None
    M.MARKET_SOURCE.update({"plan": "", "name": "", "detail": ""})
    M.LADDER_DIAG["plans"] = []
    M.LADDER_DIAG["selected"] = ""
    M.LADDER_DIAG["conclusion"] = ""
    M.PLANC.update({"available": False, "reason": "", "shares_field": "", "canary": [],
                    "cross_validation": {}, "coverage": {}, "price": {}})
    M.DART_PREFLIGHT.update({
        "done": True, "ok": preflight_ok, "code_fixable": code_fixable,
        "classification": "정상 (HTTP 200 + 정상 JSON)" if preflight_ok else "연결 거부/차단",
        "action": "그대로 진행" if preflight_ok else "망 문제다. 코드로 해결할 수 없다",
        "detail": {"classification": "stub", "code_fixable": code_fixable}})
    M.write_json(M.DIR_REPORTS / "diag_dart_preflight.json", M.DART_PREFLIGHT["detail"])
    _market_calls.clear()
    _fetch_log.clear()
    return root


M._bootstrap = lambda: None
M.DART_API_KEY = "d" * 40
M.GDRIVE_ROOT = ""
M.CONFIRM_LARGE_COLLECTION = True
M.Collector.fetch = stub_fetch
M.PriceStore._fetch = stub_price_fetch
_real_plan_a, _real_plan_b, _real_plan_c = M.plan_a_pykrx, M.plan_b_marketplace, M.plan_c_reconstruct
_real_load_corpcode = M.load_corpcode
M.load_corpcode = lambda: seed_corpcode()


def plan_ok(letter, name):
    def _f(*a, **k):
        rec = M._plan_record(letter, f"stub {name}")
        M._step(rec, "카나리", True, "1,300종목")
        rec["ok"] = True
        return True
    return _f


def plan_ng(letter, why):
    def _f(*a, **k):
        rec = M._plan_record(letter, f"stub {letter}")
        M._step(rec, "카나리", False, why)
        rec["reason"] = why
        return False
    return _f


# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[1] Plan A 성공 — 4스냅샷 · 3전이 · 산출물")
_boot("s1")
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.plan_b_marketplace = plan_ng("B", "호출되면 안 된다")
M.plan_c_reconstruct = plan_ng("C", "호출되면 안 된다")
M.snap_plan_a = stub_snap
V = M.main()

check("선택된 Plan", V["data_sources"]["selected_plan"], "A")
check("Plan A 성공 시 사다리는 1단에서 끝난다", len(V["market_source_ladder"]["plans"]), 1)
snaps = {s["id"]: s for s in V["snapshots"]}
check("4개 스냅샷 모두 OK", [snaps[k]["status"] for k in ("S1", "S2", "S3", "S4")], ["OK"] * 4)
check("노드 = KONEX 제외 전 상장사", snaps["S1"]["nodes"], NCO)
check("S3 휴장일 스냅", (snaps["S3"]["date_nominal"], snaps["S3"]["date"]),
      ("2025-12-31", "2025-12-30"))
truthy("모든 스냅샷에서 PIT 폐기가 0이 아니다", all(snaps[k]["pit_dropped"] > 0 for k in snaps))
truthy("룩어헤드 폐기가 4개 모두 0이 아니다",
       all(snaps[k]["pit_dropped_lookahead"] > 0 for k in snaps))
truthy("최종접수일 ≤ as_of",
       all(snaps[k]["last_rcept_dt"] <= M.compact(snaps[k]["as_of"]) for k in snaps))
truthy("출생년월 결측이 엣지에서 빠진 건수가 기록된다",
       all(snaps[k]["records_no_birth"] > 0 for k in snaps))
trans = {f"{t['from']}->{t['to']}": t for t in V["transitions"]}
check("전이 3개", len(trans), 3)
truthy("전이 3개 모두 OK", all(t["status"] == "OK" for t in trans.values()))
truthy("edge_born 이 산출된다", all(t["edge_born"] is not None for t in trans.values()))
truthy("edge_died 가 산출된다", all(t["edge_died"] is not None for t in trans.values()))
truthy("born 과 died 가 각각 0보다 크다",
       all(t["edge_born"] > 0 and t["edge_died"] > 0 for t in trans.values()))
check("교집합 = 하위 1,000종목", trans["S1->S2"]["intersect"], M.MEASURE_N)
check("성공조건 ① 충족", V["success_conditions"]["pit_evidence"], True)
check("성공조건 ② 충족", V["success_conditions"]["delta_measured"], True)
check("전체 성공", V["success_conditions"]["overall"], True)
check("AΔ-3 는 4/4 PASS", {g["id"]: g["status"] for g in V["gates"]}["AΔ-3"], "PASS")
for f in ("phase0_verdict_v14.json", "phase0_verdict_v14.csv", "phase0_summary_v14.md",
          "diag_market_source.json", "diag_dart_preflight.json", "diag_edge_events.csv",
          "diag_pit_dropped_delta.csv", "cache_inventory.json", "run_log.txt"):
    truthy(f"산출물 {f}", (M.DIR_REPORTS / f).exists())
_pit = pd.read_csv(M.DIR_REPORTS / "diag_pit_dropped_delta.csv")
truthy("PIT 폐기 분포표에 LOOKAHEAD 행이 있다", (_pit["reason"] == "LOOKAHEAD").any())
_ev = pd.read_csv(M.DIR_REPORTS / "diag_edge_events.csv")
check("종목단위 born/died 표 행 수 = 전이 3 × 교집합", len(_ev), 3 * M.MEASURE_N)
_md = (M.DIR_REPORTS / "phase0_summary_v14.md").read_text(encoding="utf-8")
truthy("요약에 사다리 표가 있다", "3단 사다리" in _md)
truthy("요약에 edge_born 열이 있다", "edge_born" in _md)

print("\n[1b] 재실행 — 캐시 히트로 신규 호출 0건")
_fetch_log.clear()
_market_calls.clear()
M._SNAP_MEM.clear()
M.COLLECTOR = None
V1b = M.main()
check("DART 신규 호출 0건", len([x for x in _fetch_log if x[0] == "exctv"]), 0)
# 확정된 거래일은 네트워크를 타지 않는다. 다만 '그 날 데이터 없음'은 디스크에 캐시하지
# 않으므로(오늘의 휴장 응답이 내일 실데이터로 바뀔 수 있다) 휴장인 명목일자만 매 실행
# 1회 재확인된다 — 스냅샷당 최대 1회다.
check("확정된 거래일은 재조회하지 않는다 (휴장 명목일자만 1회 재확인)",
      sorted(set(_market_calls)), ["2025-12-31"])
check("휴장일 재확인은 스냅샷당 1회를 넘지 않는다", len(_market_calls) <= 4, True)
s1b = {s["id"]: s for s in V1b["snapshots"]}
check("캐시히트로도 같은 엣지 수", s1b["S1"]["edges"], snaps["S1"]["edges"])
check("캐시 인벤토리의 실제 신규 호출 0", V1b["cache"]["actual_new_calls"], 0)

print("\n[2] Plan A 실패 → Plan B 성공 (Plan C 는 호출되면 안 된다)")
_boot("s2")
M.plan_a_pykrx = plan_ng("A", "카나리 0종목 — 로그인 없이는 조회 불가")
M.plan_b_marketplace = plan_ok("B", "marketplace")
_c_called = {"n": 0}


def _c_spy(*a, **k):
    _c_called["n"] += 1
    return False


M.plan_c_reconstruct = _c_spy
M.snap_plan_b = stub_snap
V2 = M.main()
check("선택된 Plan", V2["data_sources"]["selected_plan"], "B")
check("Plan C 는 호출되지 않았다", _c_called["n"], 0)
check("사다리에 A 실패 · B 성공이 남는다",
      [(p["plan"], p["ok"]) for p in V2["market_source_ladder"]["plans"]], [("A", False), ("B", True)])
truthy("A 의 실패 사유 원문이 남는다",
       "카나리 0종목" in V2["market_source_ladder"]["plans"][0]["reason"])
check("전이 3개 산출", sum(1 for t in V2["transitions"] if t["status"] == "OK"), 3)

print("\n[3] Plan A·B 실패 → Plan C 성공 (주식총수 × 종가 재구성 + 순위상관)")
_boot("s3")
SMALL = CODES[:300] + CODES[-40:]                    # 코스피/코스닥 300 + 코넥스 40
M.load_corpcode = lambda: seed_corpcode(SMALL)
M.plan_a_pykrx = plan_ng("A", "pykrx import 실패")
M.plan_b_marketplace = plan_ng("B", "로그인 응답이 JSON 이 아니다")


def _plan_c_stub(cc_df, code2corp):
    """진짜 plan_c_reconstruct 의 카나리 부분만 대역으로 세운다 — 벌크는 진짜가 돈다."""
    rec = M._plan_record("C", "KRX 없이 시총 자체 계산")
    M._step(rec, "카나리 DART 주식총수 10종목", True, "정상 파싱 10/10")
    M._step(rec, "카나리 FDR 종가", True, "10/10")
    years = sorted({int(s[1][:4]) for s in M.SNAPSHOT_SPEC})
    M.PRICE_STORE = M.PriceStore(years, "2025-01-01", "2026-08-10")
    M.PRICE_STORE.set_keep_window([s[1] for s in M.SNAPSHOT_SPEC],
                                  M.TRADING_DAY_LOOKBACK + M.PLANC_PRICE_STALE_MAX_DAYS)
    M.PLANC["available"] = True
    M.PLANC["shares_field"] = M.PLANC_SHARES_FIELD_PRIMARY
    rec["ok"] = True
    return True


M.plan_c_reconstruct = _plan_c_stub
# S4 실측 스냅샷을 local_cache 에 심는다 (§2.3 교차검증의 기준값)
_ref = pd.DataFrame({"cap": [CAPS[c] * 1.0 for c in SMALL], "mkt": [
    MKTS[CODES.index(c)] for c in SMALL]}, index=SMALL)
M._snap_write_csv(_ref, M._krx_snap_path("2026-03-31"))
V3 = M.main()
check("선택된 Plan", V3["data_sources"]["selected_plan"], "C")
s3 = {s["id"]: s for s in V3["snapshots"]}
check("4개 스냅샷 모두 OK", [s3[k]["status"] for k in ("S1", "S2", "S3", "S4")], ["OK"] * 4)
check("시총 소스가 Plan C 재구성으로 기록된다", s3["S1"]["mcap_source"], "planc_reconstructed")
check("균일 모드에서는 S4 실측 캐시를 유니버스에 쓰지 않는다",
      s3["S4"]["mcap_source"] in ("planc_reconstructed", "local_cache_planc"), True)
check("corp_cls 로 KONEX 를 걸러낸다", s3["S1"]["nodes"], 300)
check("S3 휴장일 스냅(종가 기준 거래일 판정)", s3["S3"]["date"], "2025-12-30")
truthy("주식총수를 실제로 수집했다", len([x for x in _fetch_log if x[0] == "shares"]) > 0)
truthy("재구성 스냅샷 파일이 남는다",
       (M.DIR_CACHE_MARKET / "planc_mcap_20250630.csv").exists())
truthy("종가 캐시가 남는다 (§2.3-3)", M.count_px_cached() > 0)
xv = V3["plan_c"]["cross_validation"]
check("교차검증 수행됨", xv["performed"], True)
check("스피어만 = 1 (합성 데이터는 순위가 완전 일치)", round(xv["spearman"], 6), 1.0)
check("교차검증 임계", xv["threshold"], 0.95)
check("신뢰 가능 판정", xv["trustworthy"], True)
check("하위 1,000 집합 일치율 기록", xv["bottom_overlap_ratio"], 1.0)
check("자기주식 차감 정책이 기록된다",
      V3["plan_c"]["coverage"]["S1"]["treasury_deducted"], False)
check("전이 3개 산출", sum(1 for t in V3["transitions"] if t["status"] == "OK"), 3)
truthy("known_limitations 에 Plan C 재구성값 경고가 있다",
       any("재구성값" in s for s in V3["known_limitations"]))
truthy("known_limitations 에 교차검증 결과가 들어간다",
       any("스피어만" in s for s in V3["known_limitations"]))
_dm = json.loads((M.DIR_REPORTS / "diag_market_source.json").read_text(encoding="utf-8"))
check("diag_market_source.json 에 3단 전부 기록", [p["plan"] for p in _dm["plans"]],
      ["A", "B", "C"])
check("선택 결과 기록", _dm["selected"], "C")
M.load_corpcode = lambda: seed_corpcode()

print("\n[4] 3단 모두 실패 (§2.4) — 전 스냅샷 UNVERIFIED, DART 임원 호출 0건")
_boot("s4")
M.plan_a_pykrx = plan_ng("A", "pykrx import 실패: JSONDecodeError")
M.plan_b_marketplace = plan_ng("B", "로그인 응답이 JSON 이 아니다(차단 페이지)")
M.plan_c_reconstruct = plan_ng("C", "DART 주식총수 카나리 실패")
V4 = M.main()
check("선택된 Plan 없음", V4["data_sources"]["selected_plan"], "NONE")
s4 = {s["id"]: s for s in V4["snapshots"]}
check("4개 전부 UNVERIFIED", [s4[k]["status"] for k in ("S1", "S2", "S3", "S4")],
      ["UNVERIFIED"] * 4)
check("사유는 NO_MARKET_SOURCE", s4["S1"]["status_reason"], "NO_MARKET_SOURCE")
check("임원현황 수집에 진입하지 않았다", len([x for x in _fetch_log if x[0] == "exctv"]), 0)
check("전이 3개 전부 UNVERIFIED",
      [t["status"] for t in V4["transitions"]], ["UNVERIFIED"] * 3)
check("UNVERIFIED 전이는 0 이 아니라 None", V4["transitions"][0]["edge_born"], None)
g4 = {g["id"]: g for g in V4["gates"]}
check("AΔ-1 은 FAIL 로 위장하지 않고 UNVERIFIED", g4["AΔ-1"]["status"], "UNVERIFIED")
check("AΔ-3 는 FAIL (4/4 미달)", g4["AΔ-3"]["status"], "FAIL")
check("성공조건 미충족", V4["success_conditions"]["overall"], False)
truthy("3단 실패가 결론에 남는다", "3단 모두 실패" in V4["market_source_ladder"]["conclusion"])
truthy("각 Plan 의 실패 사유 원문이 전부 남는다",
       all(p["reason"] for p in V4["market_source_ladder"]["plans"]))

print("\n[5] DART 진단 '코드로 해결 불가' (§3.4) — 수집 진입 없이 캐시분으로만")
_boot("s5", preflight_ok=False, code_fixable=False)
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.plan_b_marketplace = plan_ng("B", "호출되면 안 된다")
M.plan_c_reconstruct = plan_ng("C", "호출되면 안 된다")
M.snap_plan_a = stub_snap
# S4 임원 캐시만 미리 심어 둔다 (v1.3 이 남긴 999건 상황의 재현)
_col = M.Collector("d" * 40)
for c in CODES[:400]:
    stub_fetch(_col, "exctv", CORPS[c], "2026", "11013")
_fetch_log.clear()
V5 = M.main()
check("신규 임원 호출 0건", len([x for x in _fetch_log if x[0] == "exctv"]), 0)
s5 = {s["id"]: s for s in V5["snapshots"]}
check("유니버스 자체는 확보된다(시장 소스는 살아 있으므로)", s5["S4"]["status"], "OK")
truthy("캐시된 400사만 읽혔다", s5["S4"]["files_read"] == 400)
truthy("미보유가 그대로 기록된다(결측은 결측으로)", s5["S4"]["cache_miss"] > 0)
check("S1 은 캐시가 없어 그래프가 비어 있다", s5["S1"]["edges"], 0)
check("AΔ-3 FAIL", {g["id"]: g for g in V5["gates"]}["AΔ-3"]["status"], "FAIL")
check("성공조건 미충족", V5["success_conditions"]["overall"], False)

print("\n[6] P0_CACHE_FIRST — 예상 신규 호출 5,000 초과 시 DART 호출 0건인 채로 정지")
_boot("s6")
M.CONFIRM_LARGE_COLLECTION = False
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.snap_plan_a = stub_snap
# 이 픽스처의 예정 호출은 정확히 4 × 1,250 = 5,000 건이다. 계약은 '초과'이므로 5,000 은
# 걸리지 않고 그대로 진행되어야 한다 — 경계를 '이상'으로 잘못 구현했는지 여기서 잡는다.
check("정확히 5,000 은 초과가 아니므로 진행된다", "status" in M.main(), False)
_gate_real = M.LARGE_COLLECTION_GATE
M.LARGE_COLLECTION_GATE = 1000
_boot("s6b")
_fetch_log.clear()
V6 = M.main()
M.LARGE_COLLECTION_GATE = _gate_real
check("게이트 상수는 5,000 으로 되돌아간다", M.LARGE_COLLECTION_GATE, 5000)
check("확인 대기 상태로 반환", V6["status"], "AWAITING_USER_CONFIRMATION")
check("정지 단계 표기", V6["stage"], "EXCTV")
check("정확한 예정 호출수 (4스냅샷 × KONEX 제외)", V6["planned_calls"], 4 * NCO)
check("게이트 초과", V6["planned_calls"] > 1000, True)
check("DART 호출 0건", len(_fetch_log), 0)
check("임원 캐시 디렉터리 비어 있음", list(M.DIR_CACHE_RAW.rglob("*.json")), [])
check("예산 파일조차 만들지 않았다", list(M.DIR_STATE.glob("call_budget_*.json")), [])
M.CONFIRM_LARGE_COLLECTION = True

print("\n[7] 특정 스냅샷만 시장 데이터가 없을 때 — 그 스냅샷만 UNVERIFIED")
_boot("s7")
_saved_holidays = set(HOLIDAYS)
HOLIDAYS.update((_dt.date(2025, 9, 30) - _dt.timedelta(days=k)).isoformat() for k in range(12))
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.snap_plan_a = stub_snap
V7 = M.main()
s7 = {s["id"]: s for s in V7["snapshots"]}
check("S2 만 UNVERIFIED", [s7[k]["status"] for k in ("S1", "S2", "S3", "S4")],
      ["OK", "UNVERIFIED", "OK", "OK"])
check("사유는 EMPTY_UNIVERSE", s7["S2"]["status_reason"], "EMPTY_UNIVERSE")
check("S2 는 수집에 진입하지 않았다", s7["S2"]["api_new"], 0)
t7 = {f"{t['from']}->{t['to']}": t for t in V7["transitions"]}
check("S1→S2 UNVERIFIED", t7["S1->S2"]["status"], "UNVERIFIED")
check("S2→S3 UNVERIFIED", t7["S2->S3"]["status"], "UNVERIFIED")
check("S3→S4 는 정상 산출", t7["S3->S4"]["status"], "OK")
check("일부만 UNVERIFIED 면 AΔ-1 도 UNVERIFIED",
      {g["id"]: g for g in V7["gates"]}["AΔ-1"]["status"], "UNVERIFIED")
HOLIDAYS.clear()
HOLIDAYS.update(_saved_holidays)

print("\n[8] P0_PIT_STRICT_DELTA — 필터가 무력화되면 즉시 중단")
_boot("s8")
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.snap_plan_a = stub_snap
_real_pit = M.pit_filter
M.pit_filter = lambda recs, as_of: ([{**r, "_rcept_dt": M.rcept_dt_of(r.get("rcept_no"))}
                                     for r in recs], [])      # 필터를 통째로 무력화
_raised = ""
try:
    M.main()
except M.ContractViolation as e:
    _raised = str(e)
finally:
    M.pit_filter = _real_pit
truthy("계약 위반으로 중단된다", "P0_PIT_STRICT_DELTA" in _raised)
truthy("어느 스냅샷의 어떤 날짜인지 메시지에 있다", "as_of" in _raised)

print("\n[9] 예산 누적 12,000 도달 → resume_todo.json (§4.3)")
_boot("s9")
M.plan_a_pykrx = plan_ok("A", "pykrx")
M.snap_plan_a = stub_snap
M.write_json(M.DIR_STATE / f"call_budget_{M.RUN_STARTED:%Y%m%d}.json",
             {"date": f"{M.RUN_STARTED:%Y-%m-%d}", "calls": M.CALL_BUDGET_STOP_CUMULATIVE - 50})
V9 = M.main()
_rt = M.DIR_REPORTS / "resume_todo.json"
truthy("resume_todo.json 이 생성된다", _rt.exists())
_rj = json.loads(_rt.read_text(encoding="utf-8"))
check("중단 사유", _rj["halt"], "BUDGET_STOP_CUMULATIVE")
check("중단 임계 기록", _rj["stop_threshold"], 12000)
truthy("남은 작업 목록이 실려 있다", len(_rj["remaining"]) > 0)
check("임계까지 남은 50건만 쓰고 멈춘다 (예약 카운터 기준)",
      V9["cache"]["actual_new_calls"], 50)
truthy("수집된 분량으로 측정은 계속된다 — 중단이지 실패가 아니다",
       any(s["files_read"] > 0 for s in V9["snapshots"] if "files_read" in s))
truthy("남은 작업은 중복 없이 실린다", len(_rj["remaining"]) == len({tuple(x) for x in _rj["remaining"]}))

M.plan_a_pykrx, M.plan_b_marketplace = _real_plan_a, _real_plan_b
M.plan_c_reconstruct, M.load_corpcode = _real_plan_c, _real_load_corpcode

print("\n" + "=" * 78)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
