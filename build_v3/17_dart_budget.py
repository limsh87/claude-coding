

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


class LayerBudget:
    """수집층(L1) 예산 — **단계별로** 재고, 넘기면 그 단계부터 캐시 전용으로 강등한다.

    ★ 총량만 재는 것은 예산이 아니다. 실측 사고에서 L1.RSRCH 하나가 126분을 먹어
      L1 합계가 배정의 6.1배가 됐는데도, 총 wall-clock 줄은 '4시간 안'이라며 통과시켰다.
      단계마다 상한이 없으면 한 단계가 나머지 전부의 예산을 먹고, 그 사실이 표에 안 남는다.
    """

    def __init__(self, total_min: float, alloc: Dict[str, float]):
        self.t0 = time.time()
        self.total_s = float(total_min) * 60.0
        self.alloc = dict(alloc)
        self.spent: Dict[str, float] = {}
        self.demoted: List[str] = []

    def elapsed_s(self) -> float:
        return time.time() - self.t0

    def stage_left_s(self, sid: str) -> float:
        """이 단계에 남은 초 = min(단계 배정, L1 전체 잔여, 전체 실행 잔여)."""
        s = float(self.alloc.get(sid, 5.0)) * 60.0 - float(self.spent.get(sid, 0.0))
        s = min(s, self.total_s - self.elapsed_s())
        if DEADLINE is not None:
            s = min(s, DEADLINE.remain_s())
        return max(0.0, s)

    def record(self, sid: str, dur_s: float):
        self.spent[sid] = float(self.spent.get(sid, 0.0)) + float(dur_s)

    def report(self) -> pd.DataFrame:
        rows = []
        for sid, al in self.alloc.items():
            sp = float(self.spent.get(sid, 0.0))
            over = sp > al * 60.0 + 1e-9
            rows.append([sid, f"{sp/60:.1f}분", f"{al:.0f}분",
                         ("❗초과" if over else "✔") +
                         (" · 캐시전용 강등" if sid in self.demoted else "")])
        tot = sum(self.spent.values())
        rows.append(["── L1 합계", f"{tot/60:.1f}분", f"{self.total_s/60:.0f}분",
                     "❗초과" if tot > self.total_s else "✔ 예산 내"])
        return pd.DataFrame(rows, columns=["단계", "실측", "배정", "판정"])


L1BUDGET: Optional[LayerBudget] = None


