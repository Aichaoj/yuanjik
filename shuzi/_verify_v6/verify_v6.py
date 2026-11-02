# -*- coding: utf-8 -*-
"""
AI数显 · 元健康 —— 前端 v6「邀请链接 + 自动推荐绑定 + 昵称」验证脚本（Playwright）

对应变更单 2026-10-08《邀请链接与自动推荐绑定》验收标准 §五 第 6–9 条，
以及师父追加指令（昵称可改 / 分享带昵称 / 落地页告诉新用户是谁分享的）。

★ 全部接口用 page.add_init_script 覆盖 window.fetch 做内存 stub：
  不写任何文件到 D:\\shuzi\\server，也不依赖真实后端。
★ 被测页面由本机静态服务提供（python -m http.server --directory D:\\shuzi\\web），
  stub 只拦截 JS 发起的 fetch，静态资源仍走真实 HTTP。
★ 跨导航计数写在 sessionStorage['stub.calls']，因此 reload / 二次导航后仍可统计。

输出：D:\\shuzi\\web\\_shots_v6\\*.png + report.json + 控制台断言报告
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

WEB = r'D:\Deepseek智能体\AI元健康\shuzi\web'
OUT = r'D:\Deepseek智能体\AI元健康\shuzi\web\_shots_v6'
PORT = 15311
BASE = 'http://127.0.0.1:%d/' % PORT
LOG = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\http_server.log'
REPORT = os.path.join(OUT, 'report.json')

CODE = 'K7QM2X9P'                       # 8 位邀请码
INVITE_URL = 'https://shuzi.yuanjk.cn/?invite=' + CODE
VIEWPORTS = [('430x932', 430, 932), ('1440x900', 1440, 900)]

TPL6 = [
    {'template_id': 's1', 'text': '今天也照顾好自己'},
    {'template_id': 's2', 'text': '记得喝口水，歇一会儿'},
    {'template_id': 's3', 'text': '早点休息，明天见'},
    {'template_id': 's4', 'text': '你今天已经很棒了'},
    {'template_id': 's5', 'text': '把好习惯一起坚持下去'},
    {'template_id': 's6', 'text': '慢慢来，节奏最重要'},
]


def share_text(nick):
    return ('我是%s，邀请你一起看每日健康指数：%s&n=%s'
            % (nick, INVITE_URL, quote(nick)))


def cfg(**kw):
    d = dict(
        previewDown=False, previewValid=True, inviterNickname='小明',
        myNickname='用户4821', code=CODE, inviteUrl=INVITE_URL,
        shareText=None, referredBy=None, invalidCode=False,
        referralDown=False, inviteCodeDown=False, nicknameFail=False, bindError=False,
        friends=[], profileCompleted=False, pending=None, pendingName=None,
        bindLog=None,
    )
    d.update(kw)
    if d['shareText'] is None:
        d['shareText'] = share_text(d['myNickname'])
    return d


# ── 内存 stub：覆盖 window.fetch；跨导航调用记录写在 sessionStorage ──────
STUB = r"""
(function () {
  var CFG = __CFG__;
  window.__cfg = CFG;
  window.__copied = null;

  function logCall(entry) {
    try {
      var arr = JSON.parse(sessionStorage.getItem('stub.calls') || '[]');
      arr.push(entry);
      sessionStorage.setItem('stub.calls', JSON.stringify(arr.slice(-200)));
    } catch (e) { /* 忽略 */ }
  }

  // 服务端可变状态跨导航持久化（reload 后仍记得「已绑定 / 已加好友 / 已改名」）
  var PERSIST = ['myNickname', 'shareText', 'referredBy', 'friends', 'bindError'];
  try {
    var saved = JSON.parse(sessionStorage.getItem('stub.cfg') || 'null');
    if (saved) {
      for (var pk in saved) {
        if (Object.prototype.hasOwnProperty.call(saved, pk)) { CFG[pk] = saved[pk]; }
      }
    }
  } catch (e) { /* 忽略 */ }
  function saveCfg() {
    try {
      var o = {};
      PERSIST.forEach(function (k) { o[k] = CFG[k]; });
      sessionStorage.setItem('stub.cfg', JSON.stringify(o));
    } catch (e) { /* 忽略 */ }
  }
  window.__saveCfg = saveCfg;
  function env(data, status) {
    return new Response(JSON.stringify({code: 0, message: 'ok', data: data,
                                        trace_id: 'stub-v6'}),
      {status: status || 200, headers: {'Content-Type': 'application/json'}});
  }
  function errEnv(code, msg, status) {
    return new Response(JSON.stringify({code: code, message: msg, data: null,
                                        trace_id: 'stub-v6-err'}),
      {status: status || 200, headers: {'Content-Type': 'application/json'}});
  }

  // 预置本机状态（模拟「先建档、后点链接」「已绑定」等历史）
  try {
    if (CFG.profileCompleted) { localStorage.setItem('yh.profile_completed', '1'); }
    if (CFG.pending) { localStorage.setItem('yh.pending_invite', CFG.pending); }
    if (CFG.pendingName) { localStorage.setItem('yh.pending_invite_name', CFG.pendingName); }
    if (CFG.bindLog) { localStorage.setItem('yh.invite_bind_log', JSON.stringify(CFG.bindLog)); }
  } catch (e) { /* 忽略 */ }

  // 记录真实复制内容（仍调用真实剪贴板 API）
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      var realWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function (t) {
        window.__copied = String(t);
        return realWrite(t);
      };
    }
  } catch (e) { /* 忽略 */ }

  window.fetch = function (url, init) {
    var u = String(url || '');
    var method = ((init && init.method) || 'GET').toUpperCase();
    var body = null;
    try { body = (init && init.body) ? JSON.parse(init.body) : null; } catch (e) { body = null; }
    logCall({url: u, method: method, body: body, at: Date.now()});

    if (u.indexOf('/auth/guest') >= 0 || u.indexOf('/auth/login/code') >= 0) {
      return Promise.resolve(env({access_token: 'stub-token', refresh_token: 'stub-refresh'}));
    }
    // 公开接口：谁分享的
    if (u.indexOf('/invite/preview') >= 0) {
      if (CFG.previewDown) { return Promise.resolve(errEnv(50000, '服务暂时不可用，请稍后重试。', 500)); }
      if (CFG.previewValid === false) { return Promise.resolve(env({valid: false, nickname: ''})); }
      return Promise.resolve(env({valid: true, nickname: CFG.inviterNickname}));
    }
    // 邀请链接 / 分享文案 / 我的推荐人
    if (u.indexOf('/me/referral') >= 0) {
      if (CFG.referralDown) { return Promise.resolve(errEnv(50000, '服务暂时不可用，请稍后重试。', 500)); }
      return Promise.resolve(env({invite_code: CFG.code, invite_url: CFG.inviteUrl,
                                  share_text: CFG.shareText, nickname: CFG.myNickname,
                                  referred_by: CFG.referredBy}));
    }
    // 修改昵称
    if (u.indexOf('/me/nickname') >= 0) {
      if (CFG.nicknameFail) {
        return Promise.resolve(errEnv(30001, '昵称包含不允许的内容，请修改后重试。', 400));
      }
      CFG.myNickname = String((body && body.nickname) || '');
      CFG.shareText = '我是' + CFG.myNickname + '，邀请你一起看每日健康指数：' +
                      CFG.inviteUrl + '&n=' + encodeURIComponent(CFG.myNickname);
      saveCfg();
      return Promise.resolve(env({nickname: CFG.myNickname}));
    }
    if (u.indexOf('/me/invite_code') >= 0) {
      if (CFG.inviteCodeDown) { return Promise.resolve(errEnv(50000, '服务暂时不可用，请稍后重试。', 500)); }
      return Promise.resolve(env({invite_code: CFG.code, nickname: CFG.myNickname}));
    }
    // 邀请绑定（自动加好友 + 一次性推荐关系）
    if (u.indexOf('/friends/invite') >= 0) {
      if (CFG.invalidCode) {
        return Promise.resolve(errEnv(30004, '邀请码无效，请核对后重试。', 400));
      }
      if (CFG.bindError) {
        return Promise.resolve(errEnv(50000, '服务暂时不可用，请稍后重试。', 500));
      }
      CFG.referredBy = {nickname: CFG.inviterNickname, bound_at: '2026-10-08T09:00:00Z'};
      CFG.friends = CFG.friends.concat([{friend_id: 'F-A', nickname: CFG.inviterNickname,
                                         status: 'accepted', share_index: false,
                                         share_streak: false, in_ranking: false,
                                         score: null, streak_days: null,
                                         last_active: '2026-10-08T09:00:00Z'}]);
      saveCfg();
      return Promise.resolve(env({status: 'accepted', auto_accept: true,
                                  referred_by: CFG.referredBy}));
    }
    if (u.indexOf('/friends/privacy') >= 0) {
      if (method === 'POST') { return Promise.resolve(env({ok: true})); }
      return Promise.resolve(errEnv(40004, '接口不存在', 404));
    }
    if (u.indexOf('/friends/cheer/templates') >= 0) {
      return Promise.resolve(env({templates: __TPL6__, daily_limit: 3, remaining: 3}));
    }
    if (u.indexOf('/friends/cheer') >= 0) {
      return Promise.resolve(env({ok: true, remaining: 2, daily_limit: 3}));
    }
    if (u.indexOf('/friends/feed') >= 0) {
      return Promise.resolve(env({items: [], next_cursor: null, has_more: false}));
    }
    if (u.indexOf('/friends/ranking') >= 0) {
      return Promise.resolve(env({ranking: CFG.friends.concat([
        {friend_id: 'me', nickname: CFG.myNickname, is_me: true, score: 82,
         share_index: true, in_ranking: true, streak_days: 6}])}));
    }
    if (u.indexOf('/friends') >= 0 && method === 'GET') {
      return Promise.resolve(env({friends: CFG.friends, me: {score: 82, streak_days: 6}}));
    }
    if (u.indexOf('/profile/birth') >= 0) {
      CFG.profileCompleted = true;
      return Promise.resolve(env({ok: true, baseline_reset: false}));
    }
    if (u.indexOf('/rhythm/daily') >= 0) {
      return Promise.resolve(env({
        date: '2026-10-08', baseline_established: true, observation_count: 9,
        index: {score: 82, band_code: 'B', band: '良',
                basis: '按出生时空与当日时相推算·仅为生活方式参考'},
        disclaimer: '本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。',
        referral: '建议咨询执业医师或前往正规医疗机构。', ai_generated: true
      }));
    }
    if (u.indexOf('/rhythm/history') >= 0) {
      return Promise.resolve(env({items: [], next_cursor: null, has_more: false}));
    }
    return Promise.resolve(env({}));
  };
})();
"""

FORBIDDEN = ['生命先知', '先知日历', '八息象数', '八息基因', 'ZYDGENE', '中易道',
             '九元情绪', '华医道', '老祖太极', '加密', '抗量子', '密钥']

RESULTS = []
CONSOLE_ERRORS = []       # [(scen, text)]
PAGE_ERRORS = []          # [(scen, text)]


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('  [PASS] ' if ok else '  [FAIL] ') + name +
          (('  -> ' + str(detail)[:220]) if detail else ''))
    return bool(ok)


def build_stub(c):
    return STUB.replace('__CFG__', json.dumps(c, ensure_ascii=False)) \
               .replace('__TPL6__', json.dumps(TPL6, ensure_ascii=False))


def port_free(port):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_server():
    f = open(LOG, 'w', encoding='utf-8')
    p = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT),
                          '--bind', '127.0.0.1', '--directory', WEB],
                         stdout=f, stderr=subprocess.STDOUT)
    for _ in range(60):
        if not port_free(PORT):
            return p, f
        time.sleep(0.25)
    return p, f


# ── 页面辅助 ─────────────────────────────────────────────────────────
def new_page(ctx, scen, w, h):
    page = ctx.new_page()
    page.set_viewport_size({'width': w, 'height': h})
    page.on('console', lambda m: CONSOLE_ERRORS.append((scen, m.text))
            if m.type == 'error' else None)
    page.on('pageerror', lambda e: PAGE_ERRORS.append((scen, str(e))))
    return page


def calls(page):
    return page.evaluate("() => JSON.parse(sessionStorage.getItem('stub.calls') || '[]')")


def count_calls(page, needle, method=None):
    n = 0
    for c in calls(page):
        if needle in c['url'] and (method is None or c['method'] == method):
            n += 1
    return n


def bind_calls(page):
    return [c for c in calls(page) if '/friends/invite' in c['url'] and c['method'] == 'POST']


def wait_for_call(page, needle, method=None, timeout=8000):
    try:
        page.wait_for_function(
            """([needle, method]) => {
                 const arr = JSON.parse(sessionStorage.getItem('stub.calls') || '[]');
                 return arr.some(c => c.url.indexOf(needle) >= 0 && (!method || c.method === method));
               }""",
            arg=[needle, method], timeout=timeout)
        return True
    except Exception:
        return False


def settle(page, ms=800):
    page.wait_for_timeout(ms)


def open_home(page, url=None):
    page.goto(url or BASE, wait_until='load')
    page.wait_for_selector('#screen-home:not([hidden])')
    page.wait_for_timeout(400)


def enter_friends(page):
    if page.evaluate("() => document.querySelector('#screen-friends').hidden"):
        page.click('#btnHomeFriends')
    page.wait_for_selector('#screen-friends:not([hidden])')
    page.wait_for_timeout(600)


def do_profile(page):
    page.click('#btnStart')
    page.wait_for_selector('#screen-profile:not([hidden])')
    page.fill('#inBirthDate', '1990-05-20')
    page.select_option('#inCity', '北京')
    page.check('#inConsent')
    page.click('#btnSubmitProfile')
    page.wait_for_selector('#screen-rhythm:not([hidden])', timeout=8000)


def index_card_ok(page):
    """指数卡渲染成功：不是「正在读取…」，且能读到分档/分数文案"""
    try:
        page.wait_for_function(
            """() => {
                 const el = document.querySelector('#indexBody');
                 if (!el) return false;
                 const t = (el.innerText || '').trim();
                 return t.length > 8 && t.indexOf('正在读取') < 0;
               }""", timeout=8000)
        return True
    except Exception:
        return False


def no_hscroll(page):
    d = page.evaluate('() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})')
    return d['sw'] <= d['iw'] + 1, d


def tap_ok(page, sel):
    box = page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {w: r.width, h: r.height};
      }""", sel)
    return box, bool(box and box['h'] >= 44 and box['w'] >= 44)


