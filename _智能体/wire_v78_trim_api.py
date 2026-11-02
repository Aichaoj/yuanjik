# -*- coding: utf-8 -*-
"""v78：能量指数接口只回必要字段（去掉 parts / rule / note / bands），抓包也看不到系数"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

old = """        return {'rule_version': 'v1',
                'index': p['index'], 'cap': self.ENERGY_CAP, 'recharge_line': self.RECHARGE_LINE,
                'at': now.strftime('%Y-%m-%dT%H:%M'), 'parts': p, 'curve': curve,
                'band': p['band'], 'band_color': p['band_color'],
                'need_recharge': p['need_recharge'],
                'bands': [{'line': l, 'name': n, 'color': c} for l, n, c in self.BANDS],
                'rule': {'drain_per_hour': self.DRAIN_PER_HOUR, 'drain_max': self.DRAIN_MAX,
                         'night_recover_ratio': self.NIGHT_RECOVER_RATIO,
                         'window': '白天 06:00–22:00 每小时 -12.5；22:00–06:00 回补当天消耗的 90%',
                         'base': '按出生月令与出生时辰估五行 → 气机升降（升：肝脾／降：肺胃肠／水火既济）'},
                'note': '这是个人能量指数的读法：0–1000 刻度，200 为"需要补充"线；'
                        '生成依据是出生时空的五行格局 + 参与度 + 今日补充 + 昼夜节律。'
                        '它不是生理指标，也不构成任何健康结论。'}"""
assert s.count(old) == 1
new = """        # ★ 只回"用户需要的"：数值、能级、是否需补充、曲线。
        #   内部参数（parts/rule/bands/note）一律不下发 —— 抓包也看不到系数（师父 2026-10-25 令）
        return {'index': p['index'], 'cap': self.ENERGY_CAP, 'recharge_line': self.RECHARGE_LINE,
                'at': now.strftime('%Y-%m-%dT%H:%M'), 'curve': curve,
                'band': p['band'], 'band_color': p['band_color'],
                'need_recharge': p['need_recharge']}"""
s = s.replace(old, new)
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('energy api trimmed')

# 前端不再依赖 rule/bands
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace("""      if ($('mineEnergyHint') && d.rule) {
        $('mineEnergyHint').textContent = (d.rule.base || '') + '；' + (d.rule.window || '') +
          '；低于 ' + (d.recharge_line || 200) + ' 会提醒补充。这是体验读法，不是生理指标。';
      }""", "")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '78';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '78'
d['notes'] = ['能量指数接口不再下发任何模型内部字段（只给数值/能级/是否需补充/曲线）'] + [
    n for n in d['notes'] if '不再下发' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web 78')
