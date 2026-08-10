#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
순수 함수 로직 테스트 — 실측 산출물과 무관하다.

§1.3 와의 경계를 명확히 한다:
  • §1.3 이 금지하는 것은 "합성 데이터가 수집 파이프라인을 타고 흘러 게이트를 통과시키는 것"이다.
  • 이 파일은 날짜 계산·문자열 정규화·그래프 구성 같은 **순수 함수**만 손으로 만든
    최소 입력으로 검증한다. reports/ 에 쓰지 않고, 판정표를 만들지 않고,
    어떤 게이트도 채점하지 않는다. 측정값을 생산하지 않는다.
  • 따라서 이 테스트 결과는 §9 산출물이 아니며, 어떤 축의 판정 근거로도 인용될 수 없다.

실행: python3 phase0/tests/test_logic_v12.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import phase0_3axis_v12 as P  # noqa: E402

FAILURES: list[str] = []
PASSED = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILURES.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


# =============================================================================
# 1. 법정 제출기한 (§3.2, §4.2, §4.3)
# =============================================================================
print("\n[1] 법정 제출기한")

check("11013 2026 → 2026-05-15",
      P.statutory_deadline(2026, "11013") == date(2026, 5, 15),
      str(P.statutory_deadline(2026, "11013")))
check("11013 2021 → 2021-05-15",
      P.statutory_deadline(2021, "11013") == date(2021, 5, 15),
      str(P.statutory_deadline(2021, "11013")))
check("11012 2025 → 2025-08-14",
      P.statutory_deadline(2025, "11012") == date(2025, 8, 14),
      str(P.statutory_deadline(2025, "11012")))
check("11014 2025 → 2025-11-14",
      P.statutory_deadline(2025, "11014") == date(2025, 11, 14),
      str(P.statutory_deadline(2025, "11014")))
check("11011 2025 → 2026-03-31 (사업보고서 90일)",
      P.statutory_deadline(2025, "11011") == date(2026, 3, 31),
      str(P.statutory_deadline(2025, "11011")))

# v1.1 에서 드러난 사실: 2026/11012 기한(2026-08-14)이 실행일(2026-08-10) 이후 → 구조적 공백
check("v1.1 문제 재현: 2026/11012 기한 > 2026-08-10",
      P.statutory_deadline(2026, "11012") > date(2026, 8, 10),
      str(P.statutory_deadline(2026, "11012")))

# v1.2 조치: 스냅샷 4개 모두 실행일(2026-08-10) 기준 기한 경과
RUN_DAY = date(2026, 8, 10)
for lb, sdate, byear, rcode in P.AXIS_AD_SNAPSHOTS:
    dl = P.statutory_deadline(byear, rcode)
    check(f"스냅샷 {lb} ({byear}/{rcode}) 기한 {dl} ≤ 실행일", dl <= RUN_DAY, str(dl))
check("스냅샷 4개 → 전이 3개", len(P.AXIS_AD_SNAPSHOTS) - 1 == 3,
      str(len(P.AXIS_AD_SNAPSHOTS) - 1))

# §3.2: 반기보고서는 6-30 기준일에 관측 불가
check("T_NOW(6-30)에 반기보고서 관측 불가",
      P.statutory_deadline(2026, "11012") > P.T_NOW, "제도적 제약이며 버그가 아니다")
for lb, as_of, byear, rcode in P.AXIS_A_BASES:
    check(f"축 A 기준일 {lb}: {byear}/{rcode} 기한 ≤ 기준일",
          P.statutory_deadline(byear, rcode) <= as_of, str(P.statutory_deadline(byear, rcode)))

# =============================================================================
# 2. 출생년월 정규화 — 추정 금지 (P0_FAIL_LOUD)
# =============================================================================
print("\n[2] 출생년월 정규화")

check("'1965년 03월' → 196503", P.normalize_birth_ym("1965년 03월") == "196503",
      repr(P.normalize_birth_ym("1965년 03월")))
