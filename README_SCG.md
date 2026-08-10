# SCG_ORIGINAL_REPRO_V1 — 스마트 컨센서스 갭 / IBK 서프라이즈 포트폴리오 재현

IBK투자증권 이정빈, 「바텀업 퀀트 – 알파 포트폴리오 전략」(2020-08-20)의
**스마트 컨센서스 갭**과 **서프라이즈 포트폴리오**를 구현한다.

> **이 코드의 첫 번째 임무는 성과를 내는 것이 아니라, 무엇을 재현했고 무엇을 재현하지
> 못했는지 거짓 없이 구분하는 것이다.** 원문이 공개한 정의와 공개하지 않은 부분을
> 코드 수준에서 분리하고, 후자를 `OPERATIONAL_REPRODUCTION_ASSUMPTION` 으로 태깅한다.

---

## 1. 실행

```bash
python3 run_smart_consensus_gap.py            # 원클릭
```

```python
from run_smart_consensus_gap import run
result = run()                                 # 노트북/Colab 도 동일 (SCG_RUN.ipynb)
```

```bash
python3 tools/scg_selftest.py                  # 자가검정 20종 (수 분)
```

주요 옵션:

| 인자 | 뜻 |
|---|---|
| `data_roots=[...]` | 캐시/데이터 경로 직접 지정 (미지정 시 자동 탐색) |
| `allow_synthetic_fallback=False` | 실데이터가 없으면 합성으로 넘어가지 말고 `NO_DATA` 로 종료 |
| `mode="ORIGINAL_EXACT"` | 벤더 필드가 **실제로** 있을 때만 유효. 없으면 자동 강등 |
| `run_robustness=False` / `run_bootstrap=False` | 빠른 확인용 |

---

## 2. 두 모드를 절대 섞지 않는다

| | `ORIGINAL_EXACT` | `PUBLIC_REPRO` |
|---|---|---|
| Smart Consensus | 벤더(FnGuide/Quantiwise) 값 그대로 | 공개 추정치로 재구성 |
| 서프라이즈 확률 | 벤더 값 | **제외** (프록시 주입 금지) |
| 팩터 수 | 7 | 6 |
| 전략 | `IBK_7F_EXACT` | `IBK_6F_PUBLIC_REPRO` |

벤더 필드가 없으면 `IBK_7F_EXACT` 는 **실행되지 않고** `SKIPPED_MISSING_VENDOR_FIELDS`
로 기록된다. 프록시를 몰래 넣고 exact 라고 부르는 경로는 코드에 존재하지 않으며,
감사 항목 `MODE_CONTAMINATION_ZERO` / `PUBLIC_REPRO_NO_SURPRISE_PROXY` 가 이를 검사한다.

벤더 필드가 있으면 기본 모드가 `PUBLIC_REPRO` 여도 **둘 다** 실행되고, 서로 다른 팩터
프레임에서 나오므로 섞이지 않는다.

---

## 3. 산출되는 4개 전략 (§2)

| 전략 | 내용 |
|---|---|
| `SCG_SINGLE_RAW` | SCG 원형 내림차순 Top30 — Smart Gap 자체가 알파인지 독립 검증 |
| `SCG_SINGLE_Z` | 윈저 후 z-score Top30 |
| `IBK_6F_PUBLIC_REPRO` | 공개재구성 6팩터 — PUBLIC_REPRO 대표 결과 |
| `IBK_7F_EXACT` | 원문 7팩터 — 벤더 필드가 있을 때만 |

> ⚠ `SCG_SINGLE_RAW` 와 `SCG_SINGLE_Z` 는 **구조적으로 거의 같은 전략이다.** 윈저라이즈도
> z-score 도 단조 변환이라 순위를 바꾸지 않기 때문이다. 두 값의 차이는 표준화의 효과가
> 아니라 꼬리에서 잘려 동점이 된 종목의 처리 차이일 뿐이다. 해석 문서가 이 사실을 먼저 말한다.

공통: KOSPI200 PIT 유니버스 · 30종목 · 시가총액 가중 · 3/6/9/12월 말 시그널 ·
다음 거래일 시가 체결 · 편도 회전율 × 35bp.

---

## 4. 산식 — 원형 보존

