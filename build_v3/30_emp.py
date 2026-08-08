# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  EMP-LITE — DART 직원현황(empSttus) 확장 수집 + C15 한계임금                         ║
# ║                                                                                          ║
# ║  코어(v2)의 fetch_dart_employees 는 sm 과 급여총액만 남기고 jan_salary_am·rgllbr_co 를     ║
# ║  버린다. 이 전략은 그 두 필드가 없으면 성립하지 않으므로 확장판을 따로 둔다.                 ║
# ║  → 공용 인덱스 테이블명도 다르다: dart_employees_ext (다른 전략도 그대로 재사용 가능)       ║
# ║                                                                                          ║
# ║  ★ 설계상 가장 중요한 결정: EMP 센서는 **연도 프레임에서 계산한다.**                        ║
# ║    월 패널에 먼저 붙인 뒤 diff(12) 를 하면, 제출일(rcept_dt)이 해마다 며칠씩 밀리는         ║
# ║    구조 때문에 "12개월 전 행"이 같은 사업연도를 가리키는 달이 생긴다 → 차분이 0 이 되고     ║
# ║    Δ직원수=0 이 되어 C15(a) 가 그 관측을 통째로 버린다. 조용히, 로그 없이.                  ║
# ║    연도 프레임에서 계산하면 Δ는 언제나 정확히 1개 사업연도 간격이고,                        ║
# ║    PIT 안전성은 merge_asof(knowledge_date=rcept_dt) 가 그대로 보장한다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EMP_EXT_COLS = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "employees",
                "regular", "payroll_total", "avg_salary", "n_rows", "unit_fix",
                "pay_fix", "src_flag"]

