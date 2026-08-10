#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QVF-FUNNEL v1.0 빌더 — 공용 코어 + QVF 전용 계층을 하나의 자립 실행 파일로 조립한다.

TCD v2 와 코어(부트스트랩/커널/유틸/캐시/HTTP/수집/PIT)를 공유하되, 전략 계층은 전부 새로 쓴다.
공유하는 코어를 건드리지 않으므로 TCD v2 빌드 결과는 영향을 받지 않는다.
"""
from __future__ import annotations
import os, re, ast, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "strategies")

# 조립 순서 = 정의 순서. 모듈 최상단에서 참조되는 이름은 반드시 먼저 나와야 한다.
ORDER = [
    # ── L0 코어 (TCD 와 공유) ──────────────────────────────────────────────
    "q00_header.py",            # QVF 전용 설정 헤더
    "01_bootstrap.py",
    "02_kernel.py",
    "03_util.py",
    "04_vault.py",
    "05_http.py",
    "q06_vault_ext.py",         # 다중루트 캐시 + DART 동적 호출한도
    # ── L1 수집 (TCD 와 공유) ─────────────────────────────────────────────
    "10_ingest_universe.py",
    "11_ingest_price.py",
    "12_ingest_dart_fin.py",
    "13_ingest_research.py",
    "14_entity_research.py",
    "20_pit.py",
    # ── QVF 전략 계층 ─────────────────────────────────────────────────────
    "q21_universe.py",          # 분기 캘린더 · PIT 시총 · U-1000
    "q22_axes.py",              # V / Q / F 축
    "q23_filter1.py",           # 1차 필터 3변형 · §5.6 비교
    "q24_dartfact.py",          # ΔNONFIN 하드팩트 · 배제플래그
    "q25_tone.py",              # TONE 분류기 · 직교화 · 인과순서
    "q26_filter2.py",           # 2차 필터 · 3-A 규칙판
    "q40_backtest.py",          # 분기 백테스트 · 비용 모델
    "q50_robust.py",            # 실험 매트릭스 · BH-FDR · 강건성
    "q60_report.py",            # Phase0 · §9 판정 · §10.4 · 산출물
    "q70_contracts.py",         # 계약 Q1~Q12
    "q80_selftest.py",          # 스모크 + 실경로 리허설
    "q90_main.py",              # 오케스트레이터
]

SPEC = dict(
    sid="QVF_FUNNEL_V1",
    fname="qvf_funnel_v1.py",
    name="가치·퀄리티·수급 깔때기 (U-1000 → U-200 → 60~80 → 20~40)",
)


def read(name: str) -> str:
    with open(os.path.join(BUILD, name), encoding="utf-8") as f:
        return f.read()


def strip_head(src: str, keep: bool) -> str:
    if keep:
        return src
    out = []
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith("#!") or s.startswith("# -*- coding") or \
           s.startswith("from __future__ import"):
            continue
        out.append(ln)
    return "\n".join(out)


def build(version: str) -> str:
    parts = []
    for i, fn in enumerate(ORDER):
        parts.append(strip_head(read(fn), keep=(i == 0)))
    blob = "\n".join(parts)
    blob = (blob.replace("@@STRATEGY_ID@@", SPEC["sid"])
                .replace("@@STRATEGY_NAME@@", SPEC["name"])
                .replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", SPEC["fname"]))
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)              # 문법 검사
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:8]}")

    # 최상위에서 '정의 전에 참조'되는 이름을 잡는다. 조립 순서 사고의 대표 증상이며,
    # 문법 검사로는 절대 잡히지 않고 실행 첫 초에 NameError 로 죽는다.
    def _local_binds(node) -> set:
        """컴프리헨션 타깃·람다 인자는 그 식 안에서만 사는 이름이다. 전역 미정의로 오인하면
        정상 코드가 전부 오탐이 된다."""
        out = set()
        for n in ast.walk(node):
            if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in n.generators:
                    for t in ast.walk(gen.target):
                        if isinstance(t, ast.Name):
                            out.add(t.id)
            elif isinstance(n, ast.Lambda):
                a = n.args
                for arg in list(a.args) + list(a.posonlyargs) + list(a.kwonlyargs):
                    out.add(arg.arg)
                if a.vararg:
                    out.add(a.vararg.arg)
                if a.kwarg:
                    out.add(a.kwarg.arg)
        return out

    defined, problems = set(dir(__builtins__)) | set(vars(__builtins__)), []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in tgts:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        defined.add(n.id)
            local = _local_binds(node)
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                    if n.id not in defined and n.id not in local:
                        problems.append((n.id, n.lineno))
        elif isinstance(node, (ast.If, ast.Try, ast.For, ast.While, ast.With, ast.Expr)):
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    defined.add(n.id)
    if problems:
        uniq = sorted({p for p in problems})[:10]
        raise SystemExit(f"{os.path.basename(path)}: 최상위에서 정의 전 참조 → {uniq}")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("qvf1.%Y%m%d.%H%M")
    blob = build(version)
    path = os.path.join(OUT, SPEC["fname"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {SPEC['fname']:<28} {n:>6,}줄  {len(blob)/1024:>7.1f}KB")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
