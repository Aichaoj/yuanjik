# -*- coding: utf-8 -*-
p = r'shuzi\web\index.html'
s = open(p, encoding='utf-8').read()

# 1) 在 2D 舞台之后插入 3D 舞台（默认隐藏）
old = """          <p class="body-hint" id="bodyHint">点一下想关注的位置</p>
        </div>
        <div class="body-actions">
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyTurn">转身</button>"""
new = """          <p class="body-hint" id="bodyHint">点一下想关注的位置</p>
        </div>
        <!-- v59 立体图舞台（默认隐藏；点「切到立体图」时才懒加载 three.js） -->
        <div class="body3d-stage" id="body3dStage" hidden>
          <canvas id="body3dCanvas"></canvas>
          <p class="body-hint" id="bodyHint3d">拖动可以转着看；点身上的位置选/取消</p>
        </div>
        <div class="body-actions">
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyMode">切到立体图</button>
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyTurn">转身</button>"""
assert s.count(old) == 1
s = s.replace(old, new)

# 2) 脚本：body3d.js（只有它会在需要时再去拉 three.js）
old_js = '<script src="energy.js?v=20261025a"></script>'
assert s.count(old_js) == 1
s = s.replace(old_js, old_js + '\n<script src="body3d.js?v=20261025a"></script>')

# 3) 版本与缓存键统一到 v59
s = s.replace('app.js?v=20261025a', 'app.js?v=20261025b')
s = s.replace('style.css?v=20261025a', 'style.css?v=20261025b')
s = s.replace('music.js?v=20261025a', 'music.js?v=20261025b')
s = s.replace('energy.js?v=20261025a', 'energy.js?v=20261025b')
s = s.replace('body3d.js?v=20261025a', 'body3d.js?v=20261025b')
open(p, 'w', encoding='utf-8', newline='\n').write(s)

# 4) app.js：WEB_VER 59
a = r'shuzi\web\app.js'
t = open(a, encoding='utf-8').read().replace("var WEB_VER = '58';", "var WEB_VER = '59';")
open(a, 'w', encoding='utf-8', newline='\n').write(t)
print('html/app patched')
