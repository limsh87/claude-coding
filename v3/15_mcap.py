

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-G  PIT 시가총액 · 상장주식수  — 계약 C13 의 유일한 입력                                ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 없으면 C13 은 성립하지 않는다. 그리고 C13 이 깨지면 이 전략은 자기가 찾는     ║
# ║    대상을 정의상 제거한다.                                                                ║
# ║                                                                                          ║
# ║    우리가 찾는 건 "시총 800억이 8,000억이 된 기업"이다. 현재 시총으로 유니버스를 자르면    ║
# ║    그 종목은 '지금 중대형주'라서 밴드 밖이고, 2016년 시점 데이터에서도 빠진다.             ║
# ║    성공 사례가 통째로 사라지는데 예외도 경고도 나지 않는다. 우측 꼬리에 의존하는           ║
# ║    전략에서 이건 조용한 거짓 음성이고, 생존자편향과 정확히 같은 급의 사고다.                ║
# ║                                                                                          ║
# ║  소스 우선순위 (모두 실패해도 죽지 않고, 무엇을 썼는지 반드시 표로 보고한다):              ║
# ║    ① pykrx get_market_cap_by_ticker(date)   진짜 PIT. 시총·상장주식수 둘 다.  ★1순위       ║
# ║    ② 네이버 금융 시가총액 페이지            현재값만 → 과거 복원 불가. 보강용             ║
# ║    ③ FDR StockListing 의 Stocks(상장주식수) 를 과거로 고정 + 과거 종가                     ║
# ║       → ★근사다. 유증·액면분할·감자를 반영하지 못한다. 편향 방향을 아래에 명시한다.        ║
# ║    ④ 20일 평균거래대금 랭크 (최후)          규모가 아니라 유동성이다. 판정에 명시한다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MCAP_COLS = ["code", "month", "mcap", "shares", "mcap_src"]


def _mcap_pykrx_month(d: pd.Timestamp, bd: Optional[str] = None) -> Optional[pd.DataFrame]:
    """특정 월말의 전 종목 시총·상장주식수. KRXG 게이트로 직렬 호출한다.

    ★ bd(영업일)를 **밖에서 받는다**. 실측 실패 사례:
      pykrx.get_nearest_business_day_in_a_week() 는 내부적으로 '지수 OHLCV' API 를 친다.
      그 API 가 막히면 `IndexError` 가 나고, 여기서 매달 None 이 되어
      ① pykrx PIT 시총 0.0% → ④ 거래대금 대리 100% 로 떨어진다.
      즉 C13(PIT 유니버스)이 조용히 폐기되는데 예외는 한 줄도 안 뜬다.
      우리는 이미 일봉 패널에서 '그 달에 실제로 거래가 체결된 마지막 날'을 알고 있다.
      영업일 달력을 남에게 물어볼 이유가 없다.
    """
    if pykrx_stock is None:
        return None
    if not bd:
        bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                       d.strftime("%Y%m%d"), prev=True)
    if not bd:
        return None
    bd = str(bd).replace("-", "")[:8]
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
        if t is None or len(t) == 0:
            continue
        t = t.reset_index()
        ren = {"티커": "code", "종목코드": "code", "시가총액": "mcap", "상장주식수": "shares"}
        t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
        if "code" not in t.columns:
            t = t.rename(columns={t.columns[0]: "code"})
        if "mcap" not in t.columns:
            continue
        frames.append(t[["code"] + [c for c in ("mcap", "shares") if c in t.columns]])
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out["code"] = out["code"].map(to_code6)
    out = out.dropna(subset=["code"])
    out["month"] = d
    out["mcap_src"] = "pykrx"
    for c in ("mcap", "shares"):
        if c not in out.columns:
            out[c] = np.nan
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 시총 0/음수는 데이터 오류다. 랭크에 넣으면 그 종목이 최하위를 차지해 밴드를 밀어낸다.
    out.loc[~(out["mcap"] > 0), "mcap"] = np.nan
    return out[MCAP_COLS]


