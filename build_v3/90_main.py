# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  각 단계는 PIPE.stage 안에서만 돈다. 실패하면 자동으로 다음이 출력된다:                     ║
# ║    실패 지점(스테이지·계층·경과) / 직전 입출력 스냅샷 / 한글 진단 힌트 / 트레이스백          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _rehearsal_hook_v3(G: dict, sec: pd.DataFrame, corps: Sequence[str],
                       months: pd.DatetimeIndex) -> None:
    """v3 전용 수집·계산 함수를 리허설에 태운다 (가짜 네트워크가 물려 있는 안쪽)."""
    _rh("fetch_emp_status(v3 확장)",
        lambda: fetch_emp_status(list(corps)[:3], [2019, 2020]), expect_rows=False,
        note="empSttus 확장 파서 — 소계행 제거·단위 역추정 포함")
    _rh("build_emp_sensors + C15",
        lambda: build_emp_sensors(pd.DataFrame({
            "corp_code": ["Z1"] * 3, "bsns_year": [2018, 2019, 2020],
            "rcept_dt": pd.to_datetime(["2019-03-20", "2020-03-20", "2021-03-20"]),
            "employees": [500.0, 600.0, 610.0], "regular": [450.0, 540.0, 550.0],
            "payroll_total": [3.5e10, 4.4e10, 4.5e10],
            "avg_salary": [7e7, 7.1e7, 7.2e7], "src_flag": ["detail"] * 3})),
        note="연도 프레임 센서 + C15 게이트")


REHEARSAL_HOOKS.append(_rehearsal_hook_v3)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Tier-2 전체재무제표 수집 범위 — 4시간 계약(§12-6)을 지키는 지점
#
#  이 함수가 없으면 잡 수는 |상장·폐지 전 종목| × |연도| × |보고서| 로 곱해진다.
#  3,981사 × 13년 × 4분기 = 207,012회. DART 일일한도 19,000 기준 11일이다.
#  좁히는 근거는 두 가지뿐이고, 둘 다 결과를 바꾸지 않는다:
#    ① 한 번도 U-MID 대역(투자가능)에 들지 못한 종목의 전체재무제표는 어떤 달에도
#       포트폴리오에 들어갈 수 없다 → 스코어에 쓰이지 않는다.
#    ② 백테스트 시작연도 −DART_FS_WARMUP_Y 이전 회계연도는 TTM·전년대비에도 안 쓰인다.
#  ①의 U-MID 판정은 **가격패널만으로** 내려진다(20일 평균거래대금 랭크) — 재무를 보지
#  않으므로 순환참조가 없고, 미래 재무를 미리 들여다보는 일도 없다.
# ══════════════════════════════════════════════════════════════════════════════════════════
def dart_fs_scope_v3(ctx: dict, all_corps: Sequence[str], quiet: bool = False
                     ) -> Tuple[List[str], List[int], List[str]]:
    """(수집대상 corp_code, 연도, 우선순위 corp_code) 를 돌려준다.

    quiet=True 면 로그를 찍지 않는다 — 직원현황 단계가 우선순위만 빌려 쓸 때 쓴다."""
    y0 = as_ts(BACKTEST_START).year - int(DART_FS_WARMUP_Y)
    years = list(range(y0, as_ts(BACKTEST_END).year + 1))
    corps = [str(c) for c in all_corps]
    prio: List[str] = []
    try:
        pm = ctx["panel"]["monthly"]
        adv = col(pm, "adv20")
        rank = adv.groupby(pm["month"], observed=True).rank(ascending=False, method="first")
        in_band = rank.between(UMID_RANK_LO, UMID_RANK_HI) & (adv >= MIN_ADV_KRW)
        # 우선순위: 'U-MID 대역에 머문 달 수'가 많은 종목부터. 유동성 1등이 아니라
        # **실제로 담길 확률이 높은 종목**부터 채우는 것이 백테스트 커버리지에 직결된다.
        months_in = (pm.loc[in_band.fillna(False), "code"].value_counts())
        c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
               .set_index("code")["corp_code"].astype(str).to_dict())
        prio = [c2c[c] for c in months_in.index if c in c2c]
        if DART_FS_UNIVERSE_ONLY and prio:
            keep = set(prio)
            dropped = len(corps) - len([c for c in corps if c in keep])
            corps = [c for c in corps if c in keep]
            if not quiet:
                LOG.info(f"Tier-2 수집대상을 U-MID 대역 경험 종목 {len(corps):,}사로 좁힙니다 "
                         f"(제외 {dropped:,}사 — 전 기간 한 번도 투자가능 대역에 들지 못해 "
                         f"어떤 달에도 편입될 수 없는 종목입니다).")
    except Exception as e:                                          # noqa
        if not quiet:
            LOG.warn(f"U-MID 기반 Tier-2 범위 축소 실패({type(e).__name__}) — 전 종목으로 진행합니다.")
    n_reprt = 1 if DART_FS_FREQ == "annual" else 4
    est = len(corps) * len(years) * n_reprt
    cap = est if DART_FS_MAX_CALLS is None else min(est, int(DART_FS_MAX_CALLS))
    if not quiet:
        LOG.info(f"Tier-2 전체재무제표 계획: {len(corps):,}사 × {len(years)}년 × "
                 f"{n_reprt}보고서 = 최대 {est:,}건 → 이번 실행 상한 {cap:,}건 "
                 f"(≈{cap/5/60:.0f}분). 나머지는 Tier-1 주요계정으로 대체하고 재실행 시 이어받습니다.")
    if DART_FS_MAX_CALLS == 0:
        if not quiet:
            LOG.warn("DART_FS_MAX_CALLS=0 — Tier-2 를 건너뜁니다. 재고·매출채권·영업CF 가 결측이므로 "
                 "TP_I1/TP_I2(회계품질) 가 비활성화됩니다.")
        return [], years, prio
    return corps, years, prio


