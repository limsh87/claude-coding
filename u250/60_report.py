# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §7 산출물                                                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

FACTOR_DIR = {"F1": "F1_capital_events", "F2": "F2_insider",
              "F3": "F3_liquidity", "F4": "F4_contracts"}


def _out(*parts) -> str:
    p = os.path.join(OUTPUT_DIR, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def write_xlsx(path: str, sheets: Dict[str, pd.DataFrame]) -> str:
    """엑셀로 쓰되, 엔진이 없으면 조용히 실패하지 않고 CSV 로 떨어뜨리고 그 사실을 알린다."""
    sheets = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame(v))
              for k, v in sheets.items() if v is not None}
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            for name, df in sheets.items():
                (df if len(df) else pd.DataFrame({"(비어 있음)": []})).to_excel(
                    w, sheet_name=str(name)[:31], index=False)
        LOG.ok(f"산출물 저장 — {os.path.relpath(path, OUTPUT_DIR)} ({len(sheets)}시트)")
        return path
    except Exception as e:                                              # noqa
        base = os.path.splitext(path)[0]
        os.makedirs(base, exist_ok=True)
        for name, df in sheets.items():
            df.to_csv(os.path.join(base, f"{name}.csv"), index=False, encoding="utf-8-sig")
        LOG.warn(f"엑셀 저장 실패({type(e).__name__}) — CSV 로 저장했습니다: "
                 f"{os.path.relpath(base, OUTPUT_DIR)}/  (openpyxl 설치 시 xlsx 로 나옵니다)")
        return base


def write_md(path: str, text: str) -> str:
    atomic_write_text(path, text)
    LOG.ok(f"산출물 저장 — {os.path.relpath(path, OUTPUT_DIR)}")
    return path


def perf_row(name: str, r: BTResult, ppy: float, base: Optional[BTResult] = None) -> dict:
    s = r.stats(ppy)
    row = {"전략": name, "CAGR": s["cagr"], "연환산변동성": s["vol"], "MDD": s["mdd"],
           "Sharpe": s["sharpe"], "연회전율": s["turnover"], "누적실현거래비용": s["cost"],
           "구간수": s["n"], "평균보유종목": float(r.n_holdings.mean()) if len(r.n_holdings) else np.nan}
    if base is not None:
        row["초과CAGR(vs B2)"] = s["cagr"] - base.stats(ppy)["cagr"]
    return row


def yearly_table(results: Dict[str, BTResult]) -> pd.DataFrame:
    cols = {}
    for k, r in results.items():
        cols[k] = r.yearly()
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).reset_index().rename(columns={"index": "연도"})


def phase0_report(covs: Dict[str, Coverage], b_cov: Dict[str, BTResult],
                  ppy: float, b2: Optional[BTResult]) -> str:
    summ = pd.DataFrame([{
        "팩터": c.factor, "팩터명": FACTOR_META[c.factor]["name"],
        "cov_stock": c.cov_stock, "cov_stock_rebal": c.cov_stock_rebal,
        "cov_universe_rebal(중앙값)": c.median_cov, "signal_rate": c.signal_rate,
        "판정": c.verdict,
        "조치": {"PASS": "정상 진행", "PARTIAL": "부분 커버 팩터로 표기하고 진행 (미커버 중립)",
                 "HOLD": "백테스트 보류 — §6.4 조기 중단"}[c.verdict],
    } for c in covs.values()])
    sheets = {"요약": summ}
    for f, c in covs.items():
        sheets[f"{f}_cov_ts"] = c.cov_universe_rebal.rename("U250내_관측종목수").reset_index() \
            .rename(columns={"index": "rebal"})
        sheets[f"{f}_cov_trend"] = c.cov_trend.rename("중앙값").reset_index() \
            .rename(columns={"index": "연도"})
        if c.bias is not None and len(c.bias):
            sheets[f"{f}_bias"] = c.bias
    if b_cov:
        rows = [perf_row(f"B_cov[{f}] 커버종목만 EW 순수익", r, ppy, b2) for f, r in b_cov.items()]
        sheets["B_cov"] = pd.DataFrame(rows)
    return write_xlsx(_out("phase0_coverage_report.xlsx"), sheets)


def baseline_report(base: Dict[str, BTResult], nulls: Dict[int, dict], ppy: float) -> str:
    rows = [perf_row(r.name, r, ppy, base.get("B2")) for r in base.values()]
    nullrows = []
    for n, d in nulls.items():
        if not len(d.get("cagr", [])):
            continue
        c = d["cagr"]
        nullrows.append({"N": n, "시행": d["sims"], "중앙 CAGR": float(np.median(c)),
                         "p05": float(np.quantile(c, .05)), "p95": d["p95"],
                         "p99": float(np.quantile(c, .99)),
                         "회전율정합": d.get("matched", False)})
    return write_xlsx(_out("baseline_B1_B4.xlsx"),
                      {"성과요약": pd.DataFrame(rows),
                       "연도별수익률": yearly_table(base),
                       "B4_무작위분포": pd.DataFrame(nullrows)})


