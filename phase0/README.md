# PHASE 0 — 축 A-Δ 재측정 v1.3

**이 실행의 유일한 질문: 분기마다 겸직 링크가 실제로 몇 개나 생기고 사라지는가?**

축 A 본체(A-1 커버리지 · A-2 식별자 · A-3 그래프 확대효과)는 이전 실행에서 확인이 끝났다.
여기서 다시 재지 않는다. 룩어헤드 오염으로 무효가 된 **A-Δ 만** 고쳐서 다시 잰다.

측정 로직(PIT 필터·그래프·전이) 자체는 검증이 끝난 상태로 안정적이다. 이번 개정은 실사용
중 발견된 **pykrx import 크래시**를 근본 수정하고, 그 김에 캐시·수집 계층을 상당히
견고하게 다시 짰다 — 아래 "이번 개정" 절 참조.

| 파일 | 용도 |
|---|---|
| `axis_a_delta_v13.py` | **측정 본체.** JupyterLab 셀 하나에 붙여넣거나 `python axis_a_delta_v13.py` |
| `verify_logic.py` | 순수 로직 검증 171건 — 네트워크·자격증명·pandas 불필요 |
| `verify_endtoend.py` | `main()` 전 구간 드라이런 113건 — 시장·DART·상장목록 폴백을 바깥에서 가짜로 주입 (pandas 필요) |

```bash
python phase0/verify_logic.py && python phase0/verify_endtoend.py
```

---

## 이번 개정 — pykrx 크래시 근본 수정 + 엔지니어링 강화

### 계기: `import pykrx` 자체가 죽는다

```
KRX 로그인 시도... 로그인 ID: xxxxx
JSONDecodeError: Expecting value: line 13 column 1 (char 25)
  ...
  File ".../pykrx/website/comm/webio.py", line 12, in <module>
    _session = build_krx_session()
  File ".../pykrx/website/comm/auth.py", line 153, in login_krx
    data = resp.json()
```

pykrx 1.2.8 은 `from pykrx import stock` 을 실행하는 순간 `website/comm/webio.py` 모듈
최상단에서 KRX 로그인을 **즉시 실행**한다. 그 로그인 함수(`login_krx`)는 응답을
`resp.json()` 으로 파싱하는데 **try/except 가 없다** — KRX 가 로그인 실패·차단·점검
페이지(HTML)를 돌려주면 `JSONDecodeError` 가 **import 시점에** 그대로 터진다. 즉
"pykrx 를 import 만 해도 프로세스 전체가 죽을 수 있다"는 게 실제 동작이다. 이 실패
시그니처는 이 저장소의 `build/10_ingest_universe.py` 의 `KRXGate` 주석에 이미 기록돼
있던 바로 그 pykrx 결함이다.

### 수정 5건

| # | 문제 | 수정 |
|---|---|---|
| **①** | pykrx import 자체가 예외로 죽는다 | import 를 넓은 `except` 로 감싼다. 1차: 자격증명 포함 시도. 실패하면 자격증명을 비우고 2차 시도(로그인 자체를 안 하므로 대개 성공). 둘 다 실패해도 `PYKRX_AVAILABLE=False` 로 남기고 **폴백 경로로 계속 진행** — 죽지 않는다. import 이후의 모든 `stock.*` 호출도 `pykrx_call()` 래퍼를 거쳐 예외를 절대 밖으로 흘리지 않는다 |
| ② | pykrx 가 죽으면 시가총액을 얻을 방법이 없었다 | **KRX Open API** 를 시총 1순위 소스로 추가(공식 API, `data-dbg.krx.co.kr`). pykrx 는 2순위. 둘 다 안 되는 날짜만 UNVERIFIED |
| ③ | pykrx 가 죽으면 상장종목 목록도 얻을 방법이 없었다 | pykrx 티커목록 실패 시 **DART corpCode + FDR(GitHub 캐시) + KIND 상장법인목록** 병합으로 point-in-time 생존자편향 없는 유니버스를 구성한다 |
| ④ | 캐시가 tar.gz 일괄 백업/복원이라 크고, 실행 종료까지 드라이브에 안 오른다 | 공용/전용 인덱스 이중탐색(로컬→드라이브) 구조로 교체. `dart_corpcode`·`security_master` 는 이 저장소의 다른 전략(`build/10_ingest_universe.py`)과 **동일한 공용 테이블명**으로 저장해 캐시를 상호 재활용한다. 신규 수집 원본은 **스냅샷 단위로 즉시 드라이브 증분 동기화** — 실행 종료를 기다리지 않는다 |
| ⑤ | 호출예산의 중도정지 임계(12,000)가 실 필요량(~11,078)보다 여유가 거의 없어 정상적인 콜드런도 중간에 멎을 수 있었다 | 그 임의 임계를 없앴다. 유일한 하드 한도는 DART 실 일일한도(안전마진 포함, 19,500) 뿐이고, 실시간 소진의 최종 권위는 DART 가 돌려주는 `status=020` 응답 자체다 |

