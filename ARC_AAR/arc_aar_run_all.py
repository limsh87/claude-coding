#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 ARC-AAR : 애널리스트 주의 재배분 (Analyst Attention Reallocation)
           양방향 현시선호 신호 — 커버리지 철회의 인과 분해 포함
           SPEC-C / ARC-AAR 계약문서 단독 구현체 (제로베이스 작성)
================================================================================

■ 실행 방법 (코랩 / 주피터랩 양방향)
  - Colab   : 이 파일 전체를 셀 하나에 붙여넣고 실행하거나,
              업로드 후  %run arc_aar_run_all.py
  - JupyterLab(로컬/Windows) :  %run arc_aar_run_all.py
  - 터미널  :  python arc_aar_run_all.py
  단일 파일 = 원셀 실행형이며 내부는 아래 모듈 섹션으로 분리되어 있어
  에러 발생 시 [스테이지 ID / 섹션 번호]가 로그에 명시된다.

■ 내부 모듈 구조 (거시 흐름)
  [S00] 자격증명 입력부 (KRX 마켓플레이스 ID/PW, DART 키 — 최상단 고정)
  [S01] 사전등록 파라미터 / 실행 설정 (계약 §4, §6.6 — 변경 금지 항목 명시)
  [S02] 실행환경 감지 (Colab/JupyterLab/Windows), 의존성 자동설치,
        구글드라이브 마운트/탐지, 프로젝트 루트 자동 해석, 로깅
  [S03] 캐시 3계층(raw/parsed/features) + 공용인덱스/전용인덱스 관리자
        - 절대 1원칙: 기존 인덱스 무손상(append-only + 백업 + 검증 후 원자적 교체)
        - 로컬(D드라이브 포함) + 구글드라이브 양측 캐시 탐색, 신규 수집분은
          전부 드라이브에 저장(드라이브 부재 시 pending 큐 후 재동기화)
  [S04] 네트워크 계층: 레이트리밋, 지수백오프, 서킷브레이커(연속 10회 실패 중단),
        실시간 잔여 호출량 추적(QuotaTracker — 고정 예산 가정 금지), 카나리 점검
  [S05] 시장데이터 허브: pykrx→KRX(로그인)→FDR→네이버→yfinance 다중소스 폴백,
        월말 PIT 스냅샷, 수정주가, 상장폐지 추론, 섹터, 벤치마크
  [S06] 리포트 메타 수집: 네이버 금융 리서치 + 한경 컨센서스, PDF 애널리스트 추출,
        금투협 전문인력 조회(베스트에포트), DART 공시/실적월, 컨센서스 EPS
  [S07] PIT 유니버스 구축 (생존편향 제거 — 상장폐지 종목 포함)
  [S08] Phase 0 데이터 실현가능성 게이트 (analyst_id 확보율 → 진행 모드 결정)
  [S09] 주의 패널: N, share, base, EA + 경험적 베이즈 축소추정
  [S10] §6.3 기계적 발간 통제회귀 (확장 윈도우 재귀 추정 = look-ahead 금지) → VAS
  [S11] 커버리지 철회 인과 분해: M-EXIT / V-DROP / H-EXIT
  [S12] 신호 12개 구성 (ω 3종 × λ 2종 × 보유 2종 — 확장 금지)
  [S13] 백테스트 엔진 (익영업일 앵커, 연도별 거래세, 비용 0/기본/2배)
  [S14] 이벤트 스터디 (3군 CAR, M-EXIT 플라시보 우선)
  [S15] 통계 검증: 블록부트스트랩, PBO(CSCV), DSR, 워크포워드, BH-FDR,
        뉴이-웨스트, 그레인저(H5), IPW 결측 민감도
  [S16] 산출물 기록 (계약 §10 전체) + 데이터 계보(lineage)/원장연결 점검표
  [S17] 비교전략: 시가총액 하위 1000종목 압축 유니버스 별도 백테스트
  [S18] SYNTH 모드: 네트워크 없이 전체 파이프라인 자가검증(파이프라인 무결성 테스트)
  [S19] main() 오케스트레이터 (스테이지 러너, 체크포인트, 에러 위치 특정)

■ 계약문서 최우선 규칙 이행 요약
  1. Look-ahead 금지  : 신호는 월말까지 공개분만 사용, 진입은 익영업일 종가.
                        통제회귀는 확장윈도우 재귀추정(월 t 신호에 t 이후 데이터 불사용).
  2. PIT 유니버스     : 월말 스냅샷 기반, 미래 참조 없음.
  3. 생존편향 제거    : 스냅샷에 당시 상장돼 있던 (이후 폐지된) 종목 전부 포함.
  4. 기계적 발간 통제 : §6.3 통제회귀를 건너뛰는 실행 경로 없음.
  5. 사전등록 준수    : §4 가설 5개, §6.6 파라미터 격자 12개 고정. 튜닝 금지.
  ※ 시간예산(발주자 지시로 계약 §8.1 개정): 전체 실행의 강제 상한은 없다.
     대신 '수집 단계'에 4시간 타임박스를 적용한다 — 초과 시 그때까지 수집·캐시된
     데이터만으로 즉시 정제→백테스트→검증을 수행해 '중간(INTERIM) 결과'를 출력하고,
     모든 산출물에 INTERIM 표식과 수집 커버리지(%)를 명기한다. 재실행하면 완료분은
     스킵하고 이어서 수집하므로 커버리지가 점진 확장된다.

■ 모드
  RUN_MODE = "FULL"   : 실데이터 수집 + 전체 파이프라인 (기본)
  RUN_MODE = "SYNTH"  : 합성데이터로 전체 파이프라인 자가검증 (네트워크 불필요)
  RUN_MODE = "CANARY" : 소스 도달성 카나리 점검만 수행
  환경변수 ARC_AAR_MODE 가 있으면 그것이 우선한다.
================================================================================
"""

# ──────────────────────────────────────────────────────────────────────────────
# 표준 라이브러리 (여기서만 import — 이후 섹션은 전부 이 블록에 의존)
# ──────────────────────────────────────────────────────────────────────────────
import os
import io
import re
import sys
import json
import time
import gzip
import math
import shutil
import random
import hashlib
import zipfile
import traceback
import threading
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# 서드파티 필수 (S02에서 자동설치 시도 후 재import 하므로 여기선 지연 로딩)
try:
    import numpy as np
    import pandas as pd
except Exception:                                     # S02.ensure_dependencies 가 처리
    np = None
    pd = None

# ══════════════════════════════════════════════════════════════════════════════
# [S00] 자격증명 / 사용자 입력부  (최상단 고정 — 계약 §2.2)
#       로직 내부 매립 금지. 전부 여기서만 수정한다.
# ══════════════════════════════════════════════════════════════════════════════

# ── ① KRX 정보데이터시스템(마켓플레이스) 계정 ────────────────────────────────
#    발급처 : https://data.krx.co.kr  (우측 상단 [회원가입] → 이메일 인증, 무료 5분)
#    용도   : 2025-12 data.krx.co.kr 이관 이후 일부 통계 화면이 로그인 세션을
#             요구한다(계약 §2.6). 미입력 시에도 pykrx/FDR/네이버/yfinance
#             폴백 체인으로 동작하지만, KRX 직접 조회 성공률이 낮아질 수 있다.
KRX_MP_ID = ""            # 예: "myemail@gmail.com"   (환경변수 KRX_MP_ID 로도 주입 가능)
KRX_MP_PW = ""            # 예: "********"            (환경변수 KRX_MP_PW)

# ── ② DART OpenAPI 인증키 (복수 등록 가능 — 라운드로빈/소진 시 자동 교체) ──
#    발급처 : https://opendart.fss.or.kr → [인증키 신청/관리] (이메일 인증, 무료)
#    한도   : 키당 일 20,000건. 단, 코드에서는 한도를 '고정 가정'하지 않고
#             실제 응답(status '020'=한도초과)과 금일 사용량을 실시간 추적하여
#             남은 만큼만 쓴다(QuotaTracker, S04).
#    용도   : 실적발표월 플래그 + 월별 공시 건수(§6.3 통제변수).
DART_API_KEYS = []        # 예: ["a1b2c3...", "d4e5f6..."]  (환경변수 DART_API_KEYS 콤마구분)

# ── ③ 구글 드라이브 루트 (절대 1원칙 — 신규 수집분은 전부 여기에 저장) ────
#    Colab      : 비워 두면 자동으로 /content/drive/MyDrive 마운트.
#    Windows/맥 : Google Drive for Desktop 이 설치돼 있으면 자동 탐지하지만,
#                 탐지 실패 시 여기에 직접 지정하라. 지정하지 않으면 로컬에만
#                 쌓이고 pending 큐에 남아 다음 실행에서 동기화된다.
#    확인 방법  : 탐색기에서 '내 드라이브' 폴더의 주소창 경로를 그대로 붙여넣기.
#    예)  GDRIVE_ROOT = r"G:\내 드라이브"      /  r"C:\Users\user\Google Drive\My Drive"
GDRIVE_ROOT = ""          # 환경변수 GDRIVE_ROOT 로도 주입 가능

# ── ④ 대화형 입력 허용 여부 ────────────────────────────────────────────────
#    True 이고 위 값이 비어 있으며 노트북/터미널이 대화형이면 getpass 로 1회 질의.
#    (자동화/배치 실행에서는 절대 블로킹하지 않도록 비대화형이면 건너뜀)
PROMPT_FOR_MISSING_CREDENTIALS = True

# ══════════════════════════════════════════════════════════════════════════════
# [S01] 실행 설정 + 사전등록 파라미터 (계약 §4, §6.6 — '변경 금지' 표기 항목은
#       튜닝 대상이 아니다. 격자 확장 시 산출물 전체 무효)
# ══════════════════════════════════════════════════════════════════════════════

class CFG:
    """전역 설정. 사용자 편의를 위해 한 곳에 모았다.
    [고정] 표시는 계약문서상 사전등록 값 — 수정하면 사전등록 위반."""

    # ── 실행 모드 ──────────────────────────────────────────────────────────
    RUN_MODE = os.environ.get("ARC_AAR_MODE", "FULL").upper()   # FULL | SYNTH | CANARY
    RANDOM_SEED = 20260809

    # ── 기간 (발주자 지시: 2016-08 ~ 2026-07 10년 백테스트) ────────────────
    BT_START_MONTH   = "2016-08"    # 백테스트 첫 보유월
    BT_END_MONTH     = "2026-07"    # 백테스트 마지막 보유월
    # 리포트 메타 수집 시작 = BT 시작 − 워밍업.
    #   워밍업 = 베이스라인 룩백 12M + 통제회귀 최소창 24M + 신호월 1M = 37M
    #   → 2016-08 보유월의 신호(2016-07)가 실제로 산출되려면 2013-07부터 필요하다.
    #   이를 계약 §5의 하한(2015-01)보다 앞당겨 잡아야 사전등록 10년 구간이
    #   '조용히 2018년으로 잘리는' 일을 막는다(감사 지적 반영). 계약 하한의 상위집합.
    META_START_MONTH = "2013-07"
    PRICE_START      = "2013-01-01" # 가격 수집 시작 (메타 시작보다 앞서야 함)

    # ── 사전등록 신호 파라미터 [고정 — 계약 §6] ────────────────────────────
    N_MIN_REPORTS      = 3      # N(a,t) < 3 이면 해당 애널리스트-월 결측 (§6.1)
    BASE_LOOKBACK_M    = 12     # 베이스라인 룩백 12개월 (§6.2)
    BASE_MIN_N         = 12     # 룩백 ΣN < 12 이면 결측 (§6.2)
    SHRINK_K_ANALYST   = 8.0    # 축소추정 강도(애널리스트→증권사 prior) [고정]
    SHRINK_K_BROKER    = 12.0   # 축소추정 강도(증권사→섹터 prior) [고정]
    EXIT_PRIOR_QUARTERS = 4     # 직전 4개 분기 연속 커버 요건 (§6.5)
    EXIT_SILENT_MONTHS  = 6     # 커버 중단 확정에 필요한 무발간 개월 수.
                                # 한국 애널리스트의 커버 종목 발간은 실적 시즌 중심의
                                # '분기 리듬'이므로 3개월 침묵은 정상 발간 간격과
                                # 구분되지 않는다(합성 세계 실측: 이벤트의 90%+가
                                # 단순 발간 공백 = 잡음). 두 번의 실적 사이클을
                                # 건너뛴 6개월을 확정 기준으로 삼는다.
                                # 확정 시점 = t+5 월말 → 모든 판정 근거가 관측
                                # 가능하므로 look-ahead 없음.
    EXIT_W_VDROP       = 1.0    # [고정 §6.5] 튜닝 금지
    EXIT_W_HEXIT       = 1.5    # [고정 §6.5] 튜닝 금지

    # ── 사전등록 격자 [고정 — 계약 §6.6 : 3×2×2 = 12개 구성, 확장 금지] ────
    GRID_OMEGA    = ["ew", "npub", "breadth"]  # 비가중 / 발간량 / 커버리지폭
    GRID_LAMBDA   = [0.0, 1.0]                 # 음의 신호 결합계수
    GRID_HOLD_M   = [1, 3]                     # 보유기간(월)

    # ── 포트폴리오 [계약 §7] ───────────────────────────────────────────────
    N_QUANTILES     = 5
    NEG_EXCL_PCT    = 0.10      # AAR_neg 하위 10% 강제 배제
    MIN_HOLDINGS    = 20        # 하한 미달 시 현금 처리 + 로그
    MAX_WEIGHT      = 0.05      # 종목당 상한 5%
    MIN_XSEC_NAMES  = 30        # 분위 형성에 필요한 최소 신호 종목 수(미달 월 현금)

    # ── 거래비용 [계약 §7.1] ───────────────────────────────────────────────
    COMMISSION_BP   = 1.5       # 편도 수수료 1.5bp
    SLIPPAGE_BP     = {"large": 10.0, "mid": 20.0, "small": 35.0}
    SIZE_LARGE_RANK = 200       # 시총 순위 ≤200 → large
    SIZE_MID_RANK   = 700       # 200 < rank ≤ 700 → mid, 이후 small
    COST_SCENARIOS  = {"zero": 0.0, "base": 1.0, "double": 2.0}
    # 증권거래세(+농특세 합산, 매도측) 연도별 테이블 [단일 세율 금지 — §7.1]
    # 출처: 증권거래세법/시행령 개정 연혁 https://www.law.go.kr/법령/증권거래세법
    #       기획재정부 보도자료(2023-· 2024-·2025 인하 로드맵) https://www.moef.go.kr
    #  구간별 (시작일, 종료일, KOSPI합산세율, KOSDAQ세율):
    #   ~2019-06-02   : 0.30% (KOSPI 0.15+농특 0.15 / KOSDAQ 0.30)
    #   2019-06-03~   : 0.25% (KOSPI 0.10+0.15 / KOSDAQ 0.25)
    #   2021-01-01~   : 0.23% (KOSPI 0.08+0.15 / KOSDAQ 0.23)
    #   2023-01-01~   : 0.20% (KOSPI 0.05+0.15 / KOSDAQ 0.20)
    #   2024-01-01~   : 0.18% (KOSPI 0.03+0.15 / KOSDAQ 0.18)
    #   2025-01-01~   : 0.15% (KOSPI 0.00+0.15 / KOSDAQ 0.15)
    TAX_TABLE = [
        ("1900-01-01", "2019-06-02", 0.0030, 0.0030),
        ("2019-06-03", "2020-12-31", 0.0025, 0.0025),
        ("2021-01-01", "2022-12-31", 0.0023, 0.0023),
        ("2023-01-01", "2023-12-31", 0.0020, 0.0020),
        ("2024-01-01", "2024-12-31", 0.0018, 0.0018),
        ("2025-01-01", "2099-12-31", 0.0015, 0.0015),
    ]

    # ── Phase 0 게이트 [계약 §3] ───────────────────────────────────────────
    PHASE0_SAMPLE_MONTHS  = ["2019-06", "2022-03", "2024-11"]
    PHASE0_SAMPLE_SIZE    = 300
    PHASE0_OK_RATE        = 0.70   # ≥70% 정상 진행
    PHASE0_FALLBACK_RATE  = 0.40   # <40% → broker×sector 폴백
    PHASE0_TIMEBOX_HOURS  = 16
    # 계약 §12는 'Phase 0 보고 후 중단·승인 대기'이나, 발주자 원셀 실행 지시에 따라
    # 기본값은 자동 계속. 엄격 게이트를 원하면 False 로 바꾸면 Phase 0 후 중단한다.
    PHASE0_AUTO_CONTINUE  = True

    # ── 통계 검증 [계약 §9] ────────────────────────────────────────────────
    BOOT_BLOCK_DAYS  = 21
    BOOT_N           = 1000
    PBO_N_BLOCKS     = 16          # CSCV S=16
    WF_TRAIN_M       = 60          # 워크포워드 학습 5년
    WF_TEST_M        = 12          # 검증 1년
    FDR_Q            = 0.10        # BH-FDR q
    NW_LAGS_1M       = 3           # 뉴이-웨스트 랙(월간, 1M 보유)
    NW_LAGS_3M       = 4           # 3M 보유(중첩) 시
    EVENT_CAR_DAYS   = 120         # 이벤트 스터디 t+1..t+120 영업일
    N_TRIALS_DSR     = 12          # DSR 시도 횟수 = 격자 12 [고정]

    # ── 수용/폐기 기준 [계약 §11] ──────────────────────────────────────────
    ACCEPT_MIN_EXCESS_PA = 0.03    # 동일가중 유니버스 대비 연 3%p (기본 비용)
    ACCEPT_MAX_PBO       = 0.5
    T_CRIT               = 2.0

    # ── 수집 안전장치 [계약 §2.3] ──────────────────────────────────────────
    MAX_WORKERS        = 4         # ThreadPoolExecutor 상한(보수적)
    CB_MAX_CONSEC_FAIL = 10        # 서킷 브레이커: 연속 실패 10회 → 소스 중단
    HTTP_TIMEOUT       = 20
    RETRY_BACKOFF      = [2, 4, 8]  # 지수 백오프(초). 403/404 는 여기 타지 않는다.
    RATE_FACTOR_MIN    = 0.35      # 적응형 페이싱 하한(정상 구간에서 최대 ~3배 가속)
    RATE_FACTOR_MAX    = 8.0       # 차단 신호 시 상한
    BASE_DELAY = {                 # 소스별 기본 랜덤 딜레이(초) — 적응형으로 조정됨
        "naver_research": (0.25, 0.6), "hankyung": (0.35, 0.8),
        "pykrx": (0.20, 0.5), "krx": (0.35, 0.8), "dart": (0.04, 0.12),
        "naver_chart": (0.12, 0.35), "fdr": (0.08, 0.25), "yfinance": (0.3, 0.8),
        "kofia": (0.6, 1.2), "fnguide": (0.4, 0.9), "kind": (0.4, 0.9),
        "fdrcache": (0.05, 0.15),      # GitHub raw — 정적 CSV, 제한 완화
    }
    PROGRESS_HEARTBEAT_S = 20      # 워치독 출력 주기(초) — 침묵 방지

    # ── 요청 예산: '실행 전체' 기준. 월당 한도는 개월 수를 곱하면 폭발한다 ──
    #   네이버 상세 페이지는 1요청당 리포트 1건 → 확장성이 없으므로 예산제로 묶고,
    #   확장 가능한 경로(한경 리스트: 1요청당 최대 80건)를 주력으로 삼는다.
    BUDGET_NAVER_DETAIL = 12000    # 상세 페이지 총 요청 상한
    BUDGET_PDF          = 300      # PDF 다운로드 총 상한(기본 경로 아님)
    PHASE0_DETAIL_PER_MONTH = 60   # Phase 0 확보율 측정용 표본(가볍게)

    # ── 기능 플래그 ────────────────────────────────────────────────────────
    AUTO_PIP                 = True    # 부족 의존성 pip 자동 설치(코랩/로컬 공통)
    # PDF 작성자 추출은 요청당 산출량이 극도로 낮고(1건/수 MB), 증권사 PDF 상당수가
    # 깨진 xref 를 가져 pypdf 경고를 대량 발생시킨다. 기본 비활성 — 확장 가능한
    # 경로(한경 리스트, 네이버 상세)로 확보율이 부족할 때만 소량 보조로 켠다.
    EXTRACT_ANALYST_FROM_PDF = False
    PDF_MAX_MB               = 2.0
    COLLECT_INVESTOR_RATIO   = True    # H4 개인 매매비중(과중 시 프록시 폴백)
    RECURSIVE_CONTROLS       = True    # §6.3 통제회귀 확장윈도우 재귀추정(look-ahead 차단)
    CTRL_MIN_WINDOW_M        = 24      # 재귀추정 최소 표본 개월
    FORCE_STAGES             = set()   # 예: {"ST06"} 해당 스테이지 캐시 무시 재계산
    SAVE_PLOTS               = True    # matplotlib 있으면 CAR/에쿼티 곡선 png 저장

    # ── 가격 수집(반복 조회 제거) ──────────────────────────────────────────
    PRICE_INCREMENTAL     = True   # 캐시 마지막 날짜 다음날부터만 받아 append
    PRICE_REFRESH_DAYS    = 5      # 캐시가 이 일수 이내면 아예 건드리지 않음
    PRICE_NODATA_COOLDOWN = 30     # 데이터 없는 티커(상폐 등) 재시도 금지 일수
    PRICE_BULK_BY_DATE    = True   # 증분 구간은 '날짜별 전종목' 1콜로 일괄 수집

    # ── 시간 예산 ──────────────────────────────────────────────────────────
    # 발주자 지시: 수집(다운로드) 단계에만 4시간 타임박스. 초과 시 수집을 우아하게
    # 멈추고 그때까지의 캐시만으로 백테스트 이후 단계를 전부 수행(INTERIM 결과).
    # 계산 단계(패널/백테스트/검증)는 시간 제한 없음.
    COLLECT_TIMEBOX_HOURS = 4.0
    BUDGET_MIN = {"phase0": 20, "meta_collect": 120, "kofia": 30,
                  "panel": 35, "backtest": 20, "stats": 25}   # 참고 로깅용

# 사전등록 가설 정의(계약 §4) — 보고서 생성에 사용
HYPOTHESES = {
    "H1": "기계적 요인 통제 후 자발적 주의 증가(VAS+)는 이후 1~3개월 수익률을 양(+)으로 예측한다",
    "H2": "효과는 애널리스트 기회비용이 클수록 강하다 (기회비용 가중 > 비가중)",
    "H3": "자발적 철회(V-DROP)는 음(-) 예측력, 기계적 철회(M-EXIT)는 예측력 없음",
    "H4": "효과는 저커버리지·소형주·고개인비중 종목에서 강하다",
    "H5": "VAS는 컨센서스 EPS 개정에 선행한다 (그레인저 방향성)",
}

# ══════════════════════════════════════════════════════════════════════════════
# [S02] 실행환경 감지 / 의존성 / 구글드라이브 / 프로젝트 루트 / 로깅
# ══════════════════════════════════════════════════════════════════════════════

def _in_colab():
    return "google.colab" in sys.modules or os.environ.get("COLAB_RELEASE_TAG") is not None

def _in_notebook():
    try:
        from IPython import get_ipython           # noqa
        ip = get_ipython()
        return ip is not None and "IPKernelApp" in getattr(ip, "config", {})
    except Exception:
        return False

def _is_windows():
    return os.name == "nt"


def ensure_dependencies():
    """필수/선택 의존성 확인, 부족분은 (허용 시) pip 자동 설치.
    실패해도 폴백 경로가 있으므로 가능한 한 진행한다."""
    global np, pd
    required = {"numpy": "numpy", "pandas": "pandas"}
    optional = {
        "requests": "requests", "bs4": "beautifulsoup4", "lxml": "lxml",
        "pyarrow": "pyarrow", "pykrx": "pykrx",
        "FinanceDataReader": "finance-datareader", "yfinance": "yfinance",
        "pypdf": "pypdf", "tqdm": "tqdm", "matplotlib": "matplotlib",
    }
    def _try(mod):
        try:
            __import__(mod)
            return True
        except Exception:
            return False
    def _pip(pkgs):
        """패키지를 '하나씩' 설치한다. 한 번에 묶으면 휠이 없는 패키지 하나 때문에
        배치 전체가 실패해 아무것도 설치되지 않는다(Python 3.14 처럼 새 런타임에서
        빈번). 개별 설치는 실패한 것만 건너뛴다."""
        if not pkgs or not CFG.AUTO_PIP:
            return
        for p in pkgs:
            try:
                print(f"[S02] pip 설치: {p}", flush=True)
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-q", p], timeout=420)
            except Exception as e:
                print(f"[S02][경고] {p} 설치 실패({str(e)[:80]}) — 폴백 경로로 진행",
                      flush=True)

    missing_req = [p for m, p in required.items() if not _try(m)]
    _pip(missing_req)
    import numpy as _np, pandas as _pd            # noqa — 실패 시 여기서 명확히 죽는다
    np, pd = _np, _pd

    if CFG.RUN_MODE != "SYNTH":                    # SYNTH 는 numpy/pandas 만으로 동작
        missing_opt = [p for m, p in optional.items() if not _try(m)]
        _pip(missing_opt)
    avail = {m: _try(m) for m in list(required) + list(optional)}
    return avail


def mount_google_drive():
    """구글드라이브 루트 탐지. 우선순위:
       S00 GDRIVE_ROOT 직접 지정 → 환경변수 → Colab 마운트 → 데스크톱 앱 경로 프로브.
    반환: (drive_root: Path|None, how: str)"""
    explicit = (GDRIVE_ROOT or os.environ.get("GDRIVE_ROOT") or "").strip().strip('"')
    if explicit:
        p = Path(explicit)
        try:
            if p.exists() and p.is_dir():
                return p, "S00 직접지정"
            p.mkdir(parents=True, exist_ok=True)
            return p, "S00 직접지정(신규생성)"
        except Exception as e:
            print(f"[S02][경고] GDRIVE_ROOT 사용 불가({p}): {e}")
    if _in_colab():
        try:
            mp = Path("/content/drive")
            if not (mp / "MyDrive").exists():
                from google.colab import drive as _gdrive     # noqa
                _gdrive.mount(str(mp), force_remount=False)
            if (mp / "MyDrive").exists():
                return mp / "MyDrive", "colab_mount"
        except Exception as e:
            print(f"[S02][경고] Colab 드라이브 마운트 실패: {e}")
        return None, "colab_mount_failed"
    # 로컬(Windows/맥/리눅스): Google Drive for Desktop 마운트 지점 프로브.
    # 데스크톱 앱은 드라이브 문자 바로 아래 또는 '내 드라이브' 하위에 붙는다.
    cands = []
    if _is_windows():
        for dl in "GHIJKLMNOPQRSTUVWXYZDEF":
            base = Path(f"{dl}:/")
            cands += [base / "내 드라이브", base / "My Drive", base / "내드라이브"]
            # 스트리밍 모드: X:\<계정>\내 드라이브 형태
            try:
                if base.exists():
                    for sub in list(base.iterdir())[:12]:
                        if sub.is_dir():
                            cands += [sub / "내 드라이브", sub / "My Drive"]
            except Exception:
                pass
    home = Path.home()
    for nm in ("Google Drive", "GoogleDrive", "Google 드라이브"):
        cands += [home / nm / "My Drive", home / nm / "내 드라이브", home / nm]
    cands += [home / "Library" / "CloudStorage"]          # macOS
    for c in cands:
        try:
            if c.exists() and c.is_dir():
                return c, "desktop_drive"
        except Exception:
            continue
    return None, "not_found"


def quiet_noisy_libraries():
    """pypdf 등이 stdout/stderr 로 직접 쏟아내는 파싱 경고를 억제한다.
    (증권사 PDF 상당수가 깨진 xref 를 가져 정상 동작 중에도 대량 출력된다)"""
    import logging
    import warnings
    for name in ("pypdf", "PyPDF2", "pdfminer", "fontTools", "urllib3",
                 "yfinance", "peewee"):
        try:
            logging.getLogger(name).setLevel(logging.CRITICAL)
            logging.getLogger(name).propagate = False
        except Exception:
            pass
    warnings.filterwarnings("ignore", category=UserWarning, module="pypdf")
    warnings.filterwarnings("ignore", message=".*startxref.*")
    warnings.filterwarnings("ignore", category=FutureWarning)
    try:
        logging.captureWarnings(True)
    except Exception:
        pass


def resolve_project_root():
    """프로젝트 루트 런타임 자동 감지 (경로 하드코딩 금지 — 계약 §2.1).
    우선순위: 환경변수 ARC_AAR_ROOT → 기존 .kr_data_work 발견 위치(홈/D:/C:)
             → Colab 이면 드라이브 내부 → 홈 디렉토리 신규 생성."""
    env_root = os.environ.get("ARC_AAR_ROOT")
    if env_root:
        p = Path(env_root)
        p.mkdir(parents=True, exist_ok=True)
        return p
    home = Path.home()
    probes = [home / ".kr_data_work" / "ARC_AAR"]
    if _is_windows():
        for dl in ["D", "E", "C"]:
            probes += [Path(f"{dl}:/.kr_data_work/ARC_AAR"),
                       Path(f"{dl}:/kr_data_work/ARC_AAR")]
    for p in probes:
        try:
            if p.parent.exists():
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            continue
    p = home / ".kr_data_work" / "ARC_AAR"
    p.mkdir(parents=True, exist_ok=True)
    return p


class RunLogger:
    """콘솔 + 파일 동시 로깅. 스테이지 배너/키값 요약/에러 위치 특정 지원."""
    def __init__(self, log_dir):
        self.t0 = time.time()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._fh = open(self.path, "a", encoding="utf-8")
        self._lock = threading.Lock()
        try:                                        # Windows cp949 콘솔 대비
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    def _emit(self, line):
        # flush=True 가 없으면 주피터/리다이렉트/파이프 환경에서 stdout 이 블록
        # 버퍼링되어 프로세스가 끝날 때까지 단 한 줄도 보이지 않는다.
        # (= '멈춘 것처럼 보이는' 현상의 진짜 원인. 워치독도 이 경로를 타므로
        #    이 한 줄이 없으면 어떤 진행 표시도 화면에 도달하지 못한다)
        with self._lock:
            try:
                print(line, flush=True)
            except Exception:
                try:
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                except Exception:
                    pass
            try:
                self._fh.write(line + "\n")
                self._fh.flush()
            except Exception:
                pass

    def info(self, msg):
        el = time.time() - self.t0
        self._emit(f"[{el:8.1f}s] {msg}")

    def warn(self, msg):
        self.info(f"⚠ 경고: {msg}")

    def error(self, msg):
        self.info(f"✖ 오류: {msg}")

    def banner(self, stage_id, title):
        bar = "═" * 74
        self._emit(f"\n{bar}\n■ [{stage_id}] {title}\n{bar}")

    def kv(self, title, d):
        self.info(f"── {title}")
        for k, v in d.items():
            self._emit(f"      · {k:<28} : {v}")

    def table(self, title, df, max_rows=40):
        self.info(f"── {title}")
        try:
            with pd.option_context("display.width", 160, "display.max_columns", 40,
                                   "display.float_format", lambda x: f"{x:,.4f}"):
                self._emit(df.head(max_rows).to_string())
        except Exception as e:
            self._emit(f"      (표 출력 실패: {e})")


# ── 소형 IO 유틸 ──────────────────────────────────────────────────────────────

def now_ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def sha1_text(s):
    return hashlib.sha1(str(s).encode("utf-8", "ignore")).hexdigest()[:12]

def read_json_safe(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def atomic_write_json(path, obj, backup_dir=None):
    """임시파일 → 파싱 검증 → (기존본 백업) → os.replace 원자 교체.
    기존 파일이 있으면 절대 파괴적 덮어쓰기를 하지 않는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp_{now_ts()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    if read_json_safe(tmp) is None:                 # 쓰기 검증
        raise IOError(f"JSON 검증 실패: {tmp}")
    if path.exists():
        bdir = Path(backup_dir) if backup_dir else path.parent / "_backup"
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, bdir / f"{path.stem}.{now_ts()}{path.suffix}")
        except Exception:
            pass
    os.replace(tmp, path)

def month_range(start_ym, end_ym):
    """'YYYY-MM' 문자열 리스트 (양끝 포함). pandas 2/3 호환을 위해 Period 사용."""
    return [str(p) for p in pd.period_range(start_ym, end_ym, freq="M")]

def month_end_date(ym):
    return pd.Period(ym, freq="M").to_timestamp(how="end").normalize()

def month_ord(ym):
    return pd.Period(ym, freq="M").ordinal

def ord_to_ym(o):
    return str(pd.Period(ordinal=int(o), freq="M"))


def _maybe_prompt_credentials(log):
    """S00 값이 비어 있고 대화형이면 1회 질의. 비대화형이면 절대 블로킹하지 않음."""
    global KRX_MP_ID, KRX_MP_PW, DART_API_KEYS
    KRX_MP_ID = KRX_MP_ID or os.environ.get("KRX_MP_ID", "")
    KRX_MP_PW = KRX_MP_PW or os.environ.get("KRX_MP_PW", "")
    env_keys = os.environ.get("DART_API_KEYS", "")
    if not DART_API_KEYS and env_keys:
        DART_API_KEYS = [k.strip() for k in env_keys.split(",") if k.strip()]
    if CFG.RUN_MODE != "FULL" or not PROMPT_FOR_MISSING_CREDENTIALS:
        return
    interactive = _in_notebook() or (hasattr(sys.stdin, "isatty") and sys.stdin.isatty())
    if not interactive:
        return
    # input() 은 무기한 블로킹된다. 워치독이 아직 뜨기 전이라 이 상태로 멈추면
    # 화면에 아무 단서도 남지 않는다 → 무엇을 기다리는지 먼저 크게 알린다.
    print("\n" + "=" * 74, flush=True)
    print("[S00] 자격증명 입력 대기 중입니다. 그냥 Enter 를 누르면 건너뜁니다.", flush=True)
    print("      · KRX 계정: https://data.krx.co.kr 무료 가입 (미입력 시 공개 경로 사용)", flush=True)
    print("      · DART 키 : https://opendart.fss.or.kr 무료 발급 (미입력 시 통제변수 축소)", flush=True)
    print("      질문 없이 바로 실행하려면 파일 상단 "
          "PROMPT_FOR_MISSING_CREDENTIALS = False 로 두세요.", flush=True)
    print("=" * 74, flush=True)
    try:
        from getpass import getpass
        if not KRX_MP_ID:
            KRX_MP_ID = input("[S00] KRX 마켓플레이스 ID (없으면 Enter): ").strip()
        if KRX_MP_ID and not KRX_MP_PW:
            KRX_MP_PW = getpass("[S00] KRX 마켓플레이스 PW: ").strip()
        if not DART_API_KEYS:
            k = input("[S00] DART API 키 (콤마 구분 복수, 없으면 Enter): ").strip()
            if k:
                DART_API_KEYS = [x.strip() for x in k.split(",") if x.strip()]
    except Exception as e:
        log.warn(f"자격증명 대화형 입력 건너뜀: {e}")
    finally:
        _export_krx_env(log)


def _export_krx_env(log):
    """KRX 는 2025-12-27 부터 로그인을 의무화했고, pykrx(≥1.2.x)는 이를
    KRX_ID / KRX_PW '환경변수'에서만 읽는다. S00 에 입력된 계정을 여기로 넘겨주지
    않으면 pykrx 가 자체적으로 '환경 변수가 설정되지 않았습니다'를 출력하며
    무인증으로 떨어진다(= 조회 실패/축소의 주원인)."""
    if KRX_MP_ID and KRX_MP_PW:
        os.environ.setdefault("KRX_ID", KRX_MP_ID)
        os.environ.setdefault("KRX_PW", KRX_MP_PW)
        log.info("[S02] KRX 계정을 pykrx 인증 환경변수(KRX_ID/KRX_PW)로 전달했습니다.")
    else:
        log.warn("[S02] KRX 계정 미입력 — KRX 는 2025-12-27 부터 로그인 필수라 "
                 "pykrx 의 KRX 직접 조회가 제한될 수 있습니다. "
                 "무료 가입: https://data.krx.co.kr → [회원가입] 후 [S00] 에 입력.")
        log.info("[S02] 계정이 없어도 FDR 공개 캐시 + 네이버 차트 경로로 "
                 "유니버스·가격을 구성하므로 파이프라인은 계속 진행됩니다.")

# ══════════════════════════════════════════════════════════════════════════════
# [S03] 캐시 3계층 + 공용인덱스/전용인덱스  (절대 1원칙 구현부)
#   - 기존 인덱스 무손상: append-only 병합 + 타임스탬프 백업 + 검증 후 원자 교체.
#     파싱 불가능한 기존 인덱스를 만나면 '읽기전용 보존'으로 전환하고 별도
#     사이드카 인덱스에 기록한다(원본은 바이트 하나도 건드리지 않음).
#   - 신규 수집 데이터: 로컬(핫) 저장 + 구글드라이브(콜드/공유) 미러 + 인덱스 등록.
#     드라이브 부재 시 pending 큐에 적재 후 다음 실행에서 자동 동기화.
#   - 캐시 탐색: 로컬(홈/D드라이브) + 드라이브(전용/공용) + 타 전략 레거시 인덱스.
# ══════════════════════════════════════════════════════════════════════════════

KR_DATA_DIRNAME = ".kr_data_work"
COMMON_DIRNAME  = "_COMMON_CACHE"      # 전략 간 공유 캐시(공용인덱스 대상)
STRATEGY_NAME   = "ARC_AAR"
INDEX_SCHEMA    = "kr_data_index_v1"


