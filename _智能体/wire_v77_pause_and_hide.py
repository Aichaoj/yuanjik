# -*- coding: utf-8 -*-
"""v77：① 补充能量加「暂停/继续」 ② 删除能量指数页面的技术模型参数（对外不显示）"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 暂停键
old_act = """        <div class="vs-actions">
          <button type="button" class="btn btn-primary" id="btnVsStart">开始（开启录音）</button>
          <button type="button" class="btn btn-ghost" id="btnVsSilent">静默模式</button>
          <button type="button" class="btn btn-ghost" id="btnVsStop" hidden>结束本轮</button>
        </div>"""
assert h.count(old_act) == 1
h = h.replace(old_act, """        <div class="vs-actions">
          <button type="button" class="btn btn-primary" id="btnVsStart">开始（开启录音）</button>
          <button type="button" class="btn btn-ghost" id="btnVsSilent">静默模式</button>
          <button type="button" class="btn btn-ghost" id="btnVsPause" hidden>暂停</button>
          <button type="button" class="btn btn-ghost" id="btnVsStop" hidden>结束本轮</button>
        </div>""")

# ② 删除技术参数文案（我的能量指数卡）
old_hint = """        <p class="fineprint fineprint-dim" id="mineEnergyHint">
          0–1000 刻度，200 为「需要补充」线；按出生时空五行（气机升降）+ 参与度 + 今日补充 + 昼夜节律生成。
        </p>"""
assert h.count(old_hint) == 1
h = h.replace(old_hint, "")

# ② 删除「规则」按钮与规则块（含公式与内部参数）
old_rule_btn = """          <button type="button" class="btn btn-ghost btn-sm" id="btnEnergyRule">规则</button></div>"""
assert h.count(old_rule_btn) == 1
h = h.replace(old_rule_btn, "</div>")
start = h.find('        <div class="energy-rule" id="energyRule" hidden>')
if start >= 0:
    end = h.find('</div>', h.find('</div>', h.find('energy-bands', start)) )
    # 找到该块的结束标签：按注释/换行定位到 </div> 之后再一刀
    tail = h.find('        <p class="fineprint fineprint-dim">只作体验读法', start)
    if tail > 0:
        cut_end = h.find('</div>', tail)
        h = h[:start] + h[cut_end + len('</div>'):] if cut_end > 0 else h

h = h.replace('app.js?v=20261026p', 'app.js?v=20261026q').replace('style.css?v=20261026p', 'style.css?v=20261026q')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok; energyRule left =', 'energyRule' in h)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 暂停/继续
a = a.replace("""    var s3 = $('btnVsStop');""", """    var s4 = $('btnVsPause');
    if (s4 && !s4.__bound) {
      s4.__bound = true;
      s4.addEventListener('click', function () {
        if (!vs.running) { return; }
        if (vs.paused) {
          vs.paused = false;
          s4.textContent = '暂停';
          vs.ticker = setInterval(vsTick, 60 * 1000);
          vsStatus('进行中', true);
          if ($('vsHint')) { $('vsHint').textContent = '继续中……'; }
        } else {
          vs.paused = true;
          s4.textContent = '继续';
          if (vs.ticker) { clearInterval(vs.ticker); vs.ticker = null; }
          vsStatus('已暂停', false);
          if ($('vsHint')) { $('vsHint').textContent = '已暂停：这一轮不计时、不结算，点「继续」接着走。'; }
        }
      });
    }
    var s3 = $('btnVsStop');""")
a = a.replace("timeline = null", "timeline = null")  # no-op

# 开始/结束时显示/隐藏暂停键
a = a.replace("      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }",
              "      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }\n      if ($('btnVsPause')) { $('btnVsPause').hidden = false; $('btnVsPause').textContent = '暂停'; }")
a = a.replace("    if ($('btnVsStop')) { $('btnVsStop').hidden = true; }",
              "    if ($('btnVsStop')) { $('btnVsStop').hidden = true; }\n    if ($('btnVsPause')) { $('btnVsPause').hidden = true; }\n    vs.paused = false;")

# 暂停状态初始化
a = a.replace("var recState = { items: [], i: 0, audio: null };",
              "var recState = { items: [], i: 0, audio: null };")
a = a.replace("  var vs = { purpose: 'energy', spot: '',", "  var vs = { paused: false, purpose: 'energy', spot: '',")

# tick 里跳过暂停
a = a.replace("  function vsTick() {\n    if (!vs.running || !vs.sid) { return; }",
              "  function vsTick() {\n    if (!vs.running || !vs.sid || vs.paused) { return; }")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '77';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '77'
d['notes'] = ['补充能量新增「暂停/继续」：暂停期间不计时、不结算',
              '能量指数页面不再显示任何模型内部参数（公式/系数/时段阈值一律不对外）'] + [
    n for n in d['notes'] if '暂停' not in n and '内部参数' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web 77')
