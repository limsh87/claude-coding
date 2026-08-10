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


# ★ 계약 Q6/Q7/Q12 는 '소스에 이런 것이 없다'를 검정한다(부재는 실행으로 증명할 수 없다).
#   그런데 Colab 처럼 파일 대신 셀에 붙여넣는 실행에서는 inspect.getsource 가
#   OSError: source code not available 로 죽는다 — 원셀실행형이 요구사항인데 정작
#   원셀에서 검정이 깨졌다. 그래서 필요한 소스 조각을 '빌드 시점에' 파일 안에 심는다.
SRC_PIN = [
    "score1", "build_u200", "apply_filter2", "build_final_selection", "run_experiment",
    "run_qbacktest", "qvf_sell_tax",
    "Vault.put_table", "Vault.put_blob", "Vault.flush", "Vault.compact",
    "QVFVault", "DartQuota",
]


def _extract_sources(blob: str, names) -> dict:
    """조립본에서 지정한 최상위 함수/클래스/메서드의 소스를 잘라낸다."""
    tree = ast.parse(blob)
    lines = blob.split("\n")
    top = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top[node.name] = node
    out = {}
    missing = []
    for nm in names:
        if "." in nm:
            cls, meth = nm.split(".", 1)
            node = top.get(cls)
            tgt = None
            if node is not None:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == meth:
                        tgt = sub
                        break
        else:
            tgt = top.get(nm)
        if tgt is None:
            missing.append(nm)
            continue
        lo = min([tgt.lineno] + [d.lineno for d in getattr(tgt, "decorator_list", [])])
        out[nm] = "\n".join(lines[lo - 1: tgt.end_lineno])
    if missing:
        raise SystemExit(f"SRC_PIN 대상이 조립본에 없습니다: {missing} "
                         f"(이름을 바꿨다면 SRC_PIN 도 함께 고치세요)")
    return out


# ★ 공용 코어(01~05, 10~14, 20)는 TCD v2 와 같은 파일을 쓴다. 그래서 QVF 가 한 번도 부르지
#   않는 수집기·유틸이 그대로 딸려 들어온다 — 사용자가 지적한 "다른 전략 코드가 그대로 있다"가
#   바로 이것이다. 공용 조각을 지우면 TCD 빌드가 깨지므로, '조립 시점에' 도달 불가능한 최상위
#   정의를 잘라낸다. 조각은 공유하되 산출물에는 안 쓰는 코드가 남지 않는다.
PRUNE_KEEP = {
    # 문자열/데코레이터로도 안 잡히는데 반드시 남겨야 하는 이름이 생기면 여기에 적는다.
}


def _names_used(node) -> set:
    out = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Name):
            out.add(x.id)
        elif isinstance(x, ast.Attribute):
            out.add(x.attr)          # 메서드명 경유 참조까지 보수적으로 센다
    return out


def _strings_in(node) -> set:
    return {x.value.strip() for x in ast.walk(node)
            if isinstance(x, ast.Constant) and isinstance(x.value, str)}