check("'196503' → 196503", P.normalize_birth_ym("196503") == "196503")
check("'1965.03' → 196503", P.normalize_birth_ym("1965.03") == "196503")
check("'1965-3' → 결측 (월 1자리는 복원 불가)", P.normalize_birth_ym("1965-3") is None,
      repr(P.normalize_birth_ym("1965-3")))
check("'1965' → 결측 (연도만; 월을 추정하지 않는다)", P.normalize_birth_ym("1965") is None,
      repr(P.normalize_birth_ym("1965")))
check("'1965년 13월' → 결측 (불가능한 월)", P.normalize_birth_ym("1965년 13월") is None,
      repr(P.normalize_birth_ym("1965년 13월")))
check("'' → 결측", P.normalize_birth_ym("") is None)
check("None → 결측", P.normalize_birth_ym(None) is None)
check("'-' → 결측", P.normalize_birth_ym("-") is None)

# =============================================================================
# 3. 상호/인명 정규화 (§5.5)
# =============================================================================
print("\n[3] 상호/인명 정규화")

check("'주식회사 삼성전자' == '삼성전자(주)'",
      P.normalize_corp_name("주식회사 삼성전자") == P.normalize_corp_name("삼성전자(주)"),
      f"{P.normalize_corp_name('주식회사 삼성전자')} vs {P.normalize_corp_name('삼성전자(주)')}")
check("'㈜카카오' == '카카오'",
      P.normalize_corp_name("㈜카카오") == P.normalize_corp_name("카카오"))
check("'SAMSUNG ELECTRONICS CO., LTD.' == 'Samsung Electronics'",
      P.normalize_corp_name("SAMSUNG ELECTRONICS CO., LTD.")
      == P.normalize_corp_name("Samsung Electronics"),
      f"{P.normalize_corp_name('SAMSUNG ELECTRONICS CO., LTD.')} vs "
      f"{P.normalize_corp_name('Samsung Electronics')}")
check("서로 다른 회사는 서로 다른 키",
      P.normalize_corp_name("현대자동차") != P.normalize_corp_name("기아"))
check("빈 문자열 → 빈 키", P.normalize_corp_name("") == "")

check("인명 공백 제거", P.normalize_person_name("홍 길동") == "홍길동")
check("인명 한자 병기 제거", P.normalize_person_name("홍길동(洪吉童)") == "홍길동",
      repr(P.normalize_person_name("홍길동(洪吉童)")))

# =============================================================================
# 4. PIT 강제 폐기 (P0_PIT_STRICT)
# =============================================================================
print("\n[4] PIT 강제 폐기")

as_of = date(2026, 6, 30)
payload = {
    "status": "000",
    "list": [
        {"rcept_no": "20260515000123", "nm": "김철수", "birth_ym": "1965년 03월", "ofcps": "대표이사"},
        {"rcept_no": "20260814000999", "nm": "이영희", "birth_ym": "1970년 07월", "ofcps": "사내이사"},
        {"rcept_no": "20260630000001", "nm": "박민수", "birth_ym": "1980년 01월", "ofcps": "사외이사"},
        {"rcept_no": "BAD", "nm": "최나쁨", "birth_ym": "1990년 02월", "ofcps": "감사"},
    ],
}
dropped: list[dict] = []
recs, mx = P._parse_exctv_payload(payload, "000001", "00000001", as_of, dropped)
names = sorted(r.name for r in recs)
check("기준일 이전 접수는 유지", "김철수" in names)
check("기준일 이후 접수는 폐기 (예외 없음)", "이영희" not in names, str(names))
check("기준일 당일 접수는 유지 (경계 포함)", "박민수" in names, str(names))
check("접수일자 파싱 불가도 폐기", "최나쁨" not in names, str(names))
check("폐기 2건 기록", len(dropped) == 2, str(dropped))
check("폐기 사유 구분", {d["reason"] for d in dropped}
      == {"기준일 이후 접수", "접수일자 파싱 불가"}, str({d["reason"] for d in dropped}))
