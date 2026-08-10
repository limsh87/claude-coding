

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  Phase 0 게이트 · 수급축 판정(§9) · 사전등록 폐기조건(§10.4) · 최종 산출물(§10.3)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PHASE0: Dict[str, Any] = {}
# Phase 0 판정을 하류가 실제로 읽는다. 표에 "미달 시 행동"을 적어 놓고 아무것도 하지 않으면
# 그 표는 거짓말이 된다(적대적 감사가 지적한 그대로).
PHASE0_FLOW_OK: Optional[bool] = None


def report_phase0(fin_cov: float, flow_cov: float, dart_parse: float,
                  report_cov_200: float, pair_count_200: float) -> dict:
    """§2.1 데이터 실현가능성 게이트. 실패해도 해당 컴포넌트만 끄고 전략은 계속한다(§2.2)."""
    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§2)",
               "게이트 실패 시 해당 컴포넌트만 비활성화한다. fin_cov 실패만 전략 중단 사유다.")
    spec = [
        ("fin_cov", fin_cov, 0.90, "U-1000 재무데이터 가용률", "게이트", "전략 중단"),
        # ★ '미달 시 행동' 칸은 코드가 실제로 하는 일과 정확히 일치해야 한다. 하지도 않을
        #   조치를 적어두면 그 표 자체가 거짓 보증이 된다(적대적 감사가 잡아낸 유형).
        ("flow_cov", flow_cov, 0.95, "외국인·기관 순매수 가용률", "게이트",
         "VQF 는 참고 산출, §9 C1·C2 판정 불가"),
        ("dart_parse_rate", dart_parse, 0.80, "DART 본문 기계판독 성공률", "게이트",
         "사유 분해 보고 후 진행(§2.2)"),
        ("report_cov_200", report_cov_200, None, "U-200 내 리포트 ≥1건 비율", "측정만", "—"),
        ("pair_count_200", pair_count_200, None, "U-200 내 연속 2분기 리포트 종목수", "측정만", "—"),
    ]
    rows, verdict = [], {}
    for key, val, thr, desc, kind, action in spec:
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            shown, ok = "—", None
        else:
            shown = f"{val:,.0f}" if key == "pair_count_200" else f"{100*val:.1f}%"
            ok = None if thr is None else bool(val >= thr)
        verdict[key] = {"value": val, "pass": ok}
        rows.append([key, desc, shown,
                     ("—" if thr is None else f"≥ {100*thr:.0f}%"),
                     kind,
                     ("—" if ok is None else ("✔ 통과" if ok else "✘ 미달")),
                     action if ok is False else ""])
    LOG.table(rows, ["항목", "정의", "실측", "기준", "성격", "판정", "미달 시 행동"],
              ["l", "l", "r", "r", "c", "c", "l"], maxw=34)
    LOG.info("§2.2 — report_cov_200 이 낮게 나오는 것은 예상된 결과이며 실패가 아닙니다. "
             "애널리스트 축은 결측 허용 설계(§6.2)이므로 그대로 진행하되 실측치를 보고합니다.")
    PHASE0.update(verdict)
    globals()["PHASE0_FLOW_OK"] = verdict.get("flow_cov", {}).get("pass")
    if verdict.get("flow_cov", {}).get("pass") is False:
        LOG.warn("flow_cov 게이트 미달 — 수급(F) 축의 표본이 부분적입니다. VARIANT-VQF 는 "
                 "참고용으로 끝까지 산출하되, §9 의 C1·C2 는 '판정 불가'로 처리합니다. "
                 "부분 표본으로 계산한 Sharpe 차이를 채택 근거로 쓰지 않기 위함입니다(§10.1).")
    return verdict