def prune_unreachable(blob: str, extra_roots=()) -> tuple:
    """조립본에서 아무도 도달하지 못하는 최상위 함수/클래스를 제거한다(고정점까지 반복).

    보수적으로 남긴다. 아래 중 하나라도 해당하면 루트로 본다:
      · 모듈 최상위 실행문이 참조하는 이름
      · 데코레이터가 붙은 정의(데코레이터가 레지스트리에 등록하는 부작용을 가진다 — 계약 _q* 가 그렇다)
      · 이름이 문자열 리터럴로 등장하는 정의(globals()[...] · getattr 동적 호출 대비)
    """
    removed = []
    while True:
        tree = ast.parse(blob)
        lines = blob.split("\n")
        defs, roots, strs = {}, set(extra_roots) | set(PRUNE_KEEP), set()
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defs[n.name] = n
                if n.decorator_list:
                    roots.add(n.name)
                    for d in n.decorator_list:
                        roots |= _names_used(d)
            else:
                roots |= _names_used(n)
            strs |= _strings_in(n)
        roots |= {s for s in strs if s in defs}
        edges = {k: _names_used(v) for k, v in defs.items()}

        seen, stack = set(), [r for r in roots if r in defs]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(x for x in edges.get(cur, ()) if x in defs and x not in seen)

        dead = [n for n in defs if n not in seen]
        if not dead:
            return blob, removed

        cut = set()
        for name in dead:
            node = defs[name]
            lo = min([node.lineno] + [d.lineno for d in node.decorator_list])
            removed.append((name, node.end_lineno - lo + 1))
            cut.update(range(lo, node.end_lineno + 1))
        blob = "\n".join(l for i, l in enumerate(lines, 1) if i not in cut)


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

    n0 = blob.count("\n") + 1
    blob, pruned = prune_unreachable(blob, extra_roots={n.split(".")[0] for n in SRC_PIN})
    if pruned:
        tot = sum(ln for _, ln in pruned)
        print(f"  · 미도달 최상위 정의 {len(pruned)}개 / {tot:,}줄 제거 "
              f"({n0:,} → {blob.count(chr(10))+1:,}줄)")
        for nm, ln in sorted(pruned, key=lambda x: -x[1]):
            print(f"      - {nm:<32}{ln:>5}줄")

    # 소스 고정 블록을 계약 계층 '앞'에 끼워 넣는다(정의 순서 = 조립 순서).
    srcmap = _extract_sources(blob, SRC_PIN)
    pin = ["", "# " + "=" * 90,
           "#  빌드 시점에 고정한 소스 조각 — 계약 Q6/Q7/Q12 의 '부재 증명'용.",
           "#  Colab 처럼 셀에 붙여넣어 실행하면 inspect.getsource 가 OSError 로 죽는다.",
           "#  파일 실행/셀 실행 어디서든 같은 검정이 돌도록 여기에 심어 둔다.",
           "# " + "=" * 90,
           "QVF_PINNED_SRC = {"]
    for k, v in srcmap.items():
        pin.append(f"    {k!r}: {v!r},")
    pin.append("}")
    pin.append("")
    marker = "# ╔═════════════════════════════════════════════════════════════════════════════════════════╗\n# ║  L0-H  계약 자동검정"
    idx = blob.find(marker)
    if idx < 0:
        raise SystemExit("계약 계층 시작 지점을 찾지 못했습니다 — SRC_PIN 삽입 위치 불명")
    blob = blob[:idx] + "\n".join(pin) + "\n" + blob[idx:]
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)              # 문법 검사

    # ★ 원셀실행형(R1)을 구조로 지킨다. 셀에 붙여넣으면 소스 파일이 없어
    #   inspect.getsource 가 OSError 로 죽는다 — 실제로 사용자의 Colab 실행을 죽였다.
    #   주석·문자열이 아니라 '실제 호출'만 봐야 하므로 AST 로 검사한다.
    _BAD_ATTR = {"getsource", "getsourcefile", "getsourcelines", "getfile"}
    _allowed_fn = "pinned_src"
    bad_calls, bad_file = [], []

    class _OneCellGuard(ast.NodeVisitor):
        def __init__(self):
            self.fn = []

        def visit_FunctionDef(self, node):
            self.fn.append(node.name)
            self.generic_visit(node)
            self.fn.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Attribute(self, node):
            base = node.value
            if isinstance(base, ast.Name) and base.id.lstrip("_") == "inspect" \
                    and node.attr in _BAD_ATTR:
                if _allowed_fn not in self.fn:
                    bad_calls.append((node.attr, node.lineno))
            self.generic_visit(node)

        def visit_Name(self, node):
            if node.id == "__file__":
                bad_file.append(node.lineno)
            self.generic_visit(node)

    _OneCellGuard().visit(tree)
    if bad_calls:
        a, ln = bad_calls[0]
        raise SystemExit(
            f"{os.path.basename(path)}:{ln} — inspect.{a} 직접 호출 {len(bad_calls)}건.\n"
            f"  Colab 처럼 셀에 붙여넣어 실행하면 소스 파일이 없어 OSError 로 죽습니다.\n"
            f"  pinned_src(\"이름\", 객체) 를 쓰고 그 이름을 SRC_PIN 에 추가하세요.")
    if bad_file:
        raise SystemExit(f"{os.path.basename(path)}:{bad_file[0]} — __file__ 참조 금지"
                         f"(셀 실행에는 __file__ 이 없습니다).")
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
