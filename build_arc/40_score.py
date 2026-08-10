

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  스코어 조립 — DART_SCORE (§6.5) / FINAL_SCORE (§7.2)                                ║
# ║                                                                                          ║
# ║  DART_SCORE = 0.40·D1 + 0.40·D2 + 0.20·D3      (사전등록 가중치. 튜닝 금지)                ║
# ║  FINAL_SCORE = 0.5·z(ΔTONE_resid) + 0.5·z(DART_SCORE)                                     ║
# ║                                                                                          ║
# ║  ★ 두 가지 '탈락시키지 않기' 규칙이 이 파일의 핵심이다:                                     ║
# ║    ① 축 A 결측(리포트 없음) → ΔTONE_resid = 0(중립)으로 두고 DART_SCORE 만으로 평가.        ║
# ║       탈락시키지 않는다. 이것이 v2.0 에서 축 B 를 강화한 이유다(§7.2).                       ║
# ║    ② D1 결측 → D1 가중치를 D2·D3 에 '비례 재배분'. 종목을 탈락시키지 않는다(§6.5).           ║
# ║    A10 / A11 계약검정이 이 두 규칙을 실제 데이터로 검사한다.                                 ║
# ║                                                                                          ║
# ║  ★ 어블레이션은 전부 이 함수 하나를 통과한다. 기준선과 절제팔이 서로 다른 계산경로를 타면    ║
# ║    Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를 재게 된다(이전 프로젝트의 사고).  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

AXIS_B_LAYERS = (("D1", "D1_SCORE", ARC_W_D1),
                 ("D2", "D2_SCORE", ARC_W_D2),
                 ("D3", "D3_SCORE", ARC_W_D3))

SCORE_OUT_COLS = ["DART_SCORE", "AXIS_A_Z", "FINAL_SCORE", "FINAL_RANK", "n_axes_b"]


def _score_axis_a(P: pd.DataFrame, use_raw: bool = False,
                  neutral_fill: bool = True) -> Tuple[pd.Series, pd.Series]:
    """축 A 표준화 점수와 '원래 결측이었는지' 마스크.

    §7.2 는 "축 A 결측 종목은 ΔTONE_resid = 0(중립)으로 두고 DART_SCORE 만으로 평가,
    탈락시키지 말 것" 을 지시한다. 그래서 축 B 가 함께 있을 때만 0 으로 채운다.

    ★ 축 A **단독** 팔(A1/A2 어블레이션)에서는 0 으로 채우면 안 된다. 그 팔에는
      DART_SCORE 가 없으므로 '중립 0' 이 곧 '전 종목 동점'이 되고, 리포트가 없는 종목이
      코드 순서로 편입된다. 그러면 A1 은 축 A 의 순기여가 아니라 '동점 처리 규칙'을
      측정하게 된다. 단독 팔에서는 결측을 결측으로 남겨 편입 대상에서 빼야 한다.
    """
    src = "dTONE" if use_raw else "dTONE_resid"
    if src not in P.columns:
        empty = pd.Series(np.nan, index=P.index, dtype="float32")
        return (empty.fillna(0.0) if neutral_fill else empty,
                pd.Series(True, index=P.index))
    z = xsec_z_arc(P, src)
    miss = z.isna()
    return ((z.fillna(0.0) if neutral_fill else z).astype("float32"), miss)


_REGROUP_MIN_N = 20


def _regroup_z(P: pd.DataFrame, v: pd.Series, gcol: str) -> pd.Series:
    """(기간 × 가용성그룹) 안에서 재표준화. 그룹이 작으면 원값을 그대로 둔다.

    ★ 이 함수의 목적은 '데이터가 몇 개 있는가'가 순위를 정하지 못하게 하는 것이다.
      축을 1개만 가진 행과 2개 가진 행은 합성 후 분산이 다르고(1.0 vs 0.71), 상위 N
      선정은 꼬리에서 일어나므로 분산이 좁은 쪽이 NaN 도 아닌 채로 구조적으로 밀린다.
    """
    x = pd.to_numeric(v, errors="coerce").astype("float64")
    key = P["asof"].astype(str) + "|" + P[gcol].astype(str)
    g = x.groupby(key, observed=True)
    n = g.transform("count")
    mu = g.transform("mean")
    sd = g.transform("std")
    ok = (n >= _REGROUP_MIN_N) & (sd > 0) & sd.notna()
    return x.where(~ok, (x - mu) / sd.where(sd > 0, 1.0))


def _score_d1_variant(P: pd.DataFrame, d1_metric: Optional[str],
                      d1_equal_weights: bool) -> pd.Series:
    """D1 점수 선택 — 기본 합성 / 지표 단독 / 섹션 균등가중 (§8.4 강건성용)."""
    if d1_metric:
        c = f"D1_SCORE_{d1_metric}"
        if c in P.columns:
            return pd.to_numeric(P[c], errors="coerce")
        LOG.warn(f"D1 지표 단독 '{d1_metric}' 컬럼이 없어 합성 D1 로 대체합니다.")
    if d1_equal_weights and "D1_SCORE_equalw" in P.columns:
        return pd.to_numeric(P["D1_SCORE_equalw"], errors="coerce")
    return pd.to_numeric(col(P, "D1_SCORE"), errors="coerce")


