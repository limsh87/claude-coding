#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KRX bld / Open API 응답 파싱 시험 — 네트워크 없이 mock 으로 필드 매핑을 고정한다.

응답 스키마는 설치된 pykrx 1.2.x 소스의 docstring 예시에서 그대로 가져왔다.
이 시험이 깨지면 사용자 환경에서 시총·지수구성·수급이 조용히 전멸한다.
"""
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "shinhan_7f_earnings_surprise_v1.py")
src = open(SRC, encoding="utf-8").read()
src = src.replace('if __name__ == "__main__" or ENV["ipython"]:', 'if False:')
src = src.replace('RUN_MODE = "FULL"', 'RUN_MODE = "CACHED"')
m = types.ModuleType("k"); sys.modules["k"] = m
exec(compile(src, SRC, "exec"), m.__dict__)
M = m.__dict__; pd = M["pd"]; np = M["np"]
F = []
def ck(n, c, d=""):
    print(("  [OK]   " if c else "  [FAIL] ") + n + (f"  — {d}" if d else ""))
    if not c: F.append(n)

# ── 전종목시세 MDCSTAT01501 → OutBlock_1 ────────────────────────────────────────────────────
QUOTE = {"OutBlock_1": [
    {"ISU_SRT_CD": "060310", "ISU_ABBRV": "3S", "MKT_NM": "KOSDAQ", "SECT_TP_NM": "중견기업부",
     "TDD_CLSPRC": "2,365", "FLUC_TP_CD": "2", "CMPPREVDD_PRC": "-5", "FLUC_RT": "-0.21",
     "TDD_OPNPRC": "2,370", "TDD_HGPRC": "2,395", "TDD_LWPRC": "2,355",
     "ACC_TRDVOL": "152,157", "ACC_TRDVAL": "361,210,535",
     "MKTCAP": "105,886,118,195", "LIST_SHRS": "44,772,143", "MKT_ID": "KSQ"},
    {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKT_NM": "KOSPI", "SECT_TP_NM": "",
     "TDD_CLSPRC": "89,400", "FLUC_TP_CD": "1", "CMPPREVDD_PRC": "2,600", "FLUC_RT": "3.00",
     "TDD_OPNPRC": "88,700", "TDD_HGPRC": "90,000", "TDD_LWPRC": "88,700",
     "ACC_TRDVOL": "26,393,970", "ACC_TRDVAL": "2,356,661,622,700",
     "MKTCAP": "533,698,559,970,000", "LIST_SHRS": "5,969,782,550", "MKT_ID": "STK"},
    {"ISU_SRT_CD": "000045", "ISU_ABBRV": "우선주", "MKT_NM": "KOSPI", "SECT_TP_NM": "",
     "TDD_CLSPRC": "-", "TDD_OPNPRC": "-", "TDD_HGPRC": "-", "TDD_LWPRC": "-",
     "ACC_TRDVOL": "0", "ACC_TRDVAL": "0", "MKTCAP": "-", "LIST_SHRS": "1,000",
     "MKT_ID": "STK"}]}
M["KRX"].session_ok = True
M["KRX"].json_data = lambda bld, **kw: QUOTE if "01501" in bld else None
q = M["krx_all_quotes"]("20210125")
ck("전종목시세 파싱 성공", q is not None and len(q) == 3, str(None if q is None else len(q)))
if q is not None:
    r = q.set_index("code")
    ck("종목코드 6자리", "005930" in r.index)
    ck("시총 콤마 제거 파싱", float(r.at["005930", "marcap"]) == 533698559970000.0,
       str(r.at["005930", "marcap"]))
    ck("상장주식수 파싱", float(r.at["005930", "shares"]) == 5969782550.0)
    ck("종가 파싱", float(r.at["005930", "close"]) == 89400.0)
    ck("거래대금 파싱", float(r.at["005930", "amount"]) == 2356661622700.0)
    ck("시장 구분 대문자", str(r.at["005930", "market"]) == "KOSPI")
    ck("'-' 는 NaN (거래정지 우선주)", not (float(r.at["000045", "marcap"]) ==
                                          float(r.at["000045", "marcap"])))

# ── 지수구성종목 MDCSTAT00601 → output ──────────────────────────────────────────────────────
PDF = {"output": [{"ISU_SRT_CD": f"{i:06d}", "ISU_ABBRV": f"N{i}", "TDD_CLSPRC": "1,000",
                   "MKTCAP": "1,000,000"} for i in range(1, 201)]}
M["KRX"].json_data = lambda bld, **kw: PDF if "00601" in bld else None
mem = M["krx_index_members"]("20210125")
ck("지수구성 200종목 파싱", mem is not None and len(mem) == 200,
   str(None if mem is None else len(mem)))
ck("지수구성 코드 정규화", mem is not None and mem[0] == "000001")
SHORT = {"output": PDF["output"][:100]}          # 150 미만이면 채택하지 않아야 한다
M["KRX"].json_data = lambda bld, **kw: SHORT if "00601" in bld else None
ck("150종목 미만은 거부(소급복사·반쪽응답 방어)", M["krx_index_members"]("20210125") is None)

# ── 투자자별 순매수 MDCSTAT02401 → output ───────────────────────────────────────────────────
FLOW = {"output": [
    {"ISU_SRT_CD": "006400", "ISU_NM": "삼성SDI", "ASK_TRDVOL": "1,298,644",
     "BID_TRDVOL": "1,636,929", "NETBID_TRDVOL": "338,285",
     "ASK_TRDVAL": "899,322,500,000", "BID_TRDVAL": "1,125,880,139,000",
     "NETBID_TRDVAL": "226,557,639,000"},
    {"ISU_SRT_CD": "051910", "ISU_NM": "LG화학", "NETBID_TRDVOL": "239,570",
     "NETBID_TRDVAL": "-204,942,176,000"}]}
M["KRX"].json_data = lambda bld, **kw: FLOW if "02401" in bld else None
fl = M["krx_net_purchases"]("20210115", "20210122", "7050", mkt_id="STK")
ck("순매수 파싱 성공", fl is not None and len(fl) == 2, str(None if fl is None else len(fl)))
if fl is not None:
    r = fl.set_index("code")
    ck("순매수대금(NETBID_TRDVAL) 사용", float(r.at["006400", "net_buy"]) == 226557639000.0)
    ck("음수 순매수 파싱", float(r.at["051910", "net_buy"]) == -204942176000.0)
ck("투자자 코드 매핑(기관합계 7050 / 외국인 9000)",
   M["KRX_INVESTOR"] == {"inst_net": "7050", "forg_net": "9000"}, str(M["KRX_INVESTOR"]))

# ── Open API: 오류도 HTTP 200 으로 온다 ─────────────────────────────────────────────────────
M["KRX_OPENAPI_KEY"] = "dummy"
calls = {"n": 0}
API_OK = {"OutBlock_1": [
    {"ISU_SRT_CD": "005930", "MKTCAP": "533698559970000", "LIST_SHRS": "5969782550",
     "TDD_CLSPRC": "89400"}]}
API_ERR = {"respMsg": "Unauthorized Key", "respCode": "401"}
def fake_json(url, source="generic", **kw):
    calls["n"] += 1
    return API_ERR if calls["n"] == 1 else API_OK
M["http_json"] = fake_json
ck("Open API 오류(respCode=401)를 데이터로 오인하지 않는다",
   (lambda r: r is not None and len(r) == 1)(M["krx_openapi_quotes"]("20210125")),
   "첫 엔드포인트는 401 → 버리고 두 번째만 채택")
M["http_json"] = lambda url, source="generic", **kw: API_ERR
ck("전 엔드포인트 오류면 None", M["krx_openapi_quotes"]("20210125") is None)
M["http_json"] = lambda url, source="generic", **kw: {"OutBlock_1": []}
ck("빈 응답을 '휴장'으로 추론하지 않고 실패 처리",
   M["krx_openapi_quotes"]("20210125") is None)

# ── marcap 이 전혀 없는 환경에서 krx_bld 만으로 40분기 스파인이 만들어지는지 ──────────────
#    사용자 실환경 재현: pykrx 인증 불가 + marcap 파일 없음 + KRX 마켓플레이스 로그인만 성공.
#    v1.0 은 이 조건에서 40개 분기 전부 시총 결손 → 유니버스 붕괴 → 36분 후 RuntimeError.
print("\n=== 실환경 재현: marcap 없음 + pykrx 불가 + KRX 로그인만 성공 ===")
import tempfile as _tf, shutil as _sh
_root = _tf.mkdtemp(prefix="sh7f_bld_")
for _ns in ("_shared", "shinhan_7f"):
    os.makedirs(os.path.join(_root, _ns, "table"), exist_ok=True)
    os.makedirs(os.path.join(_root, _ns, "index"), exist_ok=True)
M["GDRIVE_ROOT_CANDIDATES"] = [_root]
M["READ_ROOTS"] = [_root]
M["VAULT"] = M["Vault"](_root, "LOCAL")
M["VAULT"].load_index("shared")
M["VAULT"].load_index("private")
M["MARCAP"] = M["MarcapStore"]()          # 파일이 없는 새 스토어
M["pykrx_stock"] = None                    # pykrx 사용 불가
M["KRX_OPENAPI_KEY"] = ""                  # Open API 키도 없음
_BIG = {"OutBlock_1": [
    {"ISU_SRT_CD": f"{i * 10:06d}", "TDD_CLSPRC": f"{1000 + i}", "MKTCAP": f"{(3000 - i) * 10**9}",
     "LIST_SHRS": "1000000", "MKT_NM": "KOSPI" if i < 1500 else "KOSDAQ",
     "ACC_TRDVAL": "1000000"} for i in range(1, 2501)]}
M["KRX"].session_ok = True
M["KRX"].json_data = lambda bld, **kw: _BIG if "01501" in bld else None
_days = pd.bdate_range("2016-01-04", "2026-08-31")
_sig = []
for _y in range(2016, 2027):
    for _mm in (3, 6, 9, 12):
        _in = _days[(_days.year == _y) & (_days.month == _mm)]
        if len(_in) and pd.Timestamp("2016-08-01") <= _in.max() <= pd.Timestamp("2026-07-31"):
            _sig.append(_in.max())
M["RUN_MODE"] = "FULL"       # 네트워크 경로를 켠다 (실제 호출은 위 mock 이 가로챈다)
_sp = M["MarketcapSpine"]()
_panel = _sp.build(_sig, pxc=None)
ck("★marcap·pykrx 없이 KRX bld 만으로 전 분기 시총 확보",
   len(_sp.per_date) == len(_sig), f"{len(_sp.per_date)}/{len(_sig)}시점")
ck("등급이 PIT_EXACT (근사 아님)",
   len(_panel) and set(_panel["grade"]) == {"PIT_EXACT"})
ck("확보 소스가 krx_bld", _sp.n_by_src.get("krx_bld", 0) == len(_sig))
_sec = pd.DataFrame({"code": [f"{i * 10:06d}" for i in range(1, 2501)],
                     "name": [f"N{i}" for i in range(1, 2501)],
                     "market": ["KOSPI"] * 1499 + ["KOSDAQ"] * 1001,
                     "listing_date": pd.Timestamp("2010-01-04"), "delisting_date": pd.NaT})
_sch = M["rebalance_schedule"](np.array(_days, dtype="datetime64[ns]"),
                              "2016-08-01", "2026-07-31", quiet=True)
_k, _cm, _meta = M["build_universes"](_sch, _panel, _sec)
ck("★유니버스 결손 0분기", len(_meta["missing"]) == 0, str(_meta["missing"][:4]))
ck("K200 이 분기마다 200종목", len(_k) and
   int(_k.groupby("signal_date")["code"].size().min()) == 200,
   str(int(_k.groupby("signal_date")["code"].size().min()) if len(_k) else 0))
ck("비교 유니버스가 분기마다 1000종목", len(_cm) and
   int(_cm.groupby("signal_date")["code"].size().min()) == 1000)
ck("신규 시총 단면이 공용 캐시에 적재됨(다음 실행은 네트워크 0회)",
   os.path.exists(os.path.join(_root, "_shared", "table",
                               "krx_market_cap_monthly.parquet")))
_sp2 = M["MarketcapSpine"]()   # RUN_MODE 는 여전히 FULL
M["KRX"].json_data = lambda bld, **kw: None       # 이제 네트워크가 완전히 죽었다고 가정
_panel2 = _sp2.build(_sig, pxc=None)
ck("★두 번째 실행은 캐시만으로 전 분기 확보(네트워크 불통에도)",
   _sp2.n_by_src.get("cache", 0) == len(_sig), str(dict(_sp2.n_by_src)))
M["RUN_MODE"] = "CACHED"
_sh.rmtree(_root, ignore_errors=True)

print("\n" + "=" * 70)
print(f"실패 {len(F)}건: {F}" if F else "KRX 응답 파싱 시험 전체 통과")
sys.exit(1 if F else 0)
