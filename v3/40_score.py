

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  정규화 → TP → 거부권 → E/U/V → Signal   (§6.5 · §7 · §8)                             ║
# ║                                                                                          ║
# ║  이 블록 전체가 L2 다. L1 parquet 만 읽고, 매 절제마다 통째로 다시 돈다(수십 초).          ║
# ║  C5 순서는 여기서 단 한 번 하드코딩되고 파라미터화하지 않는다:                              ║
# ║      winsorize(±2σ) → cell_z → clip(·,0) → TP → rank_pct                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── §6.6 CORE-D 트레이드오프 쌍 ─────────────────────────────────────────────────────────────
TP_DEFS: List[Tuple[str, str, str, str, str]] = [
    # (ID,      개선축,      대가회피축,   최소단계, 발화 의미)
    ("TP_I2", "i_sales", "i_turn",   "M0", "매출↑인데 회전 유지 = 수요가 당김"),
    ("TP_I4", "i_sales", "i_accr",   "M0", "매출↑인데 발생액 유지 = 이익의 질"),
    ("TP_I1", "i_capex", "i_roic",   "M1", "확장하는데 수익성 유지 = 제약선 이동"),
    ("TP_P1", "p_payout", "p_invest", "M1", "환원↑인데 투자도↑ = 잉여현금 창출력"),
    ("TP_P2", "treasury_acq_amt", "p_cancel", "M1", "취득 큰데 소각까지 = 진정성"),
    ("TP_I3", "i_emp", "i_vapp",     "M2", "인원↑인데 생산성 유지 = 희석 없는 확장"),
]
# §8.1 E 의 구성: TP 6개 + rank_pct(b4_defrev). 동일가중(C7 — 최적화 금지).
E_EXTRA = [("b4_defrev", "M1", "계약부채·선수금 증가 = 미인식 수요")]
# §8.1 U 의 구성. d2/d4 는 사양 확장(USE_RESEARCH_AXIS) — R5 에서 기여도를 반드시 본다.
U_AXES_CORE = [("d1", "M3"), ("d3", "M3")]
U_AXES_RESEARCH = [("d2_raw", "M3"), ("d4_raw", "M3")]

# 하한선(breadth floor) — §8.1 "모든 축이 상위"가 아니라 **"빈 축이 없을 것"**
#
#   ★ 두 가지를 의도적으로 정했고, 둘 다 이유가 실측이다.
#
#   ① 축 하나하나가 아니라 '군' 단위다. 7개 축 전부에 50th 를 걸면 독립 가정에서
#      0.5^7 = 0.8% 만 통과해 하한선 하나가 선정을 지배한다. 그러면 R2(TP vs 나이브)
#      비교가 성립하지 않는다 — 두 팔이 같은 하한선을 물려받으면 나이브 팔조차 TP 로
#      선별된 종목만 보기 때문이다(v2 실측 자카드 0.73).
#
#   ② 군의 값은 **TP 곱이 아니라 그 군을 구성하는 원시 센서의 셀 랭크 평균**이다.
#      TP 곱을 쓰면 clip(z,0) 때문에 유니버스의 약 75%가 정확히 0 이 되고, 그 동점 덩어리의
#      평균 랭크가 0.375 라 50th 문턱에서 전부 탈락한다. 실측: 3개 군 전부에 걸면 통과율이
#      1.6% → 월 보유가 한 자릿수로 붕괴했다. 그리고 그건 '하한선'이 아니라 스코어를 한 번 더
#      건 것이다. 원시 센서 랭크로 재면 동점 덩어리가 없고, "각 센서군에서 빈 축 없이 최소한
#      중간은 간다"는 breadth 의 문자 그대로의 뜻이 된다.
FLOOR_GROUPS: Dict[str, Tuple[List[str], str]] = {
    "내부효율":   (["i_sales", "i_turn", "i_accr"], "M0"),
    "자본투입":   (["i_capex", "i_roic"], "M1"),
    "자본배분":   (["p_payout", "p_invest"], "M1"),
    "미인식수요": (["b4_defrev"], "M1"),
    "인적확장":   (["i_emp", "i_vapp"], "M2"),
}


def _stage_ok(need: str, stage: str) -> bool:
    order = STAGE_ORDER
    s = stage if stage in order else order[-1]
    return order.index(need) <= order.index(s)