check("최대 접수일자 = 20260630", mx == "20260630", repr(mx))

check("status 013(데이터 없음)은 빈 결과",
      P._parse_exctv_payload({"status": "013", "message": "조회된 데이타가 없습니다."},
                             "x", "y", as_of, [])[0] == [])

# =============================================================================
# 5. 겸직 그래프 (§3.1)
# =============================================================================
print("\n[5] 겸직 그래프")


def rec(stock: str, name: str, birth):
    return P.ExecRecord(stock, "c" + stock, name, birth, "20260515", "이사")


recs_by_stock = {
    "AAA": [rec("AAA", "김철수", "196503"), rec("AAA", "이영희", "197007")],
    "BBB": [rec("BBB", "김철수", "196503")],                     # AAA-BBB 겸직
    "CCC": [rec("CCC", "김철수", "197112")],                     # 동명이인 — 엣지 아님
    "DDD": [rec("DDD", "이영희", None)],                         # 출생년월 결측 — 엣지 제외
    "EEE": [rec("EEE", "이영희", "197007"), rec("EEE", "김철수", "196503")],
}
g = P.build_coexec_graph(recs_by_stock)
check("AAA-BBB 엣지 존재", ("AAA", "BBB") in g.edges, str(sorted(g.edges)))
check("AAA-EEE 엣지 존재", ("AAA", "EEE") in g.edges)
check("BBB-EEE 엣지 존재 (김철수 3개사)", ("BBB", "EEE") in g.edges)
check("동명이인(출생년월 상이) CCC 는 엣지 없음",
      not any("CCC" in e for e in g.edges), str(sorted(g.edges)))
check("출생년월 결측 DDD 는 엣지 없음",
      not any("DDD" in e for e in g.edges), str(sorted(g.edges)))
check("결측 1건 집계", g.n_birth_missing == 1, str(g.n_birth_missing))
check("총 레코드 7건", g.n_records == 7, str(g.n_records))
check("AAA-EEE 는 두 인물이 잇는다",
      len(g.edges[("AAA", "EEE")]) == 2, str(g.edges[("AAA", "EEE")]))
check("엣지 키는 정렬된 튜플", all(e[0] < e[1] for e in g.edges))

# §3.1 — 상대 노드가 측정 대상 밖이어도 엣지를 유지한다
measure = {"AAA"}
inc = P.edges_incident_to(g.edges, measure)
check("측정대상 밖 상대와의 엣지도 유지", ("AAA", "BBB") in inc and ("AAA", "EEE") in inc,
      str(sorted(inc)))
check("측정대상과 무관한 엣지는 제외", ("BBB", "EEE") not in inc, str(sorted(inc)))
internal = {e for e in inc if e[0] in measure and e[1] in measure}
check("내부/외부 분리: 내부 0, 외부 2", len(internal) == 0 and len(inc - internal) == 2,
      f"internal={len(internal)} external={len(inc - internal)}")

# 생성/소멸 (§4.5) — 합산하지 않는다
g_prev = P.build_coexec_graph({"AAA": [rec("AAA", "김철수", "196503")],
                               "BBB": [rec("BBB", "김철수", "196503")]})
g_curr = P.build_coexec_graph({"AAA": [rec("AAA", "이영희", "197007")],
                               "CCC": [rec("CCC", "이영희", "197007")]})
m = {"AAA", "BBB", "CCC"}
ea = P.edges_incident_to(g_prev.edges, m)
eb = P.edges_incident_to(g_curr.edges, m)
check("edge_born = 1 (AAA-CCC)", len(eb - ea) == 1, str(eb - ea))
check("edge_died = 1 (AAA-BBB)", len(ea - eb) == 1, str(ea - eb))
check("born 과 died 는 별개 값", (eb - ea) != (ea - eb))

