# G2B-DEMAND-GRAPH-V1

**나라장터 정부수요 이동 → 기업역량 정합 → 실제 수주 전환** 투자전략 연구 엔진.

> «기업이 "잘하고 있다"를 사는 것이 아니라, 그 기업이 **과거부터 경쟁력을 입증한 사업영역**으로
> **외생적인 정부수요가 이동**하고 있으며, 해당 기업이 그 증가한 수요를 **실제 수주로 전환**하고
> 있는지를 측정한다.»

이 연구의 핵심 분리는 두 축이다.

| 축 | 질문 | 원천 | 규율 |
|---|---|---|---|
| **A. EXOGENOUS DEMAND** | 정부가 어디에 돈을 쓰기 시작했는가? | 발주계획 · 사전규격 · 입찰공고 | **winner 를 보기 전** 정보로만 만든다 |
| **B. FIRM EXECUTION** | 그 수요가 증가하는 영역에서 어느 기업이 실제 수주하는가? | 낙찰 · 계약 | 기업 크기로 정규화 |

최종 알파는 이 둘의 **정합(alignment)** 에서 찾는다.

```
G2B_DWA = sqrt(P_D × P_W)        # 기하평균 — 두 축이 모두 높아야 높다
```

---

## 1. 실행

### 단일파일 (Colab / JupyterLab)

```bash
python strategies/g2b_demand_graph_v1.py
```

한 셀에 붙여넣어도 동일하게 동작한다. 필요한 config YAML 은 없으면 **내장 템플릿으로 생성**되고,
이미 있으면 절대 덮어쓰지 않는다.

### 패키지 형태 (§91 스크립트)

```bash
cd g2b/scripts && python run_all.py          # 01 → 13 순차
python run_all.py 10 11                      # 특정 단계만
```

### 환경변수

| 변수 | 뜻 |
|---|---|
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 **일반 인증키(Decoding)**. Encoding 키를 넣으면 이중 인코딩으로 401 이 난다(코드가 자동 감지·교정 시도) |
| `OPENDART_API_KEY` | OpenDART 인증키 |
| `G2B_RUN_MODE` | `SMOKE`(합성, 기본) / `FULL`(캐시 우선 + 부족분 수집) / `CACHED`(신규 수집 금지) |
| `G2B_GDRIVE_ROOT` | 구글드라이브 캐시 루트 (기본 `/content/drive/MyDrive/tcd_cache`) |

키가 없으면 **조용히 0 을 만들지 않고** 무엇이 왜 불가능한지 로그와 보고서에 남긴다.

---

## 2. 구글드라이브 인덱스 — 공용 / 전용

```
{GDRIVE_ROOT}/
├── _shared/          ← 공용 인덱스: 다른 전략이 그대로 재사용
│   ├── index/{index.jsonl(원천, append-only), index.parquet(파생), _backup/}
│   └── table/{g2b_bid_raw, g2b_award_raw, g2b_contract_raw, g2b_order_plan_raw,
│              g2b_prespec_raw, g2b_process_raw, g2b_events_normalized,
│              g2b_company_crosswalk, g2b_contract_history,
│              krx_ohlcv_daily·security_master·dart_corpcode·dart_fnltt_raw(재사용)}
└── g2b_dg_v1/        ← 전용 인덱스: 이 연구의 해석물
    └── table/{g2b_opportunity_lifecycle, g2b_demand_graph_nodes/edges,
               company_capability_monthly, government_demand_monthly,
               eligible_tam_monthly, company_g2b_features_monthly, g2b_dwa_portfolios}
```

**절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다.** 약속이 아니라 구조로 보장한다.

1. 인덱스의 진실은 **append-only JSONL 저널**이다. 기존 줄을 다시 쓰지 않는다.
2. `index.parquet` 은 저널의 파생물이며 재생성 전 **항상 타임스탬프 백업**. 백업 실패 시 컴팩션 자체를 건너뛴다.
3. 컬럼은 **합집합으로만** 확장한다.
4. blob 은 **내용해시 경로** → 같은 내용은 재기록조차 없다.
5. 이미 있던 파일은 **이동·개명 없이 경로만 등록**(adopt-by-reference).
6. **삭제 API 자체가 없다.** 손상 파일도 `.corrupt` 로 격리만 한다.

**캐시활용 최우선**: 공용 인덱스에 이미 있으면 재수집하지 않고, 같은 historical request 를 두 번 호출하지 않는다(§87). 가격·재무는 사용자의 기존 PIT DB(`krx_ohlcv_daily`, `security_master`, `dart_fnltt_raw`)를 **그대로 재사용**한다.

---

## 3. 이 엔진이 구조로 막는 것

### FUTURE_RETURN_LOCK (§1.1)

사전등록 4개 YAML + `audit/trial_ledger.json` 이 동결되고 SHA256 이 `audit/prereg_hash.txt` 에
기록되기 전에는 미래수익률에 **접근 자체가 예외로 막힌다**. 우회 파라미터를 두지 않았다.
동결 이후 파일을 고치면 해시가 어긋나 **잠금이 자동으로 다시 걸린다**.

```python
attach_forward_return(...)   # 미래수익률 진입점은 이 하나뿐이고 관문을 통과해야 한다
```

### 이중계산 (§8 · §11)

발주계획 100억 + 사전규격 100억 + 입찰공고 100억 + 계약 100억 = **400억이 아니다.**

```
best_known_amount(o, t) = 그때까지 알려진 '가장 진척된 단계'의 금액
demand_flow(o, t)       = Δ_t best_known_amount(o, t)      ← 증분만 신규수요
```

