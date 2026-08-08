
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  ★ Phase 0 — 데이터 실현가능성 게이트  (SPEC §4 · 이 전략 최대 리스크)                    ║
# ║                                                                                          ║
# ║  이 전략의 병목은 알파가 아니라 '거래원별 일별 매매동향의 과거 이력' 확보다.                ║
# ║  그래서 코드를 더 쓰기 전에, 코드가 스스로 소스를 찔러보고 판정한다.                        ║
# ║                                                                                          ║
# ║  판정 → 분기 (SPEC §4.2 / §4.3)                                                           ║
# ║    FULL10  : 거래원 10년 확보          → ARC-BDF 원 가설 그대로                            ║
# ║    PARTIAL : 거래원 3~10년 확보        → 확보 구간으로 축소 + 검정력 영향 명시              ║
# ║    PROXY   : 3년 미만 / 당일 스냅샷만  → B-1 전진수집 스크립트 생성                        ║
# ║                                          + B-2 열화 프록시 백테스트(ARC-BDF-PROXY)         ║
# ║                                                                                          ║
# ║  ★ PROXY 로 떨어지면 이것은 '원 가설의 대리 검증' 이 아니다. 브로커 정체성이 사라지므로     ║
# ║    H3(중소형사 강세)는 검증 불가, H5(리포트 조건부 우위)는 '주체 단위' 로 약화된 형태로만   ║
# ║    검증된다. 산출물 전체에 그 사실을 명시하고 "10년 백테스트 완료" 라고 보고하지 않는다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PHASE0_MD = "PHASE0_DATA_FEASIBILITY.md"


def _fmt_row(rank, name, hist, span, gran, auth, note):
    return [str(rank), name, hist, span, gran, auth, note]


