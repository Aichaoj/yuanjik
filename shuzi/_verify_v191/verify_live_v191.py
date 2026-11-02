# -*- coding: utf-8 -*-
"""v191 公网回读：弹窗 + 录音条 + 回放，都在线上真站验一遍。"""
import json
import os
import sys
import urllib.request

BASE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v191")
os.makedirs(OUT, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main():
    ver = json.loads(get("/version.json?x=v191"))
    check("线上 web=191", ver.get("web") == "191", ver.get("web"))
    check("首条=麦克风弹窗", "弹窗" in (ver.get("notes") or [""])[0])
    html = get("/?x=v191")
    check("线上资源戳 b ×6", html.count("?v=20261028b") == 6, html.count("?v=20261028b"))
    check("线上有权限弹窗", 'id="micDlg"' in html)
    check("线上有录音条", 'id="vsRecBar"' in html and 'id="vsRecPlay"' in html)
    check("线上文案=本机内存", "本机内存" in html and "不上传、不落盘" in html)
    js = get("/app.js?v=20261028b")
    check("线上 WEB_VER=191", "WEB_VER = '191'" in js)
    check("线上录音走 Blob", "new Blob(" in js and "vs.chunks.push" in js)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        # A. 有权限：录音条 + 回放
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(3500)
        pg.click('.tab-item[data-tab="music"]')
        pg.wait_for_selector("#btnGoContribute", state="visible", timeout=20000)
        pg.click("#btnGoContribute")
        pg.wait_for_selector("#screen-contribute:not([hidden])", timeout=20000)
        pg.click("#btnCChant")
        pg.wait_for_selector("#vsRecBar", state="visible", timeout=20000)
        check("线上：录音条出现", pg.is_visible("#vsRecBar"))
        pg.wait_for_timeout(3200)
        t1 = pg.inner_text("#vsRecTime")
        check("线上：时长在走", t1 not in ("00:00", ""), t1)
        pg.screenshot(path=os.path.join(OUT, "live_recbar.png"))
        pg.click("#btnVsStop")
        pg.wait_for_timeout(2500)
        src = pg.evaluate("document.getElementById('vsRecAudio').src || ''")
        check("线上：录音是本地 blob", src.startswith("blob:"), src[:22])
        pg.click("#vsRecPlay")
        pg.wait_for_timeout(1500)
        cur = pg.evaluate("document.getElementById('vsRecAudio').currentTime")
        paused = pg.evaluate("document.getElementById('vsRecAudio').paused")
        check("线上：回放真的在播", (not paused) and cur > 0.2, "t=%.2f paused=%s" % (cur, paused))
        pg.screenshot(path=os.path.join(OUT, "live_playback.png"))
        check("线上：无 JS 异常", not errs, errs[:3])
        ctx.close()

        # B. 没权限：弹窗
        ctx2 = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg2 = ctx2.new_page()
        hits = []
        pg2.on("request", lambda r: hits.append(r.url) if "/vault/session/start" in r.url else None)
        pg2.add_init_script(
            "navigator.mediaDevices.getUserMedia = function(){"
            " return Promise.reject(new DOMException('Permission denied','NotAllowedError')); };")
        pg2.goto(BASE + "/", wait_until="load", timeout=90000)
        pg2.wait_for_timeout(3500)
        pg2.click('.tab-item[data-tab="music"]')
        pg2.wait_for_selector("#btnGoContribute", state="visible", timeout=20000)
        pg2.click("#btnGoContribute")
        pg2.wait_for_selector("#screen-contribute:not([hidden])", timeout=20000)
        pg2.click("#btnCChant")
        pg2.wait_for_selector("#micDlg", state="visible", timeout=15000)
        check("线上：拒绝权限 → 弹窗", pg2.is_visible("#micDlg"))
        check("线上：弹窗说不占次数", "不占今天的次数" in pg2.inner_text("#micDlg"))
        check("线上：拒绝时没发 session/start", not hits, hits[:2])
        pg2.screenshot(path=os.path.join(OUT, "live_dialog.png"))
        ctx2.close()
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "live_result_v191.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
