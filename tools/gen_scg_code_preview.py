#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smart_consensus_gap/*.py + 오케스트레이터 + 자가검정을 읽어 브라우저에서 바로 보고
복사/다운로드할 수 있는 단일 HTML 미리보기를 만든다. tools/gen_code_preview.py(TCD v2용)와
동일한 패턴을 SCG 패키지에 맞게 옮긴 것 — 두 시스템의 미리보기 UX를 통일한다.
파일 내용을 모델 컨텍스트로 옮기지 않고 디스크에서 디스크로 직접 조립한다."""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "smart_consensus_gap")
OUT = "/tmp/claude-0/-home-user-claude-coding/bcfd6a65-63a1-5601-b3bb-7f8d11566a55/scratchpad/scg_code_preview.html"

# (id, 경로, 스테이지 태그, 한줄설명) — §24 코드 구조 / 파이프라인 순서 그대로.
FILES = [
    ("config", "smart_consensus_gap/config.py", "§25", "기본값 + 강건성 레지스트리 (사후튜닝 차단)"),
    ("contracts", "smart_consensus_gap/contracts.py", "§3", "데이터 계약 · 컬럼 별칭 · 코어싱"),
    ("util", "smart_consensus_gap/util.py", "§0-6", "로깅 · 스테이지 타이머 · 벡터화 헬퍼"),
    ("discover", "smart_consensus_gap/discover.py", "S0", "캐시 자동 탐색 · 소스 가용성 · 모드 결정"),
    ("normalize", "smart_consensus_gap/normalize.py", "S1", "애널리스트 식별 · 회계기간 · 단위"),
    ("pit_engine", "smart_consensus_gap/pit_engine.py", "S2", "거래캘린더 · 추정치 인덱스 · 시장패널"),
    ("analyst_skill", "smart_consensus_gap/analyst_skill.py", "S3", "실현 예측오차 → 시점별 skill/bias"),
    ("consensus", "smart_consensus_gap/consensus.py", "S4", "일반/스마트 컨센서스 · Smart Gap"),
    ("factors", "smart_consensus_gap/factors.py", "S5", "6/7 팩터 스냅샷 + §21 워터폴"),
    ("scoring", "smart_consensus_gap/scoring.py", "§9", "윈저·z-score/랭크 (결측 대체 금지)"),
    ("portfolio", "smart_consensus_gap/portfolio.py", "§11", "시총가중 Top-N · 회전율/비용"),
    ("backtest", "smart_consensus_gap/backtest.py", "S6", "체결·상장폐지 · 성과지표"),
    ("validation", "smart_consensus_gap/validation.py", "S8", "§20 감사 · IC/분위 · 표7 대조"),
    ("robustness", "smart_consensus_gap/robustness.py", "S7", "사전 정의 변형 · 팩터 절제"),
    ("reporting", "smart_consensus_gap/reporting.py", "§22", "산출물 · 해석 문서"),
    ("synthetic", "smart_consensus_gap/synthetic.py", "RHRSL", "합성 픽스처 (리허설 전용)"),
    ("orchestrator", "run_smart_consensus_gap.py", "MAIN", "오케스트레이터 — run() 원클릭"),
    ("selftest", "tools/scg_selftest.py", "TEST", "자가검정 20종"),
]

COMMENT_RE = re.compile(r'^([ \t]*)(#.*)$')


def _esc(s: str) -> str:
    return html.escape(s).replace("�", "&#xFFFD;")


def render_code(text: str) -> str:
    """줄 단위로 이스케이프하고, 주석 줄만 <span class="c"> 로 감싈다.
    (전체를 span 으로 감싸면 DOM 노드가 수만 개가 되어 느려진다 — 주석 줄만 감싸 가볍게 유지)"""
    out_lines = []
    for line in text.split("\n"):
        m = COMMENT_RE.match(line)
        if m:
            indent, rest = m.groups()
            out_lines.append(_esc(indent) + '<span class="c">' + _esc(rest) + "</span>")
        else:
            out_lines.append(_esc(line))
    return "\n".join(out_lines)


def main():
    panels = []
    navitems = []
    total_lines = 0
    total_kb = 0.0
    for i, (fid, relpath, tag, label) in enumerate(FILES):
        path = os.path.join(ROOT, relpath)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        n_lines = raw.count("\n") + 1
        n_kb = len(raw.encode("utf-8")) / 1024
        total_lines += n_lines
        total_kb += n_kb
        code_html = render_code(raw)
        active = " active" if i == 0 else ""
        selected = "true" if i == 0 else "false"
        hidden = "" if i == 0 else " hidden"

        navitems.append(f'''
        <button class="navitem{active}" id="tab-{fid}" role="tab"
                aria-selected="{selected}" aria-controls="panel-{fid}" tabindex="{0 if i==0 else -1}"
                data-target="{fid}">
          <span class="tag">{html.escape(tag)}</span>
          <span class="navlabel">{html.escape(os.path.basename(relpath))}</span>
          <span class="navmeta">{html.escape(label)}</span>
        </button>''')

        panels.append(f'''
        <section class="panel" id="panel-{fid}" role="tabpanel" aria-labelledby="tab-{fid}"{hidden}>
          <header class="panelhead">
            <div class="fileinfo">
              <code class="filename">{html.escape(relpath)}</code>
              <span class="filemeta">{n_lines:,}줄 · {n_kb:,.1f}KB</span>
            </div>
            <div class="actions">
              <button class="btn btn-copy" data-copy-target="src-{fid}">
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M4 2a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1v-1H4V3h6v1h1V3a1 1 0 0 0-1-1H4Zm3 3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H7Zm0 1h6v8H7V6Z"/></svg>
                <span class="btnlabel">코드 복사</span>
              </button>
              <button class="btn btn-download" data-dl-target="src-{fid}" data-dl-name="{html.escape(os.path.basename(relpath))}">
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M8 1a.5.5 0 0 1 .5.5v7.79l2.15-2.15a.5.5 0 1 1 .7.71l-3 3a.5.5 0 0 1-.7 0l-3-3a.5.5 0 1 1 .7-.71L7.5 9.29V1.5A.5.5 0 0 1 8 1ZM3 12.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5Z"/></svg>
                <span class="btnlabel">.py 다운로드</span>
              </button>
            </div>
          </header>
          <div class="codewrap"><pre class="code"><code id="src-{fid}">{code_html}</code></pre></div>
        </section>''')

    badge = f"{len(FILES)}개 파일 · {total_lines:,}줄 · {total_kb:,.0f}KB"
    doc = (HTML_TEMPLATE.replace("__NAVITEMS__", "".join(navitems))
           .replace("__PANELS__", "".join(panels))
           .replace("__BADGE__", badge))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024/1024:.2f} MB, {badge})")


HTML_TEMPLATE = r"""<title>SCG_ORIGINAL_REPRO_V1 — 소스 코드 미리보기</title>
<style>
:root{
  --bg:#eef1ee; --surface:#ffffff; --surface-2:#e6ebe6; --border:#d7ddd8;
  --text:#1b2320; --text-dim:#5c6a63; --accent:#1f7a6c; --accent-soft:#e4f0ec;
  --code-comment:#7c9089; --code-bg:#fbfdfb; --danger:#a8433a;
  --shadow: 0 1px 2px rgba(20,30,25,.06), 0 8px 24px rgba(20,30,25,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#10151a; --surface:#171f24; --surface-2:#1b242a; --border:#2a3740;
    --text:#e7ede9; --text-dim:#94a49c; --accent:#4fd1b8; --accent-soft:#16332c;
    --code-comment:#7c948c; --code-bg:#12181c; --danger:#e2837a;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --bg:#10151a; --surface:#171f24; --surface-2:#1b242a; --border:#2a3740;
  --text:#e7ede9; --text-dim:#94a49c; --accent:#4fd1b8; --accent-soft:#16332c;
  --code-comment:#7c948c; --code-bg:#12181c; --danger:#e2837a;
  --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  display:flex; flex-direction:column; min-height:100vh;
}
.topbar{
  display:flex; align-items:baseline; gap:.75rem; flex-wrap:wrap;
  padding:1.1rem 1.5rem; border-bottom:1px solid var(--border); background:var(--surface);
}
.topbar h1{ font-size:1.05rem; font-weight:700; margin:0; letter-spacing:-.01em; }
.topbar .sub{ font-size:.82rem; color:var(--text-dim); }
.topbar .badge{
  margin-left:auto; font-size:.72rem; font-weight:600; color:var(--accent);
  background:var(--accent-soft); border:1px solid var(--border); border-radius:999px;
  padding:.25rem .65rem; letter-spacing:.02em; white-space:nowrap;
}
.note{
  margin:.9rem 1.5rem 0; padding:.7rem .9rem; background:var(--surface-2);
  border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:6px;
  font-size:.82rem; line-height:1.55; color:var(--text);
}
.note code{ background:var(--surface); border:1px solid var(--border); border-radius:4px;
  padding:.05rem .35rem; font-size:.78rem; }
.note a{ color:var(--accent); font-weight:600; }
.app{ flex:1; display:flex; min-height:0; margin-top:.9rem; }
.sidebar{
  width:250px; flex:none; border-right:1px solid var(--border); padding:.4rem;
  display:flex; flex-direction:column; gap:.25rem; overflow-y:auto;
}
.navitem{
  display:flex; flex-direction:column; align-items:flex-start; gap:.15rem;
  padding:.55rem .7rem; border-radius:8px; border:1px solid transparent;
  background:transparent; color:var(--text); cursor:pointer; text-align:left;
  font-family:inherit;
}
.navitem:hover{ background:var(--surface-2); }
.navitem:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
.navitem.active{ background:var(--surface); border-color:var(--border); box-shadow:var(--shadow); }
.navitem .tag{
  font-size:.66rem; font-weight:700; color:var(--accent); letter-spacing:.03em;
  font-family:ui-monospace,Menlo,Consolas,monospace;
}
.navitem .navlabel{ font-size:.84rem; font-weight:600; font-family:ui-monospace,Menlo,Consolas,monospace; }
.navitem .navmeta{ font-size:.71rem; color:var(--text-dim); }
.main{ flex:1; min-width:0; display:flex; flex-direction:column; }
.panel{ flex:1; min-height:0; display:flex; flex-direction:column; }
.panel[hidden]{ display:none; }
.panelhead{
  display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;
  padding:.7rem 1.2rem; border-bottom:1px solid var(--border); background:var(--surface);
  position:sticky; top:0; z-index:1;
}
.fileinfo{ display:flex; align-items:baseline; gap:.6rem; min-width:0; }
.filename{
  font-family:ui-monospace,"SFMono-Regular",Menlo,Consolas,"D2Coding","Noto Sans Mono CJK KR",monospace;
  font-size:.82rem; font-weight:600; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.filemeta{ font-size:.75rem; color:var(--text-dim); font-variant-numeric:tabular-nums; white-space:nowrap; }
.actions{ display:flex; gap:.5rem; }
.btn{
  display:inline-flex; align-items:center; gap:.4rem; font-size:.78rem; font-weight:600;
  padding:.4rem .7rem; border-radius:7px; border:1px solid var(--border); background:var(--surface);
  color:var(--text); cursor:pointer; font-family:inherit;
}
.btn:hover{ background:var(--surface-2); }
.btn:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
.btn-copy{ border-color:var(--accent); color:var(--accent); }
.btn-copy.copied{ background:var(--accent-soft); }
.codewrap{ flex:1; min-height:0; overflow:auto; background:var(--code-bg); }
.code{
  margin:0; padding:1rem 1.2rem 3rem; font-size:.78rem; line-height:1.6; white-space:pre;
  font-family:ui-monospace,"SFMono-Regular",Menlo,Consolas,"D2Coding","Noto Sans Mono CJK KR",monospace;
  tab-size:4;
}
.code .c{ color:var(--code-comment); }
@media (max-width:760px){
  .app{ flex-direction:column; }
  .sidebar{ width:100%; flex-direction:row; overflow-x:auto; border-right:none; border-bottom:1px solid var(--border); }
  .navitem{ flex:none; min-width:170px; }
}
@media (prefers-reduced-motion: reduce){ *{ transition:none !important; } }
</style>
<div class="topbar">
  <h1>SCG_ORIGINAL_REPRO_V1 — 소스 코드 미리보기</h1>
  <span class="sub">스마트 컨센서스 갭 / IBK 서프라이즈 포트폴리오 재현 — 전체 소스 원문</span>
  <span class="badge">__BADGE__</span>
</div>
<div class="note">
  왼쪽에서 파일을 고른 뒤 <strong>코드 복사</strong>로 클립보드에 담거나 <strong>.py 다운로드</strong>로
  개별 파일을 받으세요. 전체 실행은 <code>from run_smart_consensus_gap import run; run()</code> 한 줄이면
  됩니다. PR: <a href="https://github.com/limsh87/claude-coding/pull/24" target="_blank" rel="noopener">#24</a>
</div>
<div class="app">
  <nav class="sidebar" role="tablist" aria-label="소스 파일 목록">__NAVITEMS__
  </nav>
  <main class="main">__PANELS__
  </main>
</div>
<script>
(function(){
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.navitem'));
  function activate(id, moveFocus){
    tabs.forEach(function(t){
      var on = t.dataset.target === id;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (on && moveFocus) t.focus();
    });
    document.querySelectorAll('.panel').forEach(function(p){
      p.hidden = (p.id !== 'panel-' + id);
    });
  }
  tabs.forEach(function(t, i){
    t.addEventListener('click', function(){ activate(t.dataset.target, false); });
    t.addEventListener('keydown', function(e){
      var idx = i;
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') idx = (i + 1) % tabs.length;
      else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') idx = (i - 1 + tabs.length) % tabs.length;
      else return;
      e.preventDefault();
      activate(tabs[idx].dataset.target, true);
    });
  });

  function rawText(el){ return el.textContent; }

  document.querySelectorAll('.btn-copy').forEach(function(btn){
    btn.addEventListener('click', function(){
      var src = document.getElementById(btn.dataset.copyTarget);
      var text = rawText(src);
      var done = function(){
        var label = btn.querySelector('.btnlabel');
        var prev = label.textContent;
        btn.classList.add('copied'); label.textContent = '복사됨 ✓';
        setTimeout(function(){ btn.classList.remove('copied'); label.textContent = prev; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done, function(){ fallbackCopy(text, done); });
      } else {
        fallbackCopy(text, done);
      }
    });
  });
  function fallbackCopy(text, done){
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch(e){}
    document.body.removeChild(ta); done();
  }

  document.querySelectorAll('.btn-download').forEach(function(btn){
    btn.addEventListener('click', function(){
      var src = document.getElementById(btn.dataset.dlTarget);
      var blob = new Blob([rawText(src)], {type:'text/x-python;charset=utf-8'});
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = btn.dataset.dlName;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(function(){ URL.revokeObjectURL(url); }, 2000);
    });
  });
})();
</script>
"""

if __name__ == "__main__":
    main()
