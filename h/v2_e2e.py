"""END-TO-END: real ingest path build_security_master() + Universe.at()
   with a delisting fixture in FDR/KRX MDCSTAT23801 schema."""
import sys, io, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-claude-coding/8a6c52fc-3c9c-54eb-b7c5-72a1e1d8c86c/scratchpad/h")
import v0_boot, fx
m, g, _ = v0_boot.load(); g["VERBOSE"] = True; g["DART_API_KEY"] = ""

# ── ① 살아있는 상장사 (FDR GitHub 캐시 listing/krx) ────────────────────────────
LIVE = [                      # Code,Name,Market,Sector,Industry,ListingDate,...
  ["005930","삼성전자",  "KOSPI","전자","반도체","1975-06-11","12","","",""],
  ["008465","한독우선주","KOSPI","의약","제약",  "1976-05-11","12","","",""],
  ["000846","현대건설우","KOSPI","건설","건설",  "1984-02-04","12","","",""],
  ["352820","하이브",    "KOSPI","엔터","엔터",  "2020-10-15","12","","",""],
]
# ── ② 상장폐지 피드 (SECUGRP_NM=신주인수권증권 행 포함) ────────────────────────
DEAD = [
  ["111111","진짜폐지사","KOSDAQ","주권","보통주","2011-06-01","2019-04-01",
   "감사의견거절","","","서비스",500,1000,"",""],
  # 7자 단축코드형 워런트 : 008465W → to_code6 → '008465'
  ["008465W","한독 3WR","KOSPI","신주인수권증권","신주인수권증권",
   "2014-03-10","2016-03-09","권리행사기간만료","","","",0,0,"",""],
  # 6자 알파벳 말미형 워런트 : 00846W → to_code6 → '000846'
  ["00846W","현대건설 2WR","KOSPI","신주인수권증서","신주인수권증서",
   "2015-05-10","2017-06-09","권리행사기간만료","","","",0,0,"",""],
  # 알파벳 선두형 : J35282 → to_code6 → '035282'  (충돌 없음 = 유령행)
  ["J35282","기타증권","KOSPI","수익증권","수익증권",
   "2013-01-10","2018-02-09","신탁계약기간만료","","","",0,0,"",""],
]
KIND = [["삼성전자",5930,"전자","폰","1975-06-11","12월","","",""],
        ["한독우선주",8465,"의약","약","1976-05-11","12월","","",""],
        ["현대건설우",846,"건설","건","1984-02-04","12월","","",""],
        ["하이브",352820,"엔터","음","2020-10-15","12월","","",""]]

L, D, K = fx.listing_csv(LIVE), fx.delisting_csv(DEAD), fx.kind_html(KIND)
def fake_http_get(url, **kw):
    if "listing/delisting" in url: return D
    if "listing/krx" in url:       return L
    if "kind.krx.co.kr" in url:    return K
    return None
g["http_get"] = fake_http_get
g["fetch_naver_names"] = lambda codes, limit=400: {}

snaps = pd.DataFrame(columns=["snap_date","code","market"])
sec = g["build_security_master"](snaps)
print("\n=== SECURITY MASTER ===")
print(sec[["code","name","listing_date","delisting_date","src"]].to_string(index=False))

px = pd.DataFrame({"date": pd.bdate_range("2010-01-04","2025-12-31"), "code":"005930"})
U = g["Universe"](sec, snaps, px)
print("\n=== UNIVERSE.at ===")
for t in ["2015-12-31","2016-12-31","2018-12-31","2021-12-31","2025-06-30"]:
    print(" ", t, U.at(t))