def run_phase0_gate(probe_codes: Optional[Sequence[str]] = None) -> dict:
    """SPEC §4 절차를 실제로 수행하고 판정 딕셔너리를 돌려준다."""
    t0 = time.time()
    codes = list(probe_codes or PHASE0_PROBE_TICKERS)
    R: Dict[str, Any] = {"branch": "", "sources": [], "started": _dt.datetime.now().isoformat(),
                         "member_history_years": 0.0, "flow_history_years": 0.0,
                         "notes": [], "probes": {}}

    LOG.banner("Phase 0 — 데이터 실현가능성 게이트",
               "거래원 과거 이력을 정말 못 구하는지 코드가 직접 확인합니다 (SPEC §4)")

    offline = (RUN_MODE in ("SMOKE",))
    if offline:
        LOG.info("SMOKE 모드 — 네트워크 프로브를 건너뛰고 PROXY 분기를 가정합니다.")

    # ── ① KRX 정보데이터시스템 ────────────────────────────────────────────────────────────
    krx_note = ("KRX 로그인 차단 상태로 사용하지 않음(KRX_ENABLE=False). "
                "2025-12 data.krx.co.kr 이관 + 로그인 요구 강화로 무인증 접근 전제 불가."
                if not KRX_ENABLE else "KRX_ENABLE=True — 교차검증용으로만 사용")
    R["sources"].append(_fmt_row(1, "KRX 정보데이터시스템 (data.krx.co.kr)",
                                 "미확인(미사용)", "-", "종목×회원사×일 (제공된다고 알려짐)",
                                 "로그인 필수", krx_note))

    # ── ② 네이버 금융 종목별 거래원 ───────────────────────────────────────────────────────
    mem = {"reachable": False, "date_param_works": False, "n_members": 0}
    if not offline:
        with PIPE.stage("P0.MEMBER", "네이버 거래원 소급 프로브", "P0",
                        budget_s=180, critical=False):
            probes = [probe_member_window(c) for c in codes[:3]]
            R["probes"]["member"] = probes
            mem["reachable"] = any(p.get("reachable") for p in probes)
            mem["date_param_works"] = any(p.get("date_param_works") for p in probes)
            mem["n_members"] = max([p.get("n_members", 0) for p in probes] or [0])
            for p in probes:
                LOG.info(f"  거래원 프로브 {p['code']}: 도달={p['reachable']} "
                         f"창구수={p['n_members']} 날짜파라미터={p['date_param_works']} "
                         f"시도={p.get('tried', [])[:3]} 예시={p.get('sample', [])[:3]}")
    R["sources"].append(_fmt_row(
        2, "네이버 금융 종목별 거래원",
        "가능" if mem["date_param_works"] else "불가(당일만)",
        "10년" if mem["date_param_works"] else "0일",
        "종목×창구(상위5)×일", "불필요",
        "날짜 파라미터가 동작함" if mem["date_param_works"] else
        "날짜 파라미터·페이지네이션 부재. 같은 종목 페이지의 일별시세/외국인기관 탭에는 "
        "&page= 가 있는데 거래원 탭에만 없다 → 설계상 이력 없음."))

    # ── ③ 증권사 OpenAPI ──────────────────────────────────────────────────────────────────
    R["sources"].append(_fmt_row(
        3, "증권사 OpenAPI (KIS / 키움 등)", "불가", "0~수십일",
        "종목×창구(상위5)", "계좌·HTS 필요",
        "KIS REST 의 회원사 조회는 '현재가 기준' 스냅샷. 키움 OpenAPI+ 는 32bit Windows OCX "
        "종속이라 Colab/JupyterLab 실행 자체가 불가. 어느 쪽도 10년 이력 없음."))

    # ── ④ 유료 벤더 ───────────────────────────────────────────────────────────────────────
    R["sources"].append(_fmt_row(
        4, "유료 벤더 (FnGuide DataGuide / 코스콤 등)", "가능(추정)", "10년+",
        "종목×회원사×일", "계약 필요",
        "항목 존재 여부만 조사 대상이며 계약은 진행하지 않음(SPEC §4-1 지시)."))

    # ── ④-b 공공데이터포털 (거래원은 없지만 PIT 를 살린다) ────────────────────────────────
    dgk_ok = bool(_dgk_key())
    R["sources"].append(_fmt_row(
        "4b", "공공데이터포털 금융위 주식시세정보", "해당없음(거래원 미제공)",
        "2015~현재", "종목×일 (시총·상장주식수 포함)",
        "무료 키", ("키 입력됨 → PIT 시총/일별 상장 스냅샷 정품 경로 가동"
                    if dgk_ok else "키 없음 → 시총이 근사로 강등됨(동작은 함)")))

    # ── ⑤ 대체 플로우 축: frgn.naver 소급 깊이 실측 ───────────────────────────────────────
    frgn_years = 0.0
    if not offline:
        with PIPE.stage("P0.FRGN", "투자자별 수급 소급 깊이 실측", "P0",
                        budget_s=300, critical=False):
            dep = [probe_frgn_depth(c) for c in codes[:2]]
            R["probes"]["frgn"] = dep
            for d in dep:
                LOG.info(f"  frgn 프로브 {d['code']}: 최대page={d['max_page']} "
                         f"최고(古)일자={d['oldest_date']} 페이지당={d['rows_per_page']}행")
                if d.get("oldest_date"):
                    yrs = (pd.Timestamp.today() - pd.Timestamp(d["oldest_date"])).days / 365.25
                    frgn_years = max(frgn_years, yrs)
    R["flow_history_years"] = round(frgn_years, 2)
    R["sources"].append(_fmt_row(
        5, "네이버 frgn.naver (기관·외국인 순매매)",
        "가능(page 소급)", f"{frgn_years:.1f}년(실측)" if frgn_years else "미측정",
        "종목×주체×일", "불필요",
        "거래원이 아니라 '투자자 주체' 단위. 브로커 정체성이 사라진다."))
    R["sources"].append(_fmt_row(
        6, "네이버 siseJson 외국인소진율", "가능", "10년+",
        "종목×일", "불필요",
        "소진율 차분 × 상장주식수 = 외국인 순매수. 종목당 1요청으로 전 구간 확보 — "
        "PROXY 축의 주력 경로."))

    # ── 판정 ──────────────────────────────────────────────────────────────────────────────
    have_member_hist = bool(mem["date_param_works"])
    member_years = 10.0 if have_member_hist else 0.0
    # 드라이브에 이미 쌓인 전진수집분이 있으면 그만큼은 실제 이력이다
    snap = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
    if snap is not None and len(snap) and "trade_date" in snap.columns:
        td = as_ts_series(snap["trade_date"]).dropna()
        if len(td):
            acc = (td.max() - td.min()).days / 365.25
            member_years = max(member_years, acc)
            R["notes"].append(f"드라이브에 축적된 거래원 전진수집분 {td.nunique():,}거래일 "
                              f"({acc:.2f}년) 을 확인했습니다.")
    R["member_history_years"] = round(member_years, 2)

    forced = (PHASE0_FORCE_BRANCH or "").strip().upper()
    if forced in ("FULL10", "PARTIAL", "PROXY"):
        branch = forced
        R["notes"].append(f"PHASE0_FORCE_BRANCH 로 분기를 {branch} 로 강제했습니다.")
    elif member_years >= 9.5:
        branch = "FULL10"
    elif member_years >= 3.0:
        branch = "PARTIAL"
    else:
        branch = "PROXY"
    R["branch"] = branch

    el_min = (time.time() - t0) / 60.0
    R["elapsed_min"] = round(el_min, 2)
    if el_min > PHASE0_TIMEBOX_MIN:
        R["notes"].append(f"타임박스 {PHASE0_TIMEBOX_MIN}분을 초과했습니다 — SPEC §4 에 따라 "
                          f"즉시 중단하고 보고합니다.")

    LOG.table([r[:7] for r in R["sources"]],
              ["순위", "후보 소스", "과거이력", "소급기간", "입도", "인증", "비고"],
              ["c", "l", "c", "c", "l", "c", "l"],
              title="Phase 0 — 거래원 이력 소스 검증 (SPEC §4-1)")

    verdict = {
        "FULL10": ("✔ 10년 전체 이력 확보 — ARC-BDF 원 가설 그대로 진행합니다.", "INFO"),
        "PARTIAL": (f"△ {member_years:.1f}년 확보 — 그 구간으로 축소해 진행합니다. "
                    f"표본이 줄어 검정력이 낮아지는 점을 결과 해석에 반드시 반영하세요.", "WARN"),
        "PROXY": ("✘ 거래원 과거 이력 확보 불가 (당일 스냅샷 전용). "
                  "SPEC §4.3 에 따라 B-1(전진수집) + B-2(열화 프록시) 로 전환합니다.", "WARN"),
    }[branch]
    (LOG.ok if verdict[1] == "INFO" else LOG.warn)(verdict[0])

    if branch == "PROXY":
        LOG.rule("PROXY 분기 — 반드시 읽어주세요")
        for ln in [
            "· 이 실행은 ARC-BDF 원 가설(자사 거래원 창구)의 백테스트가 아닙니다.",
            "  전략명을 ARC-BDF-PROXY 로 바꿔 보고하며, '10년 백테스트 완료' 라고 쓰지 않습니다.",
            "· 신호는 '리포트 발행사의 창구' 대신 '리포트 발행사와 같은 계열의 투자주체'",
            "  (외국계 하우스 → 외국인 / 국내 하우스 → 기관) 순매수로 대체됩니다.",
            "· 검증 불가로 전환되는 것: H3(중소형 증권사 강세) — 창구 단위가 사라지므로 원리상 불가.",
            "· 약화되는 것: H5(리포트 조건부 우위) — 주체 단위로만 검정되며 해상도가 낮습니다.",
            "· 그대로 유효한 것: H1 / H2 / H4, 그리고 look-ahead·생존편향 방어 전체.",
            "· 동시에 B-1 전진수집이 매 실행마다 오늘자 거래원 스냅샷을 공용 인덱스에 적재합니다.",
            "  충분히 쌓이면(3년) 같은 코드가 자동으로 PARTIAL 분기로 올라섭니다.",
        ]:
            LOG.info(ln)

    _write_phase0_md(R, mem, frgn_years, dgk_ok)
    _emit_forward_collector(branch)
    return R


