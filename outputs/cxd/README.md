# CXD (F-11) — 관세청 통관데이터 기반 산업-기업 성장 괴리

U250-F1 엔진 위에 얹는 신규 팩터. 사전등록 명세 v1.0 의 실행체다.
**CXD 는 C1 멤버십을 읽기만 하고 쓰지 않는다** — 유니버스 엔진을 건드리지 않는다.

```bash
python3 run_cxd.py --regime MECHANISM                 # Phase 0 만 (기본)
python3 run_cxd.py --regime NULL                      # 기제 제거 → KILL-1 발동 확인
python3 run_cxd.py --open-returns "사유"               # 사람이 잠금을 열면 Phase 2 까지
python3 tools/cxd_placebo.py MECHANISM 24             # 하네스 위양성률 측정
```

## 모듈

| 파일 | 역할 |
|---|---|
| `spec.py` | 사전등록 상수 동결(`SpecLock`) · arm 등록기(KILL-6) · `ReturnLock` · 정직성 기록 |
| `factor.py` | §3.1 정의의 벡터화 구현 — IEG · TREND/CYCLE · FGR · DIV · CXD |
| `data.py` | 캐시 레이크(adopt-by-reference) · 실데이터 어댑터 · 합성 하네스 |
| `gates.py` | 카나리 5항목 · G-C0~G-C8 · 상관 감사 · Phase 0 판정 |
| `backtest.py` | 신호 진단(수익률 불요) · 백테스트(잠금 통과 필수) · BH-FDR · KILL-5 |
| `pipeline.py` | PART 6 STEP 1~10 오케스트레이션 |

## 속도 규율 — 시점 루프를 쓰지 않는다

- `IEG`(12M 로그차분) · `TREND`(60M 롤링 OLS) · `CYCLE` 은 셀×월 행렬 위 `cumsum` 으로 계산한다.
- 횡단면 회귀(`DIV`, 잔차화)는 시점별 루프 대신 **정규방정식의 groupby 합**으로 일괄 해를 구한다.
  시점 T개·회귀변수 k개면 `bincount` 를 `k(k+1)/2 + k` 번만 돌리고 `(T,k,k)` 를 한 번에 푼다.

## 조용히 틀리는 지점 (전부 코드로 막아두었다)

1. **달력 연속성.** `pivot` 은 전 셀이 결측인 달의 컬럼을 통째로 없앤다. 그대로 두면 12M·60M 창이
   달력상 떨어진 구간을 이어붙여 IEG·TREND 가 왜곡된다 → `exp_matrix` 가 전 구간을 `reindex` 한다.
2. **결측을 0으로 밀지 않는다.** 수출이 끊긴 달을 0으로 밀면 `log` 가 −∞ 로 가서 TREND 가 인위적으로
   음이 된다 — 구조적 쇠퇴 판정이 통째로 뒤집힌다.
3. **게이트 축과 신호 축이 다르다.** G-C3 는 중분류, 신호는 세분류다(R-09). 세분류 IEG 를 중분류
   라벨로 재사용하면 한 중분류가 하위 셀 수만큼 중복되어 상관계수가 셀 수가 아니라 하위 셀 수에 좌우된다
   → `axis_cell_panel` 이 그 층에서 **먼저 합산한 뒤** IEG 를 계산한다.
4. **차분이 아니라 곱.** `resid(· ~ P_RS + P_EG)` 는 `g_기업 − g_산업` 의 기업 성분을 지워
   "부진 산업 통째 매수"로 축퇴시킨다(R-03). 곱항은 각 성분에 선형적으로 직교하므로 살아남는다.

## 하네스가 스스로를 반증한다

합성 세계는 **기본이 귀무**다. R-07 연결과 R-04 SNR 구조는 심되 **수익률에는 알파를 심지 않는다.**
파이프라인이 합성에서 알파를 만들어내면 그것은 데이터가 아니라 버그라는 뜻이다.

- `NULL` — 기제 제거 → G-C3 실패 → **KILL-1 발동, 실행 중단** (확인됨)
- `MECHANISM` — 알파 0 → 시드 24개에서 평균 IC −0.0015, p<0.05 비율 4.2%(기대 5%) → **누수 없음**
- `ALPHA_PLANT` — 양성 대조군 → 심은 알파를 BH-FDR q=0.10 이 검출 (확인됨)

## 알려진 한계

`docs/cxd/phase0_report.html` 의 정직성 기록을 함께 읽을 것. 특히 관세청 과거 vintage 부재로
개정 look-ahead 는 **영구 UNVERIFIED** 이며, ISTANS HS↔KSIC 연계 정밀도는 미측정이다.