def offer_download_v3(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f                 # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def downcast_floats(P: pd.DataFrame) -> pd.DataFrame:
    """float64 → float32 만. object→category 변환은 하지 않는다.

    ★ 코어의 downcast() 는 저카디널리티 object 를 category 로 바꾼다. 그러면 강건성 팔에서
      P.copy() 후 merge 할 때 category vs object dtype 불일치로 매칭이 0건이 되거나
      dtype 오류가 난다. 스코어링 패널은 여러 번 복제·재계산되므로 이 위험을 피한다.
    """
    for c in P.columns:
        if P[c].dtype.kind == "f":
            P[c] = pd.to_numeric(P[c], downcast="float")
    return P


def _flush_on_abort_v3():
    """중단 경로에서도 원장과 진단표를 반드시 남긴다.

    ★ 예전엔 DBUDGET.close() 와 report_http() 가 정상 종료 경로에만 있었다. 그래서
      ① 중단된 실행이 오늘 쓴 DART 호출이 파일에 기록되지 않아 다음 실행이 없는 예산을
         있다고 믿고 또 실패하고,
      ② '이번 실행에서 DART 요청을 한 건도 못 보냈다'를 보여줄 유일한 표(HTTP 감사)가
         하필 그게 가장 필요한 순간에 출력되지 않았다.
      중단은 진단 정보가 가장 필요한 순간이다. 그때 정보를 끊으면 안 된다.
    """
    try:
        if DBUDGET:
            DBUDGET.close()
    except Exception:
        pass
    try:
        report_http()
    except Exception:
        pass
    why = None
    try:
        why = dart_halt_reason()
    except Exception:
        pass
    if why:
        LOG.warn(f"참고 — 이번 실행의 DART 상태: {why}. "
                 f"위 표에서 dart 요청 수가 0 이면 '데이터가 없어서'가 아니라 "
                 f"'요청을 못 보내서'입니다. 한도는 매일 자정(KST)에 초기화됩니다.")
    try:
        VAULT.flush()
    except Exception:
        pass


def _enrich_research_bounded(nv: pd.DataFrame, sec: Optional[pd.DataFrame]) -> pd.DataFrame:
    """네이버 상세 보강을 시간 상한 안에서, 담을 수 있는 종목부터 수행한다."""
    if nv is None or nv.empty or not RESEARCH_ENRICH_MAX_MIN:
        if nv is not None and len(nv) and not RESEARCH_ENRICH_MAX_MIN:
            LOG.info("RESEARCH_ENRICH_MAX_MIN=0 — 상세 보강을 생략합니다. "
                     "목표주가는 한경 경로에서만 채워집니다(실측 수율이 0 이었던 단계입니다).")
        return nv if nv is not None else pd.DataFrame()
    obs = float(RATE_LIMIT_QPS.get("naver", 3.0)) or 3.0
    cap = max(0, int(RESEARCH_ENRICH_MAX_MIN * 60 * obs))
    if "code" in nv.columns and sec is not None and len(sec):
        try:
            # 담을 수 있는 종목(=거래대금이 있는 종목)을 앞으로 당긴다. 정렬만 바꾸므로
            # 상한에 걸려 잘려도 남는 것이 '쓸모 있는 쪽'이 된다.
            live = set(sec.loc[sec["delisting_date"].isna(), "code"].astype(str)) \
                if "delisting_date" in sec.columns else set(sec["code"].astype(str))
            key = (~nv["code"].astype(str).isin(live)).astype(int)
            nv = nv.assign(_pri=key).sort_values(
                ["_pri"] + (["date"] if "date" in nv.columns else []),
                ascending=[True] + ([False] if "date" in nv.columns else [])
            ).drop(columns=["_pri"]).reset_index(drop=True)
        except Exception:
            pass
    LOG.info(f"네이버 상세 보강 상한 {cap:,}건 (≈{RESEARCH_ENRICH_MAX_MIN}분 · "
             f"실측 {obs:.1f}건/초). 상장 종목·최신순으로 채웁니다. "
             f"이 단계는 U축 d1 보조이며 알파(한계임금)와 무관합니다.")
    return naver_enrich_detail(nv, limit=cap)


def emp_pairs_needed_v3(ctx: dict, years: Sequence[int]) -> Optional[set]:
    """실제로 스코어에 쓰이는 **(회사, 사업연도) 조합만** 골라낸다.

    ★ 왜 이게 핵심인가. 예전 격자는 데카르트 곱이었다 — 3,366사 × 12년 = 40,392건.
      그런데 2020~2022년에만 U-MID 대역에 있었던 회사의 FY2014 직원현황은 **어떤 달의
      스코어에도 들어가지 않는다.** 담을 수 없는 시점의 데이터이기 때문이다.
      실제로 필요한 건 '그 회사가 담길 수 있었던 해' + 차분용 직전 1년뿐이다.
      이렇게 뽑으면 보통 1/3 이하로 줄어 **키 하나로 하루에 끝난다.**

    ★ PIT 안전성: 대역 판정은 가격패널(20일 평균거래대금 랭크)만 쓴다. 재무·직원현황을
      보지 않으므로 순환참조가 없고, '나중에 좋아진 회사'를 미리 고르는 일도 없다.
      또 여기서 고르는 것은 **수집 대상**이지 스코어 입력이 아니다 — 덜 받으면 결측이
      될 뿐 신호가 유리하게 바뀌지 않는다.
    """
    try:
        pm = ctx["panel"]["monthly"]
        adv = col(pm, "adv20")
        rank = adv.groupby(pm["month"], observed=True).rank(ascending=False, method="first")
        in_band = (rank.between(UMID_RANK_LO, UMID_RANK_HI) & (adv >= MIN_ADV_KRW)).fillna(False)
        B = pm.loc[in_band, ["code", "month"]].copy()
        if B.empty:
            return None
        c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
               .set_index("code")["corp_code"].astype(str).to_dict())
        B["corp_code"] = B["code"].astype(str).map(c2c)
        B = B.dropna(subset=["corp_code"])
        if B.empty:
            return None
        # 월 m 에 쓰이는 신호는 그 시점에 **알 수 있었던** 사업보고서다. 3~4월 접수를
        # 감안해 보수적으로 m 의 2년 전까지 열어 둔다(덜 받아 결측이 되는 쪽이 안전하다).
        ymin, ymax = min(years), max(years)
        need: set = set()
        yy = B["month"].dt.year.to_numpy()
        cc = B["corp_code"].to_numpy()
        for back in (1, 2, 3):        # 신호연도 후보 + C15 차분용 직전연도
            for c, y in zip(cc, yy - back):
                if ymin <= y <= ymax:
                    need.add((str(c), int(y)))
        if not need:
            return None
        full = len(set(cc)) * len(years)
        LOG.ok(f"직원현황 수집 격자를 **필요한 조합만**으로 좁혔습니다 — "
               f"{len(need):,}건 (데카르트 곱이면 {full:,}건, {100*len(need)/max(full,1):.0f}%). "
               f"담길 수 없었던 해의 직원현황은 어떤 달의 스코어에도 쓰이지 않습니다.")
        return need
    except Exception as e:                                          # noqa
        LOG.warn(f"직원현황 조합 축소 실패({type(e).__name__}) — 전체 격자로 진행합니다.")
        return None


