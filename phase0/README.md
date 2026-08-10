# PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.2

명령서 v1.2의 실행체. **수집 가능성만 측정한다.** 팩터·시그널·수익률 연산은 코드에 존재하지 않는다(`P0_NO_STRATEGY`).

| 파일 | 역할 |
|---|---|
| `phase0_3axis_v12.py` | 실행체. §8.5 요구대로 **단일 코드 셀**. Colab 한 셀에 붙여넣거나 `python phase0_3axis_v12.py` |
| `tests/test_logic_v12.py` | 순수 함수 로직 테스트. **측정값을 만들지 않으며 §9 산출물이 아니다** |
| `../tools/gen_phase0_preview.py` | 브라우저에서 읽고 복사·다운로드하는 단일 HTML 미리보기 생성기 |

---

## 1. 실행 모드는 LIVE 하나뿐이다

v1.1의 셀프테스트 36/36 PASS는 합성 데이터였으므로 측정값이 전부 무효였다. v1.2는 그 실패를 구조로 막는다.

- `SELFTEST = False` 고정. `True`로 바꾸면 **시작 직후 예외로 중단**한다(§1.3).
- 합성 데이터를 만드는 코드 경로가 파일에 존재하지 않는다.
- 산출물은 `reports/`. `reports_selftest/`를 쓰지 않는다.
- 자가진단 2종이 통과해야 진행한다:
  - 전 상장사 노드 수가 1,100~1,600이면 → 합성 경로 의심으로 **중단**
  - 축 C 응답 `wkplNm`에 `합성`·`더미` 등 마커가 보이면 → **즉시 중단**

## 2. 실행에 필요한 것

### 2.1 키 입력란 — 파일 맨 위

`phase0_3axis_v12.py` 상단(`from __future__` 바로 아래)에 입력란이 있다. 네 칸을 채우면 된다.

```python
DART_API_KEY    = ""      # OpenDART 인증키 40자
GCP_SA_KEY_PATH = ""      # JSON 키 "파일의 절대경로"  예) /content/sa-key.json
GCP_PROJECT_ID  = ""      # "프로젝트 ID 문자열"       예) compelling-muse-311107
DATA_GO_KR_KEY  = ""      # 공공데이터포털 Decoding 키
```

비워두면 같은 이름의 환경변수에서 읽는다. 둘 다 없으면 해당 축만 `BLOCKED_PREREQ(NO_KEY)`로
기록되고 나머지 축은 정상 진행한다.

| 입력란 | 대응 환경변수 | 축 |
|---|---|---|
| `DART_API_KEY` | `DART_API_KEY` | A, A-Δ |
| `GCP_SA_KEY_PATH` | `GOOGLE_APPLICATION_CREDENTIALS` | B |
| `GCP_PROJECT_ID` | `GOOGLE_CLOUD_PROJECT` | B |
| `DATA_GO_KR_KEY` | `DATA_GO_KR_KEY` | C |
| — | `P0_PROJECT_ROOT` (선택) 캐시·산출물 루트 | 전체 |

키는 로그·판정표 어디에도 남지 않는다. 실행 시작 시 **앞 4자와 길이만** 마스킹해 출처와 함께 찍는다.

```
키 입력 상태 (값은 마스킹된다)
  [1] DART_API_KEY      abc1…****** (길이 40)  ← 입력란
  [2] GCP_SA_KEY_PATH   /content/sa-key.json   ← 환경변수 GOOGLE_APPLICATION_CREDENTIALS
```

> **v1.1이 죽은 지점**: `GOOGLE_APPLICATION_CREDENTIALS`에 프로젝트 ID(`compelling-muse-311107`)를 넣었다.
> 두 변수는 역할이 다르다. 위 표대로 넣어야 한다. 코드는 이 오설정을 감지하면
> `AUTH_PATH` 원인으로 분류하고 "이 값은 프로젝트 ID처럼 보인다"고 짚어준다.

BigQuery 최소 역할은 `BigQuery User` + `BigQuery Job User`이고 결제 계정 연결이 필요하다(월 1TB 무료 티어).
`gcloud auth application-default login`(ADC) 경로도 허용한다.

공공데이터포털은 **활용신청이 '승인' 상태여야 한다**. '신청' 상태면 어떤 파라미터로도 실패한다.
마이페이지 > 데이터활용 > 활용신청 현황에서 승인 여부와 일일 트래픽 잔량을 먼저 확인한다.

### 2.2 의존성

```bash
pip install requests pandas numpy pykrx google-cloud-bigquery
```

### 2.3 네트워크

다음 호스트로 나가는 HTTPS가 열려 있어야 한다.

| 호스트 | 축 |
|---|---|
| `opendart.fss.or.kr` | A, A-Δ |
| `data.krx.co.kr` (pykrx) | A, A-Δ 유니버스·시가총액 |
| `bigquery.googleapis.com` | B |
| `apis.data.go.kr` | C |

사전점검이 키 유무와 무관하게 네트워크를 **항상** 확인한다. 키를 넣은 뒤 다시 막히는 일을 없애기 위해서다.

## 3. 실행

```bash
python3 phase0_3axis_v12.py
```

로그 최상단에 `실행 모드: LIVE`, 전 상장사 노드 수, 축 C `wkplNm` 표본 3건이 찍힌다.

**호출 예산**: 중단선 15,200콜. 누적 호출이 80%(12,160콜)에 닿으면 즉시 중단하고
그때까지의 판정표를 저장한 뒤 `reports/resume_todo.json`을 남긴다.
캐시 키가 `(corp_code, bsns_year, reprt_code)`이므로 다음 날 재실행하면 캐시 히트로 이어받는다.
**이틀에 나눠 도는 것이 정상 경로다.** 하루에 끝내려고 하지 말 것.

