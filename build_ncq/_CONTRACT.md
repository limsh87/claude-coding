# ARC-NCQ v1.0 — 모듈 인터페이스 계약 (작성자 전원 준수)

이 파일은 **조립 규약**이다. 각 모듈은 독립 파일이지만 최종적으로 `tools/build_ncq.py` 가
하나의 자립 실행 파일로 **단순 문자열 연결**한다. 따라서:

* 모듈 파일에 `import` 문을 새로 쓰지 말 것 (전부 `build/01_bootstrap.py` 가 이미 함).
  예외: 표준 라이브러리 지역 import(`from scipy import stats as _st` 등)는 함수 **안**에서만 허용.
* `from __future__ import ...` 금지, shebang 금지.
* 최상위 이름(함수/클래스/상수)은 **전 모듈에서 유일**해야 한다 (빌더가 중복 정의를 에러로 잡는다).
  NCQ 모듈의 최상위 이름은 전부 `ncq_` / `NCQ_` 접두어 또는 아래 계약에 명시된 이름만 사용.
* 모든 로그는 `LOG.info/ok/warn/error/banner/table` 로만. `print` 금지(`_safe_print` 는 허용).
* 모든 연산은 호출자가 `PIPE.stage(...)` 안에서 돌린다. 모듈 함수는 예외를 삼키지 말고
  **의미 있는 예외**를 올리거나 빈 결과를 돌려준다(둘 중 무엇인지 docstring 에 명시).

---

## 0. 조립 순서 (빌더가 이 순서로 이어붙인다)

```
build/00 은 쓰지 않음  →  build_ncq/ncq_00_header.py      (설정·자격증명)
build/01_bootstrap.py    (환경·의존성·임포트)
build/02_kernel.py       (LOG / PIPE / IOEvent / diagnose / KillCriteria)
build/03_util.py         (as_ts, to_code6, atomic_write_*, pmap_io, xsec_z, hac_tstat, bh_fdr …)
build/04_vault.py        (Vault — 공용/전용 인덱스. 절대 1원칙)
build/05_http.py         (http_get / http_json / http_post / soup_of)
build/10_ingest_universe.py  (KRXGate, fetch_fdr_listing/delisting, fetch_kind_listing,
                              fetch_dart_corpcode, fetch_pykrx_snapshots, build_security_master)
build/11_ingest_price.py     (KRXAuth/KRX, fetch_prices, build_price_panel)
build/13_ingest_research.py  (hankyung_collect, naver_collect, naver_enrich_detail,
                              parse_kr_date, code_from_title, REPORT_COLS, pdf_text …)
build/14_entity_research.py  (normalize_broker, build_report_master, build_analyst_ledger,
                              audit_linkage, BROKER_CANON, MAJOR_BROKERS)
build/20_pit.py              (PITStore/PIT, Universe, build_cells, LISTING_SEASONING_DAYS)
build_ncq/ncq_05_budget.py   (PhaseBudget · 열화 사다리 · manifest · 드라이브 루트 해석)
build_ncq/ncq_10_universe.py (PIT 시가총액 · 하위 N 유니버스 · 3단 퍼널)
build_ncq/ncq_20_index.py    (IRS 소스 · 리포트 인덱스 통합 · 완결성 진단)
build_ncq/ncq_30_coverage.py (신규 커버리지 판정 H1/H2 · 스폰서 분리)
build_ncq/ncq_40_text.py     (렉시콘 동결 · PDF 섹션 추출 · 스코어링 · 횡단면 z)
build_ncq/ncq_50_backtest.py (오버랩 코호트 백테스트 · 벤치마크 · perf_stats)
build_ncq/ncq_60_robust.py   (P1~P4 · BH-FDR · 부트스트랩 · 순열 · WF · PBO · DSR · Holm · 민감도)
build_ncq/ncq_70_report.py   (성과표 · 진단 9종 · 해석표 · HTML · 흐름지도)
build_ncq/ncq_80_verify.py   (계약검정 · 카나리 · 실경로 리허설 · 합성 스모크)
build_ncq/ncq_90_main.py     (오케스트레이터)
```

---

## 1. 헤더가 제공하는 전역 (ncq_00_header.py)

