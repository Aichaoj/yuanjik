# -*- coding: utf-8 -*-
"""v136：接收能量不再拉麦克风；改为播放低缓「能量声」（本地合成，不录音）"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 接收能量：不取麦
old = """      vsStart(true);
      if ($('vsCard')) { $('vsCard').hidden = false; }
      if ($('btnVsPause')) { $('btnVsPause').hidden = false; $('btnVsPause').textContent = '暂停'; }"""
assert old in a
a = a.replace(old, """      vsStart(false);                     // 接收能量：不开录音
      if ($('vsCard')) { $('vsCard').hidden = false; }
      if ($('btnVsPause')) { $('btnVsPause').hidden = false; $('btnVsPause').textContent = '暂停'; }
      // 低缓能量声（本地合成，不上传、不录音）
      try {
        if (window.YJMusic && window.YJMusic.play) { window.YJMusic.play(mode === 'comfort' ? 'yu' : 'gong'); }
      } catch (e) {}
      if ($('vsHint')) {
        $('vsHint').textContent = '接收能量中：低缓能量声（本机合成，不录音、不上传）';
        $('vsHint').style.color = '';
      }""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '136';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('receive without mic ok:', '不开录音' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '136'
d['notes'] = ['接收能量不再请求麦克风，改为播放低缓能量声（本机合成）'] + [
    n for n in d['notes'] if '低缓能量声' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v144_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v145_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v144', 'v145').replace('V144', 'V145'))
p = open(r'_资料\部署载荷\_shuzi_v144.ps1', encoding='utf-8').read()
p = p.replace('V144', 'V145').replace('v144', 'v145')
p = p.replace("WEB_VER = '135'", "WEB_VER = '136'").replace('APPJS_WEBVER135', 'APPJS_WEBVER136')
p = p.replace('"web": "135"', '"web": "136"').replace('LIVE_VERSION135', 'LIVE_VERSION136')
open(r'_资料\部署载荷\_shuzi_v145.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 136 / v145 ready')