def shot(page, tag, name, full=False):
    path = os.path.join(OUT, 'shot_%s_%s.png' % (tag, name))
    page.screenshot(path=path, full_page=full, animations='disabled')
    return os.path.basename(path)


def shot_el(page, tag, name, sel):
    path = os.path.join(OUT, 'shot_%s_%s.png' % (tag, name))
    try:
        page.locator(sel).first.screenshot(path=path, animations='disabled')
        return os.path.basename(path)
    except Exception as e:
        return 'ELEMENT_SHOT_FAILED: %s' % e


def toast_text(page):
    return page.evaluate("() => (document.querySelector('#toast').hidden ? '' : document.querySelector('#toast').innerText)")


def wait_toast_contains(page, needle, timeout=8000):
    try:
        page.wait_for_function(
            """(needle) => {
                 const el = document.querySelector('#toast');
                 return el && !el.hidden && (el.innerText || '').indexOf(needle) >= 0;
               }""", arg=needle, timeout=timeout)
        return True
    except Exception:
        return False


# ── 场景 ────────────────────────────────────────────────────────────
def s1_copy(browser, tag, w, h):
    """① 复制内容含 ?invite= 与 8 位码；按钮文案「复制邀请链接」；优先用服务端 share_text"""
    print('\n== S1 复制邀请链接（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg()))
    page = new_page(ctx, 'S1', w, h)
    open_home(page)
    enter_friends(page)
    page.wait_for_function("() => (document.querySelector('#inviteSharePreview').innerText||'').indexOf('?invite=') >= 0")

    btn_text = page.inner_text('#btnCopyInvite').strip()
    check('[S1/%s] 按钮文案为「复制邀请链接」' % tag, btn_text == '复制邀请链接', btn_text)

    link = page.inner_text('#inviteLink')
    check('[S1/%s] 只读邀请链接含 ?invite= 与 8 位码' % tag,
          '?invite=' in link and CODE in link, link)
    check('[S1/%s] 链接带分享人昵称参数 n=' % tag, '&n=' in link, link)

    page.click('#btnCopyInvite')
    page.wait_for_timeout(500)
    copied = page.evaluate('() => window.__copied')
    check('[S1/%s] 复制成功（走剪贴板 API）' % tag, bool(copied), copied)
    check('[S1/%s] 复制内容含 ?invite= 与 8 位码' % tag,
          bool(copied) and '?invite=' in copied and CODE in copied, copied)
    check('[S1/%s] 复制内容优先用服务端 share_text（含昵称）' % tag,
          bool(copied) and copied.startswith('我是') and '用户4821' in copied, copied)

    tip = toast_text(page)
    check('[S1/%s] 复制成功 toast 写清用途' % tag,
          ('好友' in tip) and ('邀请链接已复制' in tip), tip)

    ok, d = no_hscroll(page)
    check('[S1/%s] 无横向滚动' % tag, ok, d)
    for sel, label in [('#btnCopyInvite', '复制邀请链接'),
                       ('#btnSaveNickname', '保存昵称'),
                       ('#btnAddFriend', '添加好友')]:
        box, ok2 = tap_ok(page, sel)
        check('[S1/%s] %s 点击区 ≥44px' % (tag, label), ok2, box)

    shot(page, tag, 'friends_top')
    shot_el(page, tag, 'invite_card', '#inviteCard')
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S1'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S1'])
    check('[S1/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S1'])
    check('[S1/%s] 无未捕获异常' % tag, n_pe == 0,
          [x[1] for x in PAGE_ERRORS if x[0] == 'S1'])
    ctx.close()


