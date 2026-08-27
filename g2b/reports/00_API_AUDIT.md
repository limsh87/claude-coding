# 00 · API 백필 감사

_명세 §5 — 메타데이터를 믿지 않고 실측한다_

> ⚠ **SMOKE 모드 산출물입니다 — 합성 데이터이며 연구 결론이 아닙니다.**

| 항목 | 값 |
|---|---|
| run_id | `run_20260820_021409_460be8` |
| 실행모드 | `SMOKE` |
| git_commit | `145e92445f80` |
| config_hash | `5208bc433cf7c463` |
| 생성시각 | 2026-08-20T02:14:09 |
| FUTURE_RETURN_LOCK | `False` |

## 왜 이 문서가 먼저인가

공식 메타데이터의 시간범위는 '그 기간의 데이터가 API 로 나온다'는 보장이 아니다. 특히 낙찰정보서비스는 공식 표기가 사실상 실시간이므로 historical depth 를 직접 재야 한다. 여기서 데이터가 없다고 판명되면 그것은 전략 실패가 아니라 **DATA_BLOCKED** 다(§96).

## API별 실측 요약

| API | 포털ID | 공식표기 | 최초 실측연도 | 마지막 실측연도 | 실측 건수합 | 사용가능 |
|---|---|---|---|---|---|---|
| award | 15129397 | 실시간(공식표기) → 실측 필요 | nan | nan | 0 | NO_DATA |
| bid | 15129394 | 1995-10~ (공식표기) | nan | nan | 0 | NO_DATA |
| contract | 15129427 | 2004-07~ | nan | nan | 0 | NO_DATA |
| order_plan | 15129462 | 2004-12~ | nan | nan | 0 | NO_DATA |
| prespec | 15129437 | 사전규격 공개 개시 이후 | nan | nan | 0 | NO_DATA |
| process | 15129459 | 미상 | nan | nan | 0 | NO_DATA |

## 표본연도별 실측

| API | 연도 | 건수 | 총건수(API보고) | 캐시 | 신규 | 메시지 | 오류 | cov_doc_id | cov_amount | cov_event_time | cov_expected_price | cov_supplier_bizno |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| order_plan | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| order_plan | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| prespec | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  |  |
| bid | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| bid | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 |  |
| award | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| award | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| contract | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| contract | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 |  | 0 |
| process | 1995 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2000 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2005 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2010 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2015 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2020 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2023 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2024 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2025 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
| process | 2026 | 0 | nan | 0 | 0 |  | NO_KEY | 0 | 0 | 0 | 0 | 0 |
