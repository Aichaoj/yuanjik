# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 1) 进「贡献能量」页也绑定按钮（之前只在能量仓页绑定）
if "name === 'contribute'" not in a:
    a = a.replace("    if (name === 'vault') { loadVault(true); bindVC(); bindUseModes(); bindPickModes(); bindBodyReceive();",
                  "    if (name === 'contribute') { bindVC(); }\n    if (name === 'use') { bindUseModes(); }\n    if (name === 'vault') { loadVault(true); bindVC(); bindUseModes(); bindPickModes(); bindBodyReceive();")

# 2) 符咒注入：在点击手势里直接取麦（避免被浏览器拦），拿到流再启动
old = """      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        vsStart(true);
        setTimeout(function () {
          if (!vs.stream) { toast('没拿到麦克风：请允许录音权限，或改用「意念注入」', 'ok'); }
        }, 1600);
      });"""
if old in a:
    a = a.replace(old, """      ch.addEventListener('click', function () {
        vs.purpose = 'contribute';
        attachVsCard('screen-contribute');
        if ($('vsHint')) { $('vsHint').textContent = '正在请求录音权限…（请在弹窗里点“允许”）'; }
        function boot() { vsStart(!!vs.stream); }
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
            vs.stream = st;
            if ($('vsHint')) { $('vsHint').textContent = '录音已开启（本机分析，不上传）'; }
            boot();
          }).catch(function (e) {
            var why = (e && e.name) ? e.name : '未知错误';
            if ($('vsHint')) {
              $('vsHint').textContent = '录音没开成：' + why +
                '（若是微信内置浏览器，请用系统浏览器打开；也可先用「意念注入」）';
            }
            toast('录音没开成：' + why, 'ok');
            boot();
          });
        } else {
          if ($('vsHint')) { $('vsHint').textContent = '这台设备/浏览器不支持网页录音（需 https + 系统浏览器）'; }
          boot();
        }
      });""")

# 3) vsStart：已有流时不再重复取麦
a = a.replace("      if (withMic && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {",
              "      if (withMic && vs.stream) {\n        vs.totalMs = 0; vs.voicedMs = 0;\n        try {\n          var AC0 = window.AudioContext || window.webkitAudioContext;\n          vs.ac = new AC0();\n          var src0 = vs.ac.createMediaStreamSource(vs.stream);\n          vs.analyser = vs.ac.createAnalyser();\n          vs.analyser.fftSize = 1024;\n          src0.connect(vs.analyser);\n        } catch (e0) {}\n        return true;\n      }\n      if (withMic && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '106';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('mic fix applied:', '正在请求录音权限' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '106'
d['notes'] = ['修：符咒注入进页面即绑定按钮，并在点击手势内直接请求麦克风、失败给出具体原因'] + [n for n in d['notes'] if '点击手势' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v113_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v114_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v113','v114').replace('V113','V114'))
p = open(r'_资料\部署载荷\_shuzi_v113.ps1', encoding='utf-8').read()
p = p.replace('V113','V114').replace('v113','v114').replace("WEB_VER = '105'","WEB_VER = '106'").replace('APPJS_WEBVER105','APPJS_WEBVER106').replace('"web": "105"','"web": "106"').replace('LIVE_VERSION105','LIVE_VERSION106')
open(r'_资料\部署载荷\_shuzi_v114.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 106 ready')
