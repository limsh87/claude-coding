# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 0 스모크 — 합성데이터로 전 경로를 실제로 돌린다                                        ║
# ║                                                                                              ║
# ║  네트워크 경계(http_get / http_json / BigQuery 클라이언트)만 바꿔 끼우고, 그 위의 파싱·PIT   ║
# ║  필터·매칭·게이트·판정표 생성은 전부 진짜 코드를 태운다. 키도 네트워크도 필요 없다.           ║
# ║                                                                                              ║
# ║      python3 phase0/phase0_smoke.py                                                          ║
# ║                                                                                              ║
# ║  시나리오 ① 선행 블로커 (키 없음) → BLOCKED_PREREQ 경로                                       ║
# ║  시나리오 ② 전 축 정상 응답      → 게이트 측정·판정표·수기검증 CSV 경로                       ║
# ║  ※ 스모크가 검증하는 것은 '코드가 도는가'이지 '데이터가 좋은가'가 아니다.                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

from __future__ import annotations

import importlib.util
import io
import json
import os
import random
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "phase0_altdata_3axis_validation.py")

TMP = tempfile.mkdtemp(prefix="phase0_smoke_")
os.environ["PHASE0_PROJECT_ROOT"] = TMP
os.environ["DART_API_KEY"] = ""
os.environ["DATA_GO_KR_KEY"] = ""
os.environ["BQ_PROJECT_ID"] = ""

spec = importlib.util.spec_from_file_location("phase0_mod", TARGET)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)                      # noqa: E402
P.ALLOW_PIP_INSTALL = False
P.DELAY_MIN = P.DELAY_MAX = 0.0                 # 스모크는 지연 없이

RNG = random.Random(7)
N_LISTED = 1400
CODES = [f"{100000 + i * 7:06d}" for i in range(N_LISTED)]
NAMES = [f"합성{i:04d}테크" for i in range(N_LISTED)]


# ── 합성 유니버스 ─────────────────────────────────────────────────────────────────────────────
def fake_pykrx_universe(as_of):
    import pandas as pd
    n = N_LISTED if as_of == P.T_NOW else N_LISTED - 120      # 과거엔 상장사가 더 적었다고 가정
    return pd.DataFrame({
        "code": CODES[:n],
        "name": NAMES[:n],
        "market": ["KOSPI" if i % 3 == 0 else "KOSDAQ" for i in range(n)],
        "marcap": [10 ** 12 - i * 10 ** 8 for i in range(n)],
        "src": "pykrx",
    }), [f"합성 PIT 경로({as_of})"]


# ── 합성 DART ─────────────────────────────────────────────────────────────────────────────────
def _corpcode_zip() -> bytes:
    rows = []
    for i, (c, n) in enumerate(zip(CODES, NAMES)):
        rows.append(f"<list><corp_code>{i:08d}</corp_code>"
                    f"<corp_name>주식회사 {n}</corp_name>"
                    f"<stock_code>{c}</stock_code>"
                    f"<modify_date>20260101</modify_date></list>")
    xml = "<result>" + "".join(rows) + "</result>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buf.getvalue()


CORP_ZIP = _corpcode_zip()
GUIDE_HTML = (b"<html><a href='?apiGrpCd=DS002&apiId=2019013'>"
              b"\xec\x9e\x84\xec\x9b\x90\xed\x98\x84\xed\x99\xa9</a></html>")   # '임원현황'

# 겸직 인물 풀 — 일부 인물을 여러 종목에 심어 A-3 이 0이 아니게 만든다.
SHARED_PEOPLE = [(f"김겸직{i}", f"{1960 + i}년 {1 + i % 12:02d}월") for i in range(60)]


def _exec_rows(corp_code: str, year: int, reprt: str):
    idx = int(corp_code)
    if idx % 11 == 0:                                   # 약 9% 는 데이터 없음
        return []
    rcept = f"{year + 1}0315" if reprt == "11011" else f"{year}0515"
    rows = []
    for k in range(4):
        if k == 0 and idx % 3 == 0:
            nm, birth = SHARED_PEOPLE[idx % len(SHARED_PEOPLE)]
        else:
            nm, birth = f"이임원{idx}_{k}", f"{1965 + (idx + k) % 25}년 {1 + (idx + k) % 12:02d}월"
        if idx % 17 == 0 and k == 3:
            birth = "-"                                  # 결측도 섞는다
        rows.append({"rcept_no": rcept + "000000001", "corp_cls": "K",
                     "corp_code": corp_code, "corp_name": f"주식회사 합성{idx:04d}테크",
                     "nm": nm, "sexdstn": "남" if k % 2 else "여", "birth_ym": birth,
                     "ofcps": "사내이사", "rgist_exctv_at": "등기임원", "fte_at": "상근",
                     "chrg_job": "경영총괄", "main_career": "합성", "hffc_pd": "5년",
                     "mxmm_shrholdr_relate": "-", "tenure_end_on": "2027년 03월 20일"})
    return rows