def l1_guard(sid: str) -> bool:
    """단계 진입 시 호출. 배정을 이미 소진했으면 이 단계를 캐시 전용으로 강등한다.

    ★ 강등은 조용히 하지 않는다. 무엇을 못 받게 되는지 로그에 남기고, 마지막
      런타임 감사표에 '캐시전용 강등'으로 표시한다.
    """
    global RUN_MODE
    if COLD_BUILD_MODE or L1BUDGET is None or RUN_MODE == "CACHED":
        return False
    if L1BUDGET.stage_left_s(sid) > 5.0:
        return False
    RUN_MODE = "CACHED"
    L1BUDGET.demoted.append(sid)
    LOG.warn(f"[{sid}] 수집 예산(L1 {COLLECT_BUDGET_MIN}분)을 소진했습니다 — "
             f"이 단계부터 **신규 수집을 중단하고 드라이브 캐시만** 사용합니다. "
             f"받지 못한 부분은 다음 실행이 정확히 이어받습니다. "
             f"예산을 넘겨 조용히 계속 도는 것보다, 무엇을 못 받았는지 표로 남기는 쪽이 "
             f"§10 계약을 지키는 방법입니다. 콜드빌드를 끝까지 돌리려면 "
             f"COLD_BUILD_MODE=True 로 두세요.")
    return True


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
        ["① 벌크 ZIP (사용자 제공 파일)", "0",
         "즉시", "재고·매출채권·매출원가·영업CF 전부", "✔ 있으면 최우선"],
        ["② 배치 fnlttMultiAcnt (100사/회)", f"{need_batch:,}",
         f"{need_batch/rate/60:.1f}분", "주요계정 14종(BS+IS). 현금흐름표 없음",
         "✘ 예산 초과" if need_batch > cap else "✔ 예산 내"],
        ["③ 단건 fnlttSinglAcntAll (1사/회)", f"{need_single:,}",
         f"{need_single/rate/3600:.1f}시간", "전 계정. 회전일수·이자보상배율 보강용",
         "✘ 예산 초과" if need_single > cap else "✔ 예산 내"],
        ["── 이번 실행 가용 호출", f"{cap:,}", f"{budget_min:.0f}분",
         f"일일잔여 {left_calls:,} · 시간환산 {can_do_calls:,}", ""],
    ]
    LOG.table(rows, ["경로", "필요 호출", "예상 소요", "얻는 것", "예산 판정"],
              ["l", "r", "r", "l", "l"], maxw=44,
              title="DART 수집 계획 (§5 · §10) — 시작 전에 견적부터 낸다")
    LOG.info("★ 이 전략의 증거층 3센서(i_sales·i_turn·i_accr)는 ②만으로 전부 산출됩니다. "
             "③은 '있으면 더 좋은' 보강이지 필수가 아닙니다 — 그래서 ③이 예산을 넘겨도 "
             "백테스트는 정상적으로 끝납니다.")

    if not COLD_BUILD_MODE and need_single > cap:
        LOG.warn(f"③ 단건 전량은 {need_single:,}회로 이번 실행 예산({cap:,}회)을 "
                 f"{need_single/max(cap,1):.0f}배 초과합니다. **시작하지 않습니다.** "
                 f"②로 E층을 완성하고, ③은 '유동성 상위'부터 예산 안에서만 받아 캐시에 "
                 f"쌓습니다(다음 실행이 이어받습니다). "
                 f"전 종목 콜드빌드를 며칠에 걸쳐 하려면 COLD_BUILD_MODE=True 로 두세요.")
    return {"need_single": need_single, "need_batch": need_batch, "cap": cap,
            "left_calls": left_calls, "rate": rate}


# ── ② 재무정보 일괄다운로드 (벌크 ZIP) ──────────────────────────────────────────────────────
#   ★ 사실관계부터 정확히 (검증 결과) ─────────────────────────────────────────────────────
#     OpenDART 의 '재무정보 일괄다운로드'는 **OpenAPI 가 아니다.**
#       · 위치: https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do  (로그인 불필요)
#       · 다운로드는 페이지의 자바스크립트 클릭 핸들러로 동작하며, crtfc_key 로 부를 수 있는
#         /api/ 엔드포인트가 존재하지 않는다. 실제로 공개된 어떤 래퍼도 이 경로를 구현하지
#         못했고, 자동화한 사례는 전부 셀레늄으로 브라우저를 몬다.
#     → 그래서 **URL 을 추측해 때려보지 않는다.** 이전 버전은 추측한 두 URL 을 48분기 ×
#       2패턴으로 시도해 25분을 버렸다. 실패를 실패로 보고하지 않고 시간을 태우는 코드다.
#
#   ★ 대신 이렇게 한다 (§5 '종목별 루프 금지'를 지키는 유일하게 정직한 방법) ──────────────
#     사용자가 위 페이지에서 받은 ZIP 을 드라이브 폴더에 넣어두면 이 코드가 읽어들인다.
#     한 번만 받아두면 그 뒤로는 영구히 공용 인덱스에서 재사용된다(API 호출 0회).
#     ZIP 안에는 재고자산·매출채권·매출원가·영업활동현금흐름이 전부 들어 있다 —
#     즉 이 전략의 증거층을 '가장 완전한 형태'로 채우는 유일한 무료 경로다.
DART_BULK_SUBDIR = "dart_bulk"          # {GDRIVE_ROOT}/dart_bulk 도 자동으로 훑는다
_BULK_SJ = {"재무상태표": "BS", "손익계산서": "IS", "포괄손익계산서": "CIS",
            "현금흐름표": "CF", "자본변동표": "SCE"}
