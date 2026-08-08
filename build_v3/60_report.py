# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증 · 해석표 · 진단카드 · 원장 연결 지도                                        ║
# ║                                                                                          ║
# ║  "어디서 에러가 났고, 데이터 입출력이 어디서 일어났고, 애널리스트 보고서와 식별된            ║
# ║   애널리스트가 제대로 연결됐고, 다중소스 원장 연결이 확실한지"를 한눈에 보여주는 층.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance_v3(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    R = bt["returns"]
    s = perf_stats(R)
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다(수익률 시계열이 비었습니다).")
        return
    order = ["월수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "월평균", "t통계량(HAC)", "최장언더워터(월)", "누적수익", "평균종목수",
             "월평균회전율", "월평균비용"]
    pct = {"CAGR", "연변동성", "MDD", "승률", "월평균", "누적수익", "월평균회전율", "월평균비용"}
    rows = []
    for k in order:
        v = s.get(k)
        if v is None:
            continue
        rows.append([k, f"{v:.2%}" if k in pct and np.isfinite(v) else
                     (f"{v:,.2f}" if isinstance(v, float) else f"{v:,}")])
    LOG.table(rows, ["지표", "값"], ["l", "r"],
              title=f"성과 검증 {label or STRATEGY_ID} (비용: 수수료+세금+제곱근충격 반영)")

    # 벤치마크 비교 — ★ 하드코딩된 과거 수치를 인용하지 않는다. 전부 이 실행에서 재측정한다.
    if bench:
        brows = []
        r = pd.Series(R["ret"].to_numpy(dtype=float), index=pd.DatetimeIndex(R["month"]))
        for name, bs in bench.items():
            b = pd.Series(bs).reindex(r.index)
            both = pd.concat([r, b], axis=1).dropna()
            if len(both) < 6:
                continue
            bstat = perf_stats(pd.DataFrame({"month": both.index, "ret": both.iloc[:, 1].to_numpy(),
                                             "n": 0, "turnover": 0.0, "cost": 0.0}))
            ex = both.iloc[:, 0] - both.iloc[:, 1]
            mu, t = hac_tstat(ex.to_numpy())
            brows.append([name, f"{bstat.get('CAGR', np.nan):.2%}",
                          f"{bstat.get('MDD', np.nan):.1%}",
                          f"{bstat.get('Calmar', np.nan):.2f}",
                          f"{(s.get('CAGR', np.nan) - bstat.get('CAGR', np.nan)):+.2%}",
                          f"{mu*12:+.2%}", f"{t:.2f}"])
        if brows:
            LOG.table(brows, ["벤치마크", "벤치 CAGR", "벤치 MDD", "벤치 Calmar",
                              "CAGR 차", "연환산 초과", "t(HAC)"],
                      ["l", "r", "r", "r", "r", "r", "r"],
                      title="벤치마크 대비 (이 실행에서 직접 재측정 — 인용 없음)")

    if "월평균현금비중" in s and np.isfinite(s.get("월평균현금비중", np.nan)):
        LOG.info(f"월평균 현금 비중 {s['월평균현금비중']:.1%} — 이 비중만큼은 시장에 노출되지 "
                 f"않았습니다. 다른 팔과 CAGR 을 비교하기 전에 이 값부터 맞춰 보세요.")
    report_emp_regime_v3(bt)
    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:.4f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측꼬리 기여도 — 상위 종목을 빼면 성과가 남는가")
        base, top5 = rt.get("총기여", 0.0), rt.get("상위5% 기여", 0.0)
        if base and abs(top5) > abs(base) * 0.8:
            LOG.warn(f"총기여의 {100*top5/base:.0f}%가 상위 5% 종목에서 나옵니다. "
                     f"이 전략은 우측 꼬리 의존적입니다 — 표본 밖에서 재현되지 않을 위험이 "
                     f"IR 이 시사하는 것보다 훨씬 큽니다. 숨기지 않고 명시합니다.")


