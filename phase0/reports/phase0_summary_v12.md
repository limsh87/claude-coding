# PHASE 0 판정 요약 v1.2

- 실행 모드: LIVE
- 전 상장사 노드 수: 미측정 (PENDING)
- 축 C 첫 응답 wkplNm 표본 3건: 미획득 (PENDING)
- 생성 시각: 2026-08-10T06:10:02
- PROJECT_ROOT: `/home/user/claude-coding/phase0` (P0_RUNTIME_ROOT=PASS)
- 총 API 호출: 0 / 중단선 15200 (80% 트립선 12160)
- 총 실행시간: 3.8s

## 축별 판정

| 축 | 기준일 | 상태 | 차단 유형 | 게이트 |
|---|---|---|---|---|
| A | 2026-06-30 | BLOCKED_PREREQ | NET_BLOCKED | — |
| A | 2021-06-30 | BLOCKED_PREREQ | NET_BLOCKED | — |
| A-delta | 2026-03-31 | BLOCKED_PREREQ | NET_BLOCKED | — |
| B | 2026-06-30 | BLOCKED_PREREQ | NO_KEY | — |
| C | 2026-06-30 | BLOCKED_PREREQ | NET_BLOCKED | — |

### 축 A — 2026-06-30 — BLOCKED_PREREQ

차단 사유 3건 (우선 해결: `NET_BLOCKED`)

