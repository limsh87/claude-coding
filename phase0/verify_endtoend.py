#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main() 전 구간 드라이런.

시장(pykrx)과 DART 를 바깥에서 가짜로 갈아끼워 오케스트레이션·판정표·산출물 생성까지 돌린다.
배포 파일 안에는 합성 경로가 없다(P0_LIVE_ONLY) — 주입은 전적으로 이 테스트 쪽에서 한다.
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


# ── [15] Collector.run 의 중단/재개 회계 ─────────────────────────────────────────────────
print("\n[15] 수집 중단 시 resume_todo 회계")
M.ROOT = TMP
M.DIR_STATE = TMP / "state"
M.DIR_STATE.mkdir(parents=True, exist_ok=True)
M.pd = pd

col = M.Collector("k")
jobs = [(f"{i:08d}", "2025", "11012") for i in range(60)]
calls = {"n": 0}


def fake_fetch(cp, y, r):
    calls["n"] += 1
    if calls["n"] > 20:
        col.halt = "BUDGET_STOP_RUN"       # 20건 처리 후 중단이 걸린 상황
        return "HALT"
    return "000"


col.fetch = fake_fetch
done, remaining = col.run(jobs, "T")
check("성공 20건", done, 20)
check("성공+잔여 = 전체 (누락도 중복도 없다)", done + len(remaining), len(jobs))
check("잔여에 중복 없음", len(remaining), len(set(remaining)))
check("성공한 건은 잔여에 없다", len(set(remaining)) + done, 60)

col2 = M.Collector("k")
col2.fetch = lambda cp, y, r: "013"        # 데이터 없음도 '확정된 사실'
d2, r2 = col2.run([("x", "2025", "11012")], "T")
check("013 은 성공으로 계상(재호출 안 함)", (d2, r2), (1, []))

col3 = M.Collector("k")
col3.fetch = lambda cp, y, r: 1 / 0        # 예외
d3, r3 = col3.run([("x", "2025", "11012")], "T")
check("예외 발생 건은 잔여로", (d3, len(r3)), (0, 1))

# ── [16] main() 드라이런 ────────────────────────────────────────────────────────────────
print("\n[16] main() 전 구간 드라이런")
ROOT = TMP / "proj"
M.PROJECT_ROOT = str(ROOT)
M.DART_API_KEY = "x" * 40
M.GDRIVE_BACKUP_DIR = str(TMP / "drive")
M.CONFIRM_LARGE_COLLECTION = True  # (복구)
M.INCLUDE_KONEX = False

rng = random.Random(7)
NCO = 1400                                        # 전 상장사 (테스트 규모)
CODES = [f"{i:06d}" for i in range(1, NCO + 1)]
CORPS = {c: f"{int(c):08d}" for c in CODES}       # 종목코드 → corp_code
CAPS = {c: (i + 1) * 1e8 for i, c in enumerate(CODES)}   # 하위 1,000 = 앞의 1,000개

TRADING = {"20250630", "20250930", "20251230", "20260331"}   # 20251231 은 휴장


class FakeStock:
    @staticmethod
    def get_market_ticker_list(date, market="ALL"):
        if date not in TRADING:
            return []
        return {"KOSPI": CODES[:400], "KOSDAQ": CODES[400:], "KONEX": [],
                "ALL": CODES}.get(market, CODES)


M._bootstrap = lambda: _boot()


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


def fake_mcap(date_c):
    caps = [CAPS[c] if date_c in TRADING else 0 for c in CODES]
    return pd.DataFrame({"시가총액": caps}, index=CODES)


M._mcap_frame = fake_mcap

# corpCode 파싱 결과 캐시를 미리 심어 둔다 → XML 을 열지 않는 경로를 탄다
_boot()
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")

# 임원 캐시를 원본 응답 형태로 심는다. 스냅샷마다 겸직 구조를 조금씩 바꿔 born/died 를 만든다.
SPEC = {s[0]: (s[3], s[4], s[5]) for s in M.SNAPSHOT_SPEC}
LOOKAHEAD = {"S1": "20260731000001", "S2": "20260215000001",
             "S3": "20260731000001", "S4": "20260801000001"}
