

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  런타임 예산 강제 + DART 재무 수집 사다리 (§5 · §10)                                 ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 존재하는 이유 (실제로 계약을 어긴 사고) ─────────────────────────────────    ║
# ║    한때 여기서 전 종목(3,915사) × 12연도 × 4보고서 = 187,920 건을 단건 API 로 요청했다.   ║
# ║    일일 한도가 20,000 이므로 코드가 스스로 "약 10일 걸립니다"라고 말하면서 그대로         ║
# ║    실행을 시작했다. §10 의 '총 4시간' 은 협상 대상이 아닌데도.                             ║
# ║    문제는 느린 게 아니라 **예산을 넘길 것을 알면서 시작한 것**이다.                        ║
# ║                                                                                          ║
# ║  → 원칙: 견적을 먼저 낸다. 예산에 안 들어가면 시작하지 않는다.                             ║
# ║          더 싼 경로로 내려가고, 그래도 안 되면 '무엇을 못 했는지'를 표로 보고한다.         ║
# ║          임계를 늘려 통과시키지 않는다. 조용히 오래 도는 것은 금지다.                     ║
# ║                                                                                          ║
# ║  수집 사다리 (싼 것부터. 각 단계는 남은 예산 안에서만 돈다)                                 ║
# ║    ① 드라이브 공용 캐시            — 0 호출                                                ║
# ║    ② 재무정보 일괄다운로드(벌크)   — 분기당 1 파일. 되면 여기서 끝난다                     ║
# ║    ③ fnlttMultiAcnt 배치           — 1 호출당 100사. 주요계정만(자본금·자산·부채·자본·매출) ║
# ║    ④ fnlttSinglAcntAll 단건        — 전 계정. ★예산 안에서 '유동성 상위부터'만            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class Deadline:
    """실행 전체의 시계. 각 단계가 '남은 시간'을 물어보고 스스로 줄인다."""

    def __init__(self, total_min: float):
        self.t0 = time.time()
        self.total_s = float(total_min) * 60.0
        self.enforced = not COLD_BUILD_MODE

    def elapsed_s(self) -> float:
        return time.time() - self.t0

    def remain_s(self, budget_min: Optional[float] = None, spent_s: float = 0.0) -> float:
        """남은 초. budget_min 을 주면 '그 단계 예산'과 '전체 잔여' 중 작은 쪽."""
        left_total = self.total_s - self.elapsed_s()
        if budget_min is None:
            return max(0.0, left_total)
        return max(0.0, min(left_total, float(budget_min) * 60.0 - spent_s))

    def over(self) -> bool:
        return self.enforced and self.elapsed_s() > self.total_s

    def report(self):
        el = self.elapsed_s() / 60.0
        pct = 100 * el / max(self.total_s / 60.0, 1e-9)
        (LOG.warn if pct > 100 else LOG.info)(
            f"런타임 예산 — 경과 {el:.1f}분 / 상한 {self.total_s/60:.0f}분 ({pct:.0f}%)"
            + ("  ※ COLD_BUILD_MODE=True 라 강제하지 않습니다" if not self.enforced else ""))


DEADLINE: Optional[Deadline] = None


def dart_calls_left() -> int:
    """오늘 남은 DART 호출 수. 예산 견적의 기준이 된다."""
    try:
        used = int(getattr(DBUDGET, "n", 0) or 0)
    except Exception:
        used = 0
    return max(0, DART_DAILY_LIMIT - used)


def plan_dart_collection(corp_codes: Sequence[str], years: Sequence[int],
                         budget_min: float) -> dict:
    """수집 '계획'을 먼저 세우고 표로 보여준다. 계획 없이 시작하지 않는다.

    반환: {"mode": "bulk"|"batch"|"single"|"cache_only", "corps": [...], "years": [...], ...}
    """
    n_corp, n_year = len(corp_codes), len(years)
    reprts = 4
    need_single = n_corp * n_year * reprts
    need_batch = (math.ceil(n_corp / max(DART_MULTI_BATCH, 1)) * n_year * reprts)
    left_calls = dart_calls_left()
    # 실측 처리율: 단건 ≈ 4.4 call/s (운영 로그 기준), 배치도 호출당 비용은 비슷하다.
    rate = 4.0
    can_do_calls = int(max(0.0, budget_min * 60.0) * rate)
    cap = min(left_calls, can_do_calls)

    rows = [
        ["단건 전량 (fnlttSinglAcntAll)", f"{need_single:,}",
         f"{need_single/rate/3600:.1f}시간", "✘ 예산 초과" if need_single > cap else "✔"],
        ["배치 (fnlttMultiAcnt, 100사/회)", f"{need_batch:,}",
         f"{need_batch/rate/60:.0f}분", "✘ 예산 초과" if need_batch > cap else "✔"],
        ["── 이번 실행 가용", f"{cap:,}",
         f"{budget_min:.0f}분", f"일일잔여 {left_calls:,} · 시간환산 {can_do_calls:,}"],
    ]
    LOG.table(rows, ["경로", "필요 호출", "예상 소요", "예산 판정"], ["l", "r", "r", "l"],
              title="DART 수집 계획 (§5 · §10) — 시작 전에 견적부터 낸다")

    if not COLD_BUILD_MODE and need_single > cap:
        LOG.warn(f"단건 전량은 {need_single:,}회로 이번 실행 예산({cap:,}회)을 "
                 f"{need_single/max(cap,1):.0f}배 초과합니다. 시작하지 않습니다 — "
                 f"싼 경로(벌크→배치)로 내려가고, 단건은 '유동성 상위'부터 예산 안에서만 받습니다. "
                 f"전 종목 콜드빌드를 며칠에 걸쳐 하려면 COLD_BUILD_MODE=True 로 두세요.")
    return {"need_single": need_single, "need_batch": need_batch, "cap": cap,
            "left_calls": left_calls, "rate": rate}


