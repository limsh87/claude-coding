#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategies/*.py 를 읽어 브라우저에서 바로 보고 복사할 수 있는 단일 HTML 미리보기를 만든다.
파일 내용을 모델 컨텍스트로 옮기지 않고 디스크에서 디스크로 직접 조립한다."""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "strategies")
OUT = "/tmp/claude-0/-home-user-claude-coding/8a6c52fc-3c9c-54eb-b7c5-72a1e1d8c86c/scratchpad/tcd_v2_code_preview.html"

FILES = [
    ("pack_c", "tcd_v2_01_pack_c_capital.py", "PACK-C", "자본배분 체제 전환"),
    ("pack_n", "tcd_v2_02_pack_n_employment.py", "PACK-N", "국민연금 고용"),
    ("pack_d", "tcd_v2_03_pack_d_text.py", "PACK-D", "공시텍스트 경직성"),
    ("pack_x", "tcd_v2_04_pack_x_customs.py", "PACK-X", "관세청 수출"),
    ("pack_p", "tcd_v2_05_pack_p_procurement.py", "PACK-P", "조달청 낙찰"),
    ("integrated", "tcd_v2_00_integrated_all_packs.py", "통합", "전 센서팩 + 공용축"),
]

COMMENT_RE = re.compile(r'^([ \t]*)(#.*)$')


def _esc(s: str) -> str:
    # 소스 안에 리터럴로 존재하는 U+FFFD(REPLACEMENT CHARACTER, "잘못된 디코딩" 감지용 문자열
    # 리터럴로 실제 코드에 등장한다)를 raw 코드포인트로 그대로 두면 아티팩트 배포 파이프라인이
    # "잘못 디코딩된 것 아니냐"며 거부한다. 브라우저에는 동일하게 보이는 숫자 엔티티로 치환한다.
    return html.escape(s).replace("�", "&#xFFFD;")


def render_code(text: str) -> str:
    """줄 단위로 이스케이프하고, 주석 줄만 <span class="c"> 로 감싼다.
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
    for i, (fid, fname, tag, label) in enumerate(FILES):
        path = os.path.join(SRC, fname)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        n_lines = raw.count("\n") + 1
        n_kb = len(raw.encode("utf-8")) / 1024
        code_html = render_code(raw)
        active = " active" if i == 0 else ""
        selected = "true" if i == 0 else "false"
        hidden = "" if i == 0 else " hidden"

        navitems.append(f'''
        <button class="navitem{active}" id="tab-{fid}" role="tab"
                aria-selected="{selected}" aria-controls="panel-{fid}" tabindex="{0 if i==0 else -1}"
                data-target="{fid}">
          <span class="tag">{tag}</span>
          <span class="navlabel">{html.escape(label)}</span>
          <span class="navmeta">{n_lines:,}줄 · {n_kb:,.0f}KB</span>
        </button>''')

        panels.append(f'''
        <section class="panel" id="panel-{fid}" role="tabpanel" aria-labelledby="tab-{fid}"{hidden}>
          <header class="panelhead">
            <div class="fileinfo">
              <code class="filename">{html.escape(fname)}</code>
              <span class="filemeta">{n_lines:,}줄 · {n_kb:,.1f}KB</span>
            </div>
            <div class="actions">
              <button class="btn btn-copy" data-copy-target="src-{fid}">
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M4 2a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1v-1H4V3h6v1h1V3a1 1 0 0 0-1-1H4Zm3 3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H7Zm0 1h6v8H7V6Z"/></svg>
                <span class="btnlabel">코드 복사</span>
              </button>
              <button class="btn btn-download" data-dl-target="src-{fid}" data-dl-name="{html.escape(fname)}">
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M8 1a.5.5 0 0 1 .5.5v7.79l2.15-2.15a.5.5 0 1 1 .7.71l-3 3a.5.5 0 0 1-.7 0l-3-3a.5.5 0 1 1 .7-.71L7.5 9.29V1.5A.5.5 0 0 1 8 1ZM3 12.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5Z"/></svg>
                <span class="btnlabel">.py 다운로드</span>
              </button>
            </div>
          </header>
          <div class="codewrap"><pre class="code"><code id="src-{fid}">{code_html}</code></pre></div>
        </section>''')

    doc = HTML_TEMPLATE.replace("__NAVITEMS__", "".join(navitems)).replace("__PANELS__", "".join(panels))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024/1024:.2f} MB)")