def announce_budget_v3():
    """수집을 시작하기 전에 '이번 실행이 몇 분짜리인지'를 먼저 못박아 보여준다.

    ★ 이 표가 없으면 곱셈으로 폭발한 잡 수가 tqdm ETA 로만 드러난다 — 이미 돌기 시작한
      뒤다. 4시간 계약(§12-6)은 사후 판정이 아니라 **사전 상한**이어야 한다.
    """
    fs_cap, emp_cap = DART_FS_MAX_CALLS, EMP_MAX_CALLS
    used = DBUDGET.n if DBUDGET else 0
    n_keys = len(DBUDGET.keys) if DBUDGET and DBUDGET.keys else 1
    room = DART_DAILY_LIMIT * n_keys
    left = max(0, room - used)
    _n = lambda v: "무제한" if v is None else f"{int(v):,}"
    _m = lambda v, qps: "며칠" if v is None else f"{int(v)/qps/60:.0f}"
    rows = [
        ["L1.UNI  종목마스터·스냅샷", "-", "10", "pykrx/FDR/KIND"],
        ["L1.PX   일봉·거래대금", "-", "40", "실패종목 30일 음성캐시 → 재실행은 대폭 단축"],
        ["L1.EMP  직원현황(empSttus)", _n(emp_cap), _m(emp_cap, 8.0),
         "① 알파 원천 — 예산을 먼저 배정 · EMP_MAX_CALLS"],
        ["L1.DART Tier-1 주요계정(배치)", "≈2,100", "5", "100사/호출 — 전 종목 전 연도"],
        ["L1.DART Tier-2 전체재무제표", _n(fs_cap), _m(fs_cap, 5.0),
         f"② 남는 예산으로 · {DART_FS_FREQ} · DART_FS_MAX_CALLS"],
        ["L2~R    피처·백테스트·강건성", "-", "35", "네트워크 없음"],
    ]
    LOG.table(rows, ["단계", "DART 호출 상한", "예상(분)", "비고"], ["l", "r", "r", "l"],
              title="이번 실행의 수집 예산 (§10 · 총 예산 153분 / 킬 기준 4시간)")
    plan = sum(int(v) for v in (emp_cap, fs_cap) if v is not None) + 2100
    LOG.info(f"DART 키 {n_keys}개 · 하루 한도 {room:,}(키당 {DART_DAILY_LIMIT:,}) · "
             f"오늘 사용 추정 {used:,} · 잔여 추정 {left:,} → 이번 실행 계획 {plan:,}건.\n"
             f"     ※ 이 잔여값은 **추정치입니다.** 실제 잔여는 서버만 알기에, 추정이 0 이어도 "
             f"호출을 막지 않습니다 — 서버가 020(한도초과)으로 거부한 키만 오늘 접습니다.\n"
             f"     ※ 부족하면 opendart.fss.or.kr 에서 키를 더 발급(무료·즉시)해 "
             f"DART_API_KEYS 에 추가하세요. 한도가 키 개수만큼 곱해집니다.")
    if fs_cap is None or emp_cap is None:
        LOG.warn("호출 상한이 None 인 단계가 있습니다 — 콜드빌드는 며칠이 걸리며 §12-6 의 "
                 "4시간 계약 밖입니다. 4시간 안에 끝내려면 숫자를 넣으세요 "
                 "(권장: EMP_MAX_CALLS=14000, DART_FS_MAX_CALLS=12000).")
    if plan > left > 0:
        LOG.warn(f"계획 호출({plan:,})이 오늘 잔여 한도({left:,})를 넘습니다 — 우선순위 상위부터 "
                 f"채우고 한도에서 멈춥니다. 커버리지는 재실행할 때마다 올라갑니다.")
    return preflight_dart_v3()


