# -*- coding: utf-8 -*-
"""v143：补充能量入口统一进 3D 页（不再进旧的小页），并修返回回路"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = "  function bindNavEntries() {\n    bindSessionButtons();"
assert old in a
a = a.replace(old, """  function bindNavEntries() {
    bindSessionButtons();
    // 入口统一：用克隆节点重绑，彻底覆盖历史处理器
    (function fixEntries() {
      function rebind(id, fn) {
        var el = $(id);
        if (!el || typeof freshNode !== 'function') { return; }
        var n = freshNode(id);
        if (n) { n.addEventListener('click', fn); }
      }
      rebind('btnGoUse', function () { window.__bodyMode = 'energy'; showView('energy'); });
      rebind('btnGoComfort', function () { window.__bodyMode = 'comfort'; showView('energy'); });
      rebind('btnGoContribute', function () { showView('contribute'); });
    })();""", 1)

# 返回键：从 3D/贡献/补充页统一回「能量场」
if 'function fixBackNav' not in a:
    a = a.replace("  function bindNavEntries() {", """  function fixBackNav() {
    var b = $('btnBack');
    if (!b || b.__fb) { return; }
    b.__fb = true;
    b.addEventListener('click', function () {
      var sec = ['screen-energy', 'screen-contribute', 'screen-use', 'screen-breath'];
      for (var i = 0; i < sec.length; i++) {
        var s = $(sec[i]);
        if (s && !s.hidden) { showView('music'); return; }
      }
    }, true);
  }

  function bindNavEntries() {""", 1)
    a = a.replace("  function bindNavEntries() {\n    bindSessionButtons();",
                  "  function bindNavEntries() {\n    bindSessionButtons();\n    fixBackNav();", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '143';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('entry/back fixed')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '143'
d['notes'] = ['补充能量入口统一进 3D 页；返回键统一回能量场（修返回回路）'] + [
    n for n in d['notes'] if '入口统一进 3D 页' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v151_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v152_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v151', 'v152').replace('V151', 'V152'))
p = open(r'_资料\部署载荷\_shuzi_v151.ps1', encoding='utf-8').read()
p = p.replace('V151', 'V152').replace('v151', 'v152')
p = p.replace("WEB_VER = '142'", "WEB_VER = '143'").replace('APPJS_WEBVER142', 'APPJS_WEBVER143')
p = p.replace('"web": "142"', '"web": "143"').replace('LIVE_VERSION142', 'LIVE_VERSION143')
open(r'_资料\部署载荷\_shuzi_v152.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 143 / v152 ready')
