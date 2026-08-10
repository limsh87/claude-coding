#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""축 A-Δ v1.4 순수 로직 검증 — 네트워크·자격증명 없이 돌린다.

v1.4 에서 새로 생기거나 바뀐 것 위주로 검증한다:
  #1  3단 사다리의 게이트 조건과 실패 기록 (P0_MARKET_SOURCE_LADDER)
  #2  엔드포인트 출처 레지스트리 — 출처 없는 URL 은 등록조차 안 된다 (P0_NO_URL_GUESSING)
  #3  설치된 pykrx 소스 ast 판독 — 진짜 pykrx 와 합성 트리 양쪽
  #4  DART 예외 분류표 — requests 예외 계층(ProxyError ⊂ ConnectionError)의 순서 (§3.2)
  #5  서킷브레이커가 '재시도 소진 콜 연속 10건'에서만 발동 (v1.3 은 단발 31건으로 즉사)
  #6  호출 예산: 누적 12,000 중단 / 일일 19,500 (§4.3)
  #7  Plan C: se 필터·발행주식총수 필드 우선순위·자기주식 정책·순위상관
  #8  SSL 검증 비활성화 자기검사 (P0_NO_VERIFY_FALSE)
  #9  PIT 필터 경계 / 그래프 / 전이 born·died 분리 (v1.3 에서 검증된 로직의 회귀 고정)
  #10 pykrx import 크래시 방탄 — 진짜 import 문을 태워서 확인한다

    python phase0/verify_logic_v14.py
