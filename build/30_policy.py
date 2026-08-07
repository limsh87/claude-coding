

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  정책 캘린더 (§12) — 모든 센서팩의 필수 자산 (C12)                                   ║
# ║                                                                                          ║
# ║  모든 대체데이터는 정책에 오염된다. 이건 PACK-N 고유 문제가 아니다.                          ║
# ║  정책 시행일은 공개되어 있고 정확하다 → 그래서 이 오염만은 자연실험 설계가 가능하다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

POLICY_COLS = ["policy_id", "name", "start", "end", "pack", "req_type", "req_value", "url"]


def build_policy_calendar() -> pd.DataFrame:
    rows = []
    for pid, p in PACK_REGISTRY.items():
        for e in p["policy"]:
            r = {c: e.get(c) for c in POLICY_COLS}
            r["pack"] = r.get("pack") or pid
            rows.append(r)
    # 전 팩 공통 매크로 이벤트 (팩 무관하게 신호-수익 관계를 흔드는 국면)
    rows += [
        {"policy_id": "COVID_CRASH", "name": "코로나 급락/급반등", "start": "2020-02-20",
         "end": "2020-09-30", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORT_BAN_2020", "name": "공매도 전면금지", "start": "2020-03-16",
         "end": "2021-05-02", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORT_BAN_2023", "name": "공매도 전면금지(2차)", "start": "2023-11-06",
         "end": "2025-03-31", "pack": "*", "req_type": "없음", "req_value": ""},
    ]
    C = pd.DataFrame(rows, columns=POLICY_COLS)
    C["start"] = as_ts_series(C["start"])
    C["end"] = as_ts_series(C["end"]).fillna(as_ts(BACKTEST_END))
    C = C.dropna(subset=["start"]).drop_duplicates("policy_id")
    LOG.ok(f"정책 캘린더 {len(C)}건 등록 (C12 — 캘린더 없는 팩은 등록 자체가 불가)")
    PIPE.io("OUT", "MEM", "policy_calendar", C)
    return C


def policy_windows(cal: pd.DataFrame, packs: Sequence[str], months: pd.DatetimeIndex,
                   halo_months: int = 6) -> pd.Series:
    """정책 이벤트 ±6개월 구간 마스크. R10 검정 C(이벤트 구간 제외)의 입력."""
    mask = pd.Series(False, index=months)
    sel = cal[cal["pack"].isin(list(packs) + ["*"])]
    for r in sel.itertuples(index=False):
        lo = r.start - pd.DateOffset(months=halo_months)
        hi = r.start + pd.DateOffset(months=halo_months)
        mask |= (months >= lo) & (months <= hi)
        if pd.notna(r.end) and r.end < as_ts(BACKTEST_END):
            mask |= (months >= r.end - pd.DateOffset(months=halo_months)) & \
                    (months <= r.end + pd.DateOffset(months=halo_months))
    return mask


def report_policy(cal: pd.DataFrame, months: pd.DatetimeIndex, packs: Sequence[str]):
    m = policy_windows(cal, packs, months)
    LOG.table([[r.policy_id, _trunc(r.name, 34), str(r.start)[:10],
                str(r.end)[:10] if pd.notna(r.end) else "-", r.pack,
                f"{r.req_type}:{r.req_value}"[:24]] for r in cal.itertuples(index=False)],
              ["ID", "제도명", "시행", "종료", "대상팩", "요건"],
              ["l", "l", "l", "l", "c", "l"], title="정책 캘린더 (§12)")
    LOG.info(f"정책 이벤트 ±6개월 구간: 전체 {len(months)}개월 중 {int(m.sum())}개월 "
             f"({100*m.mean():.0f}%) — R10 검정 C 에서 이 구간을 제외하고 재검정합니다.")
    if m.mean() > 0.75:
        LOG.warn("정책 구간이 전체의 75%를 넘습니다. 검정 C 의 잔여 표본이 부족해 "
                 "R10 결론의 검정력이 낮아집니다. 이 한계를 결과 해석에 반영하세요.")