def gate_scorecard_md(factor: str, gates: List[GateResult], head: dict) -> str:
    L = [f"# {factor} 게이트 스코어카드 — {FACTOR_META[factor]['name']}", "",
         f"> {FACTOR_META[factor]['hyp']}", "",
         f"- 주 명세: N={SPEC_N_PRIMARY}, 미커버 처리=neutral, AUM {SPEC_GATE['g2_aum_krw']:,}원",
         f"- 사전등록 해시: `{spec_sha256()[:16]}` · 명세 v{SPEC_VERSION}", ""]
    for k, v in head.items():
        L.append(f"- {k}: {v}")
    L += ["", "| # | 게이트 | 판정 | 값 | 기준 | 비고 |", "|---|---|---|---|---|---|"]
    for g in gates:
        mark = "✅ 통과" if g.passed is True else ("❌ 실패" if g.passed is False else "— 판정불가")
        L.append(f"| {g.gate} | {_GATE_NAME[g.gate]} | {mark} | {g.value} | {g.criterion} | {g.note} |")
    npass = sum(1 for g in gates if g.passed is True)
    nfail = sum(1 for g in gates if g.passed is False)
    L += ["", f"**종합: {npass}통과 / {nfail}실패 / "
              f"{sum(1 for g in gates if g.passed is None)}판정불가**",
          "", "전부 통과해야 '유효'다(§6.3). 통과시키기 위해 명세를 수정하지 않는다(§8-3, §8-5)."]
    return "\n".join(L)


_GATE_NAME = {"G1": "무작위 대비", "G2": "순수익 초과", "G3": "연도 안정성", "G4": "OOS 일관성",
              "G5": "다중검정", "G6": "단조성", "G7": "플라시보"}


def master_scorecard(all_gates: Dict[str, List[GateResult]], excess: Dict[str, dict],
                     covs: Dict[str, Coverage], capacity: pd.DataFrame,
                     amendments: List[str]) -> str:
    L = ["# MASTER SCORECARD — U250 대체데이터 팩터 독립 검정", "",
         f"- 명세 v{SPEC_VERSION} · 사전등록 해시 `{spec_sha256()}`",
         f"- 실행 {_dt.datetime.now():%Y-%m-%d %H:%M} · 유니버스 U{SPEC_UNIV['main_n']} EW · "
         f"리밸 {REBAL_FREQ} · 시행수(다중검정) {SPEC_TRIALS_TOTAL}",
         f"- 캐시 재활용: {len(LAKE.items):,}개 파일 (스캔 {LAKE.scanned:,}개 중)", "",
         "## 1. 4팩터 × G1~G7 격자", "",
         "| 팩터 | 커버리지 | G1 무작위 | G2 초과 | G3 안정 | G4 OOS | G5 다중검정 | G6 단조 | G7 플라시보 | 유효 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    any_pass = False
    for f in ("F1", "F2", "F3", "F4"):
        gs = {g.gate: g for g in all_gates.get(f, [])}
        cells = []
        for k in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            g = gs.get(k)
            cells.append("—" if g is None or g.passed is None else ("✅" if g.passed else "❌"))
        valid = all(c == "✅" for c in cells if c != "—") and any(c == "✅" for c in cells)
        # G6 가 '해당 없음(필터형)'인 경우를 제외하고 전부 통과해야 유효
        req = [gs.get(k) for k in ("G1", "G2", "G3", "G4", "G5", "G7")]
        valid = all(g is not None and g.passed is True for g in req) and \
            (gs.get("G6") is None or gs["G6"].passed is not False)
        any_pass |= valid
        cv = covs.get(f)
        L.append(f"| {f} {FACTOR_META[f]['name']} | {cv.verdict if cv else '—'}"
                 f"({cv.median_cov:.0f}종목) | " + " | ".join(cells) +
                 f" | {'**유효**' if valid else '무효'} |")
    L += ["", "## 2. B2 대비 순수익 초과 CAGR", "",
          "| 팩터 | AUM 1억 (IS) | AUM 1억 (OOS) | 동적 AUM (IS) | B_cov 대비 (IS) |",
          "|---|---|---|---|---|"]
    for f in ("F1", "F2", "F3", "F4"):
        x = excess.get(f, {})
        def _f(k):
            v = x.get(k)
            return f"{v:+.2%}p" if isinstance(v, float) and np.isfinite(v) else "—"
        L.append(f"| {f} | {_f('is')} | {_f('oos')} | {_f('dyn')} | {_f('bcov')} |")

    L += ["", "## 3. 판정", ""]
    if any_pass:
        L.append("일부 팩터가 G1~G7 을 통과했다. 위 격자와 §7 팩터별 산출물을 함께 볼 것.")
    else:
        L += ["> ### ★ 전 팩터가 G1~G7 을 통과하지 못했다.",
              ">",
              "> 명세서 §7 의 요구대로 이 사실을 명시적으로 기록한다. "
              "통과 팩터를 만들기 위해 명세를 수정하지 않았다.",
              "> 민감도 격자는 팩터당 4개로 상한이 걸려 있고(코드가 강제), "
              "임계값·기간·N값은 1차 결과를 본 뒤 조정하지 않았다.", ""]
    if len(capacity):
        cols = [str(a) for a in SPEC_AUM_LADDER] + ["dynamic"]
        hdr = [f"{a/1e8:.0f}억" if a >= 1e8 else f"{a/1e7:.0f}천만" for a in SPEC_AUM_LADDER] + ["동적 AUM"]
        L += ["", "## 4. 용량 (AUM별 순수익 CAGR 감쇠)", "",
              "| 전략 | " + " | ".join(hdr) + " |",
              "|---|" + "---|" * len(hdr)]
        for _, r in capacity.iterrows():
            cells = []
            for c in cols:
                v = r.get(c, np.nan)
                cells.append(f"{v:.2%}" if isinstance(v, (int, float)) and np.isfinite(v) else "—")
            L.append(f"| {r['전략']} | " + " | ".join(cells) + " |")
    if amendments:
        L += ["", "## 5. 명세 개정 요청 (코드를 고치지 않고 기록만 한다 — §8)", ""]
        L += [f"{i+1}. {a}" for i, a in enumerate(amendments)]
    L += ["", "---", "", "### 실행 기록", "",
          "```", json.dumps(RUNLOG, ensure_ascii=False, indent=2, default=str)[:6000], "```"]
    return "\n".join(L)
