/* ============================================================
 * AI 健康 · 元健康 —— 移动优先单页 H5 前端
 * 纯原生 JS，无框架、无外网依赖。
 *
 * 约定来源：
 *   服务端/接口契约v0.md        —— 响应信封 {code,message,data,trace_id}、错误码、游标分页
 *   服务端/app/api.py           —— 路由与入参
 *   服务端/app/reading_service.py、kernel_adapter.py —— 今日节律响应字段
 *   基线契约                    —— 未满 7 次观测不出等级、不出关注通道
 *
 * 指数契约（GET /api/v1/rhythm/daily → data）：
 *   index        —— 冷启动（0 次打卡）也必须非空，字段见 §八之二 的渲染函数
 *   personalized —— 需 7 次打卡后才有值；非空时在指数卡下方追加"个体化"卡
 * ============================================================ */
'use strict';

(function () {

  /* ══════════════════════════════════════════════════════════
   * 一、常量
   * ══════════════════════════════════════════════════════════ */

  var API_BASE = '/api/v1';

  // 本地存储键
  var K_TOKEN = 'yh.access_token';
  var K_REFRESH = 'yh.refresh_token';
  var K_DEVICE = 'yh.device_id';
  var K_PROFILE = 'yh.profile_completed';

  // 需要重新取令牌的鉴权类错误码（接口契约 §2.7）
  var AUTH_CODES = { 20000: 1, 20001: 1, 20002: 1 };

  // 危机转介（契约 §7xxxx：是流程，不是错误）
  var CODE_CRISIS = 70004;
  // 生辰档案未完成
  var CODE_NO_PROFILE = 50002;

  // 观察等级（阈值与中文名取自内核 offset_layer.LEVELS，公开且固定）
  var LEVEL_INFO = {
    L1: { name: '平和', desc: '节律平稳', order: 1 },
    L2: { name: '宜养', desc: '节律偏移轻度', order: 2 },
    L3: { name: '宜慎', desc: '节律偏移较明显', order: 3 },
    L4: { name: '宜静', desc: '节律偏移显著', order: 4 }
  };
  // 比例条满格对应的偏移量：L4 阈值 0.60。条带中心为 Δ=0，向两侧展开。
  var DELTA_REF = 0.60;

  // 固定合规文案。与接口返回的 disclaimer / referral 同源；
  // 接口未返回或请求失败时用它兜底，保证任何情况下页面上都有合规声明。
  var DISCLAIMER_FALLBACK =
    '本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。' +
    '所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。';
  var AI_NOTICE = '本内容由 AI 生成，仅供参考。';
  var REFERRAL_FALLBACK = '建议咨询执业医师或前往正规医疗机构。';

  /* ── 健康指数分档（A 优 / B 良 / C 中 / D 需关注）─────────────
   * 分档仅表达"当日节律的综合取向"，不是任何医学判断；
   * 颜色只用于区分档位：A 绿、B 蓝、C 橙、D 红。 */
  var BAND_INFO = {
    A: { name: '优' },
    B: { name: '良' },
    C: { name: '中' },
    D: { name: '需关注' }
  };
  var BAND_ORDER = ['A', 'B', 'C', 'D'];

  /* 指数依据的兜底文案：接口未给 basis 时也保证页面上有合规标识。
     注意：接口给了 basis 就原样展示（那是冻结契约里的合规标识）。 */
  var BASIS_FALLBACK = '按出生时空与当日时相推算·仅为生活方式参考';

  /* 今日关注标签展开后的中性说明：按方向给生活作息取向，不涉及任何医学判断 */
  var ATTENTION_NOTE = {
    '偏亢': '该通道今日相对当日基准偏活跃，可适当放缓节奏、留出休息时间。',
    '偏虚': '该通道今日相对当日基准偏安静，可保持规律作息、适度活动。'
  };
  var ATTENTION_NOTE_DEFAULT = '该通道今日相对当日基准变化不大，按日常作息安排即可。';

  /* 站点地址：分享文案用（纯文本，不引入任何外网 SDK） */
  var SITE_URL = 'https://shuzi.yuanjk.cn';

  /* ── 常用城市经纬度（内置，不联网）───────────────────────── */
  var CITIES = [
    { g: '华北',    n: '北京',     lng: 116.4074, lat: 39.9042 },
    { g: '华北',    n: '天津',     lng: 117.2010, lat: 39.0842 },
    { g: '华北',    n: '石家庄',   lng: 114.5149, lat: 38.0428 },
    { g: '华北',    n: '太原',     lng: 112.5489, lat: 37.8706 },
    { g: '华北',    n: '呼和浩特', lng: 111.7519, lat: 40.8414 },
    { g: '东北',    n: '沈阳',     lng: 123.4315, lat: 41.8057 },
    { g: '东北',    n: '大连',     lng: 121.6147, lat: 38.9140 },
    { g: '东北',    n: '长春',     lng: 125.3235, lat: 43.8171 },
    { g: '东北',    n: '哈尔滨',   lng: 126.5349, lat: 45.8038 },
    { g: '华东',    n: '上海',     lng: 121.4737, lat: 31.2304 },
    { g: '华东',    n: '南京',     lng: 118.7969, lat: 32.0603 },
    { g: '华东',    n: '苏州',     lng: 120.5853, lat: 31.2989 },
    { g: '华东',    n: '无锡',     lng: 120.3119, lat: 31.4912 },
    { g: '华东',    n: '杭州',     lng: 120.1551, lat: 30.2741 },
    { g: '华东',    n: '宁波',     lng: 121.5440, lat: 29.8683 },
    { g: '华东',    n: '温州',     lng: 120.6994, lat: 27.9944 },
    { g: '华东',    n: '合肥',     lng: 117.2272, lat: 31.8206 },
    { g: '华东',    n: '福州',     lng: 119.2965, lat: 26.0745 },
    { g: '华东',    n: '厦门',     lng: 118.0894, lat: 24.4798 },
    { g: '华东',    n: '南昌',     lng: 115.8581, lat: 28.6820 },
    { g: '华东',    n: '济南',     lng: 117.1205, lat: 36.6510 },
    { g: '华东',    n: '青岛',     lng: 120.3826, lat: 36.0671 },
    { g: '华中',    n: '郑州',     lng: 113.6254, lat: 34.7466 },
    { g: '华中',    n: '武汉',     lng: 114.3055, lat: 30.5928 },
    { g: '华中',    n: '长沙',     lng: 112.9388, lat: 28.2282 },
    { g: '华南',    n: '广州',     lng: 113.2644, lat: 23.1291 },
    { g: '华南',    n: '深圳',     lng: 114.0579, lat: 22.5431 },
    { g: '华南',    n: '东莞',     lng: 113.7518, lat: 23.0207 },
    { g: '华南',    n: '佛山',     lng: 113.1220, lat: 23.0288 },
    { g: '华南',    n: '珠海',     lng: 113.5767, lat: 22.2707 },
    { g: '华南',    n: '南宁',     lng: 108.3665, lat: 22.8170 },
    { g: '华南',    n: '海口',     lng: 110.1983, lat: 20.0444 },
    { g: '西南',    n: '重庆',     lng: 106.5049, lat: 29.5332 },
    { g: '西南',    n: '成都',     lng: 104.0665, lat: 30.5728 },
    { g: '西南',    n: '贵阳',     lng: 106.6302, lat: 26.6477 },
    { g: '西南',    n: '昆明',     lng: 102.8329, lat: 24.8801 },
    { g: '西南',    n: '拉萨',     lng: 91.1409,  lat: 29.6456 },
    { g: '西北',    n: '西安',     lng: 108.9398, lat: 34.3416 },
    { g: '西北',    n: '兰州',     lng: 103.8343, lat: 36.0611 },
    { g: '西北',    n: '西宁',     lng: 101.7782, lat: 36.6171 },
    { g: '西北',    n: '银川',     lng: 106.2309, lat: 38.4872 },
    { g: '西北',    n: '乌鲁木齐', lng: 87.6168,  lat: 43.8256 },
    { g: '港澳台',  n: '香港',     lng: 114.1694, lat: 22.3193 },
    { g: '港澳台',  n: '澳门',     lng: 113.5439, lat: 22.1987 },
    { g: '港澳台',  n: '台北',     lng: 121.5654, lat: 25.0330 }
  ];

  /* ══════════════════════════════════════════════════════════
   * 二、通用工具
   * ══════════════════════════════════════════════════════════ */

  function $(id) { return document.getElementById(id); }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /** 本地时区的 YYYY-MM-DD（不用 toISOString，避免时区偏移） */
  function ymd(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  function ymdLabel(s) {
    if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) { return s || ''; }
    var p = s.split('-');
    var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    return p[0] + '年' + Number(p[1]) + '月' + Number(p[2]) + '日 星期' + WEEK[d.getDay()];
  }

  /** 本地随机串（用于设备标识与幂等键；只用时间与随机数，无外部依赖） */
  function randStr(len) {
    var s = '';
    var alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789';
    for (var i = 0; i < len; i++) {
      s += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
    }
    return s;
  }

  function uid(prefix) {
    return (prefix || '') + Date.now().toString(36) + '-' + randStr(16);
  }

  function esc(v) {
    if (v === null || v === undefined) { return ''; }
    return String(v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function num(v, dflt) {
    var n = Number(v);
    return isFinite(n) ? n : (dflt === undefined ? 0 : dflt);
  }

  function fmtDelta(v) {
    var n = num(v);
    return (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(3);
  }

  function safeGet(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* 隐私模式下忽略 */ } }
  function safeDel(k) { try { window.localStorage.removeItem(k); } catch (e) { /* 忽略 */ } }

  /* ══════════════════════════════════════════════════════════
   * 三、接口层
   * ══════════════════════════════════════════════════════════ */

  /** 业务错误：携带接口返回的 code / message / detail / trace_id */
  function ApiError(code, message, detail, traceId) {
    this.name = 'ApiError';
    this.code = code;
    this.message = message || '请求无法完成';
    this.detail = detail || {};
    this.traceId = traceId || '';
  }
  ApiError.prototype = Object.create(Error.prototype);

  function getToken() { return safeGet(K_TOKEN) || ''; }

  function setToken(access, refresh) {
    if (access) { safeSet(K_TOKEN, access); }
    if (refresh) { safeSet(K_REFRESH, refresh); }
  }

  function clearToken() { safeDel(K_TOKEN); safeDel(K_REFRESH); }

  /** 设备标识：本地生成并持久化，令牌与它绑定 */
  function deviceId() {
    var v = safeGet(K_DEVICE);
    if (!v) {
      v = 'h5-' + randStr(20) + '-' + Date.now().toString(36);
      safeSet(K_DEVICE, v);
    }
    return v;
  }

  function buildUrl(path, query) {
    var url = API_BASE + path;
    if (query) {
      var parts = [];
      for (var k in query) {
        if (Object.prototype.hasOwnProperty.call(query, k) &&
            query[k] !== undefined && query[k] !== null && query[k] !== '') {
          parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(query[k]));
        }
      }
      if (parts.length) { url += (url.indexOf('?') >= 0 ? '&' : '?') + parts.join('&'); }
    }
    return url;
  }

  /**
   * 统一请求。
   * opts:
   *   method          请求方法，默认 GET
   *   body            对象，自动 JSON 序列化
   *   query           查询参数对象
   *   headers         额外请求头
   *   idempotencyKey  幂等键（写操作必带，同一次提交复用同一个值）
   *   noAuth          不携带令牌（仅取令牌接口使用）
   */
  function apiFetch(path, opts) {
    opts = opts || {};
    var method = (opts.method || 'GET').toUpperCase();

    var headers = { 'Accept': 'application/json', 'X-Device-ID': deviceId() };
    if (!opts.noAuth) {
      var t = getToken();
      if (t) { headers['Authorization'] = 'Bearer ' + t; }
    }
    if (opts.body !== undefined && method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
    }
    if (opts.idempotencyKey) { headers['Idempotency-Key'] = opts.idempotencyKey; }
    if (opts.headers) {
      for (var hk in opts.headers) {
        if (Object.prototype.hasOwnProperty.call(opts.headers, hk)) { headers[hk] = opts.headers[hk]; }
      }
    }

    var init = { method: method, headers: headers, credentials: 'same-origin' };
    if (opts.body !== undefined && method !== 'GET' && method !== 'HEAD') {
      init.body = JSON.stringify(opts.body);
    }

    return fetch(buildUrl(path, opts.query), init).then(function (res) {
      return res.text().then(function (raw) {
        var payload = null;
        try { payload = raw ? JSON.parse(raw) : {}; } catch (e) { payload = null; }
        if (!payload || typeof payload !== 'object') {
          throw new ApiError(-2, '服务返回内容无法解析（HTTP ' + res.status + '）。', {}, '');
        }
        var code = (typeof payload.code === 'number') ? payload.code : -2;
        if (code === 0) { return payload; }

        // 危机转介（70004）是强制流程，不是业务错误：交回调用方渲染就医引导
        if (code === CODE_CRISIS) { payload._crisis = true; return payload; }

        // 鉴权失效：自动取游客令牌后重试一次
        if (AUTH_CODES[code] && !opts._retried) {
          clearToken();
          return ensureToken(true).then(function (ok) {
            if (!ok) {
              throw new ApiError(code, payload.message || '登录状态已失效，请重试。',
                                 payload.detail, payload.trace_id);
            }
            var retryOpts = {};
            for (var k in opts) {
              if (Object.prototype.hasOwnProperty.call(opts, k)) { retryOpts[k] = opts[k]; }
            }
            retryOpts._retried = true;
            return apiFetch(path, retryOpts);
          });
        }
        throw new ApiError(code, payload.message || '请求无法完成',
                           payload.detail, payload.trace_id);
      });
    }, function () {
      throw new ApiError(-1, '网络连接失败，请检查网络后重试。', {}, '');
    });
  }

  /** 取游客令牌（并发时只发一次请求） */
  var tokenPending = null;
  function ensureToken(force) {
    if (!force && getToken()) { return Promise.resolve(true); }
    if (tokenPending) { return tokenPending; }

    tokenPending = apiFetch('/auth/guest', {
      method: 'POST',
      body: { device_id: deviceId() },
      noAuth: true,
      _retried: true          // 取令牌本身不再触发重试，避免递归
    }).then(function (env) {
      var d = env.data || {};
      if (d.access_token) { setToken(d.access_token, d.refresh_token); return true; }
      return false;
    }, function () {
      // 联调降级：若部署尚未提供 /auth/guest，退回登录接口取一个游客会话。
      // 两条通道都不可用时返回 false，由调用方给出可读提示，页面不白屏。
      return apiFetch('/auth/login/code', {
        method: 'POST',
        body: { code: 'h5-guest-' + deviceId(), device_id: deviceId() },
        noAuth: true,
        _retried: true
      }).then(function (env2) {
        var d2 = env2.data || {};
        if (d2.access_token) { setToken(d2.access_token, d2.refresh_token); return true; }
        return false;
      }, function () { return false; });
    }).then(function (ok) {
      tokenPending = null;
      return ok;
    });

    return tokenPending;
  }

  /* ══════════════════════════════════════════════════════════
   * 四、界面反馈（错误条 / 轻提示 / 忙碌遮罩）
   * ══════════════════════════════════════════════════════════ */

  var alertTimer = null;
  function showAlert(msg) {
    var box = $('alertBox');
    $('alertText').textContent = msg;
    box.hidden = false;
    if (alertTimer) { window.clearTimeout(alertTimer); }
  }
  function hideAlert() {
    $('alertBox').hidden = true;
    if (alertTimer) { window.clearTimeout(alertTimer); alertTimer = null; }
  }

  var toastTimer = null;
  function toast(msg, kind) {
    var el = $('toast');
    el.textContent = msg;
    el.className = 'toast' + (kind === 'ok' ? ' is-ok' : (kind === 'err' ? ' is-err' : ''));
    el.hidden = false;
    if (toastTimer) { window.clearTimeout(toastTimer); }
    toastTimer = window.setTimeout(function () { el.hidden = true; }, 3200);
  }

  var busyCount = 0;
  function busy(on) {
    busyCount += on ? 1 : -1;
    if (busyCount < 0) { busyCount = 0; }
    $('busy').hidden = busyCount === 0;
  }

  /** 把错误对象转成一句可直接展示给用户的中文 */
  function readableError(err) {
    if (!err) { return '请求无法完成，请稍后重试。'; }
    var msg = err.message || '请求无法完成，请稍后重试。';
    if (err.traceId) { msg += '（追踪号 ' + err.traceId + '）'; }
    return msg;
  }

  /* ══════════════════════════════════════════════════════════
   * 五、状态与视图切换
   * ══════════════════════════════════════════════════════════ */

  var state = {
    view: 'home',
    profileCompleted: safeGet(K_PROFILE) === '1',
    daily: null,
    dailyEnv: null,           // 最近一次今日节律的完整信封，用于重复进入时直接重绘
    history: { items: [], cursor: null, hasMore: false, loaded: false, loading: false },
    profileKey: null,         // 建档幂等键：同一次提交复用
    checkinBusy: false,
    attention: [],            // 今日关注标签的数据源（与渲染出的标签按下标一一对应）
    streakHint: null          // 打卡接口回传的连续天数（有则优先使用）
  };

  var VIEWS = ['home', 'profile', 'rhythm'];

  function showView(name) {
    if (VIEWS.indexOf(name) < 0) { name = 'home'; }
    state.view = name;
    VIEWS.forEach(function (v) {
      var el = $('screen-' + v);
      if (el) { el.hidden = (v !== name); }
    });
    $('btnBack').hidden = (name === 'home');
    hideAlert();
    window.scrollTo(0, 0);

    // 无障碍：切换视图后把焦点移到该屏标题
    var title = $('screen-' + name).querySelector('.screen-title, .hero-title');
    if (title) {
      title.setAttribute('tabindex', '-1');
      try { title.focus({ preventScroll: true }); } catch (e) { title.focus(); }
    }

    if (name === 'rhythm') { loadDaily(); }
  }

  /* ══════════════════════════════════════════════════════════
   * 六、首屏
   * ══════════════════════════════════════════════════════════ */

  function refreshHome() {
    $('btnHomeRhythm').hidden = !state.profileCompleted;
    $('btnStart').querySelector('span').textContent =
      state.profileCompleted ? '重新建档' : '开始建档';
  }

  /* ══════════════════════════════════════════════════════════
   * 七、建档屏
   * ══════════════════════════════════════════════════════════ */

  function buildCityOptions() {
    var sel = $('inCity');
    var groups = {};
    var order = [];
    CITIES.forEach(function (c) {
      if (!groups[c.g]) { groups[c.g] = []; order.push(c.g); }
      groups[c.g].push(c);
    });
    var html = '<option value="">请选择常用城市</option>' +
               '<option value="__manual__">手动输入经纬度…</option>';
    order.forEach(function (g) {
      html += '<optgroup label="' + esc(g) + '">';
      groups[g].forEach(function (c) {
        html += '<option value="' + esc(c.n) + '" data-lng="' + c.lng +
                '" data-lat="' + c.lat + '">' + esc(c.n) + '</option>';
      });
      html += '</optgroup>';
    });
    sel.innerHTML = html;
  }

  function setCoordEditable(editable) {
    $('inLng').readOnly = !editable;
    $('inLat').readOnly = !editable;
  }

  function onCityChange() {
    var sel = $('inCity');
    var opt = sel.options[sel.selectedIndex];
    var hint = $('cityHint');
    if (sel.value === '__manual__') {
      $('inLng').value = '';
      $('inLat').value = '';
      setCoordEditable(true);
      hint.textContent = '请输入出生地经纬度，精确到小数点后 4 位即可。';
      $('inLng').focus();
      return;
    }
    if (opt && opt.dataset && opt.dataset.lng) {
      $('inLng').value = opt.dataset.lng;
      $('inLat').value = opt.dataset.lat;
      setCoordEditable(false);
      hint.textContent = '已填入 ' + sel.value + ' 的经纬度；如需修改请选择「手动输入经纬度」。';
      return;
    }
    setCoordEditable(false);
    $('inLng').value = '';
    $('inLat').value = '';
    hint.textContent = '已内置常用城市及其经纬度，选择后自动填入。';
  }

  function fieldError(id, msg) {
    var el = $(id);
    if (!el) { return; }
    if (msg) { el.textContent = msg; el.hidden = false; }
    else { el.textContent = ''; el.hidden = true; }
  }

  function validateProfile() {
    var ok = true;
    fieldError('errBirthDate', '');
    fieldError('errCoord', '');
    $('inBirthDate').classList.remove('is-invalid');
    $('inLng').classList.remove('is-invalid');
    $('inLat').classList.remove('is-invalid');

    var dateVal = $('inBirthDate').value;
    if (!dateVal) {
      fieldError('errBirthDate', '请选择出生日期。');
      $('inBirthDate').classList.add('is-invalid');
      $('inBirthDate').focus();
      ok = false;
    } else if (dateVal > ymd()) {
      fieldError('errBirthDate', '出生日期不能晚于今天。');
      $('inBirthDate').classList.add('is-invalid');
      ok = false;
    }

    var lng = $('inLng').value.trim();
    var lat = $('inLat').value.trim();
    if (lng === '' || lat === '') {
      fieldError('errCoord', '请选择出生地城市，或手动输入经纬度。');
      if (!ok) { /* 保留首个焦点 */ } else { $('inLng').focus(); }
      ok = false;
    } else if (!isFinite(Number(lng)) || Number(lng) < -180 || Number(lng) > 180) {
      fieldError('errCoord', '经度需为 −180 ~ 180 之间的数字。');
      $('inLng').classList.add('is-invalid');
      ok = false;
    } else if (!isFinite(Number(lat)) || Number(lat) < -90 || Number(lat) > 90) {
      fieldError('errCoord', '纬度需为 −90 ~ 90 之间的数字。');
      $('inLat').classList.add('is-invalid');
      ok = false;
    }

    if (!$('inConsent').checked) {
      showAlert('请先阅读并勾选《健康数据处理告知同意书》，再提交建档。');
      ok = false;
    }
    return ok;
  }

  function submitProfile(ev) {
    if (ev) { ev.preventDefault(); }
    hideAlert();
    if (!validateProfile()) { return; }

    var dateVal = $('inBirthDate').value;
    var timeVal = $('inBirthTime').value || '12:00';   // 留空按正午参与计算
    var birthLocal = dateVal + ' ' + timeVal;          // 本地时间字符串，与接口一致

    // 幂等键：同一次提交复用同一个值
    if (!state.profileKey) { state.profileKey = uid('profile-'); }

    var btn = $('btnSubmitProfile');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    $('submitProfileText').textContent = '正在建档…';

    apiFetch('/profile/birth', {
      method: 'POST',
      idempotencyKey: state.profileKey,
      body: {
        birth_local: birthLocal,
        longitude: Number($('inLng').value),
        latitude: Number($('inLat').value)
      }
    }).then(function (env) {
      var d = env.data || {};
      state.profileCompleted = true;
      safeSet(K_PROFILE, '1');
      state.profileKey = null;              // 本次提交已成功，下次更正重新生成
      state.daily = null;
      state.dailyEnv = null;
      state.streakHint = null;
      state.attention = [];
      state.history = { items: [], cursor: null, hasMore: false, loaded: false, loading: false };
      refreshHome();
      toast(d.baseline_reset ? '出生信息已更正，个人基线已重置。' : '建档完成，正在生成今日节律…', 'ok');
      showView('rhythm');
    }).catch(function (err) {
      var msg = readableError(err);
      if (err && err.code === 10003) { msg = '该次提交与上一次不一致，请重新提交。'; }
      showAlert(msg);
    }).then(function () {
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      $('submitProfileText').textContent = '完成建档';
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 八、今日节律屏
   * ══════════════════════════════════════════════════════════ */

  function loadDaily(force) {
    // 已有结果时直接重绘，避免重复进入出现空白（危机转介等 data 为空的响应同样适用）
    if (state.dailyEnv && !force) { renderDaily(state.dailyEnv); return Promise.resolve(); }
    busy(true);
    var today = ymd();
    // 目标日期同时用查询参数与请求头传递，兼容两种取参实现
    return apiFetch('/rhythm/daily', {
      query: { target_date: today },
      headers: { 'X-Target-Date': today }
    }).then(function (env) {
      state.dailyEnv = env;
      state.daily = env.data || {};
      renderDaily(env);
    }).catch(function (err) {
      state.dailyEnv = null;
      renderDailyError(err);
    }).then(function () {
      busy(false);
    });
  }

  /** 通道比例条：中心为 Δ=0，向右为偏亢，向左为偏虚；满格 = L4 阈值 0.60 */
  function barHtml(delta, direction) {
    var d = num(delta);
    var half = Math.min(50, (Math.abs(d) / DELTA_REF) * 50);
    var cls, style;
    if (Math.abs(d) < 0.005) {
      cls = 'flat';
      style = 'left:calc(50% - 1.5px);width:3px';
    } else if (d > 0) {
      cls = 'pos';
      style = 'left:50%;width:' + half.toFixed(2) + '%';
    } else {
      cls = 'neg';
      style = 'right:50%;width:' + half.toFixed(2) + '%';
    }
    var ticks = [20.8333, 35, 65, 79.1667].map(function (p) {
      return '<span class="bar-tick" style="left:' + p + '%"></span>';
    }).join('');
    var label = (direction || '') + ' ' + fmtDelta(d);
    return '<div class="bar" role="img" aria-label="' + esc(label.trim()) + '">' +
             '<span class="bar-axis"></span>' + ticks +
             '<span class="bar-fill ' + cls + '" style="' + style + '"></span>' +
           '</div>' +
           '<div class="bar-legend" aria-hidden="true">' +
             '<span>−0.60 偏虚</span><span>0</span><span>偏亢 +0.60</span>' +
           '</div>';
  }

  function chanRow(c) {
    var name = c.channel || c.name || '—';
    var dir = c.direction || '';
    var tagCls = dir === '偏亢' ? ' up' : (dir === '偏虚' ? ' down' : '');
    // 沿用原有 Δ 字段；若某天接口只给 raw，则退回用 raw 渲染，避免条形图空白
    var dv = (c.delta !== undefined && c.delta !== null) ? c.delta : c.raw;
    return '<div class="chan-row">' +
             '<div class="chan-top">' +
               '<span class="chan-name">' + esc(name) +
                 (dir ? '<span class="chan-tag' + tagCls + '">' + esc(dir) + '</span>' : '') +
               '</span>' +
               '<span class="chan-val">Δ ' + esc(fmtDelta(dv)) + '</span>' +
             '</div>' +
             barHtml(dv, dir) +
           '</div>';
  }

  function renderLevelCard(d) {
    var card = $('levelCard');
    var chip = $('levelChip');
    var body = $('levelBody');

    // 冷启动：未满 7 次观测 → 不显示等级；校准进度已由独立的校准卡承担
    var calibrating = (d.baseline_established === false) || (d.calibration != null && d.calibration !== undefined);
    if (d.baseline_established === true) { calibrating = false; }

    if (calibrating) {
      card.hidden = true;
      chip.hidden = true;
      body.innerHTML = '';
      return;
    }
    card.hidden = false;

    var code = d.level || '';
    var info = LEVEL_INFO[code] || null;
    var name = d.level_name || (info ? info.name : '');
    var order = info ? info.order : 0;

    if (!code && !name) {
      chip.hidden = true;
      body.innerHTML = '<p class="placeholder">本次未返回观察等级，请稍后重新读取。</p>';
      return;
    }

    chip.hidden = false;
    chip.textContent = '基于你的个人基线';

    var meter = '';
    if (order) {
      var seg = '';
      for (var s = 1; s <= 4; s++) { seg += '<span class="' + (s <= order ? 'on' : '') + '"></span>'; }
      meter = '<div class="level-meter tone-' + order + '" aria-hidden="true">' + seg + '</div>' +
              '<div class="level-scale" aria-hidden="true">' +
                '<span>L1 平和</span><span>L2 宜养</span><span>L3 宜慎</span><span>L4 宜静</span>' +
              '</div>';
    }

    body.innerHTML =
      '<div class="level-main">' +
        (code ? '<span class="level-code">' + esc(code) + '</span>' : '') +
        (name ? '<span class="level-name">' + esc(name) + '</span>' : '') +
      '</div>' +
      (info ? '<p class="level-desc">' + esc(info.desc) + '</p>' : '') +
      meter;
  }

  /* ══════════════════════════════════════════════════════════
   * 八之二、今日健康指数 / 今日关注 / 黄金时段 / 个体化 / 分享
   *   契约来源：GET /api/v1/rhythm/daily → data.index / data.personalized
   *   index 在冷启动（0 次打卡）也必须非空；personalized 需 7 次打卡后才有值。
   * ══════════════════════════════════════════════════════════ */

  /** 文本字段可能是字符串，也可能是已过护栏的 {text: '...'} 对象 */
  function textOf(v) {
    if (v === null || v === undefined) { return ''; }
    if (typeof v === 'object') { return textOf(v.text !== undefined ? v.text : v.summary); }
    return String(v);
  }

  /** 分档码 → 色调类名（A 绿 / B 蓝 / C 橙 / D 红），非 A~D 返回空串 */
  function bandTone(code) {
    var k = String(code || '').toUpperCase();
    return BAND_INFO[k] ? k.toLowerCase() : '';
  }

  /** 分档中文名：优先用接口给的 band，其次用固定档名表 */
  function bandName(code, band) {
    if (band) { return String(band); }
    var k = String(code || '').toUpperCase();
    return BAND_INFO[k] ? BAND_INFO[k].name : '';
  }

  /** 指数是否可用：index 为对象且 score 是有效数字 */
  function hasIndex(idx) {
    return !!idx && typeof idx === 'object' &&
           idx.score !== null && idx.score !== undefined && isFinite(Number(idx.score));
  }

  /** 指数卡：大分数 + 分档胶囊 + basis 原文；index 缺失时显示"指数生成中" */
  function renderIndexCard(d) {
    var body = $('indexBody');
    var idx = (d && typeof d.index === 'object') ? d.index : null;

    if (!hasIndex(idx)) {
      // 健壮性：index 缺失 / 为 null / score 不可用 → 页面照常可用，不白屏
      body.innerHTML =
        '<p class="idx-pending" id="indexPending">指数生成中</p>' +
        '<p class="idx-pending-sub">今日指数按出生时空与当日时相推算，生成后会在这一格显示。' +
        '可稍后下拉刷新，或先查看下方内容。</p>' +
        '<p class="idx-basis" id="indexBasis">' + esc(BASIS_FALLBACK) + '</p>';
      return;
    }

    var code = String(idx.band_code || '').toUpperCase();
    var tone = bandTone(code);
    var bname = bandName(code, idx.band);
    var score = Math.round(num(idx.score));

    // 四档刻度：按 A→D 排列，当前档高亮
    var scale = '<div class="idx-scale" aria-hidden="true">' + BAND_ORDER.map(function (k) {
      var cls = 'idx-scale-item' + (k === code ? ' on tone-' + k.toLowerCase() : '');
      return '<span class="' + cls + '">' + esc(BAND_INFO[k].name) + '</span>';
    }).join('') + '</div>';

    body.innerHTML =
      '<div class="idx-main">' +
        '<span class="idx-score' + (tone ? ' tone-' + tone : '') + '" id="indexScore">' +
          esc(score) + '</span>' +
        '<span class="idx-unit">分</span>' +
        (bname ? '<span class="idx-band' + (tone ? ' tone-' + tone : '') + '" id="indexBand">' +
                   esc(bname) + '</span>' : '') +
      '</div>' +
      scale +
      // basis 原文：合规标识，必须显示
      '<p class="idx-basis" id="indexBasis">' + esc(idx.basis || BASIS_FALLBACK) + '</p>';
  }

  /** 个体化校准卡：进度条 + 与"时相推算"区分开的文案 */
  function renderCalibrationCard(d) {
    var card = $('calibCard');
    var chip = $('calibChip');
    var body = $('calibBody');
    var est = (d && d.baseline_established === true);
    var c = (d && d.calibration && typeof d.calibration === 'object') ? d.calibration : null;

    if (!c) {
      // 基线已建立（或接口没给校准信息）→ 不显示校准卡
      if (est || !d) { card.hidden = true; body.innerHTML = ''; return; }
      c = {};   // 冷启动但接口没给 calibration：按下方的 count/min 兜底
    }

    var count = num(c.observation_count !== undefined ? c.observation_count : (d && d.observation_count), 0);
    var min = num(c.min_observations !== undefined ? c.min_observations : (d && d.min_observations), 7);
    if (min <= 0) { min = 7; }
    if (count < 0) { count = 0; }
    if (count > min) { count = min; }
    var pct = Math.max(0, Math.min(100, Math.round((count / min) * 100)));

    var steps = '';
    for (var i = 0; i < min; i++) { steps += '<i class="' + (i < count ? 'done' : '') + '"></i>'; }

    card.hidden = false;
    chip.hidden = false;
    chip.textContent = '校准中';
    body.innerHTML =
      '<div class="calib">' +
        '<div class="calib-top">' +
          '<span class="calib-title">基线建立中 ' + esc(count) + '/' + esc(min) + '</span>' +
          '<span class="calib-count">' + pct + '%</span>' +
        '</div>' +
        '<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="' + esc(min) +
          '" aria-valuenow="' + esc(count) + '" aria-label="个体化校准进度 ' + esc(count) + ' / ' + esc(min) + '">' +
          '<span class="progress-fill" style="width:' + pct + '%"></span>' +
        '</div>' +
        '<div class="calib-steps" aria-hidden="true">' + steps + '</div>' +
        '<p class="calib-note" id="calibMainNote">个体化校准 ' + esc(count) + '/' + esc(min) +
          '：完成后将结合你自己的历史数据，给出相对你个人基线的偏移。</p>' +
        '<p class="calib-note">上方的今日指数来自当日时相推算，不依赖打卡次数；' +
          '本进度只影响下面「关注通道」里的个体化偏移。</p>' +
        (c.note ? '<p class="calib-note">' + esc(c.note) + '</p>' : '') +
      '</div>';
  }

  /** 个体化卡：personalized 非空才出现（指数卡本身不变） */
  function renderPersonalizedCard(d) {
    var card = $('personalizedCard');
    var chip = $('personalizedChip');
    var body = $('personalizedBody');
    var p = (d && d.personalized && typeof d.personalized === 'object' &&
             !Array.isArray(d.personalized)) ? d.personalized : null;

    if (!p) { card.hidden = true; body.innerHTML = ''; return; }

    var lvl = p.level_name || p.level || '';
    chip.hidden = !lvl;
    chip.textContent = lvl ? String(lvl) : '';

    var html = '';
    if (hasIndex(p)) {
      html += '<p class="pers-score">个体化指数<strong>' + esc(Math.round(num(p.score))) + '</strong>' +
              (p.band ? esc(String(p.band)) : '') + '</p>';
    }
    var summary = textOf(p.summary) || textOf(p.text) || textOf(p.note);
    if (summary) { html += '<p class="calib-note">' + esc(summary) + '</p>'; }

    var focus = Array.isArray(p.focus) ? p.focus
              : (Array.isArray(p.channels) ? p.channels : []);
    if (focus.length) {
      html += '<div class="att-list pers-focus">' + focus.map(function (f) {
        if (f === null || f === undefined) { return ''; }
        if (typeof f !== 'object') { return '<span class="att-tag">' + esc(String(f)) + '</span>'; }
        var nm = f.channel || f.name || '';
        var dir = f.direction || '';
        return '<span class="att-tag">' + esc(nm) +
               (dir ? '<span class="att-dir ' + (dir === '偏亢' ? 'up' : (dir === '偏虚' ? 'down' : '')) + '">' +
                      esc(dir) + '</span>' : '') + '</span>';
      }).join('') + '</div>';
    }
    if (!html) { html = '<p class="placeholder">已生成个体化结果。</p>'; }
    body.innerHTML = html;
    card.hidden = false;
  }

  /** 今日关注标签的文字与方向样式 */
  function attTagHtml(item, index) {
    var nm = (item && (item.channel || item.name)) || '—';
    var dir = (item && item.direction) || '';
    var dirCls = dir === '偏亢' ? ' up' : (dir === '偏虚' ? ' down' : '');
    return '<button type="button" class="att-tag" data-att-index="' + index + '" aria-expanded="false">' +
             '<span class="att-name">' + esc(nm) + '</span>' +
             (dir ? '<span class="att-dir' + dirCls + '">' + esc(dir) + '</span>' : '') +
           '</button>';
  }

  /** 单个标签展开后的中性说明：展示 raw 数值 + 生活作息取向（无任何医学表述） */
  function attDetailHtml(item) {
    var nm = esc((item && (item.channel || item.name)) || '—');
    var dir = (item && item.direction) || '';
    var hasRaw = item && item.raw !== null && item.raw !== undefined && isFinite(Number(item.raw));
    var sentence = ATTENTION_NOTE[dir] || ATTENTION_NOTE_DEFAULT;
    return '<p class="att-line"><strong>' + nm + '</strong>' + (dir ? '（' + esc(dir) + '）' : '') + '</p>' +
           (hasRaw ? '<p class="att-line">当日相对数值：' + esc(num(item.raw).toFixed(2)) + '</p>' : '') +
           '<p class="att-line">' + esc(sentence) + '</p>' +
           '<p class="att-line att-dim">以上为时间节律的生活方式参考，仅供日常安排参考。</p>';
  }

  function renderAttentionCard(idx) {
    var body = $('attentionBody');
    var list = (idx && Array.isArray(idx.attention)) ? idx.attention.slice() : [];
    // 兼容：接口只给 channels 且带 attention 标记时，从里面挑出来
    if (!list.length && idx && Array.isArray(idx.channels)) {
      list = idx.channels.filter(function (c) { return c && c.attention === true; });
    }
    state.attention = list.filter(function (c) { return c && typeof c === 'object'; });

    if (!state.attention.length) {
      body.innerHTML = '<p class="placeholder">' +
        (hasIndex(idx)
          ? '今日各通道相对当日基准都较平稳，暂无特别需要留意的通道。'
          : '指数生成中，生成后这里会列出今日需要留意的通道。') + '</p>';
      return;
    }

    body.innerHTML =
      '<div class="att-list" role="group" aria-label="今日关注通道">' +
        state.attention.map(attTagHtml).join('') +
      '</div>' +
      '<div class="att-detail" id="attDetail" hidden></div>';
  }

  /** 点击标签：展开/收起该通道的说明（键盘 Enter/Space 同样可用） */
  function toggleAttention(btn) {
    if (!btn) { return; }
    var detail = $('attDetail');
    if (!detail) { return; }
    var i = Number(btn.getAttribute('data-att-index'));
    var item = state.attention[i];
    if (!item) { return; }
    var wasOpen = btn.getAttribute('aria-expanded') === 'true';

    var tags = $('attentionBody').querySelectorAll('.att-tag');
    for (var k = 0; k < tags.length; k++) { tags[k].setAttribute('aria-expanded', 'false'); }

    if (wasOpen) { detail.hidden = true; detail.innerHTML = ''; return; }
    btn.setAttribute('aria-expanded', 'true');
    detail.innerHTML = attDetailHtml(item);
    detail.hidden = false;
  }

  /** 'HH:MM' → 分钟数；不合法返回 null */
  function hhmmToMin(s) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(String(s === null || s === undefined ? '' : s).trim());
    if (!m) { return null; }
    var h = Number(m[1]);
    var mi = Number(m[2]);
    if (h > 24 || mi > 59) { return null; }
    return h * 60 + mi;
  }

  /** 时段 → 24 小时时间条上的分段（跨零点拆成两段，避免被条形图裁掉） */
  function winSegments(start, end) {
    var a = hhmmToMin(start);
    var b = hhmmToMin(end);
    var label = (start || '—') + '–' + (end || '—');
    if (a === null || b === null) { return { label: label, segs: [] }; }
    if (b > a) { return { label: label, segs: [[a, b]] }; }
    if (b === a) { return { label: label, segs: [] }; }
    // 23:00–01:00 这类跨越零点：拆成 [23:00, 24:00] 与 [00:00, 01:00]
    return { label: label, segs: [[a, 1440], [0, b]] };
  }

  function renderWindowsCard(idx) {
    var body = $('windowsBody');
    var list = (idx && Array.isArray(idx.windows)) ? idx.windows.slice() : [];
    list = list.filter(function (w) { return w && typeof w === 'object'; });

    if (!list.length) {
      body.innerHTML = '<p class="placeholder">' +
        (hasIndex(idx)
          ? '今日未返回特定时段，按平常作息安排即可。'
          : '指数生成中，生成后这里会显示今日的黄金时段。') + '</p>';
      return;
    }

    body.innerHTML = '<ul class="win-list">' + list.map(function (w) {
      var r = winSegments(w.start, w.end);
      var kind = (w.kind === 'golden') ? '' : ' other';
      var label = (w.name || '时段') + ' ' + r.label;
      var segHtml = r.segs.map(function (s) {
        return '<span class="win-seg' + kind + '" style="left:' + ((s[0] / 1440) * 100).toFixed(3) +
               '%;width:' + (((s[1] - s[0]) / 1440) * 100).toFixed(3) + '%"></span>';
      }).join('');
      return '<li class="win-row">' +
        '<div class="win-top">' +
          '<span class="win-name">' + esc(w.name || '时段') + '</span>' +
          '<span class="win-time">' + esc(r.label) + '</span>' +
        '</div>' +
        '<div class="win-track" role="img" aria-label="' + esc(label) + '">' + segHtml + '</div>' +
        '<div class="win-axis" aria-hidden="true"><span>00:00</span><span>12:00</span><span>24:00</span></div>' +
      '</li>';
    }).join('') + '</ul>' +
    '<p class="bar-scale-note">时间条为 00:00–24:00，标色段即对应时段的覆盖范围。' +
    '黄金时段指当日节律中更适合安排休息与活动的窗口。</p>';
  }

  /* ── 连续记录天数 ─────────────────────────────────────────── */

  /** 从历史打卡记录算"截至今天（或昨天）的连续天数" */
  function computeStreak(items) {
    if (!Array.isArray(items) || !items.length) { return 0; }
    var set = {};
    items.forEach(function (it) {
      var s = (it && it.date) || '';
      if (/^\d{4}-\d{2}-\d{2}$/.test(s)) { set[s] = 1; }
    });
    var cursor = new Date();
    cursor = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate());
    // 今天还没打卡时从昨天起算，避免白天打开就显示为 0
    if (!set[ymd(cursor)]) { cursor.setDate(cursor.getDate() - 1); }
    var n = 0;
    while (set[ymd(cursor)] && n < 400) { n++; cursor.setDate(cursor.getDate() - 1); }
    return n;
  }

  /** 连续记录 chip：优先用接口回传，其次用历史记录推导，再次用累计观测天数 */
  function renderStreak(d) {
    var chip = $('streakChip');
    var n = null;

    var hint = state.streakHint;
    if (hint === null && d) {
      if (d.streak_days !== undefined && d.streak_days !== null) { hint = num(d.streak_days, 0); }
      else if (d.consecutive_days !== undefined && d.consecutive_days !== null) { hint = num(d.consecutive_days, 0); }
    }
    if (hint !== null && num(hint) > 0) { n = num(hint); }

    if (n === null && state.history.loaded) {
      var s = computeStreak(state.history.items);
      if (s > 0) { n = s; }
    }
    if (n !== null && n > 0) {
      chip.textContent = '连续记录 ' + n + ' 天';
      chip.hidden = false;
      return;
    }

    // 取不到连续天数时退一步：显示累计观测天数（同样取不到就不显示）
    var oc = num(d && d.observation_count, 0);
    if (oc > 0) {
      chip.textContent = '已记录 ' + oc + ' 天';
      chip.hidden = false;
      return;
    }
    chip.hidden = true;
  }

  /* ── 分享文案（纯文本 + 复制，不引入任何外网 SDK）──────────── */

  function buildShareText() {
    var d = state.daily || {};
    var idx = (d && typeof d.index === 'object') ? d.index : null;
    var head = 'AI元健康 · 做自己的健康导师——我在用它看每天的节律';
    if (hasIndex(idx)) {
      var code = String(idx.band_code || '').toUpperCase();
      var bname = bandName(code, idx.band);
      head += '：今日健康指数 ' + Math.round(num(idx.score)) + (bname ? '（' + bname + '）' : '');
    }
    return head + '。按出生时空看当日节律取向，仅供参考。 ' + SITE_URL;
  }

  function renderShareCard() {
    $('shareText').textContent = buildShareText();
  }

  /** 复制兜底：老浏览器 / 无剪贴板权限时用临时 textarea + execCommand */
  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, ta.value.length);
      var ok = document.execCommand ? document.execCommand('copy') : false;
      document.body.removeChild(ta);
      return !!ok;
    } catch (e) { return false; }
  }

  function copyShare() {
    var text = $('shareText').textContent || '';
    function done(ok) {
      toast(ok ? '分享文案已复制，可直接粘贴。' : '复制失败，请长按上方文本手动复制。', ok ? 'ok' : 'err');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); },
                                              function () { done(fallbackCopy(text)); });
      return;
    }
    done(fallbackCopy(text));
  }

  function renderDaily(env) {
    var d = env.data || {};
    state.daily = d;

    $('rhythmDate').textContent = ymdLabel(d.date) || ymdLabel(ymd());

    // ① 指数卡永远最先渲染：建档后首屏第一眼就能看到分数
    var idx = (d && typeof d.index === 'object') ? d.index : null;
    renderIndexCard(d);
    renderCalibrationCard(d);
    renderPersonalizedCard(d);
    renderAttentionCard(idx);
    renderWindowsCard(idx);
    renderStreak(d);
    renderShareCard();

    renderLevelCard(d);

    // 关注通道
    var focus = Array.isArray(d.focus) ? d.focus : [];
    var fbody = $('focusBody');
    if (focus.length) {
      fbody.innerHTML = '<div class="chan-list">' + focus.map(chanRow).join('') + '</div>' +
        '<p class="bar-scale-note">比例条以 Δ=0 为中心：向右为偏亢，向左为偏虚；' +
        '刻度依次为 0.18（L2）、0.35（L3），满格为 0.60（L4 阈值）。</p>';
    } else if (d.baseline_established === false || d.calibration) {
      fbody.innerHTML = '<p class="placeholder">校准中，暂不输出关注通道。' +
        '完成 7 次观测后即可看到「相对你自己」的偏移方向。</p>';
    } else {
      fbody.innerHTML = '<p class="placeholder">今日各通道相对你的基线均无明显偏移。</p>';
    }

    // 全部十二通道
    var channels = Array.isArray(d.channels) ? d.channels : [];
    var cbody = $('channelsBody');
    if (channels.length) {
      cbody.innerHTML = '<div class="chan-list">' + channels.map(chanRow).join('') + '</div>' +
        '<p class="bar-scale-note">同一比例尺：满格对应 L4 阈值 0.60。</p>';
    } else if (d.baseline_established === false || d.calibration) {
      cbody.innerHTML = '<p class="placeholder">校准中，通道态势在基线建立后展示。</p>';
    } else {
      cbody.innerHTML = '<p class="placeholder">本次未返回通道数据。</p>';
    }

    // 生活方式取向
    var txt = d.text;
    var textVal = (txt && typeof txt === 'object') ? (txt.text || '') : (txt || '');
    var abody = $('adviceBody');
    if (textVal) {
      var hits = (txt && typeof txt === 'object' && Array.isArray(txt.guardrail_hits)) ? txt.guardrail_hits : [];
      var action = (txt && typeof txt === 'object') ? (txt.guardrail_action || '') : '';
      abody.innerHTML =
        '<p class="compliance-text">' + esc(textVal) + '</p>' +
        (action === 'degraded'
          ? '<p class="bar-scale-note">该表述涉及需专业判断的内容，已按合规要求降级为安全话术。</p>'
          : '') +
        (hits.length ? '<p class="bar-scale-note">合规过滤命中：' + esc(hits.join('、')) + '</p>' : '');
    } else {
      abody.innerHTML = '<p class="placeholder">本次未返回生活方式取向文本。</p>';
    }

    // 依据链
    var lineage = Array.isArray(d.lineage) ? d.lineage : [];
    var lbody = $('lineageBody');
    if (lineage.length) {
      lbody.innerHTML = '<div class="lineage-list">' + lineage.map(function (item) {
        if (item && typeof item === 'object') {
          var rid = item.rule_id || item.rid || item.id || '';
          var nm = item.name || item.rule_name || '';
          var src = item.source || item.classical || item.origin || '';
          var quote = item.quote || item.point || '';
          return '<div class="lineage-item">' +
            (rid ? '<div><span class="lineage-rid">' + esc(rid) + '</span></div>' : '') +
            (nm ? '<div class="lineage-name">' + esc(nm) + '</div>' : '') +
            (src ? '<div class="lineage-src">出处：' + esc(src) + '</div>' : '') +
            (quote ? '<div class="lineage-quote">要点：' + esc(quote) + '</div>' : '') +
          '</div>';
        }
        // 字符串形态：[规则ID] 规则名｜出处：xxx｜要点：yyy
        var s = String(item);
        var m = s.match(/^\[([^\]]+)\]\s*([^｜|]*)[｜|]\s*出处：([^｜|]*)(?:[｜|]\s*要点：([\s\S]*))?$/);
        if (m) {
          return '<div class="lineage-item">' +
            '<div><span class="lineage-rid">' + esc(m[1]) + '</span></div>' +
            (m[2] ? '<div class="lineage-name">' + esc(m[2].trim()) + '</div>' : '') +
            (m[3] ? '<div class="lineage-src">出处：' + esc(m[3].trim()) + '</div>' : '') +
            (m[4] ? '<div class="lineage-quote">要点：' + esc(m[4].trim()) + '</div>' : '') +
          '</div>';
        }
        return '<div class="lineage-item"><div class="lineage-raw">' + esc(s) + '</div></div>';
      }).join('') + '</div>';
    } else {
      lbody.innerHTML = '<p class="placeholder">本次未返回依据链。</p>';
    }

    // 合规声明区
    $('disclaimerText').textContent = d.disclaimer || DISCLAIMER_FALLBACK;
    $('referralText').textContent = d.referral || REFERRAL_FALLBACK;
    var aiTag = $('aiTag');
    aiTag.hidden = (d.ai_generated === false);

    var meta = [];
    if (d.rule_version || env.rule_version) { meta.push(['规则版本', d.rule_version || env.rule_version]); }
    if (d.engine_version) { meta.push(['引擎版本', d.engine_version]); }
    if (d.param_hash) { meta.push(['参数摘要', String(d.param_hash).slice(0, 16)]); }
    if (env.trace_id) { meta.push(['追踪号', env.trace_id]); }
    $('metaList').innerHTML = meta.map(function (kv) {
      return '<dt>' + esc(kv[0]) + '</dt><dd>' + esc(kv[1]) + '</dd>';
    }).join('');

    renderCrisis(env, d);

    // 静默预取历史记录：只为推导"连续记录 n 天"，失败不影响页面
    if (!state.history.loaded && !state.history.loading) { loadHistory(false, true); }
  }

  /** 危机转介：按契约 70004 为流程码，展示就医引导 */
  function renderCrisis(env, d) {
    var box = $('crisisBox');
    var isCrisis = (env && env.code === CODE_CRISIS) ||
                   (d && (d.crisis === true || d.crisis_referral === true ||
                          d.referral_kind === 'crisis' || d.urgent === true));
    if (!isCrisis) { box.hidden = true; return; }
    var t = (d && (d.crisis_text || d.crisis_notice || d.message)) || '';
    $('crisisText').textContent = t ||
      '如果你此刻感到难以承受，请立即联系专业帮助，不要独自承担。';
    box.hidden = false;
  }

  function renderDailyError(err) {
    var msg;
    if (err && err.code === CODE_NO_PROFILE) {
      msg = '尚未完成生辰建档，请先填写出生日期、时刻与出生地。';
      $('btnStart').querySelector('span').textContent = '去建档';
    } else {
      msg = readableError(err);
    }
    showAlert(msg);

    // 页面不白屏：各区块给出可读的占位说明
    $('rhythmDate').textContent = ymdLabel(ymd());
    state.attention = [];
    $('streakChip').hidden = true;
    $('indexBody').innerHTML =
      '<p class="idx-pending">暂时无法读取今日指数</p>' +
      '<p class="idx-pending-sub">接口暂时没有返回数据，请稍后重试；' +
      '下方其余区块仍可正常浏览。</p>' +
      '<p class="idx-basis" id="indexBasis">' + esc(BASIS_FALLBACK) + '</p>';
    $('calibCard').hidden = true;
    $('calibBody').innerHTML = '';
    $('personalizedCard').hidden = true;
    $('personalizedBody').innerHTML = '';
    $('attentionBody').innerHTML = '<p class="placeholder">暂时无法读取今日关注。</p>';
    $('windowsBody').innerHTML = '<p class="placeholder">暂时无法读取黄金时段。</p>';
    $('levelCard').hidden = false;
    $('levelChip').hidden = true;
    $('levelBody').innerHTML = '<p class="placeholder">暂时无法读取观察等级。</p>';
    $('focusBody').innerHTML = '<p class="placeholder">暂时无法读取关注通道。</p>';
    $('adviceBody').innerHTML = '<p class="placeholder">暂时无法读取生活方式取向。</p>';
    $('channelsBody').innerHTML = '<p class="placeholder">暂时无法读取通道态势。</p>';
    $('lineageBody').innerHTML = '<p class="placeholder">暂时无法读取依据链。</p>';
    $('disclaimerText').textContent = DISCLAIMER_FALLBACK;
    $('referralText').textContent = REFERRAL_FALLBACK;
    $('metaList').innerHTML = '';
    $('crisisBox').hidden = true;
    renderShareCard();          // 分享文案仍可用（退化为不含分数的通用文案）
  }

  /* ══════════════════════════════════════════════════════════
   * 九、打卡
   * ══════════════════════════════════════════════════════════ */

  function checkin() {
    if (state.checkinBusy) { return; }
    var on = ymd();
    // 幂等键按日固定：同一天重复点击复用同一个键，服务端据此只计一次观测
    var keyName = 'yh.checkin_key.' + on;
    var key = safeGet(keyName);
    if (!key) { key = uid('checkin-'); safeSet(keyName, key); }

    state.checkinBusy = true;
    var btn = $('btnCheckin');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    $('checkinText').textContent = '正在打卡…';

    apiFetch('/checkin', {
      method: 'POST',
      idempotencyKey: key,
      body: { on: on }
    }).then(function (env) {
      var d = env.data || {};
      var n = d.observation_count;
      // 打卡结果里若带连续天数就直接采用，供顶部"连续记录 n 天"使用
      if (d.streak_days !== undefined && d.streak_days !== null) { state.streakHint = num(d.streak_days, 0); }
      else if (d.consecutive_days !== undefined && d.consecutive_days !== null) { state.streakHint = num(d.consecutive_days, 0); }
      var min = (state.daily && state.daily.min_observations) || 7;
      var txt = '打卡成功';
      if (n !== undefined && n !== null) {
        txt += d.established ? '，个人基线已建立。' : '，已累计 ' + n + '/' + min + ' 次观测。';
      }
      toast(txt, 'ok');
      return loadDaily(true);       // 重新读取，让校准进度即时更新
    }).catch(function (err) {
      showAlert(readableError(err));
    }).then(function () {
      state.checkinBusy = false;
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      $('checkinText').textContent = '今日打卡';
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 十、历史记录（游标分页）
   * ══════════════════════════════════════════════════════════ */

  function openHistory() {
    $('sheetBackdrop').hidden = false;
    $('historySheet').hidden = false;
    document.body.style.overflow = 'hidden';
    $('btnCloseHistory').focus();
    if (!state.history.loaded) { loadHistory(false); }
  }

  function closeHistory() {
    $('sheetBackdrop').hidden = true;
    $('historySheet').hidden = true;
    document.body.style.overflow = '';
    $('btnHistory').focus();
  }

  function histItem(it) {
    var obs = (it && it.observed) || {};
    var keys = Object.keys(obs);
    var chips = keys.slice(0, 4).map(function (k) {
      return '<span>' + esc(k) + ' ' + esc(num(obs[k]).toFixed(2)) + '</span>';
    }).join('');
    if (keys.length > 4) { chips += '<span>+' + (keys.length - 4) + '</span>'; }
    if (!keys.length) { chips = '<span>无明细</span>'; }
    return '<div class="hist-item"><div style="flex:1 1 auto;min-width:0">' +
      '<div class="hist-date">' + esc(ymdLabel(it.date) || it.date || '—') + '</div>' +
      '<div class="hist-meta">已打卡 · 观测通道 ' + keys.length + ' 项</div>' +
      '<div class="hist-obs">' + chips + '</div>' +
    '</div></div>';
  }

  /** silent = true 时用于后台预取（只为推导连续天数），失败不写错误文案 */
  function loadHistory(more, silent) {
    if (state.history.loading) { return; }
    state.history.loading = true;

    if (!more) {
      state.history.items = [];
      state.history.cursor = null;
      $('historyBody').innerHTML = '<p class="placeholder">正在读取…</p>';
    }
    var btnMore = $('btnMoreHistory');
    btnMore.hidden = true;

    var query = { limit: 30 };
    if (more && state.history.cursor) { query.cursor = state.history.cursor; }
    var headers = { 'X-Limit': '30' };
    if (more && state.history.cursor) { headers['X-Cursor'] = state.history.cursor; }

    apiFetch('/rhythm/history', { query: query, headers: headers }).then(function (env) {
      var d = env.data || {};
      var items = Array.isArray(d.items) ? d.items : [];
      state.history.items = more ? state.history.items.concat(items) : items;
      state.history.cursor = d.next_cursor || null;
      state.history.hasMore = !!d.has_more;
      state.history.loaded = true;

      if (!state.history.items.length) {
        $('historyBody').innerHTML =
          '<p class="placeholder">还没有打卡记录。回到今日节律页点击「今日打卡」，' +
          '累计 7 次观测后即可建立你的个人基线。</p>';
      } else {
        $('historyBody').innerHTML =
          '<div class="hist-list">' + state.history.items.map(histItem).join('') + '</div>' +
          (state.history.hasMore ? '' :
            '<p class="bar-scale-note">已到最后一页。</p>');
      }
      btnMore.hidden = !state.history.hasMore;
      renderStreak(state.daily);      // 历史到手后刷新"连续记录 n 天"
    }).catch(function (err) {
      if (silent) { /* 后台预取失败：不打扰用户，打开历史面板时会重试 */ }
      else if (!more) {
        $('historyBody').innerHTML =
          '<p class="placeholder">历史记录读取失败：' + esc(readableError(err)) + '</p>';
      } else {
        toast('加载更多失败，请稍后重试。', 'err');
      }
      btnMore.hidden = !state.history.hasMore;
    }).then(function () {
      state.history.loading = false;
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 十一、事件绑定与启动
   * ══════════════════════════════════════════════════════════ */

  function bind() {
    $('btnStart').addEventListener('click', function () { showView('profile'); });
    $('btnHomeRhythm').addEventListener('click', function () { showView('rhythm'); });

    $('btnBack').addEventListener('click', function () {
      if (state.view === 'rhythm' && !state.profileCompleted) { showView('profile'); return; }
      showView('home');
    });

    $('inCity').addEventListener('change', onCityChange);
    $('inLng').addEventListener('input', function () { fieldError('errCoord', ''); });
    $('inLat').addEventListener('input', function () { fieldError('errCoord', ''); });
    $('inBirthDate').addEventListener('change', function () { fieldError('errBirthDate', ''); });
    $('profileForm').addEventListener('submit', submitProfile);

    $('btnShowConsent').addEventListener('click', function () {
      var body = $('consentBody');
      body.hidden = !body.hidden;
      this.setAttribute('aria-expanded', body.hidden ? 'false' : 'true');
    });
    $('btnShowConsent').setAttribute('aria-expanded', 'false');

    $('btnCheckin').addEventListener('click', checkin);
    $('btnHistory').addEventListener('click', openHistory);
    $('btnCloseHistory').addEventListener('click', closeHistory);
    $('sheetBackdrop').addEventListener('click', closeHistory);
    $('btnMoreHistory').addEventListener('click', function () { loadHistory(true, false); });

    // 今日关注：事件委托，标签是 <button>，键盘 Enter/Space 与点击同路
    $('attentionBody').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.classList && el.classList.contains('att-tag'))) { el = el.parentNode; }
      if (el && el !== this && el.classList && el.classList.contains('att-tag')) { toggleAttention(el); }
    });

    // 分享文案复制（纯文本，不依赖任何外网 SDK）
    $('btnCopyShare').addEventListener('click', copyShare);

    $('alertClose').addEventListener('click', hideAlert);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !$('historySheet').hidden) { closeHistory(); }
    });
  }

  function boot() {
    try {
      buildCityOptions();
      refreshHome();
      bind();
      // 首次进入先取游客令牌（失败也不阻塞页面渲染）
      ensureToken(false).then(function () {
        if (!state.profileCompleted) { return; }
        // 已建档用户：静默预取今日节律，减少进入时的等待
        return apiFetch('/rhythm/daily', {
          query: { target_date: ymd() },
          headers: { 'X-Target-Date': ymd() }
        }).then(function (env) {
          state.dailyEnv = env;
          state.daily = env.data || {};
        }, function () { /* 预取失败不影响首屏，进入节律屏时会再次读取并提示 */ });
      });
      showView('home');
    } catch (e) {
      // 任何初始化异常都给出可读提示，绝不白屏
      showAlert('页面初始化失败，请刷新后重试。');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})();
