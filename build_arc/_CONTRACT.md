# ARC-TXT v2.0 — 모듈 인터페이스 계약 (작성자 전원 준수)

> 이 문서는 `build_arc/` 조각들이 **하나의 파일로 이어붙여질 때** 서로를 부르는 방식을 규정한다.
> 조각은 `tools/build_arc.py` 가 번호순으로 concat 하므로 **import 문을 쓰지 말 것**.
> 위 번호 파일에서 정의된 모든 전역은 아래 번호 파일에서 그냥 이름으로 쓸 수 있다.

---

## 0. 절대 규칙

1. **`import` 금지.** 조각 안에서 `from x import y` / `import x` 를 쓰지 않는다. 표준 라이브러리는
   `01_bootstrap.py` 가 전부 임포트해 두었다 (`os,sys,re,io,gc,json,time,math,zipfile,hashlib,
   textwrap,traceback,sqlite3,random,shutil,tempfile,platform,warnings,threading,unicodedata`,
   `datetime as _dt`, `np`, `pd`, `requests`, `BeautifulSoup`, `tqdm`,
   `defaultdict/Counter/OrderedDict`, `dataclass/field/asdict`, `contextmanager`,
   `ThreadPoolExecutor/ProcessPoolExecutor/as_completed`, typing 전부, `urlencode/urljoin/quote/
   unquote/urlparse/parse_qs`). 함수 **안에서의** 지연 임포트(`from scipy.stats import norm`)는 허용.
2. **최상위 이름 중복 금지.** 빌더가 AST 로 중복 def/class 를 검사해 실패시킨다.
   새 헬퍼는 모듈 접두사를 붙인다 (`_d1_...`, `_d2_...`, `_tone_...`).
3. **모든 연산은 `PIPE.stage(...)` 안에서** 돈다 — 단, 그 호출은 `90_main.py` 가 한다.
   조각은 순수 함수를 제공하고, 내부에서 `PIPE.io(...)` / `PIPE.note(...)` / `LOG.*` 만 쓴다.
4. **PIT 강제.** 시계열 테이블을 반환하는 수집/정제 함수는 반드시
   `pit_frame(df, event_date, knowledge_date, source=...)` 를 통과시킨다.
   `PIT.register()` 는 PIT 컬럼이 없으면 `KeyError` 로 거부한다.
5. **결측을 0으로 채우지 않는다.** 근거 없는 값이 근거 있는 값처럼 보이면 안 된다.
   0 으로 채워야 하는 곳은 명세가 명시한 곳뿐이다(§7.2 축 A 결측 → `ΔTONE_resid = 0`).
6. **LLM API 호출 절대 금지** (§5.1, §6.3). 규칙 기반 파싱 + 정규식 + 경량 ML 만.
7. 로그는 한국어. 실패는 숨기지 않고 표로 드러낸다. 수치 없는 낙관/비관 주장 금지(§9.1).

---

## 1. 파일 순서 (빌더가 이 순서로 concat)

| # | 파일 | 담당 | 계층 |
|---|---|---|---|
| 00 | `00_header.py` | **spine** | 사용자 설정 / 키 입력부 / 전역 상수 |
| 01 | `01_bootstrap.py` | 기존 재사용(+선택 의존성) | L0 |
| 02 | `02_kernel.py` | 기존 재사용 | L0 |
| 03 | `03_util.py` | 기존 재사용(+ARC 헬퍼) | L0 |
| 04 | `04_vault.py` | 기존 재사용 | L0 |
| 05 | `05_http.py` | 기존 재사용 | L0 |
| 10 | `10_ingest_universe.py` | 기존 재사용(+시총) | L1 |
| 11 | `11_ingest_price.py` | 기존 재사용(+시총/주식수) | L1 |
| 12 | `12_ingest_dart_fin.py` | 기존 재사용(+주식수/감사의견) | L1 |
| 13 | `13_ingest_research.py` | 기존 재사용(+본문 전문 추출) | L1 |
| 14 | `14_entity_research.py` | 기존 재사용(+리비전 패널) | L1 |
| 15 | `15_ingest_dart_doc.py` | **AGENT-1** | L1 — DART 정기보고서 원문 + 정규화 |
| 20 | `20_pit.py` | **spine** | L1 — PITStore + U-1000 유니버스 |
| 21 | `21_gate.py` | **AGENT-2** | L1 — Phase 0 게이트 6종 |
| 30 | `30_axis_a_tone.py` | **AGENT-3** | L2 — TONE 분류기 / ΔTONE / 직교화 |
| 31 | `31_axis_b_d1.py` | **AGENT-4** | L2 — D1 유사도 4종 / 섹션 / z |
| 32 | `32_axis_b_d2.py` | **AGENT-5** | L2 — D2 재무 이상현상 |
| 33 | `33_axis_b_d3.py` | **AGENT-6** | L2 — D3 하드팩트 + 배제 플래그 |
| 40 | `40_score.py` | **spine** | L2 — DART_SCORE / FINAL_SCORE / 상관진단 |
| 41 | `41_backtest.py` | **spine** | L3 — 분기 백테스트 + 비용 |
| 50 | `50_ablation.py` | **AGENT-7** | L5 — 어블레이션 11종 + BH-FDR |
| 51 | `51_robust.py` | **AGENT-8** | L5 — 강건성 9종 |
| 60 | `60_report.py` | **AGENT-9** | L6 — 최종 산출물 11종 |
| 70 | `70_contracts.py` | **AGENT-10** | L0 — 계약 자동검정 |
| 75 | `75_rehearsal.py` | **AGENT-11** | L0 — 실경로 리허설 |
| 80 | `80_selftest.py` | **AGENT-12** | L0 — 합성 스모크 |
| 90 | `90_main.py` | **spine** | 오케스트레이터 |

---

