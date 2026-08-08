# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  관세청 통관 수집 — 이 전략의 유일한 대체 데이터원                                          ║
# ║                                                                                             ║
# ║  ★ 계약 C18 (이 전략 고유) — 소급 수정 데이터의 보수적 PIT                                  ║
# ║   (a) 관세청은 매월 15일경 정정·취하를 반영해 전월까지 자료를 '현행화'한다.                  ║
# ║       따라서 시점 t 에 실제로 공표되었던 원값은 사후 복원이 불가능하다.                      ║
# ║   (b) knowledge_date = 귀속월의 **익월 말일**로 고정한다.                                    ║
# ║       실제 공표(익월 15일경)보다 약 15일 보수적이며, 이 여유가 소급 수정 위험을 흡수한다.    ║
# ║   (c) 오늘부터 매월 스냅샷을 raw 캐시에 적재한다. 복원 불가 자산이므로                       ║
# ║       오늘 켜지 않으면 2년 뒤에도 2년치다.                                                   ║
# ║   (d) X5 실측(현행화 크기)을 리포트에 명시한다. 1% 초과면 상향 편의 경고를 출력한다.         ║
# ║                                                                                             ║
# ║  ⚠ "확정치를 쓰면 되지 않나"로 우회하지 말 것. 확정치는 다음 연도에 나오므로 선행성을        ║
# ║    통째로 반납하고, 그러면 이 전략의 존재 이유가 사라진다.                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 공공데이터포털 관세청 오픈API 후보. 스펙이 바뀌어도 죽지 않도록 **여러 후보를 순서대로 탐침**한다.
#   추측한 파라미터명을 하드코딩해 두면 이름 하나가 달라진 순간 조용히 빈 프레임이 되고,
#   그게 이 전략에서 가장 위험한 실패다(A축 전체가 사라지는데 예외는 안 난다).
CUSTOMS_ENDPOINTS: "list[dict]" = [
    {
        "name": "품목별 국가별 수출입실적",
        "url": "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
        "has_country": True,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm", "country": "cntyCd"},
    },
    {
        "name": "품목별 국가별 수출입실적(대체경로)",
        "url": "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
        "has_country": True,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm", "country": "cntyCd"},
    },
    {
        "name": "품목별 수출입실적",
        "url": "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList",
        "has_country": False,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm"},
    },
]

# 응답 필드 별칭 — 스펙 문서와 실제 응답이 다른 경우가 잦다.
CUSTOMS_FIELD_ALIAS = {
    "hs":      ("hsCd", "hsSgn", "hsCode", "hs_cd"),
    # ★ statKor 는 **품목명**이다. 국가명은 statCdCntnKor1 이다.
    #   이걸 뒤집으면 국가군 축약이 품목명 기준으로 돌아가 목적지 축(a3·a4)이 통째로 망가진다.
    "hs_name": ("statKor", "hsCdNm", "hsNm", "korPrlstNm", "prlstNm"),
    "country": ("statCd", "cntyCd", "cntrCd", "natCd"),
    "cty_name": ("statCdCntnKor1", "cntyNm", "statCdNm", "korNm"),
    "period":  ("year", "yymm", "statYymm", "prid"),
    "exp_usd": ("expDlr", "expUsd", "expAmt"),
    "exp_wgt": ("expWgt", "expWt", "expQty"),
    "imp_usd": ("impDlr", "impUsd", "impAmt"),
    "imp_wgt": ("impWgt", "impWt", "impQty"),
}

# 국가군 축약 (§6.1). 230개국을 그대로 들고 다니면 행이 10배가 되고 얻는 것이 없다.
COUNTRY_GROUPS: "dict[str, str]" = {
    "US": "US", "CN": "CN", "JP": "JP", "TW": "TW", "DE": "DE", "VN": "VN", "IN": "IN",
    "HK": "CN", "MO": "CN",
    "FR": "EU", "IT": "EU", "NL": "EU", "BE": "EU", "ES": "EU", "PL": "EU", "SE": "EU",
    "AT": "EU", "CZ": "EU", "HU": "EU", "SK": "EU", "DK": "EU", "FI": "EU", "IE": "EU",
    "PT": "EU", "GR": "EU", "RO": "EU", "BG": "EU", "SI": "EU", "HR": "EU", "LT": "EU",
    "LV": "EU", "EE": "EU", "LU": "EU", "CY": "EU", "MT": "EU", "GB": "EU",
    "TH": "ASEAN", "MY": "ASEAN", "ID": "ASEAN", "PH": "ASEAN", "SG": "ASEAN",
    "MM": "ASEAN", "KH": "ASEAN", "LA": "ASEAN", "BN": "ASEAN",
    "SA": "ME", "AE": "ME", "QA": "ME", "KW": "ME", "OM": "ME", "BH": "ME", "IL": "ME",
    "TR": "ME", "IR": "ME", "IQ": "ME", "JO": "ME", "EG": "ME",
    "BR": "LATAM", "MX": "LATAM", "CL": "LATAM", "AR": "LATAM", "PE": "LATAM",
    "CO": "LATAM", "PA": "LATAM",
    "AU": "OCE", "NZ": "OCE",
    "RU": "CIS", "KZ": "CIS", "UZ": "CIS", "UA": "CIS",
    "CA": "NA_OTH",
}


