# PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.1

명령서 v1.1 구현체. 파일 하나로 완결된다 (§8.6 단일 셀 요구).

```
phase0/phase0_altdata_3axis_v11.py
```

Colab / JupyterLab 한 셀에 통째로 붙여넣거나 `python phase0_altdata_3axis_v11.py` 로 실행한다.

---

## 1. 실행

```bash
# ① 로직 검증 — 네트워크·키 불필요. 30개 자가검정 + 계약 10건 검사. 약 20초.
PHASE0_PROJECT_ROOT=/home/<사용자>/phase0 PHASE0_RUN_MODE=SELFTEST \
    python3 phase0/phase0_altdata_3axis_v11.py

# ② 실측
export PHASE0_PROJECT_ROOT=/home/<사용자>/phase0   # ★ /content 는 계약 FAIL 로 중단된다
export DART_API_KEY=...                            # 축 A / A-Δ
export DATA_GO_KR_KEY=...                          # 축 C (일반 인증키 Decoding)
export GOOGLE_APPLICATION_CREDENTIALS=...          # 축 B (또는 gcloud auth application-default login)
export GCP_PROJECT=...                             # 축 B 과금 프로젝트
PHASE0_RUN_MODE=FULL python3 phase0/phase0_altdata_3axis_v11.py
```

키 발급 절차와 소요시간은 파일 상단 인증정보 블록의 주석에 URL과 함께 적혀 있다.
`pip install pykrx finance-datareader google-cloud-bigquery` — 없으면 해당 축만 시끄럽게 실패한다.

**SELFTEST 산출물은 `cache/reports_selftest/` 에 따로 쓰고 `mode=SELFTEST_SYNTHETIC` 으로 낙인찍는다.**
합성 결과를 실측 판정으로 오해할 수 없게 만들기 위한 것이다.

---

## 2. 산출물 (§9)

`<PROJECT_ROOT>/cache/reports/` 아래:

| 파일 | 내용 |
|---|---|
| `phase0_verdict_v11.json` / `.csv` | 축별 판정표. `GO / STOP / UNVERIFIED / BLOCKED_PREREQ / PENDING_MANUAL` |
| `phase0_summary_v11.md` | 축별 판정과 근거 수치만 (해석·전략 제안 없음) |
| `diag_corpcode_miss.csv` | 매핑 실패 종목 + 6분류 + 보조원인 |
| `diag_pit_dropped.csv` | PIT 폐기 레코드의 접수년월 분포 |
| `diag_edge_events.csv` | 분기 전이별 종목당 생성/소멸 엣지 |
| `diag_C_probes.csv` | 축 C 프로브 4회의 HTTP 상태·resultCode·resultMsg 원문 |
| `manual_check_A_coexec_links.csv` | 겸직 링크 200건 (A-4, 사람 판정 대기) |
| `manual_check_C_workplace_match.csv` | 사업장 매칭 100건 (C-5, 사람 판정 대기) |
| `contracts_v11.csv` | 계약 10건 검사 결과 |
| `run_log.txt` | 전체 로그 |

---

## 3. v1.0 대비 달라진 것

| # | v1.0 에서 확인된 사실 | v1.1 구현 |
|---|---|---|
| 1 | 임원현황 API 존재 확인 | 선행 확인 없이 바로 수집 진입 |
| 2 | 보고서 코드 11013 사용 확인 | 분기 스냅샷 4개 신규 도입 (§4) |
| 3 | 출생년월 결측 0.47% | A-2 게이트 유지, 결측 행은 엣지 형성에서 제외하고 계상 |
| 4 | 겸직 링크가 얇았음 | **그래프를 전 상장사로 확대.** 유니버스 밖 상대와의 링크를 유지하고 내부/외부로 분리 보고 |
| 5 | 매핑 실패 86종목 | 6분류 자동 진단 + ⑥원인불명 20종목 초과 시 축 판정 보류 |
| 6 | PIT 폐기 574건 | STOP 사유에서 제외. 접수년월 분포를 진단 산출물로 남김 |
| 7 | 축 C HTTP 400 | STOP → UNVERIFIED 재분류 + 4단계 재프로브 |
| 8 | `/content` 인데 계약 PASS | 런타임 경로를 실제로 검사. `/content` 감지 시 안내 후 중단 |
| 9 | 캐시 히트율 1.0% | 키 = (corp_code, bsns_year, reprt_code). 재실행 히트율 1.000 검증 |
| 10 | 호출 수가 누적으로 기록됨 | 버킷별 독립 카운터 + 총계 별도 필드 |

---

## 4. 코드가 강제하는 구조

### 그래프 범위와 측정 범위의 분리 (`P0_GRAPH_FULL_MEASURE_SUB`)

```
그래프 구성 노드 = 해당 기준일 전 상장사 (매핑 성공분 전부)
지표 측정 대상   = 그 중 시총 하위 1,000종목
```

