# -*- coding: utf-8 -*-
"""v79（本次定版）：补齐首页「今日能量指数」的 JS + 今日健康指数时变（15 分钟刷新）"""
import json

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
assert 'function loadMineEnergy() {' in a

fn = '''  /* v79 首页：今日能量指数（填充 + 点击进我的）+ 今日健康指数时变（每 15 分钟刷新）
     时变是展示层：早 0 / 上午 -3 / 午 -5 / 下午 -7 / 晚 -10 / 夜 -12，
     再叠能量偏离与今日补充次数；次日清晨归零回到当日基准。内部系数不对外显示。 */
  function liveDayOffset() {
    var d = new Date();
    var h = d.getHours() + d.getMinutes() / 60;
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

  function loadHomeEnergy() {
    var row = $('homeEnergyRow');
    if (!row) { return; }
    apiFetch('/vault/energy').then(function (env) {
      var d = (env && env.data) || {};
      row.hidden = false;
      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if ($('homeEnergyBand')) {
        $('homeEnergyBand').textContent = d.band || '';
        $('homeEnergyBand').style.color = d.band_color || '';
        $('homeEnergyBand').style.borderColor = d.band_color || '';
      }
      row.classList.toggle('is-low', !!d.need_recharge);
      if (typeof d.index === 'number') { window.__lastEnergyIndex = d.index; refreshLiveScore(); }
      apiFetch('/vault/status').then(function (e2) {
        var s = ((e2 && e2.data) || {}).sessions || {};
        if (typeof s.today === 'number') { window.__sessionsToday = s.today; refreshLiveScore(); }
      }, function () {});
    }, function () { /* 未登录：保持隐藏 */ });
    if (row && !row.__bound) {
      row.__bound = true;
      row.addEventListener('click', function () { showView('mine'); });
    }
    if (!window.__liveScoreTimer) {
      window.__liveScoreTimer = setInterval(function () {
        refreshLiveScore();
        loadHomeEnergy();
      }, 15 * 60 * 1000);
    }
  }

''' + '  function loadMineEnergy() {'
a = a.replace('  function loadMineEnergy() {', fn, 1)

# 分数用实时值并加 id
old_score = "      var score = Math.round(num(idx.score));"
if old_score in a:
    a = a.replace(old_score, "      var score = liveDailyScore(Math.round(num(idx.score)));", 1)
a = a.replace("""'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '">' + esc(score) + '</span>' +""",
              """'<span class="idx-score' + (tone ? ' tone-' + tone : '') + '" id="idxScoreLive">' + esc(score) + '</span>' +""", 1)

# 首页进入时加载
if "if (name === 'home') { loadHomeEnergy(); }" not in a:
    a = a.replace("    if (name === 'mine') { loadMineEnergy(); }",
                  "    if (name === 'home') { loadHomeEnergy(); }\n    if (name === 'mine') { loadMineEnergy(); }", 1)

open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('live fn:', 'liveDailyScore' in a, '| home loader:', 'loadHomeEnergy' in a, '| id:', 'idxScoreLive' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '79'
d['notes'] = ['今日健康指数随当日时间与状态浮动（约每 15 分钟刷新），次日清晨回到当日基准',
              '首页「今日能量指数」补齐自动填充与点击进入'] + [n for n in d['notes'] if '浮动' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('web', d['web'])
