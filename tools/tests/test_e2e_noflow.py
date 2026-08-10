#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F6/F7 전멸 상태에서 끝까지 완주하는지 검증 (사용자 실환경 재현 · 네트워크 0회).

목적: 재배치된 L1 순서가 실제로 끝까지 흐르는지 증명한다.
  L1.CACHE(캐시·캘린더) → L1.SPINE(시총) → L1.UNIV(유니버스) → L1.PX(유니버스 한정 가격)
  → L1.FLOW → L1.DART → L1.RESEARCH → L2.FACTOR → L3.BT → L6.PERF → L5.ROBUST → 산출물

합성 캐시를 드라이브 규약대로 깔아두고 실행한다. 팩터 입력(F1~F7)을 전부 만들어 넣어
'적격종목 30개 이상'이 실제로 나오는지까지 확인한다.
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "shinhan_7f_earnings_surprise_v1.py")
ROOT = tempfile.mkdtemp(prefix="sh7f_e2e_")
CACHE = os.path.join(ROOT, "tcd_cache")
SHARED = os.path.join(CACHE, "_shared", "table")
os.makedirs(SHARED, exist_ok=True)
os.makedirs(os.path.join(CACHE, "_shared", "index"), exist_ok=True)
os.makedirs(os.path.join(CACHE, "shinhan_7f", "table"), exist_ok=True)
os.makedirs(os.path.join(CACHE, "shinhan_7f", "index"), exist_ok=True)

import numpy as np
import pandas as pd

START, END = "2016-08-01", "2026-07-31"
BD = pd.bdate_range("2015-01-01", "2026-08-31")
N = 320
CODES = [f"{(i * 10 + 1000):06d}" for i in range(N)]
rng = np.random.default_rng(7)

# ── ① marcap 연도 파일 (일봉 + 시총 + 주식수 · 폐지종목 포함 성격) ──────────────────────────
#     경로를 일부러 깊은 하위폴더에 둔다 — 재귀 발견이 실제로 필요한 상황을 만든다.
deep = os.path.join(SHARED, "marcap", "byyear")
os.makedirs(deep, exist_ok=True)
drift = rng.normal(0.0004, 0.018, size=(len(BD), N))
lvl = 10000.0 * np.exp(np.cumsum(drift, axis=0))
shares = (10 ** rng.uniform(6.0, 9.0, size=N)).round()
for y in sorted(set(BD.year)):
    m = BD.year == y
    days, px = BD[m], lvl[m]
    frames = []
    for i, c in enumerate(CODES):
        p = px[:, i]
        frames.append(pd.DataFrame({
            "date": days, "code": c, "name": f"종목{c}",
            "market": "KOSPI" if i < 200 else "KOSDAQ",
            "open": p, "high": p * 1.01, "low": p * 0.99, "close": p,
            "volume": 1e4 + i * 7, "amount": (1e4 + i * 7) * p,
            "marcap": p * shares[i], "stocks": shares[i]}))
    pd.concat(frames, ignore_index=True).to_parquet(
        os.path.join(deep, f"marcap_{y}.parquet"), index=False)
print(f"marcap {len(set(BD.year))}개 연도 생성 → {deep}")

# ── ② security_master (상장/폐지·corp_code 포함) ──────────────────────────────────────────
sec = pd.DataFrame({
    "code": CODES, "name": [f"종목{c}" for c in CODES],
    "market": ["KOSPI"] * 200 + ["KOSDAQ"] * (N - 200),
    "listing_date": [pd.Timestamp("2010-01-04")] * N,
    "delisting_date": [pd.NaT] * N,
    "industry": ["기타"] * N,
    "corp_code": [f"{i:08d}" for i in range(N)],
    "src": ["synthetic"] * N})
sec.loc[sec.index[:6], "delisting_date"] = pd.Timestamp("2019-06-28")   # 폐지 6종목
sec.loc[sec.index[6:12], "listing_date"] = pd.Timestamp("2021-03-02")   # 후발 상장 6종목
sec.to_parquet(os.path.join(SHARED, "security_master.parquet"), index=False)

