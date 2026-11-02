# -*- coding: utf-8 -*-
p = r'shuzi\web\app.js'
s = open(p, encoding='utf-8').read()
# 从 bindVault 中移除两个按钮绑定（它们属于「我的」页，绑在 vault 钩子上不会触发）
old = """    var ruleBtn = $('btnEnergyRule');
    if (ruleBtn && !ruleBtn.__bound) {
      ruleBtn.__bound = true;
      ruleBtn.addEventListener('click', function () {
        var box = $('energyRule');
        if (box) { box.hidden = !box.hidden; }
      });
    }
    var mr = $('btnMineRecharge');
    if (mr && !mr.__bound) {
      mr.__bound = true;
      mr.addEventListener('click', function () { showView('vault'); });
    }
"""
assert s.count(old) == 1
s = s.replace(old, "")
# 放进 loadMineEnergy（我的页每次进入都会跑，且用 __bound 幂等）
anchor = "  function loadMineEnergy() {\n    var card = $('mineEnergyCard');\n    if (!card) { return; }"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """
    var ruleBtn = $('btnEnergyRule');
    if (ruleBtn && !ruleBtn.__bound) {
      ruleBtn.__bound = true;
      ruleBtn.addEventListener('click', function () {
        var box = $('energyRule');
        if (box) { box.hidden = !box.hidden; }
      });
    }
    var mr = $('btnMineRecharge');
    if (mr && !mr.__bound) {
      mr.__bound = true;
      mr.addEventListener('click', function () { showView('vault'); });
    }""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('bindings moved')
