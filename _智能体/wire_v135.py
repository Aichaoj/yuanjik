# -*- coding: utf-8 -*-
"""v135：补充能量 5 次/天；次数用完给出明确提示（接口 + 卡片红字 + 弹提示）；隐藏重复按钮"""
import json
import re

# ── 服务端：上限 5，错误信息带清楚数字 ─────────────────────
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
s = s.replace("    SESSION_DAILY_COUNT = 2       # 每人每天最多使用 2 次",
              "    SESSION_DAILY_COUNT = 5       # 每人每天最多使用 5 次（2026-10-25 调整）")
old_msg = """                           message='今天已经用过 %d 次能量了（每天 %d 次），明天再来'
                                   % (used_today, self.SESSION_DAILY_COUNT))"""
if old_msg in s:
    s = s.replace(old_msg, """                           message='补充能量今天的次数已用完（%d/%d），明天 0 点恢复'
                                   % (used_today, self.SESSION_DAILY_COUNT),
                           detail={'limit': self.SESSION_DAILY_COUNT, 'used': used_today,
                                   'reason': 'daily_limit_reached'})""")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('limit=5, message ok:', 'daily_limit_reached' in s)

# ── 前端：错误显性化 + 隐藏多余按钮 ──────────────────────
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = "      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }"
assert old in a
a = a.replace(old, """      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }
      if ($('btnVsStart')) { $('btnVsStart').hidden = true; }
      if ($('btnVsSilent')) { $('btnVsSilent').hidden = true; }""", 1)

old2 = """    }).catch(function (err) {
      vsStatus('未开始', false);
      if ($('vsHint')) { $('vsHint').textContent = '开启失败：' + readableError(err); }
    });"""
if old2 in a:
    a = a.replace(old2, """    }).catch(function (err) {
      vsStatus('未开始', false);
      var msg = readableError(err) || '';
      var tip = /用完了|上限|429|每天/.test(msg)
        ? '今天的补充能量已用完（5/5），明天 0 点恢复；现在可以选「减缓疼痛」或「贡献能量」'
        : '开启失败：' + msg + '（可换「意念注入」或稍后再试）';
      if ($('vsHint')) {
        $('vsHint').textContent = tip;
        $('vsHint').style.color = '#c0392b';
      }
      toast(tip, 'ok');
    });""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '135';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('front prompt ok:', '已用完（5/5）' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '135'
d['notes'] = ['补充能量改为 5 次/天；次数用完会红字+弹窗明确提示「已用完，明天 0 点恢复」'] + [
    n for n in d['notes'] if '已用完' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v142_run.py', encoding='utf-8').read()
if '"server/vault.py"' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v144_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v142', 'v144').replace('V142', 'V144'))
p = open(r'_资料\部署载荷\_shuzi_v142.ps1', encoding='utf-8').read()
p = p.replace('V142', 'V144').replace('v142', 'v144')
p = p.replace("WEB_VER = '133'", "WEB_VER = '135'").replace('APPJS_WEBVER133', 'APPJS_WEBVER135')
p = p.replace('"web": "133"', '"web": "135"').replace('LIVE_VERSION133', 'LIVE_VERSION135')
open(r'_资料\部署载荷\_shuzi_v144.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 135 / v144 ready')