부수적으로: 고정 지연을 **적응형**(성공 스트릭엔 가속, 실패 즉시 감속)으로 바꿨고, 동일
(소스,날짜) 재조회를 실행 내 메모이제이션으로 제거했고, `to_code6` 가 2024+ 도입된
영숫자 신형 종목코드(`09701K` 형식)를 더 이상 숫자만 남겨 망가뜨리지 않도록 고쳤다.

### 검증

```
python phase0/verify_logic.py       # 171건 — pykrx 크래시를 실제로 재현해서 검증한다
python phase0/verify_endtoend.py    # 113건 — pykrx 완전 사망 시나리오의 전 구간 완주 포함
```

`verify_logic.py` 의 pykrx 방탄 테스트는 mock 이 아니라, **import 시점에 실제 결함처럼
예외를 던지는 가짜 pykrx 패키지**를 만들어 `sys.path` 에 주입하고 진짜 `import` 문을
태워서 검증한다. `verify_endtoend.py` [17]은 `PYKRX_AVAILABLE=False` 상태에서 KRX Open
API + 다중소스 유니버스 폴백만으로 4개 스냅샷과 3개 전이가 전부 정상 완주되는지를
end-to-end 로 확인한다 — 이번에 보고된 크래시와 동일한 상태를 재현한 테스트다.

### 왜 멀티프로세싱이 아니라 스레드인가

DART/KRX 호출은 전부 네트워크 왕복이 대부분의 시간을 차지하는 I/O 바운드 작업이라
GIL 이 병목이 되지 않는다. 멀티프로세싱은 여기서 처리량을 늘려주지 못하고, 오히려
프로세스 간 호출예산·서킷브레이커 상태 공유만 복잡해진다(파일 락이나
`multiprocessing.Manager` 가 필요해진다). 대신 적응형 지연으로 속도를 관리한다 —
성공이 이어지면 점점 빨라지고, 실패 신호가 오면 즉시 늦춘다. 벡터화도 마찬가지 이유로
시가총액 조회(이미 pandas 로 벡터화된 벌크 조회) 이상으로는 확장하지 않았다 — 그래프
구성 루프는 스냅샷당 레코드 수만 건 규모라 파이썬 반복의 오버헤드가 네트워크 I/O(스냅샷당
최대 수천 콜, 초 단위)에 비해 무시할 수준이고, 여기를 벡터화해도 병목은 옮겨가지 않는다.

### 하지 않은 것 — 스몰캡 백테스트 비교

이 파일의 측정 대상은 이미 시총 하위 1,000종목이고, 백테스트·팩터·시그널·수익률
연산은 `P0_NO_STRATEGY` 로 이 실행 범위 밖에 명시적으로 못박혀 있다 — 축 A 본체가
확인된 뒤 전략 연산을 절대 하지 않는다는 원 설계와 정면으로 충돌하기 때문에 구현하지
않았다. 필요하면 이 저장소의 `strategies/tcd_v2_*.py` 계열처럼 별도 전략 파일로
만드는 것이 맞다. `known_limitations` 에 이 판단을 그대로 기록해 둔다.

---

## 실행 전 채울 것

`axis_a_delta_v13.py` 최상단 블록만 채우면 된다.

| 값 | 발급처 | 비고 |
|---|---|---|
| `DART_API_KEY` | https://opendart.fss.or.kr/ → 인증키 신청 | **필수.** 즉시 발급·무료. 일 20,000건 |
| `KRX_ID` / `KRX_PW` | http://data.krx.co.kr/ → 회원가입 | 선택. 비워도 동작(pykrx 비인증 경로) |
| `KRX_OPENAPI_KEY` | https://data.krx.co.kr/ → Open API 메뉴 | 선택이지만 강력 추천. **엔드포인트별 이용신청**이 따로 필요하고 승인에 하루 정도 걸린다 — 키만 있다고 바로 되지 않는다 |
| `PROJECT_ROOT` | 로컬 SSD 경로 | `/content` 계열이면 **예외 발생 후 중단** |
| `GDRIVE_ROOT` | 마운트된 드라이브 경로 | 공용/전용 인덱스가 이 아래에 산다. 비우면 로컬 전용으로 동작(측정은 정상 진행) |
| `N_WORKERS` | 정수, 기본 4 | I/O 바운드라 4~8 권장. 과하게 올리면 차단(429)만 늘어난다 |

