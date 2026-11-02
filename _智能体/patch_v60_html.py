# -*- coding: utf-8 -*-
# 1) 后台页去掉一行无用调用
p = r'shuzi\web\admin\music.html'
s = open(p, encoding='utf-8').read()
s = s.replace("    call('/music', {}) /* GET 用 POST 会被拒，下面单独走 GET */\n", "")
open(p, 'w', encoding='utf-8', newline='\n').write(s)

# 2) 主页面：器官层 chips + 呼吸节拍音
p2 = r'shuzi\web\index.html'
h = open(p2, encoding='utf-8').read()

old = """      <section class="card body-card">
        <div class="body-stage" id="bodyStage">"""
assert h.count(old) == 1
h = h.replace(old, """      <section class="card body-card">
        <div class="chip-row body-layers" id="bodyLayerChips">
          <button type="button" class="chip is-on" data-layer="part">部位</button>
          <button type="button" class="chip" data-layer="organ">器官（示意）</button>
        </div>
        <div class="body-stage" id="bodyStage">""")

old2 = """          <select class="input input-sm" id="breathScene" aria-label="呼吸场景">"""
assert h.count(old2) == 1
h = h.replace(old2, """          <select class="input input-sm" id="breathCue" aria-label="节拍音">
            <option value="off">节拍音：关</option>
            <option value="soft" selected>节拍音：轻</option>
            <option value="wood">节拍音：木鱼</option>
          </select>
          <select class="input input-sm" id="breathScene" aria-label="呼吸场景">""")

# 3) 版本与缓存键 → v60
h = h.replace('app.js?v=20261025b', 'app.js?v=20261025c').replace('style.css?v=20261025b', 'style.css?v=20261025c')
h = h.replace('music.js?v=20261025b', 'music.js?v=20261025c').replace('energy.js?v=20261025b', 'energy.js?v=20261025c')
h = h.replace('body3d.js?v=20261025b', 'body3d.js?v=20261025c')
open(p2, 'w', encoding='utf-8', newline='\n').write(h)

a = r'shuzi\web\app.js'
t = open(a, encoding='utf-8').read().replace("var WEB_VER = '59';", "var WEB_VER = '60';")
open(a, 'w', encoding='utf-8', newline='\n').write(t)
print('html/admin patched; version 60')