def preflight_dart_v3() -> str:
    """이번 실행에서 DART 로 무엇을 할 수 있는지 **수집 시작 전에** 확정한다.

    ★ 왜 필요한가. 직전 실행은 0.35초 시점에 이미 '잔여 0'을 알고 있었는데도 그대로
      진행해, 16분 30초짜리 가격 수집을 끝낸 뒤 CANARY 에서 죽었다. 사용자는 17분을
      쓰고 아무 산출물도 받지 못했다. 알 수 있었던 사실로 나중에 죽는 것은 설계 결함이다.

    반환 "LIVE"(정상 수집) / "CACHE_ONLY"(캐시로 진행) / "BLOCKED"(진행 불가)
    """
    halt = dart_halt_reason()
    if not halt:
        return "LIVE"

    # ★★ 테이블은 서로 대체재가 아니다. ★★
    #   이 전략의 알파는 오직 한계임금(dart_employees_ext)이고, 재무 두 테이블은 **보조**다.
    #   예전 판정은 셋을 합산해 total>0 이면 진행했다. 그래서 재무 146만 행이 있고
    #   직원현황이 0행인 상태를 '캐시 충분'으로 읽고 27분을 태운 뒤, 정작 EMP 단계에서
    #   "3개 TP 가 모두 결측"을 선언했다. 알파가 없는 백테스트는 돌릴 이유가 없다.
    #   → 알파 필수(critical)와 보조(support)를 분리해 판정한다.
    CRITICAL = {"dart_employees_ext": "한계임금 — 이 전략의 유일한 알파 원천 (TP_N1·N2·N3)"}
    SUPPORT = {"dart_fnltt_raw": "전체재무제표 — TP_I1/I2/I4",
               "dart_multi_raw": "주요계정 — 유니버스·규모버킷·R3"}
    have = {}
    for t in list(CRITICAL) + list(SUPPORT):
        try:
            d = VAULT.get_table(t, scope="shared")
            have[t] = 0 if d is None else len(d)
        except Exception:
            have[t] = 0

    LOG.table([[t, "★알파" if t in CRITICAL else "보조", f"{have[t]:,}행",
                "사용 가능" if have[t] else "비어 있음",
                _trunc({**CRITICAL, **SUPPORT}[t], 44)]
               for t in list(CRITICAL) + list(SUPPORT)],
              ["공용 캐시 테이블", "역할", "보유", "이번 실행", "이 테이블이 없으면"],
              ["l", "c", "r", "c", "l"],
              title=f"DART 사전점검 — 지금 신규 수집 불가: {halt}")

    dead_alpha = [t for t in CRITICAL if not have[t]]
    if dead_alpha:
        LOG.error(
            f"★ 알파 원천이 비어 있습니다 — {dead_alpha} · {halt}\n"
            f"  재무 캐시가 {sum(have[t] for t in SUPPORT):,}행 있어도 **이 전략은 성립하지 않습니다.**\n"
            f"  한계임금 = Δ급여총액 / Δ직원수 이고, 그 입력이 empSttus 하나뿐입니다.\n"
            f"  이대로 진행하면 TP_N1·N2·N3 가 전부 결측이고, 남는 것은 CORE-D 5개 TP 뿐이라\n"
            f"  '전략 3' 이 아니라 '이름만 같은 다른 전략'의 백테스트가 나옵니다.\n"
            f"  그래서 가격·리포트 수집(실측 2시간)에 들어가기 전에 **지금** 멈춥니다.\n"
            f"\n"
            f"  선택지\n"
            f"    ① 한도 회복 후 재실행 — DART 한도는 매일 자정(KST)에 초기화됩니다.\n"
            f"       다음 실행은 EMP 에 예산을 **먼저** 배정하므로 한 번에 {EMP_MAX_CALLS:,}건까지 채웁니다.\n"
            f"    ② EMP 만 먼저 채우기 — DART_FS_MAX_CALLS=0 으로 두면 Tier-2 가 예산을 쓰지 않아\n"
            f"       직원현황이 최대 속도로 완성됩니다(권장).\n"
            f"    ③ CORE-D 단독으로 돌려보려면 REQUIRE_EMP_ALPHA=False 로 두세요.\n"
            f"       EMP-LITE 없는 축소판임이 모든 산출물에 명시됩니다.")
        if REQUIRE_EMP_ALPHA:
            raise KillCriteria(
                f"알파 원천(dart_employees_ext) 부재 · {halt} — 위 ①~③ 중 하나를 고른 뒤 재실행하세요. "
                f"2시간을 쓰고 '3개 TP 전부 결측'을 보는 대신 지금 멈춥니다.")
        LOG.warn("REQUIRE_EMP_ALPHA=False — EMP 없는 CORE-D 축소판으로 진행합니다.")
        return "CACHE_ONLY"

    if sum(have.values()) > 0:
        LOG.warn(
            f"DART 신규 수집은 못 하지만 알파 원천이 캐시에 {have['dart_employees_ext']:,}행 있어 "
            f"**캐시만으로 진행**합니다.\n"
            f"     · 캐시에 없는 (회사×연도)는 결측으로 남습니다 — 0 으로 채우지 않습니다.\n"
            f"     · CANARY 의 DART 항목은 판정 보류(SKIP)로 처리되며 킬 기준을 걸지 않습니다.\n"
            f"     · 내일(또는 한도 회복 후) 재실행하면 정확히 이 지점부터 이어받습니다.")
        return "CACHE_ONLY"

    LOG.error(
        f"DART 를 쓸 수 없고 공용 캐시도 비어 있습니다 — {halt}\n"
        f"  이 상태로 계속하면 가격 수집에만 15~40분을 쓰고 결국 재무·직원현황이 전부 비어\n"
        f"  백테스트가 성립하지 않습니다. 그래서 **지금** 멈춥니다.\n"
        f"\n"
        f"  선택지\n"
        f"    ① 한도 회복 후 재실행 — DART 한도는 매일 자정(KST)에 초기화됩니다.\n"
        f"       지금까지 받은 것은 전부 캐시에 있으므로 이어받습니다.\n"
        f"    ② 가격·유니버스만 먼저 채우기 — DART_FS_MAX_CALLS=0, EMP_MAX_CALLS=0 으로 두고\n"
        f"       실행하면 이 점검을 통과하고 가격 캐시를 미리 완성해 둘 수 있습니다.\n"
        f"    ③ RUN_MODE='CACHED' — 신규 수집 없이 캐시만으로 재현합니다.\n"
        f"    ④ 키가 문제라면 상단 DART_API_KEY 를 확인하세요 "
        f"(https://opendart.fss.or.kr → 인증키 신청/관리).")
    if (DART_FS_MAX_CALLS or 0) == 0 and (EMP_MAX_CALLS or 0) == 0:
        LOG.warn("DART 상한이 둘 다 0 이므로 애초에 DART 를 쓰지 않는 실행입니다 — 계속합니다.")
        return "CACHE_ONLY"
    raise KillCriteria(
        f"DART 사전점검 실패 — {halt} · 공용 캐시도 비어 있습니다. "
        f"위 선택지 중 하나를 고른 뒤 재실행하세요. "
        f"(17분을 쓰고 죽는 대신 지금 멈춥니다)")