def s2_bind(browser, tag, w, h):
    """②③ 带 ?invite= 打开 → 建档后恰好一次 friends/invite{auto_accept:true}；
       ③ 重复刷新/再次打开不重复调用；落地页显示是谁分享的"""
    print('\n== S2 落地自动绑定 + 幂等（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(inviterNickname='小明')))
    page = new_page(ctx, 'S2', w, h)
    open_home(page, BASE + '?invite=' + CODE)
    settle(page, 900)

    check('[S2/%s] 地址栏参数已清掉（invite= 不再出现）' % tag,
          'invite=' not in page.url, page.url)
    hint = page.inner_text('#homeInviteHint')
    check('[S2/%s] 首屏提示条显示「<昵称> 邀请你一起看每日健康指数」' % tag,
          '小明' in hint and '邀请你一起看每日健康指数' in hint, hint)
    check('[S2/%s] 落地页调用了公开 preview 接口' % tag,
          count_calls(page, '/invite/preview') == 1, calls(page))
    shot(page, tag, 'home_invite_hint')

    do_profile(page)
    check('[S2/%s] 建档后指数卡正常渲染' % tag, index_card_ok(page), page.inner_text('#indexBody')[:80])
    got = wait_for_call(page, '/friends/invite', 'POST')
    check('[S2/%s] 触发了自动绑定' % tag, got, bind_calls(page))
    check('[S2/%s] 绑定 toast 含邀请人昵称' % tag, wait_toast_contains(page, '小明'), toast_text(page))
    shot(page, tag, 'rhythm_bind_toast')

    settle(page, 700)
    bc = bind_calls(page)
    check('[S2/%s] 恰好调用一次 friends/invite' % tag, len(bc) == 1, bc)
    body = bc[0]['body'] if bc else None
    check('[S2/%s] 请求体为 {invite_code, auto_accept:true}' % tag,
          bool(body) and body.get('invite_code') == CODE and body.get('auto_accept') is True, body)

    state = page.evaluate("""() => ({
        pending: localStorage.getItem('yh.pending_invite'),
        log: localStorage.getItem('yh.invite_bind_log'),
        url: location.href
      })""")
    check('[S2/%s] 成功后清掉 pending_invite' % tag, state['pending'] is None, state)
    check('[S2/%s] 成功后留下绑定留痕 ok=true' % tag,
          bool(state['log']) and '"ok":true' in state['log'], state['log'])

    # ③ 刷新 + 再次带参打开：都不再重复调用
    page.reload(wait_until='load')
    settle(page, 1000)
    check('[S2/%s] 刷新后不重复调用' % tag, len(bind_calls(page)) == 1, bind_calls(page))
    page.goto(BASE + '?invite=' + CODE, wait_until='load')
    settle(page, 1000)
    check('[S2/%s] 再次带邀请码打开仍不重复调用' % tag,
          len(bind_calls(page)) == 1, bind_calls(page))

    enter_friends(page)
    try:
        page.wait_for_function(
            "() => (document.querySelector('#myReferrer').innerText||'').trim() !== '暂无'",
            timeout=5000)
    except Exception:
        pass
    ref = page.inner_text('#myReferrer')
    check('[S2/%s] 好友圈显示「我的推荐人：小明」' % tag, ref.strip() == '小明', ref)
    friends_txt = page.inner_text('#cheerBody')
    check('[S2/%s] 好友列表含邀请人（自动成为好友）' % tag, '小明' in friends_txt, friends_txt[:120])
    check('[S2/%s] 三隐私开关仍默认全关' % tag,
          page.eval_on_selector_all('#privacyBody .switch-row',
                                    "els => els.map(e => e.getAttribute('aria-checked'))") == ['false'] * 3,
          page.eval_on_selector_all('#privacyBody .switch-row',
                                    "els => els.map(e => e.getAttribute('aria-checked'))"))
    ok, d = no_hscroll(page)
    check('[S2/%s] 无横向滚动' % tag, ok, d)
    shot(page, tag, 'friends_after_bind')
    shot_el(page, tag, 'invite_card_after_bind', '#inviteCard')

    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S2'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S2'])
    check('[S2/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S2'])
    check('[S2/%s] 无未捕获异常' % tag, n_pe == 0,
          [x[1] for x in PAGE_ERRORS if x[0] == 'S2'])
    ctx.close()


