

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  ARC-NCQ 리포팅 — 헤드라인 / 성과 / 커버리지 진단 / 진단 9종 / 해석표 / HTML · 매니페스트 ║
# ║                                                                                          ║
# ║  목적                                                                                     ║
# ║    "이 전략이 무엇을 보았고, 그 근거가 얼마나 얇은가"를 스크롤 없이 보여준다.               ║
# ║    숫자를 예쁘게 만드는 곳이 아니라, 결손·편향·집중을 먼저 자백하는 곳이다(§16.3).          ║
# ║    ★ 출력 1순위는 콘솔 표다. HTML 은 부가 산출물이며, HTML 이 실패해도 콘솔은 남는다.       ║
# ║                                                                                          ║
# ║  입력 (전부 선택적 — 없으면 "데이터 없음 + 이유"를 출력하고 조용히 건너뛰지 않는다)         ║
# ║    ctx      : dict — BT/SIG/EV/REP/UNI/SCORE/TXT/sec/benches/diag/valid_start/months …    ║
# ║    BT       : {"returns","holdings","cohorts","label"}  (계약 §3)                         ║
# ║    benches  : {이름: 월별 수익 Series}  주=Bottom-N EW · 보조=KOSPI/KOSDAQ · 대조=Placebo  ║
# ║                                                                                          ║
# ║  출력                                                                                     ║
# ║    콘솔 : LOG.banner / LOG.table (폭 104 기준, 한글 폭 보정은 _dw/_pad/_trunc 가 담당)      ║
# ║    파일 : report.html · coverage.html · manifest.json  (전부 atomic_write_text)           ║
# ║                                                                                          ║
# ║  실패 시 동작                                                                             ║
# ║    이 계층은 파이프라인을 죽이지 않는다. 섹션 하나가 터지면 그 섹션만 경고로 남기고 다음     ║
# ║    섹션을 계속 출력한다 — 리포트가 통째로 사라져서 원인을 못 보는 상황이 가장 나쁘다.        ║
# ║    단, 결측을 0으로 채우거나 표본을 잘라 결과를 좋아 보이게 만드는 일은 하지 않는다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

NCQ_W = 104                      # 콘솔 폭 기준 (기존 build/* 와 동일)
NCQ_NA = "—"                     # 결측 표기. NaN 을 0 으로 치환하지 않는다는 원칙의 표면.
NCQ_MARKS = "*o+x#%@"            # ASCII 차트 계열 마커 (전부 ASCII — 한글 폭 문제 회피)
NCQ_BLOCKS = "▁▂▃▄▅▆▇█"          # 스파크라인 블록 (East-Asian-Width='A' → _dw 로 1칸)


# ── 렉시콘 그룹 해석 참조표 (정본은 ncq_40_text 의 NCQ_LEXICON, 여기는 그 요약·폴백) ─────────
#    (라벨, 뜻, 발화했다는 것의 의미, 발화하지 않았다는 것의 의미, 방향)
NCQ_GROUP_DOC = OrderedDict([
    ("A", ("구조적 전환",
           "사업재편·체질개선·턴어라운드·신사업 진출처럼 '무엇을 하는 회사인가'가 바뀌는 서술",
           "애널리스트가 이 회사를 과거와 다른 회사로 보기 시작했다. 신규 커버리지의 가장 강한 명분",
           "전환 서사 없이 커버가 개시됐다 — 기존 사업의 업황 코멘트이거나 의무 발간일 수 있다",
           "+강")),
    ("B", ("캐파·양산",
           "증설·신규 라인·양산 개시·가동률처럼 '이미 돈을 쓴 흔적'의 서술",
           "말이 아니라 자본적 지출로 확인되는 변화. A 와 동시 발화할 때 가장 신뢰도가 높다",
           "설비 근거가 없다 — 전환 주장이 계획 단계에 머물러 있을 수 있다",
           "+")),
    ("C", ("수요·고객",
           "신규 수주·수주잔고·1차 벤더·국산화처럼 '외부가 값을 치렀다'는 증거",
           "제3자 검증이 있다. 회사의 자기 주장이 아니라 고객의 구매 결정이 근거",
           "수요 측 증거 없이 공급 측 이야기만 있다 — 증설이 재고로 남을 위험",
           "+")),
    ("D", ("인증·승인",
           "인증 획득·품질 승인·벤더 등록·특허·임상 진입 등 제도적 관문 통과",
           "되돌리기 어려운 자격을 얻었다. 소형주에서 진입장벽이 실제로 생기는 지점",
           "관문 통과 근거 없음 — 기술·품질 주장이 아직 검증되지 않았다는 뜻",
           "+")),
    ("H", ("헤지·불확실성",
           "'기대', '전망', '가능성', '검토 중' 등 확신을 낮추는 완충 표현",
           "★ 역가중(-1.0). 근거 대신 기대를 적었다는 자기고백. 스폰서 의무 발간에서 특히 흔하다",
           "단정적으로 썼다 — 하우스가 평판을 걸었다는 뜻",
           "−역")),
    ("N", ("부정",
           "지연·차질·부진·둔화·하향·적자전환 등 명시적 악화 서술",
           "★ 역가중(-2.5). 신규 커버리지 리포트에 악재를 적었다는 것은 그만큼 크다는 뜻",
           "악재 서술 없음 — 낙관 편향이거나, 본문 추출이 앞부분에서 잘렸을 수 있다",
           "−역")),
])

# ── 신규 커버리지 이벤트 유형 (정본은 ncq_30_coverage.build_coverage_events) ─────────────────
NCQ_EVENT_TYPE_DOC = OrderedDict([
    ("H1", ("전면 신규 커버리지",
            "직전 lookback 구간(NCQ_LOOKBACK_M) 동안 어떤 증권사도 리포트를 내지 않던 종목에 "
            "리포트가 발간됨. 정보 공백이 가장 큰 상태 — 이 전략의 본류.")),
    ("H2", ("신규 하우스 진입",
            "기존 커버는 있었으나 해당 증권사가 처음 커버를 개시함. 공백은 H1 보다 얕지만 "
            "새 하우스의 자원 배분 결정이라는 점에서 정보가 있다.")),
])

NCQ_SPONSOR_DOC = OrderedDict([
    ("SPONSORED_ONLY", "IRS(거래소 기업분석보고서 발간지원) 등 발행사·기관 스폰서 리포트만으로 구성된 이벤트. "
                       "발간 자체가 의무일 수 있어 '자발적 관심'의 증거로 쓰기 어렵다."),
    ("ORGANIC_ONLY", "스폰서 없이 증권사가 자발적으로 발간한 리포트만으로 구성된 이벤트. 신호의 본체."),
    ("MIXED", "스폰서·자발 리포트가 섞인 이벤트."),
])

NCQ_HTML_CSS = """
*{box-sizing:border-box}
body{margin:0;padding:28px 22px 60px;background:#ffffff;color:#1f2328;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR","Malgun Gothic",sans-serif;
 font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid #1f2328}
h3{font-size:14px;margin:20px 0 6px;color:#39424e}
.sub{color:#6a737d;font-size:13px;margin:0 0 18px}
.note{color:#6a737d;font-size:12px;margin:4px 0 14px}
.alert{border:2px solid #d93025;background:#fdf1f0;border-radius:8px;padding:12px 16px;margin:16px 0}
.alert b{color:#d93025}
.alert ul{margin:6px 0 0;padding-left:20px}
.ok{border:1px solid #188038;background:#f2f9f4;border-radius:8px;padding:10px 16px;margin:16px 0;color:#186c33}
table{border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:13px}
th,td{border:1px solid #d0d7de;padding:5px 9px;text-align:right;white-space:nowrap}
th{background:#f2f4f7;font-weight:600;text-align:center}
td.l,th.l{text-align:left;white-space:normal}
tbody tr:nth-child(even){background:#fafbfc}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.bad{color:#d93025;font-weight:600}
.good{color:#188038}
.mut{color:#6a737d}
.chart{border:1px solid #d0d7de;border-radius:8px;padding:8px;margin:10px 0;overflow-x:auto}
footer{margin-top:44px;padding-top:14px;border-top:1px solid #d0d7de;color:#6a737d;font-size:12px}
"""


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  0. 공통 유틸 — 안전 접근 / 포맷 / 섹션 가드
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_g(name: str, default=None):
    """조립 순서상 아직 정의되지 않았을 수도 있는 전역을 안전하게 읽는다.

    리포트 계층은 모든 상위 모듈에 의존하는데, 부분 실행(SMOKE·CACHED)에서는 그중 일부가
    아예 정의되지 않는다. 그때 NameError 로 리포트가 통째로 죽는 것이 최악이라 이 관문을 둔다.
    """
    return globals().get(name, default)


def ncq_rpt_ctx_get(ctx, key: str, default=None):
    """ctx 는 dict 이거나 속성 객체일 수 있다. 둘 다 받는다."""
    if ctx is None:
        return default
    try:
        if isinstance(ctx, dict):
            return ctx.get(key, default)
        return getattr(ctx, key, default)
    except Exception:
        return default


def ncq_isnum(v) -> bool:
    """유한한 수인가. bool 은 수로 보지 않는다(True 가 1.0 으로 표에 찍히는 사고 방지)."""
    try:
        if v is None or isinstance(v, (bool, np.bool_)):
            return False
        return bool(np.isfinite(float(v)))
    except Exception:
        return False


def ncq_pct(v, digits: int = 2, signed: bool = True) -> str:
    if not ncq_isnum(v):
        return NCQ_NA
    return (f"{float(v) * 100:+.{digits}f}%" if signed else f"{float(v) * 100:.{digits}f}%")


def ncq_pctp(v, digits: int = 3) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{float(v) * 100:+.{digits}f}%p"


def ncq_rpt_num(v, digits: int = 3) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{float(v):,.{digits}f}"


def ncq_int(v) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{int(round(float(v))):,}"


def ncq_compact(v) -> str:
    """표 폭이 빡빡한 연도×월 매트릭스용 축약 표기."""
    if not ncq_isnum(v):
        return NCQ_NA
    x = float(v)
    a = abs(x)
    if a >= 1e8:
        return f"{x / 1e8:.1f}억"
    if a >= 1e4:
        return f"{x / 1e3:.0f}k"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.1f}"


def ncq_wrap(s, width: int) -> List[str]:
    """한글 폭(_dw)을 반영한 줄바꿈. 공백 없는 한글 장문도 문자 단위로 자른다."""
    words = str(s).replace("\n", " ").split(" ")
    lines: List[str] = []
    cur = ""
    for w0 in words:
        cand = (cur + " " + w0) if cur else w0
        if _dw(cand) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        while _dw(w0) > width:
            acc = ""
            for ch in w0:
                if _dw(acc) + _dw(ch) > width:
                    break
                acc += ch
            if not acc:                       # 폭보다 넓은 단일 문자 — 무한루프 방지
                acc = w0[0]
            lines.append(acc)
            w0 = w0[len(acc):]
        cur = w0
    if cur:
        lines.append(cur)
    return lines or [""]


def ncq_box(title: str, lines: Sequence[str], width: int = 100) -> List[str]:
    """한글 폭을 보정한 ASCII 박스. 문자열 리터럴로 직접 그리면 반드시 어긋난다."""
    width = max(24, int(width))
    inner = width - 4
    out = ["┌" + "─" * (width - 2) + "┐",
           "│ " + _pad(_trunc(title, inner), inner) + " │"]
    if lines:
        out.append("├" + "─" * (width - 2) + "┤")
    for ln in lines:
        for w in ncq_wrap(ln, inner):
            out.append("│ " + _pad(w, inner) + " │")
    out.append("└" + "─" * (width - 2) + "┘")
    return out


def ncq_alert_box(lines: Sequence[str], title: str = "위험 경고 — 아래 숫자를 읽기 전에 이것부터") -> None:
    """리포트 최상단 경고(§15-6). 눈에 띄지 않으면 없는 것과 같으므로 이중선 박스로 그린다."""
    lines = [l for l in (lines or []) if l]
    if not lines:
        return
    inner = NCQ_W - 4
    _safe_print("")
    _safe_print("┏" + "━" * (NCQ_W - 2) + "┓")
    _safe_print("┃ " + _pad(_trunc("⚠  " + title, inner), inner) + " ┃")
    _safe_print("┠" + "─" * (NCQ_W - 2) + "┨")
    for i, ln in enumerate(lines, 1):
        for k, w in enumerate(ncq_wrap(f"{i}. {ln}", inner)):
            _safe_print("┃ " + _pad(("" if k == 0 else "   ") + w, inner) + " ┃")
    _safe_print("┗" + "━" * (NCQ_W - 2) + "┛")


@contextmanager
def ncq_section(title: str):
    """섹션 가드 — 한 섹션이 터져도 리포트 전체가 사라지지 않게 한다.

    ★ 예외를 삼키는 것이 원칙 위반처럼 보이지만, 이 계층에 한해서는 반대다.
      리포트는 '무엇이 잘못됐는지 보여주는 장치'인데 그게 죽으면 진단 수단이 사라진다.
      대신 삼킨 사실과 예외 종류를 반드시 경고로 남긴다.
    """
    try:
        yield
    except Exception as e:                                        # noqa
        LOG.warn(f"[{title}] 출력 중 오류 — 이 섹션만 건너뜁니다: {type(e).__name__}: {str(e)[:180]}")


def ncq_no_data(title: str, reason: str) -> None:
    """데이터가 없을 때 조용히 건너뛰지 않는다. 무엇이 왜 없는지 항상 적는다."""
    LOG.warn(f"[{title}] 데이터 없음 — {reason}")


def ncq_pick_col(df, cands: Sequence[str], default=None):
    """스키마가 모듈마다 조금씩 다를 수 있는 진단표에서 컬럼을 안전하게 고른다."""
    try:
        if df is None or not hasattr(df, "columns"):
            return default
        for c in cands:
            if c in df.columns:
                return c
    except Exception:
        pass
    return default


def ncq_has_rows(df) -> bool:
    try:
        return df is not None and hasattr(df, "empty") and (not df.empty)
    except Exception:
        return False


def ncq_name_map(sec) -> Dict[str, str]:
    """code → 종목명. 없으면 빈 dict (호출부는 .get(code, '') 로 쓴다)."""
    try:
        if not ncq_has_rows(sec) or "code" not in sec.columns:
            return {}
        s = sec.dropna(subset=["code"]).drop_duplicates(subset=["code"])
        if "name" not in s.columns:
            return {}
        return {str(k): ("" if pd.isna(v) else str(v))
                for k, v in zip(s["code"].astype(str), s["name"])}
    except Exception:
        return {}


def ncq_spearman(x, y) -> Tuple[float, float]:
    """(rho, p). scipy 가 있으면 p 값까지, 없으면 rho 만 (p 는 NaN — 0 으로 채우지 않는다)."""
    try:
        xa = np.asarray(pd.to_numeric(pd.Series(list(x)), errors="coerce"), dtype=float)
        ya = np.asarray(pd.to_numeric(pd.Series(list(y)), errors="coerce"), dtype=float)
        m = np.isfinite(xa) & np.isfinite(ya)
        if int(m.sum()) < 5:
            return (np.nan, np.nan)
        try:
            from scipy import stats as _st
            r, p = _st.spearmanr(xa[m], ya[m])
            return (float(r), float(p))
        except Exception:
            s = pd.DataFrame({"x": xa[m], "y": ya[m]})
            return (float(s["x"].corr(s["y"], method="spearman")), np.nan)
    except Exception:
        return (np.nan, np.nan)


def ncq_xlabel(x) -> str:
    if isinstance(x, (pd.Timestamp, _dt.date, _dt.datetime, np.datetime64)):
        t = as_ts(x)
        return t.strftime("%Y-%m") if t is not None else NCQ_NA
    return _trunc(str(x), 10)


def ncq_rpt_month_series(df, value: Optional[str] = None, how: str = "count") -> pd.Series:
    """month 컬럼을 가진 프레임 → 월말 인덱스 Series. 없는 달은 NaN(0 으로 채우지 않는다)."""
    if not ncq_has_rows(df):
        return pd.Series(dtype="float64")
    mcol = ncq_pick_col(df, ["month", "월"])
    if mcol is None:
        return pd.Series(dtype="float64")
    d = df.copy()
    d["_m"] = as_ts_series(d[mcol]) + pd.offsets.MonthEnd(0)
    g = d.groupby("_m", observed=True)
    if how == "count" or value is None:
        s = g.size().astype("float64")
    elif how == "nunique":
        s = g[value].nunique().astype("float64")
    elif how == "sum":
        s = g[value].sum(min_count=1).astype("float64")
    else:
        s = g[value].mean().astype("float64")
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def ncq_fill_month_gaps(s: pd.Series) -> pd.Series:
    """관측 구간 전체를 월말 그리드로 펴서 '없는 달'이 NaN 으로 드러나게 한다."""
    try:
        if s is None or len(s) == 0:
            return pd.Series(dtype="float64")
        idx = pd.DatetimeIndex(pd.to_datetime(s.index))
        full = pd.date_range(idx.min(), idx.max(), freq="ME")
        return s.reindex(full)
    except Exception:
        return s


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  1. 시각화 유틸 — 스파크라인 / ASCII 차트 / 연도 요약표 / 막대
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_sparkline(values, width: int = 48, lo=None, hi=None) -> str:
    """시계열을 한 줄 블록 문자로. 결측은 '·' 로 남긴다(0 으로 채우면 결손이 사라진다).

    lo/hi 를 주면 여러 줄(예: 연도별 행) 사이에 스케일을 공유해 비교가 가능해진다.
    """
    try:
        v = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    except Exception:
        return NCQ_NA
    if v.size == 0:
        return NCQ_NA
    w = max(1, int(width))
    if v.size > w:                                    # 다운샘플: 구간 평균 (결측은 무시)
        edges = np.linspace(0, v.size, w + 1).astype(int)
        binned = []
        for i in range(w):
            a = edges[i]
            b = max(edges[i] + 1, edges[i + 1])
            seg = v[a:min(b, v.size)]
            seg = seg[np.isfinite(seg)]
            binned.append(float(seg.mean()) if seg.size else np.nan)
        v = np.asarray(binned, dtype=float)
    fin = v[np.isfinite(v)]
    if fin.size == 0:
        return NCQ_NA
    vlo = float(fin.min()) if not ncq_isnum(lo) else float(lo)
    vhi = float(fin.max()) if not ncq_isnum(hi) else float(hi)
    if vhi - vlo < 1e-12:
        return "".join("▄" if np.isfinite(x) else "·" for x in v)
    out = []
    for x in v:
        if not np.isfinite(x):
            out.append("·")
            continue
        k = int(round((x - vlo) / (vhi - vlo) * (len(NCQ_BLOCKS) - 1)))
        out.append(NCQ_BLOCKS[min(len(NCQ_BLOCKS) - 1, max(0, k))])
    return "".join(out)