## 2. 시간 축 — 이 전략의 기본 단위는 **분기**다

```python
REBAL_MONTHS = (3, 6, 9, 12)            # §4 리밸런싱: 3/1, 6/1, 9/1, 12/1
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"
```

`03_util.py` 가 제공하는 분기 헬퍼 (**spine 이 추가함, 그대로 쓸 것**):

```python
rebal_dates(start, end) -> pd.DatetimeIndex
    # 3/1, 6/1, 9/1, 12/1 (달력일). 백테스트 구간 내부만.
    # 패널의 as_of 축이며 이름은 항상 컬럼 "asof".

qlabel(ts) -> str        # Timestamp → "2019Q3"   (분기 라벨)
qshift(qs, k) -> str     # "2019Q3", -1 → "2019Q2" / -4 → "2018Q3"
qend(qs)  -> pd.Timestamp  # "2019Q3" → 2019-09-30
```

**패널 P 의 행 키는 `(code, asof)`** 이고 `asof ∈ rebal_dates(...)`.
`q` 컬럼은 `asof` 직전에 종료된 분기 라벨 (asof=2019-09-01 → q="2019Q2").

---

## 3. 패널 P 의 컬럼 계약

`20_pit.py` 의 `build_arc_panel()` 이 만들어 넘기는 **기본 컬럼** (전부 존재 보장):

| 컬럼 | 의미 |
|---|---|
| `code` | 6자리 종목코드(2024 영숫자 티커 포함) |
| `asof` | 리밸런싱 시점 (Timestamp) |
| `q` | 직전 종료 분기 라벨 "YYYYQn" |
| `corp_code` | DART 법인코드 (없을 수 있음 → NaN) |
| `market` | KOSPI / KOSDAQ |
| `industry`, `sector` | 업종 문자열 / 상위 섹터 |
| `mktcap` | PIT 시가총액(원) |
| `adtv60` | 직전 60거래일 평균 거래대금(원) |
| `close`, `exec_px` | 신호일 종가 / 체결가(익영업일 시가, 없으면 종가) |
| `fwd_ret_1q`,`fwd_ret_2q`,`fwd_ret_4q` | 체결가→체결가 1/2/4분기 수익률 (상폐 -100% 반영) |
| `listing_months` | 상장 경과 개월수 |
| `cell` | 횡단면 표준화 셀 = `"{q}|{sector}"` |
| `cell_all` | 폴백 셀 = `"{q}|ALL"` |

**각 축 모듈이 추가해야 하는 컬럼** (없으면 하류가 결측 처리하되, 컬럼 자체는 항상 만들 것):

```
축 A (30):  TONE, TONE_prev, dTONE, dTONE_resid, n_reports_q, has_axis_a
축 B D1 (31): CH_S_MDA, CH_S_LEGAL, CH_S_EXEC, CH_S_BIZ, CH_S_RISK, CH_S_GOV, CH_S_ALL,
              CHANGE_composite, D1_SCORE, STRUCT_FLAG, D1_MISSING
축 B D2 (32): ACCRUAL, NOA, AR_DIVERGE, INV_DIVERGE, CFO_NI_GAP, SHARE_GROWTH, D2_SCORE
축 B D3 (33): NF_* (이벤트별 0/1), DELTA_NONFIN, D3_SCORE
배제  (33): EX_RELATED, EX_CONTINGENT, EX_LITIGATION, EX_AUDIT, EX_OWNER, EX_CBBW,
            EX_LOSS4Q, EX_IMPAIR, EXCLUDE (1 = 제외)
스코어(40): DART_SCORE, FINAL_SCORE, FINAL_RANK
```

> ⚠ 컬럼을 만들 때는 **결합 후에** 만든다. 먼저 만들고 `asof_join` 하면 merge 가
> 접미사를 붙여 실제 데이터가 흘러가 버린다 (기존 `p_d_text.py` 주석 참조).

---

## 4. 상위 조각이 제공하는 것 (그대로 쓸 것 — 다시 만들지 말 것)

### 로깅 · 스테이지
```python
LOG.info/ok/warn/error/debug(msg)
LOG.banner(title, sub="")            LOG.rule(title="")
LOG.table(rows, headers, aligns=None, maxw=46, title="")
PIPE.io(direction, kind, name, obj=None, source="", ok=True, note="", bytes_=-1)
PIPE.note(msg)                       PIPE.stage(sid, name, layer, budget_s=, critical=, skip_if=, skip_reason=)
KillCriteria(Exception)              StageFailure(Exception)
_safe_print(...)   _dw(s)   _pad(s,n,align)   _trunc(s,n)
```

### 날짜 · 해시 · IO
```python
as_ts(x) -> Optional[pd.Timestamp]      # tz-naive normalize
as_ts_series(s) -> pd.Series
month_end(x)  month_range(start,end)
sha1_str(*parts)  sha1_bytes(b)  sha1_file(path)
norm_text(s)  norm_corp_name(s)  to_code6(x)  similarity(a,b)
atomic_write_bytes/text/parquet(path, ...)   read_parquet_safe(path)
read_jsonl(path)  append_jsonl(path, rows)
```

### 병렬 · 네트워크
```python
pmap_io(fn, items, workers=None, desc="", quiet=False)     # 스레드
pmap_cpu(fn, items, workers=None, desc="")                 # 프로세스(fork) → 실패 시 스레드
limiter(source).wait()          retry(tries=4, base=1.6, ...)
http_get(url, source=, params=, headers=, timeout=, tries=, as_bytes=, referer=, force_enc=, on_attempt=)
http_post(url, source=, data=, json_body=, ...)
http_json(url, source=, **kw)   soup_of(html)   euckr_q(s)   _decode(content, enc, url, force_enc=None)
```