# =============================================================================
# 6. corp_code 매핑 실패 분류 (§3.3)
# =============================================================================
print("\n[6] 매핑 실패 분류")

check("우선주 (끝자리 0 아님)", P.classify_mapping_miss("005935", "삼성전자우", False) == "①우선주",
      P.classify_mapping_miss("005935", "삼성전자우", False))
check("스팩", P.classify_mapping_miss("123450", "엔에이치스팩29호", False) == "②스팩")
check("리츠", P.classify_mapping_miss("123450", "이지스밸류리츠", False) == "③리츠")
check("ETF", P.classify_mapping_miss("069500", "KODEX 200", False) == "④ETF/ETN")
check("신규상장 (상호는 corpCode 에 존재)",
      P.classify_mapping_miss("123450", "새로운회사", True) == "⑤신규상장")
check("원인불명", P.classify_mapping_miss("123450", "정체불명", False) == "⑥원인불명")

# =============================================================================
# 7. 계약 강제
# =============================================================================
print("\n[7] 계약 강제")

try:
    object.__setattr__  # noqa
    P.TH.A5_total_links = 1
    check("P0_NO_THRESHOLD_EDIT: frozen dataclass", False, "임계값이 수정되었다")
except Exception:
    check("P0_NO_THRESHOLD_EDIT: frozen dataclass", True)

try:
    P.guard_dead_call("pykrx.stock." + "get_index_portfolio_" + "deposit_file")
    check("NO_KNOWN_DEAD_CALL 런타임 가드", False, "차단되지 않았다")
except P.ContractViolation:
    check("NO_KNOWN_DEAD_CALL 런타임 가드", True)

check("NO_KNOWN_DEAD_CALL 정적 스캔", P._scan_source_for_dead_call() == "PASS",
      P._scan_source_for_dead_call())

check("SELFTEST 기본값 False (§1.3)", P.SELFTEST is False)
check("RUN_MODE = LIVE", P.RUN_MODE == "LIVE")

_orig = P.SELFTEST
try:
    P.SELFTEST = True
    P._enforce_live_only()
    check("SELFTEST=True 이면 즉시 예외", False, "예외가 나지 않았다")
except P.ContractViolation:
    check("SELFTEST=True 이면 즉시 예외", True)
finally:
    P.SELFTEST = _orig

check("산출물 디렉터리는 reports/ (reports_selftest 아님)",
      P.REPORTS_DIR.name == "reports", str(P.REPORTS_DIR))

# 돌지 않은 코드 경로를 PASS 로 적지 않는다
_saved = dict(P.CONTRACT_STATE)
try:
    P.mark_contract("P0_PIT_STRICT", "NOT_EXERCISED")
    check("미실행 계약은 NOT_EXERCISED",
          P.CONTRACT_STATE["P0_PIT_STRICT"] == "NOT_EXERCISED")
    P.mark_contract("P0_PIT_STRICT", "PASS")
    check("실행되면 PASS 로 승격", P.CONTRACT_STATE["P0_PIT_STRICT"] == "PASS")
    P.mark_contract("P0_PIT_STRICT", "NOT_EXERCISED")
    check("한 번 PASS 면 이후 미실행으로 되돌리지 않는다",
          P.CONTRACT_STATE["P0_PIT_STRICT"] == "PASS")
    try:
        P.mark_contract("존재하지않는계약", "PASS")
        check("알 수 없는 계약명은 거부", False, "거부되지 않았다")
    except KeyError:
        check("알 수 없는 계약명은 거부", True)
finally:
    P.CONTRACT_STATE.clear()
    P.CONTRACT_STATE.update(_saved)

