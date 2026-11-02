# -*- coding: utf-8 -*-
"""v79（定版）：今日健康指数随当日时间/状态浮动，15 分钟刷新。锚点用函数名，稳。"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

if 'liveDailyScore' in a:
    print('already patched')
else:
    a = a.replace("      var score = Math.round(num(idx.score));",
                  "      var score = liveDailyScore(Math.round(num(idx.score)));", 1)
    a = a.replace("""'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '">' + esc(score) + '</span>' +""",
                  """'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '" id="idxScoreLive">' + esc(score) + '</span>' +""", 1)

    anchor = "  function loadHomeEnergy() {"
    assert anchor in a, 'loadHomeEnergy missing'
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

    a = a.replace("""      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }""",
                  """      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if (typeof d.index === 'number') { window.__lastEnergyIndex = d.index; refreshLiveScore(); }
      if (!window.__liveScoreTimer) {
        window.__liveScoreTimer = setInterval(function () {
          refreshLiveScore();
          if (typeof loadHomeEnergy === 'function') { loadHomeEnergy(); }
        }, 15 * 60 * 1000);
      }""", 1)

open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('live fn:', 'liveDailyScore' in a, '| id:', 'idxScoreLive' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '79'
d['notes'] = ['今日健康指数随当日时间与状态浮动（约每 15 分钟刷新），次日清晨回到当日基准'] + [
    n for n in d['notes'] if '浮动' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web', d['web'])