### 캐시 (VAULT) — **절대 1원칙**
```python
VAULT.get_table(name, scope="shared"|"private", max_age_days=None) -> Optional[pd.DataFrame]
VAULT.put_table(name, df, scope=, domain=, source=, extra=None) -> Optional[str]
VAULT.put_blob(domain, subtype, key, data, fmt, source=, event_date=, knowledge_date=, scope=, extra=)
VAULT.get_blob(uid, scope="shared") -> Optional[bytes]
VAULT.adopt(abs_path, domain, subtype, key, ...)     # 이동 없이 경로만 등록
VAULT.lookup(scope, **eq) -> pd.DataFrame            VAULT.has(scope, uid) -> bool
VAULT.flush(scope=None)   VAULT.compact(scope)   VAULT.load_index(scope)
VAULT.ns["shared"] / VAULT.ns["private"]             # 절대경로
```
- **공용(`shared`)** = 다른 전략도 재사용 가능한 원본/범용 정제본
  (가격, 재무, 공시목록, 보고서 원장, 애널리스트 원장, **DART 원문 blob**, **정규화 텍스트**).
- **전용(`private`)** = 이 전략 고유 해석물 (유사도, 피처패널, 스코어, 백테스트 결과, 리포트).
- 절대 삭제/덮어쓰기 금지. `put_table` 은 기존 파일을 자동 백업 후 교체한다.

### PIT
```python
PIT.register(name, df, key_cols=())        # PIT 컬럼 없으면 KeyError
PIT.get(name, as_of, cols=None, latest_by=None)
PIT.asof_join(panel, name, by, left_time="asof", cols=None, suffix="")
pit_frame(df, event_date, knowledge_date, source="")
```

### 횡단면 통계 (C5 순서 고정: winsorize ±2σ → z)
```python
xsec_z(values, cells, min_n=CELL_MIN_N, k=WINSOR_SIGMA) -> pd.Series   # float32
xsec_rank_pct(values, cells, min_n=CELL_MIN_N) -> pd.Series
col(df, name, default=np.nan) -> pd.Series      # 없는 컬럼도 NaN Series
gby(df, name, key="code")
safe_div(a, b)   dlog(s, periods)   nanmean_cols(df, cols)   downcast(df)   mem_mb(df)
hac_tstat(x, lags=None) -> (mean, t)
bh_fdr(pvals, q=0.10) -> np.ndarray[bool]
rolling_ols_resid(y, X, window)   rolling_ols_beta_last(y, X, window)
```

**spine 이 `03_util.py` 에 추가하는 ARC 전용 헬퍼:**
```python
rebal_dates(start, end) -> pd.DatetimeIndex
qlabel(ts) -> str            qshift(qs, k) -> str          qend(qs) -> pd.Timestamp
xsec_z_arc(P, name_or_series) -> pd.Series      # cell → cell_all 폴백 사다리 적용 z
xsec_rank_arc(P, name_or_series) -> pd.Series
winsor_series(s, p=0.01) -> pd.Series           # 상하위 p 윈저라이즈(백분위 기준)
xsec_resid(y, X, cells) -> pd.Series            # 셀별 OLS 잔차(횡단면 직교화). 절편 자동 포함
ols_resid_np(y, X) -> np.ndarray                # 단일 횡단면 OLS 잔차 (ridge 안정화)
newey_west_p(x, lags=None) -> float             # 양측 p-value
info_coef(sig, fwd, groups) -> (ic_mean, ic_ir, n)   # 기간별 Spearman IC
```

### 기존 수집 함수 (L1) — 이미 존재, 시그니처 불변
```python
fetch_pykrx_snapshots(months)          build_security_master(snapshots)
fetch_fdr_listing()  fetch_fdr_delisting()  fetch_kind_listing()  fetch_dart_corpcode()
KRXG.warmup()/call(fn,*a,**kw)         KRX.login()/json_data(bld, **params)
fetch_prices(codes, start, end)        build_price_panel(px, months)
fetch_market_cap(codes, months)        # spine 이 11 에 추가 → PIT 시총/주식수
fetch_dart_multi_accounts(corps, years)     fetch_dart_financials(corps, years, priority=None)
merge_financial_tiers(full, multi)          tidy_financials(fs)
fetch_dart_employees(corps, years)          fetch_dart_disclosures(start, end)
fetch_dart_shares(corps, years)        # spine 이 12 에 추가 → 주식총수(SHARE_GROWTH)
fetch_dart_audit(corps, years)         # spine 이 12 에 추가 → 감사의견 특기/강조사항
dart_api(endpoint, params, source="dart", tries=2) -> Optional[dict]
DBUDGET.take(k)/refund(k)/remaining() / n / DART_DAILY_LIMIT
hankyung_collect(start,end)  naver_collect(start,end)  naver_enrich_detail(df)
download_pdfs(df, cap_per_month=0)     pdf_text(data, max_pages=3)   pdf_full_text(data)
build_report_master(frames, sec)       build_analyst_ledger(rep) -> (A, L)
audit_linkage(rep, A, L)               build_revision_panel(L, rebals) -> pd.DataFrame
REPORT_COLS  normalize_broker(raw)  split_analysts(raw)  parse_kr_date  parse_target_price
```

---

## 5. 각 AGENT 모듈의 정확한 계약

### AGENT-1 — `15_ingest_dart_doc.py` (L1, DART 정기보고서 원문 + §6.1.3 정규화)