def report_flow_verdict(cmp_res: dict, exp_vq: str = "VQ-full", exp_vqf: str = "VQF-full",
                        fdr_pass: Optional[dict] = None) -> dict:
    """§9 — VARIANT-VQF 채택 여부 C1~C5. 자동 채택하지 않고 판정 결과만 보고한다."""
    LOG.banner("수급 축 판정 (§9)",
               "C1~C5 를 모두 충족해야 채택. 하나라도 미충족이면 수급 축 기각 → VQ 채택 권고")
    e_vq = EXPERIMENTS.get(exp_vq, {})
    e_vqf = EXPERIMENTS.get(exp_vqf, {})
    s_vq = (e_vq.get("net") or {}).get("Sharpe", np.nan)
    s_vqf = (e_vqf.get("net") or {}).get("Sharpe", np.nan)

    # C1: 비용 차감 후 Sharpe 우위
    #  ★ flow_cov 게이트가 미달이면 F축 표본 자체가 부분적이라 이 비교가 성립하지 않는다.
    #    숫자는 보여주되 판정은 내리지 않는다 — 근거 없는 채택/기각 둘 다 §10.1 위반이다.
    _flow_ok = globals().get("PHASE0_FLOW_OK")
    if _flow_ok is False:
        c1, c1_d = None, (f"VQF {s_vqf:.3f} vs VQ {s_vq:.3f} — 단, flow_cov 게이트 미달로 "
                          f"판정 불가" if np.isfinite(s_vqf) and np.isfinite(s_vq)
                          else "flow_cov 게이트 미달 — 판정 불가")
    else:
        c1 = bool(np.isfinite(s_vq) and np.isfinite(s_vqf) and s_vqf > s_vq)
        c1_d = (f"VQF {s_vqf:.3f} vs VQ {s_vq:.3f}"
                if np.isfinite(s_vq) and np.isfinite(s_vqf) else "산출 불가")

    # C2: 그 '차이'가 BH-FDR 보정 후에도 유의 — VQF 자신의 유의성이 아니다.
    _dkey = f"{exp_vqf}−{exp_vq}(차이)"
    if _flow_ok is False:
        c2, c2_d = None, "flow_cov 게이트 미달 — 판정 불가"
    elif fdr_pass is None:
        c2, c2_d = None, "BH-FDR 결과 없음"
    elif _dkey not in fdr_pass:
        c2, c2_d = None, f"차이검정({_dkey})이 패밀리에 없음 — 판정 불가"
    else:
        _dt_rec = EXPERIMENTS.get(_dkey, {})
        c2 = bool(fdr_pass.get(_dkey, False)) and bool(c1)
        c2_d = (f"차이 HAC t {_dt_rec.get('t', float('nan')):+.2f} · "
                f"BH-FDR {'통과' if fdr_pass.get(_dkey) else '기각'}"
                + ("" if c1 else " · C1 미충족이라 차이 자체가 없음"))

    # C3: U-200 중복률 < 0.85
    ov = (cmp_res or {}).get("overlap", {})
    key = next((k for k in ov if set(k.split("~")) == {"VQ", "VQF"}), None)
    o = ov.get(key, np.nan) if key else np.nan
    c3 = bool(np.isfinite(o) and o < 0.85)
    c3_d = f"VQ∩VQF 중복률 {o:.3f}" if np.isfinite(o) else "산출 불가"

    # C4: 수급 비영 관측 비율 ≥ 30% — 반드시 '사전등록 창(60일)' 의 값이어야 한다.
    #     axis_F 는 §8.4 민감도(20/60/120일)에서도 재호출되며 전역을 덮어쓴다. 그대로 읽으면
    #     C4 가 마지막 실행(120일)의 값을 보게 되고, 창이 길수록 비영 비율이 높아지므로
    #     사전등록 기준보다 통과하기 쉬워진다(상향 드리프트).
    nz = globals().get("FLOW_NONZERO_RATIO_PREREG", float("nan"))
    _nz_src = f"사전등록 {int(FLOW_WINDOW_DAYS)}일 창"
    if not np.isfinite(nz):
        nz = globals().get("FLOW_NONZERO_RATIO", float("nan"))
        _nz_src = "창 미상(폴백)"
    c4 = bool(np.isfinite(nz) and nz >= 0.30)
    c4_d = f"비영 관측 {100*nz:.1f}% ({_nz_src})" if np.isfinite(nz) else "산출 불가"

    # C5: 리포트 커버리지가 VQ 대비 크게 높지 않음
    cov = (cmp_res or {}).get("coverage", {})
    cvq, cvqf = cov.get("VQ", np.nan), cov.get("VQF", np.nan)
    if np.isfinite(cvq) and np.isfinite(cvqf):
        gap = cvqf - cvq
        c5 = bool(gap <= 0.10)
        c5_d = f"커버리지 VQF {100*cvqf:.1f}% − VQ {100*cvq:.1f}% = {100*gap:+.1f}%p (기준 ≤ +10%p)"
    else:
        c5, c5_d = None, "리포트 커버리지 산출 불가 → 판정 불가"

    items = [
        ("C1", "비용 차감 후 VQF Sharpe > VQ Sharpe", c1, c1_d),
        ("C2", "그 차이가 BH-FDR 보정 후에도 유의", c2, c2_d),
        ("C3", "VQF 의 U-200 이 VQ 와 충분히 다름 (중복률 < 0.85)", c3, c3_d),
        ("C4", "수급 축 비영 관측 비율 ≥ 30% (U-1000)", c4, c4_d),
        ("C5", "VQF 리포트 커버리지가 VQ 대비 크게 높지 않음", c5, c5_d),
    ]
    LOG.table([[k, d, ("판정불가" if ok is None else ("✔ 충족" if ok else "✘ 미충족")), det]
               for k, d, ok, det in items],
              ["조건", "내용", "판정", "근거 수치"], ["c", "l", "c", "l"], maxw=52)

    # ★ '판정 불가(None)'를 충족으로 세지 않는다. 모르는 것을 근거로 채택하면 안 된다.
    all_ok = all(ok is True for _k, _d, ok, _t in items)
    unknown = [k for k, _d, ok, _t in items if ok is None]
    if all_ok:
        LOG.ok("§9 — C1~C5 를 모두 충족했습니다. 수급 축 채택을 '권고'합니다. "
               "다만 자동 채택하지 않습니다 — 최종 결정은 사용자의 몫입니다.")
    else:
        fail = [k for k, _d, ok, _t in items if ok is False]
        LOG.warn(f"§9 — 미충족 조건 {fail or '없음'}"
                 + (f" · 판정불가 {unknown}" if unknown else "") +
                 ". 규정대로 수급 축을 기각하고 VARIANT-VQ 채택을 권고합니다.")
    return {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5,
            "adopt_flow": all_ok, "details": {k: t for k, _d, _o, t in items}}


