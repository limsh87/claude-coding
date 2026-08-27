# -*- coding: utf-8 -*-
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture(scope="session")
def world():
    from collectors.synthetic import build_world
    return build_world("2015-01-01", "2024-12-31", opp_per_month=40)


@pytest.fixture(scope="session")
def events(world):
    from graph.lifecycle import resolve_opportunities
    from entity.dart_crosswalk import attach_stock_code
    from entity.consortium import allocate
    from collectors.synthetic import crosswalk_from_world
    L, _ = resolve_opportunities(world["events"])
    L = attach_stock_code(L, crosswalk_from_world(world))
    L = allocate(L, "primary")
    L["broad_category"] = L["license_req"]
    return L


@pytest.fixture(scope="session")
def months():
    from core.io import month_range
    return month_range("2015-01-01", "2024-12-31")


@pytest.fixture(scope="session", autouse=True)
def _optional_freeze():
    """`G2B_TEST_FREEZE=1 pytest` 로 실행하면 임시로 사전등록을 동결해
    수익률 관련 테스트까지 전부 돌린다. 끝나면 반드시 원상복구한다.

    기본(미설정)에서는 동결하지 않는다 — 저장소는 '미동결 템플릿' 상태로 배포되며,
    동결은 실데이터를 본 시점의 행위이지 배포물이 아니기 때문이다(§1.1).
    """
    if os.environ.get("G2B_TEST_FREEZE") != "1":
        yield
        return
    from core import config as CFG
    from audit import prereg
    existed = os.path.exists(CFG.PREREG_HASH_FILE)
    backup = {}
    for fn in CFG.PREREG_FILES:
        p = os.path.join(CFG.CONFIG_DIR, fn)
        if os.path.exists(p):
            backup[p] = open(p, encoding="utf-8").read()
    prereg.freeze(maturity_embargo_days=430, usable_start_date="2018-01-31",
                  notes="pytest 임시 동결 — 테스트 종료 시 원복")
    try:
        yield
    finally:
        for p, body in backup.items():
            open(p, "w", encoding="utf-8").write(body)
        if not existed and os.path.exists(CFG.PREREG_HASH_FILE):
            os.remove(CFG.PREREG_HASH_FILE)
