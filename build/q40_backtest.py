

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  분기 리밸런싱 백테스트 엔진 + 비용 모델 (§7.4, §8.1)                                  ║
# ║                                                                                          ║
# ║  · 체결 = 리밸런싱일 이후 첫 거래일 '시가'. 신호는 그 전 거래일 종가까지만(§4).             ║
# ║  · 상장폐지: 정리매매 체결가가 있으면 반영, 없으면 −100%. 누락 처리 금지(§3.4).             ║
# ║  · 비용: 증권거래세(연도별 이력) + 실측 스프레드(Corwin-Schultz) + 수수료 + 제곱근 충격.     ║
# ║    비용 전/후를 반드시 병기한다. 비용 전만 보고하는 것은 금지(§8.1).                        ║
# ║  · 연율화 계수는 분기이므로 √4 다. √12 를 쓰면 변동성이 1.7배 과대계상된다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율(매도 시, 농특세 포함 총부담). 10년간 여섯 번 바뀌었다 —
# 한 개의 평균율로 뭉개면 초기 구간 비용이 과소, 말기 구간이 과대계상된다.
QVF_TAX_SCHEDULE = [
    ("2016-01-01", 0.0030),
    ("2019-06-03", 0.0025),
    ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020),
    ("2024-01-01", 0.0018),
    ("2025-01-01", 0.0015),
]
Q_PER_YEAR = 4.0

# 상장폐지 맵을 전역으로 한 번만 세팅한다. 실험·민감도에서 백테스트를 수십 번 부르는데
# 호출부마다 인자로 넘기게 하면 한 군데만 빠뜨려도 그 실험만 조용히 생존자편향을 갖는다.
QVF_DELIST_MAP: Dict[str, Any] = {}


def set_delist_map(m: Optional[Dict[str, Any]]):
    globals()["QVF_DELIST_MAP"] = {str(k): as_ts(v) for k, v in dict(m or {}).items()
                                   if pd.notna(as_ts(v))}
    LOG.debug(f"상장폐지 맵 등록: {len(QVF_DELIST_MAP):,}종목")


def qvf_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = QVF_TAX_SCHEDULE[0][1]
    for d, r in QVF_TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return float(rate)