class IndexManager:
    """공용/전용 인덱스 1개 파일을 관리. 기존 항목은 어떤 경우에도 삭제하지 않는다."""

    def __init__(self, path, scope, log):
        self.path = Path(path)
        self.scope = scope                      # "common" | "ARC_AAR"
        self.log = log
        self.read_only = False
        self.doc = None
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self.path.exists():
            doc = read_json_safe(self.path)
            if doc is None:
                # 절대 1원칙: 손상 의심 인덱스는 건드리지 않는다 → 사이드카로 전환
                self.read_only = True
                side = self.path.with_name(self.path.stem + f".sidecar_{now_ts()}.json")
                self.log.warn(f"인덱스 파싱 실패 → 원본 보존, 사이드카 사용: {side.name}")
                self.path = side
                doc = self._new_doc()
            elif not isinstance(doc.get("entries"), dict):
                # 스키마가 다른(타 전략) 인덱스 → 원본 필드 전부 보존, entries만 추가
                doc.setdefault("entries", {})
            self.doc = doc
        else:
            self.doc = self._new_doc()

    def _new_doc(self):
        return {"schema": INDEX_SCHEMA, "scope": self.scope,
                "created_at": datetime.now().isoformat(), "entries": {}}

    def register(self, key, record):
        """entries[key] 등록/갱신. 기존 값이 다르면 history 로 보존(무손실)."""
        with self._lock:
            ent = self.doc["entries"]
            record = dict(record)
            record["updated_at"] = datetime.now().isoformat()
            record["strategy"] = STRATEGY_NAME
            old = ent.get(key)
            if old is not None:
                same = all(old.get(k) == record.get(k)
                           for k in ("path", "rows", "sha1") if k in record)
                if not same:
                    hist = old.pop("history", [])
                    hist.append({k: v for k, v in old.items() if k != "history"})
                    record["history"] = hist[-20:]
                else:
                    record.setdefault("history", old.get("history", []))
            ent[key] = record

    def save(self):
        with self._lock:
            self.doc["updated_at"] = datetime.now().isoformat()
            try:
                atomic_write_json(self.path, self.doc,
                                  backup_dir=self.path.parent / "_backup")
            except Exception as e:
                self.log.warn(f"인덱스 저장 실패({self.path.name}): {e}")

    def lookup(self, key):
        return self.doc["entries"].get(key)

    def search(self, keywords):
        """키/경로/설명에 키워드가 모두 포함된 항목 검색(재활용 탐색용)."""
        kws = [k.lower() for k in keywords]
        out = []
        for k, v in self.doc["entries"].items():
            blob = (k + " " + str(v.get("path", "")) + " " + str(v.get("desc", ""))).lower()
            if all(kw in blob for kw in kws):
                out.append((k, v))
        return out


class CacheStore:
    """3계층(raw/parsed/features) 캐시 + 이중(로컬/드라이브) 저장 + 계보(lineage)."""

    def __init__(self, local_root, drive_root, log):
        self.log = log
        self.local_root = Path(local_root)                       # ~/.kr_data_work/ARC_AAR
        self.local_krdw = self.local_root.parent                 # ~/.kr_data_work
        self.drive_krdw = (Path(drive_root) / KR_DATA_DIRNAME) if drive_root else None
        self.drive_root = (self.drive_krdw / STRATEGY_NAME) if self.drive_krdw else None
        self.have_drive = self.drive_root is not None

        for tier in ("raw", "parsed", "features"):
            (self.local_root / "cache" / tier).mkdir(parents=True, exist_ok=True)
        for sub in ("outputs", "logs", "state"):
            (self.local_root / sub).mkdir(parents=True, exist_ok=True)
        (self.local_krdw / COMMON_DIRNAME).mkdir(parents=True, exist_ok=True)
        if self.have_drive:
            try:
                for tier in ("raw", "parsed", "features"):
                    (self.drive_root / "cache" / tier).mkdir(parents=True, exist_ok=True)
                (self.drive_root / "outputs").mkdir(parents=True, exist_ok=True)
                (self.drive_krdw / COMMON_DIRNAME).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log.warn(f"드라이브 디렉토리 준비 실패 → 로컬 전용 + pending 큐: {e}")
                self.have_drive = False

    # ── 인덱스 (전용/공용) — 드라이브 우선, 없으면 로컬에 두고 이후 동기화 ──
        ded_dir = (self.drive_root if self.have_drive else self.local_root) / "index"
        com_dir = (self.drive_krdw if self.have_drive else self.local_krdw) / COMMON_DIRNAME / "index"
        ded_dir.mkdir(parents=True, exist_ok=True)
        com_dir.mkdir(parents=True, exist_ok=True)
        self.idx_dedicated = IndexManager(ded_dir / "arc_aar_index.json", STRATEGY_NAME, log)
        self.idx_common    = IndexManager(com_dir / "common_index.json", "common", log)

        self.lineage = []                                        # 데이터 계보 원장
        self._pending_path = self.local_root / "state" / "pending_drive_sync.jsonl"
        self._pending_lock = threading.Lock()
        self._legacy_cache = None
        self._roots_cache = None

    # ── 검색 루트(로컬 D드라이브 + 드라이브 양측 — 발주자 지시) ─────────────
    def _search_roots(self):
        """※ 결과를 캐시한다. 캐시하지 않으면 load_df 호출마다 D:/E: 경로를
        재차 stat 하게 되는데, Windows(특히 Defender + 네트워크 드라이브)에서는
        이것만으로 수만 회의 디스크 왕복이 발생한다."""
        if getattr(self, "_roots_cache", None) is not None:
            return self._roots_cache
        roots = [self.local_root / "cache",
                 self.local_krdw / COMMON_DIRNAME]
        if _is_windows():
            for dl in ["D", "E"]:
                for base in (f"{dl}:/{KR_DATA_DIRNAME}", f"{dl}:/kr_data_work"):
                    roots += [Path(base) / STRATEGY_NAME / "cache",
                              Path(base) / COMMON_DIRNAME]
        if self.have_drive:
            roots += [self.drive_root / "cache", self.drive_krdw / COMMON_DIRNAME]
        out = []
        for r in roots:
            try:
                if r and r.exists():
                    out.append(r)
            except Exception:
                continue
        self._roots_cache = out
        return out

    # ── 데이터프레임 저장/로드 (모든 데이터 IO 의 단일 관문 = 계보 추적점) ──
    def _write_df(self, df, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(path, index=False)
            return path
        except Exception:
            alt = path.with_suffix(".pkl")                        # pyarrow 부재 폴백
            df.to_pickle(alt)
            return alt

    def _read_df(self, path):
        path = Path(path)
        if path.suffix == ".pkl":
            return pd.read_pickle(path)
        try:
            return pd.read_parquet(path)
        except Exception:
            alt = path.with_suffix(".pkl")
            if alt.exists():
                return pd.read_pickle(alt)
            raise

    def save_df(self, df, tier, relpath, scope="dedicated", desc="", stage=""):
        """로컬 저장 → 드라이브 미러 → 인덱스 등록(전용 + 필요시 공용) → 계보 기록.
        scope='common' 이면 타 전략도 쓸 수 있는 공용 캐시로 취급한다."""
        relpath = str(relpath).replace("\\", "/")
        if scope == "common":
            lpath = self.local_krdw / COMMON_DIRNAME / relpath
        else:
            lpath = self.local_root / "cache" / tier / relpath
        real = self._write_df(df, Path(lpath))

        drive_path = None
        if scope == "common":
            dtarget = (self.drive_krdw / COMMON_DIRNAME / relpath) if self.have_drive else None
        else:
            dtarget = (self.drive_root / "cache" / tier / relpath) if self.have_drive else None
        if dtarget is not None:
            try:
                dtarget = dtarget.with_suffix(real.suffix)
                dtarget.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(real, dtarget)
                drive_path = str(dtarget)
            except Exception as e:
                self.log.warn(f"드라이브 미러 실패({relpath}): {e} → pending 큐 적재")
                self._add_pending(str(real), scope, tier, relpath)
        else:
            self._add_pending(str(real), scope, tier, relpath)

        rec = {"path": str(real), "drive_path": drive_path, "tier": tier,
               "rows": int(len(df)), "cols": list(map(str, df.columns))[:40],
               "desc": desc, "stage": stage}
        key = f"{tier}/{relpath}"
        self.idx_dedicated.register(key, rec)
        if scope == "common":
            self.idx_common.register(key, rec)
        self.lineage.append({"stage": stage, "dataset": relpath, "tier": tier,
                             "rows": int(len(df)), "scope": scope,
                             "local": str(real), "drive": drive_path or "(pending)",
                             "ts": datetime.now().isoformat(timespec="seconds")})
        return real

    def load_df(self, tier, relpath, scope="dedicated", stage=""):
        """로컬 → D드라이브 → 구글드라이브 순 탐색. 드라이브에서만 발견되면
        로컬 핫캐시로 끌어온다. 없으면 None."""
        relpath = str(relpath).replace("\\", "/")
        rels = [relpath]
        if relpath.endswith(".parquet"):
            rels.append(relpath[:-8] + ".pkl")
        sub_ded = f"{STRATEGY_NAME}/cache/{tier}"
        for root in self._search_roots():
            for rel in rels:
                for cand in (root / rel, root / tier / rel):
                    try:
                        if cand.exists():
                            df = self._read_df(cand)
                            local_home = self.local_root / "cache" / tier / rel
                            if not str(cand).startswith(str(self.local_root)) \
                               and not local_home.exists():
                                try:
                                    local_home.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(cand, local_home)
                                except Exception:
                                    pass
                            self.lineage.append({"stage": stage, "dataset": rel,
                                                 "tier": tier, "rows": int(len(df)),
                                                 "scope": "cache_hit",
                                                 "local": str(cand), "drive": "",
                                                 "ts": datetime.now().isoformat(timespec="seconds")})
                            return df
                    except Exception:
                        continue
        _ = sub_ded
        return None

    # ── 원문(raw) 캐시: gzip 텍스트 ────────────────────────────────────────
    def save_raw_text(self, relpath, text):
        p = self.local_root / "cache" / "raw" / (str(relpath) + ".gz")
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(text)
        if self.have_drive:
            try:
                d = self.drive_root / "cache" / "raw" / (str(relpath) + ".gz")
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, d)
            except Exception:
                pass
        return p

    def load_raw_text(self, relpath):
        for root in self._search_roots():
            for cand in (root / "raw" / (str(relpath) + ".gz"),
                         root / (str(relpath) + ".gz")):
                if cand.exists():
                    try:
                        with gzip.open(cand, "rt", encoding="utf-8") as f:
                            return f.read()
                    except Exception:
                        continue
        return None

    # ── 드라이브 pending 동기화 ────────────────────────────────────────────
    def _add_pending(self, local_path, scope, tier, relpath):
        """append-only JSONL 에 한 줄만 덧붙인다.
        (이전: 매 호출마다 전체 큐를 읽고→쓰고→검증 재독→백업 복사 = O(N²).
         드라이브 미연결 상태에서 2,500건이면 Windows 에서 수 분~수십 분이 날아가고
         _backup 폴더에 수천 개 파일이 쌓였다)"""
        with self._pending_lock:
            try:
                self._pending_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._pending_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"local": local_path, "scope": scope,
                                        "tier": tier, "rel": relpath},
                                       ensure_ascii=False) + "\n")
            except Exception:
                pass

    def _read_pending(self):
        items, seen = [], set()
        try:
            if not self._pending_path.exists():
                return items
            with open(self._pending_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        it = json.loads(line)
                    except Exception:
                        continue
                    key = (it.get("local"), it.get("rel"))
                    if key in seen:            # 재실행 누적분 자동 중복 제거
                        continue
                    seen.add(key)
                    items.append(it)
        except Exception:
            pass
        return items

    def _write_pending(self, items):
        try:
            tmp = self._pending_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for it in items:
                    f.write(json.dumps(it, ensure_ascii=False) + "\n")
            os.replace(tmp, self._pending_path)
        except Exception:
            pass

    def pending_count(self):
        return len(self._read_pending())

    def sync_pending_to_drive(self):
        if not self.have_drive:
            return 0
        q = self._read_pending()
        left, done = [], 0
        for item in q:
            try:
                src = Path(item["local"])
                if item["scope"] == "common":
                    dst = self.drive_krdw / COMMON_DIRNAME / item["rel"]
                else:
                    dst = self.drive_root / "cache" / item["tier"] / item["rel"]
                dst = dst.with_suffix(src.suffix)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.copy2(src, dst)
                    done += 1
            except Exception:
                left.append(item)
        self._write_pending(left)
        if done:
            self.log.info(f"[S03] 드라이브 pending 동기화 완료: {done}건 (잔여 {len(left)})")
        return done

    # ── 타 전략 레거시 캐시 재활용 (읽기전용 — 발주자: 호환 캐시 재활용) ────
    def discover_legacy_indexes(self):
        if self._legacy_cache is not None:
            return self._legacy_cache
        found = []
        scan_roots = [self.local_krdw] + ([self.drive_krdw] if self.have_drive else [])
        ours = {str(self.idx_dedicated.path), str(self.idx_common.path)}
        for root in scan_roots:
            try:
                for p in list(root.glob("*/index/*index*.json"))[:50] + \
                         list(root.glob("*/*index*.json"))[:50]:
                    if str(p) in ours or "_backup" in str(p):
                        continue
                    doc = read_json_safe(p)
                    if isinstance(doc, dict) and isinstance(doc.get("entries"), dict):
                        found.append((p, doc))
            except Exception:
                continue
        self._legacy_cache = found
        if found:
            self.log.info(f"[S03] 레거시 인덱스 {len(found)}개 발견(읽기전용 재활용 대상)")
        return found

    def find_legacy_df(self, keywords, need_cols):
        """타 전략 인덱스에서 keywords 를 모두 포함하는 항목을 찾아 로드 시도.
        need_cols 부분집합이 확인되면 반환. 원본은 절대 수정하지 않는다."""
        kws = [k.lower() for k in keywords]
        for _, doc in self.discover_legacy_indexes():
            for key, v in doc["entries"].items():
                blob = (str(key) + " " + str(v.get("path", "")) + " "
                        + str(v.get("desc", ""))).lower()
                if not all(kw in blob for kw in kws):
                    continue
                for cand in (v.get("path"), v.get("drive_path")):
                    if not cand:
                        continue
                    try:
                        df = self._read_df(Path(cand))
                        cols = {str(c).lower() for c in df.columns}
                        if set(c.lower() for c in need_cols) <= cols:
                            self.log.info(f"[S03] 레거시 캐시 재활용: {key} ({len(df)}행)")
                            return df
                    except Exception:
                        continue
        return None

    def save_indexes(self):
        self.idx_dedicated.save()
        self.idx_common.save()

    def lineage_df(self):
        return pd.DataFrame(self.lineage) if self.lineage else pd.DataFrame(
            columns=["stage", "dataset", "tier", "rows", "scope", "local", "drive", "ts"])


class CheckpointManager:
    """스테이지 체크포인트: 입력 시그니처가 같으면 스킵(캐시 히트 재실행 단축)."""
    def __init__(self, store):
        self.path = store.local_root / "state" / "checkpoints.json"
        self.doc = read_json_safe(self.path) or {}

    def is_done(self, stage, sig):
        rec = self.doc.get(stage)
        return bool(rec and rec.get("sig") == sig and stage not in CFG.FORCE_STAGES)

    def mark(self, stage, sig):
        self.doc[stage] = {"sig": sig, "done_at": datetime.now().isoformat()}
        try:
            atomic_write_json(self.path, self.doc)
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# [S04] 네트워크 계층 (전면 재작성)
#   설계 원칙 — 이전 버전이 "조용히 멈춘 것처럼" 보였던 원인을 전부 제거한다.
#   ① 침묵 금지 : 모든 장시간 루프는 Progress 에 등록되고, 워치독이 주기적으로
#                 "지금 무엇을 하는 중 / 몇 개째 / 예상 잔여시간"을 출력한다.
#   ② 빠른 포기 : 403/404 는 재시도해도 200 이 되지 않는다. 백오프 없이 즉시
#                 헤더 프로파일을 한 번 바꿔 보고, 안 되면 소스를 끈다.
#                 (이전: 403 하나에 재시도 5회 × 백오프 = 33초 낭비)
#   ③ 적응형 페이싱 : 성공하면 딜레이를 서서히 줄이고, 429/403 이 나오면 즉시
#                 늘린다. 고정 딜레이보다 빠르면서 차단 위험은 낮다.
#   ④ 요청 예산 : 비싼 경로(상세 페이지)는 '월당 한도'가 아니라 '실행 전체 한도'로
#                 관리한다. 월당 한도는 개월 수를 곱하면 폭발한다.
#   ⑤ 실시간 쿼터 : 고정 상수(19,000/20,000)를 가정하지 않는다. 서버가 한도초과를
#                 알리면 그 즉시 소진 처리하고, 그 전까지는 관측된 사용량만 센다.
# ══════════════════════════════════════════════════════════════════════════════

class SourceDown(Exception):
    """서킷 브레이커 개방 또는 차단 확정: 해당 소스 이번 실행에서 사용 중단."""


class QuotaExhausted(Exception):
    """해당 소스/키의 호출 한도 소진(서버 응답으로 확인된 경우만)."""


class BudgetExceeded(Exception):
    """수집 타임박스 또는 요청 예산 초과 — 수집분으로 INTERIM 진행."""


class TimeBudget:
    """수집 단계 타임박스. 계산 단계에는 적용하지 않는다."""
    def __init__(self, hours):
        self.limit_s = float(hours) * 3600.0
        self.t0 = None
        self.tripped = False

    def start(self):
        if self.t0 is None:
            self.t0 = time.time()

    def elapsed(self):
        return 0.0 if self.t0 is None else time.time() - self.t0

    def remaining(self):
        return max(0.0, self.limit_s - self.elapsed())

    def exceeded(self):
        if self.t0 is None:
            return False
        if self.elapsed() > self.limit_s:
            self.tripped = True
            return True
        return False

    def status(self):
        return (f"수집 {self.elapsed()/60:.0f}분 경과 / 한도 {self.limit_s/60:.0f}분"
                + (" [초과→INTERIM]" if self.tripped else ""))


COLLECT_BUDGET = TimeBudget(CFG.COLLECT_TIMEBOX_HOURS)


# ──────────────────────────────────────────────────────────────────────────────
# 진행 상황 방송기 + 워치독  (침묵 방지 — 이번 재작성의 1순위 목표)
# ──────────────────────────────────────────────────────────────────────────────
class Progress:
    """현재 작업을 전역에 게시한다. 워치독 스레드가 이를 주기적으로 출력하므로
    어떤 루프도 '멈춘 것처럼' 보이지 않는다."""
    _lock = threading.Lock()
    task = "(대기)"
    done = 0
    total = 0
    t0 = time.time()
    last_emit = 0.0
    extra = ""

    @classmethod
    def begin(cls, task, total=0, extra=""):
        with cls._lock:
            cls.task, cls.total, cls.done = task, int(total), 0
            cls.t0, cls.extra = time.time(), extra

    @classmethod
    def tick(cls, n=1, extra=None):
        with cls._lock:
            cls.done += n
            if extra is not None:
                cls.extra = extra

    @classmethod
    def snapshot(cls):
        with cls._lock:
            el = time.time() - cls.t0
            rate = cls.done / el if el > 0.5 else 0.0
            eta = (cls.total - cls.done) / rate if (rate > 0 and cls.total) else None
            return cls.task, cls.done, cls.total, el, rate, eta, cls.extra

    @classmethod
    def line(cls):
        task, done, total, el, rate, eta, extra = cls.snapshot()
        s = f"⏳ {task}: {done}"
        if total:
            s += f"/{total} ({done/max(total,1)*100:.0f}%)"
        s += f" | {rate:.1f}건/s | 경과 {el/60:.1f}분"
        if eta:
            s += f" | 잔여 ~{eta/60:.1f}분"
        if extra:
            s += f" | {extra}"
        return s


class Watchdog:
    """N초마다 Progress 를 출력하는 데몬 스레드. 어떤 단계에서도 화면이 죽지 않는다."""
    def __init__(self, log, period=None):
        self.log = log
        self.period = period or CFG.PROGRESS_HEARTBEAT_S
        self._stop = threading.Event()
        self._th = None

    def start(self):
        if self._th is not None:
            return
        def _run():
            while not self._stop.wait(self.period):
                try:
                    _, done, _, el, _, _, _ = Progress.snapshot()
                    if done > 0 or el > self.period:
                        self.log.info(Progress.line() + f" | {COLLECT_BUDGET.status()}")
                except Exception:
                    pass
        self._th = threading.Thread(target=_run, daemon=True, name="arc-watchdog")
        self._th.start()

    def stop(self):
        self._stop.set()


# ──────────────────────────────────────────────────────────────────────────────
# 레이트리밋 / 서킷 / 쿼터 / 요청예산
# ──────────────────────────────────────────────────────────────────────────────
class AdaptiveLimiter:
    """성공하면 조금씩 빨라지고, 차단 신호(403/429)가 오면 즉시 느려진다.
    고정 딜레이 대비 정상 구간에서 2~3배 빠르면서 차단 위험은 더 낮다."""
    def __init__(self, lo, hi):
        self.base_lo, self.base_hi = lo, hi
        self.factor = 1.0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            gap = random.uniform(self.base_lo, self.base_hi) * self.factor
            due = self._last + gap
            now = time.time()
            if due > now:
                time.sleep(due - now)
            self._last = time.time()

    def on_success(self):
        with self._lock:
            self.factor = max(CFG.RATE_FACTOR_MIN, self.factor * 0.97)

    def on_throttle(self):
        with self._lock:
            self.factor = min(CFG.RATE_FACTOR_MAX, self.factor * 2.0)


class CircuitBreaker:
    """연속 실패 CB_MAX_CONSEC_FAIL 회 → 개방. 차단 확정(403 등)은 즉시 개방.
    상태는 날짜 단위로 저장하되, 재실행 시 '오늘 이미 막힘'을 존중한다."""
    def __init__(self, source, state_dir, log):
        self.source, self.log = source, log
        self.path = Path(state_dir) / f"circuit_{source}.json"
        st = read_json_safe(self.path) or {}
        today = datetime.now().strftime("%Y-%m-%d")
        self.consec = 0
        self.open = bool(st.get("open_date") == today)
        self.reason = st.get("reason", "") if self.open else ""
        self._lock = threading.Lock()
        if self.open:
            log.warn(f"[S04] {source}: 금일 차단 이력 있음({self.reason}) — 폴백 경로 사용")

    def check(self):
        if self.open:
            raise SourceDown(f"{self.source}: {self.reason or '서킷 개방'}")

    def ok(self):
        with self._lock:
            self.consec = 0

    def _persist(self, reason):
        try:
            atomic_write_json(self.path, {
                "open_date": datetime.now().strftime("%Y-%m-%d"),
                "at": datetime.now().isoformat(), "reason": reason})
        except Exception:
            pass

    def trip_now(self, reason):
        """재시도가 무의미한 차단(403/robots/로그인월) — 즉시 개방."""
        with self._lock:
            if not self.open:
                self.open, self.reason = True, reason
                self._persist(reason)
                self.log.warn(f"[S04] {self.source}: 차단 확정({reason}) → 소스 비활성화")
        raise SourceDown(f"{self.source}: {reason}")

    def fail(self):
        with self._lock:
            self.consec += 1
            if self.consec >= CFG.CB_MAX_CONSEC_FAIL and not self.open:
                self.open = True
                self.reason = f"연속 실패 {self.consec}회"
                self._persist(self.reason)
                self.log.error(f"[S04] {self.source}: {self.reason} → 서킷 개방")
                raise SourceDown(self.source)


class QuotaTracker:
    """실시간 잔여 호출량. 고정 예산(19,000 등)을 '가정'하지 않는다.
    - used(key)      : 이번 날짜에 실제로 보낸 요청 수(영속)
    - mark_exhausted : 서버가 한도초과를 알린 순간에만 호출된다
    - budget_left    : 관측된 명목한도가 있으면 그것 기준, 없으면 무한대 취급"""
    def __init__(self, state_dir, log):
        self.path = Path(state_dir) / "quota_state.json"
        self.log = log
        self._lock = threading.Lock()
        self.doc = read_json_safe(self.path) or {}
        today = datetime.now().strftime("%Y-%m-%d")
        if self.doc.get("date") != today:
            self.doc = {"date": today, "used": {}, "exhausted": {}, "observed_limit": {}}
        self.doc.setdefault("observed_limit", {})

    def _save(self):
        try:
            atomic_write_json(self.path, self.doc)
        except Exception:
            pass

    def record(self, key):
        with self._lock:
            self.doc["used"][key] = self.doc["used"].get(key, 0) + 1
            if self.doc["used"][key] % 250 == 0:
                self._save()

    def used(self, key):
        return self.doc["used"].get(key, 0)

    def mark_exhausted(self, key, why=""):
        with self._lock:
            n = self.doc["used"].get(key, 0)
            self.doc["exhausted"][key] = {"at": datetime.now().isoformat(), "why": why}
            # 소진 시점의 사용량 = 그 키의 실제 한도. 다음 실행의 계획에 쓴다.
            self.doc["observed_limit"][key] = n
            self._save()
        self.log.warn(f"[S04] 쿼터 소진: {key} ({why}) — 관측 한도 {n}건으로 기록")

    def is_exhausted(self, key):
        return key in self.doc.get("exhausted", {})

    def budget_left(self, key):
        """관측된 한도가 있으면 그 기준 잔여, 없으면 None(=제한 미확인)."""
        if self.is_exhausted(key):
            return 0
        lim = self.doc.get("observed_limit", {}).get(key)
        return None if lim is None else max(0, int(lim) - self.used(key))

    def summary(self):
        return {"used": dict(self.doc.get("used", {})),
                "exhausted": list(self.doc.get("exhausted", {})),
                "observed_limit": dict(self.doc.get("observed_limit", {}))}


class RequestBudget:
    """비싼 경로(리포트 상세 페이지 등)의 '실행 전체' 요청 상한.
    월당 한도는 개월 수를 곱하면 폭발하므로 전역으로만 관리한다."""
    def __init__(self, name, limit, log):
        self.name, self.limit, self.log = name, int(limit), log
        self.used = 0
        self._lock = threading.Lock()
        self._warned = False

    def take(self, n=1):
        with self._lock:
            if self.used + n > self.limit:
                if not self._warned:
                    self.log.warn(f"[S04] 요청예산 소진: {self.name} "
                                  f"{self.used}/{self.limit} — 이후 해당 경로 생략")
                    self._warned = True
                return False
            self.used += n
            return True

    def left(self):
        return max(0, self.limit - self.used)


# ──────────────────────────────────────────────────────────────────────────────
# HTTP 클라이언트 — 소스별 헤더 프로파일 + 세션 웜업 + 빠른 포기
# ──────────────────────────────────────────────────────────────────────────────
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
]

# 소스별 헤더 프로파일. 한경 403 의 통상 원인은 브라우저 유사 헤더 부재이므로
# Referer/Accept/Sec-Fetch 를 갖춘 프로파일을 1순위로 쓰고, 실패 시 대체안을 1회 시도.
_HEADER_PROFILES = {
    "hankyung": [
        {"Referer": "https://consensus.hankyung.com/analysis/list",
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
         "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
         "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1",
         "Upgrade-Insecure-Requests": "1", "Cache-Control": "no-cache"},
        {"Referer": "https://consensus.hankyung.com/",
         "Accept": "*/*", "X-Requested-With": "XMLHttpRequest",
         "Accept-Language": "ko-KR,ko;q=0.9"},
    ],
    "naver_research": [
        {"Referer": "https://finance.naver.com/research/company_list.naver",
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "ko-KR,ko;q=0.9"},
    ],
    "krx": [
        {"Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
         "Accept": "application/json, text/javascript, */*; q=0.01",
         "X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
    ],
}

# 세션 웜업 URL: 쿠키를 먼저 확보해야 200 을 주는 사이트 대응
_WARMUP = {
    "hankyung": "https://consensus.hankyung.com/",
    "naver_research": "https://finance.naver.com/research/",
    "krx": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201",
    "kind": "https://kind.krx.co.kr/",
}

# 재시도해도 200 이 되지 않는 상태코드 — 백오프로 시간을 버리지 않는다
_FAST_FAIL = {400, 401, 403, 404, 405, 410, 451}


class HttpClient:
    def __init__(self, source, state_dir, log, quota=None, blocked=False):
        import requests
        self.requests = requests
        self.source, self.log = source, log
        lo, hi = CFG.BASE_DELAY.get(source, (0.25, 0.6))
        self.limiter = AdaptiveLimiter(lo, hi)
        self.breaker = CircuitBreaker(source, state_dir, log)
        self.quota = quota
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": random.choice(_UA_POOL),
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
            "Connection": "keep-alive"})
        try:                                  # 커넥션 풀 확대(워커 수 대응)
            ad = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16,
                                               max_retries=0)
            self.sess.mount("https://", ad)
            self.sess.mount("http://", ad)
        except Exception:
            pass
        self.profiles = _HEADER_PROFILES.get(source, [{}])
        self._pi = 0
        self._warmed = False
        self.n_ok = self.n_fail = 0
        if blocked:
            try:
                self.breaker.trip_now("카나리 차단 감지")
            except SourceDown:
                pass

    def warmup(self):
        """쿠키 확보용 선요청. 실패해도 무시."""
        if self._warmed:
            return
        self._warmed = True
        url = _WARMUP.get(self.source)
        if not url:
            return
        try:
            self.limiter.wait()
            self.sess.get(url, timeout=CFG.HTTP_TIMEOUT,
                          headers=self.profiles[0] if self.profiles else {})
        except Exception:
            pass

    def get(self, url, params=None, encoding=None, referer=None, quota_key=None,
            method="GET", data=None, allow_codes=(200,), stream=False,
            fast=False):
        """fast=True 면 실패 시 재시도 없이 즉시 예외(대량 루프용)."""
        self.breaker.check()
        if self.quota is not None and quota_key and self.quota.is_exhausted(quota_key):
            raise QuotaExhausted(quota_key)
        self.warmup()
        # 재시도 슬롯 = 백오프 단계 + '헤더 프로파일 전환' 몫(지연 0).
        # 프로파일 전환에도 슬롯을 배정하지 않으면 fast 경로에서 전환 후 재시도가
        # 일어나지 않아 대체 헤더를 시험해 볼 기회 자체가 사라진다.
        backoffs = ([0] if fast else ([0] + list(CFG.RETRY_BACKOFF))) \
            + [0] * max(0, len(self.profiles) - 1)
        last_err = None
        for back in backoffs:
            if back:
                time.sleep(back + random.uniform(0, 0.5))
            self.limiter.wait()
            headers = dict(self.profiles[self._pi % len(self.profiles)]) \
                if self.profiles else {}
            if referer:
                headers["Referer"] = referer
            try:
                # (connect, read) 튜플로 준다. 스칼라로 주면 '읽기 간격'마다
                # 타이머가 초기화돼 찔끔찔끔 보내는 서버에 무한정 붙잡힐 수 있다.
                tmo = (min(8, CFG.HTTP_TIMEOUT), CFG.HTTP_TIMEOUT)
                if method == "POST":
                    r = self.sess.post(url, params=params, data=data, headers=headers,
                                       timeout=tmo, stream=stream)
                else:
                    r = self.sess.get(url, params=params, headers=headers,
                                      timeout=tmo, stream=stream)
                if self.quota is not None and quota_key:
                    self.quota.record(quota_key)
                if r.status_code in allow_codes:
                    if encoding:
                        r.encoding = encoding
                    self.breaker.ok()
                    self.limiter.on_success()
                    self.n_ok += 1
                    return r
                if r.status_code == 429:
                    self.limiter.on_throttle()
                    last_err = "HTTP 429"
                    continue
                if r.status_code in _FAST_FAIL:
                    # 헤더 프로파일을 한 번 바꿔 보고, 그래도 막히면 즉시 포기.
                    # (이전 버전은 여기서 백오프 5회 = 33초를 버렸다)
                    self.n_fail += 1
                    if self._pi + 1 < len(self.profiles):
                        self._pi += 1
                        self.log.info(f"[S04] {self.source}: HTTP {r.status_code} → "
                                      f"헤더 프로파일 #{self._pi} 로 재시도")
                        continue
                    self.limiter.on_throttle()
                    self.breaker.trip_now(f"HTTP {r.status_code}")
                last_err = f"HTTP {r.status_code}"
            except (SourceDown, QuotaExhausted):
                raise
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:100]}"
        self.n_fail += 1
        self.breaker.fail()
        raise IOError(f"{self.source} 요청 실패: {url} ({last_err})")


class ParallelFetcher:
    """보수적 병렬 러너: worker 상한, 완료 키 영속 스킵, 진행률 방송,
    타임박스/소스중단 시 우아한 조기 종료."""
    def __init__(self, name, store, log, max_workers=None):
        self.name, self.store, self.log = name, store, log
        self.max_workers = min(CFG.MAX_WORKERS, max_workers or CFG.MAX_WORKERS)
        self.reg_path = store.local_root / "state" / f"done_{name}.json"
        self.done = set(read_json_safe(self.reg_path) or [])
        self._lock = threading.Lock()
        self._dirty = 0

    def _mark(self, key):
        with self._lock:
            self.done.add(key)
            self._dirty += 1
            if self._dirty >= 100:
                self._dirty = 0
                self._flush()

    def _flush(self):
        try:
            atomic_write_json(self.reg_path, sorted(self.done))
        except Exception:
            pass

    def run(self, items, worker_fn, key_fn, desc=None):
        todo = [it for it in items if key_fn(it) not in self.done]
        skipped = len(items) - len(todo)
        if skipped:
            self.log.info(f"[S04] {self.name}: 캐시 완료 {skipped}건 스킵")
        if not todo:
            return []
        if COLLECT_BUDGET.exceeded():
            self.log.warn(f"[S04] {self.name}: 타임박스 초과 — 신규 수집 생략")
            return []
        Progress.begin(desc or self.name, total=len(todo))
        self.log.info(f"[S04] {self.name}: {len(todo)}건 수집 시작 "
                      f"(workers={self.max_workers})")
        out, aborted = [], None
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(worker_fn, it): it for it in todo}
            for fut in as_completed(futs):
                it = futs[fut]
                try:
                    res = fut.result()
                    if res is not None:
                        out.append(res)
                    self._mark(key_fn(it))
                except (SourceDown, QuotaExhausted, BudgetExceeded) as e:
                    aborted = str(e)[:100]
                    for f2 in futs:
                        f2.cancel()
                    break
                except Exception as e:
                    self.log.warn(f"{self.name} 실패({key_fn(it)}): {str(e)[:110]}")
                Progress.tick()
                if COLLECT_BUDGET.exceeded():
                    aborted = "타임박스"
                    for f2 in futs:
                        f2.cancel()
                    break
        self._flush()
        if aborted:
            self.log.warn(f"[S04] {self.name}: 조기 종료({aborted}) — 수집분 사용")
        else:
            self.log.info(f"[S04] {self.name}: 완료 {len(out)}건")
        return out


def canary_check(log, state_dir):
    """본 수집 전 도달성 점검. 여기서 차단으로 판정된 소스는 처음부터 끄고 시작해
    본 수집에서 시간을 낭비하지 않는다. 반환: {source: (ok, detail)}"""
    try:
        import requests
    except Exception:
        return {}
    targets = {
        "naver_research": ("GET", "https://finance.naver.com/research/company_list.naver", None),
        "hankyung": ("GET", "https://consensus.hankyung.com/analysis/list", None),
        "dart": ("GET", "https://opendart.fss.or.kr/api/list.json", None),
        "krx": ("GET", "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
                {"menuId": "MDC0201"}),
        "naver_chart": ("GET", "https://api.finance.naver.com/siseJson.naver",
                        {"symbol": "005930", "requestType": "1",
                         "startTime": "20240102", "endTime": "20240105",
                         "timeframe": "day"}),
        "kind": ("GET", "https://kind.krx.co.kr/", None),
    }
    result, blocked = {}, set()
    sess = requests.Session()
    sess.headers.update({"User-Agent": _UA_POOL[0],
                         "Accept-Language": "ko-KR,ko;q=0.9"})
    for src, (method, url, params) in targets.items():
        detail = ""
        ok = False
        for prof in (_HEADER_PROFILES.get(src, [{}]) or [{}]):
            try:
                if src in _WARMUP:               # 쿠키 확보 후 판정(403 오판 방지)
                    try:
                        sess.get(_WARMUP[src], timeout=6)
                    except Exception:
                        pass
                r = sess.get(url, params=params, headers=prof, timeout=8)
                detail = f"HTTP {r.status_code}"
                if r.status_code == 200:
                    ok = True
                    break
            except Exception as e:
                detail = f"불가({type(e).__name__})"
        result[src] = ("OK " if ok else "차단/불가 ") + detail
        if not ok:
            blocked.add(src)
    log.kv("카나리 도달성 점검", result)
    if blocked:
        log.warn(f"[S04] 차단 판정 소스: {sorted(blocked)} — 폴백 경로로 즉시 전환"
                 "(본 수집에서 재시도하며 시간을 낭비하지 않음)")
    try:
        atomic_write_json(Path(state_dir) / "canary.json",
                          {"at": datetime.now().isoformat(), "result": result,
                           "blocked": sorted(blocked)})
    except Exception:
        pass
    return result, blocked

# ══════════════════════════════════════════════════════════════════════════════
# [S05] 시장데이터 허브 (전면 재작성 — 반복 조회 제거가 최대 목표)
#
#   이전 버전의 낭비:
#     · 완료 레지스트리 키에 종료월이 들어가 매달 2,500종목 × 12년 전체를 재수집
#     · 데이터 없는 종목(상폐/오류)을 매 실행 재시도
#     · build_price_matrix 가 매번 2,500개 parquet 를 개별 로드
#   이번 설계:
#     ① 증분 수집 : 캐시의 마지막 날짜 다음날부터만 받아 append
#     ② 벌크 수집 : 증분 구간은 '날짜별 전종목' 1콜로 처리(20영업일이면 40콜)
#     ③ 실패 기억 : 데이터 없는 티커는 쿨다운 기간 재시도 금지
#     ④ 통합 행렬 : close 매트릭스를 단일 parquet 로 캐시하고 증분 갱신
#   폴백 체인: pykrx → KRX(로그인) → FDR → 네이버차트 → yfinance
# ══════════════════════════════════════════════════════════════════════════════

