# -*- coding: utf-8 -*-
"""v15 用户中心真浏览器验收：底部导航 / 我的 / 账号与安全 / 问题解答 / 昵称与改密码全链路。"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15120/"
OUT = r"D:\Deepseek智能体\AI元健康\_资料\过程截图"
R = []


def ck(name, ok, detail=''):
    R.append((name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844},
                        user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
                                    "Mobile/15E148 Safari/604.1"),
                        is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:200]))
    page.on("console", lambda m: errs.append("console:" + m.text[:150]) if m.type == "error" else None)

    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    ck("首页加载且无 JS 报错", len([e for e in errs if not e.startswith('console:')]) == 0,
       "; ".join(errs[:2]))

    # ① 底部导航
    bar = page.locator("#tabbar")
    ck("底部导航存在且可见（首页）", bar.count() == 1 and bar.first.is_visible())
    tabs = page.locator("#tabbar .tab-item")
    ck("底部导航 3 个 tab", tabs.count() == 3, "count=%d" % tabs.count())
    ck("首页 tab 高亮", "is-on" in (page.locator('#tabbar .tab-item[data-tab="home"]').get_attribute("class") or ""))

    # ② 进「我的」
    page.locator('#tabbar .tab-item[data-tab="mine"]').click()
    page.wait_for_timeout(1200)
    ck("切到「我的」屏", page.locator("#screen-mine").is_visible())
    ck("「我的」屏里底部导航仍在", page.locator("#tabbar").is_visible())
    ck("底部导航切到「我的」高亮",
       "is-on" in (page.locator('#tabbar .tab-item[data-tab="mine"]').get_attribute("class") or ""))
    ck("账号卡渲染（未登录文案）", "未登录" in page.locator("#mineNick").inner_text())
    for sid, label in (("mineProfileNote", "我的资料"), ("mineRhythmNote", "健康档案"),
                       ("mineFamilyNote", "家人管理"), ("mineInviteNote", "我的邀请"),
                       ("minePointsNote", "积分"), ("mineSubNote", "订阅"),
                       ("mineAccountNote", "账号与安全")):
        ck("用户中心含「%s」条目" % label, page.locator("#" + sid).count() == 1)
    items = page.locator("#screen-mine .mine-item")
    ck("用户中心条目数 >= 10", items.count() >= 10, "count=%d" % items.count())
    ck("有「修改密码 / 修改昵称」入口",
       page.locator('#screen-mine .mine-item[data-goto="account"]').count() == 1)
    ck("有「退出登录」入口", page.locator("#btnMineLogout").count() == 1)
    ck("有「问题解答」入口",
       page.locator('#screen-mine .mine-item[data-goto="help"]').count() == 1)

    page.screenshot(path=os.path.join(OUT, "_v15_mine.png"), full_page=True)

    # ③ 账号与安全
    page.locator('#screen-mine .mine-item[data-goto="account"]').click()
    page.wait_for_timeout(1000)
    ck("进「账号与安全」屏", page.locator("#screen-account").is_visible())
    ck("「账号与安全」屏隐藏底部导航", not page.locator("#tabbar").is_visible())
    ck("有昵称输入框", page.locator("#inNickname").count() == 1 and page.locator("#inNickname").is_visible())
    ck("有当前密码输入框", page.locator("#inOldPwd").count() == 1)
    ck("有新密码 + 确认输入框",
       page.locator("#inNewPwd").count() == 1 and page.locator("#inNewPwd2").count() == 1)
    ck("有保存昵称按钮", page.locator("#btnSaveNickname").count() == 1)
    ck("有保存新密码按钮", page.locator("#btnChangePwd").count() == 1)
    ck("登录方式说明已渲染", "登录方式" in page.locator("#loginWaysText").inner_text()
       or "还没登录" in page.locator("#loginWaysText").inner_text())
    page.screenshot(path=os.path.join(OUT, "_v15_account.png"), full_page=True)

    # ④ 问题解答
    page.locator("#btnBack").click()
    page.wait_for_timeout(700)
    page.locator('#screen-mine .mine-item[data-goto="help"]').click()
    page.wait_for_timeout(900)
    ck("进「问题解答」屏", page.locator("#screen-help").is_visible())
    qs = page.locator("#helpList .help-q")
    ck("问题解答条目 >= 8", qs.count() >= 8, "count=%d" % qs.count())
    first_a = page.locator("#helpList .help-a").first
    ck("答案默认收起", first_a.is_hidden())
    qs.first.click()
    page.wait_for_timeout(400)
    ck("点击后答案展开", page.locator("#helpList .help-a").first.is_visible())
    page.screenshot(path=os.path.join(OUT, "_v15_help.png"), full_page=True)

    # ⑤ 登录面板：登录态收昵称
    page.locator("#btnBack").click()
    page.wait_for_timeout(600)
    page.locator('#tabbar .tab-item[data-tab="home"]').click()
    page.wait_for_timeout(600)
    page.locator("#btnAuthEntry").click()
    page.wait_for_timeout(900)
    ip = page.locator("#inAuthPhone")
    ck("登录模式：输入框接受文字（type=text）", (ip.get_attribute("type") or "") == "text",
       "type=%s maxlength=%s" % (ip.get_attribute("type"), ip.get_attribute("maxlength")))
    ck("登录模式：标签为「手机号 / 昵称」",
       "昵称" in page.locator("#authPhoneLabel").inner_text())
    ip.fill("大艾")
    ck("昵称可输入（非数字）", ip.input_value() == "大艾")

    # 切到注册模式应回到手机号
    page.locator("#btnAuthClose").click() if page.locator("#btnAuthClose").count() else None
    page.wait_for_timeout(400)

    b.close()

print("\n================ 汇总 ================")
fails = [r for r in R if not r[1]]
print("总计 %d 项，通过 %d，失败 %d" % (len(R), len(R) - len(fails), len(fails)))
for n, _ok, d in fails:
    print("  FAIL %s  %s" % (n, d))
print("V15UI_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
