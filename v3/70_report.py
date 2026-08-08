

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단카드 · 데이터흐름 지도                                     ║
# ║                                                                                          ║
# ║  사용자 요구: "에러 발생 시 어디서 에러가 발생했고 데이터 입출력이 어디서 이뤄지는지,       ║
# ║  애널리스트보고서와 식별된 애널리스트가 제대로 연결되었는지, 다중소스 원장연결은            ║
# ║  확실한지를 한눈에 파악할 수 있게" → 아래 세 표가 그 답이다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _fnum(x, default: float = float("nan")) -> float:
    """포맷 직전 방어. None/NaT/문자열이 f-string 숫자 포맷에 닿으면 ValueError 로 죽는데,
    하필 그 지점이 '리포트 출력'이라 백테스트를 다 돌리고 마지막에 잃는다."""
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:
        return default


def report_universe_compare(bt_main: dict, bt_alt: dict):
    """U-MID 와 대조군을 나란히 놓는다.

    ★ 왜 필요한가 — 이 전략의 성과가 '전환 탐지' 때문인지 '그냥 소형주'  때문인지는
      단독 성과표로는 절대 알 수 없다. 같은 신호·같은 비용으로 밴드만 바꿔 돌려야
      비로소 갈린다. 대조군이 더 좋으면 U-MID 밴드 가설이 기각된 것이고, 그 사실을
      숨기지 않고 그대로 적는다.
    """
    a, b = perf_stats(bt_main.get("returns")), perf_stats(bt_alt.get("returns"))
    if not a or not b:
        LOG.warn("유니버스 대조표를 만들 수 없습니다 (한쪽 수익률 시계열이 비었습니다).")
        return
    keys = ["CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
            "t통계량(HAC)", "누적수익", "평균보유종목수", "월평균회전율", "월평균비용"]
    pct = {"CAGR", "연변동성", "MDD", "승률", "누적수익", "월평균비용"}
    rows = []
    for k in keys:
        va, vb = a.get(k, np.nan), b.get(k, np.nan)
        fmt = (lambda v: f"{v:+.2%}") if k in pct else (lambda v: f"{v:,.3f}")
        try:
            d = va - vb
            ds = fmt(d) if np.isfinite(d) else "—"
        except (TypeError, ValueError):
            ds = "—"
        rows.append([k, fmt(va) if np.isfinite(va) else "—",
                     fmt(vb) if np.isfinite(vb) else "—", ds])
    ca, cb = a.get("CAGR", np.nan), b.get("CAGR", np.nan)
    if np.isfinite(ca) and np.isfinite(cb):
        if ca > cb:
            verdict = (f"U-MID 가 대조군을 CAGR {100*(ca-cb):+.2f}%p 앞섭니다 — "
                       f"밴드 가설이 이 표본에서 지지됩니다.")
        else:
            verdict = (f"❗ 대조군(스몰캡)이 U-MID 를 CAGR {100*(cb-ca):+.2f}%p 앞섭니다. "
                       f"성과의 상당 부분이 '전환 탐지'가 아니라 '소형주 노출'일 수 있습니다. "
                       f"파라미터를 바꿔 통과시키지 말고 이 결과를 그대로 보고합니다(§15).")
    else:
        verdict = "한쪽 CAGR 이 계산되지 않아 판정을 보류합니다."
    LOG.table(rows, ["지표", f"U-MID ({bt_main.get('label','main')})",
                     f"대조군 ({bt_alt.get('label','alt')})", "차이(U-MID − 대조군)"],
              ["l", "r", "r", "r"],
              title="유니버스 대조 — 같은 신호·같은 비용, 밴드만 다릅니다")
    (LOG.ok if (np.isfinite(ca) and np.isfinite(cb) and ca > cb) else LOG.warn)(verdict)


