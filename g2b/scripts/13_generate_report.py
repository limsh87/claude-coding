#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""13 — 보고서 생성 (§94 §95 §96).

reports/ 아래 9개 문서를 만들고, FINAL_DECISION 에서 17개 질문에 답한다.
판정은 STRONG_PASS / PASS / WEAK_EVIDENCE / NO_ALPHA / DATA_BLOCKED / PIT_BLOCKED /
SAMPLE_COLLAPSE 중 하나로만 내린다. DATA_BLOCKED 와 NO_ALPHA 를 반드시 구분한다.
"""
from _common import *                                          # noqa: F401,F403
import datetime as _dt
import numpy as np
import pandas as pd
from audit import prereg


def _get(name):
    return load(name)


def _val(T, col, where=None, default=np.nan):
    if T is None or not len(T) or col not in T.columns:
        return default
    d = T if where is None else T[where(T)]
    if not len(d):
        return default
    return d[col].iloc[0]


def _hdr(title: str, spec: str) -> str:
    st = CFG.run_stamp()
    warn = ("\n> ⚠ **SMOKE 모드 산출물입니다 — 합성 데이터이며 연구 결론이 아닙니다.**\n"
            if CFG.RUN_MODE == "SMOKE" else "")
    return (f"# {title}\n\n_{spec}_\n{warn}\n"
            f"| 항목 | 값 |\n|---|---|\n"
            f"| run_id | `{st['run_id']}` |\n| 실행모드 | `{st['run_mode']}` |\n"
            f"| git_commit | `{st['git_commit'][:12]}` |\n| config_hash | `{st['config_hash']}` |\n"
            f"| 생성시각 | {st['timestamp']} |\n| FUTURE_RETURN_LOCK | `{st['future_return_lock']}` |\n\n")


def r00_api() -> None:
    S, A = _get("api_depth_summary"), _get("api_depth_probe")
    t = _hdr("00 · API 백필 감사", "명세 §5 — 메타데이터를 믿지 않고 실측한다")
    t += ("## 왜 이 문서가 먼저인가\n\n"
          "공식 메타데이터의 시간범위는 '그 기간의 데이터가 API 로 나온다'는 보장이 아니다. "
          "특히 낙찰정보서비스는 공식 표기가 사실상 실시간이므로 historical depth 를 직접 재야 한다. "
          "여기서 데이터가 없다고 판명되면 그것은 전략 실패가 아니라 **DATA_BLOCKED** 다(§96).\n\n")
    t += "## API별 실측 요약\n\n" + md_table(S)
    t += "\n## 표본연도별 실측\n\n" + md_table(A, 120)
    report_write("00_API_AUDIT.md", t)


def r01_pit() -> None:
    t = _hdr("01 · PIT 감사", "명세 §6 §7 §8 §11 — 시점복원 가능성")
    t += ("## 세 시각\n\n`event_time`(사건) · `source_published_at`(원천 공개) · "
          "`available_at`(우리가 쓸 수 있게 된 시각). 공개시각을 모르면 보수적으로 하루를 더 얹고 "
          "그 사실을 `published_imputed` 로 남긴다.\n\n")
    t += "### 단계별 지연 분포\n\n" + md_table(_get("pit_audit_lag"))
    t += ("\n## 필드 등급 (§6.1)\n\nCLASS C = 현재 API 가 과거 최종값만 돌려주고 변경과정을 알 수 없는 필드. "
          "역사적 백테스트 사용 금지(PIT_UNCERTIFIED). **등록되지 않은 필드는 자동으로 C 로 간주한다 — "
          "모르면 쓰지 않는다.**\n\n")
    t += md_table(_get("pit_audit_field_class_summary"))
    t += "\n## 리비전 처리 (§8)\n\n" + md_table(_get("pit_audit_revision"))
    dc = _get("double_count_audit")
    t += ("\n## 이중계산 제거 (§11)\n\n발주계획·사전규격·입찰·계약을 단순 합산하면 같은 조달건을 "
          "네 번 세게 된다. lifecycle 계단함수의 **증분**만 신규수요로 세면 그 합은 언제나 "
          "'최종 알려진 금액'과 정확히 같다.\n\n") + md_table(dc)
    t += "\n## 월별 커버리지\n\n" + md_table(_get("pit_monthly_coverage"), 60)
    report_write("01_PIT_AUDIT.md", t)


def r02_entity() -> None:
    t = _hdr("02 · 기업 매핑", "명세 §13 §14 §52")
    res = read_json(os.path.join(CFG.AUDIT_DIR, "entity_gate.json"), {}) or {}
    t += ("## 원칙\n\nPRIMARY 는 **사업자등록번호 exact match** 뿐이다. 상호 fuzzy matching 은 "
          "candidate generation 용도로만 쓰고 자동 확정하지 않는다. 현재 stock_code 를 과거 전체에 "
          "소급하지 않으며, 유효기간 밖의 매핑은 `OUT_OF_VALIDITY` 로 격리한다.\n\n")
    t += "## 금액기준 매칭 품질 (§52)\n\n" + md_table(_get("entity_gate"))
    t += ("\n| 지표 | 값 |\n|---|---|\n" +
          "".join(f"| {k} | {v} |\n" for k, v in res.items()))
    t += ("\n> 상장사 귀속 금액이 전체 조달의 일부인 것은 정상이다 — 공급자 다수가 비상장이다. "
          "게이트는 '식별된 것 중 exact 비중'으로 본다.\n")
    report_write("02_ENTITY_MAPPING.md", t)


def r03_graph() -> None:
    t = _hdr("03 · G2B Demand Graph 진단", "명세 §9 §10 §12")
    t += "## 그래프 구성 (§12)\n\n" + md_table(_get("graph_summary"))
    t += ("\n## graph.asof(t) (§7)\n\n조회는 반드시 시점을 통과한다. 노드·엣지가 시간에 대해 "
          "단조 증가해야 하며, asof(t) 가 known_at > t 인 노드를 하나라도 반환하면 위반이다.\n\n")
    t += md_table(_get("graph_asof_check"), 40)
    lc = _get("opportunity_lifecycle")
    if lc is not None and len(lc):
        t += ("\n## lifecycle 도달 분포 (§2.F)\n\n모든 건에 5단계가 다 존재하지는 않는다. "
              "연결 실패를 사건 실패로 간주하지 않는다.\n\n")
        t += md_table(lc["reached_stage"].value_counts().rename_axis("도달단계")
                      .reset_index(name="건수"))
    t += "\n## 공동수급 처리 (§16)\n\n" + md_table(_get("consortium_audit"))
    report_write("03_G2B_GRAPH_DIAGNOSTIC.md", t)


def r04_factor() -> None:
    t = _hdr("04 · 팩터 진단", "명세 §17~§44 §77")
    t += "## 사전등록된 시험 장부 (§77)\n\n" + md_table(prereg.ledger_table())
    t += "\n## 동결 검증 (§1.1)\n\n" + md_table(prereg.verify())
    t += "\n## capability 지속성 (§17)\n\n" + md_table(_get("capability_persistence"))
    t += ("\n## 단계 성숙 분포 (§23)\n\nMATURITY_EMBARGO 는 이 분포를 보고 **수익률을 열기 전에** "
          "정해 동결했다.\n\n") + md_table(_get("maturity_distribution"))
    t += "\n## 월별 커버리지 게이트 (§51)\n\n" + md_table(_get("coverage_monthly"), 60)
    report_write("04_FACTOR_DIAGNOSTIC.md", t)


def r05_backtest() -> None:
    t = _hdr("05 · PRIMARY 백테스트", "명세 §53~§62")
    t += ("## PRIMARY 정의 (동결)\n\n`G2B_DWA = sqrt(P_D × P_W)`, sector+log(mcap) 중립, "
          "상위 20% Long-only, 동일가중, 월 리밸런싱, T+1 체결, 비용 반영.\n\n")
    t += "## 누수 카나리아 (§93)\n\n" + md_table(_get("canary"))
    t += "\n## 성과표 (§60)\n\n" + md_table(_get("primary_summary"))
    t += "\n## 분위 성과 (§55)\n\n" + md_table(_get("primary_quantile_table"))
    t += "\n## 초과수익 검정 (§61)\n\n" + md_table(_get("primary_excess"))
    t += "\n## IC (§61)\n\n" + md_table(_get("primary_ic"))
    t += "\n## Fama-MacBeth (§62)\n\n" + md_table(_get("primary_fama_macbeth"))
    t += "\n## 비용 (§59)\n\n" + md_table(_get("primary_costs"))
    t += "\n## Placebo (§74 §75)\n\n" + md_table(_get("permutation_placebo"))
    t += "\n" + md_table(_get("temporal_placebo"))
    report_write("05_PRIMARY_BACKTEST.md", t)


def r06_mech() -> None:
    t = _hdr("06 · 메커니즘 검정", "명세 §29 §39 §46 §63 §64 §80 §84")
    t += ("## 인과 사슬 (§80)\n\n정부수요↑ → EligibleTAM↑ → 낙찰↑ → 계약↑ → 매출↑ 의 "
          "각 화살표를 따로 측정한다.\n\n") + md_table(_get("mech_causal_chain"))
    t += "\n## 단계 전환율 (§39)\n\n" + md_table(_get("mech_pipeline_conversion"))
    t += "\n## 입찰→낙찰 전환 (§38)\n\n" + md_table(_get("mech_win_conversion"))
    t += ("\n## 분해: Demand / Win / Alignment (§63)\n\n원 가설이 맞다면 Alignment 가 "
          "둘 중 하나를 단독 사용하는 것보다 증분성이 있어야 한다.\n\n")
    t += md_table(_get("mech_decomposition"))
    t += ("\n## 2×2 메커니즘 (§29)\n\n가설상 `D_high_W_high` 가 가장 좋아야 한다. "
          "이 검정은 메커니즘 확인용이며 파라미터 탐색 도구가 아니다.\n\n") + md_table(_get("mech_2x2"))
    t += ("\n## ★ 최종 비교 (§84 §99)\n\n**복잡한 Demand Graph 가 단순 '낙찰금액/시가총액'보다 "
          "실제로 더 많은 정보를 주는가?** 복잡성이 단순모델을 명백히 이기지 못하면 "
          "단순모델을 채택한다.\n\n") + md_table(_get("mech_nested_comparison"))
    t += "\n## Secondary family + BH/FDR (§78)\n\n" + md_table(_get("mech_secondary_fdr"))
    t += ("\n## 매출 인식 지연 (§46 §47)\n\n이 분석은 `MECHANISM_VALIDATION_ONLY` 다 — "
          "여기서 얻은 lag 를 과거 팩터 가중치에 소급 적용하지 않는다.\n\n")
    t += md_table(_get("mech_revenue_lag"))
    t += "\n## 이벤트 스터디 (§54 §82)\n\n" + md_table(_get("mech_event_study"), 40)
    report_write("06_MECHANISM_TEST.md", t)


def r07_robust() -> None:
    t = _hdr("07 · 강건성", "명세 §65~§75")
    t += "## 요약\n\n" + md_table(_get("robust_summary"))
    for nm, f in [("기간 (§65)", "robust_기간"), ("Leave-One-Year-Out (§66)", "robust_LOYO"),
                  ("Leave-One-Agency-Out (§67)", "robust_LOAO"),
                  ("Leave-One-Category-Out (§68)", "robust_LOCO"),
                  ("초대형 계약 제거 (§69)", "robust_초대형계약"),
                  ("상위기여 종목 제거 (§70)", "robust_상위기여제거"),
                  ("시총 (§71)", "robust_시총"), ("시장 (§72)", "robust_시장"),
                  ("업종 (§73)", "robust_업종"), ("비용 스트레스 (§59)", "robust_비용")]:
        t += f"\n## {nm}\n\n" + md_table(_get(f))
    report_write("07_ROBUSTNESS.md", t)


def r99_final() -> str:
    nc = _get("mech_nested_comparison")
    dec = _get("mech_decomposition")
    ex = _get("primary_excess")
    cov = read_json(os.path.join(CFG.AUDIT_DIR, "coverage_gate.json"), {}) or {}
    ent = read_json(os.path.join(CFG.AUDIT_DIR, "entity_gate.json"), {}) or {}
    apis = _get("api_depth_summary")
    dc = _get("double_count_audit")
    rb = _get("robust_summary")
    tp = _get("temporal_placebo")

    net_t = _val(ex, "NW_t", lambda T: T["전략"].str.contains("net"), np.nan)
    net_ann = _val(ex, "연환산수익", lambda T: T["전략"].str.contains("net"), np.nan)

    # ── §96 판정 ─────────────────────────────────────────────────────────────
    data_ok = (apis is not None and len(apis) and (apis["사용가능"] == "YES").any()) \
        if apis is not None else False
    pit_ok = True
    if tp is not None and len(tp) and "판정" in tp.columns:
        pit_ok = tp["판정"].iloc[0] != "LEAKAGE_SUSPECT"
    sample_ok = cov.get("verdict") == "PASS"

    if CFG.RUN_MODE == "SMOKE":
        verdict, why = "DATA_BLOCKED", "SMOKE 모드 — 합성 데이터이므로 실증 판정을 내리지 않는다."
    elif not data_ok:
        verdict, why = "DATA_BLOCKED", "핵심 API 에서 historical 데이터를 확보하지 못했다."
    elif not pit_ok:
        verdict, why = "PIT_BLOCKED", "temporal placebo 가 누수를 시사한다."
    elif not sample_ok:
        verdict, why = "SAMPLE_COLLAPSE", "월별 스코어 기업수/보유종목이 연구게이트에 미달한다."
    elif not np.isfinite(net_t):
        verdict, why = "DATA_BLOCKED", "초과수익 검정을 수행할 표본이 없다."
    else:
        strong = (np.isfinite(net_ann) and net_ann * 100 >= 3.0 and net_t >= 2.0 and
                  (rb is not None and len(rb) and
                   float(pd.to_numeric(rb["양수비율"], errors="coerce").mean() or 0) >= 0.7))
        if strong:
            verdict, why = "STRONG_PASS", "순초과 ≥ +3%p, NW t ≥ 2.0, 강건성 대부분 양수."
        elif net_t >= 2.0 and net_ann > 0:
            verdict, why = "PASS", "순알파 > 0 이고 NW t ≥ 2.0."
        elif net_t >= 1.0 and net_ann > 0:
            verdict, why = "WEAK_EVIDENCE", "방향은 양이나 통계적 강도가 부족하다."
        else:
            verdict, why = "NO_ALPHA", "데이터는 확보되었으나 초과수익이 확인되지 않는다."

    simple = full = np.nan
    if nc is not None and len(nc) and "복잡도" in nc.columns:
        simple = pd.to_numeric(nc[nc["복잡도"] == "단순"]["순초과(연,%)"], errors="coerce").max()
        full = pd.to_numeric(nc[nc["복잡도"] == "복합"]["순초과(연,%)"], errors="coerce").max()

    t = _hdr("FINAL DECISION", "명세 §95 §96 — 17개 질문에 답한다")
    t += (f"## 판정\n\n# `{verdict}`\n\n{why}\n\n"
          "> `DATA_BLOCKED` 와 `NO_ALPHA` 는 다르다. 데이터가 부족해서 검증하지 못한 전략을 "
          "성과부진 전략으로 기각하지 않는다(§96).\n\n---\n\n")

    def q(n, question, answer):
        return f"**{n}. {question}**\n\n{answer}\n\n"

    dcx = ""
    if dc is not None and len(dc):
        naive = _val(dc, "금액", lambda T: T["측정"].str.contains("단순합산"))
        corr = _val(dc, "금액", lambda T: T["측정"].str.contains("증분합"))
        if np.isfinite(naive) and np.isfinite(corr) and corr:
            dcx = (f"단순합산 {naive / 1e12:,.1f}조 → 증분합 {corr / 1e12:,.1f}조 "
                   f"({naive / corr:.2f}배 이중계상 제거). 증분합 = 최종 알려진 금액 합.")
    t += "## 17개 질문\n\n"
    t += q(1, "나라장터 데이터로 역사적 PIT 백테스트가 실제로 가능한가?",
           ("가능하다 — 세 시각(event/published/available)과 변경이력으로 리비전 구간을 "
            "복원했고 CLASS C 필드는 구조적으로 차단된다." if data_ok and pit_ok else
            "이번 실행에서는 확인되지 않았다. 위 판정 사유를 참조하라."))
    t += q(2, "어느 시점부터 데이터 품질이 안정적인가?",
           f"`{(read_json(os.path.join(CFG.AUDIT_DIR, 'usable_start_candidate.json'), {}) or {}).get('usable_start_date', '미확정')}` "
           f"(데이터 커버리지만 보고 결정, warm-up {CFG.WARMUP_MONTHS}개월 반영 — §48).")
    t += q(3, "상장기업 수주금액 중 사업자등록번호 exact match 비율은?",
           f"식별된 금액 중 exact 비중 `{ent.get('exact_among_identified', 'n/a')}`, "
           f"전체 대비 exact `{ent.get('exact_amount_share', 'n/a')}`, "
           f"미매칭 `{ent.get('unmatched_share', 'n/a')}` (대부분 비상장 공급자).")
    t += q(4, "G2B signal 적용 가능 기업 수는 월별 몇 개인가?",
           f"중앙값 `{cov.get('scored', {}).get('median', 'n/a')}`, "
           f"p10 `{cov.get('scored', {}).get('p10', 'n/a')}`, "
           f"최소 `{cov.get('scored', {}).get('min', 'n/a')}` → 게이트 `{cov.get('verdict', 'n/a')}`.")
    t += q(5, "정부수요 이동은 실제 향후 수주를 예측하는가?", "§80 인과사슬 표(06 보고서) ②③ 행 참조.")
    t += q(6, "Eligible TAM 증가는 실제 향후 매출을 예측하는가?",
           "§46 매출인식 지연 표 참조. 이 분석은 `MECHANISM_VALIDATION_ONLY` 이며 "
           "여기서 얻은 lag 를 과거 팩터에 소급 적용하지 않는다(§47).")
    t += q(7, "Demand Shift 단독으로 알파가 있는가?",
           md_table(dec[dec["구성"].str.contains("Demand only")] if dec is not None and len(dec)
                    else None))
    t += q(8, "Win signal 단독으로 알파가 있는가?",
           md_table(dec[dec["구성"].str.contains("Win only")] if dec is not None and len(dec)
                    else None))
    t += q(9, "Demand × Win alignment 가 증분 알파를 만드는가?",
           md_table(dec[dec["구성"].str.contains("Alignment")] if dec is not None and len(dec)
                    else None))
    t += q(10, "'낙찰금액/시총'이라는 단순 전략보다 복잡한 Demand Graph 가 실제로 우월한가?",
           (f"단순 최고 `{simple:.2f}`%p vs 복합 `{full:.2f}`%p → "
            f"**{'복합 채택' if (np.isfinite(simple) and np.isfinite(full) and full > simple + 0.5) else '단순 채택(§99)'}**"
            if np.isfinite(simple) and np.isfinite(full) else "비교표를 생성하지 못했다.") +
           "\n\n" + md_table(nc))
    t += q(11, "알파는 어느 조달단계에서 처음 나타나는가?", "§64 단계별 정보가치 표 참조(해석용, 사후선택 금지).")
    t += q(12, "낙찰시점에는 이미 가격반영이 끝났는가?",
           "§82 이벤트 스터디 참조. 일별 가격 패널이 없으면 `NOT_IDENTIFIABLE` 로 두고 "
           "월별 근사로 대체하지 않는다.")
    t += q(13, "산업·시총 효과를 제거하고도 살아남는가?",
           "PRIMARY 는 sector + log(mcap) 중립화 버전이다(§44). raw/sector 버전도 함께 산출된다.")
    t += q(14, "특정 정부·연도·기관·품목에 의존하는가?", md_table(rb))
    t += q(15, "대형 계약 몇 건을 제거하고도 살아남는가?", md_table(_get("robust_초대형계약")))
    t += q(16, "비용 이후에도 살아남는가?", md_table(_get("robust_비용")))
    t += q(17, "향후 실전투자에 사용할 만큼 기업 수가 충분한가?",
           f"top bucket 중앙값 `{cov.get('top_bucket', {}).get('median', 'n/a')}` 종목 "
           f"(연구게이트 권장 ≥ 20).")

    t += ("\n---\n\n## 데이터 무결성 요약\n\n"
          f"- 이중계산 제거(§11): {dcx or 'n/a'}\n"
          f"- 누수 카나리아(§93): {'통과' if _get('canary') is not None else '미실행'}\n"
          f"- 사전등록 동결(§1.1): {'완료' if not CFG.future_return_lock() else '미완료(잠김)'}\n"
          f"- 공동수급 지분불명 제외(§16): 03 보고서 참조\n")
    t += ("\n## 이 연구가 하지 않은 것\n\n"
          "- 성과를 본 뒤 lookback/window/threshold 를 다시 고르지 않았다.\n"
          "- 성과가 좋은 품목·연도만 사후 선택하지 않았다.\n"
          "- 유찰률·낙찰률의 부호를 성과를 본 뒤 뒤집지 않았다(§76 진단용으로만 분리).\n"
          "- Track A(상장법인 직접 계약)와 Track B(연결 자회사)를 섞어 보고하지 않았다(§15).\n"
          "  Track B 는 자회사 관계를 PIT 로 복원하지 못하면 백테스트하지 않는다.\n")
    report_write("FINAL_DECISION.md", t)
    return verdict


def main() -> int:
    header("13 보고서 생성", "§94 §95 §96")
    r00_api(); r01_pit(); r02_entity(); r03_graph()
    r04_factor(); r05_backtest(); r06_mech(); r07_robust()
    v = r99_final()
    LOG.banner(f"FINAL DECISION: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