```
SCG_RAW = (Smart Consensus_FQ1 − General Consensus_FQ1) / General Consensus_FQ1
```

**분모에 `abs` 를 씌우지 않는다.** 음수 컨센서스에서 부호가 뒤집히는 것은 원문 산식의
성질이며, 그것을 "고치면" 다른 전략이 된다. 단위테스트와 소스 검사 두 곳에서 고정한다.

- `|C_general| < 1e-8` → 결측 + `DENOM_NEAR_ZERO` 플래그
- composite 입력용 윈저라이즈는 별도 컬럼에만 적용하고 `SCG_RAW` 는 절대 덮어쓰지 않는다

스마트 컨센서스 재구성(§5)은 공개적으로 알려진 세 원리만 쓴다 —
**최신성**(반감기 30일) × **과거 정확도**(shrinkage 후 skill) × **편향 보정**.
FnGuide 비공개 산식의 복제가 아니다.

---

## 5. 스마트 컨센서스는 역산 가능해야 한다

`04_smart_consensus_components.parquet` 에 estimator 단위로 전부 남는다:

```
asof · company · fiscal_period · estimator_id · published_at · age_days
estimate_raw · bias · bias_scale · estimate_adj
w_recency · skill · w_raw · w_final · n_events
```

`Σ(w_final × estimate_adj)` 가 그 시점의 smart consensus 와 일치한다(단위테스트 `감사표_역산가능`).
어떤 종목의 어떤 값이 왜 그렇게 나왔는지 설명하지 못하는 상태를 허용하지 않는다.

---

## 6. PIT — 구조로 막는다

| 위험 | 대응 |
|---|---|
| 미래 추정치 | 스냅샷 조회 경로가 `published_at ≤ t` 마스크 **하나뿐**이다. 우회 인자를 만들지 않았다 |
| 미래 실적으로 skill 학습 | `actual_announced_at < t` (등호 없음). 발표 당일도 차단 |
| 현재 구성종목 소급 | 유니버스는 `t` 이하 최신 스냅샷만. 스냅샷이 1개뿐이면 감사가 소급을 의심해 실패시킨다 |
| 상장폐지 종목 삭제 | 삭제하지 않는다. 마지막 가용 가격으로 청산해 현금으로 남기고 플래그 |
| 체결 look-ahead | 공식 체결은 다음 거래일 **시가**. 당일 종가 체결은 진단용으로만 출력 |
| 수정주가 혼용 | 수정종가와 원시 시가를 섞지 않는다. 수정계수를 알 수 없으면 시가 체결을 포기하고 플래그 |

`12_audit_checks.csv` 의 CRITICAL 이 하나라도 실패하면 **공식 성과표를 만들지 않고**
`run_status = FAILED_AUDIT` 로 끝난다. 성과가 감사를 우회하는 경로는 없다.

---

## 7. 사후 튜닝을 구조로 막는다

1. §25 기본값은 **리터럴 스냅샷**과 **데이터클래스 기본값** 두 곳에 이중으로 적혀 있고,
   어긋나면 `BASE_CONFIG_UNMODIFIED` 가 CRITICAL 실패한다.
2. 강건성 변형은 자유 오버라이드가 아니라 **사전 등록 레지스트리**에서만 나오며,
   생성 시점에 *한 번에 한 축만* 바꾸는지 검증한다 → 카테시안 전수탐색이 불가능하다.
3. 강건성 결과는 전부 출력하고 BASE 를 공식으로 고정한다. 최고 CAGR 변형을 승격하지 않는다.
4. 2020-06-30 표7은 **학습 대상이 아니라 검증 대상**이다. 겹침이 낮아도 파라미터를 맞추지 않는다.

---

## 8. 2020-06-30 원문 표7 대조 (§14) — 지금은 비어 있다

`smart_consensus_gap/reference/reference_20200630.csv` 는 헤더만 있고 데이터가 없다.
**원문 PDF가 이 저장소에 없기 때문이며, 없는 30종목을 코드가 지어내지 않는다.**

- 현재 상태: `11_reference_20200630_match.csv` → `fixture_status = REFERENCE_FIXTURE_EMPTY`
- 해석 문서는 이것을 "재현 실패"가 아니라 **"검증 재료 부재"** 로 구분해 적는다
- PDF 16쪽 표7을 채우면 다음 실행부터 overlap / Jaccard / 순위상관 / 팩터값 상관이 자동 계산된다

