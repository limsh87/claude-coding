
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  증권사 ↔ 거래원(회원사) 매핑 원장                        [SPEC §5 · config 고정]   ║
# ║                                                                                          ║
# ║  이 전략의 신호는 "A증권이 리포트를 냈다" 와 "A증권 창구에서 순매수가 났다" 를 잇는 것이다.║
# ║  두 이름이 같은 문자열로 오지 않는다는 것이 실무의 전부다:                                 ║
# ║    · 리포트 원장  : "미래에셋증권", "하나증권", "이베스트투자증권"(과거 표기)              ║
# ║    · 거래원 창구  : "미래에셋", "하나금투", "이베스트"  ← 표시명이 짧고 시점마다 다르다     ║
# ║  게다가 사명 변경·합병이 10년 구간에 20건 넘게 일어난다. 정규화하지 않으면 같은 회사가     ║
# ║  시점에 따라 다른 회사가 되어 신호가 조용히 소멸한다.                                      ║
# ║                                                                                          ║
# ║  ★ 규칙 (SPEC §5)                                                                         ║
# ║    · 매핑 실패 건은 버리지 않고 unmapped 로 로그에 남긴다.                                 ║
# ║    · 매핑 실패율이 20% 를 넘으면 진행을 중단하고 보고한다.                                 ║
# ║    · 매핑표는 config/broker_member_map.csv 로 고정 저장하며, 드라이브 공용 인덱스에도      ║
# ║      올려 다른 전략이 그대로 재사용할 수 있게 한다.                                        ║
# ║                                                                                          ║
# ║  ⚠ 이 파일에는 특정 증권사에 대한 어떤 가치판단도 담지 않는다(SPEC §0.5).                  ║
# ║    'RETAIL' / 'FOREIGN' 같은 분류는 창구의 주문 구성이 통계적으로 다르다는 관측일 뿐이다.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BROKER_MAP_CSV = "broker_member_map.csv"

# ★ 비-증권 법인 차단 사전 (가장 먼저 검사한다)
#   '미래에셋' 별칭 하나만 두면 미래에셋생명·미래에셋자산운용까지 미래에셋증권으로 흡수된다.
#   '기업은행' 을 IBK 별칭에 넣으면 IBK기업은행이 IBK투자증권이 된다.
#   '한국투자' 는 한국투자파트너스(VC)를, '키움' 은 키움투자자산운용을 빨아들인다.
#   전부 실제로 일어나는 오매칭이고, 그대로 두면 '자사 창구' 신호에 남의 주문이 섞인다.
NON_BROKER_MARKERS = re.compile(
    r"(생명|화재|손해보험|보험|자산운용|투자자문|파트너스|밸류|벤처|캐피탈|저축은행|"
    r"은행|카드|신탁|리츠|기술투자|창업투자|IR협의회|기업평가|신용평가|거래소|"
    r"연구소|경제연구|리서치센터|애널리스트협회|NICE|나이스|에프앤가이드|FNGUIDE|"
    r"ASSETMANAGEMENT|SECURITIESINVESTMENTTRUST)", re.I)

