
# ────────────────────────────────────────────────────────────────────────────────────────
#  L2-C  스코어 조립 — DART_SCORE (§6.5) / FINAL_SCORE (§7.2)
#  ★ 두 가지 '탈락시키지 않기' 규칙이 이 파일의 핵심이다:
#  ★ 어블레이션은 전부 이 함수 하나를 통과한다. 기준선과 절제팔이 서로 다른 계산경로를 타면
# ────────────────────────────────────────────────────────────────────────────────────────

AXIS_B_LAYERS = (("D1", "D1_SCORE", ARC_W_D1),
                 ("D2", "D2_SCORE", ARC_W_D2),
                 ("D3", "D3_SCORE", ARC_W_D3))

def _score_axis_a(P: pd.DataFrame, use_raw: bool = False,
                  neutral_fill: bool = True) -> Tuple[pd.Series, pd.Series]:
    """축 A 표준화 점수와 '원래 결측이었는지' 마스크.
    ★ 축 A **단독** 팔(A1/A2 어블레이션)에서는 0 으로 채우면 안 된다. 그 팔에는
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
    """지정된 축만으로 DART_SCORE / FINAL_SCORE / FINAL_RANK 를 재조립한다."""
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
        #   (상세 근거는 커밋 로그 참조)
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
