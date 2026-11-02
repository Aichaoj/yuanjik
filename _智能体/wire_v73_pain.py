# -*- coding: utf-8 -*-
import json
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = """        <p class="fineprint fineprint-dim vs-disclaim" id="vsDisclaim" hidden>
          舒缓不适是放松与注意力练习，<strong>不是止痛治疗</strong>；疼痛持续、加重或伴随其他症状，请及时就医。
        </p>"""
assert h.count(old) == 1
new = """        <p class="fineprint fineprint-dim vs-disclaim" id="vsDisclaim" hidden>
          舒缓不适是放松与注意力练习，<strong>不是止痛治疗</strong>；疼痛持续、加重或伴随其他症状，请及时就医。<br>
          做法：① 把意念轻轻放在不适处，不使劲；② 跟着心跳/呼吸慢慢数；③ 结束时慢慢睁眼、喝口温水。
        </p>"""
s = h.replace(old, new)
s = s.replace('app.js?v=20261026k','app.js?v=20261026m').replace('style.css?v=20261026k','style.css?v=20261026m')
s = s.replace('music.js?v=20261026k','music.js?v=20261026m').replace('energy.js?v=20261026k','energy.js?v=20261026m')
s = s.replace('body3d.js?v=20261026k','body3d.js?v=20261026m')
open(H,'w',encoding='utf-8',newline='\n').write(s)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web']='73'; d['build']='2026-10-26'
d['notes'] = ['舒缓不适（意念痛处）加入三步做法提示；首页显示今日能量指数；能量术语统一为「贡献能量 / 补充能量」'] + [n for n in d['notes'] if '三步' not in n]
open(VJ,'w',encoding='utf-8',newline='\n').write(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('v73 ready')