def report_preregistration_kill(main_names: Sequence[str], best: str,
                                x1_name: str) -> dict:
    """§10.4 사전등록 폐기 조건. 충족 시 파라미터 튜닝으로 되살리지 않고 보고 후 중단한다."""
    LOG.banner("사전등록 폐기 조건 점검 (§10.4)",
               "충족 시 파라미터 튜닝으로 되살리려 시도하지 않는다 — 폐기 보고 후 중단")
    out = {}

    # ① 세 변형 모두 거래비용 차감 후 알파 소멸
    cagrs = {n: (EXPERIMENTS.get(n, {}).get("net") or {}).get("CAGR", np.nan)
             for n in main_names}
    alive = [n for n, v in cagrs.items() if np.isfinite(v) and v > 0]
    k1 = len(alive) == 0
    out["all_alpha_dead"] = k1

    # ② X1(1차만)과 최우수 full 의 차이가 미미 → 깔때기 구조 무가치
    #   ★ 명세는 "미미"라고만 하고 수치를 주지 않는다. 예전 코드의 0.05 는 순수 임의값이었고,
    #     40분기 표본에서 두 Sharpe 차이의 표준오차(≈0.50)의 0.1배에 불과하다 — 참 기여가
    #     0 이어도 절반의 확률로 통과하는, 사실상 판별력 없는 기준이다.
    #     그래서 '차이의 신뢰구간이 0 을 포함하면 미미'라는 통계적 정의로 대체한다.
    #     비교 가능한 검정을 못 만들면 0.05 를 폴백으로 쓰되 그 사실을 근거란에 적는다.
    s_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("Sharpe", np.nan)
    s_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("Sharpe", np.nan)
    _dt2 = paired_diff_test(best, x1_name, label=f"{best}−{x1_name}(깔때기기여)")
    if np.isfinite(_dt2.get("t", np.nan)):
        # 단측(우측) t 가 임계 미만 = 차이가 0 과 구분되지 않음 = 깔때기 기여 미미
        k2 = bool(_dt2["p"] >= 0.10)
        k2_basis = (f"분기수익률 차이 HAC t {_dt2['t']:+.2f} · p {_dt2['p']:.3f} "
                    f"(n={_dt2['n']}) — p ≥ 0.10 이면 '미미'")
    else:
        k2 = bool(np.isfinite(s_full) and np.isfinite(s_x1) and (s_full - s_x1) < 0.05)
        k2_basis = "차이검정 불가 → Sharpe 차 < 0.05 폴백(임의 임계값임을 명시)"
    out["funnel_worthless"] = k2

    # ③ 배제플래그가 MDD 개선에 기여하지 못함 → 2층 논리 반증
    m_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("MDD", np.nan)
    m_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("MDD", np.nan)
    k3 = bool(np.isfinite(m_full) and np.isfinite(m_x1) and (m_full <= m_x1 + 1e-9))
    out["exclusion_no_mdd_help"] = k3

    LOG.table([
        ["① 세 변형 모두 비용 차감 후 알파 소멸",
         ", ".join(f"{n} {100*cagrs[n]:+.1f}%" for n in main_names if np.isfinite(cagrs.get(n, np.nan))) or "산출 불가",
         "❗ 충족(폐기)" if k1 else "✔ 미충족"],
        ["② X1(1차만) 과 최우수 full 의 차이가 미미", k2_basis,
         "❗ 충족(폐기)" if k2 else "✔ 미충족"],
        ["③ 배제 컴포넌트가 MDD 개선에 기여 못함",
         f"MDD {100*m_full:+.1f}% vs X1 {100*m_x1:+.1f}%" if np.isfinite(m_full) and np.isfinite(m_x1) else "산출 불가",
         "❗ 충족(폐기)" if k3 else "✔ 미충족"],
    ], ["폐기 조건", "근거 수치", "판정"], ["l", "l", "c"], maxw=48)

    if any(out.values()):
        LOG.warn("§10.4 폐기 조건이 충족되었습니다. 이 결과를 파라미터 조정으로 되살리려 하지 "
                 "마십시오. 위 수치를 그대로 보고하고 중단하는 것이 사전등록의 이행입니다.")
        # ★ '미달 시 행동'을 표에 적어 놓고 아무것도 하지 않으면 그 표는 거짓말이 된다.
        #   예전에는 폐기 판정을 낸 직후 그 폐기된 전략의 실전 편입 종목표를 그대로 출력했다.
        out["_halted"] = bool(STOP_ON_KILL_CRITERIA)
        if STOP_ON_KILL_CRITERIA:
            _hit = [k for k, v in out.items() if v is True and not k.startswith("_")]
            raise KillCriteria(
                "§10.4 사전등록 폐기 조건 충족: " + ", ".join(_hit) + "\n"
                "  사전등록의 이행은 '여기서 멈추는 것' 입니다. 최종 편입 종목표는 출력하지 "
                "않습니다.\n"
                "  수치만 확인하고 계속 보고 싶다면 STOP_ON_KILL_CRITERIA = False 로 두십시오 "
                "— 단, 그 실행 결과를 '전략이 통과했다'고 읽으면 안 됩니다.")
    else:
        LOG.ok("§10.4 폐기 조건에 해당하지 않습니다.")
    LOG.info("§10.2 성격 구분 — 1차필터(가치·퀄리티)의 기여는 알파 창출로, 2차 배제플래그와 "
             "3-A 의 기여는 좌측꼬리 제거(MDD·Sortino)로 해석합니다. 배제 컴포넌트가 CAGR 을 "
             "크게 올렸다면 그것이 우연인지 별도로 검증해야 합니다.")
    return out


