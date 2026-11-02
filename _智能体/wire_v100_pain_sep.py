# -*- coding: utf-8 -*-
"""v100：减缓疼痛独立成一条路 —— 3D 人体选部位 → 再开始接收能量；从贡献/补充里拆出去"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 补充能量行只留「补充能量」（去掉舒缓不适，它归 3D 页）
old_row = '''        <div class="vc-row" id="vcRow2">
          <span class="vc-label">补充能量</span>
          <button type="button" class="vc-link" id="btnCEnergy">补充能量</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnCComfort">舒缓不适（意念痛处）</button>
        </div>'''
assert old_row in h
h = h.replace(old_row, '''        <div class="vc-row" id="vcRow2">
          <span class="vc-label">补充能量</span>
          <button type="button" class="vc-link" id="btnCEnergy">补充能量</button>
        </div>''')

# ② 音疗入口「减缓疼痛」→ 直接进 3D 人体页
h = h.replace('<span class="entry-sub">把意念放在痛处，边听边放松（放松练习，不是止痛治疗）</span>',
              '<span class="entry-sub">在立体人体上点选痛处，再开始接收能量（放松练习，不是止痛治疗）</span>')

# ③ 3D 页按钮文案
h = h.replace('<i>◈</i>吸收</button>', '<i>◈</i>接收能量</button>')

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027e', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# ④ 减缓疼痛入口 → 立体人体页
a = a.replace("""        showView('vault');
        setTimeout(function () {
          var el = document.querySelector('#vsPurpose [data-purpose="comfort"]');
          if (el) { el.click(); }
          if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        }, 350);""",
"""        showView('energy');
        setTimeout(function () {
          if ($('btnBodyMode')) { $('btnBodyMode').click(); }   // 直接切立体图
        }, 400);""")

# ⑤ 3D 页「接收能量」：必须有选中部位 → 以 comfort 方式开会话（部位带过去）
if 'function bindBodyReceive' not in a:
    a = a.replace("  function bindUseModes() {", """  function bindBodyReceive() {
    var b = $('btnBodyInject');
    if (!b || b.__bound2) { return; }
    b.__bound2 = true;
    b.addEventListener('click', function (ev) {
      var picked = (window.YJEnergy && window.YJEnergy.picked) ? window.YJEnergy.picked() : [];
      if (!picked || !picked.length) {
        toast('先在人体上点选不适的位置', 'ok');
        return;
      }
      ev.stopImmediatePropagation();
      ev.preventDefault();
      var spot = picked.map(function (x) { return (x && x.name) ? x.name : String(x); }).join('、').slice(0, 20);
      vs.purpose = 'comfort';
      vs.spot = spot;
      vsStart(true);
      if ($('vsCard')) { $('vsCard').hidden = false; }
      toast('开始接收能量：' + spot, 'ok');
    }, true);
  }

  function bindUseModes() {""", 1)
    a = a.replace("    if (name === 'vault') { loadVault(true); bindVC(); bindUseModes(); bindPickModes();",
                  "    if (name === 'vault') { loadVault(true); bindVC(); bindUseModes(); bindPickModes(); bindBodyReceive();")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '100';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '100'
d['notes'] = ['减缓疼痛独立：3D 人体点选痛处 → 「接收能量」开始；不再和贡献/补充混在一起'] + [
    n for n in d['notes'] if '减缓疼痛独立' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v107_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v108_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v107', 'v108').replace('V107', 'V108'))
p = open(r'_资料\部署载荷\_shuzi_v107.ps1', encoding='utf-8').read()
p = p.replace('V107', 'V108').replace('v107', 'v108')
p = p.replace("WEB_VER = '99'", "WEB_VER = '100'").replace('APPJS_WEBVER99', 'APPJS_WEBVER100')
p = p.replace('"web": "99"', '"web": "100"').replace('LIVE_VERSION99', 'LIVE_VERSION100')
open(r'_资料\部署载荷\_shuzi_v108.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 100 / v108 ready')
