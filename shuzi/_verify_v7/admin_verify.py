# -*- coding: utf-8 -*-
"""
AI数显 · 元健康 —— 独立后台（/admin/）前端验证
方式：本地静态服务 + Playwright；用 page.add_init_script 覆盖 window.fetch 做接口打桩，
     完全不写 server/、不发真实后端请求。
产出：D:\\shuzi\\_verify_v7\\admin_shots\\ 下双视口截图 + 控制台/断言统计。
"""
import json
import os
import re
import threading
import http.server
import socketserver
import functools
import urllib.parse

from playwright.sync_api import sync_playwright

WEB = r"D:\Deepseek智能体\AI元健康\shuzi\web"
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v7"
SHOTS = os.path.join(OUT, "admin_shots")
PORT = 15121

os.makedirs(SHOTS, exist_ok=True)

# ---------------------------------------------------------------- 断言收集
CHECKS = []


def check(name, cond, detail=""):
    ok = bool(cond)
    CHECKS.append({"name": name, "ok": ok, "detail": str(detail)})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  " + str(detail)) if detail else ""))
    return ok


# ---------------------------------------------------------------- 本地静态服务
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def start_server():
    handler = functools.partial(Quiet, directory=WEB)
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


# ---------------------------------------------------------------- fetch 打桩脚本
STUB_JS = r"""
(function () {
  var CFG = {
    login:  { status: 200, body: { admin_token: 'STUB-TOKEN', expires_in: 3600 } },
    users:  { status: 200, gen: 'users', total: 137 },
    detail: { status: 200, body: {} },
    stats:  { status: 200, body: {} },
    social: { status: 200, body: { total: 45, page: 1, size: 20, items: [] } },
    ban:    { status: 200, body: { ok: true } },
    audit:  { status: 200, body: { total: 88, page: 1, size: 20, items: [] } },
    export: { status: 200, csv: 'member_id,nickname,profile_done,baseline_n\nM0001,小明,1,7\n' },
    envelope: false,
    rules:  []
  };

  function pad(n, w) { var s = String(n); while (s.length < w) s = '0' + s; return s; }

  /* 按页码/关键词生成用户列表，用于验证分页与搜索的接线（变更单口径） */
  function genUsers(q, page, size, total) {
    var items = [];
    for (var i = 0; i < 3; i++) {
      var idx = (page - 1) * size + i + 1;
      items.push({
        member_id: 'M' + pad(idx, 4) + '-abcdefvault:zhengfu.admin.aaa',
        nickname: (q ? q + '-命中' : '用户') + idx,
        profile_done: idx % 2 === 0,
        baseline_n: idx % 8,
        last_active: '2026-10-0' + ((idx % 8) + 1) + 'T09:30:00Z',
        streak_days: idx
      });
    }
    return { total: total, page: page, size: size, items: items };
  }

  /* 线上实现口径：admin_api.py 实际返回的用户项字段名 */
  function genUsersReal(q, page, size, total) {
    var items = [];
    for (var i = 0; i < 3; i++) {
      var idx = (page - 1) * size + i + 1;
      var profiled = idx % 2 === 0;
      var obs = idx % 8;
      items.push({
        member_id: 'M' + pad(idx, 4) + '-abcdefvault:zhengfu.admin.aaa',
        nickname: (q ? q + '-命中' : '用户') + idx,
        invite_code: 'INV' + pad(idx, 3),
        created_at: '2026-10-01T08:00:00',
        account_present: true,
        profile_completed: profiled,
        archive_status: profiled ? '已建档' : '未建档',
        baseline_progress: { observation_count: obs, min_observations: 7,
                             established: obs >= 7, text: obs + '/7' },
        observation_count: obs,
        last_active: '2026-10-0' + ((idx % 8) + 1),
        streak_days: idx,
        checkin_days: idx,
        banned: false,
        friends_accepted: 1, friends_pending: 0, referrer_member_id: null
      });
    }
    return { total: total, page: page, size: size,
             pages: Math.ceil(total / size), items: items, q: q };
  }

  /* 线上实现口径：social 按 kind 分别分页 */
  function genSocialReal(kind, page, size) {
    if (kind === 'cheers') {
      return { kind: 'cheers', total: 7, page: page, size: size, pages: 1,
               counts: { cheer_total: 7, cheer_today: 2 },
               items: [{ id: 11, from_member: 'M0001', to_member: 'M0002',
                         from_nickname: '小明', to_nickname: '小红',
                         template_id: '加油模板A', on_date: '2026-10-08',
                         created_at: '2026-10-08T10:00:00' }] };
    }
    return { kind: 'relations', total: 45, page: page, size: size, pages: 3,
             counts: { accepted: 30, pending: 15 },
             items: [{ id: 1, a_member: 'M0001', b_member: 'M0002',
                       a_nickname: '小明', b_nickname: '小红', status: 'accepted',
                       created_at: '2026-10-08T10:00:00', accepted_at: '2026-10-08T11:00:00' }] };
  }

  function routeOf(url) {
    var path = String(url).replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    if (path.indexOf('/api/v1/admin/') !== 0) return null;
    var rest = path.slice('/api/v1/admin/'.length);
    if (rest === 'login') return 'login';
    if (rest === 'users') return 'users';
    if (rest.indexOf('user/') === 0) return 'detail';
    if (rest === 'stats') return 'stats';
    if (rest === 'social') return 'social';
    if (rest === 'ban') return 'ban';
    if (rest === 'export.csv') return 'export';
    if (rest === 'audit') return 'audit';
    return null;
  }

  var stub = { config: CFG, calls: [] };
  window.__stub = stub;

  window.fetch = function (input, init) {
    init = init || {};
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    var method = String(init.method || 'GET').toUpperCase();
    stub.calls.push({
      url: url, method: method,
      headers: init.headers || {},
      body: init.body === undefined ? null : String(init.body)
    });

    var key = routeOf(url);
    if (!key) return Promise.reject(new TypeError('stub: 未匹配到路由 ' + method + ' ' + url));

    var base = CFG[key] || {};
    var rule = null;
    var rules = CFG.rules || [];
    for (var i = 0; i < rules.length; i++) { if (rules[i].key === key) rule = rules[i]; }

    var status = (rule && rule.status) || base.status || 200;
    var body = (rule && rule.body !== undefined) ? rule.body : base.body;
    var csv = (rule && rule.csv !== undefined) ? rule.csv : base.csv;

    if (base.gen === 'users' && !rule) {
      var qs = new URLSearchParams(String(url).split('?')[1] || '');
      body = genUsers(qs.get('q') || '', Number(qs.get('page') || 1),
                      Number(qs.get('size') || 20), base.total || 0);
    }
    if (base.gen === 'users_real' && !rule) {
      var qs1 = new URLSearchParams(String(url).split('?')[1] || '');
      body = genUsersReal(qs1.get('q') || '', Number(qs1.get('page') || 1),
                          Number(qs1.get('size') || 20), base.total || 0);
    }
    if (base.gen === 'social_real' && !rule) {
      var qs2 = new URLSearchParams(String(url).split('?')[1] || '');
      body = genSocialReal(qs2.get('kind') || 'relations',
                           Number(qs2.get('page') || 1), Number(qs2.get('size') || 20));
    }

    if (key === 'export') {
      return Promise.resolve(new Response(csv || '', {
        status: status, headers: { 'Content-Type': 'text/csv; charset=utf-8' }
      }));
    }

    var payload = (body === undefined ? {} : body);
    if (CFG.envelope) {
      if (status >= 400) {
        payload = { code: (rule && rule.code) || 50000,
                    message: (body && body.message) || '请求失败', data: null,
                    detail: (rule && rule.detail) || null, trace_id: 'stub' };
      } else {
        payload = { code: 0, message: 'ok', data: payload, trace_id: 'stub' };
      }
    }
    return Promise.resolve(new Response(JSON.stringify(payload), {
      status: status, headers: { 'Content-Type': 'application/json' }
    }));
  };
})();
"""