```python
ARC_DOC_TYPES = {"FY": "사업보고서", "H1": "반기보고서",
                 "Q1": "분기보고서", "Q3": "분기보고서"}

ARC_SECTIONS = ["S_MDA","S_LEGAL","S_EXEC","S_BIZ","S_RISK","S_GOV","S_ALL"]
ARC_SECTION_PAT: Dict[str, str]      # 섹션ID → 정규식 (사업보고서 목차 표제)

def arc_normalize_text(raw_html: str, company_names: Sequence[str]) -> str:
    """§6.1.3 [1]~[5] 를 순서대로 적용한 정규화 텍스트를 반환한다.
       [1] <table>/이미지/첨부 제거  [2] 숫자 → <NUM>  [3] 날짜/기수 → <DATE>/<PERIOD>
       [4] 자사명·종속회사명 → <COMPANY>   [5] 서식·법정문구·목차·페이지번호 제거 + 공백정규화
       ※ [6] 형태소 토큰화는 arc_tokenize() 가 담당(가역 검증을 위해 분리)."""

def arc_tokenize(norm_text: str) -> List[str]:
    """§6.1.3 [6]. KoNLPy(Mecab/Okt) → soynlp → 규칙기반 순으로 폴백.
       명사·동사·형용사 어간만, 조사·어미 제거, 불용어 사전 적용.
       폴백 경로가 쓰였으면 LOG.warn 으로 한 번만 알린다(전역 플래그)."""

def arc_split_sections(norm_text: str) -> Dict[str, str]:
    """정규화 텍스트 → {섹션ID: 본문}. S_ALL 은 항상 포함. 실패 섹션은 키 자체를 넣지 않는다."""

def fetch_arc_documents(dis: pd.DataFrame, sec: pd.DataFrame,
                        max_docs: int = 60000) -> pd.DataFrame:
    """반환 컬럼 (전부 필수):
       corp_code, rcept_no, rcept_dt(Timestamp), doc_type("FY"/"H1"/"Q1"/"Q3"),
       bsns_year(int), section, n_tokens(int), tf(str: JSON dict 토큰→빈도),
       bigram(str: JSON dict 상위 bigram→빈도), tok_len(int), is_amend(bool)
       · 원문 zip 은 VAULT.put_blob("dart_doc","raw",rcept_no,...) 로 공용 저장(scope="shared")
       · 정규화 결과는 종목×기간 단위 parquet 으로 공용 저장:
         VAULT.put_table(f"dart_doc_norm_{bsns_year}", ..., scope="shared")
       · 증분 캐시 필수(이미 있는 rcept_no 는 건너뜀)
       · PDF 스캔본 등 기계판독 실패는 세어서 LOG 로 실패율 보고 (§0.4)
       · 정정공시(is_amend)는 플래그만 기록, 신호에는 미사용 (§4.1)"""

def arc_doc_pairs(T: pd.DataFrame) -> pd.DataFrame:
    """§6.1.1 페어링: 동일 corp_code × 동일 doc_type × 전년 동기.
       반환: corp_code, doc_type, bsns_year, rcept_no, prev_rcept_no, rcept_dt, prev_rcept_dt,
             section, tf, prev_tf, bigram, prev_bigram, tok_len, prev_tok_len
       · 직전 분기와 비교 금지. 전년 동기가 없으면 그 행을 만들지 않는다."""

def arc_norm_sample_report(T: pd.DataFrame, n: int = 5) -> None:
    """§10-[4] 육안 검증용. 5종목의 정규화 전/후 앞 400자를 표로 출력.
       가짜 변화(숫자/날짜/사명)가 남아있는지 사람이 볼 수 있어야 한다."""
```
- `fetch_dart_disclosures` 는 `report_nm` 에 "사업보고서/반기보고서/분기보고서" 를 포함한 A 유형
  정기공시를 이미 담고 있다. 여기서 필터링해서 쓴다.
- DART 원문 API: `GET https://opendart.fss.or.kr/api/document.xml?crtfc_key=&rcept_no=` → ZIP.
  `PK` 매직바이트 검사 필수. zip 내부 **모든** xml/html 엔트리를 읽어야 한다(첫 엔트리만 읽으면 본문 대부분 소실).
  XML 선언의 `encoding=` 을 읽어 EUC-KR 디코딩.
- 호출 예산은 `dart_api` 를 쓰지 않고 `http_get` 을 쓰되, **`DBUDGET.take(1)` 을 반드시 직접 호출**하고
  False 면 즉시 중단한다(§0.3 실시간 잔여 호출량).

---

### AGENT-2 — `21_gate.py` (Phase 0 게이트 §2)

```python
ARC_GATES = [("GATE_1","median(pair_count) >= 150"), ..., ("GATE_6","fs_cov >= 0.90")]
GATE_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

def run_phase0_gates(ctx: dict, rebals: pd.DatetimeIndex) -> dict:
    """§2.1 산출물 7개를 실측하고 §2.2 조건으로 판정한다.
       입력 ctx 키: 'panel_base'(P 기본 패널), 'reports'(보고서 원장),
                    'doc_tokens'(fetch_arc_documents 결과), 'doc_pairs', 'fin'(tidy_financials),
                    'links'(report_analyst_link)
       반환 dict: {"axis_a": bool, "d1": bool, "d2": bool, "mode": "FULL"|"DART_ONLY"|...,
                   "metrics": {...}}
       · 표를 반드시 출력: 게이트ID / 실측치 / 기준 / 판정
       · GATE_1|2|3 실패 → axis_a=False, mode="DART_ONLY 폴백" 으로 보고 (§2.3)
       · GATE_4|5 실패 → d1=False, 사유 분해(PDF 스캔본/서식변경/페어부재) 표 출력
       · GATE_6 실패 → d2=False + '심각 이슈' 배너
       · text_extract_rate, analyst_id_rate, report_dist(0/1/2/3/4/5+ 히스토그램) 표 출력
       · 어떤 경우에도 예외를 던지지 않는다. 판정만 하고 돌려준다."""

def report_gate_table() -> None:
    """§9.2-(1) 최종 산출물용. GATE_RESULTS 를 표로 다시 출력."""
```

---

### AGENT-3 — `30_axis_a_tone.py` (축 A §5)