"""
import errno
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import datetime as _dt
from pathlib import Path

import pandas as pd

SRC = str(Path(__file__).with_name("axis_a_delta_v14.py"))
spec = importlib.util.spec_from_file_location("axd14", SRC)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
M.pd = pd

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


def raises(name, exc, fn, *a, **k):
    global N
    N += 1
    try:
        fn(*a, **k)
    except exc:
        print(f"  . {name}")
        return
    except Exception as e:
        FAIL.append(f"{name}: 잘못된 예외 {type(e).__name__}: {e}")
        print(f"  x {name}: 잘못된 예외 {type(e).__name__}")
        return
    FAIL.append(f"{name}: 예외가 발생하지 않았다")
    print(f"  x {name}: 예외 없음")


def _dirs(sub: str):
    """네트워크 없이 파일 계층만 쓰는 테스트용 디렉터리."""
    root = TMP / sub
    M.ROOT = root
    M.DIR_CACHE_RAW = root / "cache" / "raw" / "dart_exctv"
    M.DIR_CACHE_SHARES = root / "cache" / "raw" / "dart_shares"
    M.DIR_CACHE_PX = root / "cache" / "raw" / "px"
    M.DIR_CACHE_META = root / "cache" / "meta"
    M.DIR_STATE = root / "cache" / "state"
    M.DIR_REPORTS = root / "reports"
    M.DIR_CACHE_MARKET = root / "cache" / "market"
    for d in (M.DIR_CACHE_RAW, M.DIR_CACHE_SHARES, M.DIR_CACHE_PX, M.DIR_CACHE_META,
              M.DIR_STATE, M.DIR_REPORTS, M.DIR_CACHE_MARKET):
        d.mkdir(parents=True, exist_ok=True)
    return root


# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n[1] P0_LOCAL_ROOT_ONLY — /content 계열 차단")
raises("/content 거부", M.ContractViolation, M.resolve_project_root, "/content")
raises("/content/drive/MyDrive 거부", M.ContractViolation, M.resolve_project_root,
       "/content/drive/MyDrive/quant")
raises("/gdrive 거부", M.ContractViolation, M.resolve_project_root, "/gdrive/x")
check("로컬 경로 허용", type(M.resolve_project_root("~/quant/phase0")).__name__, "PosixPath")
check("/contentious 는 오탐 아님",
      str(M.resolve_project_root("/tmp/contentious")).endswith("contentious"), True)

print("\n[2] P0_PIT_STRICT_DELTA — as_of = 법정 제출기한 (FROZEN)")
M.verify_snapshot_spec()
print("  . FROZEN as_of 4건 == 법정기한 계산값")
for sid, _n, pe, _y, rc, as_of, _need in M.SNAPSHOT_SPEC:
    check(f"{sid} {pe}+{M._DEADLINE_DAYS[rc]}d", M._legal_deadline(pe, rc), as_of)
_orig = M.SNAPSHOT_SPEC
M.SNAPSHOT_SPEC = [("SX", "x", (_dt.date.today() - _dt.timedelta(days=45)).isoformat(),
                    "2026", "11013", _dt.date.today().isoformat(), 1)]
raises("as_of == 실행일이면 중단", M.ContractViolation, M.verify_snapshot_spec)
M.SNAPSHOT_SPEC = _orig
check("전이는 정확히 3개", M.TRANSITIONS, [("S1", "S2"), ("S2", "S3"), ("S3", "S4")])

print("\n[3] P0_NO_THRESHOLD_EDIT — 임계 frozen (v1.3 과 동일 해시)")
check("고정 해시 일치", M._sha256_thresholds(), M.GATE_THRESHOLDS_SHA256)
check("AΔ-1 임계", M.GATE_THRESHOLDS["AD1_born_ratio_mean"], 0.05)
check("AΔ-2 임계", M.GATE_THRESHOLDS["AD2_born_total_median"], 50)
_t = dict(M.GATE_THRESHOLDS)
M.GATE_THRESHOLDS = {**_t, "AD2_born_total_median": 10}      # 게이트 통과용 하향 시도
check("임계 변경 시 해시 불일치", M._sha256_thresholds() != M.GATE_THRESHOLDS_SHA256, True)
M.GATE_THRESHOLDS = _t

print("\n[4] P0_NO_URL_GUESSING — 출처 없는 URL 은 등록조차 되지 않는다")
raises("provenance 없으면 등록 거부", M.ContractViolation, M.register_endpoint,
       "x", "https://example.invalid/a", "")
raises("url 없으면 등록 거부", M.ContractViolation, M.register_endpoint, "x", "", "OFFICIAL_DOC")
raises("미등록 키 호출 거부", M.ContractViolation, M.endpoint, "krx_data_not_registered")
check("DART 엔드포인트 3종 사전 등록",
      sorted(k for k in M.ENDPOINT_REGISTRY if k.startswith("dart_")),
      ["dart_corpcode", "dart_exctv", "dart_stock_totqy"])
check("exctv URL", M.endpoint("dart_exctv"), "https://opendart.fss.or.kr/api/exctvSttus.json")
check("주식총수 URL", M.endpoint("dart_stock_totqy"),
      "https://opendart.fss.or.kr/api/stockTotqySttus.json")
M.register_endpoint("t_ok", "https://data.krx.co.kr/x", "LIBRARY_SOURCE", "auth.py:10")
check("출처가 있으면 등록된다", M.ENDPOINT_REGISTRY["t_ok"]["provenance"], "LIBRARY_SOURCE")

print("\n[5] P0_NO_VERIFY_FALSE — 자기 소스 검사")
check("배포 파일 자체는 통과", M.assert_no_verify_false().startswith("ENFORCED"), True)
_bad = TMP / "bad_module.py"
_bad.write_text("import requests\nrequests.get('https://x', verify=False)\n", encoding="utf-8")
_real_file = M.__file__
try:
    M.__file__ = str(_bad)
    raises("SSL 검증 끄는 코드가 있으면 예외", M.ContractViolation, M.assert_no_verify_false)
    _cmt = TMP / "comment_only.py"
    _cmt.write_text("# verify=False 는 금지다 (주석은 위반이 아니다)\nx = 1\n", encoding="utf-8")
    M.__file__ = str(_cmt)
    check("주석 안의 언급은 위반이 아니다", M.assert_no_verify_false().startswith("ENFORCED"), True)
    M.__file__ = str(TMP / "does_not_exist.py")
    check("소스를 못 읽으면 통과로 위장하지 않는다",
          M.assert_no_verify_false().startswith("UNCHECKABLE"), True)
finally:
    M.__file__ = _real_file

print("\n[6] §3.2 DART 예외 분류표 — requests 예외 계층 순서가 핵심")
import requests as _rq


def _cls(exc):
    return M.classify_dart_exception(exc)[0]


check("SSLError → SSL 인터셉트", _cls(_rq.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")),
      "사내망 SSL 인터셉트(중간자 인증서)")
check("ProxyError → 프록시 (ConnectionError 로 뭉개지지 않는다)",
      _cls(_rq.exceptions.ProxyError("no proxy")), "프록시 미설정 또는 프록시 설정 오류")
check("ReadTimeout → 타임아웃", _cls(_rq.exceptions.ReadTimeout("t")), "타임아웃 과소 또는 회선 지연")
check("ConnectTimeout → 타임아웃(연결거부로 오분류 금지)",
      _cls(_rq.exceptions.ConnectTimeout("t")), "타임아웃 과소 또는 회선 지연")
check("ConnectionError → 방화벽",
      _cls(_rq.exceptions.ConnectionError("refused")),
      "연결 거부/차단 — 방화벽이 막고 있을 가능성이 높다")
check("SSL 은 코드로 해결 가능",
      M.classify_dart_exception(_rq.exceptions.SSLError("x"))[2], True)
check("방화벽은 코드로 해결 불가",
      M.classify_dart_exception(_rq.exceptions.ConnectionError("x"))[2], False)
check("이름 기반 분류도 같은 결과 (dart_request 는 예외 객체를 넘기지 않는다)",
      M._classify_by_name("SSLError", "CERTIFICATE_VERIFY_FAILED")[0],
      "사내망 SSL 인터셉트(중간자 인증서)")
check("ConnectionError 안에 감싸인 인증서 단서도 잡는다",
      M._classify_by_name("ConnectionError",
                          "HTTPSConnectionPool: certificate verify failed")[0],
      "사내망 SSL 인터셉트(중간자 인증서)")
check("DNS 실패는 방화벽과 구분",
      M._classify_by_name("gaierror", "getaddrinfo failed")[0],
      "DNS 해석 실패 — opendart.fss.or.kr 을 못 찾는다")
check("미분류는 코드로 해결 불가로 본다(낙관 금지)",
      M._classify_by_name("WeirdError", "??")[2], False)

print("\n[7] rcept_no → 접수일자 (추정 금지)")
check("정상", M.rcept_dt_of("20250814000123"), "20250814")
check("짧으면 폐기", M.rcept_dt_of("2025"), "")
check("없으면 폐기", M.rcept_dt_of(None), "")
check("존재하지 않는 날짜는 폐기", M.rcept_dt_of("20250230000001"), "")
check("문자 섞여도 숫자만 추출", M.rcept_dt_of("A20250814X000123"), "20250814")

print("\n[8] PIT 필터 — 경계일 포함 / 룩어헤드 폐기 / 접수번호불량 분리")
recs = [{"rcept_no": "20250813000001", "nm": "a"},     # as_of 이전
        {"rcept_no": "20250814000001", "nm": "b"},     # as_of 당일 → 포함
        {"rcept_no": "20250815000001", "nm": "c"},     # as_of 다음날 → LOOKAHEAD
        {"rcept_no": "", "nm": "d"}]                   # BAD_RCEPT
kept, dropped = M.pit_filter(recs, "2025-08-14")
check("잔존 2건", len(kept), 2)
check("경계일 포함", sorted(r["nm"] for r in kept), ["a", "b"])
check("룩어헤드 1건", sum(1 for d in dropped if d["_drop_reason"] == "LOOKAHEAD"), 1)
check("접수번호불량 1건", sum(1 for d in dropped if d["_drop_reason"] == "BAD_RCEPT"), 1)
check("잔존 최종접수일 ≤ as_of", max(r["_rcept_dt"] for r in kept) <= "20250814", True)
check("원본 캐시는 필터되지 않는다(입력 불변)", recs[2]["nm"], "c")

print("\n[9] 인물키 · 출생년월 (보간 금지)")
check("괄호 병기 제거", M.norm_name("홍길동(洪吉童)"), "홍길동")
check("공백 제거", M.norm_name("홍 길동"), "홍길동")
check("출생년월 정규화", M.norm_birth_ym("1960년 03월"), "196003")
check("점 표기", M.norm_birth_ym("1960.3"), "196003")
check("복원 불가면 빈 값", M.norm_birth_ym("미상"), "")
check("13월은 거부", M.norm_birth_ym("1960.13"), "")
check("출생년월 없으면 인물키 없음(엣지 제외)", M.person_key("홍길동", ""), "")
check("정상 인물키", M.person_key("홍길동", "1960-03"), "홍길동|196003")

print("\n[10] 종목코드 정규화 — 2024 신형 영숫자 코드")
check("일반", M.to_code6("005930"), "005930")
check("정수", M.to_code6(5930), "005930")
check("접두 A", M.to_code6("A005930"), "005930")
check("야후 접미", M.to_code6("005930.KS"), "005930")
check("신형 09701K 보존", M.to_code6("09701K"), "09701K")
check("신형 소문자도 대문자화", M.to_code6("09701k"), "09701K")
check("불량은 빈 값", M.to_code6("XYZ"), "")
check("NaN 은 빈 값", M.to_code6(float("nan")), "")

print("\n[11] 그래프 — 출생년월 결측 제외, 측정대상 밖 상대 노드 유지")
c2c = {"C1": "000001", "C2": "000002", "C3": "000003"}
recs = [{"corp_code": "C1", "nm": "홍길동", "birth_ym": "1960년 03월"},
        {"corp_code": "C2", "nm": "홍길동", "birth_ym": "1960.03"},
        {"corp_code": "C3", "nm": "홍길동", "birth_ym": ""},          # 결측 → 제외
        {"corp_code": "C1", "nm": "김철수", "birth_ym": "1970년 01월"},
        {"corp_code": "C9", "nm": "김철수", "birth_ym": "1970년 01월"}]  # 매핑 없음
g = M.build_graph(recs, c2c)
check("엣지 1개(홍길동 C1-C2)", sorted(g["edges"]), [("000001", "000002")])
check("출생년월 결측 제외 1건", g["records_no_birth"], 1)
check("corp 매핑 불가 1건", g["records_unmapped_corp"], 1)
check("겸직 인물 1명", g["persons_multi"], 1)

print("\n[12] 전이 — born / died 분리 (절대 합산하지 않는다)")
prev = {"snapshot": "S1", "measure": {"A", "B", "C"}, "listed": {"A", "B", "C", "X"},
        "edges": {("A", "B"), ("B", "C")}}
nxt = {"snapshot": "S2", "measure": {"A", "B", "C"}, "listed": {"A", "B", "C", "X"},
       "edges": {("A", "B"), ("A", "C"), ("A", "X")}}
t = M.transition(prev, nxt)
check("edge_born 2 (A-C, A-X)", t["edge_born"], 2)
check("edge_died 1 (B-C)", t["edge_died"], 1)
check("합산값이 산출물에 없다", "edge_changed" in t, False)
check("교집합 3", t["intersect"], 3)
check("born 이 붙은 종목은 A,C 두 개 (B 는 0)", t["stocks_with_born"], 2)
check("X 는 measure 밖이어도 listed 라 both_listed 에 들어간다", t["born_both_listed"], 2)
prev2 = dict(prev, listed={"A", "B", "C"})
nxt2 = dict(nxt, listed={"A", "B", "C"})
check("상대가 미상장이면 both_listed 에서 빠진다",
      M.transition(prev2, nxt2)["born_both_listed"], 1)
check("측정대상 밖 상대 노드도 엣지로 센다(외부링크 유지)",
      M.transition({**prev, "measure": {"A"}}, {**nxt, "measure": {"A"}})["edge_born"], 2)

print("\n[13] Plan C — se 필터 · 발행주식총수 필드 우선순위 · 자기주식 정책")
check("보통주 인정", M._is_common_share_row("보통주"), True)
check("기명식보통주 인정", M._is_common_share_row("기명식 보통주"), True)
check("우선주 제외", M._is_common_share_row("우선주"), False)
check("합계 제외(우선주가 섞인다)", M._is_common_share_row("합계"), False)
check("'계' 제외", M._is_common_share_row("계"), False)
check("빈 값 제외", M._is_common_share_row(""), False)

payload = {"status": "000", "list": [
    {"corp_cls": "Y", "se": "보통주", "isu_stock_totqy": "5,000,000,000",
     "istc_totqy": "5,969,782,550", "tesstk_co": "20,000,000",
     "distb_stock_co": "5,949,782,550"},
    {"corp_cls": "Y", "se": "우선주", "istc_totqy": "822,886,700", "tesstk_co": "0"},
    {"corp_cls": "Y", "se": "합계", "istc_totqy": "6,792,669,250", "tesstk_co": "20,000,000"},
]}
p = M.parse_shares_payload(payload)
check("보통주만 합산", p["shares"], 5969782550)
check("1순위 필드는 istc_totqy(수권주식수 아님)", p["field_used"], "istc_totqy")
check("자기주식 별도 기록", p["treasury"], 20000000)
check("corp_cls 확보", p["corp_cls"], "Y")
check("자기주식 차감 정책 = 차감 안 함(KRX 정의와 일치)", M.PLANC_DEDUCT_TREASURY, False)
check("corp_cls Y→STK", M._norm_market("Y"), "STK")
check("corp_cls K→KSQ", M._norm_market("K"), "KSQ")
check("corp_cls N→KNX(코넥스 제외에 쓰인다)", M._norm_market("N"), "KNX")

p2 = M.parse_shares_payload({"status": "000", "list": [
    {"corp_cls": "K", "se": "보통주", "distb_stock_co": "1,000,000"}]})
check("istc_totqy 가 없을 때만 유통주식수로 폴백", p2["field_used"], "distb_stock_co")
p3 = M.parse_shares_payload({"status": "000", "list": [
    {"corp_cls": "K", "se": "우선주", "istc_totqy": "1,000"}]})
check("보통주 행이 없으면 결측(추정 금지)", p3["shares"], None)
p4 = M.parse_shares_payload({"status": "013", "list": []})
check("데이터 없음도 결측", p4["shares"], None)
p5 = M.parse_shares_payload({"status": "000", "list": [
    {"se": "보통주", "isu_stock_totqy": "9,999,999,999"}]})
check("수권주식수만 있으면 쓰지 않는다(치명적 오독 방지)", p5["shares"], None)

print("\n[14] 스피어만 순위상관 (scipy 없이)")
check("완전 일치 ≈ 1", round(M.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 6), 1.0)
check("완전 역순 ≈ -1", round(M.spearman([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]), 6), -1.0)
check("단조 비선형도 1 (피어슨과 다른 점)",
      round(M.spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]), 6), 1.0)
check("동점은 평균순위", round(M.spearman([1, 1, 2, 3], [1, 1, 2, 3]), 6), 1.0)
check("표본이 3 미만이면 None", M.spearman([1, 2], [1, 2]), None)
check("길이 불일치면 None", M.spearman([1, 2, 3], [1, 2]), None)
check("전부 동값이면 None(0 으로 위장 금지)", M.spearman([1, 1, 1], [1, 2, 3]), None)
check("교차검증 임계는 0.95", M.PLANC_XVAL_MIN_SPEARMAN, 0.95)

print("\n[15] 설치된 pykrx 소스 ast 판독 (P0_NO_URL_GUESSING 의 실체)")
_fake = TMP / "fakepkg"
for sub in ("website/comm", "website/krx/market"):
    (_fake / "pykrx" / sub).mkdir(parents=True, exist_ok=True)
(_fake / "pykrx" / "website" / "comm" / "auth.py").write_text('''
LOGIN_PAGE = "https://example.test/page.cmd"
LOGIN_URL = "https://example.test/login.cmd"
USER_AGENT = "Mozilla/5.0 (test)"


def warmup_krx_session(session):
    session.get(LOGIN_PAGE, timeout=15)


def login_krx(login_id, login_pw, session=None):
    warmup_krx_session(session)
    payload = {"blank": "", "uid": login_id, "upw": login_pw}
    resp = session.post(LOGIN_URL, data=payload, timeout=15)
    data = resp.json()
    error_code = data.get("_err", "")
    if error_code == "DUP99":
        payload["skipDup"] = "Y"
        resp = session.post(LOGIN_URL, data=payload, timeout=15)
        error_code = resp.json().get("_err", "")
    return error_code == "OKZZ"
''', encoding="utf-8")
(_fake / "pykrx" / "website" / "comm" / "webio.py").write_text('''
class Post:
    def __init__(self, headers=None):
        self.headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://example.test/ref"}
''', encoding="utf-8")
(_fake / "pykrx" / "website" / "krx" / "krxio.py").write_text('''
class KrxWebIo:
    @property
    def url(self):
        return "https://example.test/getJsonData.cmd"
''', encoding="utf-8")
(_fake / "pykrx" / "website" / "krx" / "market" / "core.py").write_text('''
class 전종목시세:
    @property
    def bld(self):
        return "dbms/TEST/BLD01"

    def fetch(self, theDate, theMarket):
        result = self.read(theMarket=theMarket, theDate=theDate)
        return DataFrame(result["Block_9"])
''', encoding="utf-8")
(_fake / "pykrx" / "website" / "krx" / "market" / "wrap.py").write_text('''
def get_market_cap_by_ticker(date, market="KOSPI"):
    market2mktid = {"ALL": "ALLX", "KOSPI": "STK"}
    return market2mktid[market]
''', encoding="utf-8")

_real_pkgdir = M._pykrx_pkg_dir
M._pykrx_pkg_dir = lambda: _fake / "pykrx"
d = M.discover_pykrx_endpoints()
check("로그인 URL 을 소스에서 읽는다", d.get("login_url"), "https://example.test/login.cmd")
check("ID 키를 인자 대조로 찾는다", d.get("login_id_key"), "uid")
check("PW 키를 인자 대조로 찾는다", d.get("login_pw_key"), "upw")
check("payload 키 전체", d.get("login_payload_keys"), ["blank", "uid", "upw"])
check("오류코드 키", d.get("error_code_key"), "_err")
check("성공코드", d.get("login_success_code"), "OKZZ")
check("중복로그인 파라미터", d.get("dup_login_param"), ("skipDup", "Y"))
check("중복로그인 트리거 코드까지 읽는다", d.get("dup_login_trigger"), "DUP99")
check("워밍업 URL", d.get("warmup_urls"), ["https://example.test/page.cmd"])
check("조회 URL", d.get("data_url"), "https://example.test/getJsonData.cmd")
check("bld", d.get("bld_all_quotes"), "dbms/TEST/BLD01")
check("날짜 파라미터 이름(fetch 인자 순서로 판정)", d.get("param_date"), "theDate")
check("시장 파라미터 이름", d.get("param_market"), "theMarket")
check("응답 키", d.get("result_key"), "Block_9")
check("전체시장 코드값", d.get("market_all_value"), "ALLX")
check("기본 헤더", d.get("data_headers", {}).get("Referer"), "https://example.test/ref")
check("미확인 항목 없음", d.get("missing"), [])
truthy("출처에 파일:줄번호가 남는다", ":" in d["provenance"]["login_url"])

M._pykrx_pkg_dir = lambda: TMP / "no_such_pkg"
d2 = M.discover_pykrx_endpoints()
truthy("소스가 없으면 추측하지 않고 missing 으로 남긴다", len(d2["missing"]) > 0)
check("소스가 없으면 login_url 을 만들어내지 않는다", d2.get("login_url"), None)
M._pykrx_pkg_dir = _real_pkgdir

if importlib.util.find_spec("pykrx") is not None:
    real = M.discover_pykrx_endpoints()
    check("진짜 pykrx: 로그인 URL 이 data.krx.co.kr",
          str(real.get("login_url", "")).startswith("https://data.krx.co.kr/"), True)
    check("진짜 pykrx: 성공코드 CD001", real.get("login_success_code"), "CD001")
    check("진짜 pykrx: ID 키 mbrId", real.get("login_id_key"), "mbrId")
    check("진짜 pykrx: 조회 bld", real.get("bld_all_quotes"),
          "dbms/MDC/STAT/standard/MDCSTAT01501")
    check("진짜 pykrx: 응답 키 OutBlock_1", real.get("result_key"), "OutBlock_1")
    check("진짜 pykrx: 미확인 항목 없음", real.get("missing"), [])
else:
    print("  ~ pykrx 미설치 — 실물 판독 검증 생략 (합성 트리 검증은 위에서 통과)")

print("\n[16] pykrx import 크래시 방탄 — 진짜 import 문을 태워서 확인한다")
_crash = TMP / "crashpkg"
(_crash / "pykrx").mkdir(parents=True, exist_ok=True)
(_crash / "pykrx" / "__init__.py").write_text(
    'import json\n'
    'raise json.JSONDecodeError("Expecting value", "line 13 column 1 (char 25)", 0)\n',
    encoding="utf-8")
sys.path.insert(0, str(_crash))
try:
    M.KRX_ID, M.KRX_PW = "someid", "somepw"
    mod, err, out = M._try_import_pykrx(with_creds=True)
    check("import 크래시를 예외로 흘리지 않는다", mod, None)
    truthy("예외 전문을 남긴다(조용히 삼키지 않는다)", "JSONDecodeError" in err)
    M.PYKRX_AVAILABLE, M.PYKRX_DIAGNOSTIC = False, ""
    got = M.import_pykrx_guarded()
    check("두 경로 모두 실패해도 프로세스가 죽지 않는다", got, None)
    check("PYKRX_AVAILABLE=False 로 남는다", M.PYKRX_AVAILABLE, False)
    truthy("자격증명/무자격 두 시도 모두 기록", len(M.PYKRX_IMPORT_LOG["attempts"]) >= 2)
    truthy("진단에 두 경로가 다 들어간다",
           "자격증명포함" in M.PYKRX_DIAGNOSTIC and "무자격" in M.PYKRX_DIAGNOSTIC)
    check("죽은 pykrx 로는 어떤 호출도 예외를 내지 않는다",
          M.pykrx_call("get_market_cap_by_ticker", "20250630", market="ALL"), None)
    check("sys.modules 에 반쪽 pykrx 가 남지 않는다",
          [m for m in sys.modules if m == "pykrx" or m.startswith("pykrx.")], [])
finally:
    sys.path.remove(str(_crash))
    M._purge_pykrx_modules()
    M.KRX_ID = M.KRX_PW = ""

print("\n[17] 자격증명 env 주입은 import 보다 먼저 (v1.3 KRX_ENV_TOO_LATE)")
M.KRX_ID, M.KRX_PW = "abc", "def"
M.inject_krx_env()
check("env 주입 표시", M.PYKRX_IMPORT_LOG["env_injected_before_import"], True)
check("KRX_ID 가 환경에 들어간다", os.environ.get("KRX_ID"), "abc")
sys.modules["pykrx"] = type(sys)("pykrx")     # 누가 먼저 import 해 둔 상황을 재현
M.inject_krx_env()
check("이미 로드된 pykrx 를 감지한다", M.PYKRX_IMPORT_LOG["env_too_late"], True)
check("걷어낸 모듈 수를 센다", M.PYKRX_IMPORT_LOG["purged_stale_modules"] >= 1, True)
check("sys.modules 에서 실제로 제거된다", "pykrx" in sys.modules, False)
M.KRX_ID = M.KRX_PW = ""
M.inject_krx_env()
check("자격증명이 비면 환경변수도 지운다 — 로그인 경로를 아예 타지 않는다",
      os.environ.get("KRX_ID"), None)

print("\n[18] NO_KNOWN_DEAD_CALL — 쓰지 않는 게 아니라 부르면 터진다")


class _FakeStock:
    @staticmethod
    def get_index_portfolio_deposit_file(*a, **k):
        return ["something"]


_fs = _FakeStock()
check("가드 장착", M._arm_dead_call_guard(_fs), True)
raises("호출하면 계약위반", M.ContractViolation, _fs.get_index_portfolio_deposit_file, "1028")
check("없는 모듈에는 조용히 미장착", M._arm_dead_call_guard(None), False)

print("\n[19] 서킷브레이커 — '재시도 소진 콜 연속 10건'에서만 (v1.3 은 단발 31건으로 즉사)")
_dirs("circuit")
col = M.Collector("k" * 40)
check("규칙 상수", (M.CIRCUIT_FAIL_N, M.MAX_RETRY_PER_CALL, M.BACKOFF_SECONDS),
      (10, 3, (2, 4, 8)))
for _ in range(9):
    col._on_call_exhausted()
check("9건으로는 발동 안 함", col.trips, 0)
col._on_call_exhausted()
check("10건째에 1회 발동", col.trips, 1)
check("발동 후 카운터 리셋", col.consec_exhausted, 0)
for _ in range(5):
    col._on_call_exhausted()
col._on_call_ok()                       # 성공 1건이 연속을 끊는다
check("성공 1건이 연속을 끊는다", col.consec_exhausted, 0)
for _ in range(10):
    col._on_call_exhausted()
check("두 번째 발동", col.trips, 2)
for _ in range(10):
    col._on_call_exhausted()
check("3회째에 halt", col.halt, "CIRCUIT_BREAKER")

print("\n[20] 호출 예산 — 누적 12,000 중단 / 일일 19,500 (§4.3)")
check("중단 임계", M.CALL_BUDGET_STOP_CUMULATIVE, 12000)
check("일일 한도", M.CALL_BUDGET_DAILY, 19500)
_dirs("budget")
col2 = M.Collector("k" * 40)
col2.calls_today = M.CALL_BUDGET_STOP_CUMULATIVE - 2
check("임계 직전에는 예약된다", col2._reserve(), True)
check("임계 도달 직전 한 건 더", col2._reserve(), True)
check("임계에 닿으면 거부", col2._reserve(), False)
check("halt 사유 기록", col2.halt, "BUDGET_STOP_CUMULATIVE")
col3 = M.Collector("k" * 40)
col3.calls_today = M.CALL_BUDGET_DAILY
check("일일한도에서도 거부", col3._reserve(), False)
check("일일한도 사유", col3.halt, "BUDGET_STOP_DAILY")
col4 = M.Collector("k" * 40)
col4.calls_today = 5
col4.persist_budget()
col5 = M.Collector("k" * 40)
check("같은 날 이전 실행분을 이어받는다", col5.calls_today, 5)

print("\n[21] KRX 계열 직렬화 — 단일 스레드 + 요청 간 1초 이상 (§8)")
gate = M.SerialGate(0.25)
_seen = []


def _hit(i):
    with gate:
        _seen.append((i, time.time()))


ths = [threading.Thread(target=_hit, args=(i,)) for i in range(4)]
t0 = time.time()
for x in ths:
    x.start()
for x in ths:
    x.join()
el = time.time() - t0
check("4회 호출이 직렬화되어 최소 간격을 지킨다", el >= 0.25 * 2, True)
check("동시 진입이 없다(락으로 강제)", gate.calls, 4)
check("실운영 간격은 1초", M.KRX_GATE.min_interval, 1.0)

print("\n[22] 스냅샷 표 — pandas 라벨 재색인 함정 (v1.3 에서 캐시가 항상 비어 보이던 버그)")
_dirs("snap")
snap = M._mk_snapshot([f"{i:06d}" for i in range(1, 301)],
                      [float(i) * 1e8 for i in range(1, 301)],
                      ["STK"] * 150 + ["KSQ"] * 140 + ["KNX"] * 10)
check("스냅샷 300종목", len(snap), 300)
check("KONEX 라벨 정규화", int((snap["mkt"] == "KNX").sum()), 10)
p = M.DIR_CACHE_MARKET / "krx_market_20250630.csv"
M._snap_write_csv(snap, p)
back = M._snap_read_csv(p)
check("왕복 후에도 종목 수 보존", len(back), 300)
check("왕복 후 시총이 NaN 으로 무너지지 않는다", int(back["cap"].isna().sum()), 0)
check("왕복 후 값 일치", float(back.loc["000005", "cap"]), 5e8)
check("유효행이 100 미만이면 None(빈 유니버스 가드)",
      M._mk_snapshot(["000001"], [1e8], ["STK"]), None)
check("시총 0 은 제외된다",
      len(M._mk_snapshot([f"{i:06d}" for i in range(1, 301)],
                         [0.0] * 100 + [1e8] * 200, ["STK"] * 300)), 200)

print("\n[23] PriceStore — 캐시 커버리지 판정과 as-of 종가 (보간 금지)")
_dirs("px")
M._check_parquet()
ps = M.PriceStore([2025, 2026], "2025-01-01", "2026-08-10")
ps.set_keep_window(["2025-06-30"], 20)
check("커버리지 없으면 받아야 한다", ps._covered("000001", ["2025-06-30"]), False)
ps._write_year("000001", 2025, {"2025-06-26": 1000.0, "2025-06-27": 1100.0})
ps._write_year("000001", 2026, {})
check("메타의 fetch_range 안이면 커버된 것으로 본다",
      ps._covered("000001", ["2025-06-30"]), True)
check("체결이 없는 해도 '확정된 사실'로 커버 인정",
      ps._covered("000001", ["2026-03-31"]), True)
c, used, back = ps.close_asof("000001", "2025-06-27")
check("당일 종가", (c, used, back), (1100.0, "2025-06-27", 0))
c, used, back = ps.close_asof("000001", "2025-06-30")
check("휴장/미체결이면 직전 종가와 경과일을 함께 돌려준다", (c, used, back),
      (1100.0, "2025-06-27", 3))
ps.mem.clear()
c, used, back = ps.close_asof("000001", "2025-07-31")
check("허용 기간을 넘으면 결측(추정 금지)", c, None)
check("허용 기간 상수", M.PLANC_PRICE_STALE_MAX_DAYS, 10)
ps.mem.clear()
check("거래일 판정은 '그 날 실제 체결'로 한다",
      ps.trading_day_count(["000001"], "2025-06-27"), 1)
check("체결이 없는 날은 0", ps.trading_day_count(["000001"], "2025-06-30"), 0)

# 종가를 못 받은 종목의 유한 음성 캐시 — 상장폐지 종목 수백 건을 매 실행 다시 두들기지
# 않으면서, 일시적 장애가 영원한 결측으로 굳지도 않게 한다.
check("표시가 없으면 재시도 대상", ps._nodata_fresh("000009"), False)
ps._mark_nodata("000009", "빈 응답")
check("방금 표시했으면 재시도 생략", ps._nodata_fresh("000009"), True)
M.write_json(ps._nodata_path("000009"),
             {"at": (_dt.datetime.now() - _dt.timedelta(days=M.PX_NODATA_TTL_DAYS + 1))
              .isoformat(timespec="seconds"), "note": "old"})
check("유효기간이 지나면 다시 시도한다(영구 결측 금지)", ps._nodata_fresh("000009"), False)
check("유효기간 상수", M.PX_NODATA_TTL_DAYS, 3)
M.write_json(ps._nodata_path("000009"), {"at": "깨진값"})
check("표시 파일이 깨져 있으면 재시도 대상으로 본다", ps._nodata_fresh("000009"), False)

ps._mark_nodata("000009", "빈 응답")           # 다시 신선한 표시로 되돌린 뒤
_got, _fail = ps.ensure(["000001", "000009"], ["2025-06-30"], "테스트")
check("커버된 종목과 음성표시 종목은 둘 다 수신 대상에서 빠진다", (_got, _fail), (0, 0))

print("\n[24] 사다리 기록 — 실패해도 사유가 반드시 남는다 (§2.4)")
M.LADDER_DIAG["plans"] = []
r = M._plan_record("Z", "테스트 플랜")
M._step(r, "1단계", False, "네트워크 차단")
r["reason"] = "카나리 0종목"
check("플랜 기록이 남는다", len(M.LADDER_DIAG["plans"]), 1)
check("단계별 성패가 남는다", M.LADDER_DIAG["plans"][0]["steps"][0]["ok"], False)
check("사유 원문이 남는다", M.LADDER_DIAG["plans"][0]["reason"], "카나리 0종목")
check("카나리 날짜는 명령서 지정값", M.CANARY_DATE, "2025-06-30")
check("카나리 성공 기준 100종목", M.CANARY_MIN_ROWS, 100)
check("초기 상태에서는 선택된 소스가 없다", M.MARKET_SOURCE["plan"], "")
M.LADDER_DIAG["plans"] = []

print("\n[25] 계약 목록 — v1.4 §6 과 일치")
_expect = {"P0_MARKET_SOURCE_LADDER", "P0_NO_URL_GUESSING", "P0_DART_PREFLIGHT",
           "P0_NO_VERIFY_FALSE", "P0_LOCAL_ROOT_ONLY", "P0_PIT_STRICT_DELTA",
           "P0_EMPTY_UNIVERSE_GUARD", "P0_CACHE_FIRST", "P0_NO_STRATEGY",
           "P0_GRAPH_FULL_MEASURE_SUB", "P0_FAIL_LOUD", "P0_NO_THRESHOLD_EDIT",
           "P0_LIVE_ONLY", "NO_KNOWN_DEAD_CALL"}
check("계약 14건이 정확히 일치", set(M.CONTRACTS), _expect)
check("워커 2 (§3.3)", M.N_WORKERS, 2)
check("타임아웃 30초", M.HTTP_TIMEOUT, 30)
check("측정 대상 1,000종목", M.MEASURE_N, 1000)
check("빈 유니버스 가드 100", M.EMPTY_UNIVERSE_MIN, 100)
check("대량수집 게이트 5,000", M.LARGE_COLLECTION_GATE, 5000)
check("KONEX 기본 제외", M.INCLUDE_KONEX, False)
truthy("합성 데이터 경로가 소스에 없다 (P0_LIVE_ONLY)",
       "synthetic" not in Path(SRC).read_text(encoding="utf-8").lower())

print("\n[26] 안전한 파일 IO — ENOSPC 즉시 실패 / 동시쓰기 / Windows 락 재시도")
_dirs("io")
_w = M.DIR_CACHE_META
M.write_json(_w / "a.json", {"k": "값"})
check("json 왕복", M.read_json(_w / "a.json"), {"k": "값"})
check("깨진 파일은 None", M.read_json(_w / "nope.json"), None)
_real_replace = os.replace


def _enospc(a, b):
    e = OSError(errno.ENOSPC, "No space left")
    e.errno = errno.ENOSPC
    raise e


os.replace = _enospc
try:
    raises("ENOSPC 는 재시도 없이 즉시 DiskFull", M.DiskFull, M.write_bytes, _w / "full.json", b"z")
finally:
    os.replace = _real_replace

_calls = {"n": 0}


def _locked_twice(a, b):
    _calls["n"] += 1
    if _calls["n"] <= 2:
        raise PermissionError(13, "locked")
    return _real_replace(a, b)


os.replace = _locked_twice
try:
    M.write_bytes(_w / "retry.json", b'{"ok":1}')
    check("Windows 일시적 락은 짧게 되짚어 기다린다", M.read_json(_w / "retry.json"), {"ok": 1})
finally:
    os.replace = _real_replace

_errs = []


def _concurrent(i):
    try:
        for _ in range(10):
            M.write_bytes(_w / "shared.json", b'{"w":%d}' % i)
    except BaseException as e:                                # noqa: BLE001
        _errs.append(f"{type(e).__name__}: {e}")


ths = [threading.Thread(target=_concurrent, args=(i,)) for i in range(5)]
for x in ths:
    x.start()
for x in ths:
    x.join()
check("같은 경로 동시 쓰기 5스레드 — 서로의 tmp 를 지워 터지지 않는다", _errs, [])
check("동시 쓰기 후에도 온전한 JSON", M.read_json(_w / "shared.json")["w"] in range(5), True)

print("\n[27] 캐시 인벤토리 스캔 — 파일명만 읽는다")
_dirs("inv")
for cp, yy, rc in [("00126380", "2025", "11012"), ("00126380", "2025", "11014"),
                   ("00164779", "2025", "11012")]:
    M.write_json(M.cache_path(cp, yy, rc), {"status": "000", "list": []})
inv = M.scan_blob_inventory(M.DIR_CACHE_RAW)
check("(2025,11012) 2건", len(inv[("2025", "11012")]), 2)
check("(2025,11014) 1건", len(inv[("2025", "11014")]), 1)
check("없는 조합은 0건", len(inv[("2026", "11013")]), 0)
check("주식총수 캐시는 별도 경로", str(M.shares_path("X", "2025", "11012")).find("dart_shares") > 0,
      True)
check("종가 캐시 경로 형식(명령서 §2.3-3)",
      str(M.px_path("005930", 2025)).endswith("px/005930/2025.parquet")
      or str(M.px_path("005930", 2025)).endswith("px/005930/2025.csv"), True)

print("\n" + "=" * 78)
if FAIL:
    print(f"실패 {len(FAIL)}/{N}")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"전체 통과 {N}/{N}")
