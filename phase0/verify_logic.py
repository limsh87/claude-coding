#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""축 A-Δ v1.3 순수 로직 검증 — 자격증명·네트워크 없이 돌린다.

핵심은 v1.2 를 무효화한 세 결함이 실제로 막히는지다:
  #1 PIT: as_of 이후 접수(정정공시)가 폐기되는가 / 경계일이 포함되는가
  #2 휴장일: 시총>0 실측으로 직전 거래일을 찾는가
  #3 빈 유니버스: 수집 진입 전에 멈추는가
"""
import importlib.util
import json
import sys
import tarfile
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

print("\n[7] 캐시 봉투 해석 (§2.4 — v1.2 캐시 재사용, as_of 필드 무시)")
raw = {"status": "000", "message": "정상", "list": [{"nm": "김"}]}
check("원본 응답", M.extract_dart_payload(raw), ("000", [{"nm": "김"}]))
env = {"as_of": "2026-08-10", "pit_filtered": True, "response": raw}      # v1.2 봉투
check("v1.2 봉투에서 원본 추출", M.extract_dart_payload(env), ("000", [{"nm": "김"}]))
check("list 만 저장된 캐시", M.extract_dart_payload([{"nm": "이"}]), ("", [{"nm": "이"}]))
check("데이터 없음(013)", M.extract_dart_payload({"status": "013", "message": "없음"}),
      ("013", []))
check("as_of 는 무시 대상 필드", "as_of" in M._IGNORED_CACHE_FIELDS, True)

print("\n[8] 그래프 구성 (§4.1)")
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

print("\n[9] 전이 born/died (§4.2 — 합산 금지 · 외부 링크 유지)")
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

print("\n[11] 캐시 인벤토리 · 드라이브 복원")
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

drive = tmp / "drive"
drive.mkdir()
stage = tmp / "stage" / "cache" / "raw" / "dart_exctv"
(stage / "00126380").mkdir(parents=True)
(stage / "00126380" / "2025_11012.json").write_text('{"BACKUP":"덮어쓰면 안 됨"}', encoding="utf-8")
(stage / "00999999").mkdir(parents=True)
(stage / "00999999" / "2025_11011.json").write_text('{"status":"000","list":[]}', encoding="utf-8")
with tarfile.open(drive / M.BACKUP_NAME, "w:gz") as tf:
    tf.add(stage, arcname="cache/raw/dart_exctv")
    ti = tarfile.TarInfo("../../../etc/evil")           # 경로 탈출 시도
    payload = b"x"
    ti.size = len(payload)
    import io as _io
    tf.addfile(ti, _io.BytesIO(payload))
M.GDRIVE_BACKUP_DIR = str(drive)
res = M.restore_from_drive()
check("신규 1건 복원", res["restored"], 1)
check("기존 1건 건너뜀", res["skipped_existing"], 1)
check("로컬 파일 덮어쓰지 않음",
      (M.DIR_CACHE_RAW / "00126380" / "2025_11012.json").read_text(encoding="utf-8"),
      '{"status":"000","list":[]}')
check("경로 탈출 멤버 거부(무해화 아님)", res["rejected_members"], 1)
check("ROOT 밖에 쓰지 않음", (tmp.parent / "etc" / "evil").exists(), False)
check("ROOT 안에도 둔갑해서 쓰지 않음", (tmp / "etc" / "evil").exists(), False)
check("복원 후 재집계 2025/11011 = 1건",
      len(M.scan_cache_inventory()[("2025", "11011")]), 1)

print("\n[12] 예산 · 서킷브레이커")
M.DIR_STATE = tmp / "cache" / "state"
M.DIR_STATE.mkdir(parents=True, exist_ok=True)
M.pd = type("X", (), {})()          # write_json 만 쓰므로 pandas 불필요
col = M.Collector("dummy")
check("초기 누적 0", col.calls_run, 0)
col.calls_run = M.CALL_BUDGET_STOP - 1
check("예산 직전 예약 성공", col._reserve(), True)
check("예산 도달 시 예약 거부", col._reserve(), False)
check("halt = BUDGET_STOP_RUN", col.halt, "BUDGET_STOP_RUN")
col2 = M.Collector("dummy")
for _ in range(M.CIRCUIT_FAIL_N):
    col2._on_fail()
check("연속실패 10회 → 트립 1", col2.trips, 1)
check("트립 후 60초 대기 설정", col2.pause_until > 0, True)
check("아직 중단 아님", col2.halt, "")
for _ in range(M.CIRCUIT_FAIL_N * 2):
    col2._on_fail()
check("트립 3회 → CIRCUIT_BREAKER", col2.halt, "CIRCUIT_BREAKER")
col3 = M.Collector("dummy")
for _ in range(M.CIRCUIT_FAIL_N - 1):
    col3._on_fail()
col3._on_ok()
col3._on_fail()
check("성공이 연속실패 카운터를 리셋", col3.trips, 0)

print("\n[13] 거래일 스냅 / 빈 유니버스 가드 (pykrx 대역)")


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
    """휴장일이면 시총이 전부 0 — v1.2 결함 #2 의 실제 응답 형태."""
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
CAL_EMPTY = {}
M._mcap_frame = lambda d: _Frame([0] * 2903)
eff3, df3, trail3 = M.resolve_trading_day("2025-12-31")
check("전부 휴장이면 None (수집 진입 금지)", eff3, None)
check("역행 11일치 시도 기록", len(trail3), M.TRADING_DAY_LOOKBACK + 1)
M.pd, M._mcap_frame = _real_pd, _real_frame

print("\n[14] 계약/한계 기록")
check("계약 10개", len(M.CONTRACTS), 10)
check("임계 근거 문장 포함",
      any("경험적 근거 없이 설정된 임계값" in s for s in M.KNOWN_LIMITATIONS), True)
check("죽은 호출 이름 고정", M._DEAD_CALL_NAME, "get_index_portfolio_deposit_file")
check("측정대상 1000", M.MEASURE_N, 1000)
check("빈 유니버스 임계 100", M.EMPTY_UNIVERSE_MIN, 100)
check("워커 ≤ 4", M.N_WORKERS <= 4, True)
check("예산 중단 12000", M.CALL_BUDGET_STOP, 12000)
check("전이 3개", M.TRANSITIONS, [("S1", "S2"), ("S2", "S3"), ("S3", "S4")])

print("\n" + "=" * 70)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
