# -*- coding: utf-8 -*-
r"""
数显 v18 验收：① 首页入口组移入用户中心  ② 底部导航新增「健康商城」（真浏览器 + 静态接线）

师父令（2026-10-10）：
  ① 截图圈出首页那一组入口（重新建档 / 查看今日健康指数 / 好友圈 / 订阅 /
     我的积分·推广收益 / 添加家人）→「这部分不要放首页，移到用户中心」
  ② 「底部的 今日节律 后面增加一个：健康商城」

★ 必须用**系统 Python** 跑（便携运行时没有 playwright）：
    C:\Users\41692\AppData\Local\Programs\Python\Python312\python.EXE
★ 被测量的服务由本脚本自起，stdout 重定向到**日志文件**（绝不用 PIPE 挂着不读 —— 见技能错误记录 28）。
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

WS = r"D:\Deepseek智能体\AI元健康"
ROOT = os.path.join(WS, "shuzi")
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
WEB = os.path.join(ROOT, "web")
PORT = 15198
R = []


def ck(name, ok, detail=''):
    R.append((name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def static_checks():
    """静态接线断言：不依赖浏览器，先把"文件里到底怎么写的"钉死。"""
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()

    tabs = re.findall(r'class="tab-item"\s+data-tab="([a-z]+)"', html)
    ck('S1：底部导航 4 项且顺序=首页/今日节律/健康商城/我的',
       tabs == ['home', 'rhythm', 'mall', 'mine'], str(tabs))
    ck('S2：TAB_VIEWS 与底栏一致（含 mall）',
       "var TAB_VIEWS = ['home', 'rhythm', 'mall', 'mine'];" in js)
    ck('S3：VIEWS 已注册 mall', "'bencao', 'mall']" in js)
    ck('S4：健康商城屏与入口按钮都在 index.html',
       all(k in html for k in ('id="screen-mall"', 'id="btnOpenMall"', 'id="mallUrl"')))

    # 首页那 5 个入口必须彻底消失 —— 判据用「真接线」而不是「出现过这个词」：
    # 只有 $('id') / getElementById('id') / id="id" 才算残留，注释里提到名字不算。
    leftovers = []
    for el in ('btnHomeRhythm', 'btnHomeFriends', 'btnHomeSubscribe',
               'btnHomePoints', 'btnHomeFamily'):
        for pat in (r"\$\('%s'\)" % el, r"getElementById\('%s'\)" % el, r'id="%s"' % el):
            if re.search(pat, html + js):
                leftovers.append('%s:%s' % (el, pat))
    ck('S5：首页 5 个入口 id 无残留接线', not leftovers, '; '.join(leftovers[:3]))
    ck('S6：首页不再有「查看今日健康指数」按钮（该卡本身仍在）',
       'id="btnHomeRhythm"' not in html and 'id="homeDailyCard"' in html)


def browser_checks(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)

        # ── 未建档：首页应只剩「开始建档」这一处主引导 ──────────────
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                            has_touch=True, locale="zh-CN")
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        start = page.locator('#btnStart')
        ck('A1：未建档时首页「开始建档」可见', start.count() == 1 and start.is_visible())
        ck('A2：未建档时文案=开始建档',
           start.count() == 1 and '开始建档' in start.inner_text())

        home_text = page.locator('#screen-home').inner_text()
        gone = []
        for t in ('好友圈', '订阅', '我的积分 / 推广收益', '添加家人', '重新建档'):
            # 首页正文里不应再有这些**入口文案**（正文别处的同名词不算：这里按行首按钮名判）
            if re.search(r'(?m)^\s*' + re.escape(t) + r'\s*$', home_text):
                gone.append(t)
        ck('A3：首页不再有那 5 个入口按钮文案', not gone, '仍出现: %s' % gone)

        # 底栏：4 项、顺序正确
        items = page.locator('#tabbar .tab-item')
        labels = [items.nth(i).inner_text().strip() for i in range(items.count())]
        ck('C1：底栏 4 项，今日节律后面是健康商城',
           labels == ['首页', '今日节律', '健康商城', '我的'], str(labels))

        # 点第 3 项 → 健康商城屏
        items.nth(2).click()
        page.wait_for_timeout(900)
        mall = page.locator('#screen-mall')
        ck('C2：点「健康商城」进入商城屏且底栏高亮',
           mall.is_visible() and 'is-on' in (items.nth(2).get_attribute('class') or ''),
           'class=%s' % items.nth(2).get_attribute('class'))
        mtxt = mall.inner_text()
        ck('C3：商城屏写明域名与结算口径',
           'yuanjk.cn' in mtxt and '独立站点' in mtxt, mtxt.replace('\n', ' ')[:90])
        ck('C4：商城屏含合规声明（不属医疗器械）', '不属于医疗器械' in mtxt)

        # 入口按钮必须真的可点（elementFromPoint 命中自身 —— v16.1 遮挡类判据）
        btn = page.locator('#btnOpenMall')
        hit = page.evaluate("""() => {
            const b = document.getElementById('btnOpenMall');
            const r = b.getBoundingClientRect();
            const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
            return {ok: !!el && (el === b || b.contains(el)), w: Math.round(r.width), h: Math.round(r.height)};
        }""")
        ck('C5：「进入健康商城」按钮未被遮挡且尺寸正常',
           hit['ok'] and hit['w'] > 100 and hit['h'] > 30, str(hit))
        page.screenshot(path=os.path.join(WS, r"_资料\过程截图\_v18_mall.png"), full_page=True)

        # ── 用户中心：六项入口齐全、可点（★ 必须放在 C6 之前 ──────────
        #    C6 会让页面真的导航走（哪怕是被拦成桩页），那之后这个 context 就没用了）
        items.nth(3).click()          # 「我的」
        page.wait_for_timeout(900)
        mine = page.locator('#screen-mine')
        ck('B1：底栏「我的」进入用户中心', mine.is_visible())
        mt = mine.inner_text()
        want = ['我的资料 / 重新建档', '今日健康指数 / 健康档案', '家人管理',
                '我的积分 / 推广收益', '订阅会员', '好友圈']
        missing = [w for w in want if w not in mt]
        ck('B2：用户中心承接了首页那组入口（六项齐全）', not missing, '缺: %s' % missing)

        bad = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('#screen-mine .mine-item').forEach(it => {
                // 按设计隐藏的项（如未登录时的「退出登录」）跳过：0 尺寸不是「被遮挡」
                if (it.hidden || !it.offsetHeight || !it.offsetWidth) { return; }
                // ★ 必须先滚进视口再判定：elementFromPoint 用的是**视口坐标**，
                //   折叠线以下的元素恒为 null —— 不滚动就会把「在屏幕外」误判成「被遮挡」。
                it.scrollIntoView({block: 'center'});
                const r = it.getBoundingClientRect();
                if (r.top < 0 || r.bottom > innerHeight) { out.push('OFFSCREEN:' + (it.innerText||'').trim().slice(0,10)); return; }
                const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                if (!el || !(el === it || it.contains(el))) {
                    out.push((it.innerText||'').trim().slice(0,12));
                }
            });
            return out;
        }""")
        ck('B3：用户中心每一项都没被遮挡（滚动到视口中心后 elementFromPoint 命中自身）',
           not bad, '被挡: %s' % bad)

        # 点「今日健康指数 / 健康档案」→ 真实进入节律屏
        page.locator('#screen-mine .mine-item[data-goto="rhythm"]').click()
        page.wait_for_timeout(2200)
        ck('B4：用户中心可进入今日节律屏',
           page.locator('#screen-rhythm').is_visible())
        page.screenshot(path=os.path.join(WS, r"_资料\过程截图\_v18_mine.png"), full_page=True)

        # ── C6（放最后）：点击后到底请求了哪个地址 ────────────────────
        #   用桩页顶替，让导航"成功"落在一个可读取的 URL 上 —— 比 abort 更好：
        #   abort 会让主框架变成错误页，后面的断言就查不到真实目标地址了。
        items.nth(2).click()          # 回到「健康商城」
        page.wait_for_timeout(700)
        page.route("https://yuanjk.cn/**",
                   lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8",
                                               body="<html><head><title>stub</title></head><body>mall stub</body></html>"))
        page.locator('#btnOpenMall').click()
        try:
            page.wait_for_url(re.compile(r"^https://yuanjk\.cn/"), timeout=8000)
        except Exception:
            pass
        ck('C6：点击后跳转 https://yuanjk.cn/（纯链接、不带任何参数）',
           page.url.rstrip('/') == 'https://yuanjk.cn', page.url)
        ctx.close()

        # ── 已建档：首页「重新建档」必须收起 ────────────────────────
        ctx2 = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                             has_touch=True, locale="zh-CN")
        ctx2.add_init_script("try{localStorage.setItem('yh.profile_completed','1');}catch(e){}")
        page2 = ctx2.new_page()
        errs2 = []
        page2.on("pageerror", lambda e: errs2.append(str(e)[:160]))
        page2.goto(url, wait_until="networkidle", timeout=60000)
        page2.wait_for_timeout(1500)
        s2 = page2.locator('#btnStart')
        ck('A4：已建档时首页不再出现「重新建档」（已收进用户中心）',
           s2.count() == 1 and not s2.is_visible(),
           'hidden=%s' % (s2.get_attribute('hidden') if s2.count() else 'n/a'))
        ck('A5：无新增 JS 报错（未建档的 422 除外）',
           len([e for e in (errs + errs2) if '422' not in e]) == 0, '; '.join((errs + errs2)[:2]))
        page2.screenshot(path=os.path.join(WS, r"_资料\过程截图\_v18_home.png"), full_page=True)
        ctx2.close()
        b.close()


def main():
    static_checks()

    tmp = tempfile.mkdtemp(prefix='v18ui_')
    db = os.path.join(tmp, 't.db')
    logpath = os.path.join(tmp, 'server.log')
    logfh = open(logpath, 'w', encoding='utf-8', errors='replace')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=logfh, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                req = urllib.request.Request("http://127.0.0.1:%d/api/v1/timemed/shichen" % PORT)
                req.add_header("Connection", "close")
                with urllib.request.urlopen(req, timeout=10) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                pass
        print("=== 服务就绪: %s ===" % ok)
        if not ok:
            print(open(logpath, encoding='utf-8', errors='replace').read()[-1200:])
            return 2
        browser_checks("http://127.0.0.1:%d/" % PORT)
    finally:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:
            pass
        logfh.close()

    print("\n================ 汇总 ================")
    fails = [r for r in R if not r[1]]
    print("总计 %d 项，通过 %d，失败 %d" % (len(R), len(R) - len(fails), len(fails)))
    for n, _ok, d in fails:
        print("  FAIL %s  %s" % (n, d))
    print("V18_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
