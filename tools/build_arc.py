#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-TXT v2 빌더 — build_arc/ 조각을 하나의 자립 실행 파일로 조립한다.

산출물은 Colab / JupyterLab 어디서든 한 셀에 붙여넣거나 `python <파일>` 로 실행하면
백테스트 → 성과검증 → 어블레이션 → BH-FDR → 강건성 → 해석표까지 전부 로그에 출력된다.

조립 후 검사:
  · 문법(ast.parse)
  · 최상위 def/class 중복 정의
  · 조각 안의 import 문 (concat 파일에서는 사고의 원인)
  · 미치환 플레이스홀더
"""
from __future__ import annotations
import os, re, ast, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build_arc")
OUT = os.path.join(ROOT, "strategies")

# 본체 — 사용자가 실제로 돌리는 산출물(수집·정제·백테스트·성과·어블레이션·강건성·해석표)
ORDER = [
    "00_header.py", "01_bootstrap.py", "02_kernel.py", "03_util.py", "04_vault.py",
    "05_http.py",
    "10_ingest_universe.py", "11_ingest_price.py", "12_ingest_dart_fin.py",
    "13_ingest_research.py", "14_entity_research.py", "15_ingest_dart_doc.py",
    "20_pit.py", "21_gate.py",
    "30_axis_a_tone.py", "31_axis_b_d1.py", "32_axis_b_d2.py", "33_axis_b_d3.py",
    "40_score.py", "41_backtest.py",
    "50_ablation.py", "51_robust.py", "60_report.py", "90_main.py",
]

# 검증 하네스 — 별도 파일. 본체는 이게 없어도 완전히 동작한다.
#   같은 폴더에 두면 SELFTEST=True 일 때 본체가 자동으로 읽어 실행한다.
VERIFY_ORDER = ["70_contracts.py", "75_rehearsal.py", "80_selftest.py"]
VERIFY_FNAME = "arc_txt_v2_verify.py"

SPEC = dict(
    sid="ARC_TXT_V2",
    fname="arc_txt_v2.py",
    name="애널리스트 텍스트톤 변화 × DART 3층 교차확증",
)


def read(name: str) -> str:
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def strip_head(src: str, keep: bool) -> str:
    """헤더 파일이 아닌 조각에서 shebang / coding / __future__ 를 제거."""
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
        p = os.path.join(SRC, fn)
        if not os.path.exists(p):
            raise SystemExit(f"조각 없음: {fn}")
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


def build_verify() -> str:
    """검증 하네스 조각을 하나로 묶는다. 본체가 exec 로 읽어 들이므로 import 는 없다."""
    head = ('"""ARC-TXT v2 검증 하네스 — 계약검정 A1~A39 / 실경로 리허설 / 합성 스모크.\n\n'
            "본체(arc_txt_v2.py)와 같은 폴더에 두면 SELFTEST=True 일 때 자동으로 실행된다.\n"
            "단독 실행은 불가하다(본체의 전역 이름을 쓴다). 없어도 본체는 완전히 동작한다.\n"
            '"""\n')
    return head + "\n".join(strip_head(read(fn), keep=False) for fn in VERIFY_ORDER)


def check_pieces() -> None:
    """조각 안의 최상위 import 를 잡는다 — concat 파일에서 순서 사고의 원인이 된다."""
    bad = []
    for fn in ORDER + VERIFY_ORDER:
        if fn in ("00_header.py", "01_bootstrap.py"):
            continue                                  # 부트스트랩만 임포트를 허용
        src = read(fn)
        try:
            tree = ast.parse(src, filename=fn)
        except SyntaxError as e:
            raise SystemExit(f"{fn}: 문법 오류 line {e.lineno}: {e.msg}")
        for node in tree.body:                        # 최상위만 검사(함수 내부 지연 임포트는 허용)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bad.append(f"{fn}:{node.lineno}")
    if bad:
        raise SystemExit("조각 최상위에 import 문이 있습니다(함수 내부로 옮기세요): " +
                         ", ".join(bad))


def check_built(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:8]}")


def main():
    os.makedirs(OUT, exist_ok=True)
    check_pieces()
    version = datetime.datetime.now().strftime("v2.%Y%m%d.%H%M")
    blob = build(version)
    path = os.path.join(OUT, SPEC["fname"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check_built(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {SPEC['fname']:<24} {n:>7,}줄  {len(blob)/1024:>8.1f}KB   [본체]")

    vblob = build_verify()
    vpath = os.path.join(OUT, VERIFY_FNAME)
    with open(vpath, "w", encoding="utf-8") as f:
        f.write(vblob)
    ast.parse(vblob, filename=vpath)
    vn = vblob.count("\n") + 1
    print(f"  ✔ {VERIFY_FNAME:<24} {vn:>7,}줄  {len(vblob)/1024:>8.1f}KB   [검증 하네스·선택]")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