# ── L1 수집 ─────────────────────────────────────────────────────────────────────────────────
def collect_all_v3(months: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}
    t_ing = time.time()
    ctx["dart_mode"] = announce_budget_v3()

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금 (다중소스 폴백 체인)", "L1", budget_s=2400):
        KRX.login()
        LOG.info(f"KRX 마켓플레이스 세션: {getattr(KRX, 'status', '미시도')}")
        # 야후 접미사를 미리 알려준다 — 모르면 종목당 .KS/.KQ 를 둘 다 때려 호출이 2배가 된다.
        try:
            _mk = ctx["sec"].dropna(subset=["code"]).drop_duplicates("code")
            _s = _mk["market"].astype(str).str.upper()
            YF_SUFFIX_HINT.update(dict(zip(
                _mk["code"].astype(str),
                np.where(_s.str.contains("KOSDAQ|KSQ|코스닥"), ".KQ", ".KS"))))
        except Exception:
            pass
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END, sec=ctx["sec"])
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L0.CANARY", "CANARY K1~K9", "L0", budget_s=2100):
        ctx["canary"] = run_canary(ctx["sec"],
                                   canary_sample(ctx["sec"], ctx["panel"]["monthly"]))

    with PIPE.stage("L1.FLOW", "기관·외국인 수급 (U축 d3)", "L1", budget_s=1200, critical=False):
        ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(), BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.EMP", "DART 직원현황(확장) · C15 한계임금", "L1",
                    budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        # ★ 상한을 '아직 제출되지 않은 회계연도' 앞에서 끊는다.
        #   사업보고서는 다음 해 3~4월에 나오므로 FY(올해)는 존재할 수 없다. 그런데 잡은
        #   연도 내림차순이라 그 없는 연도가 **큐 맨 앞**에 온다 — 3,366건(상한의 24%)을
        #   확실히 빈 응답에 먼저 태우고 나서야 쓸 수 있는 연도에 도달했다.
        _y_max = min(as_ts(BACKTEST_END).year, _dt.date.today().year) - 1
        eyears = list(range(as_ts(BACKTEST_START).year - EMP_YEARS_BACK, _y_max + 1))
        LOG.info(f"직원현황 대상 회계연도 {eyears[0]}~{eyears[-1]} "
                 f"(FY{_y_max + 1} 이후는 아직 제출 전이라 제외 — 없는 연도를 먼저 묻지 않습니다)")
        # ★ 한계임금이 이 전략의 알파 원천이므로 DART 일일예산을 **여기에 먼저** 배정한다.
        emp_corps, _, emp_prio = dart_fs_scope_v3(ctx, corps, quiet=True)
        if not (EMP_UNIVERSE_ONLY and emp_corps):
            emp_corps = corps
        pairs = emp_pairs_needed_v3(ctx, eyears)
        E = fetch_emp_status(emp_corps, eyears, priority=emp_prio,
                             max_calls=EMP_MAX_CALLS, pairs=pairs)
        ctx["emp_raw"] = E
        S = build_emp_sensors(E)
        ctx["emp_sensors"] = S
        ok, msg = test_c15(S)
        (LOG.ok if ok else LOG.error)(f"C15 자가검정 — {msg}")
        if not ok and STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"C15 계약 위반: {msg}")
        if len(S):
            PIT.register("emp_sensors",
                         pit_frame(S, "period_end", "knowledge_date", source="dart"),
                         key_cols=["corp_code"])
            VAULT.put_table("emp_sensors_annual", S, scope="shared", domain="dart",
                            source="v3 EMP-LITE 연도 센서 (C15 적용) — 타 전략 재사용 가능")

    with PIPE.stage("L1.DART", "DART 재무 · 공시목록", "L1", budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        # ── Tier-1(배치): 전 종목 · 전 연도. 100사/호출이므로 싸다. 항상 전부 받는다.
        multi = fetch_dart_multi_accounts(corps, years)
        # ── Tier-2(단건): 기업×연도×보고서로 곱해진다 → 반드시 범위를 좁히고 상한을 건다.
        fs_corps, fs_years, prio = dart_fs_scope_v3(ctx, corps)
        fs = fetch_dart_financials(fs_corps, fs_years, priority=prio,
                                   max_calls=DART_FS_MAX_CALLS, freq=DART_FS_FREQ)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        dis = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["fin"], ctx["disclosures"] = fin, dis
        # ★ 빈 경로의 tidy_financials 는 PIT 컬럼조차 없는 3열짜리 프레임을 돌려준다.
        #   그대로 register 하면 KeyError 로 죽으므로 컬럼 존재를 먼저 확인한다.
        if len(fin) and all(c in fin.columns for c in PIT_COLS):
            PIT.register("dart_financials", fin, key_cols=["corp_code"])
        else:
            LOG.warn("DART 재무가 비어 PIT 등록을 건너뜁니다 — CORE-D TP 는 전부 결측이 됩니다.")

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장 구축", "L1",
                    budget_s=3600, critical=False):
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        # ★ 캐시를 읽어 놓고도 전 구간을 다시 긁고 있었다. "재수집하지 않습니다" 로그는
        #   재수집이 **끝난 뒤에** 찍혔다(13분 낭비 × 매 실행). 가격·공시는 이미 증분인데
        #   리포트만 전량 재수집이었다 → 캐시 최신일 이후만 받는다.
        r_start = BACKTEST_START
        if cached is not None and len(cached) and "date" in cached.columns:
            try:
                _mx = as_ts_series(cached["date"]).max()
                if pd.notna(_mx):
                    # 7일 겹쳐 받는다 — 경계일에 늦게 올라온 리포트를 놓치지 않기 위함.
                    r_start = max(as_ts(BACKTEST_START),
                                  _mx - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
                    if r_start != BACKTEST_START:
                        LOG.info(f"보고서 증분 수집 — 캐시 최신 {_mx:%Y-%m-%d} 이후만 받습니다 "
                                 f"({r_start} ~). 전 구간 재수집이면 실측 13분이 매번 듭니다.")
            except Exception:
                pass
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                     "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                     "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
            if "hankyung" in RESEARCH_SOURCES:
                _hk = hankyung_collect(r_start, BACKTEST_END)
                if not len(_hk) and r_start == BACKTEST_START:
                    # ★ 전 구간을 요청했는데 0건이면 소스 장애다. 예전엔 LOG.ok 로 찍혀
                    #   초록 체크마크 뒤에 숨었다. 한경은 analyst_raw 의 **유일한** 원천이라
                    #   0건이면 애널리스트 원장 전체가 빈다.
                    LOG.error("한경컨센서스 0건 — 전 구간을 요청했는데 한 건도 받지 못했습니다. "
                              "위 'HTTP 수집 감사' 표에서 hankyung 의 403/404 건수를 확인하세요. "
                              "403 이면 차단(잠시 뒤 재시도), 404 면 엔드포인트 변경입니다. "
                              "이 소스가 비면 애널리스트 원장·목표주가가 통째로 비어 "
                              "다중소스 원장연결 감사가 무의미해집니다.")
                frames.append(_hk)
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(r_start, BACKTEST_END)
                # ★ 상세 보강은 리포트 1건당 1회 요청이라 **이 전략에서 가장 비싼 단계**다.
                #   실측: 45,000건 대상 → 20,000건만 해도 ETA 1시간 44분(2.99 it/s).
                #   §10 의 수집 총예산이 95분인데 한 보조축 보강이 그 배를 먹는다.
                #   게다가 리허설·실행 모두 '목표주가 0건 추가 확보' 였다 — 수율이 0 이다.
                #   → 시간 상한을 걸고, 그 안에서 **U-MID 대역 종목부터** 보강한다.
                #     (담을 수 없는 종목의 목표주가는 스코어에 쓰이지 않는다)
                nv = _enrich_research_bounded(nv, ctx.get("sec"))
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.ok(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                   f"(신규는 {r_start} 이후만 받았습니다)")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"]) if frames else pd.DataFrame()
        if len(rep):
            if RESEARCH_DOWNLOAD_PDF:
                rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
                if "pdf_target" in rep.columns:
                    fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                    if fill.any():
                        rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                        LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
            VAULT.put_table(f"report_master_{STRATEGY_ID}", rep, scope="private",
                            domain="research", source="strategy view")
            A, L = build_analyst_ledger(rep)
            if len(A):
                VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                                source="entity_resolution")
                VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                                source="entity_resolution")
            ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
        else:
            ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
            LOG.info("리포트 원장이 비었습니다 — U 는 스펙 §8 대로 d1·d3 로만 구성되므로 "
                     "전략 자체는 온전합니다(원장은 감사·공용재활용 목적).")

    runtime_mark("수집", time.time() - t_ing)
    return ctx


