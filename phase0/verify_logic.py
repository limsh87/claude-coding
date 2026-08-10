#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""축 A-Δ v1.3 순수 로직 검증 — 자격증명·네트워크·pandas 없이 돌린다.

핵심 확인 대상:
  #1 PIT: as_of 이후 접수(정정공시)가 폐기되는가 / 경계일이 포함되는가
  #2 휴장일: 시총>0 실측으로 직전 거래일을 찾는가
  #3 빈 유니버스: 수집 진입 전에 멈추는가
  #4 pykrx import 크래시(JSONDecodeError 등)가 실제로 흡수되는가 — 이번 개정의 핵심
  #5 캐시 로컬+드라이브 이중탐색이 로컬을 절대 덮어쓰지 않는가
  #6 호출예산이 실 필요량보다 낮은 임의 임계로 조기중단하지 않는가
"""
import importlib.util
import json
import sys
import tempfile
import datetime as _dt
from pathlib import Path

spec = importlib.util.spec_from_file_location("axd", str(Path(__file__).with_name("axis_a_delta_v13.py")))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

FAIL = []
N = 0


def check(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append(f"{name}: got={got!r} want={want!r}")
        print(f"  ✗ {name}: got={got!r} want={want!r}")
    else:
        print(f"  ✓ {name}")


def raises(name, exc, fn, *a, **k):
    global N
    N += 1
    try:
        fn(*a, **k)
    except exc:
        print(f"  ✓ {name}")
        return
    except Exception as e:
        FAIL.append(f"{name}: 잘못된 예외 {type(e).__name__}: {e}")
        print(f"  ✗ {name}: 잘못된 예외 {type(e).__name__}")
        return
    FAIL.append(f"{name}: 예외가 발생하지 않았다")
    print(f"  ✗ {name}: 예외 없음")


print("\n[1] P0_LOCAL_ROOT_ONLY — /content 계열 차단")
raises("/content 거부", M.ContractViolation, M.resolve_project_root, "/content")
raises("/content/drive/MyDrive 거부", M.ContractViolation, M.resolve_project_root,
       "/content/drive/MyDrive/quant")
raises("/gdrive 거부", M.ContractViolation, M.resolve_project_root, "/gdrive/x")
check("로컬 경로 허용", type(M.resolve_project_root("~/quant/phase0")).__name__, "PosixPath")
check("/contentious 는 오탐 아님",
      str(M.resolve_project_root("/tmp/contentious")).endswith("contentious"), True)

print("\n[2] P0_PIT_STRICT_DELTA — as_of = 법정 제출기한")
M.verify_snapshot_spec()
print("  ✓ FROZEN as_of 4건 == 법정기한 계산값")
for sid, _n, pe, _y, rc, as_of, _need in M.SNAPSHOT_SPEC:
    check(f"{sid} {pe}+{M._DEADLINE_DAYS[rc]}d", M._legal_deadline(pe, rc), as_of)
_orig = M.SNAPSHOT_SPEC
M.SNAPSHOT_SPEC = [("SX", "x", "2026-05-11", "2026", "11013", _dt.date.today().isoformat(), 1)]
raises("as_of == 실행일이면 중단", M.ContractViolation, M.verify_snapshot_spec)
M.SNAPSHOT_SPEC = _orig

print("\n[3] P0_NO_THRESHOLD_EDIT — 임계 frozen")
check("고정 해시 일치", M._sha256_thresholds(), M.GATE_THRESHOLDS_SHA256)
_t = dict(M.GATE_THRESHOLDS)
M.GATE_THRESHOLDS = {**_t, "AD2_born_total_median": 10}      # 게이트 통과용 하향 시도
check("임계 변경 시 해시 불일치", M._sha256_thresholds() != M.GATE_THRESHOLDS_SHA256, True)
M.GATE_THRESHOLDS = _t

print("\n[4] rcept_no → 접수일자 (추정 금지)")
check("정상 14자리", M.rcept_dt_of("20250814000123"), "20250814")
check("v1.2 오염 접수번호", M.rcept_dt_of("20260731900001"), "20260731")
check("빈 값", M.rcept_dt_of(""), "")
check("None", M.rcept_dt_of(None), "")
check("길이 부족", M.rcept_dt_of("2025"), "")
check("날짜 아님(13월)", M.rcept_dt_of("20251345000001"), "")
check("하이픈 포함", M.rcept_dt_of("2025-08-14-000123"), "20250814")

print("\n[5] 인물 식별자 (성명 + 출생년월)")
check("한자 병기 제거", M.norm_name("홍길동(洪吉童)"), "홍길동")
check("전각 괄호", M.norm_name("홍길동（洪吉童）"), "홍길동")
check("공백 제거", M.norm_name(" 홍 길동 "), "홍길동")
check("생년월 한글", M.norm_birth_ym("1960년 03월"), "196003")
check("생년월 한자리월", M.norm_birth_ym("1960년 3월"), "196003")
check("생년월 점표기", M.norm_birth_ym("1960.03"), "196003")
check("생년월 하이픈", M.norm_birth_ym("1960-12"), "196012")
check("생년월 결측", M.norm_birth_ym("-"), "")
check("생년월 빈값", M.norm_birth_ym(""), "")
check("생년월 13월 → 결측", M.norm_birth_ym("1960년 13월"), "")
check("인물키", M.person_key("홍길동(洪吉童)", "1960년 03월"), "홍길동|196003")
check("생년월 없으면 키 없음", M.person_key("홍길동", ""), "")
check("성명 없으면 키 없음", M.person_key("", "196003"), "")

print("\n[6] PIT 필터 — v1.2 결함 #1 의 직접 재현")
AS_OF = "2025-08-14"                                  # S1 (2025 반기)
recs = [
    {"corp_code": "A", "nm": "김", "birth_ym": "1970년 01월", "rcept_no": "20250811000001"},
    {"corp_code": "B", "nm": "이", "birth_ym": "1971년 02월", "rcept_no": "20250814000002"},  # 경계
    {"corp_code": "C", "nm": "박", "birth_ym": "1972년 03월", "rcept_no": "20250815000003"},  # +1일
    {"corp_code": "D", "nm": "최", "birth_ym": "1973년 04월", "rcept_no": "20260731000004"},  # v1.2
    {"corp_code": "E", "nm": "정", "birth_ym": "1974년 05월", "rcept_no": ""},                # 불량
]
kept, dropped = M.pit_filter(recs, AS_OF)
check("잔존 2건 (경계일 포함)", sorted(r["corp_code"] for r in kept), ["A", "B"])
check("폐기 3건", len(dropped), 3)
check("룩어헤드 2건",
      sorted(d["corp_code"] for d in dropped if d["_drop_reason"] == "LOOKAHEAD"), ["C", "D"])
check("접수번호불량 1건",
      [d["corp_code"] for d in dropped if d["_drop_reason"] == "BAD_RCEPT"], ["E"])
check("최종접수일 ≤ as_of", max(r["_rcept_dt"] for r in kept) <= M.compact(AS_OF), True)
check("20260731 이 잔존에 없다", any(r["_rcept_dt"] == "20260731" for r in kept), False)
check("폐기 0건은 이 데이터에서 불가능", len(dropped) > 0, True)
# as_of 를 실행일(2026-08-10)로 두면 v1.2 와 똑같이 전부 통과한다 — 결함의 인과를 고정한다
k2, d2 = M.pit_filter(recs, "2026-08-10")
check("as_of=실행일이면 폐기 1건뿐 (v1.2 재현)", len(d2), 1)
check("as_of=실행일이면 20260731 이 섞인다",
      max(r["_rcept_dt"] for r in k2), "20260731")

print("\n[7] 캐시 봉투 해석 (v1.2 캐시 재사용, as_of 필드 무시)")
raw = {"status": "000", "message": "정상", "list": [{"nm": "김"}]}
check("원본 응답", M.extract_dart_payload(raw), ("000", [{"nm": "김"}]))
env = {"as_of": "2026-08-10", "pit_filtered": True, "response": raw}      # v1.2 봉투
check("v1.2 봉투에서 원본 추출", M.extract_dart_payload(env), ("000", [{"nm": "김"}]))
check("list 만 저장된 캐시", M.extract_dart_payload([{"nm": "이"}]), ("", [{"nm": "이"}]))
check("데이터 없음(013)", M.extract_dart_payload({"status": "013", "message": "없음"}),
      ("013", []))
check("as_of 는 무시 대상 필드", "as_of" in M._IGNORED_CACHE_FIELDS, True)

print("\n[8] 그래프 구성")
c2c = {"C1": "000001", "C2": "000002", "C3": "000003", "C4": "000004"}
grecs = [
    {"corp_code": "C1", "nm": "홍길동", "birth_ym": "1960년 03월"},
    {"corp_code": "C2", "nm": "홍길동(洪吉童)", "birth_ym": "1960.03"},   # 동일 인물 → 엣지
    {"corp_code": "C3", "nm": "홍길동", "birth_ym": "1960년 03월"},        # 3종목 → C(3,2)=3
    {"corp_code": "C1", "nm": "무명씨", "birth_ym": ""},                   # 생년월 결측 → 제외
    {"corp_code": "C2", "nm": "무명씨", "birth_ym": ""},
    {"corp_code": "C4", "nm": "단독인", "birth_ym": "1980년 01월"},        # 겸직 아님 → 엣지 없음
    {"corp_code": "ZZ", "nm": "미매핑", "birth_ym": "1980년 02월"},        # corp_code 미매핑
]
g = M.build_graph(grecs, c2c)
check("엣지 3개 (3종목 겸직)", len(g["edges"]), 3)
check("엣지 내용", sorted(g["edges"]),
      [("000001", "000002"), ("000001", "000003"), ("000002", "000003")])
check("생년월 결측 제외 2건", g["records_no_birth"], 2)
check("corp 미매핑 1건", g["records_unmapped_corp"], 1)
check("겸직 인물 1명", g["persons_multi"], 1)
check("동명이인 의심 없음(3<8)", g["homonym_suspects"], [])
g2 = M.build_graph([{"corp_code": f"C{i}", "nm": "김철수", "birth_ym": "1965년 05월"}
                    for i in range(1, 11)],
                   {f"C{i}": f"{i:06d}" for i in range(1, 11)})
check("10종목 겸직 → C(10,2)=45 엣지", len(g2["edges"]), 45)
check("동명이인 의심 1명 감지(≥8)", len(g2["homonym_suspects"]), 1)

print("\n[9] 전이 born/died (합산 금지 · 외부 링크 유지)")
prev = {"snapshot": "S1", "measure": {"A", "B", "C"}, "listed": {"A", "B", "C", "X", "Y"},
        "edges": {("A", "B"), ("A", "X"), ("C", "Y")}}
nxt = {"snapshot": "S2", "measure": {"A", "B", "D"}, "listed": {"A", "B", "D", "X"},
       "edges": {("A", "B"), ("A", "D"), ("B", "X")}}
#  교집합 I = {A,B}
#  born = nxt-prev = {(A,D),(B,X)} → 둘 다 I 에 걸침 → 2
#  died = prev-nxt = {(A,X),(C,Y)} → (A,X) 만 I 에 걸침 → 1   ((C,Y) 는 C∉I 라 제외)
t = M.transition(prev, nxt)
check("교집합 2종목", t["intersect"], 2)
check("edge_born 2", t["edge_born"], 2)
check("edge_died 1", t["edge_died"], 1)
check("born/died 합산 안 함", (t["edge_born"], t["edge_died"]) != (3, 3), True)
check("측정대상 밖 X 와의 엣지 유지", t["edge_died"] >= 1, True)
check("born_ratio = 2/2", t["born_ratio"], 1.0)
check("born 종목수 2", t["stocks_with_born"], 2)
check("양끝 상장 born (A,D): D∉prev.listed → 1건만",
      t["born_both_listed"], 1)      # (B,X) 만 양끝이 두 스냅샷 모두 상장
ps = {r["code"]: (r["edge_born"], r["edge_died"]) for r in t["_per_stock"]}
check("종목단위 A", ps["A"], (1, 1))
check("종목단위 B", ps["B"], (1, 0))
check("교집합 밖 C 는 미출력", "C" in ps, False)
e = M.transition({"snapshot": "S1", "measure": set(), "listed": set(), "edges": set()},
                 {"snapshot": "S2", "measure": set(), "listed": set(), "edges": set()})
check("빈 교집합 born_ratio 0 (ZeroDivision 없음)", e["born_ratio"], 0.0)

print("\n[10] 게이트 산술")
check("중앙값 홀수", M._median([10, 50, 90]), 50.0)
check("중앙값 짝수", M._median([10, 50, 60, 90]), 55.0)
check("빈 리스트", M._median([]), None)
rr = [0.02, 0.08, 0.05]
check("AΔ-1 평균", round(sum(rr) / len(rr), 6), 0.05)
check("AΔ-1 판정(0.05 ≥ 0.05 → PASS)", (sum(rr) / len(rr)) >= 0.05, True)
check("AΔ-2 판정(중앙값 49 < 50 → FAIL)", M._median([10, 49, 300]) >= 50, False)

print("\n[11] to_code6 — 2024+ 영숫자 신형 티커")
check("구형 6자리 숫자", M.to_code6("005930"), "005930")
check("정수 입력 zfill", M.to_code6(5930), "005930")
check("A접두 구형표기", M.to_code6("A005930"), "005930")
check(".KS 접미 제거", M.to_code6("005930.KS"), "005930")
check("신형 영숫자 티커 보존(009701K)", M.to_code6("09701K"), "09701K")
check("신형 티커에 자리채움 오적용 안 함(009701 아님)", M.to_code6("09701K") != "009701", True)
check("소문자 신형 티커 대문자화", M.to_code6("09701k"), "09701K")
check("빈 문자열", M.to_code6(""), "")
check("None", M.to_code6(None), "")
check("NaN(float)", M.to_code6(float("nan")), "")
check("완전히 문자아닌 값", M.to_code6("!!!"), "")

print("\n[12] 임원 원본 blob — 로컬+드라이브 이중탐색 (skip-if-exists)")
tmp = Path(tempfile.mkdtemp())
M.ROOT = tmp
M.DIR_CACHE_RAW = tmp / "cache" / "raw" / "dart_exctv"
M.DIR_CACHE_META = tmp / "cache" / "meta"
M.DIR_REPORTS = tmp / "reports"
for d in (M.DIR_CACHE_RAW, M.DIR_CACHE_META, M.DIR_REPORTS):
    d.mkdir(parents=True, exist_ok=True)
for corp, files in {"00126380": ["2025_11012.json", "2025_11014.json"],
                    "00164742": ["2025_11012.json"],
                    "00401731": ["2026_11013.json"]}.items():
    for f in files:
        p = M.DIR_CACHE_RAW / corp / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"status":"000","list":[]}', encoding="utf-8")
(M.DIR_CACHE_RAW / "00126380" / "notes.txt").write_text("noise", encoding="utf-8")
inv = M.scan_cache_inventory()
check("2025/11012 = 2건", len(inv[("2025", "11012")]), 2)
check("2025/11014 = 1건", len(inv[("2025", "11014")]), 1)
check("2026/11013 = 1건", len(inv[("2026", "11013")]), 1)
check("json 아닌 파일 무시", ("notes", "txt") in inv, False)
check("미보유 키 = 0건", len(inv[("2025", "11011")]), 0)

drive_dir = tmp / "drive"
M.GDRIVE_ROOT = str(drive_dir)

local_existing = M.cache_path("00126380", "2025", "11012")   # 이미 스캔된 로컬 기존 파일
drive_only = M._drive_blob_path("00164742", "2025", "11011")  # 로컬엔 없고 드라이브에만
drive_only.parent.mkdir(parents=True, exist_ok=True)
drive_only.write_text('{"status":"000","list":[],"FROM":"drive"}', encoding="utf-8")
drive_dup = M._drive_blob_path("00126380", "2025", "11012")   # 로컬에도 이미 있는 키
drive_dup.parent.mkdir(parents=True, exist_ok=True)
drive_dup.write_text('{"BACKUP":"덮어쓰면 안 됨"}', encoding="utf-8")

keys = [("00126380", "2025", "11012"), ("00164742", "2025", "11011"), ("00999999", "2025", "11012")]
n_restored = M.restore_officer_blobs_from_drive(keys)
check("드라이브에만 있던 1건만 복원", n_restored, 1)
check("로컬 기존 파일 안 건드림(내용 그대로)",
      local_existing.read_text(encoding="utf-8"), '{"status":"000","list":[]}')
check("복원분이 로컬에 실존", M.cache_path("00164742", "2025", "11011").exists(), True)
check("복원분 내용 일치",
      M.cache_path("00164742", "2025", "11011").read_text(encoding="utf-8"),
      '{"status":"000","list":[],"FROM":"drive"}')
check("드라이브에도 로컬에도 없는 키는 그대로 없음",
      M.cache_path("00999999", "2025", "11012").exists(), False)

sync = M.sync_officer_blobs_to_drive(keys)
check("동기화 시도됨(GDRIVE_ROOT 설정됨)", sync["attempted"], True)
check("드라이브에 이미 있던 것들은 already_there로 집계",
      sync["already_there"] >= 2, True)          # 방금 복원한 것 + 원래 dup
check("로컬에 없는 999999 는 local_missing", sync["local_missing"], 1)
newer = M.cache_path("00777777", "2025", "11012")
newer.parent.mkdir(parents=True, exist_ok=True)
newer.write_text('{"status":"000","list":[]}', encoding="utf-8")
sync2 = M.sync_officer_blobs_to_drive([("00777777", "2025", "11012")])
check("신규 로컬파일 1건이 드라이브로 동기화(synced)", sync2["synced"], 1)
check("동기화된 파일이 드라이브에 실존", M._drive_blob_path("00777777", "2025", "11012").exists(), True)
check("GDRIVE_ROOT 미설정이면 시도 자체를 안 함",
      (lambda: (setattr(M, "GDRIVE_ROOT", ""), M.sync_officer_blobs_to_drive(keys)["attempted"])[1])(),
      False)
M.GDRIVE_ROOT = str(drive_dir)

print("\n[13] 공용 테이블(dart_corpcode 등) — 로컬+드라이브 이중탐색")
M.pd = None  # 이 섹션은 CSV 바이트를 그대로 복사/비교만 한다 — pandas 불필요
local_table = M.DIR_CACHE_META / "test_table.csv"
check("로컬·드라이브 둘 다 없으면 복원 안 됨",
      M.restore_shared_table("test_table", local_table), False)
remote_table = M.drive_shared("table", "test_table.csv")
remote_table.parent.mkdir(parents=True, exist_ok=True)
remote_table.write_text("corp_code,code\n00126380,005930\n", encoding="utf-8")
ok = M.restore_shared_table("test_table", local_table)
check("드라이브에 있으면 복원됨", ok, True)
check("복원된 내용 일치", local_table.read_text(encoding="utf-8"), "corp_code,code\n00126380,005930\n")
local_table.write_text("EXISTING_LOCAL_CONTENT\n", encoding="utf-8")
ok2 = M.restore_shared_table("test_table", local_table)
check("로컬에 이미 있으면 재복원 안 함(skip-if-exists)", ok2, False)
check("기존 로컬 내용 보존", local_table.read_text(encoding="utf-8"), "EXISTING_LOCAL_CONTENT\n")

pub_src = M.DIR_CACHE_META / "publish_me.csv"
pub_src.write_text("a,b\n1,2\n", encoding="utf-8")
pok = M.publish_shared_table("test_table", pub_src)
check("게시 성공", pok, True)
# 게시(publish)는 우리가 만든 최신본이 진실이므로 드라이브 쪽을 덮어쓴다 — 이는 restore 의
# skip-if-exists 와 반대 방향의 의도된 비대칭이다(로컬 원본 보호 vs 공용본 최신화).
check("게시는 드라이브 파일을 갱신한다(복원과 반대 방향의 의도된 동작)",
      remote_table.read_text(encoding="utf-8"), "a,b\n1,2\n")

print("\n[14] 저널 append-only (임원 수집 원장)")
jp = tmp / "journal_test.jsonl"
M.append_jsonl(jp, [{"a": 1}, {"a": 2}])
check("2줄 기록", len(M.read_jsonl(jp)), 2)
M.append_jsonl(jp, [{"a": 3}])
check("append 후 3줄(기존 줄 안 건드림)", len(M.read_jsonl(jp)), 3)
check("순서 보존", [r["a"] for r in M.read_jsonl(jp)], [1, 2, 3])
with open(jp, "a", encoding="utf-8") as _f:
    _f.write('{"broken json\n{"a": 4}\n')
rows = M.read_jsonl(jp)
check("깨진 줄은 건너뛰고 정상 줄은 읽는다", any(r.get("a") == 4 for r in rows), True)
check("존재하지 않는 파일은 빈 리스트", M.read_jsonl(tmp / "no_such.jsonl"), [])
check("빈 rows 로 append 해도 파일 생성 안 함(불필요한 I/O 회피)",
      (M.append_jsonl(tmp / "never_created.jsonl", []),
       (tmp / "never_created.jsonl").exists())[1], False)

print("\n[15] 예산 — 실 필요량 대비 사전계산 (임의 중도정지 임계 제거)")
M.DIR_STATE = tmp / "cache" / "state"
M.DIR_STATE.mkdir(parents=True, exist_ok=True)
check("CALL_BUDGET_STOP 는 더 이상 존재하지 않는다(실필요량보다 낮아 정상 콜드런도 멎던 결함)",
      hasattr(M, "CALL_BUDGET_STOP"), False)
check("일일한도만 존재", M.CALL_BUDGET_DAILY, 19500)
need_total = sum(n for *_, n in M.SNAPSHOT_SPEC)
check("4스냅샷 콜드 실필요량이 일일한도보다 여유 있게 작다(정상 콜드런이 중도정지 안 됨)",
      need_total < M.CALL_BUDGET_DAILY, True)

col = M.Collector("dummy")
check("초기 누적 0", col.calls_run, 0)
col.calls_today = M.CALL_BUDGET_DAILY - 1
check("일일한도 직전 예약 성공", col._reserve(), True)
check("일일한도 도달 시 예약 거부", col._reserve(), False)
check("halt = BUDGET_STOP_DAILY", col.halt, "BUDGET_STOP_DAILY")

col2 = M.Collector("dummy")
for _ in range(M.CIRCUIT_FAIL_N):
    col2._on_fail()
check("연속실패 10회 → 트립 1", col2.trips, 1)
check("트립 후 60초 대기 설정", col2.pause_until > 0, True)
check("아직 중단 아님", col2.halt, "")
check("연속실패가 AdaptiveDelay 도 감속시킴", col2.delay.cur > 0.4, True)
for _ in range(M.CIRCUIT_FAIL_N * 2):
    col2._on_fail()
check("트립 3회 → CIRCUIT_BREAKER", col2.halt, "CIRCUIT_BREAKER")

col3 = M.Collector("dummy")
for _ in range(M.CIRCUIT_FAIL_N - 1):
    col3._on_fail()
col3._on_ok()
col3._on_fail()
check("성공이 연속실패 카운터를 리셋", col3.trips, 0)

print("\n[16] AdaptiveDelay — 성공 스트릭 가속 · 실패 즉시 감속")
ad = M.AdaptiveDelay(lo=0.1, hi=1.0, start=0.5, speedup_every=3, speedup_factor=0.5,
                     backoff_factor=2.0)
check("초기값", ad.cur, 0.5)
ad.on_success()
ad.on_success()
check("스트릭 미달시 유지", ad.cur, 0.5)
ad.on_success()
check("스트릭 도달시 가속(0.5×0.5)", ad.cur, 0.25)
check("가속 후 스트릭 리셋", ad.streak, 0)
ad.on_failure()
check("실패 즉시 감속(0.25×2.0)", ad.cur, 0.5)
check("실패도 스트릭 리셋", ad.streak, 0)
ad2 = M.AdaptiveDelay(lo=0.2, hi=1.0, start=0.21, speedup_every=1, speedup_factor=0.1)
ad2.on_success()
check("바닥(lo) 아래로 안 내려감", ad2.cur, 0.2)
ad3 = M.AdaptiveDelay(lo=0.1, hi=0.6, start=0.5, backoff_factor=3.0)
ad3.on_failure()
check("상한(hi) 위로 안 올라감", ad3.cur, 0.6)

print("\n[17] KRX Open API — 키 미설정/네트워크 없음 시 조용히 생략")
_real_requests = M.requests
M.requests = None
M.KRX_OPENAPI_KEY = ""
M.KRX_OPENAPI_OK = False
check("키 없으면 probe False", M.probe_krx_openapi(), False)
check("키 없으면 mcap fetch None", M._mcap_frame_openapi("20250630"), None)
check("probe 후에도 OK 플래그 False", M.KRX_OPENAPI_OK, False)
M.requests = _real_requests

print("\n[18] pykrx_call 래퍼 — 예외를 절대 밖으로 흘리지 않는다 (P0_DEFENSIVE_PYKRX)")
M.PYKRX_AVAILABLE = False
M.stock = None
check("PYKRX_AVAILABLE=False 면 무조건 None(호출 자체를 안 함)",
      M.pykrx_call("get_market_cap_by_ticker", "20250630"), None)


class _BoomStock:
    """실제 크래시를 흉내낸다: 호출할 때마다 다른 예외를 던진다."""
    @staticmethod
    def get_market_cap_by_ticker(*a, **k):
        raise json.decoder.JSONDecodeError("Expecting value", "<html>error</html>", 0)

    @staticmethod
    def get_market_ticker_list(*a, **k):
        return ["005930", "000660"]

    @staticmethod
    def get_market_trading_value_by_date(*a, **k):
        raise ConnectionError("네트워크 붕괴")


M.PYKRX_AVAILABLE = True
M.stock = _BoomStock
check("JSONDecodeError 를 던지는 호출도 pykrx_call 은 None 반환",
      M.pykrx_call("get_market_cap_by_ticker", "20250630"), None)
check("ConnectionError 도 흡수", M.pykrx_call("get_market_trading_value_by_date"), None)
check("정상 호출은 그대로 통과",
      M.pykrx_call("get_market_ticker_list", "20250630", market="KOSPI"),
      ["005930", "000660"])
check("존재하지 않는 함수명은 None", M.pykrx_call("no_such_function_xyz"), None)
M.PYKRX_AVAILABLE = False
M.stock = None

print("\n[19] pykrx 방탄 import — 실제 크래시(JSONDecodeError) 재현으로 검증")
print("     (진짜 pykrx 패키지 대신, import 시점에 실제 결함처럼 예외를 던지는 가짜 패키지를 만들어 주입한다)")


def _make_fake_pykrx(init_body: str):
    d = Path(tempfile.mkdtemp())
    pkg = d / "pykrx"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(init_body, encoding="utf-8")
    (pkg / "stock.py").write_text("MARKER = 'fake_stock_loaded'\n", encoding="utf-8")
    return d


def _clear_pykrx_sys_state(path_entry):
    if str(path_entry) in sys.path:
        sys.path.remove(str(path_entry))
    for mod in list(sys.modules):
        if mod == "pykrx" or mod.startswith("pykrx."):
            del sys.modules[mod]


# ── (a) 항상 실패하는 가짜 pykrx: 실제 버그의 정확한 재현 ──────────────────────────────────
_always_fail = _make_fake_pykrx(
    "import json\n"
    "raise json.decoder.JSONDecodeError('Expecting value', '<html>KRX error page</html>', 12)\n")
sys.path.insert(0, str(_always_fail))
try:
    got, err = M._try_import_pykrx(with_creds=True)
    check("크래시 import — 예외가 새지 않고 (None, 진단문자열)로 반환됨", got, None)
    check("진단 메시지에 JSONDecodeError 포함", "JSONDecodeError" in err, True)
    M._purge_pykrx_modules()     # sys.path 는 그대로 둔다 — 같은 가짜 패키지로 재시도해야 한다

    M.KRX_ID, M.KRX_PW = "", ""
    M.PYKRX_AVAILABLE = True                      # 이전 상태 오염 방지용 사전 리셋
    got2 = M._import_pykrx_after_env()
    check("완전 실패해도 예외를 던지지 않고 None 반환 (P0_DEFENSIVE_PYKRX)", got2, None)
    check("PYKRX_AVAILABLE 이 False 로 전환됨", M.PYKRX_AVAILABLE, False)
    check("진단 문자열에 실제 주입한 JSONDecodeError 가 남는다(엉뚱한 ModuleNotFoundError 아님)",
          "JSONDecodeError" in M.PYKRX_DIAGNOSTIC, True)
finally:
    _clear_pykrx_sys_state(_always_fail)

# ── (b) 자격증명이 있을 때만 실패, 없으면 성공 — 실제 보고된 시나리오와 동일 ────────────────
_creds_only_fail = _make_fake_pykrx(
    "import os, json\n"
    "if os.environ.get('KRX_ID'):\n"
    "    raise json.decoder.JSONDecodeError('Expecting value', '<html>login failed</html>', 12)\n")
sys.path.insert(0, str(_creds_only_fail))
try:
    M.KRX_ID, M.KRX_PW = "baduser", "badpass"
    M.PYKRX_AVAILABLE = False
    M.PYKRX_DIAGNOSTIC = ""
    n_before = len(M.PYKRX_IMPORT_ORDER["attempts"])
    got3 = M._import_pykrx_after_env()
    check("자격증명 포함시 실패하지만 무자격 재시도로 결국 로드됨", got3 is not None, True)
    check("PYKRX_AVAILABLE 이 True 로 전환됨(무자격 재시도 성공)", M.PYKRX_AVAILABLE, True)
    check("2회 시도(자격증명 포함 실패 + 무자격 성공)가 기록됨",
          len(M.PYKRX_IMPORT_ORDER["attempts"]) - n_before, 2)
    check("첫 시도는 with_creds=True 로 실패",
          M.PYKRX_IMPORT_ORDER["attempts"][n_before]["ok"], False)
    check("두번째 시도는 with_creds=False 로 성공",
          (M.PYKRX_IMPORT_ORDER["attempts"][n_before + 1]["with_creds"],
           M.PYKRX_IMPORT_ORDER["attempts"][n_before + 1]["ok"]), (False, True))
finally:
    _clear_pykrx_sys_state(_creds_only_fail)
    M.KRX_ID = M.KRX_PW = ""
    M.PYKRX_AVAILABLE = False
    M.stock = None

# ── (c) 항상 성공하는 가짜 pykrx: 정상 경로가 여전히 동작하는지 ─────────────────────────────
_always_ok = _make_fake_pykrx("")
sys.path.insert(0, str(_always_ok))
try:
    M.KRX_ID, M.KRX_PW = "", ""
    got4 = M._import_pykrx_after_env()
    check("정상 pykrx 는 1회 시도로 로드됨", got4 is not None, True)
    check("PYKRX_AVAILABLE True", M.PYKRX_AVAILABLE, True)
finally:
    _clear_pykrx_sys_state(_always_ok)
    M.PYKRX_AVAILABLE = False
    M.stock = None

# ── (d) _purge_pykrx_modules 단위 확인 ──────────────────────────────────────────────────
import types as _types
sys.modules["pykrx"] = _types.ModuleType("pykrx")
sys.modules["pykrx.stock"] = _types.ModuleType("pykrx.stock")
n_purged = M._purge_pykrx_modules()
check("stale 모듈 2개 정리", n_purged, 2)
check("sys.modules 에서 완전히 제거됨",
      ("pykrx" not in sys.modules) and ("pykrx.stock" not in sys.modules), True)

print("\n[20] 계약/한계 기록")
check("계약 12개", len(M.CONTRACTS), 12)
check("방탄 pykrx 계약 존재", "P0_DEFENSIVE_PYKRX" in M.CONTRACTS, True)
check("다중소스 유니버스 계약 존재", "P0_MULTI_SOURCE_UNIVERSE" in M.CONTRACTS, True)
check("임계 근거 문장 포함",
      any("경험적 근거 없이 설정된 임계값" in s for s in M.KNOWN_LIMITATIONS), True)
check("백테스트 미구현 사유가 known_limitations 에 기록됨",
      any("P0_NO_STRATEGY" in s and "백테스트" in s for s in M.KNOWN_LIMITATIONS), True)
check("죽은 호출 이름 고정", M._DEAD_CALL_NAME, "get_index_portfolio_deposit_file")
check("측정대상 1000", M.MEASURE_N, 1000)
check("빈 유니버스 임계 100", M.EMPTY_UNIVERSE_MIN, 100)
check("워커 ≤ 8 (I/O바운드라 멀티프로세싱 대신 스레드 — 상한만 확인)", M.N_WORKERS <= 8, True)
check("전이 3개", M.TRANSITIONS, [("S1", "S2"), ("S2", "S3"), ("S3", "S4")])

print("\n[21] 거래일 스냅 / 빈 유니버스 가드 (pykrx 대역)")


class _FakePd:
    """resolve_trading_day 가 쓰는 pandas 표면만 흉내낸다."""
    @staticmethod
    def to_numeric(s, errors=None):
        return s

    class DataFrame:
        pass


class _Series(list):
    def fillna(self, v):
        return self

    def __gt__(self, v):
        return _Series([x > v for x in self])

    def sum(self):
        return sum(1 for x in self if x is True)


class _Frame:
    """휴장일이면 시총이 전부 0 — 실제 결함 재현 형태."""
    columns = ["시가총액"]

    def __init__(self, caps):
        self.caps = caps

    def __len__(self):
        return len(self.caps)

    def __getitem__(self, k):
        return _Series(self.caps)


_real_pd, _real_frame = M.pd, M._mcap_frame
M.pd = _FakePd
_FakePd.DataFrame = _Frame
CAL = {"20251231": [0] * 2903, "20251230": [1e9] * 2903,
       "20250630": [1e9] * 2900, "20260101": [0] * 10}
M._mcap_frame = lambda d: (_Frame(CAL[d]) if d in CAL else None)
eff, df, trail = M.resolve_trading_day("2025-12-31")
check("휴장일 12-31 → 직전 거래일 12-30", eff, "2025-12-30")
check("12-31 을 먼저 시도한 기록이 남는다", trail[0][0], "2025-12-31")
check("시총>0 0종목이 로그에 남는다", "시총>0 0" in trail[0][1], True)
eff2, _, _ = M.resolve_trading_day("2025-06-30")
check("거래일이면 이동 없음", eff2, "2025-06-30")
M._mcap_frame = lambda d: _Frame([0] * 2903)
eff3, df3, trail3 = M.resolve_trading_day("2025-12-31")
check("전부 휴장이면 None (수집 진입 금지)", eff3, None)
check("역행 11일치 시도 기록", len(trail3), M.TRADING_DAY_LOOKBACK + 1)
M.pd, M._mcap_frame = _real_pd, _real_frame

print("\n" + "=" * 70)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