def adopt_legacy_emp_cache(ext: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """★★ 구버전(v2 코어)이 같은 empSttus 로 채워 둔 공용 캐시를 흡수한다 ★★

    v2 코어의 fetch_dart_employees 는 **같은 API**(empSttus)를 받아 공용 테이블
    `dart_employees` 에 (corp_code, bsns_year, employees, payroll, knowledge_date) 로 쌓는다.
    v3 는 확장 파서를 쓰느라 `dart_employees_ext` **하나만** 읽었고, 그래서 v2 를 여러 번
    돌려 이미 받아 둔 직원현황이 눈앞에 있는데도 "직원현황 데이터가 전혀 없습니다" 로
    끝났다. 호출권을 다 쓴 날에는 이것이 알파의 유일한 원천이다.

    한계임금은 **연간급여총액과 직원수 두 개면 계산된다**:
        한계임금    = Δpayroll / Δemployees
        임금프리미엄 = 한계임금 / (payroll_prev / employees_prev)
    즉 v2 스키마만으로 TP_N1(핵심 알파)·TP_N2 가 살아난다.
    정규직 수(rgllbr_co)는 v2 가 받지 않으므로 nl_regular(TP_N3)만 결측으로 남는다 —
    없는 것을 0 으로 채우지 않는다(원칙 6).

    ★ 우선순위: 같은 (회사, 연도)가 양쪽에 있으면 **ext 를 이긴다**(부문×성별 분해행을
      쓰고 단위 역추정까지 거친 값이라 더 정확하다). 레거시는 빈 자리만 메운다.
    """
    try:
        leg = VAULT.get_table("dart_employees", scope="shared")
    except Exception:                                               # noqa
        leg = None
    if leg is None or not len(leg):
        return ext
    need = {"corp_code", "bsns_year", "employees", "payroll"}
    if not need.issubset(set(leg.columns)):
        LOG.warn(f"구버전 직원현황 캐시에 필요한 컬럼이 없습니다({sorted(need - set(leg.columns))}) "
                 f"— 흡수를 건너뜁니다.")
        return ext
    L = leg.copy()
    L["corp_code"] = L["corp_code"].astype(str)
    L["bsns_year"] = pd.to_numeric(L["bsns_year"], errors="coerce")
    L = L.dropna(subset=["corp_code", "bsns_year"])
    L["bsns_year"] = L["bsns_year"].astype(int)
    L["employees"] = pd.to_numeric(L["employees"], errors="coerce")
    L["payroll_total"] = pd.to_numeric(L["payroll"], errors="coerce")
    # 1인평균급여는 v2 가 저장하지 않는다 → 총액/인원으로 역산한다(0 나눗셈은 결측).
    L["avg_salary"] = safe_div(L["payroll_total"], L["employees"])
    L["regular"] = np.nan          # v2 는 rgllbr_co 를 받지 않는다 — 모르는 것은 결측
    L["n_rows"] = np.nan
    L["unit_fix"] = L["pay_fix"] = 1.0
    L["src_flag"] = "legacy_v2"
    if "rcept_no" not in L.columns:
        L["rcept_no"] = ""
    L["rcept_dt"] = (as_ts_series(L["knowledge_date"]) if "knowledge_date" in L.columns
                     else pd.NaT)
    L = L.reindex(columns=EMP_EXT_COLS)
    L = L[L["employees"].notna() & (L["employees"] > 0)]
    if not len(L):
        return ext
    have = set()
    if ext is not None and len(ext):
        try:
            have = set(zip(ext["corp_code"].astype(str), ext["bsns_year"].astype(int)))
        except Exception:                                           # noqa
            have = set()
    add = L[[(c, y) not in have
             for c, y in zip(L["corp_code"], L["bsns_year"])]]
    if not len(add):
        return ext
    _pay = int(add["payroll_total"].notna().sum())
    LOG.ok(f"★ 구버전 공용 캐시(dart_employees)에서 직원현황 {len(add):,}행을 흡수했습니다 "
           f"— {add['corp_code'].nunique():,}사 · {int(add['bsns_year'].min())}~"
           f"{int(add['bsns_year'].max())}년 · 급여총액 기재 {_pay:,}행 "
           f"({100*_pay/max(len(add),1):.0f}%).\n"
           f"     같은 empSttus API 를 v2 전략이 이미 받아 둔 것입니다. 한계임금은 "
           f"연간급여총액과 직원수만 있으면 계산되므로 TP_N1·TP_N2 가 이 데이터로 살아납니다.\n"
           f"     ※ 정규직 수(rgllbr_co)는 v2 가 받지 않으므로 TP_N3(nl_regular)만 결측으로 "
           f"남습니다 — 0 으로 채우지 않습니다.")
    out = (pd.concat([ext, add], ignore_index=True) if ext is not None and len(ext) else add)
    return out.drop_duplicates(["corp_code", "bsns_year"], keep="first").reset_index(drop=True)


_TOTAL_TOKENS = {"합계", "계", "소계", "총계", "합 계", "전체", "총 계", "합계(계)", "-"}

# 서킷브레이커 — 연속 실패가 이 수를 넘으면 남은 호출을 즉시 포기한다(§3).
EMP_CIRCUIT_MAX = 15

# 예산 예약 라벨. 이 이름으로 예약된 호출은 직원현황만 인출할 수 있다.
EMP_PURPOSE = "emp"

# 이번 실행에서 직원현황 수집이 잘렸는가. §6 커버리지 판정이 '미수집'을 'DART 결측'으로
# 오독하지 않게 하는 근거. dropped>0 이면 자동 창 단축(COVERAGE_AUTO_TRIM)을 걸지 않는다.
EMP_TRUNCATED: Dict[str, Any] = {"dropped": 0, "why": ""}
_EMP_CB = {"consec": 0, "tripped": False, "lock": threading.Lock()}

# 미제출(013) 원장 — 답이 존재하지 않는 (회사, 연도). 다음 실행에서 다시 묻지 않는다.
_EMP_NODATA: List[dict] = []
EMP_NODATA_TABLE = "dart_emp_nodata"


def _emp_cb_ok() -> bool:
    # ★ 예산이 이미 바닥났으면 한 건도 시도하지 않는다. 예전엔 예산 거부(None)를 '실패'로
    #   세어 서킷브레이커가 15건 만에 터질 때까지 헛돌았고, 각 호출마다 0.05~0.15초를
    #   자고 있었다 — 14,000건이면 12스레드로도 2분을 아무 일 없이 태운다.
    if dart_halt_reason(EMP_PURPOSE):
        return False
    with _EMP_CB["lock"]:
        return not _EMP_CB["tripped"]


def _emp_cb_mark(success: bool):
    with _EMP_CB["lock"]:
        if success:
            _EMP_CB["consec"] = 0
        else:
            _EMP_CB["consec"] += 1
            if _EMP_CB["consec"] >= EMP_CIRCUIT_MAX and not _EMP_CB["tripped"]:
                _EMP_CB["tripped"] = True
                # ★ 사유를 추측하지 않는다. 예산 소진·인증 오류는 이미 기록돼 있으므로
                #   "대개 …입니다" 같은 짐작 대신 실제 사유를 그대로 말한다. 짐작이 틀리면
                #   사용자는 멀쩡한 키를 의심하거나 IP 차단을 걱정하며 시간을 버린다.
                why = dart_halt_reason(EMP_PURPOSE)
                LOG.warn(f"직원현황 수집 중단 — 연속 {EMP_CIRCUIT_MAX}건 실패. "
                         f"남은 호출을 포기하고 여기까지 받은 것을 저장합니다. "
                         + (f"사유: {why}. 내일 재실행하면 이어받습니다."
                            if why else
                            "예산·인증에는 이상이 없습니다 — 네트워크 또는 DART 서버 상태를 "
                            "확인하세요(이 경우는 데이터 부재가 아닙니다)."))


def _emp_pick_rows(d: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """부문×성별 분해 행만 남긴다. 소계/합계 행과 섞으면 인원이 두 배로 계산된다.

    다만 '분해 행이 아예 없고 합계 행 하나만 제출한 회사'가 실재한다. 그 경우까지
    버리면 중소형주가 통째로 사라지므로, 분해 행이 없을 때만 합계 행을 쓴다.
    어느 경로를 탔는지는 src_flag 로 남겨 하류에서 감사할 수 있게 한다.
    """
    def _is_total(colname):
        if colname not in d.columns:
            return pd.Series(False, index=d.index)
        v = d[colname].astype(str).str.strip()
        return v.isin(_TOTAL_TOKENS)

    tot_b, tot_s = _is_total("fo_bbm"), _is_total("sexdstn")
    detail = d[~tot_b & ~tot_s]
    if len(detail):
        return detail, "detail"
    # 부문만 합계이고 성별은 분해된 경우 (또는 그 반대)
    half = d[~(tot_b & tot_s)]
    if len(half):
        return half, "half"
    return d, "total_only"


def _norm_money(v: float, kind: str) -> Tuple[float, int]:
    """단위(원/천원/백만원) 혼재 보정. (보정값, 적용배수) 를 돌려준다.

    한국 상장사 1인 평균급여의 현실 범위는 대략 1,500만 ~ 3억원이다.
    이 범위를 크게 벗어나면 단위가 원이 아니라는 뜻이므로 1000 배수로 스냅한다.
    범위 안으로 못 들어오면 보정하지 않고 그대로 둔다 — 억지로 맞추면 조용한 오염이 된다.
    """
    if not np.isfinite(v) or v <= 0:
        return (np.nan, 1)
    lo, hi = (5e6, 5e8) if kind == "avg" else (0.0, np.inf)
    if kind != "avg":
        return (v, 1)
    for mult in (1, 1_000, 1_000_000):
        if lo <= v * mult <= hi:
            return (v * mult, mult)
    return (v, 1)


def _emp_one_raw(corp: str, year: int) -> Optional[dict]:
    """empSttus 단건 → 정규화된 연 1행. 실패는 None (예외를 위로 던지지 않는다)."""
    if not _emp_cb_ok():
        return None
    try:
        time.sleep(0.05 + random.random() * 0.10)          # §5 — 0.05~0.15s 지연
        js = dart_api("empSttus.json", {"corp_code": str(corp), "bsns_year": str(int(year)),
                                        "reprt_code": REPRT_CODES["FY"]}, no_data_ok=True,
                      purpose=EMP_PURPOSE)
    except Exception:
        _emp_cb_mark(False)
        return None
    # ★ '그 해에 사업보고서를 안 낸 회사'(status 013)는 **정상 응답**이지 실패가 아니다.
    #   실패로 세면 서킷브레이커가 정상 데이터만으로 터진다: 잡 격자가 corp × year 라
    #   신규상장사·폐지사는 초기/말기 연도가 통째로 013 이고, 12개 스레드가 공유하는
    #   연속실패 카운터는 그런 회사 몇 곳이면 15에 도달한다. 그러면 아직 받지 않은
    #   수천 건을 전부 포기하고, 로그에는 '차단당한 것 같다'는 오해를 남긴다.
    if isinstance(js, dict) and str(js.get("status", "")) == "013":
        _emp_cb_mark(True)
        # ★ '그 해에 제출하지 않았다'는 **영구적 사실**이다. 그런데 흔적을 남기지 않아
        #   매 실행 다시 물었다. 유니버스가 생존자편향 없이 구성돼 있어 폐지 이후·상장 이전
        #   연도가 격자의 40% 가까이 되고, 그게 연도 내림차순 큐의 앞쪽에 몰린다.
        #   → 답이 있을 수 없는 질문에 매일 한도의 대부분을 쓰고 있었다. 기록해 둔다.
        with _EMP_CB["lock"]:
            # ★ asked_at 이 없으면 이 원장은 **영구**가 된다. 사업보고서 제출 전에 한 번
            #   물어본 (회사,연도)가 영영 결측으로 굳는다 — 다른 음성캐시는 전부 만료를
            #   갖는데 여기만 없었다. 최근 회계연도일수록 짧게 만료시킨다.
            _EMP_NODATA.append({"corp_code": str(corp), "bsns_year": int(year),
                                "asked_at": _dt.date.today().isoformat()})
        return None
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        _emp_cb_mark(False)
        return None
    _emp_cb_mark(True)

    d = pd.DataFrame(js["list"])
    sel, flag = _emp_pick_rows(d)
    if sel.empty:
        return None

    sm = _num_series(sel.get("sm", pd.Series(dtype=object)))
    reg = _num_series(sel.get("rgllbr_co", pd.Series(dtype=object)))
    cnt = _num_series(sel.get("cnttk_co", pd.Series(dtype=object)))
    tot = _num_series(sel.get("fyer_salary_totamt", pd.Series(dtype=object)))
    jan = _num_series(sel.get("jan_salary_am", pd.Series(dtype=object)))

    emp = float(sm.sum(skipna=True)) if sm.notna().any() else np.nan
    if not np.isfinite(emp) or emp <= 0:
        # sm 이 비면 정규직+계약직으로 복원한다 (일부 제출본이 sm 을 비워 둔다)
        alt = float(reg.fillna(0).sum() + cnt.fillna(0).sum())
        emp = alt if alt > 0 else np.nan
    regular = float(reg.sum(skipna=True)) if reg.notna().any() else np.nan
    payroll = float(tot.sum(skipna=True)) if tot.notna().any() else np.nan

    # ★ jan_salary_am(1인 평균급여)은 절대 합산하지 않는다. 인원 가중평균이 유일하게 옳다.
    if jan.notna().any() and sm.notna().any():
        w = sm.where(sm > 0)
        num = (jan * w).sum(skipna=True)
        den = w.where(jan.notna()).sum(skipna=True)
        avg = float(num / den) if den and den > 0 else float(jan.mean(skipna=True))
    elif jan.notna().any():
        avg = float(jan.mean(skipna=True))
    else:
        avg = np.nan

    avg, unit_fix = _norm_money(avg, "avg")

    # ── 급여총액 단위 보정 ──────────────────────────────────────────────────────────────
    #   tot ≈ avg × emp 가 성립해야 한다. 다만 **먼저 '고칠 필요가 있는가'를 묻는다.**
    #
    #   ★ 가장 가까운 1000 배수를 무조건 고르면 멀쩡한 값을 망친다: 1인평균급여가 그 회사를
    #     대표하지 못하는 제출본(예: 임원만 기재)에서는 expect 가 실제보다 수십 배 작아지고,
    #     그러면 '÷1000' 이 오히려 오차를 줄이는 것처럼 보여 **정확한 급여총액이 1000분의 1로
    #     조용히 축소된다.** 한계임금은 이 값의 차분이므로 그대로 신호가 뒤집힌다.
    #   → 원값이 이미 10배 이내면 손대지 않는다. 명백히 틀렸을 때만, 그것도 배수 보정이
    #     3배 이내로 들어맞을 때만 고친다. 둘 다 아니면 폐기한다(0 채움 금지).
    pay_fix = 1
    if np.isfinite(payroll) and np.isfinite(avg) and np.isfinite(emp) and emp > 0 and avg > 0:
        expect = avg * emp
        err0 = abs(math.log10(max(payroll, 1e-9) / expect))
        if err0 > 1.0:                                     # 10배 넘게 어긋난 경우에만 개입
            best, best_err = None, np.inf
            for m2 in (1_000, 1_000_000, 0.001, 0.000001):
                err = abs(math.log10(max(payroll * m2, 1e-9) / expect))
                if err < best_err:
                    best, best_err = m2, err
            if best_err <= 0.5:                            # 보정 후 3배 이내로 맞을 때만 채택
                payroll, pay_fix = payroll * best, best
            else:
                payroll = np.nan                           # §5 — 불일치 10배+ 폐기

    rn = str(sel["rcept_no"].iloc[0]) if "rcept_no" in sel.columns and len(sel) else ""
    kd = _knowledge_from_rcept(rn, REPRT_CODES["FY"], int(year))
    return {"corp_code": str(corp), "bsns_year": int(year), "rcept_no": rn,
            "rcept_dt": kd, "employees": emp, "regular": regular,
            "payroll_total": payroll, "avg_salary": avg, "n_rows": int(len(sel)),
            "unit_fix": int(unit_fix), "pay_fix": float(pay_fix), "src_flag": flag}


def fetch_emp_status(corp_codes: Sequence[str], years: Sequence[int],
                     priority: Optional[Sequence[str]] = None,
                     max_calls: Optional[int] = None,
                     pairs: Optional[set] = None) -> pd.DataFrame:
    """empSttus 증분 수집. 공용 캐시(dart_employees_ext)를 먼저 소진하고 부족분만 호출한다.

    ★ 잡 수는 |기업| × |연도| 로 곱해진다(3,981사 × 13년 = 51,753 > 일일한도 19,000).
      max_calls 로 이번 실행분을 잘라내고, priority 순서로 '담길 확률이 높은 종목'부터 채운다.
      한계임금은 이 전략의 알파 원천이므로 Tier-2 재무보다 **먼저** 예산을 배정한다.
    """
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ v2 레거시 흡수분을 dart_employees_ext 로 되쓰지 않는다 ★★
    #    v2 코어의 dart_employees 에는 **정규직 수(rgllbr_co)가 없다.** 흡수하면서
    #    regular=NaN 으로 채우는데, 그 행을 그대로 ext 에 저장해 버리면 다음 실행의
    #    `done` 집합에 (회사,연도)가 들어가 **영영 다시 묻지 않는다.**
    #    그러면 nl_regular 가 영구 결측이 되고 TP_N3(정규직 확충 = 확신의 증거)는
    #    이 캐시가 존재하는 한 절대 살아나지 못한다. 흡수가 알파를 살린 자리에서
    #    다른 알파를 죽이는 셈이다.
    #  → 저장용(ext_only)과 계산용(cached)을 분리한다. 흡수분은 계산·반환에만 쓴다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    ext_only = VAULT.get_table("dart_employees_ext", scope="shared")
    cached = adopt_legacy_emp_cache(ext_only)
    done = set()
    if cached is not None and len(cached):
        try:
            _full = cached
            if "src_flag" in cached.columns:
                # 레거시 흡수분은 '값은 쓰되 완성으로 치지 않는다'. 정규직 수가 없으므로
                # 예산이 남으면 원본(empSttus)으로 다시 받아 TP_N3 를 살릴 여지를 남긴다.
                _full = cached[cached["src_flag"].astype(str) != "legacy_v2"]
            done = set(zip(_full["corp_code"].astype(str), _full["bsns_year"].astype(int)))
            _leg = len(cached) - len(_full)
            LOG.ok(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용 ({len(done):,} 조합) — "
                   f"이만큼은 API 를 다시 부르지 않습니다" +
                   (f" · 그중 v2 레거시 {_leg:,}행은 정규직 수가 없어 **재수집 대상으로 남깁니다**"
                    f"(TP_N3 를 영구 결측으로 굳히지 않기 위함 — 값 자체는 지금도 씁니다)"
                    if _leg else ""))
        except Exception:
            done = set()
    skip = emp_nodata_skip_set()          # ★ 만료된 기록은 제외 대상에서 빠진다
    if skip:
        done |= skip
        LOG.info(f"미제출 원장에서 {len(skip):,} (사×연) 을 제외합니다 — "
                 f"그 해 사업보고서를 내지 않은 조합이라 다시 물어도 답이 없습니다. "
                 f"(만료된 기록은 이 집합에 들어가지 않아 다시 시도합니다)")
    if not dart_has_key():
        LOG.warn("DART_API_KEY 미입력 — 직원현황 신규 수집을 건너뜁니다. "
                 "캐시에 있는 것만으로 진행하며, 없으면 EMP-LITE 전 센서가 결측입니다.")
        return _emp_finalize(cached, [], store=ext_only)

    corps = [str(c) for c in dict.fromkeys(corp_codes) if str(c) and str(c) != "nan"]
    if EMP_MAX_CORPS and EMP_MAX_CORPS > 0:
        corps = corps[:EMP_MAX_CORPS]
    # 담길 확률이 높은 종목 먼저 — 예산에 걸려 잘려도 '쓸 수 있는' 한계임금이 먼저 완성된다.
    _ord = {str(c): i for i, c in enumerate(priority or [])}
    corps = sorted(corps, key=lambda c: (_ord.get(c, 10 ** 9), c))
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 회사 우선(company-first) 격자 — 7회차에 EMP 가 4개년(2022~2025)뿐이던 원인 ★★
    #
    #    예전: for y in years(내림차순) for c in corps   ← **연도 우선**
    #    잡이 잘리면 항상 '오래된 연도'가 통째로 버려진다. 실측 결과가 정확히 그랬다:
    #    2,536사 × 3.4년. 그런데 이 전략의 백테스트는 120개월이다 —
    #    **앞 80개월에 EMP 신호가 한 건도 없는 채로** 10년 성과를 보고하고 있었다.
    #    그건 'CORE-D 단독 80개월 + CORE-D+EMP 40개월'을 이어 붙인 것이지 10년 전략이 아니다.
    #
    #    지금: for c in corps(우선순위) for y in years(내림차순)   ← **회사 우선**
    #    잘리면 '뒤쪽 회사'가 버려진다. 즉 확보한 회사는 **10년 전 구간이 완성**된다.
    #    커버리지 폭(회사 수)은 줄지만 커버리지 **깊이**(연도)가 생긴다. 이 전략에서는
    #    깊이가 훨씬 중요하다 — 12개월 차분 센서(nl_emp·nl_premium)는 연속 2개년이 없으면
    #    아예 산출되지 않고, 앞 구간이 비면 백테스트의 3분의 2가 무증거 구간이 된다.
    #    재실행하면 append-only 캐시가 이어받아 회사 수가 매번 늘어난다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    _years_desc = sorted({int(y) for y in years}, reverse=True)
    jobs = [(c, y) for c in corps for y in _years_desc if (c, int(y)) not in done]
    # ★ 호출자가 '실제로 쓰이는 조합'을 주면 그것만 남긴다. 데카르트 곱은 담길 수 없었던
    #   해까지 묻느라 한도의 대부분을 태운다 — 부족한 건 한도가 아니라 격자 설계였다.
    if pairs:
        before = len(jobs)
        jobs = [j for j in jobs if (str(j[0]), int(j[1])) in pairs]
        if before != len(jobs):
            LOG.info(f"  필요 조합 필터로 {before:,} → {len(jobs):,}건 "
                     f"({100*len(jobs)/max(before,1):.0f}%)")
    if RUN_MODE == "CACHED":
        if jobs:
            LOG.info(f"RUN_MODE='CACHED' — 신규 수집 대상 {len(jobs):,}건을 건너뜁니다.")
        jobs = []

    got: List[dict] = []
    if jobs:
        total_needed = len(jobs)
        if max_calls is not None:
            # ★★ 로컬 추정 잔량으로 알파 수집을 자르지 않는다 ★★
            #   예전엔 `cap = min(total, max_calls, dart_budget_left("emp"))` 였다.
            #   left 는 dart_budget.json 에서 복원한 **KST 같은 날 누적 추정치**일 뿐인데,
            #   그 값이 19,000 에 닿는 순간 cap=0 → jobs[:0] → 호출 0건 → 직원현황 0행이 됐다.
            #   서버는 같은 실행에서 3,740 요청에 100% 응답했고 020 을 한 번도 주지 않았다.
            #   즉 우리가 스스로 알파를 포기한 것이다. 이 전략에서 직원현황이 비면
            #   '전략 3' 이 아니라 이름만 같은 다른 전략이 된다.
            #   → 상한은 '이번 실행에서 의도적으로 정한 작업량'(EMP_MAX_CALLS)뿐이고,
            #     진짜 중단은 아래 청크 루프의 _emp_cb_ok() → 서버 020/021 로만 일어난다.
            cap = max(0, min(total_needed, int(max_calls)))
            # ★ 잘라야 한다면 **회사 경계**에서 자른다. 회사 중간에서 끊으면 그 회사만
            #   연도가 뚫린 채 남고, 12개월 차분 센서는 뚫린 구간에서 산출되지 않는다.
            _per = max(1, len(_years_desc))
            if 0 < cap < total_needed:
                cap = max(_per, (cap // _per) * _per)
            if cap < total_needed:
                # ★ 절단 사실을 기록해 둔다. §6 커버리지 판정이 이 표를 'DART 의 보유량'으로
                #   오독해 백테스트 창을 영구히 잘라내는 것을 막기 위한 유일한 근거다.
                EMP_TRUNCATED.update({
                    "dropped": total_needed - cap,
                    "why": f"상한 EMP_MAX_CALLS={int(max_calls):,}"})
                jobs = jobs[:cap]
                LOG.warn(f"직원현황 {total_needed:,}건 중 이번 실행은 {cap:,}건만 받습니다 "
                         f"(상한 EMP_MAX_CALLS={max_calls:,} · 회사 {cap//_per:,}사의 전 기간). "
                         f"회사 우선이므로 확보한 회사는 {_years_desc[-1]}~{_years_desc[0]}년이 "
                         f"모두 채워집니다 — 재실행하면 다음 회사부터 이어받습니다. "
                         f"※ 미수집분이 있으므로 §6 커버리지 기반 자동 창 단축은 비활성화됩니다.")
        LOG.info(f"직원현황 신규 수집 {len(jobs):,}건 "
                 f"({len(corps):,}사 × {len(years)}년, 캐시 적중 {len(done):,}) — "
                 f"약 {len(jobs)/max(RATE_LIMIT_QPS.get('dart',8.0),1)/60:.0f}분 예상 "
                 f"· 계획 기준선 {dart_budget_left(EMP_PURPOSE):,}건(추정, 차단 기준 아님)")
        _EMP_CB.update({"consec": 0, "tripped": False})
        # ══════════════════════════════════════════════════════════════════════════════════
        #  ★ 청크 체크포인트 — 예산은 200건마다 영속되는데 **데이터는 맨 끝에 한 번**이었다.
        #    비대칭이 치명적이다: 28분째에 죽으면 드라이브에는 '14,000건 썼음'만 남고
        #    dart_employees_ext 는 0행 그대로다. 다음 실행은 예산이 없다며 정당하게 거부한다.
        #    → 세션 종료·OOM·Ctrl+C 어디서 끊겨도 **받은 만큼은 반드시 남는다.**
        #    Vault 는 append-only 저널이라 증분 저장이 싸고 안전하다.
        # ══════════════════════════════════════════════════════════════════════════════════
        # ★ 시간 몫. 직원현황은 이 전략의 알파 원천이므로 남은 수집시간의 절반 가까이를
        #   먼저 배정한다(Tier-2 재무는 그 다음). 고정 상수를 쓰지 않는 이유는 06_env 참조.
        _deadline = time.time() + stage_time_budget(EMP_TIME_SHARE, floor_s=120.0)
        LOG.info(f"  시간 몫 {max(0.0, _deadline-time.time())/60:.0f}분 배정 · {deadline_note()} "
                 f"— 멈추는 조건은 ①서버 020/021 ②시계 둘뿐입니다(로컬 추정 잔량으로는 "
                 f"자르지 않습니다).")
        got, done_n = [], 0
        # 청크를 회사 경계의 배수로 맞춘다 — 중단해도 반쪽짜리 회사가 남지 않는다.
        _per = max(1, len(_years_desc))
        _chunk_n = max(_per, (EMP_CHECKPOINT_EVERY // _per) * _per)
        for i in range(0, len(jobs), _chunk_n):
            chunk = jobs[i:i + _chunk_n]
            res = pmap_io(lambda j: _emp_one_raw(j[0], j[1]), chunk,
                          workers=min(N_WORKERS_IO, 12),
                          desc=f"DART 직원현황({i//_chunk_n + 1}/"
                               f"{math.ceil(len(jobs)/_chunk_n)})")
            got.extend(r for r in res if r)
            done_n += len(chunk)
            _emp_checkpoint(ext_only, got)
            _halt = (None if _emp_cb_ok() else
                     (dart_halt_reason(EMP_PURPOSE) or "수집 중단(서킷브레이커)"))
            if _halt is None and time.time() >= _deadline:
                _halt = (f"4시간 계약의 직원현황 시간 몫 소진 — {deadline_note()}. "
                         f"회사 경계에서 멈췄으므로 받은 회사는 전 기간이 온전합니다")
            if _halt:
                if done_n < len(jobs):
                    EMP_TRUNCATED.update({"dropped": len(jobs) - done_n, "why": _halt})
                    LOG.warn(f"직원현황 수집을 {done_n:,}/{len(jobs):,}건"
                             f"(회사 {done_n//_per:,}사)에서 멈춥니다 — {_halt}. "
                             f"여기까지는 드라이브 공용 인덱스에 저장됐고 재실행 시 정확히 "
                             f"이 지점부터 이어받습니다. "
                             f"※ 미수집분이 있으므로 §6 자동 창 단축은 비활성화됩니다.")
                break
        LOG.info(f"직원현황 신규 확보 {len(got):,}/{len(jobs):,}건")
    return _emp_finalize(cached, got, store=ext_only)


EMP_CHECKPOINT_EVERY = 1_000


def _emp_checkpoint(cached: Optional[pd.DataFrame], got: List[dict]) -> None:
    """지금까지 받은 것을 공용 인덱스에 즉시 반영한다(실패해도 수집은 계속)."""
    try:
        if got:
            E = pd.concat([f for f in (cached, pd.DataFrame(got)) if f is not None and len(f)],
                          ignore_index=True)
            E["corp_code"] = E["corp_code"].astype(str)
            E = E.drop_duplicates(["corp_code", "bsns_year"], keep="last")
            VAULT.put_table("dart_employees_ext", E, scope="shared", domain="dart",
                            source="opendart empSttus 확장 (증분 체크포인트)",
                            backup=False)   # 청크마다 전량 복사하지 않는다(수집 시간·용량)
        if _EMP_NODATA:
            prev = VAULT.get_table(EMP_NODATA_TABLE, scope="shared")
            N = pd.concat([f for f in (prev, pd.DataFrame(_EMP_NODATA))
                           if f is not None and len(f)], ignore_index=True)
            N["corp_code"] = N["corp_code"].astype(str)
            if "asked_at" not in N.columns:
                N["asked_at"] = pd.NaT
            N = (N.sort_values("asked_at", na_position="first")
                  .drop_duplicates(["corp_code", "bsns_year"], keep="last"))
            VAULT.put_table(EMP_NODATA_TABLE, N, scope="shared", domain="dart",
                            source="empSttus 미제출(013) 원장 — 재요청 방지(만료 있음)")
    except Exception as e:                                          # noqa
        LOG.debug(f"직원현황 체크포인트 실패({type(e).__name__}) — 수집은 계속합니다.")


def emp_nodata_skip_set() -> set:
    """'물어봤는데 자료가 없더라' 원장에서 **아직 유효한** 조합만 돌려준다.

    ★ 만료가 없으면 이 원장은 영구 배제 목록이 된다. 사업보고서는 다음 해 3~4월에
      제출되므로, 제출 전에 한 번 물어본 (회사, 최근연도) 조합이 영영 결측으로 굳는다.
      실제로 이 파일의 다른 음성캐시(dart_multi_nodata·dart_fnltt_nodata)는 전부
      만료를 갖고 있는데 여기만 없었다.
      → 오래된 회계연도는 1년, 최근 2개 회계연도는 30일 뒤 다시 묻는다.
        asked_at 이 없는 기존 기록은 '최근 연도만' 만료로 보수적으로 처리한다.
    """
    nod = VAULT.get_table(EMP_NODATA_TABLE, scope="shared")
    if nod is None or not len(nod):
        return set()
    try:
        d = nod.copy()
        d["bsns_year"] = pd.to_numeric(d["bsns_year"], errors="coerce")
        d = d.dropna(subset=["corp_code", "bsns_year"])
        _y_now = _dt.date.today().year
        recent = d["bsns_year"] >= (_y_now - 2)
        age = ((pd.Timestamp(_dt.date.today()) - as_ts_series(d.get("asked_at", pd.NaT)))
               .dt.days if "asked_at" in d.columns else pd.Series(np.nan, index=d.index))
        ttl = np.where(recent, MULTI_NODATA_RECENT_DAYS, MULTI_NODATA_OLD_DAYS)
        # asked_at 결측(구 원장) → 최근 연도는 만료시키고 과거 연도는 유지한다.
        alive = np.where(age.isna().to_numpy(), ~recent.to_numpy(),
                         age.fillna(0).to_numpy() <= ttl)
        keep = d[alive]
        n_exp = len(d) - len(keep)
        if n_exp:
            LOG.info(f"직원현황 미제출 원장에서 {n_exp:,}건이 만료돼 다시 묻습니다 "
                     f"(최근 회계연도 {MULTI_NODATA_RECENT_DAYS}일 · 과거 "
                     f"{MULTI_NODATA_OLD_DAYS}일). 제출 전에 물어본 조합이 영구 결측으로 "
                     f"굳는 것을 막습니다.")
        return set(zip(keep["corp_code"].astype(str), keep["bsns_year"].astype(int)))
    except Exception:                                                # noqa
        return set()


def _emp_finalize(cached: Optional[pd.DataFrame], got: List[dict],
                  store: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    # store 가 주어지면 **저장은 그것에만** 한다(v2 레거시 흡수분을 ext 로 되쓰지 않기 위함).
    if store is not None and got:
        _emp_checkpoint(store, got)
    frames = []
    if cached is not None and len(cached):
        frames.append(cached)
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        LOG.warn("직원현황 데이터가 전혀 없습니다 — EMP-LITE 3개 TP 가 모두 결측이 됩니다.")
        return pd.DataFrame(columns=EMP_EXT_COLS)
    E = pd.concat(frames, ignore_index=True)
    for c in EMP_EXT_COLS:
        if c not in E.columns:
            E[c] = np.nan
    E["corp_code"] = E["corp_code"].astype(str)
    E["bsns_year"] = pd.to_numeric(E["bsns_year"], errors="coerce").astype("Int64")
    E = E.dropna(subset=["bsns_year"])
    E["bsns_year"] = E["bsns_year"].astype(int)
    E = E.drop_duplicates(["corp_code", "bsns_year"], keep="last").reset_index(drop=True)
    E["rcept_dt"] = as_ts_series(E["rcept_dt"])
    # rcept_dt 가 없으면 법정 제출기한(사업보고서 90일)으로 보수적 추정 — '늦게 알았다' 방향
    miss = E["rcept_dt"].isna()
    if miss.any():
        E.loc[miss, "rcept_dt"] = [
            _knowledge_from_rcept("", REPRT_CODES["FY"], int(y)) for y in E.loc[miss, "bsns_year"]]
    if got:
        VAULT.put_table("dart_employees_ext", E, scope="shared", domain="dart",
                        source="opendart empSttus (v3 확장: jan_salary_am·rgllbr_co 포함)")
    PIPE.io("OUT", "DRIVE", "dart_employees_ext", E, source="opendart empSttus")
    LOG.ok(f"직원현황 총 {len(E):,}행 · {E['corp_code'].nunique():,}사 · "
           f"{E['bsns_year'].min()}~{E['bsns_year'].max()}년 "
           f"(급여총액 기재 {E['payroll_total'].notna().mean():.0%})")
    # 단위 정규화가 얼마나 개입했는지 드러낸다 — 조용한 보정은 조용한 오염과 구별되지 않는다.
    rows = []
    if "unit_fix" in E.columns:
        for m, n in E["unit_fix"].value_counts().sort_index().items():
            rows.append([f"1인평균급여 ×{int(m):,}", f"{int(n):,}",
                         "원 단위 그대로" if int(m) == 1 else "천원/백만원 기재로 판단해 환산"])
    if "pay_fix" in E.columns:
        for m, n in E["pay_fix"].value_counts().sort_index().items():
            rows.append([f"급여총액 ×{float(m):g}", f"{int(n):,}",
                         "손대지 않음" if float(m) == 1.0 else "10배 초과 불일치 → 배수 보정"])
    n_drop = int(E["payroll_total"].isna().sum())
    rows.append(["급여총액 결측/폐기", f"{n_drop:,}", "무기재이거나 10배+ 불일치로 폐기(0 채움 안 함)"])
    if "src_flag" in E.columns:
        for f, n in E["src_flag"].value_counts().items():
            rows.append([f"행 선택 경로: {f}", f"{int(n):,}",
                         {"detail": "부문×성별 분해행 사용(정상)",
                          "half": "한쪽만 합계 — 부분 분해",
                          "total_only": "합계행만 제출 — 이중계상 위험 없음"}.get(str(f), "")])
    LOG.table(rows, ["단위·행선택 정규화", "건수", "의미"], ["l", "r", "l"],
              title="직원현황 정규화 감사 (K9 단위 정합성의 실측 결과)")
    return E


# ── C15 : 한계임금 분모 안정성 (스펙 §4 신설 계약) ──────────────────────────────────────────
C15_STATS: Dict[str, Any] = {}


def build_emp_sensors(E: pd.DataFrame) -> pd.DataFrame:
    """연도 프레임에서 EMP-LITE 센서를 만든다. C15 (a)(b)(d) 를 여기서 강제한다.

    출력 컬럼(연 1행/사):
      nl_emp      Δlog(직원수)
      nl_dn       Δ(직원수)
      nl_marginal Δ(연간급여총액) / Δ(직원수)          ← C15 조건부
      nl_premium  nl_marginal / 전기 1인평균급여액       ← ★ 이 전략의 핵심
      nl_regular  Δ(정규직 비중)
      emp_ok      C15 전 조건 통과 여부 (커버리지 감사용)
    """
    if E is None or E.empty:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "knowledge_date"])
    D = E.sort_values(["corp_code", "bsns_year"]).copy()
    g = D.groupby("corp_code", observed=True)

    # ★ 연도가 비연속이면(예: 2018 → 2020) 차분이 2년치가 되어 '1년간 변화'라는 전제가 깨진다.
    #   그런 관측은 계산하지 않는다. 채워 넣지도 않는다(C15: forward-fill 금지).
    D["year_gap"] = g["bsns_year"].diff()
    contiguous = D["year_gap"] == 1

    emp_prev = g["employees"].shift(1)
    pay_prev = g["payroll_total"].shift(1)
    avg_prev = g["avg_salary"].shift(1)
    reg_ratio = safe_div(D["regular"], D["employees"])
    D["regular_ratio"] = reg_ratio.where((reg_ratio >= 0) & (reg_ratio <= 1.001))

    D["emp_prev"] = emp_prev.where(contiguous)
    D["dn"] = (D["employees"] - emp_prev).where(contiguous)
    D["d_pay"] = (D["payroll_total"] - pay_prev).where(contiguous)

    # (a) |Δ직원수| >= max(5, 직원수_{t-1} × 3%) 일 때만 계산
    thresh = np.maximum(C15_MIN_ABS_DN, D["emp_prev"].fillna(0) * C15_MIN_REL_DN)
    gate_a = D["dn"].abs() >= thresh

    # (d) Δ직원수 급변 (>+100% / <-50%) = M&A·분할 의심 → 결측
    rel = safe_div(D["dn"], D["emp_prev"])
    gate_d = (rel <= C15_MNA_UP) & (rel >= C15_MNA_DN)

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ (d) M&A·분할 게이트는 nl_marginal 뿐 아니라 **nl_emp 계열 전부**에 걸어야 한다 ★★
    #    예전엔 gate_d 가 nl_marginal(=한계임금)에만 걸려 있었다. 그런데 nl_emp 는
    #    TP_N1·TP_N2·TP_N3 **세 개 모두의 a-다리**다. 인수합병으로 인원이 2배가 된 회사는
    #    nl_emp 가 크게 양(+)이 되어 셀 상위 랭크를 받고, TP_N2(희석 없는 확장)·
    #    TP_N3(정규직 확충)에서 '인력을 크게 늘렸다'는 증거로 계산된다.
    #    그건 채용이 아니라 회계적 편입이다 — 스펙 §4 C15(d) 가 정확히 배제하려던 것이고,
    #    한 다리에만 걸어 두면 산식 정의가 절반만 지켜진다.
    #  ★ 반대로 (a) 분모 안정성 게이트는 nl_emp 에 걸지 않는다. 그건 'Δn 으로 나눌 때'의
    #    조건이지 '인원이 얼마나 변했는가' 자체의 조건이 아니다. 걸면 정상적인 소폭 증감이
    #    통째로 사라져 표본이 근거 없이 줄어든다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    _organic = gate_d.fillna(False) & contiguous.fillna(False)
    D["nl_emp"] = (np.log(D["employees"].where(D["employees"] > 0)) -
                   np.log(D["emp_prev"].where(D["emp_prev"] > 0))).where(_organic)
    D["nl_dn"] = D["dn"].where(_organic)
    D["nl_regular"] = ((D["regular_ratio"] - g["regular_ratio"].shift(1)).where(_organic)
                       if "regular_ratio" in D.columns else np.nan)

    ok = gate_a.fillna(False) & _organic
    D["nl_marginal"] = safe_div(D["d_pay"], D["dn"]).where(ok)

    # (b) 임금프리미엄 [0, 5] 클리핑. 초과는 '오류'로 보고 NaN — 절대 clip 으로 뭉개지 않는다.
    prem_raw = safe_div(D["nl_marginal"], avg_prev.where(avg_prev > 0))
    in_range = prem_raw.between(C15_PREMIUM_LO, C15_PREMIUM_HI)
    n_out = int((prem_raw.notna() & ~in_range).sum())
    D["nl_premium"] = prem_raw.where(in_range)
    D["emp_ok"] = (D["nl_premium"].notna()).astype(int)

    C15_STATS.update({
        "n_rows": int(len(D)),
        "n_contiguous": int(contiguous.sum()),
        "n_gate_a_fail": int((~gate_a.fillna(False) & contiguous.fillna(False)).sum()),
        "n_gate_d_fail": int((~gate_d.fillna(False) & contiguous.fillna(False)).sum()),
        "n_premium_out_of_range": n_out,
        "n_valid": int(D["nl_premium"].notna().sum()),
    })
    LOG.table([["전체 (사×연) 관측", f"{C15_STATS['n_rows']:,}"],
               ["연도 연속(Δ=1년)", f"{C15_STATS['n_contiguous']:,}"],
               ["(a) |Δ인원| 임계 미달 → 결측", f"{C15_STATS['n_gate_a_fail']:,}"],
               ["(d) M&A·분할 의심 → 결측", f"{C15_STATS['n_gate_d_fail']:,}"],
               ["(b) 프리미엄 [0,5] 이탈 → 결측", f"{C15_STATS['n_premium_out_of_range']:,}"],
               ["★ 최종 유효 임금프리미엄", f"{C15_STATS['n_valid']:,}"]],
              ["C15 게이트", "건수"], ["l", "r"],
              title="C15 한계임금 분모 안정성 (0 채움·forward-fill 금지)")

    # knowledge_date = 사업보고서 접수일. 이것이 PIT 의 전부다.
    D["knowledge_date"] = as_ts_series(D["rcept_dt"])
    D["period_end"] = as_ts_series(D["bsns_year"].astype(int).astype(str) + "-12-31")
    # ★ d_pay·avg_prev 를 함께 내보내는 이유: R5 절제검사가 C15 분모 임계값을 바꿔가며
    #   한계임금을 '재계산'해야 하는데, 원재료가 패널에 없으면 그 절제는 아예 불가능하다.
    D["avg_prev"] = avg_prev
    keep = ["corp_code", "bsns_year", "period_end", "knowledge_date", "employees", "emp_prev",
            "regular_ratio", "payroll_total", "avg_salary", "avg_prev", "dn", "d_pay",
            "nl_emp", "nl_dn", "nl_marginal", "nl_premium", "nl_regular", "emp_ok", "src_flag"]
    out = D[[c for c in keep if c in D.columns]].copy()
    return out


def test_c15(df: pd.DataFrame) -> Tuple[bool, str]:
    """스펙 §4 의 test_c15 를 그대로 코드로 옮긴 자가검정."""
    if df is None or df.empty or "dn" not in df.columns:
        return True, "표본 없음 — 검정 생략"
    d = df.dropna(subset=["emp_prev"])
    if d.empty:
        return True, "표본 없음 — 검정 생략"
    ok = d["dn"].abs() >= np.maximum(C15_MIN_ABS_DN, d["emp_prev"] * C15_MIN_REL_DN)
    leak = int(d.loc[~ok, "nl_marginal"].notna().sum())
    if leak:
        return False, f"C15(a) 위반 — 임계 미달인데 한계임금이 계산된 행 {leak:,}건"
    p = d["nl_premium"].dropna()
    if len(p) and not p.between(C15_PREMIUM_LO, C15_PREMIUM_HI).all():
        return False, (f"C15(b) 위반 — 임금프리미엄이 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}] 밖: "
                       f"min={p.min():.2f} max={p.max():.2f}")
    return True, f"통과 (유효 프리미엄 {len(p):,}건 · 전부 [{C15_PREMIUM_LO},{C15_PREMIUM_HI}])"


# ── §6 커버리지 감사 (필수 출력) ────────────────────────────────────────────────────────────
def emp_coverage_audit(S: pd.DataFrame, umid_n: Dict[int, int],
                       umid_corps: Optional[Dict[int, set]] = None) -> pd.DataFrame:
    """연도별: U-MID 대상 / empSttus 성공 / 급여총액 기재 / C15 통과 / 유효 관측치.

    ★ 분자와 분모는 반드시 같은 모집단이어야 한다. umid_corps 를 주면 그 해 U-MID 였던
      기업으로 분자를 제한한다. 주지 않으면 전 상장사 기준이며, 그 사실을 표 제목에 밝힌다.
    반환 DataFrame 은 emp_coverage.csv 로 저장되고, 시작연도 판정의 근거가 된다.
    """
    rows = []
    if S is None or S.empty:
        LOG.warn("직원현황 패널이 비어 커버리지 감사를 출력할 수 없습니다.")
        return pd.DataFrame(columns=["year", "u_mid", "emp_ok", "pay_ok", "c15_ok", "valid"])
    scoped = umid_corps is not None and len(umid_corps) > 0
    for y in sorted(S["bsns_year"].dropna().astype(int).unique()):
        sub = S[S["bsns_year"] == y]
        if scoped:
            # 사업연도 y 의 공시는 y+1 년에 알려지므로, 그 해 U-MID 였던 기업 기준으로 센다.
            #   ★ 교집합이 비면 그 해엔 U-MID 종목이 아예 없다는 뜻이다(대개 백테스트 창 밖).
            #     그때 필터를 건너뛰면 분자만 전 상장사로 튀어 분모(0)와 어긋난다 → 0 으로 센다.
            keep = umid_corps.get(int(y), set()) | umid_corps.get(int(y) + 1, set())
            sub = sub[sub["corp_code"].astype(str).isin(keep)] if keep else sub.iloc[0:0]
        # ★ 분모도 분자와 **같은 집합**에서 센다. 분모를 '그 해 U-MID', 분자를 'y 또는 y+1 에
        #   U-MID' 로 두면 (사업연도 y 의 공시는 y+1 에 알려지므로 분자는 y+1 을 포함해야 한다)
        #   표가 자기모순에 빠진다 — 분모 0 인데 분자 84 같은 행이 나온다.
        denom = len(keep) if scoped else int(umid_n.get(int(y), 0))
        rows.append({
            "year": int(y),
            "u_mid": int(denom),
            "emp_ok": int(sub["employees"].notna().sum()),
            "pay_ok": int(sub["payroll_total"].notna().sum()),
            "c15_ok": int(sub["nl_marginal"].notna().sum()),
            "valid": int(sub["nl_premium"].notna().sum()),
        })
    C = pd.DataFrame(rows)
    LOG.table([[str(r.year), f"{r.u_mid:,}", f"{r.emp_ok:,}", f"{r.pay_ok:,}",
                f"{r.c15_ok:,}", f"{r.valid:,}",
                "구간밖" if (scoped and r.u_mid == 0) else
                ("부족" if r.valid < C15_MIN_OBS_PER_YR else
                 ("경계" if r.valid < COVERAGE_MIN_OBS_START else "충분"))]
               for r in C.itertuples(index=False)],
              ["사업연도", "U-MID 대상", "empSttus 성공", "급여총액 기재", "C15 통과",
               "유효 관측치", "판정"],
              ["c", "r", "r", "r", "r", "r", "c"],
              title="EMP 커버리지 감사 (§6 — 필수 출력) · 분자 모집단 = " +
                    ("U-MID 기업" if scoped else "전 상장사(분모와 불일치, 참고용)"))
    if not scoped:
        LOG.warn("커버리지 분자를 U-MID 로 제한하지 못했습니다(corp_code 매핑 부재). "
                 "비율이 과대평가될 수 있으므로 시작연도 판정을 보수적으로 읽으세요.")
    return C


def coverage_verdict(C: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], str]:
    """§6 판정: 앞구간의 유효 관측치가 부족하면 백테스트 시작월을 상향한다.

    ★ 시작연도 y 의 관측은 그 해 사업보고서(다음해 3~4월 접수)부터 신호가 되므로,
      창을 자를 때도 '사업연도 y' 가 아니라 '실제로 알 수 있게 된 시점'을 기준으로 자른다.
    """
    if C is None or C.empty:
        return None, "커버리지 표가 비어 판정을 유보합니다."

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ 이 판정의 전제: 커버리지 표가 'DART 가 실제로 보유한 양'을 잰다는 것.
    #    예산에 걸려 잘린 실행에서는 그 전제가 깨진다. 수집 잡은 연도 내림차순이라
    #    jobs[:cap] 은 **항상 오래된 연도부터** 버린다 → 커버리지는 최근이 두껍고 과거가
    #    얇은 모양이 되고, 그건 DART 의 사실이 아니라 우리 지갑의 사실이다.
    #    그 모양을 그대로 읽어 COVERAGE_AUTO_TRIM 이 창을 자르면, **일시적 예산 부족이
    #    10년 백테스트를 영구히 단축**시키고 그 단축이 §6 데이터 근거로 리포트에 박힌다.
    #  → 절단이 있었으면 자동 트림을 걸지 않는다. 자를지 말지는 완전 수집 후에 판단한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    trunc = EMP_TRUNCATED.get("dropped", 0)
    if trunc:
        return None, (
            f"이번 실행에서 직원현황 수집이 {trunc:,}건 잘렸습니다"
            f"({EMP_TRUNCATED.get('why', '호출 상한')}). 수집은 최근 연도부터 채우므로 "
            f"아래 표의 과거 연도 부족분은 **DART 의 결측이 아니라 이번 실행의 미수집**입니다. "
            f"이 표를 근거로 백테스트 창을 자르면 일시적 예산 부족이 10년 구간을 영구히 "
            f"단축시킵니다 — 자동 트림을 걸지 않습니다. 재실행으로 수집을 완성한 뒤 재판정하세요.")

    good = C[C["valid"] >= COVERAGE_MIN_OBS_START]
    if good.empty:
        worst = int(C["valid"].max()) if len(C) else 0
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 미만입니다 "
                      f"(최대 {worst:,}건). 창을 자르지 않고 전 구간을 쓰되, "
                      f"EMP 신호의 검정력이 낮다는 사실을 결론에 명시합니다.")
    y0 = int(good["year"].min())
    thin = C[C["year"] < y0]
    if thin.empty:
        return None, (f"전 연도에서 유효 관측치가 {COVERAGE_MIN_OBS_START}건 이상입니다 "
                      f"— 백테스트 창을 그대로 사용합니다.")
    start = as_ts(f"{y0 + 1}-04-01")          # 사업연도 y0 는 y0+1 년 3~4월에 공시된다
    msg = (f"{int(thin['year'].min())}~{int(thin['year'].max())}년 유효 관측치가 "
           f"{COVERAGE_MIN_OBS_START}건 미만(" +
           ", ".join(f"{int(r.year)}:{int(r.valid)}" for r in thin.itertuples(index=False)) +
           f") → EMP 신호 유효 시작 {start:%Y-%m}. ")
    if COVERAGE_AUTO_TRIM:
        msg += "COVERAGE_AUTO_TRIM=True 이므로 EMP TP 를 이 시점 이전에는 결측으로 둡니다."
    else:
        msg += "COVERAGE_AUTO_TRIM=False 이므로 자르지 않고 그대로 진행합니다."
    return (start if COVERAGE_AUTO_TRIM else None), msg