# ---------------------------------------------------------------- 打桩数据
DETAIL_BODY = {
    # 故意塞进敏感字段：前端必须一个都不渲染
    "member_id": "M0001-abcdefvault:zhengfu.admin.aaa",
    "nickname": "小明",
    "invite_code": "AB12CD",
    "birth_date": "1990-05-12",
    "birth_city": "成都",
    "birth_time": "1990-05-12T03:47:00",
    "blood_pressure": "138/88",
    "history_note": "既往有高血压家族史",
    "has_vitals": True,
    "profile_done": True,
    "baseline_n": 7,
    "streak_days": 9,
    "last_active": "2026-10-08T09:30:00Z"
}

STATS_BODY = {
    "total_users": 137, "today_new": 9, "profile_rate": 0.62,
    "checkin_users": 88, "index_bands": {"A": 41, "B": 33, "C": 18, "D": 8},
    "social_edges": 45
}

SOCIAL_BODY = {
    "total": 45, "page": 1, "size": 20,
    "items": [
        {"created_at": "2026-10-08T10:00:00Z", "from_member_id": "M0001", "from_nickname": "小明",
         "to_member_id": "M0002", "to_nickname": "小红", "kind": "好友关系", "cheers": 12,
         "banned": False, "target_member_id": "M0002"},
        {"created_at": "2026-10-07T20:12:00Z", "from_member_id": "M0003", "from_nickname": "小刚",
         "to_member_id": "M0004", "to_nickname": "小美", "kind": "加油", "cheers": 3,
         "banned": True, "target_member_id": "M0004"}
    ]
}

AUDIT_BODY = {
    "total": 88, "page": 1, "size": 20,
    "items": [
        {"created_at": "2026-10-08T10:05:00Z", "operator": "ops", "action": "查看用户详情", "target": "M0001"},
        {"created_at": "2026-10-08T10:06:00Z", "operator": "ops", "action": "封禁用户", "target": "M0002"}
    ]
}