def _country_group(code: Any, name: Any = "") -> str:
    c = str(code or "").strip().upper()
    if c in COUNTRY_GROUPS:
        return COUNTRY_GROUPS[c]
    return "OTHER" if c else "OTHER"


def customs_knowledge_date(ym: pd.Series) -> pd.Series:
    """C18-(b): knowledge_date = 귀속월의 익월 말일.

    귀속 2018-03 → 알 수 있게 되는 시점 2018-04-30.
    실제 공표는 04-15경이므로 약 15일 보수적이다. 이 여유가 소급 수정 위험을 흡수한다.
    """
    t = as_ts_series(ym)
    return (t + pd.offsets.MonthEnd(1)).astype("datetime64[ns]")


def _cpick(row: dict, names: "Sequence[str]") -> Any:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    # 대소문자 무시 재시도
    low = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(str(n).lower())
        if v not in (None, ""):
            return v
    return None


def _cnum(x: Any) -> float:
    """천단위 콤마·공백을 제거하고 실수로. 실패하면 NaN."""
    if x is None:
        return float("nan")
    t = str(x).replace(",", "").replace(" ", "").strip()
    if t in ("", "-", "--"):
        return float("nan")
    try:
        return float(t)
    except Exception:                                                   # noqa
        return float("nan")


def _customs_parse(items: "Sequence[dict]", has_country: bool) -> pd.DataFrame:
    """응답 아이템 목록 → 표준 스키마. 별칭표로 필드명 변화를 흡수한다."""
    if not items:
        return pd.DataFrame(columns=["hs", "ym", "country", "exp_wgt", "exp_usd",
                                     "imp_wgt", "imp_usd"])
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        per = str(_cpick(it, CUSTOMS_FIELD_ALIAS["period"]) or "").strip()
        # 'year' 필드가 총계행에서는 '2018' 처럼 연도만 오기도 한다 → 월이 없으면 버린다.
        digits = "".join(ch for ch in per if ch.isdigit())
        if len(digits) < 6:
            continue
        ym = pd.Timestamp(f"{digits[:4]}-{digits[4:6]}-01") + pd.offsets.MonthEnd(0)
        hs = str(_cpick(it, CUSTOMS_FIELD_ALIAS["hs"]) or "").strip()
        # ★ 응답은 상세행과 '총계' 집계행을 섞어서 준다. 총계를 걸러내지 않으면
        #   물량·금액이 정확히 두 배가 되고 단가는 멀쩡해 보여 발견이 매우 어렵다.
        if not hs or hs in ("-", "총계", "합계"):
            continue
        ccode = _cpick(it, CUSTOMS_FIELD_ALIAS["country"]) if has_country else "ALL"
        cname = _cpick(it, CUSTOMS_FIELD_ALIAS["cty_name"]) if has_country else ""
        rows.append({
            "hs": hs,
            "ym": ym,
            "country": _country_group(ccode, cname) if has_country else "ALL",
            # ★ 숫자가 "12,300" 처럼 천단위 콤마를 달고 온다. to_numeric 은 이를 NaN 으로
            #   만들어 버리므로, 큰 값일수록 결측이 되는 체계적 편의가 생긴다.
            "exp_usd": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["exp_usd"])),
            "exp_wgt": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["exp_wgt"])),
            "imp_usd": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["imp_usd"])),
            "imp_wgt": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["imp_wgt"])),
        })
    d = pd.DataFrame(rows)
    if not len(d):
        return d
    # 국가군으로 축약했으므로 같은 (hs, ym, group) 이 여러 국가에서 온다 → 합산.
    d = d.groupby(["hs", "ym", "country"], observed=True, as_index=False).sum(numeric_only=True)
    return d


