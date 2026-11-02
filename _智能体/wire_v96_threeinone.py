# -*- coding: utf-8 -*-
"""v96：贡献能量三合一（文字 + 两个选择）：「贡献能量  符咒注入 · 意念注入」"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 删除独立的选择面板卡（内容并入大按钮位置）
p_start = h.find('      <section class="card" id="vsPick">')
assert p_start > 0
p_end = h.find('</section>', p_start) + len('</section>')
h = h[:p_start] + h[p_end:]

# ② 大按钮 → 一行文字 + 两个选择
old_btn = '        <button type="button" class="btn btn-primary vault-btn" id="btnVaultInject">贡献能量</button>'
assert old_btn in h, 'hero button not found'
new_row = '''        <div class="vc-row" id="vcRow">
          <span class="vc-label">贡献能量</span>
          <button type="button" class="vc-link" id="btnCChant">符咒注入</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnCAbsorb">意念注入</button>
        </div>'''
h = h.replace(old_btn, new_row)

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027c', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok; has vc-row =', 'vc-row' in h, '; vsPick left =', 'id="vsPick"' in h)

css = """
/* ── v96 贡献能量：文字 + 两个选择 ───────────────────────────── */
.vc-row { display: flex; align-items: center; justify-content: center; gap: 6px;
  flex-wrap: wrap; margin: 10px 0 4px; font-size: 14px; }
.vc-label { color: var(--ink-1); font-weight: 700; }
.vc-link { border: 0; background: none; padding: 2px 4px; font: inherit; cursor: pointer;
  color: var(--brand-1); text-decoration: underline; text-underline-offset: 3px; }
.vc-dot { color: var(--ink-3); }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 绑定：两个链接直接开始会话（去掉中间面板）
old_bind = a[a.find('    var inj = $(\'btnVaultInject\');'):]
if 'btnCChant' not in a:
    a = a.replace("  function bindPickModes() {", """  function bindVC() {
    var ch = $('btnCChant');
    if (ch && !ch.__bound) {
      ch.__bound = true;
      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        vsStart(true);                    // 符咒注入：开录音
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    }
    var ab = $('btnCAbsorb');
    if (ab && !ab.__bound) {
      ab.__bound = true;
      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        vsStart(false);                   // 意念注入：不开麦
        if ($('vaultOrb')) { $('vaultOrb').classList.add('is-flowing'); }
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    }
  }

  function bindPickModes() {""", 1)
    a = a.replace("    if (name === 'vault') { loadVault(true); bindPickModes();",
                  "    if (name === 'vault') { loadVault(true); bindVC(); bindPickModes();")

# 文案：面板/卡片里的旧名称也改
a = a.replace('符咒（录音）', '符咒注入').replace('意念吸入', '意念注入')
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '96';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok; bindVC =', 'bindVC' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '96'
d['notes'] = ['贡献能量三合一：文字「贡献能量」+「符咒注入 / 意念注入」两个选择，去掉中间面板',
              '名称改为：符咒注入、意念注入'] + [n for n in d['notes'] if '三合一' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v103_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v104_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v103', 'v104').replace('V103', 'V104'))
p = open(r'_资料\部署载荷\_shuzi_v103.ps1', encoding='utf-8').read()
p = p.replace('V103', 'V104').replace('v103', 'v104')
p = p.replace("WEB_VER = '95'", "WEB_VER = '96'").replace('APPJS_WEBVER95', 'APPJS_WEBVER96')
p = p.replace('"web": "95"', '"web": "96"').replace('LIVE_VERSION95', 'LIVE_VERSION96')
open(r'_资料\部署载荷\_shuzi_v104.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 96 / v104 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