채우는 방법은 `smart_consensus_gap/reference/README.md` 참조.

---

## 9. 데이터가 없을 때

이 저장소에는 FnGuide/Quantiwise/KRX 원자료가 없다. 필수 테이블이 없으면:

- 기본: **합성 픽스처 리허설**로 전환해 계산경로·감사·산출물 전부를 실제로 통과시키고,
  모든 산출물에 `synthetic=true` 를 박는다.
- 이때 나오는 성과·IC·분위 수치는 **성과가 아니다.** 설계자가 합성 데이터에 심어 둔 신호를
  되찾은 것일 뿐이며, 해석 문서 맨 앞에 그 사실이 먼저 나온다.
- `allow_synthetic_fallback=False` 면 `NO_DATA` 로 즉시 종료한다.

실데이터를 연결하려면 §3 데이터 계약에 맞는 parquet/csv 를 아래 중 아무 곳에나 두면 된다.
탐색은 **파일명이 아니라 실제 컬럼 구성**으로 매칭하며, 어떤 파일도 옮기거나 지우지 않는다.

```
SCG_DATA_DIR 환경변수 · ./data · ./scg_data · ./scg_cache · ~/scg_cache
/content/drive/MyDrive/scg_cache
/content/drive/MyDrive/tcd_cache/_shared/table   ← 기존 TCD v2 공용 캐시 재사용
```

필수: `analyst_estimates` `actuals` `prices` `flows` `universe_membership`
선택: `vendor_consensus`(있으면 EXACT 활성) `benchmark` `fiscal_calendar`

`analyst_estimates` 원본에는 `broker_name_norm` / `estimator_id` 같은 파생 컬럼이 없어도 된다.
필요한 것은 `published_at, company_code, metric, fiscal_period, estimate_value` 뿐이고
나머지는 Stage 1 이 만든다.

---

## 10. 성능

10년 전체 파이프라인 예산은 4시간(§19)이다. KOSPI200 규모(250종목 · 30 estimator ·
추정치 171만 행 · 거래일 2,999일) 합성 원장으로 측정한 실제 소요:

| 스테이지 | 소요 | 예산 |
|---|---|---|
| S0 탐색 | 7s | 10m |
| S1 정규화 | 29s | 30m |
| S2 PIT 스냅샷 | 6s | 40m |
| S3 애널리스트 정확도 | 3s | 60m |
| S4·5 컨센서스/팩터 | 50s | 45m |
| S6 백테스트 | 5s | 15m |
| S7 강건성(11변형+절제) | 159s | 50m |
| S8 감사·검증 | 3s | 20m |
| **합계** | **4.4분** | **240m** |

peak RSS 2.3GB. 여유가 큰 이유는 파이썬 행 루프를 쓰지 않기 때문이다:

- 정규화는 **유니크 값에만** 함수를 적용하고 매핑으로 되돌린다 (증권사명 정규식 36개 ×
  수백만 행 → 수백 개)
- PIT 스냅샷은 한 번 정렬해 두고 시점마다 마스크 1회 + `np.maximum.at` 1회
- 애널리스트 정확도는 정렬된 이벤트의 *접두부* 성질을 이용해 `bincount` + `repeat/cumsum`
- 강건성은 컨센서스 축만 재계산하고 포트폴리오 축은 캐시된 팩터 스냅샷을 재사용

---

## 11. 출력물 (§22)

`outputs/scg_<run_id>/` 에 19개:

```
00_run_manifest.json          10_monthly_returns.csv
01_source_availability.csv    11_reference_20200630_match.csv
02_data_quality_waterfall.csv 12_audit_checks.csv
03_analyst_skill.parquet      13_rank_ic.csv
04_smart_consensus_components.parquet
05_factor_snapshots.parquet   14_quintiles.csv
06_rebalance_candidates.csv   15_robustness.csv
07_holdings.csv               16_factor_ablation.csv
08_performance_official.csv   17_runtime_profile.csv
09_yearly_returns.csv         18_interpretation.md   +  run.log
```