```python
KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY, DART_API_KEY
HANKYUNG_ID, HANKYUNG_PW
GDRIVE_ROOT, GDRIVE_SHARED_NS="_shared", GDRIVE_PRIVATE_NS="arc_ncq_v1"
GDRIVE_ADOPT_DIRS: List[str], LOCAL_CACHE_ROOT
BACKTEST_START="2016-08-01", BACKTEST_END="2026-07-31"
N_WORKERS_IO, N_WORKERS_CPU, RATE_LIMIT_QPS(dict), MEM_BUDGET_GB
RESEARCH_COLLECT, RESEARCH_SOURCES, RESEARCH_DOWNLOAD_PDF,
RESEARCH_PDF_MAX_PER_MONTH, RESEARCH_TARGET_PER_YEAR
RUN_MODE ∈ {"SMOKE","FULL","CACHED"}
SEED, VERBOSE, STOP_ON_KILL_CRITERIA
STRATEGY_ID="ARC_NCQ_V1", STRATEGY_NAME, BUILD_VERSION
# 전략 파라미터 (기본값 = 사전등록 기준선)
NCQ_UNIVERSE_BOTTOM_N=1000, NCQ_MIN_ADV=100_000_000, NCQ_LOOKBACK_M=24, NCQ_BURNIN_M=24
NCQ_HOLD_MONTHS=12, NCQ_TERCILE=1/3, NCQ_COST_ROUNDTRIP=0.018
NCQ_MAX_NEW_PER_MONTH=20, NCQ_ADV_PARTICIPATION=0.10, NCQ_ACCOUNT_KRW
NCQ_SENS_ADV=[50_000_000,100_000_000,300_000_000]
NCQ_SENS_TOPPCT=[0.25,1/3,0.50]
NCQ_SENS_HOLD=[6,12,18]
NCQ_SENS_COST=[0.010,0.018,0.030]
NCQ_PHASE_BUDGET_S = {"P0":2700,"P1":7200,"P2":300,"P3":3600,"P4":600,"P5":300,"P6":1500}
NCQ_MIN_EVENTS_PER_MONTH=5, NCQ_MIN_TOTAL_EVENTS=800, NCQ_MIN_VALID_YEARS=5.0
DART_STATUS_MSG: Dict[str,str]     # build/10 이 참조하므로 반드시 존재
```

## 2. ncq_05_budget.py 가 제공 (이미 작성됨 — 아래는 사용 API)

```python
class PhaseBudget:                       # with PhaseBudget("P1", 7200) as B: ... B.check()
    def check(self) -> bool              # 캡 도달 시 False (예외 안 던짐)
    def frac(self) -> float
LADDER: "OrderedDict[str,str]"           # L1..L5 설명
def degrade(level: str, reason: str) -> None      # L5 는 자동 적용 금지(예외)
def degraded() -> List[str]
def is_degraded(level: str) -> bool
MANIFEST: Dict[str, Any]                 # 자유 갱신. ncq_write_manifest 가 직렬화
def manifest_put(key: str, value) -> None
def resolve_gdrive_root() -> str         # Colab/Jupyter/Windows 자동 해석
```

## 3. 데이터 프레임 스키마 (컬럼명 고정 — 임의 변경 금지)

```
sec        : code,name,market,listing_date,delisting_date,industry,corp_code,src
px_daily   : code,date,open,high,low,close,volume,amount,src,adv20,ret1d
pxm        : code,month,signal_date,close,adv20,next_open,next_date,exec_px,fwd_ret
MCAP       : code,month,mcap,shares,mcap_src              (PIT: month 말 시점 값)
UNI        : month,code,mcap,adv20,mcap_rank,in_uni(bool),liq_pass(bool),excl(str)
REP        : report_uid,source,pub_date,stock_code,stock_name,broker_raw,broker_id,
             broker_name,analyst_raw,title,pdf_url,detail_url,target_price,opinion,
             is_sponsored(bool),category,src_report_id,dedup_key,event_date,knowledge_date
EV         : month,code,event_type('H1'|'H2'),n_reports,n_brokers,sources,broker_ids,
             sponsor_group('SPONSORED_ONLY'|'ORGANIC_ONLY'|'MIXED'),report_uids
TXT        : report_uid,code,pub_date,sec_title,sec_headline,sec_body,n_chars,n_pages,
             extract_ok(bool),extract_method
SCORE      : report_uid,code,month,doc_raw,doc_score,n_chars,g_A,g_B,g_C,g_D,g_H,g_N
SIG        : month,code,event_score,z,pooled(bool),pool_n,rank_pct,selected(bool),
             placebo(bool),sponsor_group,event_type,exec_px,adv20,fwd_ret
BT(dict)   : {"returns": DataFrame[month,ret,ret_gross,n,turnover,cost,equity],
              "holdings": DataFrame[month,code,weight,ret,cohort,z],
              "cohorts":  DataFrame[cohort,code,entry_month,exit_month,ret_h,n_months],
              "label": str}
```

