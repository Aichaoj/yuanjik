# -*- coding: utf-8 -*-
import json, re

# 1) 登录 300 天免登录：把访问令牌 TTL 提到 300 天
P = r'shuzi\server\serve.py'
s = open(P, encoding='utf-8').read()
m = re.search(r"(TOKEN_TTL\w*)\s*=\s*([0-9][0-9_]*\s*\*\s*[0-9_]+|[0-9_]+)", s)
print('ttl before:', m.group(0) if m else None)
if m:
    s = s[:m.start()] + m.group(1) + ' = 300 * 24 * 3600    # 登录一次 300 天免登录（2026-10-25 师父令）' + s[m.end():]
    open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('ttl after: 300 days')

# 2) 入口增加「减缓疼痛」
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = """        <button type="button" class="entry-card" id="btnGoVault">"""
assert h.count(old) == 1
h = h.replace(old, """        <button type="button" class="entry-card" id="btnGoComfort">
          <span class="entry-title">减缓疼痛</span>
          <span class="entry-sub">把意念放在痛处，边听边放松（放松练习，不是止痛治疗）</span>
        </button>
        <button type="button" class="entry-card" id="btnGoVault">""")
h = h.replace('app.js?v=20261026m','app.js?v=20261026n')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('entry added')

# 3) 版本 74 + app.js WEB_VER
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '74';", a, count=1)
# 减缓疼痛入口：进仓并预选「舒缓不适」
a = a.replace("""    var mv = $('btnMineVault');""", """    var cm = $('btnGoComfort');
    if (cm && !cm.__bound) {
      cm.__bound = true;
      cm.addEventListener('click', function () {
        showView('vault');
        setTimeout(function () {
          var el = document.querySelector('#vsPurpose [data-purpose="comfort"]');
          if (el) { el.click(); }
          if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        }, 350);
      });
    }
    var mv = $('btnMineVault');""")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web']='74'
d['notes'] = ['登录一次 300 天免登录（令牌有效期延长）', '音疗入口新增「减缓疼痛」：直达舒缓不适（意念痛处）'] + [n for n in d['notes'] if '300 天' not in n and '减缓疼痛' not in n]
open(VJ,'w',encoding='utf-8',newline='\n').write(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('web 74')
