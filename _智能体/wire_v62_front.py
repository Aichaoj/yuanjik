# -*- coding: utf-8 -*-
"""v62 前端：① 贡献榜  ② 后台上传控件  ③ 积分评审稿另写文档。"""

# ══ 1) index.html：贡献榜区块 ═══════════════════════════════════
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = """      <section class="card">
        <div class="card-head"><h2 class="card-title">积分奖励（后期开放）</h2></div>"""
assert h.count(old) == 1
h = h.replace(old, """      <section class="card">
        <div class="card-head"><h2 class="card-title">贡献榜</h2>
          <span class="chip chip-quiet" id="vaultMyRank">—</span></div>
        <div id="vaultBoard" class="vault-board"><p class="placeholder">正在读取…</p></div>
        <p class="fineprint fineprint-dim">只显示昵称（或脱敏标识）与贡献值，不显示手机号与会员号。</p>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="card-title">积分奖励（后期开放）</h2></div>""")

h = h.replace('app.js?v=20261025d', 'app.js?v=20261025e').replace('style.css?v=20261025d', 'style.css?v=20261025e')
h = h.replace('music.js?v=20261025d', 'music.js?v=20261025e').replace('energy.js?v=20261025d', 'energy.js?v=20261025e')
h = h.replace('body3d.js?v=20261025d', 'body3d.js?v=20261025e')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html: leaderboard block ok')

# ══ 2) app.js：榜单读取与渲染 ══════════════════════════════════
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
old_load = """    return Promise.all([
      apiFetch('/vault/status').then(function (env) { return env.data || {}; }, function () { return null; }),
      apiFetch('/vault/ledger').then(function (env) { return env.data || {}; }, function () { return null; })
    ]).then(function (rs) {
      var st = rs[0], lg = rs[1];
      if (st) { renderVault(st); }"""
assert a.count(old_load) == 1
a = a.replace(old_load, """    return Promise.all([
      apiFetch('/vault/status').then(function (env) { return env.data || {}; }, function () { return null; }),
      apiFetch('/vault/ledger').then(function (env) { return env.data || {}; }, function () { return null; }),
      apiFetch('/vault/leaderboard', { query: { limit: 10 } })
        .then(function (env) { return env.data || {}; }, function () { return null; })
    ]).then(function (rs) {
      var st = rs[0], lg = rs[1], lb = rs[2];
      if (st) { renderVault(st); }
      if (lb && $('vaultBoard')) {
        var items = lb.items || [];
        $('vaultBoard').innerHTML = items.length ? items.map(function (x) {
          var me = (lb.mine && x.label && x.rank && lb.mine.rank === x.rank) ? ' is-me' : '';
          return '<div class="vb-row' + me + '">' +
                 '<span class="vb-rank r' + (x.rank <= 3 ? x.rank : 'n') + '">' + esc(x.rank) + '</span>' +
                 '<span class="vb-name">' + esc(x.label) + '</span>' +
                 '<span class="vb-val">' + vaultFmt(x.contribution) + '</span></div>';
        }).join('') : '<p class="placeholder">还没有人注入，做第一个吧。</p>';
        if ($('vaultMyRank')) {
          $('vaultMyRank').textContent = (lb.mine && lb.mine.rank)
            ? ('我的第 ' + lb.mine.rank + ' 名') : '我还没上榜';
        }
      }""")

# 注入成功后也刷新榜单（loadVault 已含）
a = a.replace("var WEB_VER = '61';", "var WEB_VER = '62';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js: leaderboard ok')

# ══ 3) 后台页：分片上传控件 ════════════════════════════════════
M = r'shuzi\web\admin\music.html'
m = open(M, encoding='utf-8').read()
old_file = """    <label for="fFile">文件（music/ 下的相对路径，或 https 地址）</label>
    <input id="fFile" placeholder="music/xxx.ogg">"""
assert m.count(old_file) == 1
m = m.replace(old_file, """    <label for="fFile">文件（music/ 下的相对路径，或 https 地址）</label>
    <input id="fFile" placeholder="music/xxx.ogg">
    <label>或直接上传音频（≤20 MB，自动分片，绕开单请求限制）</label>
    <div class="toolbar" style="margin-top:0">
      <input type="file" id="upFile" accept="audio/*" style="max-width:260px">
      <button class="small" id="btnUpload">上传</button>
      <span class="msg" id="upMsg"></span>
    </div>
    <progress id="upBar" value="0" max="100" style="width:100%;display:none"></progress>""")

old_js = """  $('btnLogin').addEventListener('click', login);"""
assert m.count(old_js) == 1
up_js = """  function b64(buf) {
    var bytes = new Uint8Array(buf), s = '', i;
    for (i = 0; i < bytes.length; i += 0x8000) {
      s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(s);
  }

  function uploadAudio() {
    var f = $('upFile').files && $('upFile').files[0];
    if (!f) { msg($('upMsg'), '先选一个音频文件', true); return; }
    if (f.size > 20 * 1024 * 1024) { msg($('upMsg'), '文件超过 20 MB', true); return; }
    var bar = $('upBar');
    bar.style.display = 'block'; bar.value = 0;
    msg($('upMsg'), '开始上传：' + f.name + '（' + Math.round(f.size / 1024) + ' KB）');
    call('/music/upload/begin', { filename: f.name, size: f.size }).then(function (x) {
      if (x.status !== 200) { throw new Error((x.j && x.j.message) || 'begin 失败'); }
      var uid = x.j.data.upload_id;
      var chunkMax = x.j.data.chunk_max || 2097152;
      var chunks = Math.ceil(f.size / chunkMax);
      var seq = 0;
      function next() {
        if (seq >= chunks) { return finish(uid); }
        var start = seq * chunkMax, end = Math.min(f.size, start + chunkMax);
        var slice = f.slice(start, end);
        return new Promise(function (res, rej) {
          var fr = new FileReader();
          fr.onload = function () { res(fr.result.split(',')[1]); };
          fr.onerror = rej;
          fr.readAsDataURL(slice);
        }).then(function (data) {
          return call('/music/upload/chunk', { upload_id: uid, seq: seq, data_b64: data });
        }).then(function (y) {
          if (y.status !== 200) { throw new Error((y.j && y.j.message) || ('分片 ' + seq + ' 失败')); }
          seq++;
          bar.value = Math.round(seq / chunks * 100);
          msg($('upMsg'), '已传 ' + seq + '/' + chunks + ' 片');
          return next();
        });
      }
      function finish(id) {
        return call('/music/upload/finish', { upload_id: id }).then(function (z) {
          if (z.status !== 200) { throw new Error((z.j && z.j.message) || 'finish 失败'); }
          $('fFile').value = z.j.data.file;
          msg($('upMsg'), '上传完成：' + z.j.data.file + '（' + z.j.data.bytes + ' 字节）');
          bar.value = 100;
        });
      }
      return next();
    }).catch(function (e) {
      msg($('upMsg'), '上传失败：' + e.message, true);
      bar.style.display = 'none';
    });
  }

  $('btnLogin').addEventListener('click', login);
  $('btnUpload').addEventListener('click', uploadAudio);"""
m = m.replace(old_js, up_js)
open(M, 'w', encoding='utf-8', newline='\n').write(m)
print('admin: upload ui ok')