# ── 합성 국민연금 ─────────────────────────────────────────────────────────────────────────────
NPS_ROWS = []
for i, (c, n) in enumerate(zip(CODES, NAMES)):
    if i % 5 == 4:                                       # 일부 종목은 사업장이 없다
        continue
    n_wk = 2 if i % 7 == 0 else 1                        # 다사업장 사례
    for w in range(n_wk):
        NPS_ROWS.append({
            "seq": str(100000 + len(NPS_ROWS)),
            "wkplNm": (n if w == 0 else f"{n} 제2공장"),
            "bzowrRgstNo": f"{100000 + i % 899999:06d}",  # ★ 6자리만 공개 (C-1 = N)
            "jnngpCnt": str(50 + (i % 400)),
            "crrmmNtcAmt": str(10_000_000 + i * 1000),
            "nwAcqzrCnt": str(i % 9), "lssJnngpCnt": str(i % 5),
            "wkplRoadNmDtlAddr": "합성시 합성구", "ldongAddrMgplDgCd": "11",
            "ldongAddrMgplSggCd": "110", "vldtVlKrnNm": "합성업",
            "wkplJnngStcd": "1", "wkplStylDvcd": "1",
            "adptDt": "20150101", "scsnDt": "",
        })
for i in range(600):                                     # 상장사와 무관한 사업장 잡음
    NPS_ROWS.append({"seq": str(900000 + i), "wkplNm": f"무관법인{i}", "bzowrRgstNo": f"{700000+i:06d}",
                     "jnngpCnt": "12", "crrmmNtcAmt": "1000", "nwAcqzrCnt": "0",
                     "lssJnngpCnt": "0", "wkplRoadNmDtlAddr": "", "ldongAddrMgplDgCd": "11",
                     "ldongAddrMgplSggCd": "110", "vldtVlKrnNm": "기타",
                     "wkplJnngStcd": "1", "wkplStylDvcd": "1", "adptDt": "", "scsnDt": ""})


def _nps_envelope(items, total):
    return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                         "body": {"items": {"item": items}, "totalCount": total,
                                  "pageNo": 1, "numOfRows": len(items)}}}


# ── 네트워크 경계 스텁 ────────────────────────────────────────────────────────────────────────
def fake_http_get(url, source, params=None, tries=3, timeout=30, referer=None):
    P.HTTP_STAT[source]["req"] += 1
    if "corpCode.xml" in url:
        P.HTTP_STAT[source]["ok"] += 1
        return CORP_ZIP
    if "guide/main.do" in url:
        P.HTTP_STAT[source]["ok"] += 1
        return GUIDE_HTML
    return None


def fake_http_json(url, source, params=None, tries=3, timeout=30, referer=None):
    p = params or {}
    P.HTTP_STAT[source]["req"] += 1
    P.HTTP_STAT[source]["ok"] += 1
    if url.endswith("exctvSttus.json"):
        rows = _exec_rows(str(p.get("corp_code")), int(p.get("bsns_year")),
                          str(p.get("reprt_code")))
        return {"status": "000" if rows else "013", "message": "", "list": rows}
    if url.endswith("empSttus.json"):
        return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
    if url.endswith("company.json"):
        i = int(str(p.get("corp_code") or 0))
        return {"status": "000", "corp_name": f"주식회사 합성{i:04d}테크",
                "bizr_no": f"{100000 + i % 899999:06d}{i % 10000:04d}",
                "jurir_no": "1101110000000", "adres": "합성시"}
    if "getBassInfoSearch" in url:
        page = int(p.get("pageNo", 1))
        rows = int(p.get("numOfRows", 1000))
        ym = str(p.get("dataCrtYm") or "202606")
        chunk = NPS_ROWS[(page - 1) * rows: page * rows]
        return _nps_envelope([dict(r, dataCrtYm=ym) for r in chunk], len(NPS_ROWS))
    if "getPdAcctoSttusInfoSearch" in url:
        seq = str(p.get("seq") or "").strip()
        if not seq.isdigit():                            # 실제 API 도 seq 없이는 실패한다
            return {"response": {"header": {"resultCode": "30",
                                            "resultMsg": "SERVICE_KEY_OR_PARAM_ERROR"},
                                 "body": {}}}
        deep = (int(seq) % 3 != 0)                       # 1/3 은 과거 깊이가 얕다
        months = ([f"{y}{m:02d}" for y in range(2018, 2027) for m in range(1, 13)]
                  if deep else [f"{y}{m:02d}" for y in range(2024, 2027) for m in range(1, 13)])
        months = [m for m in months if m <= "202606"]
        return _nps_envelope([{"dataCrtYm": m, "jnngpCnt": "100", "seq": seq} for m in months],
                             len(months))
    if "getDetailInfoSearch" in url:
        return _nps_envelope([{"seq": p.get("seq"), "wkplNm": "합성"}], 1)
    return None


