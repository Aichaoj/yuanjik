# -*- coding: utf-8 -*-
"""v132：清掉历史重复监听（克隆节点再绑定），彻底解决暂停/接收能量被旧处理器干扰"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = "  function bindSessionButtons() {"
assert old in a
a = a.replace(old, """  function freshNode(id) {
    var el = $(id);
    if (!el) { return null; }
    var clone = el.cloneNode(true);   // 丢掉所有历史监听
    el.parentNode.replaceChild(clone, el);
    return clone;
  }

  function bindSessionButtons() {""", 1)

# 用克隆后的节点绑定
a = a.replace("""    function on(id, fn) {
      var el = $(id);
      if (el && !el.__sb) { el.__sb = true; el.addEventListener('click', fn); }
    }
    on('btnVsStart'""", """    function on(id, fn) {
      var el = freshNode(id);
      if (el) { el.__sb = true; el.addEventListener('click', fn); }
    }
    on('btnVsStart'""", 1)

# 接收能量：同样克隆后绑定
a = a.replace("""    var b = $('btnBodyInject');
    if (!b || b.__bound2) { return; }
    b.__bound2 = true;
    b.addEventListener('click', function (ev) {""",
"""    var b = freshNode('btnBodyInject');
    if (!b) { return; }
    b.__bound2 = true;
    b.addEventListener('click', function (ev) {""", 1)

# 去抖不再需要（历史监听已清），但保留无害
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '132';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('fresh node binding ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '132'
d['notes'] = ['修：暂停/接收能量按钮存在历史重复监听（改为克隆节点后重新绑定）'] + [
    n for n in d['notes'] if '重复监听' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v140_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v141_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v140', 'v141').replace('V140', 'V141'))
p = open(r'_资料\部署载荷\_shuzi_v140.ps1', encoding='utf-8').read()
p = p.replace('V140', 'V141').replace('v140', 'v141')
p = p.replace("WEB_VER = '131'", "WEB_VER = '132'").replace('APPJS_WEBVER131', 'APPJS_WEBVER132')
p = p.replace('"web": "131"', '"web": "132"').replace('LIVE_VERSION131', 'LIVE_VERSION132')
open(r'_资料\部署载荷\_shuzi_v141.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 132 ready')