# ── L1 피처 ─────────────────────────────────────────────────────────────────────────────────
def build_features_v3(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe", dict]:
    t_l1 = time.time()
    with PIPE.stage("L1.PANEL", "피처 패널 조립 (L1 센서)", "L1", budget_s=1800):
        uni = Universe(ctx["sec"],
                       ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel_v3(uni, months, ctx["panel"]["monthly"])
        P = attach_pit_sources(P, ctx["sec"])
        P = apply_umid(P, uni)
        P = build_cells_v3(P, ctx["sec"])
        P = core_d_sensors(P, ctx)

        # §6 커버리지 감사 → 판정 → EMP 유효 시작월
        C = emp_coverage_audit(ctx.get("emp_sensors", pd.DataFrame()),
                               umid_by_year(P), umid_corps_by_year(P))
        emp_start, verdict = coverage_verdict(C)
        LOG.info(f"§6 판정 — {verdict}")
        ctx["emp_coverage"], ctx["emp_coverage_verdict"] = C, verdict

        P = emp_lite_sensors(P, emp_start)
        P = axis_U_v3(P, ctx.get("flows"))

        # ★ 대역 밖은 여기서 제외한다. TP 랭크가 '고를 수 있었던 종목' 안에서 매겨져야 한다.
        #   (센서 계산은 전 종목으로 끝낸 뒤에 자른다 — 먼저 자르면 12개월 차분이 깨진다)
        #   ★ 자르기 **직전** 패널을 보관한다. 스몰캡 비교 팔이 같은 센서 위에서 대역만
        #     바꿔 다시 자르기 위함이다. 센서를 다시 계산하지 않으므로 두 팔의 차이는
        #     오직 '규모 대역' 하나뿐임이 구조적으로 보장된다.
        ctx["panel_full"] = P.copy()
        before = len(P)
        P = P[P["u_mid"]].reset_index(drop=True)
        LOG.info(f"U-MID 유니버스로 스코어링 패널 확정 — {before:,} → {len(P):,}행")
        P = downcast_floats(P)
        LOG.ok(f"피처 패널 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 panel")
    runtime_mark("L1.센서+커버리지", time.time() - t_l1)
    return P, uni, ctx


def score_and_backtest_v3(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex,
                          uni: "Universe") -> Tuple[pd.DataFrame, dict, Callable]:
    t_l2 = time.time()
    with PIPE.stage("L2.SCORE", "TP 조립 · 거부권 · Signal", "L2", budget_s=300):
        P = build_tps(P)
        P = apply_vetoes_v3(P, ctx)
        P = assemble_score_v3(P)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        P[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "n_tp") if c in P.columns]],
                        scope="private", domain="scores", source="L2")

    def _run(pp, label="run", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else months,
                            uni, ctx["sec"], apply_costs=apply_costs, label=label)

    with PIPE.stage("L3.BT", "백테스트", "L3", budget_s=300):
        bt = _run(P, label=STRATEGY_ID)
    runtime_mark("L2+L3.백테스트", time.time() - t_l2)
    return P, bt, _run


def run_smallcap_arm_v3(ctx: dict, months: pd.DatetimeIndex, uni: "Universe",
                        bench: Dict[str, pd.Series]) -> Optional[dict]:
    """같은 신호·같은 규칙을 **규모 대역만 바꿔** 다시 돌린다.

    ★ 왜 같은 실행 안에서 도는가. 두 팔이 같은 수집물·같은 센서·같은 시드를 쓰므로
      성과 차이의 원인이 '규모 대역' 하나로 특정된다. 따로 실행하면 수집 시점이 달라
      무엇 때문에 달라졌는지 말할 수 없게 된다.
    ★ TP·셀·랭크는 **대역 안에서 다시** 매긴다. 중형주 랭크를 소형주에 그대로 쓰면
      소형주가 전부 하위권으로 몰려 아무것도 못 고른다.
    """
    if not RUN_SMALLCAP_ARM:
        return None
    PF = ctx.get("panel_full")
    if PF is None or PF.empty:
        LOG.warn("스몰캡 팔 — 전체 패널이 없어 건너뜁니다.")
        return None
    with PIPE.stage("L3.SMALL", f"스몰캡 비교 팔 (랭크 [{SMALL_RANK_LO},{SMALL_RANK_HI}])",
                    "L3", budget_s=600, critical=False):
        S = apply_umid(PF.copy(), uni, band="SMALL")
        S = S[S["u_mid"]].reset_index(drop=True)
        if S.empty or S["month"].nunique() < 24:
            LOG.warn(f"스몰캡 대역에 남는 행이 부족합니다({len(S):,}행 · "
                     f"{S['month'].nunique() if len(S) else 0}개월) — 비교 팔을 건너뜁니다. "
                     f"거래대금 하한 {MIN_ADV_KRW/1e8:.0f}억을 하위 대역이 못 넘기는 것이 "
                     f"보통이며, 이 사실 자체가 '소형주는 담기 어렵다'는 결과입니다.")
            return None
        S = downcast_floats(S)
        S = build_tps(S)
        S = apply_vetoes_v3(S, ctx)
        S = assemble_score_v3(S)
        bt_s = run_backtest(S, months, uni, ctx["sec"], apply_costs=True,
                            label=f"{STRATEGY_ID}__SMALLCAP")
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}_smallcap",
                        S[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "n_tp") if c in S.columns]],
                        scope="private", domain="scores", source="L3 스몰캡 팔")
        return {"panel": S, "bt": bt_s}


