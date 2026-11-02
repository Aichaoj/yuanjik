# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
old = """      var sec = ['screen-energy', 'screen-contribute', 'screen-use', 'screen-breath'];
      for (var i = 0; i < sec.length; i++) {
        var s = $(sec[i]);
        if (s && !s.hidden) { showView('music'); return; }
      }"""
assert old in a
a = a.replace(old, """      var sec = ['screen-energy', 'screen-contribute', 'screen-use', 'screen-breath'];
      for (var i = 0; i < sec.length; i++) {
        var s = $(sec[i]);
        if (s && !s.hidden) {
          // 直接回能量场（不依赖 showView，避免历史栈干扰）
          var all = document.querySelectorAll('section.screen');
          for (var k = 0; k < all.length; k++) { all[k].hidden = true; }
          var m = $('screen-music');
          if (m) { m.hidden = false; }
          var tabs = document.querySelectorAll('#tabbar .tab-item');
          for (var t = 0; t < tabs.length; t++) {
            tabs[t].classList.toggle('is-active', tabs[t].getAttribute('data-tab') === 'music');
          }
          window.scrollTo(0, 0);
          return;
        }
      }""")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '144';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '144'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v152_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v153_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v152','v153').replace('V152','V153'))
p = open(r'_资料\部署载荷\_shuzi_v152.ps1', encoding='utf-8').read()
p = p.replace('V152','V153').replace('v152','v153').replace("WEB_VER = '143'","WEB_VER = '144'").replace('APPJS_WEBVER143','APPJS_WEBVER144').replace('"web": "143"','"web": "144"').replace('LIVE_VERSION143','LIVE_VERSION144')
open(r'_资料\部署载荷\_shuzi_v153.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 144 ready')
