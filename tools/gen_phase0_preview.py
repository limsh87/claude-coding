#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""phase0/phase0_3axis_v12.py 를 브라우저에서 바로 읽고 복사·다운로드할 수 있는
단일 HTML 미리보기로 조립한다. 소스를 모델 컨텍스트로 옮기지 않고 디스크에서 디스크로 옮긴다.

판정 요약은 reports/phase0_verdict_v12.json 에서 읽는다 — 페이지가 실제 실행 결과와
어긋나지 않게 하기 위해서다. 손으로 적지 않는다.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "phase0" / "phase0_3axis_v12.py"
VERDICT = ROOT / "phase0" / "reports" / "phase0_verdict_v12.json"
OUT = Path("/tmp/claude-0/-home-user-claude-coding/"
           "2c5d2795-7b92-5d2a-be31-9f93d8d0b210/scratchpad/phase0_v12_preview.html")

COMMENT_RE = re.compile(r'^([ \t]*)(#.*)$')
BANNER_TOP = "▼▼▼  인 증 정 보"
BANNER_END = "▲▲▲  여기까지가 입력란"


def esc(s: str) -> str:
    # 소스에 U+FFFD 가 리터럴로 있으면 배포 파이프라인이 "잘못 디코딩된 것" 으로 보고 거부한다.
    return html.escape(s).replace("�", "&#xFFFD;")


def render_code(text: str) -> str:
    """주석 줄만 span 으로 감싼다. 토큰마다 감싸면 DOM 노드가 수만 개가 되어 느려진다."""
    out = []
    for line in text.split("\n"):
        m = COMMENT_RE.match(line)
        if m:
            indent, rest = m.groups()
            out.append(esc(indent) + '<span class="c">' + esc(rest) + "</span>")
        elif line.lstrip().startswith('"""') or line.lstrip().startswith("'''"):
            out.append('<span class="s">' + esc(line) + "</span>")
        else:
            out.append(esc(line))
    return "\n".join(out)


def extract_key_block(text: str) -> str:
    lines = text.split("\n")
    start = end = None
    for i, ln in enumerate(lines):
        if BANNER_TOP in ln and start is None:
            start = i
        if BANNER_END in ln:
            end = i + 2
            break
    if start is None or end is None:
        raise SystemExit("인증정보 입력란 배너를 찾지 못했다 — 소스가 바뀌었는지 확인할 것")
    return "\n".join(lines[start:end])