* `month` 는 **항상 월말 Timestamp**(`month_end`), tz-naive.
* `code` 는 `to_code6` 를 통과한 6자리 문자열.
* 결측을 0으로 채우지 말 것. 모르는 것은 NaN 으로 남긴다.

## 4. 스파인 모듈이 제공하는 함수 (leaf 모듈이 호출해도 되는 것)

```python
# ncq_10_universe.py
def build_marketcap_panel(codes, months, px_daily, sec) -> pd.DataFrame            # MCAP
def build_ncq_universe(months, pxm, mcap, uni_obj, sec,
                       bottom_n=None, min_adv=None) -> pd.DataFrame                # UNI
def universe_funnel(UNI, EV=None) -> pd.DataFrame                                  # 3단 퍼널

# ncq_20_index.py
def collect_report_index(months) -> pd.DataFrame                                   # REP
def coverage_completeness(REP, months) -> Tuple[pd.DataFrame, pd.Timestamp]        # (진단표, 유효시작월)

# ncq_30_coverage.py
def build_coverage_events(REP, UNI, months, valid_start,
                          lookback_m=None, burnin_m=None) -> pd.DataFrame          # EV
def audit_events(EV, REP) -> dict

# ncq_40_text.py
NCQ_LEXICON: dict ; NCQ_LEXICON_SHA: str ; NCQ_PREREG: dict ; NCQ_PREREG_SHA: str
def freeze_configs(outdir: str) -> Tuple[dict,str,dict,str]
def collect_event_texts(EV, REP) -> pd.DataFrame                                   # TXT
def score_texts(TXT) -> pd.DataFrame                                               # SCORE
def build_signal_panel(SCORE, EV, UNI, pxm, months, top_pct=None) -> pd.DataFrame  # SIG

# ncq_50_backtest.py
def run_overlap_backtest(SIG, pxm, sec, uni_obj, months, hold_months=None,
                         sel_col="selected", cost_roundtrip=None,
                         adv_cap=True, label="NCQ") -> dict                        # BT
def perf_stats(R: pd.DataFrame) -> dict
def bench_universe_ew(UNI, pxm, months) -> pd.Series      # Bottom-N 동일가중 (주 벤치마크)
def bench_index(months) -> Dict[str, pd.Series]           # KOSPI / KOSDAQ
def excess_series(BT, bench: pd.Series) -> pd.Series
```

## 5. leaf 모듈이 제공해야 하는 함수 (main 이 이 이름으로 호출한다)

```python
# ncq_60_robust.py
NCQ_ROBUST: "OrderedDict[str,dict]"          # {id: {"id","name","pass","detail","kill","metrics"}}
def run_prereg_tests(SIG, BT, bench_ew, pxm, sec, uni_obj, months, run_fn) -> dict
def run_stat_suite(BT, bench_ew, SIG, months, run_fn, n_trials:int) -> dict
def run_sensitivity(ctx, months, build_sig_fn, run_fn) -> pd.DataFrame
def report_robustness() -> None

# ncq_70_report.py
def report_performance(BT, benches: Dict[str,pd.Series], label="") -> None
def report_coverage_diagnostics(diag, REP, EV) -> None
def report_diagnostics(SIG, EV, BT, UNI, sec, benches) -> None
def report_interpretation(SIG, EV, SCORE) -> None
def report_dataflow_map() -> None
def write_html_report(outdir, ctx) -> str
def write_manifest(outdir, ctx) -> str
def offer_download(paths) -> None

# ncq_80_verify.py
def run_contract_tests(strict=True) -> bool
def run_canaries(strict=True) -> dict
def run_rehearsal(strict=True) -> bool
def run_selftest(full_chain=False) -> bool
```

## 6. 절대 규칙

1. **드라이브 캐시 훼손 금지.** 신규 저장은 `VAULT.put_table(name, df, scope="shared"|"private")`
   또는 `VAULT.put_blob(...)` 로만. 삭제·이동 API를 새로 만들지 말 것.
   공용(`scope="shared"`)에는 **다른 전략도 재사용 가능한 원본/범용 정제본**만,
   전용(`scope="private"`)에는 이 전략의 해석물만.
2. **PIT.** 이벤트 판정·신호 산출에 쓰는 모든 정보는 `pub_date <= month말`. 진입은 익영업일 시가.
3. **생존자편향.** 상장폐지 종목을 유니버스에서 빼지 않는다. 폐지 시 명세 §10 대로 -50% 후 현금화.
4. **렉시콘·사전등록은 수익률 확인 전에 동결**하고 SHA 를 manifest 에 남긴다.
5. 나쁜 결과를 좋아 보이게 만들지 않는다. 판정 실패는 그대로 출력한다.