def report_performance(bt: dict, bench: Dict[str, pd.Series], title: str = "성과 검증"):
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return s
    LOG.banner(f"{title} — {bt.get('label', '')}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 리밸런싱 · 다음 거래일 시가 체결")
    fmt = {"CAGR": "{:+.2%}", "연변동성": "{:.2%}", "MDD": "{:+.2%}", "승률": "{:.1%}",
           "월평균수익": "{:+.3%}", "누적수익": "{:+.2%}", "월평균비용": "{:.4%}"}
    LOG.table([[k, (fmt.get(k, "{:,.3f}").format(v) if isinstance(v, float) and np.isfinite(v)
                    else (f"{v:,}" if isinstance(v, (int,)) else str(v)))]
               for k, v in s.items()],
              ["지표", "값"], ["l", "r"])
    if bench:
        rows = []
        R = bt["returns"].set_index("month")["ret"]
        for name, b in bench.items():
            b = b.reindex(R.index)
            n = int(b.notna().sum())
            if n < 12:
                continue
            cum = float((1 + b.fillna(0)).prod() - 1)
            cagr = (1 + cum) ** (12 / max(n, 1)) - 1
            ex = (R - b.fillna(0)).dropna()
            _, t = hac_tstat(ex.to_numpy())
            rows.append([name, f"{cagr:+.2%}", f"{cum:+.2%}",
                         f"{float(ex.mean())*12:+.2%}", f"{t:+.2f}"])
        if rows:
            LOG.table(rows, ["벤치마크", "CAGR", "누적", "연초과수익", "t(HAC)"],
                      ["l", "r", "r", "r", "r"], title="벤치마크 대비")
    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, (f"{v:+.2%}" if isinstance(v, float) and "CAGR" in k
                        else f"{v:.2f}" if isinstance(v, float) else str(v))]
                   for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 기여도 (§8.4) — 상위 소수를 빼면 성과가 사라지는가")
        try:
            base, ex5 = rt.get("원본 CAGR"), rt.get("상위5% 제외 CAGR")
            if base is not None and ex5 is not None and np.isfinite(base) and np.isfinite(ex5):
                LOG.info(f"상위 5% 종목을 빼면 CAGR 이 {base:+.2%} → {ex5:+.2%} 로 바뀝니다. "
                         + ("이 전략은 우측 꼬리에 의존합니다 — 소수 종목이 성과의 대부분을 "
                            "만듭니다. 재현성이 낮고 표본 밖에서 무너질 수 있습니다."
                            if ex5 <= 0 < base else
                            "상위 소수를 빼도 성과가 남습니다 — 꼬리 의존이 지배적이지 않습니다."))
        except Exception:
            pass
    return s