`CONFIRM_LARGE_COLLECTION` 은 기본 `False`. 실제 신규 호출이 5,000건을 넘으면 스크립트가
**수집에 진입하지 않고** 내역만 출력하고 멈춘다. 확인 후 `True` 로 바꿔 다시 실행한다.

실행 시작 직후 "데이터소스 가용성" 절에서 pykrx / KRX Open API / FinanceDataReader /
KRX ID·PW 각각이 실제로 쓸 수 있는 상태인지 미리 보고한다 — pykrx 와 KRX Open API 가
둘 다 안 되면 시가총액을 전혀 얻을 수 없다는 경고가 뜬다.

---

## PIT 정합성 — as_of 는 실행일이 아니다

`as_of` 는 **관측시점 정렬(A)** 을 채택했다 — "그 정보를 알 수 있게 된 시점".

| 스냅샷 | 기준일 | 보고서 | `as_of` (법정 제출기한) |
|---|---|---|---|
| S1 | 2025-06-30 | 2025/11012 반기 | 2025-08-14 |
| S2 | 2025-09-30 | 2025/11014 3분기 | 2025-11-14 |
| S3 | 2025-12-31 → **2025-12-30**(휴장일 스냅) | 2025/11011 사업 | 2026-03-31 |
| S4 | 2026-03-31 | 2026/11013 1분기 | 2026-05-15 |

이 값들은 코드에 FROZEN 되어 있고, 실행 시 `결산기준일 + 45일(분기·반기) / 90일(사업)`
계산과 대조한다. 어긋나면 실행되지 않는다.

**캐시는 API 원본 응답을 저장하고, PIT 필터는 읽은 뒤에 건다.** 봉투(envelope) 형태로
저장된 예전 캐시도 그대로 재사용된다 — 파일에 `as_of` 가 박혀 있어도 그 필드는 읽지
않고 `rcept_no` 로 다시 필터링한다.

필터 후 최종접수일이 해당 `as_of` 를 넘으면(필터가 걸리지 않았다는 뜻) 그 자리에서
예외를 던진다. 스냅샷별 PIT 폐기 건수(룩어헤드/접수번호불량 구분)를 반드시 로그와
`diag_pit_dropped_delta.csv` 에 출력한다 — 4개 스냅샷 모두 룩어헤드 폐기가 0건이면
필터가 무력화됐다는 신호다.

---

## 측정 내용

- **노드** = 해당 스냅샷 거래일의 시총>0 상장사 전체 (pykrx 1순위, 안 되면 다중소스 폴백)
- **엣지** = (성명, 출생년월) 동일 인물이 두 종목에 동시 임원 등재
  - 출생년월 결측 레코드는 엣지 생성에서 **제외**(보간하지 않음)
- **측정 대상** = 각 스냅샷의 시총 **하위 1,000종목**
- **상대 노드가 측정 대상 밖이어도 엣지는 유지** (외부 링크가 대다수였다)
- **전이** S1→S2, S2→S3, S3→S4 각각에 대해 하위 1,000종목 교집합 기준
  `edge_born` / `edge_died` 를 **분리해서** 산출한다. 합산하지 않는다.

### 판정 게이트

| 게이트 | 기준 | 임계 |
|---|---|---|
| AΔ-1 | 분기당 `edge_born ≥ 1` 인 종목 비율 (전이 평균) | ≥ 0.05 |
| AΔ-2 | 분기당 전체 `edge_born` 총건수 중앙값 | ≥ 50 |
| AΔ-3 | 4개 스냅샷 모두 그래프 구성 성공 | 4/4 |

> **AΔ-1=0.05, AΔ-2=50, A-5=600 은 경험적 근거 없이 설정된 임계값이다.**
> 게이트 미달을 "전략 불가"로 읽으면 안 된다. 실측값을 근거로 임계를 재설정하는 것은
> 다음 단계의 판단이다. 이번 실행 중 임계 변경은 금지되어 있으며, 임계값 SHA-256 이
> 코드에 고정되어 있어 바꾸면 실행이 중단된다(`P0_NO_THRESHOLD_EDIT`).

### 성공 조건 (게이트 통과 여부와 무관)

1. 4개 스냅샷 각각의 PIT 폐기 건수가 0이 아니고, 최종접수일이 해당 `as_of` 이내
2. 전이 3개의 `edge_born` / `edge_died` 가 산출됨

수치가 낮게 나와도 성공이다. 낮다는 사실을 정확히 아는 것이 이 단계의 목적이다.

---

## 산출물 (`{PROJECT_ROOT}/reports/`)