for si, (sid, (yy, rc, as_of)) in enumerate(SPEC.items()):
    ok_no = M.compact(as_of)[:8] + "000001"
    for i, code in enumerate(CODES):
        rows = [{"nm": f"임원{i}_{k}", "birth_ym": f"19{60 + k}년 0{(k % 9) + 1}월",
                 "corp_code": CORPS[code], "rcept_no": ok_no} for k in range(3)]
        # 겸직: 코드 i 와 i+1 이 같은 인물을 공유. 스냅샷마다 공유 쌍을 옮긴다.
        if i % 7 == si % 7 and i + 1 < NCO:
            rows.append({"nm": "겸직인", "birth_ym": f"1955년 {(i % 12) + 1:02d}월",
                         "corp_code": CORPS[code], "rcept_no": ok_no})
        if i % 7 == (si + 1) % 7 and i + 1 < NCO:
            rows.append({"nm": "겸직인", "birth_ym": f"1955년 {((i - 1) % 12) + 1:02d}월",
                         "corp_code": CORPS[code], "rcept_no": ok_no})
        if i % 50 == 0:                       # 정정공시 = 룩어헤드. 반드시 폐기되어야 한다.
            rows.append({"nm": f"정정임원{i}", "birth_ym": "1966년 06월",
                         "corp_code": CORPS[code], "rcept_no": LOOKAHEAD[sid]})
        if i % 300 == 0:                      # 접수번호 불량
            rows.append({"nm": f"불량{i}", "birth_ym": "1966년 06월",
                         "corp_code": CORPS[code], "rcept_no": ""})
        # v1.2 봉투 형태로 저장 — as_of 가 박혀 있어도 무시되고 재필터링돼야 한다
        M.write_json(M.cache_path(CORPS[code], yy, rc),
                     {"as_of": "2026-08-10", "pit_filtered": True,
                      "response": {"status": "000", "message": "정상", "list": rows}})

V = M.main()

print()
check("run_mode LIVE", V["run_mode"], "LIVE")
check("정렬 A", V["alignment"], "A_OBSERVATION_TIME")
check("스냅샷 4개", len(V["snapshots"]), 4)
check("전이 3개", len(V["transitions"]), 3)
check("신규 API 호출 0건 (전량 캐시 히트)", V["cache"]["actual_new_calls"], 0)

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
check("축 B/C SKIPPED_BY_SCOPE",
      sorted(x["axis"] for x in V["skipped"] if x["status"] == "SKIPPED_BY_SCOPE"),
      ["A(본체)", "B(BigQuery)", "C(국민연금)"])
check("known_limitations 첫 문장 고정", V["known_limitations"][0],
      "AΔ-1=0.05, AΔ-2=50, A-5=600 은 경험적 근거 없이 설정된 임계값이다.")

print("\n[17] 산출물")
R = M.DIR_REPORTS
for f in ("phase0_verdict_v13.json", "phase0_verdict_v13.csv", "phase0_summary_v13.md",
          "diag_edge_events.csv", "diag_pit_dropped_delta.csv", "cache_inventory.json",
          "run_log.txt"):
    check(f"{f} 생성", (R / f).exists(), True)
ee = pd.read_csv(R / "diag_edge_events.csv", dtype=str)
check("diag_edge_events 3,000행 (전이3 × 교집합1000)", len(ee), 3000)
check("diag_edge_events 컬럼", list(ee.columns),
      ["transition", "code", "edge_born", "edge_died"])
pdrop = pd.read_csv(R / "diag_pit_dropped_delta.csv", dtype=str)
check("PIT 폐기 분포에 4개 스냅샷 모두", sorted(pdrop["snapshot"].unique()),
      ["S1", "S2", "S3", "S4"])
check("폐기 사유 두 종류", sorted(pdrop["reason"].unique()), ["BAD_RCEPT", "LOOKAHEAD"])
la = pdrop[pdrop["reason"] == "LOOKAHEAD"]
check("S1 룩어헤드 접수월 = 2026-07 (v1.2 가 흘려보낸 바로 그것)",
      sorted(la[la["snapshot"] == "S1"]["rcept_ym"].unique()), ["202607"])
check("분포표 컬럼", list(pdrop.columns),
      ["snapshot", "as_of", "report", "reason", "rcept_ym", "n_records", "n_corps",
       "min_rcept_dt", "max_rcept_dt"])
check("모든 룩어헤드 접수일 > as_of",
      all(r["min_rcept_dt"] > M.compact(r["as_of"]) for _, r in la.iterrows()), True)
check("폐기 레코드 건수 집계됨", int(la["n_records"].astype(int).sum()) > 0, True)
md = (R / "phase0_summary_v13.md").read_text(encoding="utf-8")
check("요약에 전이표", "edge_born" in md, True)
check("요약에 휴장일 스냅 표기", "2025-12-31→2025-12-30" in md, True)
check("요약에 해석·전략 제안 없음",
      any(w in md for w in ("추천", "전략을 제안", "매수", "포트폴리오 구성")), False)
inv = json.loads((R / "cache_inventory.json").read_text(encoding="utf-8"))
check("인벤토리에 실제 신규 호출 기록", inv["actual_new_calls"], 0)
check("인벤토리 4개 스냅샷 행", len(inv["rows"]), 4)
check("드라이브 백업 성공", V["backup"]["ok"], True)
check("백업 아카이브 존재", Path(V["backup"]["archive"]).exists(), True)