# tier: MAJOR(대형 리서치) / MID(중소형 리서치) / RETAIL(리테일 주문 비중이 압도적인 창구) /
#       FOREIGN(외국계 창구) / OTHER(증권사가 아니거나 분류 불가 → 이벤트에서 제외)
#
# 별칭 규칙 두 가지 (오매칭을 구조적으로 막는다):
#   · 긴 별칭을 먼저 검사한다 ("한국투자증권" 이 "한국" 에 먹히지 않게)
#   · 짧은 축약 별칭(거래원 창구 표시명)은 '완전일치' 로만 허용한다. 부분포함으로 허용하면
#     "미래에셋" 이 "미래에셋생명" 을 잡는다. 완전일치 전용 별칭은 앞에 '=' 를 붙여 표시한다.
#
# valid_from / valid_to (YYYY-MM-DD, 빈 값=무제한): 사명이 재사용된 경우의 PIT 매핑.
#   ★ 우리투자증권이 대표 사례다. 2014년 NH농협증권과 합병해 NH투자증권이 되었지만,
#     2024-08 우리금융이 한국포스증권+우리종합금융을 합쳐 같은 이름으로 재출범시켰다.
#     시점을 안 보면 2024년 이후 우리투자증권 창구의 주문이 NH 이벤트에 붙는다.
BROKER_MEMBER_SEED: List[Tuple[str, str, str, str, str]] = [
    # (정식 증권사명, tier, "별칭|별칭|...", valid_from, valid_to)
    ("미래에셋증권",   "MAJOR",   "미래에셋증권|미래에셋대우|=미래에셋|대우증권|KDB대우|=대우", "", ""),
    ("NH투자증권",     "MAJOR",   "NH투자증권|NH투자|엔에이치투자|NH농협증권|=NH", "", ""),
    ("NH투자증권",     "MAJOR",   "우리투자증권|우리투자", "", "2014-12-31"),
    ("우리투자증권",   "MID",     "우리투자증권|우리투자|우리종합금융", "2024-08-01", ""),
    ("한국투자증권",   "MAJOR",   "한국투자증권|한국증권|한투증권|=한국투자|=한투", "", ""),
    ("삼성증권",       "MAJOR",   "삼성증권|=삼성", "", ""),
    ("KB증권",         "MAJOR",   "KB증권|KB투자증권|현대증권|케이비증권|=KB", "", ""),
    ("신한투자증권",   "MAJOR",   "신한투자증권|신한금융투자|신한금투|=신한투자|=신한", "", ""),
    ("하나증권",       "MAJOR",   "하나증권|하나금융투자|하나금투|하나대투증권|하나대투|=하나", "", ""),
    ("메리츠증권",     "MAJOR",   "메리츠증권|메리츠종금증권|메리츠종금|아이엠투자증권|=메리츠", "", ""),
    ("키움증권",       "RETAIL",  "키움증권|=키움", "", ""),
    ("대신증권",       "MID",     "대신증권|=대신", "", ""),
    ("유안타증권",     "MID",     "유안타증권|동양증권|=유안타|=동양", "", ""),
    ("한화투자증권",   "MID",     "한화투자증권|한화증권|=한화투자|=한화", "", ""),
    ("교보증권",       "MID",     "교보증권|=교보", "", ""),
    ("IBK투자증권",    "MID",     "IBK투자증권|IBK증권|아이비케이투자증권|=IBK", "", ""),
    ("신영증권",       "MID",     "신영증권|=신영", "", ""),
    ("현대차증권",     "MID",     "현대차증권|현대차투자증권|HMC투자증권|=HMC|=현대차", "", ""),
    ("SK증권",         "MID",     "SK증권|에스케이증권|=SK", "", ""),
    ("유진투자증권",   "MID",     "유진투자증권|유진증권|=유진", "", ""),
    ("iM증권",         "MID",     "iM증권|IM증권|아이엠증권|하이투자증권|하이증권|=하이투자|=하이", "", ""),
    ("LS증권",         "MID",     "LS증권|엘에스증권|이베스트투자증권|EBEST투자증권|"
                                 "=이베스트|=EBEST|=E*BEST", "", ""),
    ("다올투자증권",   "MID",     "다올투자증권|KTB투자증권|=다올|=KTB", "", ""),
    ("DB금융투자",     "MID",     "DB금융투자|디비금융투자|동부증권|DB증권|=DB금투|=DB", "", ""),
    ("BNK투자증권",    "MID",     "BNK투자증권|BNK증권|=BNK", "", ""),
    ("흥국증권",       "MID",     "흥국증권|=흥국", "", ""),
    ("부국증권",       "MID",     "부국증권|=부국", "", ""),
    ("한양증권",       "MID",     "한양증권|=한양", "", ""),
    ("상상인증권",     "MID",     "상상인증권|골든브릿지투자증권|=상상인|=골든브릿지", "", ""),
    ("케이프투자증권", "MID",     "케이프투자증권|LIG투자증권|=케이프|=LIG", "", ""),
    ("토스증권",       "RETAIL",  "토스증권|=토스", "", ""),
    ("카카오페이증권", "RETAIL",  "카카오페이증권|바로투자증권|=카카오페이|=바로투자", "", ""),
    ("리딩투자증권",   "MID",     "리딩투자증권|=리딩투자", "", ""),
    ("코리아에셋투자증권", "MID", "코리아에셋투자증권|=코리아에셋", "", ""),
    ("유화증권",       "MID",     "유화증권|=유화", "", ""),
    ("DS투자증권",     "MID",     "DS투자증권|디에스투자증권|DS증권", "", ""),
    ("한국포스증권",   "MID",     "한국포스증권|포스증권|펀드온라인코리아", "", "2024-07-31"),
    ("교보악사",       "OTHER",   "교보악사", "", ""),
    # ── 외국계 창구 ─────────────────────────────────────────────────────────────────────
    ("모간스탠리",     "FOREIGN", "모간스탠리|모건스탠리|모건스탠리서울|=모건서울|=모간스탠|"
                                 "MORGANSTANLEY|=MS서울", "", ""),
    ("골드만삭스",     "FOREIGN", "골드만삭스|GOLDMANSACHS|=골드만|=GS서울", "", ""),
    ("JP모간",         "FOREIGN", "JP모간|제이피모간|JP모건|JPMORGAN", "", ""),
    ("메릴린치",       "FOREIGN", "메릴린치|BOFA|뱅크오브아메리카|MERRILL|=BOA|=메릴", "", ""),
    ("CS증권",         "FOREIGN", "CS증권|크레디트스위스|크레디스위스|CREDITSUISSE|=CS", "", ""),
    ("UBS",            "FOREIGN", "UBS증권|UBS", "", ""),
    ("씨티그룹",       "FOREIGN", "씨티그룹|한국씨티|CITIGROUP|=씨티|=CITI", "", ""),
    ("도이치",         "FOREIGN", "도이치증권|도이치|DEUTSCHE", "", ""),
    ("HSBC",           "FOREIGN", "HSBC증권|HSBC", "", ""),
    ("노무라",         "FOREIGN", "노무라금융투자|노무라|NOMURA", "", ""),
    ("다이와",         "FOREIGN", "다이와증권|다이와|DAIWA", "", ""),
    ("맥쿼리",         "FOREIGN", "맥쿼리증권|맥쿼리|MACQUARIE", "", ""),
    ("CLSA",           "FOREIGN", "CLSA코리아|CLSA", "", ""),
    ("BNP파리바",      "FOREIGN", "BNP파리바|BNPPARIBAS|=BNP", "", ""),
    ("SG증권",         "FOREIGN", "SG증권|소시에테제네랄|SOCIETEGENERALE|=소시에테", "", ""),
    ("바클레이즈",     "FOREIGN", "바클레이즈|바클레이|BARCLAYS", "", ""),
    ("홍콩상하이",     "FOREIGN", "홍콩상하이", "", ""),
    # ── 비증권 리서치 제공자: 매핑은 하되 tier=OTHER 로 두어 이벤트에서 제외한다 ──────────
    ("한국IR협의회",   "OTHER",   "한국IR협의회|IR협의회", "", ""),
    ("NICE디앤비",     "OTHER",   "NICE디앤비|나이스디앤비", "", ""),
    ("에프앤가이드",   "OTHER",   "에프앤가이드|FNGUIDE", "", ""),
]

