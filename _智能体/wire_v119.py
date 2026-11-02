# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# ① 补充能量：标题强制为「补充能量」（原来沿用上次的贡献能量）
a = a.replace("""    function start(purpose) {
      vs.purpose = purpose;
      if ($('vsCard')) { $('vsCard').hidden = false; }""",
"""    function start(purpose) {
      vs.purpose = purpose;
      attachVsCard('screen-use');
      if ($('vsTitle')) { $('vsTitle').textContent = (purpose === 'comfort' ? '减缓疼痛' : '补充能量'); }
      if ($('lbEnergy')) { $('lbEnergy').textContent = '本次我的能量'; }
      if ($('lbCost')) { $('lbCost').textContent = '本次扣共享'; }
      if ($('btnVsPause')) { $('btnVsPause').hidden = false; $('btnVsPause').textContent = '暂停'; }
      if ($('vsCard')) { $('vsCard').hidden = false; }""")

# ② 减缓疼痛（3D 页）：把会话卡挂到本页并显示暂停
a = a.replace("""      vs.purpose = 'comfort';
      vs.spot = spot;
      vsStart(true);
      if ($('vsCard')) { $('vsCard').hidden = false; }""",
"""      vs.purpose = 'comfort';
      vs.spot = spot;
      attachVsCard('screen-energy');
      if ($('vsTitle')) { $('vsTitle').textContent = '减缓疼痛'; }
      if ($('lbEnergy')) { $('lbEnergy').textContent = '本次我的能量'; }
      if ($('lbCost')) { $('lbCost').textContent = '本次扣共享'; }
      vsStart(true);
      if ($('vsCard')) { $('vsCard').hidden = false; }
      if ($('btnVsPause')) { $('btnVsPause').hidden = false; $('btnVsPause').textContent = '暂停'; }""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '119';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('use title + pause ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '119'
d['notes'] = ['补充能量标题不再显示贡献能量；减缓疼痛页也能暂停'] + [n for n in d['notes'] if '减缓疼痛页也能暂停' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v127_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v128_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v127','v128').replace('V127','V128'))
p = open(r'_资料\部署载荷\_shuzi_v127.ps1', encoding='utf-8').read()
p = p.replace('V127','V128').replace('v127','v128').replace("WEB_VER = '118'","WEB_VER = '119'").replace('APPJS_WEBVER118','APPJS_WEBVER119').replace('"web": "118"','"web": "119"').replace('LIVE_VERSION118','LIVE_VERSION119')
open(r'_资料\部署载荷\_shuzi_v128.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 119 ready')
