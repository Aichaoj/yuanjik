# -*- coding: utf-8 -*-
"""v82：我的页「空间能量仓」入口可点（之前绑在错的钩子上）+ 金色动态卡面"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = """        <button type="button" class="entry-card" id="btnMineVault" style="width:100%">
          <span class="entry-title">空间能量仓</span>
          <span class="entry-sub">贡献能量 · 看共享能量指数 · 我的次数与总能力值</span>
        </button>"""
assert h.count(old) == 1
new = """        <button type="button" class="entry-card mine-vault" id="btnMineVault" style="width:100%">
          <span class="mv-emblem" aria-hidden="true">✦</span>
          <span class="mv-text">
            <span class="entry-title">空间能量仓</span>
            <span class="entry-sub">贡献能量 · 看共享能量指数 · 我的次数与总能力值</span>
          </span>
          <span class="mv-arrow" aria-hidden="true">›</span>
        </button>"""
h = h.replace(old, new)
h = h.replace('style.css?v=20261026q', 'style.css?v=20261026r')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

css = """
/* ── v82 我的页「空间能量仓」金色动态卡 ───────────────────── */
.mine-vault { position: relative; display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 14px 14px; border-radius: 14px; border: 1px solid rgba(206, 160, 62, .55);
  background:
    linear-gradient(115deg, rgba(255,246,222,.95), rgba(255,233,190,.9) 40%, rgba(255,247,228,.95) 60%, rgba(255,236,199,.92)),
    #fffaf0;
  overflow: hidden; cursor: pointer; text-align: left; font: inherit; }
.mine-vault::after { content: ''; position: absolute; top: -60%; bottom: -60%; left: -35%; width: 28%;
  background: linear-gradient(100deg, rgba(255,255,255,0), rgba(255,255,255,.85), rgba(255,255,255,0));
  transform: skewX(-18deg); animation: mvShine 3.6s ease-in-out infinite; pointer-events: none; }
@keyframes mvShine { 0% { left: -40%; } 55% { left: 120%; } 100% { left: 120%; } }
.mv-emblem { flex: 0 0 auto; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
  font-size: 18px; color: #7a4d06;
  background: radial-gradient(circle at 32% 28%, #fff5cf, #f0c568 55%, #c8901f);
  box-shadow: 0 0 0 3px rgba(255,220,150,.55), 0 4px 14px rgba(200,144,31,.35);
  animation: mvPulse 2.8s ease-in-out infinite; }
@keyframes mvPulse { 0%,100% { box-shadow: 0 0 0 3px rgba(255,220,150,.45), 0 4px 14px rgba(200,144,31,.28); }
  50% { box-shadow: 0 0 0 6px rgba(255,220,150,.28), 0 6px 20px rgba(200,144,31,.45); } }
.mv-text { flex: 1 1 auto; display: flex; flex-direction: column; gap: 3px; }
.mine-vault .entry-title { color: #6b4404; font-weight: 700; }
.mine-vault .entry-sub { color: #9a6f22; }
.mv-arrow { flex: 0 0 auto; color: #b8862c; font-size: 18px; }
.mine-vault:active { transform: scale(.995); }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
# 在「我的」页加载时绑定（之前绑在 vault 钩子里，我的页点不到）
old_hook = "  function loadMineEnergy() {"
assert old_hook in a
a = a.replace(old_hook, """  function bindMineVault() {
    var mv = $('btnMineVault');
    if (mv && !mv.__bound) {
      mv.__bound = true;
      mv.addEventListener('click', function (ev) {
        ev.preventDefault();
        showView('vault');
      });
    }
  }

  function loadMineEnergy() {
    bindMineVault();""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '82';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '82'
d['notes'] = ['我的页「空间能量仓」入口修好点击，并改成金色动态卡（流光 + 呼吸光晕）'] + [
    n for n in d['notes'] if '金色动态' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

T = r'_智能体\deploy\_tool_v89_run.py'
t = open(T, encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v90_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v89', 'v90').replace('V89', 'V90'))

P = r'_资料\部署载荷\_shuzi_v89.ps1'
p = open(P, encoding='utf-8').read()
p = p.replace('V89', 'V90').replace('v89', 'v90')
p = p.replace("WEB_VER = '81'", "WEB_VER = '82'").replace('APPJS_WEBVER81', 'APPJS_WEBVER82')
p = p.replace('"web": "81"', '"web": "82"').replace('LIVE_VERSION81', 'LIVE_VERSION82')
open(r'_资料\部署载荷\_shuzi_v90.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 82 / v90 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