class KRXAuthSession:
    """data.krx.co.kr 로그인 세션(베스트에포트). 실패해도 폴백 체인으로 진행."""
    LOGIN_URLS = [
        "https://data.krx.co.kr/contents/MMC/MMCLOGIN/mmcLogin.cmd",
        "https://data.krx.co.kr/comm/loginProc.cmd",
    ]
    GEN_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    def __init__(self, http, log):
        self.http, self.log = http, log
        self.logged_in = False

    def login(self):
        if not (KRX_MP_ID and KRX_MP_PW):
            self.log.info("[S05] KRX 계정 미입력 — 무로그인 + 폴백 체인 사용"
                          "(대부분의 통계는 무로그인으로도 조회된다)")
            return False
        try:
            self.http.warmup()
            for url in self.LOGIN_URLS:
                try:
                    r = self.http.get(url, method="POST",
                                      data={"usrId": KRX_MP_ID, "usrPwd": KRX_MP_PW,
                                            "mbrId": KRX_MP_ID, "mbrPwd": KRX_MP_PW},
                                      allow_codes=(200, 302), fast=True)
                    if r is not None:
                        self.logged_in = True
                        self.log.info("[S05] KRX 로그인 세션 확보")
                        return True
                except Exception:
                    continue
        except Exception as e:
            self.log.warn(f"KRX 로그인 실패(폴백 진행): {str(e)[:100]}")
        return False

    def fetch_snapshot(self, date_str):
        try:
            r = self.http.get(self.GEN_URL, method="POST", data={
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
                "mktId": "ALL", "trdDd": date_str.replace("-", ""),
                "share": "1", "money": "1", "csvxls_isNo": "false"}, fast=True)
            rows = (r.json().get("OutBlock_1") or r.json().get("output") or [])
            if not rows:
                return None
            df = pd.DataFrame(rows)
            def _num(s):
                return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")
            out = pd.DataFrame({
                "ticker": df["ISU_SRT_CD"].astype(str).str.zfill(6),
                "name": df.get("ISU_ABBRV", ""),
                "market": df.get("MKT_NM", "").astype(str).str.upper()
                            .str.replace("KOSDAQ GLOBAL", "KOSDAQ"),
                "close": _num(df["TDD_CLSPRC"]),
                "mcap": _num(df["MKTCAP"]),
                "shares": _num(df.get("LIST_SHRS", pd.Series(dtype=str)))})
            return out[out["close"].notna() & (out["mcap"] > 0)]
        except Exception:
            return None


class FdrPublicCache:
    """FinanceDataReader 가 GitHub 에 공개 미러하는 KRX 캐시.
    - 전종목 일별 스냅샷(OHLCV + 시가총액 + 상장주식수)을 1 GET 으로 받는다.
    - 상장폐지 전체 이력(사유·승계종목 포함)도 1 GET.
    KRX 로그인이 필요 없고 pykrx 대비 월 스냅샷 1건당 요청이 2회 → 1회로 준다.
    (출처: FinanceData/fdr_krx_data_cache — FDR 라이브러리가 실제로 쓰는 경로)"""
    BASE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache"
            "/refs/heads/master/data/listing")

    # 실측(2026-08): 이 캐시는 '최근 영업일' 스냅샷만 보관하고 과거 이력은 없다.
    # 과거 월마다 며칠씩 되짚으면 요청만 낭비하므로, 이 기간보다 오래된 날짜는
    # 아예 시도하지 않는다. 상장폐지 파일은 반대로 전체 이력을 담고 있다.
    SNAPSHOT_RECENT_DAYS = 45

    def __init__(self, store, log, quota):
        self.store, self.log, self.quota = store, log, quota
        self._http = None               # 지연 생성: SYNTH/오프라인에서 requests 불필요
        self.dead = False
        self.hist_dead = False          # 과거 스냅샷 부재 확인됨

    def _get_http(self):
        if self._http is None:
            self._http = HttpClient("fdrcache", self.store.local_root / "state",
                                    self.log, self.quota)
        return self._http

    def _csv(self, url):
        r = self._get_http().get(url, fast=True)
        return pd.read_csv(io.StringIO(r.text))

    def snapshot_near(self, date_ts, back_days=5):
        """해당 일자(또는 직전 영업일)의 전종목 스냅샷. 최근 구간에만 유효."""
        if self.dead or CFG.RUN_MODE != "FULL":
            return None
        age = (pd.Timestamp(datetime.now().date()) - pd.Timestamp(date_ts)).days
        if age > self.SNAPSHOT_RECENT_DAYS or self.hist_dead:
            return None                 # 과거 월: 헛된 왕복 금지 → pykrx/KRX 로 직행
        for k in range(back_days):
            d = (date_ts - pd.Timedelta(days=k))
            if d.weekday() >= 5:
                continue
            try:
                df = self._csv(f"{self.BASE}/krx/{d.strftime('%Y-%m-%d')}.csv")
            except SourceDown:
                self.dead = True
                return None
            except Exception:
                continue
            if df is None or not len(df):
                continue
            c = {str(x).lower(): x for x in df.columns}
            code = c.get("code") or c.get("symbol")
            if code is None:
                continue
            out = pd.DataFrame({
                "ticker": df[code].astype(str).str.zfill(6),
                "name": df[c["name"]] if "name" in c else "",
                "market": (df[c["market"]].astype(str).str.upper()
                           if "market" in c else "KOSPI"),
                "close": pd.to_numeric(df[c.get("close", code)], errors="coerce"),
                "mcap": pd.to_numeric(df[c["marcap"]], errors="coerce")
                        if "marcap" in c else np.nan,
                "shares": pd.to_numeric(df[c["stocks"]], errors="coerce")
                          if "stocks" in c else np.nan})
            out = out[out["close"].notna() & (out["mcap"] > 0)]
            if len(out) > 300:
                return out, d
        if age > 7:
            self.hist_dead = True       # 최근이 아닌데 실패 → 이 캐시엔 이력이 없다
            self.log.info("[S05] FDR 공개캐시는 최근 스냅샷만 보유 — 과거 월은 "
                          "pykrx/KRX 경로로 처리합니다(이후 재시도 안 함).")
        return None

    def delisting_history(self):
        if self.dead or CFG.RUN_MODE != "FULL":
            return None
        today = pd.Timestamp(datetime.now().date())
        for k in range(12):
            d = today - pd.Timedelta(days=k)
            if d.weekday() >= 5:
                continue
            try:
                df = self._csv(f"{self.BASE}/delisting/{d.strftime('%Y-%m-%d')}.csv")
            except SourceDown:
                self.dead = True
                return None
            except Exception:
                continue
            if df is not None and len(df) > 100:
                c = {str(x).lower(): x for x in df.columns}
                if "symbol" in c and "delistingdate" in c:
                    out = pd.DataFrame({
                        "ticker": df[c["symbol"]].astype(str).str.zfill(6),
                        "delist_date": pd.to_datetime(df[c["delistingdate"]],
                                                      errors="coerce")
                                         .dt.strftime("%Y-%m-%d"),
                        "reason": df[c["reason"]] if "reason" in c else "",
                        "to_symbol": (df[c["tosymbol"]].astype(str)
                                      if "tosymbol" in c else "")})
                    out = out[out["delist_date"].notna()]
                    self.log.info(f"[S05] FDR 공개캐시 상장폐지 이력 {len(out)}건 확보"
                                  "(1회 요청, KRX 로그인 불필요)")
                    return out
        return None


class MarketDataHub:
    SNAP_MIN_ROWS_FULL = 300
    SNAP_MIN_ROWS_SYNTH = 50

    def __init__(self, store, log, quota, blocked=None):
        self.store, self.log, self.quota = store, log, quota
        self.blocked = blocked or set()
        self.state_dir = store.local_root / "state"
        self._pykrx = self._fdr = None
        self._http_naver = self._http_krx = self._krx_auth = None
        self.src_stats = {}
        self._nodata_path = self.state_dir / "price_nodata.json"
        self._nodata = read_json_safe(self._nodata_path) or {}
        self._nodata_lock = threading.Lock()
        self.fdrc = FdrPublicCache(store, log, quota)

    # ── 지연 로더 ──────────────────────────────────────────────────────────
    def _get_pykrx(self):
        if self._pykrx is None:
            try:
                from pykrx import stock as _stk
                self._pykrx = _stk
            except Exception:
                self._pykrx = False
        return self._pykrx or None

    def _get_fdr(self):
        if self._fdr is None:
            try:
                import FinanceDataReader as _fdr
                self._fdr = _fdr
            except Exception:
                self._fdr = False
        return self._fdr or None

    def _naver_http(self):
        if self._http_naver is None:
            self._http_naver = HttpClient("naver_chart", self.state_dir, self.log,
                                          self.quota,
                                          blocked="naver_chart" in self.blocked)
        return self._http_naver

    def _krx(self):
        if self._krx_auth is None:
            self._http_krx = HttpClient("krx", self.state_dir, self.log, self.quota,
                                        blocked="krx" in self.blocked)
            self._krx_auth = KRXAuthSession(self._http_krx, self.log)
            self._krx_auth.login()
        return self._krx_auth

    def _bump(self, src, n=1):
        self.src_stats[src] = self.src_stats.get(src, 0) + n

    def _snap_min(self):
        return self.SNAP_MIN_ROWS_FULL if CFG.RUN_MODE == "FULL" \
            else self.SNAP_MIN_ROWS_SYNTH

    # ── 실패 기억(반복 조회 제거) ──────────────────────────────────────────
    def _is_nodata(self, ticker):
        rec = self._nodata.get(ticker)
        if not rec:
            return False
        try:
            age = (datetime.now() - pd.Timestamp(rec)).days
            return age < CFG.PRICE_NODATA_COOLDOWN
        except Exception:
            return False

    def _mark_nodata(self, ticker):
        with self._nodata_lock:
            self._nodata[ticker] = datetime.now().strftime("%Y-%m-%d")

    def flush_nodata(self):
        try:
            atomic_write_json(self._nodata_path, self._nodata)
        except Exception:
            pass

    # ── 월말 PIT 스냅샷 (과거 월은 불변 → 한 번 받으면 영구 재사용) ─────────
    def monthly_snapshot(self, ym):
        rel = f"snapshots/{ym}.parquet"
        df = self.store.load_df("parsed", rel, stage="ST02")
        if df is not None and len(df) >= self._snap_min():
            return df
        if CFG.RUN_MODE != "FULL":
            return df
        eom = month_end_date(ym)
        # ① FDR 공개 캐시: 1 GET 으로 전종목 스냅샷. KRX 로그인 불필요 → 1순위.
        got = self.fdrc.snapshot_near(eom)
        if got is not None:
            snap, d = got
            snap = snap.copy()
            snap["date"] = d.strftime("%Y-%m-%d")
            snap["ym"] = ym
            self._bump("snapshot:fdr_cache")
            self.store.save_df(snap, "parsed", rel, scope="common",
                               desc=f"전종목 월말 스냅샷 {ym}(FDR 공개캐시)", stage="ST02")
            return snap
        # ② pykrx(로그인 필요) → ③ KRX 직접
        for back in range(0, 10):
            d = eom - pd.Timedelta(days=back)
            if d.weekday() >= 5:
                continue
            snap = self._snapshot_for_date(d.strftime("%Y%m%d"))
            if snap is not None and len(snap) >= self._snap_min():
                snap = snap.copy()
                snap["date"] = d.strftime("%Y-%m-%d")
                snap["ym"] = ym
                self.store.save_df(snap, "parsed", rel, scope="common",
                                   desc=f"KRX 전종목 월말 스냅샷 {ym}", stage="ST02")
                return snap
        self.log.warn(f"스냅샷 실패: {ym}")
        return None

    def _snapshot_for_date(self, ymd):
        stk = self._get_pykrx()
        if stk is not None:
            try:
                frames = []
                for mkt in ("KOSPI", "KOSDAQ"):
                    c = stk.get_market_cap_by_ticker(ymd, market=mkt)
                    if c is not None and len(c):
                        c = c.reset_index()
                        c.columns = [str(x) for x in c.columns]
                        tick_col = "티커" if "티커" in c.columns else c.columns[0]
                        frames.append(pd.DataFrame({
                            "ticker": c[tick_col].astype(str).str.zfill(6),
                            "close": pd.to_numeric(c.get("종가"), errors="coerce"),
                            "mcap": pd.to_numeric(c.get("시가총액"), errors="coerce"),
                            "shares": pd.to_numeric(c.get("상장주식수"), errors="coerce"),
                            "market": mkt}))
                    time.sleep(random.uniform(*CFG.BASE_DELAY["pykrx"]))
                if frames:
                    out = pd.concat(frames, ignore_index=True)
                    if len(out) >= self._snap_min():
                        self._bump("snapshot:pykrx")
                        return out
            except Exception as e:
                self.log.warn(f"pykrx 스냅샷 실패({ymd}): {str(e)[:90]}")
        try:
            snap = self._krx().fetch_snapshot(ymd)
            if snap is not None and len(snap) >= self._snap_min():
                self._bump("snapshot:krx_direct")
                return snap
        except (SourceDown, QuotaExhausted):
            pass
        except Exception:
            pass
        return None

    # ── 일별 수정주가: 증분 수집 ───────────────────────────────────────────
    def _cached_price(self, ticker):
        return self.store.load_df("parsed", f"prices/{ticker}.parquet", stage="ST03")

    def price_history(self, ticker, start, end, market_hint="", force_full=False):
        """캐시가 있으면 '마지막 날짜 다음날부터'만 받아 이어붙인다.
        전체 히스토리를 다시 받는 일은 없다(사용자 최우선 불만 해소)."""
        rel = f"prices/{ticker}.parquet"
        cached = None if force_full else self._cached_price(ticker)
        end_ts = pd.Timestamp(end)
        if cached is not None and len(cached):
            try:
                mx = pd.to_datetime(cached["date"]).max()
                if (end_ts - mx).days <= CFG.PRICE_REFRESH_DAYS:
                    return cached                      # 충분히 최신 → 네트워크 접촉 없음
                if self._is_nodata(ticker):
                    return cached                      # 상폐 등 — 쿨다운 중
                if CFG.PRICE_INCREMENTAL:
                    inc_start = (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                    if pd.Timestamp(inc_start) > end_ts:
                        return cached
                    new = self._fetch_price_chain(ticker, inc_start, end, market_hint)
                    if new is None or not len(new):
                        self._mark_nodata(ticker)      # 더는 데이터가 없다(상폐 추정)
                        return cached
                    merged = self._merge_price(cached, new, ticker)
                    self.store.save_df(merged, "parsed", rel, scope="common",
                                       desc=f"일별 수정주가 {ticker}(증분)", stage="ST03")
                    return merged
            except Exception:
                pass
        if CFG.RUN_MODE != "FULL":
            return cached
        if cached is None and self._is_nodata(ticker):
            return None
        df = self._fetch_price_chain(ticker, start, end, market_hint)
        if df is None or df.empty:
            self._mark_nodata(ticker)
            return cached
        df = df.sort_values("date").drop_duplicates("date")
        df["asof"] = end_ts.strftime("%Y-%m-%d")
        self.store.save_df(df, "parsed", rel, scope="common",
                           desc=f"일별 수정주가 {ticker} src={df['src'].iloc[-1]}",
                           stage="ST03")
        return df

    def _merge_price(self, cached, new, ticker):
        """증분 병합 + 액면분할/무상증자 감지. 이어붙이는 지점에서 비정상 점프가
        보이면 수정주가 기준이 달라진 것이므로 전체 재수집을 예약한다."""
        out = pd.concat([cached, new], ignore_index=True)
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        out = out.sort_values("date").drop_duplicates("date", keep="last")
        try:
            c = pd.to_numeric(out["close"], errors="coerce")
            jump = (c / c.shift(1) - 1).abs()
            if (jump.tail(len(new) + 1) > 0.45).any():
                full = self._fetch_price_chain(
                    ticker, str(pd.to_datetime(out["date"]).min().date()),
                    str(pd.to_datetime(out["date"]).max().date()))
                if full is not None and len(full) > len(out) * 0.8:
                    self.log.info(f"[S05] {ticker}: 수정주가 기준 변경 감지 → 전체 재수집")
                    out = full.sort_values("date").drop_duplicates("date")
        except Exception:
            pass
        out["asof"] = datetime.now().strftime("%Y-%m-%d")
        return out

    def _naver_xml_full(self, ticker, start, end):
        """fchart sise.nhn: count=6000(≈24년)을 한 번에 준다. 전체 백필의 최적 경로.
        pykrx/FDR 이 '수정주가' 소스로 실제 사용하는 엔드포인트이기도 하다
        (배당은 미반영 — 가격수정만. OPEN_QUESTIONS 기재)."""
        try:
            import xml.etree.ElementTree as ET
            r = self._naver_http().get(
                "https://fchart.stock.naver.com/sise.nhn",
                params={"symbol": ticker, "timeframe": "day", "count": 6000,
                        "requestType": "0"},
                referer="https://finance.naver.com/", fast=True)
            rows = [n.get("data").split("|") for n in ET.fromstring(r.text).iter("item")
                    if n.get("data")]
            if len(rows) < 5:
                return None
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low",
                                             "close", "volume"])
            df["date"] = pd.to_datetime(df["date"], format="%Y%m%d",
                                        errors="coerce")
            df = df[df["date"].notna()]
            for c in ("open", "high", "low", "close", "volume"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df[(df["date"] >= pd.Timestamp(start))
                    & (df["date"] <= pd.Timestamp(end)) & (df["close"] > 0)]
            if not len(df):
                return None
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            df["src"] = "naver_xml"
            return df
        except (SourceDown, QuotaExhausted):
            raise
        except Exception:
            return None

    def _fetch_price_chain(self, ticker, start, end, market_hint=""):
        s8, e8 = str(start).replace("-", ""), str(end).replace("-", "")
        span_days = (pd.Timestamp(end) - pd.Timestamp(start)).days
        if span_days > 400:
            # 장기 백필: 1요청으로 24년치를 받는다(2,500종목 × 1콜).
            try:
                out = self._naver_xml_full(ticker, start, end)
                if out is not None:
                    self._bump("price:naver_xml")
                    return out
            except (SourceDown, QuotaExhausted):
                pass
        stk = self._get_pykrx()
        if stk is not None and "pykrx" not in self.blocked:
            try:
                d = stk.get_market_ohlcv(s8, e8, ticker, adjusted=True)
                out = self._norm_pykrx(d)
                if out is not None:
                    self._bump("price:pykrx")
                    return out
            except Exception:
                pass
        fdr = self._get_fdr()
        if fdr is not None:
            try:
                d = fdr.DataReader(ticker, start, end)
                out = self._norm_generic(d, "fdr")
                if out is not None:
                    self._bump("price:fdr")
                    return out
            except Exception:
                pass
        try:
            r = self._naver_http().get(
                "https://api.finance.naver.com/siseJson.naver",
                params={"symbol": ticker, "requestType": "1", "startTime": s8,
                        "endTime": e8, "timeframe": "day"}, fast=True)
            rows = json.loads(re.sub(r",\s*]", "]", r.text.replace("'", '"')))
            if len(rows) > 2:
                body = pd.DataFrame(rows[1:], columns=[str(c).strip() for c in rows[0]])
                out = pd.DataFrame({
                    "date": pd.to_datetime(body["날짜"], format="%Y%m%d")
                              .dt.strftime("%Y-%m-%d"),
                    "open": pd.to_numeric(body["시가"], errors="coerce"),
                    "high": pd.to_numeric(body["고가"], errors="coerce"),
                    "low": pd.to_numeric(body["저가"], errors="coerce"),
                    "close": pd.to_numeric(body["종가"], errors="coerce"),
                    "volume": pd.to_numeric(body["거래량"], errors="coerce"),
                    "src": "naver"})
                out = out[out["close"] > 0]
                if len(out):
                    self._bump("price:naver")
                    return out
        except (SourceDown, QuotaExhausted):
            pass
        except Exception:
            pass
        try:
            import yfinance as yf
            for suf in ([".KQ", ".KS"] if market_hint == "KOSDAQ" else [".KS", ".KQ"]):
                d = yf.download(ticker + suf, start=start, end=end, progress=False,
                                auto_adjust=True, threads=False)
                if d is not None and len(d):
                    d = d.reset_index()
                    if isinstance(d.columns, pd.MultiIndex):
                        d.columns = [c[0] for c in d.columns]
                    out = self._norm_generic(d, "yfinance")
                    if out is not None:
                        self._bump("price:yfinance")
                        return out
        except Exception:
            pass
        return None

    @staticmethod
    def _norm_pykrx(d):
        if d is None or not len(d):
            return None
        d = d.reset_index()
        d.columns = [str(c) for c in d.columns]
        out = pd.DataFrame({
            "date": pd.to_datetime(d[d.columns[0]]).dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(d.get("시가"), errors="coerce"),
            "high": pd.to_numeric(d.get("고가"), errors="coerce"),
            "low": pd.to_numeric(d.get("저가"), errors="coerce"),
            "close": pd.to_numeric(d.get("종가"), errors="coerce"),
            "volume": pd.to_numeric(d.get("거래량"), errors="coerce"),
            "src": "pykrx"})
        out = out[out["close"] > 0]
        return out if len(out) else None

    @staticmethod
    def _norm_generic(d, src):
        if d is None or not len(d):
            return None
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        dc = "date" if "date" in d.columns else d.columns[0]
        out = pd.DataFrame({
            "date": pd.to_datetime(d[dc]).dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(d.get("open"), errors="coerce"),
            "high": pd.to_numeric(d.get("high"), errors="coerce"),
            "low": pd.to_numeric(d.get("low"), errors="coerce"),
            "close": pd.to_numeric(d.get("close"), errors="coerce"),
            "volume": pd.to_numeric(d.get("volume"), errors="coerce"),
            "src": src})
        out = out[out["close"] > 0]
        return out if len(out) else None

    # ── 벌크 증분: '날짜별 전종목' 1콜로 최근 구간을 한 번에 채운다 ─────────
    def bulk_recent_by_date(self, tickers, end, log):
        """캐시된 종목들의 공통 결손 구간이 짧으면(수십 영업일) 종목별 호출 대신
        날짜별 전종목 조회로 처리한다. 2,500콜 → 40콜."""
        stk = self._get_pykrx()
        if not (CFG.PRICE_BULK_BY_DATE and stk is not None and CFG.RUN_MODE == "FULL"):
            return set()
        last_by_t, cache_by_t = {}, {}
        for t in tickers:
            df = self._cached_price(t)
            if df is not None and len(df):
                cache_by_t[t] = df
                last_by_t[t] = pd.to_datetime(df["date"]).max()
        if len(last_by_t) < 50:
            return set()
        end_ts = pd.Timestamp(end)
        stale = {t: d for t, d in last_by_t.items()
                 if (end_ts - d).days > CFG.PRICE_REFRESH_DAYS
                 and not self._is_nodata(t)}
        if not stale:
            return set(last_by_t)
        start_ts = min(stale.values()) + pd.Timedelta(days=1)
        days = pd.bdate_range(start_ts, end_ts)
        if not len(days) or len(days) > 90:
            return set()                      # 결손이 길면 종목별 증분이 더 정확
        self.log.info(f"[S05] 벌크 증분: {len(stale)}종목 × {len(days)}영업일 → "
                      f"{len(days)*2}콜로 처리(종목별이면 {len(stale)}콜)")
        Progress.begin("가격 벌크 증분(날짜별 전종목)", total=len(days))
        frames = []
        for d in days:
            if COLLECT_BUDGET.exceeded():
                break
            ymd = d.strftime("%Y%m%d")
            for mkt in ("KOSPI", "KOSDAQ"):
                try:
                    x = stk.get_market_ohlcv_by_ticker(ymd, market=mkt)
                    if x is None or not len(x):
                        continue
                    x = x.reset_index()
                    x.columns = [str(c) for c in x.columns]
                    tc = "티커" if "티커" in x.columns else x.columns[0]
                    frames.append(pd.DataFrame({
                        "ticker": x[tc].astype(str).str.zfill(6),
                        "date": d.strftime("%Y-%m-%d"),
                        "open": pd.to_numeric(x.get("시가"), errors="coerce"),
                        "high": pd.to_numeric(x.get("고가"), errors="coerce"),
                        "low": pd.to_numeric(x.get("저가"), errors="coerce"),
                        "close": pd.to_numeric(x.get("종가"), errors="coerce"),
                        "volume": pd.to_numeric(x.get("거래량"), errors="coerce"),
                        "src": "pykrx_bulk"}))
                except Exception:
                    continue
                time.sleep(random.uniform(*CFG.BASE_DELAY["pykrx"]))
            Progress.tick()
        if not frames:
            return set()
        allrows = pd.concat(frames, ignore_index=True)
        allrows = allrows[allrows["close"] > 0]
        self._bump("price:pykrx_bulk", len(days) * 2)
        filled = set()
        for t, g in allrows.groupby("ticker"):
            if t not in cache_by_t:
                continue
            g = g.drop(columns=["ticker"])
            merged = self._merge_price(cache_by_t[t], g, t)
            self.store.save_df(merged, "parsed", f"prices/{t}.parquet", scope="common",
                               desc=f"일별 수정주가 {t}(벌크증분)", stage="ST03")
            filled.add(t)
        self.log.info(f"[S05] 벌크 증분 반영 {len(filled)}종목")
        return filled

    def collect_prices(self, tickers, start, end, market_map=None):
        """① 벌크 증분으로 최근 구간을 메우고 ② 남은 종목만 개별 수집."""
        tickers = list(dict.fromkeys(tickers))
        filled = self.bulk_recent_by_date(tickers, end, self.log)
        mm = market_map or {}
        rest = [t for t in tickers if t not in filled and not self._is_nodata(t)]
        skipped = len(tickers) - len(rest) - 0
        if skipped:
            self.log.info(f"[S05] 개별 수집 대상 {len(rest)}종목 "
                          f"(벌크/쿨다운으로 {skipped}종목 생략)")
        pf = ParallelFetcher("prices", self.store, self.log, max_workers=3)
        def _work(t):
            return self.price_history(t, start, end, mm.get(t, ""))
        # 완료 키에 종료월을 넣지 않는다 — 넣으면 매달 전체가 미완료로 뒤집힌다.
        # 최신성 판단은 캐시 내부의 마지막 날짜로 한다(위 price_history).
        pf.run(rest, _work, key_fn=lambda t: f"px_{t}", desc="일별 수정주가 수집")
        self.flush_nodata()

    # ── 통합 close 행렬 (매번 수천 파일을 읽지 않는다) ─────────────────────
    def close_matrix(self, tickers, log):
        rel = "close_matrix.parquet"
        meta_p = self.store.local_root / "state" / "close_matrix_meta.json"
        meta = read_json_safe(meta_p) or {}
        cached = self.store.load_df("features", rel, stage="ST10")
        want = set(tickers)
        if cached is not None and len(cached):
            try:
                have = set(cached.columns) - {"date"}
                if want <= have and meta.get("asof") == self._price_stamp(tickers):
                    m = cached.set_index(pd.to_datetime(cached["date"])).drop(
                        columns=["date"])
                    log.info(f"[S05] close 행렬 캐시 적중: {m.shape[1]}종목 × "
                             f"{m.shape[0]}일 (개별 파일 재로드 없음)")
                    return m.astype("float32")
            except Exception:
                pass
        Progress.begin("close 행렬 구성", total=len(tickers))
        cols, miss = {}, 0
        for t in tickers:
            df = self._cached_price(t)
            Progress.tick()
            if df is None or not len(df):
                miss += 1
                continue
            s = pd.Series(pd.to_numeric(df["close"], errors="coerce").to_numpy(),
                          index=pd.to_datetime(df["date"]), name=t)
            cols[t] = s[~s.index.duplicated()]
        if not cols:
            return None
        wide = pd.DataFrame(cols).sort_index().astype("float32")
        out = wide.reset_index().rename(columns={"index": "date"})
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        self.store.save_df(out, "features", rel, scope="dedicated",
                           desc="통합 close 행렬", stage="ST10")
        try:
            atomic_write_json(meta_p, {"asof": self._price_stamp(tickers),
                                       "n": len(cols)})
        except Exception:
            pass
        log.info(f"[S05] close 행렬 구성: {wide.shape[1]}종목 × {wide.shape[0]}일 "
                 f"(가격 미확보 {miss}종목 → 월간 스냅샷 폴백)")
        return wide

    def _price_stamp(self, tickers):
        """가격 캐시 상태 지문 — 파일 개수 + 최근 수정시각으로 재구성 필요 판단."""
        d = self.store.local_root / "cache" / "parsed" / "prices"
        try:
            files = list(d.glob("*.parquet")) + list(d.glob("*.pkl"))
            if not files:
                return "none"
            mt = max(f.stat().st_mtime for f in files)
            return f"{len(files)}@{int(mt)}@{len(tickers)}"
        except Exception:
            return "unknown"

    # ── 벤치마크 / 섹터 / 개인비중 ─────────────────────────────────────────
    def benchmark_series(self, code, start, end):
        rel = f"benchmarks/{code}.parquet"
        df = self.store.load_df("parsed", rel, stage="ST03")
        if df is not None and len(df):
            try:
                if (pd.Timestamp(end) - pd.to_datetime(df["date"]).max()).days \
                        <= CFG.PRICE_REFRESH_DAYS:
                    return df
            except Exception:
                pass
        out = None
        fdr = self._get_fdr()
        if fdr is not None:
            try:
                out = self._norm_generic(fdr.DataReader(code, start, end), "fdr")
                if out is not None:
                    out = out[["date", "close", "src"]]
            except Exception:
                out = None
        if out is None:
            try:
                import yfinance as yf
                sym = {"KS11": "^KS11", "KQ11": "^KQ11"}.get(code, code)
                d = yf.download(sym, start=start, end=end, progress=False,
                                auto_adjust=True, threads=False)
                o = self._norm_generic(d.reset_index() if d is not None else None,
                                       "yfinance")
                out = o[["date", "close", "src"]] if o is not None else None
            except Exception:
                out = None
        if out is not None and len(out):
            self.store.save_df(out, "parsed", rel, scope="common",
                               desc=f"지수 {code}", stage="ST03")
        return out

    def sector_map(self):
        rel = "sectors/krx_sector_map.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None and len(df) > 500:
            return df
        fdr = self._get_fdr()
        if fdr is not None:
            for lst in ("KRX", "KOSPI", "KOSDAQ"):
                try:
                    d = fdr.StockListing(lst)
                    d.columns = [str(c).lower() for c in d.columns]
                    code_c = "code" if "code" in d.columns else "symbol"
                    sec_c = next((c for c in ("sector", "industry", "sectorname")
                                  if c in d.columns), None)
                    if sec_c is None or code_c not in d.columns:
                        continue
                    out = pd.DataFrame({
                        "ticker": d[code_c].astype(str).str.zfill(6),
                        "sector": d[sec_c].astype(str).fillna("UNKNOWN")
                                    .replace("nan", "UNKNOWN")}).drop_duplicates("ticker")
                    if len(out) > 500:
                        self.store.save_df(out, "parsed", rel, scope="common",
                                           desc=f"섹터맵({lst}) — 현재분류 소급적용",
                                           stage="ST05")
                        self._bump("sector:fdr")
                        return out
                except Exception:
                    continue
        return pd.DataFrame(columns=["ticker", "sector"])

    def investor_ratio(self, tickers, years):
        rel = "investor/individual_ratio.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None and len(df):
            return df
        stk = self._get_pykrx()
        est = len(tickers) * len(years)
        if (not CFG.COLLECT_INVESTOR_RATIO) or stk is None or est > 6000:
            self.log.info(f"[S05] 개인비중 직접수집 생략(예상 {est}건) → "
                          "KOSDAQ×소형 프록시 사용(mechanism_tests.md 에 명시)")
            return None
        pf = ParallelFetcher("inv_ratio", self.store, self.log, max_workers=2)
        items = [(t, y) for t in tickers for y in years]
        def _work(it):
            t, y = it
            try:
                d = stk.get_market_trading_value_by_investor(f"{y}0101", f"{y}1231", t)
                if d is None or not len(d):
                    return None
                d = d.reset_index()
                d.columns = [str(c) for c in d.columns]
                icol = d.columns[0]
                vcol = "거래대금" if "거래대금" in d.columns else d.columns[-1]
                tot = pd.to_numeric(d[vcol], errors="coerce").abs().sum()
                ind = pd.to_numeric(
                    d.loc[d[icol].astype(str).str.contains("개인"), vcol],
                    errors="coerce").abs().sum()
                if tot > 0:
                    return {"ticker": t, "year": int(y), "indiv_ratio": float(ind / tot)}
            except Exception:
                return None
            return None
        got = [g for g in pf.run(items, _work, key_fn=lambda it: f"iv_{it[0]}_{it[1]}",
                                 desc="개인 매매비중") if g]
        if got:
            out = pd.DataFrame(got)
            self.store.save_df(out, "parsed", rel, scope="common",
                               desc="연도별 개인 매매비중(pykrx)", stage="ST05")
            return out
        return None

# ══════════════════════════════════════════════════════════════════════════════
# [S06] 리포트 메타 수집 (전면 재작성)
#
#   ■ 수집 전략의 핵심 — 요청당 산출량(reports per request)으로 경로를 고른다.
#     · 한경 컨센서스 리스트 : 1요청 = 최대 80건 + 작성자 포함  → 확장 가능 ★주력
#       157개월 × 약 30페이지 ≈ 4,700요청 ≈ 45분. 이것이 유일하게 완주 가능한 경로.
#     · 네이버 리스트        : 1요청 = 약 30건, 작성자 없음(증권사만) → 항상 수집
#     · 네이버 상세 페이지   : 1요청 = 1건, 작성자 있음 → 확장 불가, 전역 예산제
#     · PDF 본문             : 1요청 = 1건 + 수 MB + 파싱 실패 빈발 → 기본 비활성
#     이전 버전은 상세/PDF 를 '월당 한도'로 돌려 157개월이면 31만 요청(48시간)이
#     필요했다. 시간 예산의 문제가 아니라 경로 선택의 문제였다.
#
#   ■ 한경이 막히면(403/로그인월) 계약 §3 의 공식 폴백인 broker×sector(하우스 단위)로
#     내려간다. 네이버 리스트만으로 증권사는 100% 확보되므로 폴백은 항상 실행 가능하다.
#
#   식별자 규약(계약 §5): analyst_id = f"{analyst}@{broker}" (고정),
#                         analyst_person_id = 정규화 인명(이직 추적용) — 혼동 금지.
# ══════════════════════════════════════════════════════════════════════════════

_ANALYST_TITLE_RE = re.compile(
    r"(수석|책임|선임|전문|연구|투자|애널리스트|Analyst|analyst|위원|연구원|팀장|"
    r"파트장|이사|상무|본부장|센터장|RA|CFA|Ph\.?D)\.?")
_HANGUL_NAME_RE = re.compile(r"^[가-힣]{2,4}$")

# 증권사 리브랜딩 별칭(하우스 연속성 유지 — 누락 시 개명이 가짜 H-EXIT 으로 보인다)
_BROKER_ALIAS = {
    "미래에셋대우": "미래에셋", "미래에셋증권": "미래에셋", "대우": "미래에셋",
    "KB투자": "KB", "현대": "KB",                     # 현대증권→KB증권(2017 합병)
    "HMC투자": "현대차", "현대차투자": "현대차",
    "동부": "DB금융투자", "DB": "DB금융투자", "DB금투": "DB금융투자",
    "메리츠종금": "메리츠", "메리츠종합금융": "메리츠",
    "하이투자": "하이", "아이엠": "하이", "iM": "하이",   # 하이투자→iM증권(2024)
    "이베스트투자": "이베스트", "LS": "이베스트",         # 이베스트→LS증권(2024)
    "케이프투자": "케이프", "신한금융투자": "신한", "신한투자": "신한",
    "삼성증권": "삼성", "한국투자": "한투", "한국": "한투", "한화투자": "한화",
    "유안타": "유안타", "동양": "유안타",                # 동양증권→유안타(2014)
    "SK": "SK", "키움": "키움", "NH투자": "NH", "우리투자": "NH",
}

def norm_broker(name):
    s = re.sub(r"\s|\(주\)|㈜", "", str(name))
    s = re.sub(r"(투자증권|금융투자|증권|투자|Investment|Securities)$", "", s)
    s = s.strip() or "UNKNOWN"
    return _BROKER_ALIAS.get(s, s)

def norm_analysts(raw):
    """작성자 문자열 → 정규화 인명 리스트. 공저자는 각자 1건 인정(§OPEN_QUESTIONS)."""
    if raw is None:
        return []
    s = unicodedata.normalize("NFKC", str(raw))
    s = _ANALYST_TITLE_RE.sub(" ", s)
    parts = re.split(r"[,/·;·&]|\s{2,}", s)
    out = []
    for p in parts:
        p = re.sub(r"[^가-힣]", "", p.strip())
        if _HANGUL_NAME_RE.match(p) and p not in out:
            out.append(p)
    return out


def _try_import(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml" if _try_import("lxml") else "html.parser")


def _month_cache_complete(df):
    """월 캐시가 '완결'인지 판정. 타임박스/네트워크 오류로 페이지네이션이 중도에
    끊긴 달을 완결로 착각하면, 그 달은 영구히 부분 데이터로 굳어져 이후 모든
    통계를 조용히 편향시킨다(재수집 트리거가 없기 때문). _complete 플래그가
    없는 옛 캐시는 보수적으로 '미완결'로 보아 한 번 더 확인한다."""
    if df is None or not len(df):
        return False
    if "_complete" not in df.columns:
        return False
    try:
        return int(pd.to_numeric(df["_complete"], errors="coerce").fillna(0).iloc[0]) == 1
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# 한경 컨센서스 — 주력 경로(리스트에 작성자 포함)
# ──────────────────────────────────────────────────────────────────────────────
class HankyungConsensusCollector:
    """엔드포인트/파라미터 변형을 순차 시도하고, 첫 성공 형태를 고정해 재사용한다.
    403·로그인월은 재시도 없이 즉시 폴백으로 넘긴다(시간 낭비 금지)."""

    # ※ skinType=business 가 없으면 '작성자' 열 자체가 응답에 포함되지 않는다.
    #   이 파라미터가 이 수집기의 존재 이유이므로 절대 빼지 말 것.
    ENDPOINTS = [
        ("https://consensus.hankyung.com/analysis/list", "utf-8",
         lambda d0, d1, pg: {"skinType": "business", "sdate": d0, "edate": d1,
                             "now_page": pg, "pagenum": 80, "report_type": "CO",
                             "order_type": "", "search_text": "",
                             "business_code": ""}),
        ("https://consensus.hankyung.com/analysis/list", "utf-8",
         lambda d0, d1, pg: {"skinType": "business", "sdate": d0, "edate": d1,
                             "now_page": pg, "pagenum": 50, "report_type": "CO"}),
        # 구 경로: http + EUC-KR
        ("http://consensus.hankyung.com/apps.analysis/analysis.list", "euc-kr",
         lambda d0, d1, pg: {"skinType": "business", "sdate": d0, "edate": d1,
                             "now_page": pg, "pagenum": 80, "report_type": "CO"}),
    ]

    def __init__(self, store, log, quota, blocked=False):
        self.store, self.log = store, log
        self.http = HttpClient("hankyung", store.local_root / "state", log, quota,
                               blocked=blocked)
        self.blocked = blocked
        self.endpoint_idx = None
        self._probe_done = False

    def _probe(self):
        """어떤 엔드포인트 형태가 살아 있는지 1회만 탐색하고 고정한다."""
        if self._probe_done:
            return self.endpoint_idx is not None
        self._probe_done = True
        d0, d1 = "2024-11-01", "2024-11-30"
        for i, (url, enc, mk) in enumerate(self.ENDPOINTS):
            try:
                r = self.http.get(url, params=mk(d0, d1, 1), encoding=enc, fast=True)
                rows = self._parse_list(r.text)
                if rows:
                    self.endpoint_idx = i
                    n_auth = sum(1 for x in rows if norm_analysts(x["analyst_raw"]))
                    self.log.info(f"[S06] 한경 엔드포인트 #{i} 확인 — 주력 경로 사용 "
                                  f"(표본 {len(rows)}건 중 작성자 {n_auth}건)")
                    if n_auth == 0:
                        self.log.warn("[S06] 한경 응답에 작성자가 없다 — skinType 파라미터 "
                                      "또는 열 구조 변경 가능성. 하우스 단위 폴백 검토")
                    return True
            except SourceDown:
                self.blocked = True
                self.log.warn("[S06] 한경 차단 확정 → 네이버 경로 + 하우스 단위 폴백 검토")
                return False
            except Exception:
                continue
        self.blocked = True
        self.log.warn("[S06] 한경 유효 엔드포인트 없음 → 네이버 경로로 전환")
        return False

    def available(self):
        return (not self.blocked) and self._probe()

    def collect_month(self, ym):
        rel = f"reports_meta/hankyung/{ym}.parquet"
        df = self.store.load_df("parsed", rel, stage="ST04")
        if _month_cache_complete(df):
            return df
        if not self.available():
            return df if df is not None else pd.DataFrame()
        url, enc, mk = self.ENDPOINTS[self.endpoint_idx]
        p = pd.Period(ym, freq="M")
        d0 = p.to_timestamp(how="start").strftime("%Y-%m-%d")
        d1 = p.to_timestamp(how="end").strftime("%Y-%m-%d")
        rows, seen_sig, complete = [], set(), False
        for page in range(1, 120):
            if COLLECT_BUDGET.exceeded():
                break                      # 중도 절단 → complete=False 로 표시
            try:
                r = self.http.get(url, params=mk(d0, d1, page), encoding=enc)
            except (SourceDown, QuotaExhausted):
                self.blocked = True
                break
            except Exception:
                break
            if "로그인" in r.text[:3000] and "작성일" not in r.text[:8000]:
                self.log.warn("[S06] 한경 로그인월 감지 → 소스 차단 처리")
                self.blocked = True
                break
            page_rows = self._parse_list(r.text)
            if not page_rows:
                complete = True            # 자연 종료
                break
            sig = sha1_text(str(page_rows[0]) + str(len(page_rows)))
            if sig in seen_sig:            # 페이지 파라미터 무시하고 같은 내용 반환
                complete = True
                break
            seen_sig.add(sig)
            rows += page_rows
            if len(page_rows) < 40:
                complete = True
                break
        else:
            complete = True
        if not rows:
            return df if df is not None else pd.DataFrame()
        out = pd.DataFrame(rows).drop_duplicates(subset=["nid"])
        out["ym"] = ym
        out["source"] = "hankyung"
        out["_complete"] = int(complete)
        self.store.save_df(out, "parsed", rel, scope="common",
                           desc=f"한경 컨센서스 {ym} ({len(out)}건, "
                                f"{'완결' if complete else '부분'})", stage="ST04")
        return out

    def _parse_list(self, html):
        """기업(business) 탭 열 구조: 9칸
           [0]작성일 [1]제목 [2]적정가격 [3]투자의견 [4]작성자 [5]제공출처
           [6]기업정보 [7]차트 [8]첨부
        뒤에서 세면(-3/-2) 기업정보·차트를 작성자·증권사로 오인한다.
        고정 인덱스를 1순위로 쓰되, 열 수가 다르면 내용 기반으로 판별한다."""
        out = []
        if not html or "<" not in html:
            return out
        try:
            soup = _soup(html)
            trs = soup.select("div.table_style01 table tbody tr") or soup.find_all("tr")
            for tr in trs:
                tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(tds) < 6:
                    continue
                date_txt = next((t for t in tds
                                 if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)), "")
                if not date_txt:
                    continue
                joined = " ".join(tds)
                mt = re.search(r"\((\d{6})\)", joined)
                if not mt:
                    continue
                title = next((t for t in tds if "(" + mt.group(1) + ")" in t), tds[1])
                writer, origin = tds[4], tds[5]
                if not norm_analysts(writer):
                    # 열 구조가 바뀐 경우: 인명처럼 보이는 셀을 작성자로,
                    # 그 다음 비어 있지 않은 셀을 증권사로 채택
                    for i, t in enumerate(tds):
                        if i >= 2 and norm_analysts(t) and t != title:
                            writer = t
                            origin = next((tds[j] for j in range(i + 1, len(tds))
                                           if tds[j].strip()), origin)
                            break
                out.append({"pub_date": date_txt, "ticker": mt.group(1),
                            "title": title, "broker": origin,
                            "analyst_raw": writer,
                            "nid": sha1_text(date_txt + title + origin),
                            "pdf_url": ""})
        except Exception:
            return out
        return out


# ──────────────────────────────────────────────────────────────────────────────
# 네이버 금융 리서치 — 항상 수집(증권사 100%), 작성자는 예산 내 보조 확보
# ──────────────────────────────────────────────────────────────────────────────
class NaverResearchCollector:
    LIST_URL = "https://finance.naver.com/research/company_list.naver"
    READ_URL = "https://finance.naver.com/research/company_read.naver"

    def __init__(self, store, log, quota, detail_budget=None, pdf_budget=None,
                 blocked=False):
        self.store, self.log = store, log
        self.http = HttpClient("naver_research", store.local_root / "state", log,
                               quota, blocked=blocked)
        self.detail_budget = detail_budget or RequestBudget(
            "naver_detail", CFG.BUDGET_NAVER_DETAIL, log)
        self.pdf_budget = pdf_budget or RequestBudget("naver_pdf", CFG.BUDGET_PDF, log)

    # ── 리스트(싸다) ───────────────────────────────────────────────────────
    def collect_month(self, ym):
        rel = f"reports_meta/naver/{ym}.parquet"
        df = self.store.load_df("parsed", rel, stage="ST04")
        if _month_cache_complete(df):
            return df
        p = pd.Period(ym, freq="M")
        d0 = p.to_timestamp(how="start").strftime("%Y-%m-%d")
        d1 = p.to_timestamp(how="end").strftime("%Y-%m-%d")
        rows, prev_sig, complete = [], None, False
        for page in range(1, 200):
            if COLLECT_BUDGET.exceeded():
                break
            try:
                r = self.http.get(self.LIST_URL, params={
                    "searchType": "writeDate", "writeFromDate": d0,
                    "writeToDate": d1, "page": page}, encoding="euc-kr")
            except (SourceDown, QuotaExhausted):
                break
            except Exception:
                break
            page_rows = self._parse_list(r.text)
            if not page_rows:
                complete = True
                break
            sig = sha1_text(str(page_rows[0]))
            if sig == prev_sig:            # 마지막 페이지 이후 동일 내용 반복 방지
                complete = True
                break
            prev_sig = sig
            rows += page_rows
            if len(page_rows) < 5:
                complete = True
                break
        else:
            complete = True
        if not rows:
            return df if df is not None else pd.DataFrame()
        # 기존 부분 캐시가 있으면 작성자 보강분을 잃지 않도록 병합한다
        out = pd.DataFrame(rows)
        out["analyst_raw"] = ""
        if df is not None and len(df) and "analyst_raw" in df.columns:
            prev = df[df["analyst_raw"].astype(str).str.len() > 0][["nid", "analyst_raw"]]
            if len(prev):
                out = out.drop(columns=["analyst_raw"]).merge(prev, on="nid", how="left")
                out["analyst_raw"] = out["analyst_raw"].fillna("")
        out = out.drop_duplicates(subset=["nid"])
        out["ym"] = ym
        out["source"] = "naver"
        out["_complete"] = int(complete)
        self.store.save_df(out, "parsed", rel, scope="common",
                           desc=f"네이버 리서치 {ym} ({len(out)}건, "
                                f"{'완결' if complete else '부분'})", stage="ST04")
        return out

    def _parse_list(self, html):
        out = []
        if not html:
            return out
        try:
            soup = _soup(html)
            for tr in soup.select("table.type_1 tr"):
                tds = tr.find_all("td")
                if len(tds) < 5:
                    continue
                a_code = tr.select_one("a[href*='item/main']")
                a_read = tr.select_one("a[href*='company_read']")
                if a_code is None or a_read is None:
                    continue
                m = re.search(r"code=(\d{6})", a_code.get("href", ""))
                nid = re.search(r"nid=(\d+)", a_read.get("href", ""))
                pdf = tr.select_one("a[href$='.pdf']")
                date_txt = next((td.get_text(strip=True) for td in tds
                                 if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}",
                                                 td.get_text(strip=True))), "")
                if not (m and nid and date_txt):
                    continue
                out.append({
                    "pub_date": "20" + date_txt.replace(".", "-"),
                    "ticker": m.group(1), "title": a_read.get_text(strip=True),
                    "broker": tds[2].get_text(strip=True) if len(tds) > 2 else "",
                    "nid": nid.group(1),
                    "pdf_url": pdf.get("href") if pdf else ""})
        except Exception:
            return out
        return out

    # ── 상세(비싸다: 1요청=1건) — 전역 예산 안에서만 ──────────────────────
    def enrich_analysts(self, df, max_items, tag=""):
        """df 의 일부 행에 대해 상세 페이지에서 작성자를 추출한다.
        반환: (갱신된 df, 시도건수). 예산/타임박스 초과 시 즉시 중단."""
        if df is None or not len(df):
            return df, 0
        df = df.copy()
        if "analyst_raw" not in df.columns:
            df["analyst_raw"] = ""
        need = df[df["analyst_raw"].astype(str).str.len() == 0]
        idxs = list(need.index)[:max(0, int(max_items))]
        if not idxs:
            return df, 0
        Progress.begin(f"네이버 상세 작성자 추출{tag}", total=len(idxs),
                       extra=f"예산잔여 {self.detail_budget.left()}")
        tried = 0
        lock = threading.Lock()

        def _work(idx):
            nonlocal tried
            if COLLECT_BUDGET.exceeded():
                raise BudgetExceeded("타임박스")
            nid = df.at[idx, "nid"]
            cache_key = f"naver_read/{nid}"
            html = self.store.load_raw_text(cache_key)
            if html is None:
                if not self.detail_budget.take():
                    raise BudgetExceeded("상세 요청예산")
                r = self.http.get(self.READ_URL, params={"nid": nid, "page": "1"},
                                  encoding="euc-kr", fast=True)
                html = r.text
                self.store.save_raw_text(cache_key, html)
            names = self._names_from_text(html)
            if not names and CFG.EXTRACT_ANALYST_FROM_PDF:
                url = str(df.at[idx, "pdf_url"] or "")
                if not url:
                    m = re.search(r"href=[\"']([^\"']+\.pdf)[\"']", html or "")
                    url = m.group(1) if m else ""
                if url.startswith("http") and self.pdf_budget.take():
                    names = self._names_from_pdf(url)
            with lock:
                tried += 1
            return (idx, ",".join(names) if names else "")

        results = []
        try:
            with ThreadPoolExecutor(max_workers=CFG.MAX_WORKERS) as ex:
                futs = {ex.submit(_work, i): i for i in idxs}
                for fut in as_completed(futs):
                    try:
                        results.append(fut.result())
                    except (BudgetExceeded, SourceDown, QuotaExhausted):
                        for f2 in futs:
                            f2.cancel()
                        break
                    except Exception:
                        pass
                    Progress.tick()
        except Exception as e:
            self.log.warn(f"[S06] 상세 추출 중단: {str(e)[:100]}")
        for idx, val in results:
            if val:
                df.at[idx, "analyst_raw"] = val
        return df, tried

    def _names_from_text(self, html):
        if not html:
            return []
        txt = re.sub(r"<[^>]+>", " ", html)
        cands = []
        for pat in (r"([가-힣]{2,4})\s*(?:수석|책임|선임)?\s*연구원",
                    r"([가-힣]{2,4})\s*애널리스트", r"Analyst[:\s]*([가-힣]{2,4})",
                    r"작성자[:\s]*([가-힣]{2,4})"):
            cands += re.findall(pat, txt)
        return norm_analysts(",".join(cands[:4]))

    def _names_from_pdf(self, url):
        """PDF 1~2쪽 작성자 추출. 깨진 PDF 가 많아 pypdf 가 대량 경고를 내므로
        stdout/stderr 를 통째로 삼킨다(정상 동작 중 화면 오염 방지)."""
        try:
            import io as _io
            import contextlib
            import pypdf
            r = self.http.get(url, fast=True, stream=True)
            blob = r.content
            if len(blob) > CFG.PDF_MAX_MB * 1e6:
                return []
            sink = _io.StringIO()
            with contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
                reader = pypdf.PdfReader(_io.BytesIO(blob), strict=False)
                txt = ""
                for pg in reader.pages[:2]:
                    txt += pg.extract_text() or ""
            cands = []
            for pat in (r"([가-힣]{2,4})\s*(?:수석|책임|선임)?\s*연구원",
                        r"Analyst\s*([가-힣]{2,4})", r"([가-힣]{2,4})\s*Analyst"):
                cands += re.findall(pat, txt)
            return norm_analysts(",".join(cands[:4]))
        except Exception:
            return []


