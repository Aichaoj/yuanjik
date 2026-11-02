# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
if 'id="cosmicFx"' not in h:
    fx = '\n  <div class="cosmic-fx" id="cosmicFx" aria-hidden="true">' + \
         ''.join('<b class="fcm f%d"></b>' % i for i in range(1, 17)) + \
         '<span class="fx-core"></span></div>\n'
    h = h.replace('<body>', '<body>' + fx, 1)
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027m', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('overlay html ok')

css = """
/* ── v109 意念注入：全屏宇宙能量汇入 ─────────────────────── */
.cosmic-fx { position: fixed; inset: 0; z-index: 9999; display: none; pointer-events: none;
  background: radial-gradient(60% 60% at 50% 50%, rgba(40,80,160,.35), rgba(4,8,18,.92) 72%); }
.cosmic-fx.on { display: block; }
.fx-core { position: absolute; left: 50%; top: 50%; width: 80px; height: 80px;
  margin: -40px 0 0 -40px; border-radius: 50%;
  background: radial-gradient(circle, #fff, #a9dcff 42%, rgba(120,190,255,0) 72%);
  box-shadow: 0 0 48px rgba(160,215,255,.85); animation: fxCore 2s ease-in-out infinite; }
@keyframes fxCore { 0%,100% { transform: scale(.85); opacity: .9 } 50% { transform: scale(1.2); opacity: 1 } }
.cosmic-fx .fcm { position: absolute; left: 50%; top: 50%; width: 6px; height: 6px; border-radius: 50%;
  background: #e6f4ff; box-shadow: 0 0 12px rgba(190,225,255,.95); opacity: 0; }
.cosmic-fx.on .fcm { animation: fxIn 2.2s linear infinite; }
.cosmic-fx .f1 { --a: 0deg } .cosmic-fx .f2 { --a: 22deg; animation-delay: .1s }
.cosmic-fx .f3 { --a: 45deg; animation-delay: .2s } .cosmic-fx .f4 { --a: 67deg; animation-delay: .3s }
.cosmic-fx .f5 { --a: 90deg; animation-delay: .4s } .cosmic-fx .f6 { --a: 112deg; animation-delay: .5s }
.cosmic-fx .f7 { --a: 135deg; animation-delay: .6s } .cosmic-fx .f8 { --a: 157deg; animation-delay: .7s }
.cosmic-fx .f9 { --a: 180deg; animation-delay: .8s } .cosmic-fx .f10 { --a: 202deg; animation-delay: .9s }
.cosmic-fx .f11 { --a: 225deg; animation-delay: 1s } .cosmic-fx .f12 { --a: 247deg; animation-delay: 1.1s }
.cosmic-fx .f13 { --a: 270deg; animation-delay: 1.2s } .cosmic-fx .f14 { --a: 292deg; animation-delay: 1.3s }
.cosmic-fx .f15 { --a: 315deg; animation-delay: 1.4s } .cosmic-fx .f16 { --a: 337deg; animation-delay: 1.5s }
@keyframes fxIn {
  0% { opacity: 0; transform: rotate(var(--a)) translateX(46vmin) scale(2); }
  12% { opacity: 1; }
  88% { opacity: .95; }
  100% { opacity: 0; transform: rotate(var(--a)) translateX(8px) scale(.5); }
}
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace("""        if ($('cosmic')) { $('cosmic').classList.add('is-on'); }""",
"""        if ($('cosmic')) { $('cosmic').classList.add('is-on'); }
        if ($('cosmicFx')) { $('cosmicFx').classList.add('on'); }
        setTimeout(function () { if ($('cosmicFx')) { $('cosmicFx').classList.remove('on'); } }, 9000);""")
a = a.replace("""    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }""",
"""    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }
    if ($('cosmicFx')) { $('cosmicFx').classList.remove('on'); }""")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '109';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '109'
d['notes'] = ['意念注入加全屏宇宙能量汇入动效（16 道光线向中心汇聚）'] + [n for n in d['notes'] if '全屏宇宙' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v116_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v117_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v116','v117').replace('V116','V117'))
p = open(r'_资料\部署载荷\_shuzi_v116.ps1', encoding='utf-8').read()
p = p.replace('V116','V117').replace('v116','v117').replace("WEB_VER = '108'","WEB_VER = '109'").replace('APPJS_WEBVER108','APPJS_WEBVER109').replace('"web": "108"','"web": "109"').replace('LIVE_VERSION108','LIVE_VERSION109')
open(r'_资料\部署载荷\_shuzi_v117.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 109 ready')
