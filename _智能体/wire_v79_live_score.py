# -*- coding: utf-8 -*-
"""v79：今日健康指数随当日时间与状态浮动（每 15 分钟刷新一次），次日清晨回到当日基准

显示层浮动（不改内核评分口径，合约不变）：
  时段 0/-3/-5/-7/-10/-12（早/上午/午/下午/晚/夜）
  能量指数偏离 600 时 ±5；今日「补充能量」次数每次 -1（工作/使劲的可用近似）
  次日清晨时段项归零 → 回到当日基准（80 → 75 → 70 → 次日 80 的观感）
"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 1) 工具函数：放在 renderDaily 之前（用 dayLineHtml 定位不到就放在 BAND 常量附近）
anchor = "    var d = state.daily || {};\n    var idx = (d && typeof d.index === 'object') ? d.index : null;"
assert a.count(anchor) == 1
helper = '''    var score0 = Math.round(num((idx || {}).score));
''' + anchor
a = a.replace(anchor, anchor)

# 2) 用实时分替换展示分，并给分数元素一个 id 便于 15 分钟刷新
old_score = """      var score = Math.round(num(idx.score));
      body.innerHTML ="""
assert a.count(old_score) == 1
a = a.replace(old_score, """      var score = liveDailyScore(Math.round(num(idx.score)));
      body.innerHTML =""")

a = a.replace("""'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '">' + esc(score) + '</span>' +""",
              """'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '" id="idxScoreLive">' + esc(score) + '</span>' +""")

# 3) 函数定义 + 15 分钟刷新（插在 loadHomeEnergy 之前）
anchor2 = "  /* v72：首页「今日能量指数」（显示在今日健康指数下面） */"
assert a.count(anchor2) == 1
fn = '''  /* v79：今日健康指数随当日时间/状态浮动（展示层，不改内核口径）。
     次日清晨时段项归零 → 回到当日基准分数。内部系数不对外显示。 */
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
    var used = window.__sessionsToday || 0;
    off -= Math.min(6, used);
    return Math.max(0, Math.min(100, Math.round(base + off)));
  }

  function refreshLiveScore() {
    var el = $('idxScoreLive');
    var idx = (state.daily && typeof state.daily.index === 'object') ? state.daily.index : null;
    if (!el || !idx || typeof idx.score === 'undefined') { return; }
    el.textContent = liveDailyScore(Math.round(num(idx.score)));
  }

''' + anchor2
a = a.replace(anchor2, fn)

# 4) 记录能量指数与今日次数，供浮动使用；并起 15 分钟定时器（只起一次）
a = a.replace("""      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }""",
              """      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if (typeof d.index === 'number') { window.__lastEnergyIndex = d.index; refreshLiveScore(); }
      if (!window.__liveScoreTimer) {
        window.__liveScoreTimer = setInterval(function () {
          refreshLiveScore();
          if (typeof loadHomeEnergy === 'function') { loadHomeEnergy(); }
        }, 15 * 60 * 1000);
      }""")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '79';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js live score ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '79'
d['notes'] = ['今日健康指数随当日时间与状态浮动（约每 15 分钟刷新），次日清晨回到当日基准'] + [
    n for n in d['notes'] if '浮动' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web 79')
