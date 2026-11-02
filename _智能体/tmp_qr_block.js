  /* ── v57（2026-10-24 师父令）：随手记改成「首页一行摘要 + 弹窗填写」──
     令：「我在电脑上填写了心情饮食等，怎么手机登陆了又要填一次？填写好上报后最好收起来，以弹窗模式。」
     三条口径：
       ① **回填**：进首页先读 /healthscore/status，把上次的饮食/心情/睡眠填进选择器，
          同一账号换设备（电脑→手机）看到的就是上次那份，不用重填；
       ② **收起**：卡片上只留一行摘要（今日已报：饮食较好·心情一般·睡眠 7h），点「修改」才展开；
       ③ **弹窗**：填写在底部弹窗里完成，上报成功 → 自动收起 + 摘要刷新；
          写入仍是「先读 → 只覆盖这次填的项 → 再写」，不会抹掉吸烟/运动/血压等其它项。 */
  var QR_OPTS = {
    diet: { label: '饮食', opts: [[5, '很好'], [4, '较好'], [3, '一般'], [2, '较差'], [1, '很差']] },
    mood: { label: '心情', opts: [[5, '很好'], [4, '较好'], [3, '一般'], [2, '偏低'], [1, '很低落']] }
  };
  var qrPick = { diet: 0, mood: 0 };
  var QR_KEY = 'yh.qr.';

  function qrFmtAnswers(a) {
    var out = [];
    var dietMap = { 5: '很好', 4: '较好', 3: '一般', 2: '较差', 1: '很差' };
    var moodMap = { 5: '很好', 4: '较好', 3: '一般', 2: '偏低', 1: '很低落' };
    if (a && a.diet > 0 && dietMap[a.diet]) { out.push('饮食 ' + dietMap[a.diet]); }
    if (a && a.mood > 0 && moodMap[a.mood]) { out.push('心情 ' + moodMap[a.mood]); }
    if (a && typeof a.sleep_hours_x10 === 'number' && a.sleep_hours_x10 > 0) {
      out.push('睡眠 ' + (Math.round(a.sleep_hours_x10 / 10 * 10) / 10) + 'h');
    }
    return out;
  }

  function applyAnswersToPicks(a) {
    qrPick.diet = (a && a.diet > 0) ? Number(a.diet) : 0;
    qrPick.mood = (a && a.mood > 0) ? Number(a.mood) : 0;
    var s = $('qrSleep');
    if (s) {
      s.value = (a && typeof a.sleep_hours_x10 === 'number' && a.sleep_hours_x10 > 0)
        ? String(Math.round(a.sleep_hours_x10 / 10 * 10) / 10) : '';
    }
  }

  function renderQrChips() {
    var box = $('qrChips');
    if (!box) { return; }
    var h = '';
    ['diet', 'mood'].forEach(function (k) {
      var g = QR_OPTS[k];
      h += '<div class="qr-row"><span class="qr-label">' + esc(g.label) + '</span>' +
           '<div class="chip-row">';
      g.opts.forEach(function (o) {
        var on = String(qrPick[k]) === String(o[0]) ? ' is-on' : '';
        h += '<button type="button" class="chip' + on + '" data-qr="' + k +
             '" data-val="' + o[0] + '">' + esc(o[1]) + '</button>';
      });
      h += '</div></div>';
    });
    box.innerHTML = h;
  }

  /** 首页一行摘要：有数据就显示上次那份，并标出「今日已报」 */
  function renderQrSummary() {
    var btn = $('btnOpenQr');
    if (!btn) { return; }
    var a = state.hsAnswers || null;
    var parts = qrFmtAnswers(a);
    var reportedToday = safeGet(QR_KEY + ymd()) === '1';
    if (!parts.length) {
      btn.innerHTML = '随手记一下今天的饮食 / 心情';
      btn.classList.remove('is-done');
      return;
    }
    btn.innerHTML = (reportedToday ? '今日已报：' : '上次记录：') + esc(parts.join(' · ')) +
                    '<i>' + (reportedToday ? '点这里修改' : '点这里修改或补报今天') + '</i>';
    btn.classList.add('is-done');
  }

  /** 读一次服务端的问卷（回填 + 摘要都靠它；同一账号换设备也能拿到） */
  function loadHealthStatus(force) {
    if (state.hsLoaded && !force) { renderQrSummary(); return Promise.resolve(); }
    return apiFetch('/healthscore/status').then(function (env) {
      var d = (env && env.data) || {};
      state.hsAnswers = d.answers || null;
      state.hsLoaded = true;
      if (d.answers) { applyAnswersToPicks(d.answers); }
      renderQrSummary();
    }, function () {
      state.hsLoaded = true;      // 取不到就当没填过，不挡住页面
      renderQrSummary();
    });
  }

  function openQrSheet() {
    if (state.hsAnswers) { applyAnswersToPicks(state.hsAnswers); }
    renderQrChips();
    if ($('qrHint')) {
      $('qrHint').textContent = state.hsAnswers
        ? '这里是你在任一设备上填过的那份，改完按「上报」即可覆盖。'
        : '上报会计入你的综合健康分，不会公开；只记情况，不做诊断。';
    }
    openSheet('qrSheet', 'btnCloseQr');
  }

  function renderHomeNeed() {
    var card = $('homeNeedCard');
    if (!card) { return; }
    if (!state.profileCompleted) { card.hidden = true; return; }
    card.hidden = false;
    renderQrSummary();

    var d = state.daily || {};
    var items = [];

    // ① 今日节律要点（daily.text 已过护栏）
    //    ★ 未建立基线时内核给的是「校准中」的说明文，与第 ③ 条重复 ⇒ 不重复播报
    var txt = (d && d.text && (d.text.text !== undefined ? d.text.text : d.text)) || '';
    txt = String(txt).replace(/\s+/g, ' ').trim();
    if (txt && txt !== '[object Object]' && d && d.baseline_established) {
      items.push('今日节律：' + (txt.length > 76 ? (txt.slice(0, 76) + '…') : txt));
    }

    // ② 当令时辰（纯时间推算，来自 /timemed/shichen）
    var sc = state.shichen;
    if (sc && sc.label) {
      var tip0 = (sc.tips && sc.tips[0]) ? String(sc.tips[0]) : '';
      items.push(sc.label + ' · ' + (sc.meridian || '') + '当令（' + (sc.range || '') + '）：' + tip0);
      if ($('homeNeedPhase')) {
        $('homeNeedPhase').hidden = false;
        $('homeNeedPhase').textContent = sc.label;
      }
    }

    // ③ 个体化：基线建立后给「今天多留意」；未建立给还差几天
    if (d && d.baseline_established) {
      var fc = (d.focus || []).slice(0, 2).map(function (f) {
        return (f && f.channel) ? String(f.channel) : String(f);
      });
      if (fc.length) {
        items.push('今天多留意：' + fc.join('、') + '（相对你自己的基线），作息上松一点、别硬扛。');
      }
    } else if (d && d.calibration) {
      var n = num(d.calibration.observation_count, 0);
      var m = num(d.calibration.min_observations, 7);
      items.push('个体化校准 ' + n + '/' + m + '：还差 ' + Math.max(0, m - n) +
                 ' 天，坚持每天签到；满 ' + m + ' 天后这里换成「相对你自己」的偏移。');
    }

    // ④ 今天记过没有：只在"从来没有记录"时提醒一句（有记录就靠摘要行，不唠叨）
    if (!qrFmtAnswers(state.hsAnswers).length && safeGet(QR_KEY + ymd()) !== '1') {
      items.push('今天还没记饮食和心情：点下面的「随手记」填一下，10 秒。');
    }

    $('homeNeedList').innerHTML = items.length
      ? items.map(function (t) { return '<li class="need-item">' + esc(t) + '</li>'; }).join('')
      : '<li class="placeholder">今日数据还没准备好，稍后刷新本页。</li>';

    if (!sc) { loadShichenTip(); }
    if (!state.hsLoaded) { loadHealthStatus(false); }
  }

  function loadShichenTip() {
    if (state.shichen || state.shichenLoading) { return; }
    state.shichenLoading = true;
    apiFetch('/timemed/shichen').then(function (env) {
      state.shichen = (env && env.data) || null;
      state.shichenLoading = false;
      renderHomeNeed();
    }, function () {
      state.shichenLoading = false;      // 取不到就当没有这一条，不影响其它内容
    });
  }

  function submitQuickReport() {
    var btn = $('btnQuickReport');
    var sleepEl = $('qrSleep');
    var sleep = sleepEl ? String(sleepEl.value || '').trim() : '';
    if (!qrPick.diet && !qrPick.mood && !sleep) {
      if ($('qrHint')) { $('qrHint').textContent = '先点一下饮食或心情（或填睡眠小时），再按「上报」。'; }
      return;
    }
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    if ($('qrHint')) { $('qrHint').textContent = '正在上报…'; }

    // 先读既有问卷 → 只覆盖这次填的项 → 再写（不把别的项清成未知）
    apiFetch('/healthscore/status').then(function (env) {
      var cur = ((env && env.data) || {}).answers || {};
      var merged = {};
      Object.keys(cur).forEach(function (k) { merged[k] = cur[k]; });
      if (qrPick.diet) { merged.diet = qrPick.diet; }
      if (qrPick.mood) { merged.mood = qrPick.mood; }
      if (sleep) {
        var v = Number(sleep);
        if (isFinite(v) && v > 0 && v <= 24) { merged.sleep_hours_x10 = Math.round(v * 10); }
      }
      var allow = ['smoking_cigs', 'smoking_dx', 'alcohol_liang_week', 'alcohol_dx',
                   'exercise_min', 'sleep_hours_x10', 'diet', 'sedentary_hours_x10',
                   'bmi_x10', 'waist_cm', 'systolic', 'diastolic', 'glucose', 'family',
                   'mood', 'work_stress', 'environment', 'low_two_weeks'];
      var answers = {};
      allow.forEach(function (k) {
        var v2 = merged[k];
        if (v2 === undefined || v2 === null || v2 === '' || v2 === -1) { return; }
        answers[k] = v2;
      });
      return apiFetch('/healthscore/save', { method: 'POST', body: { answers: answers } });
    }).then(function (env) {
      var r = (env && env.data) || {};
      safeSet(QR_KEY + ymd(), '1');
      var ch = (r.changed || []).slice(0, 2).map(function (c) {
        var b = (c.before === null || c.before === undefined) ? '—' : c.before;
        var a = (c.after === null || c.after === undefined) ? '—' : c.after;
        return c.domain + '·' + c.sub + ' ' + b + '→' + a;
      });
      var head = r.unchanged ? '记下了，今天的数据没有变化' : ('已上报，综合健康分 ' + hsFmtScore(r.score));
      toast(head + (ch.length ? '（' + ch.join('；') + '）' : ''), 'ok');
      closeSheet('qrSheet');            // ★ 上报成功即收起（师父令）
      return loadHealthStatus(true);    // ★ 摘要立刻刷新成"今日已报"
    }).catch(function (err) {
      if ($('qrHint')) { $('qrHint').textContent = '上报失败：' + readableError(err); }
    }).then(function () {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
    });
  }

  function bindHomeNeed() {
    var box = $('qrChips');
    if (box) {
      box.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== box && !(el.getAttribute && el.getAttribute('data-qr'))) { el = el.parentNode; }
        if (!el || el === box) { return; }
        var k = el.getAttribute('data-qr');
        qrPick[k] = Number(el.getAttribute('data-val')) || 0;
        var chips = el.parentNode.querySelectorAll('[data-qr]');
        for (var i = 0; i < chips.length; i++) { chips[i].classList.remove('is-on'); }
        el.classList.add('is-on');
        if ($('qrHint')) { $('qrHint').textContent = '选好了就按「上报」，会计入综合健康分。'; }
      });
    }
    var open = $('btnOpenQr');
    if (open) { open.addEventListener('click', openQrSheet); }
    var btn = $('btnQuickReport');
    if (btn) { btn.addEventListener('click', submitQuickReport); }
  }