def build_tps(P: pd.DataFrame, stage: str = "M3", tp_mode: str = "clip",
              cell_keys: Sequence[str] = CELL_KEYS,
              drop: Sequence[str] = ()) -> Tuple[pd.DataFrame, List[str]]:
    """§6.5 TP 조립. drop 에 든 TP 는 만들지 않는다(R5 절제용)."""
    p = P.copy()
    cells = cell_series(p, cell_keys)
    cells_fb = cell_ladder(p, cell_keys)
    made = []
    for tid, a, b, need, _why in TP_DEFS:
        if tid in drop or not _stage_ok(need, stage):
            continue
        if a not in p.columns or b not in p.columns:
            continue
        if col(p, a).notna().sum() == 0 or col(p, b).notna().sum() == 0:
            LOG.debug(f"{tid} 건너뜀 — 입력 센서({a} 또는 {b})가 전부 결측")
            continue
        p[tid] = tp_dispatch(tp_mode, col(p, a), col(p, b), cells, cells_fb)
        made.append(tid)
    return p, made


def assemble_score(P: pd.DataFrame, stage: str = "M3", tp_mode: str = "clip",
                   drop_tp: Sequence[str] = (), drop_axis: Sequence[str] = (),
                   floor_pct: float = BREADTH_FLOOR_PCT,
                   cell_keys: Sequence[str] = CELL_KEYS,
                   use_research: Optional[bool] = None,
                   quiet: bool = False) -> pd.DataFrame:
    """§8.1  Signal = rank_pct(E) × rank_pct(U) × ∏V_k

    ★ E 와 U 를 **둘 다 백분위 랭크로 바꾼 뒤** 곱한다. 원값 곱은 음수 구간에서 단조성이
      깨진다(U 는 z 평균이라 음수가 나온다). v2 는 이걸 원값으로 곱해 U<0 인 종목의
      순서가 뒤집혀 있었다.
    """
    use_research = USE_RESEARCH_AXIS if use_research is None else use_research
    p, tps = build_tps(P, stage=stage, tp_mode=tp_mode, cell_keys=cell_keys, drop=drop_tp)
    cells = cell_series(p, cell_keys)
    cells_fb = cell_ladder(p, cell_keys)
    fb = list(cell_keys[:-1]) or list(cell_keys)

    # ── E: 동일가중 평균 (C7) ───────────────────────────────────────────────────────────
    e_parts, e_names = [], []
    for tid in tps:
        r = cell_rank(p, p[tid], cell_keys, fb, tag=tid)
        p[f"r_{tid}"] = r
        e_parts.append(r)
        e_names.append(tid)
    for nm, need, _why in E_EXTRA:
        if nm in drop_tp or nm in drop_axis or not _stage_ok(need, stage):
            continue
        if nm not in p.columns or col(p, nm).notna().sum() == 0:
            continue
        r = cell_rank(p, p[nm], cell_keys, fb, tag=nm)
        p[f"r_{nm}"] = r
        e_parts.append(r)
        e_names.append(nm)
    if not e_parts:
        raise RuntimeError(
            "E 를 구성할 축이 하나도 없습니다. L1 센서가 전부 결측이라는 뜻입니다 — "
            "위 'L1 센서 커버리지' 표에서 어느 입력이 비었는지 확인하세요. "
            "가장 흔한 원인은 DART_API_KEY 미입력 또는 재무 수집 실패입니다.")
    E = pd.concat(e_parts, axis=1)
    # ★ 결측 축은 '제외 평균'이다. 0 으로 채우면 "그 축에서 최하위" 라는 거짓 주장이 된다.
    p["E"] = E.mean(axis=1, skipna=True).astype("float32")
    p["E_n"] = E.notna().sum(axis=1).astype("int16")

    # ── U: 결측 축 제외 평균 (z 스케일) ─────────────────────────────────────────────────
    u_axes = [a for a, need in U_AXES_CORE if _stage_ok(need, stage)]
    if use_research:
        u_axes += [a for a, need in U_AXES_RESEARCH if _stage_ok(need, stage)]
    u_axes = [a for a in u_axes if a not in drop_axis and a in p.columns
              and col(p, a).notna().sum() > 0]
    if u_axes:
        U = pd.concat([xsec_z_fb(col(p, a), cells, cells_fb, tag=a).rename(a) for a in u_axes],
                      axis=1)
        p["U"] = U.mean(axis=1, skipna=True).astype("float32")
        p["U_n"] = U.notna().sum(axis=1).astype("int16")
    else:
        # U 층이 아직 없는 단계(M0~M2)에서는 U 를 중립(전 종목 동일)으로 둔다.
        # 0 으로 채우는 것과 다르다 — 랭크가 전부 같아지므로 Signal 순서를 E 가 결정한다.
        p["U"] = 0.0
        p["U_n"] = 0

    p["E_rank"] = cell_rank(p, p["E"], ["ym"], ["ym"], min_n=20, tag="E")
    p["U_rank"] = (cell_rank(p, p["U"], ["ym"], ["ym"], min_n=20, tag="U")
                   if len(u_axes) else pd.Series(1.0, index=p.index, dtype="float32"))

    # ── V: 거부권 (이진, 상쇄 금지 — C6) ────────────────────────────────────────────────
    p = apply_vetoes(p, stage=stage, quiet=quiet, copy=False)

    # ── 하한선 (breadth floor) ──────────────────────────────────────────────────────────
    p, floor_info = apply_breadth_floor(p, stage=stage, tps=tps, floor_pct=floor_pct,
                                        cell_keys=cell_keys, quiet=quiet, copy=False)

    # ── Signal ──────────────────────────────────────────────────────────────────────────
    p["Signal"] = (p["E_rank"].astype("float64") * p["U_rank"].astype("float64")
                   * p["VETO"].astype("float64")).astype("float32")
    # ★ Signal_rank 는 **월 전체** 백분위여야 한다. 하위 그룹(정보량·셀)별로 매기면
    #   '자기 그룹에 혼자인' 종목이 전부 1.0 을 받아 상위를 독차지한다(v2 의 치명 결함).
    p["Signal_rank"] = (p["Signal"].groupby(p["month"], observed=True)
                        .rank(pct=True, method="average").astype("float32"))

    if not quiet:
        _report_score_health(p, e_names, u_axes, floor_info)
    PIPE.io("OUT", "MEM", "L2_scores", p[["code", "month", "E", "U", "Signal", "VETO", "FLOOR"]])
    return p