`18_interpretation.md` 는 §23 의 12개 질문에 순서대로 답하고, 마지막에
**재현 신뢰도**와 **알파 여부**를 *분리해서* 판정한다. 알파 판정은 사전에 고정된
5개 기준(IC · 분위 단조성 · SCG 절제 · 부트스트랩 CI · 이벤트 제거) 중 3개 이상을
만족할 때만 "독립 알파"라고 부르며, **판정불가는 통과로 세지 않는다.**

---

## 12. 코드 구조 (§24)

```
smart_consensus_gap/
    config.py        §25 기본값 + 사전 정의 강건성 레지스트리 (사후 튜닝 차단 장치)
    contracts.py     §3 데이터 계약 · 컬럼 별칭 · 코어싱 · 회계기간 표기
    util.py          로깅 · 스테이지 타이머(§19) · IO · 벡터화 그룹 헬퍼
    discover.py      Stage 0 캐시 자동 탐색 · 소스 가용성 · 모드 결정
    normalize.py     Stage 1 애널리스트 식별 · 회계기간 · 단위 · 타임스탬프
    pit_engine.py    Stage 2 거래캘린더 · 추정치 인덱스 · 타깃 기간 해상 · 시장 패널
    analyst_skill.py Stage 3 실현 예측오차 원장 → 시점별 skill/bias
    consensus.py     Stage 4 일반/스마트 컨센서스 · Smart Gap · 산식 단위테스트
    factors.py       Stage 5 6/7 팩터 스냅샷 + §21 워터폴
    scoring.py       §9 윈저·z-score/랭크·동일가중 합성 (결측 대체 금지)
    portfolio.py     §11 시총가중 Top-N · §13 회전율/비용
    backtest.py      §12 체결·상장폐지 · §17 성과지표
    validation.py    §20 감사 · §15 IC/분위/조건부 · §14 표7 대조 · §17 통계
    robustness.py    §16 사전 정의 변형 · 팩터 절제
    reporting.py     §22 산출물 · §23 해석
    synthetic.py     합성 픽스처(리허설 전용)
    reference/       2020-06-30 표7 픽스처 (현재 비어 있음)
run_smart_consensus_gap.py   오케스트레이터
SCG_RUN.ipynb                런처/조회 전용 노트북
tools/scg_selftest.py        자가검정 20종
```

노트북에는 로직을 넣지 않는다. 셀 하나가 `run()` 을 부를 뿐이다.

---

## 13. 알려진 한계 (숨기지 않는다)

1. **2020-06-30 표7 대조가 아직 수행되지 않았다.** 원문 PDF가 없어서다. 재현도의 가장
   직접적인 증거가 비어 있는 상태이며, 픽스처를 채우기 전까지는 "얼마나 닮았는지" 말할 수 없다.
2. **PUBLIC_REPRO 의 스마트 컨센서스는 벤더 산식이 아니다.** 최신성·정확도·편향의 3요소
   재구성이며, 원문이 공개하지 않은 가중식을 복제했다고 주장하지 않는다.
3. **서프라이즈 확률이 없으면 6팩터다.** 원문은 7팩터이고, 그 차이는 성과가 아니라
   *정의*의 차이다.
4. **FQ1/FY1 타깃 기간 정의는 재현 가정이다.** 원문은 "해당 시점의 FQ1"이 정확히 어떤
   회계기간인지 명시하지 않는다. 여기서는 '아직 발표되지 않은 최초 기간'으로 정의했다.
5. **벤치마크가 실지수가 아닐 수 있다.** `benchmark` 테이블이 없으면 PIT 유니버스
   시총가중을 대용으로 쓰고 `PROXY_UNIVERSE_CAPWEIGHT` 로 표기한다. TE/IR 해석 시 주의.
6. **수급 팩터는 20영업일 중 15일 이상 관측을 요구한다.** 이 임계값은 재현 가정이다.
7. **단위 오류 제거 규칙은 보수적이지만 완벽하지 않다.** 그룹 중앙값 대비 50배 이상이면서
   10의 거듭제곱에 붙어 있을 때만 제거하며, 제거 건수는 항상 드롭 사유 표에 표시된다.

---

*본 문서와 코드는 전략 설계·검증용이며 투자자문이 아니다.*