def report_emp_regime_v3(bt: dict) -> None:
    """★★ 이 전략의 결과를 CAGR 한 줄로 말하면 안 되는 이유를 표로 보여준다 ★★

    7회차 실행의 직원현황 커버리지는 2022~2025 네 해뿐이었다. 백테스트는 120개월인데
    앞 80개월에는 EMP 센서가 한 건도 없다. 그 구간의 성과는 **CORE-D 단독 전략**의
    성과이고, 뒤 40개월만이 'CORE-D + EMP-LITE' 다. 두 구간을 복리로 이어 붙여
    "이 전략의 10년 CAGR" 이라고 부르면, 존재한 적 없는 하나의 전략을 보고하는 셈이다.

    → 신호가 실제로 존재한 구간과 아닌 구간을 갈라서 나란히 낸다. 합산값도 함께 두되,
      그것이 두 전략의 이어붙임이라는 사실을 표 제목에 적는다. 숨기고 합치지 않는다.
    """
    R = bt.get("returns")
    if R is None or R.empty:
        return
    R = R.copy()
    R["month"] = as_ts_series(R["month"])
    # ★ '최소~최대 봉투'가 아니라 **실제 관측이 있는 달의 집합**으로 가른다.
    #   봉투를 쓰면 중간에 뚫린 달(수집이 안 된 해)까지 'EMP 있음'으로 계산된다.
    _mset = EMP_SIGNAL_SPAN.get("months") or set()
    if _mset:
        on = R["month"].isin({as_ts(m) for m in _mset})
    else:
        lo, hi = EMP_SIGNAL_SPAN.get("lo"), EMP_SIGNAL_SPAN.get("hi")
        on = (pd.Series(False, index=R.index) if lo is None or hi is None
              else (R["month"] >= as_ts(lo)) & (R["month"] <= as_ts(hi)))
    pre = R[~on]
    n_on = int(on.sum())
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 표를 못 그리는 경우일수록 **더 크게** 말해야 한다 ★★
    #    예전 판은 `if len(pre) < 6 or n_on < 6: return` 으로 조용히 빠져나갔다.
    #    그런데 이 함수의 존재 이유는 'EMP 구간이 짧으니 합산 CAGR 을 인용하지 말라'는
    #    경고다. EMP 커버리지가 최악일 때(=경고가 가장 필요할 때) 정확히 침묵하는 셈이었다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    if n_on < 6:
        LOG.warn(f"★ 이 실행에는 직원현황(알파) 관측이 {n_on}개월뿐입니다 — 사실상 "
                 f"**CORE-D 단독 전략**의 백테스트입니다. 위/아래의 CAGR·Sharpe 를 "
                 f"'CORE-D + EMP-LITE' 의 성과로 인용하면 안 됩니다. TP_N1·N2·N3 가 "
                 f"거의 전 구간 결측이므로 이 문서의 존재 이유인 R2-N 도 검정불가입니다. "
                 f"직원현황을 더 채운 뒤 재실행하세요(격자가 회사 우선이라 재실행할수록 "
                 f"과거 구간이 함께 채워집니다).")
        return
    if len(pre) < 6:
        LOG.info(f"전 구간({len(R)}개월) 중 {n_on}개월에 EMP 관측이 있어 레짐이 사실상 "
                 f"하나입니다 — 분할표를 생략합니다(가를 것이 없습니다).")
        return
    rows = []
    for lab, sub, note in (
            ("EMP 신호 없음 (CORE-D 단독)", pre, "직원현황 미수집 구간"),
            (f"EMP 신호 있음 ({as_ts(lo):%Y-%m}~{as_ts(hi):%Y-%m})", R[on],
             "CORE-D + EMP-LITE"),
            ("합산 (두 전략의 이어붙임)", R, "★ 하나의 전략이 아님")):
        st = perf_stats(sub.reset_index(drop=True))
        _f = lambda k, fmt: (format(st[k], fmt)
                             if k in st and np.isfinite(st.get(k, np.nan)) else "-")
        rows.append([lab, f"{len(sub)}", _f("CAGR", ".2%"), _f("Sharpe", ".2f"),
                     _f("MDD", ".1%"), _f("t통계량(HAC)", ".2f"), note])
    LOG.table(rows, ["구간", "월수", "CAGR", "Sharpe", "MDD", "t(HAC)", "비고"],
              ["l", "r", "r", "r", "r", "r", "l"],
              title="★ EMP 레짐 분할 — 이 표를 보기 전에 위의 합산 CAGR 을 인용하지 마십시오")
    LOG.warn(f"직원현황(알파 원천)이 존재한 구간은 {int(on.sum())}/{len(R)}개월"
             f"({on.mean():.0%})뿐입니다. 나머지 {len(pre)}개월은 CORE-D 5개 TP 만으로 돈 "
             f"**다른 전략**입니다. 두 구간을 복리로 이어 붙인 값을 '이 전략의 10년 성과'로 "
             f"쓰면 존재한 적 없는 전략을 보고하는 것이 됩니다. "
             f"결론은 위 표의 'EMP 신호 있음' 행에서 읽으시고, 그 구간이 짧다면 "
             f"직원현황을 더 채운 뒤 재판정하세요 — 격자가 회사 우선이라 재실행할수록 "
             f"과거 구간이 함께 채워집니다.")


