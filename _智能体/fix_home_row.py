# -*- coding: utf-8 -*-
p = r'shuzi\web\index.html'
s = open(p, encoding='utf-8').read()
old = """        <div id="homeDailyBody">
          <p class="placeholder">正在读取今日指数…</p>
        </div>"""
assert s.count(old) == 1
s = s.replace(old, old + """
        <button type="button" class="idx-energy" id="homeEnergyRow" hidden>
          <span class="idx-energy-label">今日能量指数</span>
          <span class="idx-energy-val" id="homeEnergyVal">—</span>
          <span class="idx-energy-band" id="homeEnergyBand"></span>
          <span class="idx-energy-arrow" aria-hidden="true">›</span>
        </button>""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('re-inserted homeEnergyRow')