# ──────────────────────────────────────────────────────────────────────────────
# 금융투자협회 전문인력 (베스트에포트 — 실패 시 계약 §3 의 재직 프록시로 대체)
# ──────────────────────────────────────────────────────────────────────────────
class KofiaCollector:
    def __init__(self, store, log, quota):
        self.store, self.log = store, log
        self.http = HttpClient("kofia", store.local_root / "state", log, quota)

    def try_fetch_registry(self):
        rel = "kofia/analyst_registry.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None and len(df):
            return df
        legacy = self.store.find_legacy_df(["kofia"], ["analyst"])
        if legacy is None:
            legacy = self.store.find_legacy_df(["전문인력"], [])
        if legacy is not None:
            return legacy
        self.log.info("[S06] 금투협 정형 API 미확보 → 재직 프록시 사용(계약 §3 공식 폴백): "
                      "'동일 인물이 같은 기간 다른 종목을 계속 커버 중인가'")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# DART — 월별 공시집계(§6.3 통제변수). 총 페이지 수를 먼저 알아내 병렬로 받는다.
# ──────────────────────────────────────────────────────────────────────────────
class DartCollector:
    BASE = "https://opendart.fss.or.kr/api"
    _EARN_RE = re.compile(r"사업보고서|반기보고서|분기보고서|영업\s*\(?잠정\)?\s*실적|"
                          r"매출액또는손익구조|연결재무제표기준영업")

    def __init__(self, store, log, quota):
        self.store, self.log, self.quota = store, log, quota
        self.http = HttpClient("dart", store.local_root / "state", log, quota)
        self.keys = [k for k in DART_API_KEYS if k]
        self._ki = 0
        self._lock = threading.Lock()

    def _key(self):
        with self._lock:
            alive = [k for k in self.keys
                     if not self.quota.is_exhausted(f"dart:{k[:8]}")]
            if not alive:
                raise QuotaExhausted("dart: 모든 키 소진")
            self._ki = (self._ki + 1) % len(alive)
            return alive[self._ki]

    def available(self):
        if not self.keys:
            return False
        try:
            self._key()
            return True
        except QuotaExhausted:
            return False

    def quota_note(self):
        """남은 호출량을 '관측 기반'으로 보고한다(고정 상수 가정 없음)."""
        out = {}
        for k in self.keys:
            kk = f"dart:{k[:8]}"
            left = self.quota.budget_left(kk)
            out[kk] = (f"사용 {self.quota.used(kk)}건, "
                       + ("소진" if left == 0 else
                          (f"잔여 {left}건" if left is not None else "한도 미관측")))
        return out

    def corp_map(self):
        rel = "dart/corp_map.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None and len(df) > 1000:
            return dict(zip(df["corp_code"], df["ticker"]))
        if not self.available():
            return {}
        try:
            key = self._key()
            r = self.http.get(f"{self.BASE}/corpCode.xml",
                              params={"crtfc_key": key}, quota_key=f"dart:{key[:8]}")
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            xml = zf.read(zf.namelist()[0]).decode("utf-8", "ignore")
            pat = re.compile(r"<corp_code>(\d+)</corp_code>.*?<stock_code>([0-9A-Z]*)"
                             r"</stock_code>", re.S)
            rows = [{"corp_code": c, "ticker": s.strip().zfill(6)}
                    for c, s in pat.findall(xml) if s.strip()]
            df = pd.DataFrame(rows).drop_duplicates("corp_code")
            self.store.save_df(df, "parsed", rel, scope="common",
                               desc="DART corp_code→ticker 맵", stage="ST05")
            self.log.info(f"[S06] DART 종목 매핑 {len(df)}건 확보")
            return dict(zip(df["corp_code"], df["ticker"]))
        except Exception as e:
            self.log.warn(f"DART corp_map 실패: {str(e)[:110]}")
            return {}

    def _page(self, b, e, page):
        key = self._key()
        r = self.http.get(f"{self.BASE}/list.json", params={
            "crtfc_key": key, "bgn_de": b, "end_de": e,
            "page_no": page, "page_count": 100}, quota_key=f"dart:{key[:8]}",
            fast=(page > 1))
        js = r.json()
        st = js.get("status")
        if st == "020":
            self.quota.mark_exhausted(f"dart:{key[:8]}", "status 020(한도초과)")
            raise QuotaExhausted("dart key exhausted")
        if st == "013":
            return [], 0
        if st != "000":
            raise IOError(f"DART status={st} {str(js.get('message'))[:60]}")
        return js.get("list", []), int(js.get("total_page", 1))

    def monthly_disclosures(self, ym, cmap):
        rel = f"dart/{ym}.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None:
            return df
        if not self.available() or not cmap:
            return None
        p = pd.Period(ym, freq="M")
        b = p.to_timestamp(how="start").strftime("%Y%m%d")
        e = p.to_timestamp(how="end").strftime("%Y%m%d")
        try:
            first, total_page = self._page(b, e, 1)
        except QuotaExhausted:
            raise
        except Exception as ex:
            self.log.warn(f"DART {ym} 1페이지 실패: {str(ex)[:90]}")
            return None
        items = list(first)
        if total_page > 1:
            pages = list(range(2, min(total_page, 400) + 1))
            with ThreadPoolExecutor(max_workers=CFG.MAX_WORKERS) as ex_:
                futs = {ex_.submit(self._page, b, e, pg): pg for pg in pages}
                for fut in as_completed(futs):
                    try:
                        lst, _ = fut.result()
                        items += lst
                    except QuotaExhausted:
                        for f2 in futs:
                            f2.cancel()
                        break
                    except Exception:
                        pass
        if not items:
            return None
        raw = pd.DataFrame([{"corp_code": it.get("corp_code"),
                             "report_nm": it.get("report_nm", "")} for it in items])
        raw["ticker"] = raw["corp_code"].map(cmap)
        raw = raw[raw["ticker"].notna()]
        if not len(raw):
            return None
        raw["is_earn"] = raw["report_nm"].str.contains(self._EARN_RE).astype("int8")
        g = raw.groupby("ticker", as_index=False).agg(
            n_disc=("report_nm", "size"), earnings_flag=("is_earn", "max"))
        g["ym"] = ym
        self.store.save_df(g, "parsed", rel, scope="common",
                           desc=f"DART 월별 공시집계 {ym} ({len(g)}종목)", stage="ST05")
        return g


# ──────────────────────────────────────────────────────────────────────────────
# KIND — 상장폐지 이력(생존편향 교차검증용 독립 소스)
# ──────────────────────────────────────────────────────────────────────────────
class KindCollector:
    URL = "https://kind.krx.co.kr/investwarn/delistingcompany.do"

    def __init__(self, store, log, quota, blocked=False):
        self.store, self.log = store, log
        self.http = HttpClient("kind", store.local_root / "state", log, quota,
                               blocked=blocked)

    def delisted(self, start_ym, end_ym):
        rel = "kind/delisted.parquet"
        df = self.store.load_df("parsed", rel, stage="ST05")
        if df is not None and len(df):
            return df
        d0 = pd.Period(start_ym, freq="M").to_timestamp(how="start").strftime("%Y%m%d")
        d1 = pd.Period(end_ym, freq="M").to_timestamp(how="end").strftime("%Y%m%d")
        rows = []
        try:
            r = self.http.get(self.URL, method="POST", data={
                "method": "searchDelistingCompany", "currentPageSize": "3000",
                "pageIndex": "1", "forward": "delistingcompany_down",
                "fromDate": d0, "toDate": d1, "marketType": "",
                "searchCorpName": ""}, fast=True)
            soup = _soup(r.text)
            for tr in soup.find_all("tr"):
                tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(tds) < 3:
                    continue
                code = next((re.sub(r"\D", "", t) for t in tds
                             if re.fullmatch(r"\d{6}", re.sub(r"\D", "", t))), None)
                dt = next((t for t in tds
                           if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
                if code and dt:
                    rows.append({"ticker": code,
                                 "delist_date": dt.replace(".", "-").replace("/", "-")})
        except Exception as e:
            self.log.info(f"[S06] KIND 상장폐지 조회 미확보({str(e)[:70]}) — "
                          "스냅샷 소멸 기반 추론으로 대체(계약 §1-3 충족)")
            return None
        if not rows:
            return None
        out = pd.DataFrame(rows).drop_duplicates("ticker")
        self.store.save_df(out, "parsed", rel, scope="common",
                           desc=f"KIND 상장폐지 이력 {len(out)}건", stage="ST05")
        self.log.info(f"[S06] KIND 상장폐지 {len(out)}건 확보(생존편향 교차검증)")
        return out


# ──────────────────────────────────────────────────────────────────────────────
# 컨센서스 EPS (H5) — 레거시 캐시 재활용 우선, 없으면 당월 스냅샷 전향 축적
# ──────────────────────────────────────────────────────────────────────────────
class ConsensusEPSCollector:
    def __init__(self, store, log, quota):
        self.store, self.log = store, log
        self.http = HttpClient("fnguide", store.local_root / "state", log, quota)

    def load_history(self):
        df = self.store.load_df("parsed", "consensus/eps_monthly.parquet", stage="ST05")
        if df is not None and len(df):
            return df
        for kws in (["consensus", "eps"], ["컨센서스"], ["estimate", "eps"]):
            legacy = self.store.find_legacy_df(kws, ["ticker"])
            if legacy is None:
                continue
            cols = {str(c).lower(): c for c in legacy.columns}
            eps_c = next((cols[c] for c in cols if "eps" in c), None)
            ym_c = next((cols[c] for c in cols
                         if c in ("ym", "month", "yearmonth", "연월")), None)
            tk_c = cols.get("ticker")
            if eps_c and ym_c and tk_c:
                out = legacy.rename(columns={eps_c: "eps_fy1", ym_c: "ym"})
                out["ticker"] = out[tk_c].astype(str).str.zfill(6)
                out = out[["ticker", "ym", "eps_fy1"]].dropna()
                self.store.save_df(out, "parsed", "consensus/eps_monthly.parquet",
                                   scope="common", desc="컨센서스EPS(레거시 재활용)",
                                   stage="ST05")
                self.log.info(f"[S06] 컨센서스 EPS 레거시 캐시 재활용 {len(out)}행")
                return out
        return None

    def snapshot_current(self, tickers, max_n=400):
        ym = datetime.now().strftime("%Y-%m")
        rel = f"consensus/snapshot_{ym}.parquet"
        if self.store.load_df("parsed", rel, stage="ST05") is not None:
            return
        items = list(tickers)[:max_n]
        Progress.begin("컨센서스 EPS 당월 스냅샷", total=len(items))
        rows = []
        def _work(t):
            r = self.http.get("https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp",
                              params={"pGB": "1", "gicode": "A" + t}, fast=True)
            m = re.search(r"EPS.{0,400}?([\-0-9,]{2,12})\s*<", r.text, re.S)
            if m:
                return {"ticker": t, "ym": ym,
                        "eps_fy1": float(m.group(1).replace(",", ""))}
            return None
        with ThreadPoolExecutor(max_workers=CFG.MAX_WORKERS) as ex:
            futs = [ex.submit(_work, t) for t in items]
            for fut in as_completed(futs):
                try:
                    v = fut.result()
                    if v:
                        rows.append(v)
                except Exception:
                    pass
                Progress.tick()
                if COLLECT_BUDGET.exceeded():
                    break
        if rows:
            df = pd.DataFrame(rows)
            self.store.save_df(df, "parsed", rel, scope="common",
                               desc=f"컨센서스EPS 당월 스냅샷 {ym}", stage="ST05")
            hist = self.store.load_df("parsed", "consensus/eps_monthly.parquet",
                                      stage="ST05")
            allv = pd.concat([hist, df], ignore_index=True) if hist is not None else df
            allv = allv.drop_duplicates(["ticker", "ym"], keep="last")
            self.store.save_df(allv, "parsed", "consensus/eps_monthly.parquet",
                               scope="common", desc="컨센서스EPS 월별 누적", stage="ST05")

# ══════════════════════════════════════════════════════════════════════════════
# [S07] PIT 유니버스 (월말 스냅샷, 생존편향 제거 — 상장폐지 종목 포함)
# ══════════════════════════════════════════════════════════════════════════════

_NAME_EXCL_RE = re.compile(r"스팩|SPAC|제\s*\d+\s*호|ETN|ETF|리츠|REIT|"
                           r"인프라|우선주|\d*우(B|C)?$|채권|선물|레버리지|인버스", re.I)

def _is_common_stock(ticker, name=""):
    """보통주 판별: 6자리 & 끝자리 '0'. 이름이 있으면 스팩/ETF/리츠 등 추가 배제."""
    t = str(ticker)
    if not re.match(r"^\d{6}$", t) or not t.endswith("0"):
        return False
    if name and _NAME_EXCL_RE.search(str(name)):
        return False
    return True


def build_pit_universe(hub, store, log, months):
    """월별 PIT 유니버스 패널. 스냅샷에 존재 = 당시 상장(상폐 종목 자동 포함).
    ※ 계약 §2.6: pykrx 지수 PDF 호출 금지 → 시총 순위 프록시로 지수 이벤트 산출."""
    cached = store.load_df("features", "universe_panel.parquet", stage="ST02")
    if cached is not None and cached["ym"].nunique() >= len(months) - 1:
        log.info(f"[S07] 유니버스 패널 캐시 적중 ({cached['ym'].nunique()}개월)")
        return cached
    Progress.begin("월말 PIT 스냅샷", total=len(months))
    frames = []
    for ym in months:
        if COLLECT_BUDGET.exceeded():
            log.warn(f"[S07] 타임박스 — 스냅샷 {ym} 이후 중단(수집분 사용)")
            break
        snap = hub.monthly_snapshot(ym)
        Progress.tick(extra=f"{ym}")
        if snap is None or not len(snap):
            continue
        s = snap.copy()
        s["ticker"] = s["ticker"].astype(str).str.zfill(6)
        if "name" not in s.columns:
            s["name"] = ""
        keep = [_is_common_stock(t, n) for t, n in zip(s["ticker"], s["name"])]
        s = s[pd.Series(keep, index=s.index)
              & (pd.to_numeric(s["mcap"], errors="coerce") > 0)].copy()
        if not len(s):
            continue
        s["ym"] = ym
        s["mcap"] = pd.to_numeric(s["mcap"], errors="coerce")
        s["close"] = pd.to_numeric(s["close"], errors="coerce")
        s["mcap_rank"] = s["mcap"].rank(ascending=False, method="first")
        s["market"] = s["market"].astype(str).str.upper().str.replace(" ", "")
        s.loc[~s["market"].isin(["KOSPI", "KOSDAQ"]), "market"] = "KOSPI"
        s["kospi_rank"] = s.loc[s["market"] == "KOSPI", "mcap"] \
            .rank(ascending=False, method="first")
        s["kosdaq_rank"] = s.loc[s["market"] == "KOSDAQ", "mcap"] \
            .rank(ascending=False, method="first")
        s["in_k200p"] = ((s["market"] == "KOSPI") & (s["kospi_rank"] <= 200)).astype("int8")
        s["in_kq150p"] = ((s["market"] == "KOSDAQ") & (s["kosdaq_rank"] <= 150)).astype("int8")
        frames.append(s[["ym", "ticker", "market", "close", "mcap", "mcap_rank",
                         "in_k200p", "in_kq150p"]])
    if not frames:
        return None
    uni = pd.concat(frames, ignore_index=True)
    store.save_df(uni, "features", "universe_panel.parquet", scope="common",
                  desc="PIT 월별 유니버스 패널(상폐 포함)", stage="ST02")
    return uni


def delist_events_from_universe(uni, months, kind_df=None, log=None):
    """스냅샷 소멸 = 상장폐지 추론. KIND 이력이 있으면 교차검증 결과를 로그로 남긴다."""
    last = uni.groupby("ticker")["ym"].max().reset_index()
    last.columns = ["ticker", "last_ym"]
    present = set(uni["ym"].unique())
    final_ym = max(m for m in months if m in present)
    ev = last[last["last_ym"] < final_ym].copy()
    ev["delist_after"] = ev["last_ym"]
    if kind_df is not None and len(kind_df) and log is not None:
        k = set(kind_df["ticker"].astype(str).str.zfill(6))
        inferred = set(ev["ticker"])
        log.kv("상장폐지 교차검증(스냅샷 추론 vs KIND)", {
            "스냅샷 추론": len(inferred), "KIND 이력": len(k),
            "양측 일치": len(inferred & k),
            "KIND 만 존재(스냅샷 누락)": len(k - inferred),
            "추론만 존재(장기거래정지 등 포함)": len(inferred - k)})
    return ev


# ══════════════════════════════════════════════════════════════════════════════
# [S06b] 리포트 수집 오케스트레이션
#   전략: 한경(확장 가능, 작성자 포함)을 주력으로 전 기간 수집.
#         네이버 리스트는 항상 병행(증권사 100% 확보 → 하우스 단위 폴백 보장).
#         네이버 상세는 '전역 예산' 안에서 한경이 못 채운 부분만 보조.
# ══════════════════════════════════════════════════════════════════════════════

def collect_reports_month(ym, naver, hk, store, log):
    """월 단위 리스트 수집(싸다). 상세 추출은 여기서 하지 않는다."""
    if hk is not None:
        hk_df = hk.collect_month(ym)
    else:
        hk_df = store.load_df("parsed", f"reports_meta/hankyung/{ym}.parquet",
                              stage="ST04")
    if naver is not None:
        nv_df = naver.collect_month(ym)
    else:
        nv_df = store.load_df("parsed", f"reports_meta/naver/{ym}.parquet", stage="ST04")
    return (nv_df if nv_df is not None else pd.DataFrame(),
            hk_df if hk_df is not None else pd.DataFrame())


def collect_all_reports(months, naver, hk, store, log):
    """전 기간 리스트 수집.
    월끼리는 완전히 독립이므로 여러 월을 동시에 진행한다. 소스별 AdaptiveLimiter 가
    여전히 요청 간격을 강제하므로 서버에 가해지는 부하는 직렬일 때와 같고, 대기
    시간(왕복 지연)만 겹쳐 사라진다 — 이 단계가 전체 수집의 최대 병목이었다."""
    Progress.begin("리포트 리스트 수집(월별)", total=len(months))
    n_hk = n_nv = 0
    lock = threading.Lock()
    workers = max(1, min(CFG.MAX_WORKERS - 1, 3))

    def _one(ym):
        nonlocal n_hk, n_nv
        if COLLECT_BUDGET.exceeded():
            raise BudgetExceeded("타임박스")
        nv, hkd = collect_reports_month(ym, naver, hk, store, log)
        with lock:
            n_nv += len(nv) if nv is not None else 0
            n_hk += len(hkd) if hkd is not None else 0
            Progress.tick(extra=f"{ym} | 한경 {n_hk} / 네이버 {n_nv}")
        return ym

    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, ym): ym for ym in months}
        for fut in as_completed(futs):
            try:
                fut.result()
            except (BudgetExceeded, SourceDown, QuotaExhausted) as e:
                if not stopped:
                    log.warn(f"[S06b] 수집 조기 종료({str(e)[:60]}) — "
                             "캐시분으로 INTERIM 진행")
                    stopped = True
                for f2 in futs:
                    f2.cancel()
            except Exception as e:
                log.warn(f"[S06b] {futs[fut]} 실패: {str(e)[:100]}")
    log.kv("리포트 리스트 수집 결과", {
        "한경(작성자 포함)": n_hk, "네이버(증권사)": n_nv,
        "한경 사용가능": (hk.available() if hk is not None else False),
        "동시 처리 월": workers})
    return n_hk, n_nv