# ── 합성 BigQuery ─────────────────────────────────────────────────────────────────────────────
class FakeBQ:
    def __init__(self):
        self.estimates = []
        self.project = "smoke-project"
        self.client = None
        self.bigquery = None

    def dry(self, sql, label):
        n = 3 * 1024 ** 3 if "청구항" not in label else 900 * 1024 ** 3
        self.estimates.append({"label": label, "bytes": n, "gb": round(n / 1024 ** 3, 2)})
        return n

    def run(self, sql, label, dest=None):
        import pandas as pd
        n = self.dry(sql, label)
        if n > P.BQ_MAX_SCAN_BYTES:
            return None, n
        if label.startswith("출원인 집계"):
            recs = []
            for i, nm in enumerate(NAMES):
                if i % 4 == 3:                            # 약 25% 는 특허가 없다
                    continue
                name = (f"주식회사 {nm}" if i % 3 else f"{nm} CO., LTD.")
                if i % 13 == 0:
                    name = f"주식회사 {nm}홀딩스"          # 완전일치 실패 → 퍼지 후보
                recs.append({"assignee_name": name, "n_publication": 3 + i % 40,
                             "n_family": 1 + i % 9, "first_filing_date": 20150101,
                             "last_filing_date": 20250101})
            return pd.DataFrame(recs), n
        if label.startswith("출원인 표기 언어 분포"):
            return pd.DataFrame([{"n_h_hangul": 700, "n_raw_hangul": 900, "n_total": 1000}]), n
        if label.startswith("피인용 결측 측정"):
            return pd.DataFrame([{"n_pub": 10000, "n_absent": 1500}]), n
        return pd.DataFrame(), n


def install_axis_b_stubs():
    P.BQ = FakeBQ
    P.axis_b_prereq = lambda: {"library": True, "credentials": True, "project": True,
                               "billing_ok": True, "reason": ""}
    P._bq_ensure_dataset = lambda bq: "smoke-project.phase0_altdata"
    P._bq_materialize_kr = lambda bq, ds, lo, hi: f"{ds}.kr_pubs"
    P._bq_forward_citations = lambda bq, ds: (f"{ds}.kr_fwd_cit",
                                              {"route": "gpr.cited_by",
                                               "distinguishes_zero": True, "estimates": []})


# ── 시나리오 ─────────────────────────────────────────────────────────────────────────────────
def scenario_blocked():
    print("\n" + "=" * 92)
    print("시나리오 ① 선행 블로커 — 키 없음 / BigQuery 미준비")
    print("=" * 92)
    P.DART_API_KEY = ""
    P.DATA_GO_KR_KEY = ""
    P._DGK_CACHE.clear()
    P.BQ_PROJECT_ID = ""
    P._pykrx_universe = fake_pykrx_universe
    P.http_get = fake_http_get
    P.http_json = fake_http_json
    P.axis_b_prereq = lambda: {"library": False, "credentials": False, "project": False,
                               "billing_ok": None, "reason": "스모크: GCP 미준비"}
    P.main()
    v = json.load(open(os.path.join(P.DIR_REPORTS, "phase0_verdict.json"), encoding="utf-8"))
    got = {k: x["status"] for k, x in v["axis_overall"].items()}
    print("→ 축별 판정:", got)
    assert got["A"] == "BLOCKED_PREREQ", got
    assert got["B"] == "BLOCKED_PREREQ", got
    assert got["C"] == "BLOCKED_PREREQ", got
    print("✓ 선행 블로커 경로 정상")