def report_arm_comparison_v3(bt_main: dict, arm: Optional[dict],
                             bench: Dict[str, pd.Series]) -> None:
    """메인(U-MID) vs 스몰캡 성과를 나란히 출력한다. 유리하게 해석하지 않는다."""
    if not arm:
        return
    rows = []
    for name, b, lo, hi in ((f"메인 U-MID", bt_main, UMID_RANK_LO, UMID_RANK_HI),
                            ("스몰캡", arm["bt"], SMALL_RANK_LO, SMALL_RANK_HI)):
        R = b.get("returns")
        if R is None or R.empty:
            continue
        st = perf_stats(R)
        _f = lambda k, fmt: (format(st[k], fmt) if k in st and np.isfinite(st.get(k, np.nan))
                             else "-")
        rows.append([name, f"[{lo},{hi}]", _f("CAGR", ".2%"), _f("Sharpe", ".2f"),
                     _f("MDD", ".1%"), _f("승률", ".0%"), _f("t통계량(HAC)", ".2f"),
                     _f("평균종목수", ".1f"), f"{len(R)}개월"])
    if not rows:
        return
    LOG.table(rows, ["팔", "규모랭크", "CAGR", "Sharpe", "MDD", "승률", "t(HAC)",
                     "평균종목", "관측"],
              ["l", "c", "r", "r", "r", "r", "r", "r", "r"],
              title="규모 대역 비교 — 같은 신호·같은 규칙, 대역만 다름")
    LOG.info("두 팔은 동일한 수집물·센서·시드를 씁니다. 따라서 차이의 원인은 규모 대역 하나로 "
             "특정됩니다. 다만 스몰캡은 거래비용·시장충격이 실제로 더 크므로, 이 표의 "
             "스몰캡 우위는 비용 가정이 낙관적일 때 과대평가됩니다(R8 비용민감도를 함께 보세요).")


# ── 산출물 ──────────────────────────────────────────────────────────────────────────────────
def persist_outputs_v3(P: pd.DataFrame, bt: dict, ctx: dict, bench: Dict[str, pd.Series],
                       t_all: float) -> List[str]:
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []

    def _w(fname: str, fn: Callable[[str], None]):
        p = os.path.join(outdir, fname)
        try:
            fn(p)
            outs.append(p)
        except Exception as e:                                    # noqa
            LOG.warn(f"산출물 저장 실패 {fname} ({type(e).__name__}: {e})")

    _w(f"canary_report_{stamp}.md", lambda p: atomic_write_text(p, canary_report_md()))
    _w(f"r2n_verdict_{stamp}.md", lambda p: atomic_write_text(p, r2n_verdict_md()))
    C = ctx.get("emp_coverage")
    if C is not None and len(C):
        _w(f"emp_coverage_{stamp}.csv",
           lambda p: C.to_csv(p, index=False, encoding="utf-8-sig"))
    cal = ctx.get("policy")
    if cal is not None and len(cal):
        _w(f"r10_policy_calendar_{stamp}.csv",
           lambda p: cal.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"returns_{stamp}.csv",
       lambda p: bt["returns"].to_csv(p, index=False, encoding="utf-8-sig"))
    if len(bt.get("holdings", pd.DataFrame())):
        _w(f"holdings_{stamp}.csv",
           lambda p: bt["holdings"].to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"panel_{stamp}.parquet", lambda p: atomic_write_parquet(P, p))

    full = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "window": [BACKTEST_START, BACKTEST_END],
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "performance": {k: (float(v) if isinstance(v, (int, float, np.floating)) and
                            np.isfinite(v) else None)
                        for k, v in (perf_stats(bt["returns"]) or {}).items()},
        "right_tail": {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v))
                       for k, v in (right_tail_contribution(bt) or {}).items()},
        "benchmarks": {},
        "canary": CANARY_RESULTS,
        "contracts": CONTRACT_V3,
        "robustness": ROBUST_V3,
        "r2n": R2N_VERDICT,
        "c15": C15_STATS,
        "coverage_verdict": ctx.get("emp_coverage_verdict", ""),
        "active_tp": globals().get("ACTIVE_TP_COLS", []),
        "runtime_minutes": (time.time() - t_all) / 60.0,
    }
    for name, s in (bench or {}).items():
        try:
            bs = perf_stats(pd.DataFrame({"month": s.index, "ret": s.to_numpy(dtype=float),
                                          "n": 0, "turnover": 0.0, "cost": 0.0}))
            full["benchmarks"][name] = {k: (float(v) if isinstance(v, (int, float, np.floating))
                                            and np.isfinite(v) else None)
                                        for k, v in bs.items()}
        except Exception:
            continue
    _w(f"backtest_full_{stamp}.json",
       lambda p: atomic_write_text(p, json.dumps(full, ensure_ascii=False, indent=2, default=str)))
    RT = report_runtime_v3(t_all)
    _w(f"runtime_{stamp}.csv", lambda p: RT.to_csv(p, index=False, encoding="utf-8-sig"))
    _w(f"log_{stamp}.txt", lambda p: atomic_write_text(p, "\n".join(LOG.buffer)))

    VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                    domain="backtest", source=STRATEGY_ID)
    VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
    if DBUDGET:
        DBUDGET.close()
    VAULT.report()
    return outs