print("\n[18] 재실행 — 백업 .prev 보존")
V2 = M.main()
check("2회차도 신규 호출 0건", V2["cache"]["actual_new_calls"], 0)
check("이전 아카이브가 .prev 로 보존됨",
      Path(V2["backup"]["archive"] + ".prev").exists(), True)
check("2회차 결과 동일 (결정적)",
      [x["edge_born"] for x in V2["transitions"]], [x["edge_born"] for x in t])

print("\n" + "=" * 70)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")

# ── [19] 빈 유니버스 (v1.2 결함 #2+#3) ──────────────────────────────────────────────────
print("\n[19] S3 전면 휴장 → UNVERIFIED, 수집 진입 금지")
DEAD = TRADING - {"20251230"}                      # 12-30 도 휴장으로 만든다 → S3 복구 불가
_prev_mcap = M._mcap_frame


def mcap_s3_dead(date_c):
    d = _dt.date.fromisoformat(f"{date_c[:4]}-{date_c[4:6]}-{date_c[6:]}")
    alive = date_c in DEAD and not (d.year == 2025 and d.month == 12)
    return pd.DataFrame({"시가총액": [CAPS[c] if alive else 0 for c in CODES]}, index=CODES)


M._mcap_frame = mcap_s3_dead
M.PROJECT_ROOT = str(TMP / "proj_s3dead")
V3 = M.main()
s3 = {x["id"]: x for x in V3["snapshots"]}
check("S3 UNVERIFIED", s3["S3"]["status"], "UNVERIFIED")
check("S3 사유 EMPTY_UNIVERSE", s3["S3"]["status_reason"], "EMPTY_UNIVERSE")
check("S3 수집 진입 안 함 (신규호출 0)", s3["S3"]["api_new"], 0)
check("S3 엣지 0", s3["S3"]["edges"], 0)
check("S1/S2/S4 는 정상", [s3[k]["status"] for k in ("S1", "S2", "S4")], ["OK"] * 3)
t3 = {f"{x['from']}->{x['to']}": x for x in V3["transitions"]}
check("S2→S3 UNVERIFIED", t3["S2->S3"]["status"], "UNVERIFIED")
check("S3→S4 UNVERIFIED", t3["S3->S4"]["status"], "UNVERIFIED")
check("S1→S2 는 정상 산출", t3["S1->S2"]["status"], "OK")
check("UNVERIFIED 전이는 0 이 아니라 None", t3["S2->S3"]["edge_born"], None)
g3 = {g["id"]: g for g in V3["gates"]}
check("AΔ-1 UNVERIFIED (FAIL 로 위장하지 않음)", g3["AΔ-1"]["status"], "UNVERIFIED")
check("AΔ-2 UNVERIFIED", g3["AΔ-2"]["status"], "UNVERIFIED")
check("AΔ-3 FAIL (4/4 미달)", g3["AΔ-3"]["status"], "FAIL")
check("AΔ-3 실측 3", g3["AΔ-3"]["value"], 3)
check("성공조건 미충족", V3["success_conditions"]["overall"], False)
M._mcap_frame = _prev_mcap

# ── [20] P0_CACHE_FIRST 확인 대기 ───────────────────────────────────────────────────────
print("\n[20] 신규 호출 5,000건 초과 → 수집 전 정지")
M.CONFIRM_LARGE_COLLECTION = False
M.PROJECT_ROOT = str(TMP / "proj_bigcollect")     # 캐시 없는 새 루트
M.GDRIVE_BACKUP_DIR = ""                          # 드라이브 복원도 막아 진짜 '캐시 없음'을 만든다
_boot()                                           # corpCode 만 있고 임원 캐시는 없는 상태
pd.DataFrame({"corp_code": [CORPS[c] for c in CODES], "corp_name": CODES,
              "code": CODES, "modify_date": "20260101"}).to_csv(
    M._corpcode_parsed(), index=False, encoding="utf-8")
V4 = M.main()
check("확인 대기 상태로 반환", V4["status"], "AWAITING_USER_CONFIRMATION")
check("정확한 예정 호출수 보고", V4["planned_calls"], 4 * NCO)
check("5,000 초과", V4["planned_calls"] > 5000, True)
budget = list((Path(M.PROJECT_ROOT).expanduser() / "cache" / "state").glob("call_budget_*.json"))
check("DART 호출 0건 (예산 파일조차 없음)", budget, [])
check("임원 캐시 디렉터리 비어 있음", list(M.DIR_CACHE_RAW.rglob("*.json")), [])
M.CONFIRM_LARGE_COLLECTION = True  # (복구)

print("\n" + "=" * 70)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
