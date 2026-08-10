

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  Phase 0 게이트 · 수급축 판정(§9) · 사전등록 폐기조건(§10.4) · 최종 산출물(§10.3)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PHASE0: Dict[str, Any] = {}


def report_phase0(fin_cov: float, flow_cov: float, dart_parse: float,
                  report_cov_200: float, pair_count_200: float) -> dict:
    """§2.1 데이터 실현가능성 게이트. 실패해도 해당 컴포넌트만 끄고 전략은 계속한다(§2.2)."""
    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§2)",
               "게이트 실패 시 해당 컴포넌트만 비활성화한다. fin_cov 실패만 전략 중단 사유다.")
    spec = [
        ("fin_cov", fin_cov, 0.90, "U-1000 재무데이터 가용률", "게이트", "전략 중단"),
        ("flow_cov", flow_cov, 0.95, "외국인·기관 순매수 가용률", "게이트", "F축 비활성 → VQF=VQ"),
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
    c1 = bool(np.isfinite(s_vq) and np.isfinite(s_vqf) and s_vqf > s_vq)
    c1_d = (f"VQF {s_vqf:.3f} vs VQ {s_vq:.3f}"
            if np.isfinite(s_vq) and np.isfinite(s_vqf) else "산출 불가")

    # C2: 그 차이가 BH-FDR 보정 후에도 유의
    if fdr_pass is None:
        c2, c2_d = None, "BH-FDR 결과 없음"
    else:
        c2 = bool(fdr_pass.get(exp_vqf, False)) and c1
        c2_d = (f"VQF-full BH-FDR {'통과' if fdr_pass.get(exp_vqf) else '기각'}"
                + ("" if c1 else " · C1 미충족이라 차이 자체가 없음"))

    # C3: U-200 중복률 < 0.85
    ov = (cmp_res or {}).get("overlap", {})
    key = next((k for k in ov if set(k.split("~")) == {"VQ", "VQF"}), None)
    o = ov.get(key, np.nan) if key else np.nan
    c3 = bool(np.isfinite(o) and o < 0.85)
    c3_d = f"VQ∩VQF 중복률 {o:.3f}" if np.isfinite(o) else "산출 불가"

    # C4: 수급 비영 관측 비율 ≥ 30%
    nz = globals().get("FLOW_NONZERO_RATIO", float("nan"))
    c4 = bool(np.isfinite(nz) and nz >= 0.30)
    c4_d = f"비영 관측 {100*nz:.1f}%" if np.isfinite(nz) else "산출 불가"

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
    s_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("Sharpe", np.nan)
    s_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("Sharpe", np.nan)
    k2 = bool(np.isfinite(s_full) and np.isfinite(s_x1) and (s_full - s_x1) < 0.05)
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
        ["② X1(1차만) 과 최우수 full 의 차이가 미미",
         f"Sharpe {s_full:.3f} vs X1 {s_x1:.3f}" if np.isfinite(s_full) and np.isfinite(s_x1) else "산출 불가",
         "❗ 충족(폐기)" if k2 else "✔ 미충족"],
        ["③ 배제 컴포넌트가 MDD 개선에 기여 못함",
         f"MDD {100*m_full:+.1f}% vs X1 {100*m_x1:+.1f}%" if np.isfinite(m_full) and np.isfinite(m_x1) else "산출 불가",
         "❗ 충족(폐기)" if k3 else "✔ 미충족"],
    ], ["폐기 조건", "근거 수치", "판정"], ["l", "l", "c"], maxw=48)

    if any(out.values()):
        LOG.warn("§10.4 폐기 조건이 충족되었습니다. 이 결과를 파라미터 조정으로 되살리려 하지 "
                 "마십시오. 위 수치를 그대로 보고하고 중단하는 것이 사전등록의 이행입니다.")
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