def report_final_holdings(P: pd.DataFrame, variant: str, sel_col: str,
                          sec: pd.DataFrame, top_n: int = 60) -> pd.DataFrame:
    """§10.3-9 — 3-A 규칙판 최종 편입 종목 리스트 (3-B 재량 검토용)."""
    if sel_col not in P.columns:
        return pd.DataFrame()
    last = P["rebal"].max()
    sub = P[(P["rebal"] == last) & P[sel_col].fillna(False).astype(bool)].copy()
    if sub.empty:
        LOG.warn("최종 시점 편입 종목이 없습니다.")
        return sub
    names = sec.set_index("code")["name"].astype(str).to_dict() if len(sec) else {}
    sub["name"] = sub["code"].map(names).fillna("")
    cols = ["code", "name", "sector", "mktcap", "adtv", f"score1_{variant}",
            f"score2_{variant}", "dNONFIN", "dTONE_resid", "n_reports"]
    cols = [c for c in cols if c in sub.columns]
    sub = sub.sort_values(f"score2_{variant}" if f"score2_{variant}" in sub.columns
                          else f"score1_{variant}", ascending=False)
    LOG.table([[r.get("code"), _trunc(r.get("name", ""), 16), _trunc(str(r.get("sector", "")), 12),
                f"{r.get('mktcap', float('nan'))/1e8:,.0f}억",
                f"{r.get('adtv', float('nan'))/1e8:,.2f}억",
                f"{r.get(f'score1_{variant}', float('nan')):+.2f}",
                f"{r.get(f'score2_{variant}', float('nan')):+.2f}",
                f"{r.get('dNONFIN', float('nan')):.0f}" if np.isfinite(r.get("dNONFIN", np.nan)) else "—",
                f"{r.get('dTONE_resid', float('nan')):+.3f}" if np.isfinite(r.get("dTONE_resid", np.nan)) else "0(중립)",
                f"{int(r.get('n_reports', 0) or 0)}"]
               for _i, r in sub.head(top_n).iterrows()],
              ["코드", "종목명", "섹터", "시총", "ADTV", "Score1", "Score2", "ΔNONFIN", "ΔTONE_r", "리포트"],
              ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r"],
              title=f"[{variant}] {pd.Timestamp(last):%Y-%m} 3-A 규칙판 최종 편입 종목 "
                    f"(§7.3 3-B 재량 검토용 — 백테스트에는 3-B 를 소급 적용하지 않았습니다)")
    return sub[cols + ["name"]] if cols else sub


