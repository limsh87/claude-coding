#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립본 정적 점검 — 여러 모듈을 이어붙였을 때만 드러나는 사고를 잡는다.

잡는 것:
  ① 문법 오류 / 최상위 중복 정의 (build_ncq.py 가 이미 잡지만 재확인)
  ② 정의되지 않은 전역 이름 사용 (모듈 간 이름 불일치의 대표 증상)
  ③ 계약(_CONTRACT.md §5)이 요구한 함수의 부재
  ④ 늦은 위치의 import (조립 순서 사고)
  ⑤ 위험 패턴: `is True` / `is False` 로 numpy bool 비교, print( 직접 호출
"""
from __future__ import annotations
import ast, builtins, os, re, sys, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "strategies", "arc_ncq_v1_new_coverage_quality.py")

REQUIRED = [
    # 스파인
    "build_marketcap_panel", "build_ncq_universe", "universe_funnel",
    "collect_report_index", "coverage_completeness", "build_coverage_events", "audit_events",
    "freeze_configs", "collect_event_texts", "score_texts", "build_signal_panel",
    "run_overlap_backtest", "perf_stats", "bench_universe_ew", "bench_index", "excess_series",
    "ncq_configure_sources", "ncq_enrich_security_master", "ncq_build_shares_history",
    "fetch_dart_shares", "resolve_gdrive_root", "degrade", "manifest_put",
    # 리프
    "run_prereg_tests", "run_stat_suite", "run_sensitivity", "report_robustness",
    "report_structural_risks",
    "report_performance", "report_coverage_diagnostics", "report_diagnostics",
    "report_interpretation", "report_dataflow_map", "report_headline",
    "write_html_report", "write_coverage_html", "write_manifest", "offer_download",
    "run_contract_tests", "run_canaries", "run_rehearsal", "run_selftest",
    # 오케스트레이터
    "main",
]


def collect_defined(tree: ast.AST) -> set:
    """모듈 최상위에서 바인딩되는 모든 이름."""
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    out.add(n.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    out.add(sub.name)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for a in sub.names:
                        out.add((a.asname or a.name).split(".")[0])
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        for n in ast.walk(t):
                            if isinstance(n, ast.Name):
                                out.add(n.id)
    return out


class LocalScope(ast.NodeVisitor):
    """함수 안에서 로컬로 바인딩되는 이름 + 전역으로 읽는 이름을 모은다."""

    def __init__(self):
        self.loads: set = set()

    def visit_FunctionDef(self, node):
        self._fn(node)

    def visit_AsyncFunctionDef(self, node):
        self._fn(node)

    def visit_Lambda(self, node):
        self._fn(node, is_lambda=True)

    def _fn(self, node, is_lambda=False):
        local = set()
        args = node.args
        for a in (list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)):
            local.add(a.arg)
        if args.vararg:
            local.add(args.vararg.arg)
        if args.kwarg:
            local.add(args.kwarg.arg)
        body = node.body if isinstance(node.body, list) else [node.body]
        for sub in body:
            for n in ast.walk(sub):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    local.add(n.name)
                elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    local.add(n.id)
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        local.add((a.asname or a.name).split(".")[0])
                elif isinstance(n, ast.ExceptHandler) and n.name:
                    local.add(n.name)
                elif isinstance(n, (ast.Global, ast.Nonlocal)):
                    local.update(n.names)
                elif isinstance(n, ast.arg):
                    local.add(n.arg)
        for sub in body:
            for n in ast.walk(sub):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in local:
                    self.loads.add(n.id)
        for sub in body:
            for n in ast.walk(sub):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and n is not node:
                    pass


def main() -> int:
    if not os.path.exists(TARGET):
        print(f"조립본이 없습니다: {TARGET}  →  python3 tools/build_ncq.py 를 먼저 실행하세요")
        return 2
    src = open(TARGET, encoding="utf-8").read()
    tree = ast.parse(src, filename=TARGET)
    problems = 0

    defined = collect_defined(tree)
    builtin = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "self", "cls"}

    sc = LocalScope()
    for node in tree.body:
        sc.visit(node)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            sc._fn(node)

    unknown = sorted(n for n in sc.loads if n not in defined and n not in builtin)
    if unknown:
        problems += 1
        print(f"✘ 정의되지 않은 전역 이름 {len(unknown)}개:")
        for n in unknown[:40]:
            m = re.search(rf"\b{re.escape(n)}\b", src)
            ln = src[:m.start()].count("\n") + 1 if m else 0
            print(f"    - {n}   (첫 등장 ~{ln}행)")
    else:
        print("✔ 정의되지 않은 전역 이름 없음")

    missing = [f for f in REQUIRED if f not in defined]
    if missing:
        problems += 1
        print(f"✘ 계약이 요구한 함수 부재 {len(missing)}개: {missing}")
    else:
        print(f"✔ 계약 필수 함수 {len(REQUIRED)}개 전부 존재")

    late = [(getattr(n, "module", None) or ",".join(a.name for a in n.names), n.lineno)
            for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and n.lineno > 400]
    if late:
        print(f"⚠ 늦은 최상위 import {len(late)}건: {late[:6]}")

    bad_is = [(i + 1, l.strip()) for i, l in enumerate(src.split("\n"))
              if re.search(r"\bis\s+(True|False)\b", l)]
    if bad_is:
        print(f"⚠ `is True/False` 비교 {len(bad_is)}건 (numpy bool 은 이 비교가 조용히 실패합니다):")
        for ln, t in bad_is[:8]:
            print(f"    {ln}: {t[:96]}")

    raw_print = [(i + 1, l.strip()) for i, l in enumerate(src.split("\n"))
                 if re.search(r"(?<![\w_.])print\(", l) and "_safe_print" not in l
                 and not l.strip().startswith("#")]
    if raw_print:
        print(f"⚠ print( 직접 호출 {len(raw_print)}건 (윈도우 cp949 콘솔에서 죽을 수 있음):")
        for ln, t in raw_print[:8]:
            print(f"    {ln}: {t[:96]}")

    r = subprocess.run([sys.executable, "-m", "pyflakes", TARGET],
                       capture_output=True, text=True)
    lines = [l for l in (r.stdout or "").split("\n")
             if l.strip() and "imported but unused" not in l and "unable to detect undefined" not in l]
    if lines:
        print(f"⚠ pyflakes {len(lines)}건:")
        for l in lines[:30]:
            print("    " + l.replace(TARGET + ":", ""))
    else:
        print("✔ pyflakes 지적 없음")

    print(f"\n조립본 {src.count(chr(10))+1:,}줄 · 최상위 정의 {len(defined)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
