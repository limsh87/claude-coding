#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCD v3 · 전략 7 XCB 조립기.

검증된 v3 인프라(부트스트랩·커널·유틸·볼트·HTTP·통계·수집·PIT)를 **그대로 재사용**하고,
XCB 전략층(`v3x/`)만 새로 얹어 한 파일로 조립한다.

  · v3/00_header.py        → 제외. XCB 전용 설정(v3x/00_header.py)으로 대체한다.
  · v3/30~90               → 제외. CORE-D 전략층이므로 XCB 에는 죽은 코드다(경량화).
  · v3/01~20 인프라        → 포함.
  · v3x/*.py               → 포함.

조립 결과는 import 없이 위에서 아래로 한 번만 읽히므로 **정의 순서가 곧 파일 순서**다.
파일 번호가 의존 순서를 표현한다.

빌드 시점에 강제하는 것(런타임까지 미루지 않는다):
  1. 문법
  2. 최상위 이름 중복 정의   — 조립 사고의 대표 증상
  3. 미정의 전역 이름 참조   — 순서를 잘못 놓으면 NameError 가 2시간 뒤에 난다
  4. 원칙 2  TP 는 clip×clip  (`z × z` 금지)
  5. 원칙 3  groupby.apply 금지 (셀 정규화 경로)
  6. 원칙 1  PIT 결합은 merge_asof backward
  7. 절대1원칙  드라이브 삭제 API 부재
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "v3")
SRC = os.path.join(ROOT, "v3x")
OUT = os.path.join(ROOT, "strategies", "tcd_v3_07_xcb.py")

# v3 인프라 중 XCB 가 재사용하는 조각. 순서가 곧 의존 순서다.
CORE_REUSE = [
    "01_bootstrap.py",
    "02_kernel.py",
    "03_util.py",
    "04_vault.py",
    "05_http.py",
    "06_statv3.py",
    "10_ingest_universe.py",
    "11_ingest_price.py",
    "12_ingest_dart.py",
    "15_mcap.py",
    "16_ingest_research.py",
    "17_entity_research.py",
    "20_pit_v3.py",
    # 백테스트 엔진은 전략 비의존이다 — 체결·비용·세금·상폐 -100%·청산게이트 전부
    # XCB 사양(§15.3)과 동일하므로 그대로 재사용한다. 반면 60_robust/70_report 는
    # CORE-D 고유 TP 이름을 참조하므로 포함하지 않고 XCB 판으로 새로 쓴다(죽은 코드 방지).
    "50_backtest.py",
]

BANNER = """
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [{i:02d}/{n:02d}]  {name}{tag}
# ═══════════════════════════════════════════════════════════════════════════════════════════════
"""


def _strip(txt: str, first: bool) -> str:
    if first:
        return txt
    return "\n".join(
        ln for ln in txt.split("\n")
        if not ln.startswith(("#!/usr/bin/env", "# -*- coding:"))
        and not ln.startswith("from __future__ import")
    )


def collect() -> list[tuple[str, str, str]]:
    """(표시이름, 절대경로, 태그) 목록을 조립 순서대로 만든다."""
    if not os.path.isdir(SRC):
        raise SystemExit(f"v3x/ 소스 디렉터리가 없습니다: {SRC}")
    xs = sorted(f for f in os.listdir(SRC) if f.endswith(".py"))
    if not xs:
        raise SystemExit("v3x/ 에 소스가 없습니다.")

    head = [f for f in xs if f.startswith("00_")]
    if not head:
        raise SystemExit("v3x/00_header.py 가 없습니다 — 설정 블록이 최상단이어야 합니다.")

    out: list[tuple[str, str, str]] = []
    for f in head:
        out.append((f, os.path.join(SRC, f), "  [XCB]"))
    for f in CORE_REUSE:
        p = os.path.join(CORE, f)
        if not os.path.exists(p):
            raise SystemExit(f"v3 인프라 조각이 없습니다: {p}")
        out.append((f, p, "  [v3 코어 재사용]"))
    for f in xs:
        if f in head:
            continue
        out.append((f, os.path.join(SRC, f), "  [XCB]"))
    return out


# ── 빌드 시 소스 검사 ───────────────────────────────────────────────────────────────────────────

def check_duplicates(tree: ast.AST, body: str) -> list[str]:
    seen: dict[str, int] = {}
    dups: list[str] = []
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append(f"{node.name}  (줄 {seen[node.name]} ↔ {node.lineno})")
            seen[node.name] = node.lineno
    return dups


def check_undefined(tree: ast.AST) -> list[str]:
    """최상위에서 정의되는 이름을 모으고, 함수 밖(모듈 실행부)에서 참조되는 미정의 이름을 찾는다.

    함수 본문 안의 이름은 호출 시점에 정의되어 있으면 되므로 검사하지 않는다.
    모듈 실행부(데코레이터·기본값·최상위 표현식)만 본다 — 여기서 나는 NameError 가
    '2시간 수집 후 크래시' 의 주범이다.
    """
    defined: set[str] = set(dir(builtins))
    errs: list[str] = []

    def bind(node: ast.AST) -> None:
        for n in ast.walk(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                defined.add(n.id)
            elif isinstance(n, ast.alias):
                defined.add((n.asname or n.name).split(".")[0])
            elif isinstance(n, ast.arg):
                defined.add(n.arg)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                defined.add(n.name)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                defined.update(n.names)

    # 1패스: 전역에 바인딩되는 모든 이름 수집(함수 내부 지역까지 포함해 보수적으로)
    bind(tree)

    # 2패스: 모듈 실행부에서만 Load 되는 이름 검사
    for node in tree.body:  # type: ignore[attr-defined]
        targets: list[ast.AST] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            targets = list(node.decorator_list) + list(node.args.defaults)
        elif isinstance(node, ast.ClassDef):
            targets = list(node.decorator_list) + list(node.bases)
        else:
            targets = [node]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                    if n.id not in defined:
                        errs.append(f"{n.id}  (줄 {n.lineno})")

    # 3패스: **함수 본문에서 호출되는 전역 이름**도 검사한다.
    #   ★ 2패스만으로는 부족하다. `Path.home()` 이나 `fetch_research_all(...)` 처럼
    #     함수 안에서만 쓰이는 미정의 이름은 조립·문법 검사를 전부 통과하고
    #     **수집을 두 시간 한 뒤 NameError** 로 죽는다. 실제로 그런 결함을 세 개 만들었다.
    #   지역 변수와 구분하기 위해 각 함수의 지역 바인딩을 따로 모아 제외한다.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local: set[str] = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                local.add(n.id)
            elif isinstance(n, ast.arg):
                local.add(n.arg)
            elif isinstance(n, ast.alias):
                local.add((n.asname or n.name).split(".")[0])
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(n.name)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                local.add(n.name)
            elif isinstance(n, (ast.comprehension,)):
                for t2 in ast.walk(n.target):
                    if isinstance(t2, ast.Name):
                        local.add(t2.id)
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                if n.id not in defined and n.id not in local:
                    errs.append(f"{n.id}  (함수 {node.name} 내부, 줄 {n.lineno})")
    return sorted(set(errs))


def check_principles(body: str) -> list[str]:
    """명세 §1 의 원칙을 소스 검사로 강제한다."""
    errs: list[str] = []
    lines = body.split("\n")

    def hits(pat: str) -> list[int]:
        rx = re.compile(pat)
        out = []
        for i, ln in enumerate(lines, 1):
            s = ln.split("#")[0]
            if rx.search(s):
                out.append(i)
        return out

    # 원칙 3: 셀 정규화에 groupby.apply 금지
    ga = hits(r"\.groupby\([^)]*\)\s*\.\s*apply\s*\(")
    if ga:
        errs.append(f"[원칙3] groupby.apply 사용 — 줄 {ga[:5]} (transform/rank 로 대체할 것)")

    # 원칙 2: TP 는 clip×clip. 최소 한 곳에 np.maximum(...,0.0) 곱이 있어야 한다.
    if not re.search(r"np\.maximum\(", body):
        errs.append("[원칙2] np.maximum 절단이 소스에 없습니다 — TP 가 clip×clip 이 아닐 수 있습니다")

    # 원칙 1: PIT 결합은 merge_asof backward
    if "merge_asof" not in body:
        errs.append("[원칙1] merge_asof 가 없습니다 — PIT 결합 경로가 없습니다")
    for i, ln in enumerate(lines, 1):
        if "merge_asof" in ln.split("#")[0]:
            window = "\n".join(lines[i - 1:i + 12])
            if "direction" in window and "forward" in window:
                errs.append(f"[원칙1] merge_asof direction='forward' 의심 — 줄 {i} (미래참조)")

    # 절대1원칙: 사용자 데이터 삭제 경로 부재.
    #   ★ 유일한 예외는 **우리가 만든 잠금 파일**(`lp`) 해제다. 잠금은 우리 소유이고
    #     해제하지 않으면 다음 실행이 영구히 막힌다. 그 외 인자에 대한 삭제는 전부 금지한다.
    for i, ln in enumerate(lines, 1):
        s = ln.split("#")[0]
        m = re.search(r"\b(os\.remove|os\.unlink|shutil\.rmtree)\s*\(\s*([A-Za-z_][\w\.]*)",
                      s)
        if m and m.group(2) != "lp":
            errs.append(f"[절대1원칙] 파일 삭제 호출 — 줄 {i}: {ln.strip()[:90]}")
    return errs


# 사용처가 없어도 **남겨야 하는** 이름. 사용자가 직접 부를 수 있는 진입점과
# 계약 검정이 이름으로 찾는 것들이다.
KEEP_UNUSED = {"main", "run_xcb", "smoke_xcb", "contracts_xcb"}


def prune_dead(body: str) -> tuple[str, list[str]]:
    """최상위 def/class 중 **어디에서도 참조되지 않는 것**을 잘라낸다.

    v3 코어는 다른 전략(CORE-D)과 공유하므로 원본 조각을 건드리지 않는다.
    XCB 가 쓰지 않는 코어 함수는 조립 시점에만 제거한다 — 원본은 그대로 남는다.

    보수적으로만 자른다:
      · ast 상 Name/Attribute Load 참조가 0회
      · 이름이 **문자열 리터럴로도** 등장하지 않음 (getattr·디스패치표 방어)
      · KEEP_UNUSED 에 없음
    하나를 지우면 그것만 부르던 다른 함수가 죽으므로 고정점까지 반복한다.
    """
    removed: list[str] = []
    for _ in range(12):
        tree = ast.parse(body)
        defs = {n.name: n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        strs: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                strs.update(n.value.split())
        # 자기 자신 안에서만 쓰이는 재귀 호출은 '사용'이 아니다 → 정의 밖 참조만 센다.
        outside: dict[str, int] = {nm: 0 for nm in defs}
        for top in tree.body:
            skip = top.name if isinstance(
                top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
            for x in ast.walk(top):
                nm = None
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
                    nm = x.id
                elif isinstance(x, ast.Attribute):
                    nm = x.attr
                if nm in outside and nm != skip:
                    outside[nm] += 1
        cand = [(nm, node) for nm, node in defs.items()
                if nm not in KEEP_UNUSED and not nm.startswith("__")
                and outside[nm] == 0 and nm not in strs]
        # ★ 마지막 안전망 — **텍스트 수준**에서 한 번 더 본다.
        #   getattr("naver_enrich_detail") 처럼 문자열 안에 박힌 호출, 주석 속 참조,
        #   f-string 조각까지 ast 만으로는 놓칠 수 있다. 이름의 전체 등장 횟수가
        #   '자기 정의 구간 안에서의 등장 횟수'와 같을 때만 지운다.
        src_lines = body.split("\n")
        dead = []
        for nm, node in cand:
            pat = re.compile(r"\b" + re.escape(nm) + r"\b")
            total = len(pat.findall(body))
            own = len(pat.findall("\n".join(src_lines[node.lineno - 1:node.end_lineno])))
            if total == own:
                dead.append(node)
        if not dead:
            break
        lines = body.split("\n")
        cut: set[int] = set()
        for node in dead:
            removed.append(node.name)
            s = node.lineno - 1
            for d in getattr(node, "decorator_list", []):
                s = min(s, d.lineno - 1)
            # 바로 위에 붙은 주석·데코레이터도 함께 지운다(고아 주석 방지).
            while s > 0 and lines[s - 1].lstrip().startswith("#"):
                s -= 1
            cut.update(range(s, node.end_lineno))
        body = "\n".join(ln for i, ln in enumerate(lines) if i not in cut)
    return body, removed


def check_arity(tree: ast.AST) -> list[str]:
    """최상위 함수 호출의 **인자 개수·키워드 이름**을 정의와 대조한다.

    ★ 왜 필요한가: RX10_policy(runner) 가 runner(Q, months=..., label=...) 로 부르는데
      호출부가 months 를 안 받는 러너를 넘겨 TypeError 로 죽었다. 이런 불일치는
      **수집이 다 끝난 6시간 뒤**에 처음 터진다. 조립 시점에 잡는다.
    """
    sigs: dict[str, ast.arguments] = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs[n.name] = n.args
    errs: list[str] = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
            continue
        a = sigs.get(n.func.id)
        if a is None:
            continue
        names = [x.arg for x in (a.posonlyargs + a.args)]
        n_req = len(names) - len(a.defaults)
        n_pos = len(n.args)
        if any(isinstance(x, ast.Starred) for x in n.args):
            continue                                   # *args 전개는 셀 수 없다
        kw = {k.arg for k in n.keywords if k.arg is not None}
        if any(k.arg is None for k in n.keywords):
            continue                                   # **kwargs 전개
        if n_pos > len(names) and a.vararg is None:
            errs.append(f"{n.func.id}(): 위치인자 {n_pos}개 > 정의 {len(names)}개 "
                        f"— 줄 {n.lineno}")
            continue
        if a.kwarg is None:
            valid = set(names) | {x.arg for x in a.kwonlyargs}
            bad = kw - valid
            if bad:
                errs.append(f"{n.func.id}(): 없는 키워드 {sorted(bad)} — 줄 {n.lineno}")
                continue
        supplied = set(names[:n_pos]) | kw
        missing = [x for x in names[:n_req] if x not in supplied]
        if missing:
            errs.append(f"{n.func.id}(): 필수인자 {missing} 누락 — 줄 {n.lineno}")
    return errs


def main() -> int:
    items = collect()
    parts, n = [], len(items)
    for i, (name, path, tag) in enumerate(items, 1):
        txt = open(path, encoding="utf-8").read()
        txt = _strip(txt, first=(i == 1))
        if i > 1:
            parts.append(BANNER.format(i=i, n=n, name=name, tag=tag))
        parts.append(txt.rstrip() + "\n")
    body = "\n".join(parts)
    raw_lines = len(body.splitlines())

    try:
        ast.parse(body)
    except SyntaxError as e:
        print(f"✘ 구문 오류(가지치기 전): 줄 {e.lineno}: {e.msg}", file=sys.stderr)
        return 2
    body, pruned = prune_dead(body)

    try:
        tree = ast.parse(body)
    except SyntaxError as e:
        print(f"✘ 구문 오류: 줄 {e.lineno}: {e.msg}", file=sys.stderr)
        ctx = body.split("\n")[max(0, (e.lineno or 1) - 5):(e.lineno or 1) + 4]
        print("\n".join(ctx), file=sys.stderr)
        return 2

    fatal = 0
    dups = check_duplicates(tree, body)
    if dups:
        print("✘ 최상위 이름 중복 정의:", file=sys.stderr)
        for d in dups[:12]:
            print(f"    {d}", file=sys.stderr)
        fatal += 1

    und = check_undefined(tree)
    if und:
        print("✘ 모듈 실행부에서 미정의 이름 참조:", file=sys.stderr)
        for u in und[:12]:
            print(f"    {u}", file=sys.stderr)
        fatal += 1

    ar = check_arity(tree)
    if ar:
        print("✘ 함수 호출 시그니처 불일치:", file=sys.stderr)
        for a in ar[:12]:
            print(f"    {a}", file=sys.stderr)
        fatal += 1

    pr = check_principles(body)
    if pr:
        print("✘ 원칙 위반:", file=sys.stderr)
        for p in pr[:12]:
            print(f"    {p}", file=sys.stderr)
        fatal += 1

    if fatal:
        return 3

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, OUT)
    h = hashlib.sha1(body.encode()).hexdigest()[:12]
    nl = len(body.splitlines())
    print(f"조립 완료: {os.path.relpath(OUT, ROOT)}  {nl:,}줄 / {len(body)/1e3:.0f}KB / sha1:{h}")
    print(f"  XCB 전략층 {sum(1 for _, p, _ in items if p.startswith(SRC))}조각 · "
          f"v3 코어 재사용 {len(CORE_REUSE)}조각")
    if pruned:
        print(f"  미사용 정의 {len(pruned)}건 가지치기 (−{raw_lines - nl:,}줄): "
              + ", ".join(sorted(pruned)[:8]) + (" …" if len(pruned) > 8 else ""))
    print("  검사 통과: 문법 · 중복정의 · 미정의이름 · 원칙1/2/3 · 절대1원칙")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