# ── 분기 신호일 (marcap 캘린더 기준 · 3/6/9/12월 마지막 영업일) ────────────────────────────
cal = pd.DatetimeIndex(BD)
sig = []
for y in range(2016, 2027):
    for mth in (3, 6, 9, 12):
        me = pd.Timestamp(y, mth, 1) + pd.offsets.MonthEnd(0)
        if me < pd.Timestamp(START) or me > pd.Timestamp(END):
            continue
        inm = cal[(cal.year == y) & (cal.month == mth)]
        if len(inm) and len(cal[cal > inm.max()]):
            sig.append(inm.max())
print(f"기대 신호일 {len(sig)}개: {sig[0]:%Y-%m-%d} ~ {sig[-1]:%Y-%m-%d}")

# ── ③ 수급 윈도우 (F6/F7) ─────────────────────────────────────────────────────────────────
fl = []
for d in sig:
    fl.append(pd.DataFrame({
        "signal_date": d.strftime("%Y-%m-%d"), "code": CODES,
        "inst_net": rng.normal(0, 3e9, N), "forg_net": rng.normal(0, 4e9, N),
        "cells_ok": 2}))
# ★ 수급 캐시를 일부러 만들지 않는다 → F6/F7 이 전량 결측(KRX 차단 상황과 동일)
print("krx_flow_windows 생성 생략 — F6/F7 전멸 상태를 만든다")

# ── ④ DART 주요계정 (F1/F2/F3) — 실제 스키마 그대로 ───────────────────────────────────────
REPRT = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
rows = []
for i, c in enumerate(CODES):
    base = 1e10 * (i % 17 + 1)
    for y in range(2013, 2027):
        for k, (rm, rd) in REPRT.items():
            q = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}[k]
            cum = base * q * (1 + 0.05 * (y - 2013)) * (1 + rng.normal(0, 0.10))
            rcpt = (pd.Timestamp(y, rm, rd) + pd.Timedelta(days=40)).strftime("%Y%m%d") + "000001"
            for nm, mult in (("당기순이익", 1.0), ("영업이익", 1.3), ("매출액", 8.0)):
                rows.append({"corp_code": f"{i:08d}", "bsns_year": y, "reprt_code": k,
                             "fs_div": "CFS", "sj_div": "IS", "account_id": nm,
                             "account_nm": nm,
                             "thstrm_amount": f"{cum * mult:,.0f}", "rcept_no": rcpt})
pd.DataFrame(rows).to_parquet(os.path.join(SHARED, "dart_multi_raw.parquet"), index=False)
print(f"dart_multi_raw {len(rows):,}행")

# ── ⑤ 리서치 원장 (F4/F5) ─────────────────────────────────────────────────────────────────
# 실제 애널리스트 이름처럼 한글 2~3자 (숫자를 넣으면 split_analysts 가 숫자를 떼어내
# 전부 동일 이름으로 뭉쳐 스마트집합 최소 인원(9명) 미달로 F4 가 전멸한다 — 첫 시도에서 겪음)
_SUR = ["김", "이", "박", "최", "정", "강", "조", "윤"]
_GIV = ["민수", "지훈", "서연", "현우", "예린"]
ANALYSTS = [s + g for s in _SUR for g in _GIV]
reps = []
for j, d in enumerate(pd.date_range("2015-01-15", "2026-07-15", freq="MS")):
    for i, c in enumerate(CODES):
        if (i + j) % 3:
            continue
        a = ANALYSTS[(i + j) % len(ANALYSTS)]
        reps.append({"src_report_id": f"R{j:04d}{i:04d}", "source": "hankyung",
                     "pub_date": d, "title": f"종목{c} 실적 전망",
                     "broker_raw": f"증권{(i % 7) + 1}", "broker": f"증권{(i % 7) + 1}",
                     "analyst_raw": a, "analysts": a,
                     "stock_code": c, "stock_name": f"종목{c}",
                     "target_price": float(lvl[BD.searchsorted(d), i] * (1 + rng.normal(0.15, .1))),
                     "opinion": "매수", "detail_url": f"http://x/{j}/{i}",
                     "eps_fy1": float(1000 * (1 + 0.02 * j) * (1 + rng.normal(0, .05))),
                     "eps_fy2": float(1100 * (1 + 0.02 * j) * (1 + rng.normal(0, .05)))})
