# -*- coding: utf-8 -*-
import json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
API = BASE + "/api/v1"


def call(path, body=None, tok=None, dev="dbg"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("X-Device-ID", dev)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


tok = (call("/auth/password/login", {"identifier": "13900000201", "password": "EmoPass123", "device_id": "dbg-1"}).get("data") or {}).get("access_token")
print("tok", bool(tok))
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    logs = []
    pg.on("console", lambda m: logs.append(m.type + ":" + m.text))
    pg.on("pageerror", lambda e: logs.append("PAGEERROR:" + str(e)))
    pg.on("requestfailed", lambda r: logs.append("REQFAIL:" + r.url + " " + str(r.failure)))
    pg.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id','dbg-web');localStorage.setItem('yh.profile_completed','1');}catch(e){}" % json.dumps(tok))
    pg.goto(BASE + "/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(3000)
    print("visible screens:", pg.evaluate("[].slice.call(document.querySelectorAll('.screen')).filter(function(s){return !s.hidden}).map(function(s){return s.id})"))
    print("tabbar hidden:", pg.evaluate("document.getElementById('tabbar').hidden"))
    pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213\dbg_home.png")
    try:
        pg.click("button[data-tab='rhythm']", timeout=8000)
    except Exception as e:
        print("click rhythm failed", e)
    pg.wait_for_timeout(4000)
    print("visible screens2:", pg.evaluate("[].slice.call(document.querySelectorAll('.screen')).filter(function(s){return !s.hidden}).map(function(s){return s.id})"))
    print("indexBody:", pg.evaluate("(document.getElementById('indexBody')||{}).innerText"))
    print("energyIdx hidden:", pg.evaluate("document.getElementById('energyIdxCard').hidden"))
    print("energyIdxBody:", pg.evaluate("(document.getElementById('energyIdxBody')||{}).innerText"))
    print("rhythmWho:", pg.evaluate("(document.getElementById('rhythmWho')||{}).innerText"))
    print("logs:", logs[-15:])
    pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213\dbg_rhythm.png", full_page=True)
    b.close()
