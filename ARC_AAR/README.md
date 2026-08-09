# ARC-AAR — 애널리스트 주의 재배분 (SPEC-C 단독 구현체)

한국 시장 애널리스트의 **현시선호(주의 배분)** 만으로 양방향 신호를 만드는 전략의
10년(2016-08 ~ 2026-07) 백테스트 원셀 실행형 파이프라인입니다.
계약문서(SPEC-C / ARC-AAR)만을 근거로 제로베이스에서 작성되었으며, 저장소의 다른
전략 코드를 참조하지 않습니다.

## 파일

- `arc_aar_run_all.py` — 단일 파일 전체 파이프라인 (수집→정제→패널→통제회귀→
  철회 인과분해→백테스트 12구성→이벤트 스터디→통계 검증→산출물/표 출력)

## 실행

```bash
# Colab: 파일 업로드 후 셀에서
%run arc_aar_run_all.py
# 또는 파일 전체를 셀 하나에 붙여넣고 실행

# JupyterLab(로컬/Windows)
%run arc_aar_run_all.py

# 터미널
python arc_aar_run_all.py
```

- 자격증명(KRX 마켓플레이스 ID/PW, DART API 키)은 **파일 최상단 [S00]** 에서 입력.
  발급처 URL/절차가 주석으로 안내됨. 비워두면 대화형 1회 질의(비대화형이면 스킵 후
  폴백 체인 사용).
- 모드: 환경변수 `ARC_AAR_MODE` = `FULL`(기본) / `SYNTH`(네트워크 없이 전체
  파이프라인 자가검증) / `CANARY`(소스 도달성만 점검).

## 핵심 동작 규약

- **구글드라이브 절대 1원칙**: 신규 수집 데이터는 전부 드라이브에 저장되고
  `공용인덱스(common_index.json)` / `전용인덱스(arc_aar_index.json)` 에 등록됩니다.
  기존 인덱스는 append-only 병합 + 타임스탬프 백업 + 검증 후 원자 교체로 **절대
  파괴되지 않으며**, 파싱 불가 인덱스를 만나면 원본을 건드리지 않고 사이드카로
  전환합니다. 타 전략 레거시 인덱스는 읽기전용으로 재활용합니다.
- **캐시 탐색**: 로컬(홈/D드라이브) + 드라이브 양측을 모두 탐색, 드라이브 부재 시
  pending 큐 적재 후 다음 실행에서 자동 동기화.
- **수집 4시간 타임박스**: 초과 시 수집을 우아하게 멈추고 그때까지의 데이터로
  **INTERIM 백테스트 결과**를 산출(모든 산출물에 표기). 재실행 시 완료분은 스킵하고
  이어서 수집합니다. 계산 단계에는 시간 제한이 없습니다.
- **실시간 쿼터**: DART 등 API 는 고정 예산을 가정하지 않고 서버 응답('020' 등)과
  금일 사용량으로 잔여 호출량을 추적, 소진 시 키 교체/우아한 중단.
- **PIT/생존편향**: KRX 월말 전종목 스냅샷으로 유니버스를 구성해 상장폐지 종목을
  포함(스냅샷 소멸=상폐 추론), 진입은 익영업일 종가, 통제회귀는 확장윈도우
  재귀추정으로 look-ahead 차단.

## 산출물 (`<root>/outputs/`)

계약 §10 전체: `PHASE0_DATA_FEASIBILITY.md`, `attention_panel.parquet`,
`coverage_exit_classification.parquet`, `metrics_all_configs.csv`,
`event_study_car.parquet`, `equity_curves.parquet`, `trade_log.parquet`,
`hypothesis_test_report.md`, `mechanism_tests.md`, `causal_decomposition.md`,
`lead_lag_consensus.md`, `shrinkage_diagnostics.md`, `cost_sensitivity.md`,
`OPEN_QUESTIONS.md`, `FINAL_VERDICT.md`, `run_summary.json` + 로그에
성과검증표/강건성검사표/기타해석표 출력. 비교전략(시총 하위 1000종목)은
`outputs/compare_small1000/` 에 별도 산출.

## 검증 상태

- SYNTH 합성 세계(플란트 효과 내장)로 전체 파이프라인 엔드투엔드 자가검증:
  M-EXIT 플라시보 귀무 유지, H-EXIT 음(−) CAR 회수, H5 선행성 회수, PBO/DSR/
  워크포워드/부트스트랩 정상 동작 확인.
- pandas 2.2(코랩) / 3.x 양쪽에서 실행 검증.