def report_dead_signals(P: pd.DataFrame, stage: str = "M3"):
    """★ '무엇이 죽었는가'를 백테스트 **전에** 표로 못박는다.

    K1(벌크) 이 실패해 폴백 A 로 내려가면 재고·매출채권·영업CF 가 없어 TP_I2/TP_I4/TP_I1 이
    조용히 결측이 된다. 그런데 파이프라인은 남은 축으로 평균을 내고 끝까지 '성공'한다.
    사용자는 코어가 빠진 전략의 성과를 보면서 그 사실을 모른다. 그게 최악이다.
    """
    rows, dead = [], []
    for tid, a, b, need, why in TP_DEFS:
        if not _stage_ok(need, stage):
            rows.append([tid, "—", "—", f"단계 미도달({need})", why])
            continue
        na = int(col(P, a).notna().sum()) if a in P.columns else 0
        nb = int(col(P, b).notna().sum()) if b in P.columns else 0
        ok = na > 0 and nb > 0
        if not ok:
            dead.append(tid)
        rows.append([tid, f"{na:,}", f"{nb:,}",
                     "✔ 살아있음" if ok else f"✘ 죽음 ({a if na == 0 else b} 결측)", why])
    LOG.table(rows, ["TP", f"개선축 관측", "대가축 관측", "상태", "발화 의미"],
              ["c", "r", "r", "l", "l"],
              title="신호 생존 점검 — 어떤 트레이드오프 쌍이 실제로 계산되는가")
    if dead:
        LOG.warn(f"죽은 TP: {dead}. 이 전략의 코어가 그만큼 비어 있는 상태로 백테스트가 "
                 f"진행됩니다 — 남은 축으로 평균을 내고 끝까지 '성공'하므로 결과만 보면 "
                 f"알 수 없습니다. 가장 흔한 원인은 CANARY K1(벌크) 실패 후 폴백 A 로 "
                 f"내려가 재고·매출채권·영업CF 가 없는 경우입니다. 위 '필수 계정 커버리지' "
                 f"표에서 어느 계정이 비었는지 확인하세요.")
        PIPE.note(f"WARN: 죽은 TP {dead}")
    return dead