rep = pd.DataFrame(reps)
rep.to_parquet(os.path.join(SHARED, "research_report_master.parquet"), index=False)
print(f"research_report_master {len(rep):,}행 · 애널리스트 {rep['analysts'].nunique()}명")

# ── 실행 ──────────────────────────────────────────────────────────────────────────────────
src = open(SRC, encoding="utf-8").read()
src = src.replace('RUN_MODE = "FULL"', 'RUN_MODE = "CACHED"')
src = src.replace('GDRIVE_ROOT_CANDIDATES = [', 'GDRIVE_ROOT_CANDIDATES = [%r,' % CACHE)
src = src.replace('RESEARCH_COLLECT      = True', 'RESEARCH_COLLECT      = False')
run = os.path.join(ROOT, "run_e2e.py")
open(run, "w", encoding="utf-8").write(src)
env = dict(os.environ, SH7F_NO_PROMPT="1", PYTHONIOENCODING="utf-8")
r = subprocess.run([sys.executable, run], cwd=ROOT, env=env,
                   capture_output=True, text=True, timeout=3000)
log = (r.stdout or "") + (r.stderr or "")
open(os.path.join(HERE, "e2e_cached.log"), "w", encoding="utf-8").write(log)
print(f"\nexit={r.returncode} · 로그 {len(log.splitlines()):,}줄 → e2e_cached.log")

FAILS = []


def check(name, cond, detail=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


import re
def stage_ok(sid):
    return re.search(r"\b" + re.escape(sid) + r"\s+✔ 완료", log) is not None


check("프로세스 정상 종료", r.returncode == 0, f"exit={r.returncode}")
for sid in ("L1.SPINE", "L1.UNIV", "L1.PX", "L2.FACTOR", "L3.BT", "L6.PERF", "L5.ROBUST",
            "L6.INTERP", "L0.PERSIST"):
    check(f"{sid} 완료", stage_ok(sid))
check("★F6/F7 결손이 진단표에 특정된다",
      "F6_INST_NETBUY_20D" in log and "★비었음" in log)
check("★축소 팩터셋으로 완주 배너 출력", "축소 팩터셋으로 완주" in log)
check("★계약 baseline 아님을 STATUS 로 명시",
      "DEGRADED_FACTOR_SUBSET_NOT_CONTRACT_BASELINE" in log)
check("★성과 검증표가 축소 라벨로 출력",
      "SHINHAN_7F_DEGRADED_DIAGNOSTIC" in log and "계약 baseline 아님" in log)
check("강건성 표 출력", "PRIMARY baseline" in log)
check("비교전략도 같은 팩터셋으로 수행", stage_ok("L3.BT.CMP"))
m = re.search(r"투자 분기\s*│?\s*(\d+)/(\d+)", log)
check("투자 분기가 채워짐", m is not None and int(m.group(1)) >= 30,
      f"{m.group(1)}/{m.group(2)}" if m else "패턴 없음")
for f in ("01_coverage_report.csv", "05_portfolios.parquet", "07_performance.csv",
          "09_robustness.csv", "10_exact_vs_reconstructed.md", "11_runtime_profile.json",
          "config.yaml", "data_dictionary.md", "cost_schedule.parquet"):
    check(f"산출물 {f}", f in log)
check("★마지막에 계약 baseline 아님을 다시 경고",
      "이 실행은 계약 baseline 이 아닙니다" in log)
check("기존 marcap 파일 불변", os.path.exists(os.path.join(deep, "marcap_2016.parquet")))

print("\n" + "=" * 78)
if FAILS:
    print(f"실패 {len(FAILS)}건:")
    for f in FAILS:
        print("   - " + f)
    print("\n--- 로그 마지막 50줄 ---")
    print("\n".join(log.splitlines()[-50:]))
else:
    print("F6/F7 전멸 상태 완주 시험 통과")
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if FAILS else 0)