def report_interpretation(P: pd.DataFrame, bt: dict):
    """해석표 — 어떤 트레이드오프 쌍이 어떤 종목을 얼마나 골랐고, 그게 수익에 얼마나 기여했나."""
    LOG.banner("해석표", "무엇이 신호를 만들었고 무엇이 수익을 만들었는가")
    tps = [t for t, *_ in [(d[0],) for d in TP_DEFS] if t in P.columns]
    rows = []
    for tid, a, b, need, why in TP_DEFS:
        if tid not in P.columns:
            rows.append([tid, why, "-", "-", "-", "미구성(단계 또는 데이터 부족)"])
            continue
        v = col(P, tid)
        pos = float((v > 0).mean())
        rows.append([tid, why, f"{int(v.notna().sum()):,}", f"{100*pos:.1f}%",
                     f"{float(v[v > 0].mean()) if (v > 0).any() else np.nan:.3f}",
                     f"{a} × {b}"])
    LOG.table(rows, ["TP", "발화 의미", "유효관측", "양수 비율", "양수 평균", "구성 축"],
              ["c", "l", "r", "r", "r", "l"],
              title="트레이드오프 쌍 (§6.6) — 양수 비율이 곧 '제약이 풀린 종목'의 비율")

    H = bt.get("holdings")
    if H is not None and not H.empty:
        H = H.copy()
        H["contrib"] = pd.to_numeric(H["weight"], errors="coerce") * pd.to_numeric(H["ret"], errors="coerce")
        H["year"] = as_ts_series(H["month"]).dt.year
        g = H.groupby("year").agg(종목수=("code", "nunique"), 기여합=("contrib", "sum"),
                                  평균수익=("ret", "mean"), 승률=("ret", lambda s: (s > 0).mean()))
        LOG.table([[int(y), f"{r.종목수:,}", f"{r.기여합:+.3f}", f"{r.평균수익:+.2%}",
                    f"{r.승률:.0%}"] for y, r in g.iterrows()],
                  ["연도", "보유 종목수", "기여합", "평균 종목수익", "종목 승률"],
                  ["c", "r", "r", "r", "r"], title="연도별 보유 종목 성과 분해")

    if "mcap_src" in P.columns:
        m = P["mcap_src"].astype(str).value_counts()
        LOG.table([[k, f"{v:,}", f"{100*v/max(len(P),1):.1f}%"] for k, v in m.items()],
                  ["시총 소스", "행수", "비중"], ["l", "r", "r"],
                  title="유니버스 정의의 근거 (C13) — 근사 비중이 크면 밴드 편입이 흔들립니다")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 10):
    """최근 시점 상위 종목 진단 카드 — 왜 이 종목이 뽑혔는지 축 단위로 보여준다."""
    if P.empty or "Signal_rank" not in P.columns:
        return ""
    last = P["month"].max()
    sub = P[(P["month"] == last) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    if "u_mid" in sub.columns:
        sub = sub[sub["u_mid"].astype(bool)]
    if sub.empty:
        LOG.warn("최근 시점에 선정 가능한 종목이 없어 진단 카드를 만들 수 없습니다.")
        return ""
    sub = _top_n(sub, top_n, "Signal_rank")
    name = sec.drop_duplicates("code").set_index("code")["name"].astype(str).to_dict() \
        if "name" in sec.columns else {}
    lines = [f"진단 카드 — 기준월 {last:%Y-%m}  (상위 {len(sub)}종목)", "=" * 92]
    for r in sub.itertuples(index=False):
        c = getattr(r, "code")
        lines.append(f"\n[{c}] {name.get(c, '')}   Signal {getattr(r, 'Signal', float('nan')):.4f} "
                     f"(월내 백분위 {getattr(r, 'Signal_rank', float('nan')):.3f})")
        lines.append(f"  E {getattr(r, 'E', float('nan')):.3f} (축 {getattr(r, 'E_n', 0)}개) · "
                     f"U {getattr(r, 'U', float('nan')):.3f} · "
                     f"시총랭크 {getattr(r, 'mcap_rank', float('nan')):,.0f} · "
                     f"ADTV {_fnum(getattr(r, 'adv20', np.nan))/1e8:,.1f}억")
        for tid, a, b, need, why in TP_DEFS:
            v = getattr(r, tid, None)
            if v is None or not np.isfinite(v):
                continue
            lines.append(f"   · {tid} {v:6.3f}  {why}"
                         f"   [{a}={getattr(r, a, float('nan')):+.3f} / "
                         f"{b}={getattr(r, b, float('nan')):+.3f}]")
    txt = "\n".join(lines)
    _safe_print("\n" + txt)
    return txt


def report_dataflow_map():
    """데이터 흐름 지도 — 어떤 소스가 어떤 스테이지를 거쳐 어디로 갔는가."""
    if not PIPE.flow:
        return
    LOG.banner("데이터 흐름 지도",
               "소스 → 스테이지 → 산출물. PIT 열은 event/knowledge 컬럼 보유 여부다(C1 감사).")
    agg: Dict[Tuple[str, str, str], dict] = {}
    for e in PIPE.flow:
        k = (e.stage, e.kind, e.name)
        a = agg.setdefault(k, {"in": 0, "out": 0, "rows": 0, "pit": e.pit_cols, "src": e.source})
        a["in" if e.direction == "IN" else "out"] += 1
        a["rows"] = max(a["rows"], e.rows)
        if e.pit_cols and e.pit_cols != "—":
            a["pit"] = e.pit_cols
    LOG.table([[st, kd, _trunc(nm, 34), f"{v['rows']:,}" if v["rows"] >= 0 else "-",
                f"{v['in']}/{v['out']}", v["pit"] or "—", _trunc(v["src"], 28)]
               for (st, kd, nm), v in agg.items()],
              ["스테이지", "종류", "대상", "최대행수", "IN/OUT", "PIT", "소스"],
              ["l", "l", "l", "r", "c", "c", "l"], maxw=36)


def report_stage_matrix():
    """§2 단계 게이트 — 각 단계에서 무엇이 활성화되는가."""
    rows = []
    for st in STAGE_ORDER:
        tps = [t for t, a, b, need, _ in TP_DEFS if _stage_ok(need, st)]
        vs = [v for v, need, _ in VETO_DEFS if _stage_ok(need, st)]
        us = [a for a, need in U_AXES_CORE if _stage_ok(need, st)]
        rows.append([st, f"{STAGE_BUDGET_MIN.get(st, 0):.0f}분",
                     ", ".join(tps) or "-", ", ".join(vs) or "-", ", ".join(us) or "-"])
    LOG.table(rows, ["단계", "누적 예산", "활성 TP", "활성 거부권", "활성 U축"],
              ["c", "r", "l", "l", "l"],
              title="§2 단계 게이트 — M0 에서 이미 백테스트 결과가 나옵니다")


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    LOG.banner("산출물 다운로드", "아래 링크를 클릭하면 바로 저장됩니다 (미리보기 없음)")
    for p in paths:
        _safe_print(f"  · {os.path.basename(p)}  ({os.path.getsize(p)/1e6:.2f} MB)  →  {p}")
    if ENV["colab"]:
        try:
            from google.colab import files as _f                 # type: ignore
            for p in paths:
                if os.path.getsize(p) <= 200 * 1024 * 1024:
                    _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2.2'>"]
        for p in paths:
            sz = os.path.getsize(p)
            if sz > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({sz/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        pass
