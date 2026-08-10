import types, sys, os, time, json, tempfile, collections
os.environ["TCD_NO_PIP"]="1"
FILE="/home/user/claude-coding/strategies/tcd_v2_00_integrated_all_packs.py"
src=open(FILE,encoding="utf-8").read()
src=src[:src.index("def offer_download")]
src=src.replace("def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
                "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n    return True,'skip'")
m=types.ModuleType("tcd"); sys.modules["tcd"]=m
exec(compile(src,"tcd","exec"), m.__dict__)
g=m.__dict__; g["VERBOSE"]=False

TMP=tempfile.mkdtemp(prefix="tcdvault")
g["VAULT"]=g["Vault"](TMP,"TEST")
g["DART_API_KEY"]="KEY"
g["DBUDGET"]=g["DartBudget"]()
g["RUN_MODE"]="FULL"

CALLS=collections.Counter()
LK=__import__("threading").Lock()

def fake_http_json(url, source="generic", params=None, tries=2, on_attempt=None, **kw):
    ep=url.rsplit("/",1)[-1]
    with LK: CALLS[ep]+=1
    if on_attempt: on_attempt()          # 1 real attempt -> refund tries-1
    if ep=="fnlttMultiAcnt.json":
        codes=str((params or {}).get("corp_code","")).split(",")
        return {"status":"000","list":[{"corp_code":c,"sj_div":"IS","account_nm":"매출액",
                 "thstrm_amount":"1000","rcept_no":"20200101000001"} for c in codes]}
    if ep=="fnlttSinglAcntAll.json":
        return {"status":"000","list":[{"corp_code":(params or {}).get("corp_code"),"sj_div":"BS",
                 "account_id":"ifrs-full_Assets","account_nm":"자산총계","thstrm_amount":"1000",
                 "fs_div":"OFS","rcept_no":"20200101000001"}]}
    if ep=="empSttus.json":
        return {"status":"000","list":[{"fo_bbm":"전사","sexdstn":"남","sm":"100",
                 "fyer_salary_totamt":"1000000","rcept_no":"20200101000001"}]}
    if ep=="list.json":
        return {"status":"000","total_page":1,"list":[{"corp_code":"00126380","corp_name":"X",
                 "stock_code":"005930","rcept_no":"2020010100000%d"%(CALLS[ep]%10),
                 "rcept_dt":"20200115","report_nm":"현금ㆍ현물배당 결정","flr_nm":"X","corp_cls":"Y"}]}
    return {"status":"000","list":[]}

g["http_json"]=fake_http_json

corps=[f"{i:08d}" for i in range(2500)]
years=list(range(2014,2027))
print(f"corps={len(corps)}  years={len(years)}  DART_DAILY_LIMIT={g['DART_DAILY_LIMIT']:,}")
print(f"job arithmetic: multi={len(corps)//100*len(years)*4:,}  full={len(corps)*len(years)*4:,}  "
      f"emp={len(corps)*len(years):,}  disc-months={len(list(__import__('pandas').period_range('2016-08-01','2026-07-31',freq='M')))}")

def show(tag,t0):
    b=g["DBUDGET"]
    print(f"after {tag:<28}: calls={dict(CALLS)}  budget used={b.n:,}  exhausted={b.exhausted}  ({time.time()-t0:.1f}s)")

t0=time.time(); multi=g["fetch_dart_multi_accounts"](corps,years); show("fetch_dart_multi_accounts",t0)
print("   multi rows:",len(multi))
t0=time.time(); fs=g["fetch_dart_financials"](corps,years,priority=[]); show("fetch_dart_financials",t0)
print("   fs rows:",len(fs))
t0=time.time(); emp=g["fetch_dart_employees"](corps,years); show("fetch_dart_employees",t0)
print("   emp rows:",len(emp))
t0=time.time(); dis=g["fetch_dart_disclosures"]("2016-08-01","2026-07-31"); show("fetch_dart_disclosures",t0)
print("   dis rows:",len(dis))
