# -*- coding: utf-8 -*-
"""v131：会话状态重置 + 暂停防重复触发 + 接收能量按模式启动"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 1) vsStart 开头重置会话相关状态（避免上一个流程残留）
old = "  function vsStart(withMic) {"
assert old in a
a = a.replace(old, """  function vsStart(withMic) {
    // 重置上一轮残留（不同流程共用同一个 vs 对象）
    vs.paused = false;
    vs.sid = '';
    vs.minutes = 0;
    vs.energy = 0;
    vs.voicedMs = 0;
    vs.totalMs = 0;
    if (vs.ticker) { clearInterval(vs.ticker); vs.ticker = null; }
    if ($('btnVsPause')) { $('btnVsPause').textContent = '暂停'; }
""", 1)

# 2) 暂停按钮：250ms 去抖（历史上存在重复绑定，两次点击互相抵消）
a = a.replace("""    on('btnVsPause', function () {
      if (!vs.running) { return; }""",
"""    on('btnVsPause', function () {
      var now = Date.now();
      if (window.__pauseLock && now - window.__pauseLock < 400) { return; }
      window.__pauseLock = now;
      if (!vs.running) { return; }""")

# 3) 接收能量：明确用入口模式，并把 purpose 先写死再启动
a = a.replace("""      var mode = window.__bodyMode || 'comfort';""",
"""      var mode = (window.__bodyMode === 'energy') ? 'energy' : 'comfort';""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '131';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('state reset + pause debounce ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '131'
d['notes'] = ['修：会话状态不重置导致补充模式沿用贡献、暂停按钮偶发无效'] + [
    n for n in d['notes'] if '会话状态不重置' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v139_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v140_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v139', 'v140').replace('V139', 'V140'))
p = open(r'_资料\部署载荷\_shuzi_v139.ps1', encoding='utf-8').read()
p = p.replace('V139', 'V140').replace('v139', 'v140')
p = p.replace("WEB_VER = '130'", "WEB_VER = '131'").replace('APPJS_WEBVER130', 'APPJS_WEBVER131')
p = p.replace('"web": "130"', '"web": "131"').replace('LIVE_VERSION130', 'LIVE_VERSION131')
open(r'_资料\部署载荷\_shuzi_v140.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 131 ready')
