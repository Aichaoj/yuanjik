# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = """        if ($('cosmicFx')) { $('cosmicFx').classList.add('on'); }
        setTimeout(function () { if ($('cosmicFx')) { $('cosmicFx').classList.remove('on'); } }, 9000);"""
assert old in a
new = """        if ($('cosmicFx')) {
          $('cosmicFx').classList.add('on');
          var fx = $('cosmicFx');
          var off = function () { fx.classList.remove('on'); };
          setTimeout(off, 5000);
          document.addEventListener('click', off, { once: true });
          document.addEventListener('touchstart', off, { once: true });
        }"""
a = a.replace(old, new)
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '123';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('overlay dismissible')

css = """
/* ── v123：意念注入全屏光效只做暗角，不遮挡操作、5 秒自动退 ── */
.cosmic-fx { background: radial-gradient(70% 60% at 50% 50%,
  rgba(30, 60, 120, .18), rgba(4, 8, 18, .62) 78%) !important; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028d', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '123'
d['notes'] = ['修：意念注入全屏光效会一直盖住页面（现在 5 秒自动退、点一下即退、暗角减淡）'] + [
    n for n in d['notes'] if '全屏光效' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v131_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v132_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v131','v132').replace('V131','V132'))
p = open(r'_资料\部署载荷\_shuzi_v131.ps1', encoding='utf-8').read()
p = p.replace('V131','V132').replace('v131','v132').replace("WEB_VER = '122'","WEB_VER = '123'").replace('APPJS_WEBVER122','APPJS_WEBVER123').replace('"web": "122"','"web": "123"').replace('LIVE_VERSION122','LIVE_VERSION123')
open(r'_资料\部署载荷\_shuzi_v132.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 123 ready')
