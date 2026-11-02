# -*- coding: utf-8 -*-
"""v64 前端：能量仓兑换区（两权益）+ 称号展示 + 版本号。"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """        <button type="button" class="btn btn-ghost btn-sm" id="btnGoPoints">查看积分明细</button>
      </section>"""
assert h.count(old) == 1
h = h.replace(old, """        <button type="button" class="btn btn-ghost btn-sm" id="btnGoPoints">查看积分明细</button>
        <div class="vault-perks" id="vaultPerks"></div>
      </section>""")

h = h.replace('app.js?v=20261026a', 'app.js?v=20261026b').replace('style.css?v=20261026a', 'style.css?v=20261026b')
h = h.replace('music.js?v=20261026a', 'music.js?v=20261026b').replace('energy.js?v=20261026a', 'energy.js?v=20261026b')
h = h.replace('body3d.js?v=20261026a', 'body3d.js?v=20261026b')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html perks ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_pts = """    if ($('vaultPointsChip')) {
      $('vaultPointsChip').textContent = (pts.rate || '1 能力值 = 1 积分') + (pts.expire ? ' · ' + pts.expire : '');
    }"""
assert a.count(old_pts) == 1
a = a.replace(old_pts, old_pts + """

    // v64：权益兑换（额度加成 / 称号）
    var perks = d.perks || [];
    var pbox = $('vaultPerks');
    if (pbox) {
      var bal = Number(pts.balance || 0);
      pbox.innerHTML = perks.length ? perks.map(function (p) {
        var disabled = p.owned || bal < Number(p.cost || 0);
        return '<div class="perk-row">' +
               '<div class="perk-main"><span class="perk-name">' + esc(p.name) + '</span>' +
               '<span class="perk-note">' + esc(p.note || '') + '</span></div>' +
               '<button type="button" class="btn btn-ghost btn-sm" data-perk="' + esc(p.item) + '"' +
               (disabled ? ' disabled' : '') + '>' +
               (p.owned ? '已拥有' : (esc(p.cost) + ' 积分兑换')) + '</button></div>';
      }).join('') : '<p class="placeholder">暂无可兑换权益</p>';
    }
    var mineTitle = (d.mine || {}).title || '';
    if (mineTitle && $('vaultHint')) {
      $('vaultHint').textContent = '我的称号：' + mineTitle + '。' + (d.note || '');
    }""")

old_bind = """    var gp = $('btnGoPoints');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var pk = $('vaultPerks');
    if (pk && !pk.__bound) {
      pk.__bound = true;
      pk.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== pk && !(el.getAttribute && el.getAttribute('data-perk'))) { el = el.parentNode; }
        if (!el || el === pk) { return; }
        var item = el.getAttribute('data-perk');
        if (!window.confirm('确定用积分兑换「' + item + '」权益？')) { return; }
        el.disabled = true;
        apiFetch('/vault/redeem', { method: 'POST', body: { item: item } })
          .then(function (env) {
            var d2 = env.data || {};
            toast('兑换成功，扣 ' + (d2.cost || 0) + ' 积分（余额 ' + (d2.points_balance || 0) + '）', 'ok');
            return loadVault(true);
          }).catch(function (err) {
            if ($('vaultHint')) { $('vaultHint').textContent = '兑换失败：' + readableError(err); }
          }).then(function () { el.disabled = false; });
      });
    }
    var gp = $('btnGoPoints');""")

# 榜单显示称号
a = a.replace("""                 '<span class="vb-name">' + esc(x.label) + '</span>' +""",
"""                 '<span class="vb-name">' + esc(x.label) +
                 (x.title ? '<i class="vb-title">' + esc(x.title) + '</i>' : '') + '</span>' +""")

a = a.replace("var WEB_VER = '63';", "var WEB_VER = '64';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js perks ok')

css = """
/* ── v64 权益兑换与称号 ───────────────────────────────────── */
.vault-perks { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.perk-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px dashed var(--line); }
.perk-main { flex: 1 1 auto; display: flex; flex-direction: column; gap: 2px; }
.perk-name { font-size: 13.5px; font-weight: 600; }
.perk-note { font-size: 11.5px; color: var(--ink-3); }
.vb-title { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 8px;
  background: #fdf0e6; color: #b5764a; font-size: 10.5px; font-style: normal; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