INTERP_D_STATE_V3 = [
    ("목표상태(진입)", "이익은 늘었는데 시장이 자본화를 거부 — 노리는 미스프라이싱"),
    ("리레이팅중(관망)", "이익도 늘고 멀티플도 확장 중 — 이미 반영이 진행됨"),
    ("기대선행(배제)", "이익은 그대로인데 멀티플만 확장 — 기대만 앞선 상태"),
    ("개선없음(배제)", "이익도 멀티플도 개선 없음"),
]

INTERP_TP_V3 = [
    ("TP_I1", "확장하면서 수익성을 지킴 — 투하자본 효율이 계단 상승", "설비만 늘고 ROIC 하락"),
    ("TP_I2", "매출이 느는데 운전자본 회전이 안 나빠짐 — 밀어내기가 아님", "매출↑ + 재고/채권 급증"),
    ("TP_N1", "★비싼 사람을 뽑으며 인원 확충 — 진짜 역량 확충", "저임금 대량채용(보조금 유인 의심)"),
    ("TP_N2", "인원이 느는데 1인당 부가가치가 안 희석됨", "인원만 늘고 생산성 희석"),
    ("TP_N3", "정규직으로 늘림 — 되돌릴 수 없는 확신의 증거", "계약직 위주 확대"),
    ("TP_I4", "매출이 느는데 발생액이 안 늘어남 — 이익의 질 유지", "매출↑ + 발생액 급증"),
    ("TP_P1", "환원과 투자를 동시에 늘림 — 진짜 잉여현금 창출력", "성장 포기하고 환원만"),
    ("TP_P2", "자사주를 사서 실제로 소각까지 감 — 진정성", "취득만 하고 물량 재활용"),
]


def report_interpretation_v3(P: pd.DataFrame):
    if "D_state" in P.columns:
        cnt = P["D_state"].value_counts()
        tot = int(cnt.sum()) or 1
        LOG.table([[k, d, f"{int(cnt.get(k,0)):,}", f"{100*int(cnt.get(k,0))/tot:.1f}%"]
                   for k, d in INTERP_D_STATE_V3],
                  ["U축 상태", "의미", "행수", "비율"], ["l", "l", "r", "r"],
                  title="반영도(U) 상태 분포 — Δlog P = Δlog E + Δlog M 분해")

    rows = []
    for tid, good, bad in INTERP_TP_V3:
        if tid not in P.columns:
            continue
        v = P[tid]
        rows.append([tid, _trunc(good, 40), _trunc(bad, 30),
                     f"{float(v.notna().mean())*100:.1f}%",
                     f"{float((v > 0).mean())*100:.1f}%"])
    LOG.table(rows, ["TP", "높으면 (해석)", "낮으면/0 (해석)", "관측률", "양(>0)"],
              ["l", "l", "l", "r", "r"], title="트레이드오프 해석표", maxw=44)

    if "nl_premium" in P.columns and P["nl_premium"].notna().any():
        q = P["nl_premium"].dropna()
        below = float((q < 1.0).mean())
        LOG.table([["관측 수", f"{len(q):,}"],
                   ["중앙값", f"{q.median():.2f}"],
                   ["평균", f"{q.mean():.2f}"],
                   ["< 1.0 비율 (저임금 채용 의심)", f"{below:.1%}"],
                   ["> 1.0 비율 (역량 확충)", f"{1-below:.1%}"],
                   ["상위 10% 경계", f"{q.quantile(0.9):.2f}"]],
                  ["임금프리미엄", "값"], ["l", "r"],
                  title="임금프리미엄 분포 — 정책오염 필터가 산식에 내장되어 있다")


