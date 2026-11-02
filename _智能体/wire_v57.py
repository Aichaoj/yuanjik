# -*- coding: utf-8 -*-
"""一次性的接线脚本：VIEWS/TAB_VIEWS 加 music、showView 钩子、state 字段（v57）。
跑完即可删；改动都写回 shuzi/web/app.js。"""
import os

P = r'shuzi\web\app.js'
s = open(P, encoding='utf-8').read()

old_views = "'reports', 'dictation', 'bespoke', 'intimacy', 'healthscore'];"
assert s.count(old_views) == 1, s.count(old_views)
s = s.replace(old_views, "'reports', 'dictation', 'bespoke', 'intimacy', 'healthscore', 'music'];")

s = s.replace("var TAB_VIEWS = ['home', 'rhythm', 'mall', 'mine'];",
              "var TAB_VIEWS = ['home', 'rhythm', 'music', 'mall', 'mine'];")

old_hook = "    if (name === 'healthscore') { loadHealthScore(true); }   // v48：综合健康分 v3"
assert s.count(old_hook) == 1, s.count(old_hook)
s = s.replace(old_hook, old_hook +
              "\n    if (name === 'music') { if (window.YJMusic) { window.YJMusic.init(); } }   // v57：音疗")

old_state = "    checkinBusy: false,"
assert s.count(old_state) == 1, s.count(old_state)
s = s.replace(old_state,
              "    checkinBusy: false,\n"
              "    hsAnswers: null,          // v57：服务端已存的健康分问卷（回填用）\n"
              "    hsLoaded: false,")

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched app.js OK; TAB_VIEWS count =', s.count("'home', 'rhythm', 'music', 'mall', 'mine'"))