def naver_shares_snapshot() -> pd.Series:
    """네이버 금융 '시가총액' 목록에서 전 종목 상장주식수를 한 번에 긁는다.

    현재값이라 PIT 가 아니다. 오직 ③ 역투영의 '씨앗'으로만 쓴다 — pykrx 가 막혀
    상장주식수를 한 건도 못 얻었을 때, 시총 자리에 거래대금(유동성)을 넣는 것보다는
    '주식수 × 과거 종가'가 규모의 대리로서 훨씬 낫기 때문이다.
    페이지당 50종목 · 시장당 약 20~30페이지 → 총 60회 미만의 요청으로 끝난다.
    """
    cached = VAULT.get_table("naver_shares_snapshot", scope="shared")
    if cached is not None and len(cached):
        c = cached.copy()
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["code"])
        LOG.info(f"공용 캐시에서 상장주식수 스냅샷 {len(c):,}종목 재사용")
        return pd.to_numeric(c.set_index("code")["shares"], errors="coerce").dropna()

    rows: List[tuple] = []
    for sosok in (0, 1):                       # 0=코스피 1=코스닥
        empty_streak = 0
        for page in range(1, 45):
            html = http_get("https://finance.naver.com/sise/sise_market_sum.naver",
                            source="naver_mcap", params={"sosok": sosok, "page": page})
            sp = soup_of(html)
            tb = sp.find("table", class_="type_2") if sp else None
            if tb is None:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                continue
            heads = [th.get_text(strip=True) for th in tb.find_all("th")]
            try:
                j_sh = heads.index("상장주식수")
            except ValueError:
                j_sh = -1
            got = 0
            for tr in tb.find_all("tr"):
                a = tr.find("a", href=True)
                if not a or "code=" not in a["href"]:
                    continue
                code = to_code6(a["href"].split("code=")[-1][:6])
                tds = [td.get_text(strip=True).replace(",", "") for td in tr.find_all("td")]
                if not code or j_sh < 0 or j_sh >= len(tds):
                    continue
                try:
                    sh = float(tds[j_sh]) * 1000.0        # 네이버 표기는 '천주'
                except ValueError:
                    continue
                if sh > 0:
                    rows.append((code, sh)); got += 1
            empty_streak = 0 if got else empty_streak + 1
            if empty_streak >= 2:
                break

    if not rows:
        LOG.warn("네이버 상장주식수 스냅샷이 비었습니다 — 역투영 폴백을 쓸 수 없습니다.")
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["code", "shares"]).drop_duplicates("code", keep="first")
    VAULT.put_table("naver_shares_snapshot", df, scope="shared", domain="universe",
                    source="finance.naver.com/sise/sise_market_sum",
                    extra={"note": "현재 상장주식수 스냅샷 — PIT 아님. 역투영 근사 전용"})
    LOG.ok(f"네이버 상장주식수 스냅샷 {len(df):,}종목 확보 (공용 인덱스 저장)")
    return pd.to_numeric(df.set_index("code")["shares"], errors="coerce").dropna()