def diagnostic_card_v3(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    """최근 월 상위 종목이 '왜' 뽑혔는지 TP 단위로 분해해 보여준다."""
    if P.empty or "Signal_rank" not in P.columns:
        return
    m = P["month"].max()
    sub = P[(P["month"] == m) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    sub = sub.sort_values("Signal_rank", ascending=False).head(top_n)
    if sub.empty:
        LOG.info("최근 월에 선정 조건을 통과한 종목이 없어 진단 카드를 생략합니다.")
        return
    nm = sec.drop_duplicates("code").set_index("code")["name"].to_dict()
    live = [c for c, *_ in TP_DEFS if c in P.columns]
    LOG.banner(f"종목 진단 카드 — {as_ts(m):%Y-%m} 상위 {len(sub)}종목",
               "각 종목이 어떤 트레이드오프로 뽑혔는지 분해합니다")
    for r in sub.itertuples(index=False):
        d = r._asdict()
        vals = [(c, d.get(c)) for c in live]
        got = [(c, v) for c, v in vals if v is not None and pd.notna(v)]
        got.sort(key=lambda x: -float(x[1]))
        LOG.table([[c, f"{float(v):.4f}",
                    next((g for t, g, _b in INTERP_TP_V3 if t == c), "")[:38]] for c, v in got]
                  + [["— 없음(결측)", ", ".join(c for c, v in vals
                                                if v is None or pd.isna(v)) or "-", ""]],
                  ["TP", "값", "해석"], ["l", "r", "l"],
                  title=f"{nm.get(d.get('code'), '')}({d.get('code')}) · "
                        f"Signal_rank {float(d.get('Signal_rank', np.nan)):.3f} · "
                        f"E {float(d.get('E', np.nan)):.3f} · U {float(d.get('U', np.nan)):.3f} · "
                        f"{d.get('D_state', '')}", maxw=40)
        emp_bits = []
        for k, lab, fmt in (("employees", "직원수", ",.0f"), ("nl_emp", "Δlog인원", "+.3f"),
                            ("nl_premium", "임금프리미엄", ".2f"),
                            ("nl_regular", "Δ정규직비중", "+.3f"),
                            ("i_capex", "CapEx/3년평균", ".2f"),
                            ("eff_tax", "실효세율", ".1%")):
            v = d.get(k)
            if v is not None and pd.notna(v):
                emp_bits.append(f"{lab} {format(float(v), fmt)}")
        if emp_bits:
            LOG.info("   " + " · ".join(emp_bits))


def report_ledger_v3(ctx: dict):
    """다중소스 원장 연결 감사 — '무엇과 무엇이 어떤 키로 연결되었는가'를 표로 못박는다."""
    sec = ctx.get("sec", pd.DataFrame())
    rep = ctx.get("reports", pd.DataFrame())
    A = ctx.get("analysts", pd.DataFrame())
    L = ctx.get("links", pd.DataFrame())
    emp = ctx.get("emp_raw", pd.DataFrame())
    fin = ctx.get("fin", pd.DataFrame())

    def _n(df, c=None):
        """행수(c=None) 또는 컬럼 c 의 유효값 수.

        ★★ 예전엔 컬럼이 없으면 **전체 행수**를 돌려줬다 ★★
          그래서 리포트 원장의 종목코드 연결률이 항상 100% 로 찍혔다 — 실제 컬럼명은
          'stock_code' 인데 표는 'code' 를 물었고, 없으니 len(df) 가 반환돼
          '연결 N건 (100%)' 이 되는 구조였다. 연결이 하나도 안 됐을 때 가장 크게
          100% 라고 말하는 셈이다. 컬럼 부재는 '전부 연결됨'이 아니라 '잴 수 없음'이다.
        """
        if df is None or len(df) == 0:
            return 0
        if not c:
            return int(len(df))
        return int(df[c].notna().sum()) if c in df.columns else 0

    def _link(df, cands: Sequence[str]) -> Tuple[int, str]:
        """후보 컬럼명 중 실제로 존재하는 것으로 연결 수를 센다(이름 불일치로 0 이 되지 않게)."""
        if df is None or len(df) == 0:
            return 0, "-"
        for c in cands:
            if c in df.columns:
                return int(df[c].notna().sum()), c
        return 0, "컬럼없음"

    def _nuniq(df, c):
        """컬럼이 없거나 비어도 감사표가 죽지 않게 한다 — 감사표는 실패했을 때 가장 필요하다."""
        if df is None or len(df) == 0 or c not in df.columns:
            return "0사"
        return f"{df[c].nunique():,}사"

    rows = [
        ["종목마스터 ← FDR·KIND·pykrx·폐지목록", "code", f"{_n(sec):,}",
         f"corp_code 연결 {_n(sec,'corp_code'):,} ({100*_n(sec,'corp_code')/max(_n(sec),1):.0f}%)",
         "DART 재무·직원현황의 유일한 조인키"],
        ["DART 재무 ← corp_code", "corp_code",
         f"{_n(fin):,}", _nuniq(fin, "corp_code"),
         "knowledge_date = 접수일자(rcept_no 앞 8자리)"],
        ["DART 직원현황 ← corp_code", "corp_code",
         f"{_n(emp):,}", _nuniq(emp, "corp_code"),
         "knowledge_date = 사업보고서 접수일"],
        ["리포트 원장 ← 한경컨센서스·네이버", "report_id", f"{_n(rep):,}",
         (lambda nc: f"종목코드 연결 {nc[0]:,} "
                     f"({100*nc[0]/max(_n(rep),1):.0f}% · 키={nc[1]})")(
             _link(rep, ["stock_code", "code", "ticker"])),
         "제목 정규식 + 네이버 stock_item href"],
        ["애널리스트 원장 ← 리포트", "analyst_id", f"{_n(A):,}",
         f"보고서-애널 링크 {_n(L):,}건", "증권사 사명 정규화 후 (이름,증권사) 동일성"],
    ]
    LOG.table(rows, ["원장 / 소스", "조인키", "행수", "연결 실적", "비고"],
              ["l", "c", "r", "l", "l"], title="다중소스 원장 연결 감사", maxw=44)

    if _n(rep) and _n(A):
        try:
            audit_linkage(rep, A, L)
        except Exception as e:                                    # noqa
            LOG.warn(f"애널리스트 원장 상세 감사 실패({type(e).__name__}) — 요약만 출력했습니다.")
    elif RESEARCH_COLLECT:
        LOG.info("애널리스트 리포트가 수집되지 않았습니다. U축은 d1·d3 만으로 구성되며 "
                 "(스펙 §8 이 요구하는 구성이 바로 그것이므로) 전략 자체는 온전합니다. "
                 "원장은 공용 인덱스 재활용·감사 목적으로만 사용합니다.")


def report_dataflow_map_v3():
    LOG.banner("데이터 흐름 지도", "어느 소스가 어느 단계에서 무엇을 만드는지")
    _safe_print("""
  ┌───────────────────────── L0 준비 ─────────────────────────────────────────────────────┐
  │  환경감지(Colab/Jupyter) → 구글드라이브 마운트 → VAULT(공용 _shared / 전용 tcd_v3_*)   │
  │  계약검정 C1·C2·C13·C15 · 원칙1~7  →  합성 스모크  →  실경로 리허설                    │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │
  ┌───────────────────────── L1 수집 ─────────────────────────────────────────────────────┐
  │  FDR/KIND/pykrx/DART corpCode ─→ 종목마스터(code·corp_code·상장일·폐지일·업종)         │
  │  pykrx→FDR→네이버→yfinance(+KRX 마켓플레이스 세션) ─→ 일별 가격 ─→ 월 패널(exec_px)    │
  │  DART fnlttMultiAcnt(배치) + fnlttSinglAcntAll(단건) ─→ 재무 TTM (knowledge=접수일)    │
  │  DART empSttus(확장: sm·급여총액·1인평균·정규직) ───→ 연도 프레임 EMP 센서 + C15       │
  │  DART list.json 스윕 ───→ 자사주 취득/소각·유증·CB/BW  (V3·p_cancel)                   │
  │  한경컨센서스 + 네이버리서치 ─→ 리포트 원장 ─→ 애널리스트 원장(엔티티 해소)             │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │  merge_asof(knowledge_date ≤ month) 단일 패스
  ┌───────────────────────── L1 센서 ─────────────────────────────────────────────────────┐
  │  CORE-D : i_sales i_turn i_accr i_capex i_ic i_roic p_payout p_invest p_cancel        │
  │  EMP-LITE: nl_emp nl_dn nl_marginal nl_premium★ nl_vapp nl_regular   (C15 게이트)      │
  │  U축    : d1 = -ΔlogM(120거래일) · d3 = -기관외국인 120일 누적순매수                   │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │  셀 = month × ind_mid × size_bucket(3단계)
  ┌───────────────────────── L2 스코어 ───────────────────────────────────────────────────┐
  │  TP = max(rank-0.5, 0) × max(rank-0.5, 0)        ← 음수 불가 (부호 버그 구조적 차단)   │
  │  E = mean(8 TP) · U = mean(z(d1), z(d3))                                              │
  │  Signal = rank(E) × rank(U) × V1·V2·V3·V5·V6·V8                                       │
  └──────────────────────────────────────────────────────────────────────────────────────┘
                                        │
  ┌──────────── L3 백테스트 ────────────┐   ┌──────────── L5 강건성 ─────────────────────┐
  │ 월 1회 · 다음 거래일 시가 체결       │   │ R0 자체벤치 · R1 누수 · R2-N★ · R3 직교화  │
  │ 비용(수수료+세금+제곱근충격)         │   │ R5 절제 · R7 레짐 · R8 하위기간 · R10 정책 │
  │ 상폐 -100% · 24개월 상한 · 청산게이트│   └────────────────────────────────────────────┘
  └─────────────────────────────────────┘
""")
