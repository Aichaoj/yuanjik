# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 找到「吸收能量」入口卡并整块删除
i = h.find('<span class="entry-title">吸收能量</span>')
assert i > 0
start = h.rfind('<button', 0, i)
end = h.find('</button>', i) + len('</button>')
block = h[start:end]
print('removing block head:', block[:60].replace(chr(10),' '))
h = h[:start] + h[end:]

# 文案改掉「吸收能量」
h = h.replace('你在任何地方按下「吸收能量」，都会计入这个共享的仓；',
              '你在任何地方贡献能量，都会计入这个共享的仓；')
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027k', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('entries left: 吸收能量 =', ('吸收能量' in h))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '108';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '108'
d['notes'] = ['去掉重复的「吸收能量」入口（与补充能量同义），共享仓文案随之调整'] + [n for n in d['notes'] if '吸收能量' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v115_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v116_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v115','v116').replace('V115','V116'))
p = open(r'_资料\部署载荷\_shuzi_v115.ps1', encoding='utf-8').read()
p = p.replace('V115','V116').replace('v115','v116').replace("WEB_VER = '107'","WEB_VER = '108'").replace('APPJS_WEBVER107','APPJS_WEBVER108').replace('"web": "107"','"web": "108"').replace('LIVE_VERSION107','LIVE_VERSION108')
open(r'_资料\部署载荷\_shuzi_v116.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 108 ready')
