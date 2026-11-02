# -*- coding: utf-8 -*-
"""v102：符咒注入确保开麦（取不到就明确报错）；意念注入加「宇宙能量四面汇入」动效"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = '''      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCChant">符咒注入</button>'''
assert old in h
new = '''      <div class="cosmic" id="cosmic" aria-hidden="true">
        <b class="cm c1"></b><b class="cm c2"></b><b class="cm c3"></b><b class="cm c4"></b>
        <b class="cm c5"></b><b class="cm c6"></b><b class="cm c7"></b><b class="cm c8"></b>
        <span class="cosmic-core"></span>
      </div>
      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCChant">符咒注入</button>'''
h = h.replace(old, new)
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027g', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

css = """
/* ── v102 宇宙能量汇入（贡献能量页）────────────────────────── */
.cosmic { position: relative; height: 190px; margin: 4px 0 10px; overflow: hidden;
  border-radius: 16px; background:
    radial-gradient(60% 60% at 50% 50%, rgba(90,140,255,.28), rgba(10,20,40,.96) 70%),
    radial-gradient(120% 90% at 50% 0%, #0d1c38, #060a14 70%); }
.cosmic-core { position: absolute; left: 50%; top: 50%; width: 46px; height: 46px;
  margin: -23px 0 0 -23px; border-radius: 50%;
  background: radial-gradient(circle, #fff, #9fd8ff 45%, rgba(120,190,255,0) 72%);
  box-shadow: 0 0 26px rgba(150,210,255,.75); animation: corePulse 2.4s ease-in-out infinite; }
@keyframes corePulse { 0%,100% { transform: scale(.9); opacity: .85 } 50% { transform: scale(1.15); opacity: 1 } }
.cosmic .cm { position: absolute; left: 50%; top: 50%; width: 4px; height: 4px; border-radius: 50%;
  background: #cfe8ff; box-shadow: 0 0 8px rgba(180,220,255,.9); opacity: 0; }
.cosmic.is-on .cm { animation: cmIn 2.6s linear infinite; }
.cosmic .c1 { --a: 0deg; animation-delay: 0s } .cosmic .c2 { --a: 45deg; animation-delay: .33s }
.cosmic .c3 { --a: 90deg; animation-delay: .66s } .cosmic .c4 { --a: 135deg; animation-delay: .99s }
.cosmic .c5 { --a: 180deg; animation-delay: 1.32s } .cosmic .c6 { --a: 225deg; animation-delay: 1.65s }
.cosmic .c7 { --a: 270deg; animation-delay: 1.98s } .cosmic .c8 { --a: 315deg; animation-delay: 2.31s }
@keyframes cmIn {
  0% { opacity: 0; transform: rotate(var(--a)) translateX(150px) scale(1.6); }
  12% { opacity: 1; }
  85% { opacity: .9; }
  100% { opacity: 0; transform: rotate(var(--a)) translateX(6px) scale(.4); }
}
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 符咒：开麦失败要报出来
a = a.replace("""        attachVsCard('screen-contribute');
        vsStart(true);""",
"""        attachVsCard('screen-contribute');
        vsStart(true);
        setTimeout(function () {
          if (!vs.stream) { toast('没拿到麦克风：请允许录音权限，或改用「意念注入」', 'ok'); }
        }, 1600);""")

# 意念：打开宇宙汇入动画
a = a.replace("""        attachVsCard('screen-contribute');
        vsStart(false);""",
"""        attachVsCard('screen-contribute');
        if ($('cosmic')) { $('cosmic').classList.add('is-on'); }
        vsStart(false);
        toast('意念注入开始：能量从四方汇入', 'ok');""")

# 停止时关动画
a = a.replace("    vs.released = true;", "    vs.released = true;")
a = a.replace("  function vsFinish(msg) {", """  function vsFinish(msg) {
    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '102';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '102'
d['notes'] = ['符咒注入：拿不到麦克风会明确提示；意念注入：新增宇宙能量四面汇入动效'] + [
    n for n in d['notes'] if '宇宙能量' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v109_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v110_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v109', 'v110').replace('V109', 'V110'))
p = open(r'_资料\部署载荷\_shuzi_v109.ps1', encoding='utf-8').read()
p = p.replace('V109', 'V110').replace('v109', 'v110')
p = p.replace("WEB_VER = '101'", "WEB_VER = '102'").replace('APPJS_WEBVER101', 'APPJS_WEBVER102')
p = p.replace('"web": "101"', '"web": "102"').replace('LIVE_VERSION101', 'LIVE_VERSION102')
open(r'_资料\部署载荷\_shuzi_v110.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 102 / v110 ready')
