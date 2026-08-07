#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립된 전략 파일을 실제로 실행해서 검증한다 (SMOKE 모드, 네트워크·키 불필요)."""
from __future__ import annotations
import os, re, sys, subprocess, tempfile, shutil, glob, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "strategies")


def patch(src: str, cache_dir: str) -> str:
    src = re.sub(r'^RUN_MODE = "FULL"', 'RUN_MODE = "SMOKE"', src, flags=re.M)
    src = re.sub(r'^GDRIVE_ROOT\s*=\s*".*?"', f'GDRIVE_ROOT       = "{cache_dir}"', src, flags=re.M)
    src = re.sub(r'^LOCAL_CACHE_ROOT\s*=\s*".*?"',
                 f'LOCAL_CACHE_ROOT  = "{cache_dir}"', src, flags=re.M)
    src = re.sub(r'^GDRIVE_ADOPT_DIRS = \[.*?\]', f'GDRIVE_ADOPT_DIRS = ["{cache_dir}"]',
                 src, flags=re.M | re.S)
    # 오프라인: 의존성 설치 시도를 끈다 (컨테이너는 이미 설치돼 있음)
    src = src.replace("def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
                      "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n"
                      "    if os.environ.get('TCD_NO_PIP'): return True, 'skipped'")
    return src


def run_one(path: str) -> tuple[bool, str, float]:
    name = os.path.basename(path)
    cache = tempfile.mkdtemp(prefix="tcdsmoke_")
    tmp = os.path.join(cache, name)
    with open(path, encoding="utf-8") as f:
        src = patch(f.read(), cache)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    env = dict(os.environ, TCD_NO_PIP="1", PYTHONWARNINGS="ignore",
               MPLBACKEND="Agg", TQDM_DISABLE="1")
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, tmp], capture_output=True, text=True,
                           timeout=900, env=env, cwd=cache)
        out = (r.stdout or "") + "\n----STDERR----\n" + (r.stderr or "")
        ok = (r.returncode == 0 and "스모크 통과" in out and "Traceback" not in (r.stderr or ""))
    except subprocess.TimeoutExpired:
        out, ok = "TIMEOUT (900s)", False
    dur = time.time() - t0
    logp = os.path.join(ROOT, "build", f".smoke_{name}.log")
    with open(logp, "w", encoding="utf-8") as f:
        f.write(out)
    shutil.rmtree(cache, ignore_errors=True)
    return ok, out, dur


def main():
    targets = sys.argv[1:] or sorted(glob.glob(os.path.join(OUT, "*.py")))
    fails = []
    for p in targets:
        ok, out, dur = run_one(p)
        print(f"{'✔' if ok else '✘'} {os.path.basename(p):<44} {dur:6.1f}s")
        if not ok:
            fails.append(os.path.basename(p))
            tail = [ln for ln in out.split("\n") if ln.strip()][-45:]
            print("   " + "\n   ".join(tail))
            break
    print(f"\n{len(targets)-len(fails)}/{len(targets)} 통과")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
