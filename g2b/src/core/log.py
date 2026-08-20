# -*- coding: utf-8 -*-
"""로그 · 표 출력 · 단계 타이머. 조용한 실패를 만들지 않는 것이 유일한 목표다."""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.config import VERBOSE
# ── /PACKAGE IMPORTS ──

import sys
import time
import unicodedata
from contextlib import contextmanager
from typing import Sequence, List, Optional

_T0 = time.time()


def _w(s: str) -> int:
    """동아시아 전각 문자를 2칸으로 계산 — 안 하면 한글 표가 전부 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))


def _pad(s: str, width: int, align: str = "l") -> str:
    s = str(s)
    gap = max(0, width - _w(s))
    if align == "r":
        return " " * gap + s
    if align == "c":
        return " " * (gap // 2) + s + " " * (gap - gap // 2)
    return s + " " * gap


class Log:
    def _emit(self, tag: str, msg: str) -> None:
        el = time.time() - _T0
        sys.stdout.write(f"[{el:7.1f}s] {tag} {msg}\n")
        sys.stdout.flush()

    def info(self, m: str) -> None:
        if VERBOSE:
            self._emit("   ", m)

    def ok(self, m: str) -> None:
        self._emit("✔  ", m)

    def warn(self, m: str) -> None:
        self._emit("⚠  ", m)

    def err(self, m: str) -> None:
        self._emit("✖  ", m)

    def debug(self, m: str) -> None:
        if VERBOSE:
            self._emit("·  ", m)

    def banner(self, title: str, sub: str = "") -> None:
        bar = "═" * 92
        sys.stdout.write(f"\n{bar}\n  {title}\n" + (f"  {sub}\n" if sub else "") + f"{bar}\n")
        sys.stdout.flush()

    def table(self, rows: Sequence[Sequence], head: Sequence[str],
              align: Optional[Sequence[str]] = None, title: str = "",
              max_rows: int = 200) -> None:
        rows = [list(map(lambda x: "" if x is None else str(x), r)) for r in rows]
        if not rows:
            if title:
                sys.stdout.write(f"\n  {title}\n    (행 없음)\n")
            return
        n = len(head)
        align = list(align) if align else ["l"] * n
        align = (align + ["l"] * n)[:n]
        widths = [max(_w(head[i]), *(_w(r[i]) if i < len(r) else 0 for r in rows)) for i in range(n)]
        out: List[str] = []
        if title:
            out.append(f"\n  {title}")
        out.append("  " + " │ ".join(_pad(head[i], widths[i], "c") for i in range(n)))
        out.append("  " + "─┼─".join("─" * widths[i] for i in range(n)))
        for r in rows[:max_rows]:
            out.append("  " + " │ ".join(_pad(r[i] if i < len(r) else "", widths[i], align[i])
                                         for i in range(n)))
        if len(rows) > max_rows:
            out.append(f"  … 외 {len(rows) - max_rows:,}행")
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

    @contextmanager
    def stage(self, name: str):
        t0 = time.time()
        self.banner(name)
        try:
            yield
        except Exception as e:                                  # noqa: BLE001
            self.err(f"{name} 실패 — {type(e).__name__}: {e}")
            raise
        finally:
            self.info(f"↳ {name} 완료 ({time.time() - t0:.1f}s)")


LOG = Log()
