# -*- coding: utf-8 -*-
"""
AI 健康 · 元健康 —— 前端 v3「轻社交三件套」验证脚本（Playwright）

覆盖变更单 2026-10-08 §三 接口契约与可见性规则、§四 第 11 条前端验收、§二 合规红线。

★ 全部接口用 page.add_init_script 覆盖 window.fetch 做内存 stub：
  不写任何文件到 D:\\shuzi\\server，也不依赖真实后端。
★ 被测页面由本机静态服务提供（python -m http.server --directory D:\\shuzi\\web），
  stub 只拦截 JS 发起的 fetch，静态资源仍走真实 HTTP。

四种 stub 状态：
  empty          ① 全部为空的新用户
  public         ② 有好友且都公开（含待确认）
  private_friend ③ 对方未公开（payload 里带分数，界面必须显示「未公开」）
  error500       ④ 接口 500

输出：D:\\shuzi\\web\\_shots_v3\\*.png + report.json + 控制台断言报告
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import socket

from playwright.sync_api import sync_playwright

WEB = r'D:\Deepseek智能体\AI元健康\shuzi\web'
OUT = r'D:\Deepseek智能体\AI元健康\shuzi\web\_shots_v3'
PORT = 15243
BASE = 'http://127.0.0.1:%d/' % PORT
LOG = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\http_server.log'

# ── stub 数据 ────────────────────────────────────────────────────────
TPL6 = [
    {'template_id': 's1', 'text': '今天也照顾好自己'},
    {'template_id': 's2', 'text': '记得喝口水，歇一会儿'},
    {'template_id': 's3', 'text': '早点休息，明天见'},
    {'template_id': 's4', 'text': '你今天已经很棒了'},
    {'template_id': 's5', 'text': '一起把好习惯坚持下去'},
    {'template_id': 's6', 'text': '慢慢来，节奏最重要'},
]

FRIEND_XM = {  # 小明：三项全公开
    'friend_id': 'F1024', 'nickname': '小明', 'status': 'accepted',
    'share_index': True, 'share_streak': True, 'in_ranking': True,
    'score': 91, 'streak_days': 12, 'last_active': '2026-10-08T06:30:00Z',
}
FRIEND_XJ = {  # 小静：未公开
    'friend_id': 'F2048', 'nickname': '小静', 'status': 'accepted',
    'share_index': False, 'share_streak': False, 'in_ranking': True,
    'score': 88, 'streak_days': 5, 'last_active': '2026-10-08T05:00:00Z',
}
PENDING_IN = {  # 对方请求加我
    'friend_id': 'F3001', 'nickname': '阿真', 'status': 'pending',
    'share_index': True, 'share_streak': True, 'in_ranking': False,
    'score': None, 'streak_days': None, 'last_active': '2026-10-08T04:00:00Z',
}
PENDING_OUT = {  # 我发出的请求
    'friend_id': 'F3002', 'nickname': '小北', 'status': 'pending',
    'requested_by': 'me', 'share_index': False, 'share_streak': False,
    'in_ranking': False, 'score': None, 'streak_days': None,
    'last_active': '2026-10-08T03:00:00Z',
}

SCEN = {
    'empty': {
        'friends': [], 'me': None, 'templates': TPL6, 'remaining': 3,
        'feed': [], 'ranking': [],
    },
    'public': {
        'friends': [FRIEND_XM, PENDING_IN, PENDING_OUT],
        'me': {'score': 82, 'streak_days': 6},
        'templates': TPL6, 'remaining': 3,
        'feed': [
            {'kind': 'cheer', 'from_nickname': '小明', 'to_nickname': '我',
             'template_text': '早点休息，明天见', 'last_active': '2026-10-08T07:10:00Z'},
            dict(FRIEND_XM),
        ],
        'ranking': [FRIEND_XM,
                    {'friend_id': 'me', 'nickname': '我', 'is_me': True,
                     'score': 82, 'share_index': True, 'in_ranking': True}],
    },
    'private_friend': {
        'friends': [FRIEND_XJ],
        'me': {'score': 82, 'streak_days': 6},
        'templates': TPL6[:3], 'remaining': 3,     # 只给 3 条 → 前端应补齐到 6 条
        'feed': [dict(FRIEND_XJ)],
        'ranking': [FRIEND_XJ,
                    {'friend_id': 'me', 'nickname': '我', 'is_me': True,
                     'score': 82, 'share_index': True, 'in_ranking': True}],
    },
    'error500': {
        'friends': [], 'me': None, 'templates': [], 'remaining': 3,
        'feed': [], 'ranking': [],
    },
    # ⑤ 附加健壮性：只有社交接口挂掉，其余屏（今日指数）必须不受影响
    'social_down': {
        'friends': [], 'me': None, 'templates': TPL6, 'remaining': 3,
        'feed': [], 'ranking': [],
    },
}

STUB = r"""
(function () {
  var SCEN = __SCEN__;
  var D = SCEN.data;
  var calls = [];
  window.__calls = calls;
  var removed = {};
  var removedNames = {};
  var cheerLeft = D.remaining;   // 今日剩余加油次数

  function env(data, status) {
    return new Response(JSON.stringify({code: 0, message: 'ok', data: data,
                                        trace_id: 'stub-v3'}),
      {status: status || 200, headers: {'Content-Type': 'application/json'}});
  }
  function errEnv(code, msg, status) {
    return new Response(JSON.stringify({code: code, message: msg, data: null,
                                        trace_id: 'stub-v3-err'}),
      {status: status || 200, headers: {'Content-Type': 'application/json'}});
  }
  function liveFriends() {
    return D.friends.filter(function (f) { return !removed[f.friend_id]; });
  }
  function liveFeed() {
    // 契约 §四-9：解除好友后 feed 也不再出现对方（含对方的加油记录）
    return D.feed.filter(function (it) {
      if (it.friend_id && removed[it.friend_id]) return false;
      if (it.from_nickname && removedNames[it.from_nickname]) return false;
      if (it.to_nickname && removedNames[it.to_nickname]) return false;
      if (it.nickname && removedNames[it.nickname]) return false;
      return true;
    });
  }
  function liveRanking() {
    return D.ranking.filter(function (it) {
      return !(it.friend_id && removed[it.friend_id]);
    });
  }

  window.fetch = function (url, init) {
    var u = String(url || '');
    var method = ((init && init.method) || 'GET').toUpperCase();
    var body = null;
    try { body = (init && init.body) ? JSON.parse(init.body) : null; } catch (e) { body = null; }
    calls.push({url: u, method: method, body: body});

    if (u.indexOf('/auth/guest') >= 0) {
      return Promise.resolve(env({access_token: 'stub-token', refresh_token: 'stub-refresh'}));
    }
    if (SCEN.name === 'error500') {
      return Promise.resolve(errEnv(50000, '服务暂时不可用，请稍后重试。', 500));
    }
    // ⑤ 只让社交接口失败：验证「好友圈挂了不影响其它屏」
    if (SCEN.name === 'social_down' &&
        (u.indexOf('/friends') >= 0 || u.indexOf('/me/invite_code') >= 0)) {
      return Promise.resolve(errEnv(50000, '社交服务暂时不可用，请稍后重试。', 500));
    }
    // 契约外可选接口：本 stub 故意返回 404，验证前端退回本机默认（全关）
    if (u.indexOf('/friends/privacy') >= 0) {
      if (method === 'POST') { return Promise.resolve(env({ok: true})); }
      return Promise.resolve(errEnv(40004, '接口不存在', 404));
    }
    if (u.indexOf('/me/invite_code') >= 0) {
      return Promise.resolve(env({invite_code: 'K7QM2X9P', nickname: '用户4821'}));
    }
    if (u.indexOf('/friends/cheer/templates') >= 0) {
      return Promise.resolve(env({templates: D.templates, daily_limit: 3, remaining: cheerLeft}));
    }
    if (u.indexOf('/friends/cheer') >= 0) {
      if (cheerLeft <= 0) {
        return Promise.resolve(errEnv(40000, '今日加油次数已用完。', 429));
      }
      cheerLeft = cheerLeft - 1;
      D.feed = [{kind: 'cheer', from_me: true, to_nickname: '小明',
                 template_text: (body && body.template_id) || '', last_active: '2026-10-08T08:00:00Z'}]
               .concat(D.feed);
      // 与真实后端同形：只给 sent_today / daily_limit，剩余次数由前端推算
      return Promise.resolve(env({ok: true, cheer_id: 1, friend_id: 'F1024',
                                  template_id: body && body.template_id,
                                  sent_today: 3 - cheerLeft, daily_limit: 3}));
    }
    if (u.indexOf('/friends/invite') >= 0) {
      D.friends = D.friends.concat([{friend_id: 'F9001', nickname: '新朋友', status: 'pending',
                                     requested_by: 'me', share_index: false,
                                     share_streak: false, in_ranking: false}]);
      return Promise.resolve(env({status: 'pending'}));
    }
    if (u.indexOf('/friends/accept') >= 0 || u.indexOf('/friends/reject') >= 0) {
      return Promise.resolve(env({ok: true}));
    }
    if (u.indexOf('/friends/feed') >= 0) {
      return Promise.resolve(env({items: liveFeed(), next_cursor: null, has_more: false}));
    }
    if (u.indexOf('/friends/ranking') >= 0) {
      return Promise.resolve(env({ranking: liveRanking()}));
    }
    if (method === 'DELETE' && u.indexOf('/friends/') >= 0) {
      var fid = decodeURIComponent(u.split('/friends/')[1] || '');
      removed[fid] = true;
      D.friends.forEach(function (f) {
        if (f.friend_id === fid) { removedNames[f.nickname] = true; }
      });
      return Promise.resolve(env({ok: true}));
    }
    if (u.indexOf('/friends') >= 0 && method === 'GET') {
      return Promise.resolve(env({friends: liveFriends(), me: D.me}));
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
             '九元情绪', '华医道', '老祖太极', '加密', '抗量子', '密钥',
             '诊断', '确诊', '治疗', '治愈', '疗效', '疾病', '病历',
             '血压', '身高', '体重']

RESULTS = []
CONSOLE_TOTAL = 0
PAGEERR_TOTAL = 0


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('  [PASS] ' if ok else '  [FAIL] ') + name +
          (('  -> ' + str(detail)[:200]) if detail else ''))


def build_stub(name):
    return STUB.replace('__SCEN__', json.dumps({'name': name, 'data': SCEN[name]},
                                               ensure_ascii=False))


def free_port(port):
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
        if not free_port(PORT):
            return p, f
        time.sleep(0.25)
    return p, f


def enter_friends(page):
    page.goto(BASE, wait_until='load')
    page.wait_for_selector('#screen-home:not([hidden])')
    page.click('#btnHomeFriends')
    page.wait_for_selector('#screen-friends:not([hidden])')
    page.wait_for_timeout(500)
    try:
        page.wait_for_selector('#toast', state='hidden', timeout=3000)
    except Exception:
        pass


def text_sans_compliance(page):
    """好友圈可见文字，剔除合规声明区（免责声明是法定固定表述）"""
    return page.evaluate("""() => {
      const parts = [];
      (function walk(el) {
        for (const ch of el.children) {
          if (ch.id === 'friendsCompliance') continue;
          if (ch.children.length === 0) {
            const t = (ch.textContent || '').trim();
            if (t) parts.push(t);
          } else { walk(ch); }
        }
      })(document.querySelector('#screen-friends'));
      return parts.join('\\n');
    }""")


def shot(page, tag, name, full=False):
    path = os.path.join(OUT, 'shot_%s_%s.png' % (tag, name))
    page.screenshot(path=path, full_page=full, animations='disabled')
    return os.path.basename(path)


def wait_toast(page):
    """等轻提示自然消失，避免 z-index 60 的 toast 盖住底部按钮导致点击被拦截"""
    try:
        page.wait_for_selector('#toast', state='hidden', timeout=4000)
    except Exception:
        pass
    page.wait_for_timeout(80)


def common_checks(page, scen, tag, ce, pe):
    global CONSOLE_TOTAL, PAGEERR_TOTAL
    CONSOLE_TOTAL += len(ce)
    PAGEERR_TOTAL += len(pe)
    check('[%s/%s] console 无 error' % (scen, tag), not ce, ce)
    check('[%s/%s] 无未捕获异常' % (scen, tag), not pe, pe)

    sw = page.evaluate('() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})')
    check('[%s/%s] 无横向滚动' % (scen, tag), sw['sw'] <= sw['iw'] + 1, sw)

    three = page.evaluate("""() => ({
      feed: !!document.querySelector('#feedCard') && document.querySelector('#feedCard').getBoundingClientRect().height > 0,
      rank: !!document.querySelector('#rankingCard') && document.querySelector('#rankingCard').getBoundingClientRect().height > 0,
      cheer: !!document.querySelector('#cheerCard') && document.querySelector('#cheerCard').getBoundingClientRect().height > 0
    })""")
    check('[%s/%s] 三件套区块（动态/排行/互促）可见' % (scen, tag), all(three.values()), three)

    n = page.eval_on_selector_all('#privacyBody .switch-row',
                                  'els => els.length')
    states = page.eval_on_selector_all('#privacyBody .switch-row',
                                       "els => els.map(e => e.getAttribute('aria-checked'))")
    check('[%s/%s] 三个隐私开关齐备且默认全关' % (scen, tag),
          n == 3 and all(s == 'false' for s in states), [n, states])

    bodies = page.evaluate("""() => ({
      feed: (document.querySelector('#feedBody').innerText || '').trim(),
      rank: (document.querySelector('#rankingBody').innerText || '').trim(),
      cheer: (document.querySelector('#cheerBody').innerText || '').trim(),
      invite: (document.querySelector('#inviteCode').innerText || '').trim()
    })""")
    check('[%s/%s] 无白屏（各区块均有可读文案）' % (scen, tag),
          all(len(v) > 0 for v in bodies.values()), bodies)

    taps = page.evaluate("""() => {
      const sels = ['#btnHomeFriends', '#btnBack', '#btnCopyInvite', '#btnAddFriend',
                    '#inInviteCode', '#privacyBody .switch-row', '#cheerBody .fr-btn'];
      const out = [];
      for (const s of sels) {
        for (const e of document.querySelectorAll(s)) {
          if (e.offsetParent === null && e.getClientRects().length === 0) continue;
          const r = e.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) out.push([s, Math.round(r.height)]);
        }
      }
      return out;
    }""")
    check('[%s/%s] 可见点击区 ≥44px' % (scen, tag),
          len(taps) > 0 and all(h >= 44 for _, h in taps), taps)

    txt = text_sans_compliance(page)
    ban = [w for w in FORBIDDEN if w in txt]
    check('[%s/%s] 好友圈正文无禁用词（合规区外）' % (scen, tag), not ban, ban)
    leak = [w for w in ['生辰', '出生日期', '出生地', '经纬度', '通道明细', '病历'] if w in txt]
    check('[%s/%s] 未展示生辰/体征/通道明细/病历' % (scen, tag), not leak, leak)

    comp = page.text_content('#friendsCompliance') or ''
    check('[%s/%s] 结果屏保留免责声明与 AI 标识' % (scen, tag),
          '不属于医疗器械' in comp and '本内容由 AI 生成' in comp, comp[:120])

    code = page.text_content('#inviteCode').strip()
    if scen == 'error500':
        check('[%s/%s] 邀请码读取失败有可读占位' % (scen, tag), code not in ('', '········'), code)
        check('[%s/%s] 接口 500 有可读错误条' % (scen, tag),
              page.is_visible('#alertBox') and len(page.text_content('#alertText')) > 0,
              page.text_content('#alertText'))
    else:
        check('[%s/%s] 邀请码 8 位且已显示' % (scen, tag),
              len(code) == 8 and code == 'K7QM2X9P', code)
        check('[%s/%s] 昵称显示（不含真名/手机号）' % (scen, tag),
              '用户4821' in (page.text_content('#myNickname') or ''),
              page.text_content('#myNickname'))


def run_scenario(pw, scen, width, height, deep):
    tag = '%dx%d' % (width, height)
    print('\n=== 场景 %s @ %s ===' % (scen, tag))
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={'width': width, 'height': height},
                              device_scale_factor=1)
    try:
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'],
                              origin=BASE.rstrip('/'))
    except Exception:
        pass
    page = ctx.new_page()
    ce, pe = [], []
    page.on('console', lambda m: ce.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: pe.append(str(e)))
    page.add_init_script(build_stub(scen))

    # 首页入口
    page.goto(BASE, wait_until='load')
    page.wait_for_selector('#screen-home:not([hidden])')
    check('[%s/%s] 首页有「好友圈」入口' % (scen, tag),
          page.is_visible('#btnHomeFriends'),
          page.text_content('#btnHomeFriends'))
    shot(page, tag, '%s_home' % scen)
    page.click('#btnHomeFriends')
    page.wait_for_selector('#screen-friends:not([hidden])')
    page.wait_for_timeout(600)
    try:
        page.wait_for_selector('#toast', state='hidden', timeout=3000)
    except Exception:
        pass
    check('[%s/%s] 返回按钮复用 btnBack 机制' % (scen, tag),
          page.is_visible('#btnBack'))

    shot(page, tag, '%s_top' % scen)
    page.evaluate("() => { const e=document.querySelector('#feedCard'); window.scrollTo(0, e.offsetTop-10); }")
    page.wait_for_timeout(150)
    shot(page, tag, '%s_mid' % scen)
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(150)
    shot(page, tag, '%s_bottom' % scen)
    page.evaluate('() => window.scrollTo(0, 0)')
    page.wait_for_timeout(100)
    shot(page, tag, '%s_full' % scen, full=True)

    common_checks(page, scen, tag, ce, pe)

    if scen == 'empty':
        feed = page.text_content('#feedBody') or ''
        check('[%s/%s] 空态：动态有友好文案' % (scen, tag), '好友动态还是空的' in feed, feed[:120])
        check('[%s/%s] 空态：互促有引导文案' % (scen, tag),
              '还没有好友' in (page.text_content('#cheerBody') or ''))
        check('[%s/%s] 空态：排行有提示' % (scen, tag),
              '还没有人上榜' in (page.text_content('#rankingBody') or ''),
              page.text_content('#rankingBody'))
        check('[%s/%s] 空态：待确认区隐藏' % (scen, tag), not page.is_visible('#pendingWrap'))
        check('[%s/%s] 未开启 in_ranking 时显示开关提示' % (scen, tag),
              page.is_visible('#rankOff') and
              page.eval_on_selector('#rankOff [data-priv]', "e => e.getAttribute('aria-checked')") == 'false')

    if scen in ('public', 'private_friend') and deep:
        # ②/③ 待确认列表
        if scen == 'public':
            check('[%s/%s] 待确认列表可见' % (scen, tag), page.is_visible('#pendingWrap'))
            check('[%s/%s] 待确认含接受/拒绝按钮' % (scen, tag),
                  page.is_visible('#pendingList [data-accept]') and
                  page.is_visible('#pendingList [data-reject]'))
            check('[%s/%s] 我发出的请求显示等待对方确认' % (scen, tag),
                  '等待对方确认' in (page.text_content('#pendingList') or ''))
            feed = page.text_content('#feedBody') or ''
            check('[%s/%s] 对方公开时动态显示分数 91 与连续 12 天' % (scen, tag),
                  '91' in feed and '12' in feed, feed[:200])
            check('[%s/%s] 动态含加油记录' % (scen, tag),
                  page.is_visible('.feed-cheer') and '早点休息' in feed)
            check('[%s/%s] 自己未开启 share_index → 动态里自己显示未公开' % (scen, tag),
                  page.eval_on_selector('#feedBody .feed-item.is-me .feed-stats',
                                        "e => e.innerText.includes('未公开')"))

            # 开启 share_index → 立刻出现分数（自己 82）
            page.click('#privacyBody [data-priv="share_index"]')
            page.wait_for_timeout(300)
            me_txt = page.eval_on_selector('#feedBody .feed-item.is-me .feed-stats', 'e => e.innerText')
            check('[%s/%s] 开启 share_index 后自己立即出现分数 82' % (scen, tag),
                  '82' in me_txt and '未公开' not in me_txt, me_txt)
            body = page.evaluate("() => window.__calls.filter(c => c.url.includes('/friends/privacy') && c.method === 'POST').map(c => c.body)")
            check('[%s/%s] 开关切换调用 POST /friends/privacy' % (scen, tag),
                  body and body[-1] == {'share_index': True}, body)

            # 关闭 share_index → 立刻回到「未公开」
            page.click('#privacyBody [data-priv="share_index"]')
            page.wait_for_timeout(300)
            me_txt = page.eval_on_selector('#feedBody .feed-item.is-me .feed-stats', 'e => e.innerText')
            check('[%s/%s] 关闭 share_index 后自己立即变为「未公开」' % (scen, tag),
                  '未公开' in me_txt and '82' not in me_txt, me_txt)

            # 键盘：Enter / Space 可操作开关
            page.focus('#privacyBody [data-priv="share_streak"]')
            page.keyboard.press('Enter')
            page.wait_for_timeout(150)
            st = page.eval_on_selector('#privacyBody [data-priv="share_streak"]',
                                       "e => e.getAttribute('aria-checked')")
            check('[%s/%s] 键盘 Enter 可开启开关' % (scen, tag), st == 'true', st)
            page.keyboard.press('Space')
            page.wait_for_timeout(150)
            st = page.eval_on_selector('#privacyBody [data-priv="share_streak"]',
                                       "e => e.getAttribute('aria-checked')")
            check('[%s/%s] 键盘 Space 可关闭开关' % (scen, tag), st == 'false', st)

            # 开启 in_ranking → 排行里自己高亮
            page.click('#privacyBody [data-priv="in_ranking"]')
            page.wait_for_timeout(350)
            check('[%s/%s] 开启 in_ranking 后自己出现在排行且高亮' % (scen, tag),
                  page.is_visible('#rankList .rank-item.is-me') and
                  '我' in page.text_content('#rankList .rank-item.is-me'),
                  page.text_content('#rankList'))
            check('[%s/%s] 排行按分数降序（小明 91 > 我 82）' % (scen, tag),
                  page.eval_on_selector_all('#rankList .rank-score',
                                            "els => els.map(e => e.innerText)")[:2] == ['91', '82'],
                  page.eval_on_selector_all('#rankList .rank-score',
                                            "els => els.map(e => e.innerText)"))
            shot(page, tag, '%s_ranking_self_on' % scen)

            # 加油：模板必须 6 条可选
            wait_toast(page)
            page.click('#cheerBody [data-cheer]')
            page.wait_for_timeout(300)
            n = page.eval_on_selector_all('#tmplList .tmpl-item', 'els => els.length')
            check('[%s/%s] 加油模板可选 6 条' % (scen, tag), n == 6, n)
            check('[%s/%s] 加油模板为中性文案' % (scen, tag),
                  not any(w in (page.text_content('#tmplList') or '') for w in FORBIDDEN))
            shot(page, tag, '%s_cheer_sheet' % scen)
            page.click('#tmplList .tmpl-item')
            page.wait_for_timeout(400)
            calls = page.evaluate("() => window.__calls.filter(c => c.url.includes('/friends/cheer') && c.method === 'POST').map(c => c.body)")
            check('[%s/%s] 选模板后调用 POST /friends/cheer' % (scen, tag),
                  len(calls) == 1 and calls[0]['friend_id'] == 'F1024' and calls[0]['template_id'],
                  calls)
            check('[%s/%s] 今日次数递减为 2' % (scen, tag),
                  '2' in (page.text_content('#cheerQuota') or ''), page.text_content('#cheerQuota'))
            check('[%s/%s] 加油记录出现在动态里' % (scen, tag),
                  page.is_visible('#feedBody .feed-cheer'),
                  (page.text_content('#feedBody') or '')[:160])

            # 解除好友：二次确认
            wait_toast(page)
            page.click('#cheerBody [data-remove]')
            page.wait_for_timeout(300)
            check('[%s/%s] 解除好友需二次确认（先弹确认框，不直接删除）' % (scen, tag),
                  page.is_visible('#confirmSheet') and
                  not page.evaluate("() => window.__calls.some(c => c.method === 'DELETE')"),
                  page.text_content('#confirmText')[:80])
            check('[%s/%s] 确认框文案说明解除后果' % (scen, tag),
                  '互不可见' in (page.text_content('#confirmText') or ''))
            shot(page, tag, '%s_remove_confirm' % scen)
            page.click('#btnConfirmCancel')
            page.wait_for_timeout(200)
            check('[%s/%s] 取消后不删除好友' % (scen, tag),
                  not page.evaluate("() => window.__calls.some(c => c.method === 'DELETE')") and
                  not page.is_visible('#confirmSheet'))
            page.click('#cheerBody [data-remove]')
            page.wait_for_timeout(400)
            shot(page, tag, '%s_remove_confirm' % scen)
            page.click('#btnConfirmOk')
            page.wait_for_timeout(900)
            dele = page.evaluate("() => window.__calls.filter(c => c.method === 'DELETE').map(c => c.url)")
            check('[%s/%s] 二次确认后调用 DELETE /friends/{id}' % (scen, tag),
                  dele and 'F1024' in dele[-1], dele)
            check('[%s/%s] 解除后列表/动态不再出现对方' % (scen, tag),
                  '小明' not in (page.text_content('#feedBody') or '') and
                  '小明' not in (page.text_content('#cheerBody') or ''),
                  (page.text_content('#cheerBody') or '')[:120])

        if scen == 'private_friend':
            feed = page.text_content('#feedBody') or ''
            check('[%s/%s] 对方未公开 → 动态显示「未公开」' % (scen, tag), '未公开' in feed, feed[:200])
            check('[%s/%s] 对方未公开 → 分数 88 绝不出现' % (scen, tag), '88' not in feed, feed[:200])
            check('[%s/%s] 未开启 share_streak → 不显示连续天数' % (scen, tag),
                  '连续记录' not in feed, feed[:200])
            check('[%s/%s] 互促列表同样不显示对方分数' % (scen, tag),
                  '88' not in (page.text_content('#cheerBody') or ''))
            wait_toast(page)
            page.click('#cheerBody [data-cheer]')
            page.wait_for_timeout(300)
            n = page.eval_on_selector_all('#tmplList .tmpl-item', 'els => els.length')
            check('[%s/%s] 接口只给 3 条模板时补足到 6 条' % (scen, tag), n == 6, n)
            page.click('#btnCancelCheer')
            page.wait_for_timeout(200)

    ctx.close()
    browser.close()
    return {'scenario': scen, 'viewport': tag, 'console_errors': ce, 'page_errors': pe}