def s3_invalid(browser, tag):
    """④ 码无效 → 建档与指数卡仍正常、无白屏、轻提示"""
    print('\n== S3 邀请码无效不阻塞建档（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(invalidCode=True)))
    page = new_page(ctx, 'S3', 430, 932)
    open_home(page, BASE + '?invite=' + CODE)
    settle(page, 600)
    do_profile(page)
    check('[S3] 码无效时建档仍成功（进入今日节律屏）',
          not page.evaluate("() => document.querySelector('#screen-rhythm').hidden"), page.url)
    check('[S3/%s] 码无效时指数卡仍正常渲染' % tag, index_card_ok(page),
          page.inner_text('#indexBody')[:80])
    got = wait_for_call(page, '/friends/invite', 'POST')
    check('[S3/%s] 仍尝试了一次绑定' % tag, got, bind_calls(page))
    check('[S3/%s] 轻提示「邀请码无效」' % tag, wait_toast_contains(page, '邀请码无效'), toast_text(page))
    check('[S3/%s] 无效码不再保留在待绑定状态' % tag,
          page.evaluate("() => localStorage.getItem('yh.pending_invite')") is None)
    check('[S3/%s] 失败留痕 ok=false（幂等）' % tag,
          '"ok":false' in (page.evaluate("() => localStorage.getItem('yh.invite_bind_log')") or ''))
    check('[S3/%s] 无白屏（页面有可读文案）' % tag,
          len((page.inner_text('#screen-rhythm') or '').strip()) > 40,
          (page.inner_text('#screen-rhythm') or '')[:80])
    ok, d = no_hscroll(page)
    check('[S3/%s] 无横向滚动' % tag, ok, d)
    shot(page, tag, 'rhythm_invalid_code')
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S3'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S3'])
    check('[S3/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S3'])
    check('[S3/%s] 无未捕获异常' % tag, n_pe == 0, [x[1] for x in PAGE_ERRORS if x[0] == 'S3'])
    ctx.close()