def _report_score_health(p: pd.DataFrame, e_names, u_axes, floor_info):
    n = max(len(p), 1)
    e = p["E"]
    zero_mass = float((e.fillna(-1) <= 1e-12).mean())
    top = p[p["Signal_rank"] >= 0.95]
    tie = float(top["Signal"].duplicated().mean()) if len(top) else 0.0
    LOG.table([["E 구성축", ", ".join(e_names)],
               ["U 구성축", ", ".join(u_axes) or "(없음 — 단계 미도달)"],
               ["E 유효행", f"{int(e.notna().sum()):,} / {n:,} ({100*e.notna().mean():.1f}%)"],
               ["E 평균 축개수", f"{float(p['E_n'].mean()):.2f}"],
               ["E=0 질량", f"{100*zero_mass:.1f}%"],
               ["상위 5% 내 동점비율", f"{100*tie:.1f}%"],
               ["거부권 통과", f"{int((p['VETO'] == 1).sum()):,} ({100*(p['VETO'] == 1).mean():.1f}%)"],
               ["하한선 통과", f"{int((p['FLOOR'] == 1).sum()):,} ({100*(p['FLOOR'] == 1).mean():.1f}%)"],
               ["최종 후보(둘 다 통과)",
                f"{int(((p['VETO'] == 1) & (p['FLOOR'] == 1)).sum()):,}"]],
              ["항목", "값"], ["l", "l"], title="L2 스코어 건전성")
    if zero_mass > 0.75:
        LOG.warn(f"E 가 정확히 0 인 행이 {100*zero_mass:.0f}% 입니다. clip(z,0) 방식에서는 "
                 f"자연스러운 현상이지만(양쪽 축이 모두 평균 이상인 종목만 양수), 이 값이 "
                 f"90% 를 넘으면 선정이 사실상 소수 후보 안에서만 이뤄집니다. "
                 f"R5 의 tp_mode='rank' 팔과 비교해 어느 쪽이 나은지 확인하세요.")
    if tie > 0.25:
        LOG.warn(f"상위 5% 구간의 동점비율이 {100*tie:.0f}% 입니다. 동점은 명시적 정렬키로 "
                 f"결정적으로 깨지지만(_top_n), 동점이 많다는 건 신호의 분해능이 낮다는 뜻입니다.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §8.2  거부권 — 이진, 상쇄 금지 (C6)
# ═══════════════════════════════════════════════════════════════════════════════════════════
VETO_DEFS = [
    ("V1", "M0", "밀어내기: Δ매출>0 인데 (Δ재고+Δ매출채권)/Δ매출 > 1.5"),
    ("V2", "M0", "이익-현금 괴리 3분기 연속: 순이익>0 인데 영업CF < 0.5×순이익"),
    ("V3", "M1", "90일 내 대규모 희석성 조달(유증/CB/BW)"),
    ("V5", "M0", "자본잠식 (감사의견·관리종목은 데이터 없음 — 아래 주석 참조)"),
    ("V6", "M0", "20일 평균거래대금 하한 미만 또는 거래정지"),
]


def apply_vetoes(P: pd.DataFrame, stage: str = "M3", quiet: bool = False,
                 copy: bool = True) -> pd.DataFrame:
    """각 거부권은 독립 이진이고 곱으로 결합한다. 점수로 환산해 상쇄시키지 않는다(C6).

    ★ 결측 = 통과다. 근거 없이 종목을 제외하면 그게 곧 선택편향이다.
      (예: 재무가 없는 종목을 V2 로 자르면 DART 커버리지가 낮은 소형주만 통째로 사라진다)

    copy=False 는 호출자가 이미 소유한 복사본일 때만 쓴다. 실데이터 패널은 300~400MB 라
    assemble_score 안에서 무조건 복사하면 한 번의 L2 통과에 전체 패널이 3벌 상주하고,
    R5 절제가 그걸 18회 반복한다.
    """
    p = P.copy() if copy else P
    v1 = ~(col(p, "v1_push") > 1.5).fillna(False)
    v2 = ~(col(p, "v2_bad") >= 1.0).fillna(False)
    v3 = ~(col(p, "v3_dilute") > 0).fillna(False) if _stage_ok("M1", stage) else pd.Series(True, index=p.index)
    v5 = ~(col(p, "v5_impair") > 0).fillna(False)
    halted = col(p, "volume").fillna(1.0) <= 0
    v6 = (col(p, "adv20") >= UNIVERSE_MIN_ADTV).fillna(False) & ~halted
    for nm, s in (("V1", v1), ("V2", v2), ("V3", v3), ("V5", v5), ("V6", v6)):
        p[nm] = s.astype("int8")
    p["VETO"] = (p["V1"] * p["V2"] * p["V3"] * p["V5"] * p["V6"]).astype("int8")
    if not quiet:
        rows = []
        for nm, need, why in VETO_DEFS:
            blocked = int((p[nm] == 0).sum())
            rows.append([nm, why, f"{blocked:,}", f"{100*blocked/max(len(p),1):.2f}%",
                         "활성" if _stage_ok(need, stage) else "단계 미도달"])
        LOG.table(rows, ["ID", "조건", "차단 행수", "차단률", "상태"], ["c", "l", "r", "r", "c"],
                  title="거부권 발동 감사 (§8.2 · C6 — 이진이며 상쇄 없음)")
        LOG.info("※ V5 는 자본잠식만 판정합니다. 감사의견 비적정·관리종목 지정은 공시목록 제목만으로 "
                 "알 수 없고 별도 소스가 필요합니다 — 없는 것을 있는 척하지 않습니다. "
                 "그만큼 V5 는 사양보다 약합니다.")
    return p


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  하한선 (breadth floor) — "모든 축이 상위"가 아니라 "빈 축이 없을 것"
# ═══════════════════════════════════════════════════════════════════════════════════════════
def apply_breadth_floor(P: pd.DataFrame, stage: str, tps: Sequence[str],
                        floor_pct: float = BREADTH_FLOOR_PCT,
                        cell_keys: Sequence[str] = CELL_KEYS,
                        quiet: bool = False, copy: bool = True) -> Tuple[pd.DataFrame, dict]:
    """활성 센서군 각각의 셀 내 백분위 ≥ floor_pct.

    ★ 축 단위가 아니라 '군' 단위다. 7개 축 전부에 50th 를 걸면 독립 가정에서 0.8% 만
      통과해 하한선 하나가 선정을 지배한다. 그러면 R2(TP vs 나이브) 비교가 성립하지 않는다 —
      두 팔이 같은 하한선을 물려받으면 나이브 팔조차 TP 로 선별된 종목만 보게 되기 때문이다.
    ★ 군이 '활성'인지는 단계(STAGE)로 결정한다. 단계에 도달하지 않은 군은 존재하지 않는 것이지
      비어 있는 것이 아니다. 이 구분이 없으면 M0 에서 자본배분군이 없다는 이유로 전 종목이 탈락한다.
    """
    p = P.copy() if copy else P
    fb = list(cell_keys[:-1]) or list(cell_keys)
    ok = pd.Series(True, index=p.index)
    info = {"groups": [], "pass_rate": {}}
    active_groups = 0
    for gname, (members, need) in FLOOR_GROUPS.items():
        if not _stage_ok(need, stage):
            continue
        have = [m for m in members if m in p.columns and col(p, m).notna().sum() > 0]
        if not have:
            continue
        active_groups += 1
        # 군의 값 = 구성 센서들의 셀 랭크 평균. 원시값 평균이 아니다 —
        # 원시값은 단위가 제각각(일수·비율·배수)이라 평균이 의미를 갖지 않는다.
        r_members = [cell_rank(p, col(p, m), cell_keys, fb, tag=f"floor:{m}") for m in have]
        gv = pd.concat(r_members, axis=1).mean(axis=1, skipna=True)
        r = cell_rank(p, gv, cell_keys, fb, tag=f"floor:{gname}")
        # 관측이 없으면(NaN) '빈 축'이므로 탈락한다 — 이게 §8.1 의 문자 그대로의 의미다.
        g_ok = (r >= floor_pct).fillna(False)
        ok &= g_ok
        info["groups"].append(gname)
        info["pass_rate"][gname] = float(g_ok.mean())
    if active_groups == 0:
        ok = pd.Series(True, index=p.index)
    p["FLOOR"] = ok.astype("int8")
    info["n_groups"] = active_groups
    info["overall"] = float(ok.mean())
    if not quiet and active_groups:
        LOG.table([[g, f"{100*info['pass_rate'][g]:.1f}%"] for g in info["groups"]] +
                  [["── 전체 동시통과 ──", f"{100*info['overall']:.1f}%"]],
                  ["센서군", f"백분위 ≥ {floor_pct:.0%} 통과율"], ["l", "r"],
                  title=f"하한선 감사 — 활성 센서군 {active_groups}개")
        if info["overall"] < 0.02:
            LOG.warn(f"하한선 통과율이 {100*info['overall']:.2f}% 로 매우 낮습니다. "
                     f"하한선 하나가 선정을 지배하면 R2(TP vs 나이브) 비교가 무의미해집니다 — "
                     f"두 팔이 같은 하한선을 물려받아 나이브 팔조차 TP 로 선별된 종목만 보기 "
                     f"때문입니다. R5 의 floor 40/50/60 절제 결과를 반드시 확인하세요.")
    return p, info