def scenario_full():
    print("\n" + "=" * 92)
    print("시나리오 ② 전 축 정상 응답")
    print("=" * 92)
    shutil.rmtree(P.CACHE_ROOT, ignore_errors=True)
    for d in (P.DIR_RAW, P.DIR_PARSED, P.DIR_REPORTS):
        os.makedirs(d, exist_ok=True)
    P.DART_API_KEY = "SMOKE" * 8
    P.DATA_GO_KR_KEY = "smoke-decoding-key"
    P._DGK_CACHE.clear()
    P.BQ_PROJECT_ID = "smoke-project"
    P._pykrx_universe = fake_pykrx_universe
    P.http_get = fake_http_get
    P.http_json = fake_http_json
    install_axis_b_stubs()
    P.main()

    rep = P.DIR_REPORTS
    for f in ("phase0_verdict.json", "phase0_verdict.csv", "phase0_summary.md",
              "manual_check_A_coexec_links.csv", "manual_check_C_workplace_match.csv",
              "phase0_run_log.txt"):
        p = os.path.join(rep, f)
        assert os.path.exists(p) and os.path.getsize(p) > 0, f"산출물 누락: {f}"
    v = json.load(open(os.path.join(rep, "phase0_verdict.json"), encoding="utf-8"))
    print("→ 축별 판정:", {k: x["status"] for k, x in v["axis_overall"].items()})
    print("\n게이트 측정값")
    seen = set()
    for ax in v["axes"]:
        for g in ax["gates"]:
            print(f"  {ax['axis']} {ax['as_of']} {g['id']:<4} "
                  f"measured={g['measured']} thr={g['threshold']} pass={g['pass']}")
            seen.add(g["id"])
    for gid in ("A-1", "A-2", "A-3", "A-4", "B-1", "B-2", "B-3", "B-4",
                "C-1", "C-2", "C-3", "C-4", "C-5"):
        assert gid in seen, f"게이트 누락: {gid}"
    assert v["run"]["contract_check"]["checks"]["P0_NO_STRATEGY"] == "PASS"
    assert not v["run"]["contract_check"]["violations"], v["run"]["contract_check"]["violations"]

    import csv as _csv
    with open(os.path.join(rep, "manual_check_A_coexec_links.csv"), encoding="utf-8-sig") as fh:
        n_a = sum(1 for _ in _csv.DictReader(fh))
    with open(os.path.join(rep, "manual_check_C_workplace_match.csv"), encoding="utf-8-sig") as fh:
        n_c = sum(1 for _ in _csv.DictReader(fh))
    print(f"\n수기검증 CSV: A={n_a}행, C={n_c}행")
    assert n_a > 0 and n_c > 0
    print("✓ 전 경로 정상 · 모든 게이트가 판정표에 기록됨")
    print("\n─── phase0_summary.md (앞부분) " + "─" * 55)
    with open(os.path.join(rep, "phase0_summary.md"), encoding="utf-8") as fh:
        print("".join(fh.readlines()[:40]))


def scenario_notebook_path():
    """노트북에서는 __file__ 이 없다. 그때 계약 자기검사가 셀 원문으로 돌아가는지 확인한다.
    (이 경로가 죽으면 P0_NO_STRATEGY 검사가 조용히 SKIPPED 로 빠진다.)"""
    print("\n" + "=" * 92)
    print("시나리오 ③ 노트북 실행 경로 (__file__ 없음 · get_ipython 존재)")
    print("=" * 92)
    import builtins
    src = open(TARGET, encoding="utf-8").read()

    class ZMQInteractiveShell:                       # 이름이 곧 판정 기준이다
        def __init__(self, ns):
            self.user_ns = ns

    shell = ZMQInteractiveShell({"In": ["", src]})
    old = getattr(builtins, "get_ipython", None)
    builtins.get_ipython = lambda: shell
    try:
        ns = {"__name__": "notebook_smoke"}          # main() 자동 실행은 막는다
        exec(compile(src, "<notebook-cell>", "exec"), ns)
        got_src, origin = ns["_read_self_source"]()
        assert origin == "ipython_cell", origin
        assert got_src == src, "셀 원문을 그대로 읽지 못했습니다"
        cc = ns["verify_contracts"](got_src, origin)
        print("→ 계약 검사:", cc["checks"])
        assert all(x == "PASS" for x in cc["checks"].values()), cc
        assert not cc["violations"], cc["violations"]
        assert ns["_in_notebook"]() is True
        print("✓ 노트북 경로에서도 계약 자기검사가 실제로 수행됨")
    finally:
        if old is None:
            delattr(builtins, "get_ipython")
        else:
            builtins.get_ipython = old


if __name__ == "__main__":
    try:
        scenario_blocked()
        scenario_full()
        scenario_notebook_path()
        print(f"\n스모크 통과. 산출물: {P.DIR_REPORTS}")
    finally:
        keep = os.environ.get("PHASE0_SMOKE_KEEP")
        if not keep:
            shutil.rmtree(TMP, ignore_errors=True)
        else:
            print(f"작업 디렉터리 보존: {TMP}")
    sys.exit(0)