```python
TONE_MODEL_KIND = "logreg"     # "nb" | "logreg" | "lgbm"  — 00_header 의 ARC_TONE_MODEL 을 읽음
TONE_BOILERPLATE_PAT: List[str]  # 면책조항/컴플라이언스/서명부/투자등급 정의표 정규식

def tone_clean_report_text(txt: str) -> str:
    """정형 텍스트 제거(§5.1). 제거하지 않으면 증권사 식별자로 작동해 누출."""

def tone_sentences(txt: str) -> List[str]:
    """한국어 문장 분리. 최소 8자, 최대 400자. 숫자표/목차 라인 제거."""

def build_tone_training(rep: pd.DataFrame, px_daily: pd.DataFrame,
                        bench: Optional[pd.Series] = None) -> pd.DataFrame:
    """라벨 = 발간일 기준 2일 CAR(시장수익률 차감)의 부호. 문장 단위.
       반환: sentence(str), label(int 0/1), pub_date(Timestamp), report_uid, code
       ※ U-1000 한정이 아니다. 대형주 리포트도 학습에 쓴다(§5.1)."""

def fit_tone_expanding(train: pd.DataFrame, cut: pd.Timestamp):
    """cut 이전 데이터로만 학습. (vectorizer, model) 반환. 표본 부족 시 None."""

def score_tone_reports(rep_text: pd.DataFrame, train: pd.DataFrame,
                       rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """확장윈도우 재학습(§5.1 필수). 각 리밸일 cut 마다 이전 데이터로만 학습한 모델로
       그 이후~다음 cut 사이 발간 리포트를 채점한다.
       반환: report_uid, code, pub_date, TONE_report(float), n_sent(int),
             knowledge_date(=pub_date+1영업일), event_date(=pub_date)
       TONE(report) = (긍정문장수 − 부정문장수) / 전체문장수"""

def aggregate_tone(tone_rep: pd.DataFrame, rebals: pd.DatetimeIndex,
                   half_life_days: float = 30.0) -> pd.DataFrame:
    """§5.2 분기 집계. 가중치 = exp(-λ·경과일수), 반감기 30일.
       반환: code, asof, q, TONE, n_reports_q"""

def attach_axis_a(P: pd.DataFrame, tone_q: pd.DataFrame, rev: pd.DataFrame) -> pd.DataFrame:
    """§5.3 ΔTONE + 직교화.
       · dTONE = TONE(q) − TONE(q−1), 양 분기 모두 리포트 ≥1건일 때만
       · 통제변수: eps_rev(EPS 컨센 수정률), tp_rev(목표주가 수정률), opin_chg(투자의견 변경 더미),
                   mom_12_1, log_mktcap, log_adtv, 섹터 더미
       · 셀별이 아니라 **기간(q) 횡단면 전체**에 대해 회귀 → 잔차 dTONE_resid
       · has_axis_a = 1/0.  축 A 결측 종목은 탈락시키지 않는다(§7.2).
       반환: P (컬럼 추가)"""

def report_axis_a_ic(P: pd.DataFrame) -> dict:
    """§5.3 중간 검증. 직교화 전/후 IC 를 나란히 표로 출력하고 dict 반환.
       {"ic_raw":..,"icir_raw":..,"ic_resid":..,"icir_resid":..,"n":..,"verdict":str}
       직교화 후 IC 가 0과 구분 불가면 verdict 에 '축 A 비활성화 권고' 를 넣는다."""
```
- `rev` = `build_revision_panel(L, rebals)` 결과: `code, asof, q, eps_rev, tp_rev, opin_chg, n_analyst`.
- 학습 데이터가 없으면(리포트 미수집) 전 컬럼 NaN + `has_axis_a=0` 으로 채우고 경고 후 정상 반환.

---

### AGENT-4 — `31_axis_b_d1.py` (D1 §6.1)

```python
D1_SECTION_WEIGHTS = {"S_MDA":0.35,"S_LEGAL":0.25,"S_EXEC":0.15,
                      "S_BIZ":0.10,"S_RISK":0.05,"S_GOV":0.05,"S_ALL":0.05}   # 사전등록·튜닝금지
D1_METRICS = ("cosine","jaccard","simple","len_ratio")

def d1_similarity(pairs: pd.DataFrame) -> pd.DataFrame:
    """§6.1.4 4종 유사도. tf/bigram JSON 을 복원해 계산.
       cosine    : TF-IDF (unigram+bigram) 코사인. IDF 는 **해당 기간까지 관측된 문서로만**
                   확장(expanding) 산출 — 전체 기간 IDF 를 쓰면 그 자체가 미래누수다.
       jaccard   : 토큰 집합 자카드
       simple    : 공통 토큰 수 / 두 문서 평균 토큰 수
       len_ratio : min(len)/max(len)
       반환: corp_code, rcept_dt, bsns_year, doc_type, section,
             cosine, jaccard, simple, len_ratio"""

def d1_composite(S: pd.DataFrame, struct: pd.DataFrame) -> pd.DataFrame:
    """§6.1.5 기간별 횡단면 z-score → §6.1.7 섹션 가중합성.
       · CHANGE = 1 − similarity, 지표별로 (기간 × 섹션) 횡단면 z, 동일가중 평균
       · 섹션 가중 합성. 결측 섹션 가중치는 나머지에 비례 재배분
       · STRUCT_FLAG(합병·분할·영업양수도·지주전환) 종목-기간은 D1 결측(0 아님) 처리
       반환 (PIT frame): corp_code, event_date(=rcept_dt), knowledge_date(=rcept_dt+1영업일),
             CH_S_MDA..CH_S_ALL, CHANGE_composite, D1_SCORE(= −z(CHANGE_composite)), STRUCT_FLAG"""

def build_struct_flags(dis: pd.DataFrame) -> pd.DataFrame:
    """§6.1.6. 공시목록 report_nm 정규식으로 합병/분할/영업양수도/지주회사전환 탐지.
       반환 (PIT frame): corp_code, event_date, knowledge_date, STRUCT_FLAG(=1)"""

def attach_d1(P: pd.DataFrame, d1: pd.DataFrame) -> pd.DataFrame:
    """PIT.register + asof_join(by='corp_code', left_time='asof'). 결합 후 결측 컬럼 채움.
       D1_MISSING = 1 (상장 24개월 미만 / STRUCT_FLAG / 파싱 실패) — §3.3, §6.5"""

def report_d1_sign_check(P: pd.DataFrame) -> dict:
    """§9.2-(4) D1 부호 검증. 한국 데이터에서 '변화=악재'가 성립하는가.
       CHANGE_composite 5분위별 forward 1Q 수익률 표 + 단조성/부호 판정.
       역전이면 그 사실을 그대로 보고 (부호를 뒤집지 말 것 §9.3-5)."""
```

