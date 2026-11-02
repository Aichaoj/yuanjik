/* ============================================================
   AI数显 · 元健康 —— 独立后台（/admin/）前端逻辑
   纯原生 JS：无框架、无构建、无外网依赖。
   令牌只存 sessionStorage（后台更敏感，不使用 localStorage）。
   所有接口失败都给出可读提示条，不出现白屏。

   ★ 契约兼容口径（2026-10-08 实测）：
     变更单 §二 列的是「裸载荷」字段名；线上实现的 admin_api.py 用的是
     JSON 信封 {code,message,data,trace_id} + 更细的字段名（如 users_total /
     archive_rate / index_distribution / baseline_progress / birth.birth_date）。
     本文件对两种形状都做兼容：先按变更单字段名取，取不到再按实现字段名取，
     字段名一律不改写、不臆造。
   ============================================================ */
(function () {
  'use strict';

  /* 接口前缀（与后端契约一致，字段名不得改） */
  var API = '/api/v1/admin';
  /* 会话令牌存储键 */
  var TOKEN_KEY = 'shuzi_admin_token';

  /* 运行时状态 */
  var state = {
    token: '',
    panel: 'users',
    loaded: {},                                  /* 各板块是否已加载过 */
    users: { page: 1, size: 20, q: '', total: 0 },
    social: { page: 1, size: 20, total: 0, kind: 'relations' },
    audit: { page: 1, size: 20, total: 0 }
  };

  /* 弹窗 / 抽屉的临时状态 */
  var modalResolve = null;

  /* ---------- 基础工具 ---------- */

  function $(id) { return document.getElementById(id); }

  /* HTML 转义：所有来自接口的文本都必须先转义再拼串 */
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function pad2(n) {
    n = Number(n);
    if (!isFinite(n)) return '00';
    return n < 10 ? '0' + n : String(n);
  }

  /* 统一时间展示：支持 ISO 字符串 / 秒级或毫秒级时间戳 */
  function fmtTime(v) {
    if (v === null || v === undefined || v === '') return '—';
    var d;
    if (typeof v === 'number') {
      d = new Date(v < 1e12 ? v * 1000 : v);
    } else {
      var s = String(v);
      if (/^\d{10}$/.test(s)) d = new Date(Number(s) * 1000);
      else if (/^\d{13}$/.test(s)) d = new Date(Number(s));
      else d = new Date(s);
      if (isNaN(d.getTime())) return s;         /* 已是可读文本则原样显示 */
    }
    if (isNaN(d.getTime())) return String(v);
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
           ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  /* member_id 过长时截断显示（完整值放在 title 中） */
  function shortId(id) {
    var s = String(id === null || id === undefined ? '' : id);
    if (s.length <= 12) return s;
    return s.slice(0, 8) + '…' + s.slice(-2);
  }

  function isTrue(v) {
    return v === true || v === 1 || v === '1' || v === 'true';
  }

  function num(v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    if (!isFinite(n)) return esc(v);
    return n.toLocaleString('zh-CN');
  }

  /* 比例归一：接口可能给 0~1 或 0~100，统一成百分数文本 */
  function toPercent(v) {
    var n = Number(v);
    if (!isFinite(n)) return '—';
    if (n > 0 && n <= 1.0000001) n = n * 100;
    return (Math.round(n * 10) / 10) + '%';
  }

  function errOf(msg, status) {
    var e = new Error(msg);
    e.status = status;
    e.detail = null;
    return e;
  }

  /* ---------- 字段兼容取数 ----------
     一律「先契约名、后实现名」，取到即用；不改名、不猜值。
     ───────────────────────────────── */
  var SENSITIVE_KEY_RE = /(birth_time|birthtime|birth_hour|birth_minute|hour|minute|second|timestamp_ms|pressure|systolic|diastolic|pulse|heart|weight|height|glucose|sugar|spo2|bmi|history_note|diagnos|medic|symptom)/i;

  function isSensitiveKey(k) { return SENSITIVE_KEY_RE.test(String(k)); }

  /* 从对象里按候选键名依次取值：跳过敏感键，取到第一个非空值 */
  function pick(src, keys) {
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (isSensitiveKey(k)) continue;
      if (src && src[k] !== undefined && src[k] !== null && src[k] !== '') return src[k];
    }
    return null;
  }

  function obj(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }

  /* ---------- 提示条 / 轻提示 ---------- */

  function panelErr(id, msg, retry) {
    var el = $(id);
    if (!el) return;
    if (!msg) { el.hidden = true; el.innerHTML = ''; return; }
    el.hidden = false;
    el.innerHTML = '<span class="banner-text">' + esc(msg) + '</span>';
    if (retry) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-ghost btn-sm';
      b.textContent = '重试';
      b.addEventListener('click', retry);
      el.appendChild(b);
    }
  }

  function globalErr(msg, retry) {
    var box = $('globalErr');
    if (!box) return;
    if (!msg) { box.hidden = true; return; }
    $('globalErrText').textContent = msg;
    var btn = $('globalErrRetry');
    btn.hidden = !retry;
    btn.onclick = retry || null;
    box.hidden = false;
  }

  function toast(msg, kind) {
    var wrap = $('toastWrap');
    if (!wrap) return;
    var el = document.createElement('div');
    el.className = 'toast' + (kind === 'ok' ? ' toast-ok' : (kind === 'err' ? ' toast-err' : ''));
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 4200);
  }

  /* ---------- 网络层 ---------- */

  /* 解信封：实现若返回 {code,message,data,...}，取出 data；code≠0 视为错误。
     裸载荷（变更单口径）原样返回。 */
  function unwrap(data) {
    if (data && typeof data === 'object' && !Array.isArray(data) &&
        Object.prototype.hasOwnProperty.call(data, 'code') &&
        Object.prototype.hasOwnProperty.call(data, 'data')) {
      var code = Number(data.code);
      if (isFinite(code) && code !== 0) {
        var e = errOf(data.message || ('接口返回错误码 ' + data.code), 0);
        e.detail = data.detail || null;
        throw e;
      }
      return data.data === null || data.data === undefined ? {} : data.data;
    }
    return data;
  }

  /* 统一请求：自动带 Bearer，401 一律回登录界面 */
  function api(path, opts) {
    opts = opts || {};
    var headers = {};
    if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
    var init = { method: opts.method || 'GET', headers: headers };
    if (opts.body !== undefined && opts.body !== null) {
      headers['Content-Type'] = 'application/json';
      init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    }

    return fetch(API + path, init).then(function (res) {
      return res.text().then(function (raw) {
        var data = null;
        if (raw) {
          try { data = JSON.parse(raw); } catch (e) { data = null; }
        }
        if (res.status === 401) {
          onUnauthorized();
          throw errOf('登录已失效，请重新登录。', 401);
        }
        if (!res.ok) {
          var msg = data && (data.message || data.error || data.detail || data.msg);
          var e = errOf(msg ? String(msg) : ('请求失败（HTTP ' + res.status + '）'), res.status);
          if (data && typeof data.detail === 'object') e.detail = data.detail;
          throw e;
        }
        if (data === null) throw errOf('返回内容无法解析（非 JSON 格式）', res.status);
        return unwrap(data);
      });
    }, function (netErr) {
      throw errOf('网络异常：' + ((netErr && netErr.message) || '无法连接服务端'), 0);
    });
  }

  /* ---------- 登录 / 登出 ---------- */

  function setLoginErr(msg) {
    var el = $('loginErr');
    if (!el) return;
    if (!msg) { el.hidden = true; el.textContent = ''; return; }
    el.hidden = false;
    el.textContent = msg;
  }

  function onUnauthorized() {
    try { sessionStorage.removeItem(TOKEN_KEY); } catch (e) { /* 隐私模式下忽略 */ }
    state.token = '';
    state.loaded = {};
    closeDrawer();
    closeModal(false);
    globalErr('');
    var app = $('appView');
    var login = $('loginView');
    if (app) app.hidden = true;
    if (login) login.hidden = false;
    setLoginErr('登录已失效，请重新登录。');
    var pw = $('loginPwd');
    if (pw) { pw.value = ''; try { pw.focus(); } catch (e2) {} }
  }

  function doLogin() {
    var input = $('loginPwd');
    var pwd = input ? input.value : '';
    if (!pwd) { setLoginErr('请输入管理口令。'); return; }

    setLoginErr('');
    globalErr('');
    var btn = $('loginBtn');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;

    api('/login', { method: 'POST', body: { password: pwd } })
      .then(function (d) {
        if (!d || !d.admin_token) throw errOf('登录响应异常：缺少 admin_token 字段。', 0);
        state.token = d.admin_token;
        try { sessionStorage.setItem(TOKEN_KEY, d.admin_token); } catch (e) { /* 忽略 */ }
        if (input) input.value = '';
        enterApp();
      })
      .catch(function (e) {
        var det = obj(e.detail);
        if (e.status === 401) {
          var left = det.remaining_attempts;
          setLoginErr('口令错误，请重新输入。' +
            (left === undefined || left === null ? '' : '还可尝试 ' + left + ' 次；') +
            '连续失败 5 次将锁定 15 分钟。');
        } else if (e.status === 429) {
          var sec = Number(det.remaining_sec);
          setLoginErr(e.message + (isFinite(sec) && sec > 0
            ? '（剩余 ' + Math.ceil(sec / 60) + ' 分钟）' : '') + '，锁定期间请稍后再试。');
        } else {
          setLoginErr(e.message || '登录失败，请稍后重试。');
        }
      })
      .then(function () {
        btn.removeAttribute('aria-busy');
        btn.disabled = false;
      });
  }

  function doLogout() {
    try { sessionStorage.removeItem(TOKEN_KEY); } catch (e) { /* 忽略 */ }
    state.token = '';
    state.loaded = {};
    closeDrawer();
    closeModal(false);
    globalErr('');
    $('appView').hidden = true;
    $('loginView').hidden = false;
    setLoginErr('');
    toast('已退出登录。');
  }

  function enterApp() {
    $('loginView').hidden = true;
    $('appView').hidden = false;
    globalErr('');
    switchPanel(state.panel || 'users', true);
  }

  /* ---------- 板块切换 ---------- */

  var LOADERS = {
    users: function () { loadUsers(); },
    stats: function () { loadStats(); },
    social: function () { loadSocial(); },
    audit: function () { loadAudit(); }
  };

  function switchPanel(name, force) {
    if (name !== 'export' && !LOADERS[name]) name = 'users';
    state.panel = name;

    var tabs = document.querySelectorAll('.nav-btn');
    for (var i = 0; i < tabs.length; i++) {
      var on = tabs[i].getAttribute('data-panel') === name;
      tabs[i].classList.toggle('is-on', on);
      tabs[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    var panels = document.querySelectorAll('.panel');
    for (var j = 0; j < panels.length; j++) {
      panels[j].hidden = panels[j].getAttribute('data-panel') !== name;
    }

    if (name === 'export') return;                 /* 导出板块无需预拉数据 */
    if (force || !state.loaded[name]) {
      state.loaded[name] = true;
      LOADERS[name]();
    }
  }

  /* ---------- 分页渲染 ---------- */

  function renderPager(el, st, reload) {
    if (!el) return;
    var size = st.size || 20;
    var total = st.total || 0;
    var pages = Math.max(1, Math.ceil(total / size));
    var page = Math.min(Math.max(1, st.page || 1), pages);
    st.page = page;

    el.innerHTML =
      '<button type="button" class="btn btn-ghost btn-sm" data-go="prev"' + (page <= 1 ? ' disabled' : '') + '>上一页</button>' +
      '<span class="pager-info">第 ' + page + ' / ' + pages + ' 页 · 共 ' + total + ' 条</span>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-go="next"' + (page >= pages ? ' disabled' : '') + '>下一页</button>';

    var prev = el.querySelector('[data-go="prev"]');
    var next = el.querySelector('[data-go="next"]');
    if (prev) prev.addEventListener('click', function () { if (st.page > 1) { st.page--; reload(); } });
    if (next) next.addEventListener('click', function () { if (st.page < pages) { st.page++; reload(); } });
  }

  /* 表格加载失败：在表体内给出可读提示 + 重试，而不是空白 */
  function tableError(tbodyId, colspan, msg, retry) {
    var box = $(tbodyId);
    if (!box) return;
    box.innerHTML = '<tr><td class="td-err" colspan="' + colspan + '">' + esc(msg) + '</td></tr>';
    if (retry) {
      var tr = document.createElement('tr');
      var td = document.createElement('td');
      td.className = 'td-err';
      td.colSpan = colspan;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-ghost btn-sm';
      b.textContent = '重试';
      b.addEventListener('click', retry);
      td.appendChild(b);
      tr.appendChild(td);
      box.appendChild(tr);
    }
  }

  /* ============================================================
     板块 1：用户列表
     ============================================================ */

  function loadUsers() {
    panelErr('userErr', '');
    var st = state.users;
    var q = st.q ? ('&q=' + encodeURIComponent(st.q)) : '';

    api('/users?page=' + st.page + '&size=' + st.size + q)
      .then(function (d) {
        var items = (d && d.items) || [];
        st.total = Number(d && d.total) || 0;
        if (d && d.page) st.page = Number(d.page) || st.page;
        if (d && d.size) st.size = Number(d.size) || st.size;

        renderUsers(items);
        renderPager($('userPager'), st, loadUsers);
        $('usersNote').textContent = (st.q ? '关键词「' + st.q + '」· ' : '') + '共 ' + st.total + ' 位用户';
      })
      .catch(function (e) {
        if (e.status === 401) return;
        tableError('userRows', 6, '用户列表加载失败：' + e.message, loadUsers);
        $('userPager').innerHTML = '';
        $('usersNote').textContent = '加载失败';
        panelErr('userErr', '用户列表加载失败：' + e.message, loadUsers);
      });
  }

  /* 建档状态：兼容 profile_done / profile_completed / archive_status 文本 */
  function profileText(u) {
    var done = pick(u, ['profile_done', 'profile_completed']);
    if (done === null) {
      var txt = pick(u, ['archive_status']);
      if (txt !== null) {
        var s = String(txt);
        return s.indexOf('未') === 0
          ? '<span class="badge badge-warn">' + esc(s) + '</span>'
          : '<span class="badge badge-ok">' + esc(s) + '</span>';
      }
      return '<span class="badge badge-mute">—</span>';
    }
    return isTrue(done) ? '<span class="badge badge-ok">已建档</span>'
                        : '<span class="badge badge-warn">未建档</span>';
  }

  /* 基线进度 n/m：兼容 baseline_n（契约）与 baseline_progress（实现） */
  function baselineCell(u) {
    var bp = obj(u.baseline_progress);
    var n = pick(u, ['baseline_n']);
    if (n === null) n = pick(bp, ['observation_count']);
    if (n === null) n = pick(u, ['observation_count']);
    if (n === null) return '<span class="badge badge-mute">—</span>';
    var m = pick(bp, ['min_observations']);
    if (m === null) m = 7;
    n = Math.max(0, Math.round(Number(n) || 0));
    m = Math.max(1, Math.round(Number(m) || 7));
    var cls = n >= m ? 'badge-ok' : (n > 0 ? 'badge-warn' : 'badge-mute');
    return '<span class="badge ' + cls + '">' + n + ' / ' + m + '</span>';
  }

  function renderUsers(items) {
    var box = $('userRows');
    if (!items.length) {
      box.innerHTML = '<tr><td class="td-empty" colspan="8">没有符合条件的用户</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < items.length; i++) {
      var u = items[i] || {};
      var id = u.member_id === undefined || u.member_id === null ? '' : String(u.member_id);
      var streak = pick(u, ['streak_days']);
      var banned = pick(u, ['banned']);
      html +=
        '<tr class="row-click" data-id="' + esc(id) + '" tabindex="0">' +
          '<td><button type="button" class="cell-open mono" title="' + esc(id) + '">' + esc(shortId(id)) + '</button>' +
            (isTrue(banned) ? ' <span class="badge badge-alert">已封禁</span>' : '') + '</td>' +
          '<td>' + esc(pick(u, ['nickname']) || '（未设置）') + '</td>' +
          '<td class="nowrap">' + phoneCell(u) + '</td>' +
          '<td>' + profileText(u) + '</td>' +
          '<td>' + baselineCell(u) + '</td>' +
          '<td class="nowrap">' + esc(fmtTime(pick(u, ['last_active']))) + '</td>' +
          '<td class="nowrap">' + resetPwdCell(u, id) + '</td>' +
          '<td class="nowrap">' + esc(streak === null ? '—' : (Number(streak) || 0) + ' 天') + '</td>' +
        '</tr>';
    }
    box.innerHTML = html;
  }

  /** 手机号列（v13.1，师父 2026-10-09「用户管理里面还应该增加一栏手机号」） */
  function phoneCell(u) {
    var p = pick(u, ['phone']);
    if (!p) return '<span class="muted">未绑定</span>';
    return '<span class="mono">' + esc(String(p)) + '</span>';
  }

  /**
   * 「重置密码」列（v13，师父 2026-10-09）：
   *   · 该账号已注册手机号+密码 → 可点「重置」
   *   · 尚未注册（设备游客）→ 显示「未注册」，不误导管理员去点
   */
  function resetPwdCell(u, id) {
    if (!isTrue(pick(u, ['has_password']))) {
      return '<span class="muted" title="该用户还没有注册密码账号（设备游客）">未注册</span>';
    }
    return '<button type="button" class="btn btn-ghost btn-sm act-reset" data-id="' + esc(id) +
           '" title="为该用户生成新的随机登录密码">重置</button>';
  }

  /** 二次确认 → 调后台重置 → 把新口令**只显示一次**给管理员（审计不留口令） */
  function doResetPassword(memberId, label) {
    if (!memberId) return;
    confirmDialog('重置密码',
      '确定为「' + (label || '该用户') + '」重置登录密码吗？重置后旧密码立即失效，失败锁定同时解除。',
      '重置')
      .then(function (ok) {
        if (!ok) return;
        api('/user/' + encodeURIComponent(memberId) + '/reset-password', { method: 'POST' })
          .then(function (d) {
            var pwd = (d && d.new_password) || '';
            confirmDialog('密码已重置',
              '账号 ' + ((d && d.phone_masked) || '') + ' 的新密码：' + pwd +
              '　（只显示这一次，请立即转告用户；用户登录后可自行修改。）', '知道了');
            toast('已重置密码', 'ok');
            loadUsers();
          })
          .catch(function (e) {
            toast('重置失败：' + ((e && e.message) ? e.message : e), 'err');
          });
      });
  }

  function doUserSearch() {
    state.users.q = ($('userQ').value || '').trim();
    state.users.page = 1;
    loadUsers();
  }

  /* ============================================================
     用户详情抽屉（严格脱敏）
     ============================================================ */

  function openDrawer(title, html) {
    $('drawerTitle').textContent = title;
    $('drawerBody').innerHTML = html;
    $('drawer').hidden = false;
    $('drawerMask').hidden = false;
    try { $('drawerClose').focus(); } catch (e) { /* 忽略 */ }
  }

  function closeDrawer() {
    var d = $('drawer');
    var m = $('drawerMask');
    if (d) d.hidden = true;
    if (m) m.hidden = true;
  }

  function openDetail(memberId) {
    if (!memberId) return;
    openDrawer('用户详情', '<div class="loading">正在加载用户详情…</div>');

    api('/user/' + encodeURIComponent(memberId))
      .then(function (d) { renderDetail(d, memberId); })
      .catch(function (e) {
        if (e.status === 401) return;
        $('drawerBody').innerHTML = '<div class="err-box">用户详情加载失败：' + esc(e.message) + '</div>';
      });
  }

  /* 取详情对象：兼容 {user:{}} / {detail:{}} / 平铺 三种形态 */
  function detailSource(d) {
    if (!d || typeof d !== 'object') return {};
    if (d.user && typeof d.user === 'object') return d.user;
    if (d.detail && typeof d.detail === 'object') return d.detail;
    return d;
  }

  function kvRow(label, value) {
    return '<div class="kv"><dt>' + esc(label) + '</dt><dd>' + value + '</dd></div>';
  }

  /* 渲染详情：只读白名单字段，敏感键永不参与渲染 */
  function renderDetail(d, fallbackId) {
    var src = detailSource(d);
    var birth = obj(src.birth);              /* 实现口径：生辰信息在 birth 子对象里 */
    var archive = obj(src.archive);          /* 实现口径：体征/病史只有布尔标记 */
    var bp = obj(src.baseline_progress);
    var idx = obj(src.today_index);
    var checkins = obj(src.checkins);
    var social = obj(src.social);

    var memberId = String(pick(src, ['member_id']) || fallbackId || '');
    var nickname = pick(src, ['nickname']);
    var inviteCode = pick(src, ['invite_code', 'invite']);

    /* 出生日：只取年月日（birth.birth_date 优先，其次平铺 birth_date，再次年/月/日三段） */
    var birthDate = pick(birth, ['birth_date']);
    if (birthDate === null) birthDate = pick(src, ['birth_date', 'birthday']);
    if (birthDate === null) {
      var by = pick(src, ['birth_year']);
      var bm = pick(src, ['birth_month']);
      var bd = pick(src, ['birth_day']);
      if (by && bm && bd) birthDate = String(by) + '-' + pad2(bm) + '-' + pad2(bd);
    }
    var birthCity = pick(birth, ['birth_city']);
    if (birthCity === null) birthCity = pick(src, ['birth_city', 'birth_place', 'city']);

    /* 体征：只显示「是否已采集/已填写」，不显示任何数值 */
    var vitalsMark = pick(archive, ['vitals_collected']);
    var hasVitals = (vitalsMark === null) ? pick(src, ['has_vitals', 'vitals_filled', 'vitals'])
                                          : vitalsMark;
    var historyMark = pick(archive, ['history_collected']);

    var profileDone = pick(src, ['profile_done', 'profile_completed']);
    var baselineN = pick(src, ['baseline_n']);
    if (baselineN === null) baselineN = pick(bp, ['observation_count']);
    if (baselineN === null) baselineN = pick(src, ['observation_count']);
    var baselineM = pick(bp, ['min_observations']);
    if (baselineM === null) baselineM = 7;

    var streak = pick(src, ['streak_days']);
    var checkinDays = pick(src, ['checkin_days']);
    if (checkinDays === null) checkinDays = pick(checkins, ['total']);
    var lastActive = pick(src, ['last_active']);
    var banned = pick(src, ['banned']);

    var html = '';
    /* 合规提示：详情抽屉顶部常显 */
    html += '<div class="compliance"><span class="compliance-mark" aria-hidden="true">合规</span>' +
            '<span>按合规要求：后台不展示精确出生时刻、体征数值与病史原文。</span></div>';

    /* 身份 */
    html += '<section class="kv-section"><h3>身份</h3><dl class="kv-list">';
    html += kvRow('用户标识', '<span class="mono">' + esc(memberId || '—') + '</span>');
    html += kvRow('昵称', esc(nickname || '（未设置）'));
    if (inviteCode) html += kvRow('邀请码', '<span class="mono">' + esc(inviteCode) + '</span>');
    html += '</dl></section>';

    /* 生辰档案（脱敏） */
    html += '<section class="kv-section"><h3>生辰档案（脱敏）</h3><dl class="kv-list">';
    html += kvRow('出生日（仅年月日）',
                  esc(birthDate || '未填写') + (birthDate ? '<span class="card-note">　不含出生时刻</span>' : ''));
    html += kvRow('出生地（城市）', esc(birthCity || '未填写'));
    html += '</dl></section>';

    /* 体征档案（脱敏） */
    html += '<section class="kv-section"><h3>体征档案（脱敏）</h3><dl class="kv-list">';
    var vTxt;
    if (hasVitals === null || hasVitals === undefined) vTxt = '<span class="badge badge-mute">未填写</span>';
    else if (isTrue(hasVitals)) vTxt = '<span class="badge badge-ok">已填写</span><span class="card-note">　后台不显示数值</span>';
    else vTxt = '<span class="badge badge-mute">未采集</span><span class="card-note">　后台不显示数值</span>';
    html += kvRow('是否已填写', vTxt);
    if (historyMark !== null) {
      html += kvRow('病史自述采集', isTrue(historyMark)
        ? '<span class="badge badge-warn">已采集</span><span class="card-note">　后台不展示原文</span>'
        : '<span class="badge badge-mute">未采集</span><span class="card-note">　后台不展示原文</span>');
    }
    html += '</dl></section>';

    /* 使用情况 */
    html += '<section class="kv-section"><h3>使用情况</h3><dl class="kv-list">';
    html += kvRow('建档状态', profileDone === null ? '—' : profileText({ profile_done: profileDone }));
    var bn = Number(baselineN);
    var bm = Math.max(1, Math.round(Number(baselineM) || 7));
    html += kvRow('基线进度', isFinite(bn) ? (Math.max(0, Math.round(bn)) + ' / ' + bm) : '—');
    html += kvRow('连续天数', (streak === null ? '—' : (Number(streak) || 0) + ' 天'));
    if (checkinDays !== null) html += kvRow('累计打卡', (Number(checkinDays) || 0) + ' 天');
    html += kvRow('最近活跃', esc(fmtTime(lastActive)));
    html += kvRow('账号状态', isTrue(banned)
      ? '<span class="badge badge-alert">已封禁</span>' : '<span class="badge badge-ok">正常</span>');
    html += '</dl></section>';

    /* 今日指数（非敏感：展示分与分档） */
    var score = pick(idx, ['score']);
    if (score !== null) {
      var band = pick(idx, ['band']);
      var code = pick(idx, ['band_code']);
      html += '<section class="kv-section"><h3>今日指数</h3><dl class="kv-list">';
      html += kvRow('展示分', esc(String(score)) + (band ? '　<span class="badge badge-ok">' + esc(band) + (code ? ' · ' + esc(code) : '') + '</span>' : ''));
      html += '</dl></section>';
    }

    /* 社交概况 */
    var fa = pick(social, ['friends_accepted']);
    var fp = pick(social, ['friends_pending']);
    if (fa !== null || fp !== null) {
      html += '<section class="kv-section"><h3>社交概况</h3><dl class="kv-list">';
      html += kvRow('好友数', esc(String(Number(fa) || 0)));
      html += kvRow('待确认', esc(String(Number(fp) || 0)));
      html += '</dl></section>';
    }

    /* 服务端脱敏口径（实现会回一组策略说明，原样展示以增强可核查性） */
    var policy = src.masking_policy;
    if (Object.prototype.toString.call(policy) === '[object Array]' && policy.length) {
      html += '<section class="kv-section"><h3>服务端脱敏口径</h3><ul class="policy-list">';
      for (var i = 0; i < policy.length; i++) {
        html += '<li>' + esc(policy[i]) + '</li>';
      }
      html += '</ul></section>';
    }

    $('drawerBody').innerHTML = html;
  }

  /* ============================================================
     板块 2：运营指标
     ============================================================ */

  function loadStats() {
    panelErr('statsErr', '');
    api('/stats')
      .then(function (d) { renderStats(d || {}); })
      .catch(function (e) {
        if (e.status === 401) return;
        $('statsGrid').innerHTML = '';
        $('bandList').innerHTML = '<p class="loading">指数分布暂无数据</p>';
        panelErr('statsErr', '运营指标加载失败：' + e.message, loadStats);
      });
  }

  function statCard(label, valueHtml, sub) {
    return '<div class="stat"><div class="stat-label">' + esc(label) + '</div>' +
           '<div class="stat-value">' + valueHtml + '</div>' +
           (sub ? '<div class="stat-sub">' + sub + '</div>' : '') + '</div>';
  }

  function renderStats(d) {
    var circle = obj(d.friend_circle);
    var html = '';
    /* 五个指标：先契约名，后实现名 */
    html += statCard('总用户', num(pick(d, ['total_users', 'users_total'])));
    html += statCard('今日新增', num(pick(d, ['today_new', 'new_today'])));

    var profiledTotal = pick(d, ['profiled_total']);
    html += statCard('建档率', esc(toPercent(pick(d, ['profile_rate', 'archive_rate']))),
                     profiledTotal === null ? '' : '已建档 ' + num(profiledTotal) + ' 人');

    var checkinTotal = pick(d, ['checkin_users', 'checkin_users_total']);
    var checkinToday = pick(d, ['checkin_users_today']);
    html += statCard('打卡用户', num(checkinTotal),
                     checkinToday === null ? '' : '今日打卡 ' + num(checkinToday) + ' 人');

    var edges = pick(d, ['social_edges']);
    if (edges === null) edges = pick(circle, ['accepted']);
    var sub2 = '';
    if (pick(circle, ['accepted']) !== null || pick(circle, ['cheer_total']) !== null) {
      sub2 = '待确认 ' + num(pick(circle, ['pending'])) + ' · 加油 ' + num(pick(circle, ['cheer_total']));
    }
    html += statCard('好友圈关系数', num(edges), sub2);

    $('statsGrid').innerHTML = html;
    renderBands(d);
  }

  /* 指数分布：兼容 index_bands{A,B,C,D}（契约）与 index_distribution.items（实现） */
  function renderBands(d) {
    var rows = [];
    var dist = obj(d.index_distribution);
    var items = dist.items;

    if (Object.prototype.toString.call(items) === '[object Array]' && items.length) {
      for (var i = 0; i < items.length; i++) {
        var it = obj(items[i]);
        rows.push({
          code: String(it.code === undefined ? '' : it.code),
          name: pick(it, ['name']) || '',
          count: Number(it.count) || 0,
          pct: Number(it.pct)
        });
      }
    } else {
      var bands = obj(d.index_bands);
      if (!Object.keys(bands).length && Object.keys(dist).length) bands = dist;
      var keys = ['A', 'B', 'C', 'D'];
      var vals = keys.map(function (k) { var n = Number(bands[k]); return isFinite(n) && n > 0 ? n : 0; });
      var sum = vals.reduce(function (a, b) { return a + b; }, 0);
      for (var j = 0; j < keys.length; j++) {
        rows.push({
          code: keys[j], name: '', count: vals[j],
          pct: sum <= 0 ? 0 : (sum <= 1.5 ? vals[j] * 100 : vals[j] / sum * 100)
        });
      }
      if (!sum) rows = [];
    }

    if (!rows.length) {
      $('bandList').innerHTML = '<p class="loading">暂无指数分布数据</p>';
      return;
    }

    var body = '';
    for (var k = 0; k < rows.length; k++) {
      var r = rows[k];
      var p = Math.round((isFinite(r.pct) ? r.pct : 0) * 10) / 10;
      var w = Math.max(0, Math.min(100, p));
      body +=
        '<div class="bar-row" data-band="' + esc(r.code) + '">' +
          '<span class="bar-name" title="' + esc(r.name) + '">指数 ' + esc(r.code) +
            (r.name ? '<span class="bar-sub">' + esc(r.name) + '</span>' : '') + '</span>' +
          '<span class="bar-track"><i class="bar-fill" style="width:' + w + '%"></i></span>' +
          '<span class="bar-val">' + p + '%<span class="bar-sub">' + num(r.count) + ' 人</span></span>' +
        '</div>';
    }
    $('bandList').innerHTML = body;
  }

  /* ============================================================
     板块 3：好友圈治理
     ============================================================ */

  function loadSocial() {
    panelErr('socialErr', '');
    var st = state.social;
    api('/social?kind=' + encodeURIComponent(st.kind) + '&page=' + st.page + '&size=' + st.size)
      .then(function (d) {
        var items = (d && d.items) || [];
        st.total = Number(d && d.total) || 0;
        if (d && d.page) st.page = Number(d.page) || st.page;
        if (d && d.size) st.size = Number(d.size) || st.size;
        if (d && d.kind) st.kind = String(d.kind);

        renderSocial(items);
        renderPager($('socialPager'), st, loadSocial);
        var counts = obj(d && d.counts);
        var cTxt = st.kind === 'cheers'
          ? ('加油共 ' + num(pick(counts, ['cheer_total'])) + ' 条 · 今日 ' + num(pick(counts, ['cheer_today'])))
          : ('已建立 ' + num(pick(counts, ['accepted'])) + ' · 待确认 ' + num(pick(counts, ['pending'])));
        $('socialNote').textContent = '共 ' + st.total + ' 条' + (Object.keys(counts).length ? '（' + cTxt + '）' : '');

        /* 同步类型切换按钮态 */
        var segs = document.querySelectorAll('#socialKind .seg-btn');
        for (var i = 0; i < segs.length; i++) {
          var on = segs[i].getAttribute('data-kind') === st.kind;
          segs[i].classList.toggle('is-on', on);
          segs[i].setAttribute('aria-pressed', on ? 'true' : 'false');
        }
      })
      .catch(function (e) {
        if (e.status === 401) return;
        tableError('socialRows', 6, '好友圈数据加载失败：' + e.message, loadSocial);
        $('socialPager').innerHTML = '';
        $('socialNote').textContent = '加载失败';
        panelErr('socialErr', '好友圈数据加载失败：' + e.message, loadSocial);
      });
  }

  /* 关系行 / 加油行 → 统一的展示与「封禁对象」推导 */
  function socialRowView(r) {
    var relation = (state.social.kind === 'relations');
    var aName, bName, aId, bId, typeText, timeVal, extra;

    if (relation) {
      aName = pick(r, ['a_nickname', 'from_nickname']) || '—';
      bName = pick(r, ['b_nickname', 'to_nickname']) || '—';
      aId = pick(r, ['a_member', 'from_member_id', 'from_member']) || '';
      bId = pick(r, ['b_member', 'to_member_id', 'to_member']) || '';
      var status = pick(r, ['status', 'kind', 'type']);
      typeText = status === 'accepted' ? '已建立' : (status === 'pending' ? '待确认' : (status || '关系'));
      timeVal = pick(r, ['created_at', 'at', 'time', 'ts']);
      extra = pick(r, ['accepted_at']) ? null : null;
    } else {
      aName = pick(r, ['from_nickname']) || '—';
      bName = pick(r, ['to_nickname']) || '—';
      aId = pick(r, ['from_member', 'from_member_id']) || '';
      bId = pick(r, ['to_member', 'to_member_id']) || '';
      typeText = pick(r, ['template_id', 'kind', 'type']) || '加油';
      timeVal = pick(r, ['created_at', 'at', 'on_date', 'time', 'ts']);
      extra = pick(r, ['on_date']);
    }

    /* 封禁对象：优先契约字段，其次本行「接受方/被加油方」；再回退到发起方 */
    var target = pick(r, ['target_member_id', 'member_id']);
    if (!target) target = bId || aId;
    var targetName = (String(target) === String(bId)) ? bName
                     : (String(target) === String(aId) ? aName : (bName !== '—' ? bName : aName));
    var banned = pick(r, ['banned']);

    return { relation: relation, aName: aName, bName: bName, aId: aId, bId: bId,
             typeText: typeText, timeVal: timeVal, onDate: extra,
             target: String(target || ''), targetName: targetName, banned: banned };
  }

  function renderSocial(items) {
    var box = $('socialRows');
    if (!items.length) {
      box.innerHTML = '<tr><td class="td-empty" colspan="6">' +
        (state.social.kind === 'cheers' ? '暂无加油记录' : '暂无好友关系记录') + '</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < items.length; i++) {
      var v = socialRowView(items[i] || {});
      var cheers = pick(items[i] || {}, ['cheers', 'cheer_count', 'cheer_n', 'count']);
      var isBanned = isTrue(v.banned);
      var banLabel = state.social.kind === 'cheers' ? '加油' : '关系';
      html +=
        '<tr data-target="' + esc(v.target) + '">' +
          '<td class="nowrap">' + esc(fmtTime(v.timeVal)) + '</td>' +
          '<td>' + esc(v.aName) + ' <span class="card-note">→</span> ' + esc(v.bName) +
            (v.aId || v.bId ? '<span class="card-note mono">　' + esc(shortId(v.aId)) + '/' + esc(shortId(v.bId)) + '</span>' : '') + '</td>' +
          '<td>' + esc(v.typeText) + (v.onDate && v.onDate !== v.timeVal ? '<span class="card-note">　' + esc(v.onDate) + '</span>' : '') + '</td>' +
          '<td class="nowrap">' + esc(cheers === null ? (v.relation ? '—' : '1') : (Number(cheers) || 0)) + '</td>' +
          '<td>' + (v.banned === null ? '<span class="badge badge-mute">—</span>'
                    : (isBanned ? '<span class="badge badge-alert">已封禁</span>' : '<span class="badge badge-ok">正常</span>')) + '</td>' +
          '<td><button type="button" class="btn btn-sm ' + (isBanned ? 'btn-ghost' : 'btn-danger') + '" ' +
            'data-ban="' + esc(v.target) + '" data-banned="' + (isBanned ? '1' : '0') + '" ' +
            'title="' + esc(banLabel + '对象：' + (v.targetName || v.target)) + '　' + esc(v.target) + '" ' +
            (v.target ? '' : 'disabled ') + '>' + (isBanned ? '解封' : '封禁') + '</button></td>' +
        '</tr>';
    }
    box.innerHTML = html;
  }

  /* 封禁 / 解封：必须二次确认后才发请求 */
  function onBanClick(memberId, isBanned) {
    if (!memberId) return;
    confirmDialog(
      isBanned ? '解除封禁' : '封禁用户',
      (isBanned ? '确认解除对 ' : '确认封禁用户 ') + memberId +
        (isBanned ? ' 的封禁？解除后其社交功能恢复。' : ' ？封禁后其社交功能将停用（好友圈与加油均不可用）。'),
      isBanned ? '确认解封' : '确认封禁'
    ).then(function (ok) {
      if (!ok) return;
      return api('/ban', { method: 'POST', body: { member_id: memberId, banned: !isBanned } })
        .then(function () {
          toast((isBanned ? '已解除封禁：' : '已封禁：') + memberId, 'ok');
          loadSocial();
        })
        .catch(function (e) {
          if (e.status === 401) return;
          panelErr('socialErr', '操作失败：' + e.message, null);
          toast('操作失败：' + e.message, 'err');
        });
    });
  }

  /* ============================================================
     板块 4：导出（fetch + blob，不用 <a href>，因为要带令牌头）
     ============================================================ */

  function doExport() {
    panelErr('exportErr', '');
    var btn = $('exportBtn');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;

    var headers = {};
    if (state.token) headers['Authorization'] = 'Bearer ' + state.token;

    fetch(API + '/export.csv', { method: 'GET', headers: headers })
      .then(function (res) {
        if (res.status === 401) {
          onUnauthorized();
          throw errOf('登录已失效，请重新登录。', 401);
        }
        if (!res.ok) throw errOf('导出失败（HTTP ' + res.status + '）', res.status);
        return res.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'ai-users-export.csv';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
        toast('已开始下载脱敏 CSV（不含精确出生时刻、体征数值与病史原文）。', 'ok');
      })
      .catch(function (e) {
        if (e.status === 401) return;
        panelErr('exportErr', '导出失败：' + e.message, null);
        toast('导出失败：' + e.message, 'err');
      })
      .then(function () {
        btn.removeAttribute('aria-busy');
        btn.disabled = false;
      });
  }

  /* ============================================================
     板块 5：审计
     ============================================================ */

  function loadAudit() {
    panelErr('auditErr', '');
    var st = state.audit;
    api('/audit?page=' + st.page + '&size=' + st.size)
      .then(function (d) {
        var items = (d && d.items) || [];
        st.total = Number(d && d.total) || 0;
        if (d && d.page) st.page = Number(d.page) || st.page;
        if (d && d.size) st.size = Number(d.size) || st.size;

        renderAudit(items);
        renderPager($('auditPager'), st, loadAudit);
        $('auditNote').textContent = '共 ' + st.total + ' 条日志';
      })
      .catch(function (e) {
        if (e.status === 401) return;
        tableError('auditRows', 4, '审计日志加载失败：' + e.message, loadAudit);
        $('auditPager').innerHTML = '';
        $('auditNote').textContent = '加载失败';
        panelErr('auditErr', '审计日志加载失败：' + e.message, loadAudit);
      });
  }

  function renderAudit(items) {
    var box = $('auditRows');
    if (!items.length) {
      box.innerHTML = '<tr><td class="td-empty" colspan="4">暂无审计日志</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < items.length; i++) {
      var r = items[i] || {};
      var ip = pick(r, ['ip', 'client_ip']);
      var action = pick(r, ['action', 'event', 'kind']);
      html +=
        '<tr>' +
          '<td class="nowrap">' + esc(fmtTime(pick(r, ['at', 'created_at', 'time', 'ts']))) + '</td>' +
          '<td>' + esc(pick(r, ['operator', 'actor', 'admin', 'user']) || '—') + '</td>' +
          '<td>' + esc(action || '—') + '</td>' +
          '<td>' + esc(pick(r, ['target', 'target_member_id', 'member_id', 'object']) || '—') +
            (ip ? '<span class="card-note mono">　' + esc(ip) + '</span>' : '') + '</td>' +
        '</tr>';
    }
    box.innerHTML = html;
  }

  /* ============================================================
     二次确认弹窗
     ============================================================ */

  function confirmDialog(title, text, okText) {
    return new Promise(function (resolve) {
      modalResolve = resolve;
      $('modalTitle').textContent = title;
      $('modalText').textContent = text;
      $('modalOk').textContent = okText || '确认';
      $('modalMask').hidden = false;
      try { $('modalCancel').focus(); } catch (e) { /* 忽略 */ }
    });
  }

  function closeModal(result) {
    var mask = $('modalMask');
    if (mask) mask.hidden = true;
    if (modalResolve) {
      var fn = modalResolve;
      modalResolve = null;
      fn(!!result);
    }
  }

  /* ============================================================
     事件绑定与启动
     ============================================================ */

  function bind() {
    /* 登录 */
    $('loginBtn').addEventListener('click', doLogin);
    $('loginForm').addEventListener('submit', function (e) { e.preventDefault(); doLogin(); });
    $('loginPwd').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); doLogin(); }
    });

    /* 顶栏 */
    $('logoutBtn').addEventListener('click', doLogout);
    $('globalErrClose').addEventListener('click', function () { globalErr(''); });

    /* 导航 */
    var tabs = document.querySelectorAll('.nav-btn');
    for (var i = 0; i < tabs.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () { switchPanel(btn.getAttribute('data-panel'), false); });
      })(tabs[i]);
    }

    /* 用户板块 */
    $('userSearchBtn').addEventListener('click', doUserSearch);
    $('userResetBtn').addEventListener('click', function () {
      $('userQ').value = '';
      state.users.q = '';
      state.users.page = 1;
      loadUsers();
    });
    $('userReloadBtn').addEventListener('click', function () {
      state.loaded.users = true;
      loadUsers();
    });
    $('userQ').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); doUserSearch(); }
    });
    /* 行点击（含键盘）打开详情抽屉；行内「重置」按钮走自己的动作，不打开抽屉 */
    $('userRows').addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.act-reset') : null;
      if (btn) {
        e.preventDefault();
        e.stopPropagation();
        var tr = btn.closest('tr.row-click');
        doResetPassword(btn.getAttribute('data-id'),
                        tr ? (tr.children[1] ? tr.children[1].textContent.trim() : '') : '');
        return;
      }
      var tr2 = e.target && e.target.closest ? e.target.closest('tr.row-click') : null;
      if (tr2) openDetail(tr2.getAttribute('data-id'));
    });
    $('userRows').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var tr = e.target && e.target.closest ? e.target.closest('tr.row-click') : null;
      if (tr) { e.preventDefault(); openDetail(tr.getAttribute('data-id')); }
    });

    /* 指标板块 */
    $('statsReloadBtn').addEventListener('click', function () { loadStats(); });

    /* 好友圈板块：关系 / 加油 切换 */
    var segs = document.querySelectorAll('#socialKind .seg-btn');
    for (var s = 0; s < segs.length; s++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          state.social.kind = btn.getAttribute('data-kind');
          state.social.page = 1;
          loadSocial();
        });
      })(segs[s]);
    }
    $('socialReloadBtn').addEventListener('click', function () { loadSocial(); });
    $('socialRows').addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('[data-ban]') : null;
      if (!btn || btn.disabled) return;
      onBanClick(btn.getAttribute('data-ban'), btn.getAttribute('data-banned') === '1');
    });

    /* 导出板块 */
    $('exportBtn').addEventListener('click', doExport);

    /* 审计板块 */
    $('auditReloadBtn').addEventListener('click', function () { loadAudit(); });

    /* 抽屉关闭 */
    $('drawerClose').addEventListener('click', closeDrawer);
    $('drawerMask').addEventListener('click', closeDrawer);

    /* 弹窗按钮 */
    $('modalCancel').addEventListener('click', function () { closeModal(false); });
    $('modalOk').addEventListener('click', function () { closeModal(true); });
    $('modalMask').addEventListener('click', function (e) {
      if (e.target === $('modalMask')) closeModal(false);
    });

    /* Esc：先关弹窗，再关抽屉 */
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if (!$('modalMask').hidden) { closeModal(false); return; }
      if (!$('drawer').hidden) closeDrawer();
    });
  }

  function boot() {
    bind();
    /* 会话内已有令牌 → 直接进入后台；否则显示登录界面 */
    var saved = '';
    try { saved = sessionStorage.getItem(TOKEN_KEY) || ''; } catch (e) { saved = ''; }
    if (saved) {
      state.token = saved;
      enterApp();
    } else {
      $('loginView').hidden = false;
      $('appView').hidden = true;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
