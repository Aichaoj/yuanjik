
import json, os, subprocess, sys, time, urllib.request
ROOT = os.environ['PROBE_ROOT']; STAGE = os.environ['PROBE_STAGE']
PY = os.path.join(ROOT, 'runtime', 'python.exe')
PORT = int(os.environ['PROBE_PORT']); BASE = 'http://127.0.0.1:%d' % PORT
DB = os.environ['PROBE_DB']; PW = os.environ['PROBE_PW']; OUT = os.environ['PROBE_OUT']

try:
    from playwright.sync_api import sync_playwright
except Exception as ex:
    print('PROBE_SKIP playwright 不可用：%s' % ex); sys.exit(3)

for s in ('', '-wal', '-shm'):
    try: os.remove(DB + s)
    except OSError: pass
env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_HOST='127.0.0.1', SHUZI_DATA=DB,
           SHUZI_SRC_ROOT=STAGE, YJK_ADMIN_PASSWORD=PW, PYTHONIOENCODING='utf-8')
proc = subprocess.Popen([PY, os.path.join(STAGE, 'server', 'serve.py')],
                        cwd=os.path.join(STAGE, 'server'), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def http(method, path, body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token: req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))

res = {}
try:
    up = False
    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE + '/api/health', timeout=2) as r:
                if r.status == 200: up = True; break
        except Exception: time.sleep(0.4)
    if not up:
        print('PROBE_SKIP 服务未就绪'); sys.exit(4)
    # 种 2 个会员，让列表页有真行可渲染
    for i in range(2):
        d = http('POST', '/api/v1/auth/guest', {'device_id': 'probe-browser-%d' % i})
        tok = d['data']['access_token']
        http('POST', '/api/v1/profile/birth',
             {'birth_local': '1990-05-20 14:30', 'longitude': 116.4074, 'latitude': 39.9042}, tok)
        http('POST', '/api/v1/checkin', {'on': '2026-09-1%d' % i}, tok)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, w, h in (('430x932', 430, 932), ('1440x900', 1440, 900)):
            page = browser.new_page(viewport={'width': w, 'height': h})
            errs, cons = [], []
            page.on('pageerror', lambda e: errs.append(str(e)))
            page.on('console', lambda m: (cons.append('%s: %s' % (m.type, m.text))
                                          if m.type == 'error' else None))
            page.goto(BASE + '/admin/', wait_until='networkidle')
            scroll0 = page.evaluate('() => [document.documentElement.scrollWidth, window.innerWidth]')
            rowcount0 = page.eval_on_selector_all('#appView table tbody tr', 'e => e.length')
            login_ok = True
            try:
                page.fill('#loginPwd', PW)
                page.click('#loginBtn')
                page.wait_for_selector('#appView', state='visible', timeout=15000)
                page.wait_for_function('() => document.querySelectorAll("#appView table tbody tr").length > 0',
                                       timeout=15000)
            except Exception as ex:
                login_ok = False; errs.append('login/render: %s' % str(ex)[:200])
            time.sleep(0.8)
            scroll1 = page.evaluate('() => [document.documentElement.scrollWidth, window.innerWidth]')
            rows = page.eval_on_selector_all('#appView table tbody tr', 'e => e.length')
            txt = ''
            try: txt = page.inner_text('#appView')[:160]
            except Exception: pass
            try: page.screenshot(path=os.path.join(OUT, 'admin_%s.png' % name))
            except Exception: pass
            res[name] = {'login_ok': login_ok, 'pageerrors': errs, 'console_errors': cons,
                         'scroll_login': scroll0, 'scroll_app': scroll1,
                         'rows_login': rowcount0, 'rows_app': rows, 'text_head': txt}
            page.close()
        browser.close()
finally:
    proc.terminate()
    try: proc.wait(timeout=8)
    except Exception: proc.kill()
print('PROBE_JSON ' + json.dumps(res, ensure_ascii=False))
