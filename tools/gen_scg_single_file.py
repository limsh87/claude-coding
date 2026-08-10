#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smart_consensus_gap/ 패키지 + 오케스트레이터를 **하나의 자립 실행 파일**로 조립한다.

TCD v2 의 tools/build.py 와 같은 목적이다 — "붙여넣으면 그대로 돌아가는 파일 하나".
다만 SCG 패키지는 build/*.py 조각(순수 텍스트 concat 용으로 미리 설계됨)이 아니라
실제 `from . import x as y` 상대 임포트를 쓰는 정규 파이썬 패키지이므로, 병합 시
다음을 처리해야 한다:

  1. 패키지 내부 import 문(단일행/괄호multi-line/백슬래시 연속 전부)을 제거한다.
  2. `from . import contracts as C` 처럼 **별칭으로만** 쓰인 모듈은 병합 후에도
     `C.fp_quarter(...)` 호출이 그대로 동작해야 한다 → 각 모듈의 최상위 이름을
     ast 로 뽑아 `C = SimpleNamespace(fp_quarter=fp_quarter, ...)` 형태의 별칭을
     "이미 별칭이 필요한 실제 사용처가 있는" 모듈에 대해서만 생성한다.
  3. 오케스트레이터(run_smart_consensus_gap.py)의 `_clean()` 은 normalize.py 의
     `_clean()` 과 완전히 다른 함수인데 이름이 같다 — 단일 네임스페이스로 합치면
     나중에 로드되는 쪽이 앞의 정의를 덮어써 조용한 버그가 된다. 오케스트레이터
     쪽만 `_clean_result` 로 이름을 바꿔 충돌을 없앤다.
  4. argparse 기반 `if __name__ == "__main__":` 블록은 노트북 셀에 붙여넣으면
     커널 launch 인자(sys.argv)를 파싱하다 죽는다 — TCD v2 전략 파일들이 쓰는
     `if __name__ == "__main__" or 노트북감지():` 패턴으로 교체한다.

조립 후 실제로 `python`으로 실행해 ImportError/NameError 없이 끝까지 도는지
검증한다(§20 감사와 별개로, "이 파일 자체가 돌아간다"는 것을 증명하는 절차).
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "smart_consensus_gap")
OUT = "/tmp/claude-0/-home-user-claude-coding/bcfd6a65-63a1-5601-b3bb-7f8d11566a55/scratchpad/scg_single_file.py"

#  병합 순서 = 패키지 내부 의존성 순서 그대로 (config 가 가장 밑, synthetic 이 마지막).
MODULE_ORDER = ["config", "contracts", "util", "discover", "normalize", "pit_engine",
                "analyst_skill", "consensus", "factors", "scoring", "portfolio",
                "backtest", "validation", "robustness", "reporting", "synthetic"]

#  원본 패키지에서 실제로 `from . import X as ALIAS` 로 쓰인 것만 별칭을 만든다.
#  (config/util 은 항상 특정 이름만 직접 import 했으므로 별칭이 필요 없다 — §3 확인됨)
ALIAS_OF = {
    "contracts": "C", "discover": "DISC", "normalize": "NORM", "pit_engine": "PIT",
    "analyst_skill": "SK", "consensus": "CONS", "factors": "FX", "scoring": "SC",
    "portfolio": "PF", "backtest": "BT", "validation": "VAL", "robustness": "ROB",
    "reporting": "REP", "synthetic": "SYN",
}

_HEADER_STRIP_RE = re.compile(r"^(#!.*|# -\*- coding.*|from __future__ import annotations)\s*$")


def strip_module_header(src: str) -> str:
    """shebang / coding 선언 / future import 를 제거한다 (병합 파일 맨 위에 한 번만 둔다)."""
    return "\n".join(ln for ln in src.split("\n") if not _HEADER_STRIP_RE.match(ln))


def transform_imports(src: str, path: str) -> str:
    """패키지 내부 import 문을 병합 후에도 동작하도록 변환한다.

    ★ 단순히 지우기만 하면 안 되는 경우가 있다: `from .config import SCGConfig as _Cfg`
      처럼 함수 **안에서** 특정 이름에 로컬 별칭을 붙인 경우, 그 줄을 지우면 뒤에서
      `_Cfg` 를 쓰는 코드가 NameError 를 낸다. 그래서 import 종류를 구분한다:

      · `from . import contracts as C`               → 서브모듈을 별칭으로 통째로 가져옴.
        지운다. (에필로그가 만드는 네임스페이스 별칭이 이미 이 역할을 대신한다)
      · `from smart_consensus_gap import X as Y`      → 위와 동일한 의미(절대경로 표기).
      · `from .config import A, B as C`               → 특정 이름을 가져옴. `A` 는 이미
        전역에 존재하므로 지우고, `B as C` 는 `C = B` 대입문으로 **대체**해 로컬 별칭을
        살린다 (해당 import 문이 함수 내부에 있어도 들여쓰기를 그대로 보존한다).

    ast 로 정확한 줄 범위(node.lineno~end_lineno)를 찾아 뒤에서부터 스플라이스한다
    (앞에서부터 지우면 이후 노드들의 줄번호가 밀려 어긋난다).
    """
    tree = ast.parse(src, filename=path)
    lines = src.split("\n")
    edits = []  # (start, end, replacement_lines) — 1-indexed, inclusive
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        is_relative = node.level >= 1
        is_abs_pkg = (node.module or "").startswith("smart_consensus_gap")
        if not (is_relative or is_abs_pkg):
            continue
        indent = re.match(r"[ \t]*", lines[node.lineno - 1]).group(0)
        whole_submodule = node.module is None or node.module == "smart_consensus_gap"
        replacement = []
        if not whole_submodule:
            for alias in node.names:
                if alias.asname:
                    replacement.append(f"{indent}{alias.asname} = {alias.name}")
        edits.append((node.lineno, node.end_lineno, replacement))

    for start, end, replacement in sorted(edits, key=lambda e: -e[0]):
        lines[start - 1:end] = replacement
    return "\n".join(lines)


def top_level_names(src: str, path: str) -> list:
    """함수/클래스/모듈수준 대입의 최상위 이름만 뽑는다 (private(_로 시작) 도 포함 —
    실제로 별칭을 통해 접근되는 이름은 전부 public 이지만, 정확성을 위해 전체를 담는다)."""
    tree = ast.parse(src, filename=path)
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def check_no_duplicate_top_level(paths_and_srcs: list) -> None:
    """조립 사고의 대표 증상(같은 이름을 두 파일이 정의)을 사전에 잡는다.
    (tools/build.py 의 check() 와 같은 목적 — 여기서는 파일 간 교차 검사)
    `__all__` 같은 던더는 모든 모듈이 관례적으로 갖고 있으므로 검사에서 제외한다."""
    seen = {}
    for path, src in paths_and_srcs:
        for name in top_level_names(src, path):
            if name.startswith("__") and name.endswith("__"):
                continue
            if name in seen and seen[name] != path:
                raise SystemExit(f"최상위 이름 충돌: '{name}' — {seen[name]} 와 {path} 양쪽에서 정의됨")
            seen[name] = path


def build_alias_epilogue(module_srcs: dict) -> str:
    lines = [
        "# ══════════════════════════════════════════════════════════════════════════════",
        "#  모듈 별칭 — 원 패키지의 `from . import X as Y` 를 단일 파일 병합 후에도",
        "#  동작시키기 위함. 각 별칭은 해당 모듈이 실제로 정의했던 최상위 이름만 담는다",
        "#  (조립 스크립트가 ast 로 추출 — 수동 나열이 아니다).",
        "# ══════════════════════════════════════════════════════════════════════════════",
        "import types as _sc_types",
    ]
    for mod, alias in ALIAS_OF.items():
        names = [n for n in top_level_names(module_srcs[mod], mod) if not n.startswith("__")]
        kw = ", ".join(f"{n}={n}" for n in names)
        # 한 줄이 너무 길어지면 가독성이 떨어지므로 감싼다.
        wrapped = textwrap.fill(kw, width=96, subsequent_indent="    ")
        lines.append(f"{alias} = _sc_types.SimpleNamespace({wrapped})")
    return "\n".join(lines)


def build_tail() -> str:
    return textwrap.dedent('''
        # ══════════════════════════════════════════════════════════════════════════════
        #  실행 — python 파일.py 로 실행하거나 Jupyter/Colab 셀에 그대로 붙여넣어도 동일하게
        #  동작한다. argparse 를 쓰지 않는 것은 의도적이다: 노트북 커널의 launch 인자가
        #  sys.argv 에 섞여 있어 argparse 가 그걸 파싱하다 죽기 때문이다.
        # ══════════════════════════════════════════════════════════════════════════════
        def _sc_in_notebook() -> bool:
            try:
                return get_ipython() is not None          # noqa: F821
            except NameError:
                return False


        if __name__ == "__main__" or _sc_in_notebook():
            RESULT = run()
    ''').strip() + "\n"


def main() -> None:
    module_srcs = {}
    for mod in MODULE_ORDER:
        path = os.path.join(PKG, f"{mod}.py")
        with open(path, encoding="utf-8") as f:
            module_srcs[mod] = f.read()

    orch_path = os.path.join(ROOT, "run_smart_consensus_gap.py")
    with open(orch_path, encoding="utf-8") as f:
        orch_src = f.read()

    # ── 충돌 검사 (병합 전, 원본 그대로) ────────────────────────────────────────────
    check_pairs = [(f"smart_consensus_gap/{m}.py", module_srcs[m]) for m in MODULE_ORDER]
    check_no_duplicate_top_level(check_pairs)

    # ── 오케스트레이터의 argparse 블록 제거 + _clean 이름 충돌 해소 ──────────────────
    #  (뒤 두 변환 모두 텍스트 상에서 안전한 조작이며 결과는 여전히 완결된 파이썬이다 —
    #   그 상태에서 ast 로 import 를 정확히 변환한다)
    orch_body = orch_src.split('if __name__ == "__main__":', 1)[0]
    orch_body = re.sub(r"\b_clean\b", "_clean_result", orch_body)
    orch_body = transform_imports(orch_body, "run_smart_consensus_gap.py")
    orch_body = strip_module_header(orch_body)

    # ── 각 모듈 스트립 (import 변환은 원본 그대로의 소스에 대해서만 정확하다) ─────────
    parts = []
    for mod in MODULE_ORDER:
        s = transform_imports(module_srcs[mod], f"smart_consensus_gap/{mod}.py")
        s = strip_module_header(s)
        parts.append(f"\n# {'─' * 90}\n#  {mod}.py\n# {'─' * 90}\n" + s.strip() + "\n")

    epilogue = build_alias_epilogue(module_srcs)
    tail = build_tail()

    doc = textwrap.dedent(f'''\
        #!/usr/bin/env python3
        # -*- coding: utf-8 -*-
        # ══════════════════════════════════════════════════════════════════════════════════
        #  SCG_ORIGINAL_REPRO_V1 — 스마트 컨센서스 갭 / IBK 서프라이즈 포트폴리오 재현
        #  단일 파일 병합본 (tools/gen_scg_single_file.py 로 조립됨. 원본 = smart_consensus_gap/)
        #
        #  원문: IBK투자증권 이정빈, 「바텀업 퀀트 – 알파 포트폴리오 전략」(2020-08-20)
        #
        #  ── 이 파일 하나로 끝납니다 ──────────────────────────────────────────────────
        #   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
        #   `python 이파일.py` 로 그냥 실행해도 동일하게 동작합니다. 데이터가 없으면
        #   자동으로 합성 픽스처 리허설로 전환되어 배선을 증명하고, 그 사실이 모든
        #   출력에 synthetic=true 로 표시됩니다(§0-2). 실데이터를 연결하려면
        #   `run(data_roots=["/path/to/data"])` 처럼 인자를 바꿔 호출하십시오.
        #
        #  PR: https://github.com/limsh87/claude-coding/pull/24
        # ══════════════════════════════════════════════════════════════════════════════════
        from __future__ import annotations
        ''')

    merged = doc + "".join(parts) + "\n" + epilogue + "\n\n" + orch_body.strip() + "\n\n\n" + tail

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(merged)

    # ── 문법 검사 + 병합 후 중복 이름 재검사 ────────────────────────────────────────
    tree = ast.parse(merged, filename=OUT)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"병합 후 최상위 이름 중복 → {dups}")

    n_lines = merged.count("\n") + 1
    print(f"wrote {OUT} ({n_lines:,}줄, {len(merged)/1024:.0f}KB) — 문법/중복 검사 통과")


if __name__ == "__main__":
    main()
