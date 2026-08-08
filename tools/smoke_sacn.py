#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립된 ARC-SACN 파일을 실제로 실행해 검증한다 (SMOKE, 네트워크·키 불필요)."""
from __future__ import annotations
import os, re, sys, time, shutil, tempfile, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "strategies", "arc_sacn_shared_coverage_network.py")


def patch(src: str, cache: str, mode: str) -> str:
    src = re.sub(r'^RUN_MODE = "FULL"', f'RUN_MODE = "{mode}"', src, flags=re.M)
    src = re.sub(r'^GDRIVE_ROOT_CANDIDATES = \[.*?\n\]',
                 f'GDRIVE_ROOT_CANDIDATES = [{cache!r}]', src, flags=re.M | re.S)
    src = re.sub(r'^GDRIVE_ADOPT_DIRS = \[.*?\n\]',
                 f'GDRIVE_ADOPT_DIRS = [{cache!r}]', src, flags=re.M | re.S)
    src = re.sub(r'^LOCAL_CACHE_ROOT = ".*?"', f'LOCAL_CACHE_ROOT = {cache!r}', src, flags=re.M)
    src = src.replace(
        "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
        "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n"
        "    if os.environ.get('SACN_NO_PIP'): return True, 'skipped'")
    return src


def run(mode: str = "SMOKE", timeout: int = 1200):
    cache = tempfile.mkdtemp(prefix="sacn_smoke_")
    tmp = os.path.join(cache, os.path.basename(TARGET))
    with open(TARGET, encoding="utf-8") as f:
        src = patch(f.read(), cache, mode)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    env = dict(os.environ, SACN_NO_PIP="1", PYTHONWARNINGS="ignore",
               TQDM_DISABLE="1", MPLBACKEND="Agg", ARC_SACN_ROOT=cache)
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, tmp], capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=cache)
        out = (r.stdout or "") + "\n----STDERR----\n" + (r.stderr or "")
        ok = (r.returncode == 0 and "스모크 통과" in out
              and "Traceback" not in (r.stderr or ""))
    except subprocess.TimeoutExpired as e:
        out, ok = f"TIMEOUT ({timeout}s)\n" + (e.stdout or ""), False
    dur = time.time() - t0
    log = os.path.join(ROOT, "build_sacn", f".smoke_{mode}.log")
    with open(log, "w", encoding="utf-8") as f:
        f.write(out)
    shutil.rmtree(cache, ignore_errors=True)
    print(f"{'PASS' if ok else 'FAIL'}  {mode}  {dur:.1f}s  → {log}")
    if not ok:
        tail = [l for l in out.split("\n") if l.strip()][-60:]
        print("\n".join("   " + l for l in tail))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "SMOKE"))
