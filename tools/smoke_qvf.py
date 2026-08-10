#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립된 QVF 파일을 SMOKE 모드로 '실제 실행'해서 검증한다.

문법 검사와 조립 검사가 통과해도 실행 첫 초에 죽는 일이 잦다. 여기서 진짜로 돌린다.
"""
from __future__ import annotations
import os, re, sys, subprocess, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "strategies", "qvf_funnel_v1.py")


def main(mode: str = "SMOKE", timeout: int = 1800) -> int:
    src = open(SRC, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="qvf_smoke_")
    cache = os.path.join(tmp, "cache")
    os.makedirs(cache, exist_ok=True)
    patched = src
    patched = re.sub(r'^RUN_MODE = "FULL"', f'RUN_MODE = "{mode}"', patched, flags=re.M)
    patched = re.sub(r'^GDRIVE_ROOT        = ""',
                     f'GDRIVE_ROOT        = {cache!r}', patched, flags=re.M)
    patched = re.sub(r'^CACHE_MIRROR_ROOTS = \[', 'CACHE_MIRROR_ROOTS = [] or [',
                     patched, flags=re.M)
    path = os.path.join(tmp, "qvf_run.py")
    open(path, "w", encoding="utf-8").write(patched)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    print(f"▶ 실행: {path}  (mode={mode}, cache={cache})")
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=tmp)
    except subprocess.TimeoutExpired:
        print(f"✘ 타임아웃 {timeout}s")
        return 2
    out = (r.stdout or "") + (r.stderr or "")
    tail = out[-14000:]
    print(tail)
    bad = ("Traceback" in out or "실행 중단" in out or "스모크 실패" in out or
           "✘ 실패" in out or r.returncode != 0)
    print("\n" + "=" * 70)
    print(f"returncode={r.returncode}  출력 {len(out):,}자  판정: {'✘ 실패' if bad else '✔ 통과'}")
    if not bad:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"작업 디렉터리 보존: {tmp}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:] or ["SMOKE"])))