# ── main ────────────────────────────────────────────────────────────────────────────────────
def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["DART 키", "입력됨" if DART_API_KEY else "없음 (핵심 입력 — 넣으면 살아납니다)"],
               ["KRX 마켓플레이스", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW)
                else "없음 (가격은 pykrx→FDR→네이버→yfinance 체인으로 대체)"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    if pykrx_stock is None:
        LOG.warn(
            "pykrx 를 쓸 수 없습니다 — 결과에 실제로 영향이 갑니다. 두 가지가 죽습니다:\n"
            "     ① 기관·외국인 수급 → U축 d3 가 전 기간 결측 (U 는 d1 하나로만 구성됩니다)\n"
            "     ② 특정일 상장목록 스냅샷 → PIT 유니버스가 KIND·FDR 경로에만 의존합니다\n"
            "   가격 자체는 FDR→네이버→yfinance 로 대체되지만 3~4배 느립니다. "
            f"현재 파이썬 {ENV['python']} 에 설치 가능한 휠이 없으면 3.11~3.12 환경을 권합니다.")

    t_l0 = time.time()
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root, mode = mount_cache_v3()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        # 중복 경로를 미리 제거한다(ADOPT_DIRS[0] 이 ROOT 와 같으면 같은 트리를 두 번 훑는다)
        # ★ 헤더의 ADOPT 경로는 Colab 기준(/content/...)이라 JupyterLab 에서는 하나도 안 맞는다.
        #   실제로 붙어 있는 캐시 루트의 형제 폴더(research/reports/consensus)도 함께 훑어
        #   '드라이브에 이미 모아둔 리포트'를 어느 환경에서든 등록만 하고 재사용한다.
        _sib = os.path.dirname(VAULT.root)
        adopt = list(dict.fromkeys(os.path.abspath(os.path.expanduser(d)) for d in (
            list(GDRIVE_ADOPT_DIRS) + [VAULT.root] +
            [os.path.join(_sib, n) for n in ("research", "reports", "consensus", "tcd_cache")]
        ) if d))
        adopt = [d for d in adopt if os.path.isdir(d)]
        VAULT.adopt_scan(adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET
        # ★ 알파 몫을 먼저 떼어 둔다. 이것이 없어서 Tier-2 재무가 일일 한도를 먼저 다 쓰고
        #   직원현황이 3회 실행 내내 0행이었다. 예약분은 EMP 만 인출할 수 있다.
        if EMP_RESERVED_CALLS:
            DBUDGET.reserve(EMP_PURPOSE, int(EMP_RESERVED_CALLS))
            LOG.info(f"DART 예산 예약 — 직원현황(알파) {int(EMP_RESERVED_CALLS):,}건. "
                     f"다른 단계는 나머지({DBUDGET.left(None):,}건)만 씁니다.")

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 (C1·C2·C13·C15 · 원칙1~7)", "L0", budget_s=180):
        run_contracts_v3(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest_v3(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=900):
        run_rehearsal(strict=True)
    runtime_mark("L0.준비", time.time() - t_l0)

    months = month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_flow(); report_runtime_v3(t_all)
        report_dataflow_map_v3()
        return {"mode": "SMOKE"}

    ctx = collect_all_v3(months)

    with PIPE.stage("L1.AUDIT", "다중소스 원장 연결 감사", "L1", budget_s=180, critical=False):
        report_ledger_v3(ctx)

    P, uni, ctx = build_features_v3(ctx, months)
    P, bt, _run = score_and_backtest_v3(P, ctx, months, uni)
    arm = run_smallcap_arm_v3(ctx, months, uni, {})

    with PIPE.stage("L2.POLICY", "정책 캘린더", "L2", budget_s=60, critical=False):
        cal = build_policy_calendar_v3()
        report_policy_v3(cal, months)
        ctx["policy"] = cal

    bench: Dict[str, pd.Series] = {}
    with PIPE.stage("L6.PERF", "성과 검증 (자체측정 벤치마크 대비)", "L6", budget_s=300):
        bench = R0_benchmark(P, bt, months)
        report_performance_v3(bt, bench)
        report_arm_comparison_v3(bt, arm, bench)
        # ★ 감쇠 감사는 강건성 재실행(백테스트 10여 회)이 섞이기 전에 뽑는다.
        uni.report_attrition()
        uni.attrition = []

    t_rob = time.time()
    with PIPE.stage("L5.ROBUST", "강건성 검사", "L5", budget_s=3 * 3600, critical=False):
        try:
            R1_leakage(P, months, _run)
            R2N_kill_gate(P, _run)
            R3_orthogonal(P, _run)
            R5_ablation(P, _run)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R10_policy_falsify(P, ctx.get("policy", build_policy_calendar_v3()), months, _run)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness_v3()
    runtime_mark("R-SUITE", time.time() - t_rob)

    with PIPE.stage("L6.REPORT", "해석표 · 진단 카드", "L6", budget_s=300, critical=False):
        report_interpretation_v3(P)
        diagnostic_card_v3(P, bt, ctx["sec"])

    outs: List[str] = []
    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = persist_outputs_v3(P, bt, ctx, bench, t_all)
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    report_dataflow_map_v3()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시 — ① 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 U축 d1 의 E 는 "
             "후행 12M 순이익 대리를 씁니다. ② U-MID 의 규모 랭크는 시가총액이 아니라 20일 "
             "평균거래대금 랭크입니다(시총 PIT 복원 불가에 따른 치환). ③ empSttus 는 별도 기준에 "
             "가까우므로 1인당 부가가치의 분자도 별도(OFS) 우선으로 맞췄으나, 연결 비중이 큰 "
             "지주회사에서는 오차가 큽니다. 숨기지 않고 여기에 명시합니다.")
    offer_download_v3(outs)
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_V3, "r2n": R2N_VERDICT}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§12 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        _flush_on_abort_v3()
        try:
            report_robustness_v3()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        _flush_on_abort_v3()
        PIPE.report_stages(); PIPE.report_flow()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 정확히 이 지점부터 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
