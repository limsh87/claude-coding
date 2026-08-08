
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  산출물 — 성과검증표 / 강건성표 / 해석표 / 최종판정                                   ║
# ║                                                                                          ║
# ║  원칙: 숫자가 나쁘면 나쁘게 적는다. 판정 기준(SPEC §11)은 사전 확정이며 사후 변경 없다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance(bts: Dict[str, dict], bench: Dict[str, pd.Series],
                       cal: pd.DatetimeIndex, title: str = "") -> pd.DataFrame:
    """12개 구성 전체 성과표 + 벤치마크 비교."""
    rows = []
    for name, bt in bts.items():
        st = bt.get("stats") or {}
        if not st:
            continue
        rows.append([name, f"{st.get('CAGR', np.nan)*100:+.2f}%",
                     f"{st.get('연변동성', np.nan)*100:.1f}%",
                     f"{st.get('Sharpe', np.nan):.2f}",
                     f"{st.get('Sortino', np.nan):.2f}",
                     f"{st.get('MDD', np.nan)*100:.1f}%",
                     f"{st.get('Calmar', np.nan):.2f}",
                     f"{st.get('t통계량(NW)', np.nan):+.2f}",
                     f"{st.get('이벤트체결수', 0):,}",
                     f"{st.get('승률', np.nan)*100:.0f}%",
                     f"{st.get('평균보유일', np.nan):.0f}",
                     f"{st.get('연회전율', np.nan):.1f}x"])
    if not rows:
        LOG.warn("성과표를 만들 결과가 없습니다.")
        return pd.DataFrame()
    LOG.table(rows, ["구성", "CAGR", "변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                     "t(NW)", "체결수", "승률", "평균보유", "회전율"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              title=f"성과 검증표 {title}".strip())

    brows = []
    for bn, bs in bench.items():
        if bn.startswith("_") or bs is None or not len(bs):
            continue
        r = bs.reindex(cal).fillna(0.0).to_numpy(float)
        eq = float(np.prod(1 + r))
        yrs = max(len(r) / 252.0, 1e-9)
        cagr = eq ** (1 / yrs) - 1 if eq > 0 else np.nan
        vol = r.std(ddof=1) * math.sqrt(252) if len(r) > 1 else np.nan
        peak = np.maximum.accumulate(np.cumprod(1 + r))
        mdd = float((np.cumprod(1 + r) / peak - 1).min())
        brows.append([bn, f"{cagr*100:+.2f}%", f"{vol*100:.1f}%",
                      f"{(cagr/vol) if vol else float('nan'):.2f}", f"{mdd*100:.1f}%"])
    if brows:
        LOG.table(brows, ["벤치마크", "CAGR", "변동성", "Sharpe", "MDD"],
                  ["l", "r", "r", "r", "r"],
                  title="벤치마크 — ★ 진짜 비교 대상은 지수가 아니라 '리포트 무차별 매수' 다")

    M = pd.DataFrame([{"구성": n, **(b.get("stats") or {})} for n, b in bts.items()])
    return M


def report_yearly(bts: Dict[str, dict], best: str, bench: Dict[str, pd.Series],
                  cal: pd.DatetimeIndex) -> None:
    if best not in bts:
        return
    yr = yearly_returns(bts[best]["daily"])
    nb = bench.get("나이브(리포트무차별매수)")
    ny = (yearly_returns(pd.DataFrame({"date": cal, "ret": nb.reindex(cal).fillna(0.0)}))
          if nb is not None else pd.Series(dtype=float))
    ks = bench.get("KOSPI")
    ky = (yearly_returns(pd.DataFrame({"date": cal, "ret": ks.reindex(cal).fillna(0.0)}))
          if ks is not None else pd.Series(dtype=float))
    rows = []
    for y in yr.index:
        rows.append([str(int(y)), f"{yr[y]*100:+.2f}%",
                     f"{ny.get(y, np.nan)*100:+.2f}%" if len(ny) else "-",
                     f"{ky.get(y, np.nan)*100:+.2f}%" if len(ky) else "-",
                     f"{(yr[y]-ny.get(y, np.nan))*100:+.2f}%p" if len(ny) else "-"])
    LOG.table(rows, ["연도", "전략", "나이브(리포트전량)", "KOSPI", "나이브 대비 초과"],
              ["c", "r", "r", "r", "r"],
              title=f"연도별 수익률 — 대표구성 [{best}]")


def report_costs(cost_bts: Dict[str, Dict[str, dict]], naive_by_cost: Dict[float, float],
                 best: str) -> str:
    """SPEC §7.1: 비용 0 / 기본 / 2배 3종 모두 보고. 2배에서 살아남는지가 핵심 판정 기준."""
    rows, md = [], ["# 비용 민감도 (SPEC §7.1)", "",
                    "| 시나리오 | CAGR | Sharpe | MDD | 나이브 대비 초과 | 판정 |",
                    "|---|---|---|---|---|---|"]
    survive2x = False
    for lab, mult in [(l, m) for l, m in COST_SCENARIOS]:
        bt = (cost_bts.get(lab) or {}).get(best)
        if not bt:
            rows.append([lab, "-", "-", "-", "-", "결과없음"])
            continue
        st = bt["stats"]
        nv = naive_by_cost.get(mult, np.nan)
        exc = st.get("CAGR", np.nan) - nv
        ok = np.isfinite(exc) and exc > 0
        if mult >= 2.0:
            survive2x = bool(ok)
        rows.append([lab, f"{st.get('CAGR', np.nan)*100:+.2f}%",
                     f"{st.get('Sharpe', np.nan):.2f}",
                     f"{st.get('MDD', np.nan)*100:.1f}%",
                     f"{exc*100:+.2f}%p" if np.isfinite(exc) else "-",
                     "초과유지" if ok else "초과소멸"])
        md.append(f"| {lab} | {st.get('CAGR', np.nan)*100:+.2f}% | "
                  f"{st.get('Sharpe', np.nan):.2f} | {st.get('MDD', np.nan)*100:.1f}% | "
                  f"{exc*100:+.2f}%p | {'초과유지' if ok else '초과소멸'} |")
    LOG.table(rows, ["비용 시나리오", "CAGR", "Sharpe", "MDD", "나이브 대비", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="비용 민감도 — ★ 이 전략은 회전율이 높다. 2배에서 살아남는가가 핵심이다")
    md += ["", f"**2배 비용 시나리오 생존: {'예' if survive2x else '아니오'}**", "",
           "- 편도 수수료 1.5bp · 슬리피지 대형 10bp / 중형 20bp / 소형 35bp",
           "- 증권거래세는 연도별 테이블(2016 0.30% → 2025 0.15%, 5회 인하)로 적용했다. "
           "단일 세율을 쓰면 초기 구간 비용이 과소평가되어 성과가 부풀려진다.",
           "- 비교 대상인 나이브 전략에도 동일한 비용을 적용했다."]
    return "\n".join(md) + "\n"


def report_robustness(rob: dict) -> None:
    rows = []
    for k, v in rob.items():
        if not isinstance(v, dict):
            continue
        rows.append([k, v.get("value", "-"), v.get("thresh", "-"),
                     "통과" if v.get("pass") else ("판정불가" if v.get("pass") is None else "실패"),
                     _trunc(str(v.get("note", "")), 46)])
    if rows:
        LOG.table(rows, ["검정", "값", "기준", "판정", "비고"],
                  ["l", "r", "r", "c", "l"], title="강건성 검사 (SPEC §9)")


INTERP = [
    ("확증(Confirmation)", "리포트 발간 + 자사(계열) 창구 순매수 동반",
     "리서치가 실제 기관 수요로 전환되고 있다는 관측. 롱 후보."),
    ("페이드(Distribution)", "리포트 발간 직후 자사(계열) 창구 순매도",
     "물량 분배 국면일 수 있다. 롱온리에서는 배제 필터로 쓴다."),
    ("잔차 소멸", "원값에서는 신호가 있는데 이중디민 후 사라짐",
     "관측된 것은 알파가 아니라 창구 고정효과다. 그것이 결론이다."),
    ("H5 실패", "무리포트 대조군이 확증군만큼 좋음",
     "리포트가 정보를 더하지 않는다 → '리포트 전략' 이 아니라 '플로우 전략' 이다."),
    ("H3 역전", "대형 리테일 창구에서 오히려 강함",
     "메커니즘과 반대다. SPEC §3 에 따라 데이터마이닝으로 판정한다."),
    ("플라시보 유의", "가짜 이벤트에서도 효과 검출",
     "파이프라인에 미래참조가 있다. 결과 전체를 폐기해야 한다."),
]


def report_interpretation(res: dict, mode: str) -> None:
    LOG.table([[k, cond, mean] for k, cond, mean in INTERP],
              ["패턴", "관측 조건", "해석"], ["l", "l", "l"],
              title="해석표 — 무엇을 보면 무엇이라고 읽는가")
    if mode == "PROXY":
        LOG.warn("★ 이 실행은 ARC-BDF-PROXY 입니다. 신호는 '증권사 창구' 가 아니라 "
                 "'투자 주체(기관/외국인)' 이며, 원 가설의 대리 검증이 아닙니다. "
                 "H3 는 원리상 검정 불가이고 H5 는 해상도가 낮아진 형태로만 검정됩니다.")


def final_verdict(res: dict, rob: dict, cost_md: str, mode: str,
                  survive2x: bool, placebo_clean: bool) -> str:
    """SPEC §11 — 사전 확정 수용/폐기 기준. 사후 변경 없음."""
    pbo = rob.get("PBO", {}).get("raw", np.nan)
    dsr = rob.get("DSR", {}).get("raw", np.nan)
    h1 = res.get("H1_fdr", False) and res.get("H1_pass", False)
    h5 = res.get("H5_fdr", False) and res.get("H5_pass", False)
    h3 = res.get("H3_fdr", False) and res.get("H3_pass", False)
    pbo_ok = np.isfinite(pbo) and pbo < 0.5
    dsr_ok = np.isfinite(dsr) and dsr > 0.5      # DSR 은 확률이므로 '0 초과' 의 실질 기준은 0.5
    accept = h1 and h5 and h3 and pbo_ok and dsr_ok and survive2x and placebo_clean

    if not placebo_clean:
        verdict, why = "KILL", "플라시보 테스트에서 유의한 효과가 검출되었습니다(파이프라인 결함)."
    elif not h1:
        verdict, why = "KILL", "H1(확증군 CAR>0)이 BH-FDR 보정 후 통과하지 못했습니다."
    elif np.isfinite(pbo) and pbo >= 0.5:
        verdict, why = "KILL", f"PBO={pbo:.2f} ≥ 0.5 — 과최적화 확률이 절반을 넘습니다."
    elif not survive2x:
        verdict, why = "KILL", "비용 2배 시나리오에서 나이브 벤치마크 대비 초과수익이 소멸합니다."
    elif h1 and not h5:
        verdict, why = "CONDITIONAL", ("H1 은 통과했으나 H5(리포트 조건부 우위)가 실패했습니다. "
                                       "리포트 파트를 제거한 순수 브로커/수급 플로우 전략으로 "
                                       "재정의해 별도 검증해야 하며, 현 형태로는 배분 금지입니다.")
    elif accept:
        verdict, why = "ACCEPT", "SPEC §11 의 모든 수용 조건을 충족했습니다."
    else:
        missing = [n for n, ok in (("H3", h3), ("DSR", dsr_ok)) if not ok]
        verdict, why = "CONDITIONAL", f"핵심 조건 일부 미충족: {', '.join(missing) or '기타'}."

    lines = [
        "# FINAL VERDICT", "",
        f"## 판정: **{verdict}**", "", why, "",
        f"- 전략: {STRATEGY_NAME} ({'ARC-BDF-PROXY' if mode == 'PROXY' else 'ARC-BDF'})",
        f"- 빌드: `{BUILD_VERSION}` · 구간 {BACKTEST_START} ~ {BACKTEST_END}",
        "",
        "## SPEC §11 조건별 충족 현황", "",
        "| 조건 | 기준 | 결과 | 충족 |",
        "|---|---|---|---|",
        f"| H1 (BH-FDR 후) | 통과 | {'통과' if h1 else '미통과'} | {'✔' if h1 else '✘'} |",
        f"| H5 (리포트 조건부 우위) | 통과 | {'통과' if h5 else '미통과'} | {'✔' if h5 else '✘'} |",
        f"| H3 (중소형사 강화) | 통과 | "
        f"{'검정불가(PROXY)' if mode == 'PROXY' else ('통과' if h3 else '미통과')} | "
        f"{'✔' if h3 else '✘'} |",
        f"| PBO | < 0.50 | {pbo:.3f} | {'✔' if pbo_ok else '✘'} |",
        f"| DSR | > 0.50 | {dsr:.3f} | {'✔' if dsr_ok else '✘'} |",
        f"| 비용 2배 초과수익 | 유지 | {'유지' if survive2x else '소멸'} | "
        f"{'✔' if survive2x else '✘'} |",
        f"| 플라시보 | 무효과 | {'무효과' if placebo_clean else '★효과검출'} | "
        f"{'✔' if placebo_clean else '✘'} |",
        "",
    ]
    if mode == "PROXY":
        lines += [
            "## ⚠ 이 판정의 적용 범위", "",
            "이 실행은 **ARC-BDF-PROXY** 입니다. 거래원(회원사)별 일별 매매동향의 과거 이력을",
            "확보할 수 없어(Phase 0 참조) 신호를 '투자 주체(기관/외국인)' 로 대체했습니다.",
            "",
            "- 이것은 **원 가설(ARC-BDF)의 대리 검증이 아닙니다.**",
            "- **H3 는 원리상 검정 불가**입니다 — 창구 단위가 사라졌기 때문입니다.",
            "- 따라서 위 판정이 ACCEPT 라 해도 그것은 ARC-BDF 의 수용이 아니라",
            "  ARC-BDF-PROXY 라는 별개 전략의 수용입니다.",
            "- 'ARC-BDF 10년 백테스트 완료' 라고 보고해서는 안 됩니다.",
            "",
        ]
    lines += ["## 비용 민감도", "", cost_md, ""]
    lines += ["## 참고", "",
              "- 이 문서의 판정 기준은 실행 전에 확정된 것이며 결과를 본 뒤 변경하지 않았습니다.",
              "- 특정 증권사에 대한 가치판단은 담지 않습니다. 통계적 패턴만 기술합니다(SPEC §0.5).",
              "- 투자자문이 아닙니다."]
    return "\n".join(lines) + "\n"


def report_dataflow(ctx: dict) -> None:
    """★ 사용자 요구: '데이터 입출력이 어디서 이뤄지는지 한눈에'."""
    rows = []
    for k, v in ctx.items():
        if isinstance(v, pd.DataFrame):
            rows.append([k, f"{len(v):,}행 × {len(v.columns)}열", f"{mem_mb(v):.1f}MB",
                         ", ".join(map(str, list(v.columns)[:6]))])
        elif isinstance(v, (list, tuple, set)):
            rows.append([k, f"{len(v):,}개", "-", ""])
    if rows:
        LOG.table(rows, ["데이터셋", "규모", "메모리", "주요 컬럼"],
                  ["l", "r", "r", "l"], title="데이터 흐름 — 무엇이 어디까지 만들어졌는가")


def write_outputs(paths: Dict[str, str]) -> List[str]:
    ok = []
    for name, content in paths.items():
        try:
            p = out_path(name)
            atomic_write_text(p, content)
            VAULT.put_blob("report", "arc_bdf", name.replace(".", "_"),
                           content.encode("utf-8"), name.rsplit(".", 1)[-1],
                           scope="private", source=STRATEGY_ID)
            ok.append(p)
        except Exception as e:                                        # noqa
            LOG.warn(f"{name} 저장 실패: {type(e).__name__}: {e}")
    return ok