def _extract_items(payload: Any) -> "list[dict]":
    """공공데이터포털 응답에서 item 리스트를 꺼낸다. 래핑 구조가 서비스마다 다르다."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    # response.body.items.item  /  response.body.items  /  items.item …
    for path in (("response", "body", "items", "item"),
                 ("response", "body", "items"),
                 ("body", "items", "item"),
                 ("items", "item"), ("items",), ("item",)):
        cur: Any = payload
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            if isinstance(cur, dict):
                return [cur]
            if isinstance(cur, list):
                return [x for x in cur if isinstance(x, dict)]
    return []


def _customs_error(payload: Any) -> str:
    """오류 응답이면 한국어 진단 문자열을, 정상이면 빈 문자열을 돌려준다."""
    if not isinstance(payload, dict):
        return ""
    txt = json.dumps(payload, ensure_ascii=False)[:400]
    for key, msg in (
        ("SERVICE_KEY_IS_NOT_REGISTERED", "인증키가 등록되지 않았습니다. "
         "data.go.kr 에서 이 API 를 '활용신청'했는지, **Decoding 키**를 넣었는지 확인하세요."),
        ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "일일 트래픽 한도를 초과했습니다. "
         "내일 다시 시도하거나 활용신청에서 한도를 늘리세요."),
        ("SERVICE_ACCESS_DENIED", "접근이 거부되었습니다. 활용신청 승인 상태를 확인하세요."),
        ("DEADLINE_HAS_EXPIRED", "활용신청 기간이 만료되었습니다. 연장 신청이 필요합니다."),
        ("UNKNOWN_ERROR", "제공기관 내부 오류입니다. 잠시 후 재시도합니다."),
        ("NODATA", ""),
    ):
        if key in txt:
            return msg or ""
    # resultCode 가 00 이 아니면 오류로 본다
    for path in (("response", "header", "resultCode"), ("resultCode",)):
        cur: Any = payload
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is not None and str(cur) not in ("00", "0", "000"):
            return f"제공기관 응답코드 {cur}: {txt[:160]}"
    return ""


class CustomsClient:
    """관세청 오픈API 클라이언트. 엔드포인트/파라미터를 실행 시점에 탐침해 확정한다."""

    def __init__(self, key: str):
        self.key = (key or "").strip()
        self.ep: Optional[dict] = None
        self.range_ok: Optional[bool] = None       # X2: 기간 일괄조회 지원 여부
        self.fail_streak = 0
        self.calls = 0
        self.diag: List[str] = []

    # ── 저수준 호출 ------------------------------------------------------------------
    def _call(self, ep: dict, hs: str, start: str, end: str,
              country: Optional[str] = None, rows: int = 1000) -> Tuple[Any, str]:
        p = ep["params"]
        params = {
            "serviceKey": self.key,
            p["hs"]: hs,
            p["start"]: start,
            p["end"]: end,
            "type": "json",
            "numOfRows": rows,
            "pageNo": 1,
        }
        if country and ep.get("has_country") and "country" in p:
            params[p["country"]] = country
        # ★ http_get 은 응답객체가 아니라 **본문 문자열**을 돌려준다(실패 시 None).
        #   r.json() 을 부르면 AttributeError 로 A축 수집이 통째로 죽는다.
        try:
            txt = http_get(ep["url"], params=params, source="customs", timeout=30)
        except Exception as e:                                          # noqa
            return None, f"{type(e).__name__}: {e}"
        if not txt:
            return None, "응답 없음"
        if isinstance(txt, bytes):
            txt = txt.decode("utf-8", "replace")
        s = txt.lstrip()
        if s[:1] in ("{", "["):
            try:
                payload = json.loads(txt)
            except Exception:                                           # noqa
                return None, "JSON 파싱 실패"
            return payload, _customs_error(payload)
        if s[:1] == "<":
            low = s[:400].lower()
            if "<html" in low or "<!doctype" in low:
                return None, "HTML 응답(인증 실패·차단 의심)"
            # 다수 서비스가 type=json 을 무시하고 XML 로만 응답한다.
            xml = _xml_items(txt)
            if xml is None:
                # 오류도 XML 로 온다 — 사유를 뽑아 준다.
                for key in ("SERVICE_KEY_IS_NOT_REGISTERED", "LIMITED_NUMBER_OF_SERVICE_REQUESTS",
                            "SERVICE_ACCESS_DENIED", "DEADLINE_HAS_EXPIRED"):
                    if key in txt:
                        return None, _customs_error({"msg": key})
                return None, f"XML 파싱 실패: {s[:120]}"
            return xml, ""
        return None, f"알 수 없는 응답 형식: {s[:120]}"

    # ── 탐침 ---------------------------------------------------------------------------
    def probe(self, sample_hs: str = "854370") -> dict:
        """CANARY X1~X4 를 겸한다. 어떤 엔드포인트가 살아있고 무엇을 주는지 실측한다."""
        out = {"endpoint": "", "weight": False, "value": False, "country": False,
               "range": False, "back2016": False, "detail": ""}
        if not self.key:
            out["detail"] = "DATA_GO_KR_KEY 가 비어 있습니다."
            return out
        for ep in CUSTOMS_ENDPOINTS:
            payload, err = self._call(ep, sample_hs, "202401", "202403")
            items = _extract_items(payload)
            if err:
                self.diag.append(f"{ep['name']}: {err}")
            if not items:
                continue
            d = _customs_parse(items, ep.get("has_country", False))
            if not len(d):
                continue
            self.ep = ep
            out["endpoint"] = ep["name"]
            out["weight"] = bool(pd.to_numeric(d["exp_wgt"], errors="coerce").notna().any())
            out["value"] = bool(pd.to_numeric(d["exp_usd"], errors="coerce").notna().any())
            out["country"] = bool(ep.get("has_country") and d["country"].nunique() > 1)
            # X2: 기간 일괄조회가 진짜 되는가 — 서로 다른 월이 2개 이상 나와야 한다.
            out["range"] = bool(d["ym"].nunique() >= 2)
            self.range_ok = out["range"]
            # X4: 2016-01 소급
            p2, _e2 = self._call(ep, sample_hs, "201601", "201603")
            out["back2016"] = bool(len(_customs_parse(_extract_items(p2),
                                                      ep.get("has_country", False))))
            out["detail"] = f"{ep['url']}"
            break
        if not self.ep:
            out["detail"] = "; ".join(self.diag[:3]) or "모든 후보 엔드포인트가 응답하지 않았습니다."
        return out

    # ── 수집 ---------------------------------------------------------------------------
    def fetch_hs(self, hs: str, start: str, end: str) -> pd.DataFrame:
        if self.ep is None or self.fail_streak >= 15:
            return pd.DataFrame()
        chunks: List[pd.DataFrame] = []
        # ★ 기간 일괄조회는 지원되지만 **1년 이내**로 제한된다(포털 샘플 주석: 조회기간 1년이내).
        #   10년을 한 번에 던지면 조용히 잘린 결과가 오거나 오류가 난다 —
        #   둘 다 'A축이 일부만 채워진 채 통과'라서 가장 위험하다. 반드시 12개월로 자른다.
        spans = _year_spans(start, end) if self.range_ok else _month_spans(start, end)
        for s, e in spans:
            payload, err = self._call(self.ep, hs, s, e)
            self.calls += 1
            if err:
                self.fail_streak += 1
                if self.fail_streak >= 15:
                    LOG.error(f"관세청 연속 실패 15회 — 서킷브레이커 작동. 마지막 오류: {err}")
                    break
                continue
            items = _extract_items(payload)
            if items:
                self.fail_streak = 0
                d = _customs_parse(items, self.ep.get("has_country", False))
                if len(d):
                    chunks.append(d)
        if not chunks:
            return pd.DataFrame()
        return pd.concat(chunks, ignore_index=True).drop_duplicates(["hs", "ym", "country"])


def _year_spans(start: str, end: str, months: int = 12) -> "list[tuple]":
    """[start, end] 를 최대 12개월 창으로 자른다. 제공기관의 하드 제한이다."""
    s = pd.Timestamp(f"{start[:4]}-{start[4:6]}-01")
    e = pd.Timestamp(f"{end[:4]}-{end[4:6]}-01")
    out = []
    cur = s
    while cur <= e:
        nxt = min(e, cur + pd.DateOffset(months=months - 1))
        out.append((cur.strftime("%Y%m"), nxt.strftime("%Y%m")))
        cur = nxt + pd.DateOffset(months=1)
    return out


def _month_spans(start: str, end: str) -> "list[tuple]":
    """X2 FAIL 시 월별 개별 조회로 떨어진다. 호출 수가 126배가 되므로 로그로 경고한다."""
    s = pd.Timestamp(f"{start[:4]}-{start[4:6]}-01")
    e = pd.Timestamp(f"{end[:4]}-{end[4:6]}-01")
    out = []
    cur = s
    while cur <= e:
        t = cur.strftime("%Y%m")
        out.append((t, t))
        cur = cur + pd.offsets.MonthBegin(1)
    return out


def _xml_items(text: str) -> Any:
    """JSON 이 아닌 XML 응답을 최소한으로 파싱한다(의존성 추가 없이)."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception:                                                   # noqa
        return None
    items = []
    for it in root.iter("item"):
        items.append({ch.tag: (ch.text or "").strip() for ch in it})
    return {"response": {"body": {"items": {"item": items}}}} if items else None