# ── 以下为「线上实现口径」：JSON 信封 + admin_api.py 的真实字段名 ──────────
DETAIL_REAL = {
    "member_id": "M0001-abcdefvault:zhengfu.admin.aaa", "nickname": "小明", "invite_code": "INV001",
    "created_at": "2026-10-01T08:00:00", "account_present": True,
    "profile_completed": True, "archive_status": "已建档",
    "baseline_progress": {"observation_count": 7, "min_observations": 7,
                          "established": True, "text": "7/7"},
    "last_active": "2026-10-08", "streak_days": 9, "checkin_days": 12, "banned": False,
    "birth": {"completed": True, "birth_date": "1990-05-12", "precision": "day",
              "birth_city": "成都", "birth_region": "四川",
              "exact_time_returned": False, "coordinates_returned": False,
              # ★ 故意塞进敏感字段：前端必须一个都不渲染
              "birth_time": "1990-05-12T03:47:00", "pressure": "138/88"},
    "archive": {"vitals_collected": False, "history_collected": False},
    "today_index": {"date": "2026-10-08", "score": 78.5, "score_kernel": 0.62,
                    "band_code": "B", "band": "平稳"},
    "checkins": {"total": 12, "items": [], "truncated": False},
    "social": {"friends_accepted": 3, "friends_pending": 1,
               "cheer_sent": 5, "cheer_received": 2},
    "referral": {"referrer_member_id": "M0009", "bound_at": "2026-10-02", "source": "invite"},
    "history_note": "既往有高血压家族史",     # ★ 敏感：不得渲染
    "masking_policy": ["出生信息只到日（不回精确出生时刻，也不回经纬度）",
                       "体征数值未采集，不返回",
                       "病史自述未采集，不返回",
                       "打卡只回日期与通道数，不回观测数值"],
}

STATS_REAL = {
    "users_total": 137, "accounts_total": 130, "new_today": 9, "profiled_total": 85,
    "archive_rate": 0.62, "checkin_users_total": 88, "checkin_users_today": 12,
    "checkin_users_7d": 40, "checkin_rate_today": 0.0876,
    "index_distribution": {
        "basis": "展示分口径", "total": 85, "profiled_total": 85, "unavailable": 0,
        "items": [{"code": "A", "name": "充盈", "count": 35, "pct": 41.2, "pct_raw": 41.1765},
                  {"code": "B", "name": "平稳", "count": 28, "pct": 32.9, "pct_raw": 32.9412},
                  {"code": "C", "name": "宜慎", "count": 15, "pct": 17.7, "pct_raw": 17.6471},
                  {"code": "D", "name": "宜静", "count": 7, "pct": 8.2, "pct_raw": 8.2353}],
        "pct_sum": 100.0},
    "friend_circle": {"accepted": 30, "pending": 15, "members_with_friends": 18,
                      "cheer_total": 120, "cheer_today": 6},
    "referral_bound": 22, "banned_users": 2, "on_date": "2026-10-08",
}

AUDIT_REAL = {
    "total": 88, "page": 1, "size": 20, "pages": 5, "action": None,
    "counts": {"login_ok": 2, "login_fail": 2, "login_locked": 0, "user_detail": 1,
               "ban": 0, "unban": 0, "export": 0},
    "items": [{"id": 4, "at": "2026-10-08T09:57:33", "actor": "admin", "session": "7a5f",
               "action": "login_ok", "target": "", "ip": "127.0.0.1", "detail": {}},
              {"id": 3, "at": "2026-10-08T09:58:10", "actor": "admin", "session": "7a5f",
               "action": "user_detail", "target": "M0001", "ip": "127.0.0.1", "detail": {}}],
}


def set_cfg(page, **kw):
    page.evaluate("c => { Object.assign(window.__stub.config, c); }", kw)


def set_rules(page, rules):
    page.evaluate("r => { window.__stub.config.rules = r; }", rules)


def clear_calls(page):
    page.evaluate("() => { window.__stub.calls.length = 0; }")


def calls(page):
    return page.evaluate("() => window.__stub.calls")


def shot(page, name):
    p = os.path.join(SHOTS, "%s.png" % name)
    page.screenshot(path=p, full_page=False)
    print("    shot -> %s" % p)
    return p