def report_discretion_ledger():
    """★ 명세가 침묵하는 곳에서 코드가 택한 것을 전부 드러낸다.

    §10.1 은 '근거를 찾지 못했으면 근거 없음이라고 명시' 하라고 요구한다. 산식이 정해지지
    않은 지점에서 구현이 한쪽을 택했다면 그것은 '데이터가 말한 것'이 아니라 '우리가 정한 것'
    이며, 어느 방향으로 성과를 미는지까지 밝혀야 읽는 사람이 할인해서 볼 수 있다.

    드리프트 방향:
      상향 = 성과를 실제보다 좋게 보이게 하는 방향 (위험을 덜 걸러냄 / 비용을 덜 매김)
      하향 = 성과를 실제보다 나쁘게 보이게 하는 방향 (보수적)
      중립 = 방향성이 없거나 상쇄
    """
    LOG.banner("임의 선택 원장 (§10.1) — 명세가 정하지 않은 지점에서 코드가 택한 것",
               "'데이터가 말한 것'과 '우리가 정한 것'을 구분한다. 드리프트 방향까지 밝힌다.")
    rows = [
        ["EV 정의 = 시총 + 총차입금 − 현금", "명세는 EV/EBIT 만 지정", "중립",
         "차입금 계정이 전부 결측이면 부채총계로 폴백 → EV 과대추정(=밸류 매력 과소평가)"],
        ["EV<0 을 클립하지 않음", "명세 침묵", "중립",
         "순현금>시총 기업이 연속 순서를 유지. 클립하면 최상위에 동점 덩어리가 생겼다"],
        ["분모 부적격의 강제 바닥 = 그 리밸일 횡단면 최소 z", "§5.2 '최하위 순위로 강제'", "중립",
         "셀 최소를 쓰면 폴백 사다리와 어긋나 벌점이 양수(=상점)가 되고 셀 크기에 따라 "
         "벌점이 2배 차이 났다. 선정이 횡단면 단위이므로 벌점도 횡단면 단위로 맞췄다. "
         "임의 상수(-3 등)는 쓰지 않는다"],
        ["분모 = 0 도 '부적격'(3상태 판정)", "§5.2 '음수 EBIT/분모'", "하향(보수적)",
         "safe_div 가 NaN 을 주는 탓에 분모가 정확히 0 인 기업(완전자본잠식 등)이 벌점을 "
         "빠져나가 Z_V 상위에 앉았다. '모름(재무 미보유)'과는 구분해 벌점을 주지 않는다"],
        ["ROIC 유효세율 결측 시 22% 가정", "명세 침묵", "중립",
         "ROIC 는 3년 표준편차로만 쓰이고 전 기업 동일 가정이라 횡단면 효과는 작다"],
        ["Score1 축 결측 시 가중치 재정규화", "§5.5 는 고정 가중치", "중립~보수",
         "0(셀 평균)으로 채우지 않는다. VQF 를 VQ 에 가깝게 만들어 §9 채택을 어렵게 함(보수적)"],
        ["배제플래그: 근거 결측이면 배제하지 않음", "§6.1 '해당 시 즉시 제외'", "⚠ 상향",
         "근거가 없는 종목이 안 걸러진다. 위 배제플래그 표의 '근거 관측 보유율'과 함께 볼 것"],
        ["3-A: 근거 결측이면 제외하지 않음", "§7.2 임계값만 지정", "⚠ 상향",
         "위와 동일. 반대로 하면 재무 결측이 많은 초소형주가 통째로 사라져 선택편향이 된다"],
        ["유동시총 ≈ (발행주식수 − 자기주식) × 주가", "§5.4 '유동주식 시가총액'", "중립",
         "대주주·우리사주 미차감 → 분모 과대 → F축 정규화 강도 약화(신호 희석)"],
        ["TONE 라벨 = 횡단면 중앙값 조정 2일 수익", "§6.2 '2일 CAR'", "중립",
         "시장모형 대신 당일 횡단면 조정. 같은 날 정보만 쓰므로 누수가 없다"],
        ["직교화에서 EPS 컨센서스 수정률 제외", "§6.2 는 포함 요구", "불명",
         "과거 시계열 복원 불가. 목표주가 수정률로 일부 대체 — 잔차에 컨센서스 성분이 남을 수 있음"],
        ["Sharpe = (CAGR − rf) / 연변동성", "명세는 Sharpe 만 지정", "하향(보수적)",
         "기하평균(CAGR)을 쓰므로 산술평균 기준 Sharpe 보다 낮게 나온다"],
        [f"기본 비용모형 = '{QVF_COST_MODEL}' (거래세 + 스프레드/2)", "§8.1 문언 그대로", "중립",
         f"수수료 {COMMISSION_BPS}bp 와 제곱근 충격 K={IMPACT_K} 는 명세에 없으므로 기본에서 "
         f"뺐다. 사전등록 판정(§9·§10.4)은 명세 문언 기준이어야 한다. 확장 모형은 §8.4 "
         f"민감도로 병기한다"],
        ["ADTV 조회 실패 시 그 분기 중앙 ADTV 로 대체", "명세 침묵", "혼합",
         "예전엔 조회 실패를 '참여율 100%'(=충격 1000bp)로 등치시켜 매도 레그 전체가 "
         "18배 과다 비용을 맞았다. 중앙값 대체는 과소·과대 어느 쪽으로도 치우치지 않는다"],
        [f"체결 허용 지연 {EXEC_FILL_MAX_LAG_DAYS}일 초과 시 매수 후보 탈락", "명세 침묵", "혼합",
         "길게 잡으면 정지 종목의 '재개장 −60% 가격'을 진입가로 쓰게 된다(상향). 짧게 잡으면 "
         "리밸일에 정지된 종목이 빠진다(상향). 후자는 현실 제약이고 전자는 공짜 복권이라 "
         "짧은 쪽을 골랐다. 체결 지연 분포는 감사표로 출력한다"],
        [f"스프레드 하한 {SLIPPAGE_FLOOR_BPS:.0f}bp / 상한 {SLIPPAGE_CAP_BPS:.0f}bp",
         "명세 침묵", "혼합",
         "하한은 비용↑(보수적), 상한은 최악 종목의 비용↓(상향). CS 추정치 폭주 방지용"],
        [f"가정 계좌 {ACCOUNT_KRW/1e8:.0f}억 (충격 참여율 계산)", "명세 침묵", "혼합",
         "계좌가 클수록 비용↑. 실제 운용규모와 다르면 비용 추정이 그만큼 어긋난다"],
        [f"U-200 크기 {U200_N} · 2차 {SECOND_N} · 최종 {FINAL_N}", "§5.5/6.3/7.4 범위 지정",
         "중립", "각각 명세 범위(200 / 60~80 / 20~40)의 값. 민감도는 §8.4 에서 별도 검정"],
        ["PIT 관리종목 이력 미적용", "§3.3 은 제외 요구", "⚠ 상향",
         "소급 조회 불가. 현재 명단을 과거에 적용하면 그게 미래누수라 적용하지 않았다. "
         "재무기준(자본잠식·연속적자·감사의견)으로 근사하지만 동일하지 않다. "
         "★ 그 근사는 3-A 안에 있으므로 어블레이션 X1~X3 에는 §3.3 3종 제외가 없다"],
        ["§10.4 ② '미미' = 차이의 단측 p ≥ 0.10", "명세는 '미미'라고만 함", "중립",
         "예전 임계 0.05(Sharpe 차)는 40분기 표본에서 차이 표준오차의 0.1배라 판별력이 "
         "사실상 없었다(참 기여가 0 이어도 절반만 발동). 통계적 정의로 바꿨다"],
        ["U-1000 = 게이트 통과 종목 안에서의 하위 1000", "§3.1 '하위 1000종목'", "⚠ 상향",
         "문언적 해석(전 종목 하위 1000 → 게이트)이면 종목수가 크게 줄고 시총 상한도 낮아진다. "
         "게이트를 먼저 통과시키면 1차필터 선택률이 낮아져 Score1 의 분산이 커진다. "
         "U1000_RANK_BEFORE_FILTER=True 로 대안 해석을 실행해 비교할 수 있다"],
    ]
    LOG.table(rows, ["임의 선택", "명세 조항", "드리프트", "영향 / 근거"],
              ["l", "l", "c", "l"], maxw=54)
    up = [r[0] for r in rows if "상향" in r[2]]
    LOG.warn(f"성과를 좋게 보이게 하는 방향의 선택 {len(up)}건: {', '.join(up)}. "
             f"앞의 셋은 모두 '근거가 없는 종목을 배제하지 않는다'는 같은 원칙에서 나온다 — "
             f"반대로 하면 재무·공시 결측이 많은 초소형주가 통째로 사라져 선택편향이 되므로 "
             f"교환관계이며, 어느 쪽도 공짜가 아니다. 마지막 U-1000 해석은 성격이 다르다: "
             f"명세 문언이 두 가지로 읽히는 지점이며, 대안 해석을 실행해 비교하는 것이 "
             f"유일한 정직한 처리다. 근거 보유율 표와 함께 해석하십시오.")
    LOG.info("§10.2 — 1차필터(가치·퀄리티)의 기여는 알파 창출로, 2차 배제플래그와 3-A 의 "
             "기여는 좌측꼬리 제거(MDD·Sortino)로 해석합니다. 배제 컴포넌트가 CAGR 을 크게 "
             "올렸다면 그것이 우연인지 별도 검증이 필요합니다.")


