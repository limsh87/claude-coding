#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""U250 팩터 검정 빌더 — 공용 코어(build/) + U250 계층(u250/) → 자립 실행 파일 1개.

명세서 §0 규약 ③ "원클릭 완전내장형 — 외부 수동 준비물 없이 단독 실행 가능" 을 만족시킨다.
공용 코어는 TCD v2 와 같은 파일을 쓴다 — 그래야 같은 구글드라이브 캐시(_shared)를
그대로 재활용할 수 있다. 캐시를 나누면 이미 모아둔 데이터를 또 받게 된다.
"""
from __future__ import annotations
import os, sys, ast, datetime, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "build")
U250 = os.path.join(ROOT, "u250")
OUT = os.path.join(ROOT, "strategies")

# 공용 코어에서 그대로 가져오는 조각 (헤더는 U250 전용으로 교체)
CORE_PARTS = ["01_bootstrap.py", "02_kernel.py", "03_util.py", "04_vault.py", "05_http.py"]
U250_PARTS = ["00_header.py", "06_spec.py", "07_lake.py", "11_data.py", "12_dart.py",
              "10_universe.py", "20_engine.py", "30_phase0.py", "40_factors.py",
              "50_gates.py", "60_report.py", "90_main.py"]
TARGET = "u250_factor_test_v1.py"


def strip(src: str, keep_header: bool) -> str:
    if keep_header:
        return src
    out = []
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith("#!") or s.startswith("# -*- coding") or s.startswith("from __future__ import"):
            continue
        out.append(ln)
    return "\n".join(out)


def build() -> str:
    parts, order = [], []
    order.append((os.path.join(U250, U250_PARTS[0]), True))
    order += [(os.path.join(CORE, f), False) for f in CORE_PARTS]
    order += [(os.path.join(U250, f), False) for f in U250_PARTS[1:]]
    for path, hdr in order:
        with open(path, encoding="utf-8") as fh:
            parts.append(strip(fh.read(), hdr))
    blob = "\n".join(parts)
    ver = f"u250-{datetime.date.today():%Y%m%d}-{hashlib.sha1(blob.encode()).hexdigest()[:7]}"
    blob = blob.replace("@@BUILD_VERSION@@", ver).replace("@@FILENAME@@", TARGET)
    if "@@" in blob:
        import re
        left = sorted(set(re.findall(r"@@\w+@@", blob)))
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit("중복 최상위 정의: " +
                         ", ".join(f"{n} (L{a} ↔ L{b})" for n, a, b in dups))
    print(f"  ✔ {os.path.basename(path)}  {len(src.splitlines()):,}행 · "
          f"{len(src)/1024:.0f}KB · 최상위 정의 {len(seen)}개")


def main():
    os.makedirs(OUT, exist_ok=True)
    blob = build()
    p = os.path.join(OUT, TARGET)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(blob)
    check(p)
    print(f"\n조립 완료 → strategies/{TARGET}")


if __name__ == "__main__":
    main()