def ncq_ascii_chart(series_dict: Dict[str, Any], height: int = 14, width: int = 92) -> List[str]:
    """여러 시계열을 하나의 ASCII 라인차트로. 반환은 출력용 줄 리스트(호출자가 _safe_print).

    콘솔이 1순위 출력이라는 원칙 때문에 필요하다 — matplotlib 은 로그에 남지 않는다.
    · 값이 전부 결측인 계열은 조용히 빼지 않고 범례에 '(데이터 없음)' 으로 표기한다.
    · 선이 겹치면 먼저 그린 계열이 보인다(범례 순서 = 그린 순서).
    """
    items: List[List[Any]] = []
    empty: List[str] = []
    for name, s in (series_dict or {}).items():
        try:
            ss = pd.to_numeric(pd.Series(s), errors="coerce").astype(float)
        except Exception:
            ss = None
        if ss is None or int(ss.notna().sum()) == 0:
            empty.append(str(name))
            continue
        items.append([str(name), ss])
    if not items:
        why = ("전부 결측: " + ", ".join(empty)) if empty else "입력이 비었습니다"
        return [f"  (차트 데이터 없음 — {why})"]

    try:                                              # 공통 x축 = 인덱스 합집합
        uni = pd.Index(sorted(set().union(*[set(pd.Index(s.index)) for _, s in items])))
        cols = [pd.Series(s).reindex(uni).astype(float).ffill().to_numpy() for _, s in items]
    except Exception:                                 # 인덱스 타입이 섞이면 위치 기준으로 폴백
        n0 = max(len(s) for _, s in items)
        uni = pd.RangeIndex(n0)
        cols = [np.concatenate([pd.Series(s).to_numpy(dtype=float),
                                np.full(n0 - len(s), np.nan)]) for _, s in items]

    fin = [c[np.isfinite(c)] for c in cols]
    fin = [f for f in fin if f.size]
    if not fin:
        return ["  (차트 데이터 없음 — 정렬 후 유한값이 하나도 남지 않았습니다)"]
    allv = np.concatenate(fin)
    ymin, ymax = float(allv.min()), float(allv.max())
    as_pct = max(abs(ymin), abs(ymax)) <= 50.0        # 수익률 비율값이면 % 로 표시
    # ★ 폭 0 가드는 반드시 '스케일 상대값'이어야 한다.
    #   절대 epsilon(1e-9)은 값이 1e8(원화 ADV)만 돼도 float64 정밀도에 먹혀 ymin+1e-9 == ymin 이 되고,
    #   span 이 정확히 0 → 아래 (ymax-v)/span 이 ZeroDivisionError / NaN→int 로 터진다.
    #   상수 시계열(월별 건수·금액)은 실제로 흔하므로 여기서 막지 않으면 리포트가 통째로 사라진다.
    scale = max(abs(ymin), abs(ymax), 1.0)
    if not np.isfinite(ymax - ymin) or (ymax - ymin) <= scale * 1e-9:
        ymin, ymax = ymin - scale * 1e-6, ymax + scale * 1e-6
    span = ymax - ymin

    H = max(4, int(height))
    W = max(20, int(width))
    grid = [[" "] * W for _ in range(H)]
    n = len(uni)
    xpos = [0] * W if n <= 1 else [int(round(j * (n - 1) / (W - 1))) for j in range(W)]

    if ymin < 0.0 < ymax:                             # 0 기준선 — 손실 구간이 눈에 보이게
        r0 = min(H - 1, max(0, int(round((ymax - 0.0) / span * (H - 1)))))
        for j in range(W):
            grid[r0][j] = "·"

    for si, (_nm, _s) in enumerate(items):
        m = NCQ_MARKS[si % len(NCQ_MARKS)]
        vals = cols[si]
        prev = None
        for j in range(W):
            v = vals[xpos[j]]
            if not np.isfinite(v):
                prev = None
                continue
            r = min(H - 1, max(0, int(round((ymax - v) / span * (H - 1)))))
            if prev is not None and abs(r - prev) > 1:      # 급변 구간을 세로로 이어 선처럼 보이게
                step = 1 if r > prev else -1
                for rr in range(prev + step, r, step):
                    if grid[rr][j] in (" ", "·"):
                        grid[rr][j] = m
            if grid[r][j] in (" ", "·"):
                grid[r][j] = m
            prev = r

    lines: List[str] = []
    for r in range(H):
        y = ymax - span * r / (H - 1)
        lab = f"{y * 100:+.1f}%" if as_pct else f"{y:+.3g}"
        lines.append("  " + _pad(lab, 9, "r") + " │" + "".join(grid[r]))
    lines.append("  " + " " * 9 + " └" + "─" * W)
    if n:
        bar = [" "] * W
        def _put(pos: int, txt: str):
            pos = max(0, min(W - len(txt), int(pos)))
            for k, ch in enumerate(txt):
                if pos + k < W:
                    bar[pos + k] = ch
        l0, lm, l1 = ncq_xlabel(uni[0]), ncq_xlabel(uni[n // 2]), ncq_xlabel(uni[-1])
        _put(0, l0)
        _put(W // 2 - len(lm) // 2, lm)
        _put(W - len(l1), l1)
        lines.append("  " + " " * 9 + "  " + "".join(bar))
    leg = "  범례: " + "   ".join(f"{NCQ_MARKS[i % len(NCQ_MARKS)]} {nm}"
                                 for i, (nm, _) in enumerate(items))
    if empty:
        leg += "   (데이터 없음: " + ", ".join(empty) + ")"
    lines.append(_trunc(leg, NCQ_W))
    lines.append("  " + ("y축 단위 % · " if as_pct else "y축 원값 · ") +
                 "선이 겹치면 먼저 그린 계열(범례 앞쪽)이 보입니다.")
    return lines


def ncq_print_chart(series_dict: Dict[str, Any], title: str = "",
                    height: int = 14, width: int = 92) -> None:
    if title:
        _safe_print(f"\n▶ {title}")
    for ln in ncq_ascii_chart(series_dict, height=height, width=width):
        _safe_print(ln)


def ncq_year_spark(s: pd.Series, title: str = "", note: str = "",
                   fmt: str = "int") -> None:
    """월별 시계열 → '연도 요약 + 12칸 스파크라인' 표.

    스파크라인 스케일은 전 연도 공통이라 연도 간 비교가 성립한다.
    관측이 없는 달은 '·' 로 남는다 — 결손을 0 으로 그리면 결손이 사라진다.
    """
    if s is None or len(s) == 0:
        ncq_no_data(title or "연도 요약", "입력 시계열이 비었습니다.")
        return
    ss = ncq_fill_month_gaps(pd.to_numeric(pd.Series(s), errors="coerce"))
    idx = pd.DatetimeIndex(pd.to_datetime(ss.index))
    fin = ss.to_numpy(dtype=float)
    fin = fin[np.isfinite(fin)]
    if fin.size == 0:
        ncq_no_data(title or "연도 요약", "유한값이 하나도 없습니다.")
        return
    lo, hi = float(fin.min()), float(fin.max())
    f = (lambda v: ncq_int(v)) if fmt == "int" else \
        (lambda v: ncq_pct(v)) if fmt == "pct" else (lambda v: ncq_rpt_num(v))
    rows = []
    for y in sorted(set(idx.year)):
        m = idx.year == y
        vals = ss[m]
        arr = np.full(12, np.nan, dtype=float)
        for t, v in zip(idx[m], vals.to_numpy(dtype=float)):
            arr[int(t.month) - 1] = v
        obs = int(np.isfinite(arr).sum())
        tot = float(np.nansum(arr)) if obs else np.nan
        rows.append([str(y), f"{obs}/12",
                     f(tot) if fmt != "pct" else NCQ_NA,
                     f(float(np.nanmean(arr))) if obs else NCQ_NA,
                     f(float(np.nanmin(arr))) if obs else NCQ_NA,
                     f(float(np.nanmax(arr))) if obs else NCQ_NA,
                     ncq_sparkline(arr, width=12, lo=lo, hi=hi)])
    LOG.table(rows, ["연도", "관측월", "합계", "평균", "최소", "최대", "1월─────────12월"],
              ["c", "c", "r", "r", "r", "r", "l"], title=title)
    tail = f"스파크라인 스케일 공통 [{ncq_compact(lo)} ~ {ncq_compact(hi)}] · '·' 는 관측 없음(0 아님)"
    LOG.info("    " + (note + " · " if note else "") + tail)


def ncq_year_matrix(s: pd.Series, title: str = "", note: str = "") -> None:
    """연도×월 매트릭스. 값은 축약 표기(ncq_compact)로 폭 104 안에 들어오게 한다."""
    if s is None or len(s) == 0:
        ncq_no_data(title or "연도×월", "입력 시계열이 비었습니다.")
        return
    ss = ncq_fill_month_gaps(pd.to_numeric(pd.Series(s), errors="coerce"))
    idx = pd.DatetimeIndex(pd.to_datetime(ss.index))
    rows = []
    for y in sorted(set(idx.year)):
        m = idx.year == y
        arr = np.full(12, np.nan, dtype=float)
        for t, v in zip(idx[m], ss[m].to_numpy(dtype=float)):
            arr[int(t.month) - 1] = v
        obs = int(np.isfinite(arr).sum())
        rows.append([str(y)] + [ncq_compact(x) if np.isfinite(x) else NCQ_NA for x in arr] +
                    [ncq_compact(float(np.nansum(arr))) if obs else NCQ_NA])
    LOG.table(rows, ["연도"] + [str(i) for i in range(1, 13)] + ["계"],
              ["c"] + ["r"] * 13, maxw=8, title=title)
    if note:
        LOG.info("    " + note)


def ncq_bar(v, vmax, width: int = 30, ch: str = "█") -> str:
    if not ncq_isnum(v) or not ncq_isnum(vmax) or float(vmax) <= 0:
        return ""
    k = int(round(max(0.0, float(v)) / float(vmax) * width))
    return ch * max(0, min(width, k))


def ncq_runs(flags: Sequence[bool], index: Sequence[Any], min_len: int = 1) -> List[Tuple[Any, Any, int]]:
    """True 가 연속된 구간을 (시작, 끝, 길이) 로. 결손 구간 보고용."""
    out: List[Tuple[Any, Any, int]] = []
    start = None
    prev = None
    for f, i in zip(list(flags), list(index)):
        if bool(f):
            if start is None:
                start = i
            prev = i
        else:
            if start is not None:
                out.append((start, prev, 0))
                start = None
    if start is not None:
        out.append((start, prev, 0))
    res = []
    idx_list = list(index)
    for a, b, _ in out:
        try:
            n = idx_list.index(b) - idx_list.index(a) + 1
        except Exception:
            n = 1
        if n >= min_len:
            res.append((a, b, n))
    return res


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  2. 헤드라인 (§15-6) — 리포트 최상단 필수 표시
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_degraded_levels() -> List[str]:
    fn = ncq_g("degraded")
    try:
        return list(fn()) if callable(fn) else []
    except Exception:
        return []


def ncq_archive_gaps(diag) -> Tuple[List[pd.Timestamp], List[Tuple[Any, Any, int]], Optional[pd.Timestamp]]:
    """진단표에서 (결손 태깅 월, 3개월+ 연속 결손 구간, 그로부터 도출되는 유효 시작월).

    스키마가 모듈마다 다를 수 있어 컬럼명을 후보 목록으로 찾는다.
    아무 단서도 없으면 (빈 리스트, 빈 리스트, None) — 추측해서 채우지 않는다.
    """
    if not ncq_has_rows(diag):
        return ([], [], None)
    mcol = ncq_pick_col(diag, ["month", "월"])
    if mcol is None:
        return ([], [], None)
    d = diag.copy()
    d["_m"] = as_ts_series(d[mcol]) + pd.offsets.MonthEnd(0)
    d = d.dropna(subset=["_m"]).sort_values("_m")
    inc_col = ncq_pick_col(d, ["archive_incomplete", "incomplete", "is_incomplete", "gap"])
    ok_col = ncq_pick_col(d, ["archive_ok", "complete", "is_complete"])
    if inc_col is not None:
        flags = d[inc_col].fillna(False).astype(bool).to_numpy()
    elif ok_col is not None:
        flags = (~d[ok_col].fillna(False).astype(bool)).to_numpy()
    else:
        ncol = ncq_pick_col(d, ["n_reports", "n", "count", "n_total"])
        if ncol is None:
            return ([], [], None)
        flags = (pd.to_numeric(d[ncol], errors="coerce").fillna(0) <= 0).to_numpy()
    months = list(pd.DatetimeIndex(d["_m"]))
    tagged = [m for m, f in zip(months, flags) if bool(f)]
    runs = ncq_runs(flags, months, min_len=3)
    valid_start = None
    if runs:
        last_end = runs[-1][1]
        try:
            valid_start = (pd.Timestamp(last_end) + pd.offsets.MonthEnd(1)).normalize()
        except Exception:
            valid_start = None
    elif months:
        valid_start = months[0]
    return (tagged, runs, valid_start)


def ncq_headline_facts(ctx) -> "OrderedDict[str, Any]":
    """§15-6 필수 표시 항목을 한 번에 계산한다(콘솔·HTML·매니페스트가 같은 값을 쓴다)."""
    EV = ncq_rpt_ctx_get(ctx, "EV")
    REP = ncq_rpt_ctx_get(ctx, "REP")
    TXT = ncq_rpt_ctx_get(ctx, "TXT")
    diag = ncq_rpt_ctx_get(ctx, "diag")
    months = ncq_rpt_ctx_get(ctx, "months")
    f: "OrderedDict[str, Any]" = OrderedDict()

    f["열화단계"] = ncq_degraded_levels()

    vs = ncq_rpt_ctx_get(ctx, "valid_start")
    vs = as_ts(vs) if vs is not None else None
    end = None
    try:
        if months is not None and len(months):
            end = as_ts(pd.DatetimeIndex(months)[-1])
    except Exception:
        end = None
    if end is None:
        end = as_ts(ncq_g("BACKTEST_END"))
    if vs is None:
        vs = ncq_archive_gaps(diag)[2]
    f["유효시작월"], f["유효종료월"] = vs, end
    n_month = np.nan
    if vs is not None and end is not None:
        n_month = (end.year - vs.year) * 12 + (end.month - vs.month) + 1
    f["유효개월수"] = float(n_month) if ncq_isnum(n_month) else np.nan
    f["유효연수"] = float(n_month) / 12.0 if ncq_isnum(n_month) else np.nan

    f["총이벤트수"] = float(len(EV)) if ncq_has_rows(EV) else np.nan
    ev_m = ncq_rpt_month_series(EV) if ncq_has_rows(EV) else pd.Series(dtype="float64")
    f["월평균이벤트"] = float(ncq_fill_month_gaps(ev_m).fillna(0).mean()) if len(ev_m) else np.nan
    f["이벤트월수"] = float(len(ev_m)) if len(ev_m) else np.nan

    # IRS(스폰서) 비중 — 리포트 기준과 이벤트 기준을 둘 다 낸다. 둘은 다른 질문에 답한다.
    f["IRS리포트비중"] = np.nan
    if ncq_has_rows(REP) and "is_sponsored" in REP.columns:
        v = REP["is_sponsored"]
        try:
            f["IRS리포트비중"] = float(v.fillna(False).astype(bool).mean())
        except Exception:
            f["IRS리포트비중"] = np.nan
    f["IRS이벤트비중"] = np.nan
    f["ORGANIC이벤트비중"] = np.nan
    if ncq_has_rows(EV) and "sponsor_group" in EV.columns:
        g = EV["sponsor_group"].astype(str)
        n = max(1, len(g))
        f["IRS이벤트비중"] = float(((g == "SPONSORED_ONLY") | (g == "MIXED")).sum()) / n
        f["ORGANIC이벤트비중"] = float((g == "ORGANIC_ONLY").sum()) / n

    # 종목명 → 티커 매핑 실패율: stock_code 가 비어 있는 리포트 비율
    f["티커매핑실패율"] = np.nan
    if ncq_has_rows(REP) and "stock_code" in REP.columns:
        c = REP["stock_code"].astype(object)
        bad = c.isna() | (c.astype(str).str.strip().isin(["", "None", "nan", "NaN"]))
        f["티커매핑실패율"] = float(bad.mean())

    # PDF 추출 실패율
    f["PDF추출실패율"] = np.nan
    f["PDF시도건수"] = np.nan
    if ncq_has_rows(TXT) and "extract_ok" in TXT.columns:
        ok = TXT["extract_ok"].fillna(False).astype(bool)
        f["PDF추출실패율"] = float(1.0 - ok.mean())
        f["PDF시도건수"] = float(len(ok))

    tagged, runs, derived = ncq_archive_gaps(diag)
    f["결손태깅월수"] = float(len(tagged)) if ncq_has_rows(diag) else np.nan
    f["결손구간"] = runs
    f["도출유효시작월"] = derived
    return f


def report_headline(ctx) -> None:
    """리포트 최상단 필수 표시(§15-6) + 위험 경고. 이 함수가 리포트의 첫 출력이어야 한다."""
    LOG.banner("ARC-NCQ v1.0 — 리포트 헤드라인 (§15-6 필수 표시)",
               "아래 경고를 읽기 전에 성과 숫자를 읽지 마세요. 표본이 얇으면 숫자는 의미가 없습니다.")
    f = ncq_headline_facts(ctx)

    min_ev_m = float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5)
    min_ev_t = float(ncq_g("NCQ_MIN_TOTAL_EVENTS", 800) or 800)
    min_years = float(ncq_g("NCQ_MIN_VALID_YEARS", 5.0) or 5.0)

    warns: List[str] = []
    if ncq_isnum(f["월평균이벤트"]) and f["월평균이벤트"] < min_ev_m:
        warns.append(f"월평균 이벤트가 {f['월평균이벤트']:.2f}건으로 최소 기준 {min_ev_m:.0f}건 미달입니다. "
                     f"횡단면 z 와 tercile 선별이 사실상 소수 종목 추첨이 됩니다 — "
                     f"이 상태의 성과 지표는 신뢰구간이 표시되지 않은 채로도 무의미합니다.")
    elif not ncq_isnum(f["월평균이벤트"]):
        warns.append("월평균 이벤트를 계산할 수 없습니다(EV 가 비었거나 month 컬럼이 없음). "
                     "이벤트 판정 단계(P2)를 먼저 확인하세요.")
    if ncq_isnum(f["총이벤트수"]) and f["총이벤트수"] < min_ev_t:
        warns.append(f"총 이벤트가 {int(f['총이벤트수']):,}건으로 최소 기준 {int(min_ev_t):,}건 미달입니다. "
                     f"부트스트랩·순열 검정의 검정력이 낮아 '유의하지 않음'이 '효과 없음'을 뜻하지 않습니다.")
    if ncq_isnum(f["IRS이벤트비중"]) and f["IRS이벤트비중"] > 0.70:
        warns.append(f"IRS(스폰서) 포함 이벤트 비중이 {f['IRS이벤트비중']*100:.1f}% 로 70% 를 넘습니다. "
                     f"이 신호는 '증권사의 자발적 관심'이 아니라 '발간지원 사업의 대상 선정'을 "
                     f"주로 측정하고 있을 가능성이 큽니다 — 진단 8(스폰서 분해)을 반드시 함께 보세요.")
    if ncq_isnum(f["유효연수"]) and f["유효연수"] < min_years:
        warns.append(f"유효 백테스트 구간이 {f['유효연수']:.2f}년으로 최소 {min_years:.1f}년 미달입니다. "
                     f"12개월 오버랩 보유 전략에서 이 길이는 독립 코호트가 몇 개 안 된다는 뜻입니다.")
    if ncq_isnum(f["결손태깅월수"]) and f["결손태깅월수"] > 0:
        runs = f["결손구간"] or []
        gap_txt = ", ".join(f"{ncq_xlabel(a)}~{ncq_xlabel(b)}({n}개월)" for a, b, n in runs[:4])
        warns.append(f"아카이브 결손 월 {int(f['결손태깅월수'])}개" +
                     (f" · 3개월 이상 연속 결손 구간: {gap_txt}" if runs else "") +
                     ". 결손 구간의 '이벤트 없음'은 사건이 없었다는 뜻이 아니라 수집이 안 됐다는 뜻입니다.")
    if ncq_isnum(f["티커매핑실패율"]) and f["티커매핑실패율"] > 0.10:
        warns.append(f"종목명→티커 매핑 실패율 {f['티커매핑실패율']*100:.1f}%. "
                     f"실패는 무작위가 아니라 신규·소형·개명 종목에 몰리는데, 그게 정확히 이 전략의 표적입니다.")
    if ncq_isnum(f["PDF추출실패율"]) and f["PDF추출실패율"] > 0.30:
        warns.append(f"PDF 본문 추출 실패율 {f['PDF추출실패율']*100:.1f}%. "
                     f"텍스트 z 는 추출 성공 문서만으로 계산되므로 표본이 하우스별로 편향됩니다.")
    lv = f["열화단계"]
    if lv:
        warns.append("열화 사다리가 적용된 실행입니다: " + ", ".join(lv) +
                     ". 사전등록 기준선과 다른 조건에서 나온 숫자이므로 그대로 비교하지 마세요.")

    ncq_alert_box(warns)
    if not warns:
        LOG.ok("§15-6 위험 경고 해당 없음 — 다만 '경고가 없다'가 '결과가 좋다'는 뜻은 아닙니다.")

    rows = [
        ["적용된 열화 단계", (", ".join(lv) if lv else "없음 (사전등록 기준선 그대로)"),
         "L5 는 자동 적용 금지"],
        ["유효 백테스트 윈도우",
         f"{ncq_xlabel(f['유효시작월']) if f['유효시작월'] is not None else NCQ_NA}"
         f" ~ {ncq_xlabel(f['유효종료월']) if f['유효종료월'] is not None else NCQ_NA}",
         f"{ncq_rpt_num(f['유효연수'], 2)}년 / 최소 {min_years:.1f}년"],
        ["유효 개월 수", ncq_int(f["유효개월수"]), f"이벤트 관측월 {ncq_int(f['이벤트월수'])}개월"],
        ["총 이벤트 수", ncq_int(f["총이벤트수"]), f"최소 {int(min_ev_t):,}건"],
        ["월평균 이벤트 수", ncq_rpt_num(f["월평균이벤트"], 2), f"최소 {min_ev_m:.0f}건"],
        ["IRS(스폰서) 비중 · 리포트", ncq_pct(f["IRS리포트비중"], 1, signed=False), "REP.is_sponsored"],
        ["IRS(스폰서) 비중 · 이벤트", ncq_pct(f["IRS이벤트비중"], 1, signed=False),
         "경고선 70% (SPONSORED_ONLY+MIXED)"],
        ["ORGANIC_ONLY 이벤트 비중", ncq_pct(f["ORGANIC이벤트비중"], 1, signed=False), "신호의 본체"],
        ["종목명→티커 매핑 실패율", ncq_pct(f["티커매핑실패율"], 2, signed=False), "경고선 10%"],
        ["PDF 추출 실패율", ncq_pct(f["PDF추출실패율"], 2, signed=False),
         f"시도 {ncq_int(f['PDF시도건수'])}건 · 경고선 30%"],
        ["아카이브 결손 태깅 월", ncq_int(f["결손태깅월수"]),
         f"3개월+ 연속 구간 {len(f['결손구간'] or [])}개"],
    ]
    LOG.table(rows, ["필수 표시 항목", "값", "기준 / 비고"], ["l", "r", "l"], maxw=48,
              title="§15-6 리포트 최상단 필수 표시")

    if lv:
        ladder = ncq_g("LADDER") or {}
        why = ncq_g("_DEGRADED") or {}
        lrows = [[x, _trunc(str(ladder.get(x, "설명 없음")), 52),
                  _trunc(str(why.get(x, NCQ_NA)), 34)] for x in lv]
        LOG.table(lrows, ["단계", "무엇을 포기했는가", "발동 사유"], ["c", "l", "l"], maxw=54,
                  title="적용된 열화 사다리 — 이 실행이 기준선과 다른 지점")

    if f["도출유효시작월"] is not None and f["유효시작월"] is not None:
        try:
            if pd.Timestamp(f["도출유효시작월"]) != pd.Timestamp(f["유효시작월"]):
                LOG.warn(f"유효 시작월 불일치 — 호출자 지정 {ncq_xlabel(f['유효시작월'])} vs "
                         f"커버리지 결손에서 도출 {ncq_xlabel(f['도출유효시작월'])}. "
                         f"둘 중 늦은 쪽을 쓰는 것이 안전합니다(결손 구간을 백테스트에 포함하면 "
                         f"'이벤트 없음'이 '현금 보유'로 잘못 해석됩니다).")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  3. 성과 리포트
# ═══════════════════════════════════════════════════════════════════════════════════════════
NCQ_PERF_ORDER = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                  "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
                  "월평균회전율", "월평균비용"]
NCQ_PERF_PCT = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
NCQ_PERF_PCTP = {"월평균", "월평균비용"}


def ncq_fmt_metric(k: str, v) -> str:
    """지표 이름으로 단위를 정한다. 결측은 무조건 '—' (0 으로 치환 금지)."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return NCQ_NA
    if k in NCQ_PERF_PCT:
        return ncq_pct(v)
    if k in NCQ_PERF_PCTP:
        return ncq_pctp(v)
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return f"{int(v):,}"
    return ncq_rpt_num(v) if ncq_isnum(v) else _trunc(str(v), 24)


def ncq_ret_series(BT) -> pd.Series:
    """BT["returns"] → month 인덱스 월수익 Series. 형식이 어긋나면 빈 Series."""
    try:
        R = BT.get("returns") if isinstance(BT, dict) else None
        if not ncq_has_rows(R) or "ret" not in R.columns:
            return pd.Series(dtype="float64")
        mcol = ncq_pick_col(R, ["month", "월"])
        if mcol is None:
            return pd.Series(dtype="float64")
        s = pd.Series(pd.to_numeric(R["ret"], errors="coerce").to_numpy(dtype=float),
                      index=pd.DatetimeIndex(as_ts_series(R[mcol]) + pd.offsets.MonthEnd(0)))
        return s.sort_index()
    except Exception:
        return pd.Series(dtype="float64")


def ncq_cum(s: pd.Series) -> pd.Series:
    """누적수익(비율). 결측 월은 0 수익으로 '연결'하되, 그 사실을 호출부가 로그로 밝힌다."""
    if s is None or len(s) == 0:
        return pd.Series(dtype="float64")
    return (1.0 + pd.to_numeric(s, errors="coerce").fillna(0.0)).cumprod() - 1.0


def ncq_bench_role(name: str) -> str:
    low = str(name).lower()
    if "placebo" in low or "플라시보" in str(name) or "대조" in str(name):
        return "대조"
    if "bottom" in low or "ew" in low or "유니버스" in str(name) or "동일가중" in str(name):
        return "주"
    if "kospi" in low or "kosdaq" in low or "코스" in str(name) or "지수" in str(name):
        return "보조"
    return "기타"


def ncq_bench_order(benches: Dict[str, pd.Series]) -> List[str]:
    rank = {"주": 0, "보조": 1, "대조": 2, "기타": 3}
    return sorted(list((benches or {}).keys()), key=lambda k: (rank.get(ncq_bench_role(k), 9), str(k)))


def ncq_bench_table(R: pd.Series, benches: Dict[str, pd.Series]) -> List[List[str]]:
    """벤치마크별 누적 / 월평균 초과 / HAC t. 비교 구간은 항상 전략의 관측월로 제한한다."""
    rows: List[List[str]] = []
    if R is None or len(R) == 0:
        return rows
    cum_s = float((1.0 + R.fillna(0.0)).prod() - 1.0)
    for name in ncq_bench_order(benches):
        b = benches.get(name)
        try:
            bb = pd.to_numeric(pd.Series(b), errors="coerce").reindex(R.index)
        except Exception:
            bb = pd.Series(np.nan, index=R.index)
        n_ov = int(bb.notna().sum())
        if n_ov == 0:
            rows.append([ncq_bench_role(name), _trunc(name, 26), NCQ_NA, ncq_pct(cum_s, 1),
                         NCQ_NA, NCQ_NA, NCQ_NA, "0"])
            continue
        cum_b = float((1.0 + bb.fillna(0.0)).prod() - 1.0)
        ex = R.fillna(0.0) - bb.fillna(0.0)
        try:
            _mu, t = hac_tstat(ex.to_numpy(dtype=float))
        except Exception:
            _mu, t = (np.nan, np.nan)
        rows.append([ncq_bench_role(name), _trunc(name, 26), ncq_pct(cum_b, 1), ncq_pct(cum_s, 1),
                     ncq_pctp(cum_s - cum_b, 1), ncq_pctp(float(ex.mean())),
                     ncq_rpt_num(t, 2), f"{n_ov}"])
    return rows


def report_performance(BT, benches: Dict[str, pd.Series], label: str = "") -> None:
    """포트폴리오 성과 · 벤치마크 대비 · 비용 전후 · 연도별 분해.

    실패해도 예외를 올리지 않는다(리포트 계층). 대신 무엇이 없어서 못 찍었는지 남긴다.
    """
    nm = label or str((BT or {}).get("label") if isinstance(BT, dict) else "") or \
        str(ncq_g("STRATEGY_NAME", "ARC-NCQ"))
    LOG.banner(f"성과 검증 — {nm}",
               f"{ncq_g('BACKTEST_START', '?')} ~ {ncq_g('BACKTEST_END', '?')} · "
               f"오버랩 코호트 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유 · 익영업일 시가 체결 · 롱온리")

    if not isinstance(BT, dict) or not ncq_has_rows(BT.get("returns")):
        ncq_no_data("성과 검증", "BT['returns'] 가 비었습니다. 백테스트(P4)가 실행되지 않았거나 "
                                "선별된 종목이 0 이라 수익 시계열이 만들어지지 않았습니다.")
        return
    Rdf = BT["returns"]

    with ncq_section("포트폴리오 성과"):
        pf = ncq_g("perf_stats")
        s = pf(Rdf) if callable(pf) else {}
        if not s:
            ncq_no_data("포트폴리오 성과", "perf_stats 가 빈 dict 를 반환했습니다(수익 시계열 길이 0).")
        else:
            seen = set()
            rows = []
            for k in NCQ_PERF_ORDER:
                if k in s:
                    rows.append([k, ncq_fmt_metric(k, s.get(k))])
                    seen.add(k)
            for k, v in s.items():                 # 계약 밖 지표도 버리지 않는다
                if k not in seen:
                    rows.append([k, ncq_fmt_metric(k, v)])
            LOG.table(rows, ["지표", "값"], ["l", "r"], title="포트폴리오 성과 (비용 차감 후)")

    R = ncq_ret_series(BT)

    with ncq_section("비용 전·후 비교"):
        if "ret_gross" in Rdf.columns:
            pf = ncq_g("perf_stats")
            G = Rdf.copy()
            G["ret"] = pd.to_numeric(G["ret_gross"], errors="coerce")
            sg = pf(G) if callable(pf) else {}
            sn = pf(Rdf) if callable(pf) else {}
            if sg and sn:
                keys = [k for k in ("누적수익", "CAGR", "Sharpe", "월평균", "MDD", "승률")
                        if k in sg and k in sn]
                rows = []
                for k in keys:
                    a, b = sg.get(k), sn.get(k)
                    d = (float(a) - float(b)) if (ncq_isnum(a) and ncq_isnum(b)) else np.nan
                    rows.append([k, ncq_fmt_metric(k, a), ncq_fmt_metric(k, b),
                                 ncq_fmt_metric(k, d) if ncq_isnum(d) else NCQ_NA])
                cost = float(pd.to_numeric(Rdf.get("cost"), errors="coerce").mean()) \
                    if "cost" in Rdf.columns else np.nan
                LOG.table(rows, ["지표", "비용 전(gross)", "비용 후(net)", "차이"],
                          ["l", "r", "r", "r"],
                          title=f"거래비용 영향 (왕복 {float(ncq_g('NCQ_COST_ROUNDTRIP', 0.018) or 0.018)*100:.1f}% 가정 · "
                                f"월평균 비용 {ncq_pctp(cost)})")
        else:
            LOG.info("    비용 전(gross) 시계열이 BT['returns'] 에 없어 비용 전·후 비교를 생략합니다 "
                     "(ret_gross 컬럼 부재).")

    with ncq_section("벤치마크 대비"):
        rows = ncq_bench_table(R, benches or {})
        if not rows:
            ncq_no_data("벤치마크 대비", "benches 가 비었습니다. 최소한 주 벤치마크(Bottom-N EW)는 "
                                       "bench_universe_ew 로 만들어 넘겨야 비교가 성립합니다.")
        else:
            LOG.table(rows, ["역할", "벤치마크", "벤치 누적", "전략 누적", "초과", "월평균 초과",
                             "HAC t", "겹친 월"],
                      ["c", "l", "r", "r", "r", "r", "r", "r"],
                      title="벤치마크 대비 (구간은 전략 관측월로 제한 · 주=Bottom-N EW, 보조=지수, 대조=Placebo)")
            LOG.info("    ★ 판정의 기준은 주 벤치마크입니다. 하위 N 유니버스가 그 자체로 강세였던 구간에서 "
                     "지수 대비 초과는 전략의 공로가 아닙니다.")
            if not any(r[0] == "주" for r in rows):
                LOG.warn("주 벤치마크(Bottom-N 동일가중)가 없습니다 — 지수 대비 숫자만으로 결론 내리지 마세요.")
            if not any(r[0] == "대조" for r in rows):
                LOG.warn("대조군(Placebo 하위 tercile)이 없습니다 — '텍스트 z 가 방향성을 가진다'는 "
                         "주장을 반증할 장치가 빠졌습니다.")

    with ncq_section("연도별 분해"):
        if len(R) == 0:
            ncq_no_data("연도별 분해", "월수익 시계열이 비었습니다.")
        else:
            main = None
            for k in ncq_bench_order(benches or {}):
                if ncq_bench_role(k) == "주":
                    main = k
                    break
            bb = None
            if main is not None:
                try:
                    bb = pd.to_numeric(pd.Series((benches or {})[main]), errors="coerce").reindex(R.index)
                except Exception:
                    bb = None
            rows = []
            years = sorted(set(pd.DatetimeIndex(R.index).year))
            for y in years:
                m = pd.DatetimeIndex(R.index).year == y
                r = R[m].fillna(0.0)
                cy = float((1.0 + r).prod() - 1.0)
                by = np.nan
                if bb is not None and int(bb[m].notna().sum()) > 0:
                    by = float((1.0 + bb[m].fillna(0.0)).prod() - 1.0)
                nn = np.nan
                if "n" in Rdf.columns:
                    try:
                        nn = float(pd.to_numeric(Rdf["n"], errors="coerce")
                                   .to_numpy(dtype=float)[m].mean())
                    except Exception:
                        nn = np.nan
                rows.append([str(y), f"{int(m.sum())}", ncq_pct(cy, 1),
                             ncq_pct(by, 1) if ncq_isnum(by) else NCQ_NA,
                             ncq_pctp(cy - by, 1) if ncq_isnum(by) else NCQ_NA,
                             ncq_rpt_num(nn, 1),
                             ncq_sparkline(r.to_numpy(dtype=float), width=12)])
            LOG.table(rows, ["연도", "월수", "전략", (f"주벤치({_trunc(main, 14)})" if main else "주벤치"),
                             "초과", "평균종목수", "월수익 추이"],
                      ["c", "r", "r", "r", "r", "r", "l"],
                      title="연도별 성과 (좋은 해와 나쁜 해를 평균으로 덮지 않는다)")

    with ncq_section("우측 꼬리 의존도"):
        H = BT.get("holdings") if isinstance(BT, dict) else None
        if not ncq_has_rows(H) or not {"code", "weight", "ret"}.issubset(set(H.columns)):
            LOG.info("    보유 원장(holdings)이 없거나 code/weight/ret 컬럼이 없어 꼬리 의존도를 생략합니다.")
        else:
            c = (pd.to_numeric(H["weight"], errors="coerce") *
                 pd.to_numeric(H["ret"], errors="coerce"))
            contrib = c.groupby(H["code"].astype(str)).sum().sort_values(ascending=False)
            n = int(len(contrib))
            base = float(contrib.sum())
            rows = [["총기여", ncq_pctp(base, 2), f"종목 {n:,}개"]]
            for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
                k = max(1, int(round(n * q)))
                ex = float(contrib.iloc[k:].sum()) if k < n else np.nan
                rows.append([f"{lab} 제외 후 총기여", ncq_pctp(ex, 2), f"제외 {k:,}종목"])
            LOG.table(rows, ["항목", "값", "비고"], ["l", "r", "l"],
                      title="우측 꼬리 의존도 — 신규 커버리지 전략은 구조적으로 소수 종목에 쏠린다")
            k5 = max(1, int(round(n * 0.05)))
            ex5 = float(contrib.iloc[k5:].sum()) if k5 < n else np.nan
            if base > 0 and ncq_isnum(ex5) and ex5 <= 0:
                LOG.warn("상위 5% 종목을 빼면 총기여가 0 이하입니다. 성과가 소수 종목에 전적으로 "
                         "의존하므로, 실전에서 그 종목을 놓치면 전략 전체가 실패합니다. "
                         "사이징과 기대치를 여기에 맞추세요.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  4. 커버리지 완결성 진단 (§6.4)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def report_coverage_diagnostics(diag, REP, EV) -> None:
    """§6.4 — 리서치 아카이브가 '언제부터 믿을 만한가'를 판정한다.

    이 섹션의 결론(유효 백테스트 시작월)이 이후 모든 숫자의 전제다.
    아카이브가 얇은 구간에서 '이벤트가 없었다'는 것은 사건 부재가 아니라 관측 부재이며,
    그 구간을 백테스트에 넣으면 현금 보유 수익이 전략 성과로 둔갑한다.
    """
    LOG.banner("커버리지 완결성 진단 (§6.4)",
               "월별 수집량 · 유니크 커버 종목 · 결손 태깅 · 연속 결손 구간 → 유효 시작월 확정")

    if not ncq_has_rows(REP) and not ncq_has_rows(diag):
        ncq_no_data("커버리지 완결성", "REP(리포트 인덱스)와 diag(완결성 진단표)가 모두 비었습니다. "
                                     "수집(P1)이 전혀 수행되지 않았거나 캐시가 비어 있습니다.")
        return

    # ── (1) 월별 총 리포트 건수 — 소스별 ─────────────────────────────────────────────────
    with ncq_section("월별 리포트 건수(소스별)"):
        if not ncq_has_rows(REP):
            ncq_no_data("월별 리포트 건수", "REP 가 비었습니다(diag 만으로는 소스 분해가 불가).")
        else:
            R = REP.copy()
            dcol = ncq_pick_col(R, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is None:
                ncq_no_data("월별 리포트 건수", "REP 에 pub_date/event_date 계열 날짜 컬럼이 없습니다.")
            else:
                R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
                R = R.dropna(subset=["_m"])
                total = R.groupby("_m", observed=True).size().astype("float64").sort_index()
                total.index = pd.DatetimeIndex(total.index)
                ncq_year_spark(total, title="월별 총 리포트 건수 (전 소스 합)",
                               note="합계가 급감하는 구간은 사이트 개편·차단·PDF 정책 변경을 의심")
                scol = ncq_pick_col(R, ["source", "src", "_src"])
                if scol is None:
                    LOG.info("    소스 컬럼(source)이 없어 소스별 분해를 생략합니다.")
                else:
                    srcs = [s for s in R[scol].astype(str).value_counts().head(6).index]
                    lo = hi = None
                    per = {}
                    for s in srcs:
                        ss = ncq_fill_month_gaps(
                            R[R[scol].astype(str) == s].groupby("_m", observed=True)
                             .size().astype("float64").sort_index())
                        per[s] = ss
                    vals = np.concatenate([x.to_numpy(dtype=float) for x in per.values()]) \
                        if per else np.array([])
                    vals = vals[np.isfinite(vals)]
                    if vals.size:
                        lo, hi = float(vals.min()), float(vals.max())
                    rows = []
                    for s, ss in per.items():
                        arr = ss.to_numpy(dtype=float)
                        obs = int(np.isfinite(arr).sum())
                        rows.append([_trunc(s, 18), ncq_int(float(np.nansum(arr))),
                                     f"{obs}/{len(arr)}",
                                     ncq_xlabel(ss.index[0]) if len(ss) else NCQ_NA,
                                     ncq_xlabel(ss.index[-1]) if len(ss) else NCQ_NA,
                                     ncq_sparkline(arr, width=40, lo=lo, hi=hi)])
                    LOG.table(rows, ["소스", "총건수", "관측월", "최초월", "최종월", "월별 추이"],
                              ["l", "r", "c", "c", "c", "l"], maxw=44,
                              title="소스별 수집량 (스케일 공통 — 소스 간 두께 비교 가능)")

    # ── (2) 월별 유니크 커버 종목 수 ─────────────────────────────────────────────────────
    with ncq_section("월별 유니크 커버 종목 수"):
        if not ncq_has_rows(REP) or "stock_code" not in REP.columns:
            ncq_no_data("월별 유니크 커버 종목", "REP 에 stock_code 컬럼이 없습니다 "
                                               "(종목 매핑 단계가 수행되지 않았을 수 있습니다).")
        else:
            R = REP.copy()
            dcol = ncq_pick_col(R, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is None:
                ncq_no_data("월별 유니크 커버 종목", "날짜 컬럼이 없습니다.")
            else:
                R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
                R = R.dropna(subset=["_m", "stock_code"])
                uq = R.groupby("_m", observed=True)["stock_code"].nunique().astype("float64").sort_index()
                uq.index = pd.DatetimeIndex(uq.index)
                ncq_year_matrix(uq, title="월별 유니크 커버 종목 수 (연도×월)",
                                note="'—' 는 그 달에 매핑된 리포트가 한 건도 없다는 뜻입니다(0 과 구분).")
                ncq_year_spark(uq, title="월별 유니크 커버 종목 수 — 연도 요약")

    # ── (3) archive_incomplete 태깅 월 · 연속 결손 구간 ──────────────────────────────────
    tagged, runs, derived = ncq_archive_gaps(diag)
    with ncq_section("결손 태깅"):
        if not ncq_has_rows(diag):
            ncq_no_data("결손 태깅", "diag(coverage_completeness 산출물)가 없습니다. "
                                    "ncq_20_index.coverage_completeness 결과를 넘겨 주세요.")
        elif not tagged:
            LOG.ok("archive_incomplete 로 태깅된 월이 없습니다 — 다만 '태깅 규칙이 느슨해서 "
                   "안 걸린 것'일 수 있으므로 위 월별 추이의 급감 구간을 눈으로 확인하세요.")
        else:
            byyear: Dict[int, List[int]] = defaultdict(list)
            for m in tagged:
                byyear[int(pd.Timestamp(m).year)].append(int(pd.Timestamp(m).month))
            rows = [[str(y), f"{len(ms)}", ", ".join(f"{x}월" for x in sorted(ms))]
                    for y, ms in sorted(byyear.items())]
            LOG.table(rows, ["연도", "결손 월수", "해당 월"], ["c", "r", "l"], maxw=60,
                      title=f"archive_incomplete 태깅 월 (총 {len(tagged)}개월)")

        if runs:
            rows = [[f"{i}", ncq_xlabel(a), ncq_xlabel(b), f"{n}", "★ 유효 시작 판정 근거"
                     if (derived is not None and i == len(runs)) else ""]
                    for i, (a, b, n) in enumerate(runs, 1)]
            LOG.table(rows, ["#", "시작", "종료", "개월", "비고"], ["r", "c", "c", "r", "l"],
                      title="3개월 이상 연속 결손 구간 — 이 구간은 백테스트 유효 창에서 제외해야 한다")
        elif ncq_has_rows(diag):
            LOG.ok("3개월 이상 연속 결손 구간 없음.")

    # ── (4) 유효 백테스트 시작월 확정 ────────────────────────────────────────────────────
    with ncq_section("유효 시작월"):
        vs_attr = None
        try:
            vs_attr = as_ts((getattr(diag, "attrs", {}) or {}).get("valid_start"))
        except Exception:
            vs_attr = None
        vcol = ncq_pick_col(diag, ["valid_start", "유효시작월"])
        vs_col = None
        if vcol is not None and ncq_has_rows(diag):
            try:
                vs_col = as_ts(diag[vcol].dropna().iloc[0])
            except Exception:
                vs_col = None
        burn = ncq_g("NCQ_BURNIN_M", 24)
        look = ncq_g("NCQ_LOOKBACK_M", 24)
        rows = [
            ["결손 구간에서 도출", ncq_xlabel(derived) if derived is not None else NCQ_NA,
             "마지막 3개월+ 결손 구간의 다음 달"],
            ["diag.attrs['valid_start']", ncq_xlabel(vs_attr) if vs_attr is not None else NCQ_NA,
             "coverage_completeness 가 남긴 값"],
            ["diag 컬럼", ncq_xlabel(vs_col) if vs_col is not None else NCQ_NA, "있으면 우선"],
            ["번인(burn-in)", f"{burn}개월", "신규 커버리지 판정용 과거 관측 확보 구간"],
            ["룩백(lookback)", f"{look}개월", "H1/H2 판정 시 '커버 없음'을 확인하는 창"],
        ]
        LOG.table(rows, ["출처", "유효 시작월", "설명"], ["l", "c", "l"], maxw=52,
                  title="유효 백테스트 시작월 — 여러 출처가 다르면 가장 늦은 것을 쓴다")
        cands = [x for x in (derived, vs_attr, vs_col) if x is not None]
        if cands:
            latest = max(pd.Timestamp(x) for x in cands)
            LOG.info(f"    → 권고 유효 시작월: {ncq_xlabel(latest)} "
                     f"(가장 보수적인 값. 여기보다 앞을 쓰면 관측 부재를 성과로 오독합니다)")
        else:
            LOG.warn("유효 시작월을 어느 출처에서도 확정하지 못했습니다. "
                     "BACKTEST_START 를 그대로 쓰면 초기 구간이 아카이브 결손으로 오염됩니다.")

    # ── (5) 이벤트 쪽 관측과의 정합성 ────────────────────────────────────────────────────
    with ncq_section("리포트 vs 이벤트 정합성"):
        if not ncq_has_rows(EV):
            ncq_no_data("리포트 vs 이벤트", "EV 가 비었습니다 — 이벤트 판정(P2)이 수행되지 않았습니다.")
            return
        ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV))
        ncq_year_spark(ev_m, title="월별 신규 커버리지 이벤트 수",
                       note="리포트는 있는데 이벤트가 0 인 달이 길게 이어지면 판정 규칙(룩백/번인)을 의심")
        if ncq_has_rows(REP):
            dcol = ncq_pick_col(REP, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is not None:
                Rm = REP.copy()
                Rm["_m"] = as_ts_series(Rm[dcol]) + pd.offsets.MonthEnd(0)
                rep_m = ncq_fill_month_gaps(
                    Rm.dropna(subset=["_m"]).groupby("_m", observed=True).size().astype("float64"))
                joint = pd.DataFrame({"rep": rep_m, "ev": ev_m}).dropna(how="all")
                bad = joint[(joint["rep"].fillna(0) > 0) & (joint["ev"].fillna(0) <= 0)]
                if len(bad):
                    LOG.warn(f"리포트는 있으나 이벤트가 0 인 달이 {len(bad)}개월 있습니다 "
                             f"(예: {', '.join(ncq_xlabel(x) for x in list(bad.index)[:6])}). "
                             f"신규 커버리지 판정이 지나치게 엄격하거나 유니버스 교집합이 비었을 수 있습니다.")
                else:
                    LOG.ok("리포트가 있는 달에는 이벤트도 관측됩니다(판정 규칙이 전면 차단되지는 않음).")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  5. 진단 9종 (§11.3)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_cohort_table(BT, SIG) -> pd.DataFrame:
    """코호트(진입 연월 × 종목)별 보유수익 + 진입 시점 신호 속성.

    1순위는 BT["cohorts"](ret_h), 없으면 BT["holdings"] 를 코호트별로 복리 합성해 만든다.
    진입 시점 속성(z / sponsor_group / event_type)은 SIG 를 (month=진입월, code) 로 붙인다.
    조인 실패는 결측으로 남긴다 — 채우지 않는다.
    """
    out = pd.DataFrame()
    try:
        C = BT.get("cohorts") if isinstance(BT, dict) else None
        if ncq_has_rows(C):
            ecol = ncq_pick_col(C, ["entry_month", "cohort", "month"])
            rcol = ncq_pick_col(C, ["ret_h", "ret", "ret_hold"])
            if ecol is not None and rcol is not None and "code" in C.columns:
                out = pd.DataFrame({
                    "entry_month": as_ts_series(C[ecol]) + pd.offsets.MonthEnd(0),
                    "code": C["code"].astype(str),
                    "ret_h": pd.to_numeric(C[rcol], errors="coerce"),
                    "n_months": pd.to_numeric(C.get("n_months"), errors="coerce")
                    if "n_months" in C.columns else np.nan,
                })
        if out.empty:
            H = BT.get("holdings") if isinstance(BT, dict) else None
            if ncq_has_rows(H) and {"code", "ret"}.issubset(set(H.columns)):
                h = H.copy()
                ccol = ncq_pick_col(h, ["cohort", "entry_month", "month"])
                if ccol is None:
                    return pd.DataFrame()
                h["_c"] = as_ts_series(h[ccol]) + pd.offsets.MonthEnd(0)
                h["_r"] = pd.to_numeric(h["ret"], errors="coerce")
                g = h.dropna(subset=["_c"]).groupby(["_c", h["code"].astype(str)], observed=True)["_r"]
                comp = g.apply(lambda x: float(np.prod(1.0 + x.dropna().to_numpy()) - 1.0)
                               if int(x.notna().sum()) else np.nan)
                cnt = g.count()
                out = comp.reset_index()
                out.columns = ["entry_month", "code", "ret_h"]
                out["n_months"] = cnt.to_numpy()
    except Exception:
        return pd.DataFrame()
    if out.empty:
        return out
    try:
        if ncq_has_rows(SIG) and {"month", "code"}.issubset(set(SIG.columns)):
            s = SIG.copy()
            s["month"] = as_ts_series(s["month"]) + pd.offsets.MonthEnd(0)
            keep = ["month", "code"] + [c for c in ("z", "sponsor_group", "event_type",
                                                    "rank_pct", "event_score", "pool_n")
                                        if c in s.columns]
            s = s[keep].drop_duplicates(subset=["month", "code"])
            s["code"] = s["code"].astype(str)
            out = out.merge(s, how="left", left_on=["entry_month", "code"],
                            right_on=["month", "code"])
            if "month" in out.columns:
                out = out.drop(columns=["month"])
    except Exception:
        pass
    return out


def ncq_dist_row(label: str, v: pd.Series) -> List[str]:
    """분포 요약 한 줄: n / min / Q1 / 중앙 / Q3 / max / 평균 / 승률."""
    x = pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    if len(x) == 0:
        return [label, "0"] + [NCQ_NA] * 7
    return [label, f"{len(x):,}", ncq_pct(float(x.min()), 1), ncq_pct(float(x.quantile(0.25)), 1),
            ncq_pct(float(x.median()), 1), ncq_pct(float(x.quantile(0.75)), 1),
            ncq_pct(float(x.max()), 1), ncq_pct(float(x.mean()), 1),
            ncq_pct(float((x > 0).mean()), 1, signed=False)]


NCQ_DIST_HEAD = ["구분", "n", "최소", "Q1", "중앙", "Q3", "최대", "평균", "승률"]
NCQ_DIST_ALIGN = ["l", "r", "r", "r", "r", "r", "r", "r", "r"]


def report_diagnostics(SIG, EV, BT, UNI, sec, benches) -> None:
    """§11.3 진단 9종. 각 항목은 데이터가 없으면 '데이터 없음 + 이유'를 반드시 출력한다."""
    LOG.banner("진단 9종 (§11.3)",
               "퍼널 · 커버리지 · 이벤트분포 · 누적곡선 · 코호트 · 섹터 · 기여종목 · 스폰서 · 단조성")
    names = ncq_name_map(sec)
    H = BT.get("holdings") if isinstance(BT, dict) else None
    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) \
        else pd.Series(dtype="float64")

    # ── 진단 1. 3단 퍼널 (유니버스 → 유동성통과 → 이벤트) ────────────────────────────────
    LOG.rule("진단 1 — 3단 퍼널 (유니버스 → 유동성 통과 → 이벤트)")
    with ncq_section("진단1 퍼널"):
        if not ncq_has_rows(UNI):
            ncq_no_data("진단1 퍼널", "UNI 가 비었습니다. PIT 유니버스 구축(P0)이 수행되지 않았습니다.")
        else:
            U = UNI.copy()
            mcol = ncq_pick_col(U, ["month", "월"])
            if mcol is None:
                ncq_no_data("진단1 퍼널", "UNI 에 month 컬럼이 없습니다.")
            else:
                U["_m"] = as_ts_series(U[mcol]) + pd.offsets.MonthEnd(0)
                U = U.dropna(subset=["_m"])
                in_uni = U["in_uni"].fillna(False).astype(bool) if "in_uni" in U.columns \
                    else pd.Series(True, index=U.index)
                liq = U["liq_pass"].fillna(False).astype(bool) if "liq_pass" in U.columns \
                    else pd.Series(np.nan, index=U.index)
                s_cand = U.groupby("_m", observed=True).size().astype("float64")
                s_uni = U[in_uni].groupby("_m", observed=True).size().astype("float64")
                s_liq = (U[in_uni & liq.fillna(False)].groupby("_m", observed=True).size()
                         .astype("float64")) if "liq_pass" in U.columns else pd.Series(dtype="float64")
                for s in (s_cand, s_uni, s_liq):
                    if len(s):
                        s.index = pd.DatetimeIndex(s.index)
                lo = hi = None
                pool = np.concatenate([x.to_numpy(dtype=float) for x in (s_cand, s_uni, s_liq) if len(x)])
                pool = pool[np.isfinite(pool)]
                if pool.size:
                    lo, hi = float(pool.min()), float(pool.max())
                rows = []
                for lab, s in (("① 후보 전체(상장·PIT)", s_cand),
                               (f"② 하위 {ncq_g('NCQ_UNIVERSE_BOTTOM_N', 1000)}개 유니버스", s_uni),
                               (f"③ 유동성 통과(ADV≥{ncq_compact(ncq_g('NCQ_MIN_ADV', 1e8))}원)", s_liq),
                               ("④ 신규 커버리지 이벤트", ev_m)):
                    if s is None or len(s) == 0:
                        rows.append([lab, NCQ_NA, NCQ_NA, NCQ_NA, "관측 없음"])
                        continue
                    ss = ncq_fill_month_gaps(pd.Series(s))
                    arr = ss.to_numpy(dtype=float)
                    rows.append([lab, ncq_rpt_num(float(np.nanmean(arr)), 1),
                                 ncq_int(float(np.nanmin(arr))), ncq_int(float(np.nanmax(arr))),
                                 ncq_sparkline(arr, width=42, lo=lo if lab.startswith(("①", "②", "③")) else None,
                                               hi=hi if lab.startswith(("①", "②", "③")) else None)])
                LOG.table(rows, ["단계", "월평균", "최소", "최대", "월별 추이"],
                          ["l", "r", "r", "r", "l"], maxw=46,
                          title="3단 퍼널 월별 시계열 (①②③ 은 스케일 공통, ④ 는 자체 스케일)")
                try:
                    m_uni = float(np.nanmean(ncq_fill_month_gaps(s_uni).to_numpy(dtype=float)))
                    m_liq = float(np.nanmean(ncq_fill_month_gaps(s_liq).to_numpy(dtype=float))) \
                        if len(s_liq) else np.nan
                    m_ev = float(np.nanmean(ev_m.to_numpy(dtype=float))) if len(ev_m) else np.nan
                    rows2 = [["유니버스 → 유동성", ncq_pct(m_liq / m_uni, 2, signed=False)
                              if ncq_isnum(m_liq) and ncq_isnum(m_uni) and m_uni > 0 else NCQ_NA],
                             ["유동성 → 이벤트", ncq_pct(m_ev / m_liq, 3, signed=False)
                              if ncq_isnum(m_ev) and ncq_isnum(m_liq) and m_liq > 0 else NCQ_NA],
                             ["유니버스 → 이벤트", ncq_pct(m_ev / m_uni, 3, signed=False)
                              if ncq_isnum(m_ev) and ncq_isnum(m_uni) and m_uni > 0 else NCQ_NA]]
                    LOG.table(rows2, ["통과 구간", "월평균 통과율"], ["l", "r"],
                              title="퍼널 감쇠율 — 어느 관문이 표본을 죽이는가")
                except Exception:
                    pass
                ncq_year_spark(ncq_fill_month_gaps(s_uni), title="유니버스 규모 연도 요약")

    # ── 진단 2. 커버리지 완결성 (요약) ───────────────────────────────────────────────────
    LOG.rule("진단 2 — 커버리지 완결성 (요약)")
    with ncq_section("진단2 커버리지 요약"):
        if len(ev_m) == 0:
            ncq_no_data("진단2 커버리지", "EV 가 비어 커버리지 요약을 만들 수 없습니다.")
        else:
            arr = ev_m.to_numpy(dtype=float)
            obs = int(np.isfinite(arr).sum())
            zero = int((np.nan_to_num(arr, nan=0.0) <= 0).sum())
            rows = [["관측 월 수", f"{len(arr)}", "이벤트 시계열이 덮는 월"],
                    ["이벤트 있는 월", f"{obs}", ncq_pct(obs / max(1, len(arr)), 1, signed=False)],
                    ["이벤트 0 인 월", f"{zero}", "결손인지 실제 부재인지는 §6.4 표를 볼 것"],
                    ["총 이벤트", ncq_int(float(np.nansum(arr))), ""],
                    ["월평균 이벤트", ncq_rpt_num(float(np.nanmean(arr)), 2),
                     f"최소 기준 {ncq_g('NCQ_MIN_EVENTS_PER_MONTH', 5)}건"]]
            LOG.table(rows, ["항목", "값", "비고"], ["l", "r", "l"],
                      title="커버리지 완결성 요약 (상세는 report_coverage_diagnostics 참조)")

    # ── 진단 3. 이벤트 수 히스토그램 ─────────────────────────────────────────────────────
    LOG.rule("진단 3 — 월별 이벤트 수 분포")
    with ncq_section("진단3 이벤트 히스토그램"):
        if len(ev_m) == 0:
            ncq_no_data("진단3 히스토그램", "EV 가 비었습니다(이벤트 판정 P2 미수행 또는 결과 0건).")
        else:
            arr = np.nan_to_num(ev_m.to_numpy(dtype=float), nan=0.0)
            edges = [0, 1, 3, 5, 10, 20, 50, 100, float("inf")]
            labs = ["0건", "1–2", "3–4", "5–9", "10–19", "20–49", "50–99", "100+"]
            cnt = [int(((arr >= edges[i]) & (arr < edges[i + 1])).sum()) for i in range(len(labs))]
            mx = max(cnt) if cnt else 0
            rows = [[labs[i], f"{cnt[i]}", ncq_pct(cnt[i] / max(1, len(arr)), 1, signed=False),
                     ncq_bar(cnt[i], mx, 40)] for i in range(len(labs))]
            LOG.table(rows, ["월간 이벤트 수", "월 개수", "비중", "분포"], ["l", "r", "r", "l"],
                      maxw=44, title="월별 이벤트 수 히스토그램 (가로축=한 달에 몇 건 났는가)")
            mean_ev = float(arr.mean())
            med_ev = float(np.median(arr))
            thin = int((arr < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5)).sum())
            LOG.table([["월평균", ncq_rpt_num(mean_ev, 2)], ["중앙값", ncq_rpt_num(med_ev, 2)],
                       ["기준 미달 월", f"{thin} / {len(arr)}"],
                       ["기준 미달 비중", ncq_pct(thin / max(1, len(arr)), 1, signed=False)]],
                      ["항목", "값"], ["l", "r"], title="요약")
            if mean_ev < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5):
                LOG.warn(f"월평균 이벤트 {mean_ev:.2f}건 < 기준 "
                         f"{ncq_g('NCQ_MIN_EVENTS_PER_MONTH', 5)}건. 월별 횡단면 z 가 성립하지 않는 달이 "
                         f"많다는 뜻이며, 이때 tercile 선별은 사실상 무작위 추첨입니다. "
                         f"결과의 부호를 해석하지 마세요.")

    # ── 진단 4. 누적수익 곡선 (ASCII) ────────────────────────────────────────────────────
    LOG.rule("진단 4 — 누적수익 곡선 (전략 vs 주벤치 vs 대조 vs 지수)")
    with ncq_section("진단4 누적곡선"):
        R = ncq_ret_series(BT)
        if len(R) == 0:
            ncq_no_data("진단4 누적곡선", "BT['returns'] 가 비어 전략 곡선을 그릴 수 없습니다.")
        else:
            curves: "OrderedDict[str, pd.Series]" = OrderedDict()
            curves["전략(NCQ)"] = ncq_cum(R)
            for k in ncq_bench_order(benches or {}):
                try:
                    b = pd.to_numeric(pd.Series((benches or {})[k]), errors="coerce").reindex(R.index)
                except Exception:
                    continue
                if int(b.notna().sum()) == 0:
                    continue
                curves[_trunc(k, 22)] = ncq_cum(b)
            ncq_print_chart(curves, title="누적수익 곡선 (전략 관측월 구간 · 비용 차감 후)",
                            height=16, width=88)
            missing = [r for r in ("주", "대조") if not any(ncq_bench_role(k) == r
                                                          for k in (benches or {}).keys())]
            if missing:
                LOG.warn("곡선에 빠진 계열: " + ", ".join(
                    {"주": "Bottom-N EW(주 벤치마크)", "대조": "Placebo 하위 tercile(대조군)"}[m]
                    for m in missing) + " — benches 에 넣어 주지 않으면 비교가 성립하지 않습니다.")

    # ── 진단 5. 코호트별 12개월 수익 분포 ────────────────────────────────────────────────
    LOG.rule("진단 5 — 코호트(진입 연월)별 보유수익 분포")
    COH = ncq_cohort_table(BT, SIG)
    with ncq_section("진단5 코호트 분포"):
        if not ncq_has_rows(COH) or "ret_h" not in COH.columns:
            ncq_no_data("진단5 코호트", "BT['cohorts'] 도 BT['holdings'] 도 코호트 수익을 만들 수 "
                                       "없습니다(진입월/보유수익 컬럼 부재).")
        else:
            rows = []
            yrs = sorted(set(pd.DatetimeIndex(COH["entry_month"].dropna()).year))
            for y in yrs:
                m = pd.DatetimeIndex(COH["entry_month"]).year == y
                rows.append(ncq_dist_row(str(y), COH.loc[m, "ret_h"]))
            rows.append(ncq_dist_row("전체", COH["ret_h"]))
            LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                      title=f"진입 연도별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 분포 "
                            f"(코호트=진입 연월×종목 · 평균이 아니라 분포를 본다)")
            x = pd.to_numeric(COH["ret_h"], errors="coerce").dropna()
            if len(x):
                LOG.info(f"    코호트 {len(x):,}개 · 승률 {float((x > 0).mean())*100:.1f}% · "
                         f"평균 {float(x.mean())*100:+.2f}% · 중앙값 {float(x.median())*100:+.2f}% "
                         f"— 평균 > 중앙값이면 소수 대박에 의존한다는 뜻입니다.")

    # ── 진단 6. 섹터 집중도 시계열 ───────────────────────────────────────────────────────
    LOG.rule("진단 6 — 보유 종목 섹터 집중도")
    with ncq_section("진단6 섹터 집중도"):
        if not ncq_has_rows(H) or "code" not in H.columns:
            ncq_no_data("진단6 섹터", "BT['holdings'] 가 비었거나 code 컬럼이 없습니다.")
        elif not ncq_has_rows(sec) or "industry" not in sec.columns:
            ncq_no_data("진단6 섹터", "sec 에 industry 컬럼이 없어 섹터를 붙일 수 없습니다.")
        else:
            h = H.copy()
            h["code"] = h["code"].astype(str)
            mcol = ncq_pick_col(h, ["month", "cohort", "entry_month"])
            h["_m"] = as_ts_series(h[mcol]) + pd.offsets.MonthEnd(0) if mcol else pd.NaT
            h["_w"] = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns else 1.0
            ind = sec.drop_duplicates(subset=["code"]).set_index(sec.drop_duplicates(
                subset=["code"])["code"].astype(str))["industry"]
            h["_ind"] = h["code"].map(ind.to_dict()).fillna("(미분류)").astype(str)
            miss = float((h["_ind"] == "(미분류)").mean())
            rows = []
            yrs = sorted(set(pd.DatetimeIndex(h["_m"].dropna()).year)) if h["_m"].notna().any() else []
            for y in yrs:
                m = pd.DatetimeIndex(h["_m"]).year == y
                sub = h.loc[m]
                w = sub.groupby("_ind", observed=True)["_w"].sum()
                tot = float(w.sum())
                if tot <= 0:
                    continue
                sh = (w / tot).sort_values(ascending=False)
                top5 = sh.head(5)
                hhi = float((sh ** 2).sum())
                # ★ 폭 104 제약: 1~5위를 각각 컬럼으로 두면 표가 넘친다 → 한 칸에 이어 붙인다.
                cells = " · ".join(f"{_trunc(str(k), 12)} {v*100:.0f}%" for k, v in top5.items())
                rows.append([str(y), ncq_int(float(sub["code"].nunique())),
                             ncq_pct(float(top5.sum()), 0, signed=False), ncq_rpt_num(hhi, 3),
                             cells])
            if not rows:
                ncq_no_data("진단6 섹터", "보유 원장에 유효한 월/가중치가 없어 연도별 집계가 비었습니다.")
            else:
                LOG.table(rows, ["연도", "종목수", "상위5합", "HHI", "상위 5 산업 (비중)"],
                          ["c", "r", "r", "r", "l"], maxw=62,
                          title="연도별 산업 비중 상위 5 (HHI 는 허핀달 — 1 에 가까울수록 한 섹터에 몰림)")
                LOG.info(f"    산업 미분류 비중 {miss*100:.1f}% · "
                         f"상위5 합이 계속 70% 를 넘으면 이 전략은 '신규 커버리지'가 아니라 "
                         f"'특정 섹터 사이클'을 타고 있는 것입니다(R7 레짐 검정과 함께 볼 것).")

    # ── 진단 7. 상·하위 기여 종목 ────────────────────────────────────────────────────────
    LOG.rule("진단 7 — 상위/하위 기여 종목")
    with ncq_section("진단7 기여 종목"):
        if not ncq_has_rows(H) or not {"code", "ret"}.issubset(set(H.columns)):
            ncq_no_data("진단7 기여종목", "BT['holdings'] 에 code/ret 컬럼이 없습니다.")
        else:
            h = H.copy()
            h["code"] = h["code"].astype(str)
            w = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns \
                else pd.Series(1.0, index=h.index)
            r = pd.to_numeric(h["ret"], errors="coerce")
            h["_c"] = w * r
            grp = h.groupby("code", observed=True)
            contrib = grp["_c"].sum().sort_values(ascending=False)
            nmon = grp.size()
            ncoh = grp["cohort"].nunique() if "cohort" in h.columns else None
            def _rows(idx, start=1):
                out = []
                for i, code in enumerate(idx, start):
                    out.append([f"{i}", code, _trunc(names.get(code, ""), 16),
                                ncq_pctp(float(contrib.get(code, np.nan)), 3),
                                ncq_int(float(nmon.get(code, np.nan))),
                                ncq_int(float(ncoh.get(code, np.nan))) if ncoh is not None else NCQ_NA])
                return out
            k = min(20, len(contrib))
            LOG.table(_rows(list(contrib.index[:k])),
                      ["#", "code", "종목명", "기여도", "보유월수", "코호트수"],
                      ["r", "l", "l", "r", "r", "r"],
                      title=f"상위 기여 종목 {k} (기여도 = Σ 월별 weight×ret, 포트 총수익 기여분)")
            tail = list(contrib.index[-k:])[::-1] if k else []
            LOG.table(_rows(tail), ["#", "code", "종목명", "기여도", "보유월수", "코호트수"],
                      ["r", "l", "l", "r", "r", "r"],
                      title=f"하위 기여 종목 {len(tail)} (손실 기여 — 여기가 실전에서 먼저 눈에 띈다)")
            tot = float(contrib.sum())
            top5 = float(contrib.head(max(1, int(round(len(contrib) * 0.05)))).sum())
            LOG.info(f"    총기여 {ncq_pctp(tot, 2)} · 상위 5% 종목 기여 {ncq_pctp(top5, 2)}"
                     + (f" (총기여의 {top5/tot*100:.0f}%)" if tot > 0 else ""))

    # ── 진단 8. 스폰서 그룹별 성과 분해 ──────────────────────────────────────────────────
    LOG.rule("진단 8 — SPONSORED_ONLY vs ORGANIC_ONLY vs MIXED")
    with ncq_section("진단8 스폰서 분해"):
        if not ncq_has_rows(COH) or "sponsor_group" not in COH.columns:
            ncq_no_data("진단8 스폰서", "코호트에 sponsor_group 을 붙이지 못했습니다 "
                                      "(SIG 에 sponsor_group 이 없거나 진입월-종목 조인 실패).")
        else:
            rows = []
            for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                sub = COH[COH["sponsor_group"].astype(str) == g]
                rows.append(ncq_dist_row(g, sub["ret_h"] if len(sub) else pd.Series(dtype=float)))
            other = COH[~COH["sponsor_group"].astype(str).isin(
                ["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"])]
            if len(other):
                rows.append(ncq_dist_row("(그 외/결측)", other["ret_h"]))
            rows.append(ncq_dist_row("전체", COH["ret_h"]))
            LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                      title="스폰서 그룹별 보유수익 분포 — '누가 왜 그 리포트를 냈는가'가 성과를 가르는가")
            trows = []
            for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                x = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == g, "ret_h"],
                                  errors="coerce").dropna()
                t = np.nan
                if len(x) >= 12:
                    try:
                        _mu, t = hac_tstat(x.to_numpy(dtype=float))
                    except Exception:
                        t = np.nan
                trows.append([g, f"{len(x):,}", ncq_pct(float(x.mean()), 2) if len(x) else NCQ_NA,
                              ncq_rpt_num(t, 2),
                              _trunc(NCQ_SPONSOR_DOC.get(g, ""), 44)])
            LOG.table(trows, ["그룹", "n", "평균 보유수익", "t(HAC·참고)", "이 그룹의 뜻"],
                      ["l", "r", "r", "r", "l"], maxw=46,
                      title="그룹별 요약 (t 는 코호트 오버랩 때문에 보수적으로 읽을 것 — 독립표본이 아니다)")
            n_org = int((COH["sponsor_group"].astype(str) == "ORGANIC_ONLY").sum())
            if n_org < 30:
                LOG.warn(f"ORGANIC_ONLY 코호트가 {n_org}개뿐입니다. 이 전략의 핵심 주장(자발적 신규 "
                         f"커버리지에 정보가 있다)을 검정할 표본이 사실상 없습니다.")
            m_org = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == "ORGANIC_ONLY",
                                          "ret_h"], errors="coerce").mean()
            m_spo = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == "SPONSORED_ONLY",
                                          "ret_h"], errors="coerce").mean()
            if ncq_isnum(m_org) and ncq_isnum(m_spo) and m_spo >= m_org:
                LOG.warn("SPONSORED_ONLY 의 평균 수익이 ORGANIC_ONLY 이상입니다. 이는 신호가 "
                         "'증권사의 자발적 관심'이 아니라 '스폰서 프로그램의 종목 선정 기준'을 "
                         "타고 있을 가능성을 시사합니다 — 그대로 보고합니다.")

    # ── 진단 9. 텍스트 z 분위별 수익 (단조성) ────────────────────────────────────────────
    LOG.rule("진단 9 — 텍스트 z 분위(quintile)별 수익 · 단조성")
    with ncq_section("진단9 단조성"):
        did = False
        if ncq_has_rows(COH) and "z" in COH.columns:
            d = COH.dropna(subset=["z", "ret_h"]).copy()
            if len(d) >= 25:
                did = True
                d["_q"] = (d.groupby(pd.DatetimeIndex(d["entry_month"]).to_period("M"),
                                     observed=True)["z"]
                            .rank(pct=True, method="average"))
                d["_qb"] = np.ceil(d["_q"] * 5).clip(1, 5)
                rows = []
                means = []
                for q in range(1, 6):
                    sub = d[d["_qb"] == q]
                    rows.append(ncq_dist_row(f"Q{q}" + (" (최저 z)" if q == 1 else
                                                        " (최고 z)" if q == 5 else ""),
                                             sub["ret_h"]))
                    means.append(float(pd.to_numeric(sub["ret_h"], errors="coerce").mean())
                                 if len(sub) else np.nan)
                LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                          title=f"텍스트 z 분위별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 "
                                f"(코호트 기준 — 선별된 종목만 포함될 수 있음)")
                rho_q, p_q = ncq_spearman(list(range(1, 6)), means)
                rho_i, p_i = ncq_spearman(d["z"].to_numpy(dtype=float),
                                          pd.to_numeric(d["ret_h"], errors="coerce").to_numpy(dtype=float))
                LOG.table([["분위 평균 vs 분위번호", ncq_rpt_num(rho_q, 3),
                            ncq_rpt_num(p_q, 4) if ncq_isnum(p_q) else "scipy 없음",
                            "5점이라 검정력은 매우 낮음"],
                           ["개별 관측 z vs 수익", ncq_rpt_num(rho_i, 3),
                            ncq_rpt_num(p_i, 4) if ncq_isnum(p_i) else "scipy 없음",
                            f"n={len(d):,} · 코호트 오버랩으로 독립 아님"]],
                          ["대상", "스피어만 ρ", "p", "주의"], ["l", "r", "r", "l"], maxw=40,
                          title="단조성 검정")
                mono = all(ncq_isnum(a) and ncq_isnum(b) and b >= a
                           for a, b in zip(means[:-1], means[1:]))
                if mono:
                    LOG.ok("Q1→Q5 평균이 단조 증가합니다. 다만 분위 간 차이가 표본오차 안일 수 있으니 "
                           "위 ρ 와 각 분위 n 을 함께 보세요.")
                else:
                    LOG.warn("Q1→Q5 평균이 단조가 아닙니다. 텍스트 z 가 '연속적인 강도'가 아니라 "
                             "특정 구간에서만 의미를 가지거나, 표본이 얇아 노이즈일 수 있습니다. "
                             "단조성이 없다고 전략이 자동 기각되지는 않지만, 근거는 그만큼 약합니다.")
                cov = [int((d["_qb"] == q).sum()) for q in range(1, 6)]
                if min(cov) == 0:
                    LOG.warn(f"비어 있는 분위가 있습니다(분위별 n={cov}). 코호트가 상위 tercile 만 "
                             f"포함하기 때문일 가능성이 큽니다 — 아래 전 이벤트 기준 표를 보세요.")
        if ncq_has_rows(SIG) and {"z"}.issubset(set(SIG.columns)) and "fwd_ret" in SIG.columns:
            s = SIG.dropna(subset=["z", "fwd_ret"]).copy()
            if len(s) >= 25:
                did = True
                s["month"] = as_ts_series(s["month"]) + pd.offsets.MonthEnd(0)
                s["_q"] = s.groupby("month", observed=True)["z"].rank(pct=True, method="average")
                s["_qb"] = np.ceil(s["_q"] * 5).clip(1, 5)
                rows, means = [], []
                for q in range(1, 6):
                    sub = s[s["_qb"] == q]
                    rows.append(ncq_dist_row(f"Q{q}", sub["fwd_ret"]))
                    means.append(float(pd.to_numeric(sub["fwd_ret"], errors="coerce").mean())
                                 if len(sub) else np.nan)
                LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                          title="텍스트 z 분위별 1개월 선도수익 (전 이벤트 — 12개월 수익이 "
                                "선별 종목에만 있어 대체 지표로 병기)")
                rho, p = ncq_spearman(list(range(1, 6)), means)
                LOG.info(f"    분위 단조성 ρ={ncq_rpt_num(rho, 3)} "
                         f"p={ncq_rpt_num(p, 4) if ncq_isnum(p) else 'scipy 없음'} "
                         f"— 보유기간이 1개월이라 전략의 실제 구성과 다릅니다(참고용).")
        if not did:
            ncq_no_data("진단9 단조성", "z 와 수익을 함께 가진 관측이 25건 미만입니다 "
                                      "(SIG.z / SIG.fwd_ret / 코호트 ret_h 중 어느 것도 충분치 않음).")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  6. 해석 참조표
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_lexicon_group_info() -> "OrderedDict[str, dict]":
    """렉시콘 그룹 메타 — 라벨/가중/어휘수는 정본(NCQ_LEXICON)에서, 해석문은 이 파일에서.

    정본에만 있는 그룹(렉시콘을 v2 로 올린 경우)도 표에서 빠지지 않게 합집합으로 만든다.
    """
    out: "OrderedDict[str, dict]" = OrderedDict()
    for g, (label, mean_, fire, nofire, sign) in NCQ_GROUP_DOC.items():
        out[g] = {"label": label, "뜻": mean_, "발화": fire, "미발화": nofire,
                  "방향": sign, "weight": None, "n_terms": None, "출처": "내장 참조표"}
    lex = ncq_g("NCQ_LEXICON")
    try:
        groups = lex.get("groups") if isinstance(lex, dict) else None
        if isinstance(groups, dict):
            for k, v in groups.items():
                gid = str(k).upper()
                if gid.startswith("G_"):
                    gid = gid[2:]
                if gid not in out:
                    out[gid] = {"label": str(k), "뜻": "(정본 렉시콘에만 존재 — 해석문 미작성)",
                                "발화": NCQ_NA, "미발화": NCQ_NA, "방향": "?",
                                "weight": None, "n_terms": None, "출처": "NCQ_LEXICON"}
                d = out[gid]
                if isinstance(v, dict):
                    if v.get("label"):
                        d["label"] = str(v["label"])
                        d["출처"] = "NCQ_LEXICON"
                    if ncq_isnum(v.get("weight")):
                        d["weight"] = float(v["weight"])
                    terms = v.get("terms") or v.get("words") or v.get("patterns")
                    if isinstance(terms, (list, tuple, set)):
                        d["n_terms"] = len(terms)
                elif isinstance(v, (list, tuple, set)):
                    d["n_terms"] = len(v)
    except Exception:
        pass
    return out


def report_interpretation(SIG, EV, SCORE) -> None:
    """해석 참조표 — 이 신호가 발화했다는 것이 무엇을 뜻하는가.

    참조표 부분은 데이터가 없어도 항상 출력한다(리포트의 존재 이유가 해석이기 때문).
    통계 부분은 데이터가 없으면 '데이터 없음 + 이유'를 남긴다.
    """
    LOG.banner("해석 참조표",
               "렉시콘 그룹의 뜻 · 발화/미발화의 의미 · 실제 패널의 발화 프로필 · 이벤트 유형 분포")
    info = ncq_lexicon_group_info()

    with ncq_section("렉시콘 그룹 정의"):
        # 폭 104 제약: '정의 출처'는 표에서 빼고 아래 한 줄로 요약한다(값이 대개 동일하다).
        rows = [[g, _trunc(d["label"], 14), d["방향"],
                 ncq_rpt_num(d["weight"], 1) if ncq_isnum(d["weight"]) else NCQ_NA,
                 ncq_int(d["n_terms"]) if ncq_isnum(d["n_terms"]) else NCQ_NA,
                 _trunc(d["뜻"], 54)]
                for g, d in info.items()]
        LOG.table(rows, ["그룹", "라벨", "방향", "가중", "어휘수", "무엇을 잡는가"],
                  ["c", "l", "c", "r", "r", "l"], maxw=56,
                  title="렉시콘 그룹 A/B/C/D/H/N (방향 +강=최대가중, −역=역가중)")
        srcs = sorted(set(d["출처"] for d in info.values()))
        LOG.info(f"    정의 출처: {', '.join(srcs)} "
                 f"(라벨·가중·어휘수는 정본 NCQ_LEXICON, 해석문은 리포트 모듈 내장 참조표)")
        LOG.info(f"    섹션 가중: {json.dumps((ncq_g('NCQ_LEXICON') or {}).get('section_weight', {}), ensure_ascii=False)}"
                 f" · 부정어 창: {(ncq_g('NCQ_LEXICON') or {}).get('negation_window', NCQ_NA)}자 "
                 f"— 부정 문맥에서는 매칭을 무효화합니다(‘증설이 어렵다’를 호재로 세지 않기 위함).")

    with ncq_section("발화/미발화 해석"):
        rows = [[g, _trunc(d["발화"], 44), _trunc(d["미발화"], 44)] for g, d in info.items()]
        LOG.table(rows, ["그룹", "발화했다는 것은 무엇을 뜻하는가", "발화하지 않았다는 것은 무엇을 뜻하는가"],
                  ["c", "l", "l"], maxw=46,
                  title="★ 이 표가 이 전략의 전부다 — 점수는 이 해석의 요약일 뿐이다")
        LOG.info("    주의: H/N 은 역가중이므로 '발화 = 점수 하락'입니다. 발화율이 높은 것 자체가 "
                 "나쁜 것이 아니라, 그 문서가 근거보다 기대를 많이 적었다는 뜻입니다.")

    with ncq_section("실제 패널 발화 통계"):
        gcols = [f"g_{g}" for g in info.keys()]
        have = [c for c in gcols if ncq_has_rows(SCORE) and c in SCORE.columns]
        if not have:
            ncq_no_data("발화 통계", "SCORE 가 비었거나 g_* 컬럼이 없습니다 "
                                   "(텍스트 스코어링 P3 미수행 또는 PDF 추출 전면 실패).")
        else:
            S = SCORE
            abs_mean = {c: float(pd.to_numeric(S[c], errors="coerce").abs().mean()) for c in have}
            tot_abs = float(sum(v for v in abs_mean.values() if np.isfinite(v))) or np.nan
            rows = []
            for c in have:
                v = pd.to_numeric(S[c], errors="coerce")
                obs = int(v.notna().sum())
                fired = v.abs() > 0
                nf = int(fired.sum())
                corr = np.nan
                if "doc_score" in S.columns:
                    try:
                        corr = float(v.corr(pd.to_numeric(S["doc_score"], errors="coerce")))
                    except Exception:
                        corr = np.nan
                rows.append([c.replace("g_", ""), f"{obs:,}", f"{nf:,}",
                             ncq_pct(nf / max(1, obs), 1, signed=False),
                             ncq_rpt_num(float(v[fired].mean()), 3) if nf else NCQ_NA,
                             ncq_rpt_num(float(v.mean()), 3) if obs else NCQ_NA,
                             ncq_pct(abs_mean[c] / tot_abs, 1, signed=False)
                             if ncq_isnum(tot_abs) and tot_abs > 0 else NCQ_NA,
                             ncq_rpt_num(corr, 3)])
            LOG.table(rows, ["그룹", "관측문서", "발화문서", "발화율", "발화시 평균",
                             "전체 평균", "절대기여 비중", "doc_score 상관"],
                      ["c", "r", "r", "r", "r", "r", "r", "r"],
                      title="그룹별 발화 빈도·평균 기여 (문서 단위)")
            dead = [r[0] for r in rows if r[2] == "0"]
            if dead:
                LOG.warn(f"한 번도 발화하지 않은 그룹: {', '.join(dead)}. 렉시콘 어휘가 실제 리포트 "
                         f"문체와 어긋났거나, 해당 섹션이 추출되지 않았습니다 — 점수에서 그 축은 "
                         f"존재하지 않는 것과 같습니다.")

    with ncq_section("z tercile 그룹 프로필"):
        gcols = [f"g_{g}" for g in info.keys()]
        have = [c for c in gcols if ncq_has_rows(SCORE) and c in SCORE.columns]
        if not have or not ncq_has_rows(SIG) or "z" not in getattr(SIG, "columns", []):
            ncq_no_data("z tercile 프로필", "SIG.z 또는 SCORE.g_* 가 없어 상·하위 대비표를 만들 수 없습니다.")
        else:
            S = SCORE.copy()
            if not {"month", "code"}.issubset(set(S.columns)):
                ncq_no_data("z tercile 프로필", "SCORE 에 month/code 가 없어 SIG 와 조인할 수 없습니다.")
            else:
                S["month"] = as_ts_series(S["month"]) + pd.offsets.MonthEnd(0)
                S["code"] = S["code"].astype(str)
                agg = S.groupby(["month", "code"], observed=True)[have].mean().reset_index()
                Q = SIG.copy()
                Q["month"] = as_ts_series(Q["month"]) + pd.offsets.MonthEnd(0)
                Q["code"] = Q["code"].astype(str)
                Q = Q[["month", "code", "z"]].dropna(subset=["z"])
                M = Q.merge(agg, how="inner", on=["month", "code"])
                if len(M) < 20:
                    ncq_no_data("z tercile 프로필", f"조인 결과가 {len(M)}행뿐입니다 "
                                                  f"(month/code 키가 어긋났을 가능성).")
                else:
                    ter = float(ncq_g("NCQ_TERCILE", 1 / 3) or (1 / 3))
                    r = M.groupby("month", observed=True)["z"].rank(pct=True, method="average")
                    hi = M[r >= (1.0 - ter)]
                    lo = M[r <= ter]
                    rows = []
                    for c in have:
                        a = pd.to_numeric(hi[c], errors="coerce")
                        b = pd.to_numeric(lo[c], errors="coerce")
                        ma, mb = (float(a.mean()) if len(a) else np.nan,
                                  float(b.mean()) if len(b) else np.nan)
                        rows.append([c.replace("g_", ""), ncq_rpt_num(ma, 3), ncq_rpt_num(mb, 3),
                                     ncq_rpt_num(ma - mb, 3) if (ncq_isnum(ma) and ncq_isnum(mb)) else NCQ_NA,
                                     ncq_pct(float((a.abs() > 0).mean()), 1, signed=False) if len(a) else NCQ_NA,
                                     ncq_pct(float((b.abs() > 0).mean()), 1, signed=False) if len(b) else NCQ_NA])
                    LOG.table(rows, ["그룹", "상위T 평균", "하위T 평균", "차이",
                                     "상위T 발화율", "하위T 발화율"],
                              ["c", "r", "r", "r", "r", "r"],
                              title=f"z 상위/하위 tercile 의 그룹 프로필 대비 "
                                    f"(상위 n={len(hi):,} · 하위 n={len(lo):,})")
                    LOG.info("    ★ 읽는 법: 상·하위 tercile 을 실제로 가르는 그룹이 무엇인지 보세요. "
                             "차이가 H/N 에서만 크다면 이 신호는 '좋은 이야기'가 아니라 "
                             "'덜 조심스러운 문체'를 고르고 있는 것입니다.")

    with ncq_section("이벤트 유형·스폰서 분포"):
        LOG.table([[k, v[0], _trunc(v[1], 62)] for k, v in NCQ_EVENT_TYPE_DOC.items()],
                  ["유형", "이름", "판정 기준"], ["c", "l", "l"], maxw=64,
                  title="신규 커버리지 이벤트 유형 (정본은 ncq_30_coverage)")
        LOG.table([[k, _trunc(v, 78)] for k, v in NCQ_SPONSOR_DOC.items()],
                  ["스폰서 그룹", "뜻"], ["l", "l"], maxw=80, title="스폰서 그룹")
        if not ncq_has_rows(EV) or "event_type" not in EV.columns:
            ncq_no_data("이벤트 분포", "EV 에 event_type 이 없습니다.")
        else:
            sg = EV["sponsor_group"].astype(str) if "sponsor_group" in EV.columns else None
            et = EV["event_type"].astype(str)
            if sg is None:
                vc = et.value_counts()
                LOG.table([[k, f"{v:,}", ncq_pct(v / max(1, len(et)), 1, signed=False)]
                           for k, v in vc.items()],
                          ["유형", "건수", "비중"], ["c", "r", "r"],
                          title="이벤트 유형 분포 (sponsor_group 부재로 교차표 생략)")
            else:
                cols = ["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"]
                cols += sorted(set(sg.unique()) - set(cols))
                rows = []
                for t in sorted(set(et.unique())):
                    m = et == t
                    n = int(m.sum())
                    cells = [f"{int((m & (sg == c)).sum()):,}" for c in cols]
                    rows.append([t, f"{n:,}"] + cells +
                                [ncq_pct(n / max(1, len(et)), 1, signed=False)])
                tot = [f"{int((sg == c).sum()):,}" for c in cols]
                rows.append(["합계", f"{len(et):,}"] + tot + ["100.0%"])
                LOG.table(rows, ["유형", "건수"] + [_trunc(c, 14) for c in cols] + ["비중"],
                          ["c", "r"] + ["r"] * len(cols) + ["r"], maxw=16,
                          title="이벤트 유형 × 스폰서 그룹 교차표")
                p_h1 = float((et == "H1").mean())
                LOG.info(f"    H1(전면 신규) 비중 {p_h1*100:.1f}%. "
                         f"H2 가 대부분이라면 이 전략은 '정보 공백'이 아니라 "
                         f"'하우스 간 커버 확산'을 측정하고 있는 것입니다.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  7. 거시 흐름 지도
# ═══════════════════════════════════════════════════════════════════════════════════════════
NCQ_PHASE_MAP = [
    ("P0", "부트 · 캐시 · PIT 유니버스",
     ["입력  종목마스터(pykrx 월말 스냅샷 / FDR·KIND 상장·폐지 / DART corpCode) · KRX·pykrx 일봉",
      "출력  sec · px_daily · pxm(월말 신호일 → 익영업일 시가 exec_px) · MCAP · UNI",
      "캐시  _shared/table/{krx_ohlcv_daily, security_master_ncq, pykrx_snapshot_*}  ← 공용(타 전략 재사용)",
      "PIT   시총·ADV 는 그 달 말 관측값만. 상폐 종목을 유니버스에서 빼지 않는다(생존자편향 §10)"]),
    ("P1", "리서치 인덱스 수집 (가장 긴 단계 · 예산 초과 시 열화 L1)",
     ["입력  IRS(거래소 발간지원) · 네이버 금융 리서치 · 한경컨센서스",
      "출력  REP(report_uid, source, pub_date, stock_code, broker_id, is_sponsored, …)",
      "캐시  _shared/table/research_report_master · _shared/blob/research/report_pdf/<해시>",
      "함정  종목명→티커 매핑 실패는 신규·소형·개명 종목에 몰린다 = 정확히 이 전략의 표적"]),
    ("P2", "커버리지 완결성 · 신규 커버리지 이벤트 판정",
     ["입력  REP · UNI · months",
      "출력  diag(월별 완결성 · archive_incomplete) → valid_start · EV(H1/H2 · sponsor_group)",
      "게이트 아카이브 3개월+ 연속 결손 구간 이후로 유효 백테스트 시작월을 늦춘다",
      "PIT   판정에 쓰는 리포트는 pub_date ≤ 해당 월말. 룩백/번인 구간은 판정에만 쓰고 매매하지 않는다"]),
    ("P3", "PDF 섹션 추출 · 렉시콘 스코어링 (예산 초과 시 열화 L2)",
     ["입력  EV 에 연결된 리포트의 PDF · 제목 · 요약",
      "출력  TXT(sec_title/headline/body, extract_ok) → SCORE(doc_score, g_A…g_N)",
      "동결  렉시콘·사전등록은 수익률 확인 전에 동결하고 SHA 를 매니페스트에 남긴다(계약 §6-4)",
      "함정  추출 실패는 하우스별로 편향된다 → 텍스트 z 표본이 특정 증권사로 쏠릴 수 있다"]),
    ("P4", "횡단면 z · 신호 패널 · 오버랩 코호트 백테스트",
     ["입력  SCORE · EV · UNI · pxm",
      "출력  SIG(z, rank_pct, selected, placebo) → BT{returns, holdings, cohorts}",
      "체결  월말 신호 → 익영업일 시가 · ADV 참여율 상한 · 왕복비용 · 상폐 시 -50% 후 현금화",
      "대조  placebo = z 하위 tercile · 주 벤치 = Bottom-N 동일가중"]),
    ("P5", "강건성 (사전등록 P1~P4 · BH-FDR · 부트스트랩 · 순열 · WF · PBO · DSR)",
     ["입력  SIG · BT · bench_ew · run_fn",
      "출력  NCQ_ROBUST(검정별 pass/kill) · 민감도 격자 · 다중검정 보정 결과",
      "원칙  실패한 검정은 그대로 출력한다. 파라미터를 바꿔 통과시키는 것이 가장 해로운 행동이다"]),
    ("P6", "리포트 · 산출물",
     ["입력  위 전부 + MANIFEST",
      "출력  콘솔 표(1순위) · report.html · coverage.html · manifest.json · parquet/csv",
      "저장  VAULT.put_table(scope='private') — 공용 인덱스에는 원본·범용 정제본만 넣는다"]),
]


def report_dataflow_map() -> None:
    """거시 흐름 지도 — 에러가 나면 어느 상자인지부터 좁힌다."""
    LOG.banner("데이터 흐름 지도 (거시) — ARC-NCQ v1.0",
               "Phase 0~6 · 각 단계의 입출력 / 캐시 위치 / PIT 관문을 한 화면에")
    budgets = ncq_g("NCQ_PHASE_BUDGET_S", {}) or {}
    spent = {}
    try:
        pb = ncq_g("PhaseBudget")
        spent = dict(getattr(pb, "_spent", {}) or {})
    except Exception:
        spent = {}
    width = min(NCQ_W - 2, 100)
    for i, (pid, title, lines) in enumerate(NCQ_PHASE_MAP):
        cap = budgets.get(pid)
        sp = spent.get(pid)
        head = f"{pid}  {title}"
        if ncq_isnum(cap):
            head += f"   [예산 {float(cap)/60:.0f}분"
            head += (f" · 실측 {float(sp)/60:.1f}분]" if ncq_isnum(sp) else "]")
        for ln in ncq_box(head, lines, width=width):
            _safe_print("  " + ln)
        if i < len(NCQ_PHASE_MAP) - 1:
            gate = "▼   PIT 관문: pub_date ≤ 월말 · 진입은 익영업일 시가" if pid in ("P1", "P3") else "▼"
            _safe_print("  " + " " * (width // 2 - 1) + gate)
    _safe_print("")
    for ln in ncq_box("실패했을 때 보는 순서",
                      ["1) PIPE.report_stages() — 어느 스테이지에서 멈췄는가",
                       "2) PIPE.report_flow()   — 그 스테이지가 몇 행을 읽고 썼는가 (0행이면 수집 실패)",
                       "3) report_coverage_diagnostics — 아카이브가 얇은 구간인가",
                       "4) report_diagnostics 진단1 퍼널 — 어느 관문이 표본을 죽였는가",
                       "5) report_headline — 열화 사다리가 적용된 실행인가"],
                      width=width):
        _safe_print("  " + ln)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  8. HTML 산출물 — 외부 라이브러리 없이 순수 문자열 (인라인 CSS · <table> · 인라인 SVG)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def ncq_html_head(title: str, sub: str = "") -> str:
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{ncq_esc(title)}</title><style>{NCQ_HTML_CSS}</style></head><body><div class='wrap'>"
            f"<h1>{ncq_esc(title)}</h1><p class='sub'>{ncq_esc(sub)}</p>")


def ncq_html_tail(extra: str = "") -> str:
    return (f"<footer>{extra}생성 {ncq_esc(_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} · "
            f"{ncq_esc(ncq_g('STRATEGY_ID', 'ARC_NCQ_V1'))} "
            f"{ncq_esc(ncq_g('BUILD_VERSION', ''))} · "
            f"이 파일은 자체 완결형입니다(외부 리소스 요청 없음).</footer></div></body></html>")


def ncq_html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]],
                   title: str = "", note: str = "", left_cols: Sequence[int] = (0,)) -> str:
    """표 하나. rows 가 비면 '데이터 없음'을 명시해서 남긴다(조용히 사라지지 않게)."""
    out = []
    if title:
        out.append(f"<h3>{ncq_esc(title)}</h3>")
    if not rows:
        out.append("<p class='mut'>데이터 없음 — 이 표를 만들 입력이 비었습니다.</p>")
        if note:
            out.append(f"<p class='note'>{ncq_esc(note)}</p>")
        return "".join(out)
    lc = set(int(i) for i in (left_cols or ()))
    out.append("<table><thead><tr>")
    for i, h in enumerate(headers):
        out.append(f"<th class='{'l' if i in lc else ''}'>{ncq_esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>")
        for i in range(len(headers)):
            v = r[i] if i < len(r) else ""
            cls = "l" if i in lc else ""
            txt = ncq_esc("" if v is None else v)
            if isinstance(v, str) and (v.startswith("✘") or v.startswith("−") or "미달" in v):
                cls += " bad"
            out.append(f"<td class='{cls.strip()}'>{txt}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    if note:
        out.append(f"<p class='note'>{ncq_esc(note)}</p>")
    return "".join(out)


def ncq_svg_line(series_dict: Dict[str, Any], width: int = 880, height: int = 300,
                 title: str = "", pct: bool = True) -> str:
    """인라인 SVG 라인차트. 외부 라이브러리 없음. 그릴 게 없으면 빈 문자열."""
    pal = ["#1a73e8", "#d93025", "#188038", "#f29900", "#9334e6", "#00838f"]
    items = []
    for name, s in (series_dict or {}).items():
        try:
            ss = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            continue
        if len(ss):
            items.append((str(name), ss))
    if not items:
        return ""
    try:
        uni = pd.Index(sorted(set().union(*[set(pd.Index(s.index)) for _, s in items])))
        cols = [(nm, pd.Series(s).reindex(uni).astype(float).ffill()) for nm, s in items]
    except Exception:
        return ""
    # ★ dropna() 만으로는 ±inf 가 남는다 → ymax=inf → 좌표가 전부 'nan' 인 SVG 가 조용히 생성된다.
    #   유한값만으로 축을 잡고, inf 점은 아래 polyline 루프의 isfinite 검사에서 자연히 빠진다.
    finite = [a[np.isfinite(a)] for a in (c.to_numpy(dtype=float) for _, c in cols)]
    finite = [a for a in finite if a.size]
    if not finite:
        return ""
    allv = np.concatenate(finite)
    ymin, ymax = float(allv.min()), float(allv.max())
    # ★ 절대 epsilon 은 큰 값(원화 금액·월별 건수)에서 float64 정밀도에 먹혀 span=0 → ZeroDivisionError.
    scale = max(abs(ymin), abs(ymax), 1.0)
    if (ymax - ymin) <= scale * 1e-9:
        ymin, ymax = ymin - scale * 1e-6, ymax + scale * 1e-6
    pad = (ymax - ymin) * 0.06
    ymin, ymax = ymin - pad, ymax + pad
    L, Rr, T, B = 66, 16, 30 if title else 12, 34
    n = len(uni)
    def X(i):
        return L + (0 if n <= 1 else (width - L - Rr) * i / (n - 1))
    def Y(v):
        return T + (height - T - B) * (ymax - float(v)) / (ymax - ymin)
    def fnum(v):
        return f"{v*100:.0f}%" if pct else f"{v:.3g}"
    p = [f"<svg viewBox='0 0 {width} {height}' width='100%' "
         f"style='max-width:{width}px;height:auto' xmlns='http://www.w3.org/2000/svg'>",
         f"<rect x='0' y='0' width='{width}' height='{height}' fill='#ffffff'/>"]
    if title:
        p.append(f"<text x='{L}' y='18' font-size='13' fill='#1f2328'>{ncq_esc(title)}</text>")
    for k in range(5):                                    # y 격자
        v = ymax - (ymax - ymin) * k / 4.0
        y = Y(v)
        p.append(f"<line x1='{L}' y1='{y:.1f}' x2='{width-Rr}' y2='{y:.1f}' "
                 f"stroke='#e6e9ee' stroke-width='1'/>")
        p.append(f"<text x='{L-6}' y='{y+4:.1f}' font-size='11' fill='#6a737d' "
                 f"text-anchor='end'>{ncq_esc(fnum(v))}</text>")
    if ymin < 0 < ymax:
        p.append(f"<line x1='{L}' y1='{Y(0):.1f}' x2='{width-Rr}' y2='{Y(0):.1f}' "
                 f"stroke='#9aa4b0' stroke-width='1' stroke-dasharray='4 3'/>")
    for ci, (nm, c) in enumerate(cols):
        col = pal[ci % len(pal)]
        pts = []
        for i, v in enumerate(c.to_numpy(dtype=float)):
            if np.isfinite(v):
                pts.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(pts) >= 2:
            p.append(f"<polyline fill='none' stroke='{col}' stroke-width='2' "
                     f"stroke-linejoin='round' points='{' '.join(pts)}'/>")
        lx = L + 4 + ci * max(120, int((width - L - Rr) / max(1, len(cols))))
        p.append(f"<rect x='{lx}' y='{height-16}' width='10' height='3' fill='{col}'/>")
        p.append(f"<text x='{lx+14}' y='{height-11}' font-size='11' fill='#39424e'>"
                 f"{ncq_esc(_trunc(nm, 22))}</text>")
    for i, lab in ((0, ncq_xlabel(uni[0])), (n // 2, ncq_xlabel(uni[n // 2])),
                   (n - 1, ncq_xlabel(uni[-1]))):
        p.append(f"<text x='{X(i):.1f}' y='{height-B+16}' font-size='11' fill='#6a737d' "
                 f"text-anchor='middle'>{ncq_esc(lab)}</text>")
    p.append("</svg>")
    return "<div class='chart'>" + "".join(p) + "</div>"


def ncq_headline_html(f: "OrderedDict[str, Any]", warns: Sequence[str]) -> str:
    out = []
    if warns:
        out.append("<div class='alert'><b>⚠ 위험 경고 — 아래 숫자를 읽기 전에</b><ul>" +
                   "".join(f"<li>{ncq_esc(w)}</li>" for w in warns) + "</ul></div>")
    else:
        out.append("<div class='ok'>§15-6 위험 경고 해당 없음. "
                   "다만 '경고가 없다'가 '결과가 좋다'는 뜻은 아닙니다.</div>")
    rows = [
        ["적용된 열화 단계", ", ".join(f["열화단계"]) if f["열화단계"] else "없음 (사전등록 기준선)"],
        ["유효 백테스트 윈도우",
         f"{ncq_xlabel(f['유효시작월']) if f['유효시작월'] is not None else NCQ_NA} ~ "
         f"{ncq_xlabel(f['유효종료월']) if f['유효종료월'] is not None else NCQ_NA} "
         f"({ncq_rpt_num(f['유효연수'], 2)}년)"],
        ["총 이벤트 수", ncq_int(f["총이벤트수"])],
        ["월평균 이벤트 수", ncq_rpt_num(f["월평균이벤트"], 2)],
        ["IRS(스폰서) 비중 · 리포트", ncq_pct(f["IRS리포트비중"], 1, signed=False)],
        ["IRS(스폰서) 비중 · 이벤트", ncq_pct(f["IRS이벤트비중"], 1, signed=False)],
        ["종목명→티커 매핑 실패율", ncq_pct(f["티커매핑실패율"], 2, signed=False)],
        ["PDF 추출 실패율", ncq_pct(f["PDF추출실패율"], 2, signed=False)],
        ["아카이브 결손 태깅 월", ncq_int(f["결손태깅월수"])],
    ]
    out.append(ncq_html_table(["필수 표시 항목(§15-6)", "값"], rows, left_cols=(0,)))
    return "".join(out)


def write_html_report(outdir, ctx) -> str:
    """성과·진단 요약 HTML. ctx 에서 가용한 것만 넣고 없으면 생략한다. 반환은 파일 경로."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, f"ncq_report_{_dt.datetime.now():%Y%m%d_%H%M}.html")
    BT = ncq_rpt_ctx_get(ctx, "BT")
    benches = ncq_rpt_ctx_get(ctx, "benches") or {}
    EV = ncq_rpt_ctx_get(ctx, "EV")
    SIG = ncq_rpt_ctx_get(ctx, "SIG")
    sec = ncq_rpt_ctx_get(ctx, "sec")
    names = ncq_name_map(sec)
    f = ncq_headline_facts(ctx)

    warns = []
    try:
        if ncq_isnum(f["월평균이벤트"]) and f["월평균이벤트"] < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5):
            warns.append(f"월평균 이벤트 {f['월평균이벤트']:.2f}건 — 최소 기준 미달. "
                         f"횡단면 선별이 사실상 소수 종목 추첨입니다.")
        if ncq_isnum(f["총이벤트수"]) and f["총이벤트수"] < float(ncq_g("NCQ_MIN_TOTAL_EVENTS", 800) or 800):
            warns.append(f"총 이벤트 {int(f['총이벤트수']):,}건 — 최소 기준 미달. 검정력이 낮습니다.")
        if ncq_isnum(f["IRS이벤트비중"]) and f["IRS이벤트비중"] > 0.70:
            warns.append(f"IRS(스폰서) 포함 이벤트 비중 {f['IRS이벤트비중']*100:.1f}% — 70% 초과. "
                         f"자발적 관심이 아니라 발간지원 대상 선정을 측정할 위험.")
        if ncq_isnum(f["유효연수"]) and f["유효연수"] < float(ncq_g("NCQ_MIN_VALID_YEARS", 5.0) or 5.0):
            warns.append(f"유효 구간 {f['유효연수']:.2f}년 — 최소 기준 미달.")
        if f["열화단계"]:
            warns.append("열화 적용: " + ", ".join(f["열화단계"]) + " — 기준선과 조건이 다릅니다.")
    except Exception:
        pass

    H: List[str] = [ncq_html_head(
        f"ARC-NCQ v1.0 리포트 — {ncq_esc(str((BT or {}).get('label', '') if isinstance(BT, dict) else ''))}",
        f"{ncq_g('BACKTEST_START', '?')} ~ {ncq_g('BACKTEST_END', '?')} · "
        f"오버랩 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유 · 익영업일 시가 체결 · 롱온리 · "
        f"실행모드 {ncq_g('RUN_MODE', '?')}")]

    H.append("<h2>0. 헤드라인 (§15-6)</h2>")
    H.append(ncq_headline_html(f, warns))

    # 성과
    H.append("<h2>1. 성과</h2>")
    R = ncq_ret_series(BT)
    pf = ncq_g("perf_stats")
    # ★ perf_stats 는 이 모듈 밖(ncq_50_backtest)의 함수다. 여기서 예외가 나면 HTML 파일 자체가
    #   만들어지지 않아 진단 수단이 통째로 사라진다 — 표 하나만 포기하고 나머지는 계속 쓴다.
    s: Dict[str, Any] = {}
    s_err = ""
    if callable(pf) and isinstance(BT, dict) and ncq_has_rows(BT.get("returns")):
        try:
            s = pf(BT["returns"]) or {}
        except Exception as e:                                    # noqa
            s, s_err = {}, f"{type(e).__name__}: {str(e)[:180]}"
            LOG.warn(f"[HTML 성과표] perf_stats 실패 — 이 표만 건너뜁니다: {s_err}")
    if s:
        order = [k for k in NCQ_PERF_ORDER if k in s] + [k for k in s if k not in NCQ_PERF_ORDER]
        H.append(ncq_html_table(["지표", "값"], [[k, ncq_fmt_metric(k, s[k])] for k in order],
                                title="포트폴리오 성과 (비용 차감 후)", left_cols=(0,)))
    else:
        H.append("<p class='mut'>성과 지표 없음 — " +
                 (f"perf_stats 호출 실패({ncq_esc(s_err)})" if s_err
                  else "BT['returns'] 가 비었습니다") + ".</p>")
    brows = ncq_bench_table(R, benches)
    H.append(ncq_html_table(["역할", "벤치마크", "벤치 누적", "전략 누적", "초과",
                             "월평균 초과", "HAC t", "겹친 월"], brows,
                            title="벤치마크 대비",
                            note="판정 기준은 주 벤치마크(Bottom-N 동일가중)입니다. "
                                 "지수 대비 초과는 소형주 강세 구간에서 전략의 공로가 아닙니다.",
                            left_cols=(0, 1)))
    if len(R):
        curves: "OrderedDict[str, pd.Series]" = OrderedDict()
        curves["전략(NCQ)"] = ncq_cum(R)
        for k in ncq_bench_order(benches):
            try:
                b = pd.to_numeric(pd.Series(benches[k]), errors="coerce").reindex(R.index)
            except Exception:
                continue
            if int(b.notna().sum()):
                curves[_trunc(k, 20)] = ncq_cum(b)
        H.append(ncq_svg_line(curves, title="누적수익 곡선 (전략 관측월 · 비용 차감 후)", pct=True))
        yr = []
        for y in sorted(set(pd.DatetimeIndex(R.index).year)):
            m = pd.DatetimeIndex(R.index).year == y
            yr.append([str(y), f"{int(m.sum())}", ncq_pct(float((1 + R[m].fillna(0)).prod() - 1), 1)])
        H.append(ncq_html_table(["연도", "월수", "전략 수익"], yr, title="연도별 성과", left_cols=(0,)))

    # 이벤트·커버리지
    H.append("<h2>2. 이벤트 · 커버리지</h2>")
    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) else pd.Series(dtype=float)
    if len(ev_m):
        H.append(ncq_svg_line({"월별 이벤트 수": ev_m}, height=220,
                              title="월별 신규 커버리지 이벤트 수", pct=False))
    if ncq_has_rows(EV) and "event_type" in EV.columns:
        et = EV["event_type"].astype(str)
        sg = EV["sponsor_group"].astype(str) if "sponsor_group" in EV.columns else None
        rows = []
        for t in sorted(set(et.unique())):
            m = et == t
            row = [t, f"{int(m.sum()):,}", ncq_pct(float(m.mean()), 1, signed=False)]
            if sg is not None:
                for c in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                    row.append(f"{int((m & (sg == c)).sum()):,}")
            rows.append(row)
        hdr = ["유형", "건수", "비중"] + (["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"] if sg is not None else [])
        H.append(ncq_html_table(hdr, rows, title="이벤트 유형 × 스폰서 그룹", left_cols=(0,)))
    else:
        H.append("<p class='mut'>이벤트 분포 없음 — EV 가 비었거나 event_type 이 없습니다.</p>")

    # 코호트·기여 종목
    H.append("<h2>3. 코호트 · 기여 종목</h2>")
    COH = ncq_cohort_table(BT, SIG)
    if ncq_has_rows(COH) and "ret_h" in COH.columns:
        rows = []
        for y in sorted(set(pd.DatetimeIndex(COH["entry_month"].dropna()).year)):
            m = pd.DatetimeIndex(COH["entry_month"]).year == y
            rows.append(ncq_dist_row(str(y), COH.loc[m, "ret_h"]))
        rows.append(ncq_dist_row("전체", COH["ret_h"]))
        H.append(ncq_html_table(NCQ_DIST_HEAD, rows,
                                title=f"진입 연도별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 분포",
                                left_cols=(0,)))
        if "sponsor_group" in COH.columns:
            srows = [ncq_dist_row(g, COH.loc[COH["sponsor_group"].astype(str) == g, "ret_h"])
                     for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY")]
            H.append(ncq_html_table(NCQ_DIST_HEAD, srows, title="스폰서 그룹별 보유수익 분포",
                                    left_cols=(0,)))
    else:
        H.append("<p class='mut'>코호트 없음 — BT['cohorts'] / BT['holdings'] 로 구성할 수 없습니다.</p>")

    Hd = BT.get("holdings") if isinstance(BT, dict) else None
    if ncq_has_rows(Hd) and {"code", "ret"}.issubset(set(Hd.columns)):
        h = Hd.copy()
        h["code"] = h["code"].astype(str)
        w = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns \
            else pd.Series(1.0, index=h.index)
        contrib = (w * pd.to_numeric(h["ret"], errors="coerce")).groupby(h["code"]).sum() \
                   .sort_values(ascending=False)
        k = min(20, len(contrib))
        top = [[f"{i}", c, names.get(c, ""), ncq_pctp(float(contrib[c]), 3)]
               for i, c in enumerate(list(contrib.index[:k]), 1)]
        bot = [[f"{i}", c, names.get(c, ""), ncq_pctp(float(contrib[c]), 3)]
               for i, c in enumerate(list(contrib.index[-k:])[::-1], 1)]
        H.append(ncq_html_table(["#", "code", "종목명", "기여도"], top,
                                title=f"상위 기여 종목 {k}", left_cols=(1, 2)))
        H.append(ncq_html_table(["#", "code", "종목명", "기여도"], bot,
                                title=f"하위 기여 종목 {len(bot)}", left_cols=(1, 2)))

    # 강건성
    H.append("<h2>4. 강건성</h2>")
    rob = ncq_rpt_ctx_get(ctx, "robust") or ncq_g("NCQ_ROBUST") or {}
    rrows = []
    try:
        for rid, d in (rob.items() if hasattr(rob, "items") else []):
            # ★ pass 는 np.bool_ 로 올라올 수 있다. dict 키 조회나 `is True` 비교에 기대지 말고
            #   None(판정불가) 만 따로 걸러낸 뒤 파이썬 bool 로 좁힌다.
            p = d.get("pass")
            p = None if p is None else bool(p)
            rrows.append([("⭐ " if bool(d.get("kill")) else "") + str(rid),
                          _trunc(str(d.get("name", "")), 34),
                          ("— 판정불가" if p is None else ("✔ 통과" if p else "✘ 실패")),
                          _trunc(str(d.get("detail", "")), 160)])
    except Exception:
        rrows = []
    H.append(ncq_html_table(["ID", "검정", "판정", "상세"], rrows,
                            title="강건성 검사 (⭐ = 킬 게이트)",
                            note="실패한 검정은 그대로 표시합니다. 파라미터를 바꿔 통과시키지 않습니다.",
                            left_cols=(0, 1, 3)))

    # 해석 참조표
    H.append("<h2>5. 해석 참조표</h2>")
    info = ncq_lexicon_group_info()
    H.append(ncq_html_table(["그룹", "라벨", "방향", "가중", "어휘수", "무엇을 잡는가"],
                            [[g, d["label"], d["방향"],
                              ncq_rpt_num(d["weight"], 1) if ncq_isnum(d["weight"]) else NCQ_NA,
                              ncq_int(d["n_terms"]) if ncq_isnum(d["n_terms"]) else NCQ_NA,
                              d["뜻"]] for g, d in info.items()],
                            title="렉시콘 그룹", left_cols=(0, 1, 5)))
    H.append(ncq_html_table(["그룹", "발화했다는 것은", "발화하지 않았다는 것은"],
                            [[g, d["발화"], d["미발화"]] for g, d in info.items()],
                            title="발화 / 미발화 해석", left_cols=(0, 1, 2)))

    lex_sha = ncq_g("NCQ_LEXICON_SHA", "") or NCQ_NA
    pre_sha = ncq_g("NCQ_PREREG_SHA", "") or NCQ_NA
    H.append(ncq_html_tail(f"렉시콘 SHA <span class='mono'>{ncq_esc(lex_sha)}</span> · "
                           f"사전등록 SHA <span class='mono'>{ncq_esc(pre_sha)}</span> · "))
    atomic_write_text(path, "".join(H))
    LOG.ok(f"HTML 리포트 저장: {path}")
    return path


def write_coverage_html(outdir, ctx) -> str:
    """커버리지 완결성 전용 HTML(§6.4). 반환은 파일 경로."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, f"ncq_coverage_{_dt.datetime.now():%Y%m%d_%H%M}.html")
    REP = ncq_rpt_ctx_get(ctx, "REP")
    EV = ncq_rpt_ctx_get(ctx, "EV")
    diag = ncq_rpt_ctx_get(ctx, "diag")
    tagged, runs, derived = ncq_archive_gaps(diag)

    H: List[str] = [ncq_html_head(
        "ARC-NCQ — 리서치 커버리지 완결성 진단 (§6.4)",
        "언제부터 아카이브를 믿을 수 있는가. 이 페이지의 결론이 백테스트 유효 구간을 정한다.")]

    curves: "OrderedDict[str, pd.Series]" = OrderedDict()
    src_rows = []
    if ncq_has_rows(REP):
        dcol = ncq_pick_col(REP, ["pub_date", "event_date", "knowledge_date", "date"])
        if dcol is not None:
            R = REP.copy()
            R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
            R = R.dropna(subset=["_m"])
            tot = ncq_fill_month_gaps(R.groupby("_m", observed=True).size().astype("float64"))
            curves["전 소스 합"] = tot
            scol = ncq_pick_col(R, ["source", "src", "_src"])
            if scol is not None:
                for s in list(R[scol].astype(str).value_counts().head(5).index):
                    ss = ncq_fill_month_gaps(R[R[scol].astype(str) == s]
                                             .groupby("_m", observed=True).size().astype("float64"))
                    curves[_trunc(s, 18)] = ss
                    arr = ss.to_numpy(dtype=float)
                    src_rows.append([s, ncq_int(float(np.nansum(arr))),
                                     f"{int(np.isfinite(arr).sum())}/{len(arr)}",
                                     ncq_xlabel(ss.index[0]), ncq_xlabel(ss.index[-1])])
            if "stock_code" in R.columns:
                uq = ncq_fill_month_gaps(R.dropna(subset=["stock_code"])
                                         .groupby("_m", observed=True)["stock_code"]
                                         .nunique().astype("float64"))
                curves["유니크 커버 종목"] = uq
    if curves:
        H.append(ncq_svg_line(curves, height=320, title="월별 수집량 · 유니크 커버 종목", pct=False))
    else:
        H.append("<p class='mut'>월별 수집 시계열 없음 — REP 가 비었거나 날짜 컬럼이 없습니다.</p>")

    H.append(ncq_html_table(["소스", "총건수", "관측월", "최초월", "최종월"], src_rows,
                            title="소스별 수집량", left_cols=(0,)))

    grows = [[f"{i}", ncq_xlabel(a), ncq_xlabel(b), f"{n}"] for i, (a, b, n) in enumerate(runs, 1)]
    H.append(ncq_html_table(["#", "시작", "종료", "개월"], grows,
                            title="3개월 이상 연속 결손 구간",
                            note="이 구간의 '이벤트 없음'은 사건 부재가 아니라 관측 부재입니다. "
                                 "백테스트 유효 창에서 제외해야 합니다.", left_cols=(0,)))

    trows = []
    byyear: Dict[int, List[int]] = defaultdict(list)
    for m in tagged:
        byyear[int(pd.Timestamp(m).year)].append(int(pd.Timestamp(m).month))
    for y, ms in sorted(byyear.items()):
        trows.append([str(y), f"{len(ms)}", ", ".join(f"{x}월" for x in sorted(ms))])
    H.append(ncq_html_table(["연도", "결손 월수", "해당 월"], trows,
                            title="archive_incomplete 태깅 월", left_cols=(0, 2)))

    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) else pd.Series(dtype=float)
    if len(ev_m):
        H.append(ncq_svg_line({"월별 이벤트 수": ev_m}, height=220,
                              title="월별 신규 커버리지 이벤트 수", pct=False))

    vs = ncq_rpt_ctx_get(ctx, "valid_start")
    H.append(ncq_html_table(["출처", "유효 시작월"],
                            [["결손 구간에서 도출", ncq_xlabel(derived) if derived is not None else NCQ_NA],
                             ["파이프라인 확정값(ctx)", ncq_xlabel(as_ts(vs)) if vs is not None else NCQ_NA]],
                            title="유효 백테스트 시작월",
                            note="여러 출처가 다르면 가장 늦은 값을 씁니다.", left_cols=(0,)))
    H.append(ncq_html_tail())
    atomic_write_text(path, "".join(H))
    LOG.ok(f"커버리지 HTML 저장: {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  9. 매니페스트 · 다운로드
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_phase_times() -> "OrderedDict[str, float]":
    """Phase 별 실측 소요초. PhaseBudget._spent 가 정본, 없으면 MANIFEST 기록으로 폴백."""
    out: "OrderedDict[str, float]" = OrderedDict()
    try:
        pb = ncq_g("PhaseBudget")
        sp = dict(getattr(pb, "_spent", {}) or {})
    except Exception:
        sp = {}
    if not sp:
        sp = dict((ncq_g("MANIFEST", {}) or {}).get("phase_seconds", {}) or {})
    for k in sorted(sp):
        try:
            out[str(k)] = round(float(sp[k]), 1)
        except Exception:
            continue
    return out


def write_manifest(outdir, ctx) -> str:
    """실행 매니페스트 JSON. 재현에 필요한 것만 정확히 남기고, 모르는 값은 null 로 둔다."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, "ncq_run_manifest.json")
    man: Dict[str, Any] = {}
    try:
        man = json.loads(json.dumps(ncq_g("MANIFEST", {}) or {}, ensure_ascii=False, default=str))
    except Exception:
        man = dict(ncq_g("MANIFEST", {}) or {})

    f = ncq_headline_facts(ctx)
    man["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    man["elapsed_seconds_total"] = round(float(time.time() - ncq_g("_T0_PROCESS", time.time())), 1)
    man["degradation_applied"] = f["열화단계"]
    try:
        man["degradation_reasons"] = dict(ncq_g("_DEGRADED", {}) or {})
    except Exception:
        man["degradation_reasons"] = {}
    man["valid_window"] = {
        "start": (str(f["유효시작월"].date()) if f["유효시작월"] is not None else None),
        "end": (str(f["유효종료월"].date()) if f["유효종료월"] is not None else None),
        "months": (int(f["유효개월수"]) if ncq_isnum(f["유효개월수"]) else None),
        "years": (round(float(f["유효연수"]), 3) if ncq_isnum(f["유효연수"]) else None),
    }
    man["phase_seconds"] = dict(ncq_phase_times())
    man["phase_budget_seconds"] = dict(ncq_g("NCQ_PHASE_BUDGET_S", {}) or {})
    man["lexicon_sha"] = ncq_g("NCQ_LEXICON_SHA", "") or None
    man["prereg_sha"] = ncq_g("NCQ_PREREG_SHA", "") or None
    man["lexicon_version"] = (ncq_g("NCQ_LEXICON", {}) or {}).get("version")
    man["headline"] = {
        "total_events": (int(f["총이벤트수"]) if ncq_isnum(f["총이벤트수"]) else None),
        "events_per_month": (round(float(f["월평균이벤트"]), 3) if ncq_isnum(f["월평균이벤트"]) else None),
        "irs_share_reports": (round(float(f["IRS리포트비중"]), 4) if ncq_isnum(f["IRS리포트비중"]) else None),
        "irs_share_events": (round(float(f["IRS이벤트비중"]), 4) if ncq_isnum(f["IRS이벤트비중"]) else None),
        "ticker_map_fail_rate": (round(float(f["티커매핑실패율"]), 4) if ncq_isnum(f["티커매핑실패율"]) else None),
        "pdf_extract_fail_rate": (round(float(f["PDF추출실패율"]), 4) if ncq_isnum(f["PDF추출실패율"]) else None),
        "archive_incomplete_months": (int(f["결손태깅월수"]) if ncq_isnum(f["결손태깅월수"]) else None),
        "archive_gap_runs": [[str(pd.Timestamp(a).date()), str(pd.Timestamp(b).date()), int(n)]
                             for a, b, n in (f["결손구간"] or [])],
    }

    # 소스별 수집 건수 — ctx 우선, 없으면 REP 에서 직접 집계
    counts = ncq_rpt_ctx_get(ctx, "source_counts")
    if not isinstance(counts, dict) or not counts:
        counts = {}
        REP = ncq_rpt_ctx_get(ctx, "REP")
        scol = ncq_pick_col(REP, ["source", "src", "_src"])
        if ncq_has_rows(REP) and scol is not None:
            counts = {str(k): int(v) for k, v in REP[scol].astype(str).value_counts().items()}
    man["source_counts"] = counts
    try:
        man["source_status"] = {k: {"ok": bool(v.get("ok")), "n": int(v.get("n", -1)),
                                    "note": str(v.get("note", ""))[:200]}
                                for k, v in (ncq_g("NCQ_SOURCE_STATUS", {}) or {}).items()}
    except Exception:
        man["source_status"] = {}

    # 캐시 히트율 — 계측값이 있을 때만 기록한다(추정치를 진짜처럼 남기지 않는다)
    cs = ncq_rpt_ctx_get(ctx, "cache_stats")
    if isinstance(cs, dict) and cs:
        hit = float(cs.get("hit", np.nan))
        miss = float(cs.get("miss", np.nan))
        man["cache"] = {"hit": cs.get("hit"), "miss": cs.get("miss"),
                        "hit_rate": (round(hit / (hit + miss), 4)
                                     if ncq_isnum(hit) and ncq_isnum(miss) and (hit + miss) > 0 else None)}
    else:
        man["cache"] = {"hit": None, "miss": None, "hit_rate": None,
                        "note": "캐시 히트/미스 계측값이 ctx['cache_stats'] 로 전달되지 않았습니다."}
    try:
        man["http_stats"] = {str(k): int(v) for k, v in (ncq_g("HTTP_STATS", {}) or {}).items()}
    except Exception:
        man["http_stats"] = {}

    # 강건성 요약 (판정만 — 상세는 콘솔/HTML)
    rob = ncq_rpt_ctx_get(ctx, "robust") or ncq_g("NCQ_ROBUST") or {}
    try:
        # ★ pass 가 np.bool_ 이면 json 이 직렬화하지 못해 default=str 이 문자열 "False" 로 바꿔 버린다.
        #   "False" 는 truthy 이므로 매니페스트를 읽는 쪽의 판정이 그대로 뒤집힌다 — 진짜 bool 로 좁힌다.
        #   None(판정불가)은 null 로 남긴다. 모르는 것을 False 로 채우지 않는다.
        man["robust"] = {str(k): {"pass": (None if v.get("pass") is None else bool(v.get("pass"))),
                                  "kill": bool(v.get("kill")),
                                  "name": str(v.get("name", ""))}
                         for k, v in (rob.items() if hasattr(rob, "items") else [])}
    except Exception:
        man["robust"] = {}
    man["outputs"] = [str(p) for p in (ncq_rpt_ctx_get(ctx, "outputs") or [])]

    atomic_write_text(path, json.dumps(man, ensure_ascii=False, indent=2, default=str))
    LOG.ok(f"매니페스트 저장: {path}")
    return path


def offer_download(paths) -> None:
    """산출물 다운로드 안내. Colab → google.colab.files, 그 외 → base64 data-URI 링크.

    둘 다 안 되면 경로만 출력한다(헤드리스 실행에서 여기서 죽으면 안 된다).
    40MB 초과 파일은 브라우저 메모리를 터뜨리므로 링크 대신 경로를 안내한다.
    """
    try:
        paths = [str(p) for p in (paths or []) if p and os.path.exists(str(p))]
    except Exception:
        paths = []
    if not paths:
        LOG.info("다운로드할 산출물이 없습니다(경로가 비었거나 파일이 생성되지 않았습니다).")
        return

    rows = []
    for p in paths:
        try:
            sz = os.path.getsize(p)
        except Exception:
            sz = -1
        rows.append([_trunc(os.path.basename(p), 40),
                     f"{sz/1e6:,.2f}MB" if sz >= 0 else NCQ_NA, _trunc(p, 52)])
    LOG.table(rows, ["파일", "크기", "경로"], ["l", "r", "l"], maxw=54, title="산출물")

    env = ncq_g("ENV", {}) or {}
    if env.get("colab"):
        try:
            from google.colab import files as _f                     # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception as e:                                       # noqa
            LOG.warn(f"Colab 다운로드 실패({type(e).__name__}) — 링크 방식으로 전환합니다.")
    try:
        from IPython.display import display, HTML                    # type: ignore
        import base64
        big: List[str] = []
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                big.append(p)
                html.append(f"<div>· {ncq_esc(os.path.basename(p))} — 용량이 커서 링크 대신 경로로 "
                            f"안내합니다: <code>{ncq_esc(p)}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{ncq_esc(os.path.basename(p))}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {ncq_esc(os.path.basename(p))} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
        if big:
            LOG.warn(f"40MB 초과로 링크를 만들지 않은 파일 {len(big)}건 — 위 경로에서 직접 가져가세요.")
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")
