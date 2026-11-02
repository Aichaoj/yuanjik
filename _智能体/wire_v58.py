# -*- coding: utf-8 -*-
"""v58 接线：VIEWS 增加 energy/breath、showView 钩子、音疗页两个入口按钮绑定。"""
P = r'shuzi\web\app.js'
s = open(P, encoding='utf-8').read()

old = "'intimacy', 'healthscore', 'music'];"
assert s.count(old) == 1, s.count(old)
s = s.replace(old, "'intimacy', 'healthscore', 'music', 'energy', 'breath'];")

old_hook = "    if (name === 'music') { if (window.YJMusic) { window.YJMusic.init(); } }   // v57：音疗"
assert s.count(old_hook) == 1, s.count(old_hook)
new_hook = old_hook + """
    // v58：能量注入 / 呼吸引导（同一份 energy.js 里的两个模块）
    if (name === 'music') { bindMusicEntries(); }
    if (name === 'energy') { if (window.YJEnergy) { window.YJEnergy.init(); } }
    if (name === 'breath') { if (window.YJEnergy) { window.YJEnergy.initBreath(); } }"""
s = s.replace(old_hook, new_hook)

# 入口绑定函数（放在 bindHomeNeed 之后，避免与其它绑定函数混在一起）
anchor = """    var btn = $('btnQuickReport');
    if (btn) { btn.addEventListener('click', submitQuickReport); }
  }
"""
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """
  /** v58：音疗页的两个入口（能量注入 / 呼吸引导）——只绑一次 */
  function bindMusicEntries() {
    var a = $('btnGoEnergy');
    if (a && !a.__bound) {
      a.__bound = true;
      a.addEventListener('click', function () { showView('energy'); });
    }
    var b = $('btnGoBreath');
    if (b && !b.__bound) {
      b.__bound = true;
      b.addEventListener('click', function () { showView('breath'); });
    }
  }
""")

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched; energy hooks =', s.count("if (name === 'energy')"), '| bindMusicEntries =', s.count('function bindMusicEntries'))
