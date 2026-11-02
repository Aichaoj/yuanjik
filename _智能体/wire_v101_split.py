# -*- coding: utf-8 -*-
"""v101：贡献能量 / 补充能量 拆成两个独立页面（会话卡按需移入当前页）"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 从能量仓页移除两行入口
row1_start = h.find('        <div class="vc-row" id="vcRow">')
assert row1_start > 0
row1_end = h.find('</div>', row1_start) + len('</div>')
h = h[:row1_start] + h[row1_end:]
row2_start = h.find('        <div class="vc-row" id="vcRow2">')
if row2_start > 0:
    row2_end = h.find('</div>', row2_start) + len('</div>')
    h = h[:row2_start] + h[row2_end:]

# ② 新两页（放在能量仓屏之前）
anchor = '    <!-- ═══ v61 空间能量仓'
assert anchor in h
pages = '''    <!-- v101：贡献能量（独立页） -->
    <section class="screen" id="screen-contribute" aria-labelledby="contribute-title" hidden>
      <h1 class="screen-title" id="contribute-title">贡献能量</h1>
      <p class="screen-desc">把能量送进共享仓：每满 5 分钟自动 +10。念咒或静心都可。</p>
      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCChant">符咒注入</button>
          <button type="button" class="btn btn-ghost" id="btnCAbsorb">意念注入</button>
        </div>
        <p class="fineprint fineprint-dim">符咒会开录音；意念不需要麦克风。音频只在本机分析，不上传。</p>
      </section>
    </section>

    <!-- v101：补充能量（独立页） -->
    <section class="screen" id="screen-use" aria-labelledby="use-title" hidden>
      <h1 class="screen-title" id="use-title">补充能量</h1>
      <p class="screen-desc">给自己补：每次 ≤15 分钟、每天 2 次；每次共享能量 −1、我的能量 +10。</p>
      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCEnergy">补充能量</button>
        </div>
      </section>
    </section>

'''
h = h.replace(anchor, pages + anchor)

# ③ 音疗入口：贡献/补充两张卡
old_entry = '''        <button type="button" class="entry-card" id="btnGoComfort">
          <span class="entry-title">减缓疼痛</span>
          <span class="entry-sub">在立体人体上点选痛处，再开始接收能量（放松练习，不是止痛治疗）</span>
        </button>'''
assert old_entry in h
h = h.replace(old_entry, '''        <button type="button" class="entry-card" id="btnGoComfort">
          <span class="entry-title">减缓疼痛</span>
          <span class="entry-sub">在立体人体上点选痛处，再开始接收能量（放松练习，不是止痛治疗）</span>
        </button>
        <button type="button" class="entry-card" id="btnGoContribute">
          <span class="entry-title">贡献能量</span>
          <span class="entry-sub">符咒注入 / 意念注入 · 每 5 分钟 +10</span>
        </button>
        <button type="button" class="entry-card" id="btnGoUse">
          <span class="entry-title">补充能量</span>
          <span class="entry-sub">给自己补 · 每天 2 次、每次 ≤15 分钟</span>
        </button>''')

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027f', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 视图注册
a = a.replace("'music', 'energy', 'breath', 'vault'];", "'music', 'energy', 'breath', 'vault', 'contribute', 'use'];")

# 会话卡跟随当前页
if 'function attachVsCard' not in a:
    a = a.replace("  function bindVC() {", """  function attachVsCard(screenId) {
    var card = $('vsCard');
    var scr = $(screenId);
    if (card && scr && card.parentNode !== scr) { scr.appendChild(card); }
    if (card) { card.hidden = false; }
  }

  function bindVC() {""", 1)

# 贡献/补充的启动：把会话卡移到对应页再开始
a = a.replace("""      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        vsStart(true);""",
"""      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        vsStart(true);""")
a = a.replace("""      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        vsStart(false);""",
"""      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        attachVsCard('screen-contribute');
        vsStart(false);""")
a = a.replace("""      e.addEventListener('click', function () { start('energy'); });""",
              """      e.addEventListener('click', function () { attachVsCard('screen-use'); start('energy'); });""")

# 入口绑定
if 'btnGoContribute' not in a:
    a = a.replace("    var cm = $('btnGoComfort');", """    var gc = $('btnGoContribute');
    if (gc && !gc.__bound) { gc.__bound = true; gc.addEventListener('click', function () { showView('contribute'); }); }
    var gu = $('btnGoUse');
    if (gu && !gu.__bound) { gu.__bound = true; gu.addEventListener('click', function () { showView('use'); }); }
    var cm = $('btnGoComfort');""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '101';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '101'
d['notes'] = ['贡献能量与补充能量拆成两个独立页面（音疗入口各一张卡）'] + [
    n for n in d['notes'] if '拆成两个独立页面' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v108_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v109_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v108', 'v109').replace('V108', 'V109'))
p = open(r'_资料\部署载荷\_shuzi_v108.ps1', encoding='utf-8').read()
p = p.replace('V108', 'V109').replace('v108', 'v109')
p = p.replace("WEB_VER = '100'", "WEB_VER = '101'").replace('APPJS_WEBVER100', 'APPJS_WEBVER101')
p = p.replace('"web": "100"', '"web": "101"').replace('LIVE_VERSION100', 'LIVE_VERSION101')
open(r'_资料\部署载荷\_shuzi_v109.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 101 / v109 ready')
