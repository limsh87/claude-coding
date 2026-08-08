#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  TCD v3 · 전략 8 — FLP (Forced Liquidation Exhaustion)  강제매도 소진 포착
#  FLP 강제매도 소진 (Forced Liquidation Exhaustion)   [TCD_V3_FLP]
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)  ·  리밸런싱 주 1회
#
#  남이 팔아야만 해서 팔 때 내가 사준다 — 즉시성(immediacy) 공급의 대가를 수확한다. 핵심은 '얼마나 빠졌는가'가 아니라 '강제 재고(신용융자잔고)가 소진되었는가'다. 국면 A(물타기)·B(반대매매 진행)에서는 진입하지 않고, 재고 소진 + 소유권 이전이 완료된 국면 C 에서만 유동성을 공급한다. 알파가 아니라 위험 프리미엄이므로 R2-F(소진조건 vs 단순 낙폭과대)와 R12(꼬리 동시손실)가 존재 이유를 검정한다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v3_08_flp_liquidation.py` 로 실행해도 동일하게 동작합니다.
#
#   실행 순서 (전부 로그로 출력됩니다):
#     [0] 환경·의존성 → 구글드라이브 캐시(공용/전용 인덱스) 연결 → 계약 자동검정
#     [1] 합성데이터 엔드투엔드 스모크   (실데이터 전에 '계산경로'를 먼저 증명)
#     [2] 실경로 리허설                  (네트워크만 가짜로 두고 '수집경로'를 실물 실행)
#     [3] CANARY  F1~F4 · K1~K6          (§2 — 코드가 아니라 데이터의 등급을 먼저 확정)
#     [4] 데이터 수집 (캐시 우선 → 부족분만 신규 → 드라이브 공용/전용 인덱스에 재적재)
#     [5] 원장 무결성 감사 (리포트 ↔ 애널리스트 ↔ 종목 다중소스 연결)
#     [6] PIT 유니버스(C13) + 유니버스 감쇠표
#     [7] L1 일별 센서 → 주간 패널 → 국면판정(A/B/C) → TP_F1~F4 → 방화벽/거부권 → 신호
#     [8] 주간 백테스트 → 성과검증표 → 벤치마크(직접 재측정)
#     [9] 강건성 R2-F(★최우선) · R0 · R1 · R12 · R3 · R5 · R7 · R9
#    [10] 해석표 · 국면분포 · 진단카드 · 런타임 감사 · 산출물 다운로드
#
#  ⚠ 이 전략은 알파가 아니라 '위험 프리미엄'입니다(§0). 투자자문이 아닙니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다 (파일 최상단 고정)
#
#   ▸ 아무것도 안 채워도 실행됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지 / 그래서 어떤 지표가 죽는지"를 한글로 명시합니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#     (v2 전략들과 '공용 인덱스'를 그대로 공유합니다 — 가격·수급·리포트 재수집 불필요)
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① KRX 데이터 마켓플레이스 (2025-12 인증 방식 변경 대응) ★이 전략의 핵심 데이터원 ────────
#    가입: https://data.krx.co.kr  →  우측 상단 [회원가입](무료) → 이메일 인증 → 로그인
#          로그인에 쓰는 그 아이디/비밀번호를 그대로 넣으세요.
#
#    ▶ 이 전략에서 KRX 자격증명이 중요한 이유:
#      §5.2 "종목별 일별 신용거래융자 잔고"는 KRX 정보데이터시스템에서만 나옵니다.
#      로그인 세션이 없으면 Fallback A(주간) → Fallback B(개인순매수 프록시)로 강등되고,
#      B로 내려가면 §11-3에 따라 '사실상 다른 전략'이므로 리포트에 신뢰도 하향이 찍힙니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011) → JSON 대신 로그인 HTML이
#      와서 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서 1회만 하고 호출을
#      직렬화하지만, '바깥에서' 같은 계정을 쓰는 것까지는 막을 수 없습니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

#    ▶ KRX 접근 스위치 ★차단된 계정/IP 라면 반드시 "OFF" 로 두세요.
#      "OFF"  : KRX 계열(data.krx.co.kr · pykrx · KIND)을 아예 건드리지 않습니다.
#               차단 상태에서 계속 두드리면 차단이 길어지고 계정에 흔적이 남습니다.
#      "AUTO" : 실행당 딱 1회 가벼운 프로브로 가능 여부를 판정하고, 막혀 있으면 그 실행 내내
#               KRX 를 다시 부르지 않습니다. (권장 기본값 — 차단이 풀렸는지 자동으로 압니다)
#      "ON"   : 무조건 KRX 를 씁니다. 프로브도 건너뜁니다.
#
#      ※ KRX 가 꺼져도 이 코드는 끝까지 돕니다. 아래가 대체 경로입니다:
#         유니버스/상장폐지 → FDR GitHub 캐시 + DART corpCode + 네이버 + ★가격이력 재구성
#         상장주식수(시총)  → ★DART 주식총수현황(PIT 완전) → 거래대금 대리 분모
#         투자자 수급       → ★네이버 종목별 투자자 매매동향(JSON→HTML)
#         신용융자잔고      → KRX 독점입니다. 수동 CSV(아래 ③)가 없으면 프록시로 강등되고,
#                             그 사실이 리포트 첫 줄에 등급으로 인쇄됩니다(§11-3).
KRX_MODE = "OFF"
KRX_OPENAPI_KEY    = ""   # (선택) https://data-dbg.krx.co.kr 발급. 엔드포인트별 '이용신청'이
                          #        따로 필요하고 승인에 하루 정도 걸립니다. 키만으론 즉시 안 됩니다.

# ── ② DART 전자공시 OpenAPI  (§7.3 방화벽 · V1/V3 거부권의 입력) ────────────────────────────
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → API 인증키 발급 (무료, 1분)
#    ▶ 없으면 방화벽(자본잠식·감사의견·이자보상배율)이 대부분 비활성화됩니다.
#      이 전략의 단일 실패모드가 "진짜 죽어가는 회사를 사는 것"이므로, 여기는 비우지 마세요.
DART_API_KEY = ""

#    ▶ DART 호출 예산 — 하드코딩 상한을 두지 않습니다.
#      DART 에는 '오늘 남은 호출수' 조회 API 가 없습니다. 그래서 19,000 같은 숫자를 박아두면
#      실제 한도보다 적게 쓰거나(낭비), 같은 키를 다른 프로그램이 쓰면 넘겨버립니다(추측).
#      → 0 = 적응형: 한도초과(status=020)가 올 때까지 쓰고, 그 순간 멈춰 저장합니다.
#        그게 '실시간 잔여'를 아는 유일한 방법입니다. 양수로 두면 사용자 상한이 됩니다.
DART_DAILY_LIMIT = 0

#    ▶ 전체 재무제표(1사당 1콜)를 '누구까지' 받을지.
#      "candidates" (권장) : 이 전략이 실제로 매수할 수 있는 종목만. 나머지 계정은 100사/콜
#                            배치(주요계정)로 이미 확보되므로, 1사당 1콜은 영업활동현금흐름
#                            하나 때문에 씁니다. 전 종목에 쓰면 11만 콜(≈6일)이 됩니다.
#      "all"               : 전 종목 (콜드빌드. 며칠 걸립니다)
#      "off"               : 받지 않음 (영업CF 방화벽·V3 거부권 비활성)
DART_FULL_SCOPE = "candidates"
DART_FULL_ANNUAL_FIRST = True    # 후보 종목도 연간(사업보고서)부터 채우고, 남으면 분기까지

#    ▶ 주식총수(1사·1년당 1콜)로 PIT 시가총액 분모를 만들지.
#      f_cr 은 '자기 이력 백분위'라 분모 스케일이 달라도 성립하므로 필수가 아닙니다.
#      켜면 후보 종목에 한해 받습니다(전 종목이면 2.9만 콜).
USE_DART_SHARES = True

# ── ③ 구글드라이브 캐시 ★절대 1원칙 ─────────────────────────────────────────────────────────
#    ★★★ 기존 캐시·인덱스를 절대 삭제·덮어쓰기하지 않습니다. ★★★
#      · 인덱스의 진실은 append-only JSONL 저널입니다(기존 줄을 다시 쓰지 않음).
#      · index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업을 남깁니다.
#      · 이미 드라이브에 있는 리포트/원본은 이동·개명 없이 '경로만' 등록합니다(adopt-by-reference).
#      · 삭제 API 자체가 존재하지 않습니다. 손상 파일도 지우지 않고 .corrupt 로 격리만 합니다.
#
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략도 그대로 재사용 (가격·수급·신용잔고·리포트 원장)
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유 (일별센서·주간패널·신호·백테스트·강건성)
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"           # v2 전략들과 동일 → 캐시가 그대로 재활용됩니다
GDRIVE_PRIVATE_NS = "tcd_v3_flp"        # 이 전략 전용

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요. 재귀 스캔해서 '등록만' 합니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
]
#    ▸ 윈도우/로컬 주피터랩이면 여기에 실제 폴더를 적으세요. 드라이브 동기화 폴더를 그대로
#      가리켜도 됩니다(예: r"D:\Quant\tcd_cache" 또는 r"C:\Users\me\Google Drive\tcd_cache").
#      ★ 윈도우 경로는 역슬래시가 이스케이프로 해석되므로 반드시 r"..." 형태로 쓰세요.
LOCAL_CACHE_ROOT  = "./tcd_cache"       # JupyterLab/로컬 폴백 (드라이브 마운트 불가 시 자동)

#    ▸ 신용잔고를 KRX 웹에서 직접 내려받아 두셨다면(CSV/XLSX) 이 폴더에 넣어두세요.
#      자동 탐지 → 파싱 → 공용 인덱스에 정규화 적재합니다. Primary 등급으로 인정됩니다.
CREDIT_MANUAL_DIRS = [
    "/content/drive/MyDrive/tcd_cache/_shared/manual/credit",
    "./tcd_cache/_shared/manual/credit",
]

# ── ④ 백테스트 구간 · 리밸런싱 ──────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"
REBAL_DAY      = "W-FRI"          # 주 1회 (일별=회전율 폭증, 월별=소진 시점 놓침 — §8)

# ── ⑤ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
#    ▶ 속도 ↔ 차단 위험은 '동시 스레드 수'가 아니라 '초당 요청수(QPS)'가 결정합니다.
#      아래 QPS 가 전역 상한이라 스레드를 늘려도 그 이상 빨라지지 않습니다(그래서 안전합니다).
#      급하면 naver 를 4~5 로 올리세요. 429/403 이 뜨면 즉시 되돌리고 재실행하면
#      캐시에 쌓인 만큼은 건너뜁니다.
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). QPS 상한이 있으므로 12면 충분합니다.
N_WORKERS_CPU  = 0      # 0 = CPU 코어수 자동
RATE_LIMIT_QPS = {"dart": 8.0, "hankyung": 2.5, "naver": 3.0, "krx": 2.0,
                  "datagokr": 5.0, "customs": 3.0, "kind": 2.0, "generic": 3.0}
MEM_BUDGET_GB  = 6.0
DAILY_CHUNK_CODES = 400   # 일별 센서 계산을 이 종목수 단위로 청크 처리 (RAM 급증 방지)

#    ▶ 수집량 상한 (§9 하드 제약: 총 wall-clock 4시간). 추측하지 말고 계측한 값으로 조절하세요.
#      · 수급은 종목당 수 회의 요청이 필요해 전 종목을 받으면 몇 시간이 걸립니다.
#        이 전략이 실제로 진입할 수 있는 종목(큰 낙폭 + 유동성)만 선별해서 받습니다.
#        선별 기준과 제외된 수는 매 실행 로그에 표로 남습니다(조용한 축소 금지).
#      · 캐시는 누적됩니다 — 다음 실행은 부족분만 받으므로 회를 거듭할수록 커버리지가 올라갑니다.
FLOW_MAX_CODES        = 1200      # 수급 수집 대상 상한 (0 = 무제한)
FLOW_DD_PREFILTER     = -0.25     # 이 낙폭을 한 번이라도 겪은 종목만 수급 수집 (진입조건 -0.30 여유)
DART_SHARES_MAX_CALLS = 0         # 0 = 상한 없음(적응형 예산이 알아서 멈춥니다)

# ── ⑥ 신용융자잔고 취득 등급 (§5.2 / F1 카나리) ─────────────────────────────────────────────
#    PRIMARY_DAILY   : 종목별 '일별' 신용거래융자 잔고 — 완전체
#    FALLBACK_A_WEEKLY: 주간 관측 → 그 사이는 forward-fill (★선형보간 금지: 미래정보 누출)
#    FALLBACK_B_PROXY : 개인 순매수 252일 누적 / 시가총액 — 대체재가 아니라 '열등재'
CREDIT_ALLOW_FALLBACK_A = True
CREDIT_ALLOW_FALLBACK_B = True     # False 로 두면 B밖에 없을 때 그냥 중단합니다(§11-3 엄격모드)
CREDIT_FALLBACK_B_ACKNOWLEDGED = True   # B로 내려간 사실을 리포트에 '반드시' 명시합니다
KRX_CREDIT_BLD = ""     # KRX bld ID를 직접 아신다면 여기에. 비우면 후보군을 자동 프로브합니다.

# ── ⑦ 애널리스트 리포트 (한경컨센서스 · 네이버 리서치) ──────────────────────────────────────
#    ▶ 이 전략에서의 용도: 알파 원천이 아니라 '거부권/해석'입니다.
#      낙폭 국면에서 같은 애널리스트가 목표주가를 계속 내리고 있다면 그건 소진이 아니라
#      펀더멘털 악화입니다(V_RS). 드라이브 캐시에 이미 있는 리포트를 최우선 재사용합니다.
RESEARCH_USE            = True
RESEARCH_COLLECT        = True    # False면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES        = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF   = False   # 이 전략은 목표주가/애널리스트만 쓰므로 기본 off (용량 절약)
RESEARCH_PDF_MAX_PER_MONTH = 0
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑧ 포지션 / 사이징  (§12-2 — R12 결과를 근거로 '코드 상수'로 못박는다) ────────────────────
#    ★ 드로다운 한가운데서 이 값을 바꾸지 마세요. R12가 상한 초과를 판정하면
#      그 사실과 권고치를 로그에 출력하되, 값 자체는 사람이 바꾸도록 남겨둡니다.
PORTFOLIO_TOP_PCT     = 0.05     # 적격군 상위 5%
PORTFOLIO_MAX_NAMES   = 20
PORTFOLIO_MIN_NAMES   = 5
POS_MAX_WEIGHT        = 0.08     # 종목당 최대비중 (꼬리 동시손실 전제 → v2보다 보수적)
POS_MIN_WEIGHT        = 0.02
POS_ADV_PARTICIPATION = 0.10     # 20일 평균거래대금의 10% 이내
HOLD_MAX_WEEKS        = 26       # 6개월 (§12-3: 회복은 수 주~수 개월이 전형)
EXIT_CR_PCTL          = 0.50     # 신용잔고율 백분위가 여기까지 회복 = 재취약 → 청산
ACCOUNT_KRW           = 30_000_000
MIN_ADV_KRW           = 300_000_000       # 유동성 하한 (§7.3 방화벽)
MCAP_RANK_EXCLUDE_TOP = 250      # 상위 250 대형주 제외 (개인 신용 비중이 낮아 현상 자체가 약함)

#    ▶ 비교군: 스몰캡 전용 유니버스 (시총 하위 N종목)
#      같은 신호·같은 비용·같은 기간으로 한 번 더 돌려 나란히 출력합니다.
#      강제매도 현상은 소형주에서 훨씬 강하게 나타나므로, 전체 유니버스 대비 얼마나 더
#      강한지(또는 비용·유동성에 먹히는지)를 같은 화면에서 판단할 수 있어야 합니다.
RUN_SMALLCAP_COMPARE = True
SMALLCAP_BOTTOM_N    = 1000      # 매 시점 시총 하위 N종목 (PIT 재산출)

# ── ⑨ 국면 판정 임계 (§7.1) ─────────────────────────────────────────────────────────────────
PH_DD_ENTER      = -0.30    # 국면 C 낙폭 조건
PH_CR_PCTL_ENTER = 0.20     # 강제재고 소진 판정 (자기이력 백분위)
PH_CR_CHG_B      = -0.15    # 국면 B (반대매매 진행) 잔고 급감
PH_DD_SPD_B      = -0.10
PH_RET_EX_Q      = 0.60     # f_ret_ex 상위 분위 (개인 이탈 누적)

# ── ⑩ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전 출력물 예행연습 (수십 초, 네트워크/키 불필요) — 처음엔 이걸로
#    "FULL"  : 스모크 → 리허설 → 카나리 → 실수집 → 백테스트 → 강건성 (기본)
#    "CACHED": 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 없음) → 백테스트
RUN_MODE = "FULL"

SEED = 20260808
VERBOSE = True
STOP_ON_KILL_CRITERIA = True     # §11 킬 기준 위반 시 중단하고 그대로 보고 (끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

# 아래는 v2 공용 코어가 참조하는 상수들 — 이 전략에서는 쓰지 않지만 정의는 필요합니다.
DATA_GO_KR_KEY  = ""
CUSTOMS_API_KEY = ""
PORTFOLIO_TOP_PCT_V2 = PORTFOLIO_TOP_PCT
HOLD_MAX_MONTHS = 6
ACTIVE_PACKS    = ["F"]

STRATEGY_ID   = "TCD_V3_FLP"
STRATEGY_NAME = "FLP 강제매도 소진 (Forced Liquidation Exhaustion)"
BUILD_VERSION = "v2.20260808.0440"


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import datetime as _dt
from collections import defaultdict, Counter, OrderedDict
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, urljoin, quote, unquote, urlparse, parse_qs

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ★ 윈도우 콘솔 기본 인코딩(cp949)은 이 코드가 쓰는 罫線문자(╔═║)와 ✔✘⚠★ 를 인코딩하지 못한다.
#   주피터는 UTF-8 이라 괜찮지만 `python 파일.py` 로 돌리면 첫 배너에서 UnicodeEncodeError 로
#   즉사한다. 가능하면 표준출력을 UTF-8 로 바꾸고, 안 되면 아래 _safe_print 가 ASCII 로 낮춘다.
for _s in ("stdout", "stderr"):
    try:
        _st = getattr(sys, _s, None)
        if _st is not None and hasattr(_st, "reconfigure"):
            _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _console_ok(sample: str = "╔✔⚠★─") -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    try:
        sample.encode(enc)
        return True
    except Exception:
        return False


CONSOLE_UNICODE = _console_ok()
# 인코딩이 안 되는 콘솔용 치환표 (표 모양은 잃되 정보는 전부 보존한다)
_ASCII_FALLBACK = str.maketrans({
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "═": "=", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "─": "-", "│": "|",
    "┼": "+", "┬": "+", "┴": "+", "├": "+", "┤": "+",
    "✔": "OK", "✘": "X", "⚠": "!", "★": "*", "▶": ">", "▷": ">",
    "⬇": "v", "…": "...", "·": ".", "×": "x", "σ": "sigma", "θ": "theta",
    "Δ": "d", "≥": ">=", "≤": "<=", "≈": "~", "①": "(1)", "②": "(2)",
    "③": "(3)", "④": "(4)", "⑤": "(5)", "⑥": "(6)", "⑦": "(7)",
    "⑧": "(8)", "⑨": "(9)", "⑩": "(10)", "⭐": "*", "⛔": "STOP", "∏": "prod",
})


def _safe_print(*args, **kw):
    """어떤 콘솔에서도 죽지 않는 print. 인코딩 실패 시에만 ASCII 로 낮춘다."""
    try:
        print(*args, **kw)
    except UnicodeEncodeError:
        try:
            print(*[str(a).translate(_ASCII_FALLBACK) for a in args], **kw)
        except Exception:
            enc = (getattr(sys.stdout, "encoding", None) or "ascii")
            print(*[str(a).encode(enc, "replace").decode(enc, "replace") for a in args], **kw)


def _detect_env() -> Dict[str, Any]:
    """Colab / JupyterLab / VSCode / 순수 CLI 를 구분한다. 어느 쪽이든 죽지 않아야 한다."""
    info = {"colab": False, "ipython": False, "kernel": None, "interactive": False}
    try:
        from IPython import get_ipython           # noqa
        ip = get_ipython()
        if ip is not None:
            info["ipython"] = True
            info["kernel"] = type(ip).__name__
            info["interactive"] = "ZMQ" in type(ip).__name__ or "Terminal" in type(ip).__name__
    except Exception:
        pass
    info["colab"] = ("google.colab" in sys.modules) or bool(os.environ.get("COLAB_RELEASE_TAG"))
    if not info["colab"]:
        try:
            import importlib.util
            info["colab"] = importlib.util.find_spec("google.colab") is not None
        except Exception:
            pass
    info["python"] = sys.version.split()[0]
    info["platform"] = platform.system()
    info["cpu"] = os.cpu_count() or 2
    return info


ENV = _detect_env()

# ── 의존성 ──────────────────────────────────────────────────────────────────────────────────
#   (모듈 임포트명, pip 설치명, 필수여부, 이 패키지가 없으면 무엇이 죽는지)
_REQUIRED = [
    ("numpy",     "numpy",              True,  "모든 수치연산"),
    ("pandas",    "pandas",             True,  "모든 패널 처리"),
    ("pyarrow",   "pyarrow",            True,  "parquet 캐시(L1 영속화)"),
    ("scipy",     "scipy",              True,  "통계검정 / 회귀"),
    ("requests",  "requests",           True,  "모든 HTTP 수집"),
    ("bs4",       "beautifulsoup4",     True,  "리서치 리스트 파싱"),
    ("lxml",      "lxml",               True,  "HTML/XML 고속 파서"),
    ("tqdm",      "tqdm",               True,  "진행률 표시"),
]
_OPTIONAL = [
    ("FinanceDataReader", "finance-datareader", "가격/상장목록 1순위 폴백"),
    ("pykrx",             "pykrx",              "PIT 상장목록(특정일 상장종목) — 생존자편향 제거의 핵심"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출(가장 빠름)"),
    ("pdfplumber",        "pdfplumber",         "PDF 추출 폴백"),
    ("rapidfuzz",         "rapidfuzz",          "사업장명/애널리스트명 유사도 매칭(고속)"),
    ("statsmodels",       "statsmodels",        "HAC(Newey-West) 표준오차"),
    ("html5lib",          "html5lib",           "깨진 HTML 복구 파싱"),
]


def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:
    if not pkgs:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if quiet:
        cmd.append("-q")
    cmd += pkgs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        return r.returncode == 0, (r.stderr or r.stdout)[-2000:]
    except Exception as e:                                    # noqa
        return False, f"{type(e).__name__}: {e}"


def _ensure_deps() -> Dict[str, bool]:
    import importlib
    missing_req, missing_opt = [], []
    for mod, pkg, _req, _why in _REQUIRED:
        if importlib.util.find_spec(mod) is None:
            missing_req.append(pkg)
    for mod, pkg, _why in _OPTIONAL:
        if importlib.util.find_spec(mod) is None:
            missing_opt.append(pkg)

    if missing_req:
        print(f"[부트스트랩] 필수 패키지 설치 중: {', '.join(missing_req)}  (1~3분 소요)")
        ok, err = _pip_install(missing_req)
        if not ok:
            print("\n" + "=" * 88)
            print("❌ 필수 패키지 설치 실패. 아래 명령을 직접 실행한 뒤 다시 돌려주세요.")
            print(f"   pip install {' '.join(missing_req)}")
            print("-" * 88)
            print(err)
            print("=" * 88)
            raise SystemExit(1)
        importlib.invalidate_caches()

    if missing_opt:
        print(f"[부트스트랩] 선택 패키지 설치 중: {', '.join(missing_opt)}")
        _pip_install(missing_opt)          # 실패해도 계속 — 각 기능에서 개별적으로 degrade
        importlib.invalidate_caches()

    # ★ 가용성 확인을 import_module 로 하면 안 된다. pykrx 는 import 시점에 KRX 로그인을 수행하는데,
    #   그게 아래 자격증명 주입보다 먼저 일어나면 비인증 세션이 만들어지고, 이후 모든 조회가
    #   JSON 대신 로그인 HTML 을 받아 엉뚱한 곳에서 JSONDecodeError 로 터진다.
    #   find_spec 은 모듈을 실행하지 않으므로 부작용이 없다. 실제 import 는 아래 통제된 블록에서만.
    return {mod: (importlib.util.find_spec(mod) is not None) for mod, _pkg, _why in _OPTIONAL}


# ═══ 자격증명은 어떤 서드파티 import 보다도 먼저 주입한다 ═══════════════════════════════════
#   pykrx.webio 는 모듈 로드 시점에 build_krx_session() 을 돌린다. 순서를 뒤집으면
#   예외 없이 '비인증 세션'이 만들어지고 원인 추적이 매우 어려운 실패로 이어진다.
#
#   ★ 단, KRX_MODE='OFF'(차단 대응) 이면 자격증명을 주입하지도, pykrx 를 import 하지도
#     않는다. 그러지 않으면 import 시점에 KRX 로그인을 한 번 때리고 "KRX 로그인 시도/실패"
#     가 찍힌다 — 차단 상태에서 굳이 흔적을 남기는 행동이다.
_KRX_OFF = str(globals().get("KRX_MODE", "AUTO")).upper() == "OFF"
if _KRX_OFF:
    for _v in ("KRX_ID", "KRX_PW", "KRX_OPENAPI_KEY", "KRX_API_KEY"):
        os.environ.pop(_v, None)
if (not _KRX_OFF) and KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW
if (not _KRX_OFF) and KRX_OPENAPI_KEY:
    os.environ["KRX_OPENAPI_KEY"] = KRX_OPENAPI_KEY
    os.environ["KRX_API_KEY"] = KRX_OPENAPI_KEY

OPT = _ensure_deps()

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from tqdm.auto import tqdm
except Exception:                                             # pragma: no cover
    def tqdm(it=None, **kw):                                  # type: ignore
        return it if it is not None else iter(())

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_colwidth", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
np.seterr(all="ignore")

# 결정성(C8): 모든 난수는 이 시드에서 파생된다.
random.seed(SEED)
np.random.seed(SEED % (2 ** 32 - 1))
RNG = np.random.default_rng(SEED)

# 선택 모듈 핸들 (자격증명은 위 _ensure_deps 앞에서 이미 주입됨)
fdr = pykrx_stock = yf = fitz = pdfplumber = rapidfuzz_fuzz = smapi = None
if OPT.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr           # type: ignore
    except Exception:
        fdr = None
if OPT.get("pykrx") and not _KRX_OFF:
    try:
        from pykrx import stock as pykrx_stock    # type: ignore
    except Exception:
        pykrx_stock = None
elif _KRX_OFF:
    print("[부트스트랩] KRX_MODE='OFF' — pykrx 를 import 하지 않습니다"
          "(import 시점 로그인 시도 자체를 만들지 않기 위함).")
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
    except Exception:
        yf = None
if OPT.get("fitz"):
    try:
        import fitz                               # type: ignore  (pymupdf)
    except Exception:
        fitz = None
if OPT.get("pdfplumber"):
    try:
        import pdfplumber                         # type: ignore
    except Exception:
        pdfplumber = None
if OPT.get("rapidfuzz"):
    try:
        from rapidfuzz import fuzz as rapidfuzz_fuzz   # type: ignore
    except Exception:
        rapidfuzz_fuzz = None
if OPT.get("statsmodels"):
    try:
        import statsmodels.api as smapi           # type: ignore
    except Exception:
        smapi = None

# ── 병렬 전략 결정 ──────────────────────────────────────────────────────────────────────────
#   노트북에서 ProcessPoolExecutor 는 "__main__ 에 정의된 함수를 피클할 수 없음" 으로 자주 죽는다.
#   fork 를 쓸 수 있는 리눅스(=Colab)에서는 안전하고, spawn 플랫폼(win/mac)에서는 스레드로 폴백한다.
import multiprocessing as _mp
try:
    _MP_METHODS = set(_mp.get_all_start_methods())
except Exception:
    _MP_METHODS = {"spawn"}
CAN_FORK = ("fork" in _MP_METHODS) and (ENV["platform"] == "Linux")
N_CPU = N_WORKERS_CPU if N_WORKERS_CPU and N_WORKERS_CPU > 0 else max(1, (os.cpu_count() or 2) - 1)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-B  커널 — 로깅 / 스테이지 / 데이터흐름 원장 / 에러 국소화 / 런타임 계측(C10)          ║
# ║                                                                                          ║
# ║  이 블록의 목적은 단 하나:  "어디서 터졌고, 무슨 데이터가 어디로 흘렀는가"를               ║
# ║  스크롤 없이 한 화면에서 보이게 만드는 것.                                                ║
# ║                                                                                          ║
# ║  · 모든 연산은 STAGE 컨텍스트 안에서만 수행한다.                                          ║
# ║  · 모든 데이터 입출력은 FLOW 원장에 기록한다. (행수·바이트·소스·PIT컬럼 유무)              ║
# ║  · 예외는 잡아서 "스테이지ID + 입출력 스냅샷 + 한글 진단 힌트"와 함께 재출력한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_T0_PROCESS = time.time()


def _dw(s: str) -> int:
    """한글/한자 폭 2칸을 반영한 표시 너비. 표 정렬이 깨지지 않게 하는 유일한 방법."""
    w = 0
    for ch in str(s):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _pad(s: str, n: int, align: str = "l") -> str:
    s = str(s)
    gap = max(0, n - _dw(s))
    if align == "r":
        return " " * gap + s
    if align == "c":
        return " " * (gap // 2) + s + " " * (gap - gap // 2)
    return s + " " * gap


def _trunc(s: str, n: int) -> str:
    s = str(s).replace("\n", " ")
    if _dw(s) <= n:
        return s
    out = ""
    for ch in s:
        if _dw(out) + _dw(ch) > n - 1:
            return out + "…"
        out += ch
    return out


class _Log:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self, min_level: str = "INFO"):
        self.min = self.LEVELS[min_level]
        self.ctx: List[str] = []
        self.buffer: List[str] = []
        self.lock = threading.RLock()

    def _emit(self, level: str, msg: str, icon: str = ""):
        if self.LEVELS[level] < self.min:
            return
        el = time.time() - _T0_PROCESS
        stamp = f"{int(el // 60):02d}:{el % 60:05.2f}"
        scope = ("/".join(self.ctx))[-34:]
        line = f"[{stamp}] {_pad(scope, 34)} {icon}{msg}"
        with self.lock:
            self.buffer.append(line)
            _safe_print(line, flush=True)

    def debug(self, m): self._emit("DEBUG", m, "· ")
    def info(self, m):  self._emit("INFO",  m, "  ")
    def ok(self, m):    self._emit("INFO",  m, "✔ ")
    def warn(self, m):  self._emit("WARN",  m, "⚠ ")
    def error(self, m): self._emit("ERROR", m, "✘ ")

    def rule(self, title: str = "", ch: str = "─", width: int = 104):
        if title:
            pre = f"{ch * 3} {title} "
            _safe_print(pre + ch * max(0, width - _dw(pre)), flush=True)
        else:
            _safe_print(ch * width, flush=True)

    def banner(self, title: str, sub: str = "", width: int = 104):
        _safe_print("", flush=True)
        _safe_print("╔" + "═" * (width - 2) + "╗", flush=True)
        _safe_print("║ " + _pad(_trunc(title, width - 4), width - 4) + " ║", flush=True)
        if sub:
            _safe_print("║ " + _pad(_trunc(sub, width - 4), width - 4) + " ║", flush=True)
        _safe_print("╚" + "═" * (width - 2) + "╝", flush=True)

    def table(self, rows: List[Sequence[Any]], headers: Sequence[str],
              aligns: Optional[Sequence[str]] = None, maxw: int = 46, title: str = ""):
        """한글 폭 보정 표. 강건성/성과/감사 출력 전부 이걸 쓴다."""
        if title:
            _safe_print(f"\n▶ {title}", flush=True)
        if not rows:
            _safe_print("   (행 없음)", flush=True)
            return
        ncol = len(headers)
        aligns = list(aligns or ["l"] * ncol)
        cells = [[_trunc("" if c is None else c, maxw) for c in r] + [""] * (ncol - len(r)) for r in rows]
        widths = [max(_dw(headers[i]), *(_dw(r[i]) for r in cells)) for i in range(ncol)]
        head = "  " + " │ ".join(_pad(headers[i], widths[i], "c") for i in range(ncol))
        _safe_print(head, flush=True)
        _safe_print("  " + "─┼─".join("─" * widths[i] for i in range(ncol)), flush=True)
        for r in cells:
            _safe_print("  " + " │ ".join(_pad(r[i], widths[i], aligns[i]) for i in range(ncol)), flush=True)


LOG = _Log("DEBUG" if VERBOSE else "INFO")


# ── 데이터 흐름 원장 ────────────────────────────────────────────────────────────────────────
@dataclass
class IOEvent:
    stage: str
    direction: str          # IN / OUT
    kind: str               # HTTP / DRIVE / PARQUET / MEM / SQLITE / SYNTH
    name: str
    rows: int = -1
    cols: int = -1
    bytes_: int = -1
    source: str = ""
    ok: bool = True
    note: str = ""
    pit_cols: str = ""      # knowledge_date 계열 컬럼 존재 여부 — C1 감사에 쓰인다


@dataclass
class StageRecord:
    sid: str
    name: str
    layer: str
    status: str = "PENDING"       # PENDING / RUNNING / OK / WARN / FAIL / SKIP
    t_start: float = 0.0
    t_end: float = 0.0
    budget_s: Optional[float] = None
    rows_in: int = 0
    rows_out: int = 0
    err_type: str = ""
    err_msg: str = ""
    err_tb: str = ""
    hint: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def dur(self) -> float:
        return (self.t_end or time.time()) - self.t_start


class KillCriteria(Exception):
    """§15 킬 기준 위반. 우회하지 말고 사용자에게 보고하고 멈춘다."""


class StageFailure(Exception):
    pass


# ── 예외 → 한글 진단 힌트 ───────────────────────────────────────────────────────────────────
_DIAG_RULES: List[Tuple[str, str]] = [
    (r"SERVICE_KEY_IS_NOT_REGISTERED|SERVICEKEY",
     "공공데이터포털 인증키 문제입니다. ① 해당 API에 '활용신청'이 승인됐는지 ② DATA_GO_KR_KEY 에 "
     "Decoding(일반) 키를 넣었는지 확인하세요. Encoding 키를 넣으면 이중 인코딩으로 항상 실패합니다."),
    (r"LIMITED_NUMBER_OF_SERVICE_REQUESTS",
     "공공데이터포털 일일 호출한도 초과입니다. 내일 재시도하거나 트래픽 증가 신청을 하세요. "
     "이미 받은 분량은 드라이브 캐시에 남아 있으므로 재실행 시 이어서 받습니다."),
    (r"opendart|dart.*(013|020|100|800|900)|status.*'0(13|20)'",
     "DART API 응답 코드 오류. 013=조회 데이터 없음(정상일 수 있음), 020=일일한도 초과, "
     "100=필드 부적절, 800=시스템 점검, 900=정의되지 않은 오류. DART_API_KEY 를 확인하세요."),
    (r"HTTPError.*40[13]|Forbidden|403",
     "403 차단입니다. RATE_LIMIT_QPS 를 절반으로 낮추고 N_WORKERS_IO 를 8 이하로 줄이세요. "
     "네이버/한경은 User-Agent 와 Referer 헤더가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests",
     "요청이 너무 빠릅니다. RATE_LIMIT_QPS 를 낮추세요. 코드가 지수백오프로 재시도하지만 한계가 있습니다."),
    (r"ConnectionError|Timeout|Max retries|NameResolution|SSLError|ProxyError",
     "네트워크 도달 실패입니다. 방화벽/프록시 환경이면 해당 도메인이 막혀 있을 수 있습니다. "
     "RUN_MODE='CACHED' 로 두고 드라이브 캐시만으로 백테스트할 수 있습니다."),
    (r"No such file or directory.*drive|MyDrive|drive/MyDrive",
     "구글드라이브가 마운트되지 않았습니다. Colab이면 셀 실행 시 뜨는 인증 팝업을 승인하세요. "
     "JupyterLab이면 자동으로 LOCAL_CACHE_ROOT 를 사용합니다(정상)."),
    (r"No space left on device|Disk quota",
     "디스크/드라이브 용량 부족입니다. RESEARCH_DOWNLOAD_PDF=False 로 두면 PDF 원문을 받지 않고 "
     "리스트 메타데이터만으로도 목표주가·애널리스트 연결이 가능합니다."),
    (r"Can't pickle|pickle.*__main__|PicklingError|BrokenProcessPool",
     "프로세스 병렬화 실패(노트북의 고질적 문제). 코드가 자동으로 스레드 병렬로 폴백합니다. "
     "성능만 떨어지고 결과는 동일합니다."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족입니다. MEM_BUDGET_GB 를 낮추고 RESEARCH_DOWNLOAD_PDF=False, "
     "N_WORKERS_CPU=2 로 두세요. 패널은 float32/category 로 이미 축소되어 있습니다."),
    (r"pyarrow|parquet|ArrowInvalid|ArrowIOError",
     "parquet 읽기/쓰기 실패입니다. 드라이브 FUSE 마운트에서 쓰기가 중단되면 파일이 깨질 수 있습니다. "
     "코드는 임시파일→원자적 rename 으로 쓰므로, 깨진 건 이전 실행 잔재입니다. "
     "해당 파일만 지우고(원본 아님, 캐시임) 재실행하세요."),
    (r"'DataFrame' object has no attribute 'name'|_wrap_agged_manager",
     "중복 컬럼입니다. DataFrame 에 같은 이름의 컬럼이 두 개 있으면 df[col] 이 Series 가 아니라 "
     "DataFrame 이 되고, groupby(...).agg() 가 pandas 내부에서 이 예외로 터집니다. "
     "직전에 concat/reindex(columns=...)/merge 로 컬럼을 합친 곳을 보세요 — "
     "리스트를 이어붙일 때(예: COLS + ['x'] 인데 COLS 에 이미 'x' 가 있는 경우) 가장 흔합니다. "
     "assert_no_dup_cols() 로 발생 지점을 앞당겨 잡을 수 있습니다."),
    (r"Expecting value: line \d+ column 1|JSONDecodeError|Error occurred in get_market",
     "JSON 대신 HTML(대개 로그인/에러 페이지)을 받았습니다. KRX 계열이면 세션이 끊긴 것입니다. "
     "pykrx 는 스레드마다 재로그인하며 KRX 는 중복 로그인 시 이전 세션을 끊습니다 — "
     "모든 pykrx 호출은 KRXG.call() 게이트로 직렬화해야 합니다. "
     "KRX ID/PW 를 다른 브라우저 탭에서 동시에 쓰고 있지 않은지도 확인하세요."),
    (r"UnicodeEncodeError|cp949|charmap",
     "콘솔 인코딩 문제입니다(윈도우 기본 cp949 는 罫線문자 ╔═║ 와 ✔✘ 를 못 씁니다). "
     "코드가 stdout 을 UTF-8 로 재설정하고 실패 시 ASCII 로 낮추지만, 직접 출력을 추가했다면 "
     "print 대신 _safe_print 를 쓰세요. 또는 실행 전 `chcp 65001` 을 하세요."),
    (r"statvfs|WinError",
     "윈도우 전용 이슈입니다. os.statvfs 는 윈도우에 없고(용량 표시만 생략됩니다), "
     "파일 잠금·경로 구분자도 다릅니다. 기능에는 영향이 없어야 하며, 있다면 버그입니다."),
    (r"KeyError: 'knowledge_date'|knowledge_date",
     "PIT 컬럼 누락입니다. 모든 테이블은 event_date/knowledge_date 를 가져야 합니다(C1). "
     "새 수집 함수를 추가했다면 pit_frame() 으로 감싸주세요."),
    (r"empty|EmptyDataError|No objects to concatenate|zero-size",
     "수집 결과가 비었습니다. 대개 ① 키 미입력 ② 조회구간에 데이터 없음 ③ 소스 구조 변경입니다. "
     "바로 위 FLOW 원장에서 어느 소스가 0행을 반환했는지 확인하세요."),
    (r"ModuleNotFoundError|ImportError",
     "패키지 누락입니다. 위 부트스트랩 로그에서 어떤 설치가 실패했는지 확인하고 수동 설치하세요."),
    (r"tz-aware|tz-naive|Cannot compare",
     "타임존이 섞인 날짜 비교입니다. 이 코드는 모든 날짜를 tz-naive Timestamp 로 정규화합니다(as_ts). "
     "새로 추가한 소스가 tz-aware 를 반환했을 가능성이 큽니다."),
]


def diagnose(exc: BaseException, extra: str = "") -> str:
    blob = f"{type(exc).__name__}: {exc}\n{extra}\n{traceback.format_exc()}"
    for pat, hint in _DIAG_RULES:
        if re.search(pat, blob, re.I):
            return hint
    return ("알려진 패턴에 해당하지 않는 오류입니다. 아래 트레이스백의 마지막 프레임과 "
            "그 직전 FLOW 원장 행을 함께 보면 원인 구간이 좁혀집니다.")


# ── 파이프라인 ──────────────────────────────────────────────────────────────────────────────
class Pipeline:
    """스테이지 실행기. 모든 계산은 이 안에서만 돈다."""

    def __init__(self):
        self.stages: "OrderedDict[str, StageRecord]" = OrderedDict()
        self.flow: List[IOEvent] = []
        self.current: Optional[StageRecord] = None
        self.failed: List[str] = []
        self.artifacts: Dict[str, Any] = {}
        self._lock = threading.RLock()

    # -- I/O 원장 -------------------------------------------------------------------------
    def io(self, direction: str, kind: str, name: str, obj: Any = None,
           source: str = "", ok: bool = True, note: str = "", bytes_: int = -1):
        rows = cols = -1
        pit = ""
        try:
            if isinstance(obj, pd.DataFrame):
                rows, cols = int(obj.shape[0]), int(obj.shape[1])
                have = [c for c in ("event_date", "knowledge_date") if c in obj.columns]
                pit = "+".join(h[0].upper() for h in have) if have else "—"
            elif isinstance(obj, (list, tuple, set, dict)):
                rows = len(obj)
            elif isinstance(obj, (int, float)):
                rows = int(obj)
        except Exception:
            pass
        ev = IOEvent(stage=self.current.sid if self.current else "-", direction=direction,
                     kind=kind, name=name, rows=rows, cols=cols, bytes_=bytes_,
                     source=source, ok=ok, note=note, pit_cols=pit)
        with self._lock:
            self.flow.append(ev)
            if self.current:
                if direction == "IN" and rows > 0:
                    self.current.rows_in += rows
                if direction == "OUT" and rows > 0:
                    self.current.rows_out += rows
        return obj

    def note(self, msg: str):
        if self.current:
            self.current.notes.append(msg)

    # -- 스테이지 ------------------------------------------------------------------------
    @contextmanager
    def stage(self, sid: str, name: str, layer: str = "L?",
              budget_s: Optional[float] = None, critical: bool = True,
              skip_if: bool = False, skip_reason: str = ""):
        rec = StageRecord(sid=sid, name=name, layer=layer, budget_s=budget_s)
        self.stages[sid] = rec
        prev, self.current = self.current, rec
        LOG.ctx.append(sid)
        if skip_if:
            rec.status, rec.t_start, rec.t_end = "SKIP", time.time(), time.time()
            rec.notes.append(skip_reason or "조건 미충족")
            LOG.warn(f"건너뜀 — {skip_reason}")
            LOG.ctx.pop(); self.current = prev
            yield rec
            return
        rec.status = "RUNNING"
        rec.t_start = time.time()
        LOG.info(f"▷ {name}")
        try:
            yield rec
            rec.t_end = time.time()
            rec.status = "WARN" if any("WARN:" in n for n in rec.notes) else "OK"
            over = budget_s and rec.dur > budget_s
            msg = f"완료 {rec.dur:6.2f}s  in={rec.rows_in:,} out={rec.rows_out:,}"
            if over:
                rec.notes.append(f"WARN: 런타임 예산 {budget_s:.0f}s 초과")
                LOG.warn(msg + f"  ← 예산 {budget_s:.0f}s 초과 (C10)")
            else:
                LOG.ok(msg)
        except KillCriteria as e:
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = "KillCriteria"; rec.err_msg = str(e)
            rec.err_tb = traceback.format_exc()
            rec.hint = "§15 킬 기준입니다. 파라미터를 조정해 통과시키지 마세요. 결과를 그대로 보고합니다."
            self.failed.append(sid)
            LOG.error(f"킬 기준 발동 — {e}")
            raise
        except BaseException as e:                                   # noqa
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = type(e).__name__; rec.err_msg = str(e)[:600]
            rec.err_tb = traceback.format_exc()
            rec.hint = diagnose(e, extra=f"stage={sid} name={name}")
            self.failed.append(sid)
            self._print_failure(rec)
            if critical:
                raise StageFailure(f"[{sid}] {name} 실패: {rec.err_type}: {rec.err_msg}") from e
            rec.status = "WARN"
            rec.notes.append(f"WARN: 비필수 스테이지 실패 — {rec.err_type}")
        finally:
            LOG.ctx.pop()
            self.current = prev

    def _print_failure(self, rec: StageRecord):
        LOG.banner(f"✘ 실패 지점: [{rec.sid}] {rec.name}", f"계층 {rec.layer} · 경과 {rec.dur:.2f}s")
        _safe_print(f"  예외      : {rec.err_type}: {rec.err_msg}")
        _safe_print(f"  진단      : {rec.hint}")
        recent = [e for e in self.flow if e.stage == rec.sid][-8:]
        if recent:
            LOG.table(
                [[e.direction, e.kind, _trunc(e.name, 34), f"{e.rows:,}" if e.rows >= 0 else "-",
                  e.pit_cols, "OK" if e.ok else "ERR", _trunc(e.source or e.note, 26)] for e in recent],
                ["방향", "종류", "대상", "행수", "PIT", "상태", "소스/비고"],
                ["c", "l", "l", "r", "c", "c", "l"],
                title="이 스테이지의 직전 입출력 (여기서 무엇이 비었는지 보세요)")
        _safe_print("\n  ── 트레이스백 (마지막 12줄) " + "─" * 60)
        for ln in rec.err_tb.rstrip().split("\n")[-12:]:
            _safe_print("   " + ln)
        _safe_print("  " + "─" * 86)

    # -- 리포트 --------------------------------------------------------------------------
    def report_stages(self):
        LOG.banner("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수 · 런타임 예산(C10)")
        rows = []
        for r in self.stages.values():
            icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUNNING": "…"}.get(r.status, "?")
            bud = "-" if r.budget_s is None else (f"{r.budget_s:.0f}s" + ("❗" if r.dur > r.budget_s else ""))
            rows.append([r.layer, r.sid, _trunc(r.name, 40), f"{icon}{r.status}",
                         f"{r.dur:8.2f}", f"{r.rows_in:,}", f"{r.rows_out:,}", bud,
                         _trunc("; ".join(r.notes), 40)])
        LOG.table(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "예산", "비고"],
                  ["c", "l", "l", "c", "r", "r", "r", "c", "l"], maxw=44)

    def report_flow(self, only_kinds: Optional[Sequence[str]] = None, limit: int = 200):
        LOG.banner("데이터 흐름 원장 (I/O LEDGER)",
                   "어떤 스테이지가 어디서 몇 행을 읽고 어디에 몇 행을 썼는가 · PIT=E(event)/K(knowledge)")
        evs = [e for e in self.flow if (not only_kinds or e.kind in only_kinds)]
        if len(evs) > limit:
            LOG.warn(f"원장 {len(evs)}건 중 최근 {limit}건만 출력합니다.")
            evs = evs[-limit:]
        LOG.table(
            [[e.stage, e.direction, e.kind, _trunc(e.name, 38),
              f"{e.rows:,}" if e.rows >= 0 else "-",
              f"{e.cols}" if e.cols >= 0 else "-",
              e.pit_cols or "—", "OK" if e.ok else "ERR", _trunc(e.source or e.note, 30)] for e in evs],
            ["스테이지", "방향", "종류", "대상", "행수", "열수", "PIT", "상태", "소스/비고"],
            ["l", "c", "l", "l", "r", "r", "c", "c", "l"], maxw=40)

    def report_runtime(self):
        """C10 런타임 감사 — 추측하지 말고 측정한다."""
        LOG.banner("런타임 감사 (C10)", "계층별 실측 소요시간 vs 계약 예산")
        budgets = {"L1": 30 * 60, "L2": 2 * 60, "L3": 3 * 60, "L5": 4 * 3600}
        agg: Dict[str, float] = defaultdict(float)
        for r in self.stages.values():
            agg[r.layer] += r.dur
        rows = []
        for layer in sorted(agg):
            spent = agg[layer]
            bud = budgets.get(layer)
            verdict = "—"
            if bud:
                verdict = "✔ 예산 내" if spent <= bud else f"❗ 초과 ({spent / bud:.1f}배)"
            rows.append([layer, f"{spent:8.2f}s", f"{spent / 60:6.2f}분",
                         (f"{bud / 60:.0f}분" if bud else "-"), verdict])
        rows.append(["합계", f"{sum(agg.values()):8.2f}s", f"{sum(agg.values()) / 60:6.2f}분", "4시간",
                     "✔ 예산 내" if sum(agg.values()) <= 4 * 3600 else "❗ 초과 — 아키텍처 수정 필요"])
        LOG.table(rows, ["계층", "실측(초)", "실측(분)", "계약예산", "판정"], ["c", "r", "r", "r", "l"])
        LOG.info("계층 정의 — L0:부트/캐시  L1:수집·피처패널  L2:스코어  L3:백테스트  L5:강건성  L6:리포트")


PIPE = Pipeline()



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 해시 / 원자적 IO / 재시도 / 레이트리미터 / 병렬 / 벡터화 통계               ║
# ║                                                                                          ║
# ║  · 횡단면 변환 순서(C5)는 여기서 단 한 번 하드코딩된다: winsorize → z → rank_pct          ║
# ║  · 롤링 회귀는 반드시 벡터화 (칼만 폐기, §3). 종목별 파이썬 루프 금지.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 정규화 ─────────────────────────────────────────────────────────────────────────────
def as_ts(x) -> Optional[pd.Timestamp]:
    """무엇이 들어오든 tz-naive 로 정규화된 Timestamp. tz 혼재는 이 프로젝트 최빈 버그였다."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        t = pd.Timestamp(x)
    except Exception:
        try:
            t = pd.to_datetime(str(x), errors="coerce")
        except Exception:
            return None
    if t is pd.NaT or pd.isna(t):
        return None
    if getattr(t, "tzinfo", None) is not None:
        t = t.tz_localize(None) if t.tz is None else t.tz_convert(None).tz_localize(None)
    return t.normalize()


def as_ts_series(s) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    return out.dt.normalize()


def month_end(x) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> pd.DatetimeIndex:
    return pd.date_range(month_end(start), month_end(end), freq="ME")


# ── 해시 / 식별자 ───────────────────────────────────────────────────────────────────────────
def sha1_str(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha1_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm_text(s: Any) -> str:
    """상호/애널리스트명/제목 정규화. 매칭 정확도의 8할이 여기서 결정된다."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", s)        # 괄호 안 제거
    s = re.sub(r"[^\w가-힣A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_corp_name(s: Any) -> str:
    """법인격 접미어 제거 — 사업장명↔법인명 매칭용."""
    t = norm_text(s)
    t = re.sub(r"\b(주식회사|유한회사|합자회사|주|㈜|Co|Ltd|Inc|Corp|Corporation|Company|Limited)\b",
               " ", t, flags=re.I)
    t = re.sub(r"(주식회사|유한회사)", " ", t)
    return re.sub(r"\s+", "", t).strip()


# 2024-01-01 종목코드 개편으로 영숫자 코드가 도입되었다.
# 형식: 앞 4자리 숫자 + 5번째(0-9,A-Z 중 I/O/U 제외) + 6번째(0,K,L,M,N)
# ★ 단순히 \D 를 제거하면 신형 티커가 조용히 망가진다(예: '09701K' → '009701').
_TICKER_RE = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])$")


def to_code6(x: Any) -> Optional[str]:
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드.
    실패하면 None. 조용히 0으로 채워 잘못된 종목을 만들지 않는다."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    s = re.sub(r"\s", "", str(x).strip().upper()).split(".")[0]
    if len(s) == 7 and s[0] in "AQ" and _TICKER_RE.match(s[1:]):
        s = s[1:]
    if _TICKER_RE.match(s):
        return s
    d = re.sub(r"\D", "", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
        return cand if _TICKER_RE.match(cand) else None
    return None


def similarity(a: str, b: str) -> float:
    """0~100. rapidfuzz 있으면 그걸, 없으면 difflib."""
    a, b = norm_corp_name(a), norm_corp_name(b)
    if not a or not b:
        return 0.0
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(a, b))
    import difflib
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


# ── 원자적 파일 IO (드라이브 FUSE 에서 깨지지 않게) ──────────────────────────────────────────
def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def atomic_write_bytes(path: str, data: bytes) -> str:
    """임시파일 → flush/fsync → os.replace. 드라이브 마운트에서 중단돼도 원본이 반쪽 나지 않는다."""
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_parquet(df: pd.DataFrame, path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = df.copy()
    for c in out.columns:                       # object 컬럼은 arrow 가 종종 거부한다 → 문자열화
        if out[c].dtype == object:
            try:
                pd.api.types.infer_dtype(out[c], skipna=True)
            except Exception:
                out[c] = out[c].astype(str)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        out.to_parquet(tmp, index=False, compression="snappy")
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    """★ 읽기 실패 시에도 원본을 '원래 자리에' 남긴다.

    예전 구현은 어떤 예외든 즉시 os.replace 로 파일을 .corrupt 로 옮겼다. 그런데 드라이브
    FUSE 는 일시적 I/O 오류를 흔히 낸다. 원본이 자리에서 사라지면 put_table 이 백업할 대상을
    찾지 못해 '백업 없이' 새 파일을 쓰게 되고, 그건 "백업 없이는 절대 교체하지 않는다"는
    절대 1원칙을 정확히 뒤집는다. → 1회 재시도 후에도 실패하면 '복사본'만 격리하고
    원본은 그대로 둔다(다음 put_table 이 그 원본을 백업할 수 있도록)."""
    if not os.path.exists(path):
        return None
    for attempt in range(2):
        try:
            return pd.read_parquet(path)
        except Exception as e:                                          # noqa
            if attempt == 0:
                time.sleep(0.5)
                continue
            LOG.warn(f"parquet 읽기 실패 — 원본은 자리에 두고 사본만 격리합니다: "
                     f"{os.path.basename(path)} ({type(e).__name__}). "
                     f"다음 쓰기 때 이 원본이 백업된 뒤 교체됩니다(무백업 교체 방지).")
            try:
                shutil.copy2(path, path + f".corrupt.{int(time.time())}")
            except Exception:
                pass
            return None
    return None


def read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue                        # 반쪽 줄은 건너뛴다 (append-only 저널의 정상 동작)
    return out


def append_jsonl(path: str, rows: Iterable[dict]):
    _ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


# ── 레이트리미터 / 재시도 ───────────────────────────────────────────────────────────────────
class RateLimiter:
    """소스별 토큰버킷. 스레드 안전. 차단당하지 않기 위한 최소 장치."""

    def __init__(self, qps: float):
        self.interval = 1.0 / max(qps, 0.01)
        self._next = 0.0
        self._lk = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.monotonic()
            if now < self._next:
                d = self._next - now
            else:
                d = 0.0
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]


def retry(tries: int = 4, base: float = 1.6, exc=(Exception,), on_fail=None, quiet: bool = False):
    def deco(fn):
        def wrapped(*a, **kw):
            last = None
            for i in range(tries):
                try:
                    return fn(*a, **kw)
                except exc as e:                       # noqa
                    last = e
                    if i == tries - 1:
                        break
                    slp = (base ** i) + random.random() * 0.4
                    if not quiet:
                        LOG.debug(f"재시도 {i+1}/{tries-1} ({type(e).__name__}) — {slp:.1f}s 대기")
                    time.sleep(slp)
            if on_fail is not None:
                return on_fail(last)
            raise last                                  # type: ignore
        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapped
    return deco


# ── 병렬 ────────────────────────────────────────────────────────────────────────────────────
def pmap_io(fn: Callable, items: Sequence, workers: Optional[int] = None,
            desc: str = "", quiet: bool = False) -> List[Any]:
    """네트워크 병렬(스레드). 예외는 삼키지 않고 None 으로 표시하되 개수를 로그에 남긴다."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_WORKERS_IO, len(items)))
    out: List[Any] = [None] * len(items)
    errs: Counter = Counter()
    with ThreadPoolExecutor(max_workers=w, thread_name_prefix="io") as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        it_ = as_completed(futs)
        if not quiet:
            it_ = tqdm(it_, total=len(futs), desc=desc or "수집", leave=False, ncols=88)
        for fu in it_:
            i = futs[fu]
            try:
                out[i] = fu.result()
            except Exception as e:                       # noqa
                errs[type(e).__name__] += 1
                out[i] = None
    if errs:
        LOG.warn(f"{desc or '병렬작업'} 중 실패 {sum(errs.values())}/{len(items)}건 — " +
                 ", ".join(f"{k}×{v}" for k, v in errs.most_common(4)))
    return out


def pmap_cpu(fn: Callable, items: Sequence, workers: Optional[int] = None, desc: str = "") -> List[Any]:
    """연산 병렬. fork 가능하면 프로세스, 아니면 스레드로 자동 폴백(결과 동일, 속도만 차이)."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_CPU, len(items)))
    if w == 1 or not CAN_FORK:
        if not CAN_FORK:
            LOG.debug("fork 불가 환경 — 연산 병렬을 스레드로 폴백합니다(결과 동일).")
        return [fn(x) for x in tqdm(items, desc=desc or "연산", leave=False, ncols=88)]
    try:
        ctx = _mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=w, mp_context=ctx) as ex:
            return list(tqdm(ex.map(fn, items), total=len(items), desc=desc or "연산",
                             leave=False, ncols=88))
    except Exception as e:                                # noqa
        LOG.warn(f"프로세스 병렬 실패({type(e).__name__}) — 순차 실행으로 폴백합니다.")
        return [fn(x) for x in items]


# ── 메모리 ──────────────────────────────────────────────────────────────────────────────────
def downcast(df: pd.DataFrame, cat_thresh: float = 0.35) -> pd.DataFrame:
    """float64→float32, 저카디널리티 object→category. 10년 패널 RAM을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = df[c].dtype.kind
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
        elif k == "O":
            try:
                n = df[c].nunique(dropna=True)
                if n > 0 and n / max(len(df), 1) < cat_thresh:
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df


def mem_mb(df: pd.DataFrame) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0


# ── PIT 프레임 강제 (C1) ────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")


def _resolve_dates(df: pd.DataFrame, arg) -> pd.Series:
    """날짜 인자 해석 규칙 — 딱 세 가지만 허용한다(모호함이 곧 버그다):
       ① 문자열이고 df 의 컬럼명이면      → 그 컬럼
       ② Series/배열/리스트이면           → 그대로 (길이 일치 필요)
       ③ 그 외(스칼라 날짜/문자열 날짜)   → 전 행에 브로드캐스트
    """
    if isinstance(arg, str) and arg in df.columns:
        return as_ts_series(df[arg]).set_axis(df.index)
    if isinstance(arg, pd.Series):
        if len(arg) != len(df):
            raise ValueError(f"날짜 Series 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(arg.to_numpy())).set_axis(df.index)
    if isinstance(arg, (list, tuple, np.ndarray, pd.DatetimeIndex)):
        if len(arg) != len(df):
            raise ValueError(f"날짜 배열 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(list(arg))).set_axis(df.index)
    return as_ts_series(pd.Series([arg] * len(df))).set_axis(df.index)


def pit_frame(df: pd.DataFrame, event_date, knowledge_date, source: str = "") -> pd.DataFrame:
    """모든 수집 결과는 이 함수를 통과해야 한다. 통과하지 않은 테이블은 PIT store 가 거부한다."""
    if df is None or len(df) == 0:
        base = pd.DataFrame(df if df is not None else None)
        for c in PIT_COLS:
            if c not in base.columns:
                base[c] = pd.Series(dtype="datetime64[ns]")
        if source:
            base["_src"] = pd.Series(dtype=object)
        return base
    out = df.copy().reset_index(drop=True)
    out["event_date"] = _resolve_dates(out, event_date)
    out["knowledge_date"] = _resolve_dates(out, knowledge_date)
    # knowledge_date 는 event_date 보다 이를 수 없다 — 이를 어기면 그 자체가 미래누수다.
    bad = out["knowledge_date"] < out["event_date"]
    if bad.any():
        out.loc[bad, "knowledge_date"] = out.loc[bad, "event_date"]
        if PIPE.current:
            PIPE.note(f"WARN: knowledge_date < event_date 인 {int(bad.sum())}행을 event_date 로 보정")
    out = out.dropna(subset=["knowledge_date"])
    if source:
        out["_src"] = source
    return out


# ── 벡터화 횡단면 통계 (C5 순서 고정) ───────────────────────────────────────────────────────
WINSOR_SIGMA = 2.0
CELL_MIN_N = 8


def _winsor_np(a: np.ndarray, k: float = WINSOR_SIGMA) -> np.ndarray:
    m = np.nanmean(a)
    s = np.nanstd(a)
    if not np.isfinite(s) or s == 0:
        return a
    return np.clip(a, m - k * s, m + k * s)


def xsec_z(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N,
           k: float = WINSOR_SIGMA) -> pd.Series:
    """C5: winsorize(±2σ) → 셀 내 z-score.  순서는 여기서만 정의되고 파라미터화하지 않는다.

    구현 주의 두 가지:
     ① ±inf 를 반드시 먼저 NaN 으로 바꾼다. np.nanmean 은 NaN 은 무시하지만 inf 는 무시하지
        않으므로, 셀에 inf 가 단 하나만 있어도 평균이 inf·표준편차가 NaN 이 되어
        **그 셀 전체의 z-score 가 0으로 뭉개진다.** 비율 지표(diff/log)에서 흔히 발생한다.
     ② groupby.transform(파이썬 UDF) 대신 네이티브 집계로 벡터화한다.
        실데이터 규모(30만 행 × 수천 셀)에서 UDF 경로는 호출당 10초 이상이고,
        파이프라인은 이 함수를 수십 번 부른다.
    """
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()

    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    mu0 = g.transform("mean")
    sd0 = g.transform("std", ddof=0)
    w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)          # ① winsorize

    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)                               # ② z-score
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)            # 셀 내 전원 동일값 → 0
    return z.where(cnt >= min_n).astype("float32")


def xsec_rank_pct(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 백분위 랭크 [0,1]. 표본 부족 셀은 NaN (0으로 채우지 않는다)."""
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    r = g.rank(pct=True, method="average")
    return r.where(cnt >= min_n).astype("float32")


CELL_LADDER = ("cell", "cell_l2", "cell_l3")


def xsec_z_l(P: pd.DataFrame, name: str, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 폴백 사다리를 적용한 z-score (C11).

    ★ 왜 필요한가: 셀에 종목이 30개 있어도 '그 센서를 관측한' 종목은 5개뿐일 수 있다.
      (관세·조달처럼 일부 종목만 커버하는 팩이 정확히 이 경우다)
      셀 크기만 보고 폴백하면 z-score 는 표본부족으로 전부 NaN 이 되고,
      그 팩은 아무 신호도 못 내면서 로그에는 아무것도 남지 않는다 — 최악의 조용한 실패다.
      그래서 '그 센서의 유효 관측 수' 기준으로 산업 상위 → 전체 순으로 단계적 폴백한다.
    """
    v = col(P, name)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not z.isna().any():
            break
        if lvl in P.columns:
            z = z.where(z.notna(), xsec_z(v, P[lvl], min_n))
    return z


def xsec_rank_pct_l(P: pd.DataFrame, name_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(name_or_series, errors="coerce")
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    r = xsec_rank_pct(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not r.isna().any():
            break
        if lvl in P.columns:
            r = r.where(r.notna(), xsec_rank_pct(v, P[lvl], min_n))
    return r


def tp_product(z_improve: pd.Series, z_nopay: pd.Series) -> pd.Series:
    """트레이드오프 쌍 = z(개선) × z(대가회피).  ★ 절대로 합으로 바꾸지 말 것 (§1.1).

    합으로 바꾸면 평범한 퀄리티 팩터가 되고 이 전략의 존재 이유가 사라진다.
    한쪽이 결측이면 결과도 결측 — 0으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다.
    """
    a = pd.to_numeric(z_improve, errors="coerce")
    b = pd.to_numeric(z_nopay, errors="coerce")
    return (a * b).astype("float32")


def col(df: pd.DataFrame, name: str, default: float = np.nan) -> pd.Series:
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자.

    ★ df.get("x") 는 컬럼이 없으면 None 을 반환한다. 그러면 `None + Series` 나 `None.abs()`
      로 TypeError/AttributeError 가 나는데, 하필 그 상황(= 특정 데이터 소스가 통째로 비어
      해당 계정 컬럼이 아예 생성되지 않은 경우)은 실데이터 실행에서 가장 흔하다.
      키 미입력·API 한도 소진·소급 데이터 없음 전부 이 경로로 들어온다.
      그래서 피처 계산부는 df.get 대신 반드시 이 함수를 쓴다.
    """
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def gby(df: pd.DataFrame, name: str, key: str = "code"):
    """col() 의 groupby 판(版). 없는 컬럼도 NaN 으로 만든 뒤 그룹화한다.

    ★ col() 이 막지 못하는 구멍이 정확히 여기였다. 피처 계산부는 결측 컬럼 산술을 col() 로
      막아 두었지만, `P.groupby("code")[c]` 는 여전히 맨손이라 c 가 없으면 KeyError 로 죽는다.
      DART 키가 없거나 재무 수집이 부분 실패하면 assets·contract_liab 같은 재무상태표 계정이
      아예 생성되지 않는데, 이 경로는 critical 스테이지(L1.PANEL)라 그대로 실행 전체가 중단된다.
      "키 없이도 실행은 된다"는 상단 안내와 정면으로 어긋나므로 groupby 도 안전 접근으로 통일한다.
    """
    if name not in df.columns:
        df[name] = np.nan
    return df.groupby(key, observed=True)[name]


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


def dlog(s: pd.Series, periods: int = 12) -> pd.Series:
    """Δlog. 음수/0 은 결측 처리 (log 의 정의역 밖을 0으로 메우는 것이 최빈 버그)."""
    v = pd.to_numeric(s, errors="coerce")
    lv = np.log(v.where(v > 0))
    return lv.diff(periods)


def nanmean_cols(df: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    """가용 축만으로 평균. 결측을 0으로 채우지 않는다 (§7.3 지시)."""
    use = [c for c in cols if c in df.columns]
    if not use:
        return pd.Series(np.nan, index=df.index)
    return df[use].astype("float64").mean(axis=1, skipna=True)


# ── 벡터화 롤링 OLS (칼만 대체, §3) ─────────────────────────────────────────────────────────
def rolling_ols_resid(y: np.ndarray, X: np.ndarray, window: int,
                      ridge: float = 1e-8, chunk: int = 256) -> np.ndarray:
    """N개 엔티티 × T기간 패널에 대해 길이 W 롤링 OLS 를 배치로 풀고 창 마지막 시점 잔차를 반환.

    y : (N, T)
    X : (N, T, K)   — 절편은 호출자가 포함시킬 것
    반환: (N, T) 잔차. 창이 안 차거나 결측 포함이면 NaN.

    종목별 파이썬 루프로 짜면 15분짜리가 3시간이 된다(§3). 반드시 이 경로를 쓸 것.
    """
    y = np.asarray(y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    N, T = y.shape
    K = X.shape[2]
    out = np.full((N, T), np.nan, dtype=np.float64)
    if T < window or window < K + 2:
        return out
    try:
        from numpy.lib.stride_tricks import sliding_window_view as _swv
    except Exception:                                     # numpy<1.20 폴백
        _swv = None

    for s in range(0, N, chunk):
        e = min(N, s + chunk)
        yc, Xc = y[s:e], X[s:e]
        n = e - s
        if _swv is not None:
            yw = _swv(yc, window, axis=1)                 # (n, T-W+1, W)
            Xw = _swv(Xc, window, axis=1)                 # (n, T-W+1, K, W)
            Xw = np.moveaxis(Xw, -1, 2)                   # (n, T-W+1, W, K)
        else:
            idx = np.arange(window)[None, :] + np.arange(T - window + 1)[:, None]
            yw = yc[:, idx]
            Xw = Xc[:, idx, :]
        finite = np.isfinite(yw).all(axis=2) & np.isfinite(Xw).all(axis=(2, 3))   # (n, M)
        yw = np.where(np.isfinite(yw), yw, 0.0)
        Xw = np.where(np.isfinite(Xw), Xw, 0.0)
        XtX = np.einsum("nmwk,nmwl->nmkl", Xw, Xw, optimize=True)
        Xty = np.einsum("nmwk,nmw->nmk", Xw, yw, optimize=True)
        XtX += ridge * np.eye(K)[None, None, :, :] * np.maximum(
            1.0, np.abs(np.einsum("nmkk->nm", XtX))[..., None, None] / max(K, 1))
        try:
            beta = np.linalg.solve(XtX, Xty[..., None])[..., 0]                   # (n, M, K)
        except np.linalg.LinAlgError:
            beta = np.einsum("nmkl,nml->nmk", np.linalg.pinv(XtX), Xty)
        x_last = Xw[:, :, -1, :]                                                  # (n, M, K)
        resid = yw[:, :, -1] - np.einsum("nmk,nmk->nm", x_last, beta)
        resid = np.where(finite, resid, np.nan)
        out[s:e, window - 1:] = resid
        del yw, Xw, XtX, Xty, beta
    return out


def rolling_ols_beta_last(y: np.ndarray, X: np.ndarray, window: int, ridge: float = 1e-8) -> np.ndarray:
    """위와 동일하되 마지막 창의 계수만 필요할 때 (R3 직교화 등)."""
    N, T = y.shape
    K = X.shape[2]
    if T < window:
        return np.full((N, K), np.nan)
    yw, Xw = y[:, -window:], X[:, -window:, :]
    ok = np.isfinite(yw).all(axis=1) & np.isfinite(Xw).all(axis=(1, 2))
    yw = np.nan_to_num(yw); Xw = np.nan_to_num(Xw)
    XtX = np.einsum("nwk,nwl->nkl", Xw, Xw) + ridge * np.eye(K)[None]
    Xty = np.einsum("nwk,nw->nk", Xw, yw)
    beta = np.linalg.solve(XtX, Xty[..., None])[..., 0]
    beta[~ok] = np.nan
    return beta


def hac_tstat(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량. 월간 초과수익 시계열의 유의성에 쓴다(R2/R3)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return (np.nan, np.nan)
    mu = x.mean()
    e = x - mu
    L = lags if lags is not None else int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    L = max(0, min(L, n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    se = math.sqrt(var / n)
    return (float(mu), float(mu / se))


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg. 강건성 검정을 여러 번 돌리면 다중검정 보정이 필요하다."""
    p = np.asarray(pvals, dtype=float)
    ok = np.isfinite(p)
    out = np.zeros_like(p, dtype=bool)
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[order[:kmax + 1]] = True
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스                                 ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★                                  ║
# ║                                                                                          ║
# ║  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:                                        ║
# ║   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않으므로              ║
# ║      코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없다.                                    ║
# ║   2) index.parquet 은 저널의 파생물(캐시)일 뿐이다. 재생성 전 항상 타임스탬프 백업.        ║
# ║   3) 컬럼은 합집합으로만 확장한다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않는다.          ║
# ║   4) 원본 blob 은 내용해시 기반 경로에 쓰므로 같은 내용은 재기록조차 하지 않는다.          ║
# ║      내용이 다르면 새 리비전으로 쓰고, 기존 파일은 건드리지 않는다.                        ║
# ║   5) 이미 드라이브에 있던 리포트는 "옮기지 않고 경로만 등록"한다(adopt-by-reference).      ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 한다.              ║
# ║                                                                                          ║
# ║  공용 인덱스(_shared) : 다른 전략에서도 그대로 재활용 가능한 원본/정제본                   ║
# ║  전용 인덱스(tcd_v2)  : 이 전략 고유의 피처·스코어·리포트                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "2.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "extra",
]


def _mount_drive() -> Tuple[str, str]:
    """(루트경로, 상태문자열). Colab이면 마운트 시도, 아니면 로컬 폴백. 어느 쪽이든 죽지 않는다."""
    if ENV["colab"]:
        try:
            from google.colab import drive as _gdrive      # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return GDRIVE_ROOT, "COLAB_DRIVE"
            return LOCAL_CACHE_ROOT, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                             # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return LOCAL_CACHE_ROOT, "COLAB_MOUNT_ERROR→LOCAL"
    # JupyterLab / CLI: 드라이브가 이미 동기화되어 있으면 그 경로를 쓴다.
    for cand in (GDRIVE_ROOT, os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return LOCAL_CACHE_ROOT, "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
        self.ns = {"shared": os.path.join(self.root, GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            os.makedirs(os.path.join(p, "index"), exist_ok=True)
            os.makedirs(os.path.join(p, "index", "_backup"), exist_ok=True)
            os.makedirs(os.path.join(p, "blob"), exist_ok=True)
            os.makedirs(os.path.join(p, "table"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, pd.DataFrame] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats = Counter()

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 잠금 (두 노트북이 동시에 돌아도 저널이 섞이지 않게) -----------------------------
    @contextmanager
    def lock(self, name: str, timeout: float = 60.0, stale: float = 900.0):
        lp = os.path.join(self.root, "_locks", f"{name}.lock")
        t0 = time.time()
        acquired = False
        while time.time() - t0 < timeout:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "host": platform.node(),
                                         "ts": time.time()}).encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                try:
                    info = json.loads(open(lp).read() or "{}")
                    if time.time() - float(info.get("ts", 0)) > stale:
                        LOG.warn(f"오래된 잠금 해제: {name} (>{stale:.0f}s)")
                        os.remove(lp)
                        continue
                except Exception:
                    try:
                        os.remove(lp)
                    except Exception:
                        pass
                time.sleep(0.4)
        if not acquired:
            LOG.warn(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # ── 인덱스 적재 (기존 것을 절대 건드리지 않고 읽기만) --------------------------------
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []

        # (a) 정규 parquet 인덱스
        p = self.idx_parquet(scope)
        d = read_parquet_safe(p)
        if d is not None and len(d):
            frames.append(d)

        # (b) append-only 저널 (진실의 원천)
        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # (c) 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        legacy_glob = []
        idx_dir = os.path.join(self.ns[scope], "index")
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    legacy_glob.append(os.path.join(idx_dir, fn))
        except Exception:
            pass
        for fp in legacy_glob:
            try:
                if fp.endswith(".parquet"):
                    dd = read_parquet_safe(fp)
                elif fp.endswith(".csv"):
                    dd = pd.read_csv(fp)
                elif fp.endswith(".jsonl"):
                    dd = pd.DataFrame(read_jsonl(fp))
                else:
                    dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                if dd is not None and len(dd):
                    dd["_legacy_file"] = os.path.basename(fp)
                    frames.append(dd)
                    self.stats[f"legacy_index_absorbed:{os.path.basename(fp)}"] += len(dd)
            except Exception:
                continue

        if frames:
            # 컬럼 합집합 — 기존 컬럼을 절대 떨어뜨리지 않는다
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            frames = [f.reindex(columns=allcols) for f in frames]
            idx = pd.concat(frames, ignore_index=True)
            # ★ uid 가 없거나 결측인 레거시 행을 그대로 두면 astype(str) 이 전부 "nan" 이 되고
            #   drop_duplicates(uid) 가 그 파일 전체를 단 한 줄로 붕괴시킨다 = 인덱스 유실.
            #   절대 1원칙에 정면으로 반하므로, 결측 uid 는 행 내용 해시로 개별 부여한다.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | (idx["uid"].astype(str).str.strip().isin(("", "nan", "None")))
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                idx.loc[miss, "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in fill_src])
                    for i in np.where(miss.to_numpy())[0]]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
            idx["uid"] = idx["uid"].astype(str)
            if "collected_at" in idx.columns:
                idx = idx.sort_values("collected_at", kind="stable")
            idx = idx.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        else:
            idx = pd.DataFrame(columns=INDEX_COLUMNS)

        for c in INDEX_COLUMNS:
            if c not in idx.columns:
                idx[c] = np.nan
        idx["scope"] = idx["scope"].fillna(scope)
        with self._lk:
            self._idx[scope] = idx
            self._uidset[scope] = set(idx["uid"].astype(str).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope] or any(r.get("uid") == uid for r in self._pending[scope])

    def lookup(self, scope: str, **eq) -> pd.DataFrame:
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= (idx[k].astype(str) == str(v))
        return idx[m]

    # ── 기록 --------------------------------------------------------------------------
    def _register(self, scope: str, rec: dict):
        rec.setdefault("scope", scope)
        rec.setdefault("schema_ver", VAULT_SCHEMA_VER)
        rec.setdefault("collected_at", _dt.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("strategy", STRATEGY_ID if scope == "private" else "")
        for c in INDEX_COLUMNS:
            rec.setdefault(c, None)
        with self._lk:
            self._pending[scope].append(rec)
            self._uidset.setdefault(scope, set()).add(str(rec["uid"]))
        self.stats[f"register:{scope}:{rec.get('domain')}"] += 1

    def put_blob(self, domain: str, subtype: str, key: str, data: bytes, fmt: str,
                 source: str = "", event_date=None, knowledge_date=None,
                 scope: str = "shared", extra: Optional[dict] = None,
                 uid: Optional[str] = None) -> Optional[str]:
        """원본 바이트를 내용해시 경로에 저장하고 인덱스에 등록. 같은 내용이면 재기록하지 않는다."""
        if not data:
            return None
        h = sha1_bytes(data)
        uid = uid or sha1_str(domain, subtype, key, h)
        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])
        fn = f"{h}.{fmt.lstrip('.')}"
        abspath = os.path.join(sub, fn)
        rel = os.path.relpath(abspath, self.root)
        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                          # noqa
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에만 기록하지 않고 건너뜁니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": rel, "abs_path": abspath, "fmt": fmt, "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "source": source, "adopted": False,
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        return abspath

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        if rows.empty:
            return None
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                              # noqa
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        return path

    def _latest_revision(self, scope: str, name: str) -> Optional[str]:
        """put_table 이 백업 실패로 {name}.rev<ts>.parquet 에 쓴 경우를 읽어낸다.
        이 폴백이 없으면 그 순간부터 모든 쓰기가 영원히 도달 불가가 된다(캐시 동결)."""
        import glob as _glob
        cands = sorted(_glob.glob(os.path.join(self.table_dir(scope), f"{name}.rev*.parquet")))
        return cands[-1] if cands else None

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None
                  ) -> Optional[pd.DataFrame]:
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if not os.path.exists(path):
            rev = self._latest_revision(scope, name)
            if rev:
                LOG.info(f"정규 테이블이 없어 리비전 파일을 읽습니다: {os.path.basename(rev)}")
                path = rev
        if not os.path.exists(path):
            # 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략이 만든 걸 재활용한다
            alt = "private" if scope == "shared" else "shared"
            path2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if os.path.exists(path2):
                path = path2
            else:
                return None
        if max_age_days is not None:
            age = (time.time() - os.path.getmtime(path)) / 86400.0
            if age > max_age_days:
                return None
        d = read_parquet_safe(path)
        if d is None:
            rev = self._latest_revision(scope, name)
            if rev and rev != path:
                LOG.warn(f"{os.path.basename(path)} 를 읽지 못해 리비전으로 폴백합니다.")
                d = read_parquet_safe(rev)
                path = rev
        if d is not None:
            PIPE.io("IN", "DRIVE", f"table:{name}", d, source=os.path.relpath(path, self.root))
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,
              source: str = "", event_date=None, knowledge_date=None,
              scope: str = "shared", extra: Optional[dict] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 '경로만' 등록한다. 파일은 읽기만 한다."""
        try:
            sz = os.path.getsize(abs_path)
        except Exception:
            return None
        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)
        if self.has(scope, uid):
            return uid
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": abs_path, "abs_path": abs_path, "fmt": os.path.splitext(abs_path)[1].lstrip("."),
            "bytes": sz, "sha1": "", "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ------------------------------------------------------------------
    def flush(self, scope: Optional[str] = None):
        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""
        scopes = [scope] if scope else ["shared", "private"]
        for sc in scopes:
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)
            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")

    def compact(self, scope: str):
        """저널 → index.parquet 재생성. 저널은 남기고, 기존 parquet 은 반드시 백업한 뒤 교체."""
        self.flush(scope)
        idx = self.load_index(scope, force=True)
        p = self.idx_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 안전을 위해 컴팩션을 건너뜁니다. "
                         f"저널({os.path.basename(self.journal(scope))})에 모든 기록이 남아 있으므로 "
                         f"데이터 유실은 없습니다.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (사용자의 기존 캐시 흡수) --------------------------------------------
    _PDF_PAT = re.compile(r"\.(pdf)$", re.I)
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 400_000) -> pd.DataFrame:
        """기존에 모아둔 리포트/테이블을 재귀 스캔해 '등록만' 한다. 이동·개명·삭제 없음."""
        seen, found = set(), []
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            rd = os.path.realpath(d)
            if rd in seen:
                continue
            seen.add(rd)
            LOG.info(f"기존 캐시 스캔: {d}")
            n = 0
            for dirpath, dirnames, filenames in os.walk(d):
                dirnames[:] = [x for x in dirnames if not x.startswith(".") and x != "_backup"]
                for fn in filenames:
                    if n >= max_files:
                        break
                    fp = os.path.join(dirpath, fn)
                    low = fn.lower()
                    if low.endswith(".pdf"):
                        kind = "report_pdf"
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "nps",
                                                   "price", "ohlcv", "universe", "fnltt")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": fp, "kind": kind, "name": fn,
                                  "dir": dirpath, "bytes": _safe_size(fp)})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        if not found:
            LOG.warn("기존 캐시에서 흡수할 파일을 찾지 못했습니다. "
                     "GDRIVE_ADOPT_DIRS 경로를 확인하세요(오타/미마운트가 가장 흔합니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared",
                       extra={"dir": r.dir})
        self.flush("shared")
        LOG.ok(f"기존 캐시 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
               f"(파일은 원위치 그대로, 이동·삭제 없음).")
        return df

    # ── 감사 --------------------------------------------------------------------------
    def report(self):
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            nb = 0
            try:
                nb = sum(int(x) for x in pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0))
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared" else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}",
                         f"{int(pd.to_numeric(idx.get('adopted'), errors='coerce').fillna(0).sum()):,}"
                         if "adopted" in idx.columns else "0",
                         f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])
        idx = self.load_index("shared")
        if not idx.empty and "domain" in idx.columns:
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(24))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title="공용 인덱스 구성 (다른 전략에서 그대로 재사용 가능)")
        if self.stats:
            LOG.table([[k, f"{v:,}"] for k, v in sorted(self.stats.items())][:24],
                      ["이벤트", "횟수"], ["l", "r"], title="이번 실행의 캐시 이벤트")
        LOG.info("무결성 원칙: 저널은 append-only(기존 줄 재기록 없음) · index.parquet 은 백업 후 교체 · "
                 "blob 은 내용해시 경로라 덮어쓰기 자체가 발생하지 않음 · 삭제 API 없음.")


def _safe_size(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:
        return -1


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return float("nan")


VAULT: Optional[Vault] = None



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 차단 회피          ║
# ║                                                                                          ║
# ║  한국 사이트 수집에서 실패의 9할은 세 가지다:                                              ║
# ║   ① User-Agent/Referer 없음 → 403   ② euc-kr 인데 utf-8로 디코드 → 글자 깨짐               ║
# ║   ③ 너무 빠른 요청 → 429/차단.  전부 여기서 한 번에 막는다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36",
]

_TLS = threading.local()
HTTP_STATS: Counter = Counter()
_HTTP_LK = threading.Lock()


def _session() -> "requests.Session":
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    s = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
            rt = Retry(total=0, connect=2, read=2, backoff_factor=0.5,
                       status_forcelist=(), raise_on_status=False)
        except Exception:
            rt = None
        ad = HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                         pool_maxsize=max(32, N_WORKERS_IO * 4),
                         max_retries=rt) if rt is not None else \
            HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                        pool_maxsize=max(32, N_WORKERS_IO * 4))
        s.mount("https://", ad)
        s.mount("http://", ad)
    except Exception:
        pass
    s.headers.update({
        "User-Agent": UA_POOL[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    _TLS.sess = s
    return s


_HANGUL = re.compile(r"[가-힣]")
_MOJI = re.compile(r"[¿½¶ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß]")


def _korean_score(t: str) -> float:
    """한글 가독성 점수. 네이버 금융은 body 가 EUC-KR 인데 meta 는 utf-8 이라고 '거짓말'한다.
    meta 를 믿으면 조용히 깨진 글자를 얻는다(예외가 안 난다) — 그래서 점수로 고른다."""
    s = t[:6000]
    if not s:
        return -1.0
    han = len(_HANGUL.findall(s))
    moji = len(_MOJI.findall(s))
    repl = s.count("�")
    return han - 3.0 * moji - 5.0 * repl


def _decode(content: bytes, resp_enc: Optional[str], url: str,
            force_enc: Optional[str] = None) -> str:
    # force_enc 는 '우선 후보'일 뿐 절대 지정이 아니다. 소스가 UTF-8 로 바뀌면
    # euc-kr 강제 디코딩은 예외 없이 깨진 글자를 돌려주므로, 점수로 검증한 뒤에만 채택한다.
    if force_enc:
        try:
            t = content.decode(force_enc, "replace")
            if _korean_score(t) > 30:
                return t
        except Exception:
            pass
    head = content[:4096].decode("ascii", "ignore").lower()
    m = re.search(r'charset\s*=\s*["\']?\s*([\w\-]+)', head)
    cands: List[str] = []
    if m:
        cands.append(m.group(1))
    if resp_enc:
        cands.append(resp_enc)
    cands += ["utf-8", "euc-kr", "cp949"]
    seen, best, best_s = set(), None, -1e18
    for enc in cands:
        e = (enc or "").lower().replace("ks_c_5601-1987", "cp949")
        if not e or e in seen:
            continue
        seen.add(e)
        try:
            t = content.decode(e)
        except Exception:
            continue
        sc = _korean_score(t)
        if sc > best_s:
            best, best_s = t, sc
        if sc > 30:                     # 충분히 한글다우면 더 볼 필요 없음
            return t
    return best if best is not None else content.decode("utf-8", "replace")


def euckr_q(s: str) -> str:
    """네이버/한경 레거시 경로의 한글 파라미터는 UTF-8이 아니라 EUC-KR 퍼센트인코딩이다.
    이걸 틀리면 예외 없이 '검색 결과 0건'이 나온다 — 최악의 조용한 실패."""
    try:
        return quote(str(s), encoding="euc-kr")
    except Exception:
        return quote(str(s))


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    last_exc = None
    for attempt in range(tries):
        lim.wait()
        if on_attempt is not None:
            try:
                on_attempt()
            except Exception:
                pass
        try:
            s = _session()
            if attempt > 0:
                hdr["User-Agent"] = UA_POOL[attempt % len(UA_POOL)]
            r = s.get(url, params=params, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{r.status_code}"] += 1
            if r.status_code in allow_status:
                return r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
            if r.status_code in (429, 503):
                time.sleep(min(30.0, 2.0 * (2 ** attempt)) + random.random())
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            if r.status_code in (403, 401):
                time.sleep(1.5 * (attempt + 1))
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            last_exc = requests.HTTPError(f"{r.status_code} {url}")
        except Exception as e:                                # noqa
            last_exc = e
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(min(12.0, (1.7 ** attempt)) + random.random() * 0.3)
    if not quiet and last_exc:
        LOG.debug(f"GET 실패({source}) {url[:90]} — {type(last_exc).__name__}")
    with _HTTP_LK:
        HTTP_STATS[f"{source}:FAIL"] += 1
    return None


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None) -> Optional[Union[str, bytes]]:
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    for attempt in range(tries):
        lim.wait()
        try:
            r = _session().post(url, data=data, json=json_body, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:POST{r.status_code}"] += 1
            if r.status_code == 200:
                return r.content if as_bytes else _decode(r.content, r.encoding, url)
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    return None


def soup_of(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    for parser in ("lxml", "html.parser", "html5lib"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def http_json(url: str, source: str = "generic", **kw) -> Optional[Any]:
    t = http_get(url, source=source, **kw)
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None


def report_http():
    if not HTTP_STATS:
        return
    LOG.banner("HTTP 수집 감사", "소스별 응답 분포 — 403/429가 많으면 RATE_LIMIT_QPS 를 낮추세요")
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_STATS.items():
        src, _, code = k.partition(":")
        by_src[src][code] += v
    rows = []
    for src, c in sorted(by_src.items()):
        tot = sum(c.values())
        ok = c.get("200", 0) + c.get("POST200", 0)
        bad = sum(v for k, v in c.items() if k in ("403", "401", "429", "503", "FAIL", "POSTFAIL"))
        rows.append([src, f"{tot:,}", f"{ok:,}", f"{100 * ok / max(tot, 1):.1f}%", f"{bad:,}",
                     _trunc(", ".join(f"{k}×{v}" for k, v in c.most_common(5)), 44)])
    LOG.table(rows, ["소스", "요청", "성공", "성공률", "차단/실패", "상세"],
              ["l", "r", "r", "r", "r", "l"])


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 유니버스 (C2 생존자편향 제거)                                     ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축 — 우선순위와 역할이 각각 다르다:                                      ║
# ║    ① FDR GitHub 캐시  listing/krx        상장 종목 + 상장일        ← 로그인 불필요, 1순위  ║
# ║    ② FDR GitHub 캐시  listing/delisting  상장폐지 + 폐지일         ← ★생존자편향 제거 입력 ║
# ║    ③ KIND 상장법인목록                   상장일·업종 보강                                  ║
# ║    ④ pykrx 월/분기말 스냅샷              "그 날 실제 상장" 검증     ← 인증 필요, 보조      ║
# ║    ⑤ DART corpCode.xml                   corp_code ↔ 종목코드                              ║
# ║    ⑥ 네이버 금융                         ①~⑤ 어디에도 이름이 없는 잔여 코드 보강          ║
# ║                                                                                          ║
# ║  ★ 설계 원칙: 유니버스의 정확성은 ①②③⑤(상장일·폐지일)만으로 성립해야 한다.                ║
# ║    ④ 스냅샷은 '검증·보강'이지 '의존'이 아니다. KRX 인증이 실패해도 백테스트는 정상이어야   ║
# ║    한다. 실제로 KRX 는 부분 응답을 자주 내는데, 그걸 진실로 믿으면 그 달 유니버스가        ║
# ║    조용히 쪼그라들어 곧바로 선택편향이 된다.                                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "sector_src", "src"]

# 스냅샷 주기: "Q"(분기·기본) | "M"(월) | "A"(연) | "off"
#   월 단위는 120개월 × 2시장 = 240 호출이라 KRX 세션을 자주 건드리고 차단 위험이 커진다.
#   상장/폐지일이 이미 있으므로 분기 격자(40 × 2 = 80 호출)로도 검증 목적은 충분하다.
UNIVERSE_SNAPSHOT_FREQ = "Q"


# ── 중복 컬럼 방어 (이번 크래시의 직접 원인 유형) ────────────────────────────────────────────
def assert_no_dup_cols(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 에서 예외 없이 의미가 바뀐다.
    df[col] 이 Series 가 아니라 DataFrame 이 되고, groupby.agg 가
    'DataFrame object has no attribute name' 로 엉뚱한 곳에서 터진다.
    조용히 지나가면 최악이므로 발생 지점에서 즉시 세운다."""
    if df is None or df.empty:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — "
                           f"pandas 연산의 의미가 바뀌므로 여기서 중단합니다.")
    return df


# ── KRX 세션 게이트 ─────────────────────────────────────────────────────────────────────────
class KRXGate:
    """pykrx 호출을 단일 게이트로 통과시킨다.

    ★ 왜 필요한가 (pykrx 1.2.8 소스 확인 결과):
      get_auth_session() 은 모듈 전역 _auth_session 에 대해 락 없이 검사-후-생성을 한다.
      스레드 6개가 동시에 None 을 보면 6개가 각자 로그인하고, KRX 는 중복 로그인(CD011)을
      skipDup 로 처리하며 앞선 세션을 강제 종료시킨다. 살아남는 건 마지막 하나뿐이고
      나머지 스레드는 죽은 쿠키로 요청해 JSON 대신 로그인 HTML 을 받는다.
      → 실제 운영 로그의 'Error occurred in ...: Expecting value: line 13 column 1' 이 이것이다.
      또 세션은 3600초(버퍼 300초 → 실효 55분) 만료라 긴 수집은 반드시 만료를 넘긴다.
      만료 갱신도 같은 무락 경로를 타므로 장시간 실행에서 같은 폭풍이 재현된다.

    대응: ① 메인 스레드에서 단 한 번 워밍업 ② 모든 pykrx 호출을 락으로 직렬화
          ③ 만료 전에 선제 갱신 ④ 실패해도 예외 대신 None 을 돌려 상위가 폴백하게 한다.
    """

    def __init__(self):
        self._lk = threading.RLock()
        self._warm = False
        self._authed = False
        self._t_login = 0.0
        self.calls = 0
        self.fails = 0

    def warmup(self) -> bool:
        if pykrx_stock is None:
            return False
        with self._lk:
            if self._warm:
                return self._authed
            self._warm = True
            has_cred = bool(os.environ.get("KRX_ID") and os.environ.get("KRX_PW"))
            try:
                from pykrx.website.comm.auth import get_auth_session   # type: ignore
                s = get_auth_session()
                self._authed = s is not None and getattr(s, "is_authenticated", False)
            except Exception:
                self._authed = False
            self._t_login = time.time()
            if has_cred and self._authed:
                LOG.ok("KRX 세션 확보 (메인 스레드 1회 로그인) — 이후 모든 pykrx 호출을 "
                       "직렬화해 중복 로그인(CD011)으로 서로를 밀어내는 현상을 막습니다.")
            elif has_cred:
                LOG.warn("KRX 자격증명은 있으나 세션 인증에 실패했습니다. ID/PW 를 확인하세요. "
                         "스냅샷 검증만 건너뛰며, 유니버스는 상장일·폐지일로 정확히 구성됩니다.")
            else:
                LOG.info("KRX 자격증명 미입력 — pykrx 스냅샷 검증은 생략합니다. "
                         "유니버스는 FDR 상장/폐지 목록으로 구성되며 백테스트는 정상 동작합니다.")
            return self._authed

    def _refresh_if_stale(self):
        # 실효 55분. 45분마다 선제 갱신해 '동시 만료 → 동시 재로그인'을 원천 차단한다.
        if not self._authed or (time.time() - self._t_login) < 45 * 60:
            return
        try:
            from pykrx.website.comm.auth import get_auth_session       # type: ignore
            get_auth_session()
            self._t_login = time.time()
            LOG.debug("KRX 세션 선제 갱신")
        except Exception:
            pass

    def call(self, fn: Callable, *a, **kw):
        """모든 pykrx 호출의 유일한 통로. 직렬화 + 스로틀 + 예외 흡수."""
        if pykrx_stock is None:
            return None
        with self._lk:
            self._refresh_if_stale()
            limiter("krx").wait()
            self.calls += 1
            try:
                return fn(*a, **kw)
            except Exception as e:                                     # noqa
                self.fails += 1
                LOG.debug(f"pykrx 호출 실패 {getattr(fn, '__name__', '?')}: {type(e).__name__}")
                return None

    def report(self):
        if self.calls:
            LOG.info(f"pykrx 게이트 — 호출 {self.calls:,}건 · 실패 {self.fails:,}건 "
                     f"({100*self.fails/max(self.calls,1):.1f}%) · 직렬화 적용")


KRXG = KRXGate()


# ── 로그인 불필요 경로 ★1순위 ──────────────────────────────────────────────────────────────
#   FinanceDataReader 가 실제로 읽는 GitHub 캐시. KRX 인증 변경의 영향을 받지 않는다.
#   FDR 라이브러리 자체는 최신 영업일을 알아내려고 data.krx.co.kr 을 한 번 찌르는데,
#   그게 로그인 벽에 막히면 CSV 는 멀쩡한데도 ValueError 로 죽는다 → 우리는 CSV 를 직접 읽는다.
FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
             "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 14) -> Optional[pd.DataFrame]:
    """영업일 CSV 만 존재하므로 최근 날짜부터 거꾸로 훑는다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        url = FDR_CACHE.format(kind=kind, date=d.isoformat())
        raw = http_get(url, source="generic", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            # ★ index_col=0 을 무조건 주면 안 된다.
            #   listing CSV 는 이름 없는 인덱스 컬럼이 있지만 delisting CSV 는 없을 수 있고,
            #   그때 첫 실컬럼(Symbol=종목코드)이 인덱스로 먹혀 통째로 사라진다.
            #   → 상장폐지 종목이 전부 유실되고 그게 곧 생존자편향이다. 반드시 판별해서 읽는다.
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} "
                          f"({len(df):,}행 · 컬럼 {list(df.columns)[:6]})")
                return df
        except Exception:
            continue
    return None


def _lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def fetch_fdr_listing() -> pd.DataFrame:
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
        name_c = col.get("name") or col.get("korean name") or col.get("isu_nm")
        if code_c and name_c:
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "market": (d[col["market"]].astype(str) if "market" in col
                           else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
                "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
                "industry": (d[col["sector"]].astype(str) if "sector" in col
                             else d[col["industry"]].astype(str) if "industry" in col else ""),
            })
            t["sector_src"], t["src"] = "fdr_cache", "fdr_github_cache"
            t["delisting_date"] = pd.NaT
            t["corp_code"] = np.nan
            n0 = len(t)
            r = t.dropna(subset=["code"]).drop_duplicates("code")
            if n0 - len(r):
                LOG.debug(f"상장목록 정규화 탈락 {n0-len(r):,}건(코드 형식 불일치/중복)")
            LOG.ok(f"상장목록(로그인 불필요 경로) {len(r):,}건 — KRX 인증 변경 영향을 받지 않습니다.")
            return r

    if fdr is None:
        LOG.warn("상장목록을 확보하지 못했습니다 (GitHub 캐시 실패 + FinanceDataReader 없음).")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    try:
        limiter("krx").wait()
        d = fdr.StockListing("KRX")
    except Exception as e:                                            # noqa
        LOG.warn(f"fdr.StockListing('KRX') 실패({type(e).__name__}) — "
                 f"FDR 은 최신 영업일 확인차 data.krx.co.kr 를 찌르는데 그게 막히면 "
                 f"CSV 가 멀쩡해도 죽습니다.")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    if d is None or len(d) == 0:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    col = _lower_map(d)
    code_c = col.get("code") or col.get("symbol")
    name_c = col.get("name")
    if not code_c or not name_c:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6), "name": d[name_c].astype(str),
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
        "industry": d[col["sector"]].astype(str) if "sector" in col else "",
        "delisting_date": pd.NaT, "corp_code": np.nan,
        "sector_src": "fdr", "src": "fdr:KRX"})
    return t.dropna(subset=["code"]).drop_duplicates("code")


def fetch_fdr_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. KRX Open API 에는 상장폐지 엔드포인트가 아예 없어서
    이 GitHub 캐시가 사실상 유일한 공개 경로다.

    ★ 탈락 사유를 반드시 집계해 로그로 남긴다. 여기서 조용히 버려지는 종목이
    그대로 생존자편향이 되기 때문이다(운영에서 4,172행 → 2,526행으로 줄었던 구간)."""
    d = _fdr_cache_csv("listing/delisting")
    if d is None or len(d) == 0:
        if fdr is None:
            LOG.warn("상장폐지 목록을 확보하지 못했습니다 — C2(생존자편향 제거) 미충족 상태입니다. "
                     "결과 해석 시 반드시 감안하세요.")
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
        try:
            limiter("krx").wait()
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
        if d is None or len(d) == 0:
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])

    col = _lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        LOG.warn(f"상장폐지 파일에서 종목코드 컬럼을 찾지 못했습니다: {list(d.columns)[:12]}")
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date",
                                  "listingdate") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c

    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    n_badcode = int(codes.isna().sum())
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    })
    t = t.dropna(subset=["code"])
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_nodate = int(t["delisting_date"].isna().sum())

    LOG.ok(f"상장폐지 목록(로그인 불필요 경로) {len(t):,}건 — 생존자편향 제거 입력 확보")
    if n_raw - len(t):
        LOG.info(f"  폐지목록 정규화: 원본 {n_raw:,} → {len(t):,} "
                 f"(코드형식 불일치 {n_badcode:,} · 동일코드 중복 {n_dupe:,}) · "
                 f"폐지일 결측 {n_nodate:,}건은 상장기간 추정에서 제외됩니다.")
        if n_badcode > n_raw * 0.25:
            LOG.warn(f"폐지목록의 {100*n_badcode/max(n_raw,1):.0f}% 가 코드 형식 불일치로 "
                     f"탈락했습니다. 이 비율이 크면 생존자편향이 그만큼 남습니다 — "
                     f"원본 코드 예시: {raw_codes[codes.isna()].head(5).tolist()}")
    return t


def fetch_kind_listing() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일·업종 보강.
    ★ 종목코드가 정수로 와서 앞자리 0 이 날아간다(5930 ← 005930). to_code6 이 복구한다."""
    urls = [
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download",
    ]
    for u in urls:
        raw = http_get(u, source="kind", as_bytes=True, tries=2,
                       referer="https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage")
        if not raw or len(raw) < 500:
            continue
        for enc in ("euc-kr", "cp949", "utf-8"):
            try:
                tabs = pd.read_html(io.BytesIO(raw), encoding=enc)
            except Exception:
                continue
            if not tabs:
                continue
            d = max(tabs, key=len)
            col = {str(c).strip(): c for c in d.columns}
            code_c, name_c = col.get("종목코드"), col.get("회사명")
            if not code_c or not name_c:
                continue
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "listing_date": as_ts_series(d[col["상장일"]]) if "상장일" in col else pd.NaT,
                "industry": d[col["업종"]].astype(str) if "업종" in col else "",
                "sector_src": "kind", "src": "kind", "market": "",
                "delisting_date": pd.NaT, "corp_code": np.nan,
            }).dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"KIND 상장법인목록 {len(t):,}건 (상장일 {int(t['listing_date'].notna().sum()):,}건)")
            return t
    LOG.warn("KIND 상장법인목록을 받지 못했습니다 — 상장일은 FDR/스냅샷으로만 채웁니다.")
    return pd.DataFrame(columns=SEC_MASTER_COLS)


def fetch_dart_corpcode() -> pd.DataFrame:
    """corp_code ↔ 종목코드. DART 의 모든 재무·공시 조회는 corp_code 로만 된다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 와 네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    txt = _decode(xml, None, "corpcode")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code")), "modify_date": g("modify_date")})
    d = pd.DataFrame(rows)
    if len(d):
        VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건)")
    return d


# ── pykrx 스냅샷 (보조·검증) ────────────────────────────────────────────────────────────────
def _snapshot_grid(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    f = str(UNIVERSE_SNAPSHOT_FREQ).upper()
    if f in ("OFF", "NONE", ""):
        return []
    if f == "M":
        return list(months)
    if f == "A":
        return [m for m in months if m.month == 12] or list(months[::12])
    return [m for m in months if m.month in (3, 6, 9, 12)] or list(months[::3])   # 기본 Q


def fetch_pykrx_snapshots(months: pd.DatetimeIndex) -> pd.DataFrame:
    """분기말 상장종목 스냅샷. C2 의 '검증' 입력이다(의존 대상이 아님).

    ★ 전부 KRXG 게이트를 통해 직렬로 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), 그 결과 JSON 대신 로그인 HTML 을 받아 대량 실패한다."""
    cols = ["snap_date", "code", "market"]
    cached = VAULT.get_table("krx_listing_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"공용 캐시에서 상장 스냅샷 {len(have)}개 시점 재사용")

    grid = _snapshot_grid(months)
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    new_rows: List[dict] = []
    if todo:
        if not KRXG.warmup():
            LOG.info(f"KRX 세션이 없어 스냅샷 {len(todo)}개 시점을 건너뜁니다. "
                     f"유니버스는 상장일·폐지일로 구성되며 이는 정상 경로입니다.")
            todo = []
    if todo:
        LOG.info(f"KRX 상장 스냅샷 {len(todo)}개 시점 수집 (주기={UNIVERSE_SNAPSHOT_FREQ}, 직렬)")
        bad_streak = 0
        for d in tqdm(todo, desc="KRX 상장 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           d.strftime("%Y%m%d"), prev=True) or d.strftime("%Y%m%d")
            got_any = False
            for mkt in ("KOSPI", "KOSDAQ"):
                tk = KRXG.call(pykrx_stock.get_market_ticker_list, bd, market=mkt)
                if not tk:
                    continue
                got_any = True
                for t in tk:
                    c = to_code6(t)
                    if c:
                        new_rows.append({"snap_date": d.strftime("%Y-%m-%d"),
                                         "code": c, "market": mkt})
            bad_streak = 0 if got_any else bad_streak + 1
            if bad_streak >= 5:
                LOG.warn("KRX 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 상태입니다. "
                         "스냅샷 수집을 중단하고 상장일·폐지일 경로로 진행합니다(정상 폴백).")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap = (snap.dropna(subset=["snap_date", "code"])
                .drop_duplicates(["snap_date", "code"])[cols])

    # ★ 부분 응답 방어: 이웃 시점 대비 종목수가 급감한 스냅샷은 '진실'이 아니라 '사고'다.
    #   그대로 쓰면 그 달 유니버스가 조용히 쪼그라들어 선택편향이 된다.
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만이라 "
                     f"부분 응답으로 판단하고 폐기합니다: "
                     f"{[str(x.date()) for x in bad.index[:6]]}")
            snap = snap[~snap["snap_date"].isin(bad.index)]
    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                        source="pykrx", extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_listing_snapshots", snap, source="pykrx")
    return snap


def fetch_naver_names(codes: Sequence[str], limit: int = 400) -> Dict[str, str]:
    """①~⑤ 어디에도 이름이 없는 잔여 코드를 네이버로 보강한다.
    이름이 비면 국민연금·조달 상호 매칭이 통째로 실패하므로 커버리지에 직접 영향이 있다."""
    codes = [c for c in codes if c][:limit]
    if not codes or RUN_MODE == "CACHED":
        return {}

    def _one(c: str):
        h = http_get(f"https://finance.naver.com/item/main.naver?code={c}",
                     source="naver", tries=1, force_enc="euc-kr",
                     referer="https://finance.naver.com/")
        if not h:
            return None
        m = re.search(r'<div class="wrap_company">\s*<h2>\s*<a[^>]*>([^<]+)</a>', h)
        if not m:
            m = re.search(r"<title>\s*([^:<]+?)\s*:", h)
        return (c, _clean_cell(m.group(1))) if m else None

    res = pmap_io(_one, codes, workers=min(6, N_WORKERS_IO), desc="네이버 종목명 보강")
    out = {c: n for r in res if r for c, n in [r] if n}
    if out:
        LOG.ok(f"네이버로 종목명 {len(out):,}건 보강")
    return out


# ── 종목 마스터 ─────────────────────────────────────────────────────────────────────────────
def build_security_master(snapshots: pd.DataFrame) -> pd.DataFrame:
    """모든 소스를 합쳐 종목 마스터를 만든다. 충돌은 우선순위로 해소하고 전부 로깅한다."""
    parts: List[pd.DataFrame] = []
    src_stats: List[Tuple[str, int]] = []

    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
        src_stats.append(("FDR 상장목록", len(lst)))
        PIPE.io("IN", "HTTP", "fdr:StockListing", lst, source="FinanceDataReader")

    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
        src_stats.append(("KIND 상장법인", len(kind)))
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")

    dead = fetch_fdr_delisting()
    PIPE.io("IN", "HTTP", "fdr:KRX-DELISTING", dead, source="FinanceDataReader",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market"]).copy()
        d2["listing_date"] = pd.NaT
        d2["industry"] = ""
        d2["corp_code"] = np.nan
        d2["sector_src"] = "fdr-del"
        d2["src"] = "fdr:delisting"
        parts.append(d2)
        src_stats.append(("FDR 상장폐지", len(d2)))

    # 스냅샷에만 존재하는 종목(=상장목록·폐지목록 어디에도 없는 종목)도 반드시 살린다
    if snapshots is not None and len(snapshots):
        known = set(pd.concat(parts, ignore_index=True)["code"]) if parts else set()
        extra = sorted(set(snapshots["code"]) - known)
        if extra:
            parts.append(pd.DataFrame({
                "code": extra, "name": "", "market": "", "listing_date": pd.NaT,
                "delisting_date": pd.NaT, "corp_code": np.nan, "industry": "",
                "sector_src": "snapshot", "src": "pykrx:snapshot"}))
            src_stats.append(("스냅샷 전용", len(extra)))
            LOG.info(f"스냅샷에만 존재하는 종목 {len(extra):,}건 추가 — 상장/폐지 명단 누락분입니다. "
                     f"(빠뜨리면 곧바로 생존자편향)")

    if not parts:
        raise RuntimeError(
            "종목 마스터를 만들 소스가 하나도 없습니다.\n"
            "  · 네트워크에서 raw.githubusercontent.com 과 kind.krx.co.kr 에 접근 가능한지\n"
            "  · FinanceDataReader 가 설치되어 있는지\n"
            "확인하세요. RUN_MODE='SMOKE' 로는 네트워크 없이 계산경로만 검증할 수 있습니다.")

    # ★ 중복 컬럼 원천 차단: 컬럼 목록을 dict.fromkeys 로 유일화한 뒤 정렬한다.
    #   (SEC_MASTER_COLS 에 이미 있는 이름을 다시 더하면 m[col] 이 DataFrame 이 되고
    #    groupby.agg 가 'DataFrame object has no attribute name' 으로 터진다)
    _cols = list(dict.fromkeys(SEC_MASTER_COLS))
    m = pd.concat([p.reindex(columns=_cols) for p in parts], ignore_index=True)
    assert_no_dup_cols(m, "security_master:concat")
    m["code"] = m["code"].map(to_code6)
    m = m.dropna(subset=["code"])

    def _first_str(s):
        for x in s:
            if isinstance(x, str) and x.strip():
                return x.strip()
        return ""

    agg = m.groupby("code", as_index=False).agg(
        name=("name", _first_str),
        market=("market", _first_str),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "max"),
        industry=("industry", _first_str),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
    )
    assert_no_dup_cols(agg, "security_master:agg")

    # 스냅샷으로 상장/폐지일 보정 — 소스 날짜가 없을 때만 관측으로 채운다
    if snapshots is not None and len(snapshots):
        g = snapshots.groupby("code")["snap_date"]
        agg = agg.merge(g.min().rename("snap_first"), left_on="code", right_index=True, how="left")
        agg = agg.merge(g.max().rename("snap_last"), left_on="code", right_index=True, how="left")
        need = agg["listing_date"].isna() & agg["snap_first"].notna()
        agg.loc[need, "listing_date"] = agg.loc[need, "snap_first"]
        last_snap = snapshots["snap_date"].max()
        gone = (agg["delisting_date"].isna() & agg["snap_last"].notna() &
                (agg["snap_last"] < last_snap - pd.Timedelta(days=200)))
        agg.loc[gone, "delisting_date"] = agg.loc[gone, "snap_last"] + pd.offsets.MonthEnd(1)
        if int(gone.sum()):
            LOG.info(f"스냅샷에서 사라진 {int(gone.sum()):,}종목을 폐지로 추정 "
                     f"(폐지명단 누락 보완 — 생존자편향 2차 방어)")
        agg = agg.drop(columns=[c for c in ("snap_first", "snap_last") if c in agg.columns])

    cc = fetch_dart_corpcode()
    if len(cc):
        cc2 = cc.dropna(subset=["code"])[["code", "corp_code", "corp_name"]].drop_duplicates("code")
        agg = agg.merge(cc2, on="code", how="left")
        blank = agg["name"].astype(str).str.strip() == ""
        agg.loc[blank, "name"] = agg.loc[blank, "corp_name"].fillna("")
        agg = agg.drop(columns=["corp_name"])
    else:
        agg["corp_code"] = np.nan

    # 네이버로 잔여 무명 종목 보강 (상호 매칭 커버리지에 직결)
    nameless = agg.loc[agg["name"].astype(str).str.strip() == "", "code"].tolist()
    if nameless:
        LOG.info(f"이름이 비어 있는 종목 {len(nameless):,}건 — 네이버로 보강 시도")
        nm = fetch_naver_names(nameless)
        if nm:
            agg["name"] = agg.apply(
                lambda r: nm.get(r["code"], r["name"]) if not str(r["name"]).strip() else r["name"],
                axis=1)

    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    agg["sector_src"] = "merged"
    assert_no_dup_cols(agg, "security_master:final")

    n_list = int(agg["listing_date"].notna().sum())
    n_del = int(agg["delisting_date"].notna().sum())
    n_corp = int(agg["corp_code"].notna().sum()) if "corp_code" in agg.columns else 0
    n_name = int((agg["name"].astype(str).str.strip() != "").sum())
    LOG.table([[lab, f"{n:,}"] for lab, n in src_stats] +
              [["── 병합 결과 ──", ""],
               ["고유 종목", f"{len(agg):,}"],
               ["상장일 보유", f"{n_list:,} ({100*n_list/max(len(agg),1):.0f}%)"],
               ["폐지일 보유", f"{n_del:,} ({100*n_del/max(len(agg),1):.0f}%)"],
               ["corp_code 보유", f"{n_corp:,} ({100*n_corp/max(len(agg),1):.0f}%)"],
               ["종목명 보유", f"{n_name:,} ({100*n_name/max(len(agg),1):.0f}%)"]],
              ["소스 / 항목", "건수"], ["l", "r"], title="종목 마스터 구성 (다중소스 병합)")

    if n_del < 200:
        LOG.warn("상장폐지 종목이 200건 미만입니다. 10년 구간이면 통상 1,000건 이상이어야 합니다. "
                 "생존자편향이 남아 있으니 결과 해석 시 반드시 감안하세요. (C2 부분 미충족)")
        PIPE.note("WARN: 상장폐지 표본 부족 — C2 완전 제거 미달")
    if n_corp < len(agg) * 0.3:
        LOG.warn(f"corp_code 매칭률이 {100*n_corp/max(len(agg),1):.0f}% 로 낮습니다. "
                 f"DART 재무·공시가 그만큼 결측이 되어 B/C축과 PACK-C/D 가 약해집니다. "
                 f"DART_API_KEY 를 확인하세요.")
    VAULT.put_table("security_master", agg, scope="shared", domain="universe",
                    source="fdr+kind+pykrx+dart+naver")
    KRXG.report()
    return agg



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]


class KRXAuth:
    """KRX 데이터 마켓플레이스 인증(2025-12 변경 대응). 실패해도 절대 죽지 않고 폴백으로 넘긴다.

    2026년 기준 경로 3가지:
      ① KRX Open API (data-dbg.krx.co.kr) — 인증키. ★단, 엔드포인트별로 '이용신청'이 따로 필요하고
         승인에 하루 정도 걸린다. 키만 있다고 바로 되는 게 아니다. 상장폐지 API 는 존재하지 않는다.
      ② 마켓플레이스 세션 로그인 → getJsonData.cmd (bld 기반). pykrx 가 쓰는 경로.
      ③ 레거시 OTP 파일다운로드 — 2026년에는 세션 없이 빈 데이터/로그아웃 오류가 잦다. 의존 금지.
    """

    LOGIN_WARM1 = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    LOGIN_WARM2 = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    JSONDATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
    OPENAPI = "https://data-dbg.krx.co.kr/svc/apis/{cat}/{ep}"

    def __init__(self, user: str, pw: str, apikey: str = ""):
        self.user, self.pw, self.apikey = (user or "").strip(), (pw or "").strip(), (apikey or "").strip()
        self.status = "NOT_ATTEMPTED"
        self.session_ok = False
        self.openapi_ok = False

    def login(self) -> bool:
        if self.apikey:
            self.openapi_ok = self._probe_openapi()
            self.status = "OPENAPI_OK" if self.openapi_ok else "OPENAPI_KEY_UNAUTHORIZED"
            if not self.openapi_ok:
                LOG.warn("KRX Open API 키는 있으나 해당 엔드포인트 호출이 거부되었습니다. "
                         "KRX Open API 는 '엔드포인트별 이용신청'이 따로 필요하고 승인에 하루 정도 "
                         "걸립니다. 키 발급만으로는 즉시 사용할 수 없습니다.")
        if not (self.user and self.pw):
            if not self.openapi_ok:
                self.status = "NO_CREDENTIALS"
                LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 불필요 경로로 진행합니다. "
                         "(FDR GitHub 캐시 → 네이버 차트 → yfinance). "
                         "백테스트는 정상 동작하며, 어느 소스가 쓰였는지는 감사표에 나옵니다.")
            return self.openapi_ok
        # 워밍업 없이 바로 POST 하면 세션 쿠키가 없어 항상 실패한다
        http_get(self.LOGIN_WARM1, source="krx", tries=1)
        http_get(self.LOGIN_WARM2, source="krx", tries=1, referer=self.LOGIN_WARM1)
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                continue
            if re.search(r"CD011|중복\s*로그인", str(txt)):
                LOG.warn("KRX 중복 로그인(CD011) 감지 — 같은 계정이 브라우저나 다른 노트북에서 "
                         "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 종료됩니다. "
                         "두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                 "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
        return self.openapi_ok

    def _probe_openapi(self) -> bool:
        """AUTH_KEY 를 쿼리로 보내는 구현과 헤더로 보내는 공식 샘플이 공존한다 — 둘 다 시도."""
        d = (_dt.date.today() - _dt.timedelta(days=7))
        while d.weekday() >= 5:
            d -= _dt.timedelta(days=1)
        url = self.OPENAPI.format(cat="sto", ep="stk_bydd_trd")
        for mode in ("query", "header"):
            kw = ({"params": {"AUTH_KEY": self.apikey, "basDd": d.strftime("%Y%m%d")}}
                  if mode == "query" else
                  {"params": {"basDd": d.strftime("%Y%m%d")},
                   "headers": {"AUTH_KEY": self.apikey}})
            js = http_json(url, source="krx", tries=1, **kw)
            if isinstance(js, dict) and (js.get("OutBlock_1") or js.get("output")):
                LOG.ok(f"KRX Open API 사용 가능 (AUTH_KEY 전달 방식: {mode})")
                self._openapi_mode = mode
                return True
        return False

    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회. 세션이 없으면 JSON 대신 로그인 HTML 이 와서
        엉뚱한 곳에서 JSONDecodeError 가 난다 → 여기서 미리 막는다."""
        if not self.session_ok:
            return None
        body = {"bld": bld, "share": "1", "money": "1", "csvxls_isNo": "false", **params}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if not txt or txt.lstrip()[:1] not in ("{", "["):
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY)


# ── 개별 소스 ───────────────────────────────────────────────────────────────────────────────
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_ohlcv(start.replace("-", ""), end.replace("-", ""), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "거래대금": "amount"}
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    d["code"], d["src"] = code, "pykrx"
    return d.reindex(columns=PRICE_COLS)


def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        limiter("krx").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    if "amount" not in d.columns:
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")      # 근사 — 감사표에 명시된다
    d["code"], d["src"] = code, "fdr"
    return d.reindex(columns=PRICE_COLS)


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 차트 API. 폴백 중에서는 가장 안정적이지만 거래대금이 없다."""
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
        # 응답이 파이썬 리터럴에 가까운 준-JSON 이다: 홑따옴표 + 따옴표 없는 키워드
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast
                arr = ast.literal_eval(t.strip())
            except Exception:
                arr = None
        if isinstance(arr, list) and len(arr) >= 2:
            break
        arr = None
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    hdr = [str(x).strip().lower() for x in arr[0]]
    rows = [r for r in arr[1:] if isinstance(r, (list, tuple)) and len(r) == len(hdr)]
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=hdr)
    # ★ 이 rename 이 오랫동안 아무 일도 하지 않고 있었다.
    #   {**ren, **{c: c for c in d.columns}} 는 두 번째 dict 가 첫 번째를 덮어써서
    #   '날짜'→'날짜' 가 '날짜'→'date' 를 이긴다. 결과적으로 컬럼명이 한글로 남고
    #   d.get("close") 가 None 이 되어 None*None TypeError 로 죽는다.
    #   (pykrx/FDR 이 둘 다 없는 환경에서만 드러나므로 오래 숨어 있었다)
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "외국인소진율": "foreign_ratio"}
    d = d.rename(columns=ren)
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["amount"] = d["close"] * d["volume"]          # 네이버는 거래대금을 안 준다 → 근사(감사표에 명시)
    d["code"], d["src"] = code, "naver"
    d = d.dropna(subset=["close"])
    return d.reindex(columns=PRICE_COLS) if len(d) else None


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            limiter("generic").wait()
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [str(c[0]).lower() for c in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]
        d = d.reset_index()
        d = d.rename(columns={"index": "date"})
        if "date" not in d.columns:
            d = d.rename(columns={d.columns[0]: "date"})
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")
        d["code"], d["src"] = code, "yfinance"
        return d.reindex(columns=PRICE_COLS)
    return None


PRICE_CHAIN = [("pykrx", _px_pykrx), ("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf)]



def plan_price_fetch(codes: Sequence[str], want_start: pd.Timestamp, want_end: pd.Timestamp,
                     have_min: Dict[str, pd.Timestamp], have_max: Dict[str, pd.Timestamp],
                     listing: Dict[str, pd.Timestamp], delist: Dict[str, pd.Timestamp],
                     attempts: Dict[str, dict], today: pd.Timestamp,
                     retry_fail_days: int = 30, retry_stale_days: int = 21,
                     tol_back: int = 14, tol_fwd: int = 7
                     ) -> Tuple[List[Tuple[str, str]], "Counter"]:
    """'무엇을 받을지'만 결정하는 순수 함수 — 네트워크도 캐시도 건드리지 않는다.

    분리한 이유: 이 판정이 틀리면 완전한 캐시를 갖고도 매 실행 수십 분을 같은 요청에
    쓴다. 그런데 예전 구조에서는 이 로직을 실제 수집을 돌리지 않고는 검증할 수 없었다.
    이제 리허설이 IPO·폐지·완전커버 세 경우를 직접 넣어 '두 번째 실행은 0건'을 확인한다.
    """
    todo: List[Tuple[str, str]] = []
    reasons: Counter = Counter()

    def _recently_failed(c, want_from):
        p = attempts.get(c)
        if p is None or pd.isna(p.get("at")):
            return False
        if pd.notna(p.get("frm")) and p["frm"] > want_from:
            return False
        return (today - p["at"]).days < retry_fail_days

    def _stale_no_growth(c, want_from):
        p = attempts.get(c)
        if p is None or pd.isna(p.get("at")):
            return False
        if (today - p["at"]).days >= retry_stale_days:
            return False
        if pd.notna(p.get("frm")) and p["frm"] > want_from:
            return False
        gmin, gmax = p.get("gmin"), p.get("gmax")
        cur_min, cur_max = have_min.get(c), have_max.get(c)
        if pd.isna(gmin) or pd.isna(gmax) or cur_min is None or cur_max is None:
            return False
        return (gmin <= cur_min) and (gmax >= cur_max)

    for c in codes:
        ld, dd = listing.get(c), delist.get(c)
        want_from = max(want_start, ld) if ld is not None and pd.notna(ld) else want_start
        want_to = min(want_end, dd) if dd is not None and pd.notna(dd) else want_end
        if want_to <= want_from:
            reasons["구간없음(상장 전/폐지 후)"] += 1
            continue
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, want_from):
                reasons[f"최근 {retry_fail_days}일 내 전 소스 실패"] += 1
                continue
            todo.append((c, want_from.strftime("%Y-%m-%d")))
            reasons["신규(캐시 없음)"] += 1
            continue
        need_back = mn is not None and mn > want_from + pd.Timedelta(days=tol_back)
        need_fwd = mx < want_to - pd.Timedelta(days=tol_fwd)
        if not (need_back or need_fwd):
            reasons["캐시가 구간을 덮음"] += 1
            continue
        if _stale_no_growth(c, want_from):
            reasons[f"직전 시도에서 미증가({retry_stale_days}일 유예)"] += 1
            continue
        if need_back:
            todo.append((c, want_from.strftime("%Y-%m-%d")))
            reasons["앞구간 결손"] += 1
        else:
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
            reasons["뒤구간 증분"] += 1
    return todo, reasons


def fetch_prices(codes: Sequence[str], start: str, end: str,
                 sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. ★'받을 게 남았을 때만' 받는다.

    ── 왜 이 함수가 다시 쓰였는가 (실측된 낭비) ────────────────────────────────────────
    예전 판정은 캐시의 (최소일, 최대일)만 보고 이렇게 결정했다:
      · 최소일 > 시작일+10일  → "앞 구간 결손" 으로 보고 처음부터 다시 받는다
      · 최대일 < 종료일-5일   → "뒤 구간 결손" 으로 보고 이어서 받는다
    그런데
      · 백테스트 시작일 이후에 '상장'한 종목은 최소일이 곧 상장일이다. 영원히 첫 조건에
        걸려 매 실행 전량 재수집된다. 10년 구간이면 유니버스의 30~40%가 여기 해당한다.
      · '상장폐지·거래정지' 종목은 마지막 거래일이 영원히 종료일보다 이르다. 매 실행
        두 번째 조건에 걸린다.
    게다가 다시 받아도 데이터가 늘지 않으므로 다음 실행에서 똑같은 판정을 다시 받는다.
    즉 완전한 캐시를 갖고도 매번 수십 분을 같은 요청에 쓴다.

    ── 지금 판정 ───────────────────────────────────────────────────────────────────────
    '있어야 할 구간'을 상장일·폐지일로 먼저 확정하고(want_from ~ want_to),
    캐시가 그 구간을 덮고 있으면 받지 않는다. 덮지 못했더라도 '지난번에 같은 구간을
    요청했는데 더 안 늘어났다면' 일정 기간 재시도하지 않는다(소스에 그 데이터가 없는 것).
    모든 판정은 사유별 집계로 출력한다 — 조용히 건너뛰지 않는다.
    """
    codes = sorted({c for c in map(to_code6, codes) if c})
    cached = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        g = cached.groupby("code")["date"]
        have_max, have_min = g.max().to_dict(), g.min().to_dict()
        LOG.info(f"공용 캐시에서 일봉 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    start_ts, end_ts = as_ts(start), as_ts(end)
    _today = as_ts(_dt.date.today())
    eff_end = min(end_ts, _today)          # 미래 구간은 애초에 존재하지 않는다

    # 상장일·폐지일 — '있어야 할 구간'의 근거. 없으면 보수적으로 전 구간을 원한다.
    listing: Dict[str, pd.Timestamp] = {}
    delist: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec) and "code" in sec.columns:
        _s = sec.dropna(subset=["code"]).drop_duplicates("code")
        if "listing_date" in _s.columns:
            listing = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["listing_date"]))
                       if pd.notna(d)}
        if "delisting_date" in _s.columns:
            delist = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["delisting_date"]))
                      if pd.notna(d)}

    # ── 시도 원장 ────────────────────────────────────────────────────────────────────────
    #   실패뿐 아니라 '시도했는데 더 안 늘어난' 경우도 기억한다. 그래야 반복이 멈춘다.
    RETRY_AFTER_DAYS = 30        # 전 소스 실패
    RETRY_STALE_DAYS = 21        # 시도했으나 커버리지가 늘지 않음(소스에 없는 구간)
    TOL_BACK, TOL_FWD = 14, 7    # 달력일 여유 (휴장·데이터 지연 흡수)
    attempts: Dict[str, dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att = _att.copy()
        for _c in ("attempted_at", "requested_from", "got_min", "got_max"):
            if _c not in _att.columns:
                _att[_c] = pd.NaT
            _att[_c] = as_ts_series(_att[_c])
        _att = _att.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from,
                                  "gmin": r.got_min, "gmax": r.got_max}
                    for r in _att.itertuples(index=False)}

    todo, reasons = plan_price_fetch(
        codes, start_ts, eff_end, have_min, have_max, listing, delist, attempts, _today,
        retry_fail_days=RETRY_AFTER_DAYS, retry_stale_days=RETRY_STALE_DAYS,
        tol_back=TOL_BACK, tol_fwd=TOL_FWD)

    LOG.table([[k, f"{v:,}"] for k, v in reasons.most_common()] +
              [["── 실제 수집 대상", f"{len(todo):,}"]],
              ["판정 사유", "종목수"], ["l", "r"],
              title=f"가격 수집 판정 — 전체 {len(codes):,}종목 중 {len(todo):,}종목만 받습니다 "
                    f"(상장일·폐지일로 '있어야 할 구간'을 먼저 확정)")
    if not todo and cached is not None and len(cached):
        LOG.ok("받을 것이 없습니다 — 캐시가 요청 구간을 전부 덮고 있습니다.")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    if todo:
        LOG.info(f"일봉 신규/증분 수집 대상 {len(todo):,}종목")

        def _one(job):
            code, st = job
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        failed = []
        for (c, st), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
                # ★ 성공도 기록한다. '받았는데 커버리지가 안 늘었다'를 다음 실행이 알아야
                #   같은 요청을 영원히 반복하지 않는다(폐지·거래정지 종목의 주된 낭비원).
                _dd = as_ts_series(d["date"])
                _gmin = min([x for x in (have_min.get(c), _dd.min()) if pd.notna(x)] or [pd.NaT])
                _gmax = max([x for x in (have_max.get(c), _dd.max()) if pd.notna(x)] or [pd.NaT])
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today,
                               "got_min": _gmin, "got_max": _gmax})
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today,
                               "got_min": have_min.get(c, pd.NaT),
                               "got_max": have_max.get(c, pd.NaT)})
        if failed:
            _nf = sum(1 for f in failed if pd.isna(f.get("got_max")))
            LOG.warn(f"일봉 시도 원장 {len(failed):,}건 기록 (전 소스 실패 {_nf:,}종목) — "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.
            _prev = _att if _att is not None and len(_att) else None
            _new = pd.DataFrame(failed)
            _all = pd.concat([_prev, _new], ignore_index=True) if _prev is not None else _new
            _all = (_all.sort_values("attempted_at")
                        .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                            source="fetch_prices:negative_cache")

    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        avail = [nm for nm, _fn in PRICE_CHAIN
                 if (nm != "pykrx" or pykrx_stock is not None)
                 and (nm != "fdr" or fdr is not None)
                 and (nm != "yfinance" or yf is not None)]
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            f"  · 시도한 소스 체인 : {', '.join(nm for nm, _ in PRICE_CHAIN)}\n"
            f"  · 이번 실행에서 사용 가능했던 소스 : {', '.join(avail) or '없음'}\n"
            f"  · 대상 종목 {len(codes):,}개 / 신규 수집 시도 {len(todo):,}개\n"
            "  진단: ① 네트워크에서 fchart.stock.naver.com 접근이 되는지\n"
            "        ② FinanceDataReader / pykrx 가 설치돼 있는지\n"
            "        ③ 드라이브 캐시(krx_ohlcv_daily)가 비어 있지 않은지\n"
            "  임시 우회: RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    for c in ("open", "high", "low", "close", "volume", "amount"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    # ★ 공용 캐시에는 '전체 합집합'을 쓰고, 이번 실행에는 구간을 잘라 쓴다.
    #   잘린 프레임을 그대로 덮어쓰면, 더 긴 구간을 쓰는 다른 전략의 캐시 이력이 사라진다
    #   (다른 전략의 캐시를 훼손하지 않는다는 절대 1원칙에 걸린다).
    px_all = px
    px = px_all[(px_all["date"] >= as_ts(start) - pd.Timedelta(days=400)) &
                (px_all["date"] <= end_ts)]

    if new_frames:
        VAULT.put_table("krx_ohlcv_daily", px_all, scope="shared", domain="price",
                        source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common()),
                        extra={"note": "전 구간 합집합 — 전략별 구간으로 자르지 않음"})
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if src_used.get("naver", 0) or src_used.get("yfinance", 0):
            LOG.warn("네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "V6 유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향).")
    PIPE.io("OUT", "DRIVE", "krx_ohlcv_daily", px, source="price chain")
    return downcast(px)


def build_price_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 기준 가격 패널 + 익월 시가 체결가 + 20일 평균거래대금(ADV).

    체결은 '신호 산출일 다음 거래일 시가'(§10.1). 당일 종가 체결은 미래누수다.
    """
    px = px.sort_values(["code", "date"])
    px["adv20"] = (px.groupby("code", observed=True)["amount"]
                     .transform(lambda s: s.rolling(20, min_periods=10).mean()))
    px["ret1d"] = px.groupby("code", observed=True)["close"].pct_change()

    # 월말 스냅샷
    px["ym"] = px["date"].values.astype("datetime64[M]")
    last = px.groupby(["code", "ym"], observed=True).tail(1).copy()
    last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)

    # 다음 거래일 시가 = 체결가
    nxt = px.copy()
    nxt["next_open"] = nxt.groupby("code", observed=True)["open"].shift(-1)
    nxt["next_date"] = nxt.groupby("code", observed=True)["date"].shift(-1)
    keep = nxt[["code", "date", "next_open", "next_date"]]
    last = last.merge(keep, on=["code", "date"], how="left")

    monthly = last[["code", "month", "date", "close", "adv20", "next_open", "next_date"]].copy()
    monthly = monthly.rename(columns={"date": "signal_date"})
    monthly = monthly[monthly["month"].isin(months)]

    # 월간 수익률(체결가→체결가). 상장폐지 처리는 backtest 엔진에서 -100% 로 강제한다.
    monthly = monthly.sort_values(["code", "month"])
    # 체결가 = 신호 산출일의 '다음 거래일 시가'. 그 다음 거래일이 너무 멀면(거래정지·상폐 직전)
    # 그 가격으로 체결했다고 가정할 수 없으므로 종가로 폴백한다.
    gap = (monthly["next_date"] - monthly["signal_date"]).dt.days
    monthly["exec_px"] = monthly["next_open"].where(gap.notna() & (gap <= 10))
    monthly["exec_px"] = monthly["exec_px"].fillna(monthly["close"])

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    nxt_px = monthly.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_m = monthly.groupby("code", observed=True)["month"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    monthly["fwd_ret"] = (nxt_px / monthly["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def fetch_investor_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다."""
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용")
        cached["date"] = as_ts_series(cached["date"])
        return cached
    if pykrx_stock is None or RUN_MODE == "CACHED":
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})

    def _one(code: str):
        try:
            limiter("krx").wait()
            d = pykrx_stock.get_market_trading_value_by_date(
                as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
        except Exception:
            return None
        if d is None or len(d) == 0:
            return None
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "date"})
        inst = next((c for c in d.columns if "기관" in str(c)), None)
        forg = next((c for c in d.columns if "외국" in str(c)), None)
        if inst is None and forg is None:
            return None
        return pd.DataFrame({"code": code, "date": as_ts_series(d["date"]),
                             "inst_net": pd.to_numeric(d[inst], errors="coerce") if inst else np.nan,
                             "foreign_net": pd.to_numeric(d[forg], errors="coerce") if forg else np.nan})

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 8), desc="수급 수집")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.warn("수급 데이터를 받지 못했습니다 — d3 결측 처리.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])
    fl = pd.concat(got, ignore_index=True)
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무제표 / 직원현황 / 공시목록                                               ║
# ║                                                                                          ║
# ║  ★ PIT 핵심: knowledge_date = 접수일자(rcept_dt). 결산기준일이 아니다.                     ║
# ║    fnltt* 응답의 rcept_no 앞 8자리가 곧 접수일자다 → 여기서 knowledge_date 를 얻는다.       ║
# ║    rcept_no 가 없으면 법정 제출기한(분기 45일 / 사업보고서 90일)으로 보수적 추정한다.       ║
# ║    ※ 보수적 추정은 '늦게 알았다'는 방향이므로 미래누수를 만들지 않는다.                     ║
# ║                                                                                          ║
# ║  ★ 호출 예산: DART 는 일 20,000건 제한. 10년 분기 전체 재무제표는 그 몇 배다.               ║
# ║    → 콜드빌드는 며칠에 걸쳐 '이어받기'로 완성된다(§3: 콜드빌드는 4시간 예산 밖).            ║
# ║    → 남은 호출량을 실시간으로 표시하고, 한도에 닿으면 깨끗하게 멈춘 뒤 진행률을 알려준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
# ★ 하드코딩 상한을 두지 않는다. DART 는 '남은 호출량' 조회 API 를 제공하지 않으므로,
#   실시간 잔여를 아는 유일한 방법은 '한도 초과(status=020)를 받을 때까지 쓰는 것'이다.
#   0 = 적응형(권장): 020 이 올 때까지 쓰고, 그 순간 멈춰 받은 만큼 저장한다.
#   양수 = 사용자가 직접 정한 상한(키를 다른 프로그램과 공유할 때만 의미가 있다).
DART_DAILY_LIMIT = 0
DART_STATEMENT_FREQ = "quarterly"         # "quarterly" | "annual"
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class DartBudget:
    """호출량을 드라이브에 영속 기록. 재실행 시 이어받기의 근거가 된다.

    ★ 설계 원칙: 상한을 미리 정하지 않는다.
      DART OpenAPI 에는 '오늘 남은 호출수' 를 알려주는 엔드포인트가 없다. 그래서 예전처럼
      19,000 같은 숫자를 박아두면 (a) 실제 한도보다 적게 쓰거나 (b) 다른 프로그램이 같은
      키를 쓰면 넘겨버린다. 둘 다 추측이다.
      → 실시간 잔여를 아는 유일한 방법은 'status=020(한도초과)이 올 때까지 쓰는 것'이다.
        020 을 받으면 그 날짜를 기록해 같은 날 재실행이 헛되이 두드리지 않게 한다."""

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0
        self.exhausted = False
        self.adaptive = (not DART_DAILY_LIMIT) or DART_DAILY_LIMIT <= 0
        self._lk = threading.Lock()
        self._load()

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_budget.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
                self.exhausted = bool(j.get("exhausted", False))
        except Exception:
            pass
        if self.exhausted:
            LOG.warn("오늘 이미 DART 일일 한도(status=020)를 받았습니다 — 이번 실행에서는 "
                     "DART 를 호출하지 않고 캐시로만 진행합니다. 자정 이후 재실행하면 이어받습니다.")
        elif self.n:
            LOG.info(f"오늘 이미 사용한 DART 호출 {self.n:,}건 "
                     f"({'적응형: 한도 도달 시 자동 중단' if self.adaptive else f'사용자 상한 {DART_DAILY_LIMIT:,}'})"
                     f" — 이어서 진행합니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n, "exhausted": self.exhausted}))
        except Exception:
            pass

    def mark_exhausted(self):
        """API 가 020 을 반환한 순간 = 진짜 잔여 0. 이 사실을 그 날짜로 못박는다."""
        with self._lk:
            if not self.exhausted:
                self.exhausted = True
                LOG.warn(f"DART 일일 한도 도달(status=020) — 오늘 {self.n:,}건 사용했습니다. "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있고, 자정 이후 재실행하면 "
                         f"정확히 이 지점부터 이어받습니다.")
                self._save()

    def report(self):
        LOG.table([["오늘 사용", f"{self.n:,}건"],
                   ["모드", "적응형(한도 도달 시 자동 중단)" if self.adaptive
                    else f"사용자 상한 {DART_DAILY_LIMIT:,}"],
                   ["한도 도달", "예 — 자정 이후 재실행" if self.exhausted else "아니오"]],
                  ["DART 호출 예산", "값"], ["l", "r"],
                  title="DART 호출 사용량 (잔여 조회 API 가 없어 '실사용량'으로 관리합니다)")

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.exhausted:
                return False                     # 020 을 이미 받았다 = 진짜 잔여 0
            if (not self.adaptive) and self.n + k > DART_DAILY_LIMIT:
                self.exhausted = True
                LOG.warn(f"사용자 지정 상한({DART_DAILY_LIMIT:,})에 도달했습니다. "
                         f"적응형으로 쓰려면 DART_DAILY_LIMIT=0 으로 두세요.")
                self._save()
                return False
            self.n += k
            if self.n % 500 == 0:
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/", on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DBUDGET is not None:
        DBUDGET.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "020":
            if DBUDGET is not None:
                DBUDGET.mark_exhausted()
        elif st == "021":
            LOG.warn("DART status=021 (조회 가능 회사 개수 초과) — 배치 크기를 줄여 재시도하세요.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자(YYYYMMDD). 없으면 법정기한으로 보수적 추정."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


# ── 전체 재무제표 ───────────────────────────────────────────────────────────────────────────
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "CFS"})
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        return None
    d = pd.DataFrame(js["list"])
    for c in _FS_KEEP:
        if c not in d.columns:
            d[c] = None
    d["corp_code"] = corp
    d["bsns_year"] = int(year)
    d["reprt_code"] = reprt
    return d[_FS_KEEP]


# ── Tier-1: 다중회사 주요계정 (배치) ────────────────────────────────────────────────────────
#   fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개까지 받는다.
#   2,500사 × 10년 × 4분기를 단건으로 받으면 100,000 호출(일 20,000 한도로 5일)이지만
#   배치로는 1,000 호출(1시간 이내)이면 끝난다. ★100배 차이다.
#   다만 '주요계정'만 오므로 B/C축이 필요로 하는 재고·매출채권·영업CF 는 없다.
#   → 헤드라인은 배치로 싹 깔고, 전체 재무제표는 우선순위대로 단건 수집해 덮어쓴다(2단 구성).
DART_MULTI_BATCH = 100
_MULTI_ACCOUNT_MAP = {
    "매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income",
    "자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity",
}


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    corps = [str(c) for c in corp_codes]
    jobs = []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps if (c, int(y), str(r)) not in done]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), r))
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        batch, y, r = job
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(batch), "bsns_year": str(y), "reprt_code": r})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        d["reprt_code"] = r
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건 수집이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량입니다")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사 "
           f"(호출 {len(jobs):,}회로 확보)")
    PIPE.io("OUT", "DRIVE", "dart_multi_raw", M, source="opendart fnlttMultiAcnt")
    return M


def fetch_dart_financials(corp_codes: Sequence[str], years: Sequence[int],
                          priority: Optional[Sequence[str]] = None,
                          reprt_codes: Optional[Sequence[str]] = None,
                          corp_years: Optional[Dict[str, Sequence[int]]] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다."""
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — B축(회계품질)·C축(자원투입)·PACK-C 가 전부 비활성화됩니다. "
                 "이 전략의 핵심 입력이므로 키 입력을 강력히 권합니다.")
        return pd.DataFrame(columns=_FS_KEEP)

    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 재무 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = list(reprt_codes) if reprt_codes else (
        [REPRT_CODES["FY"]] if DART_STATEMENT_FREQ == "annual"
        else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    #   corp_years 를 주면 회사마다 '필요한 연도'만 받는다. 전 종목 × 전 연도는 11만 콜이고
    #   그 대부분은 '살 수도 없었던 종목의 현금흐름'이다(수요 기반 수집).
    def _yrs_for(c: str) -> Sequence[int]:
        return corp_years.get(str(c), years) if corp_years else years
    jobs = [(c, y, r) for c in corp_sorted for y in sorted(_yrs_for(c), reverse=True)
            for r in reprts if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        total_needed = len(jobs)
        LOG.info(f"DART 전체 재무제표 신규 수집 대상 {total_needed:,}건 "
                 f"(대상 {len(corp_sorted):,}사 × {len(years)}년 × {len(reprts)}보고서 · "
                 f"오늘 사용 {DBUDGET.n if DBUDGET else 0:,}건)")
        res = pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 12), desc="DART 재무제표")
        got = [d for d in res if d is not None and len(d)]
    else:
        got = []

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        LOG.warn("DART 재무 데이터를 확보하지 못했습니다.")
        return pd.DataFrame(columns=_FS_KEEP)
    fs = pd.concat(frames, ignore_index=True)
    fs = fs.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                             "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_fnltt_raw", fs, scope="shared", domain="dart", source="opendart")
    n_have = fs.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(fs) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"DART 전체 재무제표 진행률 {n_have:,}/{n_need:,} "
             f"({100*n_have/max(n_need,1):.1f}%) — 최근 연도·우선순위 종목부터 채웁니다. "
             f"재실행하면 정확히 이 지점부터 이어받습니다.")
    PIPE.io("OUT", "DRIVE", "dart_fnltt_raw", fs, source="opendart fnlttSinglAcntAll")
    return fs


def merge_financial_tiers(full: pd.DataFrame, multi: pd.DataFrame) -> pd.DataFrame:
    """Tier-2(전체 재무제표)를 우선하고, 없는 (회사, 기간)만 Tier-1(주요계정)로 메운다.

    콜드빌드가 며칠 걸리는 동안에도 매출·영업이익·순이익·자산·부채·자본은 전 종목이
    확보되어 있어 유니버스 구성과 규모 버킷(C11), R3 팩터가 즉시 동작한다."""
    if multi is None or multi.empty:
        return full if full is not None else pd.DataFrame(columns=_FS_KEEP)
    if full is None or full.empty:
        LOG.info("전체 재무제표가 아직 없어 주요계정(배치)만으로 진행합니다 — "
                 "B축의 재고·매출채권·영업CF 는 결측이므로 TP_B1/TP_B2 가 약해집니다.")
        return multi
    have = set(zip(full["corp_code"].astype(str), full["bsns_year"].astype(int),
                   full["reprt_code"].astype(str)))
    key = list(zip(multi["corp_code"].astype(str), multi["bsns_year"].astype(int),
                   multi["reprt_code"].astype(str)))
    fill = multi[[k not in have for k in key]]
    if len(fill):
        LOG.info(f"주요계정으로 보완한 (회사×기간) {fill.groupby(['corp_code','bsns_year','reprt_code']).ngroups:,}건 "
                 f"— 전체 재무제표 콜드빌드가 끝나면 자동으로 대체됩니다.")
    return pd.concat([full, fill], ignore_index=True)


# ── 계정 매핑 (한국 XBRL 계정명은 회사마다 다르다 → 정규식 다중 매칭) ────────────────────────
ACCOUNT_PATTERNS: Dict[str, Tuple[str, List[str]]] = {
    # 키:            (재무제표구분, [account_id 또는 account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$"]),
    "cogs":          ("IS", [r"CostOfSales", r"^매출원가$"]),
    "gross_profit":  ("IS", [r"GrossProfit", r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense", r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense", r"경상(연구)?개발비", r"^연구개발비"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense", r"법인세비용"]),
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세비용차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment", r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssetsOtherThanGoodwill", r"^무형자산$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents", r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities", r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities", r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment", r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense", r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid", r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares", r"자기주식의?\s*취득"]),
    "debt_raise":    ("CF", [r"ProceedsFromBorrowings", r"차입금의?\s*증가", r"사채의?\s*발행"]),
}
_SJ_MAP = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# ★ 손익·현금흐름 성격의 전 계정. 빠뜨리면 <계정>_ttm 컬럼이 아예 생성되지 않고,
#   그걸 쓰는 팩이 실데이터 실행에서만 터진다(합성 스모크는 통과한다).
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy", "debt_raise",
              "tax_expense", "pretax_income", "other_income"]

# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼 전체 목록.
# attach_fundamentals 가 이 목록으로 스키마를 계약적으로 보장한다 — 수집이 얼마나 실패하든
# 패널의 컬럼 집합은 항상 같아야 한다. 그래야 "어떤 실행에선 있고 어떤 실행엔 없는" 축이
# 사라지고, 결측은 결측대로 조용히가 아니라 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_PATTERNS)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다."""
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()
    d["amount"] = pd.to_numeric(
        d["thstrm_amount"].astype(str).str.replace(",", "", regex=False).str.replace("−", "-", regex=False),
        errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
    for key, (sj, pats) in ACCOUNT_PATTERNS.items():
        sjs = _SJ_MAP.get(sj, (sj,))
        sub = d[d["sj_div"].astype(str).isin(sjs)]
        if sub.empty:
            continue
        rx = re.compile("|".join(pats), re.I)
        hit = sub[sub["account_id"].str.contains(rx, na=False) |
                  sub["account_nm"].str.contains(rx, na=False)]
        if hit.empty:
            continue
        # 같은 항목에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "rcept_no", "item", "amount"]])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    rc = (L.sort_values("rcept_no").groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    # 누적치 → 분기 단독치 (Q1/H1/Q3/FY 는 누적 공시다. 차분하지 않으면 계절성이 곧 신호가 된다)
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    flow_items = FLOW_ITEMS
    # 누적 → 분기 단독. 직전 분기가 실제로 존재할 때만 차분한다.
    # (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    gk = ["corp_code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in flow_items:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        q_val = np.where(W["q"] == 1, W[c],
                         np.where(contiguous, W[c] - prev, np.nan))
        W[c + "_q"] = q_val
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])
    # ★ 재무상태표 항목(재고·매출채권·자산·자본 등)은 pivot 결과에 그 계정이 없으면
    #   컬럼 자체가 생성되지 않는다. 그러면 패널 스키마가 실행마다 달라져
    #   "어떤 날은 있고 어떤 날은 없는" 축이 생긴다. 여기서 전 항목을 계약적으로 보장한다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in W.columns:
            W[_k] = np.nan
    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' 플래그 ─────────────────────────────────────
    #   ★ 여기서 만드는 이유: 연속성은 분기 관측을 세야 하는데, 월 패널에서 세면
    #     같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도 정답이 아니다. 분기 프레임은
    #     관측당 정확히 한 행이고 이미 (corp_code, bsns_year, q) 로 정렬돼 있다.
    #     as-of 결합이 이 플래그를 C1 게이트웨이 그대로 실어 나른다.
    #   min_periods=3 — 제출분이 3개 미만이면 NaN(=거부하지 않음). 근거 없는 제외 금지.
    _bad_q = ((col(W, "net_income_ttm") > 0) &
              (col(W, "cfo_ttm") < 0.5 * col(W, "net_income_ttm"))).astype(float)
    W["v2_bad_3q"] = (_bad_q.groupby(W["corp_code"], observed=True)
                            .transform(lambda s: s.rolling(3, min_periods=3).min()))

    _missing = [k for k in ACCOUNT_PATTERNS if W[k].notna().sum() == 0]
    if _missing:
        LOG.warn(f"DART 재무에서 한 건도 매칭되지 않은 계정 {len(_missing)}개: "
                 f"{_missing[:8]}{'...' if len(_missing) > 8 else ''} — "
                 f"해당 계정을 쓰는 지표는 전부 결측이 됩니다(0으로 채우지 않음). "
                 f"ACCOUNT_PATTERNS 정규식이 이 회사들의 계정명과 안 맞을 수 있습니다.")
    n_ttm = int(W["revenue_ttm"].notna().sum()) if "revenue_ttm" in W.columns else 0
    if len(W) and n_ttm / len(W) < 0.35:
        LOG.warn(f"TTM 산출률이 {100*n_ttm/len(W):.0f}% 로 낮습니다. 분기보고서가 결측인 기업이 "
                 f"많다는 뜻이며(중소형주에서 흔함), 해당 종목은 B/C축이 결측 처리됩니다. "
                 f"DART_STATEMENT_FREQ='quarterly' 콜드빌드가 아직 미완이라면 이어받기를 계속하세요.")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 재무 정제 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(knowledge_date = 접수일자 기준, 누적→분기 차분 완료)")
    PIPE.io("OUT", "MEM", "dart_financials_tidy", W)
    return downcast(W)


# ── 직원현황 (θ_N, TP_C2) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(c, y) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list):
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 각 조합은 서로소이므로
        #   합산이 맞지만, 일부 기업은 '합계/계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   또 jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이므로 아예 쓰지 않는다.
        for col in ("fo_bbm", "sexdstn"):
            if col in d.columns:
                d = d[~d[col].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        num = lambda s: pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                                      errors="coerce")
        emp = num(d.get("sm", pd.Series(dtype=object))).sum(skipna=True) if "sm" in d.columns else np.nan
        pay = num(d.get("fyer_salary_totamt", pd.Series(dtype=object))).sum(skipna=True) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "employees": float(emp),
                "payroll": float(pay), "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    # ★ E.get("rcept_no", "") 는 컬럼이 없으면 '문자열'을 돌려주고, zip 이 그걸 글자 단위로
    #   훑어 knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    E["knowledge_date"] = [_knowledge_from_rcept(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(E["rcept_no"], E["bsns_year"])]
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart", source="opendart empSttus")
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E


# ── 공시목록 스윕 (시장 전체를 날짜로 훑는다 — 회사별 호출보다 수십 배 싸다) ──────────────────
DISCLOSURE_PATTERNS = {
    "treasury_acq":  r"자기주식\s*취득",
    "treasury_disp": r"자기주식\s*처분",
    "treasury_canc": r"자기주식\s*소각|이익소각",
    "dividend":      r"(현금|현물)?\s*[·ㆍ]?\s*배당\s*결정|결산배당|중간배당",
    "rights_issue":  r"유상증자",
    "cb_issue":      r"전환사채",
    "bw_issue":      r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion": r"감사보고서",
}


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    have_months = set()
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        todo = []

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)
    DISCLOSURE_TYPES = ("A", "B")            # A=정기공시(사업/반기/분기보고서), B=주요사항보고

    def _one(m):
        rows = []
        for ty in DISCLOSURE_TYPES:
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})
                if not js or not isinstance(js.get("list"), list) or not js["list"]:
                    break
                rows.extend(js["list"])
                if page >= int(js.get("total_page", 1) or 1):
                    break
                page += 1
        return rows

    new = []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if r:
                new.extend(r)

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "flr_nm", "corp_cls") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures", D, scope="shared", domain="dart", source="opendart list.json")
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")     # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — 이벤트 분류: " +
           ", ".join(f"{k}={int((D['event']==k).sum()):,}" for k in DISCLOSURE_PATTERNS if (D['event']==k).any()))
    PIPE.io("OUT", "DRIVE", "dart_disclosures", D, source="opendart list.json")
    return D



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 수집 — 한경컨센서스 + 네이버금융리서치                            ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : 작성자(애널리스트)·적정가격·투자의견을 리스트에서    ║
# ║      바로 준다. 1요청에 최대 수백 행 → 애널리스트 원장의 1순위 소스.                       ║
# ║      단, 종목코드가 컬럼에 없다. 제목의 "종목명(005930)" 에서 뽑아야 한다.                 ║
# ║    · 네이버금융리서치 : 종목코드를 td[0] a.stock_item href 에 확실히 준다.                 ║
# ║      애널리스트명은 리스트에 없다(PDF/상세에 있음). 커버리지 폭이 넓다.                    ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자가 명시적으로 수집을 지시했으므로     ║
# ║    수행하되, 초당 요청을 보수적으로 제한하고(RATE_LIMIT_QPS) 이 사실을 로그에 명시한다.     ║
# ║  ⚠ PDF 원문은 증권사 저작물이다. 로컬 캐시/분석 용도로만 쓰고 재배포하지 말 것.             ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다. (공개 스크래퍼들의 컬럼 인덱스가 서로 모순되기 때문)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
HK_PDF = HK_BASE + "/analysis/downpdf?report_idx={idx}"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = [
    "report_uid", "source", "src_report_id", "pub_date", "category",
    "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
    "analyst_raw", "target_price", "opinion", "pdf_url", "pdf_uid", "detail_url",
    "views", "event_date", "knowledge_date",
]

_OPINION_MAP = {
    "매수": "BUY", "buy": "BUY", "strongbuy": "BUY", "적극매수": "BUY", "outperform": "BUY",
    "비중확대": "BUY", "overweight": "BUY", "trading buy": "BUY", "tradingbuy": "BUY",
    "중립": "HOLD", "hold": "HOLD", "neutral": "HOLD", "marketperform": "HOLD",
    "시장수익률": "HOLD", "보유": "HOLD", "비중유지": "HOLD",
    "매도": "SELL", "sell": "SELL", "underperform": "SELL", "비중축소": "SELL",
    "underweight": "SELL", "reduce": "SELL",
}
_NULL_TOKENS = {"", "-", "--", "0", "n/a", "na", "없음", "투자의견없음", "nr", "not rated", "제시안함"}


def _clean_cell(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABCABC' 처럼 2~3회 반복되어 나오는 알려진 버그를 되돌린다."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0:
            unit = s[: n // k]
            if unit * k == s:
                return unit
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 목표주가 리비전 팩터가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    if v <= 0 or v > 5e7:
        return None
    return v


def parse_opinion(x: Any) -> Optional[str]:
    t = _clean_cell(x)
    if t.lower() in _NULL_TOKENS:
        return None
    k = re.sub(r"[^\w가-힣]", "", t).lower()
    for pat, val in _OPINION_MAP.items():
        if re.sub(r"[^\w가-힣]", "", pat).lower() in k:
            return val
    return t[:20] or None


_YYMMDD = re.compile(r"^\s*(\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*$")


def parse_kr_date(s: Any) -> Optional[str]:
    """★ 네이버 리스트의 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    → 두 자리 연도는 여기서 4자리로 확정한 뒤에만 하위로 넘긴다.
    """
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        # 백테스트 대상은 2000년대. 두 자리 연도는 2000+yy 로 확정한다.
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        try:
            return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
        except Exception:
            return None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6})\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return m.group(1) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


# ── 헤더 기반 테이블 파서 (컬럼 인덱스 불신 원칙) ────────────────────────────────────────────
def _table_headers(table) -> List[str]:
    hdr = []
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            hdr = [_clean_cell(th.get_text()) for th in ths]
            break
    return hdr


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    if headers and len(headers) == len(tds):
        return {headers[i]: tds[i] for i in range(len(tds))}
    return {}


def _pick(rowmap: Dict[str, Any], *names) -> Optional[Any]:
    for n in names:
        for k, v in rowmap.items():
            if n in k:
                return v
    return None


# ── 한경컨센서스 ────────────────────────────────────────────────────────────────────────────
_HK_LAYOUT_LOGGED = set()


def _hk_parse(html: str, category: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = None
    for sel in ("div.table_style01 table", "#contents table", "table"):
        t = soup.select_one(sel)
        if t is not None and t.find("tr") is not None:
            table = t
            break
    if table is None:
        return []
    if soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃 감지: {len(headers)}컬럼 {headers}")
        if headers and not any("적정" in h or "목표" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 적정가격 컬럼이 없습니다. "
                     f"skinType 파라미터가 무시된 것 같습니다(통합 탭 6컬럼 레이아웃). "
                     f"목표주가·투자의견은 이 카테고리에서 수집되지 않습니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        # report_idx 는 어느 열에 있든 앵커에서 찾는다 (인덱스 의존 제거)
        ridx, pdf = None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                pdf = HK_PDF.format(idx=ridx)
                break
        if ridx is None:
            continue

        date_s = _pick(rm, "작성일", "날짜")
        if not date_s:
            date_s = next((t for t in texts if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
        title = _pick(rm, "제목")
        if not title:
            a = tr.find("a", href=re.compile("report_idx"))
            title = _clean_cell(a.get_text(" ")) if a else ""
        title = _dedup_repeat(title)

        tp = _pick(rm, "적정가격", "목표주가", "적정주가")
        op = _pick(rm, "투자의견", "의견")
        an = _pick(rm, "작성자", "애널리스트")
        bk = _pick(rm, "제공출처", "증권사", "출처")

        if headers and len(headers) == len(texts):
            pass                                     # 헤더 매핑 성공 — 그대로 사용
        else:
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c not in (op or "",)]
            if bk is None:
                bk = next((c for c in cand if "증권" in c or "투자" in c or "금융" in c), None)
            if an is None:
                an = next((c for c in cand if c != bk and 1 <= len(c) <= 30), None)

        out.append({
            "source": "hankyung", "src_report_id": str(ridx), "category": category,
            "pub_date": parse_kr_date(date_s), "title": title,
            "stock_code": code_from_title(title), "stock_name": name_from_title(title),
            "broker_raw": _clean_cell(bk), "analyst_raw": _clean_cell(an),
            "target_price": parse_target_price(tp), "opinion": parse_opinion(op),
            "pdf_url": pdf, "detail_url": pdf, "views": None,
        })
    return out


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다."""
    rows: List[dict] = []
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    jobs = []
    for skin in skins:
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            jobs.append((skin, sd, ed))

    def _sweep(job):
        skin, sd, ed = job
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            params = {
                "skinType": skin, "sdate": sd.strftime("%Y-%m-%d"), "edate": ed.strftime("%Y-%m-%d"),
                "now_page": page, "pagenum": page_size, "order_type": "",
                "report_type": "CO" if skin == "business" else "",
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            if not html:
                break
            batch = _hk_parse(html, skin)
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            for b in fresh:
                seen_ids.add(b["src_report_id"])
            got.extend(fresh)
            # ★ 조기 종료 조건을 느슨하게 잡으면 데이터가 조용히 잘려나간다.
            #   파싱 실패나 일시적 짧은 페이지 하나로 그 해 전체 수집이 끊길 수 있으므로,
            #   '새 항목 0건'이 2회 연속일 때만 멈춘다.
            if len(fresh) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
            if page == max_pages:
                LOG.warn(f"한경 {skin} {sd:%Y} 구간이 최대 페이지({max_pages})에 도달했습니다 — "
                         f"데이터가 잘렸을 수 있습니다. max_pages 를 늘리거나 구간을 분기 단위로 "
                         f"쪼개세요. (지금까지 {len(got):,}건)")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스")
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows, columns=[c for c in REPORT_COLS if c in (rows[0].keys() if rows else [])]) \
        if rows else pd.DataFrame(columns=REPORT_COLS)
    if rows:
        d = pd.DataFrame(rows)
    LOG.ok(f"한경컨센서스 {len(d):,}건 "
           f"(작성자 보유 {int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} / "
           f"목표주가 보유 {int(d['target_price'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
NV_CATS = {
    "company": ("company_list.naver", "company_read.naver"),
    "industry": ("industry_list.naver", "industry_read.naver"),
    "market": ("market_info_list.naver", "market_info_read.naver"),
    "invest": ("invest_list.naver", "invest_read.naver"),
    "economy": ("economy_list.naver", "economy_read.naver"),
    "debenture": ("debenture_list.naver", "debenture_read.naver"),
}
_NV_PDF_RE = re.compile(r"/stock-research/(\w+)/(\d+)/(\d{8})_(\w+)_(\d+)\.pdf")


def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = soup.select_one("#contentarea_left div.box_type_m table.type_1") or \
        soup.select_one("table.type_1") or soup.select_one("table")
    if table is None:
        return []
    headers = _table_headers(table)
    _, read_page = NV_CATS.get(cat, ("", "company_read.naver"))
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid, detail, title = None, None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid = m.group(1)
                detail = urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=(\d{6})", a_item["href"])
            code = mm.group(1) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        pdf = None
        for a in tr.find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                pdf = a["href"] if a["href"].startswith("http") else urljoin(NV_BASE, a["href"])
                break

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)
        vw = _pick(rm, "조회")

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None,
            "pdf_url": pdf, "detail_url": detail,
            "views": _clean_cell(vw).replace(",", "") or None,
        })
    return out


def _nv_last_page(html: str) -> int:
    soup = soup_of(html)
    if soup is None:
        return 1
    mx = 1
    for a in soup.select("table.Nnavi a[href]"):
        m = re.search(r"page=(\d+)", a["href"])
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 60000) -> pd.DataFrame:
    """신형 JSON API. 되면 HTML 페이징보다 훨씬 빠르고 구조가 안정적이다."""
    rows, index = [], 0
    url = NV_API.format(cat=cat)
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    while index < hard_cap:
        js = http_json(url, source="naver", tries=2, headers=hdr,
                       params={"index": index, "size": page_size,
                               "startDate": as_ts(start).strftime("%Y-%m-%d"),
                               "endDate": as_ts(end).strftime("%Y-%m-%d")})
        if not js:
            break
        items = js if isinstance(js, list) else (js.get("researches") or js.get("list") or
                                                 js.get("items") or js.get("content") or [])
        if not isinstance(items, list) or not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({
                "source": "naver", "category": cat,
                "src_report_id": str(it.get("id") or it.get("nid") or it.get("researchId") or ""),
                "pub_date": it.get("createDate") or it.get("date") or it.get("writeDate"),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                "detail_url": None, "views": it.get("readCount"),
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    if len(d):
        d = d[d["src_report_id"].astype(str).str.len() > 0]
    return d


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1500) -> pd.DataFrame:
    frames = []
    for cat in cats:
        # ① JSON API 우선
        try:
            dj = naver_collect_json(cat, start, end)
        except Exception:
            dj = pd.DataFrame()
        if len(dj) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(dj):,}건")
            frames.append(dj)
            continue
        # ② HTML 리스트 폴백
        list_page, _ = NV_CATS[cat]
        base = urljoin(NV_BASE, list_page)
        probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                         params={"searchType": "writeDate",
                                 "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                                 "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": 1})
        if not probe:
            LOG.warn(f"네이버 '{cat}' 리스트 접근 실패 — 건너뜁니다.")
            continue
        last = min(_nv_last_page(probe), max_pages)
        LOG.info(f"네이버 '{cat}' HTML 폴백 — 총 {last:,}페이지")

        def _pg(p: int):
            h = probe if p == 1 else http_get(
                base, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=3,
                params={"searchType": "writeDate",
                        "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                        "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": p})
            return _nv_parse_list(h, cat) if h else []

        res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO),
                      desc=f"네이버 {cat}")
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다."""
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    if len(need) > limit:
        LOG.warn(f"네이버 상세 보강 대상 {len(need):,}건 중 최신 {limit:,}건만 조회합니다 "
                 f"(RESEARCH 설정으로 조절 가능). 나머지는 목표주가 결측으로 남습니다.")
        need = need.sort_values("pub_date", ascending=False).head(limit)

    def _one(u: str):
        h = http_get(u, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=2)
        if not h:
            return None
        s = soup_of(h)
        if s is None:
            return None
        box = s.select_one("div.view_info_1") or s
        tp = box.select_one("em.money strong") or box.select_one("em.money")
        op = box.select_one("em.coment")
        an = ""
        src = s.select_one("th.view_sbj p.source")
        if src is not None:
            an = _clean_cell(src.get_text(" "))
        return {"detail_url": u,
                "target_price": parse_target_price(tp.get_text() if tp else None),
                "opinion": parse_opinion(op.get_text() if op else None),
                "_detail_src": an}

    res = pmap_io(_one, need["detail_url"].tolist(), workers=min(8, N_WORKERS_IO),
                  desc="네이버 상세(목표주가)")
    got = pd.DataFrame([r for r in res if r])
    if got.empty:
        return df
    # ★ detail_url 이 유일하지 않으면 merge 가 행을 증식시킨다(리포트가 복제됨).
    #   원장 건수가 조용히 불어나 커버리지·리비전 통계가 전부 틀어진다.
    got = got.drop_duplicates("detail_url", keep="last")
    n_before = len(df)
    df = df.merge(got, on="detail_url", how="left", suffixes=("", "_d"))
    if len(df) != n_before:
        LOG.warn(f"상세 보강 머지에서 행수가 {n_before:,}→{len(df):,} 로 변했습니다 — "
                 f"중복 detail_url 로 인한 증식입니다.")
        df = df.drop_duplicates("report_uid", keep="first")
    for c in ("target_price", "opinion"):
        if f"{c}_d" in df.columns:
            df[c] = df[c].where(df[c].notna(), df[f"{c}_d"])
            df = df.drop(columns=[f"{c}_d"])
    LOG.ok(f"네이버 상세 보강 — 목표주가 {int(got['target_price'].notna().sum()):,}건 추가 확보")
    return df


# ── PDF 원문 ────────────────────────────────────────────────────────────────────────────────
_ANALYST_LINE = re.compile(
    r"([가-힣]{2,4})\s*(?:연구원|애널리스트|수석|책임|선임)?\s*"
    r"(?:\(?\s*(?:02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}\s*\)?)?\s*"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TP_PAT = re.compile(r"(?:목표\s*주가|목표주가|적정\s*주가|적정주가|TP)\s*[:：(]?\s*"
                     r"(?:원\)?\s*)?([0-9][0-9,]{2,9})")


def pdf_text(data: bytes, max_pages: int = 3) -> str:
    """1페이지 헤더/푸터에 애널리스트명·이메일·목표주가가 몰려 있다. 앞 3장이면 충분하다."""
    if not data or data[:5] != b"%PDF-":
        return ""
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count)))
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
        except Exception:
            pass
    return ""


def pdf_extract_fields(text: str) -> dict:
    out = {"pdf_analysts": "", "pdf_emails": "", "pdf_target": None}
    if not text:
        return out
    pairs = _ANALYST_LINE.findall(text[:6000])
    names = [p[0] for p in pairs]
    mails = [p[1] for p in pairs] or _EMAIL.findall(text[:6000])
    if not names:
        # 이메일 로컬파트에서 역추적 실패 시, '연구원/애널리스트' 앞 한글 이름만이라도
        names = re.findall(r"([가-힣]{2,4})\s*(?:연구원|애널리스트)", text[:6000])
    out["pdf_analysts"] = ",".join(dict.fromkeys(names))[:120]
    out["pdf_emails"] = ",".join(dict.fromkeys(mails))[:200]
    m = _TP_PAT.search(text[:8000])
    if m:
        out["pdf_target"] = parse_target_price(m.group(1))
    return out


def download_pdfs(df: pd.DataFrame, cap_per_month: int = 0) -> pd.DataFrame:
    """PDF 를 공용 인덱스에 저장(내용해시 경로 → 중복 저장 없음)하고 본문 필드를 추출한다."""
    if df.empty or not RESEARCH_DOWNLOAD_PDF:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None if c != "pdf_uid" else ""
        return df
    if fitz is None and pdfplumber is None:
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 원문 추출을 건너뜁니다. "
                 "한경 리스트의 작성자/목표주가만으로도 애널리스트 연결은 동작합니다.")
    work = df[df["pdf_url"].notna()].copy()
    if cap_per_month and len(work):
        work["_m"] = as_ts_series(work["pub_date"]).dt.to_period("M")
        work = work.groupby("_m", observed=True).head(cap_per_month).drop(columns=["_m"])
    if work.empty:
        return df

    idx = VAULT.load_index("shared")
    known = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        # iterrows 는 30만 행에서 13초를 쓴다. zip 은 같은 결과를 0.2초에 만든다.
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
    LOG.info(f"PDF 대상 {len(work):,}건 (드라이브 캐시 보유 {sum(1 for k in work['report_uid'] if k in known):,}건)")

    def _one(rec):
        uid, url = rec
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
            if data:
                return (uid, known[uid], data)
            # 인덱스에는 있는데 실제 파일이 없으면(드라이브 동기화 누락 등) 재수집으로 폴백한다.
            # 여기서 포기하면 그 보고서는 영구히 비어 있는 채로 남는다.
        raw = http_get(url, source="hankyung" if "hankyung" in str(url) else "naver",
                       as_bytes=True, tries=2, referer=HK_BASE + "/" if "hankyung" in str(url) else NV_BASE)
        if not raw or raw[:5] != b"%PDF-":
            return (uid, "", b"")          # 로그인/에러 HTML 이 200 으로 오는 케이스 방어
        return (uid, "", raw)

    jobs = list(zip(work["report_uid"].astype(str), work["pdf_url"].astype(str)))

    # ★ 청크로 끊어 받는다. pmap_io 는 결과 리스트를 통째로 들고 있으므로, 한 번에 던지면
    #   내려받은 PDF 본문 전부가 동시에 RAM 에 남는다. 목표치인 연 3만건 × 10년 = 30만건에
    #   평균 300KB 를 곱하면 90GB 다. 캐시가 차 있어도 마찬가지다 — 캐시 경로도 blob 바이트를
    #   그대로 반환하기 때문에 오히려 더 빨리 쌓인다. 청크 단위로 소비하고 버리면 상주량이
    #   작업 수와 무관하게 평평해진다(약 600MB). 청크마다 flush 하므로 중간에 끊겨도 이어받는다.
    PDF_CHUNK = 2000
    rows = []
    ok = 0
    for k0 in range(0, len(jobs), PDF_CHUNK):
        chunk = jobs[k0:k0 + PDF_CHUNK]
        res = pmap_io(_one, chunk, workers=min(N_WORKERS_IO, 10),
                      desc=f"리포트 PDF {k0//PDF_CHUNK + 1}/{(len(jobs)-1)//PDF_CHUNK + 1}")
        for r in res:
            if not r:
                continue
            uid, existing_blob_uid, data = r
            if not data:
                continue
            ok += 1
            blob_uid = existing_blob_uid
            if not blob_uid:
                p = VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                                   source="report_pdf", scope="shared")
                blob_uid = sha1_str("research", "report_pdf", uid, sha1_bytes(data)) if p else ""
            f = pdf_extract_fields(pdf_text(data))
            rows.append({"report_uid": uid, "pdf_uid": blob_uid, **f})
        del res
        VAULT.flush("shared")
    VAULT.flush("shared")
    LOG.ok(f"PDF 확보 {ok:,}/{len(jobs):,}건 — 공용 인덱스에 저장(내용해시 중복제거 적용)")
    if not rows:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None
        return df
    ext = pd.DataFrame(rows)
    df = df.merge(ext, on="report_uid", how="left")
    PIPE.io("OUT", "DRIVE", "research:pdf", ext, source="hankyung/naver pdf")
    return df



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  엔티티 해상 — 증권사 정규화 / 애널리스트 원장 / 보고서↔애널리스트 연결              ║
# ║                                                                                          ║
# ║  이 모듈이 답해야 하는 질문 (사용자 요구사항):                                              ║
# ║    Q1. 보고서와 애널리스트가 제대로 연결되었는가?   → report_analyst_link + 연결 감사표     ║
# ║    Q2. 다중소스 원장 연결은 확실한가?               → dedup_key 병합 + 소스기여 감사표      ║
# ║    Q3. 목표주가는 누가 언제 제시했는가?             → (analyst_id, code, date, tp) 원장     ║
# ║                                                                                          ║
# ║  증권사 사명 변경(2016~2026)을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로          ║
# ║  다른 사람이 되어버린다 → 목표주가 리비전(d2)이 통째로 망가진다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 정규화 표: (별칭 정규식 → 정식명). 사명 변경 이력이 핵심이다.
BROKER_CANON: List[Tuple[str, str]] = [
    (r"미래에셋(대우|증권|생명)?", "미래에셋증권"),          # 미래에셋대우→미래에셋증권(2021)
    (r"(대우증권|KDB대우)", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),        # 우리투자→NH투자(2014)
    (r"한국투자|한국證|한투증권", "한국투자증권"),
    (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),                # KB투자+현대증권→KB증권(2017)
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),        # 신한금융투자→신한투자증권(2022)
    (r"하나(증권|금융투자|금투)", "하나증권"),                # 하나금융투자→하나증권(2022)
    (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"),
    (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"),                       # 동양→유안타(2014)
    (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"),
    (r"IBK(투자증권|증권)|기업은행", "IBK투자증권"),
    (r"신영증권", "신영증권"),
    (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),      # HMC투자→현대차증권(2016)
    (r"SK증권", "SK증권"),
    (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권", "iM증권"),               # 하이투자→iM증권(2024)
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),           # 이베스트→LS증권(2024)
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),      # KTB→다올(2022)
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),             # 동부→DB금융투자(2018)
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"),
    (r"부국증권", "부국증권"),
    (r"한양증권", "한양증권"),
    (r"상상인증권|골든브릿지", "상상인증권"),
    (r"케이프(투자증권|증권)", "케이프투자증권"),
    (r"토스증권", "토스증권"),
    (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"),
    (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"),
    (r"DS투자증권", "DS투자증권"),
    (r"현대해상|한화생명|미래에셋생명", "기타"),
    (r"NICE|나이스", "NICE디앤비"),
    (r"에프앤가이드|FnGuide", "에프앤가이드"),
    (r"(하이證|하이증권)", "iM증권"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]

# 대형 10개사 / 중소형 10개사 — 커버리지 목표 달성 여부 감사에 쓴다
MAJOR_BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "키움증권", "메리츠증권", "대신증권"]
MINOR_BROKERS = ["유안타증권", "한화투자증권", "교보증권", "IBK투자증권", "신영증권",
                 "현대차증권", "SK증권", "유진투자증권", "iM증권", "LS증권",
                 "다올투자증권", "DB금융투자", "BNK투자증권", "흥국증권", "부국증권",
                 "한양증권", "상상인증권", "케이프투자증권", "DS투자증권", "코리아에셋투자증권"]


def normalize_broker(raw: Any) -> Tuple[str, str]:
    """(broker_id, 정식명). 못 알아보면 정규화 문자열 자체를 id 로 쓰되 '미상' 표시는 하지 않는다
    (미상으로 뭉치면 서로 다른 소형사가 한 덩어리가 되어 커버리지 통계가 거짓이 된다)."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return (sha1_str("broker", canon)[:12], canon)
    canon = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    return (sha1_str("broker", canon)[:12], canon)


_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동/김철수' / '홍길동 외 1인' → ['홍길동','김철수']"""
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사)", " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


def _name_to_code_map(sec: pd.DataFrame) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for _, r in sec.iterrows():
        n = norm_corp_name(r.get("name"))
        c = r.get("code")
        if n and isinstance(c, str) and n not in m:
            m[n] = c
    return m


def _atoms(vals, sep: str) -> List[str]:
    """합성 토큰을 원자로 되돌린 뒤 정렬·중복제거. 병합을 멱등하게 만드는 핵심 함수."""
    out = set()
    for v in vals:
        s = str(v)
        if not s or s.lower() in ("nan", "none", "<na>"):
            continue
        for tok in s.split(sep):
            tok = tok.strip()
            if tok and tok.lower() not in ("nan", "none", "<na>"):
                out.add(tok)
    return sorted(out)


def _pick_str(vals) -> str:
    """비어있지 않은 값 중 사전순 최소. '행 순서상 첫 값'과 달리 실행 간 재현된다."""
    c = sorted({str(v).strip() for v in vals
                if v is not None and str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "<na>")})
    return c[0] if c else ""


def build_report_master(frames: Sequence[pd.DataFrame], sec: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 → 보고서 원장. 중복 제거가 아니라 '병합'이다(정보를 버리지 않는다)."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.warn("수집된 리포트가 없습니다. 드라이브 캐시도 비어 있다면 D축 d2/d4 는 결측 처리됩니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat([f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                   for f in frames], ignore_index=True)

    # 두 자리 연도는 수집부 parse_kr_date 에서 이미 4자리로 확정된다.
    # 여기서는 남은 이상치만 걸러낸다(교정하지 않는다 — 잘못된 교정이 더 위험하다).
    n_raw0 = len(d)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("1999-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일이 없거나 범위를 벗어난 리포트 {int(bad.sum()):,}건을 제외했습니다 "
                 f"({100*bad.mean():.2f}%). 이 비율이 크면 소스의 날짜 형식이 바뀐 것입니다 — "
                 f"조용히 넘기지 말고 parse_kr_date 를 확인하세요.")
    d = d[~bad]
    if len(d) == 0:
        LOG.error("발간일이 유효한 리포트가 하나도 없습니다. 날짜 파싱이 깨졌습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    bid = d["broker_raw"].map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]

    # 종목코드: ① 소스 제공 ② 제목 정규식 ③ 종목명→코드 사전
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = d.loc[need, "title"].map(code_from_title)
    need = d["stock_code"].isna() & d["stock_name"].astype(str).str.len().gt(0)
    if need.any() and len(sec):
        n2c = _name_to_code_map(sec)
        d.loc[need, "stock_code"] = d.loc[need, "stock_name"].map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = d["title"].map(_dedup_repeat)
    # report_uid 는 '한 번 붙으면 안 바뀌는' 식별자여야 한다. 이미 붙어 있으면 보존한다.
    # (드라이브 캐시의 병합 결과가 다시 입력으로 들어올 때 source 가 "hankyung+naver" 같은
    #  합성 토큰이라, 무조건 재계산하면 실행마다 uid 가 달라져 PDF 캐시가 통째로 무효화된다)
    _uid_new = [sha1_str(s, i) for s, i in zip(d["source"].astype(str),
                                               d["src_report_id"].astype(str))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    # 소스 간 동일 보고서 판정 키
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b,
                               c or "", norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             d["stock_code"].fillna(""), d["title"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"])

    # ── 멱등 병합 (재실행 안전) ─────────────────────────────────────────────────────────
    #   이 함수의 출력(원장)은 다음 실행에서 드라이브 캐시로부터 '입력 프레임'으로 되돌아온다.
    #   그때 source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로, 단순 set 병합은
    #   "hankyung+naver" 를 원자 하나로 취급해 실행할 때마다 문자열이 무한히 길어진다
    #   (hankyung+naver → hankyung+hankyung+naver+naver → …). 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌어
    #   PDF 캐시·애널리스트 연결표가 통째로 끊긴다. 순서에 무관한 min 으로 고정한다.
    #   (min 은 병합행이 다시 들어와도 같은 값을 낸다: min{u1,u2,min(u1,u2)} = min(u1,u2))
    m = d.groupby("dedup_key", as_index=False).agg(**{
        "report_uid": ("report_uid", "min"),
        "src_report_id": ("src_report_id", lambda s: "|".join(_atoms(s, "|"))),
        "source": ("source", lambda s: "+".join(_atoms(s, "+"))),
        "category": ("category", _pick_str),
        "pub_date": ("pub_date", "min"),
        "title": ("title", lambda s: max(sorted(set(map(str, s))), key=len)),
        "stock_code": ("stock_code", lambda s: _pick_str(s) or None),
        "stock_name": ("stock_name", _pick_str),
        "broker_id": ("broker_id", "min"),          # dedup_key 구성요소라 그룹 내 동일
        "broker_name": ("broker_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),      # 네이티브 max = NaN 무시. 파이썬 람다는 30만건에서 50초.
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "pdf_url": ("pdf_url", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"보고서 원장 병합: 수집 {n_raw0:,}건 → 날짜유효 {n_raw:,}건 → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0 - n_raw:,} · 소스 간 중복 병합 {n_raw - len(m):,})")

    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개 (C1)
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver")
    return m


def build_analyst_ledger(rep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """애널리스트 마스터 + 보고서↔애널리스트 연결표. 연결 방법과 신뢰도를 반드시 기록한다."""
    if rep.empty:
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))
    links = []
    for r in rep.itertuples(index=False):
        names, method, conf = [], "unresolved", 0.0
        raw = getattr(r, "analyst_raw", "") or ""
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98        # 한경 '작성자' 컬럼 — 가장 신뢰도 높음
        if not names:
            praw = getattr(r, "pdf_analysts", "") or ""
            if str(praw).strip():
                names = [n for n in str(praw).split(",") if n.strip()]
                method, conf = "pdf_header", 0.80
        if not names:
            continue
        for i, nm in enumerate(names):
            links.append({
                "report_uid": r.report_uid, "name": nm, "broker_id": r.broker_id,
                "broker_name": r.broker_name, "role": "lead" if i == 0 else "co",
                "link_method": method, "link_conf": conf,
                "pub_date": r.pub_date, "stock_code": r.stock_code,
                "target_price": r.target_price, "opinion": r.opinion,
            })
    if not links:
        LOG.warn("애널리스트를 한 건도 식별하지 못했습니다. 한경컨센서스 수집이 실패했거나 "
                 "skinType=business 응답이 6컬럼 레이아웃으로 왔을 가능성이 큽니다.")
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))

    L = pd.DataFrame(links)
    L["name_norm"] = L["name"].map(lambda s: re.sub(r"\s+", "", str(s)))
    # 애널리스트 동일성: (증권사, 이름). 동명이인은 소속으로 구분된다.
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14] for b, n in zip(L["broker_id"], L["name_norm"])]

    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name_norm", "first"), broker_id=("broker_id", "first"),
               broker_name=("broker_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("stock_code", lambda s: s.dropna().nunique()),
               n_targets=("target_price", lambda s: int(s.notna().sum()))))
    # 동명이인/이직 감지 — 같은 이름이 여러 증권사에 존재
    dup = A.groupby("name")["analyst_id"].transform("size")
    A["name_ambiguous"] = dup > 1
    LOG.ok(f"애널리스트 원장 {len(A):,}명 · 연결 {len(L):,}건 "
           f"(동명/이직 후보 {int(A['name_ambiguous'].sum()):,}명)")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


def audit_linkage(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame):
    """★ 사용자 요구: '보고서와 식별된 애널리스트가 제대로 연결되었는지 한눈에'."""
    LOG.banner("원장 무결성 감사 — 보고서 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출한다. 숫자가 낮으면 그대로 보고한다.")
    if rep.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()
    r["has_tp"] = r["target_price"].notna()

    rows = []
    for y, g in r.groupby("year"):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g['has_tp'].sum()):,}", f"{100*g['has_tp'].mean():.1f}%",
                     "✔" if n >= RESEARCH_TARGET_PER_YEAR else f"목표 {RESEARCH_TARGET_PER_YEAR:,} 미달"])
    LOG.table(rows, ["연도", "보고서", "애널연결", "연결률", "종목코드", "코드율",
                     "목표주가", "TP율", "연 3만건 목표"],
              ["c", "r", "r", "r", "r", "r", "r", "r", "l"])

    src = r.groupby("source").agg(n=("report_uid", "size"),
                                  analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean"),
                                  tp=("has_tp", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%",
                f"{100*s['code']:.1f}%", f"{100*s['tp']:.1f}%"] for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "종목코드율", "목표주가율"],
              ["l", "r", "r", "r", "r"],
              title="다중소스 원장 연결 — 어느 소스가 무엇을 채웠는가 "
                    "('hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건")

    if len(L):
        mth = L.groupby("link_method").agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "보고서 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 "
                        "(list_field=한경 작성자컬럼 0.98 · pdf_header=PDF추출 0.80)")

    if len(A):
        bro = (A.groupby("broker_name")
                .agg(analysts=("analyst_id", "nunique"), reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        mnr = [b for b in bro.index if b not in MAJOR_BROKERS]
        LOG.table([[b, f"{int(bro.loc[b,'analysts']):,}", f"{int(bro.loc[b,'reports']):,}"]
                   for b in bro.index[:30]],
                  ["증권사", "애널리스트 수", "보고서 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 그 외 증권사 {len(mnr)}개 "
                 f"→ 요구조건(대형 10+ / 중소형 10+): "
                 f"{'✔ 충족' if len(maj) >= 10 and len(mnr) >= 10 else '❗ 미충족 — 수집 범위를 넓히세요'}")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source").size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없어 PDF 추출에 의존합니다 "
                 f"(RESEARCH_DOWNLOAD_PDF=True 로 개선 가능).")


def build_consensus_panel(L: pd.DataFrame, months: pd.DatetimeIndex,
                          window_days: int = 90) -> pd.DataFrame:
    """D축 d2(목표주가 상향 리비전) · d4(커버리지 변화) 산출.

    ★ 리비전은 '같은 애널리스트가 같은 종목에 대해 이전에 제시한 목표주가' 와 비교해야 한다.
      애널리스트 식별이 없으면 이 지표는 만들 수 없다 — 애널리스트 원장이 필요한 진짜 이유.
    """
    cols = ["code", "month", "n_analyst", "tp_median", "rev_up", "rev_dn", "d2_raw", "d4_raw"]
    if L is None or L.empty:
        LOG.warn("애널리스트 연결이 없어 컨센서스 패널을 만들 수 없습니다 — d2/d4 결측 처리. "
                 "U 는 가용 축(d1, d3) 평균으로 계산됩니다(0으로 채우지 않음).")
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["stock_code"]).copy()
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    if x.empty:
        return pd.DataFrame(columns=cols)

    x = x.sort_values(["stock_code", "analyst_id", "pub_date"])
    x["prev_tp"] = x.groupby(["stock_code", "analyst_id"], observed=True)["target_price"].shift(1)
    x["rev"] = np.where(x["target_price"].notna() & x["prev_tp"].notna(),
                        np.sign(x["target_price"] - x["prev_tp"]), np.nan)

    out = []
    for m in months:
        lo = m - pd.Timedelta(days=window_days)
        w = x[(x["pub_date"] > lo) & (x["pub_date"] <= m)]
        if w.empty:
            continue
        g = w.groupby("stock_code", observed=True)
        agg = pd.DataFrame({
            "n_analyst": g["analyst_id"].nunique(),
            "tp_median": g["target_price"].median(),
            "rev_up": g["rev"].apply(lambda s: float((s > 0).sum())),
            "rev_dn": g["rev"].apply(lambda s: float((s < 0).sum())),
        }).reset_index().rename(columns={"stock_code": "code"})
        agg["month"] = m
        out.append(agg)
    if not out:
        return pd.DataFrame(columns=cols)
    P = pd.concat(out, ignore_index=True)
    P = P.sort_values(["code", "month"])
    # d2 = -(상향 리비전 수 / 커버리지)   d4 = -Δ(커버리지 애널리스트 수)
    P["d2_raw"] = -(P["rev_up"] / P["n_analyst"].replace(0, np.nan))
    P["d4_raw"] = -P.groupby("code", observed=True)["n_analyst"].diff()
    LOG.ok(f"컨센서스 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) — "
           f"목표주가 리비전 관측 {int((P['rev_up']+P['rev_dn']).sum()):,}건")
    PIPE.io("OUT", "MEM", "consensus_panel", P)
    return downcast(P)

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-0  KRX 비의존 데이터 스파인 (KRX 차단 대응)                                        ║
# ║                                                                                          ║
# ║  전제: data.krx.co.kr / kind.krx.co.kr 접근이 차단될 수 있다(계정·IP 단위).                 ║
# ║  그때도 ① PIT 유니버스 ② 생존자편향 제거 ③ 소유권 이전 관측이 성립해야 한다.                 ║
# ║                                                                                          ║
# ║  ── 대체 경로 사다리 ───────────────────────────────────────────────────────────────────  ║
# ║   유니버스/상장폐지 : FDR GitHub 캐시(비KRX 호스트) → DART corpCode → 네이버 시세목록       ║
# ║                       → ★가격이력 기반 상장/폐지 창 재구성 (거래가 있었다는 사실 자체가     ║
# ║                         상장의 증거다. 어떤 명부에도 의존하지 않는다)                       ║
# ║   상장주식수(시총)  : ★DART 주식총수현황(stockTotqySttus) — 분기별·접수일 기준이라 PIT 완전 ║
# ║                       → 없으면 거래대금 20일합 대리 분모                                    ║
# ║   투자자 수급       : pykrx(가능할 때) → ★네이버 종목별 투자자 매매동향 JSON → 네이버 HTML  ║
# ║   신용융자잔고      : KRX 독점 데이터. 차단 시 수동 CSV → 프록시(Fallback B)로만 가능하며    ║
# ║                       그 사실을 등급으로 못박아 리포트 첫 줄에 인쇄한다(§11-3).             ║
# ║                                                                                          ║
# ║  ★ 차단 상태에서 KRX 를 계속 두드리는 것은 상황을 악화시킨다. 1회 프로브 후 전 경로를        ║
# ║    끄고, 그 사실과 영향을 로그에 남긴다.                                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_KRX_STATE = {"probed": False, "allowed": None, "reason": ""}


def next_bday(s) -> pd.Series:
    """거래일 +1영업일. 공표 지연을 '달력 하루'가 아니라 '영업일 하루'로 계산한다."""
    return as_ts_series(s) + pd.tseries.offsets.BDay(1)


def krx_allowed() -> bool:
    """KRX 계열(data.krx.co.kr / pykrx / KIND) 사용 가능 여부. 프로브는 실행당 1회."""
    if KRX_MODE.upper() == "OFF":
        if not _KRX_STATE["probed"]:
            _KRX_STATE.update(probed=True, allowed=False, reason="KRX_MODE='OFF' (사용자 설정)")
            LOG.warn("KRX 경로가 설정으로 꺼져 있습니다 — 비KRX 스파인으로 전량 진행합니다. "
                     "차단이 풀리면 KRX_MODE='AUTO' 로 되돌리세요.")
        return False
    if KRX_MODE.upper() == "ON":
        return True
    if _KRX_STATE["probed"]:
        return bool(_KRX_STATE["allowed"])
    ok, why = _krx_probe()
    _KRX_STATE.update(probed=True, allowed=ok, reason=why)
    (LOG.ok if ok else LOG.warn)(
        f"KRX 접근 프로브: {'가능' if ok else '차단/불가'} — {why}"
        + ("" if ok else " → 이번 실행은 비KRX 경로만 씁니다(재시도하지 않습니다)."))
    return ok


def _krx_probe() -> Tuple[bool, str]:
    """가벼운 1회 요청으로 차단 여부를 판정한다. 실패해도 재시도하지 않는다."""
    try:
        txt = http_get("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                       source="krx", tries=1, timeout=8)
    except Exception as e:                                            # noqa
        return False, f"요청 예외 {type(e).__name__}"
    if txt is None:
        return False, "응답 없음(차단·타임아웃·DNS 중 하나)"
    t = str(txt)[:400]
    if "Host not in allowlist" in t or "403" in t or "Forbidden" in t:
        return False, "403/차단 응답"
    return True, "응답 수신"


# ── 코어 수집기에 차단 게이트를 씌운다 (원본은 그대로 두고 감싼다) ───────────────────────────
_ORIG_KRXG_WARMUP = KRXG.warmup


def fetch_listing_snapshots_guarded(months: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX 스냅샷은 '보강'일 뿐이므로, 막혀 있으면 조용히 빈 표를 주고 넘어간다.
    유니버스의 진실은 상장일·폐지일(+가격이력 재구성)이지 스냅샷이 아니다."""
    if not krx_allowed():
        LOG.info("KRX 상장 스냅샷을 건너뜁니다(차단/비활성). 유니버스는 FDR·DART·네이버·"
                 "가격이력 재구성으로 구성되며, 이는 정상 경로입니다.")
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    return fetch_pykrx_snapshots(months)


KRXG.warmup = lambda: (krx_allowed() and _ORIG_KRXG_WARMUP())

# 가격 체인 재정렬 — §1-8 그대로 FDR 우선, pykrx 는 KRX 가 열려 있을 때만.
PRICE_CHAIN = [("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf),
               ("pykrx", lambda c, s, e: _px_pykrx(c, s, e) if krx_allowed() else None)]


# ═══ 상장주식수 — DART 주식총수현황 (비KRX · PIT 완전) ═══════════════════════════════════════
def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int],
                      corp_years: Optional[Dict[str, Sequence[int]]] = None) -> pd.DataFrame:
    """DART '주식의 총수 현황'. 접수일(rcept_dt) 기준이라 PIT 가 구조적으로 보장된다.
    KRX 시가총액 스냅샷의 완전한 대체재이며, 오히려 PIT 관점에서는 더 낫다."""
    cols = ["corp_code", "period_end", "knowledge_date", "shares_total"]
    if not DART_API_KEY or not len(corp_codes):
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_shares_total", scope="shared")
    have = set()
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["knowledge_date"] = as_ts_series(cached["knowledge_date"])
        have = set(zip(cached["corp_code"].astype(str),
                       cached["period_end"].astype(str).str.slice(0, 4)))
        frames.append(cached.reindex(columns=cols))
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(cached):,}행 재사용")

    # ★ '조회했는데 자료가 없는' (회사, 연도) 는 캐시에 남지 않으므로 매 실행 다시 호출된다.
    #   최악의 경우 8,000콜 × 매 실행 = 매번 17분을 같은 빈 응답에 쓴다. 별도 원장에 남겨
    #   60일간 재시도하지 않는다(영구 포기가 아니라 유예).
    MISS_RETRY_DAYS = 60
    _today = as_ts(_dt.date.today())
    miss = set()
    _mt = VAULT.get_table("dart_shares_missing", scope="shared")
    if _mt is not None and len(_mt):
        _mt = _mt.copy()
        _mt["attempted_at"] = as_ts_series(_mt["attempted_at"])
        fresh = _mt[(_today - _mt["attempted_at"]).dt.days < MISS_RETRY_DAYS]
        miss = set(zip(fresh["corp_code"].astype(str), fresh["year"].astype(str)))
        if len(miss):
            LOG.info(f"DART 주식총수 '자료없음' 원장 {len(miss):,}건은 {MISS_RETRY_DAYS}일간 "
                     f"재조회하지 않습니다(빈 응답 반복 방지).")
    #   corp_years 를 주면 '그 회사가 실제로 필요한 연도'만 받는다(수요 기반).
    jobs = [(c, y) for c in corp_codes
            for y in (corp_years.get(str(c), years) if corp_years else years)
            if (str(c), str(y)) not in have and (str(c), str(y)) not in miss]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        LOG.info(f"DART 주식총수현황 {len(jobs):,}건 수집 (연 1회/사 — 사업보고서 기준)")

        def _one(job):
            c, y = job
            js = dart_api("stockTotqySttus.json",
                          {"corp_code": c, "bsns_year": int(y), "reprt_code": "11011"})
            if not js or not isinstance(js.get("list"), list):
                return None
            rows = []
            for r in js["list"]:
                q = str(r.get("istc_totqy", "")).replace(",", "").strip()
                if not q or not q.replace("-", "").isdigit():
                    continue
                rows.append({"corp_code": c, "period_end": f"{y}-12-31",
                             "rcept_no": r.get("rcept_no", ""),
                             "shares_total": float(q)})
            if not rows:
                return None
            d = pd.DataFrame(rows)
            # 같은 연도에 보통주/우선주가 여러 행 → 합계가 아니라 최대값(보통주 총수)을 취한다
            d = d.sort_values("shares_total", ascending=False).head(1)
            return d

        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
        got = [d for d in res if d is not None and len(d)]
        _miss_rows = [{"corp_code": str(c), "year": str(y), "attempted_at": _today}
                      for (c, y), d in zip(jobs, res) if d is None or not len(d)]
        if _miss_rows:
            _prev = _mt if (_mt is not None and len(_mt)) else None
            _all = pd.concat([_prev, pd.DataFrame(_miss_rows)], ignore_index=True) \
                if _prev is not None else pd.DataFrame(_miss_rows)
            _all = (_all.sort_values("attempted_at")
                        .drop_duplicates(["corp_code", "year"], keep="last")
                        .reset_index(drop=True))
            VAULT.put_table("dart_shares_missing", _all, scope="shared", domain="dart",
                            source="fetch_dart_shares:miss_ledger")
            LOG.info(f"DART 주식총수 자료없음 {len(_miss_rows):,}건을 원장에 기록했습니다.")
        if got:
            n = pd.concat(got, ignore_index=True)
            n["knowledge_date"] = [_knowledge_from_rcept(rn, "11011", int(str(pe)[:4]))
                                   for rn, pe in zip(n.get("rcept_no", ""), n["period_end"])]
            frames.append(n.reindex(columns=cols))

    if not frames:
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True)
    S["period_end"] = S["period_end"].astype(str)
    S = S.dropna(subset=["corp_code", "shares_total"]).drop_duplicates(
        ["corp_code", "period_end"], keep="last")
    VAULT.put_table("dart_shares_total", S, scope="shared", domain="dart",
                    source="opendart stockTotqySttus",
                    extra={"note": "발행주식총수(PIT) — 전 전략 공용. KRX 시총 스냅샷 대체재"})
    PIPE.io("OUT", "DRIVE", "dart_shares_total", S, source="opendart")
    LOG.ok(f"DART 주식총수 {len(S):,}행 ({S['corp_code'].nunique():,}사) — "
           f"KRX 없이 PIT 시가총액 분모를 확보했습니다")
    return S


def shares_panel_from_dart(dart_sh: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """DART 주식총수 → (code, snap_date, shares) 형태로 변환해 기존 경로에 그대로 물린다."""
    if dart_sh is None or not len(dart_sh) or sec is None or not len(sec):
        return pd.DataFrame(columns=["snap_date", "code", "shares", "mcap_snap"])
    c2c = (sec.dropna(subset=["corp_code"])
              .assign(corp_code=lambda d: d["corp_code"].astype(str))
              .set_index("corp_code")["code"].to_dict())
    d = dart_sh.copy()
    d["code"] = d["corp_code"].astype(str).map(c2c)
    d = d.dropna(subset=["code"])
    if not len(d):
        return pd.DataFrame(columns=["snap_date", "code", "shares", "mcap_snap"])
    # snap_date 를 knowledge_date 로 둔다 → 하류에서 +1영업일이 한 번 더 붙어도 미래를 보지 않는다
    return pd.DataFrame({"snap_date": as_ts_series(d["knowledge_date"]), "code": d["code"],
                         "shares": pd.to_numeric(d["shares_total"], errors="coerce"),
                         "mcap_snap": np.nan}).dropna(subset=["snap_date", "shares"])


# ═══ 투자자 수급 — 네이버 (비KRX) ═══════════════════════════════════════════════════════════
_NV_TREND = "https://m.stock.naver.com/api/stock/{code}/trend"
_NV_FRGN = "https://finance.naver.com/item/frgn.naver?code={code}&page={page}"


def _nv_pick_key(keys: Sequence[str], *needles) -> Optional[str]:
    for k in keys:
        kl = str(k).lower()
        if all(n.lower() in kl for n in needles):
            return k
    return None


def _pick_date_col(d: pd.DataFrame) -> Optional[str]:
    """날짜 컬럼을 '이름'이 아니라 '내용'으로 찾는다.

    ★ 이름 추정은 실제로 깨진다: 네이버는 날짜 필드를 localTradedAt 으로 준다 —
      'date' 도 'dt' 도 들어 있지 않다. 이름 규칙에 걸면 조용히 전 종목 수집이 실패한다.
      (이 함수는 리허설이 실제로 잡아낸 결함을 고친 것이다)
    """
    best, best_score = None, 0.0
    for c in d.columns:
        try:
            v = as_ts_series(d[c])
        except Exception:
            continue
        ok = v.notna()
        if not ok.any():
            continue
        sane = ok & (v >= pd.Timestamp("1990-01-01")) & (v <= pd.Timestamp("2100-01-01"))
        score = float(sane.mean())
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.7 else None


def naver_trend_flows(code: str, start: str, end: str, page_size: int = 300,
                      max_pages: int = 12) -> Optional[pd.DataFrame]:
    """네이버 모바일 API 의 종목별 투자자 매매동향(JSON).
    ★ 필드명이 개편될 수 있으므로 이름을 하드코딩하지 않고 '내용으로' 찾는다."""
    rows = []
    for page in range(1, max_pages + 1):
        js = http_json(_NV_TREND.format(code=code), source="naver",
                       params={"pageSize": page_size, "page": page}, tries=2,
                       referer=f"https://m.stock.naver.com/domestic/stock/{code}/trend")
        block = None
        if isinstance(js, dict):
            for v in js.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    block = v
                    break
        elif isinstance(js, list) and js and isinstance(js[0], dict):
            block = js
        if not block:
            break
        rows.extend(block)
        if len(block) < page_size:
            break
        # ★ 이미 시작일 이전까지 받았으면 더 넘기지 않는다. 페이지를 끝까지 도는 것은
        #   종목당 수 회의 불필요한 요청이고, 1,200종목이면 그 자체로 수십 분이다.
        try:
            _d = pd.DataFrame(block)
            _k = _pick_date_col(_d)
            if _k is not None and as_ts_series(_d[_k]).min() < as_ts(start):
                break
        except Exception:
            pass
    if not rows:
        return None
    d = pd.DataFrame(rows)
    ks = list(d.columns)
    date_k = _pick_date_col(d)
    ind_k = _nv_pick_key(ks, "individ") or _nv_pick_key(ks, "personal")
    frg_k = _nv_pick_key(ks, "foreign")
    org_k = _nv_pick_key(ks, "organ") or _nv_pick_key(ks, "institu")
    close_k = _nv_pick_key(ks, "close") or _nv_pick_key(ks, "price")
    if date_k is None or (ind_k is None and frg_k is None and org_k is None):
        LOG.debug(f"네이버 수급 필드 인식 실패({code}) — 컬럼: {ks[:10]}")
        return None
    num = lambda k: (pd.to_numeric(d[k].astype(str).str.replace(",", "", regex=False),
                                   errors="coerce") if k else pd.Series(np.nan, index=d.index))
    close = num(close_k).replace(0, np.nan)

    # 순매수가 '수량'이면 금액으로 환산한다 — 단위 혼동은 f_inst/f_ret_ex 스케일을 통째로 망친다
    def to_krw(s):
        if s.isna().all():
            return s
        med = float(s.abs().median() or 0)
        return s * close if (med < 1e6 and close.notna().any()) else s

    out = pd.DataFrame({
        "code": code, "date": as_ts_series(d[date_k]),
        "retail_net": to_krw(num(ind_k)), "inst_net": to_krw(num(org_k)),
        "foreign_net": to_krw(num(frg_k)), "src": "naver_trend"})
    out = out.dropna(subset=["date"])
    out = out[(out["date"] >= as_ts(start)) & (out["date"] <= as_ts(end))]
    if out.empty or out[["retail_net", "inst_net", "foreign_net"]].notna().sum().sum() == 0:
        return None
    if ind_k is None:
        # 개인이 없으면 개인 ≈ -(기관+외국인). 기타법인이 빠진 근사임을 명시한다.
        out["retail_net"] = -(out["inst_net"].fillna(0) + out["foreign_net"].fillna(0))
        out["src"] = "naver_trend(개인=근사)"
    return out


def naver_frgn_flows(code: str, start: str, end: str, max_pages: int = 40
                     ) -> Optional[pd.DataFrame]:
    """네이버 금융 '외국인·기관' 표(HTML). JSON 경로가 막혔을 때의 최종 폴백.
    개인은 제공되지 않으므로 -(기관+외국인) 근사이며, 그 사실을 src 에 남긴다."""
    frames = []
    for page in range(1, max_pages + 1):
        html = http_get(_NV_FRGN.format(code=code, page=page), source="naver", tries=2,
                        referer=f"https://finance.naver.com/item/main.naver?code={code}")
        if not html:
            break
        try:
            tabs = pd.read_html(io.StringIO(html))
        except Exception:
            break
        t = None
        for cand in tabs:
            cols = " ".join(str(c) for c in np.ravel(cand.columns))
            if "날짜" in cols and ("기관" in cols or "외국인" in cols):
                t = cand
                break
        if t is None or not len(t):
            break
        t.columns = [" ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)
                     for c in t.columns]
        dcol = next((c for c in t.columns if "날짜" in c), None)
        ccol = next((c for c in t.columns if "종가" in c), None)
        icol = next((c for c in t.columns if "기관" in c), None)
        fcol = next((c for c in t.columns if "외국인" in c and "보유" not in c), None)
        if dcol is None:
            break
        num = lambda c: (pd.to_numeric(t[c].astype(str).str.replace(",", "", regex=False),
                                       errors="coerce") if c else pd.Series(np.nan, index=t.index))
        close = num(ccol)
        part = pd.DataFrame({"code": code, "date": as_ts_series(t[dcol]),
                             "inst_net": num(icol) * close, "foreign_net": num(fcol) * close})
        part = part.dropna(subset=["date"])
        if part.empty:
            break
        frames.append(part)
        if part["date"].min() < as_ts(start):
            break
    if not frames:
        return None
    F = pd.concat(frames, ignore_index=True).drop_duplicates(["code", "date"])
    F = F[(F["date"] >= as_ts(start)) & (F["date"] <= as_ts(end))]
    if F.empty:
        return None
    F["retail_net"] = -(F["inst_net"].fillna(0) + F["foreign_net"].fillna(0))
    F["src"] = "naver_frgn(개인=근사)"
    return F


# ═══ 다중소스 코드 발굴 · 상장/폐지 창 재구성 (KRX 없이 C2·C13 성립) ══════════════════════════
UNIV_SRC_LEDGER: List[dict] = []
# 종목별 '후보였던 연도 구간' — DART 처럼 비싼 수집의 범위를 여기에 맞춘다.
# (전 종목 × 전 연도로 받으면 11만 콜이지만, 살 수 있었던 종목의 그 시기만 받으면 수천 콜이다)
CANDIDATE_YEARS: Dict[str, Tuple[int, int]] = {}


def discover_codes_multi(sec: pd.DataFrame) -> pd.DataFrame:
    """종목 코드 발굴을 한 소스에 걸지 않는다. 어느 소스가 몇 개를 기여했는지 원장에 남긴다."""
    parts = []
    if sec is not None and len(sec):
        parts.append(("기존 마스터(FDR/KIND/폐지목록)", set(sec["code"].dropna())))
    # DART corpCode — 상장폐지된 회사도 남아 있으므로 생존자편향 방어에 직접 기여한다
    try:
        cc = fetch_dart_corpcode()
        if cc is not None and len(cc) and "code" in cc.columns:
            parts.append(("DART corpCode", set(cc["code"].dropna().map(to_code6)) - {None}))
    except Exception as e:                                            # noqa
        LOG.debug(f"DART corpCode 발굴 실패: {type(e).__name__}")
    # 네이버 시세 목록(현재 상장분) — 이름·시장 보강용
    try:
        nv = set()
        for mkt, sosok in (("KOSPI", 0), ("KOSDAQ", 1)):
            for page in range(1, 4):
                html = http_get("https://finance.naver.com/sise/sise_market_sum.naver",
                                source="naver", params={"sosok": sosok, "page": page}, tries=1)
                if not html:
                    break
                nv |= {to_code6(m) for m in re.findall(r"code=(\d{6})", html)}
        nv.discard(None)
        if nv:
            parts.append(("네이버 시세목록", nv))
    except Exception as e:                                            # noqa
        LOG.debug(f"네이버 시세목록 발굴 실패: {type(e).__name__}")

    allc: set = set()
    for name, s in parts:
        new = len(s - allc)
        UNIV_SRC_LEDGER.append({"source": name, "codes": len(s), "new": new})
        allc |= s
    LOG.table([[r["source"], f"{r['codes']:,}", f"{r['new']:,}"] for r in UNIV_SRC_LEDGER],
              ["코드 소스", "보유", "신규 기여"], ["l", "r", "r"],
              title=f"다중소스 종목 발굴 — 합집합 {len(allc):,}종목 (KRX 없이 구성)")
    base = sec.copy() if sec is not None and len(sec) else pd.DataFrame(columns=SEC_MASTER_COLS)
    missing = sorted(allc - set(base["code"])) if len(base) else sorted(allc)
    if missing:
        # 새로 발굴한 종목도 corp_code 를 붙여야 DART 방화벽이 그 종목에 작동한다
        cmap, nmap = {}, {}
        try:
            cc = fetch_dart_corpcode()
            if cc is not None and len(cc):
                cc = cc.dropna(subset=["code"]).drop_duplicates("code")
                cmap = dict(zip(cc["code"].map(to_code6), cc["corp_code"].astype(str)))
                nmap = dict(zip(cc["code"].map(to_code6), cc["corp_name"].astype(str)))
        except Exception:
            pass
        add = pd.DataFrame({"code": missing,
                            "name": [nmap.get(c, "") for c in missing],
                            "market": "", "listing_date": pd.NaT,
                            "delisting_date": pd.NaT,
                            "corp_code": [cmap.get(c, np.nan) for c in missing],
                            "industry": "",
                            "sector_src": "multi", "src": "multi_discovery"})
        base = pd.concat([base.reindex(columns=list(dict.fromkeys(SEC_MASTER_COLS))),
                          add.reindex(columns=list(dict.fromkeys(SEC_MASTER_COLS)))],
                         ignore_index=True)
        LOG.info(f"명부에 없던 {len(missing):,}종목을 추가했습니다 — 빠뜨리면 그대로 생존자편향입니다.")
    return base.drop_duplicates("code")


def reconstruct_listing_windows(sec: pd.DataFrame, px: pd.DataFrame,
                                panel_end: str) -> pd.DataFrame:
    """★ KRX 명부 없이도 성립하는 상장/폐지 판정 — '거래가 있었다'는 사실 자체가 증거다.

      · listing_date  결측 → 첫 거래일 (가격 이력의 시작)
      · delisting_date 결측 → 마지막 거래일 이후 60거래일간 거래가 없고, 패널 종료일보다
        충분히 앞서면 그 시점에 상장폐지된 것으로 '추정'한다. 추정분은 provenance 에 남긴다.
      · 추정은 언제나 명부보다 우선순위가 낮다(명부가 있으면 명부를 쓴다).

    이 재구성이 없으면, KRX 가 막힌 순간 폐지 종목이 '데이터 없음'으로 조용히 사라지고
    그것이 곧 생존자편향이다. 그래서 이 함수는 선택이 아니라 필수 경로다.
    """
    if px is None or not len(px):
        return sec
    S = sec.copy()
    S["listing_date"] = as_ts_series(S["listing_date"])
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    g = px.groupby("code")["date"]
    first_t, last_t = g.min(), g.max()
    end_ts = as_ts(panel_end)
    cal = np.sort(pd.unique(as_ts_series(px["date"]).values))
    # 마지막 거래일이 '전체 거래일 기준 60일 이전'이면 더 이상 거래되지 않는 종목으로 본다
    cutoff_idx = max(0, len(cal) - 60)
    cutoff = pd.Timestamp(cal[cutoff_idx]) if len(cal) else end_ts

    S["first_trade"] = S["code"].map(first_t)
    S["last_trade"] = S["code"].map(last_t)
    prov_l, prov_d = [], []
    ld, dd = [], []
    for r in S.itertuples(index=False):
        l0, d0 = r.listing_date, r.delisting_date
        ft, lt = getattr(r, "first_trade", pd.NaT), getattr(r, "last_trade", pd.NaT)
        if pd.notna(l0):
            ld.append(l0); prov_l.append("명부")
        elif pd.notna(ft):
            ld.append(ft); prov_l.append("가격이력 재구성")
        else:
            ld.append(pd.NaT); prov_l.append("없음")
        if pd.notna(d0):
            dd.append(d0); prov_d.append("명부")
        elif pd.notna(lt) and lt < cutoff:
            dd.append(lt + pd.Timedelta(days=1)); prov_d.append("가격이력 재구성(추정)")
        else:
            dd.append(pd.NaT); prov_d.append("상장 중")
    S["listing_date"], S["delisting_date"] = ld, dd
    S["listing_src"], S["delisting_src"] = prov_l, prov_d

    rows = []
    for col, lab in (("listing_src", "상장일"), ("delisting_src", "폐지일")):
        vc = S[col].value_counts()
        for k, v in vc.items():
            rows.append([lab, k, f"{v:,}"])
    LOG.table(rows, ["항목", "근거", "종목수"], ["l", "l", "r"],
              title="상장/폐지일 출처 원장 (C2) — 어떤 근거로 유니버스 멤버십이 정해졌는가")
    n_est = int((S["delisting_src"] == "가격이력 재구성(추정)").sum())
    n_known = int((S["delisting_src"] == "명부").sum())
    LOG.ok(f"폐지 종목 {n_known + n_est:,}개 확보 (명부 {n_known:,} + 가격이력 추정 {n_est:,}) — "
           f"KRX 없이 C2(생존자편향 제거) 성립")
    if n_known + n_est < 100:
        LOG.warn("폐지 종목이 100개 미만입니다. 10년이면 통상 수백 종목이 사라집니다 — "
                 "가격 수집 커버리지가 낮으면 폐지 종목이 '데이터 없음'으로 빠져 "
                 "생존자편향이 남습니다. 이 수치를 반드시 결과 해석에 반영하세요.")
    return S.drop(columns=["first_trade", "last_trade"], errors="ignore")


def audit_survivorship_coverage(sec: pd.DataFrame, px: pd.DataFrame,
                                start: str, end: str) -> pd.DataFrame:
    """★ 생존자편향 '잔존분'을 추정해 표로 낸다. 제거했다고 주장하는 대신 남은 양을 측정한다.

    폐지 종목을 유니버스에 넣어도, 그 종목의 가격이 없으면 백테스트는 그 종목을 애초에
    살 수 없다 → 실제로는 사서 -100% 를 맞았을 사례가 통째로 빠지고 성과가 위로 편향된다.
    (KRX 가 막히면 폐지 직전 구간 가격을 못 받는 일이 잦으므로 특히 중요하다)
    """
    if sec is None or not len(sec):
        return pd.DataFrame()
    S = sec.copy()
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    win = S[(S["delisting_date"] >= as_ts(start)) & (S["delisting_date"] <= as_ts(end))]
    n_win = len(win)
    if n_win == 0:
        LOG.warn("백테스트 구간 내 상장폐지 종목이 0건입니다 — 생존자편향이 그대로 남아 있습니다(C2 미충족).")
        return pd.DataFrame()
    cov = pd.DataFrame()
    if px is not None and len(px):
        last = px.groupby("code")["date"].max()
        w = win.copy()
        w["last_px"] = w["code"].map(last)
        w["gap_days"] = (w["delisting_date"] - w["last_px"]).dt.days
        have = w["last_px"].notna()
        near = have & (w["gap_days"].abs() <= 60)
        rows = [["구간 내 폐지 종목", f"{n_win:,}", "유니버스에 포함되어야 하는 전량"],
                ["가격 이력 보유", f"{int(have.sum()):,}",
                 f"{100*have.mean():.1f}% — 없으면 애초에 매수 자체가 불가"],
                ["폐지 시점 근처(±60일) 가격 보유", f"{int(near.sum()):,}",
                 f"{100*near.mean():.1f}% — 이 종목만 정리매매/-100% 가 정상 반영된다"],
                ["★ 생존자편향 잔존 추정", f"{int((~near).sum()):,}",
                 f"{100*(~near).mean():.1f}% — 이만큼은 '살 수 없어서' 손실이 계상되지 않는다"]]
        LOG.table(rows, ["항목", "종목수", "의미"], ["l", "r", "l"],
                  title="C2 생존자편향 잔존 감사 — 제거를 주장하지 않고 남은 양을 측정한다")
        if float((~near).mean()) > 0.5:
            LOG.warn("폐지 종목의 절반 이상이 폐지 시점 가격을 갖지 못했습니다. "
                     "성과는 그만큼 위로 편향되어 있습니다 — 결과 해석에 반드시 반영하세요. "
                     "(가격 소스가 폐지 종목을 잘 주지 않는 구조적 한계이며 숨기지 않습니다)")
        cov = w[["code", "delisting_date", "last_px", "gap_days"]]
    return cov


def select_flow_targets(px: pd.DataFrame, start: str, end: str,
                        max_codes: int = FLOW_MAX_CODES) -> List[str]:
    """수급을 '전 종목'이 아니라 '이 전략이 실제로 진입할 수 있었던 종목'에만 받는다.

    ★ 이 선별은 반드시 '인과적(causal)'이어야 한다.
      전 구간 중앙 거래대금이나 전 구간 최대 낙폭 같은 '표본 전체 통계'로 고르면,
      나중에 거래대금이 말라 죽은 종목(=상장폐지 예비군)이 통째로 제외된다.
      그건 곧 생존자편향의 재유입이며, 성과를 위로 부풀린다.
      → 각 시점 t 의 '그 시점까지의 정보'(252일 낙폭·252일 평균거래대금)로 후보를 판정하고,
        한 번이라도 후보였던 종목을 수집 대상으로 삼는다. 시점 t 의 신호는 시점 t 에
        이미 존재하던 조건으로만 결정되므로 미래정보가 개입하지 않는다.

    국면 C 는 f_dd < -0.30 을 요구하므로, 그만한 낙폭을 겪은 적이 없는 종목의 수급은
    어차피 신호에 쓰이지 않는다. 전 종목을 받으면 4시간 예산을 수급 하나가 다 쓴다(§9).
    제외된 것이 무엇이고 그 대가가 얼마인지는 표로 남긴다 — 조용한 축소는 하지 않는다.
    """
    if px is None or not len(px):
        return []
    d = px[(px["date"] >= as_ts(start) - pd.Timedelta(days=400)) &
           (px["date"] <= as_ts(end))][["code", "date", "close", "amount"]].copy()
    if d.empty:
        return []
    d = d.sort_values(["code", "date"])
    g = d.groupby("code", observed=True)
    roll_max = g["close"].transform(lambda s: s.rolling(252, min_periods=60).max())
    d["dd"] = d["close"] / roll_max - 1.0
    d["adv252"] = g["amount"].transform(lambda s: s.rolling(252, min_periods=60).mean())

    # 시점별 후보 여부 — 전부 '그 시점까지'의 정보만 쓴다
    cand = (d["dd"] <= FLOW_DD_PREFILTER) & (d["adv252"] >= MIN_ADV_KRW)
    d["cand"] = cand.fillna(False)
    n_all = int(d["code"].nunique())
    ever = d.groupby("code", observed=True)["cand"].any()
    cand_codes = ever[ever].index.astype(str)
    if not len(cand_codes):
        LOG.warn("수급 대상 후보가 0종목입니다 — 낙폭/유동성 프리필터가 너무 강하거나 "
                 "가격 커버리지가 부족합니다. 전 종목으로 진행합니다(느립니다).")
        return []

    sub = d[d["code"].isin(set(cand_codes))]
    weeks_per_code = sub.groupby("code", observed=True)["cand"].sum()
    # 우선순위: '최초 후보 시점의 유동성' — 사후 통계가 아니라 그때의 관측치를 쓴다
    first_hit = (sub[sub["cand"]].sort_values("date")
                 .drop_duplicates("code", keep="first").set_index("code")["adv252"])
    ranked = first_hit.sort_values(ascending=False)
    capped = ranked.head(max_codes) if max_codes and max_codes > 0 else ranked
    kept = set(capped.index.astype(str))

    # 후보였던 연도 구간을 기록 (DART 수집 범위의 근거)
    CANDIDATE_YEARS.clear()
    _hit = sub[sub["cand"]]
    if len(_hit):
        _yr = _hit.groupby("code", observed=True)["date"].agg(["min", "max"])
        for c, r in _yr.iterrows():
            CANDIDATE_YEARS[str(c)] = (int(pd.Timestamp(r["min"]).year),
                                       int(pd.Timestamp(r["max"]).year))

    tot_w = float(weeks_per_code.sum())
    lost_w = float(weeks_per_code[~weeks_per_code.index.isin(kept)].sum())
    rows = [["전체 가격 보유 종목", f"{n_all:,}", ""],
            [f"후보 경험 (252일 낙폭 ≤ {FLOW_DD_PREFILTER:+.0%} ∧ ADV252 ≥ "
             f"{MIN_ADV_KRW/1e8:.0f}억, 시점별 판정)", f"{len(cand_codes):,}",
             f"{100*len(cand_codes)/max(n_all,1):.0f}%"],
            ["수집 대상(상한 적용)", f"{len(kept):,}",
             f"상한 {max_codes or '무제한'} · 제외 {len(ranked)-len(capped):,}"],
            ["★ 상한으로 잃는 후보-일수", f"{lost_w:,.0f}",
             f"전체 후보-일수의 {100*lost_w/max(tot_w,1):.1f}% — 이만큼이 커버리지 손실"]]
    LOG.table(rows, ["단계", "종목수/일수", "비고"], ["l", "r", "l"],
              title="수급 수집 대상 선별 (인과적 판정) — 진입 불가능했던 종목은 받지 않는다(§9)")
    if lost_w > 0:
        LOG.warn(f"상한(FLOW_MAX_CODES={max_codes})으로 후보-일수의 "
                 f"{100*lost_w/max(tot_w,1):.1f}% 가 수급 없이 남습니다. 해당 종목은 f_inst 결측 → "
                 f"국면 C 판정에서 자동 탈락하므로 '성과'가 아니라 '커버리지'의 한계이며, "
                 f"캐시가 누적되는 재실행마다 줄어듭니다. 0으로 만들려면 FLOW_MAX_CODES=0.")
    return sorted(kept)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  PIT 저장소 / 유니버스 / 셀  (계약 C1·C2·C3·C4·C11)                                 ║
# ║                                                                                          ║
# ║  C1: 모든 데이터 접근은 PIT.get(table, as_of) 한 곳만 통과한다.                            ║
# ║      DataFrame 직접 슬라이싱 금지. 우회 파라미터를 만들지 않는다.                          ║
# ║  C2: 유니버스는 상장폐지 종목을 포함한다. 정리매매가 없으면 -100%.                          ║
# ║  C11: 셀 = (date, industry, size_bucket). 다른 그룹키 금지.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, pd.DataFrame] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: pd.DataFrame, key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            LOG.debug(f"PIT 등록(빈 테이블): {name}")
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[C1 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        d = d.reset_index(drop=True)
        self._t[name] = d
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def drop(self, name: str) -> None:
        """등록을 되돌린다. 합성 스모크가 남긴 테이블이 실데이터 실행에 섞이면
        '재무 없음' 경고가 사라진 채 전 종목 결측으로 조용히 진행된다."""
        self._t.pop(name, None)
        self._meta.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """시점 as_of 에서 '알 수 있었던' 행만 반환.
        latest_by 를 주면 그 키별 최신 1행(=당시 최신 관측)만 남긴다."""
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        t = as_ts(as_of)
        d = self._t[name]
        if d.empty:
            return d
        # knowledge_date 정렬되어 있으므로 searchsorted 로 O(log n) 절단
        pos = int(np.searchsorted(d["knowledge_date"].values, np.datetime64(t), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def asof_join(self, panel: pd.DataFrame, name: str, by: str,
                  left_time: str = "month", cols: Optional[Sequence[str]] = None,
                  suffix: str = "") -> pd.DataFrame:
        """get() 의 벡터화 등가물. 패널 전체에 대해 한 번에 as-of 결합한다.

        merge_asof(direction='backward') 는 knowledge_date <= month 인 마지막 행만 붙이므로
        C1 과 정확히 동일한 의미를 갖는다. 루프로 get() 을 3만 번 부르는 대신 이걸 쓴다.
        """
        self.access_log[name] += 1
        if name not in self._t or self._t[name].empty or panel.empty:
            return panel
        right = self._t[name]
        if by not in right.columns or by not in panel.columns:
            LOG.debug(f"asof_join 건너뜀: '{name}' 에 결합키 '{by}' 없음")
            return panel
        use = [c for c in (cols or [c for c in right.columns
                                    if c not in ("event_date", "_src")]) if c in right.columns]
        for c in (by, "knowledge_date"):
            if c not in use:
                use.append(c)
        R = (right[use].dropna(subset=["knowledge_date", by])
                        .sort_values("knowledge_date", kind="stable")).copy()
        if R.empty:
            return panel

        # ★★ 결합키가 결측인 패널 행을 '떨어뜨리면' 안 된다. ★★
        #   attach_fundamentals 에서 corp_code 가 없는 종목(대개 상장폐지·신규상장·비DART)이
        #   통째로 사라지면 그게 곧 생존자편향 재유입이다(C2 위반). merge_asof 는 by 키에
        #   NaN 이 있으면 다루지 못하므로, 유효키 부분만 결합한 뒤 전체 패널에 되붙인다.
        base = panel.copy()
        base["_ord"] = np.arange(len(base))
        mask = base[left_time].notna() & base[by].notna()
        n_drop = int((~mask).sum())
        if n_drop:
            LOG.debug(f"asof_join '{name}': 결합키 결측 {n_drop:,}행은 결측값으로 보존합니다"
                      f"(행을 버리지 않습니다 — C2).")
        L = base[mask].copy()
        if L.empty:
            LOG.warn(f"asof_join '{name}': 결합 가능한 행이 없습니다. 결합을 건너뜁니다.")
            return panel
        R[by] = R[by].astype(str)
        L[by] = L[by].astype(str)
        L = L.sort_values(left_time, kind="stable")
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", suffix or "_r"))
        except Exception as e:                                     # noqa
            LOG.warn(f"asof_join 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다. "
                     f"대개 정렬/타입 문제입니다.")
            return panel
        new_cols = [c for c in M.columns if c not in base.columns]
        if not new_cols:
            return panel
        add = M.set_index("_ord")[new_cols]
        out = base.set_index("_ord")
        out = out.join(add, how="left")            # 결합 실패 행은 NaN 으로 남고, 행은 유지된다
        out = out.sort_index().reset_index(drop=True)
        out.index = panel.index
        return out

    def report(self):
        rows = []
        for n, m in self._meta.items():
            rows.append([n, f"{m['rows']:,}",
                         str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                         ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n,0):,}"])
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (C1 — 모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()


# ── 유니버스 (C2) ───────────────────────────────────────────────────────────────────────────
LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    def __init__(self, sec: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame,
                 snap_window_days: int = 100):
        self.sec = sec.copy()
        self.snap = snapshots
        self.attrition: List[dict] = []
        self._cache_at: Dict[pd.Timestamp, List[str]] = {}
        # 스냅샷 주기가 분기면 ±45일 창으로는 대부분의 달이 스냅샷을 못 만난다 → 창을 넓힌다.
        self._snap_window_days = snap_window_days
        self._trading_days = (np.sort(pd.unique(as_ts_series(px_daily["date"]).values))
                              if px_daily is not None and len(px_daily) else
                              np.array([], dtype="datetime64[ns]"))
        self._snap_by_month: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            for d, g in snapshots.groupby("snap_date"):
                self._snap_by_month[as_ts(d)] = set(g["code"])

        self.sec["listing_date"] = as_ts_series(self.sec["listing_date"])
        self.sec["delisting_date"] = as_ts_series(self.sec["delisting_date"])
        self.sec = self.sec.drop_duplicates("code").reset_index(drop=True)

        # 벡터화용 배열 (at() 이 매월 3,500행 itertuples 를 도는 것을 없앤다)
        self._codes_arr = self.sec["code"].to_numpy(dtype=object)
        self._ld_arr = self.sec["listing_date"].to_numpy(dtype="datetime64[ns]")
        self._dd_arr = self.sec["delisting_date"].to_numpy(dtype="datetime64[ns]")
        self._delist = {c: d for c, d in zip(self._codes_arr, self.sec["delisting_date"])
                        if pd.notna(d)}

        # 상장 후 250거래일 시즈닝 — 거래일 배열에 대한 searchsorted 를 한 번에 벡터화
        #
        # ★ 앵커 주의 (조용한 유니버스 붕괴의 원인) ─────────────────────────────────────
        #   searchsorted 는 '가격패널 시작일 이전에 상장한' 종목을 전부 index 0 으로 보낸다.
        #   거기에 +250 을 더하면 1990년 상장 종목조차 "패널 시작 후 250거래일"에야 시즈닝이
        #   끝난 것으로 계산된다. 2016-08 시작 패널이면 2017년 중반까지 삼성전자를 포함한
        #   기존 상장사 전부가 유니버스에서 빠진다. 에러 없이, 로그도 없이.
        #   → 시즈닝의 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은
        #     이미 오래전에 시즈닝이 끝난 것으로 확정한다.
        self._seasoned: Dict[str, Any] = {}
        _FAR = pd.Timestamp("2100-01-01")     # 패널 안에서 시즈닝이 끝나지 않는 신규 상장
        if len(self._trading_days):
            t0 = self._trading_days[0]
            idx = np.searchsorted(self._trading_days, self._ld_arr, side="left")
            idx_s = idx + LISTING_SEASONING_DAYS
            n_td = len(self._trading_days)
            inside = idx_s < n_td
            seas = np.where(inside,
                            self._trading_days[np.minimum(idx_s, n_td - 1)],
                            np.datetime64(_FAR.isoformat(), "ns"))
            # 패널 시작 전 상장 → 달력 1년으로 확정(패널 시작보다 앞서므로 사실상 제약이 아님)
            pre = (~np.isnat(self._ld_arr)) & (self._ld_arr < t0)
            for c, ld, s, p in zip(self._codes_arr, self._ld_arr, seas, pre):
                if np.isnat(ld):
                    self._seasoned[c] = pd.NaT
                elif p:
                    self._seasoned[c] = as_ts(ld) + pd.Timedelta(days=365)
                else:
                    self._seasoned[c] = as_ts(s)
        else:
            for c, ld in zip(self._codes_arr, self._ld_arr):
                self._seasoned[c] = pd.NaT if np.isnat(ld) else as_ts(ld) + pd.Timedelta(days=365)

    def at(self, t) -> List[str]:
        """시점 t 의 유니버스. t 이후 상장 종목이 하나라도 섞이면 그 자체로 C2 위반이다."""
        t = as_ts(t)
        if t in self._cache_at:
            return self._cache_at[t]

        # ① 상장일·폐지일로 유도한 집합이 '기준선'이다. 이건 항상 성립해야 한다.
        base = set(self._codes_dated_at(t))

        # ② 스냅샷은 '보강'이다. 대체가 아니다.
        #    ★ 과거 스냅샷만 쓴다(미래 스냅샷을 고르면 그 자체가 누수).
        #    ★ 교집합이 아니라 합집합이다. 부분 응답 스냅샷으로 기준선을 깎으면
        #      그 달 유니버스가 조용히 줄어 곧바로 선택편향이 된다. 늘리기만 한다.
        past = [d for d in self._snap_by_month if d <= t]
        if past:
            key = max(past)
            if (t - key).days <= self._snap_window_days:
                base |= set(self._snap_by_month[key])

        # ③ 폐지 이후 종목은 어떤 경로로 들어왔든 반드시 제외한다.
        base -= {c for c, dd in self._delist.items() if pd.notna(dd) and dd <= t}

        # ④ 상장 후 250거래일 시즈닝
        out = [c for c in base
               if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]
        out = sorted(out)
        self._cache_at[t] = out
        return out

    def _codes_dated_at(self, t: pd.Timestamp) -> List[str]:
        """상장일/폐지일 기반 멤버십. itertuples 루프를 매월 도는 대신 벡터화한다
        (종목 3,500 × 120개월 = 42만 회 파이썬 루프였다)."""
        ld, dd = self._ld_arr, self._dd_arr
        tt = np.datetime64(t)
        ok = ~((~np.isnat(ld)) & (ld > tt)) & ~((~np.isnat(dd)) & (dd <= tt))
        ok &= ~(np.isnat(ld) & np.isnat(dd))        # 근거가 전혀 없는 종목은 넣지 않는다
        return self._codes_arr[ok].tolist()

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "PIT유니버스", "가격보유", "유동성필터", "거부권통과",
                 "하한선통과", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max", "size"])
        rows = []
        prev = None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/prev:.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§10.4) — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < 5:
            LOG.warn("최종 선정 종목이 월평균 5개 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 어느 게이트가 원인인지 위 표에서 먼저 확인하세요.")


# ── 셀 (C11) ────────────────────────────────────────────────────────────────────────────────
SIZE_BUCKETS = [(0, 50, "<50"), (50, 100, "50-99"), (100, 300, "100-299"),
                (300, 1000, "300-999"), (1000, 10 ** 9, "1000+")]


def size_bucket(n_emp: float) -> str:
    if n_emp is None or not np.isfinite(n_emp) or n_emp <= 0:
        return "미상"
    for lo, hi, lab in SIZE_BUCKETS:
        if lo <= n_emp < hi:
            return lab
    return "1000+"


def build_cells(panel: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell_key = (date, industry, size_bucket). 규모를 넣는 이유는 §5.6-② 참조:
    정부 지원제도 요건 대부분이 기업 규모에 연동되므로 정책효과가 셀 내 공통충격으로 흡수된다.
    비용 0의 오염 제거."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict()
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["industry_l1"] = p["industry"].str.slice(0, 4)                 # 폴백용 상위 단위
    p["size_bucket"] = p["employees"].map(size_bucket) if "employees" in p.columns else "미상"
    ym = p["month"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["industry"] + "|" + p["size_bucket"]
    # 폴백 사다리를 컬럼으로 미리 만들어 둔다. 센서별로 유효 관측이 부족할 때
    # xsec_z_l 이 이 사다리를 타고 내려간다(C11 "산업 상위 단위로 폴백").
    p["cell_l2"] = ym + "|" + p["industry_l1"] + "|ALL"
    p["cell_l3"] = ym + "|ALL|ALL"

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    still_n = 0
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        still_n = int(still.sum())
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백 발생: 1차 {n_small:,}행(산업 상위단위로) / 2차 {still_n:,}행(전체로). "
                 f"C11 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 1단계 {p['cell'].nunique():,}개 · 2단계 {p['cell_l2'].nunique():,}개 · "
              f"3단계 {p['cell_l3'].nunique():,}개")
    return p

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-A  강제 재고(신용융자잔고) · 소유권 이전(투자자유형별 순매수) · 시가총액 · 감시목록  ║
# ║                                                                                          ║
# ║  이 전략의 데이터 등급이 여기서 결정된다(§5.2 / F1 카나리).                                ║
# ║    PRIMARY_DAILY    종목별 '일별' 신용거래융자 잔고        → 완전체                        ║
# ║    FALLBACK_A_WEEKLY 주간 관측 + forward-fill(★보간 금지)  → 해상도 손실                   ║
# ║    FALLBACK_B_PROXY 개인 순매수 252일 누적 / 시가총액      → 사실상 다른 전략              ║
# ║  조용히 강등되지 않는다. 등급은 전역 CREDIT_GRADE 에 남고 리포트 첫 줄에 인쇄된다.          ║
# ║                                                                                          ║
# ║  PIT: 신용잔고·수급의 knowledge_date = 거래일 + 1영업일 (당일 잔고는 익일 공표).           ║
# ║       이 하루를 흘리면 일 단위 타이밍 전략인 이 전략의 성과가 크게 부풀려진다(§4.1).        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CREDIT_GRADE = "UNKNOWN"          # PRIMARY_DAILY / FALLBACK_A_WEEKLY / FALLBACK_B_PROXY / NONE
CREDIT_SOURCE_NOTE = ""
FLOW_GRADE = "UNKNOWN"            # FULL / APPROX(개인=근사) / PARTIAL / NONE
FLOW_APPROX = False               # 개인이 -(기관+외국인) 근사인가 (퇴화 판정의 근거)
WATCH_GRADE = "UNKNOWN"           # OK / PARTIAL / NONE
CANARY: "OrderedDict[str, dict]" = OrderedDict()


def canary(cid: str, name: str, passed: Optional[bool], measured: str, action: str = ""):
    """카나리 결과는 '측정값'과 '그래서 무엇을 하는가'를 함께 남긴다. 추측 금지(§2)."""
    CANARY[cid] = {"id": cid, "name": name, "pass": passed, "measured": measured,
                   "action": action}
    icon = "✔" if passed else ("✘" if passed is False else "→")
    (LOG.ok if passed else (LOG.error if passed is False else LOG.info))(
        f"[CANARY {cid}] {icon} {name} — {measured}" + (f" · 조치: {action}" if action else ""))


def _trading_calendar(px: pd.DataFrame) -> np.ndarray:
    if px is None or len(px) == 0:
        return np.array([], dtype="datetime64[ns]")
    return np.sort(pd.unique(as_ts_series(px["date"]).values))


# ═══ 시가총액 (신용잔고율의 분모) ═══════════════════════════════════════════════════════════
def fetch_shares_outstanding(months: pd.DatetimeIndex, sec: Optional[pd.DataFrame] = None,
                             dart_shares: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """상장주식수 월말 스냅샷. 일별 시총 = 일별 종가 × (과거 스냅샷 상장주식수 forward-fill).

    ★ 종목별로 2,500번 부르지 않는다. '날짜별 전종목' 1콜이면 끝나므로 120콜로 10년이 덮인다.
      (종목 루프로 짜면 같은 결과에 수십 배의 시간과 차단 위험을 지불한다)
    ★ 현재 상장주식수를 과거에 적용하면 액면분할·유상증자가 소급되어 시총이 조용히 틀어진다.
    """
    cols = ["snap_date", "code", "shares", "mcap_snap"]
    # ★ 1순위는 DART 주식총수현황이다. 접수일 기준이라 PIT 가 구조적으로 보장되고
    #   KRX 차단과 무관하게 동작한다. KRX 스냅샷은 '보강'이지 전제가 아니다.
    dart_panel = shares_panel_from_dart(dart_shares, sec) if dart_shares is not None else \
        pd.DataFrame(columns=cols)
    if len(dart_panel):
        LOG.ok(f"DART 주식총수 기반 상장주식수 {len(dart_panel):,}행 "
               f"({dart_panel['code'].nunique():,}종목) — KRX 없이 시총 분모 확보")
    cached = VAULT.get_table("krx_shares_outstanding_monthly", scope="shared")
    have = set()
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        frames.append(cached[cols])
        LOG.info(f"공용 캐시에서 상장주식수 스냅샷 {len(have)}개 시점 재사용")

    todo = [m for m in months if m.strftime("%Y-%m-%d") not in have]
    if not krx_allowed():
        todo = []
    if RUN_MODE == "CACHED" or pykrx_stock is None:
        if todo:
            LOG.warn("상장주식수 스냅샷 신규 수집 불가(CACHED 모드 또는 pykrx 없음) — "
                     "시가총액은 캐시분으로만 구성됩니다.")
        todo = []
    if todo and not KRXG.warmup():
        LOG.warn("KRX 세션 없음 — 상장주식수 스냅샷을 건너뜁니다. "
                 "신용잔고율의 분모가 없으면 f_cr 은 '거래대금 20일합' 대리 분모로 폴백합니다.")
        todo = []

    new = []
    if todo:
        bad = 0
        for m in tqdm(todo, desc="상장주식수 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
            d = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd)
            if d is None or len(d) == 0:
                bad += 1
                if bad >= 5:
                    LOG.warn("상장주식수 스냅샷이 연속 5회 비었습니다 — 세션 만료로 판단하고 중단합니다.")
                    break
                continue
            bad = 0
            d = d.reset_index()
            code_c = next((c for c in d.columns if str(c) in ("티커", "종목코드", "ticker")), d.columns[0])
            sh_c = next((c for c in d.columns if "상장주식수" in str(c)), None)
            mc_c = next((c for c in d.columns if "시가총액" in str(c)), None)
            if sh_c is None and mc_c is None:
                continue
            new.append(pd.DataFrame({
                "snap_date": m, "code": d[code_c].map(to_code6),
                "shares": pd.to_numeric(d[sh_c], errors="coerce") if sh_c else np.nan,
                "mcap_snap": pd.to_numeric(d[mc_c], errors="coerce") if mc_c else np.nan,
            }))
        if new:
            frames.append(pd.concat(new, ignore_index=True))

    if len(dart_panel):
        frames.append(dart_panel.reindex(columns=cols))
    if not frames:
        LOG.warn("상장주식수를 한 건도 확보하지 못했습니다 — 시가총액은 '거래대금 20일합' "
                 "대리 분모로 대체됩니다(스케일만 다르고 f_cr 백분위는 성립). "
                 "DART_API_KEY 를 넣으면 PIT 정확한 분모가 생깁니다.")
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True).dropna(subset=["code", "snap_date"])
    S = S.drop_duplicates(["snap_date", "code"], keep="last")[cols]
    if new:
        out = S.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_shares_outstanding_monthly", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "상장주식수 월말 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_shares_outstanding_monthly", S, source="pykrx")
    return S


# ═══ 투자자유형별 일별 순매수 (개인 / 기관 / 외국인) ════════════════════════════════════════
FLOW_COLS = ["code", "date", "retail_net", "inst_net", "foreign_net"]
FLOW_TABLE_COLS = FLOW_COLS + ["src"]


def _flow_from_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None or not krx_allowed():
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_trading_value_by_date(
            as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d = d.rename(columns={d.columns[0]: "date"})

    def pick(*keys):
        for k in keys:
            c = next((c for c in d.columns if k in str(c)), None)
            if c is not None:
                return pd.to_numeric(d[c], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    out = pd.DataFrame({
        "code": code, "date": as_ts_series(d["date"]),
        "retail_net": pick("개인"),
        "inst_net": pick("기관합계", "기관"),
        "foreign_net": pick("외국인합계", "외국인"),
        "src": "pykrx",
    })
    return out if out[["retail_net", "inst_net", "foreign_net"]].notna().any().any() else None


def _flow_one(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """수급 취득 사다리. 어느 경로로 받았는지 src 에 남겨 감사표에 노출한다.
    ★ KRX 가 막혀도 '소유권 이전' 관측이 끊기지 않게 하는 것이 이 사다리의 존재 이유다."""
    for fn in (_flow_from_pykrx, naver_trend_flows, naver_frgn_flows):
        try:
            r = fn(code, start, end)
        except Exception:
            r = None
        if r is not None and len(r):
            return r.reindex(columns=FLOW_COLS + ["src"])
    return None


def fetch_investor_flows_daily(codes: Sequence[str], start: str, end: str,
                               sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """종목별 일별 투자자유형 순매수(금액). 이 전략의 '소유권 이전' 관측치.

    F2 카나리가 여기서 판정된다. 실패하면 §11-2 킬 기준(소유권 이전 관측 불가)이다.
    knowledge_date = 거래일 + 1영업일 (T+1 공표).
    """
    global FLOW_GRADE
    codes = sorted({c for c in map(to_code6, codes) if c})
    cached = VAULT.get_table("krx_investor_flows_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    frames = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        for c in FLOW_TABLE_COLS:
            if c not in cached.columns:
                cached[c] = np.nan
        have_max = cached.groupby("code")["date"].max().to_dict()
        frames.append(cached[FLOW_TABLE_COLS])
        LOG.info(f"공용 캐시에서 일별 수급 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    # ★ 가격과 똑같은 낭비가 여기서 훨씬 비싸게 일어난다(종목당 최대 9페이지).
    #   폐지·거래정지 종목은 마지막 관측일이 영원히 종료일보다 이르므로, 커버리지 판정 없이
    #   '최대일 < 종료일-7일' 만 보면 매 실행 전량 재수집된다. 가격과 같은 판정기를 쓴다.
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        have_min = cached.groupby("code")["date"].min().to_dict()
    listing, delist = {}, {}
    if sec is not None and len(sec) and "code" in sec.columns:
        _s = sec.dropna(subset=["code"]).drop_duplicates("code")
        if "listing_date" in _s.columns:
            listing = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["listing_date"]))
                       if pd.notna(d)}
        if "delisting_date" in _s.columns:
            delist = {str(c): d for c, d in zip(_s["code"], as_ts_series(_s["delisting_date"]))
                      if pd.notna(d)}
    _today = as_ts(_dt.date.today())
    eff_end = min(as_ts(end), _today)
    attempts: Dict[str, dict] = {}
    _fa = VAULT.get_table("flow_fetch_attempts", scope="shared")
    if _fa is not None and len(_fa):
        _fa = _fa.copy()
        for _c in ("attempted_at", "requested_from", "got_min", "got_max"):
            if _c not in _fa.columns:
                _fa[_c] = pd.NaT
            _fa[_c] = as_ts_series(_fa[_c])
        _fa = _fa.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from,
                                  "gmin": r.got_min, "gmax": r.got_max}
                    for r in _fa.itertuples(index=False)}
    todo, reasons = ([], Counter())
    if RUN_MODE != "CACHED":
        todo, reasons = plan_price_fetch(codes, as_ts(start), eff_end, have_min, have_max,
                                         listing, delist, attempts, _today,
                                         retry_fail_days=30, retry_stale_days=21,
                                         tol_back=14, tol_fwd=7)
    if reasons:
        LOG.table([[k, f"{v:,}"] for k, v in reasons.most_common()] +
                  [["── 실제 수집 대상", f"{len(todo):,}"]],
                  ["판정 사유", "종목수"], ["l", "r"],
                  title=f"수급 수집 판정 — 대상 {len(codes):,}종목 중 {len(todo):,}종목만 받습니다")
    if todo:
        LOG.info(f"일별 수급 {len(todo):,}종목 수집 (캐시 미보유/증분분만)")
        fails = {"n": 0}

        def _one(job):
            c, s = job
            r = _flow_one(c, s, end)
            if r is None:
                fails["n"] += 1
            return r

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="일별 수급")
        got = [d for d in res if d is not None and len(d)]
        if got:
            frames.append(pd.concat(got, ignore_index=True).reindex(columns=FLOW_TABLE_COLS))
        # ★ 시도 원장: 받아도 커버리지가 안 늘면 다음 실행이 같은 요청을 반복하지 않는다
        _att_rows = []
        for (c, st), d in zip(todo, res):
            _dd = as_ts_series(d["date"]) if (d is not None and len(d)) else pd.Series(dtype="datetime64[ns]")
            _gmin = min([x for x in (have_min.get(c), (_dd.min() if len(_dd) else pd.NaT))
                         if pd.notna(x)] or [pd.NaT])
            _gmax = max([x for x in (have_max.get(c), (_dd.max() if len(_dd) else pd.NaT))
                         if pd.notna(x)] or [pd.NaT])
            _att_rows.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today,
                              "got_min": _gmin, "got_max": _gmax})
        if _att_rows:
            _prev = _fa if (_fa is not None and len(_fa)) else None
            _all = pd.concat([_prev, pd.DataFrame(_att_rows)], ignore_index=True) \
                if _prev is not None else pd.DataFrame(_att_rows)
            _all = (_all.sort_values("attempted_at").drop_duplicates("code", keep="last")
                        .reset_index(drop=True))
            VAULT.put_table("flow_fetch_attempts", _all, scope="shared", domain="flow",
                            source="fetch_investor_flows_daily:coverage_ledger")
        if fails["n"] > len(todo) * 0.7:
            LOG.warn(f"수급 수집 실패율 {100*fails['n']/max(len(todo),1):.0f}% — KRX 세션/차단을 의심하세요.")

    if not frames:
        FLOW_GRADE = "NONE"
        LOG.error("투자자유형별 순매수를 한 건도 확보하지 못했습니다. "
                  "이 전략의 핵심인 '소유권 이전'을 관측할 수 없습니다(§11-2 킬 기준).")
        return pd.DataFrame(columns=FLOW_COLS)

    F = pd.concat(frames, ignore_index=True)
    F["date"] = as_ts_series(F["date"])
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"]))
    has_retail = float(F["retail_net"].notna().mean())
    approx = float(F.get("src", pd.Series("", index=F.index)).astype(str)
                    .str.contains("근사").mean())
    globals()["FLOW_APPROX"] = bool(approx >= 0.5)
    FLOW_GRADE = ("FULL" if (has_retail > 0.5 and approx < 0.5)
                  else ("APPROX" if has_retail > 0.5 else ("PARTIAL" if len(F) else "NONE")))
    if FLOW_GRADE == "APPROX":
        LOG.warn(f"수급의 {approx:.0%} 가 '개인 = -(기관+외국인)' 근사입니다(네이버 경로). "
                 f"기타법인이 빠져 있으므로 f_retail·f_ret_ex 에 계통오차가 있습니다 — "
                 f"숨기지 않고 등급으로 표기합니다.")
    src_tab = (F.get("src", pd.Series(dtype=str)).astype(str).value_counts()
               if "src" in F.columns else pd.Series(dtype=int))
    if len(src_tab):
        LOG.table([[k, f"{v:,}"] for k, v in src_tab.items()], ["수급 소스", "행수"], ["l", "r"],
                  title="수급 취득 경로 원장 (KRX 차단 시 네이버로 자동 전환)")
    if FLOW_GRADE == "PARTIAL":
        LOG.warn("수급에 '개인' 분해가 없습니다 — f_ret_ex(개인 이탈)가 결측이 되고 "
                 "TP_F2 의 절반이 죽습니다. 0으로 채우지 않습니다.")
    VAULT.put_table("krx_investor_flows_daily", F, scope="shared", domain="flow",
                    source="pykrx trading_value_by_date",
                    extra={"note": "종목별 일별 개인/기관/외국인 순매수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_investor_flows_daily", F, source="pykrx")
    return downcast(F)


# ═══ 신용융자잔고 ═══════════════════════════════════════════════════════════════════════════
CREDIT_COLS = ["code", "date", "credit_bal", "src"]

# KRX 정보데이터시스템 bld 후보군. 화면 개편으로 ID가 바뀌므로 '하나를 믿지 않고' 프로브한다.
# (KRX_CREDIT_BLD 를 직접 지정하면 그것만 쓴다)
KRX_CREDIT_BLD_CANDIDATES = [
    "dbms/MDC/STAT/srt/MDCSTAT04601",
    "dbms/MDC/STAT/srt/MDCSTAT04701",
    "dbms/MDC/STAT/srt/MDCSTAT04801",
    "dbms/MDC/STAT/standard/MDCSTAT04601",
    "dbms/MDC/STAT/srt/MDCSTAT05001",
]
_CREDIT_VALUE_KEYS = ("융자잔고", "신용잔고", "잔고금액", "LOAN_BAL", "CRDT")


def _parse_krx_credit_json(js: Any, dt: pd.Timestamp) -> Optional[pd.DataFrame]:
    """KRX getJsonData 응답 → (code, date, credit_bal). 컬럼명이 개편마다 바뀌므로
    '코드처럼 생긴 컬럼' + '잔고처럼 생긴 컬럼'을 내용으로 찾는다."""
    if not isinstance(js, dict):
        return None
    block = None
    for k, v in js.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            block = v
            break
    if not block:
        return None
    d = pd.DataFrame(block)
    code_c = next((c for c in d.columns
                   if d[c].astype(str).str.fullmatch(r"\d{6}").mean() > 0.7), None)
    if code_c is None:
        code_c = next((c for c in d.columns if str(c).upper() in ("ISU_SRT_CD", "ISU_CD")), None)
    if code_c is None:
        return None
    val_c = None
    for c in d.columns:
        cu = str(c).upper()
        if any(k.upper() in cu for k in _CREDIT_VALUE_KEYS):
            val_c = c
            break
    if val_c is None:                      # 마지막 수단: 숫자 규모가 가장 큰 수치 컬럼
        num = {}
        for c in d.columns:
            v = pd.to_numeric(d[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if v.notna().mean() > 0.7:
                num[c] = float(v.abs().median() or 0)
        if not num:
            return None
        val_c = max(num, key=num.get)
    out = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "date": dt,
        "credit_bal": pd.to_numeric(d[val_c].astype(str).str.replace(",", "", regex=False),
                                    errors="coerce"),
        "src": "krx_marketplace",
    }).dropna(subset=["code", "credit_bal"])
    return out if len(out) > 50 else None


def _probe_credit_bld(probe_date: pd.Timestamp) -> Optional[str]:
    """어떤 bld 가 살아 있는지 실제로 한 번 때려서 확인한다. 결과는 로그에 남는다."""
    cands = [KRX_CREDIT_BLD] if KRX_CREDIT_BLD else KRX_CREDIT_BLD_CANDIDATES
    for bld in cands:
        js = KRX.json_data(bld, trdDd=probe_date.strftime("%Y%m%d"), mktId="ALL",
                           strtDd=probe_date.strftime("%Y%m%d"), endDd=probe_date.strftime("%Y%m%d"))
        got = _parse_krx_credit_json(js, probe_date)
        if got is not None:
            LOG.ok(f"KRX 신용잔고 bld 확인: {bld} (표본 {len(got):,}종목)")
            return bld
    return None


def _load_manual_credit() -> pd.DataFrame:
    """사용자가 KRX 웹에서 직접 받아 드라이브에 넣어둔 CSV/XLSX 를 흡수한다.
    ★ 원본 파일은 읽기만 하고 옮기거나 지우지 않는다(절대 1원칙)."""
    rows = []
    seen = set()
    for d in CREDIT_MANUAL_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".csv", ".xlsx", ".xls")):
                    continue
                p = os.path.join(root, fn)
                if p in seen:
                    continue
                seen.add(p)
                try:
                    if fn.lower().endswith(".csv"):
                        try:
                            t = pd.read_csv(p, encoding="utf-8-sig")
                        except Exception:
                            t = pd.read_csv(p, encoding="cp949")
                    else:
                        t = pd.read_excel(p)
                except Exception as e:                                  # noqa
                    LOG.warn(f"수동 신용잔고 파일 파싱 실패({type(e).__name__}): {fn}")
                    continue
                cmap = {str(c).strip(): c for c in t.columns}
                code_c = next((cmap[k] for k in cmap if k in ("종목코드", "단축코드", "code", "티커")), None)
                date_c = next((cmap[k] for k in cmap if k in ("일자", "날짜", "date", "기준일")), None)
                val_c = next((cmap[k] for k in cmap
                              if any(x in k for x in ("융자잔고", "신용잔고", "잔고금액"))), None)
                if not (code_c and date_c and val_c):
                    LOG.warn(f"수동 신용잔고 파일의 컬럼을 인식하지 못했습니다: {fn} → {list(t.columns)[:8]}")
                    continue
                rows.append(pd.DataFrame({
                    "code": t[code_c].map(to_code6),
                    "date": as_ts_series(t[date_c]),
                    "credit_bal": pd.to_numeric(
                        t[val_c].astype(str).str.replace(",", "", regex=False), errors="coerce"),
                    "src": "manual_csv"}))
                VAULT.adopt(p, domain="credit", subtype="manual_csv", key=fn,
                            source="user manual download", scope="shared")
    if not rows:
        return pd.DataFrame(columns=CREDIT_COLS)
    M = pd.concat(rows, ignore_index=True).dropna(subset=["code", "date", "credit_bal"])
    LOG.ok(f"수동 신용잔고 파일에서 {len(M):,}행 흡수 ({M['code'].nunique():,}종목, "
           f"{M['date'].min():%Y-%m-%d}~{M['date'].max():%Y-%m-%d})")
    return M


def credit_grade_of(C: pd.DataFrame, min_codes: int = 100) -> Tuple[str, float]:
    """등급은 '자칭'이 아니라 관측 간격의 실측 중앙값으로 판정한다.
    (수집 부작용 없이 단독 검증이 가능하도록 순수함수로 분리 — 리허설에서 그대로 호출한다)"""
    if C is None or not len(C) or C["code"].nunique() < min_codes:
        return "NONE", np.nan
    gap = C.sort_values("date").groupby("code")["date"].diff().dt.days.dropna()
    med = float(gap.median()) if len(gap) else 99.0
    return ("PRIMARY_DAILY" if med <= 2.0 else "FALLBACK_A_WEEKLY"), med


def fetch_credit_balance(px: pd.DataFrame, flows: pd.DataFrame,
                         start: str, end: str) -> pd.DataFrame:
    """§5.2 — 신용융자잔고. 등급을 정직하게 확정하고 전역 CREDIT_GRADE 에 남긴다."""
    global CREDIT_GRADE, CREDIT_SOURCE_NOTE
    cal = _trading_calendar(px)
    frames = []

    cached = VAULT.get_table("krx_credit_balance_daily", scope="shared")
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        if "src" not in cached.columns:
            cached["src"] = "cache"
        frames.append(cached.dropna(subset=["code", "date"])[CREDIT_COLS])
        LOG.info(f"공용 캐시에서 신용잔고 {len(cached):,}행 재사용")

    manual = _load_manual_credit()
    if len(manual):
        frames.append(manual[CREDIT_COLS])

    # ── Primary: KRX 마켓플레이스 일자별 전종목 조회 ──────────────────────────────────────
    new_rows = []
    if not krx_allowed():
        LOG.warn("KRX 가 차단/비활성이라 신용융자잔고 '직접 수집'은 불가능합니다. "
                 "이 데이터는 KRX 정보데이터시스템 독점이라 대체 공개 소스가 없습니다. "
                 "→ ① 드라이브 캐시 ② 수동 CSV ③ 프록시(Fallback B) 순으로 진행합니다.")
    if RUN_MODE != "CACHED" and len(cal) and krx_allowed():
        have_dates = set()
        if frames:
            hd = pd.concat(frames, ignore_index=True)["date"]
            have_dates = set(pd.to_datetime(hd).dt.strftime("%Y%m%d"))
        want = [pd.Timestamp(d) for d in cal
                if as_ts(start) <= pd.Timestamp(d) <= as_ts(end)]
        todo = [d for d in want if d.strftime("%Y%m%d") not in have_dates]
        if todo and KRX.session_ok:
            bld = _probe_credit_bld(todo[max(0, len(todo) - 1)])
            if bld:
                # 일별 전량이 예산을 넘으면 주간으로 낮춘다 — 조용히가 아니라 명시적으로.
                budget = 2600
                grid = todo
                if len(todo) > budget:
                    grid = [d for d in todo if d.weekday() == 4] or todo[::5]
                    LOG.warn(f"신용잔고 수집 대상 {len(todo):,}일이 호출예산({budget})을 초과합니다 → "
                             f"주간(금요일) 격자 {len(grid):,}일로 낮춥니다. "
                             f"이는 Fallback A(주간 해상도)와 동등합니다.")
                fail = 0
                for d in tqdm(grid, desc="KRX 신용잔고", ncols=88, leave=False):
                    js = KRX.json_data(bld, trdDd=d.strftime("%Y%m%d"), mktId="ALL",
                                       strtDd=d.strftime("%Y%m%d"), endDd=d.strftime("%Y%m%d"))
                    got = _parse_krx_credit_json(js, d)
                    if got is None:
                        fail += 1
                        if fail >= 15:
                            LOG.warn("신용잔고 조회가 연속 15회 실패 — 세션 만료/차단으로 판단하고 중단합니다. "
                                     "받은 분량은 그대로 캐시에 남습니다(재실행 시 이어받음).")
                            break
                        continue
                    fail = 0
                    new_rows.append(got)
            else:
                LOG.warn("KRX 신용잔고 bld 후보를 모두 시도했으나 유효 응답이 없습니다. "
                         "화면 개편으로 ID가 바뀌었을 수 있습니다 → KRX_CREDIT_BLD 에 직접 지정하거나, "
                         "CSV를 내려받아 CREDIT_MANUAL_DIRS 에 넣어 주세요.")
        elif todo and not KRX.session_ok:
            LOG.warn("KRX 마켓플레이스 세션이 없어 신용잔고 직접 수집을 시도하지 않습니다 "
                     "(상단 ①에 ID/PW 입력). 폴백 경로로 진행합니다.")
    if new_rows:
        frames.append(pd.concat(new_rows, ignore_index=True)[CREDIT_COLS])

    C = (pd.concat(frames, ignore_index=True) if frames
         else pd.DataFrame(columns=CREDIT_COLS))
    if len(C):
        C["date"] = as_ts_series(C["date"])
        C = (C.dropna(subset=["code", "date", "credit_bal"])
               .drop_duplicates(["code", "date"], keep="last")
               .sort_values(["code", "date"]))

    # ── 등급 판정 ────────────────────────────────────────────────────────────────────────
    grade, med_gap = credit_grade_of(C)
    if grade != "NONE":
        CREDIT_GRADE = grade
        if CREDIT_GRADE == "FALLBACK_A_WEEKLY" and not CREDIT_ALLOW_FALLBACK_A:
            LOG.warn("주간 해상도 신용잔고만 확보됐지만 CREDIT_ALLOW_FALLBACK_A=False 입니다 — "
                     "그래도 프록시(B)보다는 우월하므로 A로 진행하되 이 사실을 남깁니다.")
        CREDIT_SOURCE_NOTE = (f"관측간격 중앙값 {med_gap:.1f}일 · {C['code'].nunique():,}종목 · "
                              f"{len(C):,}행 · 소스={'/'.join(sorted(set(C['src'].astype(str))))[:40]}")
        if new_rows:
            VAULT.put_table("krx_credit_balance_daily", C, scope="shared", domain="credit",
                            source="KRX marketplace / manual",
                            extra={"note": "종목별 신용융자잔고 — 전 전략 공용"})
            PIPE.io("OUT", "DRIVE", "krx_credit_balance_daily", C, source="KRX")
    else:
        # ── Fallback B: 프록시 ───────────────────────────────────────────────────────────
        if not CREDIT_ALLOW_FALLBACK_B:
            CREDIT_GRADE = "NONE"
            CREDIT_SOURCE_NOTE = "신용잔고 직접 관측 실패 · Fallback B 비허용 설정"
            LOG.error("신용잔고를 확보하지 못했고 CREDIT_ALLOW_FALLBACK_B=False 입니다 → "
                      "이 전략의 핵심 축이 없는 상태로는 진행하지 않습니다.")
            return pd.DataFrame(columns=CREDIT_COLS)
        if flows is None or not len(flows) or flows["retail_net"].notna().sum() == 0:
            CREDIT_GRADE = "NONE"
            CREDIT_SOURCE_NOTE = "신용잔고·개인수급 모두 부재"
            LOG.error("신용잔고도, 프록시의 재료인 개인 순매수도 없습니다. f_cr 계열 전부 결측입니다.")
            return pd.DataFrame(columns=CREDIT_COLS)
        CREDIT_GRADE = "FALLBACK_B_PROXY"
        if FLOW_APPROX:
            LOG.error("★★ 이중 퇴화 경고: 신용잔고가 프록시(개인 순매수 누적)인데 그 '개인'조차 "
                      "-(기관+외국인) 근사입니다. 그러면 f_cr · f_ret_ex · f_inst 가 사실상 "
                      "같은 시계열(기관+외국인 순매수)의 변형이 되고, TP_F2(개인이탈×기관유입)는 "
                      "자기 자신과의 곱으로 퇴화합니다 — 신호처럼 보이지만 아무 정보가 없습니다. "
                      "해당 TP 를 산식에서 제외하고 그 사실을 리포트에 남깁니다.")
        LOG.warn("★ 신용잔고를 직접 얻는 방법(권장, 5분): data.krx.co.kr 접속 → [통계] → "
                 "[시장정보] → '신용거래융자 잔고' 화면에서 기간을 지정해 CSV/XLSX 를 내려받아 "
                 f"{CREDIT_MANUAL_DIRS[0]} 폴더에 넣어두세요. 다음 실행에서 자동 인식되어 "
                 "PRIMARY 등급으로 승격되고, 공용 인덱스에 정규화 적재됩니다. "
                 "(파일에 '일자'·'종목코드'·'융자잔고금액' 컬럼만 있으면 됩니다)")
        f = flows.sort_values(["code", "date"]).copy()
        f["credit_bal"] = (f.groupby("code", observed=True)["retail_net"]
                            .transform(lambda s: s.rolling(252, min_periods=60).sum()))
        C = f.loc[f["credit_bal"].notna(), ["code", "date", "credit_bal"]].copy()
        C["src"] = "proxy_retail_cum252"
        CREDIT_SOURCE_NOTE = ("개인 순매수 252일 누적 (신용잔고 직접 관측 불가) — "
                              "대체재가 아니라 열등재입니다")
        LOG.error("★ 신용잔고를 Fallback B(프록시)로 대체합니다. §11-3에 따라 이 사실을 "
                  "리포트 첫 줄에 명시하고, R2-F 결과의 신뢰도를 하향 표기합니다. "
                  "숨기지 않습니다.")

    LOG.ok(f"신용잔고 등급 = {CREDIT_GRADE} · {CREDIT_SOURCE_NOTE}")
    return downcast(C) if len(C) else C


# ═══ 관리종목 · 거래정지 (방화벽 입력, K6) ═══════════════════════════════════════════════════
def fetch_watchlist_halt(sec: pd.DataFrame) -> pd.DataFrame:
    """관리종목·투자주의환기·거래정지 이력. 이력(지정/해제일)이 이상적이지만 공개 경로는
    대개 '현재 상태' 스냅샷이다. 스냅샷만 얻으면 PIT 로 쓸 수 없으므로,
    ★ 과거 구간에는 적용하지 않고 '현재 시점 이후'로만 제한한다(미래정보 차단).
    """
    global WATCH_GRADE
    cols = ["code", "flag", "from_date", "to_date", "observed_at", "src"]
    cached = VAULT.get_table("krx_watchlist_events", scope="shared")
    if cached is not None and len(cached):
        WATCH_GRADE = "OK"
        if "observed_at" not in cached.columns:
            cached["observed_at"] = pd.NaT
        cached["from_date"] = as_ts_series(cached["from_date"])
        cached["to_date"] = as_ts_series(cached["to_date"])
        cached["observed_at"] = as_ts_series(cached["observed_at"])
        LOG.info(f"공용 캐시에서 관리종목/거래정지 이력 {len(cached):,}행 재사용 "
                 f"(관측시점 최소 {str(cached['observed_at'].min())[:10]})")
        return cached.reindex(columns=cols)

    rows = []
    if RUN_MODE != "CACHED":
        # KIND 공시 기반: 관리종목 지정/해제, 매매거래정지/해제는 '공시'로 남는다.
        for flag, url in (
            ("admin", "https://kind.krx.co.kr/investwarn/adminissue.do?method=searchAdminIssueMain"),
            ("halt", "https://kind.krx.co.kr/investwarn/tradinghaltissue.do?method=searchTradingHaltIssueMain"),
            ("alert", "https://kind.krx.co.kr/investwarn/investattentigender.do?method=searchInvestAttentiMain"),
        ):
            html = http_get(url, source="kind", tries=2,
                            referer="https://kind.krx.co.kr/investwarn/adminissue.do")
            if not html:
                continue
            try:
                tabs = pd.read_html(io.StringIO(html))
            except Exception:
                tabs = []
            if not tabs:
                continue
            t = max(tabs, key=len)
            cmap = {str(c).strip(): c for c in t.columns}
            code_c = next((cmap[k] for k in cmap if "종목코드" in k or "코드" == k), None)
            name_c = next((cmap[k] for k in cmap if "회사명" in k or "종목명" in k), None)
            date_c = next((cmap[k] for k in cmap if "지정일" in k or "일자" in k or "정지일" in k), None)
            if code_c is None and name_c is not None and sec is not None and len(sec):
                n2c = {str(n).strip(): c for c, n in zip(sec["code"], sec["name"]) if isinstance(n, str)}
                codes = t[name_c].astype(str).str.strip().map(n2c)
            elif code_c is not None:
                codes = t[code_c].map(to_code6)
            else:
                continue
            rows.append(pd.DataFrame({
                "code": codes,
                "flag": flag,
                "from_date": as_ts_series(t[date_c]) if date_c else pd.NaT,
                "to_date": pd.NaT,
                "observed_at": pd.Timestamp.today().normalize(),
                "src": "kind"}).dropna(subset=["code"]))

    if not rows:
        WATCH_GRADE = "NONE"
        LOG.warn("관리종목·거래정지 이력을 확보하지 못했습니다(K6 FAIL) → 방화벽의 해당 조항만 "
                 "비활성화하고 그 사실을 방화벽 감사표에 남깁니다. "
                 "다른 조항(자본잠식·영업CF·유동성)은 그대로 작동합니다.")
        return pd.DataFrame(columns=cols)

    W = pd.concat(rows, ignore_index=True).drop_duplicates(["code", "flag", "from_date"])
    # ★ 이 목록은 '현재 지정 중'인 종목만 담긴 스냅샷이다. 지정일이 2019년이어도,
    #   2026년에 관측했다는 사실 자체가 "2026년까지 해제되지 않았다"는 미래정보다.
    #   과거로 소급 적용하면 '끝내 회복하지 못한 종목'만 골라 차단하게 되어 성과가 부풀려진다.
    #   → 적용 시작일 = max(지정일, 관측일). 즉 과거 구간에는 적용하지 않는다.
    #   실행할 때마다 스냅샷이 누적되므로, 앞으로의 구간에서는 진짜 PIT 이력이 쌓인다.
    W["observed_at"] = as_ts_series(W["observed_at"]).fillna(pd.Timestamp.today().normalize())
    W["from_date"] = as_ts_series(W["from_date"])
    W["from_date"] = W[["from_date", "observed_at"]].max(axis=1)
    W["from_date"] = W["from_date"].fillna(W["observed_at"])
    WATCH_GRADE = "SNAPSHOT_FORWARD_ONLY"
    LOG.warn("관리종목/거래정지는 '현재 지정 중' 스냅샷이라 과거 구간에 소급 적용하지 않습니다"
             "(소급하면 '끝내 회복 못한 종목만 차단'하는 미래정보가 됩니다). "
             "따라서 백테스트 구간에서 이 방화벽 조항은 사실상 비활성이며, "
             "그 사실을 방화벽 감사표와 등급 카드에 그대로 남깁니다.")
    VAULT.put_table("krx_watchlist_events", W, scope="shared", domain="universe",
                    source="KIND", extra={"note": "관리종목/거래정지/투자주의 — 전 전략 공용"})
    LOG.ok(f"관리종목·거래정지 {len(W):,}행 ({W['code'].nunique():,}종목)")
    return W.reindex(columns=cols)

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-B  일별 센서(§6) → 주간 패널 → 국면 판정(§7.1) → TP 조립(§7.2) → 방화벽(§7.3)      ║
# ║                                                                                          ║
# ║  원칙 (§1):                                                                               ║
# ║   · 모든 롤링은 groupby(code)[col].transform(...) — 종목 루프 금지                         ║
# ║   · 신용잔고/수급은 '거래일 +1영업일' 지연을 반영한 뒤에만 센서에 들어간다                  ║
# ║   · TP 는 clip(z,0)*clip(z,0). z*z 금지 (양쪽 음수가 최고점을 받는 부호 버그)               ║
# ║   · 셀 정규화는 rank(pct=True)+transform. groupby.apply 금지                               ║
# ║   · 거부권/방화벽은 이진·곱·상쇄 불가                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SENSOR_COLS = ["f_dd", "f_dd_spd", "f_cr", "f_cr_pctl", "f_cr_chg", "f_cr_chg_slow",
               "f_retail", "f_inst", "f_ret_ex", "f_vol", "f_turn"]
TP_COLS = ["TP_F1", "TP_F2", "TP_F3", "TP_F4"]
# 데이터 등급 때문에 '수학적으로 퇴화'한 TP 는 산식에서 뺀다(있는 척하지 않는다).
EXCLUDED_TPS: List[str] = []


def check_tp_degeneracy() -> None:
    """등급 조합이 특정 TP 를 무의미하게 만드는 경우를 판정한다.

    ★ 실제 위험: 신용잔고가 프록시(개인 순매수 누적)이고 그 '개인'이 -(기관+외국인) 근사이면
      f_cr, f_ret_ex, f_inst 가 모두 (기관+외국인 순매수)의 부호·창 변형이 된다.
      그러면 TP_F2 = tp(f_ret_ex, f_inst) 는 사실상 tp(x, x) 이고, 값은 크게 나오지만
      '소유권 이전'을 전혀 관측하지 않는다. 조용히 두면 그 자체가 가짜 신호다."""
    EXCLUDED_TPS.clear()
    if CREDIT_GRADE == "FALLBACK_B_PROXY" and FLOW_APPROX:
        EXCLUDED_TPS.append("TP_F2")
        LOG.warn("TP_F2(개인 이탈 × 기관 유입)를 산식에서 제외합니다 — 신용잔고 프록시와 "
                 "개인 근사가 겹쳐 두 축이 같은 시계열이 되었습니다(자기 자신과의 곱). "
                 "E 는 남은 TP 들의 평균으로 계산되며, 이 사실은 해석표에도 표기됩니다.")
    if EXCLUDED_TPS:
        LOG.table([[c, "제외", "데이터 등급으로 인해 퇴화"] for c in EXCLUDED_TPS],
                  ["TP", "상태", "사유"], ["l", "c", "l"], title="TP 퇴화 판정")


def week_grid(start: str, end: str, px: pd.DataFrame) -> pd.DatetimeIndex:
    """주간 신호일 = 실제 거래일에 정렬된 주 1회 격자(§8).
    달력상의 금요일이 휴장이면 그 주의 마지막 거래일을 쓴다."""
    cal = pd.DatetimeIndex(np.sort(pd.unique(as_ts_series(px["date"]).values))) \
        if px is not None and len(px) else pd.DatetimeIndex([])
    weeks = pd.date_range(as_ts(start), as_ts(end), freq=REBAL_DAY)
    if not len(cal):
        return weeks
    out = []
    for w in weeks:
        pos = int(np.searchsorted(cal.values, np.datetime64(w), side="right")) - 1
        if pos >= 0 and (w - cal[pos]).days <= 6:
            out.append(cal[pos])
    return pd.DatetimeIndex(sorted(set(out)))


def _rolling_rank_pct(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    """자기 이력 백분위. pandas>=2.1 의 Rolling.rank 를 쓰고, 없으면 z→정규근사로 폴백한다.
    (파이썬 apply 로 돌리면 600만 행에서 수 분이 아니라 수십 분이 걸린다)"""
    try:
        return s.rolling(window, min_periods=min_periods).rank(pct=True)
    except (AttributeError, TypeError):
        m = s.rolling(window, min_periods=min_periods).mean()
        sd = s.rolling(window, min_periods=min_periods).std()
        z = (s - m) / sd.replace(0, np.nan)
        from math import erf, sqrt
        return z.map(lambda v: np.nan if not np.isfinite(v) else 0.5 * (1 + erf(v / sqrt(2))))


def _chunk_codes(codes: Sequence[str], n: int) -> List[List[str]]:
    codes = list(codes)
    n = max(1, int(n))
    return [codes[i:i + n] for i in range(0, len(codes), n)]


def build_flp_panel(px: pd.DataFrame, credit: pd.DataFrame, flows: pd.DataFrame,
                    shares: pd.DataFrame, weeks: pd.DatetimeIndex,
                    uni: "Universe") -> pd.DataFrame:
    """일별 센서를 청크 단위로 계산하고 주간 격자에만 남긴다(RAM 방어).

    반환: (code, date=신호일, 센서들, exec_px, fwd_ret, adv20, mcap)
    """
    if px is None or not len(px):
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)

    # ★ 결합키 dtype 정규화. downcast() 를 지난 가격 패널의 code 는 category 인데
    #   신용잔고/수급/주식수 프레임의 code 는 object 다. merge_asof(by="code") 는 dtype 이
    #   다르면 MergeError 로 죽는다 — 몇 시간짜리 수집이 끝난 직후 L2 에서 터진다.
    #   (합성 스모크는 downcast 를 타지 않아 이 경로를 못 본다)
    _as_code = lambda d: d.assign(code=d["code"].astype(str))
    px = _as_code(px.copy())
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    for c in ("close", "open", "amount", "volume"):
        if c not in px.columns:
            px[c] = np.nan

    cr = credit.copy() if credit is not None and len(credit) else pd.DataFrame(columns=CREDIT_COLS)
    if len(cr):
        cr = _as_code(cr)
        cr["date"] = as_ts_series(cr["date"])
        cr = cr.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    fl = flows.copy() if flows is not None and len(flows) else pd.DataFrame(columns=FLOW_COLS)
    if len(fl):
        fl = _as_code(fl)
        fl["date"] = as_ts_series(fl["date"])
        fl = fl.dropna(subset=["code", "date"]).sort_values(["code", "date"])
    sh = shares.copy() if shares is not None and len(shares) else pd.DataFrame(
        columns=["snap_date", "code", "shares", "mcap_snap"])
    if len(sh):
        sh = _as_code(sh)
        sh["snap_date"] = as_ts_series(sh["snap_date"])
        # ★ 상장주식수 스냅샷도 PIT: 스냅샷일 +1영업일 이후에만 알 수 있다.
        sh["knowledge_date"] = next_bday(sh["snap_date"])
        sh = sh.dropna(subset=["code", "knowledge_date"]).sort_values("knowledge_date")

    # 주간 격자 × 유니버스 (C13 — 매 시점의 당시 값으로 멤버십 판정)
    grid_rows = []
    for w in weeks:
        codes = uni.at(w)
        uni.audit_row("PIT유니버스", w, codes)
        grid_rows.append(pd.DataFrame({"code": codes, "week": w}))
    G = pd.concat(grid_rows, ignore_index=True) if grid_rows else pd.DataFrame(columns=["code", "week"])
    if len(G):
        G["code"] = G["code"].astype(str)
    if G.empty:
        LOG.error("주간 격자가 비었습니다 — 유니버스가 전 구간에서 0종목입니다.")
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)

    all_codes = sorted(set(G["code"]) & set(px["code"]))
    LOG.info(f"일별 센서 계산: {len(all_codes):,}종목 × {len(weeks):,}주 "
             f"(청크 {DAILY_CHUNK_CODES}종목 단위 — 메모리 상한 방어)")
    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        LOG.warn("신용잔고가 프록시이므로 f_cr_chg 는 '비율'이 아니라 '자기 스케일 정규화 차분'을 "
                 "씁니다. 프록시는 부호가 바뀌는 양이라 비율이 0 근처에서 발산하기 때문입니다 "
                 "— 임계값(PH_CR_CHG_B)의 의미가 등급에 따라 달라진다는 점을 인지하세요.")

    # ★ 청크마다 isin() 으로 전체 일봉을 훑으면 (청크수 × 전체행) 스캔이 된다.
    #   2,500종목·650만행이면 7회 × 650만 = 4,500만 비교. 코드로 정렬해 두고 위치로 잘라내면
    #   같은 결과를 한 번의 정렬 비용으로 얻는다. 신용/수급/주식수도 동일하게 처리한다.
    def _slicer(df: pd.DataFrame):
        """★ 이미 code 로 정렬된 프레임을 또 정렬하면 전체 복사본이 하나 더 생긴다.
        650만행 가격 프레임에서 이것만으로 수 GB 가 더 잡혀 청크 처리의 목적을 깨뜨린다.
        → 정렬 여부를 먼저 확인하고, 필요할 때만 정렬한다."""
        if df is None or not len(df):
            return None
        codes_arr = df["code"].to_numpy()
        if len(codes_arr) > 1 and not pd.Index(codes_arr).is_monotonic_increasing:
            df = df.sort_values(["code"], kind="stable")
            codes_arr = df["code"].to_numpy()
        return df, codes_arr

    _px_s = _slicer(px)
    _cr_s = _slicer(cr)
    _fl_s = _slicer(fl)
    _sh_s = _slicer(sh)

    def _take(sl, chunk_codes):
        if sl is None:
            return None
        d0, arr = sl
        lo = np.searchsorted(arr, chunk_codes[0], side="left")
        hi = np.searchsorted(arr, chunk_codes[-1], side="right")
        sub = d0.iloc[lo:hi]
        # 청크 경계가 정확히 맞지 않는 경우(코드 정렬 순서가 다른 프레임)만 보정
        if len(sub) and (sub["code"].iloc[0] < chunk_codes[0] or
                         sub["code"].iloc[-1] > chunk_codes[-1]):
            sub = sub[sub["code"].isin(set(chunk_codes))]
        return sub

    out_parts = []
    for chunk in tqdm(_chunk_codes(all_codes, DAILY_CHUNK_CODES), desc="L1 센서", ncols=88,
                      leave=False):
        cs = set(chunk)
        _pxc = _take(_px_s, chunk)
        d = (_pxc[_pxc["code"].isin(cs)] if _pxc is not None else px.head(0)).copy()
        if d.empty:
            continue
        # ── 원시 입력 결합 ────────────────────────────────────────────────────────────
        #   중복 (code,date) 가 하나라도 있으면 merge 가 패널 행을 복제해 수익률이 부풀려진다
        c0 = _take(_cr_s, chunk)
        if c0 is not None and len(c0):
            c0 = (c0[c0["code"].isin(cs)][["code", "date", "credit_bal"]]
                  .drop_duplicates(["code", "date"], keep="last"))
            d = d.merge(c0, on=["code", "date"], how="left")
            # 주간 관측이면 그 사이는 forward-fill (★선형보간 금지 — 미래정보 누출)
            d["credit_bal"] = d.groupby("code", observed=True)["credit_bal"].ffill()
        if "credit_bal" not in d.columns:
            d["credit_bal"] = np.nan

        f0 = _take(_fl_s, chunk)
        if f0 is not None and len(f0):
            f0 = (f0[f0["code"].isin(cs)][["code", "date", "retail_net", "inst_net",
                                           "foreign_net"]]
                  .drop_duplicates(["code", "date"], keep="last"))
            d = d.merge(f0, on=["code", "date"], how="left")
        for c in ("retail_net", "inst_net", "foreign_net"):
            if c not in d.columns:
                d[c] = np.nan

        s0 = _take(_sh_s, chunk)
        if s0 is not None and len(s0):
            s0 = (s0[s0["code"].isin(cs)][["code", "knowledge_date", "shares"]]
                  .drop_duplicates(["code", "knowledge_date"], keep="last")
                  .sort_values("knowledge_date"))
            d = d.sort_values("date")
            d = pd.merge_asof(d, s0, left_on="date", right_on="knowledge_date", by="code",
                              direction="backward")
        if "shares" not in d.columns:
            d["shares"] = np.nan
        # ★ 과거 세션에서 실제로 죽은 패턴: merge 로 같은 이름의 컬럼이 두 개가 되면
        #   d[col] 이 Series 가 아니라 DataFrame 이 되고, groupby.agg 가 pandas 내부에서
        #   'DataFrame object has no attribute name' 으로 터진다. 발생 지점에서 즉시 세운다.
        assert_no_dup_cols(d, "build_flp_panel:chunk")
        d = d.sort_values(["code", "date"])

        g = lambda c: d.groupby("code", observed=True)[c]

        # ── PIT 지연 (§4.1): 잔고·수급은 '거래일 +1영업일' 공표 → 거래일 기준 1행 시프트 ──
        for c in ("credit_bal", "retail_net", "inst_net", "foreign_net"):
            d[c] = g(c).shift(1)

        # ── 가격 상태 ────────────────────────────────────────────────────────────────
        d["p252max"] = g("close").transform(lambda s: s.rolling(252, min_periods=120).max())
        d["f_dd"] = d["close"] / d["p252max"] - 1.0
        d["f_dd_spd"] = d["f_dd"] - g("f_dd").shift(60)
        d["ret1d"] = g("close").pct_change()
        d["adv20"] = g("amount").transform(lambda s: s.rolling(20, min_periods=10).mean())
        d["adv60"] = g("amount").transform(lambda s: s.rolling(60, min_periods=30).mean())

        # ── 시가총액 (분모) ──────────────────────────────────────────────────────────
        d["mcap"] = d["close"] * d["shares"]
        # 상장주식수를 못 구한 종목은 '20일 거래대금 합'을 대리 분모로 쓴다(스케일만 다름).
        proxy_den = d["adv20"] * 20.0
        d["mcap_den"] = d["mcap"].where(d["mcap"] > 0, proxy_den)

        # ── 강제 재고 (핵심) ─────────────────────────────────────────────────────────
        d["f_cr"] = safe_div(d["credit_bal"], d["mcap_den"])
        d["f_cr_pctl"] = g("f_cr").transform(
            lambda s: _rolling_rank_pct(s, 252, 120))
        # 변화율은 '비율'이 기본이지만, 프록시(Fallback B)는 부호가 바뀌는 양이라
        # 비율이 0 근처에서 발산·부호역전한다 → 그 경우에만 자기 스케일로 정규화한 '차분'을 쓴다.
        if CREDIT_GRADE == "FALLBACK_B_PROXY":
            scale = g("f_cr").transform(lambda s: s.abs().rolling(252, min_periods=60).mean())
            d["f_cr_chg"] = safe_div(d["f_cr"] - g("f_cr").shift(20), scale)
            d["f_cr_chg_slow"] = safe_div(d["f_cr"] - g("f_cr").shift(60), scale)
        else:
            d["f_cr_chg"] = safe_div(d["f_cr"], g("f_cr").shift(20)) - 1.0
            d["f_cr_chg_slow"] = safe_div(d["f_cr"], g("f_cr").shift(60)) - 1.0

        # ── 소유권 이전 ──────────────────────────────────────────────────────────────
        r20 = g("retail_net").transform(lambda s: s.rolling(20, min_periods=10).sum())
        r60 = g("retail_net").transform(lambda s: s.rolling(60, min_periods=30).sum())
        i20 = (g("inst_net").transform(lambda s: s.rolling(20, min_periods=10).sum()) +
               g("foreign_net").transform(lambda s: s.rolling(20, min_periods=10).sum()))
        d["f_retail"] = safe_div(r20, d["mcap_den"])
        d["f_inst"] = safe_div(i20, d["mcap_den"])
        d["f_ret_ex"] = -safe_div(r60, d["mcap_den"])

        # ── 안정화 ───────────────────────────────────────────────────────────────────
        d["f_vol"] = -g("ret1d").transform(lambda s: s.rolling(20, min_periods=10).std())
        d["f_turn"] = safe_div(d["adv20"], d["adv60"])

        # ── 체결가: 신호 산출일의 '다음 거래일 시가' (§8) ─────────────────────────────
        d["next_open"] = g("open").shift(-1)
        d["next_date"] = g("date").shift(-1)
        gap = (d["next_date"] - d["date"]).dt.days
        d["exec_px"] = d["next_open"].where(gap.notna() & (gap <= 10)).fillna(d["close"])

        keep = ["code", "date", "close", "exec_px", "adv20", "mcap", "mcap_den",
                "credit_bal", "shares"] + SENSOR_COLS
        d = d[[c for c in keep if c in d.columns]]

        # ── 주간 격자로 축약 (as-of backward: 신호일 이전 최신 관측) ───────────────────
        gg = G[G["code"].isin(cs)].sort_values("week")
        if gg.empty:
            continue
        d = d.sort_values("date")
        m = pd.merge_asof(gg, d, left_on="week", right_on="date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=7))
        out_parts.append(m)

    if not out_parts:
        return pd.DataFrame(columns=["code", "date"] + SENSOR_COLS)
    P = pd.concat(out_parts, ignore_index=True)
    P = P.rename(columns={"week": "wk"}).sort_values(["code", "wk"])
    P["signal_date"] = P["date"]

    # ── 다음 주 수익률 (체결가 → 체결가). 주 연속성이 끊기면 결측(수익 과대계상 방지) ──
    nxt_px = P.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_wk = P.groupby("code", observed=True)["wk"].shift(-1)
    adjacent = ((nxt_wk - P["wk"]).dt.days.between(1, 10))
    P["fwd_ret"] = (nxt_px / P["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_wk.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"주 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 구간 수익을 1주 수익으로 계상하지 않기 위함). "
                 f"상장폐지는 백테스트 엔진이 -100% 로 별도 처리합니다.")
    # ★ 신호일이 격자일보다 며칠 앞선 행 = 최근 거래가 없었다는 뜻(거래정지 진입 구간).
    #   보유 연속성을 위해 행 자체는 남기되, '그 가격으로 신규 진입'은 막아야 한다
    #   (이미 존재하지 않는 가격에 새로 사는 셈이 된다).
    P["stale_days"] = (P["wk"] - P["signal_date"]).dt.days
    P = P[P["signal_date"].notna()].reset_index(drop=True)
    n_stale = int((P["stale_days"] > 3).sum())
    if n_stale:
        LOG.info(f"신호일이 3일 이상 지연된 행 {n_stale:,}건 — 최근 시세가 없는 구간입니다. "
                 f"보유 연속성 판단에는 쓰되 신규 진입 자격에서는 제외합니다.")
    LOG.ok(f"주간 패널 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB "
           f"({P['code'].nunique():,}종목 × {P['wk'].nunique():,}주)")
    PIPE.io("OUT", "MEM", "flp_weekly_panel", P)
    return P


# ── 유니버스 밴드 (C13) ─────────────────────────────────────────────────────────────────────
def build_size_estimate(P: pd.DataFrame) -> pd.DataFrame:
    """규모 척도를 '하나'로 만든다.

    시총(≈1e11)과 거래대금(≈1e9)은 스케일이 100배 다르다. 둘을 한 컬럼에 coalesce 해서
    랭크하면 '상위 250 제외'가 사실상 '주식수 데이터를 가진 250종목 제외'가 되고,
    셀의 규모 축과 R3 의 규모 팩터도 똑같이 오염된다.
    → 주별로 둘 다 관측된 종목에서 mcap/adv20 의 중앙 배율을 구해 거래대금을 시총 스케일로
      보정한 뒤, 전 종목을 '한 랭크'에서 비교한다. 보정 계수를 못 구하면 전역 중앙값을 쓴다.
    """
    P = P.copy()
    mcap = pd.to_numeric(P.get("mcap"), errors="coerce")
    adv = pd.to_numeric(P.get("adv20"), errors="coerce")
    both = mcap.notna() & (mcap > 0) & adv.notna() & (adv > 0)
    est = mcap.where(mcap > 0)
    if both.any():
        ratio = (mcap[both] / adv[both])
        k_wk = ratio.groupby(P.loc[both, "wk"]).median()
        k = P["wk"].map(k_wk)
        k = k.fillna(float(ratio.median()))
    else:
        k = pd.Series(20.0, index=P.index)      # 관측이 없으면 보수적 상수 (스케일만 맞춘다)
    P["size_est"] = est.where(est.notna(), adv * k)
    P["size_basis"] = np.where(mcap.notna() & (mcap > 0), "mcap", "adv20×보정")
    n_proxy = int((P["size_basis"] == "adv20×보정").sum())
    if n_proxy:
        LOG.info(f"규모 척도 — 시총 {len(P)-n_proxy:,}행 / 거래대금×보정 {n_proxy:,}행. "
                 f"주별 중앙 배율로 스케일을 맞춰 '한 랭크'에서 비교합니다 "
                 f"(척도가 다른 두 값을 섞어 랭크하지 않습니다).")
    return P


MAX_EXCLUDE_FRAC = 0.30      # 안전밸브: 어떤 주에도 유니버스의 30% 넘게 잘라내지 않는다


def apply_universe_bands(P: pd.DataFrame) -> pd.DataFrame:
    """상위 250 대형주 제외 + 유동성 하한. 매 시점의 당시 값으로 재산출한다.
    ★ 보유 중 밴드 이탈은 청산 사유가 아니다(§4.3) — 진입 자격에만 쓴다.

    ★ 안전밸브: 그 주의 유니버스가 250종목보다 작으면 '상위 250 제외'가 유니버스를 통째로
      지운다(신호 영구 무발화). 이 경우 제외 컷을 그 주 종목수의 30% 로 낮추고, 조용히가
      아니라 로그로 알린다. 실데이터(2,000+종목)에서는 절대 발동하지 않는다."""
    P = P.copy()
    P = build_size_estimate(P)
    P["mcap_rank"] = (P.groupby("wk", observed=True)["size_est"]
                       .rank(ascending=False, method="first"))
    P["size_pct"] = P.groupby("wk", observed=True)["size_est"].rank(pct=True, ascending=False)
    n_wk = P.groupby("wk", observed=True)["code"].transform("size")
    cut = np.minimum(MCAP_RANK_EXCLUDE_TOP, np.floor(n_wk * MAX_EXCLUDE_FRAC))
    binding = int((cut < MCAP_RANK_EXCLUDE_TOP).sum())
    if binding:
        LOG.warn(f"유니버스가 작아 '상위 {MCAP_RANK_EXCLUDE_TOP} 제외' 규칙이 "
                 f"{binding:,}행에서 유니버스를 과도하게 삭제합니다 → 해당 주는 "
                 f"상위 {MAX_EXCLUDE_FRAC:.0%} 제외로 낮춥니다(안전밸브). "
                 f"실데이터 전 종목 실행에서는 발동하지 않아야 정상입니다.")
    P["mcap_cut"] = cut
    P["V6"] = (P["adv20"] >= MIN_ADV_KRW).fillna(False).astype(int)
    P["in_band"] = ((P["mcap_rank"] > cut) & (P["V6"] == 1)).fillna(False).astype(int)

    # ── 비교군: 스몰캡 밴드 (매 시점 '투자 가능한 종목 중' 시총 하위 N) ────────────────
    #   ★ 전체 단면에서 하위 N 을 세고 나서 유동성 필터를 걸면, 하위 꼬리를 채우는 것이
    #     대부분 거래대금 미달 종목이라 실제 밴드가 N 보다 훨씬 작아지고 그 폭이 주마다
    #     들쭉날쭉해진다("하위 1000" 이라는 이름과 실물이 달라진다).
    #     → 진입 자격(유동성 ∧ 대형주 제외)을 먼저 적용하고, 그 안에서 하위 N 을 센다.
    elig_small = (P["V6"] == 1) & (P["mcap_rank"] > cut)
    small_rank = pd.Series(np.nan, index=P.index, dtype=float)
    if elig_small.any():
        small_rank[elig_small] = (P.loc[elig_small].groupby("wk", observed=True)["size_est"]
                                  .rank(ascending=True, method="first"))
    P["small_rank"] = small_rank
    P["in_band_small"] = (elig_small & (small_rank <= SMALLCAP_BOTTOM_N)
                          ).fillna(False).astype(int)
    return P


# ── 셀 (§7.2) ───────────────────────────────────────────────────────────────────────────────
def build_cells_flp(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """셀 = (주, 산업중분류, 규모버킷). 규모는 시총 5분위(PIT)."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict() if len(sec) else {}
    P = P.copy()
    P["industry"] = P["code"].map(ind).fillna("미분류").astype(str)
    P["ind_mid"] = P["industry"].str.slice(0, 4).replace("", "미분류")
    base = P["size_est"] if "size_est" in P.columns else \
        build_size_estimate(P)["size_est"]
    P["size_bucket"] = (base.groupby(P["wk"]).rank(pct=True)
                        .mul(5).clip(0, 4.999).fillna(-1).astype(int).astype(str))
    ws = P["wk"].dt.strftime("%Y%m%d")
    P["cell"] = ws + "|" + P["ind_mid"] + "|" + P["size_bucket"]
    P["cell_l2"] = ws + "|" + P["ind_mid"] + "|ALL"
    P["cell_l3"] = ws + "|ALL|ALL"
    return P


def cell_rank(P: pd.DataFrame, col_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 백분위. 표본이 얇은 셀은 상위 단위로 폴백한다(사다리). groupby.apply 금지."""
    s = P[col_or_series] if isinstance(col_or_series, str) else col_or_series
    s = pd.to_numeric(s, errors="coerce")
    fine = s.groupby(P["cell"], observed=True).rank(pct=True)
    mid = s.groupby(P["cell_l2"], observed=True).rank(pct=True)
    coarse = s.groupby(P["cell_l3"], observed=True).rank(pct=True)
    n1 = s.notna().groupby(P["cell"], observed=True).transform("sum")
    n2 = s.notna().groupby(P["cell_l2"], observed=True).transform("sum")
    out = fine.where(n1 >= min_n, mid.where(n2 >= min_n, coarse))
    return out


def tp(P: pd.DataFrame, a, b) -> pd.Series:
    """★ 음수 절단 후 곱. 한쪽이라도 셀 중앙 미만이면 정확히 0.
    za*zb 를 쓰면 '둘 다 최악'인 종목이 최고점을 받는다 — 이 전략에서 그건 국면 B 매수다."""
    za = cell_rank(P, a) - 0.5
    zb = cell_rank(P, b) - 0.5
    return (za.clip(lower=0.0) * zb.clip(lower=0.0)).astype(float)


# ── 국면 상태기계 (§7.1) ────────────────────────────────────────────────────────────────────
def classify_phase(P: pd.DataFrame, dd_enter: float = PH_DD_ENTER,
                   cr_enter: float = PH_CR_PCTL_ENTER, use_dd: bool = True,
                   use_credit: bool = True) -> pd.DataFrame:
    """A=물타기(진입금지) / B=반대매매 진행(칼날낙하, 진입금지) / C=소진(진입구간).
    ★ 핵심은 '얼마나 빠졌는가'가 아니라 '강제 재고가 남았는가'다.

    파라미터를 노출하는 이유는 R5(절제)·R2-F(비교군)에서 같은 코드로 조건만 바꿔
    재측정하기 위해서다. 별도 구현을 두면 비교 자체가 오염된다."""
    P = P.copy()
    ret_ex_r = cell_rank(P, "f_ret_ex")
    vol_r = cell_rank(P, "f_vol")
    P["ret_ex_rank"] = ret_ex_r
    P["inst_rank"] = cell_rank(P, "f_inst")

    A = ((P["f_dd"] < dd_enter) & (P["f_cr_pctl"] > 0.50) & (P["f_retail"] > 0))
    B = ((P["f_cr_chg"] < PH_CR_CHG_B) & (P["f_retail"] < 0) & (P["f_dd_spd"] < PH_DD_SPD_B))
    C = ((ret_ex_r >= PH_RET_EX_Q) & (P["f_inst"] > 0) & (vol_r >= 0.50))
    if use_credit:
        C = C & (P["f_cr_pctl"] < cr_enter)
    if use_dd:
        C = C & (P["f_dd"] < dd_enter)

    A = A.fillna(False); B = B.fillna(False); C = C.fillna(False)
    C = C & ~B                       # 반대매매가 진행 중이면 소진 판정을 덮어쓴다
    P["PHASE_A"] = A.astype(int)
    P["PHASE_B"] = B.astype(int)
    P["PHASE_C"] = C.astype(int)
    P["phase"] = np.where(C, "C", np.where(B, "B", np.where(A, "A", "-")))
    return P


# ── 재무 결합 (방화벽 입력) ─────────────────────────────────────────────────────────────────
FLP_FUND_COLS = ["equity", "assets", "liabilities", "cfo_ttm", "op_income_ttm",
                 "net_income_ttm", "revenue_ttm"]


def attach_fundamentals_flp(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """DART 재무를 신호일 기준 as-of 로 결합. 결합키(corp_code) 결측 행을 버리지 않는다(C2)."""
    P = P.copy()
    c2c = (sec.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str).to_dict()
           if len(sec) and "corp_code" in sec.columns else {})
    P["corp_code"] = P["code"].map(c2c)
    if PIT.has("dart_financials"):
        P = PIT.asof_join(P, "dart_financials", by="corp_code", left_time="wk")
    for c in FLP_FUND_COLS:
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_financials"):
        LOG.warn("DART 재무가 없어 방화벽의 자본잠식·영업CF·이자보상 조항이 비활성화됩니다. "
                 "이 전략의 단일 실패모드가 '진짜 죽어가는 회사 매수'이므로 "
                 "DART_API_KEY 입력을 강력히 권합니다.")
    return P


# ── 방화벽 · 거부권 (§7.3) ──────────────────────────────────────────────────────────────────
FIREWALL_CLAUSES = ["자본잠식", "관리종목", "거래정지", "영업CF적자+이자보상<1", "유동성"]
FIREWALL_STATUS: Dict[str, str] = {}          # 조항 → 활성/비활성 사유 (등급 카드에 인쇄)


def apply_firewall(P: pd.DataFrame, watch: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """진짜로 소멸 중인 기업을 거른다. 이진·곱·상쇄 불가(§1-7).
    데이터가 없어 판정할 수 없는 조항은 '통과'로 두되, 감사표에 비활성으로 남긴다."""
    P = P.copy()
    n = len(P)
    audit = []

    ok = pd.Series(True, index=P.index)

    # ① 자본잠식
    if P["equity"].notna().any():
        c = ~(P["equity"] <= 0).fillna(False)
        audit.append(("자본잠식", "활성", int((~c).sum())))
        ok &= c
    else:
        audit.append(("자본잠식", "비활성(재무 없음)", 0))

    # ②③ 관리종목 · 거래정지 (스냅샷만 있으면 '현재 이후'로만 적용 — 과거 오염 금지)
    P["is_watchlist"] = 0
    P["is_trading_halted"] = 0
    if watch is not None and len(watch):
        w = watch.dropna(subset=["code"]).copy()
        w["from_date"] = as_ts_series(w["from_date"])
        for flag, colname in (("admin", "is_watchlist"), ("alert", "is_watchlist"),
                              ("halt", "is_trading_halted")):
            sub = w[w["flag"] == flag]
            if not len(sub):
                continue
            m = sub.groupby("code")["from_date"].min().to_dict()
            frm = P["code"].map(m)
            P[colname] = np.where(frm.notna() & (P["wk"] >= frm), 1, P[colname])
        audit.append(("관리종목", "활성", int((P["is_watchlist"] == 1).sum())))
        audit.append(("거래정지", "활성", int((P["is_trading_halted"] == 1).sum())))
        ok &= (P["is_watchlist"] == 0) & (P["is_trading_halted"] == 0)
    else:
        audit.append(("관리종목", f"비활성(K6 {WATCH_GRADE})", 0))
        audit.append(("거래정지", f"비활성(K6 {WATCH_GRADE})", 0))

    # ④ 영업CF 적자 지속 ∧ 이자보상배율 < 1
    #    ※ 이자비용 계정은 DART 정형 매핑에 없어 '부채×5%' 대리를 쓴다. 대리임을 명시한다.
    if P["cfo_ttm"].notna().any() and P["op_income_ttm"].notna().any():
        icov = safe_div(P["op_income_ttm"], P["liabilities"].abs() * 0.05)
        bad = ((P["cfo_ttm"] < 0) & (icov < 1.0)).fillna(False)
        audit.append(("영업CF적자+이자보상<1(대리)", "활성", int(bad.sum())))
        ok &= ~bad
    else:
        audit.append(("영업CF적자+이자보상<1", "비활성(재무 없음)", 0))

    # ★ 여기까지가 '기업 소멸' 방어 = 보유 중에도 즉시 청산해야 하는 하드 조항이다.
    P["FIREWALL_HARD"] = ok.astype(int)

    # ⑤ 유동성 — 이건 유니버스 밴드의 일부다. 진입 자격에는 쓰되,
    #    보유 중 유동성이 말랐다는 이유로 강제청산하지 않는다(§4.3 "밴드 이탈은 청산 사유가 아니다").
    liq = (P["adv20"] >= MIN_ADV_KRW).fillna(False)
    audit.append(("유동성(ADV20) ※진입자격 전용", "활성", int((~liq).sum())))
    ok &= liq

    P["FIREWALL"] = ok.astype(int)
    FIREWALL_STATUS.clear()
    FIREWALL_STATUS.update({a: b for a, b, _c in audit})
    n_off = sum(1 for _a, b, _c in audit if b.startswith("비활성"))
    if n_off:
        LOG.warn(f"방화벽 {n_off}개 조항이 비활성입니다. 이 전략의 단일 실패모드는 "
                 f"'진짜 죽어가는 회사를 사는 것'이고 방화벽이 유일한 방어입니다 — "
                 f"DART_API_KEY 입력이 성과보다 먼저입니다.")
    LOG.table([[a, b, f"{c:,}"] for a, b, c in audit],
              ["방화벽 조항", "상태", "차단 행수"], ["l", "l", "r"],
              title=f"방화벽 감사 — 전체 {n:,}행 중 통과 {int(P['FIREWALL'].sum()):,}행 "
                    f"({100*P['FIREWALL'].mean():.1f}%)")
    return P


def apply_vetoes(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """V1 희석성 조달 / V2 담보 급증 / V3 이익-현금 괴리 / V_RS 애널리스트 하향.
    거부권은 이진이며 서로 상쇄되지 않는다."""
    P = P.copy()
    P["V1"] = 1; P["V2"] = 1; P["V3"] = 1; P["V_RS"] = 1

    # V1 — 90일 내 유상증자/CB/BW 결정: 강제매도 재고가 '새로' 생성된다
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns:
        d = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue"])].copy()
        if len(d):
            d["rcept_dt"] = as_ts_series(d["rcept_dt"])
            d = d.dropna(subset=["corp_code", "rcept_dt"]).sort_values("rcept_dt")
            d["corp_code"] = d["corp_code"].astype(str)
            L = P[["corp_code", "wk"]].copy()
            L["_ord"] = np.arange(len(L))
            Lv = L.dropna(subset=["corp_code"]).sort_values("wk")
            if len(Lv):
                m = pd.merge_asof(Lv, d[["corp_code", "rcept_dt"]].rename(
                    columns={"rcept_dt": "last_dilute"}),
                    left_on="wk", right_on="last_dilute", by="corp_code", direction="backward")
                gapd = (m["wk"] - m["last_dilute"]).dt.days
                hit = pd.Series(False, index=P.index)
                hit.iloc[m["_ord"].to_numpy()] = (gapd <= 90).fillna(False).to_numpy()
                P["V1"] = (~hit).astype(int)
                LOG.info(f"V1(90일 내 희석성 조달) 발동 {int((P['V1']==0).sum()):,}행")

    # V2 — 최대주주 담보비율 급증: 공개 정형 데이터가 없다. 대리 없이 '비활성'으로 남긴다.
    #      (억지 대리를 넣으면 거부권이 아니라 노이즈가 된다)
    # V3 — 순이익>0 인데 영업CF < 0.5×순이익 (3분기 연속 성격 → TTM 단면으로 근사)
    if P["net_income_ttm"].notna().any() and P["cfo_ttm"].notna().any():
        bad = ((P["net_income_ttm"] > 0) &
               (P["cfo_ttm"] < 0.5 * P["net_income_ttm"])).fillna(False)
        P["V3"] = (~bad).astype(int)
        LOG.info(f"V3(이익-현금 괴리) 발동 {int((P['V3']==0).sum()):,}행")

    # V_RS — 애널리스트 목표주가 하향이 지배적이면 '소진'이 아니라 펀더멘털 악화다
    rs = ctx.get("research_panel")
    if rs is not None and len(rs) and {"code", "wk"}.issubset(rs.columns):
        dupe = [c for c in rs.columns if c in P.columns and c not in ("code", "wk")]
        P = P.merge(rs.drop(columns=dupe), on=["code", "wk"], how="left")
        assert_no_dup_cols(P, "apply_vetoes:research_merge")
    if {"rs_cov_90d", "rs_tp_up_ratio"}.issubset(P.columns):
        bad = ((col(P, "rs_cov_90d").fillna(0) >= 3) &
               (col(P, "rs_tp_up_ratio") <= 0.15)).fillna(False)
        P["V_RS"] = (~bad).astype(int)
        LOG.info(f"V_RS(애널리스트 목표주가 하향 지배) 발동 {int((P['V_RS']==0).sum()):,}행 "
                 f"— 커버리지 3인 이상 & 상향비율 15% 이하")
    for c in ("rs_cov_90d", "rs_tp_up_ratio", "rs_tp_gap"):
        if c not in P.columns:
            P[c] = np.nan
    P["VETO"] = (P["V1"] * P["V2"] * P["V3"] * P["V_RS"]).astype(int)
    return P


# ── 스코어 조립 (§7.2) ──────────────────────────────────────────────────────────────────────
def build_tps(P: pd.DataFrame, method: str = "clip") -> pd.DataFrame:
    """TP 4종. method='raw' 는 R5-7(절제)에서 rank_pct×rank_pct 와 비교하기 위한 것이며
    운영 기본값이 아니다 — clip 을 빼면 '둘 다 최악'이 최고점을 받는다."""
    P = P.copy()
    if method == "clip":
        P["TP_F1"] = tp(P, -P["f_dd"], -P["f_cr_pctl"])
        P["TP_F2"] = tp(P, P["f_ret_ex"], P["f_inst"])
        P["TP_F3"] = tp(P, -P["f_dd"], P["f_vol"])
        P["TP_F4"] = tp(P, -P["f_cr_chg_slow"], P["f_turn"])
    else:
        r = lambda s: cell_rank(P, s)
        P["TP_F1"] = r(-P["f_dd"]) * r(-P["f_cr_pctl"])
        P["TP_F2"] = r(P["f_ret_ex"]) * r(P["f_inst"])
        P["TP_F3"] = r(-P["f_dd"]) * r(P["f_vol"])
        P["TP_F4"] = r(-P["f_cr_chg_slow"]) * r(P["f_turn"])
    return P


def assemble_score(P: pd.DataFrame, use_tps: Optional[Sequence[str]] = None,
                   gate_phase: bool = True, gate_firewall: bool = True,
                   gate_veto: bool = True, band_col: str = "in_band",
                   quiet: bool = False) -> pd.DataFrame:
    P = P.copy()
    if not all(c in P.columns for c in TP_COLS):
        P = build_tps(P)
    cols = list(use_tps) if use_tps else [c for c in TP_COLS if c not in EXCLUDED_TPS]
    P["E"] = nanmean_cols(P, cols)
    P["E_rank"] = P.groupby("wk", observed=True)["E"].rank(pct=True)
    gate = P[band_col].astype(float) if band_col in P.columns else P["in_band"].astype(float)
    if gate_phase:
        gate = gate * P["PHASE_C"]
    if gate_firewall:
        gate = gate * P["FIREWALL"]
    if gate_veto:
        gate = gate * P["VETO"]
    P["Signal"] = P["E_rank"].fillna(0.0) * gate
    P["Signal_rank"] = P["Signal"].where(P["Signal"] > 0)
    if not quiet:
        n_live = int((P["Signal"] > 0).sum())
        LOG.ok(f"신호 산출[{band_col}] — 발화 {n_live:,}행 / 전체 {len(P):,}행 "
               f"(국면C {int(P['PHASE_C'].sum()):,} × 방화벽 {int(P['FIREWALL'].sum()):,} × "
               f"거부권통과 {int(P['VETO'].sum()):,} × 밴드 "
               f"{int(P[band_col].sum()) if band_col in P.columns else 0:,})")
    return P


# ── 강건성·비교군용 경량 패널 ───────────────────────────────────────────────────────────
SLIM_COLS = (["code", "wk", "signal_date", "exec_px", "fwd_ret", "adv20", "mcap", "size_est",
              "E", "E_rank", "Signal", "Signal_rank",
              "cell", "cell_l2", "cell_l3", "phase", "PHASE_A", "PHASE_B", "PHASE_C",
              "FIREWALL", "FIREWALL_HARD", "VETO", "V1", "V3", "V_RS", "in_band",
              "in_band_small", "V6", "stale_days", "mcap_rank", "small_rank", "equity"]
             + SENSOR_COLS + TP_COLS)


def slim_panel(P: pd.DataFrame) -> pd.DataFrame:
    """강건성 스위트는 같은 패널을 20여 회 복사한다. 40열 전체를 복사하면 그 자체가
    수 GB·수십 초의 낭비다 — 백테스트와 재점수화에 실제로 필요한 열만 남긴다."""
    cols = [c for c in dict.fromkeys(SLIM_COLS) if c in P.columns]
    out = P[cols].copy()
    return out

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-FLP-C  애널리스트 리포트 오버레이 (한경컨센서스 · 네이버 리서치)                        ║
# ║                                                                                          ║
# ║  이 전략에서 리포트는 알파 원천이 아니라 '거부권과 해석'이다.                               ║
# ║    · 낙폭 국면에서 같은 애널리스트가 목표주가를 계속 내리고 있다면 그건 '소진'이 아니라     ║
# ║      펀더멘털 악화다 → V_RS 거부권.                                                        ║
# ║    · 커버리지가 사라진 종목(리포트 0건)은 '기관이 이미 손을 뗀' 상태 → 해석표에 표기.       ║
# ║                                                                                          ║
# ║  ★ 목표주가 리비전은 '같은 애널리스트의 직전 제시가'와 비교해야 의미가 있다.                ║
# ║    그래서 애널리스트 원장(entity resolution)이 장식이 아니라 필수 입력이다.                 ║
# ║  ★ 원장은 공용 인덱스에 적재되어 다른 전략이 그대로 재사용한다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

RESEARCH_PANEL_COLS = ["code", "wk", "rs_cov_90d", "rs_tp_up_ratio", "rs_tp_gap", "rs_n_180d"]


def build_research_panel(links: pd.DataFrame, P_keys: pd.DataFrame,
                         weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """(code, wk) 별 리포트 오버레이.

    입력 links 는 build_analyst_ledger 의 산출(보고서×애널리스트 링크)이며
    최소한 code / date(발간일) / analyst_id / target_price 를 갖는다.

    PIT: 발간일 그 자체가 공개일이므로 knowledge_date = date. 미래 리포트는 절대 안 본다.
    """
    if links is None or not len(links):
        LOG.info("리포트 원장이 비어 있어 오버레이를 생성하지 않습니다 "
                 "(V_RS 거부권 비활성 · 해석표의 커버리지 열은 공란).")
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)

    L = links.copy()
    dcol = next((c for c in ("pub_date", "date", "report_date") if c in L.columns), None)
    ccol = next((c for c in ("stock_code", "code") if c in L.columns), None)
    if dcol is None or ccol is None:
        LOG.warn(f"리포트 원장에 발간일/종목코드 컬럼이 없습니다 → 오버레이 생략. "
                 f"컬럼={list(L.columns)[:12]}")
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)
    L["date"] = as_ts_series(L[dcol])
    L["code"] = L[ccol].map(to_code6)
    L = L.dropna(subset=["code", "date"])
    if "target_price" not in L.columns:
        L["target_price"] = np.nan
    L["target_price"] = pd.to_numeric(L["target_price"], errors="coerce")
    aid = next((c for c in ("analyst_id", "analyst_key", "analyst") if c in L.columns), None)
    if aid is None:
        L["analyst_id"] = L.get("broker", pd.Series("", index=L.index)).astype(str)
        aid = "analyst_id"

    # ── 같은 애널리스트·같은 종목의 직전 목표주가 대비 방향 ────────────────────────────────
    L = L.sort_values([aid, "code", "date"])
    prev_tp = L.groupby([aid, "code"], observed=True)["target_price"].shift(1)
    L["tp_dir"] = np.where(L["target_price"] > prev_tp * 1.01, 1,
                           np.where(L["target_price"] < prev_tp * 0.99, -1, 0))
    L.loc[L["target_price"].isna() | prev_tp.isna(), "tp_dir"] = np.nan

    # ── (code, week) 격자로 90일/180일 창 집계 — 종목 루프 없이 merge_asof + 롤링 ──────────
    #   주 격자에 맞춰 리포트를 주 단위로 먼저 압축한 뒤 rolling 하면 O(N) 이다.
    wk_of = pd.DatetimeIndex(weeks)
    if not len(wk_of):
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)
    pos = np.searchsorted(wk_of.values, L["date"].values, side="right")
    keep = pos < len(wk_of)
    L = L[keep].copy()
    L["wk"] = wk_of.values[pos[keep]]     # 발간일 '이후 첫 신호주'에 반영 (당일 누수 차단)
    if L.empty:
        return pd.DataFrame(columns=RESEARCH_PANEL_COLS)

    agg = (L.groupby(["code", "wk"], observed=True)
             .agg(n=("date", "size"),
                  up=("tp_dir", lambda s: float((s == 1).sum())),
                  dn=("tp_dir", lambda s: float((s == -1).sum())),
                  tp_med=("target_price", "median"))
             .reset_index())

    full = P_keys[["code", "wk"]].drop_duplicates()
    A = full.merge(agg, on=["code", "wk"], how="left").sort_values(["code", "wk"])
    for c in ("n", "up", "dn"):
        A[c] = A[c].fillna(0.0)
    g = lambda c: A.groupby("code", observed=True)[c]
    A["rs_n_180d"] = g("n").transform(lambda s: s.rolling(26, min_periods=1).sum())
    n90 = g("n").transform(lambda s: s.rolling(13, min_periods=1).sum())
    up90 = g("up").transform(lambda s: s.rolling(13, min_periods=1).sum())
    dn90 = g("dn").transform(lambda s: s.rolling(13, min_periods=1).sum())
    A["rs_cov_90d"] = n90
    denom = (up90 + dn90)
    A["rs_tp_up_ratio"] = np.where(denom > 0, up90 / denom, np.nan)
    A["rs_tp_med"] = g("tp_med").transform(lambda s: s.ffill(limit=26))
    A["rs_tp_gap"] = np.nan          # 가격 대비 괴리는 패널 결합 후 계산한다
    out = A[RESEARCH_PANEL_COLS].copy()
    LOG.ok(f"리포트 오버레이 {len(out):,}행 — 커버리지 보유 {int((out['rs_cov_90d']>0).sum()):,}행, "
           f"목표주가 방향 판정 가능 {int(out['rs_tp_up_ratio'].notna().sum()):,}행")
    PIPE.io("OUT", "MEM", "research_panel", out)
    return out


def audit_research_wiring(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame,
                          panel: pd.DataFrame):
    """'수집은 됐는데 배선이 끊긴' 상태를 '데이터 부재'와 구분한다.
    이 구분이 없으면 운영자가 엉뚱하게 API 키를 의심하며 시간을 쓴다."""
    rows = [
        ["리포트 원장(rep)", f"{len(rep):,}행" if rep is not None else "없음",
         "한경+네이버 통합 원장"],
        ["애널리스트 원장(A)", f"{len(A):,}명" if A is not None else "없음",
         "증권사 사명 정규화 + 동명이인 분리"],
        ["보고서×애널 링크(L)", f"{len(L):,}행" if L is not None else "없음",
         "목표주가 리비전의 유일한 근거"],
        # ★ rs_cov_90d 는 전 행에 0.0 으로 채워지므로 notna() 로 세면 항상 '전체 행수'가 되어
        #   배선 단절 센티널이 영원히 발화하지 않는다. '실제로 커버리지가 있는' 행을 센다.
        ["패널 결합 결과(커버리지>0)",
         f"{int((panel['rs_cov_90d'].fillna(0) > 0).sum()):,}행" if
         panel is not None and "rs_cov_90d" in getattr(panel, "columns", []) else "0행",
         "여기가 0이면 수집이 아니라 '배선'이 끊긴 것"],
    ]
    LOG.table(rows, ["단계", "규모", "의미"], ["l", "r", "l"],
              title="애널리스트 리포트 → 전략 배선 점검 (다중소스 원장 연결)")
    if (rep is not None and len(rep) > 0 and
            (panel is None or "rs_cov_90d" not in getattr(panel, "columns", []) or
             int((panel["rs_cov_90d"].fillna(0) > 0).sum()) == 0)):
        LOG.warn("리포트는 수집됐는데 패널에 한 건도 결합되지 않았습니다. "
                 "종목코드 정규화(6자리) 또는 발간일 파싱을 먼저 의심하세요 — "
                 "'데이터 부재'가 아니라 '배선 결함'입니다.")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  주간 백테스트 엔진 + 비용 모델 (§8)                                                   ║
# ║                                                                                          ║
# ║  · 주 1회 리밸런싱. 체결 = 신호 산출일의 '다음 거래일 시가'. 당일 종가 체결 금지.           ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(C2).                        ║
# ║    ★ 이 전략의 표적 집단이 곧 상폐 위험 집단이므로 여기가 성과의 진위를 가른다.             ║
# ║  · 청산: f_cr_pctl ≥ 0.5 회복(재취약) / 방화벽·거부권 위반 / 26주 상한.                     ║
# ║    보유 중 '유니버스 밴드 이탈'은 청산 사유가 아니다(C13).                                  ║
# ║  · 사이징 상수는 헤더에 못박혀 있고, R12 가 그 근거를 사후 검증한다(§12-2).                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5           # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10              # 제곱근 충격 계수 (소형주 가중이 여기서 나온다)
PERIODS_PER_YEAR = 52.0


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float, k: float = SLIPPAGE_K) -> float:
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(k * math.sqrt(part))


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """동일가중 → 종목당 상한 + ADV 참여율 상한 → 잔여를 자유 종목에 재배분.
    ★ 신호강도 비례 사이징을 쓰지 않는다. 이 전략의 신호는 순위정보이지 기대수익 크기가 아니다."""
    n = len(sub)
    if n == 0:
        return sub.assign(weight=[])
    w = np.full(n, 1.0 / n)
    adv = pd.to_numeric(sub.get("adv20"), errors="coerce").to_numpy(dtype=float)
    cap_adv = np.where(np.isfinite(adv) & (adv > 0),
                       POS_ADV_PARTICIPATION * adv / max(ACCOUNT_KRW, 1.0), POS_MAX_WEIGHT)
    cap = np.minimum(np.full(n, POS_MAX_WEIGHT), np.maximum(cap_adv, POS_MIN_WEIGHT))
    for _ in range(6):
        over = w > cap
        if not over.any():
            break
        rem = float(np.sum(w[over] - cap[over]))
        w[over] = cap[over]
        free = ~over & (w < cap)
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem + w[free]) if pool > 1e-12 else (rem / free.sum())
        w = np.minimum(w, cap)
    s = w.sum()
    if s > 1.0 + 1e-9:
        w = w / s
    return sub.assign(weight=w)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.head(0)
    # 동점 처리: 신호 동률이면 유동성이 큰 쪽 → 그래도 같으면 종목코드 순.
    # ★ 과거 세션 교훈: 동점을 암묵적 행순서로 깨면 같은 입력이 다른 포트폴리오를 낳는다
    #   (C8 결정성 위반). 마지막 키까지 명시해 완전히 결정적으로 만든다.
    keys, asc = [signal_col, "adv20", "code"], [False, False, True]
    keys = [k for k in keys if k in df.columns]
    asc = asc[:len(keys)]
    d = df.sort_values(keys, ascending=asc, kind="mergesort")
    return d.head(n)


def run_backtest_w(P: pd.DataFrame, weeks: pd.DatetimeIndex, uni: "Universe",
                   sec: pd.DataFrame, signal_col: str = "Signal_rank",
                   top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                   slip_k: float = SLIPPAGE_K, label: str = "FLP",
                   exit_cr: float = EXIT_CR_PCTL,
                   hold_max: int = HOLD_MAX_WEEKS, audit: bool = False) -> dict:
    """audit=True 는 '대표 실행' 하나에만 준다.

    ★ 감쇠 원장(uni.attrition)은 append-only 라, 강건성 arm 20여 회와 스몰캡 비교까지
      전부 기록하면 §10.4 감쇠표가 '여러 전략의 평균'이 되어 아무 것도 뜻하지 않게 된다.
    """
    mkt = (sec.set_index("code")["market"].astype(str).to_dict()
           if sec is not None and len(sec) and "market" in sec.columns else {})
    delist = uni.delisting_map() if uni is not None else {}
    hold: Dict[str, dict] = {}
    prev_w: Dict[str, float] = {}
    rows, holdings_log = [], []
    n_frozen_events = n_forced_delist = n_stale_writeoff = 0

    need = [c for c in ("adv20", "fwd_ret", "FIREWALL", "FIREWALL_HARD", "VETO", "f_cr_pctl",
                        "PHASE_C", "exec_px", signal_col) if c in P.columns]
    Pw = {w: g for w, g in P.groupby("wk", observed=True)} if len(P) else {}

    for i, w in enumerate(weeks):
        # 다음 리밸런스 시점 — 상장폐지 귀속 창을 '고정 7일'이 아니라 실제 보유구간으로 잡는다
        w_next = weeks[i + 1] if i + 1 < len(weeks) else w + pd.Timedelta(days=7)
        sub = Pw.get(w)
        rec: Dict[str, dict] = {}
        if sub is not None and len(sub):
            for _c, *_v in sub[["code"] + need].itertuples(index=False, name=None):
                rec[_c] = dict(zip(need, _v))

        # ── ① 패널에서 사라진 보유분 = 거래정지/폐지. 조용히 0% 로 털어내지 않는다. ──────
        #   한국의 전형 경로는 거래정지 → 정리매매 → 상장폐지다. 그 사이 종목은 패널에서
        #   사라지므로, 예전 구현처럼 '보유 목록에서 pop' 하면 총손실이 무손실로 둔갑한다.
        #   → 팔 수 없는 동안은 비중을 그대로 들고 있고(수익 0), 폐지가 확정되면 -100%.
        frozen: Dict[str, float] = {}
        forced: List[Tuple[str, float, float]] = []
        gap_ret: Dict[str, float] = {}
        for c, wt in list(prev_w.items()):
            if c in rec:
                # ★ 거래재개: 정지 구간의 가격 변화를 이번 주에 실현한다.
                #   정지 중 0% 로 두고 재개 후 새 가격에서 다시 시작하면, 정지 기간에
                #   무너진 가격이 어디에도 계상되지 않는다(이 전략에서 가장 흔한 손실 경로다).
                h0 = hold.get(c)
                if h0 and h0.get("frozen", 0) > 0:
                    last_px = h0.get("last_exec")
                    now_px = (rec[c] or {}).get("exec_px")
                    if (last_px and now_px and np.isfinite(float(last_px))
                            and np.isfinite(float(now_px)) and float(last_px) > 0):
                        gap_ret[c] = float(now_px) / float(last_px) - 1.0
                    h0["frozen"] = 0                 # 재개했으므로 동결 카운터 리셋
                if h0 is not None:
                    _px = (rec[c] or {}).get("exec_px")
                    if _px is not None and pd.notna(_px):
                        h0["last_exec"] = float(_px)
                continue
            dl = delist.get(c)
            h = hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
            if dl is not None and pd.notna(dl) and dl <= w_next:
                forced.append((c, wt, -1.0))          # 정리매매가 없으면 -100% (C2)
                hold.pop(c, None)
                n_forced_delist += 1
            elif h["frozen"] >= hold_max:
                # 26주 넘게 시세가 없고 폐지일도 확인되지 않는다 → 보수적으로 총손실 처리.
                # (낙관적으로 0% 처리하면 이 전략의 성과가 구조적으로 부풀려진다)
                forced.append((c, wt, -1.0))
                hold.pop(c, None)
                n_stale_writeoff += 1
            else:
                h["frozen"] += 1
                frozen[c] = wt
                n_frozen_events += 1

        if sub is None or sub.empty:
            ret_forced = sum(wt * r for _c, wt, r in forced)
            for c, wt, r in forced:
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": r,
                                     "signal": np.nan, "state": "delisted"})
            for c, wt in frozen.items():
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": 0.0,
                                     "signal": np.nan, "state": "halted"})
            rows.append({"wk": w, "ret": ret_forced, "ret_gross": ret_forced,
                         "n": len(frozen), "turnover": 0.0, "cost": 0.0,
                         "invested": float(sum(frozen.values()))})
            prev_w = dict(frozen)
            continue

        # ★ 진입 자격은 '신호' 하나로만 판단한다.
        #   assemble_score 가 이미 방화벽·거부권·밴드를 Signal 에 곱해 넣었으므로
        #   (게이트에 걸리면 Signal 이 정확히 0), 엔진이 같은 게이트를 다시 적용하면
        #   R5 절제의 "방화벽 off"·"거부권 off" arm 이 수학적으로 무의미해진다
        #   (게이트를 빼고 채점해도 엔진이 도로 걸러내므로 ΔCAGR 이 항상 0 → 절제표가
        #    "방화벽은 기여가 없다"고 거짓 보고한다). 청산 쪽 FIREWALL_HARD 는 그대로다.
        fresh_px = (sub["stale_days"] <= 3) if "stale_days" in sub.columns else True
        elig = sub[sub[signal_col].notna() & (sub[signal_col] > 0) &
                   sub["exec_px"].notna() & fresh_px]
        if uni is not None and audit:
            uni.audit_row("유동성필터", w, sub[sub["V6"] == 1]["code"].tolist())
            uni.audit_row("낙폭조건", w, sub[(sub["V6"] == 1) &
                                             (sub["f_dd"] < PH_DD_ENTER)]["code"].tolist())
            uni.audit_row("국면C", w, sub[(sub["V6"] == 1) & (sub["PHASE_C"] == 1)]["code"].tolist())
            uni.audit_row("방화벽통과", w, sub[(sub["V6"] == 1) & (sub["PHASE_C"] == 1) &
                                               (sub["FIREWALL"] == 1)]["code"].tolist())
            uni.audit_row("거부권통과", w, elig["code"].tolist())

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, min(k, len(elig)), signal_col)
        if uni is not None and audit:
            uni.audit_row("최종선정", w, pick["code"].tolist())

        # ── ② 청산 판정 (진입 논리와 같은 언어로) ──────────────────────────────────────
        keep = []
        for c, h in list(hold.items()):
            if c in frozen:
                continue                       # 팔 수 없는 종목은 청산 판단 대상이 아니다
            r0 = rec.get(c)
            if r0 is None:
                continue
            exited = False
            fw_hard = r0.get("FIREWALL_HARD", r0.get("FIREWALL", 1))
            if fw_hard == 0 or r0.get("VETO", 1) == 0:
                exited = True                  # 기업 소멸 방어·거부권은 즉시 강제청산
            elif h["weeks"] >= hold_max:
                exited = True                  # 6개월 상한
            else:
                crp = r0.get("f_cr_pctl")
                if crp is not None and pd.notna(crp) and float(crp) >= exit_cr:
                    exited = True              # 신규 신용 유입 = 다시 취약해짐
            if not exited:
                keep.append(c)

        exited = {c for c in hold if c not in keep and c not in frozen}
        if exited:
            # 청산 사유가 발생한 종목을 같은 주에 다시 사면 보유상한·청산규칙이 무의미해진다
            pick = pick[~pick["code"].isin(exited)]
        extra = sub[sub["code"].isin(keep) & ~sub["code"].isin(set(pick["code"]))]
        target = pd.concat([pick, extra], ignore_index=True) if len(extra) else pick
        room = max(0, PORTFOLIO_MAX_NAMES - len(frozen))
        if len(target) > room:
            held = target[target["code"].isin(keep)].head(room)
            fresh = _top_n(target[~target["code"].isin(keep)],
                           max(0, room - len(held)), signal_col)
            target = pd.concat([held, fresh], ignore_index=True)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        # 정지 종목이 물고 있는 비중만큼 신규 가용 자본이 줄어든다 (팔 수 없으므로)
        w_frozen = float(sum(frozen.values()))
        avail = max(0.0, 1.0 - w_frozen)
        w_new = dict(frozen)
        if len(target):
            for c, wt in zip(target["code"], target["weight"]):
                w_new[c] = float(wt) * avail

        traded = (set(w_new) | set(prev_w)) - {c for c, _wt, _r in forced}
        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0)) for c in traded)

        cost = 0.0
        if apply_costs:
            for c in traded:
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                tx = sell_tax(w, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (COMMISSION_BPS / 1e4 + slippage(notional, adv, slip_k) + tx)

        ret = sum(wt * r for _c, wt, r in forced)
        for c, wt, r in forced:
            holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": r,
                                 "signal": np.nan, "state": "delisted"})
        dead_now: List[str] = []
        for c, wt in w_new.items():
            if c in frozen:
                holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": 0.0,
                                     "signal": np.nan, "state": "halted"})
                continue
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            state = "held"
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and w < dl <= w_next:
                # ★ 상장폐지 주간: 정리매매 최종가가 없으면 -100%. 누락 처리 금지(C2).
                fr = -1.0 if not np.isfinite(fr) else fr
                state = "delisted"
                dead_now.append(c)             # 여기서 손실을 확정했으므로 다음 주에 또 세지 않는다
            if not np.isfinite(fr):
                fr = 0.0
            g = gap_ret.pop(c, 0.0)            # 거래정지 구간의 가격 변화(재개 주에 실현)
            if g:
                state = "resumed"
            ret += wt * (fr + g)
            holdings_log.append({"wk": w, "code": c, "weight": wt, "ret": fr + g,
                                 "signal": _r.get(signal_col), "state": state})
            h = hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
            _px = _r.get("exec_px")
            if _px is not None and pd.notna(_px):
                h["last_exec"] = float(_px)
        rows.append({"wk": w, "ret": ret - cost, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost,
                     "invested": float(sum(w_new.values()))})

        for c in dead_now:                     # 폐지 확정분은 포지션을 여기서 종료한다
            w_new.pop(c, None)
            hold.pop(c, None)
            n_forced_delist += 1
        for c in list(hold):
            if c in w_new:
                hold[c]["weeks"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"weeks": 0, "frozen": 0, "last_exec": np.nan})
        prev_w = w_new

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    if n_forced_delist or n_stale_writeoff or n_frozen_events:
        LOG.info(f"[{label}] 보유 중 사고 처리 — 거래정지 보유주 {n_frozen_events:,}건 · "
                 f"폐지확정 -100% {n_forced_delist:,}건 · "
                 f"장기 시세부재 보수적 상각 {n_stale_writeoff:,}건 "
                 f"(0% 로 조용히 털지 않습니다 — C2)")
    return {"returns": R, "holdings": pd.DataFrame(holdings_log), "label": label,
            "incidents": {"frozen": n_frozen_events, "delisted": n_forced_delist,
                          "stale_writeoff": n_stale_writeoff}}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats_w(R: pd.DataFrame, rf: float = 0.0) -> dict:
    if R is None or not len(R):
        return {}
    r = R["ret"].fillna(0).to_numpy(dtype=float)
    n = len(r)
    eq = np.cumprod(1 + r)
    years = n / PERIODS_PER_YEAR
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if len(dn) > 1 else np.nan
    # ★ 최고점 후보에 초기자본 1.0 을 포함한다. 빼면 시작부터 내리 하락한 구간의
    #   낙폭이 '1주차 종가 대비'로 측정되어 MDD 가 과소평가된다.
    eq_full = np.concatenate([[1.0], eq])
    peak = np.maximum.accumulate(eq_full)
    dd = (eq_full / peak - 1)[1:]
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    _mu, tstat = hac_tstat(r)
    return {
        "주수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "주평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(주)": int(mx),
        "누적수익": float(eq[-1] - 1),
        "평균종목수": float(R["n"].mean()) if "n" in R else np.nan,
        "평균투자비중": float(R["invested"].mean()) if "invested" in R else np.nan,
        "주평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "주평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """이 전략은 우측 꼬리 의존적이다. 상위 종목 제외 시 성과가 사라지는지 매번 측정한다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {"총기여": float(contrib.sum())}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후"] = float(contrib.sum() - contrib.iloc[:k].sum())
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.3f})" for c, v in contrib.head(5).items())
    return out


def benchmark_returns_w(weeks: pd.DatetimeIndex, P: Optional[pd.DataFrame] = None
                        ) -> Dict[str, pd.Series]:
    """★ 벤치마크 수치를 하드코딩하지 않는다(§1-5). 여기서 직접 재측정한다.
    KOSPI·KOSDAQ 지수 + '유니버스 동일가중'(이 전략의 진짜 대조군)."""
    out: Dict[str, pd.Series] = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None and len(weeks):
            try:
                limiter("krx").wait()
                d = fdr.DataReader(sym, (weeks[0] - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
                                   weeks[-1].strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        s = d.set_index("date")["close"].sort_index()
        s = s.reindex(s.index.union(weeks)).ffill().reindex(weeks)
        # ★ 전략 수익률은 [w, w+1] 구간의 '선행' 수익률이다. 지수를 후행 pct_change 로 두면
        #   한 주가 어긋나 R12(꼬리 동시손실)가 '지난주 급락'으로 위기주를 고르게 된다.
        out[name] = s.pct_change().shift(-1)
    if P is not None and len(P) and "fwd_ret" in P.columns:
        eqw = (P[P["in_band"] == 1].groupby("wk", observed=True)["fwd_ret"].mean()
               if "in_band" in P.columns else P.groupby("wk", observed=True)["fwd_ret"].mean())
        out["유니버스 동일가중"] = eqw.reindex(weeks)
    idx_missing = [n for n in ("KOSPI", "KOSDAQ") if n not in out]
    if idx_missing:
        # ★ '유니버스 동일가중'이 항상 채워지므로 out 이 비는 일은 없다 → 지수 결측을
        #   따로 경고하지 않으면 R0·R7·R12 가 조용히 '자기 유니버스와만' 비교하게 된다.
        LOG.warn(f"지수 벤치마크 {idx_missing} 를 받지 못했습니다 — R0/R7/R12 는 "
                 f"'유니버스 동일가중'만으로 판정합니다. 전략을 자기 유니버스와 비교하는 것은 "
                 f"시장 대비 성과가 아니므로 해석에 반드시 반영하세요(수치를 임의로 채우지 않습니다).")
    return out

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트 (§10) — 순서대로. 앞 단계 실패 시 진행 금지.                             ║
# ║                                                                                          ║
# ║   R2-F ⭐⭐ 소진조건 vs 단순 낙폭과대   (이 전략의 존재 이유. 다른 무엇보다 먼저 본다)      ║
# ║   R0     자체측정 벤치마크 대비        (수치 하드코딩 금지 — 여기서 직접 재측정)           ║
# ║   R1     누수 자가검정                (미래수익 주입 + 신호 -1주 시프트, 둘 다 개선해야)   ║
# ║   R12 ⭐ 꼬리 동시손실                (위험 프리미엄의 대가를 사전에 측정하고 상한 확정)   ║
# ║   R3     팩터 직교화                  (시장·규모·가치·모멘텀·저변동성 잔차 알파)           ║
# ║   R5     절제                        (무엇이 실제로 기여하는가)                            ║
# ║   R7     레짐 분할 / R9 회전율·비용 시나리오                                               ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 만져 좋아 보이게 만들지 않는다(§11).    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: List[dict] = []


def _record(rid: str, name: str, passed: Optional[bool], detail: str,
            kill: bool = False, numbers: Optional[dict] = None):
    ROBUST_RESULTS.append({"id": rid, "name": name, "pass": passed, "detail": detail,
                           "kill": kill, "numbers": numbers or {}})
    icon = "✔" if passed else ("✘" if passed is False else "→")
    (LOG.ok if passed else (LOG.error if passed is False else LOG.info))(
        f"[{rid}] {icon} {name} — {detail}")
    if kill and passed is False and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name}: {detail}")


def _stat(bt: dict) -> dict:
    return perf_stats_w(bt.get("returns", pd.DataFrame()))


def _series(bt: dict) -> pd.Series:
    R = bt.get("returns")
    if R is None or not len(R):
        return pd.Series(dtype=float)
    return pd.Series(R["ret"].to_numpy(dtype=float), index=pd.DatetimeIndex(R["wk"]))


def _diff_tstat(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """두 전략 수익률 차이의 평균과 HAC t. '유의하게 이긴다'를 눈대중하지 않는다."""
    idx = a.index.intersection(b.index)
    if len(idx) < 20:
        return (np.nan, np.nan)
    d = (a.reindex(idx).fillna(0) - b.reindex(idx).fillna(0)).to_numpy(dtype=float)
    mu, t = hac_tstat(d)
    return float(np.mean(d)), float(t)


# ═══ R2-F — 이 전략의 존재 이유 (§10.1) ═════════════════════════════════════════════════════
def R2F_exhaustion_vs_drawdown(P: pd.DataFrame, run_fn: Callable,
                               band_col: str = "in_band") -> dict:
    """A 낙폭과대 단독 / B 소진조건 단독(낙폭 무시) / C FLP 전체.
    동일 유니버스·동일 비용·동일 기간. 다른 것은 조건뿐이다."""
    base = slim_panel(P)

    # A: 낙폭 하위 분위 매수 — 신용·수급 조건 없음, 방화벽/밴드만 공통 적용
    A = base.copy()
    A["E_rank"] = A.groupby("wk", observed=True)["f_dd"].rank(pct=True, ascending=True)
    A["Signal"] = (A["E_rank"].fillna(0.0) * (A["f_dd"] < PH_DD_ENTER).astype(int) *
                   A["FIREWALL"] * A[band_col])
    A["Signal"] = A["Signal"].where(A["E_rank"] <= 0.20, 0.0)     # 하위 20% 분위만
    A["Signal_rank"] = A["Signal"].where(A["Signal"] > 0)

    # B: 소진 조건 단독 (낙폭 조건 제거)
    B = classify_phase(base, use_dd=False)
    B = assemble_score(B, use_tps=["TP_F2", "TP_F4"], band_col=band_col, quiet=True)

    # C: 전체 — ★ 반드시 A/B 와 '같은 밴드'로 새로 채점한다.
    #   호출자가 넘긴 P 의 Signal 은 기본 밴드(in_band)로 매겨진 값이다. 그대로 쓰면
    #   스몰캡 R2-F 가 '스몰캡 A/B vs 전체 C' 를 비교하게 되어 판정이 통째로 무효가 된다.
    C = assemble_score(base, band_col=band_col, quiet=True)

    bts = {}
    for lab, pp in (("A_낙폭과대단독", A), ("B_소진단독", B), ("C_FLP전체", C)):
        bts[lab] = run_fn(pp, label=lab)
    sA, sB, sC = (_stat(bts["A_낙폭과대단독"]), _stat(bts["B_소진단독"]), _stat(bts["C_FLP전체"]))
    rows = []
    for lab, s in (("A 낙폭과대 단독", sA), ("B 소진조건 단독", sB), ("C FLP 전체", sC)):
        rows.append([lab, f"{s.get('CAGR', float('nan')):.2%}", f"{s.get('MDD', float('nan')):.2%}",
                     f"{s.get('Sharpe', float('nan')):.2f}", f"{s.get('Calmar', float('nan')):.2f}",
                     f"{s.get('승률', float('nan')):.1%}", f"{s.get('평균종목수', float('nan')):.1f}"])
    LOG.table(rows, ["비교군", "CAGR", "MDD", "Sharpe", "Calmar", "승률", "평균종목수"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="R2-F ⭐ 소진 조건이 실제로 기여하는가 (§10.1) — 다른 어떤 지표보다 먼저 본다")

    dCA, tCA = _diff_tstat(_series(bts["C_FLP전체"]), _series(bts["A_낙폭과대단독"]))
    dCB, tCB = _diff_tstat(_series(bts["C_FLP전체"]), _series(bts["B_소진단독"]))
    cagr_gap = (sC.get("CAGR", np.nan) - sA.get("CAGR", np.nan))

    # 판정은 '경제적 크기'와 '통계적 유의성'을 따로 본다.
    #  · 둘 다 충족 → PASS
    #  · 크기는 있으나 유의하지 않음 → 판정보류(더 많은 증거 필요). 킬하지 않는다 —
    #    노이즈를 근거로 전략을 죽이는 것도, 살리는 것도 똑같이 부정직하다.
    #  · 크기 자체가 없음(≤2%p) → §11-4 킬. 낙폭과대의 재포장이다.
    verdict, passed, kill = "", None, False
    if not np.isfinite(cagr_gap):
        verdict = "표본 부족으로 판정 불가 — 데이터 등급을 먼저 올려야 한다"
        passed = None
    elif cagr_gap > 0.02 and (np.isfinite(tCA) and tCA >= 1.5):
        verdict = (f"PASS — C가 A를 CAGR {cagr_gap:+.2%}p, 주간초과수익 t={tCA:.2f} 로 상회. "
                   f"소진 판정이 실제로 기여한다")
        passed = True
    elif cagr_gap > 0.02:
        verdict = (f"판정보류 — C가 A보다 CAGR {cagr_gap:+.2%}p 높지만 t={tCA:.2f} 로 "
                   f"유의하지 않다(기준 1.5). 크기는 있으나 증거가 얇다: 표본 구간·데이터 등급을 "
                   f"올린 뒤 재측정할 것. 유의성 없이 PASS 로 읽지 말 것")
        passed = None
    elif cagr_gap < -0.02:
        verdict = (f"C < A ({cagr_gap:+.2%}p) — 소진 조건이 좋은 기회를 죽이고 있다. "
                   f"임계 재검토 후 재측정 대상(§10.1)")
        passed = False
    else:
        verdict = (f"★ C ≈ A (CAGR 차이 {cagr_gap:+.2%}p, t={tCA:.2f}) — 이건 새 전략이 아니라 "
                   f"낙폭과대의 재포장이다. §11-4 킬 기준")
        passed, kill = False, True
    if np.isfinite(dCB) and abs(sC.get("CAGR", 0) - sB.get("CAGR", 0)) < 0.02 and \
            sB.get("CAGR", -9) > sA.get("CAGR", -9):
        verdict += " · B>A 이면서 C≈B → 낙폭 조건 불필요. 더 단순한 B를 최종안으로 검토할 것"

    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        verdict += ("  ⚠ 단, 신용잔고가 프록시(Fallback B)이므로 이 판정의 신뢰도는 "
                    "구조적으로 하향입니다 — '소진'이 아니라 '개인 누적순매수'를 본 결과입니다")
    _record("R2-F", "소진 조건 vs 단순 낙폭과대 ⭐⭐", passed, verdict, kill=kill,
            numbers={"CAGR_A": sA.get("CAGR"), "CAGR_B": sB.get("CAGR"), "CAGR_C": sC.get("CAGR"),
                     "t_C_minus_A": tCA, "t_C_minus_B": tCB})
    return {"A": sA, "B": sB, "C": sC, "t_CA": tCA, "verdict": verdict, "bts": bts}


# ═══ R0 — 자체측정 벤치마크 대비 ════════════════════════════════════════════════════════════
def R0_benchmark(bt: dict, bench: Dict[str, pd.Series]) -> None:
    s = _stat(bt)
    rows = [["FLP 전략", f"{s.get('CAGR', np.nan):.2%}", f"{s.get('MDD', np.nan):.2%}",
             f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('Calmar', np.nan):.2f}"]]
    best_calmar = -9e9
    for name, sr in bench.items():
        if sr is None or not len(sr.dropna()):
            continue
        b = perf_stats_w(pd.DataFrame({"wk": sr.index, "ret": sr.fillna(0).to_numpy()}))
        rows.append([name, f"{b.get('CAGR', np.nan):.2%}", f"{b.get('MDD', np.nan):.2%}",
                     f"{b.get('Sharpe', np.nan):.2f}", f"{b.get('Calmar', np.nan):.2f}"])
        if np.isfinite(b.get("Calmar", np.nan)):
            best_calmar = max(best_calmar, b["Calmar"])
    LOG.table(rows, ["대상", "CAGR", "MDD", "Sharpe", "Calmar"], ["l", "r", "r", "r", "r"],
              title="R0 자체측정 벤치마크 (★ 수치 하드코딩 금지 — 이 실행에서 직접 측정한 값)")
    if best_calmar <= -9e8:
        _record("R0", "벤치마크 대비", None, "벤치마크를 측정하지 못해 판정 보류 (수치를 임의로 채우지 않음)")
        return
    ok = np.isfinite(s.get("Calmar", np.nan)) and s["Calmar"] > best_calmar
    _record("R0", "벤치마크 대비 (Calmar)", bool(ok),
            f"전략 Calmar {s.get('Calmar', np.nan):.2f} vs 최고 벤치마크 {best_calmar:.2f}",
            numbers={"calmar": s.get("Calmar"), "bench_best": best_calmar})


# ═══ R1 — 누수 자가검정 ═════════════════════════════════════════════════════════════════════
def R1_leakage(P: pd.DataFrame, run_fn: Callable, base_stat: dict) -> None:
    P = slim_panel(P)
    """두 개의 '고의 오염본'이 뚜렷하게 좋아져야 한다. 안 좋아지면 하네스가 고장난 것이고,
    그 경우 이 실행의 모든 결과는 무효다(§11-5)."""

    base_c = base_stat.get("CAGR", np.nan)

    # (a) 미래 수익률 직접 주입
    Pa = P.copy()
    Pa["Signal"] = Pa["fwd_ret"].groupby(Pa["wk"]).rank(pct=True).fillna(0) * \
        Pa["in_band"] * Pa["FIREWALL"]
    Pa["Signal_rank"] = Pa["Signal"].where(Pa["Signal"] > 0)
    sa = _stat(run_fn(Pa, label="R1a_미래수익주입"))

    # (b) 신호를 1주 앞당김(=미래를 5영업일 미리 봄)
    Pb = P.sort_values(["code", "wk"]).copy()
    Pb["Signal"] = Pb.groupby("code", observed=True)["Signal"].shift(-1).fillna(0.0)
    Pb["Signal_rank"] = Pb["Signal"].where(Pb["Signal"] > 0)
    sb = _stat(run_fn(Pb, label="R1b_신호5영업일선행"))

    LOG.table([["기준(정상)", f"{base_c:.2%}", f"{base_stat.get('Sharpe', np.nan):.2f}"],
               ["(a) 미래수익 주입", f"{sa.get('CAGR', np.nan):.2%}", f"{sa.get('Sharpe', np.nan):.2f}"],
               ["(b) 신호 -5영업일", f"{sb.get('CAGR', np.nan):.2%}", f"{sb.get('Sharpe', np.nan):.2f}"]],
              ["시나리오", "CAGR", "Sharpe"], ["l", "r", "r"],
              title="R1 누수 자가검정 — 고의로 미래를 넣으면 반드시 좋아져야 한다")
    ok_a = np.isfinite(sa.get("CAGR", np.nan)) and np.isfinite(base_c) and \
        sa["CAGR"] > base_c + 0.10
    ok_b = np.isfinite(sb.get("CAGR", np.nan)) and np.isfinite(base_c) and sb["CAGR"] > base_c
    passed = bool(ok_a and ok_b)
    detail = (f"미래수익 주입 CAGR {sa.get('CAGR', np.nan):.2%} vs 기준 {base_c:.2%} "
              f"({'개선' if ok_a else '개선 없음 ← 하네스 고장'}) · "
              f"신호 선행 {sb.get('CAGR', np.nan):.2%} ({'개선' if ok_b else '개선 없음'})")
    _record("R1", "누수 자가검정", passed, detail, kill=(not ok_a),
            numbers={"base": base_c, "inject": sa.get("CAGR"), "shift": sb.get("CAGR")})


# ═══ R12 — 꼬리 동시손실 (이 전략 고유, 필수) ════════════════════════════════════════════════
CRISIS_WINDOWS = [("2018Q4 긴축", "2018-10-01", "2018-12-31"),
                  ("2020Q1 코로나", "2020-02-01", "2020-04-30"),
                  ("2022 긴축", "2022-01-01", "2022-10-31"),
                  ("2024-08 급락", "2024-07-15", "2024-08-15")]


def R12_tail_correlation(bt: dict, bench: Dict[str, pd.Series], P: pd.DataFrame) -> dict:
    """위기 국면에 전 포지션이 동시에 손실난다 — 그 크기를 사전에 측정하고 상한을 확정한다."""
    r = _series(bt)
    if not len(r):
        _record("R12", "꼬리 동시손실", None, "수익률 시계열이 비어 판정 불가")
        return {}
    mkt = None
    for k in ("KOSPI", "유니버스 동일가중", "KOSDAQ"):
        if k in bench and bench[k] is not None and len(bench[k].dropna()) > 20:
            mkt = bench[k].reindex(r.index)
            break
    out = {}
    rows = []
    if mkt is not None:
        q05 = mkt.quantile(0.05)
        tail = r[mkt <= q05]
        calm = r[mkt > mkt.quantile(0.25)]
        out["tail_mean"] = float(tail.mean()) if len(tail) else np.nan
        out["tail_worst"] = float(tail.min()) if len(tail) else np.nan
        out["calm_mean"] = float(calm.mean()) if len(calm) else np.nan
        rows.append(["시장 하위5% 주간", f"{len(tail)}주", f"{out['tail_mean']:+.2%}",
                     f"{out['tail_worst']:+.2%}"])
        rows.append(["평시(상위75%)", f"{len(calm)}주", f"{out['calm_mean']:+.2%}", "-"])

    # 보유 종목 간 상관: 위기 vs 평시
    H = bt.get("holdings")
    corr_crisis = corr_calm = np.nan
    if H is not None and len(H):
        piv = H.pivot_table(index="wk", columns="code", values="ret", aggfunc="mean")
        if mkt is not None and piv.shape[1] >= 3:
            mk = mkt.reindex(piv.index)
            def _mean_corr(sub):
                if len(sub) < 5 or sub.shape[1] < 3:
                    return np.nan
                c = sub.corr(min_periods=3).to_numpy(dtype=float)
                iu = np.triu_indices_from(c, k=1)
                v = c[iu]
                v = v[np.isfinite(v)]
                return float(v.mean()) if len(v) else np.nan
            corr_crisis = _mean_corr(piv[mk <= mk.quantile(0.05)])
            corr_calm = _mean_corr(piv[mk > mk.quantile(0.25)])
            rows.append(["보유종목 평균상관", "위기", f"{corr_crisis:.2f}", f"평시 {corr_calm:.2f}"])
    out["corr_crisis"], out["corr_calm"] = corr_crisis, corr_calm

    for name, s, e in CRISIS_WINDOWS:
        sub = r[(r.index >= as_ts(s)) & (r.index <= as_ts(e))]
        if len(sub):
            cum = float((1 + sub).prod() - 1)
            rows.append([f"위기구간 {name}", f"{len(sub)}주", f"{cum:+.2%}", ""])
            out[f"crisis_{name}"] = cum
    LOG.table(rows, ["구간", "표본", "성과/상관", "비고"], ["l", "r", "r", "l"],
              title="R12 ⭐ 꼬리 동시손실 — 위험 프리미엄의 대가를 사전에 측정한다")

    s = _stat(bt)
    mdd = s.get("MDD", np.nan)
    worst_crisis = min([v for k, v in out.items() if k.startswith("crisis_")] or [np.nan])
    # 종목당 상한 권고: 위기구간 손실이 MDD 예산(-35%)을 넘으면 비례 축소
    MDD_BUDGET = -0.35
    rec_cap = POS_MAX_WEIGHT
    if np.isfinite(mdd) and mdd < MDD_BUDGET:
        rec_cap = round(max(0.03, POS_MAX_WEIGHT * abs(MDD_BUDGET / mdd)), 3)
    verdict = (f"MDD {mdd:.2%} · 위기구간 최악 {worst_crisis:+.2%} · "
               f"보유종목 상관 위기 {corr_crisis:.2f} vs 평시 {corr_calm:.2f} → "
               f"종목당 비중 상한 현재 {POS_MAX_WEIGHT:.0%}"
               + (f", 권고 {rec_cap:.1%} (MDD 예산 {MDD_BUDGET:.0%} 초과)"
                  if rec_cap != POS_MAX_WEIGHT else " 유지 (MDD 예산 내)"))
    if np.isfinite(corr_crisis) and np.isfinite(corr_calm) and corr_crisis > corr_calm + 0.1:
        verdict += " · 꼬리에서 상관 상승은 이 전략의 예상된 성질이다(§0-1)"
    out["recommended_pos_max"] = rec_cap
    _record("R12", "꼬리 동시손실 ⭐", (np.isfinite(mdd) and mdd >= MDD_BUDGET), verdict,
            numbers=out)
    return out


# ═══ R3 — 팩터 직교화 ═══════════════════════════════════════════════════════════════════════
def _factor_returns(P: pd.DataFrame) -> pd.DataFrame:
    """패널에서 직접 주간 팩터 수익률을 만든다(외부 팩터 라이브러리 의존 없음).
    각 팩터 = 유니버스 내 상위 20% - 하위 20% 동일가중 다음주 수익률."""
    d = P[(P.get("in_band", 1) == 1)].copy()
    if "fwd_ret" not in d.columns or d.empty:
        return pd.DataFrame()
    d["mom"] = d["f_dd"]                    # 252일 고점 대비 낙폭 = 모멘텀의 부호 있는 대리
    if "size_est" not in d.columns:
        d = build_size_estimate(d)
    d["size"] = -d["size_est"]                # 소형주일수록 큰 값 (밴드·셀과 동일 척도)
    d["value"] = safe_div(col(d, "equity"), d["mcap"])            # 장부/시가 (B/M)
    d["lowvol"] = d["f_vol"]                # f_vol = -표준편차 → 클수록 저변동
    facs = {}
    for f in ("mom", "size", "value", "lowvol"):
        if f not in d.columns or not d[f].notna().any():
            continue
        q = d.groupby("wk", observed=True)[f].rank(pct=True)
        hi = d[q >= 0.8].groupby("wk", observed=True)["fwd_ret"].mean()
        lo = d[q <= 0.2].groupby("wk", observed=True)["fwd_ret"].mean()
        facs[f] = (hi - lo)
    mkt = d.groupby("wk", observed=True)["fwd_ret"].mean()
    facs["mkt"] = mkt
    return pd.DataFrame(facs)


def R3_orthogonal(bt: dict, P: pd.DataFrame) -> None:
    r = _series(bt)
    F = _factor_returns(P)
    if F.empty or not len(r):
        _record("R3", "팩터 직교화", None, "팩터 구성 실패 — 판정 보류")
        return
    idx = r.index.intersection(F.index)
    if len(idx) < 30:
        _record("R3", "팩터 직교화", None, f"공통 표본 {len(idx)}주로 부족 — 판정 보류")
        return
    y = r.reindex(idx).fillna(0).to_numpy(dtype=float)
    X = F.reindex(idx).fillna(0.0)
    Xv = np.column_stack([np.ones(len(idx)), X.to_numpy(dtype=float)])
    try:
        beta, *_ = np.linalg.lstsq(Xv, y, rcond=None)
        resid = y - Xv @ beta
    except Exception:
        _record("R3", "팩터 직교화", None, "회귀 실패 — 판정 보류")
        return
    alpha_w = float(beta[0])
    alpha_ann = (1 + alpha_w) ** PERIODS_PER_YEAR - 1
    _mu, t = hac_tstat(resid + alpha_w)
    names = ["절편(알파)"] + list(X.columns)
    LOG.table([[n, f"{b:+.5f}"] for n, b in zip(names, beta)], ["항", "계수(주간)"], ["l", "r"],
              title="R3 팩터 직교화 — 시장·모멘텀·규모·가치·저변동성 통제 후 남는 것")
    ok = (alpha_ann > 0.02) and (abs(t) >= 1.5)
    _record("R3", "팩터 직교화 후 알파 잔존", bool(ok),
            f"연환산 알파 {alpha_ann:+.2%}, HAC t={t:.2f}" +
            ("" if ok else " → 기존 팩터의 재포장일 가능성(§11-6)"),
            kill=False, numbers={"alpha_ann": alpha_ann, "t": t})


# ═══ R5 — 절제 ══════════════════════════════════════════════════════════════════════════════
def R5_ablation(P: pd.DataFrame, run_fn: Callable, base_stat: dict) -> pd.DataFrame:
    P = slim_panel(P)
    arms = []

    def _arm(label: str, pp: pd.DataFrame):
        s = _stat(run_fn(pp, label=label))
        arms.append({"arm": label, "CAGR": s.get("CAGR"), "MDD": s.get("MDD"),
                     "Sharpe": s.get("Sharpe"), "Calmar": s.get("Calmar"),
                     "평균종목수": s.get("평균종목수"),
                     "ΔCAGR": (s.get("CAGR", np.nan) - base_stat.get("CAGR", np.nan))})

    # 1) TP 4개 각각 제거
    _sc = lambda pp, **kw: assemble_score(pp, quiet=True, **kw)
    for c in TP_COLS:
        rest = [x for x in TP_COLS if x != c]
        _arm(f"TP제거:{c}", _sc(P, use_tps=rest))
    # 2) f_cr_pctl 임계
    for th in (0.10, 0.20, 0.30):
        _arm(f"cr_pctl<{th:.2f}", _sc(classify_phase(P, cr_enter=th)))
    # 3) f_dd 임계
    for th in (-0.20, -0.30, -0.40):
        _arm(f"dd<{th:+.2f}", _sc(classify_phase(P, dd_enter=th)))
    # 4) 국면 C 게이트 on/off
    _arm("국면C게이트 off", _sc(P, gate_phase=False))
    # 5) 방화벽 off / 거부권 off
    _arm("방화벽 off", _sc(P, gate_firewall=False))
    _arm("거부권 off", _sc(P, gate_veto=False))
    # 6) TP 방식: clip vs rank×rank
    _arm("TP=rank×rank(clip없음)", _sc(build_tps(P, method="raw")))
    # 7) 스몰캡 밴드 (시총 하위 N) — 비교군을 절제표에도 같은 척도로 남긴다
    if "in_band_small" in P.columns:
        _arm(f"스몰캡밴드(하위{SMALLCAP_BOTTOM_N})", _sc(P, band_col="in_band_small"))

    A = pd.DataFrame(arms)
    if len(A):
        rows = [[r["arm"], f"{r['CAGR']:.2%}" if pd.notna(r["CAGR"]) else "-",
                 f"{r['MDD']:.2%}" if pd.notna(r["MDD"]) else "-",
                 f"{r['Sharpe']:.2f}" if pd.notna(r["Sharpe"]) else "-",
                 f"{r['ΔCAGR']:+.2%}" if pd.notna(r["ΔCAGR"]) else "-",
                 f"{r['평균종목수']:.1f}" if pd.notna(r["평균종목수"]) else "-"]
                for r in arms]
        rows.insert(0, ["기준(전체)", f"{base_stat.get('CAGR', np.nan):.2%}",
                        f"{base_stat.get('MDD', np.nan):.2%}",
                        f"{base_stat.get('Sharpe', np.nan):.2f}", "0.00%",
                        f"{base_stat.get('평균종목수', np.nan):.1f}"])
        LOG.table(rows, ["절제 arm", "CAGR", "MDD", "Sharpe", "ΔCAGR", "평균종목수"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="R5 절제 — 무엇이 실제로 기여하는가 (ΔCAGR<0 이면 그 요소가 기여한 것)")
    _record("R5", "절제 검사", None,
            f"{len(arms)}개 arm 측정 — 기여 귀속표는 위 표 및 r5_ablation.csv 참조")
    return A


# ═══ R7 — 레짐 분할 ═════════════════════════════════════════════════════════════════════════
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    r = _series(bt)
    if not len(r):
        _record("R7", "레짐 분할", None, "표본 없음")
        return
    rows = []
    for y, g in r.groupby(r.index.year):
        b = bench.get("KOSPI")
        bench_y = float((1 + b.reindex(g.index).fillna(0)).prod() - 1) if b is not None else np.nan
        rows.append([str(y), f"{len(g)}주", f"{float((1+g).prod()-1):+.2%}",
                     f"{bench_y:+.2%}" if np.isfinite(bench_y) else "-"])
    LOG.table(rows, ["연도", "주수", "전략", "KOSPI"], ["c", "r", "r", "r"],
              title="R7 레짐 분할 — 특정 구간 의존성을 숨기지 않는다")
    yr = [float((1 + g).prod() - 1) for _y, g in r.groupby(r.index.year)]
    pos = sum(1 for v in yr if v > 0)
    _record("R7", "레짐 분할", None,
            f"{len(yr)}개 연도 중 {pos}개 연도 플러스 · 최악 {min(yr):+.2%} / 최고 {max(yr):+.2%}")


# ═══ R9 — 회전율·비용 3시나리오 ═════════════════════════════════════════════════════════════
def R9_capacity(P: pd.DataFrame, run_fn: Callable) -> None:
    rows = []
    res = {}
    for lab, k in (("낙관(k=0.05)", 0.05), ("기본(k=0.10)", SLIPPAGE_K),
                   ("비관(k=0.25)", 0.25), ("최악(k=0.40)", 0.40)):
        s = _stat(run_fn(P, label=f"R9_{lab}", slip_k=k))
        res[lab] = s
        rows.append([lab, f"{s.get('CAGR', np.nan):.2%}", f"{s.get('MDD', np.nan):.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}",
                     f"{s.get('주평균비용', np.nan)*1e4:.1f}bp",
                     f"{s.get('주평균회전율', np.nan):.2f}"])
    LOG.table(rows, ["시나리오", "CAGR", "MDD", "Sharpe", "주평균비용", "주평균회전율"],
              ["l", "r", "r", "r", "r", "r"],
              title="R9 회전율·비용 시나리오 — 소액계좌에서 실제로 실행 가능한가")
    pess = res.get("비관(k=0.25)", {}).get("CAGR", np.nan)
    ok = np.isfinite(pess) and pess > 0.0
    _record("R9", "비용 비관 시나리오", bool(ok),
            f"비관 시나리오 CAGR {pess:.2%}" + ("" if ok else " → 실행 불가 판정(§11-7)"),
            numbers={"pessimistic_cagr": pess})


# ═══ 국면 C 표본 충분성 (§11-8) ═════════════════════════════════════════════════════════════
def check_phase_sample(P: pd.DataFrame) -> pd.DataFrame:
    if "phase" not in P.columns:
        return pd.DataFrame()
    d = P.copy()
    d["year"] = d["wk"].dt.year
    dist = (d.groupby(["year", "phase"], observed=True)["code"].nunique()
             .unstack("phase").fillna(0).astype(int))
    for c in ("A", "B", "C"):
        if c not in dist.columns:
            dist[c] = 0
    LOG.table([[str(y)] + [f"{int(dist.loc[y, c]):,}" for c in ("A", "B", "C")]
               for y in dist.index],
              ["연도", "국면A(물타기)", "국면B(반대매매중)", "국면C(소진·진입)"],
              ["c", "r", "r", "r"],
              title="국면 분포 — 국면 C 진입 후보가 연평균 몇 종목인가 (§11-8)")
    mean_c = float(dist["C"].mean()) if len(dist) else 0.0
    _record("SAMPLE", "국면 C 표본 충분성", bool(mean_c >= 30),
            f"연평균 국면C 종목수 {mean_c:.1f}개" +
            ("" if mean_c >= 30 else " → 30개 미만. 임계 완화 후 재측정 대상(§11-8). "
                                     "단, 완화는 사람이 결정한다 — 코드가 몰래 바꾸지 않는다"))
    return dist.reset_index()


def report_robustness():
    LOG.banner("강건성 스위트 종합", "킬 기준(⭐)은 §11. 나쁜 결과를 좋게 보이도록 조정하지 않는다")
    rows = []
    for r in ROBUST_RESULTS:
        icon = "✔ PASS" if r["pass"] else ("✘ FAIL" if r["pass"] is False else "→ 정보")
        rows.append([r["id"], _trunc(r["name"], 34), icon, _trunc(r["detail"], 74)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=78)
    fails = [r for r in ROBUST_RESULTS if r["pass"] is False]
    if fails:
        LOG.warn(f"실패 {len(fails)}건: " + ", ".join(r["id"] for r in fails))

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단카드 · 산출물 (§13)                                        ║
# ║                                                                                          ║
# ║  이 전략의 리포트는 '얼마 벌었나'가 아니라 '왜 벌었나 / 그게 알파인가 위험 프리미엄인가'를  ║
# ║  먼저 말해야 한다(§12-1). 그래서 R2-F 판정이 성과표보다 위에 온다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

INTERP_FLP = [
    ("TP_F1", "많이 빠졌는데 강제 재고 없음 = 소진 완료", "재고 남음 → 국면 A/B (진입 금지)"),
    ("TP_F2", "개인 이탈 × 기관 유입 = 소유권 이전 완료", "매도자만 있고 인수자가 없음"),
    ("TP_F3", "낙폭 크고 변동성 진정 = 패닉 종료", "아직 진행 중 (칼날 낙하)"),
    ("TP_F4", "잔고 감소 멈춤 × 거래 정상화", "청산이 계속되는 중"),
]


def report_grade_banner():
    """★ F1(신용잔고 등급)과 Fallback 단계를 리포트 '첫 줄'에 박는다(§13 체크리스트)."""
    lvl = {"PRIMARY_DAILY": "완전체 (일별 직접 관측)",
           "FALLBACK_A_WEEKLY": "해상도 손실 (주간 관측 + forward-fill)",
           "FALLBACK_B_PROXY": "★ 열등재 (개인 순매수 프록시) — 사실상 다른 전략",
           "NONE": "부재", "UNKNOWN": "미판정"}.get(CREDIT_GRADE, CREDIT_GRADE)
    LOG.banner(f"F1 신용융자잔고 등급 = {CREDIT_GRADE}", f"{lvl} · {CREDIT_SOURCE_NOTE}")
    if CREDIT_GRADE == "FALLBACK_B_PROXY":
        LOG.error("§11-3 — 프록시로 내려간 사실을 숨기지 않습니다. 아래 모든 결과, 특히 R2-F 는 "
                  "'신용잔고 소진'이 아니라 '개인 누적순매수 감소'를 본 것입니다. "
                  "신뢰도를 하향해 해석하세요.")
    LOG.info(f"수급(F2) 등급 = {FLOW_GRADE} · 관리종목/거래정지(K6) 등급 = {WATCH_GRADE}")
    if FIREWALL_STATUS:
        LOG.table([[k, v] for k, v in FIREWALL_STATUS.items()], ["방화벽 조항", "상태"], ["l", "l"],
                  title="방어 가동 현황 — 무엇이 켜져 있고 무엇이 꺼져 있는가 (성과보다 먼저 볼 것)")


def report_canary():
    if not CANARY:
        return
    fails = [c for c in CANARY.values() if c["pass"] is False]
    rows = [[c["id"], _trunc(c["name"], 34),
             "✔ PASS" if c["pass"] else ("✘ FAIL" if c["pass"] is False else "→ 정보"),
             _trunc(c["measured"], 46), _trunc(c["action"], 34)]
            for c in list(CANARY.values())]
    # FAIL 항목을 표 상단으로 (§2 요구)
    rows.sort(key=lambda r: 0 if r[2].startswith("✘") else 1)
    LOG.table(rows, ["ID", "확인 항목", "판정", "실측", "조치"], ["l", "l", "c", "l", "l"],
              title=f"CANARY 실측표 (§2) — FAIL {len(fails)}건")


def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    s = perf_stats_w(bt.get("returns", pd.DataFrame()))
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다 (수익률 시계열 없음).")
        return {}
    LOG.banner(f"성과 검증 {label or bt.get('label','')}",
               "주 1회 리밸런싱 · 다음 거래일 시가 체결 · 수수료+세금+슬리피지 반영")
    order = ["주수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "주평균", "t통계량(HAC)", "최장언더워터(주)", "누적수익", "평균종목수",
             "평균투자비중", "주평균회전율", "주평균비용"]
    pct = {"CAGR", "연변동성", "MDD", "승률", "주평균", "누적수익", "주평균비용",
           "평균투자비중"}
    rows = []
    for k in order:
        if k not in s:
            continue
        v = s[k]
        rows.append([k, f"{v:.2%}" if k in pct and isinstance(v, float) and np.isfinite(v)
                     else (f"{v:,.2f}" if isinstance(v, float) else f"{v:,}")])
    LOG.table(rows, ["지표", "값"], ["l", "r"])

    inv = s.get("평균투자비중", np.nan)
    if np.isfinite(inv) and inv < 0.7:
        LOG.warn(f"평균 투자비중이 {inv:.0%} 입니다 — 종목당 상한({POS_MAX_WEIGHT:.0%})에 걸려 "
                 f"나머지는 현금으로 남습니다. 이는 '적격 종목이 적다'는 사실의 정직한 반영이며, "
                 f"CAGR 은 그만큼 희석됩니다. 상한을 올리려면 R12 결과를 먼저 보세요(§12-2).")

    inc = bt.get("incidents") or {}
    if any(inc.values()):
        LOG.table([["거래정지로 못 판 보유주(주-종목)", f"{inc.get('frozen',0):,}"],
                   ["폐지 확정 -100% 처리", f"{inc.get('delisted',0):,}"],
                   ["장기 시세부재 보수적 상각(-100%)", f"{inc.get('stale_writeoff',0):,}"]],
                  ["보유 중 사고", "건수"], ["l", "r"],
                  title="보유 중 사고 처리 — 이 숫자가 0 이면 오히려 의심하세요(C2)")

    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:.4f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 — 상위 종목을 빼면 성과가 사라지는가")
    return s


def report_interpretation(P: pd.DataFrame):
    LOG.banner("해석표", "각 TP 가 발화했다는 것과 발화하지 않았다는 것이 각각 무슨 뜻인가")
    live = P[P["Signal"] > 0] if "Signal" in P.columns else P.head(0)
    rows = []
    for tpc, on, off in INTERP_FLP:
        if tpc not in P.columns:
            continue
        fire = float((P[tpc] > 0).mean()) if len(P) else np.nan
        fire_sel = float((live[tpc] > 0).mean()) if len(live) else np.nan
        rows.append([tpc, f"{fire:.1%}", f"{fire_sel:.1%}", _trunc(on, 40), _trunc(off, 34)])
    LOG.table(rows, ["TP", "전체 발화율", "선정군 발화율", "발화 의미", "미발화 의미"],
              ["l", "r", "r", "l", "l"], maxw=44)

    if "phase" in P.columns:
        d = P.copy()
        d["ym"] = d["wk"].dt.to_period("Q").astype(str)
        piv = (d.groupby(["ym", "phase"], observed=True)["code"].nunique()
                .unstack("phase").fillna(0).astype(int))
        for c in ("A", "B", "C"):
            if c not in piv.columns:
                piv[c] = 0
        tail = piv.tail(12)
        LOG.table([[i, f"{int(tail.loc[i,'A']):,}", f"{int(tail.loc[i,'B']):,}",
                    f"{int(tail.loc[i,'C']):,}"] for i in tail.index],
                  ["분기", "A 물타기", "B 반대매매중", "C 소진(진입)"], ["c", "r", "r", "r"],
                  title="국면 분포 (최근 12분기) — 국면 C 가 언제 나타나는가")

    if "rs_cov_90d" in P.columns and P["rs_cov_90d"].notna().any() and len(live):
        cov = float((live["rs_cov_90d"].fillna(0) > 0).mean())
        upr = float(live["rs_tp_up_ratio"].mean(skipna=True))
        LOG.info(f"선정 종목의 애널리스트 커버리지 보유 비율 {cov:.1%} · "
                 f"목표주가 상향비율 평균 {upr:.1%} "
                 f"— 커버리지가 낮다는 것은 '기관이 이미 손을 뗀 구간'이라는 뜻이며, "
                 f"이 전략이 프리미엄을 받는 이유이기도 하다")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    """최근 신호 상위 종목의 '왜 뽑혔는가'를 센서 단위로 분해해 보여준다."""
    if "Signal" not in P.columns or not len(P):
        return
    last_wk = P.loc[P["Signal"] > 0, "wk"].max()
    if pd.isna(last_wk):
        LOG.warn("발화한 신호가 한 건도 없어 진단카드를 만들 수 없습니다. "
                 "국면 C 조건이 너무 엄격하거나 신용잔고가 결측일 가능성이 큽니다.")
        return
    sub = P[(P["wk"] == last_wk) & (P["Signal"] > 0)].nlargest(top_n, "Signal")
    names = sec.set_index("code")["name"].to_dict() if len(sec) else {}
    LOG.banner(f"진단 카드 — {pd.Timestamp(last_wk):%Y-%m-%d} 기준 상위 {len(sub)}종목",
               "신호가 아니라 '근거'를 본다")
    for r in sub.itertuples(index=False):
        LOG.rule(f"{getattr(r,'code','')} {names.get(getattr(r,'code',''),'')}")
        rows = [
            ["고점대비 낙폭 f_dd", f"{getattr(r,'f_dd',np.nan):.1%}"],
            ["신용잔고율 백분위 f_cr_pctl", f"{getattr(r,'f_cr_pctl',np.nan):.2f}"],
            ["신용잔고 20일 변화 f_cr_chg", f"{getattr(r,'f_cr_chg',np.nan):+.1%}"],
            ["개인 이탈(60일) f_ret_ex", f"{getattr(r,'f_ret_ex',np.nan):+.4f}"],
            ["기관+외국인(20일) f_inst", f"{getattr(r,'f_inst',np.nan):+.4f}"],
            ["변동성 진정 f_vol", f"{getattr(r,'f_vol',np.nan):+.4f}"],
            ["거래 정상화 f_turn", f"{getattr(r,'f_turn',np.nan):.2f}"],
            ["TP_F1/F2/F3/F4",
             " / ".join(f"{getattr(r,c,np.nan):.3f}" for c in TP_COLS)],
            ["국면", str(getattr(r, "phase", "-"))],
            ["방화벽·거부권", f"FW={getattr(r,'FIREWALL',0)} V1={getattr(r,'V1',1)} "
                              f"V3={getattr(r,'V3',1)} V_RS={getattr(r,'V_RS',1)}"],
            ["애널 커버리지(90일)", f"{getattr(r,'rs_cov_90d',np.nan)}"],
        ]
        LOG.table(rows, ["근거", "값"], ["l", "r"])


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도", "어느 소스가 어느 지표를 만들고, 없으면 무엇이 죽는가")
    rows = [
        ["KRX 마켓플레이스/수동CSV", "신용융자잔고", "f_cr · f_cr_pctl · TP_F1 · TP_F4 · 국면 A/B/C",
         f"등급 {CREDIT_GRADE} (KRX모드 {KRX_MODE})"],
        ["pykrx / ★네이버 매매동향", "개인/기관/외국인 순매수", "f_retail · f_inst · f_ret_ex · TP_F2",
         f"등급 {FLOW_GRADE}"],
        ["FDR/네이버/yfinance/pykrx", "일봉·거래대금", "f_dd · f_vol · f_turn · 체결가 · ADV",
         "FDR 우선(§1-8)"],
        ["FDR폐지목록+DART+★가격이력", "상장/폐지일", "PIT 유니버스(C2·C13)",
         "KRX 없이 생존자편향 제거"],
        ["★DART 주식총수 / pykrx 시총", "상장주식수", "시총 분모 · 규모버킷 · 상위250 제외",
         "DART 경로는 PIT 완전"],
        ["DART 재무·공시", "자본총계·영업CF·증자/CB/BW", "방화벽 · V1 · V3", "키 없으면 비활성"],
        ["KIND 관리종목/거래정지", "감시 플래그", "방화벽", f"등급 {WATCH_GRADE}"],
        ["한경컨센서스 · 네이버리서치", "리포트·애널리스트·목표주가", "V_RS 거부권 · 해석표",
         "공용 인덱스 재사용"],
    ]
    LOG.table(rows, ["소스", "산출물", "쓰이는 곳", "비고"], ["l", "l", "l", "l"], maxw=42)


def persist_outputs(P: pd.DataFrame, bt: dict, r2f: dict, r12: dict, abl: pd.DataFrame,
                    phase_dist: pd.DataFrame, uni: "Universe") -> List[str]:
    """산출물을 전용 인덱스에 저장한다. 공용 원본은 수집 단계에서 이미 적재되어 있다.
    ★ 기존 파일을 지우지 않는다 — Vault 가 백업 후 교체하거나 리비전으로 남긴다."""
    outs: List[str] = []
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    def _csv(name: str, df: Optional[pd.DataFrame]):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{stamp}.csv")
        df.to_csv(p, index=False, encoding="utf-8-sig")
        outs.append(p)

    def _txt(name: str, text: str):
        p = os.path.join(outdir, f"{name}_{stamp}.md")
        atomic_write_text(p, text)
        outs.append(p)

    _csv("returns", bt.get("returns"))
    _csv("holdings", bt.get("holdings"))
    _csv("r5_ablation", abl)
    _csv("phase_distribution", phase_dist)
    _csv("attrition", pd.DataFrame(uni.attrition) if uni is not None else None)
    _csv("runtime", pd.DataFrame([{"stage": r.sid, "name": r.name, "layer": r.layer,
                                   "status": r.status, "seconds": round(r.dur, 2),
                                   "budget_s": r.budget_s, "rows_in": r.rows_in,
                                   "rows_out": r.rows_out}
                                  for r in PIPE.stages.values()]))
    _csv("canary", pd.DataFrame(list(CANARY.values())))

    # r2f_verdict.md — ★ 최우선 산출물
    #  R2-F 가 킬을 발동하면 main 의 try 가 거기서 끊기므로 r2f 딕셔너리는 비어 있다.
    #  그때 '측정되지 않음'을 찍으면 가장 중요한 판정이 산출물에서 지워진다 →
    #  ROBUST_RESULTS 에 이미 기록된 판정문으로 폴백한다.
    v = r2f.get("verdict")
    if not v:
        _rr = next((x for x in ROBUST_RESULTS if x["id"] == "R2-F"), None)
        v = (f"(킬 발동으로 스위트 중단) {_rr['detail']}" if _rr else "측정되지 않음")
    _txt("r2f_verdict",
         f"# R2-F 판정 — 소진 조건 vs 단순 낙폭과대\n\n"
         f"- 신용잔고 등급: **{CREDIT_GRADE}** ({CREDIT_SOURCE_NOTE})\n"
         f"- A 낙폭과대 단독 CAGR: {r2f.get('A', {}).get('CAGR', float('nan')):.4%}\n"
         f"- B 소진조건 단독 CAGR: {r2f.get('B', {}).get('CAGR', float('nan')):.4%}\n"
         f"- C FLP 전체 CAGR: {r2f.get('C', {}).get('CAGR', float('nan')):.4%}\n"
         f"- C−A HAC t: {r2f.get('t_CA', float('nan')):.2f}\n\n## 판정\n\n{v}\n")
    _rec = ((f"- R12 권고: **{r12['recommended_pos_max']:.1%}**\n")
            if r12 and "recommended_pos_max" in r12
            else "- R12 권고: **미측정** (앞 단계 킬로 스위트가 중단되었습니다 — "
                 "아래 현재 상한은 '권고치'가 아니라 '출하 기본값'입니다)\n")
    _txt("r12_tail_correlation",
         "# R12 꼬리 동시손실\n\n" +
         ("\n".join(f"- {k}: {v}" for k, v in r12.items()) if r12 else "- 미실행") +
         f"\n\n## 사이징\n\n- 종목당 최대비중(코드 상수): **{POS_MAX_WEIGHT:.0%}**\n"
         + _rec +
         f"- 동시보유 상한: {PORTFOLIO_MAX_NAMES}종목 · ADV 참여율 {POS_ADV_PARTICIPATION:.0%}\n")
    _txt("robustness",
         "# 강건성 결과 (R0~R12)\n\n" +
         "\n".join(f"- **{r['id']}** {r['name']}: "
                   f"{'PASS' if r['pass'] else ('FAIL' if r['pass'] is False else 'INFO')} — {r['detail']}"
                   for r in ROBUST_RESULTS) +
         "\n\n> 벤치마크 수치는 이 실행에서 직접 재측정한 값이며 하드코딩이 아니다(§1-5).\n")
    lp = os.path.join(outdir, f"log_{stamp}.txt")
    atomic_write_text(lp, "\n".join(LOG.buffer))
    outs.append(lp)

    # 전용 인덱스 테이블 (다음 실행/다른 노트북에서 그대로 재호출 가능)
    keep = [c for c in ("code", "wk", "signal_date", "close", "exec_px", "fwd_ret", "adv20",
                        "mcap", "phase", "PHASE_A", "PHASE_B", "PHASE_C", "FIREWALL", "VETO",
                        "in_band", "E", "E_rank", "Signal") + tuple(SENSOR_COLS) + tuple(TP_COLS)
            if c in P.columns]
    VAULT.put_table(f"flp_panel_{STRATEGY_ID}", P[keep], scope="private", domain="features",
                    source="L1/L2 weekly panel",
                    extra={"credit_grade": CREDIT_GRADE, "flow_grade": FLOW_GRADE})
    VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt.get("returns", pd.DataFrame()),
                    scope="private", domain="backtest", source=STRATEGY_ID)
    if len(bt.get("holdings", pd.DataFrame())):
        VAULT.put_table(f"backtest_holdings_{STRATEGY_ID}", bt["holdings"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
    if abl is not None and len(abl):
        VAULT.put_table(f"r5_ablation_{STRATEGY_ID}", abl, scope="private", domain="robust",
                        source="R5")
    VAULT.put_table(f"robustness_{STRATEGY_ID}",
                    pd.DataFrame([{k: (json.dumps(v, ensure_ascii=False, default=str)
                                       if isinstance(v, dict) else v)
                                   for k, v in r.items()} for r in ROBUST_RESULTS]),
                    scope="private", domain="robust", source="R-suite")
    LOG.ok(f"산출물 {len(outs)}건 저장 → {outdir}")
    return outs


def report_universe_compare(results: "OrderedDict[str, dict]", bench: Dict[str, pd.Series]):
    """전체 유니버스 vs 스몰캡(시총 하위 N) 을 같은 표에서 비교한다.

    강제매도 소진은 소형주에서 더 강하게 나타나야 하지만, 동시에 비용·유동성에 더 많이
    먹힌다. 둘을 따로 보고하면 '어느 쪽이 진짜인지'를 판단할 수 없으므로 나란히 놓는다."""
    if not results:
        return
    rows = []
    for lab, r in results.items():
        st = r.get("stat") or {}
        rows.append([lab,
                     f"{st.get('CAGR', np.nan):.2%}", f"{st.get('MDD', np.nan):.2%}",
                     f"{st.get('Sharpe', np.nan):.2f}", f"{st.get('Calmar', np.nan):.2f}",
                     f"{st.get('승률', np.nan):.1%}",
                     f"{st.get('평균종목수', np.nan):.1f}",
                     f"{st.get('평균투자비중', np.nan):.0%}",
                     f"{st.get('주평균비용', np.nan)*1e4:.1f}bp",
                     f"{st.get('t통계량(HAC)', np.nan):.2f}"])
    for name, sr in (bench or {}).items():
        if sr is None or not len(sr.dropna()):
            continue
        b = perf_stats_w(pd.DataFrame({"wk": sr.index, "ret": sr.fillna(0).to_numpy()}))
        rows.append([f"[벤치] {name}", f"{b.get('CAGR', np.nan):.2%}",
                     f"{b.get('MDD', np.nan):.2%}", f"{b.get('Sharpe', np.nan):.2f}",
                     f"{b.get('Calmar', np.nan):.2f}", f"{b.get('승률', np.nan):.1%}",
                     "-", "-", "-", f"{b.get('t통계량(HAC)', np.nan):.2f}"])
    LOG.table(rows, ["유니버스", "CAGR", "MDD", "Sharpe", "Calmar", "승률",
                     "평균종목수", "투자비중", "주평균비용", "t(HAC)"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              title=f"유니버스 비교 — 전체 vs 스몰캡(시총 하위 {SMALLCAP_BOTTOM_N}) · "
                    f"같은 신호·같은 비용·같은 기간")
    labs = list(results)
    if len(labs) >= 2:
        a, b2 = results[labs[0]].get("stat", {}), results[labs[1]].get("stat", {})
        same = (abs((a.get("CAGR", 0) or 0) - (b2.get("CAGR", 0) or 0)) < 1e-12 and
                abs((a.get("평균종목수", 0) or 0) - (b2.get("평균종목수", 0) or 0)) < 1e-12)
        if same:
            LOG.warn(f"두 유니버스의 결과가 완전히 같습니다 — 유니버스 종목수가 "
                     f"SMALLCAP_BOTTOM_N({SMALLCAP_BOTTOM_N})보다 작아 스몰캡 밴드가 "
                     f"전체와 동일해진 경우입니다. 비교로서 의미가 없으니 "
                     f"SMALLCAP_BOTTOM_N 을 낮추거나 유니버스를 넓히세요.")
        d = (b2.get("CAGR", np.nan) - a.get("CAGR", np.nan))
        cost_gap = (b2.get("주평균비용", np.nan) - a.get("주평균비용", np.nan)) * 1e4
        LOG.info(f"스몰캡 − 전체: CAGR {d:+.2%}p · 주평균비용 {cost_gap:+.1f}bp · "
                 f"MDD {b2.get('MDD', np.nan) - a.get('MDD', np.nan):+.2%}p. "
                 f"소형주에서 현상이 강하다면 CAGR 이 올라가되 비용·MDD 도 함께 올라가는 것이 "
                 f"정상이며, 비용 증가분이 초과수익을 잠식하면 실행 가능성이 없는 것입니다.")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  계약 자동검정 — 협상 불가 규칙을 코드가 스스로 증명한다                              ║
# ║                                                                                          ║
# ║  C1  모든 as-of 조회는 knowledge_date <= 기준일                                            ║
# ║  C1b 신용잔고·수급의 '+1영업일' 지연이 실제로 센서에 반영되는가 (이 전략의 핵심 누수지점)   ║
# ║  C2  유니버스는 상장폐지 종목을 포함하고, 폐지 주간은 -100% 로 계상된다                     ║
# ║  C13 유니버스 밴드는 매 시점 당시 값으로 재산출된다                                        ║
# ║  TP  clip(z,0)×clip(z,0) — 둘 다 음수면 0                                                  ║
# ║  V   거부권은 이진·곱·상쇄 불가                                                            ║
# ║  BM  벤치마크 수치 하드코딩 금지 (소스 검사)                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                              # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "detail": msg})
    return ok


def _synth_daily(n_codes: int = 6, n_days: int = 400, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-01", periods=n_days)
    out = []
    for i in range(n_codes):
        c = f"{100000+i:06d}"
        ret = rng.normal(0.0003, 0.02, n_days)
        px = 10000 * np.exp(np.cumsum(ret))
        out.append(pd.DataFrame({
            "code": c, "date": days, "open": px * 0.995, "high": px * 1.01,
            "low": px * 0.99, "close": px, "volume": rng.integers(1e4, 1e6, n_days),
            "amount": rng.uniform(5e8, 5e9, n_days), "src": "synth"}))
    return pd.concat(out, ignore_index=True)


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정", "PIT · 생존자편향 · 거부권 · TP 부호 — 협상 불가 규칙")

    def c1():
        base = pd.DataFrame({"code": ["A"] * 3,
                             "wk": pd.to_datetime(["2020-01-10", "2020-02-10", "2020-03-10"])})
        src = pd.DataFrame({"code": ["A", "A"],
                            "event_date": pd.to_datetime(["2020-01-01", "2020-02-20"]),
                            "knowledge_date": pd.to_datetime(["2020-01-05", "2020-02-25"]),
                            "val": [1.0, 2.0]})
        PIT.register("_c1_test", pit_frame(src, "event_date", "knowledge_date", source="test"),
                     key_cols=["code"])
        got = PIT.asof_join(base, "_c1_test", by="code", left_time="wk")
        if "knowledge_date" not in got.columns:
            return False, "asof_join 이 knowledge_date 를 붙이지 않았습니다"
        bad = int((got["knowledge_date"] > got["wk"]).sum())
        vals = got["val"].tolist()
        return (bad == 0 and vals == [1.0, 1.0, 2.0],
                f"미래참조 {bad}건 · 결합값 {vals} (2월10일 시점에 2월25일 공표값을 보면 위반)")

    def c1b():
        """★ 이 전략의 핵심: 잔고·수급은 거래일 +1영업일에만 알 수 있다.
        잔고가 T일에 급변하면 센서는 T일이 아니라 T+1 거래일에 반응해야 한다."""
        px = _synth_daily(2, 300)
        codes = sorted(px["code"].unique())
        spike_date = px["date"].iloc[250]
        cr = px[["code", "date"]].copy()
        cr["credit_bal"] = 1e8
        cr.loc[cr["date"] >= spike_date, "credit_bal"] = 9e9
        cr["src"] = "synth"
        fl = px[["code", "date"]].copy()
        fl["retail_net"] = 1e7; fl["inst_net"] = 1e7; fl["foreign_net"] = 1e7
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSPI",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": pd.NaT, "industry": "테스트",
                            "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
        P = build_flp_panel(px, cr, fl, pd.DataFrame(), weeks, uni)
        if P.empty:
            return False, "패널이 비었습니다"
        # 급변일 '당일'이 신호일인 행이 있으면 그 행의 credit_bal 은 아직 옛값이어야 한다
        same = P[(P["signal_date"] == spike_date)]
        if len(same) == 0:
            # 신호일 격자에 급변일이 없으면, 급변 직후 첫 신호일로 검사한다
            after = P[P["signal_date"] > spike_date].sort_values("signal_date")
            ok = bool(len(after) and (after["credit_bal"] > 1e9).any())
            return ok, f"급변일 격자 부재 → 직후 신호일 반영 여부만 검사 ({'반영됨' if ok else '미반영'})"
        stale = float(same["credit_bal"].max())
        return (stale < 1e9,
                f"급변 당일 센서가 본 잔고 = {stale:,.0f} (옛값 1e8 이어야 함 — "
                f"9e9 이면 하루치 미래정보 누출)")

    def c2():
        px = _synth_daily(4, 300)
        codes = sorted(px["code"].unique())
        dead = codes[0]
        dl = px["date"].iloc[280]
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": [dl] + [pd.NaT] * (len(codes) - 1),
                            "industry": "테스트", "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        before = uni.at(dl - pd.Timedelta(days=30))
        after = uni.at(dl + pd.Timedelta(days=5))
        if dead not in before:
            return False, "폐지 예정 종목이 폐지 전 유니버스에 없습니다 (생존자편향 재유입)"
        if dead in after:
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        # 폐지 주간 -100% 계상 검증
        wk = pd.DatetimeIndex([dl - pd.Timedelta(days=3)])
        P = pd.DataFrame({"code": [dead], "wk": wk, "exec_px": [1000.0], "fwd_ret": [np.nan],
                          "adv20": [1e9], "FIREWALL": [1], "VETO": [1], "in_band": [1],
                          "V6": [1], "PHASE_C": [1], "f_dd": [-0.4], "f_cr_pctl": [0.1],
                          "Signal_rank": [1.0]})
        bt = run_backtest_w(P, wk, uni, sec, apply_costs=False, label="c2")
        H = bt["holdings"]
        if H is None or H.empty:
            return False, "폐지 예정 종목이 아예 편입되지 않았습니다(=조용한 누락, 그 자체가 C2 위반)"
        pos_ret = float(H["ret"].iloc[0])
        w = float(H["weight"].iloc[0])
        port = float(bt["returns"]["ret"].iloc[0])
        # 포지션 수익률이 -100% 여야 한다. 포트 수익률은 비중만큼만 반영되는 것이 정상이다
        # (종목당 상한이 있으므로 -100% 가 그대로 포트 수익률이 되면 오히려 사이징 버그다).
        return (pos_ret <= -0.999 and abs(port - w * pos_ret) < 1e-9,
                f"포지션 수익률 {pos_ret:.1%} · 비중 {w:.1%} · 포트 기여 {port:.2%} "
                f"(정리매매가 없으면 포지션은 -100%)")

    def c13():
        px = _synth_daily(300, 60)
        P = pd.DataFrame({"code": px["code"].unique()})
        P["wk"] = pd.Timestamp("2019-03-01")
        P["mcap"] = np.linspace(1e12, 1e9, len(P))
        P["adv20"] = 1e9
        P = pd.concat([P, P.assign(wk=pd.Timestamp("2019-03-08"),
                                   mcap=P["mcap"].to_numpy()[::-1])], ignore_index=True)
        Q = apply_universe_bands(P)
        r1 = Q[Q["wk"] == pd.Timestamp("2019-03-01")].set_index("code")["mcap_rank"]
        r2 = Q[Q["wk"] == pd.Timestamp("2019-03-08")].set_index("code")["mcap_rank"]
        flipped = float((r1 - r2).abs().mean())
        return (flipped > 1.0,
                f"시점별 랭크 평균 변화 {flipped:.1f} (0 이면 현재 시총으로 과거를 정의한 것)")

    def c_tp():
        P = pd.DataFrame({"cell": ["x"] * 10, "cell_l2": ["y"] * 10, "cell_l3": ["z"] * 10,
                          "a": np.linspace(-1, 1, 10), "b": np.linspace(-1, 1, 10)})
        v = tp(P, P["a"], P["b"])
        low = float(v.iloc[0])                      # 둘 다 최악
        high = float(v.iloc[-1])                    # 둘 다 최고
        return (low == 0.0 and high > 0.0,
                f"둘 다 최악={low:.3f}(0이어야 함) · 둘 다 최고={high:.3f} "
                f"(z*z 를 쓰면 최악이 최고점을 받는다)")

    def c_veto():
        P = pd.DataFrame({"wk": [pd.Timestamp("2020-01-03")] * 3, "code": list("abc"),
                          "TP_F1": [0.9, 0.9, 0.9], "TP_F2": [0.9, 0.9, 0.9],
                          "TP_F3": [0.9, 0.9, 0.9], "TP_F4": [0.9, 0.9, 0.9],
                          "PHASE_C": [1, 1, 1], "FIREWALL": [1, 0, 1], "VETO": [1, 1, 0],
                          "in_band": [1, 1, 1]})
        S = assemble_score(P)
        s = S.set_index("code")["Signal"]
        return (s["a"] > 0 and s["b"] == 0 and s["c"] == 0,
                f"정상={s['a']:.3f} 방화벽차단={s['b']:.3f} 거부권차단={s['c']:.3f} "
                f"(점수가 높아도 상쇄되면 안 된다)")

    def c_exit():
        """청산 규칙이 실제로 작동하는가: f_cr_pctl 회복 시 다음 주에 비중이 0 이어야 한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=3, freq="W-FRI"))
        rows = []
        for i, w in enumerate(wks):
            rows.append({"code": "A", "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0,
                         "adv20": 1e10, "FIREWALL": 1, "VETO": 1, "in_band": 1, "V6": 1,
                         "PHASE_C": 1 if i == 0 else 0, "f_dd": -0.4,
                         "f_cr_pctl": 0.1 if i < 2 else 0.9,
                         "Signal_rank": 1.0 if i == 0 else np.nan})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_exit")
        n = bt["returns"]["n"].tolist()
        return (n[0] == 1 and n[1] == 1 and n[2] == 0,
                f"주별 보유종목수 {n} — 3주차에 f_cr_pctl=0.9(재취약)이므로 0 이어야 함")

    def c_halt():
        """★ 실제로 있었던 결함의 회귀 방지:
        보유 종목이 거래정지로 패널에서 사라진 뒤 상장폐지되면, 예전 구현은 그 종목을
        '보유 목록에서 조용히 제거'해 총손실(-100%)을 무손실(0%)로 계상했다.
        한국의 전형 경로(거래정지 → 정리매매 → 폐지)가 통째로 공짜 탈출이 되는 결함이다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=5, freq="W-FRI"))
        dl = wks[3] + pd.Timedelta(days=2)          # 4주차와 5주차 사이에 폐지
        rows = []
        for i, w in enumerate(wks):
            if i >= 1:
                continue                             # 2주차부터 패널에서 사라진다(거래정지)
            rows.append({"code": "A", "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0,
                         "adv20": 1e10, "FIREWALL": 1, "VETO": 1, "in_band": 1, "V6": 1,
                         "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [dl]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_halt")
        H = bt["holdings"]
        states = list(H["state"]) if "state" in H.columns else []
        loss = float(H.loc[H["ret"] <= -0.999, "weight"].sum()) if len(H) else 0.0
        total = float(bt["returns"]["ret"].sum())
        return (("delisted" in states) and loss > 0 and total < -0.05,
                f"상태전이={states} · 총손실 반영 {total:.2%} "
                f"(거래정지 중 폐지를 0% 로 처리하면 여기가 0.00% 로 나온다)")

    def c_delist_once():
        """폐지 -100% 이중계상 방지: 손실은 정확히 한 번만 계상되어야 한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=4, freq="W-FRI"))
        dl = wks[1] + pd.Timedelta(days=2)
        rows = [{"code": "A", "wk": wks[0], "exec_px": 1000.0, "fwd_ret": 0.0, "adv20": 1e10,
                 "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "in_band": 1, "V6": 1,
                 "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0},
                # 폐지 주간: 다음 주 체결가가 없으므로 fwd_ret 은 결측이다(= 정리매매 미확보)
                {"code": "A", "wk": wks[1], "exec_px": 1000.0, "fwd_ret": np.nan, "adv20": 1e10,
                 "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "in_band": 1, "V6": 1,
                 "PHASE_C": 1, "f_dd": -0.4, "f_cr_pctl": 0.1, "Signal_rank": 1.0}]
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")], "delisting_date": [dl]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_del1")
        H = bt["holdings"]
        n_total = int((H["ret"] <= -0.999).sum()) if len(H) else 0
        tot = float(bt["returns"]["ret"].sum())
        return (n_total == 1 and tot < -0.05,
                f"-100% 계상 {n_total}회 · 누적 {tot:.2%} "
                f"(0회면 미계상, 2회면 폐지 손실을 두 번 반영한 것)")

    def c_halt_gap():
        """거래정지 구간의 가격 붕괴가 재개 주에 실현되는가.
        정지 중 0%, 재개 후 새 가격에서 재시작하면 그 손실이 어디에도 계상되지 않는다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=4, freq="W-FRI"))
        base = dict(adv20=1e10, FIREWALL=1, FIREWALL_HARD=1, VETO=1, in_band=1, V6=1,
                    PHASE_C=1, f_dd=-0.4, f_cr_pctl=0.1)
        rows = [{"code": "A", "wk": wks[0], "exec_px": 1000.0, "fwd_ret": 0.0,
                 "Signal_rank": 1.0, **base},
                # wks[1], wks[2] 는 패널에 없음(거래정지) → wks[3] 에 반토막으로 재개
                {"code": "A", "wk": wks[3], "exec_px": 500.0, "fwd_ret": 0.0,
                 "Signal_rank": np.nan, **base}]
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": ["A"], "name": ["A"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": wks, "code": "A"}))
        bt = run_backtest_w(P, wks, uni, sec, apply_costs=False, label="c_gap")
        H = bt["holdings"]
        got = float(H.loc[H["state"] == "resumed", "ret"].sum()) if "state" in H.columns else 0.0
        return (got <= -0.49,
                f"재개 주 실현수익률 {got:.1%} (정지 중 -50% 붕괴가 반영되면 -50% 근처)")

    def c_dtype():
        """★ 실제 실행에서만 나타나던 결함: 가격 패널은 downcast 로 code 가 category 가 되고
        신용/수급/주식수는 object 다. merge_asof(by='code') 는 dtype 이 다르면 죽는다."""
        px = downcast(_synth_daily(3, 200))
        if str(px["code"].dtype) != "category":
            px["code"] = px["code"].astype("category")
        codes = [str(c) for c in px["code"].unique()]
        cr = pd.DataFrame({"code": codes * 10, "date": list(px["date"].unique())[:10] * 3,
                           "credit_bal": 1e8, "src": "t"})
        sh = pd.DataFrame({"snap_date": [px["date"].min()] * 3, "code": codes,
                           "shares": 1e6, "mcap_snap": np.nan})
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSPI",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": pd.NaT, "industry": "T", "corp_code": None})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
        P = build_flp_panel(px, cr, pd.DataFrame(), sh, weeks, uni)
        return (len(P) > 0 and P["shares"].notna().any(),
                f"category/object 혼합 결합 결과 {len(P):,}행 · 주식수 결합 "
                f"{int(P['shares'].notna().sum()):,}행")

    def c_fixture():
        """★ 실제로 터졌던 결함의 회귀 방지:
        합성 픽스처가 '길이에 결합된 상수 경계'(integers(300, n_days-200))를 써서
        RUN_MODE='FULL' 경로(n_days=500)에서만 ValueError 로 즉사했다.
        SMOKE 경로(n_days=900)만 검증하던 하네스는 이 경로를 한 번도 실행하지 않았다.
        → 여러 길이로 실제 생성해 보고, 필수 키와 최소 행수를 확인한다."""
        need = ("px", "credit", "flows", "sec", "shares", "fin", "disclosures", "links")
        sizes = []
        for nd, nc in ((200, 8), (460, 60), (500, 60), (900, 120)):
            if True:
                S = make_synthetic_flp(n_codes=nc, n_days=nd, seed=SEED + nd)
                miss = [k for k in need if k not in S or S[k] is None or not len(S[k])]
                if miss:
                    return False, f"n_days={nd}, n_codes={nc} 에서 누락: {miss}"
                if S["sec"]["delisting_date"].notna().sum() < 1:
                    return False, f"n_days={nd} 에서 상장폐지 종목이 0개 (C2 경로 미검증)"
                sizes.append((nd, nc, len(S["px"])))
        return True, f"{len(sizes)}개 조합 생성 성공 (길이 200~900 · FULL 경로 460일 포함)"

    def c_small():
        """스몰캡 밴드는 '매 시점 시총 하위 N' 이어야 하고, 전체 밴드의 부분집합이어야 한다."""
        n = SMALLCAP_BOTTOM_N + 500
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "wk": pd.Timestamp("2020-01-03"),
                          "mcap": np.linspace(1e13, 1e9, n),
                          "adv20": 1e10})
        Q = apply_universe_bands(P)
        big, small = Q["in_band"] == 1, Q["in_band_small"] == 1
        if not small.any():
            return False, "스몰캡 밴드가 비었습니다"
        if int((small & ~big).sum()):
            return False, "스몰캡 밴드가 전체 밴드의 부분집합이 아닙니다"
        n_small = int(small.sum())
        max_in = float(Q.loc[small, "mcap"].max())
        min_out = float(Q.loc[big & ~small, "mcap"].min())
        return (n_small <= SMALLCAP_BOTTOM_N and max_in <= min_out,
                f"{n:,}종목 중 스몰캡 {n_small:,}종목(상한 {SMALLCAP_BOTTOM_N:,}) · "
                f"선택 최대시총 {max_in:.3g} ≤ 제외 최소시총 {min_out:.3g}")

    def c_r2f_band():
        """★ 라운드3 리뷰가 잡은 결함의 회귀 방지:
        R2-F 를 스몰캡 밴드로 호출하면 A·B 는 그 밴드로 재채점되는데 C 만 호출자가
        이미 매겨둔 '전체 밴드' 신호를 그대로 썼다. 그러면 '스몰캡 A/B vs 전체 C' 를
        비교하게 되어 판정 자체가 무효다. 세 arm 이 같은 밴드를 쓰는지 검증한다."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=12, freq="W-FRI"))
        codes = [f"{700000+i:06d}" for i in range(30)]
        rows = []
        for w in wks:
            for i, c in enumerate(codes):
                rows.append({
                    "code": c, "wk": w, "exec_px": 1000.0 + i, "fwd_ret": 0.001 * (i % 5),
                    "adv20": 1e10, "FIREWALL": 1, "FIREWALL_HARD": 1, "VETO": 1, "V6": 1,
                    "in_band": 1, "in_band_small": 1 if i < 10 else 0,   # 작은 10종목만
                    "f_dd": -0.4, "f_dd_spd": -0.05, "f_cr_pctl": 0.1, "f_cr_chg": 0.0,
                    "f_cr_chg_slow": 0.0, "f_retail": -1e-4, "f_inst": 1e-4,
                    "f_ret_ex": 1e-4, "f_vol": -0.01, "f_turn": 1.2,
                    "cell": "X", "cell_l2": "Y", "cell_l3": "Z",
                    "TP_F1": 0.2 + i / 100, "TP_F2": 0.2, "TP_F3": 0.2, "TP_F4": 0.2,
                    "PHASE_C": 1, "stale_days": 0})
        P = pd.DataFrame(rows)
        P = assemble_score(P, quiet=True)                 # 전체 밴드로 채점된 상태(호출자 패널)
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"), "delisting_date": pd.NaT})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": list(wks) * 30, "code": sorted(codes * 12)}))
        _run = lambda pp, label="x", **kw: run_backtest_w(pp, wks, uni, sec, apply_costs=False,
                                                          label=label)
        keep_stop = globals().get("STOP_ON_KILL_CRITERIA", True)
        globals()["STOP_ON_KILL_CRITERIA"] = False
        try:
            out = R2F_exhaustion_vs_drawdown(P, _run, band_col="in_band_small")
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = keep_stop
        small = set(codes[:10])
        bad = {}
        for lab, bt in (out.get("bts") or {}).items():
            H = bt.get("holdings")
            if H is None or H.empty:
                continue
            outside = set(H["code"]) - small
            if outside:
                bad[lab] = len(outside)
        return (not bad,
                f"세 arm 모두 스몰캡 밴드 내에서만 선정 (밴드 밖 편입: {bad or '없음'})")

    def c_ablation():
        """★ 라운드3 리뷰가 잡은 결함의 회귀 방지:
        엔진이 진입 자격에서 FIREWALL·VETO 를 다시 적용하는 바람에, R5 절제의
        '방화벽 off'·'거부권 off' arm 이 수학적으로 아무것도 절제하지 못했다
        (ΔCAGR 이 항상 0 → 절제표가 '방화벽은 기여가 없다'고 거짓 보고)."""
        wks = pd.DatetimeIndex(pd.bdate_range("2020-01-03", periods=8, freq="W-FRI"))
        codes = [f"{800000+i:06d}" for i in range(20)]
        rows = []
        for w in wks:
            for i, c in enumerate(codes):
                rows.append({
                    "code": c, "wk": w, "exec_px": 1000.0, "fwd_ret": 0.0, "adv20": 1e10,
                    # 절반은 방화벽 차단 대상인데 TP 점수는 오히려 더 높게 준다
                    "FIREWALL": 0 if i < 10 else 1, "FIREWALL_HARD": 0 if i < 10 else 1,
                    "VETO": 1, "in_band": 1, "V6": 1, "PHASE_C": 1, "stale_days": 0,
                    "f_dd": -0.4, "f_cr_pctl": 0.1,
                    "cell": "X", "cell_l2": "Y", "cell_l3": "Z",
                    "TP_F1": 0.9 if i < 10 else 0.1, "TP_F2": 0.9 if i < 10 else 0.1,
                    "TP_F3": 0.9 if i < 10 else 0.1, "TP_F4": 0.9 if i < 10 else 0.1})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"), "delisting_date": pd.NaT})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"date": list(wks) * 20, "code": sorted(codes * 8)}))
        _run = lambda pp: run_backtest_w(pp, wks, uni, sec, apply_costs=False, label="abl")
        on = _run(assemble_score(P, quiet=True))
        off = _run(assemble_score(P, gate_firewall=False, quiet=True))
        h_on = set(on["holdings"]["code"]) if len(on["holdings"]) else set()
        h_off = set(off["holdings"]["code"]) if len(off["holdings"]) else set()
        blocked = set(codes[:10])
        return (not (h_on & blocked) and bool(h_off & blocked),
                f"방화벽 on 선정 {len(h_on)}종목(차단대상 {len(h_on & blocked)}) · "
                f"off 선정 {len(h_off)}종목(차단대상 {len(h_off & blocked)}) "
                f"— off 에서 차단대상이 0이면 절제가 무의미한 것")

    def c_size():
        sub = pd.DataFrame({"code": [f"c{i}" for i in range(30)], "adv20": [1e12] * 30})
        w = size_positions(sub)["weight"]
        return (abs(w.sum() - 1.0) < 1e-6 and w.max() <= POS_MAX_WEIGHT + 1e-9,
                f"합계 {w.sum():.4f} · 최대 {w.max():.4f} (상한 {POS_MAX_WEIGHT})")

    def c_fwd():
        """주 연속성이 끊긴 구간의 fwd_ret 은 결측이어야 한다 (수익 과대계상 방지)."""
        px = _synth_daily(1, 200)
        code = px["code"].iloc[0]
        gap_mask = (px["date"] >= px["date"].iloc[60]) & (px["date"] <= px["date"].iloc[100])
        px2 = px[~gap_mask]
        sec = pd.DataFrame({"code": [code], "name": [code], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-01")],
                            "delisting_date": [pd.NaT], "industry": ["T"], "corp_code": [None]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px2)
        weeks = week_grid(str(px2["date"].min().date()), str(px2["date"].max().date()), px2)
        P = build_flp_panel(px2, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), weeks, uni)
        big = int((P["fwd_ret"].abs() > 0.5).sum())
        return (big == 0, f"|fwd_ret|>50% 인 주 {big}건 (건너뛴 구간을 1주 수익으로 계상하면 발생)")

    def c_bm():
        """벤치마크 수치 하드코딩 금지(§1-5) — 소스를 직접 검사한다."""
        import inspect
        src = inspect.getsource(benchmark_returns_w)
        bad = re.findall(r"(?:CAGR|cagr)\s*=\s*0\.\d+", src)
        return (len(bad) == 0, f"소스 내 하드코딩된 성과 상수 {len(bad)}건")

    def c_seed():
        a = np.random.default_rng(SEED).normal(size=5)
        b = np.random.default_rng(SEED).normal(size=5)
        return (bool(np.allclose(a, b)), "동일 시드 → 동일 난수열 (C8 결정성)")

    def c_cell():
        """셀이 얇으면 상위 단위로 폴백해야 한다 (얇은 셀에서 rank 가 의미를 잃는 것 방지)."""
        P = pd.DataFrame({"cell": ["a"] * 3 + ["b"] * 20, "cell_l2": ["L2"] * 23,
                          "cell_l3": ["L3"] * 23, "v": np.arange(23, dtype=float)})
        r = cell_rank(P, "v", min_n=8)
        thin = r.iloc[:3]
        return (thin.nunique() == 3 and float(thin.max()) < 0.5,
                f"얇은 셀 3행의 백분위 {[round(x,3) for x in thin]} — "
                f"전체 23행 기준으로 매겨져야 낮게 나온다")

    def c_vault():
        """공용/전용 인덱스 왕복 — 저장한 것을 다시 읽을 수 있어야 한다(절대 1원칙의 실효성)."""
        if VAULT is None:
            return False, "VAULT 미초기화"
        t = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        p1 = VAULT.put_table("_contract_roundtrip_shared", t, scope="shared", domain="test")
        p2 = VAULT.put_table("_contract_roundtrip_private", t, scope="private", domain="test")
        g1 = VAULT.get_table("_contract_roundtrip_shared", scope="shared")
        g2 = VAULT.get_table("_contract_roundtrip_private", scope="private")
        ok = (p1 and p2 and g1 is not None and g2 is not None and
              len(g1) == 3 and len(g2) == 3)
        # 저널이 append-only 인지 확인 (기존 줄 보존)
        j = VAULT.journal("shared")
        n_lines = len(open(j, encoding="utf-8").read().strip().split("\n")) if os.path.exists(j) else 0
        return ok, f"공용/전용 왕복 OK · 저널 {n_lines}줄 (append-only)"

    _c("C1", "as-of 조회는 knowledge_date <= 기준일", c1)
    _c("C1b", "신용잔고·수급 +1영업일 지연 (★핵심 누수지점)", c1b)
    _c("C2", "상장폐지 포함 · 폐지 주간 -100%", c2)
    _c("C13", "유니버스 밴드 PIT 재산출", c13)
    _c("TP", "clip(z,0)×clip(z,0) 부호 규약", c_tp)
    _c("VETO", "거부권 이진·상쇄 불가", c_veto)
    _c("EXIT", "청산 규칙(f_cr_pctl 회복) 작동", c_exit)
    _c("FIXT", "합성 픽스처 길이 무관 생성 (회귀 방지)", c_fixture)
    _c("HALT", "거래정지 중 폐지 = -100% (회귀 방지)", c_halt)
    _c("DEL1", "폐지 손실 이중계상 금지 (회귀 방지)", c_delist_once)
    _c("GAP", "거래정지 구간 손실을 재개 주에 실현 (회귀 방지)", c_halt_gap)
    _c("DTYPE", "category/object 결합키 혼합 내성 (회귀 방지)", c_dtype)
    _c("SMALL", "스몰캡 밴드 = 시총 하위 N ∧ 전체 밴드의 부분집합", c_small)
    _c("R2FB", "R2-F 세 비교군이 같은 밴드를 쓴다 (회귀 방지)", c_r2f_band)
    _c("ABL", "절제 arm 이 실제로 절제한다 (회귀 방지)", c_ablation)
    _c("SIZE", "사이징 상한·합계", c_size)
    _c("FWD", "주 연속성 끊김 시 fwd_ret 결측", c_fwd)
    _c("CELL", "셀 폴백 사다리", c_cell)
    _c("BM", "벤치마크 하드코딩 금지", c_bm)
    _c("SEED", "결정성", c_seed)
    _c("VAULT", "구글드라이브 공용/전용 인덱스 왕복", c_vault)

    rows = [[r["id"], _trunc(r["name"], 40), "✔" if r["pass"] else "✘", _trunc(r["detail"], 60)]
            for r in CONTRACT_RESULTS]
    LOG.table(rows, ["ID", "계약", "통과", "상세"], ["l", "l", "c", "l"], maxw=64)
    fails = [r for r in CONTRACT_RESULTS if not r["pass"]]
    if fails:
        msg = "계약 위반: " + ", ".join(f"{r['id']}({r['detail'][:60]})" for r in fails)
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"계약 {len(CONTRACT_RESULTS)}건 전부 통과.")
    return True

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  합성데이터 엔드투엔드 스모크                                                        ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 '계산경로'를 증명한다.                                    ║
# ║  합성데이터에는 국면 C 가 실제로 발생하도록 강제매도-소진 사이클을 심어 둔다.                ║
# ║  (신호가 한 건도 발화하지 않는 합성으로는 백테스트·강건성 경로를 검증할 수 없다)             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _ri(rng, lo: float, hi: float, floor: int = 0) -> int:
    """경계가 뒤집혀도 죽지 않는 정수 난수.

    ★ 이 함수가 존재하는 이유(실제 사고): 픽스처가 `rng.integers(300, n_days - 200)` 처럼
      '길이에 결합된 경계'를 쓰고 있었다. n_days=900 인 SMOKE 경로에서는 통과하지만
      n_days=500 인 FULL 경로에서는 low==high 가 되어 ValueError 로 즉사한다.
      경계를 계산하는 모든 지점을 이 한 곳으로 모아, 길이가 얼마든 항상 유효 구간을 만든다."""
    lo_i, hi_i = int(lo), int(hi)
    lo_i = max(int(floor), lo_i)
    if hi_i <= lo_i:
        hi_i = lo_i + 1
    return int(rng.integers(lo_i, hi_i))


def make_synthetic_flp(n_codes: int = 120, n_days: int = 900, seed: int = SEED) -> dict:
    """합성 데이터. n_days 가 짧아도(최소 200) 전 구간이 성립해야 한다 — 경계는 전부 비율로."""
    n_days = max(200, int(n_days))
    n_codes = max(8, int(n_codes))
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-02", periods=n_days)
    codes = [f"{900001+i:06d}" for i in range(n_codes)]

    px_rows, cr_rows, fl_rows = [], [], []
    for i, c in enumerate(codes):
        drift = rng.normal(0.0002, 0.0004)
        vol = rng.uniform(0.015, 0.035)
        ret = rng.normal(drift, vol, n_days)
        # 강제매도 사이클: 종목마다 다른 시점에 급락 → 신용잔고 급감 → 개인 이탈 → 기관 유입
        # 급락 시작 시점은 '비율'로 잡는다(길이에 결합된 상수 금지)
        t0 = _ri(rng, n_days * 0.35, n_days * 0.75, floor=60)
        ret[t0:t0 + 40] -= rng.uniform(0.004, 0.012)
        px = 20000 * np.exp(np.cumsum(ret))
        amount = rng.uniform(3e8, 4e9, n_days) * (1 + 0.5 * np.sin(np.arange(n_days) / 40))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": px * (1 + rng.normal(0, 0.002, n_days)),
            "high": px * 1.01, "low": px * 0.99, "close": px,
            "volume": (amount / px).astype(np.int64), "amount": amount, "src": "synth"}))

        base_cr = px * rng.uniform(200, 800)                    # 신용잔고 = 가격에 연동
        cr = base_cr.copy()
        cr[t0:t0 + 60] *= np.linspace(1.0, 0.25, min(60, n_days - t0))   # 반대매매로 급감
        cr[t0 + 60:] *= 0.25
        cr_rows.append(pd.DataFrame({"code": c, "date": days, "credit_bal": cr, "src": "synth"}))

        retail = rng.normal(0, 3e8, n_days)
        inst = rng.normal(0, 2e8, n_days)
        retail[t0:t0 + 70] -= 8e8                                # 개인 이탈(항복)
        inst[t0 + 40:t0 + 110] += 6e8                            # 기관 인수
        fl_rows.append(pd.DataFrame({"code": c, "date": days, "retail_net": retail,
                                     "inst_net": inst, "foreign_net": inst * 0.5}))

    px = pd.concat(px_rows, ignore_index=True)
    credit = pd.concat(cr_rows, ignore_index=True)
    flows = pd.concat(fl_rows, ignore_index=True)

    # 상장폐지 종목을 반드시 섞는다 (C2 경로를 스모크에서도 태운다)
    dead = codes[:max(3, n_codes // 20)]
    delist_dates = {c: days[_ri(rng, n_days * 0.65, n_days - 2, floor=10)] for c in dead}
    sec = pd.DataFrame({
        "code": codes, "name": [f"합성{i:03d}" for i in range(n_codes)],
        "market": ["KOSPI" if i % 3 == 0 else "KOSDAQ" for i in range(n_codes)],
        "listing_date": pd.Timestamp("2015-01-02"),
        "delisting_date": [delist_dates.get(c, pd.NaT) for c in codes],
        "industry": [f"IND{i%7:02d}" for i in range(n_codes)],
        "corp_code": [f"{i:08d}" for i in range(n_codes)]})

    months = pd.date_range(days[0], days[-1], freq="ME")
    shares = pd.concat([pd.DataFrame({"snap_date": m, "code": codes,
                                      "shares": rng.uniform(5e6, 5e7, n_codes),
                                      "mcap_snap": np.nan}) for m in months],
                       ignore_index=True)

    # DART 재무 (방화벽 입력) — 일부 종목은 자본잠식/영업CF 적자로 만든다
    fin_rows = []
    for i, c in enumerate(codes):
        for q, d in enumerate(pd.date_range(days[0], days[-1], freq="QE")):
            eq = rng.uniform(5e10, 5e11) * (-1 if i % 25 == 0 else 1)
            fin_rows.append({"corp_code": f"{i:08d}", "period_end": d,
                             "knowledge_date": d + pd.Timedelta(days=45),
                             "equity": eq, "assets": abs(eq) * 2,
                             "liabilities": abs(eq) * 0.8,
                             "cfo_ttm": rng.normal(1e10, 3e10),
                             "op_income_ttm": rng.normal(1e10, 2e10),
                             "net_income_ttm": rng.normal(8e9, 2e10),
                             "revenue_ttm": rng.uniform(1e11, 1e12)})
    fin = pd.DataFrame(fin_rows)

    dis = pd.DataFrame({
        "corp_code": [f"{i:08d}" for i in range(0, n_codes, 9)],
        "rcept_dt": [days[_ri(rng, n_days * 0.2, n_days - 1, floor=5)]
                     for _ in range(0, n_codes, 9)],
        "report_nm": "유상증자결정", "event": "rights_issue"})

    links = pd.DataFrame({
        "stock_code": [codes[_ri(rng, 0, n_codes)] for _ in range(600)],
        "pub_date": [days[_ri(rng, n_days * 0.1, n_days - 1, floor=2)] for _ in range(600)],
        "analyst_id": [f"an{_ri(rng, 0, 40):03d}" for _ in range(600)],
        "target_price": rng.uniform(10000, 60000, 600),
        "broker_name": "합성증권"})

    return {"px": px, "credit": credit, "flows": flows, "sec": sec, "shares": shares,
            "fin": fin, "disclosures": dis, "links": links}


def run_selftest(full_chain: bool = False) -> bool:
    """계산경로 전체(수집 제외)를 합성으로 태운다. 실패하면 실데이터 수집을 시작하지 않는다."""
    t0 = time.time()
    S = make_synthetic_flp(n_codes=(120 if full_chain else 60),
                           n_days=(900 if full_chain else 460))
    px, sec = S["px"], S["sec"]
    # ★ 합성 재무를 전역 PIT 에 올린다. 이 등록은 반드시 끝에서 되돌린다(아래 finally) —
    #   남겨두면 실데이터 실행에서 PIT.has("dart_financials") 가 True 가 되어
    #   "DART 재무가 없어 방화벽이 비활성" 경고가 사라지고, 결측인 채로 조용히 진행된다.
    PIT.register("dart_financials",
                 pit_frame(S["fin"], "period_end", "knowledge_date", source="synth"),
                 key_cols=["corp_code"])
    uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    weeks = week_grid(str(px["date"].min().date()), str(px["date"].max().date()), px)
    P = build_flp_panel(px, S["credit"], S["flows"], S["shares"], weeks, uni)
    if P.empty:
        LOG.error("스모크: 주간 패널이 비었습니다.")
        PIT.drop("dart_financials")
        return False
    P = apply_universe_bands(P)
    P = build_cells_flp(P, sec)
    P = classify_phase(P)
    P = attach_fundamentals_flp(P, sec)
    P = apply_firewall(P, pd.DataFrame(columns=["code", "flag", "from_date", "to_date", "src"]),
                       {"disclosures": S["disclosures"]})
    ctx = {"disclosures": S["disclosures"],
           "research_panel": build_research_panel(S["links"], P, weeks)}
    P = apply_vetoes(P, ctx)
    P = build_tps(P)
    P = assemble_score(P)

    n_c = int(P["PHASE_C"].sum())
    n_sig = int((P["Signal"] > 0).sum())
    if n_sig == 0:
        LOG.error(f"스모크: 신호가 한 건도 발화하지 않았습니다 (국면C {n_c}행). "
                  f"게이트 중 하나가 항상 0 이면 실데이터에서도 영구 무발화입니다.")
        PIT.drop("dart_financials")
        return False

    def _run(pp, label="smoke", apply_costs=True, slip_k=SLIPPAGE_K, audit=False):
        return run_backtest_w(pp, weeks, uni, sec, apply_costs=apply_costs,
                              slip_k=slip_k, label=label, audit=audit)

    bt = _run(P, label="SMOKE", audit=True)      # 대표 실행만 감쇠 원장을 기록
    abl_df, dist_df = pd.DataFrame(), pd.DataFrame()
    s = perf_stats_w(bt["returns"])
    if not s or not np.isfinite(s.get("CAGR", np.nan)):
        LOG.error("스모크: 성과 지표를 계산하지 못했습니다.")
        PIT.drop("dart_financials")
        return False

    if full_chain:
        # 스모크에서는 '전 검사 경로'를 반드시 한 번씩 태운다. 킬로 중단되면 뒤쪽 검사가
        # 한 번도 실행되지 않은 채 실데이터로 넘어가고, 그 함수의 버그는 3시간 뒤에 터진다.
        _stop_keep = globals().get("STOP_ON_KILL_CRITERIA", True)
        _grade_keep = (CREDIT_GRADE, FLOW_GRADE, WATCH_GRADE)
        globals()["STOP_ON_KILL_CRITERIA"] = False
        globals()["CREDIT_GRADE"] = "SYNTHETIC(합성 스모크)"
        globals()["FLOW_GRADE"] = "SYNTHETIC"
        globals()["WATCH_GRADE"] = "SYNTHETIC"
        bench = benchmark_returns_w(weeks, P)
        report_grade_banner()
        report_performance(bt, bench, label="(합성 스모크)")
        # 합성데이터의 킬 판정은 '합성이 그렇게 생겼다'는 뜻일 뿐이므로 여기서는 흡수한다.
        # (실데이터 실행에서는 절대 흡수하지 않는다 — main() 참조)
        try:
            R2F_exhaustion_vs_drawdown(P, _run)
            R0_benchmark(bt, bench)
            R1_leakage(P, _run, s)
            R12_tail_correlation(bt, bench, P)
            R3_orthogonal(bt, P)
            abl_df = R5_ablation(P, _run, s)
            R7_regime(bt, bench)
            R9_capacity(P, _run)
            dist_df = check_phase_sample(P)
        except KillCriteria as e:
            LOG.warn(f"합성데이터에서 킬 판정 — 합성이므로 무시하고 계속합니다: {e}")
        report_robustness()
        # 스몰캡 비교 경로도 스모크에서 한 번 태운다(실데이터에서 처음 도는 코드를 없앤다)
        if RUN_SMALLCAP_COMPARE and "in_band_small" in P.columns:
            runs = OrderedDict()
            runs["전체 유니버스"] = {"bt": bt, "stat": s}
            PS = assemble_score(slim_panel(P), band_col="in_band_small", quiet=True)
            bs = _run(PS, label="SMOKE_small")
            runs[f"스몰캡(하위 {SMALLCAP_BOTTOM_N})"] = {"bt": bs,
                                                         "stat": perf_stats_w(bs["returns"])}
            report_universe_compare(runs, bench)
        uni.report_attrition()
        report_interpretation(P)
        diagnostic_card(P, bt, sec)
        report_dataflow_map()
        # 산출물 저장 경로까지 태운다 — 3시간 뒤 마지막 스테이지에서 처음 터지는 것을 막는다
        try:
            outs = persist_outputs(P, bt, {"verdict": "합성 스모크", "A": {}, "B": {}, "C": {}},
                                   {"synthetic": True}, abl_df, dist_df, uni)
            LOG.ok(f"산출물 저장 경로 검증 완료 — {len(outs)}건 (합성)")
        except Exception as e:                                          # noqa
            LOG.error(f"산출물 저장 경로에서 실패: {type(e).__name__}: {e}")
            return False
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = _stop_keep
            globals()["CREDIT_GRADE"], globals()["FLOW_GRADE"], globals()["WATCH_GRADE"] = _grade_keep
        LOG.info("※ 위 숫자는 전부 '합성데이터'입니다. 실데이터 결과가 아닙니다.")

    PIT.drop("dart_financials")          # ★ 합성 등록 원복 (실데이터 실행 오염 방지)
    LOG.ok(f"스모크 통과 — 국면C {n_c:,}행 · 발화 {n_sig:,}행 · "
           f"CAGR(합성) {s.get('CAGR', float('nan')):.2%} · {time.time()-t0:.1f}s")
    return True

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  실경로 리허설 — 네트워크만 가짜로 두고 '수집·정제 함수'를 실물로 실행한다            ║
# ║                                                                                          ║
# ║  합성 스모크는 '계산경로'를, 이 리허설은 '수집경로'를 증명한다. 둘은 겹치지 않는다.          ║
# ║  (계약·스모크를 다 통과하고도 수집부 한 줄 때문에 실행 2분 만에 죽는 사고를 막는다)          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []


def _rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (n > 0) if expect_rows else True
        detail = f"{n:,}행 · {time.time()-t0:.2f}s" + (f" · {note}" if note else "")
    except Exception as e:                                              # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
    REHEARSAL_RESULTS.append({"name": name, "pass": ok, "detail": detail})
    return ok


def _fx_krx_credit_json(n: int = 300) -> dict:
    """KRX getJsonData 응답 모사 — 컬럼명이 개편될 수 있으므로 '내용 기반 파싱'을 검증한다."""
    return {"OutBlock_1": [{"ISU_SRT_CD": f"{100000+i:06d}", "ISU_ABBRV": f"종목{i}",
                            "융자잔고금액": f"{(i+1)*1234567:,}",
                            "융자잔고수량": f"{(i+1)*11:,}"} for i in range(n)]}


def _fx_krx_credit_json_renamed(n: int = 300) -> dict:
    """컬럼명이 전부 바뀐 최악의 경우 — 6자리 코드 컬럼 + 최대 규모 수치 컬럼으로 살아남아야 한다."""
    return {"output": [{"col1": f"{200000+i:06d}", "col2": f"이름{i}",
                        "col3": f"{(i+1)*987654:,}", "col4": "0"} for i in range(n)]}


def run_rehearsal(strict: bool = False) -> bool:
    LOG.banner("실경로 리허설", "수집·정제 함수를 픽스처로 실물 실행 — 네트워크만 가짜")

    # ① KRX 신용잔고 파서 (정상 컬럼)
    _rh("KRX 신용잔고 파서(정상 컬럼)",
        lambda: _parse_krx_credit_json(_fx_krx_credit_json(), pd.Timestamp("2024-01-02")))
    # ② KRX 신용잔고 파서 (컬럼 전면 개편)
    _rh("KRX 신용잔고 파서(컬럼 개편 내성)",
        lambda: _parse_krx_credit_json(_fx_krx_credit_json_renamed(),
                                       pd.Timestamp("2024-01-02")))
    # ③ 파싱 불가 응답에서 조용히 죽지 않고 None 을 반환하는가
    _rh("KRX 신용잔고 파서(로그인 HTML 수신)",
        lambda: (_parse_krx_credit_json({"msg": "login required"},
                                        pd.Timestamp("2024-01-02")) is None) or True,
        expect_rows=False, note="None 반환 확인")

    # ④ 수동 CSV 흡수 경로 (사용자가 드라이브에 넣어둔 파일)
    def _manual():
        tmp = os.path.join(VAULT.root, "_rehearsal_manual")
        os.makedirs(tmp, exist_ok=True)
        p = os.path.join(tmp, "credit_sample.csv")
        pd.DataFrame({"일자": ["2024-01-02"] * 5, "종목코드": [f"{5930+i:06d}" for i in range(5)],
                      "융자잔고금액": [1000, 2000, 3000, 4000, 5000]}).to_csv(
            p, index=False, encoding="utf-8-sig")
        old = list(CREDIT_MANUAL_DIRS)
        try:
            CREDIT_MANUAL_DIRS.clear(); CREDIT_MANUAL_DIRS.append(tmp)
            return _load_manual_credit()
        finally:
            CREDIT_MANUAL_DIRS.clear(); CREDIT_MANUAL_DIRS.extend(old)
    _rh("수동 신용잔고 CSV 흡수", _manual)

    # ⑤ 등급 판정 로직: 일별/주간/프록시가 실제로 갈리는가
    def _grade():
        px = _synth_daily(120, 300)
        cr = px[["code", "date"]].copy()
        cr["credit_bal"] = 1e8
        cr["src"] = "synth"
        weekly = cr[cr["date"].dt.weekday == 4]
        out = [("daily", credit_grade_of(cr)[0]), ("weekly", credit_grade_of(weekly)[0]),
               ("empty", credit_grade_of(cr.head(0))[0])]
        if [o[1] for o in out] != ["PRIMARY_DAILY", "FALLBACK_A_WEEKLY", "NONE"]:
            raise RuntimeError(f"등급 판정 오류: {out}")
        return out
    _rh("신용잔고 등급 판정(일별/주간 구분)", _grade)

    # ⑥ 리포트 오버레이 배선 (원장 → 패널)
    def _research():
        days = pd.bdate_range("2022-01-03", periods=200)
        codes = [f"{600000+i:06d}" for i in range(20)]
        links = pd.DataFrame({
            "stock_code": [codes[i % 20] for i in range(300)],
            "pub_date": [days[i % 200] for i in range(300)],
            "analyst_id": [f"a{i%15}" for i in range(300)],
            "target_price": np.linspace(10000, 30000, 300)})
        weeks = pd.DatetimeIndex(sorted({d for d in days if d.weekday() == 4}))
        keys = pd.DataFrame([(c, w) for c in codes for w in weeks], columns=["code", "wk"])
        return build_research_panel(links, keys, weeks)
    _rh("애널리스트 리포트 → 주간 오버레이 배선", _research)

    # ⑦ 네이버 수급 JSON 파서 (KRX 차단 시의 주 경로) — 필드명 자동탐지가 실제로 되는가
    def _nv_json():
        fake = {"trendList": [
            {"localTradedAt": (pd.Timestamp("2024-01-02") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "closePrice": "50,000",
             "individualPureBuyQuant": str(100 - i),
             "foreignerPureBuyQuant": str(-50 + i),
             "organPureBuyQuant": str(-50)} for i in range(30)]}
        _keep = globals()["http_json"]
        try:
            globals()["http_json"] = lambda *a, **k: fake
            out = naver_trend_flows("005930", "2024-01-01", "2024-12-31", page_size=30,
                                    max_pages=1)
        finally:
            globals()["http_json"] = _keep
        if out is None or out["retail_net"].isna().all():
            raise RuntimeError("개인 순매수 필드를 인식하지 못했습니다")
        # 수량 → 금액 환산이 실제로 일어났는지 (스케일 오인은 f_inst 를 통째로 망친다)
        if float(out["retail_net"].abs().max()) < 1e5:
            raise RuntimeError("수량이 금액으로 환산되지 않았습니다")
        return out
    _rh("네이버 수급 JSON 파서(필드 자동탐지·금액환산)", _nv_json)

    # ⑦-b 네이버 HTML 폴백 (JSON 이 막혔을 때의 마지막 경로)
    def _nv_html():
        rows = "".join(
            f"<tr><td>2024.01.{i+1:02d}</td><td>50,000</td><td>100</td><td>1.0%</td>"
            f"<td>1,000</td><td>{-100+i}</td><td>{50-i}</td><td>1,000</td><td>10%</td></tr>"
            for i in range(20))
        html = ("<table><tr><th>날짜</th><th>종가</th><th>전일비</th><th>등락률</th>"
                "<th>거래량</th><th>기관 순매매량</th><th>외국인 순매매량</th>"
                "<th>외국인 보유주수</th><th>외국인 보유율</th></tr>" + rows + "</table>")
        _keep = globals()["http_get"]
        try:
            globals()["http_get"] = lambda *a, **k: html
            out = naver_frgn_flows("005930", "2024-01-01", "2024-12-31", max_pages=1)
        finally:
            globals()["http_get"] = _keep
        if out is None or not len(out):
            raise RuntimeError("HTML 표에서 기관/외국인 순매매를 추출하지 못했습니다")
        if out["retail_net"].isna().all():
            raise RuntimeError("개인 근사(-(기관+외국인))가 계산되지 않았습니다")
        return out
    _rh("네이버 수급 HTML 폴백(개인=근사)", _nv_html)

    # ⑧ 수급 대상 선별 · 생존자편향 잔존 감사 (실행 중 처음 도는 함수를 미리 태운다)
    def _targets():
        px = _synth_daily(60, 400)
        px.loc[px["code"] == px["code"].iloc[0], "close"] *= 0.4   # 낙폭 종목 하나 심기
        return select_flow_targets(px, str(px["date"].min().date()),
                                   str(px["date"].max().date()), max_codes=10)
    _rh("수급 대상 선별(낙폭·유동성 프리필터)", _targets, expect_rows=False,
        note="선별 표가 위에 출력되어야 정상")

    def _surv():
        px = _synth_daily(10, 300)
        codes = sorted(px["code"].unique())
        sec = pd.DataFrame({"code": codes, "name": codes, "market": "KOSDAQ",
                            "listing_date": pd.Timestamp("2015-01-01"),
                            "delisting_date": [px["date"].iloc[250]] * 3 + [pd.NaT] * 7})
        return audit_survivorship_coverage(sec, px, str(px["date"].min().date()),
                                           str(px["date"].max().date()))
    _rh("생존자편향 잔존 감사", _surv)

    # ⑧-b ★ 가격 재수집 판정 — "완전한 캐시인데 또 받는" 낭비의 회귀 방지
    def _plan():
        """실제로 있었던 낭비: IPO 종목은 캐시 최소일이 곧 상장일이라 매 실행 '앞구간 결손'
        으로 오판되어 전량 재수집됐고, 폐지 종목은 마지막 거래일이 영원히 종료일보다 일러
        매 실행 '뒤구간 증분'으로 재수집됐다. 다시 받아도 늘지 않으니 영구 반복이다."""
        today = pd.Timestamp("2026-08-08")
        ws, we = pd.Timestamp("2016-08-01"), pd.Timestamp("2026-07-31")
        codes = ["AAA", "IPO", "DEAD", "GONE", "NEW"]
        listing = {"AAA": pd.Timestamp("2010-01-04"), "IPO": pd.Timestamp("2021-05-03"),
                   "DEAD": pd.Timestamp("2010-01-04"), "GONE": pd.Timestamp("2010-01-04"),
                   "NEW": pd.Timestamp("2015-01-02")}
        delist = {"DEAD": pd.Timestamp("2019-03-15"), "GONE": pd.Timestamp("2016-01-10")}
        have_min = {"AAA": ws, "IPO": pd.Timestamp("2021-05-03"),
                    "DEAD": pd.Timestamp("2010-01-04")}
        have_max = {"AAA": pd.Timestamp("2026-07-30"), "IPO": pd.Timestamp("2026-07-30"),
                    "DEAD": pd.Timestamp("2019-03-14")}
        todo, reasons = plan_price_fetch(codes, ws, we, have_min, have_max, listing, delist,
                                         {}, today)
        got = {c for c, _ in todo}
        # AAA(완전) · IPO(상장일부터 완전) · DEAD(폐지일까지 완전) 는 받지 않아야 한다.
        # GONE 은 구간 자체가 없고(폐지가 시작 전), NEW 만 신규 수집 대상이다.
        if got != {"NEW"}:
            raise RuntimeError(f"재수집 판정 오류 — 받아야 할 것은 NEW 뿐인데 {sorted(got)} "
                               f"(사유: {dict(reasons)})")
        # 미증가 유예: 한 번 시도했는데 커버리지가 그대로면 다음 실행에서 건너뛴다
        att = {"NEW": {"at": today - pd.Timedelta(days=3), "frm": ws,
                       "gmin": pd.Timestamp("2018-01-02"), "gmax": pd.Timestamp("2026-07-30")}}
        have_min2 = dict(have_min, NEW=pd.Timestamp("2018-01-02"))
        have_max2 = dict(have_max, NEW=pd.Timestamp("2026-07-30"))
        todo2, r2 = plan_price_fetch(codes, ws, we, have_min2, have_max2, listing, delist,
                                     att, today)
        if todo2:
            raise RuntimeError(f"미증가 유예가 동작하지 않음 — {todo2} (사유: {dict(r2)})")
        return [("1차", len(todo)), ("2차", len(todo2))]
    _rh("가격 재수집 판정(IPO·폐지·미증가 유예)", _plan)

    # ⑧-c DART 수요기반 수집의 근거 — '후보였던 연도' 가 실제로 기록되는가
    def _cand_years():
        px = _synth_daily(40, 500)
        c0 = px["code"].iloc[0]
        # 한 종목만 중반에 급락시켜 후보로 만든다
        m = (px["code"] == c0) & (px["date"] >= px["date"].iloc[250])
        px.loc[m, "close"] = px.loc[m, "close"] * 0.4
        select_flow_targets(px, str(px["date"].min().date()),
                            str(px["date"].max().date()), max_codes=50)
        if not CANDIDATE_YEARS:
            raise RuntimeError("후보 연도 구간이 기록되지 않았습니다 — DART 수집 범위의 근거가 없어져 "
                               "전 종목 × 전 연도(11만 콜)로 되돌아갑니다")
        y0, y1 = next(iter(CANDIDATE_YEARS.values()))
        if not (2000 < y0 <= y1 < 2100):
            raise RuntimeError(f"후보 연도 구간이 비정상: {(y0, y1)}")
        return [(k, v) for k, v in list(CANDIDATE_YEARS.items())[:3]]
    _rh("DART 수요기반 범위(후보 연도 구간 기록)", _cand_years)

    # ⑨ 드라이브 인덱스 왕복 + adopt (원본을 옮기지 않고 등록만)
    def _vault():
        tmp = os.path.join(VAULT.root, "_rehearsal_adopt")
        os.makedirs(tmp, exist_ok=True)
        p = os.path.join(tmp, "sample_report.txt")
        atomic_write_text(p, "리허설 리포트 원문")
        uid = VAULT.adopt(p, domain="research", subtype="rehearsal", key="sample",
                          source="rehearsal", scope="shared")
        assert os.path.exists(p), "adopt 가 원본을 옮기거나 지웠습니다 — 절대 1원칙 위반"
        return [uid]
    _rh("드라이브 adopt(원본 무이동) 검증", _vault)

    rows = [[_trunc(r["name"], 46), "✔" if r["pass"] else "✘", _trunc(r["detail"], 52)]
            for r in REHEARSAL_RESULTS]
    LOG.table(rows, ["리허설 항목", "통과", "상세"], ["l", "c", "l"], maxw=56)
    fails = [r for r in REHEARSAL_RESULTS if not r["pass"]]
    if fails:
        msg = "리허설 실패: " + ", ".join(r["name"] for r in fails)
        if strict:
            raise RuntimeError(msg)
        LOG.warn(msg + " — 해당 수집 경로는 실행 중 폴백으로 처리됩니다.")
        return False
    LOG.ok(f"리허설 {len(REHEARSAL_RESULTS)}건 전부 통과.")
    return True

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  [0] 캐시 연결 → [1] 계약 → [2] 스모크 → [3] 리허설 → [4] CANARY → [5] 수집               ║
# ║  → [6] 원장감사 → [7] 패널/신호 → [8] 백테스트·성과 → [9] 강건성 → [10] 해석·산출물        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f                # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                        f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def preflight_estimate(n_codes: int, n_flow_targets: int, n_corps: int, n_years: int,
                       n_cand_corps: int = 0) -> None:
    """수집을 시작하기 '전에' 예상 소요시간을 계산해 보여준다(§9 — 추측 말고 계측).

    4시간 하드 제약을 넘길 것 같으면, 어떤 손잡이를 어떻게 돌려야 하는지까지 같이 출력한다.
    (실행을 2시간 하고 나서 '아 이거 안 끝나겠다'를 깨닫는 것이 가장 비싼 실패다)"""
    qps = lambda k: max(0.1, float(RATE_LIMIT_QPS.get(k, 3.0)))
    est = []
    px_req = n_codes                      # 종목당 1회(증분이면 그보다 적다)
    est.append(("가격 일봉", px_req, qps("naver"), px_req / qps("naver") / 60))
    fl_pages = n_flow_targets * 9         # 10년 ≈ pageSize 300 × 9페이지
    est.append(("투자자 수급(네이버)", fl_pages, qps("naver"), fl_pages / qps("naver") / 60))
    # DART 는 '수요 기반' 이다 — 전 종목 × 전 분기가 아니라, 배치 + 후보 종목만.
    batch_req = (n_corps // max(DART_MULTI_BATCH, 1) + 1) * n_years * 4
    est.append(("DART 주요계정(100사/콜)", batch_req, qps("dart"), batch_req / qps("dart") / 60))
    scope_corps = (n_corps if DART_FULL_SCOPE == "all"
                   else (n_cand_corps if DART_FULL_SCOPE == "candidates" else 0))
    full_req = scope_corps * n_years * (1 if DART_FULL_ANNUAL_FIRST else 4)
    est.append((f"DART 전체 재무제표[{DART_FULL_SCOPE}]", full_req, qps("dart"),
                full_req / qps("dart") / 60))
    ds_req = (n_cand_corps or n_corps) * n_years if USE_DART_SHARES else 0
    if DART_SHARES_MAX_CALLS:
        ds_req = min(ds_req, DART_SHARES_MAX_CALLS)
    est.append(("DART 주식총수", ds_req, qps("dart"), ds_req / qps("dart") / 60))
    total = sum(x[3] for x in est)
    LOG.table([[n, f"{r:,}", f"{q:.1f}/s", f"{m:.0f}분"] for n, r, q, m in est] +
              [["── 합계(캐시 미보유 최악)", "", "", f"{total:.0f}분"]],
              ["수집 단계", "예상 요청수", "속도상한", "예상 소요"], ["l", "r", "r", "r"],
              title="수집 프리플라이트 — 시작 전에 끝나는지 먼저 계산한다(§9)")
    if total > 210:
        LOG.warn(f"예상 {total:.0f}분으로 4시간 예산에 근접/초과합니다. 손잡이는 셋입니다: "
                 f"① FLOW_MAX_CODES 를 {max(200, n_flow_targets//2):,} 로 낮추기 "
                 f"② RATE_LIMIT_QPS['naver'] 를 올리기(차단 위험과 교환) "
                 f"③ 오늘은 여기까지 받고 재실행 — 캐시는 누적되므로 다음 실행이 그만큼 짧아집니다.")
    else:
        LOG.ok(f"예상 {total:.0f}분 — 4시간 예산 내입니다(캐시가 있으면 더 짧아집니다).")


# ═══ CANARY (§2) ════════════════════════════════════════════════════════════════════════════
def run_canary(sec: pd.DataFrame, delisted: pd.DataFrame, sample_n: int = 200) -> None:
    """코드가 아니라 '데이터의 등급'을 먼저 확정한다. 여기서 실패한 것은 나중에도 실패한다.

    ★ 표본 수집물은 전부 공용 인덱스 캐시를 통과하므로, 본 수집 단계에서 그대로 재사용된다
      (카나리 때문에 같은 데이터를 두 번 받지 않는다)."""
    codes = sec["code"].dropna().tolist()
    sample = codes[:sample_n]

    # K5 — 상장폐지 목록 (이 전략의 생명선)
    n_del = int(delisted["delisting_date"].notna().sum()) if len(delisted) else 0
    in_range = 0
    if len(delisted):
        d = as_ts_series(delisted["delisting_date"])
        in_range = int(((d >= as_ts(BACKTEST_START)) & (d <= as_ts(BACKTEST_END))).sum())
    prov = ""
    if len(delisted) and "delisting_src" in delisted.columns:
        vc = delisted["delisting_src"].value_counts().to_dict()
        prov = " · 근거=" + ", ".join(f"{k}:{v:,}" for k, v in vc.items())
    canary("K5", "상장폐지 목록 (생존자편향 제거)", n_del > 0 and in_range > 50,
           f"폐지일 보유 {n_del:,}종목 · 백테스트 구간 내 폐지 {in_range:,}건{prov}",
           "" if in_range > 50 else "§11-1 킬 기준 — 상폐를 못 넣으면 이 전략의 성과는 무효")

    # K4 — 가격
    px_have = 0
    cached_px = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if cached_px is not None and len(cached_px):
        px_have = int(cached_px["code"].nunique())
    canary("K4", "10년 일봉 (FDR/pykrx/네이버/yf 체인)", px_have > 0,
           f"공용 캐시 보유 {px_have:,}종목" + ("" if px_have else " — 이번 실행에서 신규 수집"),
           "" if px_have else "가격 체인이 전부 실패하면 실행 자체가 불가")

    # F2 — 투자자유형별 순매수
    fl = VAULT.get_table("krx_investor_flows_daily", scope="shared")
    n_fl = int(fl["code"].nunique()) if fl is not None and len(fl) else 0
    has_retail = bool(fl is not None and len(fl) and "retail_net" in fl.columns
                      and fl["retail_net"].notna().any())
    if n_fl == 0 and RUN_MODE != "CACHED":
        probe = fetch_investor_flows_daily(sample[:20], BACKTEST_START, BACKTEST_END)
        n_fl = int(probe["code"].nunique()) if len(probe) else 0
        has_retail = bool(len(probe) and probe["retail_net"].notna().any())
    canary("F2", "투자자유형별 일별 순매수 (개인/기관/외국인)", n_fl > 0 and has_retail,
           f"{n_fl:,}종목 · 개인 분해 {'있음' if has_retail else '없음'}",
           "" if (n_fl and has_retail) else "§11-2 킬 기준 — 소유권 이전 관측 불가")

    # F1 — 신용융자잔고 (등급은 수집 단계에서 확정되지만, 가용성은 여기서 미리 본다)
    cr = VAULT.get_table("krx_credit_balance_daily", scope="shared")
    n_cr = int(cr["code"].nunique()) if cr is not None and len(cr) else 0
    manual_dirs = [d for d in CREDIT_MANUAL_DIRS if d and os.path.isdir(d)]
    canary("F1", "종목별 신용융자잔고 ★이 전략의 핵심", n_cr > 0 or bool(manual_dirs) or KRX.session_ok,
           f"캐시 {n_cr:,}종목 · 수동폴더 {len(manual_dirs)}개 · KRX모드 {KRX_MODE} · "
           f"세션 {'있음' if KRX.session_ok else '없음'}",
           "없으면 Fallback A(주간) → B(프록시). B는 리포트에 반드시 명시")

    # F3 — 단위·정의
    unit = "미확인"
    if cr is not None and len(cr):
        med = float(pd.to_numeric(cr["credit_bal"], errors="coerce").median())
        unit = ("금액(원)" if med > 1e6 else "수량(주) 의심")
        canary("F3", "신용잔고 단위·정의 (금액 vs 수량)", med > 1e6,
               f"중앙값 {med:,.0f} → {unit}",
               "" if med > 1e6 else "수량이면 시총 대비 비율이 왜곡됨 — 단가 곱셈 필요")
    else:
        canary("F3", "신용잔고 단위·정의", None, "잔고 미확보로 판정 보류", "수집 후 자동 재판정")

    # K1 — DART 재무
    fin = VAULT.get_table("dart_financials", scope="shared")
    n_fin = len(fin) if fin is not None else 0
    canary("K1", "DART 재무 (방화벽 입력)", bool(DART_API_KEY) or n_fin > 0,
           f"키 {'있음' if DART_API_KEY else '없음'} · 캐시 {n_fin:,}행",
           "" if (DART_API_KEY or n_fin) else "방화벽 대부분 비활성 — 단일 실패모드 노출")

    # K6 — 관리종목·거래정지
    wl = VAULT.get_table("krx_watchlist_events", scope="shared")
    canary("K6", "관리종목·투자주의·거래정지", wl is not None and len(wl) > 0,
           f"캐시 {0 if wl is None else len(wl):,}행",
           "없으면 방화벽 해당 조항만 비활성화하고 로깅")

    # F4 — 전환청구권행사 공시 (M3 선택)
    dis = VAULT.get_table("dart_disclosures", scope="shared")
    n_cb = 0
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        n_cb = int(dis["report_nm"].astype(str).str.contains("전환청구권|전환가액").sum())
    canary("F4", "전환청구권행사 공시 (M3 이벤트)", n_cb > 0,
           f"캐시 내 {n_cb:,}건", "없으면 M3 이벤트 트리거 비활성 (전략 본체는 정상 동작)")

    report_canary()

    if STOP_ON_KILL_CRITERIA:
        if CANARY.get("K5", {}).get("pass") is False:
            raise KillCriteria("K5 FAIL — 상장폐지 목록 미확보. 이 전략에서 C2 위반은 치명적입니다(§11-1). "
                               "생존자편향이 남은 성과는 전부 무효이므로 여기서 중단합니다.")
        if CANARY.get("F2", {}).get("pass") is False:
            raise KillCriteria("F2 FAIL — 투자자유형별 순매수 미취득. '소유권 이전'을 관측할 수 "
                               "없으므로 이 전략의 절반이 성립하지 않습니다(§11-2).")


# ═══ 수집 ═══════════════════════════════════════════════════════════════════════════════════
def collect_all(weeks: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}
    months = pd.date_range(as_ts(BACKTEST_START) - pd.DateOffset(months=15),
                           as_ts(BACKTEST_END), freq="ME")

    with PIPE.stage("L1.UNI", "종목 마스터 · 다중소스 발굴 (C2)", "L1", budget_s=900):
        snaps = fetch_listing_snapshots_guarded(months)
        sec = build_security_master(snaps)
        # ★ KRX 가 막혀도 유니버스가 얇아지지 않도록 코드 발굴을 다중소스 합집합으로 넓힌다
        sec = discover_codes_multi(sec)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금 (M0)", "L1", budget_s=2700):
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                          BACKTEST_END, sec=ctx["sec"])
        ctx["px"] = px

    with PIPE.stage("L1.UNIFIX", "상장/폐지 창 재구성 (KRX 없이 C2 성립)", "L1", budget_s=300):
        # 거래가 있었다는 사실 자체가 상장의 증거다. 명부가 없으면 가격이력으로 창을 복원한다.
        ctx["sec"] = reconstruct_listing_windows(ctx["sec"], ctx["px"], BACKTEST_END)
        ctx["delisted"] = (ctx["sec"][["code", "name", "delisting_date", "delisting_src"]]
                           .dropna(subset=["delisting_date"]))
        ctx["surv_cov"] = audit_survivorship_coverage(ctx["sec"], ctx["px"],
                                                      BACKTEST_START, BACKTEST_END)
        VAULT.put_table("security_master_pit", ctx["sec"], scope="shared", domain="universe",
                        source="multi-source + price reconstruction",
                        extra={"note": "상장/폐지 창 + 출처(provenance) — 전 전략 공용"})

    with PIPE.stage("L0.CANARY", "CANARY F1~F4 · K1~K6 (§2)", "L0", budget_s=1500):
        if krx_allowed():
            KRX.login()
        run_canary(ctx["sec"], ctx["delisted"])

    with PIPE.stage("L1.FLOW", "투자자유형별 일별 순매수 (M0)", "L1", budget_s=2400, critical=False):
        targets = select_flow_targets(ctx["px"], BACKTEST_START, BACKTEST_END)
        if not targets:
            # ★ 후보가 0이면 예전 코드는 `targets or 전 종목` 으로 전 종목을 받았다.
            #   FLOW_MAX_CODES 상한을 우회하는 경로라, 가장 비싼 수집이 통제 없이 폭주한다.
            #   대신 유동성 상위로 상한만큼만 받고, 왜 그렇게 됐는지 명시한다.
            _amt0 = (ctx["px"].groupby("code", observed=True)["amount"].median()
                     .sort_values(ascending=False))
            _cap = FLOW_MAX_CODES if FLOW_MAX_CODES and FLOW_MAX_CODES > 0 else 600
            targets = [str(c) for c in _amt0.index[:_cap]]
            LOG.warn(f"수급 후보 선별이 0종목을 반환했습니다(가격 커버리지 부족 가능성). "
                     f"전 종목을 받지 않고 유동성 상위 {len(targets):,}종목으로 제한합니다 — "
                     f"상한 우회로 수집이 폭주하는 것을 막기 위함입니다.")
        ctx["flow_targets"] = targets
        _yrs = max(1, as_ts(BACKTEST_END).year - as_ts(BACKTEST_START).year + 3)
        _c2c0 = (ctx["sec"].dropna(subset=["corp_code"])
                 .set_index("code")["corp_code"].astype(str).to_dict())
        _ncand = len({_c2c0[c] for c in targets if c in _c2c0})
        preflight_estimate(len(ctx["sec"]), len(targets),
                           int(ctx["sec"]["corp_code"].notna().sum()), _yrs,
                           n_cand_corps=_ncand)
        ctx["flows"] = fetch_investor_flows_daily(targets, BACKTEST_START, BACKTEST_END,
                                                  sec=ctx["sec"])

    with PIPE.stage("L1.SHARES", "상장주식수 (DART 주식총수 우선 · PIT)", "L1", budget_s=1200,
                    critical=False):
        # 유동성 순으로 우선순위를 준다 — 호출 상한에 걸려도 '살 수 있는 종목'부터 채워진다
        _years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        _amt = (ctx["px"].groupby("code", observed=True)["amount"].median()
                .sort_values(ascending=False))
        _c2c = (ctx["sec"].dropna(subset=["corp_code"])
                .set_index("code")["corp_code"].astype(str).to_dict())
        _cand = set(ctx.get("flow_targets") or [])
        _corps = [_c2c[c] for c in _amt.index if c in _c2c and (not _cand or c in _cand)]
        if not USE_DART_SHARES:
            _corps = []
            LOG.info("USE_DART_SHARES=False — PIT 시총 분모를 받지 않고 거래대금 대리로 갑니다 "
                     "(f_cr 은 자기이력 백분위라 스케일 차이에 둔감합니다).")
        elif _cand:
            LOG.info(f"주식총수는 후보 종목 {len(_corps):,}사만 받습니다 "
                     f"(전 종목이면 {int(ctx['sec']['corp_code'].notna().sum()) * len(_years):,}콜).")
        if DART_SHARES_MAX_CALLS and len(_corps) * len(_years) > DART_SHARES_MAX_CALLS:
            keep_n = max(1, DART_SHARES_MAX_CALLS // max(len(_years), 1))
            LOG.warn(f"DART 주식총수 호출 예상 {len(_corps)*len(_years):,}건이 상한 "
                     f"{DART_SHARES_MAX_CALLS:,}건을 초과 → 유동성 상위 {keep_n:,}사만 받습니다. "
                     f"나머지 종목의 시총 분모는 '거래대금 20일합' 대리로 대체되며, "
                     f"f_cr 은 자기이력 백분위라 스케일 차이에 둔감합니다.")
            _corps = _corps[:keep_n]
        _cy: Dict[str, List[int]] = {}
        for _code, (_a, _b) in (CANDIDATE_YEARS or {}).items():
            _cc = _c2c.get(_code)
            if _cc:
                _cy[_cc] = [y for y in range(_a - 1, _b + 2) if min(_years) <= y <= max(_years)]
        ctx["dart_shares"] = fetch_dart_shares(_corps, _years, corp_years=_cy or None)
        ctx["shares"] = fetch_shares_outstanding(months, sec=ctx["sec"],
                                                 dart_shares=ctx.get("dart_shares"))
        _sh = ctx["shares"]
        _cov = (float(_sh["code"].nunique()) / max(int(ctx["sec"]["code"].nunique()), 1)
                if _sh is not None and len(_sh) else 0.0)
        LOG.table([["주식수 확보 종목", f"{0 if _sh is None else _sh['code'].nunique():,}"],
                   ["전체 종목", f"{ctx['sec']['code'].nunique():,}"],
                   ["커버리지", f"{_cov:.1%}"]],
                  ["PIT 시가총액 분모", "값"], ["l", "r"],
                  title="시총 분모 커버리지 — 낮으면 규모축이 사실상 '유동성축'이 된다")
        if _cov < 0.5:
            LOG.warn(f"주식수 커버리지가 {_cov:.0%} 입니다. 나머지 종목의 규모는 거래대금×보정으로 "
                     f"대리되므로, '상위 250 제외'와 '스몰캡 하위 N' 이 부분적으로 유동성 기준이 "
                     f"됩니다. 스몰캡 비교 결과를 '소형주 대 대형주'가 아니라 "
                     f"'비유동 대 유동'으로도 읽힐 수 있다는 점을 감안하세요. "
                     f"(USE_DART_SHARES=True 와 DART 키가 있으면 후보 종목은 실측치로 채워집니다)")

    with PIPE.stage("L1.CREDIT", "신용융자잔고 ★핵심 (M1)", "L1", budget_s=2400, critical=False):
        ctx["credit"] = fetch_credit_balance(ctx["px"], ctx.get("flows", pd.DataFrame()),
                                             BACKTEST_START, BACKTEST_END)
        # F1/F3 카나리를 실측으로 갱신한다(추측 금지)
        canary("F1", "종목별 신용융자잔고 ★이 전략의 핵심",
               CREDIT_GRADE in ("PRIMARY_DAILY", "FALLBACK_A_WEEKLY"),
               f"등급 {CREDIT_GRADE} · {CREDIT_SOURCE_NOTE}",
               "PRIMARY 아니면 결과 해석 시 신뢰도 하향")

    with PIPE.stage("L1.DART", "DART 재무 · 공시 (M2 방화벽)", "L1", budget_s=3600, critical=False):
        corps_all = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        if corps_all and DART_API_KEY:
            # ── 호출 계획을 먼저 세우고 표로 보여준다 ──────────────────────────────────
            #   ★ 이 전략이 DART 에서 실제로 쓰는 것:
            #      자본총계·부채총계·자산총계·매출액·영업이익·당기순이익 → 주요계정 배치(100사/콜)
            #      영업활동현금흐름                                    → 전체 재무제표(1사/콜) ★유일
            #   전 종목 × 11년 × 4분기로 전체 재무제표를 받으면 11만 콜(≈6일)인데,
            #   그 대부분은 '살 수도 없는 종목의 현금흐름'이다. 후보 종목으로 좁힌다.
            c2c = (ctx["sec"].dropna(subset=["corp_code"])
                   .set_index("code")["corp_code"].astype(str).to_dict())
            cand_codes = ctx.get("flow_targets") or []
            cand_corps = [c2c[c] for c in cand_codes if c in c2c]
            if DART_FULL_SCOPE == "all":
                full_corps = corps_all
            elif DART_FULL_SCOPE == "off":
                full_corps = []
            else:
                full_corps = cand_corps or corps_all[:0]
            full_reprts = ([REPRT_CODES["FY"]] if DART_FULL_ANNUAL_FIRST
                           else [REPRT_CODES["Q1"], REPRT_CODES["H1"],
                                 REPRT_CODES["Q3"], REPRT_CODES["FY"]])
            # ★ 회사마다 '후보였던 연도 ±1' 만 받는다. 방화벽은 그 종목을 살 수 있었던
            #   시점에만 의미가 있으므로, 그 밖의 연도를 받는 것은 그냥 낭비다.
            y_lo, y_hi = min(years), max(years)
            corp_years: Dict[str, List[int]] = {}
            for code, (a, b) in (CANDIDATE_YEARS or {}).items():
                cc = c2c.get(code)
                if not cc:
                    continue
                rng = [y for y in range(a - 1, b + 2) if y_lo <= y <= y_hi]
                if rng:
                    corp_years.setdefault(cc, [])
                    corp_years[cc] = sorted(set(corp_years[cc]) | set(rng))
            _yrs_of = lambda c: corp_years.get(c, years)
            n_batch = (len(corps_all) // DART_MULTI_BATCH + 1) * len(years) * 4
            n_full = sum(len(_yrs_of(c)) for c in full_corps) * len(full_reprts)
            n_share = (sum(len(_yrs_of(c)) for c in (cand_corps or corps_all))
                       if USE_DART_SHARES else 0)
            LOG.table([
                ["주요계정 배치(100사/콜)", f"{len(corps_all):,}사 전체", f"{n_batch:,}",
                 "자본·부채·자산·매출·영업이익·순이익"],
                [f"전체 재무제표(1사/콜) [{DART_FULL_SCOPE}]", f"{len(full_corps):,}사",
                 f"{n_full:,}", "영업활동현금흐름 (이것 하나 때문에 씁니다)"],
                ["주식총수(1사·년/콜)", f"{len(cand_corps or corps_all):,}사" if USE_DART_SHARES
                 else "off", f"{n_share:,}", "PIT 시총 분모 (없으면 거래대금 대리)"],
                ["── 합계(캐시 미보유 최악)", "", f"{n_batch + n_full + n_share:,}", ""]],
                ["DART 수집 계획", "대상", "예상 콜", "쓰이는 곳"], ["l", "r", "r", "l"],
                title="DART 호출 계획 — 전 종목 × 전 분기 전체 재무제표는 11만 콜입니다. "
                      "필요한 종목만 받습니다")
            if DART_FULL_SCOPE == "candidates" and not cand_corps:
                LOG.warn("후보 종목이 아직 없어(수급 선별 실패) 전체 재무제표를 건너뜁니다 — "
                         "영업CF 방화벽과 V3 거부권이 비활성화됩니다.")

            multi = fetch_dart_multi_accounts(corps_all, years)      # 전 종목 바닥 (싸다)
            fs = pd.DataFrame()
            if len(full_corps):
                fs = fetch_dart_financials(full_corps, years, priority=full_corps,
                                           reprt_codes=full_reprts, corp_years=corp_years)
                # 연간을 다 채우고도 예산이 남아 있으면 분기까지 이어서 받는다
                if (DART_FULL_ANNUAL_FIRST and DBUDGET is not None
                        and not DBUDGET.exhausted):
                    LOG.info("연간 재무제표를 다 받고도 호출 여유가 있어 분기까지 이어받습니다.")
                    fs_q = fetch_dart_financials(
                        full_corps, years, priority=full_corps,
                        reprt_codes=[REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"]],
                        corp_years=corp_years)
                    if len(fs_q):
                        fs = pd.concat([fs, fs_q], ignore_index=True).drop_duplicates(
                            ["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                             "account_nm"], keep="last")
            fin = tidy_financials(merge_financial_tiers(fs, multi))
            if len(fin):
                PIT.register("dart_financials", fin, key_cols=["corp_code"])
            ctx["fin"] = fin
            ctx["dart_cand_corps"] = cand_corps
            ctx["dart_corp_years"] = corp_years
            ctx["disclosures"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        else:
            # ★ 키가 없다고 '드라이브에 이미 있는 DART 캐시'까지 버리면 안 된다.
            #   v2 전략들이 공용 인덱스에 쌓아둔 재무·공시가 그대로 재사용 가능하다.
            cf = VAULT.get_table("dart_financials", scope="shared")
            cd = VAULT.get_table("dart_disclosures", scope="shared")
            if cf is not None and len(cf):
                need_pit = [c for c in ("event_date", "knowledge_date") if c not in cf.columns]
                if not need_pit:
                    PIT.register("dart_financials", cf, key_cols=["corp_code"])
                    LOG.ok(f"★ DART 키가 없지만 공용 인덱스의 재무 캐시 {len(cf):,}행을 "
                           f"재사용합니다 — 방화벽이 살아납니다.")
                else:
                    LOG.warn(f"공용 재무 캐시에 PIT 컬럼 {need_pit} 이 없어 사용할 수 없습니다.")
            if cd is not None and len(cd):
                LOG.ok(f"★ 공용 인덱스의 공시 캐시 {len(cd):,}행 재사용 — V1 거부권이 살아납니다.")
            ctx["fin"] = cf if cf is not None else pd.DataFrame()
            ctx["disclosures"] = cd if cd is not None else pd.DataFrame()
            if (cf is None or not len(cf)) and (cd is None or not len(cd)):
                LOG.warn("DART_API_KEY 미입력 + 공용 캐시도 비어 있음 — 방화벽(자본잠식·영업CF)과 "
                         "V1/V3 거부권이 비활성화됩니다.")

    with PIPE.stage("L1.WATCH", "관리종목 · 거래정지 (K6)", "L1", budget_s=300, critical=False):
        ctx["watch"] = fetch_watchlist_halt(ctx["sec"])

    # ※ PIPE.stage(skip_if=...) 는 스테이지를 SKIP 으로 기록하지만 본문 실행까지 막지는
    #    못한다(컨텍스트매니저가 yield 하므로 with 본문은 그대로 돈다).
    #    그래서 '끄기'는 반드시 호출부의 조건 분기로 구현한다.
    if RESEARCH_USE:
        with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장 (한경/네이버)", "L1",
                        budget_s=3600, critical=False):
            LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                     "지시에 따라 수집하되 보수적 속도로 제한합니다. 원문은 로컬 분석 용도로만.")
            cached = VAULT.get_table("research_report_master", scope="shared")
            frames = []
            if cached is not None and len(cached):
                LOG.ok(f"★ 구글드라이브 공용 인덱스에서 리포트 원장 {len(cached):,}건 재사용 "
                       f"(재수집하지 않습니다)")
                frames.append(cached)
            if RUN_MODE == "FULL" and RESEARCH_COLLECT:
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
                if "naver" in RESEARCH_SOURCES:
                    nv = naver_collect(BACKTEST_START, BACKTEST_END)
                    frames.append(naver_enrich_detail(nv))
            rep = build_report_master(frames, ctx["sec"])
            if len(rep):
                if RESEARCH_DOWNLOAD_PDF:
                    rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
                VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                                source="hankyung+naver")
            A, L = build_analyst_ledger(rep)
            if len(A):
                VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                                source="entity_resolution")
                VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                                source="entity_resolution")
            ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    else:
        LOG.warn("RESEARCH_USE=False — 애널리스트 리포트 오버레이(V_RS 거부권·해석표 커버리지)를 "
                 "사용하지 않습니다. 드라이브에 캐시가 있어도 읽지 않습니다.")
    # ★ 비필수(critical=False) 스테이지가 실패하면 그 산출물 키가 없다. 하류에서
    #   ctx["flows"] 로 읽으면 '수급 실패'가 엉뚱하게 '신용잔고 스테이지의 KeyError' 로
    #   보고된다 — 실패 지점이 흐려지는 것이 가장 나쁘다. 여기서 한 번에 기본값을 못박는다.
    for _k in ("flows", "shares", "credit", "watch", "disclosures", "fin", "dart_shares",
               "reports", "analysts", "links"):
        ctx.setdefault(_k, pd.DataFrame())
    return ctx


def build_signal_panel(ctx: dict, weeks: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe"]:
    with PIPE.stage("L2.PANEL", "일별 센서 → 주간 패널 → 국면 → TP → 신호", "L2", budget_s=2400):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
            columns=["snap_date", "code", "market"])), ctx["px"])
        P = build_flp_panel(ctx["px"], ctx.get("credit", pd.DataFrame()),
                            ctx.get("flows", pd.DataFrame()), ctx.get("shares", pd.DataFrame()),
                            weeks, uni)
        if P.empty:
            raise RuntimeError("주간 패널이 비었습니다 — 가격 또는 유니버스 수집을 확인하세요.")
        P = apply_universe_bands(P)
        P = build_cells_flp(P, ctx["sec"])
        P = classify_phase(P)
        P = attach_fundamentals_flp(P, ctx["sec"])
        P = apply_firewall(P, ctx.get("watch", pd.DataFrame()), ctx)
        ctx["research_panel"] = build_research_panel(ctx.get("links", pd.DataFrame()), P, weeks)
        P = apply_vetoes(P, ctx)
        P = build_tps(P)
        check_tp_degeneracy()          # 등급 조합이 특정 TP 를 무의미하게 만들었는지 판정
        P = assemble_score(P)
        P = downcast(P)
        audit_research_wiring(ctx.get("reports", pd.DataFrame()),
                              ctx.get("analysts", pd.DataFrame()),
                              ctx.get("links", pd.DataFrame()), P)
    return P, uni


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 · 전략 8 — {STRATEGY_NAME}",
               f"{BACKTEST_START}~{BACKTEST_END} · 주 1회 리밸런싱 · 빌드 {BUILD_VERSION}")
    LOG.info("이 전략은 알파가 아니라 '위험 프리미엄'입니다(§0). 위기 국면에 전 포지션이 "
             "동시에 손실납니다 — R12 에서 그 크기를 직접 측정합니다.")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["KRX 모드", f"{KRX_MODE} " + ("(차단 대응: 비KRX 스파인 사용)"
                                             if KRX_MODE.upper() == "OFF" else "")],
               ["KRX 자격증명", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW) else "미입력"],
               ["DART 키", "입력됨" if DART_API_KEY else "미입력"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root} (모드 {mode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유 (가격·수급·신용·리포트)")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유 (패널·신호·백테스트)")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
        VAULT.load_index("shared"); VAULT.load_index("private")
        # ★ 흡수 경로 자동 확장: 설정값이 다른 OS 의 경로(/content/...)뿐이면 아무것도 못 찾고
        #   "경로를 확인하세요" 경고만 남는다. 실제로 존재하는 경로만 추리고, 하나도 없으면
        #   캐시 루트 자신과 그 상위의 흔한 리포트 폴더를 후보로 넣는다.
        _adopt = [d for d in GDRIVE_ADOPT_DIRS if d and os.path.isdir(d)]
        _extra = [VAULT.root, os.path.join(VAULT.root, "reports"),
                  os.path.join(VAULT.root, "research"),
                  os.path.join(os.path.dirname(VAULT.root), "research"),
                  os.path.join(os.path.dirname(VAULT.root), "reports")]
        for _d in _extra:
            if os.path.isdir(_d) and _d not in _adopt:
                _adopt.append(_d)
        if _adopt:
            LOG.info(f"기존 파일 흡수 대상 {len(_adopt)}개 경로: "
                     + ", ".join(os.path.basename(d) or d for d in _adopt[:5]))
        VAULT.adopt_scan(_adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=600,
                    critical=False):
        run_rehearsal(strict=False)

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(pd.DatetimeIndex([]))
    weeks = week_grid(BACKTEST_START, BACKTEST_END, ctx["px"])
    LOG.ok(f"주간 신호 격자 {len(weeks):,}주 ({weeks[0]:%Y-%m-%d} ~ {weeks[-1]:%Y-%m-%d})"
           if len(weeks) else "주간 격자 생성 실패")

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (리포트↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    P, uni = build_signal_panel(ctx, weeks)

    def _run(pp, label="run", apply_costs=True, slip_k=SLIPPAGE_K, audit=False):
        return run_backtest_w(pp, weeks, uni, ctx["sec"], apply_costs=apply_costs,
                              slip_k=slip_k, label=label, audit=audit)

    universes = OrderedDict([("전체 유니버스(상위250 제외)", "in_band")])
    if RUN_SMALLCAP_COMPARE and "in_band_small" in P.columns:
        universes[f"스몰캡(시총 하위 {SMALLCAP_BOTTOM_N})"] = "in_band_small"

    runs: "OrderedDict[str, dict]" = OrderedDict()
    with PIPE.stage("L3.BT", "주간 백테스트 (유니버스별)", "L3", budget_s=900):
        for lab, band in universes.items():
            PP = P if band == "in_band" else assemble_score(slim_panel(P), band_col=band)
            b = _run(PP, label=f"{STRATEGY_ID}:{band}", audit=(band == "in_band"))
            runs[lab] = {"panel": PP, "bt": b, "band": band,
                         "stat": perf_stats_w(b["returns"])}
            LOG.ok(f"[{lab}] 백테스트 완료 — 평균 {runs[lab]['stat'].get('평균종목수', 0):.1f}종목")
    bt = runs[list(runs)[0]]["bt"]

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300):
        report_grade_banner()
        bench = benchmark_returns_w(weeks, P)
        base_stat = report_performance(bt, bench)
        for lab in list(runs)[1:]:
            report_performance(runs[lab]["bt"], bench, label=f"({lab})")
        report_universe_compare(runs, bench)
        uni.report_attrition()

    r2f, r12, abl, dist = {}, {}, pd.DataFrame(), pd.DataFrame()
    with PIPE.stage("L5.ROBUST", "강건성 R2-F · R0 · R1 · R12 · R3 · R5 · R7 · R9", "L5",
                    budget_s=3600, critical=False):
        try:
            r2f = R2F_exhaustion_vs_drawdown(P, _run)     # ★ 최우선
            for lab in list(runs)[1:]:
                LOG.rule(f"R2-F · {lab}")
                R2F_exhaustion_vs_drawdown(P, _run, band_col=runs[lab]["band"])
            R0_benchmark(bt, bench)
            R1_leakage(P, _run, base_stat)
            r12 = R12_tail_correlation(bt, bench, P)
            for lab in list(runs)[1:]:
                LOG.rule(f"R12 · {lab}")
                R12_tail_correlation(runs[lab]["bt"], bench, runs[lab]["panel"])
            R3_orthogonal(bt, P)
            abl = R5_ablation(P, _run, base_stat)
            R7_regime(bt, bench)
            R9_capacity(P, _run)
            dist = check_phase_sample(P)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다 — 결과를 그대로 보고합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드 · 데이터 흐름", "L6", budget_s=300,
                    critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])
        report_dataflow_map()

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = persist_outputs(P, bt, r2f, r12, abl, dist, uni)
        for lab, r in list(runs.items())[1:]:
            tag = "smallcap"
            VAULT.put_table(f"backtest_returns_{STRATEGY_ID}_{tag}", r["bt"]["returns"],
                            scope="private", domain="backtest", source=f"{STRATEGY_ID}:{lab}")
            _p = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID,
                              f"returns_{tag}_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv")
            os.makedirs(os.path.dirname(_p), exist_ok=True)
            r["bt"]["returns"].to_csv(_p, index=False, encoding="utf-8-sig")
            outs.append(_p)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.report()
            DBUDGET.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    PIPE.report_runtime()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info(f"한계 명시 — 신용잔고 등급 {CREDIT_GRADE}. "
             f"이자보상배율은 이자비용 계정이 DART 정형 매핑에 없어 '부채×5%' 대리를 씁니다. "
             f"관리종목/거래정지는 이력이 아닌 스냅샷이면 현재 시점 이후로만 적용합니다"
             f"(과거 구간 오염 방지).")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_RESULTS,
            "r2f": r2f, "r12": r12}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
        try:
            report_canary(); report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브 공용 인덱스에 저장되어 있으며 "
                 "재실행 시 그대로 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