def enrich_missing_analysts(months, naver, store, log, budget_total=None):
    """한경이 채우지 못한 월에 대해 네이버 상세로 작성자를 보조 확보한다.
    전역 예산을 개월 수로 균등 배분해 특정 구간만 채워지는 편향을 막는다."""
    if naver is None or CFG.RUN_MODE != "FULL":
        return
    left = budget_total if budget_total is not None else naver.detail_budget.left()
    if left <= 0:
        return
    targets = []
    for ym in months:
        nv = store.load_df("parsed", f"reports_meta/naver/{ym}.parquet", stage="ST04")
        if nv is None or not len(nv):
            continue
        hk = store.load_df("parsed", f"reports_meta/hankyung/{ym}.parquet", stage="ST04")
        hk_ok = 0
        if hk is not None and len(hk) and "analyst_raw" in hk.columns:
            hk_ok = int((hk["analyst_raw"].astype(str).str.len() > 0).sum())
        if hk_ok >= len(nv) * 0.7:            # 한경이 이미 충분히 채움 → 생략
            continue
        targets.append(ym)
    if not targets:
        log.info("[S06b] 한경으로 작성자 확보 충분 — 네이버 상세 보조 불필요")
        return
    per = max(5, left // len(targets))
    log.info(f"[S06b] 네이버 상세 보조: {len(targets)}개월 × 약 {per}건 "
             f"(전역 예산 {left}건)")
    for ym in targets:
        if COLLECT_BUDGET.exceeded() or naver.detail_budget.left() <= 0:
            break
        rel = f"reports_meta/naver/{ym}.parquet"
        nv = store.load_df("parsed", rel, stage="ST04")
        if nv is None or not len(nv):
            continue
        upd, tried = naver.enrich_analysts(nv, per, tag=f" {ym}")
        if tried:
            store.save_df(upd, "parsed", rel, scope="common",
                          desc=f"네이버 리서치(작성자 보강) {ym}", stage="ST04")


def merge_report_meta(months, store, log):
    """월별 캐시(한경+네이버)를 통합 → 리포트/애널리스트 단위 테이블.
    dedup 키 = (pub_date, ticker, broker_norm, 제목두부), 작성자 보유 행 우선."""
    frames = []
    for ym in months:
        for src in ("hankyung", "naver"):
            df = store.load_df("parsed", f"reports_meta/{src}/{ym}.parquet", stage="ST06")
            if df is None or not len(df):
                continue
            if not {"pub_date", "ticker", "broker", "title"} <= set(df.columns):
                continue
            d = df.copy()
            if "analyst_raw" not in d.columns:
                d["analyst_raw"] = ""
            d["source"], d["ym"] = src, ym
            frames.append(d[["pub_date", "ym", "ticker", "broker",
                             "analyst_raw", "title", "source"]])
    if not frames:
        return None, None
    allr = pd.concat(frames, ignore_index=True)
    allr["ticker"] = allr["ticker"].astype(str).str.zfill(6)
    allr["pub_date"] = allr["pub_date"].astype(str).str[:10]
    allr["broker_norm"] = allr["broker"].map(norm_broker)
    allr["title_head"] = (allr["title"].astype(str).str.lower()
                          .str.replace(r"\s+", "", regex=True).str[:18])
    allr["has_analyst"] = (allr["analyst_raw"].astype(str).str.len() > 0).astype("int8")
    allr = allr.sort_values(["has_analyst", "source"], ascending=[False, True])
    allr = allr.drop_duplicates(subset=["pub_date", "ticker", "broker_norm",
                                        "title_head"], keep="first")
    allr["analysts"] = allr["analyst_raw"].map(norm_analysts)
    allr["n_authors"] = allr["analysts"].map(len).astype("int8")
    ex = allr[allr["n_authors"] > 0][
        ["pub_date", "ym", "ticker", "broker_norm", "analysts", "source"]].explode("analysts")
    ex = ex.rename(columns={"analysts": "analyst_person_id"})
    ex["analyst_id"] = ex["analyst_person_id"] + "@" + ex["broker_norm"]
    log.kv("리포트 메타 통합", {
        "총 리포트(중복제거)": len(allr),
        "작성자 식별": int(allr["has_analyst"].sum()),
        "식별률": f"{allr['has_analyst'].mean()*100:.1f}%",
        "애널리스트-행": len(ex),
        "고유 애널리스트(analyst_id)": ex["analyst_id"].nunique() if len(ex) else 0,
        "고유 인물(person_id)": ex["analyst_person_id"].nunique() if len(ex) else 0,
        "고유 증권사": allr["broker_norm"].nunique(),
        "커버 개월": allr["ym"].nunique()})
    return allr.drop(columns=["title_head"]), ex


# ══════════════════════════════════════════════════════════════════════════════
# [S08] Phase 0 데이터 실현가능성 게이트 (계약 §3)
#   재작성 포인트: 확보율 '측정'이 목적이므로 비싼 경로를 최소로 쓴다.
#   (이전 버전은 여기서 월당 250 상세 + 120 PDF 를 돌려 20~45분간 침묵했다)
# ══════════════════════════════════════════════════════════════════════════════

class Phase0Gate:
    def __init__(self, store, log, out_dir):
        self.store, self.log = store, log
        self.out_dir = Path(out_dir)
        self.decision_path = store.local_root / "state" / "phase0_decision.json"

    def prior_decision(self):
        return read_json_safe(self.decision_path)

    def run(self, naver, hk, kofia, canary_result):
        t0 = time.time()
        prior = self.prior_decision()
        if prior and prior.get("mode"):
            self.log.info(f"[S08] Phase 0 기결정 재사용: {prior['mode']} "
                          f"(확보율 {prior.get('rate')}) — 재측정하려면 "
                          "state/phase0_decision.json 삭제")
            return prior
        hk_ok = hk.available() if hk is not None else False
        self.log.info(f"[S08] 주력 경로(한경 컨센서스) 사용가능: {hk_ok}")
        stats = []
        for ym in CFG.PHASE0_SAMPLE_MONTHS:
            if COLLECT_BUDGET.exceeded():
                break
            nv_df, hk_df = collect_reports_month(ym, naver, hk, self.store, self.log)
            n_hk = len(hk_df) if hk_df is not None else 0
            n_nv = len(nv_df) if nv_df is not None else 0
            rows = []
            if n_hk:
                d = hk_df.copy()
                if "analyst_raw" not in d.columns:
                    d["analyst_raw"] = ""
                d["ok"] = d["analyst_raw"].map(lambda x: len(norm_analysts(x)) > 0)
                rows.append(d[["pub_date", "ticker", "ok"]])
            if n_nv and not hk_ok:
                # 한경이 없을 때만 네이버 상세를 '소량' 표본 추출해 확보율을 측정
                samp = nv_df.sample(n=min(len(nv_df), CFG.PHASE0_DETAIL_PER_MONTH),
                                    random_state=CFG.RANDOM_SEED).copy()
                samp, _ = naver.enrich_analysts(samp, CFG.PHASE0_DETAIL_PER_MONTH,
                                                tag=f" Phase0 {ym}") \
                    if naver is not None else (samp, 0)
                samp["ok"] = samp["analyst_raw"].map(
                    lambda x: len(norm_analysts(x)) > 0)
                rows.append(samp[["pub_date", "ticker", "ok"]])
            if not rows:
                stats.append({"ym": ym, "n": 0, "rate": np.nan,
                              "n_hk": n_hk, "n_nv": n_nv})
                continue
            merged = pd.concat(rows, ignore_index=True)
            merged = merged.sort_values("ok", ascending=False).drop_duplicates(
                subset=["pub_date", "ticker"], keep="first")
            # 정렬된 상태에서 head 를 뽑으면 확보율이 100% 로 왜곡된다 → 무작위 표본
            samp = merged.sample(n=min(len(merged), CFG.PHASE0_SAMPLE_SIZE),
                                 random_state=CFG.RANDOM_SEED)
            stats.append({"ym": ym, "n": int(len(samp)),
                          "rate": float(samp["ok"].mean()) if len(samp) else np.nan,
                          "n_hk": n_hk, "n_nv": n_nv})
            self.log.info(f"[S08] {ym}: 표본 {len(samp)}건, 확보율 "
                          f"{(samp['ok'].mean()*100 if len(samp) else 0):.1f}% "
                          f"(한경 {n_hk} / 네이버 {n_nv})")
        valid = [s for s in stats if s["n"] > 0]
        rate = float(np.mean([s["rate"] for s in valid])) if valid else 0.0
        kofia_ok = kofia.try_fetch_registry() is not None
        if not valid:
            mode = "ABORT"
        elif rate >= CFG.PHASE0_OK_RATE and hk_ok:
            mode = "ANALYST"
        elif rate >= CFG.PHASE0_FALLBACK_RATE:
            mode = "ANALYST_IPW"
        else:
            mode = "HOUSE_FALLBACK"
        decision = {"mode": mode, "rate": round(rate, 4), "stats": stats,
                    "hankyung_available": hk_ok, "kofia_available": kofia_ok,
                    "elapsed_min": round((time.time() - t0) / 60, 1),
                    "at": datetime.now().isoformat()}
        try:
            atomic_write_json(self.decision_path, decision)
        except Exception:
            pass
        self._write_report(decision, canary_result)
        return decision

    def _write_report(self, dec, canary_result):
        L = ["# PHASE0_DATA_FEASIBILITY.md", "",
             f"- 실행시각: {dec['at']} (타임박스 {CFG.PHASE0_TIMEBOX_HOURS}h, "
             f"소요 {dec['elapsed_min']}분)",
             f"- **판정 모드: `{dec['mode']}`** (평균 analyst_id 확보율 "
             f"{dec['rate']*100:.1f}%)",
             f"- 주력 경로(한경 컨센서스, 1요청=최대 80건+작성자) 사용가능: "
             f"**{dec['hankyung_available']}**", "",
             "| 표본월 | 표본 n | 확보율 | 한경 건수 | 네이버 건수 |", "|---|---|---|---|---|"]
        for s in dec["stats"]:
            r = s["rate"]
            L.append(f"| {s['ym']} | {s['n']} | "
                     f"{(r*100 if r == r else 0):.1f}% | {s.get('n_hk',0)} | "
                     f"{s.get('n_nv',0)} |")
        L += ["",
              f"- 판정 기준: ≥{CFG.PHASE0_OK_RATE*100:.0f}% 정상 / "
              f"{CFG.PHASE0_FALLBACK_RATE*100:.0f}~{CFG.PHASE0_OK_RATE*100:.0f}% "
              "진행+IPW 민감도(§6.7) / 미만 → broker×sector 폴백",
              f"- 금투협 전문인력 조회: "
              f"{'가능' if dec['kofia_available'] else '불가 → 재직 프록시(계약 §3 폴백)'}",
              f"- 소스 도달성: {canary_result}", "",
              "### 수집 경로 설계 근거",
              "요청당 산출량이 경로 선택을 지배한다. 한경 리스트는 1요청에 최대 80건과 "
              "작성자를 함께 주므로 157개월을 약 4,700요청으로 완주할 수 있다. 반면 "
              "네이버 상세 페이지는 1요청당 1건이라 전 기간을 채우려면 31만 요청이 "
              "필요해 어떤 시간 예산으로도 불가능하다. 따라서 상세 경로는 전역 예산"
              f"({CFG.BUDGET_NAVER_DETAIL}건)으로 묶어 보조로만 쓴다."]
        if dec["mode"] == "HOUSE_FALLBACK":
            L += ["", "> **⚠ 폴백 선언: 애널리스트 단위 확보 실패로 신호 단위를 "
                  "`broker_id × sector`(하우스 단위 주의 재배분)로 격하한다. "
                  "이하 모든 산출물은 애널리스트 단위 결과가 아니다.**"]
        if dec["mode"] == "ABORT":
            L += ["", "> **✖ 리포트 메타 확보 실패 — 계약 §3 에 따라 보고 후 중단.**"]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "PHASE0_DATA_FEASIBILITY.md").write_text(
            "\n".join(L) + "\n", encoding="utf-8")
        self.log.info("[S08] PHASE0_DATA_FEASIBILITY.md 작성 완료(최우선 제출물)")

# ══════════════════════════════════════════════════════════════════════════════
# [S09] 주의 배분 패널 — N, share, base, EA (계약 §6.1~6.2)
#   구현 전략: (analyst, ticker) 쌍별 '조밀 월 그리드'를 numpy 로 벡터화 생성 후
#   그룹 누적합 shift 로 12개월 롤링을 O(n) 계산 (apply/loop 금지 — 속도 최적화)
# ══════════════════════════════════════════════════════════════════════════════

def _dense_group_grid(keys_df, key_cols, m0_col, m1_col):
    """각 그룹의 [m0..m1] 조밀 월 그리드 생성. 반환: DataFrame(key_cols..., m)"""
    m0 = keys_df[m0_col].to_numpy(dtype=np.int64)
    m1 = keys_df[m1_col].to_numpy(dtype=np.int64)
    lens = (m1 - m0 + 1).clip(min=0)
    total = int(lens.sum())
    m_flat = np.empty(total, dtype=np.int64)
    pos = 0
    for a, b, L in zip(m0, m1, lens):                 # 그룹 수 만큼만 파이썬 루프
        if L > 0:
            m_flat[pos:pos + L] = np.arange(a, b + 1)
            pos += L
    out = {c: np.repeat(keys_df[c].to_numpy(), lens) for c in key_cols}
    out["m"] = m_flat
    return pd.DataFrame(out)


def build_attention_panel(ex, log, house_fallback=False, sector_map=None):
    """ex: 애널리스트 단위 리포트 행 (analyst_id, analyst_person_id, broker_norm,
    ticker, ym). 반환: (panel, aw, pair_dense, adense)
      panel      : (aid, ticker, m, ym, c, N, share, base, EA) — EA 계산 완료 행
      aw         : 애널리스트-월 가중치 (npub, breadth)  [H2 ω용]
      pair_dense : 철회 분류용 조밀 쌍 그리드(c, cumc)
      adense     : 애널리스트-월 조밀 그리드(N, cumN)"""
    ex = ex.copy()
    if house_fallback:
        smap = sector_map or {}
        ex["analyst_id"] = ex["broker_norm"] + "#" + \
            ex["ticker"].map(lambda t: smap.get(t, "UNK"))
        ex["analyst_person_id"] = ex["analyst_id"]
    ex["m"] = ex["ym"].map(month_ord).astype(np.int64)

    cnt = (ex.groupby(["analyst_id", "ticker", "m"], as_index=False)
             .size().rename(columns={"size": "c"}))
    nam = (ex.groupby(["analyst_id", "m"], as_index=False)
             .size().rename(columns={"size": "N"}))

    # ── 애널리스트-월 조밀 그리드 + 누적 N ─────────────────────────────────
    # ※ m1 을 침묵확인 기간(3개월)만큼 패딩: 퇴사/전면중단 후의 '무발간 월'이
    #   그리드에 존재해야 M-EXIT 침묵이 관측된다(§6.5 인과분해의 전제).
    #   데이터 종료 경계의 가짜 침묵은 classify 의 last_data_m 가드가 차단.
    spans = nam.groupby("analyst_id", as_index=False).agg(m0=("m", "min"),
                                                          m1=("m", "max"))
    spans["m1"] = spans["m1"] + CFG.EXIT_SILENT_MONTHS
    adense = _dense_group_grid(spans, ["analyst_id"], "m0", "m1")
    adense = adense.merge(nam, on=["analyst_id", "m"], how="left")
    adense["N"] = adense["N"].fillna(0).astype(np.int32)
    g = adense.groupby("analyst_id")["N"]
    adense["cumN"] = g.cumsum()
    gc = adense.groupby("analyst_id")["cumN"]
    adense["sumN12"] = (gc.shift(1, fill_value=0)
                        - gc.shift(13, fill_value=0)).astype(np.int32)
    adense["months_active"] = (adense["N"] >= CFG.N_MIN_REPORTS).astype(np.int8)
    adense["n_hist"] = adense.groupby("analyst_id")["months_active"].cumsum()

    # ── (a,i) 쌍 조밀 그리드 + 누적 c ─────────────────────────────────────
    pf = cnt.groupby(["analyst_id", "ticker"], as_index=False).agg(pm0=("m", "min"))
    pf = pf.merge(spans[["analyst_id", "m1"]], on="analyst_id", how="left")
    pair_dense = _dense_group_grid(pf, ["analyst_id", "ticker"], "pm0", "m1")
    pair_dense = pair_dense.merge(cnt, on=["analyst_id", "ticker", "m"], how="left")
    pair_dense["c"] = pair_dense["c"].fillna(0).astype(np.int32)
    gp = pair_dense.groupby(["analyst_id", "ticker"], sort=False)["c"]
    pair_dense["cumc"] = gp.cumsum()
    gpc = pair_dense.groupby(["analyst_id", "ticker"], sort=False)["cumc"]
    pair_dense["sumc12"] = (gpc.shift(1, fill_value=0)
                            - gpc.shift(13, fill_value=0)).astype(np.int32)

    # ── share / base / EA ─────────────────────────────────────────────────
    panel = pair_dense.merge(adense[["analyst_id", "m", "N", "sumN12", "n_hist"]],
                             on=["analyst_id", "m"], how="left")
    panel = panel[(panel["sumc12"] > 0) | (panel["c"] > 0)].copy()  # 활성 쌍만
    valid = (panel["N"] >= CFG.N_MIN_REPORTS) & (panel["sumN12"] >= CFG.BASE_MIN_N)
    panel["share"] = np.where(panel["N"] > 0, panel["c"] / panel["N"], np.nan)
    panel["base"] = np.where(panel["sumN12"] > 0,
                             panel["sumc12"] / panel["sumN12"], np.nan)
    panel["EA"] = np.where(valid, panel["share"] - panel["base"], np.nan)
    panel["new_cov"] = ((panel["sumc12"] == 0) & (panel["c"] > 0)).astype("int8")
    panel["ym"] = panel["m"].map(ord_to_ym)
    panel = panel.astype({"c": "int32", "N": "int32"})

    # ── ω 가중치: 발간량 / 커버리지폭(직전 12M 활성 쌍 수) ─────────────────
    breadth = (panel[panel["sumc12"] > 0].groupby(["analyst_id", "m"], as_index=False)
               .size().rename(columns={"size": "breadth"}))
    aw = adense[["analyst_id", "m", "N"]].rename(columns={"N": "npub"})
    aw = aw.merge(breadth, on=["analyst_id", "m"], how="left")
    aw["breadth"] = aw["breadth"].fillna(0).astype(np.int32)

    log.kv("주의 패널 구성", {
        "패널 행(활성 쌍-월)": len(panel),
        "EA 유효 행": int(panel["EA"].notna().sum()),
        "애널리스트 수": panel["analyst_id"].nunique(),
        "종목 수": panel["ticker"].nunique(),
        "N<3 결측 처리율": f"{(~valid).mean()*100:.1f}%"})
    return panel, aw, pair_dense, adense


# ══════════════════════════════════════════════════════════════════════════════
# [S09b] 경험적 베이즈 축소추정 (계약 §6.2 필수 — 애널리스트 → 증권사 → 섹터)
# ══════════════════════════════════════════════════════════════════════════════

def apply_shrinkage(panel, sector_of, log):
    """EA_sh = w·EA + (1-w)·prior_broker,  w = n_hist/(n_hist+K1)
       prior_broker = (n_b·mean_broker + K2·mean_sector)/(n_b+K2)
    모든 평균은 '해당 월 횡단면'만 사용(동시점 정보 → look-ahead 없음).
    K1/K2 는 사전 고정값(튜닝 금지)."""
    df = panel.copy()
    df["broker"] = df["analyst_id"].str.split("@").str[-1]
    hf = df["analyst_id"].str.contains("#", regex=False)
    df.loc[hf, "broker"] = df.loc[hf, "analyst_id"].str.split("#").str[0]
    df["sector"] = df["ticker"].map(lambda t: sector_of.get(t, "UNK"))

    v = df["EA"].notna()
    sub = df[v]
    bm = sub.groupby(["m", "broker"])["EA"].transform("mean")
    bn = sub.groupby(["m", "broker"])["EA"].transform("count")
    sm = sub.groupby(["m", "sector"])["EA"].transform("mean")
    prior_b = (bn * bm + CFG.SHRINK_K_BROKER * sm) / (bn + CFG.SHRINK_K_BROKER)
    w = sub["n_hist"].clip(lower=0) / (sub["n_hist"].clip(lower=0) + CFG.SHRINK_K_ANALYST)
    df.loc[v, "EA_sh"] = w * sub["EA"] + (1 - w) * prior_b
    if "EA_sh" not in df.columns:
        df["EA_sh"] = np.nan

    diag = {
        "비축소 EA 분산": float(np.nanvar(df["EA"])),
        "축소 EA_sh 분산": float(np.nanvar(df["EA_sh"])),
        "분산 축소율": f"{(1 - np.nanvar(df['EA_sh'])/max(np.nanvar(df['EA']), 1e-12))*100:.1f}%",
        "K1(애널리스트)": CFG.SHRINK_K_ANALYST, "K2(증권사)": CFG.SHRINK_K_BROKER}
    log.kv("축소추정 진단(§6.2)", diag)
    return df, diag


# ══════════════════════════════════════════════════════════════════════════════
# [S10] 기계적 발간 통제회귀 → VAS (계약 §6.3 — 건너뛰면 전체 무효)
#   FE(섹터×월, 애널리스트)는 교차 사영(alternating demeaning)으로 제거하고
#   잔여 공변량에 OLS → 잔차 = VAS.
#   look-ahead 차단: 월 t 의 VAS 는 [시작..t] 확장 윈도우 표본으로만 추정한다.
# ══════════════════════════════════════════════════════════════════════════════

_CTRL_COLS = ["earn_flag", "log_disc", "new_cov", "idx_evt"]

def _demean_two_fe(mat, fe1, fe2, iters=6):
    """mat(n×k) 를 fe1/fe2 그룹평균으로 교차 소거 (Frisch-Waugh)."""
    d = pd.DataFrame(mat)
    for _ in range(iters):
        d = d - d.groupby(fe1).transform("mean")
        d = d - d.groupby(fe2).transform("mean")
    return d.to_numpy()

def _ols_resid(y, X):
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        beta = np.zeros(X.shape[1])
    return y - X @ beta, beta

def compute_vas(panel_sh, ticker_month_ctrl, log, recursive=None):
    """panel_sh: EA_sh 포함 패널. ticker_month_ctrl: (ticker, ym) 단위 통제변수
    [earn_flag, n_disc, idx_evt]. 반환: VAS 열 추가된 패널 + 회귀 진단."""
    recursive = CFG.RECURSIVE_CONTROLS if recursive is None else recursive
    df = panel_sh[panel_sh["EA_sh"].notna()].copy()
    df = df.merge(ticker_month_ctrl, on=["ticker", "ym"], how="left")
    for c in ("earn_flag", "idx_evt"):
        df[c] = df[c].fillna(0).astype("float32")
    df["log_disc"] = np.log1p(df["n_disc"].fillna(0)).astype("float32")
    df["new_cov"] = df["new_cov"].astype("float32")
    df["fe_sm"] = df["sector"].astype(str) + "|" + df["ym"].astype(str)
    df = df.sort_values("m").reset_index(drop=True)
    df["VAS"] = np.nan

    months = np.sort(df["m"].unique())
    betas = []
    if not recursive:
        y_res = _demean_two_fe(df[["EA_sh"] + _CTRL_COLS].to_numpy(dtype=np.float64),
                               df["fe_sm"], df["analyst_id"])
        resid, beta = _ols_resid(y_res[:, 0], y_res[:, 1:])
        df["VAS"] = resid
        betas.append(beta)
        log.warn("[S10] 통제회귀: 전표본(비재귀) 모드 — 참고용(계약상 재귀 권장)")
    else:
        m_start = months[0] + CFG.CTRL_MIN_WINDOW_M
        arr = df[["EA_sh"] + _CTRL_COLS].to_numpy(dtype=np.float64)
        mvals = df["m"].to_numpy()
        # 확장 윈도우 재귀추정은 O(T²) 이라 수 분이 걸린다 — 진행률을 방송한다
        Progress.begin("§6.3 통제회귀(확장윈도우 재귀추정)",
                       total=int((months >= m_start).sum()))
        for t in months:
            sel_t = mvals == t
            if t < m_start:
                # 초기 표본 부족 구간: 해당 월까지 전체로 1회 추정(보수적) — 진입 제외됨
                continue
            win = mvals <= t
            sub = arr[win]
            fe1 = df.loc[win, "fe_sm"]
            fe2 = df.loc[win, "analyst_id"]
            dm = _demean_two_fe(sub, fe1.reset_index(drop=True),
                                fe2.reset_index(drop=True))
            resid, beta = _ols_resid(dm[:, 0], dm[:, 1:])
            take = sel_t[win]
            df.loc[sel_t, "VAS"] = resid[take]
            betas.append(beta)
            Progress.tick(extra=ord_to_ym(t))
    bmat = np.vstack(betas) if betas else np.zeros((1, len(_CTRL_COLS)))
    coef = pd.DataFrame({"var": _CTRL_COLS, "beta_mean": bmat.mean(axis=0),
                         "beta_last": bmat[-1]})
    var_ea = float(np.nanvar(df["EA_sh"]))
    var_vas = float(np.nanvar(df["VAS"]))
    diag = {"관측치": int(df["VAS"].notna().sum()),
            "통제 설명 분산비율": f"{(1 - var_vas/max(var_ea, 1e-12))*100:.1f}%",
            "재귀추정": recursive,
            "계수(평균) " + "/".join(_CTRL_COLS):
                np.round(bmat.mean(axis=0), 4).tolist()}
    log.kv("§6.3 통제회귀 진단", diag)
    return df, coef, diag


# ══════════════════════════════════════════════════════════════════════════════
# [S11] 커버리지 철회 인과 분해 — M-EXIT / V-DROP / H-EXIT (계약 §6.5)
# ══════════════════════════════════════════════════════════════════════════════

def classify_coverage_exits(pair_dense, adense, reports_all, person_month,
                            kofia_df, log, last_data_m=None):
    """반환: (exit_events, aar_neg, cov_count)
      exit_events: analyst_id, person, broker, ticker, t_exit(ym), signal_ym, cls
      aar_neg   : (ticker, ym) AAR_neg  [signal_ym 기준 — 침묵 3개월 확인 후 공표]
      cov_count : (ticker, m) 직전 4분기 연속커버 애널리스트 수 (H4 저커버리지 조건부)"""
    pd_ = pair_dense.sort_values(["analyst_id", "ticker", "m"]).copy()
    gpc = pd_.groupby(["analyst_id", "ticker"], sort=False)["cumc"]
    q1 = gpc.shift(1, fill_value=0) - gpc.shift(4, fill_value=0)
    q2 = gpc.shift(4, fill_value=0) - gpc.shift(7, fill_value=0)
    q3 = gpc.shift(7, fill_value=0) - gpc.shift(10, fill_value=0)
    q4 = gpc.shift(10, fill_value=0) - gpc.shift(13, fill_value=0)
    pd_["cov4q"] = ((q1 > 0) & (q2 > 0) & (q3 > 0) & (q4 > 0)).to_numpy()
    # 침묵 확인 창 = EXIT_SILENT_MONTHS 개월 [t, t+W]. W = 창 길이 − 1.
    # 한국 애널리스트는 커버 종목에 대해 실적 시즌 중심의 '분기 리듬'으로 발간하므로
    # 3개월 침묵은 정상 발간 간격과 구분되지 않는다(= 이벤트의 대부분이 잡음).
    # 두 번의 실적 사이클을 건너뛴 6개월을 철회 확정 기준으로 삼는다.
    W = CFG.EXIT_SILENT_MONTHS - 1
    gc = pd_.groupby(["analyst_id", "ticker"], sort=False)["c"]
    silent = (pd_["c"] == 0)                 # 쌍 그리드 밖은 무발간으로 간주
    for k in range(1, CFG.EXIT_SILENT_MONTHS):
        silent &= (gc.shift(-k).fillna(0) == 0)
    ev = pd_[pd_["cov4q"] & silent].copy()
    # 동일 쌍의 '연속 침묵'은 최초 이벤트만 채택. 12개월 이상 재커버 후 재철회는
    # 별개 이벤트로 인정(무손실).
    ev = ev.sort_values(["analyst_id", "ticker", "m"])
    prev_m = ev.groupby(["analyst_id", "ticker"])["m"].shift(1)
    ev = ev[prev_m.isna() | (ev["m"] - prev_m > 12)]
    if last_data_m is not None:
        ev = ev[ev["m"] + W <= last_data_m]          # 확인 불가(미래) 이벤트 제거
    if not len(ev):
        log.warn("[S11] 철회 이벤트 0건")
        return (pd.DataFrame(columns=["analyst_id", "person", "broker", "ticker",
                                      "t_exit", "signal_ym", "cls"]),
                pd.DataFrame(columns=["ticker", "ym", "AAR_neg"]),
                pd.DataFrame(columns=["ticker", "m", "n_cov"]))

    # ── 분류 재료 (전부 딕셔너리/머지 기반 벡터화 — 행 루프 금지) ──────────
    ev = ev.reset_index(drop=True)
    ev["eid"] = ev.index
    ra = reports_all.copy()
    ra["m"] = ra["ym"].map(month_ord).astype(np.int64)
    ev["broker"] = ev["analyst_id"].str.split("@").str[-1]
    hf = ev["analyst_id"].str.contains("#", regex=False)
    ev.loc[hf, "broker"] = ev.loc[hf, "analyst_id"].str.split("#").str[0]
    ev["person"] = ev["analyst_id"].str.split("@").str[0]

    # ※ 아래 모든 판정 창은 [t, t+W] 로, 신호 공표 시점(signal_ym = t+W)에 실제로
    #   관측 가능한 정보만 쓴다. 창을 줄여 look-ahead 를 없애면 분류 정밀도가
    #   붕괴하므로(감사 후 실측 확인), 창은 유지하고 '공표를 지연'해 PIT 를 지킨다.
    # (1) a_active: 침묵 창 [t, t+W] 동안 타 종목 총 발간이 충분한가(재직 중 프록시)
    a_active_min = max(2, CFG.EXIT_SILENT_MONTHS // 2)
    cumN_d = dict(zip(zip(adense["analyst_id"], adense["m"]), adense["cumN"]))
    m1_d = adense.groupby("analyst_id")["m"].max().to_dict()
    def _win_reports(a, t):
        m1 = m1_d.get(a, t)
        hi = cumN_d.get((a, min(t + W, m1)), 0)
        lo = cumN_d.get((a, t - 1), 0)
        return max(0, hi - lo)
    ev["a_active"] = [
        _win_reports(a, t) >= a_active_min
        for a, t in zip(ev["analyst_id"].to_numpy(), ev["m"].to_numpy())]

    # (2) b_stop_i: 하우스(broker)가 [t, t+W] 에 i 리포트 0건 (머지 윈도우 집계)
    bt_df = ra.groupby(["broker_norm", "ticker", "m"], as_index=False).size()
    tmp = ev[["eid", "broker", "ticker", "m"]].merge(
        bt_df, left_on=["broker", "ticker"], right_on=["broker_norm", "ticker"],
        how="left", suffixes=("", "_r"))
    in_w = tmp["m_r"].notna() & (tmp["m_r"] >= tmp["m"]) & (tmp["m_r"] <= tmp["m"] + W)
    has_bt = set(tmp.loc[in_w & (tmp["size"] > 0), "eid"])
    ev["b_stop_i"] = ~ev["eid"].isin(has_bt)

    # (3) b_active: 하우스가 [t, t+W] 에 어떤 종목이든 발간 (하우스 자체 소멸 배제)
    ba_df = ra.groupby(["broker_norm", "m"], as_index=False).size()
    tmp = ev[["eid", "broker", "m"]].merge(
        ba_df, left_on="broker", right_on="broker_norm", how="left",
        suffixes=("", "_r"))
    in_w = tmp["m_r"].notna() & (tmp["m_r"] >= tmp["m"]) & (tmp["m_r"] <= tmp["m"] + W)
    act = set(tmp.loc[in_w & (tmp["size"] > 0), "eid"])
    ev["b_active"] = ev["eid"].isin(act)

    # (3b) house_multi: 사건 시점에 같은 하우스에서 i 를 커버하던 애널리스트가 2인 이상.
    #      1인뿐이면 '하우스의 결정'과 '그 애널리스트의 결정'을 구분할 수 없으므로
    #      계약 §6.5 의 V-DROP 정의(재직 중 i 만 끊음)를 우선한다(보수적 선택).
    cov_pairs = pd_[pd_["cov4q"]][["analyst_id", "ticker", "m"]].copy()
    cov_pairs["broker"] = cov_pairs["analyst_id"].str.split("@").str[-1]
    hfp = cov_pairs["analyst_id"].str.contains("#", regex=False)
    cov_pairs.loc[hfp, "broker"] = \
        cov_pairs.loc[hfp, "analyst_id"].str.split("#").str[0]
    hc = (cov_pairs.groupby(["broker", "ticker", "m"], as_index=False)["analyst_id"]
          .nunique().rename(columns={"analyst_id": "n_house_cov"}))
    ev = ev.merge(hc, on=["broker", "ticker", "m"], how="left")
    ev["n_house_cov"] = ev["n_house_cov"].fillna(1)

    # (4) moved: 인물(person_id)이 [t, t+W] 에 '다른 증권사'로 발간 → 이직(M-EXIT)
    #     ※ analyst_person_id(인물)와 analyst_id(인물@증권사)를 혼동하지 않는다(계약 §5)
    ev["moved"] = False
    if person_month is not None and len(person_month):
        pm = person_month.copy()
        if "m" not in pm.columns:
            pm["m"] = pm["ym"].map(month_ord).astype(np.int64)
        pb2 = (pm.groupby(["analyst_person_id", "broker_norm", "m"], as_index=False)
               .size())
        tmp = ev[["eid", "person", "broker", "m"]].merge(
            pb2, left_on="person", right_on="analyst_person_id", how="left",
            suffixes=("", "_r"))
        in_w = (tmp["m_r"].notna() & (tmp["broker_norm"] != tmp["broker"])
                & (tmp["m_r"] >= tmp["m"]) & (tmp["m_r"] <= tmp["m"] + W))
        moved = set(tmp.loc[in_w, "eid"])
        ev["moved"] = ev["eid"].isin(moved)

    # (5) 금투협 말소/해지 이력(가용 시) — 컬럼 유연 매칭
    kofia_gone = set()
    if kofia_df is not None and len(kofia_df):
        cols = {str(c).lower(): c for c in kofia_df.columns}
        nc = next((cols[c] for c in cols if "name" in c or "성명" in c), None)
        dc = next((cols[c] for c in cols if "말소" in c or "end" in c or "해지" in c), None)
        if nc and dc:
            for nm, dt in zip(kofia_df[nc], kofia_df[dc]):
                try:
                    mm = pd.Period(pd.Timestamp(dt), freq="M").ordinal
                    kofia_gone.add((str(nm).strip(), int(mm)))
                except Exception:
                    continue
    ev["kofia_gone"] = [
        any((p, mm + k) in kofia_gone for k in range(0, W + 1))
        for p, mm in zip(ev["person"], ev["m"].to_numpy())]

    # 분류 (벡터화). 우선순위: M-EXIT(기계적) → H-EXIT(하우스 결정) → V-DROP(잔여)
    is_m = (~ev["a_active"]) | ev["moved"] | ev["kofia_gone"]
    is_h = (~is_m) & ev["b_stop_i"] & ev["b_active"] & (ev["n_house_cov"] >= 2)
    ev["cls"] = np.where(is_m, "M-EXIT", np.where(is_h, "H-EXIT", "V-DROP"))
    ev["t_exit"] = ev["m"].map(ord_to_ym)
    # 공표 시점 = 침묵 확인이 끝나는 달의 말일. 모든 판정 근거가 이 시점에 관측
    # 가능하므로 거래 신호에 look-ahead 가 없다.
    ev["signal_ym"] = (ev["m"] + W).map(ord_to_ym)

    # ── 직전 커버 애널리스트 수 & AAR_neg (계약 §6.5 산식, 가중 1.0/1.5 고정) ──
    cov_count = (pd_[pd_["cov4q"]].groupby(["ticker", "m"], as_index=False)
                 .size().rename(columns={"size": "n_cov"}))
    evc = ev.groupby(["ticker", "m", "cls"]).size().unstack(fill_value=0)
    for c in ("V-DROP", "H-EXIT", "M-EXIT"):
        if c not in evc.columns:
            evc[c] = 0
    evc = evc.reset_index()
    evc = evc.merge(cov_count, on=["ticker", "m"], how="left")
    evc["n_cov"] = evc["n_cov"].fillna(1).clip(lower=1)
    evc["AAR_neg"] = -(CFG.EXIT_W_VDROP * evc["V-DROP"]
                       + CFG.EXIT_W_HEXIT * evc["H-EXIT"]) / evc["n_cov"]
    aar_neg = evc.assign(ym=(evc["m"] + W).map(ord_to_ym))[["ticker", "ym", "AAR_neg"]]

    log.kv("철회 인과 분해(§6.5)", {
        "이벤트 총계": len(ev),
        "V-DROP": int((ev["cls"] == "V-DROP").sum()),
        "H-EXIT": int((ev["cls"] == "H-EXIT").sum()),
        "M-EXIT": int((ev["cls"] == "M-EXIT").sum()),
        "이직감지(M요인)": int(ev["moved"].sum()),
        "금투협말소(M요인)": int(ev["kofia_gone"].sum())})
    keep = ["analyst_id", "person", "broker", "ticker", "t_exit", "signal_ym", "cls"]
    return ev[keep + ["m"]], aar_neg, cov_count

# ══════════════════════════════════════════════════════════════════════════════
# [S12] 종목 신호 집계 — AAR_pos(ω 3종) / AAR_neg / AAR_total (계약 §6.4~6.6)
# ══════════════════════════════════════════════════════════════════════════════

def build_stock_signals(vas_panel, aw, aar_neg, log):
    """반환 signals: (ym, m, ticker, pos_ew, pos_npub, pos_breadth, AAR_neg,
    z_pos_*, z_neg) — 전부 월 t 정보만 사용."""
    v = vas_panel[vas_panel["VAS"].notna()][
        ["analyst_id", "ticker", "m", "ym", "VAS"]].copy()
    if not len(v):
        return None
    v = v.merge(aw, on=["analyst_id", "m"], how="left")
    v["w_ew"] = 1.0
    v["w_npub"] = v["npub"].clip(lower=1).astype(float)
    v["w_breadth"] = v["breadth"].clip(lower=1).astype(float)
    outs = []
    for om in ("ew", "npub", "breadth"):
        wc = "w_" + om
        num = (v["VAS"] * v[wc]).groupby([v["ticker"], v["m"]]).sum()
        den = v[wc].groupby([v["ticker"], v["m"]]).sum()
        s = (num / den).rename(f"pos_{om}")
        outs.append(s)
    sig = pd.concat(outs, axis=1).reset_index()
    sig["ym"] = sig["m"].map(ord_to_ym)
    sig = sig.merge(aar_neg, on=["ticker", "ym"], how="left")
    sig["AAR_neg"] = sig["AAR_neg"].fillna(0.0)

    def _z(col):
        mu = sig.groupby("m")[col].transform("mean")
        sd = sig.groupby("m")[col].transform("std").replace(0, np.nan)
        return ((sig[col] - mu) / sd).fillna(0.0)
    for om in ("ew", "npub", "breadth"):
        sig[f"z_pos_{om}"] = _z(f"pos_{om}")
    sig["z_neg"] = _z("AAR_neg")
    log.kv("신호 집계(§6.4/6.6)", {
        "신호 행": len(sig), "월 수": sig["m"].nunique(),
        "월평균 신호 종목": f"{len(sig)/max(sig['m'].nunique(),1):.0f}",
        "AAR_neg<0 행": int((sig["AAR_neg"] < 0).sum())})
    return sig


def make_config_grid():
    """사전등록 12개 구성 (계약 §6.6 — 확장 금지)."""
    grid = []
    for om in CFG.GRID_OMEGA:
        for lam in CFG.GRID_LAMBDA:
            for h in CFG.GRID_HOLD_M:
                grid.append({"name": f"w={om}|lam={lam:g}|h={h}M",
                             "omega": om, "lam": lam, "hold": h})
    assert len(grid) == 12, "사전등록 격자는 12개 고정"
    return grid


# ══════════════════════════════════════════════════════════════════════════════
# [S13] 백테스트 엔진 (계약 §7/§8) — 익영업일 종가 진입, 월간 리밸런싱,
#        3M 은 중첩 트랜치(Jegadeesh-Timan), 연도별 거래세, 상폐 현금화
# ══════════════════════════════════════════════════════════════════════════════

def month_anchor_frames(close_wide, uni, log):
    """entry_px: (월 ordinal × ticker) 익월 첫 영업일 종가(=익영업일 앵커).
       H[m]  : 보유월 m 수익률 = entry_px(m+1)/entry_px(m) − 1  (일별 기반)
       S[m]  : 스냅샷 월말 폴백 수익률 (분할 왜곡 시 mcap 수익률 사용)
       last_px/last_dt: 상폐 현금화용 최종 체결가."""
    cal = close_wide.index
    mo = pd.PeriodIndex(cal, freq="M").astype(str)
    first_idx = pd.Series(np.arange(len(cal)), index=cal).groupby(mo).min()
    ft = {month_ord(k): cal[int(v)] for k, v in first_idx.items()}
    months = sorted(ft.keys())
    entry = {}
    ff = close_wide.ffill(limit=5)
    for m in months:
        entry[m] = ff.loc[ft[m]]
    entry_px = pd.DataFrame(entry).T                          # index=m, col=ticker
    H = entry_px.shift(-1) / entry_px - 1.0

    # 상폐/거래중단 현금화: 다음 앵커가 없으면 최종 체결가로 청산 (정리매매가 반영됨)
    last_px = close_wide.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)
    last_dt = close_wide.apply(lambda s: s.dropna().index[-1] if s.notna().any() else pd.NaT)
    for i, m in enumerate(months[:-1]):
        nxt = months[i + 1]
        row = H.loc[m]
        gone = row.isna() & entry_px.loc[m].notna()
        if gone.any():
            for t in row.index[gone]:
                ld = last_dt.get(t)
                if pd.notna(ld) and ft[m] <= ld < ft[nxt] + pd.Timedelta(days=10):
                    H.loc[m, t] = float(last_px[t] / entry_px.loc[m, t] - 1.0)

    # 스냅샷 폴백 수익률 (raw 종가 — 분할 가드로 mcap 수익률 대체)
    # ※ 라벨 규약: S.loc[m] = EOM(m-1)→EOM(m) 수익률 = '월 m 중에 실현된 수익'.
    #   H.loc[m](= 첫영업일(m)→첫영업일(m+1))와 같은 월을 가리켜야 하므로 반드시
    #   shift(1) 로 나눈다. shift(-1) 을 쓰면 보유월에 '다음 달' 수익이 실리고,
    #   상장폐지 직전월의 급락이 통째로 사라진다(감사 지적 반영).
    snap_c = uni.pivot_table(index="ym", columns="ticker", values="close",
                             aggfunc="last")
    snap_m = uni.pivot_table(index="ym", columns="ticker", values="mcap",
                             aggfunc="last")
    snap_c.index = [month_ord(x) for x in snap_c.index]
    snap_m.index = [month_ord(x) for x in snap_m.index]
    snap_c, snap_m = snap_c.sort_index(), snap_m.sort_index()
    S_raw = snap_c / snap_c.shift(1) - 1.0
    S_mc = snap_m / snap_m.shift(1) - 1.0
    split_like = (S_raw < -0.35) & (S_mc > S_raw + 0.25)
    S = S_raw.mask(split_like, S_mc)
    log.info(f"[S13] 앵커 프레임: {len(months)}개월, 스냅샷 폴백 행렬 {S.shape}, "
             f"분할가드 치환 {int(split_like.sum().sum())}셀")
    return entry_px, H, S, ft


