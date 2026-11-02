# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

anchor = "  function vsStart(withMic) {"
assert anchor in a
inject = """  function vsStart(withMic) {
    // 标题与格子标签由 purpose 唯一决定（避免各入口互相覆盖）
    var ttl = (vs.purpose === 'contribute' || vs.purpose === 'absorb') ? '贡献能量'
            : (vs.purpose === 'comfort' ? '减缓疼痛' : '补充能量');
    if ($('vsTitle')) { $('vsTitle').textContent = ttl; }
    if ($('lbEnergy')) {
      $('lbEnergy').textContent = (vs.purpose === 'contribute' || vs.purpose === 'absorb')
        ? '本次贡献' : '本次我的能量';
    }
    if ($('lbCost')) {
      $('lbCost').textContent = (vs.purpose === 'contribute' || vs.purpose === 'absorb')
        ? '累计贡献' : '本次扣共享';
    }
"""
a = a.replace(anchor, inject, 1)
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '124';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('title from purpose')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '124'
d['notes'] = ['补充能量/贡献能量的卡片标题与格子标签改为按方式唯一决定，避免互相串'] + [n for n in d['notes'] if '唯一决定' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v132_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v133_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v132','v133').replace('V132','V133'))
p = open(r'_资料\部署载荷\_shuzi_v132.ps1', encoding='utf-8').read()
p = p.replace('V132','V133').replace('v132','v133').replace("WEB_VER = '123'","WEB_VER = '124'").replace('APPJS_WEBVER123','APPJS_WEBVER124').replace('"web": "123"','"web": "124"').replace('LIVE_VERSION123','LIVE_VERSION124')
open(r'_资料\部署载荷\_shuzi_v133.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 124 ready')