def fetch_pit_marketcap(months: pd.DatetimeIndex, px_monthly: pd.DataFrame,
                        sec: pd.DataFrame) -> pd.DataFrame:
    """월말 격자의 PIT 시가총액. 공용 인덱스에 저장 — 다른 전략이 그대로 재사용한다."""
    cached = VAULT.get_table("krx_marketcap_monthly", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["month"] = as_ts_series(cached["month"])
        cached["code"] = cached["code"].map(to_code6)
        cached = cached.dropna(subset=["month", "code"])
        have = set(cached["month"].dt.strftime("%Y-%m-%d"))
        frames.append(cached)
        LOG.info(f"공용 캐시에서 PIT 시가총액 {len(cached):,}행 재사용 ({len(have)}개 월)")

    todo = [m for m in months if m.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 시총 미수집 {len(todo)}개월을 건너뜁니다.")
        todo = []

    # ★ 영업일 달력을 '가격 패널이 실제로 관측한 마지막 거래일'에서 만든다.
    #   지수 API 가 막혀도 이 경로는 절대 막히지 않는다 (이미 손에 든 데이터니까).
    bd_map: Dict[pd.Timestamp, str] = {}
    if "signal_date" in px_monthly.columns:
        try:
            g = px_monthly.dropna(subset=["signal_date"]).copy()
            g["month"] = as_ts_series(g["month"])
            g["signal_date"] = as_ts_series(g["signal_date"])
            bd_map = {m: d.strftime("%Y%m%d")
                      for m, d in g.groupby("month")["signal_date"].max().items()}
            LOG.info(f"영업일 달력을 가격 패널에서 직접 구성 ({len(bd_map)}개월) — "
                     f"pykrx 지수 API 의존 제거")
        except Exception as e:                                            # noqa
            LOG.warn(f"패널에서 영업일 추출 실패({type(e).__name__}) — pykrx 달력으로 폴백합니다.")

    got_new = False
    if todo and pykrx_stock is not None:
        KRXG.warmup()
        LOG.info(f"PIT 시가총액 {len(todo)}개월 수집 (직렬 · 월당 2호출)")
        bad_streak = 0
        for d in tqdm(todo, desc="PIT 시가총액", ncols=88, leave=False):
            t = _mcap_pykrx_month(d, bd=bd_map.get(d))
            if t is not None and len(t):
                frames.append(t)
                got_new = True
                bad_streak = 0
            else:
                bad_streak += 1
                if bad_streak >= 6:
                    LOG.warn("시총 조회가 연속 6개월 비었습니다 — KRX 세션이 끊겼거나 "
                             "차단된 상태입니다. 수집을 중단하고 근사 경로로 폴백합니다.")
                    break
    elif todo:
        LOG.warn("pykrx 가 없어 PIT 시가총액을 직접 받을 수 없습니다 — 근사 경로로 폴백합니다.")

    M = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=MCAP_COLS)
    if len(M):
        M = (M.sort_values(["code", "month"])
               .drop_duplicates(["code", "month"], keep="last").reset_index(drop=True))
    if got_new:
        out = M.copy()
        out["month"] = out["month"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_monthly", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "PIT 시가총액·상장주식수 월말 격자 — 전 전략 공용"})

    # ── 폴백: 상장주식수를 과거로 고정하고 과거 종가를 곱한다 ────────────────────────────
    #   ★ 이건 근사다. 편향 방향을 정확히 알고 써야 한다:
    #     · 그 뒤 유상증자/무상증자를 한 기업 → 과거 시총이 과대 추정된다 → 랭크가 높아진다
    #       → U-MID(251~1400) 밴드에서 위로 밀려나 '빠질' 수 있다.
    #     · 자사주 소각/감자를 한 기업 → 과거 시총이 과소 추정된다 → 아래로 밀린다.
    #   즉 자본 이벤트가 있었던 기업의 유니버스 편입이 체계적으로 틀어진다. 그런데 이 전략의
    #   TP_P1/TP_P2 가 바로 자본배분 신호이므로, 하필 가장 중요한 종목군에서 틀린다.
    #   → 근사를 쓸 수밖에 없더라도 그 사실과 커버리지를 반드시 표로 남긴다.
    px = px_monthly[["code", "month", "close", "adv20"]].copy()
    px["month"] = as_ts_series(px["month"])
    base = px.merge(M, on=["code", "month"], how="left")
    n_true = int(base["mcap"].notna().sum())

    need = base["mcap"].isna()
    if need.any():
        shares_now = pd.Series(dtype="float64")
        if "shares" in M.columns and len(M):
            # 우리가 실제로 관측한 상장주식수 중 '가장 이른' 것을 그 이전 구간에 역투영한다.
            # 가장 최근 것을 쓰면 그동안의 증자를 전부 과거에 소급하게 되어 편향이 커진다.
            first_obs = (M.dropna(subset=["shares"]).sort_values("month")
                          .drop_duplicates("code", keep="first").set_index("code")["shares"])
            shares_now = first_obs
        if shares_now.empty and "shares" in sec.columns:
            shares_now = pd.to_numeric(sec.dropna(subset=["shares"]).set_index("code")["shares"],
                                       errors="coerce").dropna()
        if shares_now.empty and RUN_MODE != "CACHED":
            # pykrx 도 마스터도 주식수를 못 줬다. 여기서 포기하면 전 구간이 ④ 거래대금 대리가
            # 되어 '규모 밴드'가 '유동성 밴드'로 바뀐다 — C13 의 의미 자체가 달라진다.
            LOG.warn("상장주식수를 한 건도 확보하지 못했습니다 — 네이버 스냅샷으로 역투영 씨앗을 "
                     "만듭니다. (현재값 기준 근사이며 자본이벤트를 반영하지 못합니다)")
            try:
                shares_now = naver_shares_snapshot()
            except Exception as e:                                        # noqa
                LOG.warn(f"네이버 상장주식수 스냅샷 실패({type(e).__name__}: {e})")
        if not shares_now.empty:
            est = base.loc[need, "code"].map(shares_now) * base.loc[need, "close"]
            base.loc[need, "mcap"] = est.to_numpy()
            base.loc[need & base["mcap"].notna(), "mcap_src"] = "shares_backproj"

    n_approx = int((base["mcap_src"].astype(str) == "shares_backproj").sum())
    still = base["mcap"].isna()
    n_proxy = int(still.sum())
    if still.any():
        # 최후 폴백: 거래대금 랭크를 규모의 대리로 쓴다. 규모가 아니라 유동성이므로
        # 판정에 반드시 명시한다. (거래대금은 유동성 필터와 상관되어 밴드가 좁아진다)
        base.loc[still, "mcap"] = base.loc[still, "adv20"]
        base.loc[still & base["mcap"].notna(), "mcap_src"] = "adv_proxy"

    tot = max(len(base), 1)
    LOG.table([["① pykrx PIT 시총 (정확)", f"{n_true:,}", f"{100*n_true/tot:.1f}%", "✔ C13 충족"],
               ["③ 상장주식수 역투영 (근사)", f"{n_approx:,}", f"{100*n_approx/tot:.1f}%",
                "⚠ 자본이벤트 미반영 — 증자기업 과대/감자기업 과소"],
               ["④ 거래대금 대리 (최후)", f"{n_proxy:,}", f"{100*n_proxy/tot:.1f}%",
                "❗ 규모가 아니라 유동성 — 밴드 의미가 달라짐"],
               ["시총 미상", f"{int(base['mcap'].isna().sum()):,}",
                f"{100*int(base['mcap'].isna().sum())/tot:.1f}%", "유니버스에서 제외됨"]],
              ["시총 소스", "행수", "비중", "판정"], ["l", "r", "r", "l"],
              title="PIT 시가총액 소스 감사 (계약 C13) — 근사 비중이 크면 유니버스 정의가 흔들립니다")

    if n_true / tot < 0.60:
        LOG.warn(f"정확한 PIT 시총 비중이 {100*n_true/tot:.0f}% 에 그칩니다. "
                 f"KRX 마켓플레이스 ID/PW 를 입력하면 pykrx 경로가 열려 크게 개선됩니다. "
                 f"근사 구간에서는 U-MID 밴드 편입이 자본이벤트 기업에서 체계적으로 틀어집니다 — "
                 f"하필 TP_P1/TP_P2 가 겨냥하는 종목군입니다. 결과 해석 시 반드시 감안하세요.")
        PIPE.note("WARN: PIT 시총 근사 비중 과다 — C13 부분 충족")

    out = base[["code", "month", "mcap", "mcap_src"]].copy()
    out["mcap_src"] = out["mcap_src"].fillna("none").astype(str)
    PIPE.io("OUT", "MEM", "pit_marketcap", out, source="pykrx+approx")
    return downcast(out)
