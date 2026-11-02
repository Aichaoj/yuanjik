# -*- coding: utf-8 -*-
"""v75（方案 A）：立体图"壳"升级 —— 星空背景 + 左右两列按钮 + 脚下光环平台（不动人体模型）"""
import json

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 1) 按钮改左右两列（保持原 id，JS 绑定不用改）
old_actions = """        <div class="body-actions">
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyMode">切到立体图</button>
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyTurn">转身</button>
          <button type="button" class="btn btn-primary" id="btnBodyInject">注入</button>
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyMute">静音</button>
          <button type="button" class="btn btn-ghost btn-sm" id="btnBodyReset">重选</button>
        </div>"""
assert h.count(old_actions) == 1
new_actions = """        <div class="body-actions">
          <div class="body-col body-col-left">
            <button type="button" class="btn-orb btn-orb-primary" id="btnBodyInject"><i>◈</i>注入</button>
            <button type="button" class="btn-orb" id="btnBodyReset"><i>⟲</i>重选</button>
          </div>
          <div class="body-col body-col-right">
            <button type="button" class="btn-orb" id="btnBodyMode"><i>◇</i>立体图</button>
            <button type="button" class="btn-orb" id="btnBodyTurn"><i>↻</i>转身</button>
            <button type="button" class="btn-orb" id="btnBodyMute"><i>♪</i>静音</button>
          </div>
        </div>"""
h = h.replace(old_actions, new_actions)

# 2) 星空 + 平台光环：给舞台加两层装饰
old_stage = """        <div class="body3d-stage" id="body3dStage" hidden>
          <canvas id="body3dCanvas"></canvas>"""
assert h.count(old_stage) == 1
new_stage = """        <div class="body3d-stage" id="body3dStage" hidden>
          <div class="stage-stars" aria-hidden="true"></div>
          <canvas id="body3dCanvas"></canvas>
          <div class="stage-platform" aria-hidden="true"><i></i><i></i><i></i></div>"""
h = h.replace(old_stage, new_stage)

h = h.replace('body3d.js?v=20261026j', 'body3d.js?v=20261026p')
h = h.replace('app.js?v=20261026n', 'app.js?v=20261026p')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html shell ok')

css = """
/* ── v75 立体图舞台：星空 + 光环平台 + 左右按钮 ───────────── */
.body3d-stage { position: relative; background:
  radial-gradient(120% 90% at 50% 0%, #0b1b33 0%, #071224 55%, #040910 100%); }
.stage-stars { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.stage-stars::before, .stage-stars::after {
  content: ''; position: absolute; inset: -40%;
  background-image:
    radial-gradient(1.6px 1.6px at 20% 30%, #fff 50%, transparent 51%),
    radial-gradient(1.4px 1.4px at 70% 18%, #cfe6ff 50%, transparent 51%),
    radial-gradient(1.8px 1.8px at 42% 62%, #fff 50%, transparent 51%),
    radial-gradient(1.2px 1.2px at 84% 74%, #bcd7ff 50%, transparent 51%),
    radial-gradient(1.5px 1.5px at 12% 82%, #fff 50%, transparent 51%),
    radial-gradient(1.3px 1.3px at 58% 44%, #e8f2ff 50%, transparent 51%);
  background-size: 220px 220px, 260px 260px, 300px 300px, 240px 240px, 320px 320px, 280px 280px;
  opacity: .75; animation: starDrift 60s linear infinite;
}
.stage-stars::after { background-size: 160px 160px; opacity: .45; animation-duration: 90s; animation-direction: reverse; }
@keyframes starDrift { from { transform: translate3d(0,0,0) } to { transform: translate3d(-60px,-40px,0) } }
.stage-platform { position: absolute; left: 50%; bottom: 3%; transform: translateX(-50%);
  width: 62%; height: 84px; pointer-events: none; }
.stage-platform i { position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
  border-radius: 50%; border: 1px solid rgba(120, 220, 255, .35); }
.stage-platform i:nth-child(1) { width: 100%; height: 54px; box-shadow: 0 0 22px rgba(90,200,255,.35) inset; }
.stage-platform i:nth-child(2) { width: 66%; height: 34px; border-color: rgba(120,220,255,.5); }
.stage-platform i:nth-child(3) { width: 34%; height: 18px; background: radial-gradient(circle, rgba(150,240,255,.75), rgba(90,200,255,0) 70%); border: 0; }
.body3d-stage canvas { position: relative; z-index: 1; }
.body-actions { position: absolute; inset: 0; pointer-events: none; z-index: 2; }
.body-col { position: absolute; top: 10px; display: flex; flex-direction: column; gap: 8px; pointer-events: auto; }
.body-col-left { left: 8px; }
.body-col-right { right: 8px; }
.btn-orb { display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 20px;
  border: 1px solid rgba(255, 186, 92, .55); color: #ffe9c9;
  background: linear-gradient(180deg, rgba(90,60,20,.85), rgba(40,26,10,.9));
  font: inherit; font-size: 12.5px; cursor: pointer; backdrop-filter: blur(3px); }
.btn-orb i { font-style: normal; opacity: .9; }
.btn-orb-primary { border-color: #ffc46b; color: #fff4e2;
  background: linear-gradient(180deg, #d98a2b, #a55f16); box-shadow: 0 4px 14px rgba(217,138,43,.35); }
.btn-orb:disabled { opacity: .5; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css shell ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '75'
d['notes'] = ['立体图升级（方案A）：星空背景 + 脚下光环平台 + 左右两列圆角按钮（注入/重选 左，立体图/转身/静音 右）'] + [
    n for n in d['notes'] if '星空' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
import re
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '75';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('web 75')