---

### AGENT-5 — `32_axis_b_d2.py` (D2 §6.2)

```python
D2_ITEMS = [("ACCRUAL",-1), ("NOA",-1), ("AR_DIVERGE",-1),
            ("INV_DIVERGE",-1), ("CFO_NI_GAP",+1), ("SHARE_GROWTH",-1)]   # (컬럼, 방향)

def build_d2_panel(fin: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """분기 프레임에서 6개 지표를 만든다. (월/분기 패널에서 만들면 반복값 때문에 diff 가 깨진다)
       ACCRUAL      = (net_income_ttm − cfo_ttm) / 평균총자산
       NOA          = 순영업자산 / 전기말 총자산
                      순영업자산 = (자산총계 − 현금) − (부채총계 − 총차입금).
                      총차입금 계정이 없으면 (자산−현금) − 부채 로 근사하고 그 사실을 로그로 남긴다.
       AR_DIVERGE   = YoY 매출채권 증가율 − YoY 매출액 증가율
       INV_DIVERGE  = YoY 재고자산 증가율 − YoY 매출액 증가율
       CFO_NI_GAP   = (cfo_ttm − net_income_ttm) / 총자산
       SHARE_GROWTH = TTM 주식수 증가율
       분모 0/음수 → 해당 지표 최하위 순위로 강제 배정(역수 부호 반전 방지)
       반환 (PIT frame): corp_code, event_date(=period_end), knowledge_date, + 6개 컬럼"""

def attach_d2(P: pd.DataFrame, d2: pd.DataFrame) -> pd.DataFrame:
    """asof_join 후 §6.2 합성: 섹터 중립 z-score(cell 기준), 상하위 1% 윈저라이징, 동일가중 평균.
       방향은 D2_ITEMS 의 부호로 통일(높을수록 우수). D2_SCORE = z(합성값)."""

def report_d2_coverage(P: pd.DataFrame) -> dict:
    """지표별 결측률 표 (GATE_6 근거)."""
```

---

### AGENT-6 — `33_axis_b_d3.py` (D3 §6.3 + 배제 플래그 §6.4)

```python
D3_EVENTS = [("NF_RND_EMP","연구개발 인력 순증","기술·제조"), ... 10개 전부]
EXCL_DEFS = [("EX_RELATED","특수관계자 매입/매출 비중 상승 상위 20%"), ... 8개 전부]

def extract_hardfacts(T: pd.DataFrame, fin: pd.DataFrame, emp: pd.DataFrame,
                      dis: pd.DataFrame, notes: pd.DataFrame) -> pd.DataFrame:
    """§6.3 완료형 사실만. 전망·계획·의지·기대·예정은 전부 제외.
       규칙 기반 파싱 + 정규식 + 경량 ML 만 (LLM 금지).
       반환 (PIT frame): corp_code, event_date, knowledge_date, NF_*(0/1), DELTA_NONFIN(int)"""

def build_exclusion_flags(fin: pd.DataFrame, dis: pd.DataFrame, audit: pd.DataFrame,
                          T: pd.DataFrame) -> pd.DataFrame:
    """§6.4 하드 제외. 반환 (PIT frame): corp_code, event_date, knowledge_date, EX_*(0/1)"""

def attach_d3(P: pd.DataFrame, d3: pd.DataFrame, excl: pd.DataFrame) -> pd.DataFrame:
    """D3_SCORE = z(DELTA_NONFIN).  ★ DELTA_NONFIN > 0 을 편입조건으로 쓰지 말 것 (v1.0 폐기 규칙).
       EXCLUDE = 1 if any EX_* else 0."""

def report_d3_sector(P: pd.DataFrame) -> None:
    """§9.2-(9) 근거. 섹터별 D3 발화율 표 — v1.0 섹터 편향이 해소됐는지 확인용."""
def report_exclusion(P: pd.DataFrame) -> None:
    """배제 플래그별 발동 건수·비율 표."""
```

---

### AGENT-7 — `50_ablation.py` (§8.2 어블레이션 11종 + §8.3 BH-FDR)