## 4. 산출물 (`reports/`)

| 파일 | 내용 |
|---|---|
| `phase0_verdict_v12.json` / `.csv` | 판정표 |
| `phase0_summary_v12.md` | 요약 (해석·전략 제안 없음) |
| `phase0_run_v12.log` | 실행 로그 |
| `diag_corpcode_miss.csv` | corp_code 매핑 실패 + 유형 분류 |
| `diag_pit_dropped.csv` | PIT 폐기 레코드의 접수일자 분포 |
| `diag_edge_events.csv` | 전이별 종목 단위 `edge_born` / `edge_died` |
| `diag_C_probes.csv` | 축 C 프로브 4종의 상태코드·응답 원문 |
| `manual_check_A_coexec_links.csv` | 겸직 링크 200건 (A-4는 사람이 판정할 때까지 PENDING) |
| `manual_check_C_workplace_match.csv` | 사업장 매칭 100건 (프로브 성공 시) |
| `resume_todo.json` | 중단 시 남은 작업 |

### 판정 상태

| 상태 | 뜻 |
|---|---|
| `GO` | 전 게이트 통과 |
| `STOP` | **측정은 됐고 결과가 임계 미달** |
| `UNVERIFIED` | **측정 자체를 못 했다.** STOP과 다르다 |
| `BLOCKED_PREREQ` | 키·네트워크·의존성 등 전제조건 미충족 |
| `PENDING_MANUAL` | 자동 게이트는 통과, 수기 검증 대기 |

`STOP`과 `UNVERIFIED`를 섞지 않는 것이 이 단계의 핵심이다. 측정 실패를 결과 미달로 적으면
다음 단계가 잘못된 근거 위에 서게 된다.

계약 상태표의 `NOT_EXERCISED`는 **해당 코드 경로가 이번 실행에서 돌지 않았다**는 뜻이며 PASS가 아니다.

## 5. 이 저장소 컨테이너에서의 실행 결과

`reports/`에 커밋된 산출물은 **이 CI 컨테이너에서 LIVE 모드로 실제 실행한 결과**이며,
전 축 `BLOCKED_PREREQ`다. 게이트 측정값은 하나도 없다.

| 축 | 상태 | 우선 해결 |
|---|---|---|
| A (2026-06-30, 2021-06-30) | `BLOCKED_PREREQ` | `NET_BLOCKED` + `NO_KEY` |
| A-Δ | `BLOCKED_PREREQ` | `NET_BLOCKED` + `NO_KEY` |
| B | `BLOCKED_PREREQ` | `NO_KEY` (네트워크는 열려 있음) |
| C | `BLOCKED_PREREQ` | `NET_BLOCKED` + `NO_KEY` |

이 컨테이너의 이그레스 정책이 `opendart.fss.or.kr`, `data.krx.co.kr`, `apis.data.go.kr`에 대한
CONNECT를 403으로 거부한다. 키를 넣어도 축 A/A-Δ/C는 여기서 돌지 않는다.
`bigquery.googleapis.com`은 열려 있으므로 **축 B는 GCP 서비스계정 키만 있으면 이 환경에서도 실측 가능하다.**

## 6. 설계 메모

- **겸직 엣지**는 `(성명 + 출생년월)` 동일성으로 판정한다. 출생년월 결측 레코드는 동명이인
  오결합을 피하려고 엣지 생성에서 제외하고 그 수를 A-2로 보고한다. 추정으로 채우지 않는다.
- **A-5**는 인물 다중 겸직을 합산하지 않고 **고유 종목쌍** 수로 센다(보수적 계수).
- **A-Δ 전이별 측정대상**은 양 스냅샷 하위 1,000종목의 **교집합**이다. 유니버스 구성 변화가
  엣지 생성/소멸로 위장하는 것을 막는다. 교집합 크기를 판정표에 함께 적는다.
- **`edge_born`과 `edge_died`는 절대 합산하지 않는다.** 엣지 소멸이 실제 퇴임인지 보고서
  미기재인지 구분할 수 없다는 한계를 판정표에 명시한다.
- **축 B 룩어헤드**: 관측가능성 필터는 `publication_date`, 측정 변수는 `filing_date`. 혼용하지 않는다.
  모든 쿼리를 `dry_run`으로 먼저 돌려 스캔 바이트를 로그에 찍고, 단일 쿼리 100GB 초과 시 중단한다.
- **퍼지 매칭**은 '접두 일치, 최소 길이 3'으로 고정했다. 임의 부분문자열 포함을 쓰면 `동방`이
  `동방전자`·`동방물산`에 모두 걸려 매칭률이 부풀려진다. 완전일치와 퍼지는 분리 보고한다.
- **DART 오류 응답을 캐시하지 않는다.** `000`(정상)·`013`(데이터 없음)만 캐시한다. 쿼터 초과(`020`)
  같은 치명 오류는 즉시 축을 중단시킨다 — 종목별 오류로 흘려보내면 A-1이 0으로 떨어져
  **측정 실패가 결과 미달(STOP)로 둔갑한다.**
- **제출기한은 12월 결산법인 기준**으로 계산한다. 비12월 결산법인은 실제 기한이 다르며
  `known_limitations`에 적혀 있다.

## 7. 로직 테스트

```bash
python3 tests/test_logic_v12.py
```

날짜 계산·문자열 정규화·PIT 폐기·그래프 구성 같은 **순수 함수**만 손으로 만든 최소 입력으로 검증한다.
`reports/`에 쓰지 않고, 판정표를 만들지 않고, 어떤 게이트도 채점하지 않는다.
**이 결과는 §9 산출물이 아니며 어떤 축의 판정 근거로도 인용될 수 없다.**