def s4_already(browser, tag):
    """⑤ 已有 referred_by → 不再提交绑定"""
    print('\n== S4 已有推荐人不再提交（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(
        profileCompleted=True, pending=CODE, pendingName='老王',
        referredBy={'nickname': '老王', 'bound_at': '2026-10-01T08:00:00Z'})))
    page = new_page(ctx, 'S4', 430, 932)
    open_home(page, BASE + '?invite=' + CODE)
    settle(page, 1200)

    check('[S4/%s] 已有推荐人时未调用 friends/invite' % tag,
          len(bind_calls(page)) == 0, bind_calls(page))
    check('[S4/%s] 已绑定则清掉待绑定状态' % tag,
          page.evaluate("() => localStorage.getItem('yh.pending_invite')") is None)
    enter_friends(page)
    try:
        page.wait_for_function(
            "() => (document.querySelector('#myReferrer').innerText||'').trim() !== '暂无'",
            timeout=5000)
    except Exception:
        pass
    check('[S4/%s] 我的推荐人显示老王' % tag,
          page.inner_text('#myReferrer').strip() == '老王', page.inner_text('#myReferrer'))
    shot_el(page, tag, 'invite_card_referrer', '#inviteCard')
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S4'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S4'])
    check('[S4/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S4'])
    check('[S4/%s] 无未捕获异常' % tag, n_pe == 0, [x[1] for x in PAGE_ERRORS if x[0] == 'S4'])
    ctx.close()