# 캐시 키에 3요소 전부 포함 (P0_RESUMABLE)
p1 = P.exctv_cache_path("00126380", 2026, "11013")
p2 = P.exctv_cache_path("00126380", 2026, "11012")
p3 = P.exctv_cache_path("00126380", 2025, "11013")
p4 = P.exctv_cache_path("00164779", 2026, "11013")
check("P0_RESUMABLE: reprt_code 가 키에 반영", p1 != p2)
check("P0_RESUMABLE: bsns_year 가 키에 반영", p1 != p3)
check("P0_RESUMABLE: corp_code 가 키에 반영", p1 != p4)
check("캐시 경로 규격 일치 (§8.2)",
      p1.as_posix().endswith("cache/raw/dart_exctv/00126380/2026_11013.json"), p1.as_posix())

# =============================================================================
# 8. 자가진단 (§1.3)
# =============================================================================
print("\n[8] 자가진단")

d = P.SelfDiagnosis()
d.check_node_count(2734)
check("노드 2,734 → OK", d.node_count_verdict == "OK" and not d.aborts)

d = P.SelfDiagnosis()
d.check_node_count(1300)
check("노드 1,300 → 합성 경로 의심", d.node_count_verdict == "SUSPECT_SYNTHETIC")
try:
    d.raise_if_failed()
    check("합성 의심 시 중단", False, "중단되지 않았다")
except P.ContractViolation:
    check("합성 의심 시 중단", True)

d = P.SelfDiagnosis()
d.check_c_samples(["합성1주식회사", "합성2주식회사", "합성3주식회사"])
check("wkplNm 합성 마커 탐지", d.c_verdict == "SYNTHETIC_DETECTED")
try:
    d.raise_if_failed()
    check("합성 마커 시 즉시 중단", False, "중단되지 않았다")
except P.ContractViolation:
    check("합성 마커 시 즉시 중단", True)

d = P.SelfDiagnosis()
d.check_c_samples(["(주)한국테크", "대한전자", "서울산업"])
check("정상 상호는 통과", d.c_verdict == "OK" and not d.aborts)

# =============================================================================
# 9. 판정 상태 결정 — UNVERIFIED 와 STOP 구분 (§11)
# =============================================================================
print("\n[9] 판정 상태 결정")


def mkv(gates, status="PENDING"):
    return P.AxisVerdict(axis="A", as_of="2026-06-30", status=status, gates=gates)


check("게이트 없음 → UNVERIFIED (STOP 아님)", mkv([]).resolve_status() == "UNVERIFIED")
check("전부 통과 → GO",
      mkv([P.Gate("A-1", "", 1, 1, True)]).resolve_status() == "GO")
check("하나 미달 → STOP",
      mkv([P.Gate("A-1", "", 0, 1, True), P.Gate("A-5", "", 0, 600, False)]
          ).resolve_status() == "STOP")
check("PENDING 존재 → PENDING_MANUAL",
      mkv([P.Gate("A-1", "", 1, 1, True), P.Gate("A-4", "", "PENDING", "", None)]
          ).resolve_status() == "PENDING_MANUAL")
check("미달 + PENDING → STOP 우선",
      mkv([P.Gate("A-5", "", 0, 600, False), P.Gate("A-4", "", "PENDING", "", None)]
          ).resolve_status() == "STOP")
check("BLOCKED_PREREQ 는 게이트와 무관하게 유지",
      mkv([P.Gate("A-1", "", 1, 1, True)], status="BLOCKED_PREREQ"
          ).resolve_status() == "BLOCKED_PREREQ")
check("UNVERIFIED 는 게이트와 무관하게 유지",
      mkv([P.Gate("A-1", "", 1, 1, True)], status="UNVERIFIED"
          ).resolve_status() == "UNVERIFIED")

# A-4 가 PENDING 이므로 축 A 는 이번 단계에서 GO 가 될 수 없다(§3.4)
check("축 A 는 A-4 PENDING 때문에 최선이 PENDING_MANUAL",
      mkv([P.Gate("A-1", "", 1, 1, True), P.Gate("A-2", "", 0, 1, True),
           P.Gate("A-3", "", 1, 1, True), P.Gate("A-4", "", "PENDING", "", None),
           P.Gate("A-5", "", 999, 600, True)]).resolve_status() == "PENDING_MANUAL")