# ---------------------------------------------------------------- 主流程（双视口各跑一遍）
def run_suite(page, view, pad):
    tag = lambda n: "%s_%s" % (n, pad)

    # ---------- 基础配置 ----------
    # 注意：add_init_script 在每次导航都会重建 window.__stub，
    # 因此打桩配置必须在 reload 之后写入才生效。
    page.evaluate("() => { try { sessionStorage.clear(); } catch (e) {} }")
    page.reload()
    # 登录先配成失败口径，用来验证错误提示；成功口径在 ①b 之后切换
    set_cfg(page, login={"status": 401, "body": {"message": "口令错误"}},
            detail={"status": 200, "body": DETAIL_BODY},
            stats={"status": 200, "body": STATS_BODY},
            social={"status": 200, "body": SOCIAL_BODY},
            audit={"status": 200, "body": AUDIT_BODY},
            users={"status": 200, "gen": "users", "total": 137})
    set_rules(page, [])
    page.evaluate("() => { window.__stub.calls.length = 0; }")
    page.wait_for_selector("#loginView:not([hidden])", timeout=8000)
    page.wait_for_timeout(300)

    # ① 登录页截图 + 锁定说明
    shot(page, tag("01_login"))
    hint = page.inner_text("#loginHint")
    check("[%s] 登录页展示『失败 5 次锁定 15 分钟』说明" % view, "5 次" in hint and "15 分钟" in hint, hint[:40])

    # ①b 登录失败提示
    page.fill("#loginPwd", "wrong-pass")
    page.click("#loginBtn")
    page.wait_for_selector("#loginErr:not([hidden])", timeout=8000)
    err = page.inner_text("#loginErr")
    check("[%s] 口令错误 → 可读错误提示" % view, ("口令错误" in err) and ("5 次" in err), err)
    check("[%s] 登录失败时不写入会话令牌" % view,
          page.evaluate("() => sessionStorage.getItem('shuzi_admin_token')") in (None, ""))

    # ② 登录成功 → 用户列表
    set_cfg(page, login={"status": 200, "body": {"admin_token": "STUB-TOKEN", "expires_in": 3600}})
    page.fill("#loginPwd", "correct-pass")
    page.click("#loginBtn")
    page.wait_for_selector("#appView:not([hidden])", timeout=8000)
    page.wait_for_selector("#userRows tr", timeout=8000)
    page.wait_for_timeout(250)
    tok = page.evaluate("() => sessionStorage.getItem('shuzi_admin_token')")
    check("[%s] 登录成功 → 令牌存 sessionStorage" % view, tok == "STUB-TOKEN", tok)
    check("[%s] 登录成功 → 不进 localStorage" % view,
          page.evaluate("() => window.localStorage.length") == 0)
    shot(page, tag("02_users"))

    row1 = page.inner_text("#userRows")
    check("[%s] 用户列表首屏渲染页码 1 数据" % view, "用户1" in row1 and "用户21" not in row1)
    check("[%s] 列表列含建档状态/基线进度/连续天数" % view,
          ("已建档" in row1 or "未建档" in row1) and "/ 7" in row1 and "天" in row1)
    check("[%s] member_id 超长已截断（带省略号）" % view, "…" in row1, "")

    # ③ 分页
    clear_calls(page)
    page.click('#userPager [data-go="next"]')
    page.wait_for_function("() => document.getElementById('userRows').innerText.indexOf('用户21') >= 0",
                           timeout=8000)
    page.wait_for_timeout(150)
    c = calls(page)
    check("[%s] 下一页 → 请求 page=2" % view, any("page=2" in x["url"] for x in c),
          c[-1]["url"] if c else "")
    check("[%s] 下一页 → 列表换页（用户21 出现）" % view, "用户21" in page.inner_text("#userRows"))

    # ④ 搜索
    clear_calls(page)
    page.fill("#userQ", "阿宝")
    page.click("#userSearchBtn")
    page.wait_for_function("() => document.getElementById('userRows').innerText.indexOf('阿宝-命中1') >= 0",
                           timeout=8000)
    page.wait_for_timeout(150)
    c = calls(page)
    q_url = c[-1]["url"] if c else ""
    check("[%s] 搜索 → 请求带 q 且回到第 1 页" % view,
          ("q=" in q_url) and ("page=1" in q_url), q_url)
    check("[%s] 搜索 → 关键词按 URL 编码" % view,
          urllib.parse.quote("阿宝") in q_url, q_url)
    check("[%s] 搜索 → 结果渲染命中项" % view, "阿宝-命中1" in page.inner_text("#userRows"))
    page.click("#userResetBtn")
    page.wait_for_function("() => document.getElementById('userRows').innerText.indexOf('用户1') >= 0",
                           timeout=8000)

    # ⑤ 详情抽屉（字段级脱敏断言）
    clear_calls(page)
    page.click("#userRows tr.row-click")
    page.wait_for_selector("#drawer:not([hidden])", timeout=8000)
    page.wait_for_function(
        "() => document.getElementById('drawerBody').innerText.indexOf('身份') >= 0", timeout=8000)
    page.wait_for_timeout(250)
    shot(page, tag("03_detail"))

    d_html = page.inner_html("#drawerBody")
    d_text = page.inner_text("#drawerBody")
    sent = page.evaluate("() => JSON.stringify(window.__stub.config.detail.body)")
    check("[%s] 【前置】桩返回确实含敏感字段" % view,
          ("birth_time" in sent) and ("blood_pressure" in sent) and ("history_note" in sent))
    check("[%s] 详情不含精确出生时刻字段名/值" % view,
          ("birth_time" not in d_html) and ("03:47" not in d_text) and ("T03" not in d_text))
    check("[%s] 详情不含体征数值" % view,
          ("blood_pressure" not in d_html) and ("138/88" not in d_text) and ("138" not in d_text))
    check("[%s] 详情不含病史原文" % view,
          ("history_note" not in d_html) and ("家族史" not in d_text) and ("高血压" not in d_text))
    check("[%s] 详情保留合规必需信息（出生年月日/出生城市/是否已填体征）" % view,
          ("1990-05-12" in d_text) and ("成都" in d_text) and ("已填写" in d_text) and ("不含出生时刻" in d_text))
    check("[%s] 详情显式写明合规口径" % view,
          "按合规要求：后台不展示精确出生时刻、体征数值与病史原文" in d_text)
    page.click("#drawerClose")
    page.wait_for_selector("#drawer", state="hidden", timeout=5000)

    # ⑥ 运营指标
    page.click('.nav-btn[data-panel="stats"]')
    page.wait_for_selector("#panel-stats:not([hidden])", timeout=8000)
    page.wait_for_selector(".stat", timeout=8000)
    page.wait_for_timeout(250)
    shot(page, tag("04_stats"))
    stats_text = page.inner_text("#panel-stats")
    check("[%s] 指标卡 5 项齐全" % view,
          all(k in stats_text for k in ["总用户", "今日新增", "建档率", "打卡用户", "好友圈关系数"]),
          page.inner_text("#statsGrid").replace("\n", " | "))
    check("[%s] 建档率 0.62 → 62%%" % view, "62%" in stats_text)
    bars = page.eval_on_selector_all(".bar-row", "els => els.map(e => e.getAttribute('data-band'))")
    check("[%s] 指数分布 A/B/C/D 四条横向条" % view, bars == ["A", "B", "C", "D"], bars)
    pcts = page.eval_on_selector_all(".bar-val", "els => els.map(e => parseFloat(e.innerText))")
    check("[%s] A+B+C+D 占比之和 = 100%%（±1）" % view, abs(sum(pcts) - 100) <= 1, pcts)

    # ⑦ 好友圈治理 → 封禁二次确认
    page.click('.nav-btn[data-panel="social"]')
    page.wait_for_selector("#panel-social:not([hidden])", timeout=8000)
    page.wait_for_selector("#socialRows tr", timeout=8000)
    page.wait_for_timeout(200)
    check("[%s] 好友圈表渲染关系与加油次数" % view,
          ("小明" in page.inner_text("#socialRows")) and ("12" in page.inner_text("#socialRows")))

    clear_calls(page)
    page.click('#socialRows [data-ban="M0002"]')
    page.wait_for_selector("#modalMask:not([hidden])", timeout=8000)
    page.wait_for_timeout(250)
    shot(page, tag("05_ban_confirm"))
    m_text = page.inner_text("#modalText")
    check("[%s] 封禁前弹出二次确认（含目标与后果说明）" % view,
          ("M0002" in m_text) and ("停用" in m_text), m_text)
    check("[%s] 二次确认前不发封禁请求" % view,
          not any(x["url"].endswith("/ban") for x in calls(page)))

    page.click("#modalOk")
    page.wait_for_function(
        "() => window.__stub.calls.some(c => c.url.indexOf('/api/v1/admin/ban') >= 0)", timeout=8000)
    page.wait_for_timeout(200)
    ban_calls = [x for x in calls(page) if x["url"].endswith("/api/v1/admin/ban")]
    bc = ban_calls[-1] if ban_calls else {}
    check("[%s] 确认后发出 POST /admin/ban" % view, bc.get("method") == "POST", bc.get("method"))
    check("[%s] ban 请求体字段为 member_id/banned" % view,
          json.loads(bc.get("body") or "{}") == {"member_id": "M0002", "banned": True}, bc.get("body"))
    check("[%s] ban 请求带 Bearer 令牌" % view,
          bc.get("headers", {}).get("Authorization") == "Bearer STUB-TOKEN",
          bc.get("headers", {}).get("Authorization"))

    # ⑧ 导出：fetch + blob 下载
    page.click('.nav-btn[data-panel="export"]')
    page.wait_for_selector("#panel-export:not([hidden])", timeout=8000)
    clear_calls(page)
    url_before = page.url
    with page.expect_download(timeout=15000) as dl_info:
        page.click("#exportBtn")
    dl = dl_info.value
    check("[%s] 导出触发浏览器下载" % view, dl.suggested_filename == "ai-users-export.csv",
          dl.suggested_filename)
    body = open(dl.path(), "r", encoding="utf-8-sig", errors="replace").read()
    check("[%s] 下载内容为 CSV 且脱敏表头" % view, body.startswith("member_id,nickname"), body[:40].replace("\n", "|"))
    ex = [x for x in calls(page) if "export.csv" in x["url"]]
    check("[%s] 导出走 fetch（非 a[href] 导航）" % view, len(ex) == 1 and page.url == url_before,
          ex[-1]["url"] if ex else "no call")
    check("[%s] 导出请求带 Bearer 令牌" % view,
          ex and ex[-1]["headers"].get("Authorization") == "Bearer STUB-TOKEN")

    # ⑨ 401 → 回登录
    set_rules(page, [{"key": "users", "status": 401, "body": {"message": "令牌失效"}}])
    page.click('.nav-btn[data-panel="users"]')
    page.click("#userReloadBtn")
    page.wait_for_selector("#loginView:not([hidden])", timeout=8000)
    page.wait_for_timeout(200)
    check("[%s] 401 → 自动回到登录界面" % view, page.is_visible("#loginView") and not page.is_visible("#appView"))
    check("[%s] 401 → 会话令牌被清除" % view,
          page.evaluate("() => sessionStorage.getItem('shuzi_admin_token')") in (None, ""))
    check("[%s] 401 → 登录界面给出失效提示" % view, "登录已失效" in page.inner_text("#loginErr"))
    shot(page, tag("06_login_401"))

    # ⑩ 500 不白屏
    set_rules(page, [])
    page.fill("#loginPwd", "correct-pass")
    page.click("#loginBtn")
    page.wait_for_selector("#appView:not([hidden])", timeout=8000)
    page.wait_for_selector("#userRows tr", timeout=8000)
    set_rules(page, [{"key": "users", "status": 500, "body": {"message": "服务端内部错误"}}])
    page.click("#userReloadBtn")
    page.wait_for_function(
        "() => (document.getElementById('globalErrText')||{}).textContent || "
        "(document.getElementById('userErr')||{}).innerText || ''", timeout=8000)
    page.wait_for_timeout(300)
    err_all = page.inner_text("#userErr") + " " + page.inner_text("#userRows")
    skeleton = page.evaluate("""() => ({
        app: !!document.querySelector('#appView:not([hidden])'),
        active: (document.querySelector('.panel:not([hidden])') || {}).id || null,
        errShown: !!document.querySelector('#userErr:not([hidden])'),
        tableShown: (function(){ var t = document.querySelector('#userRows');
                                 if (!t) return false; var r = t.getBoundingClientRect();
                                 return r.width > 0 && r.height > 0; })(),
        bodyLen: document.body.innerText.trim().length
    })""")
    check("[%s] 500 → 后台骨架仍在（不白屏）" % view,
          bool(skeleton["app"]) and skeleton["active"] == "panel-users" and
          skeleton["errShown"] and skeleton["tableShown"] and skeleton["bodyLen"] > 50, skeleton)
    check("[%s] 500 → 界面出现可读错误条" % view,
          ("加载失败" in err_all) or ("HTTP 500" in err_all), err_all.strip()[:60])
    check("[%s] 500 → 错误条含重试按钮" % view,
          page.locator("#userErr button").count() + page.locator("#userRows button").count() >= 1)
    shot(page, tag("07_err500"))

    # ⑪ 审计
    set_rules(page, [])
    page.click('.nav-btn[data-panel="audit"]')
    page.wait_for_selector("#panel-audit:not([hidden])", timeout=8000)
    page.wait_for_selector("#auditRows tr", timeout=8000)
    page.wait_for_timeout(200)
    a_text = page.inner_text("#panel-audit")
    check("[%s] 审计表含 时间/操作者/动作/目标" % view,
          all(k in a_text for k in ["ops", "查看用户详情", "封禁用户", "M0001"]), a_text.replace("\n", " | ")[:120])
    shot(page, tag("08_audit"))

    # ⑫ 移动端不横向溢出（仅 430 视口做严格断言）
    if view.startswith("430"):
        ow = page.evaluate("() => ({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
        check("[%s] 页面本身无横向溢出" % view, ow["s"] <= ow["c"] + 1, ow)
        tw = page.evaluate("""() => {
            var e = document.querySelector('.panel:not([hidden]) .table-wrap');
            return e ? { sw: e.scrollWidth, cw: e.clientWidth } : null;
        }""")
        check("[%s] 宽表在容器内可横向滚动" % view, bool(tw) and tw["sw"] > tw["cw"], tw)


def run_real_shape_suite(page, view):
    """线上实现口径：JSON 信封 {code,message,data} + admin_api.py 真实字段名。"""
    set_cfg(page, envelope=True,
            login={"status": 200, "body": {"admin_token": "STUB-TOKEN", "expires_in": 7200}},
            users={"status": 200, "gen": "users_real", "total": 137},
            detail={"status": 200, "body": DETAIL_REAL},
            stats={"status": 200, "body": STATS_REAL},
            social={"status": 200, "gen": "social_real"},
            audit={"status": 200, "body": AUDIT_REAL},
            ban={"status": 200, "body": {"member_id": "M0002", "banned": True}})
    set_rules(page, [])
    page.evaluate("() => { try { sessionStorage.clear(); } catch (e) {} }")
    page.reload()
    set_cfg(page, envelope=True,
            login={"status": 200, "body": {"admin_token": "STUB-TOKEN", "expires_in": 7200}},
            users={"status": 200, "gen": "users_real", "total": 137},
            detail={"status": 200, "body": DETAIL_REAL},
            stats={"status": 200, "body": STATS_REAL},
            social={"status": 200, "gen": "social_real"},
            audit={"status": 200, "body": AUDIT_REAL},
            ban={"status": 200, "body": {"member_id": "M0002", "banned": True}})
    page.wait_for_selector("#loginView:not([hidden])", timeout=8000)

    page.fill("#loginPwd", "correct-pass")
    page.click("#loginBtn")
    page.wait_for_selector("#appView:not([hidden])", timeout=8000)
    page.wait_for_selector("#userRows tr", timeout=8000)
    check("[%s·实现口径] 信封 {code,message,data} 能正确解包并登录" % view,
          page.evaluate("() => sessionStorage.getItem('shuzi_admin_token')") == "STUB-TOKEN")

    rows = page.inner_text("#userRows")
    check("[%s·实现口径] 列表用 archive_status 渲染建档状态" % view,
          ("已建档" in rows) and ("未建档" in rows), rows.replace("\n", " | ")[:90])
    check("[%s·实现口径] 列表用 baseline_progress 渲染 n/7" % view, "/ 7" in rows)

    # 指标：users_total / new_today / archive_rate / checkin_users_total / friend_circle
    page.click('.nav-btn[data-panel="stats"]')
    page.wait_for_selector(".stat", timeout=8000)
    page.wait_for_timeout(200)
    st = page.inner_text("#panel-stats")
    check("[%s·实现口径] 指标卡用 users_total/new_today/archive_rate/checkin_users_total" % view,
          all(k in st for k in ["137", "9", "62%", "88"]), page.inner_text("#statsGrid").replace("\n", " | "))
    check("[%s·实现口径] 好友圈关系数取 friend_circle.accepted 并带子项" % view,
          ("30" in st) and ("待确认 15" in st) and ("加油 120" in st),
          page.inner_text("#statsGrid").replace("\n", " | "))
    check("[%s·实现口径] 建档率卡带已建档人数" % view, "已建档 85 人" in st)
    bands = page.eval_on_selector_all(".bar-row", "els => els.map(e => e.getAttribute('data-band'))")
    pcts = page.eval_on_selector_all(".bar-val", "els => els.map(e => parseFloat(e.innerText))")
    check("[%s·实现口径] index_distribution.items → A/B/C/D 四条" % view,
          bands == ["A", "B", "C", "D"], bands)
    check("[%s·实现口径] 实现口径占比之和 = 100%%" % view, abs(sum(pcts) - 100) <= 0.5, pcts)

    # 好友圈：关系 kind 默认 + 加油 kind 切换
    page.click('.nav-btn[data-panel="social"]')
    page.wait_for_selector("#socialRows tr", timeout=8000)
    s_text = page.inner_text("#socialRows")
    check("[%s·实现口径] relations 行渲染双方昵称与状态" % view,
          ("小明" in s_text) and ("小红" in s_text) and ("已建立" in s_text), s_text.replace("\n", " | ")[:90])
    check("[%s·实现口径] 封禁对象取 b_member" % view,
          page.get_attribute('#socialRows [data-ban]', "data-ban") == "M0002")
    clear_calls(page)
    page.click('#socialKind [data-kind="cheers"]')
    page.wait_for_function(
        "() => window.__stub.calls.some(c => c.url.indexOf('kind=cheers') >= 0)", timeout=8000)
    page.wait_for_timeout(200)
    check("[%s·实现口径] 切到加油记录 → 请求带 kind=cheers" % view,
          any("kind=cheers" in x["url"] for x in calls(page)))
    ch = page.inner_text("#socialRows")
    check("[%s·实现口径] cheers 行渲染加油模板与日期" % view,
          ("加油模板A" in ch) and ("2026-10-08" in ch), ch.replace("\n", " | ")[:90])
    check("[%s·实现口径] 封禁对象取 to_member（加油行）" % view,
          page.get_attribute('#socialRows [data-ban]', "data-ban") == "M0002")

    # 二次确认 → 发请求
    clear_calls(page)
    page.click('#socialRows [data-ban="M0002"]')
    page.wait_for_selector("#modalMask:not([hidden])", timeout=8000)
    page.click("#modalOk")
    page.wait_for_function(
        "() => window.__stub.calls.some(c => c.url.indexOf('/api/v1/admin/ban') >= 0)", timeout=8000)
    bc = [x for x in calls(page) if x["url"].endswith("/ban")][-1]
    check("[%s·实现口径] 封禁请求体与契约一致" % view,
          json.loads(bc["body"]) == {"member_id": "M0002", "banned": True}, bc["body"])

    # 审计：时间字段名 at
    page.click('.nav-btn[data-panel="audit"]')
    page.wait_for_selector("#auditRows tr", timeout=8000)
    page.wait_for_timeout(200)
    a_text = page.inner_text("#panel-audit")
    check("[%s·实现口径] 审计用 at/actor/action/target 渲染时间列" % view,
          ("2026-10-08 09:57" in a_text) and ("admin" in a_text) and
          ("user_detail" in a_text) and ("M0001" in a_text), a_text.replace("\n", " | ")[:110])

    # 详情：嵌套 birth / archive
    page.click('.nav-btn[data-panel="users"]')
    page.wait_for_selector("#userRows tr", timeout=8000)
    page.click("#userRows tr.row-click")
    page.wait_for_selector("#drawer:not([hidden])", timeout=8000)
    page.wait_for_function(
        "() => document.getElementById('drawerBody').innerText.indexOf('身份') >= 0", timeout=8000)
    page.wait_for_timeout(200)
    d_text = page.inner_text("#drawerBody")
    d_html = page.inner_html("#drawerBody")
    check("[%s·实现口径] 详情取 birth.birth_date / birth.birth_city" % view,
          ("1990-05-12" in d_text) and ("成都" in d_text))
    check("[%s·实现口径] archive.vitals_collected=false → 未采集" % view, "未采集" in d_text)
    check("[%s·实现口径] 今日指数（展示分 + 分档）已渲染" % view,
          ("78.5" in d_text) and ("平稳" in d_text))
    check("[%s·实现口径] 嵌套敏感字段仍不渲染" % view,
          ("03:47" not in d_text) and ("birth_time" not in d_html) and
          ("138" not in d_text) and ("家族史" not in d_text), "")
    check("[%s·实现口径] 服务端脱敏口径原样展示" % view, "服务端脱敏口径" in d_text)
    page.click("#drawerClose")

    # 导出仍走 fetch + blob
    page.click('.nav-btn[data-panel="export"]')
    with page.expect_download(timeout=15000) as dl_info:
        page.click("#exportBtn")
    check("[%s·实现口径] 信封模式下导出仍为 blob 下载" % view,
          dl_info.value.suggested_filename == "ai-users-export.csv")


def main():
    httpd = start_server()
    console_errors = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for view, size in [("430x932", {"width": 430, "height": 932}),
                           ("1440x900", {"width": 1440, "height": 900})]:
            pad = view.replace("x", "x")
            print("\n=== 视口 %s ===" % view)
            ctx = browser.new_context(viewport=size, accept_downloads=True)
            page = ctx.new_page()
            page.on("console", lambda m, v=view: console_errors.append({"view": v, "text": m.text})
                    if m.type == "error" else None)
            page.on("pageerror", lambda e, v=view: page_errors.append({"view": v, "text": str(e)}))
            page.add_init_script(STUB_JS)
            page.goto("http://127.0.0.1:%d/admin/index.html" % PORT, wait_until="domcontentloaded")
            run_suite(page, view, pad)
            print("\n--- 实现口径（JSON 信封 + admin_api.py 字段名）---")
            run_real_shape_suite(page, view)
            ctx.close()
        browser.close()

    httpd.shutdown()

    # 截图清单核对：五个必备场景 × 双视口
    print("\n=== 截图清单 ===")
    for r in ["01_login", "02_users", "03_detail", "04_stats", "05_ban_confirm"]:
        for v in ["430x932", "1440x900"]:
            fp = os.path.join(SHOTS, "%s_%s.png" % (r, v))
            sz = os.path.getsize(fp) if os.path.exists(fp) else 0
            check("[截图] %s_%s.png 存在且非空" % (r, v), sz > 8000, "%d bytes" % sz)

    ok = sum(1 for c in CHECKS if c["ok"])
    total = len(CHECKS)
    print("\n===== 汇总 =====")
    print("断言：%d / %d 通过" % (ok, total))
    print("console 报错：%d" % len(console_errors))
    print("未捕获异常：%d" % len(page_errors))
    for e in console_errors:
        print("  console.error[%s] %s" % (e["view"], e["text"][:200]))
    for e in page_errors:
        print("  pageerror[%s] %s" % (e["view"], e["text"][:200]))
    for c in CHECKS:
        if not c["ok"]:
            print("  FAIL %s  %s" % (c["name"], c["detail"][:160]))

    shots = sorted(os.listdir(SHOTS))
    report = {
        "assertions_total": total, "assertions_pass": ok, "assertions_fail": total - ok,
        "console_errors": console_errors, "page_errors": page_errors,
        "checks": CHECKS, "shots": shots,
    }
    with open(os.path.join(OUT, "admin_verify_result.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("截图清单：%s" % ", ".join(shots))
    return 0 if (ok == total and not page_errors) else 1


if __name__ == "__main__":
    raise SystemExit(main())
