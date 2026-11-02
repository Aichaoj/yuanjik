# -*- coding: utf-8 -*-
"""v67 前端：使用能量卡改版（场景/痛处、15 分钟、每天 2 次、共享-1/我+10）+ 我的能量卡 + 波次增强"""

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 1) 整块替换旧会话卡
start = h.index('      <section class="card vault-session" id="vsCard">')
end = h.index('      <section class="card vault-points-card">')
new_card = '''      <!-- 使用能量（v67）：场景可选「补充能量 / 舒缓不适（意念痛处）」；每次 ≤15 分钟、每天 2 次；
           每次 共享能量 −1、我的能量 +10；音频只在本机分析，不上传。 -->
      <section class="card vault-session" id="vsCard">
        <div class="card-head"><h2 class="card-title">使用能量</h2>
          <span class="chip chip-quiet" id="vsState">未开始</span></div>
        <p class="vs-desc">开启录音后，念咒语或安静待着都可以。音频只在本机分析音量，<strong>不上传、不保存</strong>。
          每次 <strong>≤15 分钟</strong>、每天 <strong>2 次</strong>；每次 <strong>共享能量 −1</strong>、<strong>我的能量 +10</strong>。</p>

        <div class="vs-purpose" id="vsPurpose">
          <button type="button" class="chip is-on" data-purpose="energy">补充能量</button>
          <button type="button" class="chip" data-purpose="comfort">舒缓不适（意念痛处）</button>
        </div>
        <div class="chip-row vs-spots" id="vsSpots" hidden>
          <span class="vs-spot-label">把意念放在：</span>
          <button type="button" class="chip" data-spot="头部">头部</button>
          <button type="button" class="chip" data-spot="颈肩">颈肩</button>
          <button type="button" class="chip" data-spot="腰背">腰背</button>
          <button type="button" class="chip" data-spot="关节">关节</button>
          <button type="button" class="chip" data-spot="腹部">腹部</button>
          <button type="button" class="chip" data-spot="其他">其他</button>
        </div>
        <p class="fineprint fineprint-dim vs-disclaim" id="vsDisclaim" hidden>
          舒缓不适是放松与注意力练习，<strong>不是止痛治疗</strong>；疼痛持续、加重或伴随其他症状，请及时就医。
        </p>

        <div class="vs-grid">
          <div class="vs-cell"><b id="vsMin">0</b><span>分钟</span></div>
          <div class="vs-cell"><b id="vsEnergy">0</b><span>本次我的能量</span></div>
          <div class="vs-cell"><b id="vsShared">—</b><span>共享能量</span></div>
          <div class="vs-cell"><b id="vsCost">0</b><span>本次扣共享</span></div>
        </div>
        <div class="vs-actions">
          <button type="button" class="btn btn-primary" id="btnVsStart">开始（开启录音）</button>
          <button type="button" class="btn btn-ghost" id="btnVsSilent">静默模式</button>
          <button type="button" class="btn btn-ghost" id="btnVsStop" hidden>结束本轮</button>
        </div>
        <p class="fineprint fineprint-dim" id="vsHint">今天还可以用 2 次。</p>
      </section>

      <!-- 我的能量（v67）：个人能量值与今日剩余次数 -->
      <section class="card vault-myenergy" id="myEnergyCard">
        <div class="card-head"><h2 class="card-title">我的能量</h2>
          <span class="chip chip-quiet" id="myEnergySessions">今日 0/2</span></div>
        <p class="myenergy-num"><span id="myEnergyValue">0</span> <span class="myenergy-unit">能量值</span></p>
        <p class="fineprint fineprint-dim" id="myEnergyHint">
          注入与使用都会累加到「我的能量」；使用能量时共享仓 −1、我的能量 +10（每天 2 次、每次 ≤15 分钟）。
        </p>
      </section>

'''
h = h[:start] + new_card + h[end:]

# 2) 波次：从 3 圈加到 5 圈（HTML 里 orb 的 i 元素）
old_orb = '<div class="vault-orb" id="vaultOrb" aria-hidden="true"><i></i><i></i><i></i></div>'
assert h.count(old_orb) == 1
h = h.replace(old_orb, '<div class="vault-orb" id="vaultOrb" aria-hidden="true">' +
                       '<i></i><i></i><i></i><i></i><i></i></div>')

h = h.replace('app.js?v=20261026e', 'app.js?v=20261026f').replace('style.css?v=20261026e', 'style.css?v=20261026f')
h = h.replace('music.js?v=20261026e', 'music.js?v=20261026f').replace('energy.js?v=20261026e', 'energy.js?v=20261026f')
h = h.replace('body3d.js?v=20261026e', 'body3d.js?v=20261026f')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html v67 ok')