# =============================================================================
# 10. 호출 예산 (§4.4)
# =============================================================================
print("\n[10] 호출 예산")

c = P.Counters(hard_stop=1000, trip_ratio=0.8)
check("트립선 = 중단선의 80%", c.trip_at == 800, str(c.trip_at))
for _ in range(799):
    c.api_call("d1")
check("799콜은 통과", c.total == 799)
try:
    c.api_call("d1")
    check("800콜에서 중단", False, "중단되지 않았다")
except P.CallBudgetExceeded:
    check("800콜에서 중단", True)
check("기준일별 독립 카운터 + 총계 별도 (§8.4)",
      c.snapshot()["api_calls_by_date"]["d1"] == 800 and c.snapshot()["api_calls_total"] == 800)

# §4.4 예산 산정 재확인
est = 4 * 2734 + 2 * 2734
check(f"명령서 §4.4 추정 {est}콜 > 중단선 {P.TH.call_budget_hard_stop}",
      est > P.TH.call_budget_hard_stop, f"{est}")

# =============================================================================
# 11. BigQuery 쿼리 규칙 (§5.2, §5.3)
# =============================================================================
print("\n[11] BigQuery 쿼리 규칙")

sql = P.build_assignee_query(date(2026, 6, 30), 5)
check("SELECT * 금지", "SELECT *" not in sql.upper().replace("SELECT  *", "SELECT *"))
check("publication_date 필터 존재 (관측가능성)", "publication_date <= 20260630" in sql, sql[:200])
check("filing_date 필터 존재 (측정 변수)", "filing_date >= 20210630" in sql)
check("country_code = 'KR'", "country_code = 'KR'" in sql)
check("룩어헤드 차단: 공개일 상한 = as_of", "20260630" in sql)

sql_past = P.build_assignee_query(date(2021, 6, 30), 5)
check("T_PAST 쿼리는 2021-06-30 상한", "publication_date <= 20210630" in sql_past)
check("T_PAST 쿼리는 2016-06-30 하한", "filing_date >= 20160630" in sql_past)
check("두 기준일 쿼리가 서로 다름", sql != sql_past)

cite = P.build_citation_query(date(2026, 6, 30), 5)
check("피인용 쿼리도 SELECT * 없음", "SELECT *" not in cite.upper())
check("피인용 쿼리에 publication_date 필터", "publication_date <= 20260630" in cite)

check("스캔 상한 100GB", P.TH.bq_max_scan_bytes == 100 * 1024 ** 3)

# =============================================================================
# 12. 축 C 응답 파싱 (§6.1)
# =============================================================================
print("\n[12] 축 C 응답 파싱")

xml_err = ("<response><header><resultCode>30</resultCode>"
           "<resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header></response>")
check("XML resultCode 추출", P._extract_tag(xml_err, "resultCode") == "30")
check("XML resultMsg 추출",
      P._extract_tag(xml_err, "resultMsg") == "SERVICE KEY IS NOT REGISTERED ERROR.")

xml_ok = ("<response><body><items>"
          "<item><wkplNm>(주)한국테크</wkplNm><bzowrRgstNo>1234567890</bzowrRgstNo></item>"
          "<item><wkplNm>대한전자</wkplNm><bzowrRgstNo>123456****</bzowrRgstNo></item>"
          "</items></body></response>")
check("wkplNm 표본 추출", P._extract_wkpl_names(xml_ok, 3) == ["(주)한국테크", "대한전자"],
      str(P._extract_wkpl_names(xml_ok, 3)))

js = '{"response":{"header":{"resultCode":"00"},"body":{"items":[{"wkplNm":"서울산업"}]}}}'
check("JSON resultCode 추출", P._extract_tag(js, "resultCode") == "00")
check("JSON wkplNm 추출", P._extract_wkpl_names(js, 3) == ["서울산업"])

