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
  // v14 首页签到：本机按日留痕（数显账号=设备绑定，本机记录与账号一一对应）
  var K_CHECKED = 'yh.checked.';
  // v6 邀请链接：待绑定邀请码 + 待绑定分享人昵称（来自链接，仅用于落地页展示）
  var K_PENDING_INVITE = 'yh.pending_invite';
  var K_PENDING_NAME = 'yh.pending_invite_name';
  // v6 自动绑定留痕：{code, at, ok}，同一邀请码只自动提交一次（未成功时 24 小时后可再试）
  var K_BIND_LOG = 'yh.invite_bind_log';

  // 邀请码：8 位大写字母或数字
  var INVITE_CODE_RE = /^[A-Z0-9]{8}$/;
  // 同一邀请码未成功时的重试窗口（毫秒）
  var BIND_RETRY_WINDOW = 24 * 3600 * 1000;

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

  /**
   * v14：「是否已建档」唯一权威来源是服务端（/auth/guest 与登录接口都带
   * profile_completed）。本机 localStorage 只是镜像，换账号/换手机号登录后必须回填，
   * 否则登录到有档案的账号时首页仍显示「开始建档」、看不到今日指数。
   * 只有服务端明确回了布尔值才写；字段缺失（老版本部署）时保持原状不动。
   */
  function applyProfileFlag(d) {
    if (!d || typeof d.profile_completed !== 'boolean') { return; }
    state.profileCompleted = d.profile_completed;
    if (d.profile_completed) { safeSet(K_PROFILE, '1'); } else { safeDel(K_PROFILE); }
  }

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
      applyProfileFlag(d);          // v14：以服务端为准回填"是否已建档"
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
        applyProfileFlag(d2);       // v14：同上
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
    streakHint: null,         // 打卡接口回传的连续天数（有则优先使用）
    social: {                 // 轻社交三件套（好友圈 / 健康排行 / 健康互促）
      loaded: false, loading: false,
      inviteCode: '', nickname: '',
      inviteUrl: '',          // 服务端返回的邀请链接（取不到时用本站地址兜底拼装）
      shareText: '',          // 服务端返回的分享文案（含昵称）；取不到时本机拼装
      referrer: null,         // 推荐人归属 {nickname, bound_at}
      referral: null, referralLoaded: false,
      pendingInvite: '',      // 待自动绑定的邀请码（来自落地链接）
      pendingName: '',        // 待绑定链接里带的分享人昵称（仅显示用）
      nicknameSaving: false,
      bind: { code: '', inFlight: null },
      privacy: { share_index: false, share_streak: false, in_ranking: false },
      privacySaving: {},
      friends: [], pending: [], accepted: [], loadedFriends: false,
      feed: [], feedCursor: null, loadedFeed: false, localFeed: [],
      ranking: null,          // null = 未取到；数组 = 已取到
      me: null,               // 服务端返回的本人摘要（可选，用于分数/连续天数兜底）
      templates: [], quotaLeft: 3, quotaTotal: 3,
      cheerTarget: null, confirmAction: null,
      err: { invite: false, privacy: false, friends: false, feed: false,
             ranking: false, templates: false }
    },
    /* v8：订阅（测试期用积分支付，不接任何真实支付通道） */
    subscribe: {
      plans: [], fallback: false, selectedId: '',
      loaded: false, loading: false, err: false,
      busy: false, lastOrder: null
    },
    /* v8：我的积分 / 推广收益 */
    points: {
      // err 的三项：失败时存错误对象（可直接 readableError），成功时为 false
      balance: null, earned: null, spent: null, loaded: false,
      err: { balance: false, ledger: false, commission: false },
      ledger: { items: [], page: 0, hasMore: false, loaded: false, loading: false },
      commission: null
    },
    /* v11：家庭健康档案（添加家人）——家人的指数与本人 daily 同一条链路；等级恒不显示 */
    family: {
      loaded: false, loading: false, err: null,
      members: [], summary: null, reminders: [], disclaimer: '',
      editingId: '',            // 非空 = 表单处于「编辑」态；空 = 「添加」态
      saving: false,
      remindTarget: null,       // 关怀提醒抽屉当前指向的家人 {family_id, nickname}
      remindKind: 'care',       // 抽屉里选中的提醒类型
      pwdSaving: false          // v15：修改密码在途
    }
  };

  var VIEWS = ['home', 'profile', 'rhythm', 'friends', 'subscribe', 'points', 'family',
               'mine', 'account', 'help'];

  // 只在顶级页显示底部导航（APP 感）；其余页面用返回键，避免"回到一半"的困惑
  var TAB_VIEWS = ['home', 'rhythm', 'mine'];
  // ★ v15 返回栈：以前 btnBack 写死回首页 —— 从「我的 → 账号与安全」点返回会直接跳回首页，
  //   用户会以为"我的"丢了。现在按进入顺序回退；点底部 tab 视为重新开始（清栈）。
  var viewStack = [];

  function syncTabbar() {
    var bar = $('tabbar');
    if (!bar) { return; }
    var on = TAB_VIEWS.indexOf(state.view) >= 0;
    bar.hidden = !on;
    document.body.classList.toggle('has-tabbar', on);
    var items = bar.querySelectorAll('.tab-item');
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle('is-on', items[i].getAttribute('data-tab') === state.view);
    }
  }

  function showView(name, opts) {
    if (VIEWS.indexOf(name) < 0) { name = 'home'; }
    var keep = opts || {};
    var prev = state.view;
    // 返回栈：进入"非顶级页"时记住来处；切到顶级 tab 视为重新开始（清栈）
    if (prev !== name && keep.push !== false) {
      if (TAB_VIEWS.indexOf(name) < 0) { viewStack.push(prev); }
      else { viewStack.length = 0; }
    }
    state.view = name;
    VIEWS.forEach(function (v) {
      var el = $('screen-' + v);
      if (el) { el.hidden = (v !== name); }
    });
    $('btnBack').hidden = (name === 'home');
    refreshAuthEntry();          // v12：登录/注册入口只在首屏显示
    syncTabbar();                // v15：底部导航只出现在顶级页
    hideAlert();
    window.scrollTo(0, 0);

    // 无障碍：切换视图后把焦点移到该屏标题
    var title = $('screen-' + name).querySelector('.screen-title, .hero-title');
    if (title) {
      title.setAttribute('tabindex', '-1');
      try { title.focus({ preventScroll: true }); } catch (e) { title.focus(); }
    }

    if (name === 'rhythm') { loadDaily(); }
    if (name === 'friends') { loadSocial(true); }
    if (name === 'subscribe') { loadSubscribe(true); }
    if (name === 'points') { loadPoints(true); }
    if (name === 'family') { loadFamily(true); }
    if (name === 'mine') { renderMine(); }
    if (name === 'account') { renderAccount(); }
    if (name === 'help') { renderHelp(); }
  }

  /* ══════════════════════════════════════════════════════════
   * 六、首屏
   * ══════════════════════════════════════════════════════════ */

  function refreshHome() {
    $('btnHomeRhythm').hidden = !state.profileCompleted;
    $('btnStart').querySelector('span').textContent =
      state.profileCompleted ? '重新建档' : '开始建档';
    renderHomeDaily();         // v14：首页直接显示今日指数 + 首页签到
    refreshFamilyEntry();      // v11：入口文案随「已有家人数」变化
  }

  /* ══════════════════════════════════════════════════════════
   * 六之二、v14 首页今日指数 + 首页签到
   *   师父令（2026-10-09）：「用户登录首页就应该看到打分指数」
   *                       「我怎么看今天的健康指数，在哪里签到？」
   *   口径：与今日节律屏同一份数据（GET /rhythm/daily → data.index），
   *        首页只做「分数 + 分档 + basis」摘要，明细仍在节律屏；
   *        签到直接复用 POST /checkin，与节律屏按钮同一幂等键。
   * ══════════════════════════════════════════════════════════ */

  /** 今日是否已签到（本机按日留痕；账号按设备绑定，故本机记录即该账号记录） */
  function checkedToday() { return safeGet(K_CHECKED + ymd()) === '1'; }

  function markCheckedToday(on) {
    try { safeSet(K_CHECKED + (on || ymd()), '1'); } catch (e) { /* 忽略 */ }
    syncCheckinButtons();
  }

  /** 两个签到按钮（节律屏 + 首页）状态保持一致 */
  function syncCheckinButtons() {
    var done = checkedToday();
    var ht = $('homeCheckinText');
    if (ht) { ht.textContent = done ? '今日已签到' : '今日签到'; }
    var hb = $('btnHomeCheckin');
    if (hb) {
      hb.disabled = done || state.checkinBusy;
      hb.classList.toggle('is-done', done);
    }
  }

  /** 首页指数卡（未建档整卡隐藏；指数未就绪显示同一条兜底文案） */
  function renderHomeDaily() {
    var card = $('homeDailyCard');
    if (!card) { return; }
    if (!state.profileCompleted) { card.hidden = true; return; }
    card.hidden = false;

    var d = state.daily || {};
    var idx = (d && typeof d.index === 'object') ? d.index : null;
    var body = $('homeDailyBody');
    var dateEl = $('homeDailyDate');
    if (dateEl) { dateEl.textContent = ymdLabel(d.date) || ymdLabel(ymd()); }

    if (!hasIndex(idx)) {
      body.innerHTML =
        '<p class="idx-pending">指数生成中</p>' +
        '<p class="idx-pending-sub">今日指数按你的出生时空与当日时相推算，' +
        '生成后会在这一格直接显示；可稍后刷新本页。</p>';
    } else {
      var code = String(idx.band_code || '').toUpperCase();
      var tone = bandTone(code);
      var bname = bandName(code, idx.band);
      var score = Math.round(num(idx.score));
      body.innerHTML =
        '<div class="idx-main">' +
          '<span class="idx-score' + (tone ? ' tone-' + tone : '') + '">' + esc(score) + '</span>' +
          '<span class="idx-unit">分</span>' +
          (bname ? '<span class="idx-band' + (tone ? ' tone-' + tone : '') + '">' +
                     esc(bname) + '</span>' : '') +
        '</div>' +
        '<div class="idx-scale" aria-hidden="true">' + BAND_ORDER.map(function (k) {
          var cls = 'idx-scale-item' + (k === code ? ' on tone-' + k.toLowerCase() : '');
          return '<span class="' + cls + '">' + esc(BAND_INFO[k].name) + '</span>';
        }).join('') + '</div>' +
        // basis 原文：合规标识，必须显示
        '<p class="idx-basis">' + esc(idx.basis || BASIS_FALLBACK) + '</p>';
    }
    syncCheckinButtons();
  }

  /* ══════════════════════════════════════════════════════════
   * 七、建档屏
   * ══════════════════════════════════════════════════════════ */

  /* 城市下拉的选项 HTML（**唯一一份**）：建档屏与家庭档案表单共用，避免两处各写一遍分组逻辑 */
  function cityOptionsHtml() {
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
    return html;
  }

  function buildCityOptions() {
    var sel = $('inCity');
    sel.innerHTML = cityOptionsHtml();
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
      // v6：建档成功后自动绑定邀请人 + 自动成为好友。
      // 异步、不阻塞：绑定失败只轻提示，绝不影响建档与指数卡展示。
      maybeAutoBindInvite();
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
    var head = 'AI数显 · 元健康（做自己的健康导师）——我在用它看每天的节律';
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
    renderHomeDaily();           // v14：首页那张指数卡与节律屏同源同步
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

  /**
   * 打卡。v14：节律屏与首页两个按钮共用同一实现。
   *   btnId / textId —— 触发按钮与其文案节点的 id（默认节律屏那一对）
   *   幂等键按日固定：同一天重复点击复用同一个键，服务端据此只计一次观测
   */
  function checkin(btnId, textId) {
    if (state.checkinBusy) { return; }
    var on = ymd();
    var keyName = 'yh.checkin_key.' + on;
    var key = safeGet(keyName);
    if (!key) { key = uid('checkin-'); safeSet(keyName, key); }

    state.checkinBusy = true;
    var btn = $(btnId || 'btnCheckin');
    var txtEl = $(textId || 'checkinText');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    txtEl.textContent = '正在打卡…';

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
      markCheckedToday(true);      // v14：两个按钮同时切到「今日已签到」
      return loadDaily(true);       // 重新读取，让校准进度即时更新
    }).catch(function (err) {
      showAlert(readableError(err));
    }).then(function () {
      state.checkinBusy = false;
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      txtEl.textContent = '今日打卡';
      syncCheckinButtons();        // v14：失败时首页按钮恢复可点，成功时保持「已签到」
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 十、历史记录（游标分页）
   * ══════════════════════════════════════════════════════════ */

  function openHistory() {
    openSheet('historySheet', 'btnCloseHistory');
    if (!state.history.loaded) { loadHistory(false); }
  }

  function closeHistory() {
    closeSheet('historySheet');
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
      // v14：历史里若已有今天，说明今天签到过 → 首页按钮切到「今日已签到」
      if (!more && state.history.items.some(function (it) {
        return String(it && it.date || '').slice(0, 10) === ymd();
      })) { markCheckedToday(true); }
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
   * 十一、轻社交三件套（好友圈 / 健康排行 / 健康互促）
   *
   *  口径来源：变更单 2026-10-08 §三（接口契约与可见性规则）
   *    · accepted 关系才可见；pending 双方互不可见分数与动态
   *    · feed 中分数仅当「对方」share_index=true；连续天数仅当 share_streak=true
   *    · ranking 仅列出 in_ranking=true 的 accepted 好友与本人（本人未开启则不出现）
   *    · 三开关只影响「别人看我」，关闭后下一次请求即生效
   *  合规（§二）：默认全关；只展示昵称 + 指数分档/分数 + 连续天数；
   *    绝不展示生辰、体征、通道明细、病历；加油只用中性模板；每日上限 3 次。
   * ══════════════════════════════════════════════════════════ */

  var K_PRIVACY = 'yh.social_privacy';     // 本机镜像（服务端为准；接口未返回时用它兜底）
  var CHEER_DAILY_LIMIT = 3;               // 每人每日加油上限（变更单 §二）

  /* 加油模板兜底：全部为中性作息问候，不含任何诊疗/疾病表述。
     接口 GET /friends/cheer/templates 可用时以接口为准。 */
  var CHEER_TEMPLATES_FALLBACK = [
    { template_id: 't1', text: '今天也照顾好自己' },
    { template_id: 't2', text: '记得喝口水，歇一会儿' },
    { template_id: 't3', text: '早点休息，明天见' },
    { template_id: 't4', text: '你今天已经很棒了' },
    { template_id: 't5', text: '一起把好习惯坚持下去' },
    { template_id: 't6', text: '慢慢来，节奏最重要' }
  ];

  /* 三个独立开关：标题 + 一句白话说明「别人能看到什么」 */
  var PRIVACY_ITEMS = [
    { key: 'share_index', title: '公开今日指数',
      desc: '开启后，好友能看到你今天的健康指数分数；关闭时对方只看到「未公开」。' },
    { key: 'share_streak', title: '公开连续记录天数',
      desc: '开启后，好友能看到你的连续记录天数；关闭时完全不显示这一项。' },
    { key: 'in_ranking', title: '参与健康排行',
      desc: '开启后，你会出现在好友圈的健康排行里；关闭后不进榜，别人也看不到你的名次。' }
  ];

  function privItem(key) {
    for (var i = 0; i < PRIVACY_ITEMS.length; i++) {
      if (PRIVACY_ITEMS[i].key === key) { return PRIVACY_ITEMS[i]; }
    }
    return null;
  }

  function hasNum(v) { return v !== null && v !== undefined && v !== '' && isFinite(Number(v)); }

  function scoreText(v) { return hasNum(v) ? String(Math.round(Number(v))) : ''; }

  function friendId(f) {
    if (!f || typeof f !== 'object') { return ''; }
    return String(f.friend_id || f.member_id || f.id || f.uid || '');
  }

  function initials(nick) {
    var s = String(nick || '好');
    return s.slice(0, 1) || '好';
  }

  function isSelfItem(it) {
    return !!(it && typeof it === 'object' &&
      (it.is_me === true || it.self === true || it.me === true ||
       it.relation === 'self' || it.friend_id === 'me' || it.member_id === 'me'));
  }

  /** 相对时间（动态用）；解析不出来就返回空串，不显示时间 */
  function relTime(v) {
    if (v === null || v === undefined || v === '') { return ''; }
    var t;
    if (typeof v === 'number') {
      t = (v < 1e12) ? v * 1000 : v;
    } else {
      var s = String(v).trim();
      var n = Number(s);
      if (isFinite(n) && s.replace(/[^0-9]/g, '').length >= 10) {
        t = (n < 1e12) ? n * 1000 : n;
      } else {
        t = Date.parse(s.replace(' ', 'T'));
      }
    }
    if (!isFinite(t)) { return ''; }
    var diff = Date.now() - t;
    if (diff < 0) { diff = 0; }
    var min = Math.floor(diff / 60000);
    if (min < 1) { return '刚刚'; }
    if (min < 60) { return min + ' 分钟前'; }
    var hr = Math.floor(min / 60);
    if (hr < 24) { return hr + ' 小时前'; }
    var day = Math.floor(hr / 24);
    if (day < 7) { return day + ' 天前'; }
    var dt = new Date(t);
    return (dt.getMonth() + 1) + '月' + dt.getDate() + '日';
  }

  /* ── 隐私镜像（默认全关；服务端返回时以服务端为准）────────── */

  function loadPrivacyLocal() {
    var p = { share_index: false, share_streak: false, in_ranking: false };
    try {
      var raw = safeGet(K_PRIVACY);
      var o = raw ? JSON.parse(raw) : null;
      if (o && typeof o === 'object') {
        PRIVACY_ITEMS.forEach(function (it) { if (o[it.key] === true) { p[it.key] = true; } });
      }
    } catch (e) { /* 本地镜像损坏 → 用默认全关，绝不默认公开 */ }
    return p;
  }

  function savePrivacyLocal(p) {
    try { safeSet(K_PRIVACY, JSON.stringify(p)); } catch (e) { /* 忽略 */ }
  }

  /** 用接口返回的开关覆盖本机镜像；返回是否真的拿到了布尔值 */
  function mergePrivacy(d) {
    if (!d || typeof d !== 'object' || Array.isArray(d)) { return false; }
    var found = false;
    var p = state.social.privacy;
    PRIVACY_ITEMS.forEach(function (it) {
      if (typeof d[it.key] === 'boolean') { p[it.key] = d[it.key]; found = true; }
    });
    if (found) { savePrivacyLocal(p); }
    return found;
  }

  /* ── 渲染：隐私开关 ───────────────────────────────────────── */

  function renderPrivacy() {
    var body = $('privacyBody');
    var p = state.social.privacy;
    body.innerHTML = PRIVACY_ITEMS.map(function (it) {
      var on = p[it.key] === true;
      return '<button type="button" class="switch-row" role="switch" tabindex="0"' +
               ' data-priv="' + it.key + '"' +
               ' aria-checked="' + (on ? 'true' : 'false') + '"' +
               ' aria-label="' + esc(it.title) + '">' +
               '<span class="switch-text">' +
                 '<span class="switch-title">' + esc(it.title) + '</span>' +
                 '<span class="switch-desc">' + esc(it.desc) + '</span>' +
               '</span>' +
               '<span class="switch-track" aria-hidden="true"><span class="switch-knob"></span></span>' +
             '</button>';
    }).join('');
  }

  /** 只刷新已有开关的 aria-checked：不重建 DOM，避免键盘焦点丢失 */
  function refreshPrivacySwitches() {
    var rows = document.querySelectorAll('[data-priv]');
    for (var i = 0; i < rows.length; i++) {
      var key = rows[i].getAttribute('data-priv');
      rows[i].setAttribute('aria-checked', state.social.privacy[key] === true ? 'true' : 'false');
    }
  }

  /** 切换某个开关：界面立刻反映 → 调接口 → 失败回滚 */
  function setPrivacy(key, on) {
    var s = state.social;
    var item = privItem(key);
    if (!item || s.privacySaving[key]) { return; }
    var prev = s.privacy[key] === true;
    if (prev === on) { return; }

    s.privacy[key] = on;                 // 乐观更新：动态里自己的条目立即变化
    savePrivacyLocal(s.privacy);
    refreshPrivacySwitches();
    renderFeed();
    if (key === 'in_ranking') { renderRanking(); }

    s.privacySaving[key] = true;
    var patch = {};
    patch[key] = on;
    apiFetch('/friends/privacy', { method: 'POST', body: patch }).then(function () {
      s.privacySaving[key] = false;
      toast(on ? '已开启「' + item.title + '」' : '已关闭「' + item.title + '」', 'ok');
    }).catch(function (err) {
      s.privacySaving[key] = false;
      s.privacy[key] = prev;             // 失败回滚：界面与服务器保持一致
      savePrivacyLocal(s.privacy);
      refreshPrivacySwitches();
      renderFeed();
      renderRanking();
      showAlert('隐私开关未能保存：' + readableError(err));
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 渲染：邀请链接 / 推荐人 / 昵称（v6）
   *   ① 落地：读 ?invite=XXXX（兼容 #/?invite=）→ 存本机 → 清掉地址栏参数
   *   ② 问询：GET /invite/preview 拿权威昵称，取不到退回链接里的 n 参数
   *   ③ 绑定：已建档（有 member_id）时 POST /friends/invite{auto_accept:true}
   *   ④ 幂等：同一邀请码只自动提交一次；已有推荐人则不再提交
   *   ⑤ 降级：任何失败都静默/轻提示，绝不阻塞建档与指数卡展示
   * ══════════════════════════════════════════════════════════ */

  /** 规范化邀请码：8 位大写字母或数字，否则返回空串 */
  function normInviteCode(v) {
    var code = String(v === null || v === undefined ? '' : v).trim().toUpperCase();
    return INVITE_CODE_RE.test(code) ? code : '';
  }

  /** 从 ?invite=XXXX 或 #/?invite=XXXX 取邀请码（两种写法都兼容） */
  function readInviteFromUrl() {
    var code = '';
    try {
      code = normInviteCode(new URLSearchParams(window.location.search || '').get('invite'));
    } catch (e) { code = ''; }
    if (!code) {
      var h = String(window.location.hash || '');
      var qi = h.indexOf('?');
      if (qi >= 0) {
        try {
          code = normInviteCode(new URLSearchParams(h.slice(qi + 1)).get('invite'));
        } catch (e2) { code = ''; }
      }
    }
    return code;
  }

  /** 从链接里读分享人昵称（n 参数）：只用于秒显，权威值以 /invite/preview 为准 */
  function readInviteNameFromUrl() {
    function pick(sp) {
      return String(sp.get('n') || sp.get('nickname') || '').trim();
    }
    var name = '';
    try {
      name = pick(new URLSearchParams(window.location.search || ''));
    } catch (e) { name = ''; }
    if (!name) {
      var h = String(window.location.hash || '');
      var qi = h.indexOf('?');
      if (qi >= 0) {
        try { name = pick(new URLSearchParams(h.slice(qi + 1))); } catch (e2) { name = ''; }
      }
    }
    return name.slice(0, 24);                 // 超长一律截断，避免脏链接撑破界面
  }

  /** 清掉地址栏里的 invite / n 参数：刷新不重复触发，转发也不会把参数一路带下去 */
  function stripInviteFromUrl() {
    try {
      var url = new URL(window.location.href);
      var changed = false;
      if (url.searchParams.has('invite')) { url.searchParams.delete('invite'); changed = true; }
      if (url.searchParams.has('n')) { url.searchParams.delete('n'); changed = true; }
      if (url.hash && url.hash.indexOf('invite=') >= 0) {
        var qi = url.hash.indexOf('?');
        if (qi >= 0) {
          var hp = new URLSearchParams(url.hash.slice(qi + 1));
          if (hp.has('invite') || hp.has('n')) {
            hp.delete('invite');
            hp.delete('n');
            var rest = hp.toString();
            var head = url.hash.slice(0, qi);
            url.hash = rest ? (head + '?' + rest) : head;
            changed = true;
          }
        }
      }
      if (!changed) { return; }
      var qs = url.searchParams.toString();
      var next = url.origin + url.pathname + (qs ? '?' + qs : '') + url.hash;
      window.history.replaceState(window.history.state, '', next);
    } catch (e) { /* 地址栏清理失败不影响任何功能 */ }
  }

  /** 页面加载时收下邀请码与分享人昵称，随即清掉地址栏参数 */
  function captureInviteFromUrl() {
    var s = state.social;
    var code = readInviteFromUrl();
    var name = readInviteNameFromUrl();
    stripInviteFromUrl();
    if (!code) { return; }

    var prev = normInviteCode(safeGet(K_PENDING_INVITE));
    if (prev && prev !== code) { safeDel(K_PENDING_NAME); s.pendingName = ''; }   // 换了码：旧昵称作废
    safeSet(K_PENDING_INVITE, code);
    s.pendingInvite = code;
    if (name) { safeSet(K_PENDING_NAME, name); s.pendingName = name; }
    renderHomeInviteHint();
  }

  /** 待绑定的邀请码（内存优先，其次本机存储） */
  function pendingInvite() {
    var s = state.social;
    return normInviteCode(s.pendingInvite || safeGet(K_PENDING_INVITE));
  }

  /** 清掉待绑定状态（成功后、或确认无需再绑时调用） */
  function clearPendingInvite() {
    var s = state.social;
    s.pendingInvite = '';
    s.pendingName = '';
    safeDel(K_PENDING_INVITE);
    safeDel(K_PENDING_NAME);
    renderHomeInviteHint();
  }

  /** 自动绑定留痕（本机）：{code, ok, at} */
  function readBindLog() {
    try { return JSON.parse(safeGet(K_BIND_LOG) || 'null') || null; } catch (e) { return null; }
  }

  /** 幂等判定：返回 'ok'（已成功）/ 'recent'（24 小时内提交过但未成功）/ ''（可提交） */
  function bindLogState(code) {
    var log = readBindLog();
    if (!log || String(log.code || '') !== code) { return ''; }
    if (log.ok === true) { return 'ok'; }
    return (Date.now() - num(log.at, 0)) < BIND_RETRY_WINDOW ? 'recent' : '';
  }

  function writeBindLog(code, ok) {
    safeSet(K_BIND_LOG, JSON.stringify({ code: code, ok: !!ok, at: Date.now() }));
  }

  var referralPending = null;
  /** GET /me/referral：邀请链接 / 分享文案 / 推荐人归属（并发只发一次，成功后缓存） */
  function fetchReferral() {
    var s = state.social;
    if (s.referralLoaded) { return Promise.resolve(s.referral); }
    if (referralPending) { return referralPending; }

    referralPending = apiFetch('/me/referral').then(function (env) {
      var d = env.data || {};
      s.referral = d;
      s.referralLoaded = true;
      if (d.invite_url) { s.inviteUrl = String(d.invite_url); }
      if (d.invite_code) {
        s.inviteCode = normInviteCode(d.invite_code) || String(d.invite_code).toUpperCase();
      }
      if (d.share_text) { s.shareText = String(d.share_text); }
      if (d.nickname) { s.nickname = String(d.nickname); }
      if (d.referred_by) { setReferrer(d.referred_by); }
      return d;
    });
    referralPending = referralPending.then(
      function (d) { referralPending = null; return d; },
      function (e) { referralPending = null; throw e; });
    return referralPending;
  }

  /** 记录推荐人归属（一次性、不可改绑；只用于内部判断与佣金归因，不向用户展示） */
  function setReferrer(rb) {
    if (!rb || typeof rb !== 'object') { return; }
    var s = state.social;
    s.referrer = rb;
    if (!s.referral || typeof s.referral !== 'object') { s.referral = {}; }
    s.referral.referred_by = rb;
  }

  /**
   * 邀请链接：优先服务端 invite_url，取不到用本站地址兜底；
   * 末尾附带分享人昵称参数 n（后端以邀请码为准，n 只用于落地页秒显）。
   */
  function inviteShareUrl() {
    var s = state.social;
    var code = s.inviteCode || pendingInvite();
    if (!code) { return ''; }
    var url = String(s.inviteUrl || '');
    if (url.indexOf('?invite=') < 0 || url.indexOf(code) < 0) {
      url = (window.location.origin || '') + '/?invite=' + code;
    }
    if (s.nickname && url.indexOf('&n=') < 0) {
      url += (url.indexOf('?') >= 0 ? '&' : '?') + 'n=' + encodeURIComponent(s.nickname);
    }
    return url;
  }

  /** 复制/展示用的分享文案：优先服务端 share_text；缺失或与当前昵称不符时本机拼装 */
  function inviteShareText() {
    var s = state.social;
    var code = s.inviteCode || pendingInvite();
    var url = inviteShareUrl();
    if (!url) { return ''; }
    var who = String(s.nickname || '');
    var fromServer = String(s.shareText || '').trim();
    var usable = fromServer && fromServer.indexOf('?invite=') >= 0 &&
                 (!code || fromServer.indexOf(code) >= 0) &&
                 (!who || fromServer.indexOf(who) >= 0);
    if (usable) { return fromServer; }
    return who ? ('我是' + who + '，邀请你一起看每日健康指数：' + url)
               : ('邀请你一起看每日健康指数：' + url);
  }

  /** GET /invite/preview?invite_code=<码>（公开接口，只回 {valid, nickname}） */
  function fetchInvitePreview(code) {
    if (!code) { return Promise.resolve(''); }
    return apiFetch('/invite/preview', {
      query: { invite_code: code },
      noAuth: true                      // 公开接口：不带令牌，避免无谓的鉴权重试
    }).then(function (env) {
      var d = env.data || {};
      if (d.valid === false) { return ''; }
      return String(d.nickname || d.nick_name || '').trim();
    }, function () { return ''; });      // 接口不可用：静默退回 n 参数兜底
  }

  /** 落地页问询：权威昵称优先，其次链接里的 n 参数，都没有则用中性文案 */
  function resolveInvitePreview() {
    var s = state.social;
    var code = pendingInvite();
    if (!s.pendingName) { s.pendingName = String(safeGet(K_PENDING_NAME) || ''); }
    renderHomeInviteHint();
    if (!code) { return Promise.resolve(''); }
    return fetchInvitePreview(code).then(function (nick) {
      if (nick) {
        s.pendingName = nick;
        safeSet(K_PENDING_NAME, nick);
        renderHomeInviteHint();
      }
      return s.pendingName;
    });
  }

  /** 邀请人昵称：优先推荐人记录，其次 preview / n 参数 */
  function inviterName() {
    var s = state.social;
    var rb = s.referrer || {};
    return String(rb.nickname || rb.nick_name || s.pendingName || '').trim();
  }

  /** 首屏邀请提示条：告诉新用户「是谁分享的」 */
  function renderHomeInviteHint() {
    var el = $('homeInviteHint');
    if (!el) { return; }
    var s = state.social;
    if (!s.pendingInvite) { el.hidden = true; el.textContent = ''; return; }
    var nick = String(s.pendingName || '').trim();
    el.innerHTML = nick
      ? ('<b>' + esc(nick) + '</b> 邀请你一起看每日健康指数')
      : '你的朋友邀请你一起看每日健康指数';
    el.hidden = false;
  }

  /**
   * 自动绑定推荐人 + 自动成为好友。
   * 前置：已建档（有 member_id）+ 有待绑定邀请码；返回的 Promise 永不 reject，
   * 任何失败都静默降级——绝不阻塞建档、绝不阻塞指数卡展示。
   */
  function maybeAutoBindInvite() {
    var s = state.social;
    var code = pendingInvite();
    if (!code || !state.profileCompleted) { return Promise.resolve(false); }
    if (s.bind.inFlight) { return s.bind.inFlight; }
    var st = bindLogState(code);
    if (st === 'ok') {                    // 已成功绑定过：清掉待绑定标记，不再打接口
      clearPendingInvite();
      return Promise.resolve(false);
    }
    if (st === 'recent') {                // 24 小时内提交过但未成功：不重复提交，保留待绑定以便日后重试
      return Promise.resolve(false);
    }

    var p = ensureToken(false).then(function (ok) {
      if (!ok) { return false; }                     // 游客登录失败：留到下次进入再试
      s.bind.code = code;
      // ① 已有推荐人 → 一次性、不可改绑，直接收工，不再打提交接口
      return fetchReferral().then(function (d) { return d; },
                                  function () { return null; })
        .then(function (d) {
          var rb = (d && d.referred_by) || s.referrer || null;
          if (rb) {
            setReferrer(rb);
            writeBindLog(code, true);
            clearPendingInvite();
            renderInvite();
            return false;
          }
          return postInviteBind(code);
        });
    }).catch(function () { return false; })
      .then(function (r) { s.bind.inFlight = null; return r; });

    s.bind.inFlight = p;
    return p;
  }

  /** 提交绑定：POST /friends/invite{invite_code, auto_accept:true} */
  function postInviteBind(code) {
    return apiFetch('/friends/invite', {
      method: 'POST',
      idempotencyKey: 'invite-bind-' + code,          // 同一邀请码复用同一幂等键
      body: { invite_code: code, auto_accept: true }
    }).then(function (env) {
      var d = (env && env.data) || {};
      writeBindLog(code, true);
      if (d.referred_by) { setReferrer(d.referred_by); }
      else if (d.referrer) { setReferrer(d.referrer); }
      var who = inviterName();                        // 清 pending 前先取昵称
      clearPendingInvite();
      renderInvite();
      if (state.view === 'friends') { loadSocial(true); }
      toast(who ? ('已与 ' + who + ' 成为好友') : '已与邀请人成为好友', 'ok');
      return true;
    }, function (err) {
      // ② 失败降级：码无效（3xxxx 业务码）就放弃这个码；其它失败留待 24 小时后再试
      writeBindLog(code, false);
      var c = err && err.code;
      if (typeof c === 'number' && c >= 30000 && c < 31000) {
        clearPendingInvite();
        toast('邀请码无效，未自动添加好友。', 'err');   // 轻提示：不阻塞建档与指数卡
      } else if (c !== 40004) {                          // 40004 = 接口尚未上线：静默留待重试
        toast('邀请人暂时没能加上，可稍后在好友圈手工添加。', 'err');
      }
      if (state.view === 'friends') { loadSocial(true); }
      return false;
    });
  }

  /* ── 渲染：邀请区 ─────────────────────────────────────────── */

  function renderInvite() {
    var s = state.social;
    var fallback = '（暂时取不到邀请链接，请稍后重试）';
    $('inviteCode').textContent = s.inviteCode || (s.err.invite ? '暂不可用' : '········');
    $('myNickname').textContent = s.nickname ? ('昵称：' + s.nickname) : '';
    $('inviteLink').textContent = inviteShareUrl() || fallback;
    $('inviteSharePreview').textContent = inviteShareText() || fallback;
    renderNicknameInput();
  }

  /* 「推荐人归属」渲染已删除（师父 2026-10-08：系统知道即可，不用让用户看到）。
     推荐人记录 referrer 仍然保留在 state.social 里，只用于内部判断是否已绑定。 */

  /** 昵称输入框回填：用户正在输入时不覆盖 */
  function renderNicknameInput() {
    var el = $('inNickname');
    if (!el || document.activeElement === el) { return; }
    var nick = String(state.social.nickname || '');
    if (nick) { el.value = nick; }
  }

  /* ── 交互：修改昵称 ───────────────────────────────────────── */

  /** 昵称字数：中文一个字算一个；拿不到 Array.from 时退回 length */
  function nickLength(name) {
    return (typeof Array.from === 'function') ? Array.from(name).length : name.length;
  }

  /** POST /me/nickname：成功后立刻刷新我的昵称 / 分享文案 / 排行榜自己那条 */
  function saveNickname() {
    var s = state.social;
    var el = $('inNickname');
    if (!el) { return; }
    var name = String(el.value || '').trim();
    fieldError('nicknameErr', '');

    var len = nickLength(name);
    if (len < 2 || len > 12) {
      fieldError('nicknameErr', '昵称需要 2–12 个字，请修改后重试。');
      el.focus();
      return;
    }
    if (name === s.nickname) { toast('昵称没有变化。', 'ok'); return; }
    if (s.nicknameSaving) { return; }

    var btn = $('btnSaveNickname');
    s.nicknameSaving = true;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');

    apiFetch('/me/nickname', {
      method: 'POST',
      idempotencyKey: uid('nick-'),
      body: { nickname: name }
    }).then(function (env) {
      var d = (env && env.data) || {};
      s.nickname = String(d.nickname || name);
      s.shareText = '';                 // 服务端分享文案可能还是旧昵称：作废，走本机拼装
      renderInvite();                   // 我的昵称 + 分享文案（含昵称）立刻变化
      renderFeed();                     // 好友圈动态里自己那条
      renderRanking();                  // 排行榜里自己那条
      renderMine();                     // v15：用户中心的昵称与头像首字
      renderAccount();                  // v15：账号与安全里的昵称回填 + 登录方式说明
      toast('昵称已改为「' + s.nickname + '」。', 'ok');
    }).catch(function (err) {
      fieldError('nicknameErr', readableError(err));
    }).then(function () {
      s.nicknameSaving = false;
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
    });
  }

  function renderPending() {
    var s = state.social;
    var wrap = $('pendingWrap');
    if (!s.pending.length) { wrap.hidden = true; $('pendingList').innerHTML = ''; return; }
    wrap.hidden = false;
    $('pendingList').innerHTML = s.pending.map(function (f) {
      var nick = f.nickname || '好友';
      var fid = friendId(f);
      var mine = (f.requested_by === 'me' || f.direction === 'out' || f.outgoing === true);
      var actions = mine ? '' :
        '<span class="fr-actions">' +
          '<button type="button" class="fr-btn" data-accept="' + esc(fid) + '"' +
            ' aria-label="接受 ' + esc(nick) + ' 的好友请求">接受</button>' +
          '<button type="button" class="fr-btn fr-btn-quiet" data-reject="' + esc(fid) + '"' +
            ' aria-label="拒绝 ' + esc(nick) + ' 的好友请求">拒绝</button>' +
        '</span>';
      return '<div class="fr-item">' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(nick)) + '</span>' +
        '<span class="fr-main">' +
          '<span class="fr-name">' + esc(nick) + '</span>' +
          '<span class="fr-sub">' + (mine ? '等待对方确认' : '请求加你为好友') + '</span>' +
        '</span>' + actions +
      '</div>';
    }).join('');
  }

  /* ── 渲染：好友圈动态 ─────────────────────────────────────── */

  /** 自己的动态条目：分数/连续天数按本机开关即时决定是否公开 */
  function selfEntry() {
    var s = state.social;
    var d = state.daily || {};
    var idx = (d && typeof d.index === 'object') ? d.index : null;
    var score = hasIndex(idx) ? Math.round(num(idx.score)) : null;
    if (score === null && s.me && hasNum(s.me.score)) { score = Math.round(num(s.me.score)); }

    var streak = null;
    if (hasNum(state.streakHint) && num(state.streakHint) > 0) { streak = num(state.streakHint); }
    else if (hasNum(d.streak_days)) { streak = num(d.streak_days); }
    else if (s.me && hasNum(s.me.streak_days)) { streak = num(s.me.streak_days); }

    return {
      nickname: s.nickname || '我', is_me: true,
      score: score, streak_days: streak,
      share_index: s.privacy.share_index === true,
      share_streak: s.privacy.share_streak === true,
      last_active: new Date().toISOString()
    };
  }

  function feedItemHtml(it) {
    // 加油记录（服务端返回的 cheer 类型，或本机刚送出的即时条目）
    if (it.kind === 'cheer' || it.type === 'cheer' || (it.template_text && !hasNum(it.score))) {
      var from = it.from_nickname || it.nickname || (it.from_me ? '我' : '好友');
      var to = it.to_nickname || it.target_nickname || '';
      var txt = it.template_text || it.cheer_text || it.text || '';
      return '<div class="feed-cheer">' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(from)) + '</span>' +
        '<span>' + esc(from) + (to ? ' 给 <b>' + esc(to) + '</b>' : '') +
          ' 加油：' + esc(txt) + '</span>' +
      '</div>';
    }

    var me = isSelfItem(it);
    var nick = it.nickname || it.nick_name || (me ? '我' : '好友');
    if (me && state.social.nickname) { nick = state.social.nickname; }

    var stats = '';
    // 指数：仅当对方（或自己）开启 share_index 才出现分数，否则「未公开」
    if (it.share_index === true && scoreText(it.score) !== '') {
      stats += '<span class="fm">今日指数 <b>' + esc(scoreText(it.score)) + '</b> 分</span>';
    } else if (it.share_index === true && it.score_band) {
      // 已公开但暂时没有分数（对方尚未生成）：退回展示指数分档
      stats += '<span class="fm">今日指数 <b>' + esc(String(it.score_band)) + '</b></span>';
    } else {
      stats += '<span class="fm is-private">今日指数 未公开</span>';
    }
    // 连续天数：仅当开启 share_streak 才显示这一项（关闭时不出现）
    if (it.share_streak === true && hasNum(it.streak_days)) {
      stats += '<span class="fm">连续记录 <b>' + esc(String(Math.round(num(it.streak_days)))) + '</b> 天</span>';
    }

    return '<div class="feed-item' + (me ? ' is-me' : '') + '">' +
      '<div class="feed-top">' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(nick)) + '</span>' +
        '<span class="feed-name">' + esc(nick) +
          (me ? '<span class="me-tag">我</span>' : '') + '</span>' +
        '<span class="feed-time">' + esc(relTime(it.last_active || it.updated_at || it.at)) + '</span>' +
      '</div>' +
      '<div class="feed-stats">' + stats + '</div>' +
    '</div>';
  }

  function renderFeed() {
    var s = state.social;
    var body = $('feedBody');
    if (!s.loadedFeed) {
      body.innerHTML = '<p class="placeholder">' +
        (s.err.feed ? '动态暂时读取失败，请稍后重试；其余区块仍可正常浏览。' : '正在读取…') + '</p>';
      return;
    }
    var others = (s.feed || []).filter(function (it) {
      return it && typeof it === 'object' && !isSelfItem(it) &&
             String(it.status || 'accepted') !== 'pending';
    });
    var html = feedItemHtml(selfEntry());
    html += (s.localFeed || []).map(feedItemHtml).join('');
    html += others.map(feedItemHtml).join('');
    if (!others.length) {
      html += '<p class="placeholder feed-empty">好友动态还是空的。把上面的邀请链接发给朋友，' +
              '对方打开并建档后就会自动成为好友，这里就会出现彼此愿意公开的记录。</p>';
    }
    body.innerHTML = html;
  }

  /* ── 渲染：健康排行 ───────────────────────────────────────── */

  function renderRanking() {
    var s = state.social;
    var body = $('rankingBody');
    if (s.ranking === null) {
      body.innerHTML = '<p class="placeholder">' +
        (s.err.ranking ? '排行暂时读取失败，请稍后重试。' : '正在读取…') + '</p>';
      return;
    }

    var meOn = s.privacy.in_ranking === true;
    var rows = s.ranking.filter(function (it) {
      return it && typeof it === 'object' && (meOn || !isSelfItem(it));
    });
    var self = selfEntry();
    if (meOn && hasNum(self.score) && !rows.some(isSelfItem)) {
      rows = rows.concat([{ nickname: self.nickname, is_me: true, score: self.score,
                            share_index: s.privacy.share_index }]);
    }
    rows.sort(function (a, b) { return num(b.score, -1) - num(a.score, -1); });   // 按分数降序

    var meInList = rows.some(isSelfItem);
    var list = rows.map(function (it, i) {
      var me = isSelfItem(it);
      var nick = (me && s.nickname) ? s.nickname : (it.nickname || (me ? '我' : '好友'));
      // 分数：对方明确关闭公开时显示「未公开」（分档/分数之外的项一律不展示）
      var sc = (it.share_index === false) ? '' : scoreText(it.score);
      var scoreHtml = sc
        ? '<span class="rank-score">' + esc(sc) + '</span>'
        : '<span class="rank-score is-private">未公开</span>';
      return '<li class="rank-item' + (me ? ' is-me' : '') + '">' +
        '<span class="rank-no">' + esc(String(i + 1)) + '</span>' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(nick)) + '</span>' +
        '<span class="rank-name">' + esc(nick) + (me ? '<span class="me-tag">我</span>' : '') + '</span>' +
        scoreHtml +
      '</li>';
    }).join('');

    var html = '';
    if (rows.length) {
      html += '<ul class="rank-list" id="rankList">' + list + '</ul>';
    } else {
      html += '<p class="placeholder">圈内暂时还没有人上榜。' +
              (meOn ? '等好友也开启排行后会出现在这里。' : '开启排行后你也会出现在这里。') + '</p>';
    }

    if (!meOn) {
      html += '<div class="rank-off" id="rankOff">' +
        '<p class="rank-off-text">你还没有参与排行。开启后才会出现在榜单里，' +
          '关闭时别人也看不到你的名次。</p>' +
        '<button type="button" class="switch-row" role="switch" tabindex="0"' +
          ' data-priv="in_ranking" aria-checked="false" aria-label="参与健康排行">' +
          '<span class="switch-text"><span class="switch-title">参与健康排行</span>' +
          '<span class="switch-desc">仅好友圈内可见，不做全区排行。</span></span>' +
          '<span class="switch-track" aria-hidden="true"><span class="switch-knob"></span></span>' +
        '</button>' +
      '</div>';
    } else if (!meInList) {
      html += '<p class="bar-scale-note">你已开启排行，等有分数后就会出现在这里。</p>';
    }

    body.innerHTML = html;
  }

  /* ── 渲染：健康互促 ───────────────────────────────────────── */

  function renderCheer() {
    var s = state.social;
    var body = $('cheerBody');
    var quota = num(s.quotaLeft, 0);
    $('cheerQuota').textContent = quota > 0
      ? ('今日还可送 ' + quota + ' 次')
      : '今日次数已用完';

    if (!s.loadedFriends) {
      body.innerHTML = '<p class="placeholder">' +
        (s.err.friends ? '好友列表暂时读取失败，请稍后重试。' : '正在读取…') + '</p>';
      return;
    }
    if (!s.accepted.length) {
      body.innerHTML = '<p class="placeholder">还没有好友。把上面的邀请链接发给朋友，' +
        '对方打开并建档后会自动成为你的好友；也可以填入对方的邀请码发起添加，' +
        '对方确认后就能互相加油。</p>';
      return;
    }

    body.innerHTML = '<div class="fr-list">' + s.accepted.map(function (f) {
      var nick = f.nickname || '好友';
      var fid = friendId(f);
      var sub = [];
      if (f.share_index === true && scoreText(f.score) !== '') {
        sub.push('今日指数 ' + scoreText(f.score) + ' 分');
      } else {
        sub.push('今日指数 未公开');
      }
      if (f.share_streak === true && hasNum(f.streak_days)) {
        sub.push('连续记录 ' + Math.round(num(f.streak_days)) + ' 天');
      }
      var t = relTime(f.last_active);
      if (t) { sub.push(t); }
      return '<div class="fr-item">' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(nick)) + '</span>' +
        '<span class="fr-main">' +
          '<span class="fr-name">' + esc(nick) + '</span>' +
          '<span class="fr-sub">' + esc(sub.join(' · ')) + '</span>' +
        '</span>' +
        '<span class="fr-actions">' +
          '<button type="button" class="fr-btn" data-cheer="' + esc(fid) + '"' +
            ' data-nick="' + esc(nick) + '"' + (quota > 0 ? '' : ' disabled') +
            ' aria-label="给 ' + esc(nick) + ' 加油">加油</button>' +
          '<button type="button" class="fr-btn fr-btn-quiet" data-remove="' + esc(fid) + '"' +
            ' data-nick="' + esc(nick) + '"' +
            ' aria-label="解除与 ' + esc(nick) + ' 的好友关系">解除</button>' +
        '</span>' +
      '</div>';
    }).join('') + '</div>' +
    '<p class="cheer-tip">加油只是一句中性问候，每人每天最多 ' + esc(String(num(s.quotaTotal, CHEER_DAILY_LIMIT))) +
      ' 次；对方会在动态里看到。解除好友后双方立刻互不可见。</p>';
  }

  /* ── 数据加载（分块容错：任一块失败都不影响其它块）───────── */

  function socialSkeleton() {
    $('inviteCode').textContent = '········';
    $('inviteLink').textContent = '正在获取邀请链接…';
    $('inviteSharePreview').textContent = '正在获取邀请文案…';
    $('feedBody').innerHTML = '<p class="placeholder">正在读取…</p>';
    $('rankingBody').innerHTML = '<p class="placeholder">正在读取…</p>';
    $('cheerBody').innerHTML = '<p class="placeholder">正在读取…</p>';
    $('pendingWrap').hidden = true;
  }

  function renderSocialAll() {
    renderInvite();
    renderPrivacy();
    renderPending();
    renderFeed();
    renderRanking();
    renderCheer();
  }

  function loadSocial(force) {
    var s = state.social;
    if (s.loading) { return Promise.resolve(); }
    if (s.loaded && !force) { renderSocialAll(); return Promise.resolve(); }

    s.loading = true;
    s.err = { invite: false, privacy: false, friends: false, feed: false,
              ranking: false, templates: false };
    if (!s.loaded) { socialSkeleton(); renderPrivacy(); }

    var errs = [];
    function fail(key) {
      return function (err) { s.err[key] = true; errs.push(err); };
    }

    // ① 邀请码 + 昵称（＋可选的本人开关）
    var p1 = apiFetch('/me/invite_code').then(function (env) {
      var d = env.data || {};
      if (d.invite_code) { s.inviteCode = normInviteCode(d.invite_code) || String(d.invite_code).toUpperCase(); }
      else if (d.code) { s.inviteCode = normInviteCode(d.code) || String(d.code).toUpperCase(); }
      if (d.nickname) { s.nickname = String(d.nickname); }
      if (d.invite_url) { s.inviteUrl = String(d.invite_url); }   // 该接口也带链接时同样采纳
      if (d.privacy) { mergePrivacy(d.privacy); }
    }).catch(fail('invite'));

    // ①b 邀请链接 / 分享文案 / 推荐人归属（GET /me/referral，契约 v6 新增；
    //    取不到就退回本机兜底拼装，绝不打扰用户，也不影响其它块）
    var p1b = fetchReferral().catch(function () { /* 静默降级 */ });

    // ② 本人三开关（契约外的可选接口；取不到就用本机镜像，默认全关，不打扰用户）
    var p2 = apiFetch('/friends/privacy').then(function (env) {
      var d = env.data || {};
      if (mergePrivacy(d)) { renderPrivacy(); }
    }).catch(function () { /* 该接口契约未定义：静默退回本机镜像 */ });

    // ③ 好友列表（含 pending）
    var p3 = apiFetch('/friends').then(function (env) {
      var d = env.data || {};
      var list = Array.isArray(d.friends) ? d.friends
               : (Array.isArray(d.items) ? d.items : []);
      s.friends = list.filter(function (f) { return f && typeof f === 'object'; });
      s.pending = s.friends.filter(function (f) { return String(f.status || '') === 'pending'; });
      s.accepted = s.friends.filter(function (f) { return String(f.status || 'accepted') === 'accepted'; });
      s.loadedFriends = true;
      if (d.privacy) { mergePrivacy(d.privacy); }
      if (d.me && typeof d.me === 'object') { s.me = d.me; }
    }).catch(fail('friends'));

    // ④ 动态流（服务端已按可见性过滤；前端再兜底过滤一次）
    var p4 = apiFetch('/friends/feed', { query: { limit: 20 } }).then(function (env) {
      var d = env.data || {};
      var items = Array.isArray(d.items) ? d.items
                : (Array.isArray(d.feed) ? d.feed : (Array.isArray(d.list) ? d.list : []));
      s.feed = items.filter(function (it) { return it && typeof it === 'object'; });
      s.feedCursor = d.next_cursor || null;
      s.loadedFeed = true;
    }).catch(fail('feed'));

    // ⑤ 圈内排行
    var p5 = apiFetch('/friends/ranking').then(function (env) {
      var d = env.data || {};
      var list = Array.isArray(d) ? d
               : (Array.isArray(d.ranking) ? d.ranking
               : (Array.isArray(d.items) ? d.items : []));
      s.ranking = list.filter(function (it) { return it && typeof it === 'object'; });
    }).catch(fail('ranking'));

    // ⑥ 加油模板（不足 6 条时补足兜底模板，保证可选 6 条）
    var p6 = apiFetch('/friends/cheer/templates').then(function (env) {
      var d = env.data || {};
      var list = Array.isArray(d) ? d : (Array.isArray(d.templates) ? d.templates : []);
      var clean = list.map(function (t, i) {
        if (typeof t === 'string') { return { template_id: 's' + (i + 1), text: t }; }
        if (t && typeof t === 'object') {
          return { template_id: String(t.template_id || t.id || ('s' + (i + 1))),
                   text: String(t.text || t.content || '') };
        }
        return null;
      }).filter(function (t) { return t && t.text; });
      s.templates = clean.length ? clean : CHEER_TEMPLATES_FALLBACK.slice();
      if (typeof d.remaining === 'number') { s.quotaLeft = d.remaining; }
      if (typeof d.left === 'number') { s.quotaLeft = d.left; }
      if (typeof d.daily_limit === 'number') { s.quotaTotal = d.daily_limit; }
      if (typeof d.limit === 'number') { s.quotaTotal = d.limit; }
    }).catch(fail('templates'));

    return Promise.all([p1, p1b, p2, p3, p4, p5, p6]).then(function () {
      s.loading = false;
      s.loaded = true;
      renderSocialAll();
      if (errs.length) {
        showAlert('好友圈部分内容读取失败：' + readableError(errs[0]) +
                  '（其余区块仍可正常浏览，可退出后重新进入本屏重试。）');
      }
    });
  }

  /** 加油模板：接口给了就用接口的，否则用内联兜底（始终 ≥6 条） */
  function cheerTemplates() {
    var s = state.social;
    var list = (s.templates && s.templates.length) ? s.templates : CHEER_TEMPLATES_FALLBACK;
    var seen = {};
    var out = [];
    list.forEach(function (t) {
      if (!t || !t.text) { return; }
      var text = String(t.text);
      if (seen[text]) { return; }
      seen[text] = 1;
      out.push({ template_id: String(t.template_id || ('t' + (out.length + 1))), text: text });
    });
    for (var i = 0; out.length < 6 && i < CHEER_TEMPLATES_FALLBACK.length; i++) {
      var f = CHEER_TEMPLATES_FALLBACK[i];
      if (!seen[f.text]) { seen[f.text] = 1; out.push(f); }
    }
    return out;
  }

  /* ── 交互：添加 / 接受 / 拒绝 / 解除 / 加油 ────────────────── */

  function addFriend() {
    var input = $('inInviteCode');
    var code = normInviteCode(input.value);
    fieldError('inviteErr', '');
    if (!code) {
      fieldError('inviteErr', '邀请码是 8 位大写字母或数字，请核对后重试。');
      input.focus();
      return;
    }
    var btn = $('btnAddFriend');
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    apiFetch('/friends/invite', { method: 'POST', body: { invite_code: code } }).then(function () {
      input.value = '';
      toast('已发出添加申请，等对方确认后即可互相可见。', 'ok');
      return loadSocial(true);
    }).catch(function (err) {
      fieldError('inviteErr', readableError(err));
    }).then(function () {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
    });
  }

  function answerFriend(fid, accept) {
    if (!fid) { return; }
    apiFetch(accept ? '/friends/accept' : '/friends/reject', {
      method: 'POST',
      body: { friend_id: fid }
    }).then(function () {
      toast(accept ? '已接受，你们现在可以互相看见。' : '已拒绝该请求。', 'ok');
      return loadSocial(true);
    }).catch(function (err) {
      showAlert(readableError(err));
    });
  }

  function confirmRemoveFriend(fid, nick) {
    if (!fid) { return; }
    openConfirm('解除好友', '确定要解除与「' + (nick || '该好友') + '」的好友关系吗？' +
      '解除后双方立刻互不可见，动态与排行里都不再出现对方。此操作不可撤销。',
      '确认解除', function () {
        apiFetch('/friends/' + encodeURIComponent(fid), { method: 'DELETE' }).then(function () {
          var s = state.social;
          // 解除后立刻清掉本机缓存的该好友相关条目（动态里不再出现对方）
          s.friends = s.friends.filter(function (f) { return friendId(f) !== fid; });
          s.accepted = s.accepted.filter(function (f) { return friendId(f) !== fid; });
          s.pending = s.pending.filter(function (f) { return friendId(f) !== fid; });
          s.feed = (s.feed || []).filter(function (it) {
            return friendId(it) !== fid && it.from_nickname !== nick && it.nickname !== nick;
          });
          if (s.ranking) {
            s.ranking = s.ranking.filter(function (it) {
              return friendId(it) !== fid && !(nick && it.nickname === nick);
            });
          }
          s.localFeed = (s.localFeed || []).filter(function (it) { return it.to_nickname !== nick; });
          toast('已解除好友关系。', 'ok');
          return loadSocial(true);
        }).catch(function (err) {
          showAlert(readableError(err));
        });
      });
  }

  function openCheerSheet(fid, nick) {
    var s = state.social;
    if (num(s.quotaLeft, 0) <= 0) {
      toast('今天的加油次数已用完，明天再来。', 'err');
      return;
    }
    if (!fid) { return; }
    s.cheerTarget = { friend_id: fid, nickname: nick || '好友' };
    $('cheerSheetTitle').textContent = '给 ' + (nick || '好友') + ' 加油';
    $('cheerSheetTip').textContent = '今日还可送 ' + num(s.quotaLeft, 0) +
      ' 次；选一句中性问候发给对方，对方会在动态里看到。';
    $('tmplList').innerHTML = cheerTemplates().map(function (t) {
      return '<button type="button" class="tmpl-item" data-tid="' + esc(t.template_id) + '">' +
               esc(t.text) + '</button>';
    }).join('');
    openSheet('cheerSheet');
    var first = $('tmplList').querySelector('.tmpl-item');
    if (first) { first.focus(); }
  }

  function sendCheer(tid) {
    var s = state.social;
    var target = s.cheerTarget;
    if (!target) { return; }
    var tpl = null;
    cheerTemplates().forEach(function (t) { if (t.template_id === tid) { tpl = t; } });
    if (!tpl) { return; }

    apiFetch('/friends/cheer', {
      method: 'POST',
      body: { friend_id: target.friend_id, template_id: tpl.template_id }
    }).then(function (env) {
      var d = (env && env.data) || {};
      // 次数以服务端为准：remaining / left / (daily_limit - sent_today) 三种口径都兼容
      if (typeof d.remaining === 'number') { s.quotaLeft = d.remaining; }
      else if (typeof d.left === 'number') { s.quotaLeft = d.left; }
      else if (typeof d.sent_today === 'number' && typeof d.daily_limit === 'number') {
        s.quotaLeft = Math.max(0, d.daily_limit - d.sent_today);
      } else { s.quotaLeft = Math.max(0, num(s.quotaLeft, 0) - 1); }
      // 被加油记录：本机即时显示一条，服务端下次返回时会带上同一条
      s.localFeed = [{
        kind: 'cheer', from_me: true, nickname: s.nickname || '我',
        to_nickname: target.nickname, template_text: tpl.text,
        last_active: new Date().toISOString()
      }].concat(s.localFeed || []);
      closeSheet('cheerSheet');
      renderCheer();
      renderFeed();
      toast('已给「' + target.nickname + '」加油：' + tpl.text, 'ok');
    }).catch(function (err) {
      // 40000 = 服务端业务码 RATE_LIMITED（每日 3 次上限），给一句可读提示
      var quotaOut = err && (err.code === 40000 || err.code === 40010);
      showAlert(quotaOut ? '今天的加油次数已用完，明天再来。' : readableError(err));
      loadSocial(true);       // 次数可能与服务端不一致，重新对齐
    });
  }

  /* ── 抽屉管理（历史 / 加油模板 / 二次确认共用）────────────── */

  var SHEET_IDS = ['historySheet', 'cheerSheet', 'confirmSheet', 'famRemindSheet', 'authSheet'];

  function syncSheets() {
    var any = SHEET_IDS.some(function (id) { return !$(id).hidden; });
    $('sheetBackdrop').hidden = !any;
    document.body.style.overflow = any ? 'hidden' : '';
  }

  function openSheet(id, focusId) {
    $(id).hidden = false;
    syncSheets();
    if (focusId && $(focusId)) { $(focusId).focus(); }
  }

  function closeSheet(id) {
    $(id).hidden = true;
    syncSheets();
  }

  function closeAllSheets() {
    SHEET_IDS.forEach(function (id) { $(id).hidden = true; });
    syncSheets();
  }

  function closeCheerSheet() {
    state.social.cheerTarget = null;
    closeSheet('cheerSheet');
    focusIfVisible('#cheerBody');
  }

  /* ══════════════════════════════════════════════════════════
   * v12 · 登录 / 注册（手机号 + 密码，数显自建账号）
   *   · 入口只在首屏右上角显示；已登录时入口显示手机号掩码
   *   · 注册即把手机号绑到本设备当前账号（先当游客用过的数据不丢）
   *   · 成功后刷新页面，让所有按 member 缓存的数据重新按新账号加载
   * ══════════════════════════════════════════════════════════ */

  var authState = { mode: 'login', hasPassword: false, phoneMasked: '', saving: false };

  function setAuthNotice(msg) {
    var el = $('authNotice');
    if (el) { el.textContent = msg || ''; }
  }

  /** 三个独立模式：登录 / 注册 / 找回（v12.2 师父令「增加找回密码」） */
  function setAuthMode(mode) {
    authState.mode = (mode === 'register' || mode === 'recover') ? mode : 'login';
    var isReg = authState.mode === 'register';
    var isRec = authState.mode === 'recover';
    var isLogin = !isReg && !isRec;
    $('authTitle').textContent = isRec ? '找回密码' : (isReg ? '注册' : '登录');
    $('authConfirmWrap').hidden = !(isReg || isRec);
    $('btnAuthSubmit').textContent = isRec ? '设置新密码' : (isReg ? '注册' : '登录');
    $('btnAuthForgot').hidden = (isReg || isRec);
    // ★ v15：登录这一栏收「手机号 或 昵称」；注册/找回仍只收手机号 → 换回数字键盘
    var el = $('inAuthPhone');
    var lab = $('authPhoneLabel');
    if (el) {
      el.type = isLogin ? 'text' : 'tel';
      el.maxLength = isLogin ? 32 : 11;
      el.setAttribute('inputmode', isLogin ? 'text' : 'numeric');
      el.setAttribute('autocomplete', isLogin ? 'username' : 'tel');
      el.placeholder = isLogin ? '请输入手机号或昵称' : '请输入 11 位手机号';
    }
    if (lab) { lab.textContent = isLogin ? '手机号 / 昵称' : '手机号'; }
    setAuthNotice(isRec
      ? '你已在这台设备上登录（设备账号或既有账号）。填手机号 + 新密码即可设置/重设：本机的档案与打卡记录都不会丢，以后换设备用「手机号 + 密码」登录。'
      : (isReg
        ? '注册：一个手机号一个账号。会绑定到本机当前账号，先当游客用过的记录不丢；注册成功后回到登录。'
        : '登录：手机号 或 昵称 ＋ 密码都可以。第一次用请点右上角「注册」；忘记密码点下面的提示。'));
    fieldError('authErr', '');
  }

  function renderAuthSheet() {
    var logged = !!authState.hasPassword;
    $('authLoggedWrap').hidden = !logged;
    $('authForm').hidden = logged;
    $('btnAuthSubmit').hidden = logged;
    $('btnAuthLogout').hidden = !logged;
    if (logged) {
      $('authTitle').textContent = '我的账号';
      $('authLoggedTip').textContent = '当前账号：' + (authState.phoneMasked || '已登录') +
        '。换设备用同一手机号登录，就能看到自己的档案与观测记录。';
    } else {
      setAuthMode(authState.mode);
    }
  }

  /** 首屏右上角：两个独立入口（未登录时「登录」「注册」；已登录时只显示手机号掩码） */
  function refreshAuthEntry() {
    var box = $('authEntryBox');
    var btn = $('btnAuthEntry');
    if (!box || !btn) { return; }
    box.hidden = (state.view !== 'home');
    var logged = !!authState.hasPassword;
    $('btnAuthEntryReg').hidden = logged;
    btn.textContent = logged ? (authState.phoneMasked || '已登录') : '登录';
  }

  /** 问一次当前账号是否已设密码（未登录/异常时保持"登录 / 注册"入口） */
  function loadAuthStatus() {
    if (!getToken()) { refreshAuthEntry(); return Promise.resolve(false); }
    return apiFetch('/auth/password/status').then(function (env) {
      var d = env.data || {};
      authState.hasPassword = !!d.has_password;
      authState.phoneMasked = String(d.phone_masked || '');
      refreshAuthEntry();
      if (!$('authSheet').hidden) { renderAuthSheet(); }
      // v15：用户中心左侧的昵称/手机号掩码跟着登录态走
      if (state.view === 'mine') { renderMine(); }
      if (state.view === 'account') { renderAccount(); }
      return authState.hasPassword;
    }, function () { refreshAuthEntry(); return false; });
  }

  function openAuthSheet(mode) {
    authState.mode = (mode === 'register') ? 'register' : 'login';
    fieldError('authErr', '');
    renderAuthSheet();
    openSheet('authSheet', authState.hasPassword ? 'btnAuthLogout' : 'inAuthPhone');
    loadAuthStatus();
  }

  function closeAuthSheet() {
    closeSheet('authSheet');
    focusIfVisible('#btnAuthEntry');
  }

  function submitAuth() {
    if (authState.saving) { return; }
    fieldError('authErr', '');
    var phone = String($('inAuthPhone').value || '').trim();
    var pwd = String($('inAuthPwd').value || '');
    var isReg = authState.mode === 'register';
    var isRec = authState.mode === 'recover';
    var isLogin = !isReg && !isRec;
    // ★ v15（2026-10-09 师父令）：**登录**时「手机号 或 昵称」都可以；
    //   注册与找回密码仍然必须是手机号（账号归属靠手机号）。
    if (isLogin) {
      if (!phone) { fieldError('authErr', '请输入手机号或昵称。'); return; }
      if (phone.length < 2 || phone.length > 32) {
        fieldError('authErr', '请输入正确的手机号或昵称。'); return;
      }
    } else if (!/^1[3-9]\d{9}$/.test(phone)) {
      fieldError('authErr', '请输入正确的 11 位手机号。'); return;
    }
    if (pwd.length < 6 || pwd.length > 32) { fieldError('authErr', '密码长度需在 6–32 位之间。'); return; }
    if ((isReg || isRec) && pwd !== String($('inAuthPwd2').value || '')) {
      fieldError('authErr', '两次输入的密码不一致。'); return;
    }
    authState.saving = true;
    busy(true);

    if (isRec) {
      // 找回/设置密码：需登录（以"持有本机会话"作归属证明），不换令牌、不刷新页面
      apiFetch('/auth/password/set', {
        method: 'POST',
        body: { phone: phone, password: pwd }
      }).then(function () {
        authState.saving = false; busy(false);
        $('inAuthPwd').value = ''; $('inAuthPwd2').value = '';
        setAuthMode('login');
        setAuthNotice('密码已设置。请用「手机号 + 新密码」登录；本机的档案与打卡记录不受影响。');
        toast('密码已设置，请登录。', 'ok');
        loadAuthStatus();
        try { $('inAuthPwd').focus({ preventScroll: true }); } catch (e) { /* 忽略 */ }
      }, function (err) {
        authState.saving = false; busy(false);
        fieldError('authErr', readableError(err));
      });
      return;
    }

    apiFetch(isReg ? '/auth/password/register' : '/auth/password/login', {
      method: 'POST',
      noAuth: true,
      // v15：登录传 identifier（服务端手机号/昵称两种都认）；注册仍传 phone
      body: isLogin ? { identifier: phone, password: pwd, device_id: deviceId() }
                    : { phone: phone, password: pwd, device_id: deviceId() }
    }).then(function (env) {
      authState.saving = false; busy(false);
      var d = env.data || {};
      if (isReg) {
        // ★ 注册与登录**彻底分开**：注册不发令牌、不自动登录，只把手机号带到登录框
        if (!d.account_id) { fieldError('authErr', '注册失败，请稍后重试。'); return; }
        toast('注册成功，请用手机号登录。', 'ok');
        $('inAuthPwd').value = ''; $('inAuthPwd2').value = '';
        setAuthMode('login');
        setAuthNotice('注册成功，请用手机号与刚设置的密码登录。');
        try { $('inAuthPwd').focus({ preventScroll: true }); } catch (e) { /* 忽略 */ }
        return;
      }
      if (!d.access_token) { fieldError('authErr', '登录失败，请稍后重试。'); return; }
      applyProfileFlag(d);                              // v14：登录到哪个账号，就按哪个账号的建档状态渲染
      setToken(d.access_token, d.refresh_token);        // 换到账号态令牌
      toast('登录成功。', 'ok');
      closeSheet('authSheet');
      // 页面按 member 缓存了档案/家庭/节律，切账号后统一刷新最稳
      window.setTimeout(function () { window.location.reload(); }, 700);
    }, function (err) {
      authState.saving = false; busy(false);
      fieldError('authErr', readableError(err));
    });
  }

  function logoutAuth() {
    openConfirm('退出登录',
                '退出后回到本机设备游客身份；档案与记录仍保存在本机，用手机号可再次登录。',
                '退出', function () {
      apiFetch('/auth/logout', { method: 'POST' }).then(function () {
        clearToken(); toast('已退出登录。', 'ok'); closeSheet('authSheet');
        window.setTimeout(function () { window.location.reload(); }, 600);
      }, function () {
        clearToken(); window.location.reload();
      });
    });
  }

  function openConfirm(title, text, okText, action) {
    $('confirmTitle').textContent = title;
    $('confirmText').textContent = text;
    $('btnConfirmOk').textContent = okText || '确认';
    state.social.confirmAction = action || null;
    openSheet('confirmSheet', 'btnConfirmCancel');
  }

  function closeConfirmSheet() {
    state.social.confirmAction = null;
    closeSheet('confirmSheet');
  }

  function focusIfVisible(sel) {
    var el = $(sel.replace('#', ''));
    if (el && el.offsetParent !== null) {
      var btn = el.querySelector('button');
      if (btn) { try { btn.focus({ preventScroll: true }); } catch (e) { /* 忽略 */ } }
    }
  }

  function copyInvite() {
    // v6：复制的是「带邀请码的分享文案」（服务端 share_text 优先，本机拼装兜底），
    // 文案里同时含 ?invite= 与 8 位邀请码，朋友打开即自动绑定。
    var text = inviteShareText();
    if (!text) { toast('邀请链接还没取到，请稍后重试。', 'err'); return; }
    function done(ok) {
      toast(ok ? '邀请链接已复制，发给朋友——对方打开并建档后，会自动成为你的好友'
               : '复制失败，请长按上方链接手动复制。', ok ? 'ok' : 'err');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); },
                                               function () { done(fallbackCopy(text)); });
      return;
    }
    done(fallbackCopy(text));
  }

  /* ══════════════════════════════════════════════════════════
   * 十一之二、订阅 / 我的积分 / 推广收益（v8）
   *
   * 接口契约（后端冻结；测试期 *_cents 的单位是积分，1 积分 = 1 分）：
   *   GET  /subscribe/plans      → {plans:[{plan_id,name,days,price_cents,active}]}
   *   POST /subscribe/order      {plan_id, pay_with:'points'}
   *                              → {order_no, amount_cents, status, channel}
   *   GET  /points/balance       → {balance, earned_total, spent_total}
   *   GET  /points/ledger?page=  → {items:[{delta,reason,ref_order_no,created_at}], has_more}
   *   GET  /me/commission        → {total_cents,pending_cents,settled_cents,
   *                                 reversed_cents,net_cents,rate_bp,...}
   *
   * 本期边界（师父裁决 2026-10-08）：
   *   ① 订阅只用积分支付（channel=points），不接任何真实支付通道、不出网；
   *   ② 提现本期不做——按钮置灰 + 说明「待银联分账通道开通后开放」。
   * ══════════════════════════════════════════════════════════ */

  /* 套餐兜底档位：接口取不到时按此展示（页面会写明"以服务端为准"）。
     与后端冻结的三档一致：月卡 9900 / 季卡 19900 / 年卡 199000 积分。 */
  var PLANS_FALLBACK = [
    { plan_id: 'plan_month',   name: '月卡', days: 30,  price_cents: 9900,   active: true },
    { plan_id: 'plan_quarter', name: '季卡', days: 90,  price_cents: 19900,  active: true },
    { plan_id: 'plan_year',    name: '年卡', days: 365, price_cents: 199000, active: true }
  ];

  /* 积分明细的变动原因中文名：接口给了未知原因就原样显示，不做猜测 */
  var POINTS_REASON = {
    grant: '后台发放',
    admin_grant: '后台发放',
    signup: '新用户注册赠送',
    subscribe: '订阅开通',
    order: '订阅开通',
    order_pay: '订阅开通',
    points_pay: '订阅开通',
    refund: '退款返还',
    order_refund: '退款返还',
    commission: '推广收益入账',
    commission_reverse: '推广收益冲正',
    expire: '积分到期扣除'
  };

  /* 提现说明：本期固定不开放 */
  var WITHDRAW_NOTE = '待银联分账通道开通后开放。';

  /** 整数千分位（积分为整数，1 积分 = 1 分） */
  function fmtInt(v) {
    var n = Math.round(num(v));
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** 时间串统一成「YYYY-MM-DD HH:mm」；识别不了就原样显示。
      带时区标记（Z 或 ±HH:MM）的按本机时区换算，避免把 UTC 直接当本地时间显示。 */
  function fmtTime(s) {
    if (!s) { return '时间未提供'; }
    var str = String(s);
    if (/(Z|[+-]\d{2}:?\d{2})$/.test(str)) {
      var d = new Date(str);
      if (!isNaN(d.getTime())) {
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
               ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }
    }
    var m = str.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (m) { return m[1] + '-' + m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5]; }
    return str;
  }

  /** 本机时区的「YYYY-MM-DD HH:mm:ss」：订单提交时间用（不用 toISOString，避免显示成 UTC） */
  function nowLocal() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) + ' ' +
           pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  function reasonText(reason) {
    var key = String(reason || '');
    return POINTS_REASON[key] || (key || '积分变动');
  }

  /** 订单状态中文名 */
  function orderStateText(status) {
    var s = String(status || '');
    if (s === 'paid') { return '已开通'; }
    if (s === 'unpaid') { return '未支付'; }
    if (s === 'pending') { return '处理中'; }
    if (s === 'refunded') { return '已退款'; }
    return s || '状态未返回';
  }

  /** 支付渠道中文名（测试期只有积分） */
  function channelText(channel) {
    var c = String(channel || '');
    if (c === 'points') { return '积分'; }
    return c || '积分';
  }

  /** 数额展示：取不到值时给一个明显"未取到"的占位（而不是一个像乱码的红色横杠） */
  function setAmount(el, v) {
    if (!el) { return; }
    if (v === null || v === undefined) {
      el.textContent = '—';
      el.className = 'balance-num is-empty';
    } else {
      el.textContent = fmtInt(v);
      el.className = 'balance-num';
    }
  }

  function findPlan(planId) {
    var hit = null;
    state.subscribe.plans.forEach(function (p) {
      if (p.plan_id === planId) { hit = p; }
    });
    return hit;
  }

  /* ── 订阅屏：数据加载 ───────────────────────────────────── */

  /** 套餐列表：GET /subscribe/plans（失败或空 → 内置三档 + 页面写明来源） */
  function loadPlans() {
    var s = state.subscribe;
    return apiFetch('/subscribe/plans').then(function (env) {
      var d = env.data || {};
      var list = Array.isArray(d) ? d
               : (Array.isArray(d.plans) ? d.plans
               : (Array.isArray(d.items) ? d.items : []));
      var clean = [];
      list.forEach(function (it, i) {
        if (!it || typeof it !== 'object') { return; }
        var id = String(it.plan_id || it.id || '');
        if (!id) { return; }
        clean.push({
          plan_id: id,
          name: String(it.name || ('套餐 ' + (i + 1))),
          days: num(it.days),
          price_cents: num(it.price_cents !== undefined && it.price_cents !== null
                            ? it.price_cents : it.price),
          active: (it.active === undefined || it.active === null) ? true : !!it.active
        });
      });
      var usable = clean.filter(function (p) { return p.active !== false; });
      s.err = false;
      if (usable.length) {
        s.plans = usable;
        s.fallback = false;
      } else {
        s.plans = PLANS_FALLBACK.slice();
        s.fallback = true;
        s.err = true;
      }
      if (!findPlan(s.selectedId)) { s.selectedId = defaultPlanId(s.plans); }
      if (s.err) {
        throw new ApiError(-3, '套餐接口未返回可用套餐，已改用内置默认档位（价格以服务端为准）。', {}, '');
      }
      return true;
    }, function (err) {
      s.plans = PLANS_FALLBACK.slice();
      s.fallback = true;
      s.err = true;
      if (!findPlan(s.selectedId)) { s.selectedId = defaultPlanId(s.plans); }
      throw err;
    });
  }

  /** 默认选中：三档取中间那档（季卡），其余取第一档 */
  function defaultPlanId(plans) {
    if (!plans.length) { return ''; }
    return plans[Math.min(1, plans.length - 1)].plan_id;
  }

  /** 积分余额：GET /points/balance（订阅屏顶部与积分屏共用同一份数据） */
  function loadBalance() {
    var p = state.points;
    return apiFetch('/points/balance').then(function (env) {
      var d = env.data || {};
      p.balance = num(d.balance);
      p.earned = num(d.earned_total);
      p.spent = num(d.spent_total);
      p.loaded = true;
      p.err.balance = false;
      return true;
    }, function (err) {
      p.err.balance = err || new ApiError(-1, '积分余额读取失败。', {}, '');
      return false;
    }).then(function (ok) {
      renderPointsSummary();
      renderPlans();
      return ok;
    });
  }

  /** 积分明细：GET /points/ledger?page=（reset=true 从第 1 页重取） */
  function loadPointsLedger(reset) {
    var lg = state.points.ledger;
    if (lg.loading) { return Promise.resolve(false); }
    var nextPage = reset ? 1 : (num(lg.page, 0) + 1);
    lg.loading = true;
    renderLedger();

    return apiFetch('/points/ledger', { query: { page: nextPage } }).then(function (env) {
      var d = env.data || {};
      var items = Array.isArray(d.items) ? d.items
                : (Array.isArray(d) ? d : (Array.isArray(d.list) ? d.list : []));
      var clean = items.filter(function (it) { return it && typeof it === 'object'; })
        .map(function (it) {
          return {
            delta: num(it.delta),
            reason: String(it.reason || ''),
            ref: String(it.ref_order_no || ''),
            created_at: String(it.created_at || '')
          };
        });
      lg.items = reset ? clean : lg.items.concat(clean);
      lg.page = nextPage;
      // has_more 优先；接口没给时按"本页是否满载 20 条"兜底
      lg.hasMore = (typeof d.has_more === 'boolean') ? d.has_more : (clean.length >= 20);
      lg.loaded = true;
      state.points.err.ledger = false;
      return true;
    }, function (err) {
      state.points.err.ledger = err || new ApiError(-1, '积分明细读取失败。', {}, '');
      return false;
    }).then(function (ok) {
      lg.loading = false;
      renderLedger();
      // 分页「加载更多」失败：已有列表照常保留，只轻提示一次
      if (!ok && lg.items.length) {
        toast('加载更多失败：' + readableError(state.points.err.ledger), 'err');
      }
      return ok;
    });
  }

  /** 推广收益：GET /me/commission（测试期单位为积分，rate_bp=3000 即 30%） */
  function loadCommission() {
    var p = state.points;
    return apiFetch('/me/commission').then(function (env) {
      var d = env.data || {};
      p.commission = {
        total: num(d.total_cents),
        pending: num(d.pending_cents),
        settled: num(d.settled_cents),
        reversed: num(d.reversed_cents),
        net: (d.net_cents === undefined || d.net_cents === null)
             ? num(d.total_cents) - num(d.reversed_cents) : num(d.net_cents),
        rate_bp: (d.rate_bp === undefined || d.rate_bp === null) ? 3000 : num(d.rate_bp)
      };
      p.err.commission = false;
      return true;
    }, function (err) {
      p.err.commission = err || new ApiError(-1, '推广收益读取失败。', {}, '');
      return false;
    }).then(function (ok) {
      renderCommission();
      return ok;
    });
  }

  /** 进入订阅屏：套餐 + 余额（任一块失败都不影响另一块，页面不白屏） */
  function loadSubscribe(force) {
    var s = state.subscribe;
    if (s.loading) { return Promise.resolve(); }
    s.loading = true;
    s.loaded = true;

    var failed = [];
    function grab(pr) {
      return pr.then(function (ok) { if (!ok) { failed.push(1); } });
    }
    return Promise.all([grab(loadPlans()), grab(loadBalance())]).then(function () {
      s.loading = false;
      renderPlans();
      renderPointsSummary();
      syncSubNotice();
      if (failed.length) {
        showAlert('订阅信息读取失败：' + readableError(state.points.err.balance ||
                  new ApiError(-1, '套餐读取失败，已改用内置默认档位。', {}, '')) +
                  '（可退出后重新进入本屏重试。）');
      }
    });
  }

  /** 进入积分/收益屏：三块并行，失败只提示一次，其余区块照常渲染 */
  function loadPoints(force) {
    var p = state.points;
    if (p.loading) { return Promise.resolve(); }
    p.loading = true;
    pointsSkeleton();
    renderPointsSummary();
    renderCommission();

    return Promise.all([loadBalance(), loadPointsLedger(true), loadCommission()])
      .then(function (oks) {
        p.loading = false;
        var firstErr = p.err.balance || p.err.ledger || p.err.commission;
        if (oks.indexOf(false) >= 0 && firstErr) {
          showAlert('积分/收益部分内容读取失败：' + readableError(firstErr) +
                    '（其余区块仍可浏览，可退出后重新进入本屏重试。）');
        }
      });
  }

  /** 订阅成功后：余额、明细、收益三处一起对齐（账务口径以服务端为准） */
  function refreshAfterOrder() {
    return Promise.all([loadBalance(), loadPointsLedger(true), loadCommission()])
      .then(function () { renderPlans(); syncSubNotice(); });
  }

  /* ── 订阅屏：渲染与交互 ─────────────────────────────────── */

  function pointsSkeleton() {
    var p = state.points;
    if (p.balance === null) { $('ptBalance').textContent = '—'; }
    if (!p.ledger.loaded) {
      $('ledgerBody').innerHTML = '<p class="placeholder">正在读取…</p>';
    }
  }

  function showSubNotice(msg) {
    var el = $('subNotice');
    el.textContent = msg;
    el.hidden = false;
  }
  function hideSubNotice() {
    var el = $('subNotice');
    el.textContent = '';
    el.hidden = true;
  }

  /** 余额不足：前端先提示（写明还需多少积分），仍可提交由服务端裁决 */
  function syncSubNotice() {
    var plan = findPlan(state.subscribe.selectedId);
    var bal = currentBalance();
    if (!plan || bal === null) { hideSubNotice(); return; }
    var price = num(plan.price_cents);
    if (bal < price) {
      showSubNotice('积分不足：还需 ' + fmtInt(price - bal) + ' 积分（当前 ' +
                    fmtInt(bal) + ' 积分，需要 ' + fmtInt(price) +
                    ' 积分）。仍可提交，由服务端最终裁决。');
    } else {
      hideSubNotice();
    }
  }

  /** 当前余额：未取到返回 null（不拿 0 冒充，避免误判"不足"） */
  function currentBalance() {
    var b = state.points.balance;
    return (b === null || b === undefined) ? null : num(b);
  }

  function planCardHtml(plan) {
    var s = state.subscribe;
    var on = (plan.plan_id === s.selectedId);
    var price = num(plan.price_cents);
    var bal = currentBalance();
    var short = (bal !== null && bal < price);
    var perDay = num(plan.days) > 0 ? Math.round(price / num(plan.days)) : 0;
    var label = plan.name + '，有效期 ' + num(plan.days) + ' 天，' + fmtInt(price) + ' 积分';

    return '<button type="button" class="plan-card' + (on ? ' is-on' : '') + '"' +
             ' role="radio" aria-checked="' + (on ? 'true' : 'false') + '"' +
             ' data-plan="' + esc(plan.plan_id) + '"' +
             ' aria-label="' + esc(label) + '">' +
             '<span class="plan-radio" aria-hidden="true"></span>' +
             '<span class="plan-main">' +
               '<span class="plan-name">' + esc(plan.name) +
                 (on ? '<span class="chip">已选</span>' : '') +
               '</span>' +
               '<span class="plan-days">有效期 ' + esc(String(num(plan.days))) + ' 天' +
                 (perDay > 0 ? ' · 约 ' + fmtInt(perDay) + ' 积分/天' : '') +
               '</span>' +
             '</span>' +
             '<span class="plan-side">' +
               '<span class="plan-price">' + fmtInt(price) +
                 '<span class="plan-price-unit"> 积分</span></span>' +
               (short ? '<span class="plan-off-tag is-warn">余额不足</span>' : '') +
             '</span>' +
           '</button>';
  }

  function renderPlans() {
    var s = state.subscribe;
    var box = $('planList');
    if (!s.plans.length) {
      box.innerHTML = s.err
        ? '<p class="placeholder">套餐读取失败，可退出后重新进入本屏重试。</p>'
        : '<p class="placeholder">正在读取套餐…</p>';
      syncSubscribeButton();
      return;
    }
    var html = s.plans.map(planCardHtml).join('');
    if (s.fallback) {
      html += '<p class="fineprint fineprint-dim plan-fallback">' +
              '套餐接口未取到，以上为内置默认档位；价格与有效期以服务端为准。</p>';
    }
    box.innerHTML = html;
    syncSubscribeButton();
  }

  function selectPlan(planId) {
    if (!findPlan(planId)) { return; }
    state.subscribe.selectedId = planId;
    renderPlans();
    syncSubNotice();
  }

  function syncSubscribeButton() {
    var s = state.subscribe;
    var plan = findPlan(s.selectedId);
    var chip = $('subSelectedChip');
    if (plan) {
      chip.hidden = false;
      chip.textContent = plan.name + ' · ' + fmtInt(plan.price_cents) + ' 积分 / ' + num(plan.days) + ' 天';
    } else {
      chip.hidden = true;
      chip.textContent = '';
    }
    $('btnSubscribe').disabled = (!plan || s.busy);
    if (s.busy) { $('btnSubscribe').setAttribute('aria-busy', 'true'); }
    else { $('btnSubscribe').removeAttribute('aria-busy'); }
    $('subscribeText').textContent = s.busy ? '正在提交…'
      : (plan ? '用积分订阅（' + fmtInt(plan.price_cents) + ' 积分）' : '用积分订阅');
  }

  /** 最近一笔订单：成功显示订单号/金额/渠道/状态；失败显示可读原因 */
  function renderOrderBox() {
    var o = state.subscribe.lastOrder;
    var box = $('orderBox');
    if (!o) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    box.className = 'order-box' + (o.ok ? '' : ' is-fail');

    var html = '<p class="order-title">' + (o.ok ? '最近一笔订单' : '最近一次提交未成功') + '</p>';
    if (o.ok) {
      html += '<p class="order-line">订单号：<b>' + esc(o.order_no || '未返回') + '</b>' +
              (o.status ? '<span class="order-state' + (o.status === 'paid' ? '' : ' is-wait') + '">' +
                          esc(orderStateText(o.status)) + '</span>' : '') + '</p>' +
              '<p class="order-line">金额：<b>' + fmtInt(o.amount_cents) + ' 积分</b>' +
              ' · 支付渠道：<b>' + esc(channelText(o.channel)) + '</b></p>';
    }
    if (o.planName) {
      html += '<p class="order-line">套餐：<b>' + esc(o.planName) + '</b>' +
              (o.at ? ' · 提交时间：' + esc(fmtTime(o.at)) : '') + '</p>';
    }
    if (o.note) { html += '<p class="order-line">' + esc(o.note) + '</p>'; }
    box.innerHTML = html;
  }

  /** 用积分订阅：余额不足先提示，仍提交由服务端裁决 */
  function submitSubscribe() {
    var s = state.subscribe;
    var plan = findPlan(s.selectedId);
    hideAlert();
    if (s.busy) { return; }
    if (!plan) {
      showAlert('请先选择一个套餐。');
      return;
    }

    // ① 前端先提示（写明还需多少积分），但不拦截提交：最终以服务端裁决为准
    var bal = currentBalance();
    var price = num(plan.price_cents);
    if (bal !== null && bal < price) {
      showSubNotice('积分不足：还需 ' + fmtInt(price - bal) + ' 积分（当前 ' + fmtInt(bal) +
                    ' 积分，需要 ' + fmtInt(price) + ' 积分）。已提交，由服务端最终裁决。');
    }

    s.busy = true;
    syncSubscribeButton();

    apiFetch('/subscribe/order', {
      method: 'POST',
      idempotencyKey: uid('sub-'),    // 同一次提交复用同一个幂等键，重复点击不会重复扣积分
      body: { plan_id: plan.plan_id, pay_with: 'points' }
    }).then(function (env) {
      var d = env.data || {};
      s.lastOrder = {
        ok: true,
        order_no: String(d.order_no || ''),
        amount_cents: num(d.amount_cents !== undefined ? d.amount_cents : plan.price_cents),
        status: String(d.status || ''),
        channel: String(d.channel || 'points'),
        planName: plan.name,
        at: nowLocal()
      };
      renderOrderBox();
      toast('订阅成功：' + plan.name + ' 已开通，积分与明细正在刷新…', 'ok');
      // ② 成功后刷新余额与订单状态（同时把明细与收益对齐）
      return refreshAfterOrder();
    }).catch(function (err) {
      s.lastOrder = {
        ok: false,
        planName: plan.name,
        at: nowLocal(),
        note: insufficient(err)
          ? '余额不足，未开单。请先在「我的积分」查看余额。'
          : readableError(err)
      };
      renderOrderBox();
      // 余额不足时不重复念「积分不足」（服务端文案里通常已经有了）
      showAlert(insufficient(err)
        ? ('本次未开通：' + readableError(err) + ' 可先在「我的积分」查看余额。')
        : ('订阅未完成：' + readableError(err)));
      // 服务端可能已改变余额口径，回读一次对齐
      return refreshAfterOrder();
    }).then(function () {
      s.busy = false;
      syncSubscribeButton();
    });
  }

  /** 余额不足类业务码：契约未定死，按 code 与文案双重判断，兼容即可 */
  function insufficient(err) {
    if (!err) { return false; }
    var code = num(err.code, 0);
    if (code === 30001 || code === 30002 || code === 40020 || code === 40021) { return true; }
    return /积分不足|余额不足|insufficient/i.test(String(err.message || ''));
  }

  /* ── 积分 / 收益屏：渲染 ───────────────────────────────── */

  function renderPointsSummary() {
    var p = state.points;
    var has = (p.balance !== null && p.balance !== undefined);
    setAmount($('subBalance'), has ? p.balance : null);
    setAmount($('ptBalance'), has ? p.balance : null);
    $('ptEarned').textContent = (p.earned === null || p.earned === undefined)
      ? '—' : (fmtInt(p.earned) + ' 积分');
    $('ptSpent').textContent = (p.spent === null || p.spent === undefined)
      ? '—' : (fmtInt(p.spent) + ' 积分');

    var note = $('subBalanceNote');
    if (p.err.balance) {
      note.className = 'balance-note is-err';
      note.textContent = '积分余额读取失败：' + readableError(p.err.balance);
    } else if (!has) {
      note.className = 'balance-note';
      note.textContent = '正在读取积分余额…';
    } else {
      note.className = 'balance-note';
      note.textContent = '测试期以积分结算，不涉及真实支付（1 积分 = 1 分）。';
    }
  }

  function renderLedger() {
    var p = state.points;
    var lg = p.ledger;
    var box = $('ledgerBody');
    var more = $('btnMoreLedger');
    var count = $('ledgerCount');

    var failErr = p.err.ledger;

    if (!lg.items.length) {
      box.innerHTML = failErr
        ? '<p class="ledger-empty">积分明细读取失败：' + esc(readableError(failErr)) +
          '（可退出后重新进入本屏重试。）</p>'
        : (lg.loaded
            ? '<p class="ledger-empty">还没有积分记录。测试期可由后台发放积分后回到本屏查看。</p>'
            : '<p class="placeholder">正在读取…</p>');
      more.hidden = true;
      count.textContent = lg.loaded && !failErr ? '共 0 条' : '';
      return;
    }

    box.innerHTML = lg.items.map(function (it) {
      var din = num(it.delta) >= 0;
      return '<div class="ledger-item">' +
               '<div class="ledger-main">' +
                 '<span class="ledger-reason">' + esc(reasonText(it.reason)) + '</span>' +
                 '<span class="ledger-meta">' + esc(fmtTime(it.created_at)) +
                   (it.ref ? ' · 关联订单 ' + esc(it.ref) : '') + '</span>' +
               '</div>' +
               '<span class="ledger-delta ' + (din ? 'is-in' : 'is-out') + '">' +
                 (din ? '+' : '−') + fmtInt(Math.abs(num(it.delta))) +
               '</span>' +
             '</div>';
    }).join('');

    more.hidden = !lg.hasMore;
    more.disabled = !!lg.loading;
    more.textContent = lg.loading ? '正在加载…' : '加载更多';
    count.textContent = '已加载 ' + lg.items.length + ' 条';
  }

  function renderCommission() {
    var p = state.points;
    var c = p.commission;
    var idMap = {
      cmTotal: 'total', cmPending: 'pending', cmSettled: 'settled', cmReversed: 'reversed'
    };
    if (!c) {
      Object.keys(idMap).forEach(function (id) { $(id).textContent = '—'; });
      setAmount($('cmNet'), null);
      $('cmNote').textContent = p.err.commission
        ? '推广收益读取失败：' + readableError(p.err.commission)
        : '正在读取推广收益…';
      return;
    }
    Object.keys(idMap).forEach(function (id) {
      $(id).textContent = fmtInt(c[idMap[id]]) + ' 积分';
    });
    setAmount($('cmNet'), c.net);

    var pct = num(c.rate_bp) / 100;                       // 3000 → 30
    var pctText = (Math.round(pct * 100) % 100 === 0)
      ? String(Math.round(pct)) : pct.toFixed(2);
    $('cmRateChip').textContent = '费率 ' + pctText + '%';
    $('cmNote').textContent = '按实付积分 × ' + pctText + '% 计；' +
      '测试期以积分结算，不涉及真实支付。';

    // 提现：本期固定不开放（按钮始终置灰，说明文字固定）
    $('btnWithdraw').disabled = true;
    $('withdrawNote').textContent = WITHDRAW_NOTE;
  }

  /* ══════════════════════════════════════════════════════════
   * 十二、事件绑定与启动
   * ══════════════════════════════════════════════════════════ */

  /* ══════════════════════════════════════════════════════════
   * 十一之三、家庭健康档案（v11：添加家人）
   *
   * 接口契约（后端冻结，见 server/family.py；全部要求登录）：
   *   GET    /family                        → {members, summary, disclaimer, reminders}
   *   POST   /family/members                {nickname, relation_code, birth_local, longitude, latitude}
   *   POST   /family/members/update         {family_id, …同上（可只传变化项）}
   *   DELETE /family/members/{family_id}    → {family_id, removed: true, summary}
   *   POST   /family/remind                 {family_id, kind, text}  ← 当日同 kind 幂等
   *   GET    /family/reminders              → {items, count, limit}
   *
   * 三条前端口径（与变更单 §二 一致）：
   *   ① **家人的等级一律不显示**（接口 level 恒为 null），只显示「基线建立中 0/7」；
   *      本屏**不出现 L0–L4 字样**——A/B/C/D 是当日**时相分档**，与观察等级不同源、不可混排。
   *   ② 家庭席位上限 8 位（产品口径）：这里只用于**提前提示**（满员时收起表单），
   *      最终裁决以后端为准（超限时后端回可读中文「家庭席位已满（8 位）…」）。
   *   ③ 家人资料只属于录入者：本屏所有请求都不携带任何他人标识，家人也不是账号、没有 member_id。
   * ══════════════════════════════════════════════════════════ */

  var FAMILY_SEAT_LIMIT = 8;

  /* 关系字典：前端只传 code，中文名由服务端映射（这里只用于下拉选项与本地兜底展示） */
  var FAMILY_RELATIONS = [
    ['self', '本人'], ['father', '父亲'], ['mother', '母亲'], ['spouse', '配偶'],
    ['child', '子女'], ['sibling', '兄弟姐妹'], ['grandparent', '祖辈'], ['other', '其他']
  ];

  /* 关怀提醒的四个类型 + 默认文案（与后端 family.DEFAULT_REMIND_TEXT 同一份中性文案） */
  var FAMILY_KINDS = [
    { code: 'care', name: '关怀提醒', text: '今天记得早点休息' },
    { code: 'checkin', name: '提醒记录', text: '今天别忘了记录一下' },
    { code: 'birthday', name: '生日祝福', text: '祝你生日快乐，健康常伴' },
    { code: 'custom', name: '自定义', text: '' }
  ];
  var FAMILY_KIND_NAME = { care: '关怀', checkin: '记录提醒', birthday: '生日祝福', custom: '自定义' };

  /** 家庭席位文案（后端 family.BASELINE_TEXT 的同一口径：家人没有观测史，已观测恒为 0） */
  function famBaselineText(m) {
    return (m && m.baseline_text) ? String(m.baseline_text) : '基线建立中 0/7';
  }

  /** 入口文案：已有家人 → 「家庭健康档案（n）」；0 位或还没取到 → 「添加家人」 */
  function refreshFamilyEntry() {
    var f = state.family;
    var n = (f.loaded && f.summary) ? num(f.summary.count, 0) : -1;
    var label = (n > 0) ? ('家庭健康档案（' + n + '）') : '添加家人';
    var home = $('btnHomeFamilyText');
    if (home) { home.textContent = label; }
    var fromProfile = $('btnFamilyFromProfile');
    if (fromProfile) { fromProfile.textContent = label; }
  }

  /** 启动期静默预取：只为了让首页入口显示「家庭健康档案（n）」；失败不进错误条（进本屏会再取） */
  function prefetchFamilyEntry() {
    if (state.family.loaded) { return; }
    apiFetch('/family').then(function (env) {
      var d = env.data || {};
      state.family.members = d.members || [];
      state.family.summary = d.summary || null;
      state.family.reminders = d.reminders || [];
      state.family.loaded = true;
      refreshFamilyEntry();
    }, function () { /* 静默失败：入口保持「添加家人」，进入本屏时会再取一次 */ });
  }

  function famErr(id, msg) { fieldError(id, msg); }

  function familySkeleton() {
    var f = state.family;
    if (!f.loaded) {
      $('famSummary').textContent = '正在读取…';
      $('famList').innerHTML = '<p class="placeholder">正在读取…</p>';
      $('famRemindList').innerHTML = '<p class="placeholder">正在读取…</p>';
    }
  }

  /** 进入家庭档案屏：一次 GET /family 拿全部数据；失败给可读提示，页面不白屏 */
  function loadFamily(force) {
    var f = state.family;
    if (f.loading) { return Promise.resolve(); }
    if (f.loaded && !force) { renderFamilyAll(); return Promise.resolve(); }
    f.loading = true;
    familySkeleton();
    refreshFamilyEntry();
    return apiFetch('/family').then(function (env) {
      f.loading = false; f.loaded = true; f.err = null;
      var d = env.data || {};
      f.members = d.members || [];
      f.summary = d.summary || null;
      f.reminders = d.reminders || [];
      f.disclaimer = d.disclaimer || '';
      renderFamilyAll();
    }, function (err) {
      f.loading = false; f.err = err;
      renderFamilyAll();
      showAlert('家庭健康档案读取失败：' + readableError(err) +
                '（可退出后重新进入本屏重试。）');
    });
  }

  function renderFamilyAll() {
    renderFamilySummary();
    renderFamilyList();
    renderFamilyReminders();
    refreshFamilyEntry();
    if (!state.family.editingId) { syncFamSaveButton(); }
  }

  function renderFamilySummary() {
    var f = state.family;
    var s = f.summary;
    var box = $('famSummary');
    if (!s) {
      box.textContent = f.err ? '读取失败，可退出后重新进入本屏重试。' : '正在读取…';
      $('famSeatChip').textContent = '— / ' + FAMILY_SEAT_LIMIT + ' 位';
      return;
    }
    var n = num(s.count, 0);
    var avg = (s.avg_score === null || s.avg_score === undefined) ? null : num(s.avg_score);
    var att = num(s.attention_count, 0);
    box.textContent = '全家 ' + n + ' 人 · 平均指数 ' + (avg === null ? '—' : avg) +
                      ' · 需关注 ' + att + ' 人';
    $('famSeatChip').textContent = n + ' / ' + FAMILY_SEAT_LIMIT + ' 位';
  }

  /** 家人卡片：称呼 / 关系 / 今日指数与分档 / 基线建立中 n/7 / 最近提醒 + 三个操作 */
  function famItemHtml(m) {
    var fid = String(m.family_id || '');
    var nick = String(m.nickname || '');
    var idx = (m.index && typeof m.index === 'object') ? m.index : null;
    var has = hasIndex(idx);
    var code = has ? String(idx.band || '').toUpperCase() : '';
    var tone = bandTone(code);
    var bname = has ? bandName(code, idx.band_name || idx.band) : '';

    // 分数与分档：家人算不出分时如实写「指数生成中」，不拿 0 冒充
    var scoreHtml = has
      ? '<span class="fam-score-num' + (tone ? ' tone-' + tone : '') + '">' +
          esc(Math.round(num(idx.score))) + '</span>' +
        '<span class="idx-unit">分</span>' +
        (bname ? '<span class="fam-band' + (tone ? ' tone-' + tone : '') + '">' +
                   esc(code ? (code + ' · ' + bname) : bname) + '</span>' : '')
      : '<span class="fam-score-pending">指数生成中</span>';

    // ★ 等级一律不显示（接口 level 恒为 null）：这里只写「基线建立中 0/7」
    var sub = [];
    if (m.relation) { sub.push(String(m.relation)); }
    if (m.age !== null && m.age !== undefined && m.age !== '') { sub.push(num(m.age) + ' 岁'); }
    if (m.birth_local) { sub.push(String(m.birth_local)); }
    var lastAt = m.last_reminded_at ? relTime(m.last_reminded_at) : '';

    return '<article class="fam-item" data-fid="' + esc(fid) + '">' +
      '<div class="fam-top">' +
        '<span class="fr-avatar" aria-hidden="true">' + esc(initials(nick)) + '</span>' +
        '<span class="fam-main">' +
          '<span class="fam-name">' + esc(nick) + '</span>' +
          '<span class="fam-sub">' + esc(sub.join(' · ')) + '</span>' +
        '</span>' +
        '<span class="fam-score">' + scoreHtml + '</span>' +
      '</div>' +
      '<p class="fam-baseline">' +
        '<span class="fam-baseline-tag">' + esc(famBaselineText(m)) + '</span>' +
        (lastAt ? '<span class="fam-last">最近提醒 ' + esc(lastAt) + '</span>' : '') +
      '</p>' +
      '<div class="fam-actions">' +
        '<button type="button" class="fr-btn" data-fam-remind="' + esc(fid) +
          '" data-nick="' + esc(nick) + '">关怀提醒</button>' +
        '<button type="button" class="fr-btn fr-btn-quiet" data-fam-edit="' + esc(fid) +
          '">编辑</button>' +
        '<button type="button" class="fr-btn fr-btn-quiet" data-fam-del="' + esc(fid) +
          '" data-nick="' + esc(nick) + '">删除</button>' +
      '</div>' +
    '</article>';
  }

  function renderFamilyList() {
    var f = state.family;
    var box = $('famList');
    var empty = $('famEmpty');
    var items = f.members || [];

    if (!items.length) {
      box.innerHTML = '';
      empty.hidden = false;
      // 满员时不给「添加家人」按钮（点后端也会回可读中文），并如实说明原因
      var full = f.summary && num(f.summary.count, 0) >= FAMILY_SEAT_LIMIT;
      $('btnFamAdd').disabled = !!full;
      $('btnFamAddTop').hidden = !!full;
      if (f.err) { empty.hidden = true; box.innerHTML =
        '<p class="placeholder">读取失败，可退出后重新进入本屏重试。</p>'; }
      return;
    }
    empty.hidden = true;
    box.innerHTML = items.map(famItemHtml).join('');
    var full2 = num((f.summary || {}).count, items.length) >= FAMILY_SEAT_LIMIT;
    $('btnFamAddTop').hidden = !!full2;
  }

  function renderFamilyReminders() {
    var f = state.family;
    var box = $('famRemindList');
    var items = f.reminders || [];
    if (!items.length) {
      box.innerHTML = '<p class="placeholder">还没有发过关怀提醒。' +
        '在家人卡片上点「关怀提醒」，当天同一种提醒只会记一条。</p>';
      return;
    }
    box.innerHTML = items.map(function (r) {
      var kind = FAMILY_KIND_NAME[String(r.kind || '')] || '提醒';
      return '<div class="fam-remind-item">' +
        '<p class="fam-remind-top">' +
          '<span class="fam-remind-nick">' + esc(String(r.nickname || '家人')) + '</span>' +
          '<span class="chip chip-quiet">' + esc(kind) + '</span>' +
          '<span class="fam-remind-time">' +
            esc(r.created_at ? String(r.created_at).replace('T', ' ').slice(0, 16) : '') +
          '</span>' +
        '</p>' +
        '<p class="fam-remind-text">' + esc(String(r.text || '')) + '</p>' +
      '</div>';
    }).join('');
  }

  /* ── 添加 / 编辑表单 ─────────────────────────────────────── */

  function buildFamFormOptions() {
    var rel = $('famRelation');
    if (rel && !rel.options.length) {
      rel.innerHTML = FAMILY_RELATIONS.map(function (p) {
        return '<option value="' + esc(p[0]) + '">' + esc(p[1]) + '</option>';
      }).join('');
    }
    var city = $('famCity');
    if (city && city.options.length <= 2) { city.innerHTML = cityOptionsHtml(); }
  }

  function syncFamSaveButton() {
    var editing = !!state.family.editingId;
    $('famFormTitle').textContent = editing ? '编辑家人' : '添加家人';
    $('famSaveText').textContent = editing ? '保存修改' : '保存家人';
  }

  /** 展开表单；传 member 时进入「编辑」态并回填，不传则是「添加」态 */
  function openFamForm(member) {
    buildFamFormOptions();
    var m = member || null;
    state.family.editingId = m ? String(m.family_id || '') : '';
    $('famNickname').value = m ? String(m.nickname || '') : '';
    $('famRelation').value = m ? String(m.relation_code || 'other') : 'mother';
    var birth = m ? String(m.birth_local || '') : '';
    $('famBirthDate').value = birth ? birth.slice(0, 10) : '';
    $('famBirthTime').value = birth.length > 11 ? birth.slice(11, 16) : '';
    $('famLng').value = m ? String(num(m.longitude)) : '';
    $('famLat').value = m ? String(num(m.latitude)) : '';
    // 编辑态下城市下拉无从反查（后端只存经纬度），保持「手动输入经纬度」并开放输入
    $('famCity').value = '__manual__';
    $('famCity').selectedIndex = 1;
    setFamCoordEditable(true);
    $('famCityHint').textContent = m
      ? '已按现有经纬度回填；如需换城市，请从下拉里选一个或直接改下面的数值。'
      : '请选择常用城市，或直接填写经纬度。';
    famErr('famNicknameErr', ''); famErr('famBirthErr', '');
    famErr('famCoordErr', ''); famErr('famFormErr', '');
    syncFamSaveButton();
    $('famFormCard').hidden = false;
    try { $('famNickname').focus({ preventScroll: true }); } catch (e) { /* 忽略 */ }
  }

  function closeFamForm() {
    state.family.editingId = '';
    $('famFormCard').hidden = true;
    syncFamSaveButton();
  }

  function setFamCoordEditable(editable) {
    $('famLng').readOnly = !editable;
    $('famLat').readOnly = !editable;
  }

  function onFamCityChange() {
    var sel = $('famCity');
    var opt = sel.options[sel.selectedIndex];
    if (sel.value === '__manual__') {
      setFamCoordEditable(true);
      $('famCityHint').textContent = '请输入出生地经纬度，精确到小数点后 4 位即可。';
      return;
    }
    if (opt && opt.dataset && opt.dataset.lng) {
      $('famLng').value = opt.dataset.lng;
      $('famLat').value = opt.dataset.lat;
      setFamCoordEditable(false);
      $('famCityHint').textContent = '已填入 ' + sel.value + ' 的经纬度；如需修改请选择「手动输入经纬度」。';
      return;
    }
    setFamCoordEditable(true);
  }

  /** 提交添加 / 修改：本地先做一遍可读校验，服务端仍是最终裁决 */
  function saveFamMember(ev) {
    if (ev && ev.preventDefault) { ev.preventDefault(); }
    var f = state.family;
    if (f.saving) { return; }
    famErr('famNicknameErr', ''); famErr('famBirthErr', '');
    famErr('famCoordErr', ''); famErr('famFormErr', '');

    var nickname = String($('famNickname').value || '').trim();
    var relation = String($('famRelation').value || 'other');
    var date = String($('famBirthDate').value || '');
    var time = String($('famBirthTime').value || '');
    var lng = String($('famLng').value || '').trim();
    var lat = String($('famLat').value || '').trim();

    var bad = false;
    if (!nickname) {
      famErr('famNicknameErr', '请填写称呼。'); $('famNickname').focus(); bad = true;
    } else if (nickname.length > 12) {
      famErr('famNicknameErr', '称呼最多 12 个字。'); bad = true;
    }
    if (!date) {
      famErr('famBirthErr', '请选择出生日期。'); bad = true;
    } else if (date > ymd()) {
      famErr('famBirthErr', '出生日期不能晚于今天。'); bad = true;
    }
    if (lng === '' || lat === '' || !isFinite(Number(lng)) || !isFinite(Number(lat))) {
      famErr('famCoordErr', '请选择常用城市，或手动填写出生地经纬度。'); bad = true;
    } else if (Number(lng) < -180 || Number(lng) > 180 || Number(lat) < -90 || Number(lat) > 90) {
      famErr('famCoordErr', '经度需在 -180 与 180 之间、纬度需在 -90 与 90 之间。'); bad = true;
    }
    if (bad) { return; }

    var body = {
      nickname: nickname,
      relation_code: relation,
      birth_local: date + ' ' + (time || '12:00'),
      longitude: Number(lng),
      latitude: Number(lat)
    };
    var editing = !!f.editingId;
    var path = '/family/members';
    if (editing) { path = '/family/members/update'; body.family_id = f.editingId; }

    f.saving = true;
    busy(true);
    apiFetch(path, { method: 'POST', body: body }).then(function () {
      f.saving = false; busy(false);
      toast(editing ? '已保存家人信息。' : '已添加家人，卡片上能看到 TA 今天的指数。', 'ok');
      closeFamForm();
      return loadFamily(true);
    }, function (err) {
      f.saving = false; busy(false);
      // 报错一律可读中文：服务端的 message 直接展示（如「这个家人已经添加过了」）
      famErr('famFormErr', readableError(err));
    });
  }

  /** 删除家人（二次确认；确认后我为 TA 记录的关怀提醒也会一并清掉） */
  function removeFamMember(fid, nick) {
    if (!fid) { return; }
    openConfirm('删除家人',
                '确定要删除「' + (nick || '这位家人') + '」吗？删除后，我为 TA 记录的关怀提醒也会一并清掉。',
                '删除', function () {
      busy(true);
      apiFetch('/family/members/' + encodeURIComponent(fid), { method: 'DELETE' })
        .then(function () {
          busy(false);
          if (state.family.editingId === fid) { closeFamForm(); }
          toast('已删除「' + (nick || '该家人') + '」。', 'ok');
          return loadFamily(true);
        }, function (err) {
          busy(false);
          showAlert('删除失败：' + readableError(err));
        });
    });
  }

  /* ── 关怀提醒抽屉 ─────────────────────────────────────────── */

  function renderFamKindList() {
    var f = state.family;
    $('famKindList').innerHTML = FAMILY_KINDS.map(function (k) {
      var on = (k.code === f.remindKind);
      return '<button type="button" class="fam-kind-btn' + (on ? ' is-on' : '') + '"' +
             ' role="radio" aria-checked="' + (on ? 'true' : 'false') + '"' +
             ' data-famkind="' + esc(k.code) + '">' +
             '<span class="fam-kind-name">' + esc(k.name) + '</span>' +
             (k.text ? '<span class="fam-kind-sub">' + esc(k.text) + '</span>' : '') +
             '</button>';
    }).join('');
  }

  function pickFamKind(kind) {
    var f = state.family;
    f.remindKind = kind;
    var preset = '';
    FAMILY_KINDS.forEach(function (k) { if (k.code === kind) { preset = k.text; } });
    $('famRemindText').value = preset;
    famErr('famRemindErr', '');
    renderFamKindList();
  }

  function openFamRemindSheet(fid, nick) {
    var f = state.family;
    f.remindTarget = { family_id: fid, nickname: nick || '' };
    $('famRemindTip').textContent = '给「' + (nick || '这位家人') + '」发一条提醒。' +
      '同一天、同一种提醒只会记一条（重复发送会保留最先那条）。';
    pickFamKind('care');
    openSheet('famRemindSheet', 'famRemindText');
  }

  function closeFamRemindSheet() {
    state.family.remindTarget = null;
    closeSheet('famRemindSheet');
    focusIfVisible('famList');
  }

  function sendFamRemind() {
    var f = state.family;
    var t = f.remindTarget;
    if (!t || !t.family_id) { closeFamRemindSheet(); return; }
    famErr('famRemindErr', '');
    var text = String($('famRemindText').value || '').trim();
    if (f.remindKind === 'custom' && !text) {
      famErr('famRemindErr', '自定义提醒需要填写内容。'); return;
    }
    if (text.length > 60) { famErr('famRemindErr', '提醒内容不超过 60 个字。'); return; }
    busy(true);
    apiFetch('/family/remind', {
      method: 'POST',
      body: { family_id: t.family_id, kind: f.remindKind, text: text }
    }).then(function (env) {
      busy(false);
      var d = env.data || {};
      toast(d.repeated ? '今天已经给「' + (t.nickname || '这位家人') + '」发过这类提醒了，保留原来那条。'
                       : '提醒已记录。', 'ok');
      closeFamRemindSheet();
      return loadFamily(true);
    }, function (err) {
      busy(false);
      famErr('famRemindErr', readableError(err));
    });
  }

  function bind() {
    $('btnStart').addEventListener('click', function () { showView('profile'); });
    $('btnHomeRhythm').addEventListener('click', function () { showView('rhythm'); });
    $('btnHomeFriends').addEventListener('click', function () { showView('friends'); });

    // v14：首页指数卡自带签到按钮与「查看今日详细节律」入口
    $('btnHomeCheckin').addEventListener('click', function () {
      checkin('btnHomeCheckin', 'homeCheckinText');
    });
    $('btnHomeDailyMore').addEventListener('click', function () { showView('rhythm'); });

    $('btnBack').addEventListener('click', function () {
      // v15：按进入顺序回退（点 tab 会清栈，所以栈空即回首页）
      var back = viewStack.pop();
      if (state.view === 'rhythm' && !state.profileCompleted) { showView('profile', { push: false }); return; }
      showView(back || 'home', { push: false });
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

    $('btnCheckin').addEventListener('click', function () {
      checkin('btnCheckin', 'checkinText');
    });
    $('btnHistory').addEventListener('click', openHistory);
    $('btnCloseHistory').addEventListener('click', closeHistory);
    $('sheetBackdrop').addEventListener('click', function () {
      // 一次只可能有一层抽屉：从上层往下关
      if (!$('confirmSheet').hidden) { closeConfirmSheet(); return; }
      if (!$('authSheet').hidden) { closeAuthSheet(); return; }
      if (!$('famRemindSheet').hidden) { closeFamRemindSheet(); return; }
      if (!$('cheerSheet').hidden) { closeCheerSheet(); return; }
      if (!$('historySheet').hidden) { closeHistory(); }
    });

    /* ── 登录 / 注册：两个独立入口（v12.1）────────────────────── */
    $('btnAuthEntry').addEventListener('click', function () { openAuthSheet('login'); });
    $('btnAuthEntryReg').addEventListener('click', function () { openAuthSheet('register'); });
    $('btnCloseAuth').addEventListener('click', closeAuthSheet);
    $('btnAuthCancel').addEventListener('click', closeAuthSheet);
    $('btnAuthSubmit').addEventListener('click', submitAuth);
    $('btnAuthForgot').addEventListener('click', function () { setAuthMode('recover'); });
    $('btnAuthLogout').addEventListener('click', logoutAuth);
    ['inAuthPhone', 'inAuthPwd', 'inAuthPwd2'].forEach(function (id) {
      $(id).addEventListener('input', function () { fieldError('authErr', ''); });
      $(id).addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); submitAuth(); }
      });
    });
    $('btnMoreHistory').addEventListener('click', function () { loadHistory(true, false); });

    /* ── 好友圈：邀请链接 / 修改昵称 / 添加 / 待确认 ─────────── */
    $('btnCopyInvite').addEventListener('click', copyInvite);
    $('btnSaveNickname').addEventListener('click', saveNickname);
    $('inNickname').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); saveNickname(); }
    });
    $('inNickname').addEventListener('input', function () { fieldError('nicknameErr', ''); });
    $('btnAddFriend').addEventListener('click', addFriend);
    $('inInviteCode').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); addFriend(); }
    });
    $('inInviteCode').addEventListener('input', function () { fieldError('inviteErr', ''); });

    /* ── 好友圈：事件委托（开关 / 接受 / 拒绝 / 加油 / 解除）──
       全部是原生 <button>，键盘 Enter/Space 与点击同路。 */
    $('screen-friends').addEventListener('click', function (e) {
      var root = this;
      // 每次查询都从本次点击的 target 重新向上找，避免闭包复用被改写的节点
      function closest(sel) {
        var el = e.target;
        while (el && el !== root) {
          if (el.matches && el.matches(sel)) { return el; }
          el = el.parentNode;
        }
        return null;
      }
      var sw = closest('[data-priv]');
      if (sw) {
        setPrivacy(sw.getAttribute('data-priv'), sw.getAttribute('aria-checked') !== 'true');
        return;
      }
      var ok = closest('[data-accept]');
      if (ok) { answerFriend(ok.getAttribute('data-accept'), true); return; }
      var no = closest('[data-reject]');
      if (no) { answerFriend(no.getAttribute('data-reject'), false); return; }
      var ch = closest('[data-cheer]');
      if (ch) { openCheerSheet(ch.getAttribute('data-cheer'), ch.getAttribute('data-nick')); return; }
      var rm = closest('[data-remove]');
      if (rm) { confirmRemoveFriend(rm.getAttribute('data-remove'), rm.getAttribute('data-nick')); return; }
    });

    /* ── 加油模板抽屉 ───────────────────────────────────────── */
    $('btnCloseCheer').addEventListener('click', closeCheerSheet);
    $('btnCancelCheer').addEventListener('click', closeCheerSheet);
    $('tmplList').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.matches && el.matches('[data-tid]'))) { el = el.parentNode; }
      if (el && el !== this && el.matches && el.matches('[data-tid]')) {
        sendCheer(el.getAttribute('data-tid'));
      }
    });

    /* ── 二次确认抽屉 ───────────────────────────────────────── */
    $('btnConfirmClose').addEventListener('click', closeConfirmSheet);
    $('btnConfirmCancel').addEventListener('click', closeConfirmSheet);
    $('btnConfirmOk').addEventListener('click', function () {
      var action = state.social.confirmAction;
      closeConfirmSheet();
      if (typeof action === 'function') { action(); }
    });

    // 今日关注：事件委托，标签是 <button>，键盘 Enter/Space 与点击同路
    $('attentionBody').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.classList && el.classList.contains('att-tag'))) { el = el.parentNode; }
      if (el && el !== this && el.classList && el.classList.contains('att-tag')) { toggleAttention(el); }
    });

    // 分享文案复制（纯文本，不依赖任何外网 SDK）
    $('btnCopyShare').addEventListener('click', copyShare);

    /* ── v8：订阅 / 我的积分 · 推广收益 ───────────────────────
       全部是原生 <button>，键盘 Enter/Space 与点击同路；
       提现按钮本期 disabled，键盘也进不去（不产生任何提现请求）。 */
    $('btnHomeSubscribe').addEventListener('click', function () { showView('subscribe'); });
    $('btnHomePoints').addEventListener('click', function () { showView('points'); });
    $('btnSubToPoints').addEventListener('click', function () { showView('points'); });
    $('btnPtToSubscribe').addEventListener('click', function () { showView('subscribe'); });

    $('btnSubscribe').addEventListener('click', submitSubscribe);
    $('btnMoreLedger').addEventListener('click', function () { loadPointsLedger(false); });

    // 套餐卡：事件委托，点哪张选哪张
    $('planList').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.getAttribute && el.getAttribute('data-plan'))) {
        el = el.parentNode;
      }
      if (el && el !== this && el.getAttribute) {
        selectPlan(el.getAttribute('data-plan'));
      }
    });

    $('alertClose').addEventListener('click', hideAlert);

    /* ── v11：家庭健康档案（添加家人）─────────────────────────
       全部是原生 <button>，键盘 Enter/Space 与点击同路；
       卡片上的三个操作走事件委托，新增/编辑共用同一张表单。 */
    $('btnHomeFamily').addEventListener('click', function () { showView('family'); });
    $('btnFamilyFromProfile').addEventListener('click', function () { showView('family'); });
    $('btnFamAdd').addEventListener('click', function () { openFamForm(null); });
    $('btnFamAddTop').addEventListener('click', function () { openFamForm(null); });
    $('btnFamFormCancel').addEventListener('click', closeFamForm);
    $('famForm').addEventListener('submit', saveFamMember);
    $('famCity').addEventListener('change', onFamCityChange);
    $('famNickname').addEventListener('input', function () { famErr('famNicknameErr', ''); });
    $('famBirthDate').addEventListener('change', function () { famErr('famBirthErr', ''); });
    $('famLng').addEventListener('input', function () { famErr('famCoordErr', ''); });
    $('famLat').addEventListener('input', function () { famErr('famCoordErr', ''); });

    $('screen-family').addEventListener('click', function (e) {
      var root = this;
      function closest(sel) {
        var el = e.target;
        while (el && el !== root) {
          if (el.matches && el.matches(sel)) { return el; }
          el = el.parentNode;
        }
        return null;
      }
      var rm = closest('[data-fam-remind]');
      if (rm) {
        openFamRemindSheet(rm.getAttribute('data-fam-remind'), rm.getAttribute('data-nick'));
        return;
      }
      var ed = closest('[data-fam-edit]');
      if (ed) {
        var fid = ed.getAttribute('data-fam-edit');
        var hit = (state.family.members || []).filter(function (m) {
          return String(m.family_id) === String(fid);
        })[0];
        openFamForm(hit || null);
        return;
      }
      var dl = closest('[data-fam-del]');
      if (dl) { removeFamMember(dl.getAttribute('data-fam-del'), dl.getAttribute('data-nick')); }
    });

    $('btnFamRemindClose').addEventListener('click', closeFamRemindSheet);
    $('btnFamRemindCancel').addEventListener('click', closeFamRemindSheet);
    $('btnFamRemindSend').addEventListener('click', sendFamRemind);
    $('famRemindText').addEventListener('input', function () { famErr('famRemindErr', ''); });
    $('famKindList').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.getAttribute && el.getAttribute('data-famkind'))) {
        el = el.parentNode;
      }
      if (el && el !== this && el.getAttribute) {
        pickFamKind(el.getAttribute('data-famkind'));
      }
    });

    bindMine();          // v15：我的（用户中心）/ 底部导航 / 账号与安全 / 问题解答

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') { return; }
      if (!$('confirmSheet').hidden) { closeConfirmSheet(); return; }
      if (!$('authSheet').hidden) { closeAuthSheet(); return; }
      if (!$('famRemindSheet').hidden) { closeFamRemindSheet(); return; }
      if (!$('cheerSheet').hidden) { closeCheerSheet(); return; }
      if (!$('historySheet').hidden) { closeHistory(); }
    });
  }

  /* ══════════════════════════════════════════════════════════
   * 十五、我的（用户中心）/ 账号与安全 / 问题解答  —— v15
   *   2026-10-09 师父令：「别人的用户中心，基本的都要做上去」。
   *   ① 入口收口：原先散落在首页的那一堆按钮，在「我的」里聚合成列表；
   *   ② 补齐基本项：**修改密码**、修改昵称、退出登录、登录方式说明、问题解答；
   *   ③ 底部导航（首页 / 今日节律 / 我的），只在顶级页出现。
   * ══════════════════════════════════════════════════════════ */

  /** 我的（用户中心）：账号卡 + 各条目右侧小注（全部取现成 state，不额外发请求） */
  function renderMine() {
    if (!$('mineNick')) { return; }
    var s = state.social || {};
    var logged = !!authState.hasPassword;
    var nick = String(s.nickname || '');

    $('mineNick').textContent = logged ? (nick || '已登录') : '未登录';
    $('mineSub').textContent = logged
      ? ('手机号 ' + (authState.phoneMasked || '—') + '（只用于登录，不对外显示）')
      : '用「手机号」或「昵称」登录，档案与打卡记录跟着账号走';
    $('mineAvatar').textContent = nick ? Array.from(nick)[0] : '·';
    $('btnMineLogin').hidden = logged;

    $('mineProfileNote').textContent = state.profileCompleted ? '已建档' : '待建档';
    var idx = (state.daily && state.daily.index) || null;
    $('mineRhythmNote').textContent = (idx && idx.score !== undefined && idx.score !== null)
      ? ('今日 ' + Math.round(num(idx.score)) + ' 分') : '';
    var fam = (state.family && state.family.members) || [];
    $('mineFamilyNote').textContent = fam.length ? (fam.length + ' 位') : '未添加';
    $('mineInviteNote').textContent = s.inviteCode ? '专属链接' : '';
    var bal = (state.points && state.points.balance !== null
               && state.points.balance !== undefined) ? state.points.balance : null;
    $('minePointsNote').textContent = (bal === null) ? '' : (num(bal) + ' 分');
    $('mineSubNote').textContent = (state.subscribe && state.subscribe.lastOrder) ? '已开通' : '未开通';
    $('mineFriendsNote').textContent = '';
    $('mineAccountNote').textContent = logged ? '' : '需登录';
    var lo = $('btnMineLogout');
    if (lo) { lo.hidden = !logged; }
  }

  /** 账号与安全：回填昵称 / 密码状态 / 两种登录方式的说明 */
  function renderAccount() {
    var s = state.social || {};
    var logged = !!authState.hasPassword;
    renderNicknameInput();                       // 复用既有回填（用户正在输入时不覆盖）

    var chip = $('pwdStateChip');
    if (chip) { chip.hidden = false; chip.textContent = logged ? '已设置密码' : '未设置密码'; }
    $('pwdNoAccountHint').hidden = logged;
    $('btnChangePwd').disabled = !logged;
    $('loginWaysText').innerHTML = logged
      ? ('当前账号有两种登录方式：<br>① <strong>手机号</strong> ' + esc(authState.phoneMasked || '—') +
         ' ＋ 密码；<br>② <strong>昵称</strong> ' + esc(s.nickname || '—') + ' ＋ 密码。<br>' +
         '手机号只用于登录；分享链接、好友圈、排行榜里只出现昵称。')
      : '还没登录。登录后这里会显示你的两种登录方式（手机号 / 昵称）。';
  }

  /** 问题解答（静态文案，不依赖任何接口） */
  var HELP_ITEMS = [
    ['怎么打卡、在哪儿看今天的健康指数？',
     '打开首页最上方的「今日健康指数」卡片，点「今日签到」即可；分数与分档就在同一张卡上。打卡本身不需要先登录。'],
    ['指数是怎么算出来的？',
     '按你的出生日期、时刻与出生地做真太阳时校正，再结合当日时相推算，输出 A/B/C/D 四档与分数。' +
     '它属于生活方式参考，不属于医疗器械，不用于疾病的诊断、治疗或预防。'],
    ['为什么要先建档？',
     '指数依赖出生信息；没有建档就算不出分数。建档只要出生日期、时刻（可留空）与出生地，一分钟完成。'],
    ['昵称能做什么？可以改吗？',
     '昵称是你对外展示的名字，会出现在好友圈、排行榜与分享链接里，<strong>也可以当登录名</strong>。' +
     '全站唯一，7 天可改一次；改完旧昵称立即释放，新昵称马上能用来登录。'],
    ['手机号会对外显示吗？',
     '不会。手机号<strong>只用于登录</strong>；分享链接、好友圈、排行榜里一律只出现昵称。'],
    ['忘记密码怎么办？',
     '在登录面板点「忘记密码 / 设置密码」，用当前设备上的登录状态作证明即可重设。' +
     '若已换设备又忘了密码，请联系客服。'],
    ['换手机 / 换浏览器后数据没了？',
     '数显账号默认按设备生成。用「手机号或昵称 ＋ 密码」登录，就会回到你自己的账号，档案与打卡记录都在。'],
    ['家人档案别人能看到吗？',
     '不能。家人的称呼与出生信息只归你本人可见，不会出现在好友圈、排行榜或邀请链接里，随时可改可删。'],
    ['数据可以导出或删除吗？',
     '可以。在「我的 → 账号与安全」里可自助操作；如需删除全部数据，请联系客服按合规流程处理。']
  ];

  function renderHelp() {
    var box = $('helpList');
    if (!box) { return; }
    box.innerHTML = HELP_ITEMS.map(function (it, i) {
      return '<div class="help-item">' +
        '<button type="button" class="help-q" aria-expanded="false" data-help="' + i + '">' +
          esc(it[0]) + '<span class="help-mark" aria-hidden="true">›</span>' +
        '</button>' +
        '<div class="help-a" hidden><p>' + it[1] + '</p></div>' +
      '</div>';
    }).join('');
  }

  /** 修改密码：POST /auth/password/change（需登录 ＋ 验旧密码） */
  function changePassword() {
    if (state.pwdSaving) { return; }
    fieldError('pwdErr', '');
    var oldPwd = String($('inOldPwd').value || '');
    var newPwd = String($('inNewPwd').value || '');
    var newPwd2 = String($('inNewPwd2').value || '');
    if (!oldPwd) { fieldError('pwdErr', '请输入当前密码。'); $('inOldPwd').focus(); return; }
    if (newPwd.length < 6 || newPwd.length > 32) { fieldError('pwdErr', '新密码长度需在 6–32 位之间。'); return; }
    if (newPwd !== newPwd2) { fieldError('pwdErr', '两次输入的新密码不一致。'); return; }
    if (newPwd === oldPwd) { fieldError('pwdErr', '新密码不能与当前密码相同。'); return; }

    state.pwdSaving = true;
    var btn = $('btnChangePwd');
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    apiFetch('/auth/password/change', {
      method: 'POST',
      body: { old_password: oldPwd, new_password: newPwd }
    }).then(function () {
      $('inOldPwd').value = ''; $('inNewPwd').value = ''; $('inNewPwd2').value = '';
      toast('密码已修改，下次登录请用新密码。', 'ok');
    }).catch(function (err) {
      fieldError('pwdErr', readableError(err));
    }).then(function () {
      state.pwdSaving = false;
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
    });
  }

  /** v15：用户中心 / 底部导航 / 账号与安全 / 问题解答 的全部接线 */
  function bindMine() {
    var mine = $('screen-mine');
    if (mine) {
      mine.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== mine && !(el.getAttribute && el.getAttribute('data-goto'))) { el = el.parentNode; }
        if (el && el !== mine) { showView(el.getAttribute('data-goto')); }
      });
    }
    var bar = $('tabbar');
    if (bar) {
      bar.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== bar && !(el.getAttribute && el.getAttribute('data-tab'))) { el = el.parentNode; }
        if (el && el !== bar) { showView(el.getAttribute('data-tab')); }
      });
    }
    $('btnMineLogin').addEventListener('click', function () { openAuthSheet('login'); });
    $('btnMineLogout').addEventListener('click', logoutAuth);
    $('pwdForm').addEventListener('submit', function (e) { e.preventDefault(); changePassword(); });
    ['inOldPwd', 'inNewPwd', 'inNewPwd2'].forEach(function (id) {
      $(id).addEventListener('input', function () { fieldError('pwdErr', ''); });
    });
    $('btnDeleteAccount').addEventListener('click', function () {
      openConfirm('申请注销账号',
                  '注销后本机将退出登录；如需删除全部数据，客服会按合规流程与你确认。确定继续吗？',
                  '确定注销', function () {
        toast('已收到注销申请，客服会尽快与你联系。', 'ok');
      });
    });
    $('helpList').addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== this && !(el.getAttribute && el.getAttribute('data-help'))) { el = el.parentNode; }
      if (!el || el === this) { return; }
      var ans = el.parentNode.querySelector('.help-a');
      if (!ans) { return; }
      var willOpen = ans.hidden;
      ans.hidden = !willOpen;
      el.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
  }

  function boot() {
    try {
      // v6：先收下落地链接里的邀请码与分享人昵称，并清掉地址栏参数（刷新不重复触发）
      captureInviteFromUrl();
      buildCityOptions();
      buildFamFormOptions();     // v11：关系下拉与城市下拉（与建档屏共用同一份城市数据）
      refreshHome();
      bind();
      // v6：公开接口问一次「是谁分享的」；拿不到就用链接里的 n 参数兜底
      resolveInvitePreview();
      // 首次进入先取游客令牌（失败也不阻塞页面渲染）
      ensureToken(false).then(function () {
        // v12：问一次账号是否已设密码 → 决定右上角显示「登录 / 注册」还是手机号掩码
        loadAuthStatus();
        // v11：静默取一次家庭档案，只为让首页入口显示「家庭健康档案（n）」
        prefetchFamilyEntry();
        // v6：已建档但尚未绑定推荐人时（例如先建档、后点链接），进入站点即尝试一次
        if (state.profileCompleted) { maybeAutoBindInvite(); }
        // v14：不论本机记不记得「已建档」，都问一次今日节律——
        //   · 能算出指数 ⇒ 这个账号确实建过档（即使 profile_completed 字段缺失也能兜住，
        //     登录到有档案的老账号时首页一定会显示指数卡）
        //   · 未建档会返回 422（产品正确拒绝）⇒ 静默忽略，指数卡保持隐藏，首屏仍由「开始建档」引导
        return apiFetch('/rhythm/daily', {
          query: { target_date: ymd() },
          headers: { 'X-Target-Date': ymd() }
        }).then(function (env) {
          state.dailyEnv = env;
          state.daily = env.data || {};
          if (!state.profileCompleted && hasIndex(state.daily.index)) {
            state.profileCompleted = true;
            safeSet(K_PROFILE, '1');
            refreshHome();
          }
          renderHomeDaily();     // v14：预取到手即把首页指数填上，不必先进节律屏
        }, function () { /* 未建档/暂不可用都不影响首屏，进入节律屏时会再次读取并提示 */ });
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