def ingest_customs(hs_list: "Sequence[str]", start: str, end: str,
                   key: str = "") -> pd.DataFrame:
    """관세청 통관 수집. 드라이브 캐시 우선 → 부족분만 신규 → 재적재.

    반환: hs, ym, country, exp_wgt(kg), exp_usd(USD), imp_wgt, imp_usd, knowledge_date
    """
    cols = ["hs", "ym", "country", "exp_wgt", "exp_usd", "imp_wgt", "imp_usd", "knowledge_date"]
    hs_list = [str(h) for h in dict.fromkeys(hs_list)]
    if not hs_list:
        return pd.DataFrame(columns=cols)

    # ① 캐시 (공용 — 다른 전략도 그대로 쓸 수 있는 원본 정제본)
    cached = VAULT.get_table("customs_hs_country_monthly", scope="shared")
    if cached is None and FOREIGN is not None:
        cached = FOREIGN.load("customs_hs", "customs_hs_country_monthly", "customs",
                              alias=FOREIGN_ALIAS_CUSTOMS)
    need = list(hs_list)
    if cached is not None and len(cached):
        cached["hs"] = cached["hs"].astype(str)
        cached["ym"] = as_ts_series(cached["ym"])
        # ★★ 캐시 적중 판정 버그 — 실측으로 확인한 6분/실행 낭비 ★★
        #   요청 키는 **조회용 HS 접두사**("28" 같은 章)인데, 캐시에 저장된 hs 는 응답으로 온
        #   **6자리 코드**("280110"…)다. `q in set(cached_hs)` 로 비교하면 영원히 불일치라
        #   매 실행 전량을 다시 받는다(실측: 610콜 × 2단계 = 12분).
        #   → HS 는 좌측 정렬 계층코드이므로 **접두사 포함**으로 판정하고, 기간까지 확인한다.
        cached_hs = cached["hs"].unique().astype(str)
        lo = pd.Timestamp(f"{start[:4]}-{start[4:6]}-01")
        hi = pd.Timestamp(f"{end[:4]}-{end[4:6]}-01") + pd.offsets.MonthEnd(0)
        need = []
        for q in hs_list:
            hit = cached_hs[np.char.startswith(cached_hs.astype(str), str(q))]
            if not len(hit):
                need.append(q)
                continue
            sub_ym = cached.loc[cached["hs"].isin(set(hit)), "ym"]
            # 요청 구간의 앞뒤가 캐시 범위 안에 들어와야 '이미 받았다'고 본다.
            if sub_ym.min() > lo + pd.DateOffset(months=1) or \
               sub_ym.max() < hi - pd.DateOffset(months=2):
                need.append(q)
        LOG.ok(f"통관 캐시 재사용: {len(cached):,}행 · HS {len(cached_hs):,}개 "
               f"(요청 {len(hs_list)}건 중 {len(hs_list) - len(need)}건 적중 · "
               f"신규 {len(need)}건)")
    fresh = pd.DataFrame(columns=cols)
    if need and RUN_MODE != "CACHED":
        cli = CustomsClient(key or DATA_GO_KR_KEY)
        if cli.ep is None:
            pr = cli.probe(sample_hs=need[0])
            if not pr["endpoint"]:
                LOG.error(f"관세청 API 를 사용할 수 없습니다 — {pr['detail']}")
                need = []
        if need:
            if cli.range_ok is False:
                LOG.warn(f"기간 일괄조회(X2) 미지원 — 월별 개별호출로 전환합니다. "
                         f"호출 수가 약 {len(_month_spans(start, end))}배가 됩니다.")
            res = pmap_io(lambda h: cli.fetch_hs(h, start, end), need,
                          workers=min(N_WORKERS_IO, 8), desc="관세청 통관")
            good = [d for d in res if d is not None and len(d)]
            if good:
                fresh = pd.concat(good, ignore_index=True)
            LOG.info(f"관세청 신규 수집: HS {len(need)}개 요청 → {len(fresh):,}행 "
                     f"({cli.calls:,}콜)")

    parts = [d for d in (cached, fresh) if d is not None and len(d)]
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    out["hs"] = out["hs"].astype(str)
    out["ym"] = as_ts_series(out["ym"])
    out = out.dropna(subset=["ym"]).drop_duplicates(["hs", "ym", "country"], keep="last")
    # C18-(b)
    out["knowledge_date"] = customs_knowledge_date(out["ym"])

    # ② 재적재 — 공용 인덱스(다른 전략 재사용) + 사용자 기존 공용 레지스트리에도 등록
    if len(fresh):
        VAULT.put_table("customs_hs_country_monthly", out, scope="shared",
                        source="data.go.kr/관세청")
        if FOREIGN is not None:
            foreign_publish_common(FOREIGN, "customs_hs_country_monthly", out,
                                   ["hs", "ym", "country"], "TCD_XCB")
        _customs_snapshot(fresh)
    return out.reindex(columns=cols)