```python
ABLATIONS = [("A1","ΔTONE_resid 단독","축 A 순기여"), ("A2","ΔTONE 직교화 미적용 단독", ...),
             ("B1",...), ("B2",...), ("B3",...), ("B4",...), ("B5",...),
             ("F1","풀버전",...), ("F2","풀버전 − D1",...), ("F3","풀버전 − D2",...),
             ("F4","v1.0 재현: ΔTONE + ΔNONFIN>0 하드게이트 + 배제","v2.0 개선효과 정량화")]
ABLATION_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

def run_ablations(P, rebals, uni, sec, run_fn) -> pd.DataFrame:
    """11개 실험 전부 실행. 각 실험: 신호 컬럼 조합 → FINAL 재조립 → run_fn 호출.
       각 실험 기록: CAGR, MDD, Sharpe, Sortino, IC, IC-IR, 회전율, 평균보유종목수,
                     승률, 평균 편입가능 종목수, 비용 전/후(§8.1) 두 벌.
       F4 는 반드시 실행한다(수치 없는 개선 주장 금지).
       B4 는 U-1000 전체에 배제플래그만 적용한 팔."""

def report_ablation_table() -> None:
    """§9.2-(6). 비용 전/후 병기 표."""

def report_f4_vs_f1() -> None:
    """§9.2-(7). v1.0(F4) 대비 v2.0(F1) 개선폭 정량 비교표."""

def apply_bh_fdr(q: float = 0.10) -> pd.DataFrame:
    """§8.3. 11개 실험을 하나의 검정 패밀리로 묶어 BH-FDR 보정.
       p-value 는 월(분기)초과수익 시계열의 HAC t → 양측 p.
       §9.2-(8) 보정 후 유의성 판정표 출력."""
```
- `run_fn(P, label=..., apply_costs=True, rebals_override=None, top_n=None, weighting="equal")`
  는 `41_backtest.py` 가 제공한다(§6 참조).
- 신호 재조립은 `40_score.py` 의 `assemble_final(P, use_axes=..., use_excl=..., v1_hardgate=False)` 를 쓴다.

---

### AGENT-8 — `51_robust.py` (§8.4 강건성)

```python
ROBUST_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

def R_subperiod(bt)                    # 전반부/후반부
def R_size_quartile(P, bt)             # 시총 사분위별 성과 분해
def R_sector(P, bt, sec)               # ★필수 — 섹터별 성과 분해 (v1.0 섹터편향 해소 확인)
def R_rebal_shift(P, rebals, run_fn)   # 리밸런싱 ±5거래일 이동
def R_holdings(P, run_fn)              # 보유종목수 20/30/40
def R_struct(P, run_fn)                # STRUCT_FLAG 포함/제외
def R_ircouncil(P, rep, run_fn)        # 한국IR협의회 기업의뢰 리포트 포함/제외
def R_d1_metrics(P, run_fn)            # D1 유사도 지표 4종 각각 단독
def R_d1_weights(P, run_fn)            # D1 섹션 가중치 균등배분 비교
def R_bottom_group(P)                  # §7.3 BOTTOM 그룹 forward 1Q/2Q/4Q + 비대칭 판정
def R_causal_order(P, rep, doc)        # §7.1 인과 순서 점검 (리포트-공시 시차 분포 + 두 축 상관)
def report_robustness() -> None        # §9.2-(10)
```
- 각 검사는 `_rrec(rid, name, passed, detail, metrics)` 로 기록(모듈 내부 헬퍼, 이름 충돌 주의).
- 판정 불가는 `None` 으로 기록하고 사유를 남긴다. **예외로 죽지 않는다.**
- 자동으로 파라미터를 바꾸지 않는다. 보고만 한다.

---

### AGENT-9 — `60_report.py` (§9.2 최종 산출물 11종)

```python
def report_performance(bt, bench, label="") -> None      # 성과 검증표(비용 전/후 병기)
def report_correlation_matrix(P) -> None                 # §6.6 D1/D2/D3 기간별 상관행렬
def report_axes_correlation(P) -> None                   # §7.1 ΔTONE_resid × DART_SCORE 상관
def report_universe_attrition(uni) -> None               # 유니버스 감쇠
def report_interpretation(P) -> None                     # 해석 참조표
def diagnostic_card(P, bt, sec, top_n=5) -> None         # 종목별 진단 카드
def report_dataflow_map() -> None                        # 거시 데이터 흐름 지도
def report_final_deliverables(ctx) -> None
    """§9.2 의 1~11 을 순서대로 '어디에 출력됐는지' 목차로 정리해 마지막에 한 번 더 보여준다."""
def report_kill_criteria(ctx) -> dict
    """§9.3 사전등록 폐기 조건 5개를 실측치로 판정하는 표. 사후 조정 금지 문구 포함."""
def benchmark_returns(rebals) -> Dict[str, pd.Series]    # KOSPI/KOSDAQ 분기 수익률
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict # 분기 기준 연율화(×4)
```
> ⚠ `perf_stats` 는 **분기** 시계열이다. 연율화 계수는 12 가 아니라 **4**.

---

### AGENT-10 — `70_contracts.py` (계약 자동검정)

`run_contract_tests(strict=True) -> bool`, `CONTRACT_RESULTS: List[dict]`.
검정할 계약(각각 실제 코드를 돌려서 확인, 주석 신뢰 금지):
- **A1 PIT**: `PITStore.get` as_of 절단 · PIT 컬럼 없는 등록 거부
- **A2 생존자편향**: 폐지종목 당시 포함 · 폐지 후 제외 · 미래 상장 배제
- **A3 U-1000**: 하위 1000 랭크가 PIT 시총으로 계산 · 현재 랭크 소급 금지 · 유동성 하한 · 제외종목
- **A4 D1 페어링**: 전년 동기 동일 유형만 페어링. 직전분기 페어가 생기면 실패
- **A5 정규화**: 숫자/날짜/사명만 바뀐 문서 두 개의 유사도가 1.0 에 근접(≥0.98)해야 한다
  (= 가짜 변화가 제거됨). 실제 문장이 바뀐 문서는 유의하게 낮아야 한다
- **A6 횡단면 z**: 기간별 z 평균≈0 · ±inf 무해화 · 표본부족 NaN
- **A7 D1 가중치 재배분**: 결측 섹션이 있어도 가중치 합이 1
- **A8 배제 하드**: EXCLUDE=1 이면 FINAL_SCORE 무관하게 편입 0건
- **A9 ΔNONFIN 게이트 폐기**: `DELTA_NONFIN==0` 인 종목이 편입 가능해야 한다 (v1.0 규칙 부활 방지)
- **A10 축 A 결측 생존**: 리포트 없는 종목이 DART_SCORE 만으로 편입 가능해야 한다 (§7.2)
- **A11 D1 가중치 재배분 시 D1 결측**: D1 결측이면 가중치가 D2·D3 에 비례 재배분되고
  종목이 탈락하지 않아야 한다 (§6.5)
