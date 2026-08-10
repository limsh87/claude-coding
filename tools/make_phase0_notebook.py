#!/usr/bin/env python3
"""phase0_altdata_3axis_validation.py  →  .ipynb (마크다운 1 + 코드 1 셀).

명령서 §6.1: "단일 코드 셀로 통합한다. 진단용 셀을 여러 개로 쪼개지 말 것."
→ 코드 셀은 정확히 1개이고, 그 내용은 .py 원본과 바이트 단위로 동일하다.
   (.py 를 편집하고 이 스크립트를 다시 돌리는 것이 노트북 갱신 방법이다.)

    python3 tools/make_phase0_notebook.py [--check]

--check 는 노트북이 .py 와 동기화되어 있는지만 검사하고 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "phase0", "phase0_altdata_3axis_validation.py")
OUT = os.path.join(ROOT, "phase0", "phase0_altdata_3axis_validation.ipynb")

INTRO = """# PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.0

시가총액 **하위 1,000종목** 유니버스에 대해 아래 3축이 기계적으로 수집 가능한지,
어느 정도의 커버리지와 과거 깊이를 갖는지를 **숫자로** 확인한다.

| 축 | 데이터 | 원재료로서의 용도 |
|---|---|---|
| A | DART 임원현황 | 이사·임원 겸직 네트워크 |
| B | Google Patents (BigQuery) | 기업 단위 특허 품질 지표 |
| C | 국민연금 사업장 월별 가입자 | 월간 고용 flow |

**하지 않는 것** — 팩터 계산 · 시그널 생성 · 포트폴리오 구성 · 수익률 산출 · 알파 주장 ·
3축 결합 분석 · 실패 축의 즉흥 우회. 이 금지사항은 코드 상단 `CONTRACTS` 로 선언되고
실행 직전 자기 소스 AST 검사로 강제된다 (위반 시 수집을 시작하지 않는다).

---

## 실행 전 준비 — 인증정보 3종

아래 셀 상단 "0. 인증정보" 블록에 직접 붙여넣거나, 환경변수로 넣는다 (환경변수 우선).

| 변수 | 필요한 축 | 발급처 | 소요 |
|---|---|---|---|
| `DART_API_KEY` | A (C 보조) | <https://opendart.fss.or.kr/> → 인증키 신청 | 이메일 인증 즉시 |
| `DATA_GO_KR_KEY` | C | <https://www.data.go.kr/> → "국민연금 가입 사업장 내역" 활용신청 | 즉시 ~ 2 영업일 |
| `BQ_PROJECT_ID` + GCP 인증 | B | <https://console.cloud.google.com/> (결제 계정 연결 필수) | 수십 분 |

- 공공데이터포털은 반드시 **일반 인증키(Decoding)** 를 쓴다. Encoding 키를 넣으면 이중
  인코딩으로 실패한다 (코드가 자동 감지해 교정하고 경고를 남긴다).
- BigQuery 는 결제 정보가 없으면 조회 자체가 거부된다 → 축 B 는 `BLOCKED_PREREQ` 로 판정하고
  즉시 종료한다. 우회하지 않는다.
- 키가 하나도 없어도 셀은 끝까지 돌아간다. 없는 축은 `BLOCKED_PREREQ` 로 기록된다.

## 실행

아래 코드 셀 **하나만** 실행한다. 셀을 쪼개지 말 것.

- 중단 후 다시 실행하면 이미 받은 것은 건너뛴다 (skip-if-exists).
- DART 일일 한도(20,000)에 걸리면 깨끗하게 멈춘다. 다음 날 재실행하면 정확히 이어받는다.
- 전체 시간 예산은 4시간이다. 초과가 예상되면 `T_PAST` 시점을 생략하고 그 사실을
  판정표의 `known_limitations` 에 기록한다.

## 산출물 — `<PROJECT_ROOT>/cache/reports/`

| 파일 | 내용 |
|---|---|
| `phase0_verdict.json` / `.csv` | 축 × 기준일 판정표 (게이트별 측정값·임계·통과 여부) |
| `phase0_summary.md` | 축별 GO/STOP 과 근거 수치 (사실과 숫자만) |
| `manual_check_A_coexec_links.csv` | 겸직 링크 200건 — **사람이** 판정 (게이트 A-4) |
| `manual_check_C_workplace_match.csv` | 사업장 매칭 100건 — **사람이** 판정 (게이트 C-5) |
| `phase0_run_log.txt` | 실행 로그 |

> 게이트를 통과시키려고 기준을 조정하지 않는다. 기준 미달은 미달로 보고한다.
> 세 축 중 하나만 통과해도 이 작업은 성공이고, 세 축 모두 실패해도 그 사실이 정확히
> 측정되었다면 성공이다.
"""


def build(code: str) -> dict:
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": INTRO.splitlines(keepends=True)},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
             "source": code.splitlines(keepends=True)},
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    with open(SRC, encoding="utf-8") as fh:
        code = fh.read()
    nb = build(code)
    text = json.dumps(nb, ensure_ascii=False, indent=1) + "\n"

    if "--check" in sys.argv:
        if not os.path.exists(OUT):
            print(f"FAIL: {OUT} 이 없습니다. tools/make_phase0_notebook.py 를 실행하세요.")
            return 1
        with open(OUT, encoding="utf-8") as fh:
            cur = json.load(fh)
        cells = [c for c in cur["cells"] if c["cell_type"] == "code"]
        if len(cells) != 1:
            print(f"FAIL: 코드 셀이 {len(cells)}개입니다 (§6.1 은 1개를 요구).")
            return 1
        if "".join(cells[0]["source"]) != code:
            print("FAIL: 노트북 코드 셀이 .py 와 다릅니다. 재생성하세요.")
            return 1
        print(f"OK: 코드 셀 1개 · .py 와 동일 ({len(code.splitlines()):,}줄)")
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"생성: {OUT}  (코드 셀 1개 · {len(code.splitlines()):,}줄 · {len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