def run_isolation_check(pw, width, height):
    """社交接口全挂 → 好友圈降级可读；返回其它屏后今日指数照常（互不影响）"""
    tag = '%dx%d' % (width, height)
    print('\n=== 场景 social_down（社交挂 / 指数正常）@ %s ===' % tag)
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={'width': width, 'height': height})
    page = ctx.new_page()
    ce, pe = [], []
    page.on('console', lambda m: ce.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: pe.append(str(e)))
    page.add_init_script(build_stub('social_down'))

    page.goto(BASE, wait_until='load')
    page.evaluate("() => localStorage.setItem('yh.profile_completed', '1')")
    page.reload(wait_until='load')
    page.wait_for_selector('#screen-home:not([hidden])')
    check('[%s/%s] 已建档时首页显示「查看今日健康指数」' % ('social_down', tag),
          page.is_visible('#btnHomeRhythm'))

    page.click('#btnHomeRhythm')
    page.wait_for_selector('#screen-rhythm:not([hidden])')
    page.wait_for_selector('#indexBody .idx-score, #indexBody .idx-pending', timeout=8000)
    check('[%s/%s] 指数屏正常（82 分）' % ('social_down', tag),
          page.text_content('#indexScore').strip() == '82',
          page.text_content('#indexBody'))

    page.click('#btnBack')
    page.click('#btnHomeFriends')
    page.wait_for_selector('#screen-friends:not([hidden])')
    page.wait_for_timeout(500)
    check('[%s/%s] 好友圈降级为可读占位（不白屏）' % ('social_down', tag),
          len((page.text_content('#feedBody') or '').strip()) > 0 and
          len((page.text_content('#cheerBody') or '').strip()) > 0 and
          len((page.text_content('#rankingBody') or '').strip()) > 0,
          (page.text_content('#feedBody') or '')[:80])
    check('[%s/%s] 社交失败有可读错误条' % ('social_down', tag),
          page.is_visible('#alertBox'), page.text_content('#alertText'))
    shot(page, tag, 'social_down_friends')

    page.click('#btnBack')
    page.click('#btnHomeRhythm')
    page.wait_for_selector('#screen-rhythm:not([hidden])')
    page.wait_for_timeout(300)
    check('[%s/%s] 返回后今日指数不受好友圈失败影响' % ('social_down', tag),
          page.is_visible('#screen-rhythm') and
          page.text_content('#indexScore').strip() == '82',
          page.text_content('#indexScore'))
    shot(page, tag, 'social_down_rhythm_after')
    check('[%s/%s] console 无 error' % ('social_down', tag), not ce, ce)
    check('[%s/%s] 无未捕获异常' % ('social_down', tag), not pe, pe)
    global CONSOLE_TOTAL, PAGEERR_TOTAL
    CONSOLE_TOTAL += len(ce)
    PAGEERR_TOTAL += len(pe)

    ctx.close()
    browser.close()
    return {'scenario': 'social_down', 'viewport': tag,
            'console_errors': ce, 'page_errors': pe}


