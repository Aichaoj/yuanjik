# -*- coding: utf-8 -*-
"""v145：应用内「检查更新」→ 显示版本 + 立即下载安装包（网页侧实现，不改壳）"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

code = '''
  /* ══════════════════════════════════════════════════════════
   * v145 应用内检查更新：查星枢商城版本 → 立即下载安装包
   *   星枢条目：59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e
   * ══════════════════════════════════════════════════════════ */
  var STORE_APP_ID = '59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e';
  var STORE_API = 'https://wxr.arpa.cc/api/apps?pageSize=300';
  var APK_DL = 'https://wxr.arpa.cc/api/apps/' + STORE_APP_ID + '/installer';

  function ensureUpdateChip() {
    if ($('updateChip')) { return; }
    var chip = document.createElement('button');
    chip.type = 'button';
    chip.id = 'updateChip';
    chip.textContent = '检查更新';
    chip.style.cssText = 'position:fixed;left:10px;bottom:74px;z-index:9000;font:12px/1 -apple-system,' +
      '"PingFang SC",sans-serif;padding:7px 10px;border-radius:14px;border:1px solid #f0b6c2;' +
      'background:#fff6f8;color:#c0392b;box-shadow:0 2px 8px rgba(0,0,0,.06)';
    document.body.appendChild(chip);
    chip.addEventListener('click', checkAppUpdate);
  }

  function checkAppUpdate() {
    var chip = $('updateChip');
    if (chip) { chip.textContent = '检查中…'; }
    fetch(STORE_API, { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var list = (d && (d.items || d.data)) || [];
        var hit = null;
        for (var i = 0; i < list.length; i++) {
          var name = typeof list[i].name === 'string' ? list[i].name : JSON.stringify(list[i].name || '');
          if (name.indexOf('元神') >= 0) { hit = list[i]; break; }
        }
        var ver = hit ? (hit.version || '未知') : '未查到';
        var hasPkg = hit ? !!hit.hasPackage : false;
        var last = safeGet('yh.appVer') || '';
        if (chip) { chip.textContent = 'v' + ver; }
        if (hasPkg) {
          var box = document.createElement('div');
          box.id = 'updateBox';
          box.style.cssText = 'position:fixed;left:12px;right:12px;bottom:110px;z-index:9001;' +
            'background:#fff;border:1px solid #eee;border-radius:14px;padding:14px;' +
            'box-shadow:0 8px 28px rgba(0,0,0,.16);font:14px/1.6 -apple-system,"PingFang SC",sans-serif';
          box.innerHTML = '<p style="margin:0 0 8px"><b>当前最新版本：v' + ver + '</b>' +
            (last ? '<span style="color:#999;font-size:12px">（你上次下载：' + last + '）</span>' : '') + '</p>' +
            '<p style="margin:0 0 10px;color:#666;font-size:12px">点下面按钮立即下载安装包，安装后即为最新版。</p>' +
            '<p style="display:flex;gap:8px;margin:0">' +
            '<a id="updateDl" href="' + APK_DL + '" style="flex:1;text-align:center;padding:10px;border-radius:10px;' +
            'background:#d6335a;color:#fff;text-decoration:none">立即下载安装包</a>' +
            '<button id="updateClose" type="button" style="flex:0 0 80px;padding:10px;border-radius:10px;' +
            'border:1px solid #ddd;background:#fff">关闭</button></p>';
          var old = $('updateBox');
          if (old) { old.remove(); }
          document.body.appendChild(box);
          $('updateClose').addEventListener('click', function () { box.remove(); });
          $('updateDl').addEventListener('click', function () { safeSet('yh.appVer', ver); });
        }
      })
      .catch(function () { if (chip) { chip.textContent = '检查更新'; } });
  }
'''

anchor = "  /* v79 首页：今日能量指数"
assert anchor in a
a = a.replace(anchor, code + "\n" + anchor, 1)

# 启动时挂一次
a = a.replace("      refreshHome();", "      refreshHome();\n      ensureUpdateChip();", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '145';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('update chip ok:', 'ensureUpdateChip' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '145'
d['notes'] = ['应用内新增「检查更新」：显示商城最新版本，一键立即下载安装包'] + [
    n for n in d['notes'] if '检查更新' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v153_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v154_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v153', 'v154').replace('V153', 'V154'))
p = open(r'_资料\部署载荷\_shuzi_v153.ps1', encoding='utf-8').read()
p = p.replace('V153', 'V154').replace('v153', 'v154')
p = p.replace("WEB_VER = '144'", "WEB_VER = '145'").replace('APPJS_WEBVER144', 'APPJS_WEBVER145')
p = p.replace('"web": "144"', '"web": "145"').replace('LIVE_VERSION144', 'LIVE_VERSION145')
open(r'_资料\部署载荷\_shuzi_v154.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 145 / v154 ready')
