# v6 真链路端到端：A 改名 → 取分享文案 → B 打开邀请链接（真后端 + 真浏览器）→ 自动绑定为好友
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

STAGE = r"D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site"
PY = r"D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe"
PORT = 15091
BASE = f"http://127.0.0.1:{PORT}"
R = []


def note(n, ok, d=""):
    R.append((n, bool(ok), d))
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}  {d}")


def api(method, path, body=None, token=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(BASE + path, data=data, method=method)
    rq.add_header("Content-Type", "application/json")
    if token:
        rq.add_header("Authorization", "Bearer " + token)
    if idem:
        rq.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(rq, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    print("=== 1 打包 + 起服务 ===")
    subprocess.run(["pwsh", "-NoProfile", "-File", r"D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    os.makedirs(os.path.join(STAGE, "data"), exist_ok=True)
    os.makedirs(os.path.join(STAGE, "logs"), exist_ok=True)
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST="127.0.0.1", SHUZI_PORT=str(PORT),
               SHUZI_DATA=os.path.join(STAGE, "data", "state.db"), PYTHONIOENCODING="utf-8")
    log = open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\e2e.log", "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(STAGE, "server", "serve.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    ok = False
    for _ in range(20):
        time.sleep(1.5)
        try:
            s, _ = api("GET", "/api/health")
            if s == 200:
                ok = True
                break
        except Exception:
            pass
    note("服务健康检查", ok)
    if not ok:
        print(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\e2e.log", encoding="utf-8", errors="replace").read()[-800:])
        proc.kill(); sys.exit(1)

    print("=== 2 A 建档 + 改名 + 取分享文案（真后端）===")
    dev_a = f"e2e-A-{int(time.time())}"
    s, j = api("POST", "/api/v1/auth/guest", {"device_id": dev_a})
    tok_a = j["data"]["access_token"]
    api("POST", "/api/v1/profile/birth", {"birth_local": "1990-05-20 08:30",
                                          "longitude": 116.4, "latitude": 39.9}, tok_a, "a-1")
    s, j = api("POST", "/api/v1/me/nickname", {"nickname": "晨光小友"}, tok_a)
    note("A 改名成功", s == 200 and j.get("code") == 0, f"HTTP {s} nickname={(j.get('data') or {}).get('nickname')}")
    s, j = api("GET", "/api/v1/me/referral", None, tok_a)
    ref = j["data"]
    code = ref["invite_code"]
    note("invite_url 含 ?invite=<码>", f"?invite={code}" in ref["invite_url"], ref["invite_url"])
    note("share_text 含昵称与链接", "晨光小友" in ref["share_text"] and code in ref["share_text"], ref["share_text"])

    s, j = api("GET", f"/api/v1/invite/preview?invite_code={code}")
    note("预览接口返回权威昵称（免鉴权）", s == 200 and (j.get("data") or {}).get("nickname") == "晨光小友",
         json.dumps(j.get("data"), ensure_ascii=False))
    note("预览响应不含 member_id", "member_id" not in json.dumps(j), "")

    print("=== 3 B 打开邀请链接（真浏览器）===")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 430, "height": 932})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        calls = []
        pg.on("response", lambda r: calls.append((r.status, r.url.replace(BASE, "")))
              if "/api/" in r.url else None)
        pg.goto(f"{BASE}/?invite={code}", wait_until="load", timeout=60000)
        pg.wait_for_timeout(4000)
        banner = pg.evaluate("""() => {
            const t = document.body.innerText || '';
            return {invited: t.includes('邀请你'), text: (t.match(/[^\\n]*邀请你[^\\n]*/) || [''])[0].slice(0, 80),
                    url: location.search};
        }""")
        note("落地页显示邀请人昵称", "晨光小友" in banner["text"],
             f"banner={banner['text']!r}")
        note("地址栏已清掉 invite 参数", banner["url"] == "", f"search={banner['url']!r}")
        # B 建档（点开始建档 → 填表 → 勾同意 → 提交）
        pg.locator("#btnStart").first.click(timeout=8000)
        pg.wait_for_timeout(1200)
        pg.fill("#inBirthDate", "1988-03-15")
        pg.fill("#inBirthTime", "09:20")
        sel = pg.locator("#inCity")
        opts = sel.locator("option").all_inner_texts()
        real = [o for o in opts if o.strip() and "请选择" not in o and "手动" not in o]
        sel.select_option(label=real[0])
        pg.wait_for_timeout(600)
        for i in range(pg.locator("input[type=checkbox]").count()):
            cb = pg.locator("input[type=checkbox]").nth(i)
            if not cb.is_checked():
                cb.check(timeout=5000)
        pg.locator("button[type=submit]").first.click(timeout=6000)
        pg.wait_for_timeout(12000)
        state = pg.evaluate("""() => {
            const t = document.body.innerText || '';
            const card = document.getElementById('indexCard');
            return {card: !!card, cardText: card ? card.innerText.replace(/\\n/g,' | ').slice(0,120) : '',
                    friendToast: t.includes('成为好友'), hasIndex: /\\d+\\s*分/.test(t)};
        }""")
        print("  B 页面:", json.dumps(state, ensure_ascii=False))
        note("B 建档后出指数卡（绑定不阻塞）", state["card"] and state["hasIndex"], state["cardText"][:80])
        bind_calls = [c for c in calls if "friends/invite" in c[1]]
        note("自动绑定被调用", len(bind_calls) >= 1, f"{bind_calls}")
        note("前端无未捕获异常", len(errs) == 0, str(errs[:2]))
        pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\e2e_B_landing_430x932.png")
        # 再刷新一次：不应重复绑定
        before = len([c for c in calls if "friends/invite" in c[1]])
        pg.reload(wait_until="load", timeout=60000)
        pg.wait_for_timeout(8000)
        after = len([c for c in calls if "friends/invite" in c[1]])
        note("刷新不重复绑定（幂等）", after == before, f"{before} -> {after}")
        # 取 B 的令牌，验证关系
        ctx.close()
        b.close()

    print("=== 4 双向关系核对（真后端）===")
    dev_b = None
    # 从服务端数据直接验证：A 的 friends 里应出现 B（昵称 用户xxxx）
    s, j = api("GET", "/api/v1/friends", None, tok_a)
    fl = (j.get("data") or {}).get("friends") or []
    accepted = [f for f in fl if f.get("status") == "accepted"]
    note("A 侧出现已接受好友", len(accepted) >= 1, json.dumps([f.get("nickname") for f in accepted], ensure_ascii=False))
    s, j = api("GET", "/api/v1/me/referral", None, tok_a)
    note("A 的邀请码仍有效", (j.get("data") or {}).get("invite_code") == code, "")

    proc.terminate()
    time.sleep(1)
    bad = [x for x in R if not x[1]]
    print(f"\n=== 汇总：断言 {len(R)}，通过 {len(R)-len(bad)}，失败 {len(bad)} ===")
    for n, _, d in bad:
        print("  FAIL:", n, d)
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in R],
              open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\e2e_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(0 if not bad else 2)


if __name__ == "__main__":
    main()