def report_dataflow_map():
    """거시적 흐름 한 장 — 어디서 어디로 데이터가 가는지."""
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ──────────────────────────────────────────────────────────────────────┐
  │ 환경감지 → 의존성 → 캐시루트 해석(드라이브 쓰기 1곳 + 로컬 미러 N곳 읽기전용)          │
  │            └ adopt_scan: 기존 리포트를 '이동 없이 참조 등록'                           │
  │ DartQuota: 공용 저널로 전략 간 사용량 합산 · 020 수신 지점을 그날의 실측 한도로 기록    │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │ 종목마스터  ← FDR GitHub캐시 / KIND / pykrx스냅샷 / DART corpCode / 네이버              │
  │ 가격        ← pykrx → FDR → 네이버차트 → yfinance (폴백 체인 + 소스 감사표)             │
  │ 시가총액    ← ①pykrx 전종목 스냅샷 ②DART 주식총수×종가 ③주식수 이월×종가                │
  │ 수급        ← pykrx 기간 순매수(시장 단위 집계) → 폴백: 일별 수급 롤링                  │
  │ DART        ← 재무제표 / 주식총수 / 공시목록(A·B·F·I) / 사업보고서 본문(규칙기반 추출)  │
  │ 리서치      ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장     │
  │               └ 애널리스트 원장 → (analyst_id, code, date, tp) → 목표주가 수정률        │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼ 모든 테이블 pit_frame() 통과 · knowledge_date = 접수일+1거래일
  ┌── L1/L2 피처 ─────────────────────────────────────────────────────────────────────────┐
  │ 분기 캘린더(신호=직전 거래일 / 체결=익 거래일 시가)                                     │
  │ 유니버스 격자 → PIT 재무 as-of 결합 → U-1000 선정(구조제외·유동성·자본잠식)             │
  │ 섹터 셀 → V축(부호처리) · Q축(주식수증가율 포함) · F축(유동시총 정규화)                 │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L2 필터 ────────────────────────────────────────────────────────────────────────────┐
  │ 1차: Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F  → U-200 ×3변형 → 중복률·특성 비교           │
  │ 2차: Score2 = 2·z(ΔNONFIN) + 1·z(ΔTONE_resid) − 배제(하드) → 60~80                     │
  │      ★ 리포트 없는 종목 = ΔTONE_resid 0(중립). 관측치 z 를 만든 '뒤에' 0 을 넣는다     │
  │ 3차: 3-A 규칙 체크리스트(소송·특수관계자·최대주주·감사·연속적자·자본잠식) → 20~40       │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L3 백테스트 → L5 강건성 → L6 리포트 ────────────────────────────────────────────────┐
  │ 익일시가 체결 · 폐지 −100%(정리매매 있으면 반영) · 거래세이력+CS스프레드+제곱근충격      │
  │ 주 실험 3 + 어블레이션 X1~X4 → BH-FDR(q=0.10) → 서브기간·시총사분위·민감도             │
  │ → 수급축 C1~C5 판정 → 사전등록 폐기조건 → 최종 편입 종목표                             │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")
