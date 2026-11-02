# -*- coding: utf-8 -*-
"""v194 验证：佛音新增两条《诗经》吟唱，插在《金刚经》之后；列表 5→6。

判据（每条可判真假）：
 1. music.json 共 10 条；排序值 -20/-10/-9/-8/20…；两条吟唱文件存在且 >100 KB
 2. /api/v1/music 返回 10 条，前四为 地藏经、金刚经、吟唱·蒹葭、吟唱·关雎
 3. 两个 mp3 HTTP 200 且字节数与本地一致
 4. 页面「音疗」佛音列表 = 6 条；第 3、4 条即两条吟唱；点第 3 条播放器显示其曲名、计时走动
 5. version.json web=194、app.js WEB_VER=194、资源戳 ?v=20261029a ×6
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
PORT = 15100
BASE = "http://127.0.0.1:%d" % PORT
LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(R, "_verify_v194")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v194_")
LOG = open(os.path.join(OUT, "local_server.log"), "w", encoding="utf-8")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def wait_health(deadline=90):
    end = time.time() + deadline
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def api_tracks(base, tag):
    req = urllib.request.Request(base + "/api/v1/music?t=%d" % time.time(),
                                 headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    tracks = (j.get("data") or {}).get("tracks") or []
    for t in tracks:
        t["_tag"] = tag
    return tracks


def static_checks():
    mj = json.load(open(os.path.join(R, "web/music.json"), encoding="utf-8"))
    tr = mj["tracks"]
    check("music.json 共 10 条", len(tr) == 10, len(tr))
    order = [(t.get("title"), t.get("sort")) for t in tr[:4]]
    check("前四条=地藏/金刚/蒹葭/关雎", [x[0][:4] for x in order] ==
          ["地藏经（", "金刚经（", "吟唱·蒹", "吟唱·关"], order)
    check("排序 -20/-10/-9/-8", [x[1] for x in order] == [-20, -10, -9, -8], order)
    for f in ("yinchang-jianjia-tts.mp3", "yinchang-guanju-tts.mp3"):
        p = os.path.join(R, "web/music", f)
        check("文件 %s >100KB" % f, os.path.isfile(p) and os.path.getsize(p) > 100000,
              os.path.getsize(p) if os.path.isfile(p) else "missing")
    js = open(os.path.join(R, "web/music.js"), encoding="utf-8").read()
    check("music.js CHANT_MAX = 6", "var CHANT_MAX = 6;" in js)
    app = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    check("app.js WEB_VER=194", "WEB_VER = '194'" in app)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=194", v.get("web") == "194", v.get("web"))
    check("首条说明=两条吟唱", "吟唱" in (v.get("notes") or [""])[0])
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()
    check("资源戳 20261029a ×6", html.count("?v=20261029a") == 6, html.count("?v=20261029a"))


def page_state(pg):
    return pg.evaluate("""(function(){
      var items = [].slice.call(document.querySelectorAll('#chantList .chant-item'));
      return {n: items.length,
              titles: items.map(function(e){
                 var t = e.querySelector('.chant-title'); return t ? t.innerText.trim() : '';
              }),
              hint: (document.getElementById('chantList')||{}).innerText || '',
              name: (document.getElementById('mpName')||{}).textContent || '',
              time: (document.getElementById('mpTime')||{}).textContent || ''};
    })()""")


def main():
    static_checks()

    env = os.environ.copy()
    env.update({"SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": os.path.join(TMP, "state.db"), "SHUZI_WEB": os.path.join(R, "web")})
    p = subprocess.Popen([os.path.join(R, "runtime", "python.exe"),
                          os.path.join(R, "server", "serve.py")],
                         cwd=os.path.join(R, "server"), env=env,
                         stdout=LOG, stderr=subprocess.STDOUT)
    try:
        check("本地 /api/health 200", wait_health())
        tr = api_tracks(BASE, "local")
        check("本地接口 10 条", len(tr) == 10, len(tr))
        got = [t.get("title") for t in tr[:4]]
        check("本地前三=地藏/金刚/蒹葭", got[0].startswith("地藏经") and got[1].startswith("金刚经")
              and got[2].startswith("吟唱·蒹葭") and got[3].startswith("吟唱·关雎"), got)
        for t in tr[:4]:
            if not t.get("file"):
                continue
            u = BASE + "/" + t["file"]
            with urllib.request.urlopen(u, timeout=30) as r:
                n = len(r.read())
            lp = os.path.join(R, "web", t["file"].replace("/", os.sep))
            check("本地音频 200 %s" % os.path.basename(t["file"]), r.status == 200 and n == os.path.getsize(lp),
                  "%d/%d" % (n, os.path.getsize(lp)))

        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(BASE + "/", wait_until="load", timeout=60000)
            pg.wait_for_timeout(2500)
            pg.click('.tab-item[data-tab="music"]')
            pg.wait_for_timeout(2500)
            st = page_state(pg)
            check("本地：佛音 6 条", st["n"] == 6, st["n"])
            check("本地：第 3、4 条=两条吟唱", st["titles"][2].startswith("吟唱·蒹葭")
                  and st["titles"][3].startswith("吟唱·关雎"), st["titles"])
            check("本地：第 5、6 条=心经/灵隐寺", "心经" in st["titles"][4] and "灵隐寺" in st["titles"][5], st["titles"])
            pg.click('#chantList .chant-item:nth-child(3)')
            pg.wait_for_timeout(3500)
            st2 = page_state(pg)
            check("本地：播放器显示吟唱·蒹葭", "吟唱·蒹葭" in st2["name"], st2["name"])
            check("本地：计时走动", st2["time"] not in ("", "00:00"), st2["time"])
            check("本地：无 JS 异常", not errs, errs[:3])
            pg.screenshot(path=os.path.join(OUT, "local_music.png"), full_page=False)
            b.close()
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    # 线上
    def get(path):
        req = urllib.request.Request(LIVE + path, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    if os.environ.get("V194_LOCAL_ONLY") == "1":
        bad = [x for x in results if not x[1]]
        print("\nSUMMARY(local only) total=%d fail=%d" % (len(results), len(bad)))
        json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
                  open(os.path.join(OUT, "result_v194_local.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        sys.exit(1 if bad else 0)

    lv = json.loads(get("/version.json?x=v194"))
    check("线上 web=194", lv.get("web") == "194", lv.get("web"))
    with urllib.request.urlopen(LIVE + "/api/v1/music?t=%d" % time.time(), timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    lt = ((j.get("data") or {}).get("tracks") or [])
    check("线上接口 10 条", len(lt) == 10, len(lt))
    check("线上前四=地藏/金刚/蒹葭/关雎",
          len(lt) >= 4 and lt[2]["title"].startswith("吟唱·蒹葭") and lt[3]["title"].startswith("吟唱·关雎"),
          [t["title"] for t in lt[:4]])
    for t in lt[2:4]:
        with urllib.request.urlopen(LIVE + "/" + t["file"], timeout=60) as r:
            n = len(r.read())
        lp = os.path.join(R, "web", t["file"].replace("/", os.sep))
        check("线上音频 200 %s" % os.path.basename(t["file"]),
              r.status == 200 and n == os.path.getsize(lp), "%d/%d" % (n, os.path.getsize(lp)))
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(3000)
        pg.click('.tab-item[data-tab="music"]')
        pg.wait_for_timeout(3000)
        st = page_state(pg)
        check("线上：佛音 6 条", st["n"] == 6, st["n"])
        check("线上：第 3、4 条=两条吟唱", len(st["titles"]) >= 4 and st["titles"][2].startswith("吟唱·蒹葭")
              and st["titles"][3].startswith("吟唱·关雎"), st["titles"])
        pg.click('#chantList .chant-item:nth-child(3)')
        pg.wait_for_timeout(4000)
        st2 = page_state(pg)
        check("线上：播放器显示吟唱·蒹葭", "吟唱·蒹葭" in st2["name"], st2["name"])
        check("线上：计时走动", st2["time"] not in ("", "00:00"), st2["time"])
        check("线上：无 JS 异常", not errs, errs[:3])
        pg.screenshot(path=os.path.join(OUT, "live_music.png"), full_page=False)
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v194.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