하위 1,000종목의 노드에 걸린 엣지는 **상대가 유니버스 밖이어도 유지**하고, 엣지마다
내부/외부 플래그를 붙여 판정표에 분리 보고한다. 계약 검사에서 프로브로 확인한다.

### PIT (`P0_PIT_STRICT`)

`exctvSttus.json` 은 `rcept_dt` 를 주지 않는다. **접수일자는 `rcept_no` 앞 8자리**다.
기준일 이후 접수분과 접수번호 판독 불가분은 예외 없이 폐기하고 분포를 남긴다.

기준일별로 요청할 보고서는 **법정 제출기한**으로 결정한다(제출기한이 지난 것 중 기간 종료일이 최신인 것):

| 기준일 | 선택되는 보고서 | 이유 |
|---|---|---|
| 2026-06-30 | 2026 / 11013 (1분기) | 반기(11012)의 제출기한은 2026-08-14 로 기준일 이후 |
| 2021-06-30 | 2021 / 11013 (1분기) | 동일 |

v1.0 이 실제로 11013 을 사용한 것과 일치한다.

### 측정 실패(UNVERIFIED)와 측정 결과 미달(STOP)의 구분

§4 의 4번째 스냅샷(2026-06-30 / 반기)은 제출기한이 **2026-08-14** 다.
그 전에 실행하면 이 스냅샷은 존재하지 않는다. 코드는 이 경우:

1. 벌크 2,700콜을 태우기 전에 **10종목 선행 프로브**로 미접수를 확인하고,
2. 해당 스냅샷을 `available=False` 로 표시해 **전이 계산에서 제외**하고
   (빈 스냅샷을 그대로 쓰면 소멸이 전부 허위로 잡힌다),
3. AΔ-3 을 FAIL 로 두되 축 판정은 **STOP 이 아니라 UNVERIFIED** 로 낸다.

셀프테스트 T12c~T12e 가 이 경로를 검증한다.

### 호출 예산

가용 19,000콜 기준, **80%(15,200콜) 도달 시 스스로 중단**하고 보고한다.
버킷별로 독립 계상하며 총계는 별도 필드다.

§3 의 T_NOW 가 사용하는 `2026/11013` 은 §4 의 `2026-03-31` 스냅샷과 캐시 키가 같아
두 번째 요청은 전부 캐시 히트가 된다(셀프테스트에서 해당 버킷 호출 수 0).

### 시간 예산 축소 (§10)

잔여 시간·호출에 따라 자동으로 적용하고 `known_limitations` 에 기록한다.
① 스냅샷 4개 → 3개(가장 오래된 것 제외) → ② T_PAST 생략 → ③ 축 B 기간 축소 → ④ 수기표본 축소.

---

## 5. 셀프테스트가 검증하는 것

`RUN_MODE=SELFTEST` 는 1,300개 합성 법인(겸직 인물 900명 중 600명 상주, 300명 분기마다 교체)으로
파이프라인을 끝까지 돌리고, 그래프 계산을 **독립적으로 재구현한 naive 버전과 대조**한다.

계약 10건 + 자가검정 30건, 전부 PASS 를 확인했다. 주요 항목:

| 검사 | 확인 내용 |
|---|---|
| T09 | 카나리 전멸 시 벌크 미진입 → UNVERIFIED (소모 11콜) |
| T10c | 유니버스 밖 상대와의 외부 링크 보존 |
| T10d | 매핑 실패 6분류 정확도 |
| T11 | 그래프 differential — 700개 엣지가 naive 재계산과 완전 일치 |
| T12b | 생성·소멸 분리 보존 (순변화로 합산하지 않음) |
| T12c~e | 제출기한 미도래 스냅샷 → UNVERIFIED, 벌크 미수집(0콜) |
| T13 | 기준일별 카운터 독립 (총계와 다른 값) |
| T14 | 재실행 캐시 히트율 1.000, 신규 호출 0회 |
| T15 | 축 C 프로브 전멸 → UNVERIFIED (STOP 아님) |
| T17 | 축 B 인증 없음 → BLOCKED_PREREQ, 우회 시도 없음 |

---

## 6. 이 코드가 하지 않는 것

명령서 §1 의 금지 항목이다. 위반 시 작업 실패로 취급한다.

- 팩터 계산 · 시그널 생성 · 수익률 산출 — `P0_NO_STRATEGY` 가 소스의 식별자를 토큰 단위로 검사한다
- 알파 존재 여부에 대한 주장
- 축 간 결합 분석 — `P0_INDEPENDENT_AXES` 가 축 스코프 밖 결과 접근을 예외로 막는다
- 게이트 미달 시 임계값 조정 — `P0_NO_THRESHOLD_EDIT` 가 임계값 지문을 게이트 평가마다 재확인한다
