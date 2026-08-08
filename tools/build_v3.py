#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3/*.py 를 하나의 실행 파일로 조립한다.

단일 파일 배포가 요구사항이지만(한 셀 실행), 8천 줄을 한 파일에서 편집하는 것은
유지보수가 불가능하다. 그래서 소스는 섹션별로 나눠 두고 이 스크립트가 사전순으로
이어붙인다. 조립 결과는 import 없이 위에서 아래로 한 번만 읽히므로 정의 순서가 곧
파일 순서다 — 파일 번호가 의존 순서를 표현한다.
"""
from __future__ import annotations
import ast
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "v3")
OUT = os.path.join(ROOT, "strategies", "tcd_v3_01_core_d.py")

BANNER = """
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [{i:02d}/{n:02d}]  {name}
# ═══════════════════════════════════════════════════════════════════════════════════════════════
"""


def main() -> int:
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".py"))
    if not files:
        print("v3/ 에 소스가 없습니다.", file=sys.stderr)
        return 1
    parts, n = [], len(files)
    for i, f in enumerate(files, 1):
        txt = open(os.path.join(SRC, f), encoding="utf-8").read()
        if i > 1:
            # 첫 파일 외에는 shebang/coding/`from __future__` 를 제거한다.
            # __future__ 임포트는 파일 최상단에만 허용되므로 남겨두면 SyntaxError 가 난다.
            lines = [ln for ln in txt.split("\n")
                     if not ln.startswith(("#!/usr/bin/env", "# -*- coding:"))
                     and not ln.startswith("from __future__ import")]
            txt = "\n".join(lines)
            parts.append(BANNER.format(i=i, n=n, name=f))
        parts.append(txt.rstrip() + "\n")
    body = "\n".join(parts)

    try:
        ast.parse(body)
    except SyntaxError as e:
        print(f"조립 결과 구문 오류: {e.filename}:{e.lineno}: {e.msg}", file=sys.stderr)
        ctx = body.split("\n")[max(0, (e.lineno or 1) - 4):(e.lineno or 1) + 3]
        print("\n".join(ctx), file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, OUT)
    h = hashlib.sha1(body.encode()).hexdigest()[:12]
    print(f"조립 완료: {os.path.relpath(OUT, ROOT)}  "
          f"{len(body.splitlines()):,}줄 / {len(body)/1e3:.0f}KB / sha1:{h}")
    print("  섹션: " + ", ".join(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
