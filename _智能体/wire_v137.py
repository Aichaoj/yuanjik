# -*- coding: utf-8 -*-
"""v137：意念注入恢复页内「宇宙能量汇入」动画（压缩在页面内，不做整页）"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = """      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        attachVsCard('screen-contribute');"""
assert old in a
a = a.replace(old, """      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        attachVsCard('screen-contribute');
        // 页内汇入动画（区域在贡献页顶部，非整页）
        if ($('cosmic')) {
          $('cosmic').classList.add('is-on');
          $('cosmic').scrollIntoView({ behavior: 'smooth', block: 'center' });
        }""")

# 结束/停止时关闭动画
if "if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }" not in a:
    a = a.replace("  function vsFinish(msg) {", """  function vsFinish(msg) {
    if ($('cosmic')) { $('cosmic').classList.remove('is-on'); }""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '137';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('cosmic inline restored:', "cosmic').classList.add('is-on')" in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '137'
d['notes'] = ['意念注入恢复页内「宇宙能量汇入」动画（压缩在贡献页顶部，不占整页）'] + [
    n for n in d['notes'] if '宇宙能量汇入' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v145_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v146_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v145', 'v146').replace('V145', 'V146'))
p = open(r'_资料\部署载荷\_shuzi_v145.ps1', encoding='utf-8').read()
p = p.replace('V145', 'V146').replace('v145', 'v146')
p = p.replace("WEB_VER = '136'", "WEB_VER = '137'").replace('APPJS_WEBVER136', 'APPJS_WEBVER137')
p = p.replace('"web": "136"', '"web": "137"').replace('LIVE_VERSION136', 'LIVE_VERSION137')
open(r'_资料\部署载荷\_shuzi_v146.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 137 / v146 ready')
