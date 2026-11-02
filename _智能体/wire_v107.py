# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = '<div class="card-head"><h2 class="card-title">补充能量</h2>'
assert old in h
h = h.replace(old, '<div class="card-head"><h2 class="card-title" id="vsTitle">补充能量</h2>', 1)
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027j', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('title id ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 微信内：先说清楚拿不到麦克风（微信内置浏览器不支持 getUserMedia）
if 'isWeChat' not in a:
    a = a.replace("  function bindVC() {", """  function isWeChat() {
    return /MicroMessenger/i.test(navigator.userAgent || '');
  }

  function bindVC() {""", 1)

a = a.replace("""      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        attachVsCard('screen-contribute');""",
"""      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        if (isWeChat()) {
          if ($('vsHint')) {
            $('vsHint').textContent = '微信内置浏览器拿不到麦克风：请点右上角「…」→「在浏览器打开」，' +
              '再点符咒注入；或先用「意念注入」（不需要麦克风）。';
          }
          toast('微信里录不了音：请用「浏览器打开」', 'ok');
        }""")

# 卡片标题跟着方式变
a = a.replace("""      vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        if (isWeChat()) {""",
"""      vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        if ($('vsTitle')) { $('vsTitle').textContent = '贡献能量'; }
        if (isWeChat()) {""")

a = a.replace("""  function attachVsCard(screenId) {""",
"""  function attachVsCard(screenId, title) {
    if ($('vsTitle') && title) { $('vsTitle').textContent = title; }""", 1)
a = a.replace("""    var card = $('vsCard');
    var scr = $(screenId);""", """    var card = $('vsCard');
    var scr = $(screenId);""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '107';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('wechat guard ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '107'
d['notes'] = ['微信内点击符咒注入会明确提示「用浏览器打开」；会话卡标题随方式变化'] + [n for n in d['notes'] if '微信内' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v114_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v115_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v114','v115').replace('V114','V115'))
p = open(r'_资料\部署载荷\_shuzi_v114.ps1', encoding='utf-8').read()
p = p.replace('V114','V115').replace('v114','v115').replace("WEB_VER = '106'","WEB_VER = '107'").replace('APPJS_WEBVER106','APPJS_WEBVER107').replace('"web": "106"','"web": "107"').replace('LIVE_VERSION106','LIVE_VERSION107')
open(r'_资料\部署载荷\_shuzi_v115.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 107 ready')