def _customs_snapshot(fresh: pd.DataFrame) -> None:
    """C18-(c): 오늘 받은 값을 그대로 스냅샷으로 남긴다.

    관세청이 매월 현행화하므로 '오늘 시점에 무엇이 공표되어 있었는가'는 오늘만 기록할 수 있다.
    복원 불가 자산이라 오늘 켜지 않으면 2년 뒤에도 2년치다.
    """
    try:
        tag = _dt.datetime.now().strftime("%Y%m%d")
        VAULT.put_table(f"customs_snapshot_{tag}", fresh, scope="private",
                        source="C18-(c) 현행화 추적용 스냅샷")
    except Exception as e:                                              # noqa
        LOG.debug(f"통관 스냅샷 저장 실패(무시): {type(e).__name__}")


def customs_revision_probe(key: str, hs: str, ym_old: str) -> dict:
    """CANARY X5 — 현행화 크기 실측.

    같은 과거월을 (a) 이번 실행에서 받은 값과 (b) 과거 스냅샷에 남아 있는 값으로 비교한다.
    스냅샷이 아직 없으면 '측정 불가'로 정직하게 보고한다 — 없는 것을 있는 척하지 않는다.
    """
    out = {"measurable": False, "diff_pct": float("nan"), "detail": ""}
    snaps = []
    try:
        tdir = VAULT.table_dir("private")
        snaps = sorted(f for f in os.listdir(tdir) if f.startswith("customs_snapshot_"))
    except Exception:                                                   # noqa
        pass
    if len(snaps) < 1:
        out["detail"] = ("과거 스냅샷이 없어 현행화 크기를 아직 실측할 수 없습니다. "
                         "이번 실행이 첫 스냅샷을 남깁니다(C18-c). "
                         "→ 보수적 knowledge_date(익월 말일)로 위험을 흡수합니다.")
        return out
    old = read_parquet_safe(os.path.join(VAULT.table_dir("private"), snaps[0]))
    cur = VAULT.get_table("customs_hs_country_monthly", scope="shared")
    if old is None or cur is None or not len(old) or not len(cur):
        out["detail"] = "스냅샷 또는 현재 테이블을 읽지 못했습니다."
        return out
    k = ["hs", "ym", "country"]
    for d in (old, cur):
        d["hs"] = d["hs"].astype(str)
        d["ym"] = as_ts_series(d["ym"])
    j = old.merge(cur, on=k, how="inner", suffixes=("_old", "_new"))
    if not len(j):
        out["detail"] = "겹치는 관측이 없습니다."
        return out
    a = pd.to_numeric(j["exp_usd_old"], errors="coerce")
    b = pd.to_numeric(j["exp_usd_new"], errors="coerce")
    tot = a.sum()
    out["measurable"] = True
    out["diff_pct"] = float(abs(b.sum() - tot) / tot * 100.0) if tot else float("nan")
    out["detail"] = f"겹치는 {len(j):,}관측 기준 총액 차이 {out['diff_pct']:.3f}%"
    if out["diff_pct"] > 1.0:
        LOG.warn(f"[C18-d] 관세청 현행화 크기 {out['diff_pct']:.2f}% > 1% — "
                 f"백테스트 성과에 상향 편의가 있을 수 있습니다. 리포트에 명시합니다.")
    return out
