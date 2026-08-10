"""Apply the candidate patch at SOURCE level and re-run unit + e2e + contract."""
import sys, types, os, tempfile, pandas as pd
sys.path.insert(0,"/tmp/claude-0/-home-user-claude-coding/8a6c52fc-3c9c-54eb-b7c5-72a1e1d8c86c/scratchpad/h")
import fx
FILE="/home/user/claude-coding/strategies/tcd_v2_00_integrated_all_packs.py"
OLD = '''    if _TICKER_RE.match(s):
        return s
    d = re.sub(r"\\D", "", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
        return cand if _TICKER_RE.match(cand) else None
    return None'''
NEW = '''    if _TICKER_RE.match(s):
        return s
    if s.isdigit() and len(s) < 6:
        cand = s.zfill(6)
        return cand if _TICKER_RE.match(cand) else None
    return None'''
os.environ["TCD_NO_PIP"]="1"
src=open(FILE,encoding="utf-8").read(); src=src[:src.index("def offer_download")]
src=src.replace("def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
                "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n    return True,'skip'")
assert src.count(OLD)==1, f"anchor count={src.count(OLD)}"
src=src.replace(OLD,NEW)
m=types.ModuleType("tcd"); sys.modules["tcd"]=m; exec(compile(src,"tcd","exec"),m.__dict__)
g=m.__dict__; g["VERBOSE"]=True; g["VAULT"]=g["Vault"](tempfile.mkdtemp(),"TEST"); g["DART_API_KEY"]=""
tc=g["to_code6"]
print("-- 정상 입력이 그대로 통과하는지 --")
for v,exp in [("005930","005930"),(5930,"005930"),(5930.0,"005930"),("005930.KS","005930"),
              ("A005930","005930"),("Q500011","500011"),("00104K","00104K"),("09701L","09701L"),
              ("900140","900140"),(" 005930 ","005930"),("00680K","00680K"),("035420","035420")]:
    got=tc(v); print(f"  {str(v):12s} -> {got}  {'OK' if got==exp else '*** REGRESSION exp='+str(exp)}")
print("-- 비주권/쓰레기 입력이 None 이 되는지 --")
for v in ["008465W","00846W","00088R","J00123","005930R","KR7005930003","0059301","abcdef","",None]:
    print(f"  {str(v):14s} -> {tc(v)}")

print("\n-- 계약 테스트 CODE 케이스 --")
for k,v in {"005930":"005930",5930:"005930","A005930":"005930","005930.KS":"005930",
            "09701K":"09701K","":None,"abcdef":None}.items():
    assert tc(k)==v, (k,tc(k),v)
print("  17개 계약 중 CODE 케이스 전부 통과")

LIVE=[["005930","삼성전자","KOSPI","전자","반도체","1975-06-11","12","","",""],
      ["008465","한독우선주","KOSPI","의약","제약","1976-05-11","12","","",""],
      ["000846","현대건설우","KOSPI","건설","건설","1984-02-04","12","","",""],
      ["352820","하이브","KOSPI","엔터","엔터","2020-10-15","12","","",""]]
DEAD=[["111111","진짜폐지사","KOSDAQ","주권","보통주","2011-06-01","2019-04-01","감사의견거절","","","서비스",500,1000,"",""],
      ["008465W","한독 3WR","KOSPI","신주인수권증권","신주인수권증권","2014-03-10","2016-03-09","권리행사기간만료","","","",0,0,"",""],
      ["00846W","현대건설 2WR","KOSPI","신주인수권증서","신주인수권증서","2015-05-10","2017-06-09","권리행사기간만료","","","",0,0,"",""],
      ["J35282","기타증권","KOSPI","수익증권","수익증권","2013-01-10","2018-02-09","신탁계약기간만료","","","",0,0,"",""]]
KIND=[["삼성전자",5930,"전자","폰","1975-06-11","12월","","",""],
      ["한독우선주",8465,"의약","약","1976-05-11","12월","","",""],
      ["현대건설우",846,"건설","건","1984-02-04","12월","","",""],
      ["하이브",352820,"엔터","음","2020-10-15","12월","","",""]]
L,D,K=fx.listing_csv(LIVE),fx.delisting_csv(DEAD),fx.kind_html(KIND)
g["http_get"]=lambda url,**kw:(D if "listing/delisting" in url else L if "listing/krx" in url
                               else K if "kind.krx.co.kr" in url else None)
g["fetch_naver_names"]=lambda codes,limit=400:{}
snaps=pd.DataFrame(columns=["snap_date","code","market"])
sec=g["build_security_master"](snaps)
print("\n=== SECURITY MASTER (패치 후) ===")
print(sec[["code","name","listing_date","delisting_date","src"]].to_string(index=False))
px=pd.DataFrame({"date":pd.bdate_range("2010-01-04","2025-12-31"),"code":"005930"})
U=g["Universe"](sec,snaps,px)
print("\n=== UNIVERSE.at (패치 후) ===")
for t in ["2015-12-31","2016-12-31","2018-12-31","2021-12-31","2025-06-30"]:
    print(" ",t,U.at(t))
