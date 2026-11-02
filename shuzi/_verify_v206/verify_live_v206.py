import json, os, sys, urllib.request
LIVE="https://shuzi.yuanjk.cn"; OUT=os.path.join(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v206")
res=[]
def check(n,ok,d=""):
    res.append((n,bool(ok),str(d))); print(("  [PASS] " if ok else "  [FAIL] ")+n+("  -> "+str(d) if d else ""))
v=json.loads(urllib.request.urlopen(LIVE+"/version.json?x=v206",timeout=30).read().decode())
check("线上 web=206", v.get("web")=="206", v.get("web"))
b=urllib.request.urlopen(LIVE+"/body3d.js",timeout=30).read().decode("utf-8")
check("线上 body3d 无金色 #ffb03a", "0xffb03a" not in b)
check("线上 body3d 选中白 + 提亮", "emissive.setHex(on ? 0xb9cede : 0x4a5a66)" in b)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True,args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"])
    c=br.new_context(viewport={"width":390,"height":844},device_scale_factor=2)
    pg=c.new_page(); errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LIVE+"/",wait_until="load",timeout=90000); pg.wait_for_timeout(3000)
    pg.click('.tab-item[data-tab="music"]'); pg.wait_for_timeout(2500)
    pg.click('#btnGoUse'); pg.wait_for_timeout(1500)
    pg.click('[data-layer="meridian"]'); pg.wait_for_timeout(4500)
    check("默认只亮肺经", pg.evaluate("window.YJBody3D.selected()")==["mer_肺"], pg.evaluate("window.YJBody3D.selected()"))
    pg.screenshot(path=os.path.join(OUT,"live_white_default.png"))
    pg.click('#meridianPicker [data-mer="胃"]'); pg.wait_for_timeout(900)
    pg.screenshot(path=os.path.join(OUT,"live_white_stomach.png"))
    check("可切到胃经", pg.evaluate("window.YJBody3D.selected()")==["mer_胃"])
    check("无 JS 异常", not errs, errs[:3])
    br.close()
bad=[x for x in res if not x[1]]
print("\nSUMMARY total=%d fail=%d"%(len(res),len(bad)))
json.dump([{"name":n,"ok":o,"detail":d} for n,o,d in res], open(os.path.join(OUT,"result_v206_live.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(1 if bad else 0)