def verdict_rows() -> list[dict]:
    if not VERDICT.exists():
        return []
    data = json.loads(VERDICT.read_text(encoding="utf-8"))
    rows = []
    for v in data.get("verdicts", []):
        rows.append({
            "axis": v["axis"], "as_of": v["as_of"], "status": v["status"],
            "cause": v.get("blocked_cause_class") or "",
            "n_blockers": len(v.get("extra", {}).get("preflight_blockers", []) or []),
        })
    return rows


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    n_lines = src.count("\n") + 1
    key_block = extract_key_block(src)
    rows = verdict_rows()

    status_tone = {
        "BLOCKED_PREREQ": "alarm", "STOP": "alarm",
        "UNVERIFIED": "warn", "PENDING_MANUAL": "warn", "GO": "ok",
    }
    chip_parts = []
    for r in rows:
        tone = status_tone.get(r["status"], "warn")
        cause = esc(r["cause"]) or "&mdash;"
        if r["n_blockers"]:
            cause += " · 차단 {}건".format(r["n_blockers"])
        chip_parts.append(
            '<div class="chip tone-{tone}">'
            '<span class="chip-axis">축 {axis}</span>'
            '<span class="chip-date">{date}</span>'
            '<span class="chip-status">{status}</span>'
            '<span class="chip-cause">{cause}</span>'
            "</div>".format(
                tone=tone, axis=esc(r["axis"]), date=esc(r["as_of"]),
                status=esc(r["status"]), cause=cause,
            )
        )
    chips = "\n".join(chip_parts)

    gutter = "\n".join(str(i) for i in range(1, n_lines + 1))

    doc = f"""<title>PHASE 0 v1.2 — 3축 수집 가능성 검증 실행체</title>
<style>
:root {{
  --ground:#F1F3F2; --surface:#FFFFFF; --surface-2:#E9EDEB;
  --ink:#14181A; --ink-soft:#5A6462; --ink-faint:#8A9491;
  --rule:#D3DAD8; --accent:#1F4E4A; --accent-soft:#DCE8E5;
  --alarm:#A6432E; --alarm-soft:#F3E2DD;
  --warn:#8A6A1F; --warn-soft:#F2EAD6;
  --ok:#2F6B3F; --ok-soft:#DEEBE1;
  --code-bg:#FAFBFA; --code-comment:#6E7C78; --code-string:#1F4E4A;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#101413; --surface:#171C1B; --surface-2:#1E2523;
    --ink:#E6EAE8; --ink-soft:#9AA5A2; --ink-faint:#6C7876;
    --rule:#2A3230; --accent:#6FBFB4; --accent-soft:#1A2E2C;
    --alarm:#E08A72; --alarm-soft:#301F1A;
    --warn:#D4B061; --warn-soft:#2C2617;
    --ok:#7FC08F; --ok-soft:#18271C;
    --code-bg:#121716; --code-comment:#7E8C88; --code-string:#8FCFC4;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#101413; --surface:#171C1B; --surface-2:#1E2523;
  --ink:#E6EAE8; --ink-soft:#9AA5A2; --ink-faint:#6C7876;
  --rule:#2A3230; --accent:#6FBFB4; --accent-soft:#1A2E2C;
  --alarm:#E08A72; --alarm-soft:#301F1A;
  --warn:#D4B061; --warn-soft:#2C2617;
  --ok:#7FC08F; --ok-soft:#18271C;
  --code-bg:#121716; --code-comment:#7E8C88; --code-string:#8FCFC4;
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",
              "Noto Sans KR","Segoe UI",sans-serif;
  font-size:16px; line-height:1.65; -webkit-font-smoothing:antialiased;
}}
.mono {{ font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:0 24px 96px; }}

/* ── 액션 바 ─────────────────────────────────────────────── */
.bar {{
  position:sticky; top:0; z-index:20; background:var(--ground);
  border-bottom:1px solid var(--rule);
}}
.bar-in {{
  max-width:1080px; margin:0 auto; padding:12px 24px;
  display:flex; gap:12px; align-items:center; flex-wrap:wrap;
}}
.bar-title {{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--ink-faint); margin-right:auto;
}}
button {{
  font:inherit; font-size:14px; font-weight:600; cursor:pointer;
  padding:8px 16px; border-radius:2px; border:1px solid var(--rule);
  background:var(--surface); color:var(--ink); transition:background .12s,border-color .12s;
}}
button:hover {{ border-color:var(--accent); }}
button.primary {{ background:var(--accent); border-color:var(--accent); color:var(--ground); }}
button.primary:hover {{ opacity:.88; }}
button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}

/* ── 헤더 ────────────────────────────────────────────────── */
header {{ padding:56px 0 32px; border-bottom:1px solid var(--rule); }}
.eyebrow {{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:11px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--accent); margin:0 0 14px;
}}
h1 {{ font-size:clamp(28px,4.4vw,42px); line-height:1.18; letter-spacing:-.02em;
     margin:0 0 16px; text-wrap:balance; font-weight:700; }}
.lede {{ font-size:18px; color:var(--ink-soft); max-width:62ch; margin:0; }}

h2 {{ font-size:22px; letter-spacing:-.01em; margin:56px 0 8px; font-weight:700; }}
h2 + .sub {{ color:var(--ink-soft); margin:0 0 20px; max-width:64ch; font-size:15px; }}
p {{ max-width:66ch; }}

/* ── 판정 칩 ─────────────────────────────────────────────── */
.chips {{ display:grid; gap:8px; margin:24px 0 0;
          grid-template-columns:repeat(auto-fill,minmax(248px,1fr)); }}
.chip {{
  display:grid; grid-template-columns:auto auto; gap:2px 10px;
  padding:12px 14px; background:var(--surface); border:1px solid var(--rule);
  border-left-width:3px; border-radius:2px;
}}
.chip-axis {{ font-weight:700; font-size:15px; }}
.chip-date {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px;
             color:var(--ink-faint); text-align:right; font-variant-numeric:tabular-nums; }}
.chip-status {{ grid-column:1/-1; font-family:ui-monospace,Menlo,Consolas,monospace;
               font-size:12px; font-weight:700; letter-spacing:.06em; }}
.chip-cause {{ grid-column:1/-1; font-size:12px; color:var(--ink-soft); }}
.tone-alarm {{ border-left-color:var(--alarm); }} .tone-alarm .chip-status {{ color:var(--alarm); }}
.tone-warn  {{ border-left-color:var(--warn);  }} .tone-warn  .chip-status {{ color:var(--warn); }}
.tone-ok    {{ border-left-color:var(--ok);    }} .tone-ok    .chip-status {{ color:var(--ok); }}

/* ── 안내 박스 ───────────────────────────────────────────── */
.note {{
  border-left:3px solid var(--accent); background:var(--accent-soft);
  padding:16px 18px; margin:24px 0; border-radius:0 2px 2px 0;
}}
.note.alarm {{ border-left-color:var(--alarm); background:var(--alarm-soft); }}
.note p {{ margin:0; }} .note p + p {{ margin-top:8px; }}
.note strong {{ font-weight:700; }}

/* ── 키 입력란 카드 ──────────────────────────────────────── */
.keycard {{ background:var(--surface); border:1px solid var(--rule); border-radius:2px;
           overflow:hidden; margin:24px 0; }}
.keycard-head {{ display:flex; align-items:center; gap:12px; padding:12px 16px;
                border-bottom:1px solid var(--rule); background:var(--surface-2); }}
.keycard-head .label {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11px;
                       letter-spacing:.12em; text-transform:uppercase; color:var(--ink-faint);
                       margin-right:auto; }}
.keycard pre {{ margin:0; padding:16px; overflow-x:auto; background:var(--code-bg);
               font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
               font-size:12.5px; line-height:1.7; }}

/* ── 키 표 ───────────────────────────────────────────────── */
.tablewrap {{ overflow-x:auto; margin:20px 0; }}
table {{ border-collapse:collapse; width:100%; min-width:560px; font-size:14px; }}
th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--rule);
         vertical-align:top; }}
th {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11px;
     letter-spacing:.1em; text-transform:uppercase; color:var(--ink-faint);
     border-bottom-color:var(--ink-faint); }}
td code {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px;
          background:var(--surface-2); padding:2px 6px; border-radius:2px; }}

/* ── 코드 패널 ───────────────────────────────────────────── */
.panel {{ border:1px solid var(--rule); border-radius:2px; overflow:hidden;
         background:var(--code-bg); margin:24px 0; }}
.panel-head {{ display:flex; align-items:center; gap:12px; padding:10px 16px;
              background:var(--surface-2); border-bottom:1px solid var(--rule);
              font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; }}
.panel-head .file {{ font-weight:700; }}
.panel-head .meta {{ color:var(--ink-faint); margin-right:auto;
                    font-variant-numeric:tabular-nums; }}
.code-scroll {{ display:flex; overflow:auto; max-height:72vh; }}
.code-scroll.full {{ max-height:none; }}
.code-scroll pre {{ margin:0; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
                   font-size:12.5px; line-height:1.62; }}
.gutter {{ position:sticky; left:0; z-index:1; padding:16px 12px 16px 16px;
          text-align:right; color:var(--ink-faint); background:var(--code-bg);
          border-right:1px solid var(--rule); user-select:none;
          font-variant-numeric:tabular-nums; }}
.src {{ padding:16px 20px; flex:1; }}
.src .c {{ color:var(--code-comment); font-style:italic; }}
.src .s {{ color:var(--code-string); }}
#payload {{ display:none; }}

footer {{ margin-top:64px; padding-top:24px; border-top:1px solid var(--rule);
         color:var(--ink-faint); font-size:13px; }}
.toast {{ position:fixed; bottom:24px; left:50%; transform:translateX(-50%) translateY(16px);
         background:var(--ink); color:var(--ground); padding:10px 20px; border-radius:2px;
         font-size:14px; font-weight:600; opacity:0; pointer-events:none;
         transition:opacity .18s, transform .18s; z-index:50; }}
.toast.on {{ opacity:1; transform:translateX(-50%) translateY(0); }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="bar"><div class="bar-in">
  <span class="bar-title">phase0_3axis_v12.py · {n_lines:,}줄</span>
  <button class="primary" onclick="copyAll()">전체 코드 복사</button>
  <button onclick="download()">.py 다운로드</button>
</div></div>

<div class="wrap">
<header>
  <p class="eyebrow">Phase 0 · v1.2 · LIVE 전용</p>
  <h1>대체데이터 3축 수집 가능성 검증 실행체</h1>
  <p class="lede">겸직 그래프(A)·분기별 엣지 변화(A-Δ)·특허(B)·국민연금 사업장(C)의
  <strong>수집 가능성만</strong> 측정한다. 팩터·시그널·수익률 연산은 코드에 존재하지 않는다.
  단일 코드 셀이므로 Colab 한 셀에 붙여넣으면 그대로 돈다.</p>
</header>

<h2>1. 키를 넣는 자리</h2>
<p class="sub">파일 맨 위에 입력란이 있다. 네 칸을 채우고 실행하면 된다.
비워두면 같은 이름의 환경변수에서 읽는다.</p>

<div class="keycard">
  <div class="keycard-head">
    <span class="label">phase0_3axis_v12.py · 인증정보 입력란</span>
    <button onclick="copyKeys()">이 블록만 복사</button>
  </div>
  <pre class="mono">{esc(key_block)}</pre>
</div>

<div class="tablewrap"><table>
<thead><tr><th>칸</th><th>넣을 값</th><th>발급</th></tr></thead>
<tbody>
<tr><td><code>DART_API_KEY</code></td>
    <td>OpenDART 인증키 40자</td>
    <td>opendart.fss.or.kr → 인증키 신청/관리 (이메일 인증 즉시, 무료)</td></tr>
<tr><td><code>GCP_SA_KEY_PATH</code></td>
    <td>서비스계정 JSON 키 <strong>파일의 절대경로</strong><br>
        예) <code>/content/sa-key.json</code></td>
    <td>console.cloud.google.com → 서비스 계정 → 키 → JSON<br>
        역할: BigQuery User + BigQuery Job User</td></tr>
<tr><td><code>GCP_PROJECT_ID</code></td>
    <td><strong>프로젝트 ID 문자열</strong><br>
        예) <code>compelling-muse-311107</code></td>
    <td>같은 콘솔의 프로젝트 선택기에서 확인</td></tr>
<tr><td><code>DATA_GO_KR_KEY</code></td>
    <td>공공데이터포털 <strong>Decoding</strong> 키<br>
        (코드가 인코딩하므로 Encoding 키를 넣지 말 것)</td>
    <td>data.go.kr → 국민연금 가입 사업장 내역 → 활용신청<br>
        마이페이지에서 <strong>'승인'</strong> 상태 확인 필수</td></tr>
</tbody></table></div>

<div class="note alarm">
<p><strong>v1.1이 죽은 지점.</strong> 위 두 GCP 칸은 역할이 다르다. 프로젝트 ID를
경로 자리에 넣으면 축 B가 통째로 죽는다. 코드가 이 오설정을 감지하면
<code>AUTH_PATH</code>로 분류하고 "이 값은 프로젝트 ID처럼 보인다"고 짚어준다.</p>
<p>키는 로그·판정표 어디에도 남지 않는다. 실행 시작 시 앞 4자와 길이만 마스킹해 찍는다.</p>
</div>

<h2>2. 이 컨테이너에서의 실행 결과</h2>
<p class="sub">아래는 이 저장소 CI 컨테이너에서 LIVE 모드로 실제 실행한 판정이다.
게이트 측정값은 하나도 없다 — 조직 이그레스 정책이 한국 데이터 소스로의 CONNECT를 403으로 거부한다.</p>

<div class="chips">{chips}</div>

<div class="note">
<p><code>BLOCKED_PREREQ</code>는 <strong>측정 자체를 못 했다</strong>는 뜻이며
<code>STOP</code>(측정은 됐고 결과가 임계 미달)과 다르다. 이 둘을 섞지 않는 것이 이 단계의 핵심이다.</p>
<p>차단된 호스트는 <code>opendart.fss.or.kr</code>, <code>data.krx.co.kr</code>,
<code>apis.data.go.kr</code>. <code>bigquery.googleapis.com</code>은 열려 있으므로
<strong>축 B는 GCP 서비스계정 키만 있으면 이 환경에서도 실측 가능하다.</strong></p>
</div>

<h2>3. 전체 소스</h2>
<p class="sub">아래 전체를 복사해 Colab 한 셀에 붙여넣거나, <code>.py</code>로 받아
<code>python3 phase0_3axis_v12.py</code>로 실행한다.
의존성은 <code>pip install requests pandas numpy pykrx google-cloud-bigquery</code>.</p>

<div class="panel">
  <div class="panel-head">
    <span class="file">phase0_3axis_v12.py</span>
    <span class="meta">{n_lines:,}줄 · {len(src) / 1024:.0f} KB</span>
    <button onclick="toggleFull(this)">전체 높이로 펼치기</button>
    <button onclick="copyAll()">복사</button>
  </div>
  <div class="code-scroll" id="scroll">
    <pre class="gutter" aria-hidden="true">{gutter}</pre>
    <pre class="src"><code>{render_code(src)}</code></pre>
  </div>
</div>

<footer>
  로직 테스트 163건 통과 (<code>phase0/tests/test_logic_v12.py</code>) — 순수 함수만 검증하며
  측정값을 만들지 않는다. 호출 예산 중단선 15,200콜, 80% 도달 시 판정표를 저장하고
  <code>resume_todo.json</code>으로 이어받는다. 이틀에 나눠 도는 것이 정상 경로다.
</footer>
</div>

<pre id="payload">{esc(src)}</pre>
<div class="toast" id="toast"></div>

<script>
const payload = () => document.getElementById('payload').textContent;

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('on');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('on'), 1900);
}}

function put(text, label) {{
  const done = () => toast(label + ' 복사됨');
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(text).then(done).catch(() => legacy(text, done));
  }} else {{ legacy(text, done); }}
}}
function legacy(text, done) {{
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select();
  try {{ document.execCommand('copy'); done(); }}
  catch (e) {{ toast('복사 실패 — .py 다운로드를 이용하세요'); }}
  document.body.removeChild(ta);
}}

function copyAll() {{ put(payload(), '전체 코드'); }}
function copyKeys() {{
  const pre = document.querySelector('.keycard pre');
  put(pre.textContent, '인증정보 입력란');
}}
function download() {{
  const blob = new Blob([payload()], {{ type: 'text/x-python;charset=utf-8' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'phase0_3axis_v12.py';
  document.body.appendChild(a); a.click();
  setTimeout(() => {{ URL.revokeObjectURL(a.href); a.remove(); }}, 1000);
  toast('다운로드 시작');
}}
function toggleFull(btn) {{
  const s = document.getElementById('scroll');
  const full = s.classList.toggle('full');
  btn.textContent = full ? '높이 접기' : '전체 높이로 펼치기';
}}
</script>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"{OUT}  ({len(doc) / 1024:.0f} KB, 소스 {n_lines:,}줄)")


if __name__ == "__main__":
    main()