- `NET_BLOCKED` — OpenDART(opendart.fss.or.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=opendart.fss.or.kr. 원문: ProxyError: HTTPSConnectionPool(host='opendart.fss.or.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NET_BLOCKED` — KRX(data.krx.co.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=data.krx.co.kr. 원문: ProxyError: HTTPSConnectionPool(host='data.krx.co.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NO_KEY` — OpenDART API 키 없음. 환경변수 DART_API_KEY 를 설정한다. 발급: https://opendart.fss.or.kr/ → 인증키 신청/관리 (이메일 인증 즉시 발급, 무료)

**known_limitations**
- 사전점검 단계에서 차단되어 어떤 게이트도 측정되지 않았다. STOP(측정 결과 미달)이 아니라 BLOCKED_PREREQ(측정 자체 불가)다(§11).

### 축 A — 2021-06-30 — BLOCKED_PREREQ

차단 사유 3건 (우선 해결: `NET_BLOCKED`)

- `NET_BLOCKED` — OpenDART(opendart.fss.or.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=opendart.fss.or.kr. 원문: ProxyError: HTTPSConnectionPool(host='opendart.fss.or.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NET_BLOCKED` — KRX(data.krx.co.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=data.krx.co.kr. 원문: ProxyError: HTTPSConnectionPool(host='data.krx.co.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NO_KEY` — OpenDART API 키 없음. 환경변수 DART_API_KEY 를 설정한다. 발급: https://opendart.fss.or.kr/ → 인증키 신청/관리 (이메일 인증 즉시 발급, 무료)

**known_limitations**
- 사전점검 단계에서 차단되어 어떤 게이트도 측정되지 않았다. STOP(측정 결과 미달)이 아니라 BLOCKED_PREREQ(측정 자체 불가)다(§11).

### 축 A-delta — 2026-03-31 — BLOCKED_PREREQ

차단 사유 3건 (우선 해결: `NET_BLOCKED`)

- `NET_BLOCKED` — OpenDART(opendart.fss.or.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=opendart.fss.or.kr. 원문: ProxyError: HTTPSConnectionPool(host='opendart.fss.or.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NET_BLOCKED` — KRX(data.krx.co.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=data.krx.co.kr. 원문: ProxyError: HTTPSConnectionPool(host='data.krx.co.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NO_KEY` — OpenDART API 키 없음. 환경변수 DART_API_KEY 를 설정한다. 발급: https://opendart.fss.or.kr/ → 인증키 신청/관리 (이메일 인증 즉시 발급, 무료)

**known_limitations**
- 사전점검 단계에서 차단되어 스냅샷을 하나도 구성하지 못했다. STOP 이 아니라 BLOCKED_PREREQ 다.

### 축 B — 2026-06-30 — BLOCKED_PREREQ

차단 사유 1건 (우선 해결: `NO_KEY`)

- `NO_KEY` — GCP 자격증명이 없다. 다음 중 하나를 설정한다: (a) GOOGLE_APPLICATION_CREDENTIALS = 서비스계정 JSON 키 '파일의 절대경로' + GOOGLE_CLOUD_PROJECT = '프로젝트 ID', 또는 (b) gcloud auth application-default login. 최소 역할: BigQuery User + BigQuery Job User. 결제 계정 연결 필요(월 1TB 무료).

**known_limitations**
- 인증/의존성 단계에서 차단되었다. §5.1에 따라 '경로 없음'·'키 형식 오류'·'프로젝트 미지정'·'권한 없음'·'결제 미설정'·'네트워크 차단'을 하나의 BLOCKED 로 뭉치지 않고 각각 기록했다. 우선 해결 대상은 cause_class=NO_KEY 다.

### 축 C — 2026-06-30 — BLOCKED_PREREQ

차단 사유 2건 (우선 해결: `NET_BLOCKED`)

- `NET_BLOCKED` — 공공데이터포털(apis.data.go.kr) 도달 불가 — 프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host=apis.data.go.kr. 원문: ProxyError: HTTPSConnectionPool(host='apis.data.go.kr', port=443): Max retries exceeded with url: / (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
- `NO_KEY` — 공공데이터포털 키 없음. 환경변수 DATA_GO_KR_KEY(Decoding 키)를 설정한다. 발급: https://www.data.go.kr/ → 국민연금공단_국민연금 가입 사업장 내역 → 활용신청. 마이페이지 > 데이터활용 > 활용신청 현황에서 '승인' 상태를 먼저 확인할 것(§6.1).

**known_limitations**
- 축 C 관측 지연: 해당 월 후 1~2개월 공표. 프로브 성공 시 실제 지연을 측정한다(§7).

## 계약 상태

`NOT_EXERCISED` = 이번 실행에서 해당 코드 경로가 돌지 않았다. PASS 가 아니다.

| 계약 | 상태 | 내용 |
|---|---|---|
| `P0_LIVE_ONLY` | PASS | 합성/모의 데이터 경로 사용 금지. §1.3 자가진단 통과 필수 |
| `P0_NO_STRATEGY` | PASS | 수익률·시그널·팩터 연산 일절 금지 |
| `P0_PIT_STRICT` | NOT_EXERCISED | 접수일자(rcept_dt)가 기준일 이후인 레코드는 무조건 폐기. 예외 없음 |
| `P0_GRAPH_FULL_MEASURE_SUB` | NOT_EXERCISED | 그래프는 전 상장사로 구성, 지표 측정은 하위 1,000종목에서만 |
| `P0_SNAPSHOT_DEADLINE_GUARD` | NOT_EXERCISED | 스냅샷 수집 전 법정 제출기한 확인. 미도래 시 벌크 없이 UNVERIFIED |
| `P0_CANARY_FIRST` | NOT_EXERCISED | 축마다 10종목 카나리 통과 전 벌크 금지 |
| `P0_INDEPENDENT_AXES` | PASS | 축 A/B/C 상호 의존 금지 |
| `P0_FAIL_LOUD` | PASS | 결측은 결측으로 기록. 보간·추정·대체값 금지 |
| `P0_RUNTIME_ROOT` | PASS | PROJECT_ROOT 런타임 감지. /content 감지 시 WAIVED (PASS 기록 금지) |
| `P0_RESUMABLE` | PASS | 캐시 키에 (corp_code, bsns_year, reprt_code) 전부 포함 |
| `P0_NO_THRESHOLD_EDIT` | PASS | 임계값 dataclass는 frozen. 실행 중 변경 금지 |
| `NO_KNOWN_DEAD_CALL` | PASS | pykrx 지수구성종목 파일 호출 금지 (영구 실패) |

## 축별 관측 지연 (§7 — 기록만)

| 축 | 실제 사건 → 관측 가능 |
|---|---|
| A | 분기보고서 45일 / 사업보고서 90일 |
| B | 출원 후 약 18개월 (공개) |
| C | 해당 월 후 1~2개월 (공표) |

