# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 删掉能量仓页那三个文字链接
i = h.find('<div class="vc-row" id="vcRow">')
assert i > 0
end = h.find('</div>', i) + len('</div>')
h = h[:i] + h[end:]

# ② 能量仓页只放「贡献能量」两种方式
hero = h.find('<section class="card vault-hero">')
hero_end = h.find('</section>', hero) + len('</section>')
row = '''
        <div class="vc-row" id="vcRow">
          <span class="vc-label">贡献能量</span>
          <button type="button" class="vc-link" id="btnVChant">符咒注入</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnVAbsorb">意念注入</button>
        </div>'''
h = h[:hero_end] + row + h[hero_end:]

# ③ 补充能量页：两个方式（咒语注入 / 意念注入）
old_use = '''      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCEnergy">补充能量</button>
        </div>
      </section>'''
assert old_use in h
h = h.replace(old_use, '''      <section class="card">
        <div class="vc-row">
          <button type="button" class="btn btn-primary" id="btnCEnergy">咒语注入</button>
          <button type="button" class="btn btn-ghost" id="btnCEnergySilent">意念注入</button>
        </div>
        <p class="fineprint fineprint-dim">咒语会开录音；意念不需要麦克风。</p>
      </section>''')

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027r', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

if 'btnVChant' not in a:
    a = a.replace("  function bindNavEntries() {", """  function bindVaultContrib() {
    function start(purpose, mic) {
      vs.purpose = purpose;
      attachVsCard('screen-vault');
      if ($('vsTitle')) { $('vsTitle').textContent = '贡献能量'; }
      if ($('lbEnergy')) { $('lbEnergy').textContent = '本次贡献'; }
      if ($('lbCost')) { $('lbCost').textContent = '累计贡献'; }
      if (!mic && $('cosmicFx')) { $('cosmicFx').classList.add('on'); }
      vsStart(mic);
    }
    var c = $('btnVChant');
    if (c && !c.__vb) { c.__vb = true; c.addEventListener('click', function () { start('contribute', true); }); }
    var ab = $('btnVAbsorb');
    if (ab && !ab.__vb) { ab.__vb = true; ab.addEventListener('click', function () { start('absorb', false); }); }
    var es = $('btnCEnergySilent');
    if (es && !es.__vb) {
      es.__vb = true;
      es.addEventListener('click', function () {
        attachVsCard('screen-use');
        if ($('vsTitle')) { $('vsTitle').textContent = '补充能量'; }
        if ($('lbEnergy')) { $('lbEnergy').textContent = '本次我的能量'; }
        if ($('lbCost')) { $('lbCost').textContent = '本次扣共享'; }
        vs.purpose = 'energy';
        vsStart(false);
      });
    }
  }

  function bindNavEntries() {""", 1)
    a = a.replace("    if (name === 'vault') { bindNavEntries(); loadVault(true);",
                  "    if (name === 'vault') { bindVaultContrib(); bindNavEntries(); loadVault(true);")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '117';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '117'
d['notes'] = ['能量仓只保留贡献能量（符咒注入/意念注入）；补充能量页恢复咒语注入/意念注入两种方式'] + [
    n for n in d['notes'] if '能量仓只保留贡献' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v125_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v126_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v125','v126').replace('V125','V126'))
p = open(r'_资料\部署载荷\_shuzi_v125.ps1', encoding='utf-8').read()
p = p.replace('V125','V126').replace('v125','v126').replace("WEB_VER = '116'","WEB_VER = '117'").replace('APPJS_WEBVER116','APPJS_WEBVER117').replace('"web": "116"','"web": "117"').replace('LIVE_VERSION116','LIVE_VERSION117')
open(r'_资料\部署载荷\_shuzi_v126.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 117 ready')
