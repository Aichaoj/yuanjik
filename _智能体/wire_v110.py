# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
pairs = [
  ('<div class="vs-cell"><b id="vsMin">0</b><span>分钟</span></div>',
   '<div class="vs-cell"><b id="vsMin">0</b><span id="lbMin">分钟</span></div>'),
  ('<div class="vs-cell"><b id="vsEnergy">0</b><span>本次我的能量</span></div>',
   '<div class="vs-cell"><b id="vsEnergy">0</b><span id="lbEnergy">本次我的能量</span></div>'),
  ('<div class="vs-cell"><b id="vsCost">0</b><span>本次扣共享</span></div>',
   '<div class="vs-cell"><b id="vsCost">0</b><span id="lbCost">本次扣共享</span></div>'),
]
for o, n in pairs:
    if o in h:
        h = h.replace(o, n)
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027n', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('labels ids ok:', 'lbCost' in h)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
# 进入贡献/意念：标签改成「贡献」语义
a = a.replace("""      if ($('vsTitle')) { $('vsTitle').textContent = '贡献能量'; }""",
"""      if ($('vsTitle')) { $('vsTitle').textContent = '贡献能量'; }
        if ($('lbEnergy')) { $('lbEnergy').textContent = '本次贡献'; }
        if ($('lbCost')) { $('lbCost').textContent = '累计贡献'; }""")
a = a.replace("""        attachVsCard('screen-contribute');
        if ($('cosmic'))""",
"""        attachVsCard('screen-contribute');
        if ($('vsTitle')) { $('vsTitle').textContent = '贡献能量'; }
        if ($('lbEnergy')) { $('lbEnergy').textContent = '本次贡献'; }
        if ($('lbCost')) { $('lbCost').textContent = '累计贡献'; }
        if ($('cosmic'))""")
# 补充能量：恢复原标签
a = a.replace("""      e.addEventListener('click', function () { attachVsCard('screen-use'); start('energy'); });""",
"""      e.addEventListener('click', function () {
        attachVsCard('screen-use');
        if ($('lbEnergy')) { $('lbEnergy').textContent = '本次我的能量'; }
        if ($('lbCost')) { $('lbCost').textContent = '本次扣共享'; }
        start('energy');
      });""")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '110';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('labels switched')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '110'
d['notes'] = ['贡献能量会话卡改为「本次贡献 / 累计贡献」标注（不再写“扣共享”）'] + [n for n in d['notes'] if '本次贡献' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v117_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v118_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v117','v118').replace('V117','V118'))
p = open(r'_资料\部署载荷\_shuzi_v117.ps1', encoding='utf-8').read()
p = p.replace('V117','V118').replace('v117','v118').replace("WEB_VER = '109'","WEB_VER = '110'").replace('APPJS_WEBVER109','APPJS_WEBVER110').replace('"web": "109"','"web": "110"').replace('LIVE_VERSION109','LIVE_VERSION110')
open(r'_资料\部署载荷\_shuzi_v118.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 110 ready')