# H3(중소형 증권사에서 효과가 강하다) 검정용 그룹 정의 — 사전등록 값. 실행 중 변경 금지.
H3_SMALL_TIERS = ("MID",)                 # '중소형 리서치' 군
H3_LARGE_TIERS = ("MAJOR", "RETAIL")      # '대형/리테일 집중' 군


def _norm_broker_token(s: Any) -> str:
    """비교용 정규화: 공백·괄호·특수문자 제거, 대문자화, '증권/투자증권/금융투자' 접미 제거."""
    t = norm_text(s)
    if not t:
        return ""
    t = re.sub(r"[\s\(\)\[\]\{\}·・,\.\-_/]", "", t)
    t = t.upper()
    for suf in ("주식회사", "㈜"):
        t = t.replace(suf, "")
    return t


class BrokerMap:
    """증권사 정식명 ↔ 거래원 창구 표시명 양방향 원장.  ★ 정규화의 단일 진실원.

    매칭 순서 (오매칭을 구조적으로 막는 순서다):
      0. 비-증권 법인 차단어가 있으면 즉시 None  (미래에셋생명 / 한국투자파트너스 / IBK기업은행)
      1. 완전일치 (별칭·정식명)
      2. 부분포함 — 단 '완전일치 전용(=접두)' 별칭은 제외하고, 긴 별칭부터
      3. 시점(when)이 주어지면 valid_from/valid_to 로 걸러 PIT 매핑을 보장
    """

    def __init__(self, rows: List[dict]):
        self.rows = rows
        self.canon2tier: Dict[str, str] = {}
        # (정규화 별칭, 정식명, exact_only, vfrom, vto)
        self._alias: List[Tuple[str, str, bool, Optional[pd.Timestamp], Optional[pd.Timestamp]]] = []
        for r in rows:
            canon = str(r.get("broker", "")).strip()
            if not canon:
                continue
            tier = str(r.get("tier", "OTHER")).strip() or "OTHER"
            # 같은 canon 이 여러 줄(시점별)로 올 수 있다 — tier 는 첫 값을 유지
            self.canon2tier.setdefault(canon, tier)
            vf = as_ts(r.get("valid_from")) if str(r.get("valid_from", "")).strip() else None
            vt = as_ts(r.get("valid_to")) if str(r.get("valid_to", "")).strip() else None
            toks = [str(r.get("aliases", "")), canon]
            for chunk in toks:
                for a in chunk.split("|"):
                    a = a.strip()
                    if not a:
                        continue
                    exact_only = a.startswith("=")
                    na = _norm_broker_token(a.lstrip("="))
                    if na:
                        self._alias.append((na, canon, exact_only, vf, vt))
        # 긴 별칭 먼저 — "한국투자증권" 이 "한국투자" 보다 먼저 검사되어야 한다
        self._alias = sorted(set(self._alias), key=lambda x: (-len(x[0]), x[0]))
        self.unmapped: Counter = Counter()
        self.hit: Counter = Counter()
        self.blocked: Counter = Counter()

    @staticmethod
    def _in_window(vf, vt, when) -> bool:
        if when is None:
            return True
        t = as_ts(when)
        if t is None:
            return True
        if vf is not None and t < vf:
            return False
        if vt is not None and t > vt:
            return False
        return True

    def resolve(self, raw: Any, when: Any = None) -> Optional[str]:
        """거래원 창구 표시명 또는 리포트 증권사명 → 정식 증권사명. 실패하면 None.

        when 을 주면 그 시점에 유효한 매핑만 쓴다(사명 재사용 대응).
        예) resolve("우리투자증권", "2013-05-01") → "NH투자증권"
            resolve("우리투자증권", "2025-03-01") → "우리투자증권"  (2024-08 재출범 별개 법인)"""
        n = _norm_broker_token(raw)
        if not n:
            return None
        # ── 0) 비증권 법인 차단. 단 정식명과 완전히 같으면 통과시킨다(예: 'NICE디앤비')
        if NON_BROKER_MARKERS.search(n) and not any(
                a == n and not eo for a, c, eo, _, _ in self._alias):
            self.blocked[str(raw)[:40]] += 1
            return None
        # ── 1) 완전일치 (시점 유효한 것 우선)
        exact = [(a, c, vf, vt) for a, c, eo, vf, vt in self._alias if a == n]
        for a, c, vf, vt in exact:
            if self._in_window(vf, vt, when):
                self.hit[c] += 1
                return c
        if exact and when is None:
            self.hit[exact[0][1]] += 1
            return exact[0][1]
        # ── 2) 부분포함 (완전일치 전용 별칭은 건너뛴다)
        for a, c, eo, vf, vt in self._alias:
            if eo or len(a) < 3:
                continue
            if (a in n or n in a) and self._in_window(vf, vt, when):
                self.hit[c] += 1
                return c
        self.unmapped[str(raw)[:40]] += 1
        return None

    def is_broker(self, canon: Optional[str]) -> bool:
        """증권사인가 (OTHER = 비증권 리서치 제공자 등 → 이벤트에서 제외)."""
        return bool(canon) and self.canon2tier.get(canon, "OTHER") != "OTHER"

    def tier(self, canon: Optional[str]) -> str:
        return self.canon2tier.get(canon or "", "OTHER")

    def is_small(self, canon: Optional[str]) -> bool:
        return self.tier(canon) in H3_SMALL_TIERS

    def is_large(self, canon: Optional[str]) -> bool:
        return self.tier(canon) in H3_LARGE_TIERS

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def load_broker_map() -> "BrokerMap":
    """config/broker_member_map.csv 우선 → 드라이브 공용 캐시 → 내장 시드.
    사용자가 CSV 를 손보면 그게 이긴다(수작업 고정 원칙, SPEC §5)."""
    rows: List[dict] = []
    src = "seed"

    # ① 로컬 config/
    for cand in (os.path.join(PROJECT_ROOT, "config", BROKER_MAP_CSV),
                 os.path.join(os.getcwd(), "config", BROKER_MAP_CSV),
                 os.path.join(os.getcwd(), BROKER_MAP_CSV)):
        try:
            if os.path.isfile(cand):
                d = read_csv_utf8(cand, dtype=str).fillna("")
                if {"broker", "aliases"} <= set(d.columns):
                    rows = d.to_dict("records")
                    src = f"csv:{cand}"
                    break
        except Exception as e:                                        # noqa
            LOG.warn(f"매핑 CSV 읽기 실패({cand}): {type(e).__name__} — 다음 후보로 넘어갑니다.")

    # ② 드라이브 공용 캐시 (다른 전략이 이미 만들어 뒀을 수 있다)
    if not rows:
        cached = VAULT.get_table("broker_member_map", scope="shared")
        if cached is not None and len(cached) and {"broker", "aliases"} <= set(cached.columns):
            rows = cached.fillna("").to_dict("records")
            src = "drive:_shared/broker_member_map"

    # ③ 내장 시드
    if not rows:
        rows = [{"broker": b, "tier": t, "aliases": a, "valid_from": vf, "valid_to": vt}
                for b, t, a, vf, vt in BROKER_MEMBER_SEED]

    bm = BrokerMap(rows)

    # 항상 CSV 로 고정 저장 (사용자가 손볼 수 있게) + 공용 인덱스에 적재
    try:
        cfg_dir = os.path.join(PROJECT_ROOT, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        out = bm.to_frame().reindex(
            columns=["broker", "tier", "aliases", "valid_from", "valid_to"]).fillna("")
        # BOM 을 붙여야 엑셀에서 한글이 깨지지 않는다(사용자가 직접 편집하는 파일이다)
        atomic_write_text(os.path.join(cfg_dir, BROKER_MAP_CSV),
                          "﻿" + out.to_csv(index=False, lineterminator="\n"))
        VAULT.put_table("broker_member_map", out, scope="shared", domain="reference",
                        source=src, extra={"note": "증권사↔거래원 회원사 매핑 — 전 전략 공용"})
    except Exception as e:                                            # noqa
        LOG.warn(f"매핑표 저장 실패({type(e).__name__}) — 메모리 상으로는 정상 동작합니다.")

    LOG.ok(f"증권사↔거래원 매핑 원장 {len(rows)}행 적재 (출처={src}) · "
           f"MAJOR {sum(1 for r in rows if r.get('tier')=='MAJOR')} / "
           f"MID {sum(1 for r in rows if r.get('tier')=='MID')} / "
           f"RETAIL {sum(1 for r in rows if r.get('tier')=='RETAIL')} / "
           f"FOREIGN {sum(1 for r in rows if r.get('tier')=='FOREIGN')}")
    return bm


def audit_broker_mapping(bm: "BrokerMap", rep: pd.DataFrame,
                         flow: Optional[pd.DataFrame]) -> dict:
    """SPEC §5: 매핑 성공률 / 사명변경 처리 내역 감사. 실패율 20% 초과 시 중단 신호를 돌려준다."""
    out: Dict[str, Any] = {"ok": True, "report_rate": np.nan, "flow_rate": np.nan}
    rows: List[List[str]] = []

    # ① 리포트 원장 쪽
    if rep is not None and len(rep):
        bcol = "broker_name" if "broker_name" in rep.columns else (
            "broker" if "broker" in rep.columns else "broker_raw")
        b = rep[bcol].astype(str) if bcol in rep.columns else pd.Series(dtype=str)
        when = as_ts_series(rep["pub_date"]) if "pub_date" in rep.columns else None
        # ★ 발간 시점 기준 매핑(사명 재사용 대응)
        if when is not None:
            mapped = pd.Series([bm.resolve(x, w) is not None for x, w in zip(b, when)],
                               index=b.index)
        else:
            mapped = b.map(lambda x: bm.resolve(x) is not None)
        nonblank = float((b.str.strip() != "").mean()) if len(b) else 0.0
        rows.append(["리포트 원장의 증권사명 비공백률", f"{len(b):,}", f"{100*nonblank:5.1f}%",
                     "OK" if nonblank >= 0.90 else "미달"])
        out["broker_fill_rate"] = nonblank
        r = float(mapped.mean()) if len(mapped) else 0.0
        out["report_rate"] = r
        rows.append(["리포트 원장 → 정식 증권사명", f"{len(b):,}", f"{100*r:5.1f}%",
                     "OK" if r >= 0.80 else "미달"])
        bad = b[~mapped].value_counts().head(8)
        if len(bad):
            LOG.info(f"  리포트 미매핑 상위: {dict(bad)}")

    # ② 거래원 플로우 쪽
    if flow is not None and len(flow) and "member_raw" in flow.columns:
        m = flow["member_raw"].astype(str)
        uniq = pd.Series(m.unique())
        mapped_u = uniq.map(lambda x: bm.resolve(x) is not None)
        # 건수 가중 성공률 (희귀 창구 하나가 실패해도 전체가 무너지진 않으므로 둘 다 본다)
        cnt = m.value_counts()
        w = float((cnt[uniq[mapped_u].tolist()].sum() if mapped_u.any() else 0) / max(cnt.sum(), 1))
        out["flow_rate"] = w
        rows.append(["거래원 창구명 → 정식 증권사명", f"{len(m):,}", f"{100*w:5.1f}%",
                     "OK" if w >= 0.80 else "미달"])
        badu = uniq[~mapped_u].tolist()[:10]
        if badu:
            LOG.info(f"  창구 미매핑 표시명(유형): {badu}")
            out["unmapped_members"] = badu

    if not rows:
        LOG.warn("매핑 감사에 쓸 입력(리포트/플로우)이 없습니다 — 감사 생략.")
        return out

    LOG.table(rows, ["매핑 축", "건수", "성공률", "판정"], ["l", "r", "r", "c"],
              title="증권사 ↔ 거래원 회원사 매핑 감사 (SPEC §5)")

    worst = np.nanmin([out.get("report_rate", np.nan), out.get("flow_rate", np.nan)])
    if np.isfinite(worst) and worst < 0.80:
        out["ok"] = False
        LOG.error(f"매핑 실패율이 {100*(1-worst):.0f}% 로 SPEC §5 한계(20%)를 초과했습니다. "
                  f"config/{BROKER_MAP_CSV} 의 aliases 컬럼에 위 미매핑 표시명을 추가한 뒤 "
                  f"다시 실행하세요. (버리지 않고 unmapped 로 전부 로그에 남겼습니다)")
    else:
        LOG.ok("매핑 실패율이 SPEC §5 한계(20%) 이내입니다 — 진행합니다.")

    # 사명변경 처리 내역 (감사 산출물용)
    changes = [
        ("2014", "우리투자증권 + NH농협증권 → NH투자증권"),
        ("2014", "동양증권 → 유안타증권"),
        ("2016", "HMC투자증권 → 현대차투자증권 → 현대차증권"),
        ("2017", "KB투자증권 + 현대증권 → KB증권"),
        ("2016~", "미래에셋증권 + KDB대우증권 → 미래에셋대우 → 미래에셋증권(2021)"),
        ("2018", "동부증권 → DB금융투자"),
        ("2022", "신한금융투자 → 신한투자증권"),
        ("2022", "하나금융투자 → 하나증권"),
        ("2022", "KTB투자증권 → 다올투자증권"),
        ("2024", "이베스트투자증권 → LS증권"),
        ("2024", "하이투자증권 → iM증권"),
        ("2020~", "바로투자증권 → 카카오페이증권 / 토스증권 신규"),
    ]
    out["name_changes"] = changes
    LOG.table([[y, c] for y, c in changes], ["시점", "사명변경·합병 (매핑에 반영됨)"],
              ["c", "l"], title="10년 구간 증권사 사명변경 이력 — 반영 내역")
    return out