def s5_preview_down(browser, tag, w, h):
    """preview 挂掉 → 用 URL 的 n 参数兜底显示分享人昵称"""
    print('\n== S5 preview 不可用时用 n 参数兜底（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(previewDown=True)))
    page = new_page(ctx, 'S5', w, h)
    open_home(page, BASE + '?invite=' + CODE + '&n=' + quote('李四'))
    settle(page, 900)
    hint = page.inner_text('#homeInviteHint')
    check('[S5/%s] preview 挂掉时用 n 参数显示「李四 邀请你…」' % tag,
          '李四' in hint and '邀请你一起看每日健康指数' in hint, hint)
    check('[S5/%s] preview 确实被调用过（才谈得上兜底）' % tag,
          count_calls(page, '/invite/preview') == 1, calls(page)[:4])
    shot(page, tag, 'home_invite_hint_n_fallback')
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S5'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S5'])
    check('[S5/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S5'])
    check('[S5/%s] 无未捕获异常' % tag, n_pe == 0, [x[1] for x in PAGE_ERRORS if x[0] == 'S5'])
    ctx.close()


def s6_preview_invalid_neutral(browser):
    """preview 说无效 + 没有 n 参数 → 中性文案"""
    print('\n== S6 preview 判无效且无 n 参数 → 中性文案 ==')
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(previewValid=False)))
    page = new_page(ctx, 'S6', 430, 932)
    open_home(page, BASE + '?invite=' + CODE)
    settle(page, 900)
    hint = page.inner_text('#homeInviteHint')
    check('[S6] 无昵称时显示中性文案' , '你的朋友邀请你一起看每日健康指数' in hint, hint)
    check('[S6] 中性文案不含任何虚构昵称', '小明' not in hint and '李四' not in hint, hint)
    ctx.close()