- **A12 직교화 필수**: `attach_axis_a` 소스에 통제변수 7종이 전부 등장하는지 소스 검사
- **A13 튜닝 금지**: `assemble_final`/`d1_composite` 소스에 `minimize|GridSearch|optimize\.|curve_fit` 없음
- **A14 결정성**: 같은 시드 · 입력 순서 무관
- **A15 시점 규약**: `knowledge_date >= event_date` 강제, DART 는 rcept_dt+1영업일
- **A16 종목코드**: 2024 영숫자 티커
- **A17 분기 연율화**: `perf_stats` 가 ×4 로 연율화하는지 (분기 4개 = 1년)
- **A18 LLM 금지**: 전체 소스에 `openai|anthropic|gpt-|claude-|generativeai|/v1/chat/completions` 부재

---

### AGENT-11 — `75_rehearsal.py` (실경로 리허설)

`run_rehearsal(strict=True) -> bool`, `REHEARSAL_RESULTS: List[dict]`, `_arh(name, fn, ...)`.
`build/75_rehearsal.py` 의 `_FixtureNet` 패턴을 **그대로 계승**하되 ARC 용 픽스처를 추가:
- DART `document.xml` ZIP: 사업보고서 목차(§6.1.2 7개 섹션 표제)가 실제로 들어있는 EUC-KR XML.
  **두 해치(전년/당년)를 만들어 페어링·유사도까지 실제로 돌린다.**
- 사업보고서 안에 특수관계자·우발부채·소송·감사의견 문단, 직원현황 표, 연구개발비 표 포함
- `stockTotqySttus`(주식총수), `accnutAdtorNmNdAdtOpinion`(감사의견) JSON 픽스처
- 한경/네이버 리스트 + PDF (기존 픽스처 재사용)
- 모드 4종(ok / empty / broken / missingcol) 전부에서 예외 없이 통과해야 한다
- ARC 함수 전부를 실물 실행: `fetch_arc_documents → arc_doc_pairs → d1_similarity → d1_composite`,
  `build_d2_panel`, `extract_hardfacts`, `build_exclusion_flags`,
  `build_tone_training → fit_tone_expanding → score_tone_reports → aggregate_tone`

---

### AGENT-12 — `80_selftest.py` (합성 스모크)

`make_arc_synthetic(...) -> dict`, `run_selftest(full_chain=False) -> bool`.
- 합성 데이터에 **진짜 알파를 심는다**: `quality[i]` 가 높으면 ① dTONE↑ ② CHANGE↓ ③ D2 지표 우수
  ④ 미래수익↑. 그래야 백테스트 하네스가 신호에 반응하는지 검증된다.
- 상장/폐지 종목 포함(생존자편향 검증), 축 A 결측 종목 20% 포함(§7.2 생존 검증),
  D1 결측 종목 15% 포함(§6.5 가중치 재배분 검증), 배제플래그 발동 종목 10% 포함.
- `full_chain=True` 면 성과검증 → 어블레이션 11종 → BH-FDR → 강건성 → 해석표까지 전부 출력.
- 합성 수치는 해석 금지임을 배너로 명시.
- 반환 dict 키: `sec, px, fin, shares, emp, dis, audit, reports, links, doc_tokens, doc_pairs, rebals`

---

## 6. spine 이 제공하는 하류 인터페이스 (AGENT 들이 호출)

```python
# 40_score.py
assemble_final(P, use_axes=("A","D1","D2","D3"), use_excl=True,
               v1_hardgate=False, d1_metric=None, d1_equal_weights=False) -> pd.DataFrame
    """지정된 축만으로 DART_SCORE / FINAL_SCORE / FINAL_RANK 를 재조립해 돌려준다.
       원본 P 를 변형하지 않는다(copy). 어블레이션은 전부 이 함수를 통과한다.
       use_axes 에 "A" 가 없으면 FINAL = z(DART_SCORE) 단독.
       v1_hardgate=True 면 DELTA_NONFIN>0 을 편입 조건으로 강제(F4 재현 전용)."""
ARC_W_D1, ARC_W_D2, ARC_W_D3 = 0.40, 0.40, 0.20     # 사전등록. 튜닝 금지
ARC_W_AXIS_A, ARC_W_AXIS_B  = 0.50, 0.50

# 41_backtest.py
run_backtest(P, rebals, uni, sec, signal_col="FINAL_RANK", apply_costs=True,
             label="ARC", top_n=None, weighting="equal") -> dict
    """반환 {"returns": DataFrame[asof, ret, ret_gross, n, turnover, cost, equity],
             "holdings": DataFrame[asof, code, weight, ret, signal],
             "label": str, "eligible": DataFrame[asof, n_elig]}"""
ARC_TOP_N_DEFAULT = 30       ARC_TOP_N_MIN, ARC_TOP_N_MAX = 20, 40
```

---

## 7. 스타일

- 파일 머리에 `╔══ ... ══╗` 박스 주석으로 **무엇을·왜** 를 한국어로 쓴다.
- 함정을 발견하면 `# ★` 주석으로 **왜 그렇게 짰는지**를 남긴다 (기존 코드의 최대 미덕).
- 표 출력은 전부 `LOG.table`. `print` 대신 `_safe_print`.
- 큰 루프는 벡터화. 종목별 파이썬 루프 금지. 30만 행에서 `iterrows` 금지 (`zip`/`itertuples` 사용).
- 메모리: 큰 프레임은 `downcast(df)`. PDF/원문 바이트는 청크 소비 후 즉시 버린다.
