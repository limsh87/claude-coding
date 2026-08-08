# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  CANARY — 코드가 본격적으로 돌기 전에 '축이 살아있는가'를 실측한다.                         ║
# ║                                                                                             ║
# ║  ★ FAIL 항목에 의존하는 단계는 큐에서 제거하고, 그 사실을 표에 남긴다.                      ║
# ║    없는 것을 있는 척하지 않는다 — 조용히 빈 값으로 진행하는 것이 최악이다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

CANARY_LOG: "List[dict]" = []


def _cn(cid: str, name: str, status: str, detail: str, kill: bool = False) -> None:
    CANARY_LOG.append({"ID": cid, "확인": name, "결과": status, "실측": detail})
    icon = {"PASS": "✔", "FAIL": "✘", "DEGRADED": "⚠", "N/A": "—"}.get(status, "·")
    (LOG.ok if status == "PASS" else LOG.warn if status != "FAIL" else LOG.error)(
        f"{icon} [{cid}] {name}: {status} — {detail[:120]}")
    if kill and status == "FAIL":
        KILL_LOG.append({"id": cid, "name": name, "detail": detail})


def run_canary(sample_hs: str = "854370") -> "pd.DataFrame":
    """X1~X6 · K1~K11. 실측만 기록하고 추측하지 않는다."""
    LOG.banner("CANARY — 축 유효성 실측",
               "이 표의 FAIL 은 해당 축을 죽인다. 통과시키지 않고 그대로 보고한다.")

    # ── X1~X4: 관세청
    cli = CustomsClient(DATA_GO_KR_KEY)
    pr = cli.probe(sample_hs=sample_hs)
    if not pr["endpoint"]:
        _cn("X1", "통관 중량·금액 동시 제공", "FAIL",
            f"관세청 API 응답 없음 — {pr['detail'][:100]}. "
            f"A축 4센서가 전부 죽으므로 이 전략은 성립하지 않습니다.", kill=True)
        _cn("X2", "기간 일괄조회", "N/A", "엔드포인트 미확보")
        _cn("X3", "HS×국가 분해", "N/A", "엔드포인트 미확보")
        _cn("X4", "2016-01 소급", "N/A", "엔드포인트 미확보")
    else:
        both = pr["weight"] and pr["value"]
        _cn("X1", "통관 중량(kg)·금액(USD) 동시 제공", "PASS" if both else "FAIL",
            f"{pr['endpoint']} — 중량 {'O' if pr['weight'] else 'X'} / "
            f"금액 {'O' if pr['value'] else 'X'}. "
            + ("단가 축(a2)이 성립합니다." if both else "단가 축 사망 — 전략 폐기 대상입니다."),
            kill=True)
        _cn("X2", "기간(strt~end) 일괄조회", "PASS" if pr["range"] else "DEGRADED",
            "지원 — 단, 제공기관 제한으로 **12개월 창**으로 잘라 호출합니다."
            if pr["range"] else
            "미지원 — 월별 개별호출로 전환합니다(호출 수 약 120배). 병렬을 낮게 유지합니다.")
        _cn("X3", "HS × 국가 분해", "PASS" if pr["country"] else "DEGRADED",
            "국가별 분해 제공 — a3(HHI)·a4(선진시장) 활성화."
            if pr["country"] else
            "국가 분해 없음 — a3·a4 및 cv_dest(V10) 비활성화, 품목 단독으로 진행합니다.")
        _cn("X4", "2016-01 소급 조회", "PASS" if pr["back2016"] else "DEGRADED",
            "2016-01 조회 성공." if pr["back2016"] else
            "2016-01 미제공 — 실제 최초 제공 시점으로 백테스트 시작일을 상향해야 합니다.")

    # ── X5: 현행화 크기 (C18-d)
    rev = customs_revision_probe(DATA_GO_KR_KEY, sample_hs, "201801")
    if rev["measurable"]:
        big = rev["diff_pct"] > 1.0
        _cn("X5", "관세청 현행화(소급수정) 크기", "DEGRADED" if big else "PASS", rev["detail"])
    else:
        _cn("X5", "관세청 현행화(소급수정) 크기", "N/A", rev["detail"])

    # ── X6: HS–KSIC 연계표
    conc, st6 = fetch_hs_ksic_concordance()
    _cn("X6", "HS–KSIC 연계표", "PASS" if st6 == "OK" else
        ("DEGRADED" if st6 == "DEGRADED" else "FAIL"),
        f"{len(conc):,}행 확보 ({st6}). "
        + ("" if st6 == "OK" else
           "내장 씨앗표(章↔KSIC 중분류) 사용 — 매핑 정밀도가 낮으므로 "
           "게이트1·2·3 판정이 그만큼 더 중요합니다."),
        kill=(st6 == "FAIL"))

    # ── K1/K2: DART
    if not DART_API_KEY:
        _cn("K1", "DART 재무 확보", "FAIL",
            "DART_API_KEY 가 비어 있습니다 — B·C축과 V1/V2/V5/V11, θ_X 가 전부 죽습니다.",
            kill=True)
        _cn("K2", "DART 최초 제공 분기", "N/A", "키 없음")
    else:
        js = dart_api("list.json", {"bgn_de": "20160101", "end_de": "20160131",
                                    "page_count": "10"})
        ok = bool(js and str(js.get("status")) == "000")
        _cn("K1", "DART 접근", "PASS" if ok else "FAIL",
            f"list.json status={js.get('status') if js else 'None'} "
            f"({DART_STATUS_MSG.get(str(js.get('status')) if js else '', '')[:60]})",
            kill=not ok)
        _cn("K2", "2016Q1 소급", "PASS" if ok else "N/A",
            "2016-01 공시 목록 조회 성공." if ok else "키 확인 필요")

    # ── K5: 상장폐지 목록 (C2 생존자편향)
    try:
        dl = fetch_fdr_delisting()
    except Exception as e:                                              # noqa
        dl = None
        LOG.debug(f"상장폐지 목록 조회 실패: {type(e).__name__}")
    nd = 0 if dl is None else len(dl)
    _cn("K5", "상장폐지 목록", "PASS" if nd > 100 else "FAIL",
        f"{nd:,}건 확보. " + ("생존자편향 제거(C2) 가능." if nd > 100 else
                              "상장폐지 목록 없이는 생존자편향을 제거할 수 없습니다 — 중단 대상."),
        kill=(nd <= 100))

    # ── K11: 리서치 목록
    n_rep = 0
    try:
        if FOREIGN is not None:
            rp = foreign_reports(FOREIGN)
            n_rep = len(rp)
    except Exception as e:                                              # noqa
        LOG.debug(f"리포트 원장 확인 실패: {type(e).__name__}")
    _cn("K11", "애널리스트 리포트 원장", "PASS" if n_rep > 1000 else "DEGRADED",
        f"드라이브 캐시에서 {n_rep:,}건 확인. "
        + ("d2/d4 활성화." if n_rep > 1000 else
           "부족 — d2/d4 를 비활성화하고 U 를 d1·d3 로 구성합니다."))

    # ── K12: KRX 없이 생존자편향 제거 + PIT 유니버스가 성립하는가 (사용자 요구 확인 항목)
    try:
        sec_probe = build_security_master_nokrx()
        aud = audit_survivorship(sec_probe, _months(), phase="pre")
        # 캐너리 시점에는 가격이 없어 폐지일 복원 전이다. '폐지 종목이 마스터에 존재하는가'
        # 까지만 본다. 폐지일 정확성의 최종 판정은 가격 수집 뒤 L1.PRICE 에서 한다.
        n_dead = int(sec_probe.get("src", pd.Series("", index=sec_probe.index))
                     .astype(str).str.contains("delist").sum())
        _cn("K12", "KRX 비의존 유니버스·생존자편향",
            "PASS" if (len(sec_probe) > 1000 and n_dead > 200) else "FAIL",
            f"KRX 모드={krx_mode()} · 마스터 {len(sec_probe):,}종목 · 폐지 종목 {n_dead:,}건 "
            f"포함 · 상장일 확보율 {aud['listing_known']*100:.0f}% "
            f"(폐지일은 가격 수집 후 마지막 거래일로 복원)",
            kill=(len(sec_probe) <= 1000 or n_dead <= 200))
    except Exception as e:                                              # noqa
        _cn("K12", "KRX 비의존 유니버스·생존자편향", "FAIL",
            f"{type(e).__name__}: {e} — 상장/폐지 목록 소스를 확인하세요.", kill=True)

    C = pd.DataFrame(CANARY_LOG)
    LOG.table([[r["ID"], r["확인"][:30], r["결과"], r["실측"][:56]] for _, r in C.iterrows()],
              ["ID", "확인", "결과", "실측"])
    return C
