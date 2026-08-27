# 02 · 기업 매핑

_명세 §13 §14 §52_

> ⚠ **SMOKE 모드 산출물입니다 — 합성 데이터이며 연구 결론이 아닙니다.**

| 항목 | 값 |
|---|---|
| run_id | `run_20260820_021409_460be8` |
| 실행모드 | `SMOKE` |
| git_commit | `145e92445f80` |
| config_hash | `5208bc433cf7c463` |
| 생성시각 | 2026-08-20T02:14:09 |
| FUTURE_RETURN_LOCK | `False` |

## 원칙

PRIMARY 는 **사업자등록번호 exact match** 뿐이다. 상호 fuzzy matching 은 candidate generation 용도로만 쓰고 자동 확정하지 않는다. 현재 stock_code 를 과거 전체에 소급하지 않으며, 유효기간 밖의 매핑은 `OUT_OF_VALIDITY` 로 격리한다.

## 금액기준 매칭 품질 (§52)

| map_type | 건수 | 금액 | 금액비중 |
|---|---|---|---|
| UNMATCHED | 43406 | 3.431e+13 | 0.7164 |
| EXACT_ID | 17388 | 1.358e+13 | 0.2836 |

| 지표 | 값 |
|---|---|
| exact_amount_share | 0.283613317493856 |
| ambiguous_share | 0.0 |
| unmatched_share | 0.716386682506144 |
| out_of_validity_share | 0.0 |
| exact_among_identified | 1.0 |
| verdict | PASS |

> 상장사 귀속 금액이 전체 조달의 일부인 것은 정상이다 — 공급자 다수가 비상장이다. 게이트는 '식별된 것 중 exact 비중'으로 본다.