HTML_TEMPLATE = r"""<title>TCD v2 — 전략 코드 미리보기</title>
<style>
:root{
  --bg:#f7f4ee; --surface:#ffffff; --surface-2:#efe9dc; --border:#ddd5c2;
  --text:#211d15; --text-dim:#6b6152; --accent:#a9781f; --accent-soft:#f1e3c2;
  --code-comment:#8a7a5c; --code-bg:#fffdf8; --danger:#a3401f;
  --shadow: 0 1px 2px rgba(30,25,10,.06), 0 8px 24px rgba(30,25,10,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#14120d; --surface:#1c1911; --surface-2:#221f16; --border:#322c1e;
    --text:#f0ead9; --text-dim:#a89b7d; --accent:#d9a94a; --accent-soft:#3a2e15;
    --code-comment:#9c8f6c; --code-bg:#171410; --danger:#e07a55;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --bg:#14120d; --surface:#1c1911; --surface-2:#221f16; --border:#322c1e;
  --text:#f0ead9; --text-dim:#a89b7d; --accent:#d9a94a; --accent-soft:#3a2e15;
  --code-comment:#9c8f6c; --code-bg:#171410; --danger:#e07a55;
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
.app{ flex:1; display:flex; min-height:0; margin-top:.9rem; }
.sidebar{
  width:230px; flex:none; border-right:1px solid var(--border); padding:.4rem;
  display:flex; flex-direction:column; gap:.25rem; overflow-y:auto;
}
.navitem{
  display:flex; flex-direction:column; align-items:flex-start; gap:.15rem;
  padding:.6rem .7rem; border-radius:8px; border:1px solid transparent;
  background:transparent; color:var(--text); cursor:pointer; text-align:left;
  font-family:inherit;
}
.navitem:hover{ background:var(--surface-2); }
.navitem:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
.navitem.active{ background:var(--surface); border-color:var(--border); box-shadow:var(--shadow); }
.navitem .tag{
  font-size:.68rem; font-weight:700; color:var(--accent); letter-spacing:.03em;
}
.navitem.active .tag{ }
.navitem .navlabel{ font-size:.86rem; font-weight:600; }
.navitem .navmeta{ font-size:.72rem; color:var(--text-dim); font-variant-numeric:tabular-nums; }
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
  .navitem{ flex:none; min-width:150px; }
}
@media (prefers-reduced-motion: reduce){ *{ transition:none !important; } }
</style>
<div class="topbar">
  <h1>TCD v2 — 전략별 실행 파일 미리보기</h1>
  <span class="sub">각 파일 하나로 백테스트 · 성과검증 · 강건성(R1~R11) · 해석표까지 완결됩니다</span>
  <span class="badge">6개 파일</span>
</div>
<div class="note">
  왼쪽에서 파일을 고른 뒤 <strong>코드 복사</strong>로 클립보드에 담아 Jupyter/Colab 셀에 그대로 붙여넣으세요.
  처음에는 코드 상단의 <code>RUN_MODE = "FULL"</code> 을 <code>RUN_MODE = "SMOKE"</code> 로 바꿔 먼저 돌려보시길 권합니다 —
  키나 네트워크 없이 합성데이터로 전체 출력물을 30초 안에 예행연습합니다.
</div>
<div class="app">
  <nav class="sidebar" role="tablist" aria-label="전략 파일 목록">__NAVITEMS__
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
