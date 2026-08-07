# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  정책 캘린더 (R10 정책반증의 입력)                                                         ║
# ║                                                                                          ║
# ║  모든 대체데이터는 정책에 오염된다. 다만 정책 시행일은 공개되어 있고 정확하다               ║
# ║  → 이 오염만은 자연실험 설계가 가능하다. 이벤트 ±6개월을 빼고도 알파가 남는지 본다.         ║
# ║                                                                                          ║
# ║  ★ 고용 관련 제도를 빠짐없이 넣는 것이 이 전략에서 특히 중요하다. TP_N1(한계임금)은         ║
# ║    설계상 보조금 채용을 걸러내지만, '걸러진다'는 주장 자체를 R10 이 반증해야 한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

POLICY_COLS_V3 = ["policy_id", "name", "start", "end", "kind", "req_type", "req_value", "url"]

POLICY_EVENTS_V3 = [
    # ── 고용 보조금·장려금 (TP_N1 의 직접 오염원) ──────────────────────────────────────────
    {"policy_id": "YOUTH_TOMORROW_2016", "name": "청년내일채움공제 시행", "start": "2016-07-01",
     "end": "2021-12-31", "kind": "고용장려금", "req_type": "연령·근속", "req_value": "만15~34세"},
    {"policy_id": "PUBLIC_REGULAR_2017", "name": "공공부문 비정규직 정규직 전환 지침",
     "start": "2017-07-20", "end": None, "kind": "고용규제", "req_type": "고용형태", "req_value": "비정규직"},
    {"policy_id": "MINWAGE_2018", "name": "최저임금 16.4% 인상", "start": "2018-01-01",
     "end": None, "kind": "임금규제", "req_type": "임금", "req_value": "7,530원"},
    {"policy_id": "JOB_STABILITY_FUND", "name": "일자리안정자금 시행", "start": "2018-01-01",
     "end": "2022-12-31", "kind": "고용장려금", "req_type": "규모", "req_value": "30인 미만"},
    {"policy_id": "EMP_INCREASE_TAXCREDIT", "name": "고용증대 세액공제 도입", "start": "2018-01-01",
     "end": "2022-12-31", "kind": "세액공제", "req_type": "고용증가", "req_value": "상시근로자 증가"},
    {"policy_id": "DURUNURI_EXPAND", "name": "두루누리 사회보험료 지원 확대", "start": "2018-01-01",
     "end": None, "kind": "고용장려금", "req_type": "규모·임금", "req_value": "10인 미만"},
    {"policy_id": "YOUTH_ADDL_HIRE_2018", "name": "청년추가고용장려금", "start": "2018-03-15",
     "end": "2021-12-31", "kind": "고용장려금", "req_type": "청년 신규채용", "req_value": "1인당 연 900만원"},
    {"policy_id": "WORKWEEK_52_L", "name": "주52시간제 (300인 이상)", "start": "2018-07-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "300인 이상"},
    {"policy_id": "MINWAGE_2019", "name": "최저임금 10.9% 인상", "start": "2019-01-01",
     "end": None, "kind": "임금규제", "req_type": "임금", "req_value": "8,350원"},
    {"policy_id": "WORKWEEK_52_M", "name": "주52시간제 (50~299인)", "start": "2020-01-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "50~299인"},
    {"policy_id": "COVID_EMP_RETAIN", "name": "코로나 고용유지지원금 특례 확대", "start": "2020-03-01",
     "end": "2022-06-30", "kind": "고용장려금", "req_type": "휴업·휴직", "req_value": "인건비 최대 90%"},
    {"policy_id": "WORKWEEK_52_S", "name": "주52시간제 (5~49인)", "start": "2021-07-01",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "5~49인"},
    {"policy_id": "YOUTH_LEAP_2022", "name": "청년일자리도약장려금", "start": "2022-01-01",
     "end": None, "kind": "고용장려금", "req_type": "청년 신규채용", "req_value": "1인당 연 960만원"},
    {"policy_id": "SERIOUS_ACCIDENT_ACT", "name": "중대재해처벌법 시행", "start": "2022-01-27",
     "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "50인 이상"},
    {"policy_id": "INTEGRATED_EMP_TAXCREDIT", "name": "통합고용세액공제 전환", "start": "2023-01-01",
     "end": None, "kind": "세액공제", "req_type": "고용증가", "req_value": "상시근로자 증가"},
    {"policy_id": "SERIOUS_ACCIDENT_SMALL", "name": "중대재해처벌법 (50인 미만) 확대",
     "start": "2024-01-27", "end": None, "kind": "고용규제", "req_type": "규모", "req_value": "5~49인"},

    # ── 자본배분 (TP_P1/TP_P2 의 레짐 의존성) ──────────────────────────────────────────────
    {"policy_id": "VALUEUP_2024", "name": "기업 밸류업 프로그램 발표", "start": "2024-02-26",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "VALUEUP_INDEX_2024", "name": "코리아 밸류업 지수 발표", "start": "2024-09-24",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "DIV_SEPARATE_TAX", "name": "배당소득 분리과세 논의/시행", "start": "2025-01-01",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},
    {"policy_id": "TREASURY_CANCEL_REFORM", "name": "자사주 소각 관련 제도 변경", "start": "2025-01-01",
     "end": None, "kind": "자본배분", "req_type": "없음", "req_value": ""},

    # ── 시장 전체 레짐 (신호-수익 관계 자체를 흔드는 국면) ─────────────────────────────────
    {"policy_id": "COVID_CRASH", "name": "코로나 급락/급반등", "start": "2020-02-20",
     "end": "2020-09-30", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
    {"policy_id": "SHORT_BAN_2020", "name": "공매도 전면금지(1차)", "start": "2020-03-16",
     "end": "2021-05-02", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
    {"policy_id": "SHORT_BAN_2023", "name": "공매도 전면금지(2차)", "start": "2023-11-06",
     "end": "2025-03-31", "kind": "시장레짐", "req_type": "없음", "req_value": ""},
]

# R10 이 제외 대상으로 삼는 종류 — '고용' 관련만 뺀다. 시장레짐까지 빼면 표본이 남지 않는다.
R10_KINDS = ("고용장려금", "세액공제", "고용규제", "임금규제")


def build_policy_calendar_v3() -> pd.DataFrame:
    C = pd.DataFrame(POLICY_EVENTS_V3, columns=POLICY_COLS_V3)
    C["start"] = as_ts_series(C["start"])
    C["end"] = as_ts_series(C["end"]).fillna(as_ts(BACKTEST_END))
    C = C.dropna(subset=["start"]).drop_duplicates("policy_id").reset_index(drop=True)
    LOG.ok(f"정책 캘린더 {len(C)}건 등록 "
           f"(고용 관련 {int(C['kind'].isin(R10_KINDS).sum())}건 · R10 제외 대상)")
    PIPE.io("OUT", "MEM", "policy_calendar", C)
    return C


def policy_mask(cal: pd.DataFrame, months: pd.DatetimeIndex,
                kinds: Sequence[str] = R10_KINDS, halo_months: int = 6) -> pd.Series:
    """정책 이벤트 시행일·종료일 ±halo 개월 마스크 (True = 정책 구간)."""
    m = pd.Series(False, index=months)
    sel = cal[cal["kind"].isin(list(kinds))]
    for r in sel.itertuples(index=False):
        lo = r.start - pd.DateOffset(months=halo_months)
        hi = r.start + pd.DateOffset(months=halo_months)
        m |= (months >= lo) & (months <= hi)
        if pd.notna(r.end) and r.end < as_ts(BACKTEST_END):
            m |= (months >= r.end - pd.DateOffset(months=halo_months)) & \
                 (months <= r.end + pd.DateOffset(months=halo_months))
    return m


def report_policy_v3(cal: pd.DataFrame, months: pd.DatetimeIndex):
    LOG.table([[r.policy_id, _trunc(r.name, 30), str(r.start)[:10],
                str(r.end)[:10] if pd.notna(r.end) else "-", r.kind,
                _trunc(f"{r.req_type}:{r.req_value}", 22)]
               for r in cal.itertuples(index=False)],
              ["ID", "제도명", "시행", "종료", "종류", "요건"],
              ["l", "l", "l", "l", "c", "l"], title="정책 캘린더 (R10 입력)", maxw=34)
    m = policy_mask(cal, months)
    LOG.info(f"고용정책 ±6개월 구간: 전체 {len(months)}개월 중 {int(m.sum())}개월 "
             f"({100*m.mean():.0f}%) — R10 은 이 구간을 빼고 재검정합니다.")
    if m.mean() > 0.75:
        LOG.warn("정책 구간이 전체의 75%를 넘습니다. R10 잔여 표본이 얇아 검정력이 낮습니다. "
                 "이 한계를 결론 해석에 반드시 반영하세요.")
