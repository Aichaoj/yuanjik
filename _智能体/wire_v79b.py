# -*- coding: utf-8 -*-
"""v79（修正版）：今日健康指数随当日时间/状态浮动，15 分钟刷新。"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_score = "      var score = Math.round(num(idx.score));"
if old_score in a:
    a = a.replace(old_score, "      var score = liveDailyScore(Math.round(num(idx.score)));", 1)

a = a.replace("""'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '">' + esc(score) + '</span>' +""",
              """'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '" id="idxScoreLive">' + esc(score) + '</span>' +""", 1)

anchor = "  /* v72：首页「今日能量指数」（显示在今日健康指数下面） */"
assert anchor in a, 'anchor missing'
fn = '''  /* v79：今日健康指数随当日时间/状态浮动（展示层；次日清晨回到当日基准） */
  function liveDayOffset() {
    var h = new Date().getHours() + new Date().getMinutes() / 60;
    if (h >= 6 && h < 9) { return 0; }
    if (h >= 9 && h < 12) { return -3; }
    if (h >= 12 && h < 14) { return -5; }
    if (h >= 14 && h < 18) { return -7; }
    if (h >= 18 && h < 22) { return -10; }
    return -12;
  }

  function liveDailyScore(base) {
    var off = liveDayOffset();
    var e = window.__lastEnergyIndex;
    if (typeof e === 'number') { off += Math.max(-5, Math.min(5, Math.round((e - 600) / 200 * 5))); }
    off -= Math.min(6, window.__sessionsToday || 0);
    return Math.max(0, Math.min(100, Math.round(base + off)));
  }

  function refreshLiveScore() {
    var el = $('idxScoreLive');
    var idx = (state.daily && typeof state.daily.index === 'object') ? state.daily.index : null;
    if (!el || !idx || typeof idx.score === 'undefined') { return; }
    el.textContent = liveDailyScore(Math.round(num(idx.score)));
  }

''' + anchor
a = a.replace(anchor, fn, 1)

if 'window.__lastEnergyIndex = d.index' not in a:
    a = a.replace("""      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }""",
                  """      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if (typeof d.index === 'number') { window.__lastEnergyIndex = d.index; refreshLiveScore(); }
      if (!window.__liveScoreTimer) {
        window.__liveScoreTimer = setInterval(function () {
          refreshLiveScore();
          if (typeof loadHomeEnergy === 'function') { loadHomeEnergy(); }
        }, 15 * 60 * 1000);
      }""", 1)

# 今日「补充能量」次数（工作/使劲的近似），从能量仓状态里取
a = a.replace("""    var sess = d.sessions || {};""",
              """    var sess = d.sessions || {};
    if (typeof sess.today === 'number') { window.__sessionsToday = sess.today; }""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '79';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok; live fn =', 'liveDailyScore' in a, '; id =', 'idxScoreLive' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '79'
d['notes'] = ['今日健康指数随当日时间与状态浮动（约每 15 分钟刷新），次日清晨回到当日基准'] + [
    n for n in d['notes'] if '浮动' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web 79')
