#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""phase0_altdata_3axis_v11.py → 코랩용 단일 셀 노트북(.ipynb) 생성기.

명세 §8.6 은 "단일 코드 셀로 통합, 진단용 셀을 여러 개로 쪼개지 말 것"을 요구한다.
코드 셀은 정확히 하나다(맨 위 안내용 마크다운 셀 하나만 추가).

.py 를 고친 뒤에는 반드시 이걸 다시 돌려서 노트북을 맞춘다:
    python3 phase0/make_notebook.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "phase0_altdata_3axis_v11.py")
OUT = os.path.join(HERE, "phase0_altdata_3axis_v11.ipynb")

INTRO = """# PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.1

아래 **셀 하나**가 전부다. 실행하면 계약 검사 → (SELFTEST면) 자가검정 → 판정표까지 나온다.

## 처음 한 번

그냥 실행한다. `RUN_MODE = "SELFTEST"` 이라 **네트워크도 키도 필요 없고** 약 20초 만에
측정 로직 36개 항목이 검증된다. 여기서 실패가 나오면 실측을 돌릴 이유가 없다.

## 실측

셀 상단 설정 블록에서 키를 채우고 `RUN_MODE = "FULL"` 로 바꾼다.

| 축 | 필요한 것 | 없으면 |
|---|---|---|
| A / A-Δ | `DART_API_KEY` — https://opendart.fss.or.kr | `BLOCKED_PREREQ` |
| B | `GOOGLE_APPLICATION_CREDENTIALS` + `GCP_PROJECT` | `BLOCKED_PREREQ` |
| C | `DATA_GO_KR_KEY` — https://www.data.go.kr (일반 인증키 **Decoding**) | `BLOCKED_PREREQ` |

`!pip install pykrx finance-datareader google-cloud-bigquery` — 없는 축만 시끄럽게 실패한다.

## 코랩에서 알아둘 것

- 작업 루트는 자동으로 `/content/phase0` 이 된다.
- `/content` 는 세션이 끝나면 사라지므로 계약 `P0_RUNTIME_ROOT` 는 **PASS 가 아니라 `WAIVED`** 로
  기록되고, 그 사실이 모든 판정표의 `known_limitations` 에 실린다.
- 대신 **구글드라이브 콜드 백업**이 켜져 있다. 원본 API 응답을 `MyDrive/phase0_cache/` 에
  아카이브로 보관하고 다음 실행에서 되살려서 **DART 일일 한도(19,000회)를 다시 태우지 않는다.**
  첫 실행 때 드라이브 마운트 승인 창이 뜬다.
- 산출물: `/content/phase0/cache/reports/` (드라이브 백업 폴더에도 복사된다)

## 이 코드가 하지 않는 것

팩터 계산 · 시그널 생성 · 수익률 산출 · 알파 주장 · 축 간 결합 분석 · 게이트 미달 시 임계값 조정.
`P0_NO_STRATEGY` 가 셀 원문을 토큰 단위로 검사해서 강제한다.
"""


def build() -> dict:
    with open(SRC, encoding="utf-8") as f:
        code = f.read()
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": INTRO.splitlines(keepends=True)},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
             "source": code.splitlines(keepends=True)},
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": [], "toc_visible": True},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


if __name__ == "__main__":
    nb = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
        f.write("\n")
    n_code = sum(1 for c in nb["cells"] if c["cell_type"] == "code")
    print(f"{OUT}  (코드 셀 {n_code}개, {os.path.getsize(OUT):,} bytes)")