_BULK_REPRT = {"1분기보고서": "11013", "반기보고서": "11012",
               "3분기보고서": "11014", "사업보고서": "11011"}


def _bulk_parse_one(name: str, raw: bytes) -> Optional[pd.DataFrame]:
    """일괄다운로드 txt 1개 → _FS_KEEP 스키마. 탭구분 · CP949 · 컬럼명은 '이름'으로 찾는다."""
    sj = next((v for k, v in _BULK_SJ.items() if k in name), None)
    rep = next((v for k, v in _BULK_REPRT.items() if k in name), None)
    yr = re.search(r"(20\d{2})", name)
    if not sj or not rep or not yr:
        return None
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            d = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, encoding=enc,
                            on_bad_lines="skip")
            break
        except Exception:
            d = None
    if d is None or not len(d):
        return None
    d.columns = [str(c).strip().replace(" ", "") for c in d.columns]
    need = {"종목코드", "항목코드", "항목명"}
    if not need <= set(d.columns):
        return None

    def _pick(prefix: str, want_cum: bool) -> Optional[str]:
        cs = [c for c in d.columns if c.startswith(prefix)]
        if not cs:
            return None
        if want_cum:
            cum = [c for c in cs if "누적" in c]
            if cum:
                return cum[0]
        return cs[0]

    flow = sj in ("IS", "CIS", "CF")
    c_cur, c_cum = _pick("당기", False), (_pick("당기", True) if flow else None)
    c_pv, c_pc = _pick("전기", False), (_pick("전기", True) if flow else None)
    if not c_cur:
        return None
    out = pd.DataFrame({
        "corp_code": None,
        "bsns_year": int(yr.group(1)),
        "reprt_code": rep,
        "fs_div": np.where(d["재무제표종류"].astype(str).str.contains("연결", na=False)
                           if "재무제표종류" in d.columns else False, "CFS", "OFS"),
        "sj_div": sj,
        "account_id": d["항목코드"],
        "account_nm": d["항목명"],
        "thstrm_amount": d[c_cur],
        "thstrm_add_amount": d[c_cum] if (c_cum and c_cum != c_cur) else None,
        "frmtrm_amount": d[c_pv] if c_pv else None,
        "frmtrm_q_amount": None,
        "frmtrm_add_amount": d[c_pc] if (c_pc and c_pc != c_pv) else None,
        "bfefrmtrm_amount": None,
        "rcept_no": None,
    })
    out["_stock_code"] = d["종목코드"].astype(str).str.replace(r"[\[\]\s]", "", regex=True)
    return out