def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    proc, logf = start_server()
    print('静态服务 http://127.0.0.1:%d/ (dir=%s)' % (PORT, WEB))
    try:
        with sync_playwright() as pw:
            runs = []
            for (w, h) in [(430, 932), (1440, 900)]:
                for sc in ['empty', 'public', 'private_friend', 'error500']:
                    deep = sc in ('public', 'private_friend')
                    runs.append(run_scenario(pw, sc, w, h, deep))
                runs.append(run_isolation_check(pw, w, h))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        logf.close()

    passed = sum(1 for r in RESULTS if r['ok'])
    total = len(RESULTS)
    print('\n' + '=' * 62)
    print('断言通过 %d / %d' % (passed, total))
    print('console error 总数 = %d，未捕获异常总数 = %d' % (CONSOLE_TOTAL, PAGEERR_TOTAL))
    print('耗时 %.1fs' % (time.time() - t0))
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump({'passed': passed, 'total': total,
                   'console_errors': CONSOLE_TOTAL, 'page_errors': PAGEERR_TOTAL,
                   'assertions': RESULTS, 'runs': [
                       {'scenario': r['scenario'], 'viewport': r['viewport'],
                        'console_errors': r['console_errors'],
                        'page_errors': r['page_errors']} for r in runs]},
                  f, ensure_ascii=False, indent=2)
    print('截图与报告：%s' % OUT)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
