# -*- coding: utf-8 -*-
"""Screenshots for v213 family screen (owner bound card + member 'my family' card)."""
import json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
API = BASE + "/api/v1"
SHOTS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213"
A, B = "13900000201", "13900000202"


def call(path, body=None, tok=None, dev="shot"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("X-Device-ID", dev)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


ta = (call("/auth/password/login", {"identifier": A, "password": "EmoPass123", "device_id": "shot-A"}).get("data") or {}).get("access_token")
tb = (call("/auth/password/login", {"identifier": B, "password": "EmoPass123", "device_id": "shot-B"}).get("data") or {}).get("access_token")
code = ((call("/family/invite/create", {"family_id": "fam_v213_ui"}, ta, "shot-A").get("data") or {}).get("code") or "")
print("code", code)
r = call("/family/invite/accept", {"code": code}, tb, "shot-B")
print("bind", r.get("code"), (r.get("data") or {}).get("linked"))


def shot(token, device, name):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);localStorage.setItem('yh.profile_completed','1');}catch(e){}" % (json.dumps(token), json.dumps(device)))
        pg.goto(BASE + "/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(4800)
        try:
            pg.evaluate("try{document.getElementById('moodAsk').hidden=true;}catch(e){}")
        except Exception:
            pass
        pg.click("button[data-tab='mine']")
        pg.wait_for_timeout(900)
        pg.click("button.mine-item[data-goto='family']")
        pg.wait_for_timeout(2600)
        pg.evaluate("window.scrollTo(0,0)")
        pg.screenshot(path=SHOTS + "\\" + name, full_page=True)
        b.close()


shot(ta, "shot-A", "ui_7_family_owner.png")
shot(tb, "shot-B", "ui_8_family_member.png")
print("done")
