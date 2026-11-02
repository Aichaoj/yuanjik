# -*- coding: utf-8 -*-
"""v142：暂停即停声；3D 页加可见「停止接收」；补充入口不再串贡献"""
import json
import re

# ① HTML：立体图下方加「停止接收」
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
anchor = '<button type="button" class="btn btn-ghost btn-sm" id="btnBodyReset">⟲ 重选</button>'
if anchor not in h:
    anchor = 'id="btnBodyReset"'
old = '<div class="body-actions">'
assert old in h
if 'id="btnBodyStop"' not in h:
    h = h.replace(old, '''<div class="body-actions">''', 1)
    # 在画面下方插一个明确的停止按钮
    stage_end = h.find('id="body3dStage"')
    ins = h.find('</div>', h.find('id="bodyHint3d"'))
    if ins > 0:
        h = h[:ins] + '</div><div class="body-stop-row"><button type="button" class="btn btn-ghost" id="btnBodyStop">停止接收能量</button></div>' + h[ins + len('</div>'):]
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028k', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('stop button html:', 'id="btnBodyStop"' in h)

css = """
/* ── v142：停止接收按钮（画面下方，常显）──────────────── */
.body-stop-row { display: flex; justify-content: center; margin: 8px 0 4px; }
.body-stop-row .btn { min-width: 160px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

# ② JS：暂停/结束都停声；绑定停止按钮
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

a = a.replace("""        vs.paused = true;
        if (b) { b.textContent = '继续'; }""",
"""        vs.paused = true;
        if (b) { b.textContent = '继续'; }
        try { if (window.YJMusic && window.YJMusic.stop) { window.YJMusic.stop(); } } catch (e) {}""")

a = a.replace("""  function vsFinish(msg) {
    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }""",
"""  function vsFinish(msg) {
    try { if (window.YJMusic && window.YJMusic.stop) { window.YJMusic.stop(); } } catch (e) {}
    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }""")

if 'btnBodyStop' not in a:
    a = a.replace("  function bindBodyReceive() {", """  function bindBodyStop() {
    var b = $('btnBodyStop');
    if (b && !b.__bs) {
      b.__bs = true;
      b.addEventListener('click', function () {
        try { if (window.YJMusic && window.YJMusic.stop) { window.YJMusic.stop(); } } catch (e) {}
        vsFinish('已停止接收');
      });
    }
  }

  function bindBodyReceive() {""", 1)
    a = a.replace("    if (name === 'energy') { bindBodyMode(); bindBodyReceive(); bindSessionButtons();",
                  "    if (name === 'energy') { bindBodyMode(); bindBodyReceive(); bindBodyStop(); bindSessionButtons();")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '142';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('js: pause stops music + stop button bound')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '142'
d['notes'] = ['暂停即停止声音；3D 页新增「停止接收能量」按钮（画面下方常显）'] + [
    n for n in d['notes'] if '停止接收能量' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v150_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v151_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v150', 'v151').replace('V150', 'V151'))
p = open(r'_资料\部署载荷\_shuzi_v150.ps1', encoding='utf-8').read()
p = p.replace('V150', 'V151').replace('v150', 'v151')
p = p.replace("WEB_VER = '141'", "WEB_VER = '142'").replace('APPJS_WEBVER141', 'APPJS_WEBVER142')
p = p.replace('"web": "141"', '"web": "142"').replace('LIVE_VERSION141', 'LIVE_VERSION142')
open(r'_资料\部署载荷\_shuzi_v151.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 142 / v151 ready')