def sell_tax_rate(year_month, market):
    d = month_end_date(year_month)
    for a, b, kospi, kosdaq in CFG.TAX_TABLE:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return kospi if market == "KOSPI" else kosdaq
    return 0.0015


class BacktestEngine:
    def __init__(self, signals, H, S, uni, log):
        self.sig, self.H, self.S, self.uni, self.log = signals, H, S, uni, log
        u = uni[["ym", "ticker", "market", "mcap_rank"]].copy()
        u["m"] = u["ym"].map(month_ord)
        self.uinfo = u.set_index(["m", "ticker"])
        self._uni_members = {m: set(g["ticker"])
                             for m, g in u.groupby("m")}
        self._slip = {}
        self._rowcache = {}

    def _slippage(self, m, t):
        key = (m, t)
        if key in self._slip:
            return self._slip[key]
        try:
            r = self.uinfo.loc[(m, t), "mcap_rank"]
            r = float(r.iloc[0]) if hasattr(r, "iloc") else float(r)
        except Exception:
            r = 9999
        bp = CFG.SLIPPAGE_BP["large"] if r <= CFG.SIZE_LARGE_RANK else \
            (CFG.SLIPPAGE_BP["mid"] if r <= CFG.SIZE_MID_RANK
             else CFG.SLIPPAGE_BP["small"])
        self._slip[key] = bp
        return bp

    def _market(self, m, t):
        try:
            v = self.uinfo.loc[(m, t), "market"]
            return str(v.iloc[0]) if hasattr(v, "iloc") else str(v)
        except Exception:
            return "KOSDAQ"

    def _month_rows(self, m):
        if m not in self._rowcache:
            hd = self.H.loc[m].dropna().to_dict() if m in self.H.index else {}
            sd = self.S.loc[m].dropna().to_dict() if m in self.S.index else {}
            self._rowcache[m] = (hd, sd)
        return self._rowcache[m]

    def _month_ret(self, m, names_w):
        """보유월 m 의 종목별 실현수익(딕셔너리 O(1) 조회 — 속도 최적화)."""
        hd, sd = self._month_rows(m)
        rets = {}
        n_fb = 0
        for t in names_w:
            if t in hd:
                r = hd[t]
            elif t in sd:
                r = sd[t]
                n_fb += 1
            else:
                r = 0.0                                  # 완전 소멸 → 현금화(로그)
            rets[t] = float(r)
        return rets, n_fb

    def select_portfolio(self, s_m, score_col, neg_excl=True, side="long"):
        """신호월 s_m 횡단면에서 Q5(또는 Q1) 선택. 반환: dict(ticker→weight)"""
        x = self.sig[self.sig["m"] == s_m][["ticker", score_col, "AAR_neg"]].dropna(
            subset=[score_col])
        x = x[x["ticker"].isin(self._uni_members.get(s_m, set()))]
        if len(x) < CFG.MIN_XSEC_NAMES:
            return {}, {"reason": f"신호종목 {len(x)}<{CFG.MIN_XSEC_NAMES}"}
        rk = x[score_col].rank(method="first")
        q = np.ceil(rk / len(x) * CFG.N_QUANTILES).astype(int)
        pick = x[q == (CFG.N_QUANTILES if side == "long" else 1)].copy()
        n_before = len(pick)
        if neg_excl and side == "long":
            thr = x["AAR_neg"].quantile(CFG.NEG_EXCL_PCT)
            pick = pick[~((pick["AAR_neg"] <= thr) & (pick["AAR_neg"] < 0))]
        if len(pick) < CFG.MIN_HOLDINGS:
            return {}, {"reason": f"보유 {len(pick)}<{CFG.MIN_HOLDINGS} → 현금",
                        "n_before_excl": n_before}
        w = min(1.0 / len(pick), CFG.MAX_WEIGHT)
        return {t: w for t in pick["ticker"]}, {"n": len(pick),
                                                "excluded": n_before - len(pick)}

    def run(self, config, cost_mult=1.0, keep_holdings=False):
        """config: {omega, lam, hold}. 반환: dict(월별 시계열/트레이드로그/보유내역)."""
        om, lam, hold = config["omega"], config["lam"], config["hold"]
        col = f"score_{om}_{lam:g}"
        if col not in self.sig.columns:
            self.sig[col] = self.sig[f"z_pos_{om}"] + lam * self.sig["z_neg"]
        months = sorted(self.sig["m"].unique())
        if not len(months):
            return {"config": config, "ts": pd.DataFrame(),
                    "trades": pd.DataFrame(), "holdings": {}}
        # 신호가 0건인 달도 '연속 월 그리드'로 순회한다. 건너뛰면 다중월 보유
        # 트랜치의 해당 월 손익이 통째로 누락된다(감사 지적 반영).
        month_iter = range(int(months[0]), int(months[-1]) + 1)
        bt_lo, bt_hi = month_ord(CFG.BT_START_MONTH), month_ord(CFG.BT_END_MONTH)
        tranches = [dict() for _ in range(hold)]
        rows, trade_log = [], []
        holdings = {}
        for s in month_iter:
            h = s + 1                                    # 보유월(진입: h 첫 영업일 종가)
            if not (bt_lo <= h <= bt_hi):
                continue
            new_w, info = self.select_portfolio(s, col)
            ti = s % hold
            old_w = tranches[ti]
            to_sell = {t: max(old_w.get(t, 0) - new_w.get(t, 0), 0)
                       for t in set(old_w) | set(new_w)}
            to_buy = {t: max(new_w.get(t, 0) - old_w.get(t, 0), 0)
                      for t in set(old_w) | set(new_w)}
            cost = 0.0
            for t, dw in to_sell.items():
                if dw > 0:
                    tax = sell_tax_rate(ord_to_ym(h), self._market(s, t))
                    cost += dw * (CFG.COMMISSION_BP / 1e4
                                  + self._slippage(s, t) / 1e4 + tax) * cost_mult
            for t, dw in to_buy.items():
                if dw > 0:
                    cost += dw * (CFG.COMMISSION_BP / 1e4
                                  + self._slippage(s, t) / 1e4) * cost_mult
            tranches[ti] = dict(new_w)
            cost /= hold                                  # 트랜치 자본 = 1/hold
            if keep_holdings:
                agg = {}
                for k in range(hold):
                    for t, w in tranches[k].items():
                        agg[t] = agg.get(t, 0.0) + w / hold
                holdings[h] = {"weights": agg, "cost": cost}

            # 보유월 수익 (트랜치 평균) + 드리프트
            port_ret = 0.0
            gross_w = 0.0
            n_fb_tot = 0
            hd_h, sd_h = self._month_rows(h)
            for k in range(hold):
                w = tranches[k]
                if not w:
                    continue
                rets, n_fb = self._month_ret(h, list(w))
                n_fb_tot += n_fb
                tr_ret = sum(w[t] * rets[t] for t in w)   # 소멸 종목은 rets=0
                cash_w = 1.0 - sum(w.values())
                port_ret += tr_ret / hold                 # 현금 수익 0 가정
                gross_w += sum(w.values()) / hold
                # 가격이 완전히 소멸한 종목(상폐 후 등)은 그 자리에서 현금 전환한다.
                # 트랜치에 남겨두면 다음 리밸런싱에 '이미 현금인 포지션'에 매도
                # 수수료·슬리피지·거래세가 부과된다(감사 지적 반영).
                newv = {t: w[t] * (1 + rets[t]) for t in w
                        if (t in hd_h) or (t in sd_h)}
                dead_w = sum(w[t] for t in w if t not in hd_h and t not in sd_h)
                tot = sum(newv.values()) + cash_w + dead_w
                if tot <= 0:
                    tranches[k] = {}
                    continue
                tranches[k] = {t: v / tot for t, v in newv.items() if v > 0}
            turn = sum(to_sell.values()) + sum(to_buy.values())
            rows.append({"m": h, "ym": ord_to_ym(h), "ret_gross": port_ret,
                         "ret_net": port_ret - cost, "cost": cost,
                         "turnover_1w": turn / 2 / hold, "invested_w": gross_w,
                         "n_hold": len(new_w), "n_fallback_px": n_fb_tot})
            trade_log.append({"signal_ym": ord_to_ym(s), "hold_ym": ord_to_ym(h),
                              "config": config["name"], "n_hold": len(new_w),
                              "note": info.get("reason", ""),
                              "excluded_negdecile": info.get("excluded", 0),
                              "turnover": turn / hold, "cost": cost})
        ts = pd.DataFrame(rows)
        return {"config": config, "ts": ts, "trades": pd.DataFrame(trade_log),
                "holdings": holdings}

    def quintile_spread(self, config):
        """Q5−Q1 스프레드(그로스, 배제/상한 미적용 — 알파 검증용 §7)."""
        om, lam, hold = config["omega"], config["lam"], config["hold"]
        col = f"score_{om}_{lam:g}"
        if col not in self.sig.columns:
            self.sig[col] = self.sig[f"z_pos_{om}"] + lam * self.sig["z_neg"]
        months = sorted(self.sig["m"].unique())
        bt_lo, bt_hi = month_ord(CFG.BT_START_MONTH), month_ord(CFG.BT_END_MONTH)
        acc = {}
        for s in months:
            q5, _ = self.select_portfolio(s, col, neg_excl=False, side="long")
            q1, _ = self.select_portfolio(s, col, neg_excl=False, side="short")
            if not q5 or not q1:
                continue
            for k in range(hold):
                h = s + 1 + k
                if not (bt_lo <= h <= bt_hi):
                    continue
                r5d, _ = self._month_ret(h, list(q5))
                r1d, _ = self._month_ret(h, list(q1))
                acc.setdefault(h, []).append(
                    float(np.mean(list(r5d.values())) - np.mean(list(r1d.values()))))
        out = pd.DataFrame({"m": list(acc), "spread":
                            [float(np.mean(v)) for v in acc.values()]}).sort_values("m")
        out["ym"] = out["m"].map(ord_to_ym)
        return out


def perf_metrics(monthly_ret, freq=12):
    r = pd.Series(monthly_ret).dropna()
    if not len(r):
        return {k: np.nan for k in ("CAGR", "vol", "Sharpe", "Sortino", "MDD",
                                    "Calmar", "hit", "n_months")}
    eq = (1 + r).cumprod()
    yrs = len(r) / freq
    cagr = float(eq.iloc[-1] ** (1 / max(yrs, 1e-9)) - 1)
    vol = float(r.std() * np.sqrt(freq))
    sharpe = float(r.mean() / r.std() * np.sqrt(freq)) if r.std() > 0 else np.nan
    dn = r[r < 0].std()
    sortino = float(r.mean() / dn * np.sqrt(freq)) if dn and dn > 0 else np.nan
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    calmar = float(cagr / abs(mdd)) if mdd < 0 else np.nan
    return {"CAGR": cagr, "vol": vol, "Sharpe": sharpe, "Sortino": sortino,
            "MDD": mdd, "Calmar": calmar, "hit": float((r > 0).mean()),
            "n_months": int(len(r))}


def naive_report_count_signal(reports_all, log):
    """나이브 벤치마크(§8): '단순 리포트 건수 증가' — 통제의 가치 비교 대상."""
    rc = reports_all.groupby(["ticker", "ym"], as_index=False).size()
    rc["m"] = rc["ym"].map(month_ord)
    rc = rc.sort_values(["ticker", "m"])
    spans = rc.groupby("ticker", as_index=False).agg(m0=("m", "min"), m1=("m", "max"))
    dense = _dense_group_grid(spans, ["ticker"], "m0", "m1")
    dense = dense.merge(rc[["ticker", "m", "size"]], on=["ticker", "m"], how="left")
    dense["size"] = dense["size"].fillna(0)
    g = dense.groupby("ticker")["size"]
    dense["cum"] = g.cumsum()
    gc = dense.groupby("ticker")["cum"]
    dense["avg12"] = (gc.shift(1, fill_value=0) - gc.shift(13, fill_value=0)) / 12.0
    dense["naive"] = dense["size"] - dense["avg12"]
    dense["ym"] = dense["m"].map(ord_to_ym)
    out = dense[["ticker", "ym", "m", "naive"]]
    log.info(f"[S13] 나이브 신호(리포트 건수 증가) 행 {len(out)}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# [S14] 이벤트 스터디 — V-DROP / H-EXIT / M-EXIT 3군 CAR (계약 §8, §9-7)
# ══════════════════════════════════════════════════════════════════════════════

def event_study_car(exit_events, close_wide, ft_map, log, horizon=None):
    """anchor = signal_ym 익월 첫 영업일. AR = r_i − r_EW(일별 동일가중 유니버스).
    반환: car_df(group, day, mean_car, se, n) + 요약(60일 CAR t 등)."""
    horizon = horizon or CFG.EVENT_CAR_DAYS
    if close_wide is None or exit_events is None or not len(exit_events):
        return None, {}
    rets = close_wide.pct_change(fill_method=None)
    mkt = rets.mean(axis=1)
    cal = rets.index
    car_acc = {}
    n_evt_used = {}
    for _, e in exit_events.iterrows():
        t = e["ticker"]
        if t not in rets.columns:
            continue
        anchor_m = month_ord(e["signal_ym"]) + 1
        if anchor_m not in ft_map:
            continue
        d0 = ft_map[anchor_m]
        i0 = cal.searchsorted(d0)
        if i0 + 5 >= len(cal):
            continue
        seg = rets[t].iloc[i0:i0 + horizon]
        seg_m = mkt.iloc[i0:i0 + horizon]
        ar = (seg - seg_m).to_numpy()
        if np.isnan(ar[:20]).all():
            continue
        ar = np.nan_to_num(ar, nan=0.0)
        car = np.cumsum(ar)
        if len(car) < horizon:
            car = np.pad(car, (0, horizon - len(car)), constant_values=car[-1]
                         if len(car) else 0.0)
        car_acc.setdefault(e["cls"], []).append(car)
        n_evt_used[e["cls"]] = n_evt_used.get(e["cls"], 0) + 1
    rows = []
    summary = {}
    for cls, mats in car_acc.items():
        M = np.vstack(mats)
        mean = M.mean(axis=0)
        se = M.std(axis=0, ddof=1) / np.sqrt(M.shape[0])
        for d in range(horizon):
            rows.append({"group": cls, "day": d + 1, "mean_car": float(mean[d]),
                         "se": float(se[d]), "n": int(M.shape[0])})
        d60 = min(59, horizon - 1)
        t60 = mean[d60] / se[d60] if se[d60] > 0 else np.nan
        summary[cls] = {"n": int(M.shape[0]), "car60": float(mean[d60]),
                        "t60": float(t60),
                        "car120": float(mean[-1]),
                        "t120": float(mean[-1] / se[-1]) if se[-1] > 0 else np.nan}
    log.kv("이벤트 스터디 요약(60영업일 CAR)", {
        k: f"CAR={v['car60']*100:.2f}% t={v['t60']:.2f} (n={v['n']})"
        for k, v in summary.items()})
    return (pd.DataFrame(rows) if rows else None), summary

# ══════════════════════════════════════════════════════════════════════════════
# [S15] 통계 검증 게이트 (계약 §9 전항목) — scipy 무의존 구현(정규근사 명시)
# ══════════════════════════════════════════════════════════════════════════════

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))

def norm_ppf(p):
    """Acklam 근사(정밀도 ~1e-9) — 역정규누적."""
    p = float(p)
    if not 0 < p < 1:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

def chi2_sf(x, k):
    """Wilson-Hilferty 정규근사 (보고서에 근사임을 명시)."""
    if x <= 0 or k <= 0:
        return 1.0
    z = ((x / k) ** (1.0 / 3.0) - (1 - 2.0 / (9 * k))) / math.sqrt(2.0 / (9 * k))
    return 1.0 - norm_cdf(z)


def newey_west_tstat(series, lags):
    """평균의 NW t-통계 (계약 §9-6)."""
    x = pd.Series(series).dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 8:
        return np.nan, np.nan, n
    mu = x.mean()
    e = x - mu
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, min(lags, n - 1) + 1):
        gl = float(e[L:] @ e[:-L]) / n
        s += 2 * (1 - L / (lags + 1)) * gl
    se = math.sqrt(max(s, 1e-18) / n)
    t = mu / se
    p = 2 * (1 - norm_cdf(abs(t)))
    return float(t), float(p), n


def block_bootstrap_sharpe(ret_daily, n_boot=None, block=None, seed=None):
    """원형 블록 부트스트랩 (계약 §9-1: 블록 21영업일, 1000회)."""
    n_boot = n_boot or CFG.BOOT_N
    block = block or CFG.BOOT_BLOCK_DAYS
    r = pd.Series(ret_daily).dropna().to_numpy(dtype=float)
    n = len(r)
    if n < block * 4:
        return {"p_sr_le_0": np.nan, "sr_ci": (np.nan, np.nan), "n": n}
    rng = np.random.default_rng(seed or CFG.RANDOM_SEED)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    idx = idx.reshape(n_boot, -1)[:, :n]
    samp = r[idx]
    mu = samp.mean(axis=1)
    sd = samp.std(axis=1, ddof=1)
    sr = np.where(sd > 0, mu / sd * math.sqrt(252), np.nan)
    sr = sr[~np.isnan(sr)]
    return {"p_sr_le_0": float((sr <= 0).mean()),
            "sr_ci": (float(np.percentile(sr, 2.5)), float(np.percentile(sr, 97.5))),
            "sr_boot_mean": float(sr.mean()), "n": n}