def s7_rename(browser, tag, w, h):
    """昵称可改：改名后分享文案 / 我的昵称 / 排行榜自己那条立刻变化；失败有可读提示"""
    print('\n== S7 修改昵称（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg()))
    page = new_page(ctx, 'S7', w, h)
    open_home(page)
    enter_friends(page)
    page.wait_for_function("() => (document.querySelector('#inviteSharePreview').innerText||'').indexOf('?invite=') >= 0")

    # 打开排行开关，让「自己那条」出现在榜单里，便于验证改名即时生效
    page.click('#privacyBody .switch-row[data-priv="in_ranking"]')
    page.wait_for_function(
        "() => document.querySelector('#privacyBody .switch-row[data-priv=\"in_ranking\"]').getAttribute('aria-checked') === 'true'")
    page.wait_for_timeout(400)
    before_share = page.inner_text('#inviteSharePreview')
    before_rank = page.inner_text('#rankList') if page.locator('#rankList').count() else ''
    check('[S7/%s] 改名前的分享文案含旧昵称' % tag, '用户4821' in before_share, before_share)
    check('[S7/%s] 改名前的排行榜自己那条是旧昵称' % tag, '用户4821' in before_rank, before_rank)

    check('[S7/%s] 昵称输入框已回填当前昵称' % tag,
          page.input_value('#inNickname') == '用户4821', page.input_value('#inNickname'))

    # 客户端校验：1 个字 → 可读提示且不发请求
    page.fill('#inNickname', '甲')
    before_nick_calls = count_calls(page, '/me/nickname', 'POST')
    page.click('#btnSaveNickname')
    page.wait_for_timeout(400)
    err_txt = page.inner_text('#nicknameErr')
    check('[S7/%s] 昵称过短给出可读提示' % tag, '2–12' in err_txt, err_txt)
    check('[S7/%s] 过短时不发请求' % tag,
          count_calls(page, '/me/nickname', 'POST') == before_nick_calls)

    # 正常改名
    page.fill('#inNickname', '健康小明')
    page.click('#btnSaveNickname')
    got = wait_for_call(page, '/me/nickname', 'POST')
    check('[S7/%s] 调用了 POST /me/nickname' % tag, got,
          [c for c in calls(page) if '/me/nickname' in c['url']])
    page.wait_for_timeout(600)
    nc = [c for c in calls(page) if '/me/nickname' in c['url'] and c['method'] == 'POST']
    check('[S7/%s] 请求体为 {nickname}（2–12 字）' % tag,
          bool(nc) and nc[-1]['body'] == {'nickname': '健康小明'}, nc[-1]['body'] if nc else None)

    my_nick = page.inner_text('#myNickname')
    share = page.inner_text('#inviteSharePreview')
    rank = page.inner_text('#rankList') if page.locator('#rankList').count() else ''
    toast = toast_text(page)
    check('[S7/%s] 我的昵称立即更新' % tag, '健康小明' in my_nick, my_nick)
    check('[S7/%s] 分享文案昵称立即变化（含新昵称、不含旧昵称）' % tag,
          '健康小明' in share and '用户4821' not in share, share)
    check('[S7/%s] 分享文案仍含 ?invite= 与 8 位码' % tag,
          '?invite=' in share and CODE in share, share)
    check('[S7/%s] 排行榜自己那条立即更新' % tag,
          '健康小明' in rank and '用户4821' not in rank, rank[:200])
    check('[S7/%s] 改名成功 toast' % tag, '昵称已改为「健康小明」' in toast, toast)

    page.click('#btnCopyInvite')
    page.wait_for_timeout(400)
    copied = page.evaluate('() => window.__copied')
    check('[S7/%s] 改名后复制内容也带新昵称' % tag,
          bool(copied) and '健康小明' in copied and CODE in copied, copied)
    shot(page, tag, 'friends_rename_ok')
    shot_el(page, tag, 'invite_card_rename', '#inviteCard')

    # 服务端拒绝（敏感词）：显示可读提示
    page.evaluate('() => { window.__cfg.nicknameFail = true; }')
    page.fill('#inNickname', '测试昵称')
    page.click('#btnSaveNickname')
    page.wait_for_timeout(700)
    err_txt2 = page.inner_text('#nicknameErr')
    check('[S7/%s] 服务端拒绝时显示可读提示' % tag,
          '不允许的内容' in err_txt2, err_txt2)
    check('[S7/%s] 服务端拒绝后昵称未被改动' % tag,
          '健康小明' in page.inner_text('#myNickname'), page.inner_text('#myNickname'))

    ok, d = no_hscroll(page)
    check('[S7/%s] 无横向滚动' % tag, ok, d)
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S7'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S7'])
    check('[S7/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S7'])
    check('[S7/%s] 无未捕获异常' % tag, n_pe == 0, [x[1] for x in PAGE_ERRORS if x[0] == 'S7'])
    ctx.close()


def s9_retry_window(browser, tag):
    """接口临时失败：保留待绑定、24 小时内不重复提交、窗口过后可再试一次"""
    print('\n== S9 绑定接口临时失败的重试窗口（%s） ==' % tag)
    ctx = browser.new_context()
    ctx.add_init_script(build_stub(cfg(bindError=True)))
    page = new_page(ctx, 'S9', 430, 932)
    open_home(page, BASE + '?invite=' + CODE)
    settle(page, 600)
    do_profile(page)
    got = wait_for_call(page, '/friends/invite', 'POST')
    check('[S9/%s] 临时失败时仍提交了一次' % tag, got, bind_calls(page))
    settle(page, 700)
    check('[S9/%s] 临时失败保留 pending_invite（可再试）' % tag,
          page.evaluate("() => localStorage.getItem('yh.pending_invite')") == CODE,
          page.evaluate("() => localStorage.getItem('yh.pending_invite')"))
    check('[S9/%s] 失败留痕 ok=false' % tag,
          '"ok":false' in (page.evaluate("() => localStorage.getItem('yh.invite_bind_log')") or ''))
    check('[S9/%s] 轻提示提示稍后手工添加' % tag,
          wait_toast_contains(page, '暂时没能加上') or '暂时没能加上' in toast_text(page),
          toast_text(page))

    page.reload(wait_until='load')
    settle(page, 1000)
    check('[S9/%s] 24 小时内刷新不重复提交' % tag, len(bind_calls(page)) == 1, bind_calls(page))

    # 把留痕时间改到 25 小时前：窗口过后应再试一次
    page.evaluate("""() => {
        const log = JSON.parse(localStorage.getItem('yh.invite_bind_log'));
        log.at = Date.now() - 25 * 3600 * 1000;
        localStorage.setItem('yh.invite_bind_log', JSON.stringify(log));
        localStorage.setItem('yh.pending_invite', '%s');
      }""" % CODE)
    page.evaluate('() => { window.__cfg.bindError = false; window.__saveCfg(); }')
    page.reload(wait_until='load')
    settle(page, 1200)
    check('[S9/%s] 重试窗口过后可再提交一次' % tag, len(bind_calls(page)) == 2, bind_calls(page))
    check('[S9/%s] 第二次成功并清掉 pending' % tag,
          page.evaluate("() => localStorage.getItem('yh.pending_invite')") is None,
          page.evaluate("() => localStorage.getItem('yh.invite_bind_log')"))
    n_err = len([x for x in CONSOLE_ERRORS if x[0] == 'S9'])
    n_pe = len([x for x in PAGE_ERRORS if x[0] == 'S9'])
    check('[S9/%s] console 无 error' % tag, n_err == 0,
          [x[1] for x in CONSOLE_ERRORS if x[0] == 'S9'])
    check('[S9/%s] 无未捕获异常' % tag, n_pe == 0, [x[1] for x in PAGE_ERRORS if x[0] == 'S9'])
    ctx.close()