# ── ② 재무정보 일괄다운로드 (벌크) ──────────────────────────────────────────────────────────
#   ★ 이 경로는 '있으면 쓰고 없으면 조용히 내려간다'. 응답을 반드시 검증한다:
#     ZIP 매직바이트(PK) 확인 → 내부 파일 파싱 성공 → 필요한 컬럼 존재.
#     검증을 통과하지 못하면 '벌크 미확인'으로 로깅하고 배치 경로로 간다.
#     (엔드포인트를 추측해서 성공한 척하지 않는다 — 실패는 실패로 보고한다)
DART_BULK_URLS = [
    "https://opendart.fss.or.kr/cmm/downloadFnlttZip.do?fl_nm={fl}",
    "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/download.do?fl_nm={fl}",
]
DART_BULK_NAMES = [
    "{y}_{q}_{fs}.zip",
    "{y}년_{q}_{fs}.zip",
]
_BULK_Q = {"11013": "1분기보고서", "11012": "반기보고서",
           "11014": "3분기보고서", "11011": "사업보고서"}


def fetch_dart_bulk(years: Sequence[int], reprts: Sequence[str]) -> pd.DataFrame:
    """분기 단위 벌크 zip. 종목별 루프 금지(§5). 되면 호출 수가 '분기 수'로 끝난다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_bulk_raw", scope="shared")
    have = set()
    if cached is not None and len(cached):
        have = set(zip(cached["bsns_year"].astype(int), cached["reprt_code"].astype(str)))
        LOG.ok(f"공용 캐시에서 DART 벌크 재무 {len(cached):,}행 재사용 ({len(have)}개 분기)")
    todo = [(int(y), str(r)) for y in years for r in reprts if (int(y), str(r)) not in have]
    if RUN_MODE == "CACHED" or not todo:
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    got, ok_n, fail_n = [], 0, 0
    for y, r in todo:
        if DEADLINE is not None and DEADLINE.over():
            break
        blob = None
        for url_t in DART_BULK_URLS:
            for nm_t in DART_BULK_NAMES:
                fl = nm_t.format(y=y, q=_BULK_Q.get(r, r), fs="재무제표")
                raw = http_get(url_t.format(fl=quote(fl)), source="dart",
                               as_bytes=True, tries=1, timeout=90)
                if raw and len(raw) > 2048 and raw[:2] == b"PK":     # ZIP 매직바이트 검증
                    blob = raw
                    break
            if blob:
                break
        if not blob:
            fail_n += 1
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
            parts = []
            for nm in z.namelist():
                try:
                    d = pd.read_csv(io.BytesIO(z.read(nm)), sep="\t",
                                    dtype=str, encoding="cp949", on_bad_lines="skip")
                except Exception:
                    continue
                if len(d):
                    parts.append(d)
            if not parts:
                fail_n += 1
                continue
            D = pd.concat(parts, ignore_index=True)
            D.columns = [str(c).strip().replace(" ", "") for c in D.columns]
            ren = {"종목코드": "stock_code", "회사명": "corp_name", "재무제표종류": "sj_nm",
                   "항목코드": "account_id", "항목명": "account_nm", "당기금액": "thstrm_amount",
                   "결산기준일": "period_end_raw"}
            D = D.rename(columns={k: v for k, v in ren.items() if k in D.columns})
            if "account_nm" not in D.columns or "thstrm_amount" not in D.columns:
                fail_n += 1
                continue
            D["bsns_year"], D["reprt_code"] = int(y), str(r)
            got.append(D)
            ok_n += 1
        except Exception:
            fail_n += 1

    if not got:
        LOG.info(f"재무정보 일괄다운로드(벌크) 경로를 확인하지 못했습니다 "
                 f"(시도 {len(todo)}분기 · 실패 {fail_n}). 배치 경로로 진행합니다 — "
                 f"K1 의 'Fallback: fnlttMultiAcnt 배치 호출' 규칙 그대로입니다.")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    B = pd.concat(([cached] if cached is not None and len(cached) else []) + got,
                  ignore_index=True)
    VAULT.put_table("dart_bulk_raw", B, scope="shared", domain="dart",
                    source="opendart 재무정보 일괄다운로드")
    LOG.ok(f"DART 벌크 재무 {len(B):,}행 · {ok_n}개 분기 확보 "
           f"(종목별 루프 없이 분기 단위로 — §5)")
    return B


# ── 사다리 실행 ─────────────────────────────────────────────────────────────────────────────
def collect_dart_financials_budgeted(sec: pd.DataFrame, months: pd.DatetimeIndex,
                                     px_daily: Optional[pd.DataFrame],
                                     budget_min: float) -> pd.DataFrame:
    """예산 안에서 최대한 받는다. 예산을 넘길 것 같으면 '시작하지 않고' 줄인다."""
    t_start = time.time()
    ccs_all = sec["corp_code"].dropna().astype(str).unique().tolist()
    yrs = sorted({int(m.year) for m in months} | {int(months[0].year) - 1})
    reprts = [REPRT_CODES[k] for k in ("Q1", "H1", "Q3", "FY")]
    plan = plan_dart_collection(ccs_all, yrs, budget_min)

    frames: List[pd.DataFrame] = []

    # ② 벌크 (되면 여기서 대부분 끝난다)
    B = fetch_dart_bulk(yrs, reprts)
    if B is not None and len(B):
        frames.append(B)

    def _spent() -> float:
        return time.time() - t_start

    def _left_min() -> float:
        if DEADLINE is None:
            return max(0.0, budget_min - _spent() / 60.0)
        return DEADLINE.remain_s(budget_min, _spent()) / 60.0

    # ③ 배치 (주요계정) — 자본금·자산·부채·자본·매출·영업이익·순이익
    if _left_min() > 1 and plan["need_batch"] <= plan["cap"] * 3:
        try:
            M = fetch_dart_multi_accounts(ccs_all, yrs)
            if M is not None and len(M):
                frames.append(M)
        except Exception as e:                                     # noqa
            LOG.warn(f"DART 주요계정 배치 실패({type(e).__name__}) — 단건 경로로 넘어갑니다.")
    else:
        LOG.warn("남은 예산이 부족해 주요계정 배치를 건너뜁니다.")

    # ④ 단건 (전 계정) — ★유동성 상위부터, 예산 안에서만
    left_min = _left_min()
    rate = plan["rate"]
    cap_calls = int(min(dart_calls_left(), max(0.0, left_min) * 60.0 * rate))
    if COLD_BUILD_MODE:
        cap_calls = dart_calls_left()
        LOG.warn("COLD_BUILD_MODE=True — 단건 수집의 예산 강제를 해제합니다. "
                 "이 실행은 §10 의 4시간 제약을 지키지 않을 수 있습니다(의도된 선택).")
    if cap_calls > 0:
        prio = _liquidity_priority(sec, px_daily)
        n_corp_afford = max(1, cap_calls // (len(yrs) * len(reprts)))
        pick = prio[:n_corp_afford] if prio else ccs_all[:n_corp_afford]
        LOG.info(f"단건 전 계정 수집 — 예산 {cap_calls:,}회로 유동성 상위 "
                 f"{len(pick):,}사 × {len(yrs)}연도 × {len(reprts)}보고서. "
                 f"(전 종목 {len(ccs_all):,}사 중 {100*len(pick)/max(len(ccs_all),1):.0f}%)")
        try:
            F = fetch_dart_financials(pick, yrs, priority=pick)
            if F is not None and len(F):
                frames.append(F)
        except Exception as e:                                     # noqa
            LOG.warn(f"DART 단건 수집 실패({type(e).__name__}) — 받은 분량으로 진행합니다.")
    else:
        LOG.warn("남은 예산이 없어 단건 전 계정 수집을 건너뜁니다 — "
                 "재고·매출원가·영업CF·이자비용이 결측이 되어 증거층이 얇아집니다. "
                 "다음 실행에서 캐시에 이어받습니다(진행분은 이미 저장됨).")

    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    out = pd.concat([f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                     for f in frames], ignore_index=True)
    LOG.ok(f"DART 재무 원시 {len(out):,}행 확보 — 소요 {_spent()/60:.1f}분 "
           f"(예산 {budget_min:.0f}분)")
    return out


def _liquidity_priority(sec: pd.DataFrame, px_daily: Optional[pd.DataFrame]) -> List[str]:
    """거래대금 상위 순 corp_code. 예산이 부족할 때 '무엇을 먼저 받을지'의 기준.

    ★ 유동성 상위부터 받는 이유: U-MICRO 는 adv20 ≥ 하한을 요구하므로, 유동성이 없는
      종목은 어차피 유니버스에 못 들어온다. 예산이 잘릴 때 버려질 종목을 먼저 버리는 것이
      가장 손실이 적다. (유니버스 '정의'를 바꾸는 게 아니라 '수집 순서'만 바꾼다)
    """
    if px_daily is None or len(px_daily) == 0 or "amount" not in px_daily.columns:
        return []
    try:
        amt = (px_daily.groupby("code", observed=True)["amount"].median()
               .sort_values(ascending=False))
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict())
        out, seen = [], set()
        for code in amt.index:
            cc = c2c.get(str(code))
            if cc and cc not in seen:
                seen.add(cc)
                out.append(cc)
        return out
    except Exception:
        return []