이 한 줄이 §8(수정공고 중복금지)과 §11(4중계상 금지)을 동시에 해결한다.
**증분의 합은 언제나 마지막으로 알려진 금액과 정확히 같다** — 어떤 순서로 집계해도 이중계산이
원천적으로 불가능하다. 회귀 테스트가 이 보존성을 고정한다.

| 측정 | 합성 세계 예시 |
|---|---|
| 전 단계 단순합산(금지된 계산) | 123.9조 |
| lifecycle 증분합(정답) | 29.6조 |
| opportunity 최종 알려진 금액 합 | 29.6조 ✔ |

### PIT 필드 등급 (§6.1)

| 등급 | 뜻 | 처리 |
|---|---|---|
| A | 당시 공개시각·값이 확정 복원 | 사용 허용 |
| B | 변경이력으로 유효기간 복원 가능 | 리비전 구간 복원 후 사용 |
| C | 과거 최종값만 반환·변경과정 불명 | **역사적 백테스트 사용 금지** (`PIT_UNCERTIFIED`) |

**등록되지 않은 필드는 자동으로 C** 다. 새 피처를 추가하면서 등급 선언을 빠뜨리면
파이프라인이 멈춘다 — 그것이 이 장치의 목적이다.

### 누수 카나리아 (§93)

의도적으로 미래 낙찰정보를 t 이전으로 앞당긴 mock dataset 을 만들어 **탐지기가 실제로
실패시키는지** 확인한다. 통과하지 못하면 본 백테스트 실행이 `LeakageDetected` 로 차단된다.
탐지기를 무력화하면(`monkeypatch`) gate 가 예외를 던지는 것까지 테스트로 고정했다.

### 두 방향 하네스 검증

| 세계 | 기대 | 실측 |
|---|---|---|
| 알파가 **없는** 합성 세계 | 아무것도 못 찾아야 정상 | IC t = −0.56, permutation p = 0.64 ✔ |
| 알파를 **심은** 합성 세계 | 반드시 찾아야 정상 | Q1 −26% → Q5 +38.6% 단조, IC t = 23.4 ✔ |

하네스가 신호를 **만들어내지도, 놓치지도** 않는다는 것을 양방향으로 확인한다.

---

## 4. 코드 구조 (§90)

```
g2b/
├── src/
│   ├── core/        config · log · io · vault(구글드라이브) · http(레이트리밋·체크포인트·스키마레지스트리)
│   ├── collectors/  order_plan · prespec · bid · award · contract · process · dart · synthetic
│   ├── pit/         timestamps(3시각·등급) · revisions(§8) · asof(§7)
│   ├── entity/      dart_crosswalk(사업자번호 exact) · company_history · consortium(§16)
│   ├── graph/       linker(연결 4순위) · lifecycle(§11) · demand_graph(§12)
│   ├── features/    capability · government_demand · eligible_tam · win_features ·
│   │                competition · concentration · g2b_dwa
│   ├── backtest/    universe · portfolio · costs · statistics
│   ├── audit/       prereg · pit_audit · leakage_test · coverage · robustness · mechanism
│   └── pipeline.py  배선 + 산출물 저장(공용/전용 인덱스)
├── scripts/  01_api_depth_audit … 13_generate_report, run_all.py
├── config/   4개 사전등록 YAML (동결 대상)
├── audit/    trial_ledger.json · prereg_hash.txt · 체크포인트
├── tests/    §92 회귀 테스트 + §93 카나리아
└── reports/  00_API_AUDIT … FINAL_DECISION.md
```

전부 **벡터화**되어 있다 — 기업 루프도 월 루프도 없다. lifecycle 은 scipy
`connected_components`, capability 는 감쇠 영향창 전개 + `groupby.sum`, as-of 는 `merge_asof`.
합성 세계 10만 이벤트 기준 전 과정 **72초**.

---

## 5. 판정 체계 (§96)

`STRONG_PASS` · `PASS` · `WEAK_EVIDENCE` · `NO_ALPHA` · `DATA_BLOCKED` · `PIT_BLOCKED` · `SAMPLE_COLLAPSE`

**`DATA_BLOCKED` 와 `NO_ALPHA` 를 반드시 구분한다.**
데이터가 부족해서 검증하지 못한 전략을 성과부진 전략으로 기각하지 않는다.

`reports/FINAL_DECISION.md` 가 §95 의 17개 질문에 답한다. 그중 10번이 이 연구의 존재 이유다:

> **"낙찰금액/시가총액"이라는 단순 전략보다 복잡한 Demand Graph 가 실제로 우월한가?**
> 복잡성이 단순모델을 명백히 이기지 못하면 **단순모델을 채택한다**(§99).

`§84` 비교표는 다섯 모델을 같은 테이블에 놓는다: Award Amount only / Award÷MCap /
Demand Shift only / Win Acceleration only / **Demand-Win Alignment**.

---

## 6. 하지 않는 것 (§98)

- 현재 상장기업 목록·기업명·자회사 관계를 과거에 소급
- 현재 계약 최종값을 최초공고 시점에 사용, 향후 낙찰자를 과거 입찰신호에 사용
- 미래 매출로 과거 award/sales 계산
- 한 조달사업을 plan+bid+award+contract 로 중복계산
- 공동수급 계약액을 모든 참여기업에 전액 배분 (지분 불명이면 `UNKNOWN_SHARE_CONSORTIUM` 으로 **제외**)
- 결과를 본 뒤 lookback/window/threshold 선택, 성과 좋은 품목·연도만 사후 선택
- 유찰률·낙찰률의 부호를 성과 보고 뒤집기 (§76 진단용으로만 분리)
- Track A(상장법인 직접 계약)와 Track B(연결 자회사)를 섞어 보고 (§15)

---

⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