def s8_static():
    """静态自检：合规词、无外网引用、只改三个文件"""
    print('\n== S8 静态自检 ==')
    files = ['index.html', 'style.css', 'app.js']
    joined = {}
    for f in files:
        p = os.path.join(WEB, f)
        with open(p, 'r', encoding='utf-8') as fh:
            joined[f] = fh.read()
        print('  %-12s %d bytes' % (f, os.path.getsize(p)))
    all_txt = '\n'.join(joined.values())
    hit = [w for w in FORBIDDEN if w in all_txt]
    check('[S8] 三个文件不含违规词', not hit, hit)
    check('[S8] app.js 无外网引用（http:// / https:// 只出现在注释与文案里）',
          'src="http' not in all_txt and "src='http" not in all_txt and '@import url(http' not in all_txt)
    check('[S8] 新增功能使用的接口路径齐全',
          all(s in joined['app.js'] for s in
              ['/me/referral', '/invite/preview', '/me/nickname', 'auto_accept']))
    check('[S8] 复制按钮文案为「复制邀请链接」', '复制邀请链接' in joined['index.html'])
    check('[S8] 存在「我的推荐人」区', '我的推荐人' in joined['index.html'])
    check('[S8] 存在修改昵称入口', 'btnSaveNickname' in joined['index.html'] and 'inNickname' in joined['index.html'])
    check('[S8] 存在邀请落地提示条', 'homeInviteHint' in joined['index.html'])
    return {f: os.path.getsize(os.path.join(WEB, f)) for f in files}


def main():
    os.makedirs(OUT, exist_ok=True)
    srv, logf = start_server()
    file_sizes = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            file_sizes = s8_static()
            for tag, w, h in VIEWPORTS:
                s1_copy(browser, tag, w, h)
            for tag, w, h in VIEWPORTS:
                s2_bind(browser, tag, w, h)
            s3_invalid(browser, '430x932')
            s4_already(browser, '430x932')
            for tag, w, h in VIEWPORTS:
                s5_preview_down(browser, tag, w, h)
            s6_preview_invalid_neutral(browser)
            s9_retry_window(browser, '430x932')
            for tag, w, h in VIEWPORTS:
                s7_rename(browser, tag, w, h)
            browser.close()
    finally:
        srv.terminate()
        logf.close()

    passed = len([r for r in RESULTS if r['ok']])
    failed = len(RESULTS) - passed
    shots = sorted(f for f in os.listdir(OUT) if f.endswith('.png'))
    report = {
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'base_url': BASE,
        'web_dir': WEB,
        'file_bytes': file_sizes,
        'assertions_total': len(RESULTS),
        'assertions_passed': passed,
        'assertions_failed': failed,
        'console_errors': len(CONSOLE_ERRORS),
        'page_errors': len(PAGE_ERRORS),
        'console_error_detail': CONSOLE_ERRORS,
        'page_error_detail': PAGE_ERRORS,
        'screenshots': shots,
        'results': RESULTS,
    }
    with open(REPORT, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print('\n================= 汇总 =================')
    print('断言：%d 通过 / %d 失败（共 %d）' % (passed, failed, len(RESULTS)))
    print('console error：%d；未捕获异常：%d' % (len(CONSOLE_ERRORS), len(PAGE_ERRORS)))
    print('截图：%d 张 -> %s' % (len(shots), OUT))
    print('报告：%s' % REPORT)
    if failed:
        print('\n失败项：')
        for r in RESULTS:
            if not r['ok']:
                print('  - %s  %s' % (r['name'], r['detail']))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
