# -*- coding: utf-8 -*-
"""v139：能量场页「符咒注入/意念注入」改用克隆节点绑定（清历史监听），并在渲染时兜底绑定"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = """    var c = $('btnVChant');
    if (c && !c.__vb) { c.__vb = true; c.addEventListener('click', function () { start('contribute', true); }); }
    var ab = $('btnVAbsorb');
    if (ab && !ab.__vb) { ab.__vb = true; ab.addEventListener('click', function () { start('absorb', false); }); }"""
assert old in a, 'vault contrib binding block not found'
new = """    var c = (typeof freshNode === 'function') ? freshNode('btnVChant') : $('btnVChant');
    if (c) { c.__vb = true; c.addEventListener('click', function () { start('contribute', true); }); }
    var ab = (typeof freshNode === 'function') ? freshNode('btnVAbsorb') : $('btnVAbsorb');
    if (ab) { ab.__vb = true; ab.addEventListener('click', function () { start('absorb', false); }); }"""
a = a.replace(old, new)

# 渲染能量场时也绑一次（兜底）
a = a.replace("  function loadVault(force) {", """  function loadVault(force) {
    try { bindVaultContrib(); } catch (e) {}""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '139';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('vault contrib fresh-bind ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '139'
d['notes'] = ['修：能量场页「符咒注入/意念注入」点击无反应（改为清监听后重绑）'] + [
    n for n in d['notes'] if '点击无反应' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v147_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v148_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v147', 'v148').replace('V147', 'V148'))
p = open(r'_资料\部署载荷\_shuzi_v147.ps1', encoding='utf-8').read()
p = p.replace('V147', 'V148').replace('v147', 'v148')
p = p.replace("WEB_VER = '138'", "WEB_VER = '139'").replace('APPJS_WEBVER138', 'APPJS_WEBVER139')
p = p.replace('"web": "138"', '"web": "139"').replace('LIVE_VERSION138', 'LIVE_VERSION139')
open(r'_资料\部署载荷\_shuzi_v148.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 139 / v148 ready')
