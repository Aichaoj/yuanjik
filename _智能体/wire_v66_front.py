# -*- coding: utf-8 -*-
"""v66 前端：共享能量与本次消耗显示 + 版本号"""
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 1) 开始后同步共享能量
old = """      if ($('vsHint')) {
        $('vsHint').textContent = '本轮上限 ' + (d.max_minutes || 120) + ' 分钟，每 ' +
          (d.prompt_minutes || 15) + ' 分钟提示一次；今日剩余额度 ' + (d.daily_minutes_left || 0) + ' 分钟。';
      }"""
assert a.count(old) == 1
a = a.replace(old, """      if ($('vsHint')) {
        $('vsHint').textContent = '本轮上限 ' + (d.max_minutes || 120) + ' 分钟，每 ' +
          (d.prompt_minutes || 15) + ' 分钟提示一次；今日剩余额度 ' + (d.daily_minutes_left || 0) +
          ' 分钟。每 15 分钟会从共享能量里扣 1 个。';
      }
      vsSet('vsCost', '0');
      apiFetch('/vault/status').then(function (env) {
        var st = (env && env.data) || {};
        vsSet('vsShared', vaultFmt((st.shared || {}).index || 0));
      }, function () {});""")

# 2) tick 里更新共享能量与本次消耗
old2 = """        vs.minutes = d.minutes_total || (vs.minutes + 1);
        vs.energy = d.energy_total || vs.energy;
        vsSet('vsMin', String(vs.minutes));
        vsSet('vsEnergy', String(vs.energy));
        vsSet('vsRate', String(d.rate || '—'));"""
assert a.count(old2) == 1
a = a.replace(old2, """        vs.minutes = d.minutes_total || (vs.minutes + 1);
        vs.energy = d.energy_total || vs.energy;
        vsSet('vsMin', String(vs.minutes));
        vsSet('vsEnergy', String(vs.energy));
        vsSet('vsRate', String(d.rate || '—'));
        if (d.shared) { vsSet('vsShared', vaultFmt(d.shared.index || 0)); }
        if (typeof d.used_cost === 'number') { vsSet('vsCost', String(d.used_cost)); }
        if (d.shared_cost > 0) {
          toast('使用能量：共享能量 -' + d.shared_cost + '（累计 ' + d.used_cost + '）', 'ok');
        }""")

# 3) 结束提示带消耗
old3 = """            $('vsHint').textContent = (msg || '本轮结束') + ' 共 ' + (d.minutes || 0) + ' 分钟、' +
              (d.energy || 0) + ' 能量值，已 1:1 折算积分。';"""
assert a.count(old3) == 1
a = a.replace(old3, """            $('vsHint').textContent = (msg || '本轮结束') + ' 共 ' + (d.minutes || 0) + ' 分钟、' +
              (d.energy || 0) + ' 能量值，已 1:1 折算积分；共享能量共扣 ' + (d.used_cost || 0) + ' 个。';""")

a = a.replace("var WEB_VER = '65';", "var WEB_VER = '66';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

css = """
.vs-grid-2 { grid-template-columns: 1fr 1fr; margin-top: -6px; }
.vs-rule { margin: 2px 0 10px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