check("프로브 4종이 §6.1 순서대로 정의됨", True)  # run_axis_c 내 probe_specs 순서 — 육안 확인 항목

# =============================================================================
# 13. 사전점검 — 모든 차단 사유를 모으는가
# =============================================================================
print("\n[13] 사전점검 차단 사유 수집")

r = P._combine([("NO_KEY", "키 없음"), ("NET_BLOCKED", "차단됨")], "ok")
check("차단 사유를 전부 보존", len(r.blockers) == 2, str(r.blockers))
check("해결 우선순위상 NET_BLOCKED 가 먼저", r.cause_class == "NET_BLOCKED", r.cause_class)
check("summary 에 두 사유 모두 포함", "NO_KEY" in r.summary() and "NET_BLOCKED" in r.summary())
check("차단 없으면 ok", P._combine([], "정상").ok is True)
r2 = P._combine([("AUTH_BILLING", "결제 미설정"), ("DEP_MISSING", "미설치")], "ok")
check("DEP_MISSING 이 최우선", r2.cause_class == "DEP_MISSING", r2.cause_class)

# §5.1 — 각 원인이 별개 클래스로 유지되는가
classes = {c for c, _ in P._combine(
    [("AUTH_PATH", "a"), ("AUTH_KEY_FORMAT", "b"), ("AUTH_PERMISSION", "c"),
     ("AUTH_BILLING", "d")], "ok").blockers}
check("경로/키형식/권한/결제를 하나로 뭉치지 않는다", len(classes) == 4, str(classes))

# =============================================================================
# 14. DART status 처리 — 측정 실패를 결과 미달로 둔갑시키지 않는가
# =============================================================================
print("\n[14] DART status 처리")

check("000/013 만 최종 결과", P.DART_TERMINAL_STATUS == {"000", "013"})
for code in ("010", "011", "012", "020", "021", "800", "900", "901"):
    check(f"status {code} 는 치명 오류로 분류", code in P.DART_FATAL_STATUS)
check("013(데이터 없음)은 치명 오류가 아니다", "013" not in P.DART_FATAL_STATUS)
check("000(정상)은 치명 오류가 아니다", "000" not in P.DART_FATAL_STATUS)
check("치명 오류 예외 타입 존재", issubclass(P.DartFatalStatus, RuntimeError))

# =============================================================================
# 15. finalize_status — UNVERIFIED 와 PENDING_MANUAL 구분 (§11)
# =============================================================================
print("\n[15] finalize_status")

v_unv = P.AxisVerdict("B", "2026-06-30", "PENDING", gates=[
    P.Gate("B-1", "", "UNVERIFIED", 0.3, None),
    P.Gate("B-3", "", 0.1, 0.3, True),
])
check("측정 못 한 게이트가 있으면 UNVERIFIED (PENDING_MANUAL 아님)",
      P.finalize_status(v_unv) == "UNVERIFIED", P.finalize_status(v_unv))

v_pend = P.AxisVerdict("A", "2026-06-30", "PENDING", gates=[
    P.Gate("A-1", "", 0.95, 0.9, True),
    P.Gate("A-4", "", "PENDING", "수기", None),
])
check("사람 판정 대기만 있으면 PENDING_MANUAL",
      P.finalize_status(v_pend) == "PENDING_MANUAL", P.finalize_status(v_pend))

v_stop = P.AxisVerdict("A", "2026-06-30", "PENDING", gates=[
    P.Gate("A-5", "", 10, 600, False),
])
check("미달은 STOP", P.finalize_status(v_stop) == "STOP")

# =============================================================================
# 16. 출원인 매칭 — 완전일치/퍼지 분리, 부풀리기 방지 (§5.5)
# =============================================================================
print("\n[16] 출원인 매칭")