| 파일 | 내용 |
|---|---|
| `phase0_verdict_v13.json` / `.csv` | 판정표. `data_sources` 블록에 pykrx/KRX Open API/FDR 가용성과 pykrx import 시도 이력이 남는다 |
| `phase0_summary_v13.md` | 요약 (해석·전략 제안 없음). 스냅샷별 `mcap_source`/`universe_source` 포함 |
| `diag_edge_events.csv` | 전이별 종목 단위 born/died |
| `diag_pit_dropped_delta.csv` | **스냅샷별 PIT 폐기 레코드의 접수일자 분포** — PIT 필터가 실제로 작동했다는 증거 |
| `cache_inventory.json` | 캐시 인벤토리, 드라이브 복원분, 실제 신규 호출 수 |
| `resume_todo.json` | 일일한도(`DART status=020`)로 중단됐을 때만 생성 |
| `run_log.txt` | 전체 로그 |

드라이브 공용 인덱스(`{GDRIVE_ROOT}/_shared/`)에는 `table/dart_corpcode.csv`,
`table/security_master.csv`, `blob/dart/exctv/{corp}/{year}_{reprt}.json`, 그리고
append-only 저널 `index/journal.jsonl` 이 쌓인다. 전용 네임스페이스는
`{GDRIVE_ROOT}/phase0_axis_a_delta/` 다.

---

## 계약

| ID | 강제 방식 |
|---|---|
| `P0_LOCAL_ROOT_ONLY` | `/content`·`/gdrive` 계열 또는 Colab 런타임 감지 시 예외. WAIVED 없음 |
| `P0_PIT_STRICT_DELTA` | `as_of` == 실행일이면 예외. 필터 후 최종접수일 > `as_of` 이면 예외 |
| `P0_EMPTY_UNIVERSE_GUARD` | 시총>0 100 미만이면 수집 진입 없이 `UNVERIFIED` |
| `P0_CACHE_FIRST` | 인벤토리 출력 후, 실제 신규 호출 5,000건 초과 시 수집 전 정지 |
| `P0_NO_STRATEGY` | 팩터·시그널·수익률·백테스트 연산 없음 |
| `P0_GRAPH_FULL_MEASURE_SUB` | 그래프는 전 상장사, 측정은 하위 1,000종목 |
| `P0_FAIL_LOUD` | 결측·폐기는 그대로 기록. 보간·추정 없음 |
| `P0_NO_THRESHOLD_EDIT` | 임계값 SHA-256 고정. 불일치 시 예외 |
| `P0_LIVE_ONLY` | 합성 데이터 경로가 코드에 없다. `DART_API_KEY` 없으면 예외 |
| `NO_KNOWN_DEAD_CALL` | `get_index_portfolio_deposit_file` 을 호출하면 터지도록 교체 |
| `P0_DEFENSIVE_PYKRX` | pykrx import·호출은 어떤 예외에도 프로세스를 죽이지 않는다 |
| `P0_MULTI_SOURCE_UNIVERSE` | 상장목록은 pykrx 단일 의존이 아니라 DART/FDR/KIND 다중소스 병합 |

## 범위 밖 (`SKIPPED_BY_SCOPE`)

- 축 A 본체 재측정 — 이전 실행 확인 완료
- 축 B (BigQuery) · 축 C (국민연금)
- 팩터·시그널·수익률·**백테스트** 연산 — 전면 금지 (스몰캡 비교 백테스트 요청 포함)
- 게이트 통과를 위한 임계 조정 — 금지

---

## 기술 규약

- 단일 코드 셀로 통합. 진단용 셀을 쪼개지 않는다
- **pykrx 는 KRX 자격증명을 `os.environ` 에 넣은 뒤에만, 방탄 처리된 경로로만 import**
  한다. import 자체가 실패해도(실제로 흔하다) 프로세스는 죽지 않고 `PYKRX_AVAILABLE`
  플래그와 함께 폴백 경로로 넘어간다
- 워커 4(상한 8), 요청 간 적응형 지연(0.12~1.2초, 성공 스트릭엔 가속·실패 즉시 감속),
  지수 백오프(2/4/8/16초)
- 연속 실패 10회 → 서킷 브레이커 → 60초 대기 → 3회 반복 시 중단
- 호출 예산 일일 19,500(DART 실 한도 20,000 대비 안전마진). 실시간 소진의 최종 권위는
  DART `status=020` 응답. 도달 시 `resume_todo.json` 저장 후 중단
  (같은 날 이전 실행분까지 `cache/state/call_budget_YYYYMMDD.json` 에 누적)
- ENOSPC 시 로컬은 즉시 실패, 드라이브는 경고 후 계속(드라이브는 백업 편의이지 진실의
  원천이 아니다). 포맷 재시도 없음