def build_exec_prices(cal: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """(code, rebal) → 체결가(체결일 시가) · 체결일. 시가가 없으면 같은 날 종가로 폴백한다."""
    px = px_daily[["code", "date", "open", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"])
    px["px_exec"] = pd.to_numeric(px["open"], errors="coerce")
    px["px_exec"] = px["px_exec"].where(px["px_exec"] > 0,
                                        pd.to_numeric(px["close"], errors="coerce"))
    px = px.dropna(subset=["px_exec"]).sort_values("date", kind="stable")

    codes = sorted(px["code"].unique())
    L = (cal[["rebal", "exec_date"]].assign(_k=1)
         .merge(pd.DataFrame({"code": codes, "_k": 1}), on="_k").drop(columns="_k"))
    # ★ 결합키의 '단위'를 왼쪽에서도 못박는다. 오른쪽(px)은 as_ts_series 를 통과해 ns 인데
    #   왼쪽 캘린더가 다른 경로로 만들어지면 pandas 3.x 가 MergeError 로 죽는다(as_ts 주석 참조).
    L["exec_date"] = as_ts_series(L["exec_date"])
    L = L.sort_values("exec_date", kind="stable")
    R = px[["code", "date", "px_exec"]].rename(columns={"date": "px_date"})
    # ★ forward 방향이다. 체결일에 거래가 없으면 '그 이후 첫 거래일'에 체결된 것으로 본다.
    #   backward 로 붙이면 체결일 이전 가격으로 사게 되어 미래를 모르고도 유리해진다.
    M = pd.merge_asof(L, R, left_on="exec_date", right_on="px_date", by="code",
                      direction="forward",
                      tolerance=pd.Timedelta(days=int(EXEC_FILL_MAX_LAG_DAYS)))
    out = M.dropna(subset=["px_exec"])[["code", "rebal", "exec_date", "px_date", "px_exec"]]
    out = out.rename(columns={"px_date": "fill_date"})
    # ★ 체결 지연 분포를 감사표로 남긴다. tolerance 를 길게 잡으면 '정지 후 재개장 가격'을
    #   진입가로 쓰게 되는데(정지 복권의 유리한 쪽만 취함), 그 건수를 숨기면 안 된다.
    lag = (as_ts_series(out["fill_date"]) - as_ts_series(out["exec_date"])).dt.days
    LOG.table([["당일 체결(lag=0)", f"{int((lag == 0).sum()):,}"],
               ["1~2일 지연", f"{int(lag.between(1, 2).sum()):,}"],
               [f"3~{int(EXEC_FILL_MAX_LAG_DAYS)}일 지연", f"{int(lag.between(3, int(EXEC_FILL_MAX_LAG_DAYS)).sum()):,}"],
               [f"체결 불가(>{int(EXEC_FILL_MAX_LAG_DAYS)}일 · 매수 후보에서 탈락)",
                f"{int(len(M) - len(out)):,}"]],
              ["체결 지연", "건수"], ["l", "r"],
              title=f"체결가 확보 상황 (허용 지연 {int(EXEC_FILL_MAX_LAG_DAYS)}일) — "
                    f"지연 체결은 정지 해제가를 진입가로 쓰게 되므로 짧게 제한한다")
    PIPE.io("OUT", "MEM", "exec_prices", out)
    return downcast_q(out)


def build_forward_returns(execp: pd.DataFrame, cal: pd.DataFrame,
                          delist: Dict[str, pd.Timestamp],
                          px_daily: pd.DataFrame) -> pd.DataFrame:
    """(code, rebal) → 다음 리밸런싱까지의 보유수익률.

    ★ 분기가 건너뛰어졌을 때 shift(-1) 이 두 분기 뒤 가격을 끌어와 '한 분기 수익'으로
      둔갑시키는 사고를 인접성 검사로 막는다.
    ★ 보유기간 중 상장폐지: 정리매매 체결가가 있으면 그 가격, 없으면 −100%.
    """
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    rank = {t: i for i, t in enumerate(reb)}
    E = execp.copy()
    # ★ code 가 category 이면 .map() 결과도 category 가 되고, 그 값이 날짜일 때
    #   `ld >= dl - 15일` 비교가 TypeError 로 죽는다. 그 코드가 하필 '보유 중 상장폐지'
    #   처리라 생존자편향 방어가 통째로 무너진다(계약 Q3 가 이 경로를 잡는다).
    E["code"] = E["code"].astype(str)
    E["rebal"] = as_ts_series(E["rebal"])
    E["_r"] = E["rebal"].map(rank)
    E = E.dropna(subset=["_r"]).sort_values(["code", "_r"], kind="stable")
    g = E.groupby("code", observed=True)
    E["px_next"] = g["px_exec"].shift(-1)
    E["r_next"] = g["_r"].shift(-1)
    adjacent = (E["r_next"] - E["_r"]) == 1
    # ★★ float64 로 못박는다 ★★
    #   px_exec 는 downcast_q 로 float32 다. 그대로 두면 fwd_ret 도 float32 가 되는데,
    #   아래 상장폐지 처리에서 넣는 정리매매 수익률은 float64(종가 소스에 따라 달라짐)라
    #   pandas 3.x 의 엄격한 setitem 이 `TypeError: Invalid value '[-0.9]' for dtype
    #   'float32'` 로 죽는다. 하필 그 경로가 생존자편향 방어라 계약 Q3 가 통째로 실패하고
    #   L0.CONTRACT 에서 실행이 멈춘다(pandas 2.x 에서는 조용히 캐스팅돼 드러나지 않았다).
    E["fwd_ret"] = (E["px_next"] / E["px_exec"] - 1.0).where(adjacent).astype("float64")
    E["exit_kind"] = np.where(E["fwd_ret"].notna(), "normal", "missing")

    # 마지막 리밸런싱은 다음 시점이 없으므로 수익률이 없는 것이 정상이다.
    last_r = max(rank.values()) if rank else -1
    E.loc[E["_r"] == last_r, "exit_kind"] = "terminal"

    # ── 상장폐지 처리 ──────────────────────────────────────────────────────────────────
    px = px_daily[["code", "date", "close"]].copy()
    px["code"] = px["code"].astype(str)
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"])
    last_px = (px.sort_values("date").groupby("code", observed=True)
                 .agg(last_date=("date", "max"), last_close=("close", "last")))
    # ★ 보유구간의 오른쪽 끝은 '다음 체결일'이다. 다음 명목일로 잡으면 그 사이 1~3일의
    #   이음매에서 폐지된 종목이 창 밖으로 새어 −100% 대신 0% 가 된다(분기마다 반복).
    _exec_of = {as_ts(r.rebal): as_ts(r.exec_date) for r in cal.itertuples(index=False)}
    nxt_rebal = {t: (_exec_of.get(reb[i + 1]) if i + 1 < len(reb) else None)
                 for i, t in enumerate(reb)}

    n_liq = n_zero = n_halt = 0
    if delist:
        dl = {str(k): as_ts(v) for k, v in dict(delist).items()}
        E["_dl"] = as_ts_series(E["code"].map(dl))
        E["_nxt"] = as_ts_series(E["rebal"].map(nxt_rebal))
        in_window = (E["_dl"].notna() & E["_nxt"].notna() &
                     (E["_dl"] > E["exec_date"]) & (E["_dl"] <= E["_nxt"]))
        # ★★ 창 밖 폐지의 뒷문 ★★
        #   종목이 분기 중간에 거래정지되면 (a) 다음 신호일에 종가가 없어 U-1000 에서
        #   탈락하고, (b) 다음 체결일에도 체결가가 없어 fwd_ret 이 결측("missing")이 되며,
        #   (c) 실제 폐지일은 대개 몇 달 뒤라 위 in_window 를 벗어난다. 세 조건이 겹치면
        #   그 포지션은 어느 분기에서도 −100% 를 받지 못하고 '정확히 0%'로 청산된다.
        #   한국 실질심사 정지가 통상 수개월인 이상 이건 예외가 아니라 표준 경로다.
        #   판정 기준을 "창 안에서 폐지됐는가"가 아니라 "이 포지션이 다시 체결 가능해지지
        #   않았고 결국 폐지되었는가"로 바꾼다.
        stuck = (E["_dl"].notna() & (E["_dl"] > E["exec_date"]) &
                 (E["exit_kind"] == "missing") & (~in_window))
        n_halt = int(stuck.sum())
        resolve = in_window | stuck
        if resolve.any():
            ld = as_ts_series(E.loc[resolve, "code"].map(last_px["last_date"]))
            lc = pd.to_numeric(E.loc[resolve, "code"].map(last_px["last_close"]),
                               errors="coerce")
            # ── 정리매매가로 인정하는 조건 (§3.4) ──────────────────────────────────────
            #  ① 가격 시계열이 폐지 시점까지 실제로 닿아 있을 것 (닿지 않으면 그냥 데이터가
            #     끊긴 것이지 정리매매를 관측한 게 아니다)
            #  ② 그 가격이 진입가 대비 '손실'일 것.
            #  ★ ②가 없으면 치명적이다: 소스가 폐지 직전에 종목을 드롭하면 마지막 정상가가
            #    청산가로 둔갑해 '상장폐지 = 0% 손실'이 된다. 그게 정확히 생존자편향의
            #    재유입이며, 계약 Q3 가 이 경로를 잡아낸다. 애매하면 규정대로 −100% 로
            #    보수적으로 처리한다(성과를 과소평가하는 방향 = 편향 통제상 옳은 방향).
            entry = E.loc[resolve, "px_exec"]
            reach = ld.notna() & (ld >= E.loc[resolve, "_dl"] - pd.Timedelta(days=7))
            liq_ret = lc / entry - 1.0
            captured = reach & liq_ret.notna() & (liq_ret < 0)
            E.loc[resolve, "fwd_ret"] = liq_ret.where(captured, -1.0).astype("float64")
            kind = np.where(captured.to_numpy(), "liquidation", "delist_-100%")
            # 정지 후 창 밖 폐지는 별도 유형으로 남겨 감사표에서 바로 보이게 한다.
            kind = np.where(stuck[resolve].to_numpy() & ~captured.to_numpy(),
                            "halt_then_delist", kind)
            E.loc[resolve, "exit_kind"] = kind
            n_liq = int(captured.sum())
            n_zero = int((~captured).sum())
        E = E.drop(columns=[c for c in ("_dl", "_nxt") if c in E.columns])

    kinds = Counter(E["exit_kind"].astype(str))
    LOG.table([[k, f"{v:,}"] for k, v in kinds.most_common()],
              ["보유 종료 유형", "건수"], ["l", "r"],
              title="보유기간 종료 유형 — 상장폐지가 누락되면 그대로 생존자편향이 된다")
    if n_liq or n_zero:
        LOG.info(f"보유 중 상장폐지 {n_liq + n_zero:,}건 — 정리매매가 반영 {n_liq:,}건 / "
                 f"가격 부재로 −100% 처리 {n_zero:,}건 (§3.4 규정대로 누락 처리하지 않음)")
    if n_halt:
        LOG.info(f"  그중 {n_halt:,}건은 '거래정지 → 다음 분기 이후 폐지'라 예전 규칙(같은 분기 "
                 f"창 안 폐지만 인정)에서는 0% 로 새던 건이다 — halt_then_delist 로 계상했다.")
    return E[["code", "rebal", "exec_date", "px_exec", "fwd_ret", "exit_kind"]]


# ── 가중 ────────────────────────────────────────────────────────────────────────────────────
def compute_weights(sub: pd.DataFrame, scheme: str = "equal") -> pd.Series:
    n = len(sub)
    if n == 0:
        return pd.Series(dtype="float64")
    if scheme == "invvol":
        v = pd.to_numeric(sub.get("vol_d"), errors="coerce")
        # ★ 변동성 결측 종목을 떨어뜨리면 '변동성을 못 구한 종목' = 대개 신규·저유동 종목이
        #   조용히 빠져 선택편향이 된다. 횡단면 중앙값으로 대체하고 개수를 로그로 남긴다.
        med = float(v.median()) if v.notna().any() else np.nan
        v = v.where(v > 0)
        v = v.fillna(med if np.isfinite(med) and med > 0 else 0.02)
        w = 1.0 / v
        w = w / w.sum() if float(w.sum()) > 0 else pd.Series(1.0 / n, index=sub.index)
        return w
    return pd.Series(1.0 / n, index=sub.index)


def run_qbacktest(P: pd.DataFrame, cal: pd.DataFrame, sel_col: str, fwd: pd.DataFrame,
                  scheme: str = "equal", apply_costs: bool = True,
                  label: str = "QVF", delist: Optional[Dict[str, pd.Timestamp]] = None,
                  cost_model: Optional[str] = None) -> dict:
    """분기 리밸런싱 롱온리 백테스트. 비용 전/후를 동시에 산출한다.

    cost_model: "spec"(기본, §8.1 문언 = 증권거래세 + 스프레드/2) | "extended"(+수수료+충격)
    """
    cost_model = str(cost_model or QVF_COST_MODEL).lower()
    need = ["code", "rebal", sel_col]
    d = P[[c for c in P.columns if c in set(need) | {"adtv", "cs_spread", "vol_d", "market",
                                                     "mktcap", "score1_V", "score1_VQ",
                                                     "score1_VQF"}]].copy()
    # ★★ 유동성/스프레드 조회표는 '선정 종목'이 아니라 패널 전체에서 만들어야 한다 ★★
    #   예전에는 선정 종목만 남긴 프레임에서 dict 를 만들었다. 그러면 이번 분기에 '팔고
    #   나가는' 종목은 ADTV 조회가 100% 실패하고, 폴백 `part=1.0`(참여율 100%) 이 걸려
    #   매도 레그 전체가 IMPACT_K = 1000bp 를 맞았다. 총비용의 9할이 이 한 줄이었고,
    #   세 변형 전부를 비용 차감 후 음의 CAGR 로 밀어 §10.4 폐기조건 ①을 자동 발동시켰다.
    _LQ = P[[c for c in ("code", "rebal", "adtv", "cs_spread") if c in P.columns]].copy()
    _LQ["code"] = _LQ["code"].astype(str)
    _LQ["rebal"] = as_ts_series(_LQ["rebal"])
    _adv_by_t: Dict[Any, Dict[str, float]] = {}
    _spr_by_t: Dict[Any, Dict[str, float]] = {}
    for _t, _g in _LQ.groupby("rebal", observed=True):
        _cd = _g["code"].to_numpy()
        if "adtv" in _g.columns:
            _adv_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["adtv"], errors="coerce")))
        if "cs_spread" in _g.columns:
            _spr_by_t[as_ts(_t)] = dict(zip(_cd, pd.to_numeric(_g["cs_spread"], errors="coerce")))
    del _LQ
    # 패널에서 아예 사라진 종목(유니버스 이탈)을 위한 '마지막으로 알던 값' 누적표.
    _known_adv: Dict[str, float] = {}
    _known_spr: Dict[str, float] = {}
    n_adv_fallback = 0
    d = d[d[sel_col].fillna(False).astype(bool)]
    F = fwd.set_index(["code", "rebal"])["fwd_ret"] if len(fwd) else pd.Series(dtype="float64")

    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    # ★ 보유구간은 [체결일, 다음 체결일) 이지 [명목일, 다음 명목일) 이 아니다.
    #   3/1 은 삼일절이라 결코 거래일이 아니고 6/1·12/1 도 주말에 자주 걸린다. 두 구간의
    #   차이(1~3일의 이음매)에서 폐지된 종목은 '창 밖'으로 판정되어 −100% 대신 0% 가 된다.
    #   즉 분기마다 며칠씩 생존자편향이 새는 뒷문이 열려 있었다.
    exec_of = {as_ts(r.rebal): as_ts(r.exec_date) for r in cal.itertuples(index=False)}
    exec_next = {t: (exec_of.get(reb[i + 1]) if i + 1 < len(reb) else None)
                 for i, t in enumerate(reb)}
    dlmap = ({str(k): as_ts(v) for k, v in dict(delist).items()} if delist
             else dict(QVF_DELIST_MAP))
    prev_w: Dict[str, float] = {}
    rows, holds = [], []
    n_missing, n_forced_delist, n_empty_q = 0, 0, 0
    for t in reb:
        # 이번 분기 조회표를 갱신한다(패널에 있는 종목은 최신값, 없으면 마지막으로 알던 값).
        _cur_adv = _adv_by_t.get(as_ts(t), {})
        _cur_spr = _spr_by_t.get(as_ts(t), {})
        for _c, _v in _cur_adv.items():
            if _v is not None and np.isfinite(_v) and _v > 0:
                _known_adv[_c] = float(_v)
        for _c, _v in _cur_spr.items():
            if _v is not None and np.isfinite(_v) and _v > 0:
                _known_spr[_c] = float(_v)
        _med_adv = float(np.median(list(_cur_adv.values()))) if _cur_adv else np.nan
        if not np.isfinite(_med_adv) or _med_adv <= 0:
            # ★ 상수 이름이 틀려 있었다(ADTV_MIN_KRW 는 이 파일 어디에도 정의돼 있지 않다).
            #   그 분기 ADTV 가 하나도 없으면 NameError 로 백테스트가 죽는다 — 함수 안이라
            #   조립기의 '정의 전 참조' 검사(최상위만 본다)도 잡지 못했다. §3.2 의 유동성
            #   하한이 의도한 값이다.
            _med_adv = float(MIN_ADTV_KRW)
        sub = d[d["rebal"] == t].copy()
        if sub.empty:
            # ★ 3-A 통과 종목이 0 인 분기는 설계상 발생할 수 있는 정상 결과다(사전등록).
            #   그런데 예전 코드는 회전율만 기록하고 비용 0, 수익 0 으로 넘겼다 — 전량 청산을
            #   공짜로 처리하고, 그 분기 보유분의 실제 수익을 통째로 증발시킨 것이다.
            turn0 = float(sum(abs(v) for v in prev_w.values()))
            g0 = 0.0
            nx0 = exec_next.get(t)
            te0 = exec_of.get(t, t)
            for c, w in prev_w.items():
                fr = F.get((c, t), np.nan) if len(F) else np.nan
                fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan
                if not np.isfinite(fr):
                    dl = dlmap.get(str(c))
                    # 창 안 폐지만 인정하면 '정지 → 다음 분기 이후 폐지'가 0% 로 샌다.
                    # 체결 불가 + 이후 폐지 확인이면 규정대로 −100%(마지막 분기는 제외).
                    fr = -1.0 if (dl is not None and nx0 is not None and as_ts(dl) > te0) else 0.0
                g0 += w * fr
            c0 = 0.0
            if apply_costs and prev_w:
                tax0 = qvf_sell_tax(te0)
                _fee0 = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0
                for c, w in prev_w.items():
                    sp0 = _known_spr.get(str(c), np.nan)
                    sp0 = (float(sp0) if sp0 is not None and np.isfinite(sp0)
                           else SLIPPAGE_FLOOR_BPS / 1e4)
                    sp0 = float(np.clip(sp0, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                    imp0 = 0.0
                    if cost_model == "extended":
                        adv0 = _cur_adv.get(str(c), _known_adv.get(str(c), np.nan))
                        adv0 = float(adv0) if adv0 is not None and np.isfinite(adv0) and adv0 > 0 else _med_adv
                        imp0 = IMPACT_K * math.sqrt(min(1.0, abs(w) * ACCOUNT_KRW / adv0))
                    c0 += abs(w) * (_fee0 + sp0 / 2.0 + imp0 + tax0)
            n_empty_q += 1
            rows.append({"rebal": t, "ret": g0 - c0, "ret_gross": g0, "n": 0,
                         "turnover": turn0, "cost": c0})
            prev_w = {}
            continue
        sub["w"] = compute_weights(sub, scheme)
        w_new = dict(zip(sub["code"].astype(str), sub["w"].astype(float)))

        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0))
                   for c in set(w_new) | set(prev_w))
        cost = 0.0
        if apply_costs:
            # ★ 세율 구간 경계가 2019-06-03 인데 2019-06-01 은 토요일이라 그 분기 체결일이
            #   정확히 2019-06-03 이다. 명목일로 조회하면 그 한 분기만 구세율(0.30%)이 적용돼
            #   매도 레그 전체에 20bp 를 과다계상한다. 체결일 기준으로 조회한다.
            tax = qvf_sell_tax(exec_of.get(t, t))
            _fee = (COMMISSION_BPS / 1e4) if cost_model == "extended" else 0.0
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                # 매수·매도 모두 패널 전체 조회표를 쓴다(매도 종목도 값을 갖는다).
                sp = _cur_spr.get(c, _known_spr.get(c, np.nan))
                sp = float(sp) if sp is not None and np.isfinite(sp) else SLIPPAGE_FLOOR_BPS / 1e4
                sp = float(np.clip(sp, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                impact = 0.0
                if cost_model == "extended":
                    adv = _cur_adv.get(c, _known_adv.get(c, np.nan))
                    if adv is None or not np.isfinite(adv) or adv <= 0:
                        # 폴백은 '참여율 100%'(=충격 상수 1000bp) 가 아니라 그 분기 횡단면
                        # 중앙 ADTV 다. 조회 실패를 최악의 유동성으로 등치시키면 안 된다.
                        adv = _med_adv
                        n_adv_fallback += 1
                    part = min(1.0, (abs(dw) * ACCOUNT_KRW) / float(adv))
                    impact = IMPACT_K * math.sqrt(part)
                one_way = _fee + sp / 2.0 + impact
                cost += abs(dw) * one_way + (abs(dw) * tax if dw < 0 else 0.0)

        gross = 0.0
        nx = exec_next.get(t)
        t_exec = exec_of.get(t, t)
        for c, w in w_new.items():
            fr = F.get((c, t), np.nan) if len(F) else np.nan
            fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan
            if not np.isfinite(fr):
                # ★ 체결가가 없어 수익률을 못 만든 종목을 일괄 0% 로 두면, 폐지 직전에
                #   소스에서 사라지는 종목이 전부 '무손실'이 된다 — 생존자편향의 뒷문이다.
                #   ★ 판정 기준은 "이번 보유창 안에서 폐지"가 아니라 "다시 체결 가능해지지
                #     않았고(=fr 결측) 이후 폐지되었다"이다. 정지가 수개월 이어지다 폐지되는
                #     한국 실질심사 경로가 예전 창 조건을 표준적으로 빠져나갔다.
                dl = dlmap.get(str(c))
                if dl is not None and nx is not None and as_ts(dl) > t_exec:
                    fr = -1.0
                    n_forced_delist += 1
                else:
                    fr = 0.0                  # 마지막 분기 등 — 임의 가정 금지
                    n_missing += 1
            gross += w * fr
            holds.append({"rebal": t, "code": c, "weight": w, "ret": fr})
        rows.append({"rebal": t, "ret": gross - cost, "ret_gross": gross, "n": len(w_new),
                     "turnover": turn, "cost": cost})
        prev_w = w_new

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
        R["equity_gross"] = (1.0 + R["ret_gross"].fillna(0)).cumprod()
    if n_forced_delist or n_missing or n_empty_q:
        LOG.info(f"[{label}] 체결가 결측 보정 — 보유구간 내 폐지 확인 {n_forced_delist:,}건은 "
                 f"−100% · 그 외 {n_missing:,}건은 0%(마지막 분기 등) · "
                 f"선정 0종목 분기 {n_empty_q:,}회(청산비용 부과·보유수익 반영)")
        if n_missing > max(20, 0.02 * len(holds)):
            LOG.warn(f"0% 로 처리된 보유가 {n_missing:,}건으로 많습니다. 폐지·거래정지가 "
                     f"'무손실'로 새고 있을 수 있습니다 — 위 '보유 종료 유형' 표와 함께 보세요.")
    if n_adv_fallback:
        LOG.debug(f"[{label}] ADTV 조회 실패 {n_adv_fallback:,}건 — 그 분기 중앙 ADTV 로 대체")
    return {"returns": R, "holdings": pd.DataFrame(holds), "label": label, "scheme": scheme,
            "cost_model": cost_model,
            "n_forced_delist": n_forced_delist, "n_missing": n_missing}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def qperf_stats(R: pd.DataFrame, ret_col: str = "ret", rf: float = 0.0) -> dict:
    if R is None or not len(R):
        return {}
    r = pd.to_numeric(R[ret_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / Q_PER_YEAR
    cagr = eq[-1] ** (1.0 / years) - 1.0 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(Q_PER_YEAR) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(Q_PER_YEAR) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if n else np.nan
    mx, cur = 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "분기수": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "분기평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(분기)": int(mx),
        "평균종목수": float(pd.to_numeric(R["n"], errors="coerce").mean()) if "n" in R else np.nan,
        "분기평균회전율": float(pd.to_numeric(R["turnover"], errors="coerce").mean())
        if "turnover" in R else np.nan,
        "분기평균비용": float(pd.to_numeric(R["cost"], errors="coerce").mean())
        if "cost" in R else np.nan,
    }


def rank_ic(P: pd.DataFrame, score_col: str, fwd: pd.DataFrame,
            pool_col: Optional[str] = None) -> Tuple[float, float, int]:
    """스코어와 다음 분기 수익률의 스피어만 순위상관. (평균 IC, IC-IR, 시점수)"""
    if score_col not in P.columns or fwd is None or not len(fwd):
        return (np.nan, np.nan, 0)
    d = P[["code", "rebal", score_col] + ([pool_col] if pool_col and pool_col in P.columns else [])]
    if pool_col and pool_col in P.columns:
        d = d[d[pool_col].fillna(False).astype(bool)]
    d = d.merge(fwd[["code", "rebal", "fwd_ret"]], on=["code", "rebal"], how="left")
    d = d.dropna(subset=[score_col, "fwd_ret"])
    ics = []
    for _t, g in d.groupby("rebal", observed=True):
        if len(g) < 10:
            continue
        c = g[score_col].rank().corr(g["fwd_ret"].rank())
        if np.isfinite(c):
            ics.append(float(c))
    if not ics:
        return (np.nan, np.nan, 0)
    m = float(np.mean(ics))
    s = float(np.std(ics, ddof=1)) if len(ics) > 1 else np.nan
    return (m, (m / s) if s and np.isfinite(s) and s > 0 else np.nan, len(ics))


def qvf_benchmarks(cal: pd.DataFrame, px_daily: pd.DataFrame) -> Dict[str, pd.Series]:
    """분기 벤치마크. 지수를 못 받으면 유니버스 동일가중 수익률로 대체하고 그 사실을 명시한다."""
    out: Dict[str, pd.Series] = {}
    reb = list(as_ts_series(cal["rebal"]))
    ex = list(as_ts_series(cal["exec_date"]))
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, (min(ex) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                   (max(ex) + pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or not len(d):
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        cl = d[["date", "close"]].dropna().sort_values("date", kind="stable")
        L = pd.DataFrame({"exec_date": ex}).sort_values("exec_date", kind="stable")
        M = pd.merge_asof(L, cl.rename(columns={"date": "px_date"}),
                          left_on="exec_date", right_on="px_date", direction="forward",
                          tolerance=pd.Timedelta(days=15))
        s = pd.Series(M["close"].to_numpy(), index=pd.Index(reb, name="rebal")).pct_change(fill_method=None).shift(-1)
        out[name] = s
    if not out:
        LOG.warn("지수 벤치마크를 받지 못했습니다 — 벤치마크 비교표는 생략됩니다.")
    return out
