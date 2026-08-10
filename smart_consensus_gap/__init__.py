# -*- coding: utf-8 -*-
"""SCG_ORIGINAL_REPRO_V1 — 스마트 컨센서스 갭 / IBK 서프라이즈 포트폴리오 재현.

원문: IBK투자증권 이정빈, 「바텀업 퀀트 – 알파 포트폴리오 전략」(2020-08-20)

이 패키지는 두 가지를 엄격히 분리한다.
  · ORIGINAL_EXACT : 벤더(FnGuide/Quantiwise)의 smart consensus + surprise probability 를
                     실제로 확보한 경우에만 쓰는 경로.
  · PUBLIC_REPRO   : 공개 애널리스트 추정치로 smart consensus 를 재구성한 경로.
                     이것을 "FnGuide 스마트컨센서스 정확 재현"이라고 부르지 않는다.

사용:
    from run_smart_consensus_gap import run
    run()
"""
from __future__ import annotations

from .config import SPEC_ID, SCGConfig, base_config

__all__ = ["SPEC_ID", "SCGConfig", "base_config"]
__version__ = "1.0.0"