def cscv_pbo(ret_matrix, n_blocks=None, log=None):
    """CSCV PBO (계약 §9-2). ret_matrix: (T×N configs) 월간 수익률."""
    from itertools import combinations
    n_blocks = n_blocks or CFG.PBO_N_BLOCKS
    R = pd.DataFrame(ret_matrix).dropna(how="all").fillna(0.0).to_numpy(dtype=float)
    T, N = R.shape
    if T < n_blocks * 2:
        return {"pbo": np.nan, "n_splits": 0}
    edges = np.linspace(0, T, n_blocks + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(n_blocks)]
    lam = []
    combos = list(combinations(range(n_blocks), n_blocks // 2))
    for comb in combos:
        is_idx = np.concatenate([blocks[i] for i in comb])
        oos_idx = np.concatenate([blocks[i] for i in range(n_blocks)
                                  if i not in comb])
        def _sr(mat):
            mu = mat.mean(axis=0)
            sd = mat.std(axis=0, ddof=1)
            return np.where(sd > 0, mu / sd, -np.inf)
        sr_is, sr_oos = _sr(R[is_idx]), _sr(R[oos_idx])
        best = int(np.argmax(sr_is))
        rank = (sr_oos < sr_oos[best]).sum() + 0.5 * (sr_oos == sr_oos[best]).sum()
        w = rank / N
        w = min(max(w, 1e-6), 1 - 1e-6)
        lam.append(math.log(w / (1 - w)))
    lam = np.array(lam)
    return {"pbo": float((lam <= 0).mean()), "n_splits": len(lam),
            "lambda_mean": float(lam.mean())}


def deflated_sharpe(sr_sel_m, all_sr_m, T, skew, kurt, n_trials=None):
    """DSR (계약 §9-3). 입력은 '월간 비연율' SR. 시도 12회 명시."""
    n_trials = n_trials or CFG.N_TRIALS_DSR
    all_sr = np.array([s for s in all_sr_m if s == s])
    if len(all_sr) < 2 or T < 12 or sr_sel_m != sr_sel_m:
        return {"dsr": np.nan, "sr0": np.nan}
    v = float(all_sr.std(ddof=1))
    em = 0.5772156649
    sr0 = v * ((1 - em) * norm_ppf(1 - 1.0 / n_trials)
               + em * norm_ppf(1 - 1.0 / (n_trials * math.e)))
    denom = 1 - skew * sr_sel_m + (kurt - 1) / 4.0 * sr_sel_m ** 2
    if denom <= 0:
        return {"dsr": np.nan, "sr0": float(sr0)}
    z = (sr_sel_m - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    return {"dsr": float(norm_cdf(z)), "sr0": float(sr0), "z": float(z),
            "n_trials": n_trials}


def walk_forward(config_ts, log):
    """학습 5년 → 검증 1년 롤링 (계약 §9-4). config_ts: {name: 월간 net 시리즈(m)}"""
    names = list(config_ts)
    allm = sorted(set().union(*[set(s.index) for s in config_ts.values()]))
    if len(allm) < CFG.WF_TRAIN_M + CFG.WF_TEST_M:
        return None, {"note": f"표본 {len(allm)}개월 < 최소 {CFG.WF_TRAIN_M+CFG.WF_TEST_M}"}
    oos = []
    picks = []
    i = CFG.WF_TRAIN_M
    while i < len(allm):
        train_m = allm[i - CFG.WF_TRAIN_M:i]
        test_m = allm[i:i + CFG.WF_TEST_M]
        srs = {}
        for nm in names:
            s = config_ts[nm].reindex(train_m).dropna()
            srs[nm] = s.mean() / s.std() if len(s) > 12 and s.std() > 0 else -9e9
        best = max(srs, key=srs.get)
        picks.append({"from": ord_to_ym(test_m[0]), "pick": best})
        seg = config_ts[best].reindex(test_m).dropna()
        oos.append(seg)
        i += CFG.WF_TEST_M
    oos_s = pd.concat(oos).sort_index() if oos else pd.Series(dtype=float)
    met = perf_metrics(oos_s)
    if log:
        log.kv("워크포워드 OOS(§9-4)", {**{k: round(v, 4) if isinstance(v, float)
                                          else v for k, v in met.items()},
                                       "선택 이력": [p["pick"] for p in picks[-5:]]})
    return oos_s, {"metrics": met, "picks": picks}


def bh_fdr(pvals_dict, q=None):
    """Benjamini-Hochberg (계약 §9-5). 반환: {key: (p, p_adj, reject)}"""
    q = q or CFG.FDR_Q
    items = [(k, v) for k, v in pvals_dict.items() if v == v]
    if not items:
        return {}
    items.sort(key=lambda kv: kv[1])
    n = len(items)
    out = {}
    padj_prev = 1.0
    padjs = {}
    for rank in range(n, 0, -1):
        k, p = items[rank - 1]
        padj = min(p * n / rank, padj_prev)
        padj_prev = padj
        padjs[k] = padj
    thr_rank = 0
    for i, (k, p) in enumerate(items, 1):
        if p <= q * i / n:
            thr_rank = i
    for i, (k, p) in enumerate(items, 1):
        out[k] = {"p": p, "p_adj": padjs[k], "reject_null": i <= thr_rank}
    for k, v in pvals_dict.items():
        if v != v:
            out[k] = {"p": np.nan, "p_adj": np.nan, "reject_null": False}
    return out


def granger_lead_lag(vas_ticker_month, eps_hist, log, lags=3):
    """H5: VAS → 컨센서스 EPS 개정 선행성 (패널 그레인저, 계약 §9-8).
    양방향 Wald χ² 비교. eps 부재 시 None(UNTESTABLE)."""
    if eps_hist is None or not len(eps_hist):
        return None
    e = eps_hist.copy()
    e["m"] = e["ym"].map(month_ord)
    e = e.sort_values(["ticker", "m"])
    e["deps"] = e.groupby("ticker")["eps_fy1"].pct_change()
    e = e.replace([np.inf, -np.inf], np.nan)
    v = vas_ticker_month.rename(columns={"pos_ew": "vas"})[["ticker", "m", "vas"]]
    df = e.merge(v, on=["ticker", "m"], how="inner").dropna(subset=["deps", "vas"])
    if len(df) < 300 or df["ticker"].nunique() < 20:
        return {"status": "UNTESTABLE", "n": int(len(df))}
    df = df.sort_values(["ticker", "m"])
    for L in range(1, lags + 1):
        df[f"vas_l{L}"] = df.groupby("ticker")["vas"].shift(L)
        df[f"deps_l{L}"] = df.groupby("ticker")["deps"].shift(L)
    df = df.dropna()
    for c in ("deps", "vas"):                       # 티커 내 demean (FE)
        df[c + "_d"] = df[c] - df.groupby("ticker")[c].transform("mean")
    for L in range(1, lags + 1):
        for c in ("vas", "deps"):
            col = f"{c}_l{L}"
            df[col + "_d"] = df[col] - df.groupby("ticker")[col].transform("mean")

    def _wald(ycol, test_pref, ctrl_pref):
        y = df[ycol].to_numpy(dtype=float)
        Xt = df[[f"{test_pref}_l{L}_d" for L in range(1, lags + 1)]].to_numpy(float)
        Xc = df[[f"{ctrl_pref}_l{L}_d" for L in range(1, lags + 1)]].to_numpy(float)
        X = np.column_stack([np.ones(len(y)), Xt, Xc])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        e_ = y - X @ beta
        s2 = float(e_ @ e_) / max(len(y) - X.shape[1], 1)
        XtX_inv = np.linalg.pinv(X.T @ X)
        cov = s2 * XtX_inv
        b = beta[1:1 + lags]
        Vb = cov[1:1 + lags, 1:1 + lags]
        try:
            w = float(b @ np.linalg.pinv(Vb) @ b)
        except Exception:
            return np.nan, np.nan, b
        return w, chi2_sf(w, lags), b
    w_fwd, p_fwd, b_fwd = _wald("deps_d", "vas", "deps")     # VAS → ΔEPS
    w_rev, p_rev, b_rev = _wald("vas_d", "deps", "vas")      # ΔEPS → VAS
    res = {"status": "TESTED", "n": int(len(df)),
           "chi2_vas_to_eps": w_fwd, "p_vas_to_eps": p_fwd,
           "sum_beta_fwd": float(np.nansum(b_fwd)),
           "chi2_eps_to_vas": w_rev, "p_eps_to_vas": p_rev,
           "leads": bool(p_fwd == p_fwd and p_fwd < 0.05
                         and float(np.nansum(b_fwd)) > 0
                         and (p_rev != p_rev or p_fwd < p_rev))}
    log.kv("H5 그레인저 선행성", {k: (round(v, 5) if isinstance(v, float) else v)
                                for k, v in res.items()})
    return res


def logistic_irls(X, y, iters=25):
    X = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        z = X @ b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        W = p * (1 - p) + 1e-9
        try:
            H = X.T @ (X * W[:, None])
            g = X.T @ (y - p)
            step = np.linalg.solve(H, g)
        except Exception:
            break
        b = b + step
        if np.max(np.abs(step)) < 1e-8:
            break
    z = X @ b
    return b, 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def ipw_sensitivity(reports_all, uni, log):
    """§6.7: 식별 성공여부 로지스틱 (시총, 증권사 규모, 연도) → IPW 가중치.
    유의한 선택편향 진단 결과와 함께 (pub_key→weight) 반환."""
    df = reports_all.copy()
    df["y"] = df["has_analyst"].astype(float)
    u = uni[["ym", "ticker", "mcap"]]
    df = df.merge(u, on=["ym", "ticker"], how="left")
    df["log_mcap"] = np.log(df["mcap"].astype(float)).replace(
        [np.inf, -np.inf], np.nan)
    bsize = df.groupby("broker_norm")["ticker"].transform("count")
    df["log_bsize"] = np.log1p(bsize)
    df["yr"] = df["ym"].str[:4].astype(int) - 2020
    sub = df.dropna(subset=["log_mcap"])
    if len(sub) < 500 or sub["y"].nunique() < 2:
        return None, {"note": "IPW 표본 부족"}
    X = sub[["log_mcap", "log_bsize", "yr"]].to_numpy(float)
    Xs = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    b, phat = logistic_irls(Xs, sub["y"].to_numpy(float))
    diag = {"coef(절편,log시총,log증권사규모,연도)": np.round(b, 3).tolist(),
            "식별률": f"{sub['y'].mean()*100:.1f}%",
            "시총계수>0(대형주 편향)": bool(b[1] > 0.1)}
    w = 1.0 / np.clip(phat, 0.05, 1.0)
    sub = sub.assign(ipw=w)
    log.kv("§6.7 결측 민감도(IPW)", diag)
    return sub[["pub_date", "ticker", "broker_norm", "ipw"]], diag


def ipw_h1_recheck(vas_panel, aar_neg, ipw_w, engine, log):
    """§6.7 후속: 식별확률 역수(IPW)로 재가중한 AAR_pos 로 H1 스프레드 '재추정 병기'.
    가중치는 증권사×월 평균 IPW(선택편향 스트라타 프록시)를 VAS 집계에 적용."""
    if ipw_w is None or not len(ipw_w):
        return None
    try:
        w = ipw_w.copy()
        w["m"] = w["pub_date"].astype(str).str[:7].map(month_ord)
        bw = (w.groupby(["broker_norm", "m"])["ipw"].mean()
              .rename("ipw_bm").reset_index())
        need = ["analyst_id", "ticker", "m", "VAS", "broker"]
        v = vas_panel[vas_panel["VAS"].notna()][need].copy()
        v = v.merge(bw, left_on=["broker", "m"], right_on=["broker_norm", "m"],
                    how="left")
        v["ipw_bm"] = v["ipw_bm"].fillna(1.0)
        num = (v["VAS"] * v["ipw_bm"]).groupby([v["ticker"], v["m"]]).sum()
        den = v["ipw_bm"].groupby([v["ticker"], v["m"]]).sum()
        sig = (num / den).rename("pos_ipw").reset_index()
        sig["ym"] = sig["m"].map(ord_to_ym)
        mu = sig.groupby("m")["pos_ipw"].transform("mean")
        sd = sig.groupby("m")["pos_ipw"].transform("std").replace(0, np.nan)
        sig["z_pos_ew"] = ((sig["pos_ipw"] - mu) / sd).fillna(0.0)
        for c in ("z_pos_npub", "z_pos_breadth"):
            sig[c] = sig["z_pos_ew"]
        sig = sig.merge(aar_neg, on=["ticker", "ym"], how="left")
        sig["AAR_neg"] = sig["AAR_neg"].fillna(0.0)
        muN = sig.groupby("m")["AAR_neg"].transform("mean")
        sdN = sig.groupby("m")["AAR_neg"].transform("std").replace(0, np.nan)
        sig["z_neg"] = ((sig["AAR_neg"] - muN) / sdN).fillna(0.0)
        eng = BacktestEngine(sig, engine.H, engine.S, engine.uni, log)
        sp = eng.quintile_spread(PRIMARY_CFG)
        t, p, n = newey_west_tstat(sp["spread"], CFG.NW_LAGS_1M)
        res = {"t_ipw": float(t) if t == t else None, "n": int(n),
               "p_two": float(min(max(2 * (1 - norm_cdf(abs(t))), 0), 1))
               if t == t else None}
        log.kv("§6.7 IPW 재추정 H1(병기)", {"NW t(IPW 재가중)": res["t_ipw"],
                                           "n": n})
        return res
    except Exception as e:
        log.warn(f"IPW 재추정 실패(진단만 병기): {str(e)[:120]}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# [S15b] 가설 판정 H1~H5 + 플라시보 + 최종 수용/폐기 (계약 §4, §9, §11)
# ══════════════════════════════════════════════════════════════════════════════

PRIMARY_CFG = {"name": "w=ew|lam=1|h=1M", "omega": "ew", "lam": 1.0, "hold": 1}

def evaluate_hypotheses(engine, grid, results, es_summary, granger_res,
                        h2_series, h4_splits, log):
    """반환: hyp = {H1..H5: {p, stat, status}}, placebo, fdr"""
    hyp = {}
    # H1: 주 사전등록 구성(ew, λ=1, 1M) Q5−Q1 스프레드 NW t ≥ 2
    sp = engine.quintile_spread(PRIMARY_CFG)
    t1, p1, n1 = newey_west_tstat(sp["spread"], CFG.NW_LAGS_1M)
    p1_two = min(max(2 * (1 - norm_cdf(abs(t1))), 0.0), 1.0) if t1 == t1 else np.nan
    hyp["H1"] = {"stat": t1, "p": p1_two,
                 "n": n1, "desc": f"Q5-Q1 NW t={t1:.2f} (n={n1})",
                 "status": "PASS" if (t1 == t1 and t1 >= CFG.T_CRIT) else "FAIL"}

    # H2: 기회비용 가중(npub/breadth) − 비가중 스프레드 차이 > 0
    if h2_series is not None and len(h2_series):
        t2, p2, n2 = newey_west_tstat(h2_series, CFG.NW_LAGS_1M)
        one_sided_p = 1 - norm_cdf(t2) if t2 == t2 else np.nan
        hyp["H2"] = {"stat": t2, "p": one_sided_p, "n": n2,
                     "desc": f"가중-비가중 스프레드차 NW t={t2:.2f}",
                     "status": ("PASS" if t2 >= CFG.T_CRIT else
                                ("FAIL_DM" if t2 <= -CFG.T_CRIT else "WEAK"))}
    else:
        hyp["H2"] = {"stat": np.nan, "p": np.nan, "status": "UNTESTABLE"}

    # H3: V-DROP(−) vs M-EXIT(0) CAR 차이 t ≥ 2 (60영업일)
    if es_summary and "V-DROP" in es_summary and "M-EXIT" in es_summary:
        v, m_ = es_summary["V-DROP"], es_summary["M-EXIT"]
        se_v = abs(v["car60"] / v["t60"]) if v["t60"] not in (0, np.nan) and \
            v["t60"] == v["t60"] else np.nan
        se_m = abs(m_["car60"] / m_["t60"]) if m_["t60"] not in (0, np.nan) and \
            m_["t60"] == m_["t60"] else np.nan
        if se_v == se_v and se_m == se_m:
            tdiff = (m_["car60"] - v["car60"]) / math.sqrt(se_v**2 + se_m**2)
            # V-DROP 이 M-EXIT 보다 낮아야(음의 정보) → tdiff>0 기대
            p3 = 1 - norm_cdf(tdiff)
            hyp["H3"] = {"stat": tdiff, "p": p3,
                         "desc": f"CAR60 V={v['car60']*100:.2f}% "
                                 f"M={m_['car60']*100:.2f}% tdiff={tdiff:.2f}",
                         "status": "PASS" if (tdiff >= CFG.T_CRIT
                                              and v["car60"] < 0) else "FAIL"}
        else:
            hyp["H3"] = {"stat": np.nan, "p": np.nan, "status": "UNTESTABLE"}
    else:
        hyp["H3"] = {"stat": np.nan, "p": np.nan, "status": "UNTESTABLE",
                     "desc": "이벤트/일별가격 표본 부족"}

    # H4: 소형·저커버리지·고개인 조건부 강화 (차이 계열 NW t)
    if h4_splits:
        stats4 = {}
        for key, ser in h4_splits.items():
            t4, p4, n4 = newey_west_tstat(ser, CFG.NW_LAGS_1M)
            stats4[key] = {"t": t4, "p_one": 1 - norm_cdf(t4) if t4 == t4 else np.nan}
        tmain = stats4.get("small_minus_large", {}).get("t", np.nan)
        hyp["H4"] = {"stat": tmain,
                     "p": stats4.get("small_minus_large", {}).get("p_one", np.nan),
                     "detail": {k: round(v["t"], 2) if v["t"] == v["t"] else None
                                for k, v in stats4.items()},
                     "status": ("PASS" if tmain == tmain and tmain >= CFG.T_CRIT else
                                ("FAIL" if tmain == tmain and tmain <= -CFG.T_CRIT
                                 else "WEAK"))}
    else:
        hyp["H4"] = {"stat": np.nan, "p": np.nan, "status": "UNTESTABLE"}

    # H5: 그레인저 선행성
    if granger_res is None or granger_res.get("status") == "UNTESTABLE":
        hyp["H5"] = {"stat": np.nan, "p": np.nan, "status": "UNTESTABLE",
                     "desc": "컨센서스 EPS 이력 미확보(전향 축적 중)"}
    else:
        hyp["H5"] = {"stat": granger_res.get("chi2_vas_to_eps"),
                     "p": granger_res.get("p_vas_to_eps"),
                     "desc": f"VAS→ΔEPS p={granger_res.get('p_vas_to_eps'):.4f} / "
                             f"역방향 p={granger_res.get('p_eps_to_vas'):.4f}",
                     "status": "PASS" if granger_res.get("leads") else "FAIL"}

    # M-EXIT 플라시보 (계약 §9-7): 기계적 철회군에서 유의 효과 '없어야' 통과
    if es_summary and "M-EXIT" in es_summary:
        tm = es_summary["M-EXIT"]["t60"]
        if tm != tm:
            # t 계산 불가(표본 1건/분산 0) — '실패'가 아니라 '검증 불가'다.
            # FAIL 로 두면 표본 부족만으로 최종 판정이 KILL 로 떨어진다(감사 반영).
            placebo = {"t60": None, "status": "UNTESTABLE",
                       "desc": f"M-EXIT 표본 부족(n={es_summary['M-EXIT']['n']}) → "
                               "플라시보 t 산출 불가"}
        else:
            placebo = {"t60": tm,
                       "status": "PASS" if abs(tm) < CFG.T_CRIT else "FAIL",
                       "desc": f"M-EXIT CAR60 t={tm:.2f} → "
                               + ("귀무 유지(분해 성공)" if abs(tm) < CFG.T_CRIT
                                  else "유의 효과 발생(분해 실패 — 소외주 재발견)")}
    else:
        placebo = {"t60": np.nan, "status": "UNTESTABLE",
                   "desc": "M-EXIT 표본/일별가격 부족"}

    fdr = bh_fdr({k: v.get("p") for k, v in hyp.items()})
    for k in hyp:
        hyp[k]["fdr"] = fdr.get(k, {})
        if hyp[k]["status"] == "PASS" and not fdr.get(k, {}).get("reject_null", False):
            hyp[k]["status"] = "FAIL_FDR"       # BH-FDR 보정 후 탈락
    log.kv("가설 판정(BH-FDR q=0.10 반영)",
           {k: f"{v['status']} (p={v.get('p', float('nan'))})" for k, v in hyp.items()})
    return hyp, placebo, fdr


def final_verdict(hyp, placebo, pbo_res, dsr_res, excess_pa, interim, log):
    """계약 §11 수용/폐기 로직 그대로."""
    h1 = hyp["H1"]["status"] == "PASS"
    h2 = hyp["H2"]["status"] == "PASS"
    h5 = hyp["H5"]["status"]
    plc = placebo["status"] == "PASS"
    pbo_ok = pbo_res.get("pbo", 1.0) == pbo_res.get("pbo", 1.0) and \
        pbo_res["pbo"] < CFG.ACCEPT_MAX_PBO
    dsr_ok = dsr_res.get("dsr", 0) == dsr_res.get("dsr", 0) and dsr_res["dsr"] > 0.5
    exc_ok = excess_pa == excess_pa and excess_pa >= CFG.ACCEPT_MIN_EXCESS_PA
    if not h1 or placebo["status"] == "FAIL" or \
       (pbo_res.get("pbo", np.nan) == pbo_res.get("pbo", np.nan)
            and pbo_res["pbo"] >= CFG.ACCEPT_MAX_PBO):
        verdict = "KILL"
        why = ("H1 실패" if not h1 else
               ("M-EXIT 플라시보 실패(§6.5 분해 실패)" if placebo["status"] == "FAIL"
                else "PBO ≥ 0.5"))
    elif h1 and h5 == "PASS" and h2 and plc and pbo_ok and dsr_ok and exc_ok:
        verdict, why = "ACCEPT", "계약 §11 전체 조건 충족"
    elif h1 and h5 in ("FAIL", "UNTESTABLE"):
        verdict = "CONDITIONAL"
        why = ("H5 실패 → 컨센서스 개정의 느린 대리변수 가능성. 독립 배분 금지, "
               "개정 팩터와의 상관 분석만 수행" if h5 == "FAIL" else
               "H5 검증 불가(컨센서스 이력 미확보) → 독립 배분 보류, 이력 축적 후 재검정")
    else:
        verdict = "CONDITIONAL"
        why = f"부분 충족 (H2={hyp['H2']['status']}, DSR={dsr_res.get('dsr')}, " \
              f"초과수익={excess_pa})"
    if interim:
        why = "[INTERIM — 수집 커버리지 불완전, 재실행으로 확장 필요] " + why
    log.kv("최종 판정(§11)", {"verdict": verdict, "why": why})
    return verdict, why

# ══════════════════════════════════════════════════════════════════════════════
# [S16] 산출물/보조 빌더 — 통제변수, 일별 커브, H4 조건부, OPEN_QUESTIONS, 저장
# ══════════════════════════════════════════════════════════════════════════════

OPEN_QUESTIONS_LOG = [
    ("공저자 크레딧", "공저 리포트는 저자 각 1건으로 계상(각자의 주의 소요). 분수(1/k) "
     "계상 대안은 보수적 선택 원칙상 채택하지 않음 — 결과 민감도는 낮다고 판단."),
    ("철회 확정 시점과 침묵 창 길이", "계약은 침묵 개월 수를 지정하지 않는다. 3개월로 "
     "두면 한국의 분기 발간 리듬과 구분되지 않아 이벤트의 대다수가 단순 발간 공백"
     "(잡음)이 된다 — 합성 세계 실측에서 심어둔 효과가 잡음에 희석돼 회수되지 않았다. "
     "두 번의 실적 사이클을 건너뛴 6개월을 확정 기준으로 채택하고, 신호는 확정 시점"
     "(t+5) 월말에 공표한다. 모든 분류 근거(하우스 중단·이직·재직)의 관측 창을 동일한 "
     "[t, t+5]로 맞춰 look-ahead 를 원천 차단했다(창을 줄이는 대신 공표를 늦추는 방식)."),
    ("한경 컨센서스 robots.txt", "제3자 검증 기록(2026-05)에 따르면 "
     "consensus.hankyung.com/robots.txt 가 'Disallow: /' 로 전체 크롤링을 불허한다. "
     "본 코드는 요청 간격을 적응형으로 유지하고 페이지 단위로만 접근하지만, "
     "운영 적용 전 이용약관·robots 정책을 직접 확인하고 필요하면 제휴/유료 피드로 "
     "대체할 것을 권고한다. 차단 시 계약 §3 의 하우스 단위 폴백으로 자동 전환된다."),
    ("네이버 상세 페이지의 작성자 부재", "네이버 리서치는 리스트에도 상세 HTML 에도 "
     "작성자를 신뢰할 만하게 노출하지 않는다(작성자는 PDF 본문에 있다). 따라서 "
     "네이버는 '증권사 100% 확보' 경로로만 쓰고, 애널리스트 단위가 필요하면 한경이 "
     "사실상 유일한 확장 가능 경로다. 한경이 막히면 하우스 단위 폴백이 정답이며 "
     "이는 계약 §3 이 이미 규정한 경로다."),
    ("수정주가의 배당 미반영", "네이버 차트 계열(pykrx/FDR 의 수정주가 소스)은 "
     "액면분할·합병 등 가격수정만 반영하고 배당은 반영하지 않는다. 본 전략은 "
     "횡단면 상대수익 신호이므로 영향이 제한적이나, 절대 총수익(TR) 비교에는 "
     "배당수익률만큼의 하향 편의가 있다."),
    ("H-EXIT 과 V-DROP 의 경계", "같은 하우스에서 i 를 커버하던 애널리스트가 1인뿐이면 "
     "'하우스의 결정'과 '그 애널리스트의 결정'을 구분할 수 없다. 이 경우 계약 §6.5 의 "
     "V-DROP 정의(재직 중 i 만 끊음)를 우선 적용하고, H-EXIT 은 커버 애널리스트가 "
     "2인 이상이던 종목에서 전원이 중단한 경우로 한정한다(가중 1.5 의 남용 방지)."),
    ("H-EXIT 집계 단위", "계약 §6.5 count(H-EXIT) 를 '해당 하우스 소속 철회 애널리스트 "
     "수'로 해석(분모 단위와 일치). 하우스 개수 해석 대비 보수적."),
    ("섹터 분류 PIT 한계", "무료 소스는 현재시점 섹터만 제공 → 소급 적용. 섹터×월 FE "
     "에 미치는 왜곡은 제한적이나 업종 개편 종목은 오분류 가능."),
    ("스냅샷 이름 부재 시 SPAC 등 잔존", "코드 규칙(끝자리 0)만으로 걸러지지 않는 "
     "스팩·리츠가 EW 유니버스 벤치마크에 소량 잔존 가능. 커버리지 요건이 있는 본 "
     "전략 포트폴리오에는 영향 없음."),
    ("스냅샷 폴백 수익률", "일별 수정주가 미확보 종목은 월말 스냅샷 원시종가 수익률로 "
     "폴백하며, 분할 의심( raw<-35% & mcap 괴리 ) 시 시총 수익률로 대체. 건수는 "
     "로그·산출물에 기록."),
    ("증권사 개명 별칭", "주요 리브랜딩은 별칭 테이블로 통합했으나 누락 개명은 가짜 "
     "H-EXIT 을 만들 수 있음. H-EXIT 급증 월은 수동 점검 권고."),
    ("KRX 로그인 엔드포인트", "2025-12 이관 후 로그인 폼 필드/URL 재변경 가능. "
     "KRXAuthSession 클래스 한 곳만 수정하면 됨. 실패 시 폴백 체인으로 자동 진행."),
    ("컨센서스 EPS 이력", "무료 과거 이력 소스 부재 시 H5 는 UNTESTABLE 로 표기하고 "
     "매 실행마다 당월 스냅샷을 드라이브에 축적해 전향적으로 검정 가능해지도록 함."),
    ("개인 매매비중", "직접 수집이 과중하면 KOSDAQ×소형 프록시로 대체(H4 보조 지표). "
     "프록시 사용 여부는 mechanism_tests.md 에 명시."),
]

def open_questions_add(title, body):
    OPEN_QUESTIONS_LOG.append((title, body))


def build_ticker_month_controls(uni, dart_frames, log):
    """(ticker, ym) 통제변수: earn_flag, n_disc, idx_evt (§6.3 입력)."""
    u = uni[["ym", "ticker", "in_k200p", "in_kq150p"]].copy()
    u["m"] = u["ym"].map(month_ord)
    u = u.sort_values(["ticker", "m"])
    g = u.groupby("ticker")
    u["idx_evt"] = ((g["in_k200p"].diff().abs() > 0)
                    | (g["in_kq150p"].diff().abs() > 0)).astype("int8")
    ctrl = u[["ticker", "ym", "idx_evt"]]
    if dart_frames:
        dd = pd.concat(dart_frames, ignore_index=True)
        ctrl = ctrl.merge(dd[["ticker", "ym", "n_disc", "earnings_flag"]],
                          on=["ticker", "ym"], how="left")
        ctrl = ctrl.rename(columns={"earnings_flag": "earn_flag"})
    else:
        ctrl["n_disc"] = np.nan
        ctrl["earn_flag"] = 0
        log.warn("[S16] DART 미확보 → earn_flag/n_disc 통제 축소 "
                 "(섹터×월 FE 가 공통 시즌은 흡수하나 종목별 변이는 미통제 — 보고서 명기)")
    return ctrl


def daily_curve_from_holdings(holdings, close_wide, ft_map):
    """월별 보유내역 → 일별 순수익률 시계열 (부트스트랩/MDD 용, 비용은 리밸일 차감)."""
    if not holdings or close_wide is None:
        return None
    months = sorted(holdings)
    out = []
    cal = close_wide.index
    for i, h in enumerate(months):
        if h not in ft_map:
            continue
        d0 = ft_map[h]
        d1 = ft_map.get(h + 1)
        i0 = cal.searchsorted(d0)
        i1 = cal.searchsorted(d1) if d1 is not None else len(cal) - 1
        if i1 <= i0:
            continue
        w = holdings[h]["weights"]
        names = [t for t in w if t in close_wide.columns]
        if not names:
            seg = pd.Series(0.0, index=cal[i0 + 1:i1 + 1])
            out.append(seg)
            continue
        px = close_wide.iloc[i0:i1 + 1][names].ffill()
        base = px.iloc[0]
        ok = base.notna() & (base > 0)
        names = [t for t in names if ok.get(t, False)]
        if not names:
            continue
        rel = px[names] / px[names].iloc[0]
        rel = rel.fillna(1.0)
        wv = np.array([w[t] for t in names])
        cash = 1.0 - wv.sum()
        V = rel.to_numpy() @ wv + cash
        r = pd.Series(V, index=px.index).pct_change().iloc[1:]
        r.iloc[0] = r.iloc[0] - holdings[h]["cost"]
        out.append(r)
    if not out:
        return None
    return pd.concat(out).sort_index()


def h2_h4_series(engine, log, cov_count=None, invr=None):
    """H2: (가중 스프레드 평균 − 비가중 스프레드) 월별 차이 계열.
       H4: 소형−대형 / 저커버−고커버 / 고개인−저개인 스프레드 차이 계열."""
    lam, hold = 1.0, 1
    sp = {}
    for om in ("ew", "npub", "breadth"):
        s = engine.quintile_spread({"omega": om, "lam": lam, "hold": hold,
                                    "name": f"tmp_{om}"})
        sp[om] = s.set_index("m")["spread"]
    both = pd.concat([sp["npub"], sp["breadth"]], axis=1).mean(axis=1)
    h2 = (both - sp["ew"]).dropna()

    # H4: 신호월 시총 중위수 기준 소형/대형 분리 스프레드 (primary score 사용)
    col = "score_ew_1"
    if col not in engine.sig.columns:
        engine.sig[col] = engine.sig["z_pos_ew"] + 1.0 * engine.sig["z_neg"]
    u = engine.uni[["ym", "ticker", "mcap", "market", "mcap_rank"]].copy()
    u["m"] = u["ym"].map(month_ord)
    sigx = engine.sig.merge(u, on=["ticker", "m"], how="left")
    if cov_count is not None and len(cov_count):
        sigx = sigx.merge(cov_count, on=["ticker", "m"], how="left")
    else:
        sigx["n_cov"] = np.nan
    if invr is not None and len(invr):
        sigx["year"] = sigx["ym"].str[:4].astype(int)
        sigx = sigx.merge(invr, on=["ticker", "year"], how="left")
    else:
        # 프록시: KOSDAQ & 시총 하위 50% → 고개인 (mechanism_tests.md 에 프록시 명시)
        med = sigx.groupby("m")["mcap"].transform("median")
        sigx["indiv_ratio"] = ((sigx["market"] == "KOSDAQ")
                               & (sigx["mcap"] < med)).astype(float)

    def _cond_spread(mask_hi):
        acc = {}
        for m, g in sigx.groupby("m"):
            g = g.dropna(subset=[col])
            hi, lo = g[mask_hi(g)], g[~mask_hi(g)]
            for part, sign in ((hi, +1), (lo, -1)):
                if len(part) < 20:
                    continue
                rk = part[col].rank(method="first")
                q = np.ceil(rk / len(part) * 5).astype(int)
                q5t, q1t = part[q == 5]["ticker"], part[q == 1]["ticker"]
                h = m + 1
                r5, _ = engine._month_ret(h, list(q5t))
                r1, _ = engine._month_ret(h, list(q1t))
                if r5 and r1:
                    spr = float(np.mean(list(r5.values()))
                                - np.mean(list(r1.values())))
                    acc.setdefault(h, {})[sign] = spr
        rows = {h: d[+1] - d[-1] for h, d in acc.items() if +1 in d and -1 in d}
        return pd.Series(rows).sort_index()

    med_mask = lambda g: g["mcap"] < g["mcap"].median()
    h4 = {"small_minus_large": _cond_spread(med_mask)}
    if sigx["n_cov"].notna().any():
        h4["lowcov_minus_highcov"] = _cond_spread(
            lambda g: g["n_cov"].fillna(0) <= g["n_cov"].fillna(0).median())
    h4["highindiv_minus_lowindiv"] = _cond_spread(
        lambda g: g["indiv_ratio"].fillna(0) >= g["indiv_ratio"].fillna(0).median())
    log.info(f"[S16] H2 차이계열 {len(h2)}개월, H4 분할 {list(h4)}")
    return h2, h4


# ══════════════════════════════════════════════════════════════════════════════
# [S17] 비교전략 — 시가총액 하위 1000종목 압축 유니버스 (발주자 지시)
# ══════════════════════════════════════════════════════════════════════════════

def run_small1000_comparison(signals, H, S, uni, grid, log, out_dir, store):
    n_by_m = uni.groupby("ym")["ticker"].transform("count")
    small = uni[uni["mcap_rank"] > (n_by_m - 1000)].copy()
    if not len(small):
        return None
    eng = BacktestEngine(signals, H, S, small, log)
    rows = []
    ts_map = {}
    for cfg_ in grid:
        try:
            res = eng.run(cfg_, cost_mult=1.0)
            met = perf_metrics(res["ts"].set_index("m")["ret_net"]) \
                if len(res["ts"]) else perf_metrics([])
            met.update({"config": cfg_["name"],
                        "avg_turnover": float(res["ts"]["turnover_1w"].mean())
                        if len(res["ts"]) else np.nan})
            rows.append(met)
            if len(res["ts"]):
                ts_map[cfg_["name"]] = res["ts"].set_index("m")["ret_net"]
        except Exception as e:
            log.warn(f"소형1000 구성 실패({cfg_['name']}): {str(e)[:100]}")
    if not rows:
        return None
    met_df = pd.DataFrame(rows).set_index("config")
    pbo = cscv_pbo(pd.DataFrame(ts_map)) if ts_map else {"pbo": np.nan}
    sp = eng.quintile_spread(PRIMARY_CFG)
    t1, p1, n1 = newey_west_tstat(sp["spread"], CFG.NW_LAGS_1M) if len(sp) \
        else (np.nan, np.nan, 0)
    out = {"metrics": met_df, "pbo": pbo, "h1_t": t1, "h1_n": n1,
           "avg_names": float(signals.merge(
               small[["ym", "ticker"]], on=["ym", "ticker"], how="inner")
               .groupby("ym")["ticker"].count().mean()) if len(signals) else 0}
    try:
        p = Path(out_dir) / "compare_small1000"
        p.mkdir(parents=True, exist_ok=True)
        met_df.to_csv(p / "metrics_small1000.csv", encoding="utf-8-sig")
    except Exception:
        pass
    log.table("비교전략(시총 하위 1000) 성과 — net(base)", met_df.round(4))
    log.kv("비교전략 강건성", {"PBO": pbo.get("pbo"), "H1 NW t": round(t1, 2)
                              if t1 == t1 else None, "월평균 신호종목": out["avg_names"]})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# [S18] SYNTH 모드 — 네트워크 없이 전체 파이프라인 자가검증용 합성 세계
#   (플란트 효과: 주의급증→양의 드리프트, V/H-EXIT→음, M-EXIT→0, EPS 는 VAS 후행)
# ══════════════════════════════════════════════════════════════════════════════

def synth_generate(store, log):
    ck = store.local_root / "state" / "synth_done.json"
    if read_json_safe(ck):
        log.info("[S18] SYNTH 데이터 기생성 — 재사용")
        return
    rng = np.random.default_rng(CFG.RANDOM_SEED)
    months = month_range(CFG.META_START_MONTH, CFG.BT_END_MONTH)
    n_kospi, n_kosdaq = 200, 120
    tickers = [f"{100000 + i * 10:06d}" for i in range(n_kospi + n_kosdaq)]
    markets = {t: ("KOSPI" if i < n_kospi else "KOSDAQ")
               for i, t in enumerate(tickers)}
    sectors = {t: f"SEC{int(i) % 12:02d}" for i, t in enumerate(tickers)}
    delist = set(rng.choice(tickers, size=24, replace=False))
    delist_m = {t: str(rng.choice(months[30:-6])) for t in delist}

    cal = pd.bdate_range(month_end_date(CFG.META_START_MONTH)
                         - pd.Timedelta(days=31), "2026-07-31")
    n_d, n_t = len(cal), len(tickers)
    mkt_f = rng.normal(0.0003, 0.009, n_d)
    eps_i = rng.normal(0, 0.02, (n_d, n_t))
    drift = np.zeros((n_d, n_t))

    # 애널리스트 세계
    brokers = [f"BR{j:02d}" for j in range(20)]
    _sur = list("김이박최정강조윤장임한오서신권황")
    _giv = ["민준", "서연", "도윤", "하은", "지호", "수아", "예준", "지유", "시우",
            "채원", "주원", "지안", "건우", "다은", "현우", "서준"]
    analysts = []
    for j in range(130):
        nm = _sur[j % len(_sur)] + _giv[(j // len(_sur)) % len(_giv)]
        a = {"name": nm, "broker": brokers[j % len(brokers)],
             "cov": list(rng.choice(tickers, size=int(rng.integers(8, 22)),
                                    replace=False)),
             "start": int(rng.integers(0, 24)), "end": len(months)}
        analysts.append(a)
    date_by_m = {}
    for i, d in enumerate(cal):
        date_by_m.setdefault(str(pd.Period(d, freq="M")), []).append(i)

    def _plant(t_idx, m_idx, days, mag):
        if m_idx + 1 >= len(months):
            return
        ds = date_by_m.get(months[m_idx + 1], [])
        if not ds:
            return
        i0 = ds[0]
        drift[i0:i0 + days, t_idx] += mag / days

    tick_ix = {t: i for i, t in enumerate(tickers)}
    reports = []
    planted = {"conv": 0, "v": 0, "h": 0, "m": 0}
    conv_events = []
    for a in analysts:
        boost = {}
        # 자발적 주의 급증(H1): 커버 종목 중 임의 시점 2개월 리포트 급증 + 양의 드리프트
        for _ in range(8):
            t = str(rng.choice(a["cov"]))
            m0 = int(rng.integers(a["start"] + 26, len(months) - 5))
            boost[(t, m0)] = boost[(t, m0 + 1)] = 5.0
            _plant(tick_ix[t], m0, 42, 0.18)
            planted["conv"] += 1
            conv_events.append((t, m0))
        # V-DROP: 재직 중 특정 종목만 중단 + 음의 드리프트
        vdrops = rng.choice(a["cov"], size=2, replace=False)
        vstart = {str(t): int(rng.integers(a["start"] + 20, len(months) - 8))
                  for t in vdrops}
        for t, m0 in vstart.items():
            _plant(tick_ix[t], m0 + 2, 60, -0.14)
            planted["v"] += 1
        # M-EXIT: 애널리스트 15% 는 중도 퇴사(전체 발간 중단, 드리프트 0 = 플라시보)
        quit_m = None
        if rng.random() < 0.15:
            quit_m = int(rng.integers(a["start"] + 26, len(months) - 6))
            planted["m"] += 1
        for mi, ym in enumerate(months):
            if mi < a["start"] or (quit_m is not None and mi >= quit_m):
                continue
            for t in a["cov"]:
                if t in vstart and mi >= vstart[t]:
                    continue
                if t in delist and months.index(delist_m[t]) <= mi:
                    continue
                lam = 0.75 * boost.get((t, mi), 1.0)
                emonth = (mi % 12) in (2, 4, 7, 10)          # 실적시즌 기계적 발간
                if emonth:
                    lam *= 1.8
                k = rng.poisson(lam)
                for _ in range(int(k)):
                    ds = date_by_m[ym]
                    d = cal[int(rng.choice(ds))]
                    reports.append((d.strftime("%Y-%m-%d"), ym, t, a["broker"],
                                    a["name"]))
    # H-EXIT: 하우스 3곳이 특정 종목 커버 전면 중단 + 강한 음
    mi_of = {ym: i for i, ym in enumerate(months)}
    for b in brokers[:3]:
        cov_all = [t for a in analysts if a["broker"] == b for t in a["cov"]]
        if not cov_all:
            continue
        t = str(rng.choice(cov_all))
        m0 = int(rng.integers(40, len(months) - 8))
        reports = [r for r in reports
                   if not (r[3] == b and r[2] == t and mi_of[r[1]] >= m0)]
        _plant(tick_ix[t], m0 + 2, 60, -0.12)
        planted["h"] += 1

    # 가격 생성 (플란트 드리프트 반영) + 상폐 처리
    ret = 0.9 * mkt_f[:, None] * rng.uniform(0.5, 1.5, n_t)[None, :] + eps_i + drift
    px = 10000 * np.exp(np.cumsum(ret, axis=0))
    for t in delist:
        di = date_by_m[delist_m[t]][-1]
        px[di - 15:di, tick_ix[t]] *= np.linspace(1.0, 0.55, 15)   # 정리매매 급락
        px[di:, tick_ix[t]] = np.nan
    shares = rng.uniform(1e6, 5e7, n_t)

    # 캐시 적재: 스냅샷/가격/리포트/DART/EPS/섹터 — 실수집과 동일 경로
    for mi, ym in enumerate(months):
        ds = date_by_m[ym]
        di = ds[-1]
        alive = ~np.isnan(px[di])
        snap = pd.DataFrame({
            "ticker": np.array(tickers)[alive],
            "name": "", "market": [markets[t] for t in np.array(tickers)[alive]],
            "close": px[di][alive], "mcap": px[di][alive] * shares[alive],
            "shares": shares[alive]})
        snap["date"] = cal[di].strftime("%Y-%m-%d")
        snap["ym"] = ym
        store.save_df(snap, "parsed", f"snapshots/{ym}.parquet", scope="common",
                      desc="SYNTH 스냅샷", stage="SYNTH")
    for t in tickers:
        s = pd.Series(px[:, tick_ix[t]], index=cal).dropna()
        d = pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "open": s.values,
                          "high": s.values, "low": s.values, "close": s.values,
                          "volume": 1e5, "src": "synth"})
        d["asof"] = str(month_end_date(CFG.BT_END_MONTH).date())
        store.save_df(d, "parsed", f"prices/{t}.parquet", scope="common",
                      desc="SYNTH 가격", stage="SYNTH")
    rep = pd.DataFrame(reports, columns=["pub_date", "ym", "ticker", "broker",
                                         "analyst_raw"])
    # 식별률 ~75% 로 계획적 결측(Phase0/IPW 경로 검증): 소형주일수록 결측 확률↑
    mc_rank = pd.Series({t: i for i, t in enumerate(tickers)})
    pmiss = 0.10 + 0.25 * (rep["ticker"].map(mc_rank) / n_t)
    miss = rng.random(len(rep)) < pmiss
    rep.loc[miss, "analyst_raw"] = ""
    rep["title"] = rep["ticker"] + "(" + rep["ticker"] + ") 기업분석"
    rep["nid"] = [str(i) for i in range(len(rep))]
    rep["pdf_url"] = ""
    for ym, g in rep.groupby("ym"):
        store.save_df(g.assign(source="hankyung"), "parsed",
                      f"reports_meta/hankyung/{ym}.parquet", scope="common",
                      desc="SYNTH 리포트", stage="SYNTH")
    # DART: 실적월(3,5,8,11 상당) + 랜덤 공시
    dart_rows = []
    for mi, ym in enumerate(months):
        for t in tickers:
            if t in delist and months.index(delist_m[t]) < mi:
                continue
            e = 1 if (mi % 12) in (2, 4, 7, 10) else 0
            nd = int(rng.poisson(1.2) + (3 if e else 0))
            if nd > 0:
                dart_rows.append({"ticker": t, "ym": ym, "n_disc": nd,
                                  "earnings_flag": e})
    dd = pd.DataFrame(dart_rows)
    for ym, g in dd.groupby("ym"):
        store.save_df(g, "parsed", f"dart/{ym}.parquet", scope="common",
                      desc="SYNTH DART", stage="SYNTH")
    # 컨센서스 EPS: VAS(주의급증) 1개월 후행 반영 → H5 PASS 설계
    eps_rows = []
    base_eps = rng.uniform(500, 5000, n_t)
    bump = np.zeros((len(months), n_t))
    for t, m0 in conv_events:
        if m0 + 1 < len(months):
            bump[m0 + 1:, tick_ix[t]] += 0.06
    for mi, ym in enumerate(months):
        vals = base_eps * (1 + bump[mi]) * (1 + rng.normal(0, 0.01, n_t))
        for t in tickers:
            eps_rows.append({"ticker": t, "ym": ym,
                             "eps_fy1": float(vals[tick_ix[t]])})
    store.save_df(pd.DataFrame(eps_rows), "parsed", "consensus/eps_monthly.parquet",
                  scope="common", desc="SYNTH 컨센서스", stage="SYNTH")
    store.save_df(pd.DataFrame({"ticker": tickers,
                                "sector": [sectors[t] for t in tickers]}),
                  "parsed", "sectors/krx_sector_map.parquet", scope="common",
                  desc="SYNTH 섹터", stage="SYNTH")
    atomic_write_json(ck, {"done": True, "planted": planted,
                           "at": datetime.now().isoformat()})
    log.kv("[S18] SYNTH 세계 생성", {"종목": n_t, "리포트": len(rep),
                                    "플란트": planted, "상폐": len(delist)})

# ══════════════════════════════════════════════════════════════════════════════
# [S16b] 산출물 기록 (계약 §10 전체) + 드라이브 발행
# ══════════════════════════════════════════════════════════════════════════════

def publish_output(store, path, desc=""):
    """outputs 파일을 드라이브에 미러하고 전용인덱스에 등록."""
    path = Path(path)
    if store.have_drive:
        try:
            d = store.drive_root / "outputs" / path.name
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, d)
        except Exception:
            pass
    store.idx_dedicated.register(f"outputs/{path.name}",
                                 {"path": str(path), "desc": desc, "tier": "outputs"})


def _md(lines):
    return "\n".join(lines) + "\n"


def write_all_outputs(ctx):
    """ctx: main() 이 채운 컨텍스트 딕셔너리."""
    store, log = ctx["store"], ctx["log"]
    out = Path(ctx["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    interim_tag = "**[INTERIM — 수집 타임박스로 부분 데이터 결과. 재실행 시 커버리지 " \
                  "자동 확장]**\n\n" if ctx["interim"] else ""
    house_tag = "**[폴백: broker×sector 하우스 단위 신호 — 애널리스트 단위 아님]**\n\n" \
        if ctx.get("house_fb") else ""

    def W(name, text):
        p = out / name
        p.write_text(house_tag + interim_tag + text, encoding="utf-8")
        publish_output(store, p, desc=name)

    def WD(name, df, desc=""):
        if df is None or (hasattr(df, "empty") and df.empty):
            return
        p = out / name
        try:
            if name.endswith(".csv"):
                df.to_csv(p, encoding="utf-8-sig")
            else:
                df.reset_index(drop=False).to_parquet(p, index=False)
        except Exception:
            p = p.with_suffix(".pkl")
            df.to_pickle(p)
        publish_output(store, p, desc=desc)

    # ── 데이터 산출물 ──────────────────────────────────────────────────────
    vp = ctx.get("vas_panel")
    if vp is not None:
        cols = [c for c in ("analyst_id", "ticker", "ym", "share", "base",
                            "EA", "EA_sh", "VAS") if c in vp.columns]
        WD("attention_panel.parquet", vp[cols].reset_index(drop=True),
           "주의 패널 (§10)")
    WD("coverage_exit_classification.parquet", ctx.get("exit_events"),
       "V-DROP/H-EXIT/M-EXIT 라벨")
    WD("event_study_car.parquet", ctx.get("car_df"), "3군 CAR 곡선")
    WD("metrics_all_configs.csv", ctx.get("metrics_df"), "12구성×비용 성과")
    WD("equity_curves.parquet", ctx.get("equity_df"), "에쿼티 곡선")
    WD("trade_log.parquet", ctx.get("trades_df"), "트레이드 로그")
    ann_df = ctx.get("annual_df")
    if ann_df is not None and len(ann_df):
        WD("annual_returns.csv", ann_df.set_index(["series", "year"]),
           "연도별 수익률(전 구성+벤치마크, §8)")

    hyp, placebo, fdr = ctx.get("hyp", {}), ctx.get("placebo", {}), ctx.get("fdr", {})
    boot, pbo, dsr = ctx.get("boot", {}), ctx.get("pbo", {}), ctx.get("dsr", {})
    wf = ctx.get("wf_info") or {}

    # ── hypothesis_test_report.md ─────────────────────────────────────────
    L = ["# 가설 검정 보고 (H1~H5 + BH-FDR + PBO/DSR)", ""]
    for k in ("H1", "H2", "H3", "H4", "H5"):
        h = hyp.get(k, {})
        L += [f"## {k}: {HYPOTHESES[k]}",
              f"- 상태: **{h.get('status')}** | 통계량 {h.get('stat')} | "
              f"p={h.get('p')} | FDR보정 p={h.get('fdr', {}).get('p_adj')}",
              f"- 상세: {h.get('desc', h.get('detail', ''))}", ""]
    ipr = ctx.get("ipw_recheck")
    if ipr:
        L += [f"### §6.7 IPW 재추정 병기 (식별률<70% 경로)",
              f"- IPW 재가중 H1 스프레드 NW t = {ipr.get('t_ipw')} "
              f"(n={ipr.get('n')}, 양측 p={ipr.get('p_two')}) — 비가중 결과와 비교해 "
              "선택편향 방향/크기를 판단할 것.", ""]
    L += ["## 다중검정/과적합 게이트",
          f"- BH-FDR(q={CFG.FDR_Q}): {json.dumps({k: v.get('reject_null') for k, v in fdr.items()}, ensure_ascii=False)}",
          f"- 블록 부트스트랩(21d×{CFG.BOOT_N}): P(SR≤0)={boot.get('p_sr_le_0')}, "
          f"95% CI={boot.get('sr_ci')}",
          f"- PBO(CSCV, S={CFG.PBO_N_BLOCKS}, 12구성): {pbo.get('pbo')} "
          f"(분할 {pbo.get('n_splits')}회)",
          f"- DSR(시도 {CFG.N_TRIALS_DSR}회 명시): {dsr.get('dsr')} "
          f"(SR0={dsr.get('sr0')})",
          f"- 워크포워드(5y/1y): OOS {json.dumps(wf.get('metrics', {}), ensure_ascii=False, default=str)}",
          "", "※ p값은 정규근사(NW/Wilson-Hilferty) 기반."]
    W("hypothesis_test_report.md", _md(L))

    # ── mechanism_tests.md (H2/H4) ────────────────────────────────────────
    L = ["# 메커니즘 조건부 예측 (H2/H4)", "",
         f"## H2 기회비용 가중 vs 비가중: {hyp.get('H2', {}).get('status')}",
         f"- 월별 (가중평균−비가중) 스프레드 차이 NW t = {hyp.get('H2', {}).get('stat')}",
         "- 해석: t≥2 → 바쁜 애널리스트의 집중이 더 정보적(메커니즘 부합). "
         "t≤−2 → 한가한 애널리스트에서 더 강함 = 데이터마이닝 판정(계약 §4).", "",
         f"## H4 조건부 이질성: {hyp.get('H4', {}).get('status')}",
         f"- 분할별 차이 t: {json.dumps(hyp.get('H4', {}).get('detail', {}), ensure_ascii=False)}",
         f"- 개인비중 데이터: {'실수집' if ctx.get('invr_real') else 'KOSDAQ×소형 프록시 사용(명시)'}"]
    W("mechanism_tests.md", _md(L))

    # ── causal_decomposition.md (핵심 플라시보) ────────────────────────────
    es = ctx.get("es_summary") or {}
    ev = ctx.get("exit_events")
    cnts = ev["cls"].value_counts().to_dict() if ev is not None and len(ev) else {}
    L = ["# 커버리지 철회 인과 분해 — M-EXIT 플라시보 (계약 §6.5/§9-7)", "",
         f"- 이벤트 분포: {json.dumps(cnts, ensure_ascii=False)}",
         "", "| 군 | n | CAR60 | t60 | CAR120 | t120 |", "|---|---|---|---|---|---|"]
    for g in ("V-DROP", "H-EXIT", "M-EXIT"):
        s = es.get(g)
        if s:
            L.append(f"| {g} | {s['n']} | {s['car60']*100:.2f}% | {s['t60']:.2f} | "
                     f"{s['car120']*100:.2f}% | {s['t120']:.2f} |")
        else:
            L.append(f"| {g} | 0 | - | - | - | - |")
    L += ["", f"**플라시보 판정: {placebo.get('status')}** — {placebo.get('desc')}",
          "", "M-EXIT(기계적 철회)에서 유의한 음의 CAR 이 나오면 분해 실패이며, "
          "신호는 '커버리지 감소=소외주'의 재발견일 뿐이다(계약 명시)."]
    W("causal_decomposition.md", _md(L))

    # ── lead_lag_consensus.md ─────────────────────────────────────────────
    gr = ctx.get("granger_res")
    if gr is None or gr.get("status") == "UNTESTABLE":
        L = ["# H5 선행성 검정 — 검증 불가(UNTESTABLE)", "",
             "- 컨센서스 EPS 과거 이력 미확보. 매 실행 시 당월 스냅샷을 드라이브 "
             "공용 캐시에 축적 중이므로 시간이 지나면 검정 가능해진다.",
             "- 계약 §11: H5 미통과 시 독립 배분 금지(CONDITIONAL 상한)."]
    else:
        L = ["# H5 선행성 검정 — VAS ↔ 컨센서스 EPS 개정 (패널 그레인저)", "",
             f"- 표본: {gr.get('n')}행",
             f"- VAS→ΔEPS: χ²={gr.get('chi2_vas_to_eps'):.2f}, "
             f"p={gr.get('p_vas_to_eps'):.5f}, Σβ={gr.get('sum_beta_fwd'):.4f}",
             f"- ΔEPS→VAS(역): χ²={gr.get('chi2_eps_to_vas'):.2f}, "
             f"p={gr.get('p_eps_to_vas'):.5f}",
             f"- **선행성 판정: {'선행함(PASS)' if gr.get('leads') else '선행성 없음(FAIL)'}**",
             "", "H5 실패 시 이 신호는 컨센서스 개정의 느린 대리변수이며 독립적 "
             "가치가 없다(계약 §4)."]
    W("lead_lag_consensus.md", _md(L))

    # ── shrinkage_diagnostics.md ──────────────────────────────────────────
    sd = ctx.get("shrink_diag") or {}
    vd = ctx.get("vas_diag") or {}
    L = ["# 축소추정/통제회귀 진단", "",
         "## 경험적 베이즈 축소(§6.2 — 비축소 단독 보고 금지)"]
    L += [f"- {k}: {v}" for k, v in sd.items()]
    L += ["", "## §6.3 통제회귀"]
    L += [f"- {k}: {v}" for k, v in vd.items()]
    cf = ctx.get("ctrl_coef")
    if cf is not None:
        L += ["", "```", cf.round(5).to_string(index=False), "```"]
    W("shrinkage_diagnostics.md", _md(L))

    # ── cost_sensitivity.md ───────────────────────────────────────────────
    cs = ctx.get("cost_table")
    L = ["# 거래비용 민감도 (비용 0 / 기본 / 2배)", ""]
    if cs is not None:
        L += ["```", cs.round(4).to_string(), "```", ""]
    L += ["- 편도 수수료 1.5bp + 슬리피지(대형10/중형20/소형35bp) + 매도 증권거래세",
          "- 거래세 연도별 테이블(§7.1, 출처: 증권거래세법/기재부):"]
    for a, b, k1, k2 in CFG.TAX_TABLE:
        L.append(f"  - {a}~{b}: KOSPI합산 {k1*100:.2f}% / KOSDAQ {k2*100:.2f}%")
    W("cost_sensitivity.md", _md(L))

    # ── OPEN_QUESTIONS.md / FINAL_VERDICT.md / run_summary.json ───────────
    L = ["# OPEN_QUESTIONS — 애매 지점과 보수적 선택의 기록 (계약 명령)", ""]
    for t, b in OPEN_QUESTIONS_LOG:
        L += [f"## {t}", b, ""]
    W("OPEN_QUESTIONS.md", _md(L))

    v, why = ctx.get("verdict", ("N/A", "")), ctx.get("verdict_why", "")
    if isinstance(v, tuple):
        v, why = v
    gates = ctx.get("gates", {})
    L = ["# FINAL_VERDICT", "", f"## 판정: **{v}**", f"- 사유: {why}", "",
         "## 게이트 체크리스트 (계약 §11)"]
    L += [f"- {k}: {val}" for k, val in gates.items()]
    L += ["", f"- 백테스트 실구간: {ctx.get('bt_span')}",
          f"- 실행 모드: {CFG.RUN_MODE} / Phase0: {ctx.get('phase0_mode')}",
          f"- INTERIM 여부: {ctx['interim']} ({ctx.get('coverage_note', '')})"]
    W("FINAL_VERDICT.md", _md(L))

    try:
        atomic_write_json(out / "run_summary.json", ctx.get("run_summary", {}))
        publish_output(store, out / "run_summary.json", "실행 요약")
    except Exception:
        pass
    log.info(f"[S16] 산출물 {len(list(out.glob('*')))}개 기록 완료 → {out}")


def print_final_tables(ctx):
    """성과검증 - 강건성검사 - 기타해석표 3종을 로그(stdout)에 출력 (발주자 지시)."""
    log = ctx["log"]
    md = ctx.get("metrics_df")
    if md is not None and len(md):
        log.banner("표1", "성과검증표 — 12개 구성(net, 기본비용) + 벤치마크/나이브")
        log.table("성과검증표", md)
    log.banner("표2", "강건성검사표 — 부트스트랩/PBO/DSR/워크포워드/플라시보/비용")
    boot, pbo, dsr = ctx.get("boot", {}), ctx.get("pbo", {}), ctx.get("dsr", {})
    wf = (ctx.get("wf_info") or {}).get("metrics", {})
    def _num(x, fb):
        return fb if x is None or x != x else x
    rob = pd.DataFrame([
        {"검사": "블록 부트스트랩 P(SR≤0)", "값": boot.get("p_sr_le_0"),
         "기준": "낮을수록 강건",
         "판정": "OK" if _num(boot.get("p_sr_le_0"), 1) < 0.05 else "약함"},
        {"검사": "PBO (CSCV, 12구성)", "값": pbo.get("pbo"), "기준": "< 0.5",
         "판정": "PASS" if _num(pbo.get("pbo"), 1) < 0.5 else "FAIL"},
        {"검사": "DSR (시도 12회)", "값": dsr.get("dsr"), "기준": "> 0.5(>0)",
         "판정": "PASS" if _num(dsr.get("dsr"), 0) > 0.5 else "FAIL"},
        {"검사": "워크포워드 OOS Sharpe", "값": wf.get("Sharpe"), "기준": "> 0",
         "판정": "PASS" if _num(wf.get("Sharpe"), -1) > 0 else "FAIL"},
        {"검사": "M-EXIT 플라시보 |t60|", "값": ctx.get("placebo", {}).get("t60"),
         "기준": "< 2 (귀무 유지)", "판정": ctx.get("placebo", {}).get("status")},
        {"검사": "H1 NW t (Q5−Q1)", "값": ctx.get("hyp", {}).get("H1", {}).get("stat"),
         "기준": "≥ 2", "판정": ctx.get("hyp", {}).get("H1", {}).get("status")},
    ])
    log.table("강건성검사표", rob)
    cs = ctx.get("cost_table")
    if cs is not None:
        log.table("비용 민감도(주 구성)", cs.round(4))
    log.banner("표3", "기타해석표 — 가설/메커니즘/인과분해/판정")
    rows = []
    for k in ("H1", "H2", "H3", "H4", "H5"):
        h = ctx.get("hyp", {}).get(k, {})
        rows.append({"항목": k, "내용": HYPOTHESES[k][:44],
                     "상태": h.get("status"),
                     "통계량": round(h["stat"], 3) if isinstance(h.get("stat"), float)
                     and h.get("stat") == h.get("stat") else None})
    es = ctx.get("es_summary") or {}
    for g in ("V-DROP", "H-EXIT", "M-EXIT"):
        if g in es:
            rows.append({"항목": f"CAR60 {g}", "내용": f"n={es[g]['n']}",
                         "상태": f"{es[g]['car60']*100:.2f}%",
                         "통계량": round(es[g]["t60"], 2)})
    v = ctx.get("verdict")
    rows.append({"항목": "최종판정(§11)", "내용": ctx.get("verdict_why", "")[:44],
                 "상태": v, "통계량": None})
    log.table("기타해석표", pd.DataFrame(rows), max_rows=20)
    lin = ctx["store"].lineage_df()
    if len(lin):
        agg = (lin.groupby(["stage", "tier", "scope"], as_index=False)
               .agg(n_datasets=("dataset", "nunique"), rows=("rows", "sum")))
        log.table("데이터 계보/원장연결 점검표(다중소스)", agg, max_rows=40)
    if ctx.get("src_stats"):
        log.kv("소스별 사용 통계", ctx["src_stats"])


def save_plots(ctx):
    if not CFG.SAVE_PLOTS:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    out = Path(ctx["out_dir"])
    eq = ctx.get("equity_df")
    if eq is not None and len(eq):
        try:
            fig, ax = plt.subplots(figsize=(11, 5.5))
            for name, g in eq.groupby("series"):
                if name.startswith("cfg:") and "base" not in name:
                    continue
                ax.plot(pd.PeriodIndex(g["ym"], freq="M").to_timestamp(),
                        g["equity"], label=name[:28], lw=1.2)
            ax.legend(fontsize=7, ncol=2)
            ax.set_title("ARC-AAR equity curves (net)")
            ax.grid(alpha=0.3)
            fig.tight_layout()
            fig.savefig(out / "equity_curves.png", dpi=110)
            plt.close(fig)
        except Exception:
            pass
    car = ctx.get("car_df")
    if car is not None and len(car):
        try:
            fig, ax = plt.subplots(figsize=(9, 5))
            for g, gg in car.groupby("group"):
                ax.plot(gg["day"], gg["mean_car"] * 100, label=g, lw=1.5)
                ax.fill_between(gg["day"], (gg["mean_car"] - 2 * gg["se"]) * 100,
                                (gg["mean_car"] + 2 * gg["se"]) * 100, alpha=0.15)
            ax.axhline(0, color="k", lw=0.6)
            ax.set_xlabel("business days after signal")
            ax.set_ylabel("CAR (%)")
            ax.set_title("Coverage-exit event study (V/H/M)")
            ax.legend()
            ax.grid(alpha=0.3)
            fig.tight_layout()
            fig.savefig(out / "event_study_car.png", dpi=110)
            plt.close(fig)
        except Exception:
            pass
    for f in ("equity_curves.png", "event_study_car.png"):
        p = out / f
        if p.exists():
            publish_output(ctx["store"], p, f)


# ══════════════════════════════════════════════════════════════════════════════
# [S19] main() — 스테이지 오케스트레이터
# ══════════════════════════════════════════════════════════════════════════════

def main():
    avail = ensure_dependencies()
    quiet_noisy_libraries()
    local_root = resolve_project_root()
    log = RunLogger(local_root / "logs")
    log.banner("ARC-AAR", f"애널리스트 주의 재배분 백테스트 — 모드 {CFG.RUN_MODE} / "
                          f"{CFG.BT_START_MONTH}~{CFG.BT_END_MONTH}")
    _maybe_prompt_credentials(log)
    drive_root, how = mount_google_drive()
    store = CacheStore(local_root, drive_root, log)
    log.kv("환경", {"platform": sys.platform, "python": sys.version.split()[0],
                    "colab": _in_colab(), "notebook": _in_notebook(),
                    "project_root": str(local_root),
                    "google_drive": f"{drive_root} ({how})" if drive_root
                    else "✖ 미탐지",
                    "pandas": pd.__version__, "numpy": np.__version__})
    if drive_root is None:
        log.warn("구글 드라이브를 찾지 못했습니다. 신규 수집분은 로컬에 저장되고 "
                 "pending 큐에 적재되어 다음 실행에서 자동 동기화됩니다.")
        log.warn("지금 바로 드라이브에 저장하려면 파일 최상단 [S00] 의 "
                 "GDRIVE_ROOT 에 '내 드라이브' 폴더 경로를 붙여넣고 재실행하세요. "
                 r"(예: GDRIVE_ROOT = r'G:\내 드라이브')")
    if CFG.RUN_MODE == "FULL" and not avail.get("requests", False):
        watchdog_msg = ("FULL 모드에는 requests 가 필요합니다. "
                        "`pip install requests beautifulsoup4 lxml` 후 재실행하거나, "
                        "네트워크 없이 파이프라인만 점검하려면 "
                        "ARC_AAR_MODE=SYNTH 로 실행하세요.")
        log.error(watchdog_msg)
        raise RuntimeError(watchdog_msg)
    store.sync_pending_to_drive()
    store.discover_legacy_indexes()
    out_dir = local_root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = store.local_root / "state"
    quota = QuotaTracker(state_dir, log)
    watchdog = Watchdog(log)
    watchdog.start()                       # 이후 어떤 단계에서도 화면이 죽지 않는다
    stage_times, errors = {}, []
    ctx = {"store": store, "log": log, "out_dir": out_dir, "interim": False}

    def stage(sid, title, fn, critical=True):
        log.banner(sid, title)
        Progress.begin(f"[{sid}] {title}")     # 워치독이 이 단계를 방송한다
        t0 = time.time()
        try:
            r = fn()
            stage_times[sid] = round(time.time() - t0, 1)
            log.info(f"[{sid}] 완료 ({stage_times[sid]}s)")
            return r
        except SourceDown as e:
            stage_times[sid] = round(time.time() - t0, 1)
            log.warn(f"[{sid}] 소스 중단으로 부분 완료: {e}")
            if critical:
                # 필수 스테이지가 None 을 반환하면 하류에서 불가해한 언패킹 에러가
                # 난다. 여기서 명확히 끊는다(감사 지적 반영).
                errors.append({"stage": sid, "err": f"SourceDown: {e}"})
                raise RuntimeError(f"치명 스테이지 소스 중단: {sid}") from e
            return None
        except Exception as e:
            stage_times[sid] = round(time.time() - t0, 1)
            errors.append({"stage": sid, "err": str(e)[:300]})
            log.error(f"[{sid}] {title} 실패: {e}")
            for ln in traceback.format_exc(limit=8).splitlines()[-8:]:
                log._emit("      " + ln)
            if critical:
                raise RuntimeError(f"치명 스테이지 실패: {sid} — 로그 확인") from e
            return None

    # ── ST00: 카나리/수집기 준비 ───────────────────────────────────────────
    canary_res, blocked = {}, set()
    naver = hk = kofia_c = dart_c = cons_c = kind_c = None
    if CFG.RUN_MODE in ("FULL", "CANARY"):
        res = stage("ST00", "소스 도달성 카나리(차단 소스는 즉시 폴백 전환)",
                    lambda: canary_check(log, state_dir), critical=False)
        if res:
            canary_res, blocked = res
        if CFG.RUN_MODE == "CANARY":
            log.info("CANARY 모드 종료")
            watchdog.stop()
            return
        det_budget = RequestBudget("naver_detail", CFG.BUDGET_NAVER_DETAIL, log)
        pdf_budget = RequestBudget("naver_pdf", CFG.BUDGET_PDF, log)
        naver = NaverResearchCollector(store, log, quota, det_budget, pdf_budget,
                                       blocked="naver_research" in blocked)
        hk = HankyungConsensusCollector(store, log, quota,
                                        blocked="hankyung" in blocked)
        kofia_c = KofiaCollector(store, log, quota)
        dart_c = DartCollector(store, log, quota)
        cons_c = ConsensusEPSCollector(store, log, quota)
        kind_c = KindCollector(store, log, quota, blocked="kind" in blocked)
        if not DART_API_KEYS:
            log.warn("DART 키 미입력 — §6.3 통제변수(실적월/공시건수)가 축소됩니다. "
                     "https://opendart.fss.or.kr 에서 무료 발급 후 [S00] 에 입력하세요.")
    else:
        stage("ST00", "SYNTH 합성 세계 생성(자가검증)",
              lambda: synth_generate(store, log))

    months_meta = month_range(CFG.META_START_MONTH, CFG.BT_END_MONTH)
    COLLECT_BUDGET.start()

    # ── ST01: Phase 0 게이트 ───────────────────────────────────────────────
    gate = Phase0Gate(store, log, out_dir)
    had_prior = gate.prior_decision() is not None
    kofia_stub = kofia_c if kofia_c is not None else \
        type("K", (), {"try_fetch_registry": staticmethod(lambda: None)})()
    decision = stage("ST01", "Phase 0 데이터 실현가능성 게이트(§3)",
                     lambda: gate.run(naver, hk, kofia_stub, canary_res))
    ctx["phase0_mode"] = decision["mode"]
    if decision["mode"] == "ABORT":
        log.error("Phase 0 ABORT — 리포트 메타 확보 실패. PHASE0_DATA_FEASIBILITY.md "
                  "보고 후 중단(계약 §3).")
        return
    if not CFG.PHASE0_AUTO_CONTINUE and not had_prior and CFG.RUN_MODE == "FULL":
        log.info("Phase 0 보고 완료 — PHASE0_AUTO_CONTINUE=False 이므로 승인 대기 중단"
                 "(계약 §12-1). 재실행 시 이어서 진행.")
        return
    house_fb = decision["mode"] == "HOUSE_FALLBACK"
    ctx["house_fb"] = house_fb

    # ── ST02: PIT 유니버스 ────────────────────────────────────────────────
    hub = MarketDataHub(store, log, quota, blocked=blocked)
    uni = stage("ST02", "PIT 유니버스 월말 스냅샷(생존편향 제거)",
                lambda: build_pit_universe(hub, store, log, months_meta))
    if uni is None or not len(uni):
        raise RuntimeError("유니버스 구축 실패 — KRX/pykrx/FDR 모두 불가")
    # 상장폐지 이력: FDR 공개캐시(1 GET, 전체 이력) 우선, 실패 시 KIND 스크레이핑
    kind_df = hub.fdrc.delisting_history() if CFG.RUN_MODE == "FULL" else None
    if kind_df is None and kind_c is not None:
        kind_df = kind_c.delisted(months_meta[0], months_meta[-1])
    delist_ev = delist_events_from_universe(uni, months_meta, kind_df, log)
    log.info(f"[ST02] 유니버스 {uni['ym'].nunique()}개월 / "
             f"고유종목 {uni['ticker'].nunique()} / 상폐추론 {len(delist_ev)}종목")

    # ── 수집 우선순위 ─────────────────────────────────────────────────────
    #   리포트 리스트 → 통합 → **일별 가격** → 작성자 보조 → 보조 데이터.
    #   가격은 백테스트·이벤트스터디의 필수 입력이므로, 타임박스가 걸리더라도
    #   반드시 확보되도록 '개선 성격'의 단계(작성자 보강·DART·EPS)보다 앞에 둔다.
    #   (이전 순서에서는 가격이 맨 끝이라 타임박스가 걸리면 일별 가격이 통째로
    #    비어 INTERIM 결과가 사실상 쓸모없어졌다)
    # ── ST04: 리포트 리스트 수집 → 통합 ───────────────────────────────────
    if CFG.RUN_MODE == "FULL":
        stage("ST04", "리포트 리스트 수집(한경 주력 + 네이버 병행)",
              lambda: collect_all_reports(months_meta, naver, hk, store, log),
              critical=False)
    reports_all, ex = stage("ST04b", "리포트 메타 통합/식별자 부여",
                            lambda: merge_report_meta(months_meta, store, log))
    if reports_all is None or ex is None or not len(ex):
        raise RuntimeError("리포트 메타 없음 — 수집 실패 또는 캐시 부재")
    ctx["run_summary_reports"] = int(len(reports_all))
    covered = sorted(set(reports_all["ticker"]) & set(uni["ticker"]))

    # ── ST03: 일별 가격 (백테스트 필수 — 보조 단계보다 먼저) ──────────────
    end_px = min(datetime.now().strftime("%Y-%m-%d"),
                 str(month_end_date(CFG.BT_END_MONTH) + pd.Timedelta(days=40))[:10])
    mkt_map = dict(uni.sort_values("ym").groupby("ticker")["market"].last())
    if CFG.RUN_MODE == "FULL":
        stage("ST03", f"일별 수정주가 수집({len(covered)}종목, 증분+벌크)",
              lambda: hub.collect_prices(covered, CFG.PRICE_START, end_px, mkt_map),
              critical=False)

    # ── ST04a: 작성자 보조 확보(개선 성격) ────────────────────────────────
    if CFG.RUN_MODE == "FULL":
        stage("ST04a", "작성자 보조 확보(네이버 상세, 전역 예산제)",
              lambda: enrich_missing_analysts(months_meta, naver, store, log),
              critical=False)
        r2 = stage("ST04c", "작성자 보강분 재통합",
                   lambda: merge_report_meta(months_meta, store, log), critical=False)
        if r2 and r2[0] is not None and r2[1] is not None and len(r2[1]) > len(ex):
            reports_all, ex = r2
            log.info(f"[ST04c] 보강 반영 — 애널리스트 행 {len(ex)}")

    # ── ST05: 보조 데이터 ─────────────────────────────────────────────────
    sector_df = stage("ST05", "섹터/금투협/DART/컨센서스 보조 데이터",
                      lambda: hub.sector_map(), critical=False)
    sector_of = dict(zip(sector_df["ticker"], sector_df["sector"])) \
        if sector_df is not None and len(sector_df) else {}
    kofia_df = kofia_c.try_fetch_registry() if kofia_c is not None else None
    dart_frames = []
    def _dart_all():
        cmap = dart_c.corp_map() if dart_c is not None else {}
        Progress.begin("DART 월별 공시집계", total=len(months_meta))
        for ym in months_meta:
            if COLLECT_BUDGET.exceeded():
                log.warn("[ST05] 타임박스 — DART 수집 중단(수집분 사용)")
                break
            try:
                if dart_c is not None:
                    g = dart_c.monthly_disclosures(ym, cmap)
                else:
                    g = store.load_df("parsed", f"dart/{ym}.parquet", stage="ST05")
            except QuotaExhausted:
                log.warn("[ST05] DART 키 소진 — 수집분까지 사용(다음 실행에서 이어서)")
                break
            except Exception as e:
                log.warn(f"[ST05] DART {ym} 실패: {str(e)[:90]}")
                g = None
            if g is not None and len(g):
                dart_frames.append(g)
            Progress.tick(extra=ym)
        if dart_c is not None:
            log.kv("DART 호출량(관측 기반)", dart_c.quota_note())
        return len(dart_frames)
    stage("ST05b", "DART 공시/실적월(§6.3 통제변수)", _dart_all, critical=False)
    eps_hist = cons_c.load_history() if cons_c is not None else \
        store.load_df("parsed", "consensus/eps_monthly.parquet", stage="ST05")
    if CFG.RUN_MODE == "FULL" and cons_c is not None \
            and not COLLECT_BUDGET.exceeded():
        stage("ST05c", "컨센서스 EPS 당월 스냅샷 축적(전향 이력)",
              lambda: cons_c.snapshot_current(covered), critical=False)
    years = sorted({int(m[:4]) for m in months_meta})
    invr = None
    if CFG.RUN_MODE == "FULL":
        invr = stage("ST05d", "개인 매매비중(H4)",
                     lambda: hub.investor_ratio(covered, years), critical=False)
    ctx["invr_real"] = invr is not None

    # ── ST03b: 가격 행렬 적재 (수집은 ST03 에서 이미 완료) ────────────────
    close_wide = stage("ST03b", "통합 close 행렬 적재(캐시)",
                       lambda: hub.close_matrix(covered, log), critical=False)
    if close_wide is not None and len(close_wide.columns) < max(30, len(covered) * 0.1):
        log.warn("일별 가격 커버리지 10% 미만 — 월간 스냅샷 폴백 중심 INTERIM 결과")
    if close_wide is None:
        # 최후 폴백: 스냅샷 월간만으로 진행(이벤트 스터디 불가)
        cal = pd.bdate_range(CFG.PRICE_START, end_px)
        close_wide = pd.DataFrame(index=cal)
    entry_px, H, S, ft = month_anchor_frames(close_wide, uni, log) \
        if len(close_wide.columns) else (None, pd.DataFrame(),
                                         *_snap_only_frames(uni))
    ctx["interim"] = COLLECT_BUDGET.tripped

    # ── ST06: 패널 → 축소 → 통제회귀 → VAS ────────────────────────────────
    def _panel_all():
        panel, aw, pair_dense, adense = build_attention_panel(
            ex, log, house_fallback=house_fb, sector_map=sector_of)
        panel_sh, shrink_diag = apply_shrinkage(panel, sector_of, log)
        ctrl = build_ticker_month_controls(uni, dart_frames, log)
        vas_panel, coef, vas_diag = compute_vas(panel_sh, ctrl, log)
        return panel, aw, pair_dense, adense, vas_panel, coef, shrink_diag, vas_diag
    panel, aw, pair_dense, adense, vas_panel, ctrl_coef, shrink_diag, vas_diag = \
        stage("ST06", "주의 패널 + 축소추정 + §6.3 통제회귀 → VAS", _panel_all)
    ctx.update({"vas_panel": vas_panel, "ctrl_coef": ctrl_coef,
                "shrink_diag": shrink_diag, "vas_diag": vas_diag})

    # ── ST07: 철회 인과 분해 ──────────────────────────────────────────────
    person_month = ex[["analyst_person_id", "broker_norm", "ym"]].copy()
    last_data_m = int(ex["ym"].map(month_ord).max())
    exit_events, aar_neg, cov_count = stage(
        "ST07", "커버리지 철회 3군 분류(M/V/H)",
        lambda: classify_coverage_exits(pair_dense, adense, reports_all,
                                        person_month, kofia_df, log, last_data_m))
    ctx["exit_events"] = exit_events

    # ── ST08: 이벤트 스터디 (M-EXIT 플라시보 우선 — 계약 §12-6) ───────────
    car_df, es_summary = stage(
        "ST08", "이벤트 스터디 3군 CAR (플라시보 우선 실행)",
        lambda: event_study_car(exit_events, close_wide if
                                len(close_wide.columns) else None, ft, log),
        critical=False) or (None, {})
    ctx.update({"car_df": car_df, "es_summary": es_summary})
    if es_summary.get("M-EXIT", {}).get("t60") is not None:
        tm = es_summary["M-EXIT"]["t60"]
        if tm == tm and abs(tm) >= CFG.T_CRIT:
            log.warn("⚠⚠ M-EXIT 플라시보 위반 신호 — 계약상 이후 결과는 KILL 후보. "
                     "전체 증거 산출을 위해 파이프라인은 계속 진행한다.")

    # ── ST09: 신호 + 백테스트 12구성 × 비용 3종 + 벤치마크/나이브 ─────────
    def _bt_all():
        signals = build_stock_signals(vas_panel, aw, aar_neg, log)
        if signals is None or not len(signals):
            raise RuntimeError("신호 없음(VAS 계산 실패)")
        engine = BacktestEngine(signals, H, S, uni, log)
        grid = make_config_grid()
        res_by_scen = {}
        for scen, mult in CFG.COST_SCENARIOS.items():
            res_by_scen[scen] = {}
            for cfg_ in grid:
                keep = (scen == "base" and cfg_["name"] == PRIMARY_CFG["name"])
                res_by_scen[scen][cfg_["name"]] = engine.run(
                    cfg_, cost_mult=mult, keep_holdings=keep)
        # 벤치마크
        bench = {}
        members = {month_ord(k): set(v) for k, v in
                   uni.groupby("ym")["ticker"].apply(set).items()}
        ew_rows = {}
        for m in sorted(members):
            # 월 m 수익의 구성원은 '직전 월말(m-1) 유니버스' — PIT 편입 시점 일치
            prev = members.get(m - 1)
            if m in S.index and prev:
                cols = [t for t in prev if t in S.columns]
                if cols:
                    ew_rows[m] = float(S.loc[m, cols].mean())
        bench["EW_UNIVERSE"] = pd.Series(ew_rows).sort_index()
        for code, nm in (("KS11", "KOSPI"), ("KQ11", "KOSDAQ")):
            b = hub.benchmark_series(code, CFG.PRICE_START, end_px) \
                if CFG.RUN_MODE == "FULL" else None
            if b is not None and len(b):
                s = pd.Series(pd.to_numeric(b["close"], errors="coerce").to_numpy(),
                              index=pd.to_datetime(b["date"]))
                ent = {}
                for m, d in ft.items():
                    v = s.asof(d + pd.Timedelta(days=0))
                    ent[m] = float(v) if v == v else np.nan
                es_ = pd.Series(ent).sort_index()
                bench[nm] = (es_.shift(-1) / es_ - 1).dropna()
        # 나이브 리포트건수 신호
        nv = naive_report_count_signal(reports_all, log)
        nz = nv.copy()
        mu = nz.groupby("m")["naive"].transform("mean")
        sd = nz.groupby("m")["naive"].transform("std").replace(0, np.nan)
        nz["z"] = ((nz["naive"] - mu) / sd).fillna(0)
        sig_nv = nz.rename(columns={"z": "z_pos_ew"})
        for c in ("z_pos_npub", "z_pos_breadth"):
            sig_nv[c] = sig_nv["z_pos_ew"]
        sig_nv["z_neg"] = 0.0
        sig_nv["AAR_neg"] = 0.0
        eng_nv = BacktestEngine(sig_nv, H, S, uni, log)
        res_naive = eng_nv.run({"name": "NAIVE_repcount", "omega": "ew",
                                "lam": 0.0, "hold": 1}, cost_mult=1.0)
        return signals, engine, grid, res_by_scen, bench, res_naive
    signals, engine, grid, res_by_scen, bench, res_naive = stage(
        "ST09", "백테스트 12구성 + 벤치마크 + 나이브(통제가치 비교)", _bt_all)

    # ── ST10: 통계 검증 + 가설 판정 ───────────────────────────────────────
    def _stats_all():
        base = res_by_scen["base"]
        ts_map = {n: r["ts"].set_index("m")["ret_net"] for n, r in base.items()
                  if len(r["ts"])}
        prim = base[PRIMARY_CFG["name"]]
        prim_net = prim["ts"].set_index("m")["ret_net"] if len(prim["ts"]) \
            else pd.Series(dtype=float)
        # 부트스트랩(일별)
        dcurve = daily_curve_from_holdings(prim.get("holdings"),
                                           close_wide if len(close_wide.columns)
                                           else None, ft)
        boot = block_bootstrap_sharpe(dcurve) if dcurve is not None else \
            {"p_sr_le_0": np.nan, "sr_ci": (np.nan, np.nan)}
        pbo = cscv_pbo(pd.DataFrame(ts_map), log=log)
        srs_m = [s.mean() / s.std() for s in ts_map.values()
                 if len(s) > 12 and s.std() > 0]
        sr_sel = prim_net.mean() / prim_net.std() if len(prim_net) > 12 and \
            prim_net.std() > 0 else np.nan
        dsr = deflated_sharpe(sr_sel, srs_m, len(prim_net),
                              float(prim_net.skew()) if len(prim_net) > 12 else 0.0,
                              float(prim_net.kurt() + 3) if len(prim_net) > 12 else 3.0)
        wf_oos, wf_info = walk_forward(ts_map, log) if ts_map else (None, {})
        h2, h4 = h2_h4_series(engine, log, cov_count, invr)
        vas_tm = signals[["ticker", "m", "pos_ew"]]
        granger_res = granger_lead_lag(vas_tm, eps_hist, log)
        ipw_w, ipw_diag, ipw_recheck = None, None, None
        if decision["mode"] == "ANALYST_IPW" or decision.get("rate", 1) < 0.70:
            ipw_w, ipw_diag = ipw_sensitivity(reports_all, uni, log)
            ipw_recheck = ipw_h1_recheck(vas_panel, aar_neg, ipw_w, engine, log)
        hyp, placebo, fdr = evaluate_hypotheses(engine, grid, res_by_scen,
                                                es_summary, granger_res, h2, h4, log)
        # 초과수익(기본비용, EW 유니버스 대비 연율)
        ew = bench.get("EW_UNIVERSE", pd.Series(dtype=float))
        common = prim_net.index.intersection(ew.index)
        excess_pa = float((prim_net.reindex(common) - ew.reindex(common)).mean() * 12) \
            if len(common) > 12 else np.nan
        return (boot, pbo, dsr, wf_oos, wf_info, h2, h4, granger_res,
                ipw_diag, ipw_recheck, hyp, placebo, fdr, excess_pa, dcurve)
    (boot, pbo, dsr, wf_oos, wf_info, h2s, h4s, granger_res, ipw_diag,
     ipw_recheck, hyp, placebo, fdr, excess_pa, dcurve) = stage(
        "ST10", "통계 검증 게이트(§9 전항목) + 가설 판정", _stats_all)
    ctx.update({"boot": boot, "pbo": pbo, "dsr": dsr, "wf_info": wf_info,
                "granger_res": granger_res, "hyp": hyp, "placebo": placebo,
                "fdr": fdr, "ipw_recheck": ipw_recheck})

    verdict, why = final_verdict(hyp, placebo, pbo, dsr, excess_pa,
                                 ctx["interim"], log)
    ctx.update({"verdict": verdict, "verdict_why": why,
                "gates": {
                    "H1(BH-FDR후)": hyp["H1"]["status"],
                    "H2 기회비용": hyp["H2"]["status"],
                    "H3 인과분해": hyp["H3"]["status"],
                    "H5 선행성": hyp["H5"]["status"],
                    "M-EXIT 플라시보": placebo["status"],
                    "PBO<0.5": pbo.get("pbo"),
                    "DSR>0": dsr.get("dsr"),
                    "EW대비 초과(연)": f"{excess_pa*100:.2f}%p"
                    if excess_pa == excess_pa else "N/A"}})

    # ── ST11: 표/산출물 구성 ─────────────────────────────────────────────
    def _collect_outputs():
        rows, eq_rows, tr_frames = [], [], []
        for scen, mult in CFG.COST_SCENARIOS.items():
            for name, r in res_by_scen[scen].items():
                if not len(r["ts"]):
                    continue
                met = perf_metrics(r["ts"].set_index("m")["ret_net"])
                met.update({"config": name, "scenario": scen,
                            "avg_turnover": float(r["ts"]["turnover_1w"].mean()),
                            "avg_n_hold": float(r["ts"]["n_hold"].mean())})
                rows.append(met)
                if scen == "base":
                    eq = (1 + r["ts"].set_index("m")["ret_net"]).cumprod()
                    for m, v in eq.items():
                        eq_rows.append({"series": f"cfg:{name}|base",
                                        "ym": ord_to_ym(m), "equity": float(v),
                                        "ret": float(r["ts"].set_index("m")
                                                     ["ret_net"].loc[m])})
                    tr_frames.append(r["trades"])
        for nm, s in bench.items():
            met = perf_metrics(s)
            met.update({"config": f"BENCH:{nm}", "scenario": "-",
                        "avg_turnover": np.nan, "avg_n_hold": np.nan})
            rows.append(met)
            eq = (1 + s).cumprod()
            for m, v in eq.items():
                eq_rows.append({"series": f"BENCH:{nm}", "ym": ord_to_ym(m),
                                "equity": float(v), "ret": float(s.loc[m])})
        if res_naive is not None and len(res_naive["ts"]):
            s = res_naive["ts"].set_index("m")["ret_net"]
            met = perf_metrics(s)
            met.update({"config": "NAIVE:repcount", "scenario": "base",
                        "avg_turnover": float(res_naive["ts"]["turnover_1w"].mean()),
                        "avg_n_hold": float(res_naive["ts"]["n_hold"].mean())})
            rows.append(met)
            eq = (1 + s).cumprod()
            for m, v in eq.items():
                eq_rows.append({"series": "NAIVE:repcount", "ym": ord_to_ym(m),
                                "equity": float(v), "ret": float(s.loc[m])})
        if wf_oos is not None and len(wf_oos):
            eq = (1 + wf_oos).cumprod()
            for m, v in eq.items():
                eq_rows.append({"series": "WALKFORWARD_OOS", "ym": ord_to_ym(m),
                                "equity": float(v), "ret": float(wf_oos.loc[m])})
        met_df = pd.DataFrame(rows).set_index(["config", "scenario"]).round(4)
        cost_rows = {}
        for scen in CFG.COST_SCENARIOS:
            r = res_by_scen[scen].get(PRIMARY_CFG["name"])
            if r is not None and len(r["ts"]):
                cost_rows[scen] = perf_metrics(r["ts"].set_index("m")["ret_net"])
        cost_table = pd.DataFrame(cost_rows).T
        prim_ts = res_by_scen["base"][PRIMARY_CFG["name"]]["ts"]
        bt_span = f"{prim_ts['ym'].min()} ~ {prim_ts['ym'].max()}" \
            if len(prim_ts) else "N/A"
        # 연도별 수익률(§8 지표) — 전체 구성(base) + 벤치마크, 산출물로도 저장
        def _annual(s_ym):
            yr = pd.Series(s_ym.values, index=[str(y)[:4] for y in s_ym.index])
            return yr.groupby(level=0).apply(lambda x: float((1 + x).prod() - 1))
        ann_rows = []
        for name, r in res_by_scen["base"].items():
            if len(r["ts"]):
                for y, vv in _annual(r["ts"].set_index("ym")["ret_net"]).items():
                    ann_rows.append({"series": name, "year": y, "annual_ret": vv})
        for nm, s0 in bench.items():
            s_ym = pd.Series(s0.values, index=[ord_to_ym(m) for m in s0.index])
            for y, vv in _annual(s_ym).items():
                ann_rows.append({"series": f"BENCH:{nm}", "year": y,
                                 "annual_ret": vv})
        annual_df = pd.DataFrame(ann_rows)
        ann = None
        if len(prim_ts):
            s = prim_ts.set_index("ym")["ret_net"]
            ann = _annual(s)
        return (met_df, pd.DataFrame(eq_rows),
                pd.concat(tr_frames, ignore_index=True) if tr_frames else None,
                cost_table, bt_span, ann, annual_df)
    met_df, equity_df, trades_df, cost_table, bt_span, annual, annual_df = stage(
        "ST11", "성과/비용/에쿼티 표 구성", _collect_outputs)
    ctx.update({"metrics_df": met_df, "equity_df": equity_df,
                "trades_df": trades_df, "cost_table": cost_table,
                "bt_span": bt_span, "annual_df": annual_df})
    if annual is not None:
        log.table("주 구성 연도별 수익률(net, base)",
                  annual.to_frame("연수익률").round(4))
    # 사전등록 구간이 실제로 채워졌는지 명시 검증 — 조용한 절단 방지(감사 반영)
    if bt_span != "N/A":
        got_start, got_end = [x.strip() for x in bt_span.split("~")]
        short_head = month_ord(got_start) - month_ord(CFG.BT_START_MONTH)
        short_tail = month_ord(CFG.BT_END_MONTH) - month_ord(got_end)
        if short_head > 0 or short_tail > 0:
            ctx["interim"] = True
            msg = (f"사전등록 구간 {CFG.BT_START_MONTH}~{CFG.BT_END_MONTH} 대비 "
                   f"실제 {bt_span} (앞 {max(short_head,0)}개월 / 뒤 "
                   f"{max(short_tail,0)}개월 미충족)")
            log.warn(f"[ST11] {msg} — INTERIM 로 표기")
            open_questions_add("백테스트 구간 절단", msg +
                               ". 원인: 워밍업(룩백 12M + 통제창 24M) 구간의 리포트 "
                               "메타 미확보 또는 수집 타임박스. 재실행 시 자동 확장됨.")
        else:
            log.info(f"[ST11] 사전등록 10년 구간 충족: {bt_span}")

    # ── ST12: 비교전략(시총 하위 1000) ────────────────────────────────────
    stage("ST12", "비교전략 — 시가총액 하위 1000 압축 유니버스",
          lambda: run_small1000_comparison(signals, H, S, uni, grid, log,
                                           out_dir, store), critical=False)

    # ── ST13: 산출물 기록 + 표 출력 + 인덱스 저장 ─────────────────────────
    exp_months = len(months_meta)
    got_months = reports_all["ym"].nunique()
    ctx["coverage_note"] = f"리포트 메타 {got_months}/{exp_months}개월, " \
                           f"일별가격 {len(close_wide.columns)}/{len(covered)}종목"
    ctx["interim"] = bool(ctx["interim"] or got_months < exp_months * 0.95)
    ctx["src_stats"] = hub.src_stats
    ctx["run_summary"] = {
        "run_at": datetime.now().isoformat(), "mode": CFG.RUN_MODE,
        "phase0": decision, "interim": ctx["interim"],
        "coverage": ctx["coverage_note"], "bt_span": bt_span,
        "verdict": verdict, "verdict_why": why,
        "stage_times_s": stage_times, "errors": errors,
        "collect_budget": COLLECT_BUDGET.status(),
        "quota": quota.summary(),
        "request_budgets": ({"naver_detail_used": naver.detail_budget.used,
                             "naver_detail_limit": naver.detail_budget.limit,
                             "pdf_used": naver.pdf_budget.used}
                            if naver is not None else {}),
        "src_stats": hub.src_stats,
        "ipw_diag": ipw_diag, "ipw_recheck": ipw_recheck,
        "n_reports": int(len(reports_all)), "n_analyst_rows": int(len(ex)),
        "grid": [g["name"] for g in grid]}
    stage("ST13", "산출물 기록(§10) + 최종 표 출력",
          lambda: (write_all_outputs(ctx), save_plots(ctx),
                   print_final_tables(ctx)), critical=False)
    store.save_indexes()
    n_sync = store.sync_pending_to_drive()
    watchdog.stop()
    log.banner("완료", f"ARC-AAR 종료 — 판정 {verdict} / INTERIM={ctx['interim']} "
                       f"/ 산출물: {out_dir}")
    log.kv("마무리", {
        "드라이브 저장": (f"{store.drive_root}" if store.have_drive
                          else "미연결 — pending 큐 보관(다음 실행에서 동기화)"),
        "이번 실행 동기화": f"{n_sync}건",
        "수집 예산": COLLECT_BUDGET.status(),
        "재실행 시": "완료분은 스킵하고 미완료분만 이어서 수집합니다"})
    log.info("드라이브 공용·전용 인덱스는 append-only 로 보존됩니다(기존 항목 무손상).")
    return ctx


def _snap_only_frames(uni):
    """일별 가격 전무 시: 스냅샷 월간 수익률 + 인공 앵커(참고용 INTERIM)."""
    snap_c = uni.pivot_table(index="ym", columns="ticker", values="close",
                             aggfunc="last")
    snap_m = uni.pivot_table(index="ym", columns="ticker", values="mcap",
                             aggfunc="last")
    snap_c.index = [month_ord(x) for x in snap_c.index]
    snap_m.index = [month_ord(x) for x in snap_m.index]
    snap_c, snap_m = snap_c.sort_index(), snap_m.sort_index()
    S_raw = snap_c / snap_c.shift(1) - 1.0        # 라벨 규약: 월 m 중 실현 수익
    S_mc = snap_m / snap_m.shift(1) - 1.0
    S = S_raw.mask((S_raw < -0.35) & (S_mc > S_raw + 0.25), S_mc)
    ft = {m: month_end_date(ord_to_ym(m)) for m in S.index}
    return S, ft


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as _e:
        print(f"\n✖ 실행 중단: {_e}")
        sys.exit(1)