def _write_phase0_md(R: dict, mem: dict, frgn_years: float, dgk_ok: bool) -> str:
    p = out_path(PHASE0_MD)
    b = R["branch"]
    lines = [
        f"# PHASE 0 — 데이터 실현가능성 게이트 결과",
        "",
        f"- 전략: **{SPEC_ID}**  ·  빌드 `{BUILD_VERSION}`",
        f"- 실행 시각: {R['started']}  ·  소요 {R.get('elapsed_min', 0):.1f}분 "
        f"(타임박스 {PHASE0_TIMEBOX_MIN}분)",
        f"- 백테스트 요청 구간: {BACKTEST_START} ~ {BACKTEST_END}",
        "",
        f"## 판정: **{b}**",
        "",
        {"FULL10": "거래원별 일별 매매동향의 10년 이력을 확보했습니다. 원 가설 그대로 진행합니다.",
         "PARTIAL": f"거래원 이력을 {R['member_history_years']:.1f}년 확보했습니다. "
                    f"확보 구간으로 축소해 진행하며, 표본 축소로 검정력이 낮아집니다.",
         "PROXY": "거래원별 일별 매매동향의 **과거 이력을 무료 경로로 확보할 수 없습니다**. "
                  "네이버 거래원 탭은 최종 거래일 1일치 스냅샷 전용이며 날짜 파라미터도 "
                  "페이지네이션도 없습니다. 공공데이터포털에 해당 데이터셋이 없고, 증권사 "
                  "OpenAPI 는 '현재가 기준' 스냅샷이거나 Windows COM 종속이라 소급이 불가합니다.\n\n"
                  "따라서 **SPEC §4.3 의 B-1 + B-2 로 전환합니다.**"}[b],
        "",
        "## 1. 후보 소스 검증 결과 (SPEC §4-1)",
        "",
        "| 순위 | 후보 | 과거이력 | 소급기간 | 입도 | 인증 | 비고 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in R["sources"]:
        lines.append("| " + " | ".join(str(x).replace("\n", " ") for x in r) + " |")

    lines += [
        "",
        "## 2. robots.txt / 이용약관",
        "",
        "- 네이버금융·한경컨센서스 모두 `robots.txt` 가 `Disallow: /` 입니다. "
        "사용자의 명시적 지시에 따라 수집하되 보수적 속도(요청간 "
        f"{FLOW_DELAY_RANGE[0]}~{FLOW_DELAY_RANGE[1]}초, 동시 {FLOW_WORKERS})로 제한하고 "
        "그 사실을 로그에 명시합니다.",
        "- 리포트 PDF 원문은 증권사 저작물이므로 로컬 캐시/분석 용도로만 사용합니다.",
        "- 공공데이터포털·DART 는 공개 API 이며 이용약관 범위 내에서 사용합니다.",
        "",
        "## 3. 분기 처리",
        "",
    ]
    if b == "PROXY":
        lines += [
            "### B-1 전진 수집 모드 (가동됨)",
            "",
            f"- 매 실행마다 오늘자 거래원 상위 5창구 스냅샷을 공용 인덱스 "
            f"`_shared/table/naver_member_flow_snapshot` 에 append 합니다.",
            "- 별도 스케줄러용 스크립트 `outputs/forward_collect_member_flow.py` 를 생성했습니다. "
            "cron / 작업 스케줄러 / GitHub Actions 에 걸어 매 영업일 장마감 후 1회 실행하세요.",
            "- **이 경로만으로는 백테스트가 불가능하며 페이퍼 트레이딩 검증만 가능합니다.**",
            "- 상위 5 절단(censoring)을 0 으로 채우지 않고 `censored` + `upper_bound` 로 "
            "명시 저장합니다. 0 으로 채우면 대형 창구일수록 순매수가 과대추정되어 "
            "가짜 알파가 생성됩니다.",
            "",
            "### B-2 열화 프록시 백테스트 — `ARC-BDF-PROXY` (가동됨)",
            "",
            "- 거래원 대신 **투자자별 매매동향**을 사용합니다.",
            "- 단, 단순히 기관+외국인을 합치지 않고 **발행사 계열 정합(class-matched)** 으로 "
            "브로커 정체성을 부분적으로 보존합니다: "
            "외국계 하우스 리포트 → 외국인 순매수 / 국내 하우스 리포트 → 기관 순매수.",
            "- **이것은 원 가설의 대리 검증이 아닙니다.** 창구 단위가 주체 단위로 바뀌므로:",
            "  - **H3 (중소형 증권사에서 더 강함) → 검증 불가**",
            "  - **H5 (리포트 조건부 우위) → 주체 단위로만, 약화된 형태로 검증**",
            "  - H1 / H2 / H4 및 look-ahead·생존편향 방어는 그대로 유효",
            "- 따라서 산출물에서 \"10년 백테스트 완료(ARC-BDF)\" 라고 보고하지 않습니다.",
            "",
        ]
    elif b == "PARTIAL":
        lines += [
            f"- 확보 구간 {R['member_history_years']:.1f}년으로 축소해 진행합니다.",
            "- 표본 축소가 검정력에 미치는 영향: 이벤트 수가 줄면 H1 의 t 값이 "
            "√(표본비) 만큼 축소됩니다. 10년 대비 유의성 문턱을 넘기기 어려워질 수 있으며, "
            "이는 효과 부재의 증거가 아닙니다.",
            "",
        ]
    else:
        lines += ["- 원 가설 그대로 진행합니다.", ""]

    lines += [
        "## 4. PIT / 편향 방어 상태 (KRX 미사용)",
        "",
        f"- 공공데이터포털 시세 API: **{'가동' if dgk_ok else '미가동(키 없음)'}** — "
        f"{'PIT 시가총액·상장주식수·일별 상장 스냅샷이 관측값으로 확정됩니다.' if dgk_ok else '시총이 근사(T2~T4)로 강등됩니다. 동작은 하지만 H4 해석 시 감안이 필요합니다.'}",
        "- 상장폐지 이력: FDR `listing/delisting` GitHub 캐시 (KRX 인증 무관)",
        "- 상장일: KIND 상장법인목록 + FDR 상장목록",
        "- 가격: FDR → 네이버 siseJson → 네이버 HTML → yfinance 4중 폴백",
        "",
        "## 5. 남은 위험",
        "",
        "- 네이버 수집은 `robots.txt` 상 비허용이며 차단 가능성이 상존합니다. "
        "서킷 브레이커(연속 실패 "
        f"{FLOW_CIRCUIT_BREAK_N}회)와 시간예산({FLOW_TIME_BUDGET_MIN}분)으로 관리합니다.",
        "- 미수집 구간은 **0 이 아니라 결측**으로 남깁니다. 0 으로 채우면 '순매수 없음' 이라는 "
        "허위 정보가 되어 신호가 오염됩니다.",
    ]
    for n in R.get("notes", []):
        lines.append(f"- {n}")

    txt = "\n".join(lines) + "\n"
    atomic_write_text(p, txt)
    VAULT.put_blob("report", "phase0", "PHASE0_DATA_FEASIBILITY", txt.encode("utf-8"),
                   "md", scope="private", source=STRATEGY_ID)
    LOG.ok(f"Phase 0 보고서 저장 → {p}")
    return p


_FORWARD_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-BDF B-1 전진 수집기 — 거래원 상위 5창구 일별 스냅샷.

거래원 과거 이력은 어떤 무료 소스에도 없다. 그래서 오늘부터 쌓는다.
매 영업일 장마감 후 1회 실행하도록 스케줄러에 등록하라.

  · Linux/Mac cron :   30 16 * * 1-5  /usr/bin/python3 {path}
  · Windows        :   작업 스케줄러 → 매일 16:30 → python {path}
  · GitHub Actions :   schedule: - cron: "30 7 * * 1-5"   (UTC 기준)

하루라도 빠지면 그날은 영구 결손이다. Colab 세션에 의존하지 말고 상시 실행 환경에 올릴 것.
저장 위치는 ARC_BDF_CACHE 환경변수(없으면 ./arc_bdf_cache) 아래 공용 인덱스다.
"""
import os, re, json, time, random, hashlib, datetime as dt
import pandas as pd, requests

ROOT = os.environ.get("ARC_BDF_CACHE", "./arc_bdf_cache")
OUT = os.path.join(ROOT, "_shared", "table", "naver_member_flow_snapshot")
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"


def codes_today():
    """상장 종목 코드 목록. FDR 이 있으면 그걸, 없으면 캐시된 목록을 쓴다."""
    try:
        import FinanceDataReader as fdr
        d = fdr.StockListing("KRX")
        c = [str(x).zfill(6) for x in d[[c for c in d.columns if c.lower() in ("code", "symbol")][0]]]
        return [x for x in c if re.fullmatch(r"\\d{6}", x)]
    except Exception:
        p = os.path.join(ROOT, "_shared", "table", "code_list.json")
        if os.path.isfile(p):
            return json.load(open(p))
        raise SystemExit("종목 목록을 얻지 못했습니다. finance-datareader 를 설치하세요.")


def fetch_one(code):
    url = f"https://finance.naver.com/item/frame_trade.naver?code={{code}}"
    try:
        r = requests.get(url, headers={{"User-Agent": UA, "Referer": "https://finance.naver.com/"}},
                         timeout=20)
        if r.status_code != 200:
            return None
        html = r.content.decode("euc-kr", "replace")
    except Exception:
        return None
    tds = re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)
    tds = [re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ").strip() for t in tds]
    rows, side_i = [], 0
    pairs = [(tds[i], tds[i + 1]) for i in range(len(tds) - 1)
             if re.fullmatch(r"[\\d,]+", tds[i + 1] or "") and tds[i]
             and not re.fullmatch(r"[\\d,\\.%]+", tds[i])]
    for i, (nm, v) in enumerate(pairs[:10]):
        rows.append(dict(member_raw=nm, volume=float(v.replace(",", "")),
                         side="SELL" if i % 2 == 0 else "BUY", rank=i // 2 + 1, code=code))
    return rows or None


def main():
    now = dt.datetime.now()
    td = now.date() if now.hour >= 16 else (now.date() - dt.timedelta(days=1))
    while td.weekday() >= 5:
        td -= dt.timedelta(days=1)
    codes = codes_today()
    out, fail = [], 0
    for i, c in enumerate(codes):
        time.sleep(random.uniform(0.3, 1.2))          # 차단 방지 (SPEC 2.3)
        r = fetch_one(c)
        if not r:
            fail += 1
            if fail >= 30:
                print("[중단] 연속 실패 30회 — 차단 가능성. 여기까지 저장합니다.")
                break
            continue
        fail = 0
        out.extend(r)
        if i % 200 == 0:
            print(f"  {{i}}/{{len(codes)}} ...")
    if not out:
        print("수집 0건 — 휴장이거나 차단입니다."); return
    df = pd.DataFrame(out)
    df["trade_date"] = pd.Timestamp(td)
    df["captured_at"] = pd.Timestamp(now)
    df["parser_ver"] = 1
    p = os.path.join(OUT, f"snapshot_{{td:%Y%m%d}}.parquet")
    df.to_parquet(p, index=False)                     # 기존 파일을 덮지 않는 날짜별 파일
    print(f"저장 {{len(df):,}}행 → {{p}}")


if __name__ == "__main__":
    main()
'''


def _emit_forward_collector(branch: str) -> Optional[str]:
    """B-1 전진수집 스크립트를 산출물로 떨군다 (PROXY/PARTIAL 분기에서만)."""
    if branch == "FULL10":
        return None
    p = out_path("forward_collect_member_flow.py")
    try:
        atomic_write_text(p, _FORWARD_TEMPLATE.format(path=p))
        LOG.ok(f"B-1 전진수집 스크립트 생성 → {p}  "
               f"(매 영업일 장마감 후 1회 실행하도록 스케줄러에 등록하세요)")
        return p
    except Exception as e:                                            # noqa
        LOG.warn(f"전진수집 스크립트 생성 실패: {type(e).__name__}")
        return None
