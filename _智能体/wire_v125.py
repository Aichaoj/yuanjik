# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# ① 全屏光效彻底不启用（只保留页面内的宇宙块）
a = a.replace("""        if ($('cosmicFx')) {
          $('cosmicFx').classList.add('on');
          var fx = $('cosmicFx');
          var off = function () { fx.classList.remove('on'); };
          setTimeout(off, 5000);
          document.addEventListener('click', off, { once: true });
          document.addEventListener('touchstart', off, { once: true });
        }""", "        // 全屏光效已停用（只用页面内 cosmic 区块）")
a = a.replace("      if (!mic && $('cosmicFx')) { $('cosmicFx').classList.add('on'); }",
              "      if (!mic && $('cosmic')) { $('cosmic').classList.add('is-on'); }")

# ② 会话按钮统一绑定（每次进页面都绑一次，幂等）
if 'function bindSessionButtons' not in a:
    a = a.replace("  function bindVaultContrib() {", """  function bindSessionButtons() {
    function on(id, fn) {
      var el = $(id);
      if (el && !el.__sb) { el.__sb = true; el.addEventListener('click', fn); }
    }
    on('btnVsStart', function () { vsStart(true); });
    on('btnVsSilent', function () { vsStart(false); });
    on('btnVsPause', function () {
      if (!vs.running) { return; }
      var b = $('btnVsPause');
      if (vs.paused) {
        vs.paused = false;
        if (b) { b.textContent = '暂停'; }
        vs.ticker = setInterval(vsTick, 60 * 1000);
        vsStatus('进行中', true);
      } else {
        vs.paused = true;
        if (b) { b.textContent = '继续'; }
        if (vs.ticker) { clearInterval(vs.ticker); vs.ticker = null; }
        vsStatus('已暂停', false);
      }
    });
    on('btnVsStop', function () { vsFinish('本轮结束'); });
  }

  function bindVaultContrib() {""", 1)

a = a.replace("  function bindNavEntries() {", "  function bindNavEntries() {\n    bindSessionButtons();", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '125';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('session buttons bound:', 'bindSessionButtons' in a)

css = """
/* ── v125：全屏光效停用（避免遮住整页无法退出）── */
.cosmic-fx { display: none !important; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028e', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '125'
d['notes'] = ['修：符箓/意念注入后暂停、结束按钮无效（绑定改为每页都挂）',
              '修：意念注入整页遮挡无退出（全屏光效停用，只保留页内效果）'] + [
    n for n in d['notes'] if '全屏光效停用' not in n and '每页都挂' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v133_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v134_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v133','v134').replace('V133','V134'))
p = open(r'_资料\部署载荷\_shuzi_v133.ps1', encoding='utf-8').read()
p = p.replace('V133','V134').replace('v133','v134').replace("WEB_VER = '124'","WEB_VER = '125'").replace('APPJS_WEBVER124','APPJS_WEBVER125').replace('"web": "124"','"web": "125"').replace('LIVE_VERSION124','LIVE_VERSION125')
open(r'_资料\部署载荷\_shuzi_v134.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 125 ready')
