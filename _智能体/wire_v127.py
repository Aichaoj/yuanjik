# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 3D 页加模式切换（补充能量 / 减缓疼痛）
anchor = '<div class="body-actions">'
assert anchor in h
h = h.replace(anchor, '''<div class="vc-row" id="bodyModeRow" style="justify-content:center;margin:6px 0">
          <button type="button" class="vc-link" data-bmode="energy" id="bmEnergy">补充能量</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" data-bmode="comfort" id="bmComfort">减缓疼痛</button>
        </div>
''' + anchor, 1)
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028g', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('mode row added')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 补充能量入口 → 3D 页（补充模式）
a = a.replace("on('btnGoUse', function () { showView('use'); });",
              "on('btnGoUse', function () { window.__bodyMode = 'energy'; showView('energy'); });")
a = a.replace("on('btnGoComfort', function () { showView('energy'); });",
              "on('btnGoComfort', function () { window.__bodyMode = 'comfort'; showView('energy'); });")

# 3D 页模式切换 + 接收能量按模式启动
if 'function bindBodyMode' not in a:
    a = a.replace("  function bindBodyReceive() {", """  function bindBodyMode() {
    function set(m) {
      window.__bodyMode = m;
      ['bmEnergy', 'bmComfort'].forEach(function (id) {
        var el = $(id);
        if (el) { el.classList.toggle('is-on', (m === 'comfort') === (id === 'bmComfort')); }
      });
      if ($('vsDisclaim')) { $('vsDisclaim').hidden = (m !== 'comfort'); }
    }
    var e = $('bmEnergy');
    if (e && !e.__bm) { e.__bm = true; e.addEventListener('click', function () { set('energy'); }); }
    var c = $('bmComfort');
    if (c && !c.__bm) { c.__bm = true; c.addEventListener('click', function () { set('comfort'); }); }
    if (!window.__bodyMode) { set('comfort'); }
  }

  function bindBodyReceive() {""", 1)

# 接收能量：按模式决定 purpose；补齐暂停
a = a.replace("""      var picked = (window.YJEnergy && window.YJEnergy.picked) ? window.YJEnergy.picked() : [];
      if (!picked || !picked.length) {
        toast('先在人体上点选不适的位置', 'ok');
        return;
      }""",
"""      var mode = window.__bodyMode || 'comfort';
      var picked = (window.YJEnergy && window.YJEnergy.picked) ? window.YJEnergy.picked() : [];
      if (mode === 'comfort' && (!picked || !picked.length)) {
        toast('先点选不适的位置', 'ok');
        return;
      }""")
a = a.replace("""      vs.purpose = 'comfort';
      vs.spot = spot;""",
"""      vs.purpose = mode;
      vs.spot = spot;""")

# 3D 视图挂载时绑定模式与按钮
a = a.replace("    if (name === 'energy') {", "    if (name === 'energy') { bindBodyMode(); bindSessionButtons();")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '127';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('js ok')

css = """
#bodyModeRow .vc-link.is-on { font-weight: 700; text-decoration: none;
  background: var(--brand-1); color: #fff; border-radius: 14px; padding: 6px 14px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '127'
d['notes'] = ['补充能量改为 3D 人体同页（可在补充/减缓之间切换），接收能量时带暂停'] + [
    n for n in d['notes'] if '3D 人体同页' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v135_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v136_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v135','v136').replace('V135','V136'))
p = open(r'_资料\部署载荷\_shuzi_v135.ps1', encoding='utf-8').read()
p = p.replace('V135','V136').replace('v135','v136').replace("WEB_VER = '126'","WEB_VER = '127'").replace('APPJS_WEBVER126','APPJS_WEBVER127').replace('"web": "126"','"web": "127"').replace('LIVE_VERSION126','LIVE_VERSION127')
open(r'_资料\部署载荷\_shuzi_v136.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 127 ready')