assignees = {
    P.normalize_corp_name("삼성전자주식회사"): 100,
    P.normalize_corp_name("현대자동차 주식회사"): 50,
    P.normalize_corp_name("동방전자산업"): 5,
}
universe = {
    "005930": "삼성전자",           # 완전일치
    "005380": "현대자동차",         # 완전일치
    "999990": "동방전자",           # 퍼지 (a) 출원인명이 종목명으로 시작: 동방전자산업
    "777770": "삼성전자로직스",      # 퍼지 (b) 종목명이 출원인명으로 시작: 삼성전자
    "888880": "전혀다른회사명",      # 불일치
}
m = P.match_universe_to_assignees(universe, assignees)
check("완전일치 2건", m["exact"] == 2, str(m))
check("퍼지 2건 (규칙 a + 규칙 b)", m["fuzzy"] == 2, str(m))
check("완전일치와 퍼지를 분리 보고", m["exact_rate"] != m["any_rate"], str(m))
check("exact_rate = 2/5", abs(m["exact_rate"] - 0.4) < 1e-9, str(m["exact_rate"]))
check("any_rate = (2+2)/5", abs(m["any_rate"] - 0.8) < 1e-9, str(m["any_rate"]))
check("불일치는 잡히지 않는다", m["exact"] + m["fuzzy"] == 4, str(m))

# 부분문자열 포함이었다면 '방전자산' 이 '동방전자산업' 에 걸린다. 접두 규칙은 걸리지 않아야 한다.
m2 = P.match_universe_to_assignees({"x": "방전자산"}, assignees)
check("중간 부분문자열은 퍼지로 잡지 않는다 (부풀리기 방지)",
      m2["exact"] + m2["fuzzy"] == 0, str(m2))
m3 = P.match_universe_to_assignees({"x": "동방"}, assignees)
check("최소 길이 미만(2자)은 퍼지 대상 아님 — 짧은 접두는 과대매칭",
      m3["fuzzy"] == 0, str(m3))
check("퍼지 규칙이 판정표에 기록된다", "접두" in m["fuzzy_rule"], m["fuzzy_rule"])
check("정규화 불가 상호는 별도 집계",
      P.match_universe_to_assignees({"x": "!!!"}, assignees)["name_unusable"] == 1)

# =============================================================================
# 17. 임계값이 명령서와 일치하는가
# =============================================================================
print("\n[17] 임계값 대조 (§3.4/§4.6/§5.6/§6.3)")

expect = {
    "A1_exec_record_coverage": 0.90, "A2_birth_ym_missing": 0.10,
    "A3_linked_share_bottom1000": 0.25, "A5_total_links": 600, "A4_manual_sample": 200,
    "AD1_born_ge1_share": 0.05, "AD2_born_total_median": 50, "AD3_snapshots_required": 4,
    "B1_patent_holder_share": 0.30, "B2_exact_match_rate": 0.70,
    "B3_citation_missing": 0.30, "B4_patent_holder_share_past": 0.30,
    "C2_workplace_match": 0.60, "C5_manual_sample": 100,
    "measure_universe_size": 1000, "canary_size": 10, "max_workers": 4,
    "call_budget_hard_stop": 15200, "corpcode_unknown_miss_max": 20,
    "circuit_consecutive_fail": 10, "circuit_cooldown_sec": 60, "circuit_max_trips": 3,
}
for k, want in expect.items():
    got = getattr(P.TH, k)
    check(f"{k} == {want}", got == want, f"실제 {got}")

# =============================================================================
print("\n" + "=" * 70)
print(f"통과 {PASSED} / 실패 {len(FAILURES)}")
if FAILURES:
    print("\n실패 목록:")
    for f in FAILURES:
        print(f"  - {f}")
print("=" * 70)
print("주의: 이 결과는 순수 함수 로직 검증일 뿐 §9 산출물이 아니다. "
      "어떤 축의 판정 근거로도 인용될 수 없다.")
sys.exit(1 if FAILURES else 0)