def ingest_dart_bulk_files(sec: pd.DataFrame) -> pd.DataFrame:
    """드라이브/로컬에 놓인 '재무정보 일괄다운로드' ZIP 을 읽어들인다. API 호출 0회."""
    cached = VAULT.get_table("dart_bulk_raw", scope="shared")
    dirs = [d for d in (list(globals().get("DART_BULK_DIRS", []))
                        + [os.path.join(VAULT.root, DART_BULK_SUBDIR)]) if d]
    zips: List[str] = []
    for root in dirs:
        try:
            if not os.path.isdir(root):
                continue
            for dp, _dn, fn in os.walk(root):
                zips += [os.path.join(dp, f) for f in fn if f.lower().endswith(".zip")]
        except Exception:
            continue
    zips = sorted(set(zips))
    if not zips:
        LOG.info("재무정보 일괄다운로드 ZIP 이 없습니다 — 배치(주요계정) 경로로 진행합니다. "
                 "★ 증거층을 가장 완전하게 채우고 싶다면 "
                 "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do 에서 "
                 f"연도·보고서별 ZIP 을 받아 '{os.path.join(VAULT.root, DART_BULK_SUBDIR)}' 에 "
                 "넣어두세요. 한 번만 넣으면 이후 실행은 영구히 재사용합니다(API 호출 0회).")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    LOG.info(f"재무정보 일괄다운로드 ZIP {len(zips)}개를 읽습니다 (API 호출 0회 · §5 벌크 경로)")
    parts, n_file = [], 0
    for zp in zips:
        try:
            with zipfile.ZipFile(zp) as z:
                for nm in z.namelist():
                    if not nm.lower().endswith((".txt", ".csv")):
                        continue
                    p = _bulk_parse_one(os.path.basename(nm), z.read(nm))
                    if p is not None and len(p):
                        parts.append(p)
                        n_file += 1
        except Exception as e:                                     # noqa
            LOG.warn(f"ZIP 읽기 실패 {os.path.basename(zp)} ({type(e).__name__}) — 건너뜁니다.")
    if not parts:
        LOG.warn("ZIP 은 있으나 인식 가능한 재무 텍스트 파일이 없습니다 "
                 "(탭구분 · CP949 · '종목코드/항목코드/항목명' 컬럼 필요).")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    B = pd.concat(parts, ignore_index=True)
    # 종목코드 → corp_code. 벌크 파일에는 corp_code 가 없다.
    link = (sec.dropna(subset=["corp_code"])[["code", "corp_code"]]
               .assign(code=lambda x: x["code"].astype(str).str.zfill(6),
                       corp_code=lambda x: x["corp_code"].astype(str))
               .drop_duplicates("code"))
    B["_stock_code"] = B["_stock_code"].map(to_code6)
    B = B.merge(link.rename(columns={"code": "_stock_code"}), on="_stock_code", how="left",
                suffixes=("", "_m"))
    B["corp_code"] = B["corp_code"].where(B["corp_code"].notna(), B.get("corp_code_m"))
    n_nolink = int(B["corp_code"].isna().sum())
    B = B.dropna(subset=["corp_code"])
    if n_nolink:
        LOG.info(f"벌크 {n_nolink:,}행은 종목코드↔법인코드 매핑이 없어 제외했습니다 "
                 f"(비상장·합병소멸 법인).")
    B = B[[c for c in _FS_KEEP if c in B.columns]]
    B = pd.concat(([cached] if cached is not None and len(cached) else []) + [B],
                  ignore_index=True)
    B = B.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                           "account_nm"], keep="last")
    VAULT.put_table("dart_bulk_raw", B, scope="shared", domain="dart",
                    source="opendart 재무정보 일괄다운로드(사용자 제공 ZIP)")
    LOG.ok(f"벌크 재무 {len(B):,}행 · 파일 {n_file}개 · {B['corp_code'].nunique():,}사 "
           f"— 재고·매출채권·매출원가·영업CF 포함. API 호출 0회로 확보했습니다.")
    PIPE.io("IN", "DRIVE", "dart_bulk_raw", B, source="재무정보 일괄다운로드 ZIP")
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

    # ② 벌크 ZIP (사용자가 넣어둔 파일 · API 호출 0회). 있으면 증거층이 가장 완전해진다.
    B = ingest_dart_bulk_files(sec)
    if B is not None and len(B):
        frames.append(B)

    def _spent() -> float:
        return time.time() - t_start

    def _left_min() -> float:
        if DEADLINE is None:
            return max(0.0, budget_min - _spent() / 60.0)
        return DEADLINE.remain_s(budget_min, _spent()) / 60.0

    # ③ 배치 (주요계정 14종) — 유동자산·유동부채·이익잉여금·자본금·자산·부채·자본·매출·
    #    영업이익·당기순이익. ★이 전략의 E층 3센서가 전부 여기서 나온다:
    #      i_sales  = 매출 전기대비          i_turn = 자산회전율 전기대비
    #      i_accr   = (Δ유동자산−Δ유동부채)/자산   (Sloan 1996 대차대조표법)
    #    100사/회이므로 전 종목 × 12연도 × 4보고서가 1,000회 미만이다. 가장 먼저, 반드시 돈다.
    if _left_min() > 0.5:
        try:
            M = fetch_dart_multi_accounts(ccs_all, yrs)
            if M is not None and len(M):
                frames.append(M)
        except Exception as e:                                     # noqa
            LOG.warn(f"DART 주요계정 배치 실패({type(e).__name__}) — 단건 경로로 넘어갑니다.")
    else:
        LOG.warn("남은 예산이 없어 주요계정 배치를 건너뜁니다 — E층 전체가 결측이 됩니다.")

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
        # ★★ 이미 받아둔 회사를 건너뛰지 않으면 창이 영원히 안 움직인다 ★★
        #   예전 구현은 우선순위 상위 N 사를 매 실행 그대로 잘라 넘겼다. 2회차부터는
        #   그 N 사가 전부 캐시에 있어 신규 작업이 0건이 되고, 시간을 안 쓰니 3회차도
        #   같은 N 사를 고른다 — 60사에서 멈춘 채 며칠을 돌려도 한 발짝도 못 나간다.
        _cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
        _done_corp: set = set()
        if _cached is not None and len(_cached):
            try:
                _need = len(yrs) * len(reprts) * 0.8
                _cnt = (_cached.groupby("corp_code")[["bsns_year", "reprt_code"]]
                        .apply(lambda g: g.drop_duplicates().shape[0]))
                _done_corp = set(_cnt[_cnt >= _need].index.astype(str))
            except Exception:
                _done_corp = set()
        n_corp_afford = max(1, cap_calls // (len(yrs) * len(reprts)))
        pool = [c for c in (prio or ccs_all) if c not in _done_corp]
        pick = pool[:n_corp_afford]
        LOG.info(f"단건 전 계정 수집 — 예산 {cap_calls:,}회로 {len(pick):,}사 × "
                 f"{len(yrs)}연도 × {len(reprts)}보고서. "
                 f"이미 확보 {len(_done_corp):,}사는 건너뜁니다(다음 실행이 그 다음 구간을 "
                 f"이어받아 창이 실제로 전진합니다). 전 종목 {len(ccs_all):,}사 중 누적 "
                 f"{100*(len(_done_corp)+len(pick))/max(len(ccs_all),1):.0f}%.")
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
    """예산이 부족할 때 '무엇을 먼저 받을지'의 기준 = **U-MICRO 에 실제로 들어올 종목**.

    ★ 예전 구현의 치명적 실수 ─────────────────────────────────────────────────────────
      거래대금 '내림차순'으로 정렬했다. 그러면 삼성전자·SK하이닉스부터 받는다.
      그런데 이 전략의 유니버스는 시총 하위권이라 그 회사들은 **정의상 전부 제외**된다.
      즉 예산을 다 써서 유니버스 밖 종목의 재무만 모으고, 정작 U-MICRO 종목의
      재고·영업CF 커버리지는 0% 로 남는다. 계정 정규식을 아무리 고쳐도 안 풀린다.

    ★ 올바른 순서: 유동성 하한(§7 방화벽 V6)은 통과하되 **거래대금이 작은 쪽부터**.
      = 유동성은 있는데 규모는 작은 구간 = U-MICRO 그 자체.
    """
    if px_daily is None or len(px_daily) == 0 or "amount" not in px_daily.columns:
        return []
    try:
        amt = px_daily.groupby("code", observed=True)["amount"].median()
        liquid = amt[amt >= UMICRO_MIN_ADV_KRW]
        # 유동성 하한을 넘는 종목이 거의 없으면(가격 소스 부실) 전체를 대상으로 한다.
        if len(liquid) < 200:
            liquid = amt
        amt = liquid.sort_values(ascending=True)      # ★작은 쪽부터 = U-MICRO 우선
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