def assemble_final(P: pd.DataFrame,
                   use_axes: Sequence[str] = ("A", "D1", "D2", "D3"),
                   use_excl: bool = True,
                   v1_hardgate: bool = False,
                   d1_metric: Optional[str] = None,
                   d1_equal_weights: bool = False,
                   include_struct: bool = False) -> pd.DataFrame:
    """지정된 축만으로 DART_SCORE / FINAL_SCORE / FINAL_RANK 를 재조립한다.

    원본 P 를 변형하지 않는다(copy). 어블레이션·강건성은 전부 이 함수를 통과한다.

    use_axes 원소:
      "A"     ΔTONE_resid (직교화 후)
      "A_RAW" ΔTONE (직교화 전) — A2 어블레이션 전용
      "D1" / "D2" / "D3"
    v1_hardgate=True 면 ΔNONFIN>0 을 편입 조건으로 강제한다 (F4: v1.0 재현 전용).
    include_struct=True 면 STRUCT_FLAG 종목의 D1 을 되살린다 (§8.4 민감도).
    """
    Q = P.copy()
    axes = set(use_axes or ())

    # ── 축 B 합성 (§6.5 비례 재배분) ──────────────────────────────────────────────────────
    vals, wts = [], []
    for lid, cname, w in AXIS_B_LAYERS:
        if lid not in axes:
            continue
        if lid == "D1":
            v = _score_d1_variant(Q, d1_metric, d1_equal_weights)
            if include_struct and "CHANGE_composite" in Q.columns:
                # STRUCT_FLAG 로 지워둔 값을 되살릴 수는 없으므로(이미 NaN),
                # 민감도 팔에서는 '결측을 그대로 둔 채' 비교한다는 사실을 남긴다.
                PIPE.note("STRUCT 포함 팔: D1 은 이미 결측 처리된 값을 되살리지 않음")
        else:
            v = pd.to_numeric(col(Q, cname), errors="coerce")
        vals.append(v.to_numpy(dtype="float64"))
        wts.append(float(w))

    if vals:
        V = np.column_stack(vals)
        Wv = np.array(wts, dtype="float64")
        msk = np.isfinite(V)
        wm = np.where(msk, Wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        dart = np.where(ws > 0,
                        np.nansum(np.where(msk, V, 0.0) * wm, axis=1) /
                        np.where(ws > 0, ws, 1.0), np.nan)
        Q["n_axes_b"] = msk.sum(axis=1)
    else:
        dart = np.full(len(Q), np.nan)
        Q["n_axes_b"] = 0
    Q["DART_SCORE"] = dart
    # 축 B 합성값도 기간 횡단면에서 다시 표준화한다(층별 z 의 스케일이 기간마다 다르므로)
    Q["DART_SCORE"] = xsec_z_arc(Q, "DART_SCORE")

    # ── 축 A ──────────────────────────────────────────────────────────────────────────────
    has_a = ("A" in axes) or ("A_RAW" in axes)
    has_b = bool(vals)
    if has_a:
        az, a_miss = _score_axis_a(Q, use_raw=("A_RAW" in axes), neutral_fill=has_b)
        Q["AXIS_A_Z"] = az
    else:
        Q["AXIS_A_Z"] = np.nan
        a_miss = pd.Series(True, index=Q.index)

    # ── 최종 합성 (§7.2) ──────────────────────────────────────────────────────────────────
    if has_a and has_b:
        b = pd.to_numeric(Q["DART_SCORE"], errors="coerce")
        az64 = Q["AXIS_A_Z"].astype("float64")
        fin = (ARC_W_AXIS_A * az64 + ARC_W_AXIS_B * b)
        # ★ 가중치 재배분은 **양방향 대칭**이어야 한다.
        #   예전에는 '축 B 결측 → 축 A 에 100% 재배분'만 있고 반대가 없었다. 축 A 결측 행은
        #   AXIS_A_Z 를 0 으로 채운 채 축 B 가중치가 0.5 로 남아, FINAL 의 **분산이 절반으로
        #   줄었다**(0.5·B vs 0.5·A+0.5·B). 상위 N 선정은 꼬리에서 일어나므로 분산이 좁은
        #   쪽은 NaN 이 아닌데도 구조적으로 밀린다 — 커버리지 50% 에서는 리포트 없는 종목이
        #   상위 30 에 사실상 한 종목도 들어가지 못했다. §7.2 '탈락시키지 말 것'의 실질 위반.
        #   A10 은 점수가 NaN 이 아닌지만 봐서 이 붕괴를 잡지 못했다.
        fin = fin.where(b.notna(), az64)                 # 축 B 결측 → 축 A 단독
        fin = fin.where(~a_miss, b)                      # 축 A 결측 → 축 B 단독 (대칭)
        # ★ 두 축이 모두 결측인 행은 '중립 0' 이 아니라 '정보 없음' 이다. 0 으로 두면
        #   아무 근거도 없는 종목이 중간 순위를 차지하고, 표본이 얇은 분기에는 그 종목들이
        #   실제로 편입된다. 명세 §7.2 의 '중립 0' 은 '축 B 가 있을 때' 의 규정이다.
        fin = fin.where(~(a_miss & b.isna()))
        # ★ 재배분만으로는 부족하다. 축이 1개인 행은 sd≈1, 2개인 행은 sd≈0.71 이라
        #   이번에는 반대 방향으로 기운다. 가용성 그룹별로 기간 안에서 재표준화해
        #   '데이터가 몇 개 있는가'가 순위를 정하지 못하게 한다. 그룹이 너무 작으면
        #   재표준화가 오히려 잡음이므로 그때는 손대지 않는다.
        Q["_avail"] = np.where(a_miss.to_numpy(), "B", np.where(b.isna().to_numpy(), "A", "AB"))
        fin = _regroup_z(Q, fin, "_avail")
        Q = Q.drop(columns=["_avail"])
    elif has_a:
        fin = Q["AXIS_A_Z"].astype("float64")
    elif has_b:
        fin = pd.to_numeric(Q["DART_SCORE"], errors="coerce")
    else:
        # 무정보 팔 (B4 배제플래그 단독) — 전 종목 동일 점수
        fin = pd.Series(0.0, index=Q.index, dtype="float64")
    Q["FINAL_SCORE"] = fin.astype("float32")

    # ── 편입 조건 ─────────────────────────────────────────────────────────────────────────
    if use_excl:
        ex = pd.to_numeric(col(Q, "EXCLUDE"), errors="coerce").fillna(0.0) > 0
        Q.loc[ex, "FINAL_SCORE"] = np.nan          # 점수 무관 즉시 제외 (§6.4)
    if v1_hardgate:
        # ★ F4(v1.0 재현) 전용. 이 게이트는 v2.0 본선에서 폐기된 규칙이다.
        nf = pd.to_numeric(col(Q, "DELTA_NONFIN"), errors="coerce")
        Q.loc[~(nf > 0).fillna(False), "FINAL_SCORE"] = np.nan

    Q["FINAL_RANK"] = (Q.groupby("asof", observed=True)["FINAL_SCORE"]
                        .rank(pct=True, method="average").astype("float32"))
    return Q


def report_score_summary(P: pd.DataFrame) -> None:
    """스코어 구성 요약 — 각 축이 실제로 몇 %의 종목에 값을 주고 있는가."""
    LOG.banner("스코어 조립 요약", "DART_SCORE = 0.40·D1 + 0.40·D2 + 0.20·D3 · "
                                   "FINAL = 0.5·축A + 0.5·축B (사전등록 가중치)")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    rows = []
    for lab, c in (("축 A ΔTONE_resid", "dTONE_resid"), ("축 A 원신호 ΔTONE", "dTONE"),
                   ("D1_SCORE", "D1_SCORE"), ("D2_SCORE", "D2_SCORE"),
                   ("D3_SCORE", "D3_SCORE"), ("DART_SCORE", "DART_SCORE"),
                   ("FINAL_SCORE", "FINAL_SCORE")):
        v = pd.to_numeric(col(P, c), errors="coerce")
        n = int(v.notna().sum())
        rows.append([lab, f"{n:,}", f"{100*n/max(len(P),1):.1f}%",
                     f"{float(v.mean()):+.3f}" if n else "—",
                     f"{float(v.std()):.3f}" if n > 1 else "—"])
    LOG.table(rows, ["신호", "관측", "커버리지", "평균", "표준편차"],
              ["l", "r", "r", "r", "r"])
    if "n_axes_b" in P.columns:
        cnt = P["n_axes_b"].value_counts().sort_index()
        LOG.table([[f"{int(k)}개 층", f"{int(v):,}", f"{100*v/max(len(P),1):.1f}%"]
                   for k, v in cnt.items()],
                  ["축 B 유효 층수", "행수", "비중"], ["l", "r", "r"],
                  title="축 B 층 가용성 — 0층이면 그 행은 축 A 단독으로 평가됩니다(§6.5 재배분)")
    n_a_missing = int((pd.to_numeric(col(P, "has_axis_a"), errors="coerce").fillna(0) == 0).sum())
    LOG.info(f"축 A 결측 {n_a_missing:,}행 ({100*n_a_missing/max(len(P),1):.1f}%) — "
             f"§7.2 에 따라 중립(0)으로 두고 DART_SCORE 로 평가합니다. 탈락시키지 않습니다.")
